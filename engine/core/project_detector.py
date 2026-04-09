"""Auto-detect the active KiCad project directory from KiCad's config files."""

import json
import os
import sys


def _kicad_config_paths():
    """Return candidate paths for kicad.json in priority order."""
    paths = []
    if sys.platform == "darwin":
        paths.append(os.path.expanduser(
            "~/Library/Preferences/kicad/8.0/kicad.json"))
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            paths.append(os.path.join(appdata, "kicad", "8.0", "kicad.json"))
    # Linux / fallback
    paths.append(os.path.expanduser("~/.config/kicad/8.0/kicad.json"))
    return paths


def _read_kicad_json():
    """Read and parse the first available kicad.json config file."""
    for path in _kicad_config_paths():
        if os.path.isfile(path):
            with open(path, "r") as f:
                return json.load(f)
    return None


def _project_dir_from_path(project_path):
    """Extract and validate a project directory from a .kicad_pro path."""
    if not project_path.endswith(".kicad_pro"):
        return None
    d = os.path.dirname(project_path)
    if os.path.isdir(d):
        return d
    return None


def detect_kicad_project():
    """Detect the most relevant KiCad project directory.

    Strategy:
      1. Check ``system.open_projects`` (currently open in KiCad)
      2. Fall back to ``system.file_history[0]`` (most recently opened)

    Returns the project directory path, or ``None`` if nothing is found.
    """
    config = _read_kicad_json()
    if config is None:
        return None

    system = config.get("system", {})

    # Prefer currently open projects
    for path in system.get("open_projects", []):
        d = _project_dir_from_path(path)
        if d:
            return d

    # Fall back to file history
    for path in system.get("file_history", []):
        d = _project_dir_from_path(path)
        if d:
            return d

    return None
