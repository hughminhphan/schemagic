"""Parse KiCad .kicad_sym / .kicad_mod files into RenderPayload for visual rendering.

Shared between the plugin UI (wxPython panels) and the webapp API.
No Pydantic, no wx, no FastAPI -- only stdlib + generation.sexpr.
"""

import math
import os

from .kicad_render_data import (
    BoundingBox, FootprintPad, GraphicItem, RenderPayload, SymbolPin,
)

# Lazy import to avoid circular deps at module level
_sexpr = None


def _get_sexpr():
    global _sexpr
    if _sexpr is None:
        from engine.generation import sexpr as _mod
        _sexpr = _mod
    return _sexpr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _extract_at(node):
    """Extract (at x y [angle]) from a node."""
    at = node.find_child("at")
    if not at:
        return [0.0, 0.0], 0.0
    x = _float(at.get_value(0))
    y = _float(at.get_value(1))
    angle = _float(at.get_value(2))
    return [x, y], angle


def _extract_stroke(node):
    stroke = node.find_child("stroke")
    if not stroke:
        return 0.0
    width = stroke.find_child("width")
    if width:
        return _float(width.get_value(0))
    return 0.0


def _extract_fill(node):
    fill = node.find_child("fill")
    if not fill:
        return "none"
    ftype = fill.find_child("type")
    if ftype:
        return ftype.get_value(0) or "none"
    return "none"


def _extract_graphic(node, layer=""):
    """Convert a KiCad graphic S-expr node to a GraphicItem."""
    tag = node.tag
    g = GraphicItem(type=tag, layer=layer)

    if tag == "rectangle":
        start = node.find_child("start")
        end = node.find_child("end")
        if start:
            g.start = [_float(start.get_value(0)), _float(start.get_value(1))]
        if end:
            g.end = [_float(end.get_value(0)), _float(end.get_value(1))]

    elif tag == "polyline":
        pts_node = node.find_child("pts")
        if pts_node:
            g.pts = [
                [_float(xy.get_value(0)), _float(xy.get_value(1))]
                for xy in pts_node.find_all("xy")
            ]

    elif tag == "arc":
        for fname in ("start", "mid", "end"):
            child = node.find_child(fname)
            if child:
                setattr(g, fname, [_float(child.get_value(0)), _float(child.get_value(1))])

    elif tag == "circle":
        center = node.find_child("center")
        radius_node = node.find_child("radius")
        if center:
            g.center = [_float(center.get_value(0)), _float(center.get_value(1))]
        if radius_node:
            g.radius = _float(radius_node.get_value(0))
        elif center:
            end = node.find_child("end")
            if end:
                ex, ey = _float(end.get_value(0)), _float(end.get_value(1))
                cx, cy = g.center
                g.radius = math.sqrt((ex - cx) ** 2 + (ey - cy) ** 2)

    elif tag == "text":
        g.text = node.get_value(0) or ""
        pos, angle = _extract_at(node)
        g.at = pos
        g.angle = angle

    # Footprint-specific graphic types
    elif tag == "fp_line":
        start = node.find_child("start")
        end = node.find_child("end")
        if start:
            g.start = [_float(start.get_value(0)), _float(start.get_value(1))]
        if end:
            g.end = [_float(end.get_value(0)), _float(end.get_value(1))]
        g.type = "line"
        layer_node = node.find_child("layer")
        if layer_node:
            g.layer = layer_node.get_value(0) or ""

    elif tag == "fp_arc":
        for fname in ("start", "mid", "end"):
            child = node.find_child(fname)
            if child:
                setattr(g, fname, [_float(child.get_value(0)), _float(child.get_value(1))])
        g.type = "arc"
        layer_node = node.find_child("layer")
        if layer_node:
            g.layer = layer_node.get_value(0) or ""

    elif tag == "fp_circle":
        center = node.find_child("center")
        end = node.find_child("end")
        if center:
            g.center = [_float(center.get_value(0)), _float(center.get_value(1))]
        if center and end:
            ex, ey = _float(end.get_value(0)), _float(end.get_value(1))
            cx, cy = g.center
            g.radius = math.sqrt((ex - cx) ** 2 + (ey - cy) ** 2)
        g.type = "circle"
        layer_node = node.find_child("layer")
        if layer_node:
            g.layer = layer_node.get_value(0) or ""

    elif tag == "fp_poly":
        pts_node = node.find_child("pts")
        if pts_node:
            g.pts = [
                [_float(xy.get_value(0)), _float(xy.get_value(1))]
                for xy in pts_node.find_all("xy")
            ]
        g.type = "poly"
        layer_node = node.find_child("layer")
        if layer_node:
            g.layer = layer_node.get_value(0) or ""

    elif tag == "fp_text":
        g.text = node.get_value(1) or node.get_value(0) or ""
        pos, angle = _extract_at(node)
        g.at = pos
        g.angle = angle
        g.type = "text"
        layer_node = node.find_child("layer")
        if layer_node:
            g.layer = layer_node.get_value(0) or ""

    g.stroke_width = _extract_stroke(node)
    if not g.fill or g.fill == "none":
        g.fill = _extract_fill(node)

    return g


def _resolve_extends(root, sym):
    """Resolve an extends symbol by merging parent graphics."""
    extends_node = sym.find_child("extends")
    if not extends_node:
        return sym

    parent_name = extends_node.get_value(0)
    parent = None
    for s in root.find_all("symbol"):
        if s.get_value(0) == parent_name:
            parent = s
            break

    if not parent:
        return sym

    resolved = parent.clone()
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

    ext = resolved.find_child("extends")
    if ext:
        resolved.remove_child(ext)

    resolved.set_value(0, sym.get_value(0))
    return resolved


def _collect_points(g, points):
    """Collect coordinate points from a GraphicItem for bounding box computation."""
    if g.start:
        points.append(tuple(g.start))
    if g.end:
        points.append(tuple(g.end))
    if g.mid:
        points.append(tuple(g.mid))
    if g.center and g.radius:
        cx, cy = g.center
        r = g.radius
        points.append((cx - r, cy - r))
        points.append((cx + r, cy + r))
    for pt in (g.pts or []):
        points.append(tuple(pt))
    if g.at:
        points.append(tuple(g.at))


def _compute_bbox(points):
    """Compute a bounding box with 15% padding from a list of (x, y) points."""
    if not points:
        return BoundingBox(x=0, y=0, w=10, h=10)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    w = max_x - min_x
    h = max_y - min_y

    pad_x = max(w * 0.15, 2.0)
    pad_y = max(h * 0.15, 2.0)

    return BoundingBox(
        x=min_x - pad_x,
        y=min_y - pad_y,
        w=w + 2 * pad_x,
        h=h + 2 * pad_y,
    )


# ---------------------------------------------------------------------------
# Symbol parsing
# ---------------------------------------------------------------------------

def _parse_symbol(root, symbol_name):
    """Extract rendering data from a parsed .kicad_sym root node."""
    sym = None
    for s in root.find_all("symbol"):
        if s.get_value(0) == symbol_name:
            sym = s
            break

    if not sym:
        return None

    sym = _resolve_extends(root, sym)

    graphics = []
    pins = []
    all_points = []

    for child in sym.find_all("symbol"):
        for tag in ("rectangle", "polyline", "arc", "circle", "text"):
            for node in child.find_all(tag):
                g = _extract_graphic(node)
                graphics.append(g)
                _collect_points(g, all_points)

        for pin_node in child.find_all("pin"):
            pin_type = pin_node.get_value(0) or "unspecified"
            pin_shape = pin_node.get_value(1) or "line"
            pos, angle = _extract_at(pin_node)
            length_node = pin_node.find_child("length")
            length = _float(length_node.get_value(0)) if length_node else 2.54

            name_node = pin_node.find_child("name")
            number_node = pin_node.find_child("number")
            name = name_node.get_value(0) if name_node else ""
            number = number_node.get_value(0) if number_node else ""

            pins.append(SymbolPin(
                number=number, name=name, pin_type=pin_type, shape=pin_shape,
                at=pos, angle=angle, length=length,
            ))

            angle_rad = math.radians(angle)
            tip_x = pos[0] + length * math.cos(angle_rad)
            tip_y = pos[1] + length * math.sin(angle_rad)
            all_points.append((pos[0], pos[1]))
            all_points.append((tip_x, tip_y))

    # Also check for graphics/pins directly on the symbol
    for tag in ("rectangle", "polyline", "arc", "circle", "text"):
        for node in sym.find_all(tag):
            g = _extract_graphic(node)
            graphics.append(g)
            _collect_points(g, all_points)

    for pin_node in sym.find_all("pin"):
        pin_type = pin_node.get_value(0) or "unspecified"
        pin_shape = pin_node.get_value(1) or "line"
        pos, angle = _extract_at(pin_node)
        length_node = pin_node.find_child("length")
        length = _float(length_node.get_value(0)) if length_node else 2.54

        name_node = pin_node.find_child("name")
        number_node = pin_node.find_child("number")
        name = name_node.get_value(0) if name_node else ""
        number = number_node.get_value(0) if number_node else ""

        if not any(p.number == number for p in pins):
            pins.append(SymbolPin(
                number=number, name=name, pin_type=pin_type, shape=pin_shape,
                at=pos, angle=angle, length=length,
            ))
            angle_rad = math.radians(angle)
            tip_x = pos[0] + length * math.cos(angle_rad)
            tip_y = pos[1] + length * math.sin(angle_rad)
            all_points.append((pos[0], pos[1]))
            all_points.append((tip_x, tip_y))

    bbox = _compute_bbox(all_points)

    return RenderPayload(
        kind="symbol", found=True, bounding_box=bbox,
        graphics=graphics, pins=pins,
    )


# ---------------------------------------------------------------------------
# Footprint parsing
# ---------------------------------------------------------------------------

_RENDER_LAYERS = {"F.SilkS", "F.CrtYd", "F.Fab", "B.SilkS", "B.CrtYd", "B.Fab"}


def _parse_footprint(fp_node):
    """Extract rendering data from a parsed .kicad_mod footprint node."""
    graphics = []
    pads = []
    all_points = []

    for child in fp_node.children:
        tag = child.tag

        if tag in ("fp_line", "fp_arc", "fp_circle", "fp_poly", "fp_text"):
            layer_node = child.find_child("layer")
            layer = layer_node.get_value(0) if layer_node else ""

            if tag == "fp_text" or layer in _RENDER_LAYERS:
                g = _extract_graphic(child, layer)
                graphics.append(g)
                _collect_points(g, all_points)

        elif tag == "pad":
            number = child.get_value(0) or ""
            shape = child.get_value(2) or "rect"

            pos, angle = _extract_at(child)
            size_node = child.find_child("size")
            size = [
                _float(size_node.get_value(0)) if size_node else 1.0,
                _float(size_node.get_value(1)) if size_node else 1.0,
            ]

            rratio = 0.0
            rr_node = child.find_child("roundrect_rratio")
            if rr_node:
                rratio = _float(rr_node.get_value(0))

            pads.append(FootprintPad(
                number=number, shape=shape, at=pos, size=size,
                angle=angle, roundrect_rratio=rratio,
            ))

            hw, hh = size[0] / 2, size[1] / 2
            all_points.append((pos[0] - hw, pos[1] - hh))
            all_points.append((pos[0] + hw, pos[1] + hh))

    bbox = _compute_bbox(all_points)

    return RenderPayload(
        kind="footprint", found=True, bounding_box=bbox,
        graphics=graphics, pads=pads,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_symbol_file(lib_path, symbol_name):
    """Parse a .kicad_sym file and return RenderPayload for a symbol.

    Returns RenderPayload with found=False if the symbol is not found.
    """
    sexpr = _get_sexpr()
    if not os.path.isfile(lib_path):
        return RenderPayload(kind="symbol", found=False)

    try:
        nodes = sexpr.parse_file(lib_path)
    except Exception:
        return RenderPayload(kind="symbol", found=False)

    if not nodes:
        return RenderPayload(kind="symbol", found=False)

    result = _parse_symbol(nodes[0], symbol_name)
    return result or RenderPayload(kind="symbol", found=False)


def parse_footprint_file(fp_path):
    """Parse a .kicad_mod file and return RenderPayload for a footprint.

    Returns RenderPayload with found=False if the file cannot be read.
    """
    sexpr = _get_sexpr()
    if not os.path.isfile(fp_path):
        return RenderPayload(kind="footprint", found=False)

    try:
        nodes = sexpr.parse_file(fp_path)
    except Exception:
        return RenderPayload(kind="footprint", found=False)

    if not nodes:
        return RenderPayload(kind="footprint", found=False)

    return _parse_footprint(nodes[0])


# ---------------------------------------------------------------------------
# Synthetic symbol generation (port of generate-synthetic-symbol.ts)
# ---------------------------------------------------------------------------

PIN_SPACING = 2.54   # KiCad standard 100mil grid
PIN_LENGTH = 2.54


def _assign_side(pin_type):
    """Assign a pin to a symbol side based on its type."""
    if pin_type == "power_in":
        return "top"
    elif pin_type == "power_out":
        return "bottom"
    elif pin_type == "input":
        return "left"
    elif pin_type in ("output", "open_collector", "open_emitter"):
        return "right"
    elif pin_type == "no_connect":
        return "bottom"
    else:
        return "left"


def _consolidate_pins(pins):
    """Merge same-name pins into a single pin with alt_numbers."""
    by_name = {}
    result = []

    for pin in pins:
        key = pin.name.upper()
        if key in by_name:
            by_name[key].append(pin)
        else:
            by_name[key] = [pin]

    for group in by_name.values():
        primary = group[0]
        # Build a new dict-like object with merged alt_numbers
        alts = list(getattr(primary, "alt_numbers", None) or [])
        for i in range(1, len(group)):
            alts.append(group[i].number)
            alts.extend(getattr(group[i], "alt_numbers", None) or [])
        result.append({
            "number": primary.number,
            "name": primary.name,
            "pin_type": getattr(primary, "pin_type", "unspecified"),
            "alt_numbers": alts,
        })

    return result


def generate_synthetic_symbol(pins):
    """Generate a synthetic KiCad-style symbol from a list of PinInfo objects.

    Used when no existing KiCad library match is found.
    Accepts any objects with .number, .name, .pin_type attributes.
    Returns a RenderPayload.
    """
    if not pins:
        return RenderPayload(kind="symbol", found=False)

    consolidated = _consolidate_pins(pins)

    sides = {"left": [], "right": [], "top": [], "bottom": []}
    for pin in consolidated:
        side = _assign_side(pin["pin_type"])
        sides[side].append(pin)

    # Balance left/right if heavily skewed
    if sides["left"] and not sides["right"]:
        mid = (len(sides["left"]) + 1) // 2
        sides["right"] = sides["left"][mid:]
        sides["left"] = sides["left"][:mid]
    elif sides["right"] and not sides["left"]:
        mid = (len(sides["right"]) + 1) // 2
        sides["left"] = sides["right"][mid:]
        sides["right"] = sides["right"][:mid]

    # If all pins are top/bottom, redistribute to left/right
    total_lr = len(sides["left"]) + len(sides["right"])
    if total_lr == 0 and (len(sides["top"]) + len(sides["bottom"])) > 0:
        all_pins = sides["top"] + sides["bottom"]
        sides["top"] = []
        sides["bottom"] = []
        mid = (len(all_pins) + 1) // 2
        sides["left"] = all_pins[:mid]
        sides["right"] = all_pins[mid:]

    max_vertical = max(len(sides["left"]), len(sides["right"]), 1)
    max_horizontal = max(len(sides["top"]), len(sides["bottom"]), 1)

    body_h = max_vertical * PIN_SPACING
    body_w = max(max_horizontal * PIN_SPACING, 10.16)

    half_w = body_w / 2.0
    half_h = body_h / 2.0

    # Body rectangle
    graphics = [GraphicItem(
        type="rectangle",
        start=[-half_w, half_h],
        end=[half_w, -half_h],
        fill="background",
        stroke_width=0.254,
    )]

    symbol_pins = []

    # Left side: angle 180 (pin extends left from body edge)
    for i, pin in enumerate(sides["left"]):
        count = len(sides["left"])
        y = half_h - (i + 0.5) * (body_h / count)
        symbol_pins.append(SymbolPin(
            number=pin["number"], name=pin["name"], pin_type=pin["pin_type"],
            shape="line", at=[-half_w, y], angle=180, length=PIN_LENGTH,
        ))

    # Right side: angle 0
    for i, pin in enumerate(sides["right"]):
        count = len(sides["right"])
        y = half_h - (i + 0.5) * (body_h / count)
        symbol_pins.append(SymbolPin(
            number=pin["number"], name=pin["name"], pin_type=pin["pin_type"],
            shape="line", at=[half_w, y], angle=0, length=PIN_LENGTH,
        ))

    # Top side: angle 90
    for i, pin in enumerate(sides["top"]):
        count = len(sides["top"])
        x = -half_w + (i + 0.5) * (body_w / count)
        symbol_pins.append(SymbolPin(
            number=pin["number"], name=pin["name"], pin_type=pin["pin_type"],
            shape="line", at=[x, half_h], angle=90, length=PIN_LENGTH,
        ))

    # Bottom side: angle 270
    for i, pin in enumerate(sides["bottom"]):
        count = len(sides["bottom"])
        x = -half_w + (i + 0.5) * (body_w / count)
        symbol_pins.append(SymbolPin(
            number=pin["number"], name=pin["name"], pin_type=pin["pin_type"],
            shape="line", at=[x, -half_h], angle=270, length=PIN_LENGTH,
        ))

    # Bounding box with padding for pin lengths and labels
    pad = PIN_LENGTH + 5
    bbox = BoundingBox(
        x=-half_w - pad, y=-half_h - pad,
        w=body_w + 2 * pad, h=body_h + 2 * pad,
    )

    return RenderPayload(
        kind="symbol", found=False, bounding_box=bbox,
        graphics=graphics, pins=symbol_pins,
    )
