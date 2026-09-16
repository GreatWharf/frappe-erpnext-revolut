"""Encrypted credential persistence. All callers must hold connection_lock."""

import base64
import time
from contextlib import contextmanager
from urllib.parse import urlencode

import frappe
from frappe.utils.password import get_decrypted_password, set_encrypted_password
from redis.exceptions import LockError

from .client import Client, assertion, token_request
from .core import FeedError

DOCTYPE = "Revolut Connection"


def secret(name, field):
    return get_decrypted_password(DOCTYPE, name, field, raise_exception=False)


@contextmanager
def connection_lock(name, blocking_timeout=0):
    # The worker budget is 600 s and RQ hard timeout 900 s; lease outlives both.
    lock = frappe.cache.lock(
        f"revolut-feed:{frappe.local.site}:{name}", timeout=960, blocking_timeout=blocking_timeout
    )
    if not lock.acquire(blocking=blocking_timeout > 0):
        raise FeedError("connection_busy")
    try:
        yield
    finally:
        try:
            lock.release()
        except LockError:
            pass


def lock_configuration(name):
    """Keep configuration changes serialized until their database transaction ends."""
    held = getattr(frappe.local, "revolut_configuration_locks", None)
    if held is None:
        held = frappe.local.revolut_configuration_locks = {}
    if name in held:
        return
    lock = frappe.cache.lock(f"revolut-feed:{frappe.local.site}:{name}", timeout=960, blocking_timeout=0)
    if not lock.acquire(blocking=False):
        raise FeedError("connection_busy")
    held[name] = lock

    def release():
        if held.get(name) is not lock:
            return
        held.pop(name)
        try:
            lock.release()
        except LockError:
            pass

    try:
        frappe.db.after_commit.add(release)
        frappe.db.after_rollback.add(release)
    except Exception:
        release()
        raise


def get_client(doc, deadline=None):
    return Client(doc.environment, lambda force=False: access_token(doc.name, force), deadline=deadline)


def signed_assertion(doc):
    try:
        pem = base64.b64decode(secret(doc.name, "private_key") or "", validate=True)
    except ValueError:
        raise FeedError("invalid_base64_private_key") from None
    return assertion(doc.client_id, doc.issuer, pem)


def save_tokens(doc, result):
    set_encrypted_password(DOCTYPE, doc.name, result["access_token"], "access_token")
    if result.get("refresh_token"):
        set_encrypted_password(DOCTYPE, doc.name, result["refresh_token"], "refresh_token")
    if not secret(doc.name, "refresh_token"):
        raise FeedError("missing_refresh_token")
    # Preserve secrets through later Document.save() calls, including this instance.
    doc.access_token = doc.refresh_token = "********"
    frappe.db.set_value(
        DOCTYPE,
        doc.name,
        {
            "access_token": "********",
            "refresh_token": "********",
            "token_expires_at": time.time() + int(result["expires_in"]),
            "authorized": 1,
        },
        update_modified=False,
    )
    # Token refresh invalidates the old token remotely. Persist before importing any
    # transaction, so a subsequent failed import cannot roll this credential back.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit


def access_token(name, force=False):
    doc = frappe.get_doc(DOCTYPE, name)
    token = secret(name, "access_token")
    if token and not force and float(doc.token_expires_at or 0) > time.time() + 90:
        return token
    refresh = secret(name, "refresh_token")
    if not refresh:
        raise FeedError("authorization_required")
    result = token_request(doc.environment, signed_assertion(doc), refresh_token=refresh)
    save_tokens(doc, result)
    return result["access_token"]


def exchange(doc, code):
    result = token_request(doc.environment, signed_assertion(doc), code=code)
    save_tokens(doc, result)


def authorization_url(doc):
    host = "business.revolut.com" if doc.environment == "Production" else "sandbox-business.revolut.com"
    return (
        "https://"
        + host
        + "/app-confirm?"
        + urlencode(
            {
                "client_id": doc.client_id,
                "redirect_uri": doc.redirect_uri,
                "response_type": "code",
                "scope": "READ",
            }
        )
    )
