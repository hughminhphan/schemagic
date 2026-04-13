"""Client for the Next.js license/validate endpoint and sidecar license enforcement."""
from __future__ import annotations

import time
import uuid

import httpx
import jwt as pyjwt


class LicenseClient:
    def __init__(self, api_base: str, *, timeout: float = 20.0):
        self.api_base = api_base.rstrip("/")
        self.client = httpx.Client(base_url=self.api_base, timeout=timeout)

    def close(self) -> None:
        self.client.close()

    # ---- validate endpoint ----

    def validate(self, email: str, machine_id: str | None = None, *, expected: int = 200):
        mid = machine_id or f"test-mach-{uuid.uuid4().hex[:8]}"
        r = self.client.post("/api/license/validate", json={"email": email, "machine_id": mid})
        return r

    def check(self, email: str):
        return self.client.get("/api/payments/check", params={"email": email})

    def checkout(self, email: str):
        return self.client.post("/api/payments/checkout", json={"email": email})

    def portal(self, email: str):
        return self.client.post("/api/payments/portal", json={"email": email})

    def webhook(self, body: str, sig_header: str):
        return self.client.post(
            "/api/payments/webhook",
            content=body,
            headers={"stripe-signature": sig_header, "content-type": "application/json"},
        )


class SidecarClient:
    def __init__(self, sidecar_url: str, *, timeout: float = 30.0):
        self.url = sidecar_url.rstrip("/")
        self.client = httpx.Client(base_url=self.url, timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def run(self, token: str, part_number: str = "LM358"):
        return self.client.post(
            "/api/run",
            json={"part_number": part_number},
            headers={"X-License-Token": token},
        )

    def run_no_token(self, part_number: str = "LM358"):
        return self.client.post("/api/run", json={"part_number": part_number})


def sign_test_token(payload: dict, private_key: str, *, expires_in: int = 300) -> str:
    """Sign a JWT with the license RS256 key. Used for negative tests (tamper, wrong-tier, etc)."""
    claims = {
        **payload,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }
    return pyjwt.encode(claims, private_key, algorithm="RS256")
