"""
Pin assignment extractor from datasheet tables.

Identifies pin assignment tables and extracts PinInfo objects.
"""

import re
from ..core.models import PinInfo


# Column header patterns for identifying pin tables
_PIN_COL_PATTERNS = [
    re.compile(r"^pins?\s*(no\.?|number|#)?$", re.I),  # "Pin", "Pins", "Pin No."
    re.compile(r"^(terminal\s*)?no\.?$", re.I),
    re.compile(r"^terminal\s+no\.?$", re.I),
    re.compile(r"^#$"),
    # Multi-package tables: "PIN PWP", "PIN SOT-23", "PIN SO PowerPAD", etc.
    # Exclude common words (NAME, TYPE) that could be merged header artifacts
    re.compile(r"^pin\s+(?!name|type|desc)[\w\-./(),\s']+$", re.I),
    # Bare package code with optional pin count: "PWP (20)", "SOT-23", "SOIC"
    # These appear in split-header tables where row 0 PIN cell is in a
    # different column, leaving the package code column without a PIN prefix
    re.compile(r"^(PWP|RTE|DDW|DAD|RGE|RGT|RGY|RHA|RHB|DRC|DDC|DBV|DCK|DGK|DGS|DGQ|DSG|RSA|QDR"
               r"|SOT[\-\s]*\d*|SOIC|MSOP|TSSOP|SSOP|VSON|X2SON|WSON|DFN|QFN|BGA|DSBGA|SON"
               r"|TDFN|WLP|LFCSP|UCSP|WLCSP|BUMPS?)[\w\-]*(\s*\(\d+\))?$", re.I),
    # "IN NUMBER" — pdfplumber sometimes splits "PIN" → "P" + "IN"
    re.compile(r"^in\s+num(ber)?\.?$", re.I),
    # Bare "NUMBER" or "NO." column
    re.compile(r"^num(ber)?(s|\(s\))?\.?$", re.I),  # "Number", "Number(s)", "Numbers"
    # ADI/Maxim: "PIN/BUMP", "PIN/BALL" — multi-package pin column
    re.compile(r"^pin\s*/\s*(bump|ball)$", re.I),
    # pdfplumber split: "PI N" (PIN split across two cells, merged to "N NO." or similar)
    re.compile(r"^n\s+no\.?$", re.I),
]

_NAME_COL_PATTERNS = [
    re.compile(r"^(pin\s*)?name$", re.I),
    re.compile(r"^terminal(\s+name)?$", re.I),
    re.compile(r"^terminal\s+name$", re.I),
    re.compile(r"^signal(\s+name)?$", re.I),
    re.compile(r"^function$", re.I),
    # pdfplumber sometimes splits "PIN" → "P" or "PI" in adjacent cell
    re.compile(r"^pi?\s+name$", re.I),
    # ADI: "MNEMONIC" used instead of "NAME" in pin tables
    re.compile(r"^mnemonic$", re.I),
    # ADI/Maxim: "SYMBOL" column in some datasheets
    re.compile(r"^symbol$", re.I),
]

_TYPE_COL_PATTERNS = [
    re.compile(r"^i/?o(\(\d+\))?$", re.I),       # I/O, I/O(1)
    re.compile(r"^(type|direction)(\(\d+\))?$", re.I),  # TYPE, TYPE(1)
    re.compile(r"^pin\s*type$", re.I),
]

_DESC_COL_PATTERNS = [
    re.compile(r"^desc(ription)?$", re.I),
    re.compile(r"^function(al)?\s*desc", re.I),
    # ADI/Maxim: "FUNCTION" column used as description
    re.compile(r"^function$", re.I),
    # ADI: "PIN FUNCTION" in some datasheets
    re.compile(r"^pin\s+function$", re.I),
]

# Alternate function column patterns (MCU GPIO muxing, FPGA bank assignment)
_ALT_FUNC_COL_PATTERNS = [
    re.compile(r"^alt(ernate)?\s*(function|func)s?", re.I),
    re.compile(r"^additional\s+function", re.I),
    re.compile(r"^AF\d+", re.I),  # STM32: AF0, AF1, ...
    re.compile(r"^remap", re.I),
    re.compile(r"^default\s*/\s*remap", re.I),
    re.compile(r"^gpio\s+config", re.I),
]

# Pin name normalization: some datasheets use full English words as pin names
# (e.g., LM2596 uses "Output" instead of "OUT"). Map to standard abbreviations.
_PIN_NAME_NORMALIZATION = {
    "OUTPUT": "OUT",
    "GROUND": "GND",
    "FEEDBACK": "FB",
    "INPUT": "IN",
    "ENABLE": "EN",
}

# Section header keywords (rows to skip)
_SECTION_KEYWORDS = {
    "power", "ground", "control", "output", "input", "analog",
    "digital", "supply", "communication", "interface", "test",
    "misc", "other", "signal", "clock", "system", "thermal",
    "status",
}


def _match_col(header, patterns):
    """Check if a header matches any of the patterns."""
    if not header:
        return False
    # Normalize newlines to spaces (pdfplumber can embed \n in cells)
    header = header.replace("\n", " ").strip()
    return any(p.match(header) for p in patterns)


def _merge_header_rows(row0, row1):
    """Merge two header rows into one (handles split headers like DRV8850).

    Example: ["", "PIN", "I/O(1)", "DESCRIPTION"] + ["NAME", "NO.", "", ""]
    → ["NAME", "PIN NO.", "I/O(1)", "DESCRIPTION"]
    """
    merged = []
    for i in range(max(len(row0), len(row1))):
        h0 = (row0[i] if i < len(row0) else None) or ""
        h1 = (row1[i] if i < len(row1) else None) or ""
        h0 = h0.strip()
        h1 = h1.strip()
        if h0 and h1:
            merged.append(f"{h0} {h1}")
        elif h0:
            merged.append(h0)
        elif h1:
            merged.append(h1)
        else:
            merged.append("")
    return merged


def _is_pin_table(headers):
    """Check if a table row (or merged rows) looks like pin table headers."""
    has_pin = any(_match_col(h, _PIN_COL_PATTERNS) for h in headers)
    has_name = any(_match_col(h, _NAME_COL_PATTERNS) for h in headers)
    return has_pin and has_name


def _find_columns(headers):
    """Find the column indices for pin, name, type, description, and alt functions.

    Name patterns are checked first because merged headers like "PIN NAME"
    match both pin and name patterns — name should win in that case.

    Returns (pin_col, name_col, type_col, desc_col, alt_func_cols).
    For multi-package tables with multiple pin columns, returns the first.
    Use _find_all_pin_columns() to get all pin columns.
    alt_func_cols is a list of column indices for alternate function columns.
    """
    pin_col = name_col = type_col = desc_col = None
    alt_func_cols = []

    # First pass: find name, type, description, and alt function columns
    for i, h in enumerate(headers):
        if h is None:
            continue
        h = h.replace("\n", " ").strip()
        if name_col is None and _match_col(h, _NAME_COL_PATTERNS):
            name_col = i
        elif type_col is None and _match_col(h, _TYPE_COL_PATTERNS):
            type_col = i
        elif desc_col is None and _match_col(h, _DESC_COL_PATTERNS):
            desc_col = i
        elif _match_col(h, _ALT_FUNC_COL_PATTERNS):
            alt_func_cols.append(i)

    # Second pass: find pin column (skip the column already assigned as name)
    for i, h in enumerate(headers):
        if h is None or i == name_col:
            continue
        h = h.replace("\n", " ").strip()
        if pin_col is None and _match_col(h, _PIN_COL_PATTERNS):
            pin_col = i
            break

    return pin_col, name_col, type_col, desc_col, alt_func_cols


def _find_all_pin_columns(headers, name_col):
    """Find ALL columns that look like pin number columns.

    Multi-package tables (e.g., LP5907 with X2SON + SOT-23 columns) have
    multiple pin columns. Returns list of column indices.
    """
    pin_cols = []
    for i, h in enumerate(headers):
        if h is None or i == name_col:
            continue
        h = h.replace("\n", " ").strip()
        if _match_col(h, _PIN_COL_PATTERNS):
            pin_cols.append(i)
    return pin_cols


def _is_section_header(row):
    """Check if a row is a section header (e.g., "POWER AND GROUND")."""
    # Section headers typically have text in only the first cell
    non_empty = [c for c in row if c and c.strip()]
    if len(non_empty) != 1:
        return False
    text = non_empty[0].strip().upper()
    # Remove "AND" and check if all words are section keywords
    words = re.sub(r"\bAND\b", "", text).split()
    if words and all(w.lower() in _SECTION_KEYWORDS for w in words):
        return True
    # Handle pdfplumber stripping spaces: "POWERANDGROUND", "CONTROLOUTPUT", etc.
    text_no_and = text.replace("AND", "")
    for kw in _SECTION_KEYWORDS:
        text_no_and = text_no_and.replace(kw.upper(), " ")
    return text_no_and.strip() == ""


def _parse_pin_numbers(pin_str):
    """Parse a pin number string that may contain multiple pins.

    Examples:
        "5" → ["5"]
        "2,3,4" → ["2", "3", "4"]
        "1,12,13,24,\\nThermal pad" → ["1", "12", "13", "24", "EP"]
        "1,12,13,24,\\nThermalpad" → ["1", "12", "13", "24", "EP"]
        "EP" → ["EP"]
    """
    if not pin_str:
        return []

    # Normalize whitespace and newlines
    s = pin_str.replace("\n", ",").replace(";", ",").strip()

    parts = [p.strip() for p in s.split(",") if p.strip()]
    numbers = []
    for p in parts:
        if re.match(r"^\d+$", p):
            numbers.append(p)
        elif re.match(r"(?i)^(thermal\s*pad|thermalpad|epad|e\.?p\.?|pad|exposed\s*pad|power\s*pad|powerpad)", p):
            numbers.append("EP")
    return numbers


# Pin type inference from name/description
_PIN_TYPE_MAP = {
    # Power supply inputs
    r"^V(IN|CC|DD|BAT|BUS|SYS)$": "power_in",
    r"^[APD]?VDD$": "power_in",
    r"^DVDD$": "power_in",
    r"^AVDD$": "power_in",
    r"^PVDD$": "power_in",
    r"^VM$": "power_in",
    r"^VS$": "power_in",
    r"^VBB$": "power_in",
    r"^VDRAIN$": "power_in",
    # Power outputs
    r"^V(OUT|SW)$": "power_out",
    r"^VREG$": "power_out",
    # Ground
    r"^[APD]?GND$": "power_in",
    r"^EP$": "power_in",
    r"^PAD$": "power_in",
    r"^EPAD$": "power_in",
    r"^THERMAL\s*PAD$": "power_in",
    # Control / input
    r"^N?EN$": "input",
    r"^ENABLE$": "input",
    r"^N?SLEEP$": "input",
    r"^N?RESET$": "input",
    r"^(N)?SS$": "passive",
    r"^SYNC$": "input",
    r"^CLK$": "input",
    r"^RT$": "passive",
    r"^COMP$": "passive",
    r"^FB$": "input",
    r"^BOOT$": "passive",
    r"^BST$": "passive",
    r"^IN\d*[HL]?$": "input",
    r"^INH[12]?$": "input",
    r"^INL[12]?$": "input",
    r"^LDO(EN|FB)$": "input",
    r"^MODE$": "input",
    r"^DRVOFF$": "input",
    r"^VREF$": "passive",
    r"^REF$": "passive",
    r"^ISET$": "passive",
    r"^ILIM$": "passive",
    r"^PMODE$": "input",
    # Output
    r"^PG(OOD)?$": "open_collector",
    r"^N?FAULT$": "open_collector",
    r"^N?ALRT$": "open_collector",
    r"^N?ALERT$": "open_collector",
    r"^SW$": "power_out",
    r"^OUT[A-Z]?\d*$": "output",
    r"^LX$": "power_out",
    r"^PH$": "power_out",
    r"^LDOOUT$": "power_out",
    r"^VPROPI$": "output",
    r"^IPROPI$": "output",
    r"^IMON$": "output",
    # Motor driver outputs
    r"^OUT[12][HL]?$": "output",
    r"^[AB]OUT\d?$": "output",
    r"^GH[A-Z]?\d*$": "output",
    r"^GL[A-Z]?\d*$": "output",
    r"^SH[A-Z]?\d*$": "output",
    r"^SL[A-Z]?\d*$": "output",
    # Motor driver inputs
    r"^[AB]IN\d?$": "input",
    # Sense pins
    r"^[AB]ISEN$": "output",
    # Internal regulator
    r"^VINT$": "power_out",
    # I/O
    r"^SDA$": "bidirectional",
    r"^SCL$": "input",
    r"^GPIO\d*$": "bidirectional",
    r"^SR$": "passive",
    # No connect
    r"^NC$": "no_connect",
    r"^N\.?C\.?$": "no_connect",
    r"^DNC$": "no_connect",
    # Charge pump / bootstrap
    r"^VCP$": "passive",
    r"^CPH$": "passive",
    r"^CPL$": "passive",
}


def infer_pin_type(name, description=""):
    """Infer KiCad pin type from pin name and description."""
    name_upper = name.upper().strip()

    # Direct match from name
    for pattern, pin_type in _PIN_TYPE_MAP.items():
        if re.match(pattern, name_upper):
            return pin_type

    # Try description keywords
    desc_lower = (description or "").lower()
    if "power supply" in desc_lower or "supply voltage" in desc_lower:
        return "power_in"
    if "device supply" in desc_lower:
        return "power_in"
    if "ground" in desc_lower:
        return "power_in"
    if "motor supply" in desc_lower or "bridge supply" in desc_lower:
        return "power_in"
    if "output" in desc_lower and "input" not in desc_lower:
        return "output"
    if "half-bridge output" in desc_lower or "h-bridge output" in desc_lower:
        return "output"
    if "input" in desc_lower and "output" not in desc_lower:
        return "input"
    if "enable" in desc_lower:
        return "input"
    if "feedback" in desc_lower:
        return "input"
    if "open drain" in desc_lower or "open collector" in desc_lower:
        return "open_collector"
    if "fault" in desc_lower and "output" in desc_lower:
        return "open_collector"
    if "bidirectional" in desc_lower:
        return "bidirectional"
    if "no connect" in desc_lower or "not connected" in desc_lower:
        return "no_connect"
    if "do not connect" in desc_lower:
        return "no_connect"
    if "regulator output" in desc_lower:
        return "power_out"
    if "charge pump" in desc_lower:
        return "passive"
    if "bootstrap" in desc_lower:
        return "passive"
    if "bypass" in desc_lower or "decoupling" in desc_lower:
        return "passive"
    if "current sense" in desc_lower or "current monitor" in desc_lower:
        return "output"
    if "reference" in desc_lower:
        return "passive"
    if "compensation" in desc_lower or "soft start" in desc_lower:
        return "passive"

    return "passive"


def _parse_io_type(io_str):
    """Parse an I/O column value to a KiCad pin type."""
    if not io_str:
        return None
    io = io_str.strip().upper()
    mapping = {
        "I": "input",
        "O": "output",
        "I/O": "bidirectional",
        "IO": "bidirectional",
        "P": "power_in",
        "PWR": "power_in",
        "POWER": "power_in",
        "S": "passive",
        "ANALOG": "passive",
        "A": "passive",
        "OD": "open_collector",
        "OC": "open_collector",
        "OPEN DRAIN": "open_collector",
        "OPEN COLLECTOR": "open_collector",
        "INPUT": "input",
        "OUTPUT": "output",
        "BIDIRECTIONAL": "bidirectional",
        "GND": "power_in",
        "SUPPLY": "power_in",
        "-": None,
        "—": None,    # em-dash means power/ground (no logic direction)
        "\u2014": None,  # unicode em-dash
    }
    return mapping.get(io)


def _extract_pins_from_single_table(table, data_start, pin_col, name_col,
                                     type_col, desc_col, alt_func_cols=None,
                                     prev_io_type=None, prev_desc=""):
    """Extract PinInfo objects from one table's data rows.

    Returns (pins, prev_io_type, prev_desc) to allow continuation across tables.
    """
    if alt_func_cols is None:
        alt_func_cols = []
    data_rows = table[data_start:]
    pins = []

    for row in data_rows:
        if len(row) <= max(pin_col, name_col):
            continue

        if _is_section_header(row):
            continue

        pin_num_raw = (row[pin_col] or "").strip()
        pin_name = (row[name_col] or "").strip()

        # Clean up pin names with embedded newlines (e.g. "V\nM" -> "VM")
        pin_name = pin_name.replace("\n", "").strip()

        # Normalize full-word pin names to standard abbreviations
        pin_name_upper = pin_name.upper()
        if pin_name_upper in _PIN_NAME_NORMALIZATION:
            pin_name = _PIN_NAME_NORMALIZATION[pin_name_upper]

        if not pin_name:
            continue

        desc = ""
        if desc_col is not None and desc_col < len(row):
            desc = (row[desc_col] or "").strip()

        io_type = None
        if type_col is not None and type_col < len(row):
            io_type = _parse_io_type(row[type_col])

        # Continuation rows inherit type/desc from previous row
        if io_type is None and not desc and prev_io_type is not None:
            io_type = prev_io_type
            desc = prev_desc

        if (row[type_col] if type_col is not None and type_col < len(row) else None):
            prev_io_type = io_type
            prev_desc = desc

        # Extract alternate functions from alt function columns
        alt_functions = []
        for ac in alt_func_cols:
            if ac < len(row) and row[ac]:
                val = row[ac].strip()
                if val and val != "-":
                    alt_functions.append(val)

        pin_numbers = _parse_pin_numbers(pin_num_raw)
        if not pin_numbers:
            # Detect exposed/thermal pad rows where pin number is "-" or empty
            name_upper = pin_name.upper()
            desc_lower = (desc or "").lower()
            if re.match(r"^(PAD|EP|EPAD|THERMAL\s*PAD|POWER\s*PAD|EXPOSED\s*PAD)$", name_upper):
                pin_numbers = ["EP"]
            elif "thermal pad" in desc_lower or "exposed pad" in desc_lower:
                pin_numbers = ["EP"]
            else:
                continue

        pin_type = io_type or infer_pin_type(pin_name, desc)

        for num in pin_numbers:
            pins.append(PinInfo(
                number=num,
                name=pin_name,
                pin_type=pin_type,
                description=desc,
                alt_functions=alt_functions,
            ))

    return pins, prev_io_type, prev_desc


def extract_pins_from_tables(tables, expected_pin_count=0, target_package="", part_number=""):
    """Extract PinInfo objects from datasheet tables.

    Handles pin tables that span multiple pages by merging tables with
    matching column layouts.

    Args:
        tables: list of (page_num, table) as returned by parser.extract_tables_and_text
        expected_pin_count: if > 0, prefer tables whose unique pin count matches
        target_package: if set, prefer pin columns whose header matches this
            package name (e.g., "SOIC", "SOT-23") in multi-package tables

    Returns:
        (pins, confidence) where pins is a list of PinInfo and confidence is 0-1
    """
    # First pass: identify all pin tables with their column layouts
    # For multi-package tables (multiple pin columns), create a separate
    # entry for each pin column so they get scored independently.
    pin_tables = []
    for page_num, table in tables:
        if not table or len(table) < 2:
            continue
        headers, data_start = _detect_headers(table)
        if headers is None:
            continue
        pin_col, name_col, type_col, desc_col, alt_func_cols = _find_columns(headers)
        if name_col is None:
            continue
        if pin_col is None:
            continue

        # Check for multiple pin columns (multi-package tables)
        all_pin_cols = _find_all_pin_columns(headers, name_col)
        if len(all_pin_cols) > 1:
            # Create separate entries for each pin column variant
            for pc in all_pin_cols:
                col_header = (headers[pc] or "").replace("\n", " ").strip()
                pin_tables.append({
                    "page": page_num,
                    "table": table,
                    "data_start": data_start,
                    "cols": (pc, name_col, type_col, desc_col),
                    "alt_func_cols": alt_func_cols,
                    "col_header": col_header,
                })
        else:
            pin_tables.append({
                "page": page_num,
                "table": table,
                "data_start": data_start,
                "cols": (pin_col, name_col, type_col, desc_col),
                "alt_func_cols": alt_func_cols,
                "col_header": "",
            })

    if not pin_tables:
        return [], 0.0

    # Group consecutive pin tables with matching column layouts
    # (tables spanning multiple pages have the same column structure)
    groups = []
    current_group = [pin_tables[0]]
    for pt in pin_tables[1:]:
        prev = current_group[-1]
        # Match on pin + name columns only; type/desc may vary between sub-tables
        same_cols = (pt["cols"][0], pt["cols"][1]) == (prev["cols"][0], prev["cols"][1])
        consecutive = pt["page"] <= prev["page"] + 1
        if same_cols and consecutive:
            current_group.append(pt)
        else:
            groups.append(current_group)
            current_group = [pt]
    groups.append(current_group)

    # Extract pins from each group and pick the best
    best_pins = []
    best_score = (-1, 0.0)
    target_pkg_upper = target_package.upper() if target_package else ""
    # Extract base part number for variant column matching (e.g. ADS1115IDGSR -> ADS1115)
    pn_base_upper = ""
    if part_number:
        from ..core.config import strip_ti_suffix
        pn_base_upper = strip_ti_suffix(part_number)[0].upper()

    for group in groups:
        pins = []
        total_data_rows = 0
        prev_io = None
        prev_d = ""
        pkg_match = False
        for pt in group:
            pin_col, name_col, type_col, desc_col = pt["cols"]
            extracted, prev_io, prev_d = _extract_pins_from_single_table(
                pt["table"], pt["data_start"],
                pin_col, name_col, type_col, desc_col,
                alt_func_cols=pt.get("alt_func_cols", []),
                prev_io_type=prev_io, prev_desc=prev_d,
            )
            pins.extend(extracted)
            total_data_rows += len(pt["table"]) - pt["data_start"]
            # Check if column header matches target package
            if target_pkg_upper and pt.get("col_header"):
                col_h = pt["col_header"].upper()
                # Strip pin count suffix for matching
                # e.g., "SOIC-8" → "SOIC", "SOT-23-5" → "SOT-23"
                target_base = re.sub(r'[\-]\d+$', '', target_pkg_upper)
                col_base = re.sub(r'[\-]\d+$', '', col_h)
                # Match if base package family appears in column header
                if (target_base and col_base and
                    (target_base in col_h or col_base in target_pkg_upper
                     or target_base == col_base)):
                    pkg_match = True

        if pins:
            unique_nums = set(p.number for p in pins)
            n_unique = len(unique_nums)
            confidence = min(1.0, n_unique / max(total_data_rows, 1))

            priority = n_unique
            if expected_pin_count > 0 and n_unique == expected_pin_count:
                priority += 10000
            # Boost score for package name match in column header
            if pkg_match:
                priority += 100000
            # Boost for part number variant match in column header
            # (e.g. prefer "ADS1115" column over "ADS1113" when part is ADS1115)
            if pn_base_upper and group[0].get("col_header"):
                col_h = group[0]["col_header"].upper().replace("PIN ", "")
                if pn_base_upper in col_h or col_h in pn_base_upper:
                    priority += 50000

            score = (priority, confidence)
            if score > best_score:
                best_pins = pins
                best_score = score

    best_confidence = best_score[1] if best_pins else 0.0

    # Deduplicate by pin number, keeping first occurrence
    if best_pins:
        seen = set()
        deduped = []
        for pin in best_pins:
            if pin.number not in seen:
                seen.add(pin.number)
                deduped.append(pin)
        best_pins = deduped

    # Quality check: reject results where pin names are obviously garbage
    if best_pins:
        avg_name_len = sum(len(p.name) for p in best_pins) / len(best_pins)
        if avg_name_len > 20:
            # Names are unreasonably long -- table extraction is broken
            return [], 0.0

        # Check if pin names look like real pin names vs specs table junk.
        # Real pin names typically contain standard patterns: VCC, GND, IN, OUT,
        # EN, FB, SW, GPIO, SDA, SCL, etc. If very few names match standard
        # patterns and many look like random words, this is probably a specs table.
        _STANDARD_PIN_PATTERNS = re.compile(
            r"^(V(CC|DD|IN|OUT|REF|BAT|BUS|SS|EE|REG|SYS|S\+?)|"
            r"[AP]?GND|EP|NC|N/C|"
            r"EN|FB|SW|BOOT|BST|COMP|SS|PG|RT|CLK|"
            r"IN\d?|OUT\d?|"
            r"SDA|SCL|MOSI|MISO|SCLK|CS|"
            r"TXD?|RXD?|CTS|RTS|DTR|DSR|DCD|RI|"
            r"GPIO\d+|P[A-Z]\d+|IO[BT]_|"
            r"[A-Z]{1,3}\d*[\+\-]?|"       # short alphanumeric like A, B, D, G, S
            r"\d+[A-Z]{2,}[\+\-]?|"        # unit-prefixed: 1OUT, 2IN+, 3IN-
            r"[\+\-\u2013][A-Z]{2,}[A-D]?|"  # polarity-prefixed: +IN, -INA, +INB
            r"[A-Z][A-Z0-9_/\-\+]{0,12})$",  # standard length pin names
            re.I,
        )
        good_names = sum(1 for p in best_pins
                         if _STANDARD_PIN_PATTERNS.match(p.name.strip()))
        if len(best_pins) >= 3 and good_names < len(best_pins) * 0.4:
            # Less than 40% of names look like real pin names -- likely a specs table
            return [], 0.0

    # Auto-add EP pin if descriptions mention PowerPAD/thermal pad and no EP exists
    if best_pins:
        has_ep = any(p.number == "EP" for p in best_pins)
        if not has_ep:
            all_descs = " ".join(p.description for p in best_pins).lower()
            if re.search(r"power\s*pad|thermal\s*pad|exposed\s*pad", all_descs):
                best_pins.append(PinInfo(
                    number="EP",
                    name="GND",
                    pin_type="power_in",
                    description="Exposed thermal pad",
                ))

    return best_pins, best_confidence


def _detect_headers(table):
    """Detect header row(s) in a table, handling single and two-row headers.

    Returns (merged_headers, data_start_row) or (None, None).
    """
    if len(table) < 2:
        return None, None

    # Try row 0 as a single-row header
    if _is_pin_table(table[0]):
        return table[0], 1

    # Try merging rows 0+1 (two-row header)
    if len(table) > 2:
        merged = _merge_header_rows(table[0], table[1])
        if _is_pin_table(merged):
            return merged, 2

    # Try row 1 as header (row 0 is a title like "PIN")
    if len(table) > 2 and _is_pin_table(table[1]):
        return table[1], 2

    # Special case: row 0 has "PIN" in first cell (rest empty), row 1 has
    # "NAME | variant1 | variant2 | TYPE | DESC". This is a two-row header
    # where row 0 is a section title. Treat row 1 as header, but we need
    # to recognize variant columns as pin number columns.
    if len(table) > 2:
        row0_cells = [str(c).strip().upper() if c else "" for c in table[0]]
        row0_nonempty = [c for c in row0_cells if c]
        # Row 0 starts with "PIN"/"PINS" (may also have TYPE/DESC in other cells)
        if row0_nonempty and row0_nonempty[0] in ("PIN", "PINS"):
            # Row 0 is just "PIN" - row 1 has the real column headers
            row1 = table[1]
            row1_cells = [str(c).strip() if c else "" for c in row1]
            # Find NAME column in row 1
            name_idx = None
            for idx, cell in enumerate(row1_cells):
                if cell and any(p.match(cell) for p in _NAME_COL_PATTERNS):
                    name_idx = idx
                    break
            if name_idx is not None:
                # Remaining non-empty columns with digits or variant codes = pin cols
                # Synthesize a header with the first such column as pin_col
                synth_header = list(row1_cells)
                for idx, cell in enumerate(row1_cells):
                    if idx != name_idx and cell and idx < len(row1_cells):
                        # Check if this could be a pin number column
                        # (contains digits, or is a known type/desc column)
                        if any(p.match(cell) for p in _TYPE_COL_PATTERNS):
                            continue
                        if any(p.match(cell) for p in _DESC_COL_PATTERNS):
                            continue
                        # Treat as pin number column by relabeling header
                        synth_header[idx] = "PIN " + cell
                if _is_pin_table(synth_header):
                    return synth_header, 2

    # Try merging rows 1+2 (row 0 is a title, rows 1+2 are split header)
    if len(table) > 3:
        merged = _merge_header_rows(table[1], table[2])
        if _is_pin_table(merged):
            return merged, 3

    return None, None


def consolidate_power_pins(pins):
    """Consolidate same-name power_in pins into single pins with alt_numbers.

    Multiple GND or VCC pins at different pin numbers are stacked in KiCad
    symbols — each gets its own pin node but at the same position. This
    function groups power_in pins by name and merges duplicates.

    Only power_in pins are consolidated. Signal pins are never merged.
    """
    from collections import OrderedDict

    # Group power_in pins by uppercase name
    groups = OrderedDict()  # (name_upper,) → [PinInfo, ...]
    result = []

    for pin in pins:
        if pin.pin_type == "power_in":
            key = pin.name.upper()
            if key not in groups:
                groups[key] = []
            groups[key].append(pin)
        else:
            result.append(pin)

    # For each power group, keep first as primary, rest go to alt_numbers
    for key, group in groups.items():
        primary = group[0]
        if len(group) > 1:
            primary.alt_numbers = [p.number for p in group[1:]]
        result.append(primary)

    return result


def extract_pins_from_text(text, pin_count_hint=0):
    """Fallback: extract pins from free text when no table is found.

    Handles two formats:
    1. ADI-style structured sections: "Pin No. Mnemonic Description" header
       followed by "1 BST Bootstrap Supply..." lines
    2. Generic patterns: "Pin 1 (GND)" or "1 GND Power ground"
    """
    pins = []

    # Strategy 1: ADI structured pin description section
    # Detect a header like "Pin No. Mnemonic Description" or
    # "Pin No. Name Description" then parse lines below it.
    # Also handles multi-line variants where "Pin No." is on its own line,
    # followed by package columns: "LFCSP TSSOP Mnemonic Description"
    section_header = re.compile(
        r"^Pin\s+No\.?\s+"
        r"(?:Mnemonic|Name|Symbol)\s+"
        r"(?:Description|Function)",
        re.I | re.MULTILINE,
    )
    # Multi-line variant: "Pin No.\n<pkg1> <pkg2> Mnemonic Description"
    section_header_multiline = re.compile(
        r"^Pin\s+No\.?\s*$\n"
        r"^(?:[A-Z][\w-]*\s+)*"  # package column headers (e.g., "LFCSP TSSOP")
        r"(?:Mnemonic|Name|Symbol)\s+"
        r"(?:Description|Function)",
        re.I | re.MULTILINE,
    )
    m_header = section_header.search(text)
    if not m_header:
        m_header = section_header_multiline.search(text)
    if m_header:
        # Parse lines after the header, stopping at the next section
        after = text[m_header.end():]

        # Find where the pin section ends: look for common section headers
        # that follow pin descriptions (e.g., "TYPICAL APPLICATION",
        # "ABSOLUTE MAXIMUM", "ELECTRICAL", "Figure N.", "Table N.")
        section_end = re.compile(
            r"^(?:TYPICAL|ABSOLUTE|ELECTRICAL|THERMAL|ORDERING|"
            r"PACKAGE|APPLICATION|BLOCK\s+DIAGRAM|Figure\s+\d|Table\s+\d"
            r"|Rev\.\s+[A-Z])",
            re.I | re.MULTILINE,
        )
        m_end = section_end.search(after)
        if m_end:
            after = after[:m_end.start()]

        # Pin line patterns:
        # Single package: "1 BST Bootstrap Supply..."
        # Dual package: "1 3 INBK Input Disconnect..." (two numbers before name)
        pin_line_dual = re.compile(
            r"^(\d+)\s+(\d+)\s+([A-Z][A-Z0-9_/\-\+\.]*(?:\s*/\s*[A-Z][A-Z0-9_/\-\+\.]*)?)\s+(.*?)$",
            re.MULTILINE,
        )
        pin_line_single = re.compile(
            r"^(\d+)\s*(?:\(EPAD\)\s*)?([A-Z][A-Z0-9_/\-\+\.]*(?:\s*/\s*[A-Z][A-Z0-9_/\-\+\.]*)?)\s+(.*?)$",
            re.MULTILINE,
        )

        # Try dual-column first (if most lines match dual pattern, use it)
        dual_matches = list(pin_line_dual.finditer(after))
        single_matches = list(pin_line_single.finditer(after))

        if len(dual_matches) >= 3 and len(dual_matches) >= len(single_matches) * 0.5:
            # Dual-column: use the LAST pin number column (usually the main package)
            for m in dual_matches:
                num = m.group(2)  # second number column (e.g., TSSOP)
                name = m.group(3).strip()
                desc = m.group(4).strip()
                if int(num) > 200:
                    continue
                if re.match(r"^[0-9.]+[A-Z]$", name):
                    continue
                pin_type = infer_pin_type(name, desc)
                pins.append(PinInfo(
                    number=num, name=name, pin_type=pin_type, description=desc,
                ))
        else:
            # Single-column
            for m in single_matches:
                num = m.group(1)
                name = m.group(2).strip()
                desc = m.group(3).strip()
                if int(num) > 200:
                    continue
                if re.match(r"^[0-9.]+[A-Z]$", name):
                    continue
                pin_type = infer_pin_type(name, desc)
                pins.append(PinInfo(
                    number=num, name=name, pin_type=pin_type, description=desc,
                ))

        # Check for exposed pad line (often formatted differently)
        # ADI format: "9 (EPAD) Exposed Pad ..." or "EPAD Exposed Pad ..."
        epad = re.compile(
            r"^(?:\d+\s+)?(?:\d+\s+)?(?:\(EPAD\)\s*)?(?:EPAD|Exposed\s+Pad)\s+(.*?)$",
            re.I | re.MULTILINE,
        )
        for m in epad.finditer(after):
            if not any(p.number == "EP" for p in pins):
                pins.append(PinInfo(
                    number="EP", name="GND", pin_type="power_in",
                    description=m.group(1).strip() if m.group(1) else "Exposed pad",
                ))

    # Strategy 2: LT-style paragraph pin functions
    # Format: "NAME (Pin N/Pin M): Description..." or "NAME (Pins N, M/Pins P, Q): ..."
    # The slash separates DFN/MSOP pin numbers. Use the LAST set (after last slash).
    # Search the entire text — two-column layouts can scatter pin descriptions.
    if not pins:
        has_pin_functions = re.search(r"PIN\s+FUNCTIONS", text, re.I)
        if has_pin_functions:
            # Pre-process: join text within parentheses that spans newlines.
            # Two-column layouts can interleave text from other paragraphs
            # inside pin declarations. Repeatedly join until stable.
            joined = text
            for _ in range(5):
                new = re.sub(r"\(([^)]*)\n([^)]*)\)", lambda m: "(" + m.group(1) + " " + m.group(2) + ")", joined)
                if new == joined:
                    break
                joined = new

            # Match: NAME (Pin N[, N][, Exposed Pad Pin X]/Pin M[, M][, Exposed Pad Pin Y]):
            lt_pin = re.compile(
                r"([A-Z][A-Z0-9_/]*)"                    # pin name
                r"\s*\("
                r"(?:Pins?\s+[\d]+(?:\s*,\s*\d+)*"       # first package pins
                r"(?:\s*,\s*Exposed\s+Pad\s+Pin\s+\d+)?" # optional EP in first pkg
                r"\s*/)?"                                  # slash separator
                r"Pins?\s+([\d]+(?:\s*,\s*\d+)*)"         # second package pin numbers
                r"(?:\s*,\s*Exposed\s+Pad\s+Pin\s+(\d+))?" # optional exposed pad
                r"\)\s*:",                                  # closing paren + colon
            )
            for m in lt_pin.finditer(joined):
                name = m.group(1).strip()
                pin_nums_str = m.group(2).strip()
                epad_num = m.group(3)

                # Skip if name is a common word, not a pin name
                if name.upper() in {"THE", "FOR", "AND", "WITH", "FROM", "THIS", "THAT",
                                     "NOTE", "TABLE", "FIGURE", "SEE", "WHEN", "PIN"}:
                    continue

                # Parse comma-separated pin numbers
                pin_nums = [n.strip() for n in pin_nums_str.split(",") if n.strip().isdigit()]
                if not pin_nums:
                    continue

                # Get description (text after "): ")
                desc_start = m.end()
                desc_text = joined[desc_start:desc_start + 200].strip()
                # Take just the first sentence
                desc = desc_text.split(".")[0].strip() + "." if "." in desc_text else desc_text[:80]

                pin_type = infer_pin_type(name, desc)
                primary = pin_nums[0]
                pin = PinInfo(number=primary, name=name, pin_type=pin_type, description=desc)
                if len(pin_nums) > 1:
                    pin.alt_numbers = pin_nums[1:]
                pins.append(pin)

                # Add exposed pad if mentioned
                if epad_num and not any(p.number == "EP" for p in pins):
                    pins.append(PinInfo(
                        number="EP", name=name, pin_type="power_in",
                        description="Exposed pad",
                    ))

    # Strategy 3: Generic patterns (only if strategies 1-2 found nothing)
    if not pins:
        pin_patterns = [
            re.compile(r"Pin\s+(\d+)\s*[–\-:]\s*(\w+)", re.I),
            re.compile(r"^(\d+)\s+([A-Z][A-Z0-9_/]+)\s+(.*)$", re.MULTILINE),
        ]

        for pattern in pin_patterns:
            for m in pattern.finditer(text):
                num = m.group(1)
                name = m.group(2).strip()
                desc = m.group(3).strip() if m.lastindex >= 3 else ""

                if int(num) > 200:
                    continue
                if len(name) > 20:
                    continue
                if re.match(r"^[0-9.]+$", name):
                    continue

                pin_type = infer_pin_type(name, desc)
                pins.append(PinInfo(
                    number=num, name=name, pin_type=pin_type, description=desc,
                ))

    # Strategy 4: Discrete semiconductor template pinout
    # When few/bad pins found and text indicates a MOSFET/BJT/diode, use standard
    # SOT-23 or TO-92 pinouts based on detected component type.
    # Override junk pins from Strategy 3 if the text clearly indicates a discrete.
    # Check if existing pins look like junk (non-standard names, high pin numbers)
    _looks_like_junk = (not pins or
        any(int(p.number) > 50 for p in pins if p.number.isdigit()) or
        any(p.name.upper() in ("NATSISE", "CRUOS") for p in pins) or
        len([p for p in pins if p.number.isdigit() and int(p.number) <= 4]) < pin_count_hint)
    if pin_count_hint <= 4 and _looks_like_junk:
        text_upper = text.upper()
        is_nch_mosfet = ("N-CHANNEL" in text_upper or "NMOS" in text_upper) and (
            "MOSFET" in text_upper or "FET" in text_upper or "DRAIN" in text_upper)
        is_pch_mosfet = ("P-CHANNEL" in text_upper or "PMOS" in text_upper) and (
            "MOSFET" in text_upper or "FET" in text_upper or "DRAIN" in text_upper)
        is_npn = "NPN" in text_upper and ("TRANSISTOR" in text_upper or "BJT" in text_upper
                                           or "COLLECTOR" in text_upper)
        is_pnp = "PNP" in text_upper and ("TRANSISTOR" in text_upper or "BJT" in text_upper
                                           or "COLLECTOR" in text_upper)

        if is_nch_mosfet or is_pch_mosfet:
            # SOT-23 MOSFET standard: 1=Gate, 2=Source, 3=Drain
            pins = [
                PinInfo(number="1", name="G", pin_type="input", description="Gate"),
                PinInfo(number="2", name="S", pin_type="passive", description="Source"),
                PinInfo(number="3", name="D", pin_type="passive", description="Drain"),
            ]
        elif is_npn or is_pnp:
            # TO-92 BJT (CBE pinout - standard for most NPN/PNP transistors)
            pins = [
                PinInfo(number="1", name="C", pin_type="passive", description="Collector"),
                PinInfo(number="2", name="B", pin_type="input", description="Base"),
                PinInfo(number="3", name="E", pin_type="passive", description="Emitter"),
            ]

    # Deduplicate by pin number, keeping first occurrence
    seen = set()
    unique_pins = []
    for pin in pins:
        if pin.number not in seen:
            seen.add(pin.number)
            unique_pins.append(pin)

    confidence = 0.5 if (m_header and unique_pins) else (0.3 if unique_pins else 0.0)
    return unique_pins, confidence
