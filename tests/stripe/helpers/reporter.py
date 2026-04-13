"""Pytest hook that collects results and writes a markdown table to results/ and the vault."""
from __future__ import annotations

import datetime as dt
import os
from collections import defaultdict
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
VAULT_PLAN = Path.home() / "Documents" / "Obsidian Vault" / "Projects" / "schemagic" / "Stripe Test Plan.md"

_rows: list[dict] = []


def record(case_id: str, phase: str, case: str, status: str, expected: str = "PASS", notes: str = "") -> None:
    _rows.append({
        "id": case_id,
        "phase": phase,
        "case": case,
        "status": status,
        "expected": expected,
        "notes": notes[:120].replace("|", "/").replace("\n", " "),
    })


def write_results(env: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"run-{ts}-{env}.md"

    totals = defaultdict(lambda: {"pass": 0, "fail": 0, "expected_fail": 0, "regression": 0})
    for r in _rows:
        key = r["phase"]
        if r["status"] == "PASS":
            totals[key]["pass"] += 1
        else:
            if r["expected"] == "FAIL":
                totals[key]["expected_fail"] += 1
            else:
                totals[key]["regression"] += 1
            totals[key]["fail"] += 1

    lines = [
        f"# scheMAGIC Stripe Harness Run — {ts} ({env})",
        "",
        f"Total cases: **{len(_rows)}**. "
        f"Pass: **{sum(v['pass'] for v in totals.values())}**. "
        f"Expected-fail: **{sum(v['expected_fail'] for v in totals.values())}**. "
        f"Regressions: **{sum(v['regression'] for v in totals.values())}**.",
        "",
        "## Summary by phase",
        "",
        "| Phase | Pass | Expected Fail | Regression |",
        "|-------|------|---------------|------------|",
    ]
    for phase in sorted(totals):
        t = totals[phase]
        lines.append(f"| {phase} | {t['pass']} | {t['expected_fail']} | {t['regression']} |")

    lines.extend(["", "## Full results", "", "| # | Phase | Case | Status | Expected | Notes |", "|---|-------|------|--------|----------|-------|"])
    for r in sorted(_rows, key=lambda r: (r["phase"], r["id"])):
        lines.append(f"| {r['id']} | {r['phase']} | {r['case']} | {r['status']} | {r['expected']} | {r['notes']} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def append_to_vault(env: str, result_path: Path) -> None:
    """Append a one-line summary to the vault test plan under a 'Test Runs' section."""
    if not VAULT_PLAN.exists():
        return
    content = VAULT_PLAN.read_text(encoding="utf-8")
    pass_ct = sum(1 for r in _rows if r["status"] == "PASS")
    fail_ct = sum(1 for r in _rows if r["status"] == "FAIL")
    reg_ct = sum(1 for r in _rows if r["status"] == "FAIL" and r["expected"] != "FAIL")
    entry = (
        f"- **{dt.datetime.now().strftime('%Y-%m-%d %H:%M')}** ({env}): "
        f"{pass_ct} pass, {fail_ct} fail ({reg_ct} regression). "
        f"Run file: `tests/stripe/results/{result_path.name}`"
    )
    if "## Test Runs" in content:
        content = content.replace("## Test Runs", f"## Test Runs\n\n{entry}", 1)
    else:
        content = content.rstrip() + "\n\n---\n\n## Test Runs\n\n" + entry + "\n"
    VAULT_PLAN.write_text(content, encoding="utf-8")
