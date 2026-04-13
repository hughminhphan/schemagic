"""Spawn the FastAPI sidecar as a subprocess for JWT-enforcement tests."""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
PORT_RE = re.compile(r"SCHEMAGIC_PORT:(\d+)")

# Stable ID used by phase 8 tests so JWT machine_id claims match the sidecar.
SIDECAR_TEST_MACHINE_ID = "test-sidecar-machine-id"


@dataclass
class Sidecar:
    proc: subprocess.Popen
    url: str

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def spawn_sidecar(port: int = 0, timeout: float = 15.0) -> Sidecar:
    """Start server/main.py, read SCHEMAGIC_PORT from stdout, wait for health."""
    env = {
        **os.environ,
        "SCHEMAGIC_SIDECAR": "1",
        "SCHEMAGIC_STANDALONE": "1",
        "SCHEMAGIC_PORT": str(port),
        "SCHEMAGIC_MACHINE_ID": SIDECAR_TEST_MACHINE_ID,
    }
    proc = subprocess.Popen(
        [str(REPO_ROOT / ".venv-tests" / "bin" / "python"), "-u", "server/main.py"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    deadline = time.time() + timeout
    bound_port: int | None = None
    while time.time() < deadline and proc.poll() is None:
        line = proc.stdout.readline()
        if not line:
            continue
        m = PORT_RE.search(line)
        if m:
            bound_port = int(m.group(1))
            break
    if bound_port is None:
        proc.kill()
        raise RuntimeError(f"sidecar never announced port within {timeout}s")
    url = f"http://127.0.0.1:{bound_port}"
    # FastAPI exposes /docs by default — use as liveness probe
    health_deadline = time.time() + 10
    while time.time() < health_deadline:
        try:
            r = httpx.get(f"{url}/docs", timeout=1.0)
            if r.status_code in (200, 404):  # 404 still means the server is up
                return Sidecar(proc=proc, url=url)
        except Exception:
            pass
        time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"sidecar bound port {bound_port} but never became responsive")
