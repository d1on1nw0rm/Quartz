from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Callable

from quartz_studio import prefs

__all__ = ["SHADINGS", "TOGGLES", "PREFIX", "DisplayFilter", "load", "save", "set_shading", "toggle",
           "reset", "is_display_key", "menu_entries", "menu_commands", "menu_checks"]

SHADINGS: tuple[tuple[str, str], ...] = (
    ("shaded_lines", "Shaded with Lines"),
    ("shaded", "Shaded"),
    ("wireframe", "Wireframe"),
    ("hidden_line", "Hidden Line"),
    ("isoparms", "Isoparms"),
)
TOGGLES: tuple[tuple[str, str], ...] = (
    ("ngon_lines", "N-gon Lines"),
    ("points", "Points"),
    ("world_axis", "World Axis"),
    ("horizon", "Horizon"),
    ("axis_triad", "Axis Triad"),
    ("gizmo", "Gizmo"),
    ("hud", "Tool HUD"),
    ("selection_outline", "Selection Outline"),
)
PREFIX = "display."
SHADING_KEY = PREFIX + "shading"
RESET_LABEL = "Reset Display"
DEFAULT_SHADING = SHADINGS[0][0]
_SHADING_IDS = frozenset(k for k, _label in SHADINGS)
_TOGGLE_IDS = frozenset(k for k, _label in TOGGLES)


@dataclass
class DisplayFilter:
    shading: str = DEFAULT_SHADING
    ngon_lines: bool = True
    points: bool = True
    world_axis: bool = True
    horizon: bool = True
    axis_triad: bool = True
    gizmo: bool = True
    hud: bool = True
    selection_outline: bool = True


def is_display_key(key) -> bool:
    return isinstance(key, str) and key.startswith(PREFIX)


def load() -> DisplayFilter:
    state = DisplayFilter()
    for f in fields(DisplayFilter):
        value = prefs.get(PREFIX + f.name)
        if f.name == "shading":
            if isinstance(value, str) and value in _SHADING_IDS:
                state.shading = value
        elif isinstance(value, bool):
            setattr(state, f.name, value)
    return state


def save(state: DisplayFilter) -> None:
    for f in fields(DisplayFilter):
        prefs.set(PREFIX + f.name, getattr(state, f.name))


def set_shading(key: str) -> None:
    if key not in _SHADING_IDS:
        return
    state = load()
    state.shading = key
    save(state)


def toggle(key: str) -> None:
    if key not in _TOGGLE_IDS:
        return
    state = load()
    setattr(state, key, not getattr(state, key))
    save(state)


def reset() -> None:
    for f in fields(DisplayFilter):
        prefs.set(PREFIX + f.name, None)


def menu_entries() -> tuple[list, list]:
    display = [("check", label, key == DEFAULT_SHADING) for key, label in SHADINGS]
    flt = [("check", label, True) for _key, label in TOGGLES]
    flt.extend([("sep",), ("item", RESET_LABEL)])
    return display, flt


def menu_commands() -> list[tuple[tuple[str, ...], Callable[[], None]]]:
    out: list[tuple[tuple[str, ...], Callable[[], None]]] = []
    for key, label in SHADINGS:
        out.append((("Window", "Display", label), lambda k=key: set_shading(k)))
    for key, label in TOGGLES:
        out.append((("Window", "Filter", label), lambda k=key: toggle(k)))
    out.append((("Window", "Filter", RESET_LABEL), reset))
    return out


def menu_checks() -> dict[tuple[str, ...], Callable[[], bool]]:
    out: dict[tuple[str, ...], Callable[[], bool]] = {}
    for key, label in SHADINGS:
        out[("Window", "Display", label)] = lambda k=key: load().shading == k
    for key, label in TOGGLES:
        out[("Window", "Filter", label)] = lambda k=key: bool(getattr(load(), k))
    return out
