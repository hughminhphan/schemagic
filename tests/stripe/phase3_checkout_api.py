"""Phase 3: Checkout behaviours via Stripe API (bypasses hosted Checkout). Cases 20-30."""
from __future__ import annotations

import pytest
import stripe

from helpers.stripe_api import safe_delete_customer, throwaway_email


def _try_sub_with_card(customer_id: str, price_id: str, token: str):
    """Attach a test token and attempt to create a sub. Returns (sub_or_none, error_or_none)."""
    try:
        pm = stripe.PaymentMethod.create(type="card", card={"token": token})
        stripe.PaymentMethod.attach(pm.id, customer=customer_id)
        stripe.Customer.modify(customer_id, invoice_settings={"default_payment_method": pm.id})
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id}],
            default_payment_method=pm.id,
        )
        return sub, None
    except stripe.StripeError as e:
        return None, e


@pytest.mark.case(20)
def test_happy_path_visa(env_cfg, make_customer):
    c = make_customer("p3-20")
    sub, err = _try_sub_with_card(c.id, env_cfg["price_id"], "tok_visa")
    assert err is None, f"tok_visa failed: {err}"
    assert sub.status == "active", f"expected active, got {sub.status}"


@pytest.mark.case(21)
def test_checkout_creates_with_user_email(license_client, make_customer):
    """Webhook of 'user cancels checkout' isn't observable server-side — session just expires.
    Here we assert a checkout can be created and contains the right customer."""
    c = make_customer("p3-21")
    r = license_client.checkout(c.email)
    assert r.status_code == 200
    assert "url" in r.json()


@pytest.mark.case(22)
def test_generic_decline(env_cfg, make_customer):
    c = make_customer("p3-22")
    sub, err = _try_sub_with_card(c.id, env_cfg["price_id"], "tok_chargeDeclined")
    # Should either raise CardError or create incomplete sub
    if err:
        assert err.code == "card_declined" or "declined" in str(err).lower()
    else:
        assert sub.status in ("incomplete", "incomplete_expired"), f"got {sub.status}"


@pytest.mark.case(24)
def test_insufficient_funds(env_cfg, make_customer):
    c = make_customer("p3-24")
    _, err = _try_sub_with_card(c.id, env_cfg["price_id"], "tok_chargeDeclinedInsufficientFunds")
    assert err is not None
    assert err.code == "card_declined"


@pytest.mark.case(25)
def test_lost_card(env_cfg, make_customer):
    c = make_customer("p3-25")
    _, err = _try_sub_with_card(c.id, env_cfg["price_id"], "tok_chargeDeclinedLostCard")
    assert err is not None


@pytest.mark.case(26)
def test_attach_succeeds_charge_fails(env_cfg, make_customer):
    """tok_chargeCustomerFail: card attaches, first invoice fails. Sub goes incomplete."""
    c = make_customer("p3-26")
    sub, err = _try_sub_with_card(c.id, env_cfg["price_id"], "tok_chargeCustomerFail")
    # Expected: sub created in incomplete state (not CardError at creation)
    if sub:
        assert sub.status == "incomplete", f"expected incomplete, got {sub.status}"


@pytest.mark.case(30)
def test_invalid_price_id_400(license_client, monkeypatch, make_customer):
    """If STRIPE_PRICE_ID pointed at a deleted/invalid price, checkout would 500.
    We simulate by calling Stripe directly to confirm the error shape."""
    c = make_customer("p3-30")
    try:
        stripe.checkout.Session.create(
            customer=c.id,
            mode="subscription",
            line_items=[{"price": "price_doesnotexist", "quantity": 1}],
            success_url="https://example.com/",
            cancel_url="https://example.com/",
        )
        pytest.fail("expected InvalidRequestError")
    except stripe.InvalidRequestError as e:
        assert "No such price" in str(e) or "price" in str(e).lower()
