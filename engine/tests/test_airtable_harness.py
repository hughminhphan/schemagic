#!/usr/bin/env python3
"""
Airtable-backed test harness for scheMAGIC.

Pulls component + pin ground truth from Airtable, runs the pipeline against each,
compares results, and writes match_rate / test_status back to Airtable.

Falls back to test_parts.json if Airtable is unreachable.

Usage:
  python3 test_airtable_harness.py                 # run all parts
  python3 test_airtable_harness.py TPS54302         # filter by part number
  python3 test_airtable_harness.py --dry-run        # pull from Airtable, don't run pipeline
  python3 test_airtable_harness.py --local-fallback  # use test_parts.json instead

Environment:
  AIRTABLE_PAT  — Airtable personal access token (or reads from `pass`)

Exit codes:
  0 = all parts passed
  1 = at least one part failed
  2 = harness error
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

# -- Path setup (same as test_harness.py) --
os.environ["SCHEMAGIC_STANDALONE"] = "1"
if __name__ == "__main__":
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)

# -- Airtable config --
BASE_ID = "appInUL3HRHDfYSCN"
COMPONENTS_TABLE = "tblaCtUSVScEJ1Pa2"
PINS_TABLE = "tbl4wKh9kqGDXI1rP"
AIRTABLE_API = "https://api.airtable.com/v0"


def log(msg):
    print(msg, file=sys.stderr)


def get_airtable_token():
    """Get Airtable PAT from env or pass."""
    token = os.environ.get("AIRTABLE_PAT")
    if token:
        return token
    try:
        result = subprocess.run(
            ["pass", "show", "airtable/pat"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def airtable_get(endpoint, token, params=None):
    """Make a GET request to Airtable API."""
    url = f"{AIRTABLE_API}/{BASE_ID}/{endpoint}"
    if params:
        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{query}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def airtable_patch(endpoint, token, data):
    """Make a PATCH request to Airtable API."""
    url = f"{AIRTABLE_API}/{BASE_ID}/{endpoint}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="PATCH", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_all_records(table_id, token):
    """Fetch all records from an Airtable table, handling pagination."""
    records = []
    offset = None
    while True:
        params = {}
        if offset:
            params["offset"] = offset
        data = airtable_get(table_id, token, params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def load_from_airtable(token):
    """Load test parts from Airtable (components + pins)."""
    log("Fetching components from Airtable...")
    components = fetch_all_records(COMPONENTS_TABLE, token)
    log(f"  Found {len(components)} components")

    log("Fetching pins from Airtable...")
    pins = fetch_all_records(PINS_TABLE, token)
    log(f"  Found {len(pins)} pin records")

    # Group pins by component record ID
    pins_by_component = {}
    for pin in pins:
        fields = pin["fields"]
        comp_links = fields.get("Component", [])
        for comp_id in comp_links:
            pins_by_component.setdefault(comp_id, []).append({
                "number": fields.get("Pin Number", ""),
                "name": fields.get("Pin Name", ""),
                "type": fields.get("Pin Type", "unspecified"),
            })

    # Build test parts list
    test_parts = []
    for comp in components:
        comp_id = comp["id"]
        fields = comp["fields"]
        pn = fields.get("Part Number", "")
        if not pn:
            continue

        comp_pins = pins_by_component.get(comp_id, [])
        if not comp_pins:
            log(f"  WARNING: {pn} has no pins in Airtable, skipping")
            continue

        test_parts.append({
            "pn": pn,
            "family": fields.get("Component Type", "unknown"),
            "kicad_lib": fields.get("KiCad Library", ""),
            "kicad_sym": fields.get("KiCad Symbol", ""),
            "expected_pins": fields.get("Pin Count", len(comp_pins)),
            "pins": comp_pins,
            "_airtable_id": comp_id,
        })

    return test_parts


def load_from_json():
    """Fallback: load from test_parts.json."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_parts.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"test_parts.json not found at {path}")
    with open(path) as f:
        parts = json.load(f)
    for p in parts:
        p["_airtable_id"] = None
    return parts


def update_airtable_status(token, record_id, status, match_rate):
    """Write test results back to the component record in Airtable."""
    if not token or not record_id:
        return
    today = time.strftime("%Y-%m-%d")
    try:
        airtable_patch(COMPONENTS_TABLE, token, {
            "records": [{
                "id": record_id,
                "fields": {
                    "Test Status": status,
                    "Match Rate": round(match_rate * 100, 1),
                    "Last Test Date": today,
                },
            }],
        })
    except Exception as e:
        log(f"  WARNING: Failed to update Airtable: {e}")


# -- Reuse comparison logic from test_harness.py --
from engine.tests.test_harness import compare_pins, _names_equivalent


def main():
    from engine.core.config import check_pdfplumber
    if not check_pdfplumber():
        log("ERROR: pdfplumber not installed.")
        sys.exit(2)

    # Parse args
    filter_pn = None
    dry_run = False
    local_fallback = False
    for arg in sys.argv[1:]:
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--local-fallback":
            local_fallback = True
        else:
            filter_pn = arg.upper()

    # Load test parts
    token = get_airtable_token()
    if local_fallback or not token:
        if not token and not local_fallback:
            log("WARNING: No Airtable token found, falling back to test_parts.json")
        test_parts = load_from_json()
        token = None
    else:
        try:
            test_parts = load_from_airtable(token)
        except Exception as e:
            log(f"WARNING: Airtable fetch failed ({e}), falling back to test_parts.json")
            test_parts = load_from_json()
            token = None

    if filter_pn:
        test_parts = [p for p in test_parts if filter_pn in p["pn"].upper()]
        log(f"Filtered to {len(test_parts)} parts matching '{filter_pn}'")

    if dry_run:
        log(f"\n--- DRY RUN: {len(test_parts)} parts loaded ---")
        for p in test_parts:
            log(f"  {p['pn']} ({p['family']}): {len(p['pins'])} pins")
        sys.exit(0)

    log(f"Running pipeline against {len(test_parts)} parts...\n")

    from engine.tests.test_harness import run_pipeline_headless

    results = []
    passed_count = 0
    failed_count = 0
    error_count = 0

    for i, part in enumerate(test_parts):
        pn = part["pn"]
        expected_pins = part["pins"]
        airtable_id = part.get("_airtable_id")
        log(f"[{i+1}/{len(test_parts)}] Testing {pn} ({part['family']})...")

        start = time.time()
        datasheet, match, error = run_pipeline_headless(pn)
        elapsed = round(time.time() - start, 1)

        result = {"pn": pn, "family": part["family"], "elapsed_seconds": elapsed}

        if error:
            result["status"] = "ERROR"
            result["error"] = error
            error_count += 1
            log(f"  ERROR ({elapsed}s): {error}")
            update_airtable_status(token, airtable_id, "Error", 0)
        elif not datasheet or not datasheet.pins:
            result["status"] = "FAIL"
            result["error"] = "No pins extracted"
            failed_count += 1
            log(f"  FAIL ({elapsed}s): No pins extracted")
            update_airtable_status(token, airtable_id, "Failing", 0)
        else:
            passed, details = compare_pins(datasheet.pins, expected_pins)
            result["status"] = "PASS" if passed else "FAIL"
            result["details"] = details

            if passed:
                passed_count += 1
                log(f"  PASS ({elapsed}s): {len(datasheet.pins)} pins, "
                    f"match rate {details['match_rate']:.0%}")
                update_airtable_status(token, airtable_id, "Passing", details["match_rate"])
            else:
                failed_count += 1
                log(f"  FAIL ({elapsed}s): {len(datasheet.pins)} pins, "
                    f"match rate {details['match_rate']:.0%}, "
                    f"missing={len(details['missing_pins'])}, "
                    f"mismatches={len(details['name_mismatches'])}")
                update_airtable_status(token, airtable_id, "Failing", details["match_rate"])

        results.append(result)

    total = len(test_parts)
    log(f"\n{'='*60}")
    log(f"RESULTS: {passed_count}/{total} passed, "
        f"{failed_count} failed, {error_count} errors")
    log(f"{'='*60}")

    output = {
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "errors": error_count,
        "pass_rate": round(passed_count / max(total, 1), 3),
        "source": "airtable" if token else "test_parts.json",
        "results": results,
    }
    print(json.dumps(output, indent=2))

    sys.exit(0 if failed_count == 0 and error_count == 0 else 1)


if __name__ == "__main__":
    main()
