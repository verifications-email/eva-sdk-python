"""Standalone webhook signature verification for EVA webhooks.

Uses only Python stdlib — no external dependencies required.

Example::

    from eva_email import verify_webhook_signature

    is_valid = verify_webhook_signature(
        payload=request.body,
        signature=request.headers["X-EVA-Signature"],
        secret=os.environ["EVA_WEBHOOK_SECRET"],
    )
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict, Union

from .errors import WebhookSignatureError


def verify_webhook_signature(
    payload: Union[str, bytes],
    signature: str,
    secret: str,
) -> bool:
    """Verify the HMAC-SHA256 signature of an incoming EVA webhook.

    Args:
        payload: Raw request body (string or bytes).
        signature: Value of the ``X-EVA-Signature`` header.
        secret: Your webhook signing secret.

    Returns:
        ``True`` if the signature is valid, ``False`` otherwise.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def parse_webhook_event(
    payload: Union[str, bytes],
    signature: str,
    secret: str,
) -> Dict[str, Any]:
    """Verify the signature and parse the webhook payload in one step.

    Args:
        payload: Raw request body (string or bytes).
        signature: Value of the ``X-EVA-Signature`` header.
        secret: Your webhook signing secret.

    Returns:
        Parsed event payload as a dictionary.

    Raises:
        WebhookSignatureError: If the signature is invalid.
    """
    if not verify_webhook_signature(payload, signature, secret):
        raise WebhookSignatureError()

    body = payload if isinstance(payload, str) else payload.decode("utf-8")
    return json.loads(body)  # type: ignore[no-any-return]
