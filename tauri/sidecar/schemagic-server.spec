# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the scheMAGIC FastAPI sidecar.

Bundles server/ + engine/ into a single executable that Tauri launches
as a sidecar process. The binary listens on a random port and prints
SCHEMAGIC_PORT:{port} to stdout for the Tauri shell to read.

Build:
    pyinstaller tauri/sidecar/schemagic-server.spec \
        --distpath tauri/sidecar \
        --workpath /tmp/schemagic-pyinstaller \
        --noconfirm
"""

import os
import sys

# SPECPATH = tauri/sidecar/, go up 2 levels to reach repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPECPATH)))

a = Analysis(
    [os.path.join(REPO_ROOT, "server", "main.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Engine modules
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
        # Server modules
        "server",
        "server.job_store",
        "server.schemas",
        "server.routes",
        "server.routes.pipeline",
        "server.routes.files",
        "server.routes.library",
        "server.routes.kicad_project",
        # Rendering module (shared between server and Tauri)
        "engine.rendering",
        "engine.rendering.kicad_lib_parser",
        "engine.rendering.kicad_render_data",
        # PDF parsing
        "pdfplumber",
        "pdfminer",
        "pdfminer.high_level",
        "pdfminer.layout",
        "pdfminer.utils",
        "pdfminer.pdfinterp",
        "pdfminer.converter",
        "pdfminer.pdfdocument",
        "pdfminer.pdfparser",
        "pdfminer.pdfpage",
        "pdfminer.pdftypes",
        "pdfminer.psparser",
        "pdfminer.cmapdb",
        "charset_normalizer",
        # FastAPI + ASGI
        "fastapi",
        "fastapi.middleware",
        "fastapi.middleware.cors",
        "starlette",
        "starlette.middleware",
        "starlette.middleware.cors",
        "starlette.responses",
        "starlette.routing",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # Async
        "anyio",
        "anyio._backends",
        "anyio._backends._asyncio",
        # Pydantic
        "pydantic",
        "pydantic.deprecated",
        "pydantic.deprecated.decorator",
        # SSL certs (optional, for AI API calls)
        "certifi",
        # Multipart form parsing
        "python_multipart",
    ],
    excludes=[
        "wx",
        "wxPython",
        "pyobjc",
        "pyobjc_framework_Cocoa",
        "Cocoa",
        "Quartz",
        "objc",
        "py2app",
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "PIL",
        "test",
        "unittest",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="schemagic-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    target_arch=None,
)
