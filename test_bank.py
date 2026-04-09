#!/usr/bin/env python3
"""Test bank: run 10 common components through the scheMAGIC API and report results."""

import json
import sys
import urllib.request
import urllib.error
import time

API = "http://localhost:8000"

# 10 easy common components with expected results
TEST_COMPONENTS = [
    {
        "part": "LM358",
        "expect_symbol_contains": "LM358",
        "expect_footprint_contains": "SOIC-8",
        "select_package": "SOIC-8",
        "min_pins": 8,
    },
    {
        "part": "STM32F103C8T6",
        "expect_symbol_contains": "STM32F103C8",
        "expect_footprint_contains": "LQFP-48",
        "select_package": "LQFP-48",
        "min_pins": 48,
    },
    {
        "part": "ATmega328P",
        "expect_symbol_contains": "ATmega328P",
        "expect_footprint_contains": "TQFP-32",
        "select_package": "TQFP-32",
        "min_pins": 28,
    },
    {
        "part": "NE555",
        "expect_symbol_contains": "NE555",
        "expect_footprint_contains": "DIP-8",
        "select_package": "PDIP-8",
        "min_pins": 8,
    },
    {
        "part": "LM7805",
        "expect_symbol_contains": "7805",
        "expect_footprint_contains": "TO-220",
        "select_package": "TO-220",
        "min_pins": 3,
    },
    {
        "part": "74HC595",
        "expect_symbol_contains": "74HC595",
        "expect_footprint_contains": "DIP-16",
        "select_package": "PDIP-16",
        "min_pins": 16,
    },
    {
        "part": "LM317",
        "expect_symbol_contains": "LM317",
        "expect_footprint_contains": "TO-220",
        "select_package": "TO-220",
        "min_pins": 3,
    },
    {
        "part": "TL431",
        "expect_symbol_contains": "TL431",
        "expect_footprint_contains": "SOT-23",
        "select_package": None,
        "min_pins": 3,
    },
    {
        "part": "LM393",
        "expect_symbol_contains": "LM393",
        "expect_footprint_contains": "DIP-8",
        "select_package": "PDIP-8",
        "min_pins": 8,
    },
    {
        "part": "TL072",
        "expect_symbol_contains": "TL07",
        "expect_footprint_contains": "DIP-8",
        "select_package": "PDIP-8",
        "min_pins": 8,
    },
]


def api_post(path, data):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def read_sse(job_id, timeout=120):
    """Read SSE stream via curl subprocess and return the final event data."""
    import subprocess
    proc = subprocess.Popen(
        ["curl", "-sN", f"{API}/api/status/{job_id}"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True,
    )
    events = []
    current_event = ""
    start = time.time()

    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("event: "):
                current_event = line[7:].strip()
            elif line.startswith("data: "):
                try:
                    d = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                events.append((current_event, d))
                if current_event in ("complete", "error", "package_select"):
                    proc.kill()
                    return events
                current_event = ""
            if time.time() - start > timeout:
                break
    finally:
        proc.kill()
        proc.wait()
    return events


def test_component(comp):
    part = comp["part"]
    print(f"\n{'='*60}")
    print(f"Testing: {part}")
    print(f"{'='*60}")

    issues = []

    # Step 1: Start run
    try:
        result = api_post("/api/run", {"part_number": part})
        job_id = result["job_id"]
    except Exception as e:
        print(f"  FAIL: Could not start run: {e}")
        return False, [f"Run failed: {e}"]

    # Step 2: Read SSE stream
    events = read_sse(job_id)
    if not events:
        print(f"  FAIL: No SSE events received")
        return False, ["No SSE events"]

    last_event, last_data = events[-1]

    # Step 3: Handle package selection if needed
    if last_event == "package_select":
        candidates = last_data.get("candidates", [])
        print(f"  Packages found: {[c['name'] for c in candidates]}")

        # Find the expected package or pick first
        selected = None
        if comp["select_package"]:
            for c in candidates:
                if c["name"] == comp["select_package"]:
                    selected = c
                    break
            if not selected:
                # Try partial match
                for c in candidates:
                    if comp["select_package"].replace("PDIP", "DIP") in c["name"] or c["name"].replace("PDIP", "DIP") in comp["select_package"]:
                        selected = c
                        break
            if not selected:
                issues.append(f"Expected package '{comp['select_package']}' not in candidates: {[c['name'] for c in candidates]}")
                selected = candidates[0] if candidates else None

        if not selected and candidates:
            selected = candidates[0]

        if selected:
            print(f"  Selecting: {selected['name']}")
            try:
                select_result = api_post("/api/select-package", {"job_id": job_id, "package": selected})
                # select-package returns JSON directly with datasheet, match, pins
                last_event = "complete"
                last_data = select_result
            except Exception as e:
                print(f"  FAIL: Package selection error: {e}")
                return False, [f"Package selection error: {e}"]

    # Step 4: Check results
    if last_event == "error":
        print(f"  FAIL: Pipeline error: {last_data.get('message', '?')}")
        return False, [f"Pipeline error: {last_data.get('message', '?')}"]

    if last_event == "complete":
        match = last_data.get("match", {})
        pins = last_data.get("pins", [])
        sym = f"{match.get('symbol_lib', '?')}/{match.get('symbol_name', '?')}"
        sym_score = match.get("symbol_score", 0)
        fp = f"{match.get('footprint_lib', '?')}/{match.get('footprint_name', '?')}"
        fp_score = match.get("footprint_score", 0)

        print(f"  Symbol:    {sym} ({sym_score}%)")
        print(f"  Footprint: {fp} ({fp_score}%)")
        print(f"  Pins:      {len(pins)}")

        # Check symbol match
        expect_sym = comp["expect_symbol_contains"].upper()
        if expect_sym not in sym.upper():
            issues.append(f"Symbol '{sym}' doesn't contain '{comp['expect_symbol_contains']}'")

        if sym_score < 50:
            issues.append(f"Symbol score too low: {sym_score}")

        # Check footprint match
        expect_fp = comp["expect_footprint_contains"].upper()
        if expect_fp not in fp.upper():
            issues.append(f"Footprint '{fp}' doesn't contain '{comp['expect_footprint_contains']}'")

        # Check pin count
        if len(pins) < comp["min_pins"]:
            issues.append(f"Only {len(pins)} pins, expected >= {comp['min_pins']}")

        # Check for known bad pin patterns
        for pin in pins:
            name = pin.get("name", "")
            if "\u00b1" in name:
                issues.append(f"Pin {pin['number']} has unsanitized ± in name: {name}")
                break

        # Check for power pins misclassified as NC
        power_names = {"VCC", "VDD", "V+", "V-", "VSS", "GND", "AVCC", "AVDD"}
        for pin in pins:
            if pin.get("name", "").upper() in power_names and pin.get("type") == "no_connect":
                issues.append(f"Power pin {pin['number']} ({pin['name']}) misclassified as no_connect")

    else:
        issues.append(f"Unexpected final event: {last_event}")

    if issues:
        for issue in issues:
            print(f"  ISSUE: {issue}")
        return False, issues
    else:
        print(f"  PASS")
        return True, []


def main():
    passed = 0
    failed = 0
    results = []

    for comp in TEST_COMPONENTS:
        ok, issues = test_component(comp)
        results.append((comp["part"], ok, issues))
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{passed+failed} passed")
    print(f"{'='*60}")
    for part, ok, issues in results:
        status = "PASS" if ok else "FAIL"
        detail = "" if ok else f" - {'; '.join(issues)}"
        print(f"  {status}: {part}{detail}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
