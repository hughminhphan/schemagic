$ErrorActionPreference = "Stop"

# Build the scheMAGIC Python sidecar for Windows.
# Produces tauri/sidecar/schemagic-server-x86_64-pc-windows-msvc.exe

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "==> Installing sidecar build dependencies..."
pip install --quiet pyinstaller fastapi uvicorn pdfplumber anyio python-multipart pydantic certifi

Write-Host "==> Building sidecar with PyInstaller..."
pyinstaller "tauri\sidecar\schemagic-server.spec" `
    --distpath "tauri\sidecar" `
    --workpath "C:\Temp\schemagic-pyinstaller" `
    --noconfirm

# Rename to Tauri's expected triple-suffix format
Rename-Item `
    "tauri\sidecar\schemagic-server.exe" `
    "schemagic-server-x86_64-pc-windows-msvc.exe"

$Size = (Get-Item "tauri\sidecar\schemagic-server-x86_64-pc-windows-msvc.exe").Length / 1MB
Write-Host "==> Sidecar built: tauri/sidecar/schemagic-server-x86_64-pc-windows-msvc.exe"
Write-Host ("    Size: {0:N1} MB" -f $Size)
