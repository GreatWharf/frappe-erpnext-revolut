import copy
import hashlib
import hmac
from datetime import datetime
from decimal import Decimal

import pytest

from revolut_bank_feed.core import (
    FeedError,
    compact_transaction,
    decide,
    identity,
    iter_transactions,
    normalize,
    validate_mapping,
    verify_signature,
)


def transaction(**changes):
    data = dict(
        id="tx-1",
        type="card_payment",
        state="completed",
        created_at="2026-08-01T22:30:00Z",
        updated_at="2026-08-02T22:30:00Z",
        completed_at="2026-08-02T22:30:00Z",
        reference="Invoice 42",
        legs=[dict(leg_id="leg-1", account_id="acct-1", amount=-10.25, currency="GBP")],
    )
    data.update(changes)
    return data


def mapping(**changes):
    data = dict(
        account_id="acct-1",
        currency="GBP",
        bank_account="Bank GBP",
        company="Acme",
        fee_policy="Review",
        timezone="Europe/London",
    )
    data.update(changes)
    return data


def test_identity_separates_accounts_even_when_revolut_reuses_leg_id():
    assert identity("Production", "acct-1", "GBP", "tx-1", "leg-1") != identity(
        "Production", "acct-2", "GBP", "tx-1", "leg-1"
    )
    assert identity("Production", "acct-1", "GBP", "tx-1", "leg-1") == identity(
        "Production", "acct-1", "GBP", "tx-1", "leg-1"
    )


def test_completed_withdrawal_uses_decimal_and_completed_date():
    row = normalize(transaction(), mapping())[0]
    assert row["withdrawal"] == Decimal("10.25")
    assert row["deposit"] == 0
    assert row["date"] == "2026-08-02"


@pytest.mark.parametrize("state", ["created", "pending", "declined", "failed", "reverted"])
def test_noncompleted_transactions_do_not_become_bank_rows(state):
    assert normalize(transaction(state=state), mapping()) == []


def test_refund_imports_as_own_positive_transaction():
    tx = transaction(type="refund", id="refund", related_transaction_id="original")
    tx["legs"][0]["amount"] = 10.25
    assert normalize(tx, mapping())[0]["deposit"] == Decimal("10.25")


def test_fx_uses_account_currency_not_bill_currency():
    tx = transaction(type="exchange")
    tx["legs"][0].update(bill_amount="-12.30", bill_currency="USD")
    tx["legs"].append(dict(leg_id="leg-1", account_id="acct-2", currency="USD", amount="12.30"))
    assert normalize(tx, mapping())[0]["withdrawal"] == Decimal("10.25")
    assert normalize(tx, mapping(account_id="acct-2", currency="USD"))[0]["deposit"] == Decimal("12.30")


def test_fee_requires_explicit_policy():
    tx = transaction()
    tx["legs"][0]["fee"] = "0.15"
    with pytest.raises(FeedError, match="fee_policy"):
        normalize(tx, mapping())
    assert normalize(tx, mapping(fee_policy="Deduct fee from amount"))[0]["withdrawal"] == Decimal("10.40")
    assert normalize(tx, mapping(fee_policy="Amount includes fee"))[0]["withdrawal"] == Decimal("10.25")


def test_deposit_fee_and_fee_only():
    tx = transaction()
    tx["legs"][0].update(amount="5.50", fee="0.10")
    assert normalize(tx, mapping(fee_policy="Deduct fee from amount"))[0]["deposit"] == Decimal("5.40")
    tx["legs"][0]["amount"] = 0
    assert normalize(tx, mapping(fee_policy="Deduct fee from amount"))[0]["withdrawal"] == Decimal("0.10")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", True])
def test_invalid_money_rejected(value):
    tx = transaction()
    tx["legs"][0]["amount"] = value
    with pytest.raises(FeedError):
        normalize(tx, mapping())


def test_missing_leg_id_does_not_use_array_index():
    tx = transaction()
    del tx["legs"][0]["leg_id"]
    with pytest.raises(FeedError, match="leg_id"):
        normalize(tx, mapping())


def test_mapping_checks_company_currency_and_disabled_account():
    bank = dict(company="Acme", is_company_account=1, disabled=0, account="GL Bank")
    gl = dict(company="Acme", account_currency="GBP", is_group=0, disabled=0, account_type="Bank")
    validate_mapping("Acme", mapping(), bank, gl)
    for obj, key, value in [
        (bank, "company", "Elsewhere"),
        (gl, "account_currency", "USD"),
        (bank, "disabled", 1),
    ]:
        original = obj[key]
        obj[key] = value
        with pytest.raises(FeedError):
            validate_mapping("Acme", mapping(), bank, gl)
        obj[key] = original


def test_state_decisions_preserve_existing_records():
    assert decide("completed", False, False) == "create"
    assert decide("pending", False, False) == "observe"
    assert decide("completed", True, False) == "unchanged"
    assert decide("completed", True, True) == "review"
    assert decide("reverted", True, False) == "review"


def test_sensitive_payload_is_minimized():
    tx = transaction(card={"phone": "private", "card_number": "private"}, auth_code="private")
    reduced = compact_transaction(tx)
    assert "card" not in reduced and "auth_code" not in reduced
    assert reduced["legs"] == tx["legs"]


def test_pagination_recovers_tied_boundary():
    rows = [transaction(id=str(i), created_at=f"2026-08-01T00:00:0{s}Z") for i, s in enumerate([3, 2, 2, 1])]
    calls = []

    def fetch(params):
        calls.append(params)
        lo = datetime.fromisoformat(params["from"].replace("Z", "+00:00"))
        hi = datetime.fromisoformat(params["to"].replace("Z", "+00:00"))
        return [
            copy.deepcopy(r)
            for r in rows
            if lo <= datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) < hi
        ][: params["count"]]

    got = list(iter_transactions(fetch, "2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z", page_size=2))
    assert {r["id"] for r in got} == {"0", "1", "2", "3"}
    assert any(c["count"] == 1000 for c in calls)


def test_saturated_timestamp_fails_closed():
    rows = [transaction(id=str(i), created_at="2026-08-01T00:00:02Z") for i in range(1000)]
    with pytest.raises(FeedError, match="pagination_tie"):
        list(
            iter_transactions(
                lambda p: rows[: p["count"]], "2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z", page_size=2
            )
        )


def test_webhook_exact_bytes_timestamp_and_rotation():
    raw = b'{"event":"TransactionCreated","data":{"id":"x"}}'
    ts = "1800000000000"
    sig = "v1=" + hmac.new(b"secret", b"v1." + ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    verify_signature(raw, ts, "v1=bad," + sig, ["old", "secret"], now=1800000000)
    for body, now in [(raw + b" ", 1800000000), (raw, 1800000301), (raw, 1799999699)]:
        with pytest.raises(FeedError):
            verify_signature(body, ts, sig, ["secret"], now=now)


def test_pagination_checkpoint_not_advanced_until_page_consumed():
    pages = [
        transaction(id="one", created_at="2026-08-01T00:00:02Z"),
        transaction(id="two", created_at="2026-08-01T00:00:01Z"),
    ]
    calls = []

    def fetch(params):
        if params["count"] == 1000:
            return [pages[-1]]
        if params["to"].startswith("2026-08-01T00:00:01"):
            return []
        return pages

    iterator = iter_transactions(
        fetch, "2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z", page_size=2, checkpoint=calls.append
    )
    assert next(iterator)["id"] == "one"
    assert calls == []
    assert next(iterator)["id"] == "two"
    assert calls == []
    list(iterator)
    assert len(calls) == 2
    assert calls[0].second == 1


def test_effective_bill_rate_preserves_original_amount_and_direction():
    tx = transaction()
    tx["legs"][0].update(amount=-100, bill_amount=-125, bill_currency="USD")
    row = normalize(tx, mapping())[0]
    assert row["bill_amount"] == Decimal("-125")
    assert row["bill_currency"] == "USD"
    assert row["effective_bill_rate"] == Decimal("1.25")
    assert row["withdrawal"] == Decimal("100")
