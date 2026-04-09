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
from ..core.user_config import get_gemini_key
from ..core.models import DatasheetData, PinInfo, PackageInfo, MatchResult, GeneratedComponent
from ..datasheet.fetcher import fetch_datasheet, guess_manufacturer
from ..datasheet.parser import extract_tables_and_text, find_description, find_component_type
from ..datasheet.ai_extractor import extract_with_gemini, extract_pins_for_package
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
        self._ai_pins = []
        self._ai_packages = []
        self._ai_pin_package = None  # which package the cached pins were extracted for

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

            # --- Gemini extraction (mandatory) ---
            gemini_key, gemini_model = get_gemini_key()
            ai_packages, ai_pins, ai_desc = extract_with_gemini(
                part_number, page_texts,
                gemini_key, gemini_model,
                status_callback=self._status,
            )
            if ai_desc and not datasheet.description:
                datasheet.description = ai_desc
            if ai_packages:
                self._status("Gemini found {} package(s)".format(len(ai_packages)))

            self._ai_packages = ai_packages
            self._ai_pins = ai_pins
            candidates = ai_packages

            # Try auto-select: suffix code matches a Gemini candidate's ti_code
            selected = None
            if suffix_code:
                for c in candidates:
                    if c.ti_code and c.ti_code.upper() == suffix_code.upper():
                        selected = c
                        break
                if selected:
                    self._status(f"Auto-selected package {selected.name} from suffix '{suffix_code}'")

            # Single candidate - auto-select
            if not selected and len(candidates) == 1:
                selected = candidates[0]
                self._status(f"Auto-selected package {selected.name} (only candidate)")

            if selected:
                self._ai_pin_package = selected.name
                datasheet.pins = ai_pins
                datasheet.confidence = 0.9
                return self._finish_with_package(datasheet, selected, candidates, suffix_code)

            # Multiple candidates - use AI pins optimistically, user will pick package
            datasheet.pins = ai_pins
            datasheet.confidence = 0.9

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

        # Use cached Gemini pins if they match, otherwise re-query for the specific package
        if self._ai_pins and self._ai_pin_package == selected_package.name:
            pins = self._ai_pins
            confidence = 0.9
        elif (self._ai_pins and not self._ai_pin_package
              and len(self._ai_pins) == selected_package.pin_count):
            # Initial extraction matches the selected package pin count - use as-is
            pins = self._ai_pins
            confidence = 0.9
            self._ai_pin_package = selected_package.name
        else:
            # Re-query Gemini for the user-selected package
            self._status(f"Re-extracting pins for {selected_package.name} with Gemini...")
            gemini_key, gemini_model = get_gemini_key()
            pins = extract_pins_for_package(
                self._part_number, self._page_texts,
                gemini_key, gemini_model,
                package_name=selected_package.name,
                pin_count=selected_package.pin_count,
                status_callback=self._status,
            )
            confidence = 0.9
            self._ai_pins = pins
            self._ai_pin_package = selected_package.name

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
