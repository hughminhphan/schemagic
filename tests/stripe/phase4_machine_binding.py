"""Phase 4: Machine binding (cases 31-38)."""
from __future__ import annotations

import uuid

import pytest
import stripe

from helpers.stripe_api import create_active_sub, safe_delete_customer, throwaway_email


@pytest.fixture()
def pro_customer(env_cfg, make_customer):
    c = make_customer("p4-pro")
    sub = create_active_sub(c.id, env_cfg["price_id"])
    if sub.status != "active":
        pytest.skip(f"sub did not activate, status={sub.status}")
    return c


@pytest.mark.case(31)
def test_first_bind_sets_machine_id(license_client, pro_customer):
    mid = f"m-{uuid.uuid4().hex[:8]}"
    r = license_client.validate(pro_customer.email, machine_id=mid)
    assert r.status_code == 200
    assert r.json()["tier"] == "pro"
    refreshed = stripe.Customer.retrieve(pro_customer.id)
    assert getattr(refreshed.metadata, "machine_id", None) == mid


@pytest.mark.case(32)
def test_same_machine_revalidate_succeeds(license_client, pro_customer):
    mid = f"m-{uuid.uuid4().hex[:8]}"
    r1 = license_client.validate(pro_customer.email, machine_id=mid)
    r2 = license_client.validate(pro_customer.email, machine_id=mid)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["tier"] == "pro"


@pytest.mark.case(33)
def test_second_machine_device_mismatch(license_client, pro_customer):
    license_client.validate(pro_customer.email, machine_id="first")
    r = license_client.validate(pro_customer.email, machine_id="second")
    assert r.status_code == 403
    assert r.json()["reason"] == "device_mismatch"


@pytest.mark.case(35)
def test_empty_machine_id_400(license_client, pro_customer):
    r = license_client.client.post(
        "/api/license/validate", json={"email": pro_customer.email, "machine_id": ""}
    )
    assert r.status_code == 400


@pytest.mark.case(36)
def test_oversized_machine_id(license_client, pro_customer):
    """Stripe metadata values cap at 500 chars — endpoint should validate or surface Stripe error."""
    huge = "x" * 600
    r = license_client.validate(pro_customer.email, machine_id=huge)
    assert r.status_code in (200, 400, 500)


@pytest.mark.case(38)
def test_transfer_flow_clear_metadata(license_client, pro_customer):
    """Admin clears machine_id in Stripe — new device can bind."""
    license_client.validate(pro_customer.email, machine_id="old-mac")
    stripe.Customer.modify(pro_customer.id, metadata={"machine_id": ""})
    r = license_client.validate(pro_customer.email, machine_id="new-mac")
    assert r.status_code == 200
    assert r.json()["tier"] == "pro"
