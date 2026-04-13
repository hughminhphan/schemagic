"""Phase 11: Full journey smoke tests (S1-S7). Run these FIRST to confirm baseline."""
from __future__ import annotations

import uuid

import pytest
import stripe

from helpers.stripe_api import create_active_sub, safe_delete_customer, throwaway_email


@pytest.mark.case("S1a")
def test_fresh_user_first_free_generation(license_client, env_cfg):
    """Fresh email -> first validate returns free tier JWT with 1 generation used."""
    email = throwaway_email("S1a")
    try:
        r = license_client.validate(email)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("valid") is True
        assert data.get("tier") == "free"
        assert data.get("generationsUsed") == 1
        assert data.get("generationsRemaining") == 2
        assert "token" in data and len(data["token"]) > 50
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case("S1b")
def test_free_tier_hits_paywall_after_three_generations(license_client):
    email = throwaway_email("S1b")
    try:
        for i in range(3):
            r = license_client.validate(email)
            assert r.status_code == 200
            assert r.json().get("generationsUsed") == i + 1
        r4 = license_client.validate(email)
        assert r4.status_code == 200
        data = r4.json()
        assert data.get("valid") is False
        assert data.get("reason") == "limit_reached"
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case("S2")
def test_pro_user_validates_with_active_subscription(license_client, env_cfg, make_customer):
    """Create customer + sub via API, then validate returns pro JWT bound to machine_id."""
    customer = make_customer("S2")
    try:
        create_active_sub(customer.id, env_cfg["price_id"])
    except stripe.CardError as e:
        pytest.skip(f"card setup failed (test mode env issue): {e}")
    machine = f"machine-{uuid.uuid4().hex[:8]}"
    r = license_client.validate(customer.email, machine_id=machine)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("valid") is True
    assert data.get("tier") == "pro"
    assert "token" in data
    # Verify machine_id bound (Stripe StripeObject needs attribute access, not .get)
    refreshed = stripe.Customer.retrieve(customer.id)
    assert getattr(refreshed.metadata, "machine_id", None) == machine


@pytest.mark.case("S3")
def test_pro_second_machine_gets_device_mismatch(license_client, env_cfg, make_customer):
    customer = make_customer("S3")
    try:
        create_active_sub(customer.id, env_cfg["price_id"])
    except stripe.CardError as e:
        pytest.skip(f"card setup failed: {e}")
    r1 = license_client.validate(customer.email, machine_id="first-machine")
    assert r1.status_code == 200
    r2 = license_client.validate(customer.email, machine_id="second-machine")
    assert r2.status_code == 403
    data = r2.json()
    assert data.get("reason") == "device_mismatch"


@pytest.mark.case("S4")
def test_checkout_session_creation(license_client, make_customer):
    customer = make_customer("S4")
    r = license_client.checkout(customer.email)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "url" in data
    assert data["url"].startswith("https://checkout.stripe.com/")


@pytest.mark.case("S5")
def test_portal_session_creation(license_client, make_customer):
    customer = make_customer("S5")
    r = license_client.portal(customer.email)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "url" in data
    assert "billing.stripe.com" in data["url"] or "stripe.com" in data["url"]


@pytest.mark.case("S6")
def test_check_endpoint_returns_status_for_unlicensed(license_client, make_customer):
    customer = make_customer("S6")
    r = license_client.check(customer.email)
    assert r.status_code == 200
    data = r.json()
    assert data.get("licensed") is False
    assert data.get("generationsLimit") == 3
    assert data.get("generationsUsed") == 0
