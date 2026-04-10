#!/bin/bash
set -euo pipefail

# Build scheMAGIC and install to /Applications.
# After running this, just open scheMAGIC.app normally to test.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Step 1/4: Building Python sidecar..."
./scripts/build-sidecar-macos.sh

echo ""
echo "==> Step 2/4: Building frontend..."
cd web && npm run build && cd "$REPO_ROOT"

echo ""
echo "==> Step 3/4: Building Tauri app..."
cd tauri && cargo tauri build 2>&1
cd "$REPO_ROOT"

echo ""
echo "==> Step 4/4: Installing to /Applications..."
# Find the built .app bundle
APP_BUNDLE="tauri/target/release/bundle/macos/scheMAGIC.app"
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
