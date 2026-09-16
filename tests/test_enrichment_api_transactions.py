import importlib
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def enrichment_api_transactions(monkeypatch):
    events = []
    fake = ModuleType("frappe")
    fake.flags = SimpleNamespace()
    fake.local = SimpleNamespace(site="test-site")
    fake.PermissionError = PermissionError
    fake.DoesNotExistError = LookupError
    fake.whitelist = lambda *a, **kw: lambda fn: fn
    fake.only_for = lambda *a: None
    fake.throw = lambda message: (_ for _ in ()).throw(ValueError(message))

    today = datetime.now(timezone.utc)
    quote = SimpleNamespace(
        connection="connection",
        from_currency="EUR",
        to_currency="GBP",
        rate_date=today,
        exchange_rate=1.1,
        currency_exchange=None,
        check_permission=lambda *a: None,
    )
    created = SimpleNamespace(name="CE-0001")

    fake.get_doc = lambda *a, **kw: (
        quote if (a and a[0] == "Revolut FX Quote") else SimpleNamespace(insert=lambda: created)
    )

    @contextmanager
    def cache_lock(key, timeout=60):
        # Same per-currency-pair lock the module acquires around the create-then-commit.
        events.append("lock")
        try:
            yield
        finally:
            events.append("unlock")

    fake.cache = SimpleNamespace(lock=cache_lock)

    fake.db = SimpleNamespace(
        set_value=lambda *a, **kw: events.append("write"),
        commit=lambda: events.append("commit"),
        rollback=lambda **kw: events.append("rollback"),
        exists=lambda *a, **kw: False,
    )

    utils = ModuleType("frappe.utils")
    utils.cint = int
    utils.now_datetime = lambda: today

    api = ModuleType("revolut_bank_feed.api")
    connection = SimpleNamespace(name="connection", environment="Production", enabled=1)
    api.connection_for_user = lambda name: connection
    api.safe_action = lambda fn: fn

    auth = ModuleType("revolut_bank_feed.auth")

    @contextmanager
    def connection_lock(name):
        events.append("lock")
        try:
            yield
        finally:
            events.append("unlock")

    auth.connection_lock = connection_lock
    auth.get_client = lambda doc: object()

    core = ModuleType("revolut_bank_feed.core")

    class FeedError(Exception):
        pass

    core.FeedError = FeedError
    core.utc = lambda value: value

    enrichment = ModuleType("revolut_bank_feed.enrichment")
    enrichment.enqueue = lambda name: events.append("enqueue")
    enrichment.expense_record = lambda *a, **kw: None
    enrichment.receipts = lambda *a, **kw: None

    enrichment_core = ModuleType("revolut_bank_feed.enrichment_core")
    enrichment_core.remote_id = lambda value: value

    for name, module in (
        ("frappe", fake),
        ("frappe.utils", utils),
        ("revolut_bank_feed.api", api),
        ("revolut_bank_feed.auth", auth),
        ("revolut_bank_feed.core", core),
        ("revolut_bank_feed.enrichment", enrichment),
        ("revolut_bank_feed.enrichment_core", enrichment_core),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.enrichment_api", raising=False)
    module = importlib.import_module("revolut_bank_feed.enrichment_api")
    yield module, events, quote
    sys.modules.pop("revolut_bank_feed.enrichment_api", None)


def test_use_quote_commits_new_currency_exchange_before_unlock(enrichment_api_transactions):
    # Mirrors test_api_transactions.py's lock/write/commit/unlock durability assertions,
    # but for enrichment_api.use_quote's per-currency-pair frappe.cache.lock instead of
    # the connection_lock used elsewhere: a racing request must see the created
    # Currency Exchange as committed before the lock is released (no duplicate rate).
    module, events, _ = enrichment_api_transactions
    result = module.use_quote("quote-1")
    assert events == ["lock", "write", "commit", "unlock"]
    assert result == {"name": "CE-0001"}


def test_use_quote_skips_duplicate_creation_when_already_linked(enrichment_api_transactions, monkeypatch):
    # A quote already linked to an existing Currency Exchange must short-circuit before
    # any write/commit -- proving the lock alone (not a redundant insert) is what a
    # concurrent caller relies on to avoid a duplicate same-day rate.
    module, events, quote = enrichment_api_transactions
    quote.currency_exchange = "CE-EXISTING"
    monkeypatch.setattr(module.frappe.db, "exists", lambda *a, **kw: True)
    result = module.use_quote("quote-1")
    assert events == ["lock", "unlock"]
    assert result == {"name": "CE-EXISTING"}


def test_use_quote_refuses_to_overwrite_existing_same_day_rate(enrichment_api_transactions, monkeypatch):
    # A same-day Currency Exchange created by a racing request (visible once that
    # request's commit-before-unlock has landed) must cause this request to refuse,
    # never silently overwrite -- and must never write or commit anything itself.
    module, events, quote = enrichment_api_transactions
    monkeypatch.setattr(module.frappe.db, "exists", lambda *a, **kw: True)
    with pytest.raises(module.FeedError, match="currency_exchange_already_exists_not_overwritten"):
        module.use_quote("quote-1")
    assert "write" not in events
    assert "commit" not in events
    assert events == ["lock", "unlock"]
