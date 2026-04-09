#!/usr/bin/env python3
"""Build scheMAGIC.app, code-sign it, and package into a DMG.

Produces a professional DMG with drag-to-Applications experience.

Run from the repo root:
    python plugin/build_dmg.py
    python plugin/build_dmg.py --skip-dmg      # .app only
    python plugin/build_dmg.py --identity "Developer ID Application: ..."
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = "/tmp/schemagic-build"
VENV_PYTHON = os.path.join(REPO_ROOT, "plugin", ".venv", "bin", "python3")
VENV_SITE_PACKAGES = os.path.join(
    REPO_ROOT, "plugin", ".venv", "lib", "python3.12", "site-packages"
)


def parse_args():
    parser = argparse.ArgumentParser(description="Build scheMAGIC.app and DMG")
    parser.add_argument("--skip-dmg", action="store_true", help="Build .app only, skip DMG creation")
    parser.add_argument("--notarize", action="store_true", help="Print notarization instructions")
    parser.add_argument("--identity", type=str, help="Codesign identity (default: auto-detect)")
    return parser.parse_args()


def _copy_missing_extensions(app_path: str):
    """Copy top-level C extension .so files that py2app misses.

    py2app discovers packages and modules listed in includes/packages,
    but misses standalone .so files at the top level of site-packages:
    - charset_normalizer's mypyc runtime (hash-named .so)
    - _cffi_backend.so (needed by cryptography, needed by pdfminer)

    This copies all top-level .so files from the venv into the app bundle.
    """
    if not os.path.isdir(VENV_SITE_PACKAGES):
        return

    dest_dir = os.path.join(app_path, "Contents", "Resources", "lib", "python3.12")
    for f in os.listdir(VENV_SITE_PACKAGES):
        if f.endswith(".so"):
            src = os.path.join(VENV_SITE_PACKAGES, f)
            dst = os.path.join(dest_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"  Copied extension: {f}")


# ---------------------------------------------------------------------------
# Phase 1: Build .app via py2app
# ---------------------------------------------------------------------------

def build_app() -> str:
    """Build scheMAGIC.app and return its path."""
    print("\n[1/4] Building scheMAGIC.app via py2app...")

    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    # Copy build config files
    shutil.copy2(os.path.join(REPO_ROOT, "plugin", "setup_app.py"), BUILD_DIR)
    shutil.copy2(os.path.join(REPO_ROOT, "plugin", "icon.icns"), BUILD_DIR)
    shutil.copy2(os.path.join(REPO_ROOT, "plugin", "app.py"), os.path.join(BUILD_DIR, "app.py"))

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "tests", ".venv")

    shutil.copytree(
        os.path.join(REPO_ROOT, "engine"),
        os.path.join(BUILD_DIR, "engine"),
        ignore=ignore,
    )

    shutil.copytree(
        os.path.join(REPO_ROOT, "plugin"),
        os.path.join(BUILD_DIR, "plugin"),
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".DS_Store", ".venv",
            "build_dmg.py", "dmg_background.py", "dist",
        ),
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = BUILD_DIR + ":" + env.get("PYTHONPATH", "")
    python = VENV_PYTHON if os.path.isfile(VENV_PYTHON) else sys.executable

    result = subprocess.run(
        [python, "setup_app.py", "py2app"],
        cwd=BUILD_DIR,
        env=env,
    )

    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    # Move dist output back to plugin dir
    build_dist = os.path.join(BUILD_DIR, "dist")
    final_dist = os.path.join(REPO_ROOT, "plugin", "dist")
    if os.path.exists(final_dist):
        shutil.rmtree(final_dist)

    if not os.path.isdir(build_dist):
        print("Build produced no dist/ directory!")
        sys.exit(1)

    shutil.move(build_dist, final_dist)
    app_path = os.path.join(final_dist, "scheMAGIC.app")

    # Copy top-level .so extensions that py2app misses
    _copy_missing_extensions(app_path)

    print(f"  Build complete: {app_path} ({_dir_size(app_path):.1f} MB)")

    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    return app_path


# ---------------------------------------------------------------------------
# Phase 2: Code sign
# ---------------------------------------------------------------------------

def _resolve_signing_identity() -> str:
    """Return signing identity: env var > auto-detected Developer ID > ad-hoc."""
    env_id = os.environ.get("SCHEMAGIC_SIGNING_IDENTITY")
    if env_id:
        return env_id

    result = subprocess.run(
        ["security", "find-identity", "-v", "-p", "codesigning"],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        if "Developer ID Application" in line:
            match = re.search(r'"(Developer ID Application:[^"]+)"', line)
            if match:
                return match.group(1)

    return "-"  # ad-hoc


def _fix_corrupted_dylibs(app_path: str):
    """Replace dylibs/shared libs corrupted by py2app with clean copies.

    py2app sometimes produces dylibs and .so extensions with invalid Mach-O
    structure (trailing data or truncated LINKEDIT segments) that cause
    codesign failures or dlopen errors at runtime.

    Scans both Contents/Frameworks/*.dylib AND all .so/.dylib files under
    Contents/Resources/lib/ (where Python C extensions live).
    """
    venv_site_packages = os.path.join(
        REPO_ROOT, "plugin", ".venv", "lib"
    )

    search_paths = [
        "/opt/homebrew/lib",
        "/usr/lib",
        "/opt/homebrew/Cellar",
    ]
    # Add venv site-packages as the primary search path for Python extensions
    if os.path.isdir(venv_site_packages):
        search_paths.insert(0, venv_site_packages)

    # Collect all .dylib and .so files from Frameworks and Resources/lib
    targets = []

    frameworks_dir = os.path.join(app_path, "Contents", "Frameworks")
    if os.path.isdir(frameworks_dir):
        for f in os.listdir(frameworks_dir):
            if f.endswith(".dylib"):
                targets.append(os.path.join(frameworks_dir, f))

    resources_lib = os.path.join(app_path, "Contents", "Resources", "lib")
    if os.path.isdir(resources_lib):
        for dirpath, _, filenames in os.walk(resources_lib):
            for f in filenames:
                if f.endswith((".so", ".dylib")):
                    targets.append(os.path.join(dirpath, f))

    for fpath in targets:
        fname = os.path.basename(fpath)
        # Test if codesign works
        r = subprocess.run(
            ["codesign", "--force", "--sign", "-", fpath],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            continue

        # Find a clean copy
        result = subprocess.run(
            ["find"] + search_paths + ["-name", fname, "-type", "f"],
            capture_output=True, text=True, timeout=30,
        )
        for candidate in result.stdout.strip().splitlines():
            if candidate and os.path.isfile(candidate):
                shutil.copy2(candidate, fpath)
                r2 = subprocess.run(
                    ["codesign", "--force", "--sign", "-", fpath],
                    capture_output=True, text=True,
                )
                if r2.returncode == 0:
                    print(f"  Fixed corrupted {fname}")
                    break


def codesign_app(app_path: str, identity: str):
    """Sign the .app bundle, handling embedded frameworks correctly."""
    label = "ad-hoc" if identity == "-" else identity
    print(f"\n[2/4] Code signing ({label})...")

    # Fix dylibs corrupted by py2app
    _fix_corrupted_dylibs(app_path)

    sign_cmd = ["codesign", "--force", "--sign", identity]
    if identity != "-":
        sign_cmd += ["--options", "runtime"]

    # Sign all .so and .dylib files individually first
    for dirpath, _, filenames in os.walk(app_path):
        for f in filenames:
            if f.endswith((".so", ".dylib")):
                fpath = os.path.join(dirpath, f)
                subprocess.run(sign_cmd + [fpath], capture_output=True)

    # Sign embedded frameworks before the app bundle
    frameworks_dir = os.path.join(app_path, "Contents", "Frameworks")
    if os.path.isdir(frameworks_dir):
        for item in os.listdir(frameworks_dir):
            item_path = os.path.join(frameworks_dir, item)
            if item.endswith(".framework"):
                subprocess.run(sign_cmd + [item_path], capture_output=True)

    # Sign the top-level app bundle
    subprocess.run(sign_cmd + [app_path], check=True)
    print("  Signed successfully")


# ---------------------------------------------------------------------------
# Phase 3: Generate DMG background
# ---------------------------------------------------------------------------

def generate_background() -> str:
    """Generate DMG background image, return its path."""
    print("\n[3/4] Generating DMG background...")
    tmpdir = tempfile.mkdtemp(prefix="schemagic-dmg-bg-")

    sys.path.insert(0, REPO_ROOT)
    from plugin.dmg_background import generate_dmg_background
    path = generate_dmg_background(tmpdir)
    print("  Created 660x400 background")
    return path


# ---------------------------------------------------------------------------
# Phase 4: Create DMG
# ---------------------------------------------------------------------------

def create_dmg(app_path: str, dmg_path: str, background: str, icon_path: str):
    """Create DMG with drag-to-Applications layout using hdiutil."""
    print("\n[4/4] Creating DMG with drag-to-Applications...")

    if os.path.exists(dmg_path):
        os.remove(dmg_path)

    # Stage the app + Applications symlink
    staging = tempfile.mkdtemp(prefix="schemagic-dmg-stage-")
    try:
        shutil.copytree(app_path, os.path.join(staging, "scheMAGIC.app"))
        os.symlink("/Applications", os.path.join(staging, "Applications"))

        # Copy background for the DMG window
        bg_dir = os.path.join(staging, ".background")
        os.makedirs(bg_dir)
        shutil.copy2(background, os.path.join(bg_dir, "background.png"))

        # Create compressed DMG directly
        subprocess.run([
            "hdiutil", "create",
            "-volname", "scheMAGIC",
            "-srcfolder", staging,
            "-ov",
            "-format", "UDZO",
            dmg_path,
        ], check=True)

    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # Set volume icon
    if os.path.isfile(icon_path):
        _set_dmg_icon(dmg_path, icon_path)

    size_mb = os.path.getsize(dmg_path) / (1024 * 1024)
    print(f"  DMG created: {dmg_path} ({size_mb:.1f} MB)")


def _set_dmg_icon(dmg_path: str, icon_path: str):
    """Attach a volume icon to the DMG (best-effort)."""
    try:
        # Mount writable
        result = subprocess.run(
            ["hdiutil", "attach", dmg_path, "-nobrowse", "-readwrite"],
            capture_output=True, text=True,
        )
        mount_point = None
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[-1].strip():
                mount_point = parts[-1].strip()
        if not mount_point:
            return

        # Copy icon and set custom icon attribute
        dest_icon = os.path.join(mount_point, ".VolumeIcon.icns")
        shutil.copy2(icon_path, dest_icon)
        subprocess.run(["SetFile", "-c", "icnC", dest_icon], capture_output=True)
        subprocess.run(["SetFile", "-a", "C", mount_point], capture_output=True)

        # Detach
        subprocess.run(["hdiutil", "detach", mount_point], capture_output=True)
    except Exception:
        pass  # Non-critical


# ---------------------------------------------------------------------------
# Phase 5: Notarize (stub)
# ---------------------------------------------------------------------------

def notarize_dmg(dmg_path: str):
    print("\nNotarization requires an Apple Developer ID ($99/year).")
    print("When ready, run:")
    print(f"  xcrun notarytool submit {dmg_path} \\")
    print("    --apple-id YOUR_APPLE_ID --team-id TEAM_ID \\")
    print("    --password APP_SPECIFIC_PASSWORD --wait")
    print(f"  xcrun stapler staple {dmg_path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dir_size(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total / (1024 * 1024)


def _get_version() -> str:
    """Read version from setup_app.py."""
    setup_path = os.path.join(REPO_ROOT, "plugin", "setup_app.py")
    with open(setup_path) as f:
        for line in f:
            if line.startswith("VERSION"):
                match = re.search(r'"([^"]+)"', line)
                if match:
                    return match.group(1)
    return "0.1.0"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # Phase 1: Build .app
    app_path = build_app()

    # Phase 2: Code sign
    identity = args.identity or _resolve_signing_identity()
    codesign_app(app_path, identity)

    if args.skip_dmg:
        print(f"\nDone. App at: {app_path}")
        return

    # Phase 3: Generate background
    bg_path = generate_background()

    # Phase 4: Create DMG
    version = _get_version()
    dmg_path = os.path.join(REPO_ROOT, "plugin", "dist", f"scheMAGIC-{version}.dmg")
    icon_path = os.path.join(REPO_ROOT, "plugin", "icon.icns")
    create_dmg(app_path, dmg_path, bg_path, icon_path)

    # Cleanup background temp dir
    shutil.rmtree(os.path.dirname(bg_path), ignore_errors=True)

    # Phase 5: Notarize (optional)
    if args.notarize:
        notarize_dmg(dmg_path)

    print(f"\nDone! Distribute: {dmg_path}")


if __name__ == "__main__":
    main()
