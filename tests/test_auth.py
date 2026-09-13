import importlib
import sys
import time
from types import ModuleType, SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.fixture
def auth_module(monkeypatch):
    fake = ModuleType("frappe")
    state = {"token_expires_at": 0, "authorized": 0}
    secrets = {"private_key": "", "access_token": "old-access", "refresh_token": "original-refresh"}
    commits = []
    connection = SimpleNamespace(
        name="connection",
        environment="Sandbox",
        client_id="client",
        issuer="erp.example.test",
        redirect_uri="https://erp.example.test/redirect",
    )

    def get_doc(*args):
        for key, value in state.items():
            setattr(connection, key, value)
        return connection

    fake.get_doc = get_doc
    fake.db = SimpleNamespace(
        set_value=lambda dt, name, values, **kwargs: state.update(values),
        commit=lambda: commits.append(dict(secrets)),
    )
    passwords = ModuleType("frappe.utils.password")
    passwords.get_decrypted_password = lambda dt, name, field, **kwargs: secrets.get(field)
    passwords.set_encrypted_password = lambda dt, name, value, field: secrets.update({field: value})
    redis_errors = ModuleType("redis.exceptions")
    redis_errors.LockError = RuntimeError
    monkeypatch.setitem(sys.modules, "frappe", fake)
    monkeypatch.setitem(sys.modules, "frappe.utils.password", passwords)
    monkeypatch.setitem(sys.modules, "redis.exceptions", redis_errors)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.auth", raising=False)
    module = importlib.import_module("revolut_bank_feed.auth")
    monkeypatch.setattr(module, "signed_assertion", lambda doc: "fresh-short-lived-assertion")
    calls = []

    def token_request(env, signed, **kwargs):
        calls.append((env, signed, kwargs))
        return {"access_token": "new-access", "expires_in": 2399}

    monkeypatch.setattr(module, "token_request", token_request)
    yield module, connection, state, secrets, commits, calls
    sys.modules.pop("revolut_bank_feed.auth", None)


def test_valid_token_does_not_refresh(auth_module):
    module, connection, state, secrets, commits, calls = auth_module
    state["token_expires_at"] = time.time() + 500
    assert module.access_token(connection.name) == "old-access"
    assert not calls and not commits


def test_expiry_refresh_preserves_refresh_token_if_response_omits_it(auth_module):
    module, connection, state, secrets, commits, calls = auth_module
    assert module.access_token(connection.name) == "new-access"
    assert secrets["refresh_token"] == "original-refresh"
    assert commits[-1]["access_token"] == "new-access"
    assert calls[0][2] == {"refresh_token": "original-refresh"}
    assert state["token_expires_at"] > time.time() + 2300


def test_forced_401_refresh_even_before_expiry(auth_module):
    module, connection, state, secrets, commits, calls = auth_module
    state["token_expires_at"] = time.time() + 500
    assert module.access_token(connection.name, force=True) == "new-access"
    assert len(calls) == 1


def test_rotated_refresh_token_is_persisted_with_access_token(auth_module):
    module, connection, state, secrets, commits, calls = auth_module
    module.save_tokens(
        connection, {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 2399}
    )
    assert commits[-1]["refresh_token"] == "refresh-2"
    assert state["authorized"] == 1


def test_authorization_url_requests_read_only(auth_module):
    module, connection, state, secrets, commits, calls = auth_module
    url = urlparse(module.authorization_url(connection))
    assert url.hostname == "sandbox-business.revolut.com"
    assert parse_qs(url.query)["scope"] == ["READ"]
    assert parse_qs(url.query)["redirect_uri"] == [connection.redirect_uri]
