"""Phase 12: Production war stories surfaced during research (cases 81-85)."""
from __future__ import annotations

import concurrent.futures as _cf
import json
import time

import pytest
import stripe

from helpers.stripe_api import (
    create_active_sub,
    make_fake_event,
    safe_delete_customer,
    sign_webhook_payload,
    throwaway_email,
)


@pytest.mark.case(81)
@pytest.mark.xfail(reason="Bug 5: customers.list race; idempotency-key-on-create rejected due to Stripe ghost-cache. Full fix needs Redis SETNX lock.", strict=False)
@pytest.mark.known_fail  # getOrCreateCustomer has no lock — parallel calls create duplicates
def test_duplicate_customer_race(license_client):
    """Two simultaneous validates with same fresh email → should yield one customer."""
    email = throwaway_email("p12-81")
    try:
        with _cf.ThreadPoolExecutor(max_workers=2) as ex:
            list(ex.map(lambda _: license_client.validate(email), range(2)))
        time.sleep(0.5)
        customers = list(stripe.Customer.list(email=email).auto_paging_iter())
        assert len(customers) == 1, f"race produced {len(customers)} customers"
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(82)
def test_subscription_deleted_double_fire_idempotent(license_client, env_cfg, make_customer):
    """If deleted fires twice (immediate cancel + period-end expiry), no crash."""
    c = make_customer("p12-82")
    stripe.Customer.modify(c.id, metadata={"machine_id": "bound"})
    event = make_fake_event("customer.subscription.deleted", {"id": "sub_x", "customer": c.id})
    body = json.dumps(event)
    sig = sign_webhook_payload(body, env_cfg["webhook_secret"])
    r1 = license_client.webhook(body, sig)
    r2 = license_client.webhook(body, sig)
    assert r1.status_code == 200 and r2.status_code == 200


@pytest.mark.case(83)
@pytest.mark.known_fail  # status='active' query excludes past_due → paying users in grace locked out
def test_past_due_sub_still_treated_as_paying(env_cfg, make_customer, license_client):
    """Create sub, force past_due, validate should STILL return pro."""
    c = make_customer("p12-83")
    sub = create_active_sub(c.id, env_cfg["price_id"])
    if sub.status != "active":
        pytest.skip(f"setup failed: {sub.status}")
    # Can't easily force past_due without test clocks; skip if we can't reproduce
    # This test documents the risk — it will be useful when wired up with test clocks
    pytest.skip("past_due simulation requires test clocks (Phase 5 work)")


@pytest.mark.case(84)
def test_activate_page_is_fully_client_side(license_client):
    """Success URL page doesn't do server-side verification — relies on next app launch."""
    r = license_client.client.get("/activate?session_id=cs_test_fake")
    # Page should render as 200 regardless — it's client-only
    assert r.status_code in (200, 308)  # 308 if trailingSlash


@pytest.mark.case(85)
def test_webhook_with_fake_customer_id_still_acks_200(license_client, env_cfg):
    """Handler must return 200 even if the referenced customer doesn't exist (Stripe CLI fixture pattern)."""
    event = make_fake_event("customer.subscription.deleted", {"id": "sub_fake", "customer": "cus_nonexistent_xyz"})
    body = json.dumps(event)
    sig = sign_webhook_payload(body, env_cfg["webhook_secret"])
    r = license_client.webhook(body, sig)
    assert r.status_code == 200, f"handler must ACK unknown customer, got {r.status_code}"
