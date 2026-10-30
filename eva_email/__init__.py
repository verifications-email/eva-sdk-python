"""EVA Email Verification API — Official Python SDK.

Example::

    from eva_email import EvaClient

    eva = EvaClient(api_key="eva_...")
    result = eva.verify("user@example.com")
    print(result.data.risk, result.data.score)
"""

from .client import EvaClient
from .errors import (
    AuthenticationError,
    DailyLimitError,
    EvaError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    WebhookSignatureError,
)
from .models import (
    BatchResult,
    BlacklistEntry,
    BlacklistResult,
    BulkJob,
    BulkJobCompletedEvent,
    BulkJobResult,
    DKIMResult,
    DMARCResult,
    DomainAuth,
    DomainDeliverability,
    EvaResponse,
    RateLimitInfo,
    SPFResult,
    VerificationResult,
    WebhookSummary,
)
from .webhook import parse_webhook_event, verify_webhook_signature

__all__ = [
    # Client
    "EvaClient",
    # Models
    "BatchResult",
    "BlacklistEntry",
    "BlacklistResult",
    "BulkJob",
    "BulkJobCompletedEvent",
    "BulkJobResult",
    "DKIMResult",
    "DMARCResult",
    "DomainAuth",
    "DomainDeliverability",
    "EvaResponse",
    "RateLimitInfo",
    "SPFResult",
    "VerificationResult",
    "WebhookSummary",
    # Errors
    "AuthenticationError",
    "DailyLimitError",
    "EvaError",
    "NotFoundError",
    "QuotaExceededError",
    "RateLimitError",
    "WebhookSignatureError",
    # Webhook utilities
    "parse_webhook_event",
    "verify_webhook_signature",
]
