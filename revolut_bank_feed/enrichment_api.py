"""Desk actions for optional evidence and explicit ERPNext links."""

from datetime import datetime, timezone

import frappe
from frappe.utils import cint, now_datetime

from .api import connection_for_user, safe_action
from .auth import connection_lock, get_client
from .core import FeedError, utc
from .enrichment import enqueue, expense_record, receipts
from .enrichment_core import remote_id


@frappe.whitelist(methods=["POST"])
@safe_action
def configure(connection, sync_fx=0, sync_expenses=0, sync_receipts=0, sync_catalogs=0):
    doc = connection_for_user(connection)
    flags = {
        k: int(bool(cint(v)))
        for k, v in dict(
            sync_fx=sync_fx,
            sync_expenses=sync_expenses,
            sync_receipts=sync_receipts,
            sync_catalogs=sync_catalogs,
        ).items()
    }
    if flags["sync_expenses"] and doc.environment != "Production":
        raise FeedError("expenses_not_available_in_sandbox")
    if flags["sync_receipts"] and not flags["sync_expenses"]:
        raise FeedError("enable_expenses_before_receipts")
    with connection_lock(connection):
        frappe.db.set_value("Revolut Connection", connection, flags)
    enqueue(connection)
    return {"queued": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def sync_now(connection):
    doc = connection_for_user(connection)
    if not doc.enabled:
        raise FeedError("enable_connection_first")
    enqueue(connection)
    return {"queued": True}


def evidence(doctype, name):
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    connection = connection_for_user(doc.connection)
    return doc, connection


@frappe.whitelist(methods=["POST"])
@safe_action
def refresh_expense(name):
    doc, connection = evidence("Revolut Expense", name)
    with connection_lock(connection.name):
        client = get_client(connection)
        row = client.get("/expenses/" + remote_id(doc.remote_id))
        if row.get("id") != doc.remote_id:
            raise FeedError("expense_identity_mismatch")
        expense_record(connection, client, row)
        if connection.sync_receipts:
            receipts(connection, client, name, row)
            frappe.db.set_value(
                "Revolut Expense",
                name,
                dict(receipt_pending=0, receipt_error_code=None, receipt_last_checked=now_datetime()),
                update_modified=False,
            )
    return {"refreshed": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def link_expense(name, target_doctype, target_name):
    doc, connection = evidence("Revolut Expense", name)
    if target_doctype not in ("Purchase Invoice", "Expense Claim"):
        raise FeedError("unsupported_expense_document")
    target = frappe.get_doc(target_doctype, target_name)
    target.check_permission("read")
    if target.company != connection.company:
        raise FeedError("expense_company_mismatch")
    if target.docstatus == 2:
        raise FeedError("cannot_link_cancelled_document")
    with connection_lock(connection.name):
        frappe.db.set_value(
            "Revolut Expense",
            name,
            dict(linked_doctype=target_doctype, linked_document=target_name, accounting_review_required=0),
        )
    return {"linked": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def use_quote(name):
    doc, connection = evidence("Revolut FX Quote", name)
    # Currency Exchange has no Company field. A site-wide lock and collision refusal
    # prevent silently replacing another Company's or provider's same-day rate.
    with frappe.cache.lock(
        "revolut-rate:" + frappe.local.site + ":" + doc.from_currency + ":" + doc.to_currency, timeout=60
    ):
        date = utc(doc.rate_date).date()
        if date != datetime.now(timezone.utc).date():
            raise FeedError("only_todays_quote_can_be_published")
        if doc.currency_exchange and frappe.db.exists("Currency Exchange", doc.currency_exchange):
            return {"name": doc.currency_exchange}
        if frappe.db.exists(
            "Currency Exchange", dict(date=date, from_currency=doc.from_currency, to_currency=doc.to_currency)
        ):
            raise FeedError("currency_exchange_already_exists_not_overwritten")
        rate = frappe.get_doc(
            dict(
                doctype="Currency Exchange",
                date=date,
                from_currency=doc.from_currency,
                to_currency=doc.to_currency,
                exchange_rate=doc.exchange_rate,
                for_buying=1,
                for_selling=1,
            )
        ).insert()
        frappe.db.set_value("Revolut FX Quote", name, "currency_exchange", rate.name)
        # Persist the created Currency Exchange before releasing the per-currency-pair
        # lock; a racing request must see it as already created, not attempt a duplicate.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
    return {"name": rate.name}
