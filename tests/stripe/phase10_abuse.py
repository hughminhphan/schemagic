"""Phase 10: Abuse / security (cases 76-80)."""
from __future__ import annotations

import concurrent.futures as _cf

import pytest
import stripe

from helpers.stripe_api import safe_delete_customer, throwaway_email


@pytest.mark.case(76)
def test_email_cycling_resets_free_tier(license_client):
    """Known product limitation: new email = new 3 free gens. Test documents behaviour."""
    emails = [throwaway_email(f"abuse-{i}") for i in range(3)]
    try:
        for email in emails:
            r = license_client.validate(email, machine_id="same-machine-id")
            assert r.status_code == 200
            assert r.json()["generationsUsed"] == 1
    finally:
        for email in emails:
            for c in stripe.Customer.list(email=email).auto_paging_iter():
                safe_delete_customer(c.id)


@pytest.mark.case(77)
def test_disposable_email_accepted(license_client):
    """Currently no email provider blocklist."""
    email = throwaway_email("mailinator")  # treat as proxy for disposable providers
    try:
        r = license_client.validate(email)
        assert r.status_code == 200
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(78)
def test_rapid_validate_no_throttle(license_client):
    """Ensures no app-level rate limit on validate. Stripe's 25 rps is the floor."""
    email = throwaway_email("dos")
    try:
        # Fire 10 validates rapidly — all should succeed (stripe rate limit not tripped)
        with _cf.ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(lambda _: license_client.validate(email), range(10)))
        success = sum(1 for r in results if r.status_code == 200)
        assert success >= 8, f"only {success}/10 succeeded — unexpected throttling or rate limit"
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(80)
def test_api_key_mode_matches_expected(env_cfg):
    """Hard assertion: we're in test mode. Live-mode smoke tests would be in a prod-only harness."""
    assert stripe.api_key.startswith("sk_test_"), "must run against sk_test_ keys only"
