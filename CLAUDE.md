# scheMAGIC

Paste a datasheet PDF, get a perfect KiCad symbol + footprint. $5 AUD/month.

## Architecture

Three folders, three concerns:

```
schemagic/
├── engine/      # Core pipeline (shared by plugin + server)
├── plugin/      # macOS menubar app - THE PRODUCT ($5/month)
├── server/      # FastAPI API - powers the webapp demo only
└── web/         # Next.js landing page + one-free-try demo
```

**The plugin is the product.** The webapp is just a demo that lets people try it once before downloading. All development effort goes into `engine/` and `plugin/`.

## Which folder to edit

| Task | Folder |
|------|--------|
| Fix parsing, extraction, generation | `engine/` |
| Fix the app UI, hotkey, menubar | `plugin/` |
| Fix the demo API | `server/` |
| Fix the landing page or demo frontend | `web/` |

## Engine structure

```
engine/
├── core/pipeline.py          # 2-phase orchestrator (run -> select_package_and_finish)
├── core/models.py            # PinInfo, PackageInfo, DatasheetData, MatchResult, GeneratedComponent
├── core/config.py            # Paths, PACKAGE_MAP (200+ entries), TI suffix tables
├── core/user_config.py       # User settings at ~/.schemagic/config.json
├── core/project_detector.py  # Auto-detect KiCad project directory
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
└── matching/footprint_matcher.py # Package-based footprint matching
```

## Running tests

```bash
# From repo root:
python -m pytest engine/tests/test_edge_cases.py -v    # 563 unit tests
python engine/tests/test_harness.py --strict            # 35/42 integration tests
```

## Running the demo locally

```bash
# Terminal 1: FastAPI backend
cd schemagic && uvicorn server.main:app --reload --port 8000

# Terminal 2: Next.js frontend
cd schemagic/web && npm run dev
```

## Running the menubar app

```bash
python plugin/app.py
```

## Building the .dmg

```bash
python plugin/build_dmg.py
```

## Critical gotchas

- No `uuid` in .kicad_sym library files (only for .kicad_sch)
- `version`/`generator_version` must be unquoted in S-expressions
- `extract_tables_and_text()` returns 3-tuple: (tables, text, pages)
- TI `-Q1` is automotive qualifier, NOT a package suffix
- pin_extractor.py is the most complex module - read it fully before editing

## What NOT to do

- Don't add ERC/electrical rule checking - it was removed intentionally
- Don't add KiCad ActionPlugin registration - the app is menubar-only
- Don't add wxPython standalone launcher - replaced by menubar app
- Don't reference `ds2kicad` anywhere - the project is scheMAGIC
- Don't edit `engine/` imports to absolute - they use relative `..` imports within the package

## Environment variable

Set `SCHEMAGIC_STANDALONE=1` when running outside KiCad to prevent pcbnew import attempts.
