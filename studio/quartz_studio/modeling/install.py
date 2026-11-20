from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from PySide6.QtWidgets import QMainWindow, QToolTip

from .. import scene as scene_module
from ..scene import get_scene
from .registry import get_tool, tool_ids
from .session import EDITABLE_MESSAGE, ModelingController, editable

__all__ = ["prepare", "install", "activate_tool", "controller", "SECTION_ORDER", "PALETTE_GROUPS",
           "MORE_GROUP", "PaletteGroup", "palette_groups", "tool_tooltip"]

SECTION_ORDER = ("CONVERSION", "CREATION TOOLS", "CUT", "TRANSFORM", "COMMANDS", "NORMALS")
SUBMENU_FOR = {"COMMANDS": "Commands", "NORMALS": "Normals"}
LABEL_ALIASES = {"Convert Selection": "Convert Selection Mode..."}

PALETTE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Extrude", ("extrude", "inset", "matrix_extrude", "smooth_shift", "thicken", "trunk")),
    ("Bevel", ("bevel",)),
    ("Cut", ("loop_path_cut", "line_cut", "plane_cut", "edge_cut")),
    ("Bridge", ("bridge", "weld", "stitch_and_sew", "connect_points_edges", "close_polygon_hole")),
    ("Dissolve", ("dissolve", "melt", "collapse", "delete", "optimize", "disconnect", "split")),
    ("Slide", ("slide", "iron", "equal_spacing", "straighten_edges", "fit_circle", "flatten",
               "smooth_edges", "randomize", "set_flow", "set_point_value")),
    ("Normals", ("normal_move", "normal_scale", "normal_rotate", "reverse_normals", "align_normals")),
    ("Subdivide", ("subdivide", "triangulate", "untriangulate", "remove_ngons",
                   "retriangulate_ngons", "spin_edge")),
    ("Clone", ("array", "clone", "mirror", "edge_to_spline")),
)
MORE_GROUP = "More"
PALETTE_MENU = "Mesh"

_PREPARED = False
_CONTROLLER: ModelingController | None = None


def controller() -> ModelingController:
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = ModelingController(get_scene())
    return _CONTROLLER


def _extend_scene_tools() -> None:
    ids = tuple(i for i in tool_ids() if i not in scene_module.TOOLS)
    if ids:
        scene_module.TOOLS = tuple(scene_module.TOOLS) + ids
    scene_module.COMMAND_TOOLS = frozenset(i for i in tool_ids() if not get_tool(i).interactive)
    try:
        from ..widgets import viewport as vp
    except Exception:
        return
    names = getattr(vp, "TOOL_NAMES", None)
    if isinstance(names, dict):
        for i in tool_ids():
            names.setdefault(i, get_tool(i).name)


@dataclass(frozen=True)
class PaletteGroup:
    name: str
    specs: tuple


def palette_groups(menu: str = PALETTE_MENU) -> list[PaletteGroup]:
    _extend_scene_tools()
    wanted = [i for i in tool_ids() if get_tool(i).menu == menu]
    placed: set[str] = set()
    groups: list[PaletteGroup] = []
    for name, ids in PALETTE_GROUPS:
        members = []
        for tool_id in ids:
            if tool_id in wanted and tool_id not in placed:
                placed.add(tool_id)
                members.append(get_tool(tool_id))
        if members:
            groups.append(PaletteGroup(name, tuple(members)))
    rest = tuple(get_tool(i) for i in wanted if i not in placed)
    if rest:
        groups.append(PaletteGroup(MORE_GROUP, rest))
    return groups


def tool_tooltip(spec) -> str:
    from .. import controls

    return controls.tooltip(spec.name, "tool." + spec.id)


def _is_item(entry) -> bool:
    return isinstance(entry, tuple) and len(entry) >= 2 and entry[0] == "item"


def _find_submenu(entries: list, label: str) -> list | None:
    for entry in entries:
        if isinstance(entry, tuple) and entry and entry[0] == "submenu" and entry[1] == label:
            return entry[2]
    return None


def _find_item(entries: list, label: str) -> int | None:
    for k, entry in enumerate(entries):
        if _is_item(entry) and entry[1] == label:
            return k
    return None


def _locate(entries: list, label: str, trail: tuple = ()) -> tuple | None:
    k = _find_item(entries, label)
    if k is not None:
        return entries, k, trail
    for entry in entries:
        if isinstance(entry, tuple) and len(entry) >= 3 and entry[0] == "submenu":
            found = _locate(entry[2], label, trail + (entry[1],))
            if found is not None:
                return found
    return None


def _section_index(entries: list, title: str) -> int | None:
    for k, entry in enumerate(entries):
        if isinstance(entry, tuple) and entry and entry[0] == "section" and entry[1] == title:
            return k
    return None


def _section_end(entries: list, start: int) -> int:
    k = start + 1
    while k < len(entries):
        entry = entries[k]
        if isinstance(entry, tuple) and entry and entry[0] in ("section", "sep"):
            break
        k += 1
    return k


def _with_shortcut(entries: list, k: int, shortcut: str | None) -> None:
    entry = entries[k]
    entries[k] = (entry[0], entry[1], shortcut) + tuple(entry[3:])


def _menu_root(md, title: str) -> list:
    for t, entries, _style in md.MENU_BAR:
        if t == title:
            return entries
    root: list = []
    md.MENU_BAR.append((title, root, None))
    return root


def _place_tool(md, spec) -> tuple[str, ...]:
    root = _menu_root(md, spec.menu)
    label = LABEL_ALIASES.get(spec.name, spec.name)
    found = _locate(root, label) or _locate(root, spec.name)
    if found is not None:
        entries, k, trail = found
        _with_shortcut(entries, k, spec.shortcut)
        return (spec.menu, *trail, entries[k][1])
    sub_label = SUBMENU_FOR.get(spec.section)
    if sub_label is not None:
        sub = _find_submenu(root, sub_label)
        if sub is None:
            sub = []
            root.append(md.sub(sub_label, sub))
        sub.append(md.item(spec.name, spec.shortcut))
        return (spec.menu, sub_label, spec.name)
    idx = _section_index(root, spec.section)
    if idx is None:
        root.append(md.section(spec.section))
        idx = len(root) - 1
    root.insert(_section_end(root, idx), md.item(spec.name, spec.shortcut))
    return (spec.menu, spec.name)


def _clear_foreign_chords(entries: list, installed: set[str]) -> None:
    for k, entry in enumerate(entries):
        if not isinstance(entry, tuple) or not entry:
            continue
        if entry[0] == "submenu":
            _clear_foreign_chords(entry[2], installed)
        elif _is_item(entry) and len(entry) > 2 and entry[2] and "~" in entry[2] \
                and entry[2].upper() not in installed:
            _with_shortcut(entries, k, None)


def prepare() -> None:
    global _PREPARED
    if _PREPARED:
        return
    _PREPARED = True
    _extend_scene_tools()
    from ..widgets import menu_bar as mb
    from ..widgets import menus_data as md

    mesh_menu = getattr(md, "MESH_MENU", None)
    if mesh_menu is None:
        mesh_menu = []
        md.MESH_MENU = mesh_menu
    if not any(title == "Mesh" for title, _entries, _style in md.MENU_BAR):
        md.MENU_BAR.append(("Mesh", mesh_menu, None))
    for tool_id in tool_ids():
        spec = get_tool(tool_id)
        path = _place_tool(md, spec)
        mb.SCENE_COMMANDS.append((path, partial(activate_tool, tool_id)))
    from . import select_tools

    appended: set[tuple[str, ...]] = set()
    for path, command in select_tools.menu_commands():
        if tuple(path) not in appended:
            appended.add(tuple(path))
            mb.SCENE_COMMANDS.append((tuple(path), command))
    installed = {"M~E"}
    for tool_id in tool_ids():
        shortcut = get_tool(tool_id).shortcut
        if shortcut and "~" in shortcut:
            installed.add(shortcut.upper())
    for _title, entries, _style in md.MENU_BAR:
        _clear_foreign_chords(entries, installed)


def activate_tool(tool_id: str) -> None:
    scene = get_scene()
    spec = get_tool(tool_id)
    ctl = controller()
    active = scene.active
    if active is not None and not editable(scene, active):
        ctl.message.emit(f"{spec.name}: {EDITABLE_MESSAGE}")
        return
    if scene.mode not in spec.modes:
        target = "polygons" if "polygons" in spec.modes else spec.modes[0]
        if target in scene_module.MODES:
            scene.set_mode(target)
    scene.set_tool(tool_id)
    ctl.activate(tool_id)
    if not spec.interactive:
        ctl.apply_once()


def _right_splitter(window: QMainWindow):
    return getattr(window, "manager_splitter", None)


def install(window: QMainWindow):
    prepare()
    from .interaction import ViewportToolFilter
    from .panel import ToolOptionsPanel

    ctl = controller()
    scene = get_scene()
    if getattr(window, "_modeling_installed", False):
        return ctl
    window._modeling_installed = True
    panel = ToolOptionsPanel(ctl)
    splitter = _right_splitter(window)
    if splitter is not None:
        splitter.insertWidget(1, panel)
        splitter.setStretchFactor(1, 0)
    else:
        panel.setParent(window)
    panel.setVisible(False)
    window.tool_options = panel
    viewport = getattr(window, "viewport", None)
    canvas = getattr(viewport, "canvas", viewport)
    if canvas is not None:
        window.modeling_filter = ViewportToolFilter(canvas, ctl)
    from . import select_interaction

    window.selection_filter = select_interaction.install(window)

    def on_tool(tool: str) -> None:
        if ctl.tool_id is not None and tool != ctl.tool_id:
            ctl.activate(None)

    scene.toolChanged.connect(on_tool)

    def on_message(text: str) -> None:
        bar = window.statusBar() if hasattr(window, "statusBar") else None
        if bar is not None and bar.isVisible():
            bar.showMessage(text, 4000)
        target = canvas if canvas is not None else window
        QToolTip.showText(target.mapToGlobal(target.rect().center()), text, target)

    ctl.message.connect(on_message)
    if getattr(window, "controls_filter", None) is None:
        from .. import controls

        controls.install(window)
    return ctl
