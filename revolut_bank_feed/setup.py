"""Browser setup endpoints. No shell execution or app installation capabilities."""

import base64
import json
from urllib.parse import urlparse

import frappe
from cryptography import x509
from frappe.utils import cint, get_url, today
from frappe.utils.password import set_encrypted_password

from .api import connection_for_user, safe_action
from .auth import connection_lock, exchange, get_client, lock_configuration, secret
from .core import FeedError
from .importer import get_maps
from .setup_core import authorization_code, make_certificate
from .sync import enqueue_connection


def public_connection(doc):
    # Explicit allowlist: never serialize a connection document containing secrets.
    fields = (
        "name",
        "connection_name",
        "company",
        "environment",
        "client_id",
        "redirect_uri",
        "public_certificate",
        "certificate_expires_on",
        "authorized",
        "enabled",
        "historical_from",
        "last_status",
        "last_error_code",
        "last_success_at",
        "poll_cursor",
        "backfill_next",
        "sync_fx",
        "sync_expenses",
        "sync_receipts",
        "sync_catalogs",
        "extras_last_status",
        "extras_error_code",
        "last_extras_at",
    )
    result = {field: doc.get(field) for field in fields}
    result["has_private_key"] = bool(secret(doc.name, "private_key"))
    return result


@frappe.whitelist()
@safe_action
def overview(connection=None):
    frappe.only_for("System Manager")
    choices = frappe.get_list(
        "Revolut Connection",
        fields=["name", "connection_name", "company", "enabled"],
        order_by="creation desc",
        limit_page_length=200,
    )
    result = {
        "connections": choices,
        "companies": frappe.get_list("Company", pluck="name", limit_page_length=200),
    }
    if connection:
        doc = connection_for_user(connection)
        result["connection"] = public_connection(doc)
        result["maps"] = frappe.get_list(
            "Revolut Account Map",
            filters={"connection": connection},
            fields=["name", "account_id", "currency", "bank_account", "enabled", "fee_policy"],
            limit_page_length=1000,
        )
        result["reviews"] = frappe.db.count(
            "Revolut Source Transaction", {"connection": connection, "needs_review": 1}
        )
        result["scheduler_enabled"] = not bool(
            frappe.conf.pause_scheduler
            or frappe.conf.disable_scheduler
            or not cint(frappe.db.get_single_value("System Settings", "enable_scheduler"))
        )
    return result


@frappe.whitelist(methods=["POST"])
@safe_action
def create_connection(company, environment="Sandbox", historical_from=None):
    frappe.only_for("System Manager")
    frappe.get_doc("Company", company).check_permission("read")
    redirect_uri = get_url("/revolut-authorized")
    if urlparse(redirect_uri).scheme != "https":
        raise FeedError("set_https_host_name_before_setup")
    doc = frappe.get_doc(
        {
            "doctype": "Revolut Connection",
            "connection_name": company + " · " + environment,
            "company": company,
            "environment": environment,
            "client_id": "pending-setup",
            "redirect_uri": redirect_uri,
            "issuer": urlparse(redirect_uri).hostname,
            "historical_from": historical_from or today(),
            "lookback_days": 7,
            "window_days": 7,
            "audit_window_days": 30,
            "audit_enabled": 1,
            "poll_overlap_minutes": 60,
            "enabled": 0,
        }
    )
    doc.insert()
    return public_connection(doc)


@frappe.whitelist(methods=["POST"])
@safe_action
def generate_certificate(connection, recover_missing_key=False):
    connection_for_user(connection)
    with connection_lock(connection):
        doc = frappe.get_doc("Revolut Connection", connection)
        recover = bool(cint(recover_missing_key))
        has_credentials = any(
            secret(doc.name, field) for field in ("private_key", "access_token", "refresh_token")
        )
        if doc.enabled or doc.authorized or has_credentials or (doc.public_certificate and not recover):
            raise FeedError("certificate_already_configured_use_advanced_settings_to_rotate")
        private_pem, certificate_pem = make_certificate(doc.issuer)
        cert = x509.load_pem_x509_certificate(certificate_pem)
        # Only the public certificate is sent back. No File attachment, no private key download.
        set_encrypted_password(doc.doctype, doc.name, base64.b64encode(private_pem).decode(), "private_key")
        frappe.db.set_value(
            doc.doctype,
            doc.name,
            {
                # Frappe deletes encrypted secrets on save when their Password field is blank.
                "private_key": "********",
                "client_id": "pending-setup",
                "public_certificate": certificate_pem.decode(),
                "certificate_expires_on": cert.not_valid_after_utc.date(),
            },
            update_modified=False,
        )
        frappe.db.commit()
    return {
        "public_certificate": certificate_pem.decode(),
        "expires_on": str(cert.not_valid_after_utc.date()),
    }


@frappe.whitelist(methods=["POST"])
@safe_action
def save_client_id(connection, client_id):
    connection_for_user(connection)
    if not client_id or len(client_id.strip()) > 140 or client_id == "pending-setup":
        raise FeedError("enter_client_id_from_revolut")
    with connection_lock(connection):
        doc = frappe.get_doc("Revolut Connection", connection)
        if doc.enabled or doc.authorized:
            raise FeedError("use_advanced_settings_to_change_authorized_client")
        doc.client_id = client_id.strip()
        frappe.flags.revolut_configuration_locked = True
        try:
            doc.save()
        finally:
            frappe.flags.revolut_configuration_locked = False
        frappe.db.commit()
    return {"saved": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def connect_from_paste(connection, pasted_value):
    doc = connection_for_user(connection)
    if doc.client_id == "pending-setup":
        raise FeedError("save_revolut_client_id_first")
    code = authorization_code(pasted_value, doc.redirect_uri)
    with connection_lock(connection):
        exchange(doc, code)
    return {"authorized": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def account_options(connection):
    doc = connection_for_user(connection)
    with connection_lock(connection):
        accounts = get_client(doc).get("/accounts")
    if not isinstance(accounts, list):
        raise FeedError("invalid_accounts_response")
    banks = []
    for bank in frappe.get_list(
        "Bank Account",
        filters={"company": doc.company, "is_company_account": 1, "disabled": 0},
        fields=["name", "account"],
        limit_page_length=1000,
    ):
        currency = frappe.db.get_value("Account", bank.account, "account_currency")
        banks.append({"name": bank.name, "currency": currency})
    return {
        "accounts": [
            {
                k: a.get(k)
                for k in ("id", "name", "currency", "state", "balance", "type", "created_at", "updated_at")
            }
            for a in accounts
        ],
        "bank_accounts": banks,
    }


@frappe.whitelist(methods=["POST"])
@safe_action
def create_bank_account(connection, ledger, account_name):
    doc = connection_for_user(connection)
    if doc.enabled:
        raise FeedError("pause_connection_before_mapping")
    account = frappe.get_doc("Account", ledger)
    account.check_permission("read")
    if (
        account.company != doc.company
        or account.is_group
        or account.disabled
        or account.account_type != "Bank"
    ):
        raise FeedError("choose_active_bank_ledger_for_company")
    if not account_name or len(account_name) > 100:
        raise FeedError("bank_account_name_required_max_100")
    bank_name = frappe.db.get_value("Bank", {"bank_name": "Revolut"}, "name")
    if not bank_name:
        bank_name = frappe.get_doc({"doctype": "Bank", "bank_name": "Revolut"}).insert().name
    bank = frappe.get_doc(
        {
            "doctype": "Bank Account",
            "account_name": account_name,
            "bank": bank_name,
            "account": ledger,
            "company": doc.company,
            "is_company_account": 1,
        }
    ).insert()
    return {"name": bank.name, "currency": account.account_currency}


@frappe.whitelist(methods=["POST"])
@safe_action
def save_mappings(connection, selections, timezone="UTC", skipped_accounts=None):
    doc = connection_for_user(connection)
    if doc.enabled:
        raise FeedError("pause_connection_before_mapping")
    selections = frappe.parse_json(selections) if isinstance(selections, str) else selections
    skipped_accounts = (
        frappe.parse_json(skipped_accounts) if isinstance(skipped_accounts, str) else skipped_accounts
    )
    skipped_accounts = [] if skipped_accounts is None else skipped_accounts
    if (
        not isinstance(selections, list)
        or not isinstance(skipped_accounts, list)
        or not 0 < len(selections) + len(skipped_accounts) <= 500
    ):
        raise FeedError("choose_bank_accounts_first")
    # Verify both selected and deliberately skipped identities; newly discovered or
    # mistyped accounts must never become silent exclusions in the importer.
    with connection_lock(connection):
        accounts = get_client(doc).get("/accounts")
    if not isinstance(accounts, list):
        raise FeedError("invalid_accounts_response")
    # Token refresh may commit during discovery. Acquire the transaction-scoped
    # configuration lock only afterwards, and hold it through the final request commit.
    lock_configuration(connection)
    doc = frappe.get_doc("Revolut Connection", connection)
    if doc.enabled:
        raise FeedError("pause_connection_before_mapping")
    known = {(a["id"], a["currency"]) for a in accounts}
    seen, existing_maps = set(), {}
    for row in selections + skipped_accounts:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(key), str) for key in ("account_id", "currency")
        ):
            raise FeedError("invalid_or_duplicate_account_selection")
        pair = (row["account_id"], row["currency"])
        if pair not in known or pair in seen:
            raise FeedError("invalid_or_duplicate_account_selection")
        seen.add(pair)
        existing_maps[pair] = frappe.db.get_value(
            "Revolut Account Map",
            {"connection": connection, "account_id": pair[0], "currency": pair[1]},
            ["name", "bank_account"],
            as_dict=True,
        )
    skipped = {
        (row["account_id"], row["currency"]) for row in json.loads(doc.get("skipped_accounts") or "[]")
    }
    for row in skipped_accounts:
        pair = (row["account_id"], row["currency"])
        if existing_maps[pair]:
            raise FeedError("existing_mapping_cannot_be_skipped_use_advanced_settings")
        skipped.add(pair)
    for row in selections:
        pair = (row["account_id"], row["currency"])
        existing = existing_maps[pair]
        if existing and existing.bank_account != row.get("bank_account"):
            raise FeedError("existing_mapping_is_immutable_use_advanced_settings")
        if not existing:
            frappe.get_doc(
                {
                    "doctype": "Revolut Account Map",
                    "connection": connection,
                    "account_id": pair[0],
                    "currency": pair[1],
                    "bank_account": row.get("bank_account"),
                    "timezone": timezone,
                    "fee_policy": "Review",
                    "enabled": 1,
                }
            ).insert()
        skipped.discard(pair)
    # Keep older exclusions (including closed accounts) until explicitly mapped.
    frappe.db.set_value(
        "Revolut Connection",
        connection,
        "skipped_accounts",
        json.dumps([{"account_id": account, "currency": currency} for account, currency in sorted(skipped)]),
    )
    return {"saved": len(selections)}


@frappe.whitelist(methods=["POST"])
@safe_action
def activate(connection):
    connection_for_user(connection)
    # Endpoint changes enabled state only. Configuration remains untouched.
    with connection_lock(connection):
        doc = frappe.get_doc("Revolut Connection", connection)
        if not doc.authorized or not any(row.enabled for row in get_maps(doc).values()):
            raise FeedError("finish_authorization_and_account_mapping_first")
        frappe.db.set_value(doc.doctype, doc.name, "enabled", 1)
        frappe.db.commit()
    enqueue_connection(connection)
    return {"queued": True}


@frappe.whitelist(methods=["POST"])
@safe_action
def pause(connection):
    doc = connection_for_user(connection)
    with connection_lock(connection):
        frappe.db.set_value(doc.doctype, doc.name, "enabled", 0)
        frappe.db.commit()
    return {"paused": True}
