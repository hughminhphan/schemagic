"""Orphan sweeper — deletes test customers matching TEST_EMAIL_PREFIX."""
from __future__ import annotations

import subprocess
import sys
import time

import stripe

TEST_PREFIX = "test-DELETEME-"


def main():
    key = subprocess.run(
        ["pass", "show", "schemagic/stripe-secret-key"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not key.startswith("sk_test_"):
        print("REFUSING: not a test-mode key")
        sys.exit(1)
    stripe.api_key = key

    deleted = 0
    for c in stripe.Customer.list(limit=100).auto_paging_iter():
        if c.email and (TEST_PREFIX in c.email or "schemagic.test" in c.email):
            try:
                stripe.Customer.delete(c.id)
                deleted += 1
            except Exception as e:
                print(f"skip {c.id}: {e}")
            time.sleep(0.05)
    print(f"deleted {deleted} test customers")


if __name__ == "__main__":
    main()
