from pydantic import BaseModel


class PinInfoSchema(BaseModel):
    number: str
    name: str
    pin_type: str = "unspecified"
    description: str = ""
    alt_numbers: list[str] = []
    is_hidden: bool = False


class PackageInfoSchema(BaseModel):
    name: str
    pin_count: int
    ti_code: str = ""
    dimensions: str = ""


class MatchResultSchema(BaseModel):
    symbol_lib: str = ""
    symbol_name: str = ""
    footprint_lib: str = ""
    footprint_name: str = ""
    symbol_score: float = 0.0
    footprint_score: float = 0.0
    pin_mapping: dict[str, str] = {}


class DatasheetSummarySchema(BaseModel):
    part_number: str
    manufacturer: str = ""
    description: str = ""
    component_type: str = ""
    package: PackageInfoSchema | None = None
    datasheet_url: str = ""
    confidence: float = 0.0
    pins: list[PinInfoSchema] = []


class RunRequest(BaseModel):
    part_number: str


class RunResponse(BaseModel):
    job_id: str


class SelectPackageRequest(BaseModel):
    job_id: str
    package: PackageInfoSchema


class SelectPackageResponse(BaseModel):
    datasheet: DatasheetSummarySchema
    match: MatchResultSchema
    pins: list[PinInfoSchema]


class FinalizeRequest(BaseModel):
    job_id: str
    pins: list[PinInfoSchema]
    project_dir: str | None = None  # KiCad project dir for direct import


class FileInfo(BaseModel):
    filename: str
    size_bytes: int


class ModelInfo(BaseModel):
    ref: str = ""                # e.g. "Package_SO.3dshapes/SOIC-8.wrl"
    inferred: bool = False       # True if injected by naming convention, not from source footprint


class FinalizeResponse(BaseModel):
    job_id: str
    files: list[FileInfo]
    model: ModelInfo | None = None
    imported: bool = False  # True if saved directly to a KiCad project


# --- Library item rendering payload ---

class GraphicItem(BaseModel):
    type: str  # rectangle, polyline, arc, circle, line, poly, text, bezier
    layer: str = ""
    start: list[float] = []
    end: list[float] = []
    mid: list[float] = []
    pts: list[list[float]] = []
    center: list[float] = []
    radius: float = 0.0
    at: list[float] = []
    angle: float = 0.0
    text: str = ""
    stroke_width: float = 0.0
    fill: str = ""  # none, outline, background
    font_size: float = 0.0
    unit: int = 0


class SymbolPin(BaseModel):
    number: str
    name: str
    pin_type: str
    shape: str = "line"
    at: list[float]
    angle: float
    length: float
    unit: int = 0


class FootprintPad(BaseModel):
    number: str
    shape: str  # rect, roundrect, oval, circle, custom
    at: list[float]
    size: list[float]
    angle: float = 0.0
    roundrect_rratio: float = 0.0
    pad_type: str = "smd"
    drill: list[float] = []


class BoundingBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class LibraryItemPayload(BaseModel):
    kind: str  # symbol or footprint
    found: bool
    bounding_box: BoundingBox | None = None
    graphics: list[GraphicItem] = []
    pins: list[SymbolPin] = []
    pads: list[FootprintPad] = []
    unit_count: int = 1
    pin_names_offset: float = 0.508
    pin_names_hide: bool = False
    pin_numbers_hide: bool = False
