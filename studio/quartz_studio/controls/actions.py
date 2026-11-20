from __future__ import annotations

import re
import sys
import types
from dataclasses import dataclass, replace
from functools import partial
from typing import Callable

SCOPES = ("global", "viewport", "objects")
CATEGORIES = ("File", "Edit", "Modes", "Tools", "Mesh", "Select", "Create", "View", "Cameras", "Objects")
CAMERA_PRESETS = ("Perspective", "Parallel", "Left", "Right", "Front", "Back", "Top", "Bottom", "Isometric",
                  "Dimetric")
NAV_PIVOTS = ("Cursor", "Center", "Object", "Camera")
ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


@dataclass
class Action:
    id: str
    label: str
    category: str
    run: Callable[[], object]
    scope: str = "global"
    available: Callable[[], bool] | None = None
    repeat: bool = False
    default_keys: tuple[str, ...] = ()
    path: tuple[str, ...] | None = None


def _window():
    from quartz_studio import controls

    return controls.window()


def _scene():
    from quartz_studio.scene import get_scene

    return get_scene()


def _project(name: str, *args) -> object:
    from quartz_studio import project

    return getattr(project, name)(*args)


def _menu_bar(name: str, *args) -> object:
    from quartz_studio.widgets import menu_bar

    return getattr(menu_bar, name)(*args)


def _canvas_call(name: str, *args) -> object:
    win = _window()
    if win is None:
        return None
    return getattr(win.viewport.canvas, name)(*args)


def _tree_call(name: str) -> object:
    win = _window()
    if win is None:
        return None
    return getattr(win.object_manager.tree, name)()


def _activate(tool_id: str) -> object:
    from quartz_studio.modeling import install

    return install.activate_tool(tool_id)


def _select_all() -> object:
    scene = _scene()
    if scene.mode == "model":
        return scene.select_all_objects()
    return _activate("select_all")


def _undo() -> None:
    _scene().undo()


def _redo() -> None:
    _scene().redo()


def _delete() -> None:
    scene = _scene()
    if scene.mode == "model":
        from quartz_studio.widgets import context_menu

        context_menu.delete_objects(scene, scene.selected_objects())
    else:
        _activate("delete")


def _can_delete() -> bool:
    scene = _scene()
    if scene.mode == "model":
        return bool(scene.selected_objects())
    return bool(scene.has_selection())


def _open_controls() -> object:
    from quartz_studio.controls import editor

    return editor.open_editor(_window())


def _set_mode(mode: str) -> None:
    _scene().set_mode(mode)


def _set_tool(tool: str) -> None:
    _scene().set_tool(tool)


def _can_make_editable() -> bool:
    return bool(_menu_bar("can_make_editable"))


def _tree_has_selection() -> bool:
    win = _window()
    if win is None:
        return False
    scene = _scene()
    return scene.active is not None and scene.active in scene.objects


def _tree_not_editing() -> bool:
    win = _window()
    if win is None:
        return False
    from PySide6.QtWidgets import QAbstractItemView

    return win.object_manager.tree.state() != QAbstractItemView.State.EditingState


def _core() -> list[Action]:
    a = Action
    out = [
        a("file.new", "New Project", "File", partial(_project, "new_project")),
        a("file.open", "Open Project", "File", partial(_project, "open_project")),
        a("file.merge", "Merge Project", "File", partial(_project, "merge_project")),
        a("file.save", "Save Project", "File", partial(_project, "save_project")),
        a("file.save_as", "Save Project As", "File", partial(_project, "save_project_as")),
        a("file.save_incremental", "Save Incremental", "File", partial(_project, "save_incremental")),
        a("file.import", "Import", "File", partial(_project, "import_files")),
        a("file.export_selection", "Export Selection", "File", partial(_project, "export_selection")),
        a("file.clear_recent", "Clear Recent File List", "File", partial(_project, "clear_recent")),
        a("file.exit", "Exit", "File", partial(_project, "exit_app")),
        a("edit.undo", "Undo", "Edit", _undo),
        a("edit.redo", "Redo", "Edit", _redo),
        a("edit.delete", "Delete", "Edit", _delete, scope="viewport", available=_can_delete),
        a("app.controls", "Controls", "Edit", _open_controls),
        a("mode.points", "Points", "Modes", partial(_set_mode, "points")),
        a("mode.edges", "Edges", "Modes", partial(_set_mode, "edges")),
        a("mode.polygons", "Polygons", "Modes", partial(_set_mode, "polygons")),
        a("mode.model", "Model", "Modes", partial(_set_mode, "model")),
        a("tool.select", "Selection", "Tools", partial(_set_tool, "select"), scope="viewport"),
        a("tool.move", "Move", "Tools", partial(_set_tool, "move"), scope="viewport"),
        a("tool.rotate", "Rotate", "Tools", partial(_set_tool, "rotate"), scope="viewport"),
        a("tool.scale", "Scale", "Tools", partial(_set_tool, "scale"), scope="viewport"),
        a("tool.pen", "Polygon Pen", "Tools", partial(_menu_bar, "polygon_pen")),
        a("tool.line_pen", "Pen", "Tools", partial(_set_tool, "line_pen")),
        a("object.make_editable", "Make Editable", "Objects", partial(_menu_bar, "make_editable"),
          available=_can_make_editable),
        a("object.rename", "Rename", "Objects", partial(_tree_call, "rename"), scope="objects",
          available=_tree_has_selection),
        a("object.delete", "Delete Object", "Objects", partial(_tree_call, "delete_active"), scope="objects",
          available=_tree_not_editing),
        a("view.undo", "Undo View", "View", partial(_canvas_call, "undo_view"), scope="viewport", repeat=True),
        a("view.redo", "Redo View", "View", partial(_canvas_call, "redo_view"), scope="viewport", repeat=True),
        a("view.frame_default", "Frame Default", "View", partial(_canvas_call, "reset_camera"), scope="viewport"),
        a("view.frame_all", "Frame Geometry", "View", partial(_canvas_call, "frame_all"), scope="viewport"),
        a("view.frame_selection", "Frame Selected Elements", "View", partial(_canvas_call, "frame_selection"),
          scope="viewport"),
        a("view.frame_objects", "Frame Selected Objects", "View", partial(_canvas_call, "frame_active"),
          scope="viewport"),
    ]
    for name in CAMERA_PRESETS:
        out.append(a("camera." + name.lower(), name, "Cameras", partial(_canvas_call, "set_view", name),
                     scope="viewport"))
    for name in NAV_PIVOTS:
        out.append(a("camera.pivot." + name.lower(), "Navigation: " + name, "Cameras",
                     partial(_canvas_call, "set_nav_pivot", name), scope="viewport"))
    return out


CORE: tuple[Action, ...] = tuple(_core())

MENU_IDS: dict[tuple[str, ...], str] = {
    ("File", "New Project"): "file.new",
    ("File", "Open Project..."): "file.open",
    ("File", "Open Recent", "Clear Recent File List"): "file.clear_recent",
    ("File", "Merge Project..."): "file.merge",
    ("File", "Save Project"): "file.save",
    ("File", "Save Project As..."): "file.save_as",
    ("File", "Save Incremental"): "file.save_incremental",
    ("File", "Import..."): "file.import",
    ("File", "Export", "Export Selection..."): "file.export_selection",
    ("File", "Exit"): "file.exit",
    ("Edit", "Undo"): "edit.undo",
    ("Edit", "Redo"): "edit.redo",
    ("Edit", "Controls..."): "app.controls",
    ("Mesh", "Make Editable"): "object.make_editable",
    ("Mesh", "Polygon Pen"): "tool.pen",
    ("Create", "Spline", "Line"): "create.line",
    ("Create", "Mesh", "Empty Polygon"): "create.empty_polygon",
}

_EXTRA: dict[str, Action] = {}
_REGISTRY: list[dict[str, Action] | None] = [None]
_PATHS: dict[tuple[str, ...], str] = {}


def _part_slug(part: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(part).lower()).strip("_")


def slug(path) -> str:
    return "menu." + ".".join(p for p in (_part_slug(x) for x in path) if p)


def menu_label(text: str) -> str:
    text = str(text).split("\t", 1)[0].strip()
    while text.endswith("."):
        text = text[:-1]
    return text.rstrip()


def _partial_of(handler, name: str):
    if isinstance(handler, partial) and getattr(handler.func, "__name__", "") == name and handler.args:
        return handler.args[0]
    return None


def menu_action_id(path, handler=None) -> str:
    path = tuple(path)
    tool = _partial_of(handler, "activate_tool")
    if tool is None and str(getattr(getattr(handler, "func", None), "__module__", "")).endswith("select_tools"):
        tool = _partial_of(handler, "activate")
    if tool is not None:
        return "tool." + str(tool)
    obj = _partial_of(handler, "create_object")
    if obj is not None:
        return "create." + str(obj)
    fmt = _partial_of(handler, "export_as")
    if fmt is not None:
        return "file.export." + str(fmt)
    if path in MENU_IDS:
        return MENU_IDS[path]
    return slug(path)


def action_for_path(path) -> str | None:
    registry()
    return _PATHS.get(tuple(path))


def _tool_name(names: dict, key: str, fallback: str) -> str:
    return names.get(key, fallback)


def collect() -> dict[str, Action]:
    from quartz_studio import fileio
    from quartz_studio import objects
    from quartz_studio.modeling import registry as tool_registry
    from quartz_studio.widgets import menu_bar

    try:
        from quartz_studio.widgets.viewport import TOOL_NAMES
    except ImportError:
        TOOL_NAMES = {}

    out: dict[str, Action] = {}
    paths: dict[tuple[str, ...], str] = {}

    def add(action: Action) -> None:
        if action.id not in out:
            out[action.id] = action

    for action in CORE:
        if action.id.startswith("tool.") and action.id[5:] in TOOL_NAMES:
            action = replace(action, label=_tool_name(TOOL_NAMES, action.id[5:], action.label))
        else:
            action = replace(action)
        add(action)
    for fmt in fileio.exporters():
        add(Action("file.export." + fmt.id, fmt.label, "File", partial(_project, "export_as", fmt.id)))
    for tool_id in tool_registry.tool_ids():
        spec = tool_registry.get_tool(tool_id)
        available = None
        if tool_id == "delete":
            available = _not_model
        run = _select_all if tool_id == "select_all" else partial(_activate, spec.id)
        add(Action("tool." + spec.id, spec.name, spec.menu, run, available=available))
    try:
        from quartz_studio.modeling import select_tools
    except ImportError:
        select_tools = None
    for tool in getattr(select_tools, "TOOLS", ()):
        add(Action("tool." + tool.id, tool.name, "Select", partial(select_tools.activate, tool.id)))
    for spec in objects.all_specs():
        add(Action("create." + spec.id, spec.label, "Create", partial(menu_bar.create_object, spec.id)))
    add(Action("create.line", "Line", "Create", menu_bar.create_line))
    add(Action("create.empty_polygon", "Empty Polygon", "Create", menu_bar.create_empty_polygon))
    enabled = getattr(menu_bar, "SCENE_ENABLED", {})
    for path, handler in list(menu_bar.SCENE_COMMANDS):
        path = tuple(path)
        aid = menu_action_id(path, handler)
        paths.setdefault(path, aid)
        if aid in out:
            if out[aid].path is None:
                out[aid].path = path
            continue
        if aid in _EXTRA:
            continue
        add(Action(aid, menu_label(path[-1]), str(path[0]), handler, available=enabled.get(path), path=path))
    for aid, action in _EXTRA.items():
        if aid not in out:
            out[aid] = action
            if action.path is not None:
                paths.setdefault(action.path, aid)
    _REGISTRY[0] = out
    _PATHS.clear()
    _PATHS.update(paths)
    _changed()
    return out


def _not_model() -> bool:
    return _scene().mode != "model"


def _changed() -> None:
    from quartz_studio import controls

    controls._invalidate()


def registry() -> dict[str, Action]:
    if _REGISTRY[0] is None:
        return collect()
    return _REGISTRY[0]


def known() -> dict[str, Action]:
    if _REGISTRY[0] is not None:
        return _REGISTRY[0]
    out = {a.id: a for a in CORE}
    for aid, action in _EXTRA.items():
        out.setdefault(aid, action)
    return out


def register_action(id, label, category, run, keys=(), scope="global", available=None,
                    path=None) -> Action:
    aid = str(id)
    if not ID_RE.match(aid):
        raise ValueError(f"invalid action id {aid!r}")
    if scope not in SCOPES:
        raise ValueError(f"invalid scope {scope!r}")
    keys = tuple(k for k in (keys or ()) if k)
    action = Action(aid, str(label), str(category), run, scope=scope, available=available,
                    default_keys=keys, path=tuple(path) if path else None)
    previous = _EXTRA.get(aid)
    _EXTRA[aid] = action
    current = _REGISTRY[0]
    if current is not None and (aid not in current or current[aid] is previous):
        current[aid] = action
        if action.path is not None:
            _PATHS.setdefault(action.path, aid)
    _changed()
    return action


def clear_extra() -> None:
    _EXTRA.clear()
    _REGISTRY[0] = None
    _PATHS.clear()
    _changed()


class _ActionsModule(types.ModuleType):
    def __call__(self) -> dict[str, Action]:
        return registry()


sys.modules[__name__].__class__ = _ActionsModule
