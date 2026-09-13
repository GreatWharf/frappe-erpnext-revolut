import importlib
import sys
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace

import pytest

from revolut_bank_feed.core import FeedError


@pytest.fixture
def setup_api(monkeypatch):
    fake = ModuleType("frappe")
    fake.whitelist = lambda *a, **kw: lambda f: f
    fake.only_for = lambda role: None
    doc = SimpleNamespace(
        name="test",
        doctype="Revolut Connection",
        enabled=0,
        authorized=0,
        public_certificate=None,
        issuer="erp.example.test",
    )
    doc.get = lambda field: getattr(doc, field, None)
    fake.get_doc = lambda *a: doc
    writes = []
    fake.db = SimpleNamespace(set_value=lambda *a, **kw: writes.append(a), commit=lambda: None)
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
    auth.secret = lambda *a: None
    auth.exchange = lambda *a: None
    auth.get_client = lambda *a: None
    importer = ModuleType("revolut_bank_feed.importer")
    importer.get_maps = lambda d: {}
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
    monkeypatch.setattr(mod, "secret", lambda *a: "existing-key")
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
    monkeypatch.setattr(mod, "secret", lambda *a: "existing-secret")
    with pytest.raises(FeedError):
        mod.generate_certificate("test", recover_missing_key=1)
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
    mod, _, _ = setup_api
    accounts = [dict(id="known", currency="GBP"), dict(id="unidentified", currency="GBP")]
    monkeypatch.setattr(mod, "get_client", lambda d: SimpleNamespace(get=lambda path: accounts))
    monkeypatch.setattr(mod.frappe.db, "get_value", lambda *a, **k: None, raising=False)
    inserted = []
    monkeypatch.setattr(
        mod.frappe, "get_doc", lambda data: SimpleNamespace(insert=lambda: inserted.append(data))
    )
    result = mod.save_mappings("test", [dict(account_id="known", currency="GBP", bank_account="Main")], "UTC")
    assert result == {"saved": 1}
    assert [r["account_id"] for r in inserted] == ["known"]
