import json

import jwt
import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from revolut_bank_feed.client import Client, assertion, token_request
from revolut_bank_feed.core import FeedError


class Response:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self.content = json.dumps(data).encode()
        self.headers = headers or {}


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_read_allowlist_cannot_call_payment_or_arbitrary_host():
    client = Client("Sandbox", lambda force=False: "token", session=Session([]))
    for path in ["/pay", "https://evil.invalid/accounts", "/transaction/../pay", "/webhooks"]:
        with pytest.raises(FeedError, match="endpoint"):
            client.get(path)


def test_401_refresh_once_then_decimal_json():
    session = Session([Response(401), Response(data=[{"amount": 1.23}])])
    refresh = []
    client = Client("Production", lambda force=False: refresh.append(force) or "token", session=session)
    assert str(client.get("/accounts")[0]["amount"]) == "1.23"
    assert refresh == [False, True]
    assert all(not c[2]["allow_redirects"] for c in session.calls)


def test_rate_limit_and_timeout_retries_are_bounded():
    session = Session([Response(429, headers={"Retry-After": "1"}), requests.Timeout(), Response(data=[])])
    sleeps = []
    assert (
        Client("Sandbox", lambda force=False: "token", session=session, sleep=sleeps.append).get("/accounts")
        == []
    )
    assert len(sleeps) == 2


def test_error_does_not_expose_response_or_token():
    session = Session([Response(400, {"message": "secret bank information"})])
    with pytest.raises(FeedError) as exc:
        Client("Sandbox", lambda force=False: "private-token", session=session).get("/accounts")
    assert str(exc.value) == "revolut_http_400"


def test_refresh_token_grant_and_no_bearer_or_write_scope():
    session = Session([Response(data={"access_token": "new", "expires_in": 2399})])
    result = token_request("Sandbox", "signed", refresh_token="refresh", session=session)
    assert result["access_token"] == "new"
    method, url, kwargs = session.calls[0]
    assert method == "POST" and url.endswith("/auth/token")
    assert kwargs["data"]["grant_type"] == "refresh_token"
    assert kwargs["data"]["client_assertion"] == "signed"
    assert "scope" not in kwargs["data"] and "Authorization" not in kwargs["headers"]


def test_assertion_is_rs256_with_short_expiry():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    token = assertion("client", "erp.example.com", pem, now=1800000000)
    claims = jwt.decode(
        token,
        key.public_key(),
        algorithms=["RS256"],
        audience="https://revolut.com",
        options={"verify_exp": False},
    )
    assert claims == {
        "iss": "erp.example.com",
        "sub": "client",
        "aud": "https://revolut.com",
        "exp": 1800000300,
    }


def test_expired_job_budget_does_not_attempt_token_refresh():
    import time

    attempted = []
    client = Client(
        "Sandbox",
        lambda **kwargs: attempted.append(True) or "token",
        session=Session([]),
        deadline=time.monotonic() - 1,
    )
    with pytest.raises(FeedError, match="job_time_budget"):
        client.get("/accounts")
    assert not attempted


def test_synthetic_api_fixture_flows_through_decimal_transport_and_normalization():
    from decimal import Decimal
    from pathlib import Path

    from revolut_bank_feed.core import normalize

    response = Response()
    response.content = (Path(__file__).parent / "fixtures" / "transactions.json").read_bytes()
    txs = Client("Sandbox", lambda **kwargs: "test-token", session=Session([response])).get("/transactions")
    mapping = {
        "account_id": "acct-1",
        "currency": "GBP",
        "bank_account": "Bank GBP",
        "company": "Acme",
        "timezone": "UTC",
        "fee_policy": "Review",
    }
    assert normalize(txs[0], mapping)[0]["withdrawal"] == Decimal("10.25")
    assert normalize(txs[1], mapping)[0]["deposit"] == Decimal("10.25")
    assert normalize(txs[2], mapping)[0]["withdrawal"] == Decimal("100.00")


@pytest.mark.parametrize(
    "path",
    [
        "/expenses",
        "/expenses/id",
        "/rate",
        "/accounting-categories",
        "/tax-rates",
        "/label-groups",
        "/label-groups/id/labels",
    ],
)
def test_extra_endpoints_only_issue_get(path):
    session = Session([Response(data=[])])
    Client("Production", lambda force=False: "token", session=session).get(path)
    assert session.calls[0][0] == "GET"


def test_sensitive_and_write_resources_still_denied():
    client = Client("Production", lambda force=False: "token", session=Session([]))
    for path in ["/exchange", "/cards/id/sensitive", "/pay", "/counterparty", "/expenses/id/../pay"]:
        with pytest.raises(FeedError):
            client.get(path)
    with pytest.raises(FeedError):
        client.get("/accounts", binary=True)


def test_receipt_download_stream_limit_and_close():
    class BinaryResponse:
        status_code = 200
        closed = False

        def iter_content(self, chunk_size):
            yield b"x" * (8 * 1024 * 1024)
            yield b"x"

        def close(self):
            self.closed = True

    response = BinaryResponse()
    client = Client("Production", lambda force=False: "token", session=Session([response]))
    with pytest.raises(FeedError, match="receipt_too_large"):
        client.get("/expenses/id/receipts/id/content", binary=True)
    assert response.closed
