"""Unit tests for the retry rules in eva_email._http. No network: requests
go to an httpx.MockTransport. Run from sdk/python with
``py -3 -m pytest tests/test_http.py``."""

import time

import httpx
import pytest

from eva_email import DailyLimitError, QuotaExceededError, RateLimitError
from eva_email._http import request

BASE_URL = "https://example.test"


def _client(responses):
    """A client answering from ``responses`` in order (the last one repeats)
    and the list of requests it saw."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return responses[min(len(seen), len(responses)) - 1]

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def _call(client):
    return request(
        client, "eva_test", 3, 1.0,
        method="POST", path="/api/v1/verify/batch", base_url=BASE_URL,
        json_body={"emails": ["a@b.com"]},
    )


def test_daily_limit_is_not_retried_and_raises_daily_limit_error():
    client, seen = _client([
        httpx.Response(
            429,
            json={"error": "The Free plan allows 50 checks a day.", "code": "DAILY_LIMIT"},
            headers={"Retry-After": "86000", "X-Daily-Limit": "50", "X-Daily-Remaining": "5"},
        ),
    ])
    started = time.monotonic()
    with pytest.raises(DailyLimitError) as exc:
        _call(client)
    assert len(seen) == 1, "a used-up day must not be retried"
    assert time.monotonic() - started < 1.0
    err = exc.value
    assert err.code == "DAILY_LIMIT"
    assert err.status == 429
    assert err.retry_after == 86000
    assert err.limit == 50
    assert err.remaining == 5
    assert err.message == "The Free plan allows 50 checks a day."


def test_quota_exceeded_is_not_retried():
    client, seen = _client([
        httpx.Response(429, json={"error": "monthly quota exceeded", "code": "QUOTA_EXCEEDED"}),
    ])
    with pytest.raises(QuotaExceededError):
        _call(client)
    assert len(seen) == 1


def test_rate_limited_is_still_retried():
    client, seen = _client([
        httpx.Response(429, json={"error": "rate limit exceeded", "code": "RATE_LIMITED"}),
    ])
    with pytest.raises(RateLimitError):
        _call(client)
    assert len(seen) == 4  # first try + max_retries


def test_rate_limited_then_success_returns_data():
    client, seen = _client([
        httpx.Response(429, json={"error": "rate limit exceeded", "code": "RATE_LIMITED"}),
        httpx.Response(200, json={"data": {"email": "a@b.com", "risk": "safe"}}),
    ])
    data, _, _ = _call(client)
    assert data["risk"] == "safe"
    assert len(seen) == 2
