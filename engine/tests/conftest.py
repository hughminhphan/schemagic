"""pytest configuration: set up import paths for schemagic tests."""

import os
import sys

# Prevent pcbnew plugin registration during tests
os.environ["SCHEMAGIC_STANDALONE"] = "1"

# Add the repo root to sys.path so `from engine.X` imports work
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
