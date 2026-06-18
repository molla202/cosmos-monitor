"""User configuration management for cosmos-monitor."""
import json
import os
from typing import Any

CONFIG_FILE = os.path.expanduser("~/.cosmos-monitor.json")

def load_config() -> dict[str, Any]:
    """Load the user configuration file."""
    default_config = {"hidden_chains": [], "custom_chains": []}
    if not os.path.exists(CONFIG_FILE):
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure defaults
            if "hidden_chains" not in data:
                data["hidden_chains"] = []
            if "custom_chains" not in data:
                data["custom_chains"] = []
            return data
    except Exception:
        return default_config


def save_config(data: dict[str, Any]):
    """Save the user configuration file."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def add_hidden_chain(chain_id_or_home: str):
    """Hide a chain by chain_id or home_dir."""
    data = load_config()
    if chain_id_or_home not in data["hidden_chains"]:
        data["hidden_chains"].append(chain_id_or_home)
        save_config(data)


def add_custom_chain(home_dir: str):
    """Add a custom chain home_dir path."""
    data = load_config()
    # Check if already exists
    for c in data["custom_chains"]:
        if isinstance(c, str) and c == home_dir:
            return
        elif isinstance(c, dict) and c.get("home_dir") == home_dir:
            return
    data["custom_chains"].append(home_dir)
    save_config(data)
