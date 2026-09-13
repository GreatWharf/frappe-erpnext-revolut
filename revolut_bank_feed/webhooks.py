"""Signed v2 webhook inbox. Verify raw bytes before accepting any bank evidence."""

import json
import re

import frappe
from frappe.utils import now_datetime

from .auth import secret
from .core import FeedError, identity, verify_signature
from .sync import enqueue_connection


@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive(key=None, **kwargs):
    frappe.flags.disable_traceback = True
    # No CSRF configuration change: Revolut sends no Frappe session cookie. The
    # endpoint authenticates the body, never the URL routing key alone.
    # Frappe v15 uses JSON alone for form_dict; it does not merge query args.
    # Always get the routing key from the actual URL, never from payload kwargs.
    key = frappe.request.args.get("key")
    if not key or len(key) > 100:
        return _reject(401)
    name = frappe.db.get_value(
        "Revolut Connection", {"webhook_key": key, "enabled": 1, "webhook_enabled": 1}, "name"
    )
    if not name:
        return _reject(401)
    if frappe.request.content_length and frappe.request.content_length > 262144:
        return _reject(413)
    raw = frappe.request.get_data(cache=True)
    if len(raw) > 262144:
        return _reject(413)
    try:
        verify_signature(
            raw,
            frappe.get_request_header("Revolut-Request-Timestamp"),
            frappe.get_request_header("Revolut-Signature"),
            [secret(name, "webhook_secret"), secret(name, "previous_webhook_secret")],
        )
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return _reject(400)
        event = payload.get("event")
        if event not in ("TransactionCreated", "TransactionStateChanged"):
            return {"accepted": True, "ignored": True}
        tx_id = payload.get("data", {}).get("id")
        if not isinstance(tx_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,140}", tx_id):
            return _reject(400)
    except FeedError, ValueError, TypeError, AttributeError:
        return _reject(401)
    name_key = identity(name, raw.hex())
    if not frappe.db.exists("Revolut Webhook Event", name_key):
        doc = frappe.get_doc(
            {
                "doctype": "Revolut Webhook Event",
                "connection": name,
                "company": frappe.db.get_value("Revolut Connection", name, "company"),
                "transaction_id": tx_id,
                "event_type": event,
                "status": "Pending",
                "attempts": 0,
                "next_attempt_at": now_datetime(),
                "received_at": now_datetime(),
            }
        )
        doc.insert(ignore_permissions=True, set_name=name_key, ignore_if_duplicate=True)
    # Inbox commit precedes best-effort queue delivery. Redis/worker failure cannot
    # lose accepted events: the periodic scheduler drains Pending/Retry rows.
    frappe.db.commit()
    try:
        enqueue_connection(name)
    except Exception:
        pass
    return {"accepted": True}


def _reject(status):
    frappe.local.response["http_status_code"] = status
    return {"accepted": False}
