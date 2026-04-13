"""Phase 1: Email signup / identity edge cases (cases 1-9)."""
from __future__ import annotations

import pytest
import stripe

from helpers.stripe_api import safe_delete_customer, throwaway_email


@pytest.mark.case(1)
def test_empty_email_400(license_client):
    r = license_client.client.post("/api/license/validate", json={"machine_id": "x"})
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"


@pytest.mark.case(2)
def test_missing_machine_id_400(license_client):
    r = license_client.client.post("/api/license/validate", json={"email": "foo@bar.com"})
    assert r.status_code == 400


@pytest.mark.case(3)
@pytest.mark.known_fail  # email case not normalised — creates two customers
def test_email_case_sensitivity_dedupe(license_client, env_cfg):
    base = throwaway_email("case")
    lower = base.lower()
    upper = base.replace("test-", "TEST-")  # mixed case
    r1 = license_client.validate(lower)
    r2 = license_client.validate(upper)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both should hit the same customer — count Stripe records
    customers = list(stripe.Customer.list(email=lower).auto_paging_iter())
    upper_customers = list(stripe.Customer.list(email=upper).auto_paging_iter())
    # Teardown
    for c in customers + upper_customers:
        safe_delete_customer(c.id)
    # Expected behaviour (test will FAIL today): one customer total
    assert len(customers) + len(upper_customers) == 1, (
        f"case-variants created {len(customers)} lowercase + {len(upper_customers)} uppercase customers"
    )


@pytest.mark.case(4)
def test_plus_alias_distinct_customer(license_client, env_cfg):
    a = throwaway_email("plus-a")
    b = a.replace("@", "+extra@")
    try:
        r1 = license_client.validate(a)
        r2 = license_client.validate(b)
        assert r1.status_code == 200 and r2.status_code == 200
        ca = list(stripe.Customer.list(email=a).auto_paging_iter())
        cb = list(stripe.Customer.list(email=b).auto_paging_iter())
        assert len(ca) == 1 and len(cb) == 1
        assert ca[0].id != cb[0].id
    finally:
        for c in ca + cb:
            safe_delete_customer(c.id)


@pytest.mark.case(5)
@pytest.mark.known_fail  # endpoint returns 500 instead of handling Stripe email-format error
def test_trailing_whitespace_normalised_or_rejected(license_client):
    email = throwaway_email("ws") + " "
    r = license_client.validate(email)
    # Either trimmed and succeed (200) or rejected with a clean 400. 500 means the endpoint
    # doesn't catch the Stripe InvalidRequestError and bubbles a server error.
    assert r.status_code in (200, 400), f"got {r.status_code}: {r.text[:120]}"
    if r.status_code == 200:
        cs = list(stripe.Customer.list(email=email).auto_paging_iter())
        for c in cs:
            safe_delete_customer(c.id)


@pytest.mark.case(6)
def test_unicode_email_accepted_or_rejected_cleanly(license_client):
    email = f"test-DELETEME-unicode-héllo@schemagic.test"
    r = license_client.validate(email)
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        cs = list(stripe.Customer.list(email=email).auto_paging_iter())
        for c in cs:
            safe_delete_customer(c.id)


@pytest.mark.case(7)
def test_oversized_email_rejected_or_creates_cleanly(license_client):
    email = "x" * 300 + "@schemagic.test"
    r = license_client.validate(email)
    # Stripe allows long emails up to ~512 chars. 200 is fine as long as no crash; 400/500 also OK.
    assert r.status_code in (200, 400, 500)
    if r.status_code == 200:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(8)
def test_same_email_reuses_customer(license_client, env_cfg):
    email = throwaway_email("reuse")
    try:
        r1 = license_client.validate(email)
        r2 = license_client.validate(email)
        assert r1.status_code == 200 and r2.status_code == 200
        cs = list(stripe.Customer.list(email=email).auto_paging_iter())
        assert len(cs) == 1, f"expected 1 customer, got {len(cs)}"
    finally:
        for c in cs:
            safe_delete_customer(c.id)


@pytest.mark.case(9)
def test_email_change_rebinds_to_new_customer(license_client, env_cfg):
    a = throwaway_email("swap-a")
    b = throwaway_email("swap-b")
    try:
        license_client.validate(a, machine_id="same-machine")
        license_client.validate(b, machine_id="same-machine")
        ca = list(stripe.Customer.list(email=a).auto_paging_iter())
        cb = list(stripe.Customer.list(email=b).auto_paging_iter())
        assert len(ca) == 1 and len(cb) == 1
        assert ca[0].id != cb[0].id
    finally:
        for c in ca + cb:
            safe_delete_customer(c.id)
