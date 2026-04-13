"""Pytest fixtures for the scheMAGIC Stripe edge case harness."""
from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest
import stripe

from helpers import reporter
from helpers.license_client import LicenseClient, SidecarClient
from helpers.sidecar import Sidecar, spawn_sidecar
from helpers.stripe_api import TEST_EMAIL_PREFIX, safe_delete_customer, throwaway_email


# ---------- CLI options ----------


def pytest_addoption(parser):
    parser.addoption("--env", action="store", default="local", choices=["local", "preview", "prod"])
    parser.addoption("--ux", action="store_true", default=False, help="include Playwright UX tests")
    parser.addoption("--api-base", action="store", default=None, help="override API base URL")


# ---------- session setup ----------


def _pass_show(path: str) -> str:
    r = subprocess.run(["pass", "show", path], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(
            f"pass show {path} failed. Ensure it exists: `pass insert {path}`\n{r.stderr}"
        )
    return r.stdout.rstrip("\n")


@pytest.fixture(scope="session")
def env_cfg(pytestconfig):
    env = pytestconfig.getoption("--env")
    override = pytestconfig.getoption("--api-base")
    if override:
        api_base = override
    elif env == "local":
        api_base = "http://localhost:3000"
    elif env == "preview":
        api_base = os.environ.get("VERCEL_PREVIEW_URL") or os.environ.get("PREVIEW_URL")
        if not api_base:
            pytest.fail("--env=preview needs VERCEL_PREVIEW_URL or PREVIEW_URL env var")
    else:
        api_base = "https://schemagic.design"

    # Credentials from pass
    stripe.api_key = _pass_show("schemagic/stripe-secret-key")
    if not stripe.api_key.startswith("sk_test_"):
        pytest.fail(f"Expected sk_test_ key; got {stripe.api_key[:10]}... — refusing to run against live mode")

    return {
        "env": env,
        "api_base": api_base,
        "price_id": _pass_show("schemagic/stripe-price-id"),
        "webhook_secret": _pass_show("schemagic/stripe-webhook-secret"),
        "license_private_key": _pass_show("schemagic/license-private-key"),
        "license_public_key": _pass_show("schemagic/license-public-key"),
    }


@pytest.fixture(scope="session")
def license_client(env_cfg):
    c = LicenseClient(env_cfg["api_base"])
    yield c
    c.close()


@pytest.fixture(scope="session")
def sidecar() -> Sidecar:
    """Spawn FastAPI sidecar. Skipped automatically for tests that don't request this fixture."""
    sc = spawn_sidecar()
    yield sc
    sc.stop()


@pytest.fixture(scope="session")
def sidecar_client(sidecar) -> SidecarClient:
    c = SidecarClient(sidecar.url)
    yield c
    c.close()


# ---------- per-test customer factory with teardown ----------


_created_customers: list[str] = []


@pytest.fixture()
def make_customer(env_cfg):
    """Factory: make_customer(tag='my-tag') -> stripe.Customer with auto-teardown."""
    created_this_test: list[str] = []

    def _factory(tag: str = "t", email: str | None = None, test_clock: str | None = None):
        email = email or throwaway_email(tag)
        kwargs = {"email": email}
        if test_clock:
            kwargs["test_clock"] = test_clock
        cust = stripe.Customer.create(**kwargs)
        _created_customers.append(cust.id)
        created_this_test.append(cust.id)
        return cust

    yield _factory

    for cid in created_this_test:
        safe_delete_customer(cid)
        if cid in _created_customers:
            _created_customers.remove(cid)


@pytest.fixture()
def throwaway_customer(make_customer):
    """Convenience: single throwaway customer per test."""
    return make_customer()


@pytest.fixture()
def test_clock():
    """A Stripe test clock that cascade-deletes its customers on teardown."""
    from helpers.stripe_api import create_test_clock, safe_delete_clock
    clock = create_test_clock()
    yield clock
    safe_delete_clock(clock.id)


# ---------- markers / --ux gate ----------


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--ux"):
        skip_ux = pytest.mark.skip(reason="Playwright UX tests only run with --ux")
        for item in items:
            if "ux" in item.keywords:
                item.add_marker(skip_ux)

    # Prod: skip destructive tests
    env = config.getoption("--env")
    if env == "prod":
        skip_destructive = pytest.mark.skip(reason="destructive marker — not allowed against prod")
        for item in items:
            if "destructive" in item.keywords:
                item.add_marker(skip_destructive)


# ---------- reporter hook ----------


def _case_metadata(item) -> tuple[str, str, str, str]:
    """Extract case_id, phase, case_name, expected from test item markers/properties."""
    case_id = "?"
    phase = item.fspath.basename.replace(".py", "").split("_")[0]
    case = item.name
    expected = "PASS"
    for m in item.iter_markers(name="case"):
        if m.args:
            case_id = str(m.args[0])
    for _ in item.iter_markers(name="known_fail"):
        expected = "FAIL"
    return case_id, phase, case, expected


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return
    case_id, phase, case, expected = _case_metadata(item)
    status = "PASS" if rep.passed else "FAIL" if rep.failed else "SKIP"
    notes = ""
    if rep.failed and rep.longrepr is not None:
        notes = str(rep.longrepr).splitlines()[-1][:120] if hasattr(rep.longrepr, "__str__") else ""
    reporter.record(case_id=case_id, phase=phase, case=case, status=status, expected=expected, notes=notes)


def pytest_sessionfinish(session, exitstatus):
    env = session.config.getoption("--env")
    # Session safety-net cleanup of any escaped customers
    for cid in list(_created_customers):
        safe_delete_customer(cid)
    # Write report
    try:
        path = reporter.write_results(env)
        reporter.append_to_vault(env, path)
        print(f"\n[reporter] results: {path}")
    except Exception as e:
        print(f"\n[reporter] failed to write: {e}")


def pytest_configure(config):
    config.addinivalue_line("markers", "case(id): test plan case number (e.g., @pytest.mark.case(3))")
