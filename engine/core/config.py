import os
import sys


PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PLUGIN_DIR, "cache")

# KiCad library search paths (platform-dependent)
_KICAD_LIB_SEARCH = [
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport",
    "/usr/share/kicad",
    "/usr/local/share/kicad",
    r"C:\Program Files\KiCad\share\kicad",
    r"C:\Program Files\KiCad\8.0\share\kicad",
]


def find_kicad_share():
    """Find the KiCad shared-support directory containing symbols/ and footprints/."""
    for var in ("KICAD8_SYMBOL_DIR", "KICAD_SYMBOL_DIR"):
        path = os.environ.get(var)
        if path and os.path.isdir(path):
            return os.path.dirname(path)
    for path in _KICAD_LIB_SEARCH:
        if os.path.isdir(os.path.join(path, "symbols")):
            return path
    return None


KICAD_SHARE = find_kicad_share()
SYMBOL_DIR = os.path.join(KICAD_SHARE, "symbols") if KICAD_SHARE else None
FOOTPRINT_DIR = os.path.join(KICAD_SHARE, "footprints") if KICAD_SHARE else None
MODEL_DIR = os.path.join(KICAD_SHARE, "3dmodels") if KICAD_SHARE else None

# Index cache file
INDEX_CACHE = os.path.join(CACHE_DIR, "library_index.json")

# TI package-suffix stripping
TI_SUFFIXES = [
    "DDCR", "DDC", "DDWR", "DDW", "DRCR", "DRC", "DGKR", "DGK",
    "RGER", "RGE", "RGTR", "RGT", "RGYR", "RGY", "PWPR", "PWP", "PWR", "PW",
    "DSGR", "DSG", "DCKR", "DCK", "DBVR", "DBV", "QDRR", "QDR",
    "RSAR", "RSA", "DGSR", "DGS", "RTER", "RTE", "YZFR", "YZF",
    "YFFR", "YFF", "RHAR", "RHA", "RHBR", "RHB", "DADR", "DAD",
    "DGNR", "DGN", "DLHR", "DLH", "DSCR", "DSC", "DWKR", "DWK",
    "DGQR", "DGQ", "DRBR", "DRB", "DRLR", "DRL",
    # DRV = WSON-6, DRVR = WSON-6 + reel (very common for TPS7Exx, TPS6xx)
    "DRVR", "DRV",
    # DDA = SOIC/PowerPAD (very common, was missing)
    "DDAR", "DDA",
    # ID = SOIC-8 (standard), IDGS = VSSOP-10, used by INA series
    "IDGSR", "IDGS", "IDR", "ID",
    # MFX = SOT-23-5 (used by LP59xx family)
    "MFXR", "MFX",
    # PDRL = SOT-563 (used by TPS629xx)
    "PDRLR", "PDRL",
    # Single-letter TI package codes (MUST come last — shortest match)
    "DR", "D",
]


def strip_ti_suffix(part_number):
    """Strip TI package/reel suffixes to get base part number.

    Returns (base_part_number, package_code_or_None).
    The package code has any trailing reel "R" stripped (e.g. "RGYR" → "RGY").
    Automotive qualifiers (-Q1, -Q2, etc.) are stripped before matching.
    """
    import re
    pn = part_number.upper().strip()
    # Strip automotive/qualifier suffixes and voltage suffixes before matching
    pn_clean = re.sub(r'-Q\d+$', '', pn)
    pn_clean = re.sub(r'-\d+\.?\d*$', '', pn_clean)  # e.g. -1.2, -3.3, -5, -12
    for suffix in TI_SUFFIXES:
        if pn_clean.endswith(suffix):
            base = pn_clean[:-len(suffix)]
            # Strip trailing reel "R" to get package code
            code = suffix.rstrip("R") if len(suffix) > 1 and suffix.endswith("R") else suffix
            return (base, code)
    return (pn_clean, None)


# TI package code to KiCad footprint mapping
PACKAGE_MAP = {
    "DDC": "Package_TO_SOT_SMD:SOT-23-6",
    "DCK": "Package_TO_SOT_SMD:SOT-353_SC-70-5",
    "DBV": "Package_TO_SOT_SMD:SOT-23-5",
    "DGK": "Package_DFN_QFN:TSSOP-8_4.4x3mm_P0.65mm",
    "DRC": "Package_SON:Texas_DRC0010J",
    "DRV": "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
    "DGN": "Package_SO:HVSSOP-8-1EP_3x3mm_P0.65mm_EP1.57x1.89mm",
    "DSG": "Package_TO_SOT_SMD:SOT-23-5",
    "PW": "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
    "PWP": "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm",
    "DDW": "Package_SO:HTSSOP-44-1EP_6.1x14mm_P0.635mm_EP5.2x14mm_Mask4.31x8.26mm",
    "DAD": "Package_SO:HTSSOP-32-1EP_6.1x11mm_P0.65mm_EP5.2x11mm_Mask4.11x4.36mm",
    "RGE": "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
    "RGT": "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm",
    "RTE": "Package_DFN_QFN:Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm",
    "RSA": "Package_DFN_QFN:QFN-40-1EP_5x5mm_P0.4mm_EP3.1x3.1mm",
    "QDR": "Package_SON:WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
    "DRB": "Package_SON:Texas_DRB0008A_VSON-8-1EP_3x3mm_P0.65mm",
    "DRL": "Package_TO_SOT_SMD:SOT-5X3",
    "D": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "YZF": "Package_BGA:BGA-9_1.587x1.587mm_P0.5mm",
    "YFF": "Package_BGA:BGA-4_0.8x0.8mm_P0.4mm",
    # SOT-23 family
    "SOT-23-3": "Package_TO_SOT_SMD:SOT-23",
    "SOT-23-5": "Package_TO_SOT_SMD:SOT-23-5",
    "SOT-23-6": "Package_TO_SOT_SMD:SOT-23-6",
    "SOT-23-8": "Package_TO_SOT_SMD:SOT-23-8",
    # SOIC (ID suffix = SOIC-8 in TI's naming)
    "ID": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "IDGS": "Package_SO:VSSOP-10_3x3mm_P0.5mm",
    "DDA": "Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm",
    "MFX": "Package_TO_SOT_SMD:SOT-23-5",
    "SOIC-8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "SOIC-14": "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    "SOIC-16": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
    # TSSOP
    "TSSOP-8": "Package_SO:TSSOP-8_4.4x3mm_P0.65mm",
    "TSSOP-14": "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    "TSSOP-16": "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
    "TSSOP-20": "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
    # QFN
    "QFN-16": "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm",
    "QFN-20": "Package_DFN_QFN:QFN-20-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
    "QFN-24": "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
    "QFN-32": "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm",
    # VQFN (TI rectangular)
    "RGY": "Package_DFN_QFN:Texas_RGY_R-PVQFN-N24_EP2.05x3.1mm",
    "RHA": "Package_DFN_QFN:QFN-40-1EP_5x5mm_P0.4mm_EP3.1x3.1mm",
    "VQFN-24": "Package_DFN_QFN:Texas_RGY_R-PVQFN-N24_EP2.05x3.1mm",
    "VQFN-32": "Package_DFN_QFN:VQFN-32-1EP_5x5mm_P0.5mm_EP3.5x3.5mm",
    "VQFN-40": "Package_DFN_QFN:QFN-40-1EP_5x5mm_P0.4mm_EP3.1x3.1mm",
    # HTSSOP
    "HTSSOP-16": "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm",
    "HTSSOP-20": "Package_SO:HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP3.4x6.5mm",
    "HTSSOP-24": "Package_SO:HTSSOP-24-1EP_4.4x7.8mm_P0.65mm_EP3.2x5mm",
    "HTSSOP-28": "Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm",
    "HTSSOP-32": "Package_SO:HTSSOP-32-1EP_6.1x11mm_P0.65mm_EP5.2x11mm_Mask4.11x4.36mm",
    "HTSSOP-38": "Package_SO:HTSSOP-38-1EP_6.1x12.5mm_P0.65mm_EP5.2x12.5mm_Mask3.39x6.35mm",
    "HTSSOP-44": "Package_SO:HTSSOP-44-1EP_6.1x14mm_P0.635mm_EP5.2x14mm_Mask4.31x8.26mm",
    # HVSSOP
    "HVSSOP-8": "Package_SO:HVSSOP-8-1EP_3x3mm_P0.65mm_EP1.57x1.89mm",
    "HVSSOP-10": "Package_SO:HVSSOP-10-1EP_3x3mm_P0.5mm_EP1.57x1.88mm",
    "HVSSOP-20": "Package_SO:HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP3.4x6.5mm",
    "HVSSOP-24": "Package_SO:HTSSOP-24-1EP_4.4x7.8mm_P0.65mm_EP3.2x5mm",
    "HVSSOP-28": "Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm",
    "DGQ": "Package_SO:HTSSOP-24-1EP_4.4x7.8mm_P0.65mm_EP3.2x5mm",
    # VSSOP (same footprint family as MSOP/TSSOP depending on pin count)
    "VSSOP-8": "Package_SO:TSSOP-8_3x3mm_P0.65mm",
    "VSSOP-10": "Package_SO:MSOP-10_3x3mm_P0.5mm",
    "VSSOP-14": "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    # SSOP
    "SSOP-16": "Package_SO:SSOP-16_5.3x6.2mm_P0.65mm",
    "SSOP-20": "Package_SO:SSOP-20_5.3x7.2mm_P0.65mm",
    "SSOP-24": "Package_SO:SSOP-24_5.3x8.2mm_P0.65mm",
    "SSOP-28": "Package_SO:SSOP-28_5.3x10.2mm_P0.65mm",
    # MSOP
    "MSOP-8": "Package_SO:MSOP-8_3x3mm_P0.65mm",
    "MSOP-10": "Package_SO:MSOP-10_3x3mm_P0.5mm",
    # WQFN
    "WQFN-16": "Package_DFN_QFN:Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm",
    "WQFN-40": "Package_DFN_QFN:Texas_RNQ0040A_WQFN-40-1EP_6x4mm_P0.4mm_EP4.7x2.7mm",
    "QFN-40": "Package_DFN_QFN:QFN-40-1EP_5x5mm_P0.4mm_EP3.1x3.1mm",
    # WSON
    "WSON-8": "Package_SON:WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
    "WSON-10": "Package_SON:WSON-10-1EP_2x3mm_P0.5mm_EP0.84x2.4mm",
    # PDIP (through-hole)
    "PDIP-8": "Package_DIP:DIP-8_W7.62mm",
    "PDIP-14": "Package_DIP:DIP-14_W7.62mm",
    "PDIP-16": "Package_DIP:DIP-16_W7.62mm",
    "PDIP-20": "Package_DIP:DIP-20_W7.62mm",
    "PDIP-28": "Package_DIP:DIP-28_W7.62mm",
    # SOT-223
    "SOT-223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
    # SOT-NNN aliases → KiCad footprint names
    "SOT-26": "Package_TO_SOT_SMD:SOT-23-6",
    "SOT-25": "Package_TO_SOT_SMD:SOT-23-5",
    "SOT-457": "Package_TO_SOT_SMD:SOT-23-6",
    "SOT-89-3": "Package_TO_SOT_SMD:SOT-89-3",
    "SOT-89-5": "Package_TO_SOT_SMD:SOT-89-5",
    "SOT-143": "Package_TO_SOT_SMD:SOT-143",
    "SOT-323": "Package_TO_SOT_SMD:SOT-323_SC-70",
    "SOT-343": "Package_TO_SOT_SMD:SOT-343_SC-70-4",
    "SOT-353": "Package_TO_SOT_SMD:SOT-353_SC-70-5",
    "SOT-363": "Package_TO_SOT_SMD:SOT-363_SC-70-6",
    "SOT-416": "Package_TO_SOT_SMD:SOT-416",
    "SOT-523": "Package_TO_SOT_SMD:SOT-523",
    "SOT-543": "Package_TO_SOT_SMD:SOT-543",
    "SOT-553": "Package_TO_SOT_SMD:SOT-553",
    "SOT-563": "Package_TO_SOT_SMD:SOT-563",
    "SOT-665": "Package_TO_SOT_SMD:SOT-665",
    "SOT-666": "Package_TO_SOT_SMD:SOT-666",
    "SOT-723": "Package_TO_SOT_SMD:SOT-723",
    "SOT-883": "Package_TO_SOT_SMD:SOT-883",
    "SOT-886": "Package_TO_SOT_SMD:SOT-886",
    "SOT-963": "Package_TO_SOT_SMD:SOT-963",
    # TSOP small-package aliases (SOT-23 variants with different body)
    "TSOP-5": "Package_SO:TSOP-5_1.65x3.05mm_P0.95mm",
    "TSOP-6": "Package_SO:TSOP-6_1.65x3.05mm_P0.95mm",
    # --- Tier 2: MCU/FPGA/discrete packages ---
    # LQFP (used by STM32, NXP, Renesas MCUs)
    "LQFP-32": "Package_QFP:LQFP-32_7x7mm_P0.8mm",
    "LQFP-44": "Package_QFP:LQFP-44_10x10mm_P0.8mm",
    "LQFP-48": "Package_QFP:LQFP-48_7x7mm_P0.5mm",
    "LQFP-64": "Package_QFP:LQFP-64_10x10mm_P0.5mm",
    "LQFP-100": "Package_QFP:LQFP-100_14x14mm_P0.5mm",
    "LQFP-144": "Package_QFP:LQFP-144_20x20mm_P0.5mm",
    "LQFP-176": "Package_QFP:LQFP-176_24x24mm_P0.5mm",
    "LQFP-208": "Package_QFP:LQFP-208_28x28mm_P0.5mm",
    # TQFP
    "TQFP-32": "Package_QFP:TQFP-32_7x7mm_P0.8mm",
    "TQFP-44": "Package_QFP:TQFP-44_10x10mm_P0.8mm",
    "TQFP-48": "Package_QFP:TQFP-48_7x7mm_P0.5mm",
    "TQFP-64": "Package_QFP:TQFP-64_10x10mm_P0.5mm",
    "TQFP-100": "Package_QFP:TQFP-100_14x14mm_P0.5mm",
    "TQFP-144": "Package_QFP:TQFP-144_20x20mm_P0.5mm",
    # Plain QFP (mapped to LQFP footprints as closest match)
    "QFP-32": "Package_QFP:LQFP-32_7x7mm_P0.8mm",
    "QFP-44": "Package_QFP:TQFP-44_10x10mm_P0.8mm",
    "QFP-48": "Package_QFP:LQFP-48_7x7mm_P0.5mm",
    "QFP-64": "Package_QFP:LQFP-64_10x10mm_P0.5mm",
    "QFP-80": "Package_QFP:TQFP-80_12x12mm_P0.5mm",
    "QFP-100": "Package_QFP:LQFP-100_14x14mm_P0.5mm",
    # BGA (common MCU/FPGA sizes)
    "BGA-100": "Package_BGA:BGA-100_11.0x11.0mm_Layout10x10_P1.0mm_Ball0.5mm_Pad0.4mm_NSMD",
    "BGA-144": "Package_BGA:BGA-144_13.0x13.0mm_Layout12x12_P1.0mm",
    "BGA-256": "Package_BGA:BGA-256_17.0x17.0mm_Layout16x16_P1.0mm",
    # UFBGA/TFBGA (STM32, memory)
    "UFBGA-100": "Package_BGA:BGA-100_6.0x6.0mm_Layout11x11_P0.5mm_Ball0.3mm_Pad0.25mm_NSMD",
    "UFBGA-144": "Package_BGA:BGA-144_7.0x7.0mm_Layout13x13_P0.5mm_Ball0.3mm_Pad0.25mm_NSMD",
    # WLCSP (wafer-level, used by STM32, PMICs)
    "WLCSP-25": "Package_CSP:WLCSP-25_2.30x2.57mm_Layout5x5_P0.4mm",
    "WLCSP-36": "Package_CSP:WLCSP-36_2.57x3.07mm_Layout6x6_P0.4mm",
    "WLCSP-49": "Package_CSP:WLCSP-49_3.15x3.13mm_Layout7x7_P0.4mm",
    # Discrete THT packages
    "TO-220-3": "Package_TO_SOT_THT:TO-220-3_Vertical",
    "TO-220-4": "Package_TO_SOT_THT:TO-220-4_Horizontal_TabDown",
    "TO-220-5": "Package_TO_SOT_THT:TO-220-5_Horizontal_TabDown",
    "TO-247-3": "Package_TO_SOT_THT:TO-247-3_Vertical",
    "TO-247-4": "Package_TO_SOT_THT:TO-247-4_Vertical",
    "TO-92": "Package_TO_SOT_THT:TO-92_Inline",
    # DIP (through-hole MCUs like ATmega328P)
    "DIP-8": "Package_DIP:DIP-8_W7.62mm",
    "DIP-14": "Package_DIP:DIP-14_W7.62mm",
    "DIP-16": "Package_DIP:DIP-16_W7.62mm",
    "DIP-20": "Package_DIP:DIP-20_W7.62mm",
    "DIP-28": "Package_DIP:DIP-28_W7.62mm",
    "DIP-40": "Package_DIP:DIP-40_W15.24mm",
    # SOIC extended (memory ICs, larger interface chips)
    "SOIC-20": "Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm",
    "SOIC-24": "Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm",
    "SOIC-28": "Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm",
}


def check_pdfplumber():
    """Check if pdfplumber is available."""
    try:
        import pdfplumber  # noqa: F401
        return True
    except ImportError:
        return False


def get_pdfplumber_install_cmd():
    """Get the pip install command for the KiCad Python environment."""
    if sys.platform == "darwin":
        return (
            "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
            "Python.framework/Versions/Current/bin/pip3 install pdfplumber"
        )
    elif sys.platform == "win32":
        return r'"C:\Program Files\KiCad\8.0\bin\python.exe" -m pip install pdfplumber'
    else:
        return "pip3 install pdfplumber"
