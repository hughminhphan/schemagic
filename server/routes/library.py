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
from engine.rendering.kicad_lib_parser import parse_symbol_file, parse_footprint_file

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
            start=g.start or [], end=g.end or [], mid=g.mid or [],
            pts=g.pts or [], center=g.center or [], radius=g.radius or 0.0,
            at=g.at or [], angle=g.angle or 0.0, text=g.text or "",
            stroke_width=g.stroke_width or 0.0, fill=g.fill or "",
            font_size=g.font_size or 0.0, unit=g.unit or 0,
        ))

    pins = []
    for p in rp.pins:
        pins.append(SymbolPin(
            number=p.number, name=p.name, pin_type=p.pin_type,
            shape=p.shape, at=p.at, angle=p.angle, length=p.length,
            unit=p.unit or 0,
        ))

    pads = []
    for p in rp.pads:
        pads.append(FootprintPad(
            number=p.number, shape=p.shape, at=p.at,
            size=p.size, angle=p.angle, roundrect_rratio=p.roundrect_rratio,
            pad_type=p.pad_type or "smd", drill=p.drill or [],
        ))

    return LibraryItemPayload(
        kind=rp.kind, found=rp.found, bounding_box=bbox,
        graphics=graphics, pins=pins, pads=pads,
        unit_count=rp.unit_count,
        pin_names_offset=rp.pin_names_offset,
        pin_names_hide=rp.pin_names_hide,
        pin_numbers_hide=rp.pin_numbers_hide,
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
