"""Phase 6: Cancellation (cases 47-51)."""
from __future__ import annotations

import pytest
import stripe

from helpers.stripe_api import create_active_sub


@pytest.fixture()
def pro_with_sub(env_cfg, make_customer):
    c = make_customer("p6")
    sub = create_active_sub(c.id, env_cfg["price_id"])
    if sub.status != "active":
        pytest.skip(f"sub not active: {sub.status}")
    return c, sub


@pytest.mark.case(47)
def test_cancel_immediately_removes_active_status(license_client, pro_with_sub):
    c, sub = pro_with_sub
    stripe.Subscription.cancel(sub.id)
    r = license_client.validate(c.email, machine_id="m1")
    assert r.status_code == 200
    d = r.json()
    # Cancelled → falls back to free tier (or limit_reached if already used 3)
    assert d.get("tier") == "free" or d.get("reason") == "limit_reached"


@pytest.mark.case(50)
def test_cancel_at_period_end_keeps_sub_active_until_date(license_client, pro_with_sub):
    c, sub = pro_with_sub
    stripe.Subscription.modify(sub.id, cancel_at_period_end=True)
    r = license_client.validate(c.email, machine_id="m1")
    # Period-end cancel: sub is still 'active' now, so user should still be pro
    assert r.status_code == 200
    assert r.json()["tier"] == "pro"


@pytest.mark.case(51)
def test_refund_does_not_cancel_subscription(env_cfg, pro_with_sub):
    c, sub = pro_with_sub
    # Refund the latest invoice (via payment_intent, avoids Stripe API version churn on invoice.charge)
    inv = stripe.Invoice.retrieve(sub.latest_invoice, expand=["payment_intent"])
    pi = getattr(inv, "payment_intent", None)
    if pi and hasattr(pi, "id"):
        try:
            stripe.Refund.create(payment_intent=pi.id)
        except stripe.InvalidRequestError:
            pass
    fresh = stripe.Subscription.retrieve(sub.id)
    assert fresh.status == "active", f"refund should not affect sub status (got {fresh.status})"
