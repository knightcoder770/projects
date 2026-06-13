import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "last_remote_url": "",
    "last_folder": "",
    "default_branch": "main",
    "remove_junk": True,
    "protect_sensitive": True,
}


def load_config() -> dict:
    """Load config from disk. Returns defaults if file doesn't exist."""
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        # Merge with defaults to handle missing keys in older configs
        return {**DEFAULT_CONFIG, **data}
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save config to disk."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def update_config(**kwargs) -> None:
    """Update specific keys in config and save."""
    config = load_config()
    config.update(kwargs)
    save_config(config)


def get(key: str):
    """Get a single config value."""
    return load_config().get(key, DEFAULT_CONFIG.get(key))
