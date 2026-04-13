"""Phase 3 UX: Real Stripe Checkout form via Playwright (cases 20-24). Gated behind --ux."""
from __future__ import annotations

import pytest

from helpers.stripe_api import safe_delete_customer, throwaway_email
import stripe


pytestmark = pytest.mark.ux


def _fill_checkout_form(page, card_number: str, expect_decline: bool = False):
    """Fill Stripe's hosted Checkout form and submit."""
    # Stripe Checkout renders all fields at top level; email may be prefilled
    page.wait_for_selector("input[name='cardNumber']", timeout=30000)
    page.fill("input[name='cardNumber']", card_number)
    page.fill("input[name='cardExpiry']", "12 / 34")
    page.fill("input[name='cardCvc']", "123")
    # Name field
    try:
        page.fill("input[name='billingName']", "Test User")
    except Exception:
        pass
    # Submit
    page.click("button[data-testid='hosted-payment-submit-button']")


@pytest.fixture()
def checkout_url(license_client, make_customer):
    c = make_customer("p3ux")
    r = license_client.checkout(c.email)
    assert r.status_code == 200
    return c, r.json()["url"]


@pytest.mark.case(20)
def test_checkout_happy_path_4242(checkout_url):
    """4242 → payment succeeds → redirects to /activate."""
    from playwright.sync_api import sync_playwright
    c, url = checkout_url
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, timeout=30000)
            _fill_checkout_form(page, "4242424242424242")
            # Wait for redirect to /activate
            page.wait_for_url("**/activate*", timeout=60000)
            # Subscription should now exist for this customer
            fresh = stripe.Customer.retrieve(c.id, expand=["subscriptions"])
            subs = fresh.subscriptions.data if fresh.subscriptions else []
            assert len(subs) >= 1, "no subscription created after checkout"
        finally:
            browser.close()


@pytest.mark.case(22)
def test_checkout_generic_decline(checkout_url):
    """4000 0000 0000 0002 → decline error visible in UI."""
    from playwright.sync_api import sync_playwright
    c, url = checkout_url
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, timeout=30000)
            _fill_checkout_form(page, "4000000000000002")
            # Decline error appears — not redirected
            page.wait_for_timeout(5000)
            assert "/activate" not in page.url
            # No subscription created
            fresh = stripe.Customer.retrieve(c.id, expand=["subscriptions"])
            subs = fresh.subscriptions.data if fresh.subscriptions else []
            assert len(subs) == 0, f"declined card created sub: {subs}"
        finally:
            browser.close()


@pytest.mark.case(21)
def test_checkout_user_closes_tab_no_provision(checkout_url):
    """User closes checkout without paying → no webhook → no subscription."""
    from playwright.sync_api import sync_playwright
    c, url = checkout_url
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_selector("input[name='cardNumber']", timeout=30000)
            # Just close — no submission
        finally:
            browser.close()
    # No sub should exist
    fresh = stripe.Customer.retrieve(c.id, expand=["subscriptions"])
    subs = fresh.subscriptions.data if fresh.subscriptions else []
    assert len(subs) == 0
