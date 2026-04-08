"""
Pipeline orchestrator: coordinates the full flow from part number to saved
library component.

Steps:
1. Fetch datasheet PDF
2. Parse PDF for pins and package
3. Search KiCad libraries for matching symbol/footprint
4. Present pin review dialog to user
5. Clone and modify symbol/footprint
6. Save to project-local library
"""

import os
import logging

from ..core.config import strip_ti_suffix, check_pdfplumber
from ..core.user_config import get_api_key
from ..core.models import DatasheetData, PinInfo, PackageInfo, MatchResult, GeneratedComponent
from ..datasheet.fetcher import fetch_datasheet, guess_manufacturer
from ..datasheet.parser import extract_tables_and_text, find_description, find_component_type
from ..datasheet.pin_extractor import extract_pins_from_tables, extract_pins_from_text, consolidate_power_pins
from ..datasheet.package_identifier import identify_package, identify_all_packages, _TI_PKG_CODES
from ..datasheet.ai_extractor import extract_with_ai
from ..matching.library_index import LibraryIndex
from ..matching.symbol_matcher import match_symbol
from ..matching.footprint_matcher import match_footprint
from ..generation.symbol_modifier import clone_and_modify_symbol, create_empty_symbol
from ..generation.library_manager import save_component

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the full part-number-to-component flow."""

    def __init__(self, project_dir=None):
        self.project_dir = project_dir
        self.index = LibraryIndex()
        self.status_callback = None  # set by UI: fn(message: str)
        self._tables = []
        self._full_text = ""
        self._page_texts = []

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _status(self, msg):
        if self.status_callback:
            self.status_callback(msg)

    def run(self, part_number, local_pdf=None):
        """Run the pipeline up to the package decision point.

        Args:
            part_number: the part number to search for
            local_pdf: optional path to a local PDF file (skips download)

        Returns (datasheet, match, candidates, suffix_code) where:
            - candidates is a list of PackageInfo found in the datasheet text
            - suffix_code is the TI package code from the part number suffix, or None
            - If package was auto-selected (suffix match or single candidate),
              match is fully populated. Otherwise match is partial and the UI
              must call select_package_and_finish() after the user chooses.
        """
        # Reset per-run state from any previous invocation
        self._tables = []
        self._full_text = ""
        self._part_number = part_number

        # Step 1: Fetch datasheet (or use local PDF)
        url = ""
        pdf_path = ""
        manufacturer = ""

        if local_pdf and os.path.isfile(local_pdf):
            self._status(f"Using local PDF: {os.path.basename(local_pdf)}")
            pdf_path = local_pdf
            manufacturer = guess_manufacturer(part_number)
        else:
            self._status("Fetching datasheet...")
            url, pdf_path, manufacturer = fetch_datasheet(part_number, status_callback=self._status)

        if not manufacturer:
            manufacturer = guess_manufacturer(part_number)

        base_pn, suffix_code = strip_ti_suffix(part_number)

        datasheet = DatasheetData(
            part_number=base_pn.upper(),
            manufacturer=manufacturer,
            datasheet_url=url or "",
            pdf_path=pdf_path or "",
        )

        candidates = []
        self._tables = []
        self._full_text = ""
        self._page_texts = []

        # Step 2: Parse datasheet (if we got a PDF)
        if pdf_path and check_pdfplumber():
            self._status("Parsing datasheet PDF...")
            tables, full_text, page_texts = extract_tables_and_text(pdf_path)
            self._tables = tables
            self._full_text = full_text
            self._page_texts = page_texts

            # Extract description and type
            datasheet.description = find_description(full_text, datasheet.part_number)
            datasheet.component_type = find_component_type(full_text)

            # --- AI extraction (if configured) ---
            ai_provider, ai_key, ai_model = get_api_key()
            ai_packages = []
            ai_pins = []
            if ai_provider and ai_key:
                self._status("Extracting with AI ({})...".format(ai_provider))
                try:
                    ai_packages, ai_pins, ai_desc = extract_with_ai(
                        part_number, page_texts,
                        ai_provider, ai_key, ai_model,
                        status_callback=self._status,
                    )
                    if ai_desc and not datasheet.description:
                        datasheet.description = ai_desc
                    if ai_packages:
                        self._status("AI found {} package(s)".format(len(ai_packages)))
                except Exception as e:
                    logger.warning("AI extraction failed, falling back to regex: %s", e)
                    self._status("AI extraction failed, using regex fallback")

            # Use AI packages if available, otherwise fall back to regex
            if ai_packages:
                candidates = ai_packages
            else:
                # Find all package candidates via table parsing / regex
                self._status("Identifying packages...")
                candidates = identify_all_packages(
                    full_text, base_pn=base_pn, manufacturer=manufacturer,
                    tables=tables, part_number=part_number,
                )

            # Try auto-select: suffix code resolves to a known package
            selected = None
            if suffix_code and suffix_code in _TI_PKG_CODES:
                pkg_name, pkg_pins = _TI_PKG_CODES[suffix_code]
                # Find matching candidate or create one
                for c in candidates:
                    if c.name == pkg_name:
                        selected = c
                        break
                if not selected:
                    selected = PackageInfo(name=pkg_name, pin_count=pkg_pins, ti_code=suffix_code)
                self._status(f"Auto-selected package {selected.name} from suffix '{suffix_code}'")

            # Single candidate - auto-select
            if not selected and len(candidates) == 1:
                selected = candidates[0]
                self._status(f"Auto-selected package {selected.name} (only candidate)")

            if selected:
                # Run phase 2 immediately
                # If AI extracted pins, attach them to the datasheet before finishing
                if ai_pins:
                    datasheet.pins = ai_pins
                    datasheet.confidence = 0.85
                return self._finish_with_package(datasheet, selected, candidates, suffix_code)

            # Multiple candidates and no suffix - extract pins
            if ai_pins:
                # Use AI-extracted pins
                datasheet.pins = ai_pins
                datasheet.confidence = 0.85
            else:
                self._status("Extracting pin assignments...")
                pins, confidence = extract_pins_from_tables(tables, part_number=self._part_number)
                if not pins:
                    pins, confidence = extract_pins_from_text(full_text)
                pins = consolidate_power_pins(pins)
                datasheet.pins = pins
                datasheet.confidence = confidence

        elif not pdf_path:
            self._status("Could not download datasheet - proceeding with library search only")

        # Build index and do initial symbol match (partial — no package selected)
        self._status("Building library index...")
        self.index.load_or_build()

        self._status("Searching for matching symbol...")
        match = match_symbol(datasheet, self.index)

        if len(candidates) > 1:
            self._status("Multiple packages found — awaiting selection")
        elif len(candidates) == 0:
            self._status("No package identified from datasheet")
        else:
            self._status("Ready for review")
        return datasheet, match, candidates, suffix_code

    def select_package_and_finish(self, datasheet, selected_package):
        """Phase 2: after user selects a package, re-extract pins and finish matching.

        Args:
            datasheet: DatasheetData from phase 1
            selected_package: the PackageInfo chosen by the user

        Returns (datasheet, match, candidates, suffix_code) ready for pin review.
        """
        return self._finish_with_package(
            datasheet, selected_package, [], None,
        )

    def _finish_with_package(self, datasheet, selected_package, candidates, suffix_code):
        """Complete the pipeline with a selected package.

        Returns (datasheet, match, candidates, suffix_code).
        """
        datasheet.package = selected_package

        # Re-extract pins filtered to expected pin count and target package
        self._status("Extracting pin assignments...")
        pins, confidence = extract_pins_from_tables(
            self._tables,
            expected_pin_count=selected_package.pin_count,
            target_package=selected_package.name,
            part_number=self._part_number,
        )
        if not pins:
            pins, confidence = extract_pins_from_text(self._full_text)
        pins = consolidate_power_pins(pins)
        datasheet.pins = pins
        datasheet.confidence = confidence

        # Build index and match
        self._status("Building library index...")
        self.index.load_or_build()

        self._status("Searching for matching symbol...")
        match = match_symbol(datasheet, self.index)

        self._status("Searching for matching footprint...")
        fp_lib, fp_name, fp_score = match_footprint(datasheet, self.index)
        match.footprint_lib = fp_lib
        match.footprint_name = fp_name
        match.footprint_score = fp_score

        # If no footprint from matcher, try the symbol's default footprint
        if not match.footprint_lib and match.symbol_lib:
            entry = self.index.get_symbol_entry(match.symbol_lib, match.symbol_name)
            if entry and entry.get("footprint"):
                fp_str = entry["footprint"]
                if ":" in fp_str:
                    match.footprint_lib, match.footprint_name = fp_str.split(":", 1)
                    match.footprint_score = 50.0

        self._status("Ready for pin review")
        return datasheet, match, candidates, suffix_code

    def get_symbol_pins(self, match: MatchResult):
        """Get the pin data from the matched symbol for the review dialog."""
        if not match.symbol_lib or not match.symbol_name:
            return []
        entry = self.index.get_symbol_entry(match.symbol_lib, match.symbol_name)
        if entry:
            return entry.get("pins", [])
        return []

    def finalize(self, datasheet: DatasheetData, match: MatchResult,
                 confirmed_pins: list):
        """After user confirmation, generate and save the component.

        Args:
            datasheet: the parsed datasheet data
            match: the match result
            confirmed_pins: list of PinInfo as confirmed by the user

        Returns:
            GeneratedComponent
        """
        if not self.project_dir:
            raise ValueError("No project directory set — open a KiCad project first")

        # Update datasheet with confirmed pins
        datasheet.pins = confirmed_pins

        # Generate the symbol
        self._status("Generating symbol...")
        use_clone = False
        if match.symbol_lib and match.symbol_name:
            # Only clone if pin count is a reasonable match
            # Count total physical pins including consolidated alt_numbers
            entry = self.index.get_symbol_entry(match.symbol_lib, match.symbol_name)
            total_physical = sum(1 + len(p.alt_numbers) for p in confirmed_pins)
            if entry and entry["pin_count"] == total_physical:
                use_clone = True

        if use_clone:
            symbol_node = clone_and_modify_symbol(
                datasheet, match.symbol_lib, match.symbol_name,
                match.pin_mapping
            )
        else:
            fp_str = f"{match.footprint_lib}:{match.footprint_name}" if match.footprint_lib else ""
            symbol_node = create_empty_symbol(datasheet, footprint_str=fp_str)

        # Save to project
        self._status("Saving to project library...")
        result = save_component(
            self.project_dir, symbol_node,
            match.footprint_lib, match.footprint_name,
        )

        self._status(f"Saved {result.symbol_name} to project library")
        return result
