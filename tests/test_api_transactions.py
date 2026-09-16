import importlib
import sys
from contextlib import contextmanager
from datetime import date
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def api_transactions(monkeypatch):
    events = []
    fake = ModuleType("frappe")
    fake.flags = SimpleNamespace()
    fake.PermissionError = PermissionError
    fake.DoesNotExistError = LookupError
    fake.whitelist = lambda *a, **kw: lambda fn: fn
    fake.only_for = lambda *a: None
    fake.throw = lambda message: (_ for _ in ()).throw(ValueError(message))
    connection = SimpleNamespace(
        doctype="Revolut Connection",
        name="connection",
        enabled=1,
        backfill_next=None,
        historical_from="2020-01-01",
        check_permission=lambda *a: None,
    )
    source = SimpleNamespace(
        connection="connection",
        transaction_id="transaction",
        check_permission=lambda *a: None,
    )
    fake.get_doc = lambda doctype, name, **kw: connection if doctype == "Revolut Connection" else source
    fake.db = SimpleNamespace(
        set_value=lambda *a, **kw: events.append("write"),
        commit=lambda: events.append("commit"),
        rollback=lambda **kw: events.append("rollback"),
        savepoint=lambda name: None,
    )
    utils = ModuleType("frappe.utils")
    utils.getdate = date.fromisoformat
    auth = ModuleType("revolut_bank_feed.auth")

    @contextmanager
    def lock(name):
        events.append("lock")
        try:
            yield
        finally:
            events.append("unlock")

    auth.connection_lock = lock
    auth.get_client = lambda doc: object()
    auth.exchange = lambda *a: None
    auth.authorization_url = lambda *a: ""
    importer = ModuleType("revolut_bank_feed.importer")

    def ingest(*a, **kw):
        events.append("write")
        return {"created": 1}

    importer.ingest = ingest
    sync = ModuleType("revolut_bank_feed.sync")
    sync.enqueue_connection = lambda name: events.append("enqueue")
    sync.safe_error = str
    sync._fetch_one = lambda *a: {}
    for name, module in (
        ("frappe", fake),
        ("frappe.utils", utils),
        ("revolut_bank_feed.auth", auth),
        ("revolut_bank_feed.importer", importer),
        ("revolut_bank_feed.sync", sync),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.api", raising=False)
    module = importlib.import_module("revolut_bank_feed.api")
    yield module, events, connection
    sys.modules.pop("revolut_bank_feed.api", None)


def test_backfill_is_committed_before_unlock_and_enqueue(api_transactions):
    module, events, _ = api_transactions
    module.start_backfill("connection", "2026-01-01", "2026-01-02")
    assert events == ["lock", "write", "commit", "unlock", "enqueue"]


def test_private_key_is_committed_before_unlock(api_transactions, monkeypatch):
    module, events, connection = api_transactions
    connection.enabled = 0
    connection.save = lambda: events.append("write")
    monkeypatch.setattr(module, "RSAPrivateKey", SimpleNamespace)
    monkeypatch.setattr(
        module.serialization, "load_pem_private_key", lambda *a, **kw: SimpleNamespace(key_size=2048)
    )
    module.set_private_key("connection", "dGVzdA==")
    assert events == ["lock", "write", "commit", "unlock"]
    assert module.frappe.flags.revolut_configuration_locked is False


def test_backfill_checks_current_enabled_state_after_lock(api_transactions, monkeypatch):
    module, events, stale = api_transactions
    current = SimpleNamespace(**{**vars(stale), "enabled": 0})
    monkeypatch.setattr(module.frappe, "get_doc", lambda *a, **kw: current if kw.get("for_update") else stale)
    with pytest.raises(ValueError, match="enable_connection_first"):
        module.start_backfill("connection", "2026-01-01", "2026-01-02")
    assert "write" not in events


def test_key_update_checks_current_enabled_state_after_lock(api_transactions, monkeypatch):
    module, events, stale = api_transactions
    stale.enabled = 0
    stale.save = lambda: events.append("write")
    current = SimpleNamespace(**{**vars(stale), "enabled": 1})
    monkeypatch.setattr(module.frappe, "get_doc", lambda *a, **kw: current if kw.get("for_update") else stale)
    monkeypatch.setattr(module, "RSAPrivateKey", SimpleNamespace)
    monkeypatch.setattr(
        module.serialization, "load_pem_private_key", lambda *a, **kw: SimpleNamespace(key_size=2048)
    )
    with pytest.raises(ValueError, match="disable_connection_before_key_change"):
        module.set_private_key("connection", "dGVzdA==")
    assert "write" not in events


def test_review_is_committed_before_unlock(api_transactions):
    module, events, _ = api_transactions
    module.review_and_apply("source", "Checked the bank statement")
    assert events == ["lock", "write", "commit", "unlock"]
