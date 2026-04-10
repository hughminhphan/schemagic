from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class PinInfo:
    number: str
    name: str
    pin_type: str = "unspecified"  # power_in, power_out, input, output, bidirectional, passive, etc.
    description: str = ""
    alt_numbers: List[str] = field(default_factory=list)  # extra pin numbers consolidated into this pin
    alt_functions: List[str] = field(default_factory=list)  # alternate functions (MCU GPIO muxing, etc.)
    is_hidden: bool = False  # hidden pins (e.g. thermal pad -> GND, not shown on symbol)


@dataclass
class PackageInfo:
    name: str           # Normalized name (e.g. "SOT-23-6")
    pin_count: int
    ti_code: str = ""   # TI-specific code (e.g. "DDC")
    dimensions: str = ""


@dataclass
class DatasheetData:
    part_number: str
    manufacturer: str = ""
    description: str = ""
    component_type: str = ""  # "voltage_regulator", "op_amp", etc.
    package: Optional[PackageInfo] = None
    pins: List[PinInfo] = field(default_factory=list)
    datasheet_url: str = ""
    pdf_path: str = ""
    confidence: float = 0.0  # 0-1, how confident the extraction was


@dataclass
class MatchResult:
    symbol_lib: str = ""       # e.g. "Regulator_Switching"
    symbol_name: str = ""      # e.g. "TPS54302"
    footprint_lib: str = ""    # e.g. "Package_TO_SOT_SMD"
    footprint_name: str = ""   # e.g. "SOT-23-6"
    symbol_score: float = 0.0
    footprint_score: float = 0.0
    pin_mapping: Dict[str, str] = field(default_factory=dict)  # datasheet pin# → symbol pin#


@dataclass
class GeneratedComponent:
    symbol_lib_path: str = ""
    footprint_lib_path: str = ""
    symbol_name: str = ""
    footprint_name: str = ""
    model_ref: str = ""             # 3D model path from (model ...) node, e.g. "Package_SO.3dshapes/SOIC-8.wrl"
    model_ref_inferred: bool = False  # True if model ref was injected by inference, not from source footprint
