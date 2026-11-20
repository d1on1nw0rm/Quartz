from __future__ import annotations

from . import core
from .core import (evaluate, insert_key, record_active, record_points, set_frame, set_key, set_time_settings,
                   time_settings)
from .player import AnimContext, AutoKey, Player, get_context

__all__ = [
    "core",
    "evaluate",
    "insert_key",
    "record_active",
    "record_points",
    "set_frame",
    "set_key",
    "set_time_settings",
    "time_settings",
    "AnimContext",
    "AutoKey",
    "Player",
    "get_context",
    "TimelineBar",
    "DopeSheet",
    "CurveEditor",
    "commands",
    "docks",
    "pages",
    "key_actions",
]


def __getattr__(name: str):
    if name == "TimelineBar":
        from .timeline import TimelineBar
        return TimelineBar
    if name == "DopeSheet":
        from .dopesheet import DopeSheet
        return DopeSheet
    if name == "CurveEditor":
        from .curves import CurveEditor
        return CurveEditor
    raise AttributeError(name)


def _ctx() -> AnimContext:
    return get_context(None)


def _toggle_loop() -> bool:
    c = _ctx()
    mode = "simple" if c.playback_mode() == "loop" else "loop"
    return c.set_playback_mode(mode) == "loop"


def _preview_to_keys() -> tuple:
    c = _ctx()
    rng = core.key_range(c.targets() or core.animated_objects(c.scene))
    if rng is None:
        return ()
    s = c.settings()
    lo, hi = int(rng[0]), int(rng[1])
    with core.edit_group(c.scene):
        c.set_settings(min=min(s["min"], lo), max=max(s["max"], hi))
        c.set_settings(preview_min=lo, preview_max=hi)
    return lo, hi


def _actions() -> list:
    return [
        ("Record Active Objects", "F9", lambda: _ctx().record()),
        ("Autokeying", "Ctrl+F9", lambda: _ctx().autokey.toggle()),
        ("Add Parameter Keys", "", lambda: _ctx().record_params()),
        ("Record Position", "", lambda: _ctx().record(core.POSITION_CHANNELS)),
        ("Record Rotation", "", lambda: _ctx().record(core.ROTATION_CHANNELS)),
        ("Record Scale", "", lambda: _ctx().record(core.SCALE_CHANNELS)),
        ("Record Visibility", "", lambda: _ctx().record_visibility()),
        ("Go to Start", "Shift+G", lambda: _ctx().player.go_start()),
        ("Go to Previous Frame", ",", lambda: _ctx().player.prev_frame()),
        ("Play Backwards", "F6", lambda: _ctx().player.toggle(-1)),
        ("Play Forwards", "F8", lambda: _ctx().player.toggle(1)),
        ("Stop", "F7", lambda: _ctx().player.stop()),
        ("Go to Next Frame", ".", lambda: _ctx().player.next_frame()),
        ("Go to End", "Shift+F", lambda: _ctx().player.go_end()),
        ("Go to Previous Key", "Ctrl+F", lambda: _ctx().player.prev_key()),
        ("Go to Next Key", "Ctrl+G", lambda: _ctx().player.next_key()),
        ("Loop Playback", "", _toggle_loop),
        ("Record Points", "", lambda: _ctx().record_points()),
        ("Record Point Selection", "", lambda: _ctx().record_point_selection()),
        ("Clear Points", "", lambda: _ctx().clear_points()),
        ("Delete Selected Keys", "", lambda: _ctx().delete_selected()),
        ("Delete Keys at Current Frame", "", lambda: _ctx().delete_at_frame()),
        ("Delete Tracks of Active Objects", "", lambda: _ctx().delete_tracks()),
        ("Copy Keys", "", lambda: _ctx().copy_selected()),
        ("Paste Keys", "", lambda: _ctx().paste()),
        ("Reverse Keys", "", lambda: _ctx().reverse_selected()),
        ("Preview Range to Keys", "", _preview_to_keys),
        ("Bake Objects", "", lambda: _ctx().bake()),
    ]


_MENU_PATHS = {
    "Record Points": ("Animate", "Point Level Animation", "Record Points"),
    "Record Point Selection": ("Animate", "Point Level Animation", "Record Point Selection"),
    "Clear Points": ("Animate", "Point Level Animation", "Clear Points"),
}


def key_actions() -> list:
    return [(name, shortcut, fn) for name, shortcut, fn in _actions()]


def commands() -> list:
    out = [(_MENU_PATHS.get(name, ("Animate", name)), fn) for name, _s, fn in _actions()]
    for rate in (24, 25, 30, 48, 50, 60):
        out.append((("Animate", "Change Frame Rate Keeping Timing", f"{rate} fps"), lambda r=rate: _ctx().retime(r)))
    for text, mode in (("Simple", "simple"), ("Loop", "loop"), ("Ping-Pong", "pingpong")):
        out.append((("Animate", "Playback Mode", text), lambda m=mode: _ctx().set_playback_mode(m)))
    for text, mode in (("Spline", "spline"), ("Linear", "linear"), ("Step", "step")):
        out.append((("Animate", "Interpolation", text), lambda m=mode: _ctx().set_interp(m)))
    for text, mode in (("None", "none"), ("Ease In", "in"), ("Ease Out", "out"), ("Ease In Out", "both")):
        out.append((("Animate", "Ease", text), lambda m=mode: _ctx().set_ease(m)))
    return out


def _timeline(scene=None, parent=None):
    from .timeline import TimelineBar
    return TimelineBar(scene, parent)


def _dopesheet(scene=None, parent=None):
    from .dopesheet import DopeSheet
    return DopeSheet(scene, parent)


def _curves(scene=None, parent=None):
    from .curves import CurveEditor
    return CurveEditor(scene, parent)


def docks() -> list:
    return [
        ("Timeline", _timeline, "bottom"),
        ("Dope Sheet", _dopesheet, "bottom"),
        ("F-Curves", _curves, "bottom"),
    ]


def pages() -> list:
    return [("Animate", ["Timeline", "Dope Sheet", "F-Curves"])]
