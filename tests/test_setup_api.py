import importlib
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from revolut_bank_feed.core import FeedError


@pytest.fixture
def setup_api(monkeypatch):
    fake = ModuleType("frappe")
    fake.whitelist = lambda *a, **kw: lambda f: f
    fake.only_for = lambda role: None
    fake.parse_json = json.loads
    doc = SimpleNamespace(
        name="test",
        doctype="Revolut Connection",
        enabled=0,
        authorized=0,
        public_certificate=None,
        issuer="erp.example.test",
    )
    doc.get = lambda field: getattr(doc, field, None)
    fake.get_doc = lambda *a, **kw: doc
    writes = []
    fake.db = SimpleNamespace(
        set_value=lambda *a, **kw: writes.append(a), commit=lambda: None, sql=lambda *a, **kw: []
    )
    utils = ModuleType("frappe.utils")
    utils.cint = lambda v: int(v or 0)
    utils.get_url = lambda p: "https://erp.example.test" + p
    utils.today = lambda: "2026-09-12"
    passwords = ModuleType("frappe.utils.password")
    passwords.set_encrypted_password = lambda *a: writes.append(a)
    api = ModuleType("revolut_bank_feed.api")
    api.connection_for_user = lambda c: doc
    api.safe_action = lambda f: f
    auth = ModuleType("revolut_bank_feed.auth")
    auth.connection_lock = lambda c: nullcontext()
    auth.lock_configuration = lambda c: None
    auth.secret = lambda *a: None
    auth.exchange = lambda *a: None
    auth.get_client = lambda *a: None
    importer = ModuleType("revolut_bank_feed.importer")
    importer.get_maps = lambda d, **kw: {}
    sync = ModuleType("revolut_bank_feed.sync")
    sync.enqueue_connection = lambda c: None
    for name, mod in [
        ("frappe", fake),
        ("frappe.utils", utils),
        ("frappe.utils.password", passwords),
        ("revolut_bank_feed.api", api),
        ("revolut_bank_feed.auth", auth),
        ("revolut_bank_feed.importer", importer),
        ("revolut_bank_feed.sync", sync),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.setup", raising=False)
    mod = importlib.import_module("revolut_bank_feed.setup")
    yield mod, doc, writes
    sys.modules.pop("revolut_bank_feed.setup", None)


def test_public_connection_excludes_credentials(setup_api, monkeypatch):
    mod, doc, _ = setup_api
    doc.private_key = "secret-key"
    doc.access_token = "secret-access"
    doc.refresh_token = "secret-refresh"
    monkeypatch.setattr(mod, "secret", lambda *a: "secret-key")
    result = mod.public_connection(doc)
    assert result["has_private_key"] is True
    assert not {"private_key", "access_token", "refresh_token", "webhook_secret"} & result.keys()
    assert "secret-key" not in str(result)


def test_certificate_returns_only_public_material(setup_api):
    mod, _, writes = setup_api
    result = mod.generate_certificate("test")
    assert set(result) == {"public_certificate", "expires_on"}
    assert "BEGIN CERTIFICATE" in result["public_certificate"]
    assert "PRIVATE" not in str(result)
    assert writes[0][-1] == "private_key"
    document_updates = [args[2] for args in writes if isinstance(args[2], dict)]
    assert any(update.get("private_key") == "********" for update in document_updates)


def test_certificate_does_not_replace_manual_key(setup_api, monkeypatch):
    mod, _, writes = setup_api
    monkeypatch.setattr(mod.frappe.db, "sql", lambda *a, **kw: [(1,)])
    with pytest.raises(FeedError, match="certificate_already_configured"):
        mod.generate_certificate("test")
    assert not writes


@pytest.mark.parametrize("field", ["enabled", "authorized", "public_certificate"])
def test_certificate_refuses_configured_connection(setup_api, field):
    mod, doc, writes = setup_api
    setattr(doc, field, 1)
    with pytest.raises(FeedError):
        mod.generate_certificate("test")
    assert not writes


def test_activate_requires_mapping_and_consent(setup_api):
    mod, _, writes = setup_api
    with pytest.raises(FeedError, match="finish_authorization"):
        mod.activate("test")
    assert not writes


def test_explicit_recovery_replaces_only_orphaned_certificate(setup_api):
    mod, doc, writes = setup_api
    doc.public_certificate = "old-public-certificate"
    mod.generate_certificate("test", recover_missing_key=1)
    update = next(args[2] for args in writes if isinstance(args[2], dict))
    assert update["client_id"] == "pending-setup"
    assert update["private_key"] == "********"


@pytest.mark.parametrize("field", ["enabled", "authorized"])
def test_recovery_refuses_active_connection(setup_api, field):
    mod, doc, writes = setup_api
    setattr(doc, field, 1)
    with pytest.raises(FeedError):
        mod.generate_certificate("test", recover_missing_key=1)
    assert not writes


def test_recovery_refuses_existing_secrets(setup_api, monkeypatch):
    mod, doc, writes = setup_api
    doc.public_certificate = "old-public-certificate"
    monkeypatch.setattr(mod.frappe.db, "sql", lambda *a, **kw: [(1,)])
    with pytest.raises(FeedError):
        mod.generate_certificate("test", recover_missing_key=1)
    assert not writes


@pytest.mark.parametrize("recover", [False, True])
def test_certificate_detects_concurrently_saved_credentials_without_decrypting(
    setup_api, monkeypatch, recover
):
    mod, doc, writes = setup_api
    doc.public_certificate = "old-public-certificate" if recover else None
    reads = []

    def sql(query, values):
        reads.append(query)
        assert "SELECT 1" in query
        assert "`__Auth`" in query
        assert values == ("Revolut Connection", "test")
        assert all(field in query for field in ("private_key", "access_token", "refresh_token"))
        assert "`encrypted` = 1" in query
        return [(1,)] if "FOR UPDATE" in query else []

    monkeypatch.setattr(mod.frappe.db, "sql", sql)
    # The old snapshot's secret() would return None; the guard must not use it.
    with pytest.raises(FeedError, match="certificate_already_configured"):
        mod.generate_certificate("test", recover_missing_key=recover)
    assert len(reads) == 1
    assert not writes


def test_certificate_existence_check_never_decrypts_credentials(setup_api, monkeypatch):
    mod, _, _ = setup_api
    monkeypatch.setattr(mod, "secret", lambda *a: pytest.fail("Existence guard must not decrypt credentials"))
    mod.generate_certificate("test")


@pytest.mark.parametrize("field", ["enabled", "authorized", "public_certificate"])
def test_certificate_observes_configuration_committed_before_lock(setup_api, monkeypatch, field):
    mod, doc, writes = setup_api
    fresh = SimpleNamespace(**vars(doc))
    setattr(fresh, field, 1)
    monkeypatch.setattr(mod.frappe, "get_doc", lambda *args, for_update=False: fresh if for_update else doc)
    with pytest.raises(FeedError, match="certificate_already_configured"):
        mod.generate_certificate("test")
    assert not writes


@pytest.mark.parametrize("field", ["enabled", "authorized"])
def test_client_id_observes_configuration_committed_before_lock(setup_api, monkeypatch, field):
    mod, doc, writes = setup_api
    doc.save = lambda: writes.append("save")
    mod.frappe.flags = SimpleNamespace()
    fresh = SimpleNamespace(**vars(doc))
    setattr(fresh, field, 1)
    monkeypatch.setattr(mod.frappe, "get_doc", lambda *args, for_update=False: fresh if for_update else doc)
    with pytest.raises(FeedError, match="use_advanced_settings_to_change_authorized_client"):
        mod.save_client_id("test", "new-client")
    assert not writes


def test_activate_observes_authorization_committed_before_lock(setup_api, monkeypatch):
    mod, doc, writes = setup_api
    fresh = SimpleNamespace(**vars(doc))
    fresh.authorized = 1
    monkeypatch.setattr(mod.frappe, "get_doc", lambda *args, for_update=False: fresh if for_update else doc)
    monkeypatch.setattr(mod, "get_maps", lambda *args, **kwargs: {"map": SimpleNamespace(enabled=1)})
    assert mod.activate("test") == {"queued": True}
    assert writes == [("Revolut Connection", "test", "enabled", 1)]


def test_activate_rejects_mapping_disabled_after_request_snapshot(setup_api, monkeypatch):
    mod, doc, writes = setup_api
    doc.authorized = 1
    monkeypatch.setattr(
        mod,
        "get_maps",
        lambda connection, *, for_update=False: {"map": SimpleNamespace(enabled=not for_update)},
    )
    with pytest.raises(FeedError, match="finish_authorization_and_account_mapping_first"):
        mod.activate("test")
    assert not writes


def test_account_options_exposes_identifying_details_only(setup_api, monkeypatch):
    mod, doc, _ = setup_api
    doc.company = "Acme"
    account = dict(
        id="a",
        name=None,
        currency="GBP",
        balance=0,
        state="active",
        type="current",
        created_at="2020-01-01",
        updated_at="2026-09-13",
        unexpected_secret="must-not-leak",
    )
    monkeypatch.setattr(mod, "get_client", lambda d: SimpleNamespace(get=lambda path: [account]))
    monkeypatch.setattr(mod.frappe, "get_list", lambda *a, **k: [], raising=False)
    result = mod.account_options("test")["accounts"][0]
    assert result["balance"] == 0
    assert result["type"] == "current"
    assert result["created_at"] == "2020-01-01"
    assert "unexpected_secret" not in result


def test_save_mappings_allows_selecting_only_known_accounts(setup_api, monkeypatch):
    mod, doc, _ = setup_api
    accounts = [dict(id="known", currency="GBP"), dict(id="unidentified", currency="GBP")]
    monkeypatch.setattr(mod, "get_client", lambda d: SimpleNamespace(get=lambda path: accounts))
    monkeypatch.setattr(mod.frappe.db, "get_value", lambda *a, **k: None, raising=False)
    inserted = []
    monkeypatch.setattr(
        mod.frappe,
        "get_doc",
        lambda data, name=None, **kwargs: (
            doc if name else SimpleNamespace(insert=lambda: inserted.append(data))
        ),
    )
    result = mod.save_mappings("test", [dict(account_id="known", currency="GBP", bank_account="Main")], "UTC")
    assert result == {"saved": 1}
    assert [r["account_id"] for r in inserted] == ["known"]


@pytest.fixture
def mapping_api(setup_api, monkeypatch):
    mod, doc, writes = setup_api
    accounts = [dict(id="known", currency="GBP"), dict(id="unidentified", currency="USD")]
    monkeypatch.setattr(mod, "get_client", lambda d: SimpleNamespace(get=lambda path: accounts))
    monkeypatch.setattr(mod.frappe.db, "get_value", lambda *a, **k: None, raising=False)
    inserted = []
    monkeypatch.setattr(
        mod.frappe,
        "get_doc",
        lambda data, name=None, **kwargs: (
            doc if name else SimpleNamespace(insert=lambda: inserted.append(data))
        ),
    )
    return mod, doc, writes, inserted


def saved_skips(writes):
    return json.loads(next(args[3] for args in writes if args[2] == "skipped_accounts"))


def test_save_mappings_persists_only_explicit_verified_skips(mapping_api):
    mod, _, writes, inserted = mapping_api
    result = mod.save_mappings(
        "test",
        json.dumps([dict(account_id="known", currency="GBP", bank_account="Main")]),
        skipped_accounts=json.dumps([dict(account_id="unidentified", currency="USD", ignored="extra")]),
    )
    assert result == {"saved": 1}
    assert saved_skips(writes) == [dict(account_id="unidentified", currency="USD")]
    assert [row["account_id"] for row in inserted] == ["known"]


def test_save_all_skipped_accounts_does_not_activate_or_create_mappings(mapping_api):
    mod, _, writes, inserted = mapping_api
    skipped = [dict(account_id="known", currency="GBP"), dict(account_id="unidentified", currency="USD")]
    assert mod.save_mappings("test", [], skipped_accounts=skipped) == {"saved": 0}
    assert saved_skips(writes) == skipped
    assert not inserted
    assert all(args[2] == "skipped_accounts" for args in writes)


@pytest.mark.parametrize(
    "skipped",
    [
        [dict(account_id="unknown", currency="USD")],
        [dict(account_id="unidentified", currency="EUR")],
        [dict(account_id="unidentified", currency="USD")] * 2,
        [dict(account_id="known", currency="GBP")],
    ],
)
def test_skip_requests_reject_unknown_currency_duplicate_or_selected_accounts(mapping_api, skipped):
    mod, _, writes, inserted = mapping_api
    with pytest.raises(FeedError, match="invalid_or_duplicate_account_selection"):
        mod.save_mappings(
            "test", [dict(account_id="known", currency="GBP", bank_account="Main")], skipped_accounts=skipped
        )
    assert not writes
    assert not inserted


def test_existing_mapping_cannot_be_replaced_with_skip(mapping_api, monkeypatch):
    mod, _, writes, inserted = mapping_api
    monkeypatch.setattr(
        mod.frappe.db, "get_value", lambda *a, **k: SimpleNamespace(name="map", bank_account="Main")
    )
    with pytest.raises(FeedError, match="existing_mapping_cannot_be_skipped"):
        mod.save_mappings("test", [], skipped_accounts=[dict(account_id="known", currency="GBP")])
    assert not writes
    assert not inserted


def test_mapping_previously_skipped_account_preserves_other_exclusions(mapping_api):
    mod, doc, writes, _ = mapping_api
    doc.skipped_accounts = json.dumps(
        [dict(account_id="known", currency="GBP"), dict(account_id="old-closed", currency="EUR")]
    )
    mod.save_mappings("test", [dict(account_id="known", currency="GBP", bank_account="Main")])
    assert saved_skips(writes) == [dict(account_id="old-closed", currency="EUR")]


def test_mapping_configuration_lock_follows_discovery_and_rechecks_enabled(mapping_api, monkeypatch):
    mod, doc, writes, inserted = mapping_api
    events = []

    def discover(path):
        events.append("discover")
        return [dict(id="known", currency="GBP")]

    monkeypatch.setattr(mod, "get_client", lambda d: SimpleNamespace(get=discover))
    monkeypatch.setattr(mod, "lock_configuration", lambda name: events.append("lock"), raising=False)
    fresh = SimpleNamespace(**vars(doc))
    fresh.enabled = 1  # Activated by another request after the initial permission check.

    def get_doc(data, name=None, *, for_update=False):
        events.append("reload")
        assert events == ["discover", "lock", "reload"]
        # Ordinary reads retain the request's pre-lock REPEATABLE READ snapshot.
        return fresh if for_update else doc

    monkeypatch.setattr(mod.frappe, "get_doc", get_doc)
    with pytest.raises(FeedError, match="pause_connection_before_mapping"):
        mod.save_mappings("test", [], skipped_accounts=[dict(account_id="known", currency="GBP")])
    assert events == ["discover", "lock", "reload"]
    assert not writes
    assert not inserted


def test_mapping_skip_merge_uses_fresh_configuration_inside_lock(mapping_api, monkeypatch):
    mod, doc, writes, _ = mapping_api
    fresh = SimpleNamespace(**vars(doc))
    fresh.skipped_accounts = json.dumps([dict(account_id="concurrently-skipped", currency="EUR")])
    fresh.get = lambda key: getattr(fresh, key, None)
    monkeypatch.setattr(
        mod.frappe,
        "get_doc",
        lambda data, name=None, *, for_update=False: fresh if for_update else doc,
    )
    mod.save_mappings("test", [], skipped_accounts=[dict(account_id="known", currency="GBP")])
    assert saved_skips(writes) == [
        dict(account_id="concurrently-skipped", currency="EUR"),
        dict(account_id="known", currency="GBP"),
    ]


@pytest.mark.parametrize("action", ["skip", "reuse", "replace"])
def test_mapping_lookup_observes_mapping_committed_after_request_snapshot(mapping_api, monkeypatch, action):
    mod, _, writes, inserted = mapping_api
    locked = []
    monkeypatch.setattr(mod, "lock_configuration", locked.append)

    def get_value(doctype, filters, fields, *, as_dict=False, for_update=False):
        assert locked == ["test"]
        assert doctype == "Revolut Account Map"
        assert filters == {"connection": "test", "account_id": "known", "currency": "GBP"}
        assert fields == ["name", "bank_account"]
        assert as_dict
        # Another request inserted this map after the initial permission read.
        return SimpleNamespace(name="concurrent-map", bank_account="Main") if for_update else None

    monkeypatch.setattr(mod.frappe.db, "get_value", get_value)
    pair = dict(account_id="known", currency="GBP")
    if action == "skip":
        with pytest.raises(FeedError, match="existing_mapping_cannot_be_skipped"):
            mod.save_mappings("test", [], skipped_accounts=[pair])
        assert not writes
    elif action == "replace":
        with pytest.raises(FeedError, match="existing_mapping_is_immutable"):
            mod.save_mappings("test", [dict(pair, bank_account="Other")])
        assert not writes
    else:
        assert mod.save_mappings("test", [dict(pair, bank_account="Main")]) == {"saved": 1}
    assert not inserted


def test_skip_state_is_read_only_hidden_and_not_copied():
    root = Path(__file__).parents[1]
    schema = json.loads(
        (
            root / "revolut_bank_feed/revolut_bank_feed/doctype/revolut_connection/revolut_connection.json"
        ).read_text()
    )
    field = next((row for row in schema["fields"] if row["fieldname"] == "skipped_accounts"), None)
    assert field is not None
    assert field["read_only"] == field["hidden"] == field["no_copy"] == 1
    assert "skipped_accounts" in schema["field_order"]
