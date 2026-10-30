"""Exception hierarchy for the EVA Email Verification API SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .models import RateLimitInfo


class EvaError(Exception):
    """Base error for all EVA API errors.

    Attributes:
        message: Human-readable error message.
        code: Machine-readable error code (e.g. ``INVALID_INPUT``).
        status: HTTP status code.
        rate_limit: Rate limit info from the response, if available.
    """

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status: int = 0,
        rate_limit: Optional[RateLimitInfo] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.rate_limit = rate_limit


class RateLimitError(EvaError):
    """Per-minute rate limit exceeded (429 RATE_LIMITED).

    Use ``retry_after`` to know how long to wait.
    """

    def __init__(
        self,
        message: str,
        retry_after: int,
        rate_limit: Optional[RateLimitInfo] = None,
    ) -> None:
        super().__init__(message, code="RATE_LIMITED", status=429, rate_limit=rate_limit)
        self.retry_after = retry_after


class QuotaExceededError(EvaError):
    """Monthly quota exhausted and no PAYG credits remain (429 QUOTA_EXCEEDED).

    The user needs to purchase credit packs or wait for the next billing cycle.
    """

    def __init__(
        self,
        message: str,
        rate_limit: Optional[RateLimitInfo] = None,
    ) -> None:
        super().__init__(message, code="QUOTA_EXCEEDED", status=429, rate_limit=rate_limit)


class DailyLimitError(EvaError):
    """Free plan without credits used its checks for the day (429 DAILY_LIMIT).

    It is never retried: the limit resets at 00:00 UTC, ``retry_after``
    seconds from the response, and any plan or credit pack removes it.
    ``limit`` and ``remaining`` come from ``X-Daily-Limit`` and
    ``X-Daily-Remaining``; ``remaining`` is above 0 when a batch was larger
    than what is left today, and a batch of at most ``remaining`` addresses
    still goes through.
    """

    def __init__(
        self,
        message: str,
        rate_limit: Optional[RateLimitInfo] = None,
        limit: Optional[int] = None,
        remaining: Optional[int] = None,
    ) -> None:
        super().__init__(message, code="DAILY_LIMIT", status=429, rate_limit=rate_limit)
        self.retry_after = rate_limit.retry_after if rate_limit is not None else None
        self.limit = limit
        self.remaining = remaining


class AuthenticationError(EvaError):
    """Invalid or missing API key (401)."""

    def __init__(self, message: str = "Invalid or missing API key") -> None:
        super().__init__(message, code="UNAUTHORIZED", status=401)


class NotFoundError(EvaError):
    """Requested resource not found (404)."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, code="NOT_FOUND", status=404)


class WebhookSignatureError(Exception):
    """Webhook HMAC-SHA256 signature verification failed."""

    def __init__(self, message: str = "Invalid webhook signature") -> None:
        super().__init__(message)
