"""Pure rules for read-only accounting evidence; no automatic ledger postings."""

import re

from .core import FeedError, iter_transactions, money, utc


def compact_expense(row):
    fields = (
        "id",
        "state",
        "transaction_type",
        "description",
        "submitted_at",
        "completed_at",
        "payer",
        "merchant",
        "transaction_id",
        "expense_date",
        "labels",
        "splits",
        "receipt_ids",
        "spent_amount",
    )
    if not row.get("id") or not row.get("expense_date"):
        raise FeedError("invalid_expense_identity")
    utc(row["expense_date"])
    money(row.get("spent_amount", {}).get("amount"))
    return {k: row[k] for k in fields if k in row}


def quote_values(row, from_currency, to_currency):
    if (
        row.get("from", {}).get("currency") != from_currency
        or row.get("to", {}).get("currency") != to_currency
    ):
        raise FeedError("quote_currency_mismatch")
    rate = money(row.get("rate"))
    if rate <= 0:
        raise FeedError("invalid_exchange_rate")
    return dict(
        from_currency=from_currency,
        to_currency=to_currency,
        exchange_rate=rate,
        rate_date=utc(row["rate_date"]).replace(tzinfo=None),
        fee_amount=money(row.get("fee", {}).get("amount", 0)),
        fee_currency=row.get("fee", {}).get("currency"),
    )


def receipt_extension(data):
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    raise FeedError("unsupported_receipt_format_pdf_png_jpeg_only")


def remote_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,140}", value):
        raise FeedError("invalid_remote_id")
    return value


def iter_expenses(fetch, start, end, page_size=200, checkpoint=None):
    yield from iter_transactions(
        fetch,
        start,
        end,
        page_size=page_size,
        checkpoint=checkpoint,
        timestamp_field="expense_date",
        tie_size=500,
    )
