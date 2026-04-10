#!/bin/bash
set -euo pipefail

# Build scheMAGIC and install to /Applications.
# After running this, just open scheMAGIC.app normally to test.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Step 1/4: Building Python sidecar..."
./scripts/build-sidecar-macos.sh

echo ""
echo "==> Step 2/4: Building frontend (static export for Tauri)..."
# Temporarily move API routes out - they only work on Vercel (server mode),
# not in static export mode used by Tauri.
if [ -d "web/app/api" ]; then
    mv web/app/api web/app/_api_server_only
fi
cd web && STATIC_EXPORT=1 npm run build && cd "$REPO_ROOT"
# Restore API routes
if [ -d "web/app/_api_server_only" ]; then
    mv web/app/_api_server_only web/app/api
fi

echo ""
echo "==> Step 3/4: Building Tauri app..."
cd tauri && cargo tauri build --bundles app 2>&1
cd "$REPO_ROOT"

echo ""
echo "==> Step 3b: Creating DMG (bypassing Tauri's bundle_dmg.sh)..."
APP_BUNDLE="tauri/target/release/bundle/macos/scheMAGIC.app"
DMG_DIR="tauri/target/release/bundle/dmg"
mkdir -p "$DMG_DIR"
VERSION=$(grep '^version' tauri/Cargo.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')
ARCH=$(uname -m | sed 's/arm64/aarch64/')
DMG_NAME="scheMAGIC_${VERSION}_${ARCH}.dmg"
rm -f "$DMG_DIR/$DMG_NAME"
hdiutil create -srcfolder "$APP_BUNDLE" -volname "scheMAGIC" -fs HFS+ -format UDZO -o "$DMG_DIR/$DMG_NAME"
echo "==> DMG created: $DMG_DIR/$DMG_NAME ($(du -h "$DMG_DIR/$DMG_NAME" | cut -f1))"

echo ""
echo "==> Step 4/4: Installing to /Applications..."
if [ ! -d "$APP_BUNDLE" ]; then
    echo "ERROR: Built app not found at $APP_BUNDLE"
    exit 1
fi

# Kill running instance if any
pkill -f "scheMAGIC.app" 2>/dev/null || true
sleep 1

# Remove old and copy new
rm -rf "/Applications/scheMAGIC.app"
cp -R "$APP_BUNDLE" "/Applications/scheMAGIC.app"

echo ""
echo "==> Done! scheMAGIC.app installed to /Applications."
echo "    Open it from Spotlight or Finder to test."
