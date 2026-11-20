from __future__ import annotations

import json
import logging
import os
import sys

from quartz_studio.controls import profiles as _profiles

LOG = logging.getLogger("quartz_studio.controls")

STORE_FORMAT = "quartz-controls-store"
STORE_VERSION = 1
SHIPPED_DEFAULT = "standard"
UNLOADED = "classic"
FILE_NAME = "controls.json"
REGISTRY_KEY = r"Software\Quartz\Quartz Studio"

_STATE: dict = {"loaded": False, "selected": UNLOADED, "profiles": []}


def state() -> dict:
    return _STATE


def reset_state() -> None:
    _STATE["loaded"] = False
    _STATE["selected"] = UNLOADED
    _STATE["profiles"] = []


def _controls():
    from quartz_studio import controls

    return controls


def _settings_file() -> str | None:
    from quartz_studio import project

    return getattr(project, "SETTINGS_FILE", None) or None


def _explicit_path() -> str | None:
    override = getattr(_controls(), "STORE_PATH", None)
    if override:
        return os.fspath(override)
    settings = _settings_file()
    if settings:
        return os.path.join(os.path.dirname(os.path.abspath(settings)), FILE_NAME)
    return None


def path() -> str:
    explicit = _explicit_path()
    if explicit:
        return explicit
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, "Quartz", FILE_NAME)


def write_json(target: str, data: dict) -> None:
    folder = os.path.dirname(os.path.abspath(target))
    os.makedirs(folder, exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=False, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, target)


def _corrupt(target: str, reason: str) -> None:
    bad = target + ".bad"
    LOG.warning("controls: store %s is corrupt (%s); renamed to %s", target, reason, bad)
    try:
        os.replace(target, bad)
    except OSError as exc:
        LOG.warning("controls: could not rename %s: %s", target, exc)


def _valid_store(data) -> str | None:
    if not isinstance(data, dict):
        return "not an object"
    if data.get("format") != STORE_FORMAT:
        return "wrong format"
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version > STORE_VERSION:
        return "unsupported version"
    if not isinstance(data.get("profiles", []), list):
        return "profiles is not a list"
    return None


def read() -> dict | None:
    target = path()
    if not os.path.exists(target):
        return None
    try:
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _corrupt(target, str(exc))
        return None
    reason = _valid_store(data)
    if reason is not None:
        _corrupt(target, reason)
        return None
    return data


def _apply(data: dict) -> None:
    users: list[dict] = []
    ids: set[str] = set()
    names: set[str] = {d["name"].casefold() for d in _profiles.BUILTINS.values()}
    for raw in data.get("profiles", []):
        try:
            doc = _profiles.load_user(raw)
        except ValueError as exc:
            LOG.warning("controls: invalid profile dropped: %s", exc)
            continue
        if doc["id"] in ids:
            LOG.warning("controls: duplicate profile id %s dropped", doc["id"])
            continue
        if doc["name"].casefold() in names:
            LOG.warning("controls: duplicate profile name %r dropped", doc["name"])
            continue
        ids.add(doc["id"])
        names.add(doc["name"].casefold())
        users.append(doc)
    selected = data.get("selected")
    if selected not in _profiles.BUILTIN_IDS and selected not in ids:
        selected = SHIPPED_DEFAULT
    _STATE["profiles"] = users
    _STATE["selected"] = selected
    _STATE["loaded"] = True


def document() -> dict:
    return {
        "format": STORE_FORMAT,
        "version": STORE_VERSION,
        "selected": _STATE["selected"],
        "profiles": [dict(d) for d in _STATE["profiles"]],
    }


def save() -> None:
    if not _STATE["loaded"] and _explicit_path() is None:
        return
    write_json(path(), document())


def previous_install() -> bool:
    settings = _settings_file()
    if settings:
        return os.path.exists(settings)
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY):
                return True
        except OSError:
            return False
    from quartz_studio import project

    return os.path.exists(project.settings().fileName())


def first_run() -> None:
    data = read()
    if data is None:
        data = {"format": STORE_FORMAT, "version": STORE_VERSION,
                "selected": "classic" if previous_install() else SHIPPED_DEFAULT, "profiles": []}
        _apply(data)
        write_json(path(), document())
    else:
        _apply(data)
    _controls()._emit()


def load() -> None:
    first_run()
