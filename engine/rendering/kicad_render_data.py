"""Plain dataclasses for KiCad visual rendering data.

No Pydantic, no wx -- pure data containers that work in Python 3.7+.
Used by both the plugin UI (wx panels) and the webapp API (converted to Pydantic).
"""

from dataclasses import dataclass, field


@dataclass
class BoundingBox:
    x = 0.0
    y = 0.0
    w = 10.0
    h = 10.0

    def __init__(self, x=0.0, y=0.0, w=10.0, h=10.0):
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = float(h)


@dataclass
class GraphicItem:
    type = ""
    layer = ""
    start = None       # [x, y] or None
    end = None         # [x, y] or None
    mid = None         # [x, y] or None (arcs only)
    pts = None         # [[x,y], ...] or None (polylines/polygons)
    center = None      # [x, y] or None (circles)
    radius = 0.0
    at = None          # [x, y] or None (text)
    angle = 0.0
    text = ""
    stroke_width = 0.0
    fill = "none"
    font_size = 0.0
    unit = 0           # 0 = shared across all units

    def __init__(self, type="", layer="", start=None, end=None, mid=None,
                 pts=None, center=None, radius=0.0, at=None, angle=0.0,
                 text="", stroke_width=0.0, fill="none", font_size=0.0, unit=0):
        self.type = type
        self.layer = layer
        self.start = start
        self.end = end
        self.mid = mid
        self.pts = pts or []
        self.center = center
        self.radius = float(radius)
        self.at = at
        self.angle = float(angle)
        self.text = text
        self.stroke_width = float(stroke_width)
        self.fill = fill
        self.font_size = float(font_size)
        self.unit = int(unit)


@dataclass
class SymbolPin:
    number = ""
    name = ""
    pin_type = "unspecified"
    shape = "line"
    at = None          # [x, y]
    angle = 0.0
    length = 2.54
    unit = 0           # 0 = shared across all units

    def __init__(self, number="", name="", pin_type="unspecified", shape="line",
                 at=None, angle=0.0, length=2.54, unit=0):
        self.number = number
        self.name = name
        self.pin_type = pin_type
        self.shape = shape
        self.at = at or [0.0, 0.0]
        self.angle = float(angle)
        self.length = float(length)
        self.unit = int(unit)


@dataclass
class FootprintPad:
    number = ""
    shape = "rect"
    at = None          # [x, y]
    size = None        # [w, h]
    angle = 0.0
    roundrect_rratio = 0.0
    pad_type = "smd"   # smd, thru_hole, np_thru_hole, connect
    drill = None       # [diameter] or [width, height] for oval drill

    def __init__(self, number="", shape="rect", at=None, size=None,
                 angle=0.0, roundrect_rratio=0.0, pad_type="smd", drill=None):
        self.number = number
        self.shape = shape
        self.at = at or [0.0, 0.0]
        self.size = size or [1.0, 1.0]
        self.angle = float(angle)
        self.roundrect_rratio = float(roundrect_rratio)
        self.pad_type = pad_type
        self.drill = drill or []


@dataclass
class RenderPayload:
    kind = "symbol"
    found = False
    bounding_box = None   # BoundingBox or None
    graphics = None       # list of GraphicItem
    pins = None           # list of SymbolPin (symbols only)
    pads = None           # list of FootprintPad (footprints only)
    unit_count = 1
    pin_names_offset = 0.508
    pin_names_hide = False
    pin_numbers_hide = False

    def __init__(self, kind="symbol", found=False, bounding_box=None,
                 graphics=None, pins=None, pads=None,
                 unit_count=1, pin_names_offset=0.508,
                 pin_names_hide=False, pin_numbers_hide=False):
        self.kind = kind
        self.found = found
        self.bounding_box = bounding_box
        self.graphics = graphics or []
        self.pins = pins or []
        self.pads = pads or []
        self.unit_count = int(unit_count)
        self.pin_names_offset = float(pin_names_offset)
        self.pin_names_hide = bool(pin_names_hide)
        self.pin_numbers_hide = bool(pin_numbers_hide)
