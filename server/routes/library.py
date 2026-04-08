"""API route for serving parsed KiCad library items for rendering.

Delegates to ui.kicad_lib_parser for the actual parsing, then converts
plain dataclass results to Pydantic models for the API response.
"""

import os

from fastapi import APIRouter, Query

from server.schemas import (
    BoundingBox, FootprintPad, GraphicItem, LibraryItemPayload, SymbolPin,
)
from engine.core.config import FOOTPRINT_DIR, SYMBOL_DIR
from plugin.ui.kicad_lib_parser import parse_symbol_file, parse_footprint_file

router = APIRouter()


def _to_pydantic_payload(rp):
    """Convert a RenderPayload dataclass to a Pydantic LibraryItemPayload."""
    bbox = None
    if rp.bounding_box:
        bbox = BoundingBox(
            x=rp.bounding_box.x, y=rp.bounding_box.y,
            w=rp.bounding_box.w, h=rp.bounding_box.h,
        )

    graphics = []
    for g in rp.graphics:
        graphics.append(GraphicItem(
            type=g.type, layer=g.layer,
            start=g.start, end=g.end, mid=g.mid,
            pts=g.pts, center=g.center, radius=g.radius,
            at=g.at, angle=g.angle, text=g.text,
            stroke_width=g.stroke_width, fill=g.fill,
        ))

    pins = []
    for p in rp.pins:
        pins.append(SymbolPin(
            number=p.number, name=p.name, pin_type=p.pin_type,
            shape=p.shape, at=p.at, angle=p.angle, length=p.length,
        ))

    pads = []
    for p in rp.pads:
        pads.append(FootprintPad(
            number=p.number, shape=p.shape, at=p.at,
            size=p.size, angle=p.angle, roundrect_rratio=p.roundrect_rratio,
        ))

    return LibraryItemPayload(
        kind=rp.kind, found=rp.found, bounding_box=bbox,
        graphics=graphics, pins=pins, pads=pads,
    )


@router.get("/library-item")
def get_library_item(
    kind: str = Query(..., pattern="^(symbol|footprint)$"),
    lib: str = Query(...),
    name: str = Query(...),
):
    """Return parsed rendering data for a KiCad symbol or footprint."""
    if kind == "symbol":
        if not SYMBOL_DIR:
            return LibraryItemPayload(kind="symbol", found=False)

        lib_path = os.path.join(SYMBOL_DIR, "%s.kicad_sym" % lib)
        rp = parse_symbol_file(lib_path, name)
        return _to_pydantic_payload(rp)

    else:  # footprint
        if not FOOTPRINT_DIR:
            return LibraryItemPayload(kind="footprint", found=False)

        fp_path = os.path.join(FOOTPRINT_DIR, "%s.pretty" % lib, "%s.kicad_mod" % name)
        rp = parse_footprint_file(fp_path)
        return _to_pydantic_payload(rp)
