"""Phase 8: Sidecar JWT enforcement (cases 61-69). Requires sidecar subprocess."""
from __future__ import annotations

import time

import jwt as pyjwt
import pytest

from helpers.license_client import sign_test_token
from helpers.sidecar import SIDECAR_TEST_MACHINE_ID


@pytest.mark.case(61)
def test_no_token_returns_403(sidecar_client):
    r = sidecar_client.run_no_token()
    assert r.status_code in (403, 422), f"got {r.status_code}: {r.text[:100]}"


@pytest.mark.case(62)
def test_tampered_jwt_returns_403(sidecar_client, license_client, env_cfg):
    """Flip one byte of a real JWT → signature invalid → 403."""
    from helpers.stripe_api import throwaway_email
    email = throwaway_email("p8-62")
    r = license_client.validate(email, machine_id=SIDECAR_TEST_MACHINE_ID)
    token = r.json()["token"]
    # Corrupt a chunk of the signature (base64url last segment)
    parts = token.split(".")
    sig = parts[2]
    corrupted = sig[:10] + ("A" * 20) + sig[30:]
    tampered = f"{parts[0]}.{parts[1]}.{corrupted}"
    r2 = sidecar_client.run(tampered)
    assert r2.status_code == 403, f"tampered JWT accepted: {r2.status_code}"


@pytest.mark.case(63)
def test_wrong_key_signed_token_returns_403(sidecar_client):
    """Sign with a different RSA key — should fail verification."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    token = sign_test_token({"sub": "cus_x", "email": "x@y.z", "machine_id": "m", "tier": "pro"}, pem)
    r = sidecar_client.run(token)
    assert r.status_code == 403


@pytest.mark.case(64)
def test_expired_jwt_returns_403(sidecar_client, env_cfg):
    # Sign a token that's already expired (exp = now - 60)
    import jwt as _jwt
    now = int(time.time())
    claims = {"sub": "cus_x", "email": "x@y.z", "machine_id": "m", "tier": "pro", "iat": now - 120, "exp": now - 60}
    expired = _jwt.encode(claims, env_cfg["license_private_key"], algorithm="RS256")
    r = sidecar_client.run(expired)
    assert r.status_code == 403


@pytest.mark.case(65)
def test_jwt_machine_id_mismatch_should_be_rejected(sidecar_client, env_cfg):
    """Hugh's spec: tokens bound to machine_id should be rejected on other machines.
    Current sidecar only checks signature + expiry — machine_id is informational."""
    token = sign_test_token(
        {"sub": "cus_x", "email": "x@y.z", "machine_id": "machine-A", "tier": "pro"},
        env_cfg["license_private_key"],
        expires_in=3600,
    )
    # Sidecar has no way to know what "this machine's" id is, but the spec says
    # the claim should be verified against something (IP, machine hash, etc).
    # Today: sidecar accepts any valid-signature token regardless of machine_id.
    r = sidecar_client.run(token)
    assert r.status_code == 403, "sidecar should reject token bound to different machine"


@pytest.mark.case(66)
def test_free_jwt_single_use_enforcement(sidecar_client, license_client):
    """Second use of a free-tier token should 403 (replay protection)."""
    from helpers.stripe_api import throwaway_email, safe_delete_customer
    import stripe
    email = throwaway_email("p8-66")
    try:
        r = license_client.validate(email, machine_id=SIDECAR_TEST_MACHINE_ID)
        token = r.json()["token"]
        r1 = sidecar_client.run(token, part_number="LM358")
        r2 = sidecar_client.run(token, part_number="LM358")
        # If single-use is enforced: r1 succeeds, r2 403s.
        # If not enforced: both "succeed" (or both fail with same non-403 code).
        if r1.status_code in (200, 202):
            assert r2.status_code == 403, f"replay allowed: r2={r2.status_code}"
    finally:
        for c in stripe.Customer.list(email=email).auto_paging_iter():
            safe_delete_customer(c.id)


@pytest.mark.case(68)
def test_sidecar_docs_responds(sidecar_client):
    """Sanity check that the sidecar is alive (FastAPI /docs)."""
    r = sidecar_client.client.get("/docs")
    assert r.status_code == 200
