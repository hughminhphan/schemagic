#!/usr/bin/env python3
"""
Comprehensive edge case tests for schemagic plugin.

Run with: python3 test_edge_cases.py
Or from KiCad Python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 test_edge_cases.py
"""

import sys
import os
import traceback
import tempfile
import shutil

# Import path is set up by conftest.py when run via pytest,
# or manually here for standalone execution.
os.environ["SCHEMAGIC_STANDALONE"] = "1"
if __name__ == "__main__":
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)

# Import the modules under test
from engine.core.models import PinInfo, PackageInfo, DatasheetData
from engine.core.config import strip_ti_suffix, PACKAGE_MAP
from engine.datasheet.pin_extractor import (
    _merge_header_rows, _is_pin_table, _find_columns, _is_section_header,
    _parse_pin_numbers, infer_pin_type, _parse_io_type, _detect_headers,
    extract_pins_from_tables, extract_pins_from_text,
    _extract_pins_from_single_table,
)
from engine.datasheet.package_identifier import (
    identify_package_from_part_number, identify_package_from_text,
    identify_all_packages, identify_package,
)
from engine.generation.sexpr import (
    SExprNode, parse, serialize, _tokenize, _unquote, _is_bare, _quote,
    regenerate_uuids,
)
from engine.generation.symbol_modifier import (
    create_empty_symbol, _fmt, _rename_symbol,
)
from engine.generation.library_manager import (
    _save_symbol_to_lib, _ensure_lib_table, _make_lib_entry,
)
from engine.matching.symbol_matcher import (
    _build_pin_mapping, _pin_name_overlap,
)


# ── Test infrastructure ──────────────────────────────────────────────────────

_pass_count = 0
_fail_count = 0
_error_count = 0
_current_section = ""
_failures = []


def section(name):
    global _current_section
    _current_section = name
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def check(name, condition, detail=""):
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        print(f"  PASS  {name}")
    else:
        _fail_count += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        _failures.append((_current_section, name, detail))


def check_eq(name, actual, expected):
    detail = f"expected {expected!r}, got {actual!r}"
    check(name, actual == expected, detail if actual != expected else "")


def check_in(name, needle, haystack):
    detail = f"{needle!r} not found in {haystack!r}"
    check(name, needle in haystack, detail if needle not in haystack else "")


def check_raises(name, fn, exc_type=Exception):
    try:
        fn()
        check(name, False, f"expected {exc_type.__name__}, no exception raised")
    except exc_type:
        check(name, True)
    except Exception as e:
        check(name, False, f"expected {exc_type.__name__}, got {type(e).__name__}: {e}")


# ── Pin Extractor Tests ──────────────────────────────────────────────────────

def test_parse_pin_numbers():
    section("_parse_pin_numbers edge cases")

    # Basic
    check_eq("single digit", _parse_pin_numbers("5"), ["5"])
    check_eq("comma separated", _parse_pin_numbers("2,3,4"), ["2", "3", "4"])

    # Empty / None
    check_eq("empty string", _parse_pin_numbers(""), [])
    check_eq("None", _parse_pin_numbers(None), [])

    # Whitespace only
    check_eq("whitespace only", _parse_pin_numbers("   "), [])

    # Newline separated (common in pdfplumber output)
    check_eq("newline separated", _parse_pin_numbers("1\n2\n3"), ["1", "2", "3"])

    # Mixed delimiters
    check_eq("mixed delimiters", _parse_pin_numbers("1,2\n3;4"), ["1", "2", "3", "4"])

    # Thermal pad variants
    check_eq("Thermal pad", _parse_pin_numbers("Thermal pad"), ["EP"])
    check_eq("ThermalPad", _parse_pin_numbers("ThermalPad"), ["EP"])
    check_eq("thermal pad lower", _parse_pin_numbers("thermal pad"), ["EP"])
    check_eq("PowerPAD", _parse_pin_numbers("PowerPAD"), ["EP"])
    check_eq("power pad", _parse_pin_numbers("power pad"), ["EP"])
    check_eq("EP", _parse_pin_numbers("EP"), ["EP"])
    check_eq("E.P.", _parse_pin_numbers("E.P."), ["EP"])
    check_eq("EPAD", _parse_pin_numbers("EPAD"), ["EP"])
    check_eq("Exposed pad", _parse_pin_numbers("Exposed pad"), ["EP"])
    check_eq("exposed pad", _parse_pin_numbers("exposed pad"), ["EP"])

    # Mixed numbers and thermal pad
    check_eq("numbers + thermal", _parse_pin_numbers("1,12,13,24,\nThermal pad"),
             ["1", "12", "13", "24", "EP"])

    # Completely non-numeric non-pad text → empty
    check_eq("random text ignored", _parse_pin_numbers("see note 5"), [])

    # Leading/trailing whitespace in parts
    check_eq("whitespace in parts", _parse_pin_numbers(" 1 , 2 , 3 "), ["1", "2", "3"])

    # Semicolons
    check_eq("semicolons", _parse_pin_numbers("1;2;3"), ["1", "2", "3"])

    # Very large pin numbers
    check_eq("large pin number", _parse_pin_numbers("999"), ["999"])

    # Pin 0 (some packages have pin 0)
    check_eq("pin zero", _parse_pin_numbers("0"), ["0"])

    # BUG HUNT: Pin number with text suffix (e.g. "5A")
    result = _parse_pin_numbers("5A")
    check("alphanumeric pin '5A' should either parse or be empty",
          result == [] or result == ["5A"],
          f"got {result}")

    # BUG HUNT: Dash as pin number (exposed pad indicator)
    result = _parse_pin_numbers("-")
    check_eq("dash pin number → empty", result, [])

    # BUG HUNT: "PAD" alone
    result = _parse_pin_numbers("PAD")
    check_eq("PAD alone → EP", result, ["EP"])


def test_merge_header_rows():
    section("_merge_header_rows edge cases")

    # Normal TI split header
    merged = _merge_header_rows(
        ["", "PIN", "I/O(1)", "DESCRIPTION"],
        ["NAME", "NO.", "", ""]
    )
    check_eq("TI split header", merged, ["NAME", "PIN NO.", "I/O(1)", "DESCRIPTION"])

    # Unequal lengths (row0 shorter)
    merged = _merge_header_rows(["A", "B"], ["C", "D", "E"])
    check_eq("row0 shorter", merged, ["A C", "B D", "E"])

    # Unequal lengths (row1 shorter)
    merged = _merge_header_rows(["A", "B", "C"], ["D", "E"])
    check_eq("row1 shorter", merged, ["A D", "B E", "C"])

    # Both empty
    merged = _merge_header_rows([], [])
    check_eq("both empty", merged, [])

    # None cells
    merged = _merge_header_rows([None, "PIN"], ["NAME", None])
    check_eq("None cells", merged, ["NAME", "PIN"])

    # All None
    merged = _merge_header_rows([None, None], [None, None])
    check_eq("all None", merged, ["", ""])

    # Whitespace-only cells
    merged = _merge_header_rows(["  ", "PIN"], ["NAME", "  "])
    check_eq("whitespace cells treated as empty",
             merged, ["NAME", "PIN"])


def test_is_pin_table():
    section("_is_pin_table edge cases")

    # Standard headers
    check("standard pin+name", _is_pin_table(["Pin", "Name", "Description"]))
    check("standard PIN NO. + NAME", _is_pin_table(["NAME", "PIN NO.", "TYPE"]))

    # Missing name → not a pin table
    check("pin only, no name", not _is_pin_table(["Pin", "Description", "Notes"]))

    # Missing pin → not a pin table
    check("name only, no pin", not _is_pin_table(["Name", "Description", "Notes"]))

    # Empty list
    check("empty list", not _is_pin_table([]))

    # All None
    check("all None", not _is_pin_table([None, None, None]))

    # Case insensitive
    check("case insensitive", _is_pin_table(["PIN", "NAME", "DESCRIPTION"]))

    # Multi-package header: "PIN PWP"
    check("multi-package PIN PWP", _is_pin_table(["Name", "PIN PWP", "TYPE"]))

    # Should NOT match "PIN NAME" as a pin column (it's name!)
    # "PIN NAME" matches name pattern, so we need another pin column
    check("PIN NAME only → not pin table",
          not _is_pin_table(["PIN NAME", "TYPE", "DESCRIPTION"]))


def test_find_columns():
    section("_find_columns edge cases")

    # Standard layout
    pin, name, typ, desc, alt = _find_columns(["Name", "Pin No.", "I/O", "Description"])
    check_eq("name col", name, 0)
    check_eq("pin col", pin, 1)
    check_eq("type col", typ, 2)
    check_eq("desc col", desc, 3)
    check_eq("no alt func cols", alt, [])

    # No type/desc columns
    pin, name, typ, desc, alt = _find_columns(["Name", "Pin No."])
    check_eq("no type col", typ, None)
    check_eq("no desc col", desc, None)

    # Name column should win over pin for "PIN NAME"
    pin, name, typ, desc, alt = _find_columns(["PIN NAME", "PIN NO.", "TYPE"])
    check("PIN NAME goes to name_col", name == 0,
          f"name={name}")
    check("PIN NO. goes to pin_col", pin == 1,
          f"pin={pin}")

    # Multi-package: merged header "PIN PWP" alongside NAME
    pin, name, typ, desc, alt = _find_columns(["NAME", "PIN PWP", "RTE", "TYPE", "", "DESCRIPTION"])
    check_eq("multi-pkg name col", name, 0)
    check_eq("multi-pkg pin col", pin, 1)
    check_eq("multi-pkg type col", typ, 3)
    check_eq("multi-pkg desc col", desc, 5)

    # All None headers
    pin, name, typ, desc, alt = _find_columns([None, None, None])
    check_eq("all None - no columns", (pin, name, typ, desc), (None, None, None, None))

    # Alternate function column detection (MCU datasheets)
    pin, name, typ, desc, alt = _find_columns(["Pin No.", "Name", "Type", "Alternate Functions"])
    check_eq("alt func col detected", alt, [3])


def test_is_section_header():
    section("_is_section_header edge cases")

    # Standard section headers
    check("POWER AND GROUND", _is_section_header(["POWER AND GROUND", None, None, None]))
    check("CONTROL", _is_section_header(["CONTROL", None, None, None]))
    check("OUTPUT", _is_section_header(["OUTPUT", "", "", ""]))

    # No-space variants (pdfplumber artifact)
    check("POWERANDGROUND", _is_section_header(["POWERANDGROUND", None, None, None]))
    check("CONTROLOUTPUT", _is_section_header(["CONTROLOUTPUT", None, None, None]))

    # Not a section header — multiple non-empty cells
    check("data row", not _is_section_header(["GND", "1", "P", "Ground"]))

    # Empty row
    check("empty row", not _is_section_header(["", "", "", ""]))
    check("all None row", not _is_section_header([None, None, None, None]))

    # Non-keyword text
    check("random text", not _is_section_header(["DRV8850", None, None, None]))

    # Mixed case
    check("mixed case Power", _is_section_header(["Power", None, None]))

    # BUG HUNT: "STATUS" is a keyword but very short — could be a pin name
    check("STATUS as section", _is_section_header(["STATUS", None, None, None]))

    # BUG HUNT: "SIGNAL" in keyword set but also column header
    check("SIGNAL single", _is_section_header(["SIGNAL", None, None, None]))

    # BUG HUNT: A real pin name that contains only section keywords
    # "DIGITAL INPUT" — has 2 non-empty cells? No, it's one cell with two words
    check("DIGITAL INPUT", _is_section_header(["DIGITAL INPUT", None, None]))


def test_parse_io_type():
    section("_parse_io_type edge cases")

    check_eq("I → input", _parse_io_type("I"), "input")
    check_eq("O → output", _parse_io_type("O"), "output")
    check_eq("I/O → bidirectional", _parse_io_type("I/O"), "bidirectional")
    check_eq("IO → bidirectional", _parse_io_type("IO"), "bidirectional")
    check_eq("P → power_in", _parse_io_type("P"), "power_in")
    check_eq("OD → open_collector", _parse_io_type("OD"), "open_collector")

    # Em-dashes (common in TI for power/ground)
    check_eq("em-dash → None", _parse_io_type("—"), None)
    check_eq("unicode em-dash → None", _parse_io_type("\u2014"), None)
    check_eq("hyphen → None", _parse_io_type("-"), None)

    # None / empty
    check_eq("None → None", _parse_io_type(None), None)
    check_eq("empty → None", _parse_io_type(""), None)

    # Whitespace
    check_eq("whitespace I", _parse_io_type("  I  "), "input")

    # Case sensitivity
    check_eq("lowercase i", _parse_io_type("i"), "input")
    check_eq("lowercase pwr", _parse_io_type("pwr"), "power_in")

    # BUG HUNT: Unknown type string
    result = _parse_io_type("TRISTATE")
    check_eq("TRISTATE → None (not mapped)", result, None)

    # BUG HUNT: "HI-Z" or "Hi-Z" — common in some datasheets
    result = _parse_io_type("HI-Z")
    check_eq("HI-Z → None (not mapped)", result, None)

    # BUG HUNT: "ANALOG" → passive
    check_eq("ANALOG → passive", _parse_io_type("ANALOG"), "passive")

    # BUG HUNT: "A" → passive (Analog)
    check_eq("A → passive", _parse_io_type("A"), "passive")


def test_infer_pin_type():
    section("infer_pin_type edge cases")

    # Power supply pins
    check_eq("VCC", infer_pin_type("VCC"), "power_in")
    check_eq("VDD", infer_pin_type("VDD"), "power_in")
    check_eq("VIN", infer_pin_type("VIN"), "power_in")
    check_eq("VBAT", infer_pin_type("VBAT"), "power_in")
    check_eq("VM", infer_pin_type("VM"), "power_in")
    check_eq("VS", infer_pin_type("VS"), "power_in")
    check_eq("DVDD", infer_pin_type("DVDD"), "power_in")
    check_eq("AVDD", infer_pin_type("AVDD"), "power_in")
    check_eq("PVDD", infer_pin_type("PVDD"), "power_in")

    # Ground
    check_eq("GND", infer_pin_type("GND"), "power_in")
    check_eq("AGND", infer_pin_type("AGND"), "power_in")
    check_eq("PGND", infer_pin_type("PGND"), "power_in")
    check_eq("EP", infer_pin_type("EP"), "power_in")
    check_eq("PAD", infer_pin_type("PAD"), "power_in")

    # Power outputs
    check_eq("VOUT", infer_pin_type("VOUT"), "power_out")
    check_eq("VSW", infer_pin_type("VSW"), "power_out")
    check_eq("SW", infer_pin_type("SW"), "power_out")
    check_eq("LX", infer_pin_type("LX"), "power_out")

    # Control inputs
    check_eq("EN", infer_pin_type("EN"), "input")
    check_eq("NEN", infer_pin_type("NEN"), "input")
    check_eq("ENABLE", infer_pin_type("ENABLE"), "input")
    check_eq("NSLEEP", infer_pin_type("NSLEEP"), "input")
    check_eq("NRESET", infer_pin_type("NRESET"), "input")
    check_eq("FB", infer_pin_type("FB"), "input")
    check_eq("CLK", infer_pin_type("CLK"), "input")

    # Motor driver
    check_eq("AIN1", infer_pin_type("AIN1"), "input")
    check_eq("BIN2", infer_pin_type("BIN2"), "input")
    check_eq("AOUT1", infer_pin_type("AOUT1"), "output")
    check_eq("GHA", infer_pin_type("GHA"), "output")
    check_eq("GL1", infer_pin_type("GL1"), "output")

    # Open collector
    check_eq("PGOOD", infer_pin_type("PGOOD"), "open_collector")
    check_eq("PG", infer_pin_type("PG"), "open_collector")
    check_eq("NFAULT", infer_pin_type("NFAULT"), "open_collector")
    check_eq("FAULT", infer_pin_type("FAULT"), "open_collector")

    # No connect
    check_eq("NC", infer_pin_type("NC"), "no_connect")
    check_eq("N.C.", infer_pin_type("N.C."), "no_connect")
    check_eq("DNC", infer_pin_type("DNC"), "no_connect")

    # I2C
    check_eq("SDA", infer_pin_type("SDA"), "bidirectional")
    check_eq("SCL", infer_pin_type("SCL"), "input")

    # Passive
    check_eq("BOOT", infer_pin_type("BOOT"), "passive")
    check_eq("BST", infer_pin_type("BST"), "passive")
    check_eq("RT", infer_pin_type("RT"), "passive")
    check_eq("COMP", infer_pin_type("COMP"), "passive")
    check_eq("VREF", infer_pin_type("VREF"), "passive")

    # Fallback to description
    check_eq("unknown name, power supply desc",
             infer_pin_type("XYZZY", "power supply input"), "power_in")
    check_eq("unknown name, ground desc",
             infer_pin_type("XYZZY", "signal ground"), "power_in")
    check_eq("unknown name, no desc → passive",
             infer_pin_type("XYZZY"), "passive")

    # BUG HUNT: Case sensitivity — patterns use uppercase match
    check_eq("lowercase vcc", infer_pin_type("vcc"), "power_in")
    check_eq("lowercase gnd", infer_pin_type("gnd"), "power_in")

    # BUG HUNT: Pin name with spaces
    check_eq("THERMAL PAD", infer_pin_type("THERMAL PAD"), "power_in")

    # BUG HUNT: Pin name with embedded newline (after cleanup)
    check_eq("VM (no newline)", infer_pin_type("VM"), "power_in")

    # BUG HUNT: OUT matches both OUT and OUT1/OUTA patterns
    check_eq("OUT alone", infer_pin_type("OUT"), "output")
    check_eq("OUT1", infer_pin_type("OUT1"), "output")
    check_eq("OUTA", infer_pin_type("OUTA"), "output")

    # BUG HUNT: "IN" by itself
    check_eq("IN alone", infer_pin_type("IN"), "input")

    # BUG HUNT: Description has both "input" and "output"
    result = infer_pin_type("XYZZY", "this is an input/output buffer")
    check("ambiguous input/output desc → passive fallback",
          result == "passive",
          f"got {result}")

    # BUG HUNT: "VREG" — could be power_in or power_out
    check_eq("VREG", infer_pin_type("VREG"), "power_out")

    # BUG HUNT: Multi-character suffixes on power
    check_eq("VBUS", infer_pin_type("VBUS"), "power_in")
    check_eq("VSYS", infer_pin_type("VSYS"), "power_in")


def test_detect_headers():
    section("_detect_headers edge cases")

    # Single-row header
    table = [["Name", "Pin No.", "Type", "Description"], ["GND", "1", "P", "Ground"]]
    headers, start = _detect_headers(table)
    check("single-row header found", headers is not None)
    check_eq("single-row data start", start, 1)

    # Two-row header (TI style)
    table = [
        ["", "PIN", "", "TYPE", "", "DESCRIPTION"],
        ["NAME", "NO.", "", "", "", ""],
        ["GND", "1", "", "P", "", "Ground"],
    ]
    headers, start = _detect_headers(table)
    check("two-row header found", headers is not None)
    check_eq("two-row data start", start, 2)

    # Row 0 is title, row 1 is header
    table = [
        ["Pin Assignments"],
        ["Name", "Pin No.", "Type"],
        ["GND", "1", "P"],
    ]
    headers, start = _detect_headers(table)
    check("title + single header found", headers is not None)
    check_eq("title + single header data start", start, 2)

    # Too small table
    table = [["Name"]]
    headers, start = _detect_headers(table)
    check_eq("1-row table → None", headers, None)

    # Empty table
    table = []
    headers, start = _detect_headers(table)
    check_eq("empty table → None", headers, None)

    # No pin table structure at all
    table = [["Spec", "Min", "Max"], ["Voltage", "3.3", "5.0"]]
    headers, start = _detect_headers(table)
    check_eq("non-pin table → None", headers, None)

    # BUG HUNT: Table with title row and two-row split header (rows 1+2)
    table = [
        ["Table 1. Pin Assignments"],
        ["", "PIN", "TYPE"],
        ["NAME", "NO.", ""],
        ["GND", "1", "P"],
    ]
    headers, start = _detect_headers(table)
    check("title + split header found", headers is not None,
          f"headers={headers}")
    if headers is not None:
        check_eq("title + split header data start", start, 3)


def test_extract_pins_from_tables():
    section("extract_pins_from_tables edge cases")

    # Simple valid table
    tables = [(1, [
        ["Name", "Pin No.", "I/O", "Description"],
        ["VCC", "1", "P", "Power supply"],
        ["GND", "2", "P", "Ground"],
        ["IN", "3", "I", "Input"],
        ["OUT", "4", "O", "Output"],
    ])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("simple table pin count", len(pins), 4)
    check("simple table confidence > 0", conf > 0)
    check_eq("pin 1 name", pins[0].name, "VCC")
    check_eq("pin 1 type", pins[0].pin_type, "power_in")

    # Empty tables list
    pins, conf = extract_pins_from_tables([])
    check_eq("empty tables → 0 pins", len(pins), 0)
    check_eq("empty tables → 0 confidence", conf, 0.0)

    # Table with no valid pin headers
    tables = [(1, [["Spec", "Min", "Max"], ["Voltage", "3.3", "5.0"]])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("non-pin table → 0 pins", len(pins), 0)

    # Duplicate pin numbers — should deduplicate
    tables = [(1, [
        ["Name", "Pin No.", "I/O", "Description"],
        ["VCC", "1", "P", "Power supply"],
        ["VCC", "1", "P", "Power supply"],  # duplicate
        ["GND", "2", "P", "Ground"],
    ])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("deduped pin count", len(pins), 2)

    # Multi-page table merging
    tables = [
        (1, [
            ["Name", "Pin No.", "I/O", "Description"],
            ["VCC", "1", "P", "Power supply"],
            ["GND", "2", "P", "Ground"],
        ]),
        (2, [
            ["Name", "Pin No.", "I/O", "Description"],
            ["IN", "3", "I", "Input"],
            ["OUT", "4", "O", "Output"],
        ]),
    ]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("multi-page merged pin count", len(pins), 4)

    # expected_pin_count selection
    tables = [
        (1, [
            ["Name", "Pin No.", "I/O", "Description"],
            ["VCC", "1", "P", "Power supply"],
            ["GND", "2", "P", "Ground"],
        ]),
        (3, [  # different table on page 3
            ["Name", "Pin", "Description"],
            ["A", "1", "Signal A"],
            ["B", "2", "Signal B"],
            ["C", "3", "Signal C"],
        ]),
    ]
    pins, conf = extract_pins_from_tables(tables, expected_pin_count=3)
    check_eq("expected count selects right table", len(pins), 3)

    # Continuation rows (type/desc inherited)
    tables = [(1, [
        ["Name", "Pin No.", "I/O", "Description"],
        ["AIN1", "3", "I", "Analog input channel"],
        ["AIN2", "4", None, None],  # continuation — should inherit I/O type
    ])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("continuation row count", len(pins), 2)
    check_eq("continuation row type inherited", pins[1].pin_type, "input")

    # Embedded newlines in pin names
    tables = [(1, [
        ["Name", "Pin No.", "I/O", "Description"],
        ["V\nM", "1", "P", "Motor supply"],
    ])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("embedded newline stripped", pins[0].name, "VM")

    # Section header rows skipped
    tables = [(1, [
        ["Name", "Pin No.", "I/O", "Description"],
        ["POWER AND GROUND", None, None, None],  # section header
        ["VCC", "1", "P", "Power supply"],
        ["GND", "2", "P", "Ground"],
    ])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("section header skipped", len(pins), 2)

    # Auto-add EP pin from description
    tables = [(1, [
        ["Name", "Pin No.", "I/O", "Description"],
        ["VCC", "1", "P", "Power supply, connect PowerPAD to ground"],
        ["GND", "2", "P", "Ground"],
    ])]
    pins, conf = extract_pins_from_tables(tables)
    ep_pins = [p for p in pins if p.number == "EP"]
    check_eq("auto-added EP pin", len(ep_pins), 1)

    # BUG HUNT: Table where pin column has non-numeric entries
    tables = [(1, [
        ["Name", "Pin No.", "I/O", "Description"],
        ["PAD", "-", "P", "Exposed thermal pad"],
        ["VCC", "1", "P", "Power supply"],
    ])]
    pins, conf = extract_pins_from_tables(tables)
    ep_pins = [p for p in pins if p.number == "EP"]
    check("thermal pad with dash pin number detected",
          len(ep_pins) >= 1,
          f"EP pins: {ep_pins}, all pins: {[(p.number, p.name) for p in pins]}")

    # BUG HUNT: Row with pin name but no pin number and no thermal pad keywords
    tables = [(1, [
        ["Name", "Pin No.", "I/O", "Description"],
        ["RESERVED", "", "I", "Do not connect"],
        ["VCC", "1", "P", "Power supply"],
    ])]
    pins, conf = extract_pins_from_tables(tables)
    reserved = [p for p in pins if p.name == "RESERVED"]
    check_eq("RESERVED with no pin number → skipped", len(reserved), 0)

    # BUG HUNT: Table with only 1 data row
    tables = [(1, [
        ["Name", "Pin No."],
        ["VCC", "1"],
    ])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("single data row", len(pins), 1)


def test_extract_pins_from_text():
    section("extract_pins_from_text edge cases")

    # Standard pattern
    text = "Pin 1 – VCC\nPin 2 – GND\nPin 3 – IN"
    pins, conf = extract_pins_from_text(text)
    check_eq("text extraction count", len(pins), 3)
    check("text confidence 0.3", conf == 0.3)

    # No pins
    pins, conf = extract_pins_from_text("This is just some random text")
    check_eq("no pins → empty", len(pins), 0)
    check_eq("no pins → 0 confidence", conf, 0.0)

    # Empty text
    pins, conf = extract_pins_from_text("")
    check_eq("empty text", len(pins), 0)

    # Very high pin numbers filtered (>200)
    text = "Pin 201 – TEST\nPin 1 – VCC"
    pins, conf = extract_pins_from_text(text)
    check_eq("pin >200 filtered", len(pins), 1)

    # Duplicate pin numbers deduplicated
    text = "Pin 1 – VCC\nPin 1 – VCC2"
    pins, conf = extract_pins_from_text(text)
    check_eq("text dedup", len(pins), 1)


# ── Package Identifier Tests ─────────────────────────────────────────────────

def test_package_from_part_number():
    section("identify_package_from_part_number edge cases")

    # Known TI codes
    pkg = identify_package_from_part_number("TPS54302PWP")
    check("TPS54302PWP → HTSSOP-16", pkg is not None and pkg.name == "HTSSOP-16")

    pkg = identify_package_from_part_number("TPS54302PWPR")
    check("TPS54302PWPR (reel) → HTSSOP-16",
          pkg is not None and pkg.name == "HTSSOP-16")

    pkg = identify_package_from_part_number("DRV8850RTE")
    check("DRV8850RTE → WQFN-16", pkg is not None and pkg.name == "WQFN-16")

    # Unknown suffix
    pkg = identify_package_from_part_number("XYZ123")
    check_eq("unknown suffix → None", pkg, None)

    # Empty/whitespace
    pkg = identify_package_from_part_number("")
    check_eq("empty → None", pkg, None)

    pkg = identify_package_from_part_number("  ")
    check_eq("whitespace → None", pkg, None)

    # BUG HUNT: Suffix that's a substring of another suffix
    # "DDC" vs "DDW" — check for correct matching
    pkg = identify_package_from_part_number("LM321DDC")
    check("LM321DDC → SOT-23-6", pkg is not None and pkg.name == "SOT-23-6",
          f"got {pkg}")

    # BUG HUNT: Part number that ends with something LIKE a code but isn't
    pkg = identify_package_from_part_number("ABC")  # "C" shouldn't match anything
    check_eq("short part number → None", pkg, None)

    # BUG HUNT: What if part number IS the code?
    pkg = identify_package_from_part_number("DDC")
    check("bare DDC → SOT-23-6", pkg is not None and pkg.name == "SOT-23-6",
          f"got {pkg}")


def test_package_from_text():
    section("identify_package_from_text edge cases")

    # Standard formats
    pkg = identify_package_from_text("Available in HTSSOP (44)")
    check("HTSSOP (44)", pkg is not None and pkg.name == "HTSSOP-44",
          f"got {pkg}")

    pkg = identify_package_from_text("44-Pin HTSSOP package")
    check("44-Pin HTSSOP", pkg is not None and pkg.name == "HTSSOP-44",
          f"got {pkg}")

    # SOT-23 without pin count → defaults to 3
    pkg = identify_package_from_text("Available in SOT-23 package")
    check("SOT-23 bare → SOT-23-3", pkg is not None and pkg.name == "SOT-23-3",
          f"got {pkg}")

    # QFN with negative lookbehind — should NOT match WQFN
    pkg = identify_package_from_text("Available in WQFN-16 package")
    check("WQFN-16 not matched as QFN",
          pkg is not None and pkg.name == "WQFN-16",
          f"got {pkg}")

    # HTSSOP should NOT match as TSSOP or SSOP
    packages = identify_all_packages("HTSSOP-44 package available")
    pkg_names = [p.name for p in packages]
    check("HTSSOP-44 no TSSOP substring", "TSSOP-44" not in pkg_names,
          f"got {pkg_names}")
    check("HTSSOP-44 no SSOP substring", "SSOP-44" not in pkg_names,
          f"got {pkg_names}")

    # BUG HUNT: Height spec that looks like a pin count
    pkg = identify_package_from_text("HTSSOP - 1.2 mm max height")
    check("height spec not matched",
          pkg is None or pkg.pin_count >= 10,
          f"got {pkg}")

    # BUG HUNT: Multiple packages in text
    packages = identify_all_packages("Available in SOT-23-6 and SOIC-8 packages")
    check("multiple packages found", len(packages) >= 2,
          f"got {[p.name for p in packages]}")

    # BUG HUNT: Empty text
    pkg = identify_package_from_text("")
    check_eq("empty text → None", pkg, None)

    # BUG HUNT: TO-252 / DPAK aliases
    pkg = identify_package_from_text("Available in DPAK")
    check("DPAK → TO-252", pkg is not None and pkg.name == "TO-252",
          f"got {pkg}")

    # BUG HUNT: SC-70-5
    pkg = identify_package_from_text("Available in SC-70-5 package")
    check("SC-70-5", pkg is not None and pkg.name == "SC-70-5",
          f"got {pkg}")

    # BUG HUNT: pin_count_hint prioritization
    pkg = identify_package_from_text("SOIC-8 and SOIC-14 available", pin_count_hint=14)
    check("pin count hint 14", pkg is not None and pkg.pin_count == 14,
          f"got {pkg}")


def test_identify_package():
    section("identify_package combined edge cases")

    # Part number takes priority over text
    pkg = identify_package("TPS54302PWP", "Available in SOT-23-6")
    check("PN suffix wins over text",
          pkg is not None and pkg.name == "HTSSOP-16",
          f"got {pkg}")

    # Falls back to text if no suffix
    pkg = identify_package("GENERIC123", "Available in SOIC-8")
    check("falls back to text",
          pkg is not None and pkg.name == "SOIC-8",
          f"got {pkg}")

    # Neither works
    pkg = identify_package("GENERIC123", "No package info here")
    check_eq("both fail → None", pkg, None)


# ── TI Suffix Stripping Tests ────────────────────────────────────────────────

def test_strip_ti_suffix():
    section("strip_ti_suffix edge cases")

    base, code = strip_ti_suffix("TPS54302PWP")
    check_eq("TPS54302PWP base", base, "TPS54302")
    check_eq("TPS54302PWP code", code, "PWP")

    base, code = strip_ti_suffix("TPS54302PWPR")
    check_eq("TPS54302PWPR base", base, "TPS54302")
    check_eq("TPS54302PWPR code", code, "PWP")

    base, code = strip_ti_suffix("DRV8850RTE")
    check_eq("DRV8850RTE base", base, "DRV8850")
    check_eq("DRV8850RTE code", code, "RTE")

    # No suffix
    base, code = strip_ti_suffix("LM358")
    check_eq("LM358 no suffix", base, "LM358")
    check_eq("LM358 no code", code, None)

    # Empty
    base, code = strip_ti_suffix("")
    check_eq("empty base", base, "")
    check_eq("empty code", code, None)

    # BUG HUNT: Suffix order matters — "DDCR" should be stripped before "DDC"
    base, code = strip_ti_suffix("LM321DDCR")
    check_eq("DDCR stripped first", base, "LM321")
    check_eq("DDCR code = DDC", code, "DDC")

    # BUG HUNT: Part number that happens to end with "R" (not a reel suffix)
    base, code = strip_ti_suffix("SOMEPARTDDR")
    # "DDR" is not in the suffix list, but should we check?
    # Actually TI_SUFFIXES doesn't have DDR, so no match expected
    check("DDR not a TI suffix", code is None or code != "DD",
          f"base={base}, code={code}")


# ── S-Expression Parser Tests ────────────────────────────────────────────────

def test_sexpr_parse():
    section("sexpr parse edge cases")

    # Basic parsing
    nodes = parse("(hello world)")
    check_eq("basic tag", nodes[0].tag, "hello")
    check_eq("basic value", nodes[0].values, ["world"])

    # Nested
    nodes = parse("(a (b c))")
    check_eq("nested tag", nodes[0].children[0].tag, "b")
    check_eq("nested value", nodes[0].children[0].values, ["c"])

    # Multiple top-level
    nodes = parse("(a 1)(b 2)")
    check_eq("multi top-level count", len(nodes), 2)

    # Quoted strings
    nodes = parse('(prop "Hello World" "value with spaces")')
    check_eq("quoted value 1", nodes[0].values[0], "Hello World")
    check_eq("quoted value 2", nodes[0].values[1], "value with spaces")

    # Escaped quotes inside strings
    nodes = parse(r'(prop "say \"hello\"")')
    check_eq("escaped quotes", nodes[0].values[0], 'say "hello"')

    # Empty expression
    nodes = parse("(empty)")
    check_eq("empty node values", nodes[0].values, [])
    check_eq("empty node children", nodes[0].children, [])

    # Empty input
    nodes = parse("")
    check_eq("empty input", len(nodes), 0)

    # Whitespace only
    nodes = parse("   \n\t  ")
    check_eq("whitespace only", len(nodes), 0)

    # BUG HUNT: Unterminated expression
    check_raises("unterminated (", lambda: parse("(hello"), ValueError)

    # BUG HUNT: Extra closing paren (stray atoms at top level skipped)
    nodes = parse("(a b) )")
    check_eq("extra close paren → parse succeeds", len(nodes), 1)

    # BUG HUNT: Very deeply nested — invalid S-expr, but should give clear error
    deep = "(" * 50 + "x" + ")" * 50
    check_raises("deep nesting gives ValueError", lambda: parse(deep), ValueError)

    # Empty expression () handled gracefully
    nodes = parse("()")
    check("empty parens don't crash", True)

    # BUG HUNT: Numeric values
    nodes = parse("(version 20231120)")
    check_eq("numeric value stored as string", nodes[0].values[0], "20231120")

    # BUG HUNT: Negative numbers
    nodes = parse("(at -1.27 2.54 0)")
    check_eq("negative number", nodes[0].values[0], "-1.27")

    # BUG HUNT: Empty quoted string
    nodes = parse('(name "")')
    check_eq("empty quoted string", nodes[0].values[0], "")

    # BUG HUNT: String with backslashes
    # NOTE: _unquote only handles \" → ", not \\ → \
    # This means round-tripping doubles backslashes (pre-existing issue,
    # not relevant for KiCad on macOS/Linux where paths use forward slashes)
    nodes = parse(r'(path "C:\\Users\\test")')
    check_eq("backslash path", nodes[0].values[0], "C:\\\\Users\\\\test")


def test_sexpr_serialize():
    section("sexpr serialize edge cases")

    # Round-trip: parse then serialize
    original = '(kicad_symbol_lib (version 20231120) (generator "schemagic"))\n'
    nodes = parse(original)
    result = serialize(nodes)
    # Re-parse to verify structural equivalence
    nodes2 = parse(result)
    check_eq("round-trip tag", nodes2[0].tag, "kicad_symbol_lib")

    # BUG HUNT: version must NOT be quoted
    nodes = parse("(version 20231120)")
    result = serialize(nodes)
    check("version unquoted", '"20231120"' not in result,
          f"version was quoted: {result}")
    check("version present", "20231120" in result)

    # BUG HUNT: generator_version must NOT be quoted
    nodes = parse('(generator_version "1.0")')
    result = serialize(nodes)
    # generator_version is not in _ALWAYS_QUOTE_VALUES
    # but "1.0" looks like a number so _is_bare returns True
    check("generator_version 1.0 bare", "1.0" in result)

    # BUG HUNT: name tag MUST be quoted
    nodes = parse('(name "VCC")')
    result = serialize(nodes)
    check("name value quoted", '"VCC"' in result,
          f"got: {result}")

    # BUG HUNT: number tag MUST be quoted
    nodes = parse('(number "1")')
    result = serialize(nodes)
    check("number value quoted", '"1"' in result,
          f"got: {result}")

    # BUG HUNT: bare keywords stay unquoted
    nodes = parse("(pin power_in line)")
    result = serialize(nodes)
    check("power_in bare", "power_in" in result and '"power_in"' not in result,
          f"got: {result}")

    # BUG HUNT: property tag forces quoting
    nodes = parse('(property "Value" "TPS54302")')
    result = serialize(nodes)
    check("property values quoted", '"Value"' in result and '"TPS54302"' in result,
          f"got: {result}")

    # BUG HUNT: Empty string serialization
    nodes = [SExprNode("options", [""])]
    result = serialize(nodes)
    check("empty string in options quoted", '""' in result,
          f"got: {result}")

    # BUG HUNT: Serialize node with zero values
    nodes = [SExprNode("empty")]
    result = serialize(nodes)
    check("tagonly node", "(empty)" in result, f"got: {result}")


def test_sexpr_node_operations():
    section("SExprNode operations edge cases")

    # find_child
    root = SExprNode("root")
    child = SExprNode("child", ["val"])
    root.add_child(child)
    check_eq("find_child", root.find_child("child"), child)
    check_eq("find_child missing", root.find_child("missing"), None)

    # find_recursive
    grandchild = SExprNode("target", ["deep"])
    child.add_child(grandchild)
    found = root.find_recursive("target")
    check_eq("find_recursive", len(found), 1)
    check_eq("find_recursive value", found[0].values[0], "deep")

    # get_value out of range
    node = SExprNode("test", ["a", "b"])
    check_eq("get_value(0)", node.get_value(0), "a")
    check_eq("get_value(1)", node.get_value(1), "b")
    check_eq("get_value(2) → None", node.get_value(2), None)

    # set_value extending
    node.set_value(5, "far")
    check_eq("set_value extends", len(node.values), 6)
    check_eq("set_value gap fill", node.values[3], "")
    check_eq("set_value far", node.values[5], "far")

    # get_property / set_property
    sym = SExprNode("symbol")
    prop = SExprNode("property", ["Value", "TPS54302"])
    sym.add_child(prop)
    check_eq("get_property", sym.get_property("Value"), "TPS54302")
    check_eq("get_property missing", sym.get_property("Missing"), None)

    sym.set_property("Value", "DRV8850")
    check_eq("set_property", sym.get_property("Value"), "DRV8850")

    # set_property returns False if not found
    result = sym.set_property("Nonexistent", "x")
    check_eq("set_property missing → False", result, False)

    # clone deep copy
    original = SExprNode("root", ["v1"])
    original.add_child(SExprNode("child", ["cv1"]))
    cloned = original.clone()
    cloned.values[0] = "v2"
    cloned.children[0].values[0] = "cv2"
    check_eq("clone doesn't affect original value", original.values[0], "v1")
    check_eq("clone doesn't affect original child", original.children[0].values[0], "cv1")

    # remove_child
    parent = SExprNode("parent")
    c1 = SExprNode("c1")
    c2 = SExprNode("c2")
    parent.add_child(c1)
    parent.add_child(c2)
    parent.remove_child(c1)
    check_eq("remove_child count", len(parent.children), 1)
    check_eq("remove_child remaining", parent.children[0].tag, "c2")

    # BUG HUNT: remove_child that doesn't exist
    check_raises("remove nonexistent child", lambda: parent.remove_child(c1), ValueError)


def test_sexpr_quoting():
    section("sexpr quoting rules edge cases")

    # Numbers are bare
    check("integer bare", _is_bare("42"))
    check("negative bare", _is_bare("-3.14"))
    check("float bare", _is_bare("1.27"))

    # Keywords are bare
    check("yes bare", _is_bare("yes"))
    check("no bare", _is_bare("no"))
    check("power_in bare", _is_bare("power_in"))
    check("smd bare", _is_bare("smd"))

    # Non-keywords/numbers need quoting
    check("text not bare", not _is_bare("hello"))
    check("empty not bare", not _is_bare(""))
    check("spaced not bare", not _is_bare("hello world"))

    # _quote function
    check_eq("quote number", _quote("42"), "42")
    check_eq("quote keyword", _quote("yes"), "yes")
    check_eq("quote text", _quote("hello"), '"hello"')
    check_eq("quote with quotes", _quote('say "hi"'), '"say \\"hi\\""')

    # BUG HUNT: String that looks like a number but shouldn't be treated as one
    # E.g., a pin number "01" — should it be bare?
    check("01 is bare", _is_bare("01"))  # This IS a number pattern match

    # BUG HUNT: Scientific notation
    check("1e5 not bare", not _is_bare("1e5"))

    # BUG HUNT: Hexadecimal
    check("0xFF not bare", not _is_bare("0xFF"))


def test_regenerate_uuids():
    section("regenerate_uuids edge cases")

    # UUIDs should all change
    node = SExprNode("root")
    uuid1 = SExprNode("uuid", ["original-uuid-1"])
    uuid2 = SExprNode("uuid", ["original-uuid-2"])
    child = SExprNode("child")
    child.add_child(uuid2)
    node.add_child(uuid1)
    node.add_child(child)

    regenerate_uuids(node)

    check("uuid1 changed", uuid1.values[0] != "original-uuid-1")
    check("uuid2 changed", uuid2.values[0] != "original-uuid-2")
    check("uuids are different", uuid1.values[0] != uuid2.values[0])

    # No UUIDs — should not crash
    empty = SExprNode("root")
    regenerate_uuids(empty)
    check("no UUIDs doesn't crash", True)


# ── Symbol Modifier Tests ────────────────────────────────────────────────────

def test_create_empty_symbol():
    section("create_empty_symbol edge cases")

    # Basic symbol creation
    ds = DatasheetData(
        part_number="TEST123",
        description="Test component",
        pins=[
            PinInfo("1", "VCC", "power_in"),
            PinInfo("2", "GND", "power_in"),
            PinInfo("3", "IN", "input"),
            PinInfo("4", "OUT", "output"),
        ]
    )
    sym = create_empty_symbol(ds, "Package:SOT-23-4")
    check_eq("symbol name", sym.get_value(0), "TEST123")
    check("has properties", sym.get_property("Value") == "TEST123")
    check("has footprint", sym.get_property("Footprint") == "Package:SOT-23-4")

    # Count sub-symbols (graphics + pins)
    sub_syms = sym.find_all("symbol")
    check_eq("sub-symbol count", len(sub_syms), 2)

    # Verify all pins exist
    all_pins = sym.find_recursive("pin")
    check_eq("all pins created", len(all_pins), 4)

    # GND should be on bottom
    gnd_pin = None
    for p in all_pins:
        name_node = p.find_child("name")
        if name_node and name_node.get_value(0) == "GND":
            gnd_pin = p
            break
    check("GND pin found", gnd_pin is not None)
    if gnd_pin:
        at_node = gnd_pin.find_child("at")
        angle = at_node.get_value(2) if at_node else None
        check_eq("GND pin angle (bottom)", angle, "90")

    # Empty pins list
    ds_empty = DatasheetData(part_number="EMPTY", pins=[])
    sym_empty = create_empty_symbol(ds_empty)
    check("empty pins doesn't crash", sym_empty is not None)
    check_eq("empty pins symbol name", sym_empty.get_value(0), "EMPTY")

    # All same type (no left/right split) — should still create valid symbol
    ds_all_input = DatasheetData(
        part_number="ALLIN",
        pins=[PinInfo(str(i), f"IN{i}", "input") for i in range(1, 9)]
    )
    sym_all_in = create_empty_symbol(ds_all_input)
    all_pins = sym_all_in.find_recursive("pin")
    check_eq("all-input pins created", len(all_pins), 8)

    # BUG HUNT: Single pin
    ds_one = DatasheetData(
        part_number="ONE",
        pins=[PinInfo("1", "VCC", "power_in")]
    )
    sym_one = create_empty_symbol(ds_one)
    check("single pin doesn't crash", sym_one is not None)

    # BUG HUNT: Very many pins
    ds_many = DatasheetData(
        part_number="MANY",
        pins=[PinInfo(str(i), f"P{i}", "passive") for i in range(1, 101)]
    )
    sym_many = create_empty_symbol(ds_many)
    all_pins = sym_many.find_recursive("pin")
    check_eq("100 pins created", len(all_pins), 100)

    # BUG HUNT: Pin with special characters in name
    ds_special = DatasheetData(
        part_number="SPECIAL",
        pins=[PinInfo("1", "IN/OUT", "bidirectional")]
    )
    sym_special = create_empty_symbol(ds_special)
    all_pins = sym_special.find_recursive("pin")
    name_node = all_pins[0].find_child("name")
    check_eq("special char pin name preserved", name_node.get_value(0), "IN/OUT")

    # BUG HUNT: EP/GND pin — should go to bottom
    ds_ep = DatasheetData(
        part_number="EPTEST",
        pins=[
            PinInfo("1", "VCC", "power_in"),
            PinInfo("EP", "EP", "power_in"),
        ]
    )
    sym_ep = create_empty_symbol(ds_ep)
    all_pins = sym_ep.find_recursive("pin")
    ep_pin = None
    for p in all_pins:
        name_node = p.find_child("name")
        if name_node and name_node.get_value(0) == "EP":
            ep_pin = p
            break
    check("EP on bottom", ep_pin is not None)
    if ep_pin:
        at_node = ep_pin.find_child("at")
        angle = at_node.get_value(2) if at_node else None
        check_eq("EP angle (bottom)", angle, "90")


def test_fmt():
    section("_fmt edge cases")

    check_eq("integer", _fmt(5.0), "5")
    check_eq("negative integer", _fmt(-3.0), "-3")
    check_eq("float", _fmt(1.27), "1.27")
    check_eq("negative float", _fmt(-2.54), "-2.54")
    check_eq("zero", _fmt(0), "0")
    check_eq("tiny float", _fmt(0.0001), "0.0001")

    # BUG HUNT: floating point noise
    check_eq("float noise", _fmt(2.54 + 1e-10), "2.54")

    # BUG HUNT: very large number
    check_eq("large number", _fmt(1000.0), "1000")


def test_rename_symbol():
    section("_rename_symbol edge cases")

    sym = SExprNode("symbol", ["OLD_NAME"])
    sub1 = SExprNode("symbol", ["OLD_NAME_0_1"])
    sub2 = SExprNode("symbol", ["OLD_NAME_1_1"])
    sym.add_child(sub1)
    sym.add_child(sub2)

    _rename_symbol(sym, "OLD_NAME", "NEW_NAME")

    check_eq("main renamed", sym.get_value(0), "NEW_NAME")
    check_eq("sub1 renamed", sub1.get_value(0), "NEW_NAME_0_1")
    check_eq("sub2 renamed", sub2.get_value(0), "NEW_NAME_1_1")

    # BUG HUNT: Sub-symbol name that doesn't start with old name
    sym2 = SExprNode("symbol", ["MYPART"])
    unrelated = SExprNode("symbol", ["OTHERPART_0_1"])
    sym2.add_child(unrelated)
    _rename_symbol(sym2, "MYPART", "NEWPART")
    check_eq("unrelated sub not renamed", unrelated.get_value(0), "OTHERPART_0_1")


# ── Library Manager Tests ────────────────────────────────────────────────────

def test_library_manager():
    section("library_manager edge cases")

    tmpdir = tempfile.mkdtemp(prefix="schemagic_test_")

    try:
        # Create a symbol
        sym = SExprNode("symbol", ["TEST_SYM"])
        sym.add_child(SExprNode("in_bom", ["yes"]))

        # Save to new library
        lib_path = os.path.join(tmpdir, "schemagic.kicad_sym")
        _save_symbol_to_lib(lib_path, sym)
        check("library file created", os.path.isfile(lib_path))

        # Verify content
        with open(lib_path) as f:
            content = f.read()
        check("version in library", "20231120" in content)
        check("generator in library", "schemagic" in content)
        check("symbol in library", "TEST_SYM" in content)

        # BUG HUNT: version should NOT be quoted
        check("version not quoted", '"20231120"' not in content,
              f"version was quoted in: {content[:200]}")

        # Save another symbol (append)
        sym2 = SExprNode("symbol", ["TEST_SYM2"])
        _save_symbol_to_lib(lib_path, sym2)
        with open(lib_path) as f:
            content = f.read()
        check("both symbols present",
              "TEST_SYM" in content and "TEST_SYM2" in content)

        # Replace existing symbol
        sym3 = SExprNode("symbol", ["TEST_SYM"])
        sym3.add_child(SExprNode("in_bom", ["no"]))  # different content
        _save_symbol_to_lib(lib_path, sym3)
        nodes = parse(open(lib_path).read())
        root = nodes[0]
        test_syms = [s for s in root.find_all("symbol") if s.get_value(0) == "TEST_SYM"]
        check_eq("replaced symbol count", len(test_syms), 1)
        check_eq("replaced symbol has new content",
                  test_syms[0].find_child("in_bom").get_value(0), "no")

        # Lib table creation
        _ensure_lib_table(
            os.path.join(tmpdir, "sym-lib-table"),
            "sym_lib_table",
            "schemagic",
            "${KIPRJMOD}/schemagic.kicad_sym",
            "Test"
        )
        check("sym-lib-table created",
              os.path.isfile(os.path.join(tmpdir, "sym-lib-table")))

        # Idempotent — second call shouldn't duplicate
        _ensure_lib_table(
            os.path.join(tmpdir, "sym-lib-table"),
            "sym_lib_table",
            "schemagic",
            "${KIPRJMOD}/schemagic.kicad_sym",
            "Test"
        )
        with open(os.path.join(tmpdir, "sym-lib-table")) as f:
            content = f.read()
        check("lib table not duplicated", content.count("schemagic") == 2,
              f"found {content.count('schemagic')} occurrences (expected 2: name + descr)")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Symbol Matcher Tests ─────────────────────────────────────────────────────

def test_build_pin_mapping():
    section("_build_pin_mapping edge cases")

    ds_pins = [
        PinInfo("1", "VCC", "power_in"),
        PinInfo("2", "GND", "power_in"),
        PinInfo("3", "IN", "input"),
    ]
    sym_pins = [
        {"name": "VCC", "number": "1"},
        {"name": "GND", "number": "2"},
        {"name": "INPUT", "number": "3"},
    ]

    mapping = _build_pin_mapping(ds_pins, sym_pins)
    check_eq("VCC maps by name", mapping["1"], "1")
    check_eq("GND maps by name", mapping["2"], "2")
    # "IN" != "INPUT" so falls back to number
    check_eq("IN maps by number", mapping["3"], "3")

    # Empty symbol pins
    mapping = _build_pin_mapping(ds_pins, [])
    check_eq("empty sym pins → all default", mapping["1"], "1")

    # Empty datasheet pins
    mapping = _build_pin_mapping([], sym_pins)
    check_eq("empty ds pins → empty mapping", mapping, {})

    # BUG HUNT: Name match is case-insensitive
    ds_pins2 = [PinInfo("1", "vcc", "power_in")]
    sym_pins2 = [{"name": "VCC", "number": "1"}]
    mapping = _build_pin_mapping(ds_pins2, sym_pins2)
    check_eq("case insensitive name match", mapping["1"], "1")

    # BUG HUNT: Pin with EP number
    ds_pins3 = [PinInfo("EP", "GND", "power_in")]
    sym_pins3 = [{"name": "GND", "number": "EP"}]
    mapping = _build_pin_mapping(ds_pins3, sym_pins3)
    check_eq("EP pin mapping", mapping["EP"], "EP")


def test_pin_name_overlap():
    section("_pin_name_overlap edge cases")

    ds_pins = [
        PinInfo("1", "VCC"),
        PinInfo("2", "GND"),
        PinInfo("3", "IN"),
        PinInfo("4", "OUT"),
    ]
    sym_pins = [
        {"name": "VCC", "number": "1"},
        {"name": "GND", "number": "2"},
        {"name": "INPUT", "number": "3"},
        {"name": "OUTPUT", "number": "4"},
    ]

    overlap = _pin_name_overlap(ds_pins, sym_pins)
    check_eq("50% overlap", overlap, 0.5)

    # Perfect match
    sym_perfect = [
        {"name": "VCC", "number": "1"},
        {"name": "GND", "number": "2"},
        {"name": "IN", "number": "3"},
        {"name": "OUT", "number": "4"},
    ]
    overlap = _pin_name_overlap(ds_pins, sym_perfect)
    check_eq("100% overlap", overlap, 1.0)

    # No match
    sym_none = [{"name": "X", "number": "1"}]
    overlap = _pin_name_overlap(ds_pins, sym_none)
    check_eq("0% overlap", overlap, 0.0)

    # Empty inputs
    check_eq("empty ds → 0", _pin_name_overlap([], sym_pins), 0.0)
    check_eq("empty sym → 0", _pin_name_overlap(ds_pins, []), 0.0)
    check_eq("both empty → 0", _pin_name_overlap([], []), 0.0)


# ── Library Manager: version quoting regression ──────────────────────────────

def test_version_quoting_regression():
    section("version/generator_version quoting regression")

    tmpdir = tempfile.mkdtemp(prefix="schemagic_ver_test_")

    try:
        sym = SExprNode("symbol", ["VERTEST"])
        lib_path = os.path.join(tmpdir, "test.kicad_sym")
        _save_symbol_to_lib(lib_path, sym)

        with open(lib_path) as f:
            content = f.read()

        # Critical: KiCad REQUIRES unquoted version numbers
        check("version unquoted in file",
              '(version 20231120)' in content or '(version\t20231120)' in content
              or '(version  20231120)' in content,
              f"looking for unquoted version in: {content[:300]}")

        # generator_version should also be unquoted if numeric
        if "generator_version" in content:
            check("generator_version not double-quoted",
                  '(generator_version "1.0")' not in content,
                  f"found quoted generator_version")

        # But generator itself SHOULD be quoted (it's in _ALWAYS_QUOTE_VALUES)
        check("generator quoted",
              '"schemagic"' in content,
              f"generator should be quoted, content: {content[:300]}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Serialization round-trip with real KiCad content ─────────────────────────

def test_kicad_roundtrip():
    section("KiCad-style S-expr round-trip")

    kicad_content = """(kicad_symbol_lib (version 20231120) (generator "schemagic") (generator_version 1.0)
\t(symbol "TPS54302"
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(property "Reference" "U"
\t\t\t(at -7.62 8.89 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Value" "TPS54302"
\t\t\t(at 0 8.89 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(symbol "TPS54302_0_1"
\t\t\t(rectangle
\t\t\t\t(start -7.62 7.62)
\t\t\t\t(end 7.62 -7.62)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t)
\t\t(symbol "TPS54302_1_1"
\t\t\t(pin power_in line
\t\t\t\t(at -10.16 5.08 0)
\t\t\t\t(length 2.54)
\t\t\t\t(name "VIN" (effects (font (size 1.27 1.27))))
\t\t\t\t(number "1" (effects (font (size 1.27 1.27))))
\t\t\t)
\t\t\t(pin power_in line
\t\t\t\t(at 0 -10.16 90)
\t\t\t\t(length 2.54)
\t\t\t\t(name "GND" (effects (font (size 1.27 1.27))))
\t\t\t\t(number "2" (effects (font (size 1.27 1.27))))
\t\t\t)
\t\t)
\t)
)
"""
    # Parse
    nodes = parse(kicad_content)
    check_eq("root tag", nodes[0].tag, "kicad_symbol_lib")

    # Check version is stored correctly
    ver = nodes[0].find_child("version")
    check("version node exists", ver is not None)
    if ver:
        check_eq("version value", ver.get_value(0), "20231120")

    # Check generator
    gen = nodes[0].find_child("generator")
    check("generator node exists", gen is not None)
    if gen:
        check_eq("generator value", gen.get_value(0), "schemagic")

    # Find the symbol
    sym = nodes[0].find_child("symbol")
    check("symbol found", sym is not None)
    if sym:
        check_eq("symbol name", sym.get_value(0), "TPS54302")

        # Check properties
        check_eq("Reference", sym.get_property("Reference"), "U")
        check_eq("Value", sym.get_property("Value"), "TPS54302")

        # Find pins
        pins = sym.find_recursive("pin")
        check_eq("pin count", len(pins), 2)

        # Pin details
        pin1 = pins[0]
        check_eq("pin1 type", pin1.get_value(0), "power_in")
        check_eq("pin1 style", pin1.get_value(1), "line")
        num_node = pin1.find_child("number")
        check("pin1 number", num_node is not None and num_node.get_value(0) == "1")

    # Serialize back
    result = serialize(nodes)

    # Critical checks on serialized output
    check("version not quoted in output",
          '(version "20231120")' not in result,
          "version was incorrectly quoted")

    check("generator quoted in output",
          '"schemagic"' in result)

    # Re-parse should produce same structure
    nodes2 = parse(result)
    check_eq("re-parsed root tag", nodes2[0].tag, "kicad_symbol_lib")
    sym2 = nodes2[0].find_child("symbol")
    check("re-parsed symbol exists", sym2 is not None)
    if sym2:
        check_eq("re-parsed symbol name", sym2.get_value(0), "TPS54302")
        check_eq("re-parsed pin count", len(sym2.find_recursive("pin")), 2)


# ── Cross-module integration: symbol creation + serialization ────────────────

def test_create_and_serialize_symbol():
    section("create_empty_symbol → serialize integration")

    ds = DatasheetData(
        part_number="DRV8850",
        description="Half-Bridge Motor Driver",
        datasheet_url="https://example.com/drv8850.pdf",
        pins=[
            PinInfo("1", "VM", "power_in", "Motor supply"),
            PinInfo("2", "OUT1", "output", "Half-bridge output 1"),
            PinInfo("3", "OUT2", "output", "Half-bridge output 2"),
            PinInfo("4", "GND", "power_in", "Ground"),
            PinInfo("5", "IN1", "input", "Input 1"),
            PinInfo("6", "IN2", "input", "Input 2"),
            PinInfo("7", "NSLEEP", "input", "Sleep control"),
            PinInfo("8", "NFAULT", "open_collector", "Fault output"),
            PinInfo("9", "IPROPI", "output", "Current sense output"),
            PinInfo("10", "VREF", "passive", "Reference voltage"),
            PinInfo("11", "VCC", "power_in", "Logic supply"),
            PinInfo("12", "EN", "input", "Enable"),
            PinInfo("EP", "GND", "power_in", "Exposed thermal pad"),
        ]
    )

    sym = create_empty_symbol(ds, "Package_DFN_QFN:WQFN-16")

    # Serialize
    lib_root = SExprNode("kicad_symbol_lib")
    lib_root.add_child(SExprNode("version", ["20231120"]))
    lib_root.add_child(SExprNode("generator", ["schemagic"]))
    lib_root.add_child(sym)

    output = serialize([lib_root])

    # Verify it's valid
    check("output not empty", len(output) > 0)

    # BUG HUNT: No uuid nodes in library symbols
    check("no uuid in library symbol",
          "uuid" not in output.lower() or output.lower().count("uuid") == 0,
          "uuid found in library symbol — will cause KiCad parse error!")

    # Re-parse the output
    nodes = parse(output)
    check_eq("re-parsed root tag", nodes[0].tag, "kicad_symbol_lib")

    sym2 = nodes[0].find_child("symbol")
    check("re-parsed symbol exists", sym2 is not None)
    if sym2:
        check_eq("re-parsed name", sym2.get_value(0), "DRV8850")
        pins = sym2.find_recursive("pin")
        check_eq("re-parsed pin count", len(pins), 13)

    # Save to temp file and verify KiCad can theoretically read it
    tmpdir = tempfile.mkdtemp(prefix="schemagic_int_test_")
    try:
        lib_path = os.path.join(tmpdir, "test.kicad_sym")
        with open(lib_path, "w") as f:
            f.write(output)

        # Read it back
        with open(lib_path) as f:
            content = f.read()

        # Critical: version not quoted
        check("version unquoted in file",
              '(version "20231120")' not in content)

        # Critical: no uuid nodes
        check("no uuid in file", "uuid" not in content.lower(),
              "uuid found — will break KiCad!")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── PACKAGE_MAP consistency checks ───────────────────────────────────────────

def test_package_map_consistency():
    section("PACKAGE_MAP consistency")

    # Every TI code in _TI_PKG_CODES should have a PACKAGE_MAP entry
    from engine.datasheet.package_identifier import _TI_PKG_CODES
    for code, (pkg_name, pin_count) in _TI_PKG_CODES.items():
        check(f"TI code {code} in PACKAGE_MAP",
              code in PACKAGE_MAP or pkg_name in PACKAGE_MAP,
              f"code={code}, pkg={pkg_name}")

    # All PACKAGE_MAP values should have ":" separator
    for key, value in PACKAGE_MAP.items():
        check(f"PACKAGE_MAP[{key}] has ':'", ":" in value,
              f"value={value}")


# ── Edge case: _extract_pins_from_single_table ───────────────────────────────

def test_extract_single_table_edge_cases():
    section("_extract_pins_from_single_table edge cases")

    # Table with all empty rows
    table = [
        ["Name", "Pin No.", "I/O", "Description"],
        ["", "", "", ""],
        ["", "", "", ""],
    ]
    pins, _, _ = _extract_pins_from_single_table(
        table, data_start=1, pin_col=1, name_col=0, type_col=2, desc_col=3
    )
    check_eq("all empty rows → 0 pins", len(pins), 0)

    # Table with None everywhere
    table = [
        ["Name", "Pin No.", "I/O", "Description"],
        [None, None, None, None],
    ]
    pins, _, _ = _extract_pins_from_single_table(
        table, data_start=1, pin_col=1, name_col=0, type_col=2, desc_col=3
    )
    check_eq("all None data → 0 pins", len(pins), 0)

    # Short row (fewer columns than expected)
    table = [
        ["Name", "Pin No.", "I/O", "Description"],
        ["VCC", "1"],  # only 2 columns
    ]
    pins, _, _ = _extract_pins_from_single_table(
        table, data_start=1, pin_col=1, name_col=0, type_col=2, desc_col=3
    )
    check_eq("short row parsed", len(pins), 1)
    check_eq("short row pin type inferred", pins[0].pin_type, "power_in")

    # Row where pin_col > name_col → should still work
    table = [
        ["Pin No.", "Name", "I/O"],
        ["1", "VCC", "P"],
    ]
    pins, _, _ = _extract_pins_from_single_table(
        table, data_start=1, pin_col=0, name_col=1, type_col=2, desc_col=None
    )
    check_eq("reversed col order", len(pins), 1)
    check_eq("reversed col pin name", pins[0].name, "VCC")

    # Multiple pin numbers in one cell
    table = [
        ["Name", "Pin No.", "I/O", "Description"],
        ["GND", "2,3,4", "P", "Ground pins"],
    ]
    pins, _, _ = _extract_pins_from_single_table(
        table, data_start=1, pin_col=1, name_col=0, type_col=2, desc_col=3
    )
    check_eq("multi-pin cell count", len(pins), 3)
    check("multi-pin all named GND", all(p.name == "GND" for p in pins))
    check("multi-pin numbers", [p.number for p in pins] == ["2", "3", "4"])

    # BUG HUNT: type_col is None
    table = [
        ["Name", "Pin No."],
        ["VCC", "1"],
    ]
    pins, _, _ = _extract_pins_from_single_table(
        table, data_start=1, pin_col=1, name_col=0, type_col=None, desc_col=None
    )
    check_eq("no type col → inferred type", pins[0].pin_type, "power_in")


# ── Edge case: Adversarial inputs ────────────────────────────────────────────

def test_adversarial_inputs():
    section("adversarial / malformed inputs")

    # Very long pin name
    long_name = "A" * 1000
    pin_type = infer_pin_type(long_name)
    check_eq("very long name → passive", pin_type, "passive")

    # Unicode in pin names
    pin_type = infer_pin_type("VCC\u200b")  # zero-width space
    check("unicode zero-width space",
          pin_type in ("power_in", "passive"),
          f"got {pin_type}")

    # Newlines everywhere in table
    tables = [(1, [
        ["Na\nme", "Pin\nNo.", "I/\nO"],
        ["VC\nC", "1\n", "P"],
    ])]
    # This will likely fail because headers won't match
    pins, conf = extract_pins_from_tables(tables)
    check("newlines in headers handled",
          isinstance(pins, list),
          f"got {type(pins)}")

    # Completely empty table
    tables = [(1, [[], []])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("empty rows → 0 pins", len(pins), 0)

    # Table with single cell
    tables = [(1, [["Hello"]])]
    pins, conf = extract_pins_from_tables(tables)
    check_eq("single cell → 0 pins", len(pins), 0)

    # Package text with only small numbers
    pkg = identify_package_from_text("TSSOP 4 pin")
    # "\d{2,}" requires 2+ digits, so "4" shouldn't match
    check("single digit not matched",
          pkg is None or pkg.pin_count >= 10,
          f"got {pkg}")

    # Very long text for package identification
    long_text = "SOIC " * 10000
    try:
        packages = identify_all_packages(long_text)
        check("long text doesn't crash", True)
    except Exception as e:
        check("long text doesn't crash", False, str(e))


# ── Run all tests ────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  schemagic Edge Case Test Suite")
    print("=" * 60)

    tests = [
        test_parse_pin_numbers,
        test_merge_header_rows,
        test_is_pin_table,
        test_find_columns,
        test_is_section_header,
        test_parse_io_type,
        test_infer_pin_type,
        test_detect_headers,
        test_extract_pins_from_tables,
        test_extract_pins_from_text,
        test_package_from_part_number,
        test_package_from_text,
        test_identify_package,
        test_strip_ti_suffix,
        test_sexpr_parse,
        test_sexpr_serialize,
        test_sexpr_node_operations,
        test_sexpr_quoting,
        test_regenerate_uuids,
        test_create_empty_symbol,
        test_fmt,
        test_rename_symbol,
        test_library_manager,
        test_build_pin_mapping,
        test_pin_name_overlap,
        test_version_quoting_regression,
        test_kicad_roundtrip,
        test_create_and_serialize_symbol,
        test_package_map_consistency,
        test_extract_single_table_edge_cases,
        test_adversarial_inputs,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            global _error_count
            _error_count += 1
            print(f"\n  ERROR in {test_fn.__name__}: {e}")
            traceback.print_exc()

    # Summary
    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    total = _pass_count + _fail_count
    print(f"  Passed: {_pass_count}/{total}")
    print(f"  Failed: {_fail_count}/{total}")
    if _error_count:
        print(f"  Errors: {_error_count} (test functions crashed)")

    if _failures:
        print(f"\n  Failed tests:")
        for section, name, detail in _failures:
            print(f"    [{section}] {name}")
            if detail:
                print(f"      {detail}")

    print()
    return 0 if _fail_count == 0 and _error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
