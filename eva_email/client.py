"""EVA Email Verification API client."""

from __future__ import annotations

from typing import Any, BinaryIO, Callable, Dict, List, Optional, Union
from urllib.parse import quote

import httpx

from . import _http
from .errors import EvaError
from .models import (
    BatchResult,
    BulkJob,
    BulkJobResult,
    DomainDeliverability,
    EvaResponse,
    RateLimitInfo,
    VerificationResult,
    parse_bulk_job,
    parse_bulk_job_result,
    parse_verification_result,
    _parse_deliverability,
)
from .polling import poll_bulk_job

_DEFAULT_BASE_URL = "https://verifications.email"


class EvaClient:
    """EVA Email Verification API client.

    Example::

        from eva_email import EvaClient

        eva = EvaClient(api_key="eva_...")
        result = eva.verify("user@example.com")
        print(result.data.risk, result.data.score, result.rate_limit.remaining)

    Can also be used as a context manager::

        with EvaClient(api_key="eva_...") as eva:
            result = eva.verify("user@example.com")
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 100.0,
        max_retries: int = 3,
        retry_delay: float = 1000.0,
    ) -> None:
        """Initialize the EVA client.

        Args:
            api_key: Your EVA API key (starts with ``eva_``).
            base_url: API base URL. Default: ``https://verifications.email``.
            timeout: Request timeout in seconds. Default: ``100``: a check can
                take up to 90 s when the mail server holds its reply.
            max_retries: Max retries on 429/5xx. Default: ``3``.
            retry_delay: Base delay between retries in ms. Default: ``1000``.
        """
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> EvaClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def _request(self, **kwargs: Any) -> EvaResponse[Any]:
        data, rate_limit, resp = _http.request(
            self._client,
            self._api_key,
            self._max_retries,
            self._retry_delay,
            base_url=self._base_url,
            **kwargs,
        )
        return EvaResponse(data=data, rate_limit=rate_limit, http_response=resp)

    # ── Single verification ─────────────────────────────────────

    def verify(self, email: str) -> EvaResponse[VerificationResult]:
        """Verify a single email address.

        Returns the full verification result with deliverability score,
        risk level, SMTP check, disposable/role/catch-all detection, and more.
        """
        raw = self._request(method="POST", path="/api/v1/verify", json_body={"email": email})
        return EvaResponse(
            data=parse_verification_result(raw.data),
            rate_limit=raw.rate_limit,
            http_response=raw.http_response,
        )

    # ── Batch verification ──────────────────────────────────────

    def verify_batch(self, emails: List[str]) -> EvaResponse[BatchResult]:
        """Verify a batch of emails synchronously (up to 100).

        Each email counts as one verification toward your quota.
        """
        if not emails:
            raise EvaError("At least one email is required", code="INVALID_INPUT", status=400)
        if len(emails) > 100:
            raise EvaError("Batch size cannot exceed 100 emails", code="INVALID_INPUT", status=400)

        raw = self._request(method="POST", path="/api/v1/verify/batch", json_body={"emails": emails})
        results = [parse_verification_result(r) for r in raw.data.get("results", [])]
        return EvaResponse(
            data=BatchResult(total=raw.data.get("total", len(results)), results=results),
            rate_limit=raw.rate_limit,
            http_response=raw.http_response,
        )

    # ── Async bulk jobs ─────────────────────────────────────────

    def upload_bulk(
        self,
        file: Union[BinaryIO, bytes],
        *,
        webhook_url: Optional[str] = None,
        filename: str = "upload.csv",
    ) -> EvaResponse[BulkJob]:
        """Upload a CSV or XLSX file for async bulk verification.

        Args:
            file: File-like object or bytes containing the email list.
            webhook_url: HTTPS URL to receive a webhook when the job completes.
            filename: Override the filename in the multipart upload.

        Returns:
            The created bulk job (status will be ``pending``).
        """
        if isinstance(file, bytes):
            file_tuple = (filename, file, "text/csv")
        else:
            file_tuple = (filename, file, "text/csv")

        files = {"file": file_tuple}
        form_data: Optional[Dict[str, str]] = None
        if webhook_url:
            form_data = {"webhook_url": webhook_url}

        raw = self._request(
            method="POST",
            path="/api/v1/verify/async/upload",
            files=files,
            data=form_data,
        )
        return EvaResponse(
            data=parse_bulk_job(raw.data),
            rate_limit=raw.rate_limit,
            http_response=raw.http_response,
        )

    def list_bulk_jobs(self) -> EvaResponse[List[BulkJob]]:
        """List all bulk jobs for the current API key."""
        raw = self._request(method="GET", path="/api/v1/verify/async")
        jobs = [parse_bulk_job(j) for j in (raw.data or [])]
        return EvaResponse(
            data=jobs,
            rate_limit=raw.rate_limit,
            http_response=raw.http_response,
        )

    def get_bulk_job(self, job_id: str) -> EvaResponse[BulkJob]:
        """Get the status of a specific bulk job."""
        raw = self._request(method="GET", path=f"/api/v1/verify/async/{quote(job_id, safe='')}")
        return EvaResponse(
            data=parse_bulk_job(raw.data),
            rate_limit=raw.rate_limit,
            http_response=raw.http_response,
        )

    def get_bulk_job_results(
        self,
        job_id: str,
        format: str = "json",
    ) -> Union[EvaResponse[List[BulkJobResult]], str]:
        """Get the results of a completed bulk job.

        Args:
            job_id: The bulk job ID.
            format: ``"json"`` (default) returns typed results, ``"csv"`` returns raw CSV.
        """
        path = f"/api/v1/verify/async/{quote(job_id, safe='')}/result"
        if format == "csv":
            raw = self._request(method="GET", path=path, params={"format": "csv"}, raw=True)
            return raw.data
        raw = self._request(method="GET", path=path)
        results = [parse_bulk_job_result(r) for r in (raw.data or [])]
        return EvaResponse(
            data=results,
            rate_limit=raw.rate_limit,
            http_response=raw.http_response,
        )

    def wait_for_bulk_job(
        self,
        job_id: str,
        *,
        interval: float = 5.0,
        timeout: float = 600.0,
        on_progress: Optional[Callable[[BulkJob], None]] = None,
    ) -> EvaResponse[BulkJob]:
        """Poll a bulk job until it completes or fails.

        Args:
            job_id: The bulk job ID to poll.
            interval: Seconds between polls (default: 5).
            timeout: Max wait time in seconds (default: 600).
            on_progress: Called after each poll with the current job state.
        """
        return poll_bulk_job(self.get_bulk_job, job_id, interval, timeout, on_progress)

    # ── Domain deliverability ───────────────────────────────────

    def get_domain_deliverability(self, domain: str) -> EvaResponse[DomainDeliverability]:
        """Get a domain deliverability report.

        Checks SPF, DKIM, DMARC, MX records, and DNSBL blacklists.
        Counts as one verification toward your quota.
        """
        raw = self._request(
            method="GET",
            path=f"/api/v1/domain/{quote(domain, safe='')}/deliverability",
        )
        parsed = _parse_deliverability(raw.data)
        if parsed is None:
            raise EvaError("Failed to parse deliverability response", code="INTERNAL_ERROR", status=0)
        return EvaResponse(
            data=parsed,
            rate_limit=raw.rate_limit,
            http_response=raw.http_response,
        )
