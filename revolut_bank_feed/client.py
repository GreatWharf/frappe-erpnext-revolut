"""Restricted Revolut Business API transport. No generic write operation exists."""

from __future__ import annotations

import json
import random
import re
import time
from decimal import Decimal
from email.utils import parsedate_to_datetime

import jwt
import requests

from .core import FeedError

BASES = {
    "Production": "https://b2b.revolut.com/api/1.0",
    "Sandbox": "https://sandbox-b2b.revolut.com/api/1.0",
}
TIMEOUT = (5, 30)


def base_url(environment):
    if environment not in BASES:
        raise FeedError("invalid_environment")
    return BASES[environment]


def parse_response(response):
    if len(response.content) > 8 * 1024 * 1024:
        raise FeedError("response_too_large")
    try:
        return json.loads(response.content, parse_float=Decimal)
    except (ValueError, UnicodeDecodeError):
        raise FeedError("invalid_json_response") from None


def assertion(client_id, issuer, private_key, now=None):
    now = int(time.time() if now is None else now)
    try:
        return jwt.encode(
            {"iss": issuer, "sub": client_id, "aud": "https://revolut.com", "exp": now + 300},
            private_key,
            algorithm="RS256",
        )
    except Exception:
        raise FeedError("invalid_signing_key") from None


def token_request(environment, signed_assertion, *, code=None, refresh_token=None, session=None):
    if bool(code) == bool(refresh_token):
        raise FeedError("invalid_token_grant")
    data = {
        "grant_type": "authorization_code" if code else "refresh_token",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": signed_assertion,
    }
    data["code" if code else "refresh_token"] = code or refresh_token
    try:
        response = (session or requests).request(
            "POST",
            base_url(environment) + "/auth/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise FeedError("token_network_error_reauthorize_if_needed") from None
    if response.status_code != 200:
        raise FeedError(f"token_http_{response.status_code}")
    result = parse_response(response)
    if not isinstance(result, dict) or not result.get("access_token"):
        raise FeedError("invalid_token_response")
    try:
        if not 60 < int(result["expires_in"]) <= 86400:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise FeedError("invalid_token_expiry") from None
    # The current API may omit scope. In that case READ is established at consent.
    if result.get("scope") and set(re.split(r"[,\s]+", result["scope"])) != {"READ"}:
        raise FeedError("unexpected_token_scope_revoke_consent")
    return result


class Client:
    def __init__(self, environment, token_provider, *, session=None, sleep=time.sleep, deadline=None):
        self.base = base_url(environment)
        self.token_provider = token_provider
        self.session = session or requests
        self.sleep = sleep
        self.deadline = deadline

    def get(self, path, params=None, *, binary=False):
        if not allowed_read_path(path, binary=binary):
            raise FeedError("endpoint_not_allowed")
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise FeedError("job_time_budget")
        token = self.token_provider()
        refreshed = False
        for attempt in range(5):
            if self.deadline is not None and time.monotonic() > self.deadline:
                raise FeedError("job_time_budget")
            try:
                response = self.session.request(
                    "GET",
                    self.base + path,
                    params=params,
                    headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/octet-stream" if binary else "application/json",
                    },
                    timeout=TIMEOUT,
                    allow_redirects=False,
                    stream=binary,
                )
            except requests.RequestException:
                if attempt == 4:
                    raise FeedError("revolut_network_error") from None
                self.sleep(min(2**attempt, 16) + random.random())
                continue
            status = response.status_code
            if status == 200:
                if binary:
                    chunks = []
                    size = 0
                    try:
                        for chunk in response.iter_content(chunk_size=65536):
                            size += len(chunk)
                            if size > 8 * 1024 * 1024:
                                raise FeedError("receipt_too_large")
                            chunks.append(chunk)
                        return b"".join(chunks)
                    except requests.RequestException:
                        raise FeedError("receipt_download_interrupted") from None
                    finally:
                        response.close()
                return parse_response(response)
            if binary:
                response.close()
            if status == 401 and not refreshed:
                token = self.token_provider(force=True)
                refreshed = True
                continue
            if status == 429 or 500 <= status < 600:
                if attempt == 4:
                    raise FeedError(f"revolut_http_{status}")
                delay = 2**attempt
                retry_after = response.headers.get("Retry-After", "")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        try:
                            delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
                        except (ValueError, TypeError):
                            pass
                if delay > 60:
                    raise FeedError("revolut_rate_limit_retry_later")
                self.sleep(max(0, delay) + random.random())
                continue
            raise FeedError(f"revolut_http_{status}")
        raise FeedError("revolut_retry_limit")


def allowed_read_path(path, *, binary=False):
    identifier = r"[A-Za-z0-9_-]{1,140}"
    receipt = bool(re.fullmatch(r"/expenses/" + identifier + r"/receipts/" + identifier + r"/content", path))
    if binary:
        return receipt
    return (
        path
        in (
            "/accounts",
            "/transactions",
            "/expenses",
            "/rate",
            "/accounting-categories",
            "/tax-rates",
            "/label-groups",
        )
        or bool(re.fullmatch(r"/(?:transaction|expenses)/" + identifier, path))
        or bool(re.fullmatch(r"/label-groups/" + identifier + r"/labels", path))
    )
