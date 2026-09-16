"""Optional accounting evidence import. Serialized per connection, bounded and resumable."""

import json
import time
from datetime import datetime, timedelta, timezone

import frappe
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file

from .auth import connection_lock, get_client
from .core import FeedError, identity, iso, money, utc
from .enrichment_core import compact_expense, iter_expenses, quote_values, receipt_extension, remote_id
from .sync import safe_error

CONNECTION = "Revolut Connection"


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def upsert(doctype, connection, remote, data, **values):
    key = identity(connection.name, doctype, remote)
    content = dict(values, data=encoded(data))
    fingerprint = identity(encoded(content))
    old = frappe.db.get_value(doctype, key, "fingerprint")
    if old:
        if old != fingerprint:
            if doctype == "Revolut Expense" and frappe.db.get_value(doctype, key, "linked_document"):
                content["accounting_review_required"] = 1
            frappe.db.set_value(doctype, key, dict(content, fingerprint=fingerprint))
        frappe.db.set_value(doctype, key, "last_seen_at", now_datetime(), update_modified=False)
    else:
        frappe.get_doc(
            dict(
                doctype=doctype,
                record_key=key,
                connection=connection.name,
                company=connection.company,
                remote_id=remote,
                fingerprint=fingerprint,
                last_seen_at=now_datetime(),
                **content,
            )
        ).insert(ignore_permissions=True)
    return key


def account_snapshots(connection, accounts):
    for row in accounts:
        rid = remote_id(row["id"])
        data = {
            k: row[k]
            for k in (
                "id",
                "name",
                "currency",
                "balance",
                "state",
                "type",
                "public",
                "created_at",
                "updated_at",
            )
            if k in row
        }
        bank = frappe.db.get_value(
            "Revolut Account Map",
            {"connection": connection.name, "account_id": rid, "currency": row["currency"]},
            "bank_account",
        )
        upsert(
            "Revolut Account Snapshot",
            connection,
            rid,
            data,
            display_name=row.get("name") or row["currency"],
            currency=row["currency"],
            balance=money(row.get("balance", 0)),
            upstream_state=row.get("state"),
            bank_account=bank,
        )
    # Accounts absent from a complete list remain as evidence, explicitly marked missing.
    present = {row["id"] for row in accounts}
    for old in frappe.get_all(
        "Revolut Account Snapshot", filters={"connection": connection.name}, fields=["name", "remote_id"]
    ):
        if old.remote_id not in present:
            frappe.db.set_value(
                "Revolut Account Snapshot",
                old.name,
                {"upstream_state": "missing_from_latest_list", "fingerprint": "missing"},
            )
    # Commit account snapshot evidence now, while still under the connection lock;
    # later phases in this run must see committed account state, not a half-written batch.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit


def due(value, hours=24):
    return not value or utc(value) <= utc(now_datetime()) - timedelta(hours=hours)


def rates(connection, client, accounts):
    if not connection.sync_fx or not due(connection.last_fx_at):
        return
    base = frappe.db.get_value("Company", connection.company, "default_currency")
    currencies = sorted({row["currency"] for row in accounts if row.get("state") == "active"} - {base})
    if len(currencies) > 100:
        raise FeedError("too_many_quote_currencies")
    for currency in currencies:
        data = client.get("/rate", {"from": currency, "to": base, "amount": 1})
        values = quote_values(data, currency, base)
        # One record per direction per UTC quote date; retain quotes from earlier days.
        remote = currency + "-" + base + "-" + str(values["rate_date"].date())
        upsert(
            "Revolut FX Quote",
            connection,
            remote,
            data,
            display_name=currency + " → " + base,
            upstream_state="Indicative sell quote",
            **values,
        )
        # Commit each FX quote as fetched; a crash partway through many currencies
        # must not lose quotes already retrieved.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
    frappe.db.set_value(CONNECTION, connection.name, "last_fx_at", now_datetime(), update_modified=False)
    # Persist last_fx_at only after every quote committed, so a retry cannot mistake
    # a partial run for a completed FX refresh.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit


def receipts(connection, client, expense_name, row):
    if not connection.sync_receipts:
        return
    rid = remote_id(row["id"])
    stored = json.loads(frappe.db.get_value("Revolut Expense", expense_name, "receipt_files") or "{}")
    receipt_ids = row.get("receipt_ids", [])
    if len(receipt_ids) > 100:
        raise FeedError("too_many_expense_receipts")
    errors = []
    for receipt in receipt_ids:
        try:
            receipt = remote_id(receipt)
            if receipt in stored and frappe.db.exists("File", stored[receipt]):
                continue
            data = client.get("/expenses/" + rid + "/receipts/" + receipt + "/content", binary=True)
            extension = receipt_extension(data)
            filename = "revolut-" + identity(connection.name, rid, receipt) + extension
            existing = frappe.db.get_value(
                "File",
                dict(
                    attached_to_doctype="Revolut Expense",
                    attached_to_name=expense_name,
                    file_name=filename,
                    is_private=1,
                ),
                "name",
            )
            file = existing or save_file(filename, data, "Revolut Expense", expense_name, is_private=1).name
            stored[receipt] = file
            frappe.db.set_value(
                "Revolut Expense", expense_name, "receipt_files", encoded(stored), update_modified=False
            )
            # Commit this receipt immediately: siblings are fetched one at a time and
            # this file's record must survive even if a later receipt in the loop fails.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        except Exception as exc:
            frappe.db.rollback()
            errors.append(safe_error(exc))
            # Earlier siblings were committed individually. Reload state after any
            # rollback so a failed File insert cannot masquerade as a saved receipt.
            stored = json.loads(frappe.db.get_value("Revolut Expense", expense_name, "receipt_files") or "{}")
    if errors:
        raise FeedError(";".join(dict.fromkeys(errors))[:140])
    # Removed receipt IDs stay archived locally, but are no longer in the upstream data's current list.


def expense_record(connection, client, row):
    data = compact_expense(row)
    remote_id(data["id"])
    source = (
        frappe.db.get_value(
            "Revolut Source Transaction",
            {"connection": connection.name, "transaction_id": data.get("transaction_id")},
            "name",
        )
        if data.get("transaction_id")
        else None
    )
    name = upsert(
        "Revolut Expense",
        connection,
        data["id"],
        data,
        display_name=(data.get("merchant") or data.get("description") or data["id"])[:140],
        upstream_state=data["state"],
        expense_date=utc(data["expense_date"]).replace(tzinfo=None),
        amount=money(data["spent_amount"]["amount"]),
        currency=data["spent_amount"]["currency"],
        merchant=data.get("merchant"),
        payer=data.get("payer"),
        transaction_type=data.get("transaction_type"),
        transaction_id=data.get("transaction_id"),
        source_transaction=source,
        description=data.get("description"),
    )
    # Commit the expense record before computing receipt_pending; enrichment runs
    # process many expenses per call and must not lose ones already saved if a
    # later row in the caller's loop fails.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit
    stored = json.loads(frappe.db.get_value("Revolut Expense", name, "receipt_files") or "{}")
    pending = any(
        receipt not in stored or not frappe.db.exists("File", stored[receipt])
        for receipt in data.get("receipt_ids", [])
    )
    frappe.db.set_value("Revolut Expense", name, "receipt_pending", int(pending), update_modified=False)
    # Commit the receipt_pending flag as its own durable step so a resumed run can
    # find and retry pending receipts even though the expense record already landed.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit
    return name


def receipt_batch(connection, client):
    if not connection.sync_receipts:
        return
    errors = []
    for row in frappe.get_all(
        "Revolut Expense",
        filters={"connection": connection.name, "receipt_pending": 1},
        fields=["name", "data"],
        order_by="receipt_last_checked asc",
        limit_page_length=20,
    ):
        try:
            receipts(connection, client, row.name, json.loads(row.data))
            frappe.db.set_value(
                "Revolut Expense",
                row.name,
                dict(receipt_pending=0, receipt_error_code=None, receipt_last_checked=now_datetime()),
                update_modified=False,
            )
        except Exception as exc:
            frappe.db.rollback()
            code = safe_error(exc)
            errors.append(code)
            frappe.db.set_value(
                "Revolut Expense",
                row.name,
                dict(receipt_error_code=code, receipt_last_checked=now_datetime()),
                update_modified=False,
            )
        # Commit this expense's receipt outcome (success or recorded error) before
        # the next one; the batch is bounded to 20 rows and must make durable
        # progress on each so a crash never redoes or loses a completed row.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
    if errors:
        raise FeedError("receipt_retry_required")


def expense_window(connection, client, start, end, prefix):
    keys = [prefix + "_window_start", prefix + "_window_end", prefix + "_window_to"]
    state = frappe.db.get_value(CONNECTION, connection.name, keys, as_dict=True)
    if state.get(keys[0]):
        start, end, page_to = (utc(state[k]) for k in keys)
    else:
        page_to = end
        frappe.db.set_value(
            CONNECTION,
            connection.name,
            dict(zip(keys, [iso(value) for value in (start, end, end)])),
            update_modified=False,
        )
        # Freeze and persist the window boundaries before fetching any page; a
        # retry must resume this exact window, never silently pick a new one.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def checkpoint(value):
        frappe.db.set_value(CONNECTION, connection.name, keys[2], iso(value), update_modified=False)
        # Advance and commit the page checkpoint immediately so a crash mid-window
        # resumes at the last committed page, not the window start.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    for row in iter_expenses(
        lambda params: client.get("/expenses", params), start, page_to, checkpoint=checkpoint
    ):
        expense_record(connection, client, row)
    frappe.db.set_value(CONNECTION, connection.name, dict.fromkeys(keys), update_modified=False)
    return end


def expenses(connection, client):
    if not connection.sync_expenses:
        return
    if connection.environment != "Production":
        raise FeedError("expenses_not_available_in_sandbox")
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=5)
    earliest = utc(connection.historical_from)
    cursor = utc(connection.expense_cursor) if connection.expense_cursor else earliest
    start = max(earliest, cursor - timedelta(hours=1))
    end = min(cursor + timedelta(days=7), cutoff)
    if start < end:
        end = expense_window(connection, client, start, end, "expense")
        frappe.db.set_value(CONNECTION, connection.name, "expense_cursor", iso(end), update_modified=False)
        # Advance the expense cursor only after the window fully committed; a crash
        # before this commit simply re-runs the window (idempotent), never skips it.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
    if due(connection.last_expense_audit_at):
        # Rotate 30 days per day to discover old edits/receipts, including terminal expenses.
        start = utc(connection.expense_audit_cursor) if connection.expense_audit_cursor else earliest
        if start >= cutoff:
            start = earliest
        end = min(start + timedelta(days=30), cutoff)
        if start < end:
            end = expense_window(connection, client, start, end, "expense_audit")
            frappe.db.set_value(
                CONNECTION,
                connection.name,
                dict(expense_audit_cursor=iso(end), last_expense_audit_at=now_datetime()),
                update_modified=False,
            )
            # Advance the audit cursor only after the window fully committed; a crash
            # before this commit simply re-audits the segment, never skips it.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
    # Older unfinished expenses can receive approval/receipts long after expense_date.
    for row in frappe.get_all(
        "Revolut Expense",
        filters={
            "connection": connection.name,
            "upstream_state": ["not in", ["approved", "rejected"]],
            "last_seen_at": ["<", now_datetime() - timedelta(hours=24)],
        },
        fields=["name", "remote_id"],
        order_by="last_seen_at asc",
        limit_page_length=20,
    ):
        try:
            fresh = client.get("/expenses/" + remote_id(row.remote_id))
            if fresh.get("id") != row.remote_id:
                raise FeedError("expense_identity_mismatch")
            expense_record(connection, client, fresh)
        except Exception:
            # Persist last_seen_at before re-raising so this expense is not
            # immediately retried in a tight loop on the next scheduler tick.
            frappe.db.set_value(
                "Revolut Expense", row.name, "last_seen_at", now_datetime(), update_modified=False
            )
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            raise


def catalog_rows(client, path, key):
    token = None
    seen = set()
    for _ in range(100):
        data = client.get(path, dict(limit=500, **({"page_token": token} if token else {})))
        if not isinstance(data, dict) or not isinstance(data.get(key), list):
            raise FeedError("invalid_catalog_response")
        yield from data[key]
        token = data.get("next_page_token")
        if not token:
            return
        if token in seen:
            raise FeedError("catalog_cursor_repeated")
        seen.add(token)
    raise FeedError("catalog_page_limit")


def catalogs(connection, client):
    if not connection.sync_catalogs or not due(connection.last_catalog_at):
        return
    for path, key, kind in [
        ("/accounting-categories", "accounting_categories", "Category"),
        ("/tax-rates", "tax_rates", "Tax rate"),
        ("/label-groups", "label_groups", "Label group"),
    ]:
        for row in catalog_rows(client, path, key):
            rid = remote_id(row["id"])
            data = {
                k: row[k]
                for k in (
                    "id",
                    "name",
                    "code",
                    "percentage",
                    "created_at",
                    "updated_at",
                    "default_tax_rate_id",
                )
                if k in row
            }
            upsert(
                "Revolut Reference",
                connection,
                kind + ":" + rid,
                data,
                display_name=row.get("name"),
                reference_type=kind,
                code=row.get("code"),
            )
            if kind == "Label group":
                for label in catalog_rows(client, "/label-groups/" + rid + "/labels", "labels"):
                    compact = {k: label[k] for k in ("id", "name", "created_at", "updated_at") if k in label}
                    upsert(
                        "Revolut Reference",
                        connection,
                        "Label:" + remote_id(label["id"]),
                        compact,
                        display_name=label.get("name"),
                        reference_type="Label",
                        group_id=rid,
                    )
            # Commit each catalog/reference page as fetched; catalog syncs can span
            # many pages and must not lose earlier rows if a later page fails.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
    frappe.db.set_value(CONNECTION, connection.name, "last_catalog_at", now_datetime(), update_modified=False)
    # Persist last_catalog_at only after every row committed, so a partial catalog
    # sync is retried in full rather than mistaken for a completed one.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit


def enqueue(name):
    return frappe.enqueue(
        "revolut_bank_feed.enrichment.run",
        connection_name=name,
        queue="long",
        timeout=900,
        job_id="revolut-extra-" + name,
        deduplicate=True,
        enqueue_after_commit=True,
    )


def schedule():
    for name in frappe.get_all(CONNECTION, filters={"enabled": 1}, pluck="name"):
        enqueue(name)


def run(connection_name):
    # Background job entry point: enqueued by schedule() (scheduler process has
    # session.user=Guest) and by the enrichment API. RQ workers therefore run
    # this as Guest, which has no document permissions. The enrichment sync must
    # read/write its own DocTypes, so it explicitly adopts the system user. Scope
    # is bounded to this job; the user is never persisted back to the caller.
    frappe.set_user("Administrator")  # nosemgrep: frappe-setuser
    try:
        with connection_lock(connection_name):
            connection = frappe.get_doc(CONNECTION, connection_name)
            if not connection.enabled:
                return
            client = get_client(connection, deadline=time.monotonic() + 600)
            errors = []
            log = frappe.get_doc(
                dict(
                    doctype="Revolut Sync Log",
                    connection=connection.name,
                    company=connection.company,
                    started_at=now_datetime(),
                    status="Running",
                )
            ).insert(ignore_permissions=True)
            # Persist the Running log before any phase runs; if the worker is killed
            # mid-run, the log must already show an attempt started, not vanish.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            accounts = None
            try:
                accounts = client.get("/accounts")
                if not isinstance(accounts, list):
                    raise FeedError("invalid_accounts_response")
                account_snapshots(connection, accounts)
            except Exception as exc:
                frappe.db.rollback()
                errors.append("accounts:" + safe_error(exc))
            phases = [
                ("expenses", lambda: expenses(connection, client)),
                ("receipts", lambda: receipt_batch(connection, client)),
                ("catalogs", lambda: catalogs(connection, client)),
            ]
            if accounts is not None:
                phases.append(("fx", lambda: rates(connection, client, accounts)))
            for kind, phase in phases:
                try:
                    phase()
                except Exception as exc:
                    frappe.db.rollback()
                    errors.append(kind + ":" + safe_error(exc))
            status = "Extra Error" if errors else "Extra Success"
            error = ";".join(errors)[:140] or None
            frappe.db.set_value(
                CONNECTION,
                connection.name,
                dict(extras_last_status=status, extras_error_code=error, last_extras_at=now_datetime()),
                update_modified=False,
            )
            frappe.db.set_value(
                "Revolut Sync Log",
                log.name,
                dict(status=status, error_code=error, finished_at=now_datetime()),
            )
            # Final commit while still holding the connection lock: extras status/log
            # must be durable before the lock is released and another run can start.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            return {"status": status, "error_code": error}
    except FeedError as exc:
        if str(exc) == "connection_busy":
            return {"status": "Busy"}
        raise
