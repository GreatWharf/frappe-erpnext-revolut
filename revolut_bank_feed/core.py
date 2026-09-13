"""Pure bank-feed rules; no Frappe imports or financial side effects."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


class FeedError(Exception):
    """Safe diagnostic code: never include bank payloads or secrets in messages."""


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def utc(value):
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError, TypeError:
            raise FeedError("invalid_timestamp") from None
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def iso(value):
    return utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def money(value):
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal("999999999999999"):
            raise InvalidOperation
        return result
    except InvalidOperation, ValueError:
        raise FeedError("invalid_money") from None


def validate_mapping(company, mapping, bank, gl):
    if mapping["company"] != company or bank.get("company") != company or gl.get("company") != company:
        raise FeedError("mapping_company_mismatch")
    if bank.get("disabled") or not bank.get("is_company_account") or not bank.get("account"):
        raise FeedError("mapping_bank_not_active_company_account")
    if gl.get("disabled") or gl.get("is_group") or gl.get("account_type") != "Bank":
        raise FeedError("mapping_gl_not_active_bank_ledger")
    if mapping["currency"] != gl.get("account_currency"):
        raise FeedError("mapping_currency_mismatch")


def compact_transaction(tx):
    """Keep reconciliation fields only; omit cardholder, phone and card metadata."""
    top = (
        "id",
        "type",
        "state",
        "reason_code",
        "created_at",
        "updated_at",
        "completed_at",
        "related_transaction_id",
        "reference",
    )
    leg = (
        "leg_id",
        "account_id",
        "amount",
        "currency",
        "fee",
        "bill_amount",
        "bill_currency",
        "description",
        "balance",
    )
    result = {key: tx[key] for key in top if key in tx}
    result["legs"] = [{key: row[key] for key in leg if key in row} for row in tx.get("legs", [])]
    return result


def normalize(tx, mapping):
    if tx.get("state") not in ("created", "pending", "completed", "declined", "failed", "reverted"):
        raise FeedError("unsupported_transaction_state")
    if tx["state"] != "completed":
        return []
    if not tx.get("id") or not tx.get("completed_at") or not isinstance(tx.get("legs"), list):
        raise FeedError("incomplete_transaction")
    rows, seen = [], set()
    for leg in tx["legs"]:
        if leg.get("account_id") != mapping["account_id"]:
            continue
        if leg.get("currency") != mapping["currency"]:
            raise FeedError("transaction_account_currency_mismatch")
        if not leg.get("leg_id"):
            raise FeedError("missing_leg_id")
        if leg["leg_id"] in seen:
            raise FeedError("duplicate_leg_id")
        seen.add(leg["leg_id"])
        amount, fee = money(leg.get("amount")), money(leg.get("fee", 0))
        if fee < 0:
            raise FeedError("negative_fee_review")
        if fee:
            policy = mapping.get("fee_policy", "Review")
            if policy == "Deduct fee from amount":
                amount -= fee
            elif policy != "Amount includes fee":
                raise FeedError("fee_policy_review_required")
        if not amount:
            continue
        rows.append(
            dict(
                leg_id=leg["leg_id"],
                account_id=leg["account_id"],
                currency=leg["currency"],
                deposit=max(amount, Decimal(0)),
                withdrawal=max(-amount, Decimal(0)),
                fee=fee,
                bill_amount=money(leg["bill_amount"]) if leg.get("bill_amount") is not None else None,
                bill_currency=leg.get("bill_currency"),
                effective_bill_rate=(
                    abs(money(leg["bill_amount"]) / money(leg["amount"]))
                    if leg.get("bill_amount") is not None and money(leg["amount"])
                    else None
                ),
                date=utc(tx["completed_at"]).astimezone(ZoneInfo(mapping["timezone"])).date().isoformat(),
                bank_account=mapping["bank_account"],
                company=mapping["company"],
                transaction_id=tx["id"],
                transaction_type=tx["type"],
                reference_number=str(tx.get("reference") or tx["id"])[:1000],
                description=str(leg.get("description") or tx.get("reference") or tx["type"])[:1000],
            )
        )
    return rows


def decide(state, has_bank_rows, financially_changed):
    if has_bank_rows:
        return "review" if state != "completed" or financially_changed else "unchanged"
    return "create" if state == "completed" else "observe"


def iter_transactions(
    fetch,
    start,
    end,
    page_size=500,
    max_pages=200,
    checkpoint=None,
    timestamp_field="created_at",
    tie_size=1000,
):
    """Recover full-page timestamp ties before following Revolut's exclusive cursor.

    No cursor can distinguish >=1000 records at exactly one timestamp. Refuse to
    claim completeness in that case. The caller must not advance its watermark.
    """
    low, high = utc(start), utc(end)
    for _ in range(max_pages):
        if low >= high:
            return
        page = fetch({"from": iso(low), "to": iso(high), "count": page_size})
        if not isinstance(page, list):
            raise FeedError("invalid_transactions_response")
        if not page:
            if checkpoint:
                checkpoint(low)
            return
        stamps = [utc(row[timestamp_field]) for row in page]
        if stamps != sorted(stamps, reverse=True) or any(not low <= stamp < high for stamp in stamps):
            raise FeedError("pagination_order_or_range")
        if len(page) < page_size:
            yield from page
            if checkpoint:
                checkpoint(low)
            return
        boundary = stamps[-1]
        tied = fetch(
            {"from": iso(boundary), "to": iso(boundary + timedelta(microseconds=1)), "count": tie_size}
        )
        if not isinstance(tied, list) or len(tied) >= tie_size:
            raise FeedError("pagination_tie_saturated")
        if any(utc(row[timestamp_field]) != boundary for row in tied):
            raise FeedError("pagination_tie_range")
        expected = {row["id"] for row in page if utc(row[timestamp_field]) == boundary}
        if not expected.issubset({row["id"] for row in tied}):
            raise FeedError("pagination_boundary_inconsistent")
        yield from (row for row in page if utc(row[timestamp_field]) > boundary)
        yield from tied
        high = boundary
        if checkpoint:
            checkpoint(high)
    raise FeedError("pagination_page_limit")


def verify_signature(raw, timestamp, signatures, secrets, now=None):
    now = time.time() if now is None else now
    if not isinstance(timestamp, str) or not re.fullmatch(r"\d{13}", timestamp):
        raise FeedError("webhook_timestamp")
    if abs(now - int(timestamp) / 1000) > 300:
        raise FeedError("webhook_timestamp")
    message = b"v1." + timestamp.encode("ascii") + b"." + raw
    candidates = [value.strip() for value in (signatures or "").split(",")]
    for secret in secrets:
        if secret:
            expected = "v1=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
            if any(hmac.compare_digest(expected, candidate) for candidate in candidates):
                return
    raise FeedError("webhook_signature")
