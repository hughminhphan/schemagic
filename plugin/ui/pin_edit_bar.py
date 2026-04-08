"""Inline pin editor bar for the visual pin review dialog.

Shows the currently selected pin's editable fields (name, type) and a
deselect button. Shows placeholder text when nothing is selected.
"""

import wx


PIN_TYPES = [
    "input", "output", "bidirectional", "tri_state", "passive",
    "power_in", "power_out", "open_collector", "open_emitter",
    "no_connect", "unspecified", "free",
]


class PinEditBar(wx.Panel):
    """Horizontal bar for editing a selected pin's name and type."""

    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(30, 30, 30))

        self._pin_idx = -1
        self.on_name_change = None   # fn(pin_idx, new_name)
        self.on_type_change = None   # fn(pin_idx, new_type)
        self.on_deselect = None      # fn()

        self._build_ui()
        self._show_placeholder()

    def _build_ui(self):
        self._sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Pin label (e.g. "Pin 3 (+4, 5)")
        self._pin_label = wx.StaticText(self, label="")
        self._pin_label.SetForegroundColour(wx.Colour(200, 200, 200))
        font = self._pin_label.GetFont()
        font.SetFamily(wx.FONTFAMILY_TELETYPE)
        self._pin_label.SetFont(font)
        self._sizer.Add(self._pin_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)

        # Name input
        self._name_label = wx.StaticText(self, label="  Name:")
        self._name_label.SetForegroundColour(wx.Colour(150, 150, 150))
        self._sizer.Add(self._name_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        self._name_input = wx.TextCtrl(self, size=(120, -1))
        self._name_input.Bind(wx.EVT_TEXT, self._on_name_text)
        self._sizer.Add(self._name_input, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        # Type dropdown
        self._type_label = wx.StaticText(self, label="  Type:")
        self._type_label.SetForegroundColour(wx.Colour(150, 150, 150))
        self._sizer.Add(self._type_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        self._type_choice = wx.Choice(self, choices=PIN_TYPES)
        self._type_choice.Bind(wx.EVT_CHOICE, self._on_type_choice)
        self._sizer.Add(self._type_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        # Description (read-only)
        self._desc_label = wx.StaticText(self, label="")
        self._desc_label.SetForegroundColour(wx.Colour(100, 100, 100))
        self._sizer.Add(self._desc_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)

        # Deselect button
        self._deselect_btn = wx.Button(self, label="Deselect", size=(70, -1))
        self._deselect_btn.Bind(wx.EVT_BUTTON, self._on_deselect)
        self._sizer.Add(self._deselect_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)

        self.SetSizer(self._sizer)

    def _show_placeholder(self):
        self._pin_idx = -1
        self._pin_label.SetLabel("  Click a pin or pad to edit")
        self._name_input.Hide()
        self._name_label.Hide()
        self._type_choice.Hide()
        self._type_label.Hide()
        self._desc_label.SetLabel("")
        self._deselect_btn.Hide()
        self.Layout()

    def show_pin(self, pin_number, datasheet_pins):
        """Show the pin editor for the given pin number.

        If pin_number is None, shows placeholder text.
        datasheet_pins is a list of PinInfo objects.
        """
        if pin_number is None:
            self._show_placeholder()
            return

        # Find the pin by number
        pin = None
        idx = -1
        for i, p in enumerate(datasheet_pins):
            if p.number == pin_number:
                pin = p
                idx = i
                break

        if pin is None:
            self._show_placeholder()
            return

        self._pin_idx = idx

        # Build label: "Pin 3" or "Pin 3 (+4, 5)"
        alts = getattr(pin, "alt_numbers", None) or []
        if alts:
            alt_str = ", ".join(alts)
            self._pin_label.SetLabel("  Pin %s (+%s)" % (pin.number, alt_str))
        else:
            self._pin_label.SetLabel("  Pin %s" % pin.number)

        # Show and populate fields
        self._name_input.Show()
        self._name_label.Show()
        self._name_input.ChangeValue(pin.name)

        self._type_choice.Show()
        self._type_label.Show()
        pin_type = getattr(pin, "pin_type", "unspecified")
        if pin_type in PIN_TYPES:
            self._type_choice.SetSelection(PIN_TYPES.index(pin_type))
        else:
            self._type_choice.SetSelection(PIN_TYPES.index("unspecified"))

        desc = getattr(pin, "description", "") or ""
        if len(desc) > 40:
            desc = desc[:37] + "..."
        self._desc_label.SetLabel(desc)

        self._deselect_btn.Show()
        self.Layout()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_name_text(self, event):
        if self._pin_idx >= 0 and self.on_name_change:
            self.on_name_change(self._pin_idx, self._name_input.GetValue())

    def _on_type_choice(self, event):
        if self._pin_idx >= 0 and self.on_type_change:
            sel = self._type_choice.GetSelection()
            if sel != wx.NOT_FOUND:
                self.on_type_change(self._pin_idx, PIN_TYPES[sel])

    def _on_deselect(self, event):
        if self.on_deselect:
            self.on_deselect()
