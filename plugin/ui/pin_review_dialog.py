"""
Pin review dialog with visual symbol/footprint preview and cross-highlighting.

Shows a split view: symbol renderer (left) + footprint renderer (right) on top,
inline pin edit bar in the middle, and a collapsible pin grid at the bottom.

Cross-highlighting: clicking a pin in the symbol highlights corresponding pads
in the footprint, and vice versa. EP (exposed pad) resolution maps the "EP"
alias to the actual large thermal pad number.
"""

import os
import math

import wx
import wx.grid

from .symbol_panel import SymbolPanel
from .footprint_panel import FootprintPanel
from .pin_edit_bar import PinEditBar


# KiCad pin types for the dropdown editor
PIN_TYPES = [
    "input", "output", "bidirectional", "tri_state", "passive",
    "power_in", "power_out", "open_collector", "open_emitter",
    "no_connect", "unspecified", "free",
]

# Column indices
COL_PIN_NUM = 0
COL_DS_NAME = 1
COL_DS_TYPE = 2
COL_SYM_NAME = 3
COL_SYM_TYPE = 4
COL_STATUS = 5

COL_LABELS = ["Pin #", "Datasheet Name", "Type", "Symbol Name", "Symbol Type", "Status"]


class PinReviewDialog(wx.Dialog):
    """Dialog for reviewing and confirming pin assignments with visual preview."""

    def __init__(self, parent, datasheet_pins, symbol_pins, pin_mapping=None,
                 match=None):
        """
        Args:
            parent: wx parent window
            datasheet_pins: list of PinInfo from the datasheet
            symbol_pins: list of {"number", "name", "type"} from the matched symbol
            pin_mapping: dict {ds_pin_num: sym_pin_num}
            match: MatchResult with symbol_lib/name, footprint_lib/name (optional)
        """
        super().__init__(parent, title="Pin Assignment Review",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                         size=(950, 700))

        self.datasheet_pins = list(datasheet_pins)
        self.symbol_pins = {p["number"]: p for p in (symbol_pins or [])}
        self.pin_mapping = dict(pin_mapping or {})
        self._match = match
        self.confirmed = False

        # Cross-highlighting state
        self._selected_pin_number = None
        self._name_groups = {}      # name.upper() -> [pin_numbers]
        self._pad_to_pin_map = {}   # pad_number -> primary_pin_number
        self._ep_pad_number = None
        self._fp_payload = None

        self._grid_visible = False

        self._build_ui()
        self._populate_grid()
        self._load_visual_data()
        self._build_cross_highlight_maps()

        self.CenterOnParent()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Header
        header = wx.StaticText(panel, label="Review pin assignments. "
                               "Click pins or pads to cross-highlight and edit.")
        header.SetFont(header.GetFont().Bold())
        main_sizer.Add(header, 0, wx.ALL, 10)

        # Visual preview row
        preview_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._symbol_panel = SymbolPanel(panel, size=(420, 320))
        self._symbol_panel.on_pin_click = self._on_pin_clicked

        self._footprint_panel = FootprintPanel(panel, size=(420, 320))
        self._footprint_panel.on_pad_click = self._on_pad_clicked

        preview_sizer.Add(self._symbol_panel, 1, wx.EXPAND | wx.RIGHT, 4)
        preview_sizer.Add(self._footprint_panel, 1, wx.EXPAND | wx.LEFT, 4)
        main_sizer.Add(preview_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Pin edit bar
        self._edit_bar = PinEditBar(panel)
        self._edit_bar.on_name_change = self._on_edit_pin_name
        self._edit_bar.on_type_change = self._on_edit_pin_type
        self._edit_bar.on_deselect = self._on_deselect
        main_sizer.Add(self._edit_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # Toggle grid button
        self._toggle_btn = wx.Button(panel, label="Show all pins (%d)" % len(self.datasheet_pins))
        self._toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle_grid)
        main_sizer.Add(self._toggle_btn, 0, wx.LEFT | wx.TOP, 10)

        # Grid (hidden by default)
        self.grid = wx.grid.Grid(panel)
        self.grid.CreateGrid(len(self.datasheet_pins), len(COL_LABELS))
        for i, label in enumerate(COL_LABELS):
            self.grid.SetColLabelValue(i, label)

        self.grid.SetColSize(COL_PIN_NUM, 50)
        self.grid.SetColSize(COL_DS_NAME, 120)
        self.grid.SetColSize(COL_DS_TYPE, 110)
        self.grid.SetColSize(COL_SYM_NAME, 120)
        self.grid.SetColSize(COL_SYM_TYPE, 110)
        self.grid.SetColSize(COL_STATUS, 80)

        # Make status and pin number columns read-only
        attr = wx.grid.GridCellAttr()
        attr.SetReadOnly(True)
        self.grid.SetColAttr(COL_STATUS, attr)

        attr2 = wx.grid.GridCellAttr()
        attr2.SetReadOnly(True)
        self.grid.SetColAttr(COL_PIN_NUM, attr2)

        # Type column dropdown
        type_editor = wx.grid.GridCellChoiceEditor(PIN_TYPES)
        attr3 = wx.grid.GridCellAttr()
        attr3.SetEditor(type_editor)
        self.grid.SetColAttr(COL_DS_TYPE, attr3)

        self.grid.Hide()
        main_sizer.Add(self.grid, 1, wx.EXPAND | wx.ALL, 10)

        # Legend
        legend_sizer = wx.BoxSizer(wx.HORIZONTAL)
        for color, label in [
            (wx.Colour(200, 255, 200), "Match"),
            (wx.Colour(255, 255, 180), "Differs"),
            (wx.Colour(255, 200, 200), "No match"),
        ]:
            indicator = wx.Panel(panel, size=(16, 16))
            indicator.SetBackgroundColour(color)
            legend_sizer.Add(indicator, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
            legend_sizer.Add(wx.StaticText(panel, label=label), 0,
                             wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 16)
        main_sizer.Add(legend_sizer, 0, wx.LEFT | wx.BOTTOM, 10)

        # Buttons
        btn_sizer = wx.StdDialogButtonSizer()
        confirm_btn = wx.Button(panel, wx.ID_OK, "Confirm && Save")
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_sizer.AddButton(confirm_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        confirm_btn.Bind(wx.EVT_BUTTON, self._on_confirm)
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)

        panel.SetSizer(main_sizer)

    # ------------------------------------------------------------------
    # Grid population (same as before)
    # ------------------------------------------------------------------

    def _populate_grid(self):
        for row, pin in enumerate(self.datasheet_pins):
            if pin.alt_numbers:
                all_nums = [pin.number] + pin.alt_numbers
                pin_display = ", ".join(all_nums)
            else:
                pin_display = pin.number
            self.grid.SetCellValue(row, COL_PIN_NUM, pin_display)
            self.grid.SetCellValue(row, COL_DS_NAME, pin.name)
            self.grid.SetCellValue(row, COL_DS_TYPE, pin.pin_type)

            all_pin_nums = [pin.number] + pin.alt_numbers
            sym_pin = None
            for pn in all_pin_nums:
                sym_pn = self.pin_mapping.get(pn, pn)
                sym_pin = self.symbol_pins.get(sym_pn)
                if sym_pin:
                    break

            if sym_pin:
                self.grid.SetCellValue(row, COL_SYM_NAME, sym_pin.get("name", ""))
                self.grid.SetCellValue(row, COL_SYM_TYPE, sym_pin.get("type", ""))

                name_match = pin.name.upper() == sym_pin.get("name", "").upper()
                type_match = pin.pin_type == sym_pin.get("type", "")
                n_pins = 1 + len(pin.alt_numbers)
                suffix = " [%d pins]" % n_pins if n_pins > 1 else ""

                if name_match and type_match:
                    self.grid.SetCellValue(row, COL_STATUS, "Match" + suffix)
                    self._set_row_color(row, wx.Colour(200, 255, 200))
                else:
                    self.grid.SetCellValue(row, COL_STATUS, "Differs" + suffix)
                    self._set_row_color(row, wx.Colour(255, 255, 180))
            else:
                self.grid.SetCellValue(row, COL_SYM_NAME, "-")
                self.grid.SetCellValue(row, COL_SYM_TYPE, "-")
                n_pins = 1 + len(pin.alt_numbers)
                suffix = " [%d pins]" % n_pins if n_pins > 1 else ""
                self.grid.SetCellValue(row, COL_STATUS, "No match" + suffix)
                self._set_row_color(row, wx.Colour(255, 200, 200))

    def _set_row_color(self, row, color):
        for col in range(self.grid.GetNumberCols()):
            self.grid.SetCellBackgroundColour(row, col, color)

    # ------------------------------------------------------------------
    # Visual data loading
    # ------------------------------------------------------------------

    def _load_visual_data(self):
        """Load symbol and footprint rendering data from KiCad library files."""
        from ui.kicad_lib_parser import (
            parse_symbol_file, parse_footprint_file, generate_synthetic_symbol,
        )
        from core.config import SYMBOL_DIR, FOOTPRINT_DIR

        # Symbol
        if self._match and self._match.symbol_lib and self._match.symbol_name:
            lib_path = os.path.join(SYMBOL_DIR, "%s.kicad_sym" % self._match.symbol_lib)
            sym_payload = parse_symbol_file(lib_path, self._match.symbol_name)
            if not sym_payload.found:
                sym_payload = generate_synthetic_symbol(self.datasheet_pins)
        else:
            sym_payload = generate_synthetic_symbol(self.datasheet_pins)
        self._symbol_panel.set_data(sym_payload)

        # Footprint
        if self._match and self._match.footprint_lib and self._match.footprint_name:
            fp_path = os.path.join(
                FOOTPRINT_DIR,
                "%s.pretty" % self._match.footprint_lib,
                "%s.kicad_mod" % self._match.footprint_name,
            )
            self._fp_payload = parse_footprint_file(fp_path)
            self._footprint_panel.set_data(self._fp_payload)
        else:
            self._fp_payload = None

    # ------------------------------------------------------------------
    # Cross-highlighting
    # ------------------------------------------------------------------

    def _build_cross_highlight_maps(self):
        """Build nameGroups and padToPinMap from datasheet pins + footprint pads."""
        # Build name groups: name.upper() -> [pin_numbers]
        self._name_groups = {}
        for pin in self.datasheet_pins:
            key = pin.name.upper()
            if key in self._name_groups:
                self._name_groups[key].append(pin.number)
            else:
                self._name_groups[key] = [pin.number]

        # Resolve EP pad number from footprint data
        self._ep_pad_number = None
        if self._fp_payload and self._fp_payload.pads:
            largest = None
            for pad in self._fp_payload.pads:
                if not pad.number:
                    continue
                area = pad.size[0] * pad.size[1]
                if not largest or area > largest[1]:
                    largest = (pad.number, area)

            if largest:
                areas = sorted(
                    pad.size[0] * pad.size[1]
                    for pad in self._fp_payload.pads if pad.number
                )
                median = areas[len(areas) // 2] if areas else 1.0
                if largest[1] > median * 3:
                    self._ep_pad_number = largest[0]

        # Build padToPinMap: every pad/alt number -> primary pin number
        self._pad_to_pin_map = {}
        for pin in self.datasheet_pins:
            key = pin.name.upper()
            group = self._name_groups.get(key, [pin.number])
            primary = group[0]
            self._pad_to_pin_map[pin.number] = primary
            for alt in (pin.alt_numbers or []):
                if alt == "EP" and self._ep_pad_number:
                    self._pad_to_pin_map[self._ep_pad_number] = primary
                else:
                    self._pad_to_pin_map[alt] = primary

        # Also handle "EP" as a primary pin number
        ep_pin = None
        for pin in self.datasheet_pins:
            if pin.number == "EP":
                ep_pin = pin
                break
        if ep_pin and self._ep_pad_number:
            key = ep_pin.name.upper()
            group = self._name_groups.get(key)
            self._pad_to_pin_map[self._ep_pad_number] = group[0] if group else ep_pin.number

    def _compute_highlighted_pads(self, pin_number):
        """Return the set of footprint pad numbers to highlight for a given pin."""
        if not pin_number:
            return set()

        highlighted = set()
        selected_pin = None
        for p in self.datasheet_pins:
            if p.number == pin_number:
                selected_pin = p
                break

        if not selected_pin:
            return set()

        key = selected_pin.name.upper()
        group = self._name_groups.get(key, [selected_pin.number])

        for num in group:
            highlighted.add(num)
            # Also add alt_numbers for each pin in the group
            for p in self.datasheet_pins:
                if p.number == num:
                    for alt in (p.alt_numbers or []):
                        if alt == "EP" and self._ep_pad_number:
                            highlighted.add(self._ep_pad_number)
                        else:
                            highlighted.add(alt)
                    break

        return highlighted

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_pin_clicked(self, pin_number):
        """Called when a pin is clicked in the symbol panel."""
        if self._selected_pin_number == pin_number:
            self._selected_pin_number = None
        else:
            self._selected_pin_number = pin_number

        self._update_selection()

    def _on_pad_clicked(self, pad_number):
        """Called when a pad is clicked in the footprint panel."""
        primary = self._pad_to_pin_map.get(pad_number, pad_number)
        if self._selected_pin_number == primary:
            self._selected_pin_number = None
        else:
            self._selected_pin_number = primary

        self._update_selection()

    def _on_deselect(self):
        self._selected_pin_number = None
        self._update_selection()

    def _update_selection(self):
        """Refresh all visual elements after selection change."""
        highlighted = self._compute_highlighted_pads(self._selected_pin_number)
        self._symbol_panel.set_selected_pin(self._selected_pin_number)
        self._footprint_panel.set_highlighted_pads(highlighted)
        self._edit_bar.show_pin(self._selected_pin_number, self.datasheet_pins)

    def _on_edit_pin_name(self, pin_idx, new_name):
        """Handle pin name edit from the edit bar."""
        if 0 <= pin_idx < len(self.datasheet_pins):
            self.datasheet_pins[pin_idx].name = new_name
            self.grid.SetCellValue(pin_idx, COL_DS_NAME, new_name)
            # Rebuild cross-highlight maps since name change affects groups
            self._build_cross_highlight_maps()
            highlighted = self._compute_highlighted_pads(self._selected_pin_number)
            self._footprint_panel.set_highlighted_pads(highlighted)
            self._symbol_panel.Refresh()

    def _on_edit_pin_type(self, pin_idx, new_type):
        """Handle pin type edit from the edit bar."""
        if 0 <= pin_idx < len(self.datasheet_pins):
            self.datasheet_pins[pin_idx].pin_type = new_type
            self.grid.SetCellValue(pin_idx, COL_DS_TYPE, new_type)

    def _on_toggle_grid(self, event):
        self._grid_visible = not self._grid_visible
        if self._grid_visible:
            self.grid.Show()
            self._toggle_btn.SetLabel("Hide pin table")
        else:
            self.grid.Hide()
            self._toggle_btn.SetLabel("Show all pins (%d)" % len(self.datasheet_pins))
        self.Layout()

    def _on_confirm(self, event):
        self.confirmed = True
        self.EndModal(wx.ID_OK)

    def _on_cancel(self, event):
        self.confirmed = False
        self.EndModal(wx.ID_CANCEL)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_confirmed_pins(self):
        """Return the list of PinInfo with user-edited values.

        Reconstructs alt_numbers from comma-separated pin number cells.
        """
        from core.models import PinInfo
        pins = []
        for row in range(self.grid.GetNumberRows()):
            pin_cell = self.grid.GetCellValue(row, COL_PIN_NUM)
            parts = [p.strip() for p in pin_cell.split(",") if p.strip()]
            primary = parts[0] if parts else ""
            alts = parts[1:] if len(parts) > 1 else []
            pins.append(PinInfo(
                number=primary,
                name=self.grid.GetCellValue(row, COL_DS_NAME),
                pin_type=self.grid.GetCellValue(row, COL_DS_TYPE),
                description="",
                alt_numbers=alts,
            ))
        return pins
