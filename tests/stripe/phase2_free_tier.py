"""Phase 2: Free tier counter, JWT lifecycle, race (cases 10-19)."""
from __future__ import annotations

import concurrent.futures as _cf
import time

import jwt as pyjwt
import pytest
import stripe

from helpers.stripe_api import safe_delete_customer, throwaway_email


@pytest.mark.case(10)
def test_first_generation(license_client):
    email = throwaway_email("p2-10")
    try:
        r = license_client.validate(email)
        assert r.status_code == 200
        d = r.json()
        assert d["tier"] == "free" and d["generationsUsed"] == 1 and d["generationsRemaining"] == 2
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(11)
def test_three_generations_progression(license_client):
    email = throwaway_email("p2-11")
    try:
        for i in range(1, 4):
            r = license_client.validate(email)
            d = r.json()
            assert d["generationsUsed"] == i, f"at call {i} got used={d.get('generationsUsed')}"
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(13)
def test_fourth_request_returns_limit_reached(license_client):
    email = throwaway_email("p2-13")
    try:
        for _ in range(3):
            license_client.validate(email)
        r = license_client.validate(email)
        d = r.json()
        assert d.get("valid") is False and d.get("reason") == "limit_reached"
        assert "token" not in d
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(14)
@pytest.mark.xfail(reason="Bug 4: non-atomic increment; fully atomic fix needs Redis INCR", strict=False)
@pytest.mark.known_fail  # non-atomic increment — race allows 4 generations
def test_parallel_validate_race_condition(license_client):
    email = throwaway_email("p2-14")
    try:
        # Seed to count=2
        license_client.validate(email)
        license_client.validate(email)
        # Fire two in parallel — race window
        with _cf.ThreadPoolExecutor(max_workers=2) as ex:
            futures = [ex.submit(license_client.validate, email) for _ in range(2)]
            results = [f.result() for f in futures]
        tokens_issued = sum(1 for r in results if r.json().get("valid") is True)
        # Expected: exactly 1 token (the 3rd slot). If 2 → race bug confirmed.
        assert tokens_issued == 1, f"race bug: {tokens_issued} tokens issued, expected 1"
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(15)
def test_free_jwt_expiry_is_five_minutes(license_client):
    """Don't wait — decode JWT and check exp claim."""
    email = throwaway_email("p2-15")
    try:
        r = license_client.validate(email)
        token = r.json()["token"]
        claims = pyjwt.decode(token, options={"verify_signature": False})
        ttl = claims["exp"] - claims["iat"]
        assert 299 <= ttl <= 301, f"free JWT ttl should be 300s, got {ttl}s"
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(17)
def test_free_jwt_has_generation_id(license_client):
    """Sanity: free tokens must carry a generation_id claim (even if not enforced)."""
    email = throwaway_email("p2-17")
    try:
        r = license_client.validate(email)
        token = r.json()["token"]
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert "generation_id" in claims
        assert claims["tier"] == "free"
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)
