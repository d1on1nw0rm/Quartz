from __future__ import annotations

import contextlib
import copy
import json
import os
import secrets

from PySide6.QtCore import QObject, Signal

from quartz_studio.controls import actions as _actions
from quartz_studio.controls import profiles as _profiles
from quartz_studio.controls import store as _store
from quartz_studio.controls.actions import Action
from quartz_studio.controls.profiles import (
    BUILTIN_IDS,
    BUILTINS,
    CLASSIC_NAME,
    STANDARD_NAME,
    Resolved,
)

STORE_PATH: str | None = None
SHIPPED_DEFAULT = _store.SHIPPED_DEFAULT
NAME_MAX = 48

__all__ = [
    "STORE_PATH", "SHIPPED_DEFAULT", "CLASSIC_NAME", "STANDARD_NAME", "Action", "Resolved", "ControlsHub",
    "hub", "load", "reset", "window", "install", "refresh", "deferred_refresh", "actions", "register_action", "run", "active",
    "active_id", "profiles", "select", "duplicate", "rename", "delete", "set_keys", "reset_action",
    "set_mouse", "reset_mouse", "set_cursor", "reset_cursor", "set_modifier", "reset_modifier", "set_modal",
    "reset_modal", "reset_profile", "export_profile", "import_profile", "bindings", "binding_text",
    "tooltip", "lookup", "hold_keys", "held_set", "match_press", "is_navigation_press", "modifier_held",
    "modifier_name", "modal_key", "cursor", "conflicts",
]


class ControlsHub(QObject):
    profileChanged = Signal(str)


_HUB = ControlsHub()
_WINDOW: list = [None]
_CACHE: dict[str, Resolved] = {}
_DEFER: list = [0, False]


def hub() -> ControlsHub:
    return _HUB


def _dispatch():
    from quartz_studio.controls import dispatch

    return dispatch


def _set_window(win) -> None:
    _WINDOW[0] = win


def window():
    win = _WINDOW[0]
    if win is None:
        return None
    try:
        from shiboken6 import isValid
    except ImportError:
        return win
    if not isValid(win):
        _WINDOW[0] = None
        return None
    return win


def _invalidate() -> None:
    _CACHE.clear()


def _emit() -> None:
    _invalidate()
    _HUB.profileChanged.emit(active_id())


def load() -> None:
    _store.first_run()


def reset() -> None:
    state = _store.state()
    changed = state["loaded"] or state["selected"] != "classic" or bool(state["profiles"])
    _store.reset_state()
    _invalidate()
    if changed:
        _HUB.profileChanged.emit(active_id())


def install(win) -> None:
    _dispatch().install(win)


def refresh() -> None:
    if _DEFER[0]:
        _DEFER[1] = True
        return
    _DEFER[1] = False
    _dispatch().refresh()


@contextlib.contextmanager
def deferred_refresh():
    _DEFER[0] += 1
    try:
        yield
    finally:
        _DEFER[0] -= 1
        if not _DEFER[0] and _DEFER[1]:
            _DEFER[1] = False
            if window() is not None:
                try:
                    _dispatch().refresh()
                except ImportError:
                    pass


actions = _actions
profiles = _profiles


def register_action(id, label, category, run, keys=(), scope="global", available=None, path=None) -> Action:
    action = _actions.register_action(id, label, category, run, keys=keys, scope=scope, available=available,
                                      path=path)
    _invalidate()
    if window() is not None:
        try:
            refresh()
        except ImportError:
            pass
    return action


def run(action_id: str) -> bool:
    action = actions().get(action_id)
    if action is None:
        return False
    if action.available is not None and not action.available():
        return False
    action.run()
    return True


def _user(profile_id: str) -> dict | None:
    for doc in _store.state()["profiles"]:
        if doc["id"] == profile_id:
            return doc
    return None


def _doc(profile_id: str) -> dict:
    if profile_id in BUILTINS:
        return BUILTINS[profile_id]
    doc = _user(profile_id)
    if doc is None:
        raise KeyError(profile_id)
    return doc


def _editable(profile_id: str) -> dict:
    if profile_id in BUILTINS:
        raise PermissionError(f"built-in profile {profile_id!r} cannot be changed")
    doc = _user(profile_id)
    if doc is None:
        raise KeyError(profile_id)
    return doc


def resolved(profile_id: str) -> Resolved:
    hit = _CACHE.get(profile_id)
    if hit is None:
        hit = _profiles.resolve(_doc(profile_id), _actions.known())
        _CACHE[profile_id] = hit
    return hit


def active() -> Resolved:
    return resolved(active_id())


def active_id() -> str:
    return _store.state()["selected"]


def profile_list() -> list[dict]:
    users = sorted(_store.state()["profiles"], key=lambda d: (d["name"].casefold(), d["id"]))
    return [copy.deepcopy(BUILTINS["standard"]), copy.deepcopy(BUILTINS["classic"])] + [
        copy.deepcopy(d) for d in users]


def _names(exclude: str | None = None) -> set[str]:
    out = {BUILTINS[b]["name"].casefold() for b in BUILTIN_IDS}
    for doc in _store.state()["profiles"]:
        if doc["id"] != exclude:
            out.add(doc["name"].casefold())
    return out


def _check_name(name, exclude: str | None = None) -> str:
    if not isinstance(name, str):
        raise ValueError("A profile name must be text.")
    name = name.strip()
    if not name:
        raise ValueError("A profile name cannot be empty.")
    if len(name) > NAME_MAX:
        raise ValueError(f"A profile name has at most {NAME_MAX} characters.")
    if name.casefold() in _names(exclude):
        raise ValueError(f"A profile named {name!r} already exists.")
    return name


def _unique_name(name: str) -> str:
    taken = _names()
    name = (name.strip() or "Profile")[:NAME_MAX]
    if name.casefold() not in taken:
        return name
    n = 1
    while True:
        suffix = " Copy" if n == 1 else f" Copy {n}"
        candidate = name[:NAME_MAX - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
        n += 1


def _copy_name(name: str) -> str:
    taken = _names()
    n = 1
    while True:
        suffix = " Copy" if n == 1 else f" Copy {n}"
        candidate = name[:NAME_MAX - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
        n += 1


def _new_id() -> str:
    while True:
        pid = "u-" + secrets.token_hex(4)
        if _user(pid) is None:
            return pid


def _save() -> None:
    _store.save()


def _touch(profile_id: str) -> None:
    _save()
    _invalidate()
    if profile_id == active_id():
        _HUB.profileChanged.emit(profile_id)


def select(profile_id: str) -> None:
    _doc(profile_id)
    _store.state()["selected"] = profile_id
    _save()
    _emit()


def duplicate(profile_id: str, name: str | None = None) -> str:
    src = _doc(profile_id)
    if profile_id in BUILTINS:
        doc = _profiles.empty_user(_new_id(), "", profile_id)
    else:
        doc = copy.deepcopy(src)
        doc["id"] = _new_id()
    doc["name"] = _copy_name(src["name"]) if name is None else _check_name(name)
    _store.state()["profiles"].append(doc)
    _store.state()["selected"] = doc["id"]
    _save()
    _emit()
    return doc["id"]


def rename(profile_id: str, name: str) -> None:
    doc = _editable(profile_id)
    doc["name"] = _check_name(name, exclude=profile_id)
    _touch(profile_id)


def delete(profile_id: str) -> None:
    doc = _editable(profile_id)
    state = _store.state()
    state["profiles"].remove(doc)
    was_active = state["selected"] == profile_id
    if was_active:
        state["selected"] = doc.get("base") or SHIPPED_DEFAULT
    _save()
    _invalidate()
    if was_active:
        _emit()


def set_keys(profile_id, action_id, bindings) -> None:
    doc = _editable(profile_id)
    doc["keys"][str(action_id)] = _profiles.check_bindings(bindings)
    _touch(profile_id)


def reset_action(profile_id, action_id) -> None:
    doc = _editable(profile_id)
    doc["keys"].pop(action_id, None)
    _touch(profile_id)


def set_mouse(profile_id, gestures) -> None:
    doc = _editable(profile_id)
    doc["mouse"] = _profiles.check_mouse(gestures)
    _touch(profile_id)


def reset_mouse(profile_id) -> None:
    doc = _editable(profile_id)
    doc["mouse"] = None
    _touch(profile_id)


def set_cursor(profile_id, key, value) -> None:
    doc = _editable(profile_id)
    doc["cursor"][key] = _profiles.check_cursor(key, value)
    _touch(profile_id)


def reset_cursor(profile_id, key) -> None:
    doc = _editable(profile_id)
    doc["cursor"].pop(key, None)
    _touch(profile_id)


def set_modifier(profile_id, role, mod) -> None:
    doc = _editable(profile_id)
    doc["modifiers"][role] = _profiles.check_modifier(role, mod)
    _touch(profile_id)


def reset_modifier(profile_id, role) -> None:
    doc = _editable(profile_id)
    doc["modifiers"].pop(role, None)
    _touch(profile_id)


def set_modal(profile_id, key, keys) -> None:
    doc = _editable(profile_id)
    doc["modal"][key] = _profiles.check_modal(key, keys)
    _touch(profile_id)


def reset_modal(profile_id, key) -> None:
    doc = _editable(profile_id)
    doc["modal"].pop(key, None)
    _touch(profile_id)


def reset_profile(profile_id) -> None:
    doc = _editable(profile_id)
    doc["keys"] = {}
    doc["mouse"] = None
    doc["cursor"] = {}
    doc["modifiers"] = {}
    doc["modal"] = {}
    _touch(profile_id)


def export_profile(profile_id, path) -> None:
    doc = _profiles.export_document(resolved(profile_id), actions())
    _store.write_json(os.fspath(path), doc)


def import_profile(path) -> str:
    try:
        with open(os.fspath(path), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"This file is not a Quartz controls profile: {exc}") from exc
    doc = _profiles.import_document(data)
    doc["id"] = _new_id()
    doc["name"] = _unique_name(doc["name"])
    _store.state()["profiles"].append(doc)
    _store.state()["selected"] = doc["id"]
    _save()
    _emit()
    return doc["id"]


def bindings(action_id: str) -> list[tuple[str, str]]:
    return _dispatch().bindings(action_id)


def binding_text(action_id: str) -> str:
    return _dispatch().binding_text(action_id)


def tooltip(label: str, action_id: str) -> str:
    return _dispatch().tooltip(label, action_id)


def lookup(event, scope: str) -> str | None:
    return _dispatch().lookup(event, scope)


def hold_keys() -> set[int]:
    return _dispatch().hold_keys()


def held_set() -> set[int]:
    return _dispatch().held_set()


def is_navigation_press(event, held: set[int]) -> bool:
    return _dispatch().is_navigation_press(event, held)


def modifier_held(mods, role: str) -> bool:
    return _dispatch().modifier_held(mods, role)


def modal_key(event, key: str) -> bool:
    return _dispatch().modal_key(event, key)


def match_press(button: str, mods: set[str], held: set[int], double: bool = False) -> dict | None:
    return _profiles.match_press(active(), button, mods, held, double)


def modifier_name(role: str) -> str:
    return _profiles.modifier_name(active(), role)


def cursor(key: str):
    return active().cursor[key]


def conflicts(profile_id: str | None = None) -> list[tuple[str, str, str]]:
    return _profiles.conflicts(resolved(active_id() if profile_id is None else profile_id))
