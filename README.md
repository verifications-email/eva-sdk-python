# eva-email

Official Python SDK for the **EVA Email Verification API**.

Single dependency (`httpx`). Works with Python 3.9+. Fully typed (`py.typed`).

## Installation

```bash
pip install eva-email
```

## Quick Start

```python
from eva_email import EvaClient

eva = EvaClient(api_key="eva_...")

result = eva.verify("user@example.com")

print(result.data.score)          # 85
print(result.data.risk)           # "safe"
print(result.data.smtp_check)     # "deliverable"
print(result.data.is_disposable)  # False
print(result.rate_limit.remaining)  # 199
```

## Features

- Single email verification
- Batch verification (up to 100 emails)
- Async bulk file upload (CSV/XLSX) with polling
- Domain deliverability reports (SPF/DKIM/DMARC/blacklists)
- Webhook signature verification (HMAC-SHA256)
- Auto-retry with exponential backoff on 429/5xx
- Rate limit info on every response
- Full type annotations (PEP 561)

## API Reference

### Constructor

```python
eva = EvaClient(
    api_key="eva_...",                        # Required
    base_url="https://verifications.email",     # Default
    timeout=30.0,                             # Seconds (default: 30)
    max_retries=3,                            # Retries on 429/5xx (default: 3)
    retry_delay=1000.0,                       # Base retry delay in ms (default: 1000)
)
```

### Context Manager

```python
with EvaClient(api_key="eva_...") as eva:
    result = eva.verify("user@example.com")
# Client is automatically closed
```

### Single Verification

```python
result = eva.verify("user@gmail.com")

print(result.data.email)                  # "user@gmail.com"
print(result.data.score)                  # 0-100
print(result.data.risk)                   # "safe" | "risky" | "invalid"
print(result.data.smtp_check)             # "deliverable" | "undeliverable" | "risky" | "unknown"
print(result.data.is_disposable)          # False
print(result.data.is_role_account)        # False
print(result.data.is_catch_all)           # False
print(result.data.is_free_provider)       # True
print(result.data.spam_trap_risk)         # "low" | "medium" | "high"
print(result.data.suggested_correction)   # None or "gmail.com"
print(result.data.mx_records)             # ["aspmx.l.google.com", ...]
```

### Batch Verification

```python
result = eva.verify_batch([
    "user1@gmail.com",
    "user2@company.com",
    "fake@disposable.xyz",
])

print(result.data.total)  # 3
for r in result.data.results:
    print(r.email, r.risk, r.score)
```

### Bulk File Upload + Polling

```python
# Upload the file
with open("emails.csv", "rb") as f:
    job = eva.upload_bulk(f, webhook_url="https://myapp.com/webhook/eva")

print(job.data.id)      # "abc-123"
print(job.data.status)  # "pending"

# Poll until complete
completed = eva.wait_for_bulk_job(
    job.data.id,
    interval=3.0,   # poll every 3s (default: 5s)
    timeout=300.0,   # max wait 5min (default: 10min)
    on_progress=lambda j: print(f"{j.completed_count}/{j.total_count} processed"),
)

# Download results as typed objects
results = eva.get_bulk_job_results(completed.data.id)
for r in results.data:
    print(r.email, r.risk, r.score)

# Or download as CSV string
csv_data = eva.get_bulk_job_results(completed.data.id, format="csv")
with open("results.csv", "w") as f:
    f.write(csv_data)
```

### Domain Deliverability

```python
result = eva.get_domain_deliverability("example.com")

print(result.data.score)                          # 85
print(result.data.grade)                          # "A"
print(result.data.authentication.spf.found)       # True
print(result.data.authentication.dkim.found)      # True
print(result.data.authentication.dmarc.policy)    # "reject"
print(result.data.blacklist.listed)               # False
```

### Bulk Job Management

```python
# List all jobs
jobs = eva.list_bulk_jobs()

# Get specific job status
job = eva.get_bulk_job("job-id-123")
```

## Webhook Verification

Verify incoming webhook signatures without instantiating the client:

```python
from eva_email import verify_webhook_signature, parse_webhook_event

# Option 1: Verify only
is_valid = verify_webhook_signature(
    payload=raw_body,
    signature=headers["X-EVA-Signature"],
    secret=os.environ["EVA_WEBHOOK_SECRET"],
)

# Option 2: Verify + parse in one step
event = parse_webhook_event(
    payload=raw_body,
    signature=headers["X-EVA-Signature"],
    secret=os.environ["EVA_WEBHOOK_SECRET"],
)

print(event["job_id"])
print(event["summary"])  # {"safe": 800, "risky": 150, "invalid": 50}
```

### Flask Example

```python
from flask import Flask, request
from eva_email import parse_webhook_event, WebhookSignatureError

app = Flask(__name__)

@app.post("/webhook/eva")
def handle_webhook():
    try:
        event = parse_webhook_event(
            payload=request.get_data(as_text=True),
            signature=request.headers["X-EVA-Signature"],
            secret=os.environ["EVA_WEBHOOK_SECRET"],
        )
        print(f"Job {event['job_id']} completed:", event["summary"])
        return "", 200
    except WebhookSignatureError:
        return "Invalid signature", 401
```

## Error Handling

All API errors are raised as typed exceptions:

```python
from eva_email import (
    EvaClient,
    EvaError,
    RateLimitError,
    QuotaExceededError,
    AuthenticationError,
    NotFoundError,
)

eva = EvaClient(api_key="eva_...")

try:
    result = eva.verify("test@example.com")
except RateLimitError as e:
    # Per-minute rate limit hit — wait and retry
    print(f"Rate limited. Retry after {e.retry_after}s")
    print(f"Remaining: {e.rate_limit.remaining}")
except QuotaExceededError:
    # Monthly quota exhausted, no PAYG credits left
    print("Quota exceeded. Purchase credit packs to continue.")
except AuthenticationError:
    # Invalid or missing API key
    print("Check your API key")
except NotFoundError:
    # Resource not found (e.g., invalid bulk job ID)
    print("Not found")
except EvaError as e:
    # Other API error
    print(e.message, e.code, e.status)
```

## Rate Limit Info

Every response includes rate limit data:

```python
result = eva.verify("user@example.com")

print(result.rate_limit.limit)              # 200 (per-minute limit)
print(result.rate_limit.remaining)          # 199
print(result.rate_limit.reset)              # datetime object (UTC)
print(result.rate_limit.credits_remaining)  # None or int (PAYG credits)
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api_key` | `str` | — | **Required.** Your EVA API key. |
| `base_url` | `str` | `https://verifications.email` | API base URL. |
| `timeout` | `float` | `30.0` | Request timeout (seconds). |
| `max_retries` | `int` | `3` | Max retries on 429/5xx errors. |
| `retry_delay` | `float` | `1000.0` | Base delay (ms) for exponential backoff. |

## Requirements

- Python >= 3.9
- httpx >= 0.27

## License

MIT
