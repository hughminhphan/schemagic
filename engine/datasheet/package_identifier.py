"""
Package identifier: extract package type from datasheet text and map to
standard names usable for KiCad footprint lookup.
"""

import re
from ..core.models import PackageInfo
from ..core.config import PACKAGE_MAP


# TI package code extraction: look for suffixes in orderable part numbers
_TI_PKG_CODES = {
    "DDC": ("SOT-23-6", 6),
    "DCK": ("SOT-353_SC-70-5", 5),
    "DBV": ("SOT-23-5", 5),
    "DGK": ("TSSOP-8", 8),
    "DGS": ("VSSOP-10", 10),
    "DGN": ("HVSSOP-8", 8),
    "DRV": ("WSON-6", 6),
    "DRC": ("SON-10", 10),
    "DSG": ("SOT-23-5", 5),
    "PWP": ("HTSSOP-16", 16),
    "RGE": ("QFN-24", 24),
    "RGT": ("QFN-16", 16),
    "RTE": ("WQFN-16", 16),
    "RSA": ("QFN-40", 40),
    "QDR": ("WSON-8", 8),
    "DLH": ("WSON-10", 10),
    "DSC": ("SOIC-8", 8),
    "DWK": ("SOIC-14", 14),
    "YZF": ("BGA-9", 9),
    "YFF": ("BGA-4", 4),
    "RGY": ("VQFN-24", 24),
    "RHA": ("VQFN-40", 40),
    "RHB": ("VQFN-32", 32),
    "DDW": ("HTSSOP-44", 44),
    "DAD": ("HTSSOP-32", 32),
    "DGQ": ("HVSSOP-24", 24),
    "DRB": ("SON-8", 8),
    "DRL": ("SOT-5X3", 6),
    "DDA": ("SOIC-8", 8),
    "ID": ("SOIC-8", 8),
    "IDGS": ("VSSOP-10", 10),
    "MFX": ("SOT-23-5", 5),
    "PDRL": ("SOT-563", 6),
    "D": ("SOIC-8", 8),
}

# Known pin counts for SOT-NNN and other fixed-name packages that don't
# capture a pin count from their regex.  Used to fill in pin_count when the
# pattern has no capture group.
_PKG_PIN_COUNTS = {
    "SOT-23-3": 3, "SOT-23-5": 5, "SOT-23-6": 6, "SOT-23-8": 8,
    "SOT-89-3": 3, "SOT-89-5": 5,
    "SOT-143": 4,
    "SOT-223": 3,
    "SOT-323": 3, "SOT-343": 4, "SOT-353": 5, "SOT-363": 6,
    "SOT-416": 3, "SOT-523": 3, "SOT-543": 4, "SOT-553": 5, "SOT-563": 6,
    "SOT-665": 5, "SOT-666": 6, "SOT-723": 3, "SOT-883": 3, "SOT-886": 6,
    "SOT-963": 6,
    "TSOP-5": 5, "TSOP-6": 6,
    "TO-252": 3, "TO-263": 3,
    "TO-220-3": 3, "TO-247-3": 3, "TO-92": 3,
    "TO-3": 3, "IPAK": 3, "I2PAK": 3,
}

# Standard package patterns in text
# Order matters: more-specific patterns (HTSSOP, WQFN, VQFN) must come before
# less-specific ones (TSSOP, SSOP, QFN) to avoid substring matches.
_PKG_PATTERNS = [
    # --- SOT-NNN aliases (must come before SOT-23 patterns) ---
    # SOT-26(A) = SOT-23-6 (Mitsumi, ROHM, Toshiba name)
    (re.compile(r"SOT-?26[A-Z]?\b", re.I), "SOT-23-6"),
    # SOT-25 = SOT-23-5
    (re.compile(r"SOT-?25\b", re.I), "SOT-23-5"),
    # SOT-457 = SOT-23-6 (JEDEC name)
    (re.compile(r"SOT-?457\b", re.I), "SOT-23-6"),
    # SOT-89 variants (3-pin default, sub-count optional)
    (re.compile(r"SOT-?89[\s\-]+(\d)", re.I), "SOT-89-{0}"),
    (re.compile(r"SOT-?89\b(?![\s\-]*\d)", re.I), "SOT-89-3"),
    # SOT-143
    (re.compile(r"SOT-?143\b", re.I), "SOT-143"),
    # SOT-3xx (SC-70 family)
    (re.compile(r"SOT-?323\b", re.I), "SOT-323"),
    (re.compile(r"SOT-?343\b", re.I), "SOT-343"),
    (re.compile(r"SOT-?353\b", re.I), "SOT-353"),
    (re.compile(r"SOT-?363\b", re.I), "SOT-363"),
    # SOT-4xx/5xx/6xx/7xx/8xx/9xx (various micro packages)
    (re.compile(r"SOT-?416\b", re.I), "SOT-416"),
    (re.compile(r"SOT-?523\b", re.I), "SOT-523"),
    (re.compile(r"SOT-?543\b", re.I), "SOT-543"),
    (re.compile(r"SOT-?553\b", re.I), "SOT-553"),
    (re.compile(r"SOT-?563\b", re.I), "SOT-563"),
    (re.compile(r"SOT-?583[\s\-]+(\d)", re.I), "SOT-583-{0}"),
    (re.compile(r"SOT-?665\b", re.I), "SOT-665"),
    (re.compile(r"SOT-?666\b", re.I), "SOT-666"),
    (re.compile(r"SOT-?723\b", re.I), "SOT-723"),
    (re.compile(r"SOT-?883\b", re.I), "SOT-883"),
    (re.compile(r"SOT-?886\b", re.I), "SOT-886"),
    (re.compile(r"SOT-?963\b", re.I), "SOT-963"),
    # TSOP-5/6 (small SOT-23 aliases, NOT memory TSOP-I packages)
    (re.compile(r"TSOP-?5\b(?!\s*[\-_]?I)", re.I), "TSOP-5"),
    (re.compile(r"TSOP-?6\b(?!\s*[\-_]?I)", re.I), "TSOP-6"),
    # --- SOT-23 variants ---
    # SOT-23 variants: handle "SOT-23-6", "SOT-23 (6)", "SOT23-5" formats
    # \b(?!\.) prevents "SOT-23 - 1.1 mm" matching as SOT-23-1
    (re.compile(r"SOT-?23[\s\-\(,]*(\d)\b(?!\.)", re.I), "SOT-23-{0}"),
    # Reverse: "5-pin SOT-23", "5-Pin SOT-23"
    (re.compile(r"(\d)-?[Pp]in\s+SOT-?23\b", re.I), "SOT-23-{0}"),
    (re.compile(r"SOT-?23(?![\d\s\-\(,]*\d)", re.I), "SOT-23-3"),
    # SOIC: "SOIC 14", "SOIC-8", "SOIC (16)", also reverse "14-pin SOIC"
    (re.compile(r"SOIC[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "SOIC-{0}"),
    (re.compile(r"(\d+)-?(?:[Pp](?:in|ad)|[Ll]ead)\s+SOIC", re.I), "SOIC-{0}"),
    (re.compile(r"MSOP[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "MSOP-{0}"),
    # VSSOP (Very thin Shrink SOP) — must come before SSOP
    # Negative lookbehind prevents "HVSSOP" from matching as "VSSOP"
    (re.compile(r"(?<!H)VSSOP[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "VSSOP-{0}"),
    # HTSSOP/HVSSOP before TSSOP/SSOP (HTSSOP contains both as substrings)
    # Use \d{2,} for xSSOP/xQFN to avoid false matches on height specs (e.g. "1.2 mm")
    # Separators include comma and pipe for TI formats like "HTSSOP, 20" and "HTSSOP | 20"
    (re.compile(r"HTSSOP[\s\-\(,|]+(\d{2,})\)?", re.I), "HTSSOP-{0}"),
    (re.compile(r"(\d{2,})-?[Pp]in\s+HTSSOP", re.I), "HTSSOP-{0}"),
    (re.compile(r"HVSSOP[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "HVSSOP-{0}"),
    (re.compile(r"(\d+)-?[Pp]in\s+HVSSOP", re.I), "HVSSOP-{0}"),
    (re.compile(r"(?<!H)TSSOP[\s\-\(,|]+(\d{2,})\)?", re.I), "TSSOP-{0}"),
    (re.compile(r"(\d{2,})-?(?:[Pp](?:in|ad)|[Ll]ead)\s+TSSOP", re.I), "TSSOP-{0}"),
    (re.compile(r"(?<![HTVA-Z])SSOP[\s\-\(,|]+(\d{2,})\)?", re.I), "SSOP-{0}"),
    # WQFN/VQFN before QFN; also reverse "32-pad QFN" format
    (re.compile(r"WQFN[\s\-\(,|]+(\d{2,})\)?", re.I), "WQFN-{0}"),
    (re.compile(r"VQFN[\s\-\(,|]?(\d{2,})\)?", re.I), "VQFN-{0}"),
    (re.compile(r"(?<![WV])QFN[\s\-\(,|]+(\d{2,})\)?", re.I), "QFN-{0}"),
    (re.compile(r"(\d{2,})-?(?:[Pp](?:in|ad)|[Ll]ead)\s+(?:W|V)?QFN", re.I), "QFN-{0}"),
    # SON/DFN: include comma separator for TI "WSON, 10" format
    (re.compile(r"WSON[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "WSON-{0}"),
    (re.compile(r"DFN[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "DFN-{0}"),
    # QFP variants
    (re.compile(r"LQFP[\s\-\(,|]+(\d{2,})\)?", re.I), "LQFP-{0}"),
    (re.compile(r"(\d{2,})-?(?:[Pp](?:in|ad)|[Ll]ead)\s+LQFP", re.I), "LQFP-{0}"),
    (re.compile(r"TQFP[\s\-\(,|]+(\d{2,})\)?", re.I), "TQFP-{0}"),
    (re.compile(r"(\d{2,})-?(?:[Pp](?:in|ad)|[Ll]ead)\s+TQFP", re.I), "TQFP-{0}"),
    # BGA and wafer-level variants
    (re.compile(r"(?<!DS)BGA[\s\-\(,|]+(\d{2,})\)?", re.I), "BGA-{0}"),
    (re.compile(r"DSBGA[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "DSBGA-{0}"),
    (re.compile(r"WCSP[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "WCSP-{0}"),
    # Through-hole
    (re.compile(r"PDIP[\s\-\(,|]+(\d{2,})\)?", re.I), "PDIP-{0}"),
    (re.compile(r"(\d{2,})-?[Pp]in\s+PDIP", re.I), "PDIP-{0}"),
    # Small outline
    (re.compile(r"SC-?70-?(\d)", re.I), "SC-70-{0}"),
    (re.compile(r"SOT-?223", re.I), "SOT-223"),
    (re.compile(r"SOT-?583", re.I), "SOT-583"),
    # Power packages (SMD)
    (re.compile(r"TO-?252", re.I), "TO-252"),
    (re.compile(r"TO-?263", re.I), "TO-263"),
    (re.compile(r"D-?PAK", re.I), "TO-252"),
    (re.compile(r"D2-?PAK", re.I), "TO-263"),
    # Power/discrete packages (THT)
    (re.compile(r"TO-?220[\s\-]+(\d+)", re.I), "TO-220-{0}"),
    (re.compile(r"TO-?220\b(?![\s\-]*\d)", re.I), "TO-220-3"),
    (re.compile(r"TO-?247[\s\-]+(\d+)", re.I), "TO-247-{0}"),
    (re.compile(r"TO-?247\b(?![\s\-]*\d)", re.I), "TO-247-3"),
    (re.compile(r"TO-?92\b", re.I), "TO-92"),
    (re.compile(r"TO-?3P?\b", re.I), "TO-3"),
    (re.compile(r"I-?PAK\b", re.I), "IPAK"),
    (re.compile(r"I2-?PAK\b", re.I), "I2PAK"),
    # Plain QFP (no L/T prefix, used by some STM32 datasheets)
    (re.compile(r"(?<![LT])QFP[\s\-\(,|]+(\d{2,})\)?", re.I), "QFP-{0}"),
    (re.compile(r"(\d{2,})-?(?:[Pp](?:in|ad)|[Ll]ead)\s+QFP", re.I), "QFP-{0}"),
    # WLCSP (wafer-level chip-scale package, used by MCUs and PMICs)
    (re.compile(r"WLCSP[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "WLCSP-{0}"),
    (re.compile(r"(\d+)-?(?:[Pp](?:in|ad)|[Bb]all)\s+WLCSP", re.I), "WLCSP-{0}"),
    # UFBGA / TFBGA (used by STM32, memory ICs)
    (re.compile(r"[UT]FBGA[\s\-\(,|]+(\d+)\b(?!\.)\)?", re.I), "UFBGA-{0}"),
    (re.compile(r"(\d+)-?(?:[Pp](?:in|ad)|[Bb]all)\s+[UT]FBGA", re.I), "UFBGA-{0}"),
]


def identify_package_from_part_number(part_number):
    """Try to identify the package from TI-style part number suffixes.

    Returns PackageInfo or None.
    """
    pn = part_number.upper().strip()

    for code, (pkg_name, pin_count) in _TI_PKG_CODES.items():
        # Check if the part number ends with the code (possibly + R for reel)
        if pn.endswith(code) or pn.endswith(code + "R"):
            return PackageInfo(
                name=pkg_name,
                pin_count=pin_count,
                ti_code=code,
            )

    return None


def identify_package_from_text(text, pin_count_hint=0):
    """Extract package info from datasheet text.

    Args:
        text: full text or relevant section of the datasheet
        pin_count_hint: if known, helps disambiguate

    Returns PackageInfo or None.
    """
    # Find all package mentions
    candidates = []

    for pattern, fmt in _PKG_PATTERNS:
        for m in pattern.finditer(text):
            if m.groups():
                name = fmt.format(*m.groups())
                try:
                    count = int(m.group(1))
                except (IndexError, ValueError):
                    count = 0
            else:
                name = fmt
                count = 0
            # Resolve pin count from lookup table when regex didn't capture one
            if count == 0:
                count = _PKG_PIN_COUNTS.get(name, 0)
            candidates.append(PackageInfo(name=name, pin_count=count))

    if not candidates:
        return None

    # If we have a pin count hint, prefer matching candidates
    if pin_count_hint > 0:
        matching = [c for c in candidates if c.pin_count == pin_count_hint]
        if matching:
            return matching[0]

    # Return the first (most prominent) match
    return candidates[0]


def _extract_packages_from_tables(tables, part_number):
    """Extract packages from structured pdfplumber tables.

    Looks for the "Device Information" / "Package Information" table
    (header contains "PACKAGE"), then finds rows matching the queried
    part number and parses package entries like "D (SOIC, 8)".

    This is the most reliable extraction strategy because it uses the
    actual table structure rather than regex on free text.

    Args:
        tables: list of (page_num, rows) from extract_tables_and_text
        part_number: the part number being searched (e.g. "UC3845")

    Returns list of PackageInfo, or empty list if no matching table found.
    """
    pn_upper = part_number.upper().strip()
    # Also try matching with wildcards: UC3845 should match UC384x
    # by comparing prefix without trailing digits/letters
    pn_prefix = re.sub(r'[\dA-Z]*$', '', pn_upper)  # "UC" for UC3845

    # Package cell pattern: "D (SOIC, 8)" or "DGS (VSSOP, 20)" or "DBV (SOT-23, 5)"
    pkg_cell_pattern = re.compile(
        r"([A-Z]{1,5})\s*\(\s*([A-Z][A-Z0-9\-]+)"  # code (package_name
        r"[\s,]+(\d+)\s*\)",                          # , pin_count)
        re.I,
    )

    for page_num, rows in tables:
        if not rows or len(rows) < 2:
            continue

        header = rows[0]
        if not header:
            continue

        # Check if this is a package information table
        header_text = " ".join(str(c) for c in header if c).upper()
        if "PACKAGE" not in header_text:
            continue
        if "PART" not in header_text and "DEVICE" not in header_text:
            continue

        # Find the PACKAGE column index
        pkg_col = None
        for ci, cell in enumerate(header):
            if cell and "PACKAGE" in str(cell).upper() and "SIZE" not in str(cell).upper():
                pkg_col = ci
                break
        if pkg_col is None:
            continue

        # Walk through rows, tracking which part number group we're in
        current_group_pn = ""
        matching_rows = []

        for row in rows[1:]:
            if not row or len(row) <= pkg_col:
                continue

            # Check if this row starts a new part number group
            first_cell = str(row[0]).strip() if row[0] else ""
            if first_cell:
                current_group_pn = first_cell.upper()

            # Check if the current group matches our part number
            # UC384x matches UC3845, TPS7E82 matches TPS7E82-Q1, etc.
            group_matches = False
            if current_group_pn:
                # Direct match
                if pn_upper.startswith(current_group_pn.rstrip("Xx")):
                    group_matches = True
                # Wildcard match: UC384x -> UC384
                elif "X" in current_group_pn:
                    prefix = current_group_pn.replace("X", "").replace("x", "")
                    if pn_upper.startswith(prefix):
                        group_matches = True
                # The part number matches the group exactly
                elif current_group_pn == pn_upper:
                    group_matches = True

            if group_matches:
                pkg_cell = str(row[pkg_col]).strip() if row[pkg_col] else ""
                if pkg_cell:
                    matching_rows.append(pkg_cell)

        # Parse package info from matching rows
        if matching_rows:
            seen = set()
            candidates = []
            for cell_text in matching_rows:
                m = pkg_cell_pattern.search(cell_text)
                if m:
                    code = m.group(1).upper()
                    pkg_text = m.group(2).upper().strip()
                    pin_count = int(m.group(3))

                    pkg_name = "{}-{}".format(pkg_text, pin_count)

                    # Cross-check with known TI codes for normalized names
                    if code in _TI_PKG_CODES:
                        known_name, _ = _TI_PKG_CODES[code]
                        family = known_name.rsplit("-", 1)[0] if "-" in known_name else known_name
                        pkg_name = "{}-{}".format(family, pin_count)

                    if pkg_name not in seen:
                        seen.add(pkg_name)
                        candidates.append(PackageInfo(
                            name=pkg_name, pin_count=pin_count, ti_code=code,
                        ))
            if candidates:
                return candidates

    return []


def _extract_ti_packages_from_orderable_pns(text, base_pn):
    """Extract packages by finding TI package codes in datasheet text.

    Uses two strategies:
    1. Orderable part numbers: TPS7E82DBV, TPS7E82DGNR, etc.
    2. Package code references: "DBV (SOT-23", "DGN (HVSSOP", "DRV (WSON"
       which TI datasheets commonly use in ordering/package info sections.

    Args:
        text: full datasheet text
        base_pn: base part number without package suffix (e.g. "TPS7E82")

    Returns list of PackageInfo, or empty list if no package codes found.
    """
    if not base_pn:
        return []

    seen = set()
    candidates = []

    # Sort codes longest-first to match greedily
    codes_by_len = sorted(_TI_PKG_CODES.keys(), key=len, reverse=True)
    codes_pattern = "|".join(re.escape(c) for c in codes_by_len)

    # Strategy 1: base_pn + package code (e.g. "TPS7E82DBV", "TPS7E82DGNR")
    pn_pattern = re.compile(
        re.escape(base_pn) + r"(" + codes_pattern + r")R?" + r"(?:-Q\d+)?",
        re.I,
    )
    for m in pn_pattern.finditer(text):
        code = m.group(1).upper()
        if code in _TI_PKG_CODES:
            pkg_name, pin_count = _TI_PKG_CODES[code]
            if pkg_name not in seen:
                seen.add(pkg_name)
                candidates.append(PackageInfo(
                    name=pkg_name, pin_count=pin_count, ti_code=code,
                ))

    if candidates:
        return candidates

    # Strategy 2: Parse "Device Information" table entries like "DGS (VSSOP, 20)"
    # or "DBV (SOT-23, 5)". Extract package name and pin count directly from text
    # rather than relying on static table (TI reuses codes across different pin counts).
    # Pattern: CODE (PACKAGE_NAME, PIN_COUNT) or CODE (PACKAGE_NAME PIN_COUNT)
    device_info_pattern = re.compile(
        r"\b([A-Z]{2,5})\s*\(\s*([A-Z][A-Z0-9\-]+)"  # code (package_name
        r"[\s,]+(\d+)\s*\)",                            # , pin_count)
        re.I,
    )
    for m in device_info_pattern.finditer(text):
        code = m.group(1).upper()
        pkg_text = m.group(2).upper().strip()
        pin_count = int(m.group(3))

        # Build normalized package name
        pkg_name = "{}-{}".format(pkg_text, pin_count)

        # Cross-check with known TI codes if available
        if code in _TI_PKG_CODES:
            known_name, _ = _TI_PKG_CODES[code]
            # Use the known package family but with the text's pin count
            # e.g. DGS -> VSSOP family, but pin count from text (20 not 10)
            family = known_name.rsplit("-", 1)[0] if "-" in known_name else known_name
            pkg_name = "{}-{}".format(family, pin_count)

        if pkg_name not in seen:
            seen.add(pkg_name)
            candidates.append(PackageInfo(
                name=pkg_name, pin_count=pin_count, ti_code=code,
            ))

    return candidates


def identify_all_packages(text, pin_count_hint=0, base_pn="", manufacturer="",
                          tables=None, part_number=""):
    """Return all package candidates, using the most reliable strategy available.

    Strategy priority:
    1. Structured table parsing (most reliable) - parses the "Device Information"
       table directly, filtering to the correct part number row group.
    2. TI orderable PN extraction - finds package codes in text (TI-specific).
    3. Regex pattern matching on full text (least reliable fallback).

    Deduplicates by normalized package name, keeping the first occurrence.
    """
    pn = part_number or base_pn or ""

    # Strategy 1: Parse the actual package information table
    if tables and pn:
        table_candidates = _extract_packages_from_tables(tables, pn)
        if table_candidates:
            return table_candidates

    # Strategy 2: TI-specific orderable PN extraction from text
    if base_pn and (not manufacturer or manufacturer.upper() in ("TI", "TEXAS INSTRUMENTS", "")):
        ti_candidates = _extract_ti_packages_from_orderable_pns(text, base_pn)
        if ti_candidates:
            return ti_candidates

    # Strategy 3: Regex fallback on full text
    seen = set()
    candidates = []

    for pattern, fmt in _PKG_PATTERNS:
        for m in pattern.finditer(text):
            if m.groups():
                name = fmt.format(*m.groups())
                try:
                    count = int(m.group(1))
                except (IndexError, ValueError):
                    count = 0
            else:
                name = fmt
                count = 0
            # Resolve pin count from lookup table when regex didn't capture one
            if count == 0:
                count = _PKG_PIN_COUNTS.get(name, 0)
            if name not in seen:
                seen.add(name)
                candidates.append(PackageInfo(name=name, pin_count=count))

    return candidates


def identify_package(part_number, text, pin_count_hint=0):
    """Identify the package using all available information.

    Tries part number suffix first, then text extraction.
    """
    pkg = identify_package_from_part_number(part_number)
    if pkg:
        return pkg

    pkg = identify_package_from_text(text, pin_count_hint)
    if pkg:
        return pkg

    return None
