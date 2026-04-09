#!/bin/bash
set -euo pipefail

# Build the scheMAGIC Python sidecar for macOS.
# Produces tauri/sidecar/schemagic-server-{arch}-apple-darwin

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Installing sidecar build dependencies..."
pip install --quiet pyinstaller fastapi uvicorn pdfplumber anyio python-multipart pydantic certifi

echo "==> Building sidecar with PyInstaller..."
pyinstaller tauri/sidecar/schemagic-server.spec \
    --distpath tauri/sidecar \
    --workpath /tmp/schemagic-pyinstaller \
    --noconfirm

# Rename to Tauri's expected triple-suffix format
ARCH="$(uname -m)"
case "$ARCH" in
    arm64) TRIPLE="aarch64-apple-darwin" ;;
    x86_64) TRIPLE="x86_64-apple-darwin" ;;
    *) echo "Unknown arch: $ARCH"; exit 1 ;;
esac

mv "tauri/sidecar/schemagic-server" "tauri/sidecar/schemagic-server-${TRIPLE}"

echo "==> Sidecar built: tauri/sidecar/schemagic-server-${TRIPLE}"
echo "    Size: $(du -h "tauri/sidecar/schemagic-server-${TRIPLE}" | cut -f1)"
