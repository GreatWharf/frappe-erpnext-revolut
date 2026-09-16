"""Atomic source-to-Bank-Transaction persistence. The caller commits per transaction."""

from __future__ import annotations

import json
from decimal import Decimal

import frappe
from frappe.utils import now_datetime

from .core import FeedError, compact_transaction, identity, normalize, utc, validate_mapping
from .guards import feed_write

SOURCE = "Revolut Source Transaction"
LEG = "Revolut Source Leg"


def encode(data):
    return json.dumps(data, default=str, sort_keys=True, separators=(",", ":"))


def financial_fingerprint(row):
    def canonical(value):
        # Fixed-point form and insignificant-zero removal preserve exact Decimal
        # value without applying a context precision or rounding.
        result = format(value, "f")
        return result.rstrip("0").rstrip(".") if "." in result else result

    return identity(
        *(str(row[key]) for key in ("bank_account", "company", "currency", "date")),
        canonical(row["deposit"]),
        canonical(row["withdrawal"]),
    )


def bank_matches(bank, row):
    return (
        bank.docstatus == 1
        and str(bank.date) == row["date"]
        and bank.bank_account == row["bank_account"]
        and bank.company == row["company"]
        and bank.currency == row["currency"]
        and Decimal(str(bank.deposit or 0)) == row["deposit"]
        and Decimal(str(bank.withdrawal or 0)) == row["withdrawal"]
    )


def get_maps(connection, *, for_update=False):
    result = {}
    filters = {"connection": connection.name}
    # Activation needs current reads; v15 get_all does not accept for_update.
    rows = (
        frappe.db.get_values("Revolut Account Map", filters, "*", as_dict=True, for_update=True)
        if for_update
        else frappe.get_all("Revolut Account Map", filters=filters, fields=["*"])
    )
    read_options = {"for_update": True} if for_update else {}
    for row in rows:
        if row.enabled:
            bank = frappe.get_doc("Bank Account", row.bank_account, **read_options)
            ledger = frappe.get_doc("Account", bank.account, **read_options)
            validate_mapping(connection.company, row, bank.as_dict(), ledger.as_dict())
        result[(row.account_id, row.currency)] = row
    return result


def mark_review(source, reason):
    source.needs_review = 1
    source.review_reason = reason
    for leg in frappe.get_all(
        LEG, filters={"source_transaction": source.name, "active": 1}, fields=["bank_transaction"]
    ):
        if leg.bank_transaction:
            frappe.db.set_value(
                "Bank Transaction",
                leg.bank_transaction,
                "custom_revolut_review_required",
                1,
                update_modified=False,
            )
    source.save(ignore_permissions=True)


def ingest(connection, transaction, maps=None, apply_review=False, review_note=None):
    if not isinstance(transaction, dict) or not transaction.get("id"):
        raise FeedError("invalid_transaction_response")
    tx = compact_transaction(transaction)
    upstream_time = utc(tx.get("updated_at"))
    source_name = identity(connection.name, tx["id"])
    exists = frappe.db.exists(SOURCE, source_name)
    source = (
        frappe.get_doc(SOURCE, source_name)
        if exists
        else frappe.get_doc(
            {
                "doctype": SOURCE,
                "name": source_name,
                "connection": connection.name,
                "company": connection.company,
                "transaction_id": tx["id"],
            }
        )
    )
    if exists and source.updated_at and upstream_time < utc(source.updated_at):
        return {"created": 0, "review": int(source.needs_review or 0)}
    payload = encode(tx)
    if exists and source.payload_hash != identity(payload):
        # Preserve the old evidence as a separate access-controlled immutable revision.
        frappe.get_doc(
            {
                "doctype": "Revolut Source Revision",
                "source_transaction": source.name,
                "company": source.company,
                "upstream_updated_at": source.updated_at,
                "payload": source.payload,
            }
        ).insert(ignore_permissions=True)
    source.update(
        {
            "upstream_state": tx["state"],
            "created_at": tx.get("created_at"),
            "updated_at": tx["updated_at"],
            "last_checked": now_datetime(),
            "payload": payload,
            "payload_hash": identity(payload),
        }
    )
    if not exists:
        source.insert(ignore_permissions=True, set_name=source_name)
    maps = maps if maps is not None else get_maps(connection)
    target = {}
    try:
        if tx["state"] == "completed":
            if not tx.get("legs"):
                raise FeedError("completed_transaction_without_legs")
            # Only deliberate, discovery-verified exclusions may bypass mapping.
            # Keep every leg in the source payload; new/unknown accounts still need review.
            skipped = {
                (row["account_id"], row["currency"])
                for row in json.loads(connection.get("skipped_accounts") or "[]")
            }
            for leg in tx["legs"]:
                pair = (leg.get("account_id"), leg.get("currency"))
                if pair not in maps and pair not in skipped:
                    raise FeedError("unmapped_account_or_currency")
            for mapping in maps.values():
                if not mapping.enabled:
                    continue
                for row in normalize(tx, mapping):
                    key = identity(
                        connection.environment, row["account_id"], row["currency"], tx["id"], row["leg_id"]
                    )
                    row["account_map"] = mapping.name
                    target[key] = row
        else:
            # Validate known states without requiring legs for rejected transactions.
            normalize(tx, {"account_id": ""})
    except FeedError as exc:
        mark_review(source, str(exc))
        return {"created": 0, "review": 1}

    previous = {
        leg.name: leg
        for leg in frappe.get_all(LEG, filters={"source_transaction": source.name}, fields=["*"])
    }
    paused_maps = {mapping.name for mapping in maps.values() if not mapping.enabled}
    paused_review = any(
        leg.active
        and leg.account_map in paused_maps
        and frappe.get_doc("Bank Transaction", leg.bank_transaction).get("custom_revolut_review_required")
        for leg in previous.values()
    )
    conflicts = []
    for key, leg in previous.items():
        if not leg.active or leg.account_map in paused_maps:
            continue
        desired = target.get(key)
        bank = frappe.get_doc("Bank Transaction", leg.bank_transaction)
        if (
            desired is None
            or leg.fingerprint != financial_fingerprint(desired)
            or not bank_matches(bank, desired)
        ):
            conflicts.append(leg)
    if conflicts and not apply_review:
        mark_review(source, "upstream_financial_or_state_change")
        return {"created": 0, "review": 1}
    if conflicts:
        if not review_note or not review_note.strip():
            raise FeedError("review_note_required")
        # Lock all active Bank Transactions before checking reconciliation. Removing
        # links is an explicit accounting operation outside this importer.
        for leg in sorted(conflicts, key=lambda row: row.bank_transaction):
            frappe.db.sql(
                "SELECT name FROM `tabBank Transaction` WHERE name=%s FOR UPDATE", leg.bank_transaction
            )
            bank = frappe.get_doc("Bank Transaction", leg.bank_transaction)
            if bank.payment_entries or Decimal(str(bank.allocated_amount or 0)) != 0:
                raise FeedError("remove_reconciliation_links_before_review")
            if bank.docstatus == 1:
                with feed_write():
                    bank.flags.ignore_permissions = True
                    bank.cancel()
                bank.add_comment(
                    "Info", "Cancelled after explicit Revolut source review; see source audit note."
                )
            elif bank.docstatus != 2:
                raise FeedError("unexpected_bank_document_state")
            frappe.db.set_value(LEG, leg.name, "active", 0, update_modified=False)
            previous[leg.name].active = 0

    created = 0
    for key, row in target.items():
        existing = previous.get(key)
        if existing and existing.active:
            frappe.db.set_value(
                "Bank Transaction",
                existing.bank_transaction,
                {
                    "custom_revolut_review_required": 0,
                    "custom_revolut_fee": str(row["fee"]),
                    **bill_metadata(row),
                },
                update_modified=False,
            )
            frappe.db.set_value(LEG, key, "reported_fee", str(row["fee"]), update_modified=False)
            continue
        revision = (existing.revision if existing else 0) + 1
        entry_key = identity(key, revision)
        if frappe.db.exists("Bank Transaction", {"custom_revolut_entry_key": entry_key}):
            # This indicates deleted source history/restored partial backup. Never guess
            # whether an existing bank row is safe to adopt.
            raise FeedError("existing_bank_provenance_requires_recovery")
        bank_data = {
            key_: value
            for key_, value in row.items()
            if key_
            not in (
                "leg_id",
                "account_id",
                "fee",
                "account_map",
                "bill_amount",
                "bill_currency",
                "effective_bill_rate",
            )
        }
        # Early v15 uses Data (140 chars); newer schemas use Small Text. Clip only
        # the display reference, never provenance or the full source audit payload.
        reference_field = frappe.get_meta("Bank Transaction").get_field("reference_number")
        if reference_field and reference_field.fieldtype == "Data":
            bank_data["reference_number"] = bank_data["reference_number"][
                : int(reference_field.length or 140)
            ]
        bank_data.update(
            doctype="Bank Transaction",
            naming_series="ACC-BTN-.YYYY.-",
            custom_revolut_source_key=key,
            custom_revolut_entry_key=entry_key,
            custom_revolut_review_required=0,
            custom_revolut_fee=str(row["fee"]),
            **bill_metadata(row),
        )
        with feed_write():
            bank = frappe.get_doc(bank_data)
            bank.flags.ignore_permissions = True
            bank.insert(ignore_permissions=True)
            bank.submit()
            if not bank_matches(bank, row):
                raise FeedError("bank_amount_precision_or_schema_mismatch")
        record = frappe.get_doc(LEG, key) if existing else frappe.get_doc({"doctype": LEG, "name": key})
        record.update(
            {
                "source_transaction": source.name,
                "company": connection.company,
                "account_map": row["account_map"],
                "transaction_id": tx["id"],
                "leg_id": row["leg_id"],
                "currency": row["currency"],
                "bank_transaction": bank.name,
                "fingerprint": financial_fingerprint(row),
                "revision": revision,
                "active": 1,
                "reported_fee": str(row["fee"]),
            }
        )
        record.save(ignore_permissions=True) if existing else record.insert(
            ignore_permissions=True, set_name=key
        )
        created += 1
    source.needs_review = int(paused_review)
    source.review_reason = "paused_map_has_unresolved_review" if paused_review else None
    if apply_review:
        source.reviewed_by = frappe.session.user
        source.reviewed_at = now_datetime()
        source.review_note = review_note
        source.add_comment(
            "Info", "Reviewed by " + frappe.session.user + ": " + frappe.utils.escape_html(review_note)
        )
    source.save(ignore_permissions=True)
    return {"created": created, "review": int(paused_review)}


def bill_metadata(row):
    return {
        "custom_revolut_" + key: str(row[key]) if row.get(key) is not None else None
        for key in ("bill_amount", "bill_currency", "effective_bill_rate")
    }
