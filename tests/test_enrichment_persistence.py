import importlib
import json
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def extra(monkeypatch):
    records = {}
    updates = []
    files = []
    fake = ModuleType("frappe")

    def get_value(dt, key, fields, **kw):
        if isinstance(key, dict):
            return None
        row = records.get((dt, key), {})
        return {f: row.get(f) for f in fields} if isinstance(fields, list) else row.get(fields)

    def set_value(dt, key, field, value=None, **kw):
        changes = field if isinstance(field, dict) else {field: value}
        records.setdefault((dt, key), {}).update(changes)
        updates.append((dt, key, changes))

    class Doc:
        def __init__(self, data):
            self.data = data
            self.name = data["record_key"]

        def insert(self, **kw):
            records[(self.data["doctype"], self.name)] = dict(self.data)
            return self

    fake.db = SimpleNamespace(
        get_value=get_value,
        set_value=set_value,
        commit=lambda: None,
        exists=lambda dt, key: (dt, key) in records,
        rollback=lambda: None,
    )
    fake.get_doc = lambda data: Doc(data)
    fake.get_all = lambda *a, **kw: []
    utils = ModuleType("frappe.utils")
    utils.now_datetime = datetime.now
    manager = ModuleType("frappe.utils.file_manager")

    def save_file(filename, data, dt, name, **kw):
        files.append((filename, data, dt, name, kw))
        key = "file-" + str(len(files))
        records[("File", key)] = {}
        return SimpleNamespace(name=key)

    manager.save_file = save_file
    auth = ModuleType("revolut_bank_feed.auth")
    auth.connection_lock = lambda *a: None
    auth.get_client = lambda *a: None
    sync = ModuleType("revolut_bank_feed.sync")
    sync.safe_error = lambda e: type(e).__name__
    for key, value in [
        ("frappe", fake),
        ("frappe.utils", utils),
        ("frappe.utils.file_manager", manager),
        ("revolut_bank_feed.auth", auth),
        ("revolut_bank_feed.sync", sync),
    ]:
        monkeypatch.setitem(sys.modules, key, value)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.enrichment", raising=False)
    mod = importlib.import_module("revolut_bank_feed.enrichment")
    yield mod, records, updates, files
    sys.modules.pop("revolut_bank_feed.enrichment", None)


def test_upsert_is_idempotent_and_preserves_accounting_link(extra):
    mod, records, updates, _ = extra
    connection = SimpleNamespace(name="conn", company="Company")
    name = mod.upsert("Revolut Expense", connection, "id", {"amount": 12}, display_name="Expense")
    records[("Revolut Expense", name)]["linked_document"] = "PINV-0001"
    updates.clear()
    assert mod.upsert("Revolut Expense", connection, "id", {"amount": 12}, display_name="Expense") == name
    assert len(records) == 1
    assert all(set(u[2]) == {"last_seen_at"} for u in updates)
    mod.upsert("Revolut Expense", connection, "id", {"amount": 15}, display_name="Changed")
    assert records[("Revolut Expense", name)]["linked_document"] == "PINV-0001"
    assert json.loads(records[("Revolut Expense", name)]["data"])["amount"] == 15


def test_receipts_are_private_and_not_downloaded_twice(extra):
    mod, records, _, files = extra
    connection = SimpleNamespace(name="conn", sync_receipts=1)
    calls = []
    client = SimpleNamespace(get=lambda *a, **kw: calls.append((a, kw)) or b"%PDF-1.7\n")
    for _ in range(2):
        mod.receipts(connection, client, "expense", {"id": "expense", "receipt_ids": ["receipt"]})
    assert len(calls) == len(files) == 1
    assert files[0][-1] == {"is_private": 1}
    assert files[0][2:4] == ("Revolut Expense", "expense")
    assert calls[0][1] == {"binary": True}


def test_receipt_failure_does_not_prevent_expense_save(extra):
    mod, records, _, _ = extra
    connection = SimpleNamespace(name="conn", company="Company", sync_receipts=1)

    def fail(*a, **kw):
        raise AssertionError("receipt must be fetched separately")

    name = mod.expense_record(
        connection,
        SimpleNamespace(get=fail),
        {
            "id": "expense",
            "state": "approved",
            "expense_date": "2026-09-12T00:00:00Z",
            "spent_amount": {"amount": 12, "currency": "GBP"},
            "receipt_ids": ["receipt"],
        },
    )
    assert records[("Revolut Expense", name)]["receipt_pending"] == 1


def test_catalog_pagination_follows_opaque_cursor(extra):
    mod, _, _, _ = extra
    calls = []

    def fetch(path, params):
        calls.append(params)
        return (
            {"tax_rates": [{"id": "a"}], "next_page_token": "next"}
            if "page_token" not in params
            else {"tax_rates": [{"id": "b"}]}
        )

    assert [r["id"] for r in mod.catalog_rows(SimpleNamespace(get=fetch), "/tax-rates", "tax_rates")] == [
        "a",
        "b",
    ]
    assert calls[1]["page_token"] == "next"


def test_expense_window_resumes_checkpoint_after_interruption(extra, monkeypatch):
    from datetime import timedelta, timezone

    from revolut_bank_feed.core import FeedError, iso, utc

    mod, records, _, _ = extra
    connection = SimpleNamespace(name="conn")
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    rows = [{"id": str(i), "expense_date": iso(start + timedelta(seconds=i))} for i in range(205)]
    imported = set()
    calls = []
    monkeypatch.setattr(mod, "expense_record", lambda c, cl, r: imported.add(r["id"]))
    fail = [True]

    def fetch(path, params):
        calls.append(params)
        if fail[0] and len(calls) == 3:
            raise FeedError("interrupted")
        return sorted(
            [r for r in rows if utc(params["from"]) <= utc(r["expense_date"]) < utc(params["to"])],
            key=lambda r: r["expense_date"],
            reverse=True,
        )[: params["count"]]

    client = SimpleNamespace(get=fetch)
    with pytest.raises(FeedError, match="interrupted"):
        mod.expense_window(connection, client, start, end, "expense")
    checkpoint = records[("Revolut Connection", "conn")]["expense_window_to"]
    assert utc(checkpoint) < end
    fail[0] = False
    calls.clear()
    finished = mod.expense_window(connection, client, start, end + timedelta(days=5), "expense")
    assert calls[0]["to"] == checkpoint
    assert finished == end
    assert len(imported) == 205


def test_changed_linked_expense_flags_review(extra):
    mod, records, _, _ = extra
    connection = SimpleNamespace(name="conn", company="Company")
    name = mod.upsert("Revolut Expense", connection, "id", {"state": "approved"})
    records[("Revolut Expense", name)]["linked_document"] = "PINV-1"
    mod.upsert("Revolut Expense", connection, "id", {"state": "rejected"})
    assert records[("Revolut Expense", name)]["accounting_review_required"] == 1


def test_bad_receipt_does_not_starve_supported_sibling(extra):
    from revolut_bank_feed.core import FeedError

    mod, records, _, files = extra
    connection = SimpleNamespace(name="conn", sync_receipts=1)
    client = SimpleNamespace(get=lambda path, **kw: b"unsupported" if "/bad/" in path else b"%PDF-1.7\n")
    with pytest.raises(FeedError):
        mod.receipts(connection, client, "expense", {"id": "expense", "receipt_ids": ["bad", "good"]})
    assert len(files) == 1
    assert "good" in json.loads(records[("Revolut Expense", "expense")]["receipt_files"])


def test_account_reappearing_restores_active_state(extra, monkeypatch):
    mod, records, _, _ = extra
    connection = SimpleNamespace(name="conn", company="Company")

    def listing(*a, **kw):
        return [
            SimpleNamespace(name=key[1], remote_id=value["remote_id"])
            for key, value in records.items()
            if key[0] == "Revolut Account Snapshot"
        ]

    monkeypatch.setattr(mod.frappe, "get_all", listing)
    account = {"id": "account", "currency": "GBP", "balance": 100, "state": "active"}
    mod.account_snapshots(connection, [account])
    mod.account_snapshots(connection, [])
    assert next(iter(records.values()))["upstream_state"] == "missing_from_latest_list"
    mod.account_snapshots(connection, [account])
    assert next(iter(records.values()))["upstream_state"] == "active"
