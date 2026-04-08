#!/bin/bash
set -euo pipefail

VERSION="0.1.0"
DMG_URL="https://github.com/hughminhphan/schemagic-webapp/releases/download/v${VERSION}/scheMAGIC.dmg"
APP_NAME="scheMAGIC.app"

# Colours
PINK='\033[35m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

echo ""
echo -e "${PINK}${BOLD}scheMAGIC${RESET} installer ${DIM}v${VERSION}${RESET}"
echo ""

# Pre-flight checks
if [ "$(uname)" != "Darwin" ]; then
  echo "Error: scheMAGIC is a macOS application."
  exit 1
fi

if [ ! -w "/Applications" ]; then
  echo "Error: Cannot write to /Applications."
  echo "Try: sudo bash <(curl -fsSL https://schemagic.design/install.sh)"
  exit 1
fi

FREE_GB=$(df -g /Applications | awk 'NR==2 {print $4}')
if [ "$FREE_GB" -lt 1 ]; then
  echo "Error: Less than 1 GB free disk space."
  exit 1
fi

# Temp directory with cleanup trap
TMPDIR=$(mktemp -d)
MOUNT_POINT=""
cleanup() {
  if [ -n "$MOUNT_POINT" ]; then
    hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || true
  fi
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

# Download
echo -e "${DIM}Downloading scheMAGIC.dmg...${RESET}"
curl -fL --progress-bar -o "$TMPDIR/scheMAGIC.dmg" "$DMG_URL"
echo ""

# Mount
echo -e "${DIM}Installing...${RESET}"
MOUNT_OUTPUT=$(hdiutil attach -nobrowse -quiet "$TMPDIR/scheMAGIC.dmg" 2>&1)
MOUNT_POINT=$(echo "$MOUNT_OUTPUT" | tail -1 | awk -F'\t' '{print $NF}' | xargs)

if [ -z "$MOUNT_POINT" ] || [ ! -d "$MOUNT_POINT" ]; then
  echo "Error: Failed to mount DMG."
  exit 1
fi

# Find and copy .app
APP_SOURCE=$(find "$MOUNT_POINT" -maxdepth 1 -name "*.app" -type d | head -1)
if [ -z "$APP_SOURCE" ]; then
  echo "Error: No .app found in DMG."
  exit 1
fi

rm -rf "/Applications/${APP_NAME}"
cp -R "$APP_SOURCE" "/Applications/${APP_NAME}"

# Strip quarantine (belt-and-suspenders)
xattr -dr com.apple.quarantine "/Applications/${APP_NAME}" 2>/dev/null || true

echo ""
echo -e "${PINK}${BOLD}Done.${RESET} scheMAGIC installed to /Applications/"
echo -e "${DIM}Open it from Launchpad or Spotlight.${RESET}"
echo ""
