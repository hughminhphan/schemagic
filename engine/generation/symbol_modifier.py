"""
Symbol modifier: clone an existing KiCad symbol and modify it to match a
target part's pin assignments.

Handles:
- Cloning a symbol from the official KiCad libraries
- Resolving `extends` inheritance into a standalone symbol
- Renaming the symbol and updating properties
- Modifying pin names, types, and numbers
- Regenerating all UUIDs
"""

import os
import re

from ..core.config import SYMBOL_DIR
from ..core.models import DatasheetData, PinInfo
from .sexpr import parse_file, SExprNode, regenerate_uuids, new_uuid


def _fmt(v):
    """Format a numeric value for KiCad, avoiding floating point noise."""
    r = round(v, 4)
    if r == int(r):
        return str(int(r))
    return f"{r:g}"


def clone_and_modify_symbol(datasheet: DatasheetData, source_lib: str,
                            source_name: str, pin_mapping: dict = None):
    """Clone a symbol from the KiCad libraries and modify it.

    Args:
        datasheet: parsed datasheet data with pins and properties
        source_lib: library name (e.g. "Regulator_Switching")
        source_name: symbol name in that library (e.g. "TPS54302")
        pin_mapping: optional {datasheet_pin_num: symbol_pin_num} override

    Returns:
        SExprNode: the modified symbol node, ready to be added to a library file
    """
    # Load the source library
    if not SYMBOL_DIR:
        raise FileNotFoundError(
            "KiCad symbol libraries not found. Check your KiCad installation "
            "or set the KICAD8_SYMBOL_DIR environment variable."
        )
    lib_path = os.path.join(SYMBOL_DIR, f"{source_lib}.kicad_sym")
    if not os.path.isfile(lib_path):
        raise FileNotFoundError(f"Symbol library not found: {lib_path}")

    nodes = parse_file(lib_path)
    root = nodes[0]

    # Find the source symbol
    source_sym = None
    for sym in root.find_all("symbol"):
        if sym.get_value(0) == source_name:
            source_sym = sym
            break

    if not source_sym:
        raise ValueError(f"Symbol '{source_name}' not found in {source_lib}")

    # Clone it
    new_sym = source_sym.clone()

    # Resolve extends if needed
    extends_node = new_sym.find_child("extends")
    if extends_node:
        parent_name = extends_node.get_value(0)
        new_sym = _resolve_extends(root, new_sym, parent_name)

    # Rename the symbol
    target_name = datasheet.part_number.upper()
    _rename_symbol(new_sym, source_name, target_name)

    # Update properties
    new_sym.set_property("Value", target_name)
    if datasheet.description:
        new_sym.set_property("Description", datasheet.description)
    if datasheet.datasheet_url:
        new_sym.set_property("Datasheet", datasheet.datasheet_url)

    # Set footprint property if we have package info
    if datasheet.package:
        from ..core.config import PACKAGE_MAP
        fp = ""
        if datasheet.package.ti_code in PACKAGE_MAP:
            fp = PACKAGE_MAP[datasheet.package.ti_code]
        elif datasheet.package.name in PACKAGE_MAP:
            fp = PACKAGE_MAP[datasheet.package.name]
        if fp:
            new_sym.set_property("Footprint", fp)

    # Modify pins to match datasheet
    _update_pins(new_sym, datasheet.pins, pin_mapping)

    # Stack same-name pins at the same position for clean symbol layout
    _stack_same_name_pins(new_sym)

    # Regenerate all UUIDs
    regenerate_uuids(new_sym)

    return new_sym


def _resolve_extends(root, sym, parent_name):
    """Resolve an `extends` symbol by merging parent graphics and pins."""
    parent = None
    for s in root.find_all("symbol"):
        if s.get_value(0) == parent_name:
            parent = s
            break

    if not parent:
        return sym

    # Start with a clone of the parent
    resolved = parent.clone()

    # Copy over properties from the child (they override parent)
    child_props = {c.get_value(0): c for c in sym.find_all("property")}
    for prop_name, prop_node in child_props.items():
        existing = None
        for p in resolved.find_all("property"):
            if p.get_value(0) == prop_name:
                existing = p
                break
        if existing:
            resolved.remove_child(existing)
        resolved.add_child(prop_node.clone())

    # Remove extends node if present
    ext = resolved.find_child("extends")
    if ext:
        resolved.remove_child(ext)

    # Use the child's name
    resolved.set_value(0, sym.get_value(0))

    return resolved


def _rename_symbol(sym, old_name, new_name):
    """Rename a symbol and all its sub-symbols."""
    sym.set_value(0, new_name)

    # Rename sub-symbols (e.g. "TPS54302_0_1" → "NEW_NAME_0_1")
    for child in sym.find_all("symbol"):
        child_name = child.get_value(0)
        if child_name and child_name.startswith(old_name):
            suffix = child_name[len(old_name):]
            child.set_value(0, new_name + suffix)


def _update_pins(sym, ds_pins: list, pin_mapping: dict = None):
    """Update the pins in a symbol to match the datasheet pins.

    If pin_mapping is provided, it maps datasheet pin numbers to symbol pin numbers.
    Otherwise, pins are matched by number directly.
    """
    if not ds_pins:
        return

    # Build lookup of datasheet pins by number (primary + alts)
    ds_by_num = {}
    for p in ds_pins:
        ds_by_num[p.number] = p
        for alt in p.alt_numbers:
            ds_by_num[alt] = p

    # If we have a pin mapping, invert it: sym_pin_num → ds_pin
    if pin_mapping:
        sym_to_ds = {}
        for ds_num, sym_num in pin_mapping.items():
            if ds_num in ds_by_num:
                sym_to_ds[sym_num] = ds_by_num[ds_num]
    else:
        sym_to_ds = ds_by_num

    # Find all pin nodes in the symbol
    all_pins = sym.find_recursive("pin")

    for pin_node in all_pins:
        num_node = pin_node.find_child("number")
        name_node = pin_node.find_child("name")
        if not num_node:
            continue

        pin_num = num_node.get_value(0)
        ds_pin = sym_to_ds.get(pin_num)

        if ds_pin:
            # Update pin name
            if name_node:
                name_node.set_value(0, ds_pin.name)

            # Update pin type (first value of the pin node)
            pin_node.set_value(0, ds_pin.pin_type)


def _stack_same_name_pins(sym):
    """Stack same-name pins at the same position in a cloned symbol.

    After pin names are updated, pins that share a name (e.g. OUT1 on pads
    2, 3, 4) are moved to the same coordinates. KiCad shows one pin visually
    but connects all pad numbers electrically.
    """
    all_pins = sym.find_recursive("pin")

    # Group pin nodes by name
    by_name = {}
    for pin_node in all_pins:
        name_node = pin_node.find_child("name")
        if not name_node:
            continue
        name = name_node.get_value(0).upper()
        if name not in by_name:
            by_name[name] = []
        by_name[name].append(pin_node)

    # For groups with >1 pin, move duplicates to the primary pin's position
    for name, group in by_name.items():
        if len(group) <= 1:
            continue

        primary_at = group[0].find_child("at")
        if not primary_at:
            continue

        # Copy position from primary to all duplicates
        for pin_node in group[1:]:
            dup_at = pin_node.find_child("at")
            if dup_at:
                dup_at.set_value(0, primary_at.get_value(0))
                dup_at.set_value(1, primary_at.get_value(1))
                dup_at.set_value(2, primary_at.get_value(2))


def _consolidate_pins(pins):
    """Consolidate same-name pins into single pins with alt_numbers.

    E.g. three OUT1 pins (numbers 2, 3, 4) become one OUT1 pin (number 2,
    alt_numbers [3, 4]). This matches the frontend preview and produces
    cleaner KiCad symbols with stacked pins.
    """
    by_name = {}
    order = []
    for pin in pins:
        key = pin.name.upper()
        if key in by_name:
            by_name[key].append(pin)
        else:
            by_name[key] = [pin]
            order.append(key)

    result = []
    for key in order:
        group = by_name[key]
        primary = group[0]
        # Collect all extra pin numbers as alt_numbers
        extra_nums = list(primary.alt_numbers) if primary.alt_numbers else []
        for p in group[1:]:
            extra_nums.append(p.number)
            if p.alt_numbers:
                extra_nums.extend(p.alt_numbers)
        result.append(PinInfo(
            number=primary.number,
            name=primary.name,
            pin_type=primary.pin_type,
            description=getattr(primary, 'description', ''),
            alt_numbers=extra_nums,
        ))
    return result


def create_empty_symbol(datasheet: DatasheetData, footprint_str=""):
    """Create a new symbol from scratch when no match is found.

    Generates a simple rectangular symbol with all pins.
    Same-name pins are consolidated: one visible pin per name, with
    duplicate pad numbers stacked at the same position.
    TODO: For MCUs/FPGAs with 48+ pins, generate multi-unit symbols with pins
    grouped by function (GPIO Port A, Port B, power, etc.) instead of one
    massive rectangle. See vault: Projects/schemagic/Component Scope.md
    """
    target_name = datasheet.part_number.upper()

    # Separate hidden pins (thermal pads) before consolidation
    visible_pins = [p for p in datasheet.pins if not getattr(p, "is_hidden", False)]
    thermal_hidden = [p for p in datasheet.pins if getattr(p, "is_hidden", False)]

    # Consolidate same-name visible pins before layout
    consolidated = _consolidate_pins(visible_pins)
    pin_count = len(consolidated)

    # Calculate box size
    left_pins = []
    right_pins = []
    bottom_pins = []

    for pin in consolidated:
        if pin.pin_type in ("power_in",) and pin.name.upper() in ("GND", "AGND", "PGND", "EP", "EPAD", "PAD"):
            bottom_pins.append(pin)
        elif pin.pin_type in ("power_in",):
            left_pins.append(pin)
        elif pin.pin_type in ("power_out", "output", "open_collector"):
            right_pins.append(pin)
        elif pin.pin_type in ("input",):
            left_pins.append(pin)
        else:
            right_pins.append(pin)

    # Ensure balance
    if not left_pins and not right_pins:
        half = pin_count // 2
        left_pins = consolidated[:half]
        right_pins = consolidated[half:]

    max_side = max(len(left_pins), len(right_pins), 1)
    # Extra height at the bottom so rotated bottom-pin names don't collide
    # with the lowest side pins
    bottom_clearance = 5.08 if bottom_pins else 0
    box_h = max_side * 2.54 + 2.54 + bottom_clearance
    # Widen box if many bottom pins need horizontal space
    min_bottom_w = len(bottom_pins) * 2.54 + 5.08 if bottom_pins else 0
    box_w = max(15.24, min_bottom_w)
    half_h = box_h / 2
    half_w = box_w / 2

    # Build the symbol node
    sym = SExprNode("symbol", [target_name])

    # Metadata
    sym.add_child(SExprNode("exclude_from_sim", ["no"]))
    sym.add_child(SExprNode("in_bom", ["yes"]))
    sym.add_child(SExprNode("on_board", ["yes"]))

    # Pin names configuration
    pin_names = SExprNode("pin_names")
    pin_names.add_child(SExprNode("offset", ["1.016"]))
    sym.add_child(pin_names)

    # Properties
    _add_property(sym, "Reference", "U", -half_w, half_h + 1.27, prop_id=0)
    _add_property(sym, "Value", target_name, 0, half_h + 1.27, prop_id=1)
    _add_property(sym, "Footprint", footprint_str or "", 0, -(half_h + 2.54), hide=True, prop_id=2)
    _add_property(sym, "Datasheet", datasheet.datasheet_url or "", 0, 0, hide=True, prop_id=3)
    _add_property(sym, "Description", datasheet.description or "", 0, 0, hide=True, prop_id=4)

    # Graphics sub-symbol
    gfx = SExprNode("symbol", [f"{target_name}_0_1"])
    rect = SExprNode("rectangle")
    rect.add_child(SExprNode("start", [_fmt(-half_w), _fmt(half_h)]))
    rect.add_child(SExprNode("end", [_fmt(half_w), _fmt(-half_h)]))
    stroke = SExprNode("stroke")
    stroke.add_child(SExprNode("width", ["0.254"]))
    stroke.add_child(SExprNode("type", ["default"]))
    rect.add_child(stroke)
    fill = SExprNode("fill")
    fill.add_child(SExprNode("type", ["background"]))
    rect.add_child(fill)
    gfx.add_child(rect)
    sym.add_child(gfx)

    # Pin sub-symbol
    pins_sym = SExprNode("symbol", [f"{target_name}_1_1"])

    # Left pins
    for i, pin in enumerate(left_pins):
        y = half_h - 2.54 - i * 2.54
        _add_pin(pins_sym, pin, -half_w - 2.54, y, 0)
        for alt_num in pin.alt_numbers:
            alt_pin = PinInfo(number=alt_num, name=pin.name, pin_type=pin.pin_type)
            _add_pin(pins_sym, alt_pin, -half_w - 2.54, y, 0)

    # Right pins
    for i, pin in enumerate(right_pins):
        y = half_h - 2.54 - i * 2.54
        _add_pin(pins_sym, pin, half_w + 2.54, y, 180)
        for alt_num in pin.alt_numbers:
            alt_pin = PinInfo(number=alt_num, name=pin.name, pin_type=pin.pin_type)
            _add_pin(pins_sym, alt_pin, half_w + 2.54, y, 180)

    # Bottom pins (GND etc.) — stacked at same position for consolidated pins
    for i, pin in enumerate(bottom_pins):
        x = -2.54 * (len(bottom_pins) - 1) / 2 + i * 2.54
        _add_pin(pins_sym, pin, x, -half_h - 2.54, 90)
        for alt_num in pin.alt_numbers:
            alt_pin = PinInfo(number=alt_num, name=pin.name, pin_type=pin.pin_type)
            _add_pin(pins_sym, alt_pin, x, -half_h - 2.54, 90)

    # Hidden pins (thermal pads -> GND) — stacked at GND position, not visible
    for pin in thermal_hidden:
        # Place at same position as first GND bottom pin, or center bottom
        x = 0
        if bottom_pins:
            for i, bp in enumerate(bottom_pins):
                if bp.name.upper() == "GND":
                    x = -2.54 * (len(bottom_pins) - 1) / 2 + i * 2.54
                    break
        _add_hidden_pin(pins_sym, pin, x, -half_h - 2.54, 90)

    sym.add_child(pins_sym)

    return sym


def _add_hidden_pin(parent, pin_info: PinInfo, x, y, angle):
    """Add a hidden pin to a symbol (e.g. thermal pad -> GND)."""
    pin = SExprNode("pin", [pin_info.pin_type, "line"])
    pin.add_child(SExprNode("at", [_fmt(x), _fmt(y), _fmt(angle)]))
    pin.add_child(SExprNode("length", ["0"]))
    pin.add_child(SExprNode("hide", ["yes"]))

    name_node = SExprNode("name", [pin_info.name])
    name_effects = SExprNode("effects")
    name_font = SExprNode("font")
    name_font.add_child(SExprNode("size", ["1.27", "1.27"]))
    name_effects.add_child(name_font)
    name_node.add_child(name_effects)
    pin.add_child(name_node)

    num_node = SExprNode("number", [pin_info.number])
    num_effects = SExprNode("effects")
    num_font = SExprNode("font")
    num_font.add_child(SExprNode("size", ["1.27", "1.27"]))
    num_effects.add_child(num_font)
    num_node.add_child(num_effects)
    pin.add_child(num_node)

    parent.add_child(pin)


def _add_property(sym, name, value, x=0, y=0, hide=False, prop_id=None):
    prop = SExprNode("property", [name, value])
    if prop_id is not None:
        prop.add_child(SExprNode("id", [str(prop_id)]))
    prop.add_child(SExprNode("at", [_fmt(x), _fmt(y), "0"]))
    effects = SExprNode("effects")
    font = SExprNode("font")
    font.add_child(SExprNode("size", ["1.27", "1.27"]))
    effects.add_child(font)
    if hide:
        effects.add_child(SExprNode("hide", ["yes"]))
    prop.add_child(effects)
    sym.add_child(prop)


def _add_pin(parent, pin_info: PinInfo, x, y, angle):
    pin = SExprNode("pin", [pin_info.pin_type, "line"])
    pin.add_child(SExprNode("at", [_fmt(x), _fmt(y), _fmt(angle)]))
    pin.add_child(SExprNode("length", ["2.54"]))

    name_node = SExprNode("name", [pin_info.name])
    name_effects = SExprNode("effects")
    name_font = SExprNode("font")
    name_font.add_child(SExprNode("size", ["1.27", "1.27"]))
    name_effects.add_child(name_font)
    name_node.add_child(name_effects)
    pin.add_child(name_node)

    num_node = SExprNode("number", [pin_info.number])
    num_effects = SExprNode("effects")
    num_font = SExprNode("font")
    num_font.add_child(SExprNode("size", ["1.27", "1.27"]))
    num_effects.add_child(num_font)
    num_node.add_child(num_effects)
    pin.add_child(num_node)

    parent.add_child(pin)
