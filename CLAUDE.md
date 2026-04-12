# scheMAGIC

Type a part number, get a perfect KiCad symbol + footprint. $5 USD/month.

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
| Fix payments/licensing | `web/lib/stripe.ts`, `web/app/api/payments/`, `web/hooks/useLicense.ts` |

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
├── datasheet/pin_extractor.py # Table -> PinInfo (legacy, used by unit tests only)
├── datasheet/package_identifier.py # Regex package detection (legacy, used by unit tests only)
├── datasheet/ai_extractor.py # Gemini-only extraction (mandatory, no fallback)
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

## Testing after code changes

**Always build and install the real app. Never use `npm run dev` or `cargo run` for testing.**

```bash
# Build everything and install to /Applications:
./scripts/build-and-install.sh
```

This rebuilds the sidecar, frontend, and Tauri app, then installs to `/Applications/scheMAGIC.app`. Open it from Spotlight or Finder to test like a real user.

**Claude Code: after finishing any code changes to engine/, server/, web/, or tauri/, run `./scripts/build-and-install.sh` automatically before testing. Never start a localhost dev server for testing.**

### Dev mode (only for rapid Rust iteration)

If iterating purely on Tauri Rust code (not engine/server/web):
```bash
mkdir -p tauri/target/debug/binaries
ln -sf "$(pwd)/tauri/sidecar/schemagic-server-aarch64-apple-darwin" tauri/target/debug/binaries/
cd web && npm run build && cd ..
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

Note: `output: "export"` is now conditional via `STATIC_EXPORT=1` env var. Dev mode works without it. The static export config is for Tauri only.

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
- Don't use `npm run dev` or localhost for testing - always build and install the real .app
- Don't use `cargo run` for testing unless purely iterating on Rust code
- Don't use PlatformIO Python for PyInstaller builds - needs Homebrew framework Python

## Payments and licensing

Stripe subscription ($5 USD/month) with 3 free generations. RS256 JWT license tokens enforced at the sidecar layer.

### How it works

```
App launch -> LicenseGate reads email + cached JWT from Tauri config
  -> No email: show EmailPrompt
  -> Has email: POST /api/license/validate with email + machine_id
     -> Pro (active subscription): get 7-day JWT, cache locally
     -> Free tier (under limit): get single-use 5-min JWT per generation
     -> Over limit: show Paywall -> Stripe Checkout in browser
     -> Device mismatch: show error
  -> Sidecar validates X-License-Token header on /api/run, /api/select-package, /api/finalize
  -> Offline: cached pro JWT valid up to 7 days
```

### Key files

| File | Purpose |
|------|---------|
| `web/lib/stripe.ts` | Stripe client + business logic (server-side only) |
| `web/lib/license.ts` | RS256 JWT signing/verification (server-side) |
| `web/lib/payments-types.ts` | Shared TypeScript types (LicenseStatus, ValidateResponse) |
| `web/app/api/license/validate/route.ts` | Core endpoint: validate email + machine_id, issue JWT |
| `web/app/api/payments/checkout/route.ts` | Create Stripe Checkout session |
| `web/app/api/payments/portal/route.ts` | Create Stripe Customer Portal session |
| `web/app/api/payments/webhook/route.ts` | Handle Stripe webhook events (subscription lifecycle) |
| `web/app/api/payments/check/route.ts` | Legacy check endpoint (kept for backwards compat) |
| `web/app/activate/page.tsx` | Post-checkout landing page |
| `web/hooks/useLicense.ts` | React hook: license state, token acquisition, offline fallback |
| `web/components/app/LicenseGate.tsx` | Gate component wrapping the wizard |
| `web/components/app/LicenseContext.tsx` | React context (acquireToken for sidecar calls) |
| `web/lib/api-base.ts` | fetchWithLicense() injects X-License-Token header |
| `server/license.py` | Sidecar JWT validation with embedded public key |

### Anti-piracy enforcement

- Sidecar requires valid `X-License-Token` header on billable endpoints (403 without it)
- JWT signed with RS256 private key (Vercel only), public key embedded in sidecar binary
- Machine binding: UUID generated on first launch, stored in config, verified server-side
- Free tier: online-only (single-use 5-min tokens), no fail-open
- Pro tier: 7-day offline grace via JWT expiry

### Dual build modes

`next.config.ts` uses `STATIC_EXPORT=1` to toggle between:
- **Static export** (Tauri): no API routes, pure HTML/JS/CSS. `build-and-install.sh` sets this and temporarily moves `web/app/api/` out during build.
- **Server mode** (Vercel): API routes work, deployed at schemagic.design.

### Stripe data model

Stripe is the database. No external DB. Customer metadata stores: `free_generations` count, `machine_id` (device binding), `payment_failed` flag.

### Vercel env vars (production)

- `STRIPE_SECRET_KEY` - sk_test_... or sk_live_...
- `STRIPE_WEBHOOK_SECRET` - whsec_...
- `STRIPE_PRICE_ID` - price_...
- `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` - pk_test_... or pk_live_...
- `LICENSE_PRIVATE_KEY` - RS256 private key for JWT signing
- `LICENSE_PUBLIC_KEY` - RS256 public key for JWT verification

### User config additions

`~/.schemagic/config.json` includes: `email`, `license_status`, `last_check`, `license_token` (JWT), `machine_id` (UUID).

## Environment variables

- `SCHEMAGIC_STANDALONE=1` - prevents pcbnew import (set automatically by server)
- `SCHEMAGIC_SIDECAR=1` - triggers server startup + port signaling to Tauri
- `SCHEMAGIC_PORT=0` - pick random free port (or set to a fixed port number)
- `STATIC_EXPORT=1` - build web/ as static export for Tauri (omit for Vercel server mode)
