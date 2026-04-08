"""
Symbol matcher: find the best existing KiCad symbol for a given part.

Search strategy (in order of preference):
1. Exact part number match in symbol libraries
2. Base part number match (strip suffixes)
3. Close match: same pin count with similar pin names
4. Generic match: component type family (e.g. generic voltage regulator)
"""

from ..core.config import strip_ti_suffix
from ..core.models import DatasheetData, MatchResult
from .library_index import LibraryIndex


# Generic symbol fallbacks by component type
_GENERIC_SYMBOLS = {
    "voltage regulator": [
        ("Regulator_Switching", "TPS5430"),
        ("Regulator_Linear", "LM317_TO-252"),
    ],
    "op_amp": [("Amplifier_Operational", "LM358")],
    "adc": [("Analog_ADC", "MCP3008")],
    "led_driver": [("Driver_LED", "TLC5940")],
    # Tier 2 component types
    "mcu": [
        ("MCU_ST_STM32F1", "STM32F103C8Tx"),
        ("MCU_Microchip_ATmega", "ATmega328P-AU"),
    ],
    "microcontroller": [
        ("MCU_ST_STM32F1", "STM32F103C8Tx"),
        ("MCU_Microchip_ATmega", "ATmega328P-AU"),
    ],
    "fpga": [
        ("FPGA_Lattice", "ICE40UP5K-SG48"),
    ],
    "cpld": [
        ("FPGA_Lattice", "ICE40UP5K-SG48"),
    ],
    "memory": [
        ("Memory_Flash", "W25Q128JVS"),
    ],
    "flash": [
        ("Memory_Flash", "W25Q128JVS"),
    ],
    "eeprom": [
        ("Memory_EEPROM", "AT24C256C-SSHL-T"),
    ],
    "sram": [
        ("Memory_RAM", "IS62WV12816DALL"),
    ],
    "mosfet": [
        ("Transistor_FET", "IRF540N"),
    ],
    "n_mosfet": [
        ("Transistor_FET", "IRF540N"),
    ],
    "p_mosfet": [
        ("Transistor_FET", "IRF9540N"),
    ],
    "diode": [
        ("Diode", "1N4148"),
    ],
    "zener": [
        ("Diode", "BZX84Cxx"),
    ],
    "bjt_npn": [
        ("Transistor_BJT", "BC547"),
    ],
    "bjt_pnp": [
        ("Transistor_BJT", "BC557"),
    ],
    "bjt": [
        ("Transistor_BJT", "BC547"),
    ],
    "igbt": [
        ("Transistor_IGBT", "IRG4PC40U"),
    ],
    "comparator": [
        ("Comparator", "LM393"),
    ],
    "interface": [
        ("Interface_CAN_LIN", "MCP2551-I-SN"),
    ],
    "sensor": [
        ("Sensor_Temperature", "LM75BIM"),
    ],
}


def match_symbol(datasheet: DatasheetData, index: LibraryIndex) -> MatchResult:
    """Find the best matching KiCad symbol for the given datasheet data.

    Returns a MatchResult with symbol_lib, symbol_name, symbol_score, and pin_mapping.
    """
    result = MatchResult()
    pn = datasheet.part_number.upper().strip()
    base_pn = strip_ti_suffix(pn)[0]
    pin_count = len(datasheet.pins)

    # Strategy 1: Exact match
    matches = index.search_symbols(pn, pin_count)
    if matches and matches[0][2] >= 100:
        lib, entry, score = matches[0]
        result.symbol_lib = lib
        result.symbol_name = entry["name"]
        result.symbol_score = score
        result.pin_mapping = _build_pin_mapping(datasheet.pins, entry.get("pins", []))
        return result

    # Keep the original search results for strategies 3 and 4
    initial_matches = matches

    # Strategy 2: Base part number match
    if base_pn != pn:
        base_matches = index.search_symbols(base_pn, pin_count)
        if base_matches and base_matches[0][2] >= 80:
            lib, entry, score = base_matches[0]
            result.symbol_lib = lib
            result.symbol_name = entry["name"]
            result.symbol_score = score
            result.pin_mapping = _build_pin_mapping(datasheet.pins, entry.get("pins", []))
            return result
        # Merge base matches into initial if they found more results
        if base_matches and (not initial_matches or base_matches[0][2] > initial_matches[0][2]):
            initial_matches = base_matches

    # Strategy 3: Close match — same pin count, similar pin names
    if pin_count > 0 and initial_matches:
        for lib, entry, score in initial_matches[:10]:
            if entry["pin_count"] == pin_count:
                pin_overlap = _pin_name_overlap(datasheet.pins, entry.get("pins", []))
                if pin_overlap > 0.5:
                    result.symbol_lib = lib
                    result.symbol_name = entry["name"]
                    result.symbol_score = score * pin_overlap
                    result.pin_mapping = _build_pin_mapping(datasheet.pins, entry.get("pins", []))
                    return result

    # Strategy 4: Best available match from initial search
    if initial_matches:
        lib, entry, score = initial_matches[0]
        result.symbol_lib = lib
        result.symbol_name = entry["name"]
        result.symbol_score = score
        result.pin_mapping = _build_pin_mapping(datasheet.pins, entry.get("pins", []))
        return result

    # Strategy 5: Generic fallback by component type
    comp_type = datasheet.component_type
    if comp_type in _GENERIC_SYMBOLS:
        for lib, name in _GENERIC_SYMBOLS[comp_type]:
            entry = index.get_symbol_entry(lib, name)
            if entry:
                result.symbol_lib = lib
                result.symbol_name = name
                result.symbol_score = 10.0
                result.pin_mapping = _build_pin_mapping(datasheet.pins, entry.get("pins", []))
                return result

    return result


def _build_pin_mapping(ds_pins, sym_pins):
    """Build a mapping from datasheet pin numbers to symbol pin numbers.

    Returns dict: {ds_pin_number: sym_pin_number}
    """
    mapping = {}
    sym_by_name = {p["name"].upper(): p["number"] for p in sym_pins}
    sym_by_num = {p["number"]: p["name"] for p in sym_pins}

    for pin in ds_pins:
        ds_name = pin.name.upper()
        ds_num = pin.number

        # First try matching by name
        if ds_name in sym_by_name:
            mapping[ds_num] = sym_by_name[ds_name]
        # Then try matching by number
        elif ds_num in sym_by_num:
            mapping[ds_num] = ds_num
        else:
            mapping[ds_num] = ds_num  # default: keep same number

    return mapping


def _pin_name_overlap(ds_pins, sym_pins):
    """Calculate the fraction of datasheet pin names that match symbol pin names."""
    if not ds_pins or not sym_pins:
        return 0.0

    sym_names = {p["name"].upper() for p in sym_pins}
    matches = sum(1 for p in ds_pins if p.name.upper() in sym_names)
    return matches / len(ds_pins)
