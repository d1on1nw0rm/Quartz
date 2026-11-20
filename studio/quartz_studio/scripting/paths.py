from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

__all__ = [
    "quartz_home",
    "scripts_dir",
    "plugins_dir",
    "settings_path",
    "read_settings",
    "write_settings",
    "read_json",
    "write_json",
    "settings_version",
]

SETTINGS_FILE = "scripting.json"
_VERSION = [0]


def quartz_home() -> Path:
    override = os.environ.get("QUARTZ_HOME", "").strip()
    if override:
        base = Path(override)
    else:
        appdata = os.environ.get("APPDATA", "").strip()
        base = Path(appdata) / "Quartz" if appdata else Path.home() / ".quartz"
    base.mkdir(parents=True, exist_ok=True)
    return base


def scripts_dir() -> Path:
    path = quartz_home() / "scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def plugins_dir() -> Path:
    path = quartz_home() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return quartz_home() / SETTINGS_FILE


def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def read_settings() -> dict:
    data = read_json(settings_path(), {})
    return data if isinstance(data, dict) else {}


def write_settings(data: dict) -> None:
    write_json(settings_path(), data)
    _VERSION[0] += 1


def settings_version() -> int:
    return _VERSION[0]


def update_settings(key: str, value: Any) -> dict:
    data = read_settings()
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    write_settings(data)
    return data
