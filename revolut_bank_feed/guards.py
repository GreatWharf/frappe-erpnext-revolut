"""Protect source identity and reconciliation while an upstream change is unresolved."""

from contextlib import contextmanager

import frappe


@contextmanager
def feed_write():
    old = frappe.flags.revolut_feed_write
    frappe.flags.revolut_feed_write = True
    try:
        yield
    finally:
        frappe.flags.revolut_feed_write = old


def validate_bank_transaction(doc, method=None):
    if frappe.flags.revolut_feed_write:
        return
    old = doc.get_doc_before_save()
    source = doc.get("custom_revolut_source_key") or (old and old.get("custom_revolut_source_key"))
    if not source:
        return
    if not old:
        frappe.throw("Revolut source fields can only be created by the bank feed.")
    immutable = (
        "custom_revolut_source_key",
        "custom_revolut_entry_key",
        "custom_revolut_review_required",
        "custom_revolut_fee",
        "deposit",
        "withdrawal",
        "date",
        "bank_account",
        "company",
        "currency",
        "transaction_id",
        "transaction_type",
    )
    if any(doc.get(key) != old.get(key) for key in immutable):
        frappe.throw(
            "Imported Revolut amounts and source fields are immutable. Use Source Transaction review."
        )
    # Allow removing existing links to prepare for review, but forbid adding or
    # increasing allocations while bank evidence is in conflict.
    if old.get("custom_revolut_review_required"):
        prior = {(r.payment_document, r.payment_entry): r.allocated_amount for r in old.payment_entries}
        for row in doc.payment_entries:
            key = (row.payment_document, row.payment_entry)
            if key not in prior or row.allocated_amount > prior[key]:
                frappe.throw("This Revolut transaction requires review before reconciliation.")


def before_cancel(doc, method=None):
    if doc.get("custom_revolut_source_key") and not frappe.flags.revolut_feed_write:
        frappe.throw("Use Review and Apply on the Revolut Source Transaction to cancel an imported row.")


def before_delete(doc, method=None):
    if doc.get("custom_revolut_source_key"):
        frappe.throw("Keep imported Revolut Bank Transactions for audit and duplicate prevention.")
