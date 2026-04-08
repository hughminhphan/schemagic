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
    "ai_provider": "gemini",       # "gemini", "openai", "anthropic", or "none"
    "gemini_api_key": "",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "gemini_model": "gemini-2.5-flash-lite",
    "openai_model": "gpt-4o-mini",
    "anthropic_model": "claude-haiku-4-5-20251001",
    "ai_enabled": True,            # master switch for AI extraction
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


def get_api_key(provider=None):
    """Get the API key for the active (or specified) provider.

    Returns (provider, api_key, model) or (None, None, None) if not configured.
    """
    config = load_config()

    if not config.get("ai_enabled", True):
        return (None, None, None)

    provider = provider or config.get("ai_provider", "gemini")

    key_map = {
        "gemini": ("gemini_api_key", "gemini_model"),
        "openai": ("openai_api_key", "openai_model"),
        "anthropic": ("anthropic_api_key", "anthropic_model"),
    }

    if provider not in key_map:
        return (None, None, None)

    key_field, model_field = key_map[provider]
    api_key = config.get(key_field, "")
    model = config.get(model_field, "")

    if not api_key:
        return (None, None, None)

    return (provider, api_key, model)
