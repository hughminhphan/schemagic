"""
Main dialog: part number input, progress display, and pipeline orchestration.

This is the primary UI entry point launched from the KiCad ActionPlugin.
"""

import os
import threading
import traceback

import wx

from engine.core.config import check_pdfplumber, get_pdfplumber_install_cmd
from engine.core.pipeline import Pipeline
from plugin.ui.pin_review_dialog import PinReviewDialog


class MainDialog(wx.Dialog):
    """Main plugin dialog with part number input and progress tracking."""

    def __init__(self, parent, project_dir=None, auto_detected=False):
        super().__init__(parent, title="Datasheet to KiCad Matcher",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                         size=(550, 400))

        self.project_dir = project_dir
        self._auto_detected = auto_detected
        self.pipeline = Pipeline(project_dir)
        self.pipeline.set_status_callback(self._on_status)

        self._datasheet = None
        self._match = None

        self._build_ui()
        self._check_dependencies()
        self.CenterOnParent()

    def _build_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="Datasheet to KiCad Matcher")
        title.SetFont(title.GetFont().MakeLarger().Bold())
        main_sizer.Add(title, 0, wx.ALL, 10)

        # Part number input
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        input_sizer.Add(wx.StaticText(panel, label="Part Number:"), 0,
                        wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.pn_input = wx.TextCtrl(panel, size=(250, -1),
                                    style=wx.TE_PROCESS_ENTER)
        input_sizer.Add(self.pn_input, 1, wx.EXPAND)
        self.search_btn = wx.Button(panel, label="Search")
        input_sizer.Add(self.search_btn, 0, wx.LEFT, 8)
        main_sizer.Add(input_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        main_sizer.AddSpacer(5)

        # Local PDF input
        pdf_sizer = wx.BoxSizer(wx.HORIZONTAL)
        pdf_sizer.Add(wx.StaticText(panel, label="Local PDF:"), 0,
                      wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.pdf_input = wx.TextCtrl(panel, size=(250, -1))
        pdf_sizer.Add(self.pdf_input, 1, wx.EXPAND)
        self.pdf_browse_btn = wx.Button(panel, label="Browse...")
        pdf_sizer.Add(self.pdf_browse_btn, 0, wx.LEFT, 8)
        main_sizer.Add(pdf_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        main_sizer.AddSpacer(5)

        # Project directory display
        proj_sizer = wx.BoxSizer(wx.HORIZONTAL)
        proj_sizer.Add(wx.StaticText(panel, label="Project:"), 0,
                       wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        proj_label = self.project_dir or "(no project open)"
        if self._auto_detected and self.project_dir:
            proj_label += "  (auto-detected)"
        self.proj_text = wx.StaticText(panel, label=proj_label)
        proj_sizer.Add(self.proj_text, 1, wx.EXPAND)
        self.browse_btn = wx.Button(panel, label="Browse...")
        proj_sizer.Add(self.browse_btn, 0, wx.LEFT, 8)
        main_sizer.Add(proj_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        main_sizer.AddSpacer(10)

        # Progress / status
        self.progress = wx.Gauge(panel, range=100, size=(-1, 20))
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.status_text = wx.StaticText(panel, label="Enter a part number to begin.")
        main_sizer.Add(self.status_text, 0, wx.ALL, 10)

        # Results area
        self.result_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                       size=(-1, 120))
        main_sizer.Add(self.result_text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Bottom buttons
        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)

        bottom_sizer.AddStretchSpacer()

        close_btn = wx.Button(panel, wx.ID_CLOSE, "Close")
        bottom_sizer.Add(close_btn, 0)

        main_sizer.Add(bottom_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(main_sizer)

        # Bind events
        self.search_btn.Bind(wx.EVT_BUTTON, self._on_search)
        self.pn_input.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.pdf_browse_btn.Bind(wx.EVT_BUTTON, self._on_pdf_browse)
        self.browse_btn.Bind(wx.EVT_BUTTON, self._on_browse)
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))

    def _check_dependencies(self):
        if not check_pdfplumber():
            self._append_result(
                "WARNING: pdfplumber not installed.\n"
                "PDF parsing will be disabled. Install with:\n"
                f"  {get_pdfplumber_install_cmd()}\n"
            )

        if not self.project_dir:
            self._append_result(
                "NOTE: No KiCad project detected. Use Browse to select a "
                "project directory, or open a project in KiCad first.\n"
            )

    def _on_pdf_browse(self, event):
        dlg = wx.FileDialog(self, "Select Datasheet PDF",
                            wildcard="PDF files (*.pdf)|*.pdf",
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.pdf_input.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _on_browse(self, event):
        dlg = wx.DirDialog(self, "Select KiCad Project Directory",
                           defaultPath=self.project_dir or os.path.expanduser("~"))
        if dlg.ShowModal() == wx.ID_OK:
            self.project_dir = dlg.GetPath()
            self.proj_text.SetLabel(self.project_dir)
            self.pipeline.project_dir = self.project_dir
        dlg.Destroy()

    def _on_search(self, event):
        pn = self.pn_input.GetValue().strip()
        if not pn:
            wx.MessageBox("Please enter a part number.", "Input Required",
                          wx.OK | wx.ICON_WARNING)
            return

        local_pdf = self.pdf_input.GetValue().strip() or None

        self.search_btn.Disable()
        self.pn_input.Disable()
        self.result_text.Clear()
        self.progress.Pulse()

        # Run pipeline in background thread
        thread = threading.Thread(target=self._run_pipeline,
                                  args=(pn, local_pdf), daemon=True)
        thread.start()

    def _run_pipeline(self, part_number, local_pdf=None):
        """Background thread: run the pipeline, then switch to UI thread for dialogs."""
        try:
            datasheet, match, candidates, suffix_code = self.pipeline.run(
                part_number, local_pdf=local_pdf
            )
            wx.CallAfter(self._on_pipeline_complete, datasheet, match,
                         candidates, suffix_code)
        except Exception as e:
            tb = traceback.format_exc()
            wx.CallAfter(self._on_pipeline_error, f"{e}\n\n{tb}")

    def _on_pipeline_complete(self, datasheet, match, candidates, suffix_code):
        """Called on UI thread when pipeline completes."""
        self.progress.SetValue(75)
        self._datasheet = datasheet
        self._match = match

        # If multiple candidates and no auto-selection, ask the user
        needs_selection = (len(candidates) > 1 and datasheet.package is None)
        if needs_selection:
            choices = [f"{c.name} ({c.pin_count} pins)" for c in candidates]
            dlg = wx.SingleChoiceDialog(
                self, "Multiple packages found in datasheet.\nSelect the target package:",
                "Package Selection", choices
            )
            if dlg.ShowModal() == wx.ID_OK:
                selected = candidates[dlg.GetSelection()]
                dlg.Destroy()
                self._status_update(f"Selected package: {selected.name}")
                # Run phase 2 in background
                thread = threading.Thread(
                    target=self._run_phase2, args=(datasheet, selected),
                    daemon=True
                )
                thread.start()
                return
            else:
                dlg.Destroy()
                self._append_result("\nPackage selection cancelled.")
                self._re_enable()
                return

        # Display results
        self._show_results(datasheet, match)

    def _run_phase2(self, datasheet, selected_package):
        """Background thread: run phase 2 after package selection."""
        try:
            datasheet, match, _, _ = self.pipeline.select_package_and_finish(
                datasheet, selected_package
            )
            wx.CallAfter(self._show_results, datasheet, match)
        except Exception as e:
            tb = traceback.format_exc()
            wx.CallAfter(self._on_pipeline_error, f"{e}\n\n{tb}")

    def _show_results(self, datasheet, match):
        """Display results and proceed to pin review."""
        self._datasheet = datasheet
        self._match = match

        lines = []
        lines.append(f"Part: {datasheet.part_number}")
        if datasheet.manufacturer:
            lines.append(f"Manufacturer: {datasheet.manufacturer}")
        if datasheet.description:
            lines.append(f"Description: {datasheet.description[:100]}")
        if datasheet.package:
            lines.append(f"Package: {datasheet.package.name} ({datasheet.package.pin_count} pins)")
        lines.append(f"Pins extracted: {len(datasheet.pins)} (confidence: {datasheet.confidence:.0%})")
        lines.append("")
        if match.symbol_lib:
            lines.append(f"Symbol match: {match.symbol_lib}:{match.symbol_name} (score: {match.symbol_score:.0f})")
        else:
            lines.append("Symbol match: none found (will create new)")
        if match.footprint_lib:
            lines.append(f"Footprint match: {match.footprint_lib}:{match.footprint_name} (score: {match.footprint_score:.0f})")
        else:
            lines.append("Footprint match: none found")

        self._append_result("\n".join(lines))

        # Check if we have pins to review
        if not datasheet.pins:
            self._append_result("\nNo pins extracted from datasheet. Cannot proceed.")
            self._re_enable()
            return

        # Check project directory
        if not self.project_dir:
            self._append_result("\nSet a project directory before saving.")
            self._re_enable()
            return

        # Launch pin review dialog
        self._show_pin_review()

    def _show_pin_review(self):
        """Show the pin review dialog and handle the result."""
        sym_pins = self.pipeline.get_symbol_pins(self._match)

        dlg = PinReviewDialog(self, self._datasheet.pins, sym_pins,
                              self._match.pin_mapping, match=self._match)
        result = dlg.ShowModal()

        if result == wx.ID_OK and dlg.confirmed:
            confirmed_pins = dlg.get_confirmed_pins()
            dlg.Destroy()

            self._status_update("Saving component...")
            try:
                gen = self.pipeline.finalize(self._datasheet, self._match,
                                             confirmed_pins)
                self.progress.SetValue(100)
                self._status_update("Saved successfully!")
                lines = ["\nSaved successfully!"]
                lines.append(f"  Symbol: {gen.symbol_name} in {gen.symbol_lib_path}")
                if gen.footprint_name:
                    lines.append(f"  Footprint: {gen.footprint_name} in {gen.footprint_lib_path}")
                lines.append("\nReload your KiCad project to see the new component.")
                self._append_result("\n".join(lines))
            except Exception as e:
                tb = traceback.format_exc()
                self._append_result(f"\nError saving: {e}\n{tb}")
        else:
            dlg.Destroy()
            self._append_result("\nCancelled — no files were saved.")

        self._re_enable()

    def _on_pipeline_error(self, error_msg):
        """Called on UI thread when pipeline fails."""
        self.progress.SetValue(0)
        self._append_result(f"\nError: {error_msg}")
        self._re_enable()

    def _on_status(self, msg):
        """Status callback from pipeline (may be called from background thread)."""
        wx.CallAfter(self._status_update, msg)

    def _status_update(self, msg):
        """Update status text on the UI thread."""
        self.status_text.SetLabel(msg)

    def _append_result(self, text):
        self.result_text.AppendText(text + "\n")

    def _re_enable(self):
        self.search_btn.Enable()
        self.pn_input.Enable()
        self.pn_input.SetFocus()
