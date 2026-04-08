#!/usr/bin/env python3
"""Build scheMAGIC.app in a clean temp directory.

Copies engine/ and plugin/ into a flat package structure that py2app
can bundle without symlink recursion issues.

Run from the repo root:
    python plugin/build_dmg.py
"""

import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = "/tmp/schemagic-build"
VENV_PYTHON = os.path.join(REPO_ROOT, "plugin", ".venv", "bin", "python3")


def main():
    # Clean previous build
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    # Copy build config files
    shutil.copy2(os.path.join(REPO_ROOT, "plugin", "setup_app.py"), BUILD_DIR)
    shutil.copy2(os.path.join(REPO_ROOT, "plugin", "icon.icns"), BUILD_DIR)
    shutil.copy2(os.path.join(REPO_ROOT, "plugin", "app.py"),
                 os.path.join(BUILD_DIR, "app.py"))

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "tests", ".venv")

    # Copy engine/ package
    shutil.copytree(
        os.path.join(REPO_ROOT, "engine"),
        os.path.join(BUILD_DIR, "engine"),
        ignore=ignore,
    )

    # Copy plugin/ package
    shutil.copytree(
        os.path.join(REPO_ROOT, "plugin"),
        os.path.join(BUILD_DIR, "plugin"),
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".DS_Store", ".venv",
            "build_dmg.py", "dist",
        ),
    )

    # Run py2app
    env = os.environ.copy()
    env["PYTHONPATH"] = BUILD_DIR + ":" + env.get("PYTHONPATH", "")

    python = VENV_PYTHON if os.path.isfile(VENV_PYTHON) else sys.executable

    print(f"Building in {BUILD_DIR}...")
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
    if os.path.isdir(build_dist):
        shutil.move(build_dist, final_dist)
        app_path = os.path.join(final_dist, "scheMAGIC.app")
        print(f"\nBuild complete: {app_path}")
        print(f"Size: {_dir_size(app_path):.1f} MB")

    # Clean
    shutil.rmtree(BUILD_DIR, ignore_errors=True)


def _dir_size(path):
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total / (1024 * 1024)


if __name__ == "__main__":
    main()
