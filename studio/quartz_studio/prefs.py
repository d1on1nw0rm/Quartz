from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import tempfile
from typing import Any

from PySide6.QtCore import QObject, Signal

__all__ = ["VERSION", "get", "set", "path", "changed", "reload", "use_user_profile"]

VERSION = 1
FILE_NAME = "prefs.json"
TMP_NAME = "prefs.json.tmp"
CORRUPT_NAME = "prefs.corrupt.json"

log = logging.getLogger("quartz_studio.prefs")


class _Hub(QObject):
    changed = Signal(str)


_hub = _Hub()
changed = _hub.changed

_state: dict[str, Any] = {"values": None, "version": VERSION, "user": False, "temp": None}


def use_user_profile() -> None:
    _state["user"] = True


def _folder() -> str:
    env = os.environ.get("QUARTZ_PREFS_DIR")
    if env:
        return env
    from quartz_studio import project

    if project.SETTINGS_FILE:
        return os.path.dirname(os.path.abspath(project.SETTINGS_FILE))
    if _state["user"]:
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Quartz")
    if _state["temp"] is None or not os.path.isdir(_state["temp"]):
        _state["temp"] = tempfile.mkdtemp(prefix="quartz-prefs-")
    return _state["temp"]


def path() -> str:
    return os.path.abspath(os.path.join(_folder(), FILE_NAME))


def reload() -> None:
    _state["values"] = None
    _state["version"] = VERSION


def _read() -> dict:
    target = path()
    _state["version"] = VERSION
    if not os.path.exists(target):
        return {}
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("values", {}), dict):
            raise ValueError("unexpected layout")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        try:
            shutil.copyfile(target, os.path.join(os.path.dirname(target), CORRUPT_NAME))
        except OSError:
            pass
        log.warning("preferences file %s is unreadable (%s); using defaults", target, exc)
        return {}
    version = data.get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version > VERSION:
        _state["version"] = version
    return dict(data.get("values", {}))


def _values() -> dict:
    if _state["values"] is None:
        _state["values"] = _read()
    return _state["values"]


def get(key: str, default: Any = None) -> Any:
    try:
        values = _values()
    except Exception as exc:
        log.warning("preferences could not be loaded (%s)", exc)
        return default
    if key not in values:
        return default
    return copy.deepcopy(values[key])


def _write() -> None:
    target = path()
    folder = os.path.dirname(target)
    data = {"version": _state["version"], "values": _state["values"]}
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    try:
        os.makedirs(folder, exist_ok=True)
        tmp = os.path.join(folder, TMP_NAME)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, target)
    except OSError as exc:
        log.warning("preferences could not be written to %s (%s)", target, exc)


def set(key: str, value: Any) -> None:
    values = _values()
    if value is None:
        if key not in values:
            return
        del values[key]
    else:
        stored = json.loads(json.dumps(value))
        if key in values and values[key] == stored:
            return
        values[key] = stored
    _write()
    changed.emit(key)
