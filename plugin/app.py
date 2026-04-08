#!/usr/bin/env python3
"""scheMAGIC - menubar app with global hotkey.

Runs as a persistent macOS menubar app. Press the configured hotkey
(default: Ctrl+Shift+K) from any app to open the component search dialog.
"""

import json
import os
import sys

os.environ["SCHEMAGIC_STANDALONE"] = "1"

# Add repo root to sys.path so engine/ and plugin/ are importable
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import wx
import wx.adv

from plugin.ui.main_dialog import MainDialog
from engine.core.project_detector import detect_kicad_project

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_DIR = os.path.expanduser("~/.schemagic")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
FIRST_RUN_SENTINEL = os.path.join(CONFIG_DIR, ".setup_done")

DEFAULT_CONFIG = {
    "hotkey_modifiers": ["ctrl", "shift"],
    "hotkey_key": "k",
    "start_at_login": False,
}


def load_config():
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# Global hotkey via pyobjc
# ---------------------------------------------------------------------------

_monitor_ref = None

# Modifier key name -> NSEvent modifier flag
_MOD_MAP = None


def _get_mod_map():
    global _MOD_MAP
    if _MOD_MAP is None:
        from Cocoa import (
            NSCommandKeyMask, NSShiftKeyMask,
            NSControlKeyMask, NSAlternateKeyMask,
        )
        _MOD_MAP = {
            "cmd": NSCommandKeyMask, "command": NSCommandKeyMask,
            "shift": NSShiftKeyMask,
            "ctrl": NSControlKeyMask, "control": NSControlKeyMask,
            "alt": NSAlternateKeyMask, "option": NSAlternateKeyMask,
        }
    return _MOD_MAP


def _modifier_mask(modifiers):
    mod_map = _get_mod_map()
    mask = 0
    for m in modifiers:
        mask |= mod_map.get(m.lower(), 0)
    return mask


# macOS virtual keycodes
_KEYCODE_TABLE = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04,
    "g": 0x05, "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09,
    "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14,
    "4": 0x15, "6": 0x16, "5": 0x17, "9": 0x19, "7": 0x1A,
    "8": 0x1C, "0": 0x1D, "o": 0x1F, "u": 0x20, "i": 0x22,
    "p": 0x23, "l": 0x25, "j": 0x26, "k": 0x28, "n": 0x2D,
    "m": 0x2E,
}

# Mask to isolate modifier flags (strip device-dependent bits)
_MODIFIER_FLAGS_MASK = 0xFFFF0000 & ~0x100


def register_hotkey(config, callback):
    """Register a global hotkey monitor. Requires Accessibility permission."""
    global _monitor_ref
    unregister_hotkey()

    from Cocoa import NSEvent, NSKeyDownMask

    target_mask = _modifier_mask(config["hotkey_modifiers"])
    target_keycode = _KEYCODE_TABLE.get(config["hotkey_key"].lower())
    if target_keycode is None:
        print(f"Warning: unknown hotkey character '{config['hotkey_key']}'")
        return

    def handler(event):
        mods = event.modifierFlags() & _MODIFIER_FLAGS_MASK
        if (event.keyCode() == target_keycode
                and mods == (target_mask & _MODIFIER_FLAGS_MASK)):
            wx.CallAfter(callback)

    _monitor_ref = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
        NSKeyDownMask, handler
    )


def unregister_hotkey():
    global _monitor_ref
    if _monitor_ref is not None:
        from Cocoa import NSEvent
        NSEvent.removeMonitor_(_monitor_ref)
        _monitor_ref = None


# ---------------------------------------------------------------------------
# Hotkey format helpers
# ---------------------------------------------------------------------------

_MOD_SYMBOLS = {
    "ctrl": "\u2303", "control": "\u2303",
    "shift": "\u21E7",
    "alt": "\u2325", "option": "\u2325",
    "cmd": "\u2318", "command": "\u2318",
}


def format_hotkey(config):
    parts = [_MOD_SYMBOLS.get(m.lower(), m) for m in config["hotkey_modifiers"]]
    parts.append(config["hotkey_key"].upper())
    return "".join(parts)


# ---------------------------------------------------------------------------
# Setup wizard
# ---------------------------------------------------------------------------

class SetupWizard(wx.Dialog):
    """First-run setup wizard."""

    def __init__(self, parent):
        super().__init__(parent, title="scheMAGIC Setup",
                         style=wx.DEFAULT_DIALOG_STYLE, size=(480, 380))
        self.config = dict(DEFAULT_CONFIG)
        self._build_ui()
        self.CenterOnScreen()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="Welcome to scheMAGIC")
        title.SetFont(title.GetFont().MakeLarger().MakeLarger().Bold())
        sizer.Add(title, 0, wx.ALL, 15)

        sizer.Add(wx.StaticText(panel, label=(
            "scheMAGIC lets you search datasheets and create KiCad symbols\n"
            "from anywhere with a single keystroke."
        )), 0, wx.LEFT | wx.RIGHT, 15)
        sizer.AddSpacer(15)

        # Checks
        checks_sizer = wx.FlexGridSizer(cols=2, hgap=8, vgap=6)

        kicad_ok = os.path.isdir("/Applications/KiCad/KiCad.app")
        checks_sizer.Add(wx.StaticText(panel,
            label="\u2705 KiCad 8 Found" if kicad_ok else "\u274C KiCad 8 Not Found"))
        checks_sizer.AddSpacer(0)

        try:
            import pdfplumber
            pdf_ok = True
        except ImportError:
            pdf_ok = False
        checks_sizer.Add(wx.StaticText(panel,
            label="\u2705 pdfplumber Installed" if pdf_ok else "\u274C pdfplumber Missing"))
        checks_sizer.AddSpacer(0)

        sizer.Add(checks_sizer, 0, wx.LEFT | wx.RIGHT, 15)
        sizer.AddSpacer(15)

        # Hotkey
        hk_sizer = wx.BoxSizer(wx.HORIZONTAL)
        hk_sizer.Add(wx.StaticText(panel, label="Global hotkey:"), 0,
                      wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self._hotkey_label = wx.StaticText(panel,
            label=format_hotkey(self.config))
        self._hotkey_label.SetFont(self._hotkey_label.GetFont().Bold())
        hk_sizer.Add(self._hotkey_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        change_btn = wx.Button(panel, label="Change...")
        change_btn.Bind(wx.EVT_BUTTON, self._on_change_hotkey)
        hk_sizer.Add(change_btn, 0)
        sizer.Add(hk_sizer, 0, wx.LEFT | wx.RIGHT, 15)
        sizer.AddSpacer(10)

        # Login item
        self._login_cb = wx.CheckBox(panel, label="Start scheMAGIC at login")
        self._login_cb.SetValue(True)
        self.config["start_at_login"] = True
        sizer.Add(self._login_cb, 0, wx.LEFT | wx.RIGHT, 15)
        sizer.AddSpacer(20)

        # Get Started button
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        go_btn = wx.Button(panel, wx.ID_OK, "Get Started")
        go_btn.SetDefault()
        btn_sizer.Add(go_btn, 0, wx.RIGHT, 15)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.BOTTOM, 15)

        panel.SetSizer(sizer)
        go_btn.Bind(wx.EVT_BUTTON, self._on_go)

    def _on_change_hotkey(self, event):
        dlg = HotkeyDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.config["hotkey_modifiers"] = dlg.modifiers
            self.config["hotkey_key"] = dlg.key
            self._hotkey_label.SetLabel(format_hotkey(self.config))
        dlg.Destroy()

    def _on_go(self, event):
        self.config["start_at_login"] = self._login_cb.GetValue()
        self.EndModal(wx.ID_OK)


# ---------------------------------------------------------------------------
# Hotkey capture dialog
# ---------------------------------------------------------------------------

class HotkeyDialog(wx.Dialog):
    """Captures a key combination from the user."""

    def __init__(self, parent):
        super().__init__(parent, title="Set Hotkey",
                         style=wx.DEFAULT_DIALOG_STYLE, size=(350, 160))
        self.modifiers = []
        self.key = ""
        self._build_ui()
        self.CenterOnParent()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(15)
        sizer.Add(wx.StaticText(panel,
            label="Press your desired key combination:"),
            0, wx.LEFT | wx.RIGHT, 15)
        sizer.AddSpacer(10)
        self._display = wx.StaticText(panel, label="Waiting...")
        self._display.SetFont(self._display.GetFont().MakeLarger().Bold())
        sizer.Add(self._display, 0, wx.LEFT | wx.RIGHT, 15)
        sizer.AddSpacer(10)
        self._hint = wx.StaticText(panel,
            label="Use at least one modifier (Ctrl/Shift/Cmd/Option) + a key")
        self._hint.SetForegroundColour(wx.Colour(128, 128, 128))
        sizer.Add(self._hint, 0, wx.LEFT | wx.RIGHT, 15)
        panel.SetSizer(sizer)

        panel.Bind(wx.EVT_KEY_DOWN, self._on_key)
        panel.SetFocus()

    def _on_key(self, event):
        mods = []
        raw = event.GetModifiers()
        if raw & wx.MOD_CONTROL:
            mods.append("ctrl")
        if raw & wx.MOD_SHIFT:
            mods.append("shift")
        if raw & wx.MOD_ALT:
            mods.append("alt")
        if raw & wx.MOD_META:
            mods.append("cmd")

        keycode = event.GetKeyCode()
        # Only accept printable characters
        if 32 < keycode < 127 and mods:
            char = chr(keycode).lower()
            self.modifiers = mods
            self.key = char
            cfg = {"hotkey_modifiers": mods, "hotkey_key": char}
            self._display.SetLabel(format_hotkey(cfg))
            self._hint.SetLabel("Got it!")
            # Auto-close after brief delay
            wx.CallLater(600, lambda: self.EndModal(wx.ID_OK))
        elif not mods:
            self._hint.SetLabel("Add a modifier key (Ctrl/Shift/Cmd/Option)")
        event.Skip()


# ---------------------------------------------------------------------------
# Menubar icon
# ---------------------------------------------------------------------------

class SchemagicTaskBarIcon(wx.adv.TaskBarIcon):
    """Persistent menubar icon."""

    TBMENU_OPEN = wx.NewIdRef()
    TBMENU_PREFS = wx.NewIdRef()
    TBMENU_QUIT = wx.NewIdRef()

    def __init__(self, frame):
        super().__init__()
        self._frame = frame

        # Use a simple text icon (the 24x24 PNG is too small for retina)
        icon = wx.Icon()
        bmp = wx.Bitmap(24, 24, 32)
        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0, 0)))
        dc.Clear()
        dc.SetTextForeground(wx.BLACK)
        font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                       wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)
        dc.DrawText("sM", 2, 2)
        dc.SelectObject(wx.NullBitmap)
        icon.CopyFromBitmap(bmp)
        self.SetIcon(icon, "scheMAGIC")

        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, lambda e: self.on_open())

    def CreatePopupMenu(self):
        menu = wx.Menu()
        menu.Append(self.TBMENU_OPEN, "Open scheMAGIC")
        menu.AppendSeparator()
        menu.Append(self.TBMENU_PREFS, "Preferences...")
        menu.AppendSeparator()
        menu.Append(self.TBMENU_QUIT, "Quit")
        self.Bind(wx.EVT_MENU, lambda e: self.on_open(), id=self.TBMENU_OPEN)
        self.Bind(wx.EVT_MENU, self._on_prefs, id=self.TBMENU_PREFS)
        self.Bind(wx.EVT_MENU, self._on_quit, id=self.TBMENU_QUIT)
        return menu

    def on_open(self):
        """Open the main dialog with auto-detected project."""
        project_dir = detect_kicad_project()
        auto_detected = project_dir is not None
        dlg = MainDialog(None, project_dir=project_dir,
                         auto_detected=auto_detected)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_prefs(self, event):
        cfg = load_config()
        dlg = HotkeyDialog(None)
        if dlg.ShowModal() == wx.ID_OK:
            cfg["hotkey_modifiers"] = dlg.modifiers
            cfg["hotkey_key"] = dlg.key
            save_config(cfg)
            register_hotkey(cfg, self.on_open)
        dlg.Destroy()

    def _on_quit(self, event):
        unregister_hotkey()
        self.RemoveIcon()
        self._frame.Close()
        wx.GetApp().ExitMainLoop()


# ---------------------------------------------------------------------------
# Login item helper
# ---------------------------------------------------------------------------

def _setup_login_item():
    """Add scheMAGIC to Login Items via osascript."""
    # Get the path to this script to use as the login item
    app_path = os.path.abspath(__file__)
    script = (
        f'tell application "System Events" to make login item at end '
        f'with properties {{path:"{app_path}", hidden:false}}'
    )
    os.system(f"osascript -e '{script}' 2>/dev/null")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class SchemagicApp(wx.App):
    def OnInit(self):
        # Hidden frame to keep the app alive
        self.frame = wx.Frame(None, style=0)

        # First-run setup
        if not os.path.isfile(FIRST_RUN_SENTINEL):
            wizard = SetupWizard(None)
            if wizard.ShowModal() == wx.ID_OK:
                save_config(wizard.config)
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(FIRST_RUN_SENTINEL, "w") as f:
                    f.write("done\n")
                if wizard.config.get("start_at_login"):
                    _setup_login_item()
            else:
                wizard.Destroy()
                return False
            wizard.Destroy()

        cfg = load_config()
        self.tray = SchemagicTaskBarIcon(self.frame)
        register_hotkey(cfg, self.tray.on_open)
        return True


def main():
    app = SchemagicApp()
    app.MainLoop()


if __name__ == "__main__":
    main()
