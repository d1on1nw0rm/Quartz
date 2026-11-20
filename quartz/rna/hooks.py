from __future__ import annotations

from typing import Any, Callable

HOOK_NAMES: tuple[str, ...] = (
    "wrap_array",
    "current_context",
    "on_property_changed",
    "on_type_property_defined",
    "on_type_property_removed",
    "note_missing",
    "repr_root",
)


def _default_wrap_array(values, pdef, inst, on_write):
    try:
        from .collections import PropArray
    except Exception:
        return values
    return PropArray(values, on_write=on_write, owner=inst, pdef=pdef)


def _default_current_context():
    return None


def _default_on_property_changed(inst, pdef):
    return None


def _default_on_type_property_defined(cls, identifier):
    return None


def _default_on_type_property_removed(cls, identifier):
    return None


def _default_note_missing(symbol):
    return None


def _default_repr_root():
    return "quartz"


_DEFAULTS: dict[str, Callable] = {
    "wrap_array": _default_wrap_array,
    "current_context": _default_current_context,
    "on_property_changed": _default_on_property_changed,
    "on_type_property_defined": _default_on_type_property_defined,
    "on_type_property_removed": _default_on_type_property_removed,
    "note_missing": _default_note_missing,
    "repr_root": _default_repr_root,
}

_STATE: dict[str, Callable] = dict(_DEFAULTS)


def _get(name: str) -> Callable:
    if name not in HOOK_NAMES:
        raise TypeError(f"unknown hook {name!r}")
    return _STATE[name]


def wrap_array(values, pdef, inst, on_write):
    return _STATE["wrap_array"](values, pdef, inst, on_write)


def current_context():
    return _STATE["current_context"]()


def on_property_changed(inst, pdef):
    return _STATE["on_property_changed"](inst, pdef)


def on_type_property_defined(cls, identifier):
    return _STATE["on_type_property_defined"](cls, identifier)


def on_type_property_removed(cls, identifier):
    return _STATE["on_type_property_removed"](cls, identifier)


def note_missing(symbol):
    return _STATE["note_missing"](symbol)


def repr_root():
    return _STATE["repr_root"]()


def install(**implementations):
    for name, impl in implementations.items():
        if name not in HOOK_NAMES:
            raise TypeError(f"unknown hook {name!r}")
        if impl is None:
            _STATE[name] = _DEFAULTS[name]
        else:
            _STATE[name] = impl


def reset():
    _STATE.clear()
    _STATE.update(_DEFAULTS)


def snapshot():
    return dict(_STATE)


def restore(snap):
    _STATE.clear()
    _STATE.update(snap)
