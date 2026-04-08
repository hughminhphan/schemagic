"""py2app build configuration for scheMAGIC.

Usage:
    Build from the repo root:
        python plugin/build_dmg.py
"""

import os
import sys

from setuptools import setup

# Add repo root so engine/ and plugin/ are importable
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

APP = ["plugin/app.py"]

DATA_FILES = []

SCHEMAGIC_MODULES = [
    "engine",
    "engine.core",
    "engine.core.config",
    "engine.core.models",
    "engine.core.pipeline",
    "engine.core.project_detector",
    "engine.core.user_config",
    "engine.datasheet",
    "engine.datasheet.fetcher",
    "engine.datasheet.parser",
    "engine.datasheet.pin_extractor",
    "engine.datasheet.package_identifier",
    "engine.datasheet.ai_extractor",
    "engine.matching",
    "engine.matching.library_index",
    "engine.matching.symbol_matcher",
    "engine.matching.footprint_matcher",
    "engine.generation",
    "engine.generation.sexpr",
    "engine.generation.symbol_modifier",
    "engine.generation.footprint_modifier",
    "engine.generation.library_manager",
    "plugin",
    "plugin.ui",
    "plugin.ui.main_dialog",
    "plugin.ui.pin_review_dialog",
    "plugin.ui.pin_edit_bar",
    "plugin.ui.footprint_panel",
    "plugin.ui.symbol_panel",
    "plugin.ui.kicad_lib_parser",
    "plugin.ui.kicad_render_data",
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "plugin/icon.icns",
    "plist": {
        "CFBundleName": "scheMAGIC",
        "CFBundleDisplayName": "scheMAGIC",
        "CFBundleIdentifier": "com.schemagic.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    },
    "includes": SCHEMAGIC_MODULES + [
        "wx", "wx.adv", "wx.grid",
        "objc", "Cocoa", "Quartz",
        "pdfplumber",
        "json", "threading", "traceback",
    ],
    "excludes": [
        "fastapi", "uvicorn", "starlette",
    ],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
