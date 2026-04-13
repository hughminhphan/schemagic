"""Stripe test-mode helpers: customers, test clocks, webhook signing."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import stripe
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


# ---------- email + customer ----------

TEST_EMAIL_PREFIX = "test-deleteme-"


def throwaway_email(tag: str = "t") -> str:
    return f"{TEST_EMAIL_PREFIX}{tag}-{uuid.uuid4().hex[:8]}@schemagic.test".lower()


@retry(
    retry=retry_if_exception_type(stripe.APIConnectionError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    reraise=True,
)
def create_customer(email: str | None = None, *, test_clock: str | None = None, metadata: dict | None = None):
    email = email or throwaway_email()
    kwargs: dict = {"email": email}
    if test_clock:
        kwargs["test_clock"] = test_clock
    if metadata:
        kwargs["metadata"] = metadata
    return stripe.Customer.create(**kwargs)


def safe_delete_customer(customer_id: str) -> None:
    try:
        stripe.Customer.delete(customer_id)
    except stripe.InvalidRequestError:
        pass  # already deleted


# ---------- test clocks ----------

def create_test_clock(frozen_time: int | None = None, name: str | None = None):
    frozen_time = frozen_time or int(time.time())
    name = name or f"harness-{uuid.uuid4().hex[:6]}"
    return stripe.test_helpers.TestClock.create(frozen_time=frozen_time, name=name)


def advance_clock(clock_id: str, target_unix: int, *, poll_timeout: float = 60.0) -> None:
    stripe.test_helpers.TestClock.advance(clock_id, frozen_time=target_unix)
    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        clock = stripe.test_helpers.TestClock.retrieve(clock_id)
        if clock.status == "ready":
            return
        if clock.status == "failed":
            raise RuntimeError(f"test clock {clock_id} entered failed state")
        time.sleep(0.5)
    raise TimeoutError(f"test clock {clock_id} did not reach ready within {poll_timeout}s")


def safe_delete_clock(clock_id: str) -> None:
    try:
        stripe.test_helpers.TestClock.delete(clock_id)
    except stripe.InvalidRequestError:
        pass


# ---------- direct subscription creation (bypasses Checkout) ----------

def create_active_sub(customer_id: str, price_id: str, *, card_token: str = "tok_visa"):
    """Attach a payment method and create an ACTIVE subscription (first payment succeeds)."""
    pm = stripe.PaymentMethod.create(type="card", card={"token": card_token})
    stripe.PaymentMethod.attach(pm.id, customer=customer_id)
    stripe.Customer.modify(customer_id, invoice_settings={"default_payment_method": pm.id})
    sub = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
        default_payment_method=pm.id,
        expand=["latest_invoice.payment_intent"],
    )
    # Poll briefly for status to become active (first invoice auto-charges)
    import time as _t
    deadline = _t.time() + 10
    while _t.time() < deadline:
        fresh = stripe.Subscription.retrieve(sub.id)
        if fresh.status == "active":
            return fresh
        _t.sleep(0.5)
    return sub


# ---------- synthetic signed webhooks (no Stripe CLI needed) ----------

def sign_webhook_payload(payload: str, secret: str, timestamp: int | None = None) -> str:
    """Build a Stripe-Signature header value."""
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.{payload}".encode()
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def make_fake_event(event_type: str, data_object: dict, event_id: str | None = None) -> dict:
    event_id = event_id or f"evt_test_{uuid.uuid4().hex[:16]}"
    return {
        "id": event_id,
        "object": "event",
        "api_version": "2024-12-18.acacia",
        "created": int(time.time()),
        "data": {"object": data_object},
        "livemode": False,
        "pending_webhooks": 0,
        "request": {"id": None, "idempotency_key": None},
        "type": event_type,
    }
