"""
User configuration for schemagic.

Settings are stored in ~/.schemagic/config.json. This keeps user preferences
(API keys, provider choices) separate from the plugin code and persists
across updates.
"""

import json
import os

CONFIG_DIR = os.path.expanduser("~/.schemagic")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

_DEFAULTS = {
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash-lite",
}


def load_config():
    """Load user config, merging with defaults for any missing keys."""
    config = dict(_DEFAULTS)
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                stored = json.load(f)
            config.update(stored)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save_config(config):
    """Save config to disk, creating directory if needed."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_gemini_key():
    """Get the Gemini API key and model.

    Returns (api_key, model). Raises RuntimeError if key is missing.
    """
    config = load_config()
    api_key = config.get("gemini_api_key", "")
    model = config.get("gemini_model", "gemini-2.5-flash-lite")

    if not api_key:
        raise RuntimeError(
            "Gemini API key not configured. "
            "Add 'gemini_api_key' to ~/.schemagic/config.json."
        )

    return (api_key, model)
