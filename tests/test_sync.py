import importlib
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace

import pytest

from revolut_bank_feed.core import FeedError, iso, utc


@pytest.fixture
def sync_module(monkeypatch):
    state, imports, commits = {}, set(), []
    fake = ModuleType("frappe")
    fake.db = SimpleNamespace(
        get_value=lambda dt, name, fields, **kwargs: {key: state.get(key) for key in fields},
        set_value=lambda dt, name, key, value=None, **kwargs: state.update(
            key if isinstance(key, dict) else {key: value}
        ),
        savepoint=lambda *args: None,
        rollback=lambda **kwargs: None,
        commit=lambda: commits.append(dict(state)),
    )
    utils = ModuleType("frappe.utils")
    utils.now_datetime = datetime.now
    auth = ModuleType("revolut_bank_feed.auth")
    auth.connection_lock = lambda *args: None
    auth.get_client = lambda *args: None
    importer = ModuleType("revolut_bank_feed.importer")
    importer.get_maps = lambda *args: {}

    def ingest(conn, tx, maps):
        created = tx["id"] not in imports
        imports.add(tx["id"])
        return {"created": int(created), "review": 0}

    importer.ingest = ingest
    for name, module in [
        ("frappe", fake),
        ("frappe.utils", utils),
        ("revolut_bank_feed.auth", auth),
        ("revolut_bank_feed.importer", importer),
    ]:
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.sync", raising=False)
    module = importlib.import_module("revolut_bank_feed.sync")
    yield module, state, imports, commits
    sys.modules.pop("revolut_bank_feed.sync", None)


def test_interrupted_window_resumes_at_committed_page_and_frozen_end(sync_module):
    module, state, imports, commits = sync_module
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    rows = [{"id": str(i), "created_at": iso(end - timedelta(seconds=i + 1))} for i in range(510)]
    connection = SimpleNamespace(name="connection")
    stats = dict(transactions_seen=0, bank_rows_created=0, review_count=0)

    class Client:
        fail = True

        def get(self, path, params):
            if self.fail and params["count"] == 500 and utc(params["to"]) < end:
                raise FeedError("revolut_network_error")
            return [row for row in rows if utc(params["from"]) <= utc(row["created_at"]) < utc(params["to"])][
                : params["count"]
            ]

    client = Client()
    with pytest.raises(FeedError):
        module._window(connection, client, {}, stats, start, end, "poll")
    assert len(imports) == 500
    assert utc(state["poll_window_to"]) == utc(rows[499]["created_at"])
    assert utc(state["poll_window_end"]) == end
    client.fail = False
    finished = module._window(connection, client, {}, stats, start, end + timedelta(days=1), "poll")
    assert len(imports) == 510
    assert stats["bank_rows_created"] == 510
    assert finished == end
    assert state["poll_window_to"] is None


def test_transaction_identity_mismatch_is_rejected(sync_module):
    module, state, imports, commits = sync_module
    client = SimpleNamespace(get=lambda path: {"id": "different"})
    with pytest.raises(FeedError, match="transaction_identity_mismatch"):
        module._fetch_one(client, "expected")


def test_unknown_exception_is_redacted(sync_module):
    module, state, imports, commits = sync_module
    assert module.safe_error(ValueError("sensitive token/body")) == "internal_error_ValueError"


def test_bad_pending_item_does_not_starve_later_pending_records(sync_module, monkeypatch):
    module, state, imports, commits = sync_module
    connection = SimpleNamespace(name="connection")
    pending = [
        SimpleNamespace(name="bad-source", transaction_id="bad"),
        SimpleNamespace(name="good-source", transaction_id="good"),
    ]
    monkeypatch.setattr(module.frappe, "get_all", lambda *args, **kwargs: pending, raising=False)

    class Client:
        def get(self, path):
            if path.endswith("/bad"):
                raise FeedError("revolut_http_404")
            return {"id": "good"}

    stats = dict(transactions_seen=0, bank_rows_created=0, review_count=0)
    with pytest.raises(FeedError):
        module._pending(connection, Client(), {}, stats)
    assert "good" in imports
    assert "last_checked" in state
