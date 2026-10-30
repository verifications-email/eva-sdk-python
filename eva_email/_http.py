"""Internal HTTP wrapper with retry logic and rate limit parsing."""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, TypeVar

import httpx

from .errors import (
    AuthenticationError,
    DailyLimitError,
    EvaError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
)
from .models import RateLimitInfo

T = TypeVar("T")


def _int_or_none(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_rate_limit(headers: httpx.Headers) -> RateLimitInfo:
    reset_raw = headers.get("X-RateLimit-Reset")
    reset_dt = None
    if reset_raw:
        try:
            reset_dt = datetime.fromtimestamp(int(reset_raw), tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            pass

    return RateLimitInfo(
        limit=_int_or_none(headers.get("X-RateLimit-Limit")),
        remaining=_int_or_none(headers.get("X-RateLimit-Remaining")),
        reset=reset_dt,
        retry_after=_int_or_none(headers.get("Retry-After")),
        credits_remaining=_int_or_none(headers.get("X-Credits-Remaining")),
    )


def _is_retryable(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


# 429 codes no retry can fix: the day's or the month's allowance is used up,
# and Retry-After can be most of a day away.
_NON_RETRYABLE_429_CODES = frozenset({"DAILY_LIMIT", "QUOTA_EXCEEDED"})


def _to_typed_error(
    status: int,
    message: str,
    code: str,
    rate_limit: RateLimitInfo,
    headers: Optional[httpx.Headers] = None,
) -> EvaError:
    if code == "RATE_LIMITED":
        return RateLimitError(message, rate_limit.retry_after or 60, rate_limit)
    if code == "QUOTA_EXCEEDED":
        return QuotaExceededError(message, rate_limit)
    if code == "DAILY_LIMIT":
        h = headers if headers is not None else httpx.Headers()
        return DailyLimitError(
            message,
            rate_limit,
            limit=_int_or_none(h.get("X-Daily-Limit")),
            remaining=_int_or_none(h.get("X-Daily-Remaining")),
        )
    if code == "UNAUTHORIZED":
        return AuthenticationError(message)
    if code == "NOT_FOUND":
        return NotFoundError(message)
    return EvaError(message, code=code, status=status, rate_limit=rate_limit)


def request(
    client: httpx.Client,
    api_key: str,
    max_retries: int,
    retry_delay: float,
    *,
    method: str,
    path: str,
    base_url: str,
    json_body: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    raw: bool = False,
) -> Tuple[Any, RateLimitInfo, httpx.Response]:
    """Execute an HTTP request with retry logic.

    Returns a tuple of (parsed_data, rate_limit_info, raw_response).
    """
    url = f"{base_url}{path}"
    headers = {"X-API-Key": api_key, "Accept": "application/json"}

    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        if attempt > 0:
            delay = retry_delay * (2 ** (attempt - 1))
            jitter = delay * random.random() * 0.25
            time.sleep((delay + jitter) / 1000.0)

        try:
            if files:
                resp = client.request(
                    method, url, headers=headers, files=files, data=data, params=params,
                )
            elif json_body is not None:
                resp = client.request(
                    method, url, headers=headers, json=json_body, params=params,
                )
            else:
                resp = client.request(method, url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            last_error = exc
            if attempt < max_retries:
                continue
            raise EvaError(f"Request timed out: {exc}", code="INTERNAL_ERROR", status=0) from exc
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < max_retries:
                continue
            raise EvaError(f"HTTP error: {exc}", code="INTERNAL_ERROR", status=0) from exc

        rate_limit = _parse_rate_limit(resp.headers)

        # Success
        if resp.is_success:
            if raw:
                return resp.text, rate_limit, resp
            body = resp.json()
            return body.get("data"), rate_limit, resp

        # Parse error body
        error_message = "Request failed"
        error_code = "INTERNAL_ERROR"
        try:
            body = resp.json()
            if "error" in body:
                error_message = body["error"]
            if "code" in body:
                error_code = body["code"]
        except Exception:
            pass

        # Retryable? Never a used-up daily or monthly allowance.
        retryable = _is_retryable(resp.status_code) and not (
            resp.status_code == 429 and error_code in _NON_RETRYABLE_429_CODES
        )
        if retryable and attempt < max_retries:
            if resp.status_code == 429 and rate_limit.retry_after:
                server_wait = rate_limit.retry_after * 1000
                our_wait = retry_delay * (2 ** attempt) * (1 + random.random() * 0.25)
                time.sleep(min(server_wait, our_wait) / 1000.0)
            continue

        raise _to_typed_error(resp.status_code, error_message, error_code, rate_limit, resp.headers)

    # Should never reach here
    if last_error:
        raise EvaError(str(last_error), code="INTERNAL_ERROR", status=0)
    raise EvaError("Request failed", code="INTERNAL_ERROR", status=0)
