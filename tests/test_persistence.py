"""Run real importer logic with an in-memory Frappe boundary; no live bank calls."""

import copy
import importlib
import json
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace

import pytest
from test_core import mapping, transaction

from revolut_bank_feed.core import FeedError


class Attr(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__

    def as_dict(self):
        return dict(self)


class Store:
    def __init__(self):
        self.rows = {}
        self.serial = 0

    def exists(self, dt, name):
        if isinstance(name, dict):
            return next(
                (
                    key[1]
                    for key, row in self.rows.items()
                    if key[0] == dt and all(row.get(k) == v for k, v in name.items())
                ),
                None,
            )
        return name if (dt, name) in self.rows else None

    def set_value(self, dt, name, key, value=None, **kwargs):
        values = key if isinstance(key, dict) else {key: value}
        self.rows[(dt, name)].update(values)

    def sql(self, *args, **kwargs):
        return []


class Doc(Attr):
    def __init__(self, store, data):
        super().__init__(copy.deepcopy(data))
        object.__setattr__(self, "store", store)
        self.flags = Attr()

    def insert(self, ignore_permissions=False, set_name=None, **kwargs):
        self.store.serial += 1
        self.name = set_name or f"row-{self.store.serial}"
        if (self.doctype, self.name) in self.store.rows:
            raise RuntimeError("duplicate identity")
        self.docstatus = 0
        self.payment_entries = []
        self.allocated_amount = 0
        self.save()
        return self

    def save(self, **kwargs):
        self.store.rows[(self.doctype, self.name)] = copy.deepcopy(dict(self))
        return self

    def submit(self):
        self.docstatus = 1
        return self.save()

    def cancel(self):
        self.docstatus = 2
        return self.save()

    def add_comment(self, *args):
        pass


@pytest.fixture
def importer(monkeypatch):
    store = Store()
    fake = ModuleType("frappe")
    fake.db = store
    fake.flags = Attr()
    fake.session = Attr(user="Administrator")
    fake.utils = SimpleNamespace(escape_html=lambda x: x)

    def get_doc(dt, name=None):
        return Doc(store, store.rows[(dt, name)] if name else dt)

    def get_all(dt, filters, fields=None):
        return [
            Attr(copy.deepcopy(row))
            for (kind, _), row in store.rows.items()
            if kind == dt and all(row.get(k) == v for k, v in filters.items())
        ]

    fake.get_doc, fake.get_all = get_doc, get_all
    fake.get_meta = lambda dt: SimpleNamespace(get_field=lambda field: Attr(fieldtype="Small Text", length=0))
    utils = ModuleType("frappe.utils")
    utils.now_datetime = datetime.now
    monkeypatch.setitem(sys.modules, "frappe", fake)
    monkeypatch.setitem(sys.modules, "frappe.utils", utils)
    for module in ("revolut_bank_feed.guards", "revolut_bank_feed.importer"):
        monkeypatch.delitem(sys.modules, module, raising=False)
    imported = importlib.import_module("revolut_bank_feed.importer")
    yield imported, store
    for module in ("revolut_bank_feed.guards", "revolut_bank_feed.importer"):
        sys.modules.pop(module, None)


def setup_rows():
    conn = Attr(name="connection", company="Acme", environment="Sandbox")
    maps = {("acct-1", "GBP"): Attr(mapping(), name="map", enabled=1)}
    return conn, maps


def banks(store):
    return [row for (dt, _), row in store.rows.items() if dt == "Bank Transaction"]


def test_duplicate_delivery_creates_exactly_one_submitted_bank_transaction(importer):
    module, store = importer
    conn, maps = setup_rows()
    assert module.ingest(conn, transaction(), maps)["created"] == 1
    assert module.ingest(conn, transaction(), maps)["created"] == 0
    assert len(banks(store)) == 1
    assert banks(store)[0]["docstatus"] == 1
    assert banks(store)[0]["transaction_id"] == "tx-1"


@pytest.mark.parametrize(
    "fieldtype,length,expected", [("Data", 0, 140), ("Data", 80, 80), ("Small Text", 0, 300)]
)
def test_reference_fits_bank_schema_without_truncating_source_or_identity(
    importer, monkeypatch, fieldtype, length, expected
):
    module, store = importer
    conn, maps = setup_rows()
    monkeypatch.setattr(
        module.frappe,
        "get_meta",
        lambda dt: SimpleNamespace(get_field=lambda field: Attr(fieldtype=fieldtype, length=length)),
    )
    tx = transaction(reference="R" * 300)
    assert module.ingest(conn, tx, maps) == {"created": 1, "review": 0}
    bank = banks(store)[0]
    assert bank["reference_number"] == "R" * expected
    assert bank["transaction_id"] == tx["id"]
    expected_identity = module.identity(conn.environment, "acct-1", "GBP", tx["id"], "leg-1")
    assert bank["custom_revolut_source_key"] == expected_identity
    assert bank["custom_revolut_entry_key"] == module.identity(expected_identity, 1)
    source = next(row for (dt, _), row in store.rows.items() if dt == "Revolut Source Transaction")
    assert json.loads(source["payload"])["reference"] == tx["reference"]
    assert module.ingest(conn, tx, maps) == {"created": 0, "review": 0}


def test_pending_to_completed(importer):
    module, store = importer
    conn, maps = setup_rows()
    module.ingest(conn, transaction(state="pending"), maps)
    assert not banks(store)
    module.ingest(conn, transaction(), maps)
    assert len(banks(store)) == 1


def test_changed_amount_does_not_mutate_submitted_row_and_requires_review(importer):
    module, store = importer
    conn, maps = setup_rows()
    tx = transaction()
    module.ingest(conn, tx, maps)
    tx["legs"][0]["amount"] = -20
    tx["updated_at"] = "2026-08-03T00:00:00Z"
    assert module.ingest(conn, tx, maps)["review"] == 1
    assert banks(store)[0]["withdrawal"] == 10.25
    assert banks(store)[0]["custom_revolut_review_required"] == 1
    assert len([1 for (dt, _) in store.rows if dt == "Revolut Source Revision"]) == 1
    assert (
        module.ingest(conn, tx, maps, apply_review=True, review_note="Compared with bank statement")[
            "created"
        ]
        == 1
    )
    assert sorted(row["docstatus"] for row in banks(store)) == [1, 2]
    assert len({row["custom_revolut_entry_key"] for row in banks(store)}) == 2


def test_reverted_reconciled_transaction_requires_removing_links(importer):
    module, store = importer
    conn, maps = setup_rows()
    tx = transaction()
    module.ingest(conn, tx, maps)
    bank = banks(store)[0]
    bank["payment_entries"] = [Attr(payment_entry="payment", allocated_amount=10.25)]
    bank["allocated_amount"] = 10.25
    tx.update(state="reverted", updated_at="2026-08-03T00:00:00Z")
    assert module.ingest(conn, tx, maps)["review"] == 1
    with pytest.raises(FeedError, match="remove_reconciliation"):
        module.ingest(conn, tx, maps, apply_review=True, review_note="Check")
    assert bank["docstatus"] == 1


def test_unmapped_source_is_retained_and_replay_after_mapping_recovers(importer):
    module, store = importer
    conn, maps = setup_rows()
    assert module.ingest(conn, transaction(), {})["review"] == 1
    assert not banks(store)
    assert module.ingest(conn, transaction(), maps)["created"] == 1


def test_older_payload_cannot_overwrite_newer_bank_evidence(importer):
    module, store = importer
    conn, maps = setup_rows()
    module.ingest(conn, transaction(updated_at="2026-08-05T00:00:00Z"), maps)
    module.ingest(conn, transaction(state="pending"), maps)
    assert len(banks(store)) == 1
    assert (
        next(row for (dt, _), row in store.rows.items() if dt == "Revolut Source Transaction")[
            "upstream_state"
        ]
        == "completed"
    )


def test_two_fx_legs_sharing_leg_id_remain_distinct(importer):
    module, store = importer
    conn, maps = setup_rows()
    maps[("acct-2", "USD")] = Attr(
        mapping(account_id="acct-2", currency="USD", bank_account="Bank USD"), name="map-2", enabled=1
    )
    tx = transaction(type="exchange")
    tx["legs"].append(dict(leg_id="leg-1", account_id="acct-2", amount=12, currency="USD"))
    assert module.ingest(conn, tx, maps)["created"] == 2
    assert module.ingest(conn, tx, maps)["created"] == 0
    assert len(banks(store)) == 2


@pytest.mark.parametrize("kind,currency", [("exchange", "USD"), ("transfer", "GBP")])
def test_selected_leg_imports_when_counterpart_is_explicitly_skipped(importer, kind, currency):
    module, store = importer
    conn, maps = setup_rows()
    conn.skipped_accounts = json.dumps([dict(account_id="acct-2", currency=currency)])
    tx = transaction(type=kind)
    tx["legs"].append(dict(leg_id="leg-1", account_id="acct-2", amount=12, currency=currency))
    assert module.ingest(conn, tx, maps) == {"created": 1, "review": 0}
    assert module.ingest(conn, tx, maps) == {"created": 0, "review": 0}
    assert [row["bank_account"] for row in banks(store)] == ["Bank GBP"]
    source = next(row for (dt, _), row in store.rows.items() if dt == "Revolut Source Transaction")
    assert len(json.loads(source["payload"])["legs"]) == 2  # Keep skipped-leg evidence.


def test_all_explicitly_skipped_legs_keep_evidence_without_review_or_bank_rows(importer):
    module, store = importer
    conn, _ = setup_rows()
    conn.skipped_accounts = json.dumps([dict(account_id="acct-1", currency="GBP")])
    assert module.ingest(conn, transaction(), {}) == {"created": 0, "review": 0}
    assert not banks(store)
    assert len([row for (dt, _), row in store.rows.items() if dt == "Revolut Source Transaction"]) == 1


@pytest.mark.parametrize("skipped_currency", [None, "EUR"])
def test_unknown_counterpart_or_unexpected_currency_still_requires_review(importer, skipped_currency):
    module, store = importer
    conn, maps = setup_rows()
    conn.skipped_accounts = json.dumps(
        [dict(account_id="acct-2", currency=skipped_currency)] if skipped_currency else []
    )
    tx = transaction(type="exchange")
    tx["legs"].append(dict(leg_id="leg-1", account_id="acct-2", amount=12, currency="USD"))
    assert module.ingest(conn, tx, maps) == {"created": 0, "review": 1}
    assert not banks(store)
    source = next(row for (dt, _), row in store.rows.items() if dt == "Revolut Source Transaction")
    assert source["review_reason"] == "unmapped_account_or_currency"


def test_mapping_previously_skipped_account_imports_only_its_missing_leg(importer):
    module, store = importer
    conn, maps = setup_rows()
    conn.skipped_accounts = json.dumps([dict(account_id="acct-2", currency="USD")])
    tx = transaction(type="exchange")
    tx["legs"].append(dict(leg_id="leg-1", account_id="acct-2", amount=12, currency="USD"))
    assert module.ingest(conn, tx, maps) == {"created": 1, "review": 0}
    maps[("acct-2", "USD")] = Attr(
        mapping(account_id="acct-2", currency="USD", bank_account="Bank USD"), name="map-2", enabled=1
    )
    # An existing mapping takes precedence even if an old skip entry remains.
    assert module.ingest(conn, tx, maps) == {"created": 1, "review": 0}
    assert module.ingest(conn, tx, maps) == {"created": 0, "review": 0}
    assert sorted(row["bank_account"] for row in banks(store)) == ["Bank GBP", "Bank USD"]


def test_skipped_counterpart_does_not_bypass_financial_change_review(importer):
    module, store = importer
    conn, maps = setup_rows()
    conn.skipped_accounts = json.dumps([dict(account_id="acct-2", currency="USD")])
    tx = transaction(type="exchange")
    tx["legs"].append(dict(leg_id="leg-1", account_id="acct-2", amount=12, currency="USD"))
    assert module.ingest(conn, tx, maps)["created"] == 1
    tx["legs"][0]["amount"] = -20
    tx["updated_at"] = "2026-08-03T00:00:00Z"
    assert module.ingest(conn, tx, maps) == {"created": 0, "review": 1}
    assert banks(store)[0]["withdrawal"] == 10.25
    assert banks(store)[0]["custom_revolut_review_required"] == 1


def test_pausing_mapping_never_cancels_historical_rows(importer):
    module, store = importer
    conn, maps = setup_rows()
    tx = transaction()
    module.ingest(conn, tx, maps)
    maps[("acct-1", "GBP")].enabled = 0
    result = module.ingest(conn, tx, maps, apply_review=True, review_note="Review other legs")
    assert result["review"] == 0
    assert banks(store)[0]["docstatus"] == 1
    assert len(banks(store)) == 1


def test_retired_disabled_mapping_does_not_require_active_bank_account(importer, monkeypatch):
    module, store = importer
    conn, maps = setup_rows()
    disabled = Attr(mapping(), name="paused", enabled=0)
    monkeypatch.setattr(module.frappe, "get_all", lambda *args, **kwargs: [disabled])
    # A retired account may no longer be available; map identity must still load.
    result = module.get_maps(conn)
    assert result[("acct-1", "GBP")].enabled == 0


def test_equal_amount_with_different_decimal_scale_is_not_financial_change(importer):
    module, store = importer
    conn, maps = setup_rows()
    tx = transaction()
    tx["legs"][0]["amount"] = "-10.0"
    module.ingest(conn, tx, maps)
    tx["legs"][0]["amount"] = "-10.00"
    tx["updated_at"] = "2026-08-03T00:00:00Z"
    assert module.ingest(conn, tx, maps)["review"] == 0
    assert len(banks(store)) == 1
