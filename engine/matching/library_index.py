"""
Library indexer: scan KiCad symbol and footprint libraries and build a
searchable in-memory index.  Results are cached as JSON for fast startup.
"""

import json
import os
import re
import time

from ..core.config import SYMBOL_DIR, FOOTPRINT_DIR, INDEX_CACHE, CACHE_DIR
from ..generation.sexpr import parse_file


class LibraryIndex:
    """Index of all KiCad symbols and footprints for fast searching."""

    def __init__(self):
        self.symbols = {}       # {lib_name: [SymbolEntry, ...]}
        self.footprints = {}    # {lib_name: [FootprintEntry, ...]}
        self._loaded = False

    def load_or_build(self, force_rebuild=False):
        """Load from cache or build fresh."""
        if self._loaded and not force_rebuild:
            return

        if not force_rebuild and os.path.isfile(INDEX_CACHE):
            try:
                age = time.time() - os.path.getmtime(INDEX_CACHE)
                if age < 86400 * 7:  # 7-day cache
                    self._load_cache()
                    self._loaded = True
                    return
            except OSError:
                pass

        self._build()
        self._save_cache()
        self._loaded = True

    def _load_cache(self):
        with open(INDEX_CACHE, "r") as f:
            data = json.load(f)
        self.symbols = data.get("symbols", {})
        self.footprints = data.get("footprints", {})

    def _save_cache(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        data = {"symbols": self.symbols, "footprints": self.footprints}
        with open(INDEX_CACHE, "w") as f:
            json.dump(data, f, indent=1)

    def _build(self):
        """Build the index by scanning all KiCad libraries."""
        self.symbols = {}
        self.footprints = {}

        if SYMBOL_DIR and os.path.isdir(SYMBOL_DIR):
            self._index_symbols()

        if FOOTPRINT_DIR and os.path.isdir(FOOTPRINT_DIR):
            self._index_footprints()

    def _index_symbols(self):
        """Scan all .kicad_sym files and extract symbol metadata."""
        for fname in sorted(os.listdir(SYMBOL_DIR)):
            if not fname.endswith(".kicad_sym"):
                continue
            lib_name = fname[:-10]  # strip .kicad_sym
            fpath = os.path.join(SYMBOL_DIR, fname)
            try:
                entries = self._parse_symbol_lib(fpath, lib_name)
                if entries:
                    self.symbols[lib_name] = entries
            except Exception:
                continue

    def _parse_symbol_lib(self, path, lib_name):
        """Parse a .kicad_sym file and extract symbol entries."""
        nodes = parse_file(path)
        if not nodes:
            return []

        root = nodes[0]  # kicad_symbol_lib
        entries = []
        # Build a map for resolving 'extends'
        parent_pins = {}

        for sym in root.find_all("symbol"):
            name = sym.get_value(0)
            if not name:
                continue

            # Skip sub-symbols (like "TPS54302_0_1")
            if re.match(r".*_\d+_\d+$", name):
                continue

            # Check for extends
            extends_node = sym.find_child("extends")
            extends = extends_node.get_value(0) if extends_node else ""

            # Extract properties
            description = sym.get_property("Description") or ""
            keywords = sym.get_property("ki_keywords") or ""
            footprint = sym.get_property("Footprint") or ""
            fp_filters = sym.get_property("ki_fp_filters") or ""

            # Extract pins
            pins = []
            for pin_node in sym.find_recursive("pin"):
                pin_name_node = pin_node.find_child("name")
                pin_num_node = pin_node.find_child("number")
                if pin_name_node and pin_num_node:
                    pins.append({
                        "number": pin_num_node.get_value(0),
                        "name": pin_name_node.get_value(0),
                        "type": pin_node.get_value(0),  # power_in, input, etc.
                    })

            if not extends:
                parent_pins[name] = pins

            entry = {
                "name": name,
                "pin_count": len(pins),
                "pins": pins,
                "description": description,
                "keywords": keywords,
                "footprint": footprint,
                "fp_filters": fp_filters,
                "extends": extends,
            }
            entries.append(entry)

        # Resolve extends: copy pin data from parent
        for entry in entries:
            if entry["extends"] and not entry["pins"]:
                parent = entry["extends"]
                if parent in parent_pins:
                    entry["pins"] = parent_pins[parent]
                    entry["pin_count"] = len(entry["pins"])

        return entries

    def _index_footprints(self):
        """Scan all .pretty directories and extract footprint metadata."""
        for dname in sorted(os.listdir(FOOTPRINT_DIR)):
            if not dname.endswith(".pretty"):
                continue
            lib_name = dname[:-7]  # strip .pretty
            dpath = os.path.join(FOOTPRINT_DIR, dname)
            entries = []

            for fname in sorted(os.listdir(dpath)):
                if not fname.endswith(".kicad_mod"):
                    continue
                fp_name = fname[:-10]  # strip .kicad_mod
                fp_path = os.path.join(dpath, fname)
                try:
                    pad_count = self._count_pads(fp_path)
                except Exception:
                    pad_count = 0

                entries.append({
                    "name": fp_name,
                    "pad_count": pad_count,
                })

            if entries:
                self.footprints[lib_name] = entries

    def _count_pads(self, fp_path):
        """Count numbered pads in a .kicad_mod file (fast regex, no full parse)."""
        with open(fp_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Count pads with non-empty numbers (quoted or unquoted)
        return len(re.findall(r'\(pad\s+(?:"[^"]+"|[^\s)]+)\s+(?:smd|thru_hole)', content))

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    def search_symbols(self, query, pin_count=0):
        """Search for symbols matching a query string.

        Returns list of (lib_name, entry, score) sorted by score descending.
        """
        self.load_or_build()
        query_upper = query.upper().strip()
        results = []

        for lib_name, entries in self.symbols.items():
            for entry in entries:
                score = self._score_symbol(entry, query_upper, pin_count)
                if score > 0:
                    results.append((lib_name, entry, score))

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def _score_symbol(self, entry, query, pin_count):
        """Score a symbol against a search query."""
        name = entry["name"].upper()
        score = 0.0

        # Exact match
        if name == query:
            score = 100.0
        # Name starts with query
        elif name.startswith(query):
            score = 80.0
        # Query starts with name (minus trailing wildcard chars like 'x')
        # Handles KiCad convention: STM32F103C8Tx matches STM32F103C8T6
        elif self._wildcard_suffix_match(name, query):
            score = 85.0
        # Query is contained in name
        elif query in name:
            score = 50.0
        # Query is in description or keywords
        elif query in entry.get("description", "").upper():
            score = 20.0
        elif query in entry.get("keywords", "").upper():
            score = 15.0
        else:
            return 0.0

        # Bonus for matching pin count
        if pin_count > 0 and entry["pin_count"] == pin_count:
            score += 10.0
        elif pin_count > 0 and entry["pin_count"] != pin_count:
            score -= 5.0

        return score

    @staticmethod
    def _wildcard_suffix_match(sym_name, query):
        """Check if a symbol name with wildcard suffix matches the query.

        KiCad uses lowercase 'x' as a wildcard in symbol names, e.g.
        STM32F103C8Tx matches STM32F103C8T6. Also handles trailing
        wildcards like ATmega328P-xU matching ATmega328P-AU.
        """
        # Strip trailing wildcard chars (x, X) from symbol name to get prefix
        name = sym_name
        while name and name[-1] in ("X",):
            name = name[:-1]
        if not name or name == sym_name:
            return False
        # Query must start with the prefix and be similar length
        # (allow up to len(wildcards_stripped) extra chars)
        wildcards = len(sym_name) - len(name)
        return (query.startswith(name)
                and len(query) <= len(name) + wildcards + 1)

    def search_footprints(self, query, pad_count=0):
        """Search for footprints matching a query string.

        Returns list of (lib_name, entry, score) sorted by score descending.
        """
        self.load_or_build()
        query_upper = query.upper().strip()
        results = []

        for lib_name, entries in self.footprints.items():
            for entry in entries:
                score = self._score_footprint(entry, query_upper, pad_count)
                if score > 0:
                    results.append((lib_name, entry, score))

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def _score_footprint(self, entry, query, pad_count):
        """Score a footprint against a search query."""
        name = entry["name"].upper()
        score = 0.0

        if name == query:
            score = 100.0
        elif query in name:
            score = 50.0
        else:
            # Try matching with normalized separators
            norm_name = name.replace("-", "").replace("_", "")
            norm_query = query.replace("-", "").replace("_", "")
            if norm_query in norm_name:
                score = 40.0
            else:
                return 0.0

        # Bonus for matching pad count
        if pad_count > 0 and entry["pad_count"] == pad_count:
            score += 10.0
        elif pad_count > 0 and entry["pad_count"] != pad_count:
            score -= 5.0

        return score

    def get_symbol_entry(self, lib_name, symbol_name):
        """Get a specific symbol entry by lib and name."""
        self.load_or_build()
        entries = self.symbols.get(lib_name, [])
        for entry in entries:
            if entry["name"] == symbol_name:
                return entry
        return None

    def get_footprint_entry(self, lib_name, footprint_name):
        """Get a specific footprint entry by lib and name."""
        self.load_or_build()
        entries = self.footprints.get(lib_name, [])
        for entry in entries:
            if entry["name"] == footprint_name:
                return entry
        return None
