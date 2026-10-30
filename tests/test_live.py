"""Live integration tests for the verifications-email Python SDK.

Mirrors the JS/TS test-live.mjs — tests against a running EVA API instance.

Usage:
    EVA_BASE_URL=http://eva-api:8080 python tests/test_live.py
"""

from __future__ import annotations

import os
import sys
import uuid

# Allow running from sdk/python/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eva_email import EvaClient, EvaError, AuthenticationError, NotFoundError

API_KEY = os.environ.get("EVA_API_KEY") or sys.exit("Set EVA_API_KEY to run live tests.")
BASE_URL = os.environ.get("EVA_BASE_URL", "http://eva-api:8080")

passed = 0
failed = 0


def check(condition: bool, label: str) -> None:
    global passed, failed
    if condition:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label}")
        failed += 1


def main() -> None:
    global passed, failed

    eva = EvaClient(api_key=API_KEY, base_url=BASE_URL, timeout=20.0, max_retries=1)

    # ── Test 1: Single email verification ───────────────────
    print("\n[Test 1] Single email verification (POST /api/v1/verify)")
    try:
        result = eva.verify("test@gmail.com")
        d = result.data
        check(isinstance(d.email, str), "email is str")
        check(isinstance(d.score, int), "score is int")
        check(d.risk in ("safe", "risky", "catchall", "invalid", "unknown"), f'risk is valid: "{d.risk}"')
        check(d.smtp_check in ("deliverable", "undeliverable", "risky", "unknown"), f'smtp_check is valid: "{d.smtp_check}"')
        check(isinstance(d.syntax_valid, bool), "syntax_valid is bool")
        check(isinstance(d.mx_found, bool), "mx_found is bool")
        check(isinstance(d.is_disposable, bool), "is_disposable is bool")
        check(isinstance(d.is_role_account, bool), "is_role_account is bool")
        check(isinstance(d.is_catch_all, bool), "is_catch_all is bool")
        check(isinstance(d.is_free_provider, bool), "is_free_provider is bool")
        check(isinstance(d.mx_records, list), "mx_records is list")
        rl = result.rate_limit
        check(rl.limit is not None, f"rate_limit.limit = {rl.limit}")
        check(rl.remaining is not None, f"rate_limit.remaining = {rl.remaining}")
        check(rl.reset is not None, "rate_limit.reset is set")
        print(f"  Score: {d.score}, Risk: {d.risk}, SMTP: {d.smtp_check}")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    # ── Test 2: Invalid email syntax ────────────────────────
    print("\n[Test 2] Invalid email syntax")
    try:
        result = eva.verify("not-an-email")
        check(result.data.syntax_valid is False, "syntax_valid is False for invalid email")
        check(result.data.risk == "invalid", f'risk is "invalid": "{result.data.risk}"')
    except EvaError as e:
        if e.status == 400:
            print("  PASS: API returned 400 for invalid email (expected)")
            passed += 1
        else:
            print(f"  ERROR: {e}")
            failed += 1

    # ── Test 3: Disposable email detection ──────────────────
    print("\n[Test 3] Disposable email detection")
    try:
        result = eva.verify("test@mailinator.com")
        check(result.data.is_disposable is True, "mailinator detected as disposable")
        print(f"  Score: {result.data.score}, Disposable: {result.data.is_disposable}")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    # ── Test 4: Catch-all verdict is first-class ────────────
    print("\n[Test 4] Catch-all verdict (random local part @google.com)")
    try:
        token = "zz" + uuid.uuid4().hex[:10]
        d = eva.verify(f"{token}@google.com").data
        check(d.is_catch_all is True, f"is_catch_all True: {d.is_catch_all}")
        check(d.risk == "catchall", f'risk is "catchall": "{d.risk}"')
        check(d.reason == "catch_all", f'reason is "catch_all": "{d.reason}"')
        check(40 <= d.score <= 69, f"score in the 40-69 band: {d.score}")
        print(f"  Score: {d.score}, Risk: {d.risk}, Reason: {d.reason}")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    # ── Test 5: Batch verification ──────────────────────────
    print("\n[Test 5] Batch verification (POST /api/v1/verify/batch)")
    try:
        result = eva.verify_batch(["test@gmail.com", "fake@nonexistent-domain-xyz123.com"])
        d = result.data
        check(d.total == 2, f"total is 2: {d.total}")
        check(isinstance(d.results, list), "results is list")
        check(len(d.results) == 2, f"results length is 2: {len(d.results)}")
        for r in d.results:
            check(isinstance(r.email, str), f"result has email: {r.email}")
            check(isinstance(r.score, int), f"result has score: {r.score}")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    # ── Test 6: Client-side batch validation ────────────────
    print("\n[Test 6] Client-side batch limit validation")
    try:
        eva.verify_batch([])
        print("  FAIL: Should have raised for empty list")
        failed += 1
    except EvaError as e:
        check(e.code == "INVALID_INPUT", f'code is INVALID_INPUT: "{e.code}"')

    try:
        eva.verify_batch([f"test{i}@example.com" for i in range(101)])
        print("  FAIL: Should have raised for >100 emails")
        failed += 1
    except EvaError as e:
        check(e.code == "INVALID_INPUT", f'code is INVALID_INPUT: "{e.code}"')

    # ── Test 7: Domain deliverability ───────────────────────
    print("\n[Test 7] Domain deliverability (GET /api/v1/domain/:domain/deliverability)")
    try:
        result = eva.get_domain_deliverability("gmail.com")
        d = result.data
        check(d.domain == "gmail.com", f'domain is gmail.com: "{d.domain}"')
        check(isinstance(d.score, int), f"score is int: {d.score}")
        check(d.grade in ("A", "B", "C", "D", "F"), f'grade is valid: "{d.grade}"')
        check(d.has_mx is True, "gmail.com has MX")
        if d.authentication:
            check(d.authentication.spf.found is True, "gmail.com has SPF")
        print(f"  Score: {d.score}, Grade: {d.grade}")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    # ── Test 8: Invalid API key ─────────────────────────────
    print("\n[Test 8] Authentication error with invalid API key")
    try:
        bad_client = EvaClient(api_key="eva_invalid_key_here", base_url=BASE_URL, max_retries=0)
        bad_client.verify("test@gmail.com")
        print("  FAIL: Should have raised AuthenticationError")
        failed += 1
    except EvaError as e:
        check(isinstance(e, AuthenticationError) or e.status == 401, "raises auth error")
        check(e.status == 401, f"status is 401: {e.status}")
        check(e.code == "UNAUTHORIZED", f'code is UNAUTHORIZED: "{e.code}"')

    # ── Test 9: List bulk jobs ──────────────────────────────
    print("\n[Test 9] List bulk jobs (GET /api/v1/verify/async)")
    try:
        result = eva.list_bulk_jobs()
        check(isinstance(result.data, list), "returns list")
        print(f"  Found {len(result.data)} bulk jobs")
        passed += 1
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    # ── Test 10: Get non-existent bulk job ──────────────────
    print("\n[Test 10] Get non-existent bulk job (404)")
    try:
        eva.get_bulk_job("00000000-0000-0000-0000-000000000000")
        print("  FAIL: Should have raised NotFoundError")
        failed += 1
    except EvaError as e:
        check(isinstance(e, NotFoundError) or e.status == 404, "raises not found error")
        check(e.status == 404, f"status is 404: {e.status}")

    # ── Test 11: Context manager ────────────────────────────
    print("\n[Test 11] Context manager support")
    try:
        with EvaClient(api_key=API_KEY, base_url=BASE_URL, max_retries=1) as client:
            r = client.verify("test@gmail.com")
            check(isinstance(r.data.email, str), "works inside context manager")
        check(True, "context manager exited cleanly")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    eva.close()

    # ── Summary ─────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 50}")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
