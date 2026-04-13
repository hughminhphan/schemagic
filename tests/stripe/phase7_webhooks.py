"""Phase 7: Webhook handler edge cases (cases 52-60). Uses synthetic HMAC-signed POSTs."""
from __future__ import annotations

import json
import time

import pytest
import stripe

from helpers.stripe_api import make_fake_event, sign_webhook_payload


@pytest.mark.case(52)
def test_missing_signature_header_400(license_client):
    r = license_client.client.post(
        "/api/payments/webhook",
        content=json.dumps({"type": "ping"}),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


@pytest.mark.case(53)
def test_invalid_signature_400(license_client):
    body = json.dumps({"id": "evt_fake", "type": "ping"})
    r = license_client.webhook(body, "t=1,v1=deadbeef")
    assert r.status_code == 400


@pytest.mark.case(54)
def test_unknown_event_type_returns_200(license_client, env_cfg):
    body = json.dumps(make_fake_event("ping", {"id": "obj_1"}))
    sig = sign_webhook_payload(body, env_cfg["webhook_secret"])
    r = license_client.webhook(body, sig)
    assert r.status_code == 200
    assert r.json().get("received") is True


@pytest.mark.case(57)
def test_webhook_for_deleted_customer_no_crash(license_client, env_cfg, make_customer):
    c = make_customer("p7-57")
    cid = c.id
    stripe.Customer.delete(cid)
    event = make_fake_event("customer.subscription.deleted", {"id": "sub_x", "customer": cid})
    body = json.dumps(event)
    sig = sign_webhook_payload(body, env_cfg["webhook_secret"])
    r = license_client.webhook(body, sig)
    assert r.status_code == 200, f"should handle deleted customer gracefully, got {r.status_code}"


@pytest.mark.case(60)
def test_subscription_deleted_clears_machine_id(license_client, env_cfg, make_customer):
    c = make_customer("p7-60")
    stripe.Customer.modify(c.id, metadata={"machine_id": "bound"})
    event = make_fake_event("customer.subscription.deleted", {"id": "sub_x", "customer": c.id})
    body = json.dumps(event)
    sig = sign_webhook_payload(body, env_cfg["webhook_secret"])
    r = license_client.webhook(body, sig)
    assert r.status_code == 200
    time.sleep(1)
    refreshed = stripe.Customer.retrieve(c.id)
    assert not getattr(refreshed.metadata, "machine_id", "")
