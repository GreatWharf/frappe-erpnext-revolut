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
