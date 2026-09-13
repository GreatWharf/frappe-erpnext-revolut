from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from revolut_bank_feed.core import FeedError, iso
from revolut_bank_feed.enrichment_core import compact_expense, iter_expenses, quote_values, receipt_extension


def test_expense_retains_splits_labels_and_receipt_identity():
    source = dict(
        id="expense",
        expense_date="2026-09-01T00:00:00Z",
        state="approved",
        spent_amount={"amount": Decimal("12.30"), "currency": "GBP"},
        transaction_id="transaction",
        receipt_ids=["receipt"],
        splits=[
            {
                "amount": {"amount": 12.3, "currency": "GBP"},
                "category": {"id": "cat"},
                "tax_rate": {"percentage": 20},
            }
        ],
        labels={"Department": ["Sales"]},
        unknown_secret="must-not-survive",
    )
    result = compact_expense(source)
    assert result["splits"] == source["splits"]
    assert result["labels"] == source["labels"]
    assert result["receipt_ids"] == ["receipt"]
    assert "unknown_secret" not in result


def test_quote_validates_direction_and_separates_fee():
    data = {
        "from": {"currency": "EUR", "amount": 1},
        "to": {"currency": "GBP", "amount": 0.86},
        "rate": Decimal(".86"),
        "rate_date": "2026-09-12T09:00:00Z",
        "fee": {"currency": "EUR", "amount": ".01"},
    }
    values = quote_values(data, "EUR", "GBP")
    assert values["exchange_rate"] == Decimal(".86")
    assert values["fee_amount"] == Decimal(".01")
    with pytest.raises(FeedError):
        quote_values(data, "GBP", "EUR")


@pytest.mark.parametrize(
    "data,extension", [(b"%PDF-1.7\n", ".pdf"), (b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg")]
)
def test_receipt_uses_content_not_remote_filename(data, extension):
    assert receipt_extension(data) == extension


def test_active_receipt_content_rejected():
    with pytest.raises(FeedError):
        receipt_extension(b'<svg onload="bad()">')


def test_expenses_page_by_expense_date_and_checkpoint():
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    rows = [{"id": str(i), "expense_date": iso(start + timedelta(seconds=i))} for i in range(7)]
    calls = []
    checkpoints = []

    def fetch(p):
        calls.append(p)
        return sorted(
            [r for r in rows if p["from"] <= r["expense_date"] < p["to"]],
            key=lambda r: r["expense_date"],
            reverse=True,
        )[: p["count"]]

    result = list(iter_expenses(fetch, start, end, page_size=3, checkpoint=checkpoints.append))
    assert {r["id"] for r in result} == {r["id"] for r in rows}
    assert checkpoints
    assert max(c["count"] for c in calls) <= 500


def test_saturated_expense_timestamp_fails_without_advancing_checkpoint():
    from datetime import datetime, timezone

    from revolut_bank_feed.core import iso

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    checkpoint = []

    def fetch(p):
        return [{"id": str(i), "expense_date": iso(start)} for i in range(p["count"])]

    with pytest.raises(FeedError, match="pagination_tie_saturated"):
        list(iter_expenses(fetch, start, end, checkpoint=checkpoint.append))
    assert not checkpoint
