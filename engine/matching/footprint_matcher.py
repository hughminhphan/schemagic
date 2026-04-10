"""
Footprint matcher: find the best existing KiCad footprint for a given package.

Uses the package info from the datasheet parser, the PACKAGE_MAP from config,
and the library index to find matching footprints.
"""

import os
import re

from ..core.config import PACKAGE_MAP, FOOTPRINT_DIR
from ..core.models import DatasheetData, PackageInfo
from .library_index import LibraryIndex


def match_footprint(datasheet: DatasheetData, index: LibraryIndex) -> tuple:
    """Find the best matching KiCad footprint for the given datasheet data.

    Returns (footprint_lib, footprint_name, score).
    """
    package = datasheet.package
    if not package:
        return "", "", 0.0

    pin_count = package.pin_count or len(datasheet.pins)

    # Strategy 1: Package name lookup in PACKAGE_MAP (most reliable)
    pkg_name = package.name.upper()
    for key, fp_str in PACKAGE_MAP.items():
        if key.upper() == pkg_name:
            lib, name = fp_str.split(":", 1)
            if _footprint_exists(lib, name):
                return lib, name, 100.0

    # Strategy 2: TI code direct lookup in PACKAGE_MAP
    if package.ti_code and package.ti_code in PACKAGE_MAP:
        fp_str = PACKAGE_MAP[package.ti_code]
        lib, name = fp_str.split(":", 1)
        if _footprint_exists(lib, name):
            return lib, name, 95.0

    # Strategy 3: Search the library index by package name
    search_terms = _generate_search_terms(package)
    for term in search_terms:
        matches = index.search_footprints(term, pin_count)
        if matches:
            lib, entry, score = matches[0]
            pad_count = entry["pad_count"]
            # Verify pad count matches
            if pad_count == pin_count or pin_count == 0:
                return lib, entry["name"], score
            # Some footprints have an exposed pad not counted in pin_count,
            # or the datasheet counts EP but the footprint doesn't (or vice versa)
            if abs(pad_count - pin_count) <= 2:
                return lib, entry["name"], score * 0.9

    # Strategy 4: Broader search
    generic_term = re.sub(r"[-_]?\d+$", "", package.name)
    if generic_term != package.name:
        matches = index.search_footprints(generic_term, pin_count)
        for lib, entry, score in matches[:5]:
            if entry["pad_count"] == pin_count:
                return lib, entry["name"], score * 0.8

    return "", "", 0.0


def _footprint_exists(lib, name):
    """Check if a footprint file actually exists on disk."""
    if not FOOTPRINT_DIR:
        return False
    fp_path = os.path.join(FOOTPRINT_DIR, f"{lib}.pretty", f"{name}.kicad_mod")
    return os.path.isfile(fp_path)


def _generate_search_terms(package: PackageInfo):
    """Generate search terms from package info, ordered by specificity."""
    terms = []
    name = package.name

    # Exact name
    terms.append(name)

    # With pin count appended
    if package.pin_count and not re.search(r"\d+$", name):
        terms.append(f"{name}-{package.pin_count}")

    # Normalized variants
    terms.append(name.replace("-", "").replace("_", ""))
    terms.append(name.replace("-", "_"))

    # Cross-reference common package family aliases
    # HTSSOP <-> TSSOP-EP, WQFN <-> QFN, VQFN <-> QFN
    upper = name.upper()
    if upper.startswith("HTSSOP"):
        suffix = upper[6:]  # e.g. "-40"
        terms.append(f"TSSOP{suffix}")
    elif upper.startswith("WQFN"):
        suffix = upper[4:]
        terms.append(f"QFN{suffix}")
        terms.append(f"VQFN{suffix}")
    elif upper.startswith("VQFN"):
        suffix = upper[4:]
        terms.append(f"QFN{suffix}")
        terms.append(f"WQFN{suffix}")
    elif upper.startswith("TQFN"):
        suffix = upper[4:]
        terms.append(f"QFN{suffix}")

    return terms
