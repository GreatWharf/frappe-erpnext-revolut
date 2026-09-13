"""Desk actions: authenticated, role-gated, document-permission checked."""

import base64
from datetime import datetime, timedelta, timezone
from functools import wraps

import frappe
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from frappe.utils import getdate

from .auth import authorization_url, connection_lock, exchange, get_client
from .core import FeedError, iso, utc
from .importer import ingest
from .sync import _fetch_one, enqueue_connection, safe_error


def safe_action(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        frappe.flags.disable_traceback = True
        try:
            return fn(*args, **kwargs)
        except frappe.PermissionError, frappe.DoesNotExistError:
            raise
        except Exception as exc:
            frappe.db.rollback()
            frappe.throw(safe_error(exc))

    return wrapper


def connection_for_user(name):
    frappe.only_for("System Manager")
    doc = frappe.get_doc("Revolut Connection", name)
    doc.check_permission("write")
    return doc


@frappe.whitelist()
@safe_action
def get_authorization_url(connection):
    doc = connection_for_user(connection)
    return authorization_url(doc)


@frappe.whitelist(methods=["POST"])
@safe_action
def set_private_key(connection, encoded_key):
    connection_for_user(connection)
    if not encoded_key or len(encoded_key) > 32768:
        raise FeedError("invalid_key_size")
    pem = base64.b64decode(encoded_key, validate=True)
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, RSAPrivateKey) or key.key_size < 2048:
        raise FeedError("rsa_key_at_least_2048_bits_required")
    with connection_lock(connection):
        doc = frappe.get_doc("Revolut Connection", connection)
        if doc.enabled:
            raise FeedError("disable_connection_before_key_change")
        doc.private_key = encoded_key
        frappe.flags.revolut_configuration_locked = True
        try:
            doc.save()
        finally:
            frappe.flags.revolut_configuration_locked = False
    return {"saved": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def exchange_code(connection, code):
    doc = connection_for_user(connection)
    if not code or len(code) > 2048:
        raise FeedError("invalid_authorization_code")
    with connection_lock(connection):
        exchange(doc, code.strip())
    return {"authorized": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def discover_accounts(connection):
    doc = connection_for_user(connection)
    with connection_lock(connection):
        rows = get_client(doc).get("/accounts")
    if not isinstance(rows, list):
        raise FeedError("invalid_accounts_response")
    return [{key: row.get(key) for key in ("id", "name", "currency", "state")} for row in rows]


@frappe.whitelist(methods=["POST"])
@safe_action
def sync_now(connection):
    doc = connection_for_user(connection)
    if not doc.enabled:
        raise FeedError("enable_connection_first")
    enqueue_connection(doc.name)
    return {"queued": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def start_backfill(connection, from_date, through_date):
    connection_for_user(connection)
    start = utc(getdate(from_date))
    end = utc(getdate(through_date)) + timedelta(days=1)
    end = min(end, datetime.now(timezone.utc))
    if start >= end:
        raise FeedError("invalid_backfill_range")
    with connection_lock(connection):
        doc = frappe.get_doc("Revolut Connection", connection)
        if not doc.enabled:
            raise FeedError("enable_connection_first")
        if doc.backfill_next:
            raise FeedError("backfill_already_active")
        if start < utc(doc.historical_from):
            raise FeedError("move_historical_from_earlier_before_backfill")
        frappe.db.set_value(
            doc.doctype,
            doc.name,
            {"backfill_next": iso(start), "backfill_end": iso(end)},
            update_modified=False,
        )
        enqueue_connection(doc.name)
    return {"queued": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def review_and_apply(source_transaction, note):
    frappe.only_for("System Manager")
    source = frappe.get_doc("Revolut Source Transaction", source_transaction)
    source.check_permission("read")
    doc = connection_for_user(source.connection)
    if not note or not note.strip() or len(note) > 2000:
        raise FeedError("review_note_required_max_2000")
    with connection_lock(doc.name):
        # Never apply stale webhook data or an old cached payload after a human review.
        tx = _fetch_one(get_client(doc), source.transaction_id)
        frappe.db.savepoint("review_apply")
        try:
            result = ingest(doc, tx, apply_review=True, review_note=note.strip())
        except Exception:
            frappe.db.rollback(save_point="review_apply")
            raise
    return result
