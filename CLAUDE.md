# scheMAGIC

Paste a datasheet PDF, get a perfect KiCad symbol + footprint. $5 AUD/month.

## Architecture

```
schemagic/
├── engine/      # Core pipeline (shared by all frontends)
├── tauri/       # Tauri v2 desktop shell - THE PRODUCT ($5/month, macOS + Windows)
├── server/      # FastAPI API - runs as Tauri sidecar + powers webapp demo
├── web/         # React frontend (shared by Tauri desktop + Next.js demo site)
└── scripts/     # Build scripts for sidecar + CI
```

**Tauri desktop app is the product.** schemagic.design is the landing/marketing page only (no webapp demo). The Tauri shell launches the FastAPI server as a PyInstaller sidecar binary, and the web/ React frontend runs in the Tauri webview as static HTML/JS/CSS. The wizard UI lives at `/app/` (Tauri loads this via `url: "app/index.html"` in tauri.conf.json). The root `/` is the landing page.

### How the Tauri app works

```
Tauri (Rust)                          Sidecar (Python)
  |                                      |
  |-- spawns PyInstaller binary -------->|
  |                                      |-- starts FastAPI on random port
  |<--- stdout: SCHEMAGIC_PORT:XXXXX ----|
  |                                      |
  |-- injects port into webview          |
  |                                      |
  Webview (React from web/out/)          |
    |-- fetch(http://127.0.0.1:XXXXX) -->|
    |<-- JSON responses ------------------|
```

Key files:
- `tauri/src/main.rs` - app lifecycle, tray icon, global shortcut, config commands
- `tauri/src/sidecar.rs` - spawn sidecar, read port from stdout, path resolution
- `tauri/tauri.conf.json` - Tauri config (bundle, window, CSP, externalBin)
- `tauri/capabilities/default.json` - permissions (sidecar, shortcuts, fs, autostart)
- `web/lib/api-base.ts` - dynamic port-aware API base URL (Tauri injects port via window.__SCHEMAGIC_API_PORT__)

## Which folder to edit

| Task | Folder |
|------|--------|
| Fix parsing, extraction, generation | `engine/` |
| Fix the desktop app shell, tray, hotkey | `tauri/` |
| Fix the API endpoints | `server/` |
| Fix the UI (desktop + web) | `web/` |

## Engine structure

```
engine/
├── core/pipeline.py          # 2-phase orchestrator (run -> select_package_and_finish)
├── core/models.py            # PinInfo, PackageInfo, DatasheetData, MatchResult, GeneratedComponent
├── core/config.py            # Paths, PACKAGE_MAP (200+ entries), TI suffix tables
├── core/user_config.py       # User settings at ~/.schemagic/config.json
├── core/project_detector.py  # Auto-detect KiCad project directory (macOS + Windows + Linux)
├── datasheet/fetcher.py      # PDF download (3 strategies: manufacturer URL, TI, DuckDuckGo)
├── datasheet/parser.py       # pdfplumber table/text extraction
├── datasheet/pin_extractor.py # Table -> PinInfo (most complex module, 450+ lines)
├── datasheet/package_identifier.py # 50+ regex patterns for package detection
├── datasheet/ai_extractor.py # LLM-assisted extraction (Gemini)
├── generation/sexpr.py       # S-expression parser/serializer for KiCad files
├── generation/symbol_modifier.py # Clone or create symbols from scratch
├── generation/footprint_modifier.py # Copy/rename footprints
├── generation/library_manager.py # Save to project (schemagic.kicad_sym + schemagic.pretty/)
├── matching/library_index.py # KiCad lib scanner (~21,700 symbols, ~14,200 footprints)
├── matching/symbol_matcher.py # 5-strategy symbol matching cascade
├── matching/footprint_matcher.py # Package-based footprint matching
├── rendering/kicad_lib_parser.py # Parse .kicad_sym/.kicad_mod to render data (shared with web)
└── rendering/kicad_render_data.py # Dataclasses for render payloads
```

## Running tests

```bash
# From repo root:
python -m pytest engine/tests/test_edge_cases.py -v    # unit tests
python engine/tests/test_harness.py --strict            # integration tests
```

## Running the desktop app (dev)

```bash
# 1. Build the sidecar (first time only, or after engine/server changes):
./scripts/build-sidecar-macos.sh

# 2. Symlink sidecar for dev mode:
mkdir -p tauri/target/debug/binaries
ln -sf "$(pwd)/tauri/sidecar/schemagic-server-aarch64-apple-darwin" tauri/target/debug/binaries/

# 3. Build the frontend:
cd web && npm run build && cd ..

# 4. Run:
cd tauri && cargo run
```

Note: `cp` corrupts PyInstaller ad-hoc signatures on macOS. Always use symlinks for dev, not copies.

## Running the landing page locally

```bash
cd web && npm run dev
```

The landing page at `/` is static and doesn't need the backend. To test the wizard UI at `/app/`, also run the FastAPI backend:

```bash
# Terminal 1: FastAPI backend
python server/main.py

# Terminal 2: Next.js frontend
cd web && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Note: dev mode needs `output: "export"` removed from next.config.ts to use the dev server with rewrites. The static export config is for Tauri only.

## Building for distribution

```bash
./scripts/build-sidecar-macos.sh
cd web && npm run build && cd ..
cd tauri && cargo tauri build
# Output: tauri/target/release/bundle/dmg/scheMAGIC_*.dmg
```

## Sidecar details

- Entry point: `server/main.py` (triggered by `SCHEMAGIC_SIDECAR=1` env var)
- Port: random (env `SCHEMAGIC_PORT=0`), printed to stdout as `SCHEMAGIC_PORT:{port}`
- Build: PyInstaller spec at `tauri/sidecar/schemagic-server.spec`
- Build script: `scripts/build-sidecar-macos.sh` (uses Homebrew Python venv, not PlatformIO)
- Output: `tauri/sidecar/schemagic-server-{target-triple}` (~27MB)
- Cold start: ~6s (PyInstaller extraction), warm: <1s

## Critical gotchas

- No `uuid` in .kicad_sym library files (only for .kicad_sch)
- `version`/`generator_version` must be unquoted in S-expressions
- `extract_tables_and_text()` returns 3-tuple: (tables, text, pages)
- TI `-Q1` is automotive qualifier, NOT a package suffix
- pin_extractor.py is the most complex module - read it fully before editing
- PyInstaller binaries cannot be `cp`'d on macOS (breaks ad-hoc signature) - use symlinks
- web/ fetch calls must use `apiBase()` from `web/lib/api-base.ts`, never hardcoded paths

## What NOT to do

- Don't add ERC/electrical rule checking - it was removed intentionally
- Don't add KiCad ActionPlugin registration - the app is a Tauri desktop app
- Don't reference `ds2kicad` anywhere - the project is scheMAGIC
- Don't edit `engine/` imports to absolute - they use relative `..` imports within the package
- Don't hardcode API URLs in web/ - use `apiBase()` from `web/lib/api-base.ts`
- Don't use PlatformIO Python for PyInstaller builds - needs Homebrew framework Python

## Environment variables

- `SCHEMAGIC_STANDALONE=1` - prevents pcbnew import (set automatically by server)
- `SCHEMAGIC_SIDECAR=1` - triggers server startup + port signaling to Tauri
- `SCHEMAGIC_PORT=0` - pick random free port (or set to a fixed port number)
