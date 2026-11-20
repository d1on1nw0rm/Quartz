import sys
import traceback
from collections.abc import Callable
from typing import TypeVar

F = TypeVar("F")

BLENDER_HANDLER_NAMES: tuple[str, ...] = (
    "animation_playback_post",
    "animation_playback_pre",
    "annotation_post",
    "annotation_pre",
    "blend_import_post",
    "blend_import_pre",
    "composite_cancel",
    "composite_post",
    "composite_pre",
    "depsgraph_update_post",
    "depsgraph_update_pre",
    "exit_pre",
    "frame_change_post",
    "frame_change_pre",
    "load_factory_preferences_post",
    "load_factory_startup_post",
    "load_post",
    "load_post_fail",
    "load_pre",
    "object_bake_cancel",
    "object_bake_complete",
    "object_bake_pre",
    "redo_post",
    "redo_pre",
    "render_cancel",
    "render_complete",
    "render_init",
    "render_post",
    "render_pre",
    "render_stats",
    "render_write",
    "save_post",
    "save_post_fail",
    "save_pre",
    "translation_update_post",
    "undo_post",
    "undo_pre",
    "version_update",
    "xr_session_start_pre",
)

QUARTZ_HANDLER_NAMES: tuple[str, ...] = (
    "startup_post",
    "shutdown_pre",
    "shutdown_post",
    "addon_enable_post",
    "addon_disable_post",
)

ALL_HANDLER_NAMES: tuple[str, ...] = BLENDER_HANDLER_NAMES + QUARTZ_HANDLER_NAMES

for _name in ALL_HANDLER_NAMES:
    globals()[_name] = []

HANDLER_LISTS: dict[str, list] = {name: globals()[name] for name in ALL_HANDLER_NAMES}


def persistent(function: F) -> F:
    setattr(function, "_bpy_persistent", True)
    return function


def is_persistent(function: object) -> bool:
    return getattr(function, "_bpy_persistent", False) is True


def all_lists() -> dict[str, list]:
    return {name: globals()[name] for name in ALL_HANDLER_NAMES}


def dispatch(name: str, *args: object) -> list[BaseException]:
    if name not in ALL_HANDLER_NAMES:
        raise KeyError(name)
    lst = globals()[name]
    captured: list[BaseException] = []
    for fn in list(lst):
        try:
            fn(*args)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            captured.append(exc)
    return captured


def clear_non_persistent() -> int:
    removed = 0
    for name in ALL_HANDLER_NAMES:
        lst = globals()[name]
        new = [fn for fn in lst if is_persistent(fn)]
        removed += len(lst) - len(new)
        lst[:] = new
    return removed


def snapshot() -> dict[str, list]:
    return {name: list(globals()[name]) for name in ALL_HANDLER_NAMES}


def restore(snap: dict[str, list]) -> None:
    for name in ALL_HANDLER_NAMES:
        lst = globals()[name]
        if name in snap:
            lst[:] = list(snap[name])
        else:
            lst[:] = []
    for name, val in snap.items():
        if name not in ALL_HANDLER_NAMES:
            globals()[name] = list(val)
            HANDLER_LISTS[name] = globals()[name]
            ALL_HANDLER_NAMES
