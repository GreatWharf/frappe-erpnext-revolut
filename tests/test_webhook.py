import hashlib
import hmac
import importlib
import json
import sys
import time
from datetime import datetime
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def webhook(monkeypatch):
    fake = ModuleType("frappe")
    fake.flags = SimpleNamespace()
    fake.local = SimpleNamespace(response={})
    fake.whitelist = lambda **kwargs: lambda fn: fn
    rows, commits, queued = {}, [], []
    fake.db = SimpleNamespace(
        get_value=lambda dt, filters, field: (
            ("connection" if filters.get("webhook_key") == "route-key" else None)
            if isinstance(filters, dict)
            else "Acme"
        ),
        exists=lambda dt, name: name in rows,
        commit=lambda: commits.append(True),
    )

    class Doc:
        def __init__(self, data):
            self.data = data

        def insert(self, set_name, **kwargs):
            rows[set_name] = self.data

    fake.get_doc = Doc
    raw = json.dumps(
        {"event": "TransactionCreated", "timestamp": "2026-08-02T00:00:00Z", "data": {"id": "tx-123"}},
        separators=(",", ":"),
    ).encode()
    ts = str(int(time.time() * 1000))
    headers = {
        "Revolut-Request-Timestamp": ts,
        "Revolut-Signature": "v1="
        + hmac.new(b"secret", b"v1." + ts.encode() + b"." + raw, hashlib.sha256).hexdigest(),
    }
    fake.request = SimpleNamespace(
        args={"key": "route-key"}, content_length=len(raw), get_data=lambda **kwargs: raw
    )
    fake.get_request_header = headers.get
    utils = ModuleType("frappe.utils")
    utils.now_datetime = datetime.now
    auth = ModuleType("revolut_bank_feed.auth")
    auth.secret = lambda *args: "secret"
    sync = ModuleType("revolut_bank_feed.sync")
    sync.enqueue_connection = queued.append
    for name, module in [
        ("frappe", fake),
        ("frappe.utils", utils),
        ("revolut_bank_feed.auth", auth),
        ("revolut_bank_feed.sync", sync),
    ]:
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.webhooks", raising=False)
    module = importlib.import_module("revolut_bank_feed.webhooks")
    yield module, fake, rows, commits, queued, headers
    sys.modules.pop("revolut_bank_feed.webhooks", None)


def test_json_webhook_uses_query_string_key_not_frappe_json_form_dict(webhook):
    module, fake, rows, commits, queued, headers = webhook
    # Frappe v15 make_form_dict chooses JSON body instead of merging request.args.
    result = module.receive(event="TransactionCreated", data={"id": "tx-123"})
    assert result["accepted"] is True
    assert len(rows) == 1 and commits
    assert next(iter(rows.values()))["transaction_id"] == "tx-123"
    assert queued == ["connection"]
    module.receive()
    assert len(rows) == 1


def test_invalid_signature_has_no_database_or_queue_side_effect(webhook):
    module, fake, rows, commits, queued, headers = webhook
    headers["Revolut-Signature"] = "v1=invalid"
    assert module.receive()["accepted"] is False
    assert not rows and not commits and not queued
    assert fake.local.response["http_status_code"] == 401


def test_body_cannot_replace_missing_routing_key(webhook):
    module, fake, rows, commits, queued, headers = webhook
    fake.request.args = {}
    assert module.receive(key="route-key")["accepted"] is False
    assert not rows


def test_queue_failure_keeps_durable_webhook(webhook, monkeypatch):
    module, fake, rows, commits, queued, headers = webhook

    def unavailable(*args):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(module, "enqueue_connection", unavailable)
    assert module.receive()["accepted"] is True
    assert len(rows) == 1 and commits
