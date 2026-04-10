#!/bin/bash
set -euo pipefail

# Build the scheMAGIC Python sidecar for macOS.
# Produces tauri/sidecar/schemagic-server-{arch}-apple-darwin
#
# Requires a framework Python (Homebrew). PlatformIO/pyenv static builds won't work.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Use Homebrew Python (framework build required by PyInstaller on macOS)
PYTHON=""
for candidate in /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /usr/local/bin/python3; do
    if [ -x "$candidate" ]; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: No Homebrew/framework Python found. Install with: brew install python@3.12"
    exit 1
fi

echo "==> Using Python: $PYTHON ($($PYTHON --version))"

# Create/reuse a venv for sidecar builds
VENV_DIR="$REPO_ROOT/.venv-sidecar"
if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating sidecar build venv..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

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

# Symlink to tauri/binaries/ where Tauri's externalBin expects it
# (cp breaks PyInstaller ad-hoc signatures on macOS - must use symlinks)
ln -sf "$(pwd)/tauri/sidecar/schemagic-server-${TRIPLE}" "tauri/binaries/schemagic-server-${TRIPLE}"
echo "==> Symlinked to tauri/binaries/"
