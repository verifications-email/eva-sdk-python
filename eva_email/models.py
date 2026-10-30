"""Response models for the EVA Email Verification API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, List, Literal, Optional, TypeVar

import httpx

# ── Literal union types ─────────────────────────────────────────

Risk = Literal["safe", "risky", "catchall", "invalid", "unknown"]
SmtpCheck = Literal["deliverable", "undeliverable", "risky", "unknown"]
SpamTrapRisk = Literal["low", "medium", "high"]
Grade = Literal["A", "B", "C", "D", "F"]
BulkJobStatus = Literal["pending", "processing", "completed", "failed"]
ErrorCode = Literal[
    "INVALID_INPUT",
    "UNAUTHORIZED",
    "FORBIDDEN",
    "PAID_PLAN_REQUIRED",
    "RATE_LIMITED",
    "QUOTA_EXCEEDED",
    "DAILY_LIMIT",
    "NOT_FOUND",
    "INTERNAL_ERROR",
]

# ── Rate limit info ─────────────────────────────────────────────

T = TypeVar("T")


@dataclass(frozen=True)
class RateLimitInfo:
    """Rate limit information parsed from response headers."""

    limit: Optional[int] = None
    """Requests allowed per minute."""
    remaining: Optional[int] = None
    """Requests remaining in current window."""
    reset: Optional[datetime] = None
    """When the rate limit window resets."""
    retry_after: Optional[int] = None
    """Seconds to wait before retrying (from Retry-After header)."""
    credits_remaining: Optional[int] = None
    """PAYG credits remaining (only present when credits were deducted)."""


@dataclass(frozen=True)
class EvaResponse(Generic[T]):
    """Wrapper returned by every SDK method."""

    data: T
    """The parsed response payload."""
    rate_limit: RateLimitInfo
    """Rate limit information from response headers."""
    http_response: httpx.Response
    """The raw httpx Response for advanced use."""


# ── Verification result ─────────────────────────────────────────


@dataclass
class VerificationResult:
    """Full email verification result."""

    email: str
    score: int
    """Composite deliverability score (0–100)."""
    risk: str  # Risk literal
    syntax_valid: bool
    mx_found: bool
    smtp_check: str  # SmtpCheck literal
    is_disposable: bool
    is_role_account: bool
    is_catch_all: bool
    is_free_provider: bool
    spam_trap_risk: str  # SpamTrapRisk literal
    reason: Optional[str] = None
    """Why the verdict landed where it did (e.g. 'catch_all', 'no_mx',
    'greylisted'); None for a plain deliverable."""
    suggested_correction: Optional[str] = None
    """Suggested domain correction (e.g. 'gmail.com' for 'gmial.com')."""
    domain_reputation_score: Optional[int] = None
    mx_records: List[str] = field(default_factory=list)
    deliverability: Optional[DomainDeliverability] = None
    smtp_provider: Optional[str] = None
    is_disabled: Optional[bool] = None
    is_locked: Optional[bool] = None
    """The provider reported the account locked (temporary or permanent lockout)."""
    is_full_inbox: Optional[bool] = None
    is_tarpitted: Optional[bool] = None
    response_latency_ms: Optional[int] = None
    banner_provider: Optional[str] = None
    is_default_catch_all: Optional[bool] = None
    is_dbeb: Optional[bool] = None
    """Double Bounce Email Box detection."""
    is_accept_all: Optional[bool] = None


# ── Batch ────────────────────────────────────────────────────────


@dataclass
class BatchResult:
    """Result of a batch verification request."""

    total: int
    results: List[VerificationResult]


# ── Bulk jobs ────────────────────────────────────────────────────


@dataclass
class BulkJob:
    """Async bulk verification job."""

    id: str
    api_key_id: str
    status: str  # BulkJobStatus literal
    total_count: int
    completed_count: int
    created_at: str
    completed_at: Optional[str] = None
    file_url: Optional[str] = None
    result_url: Optional[str] = None
    webhook_url: Optional[str] = None


@dataclass
class BulkJobResult:
    """Single result from a bulk verification job."""

    email: str
    score: int
    risk: str
    smtp_check: str
    is_disposable: bool
    is_role_account: bool
    is_catch_all: bool
    is_free_provider: bool
    spam_trap_risk: str
    domain_reputation_score: Optional[int] = None
    suggested_correction: Optional[str] = None
    is_locked: Optional[bool] = None
    """The provider reported the account locked (temporary or permanent lockout).
    None on jobs that finished before Oct 14 2026."""


# ── Domain deliverability ────────────────────────────────────────


@dataclass
class SPFResult:
    found: bool
    record: Optional[str] = None
    strictness: Optional[str] = None


@dataclass
class DKIMResult:
    found: bool
    selectors: Optional[List[str]] = None


@dataclass
class DMARCResult:
    found: bool
    record: Optional[str] = None
    policy: Optional[str] = None


@dataclass
class DomainAuth:
    spf: SPFResult
    dkim: DKIMResult
    dmarc: DMARCResult


@dataclass
class BlacklistEntry:
    zone: str
    ip: str


@dataclass
class BlacklistResult:
    listed: bool
    listed_count: int
    total_checks: int
    listings: Optional[List[BlacklistEntry]] = None


@dataclass
class DomainDeliverability:
    """Domain deliverability report."""

    domain: str
    score: int
    """Overall deliverability score (0–100)."""
    grade: str  # Grade literal
    has_mx: bool
    checked_at: str
    authentication: Optional[DomainAuth] = None
    blacklist: Optional[BlacklistResult] = None
    reputation_score: Optional[int] = None


# ── Webhook events ───────────────────────────────────────────────


@dataclass
class WebhookSummary:
    safe: int
    risky: int
    catchall: int
    invalid: int
    unknown: int


@dataclass
class BulkJobCompletedEvent:
    """Webhook payload for bulk job completion."""

    event: str
    job_id: str
    status: str
    total_count: int
    completed_count: int
    summary: WebhookSummary
    result_url: str
    timestamp: str


# ── Parsing helpers ──────────────────────────────────────────────


def _parse_spf(data: Optional[dict[str, Any]]) -> Optional[SPFResult]:
    if not data:
        return None
    return SPFResult(
        found=data.get("found", False),
        record=data.get("record"),
        strictness=data.get("strictness"),
    )


def _parse_dkim(data: Optional[dict[str, Any]]) -> Optional[DKIMResult]:
    if not data:
        return None
    return DKIMResult(
        found=data.get("found", False),
        selectors=data.get("selectors"),
    )


def _parse_dmarc(data: Optional[dict[str, Any]]) -> Optional[DMARCResult]:
    if not data:
        return None
    return DMARCResult(
        found=data.get("found", False),
        record=data.get("record"),
        policy=data.get("policy"),
    )


def _parse_domain_auth(data: Optional[dict[str, Any]]) -> Optional[DomainAuth]:
    if not data:
        return None
    return DomainAuth(
        spf=_parse_spf(data.get("spf")) or SPFResult(found=False),
        dkim=_parse_dkim(data.get("dkim")) or DKIMResult(found=False),
        dmarc=_parse_dmarc(data.get("dmarc")) or DMARCResult(found=False),
    )


def _parse_blacklist(data: Optional[dict[str, Any]]) -> Optional[BlacklistResult]:
    if not data:
        return None
    listings = None
    if data.get("listings"):
        listings = [
            BlacklistEntry(zone=e.get("zone", ""), ip=e.get("ip", ""))
            for e in data["listings"]
        ]
    return BlacklistResult(
        listed=data.get("listed", False),
        listed_count=data.get("listed_count", 0),
        total_checks=data.get("total_checks", 0),
        listings=listings,
    )


def _parse_deliverability(data: Optional[dict[str, Any]]) -> Optional[DomainDeliverability]:
    if not data:
        return None
    return DomainDeliverability(
        domain=data.get("domain", ""),
        score=data.get("score", 0),
        grade=data.get("grade", "F"),
        has_mx=data.get("has_mx", False),
        checked_at=data.get("checked_at", ""),
        authentication=_parse_domain_auth(data.get("authentication")),
        blacklist=_parse_blacklist(data.get("blacklist")),
        reputation_score=data.get("reputation_score"),
    )


def parse_verification_result(data: dict[str, Any]) -> VerificationResult:
    """Parse a raw JSON dict into a VerificationResult."""
    return VerificationResult(
        email=data.get("email", ""),
        score=data.get("score", 0),
        risk=data.get("risk", "invalid"),
        syntax_valid=data.get("syntax_valid", False),
        mx_found=data.get("mx_found", False),
        smtp_check=data.get("smtp_check", "unknown"),
        is_disposable=data.get("is_disposable", False),
        is_role_account=data.get("is_role_account", False),
        is_catch_all=data.get("is_catch_all", False),
        is_free_provider=data.get("is_free_provider", False),
        spam_trap_risk=data.get("spam_trap_risk", "low"),
        reason=data.get("reason"),
        suggested_correction=data.get("suggested_correction"),
        domain_reputation_score=data.get("domain_reputation_score"),
        mx_records=data.get("mx_records") or [],
        deliverability=_parse_deliverability(data.get("deliverability")),
        smtp_provider=data.get("smtp_provider"),
        is_disabled=data.get("is_disabled"),
        is_locked=data.get("is_locked"),
        is_full_inbox=data.get("is_full_inbox"),
        is_tarpitted=data.get("is_tarpitted"),
        response_latency_ms=data.get("response_latency_ms"),
        banner_provider=data.get("banner_provider"),
        is_default_catch_all=data.get("is_default_catch_all"),
        is_dbeb=data.get("is_dbeb"),
        is_accept_all=data.get("is_accept_all"),
    )


def parse_bulk_job(data: dict[str, Any]) -> BulkJob:
    """Parse a raw JSON dict into a BulkJob."""
    return BulkJob(
        id=data.get("id", ""),
        api_key_id=data.get("api_key_id", ""),
        status=data.get("status", "pending"),
        total_count=data.get("total_count", 0),
        completed_count=data.get("completed_count", 0),
        created_at=data.get("created_at", ""),
        completed_at=data.get("completed_at"),
        file_url=data.get("file_url"),
        result_url=data.get("result_url"),
        webhook_url=data.get("webhook_url"),
    )


def parse_bulk_job_result(data: dict[str, Any]) -> BulkJobResult:
    """Parse a raw JSON dict into a BulkJobResult."""
    return BulkJobResult(
        email=data.get("email", ""),
        score=data.get("score", 0),
        risk=data.get("risk", "invalid"),
        smtp_check=data.get("smtp_check", "unknown"),
        is_disposable=data.get("is_disposable", False),
        is_role_account=data.get("is_role_account", False),
        is_catch_all=data.get("is_catch_all", False),
        is_free_provider=data.get("is_free_provider", False),
        spam_trap_risk=data.get("spam_trap_risk", "low"),
        domain_reputation_score=data.get("domain_reputation_score"),
        suggested_correction=data.get("suggested_correction"),
        is_locked=data.get("is_locked"),
    )
