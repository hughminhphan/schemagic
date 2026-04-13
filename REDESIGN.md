# scheMAGIC Redesign — Handoff to Claude Code

> Source of truth: [Figma file](https://www.figma.com/design/eN8rsXUyx5rNaS7aLJAymh/scheMAGIC-App-UI-UX)
> File key: `eN8rsXUyx5rNaS7aLJAymh`
> Target app: `~/Documents/schemagic/web/` (Next.js 16, React 19, Tailwind v4)
> Shell: `~/Documents/schemagic/tauri/` (Tauri v2, don't touch unless routing changes require capability updates)

---

## 1. Design Tokens (from Figma "Design System" page, node `0:1`)

Claude: extract these to `web/app/globals.css` as CSS custom properties AND mirror in Tailwind v4 `@theme` block. Do this in Phase 1 before any page work.

### Colors (dark theme — confirm default)
| Token | Hex | Usage |
|---|---|---|
| `--surface` | `#0A0A0A` | page background |
| `--surface-raised` | `#111111` | cards, panels |
| `--border` | `#1A1A1A` | dividers, input borders |
| `--text-primary` | `#FFFFFF` | headings, body |
| `--text-secondary` | `#888888` | muted, meta |
| `--accent` | `#FF2D78` | primary CTA, brand |
| `--accent-hover` | `#FF4D91` | CTA hover |
| `--success` | `#4ADE80` | completion, validation |
| `--viewer-symbol-bg` | `#0A0A0A` | KiCad symbol preview bg |
| `--viewer-footprint-bg` | `#001023` | KiCad footprint preview bg |
| `--viewer-pin-line` | `#CC3333` | pin lines in viewer |
| `--viewer-pin-name` | `#00CCCC` | pin name label |
| `--viewer-pin-number` | `#CC4444` | pin number label |

### Typography
- **Headings:** Space Grotesk Bold, H1 = 30px
- **Body:** Space Grotesk Regular, 14px
- **Mono label:** JetBrains Mono, 12px
- **Mono xs:** JetBrains Mono, 10px (used for terminal/status lines)

### Spacing scale
`8 · 12 · 16 · 24 · 48 · 96` — map to Tailwind spacing (should already align except 96 ≈ `space-24`).

### ⚠️ Brand check for Hugh
This palette is dark + hot pink (#FF2D78) + Space Grotesk. That matches Hugh's **personal/Robonyx** brand tokens, not the Lyra brand. Confirm scheMAGIC is intentionally adopting the Robonyx look (not Lyra purple). If yes, update `Memories/schemagic.md` with canonical brand tokens.

---

## 2. Screen Mapping

Each screen already has an `__annotation__` frame in Figma with STATES / GATE / CTA / EDGE notes — Claude should read these via `get_design_context` for behavior.

| # | Figma screen | Figma nodeId | Current code location | New route | Status | Notes |
|---|---|---|---|---|---|---|
| 1 | Loading | `78:2` | (none — inline) | `/app` initial | NEW | Auto-routes in <1s. Non-interactive. Public gate. |
| 2 | Auth/Email | `78:3` | `components/app/EmailPrompt.tsx` (inline in `/app`) | `/auth/email` | NEW ROUTE | Magic link flow. Public. Redirect to `/wizard/idle` if authed. |
| 3 | Auth/Paywall | `78:4` | `components/app/Paywall.tsx` (inline in `/app`) | `/auth/paywall` | NEW ROUTE | Stripe Checkout. Gate: authed + no sub. Success → `/wizard/idle`. |
| 4 | Wizard/Idle | `78:5` | `components/app/PartInput.tsx` in `app/app/page.tsx` | `/wizard/idle` | MOVE + REDESIGN | Replaces current `/app`. Gate: authed + paid. |
| 5 | Wizard/Running | `78:6` | `components/app/StatusStream.tsx` | `/wizard/running` | MOVE + REDESIGN | SSE status lines. Auto → `/wizard/package-select` on complete. |
| 6 | Wizard/Running-Error | `294:2` | (inline error state) | `/wizard/running` (error view) | NEW STATE | Terminal error. Retry from last checkpoint. Report → feedback form. |
| 7 | Wizard/Package-Select | `78:7` | `components/app/PackageSelectPanel.tsx` | `/wizard/package-select` | MOVE + REDESIGN | 1–6 candidates. Skip if N=1. |
| 8 | Wizard/Pin-Review | `78:8` | `components/app/PinReviewTable.tsx` + `PinEditPanel.tsx` + `PinReviewVisual.tsx` | `/wizard/pin-review` | MOVE + REDESIGN | Editable table + live preview. Warn on unsaved back. |
| 9 | Settings | `110:105` | (none) | `/settings` | NEW ROUTE | Tabs: Account · Billing · Preferences. Billing → Stripe portal. |

### Routes to DELETE
| Current route | Why | Action |
|---|---|---|
| `/activate` (`app/activate/page.tsx`) | Out of scope — Stripe post-checkout redirect, not Tauri UI | KEEP unchanged |
| `/app` (`app/app/page.tsx`) as catch-all state machine | Being split into discrete wizard routes | Replace with redirect to `/wizard/idle` (or `/auth/email` if unauthed) |

### Routes to KEEP (don't touch)
- `/` (marketing landing) — OUT OF SCOPE. Do not modify.
- `/activate` — OUT OF SCOPE (Stripe post-checkout redirect page, not Tauri). Do not modify.
- All `app/api/**` routes — untouched unless endpoint contract changes.

---

## 3. Component Strategy

### Reusable primitives to extract first (Phase 2)
Claude: before rebuilding pages, pull these from the Figma design system node and build them once in `web/components/ui/`:
- `Button` (accent + secondary variants, hover state `--accent-hover`)
- `Input` (with mono label pattern)
- `Card` / `Panel` (surface-raised with border)
- `TerminalLine` (JetBrains Mono 10px, `> text` pattern for status stream)
- `Tabs` (for Settings)
- `Badge` (free tier / pro / error)

### Existing components — keep, replace, or absorb
| Component | Plan |
|---|---|
| `SymbolViewer.tsx` | KEEP logic, restyle shell only. Viewer colors now come from `--viewer-*` tokens. |
| `FootprintViewer.tsx` | Same — keep KiCad rendering, restyle container. |
| `WizardProvider.tsx` | KEEP. Now drives route transitions instead of inline state swaps. |
| `LicenseContext.tsx` / `useLicense.ts` | KEEP. Powers route gates. |
| `EmailPrompt.tsx` | Extract into `/auth/email/page.tsx`. |
| `Paywall.tsx` | Extract into `/auth/paywall/page.tsx`. |
| `Nav.tsx`, `Hero.tsx`, `Features.tsx`, `Pricing.tsx`, `HowItWorks.tsx`, `DownloadCTA.tsx`, `DownloadButtons.tsx` | Marketing landing — OUT OF SCOPE. Do not modify. |

---

## 4. Phased Execution Plan

Each phase = one Claude pass. Don't start Phase N+1 until N is verified in the Tauri app.

- **Phase 1 — Tokens.** ✅ Done (2026-04-13). Tokens + fonts live in `web/app/globals.css` under `@theme inline`.
- **Phase 2 — Primitives.** ✅ Done (2026-04-13). `Button`, `Input`, `Card` (+ `CardRow`), `TerminalLine` (+ `TerminalBlock`), `Tabs` (+ `TabsList`/`Trigger`/`Panel`), `Badge` in `web/components/ui/`. Barrel at `web/components/ui/index.ts`. Local `cn` helper, no new deps.
- **Phase 3 — Route scaffolding.** ✅ Done (2026-04-13). See section 7 below for scaffolded routes.
- **Phase 4 — Wizard screens** (Idle → Running → Package-Select → Pin-Review → Error). ✅ Done (2026-04-13). All 4 wizard routes wired to the real pipeline. `web/app/wizard/layout.tsx` mounts `WizardProvider` at the segment level so routes share reducer state. `/wizard/running` runs `/api/run` + SSE on mount and auto-navigates on `COMPLETE`. Zero-pin `COMPLETE` is intercepted and dispatched as `ERROR` (not a custom empty-state page). Error view renders the full message in an accent-bordered card below the scrollable `TerminalBlock`. Auto-minimise uses `useRef` (not `useState`) to avoid the effect-cleanup cancelling the 1.5s timer. Old components (`PartInput`, `StatusStream`, `PackageSelectPanel`, `PinReviewVisual`, `DownloadPanel`) now orphaned — Phase 6 cleanup. Tauri minimise call uses `import("@tauri-apps/api/window").then(m => m.getCurrentWindow().minimize())`.
  - **Known build quirk on this machine**: `./scripts/build-and-install.sh` passes Step 3a (bundling `.app`) but fails Step 3b (DMG) with `hdiutil: create failed - image not recognised`. The install step is gated on the DMG succeeding. Workaround: `trash /Applications/scheMAGIC.app && cp -R tauri/target/release/bundle/macos/scheMAGIC.app /Applications/`. The script should be patched to skip DMG when installing locally (optional cleanup).
- **Phase 5 — Auth + Settings.** Two sub-phases. **Decision (2026-04-13): use deep-link (`schemagic://auth?token=...`), not httpOnly cookies** — the Tauri shell ships as `STATIC_EXPORT=1` with no API routes, so cookies set on `schemagic.design` don't exist inside the Tauri webview. Deep link hands the identity JWT back into the app. Matches the REDESIGN "no DB, sign with `AUTH_SECRET`" constraint.
  - **5a — Magic-link backend + deep link plumbing.**
    1. **Rust / Tauri side** (`tauri/`):
       - Add `tauri-plugin-deep-link = "2"` to `Cargo.toml`.
       - Register `.plugin(tauri_plugin_deep_link::init())` in `main.rs`.
       - In `tauri.conf.json` `bundle.macOS`, add `"deepLinkAssociations": ["schemagic"]` (or the v2 equivalent — verify against plugin docs). For Windows, the plugin's NSIS fragment handles registry.
       - Capability file: add `deep-link:default` or specific permissions.
       - Rust handler: on `on_deep_link` event, parse `token` from URL, persist to `~/.schemagic/config.json` as `identity_token`, emit `deep-link-auth` event to webview.
       - Handle single-instance gracefully (existing app should come forward on link click).
    2. **Next.js / Vercel side** (`web/app/api/`):
       - `POST /api/auth/request` — body `{ email }`. Sign JWT `{ email, exp: now+15min, typ: "request" }` with `AUTH_SECRET`. Send Resend email containing `https://schemagic.design/auth/verify?token=<jwt>`. Return `{ ok: true }`.
       - `GET /auth/verify` (page, not API) — reads `?token=` query, validates with `AUTH_SECRET`, rejects expired. On success, sign a longer-lived identity JWT `{ email, exp: now+30d, typ: "identity" }` and 302 to `schemagic://auth?token=<identity_jwt>`. Render a "You can close this tab" page as fallback if the scheme handler didn't fire.
       - `POST /api/auth/logout` — no-op server-side (stateless JWT). Client clears `identity_token` from Tauri config.
       - Install `resend` npm package. Add `RESEND_API_KEY` + `AUTH_SECRET` to Vercel env.
    3. **Web shell** (`web/hooks/useLicense.ts` + `web/components/app/LicenseContext.tsx`):
       - Replace the current `email` identifier with an `identity_token` JWT stored in Tauri config.
       - On mount: read `identity_token` from `read_config`. If present, decode (client-side, trust the sidecar to re-validate on each license call) to get `email`. Continue the existing `/api/license/validate` flow.
       - Listen for `deep-link-auth` Tauri event; when received, write the incoming token to config and refresh license state.
       - `clearEmail` becomes `signOut` — clears `identity_token`.
    4. **Config schema** (`~/.schemagic/config.json`):
       - Add `identity_token: string`. Existing `email` field becomes derived (or keep for backwards compat during transition).
  - **5b — Auth + Settings UI.** Build against the already-scaffolded route files in `web/app/`:
    - `/auth/email` — form: email input → `POST /api/auth/request` → "check your inbox" confirmation card. Keep current `setEmail` fallback path gated behind `NODE_ENV !== "production"` for dev, or delete once 5a is verified.
    - `/auth/paywall` — already wired to `requestCheckout` + `refreshLicense`. Phase 5b just polishes copy + visuals against Figma node `78:4`.
    - `/settings` — already has Tabs (Account / Billing / Preferences). Billing wires to `requestPortal()` (done). Account should show email + sign-out button. Preferences stubs remain as TODOs per section 5.
- **Phase 6 — Cleanup.** Delete `/app` catch-all, delete `/activate` if folded, remove orphaned components, regression-test the full flow in the Tauri build.

---

## 5. Resolved context (investigated 2026-04-13)

- **Marketing landing (`/`) scope:** OUT OF SCOPE. Leave landing on current design. Redesign only touches Tauri app surfaces (`/app`, `/wizard/*`, `/auth/*`, `/settings`).
- **`/activate`:** KEEP. It's the Stripe post-checkout redirect target — public web page telling users the app will auto-activate on next launch. Not in Figma because it's web-only, not Tauri. Phase 6: restyle with new tokens, don't delete.
- **Fonts:** NOT currently loaded. `app/layout.tsx` only imports globals.css. Phase 1 adds Space Grotesk + JetBrains Mono via `next/font/google`.
- **Magic link auth:** IN SCOPE (full). Replace current email-as-identifier flow with real magic-link auth. Backend work required — see Phase 5 below.
- **Settings backend:** Out of scope per Hugh's direction. Build UI per Figma regardless of endpoint readiness; wire `requestPortal()` (already exists in `LicenseContext`) for Billing tab, stub Account + Preferences with TODO markers where endpoints don't exist yet.
- **Other Figma frames:** Design System page (tokens) + Screens page (9 screens) are the canonical surfaces. No additional frames tracked.

---

## 6. How Claude will consume this doc

When Hugh opens a fresh session with "start Phase 1 of the redesign", Claude will:
1. Read this file.
2. Call `mcp__figma__get_design_context` on the node for the current phase.
3. Adapt the output to the existing stack (Tailwind v4, not shadcn; hand-rolled primitives, not Radix).
4. Edit `web/` files directly.
5. Report back what changed and what's blocked.

Do NOT let Claude generate code straight from the MCP output — it will emit absolute-positioned CSS unless every frame is Auto Layout. Hugh: before Phase 2, verify Auto Layout is on in Dev Mode across all 9 screens.
