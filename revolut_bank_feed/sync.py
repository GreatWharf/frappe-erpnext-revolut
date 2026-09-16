"""Bounded jobs with durable progress. Each API transaction is a database unit."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import frappe
from frappe.utils import now_datetime

from .auth import connection_lock, get_client
from .core import FeedError, iso, iter_transactions, utc
from .importer import get_maps, ingest

CONNECTION = "Revolut Connection"
EVENT = "Revolut Webhook Event"


def enqueue_connection(name):
    return frappe.enqueue(
        "revolut_bank_feed.sync.run",
        connection_name=name,
        queue="long",
        timeout=900,
        job_id="revolut-feed-" + name,
        deduplicate=True,
        enqueue_after_commit=True,
    )


def schedule():
    for name in frappe.get_all(CONNECTION, filters={"enabled": 1}, pluck="name"):
        enqueue_connection(name)


def safe_error(exc):
    # Even framework validation messages can embed bank data. Never record tracebacks
    # or arbitrary exception text in job logs, Error Log, or HTTP responses.
    return (str(exc) if isinstance(exc, FeedError) else "internal_error_" + type(exc).__name__)[:140]


def _persist_transaction(connection, tx, maps, stats):
    frappe.db.savepoint("revolut_transaction")
    try:
        result = ingest(connection, tx, maps)
    except Exception:
        frappe.db.rollback(save_point="revolut_transaction")
        raise
    stats["transactions_seen"] += 1
    stats["bank_rows_created"] += result["created"]
    stats["review_count"] += result["review"]
    # Commit each transaction as it lands; a crash before the next one must not
    # redo or lose bank rows already created here (checkpoint recovery).
    frappe.db.commit()  # nosemgrep: frappe-manual-commit


def _fetch_one(client, transaction_id):
    tx = client.get("/transaction/" + transaction_id)
    if not isinstance(tx, dict) or tx.get("id") != transaction_id:
        raise FeedError("transaction_identity_mismatch")
    return tx


def _inbox(connection, client, maps, stats):
    events = frappe.get_all(
        EVENT,
        filters={
            "connection": connection.name,
            "status": ["in", ["Pending", "Retry"]],
            "next_attempt_at": ["<=", now_datetime()],
        },
        fields=["name", "transaction_id", "attempts"],
        order_by="next_attempt_at asc",
        limit_page_length=50,
    )
    for event in events:
        try:
            tx = _fetch_one(client, event.transaction_id)
            _persist_transaction(connection, tx, maps, stats)
            frappe.db.set_value(
                EVENT, event.name, {"status": "Done", "error_code": None}, update_modified=False
            )
        except Exception as exc:
            frappe.db.rollback()
            attempts = event.attempts + 1
            frappe.db.set_value(
                EVENT,
                event.name,
                {
                    "status": "Retry",
                    "attempts": attempts,
                    "error_code": safe_error(exc),
                    "next_attempt_at": now_datetime()
                    + timedelta(minutes=min(15 * 2 ** min(attempts, 7), 1440)),
                },
                update_modified=False,
            )
            # Retry bookkeeping must be durable even though this run is about to fail:
            # a crashed worker must resume this event from Retry, never lose it silently.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            # Fail the run visibly and allow scheduled/backfill recovery on next run.
            raise
        # Mark this inbox event durably Done before moving to the next one; a crash
        # here must never cause an already-ingested transaction to be redelivered.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit


def _pending(connection, client, maps, stats):
    pending = frappe.get_all(
        "Revolut Source Transaction",
        filters={
            "connection": connection.name,
            "upstream_state": ["in", ["created", "pending"]],
            "last_checked": ["<", now_datetime() - timedelta(minutes=15)],
        },
        fields=["name", "transaction_id"],
        order_by="last_checked asc",
        limit_page_length=50,
    )
    errors = []
    for row in pending:
        try:
            _persist_transaction(connection, _fetch_one(client, row.transaction_id), maps, stats)
        except Exception as exc:
            frappe.db.rollback()
            # Rotate failed IDs to the back of the check queue; they remain pending
            # and retryable, but cannot starve every later pending transaction.
            frappe.db.set_value(
                "Revolut Source Transaction", row.name, "last_checked", now_datetime(), update_modified=False
            )
            # Persist the rotated last_checked now; a crash before the next row must
            # not re-fetch this one immediately and starve every later pending row.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            errors.append(safe_error(exc))
    if errors:
        raise FeedError(";".join(dict.fromkeys(errors))[:140])


def _window(connection, client, maps, stats, start, end, prefix):
    # Freeze a window across retries. Checkpoint only after every transaction in
    # a page (including tied boundary timestamps) has committed successfully.
    state = frappe.db.get_value(
        CONNECTION,
        connection.name,
        [prefix + "_window_start", prefix + "_window_end", prefix + "_window_to"],
        as_dict=True,
    )
    if state.get(prefix + "_window_start"):
        start = utc(state[prefix + "_window_start"])
        end = utc(state[prefix + "_window_end"])
        page_to = utc(state[prefix + "_window_to"])
    else:
        page_to = end
        frappe.db.set_value(
            CONNECTION,
            connection.name,
            {
                prefix + "_window_start": iso(start),
                prefix + "_window_end": iso(end),
                prefix + "_window_to": iso(end),
            },
            update_modified=False,
        )
        # Freeze and persist the window boundaries before fetching any page; a
        # retry must resume this exact window, never silently pick a new one.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def checkpoint(next_to):
        frappe.db.set_value(
            CONNECTION, connection.name, prefix + "_window_to", iso(next_to), update_modified=False
        )
        # Advance and commit the page checkpoint immediately: iter_transactions calls
        # this between pages so a crash mid-window resumes at the last committed page.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    for tx in iter_transactions(
        lambda params: client.get("/transactions", params), start, page_to, checkpoint=checkpoint
    ):
        _persist_transaction(connection, tx, maps, stats)
    # These deletes and the caller's completed-window cursor commit atomically.
    frappe.db.set_value(
        CONNECTION,
        connection.name,
        {prefix + "_window_start": None, prefix + "_window_end": None, prefix + "_window_to": None},
        update_modified=False,
    )
    return end


def _poll(connection, client, maps, stats, cutoff):
    earliest = utc(connection.historical_from)
    cursor = utc(connection.poll_cursor) if connection.poll_cursor else earliest
    end = min(cursor + timedelta(days=connection.window_days), cutoff)
    start = max(earliest, cursor - timedelta(minutes=getattr(connection, "poll_overlap_minutes", None) or 60))
    if start < end:
        end = _window(connection, client, maps, stats, start, end, "poll")
        frappe.db.set_value(CONNECTION, connection.name, "poll_cursor", iso(end), update_modified=False)
        # Advance the poll cursor only after the window fully committed; a crash
        # before this commit simply re-polls the window (idempotent), never skips it.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit


def _recent(connection, client, maps, stats, cutoff):
    last = getattr(connection, "last_recent_at", None)
    if last and utc(last) > utc(now_datetime()) - timedelta(hours=24):
        return
    start = max(utc(connection.historical_from), cutoff - timedelta(days=connection.lookback_days))
    if start < cutoff:
        _window(connection, client, maps, stats, start, cutoff, "recent")
        frappe.db.set_value(
            CONNECTION, connection.name, "last_recent_at", now_datetime(), update_modified=False
        )
        # Persist last_recent_at only after the window fully committed; a crash
        # before this commit simply reruns the recent pass, never skips it.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit


def _backfill(connection, client, maps, stats):
    if not connection.backfill_next or not connection.backfill_end:
        return
    start = utc(connection.backfill_next)
    final = utc(connection.backfill_end)
    end = min(start + timedelta(days=connection.window_days), final)
    if start < end:
        end = _window(connection, client, maps, stats, start, end, "backfill")
    frappe.db.set_value(
        CONNECTION,
        connection.name,
        {
            "backfill_next": iso(end) if end < final else None,
            "backfill_end": connection.backfill_end if end < final else None,
        },
        update_modified=False,
    )
    # Persist the advanced backfill cursor only after the window fully committed;
    # a crash before this commit simply re-runs the backfill segment, never skips it.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit


def _audit(connection, client, maps, stats, cutoff):
    if not connection.audit_enabled:
        return
    if connection.last_audit_at and connection.last_audit_at > now_datetime() - timedelta(hours=24):
        return
    earliest = utc(connection.historical_from)
    start = max(earliest, utc(connection.audit_cursor)) if connection.audit_cursor else earliest
    if start >= cutoff:
        start = earliest
    end = min(start + timedelta(days=connection.audit_window_days), cutoff)
    if start < end:
        end = _window(connection, client, maps, stats, start, end, "audit")
        frappe.db.set_value(
            CONNECTION,
            connection.name,
            {"audit_cursor": iso(end) if end < cutoff else iso(earliest), "last_audit_at": now_datetime()},
            update_modified=False,
        )
        # Advance the audit cursor only after the window fully committed; a crash
        # before this commit simply re-audits the segment, never skips it.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit


def run(connection_name):
    # Background job entry point: enqueued by schedule() (scheduler process has
    # session.user=Guest) and by API/webhook callers. RQ workers therefore run
    # this as Guest, which has no document permissions. The sync must read/write
    # its own DocTypes, so it explicitly adopts the system user. Scope is bounded
    # to this job; the user is never persisted back to the caller's session.
    frappe.set_user("Administrator")  # nosemgrep: frappe-setuser
    try:
        with connection_lock(connection_name):
            return _run_locked(connection_name)
    except FeedError as exc:
        if str(exc) == "connection_busy":
            return {"status": "Busy"}
        raise


def _run_locked(name):
    connection = frappe.get_doc(CONNECTION, name)
    if not connection.enabled:
        return {"status": "Disabled"}
    stats = dict(transactions_seen=0, bank_rows_created=0, review_count=0)
    log = frappe.get_doc(
        {
            "doctype": "Revolut Sync Log",
            "connection": name,
            "company": connection.company,
            "started_at": now_datetime(),
            "status": "Running",
        }
    ).insert(ignore_permissions=True)
    frappe.db.set_value(CONNECTION, name, "last_attempt_at", now_datetime(), update_modified=False)
    # Persist the Running log and last_attempt_at before any phase runs; if the
    # worker is killed mid-run, the attempt must already be durably visible.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit
    try:
        deadline = time.monotonic() + 600
        client = get_client(connection, deadline=deadline)
        maps = get_maps(connection)
        if not maps:
            raise FeedError("no_account_mappings")
        accounts = client.get("/accounts")
        if not isinstance(accounts, list):
            raise FeedError("invalid_accounts_response")
        available = {(row["id"], row["currency"]) for row in accounts}
        if any(key not in available for key, row in maps.items() if row.enabled):
            raise FeedError("mapped_account_missing_in_revolut")
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=5)
        phase_errors = []
        for phase in (
            lambda: _poll(connection, client, maps, stats, cutoff),
            lambda: _inbox(connection, client, maps, stats),
            lambda: _pending(connection, client, maps, stats),
            lambda: _backfill(connection, client, maps, stats),
            lambda: _audit(connection, client, maps, stats, cutoff),
            lambda: _recent(connection, client, maps, stats, cutoff),
        ):
            try:
                phase()
            except Exception as exc:
                frappe.db.rollback()
                phase_errors.append(safe_error(exc))
        if phase_errors:
            raise FeedError(";".join(dict.fromkeys(phase_errors)))
        # Show all outstanding reviews, even if outside this particular window.
        reviews = frappe.db.count("Revolut Source Transaction", {"connection": name, "needs_review": 1})
        status = "Review Required" if reviews else "Success"
        frappe.db.set_value(
            CONNECTION,
            name,
            {"last_success_at": now_datetime(), "last_status": status, "last_error_code": None},
            update_modified=False,
        )
        error = None
    except Exception as exc:
        frappe.db.rollback()
        status, error = "Error", safe_error(exc)
        frappe.db.set_value(
            CONNECTION, name, {"last_status": status, "last_error_code": error}, update_modified=False
        )
    frappe.db.set_value(
        "Revolut Sync Log",
        log.name,
        dict(stats, status=status, error_code=error, finished_at=now_datetime()),
        update_modified=False,
    )
    # Final commit while still holding the connection lock: the run's outcome must
    # be durable before the lock is released and another run can be scheduled.
    frappe.db.commit()  # nosemgrep: frappe-manual-commit
    return dict(stats, status=status, error_code=error)


def cleanup():
    # Source transactions, leg identities and revisions are never pruned automatically.
    # Failed inbox entries remain retryable and diagnostic logs survive for 90 days.
    frappe.db.delete(EVENT, {"status": "Done", "received_at": ["<", now_datetime() - timedelta(days=30)]})
    frappe.db.delete(
        "Revolut Sync Log",
        {"status": ["!=", "Running"], "started_at": ["<", now_datetime() - timedelta(days=90)]},
    )
    # A hard-killed worker cannot run its finalizer. Make abandoned runs visible.
    for row in frappe.get_all(
        "Revolut Sync Log",
        filters={"status": "Running", "started_at": ["<", now_datetime() - timedelta(minutes=30)]},
        fields=["name", "connection"],
    ):
        frappe.db.set_value(
            "Revolut Sync Log",
            row.name,
            {"status": "Interrupted", "error_code": "worker_interrupted", "finished_at": now_datetime()},
            update_modified=False,
        )
