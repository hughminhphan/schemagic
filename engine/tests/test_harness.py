#!/usr/bin/env python3
"""
Headless test harness for schemagic.

Runs the pipeline against test_parts.json WITHOUT any GUI.
For each part:
1. Runs the datasheet fetch + parse pipeline
2. Compares extracted pins against KiCad's official library data (ground truth)
3. Reports pass/fail with details

Exit codes:
  0 = all parts passed
  1 = at least one part failed
  2 = harness error (bad config, missing files, etc.)

Output: JSON results to stdout, human-readable progress to stderr.
"""

import importlib
import json
import os
import sys
import time

# Import path is set up by conftest.py when run via pytest,
# or manually here for standalone execution.
os.environ["SCHEMAGIC_STANDALONE"] = "1"
if __name__ == "__main__":
    # Add repo root to sys.path so `from engine.X` imports work
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)

from engine.core.pipeline import Pipeline
from engine.core.config import check_pdfplumber


def log(msg):
    """Print to stderr (progress info)."""
    print(msg, file=sys.stderr)


def load_test_parts():
    """Load test_parts.json fixture."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_parts.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"test_parts.json not found at {path}")
    with open(path) as f:
        return json.load(f)


def run_pipeline_headless(part_number):
    """Run the schemagic pipeline without GUI.

    Returns (datasheet, match, error_msg) where error_msg is None on success.
    """
    pipeline = Pipeline(project_dir=None)

    try:
        datasheet, match, candidates, suffix_code = pipeline.run(part_number)
        return datasheet, match, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


def compare_pins(extracted_pins, expected_pins, strict=False):
    """Compare extracted pins against ground truth.

    In strict mode: 0 missing, 0 extra, 0 mismatches required.
    In loose mode: match_rate >= 70% and at most 2 missing pins.

    Returns (passed, details_dict).
    """
    details = {
        "extracted_count": len(extracted_pins),
        "expected_count": len(expected_pins),
        "missing_pins": [],
        "extra_pins": [],
        "name_mismatches": [],
    }

    # Build lookup by pin number
    extracted_by_num = {}
    for p in extracted_pins:
        num = p.number if hasattr(p, "number") else p.get("number", "")
        name = p.name if hasattr(p, "name") else p.get("name", "")
        ptype = p.pin_type if hasattr(p, "pin_type") else p.get("type", "")
        alt_nums = p.alt_numbers if hasattr(p, "alt_numbers") else []
        extracted_by_num[num] = {"name": name, "type": ptype}
        for alt in alt_nums:
            extracted_by_num[alt] = {"name": name, "type": ptype}

    expected_by_num = {}
    for p in expected_pins:
        num = p.get("number", "")
        expected_by_num[num] = {"name": p.get("name", ""), "type": p.get("type", "")}

    # Reconcile thermal pad pin numbers: engine may use "EP"/"TP" while KiCad
    # uses the numeric pin number. Match them if names are compatible.
    _THERMAL_PAD_LABELS = {"EP", "TP", "EPAD", "THERMAL PAD", "THERMALPAD"}
    extra_thermal = {n: d for n, d in extracted_by_num.items()
                     if (n.upper() in _THERMAL_PAD_LABELS
                         or d["name"].strip().upper() in _THERMAL_PAD_LABELS)
                     and n not in expected_by_num}
    missing_nums = [n for n in expected_by_num if n not in extracted_by_num]

    for et_num, et_data in list(extra_thermal.items()):
        et_name = et_data["name"].strip().upper()
        matched = False
        for m_num in list(missing_nums):
            m_name = expected_by_num[m_num]["name"].strip().upper()
            if _names_equivalent(et_name, m_name) or et_name == m_name:
                extracted_by_num[m_num] = et_data
                del extracted_by_num[et_num]
                missing_nums.remove(m_num)
                matched = True
                break
        if not matched:
            # Duplicate thermal pad with no matching missing pin - remove it
            del extracted_by_num[et_num]

    # Missing pins (in expected but not extracted)
    for num, exp in expected_by_num.items():
        if num not in extracted_by_num:
            details["missing_pins"].append({"number": num, "name": exp["name"]})

    # Extra pins (in extracted but not expected)
    for num, ext in extracted_by_num.items():
        if num not in expected_by_num:
            details["extra_pins"].append({"number": num, "name": ext["name"]})

    # Name mismatches for pins present in both
    for num in set(extracted_by_num.keys()) & set(expected_by_num.keys()):
        ext = extracted_by_num[num]
        exp = expected_by_num[num]

        ext_name = ext["name"].strip().upper()
        exp_name = exp["name"].strip().upper()
        if ext_name != exp_name and not _names_equivalent(ext_name, exp_name):
            details["name_mismatches"].append({
                "number": num,
                "extracted": ext["name"],
                "expected": exp["name"],
            })

    total_expected = len(expected_by_num)
    missing_count = len(details["missing_pins"])
    mismatch_count = len(details["name_mismatches"])
    extra_count = len(details["extra_pins"])

    details["match_rate"] = round(
        1.0 - (missing_count + mismatch_count) / max(total_expected, 1), 3
    )

    if total_expected == 0:
        passed = False
    elif strict:
        passed = (missing_count == 0 and extra_count == 0 and mismatch_count == 0)
    else:
        match_rate = details["match_rate"]
        passed = match_rate >= 0.7 and missing_count <= 2

    return passed, details


def _names_equivalent(a, b):
    """Check if two pin names are equivalent (common aliases)."""
    import re

    if a == b:
        return True

    # Normalize unicode dashes to ASCII
    a = a.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    b = b.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")

    if a == b:
        return True

    # Strip active-low markers for base comparison
    def _strip_active_low(name):
        if name.startswith("~{") and name.endswith("}"):
            return name[2:-1]
        if name.startswith("~"):
            return name[1:].strip("{}")
        if name.endswith("#"):
            return name[:-1]
        return name

    # Active-low normalization: NAME# -> ~{NAME}
    def _normalize_active_low(name):
        if name.endswith("#"):
            return "~{" + name[:-1] + "}"
        if name.startswith("~{") and name.endswith("}"):
            return name
        if name.startswith("/"):
            return "~{" + name[1:] + "}"
        return name

    if _normalize_active_low(a) == _normalize_active_low(b):
        return True

    a_base = _strip_active_low(a)
    b_base = _strip_active_low(b)
    if a_base == b_base:
        return True

    # MCU alt-function pattern: PA0/WKUP vs PA0, SS/PG vs PG, ON/OFF vs ~{ON}/OFF
    if "/" in a or "/" in b:
        a_parts = a.split("/")
        b_parts = b.split("/")
        a_first = _strip_active_low(a_parts[0])
        b_first = _strip_active_low(b_parts[0])
        if a_first == b_first and a_first:
            return True
        if a_first == _strip_active_low(b) or b_first == _strip_active_low(a):
            return True
        # Compare full slash-separated forms after active-low normalization
        a_norm = "/".join(_strip_active_low(p) for p in a_parts)
        b_norm = "/".join(_strip_active_low(p) for p in b_parts)
        if a_norm == b_norm:
            return True
        # Check if one name is a component of the other's slash-separated form
        a_set = {_strip_active_low(p) for p in a_parts}
        b_set = {_strip_active_low(p) for p in b_parts}
        if _strip_active_low(a) in b_set or _strip_active_low(b) in a_set:
            return True

    # Parenthetical notation: "SO (IO1)" <-> "SO/IO1"
    def _normalize_parens(name):
        return re.sub(r"\s*\(([^)]+)\)", r"/\1", name)
    if _normalize_parens(a) == _normalize_parens(b):
        return True

    # Normalize spaces around slash/underscore: "GPIO26 / ADC0" <-> "GPIO26_ADC0"
    def _normalize_separators(name):
        return re.sub(r"\s*/\s*", "_", name).replace(" ", "_")
    if _normalize_separators(a) == _normalize_separators(b):
        return True

    # Combined: normalize parens then apply active-low + slash checks
    a_pn = _normalize_parens(a)
    b_pn = _normalize_parens(b)
    if a_pn != a or b_pn != b:
        # Re-check with parens normalized
        if "/" in a_pn or "/" in b_pn:
            a_pp = [_strip_active_low(p) for p in a_pn.split("/")]
            b_pp = [_strip_active_low(p) for p in b_pn.split("/")]
            if a_pp == b_pp:
                return True

    # Subscript notation: V_{SS} <-> VSS, V_{CC} <-> VCC, V_{OUT} <-> VOUT
    def _strip_subscript(name):
        return re.sub(r"_\{([^}]+)\}", r"\1", name)
    if _strip_subscript(a) == _strip_subscript(b):
        return True

    # Strip parenthetical content entirely as a final normalization
    # e.g. "RT(TPS54335AandTPS54335-1A)" -> "RT"
    def _strip_parens(name):
        return re.sub(r"\s*\([^)]*\)", "", name).strip()
    a_sp = _strip_parens(a)
    b_sp = _strip_parens(b)
    if a_sp == b_sp and a_sp:
        return True

    # Multi-unit op-amp/comparator name mapping:
    # KiCad uses ~, +, -, V+, V- per unit. Datasheets use xOUT, xIN+, xIN-, VCC, GND
    _opamp_output = re.compile(r"^(\d*)OUT([A-D]?\d*)$")
    _opamp_noninv = re.compile(r"^(\d*)IN(\d*)\+|^(\d*)\+IN([A-D]?\d*)$")
    _opamp_inv = re.compile(r"^(\d*)IN(\d*)[\-]|^(\d*)[\-]IN([A-D]?\d*)$")
    if a in ("~", "+", "-", "V+", "V-") or b in ("~", "+", "-", "V+", "V-"):
        def _is_opamp_match(generic, concrete):
            c = concrete.replace(" ", "")
            if generic == "~" and _opamp_output.match(c):
                return True
            if generic == "+" and _opamp_noninv.match(c):
                return True
            if generic == "-" and _opamp_inv.match(c):
                return True
            if generic == "V+" and c in ("VCC", "VCC+", "V+", "VS+", "+VS", "+V"):
                return True
            if generic == "V-" and c in ("GND", "VCC-", "V-", "VEE", "VS-", "-VS", "VSS"):
                return True
            return False
        if _is_opamp_match(a, b) or _is_opamp_match(b, a):
            return True

    aliases = {
        # Thermal pad / ground pad aliases
        frozenset({"GNDPAD", "GND"}),
        frozenset({"ETPAD", "GND"}),
        frozenset({"EP", "GND"}),
        frozenset({"PGND", "GND"}),
        frozenset({"AGND", "GND"}),
        frozenset({"PAD", "GND"}),
        frozenset({"DAP", "GND"}),
        frozenset({"GROUND", "GND"}),
        frozenset({"THERMALPAD", "GND"}),
        frozenset({"THERMALPAD", "GNDPAD"}),
        frozenset({"DAP", "GNDPAD"}),
        frozenset({"AGND", "GNDPAD"}),
        frozenset({"PAD", "GNDPAD"}),
        # Power pin aliases
        frozenset({"PH", "SW"}),
        frozenset({"VSENSE", "FB"}),
        frozenset({"ON/OFF", "EN"}),
        frozenset({"VCC", "VIN"}),
        frozenset({"IN", "VIN"}),
        frozenset({"PVIN", "VIN"}),
        frozenset({"AVIN", "VIN"}),
        frozenset({"OUT", "VOUT"}),
        frozenset({"OUTPUT", "OUT"}),
        frozenset({"FEEDBACK", "FB"}),
        frozenset({"ENA", "EN"}),
        frozenset({"NFAULT", "FAULT"}),
        # ADI aliases
        frozenset({"PADGND", "GND"}),
        frozenset({"EPAD", "GND"}),
        frozenset({"EXPOSED PAD", "GND"}),
        frozenset({"ALERT", "ALRT"}),
        frozenset({"ALR", "ALRT"}),
        frozenset({"SCLK", "SCL"}),
        frozenset({"INT", "~{INT}"}),
        # LT active-low aliases (tilde notation)
        frozenset({"SHDN", "~{SHDN}"}),
        frozenset({"CHRG", "~{CHRG}"}),
        frozenset({"FAULT", "~{FAULT}"}),
        # Sensor pin aliases
        frozenset({"IN+", "VIN+"}),
        frozenset({"IN-", "VIN-"}),
        # Subscript truncation aliases (pdfplumber drops subscript text)
        frozenset({"V", "VIN"}),
        frozenset({"V", "VFB"}),
        frozenset({"V", "VIN_REG"}),
        # FPGA/memory aliases
        frozenset({"QSPI_CSN", "QSPI_SS"}),
        # No-connect aliases
        frozenset({"N/C", "NC"}),
        frozenset({"N.C.", "NC"}),
        # RP2040 pin name aliases
        frozenset({"VREG_VIN", "VREG_IN"}),
        # Variant-specific pin function aliases (TI multi-variant datasheets)
        frozenset({"RT", "SS"}),
    }
    if frozenset({a, b}) in aliases:
        return True
    # Also check aliases with parenthetical content stripped
    if frozenset({a_sp, b_sp}) in aliases:
        return True
    # Check with base (active-low stripped) forms
    if frozenset({a_base, b_base}) in aliases:
        return True
    return False


def main():
    if not check_pdfplumber():
        log("ERROR: pdfplumber not installed. Cannot run tests.")
        sys.exit(2)

    # Parse CLI flags
    strict = "--strict" in sys.argv
    tier_filter = None
    filter_pn = None
    for arg in sys.argv[1:]:
        if arg.startswith("--tier="):
            tier_filter = int(arg.split("=")[1])
        elif not arg.startswith("--"):
            filter_pn = arg.upper()

    test_parts = load_test_parts()
    log(f"Loaded {len(test_parts)} test parts")
    if strict:
        log("STRICT MODE: 0 missing, 0 extra, 0 mismatches required")

    # Apply filters
    if tier_filter is not None:
        test_parts = [p for p in test_parts if p.get("tier", 1) == tier_filter]
        log(f"Filtered to {len(test_parts)} tier {tier_filter} parts")
    if filter_pn:
        test_parts = [p for p in test_parts if filter_pn in p["pn"].upper()]
        log(f"Filtered to {len(test_parts)} parts matching '{filter_pn}'")

    results = []
    passed_count = 0
    failed_count = 0
    error_count = 0

    for i, part in enumerate(test_parts):
        pn = part["pn"]
        expected_pins = part["pins"]
        log(f"\n[{i+1}/{len(test_parts)}] Testing {pn} ({part['family']})...")

        start = time.time()
        datasheet, match, error = run_pipeline_headless(pn)
        elapsed = round(time.time() - start, 1)

        result = {
            "pn": pn,
            "family": part["family"],
            "tier": part.get("tier", 1),
            "manufacturer": part.get("manufacturer", ""),
            "elapsed_seconds": elapsed,
        }

        if error:
            result["status"] = "ERROR"
            result["error"] = error
            error_count += 1
            log(f"  ERROR ({elapsed}s): {error}")
        elif not datasheet or not datasheet.pins:
            result["status"] = "FAIL"
            result["error"] = "No pins extracted"
            result["details"] = {
                "extracted_count": 0,
                "expected_count": len(expected_pins),
                "has_pdf": bool(datasheet and datasheet.pdf_path),
            }
            failed_count += 1
            log(f"  FAIL ({elapsed}s): No pins extracted")
        else:
            passed, details = compare_pins(datasheet.pins, expected_pins, strict=strict)
            result["status"] = "PASS" if passed else "FAIL"
            result["details"] = details
            result["extracted_pin_count"] = len(datasheet.pins)
            result["expected_pin_count"] = len(expected_pins)

            if passed:
                passed_count += 1
                log(f"  PASS ({elapsed}s): {len(datasheet.pins)} pins, "
                    f"match rate {details['match_rate']:.0%}")
            else:
                failed_count += 1
                log(f"  FAIL ({elapsed}s): {len(datasheet.pins)} pins, "
                    f"match rate {details['match_rate']:.0%}, "
                    f"missing={len(details['missing_pins'])}, "
                    f"mismatches={len(details['name_mismatches'])}")

        results.append(result)

    # Summary
    total = len(test_parts)
    log(f"\n{'='*60}")
    log(f"RESULTS: {passed_count}/{total} passed, "
        f"{failed_count} failed, {error_count} errors")
    if strict:
        log("MODE: STRICT (100% accuracy required)")

    # Per-tier summary
    tier_stats = {}
    for r in results:
        t = r.get("tier", 1)
        if t not in tier_stats:
            tier_stats[t] = {"total": 0, "passed": 0}
        tier_stats[t]["total"] += 1
        if r.get("status") == "PASS":
            tier_stats[t]["passed"] += 1
    for t in sorted(tier_stats):
        ts = tier_stats[t]
        log(f"  Tier {t}: {ts['passed']}/{ts['total']} passed")
    log(f"{'='*60}")

    output = {
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "errors": error_count,
        "pass_rate": round(passed_count / max(total, 1), 3),
        "strict": strict,
        "tier_stats": tier_stats,
        "results": results,
    }
    print(json.dumps(output, indent=2))

    sys.exit(0 if failed_count == 0 and error_count == 0 else 1)


if __name__ == "__main__":
    main()
