import json
import os
import sys

APP_NAME = "XcosGen"


def _config_dir() -> str:
    """Return a platform-appropriate config directory (stdlib only)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


class ConfigStore:
    def __init__(self):
        config_dir = _config_dir()
        os.makedirs(config_dir, exist_ok=True)
        self.path = os.path.join(config_dir, "config.json")

    def load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, data: dict):
        existing = self.load()
        existing.update(data)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
