from __future__ import annotations

from functools import partial
from typing import Callable

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from quartz_studio import icons, objects
from quartz_studio.modeling import get_tool, tool_ids
from quartz_studio.modeling import install as modeling_install
from quartz_studio.widgets import menu_bar, menus_data
from quartz_studio.widgets.common import prepare_popup
from quartz_studio.widgets.menu_bar import StudioMenu

__all__ = [
    "build_menu", "build_object_menu", "build_component_menu", "build_empty_menu",
    "build_create_menu", "build_param_menu", "show_menu", "find_canvas", "find_tree",
    "param_is_default", "reset_param", "delete_objects", "unparent_object", "unparent_objects",
    "set_enabled", "select_children", "SELECT_ORDER",
]

SELECT_ORDER = (
    "select_all", "deselect_all", "invert_selection", "select_connected", "grow_selection",
    "shrink_selection", None, "loop_selection", "ring_selection", "path_selection",
    "outline_selection", "fill_selection", None, "convert_selection",
)
CATEGORY_ICONS = {"null": "null", "spline": "spline", "mesh": "primitive", "generator": "generator"}
CATEGORY_TITLES = (("spline", "Spline"), ("mesh", "Mesh"), ("generator", "Generator"))
COMPONENT_MODES = ("points", "edges", "polygons")


def _new_menu(title: str, parent: QWidget | None) -> StudioMenu:
    menu = StudioMenu(title, parent)
    menu.setObjectName("qsContextMenu")
    return prepare_popup(menu)


def _add(menu: StudioMenu, text: str, handler: Callable[[], object], shortcut: str | None = None,
         icon: str | None = None, enabled: bool = True, **flags):
    act = menu.add_item(text, shortcut, icon, enabled, **flags)
    menu._handlers[act] = handler
    return act


def _sep(menu: StudioMenu) -> None:
    acts = menu.actions()
    if acts and not acts[-1].isSeparator():
        menu.addSeparator()


def _icon_if(name: str | None) -> str | None:
    return name if name and icons.has(name) else None


def find_canvas(widget: QWidget | None):
    window = widget.window() if widget is not None else None
    viewport = getattr(window, "viewport", None)
    canvas = getattr(viewport, "canvas", viewport)
    return canvas if canvas is not None and hasattr(canvas, "frame_all") else None


def find_tree(widget: QWidget | None):
    window = widget.window() if widget is not None else None
    manager = getattr(window, "object_manager", None)
    tree = getattr(manager, "tree", None)
    return tree if tree is not None and hasattr(tree, "rename") else None


def show_menu(menu: StudioMenu | None, point: QPoint):
    if menu is None or not any(not a.isSeparator() for a in menu.actions()):
        if menu is not None:
            menu.deleteLater()
        return None
    menu.aboutToHide.connect(menu.deleteLater)
    menu.popup(point)
    return menu


def delete_objects(scene, objs) -> None:
    targets = [o for o in objs if o in scene.objects]
    if not targets:
        return
    scene.begin_group()
    try:
        for obj in targets:
            if obj in scene.objects:
                scene.remove_object(obj)
    finally:
        scene.end_group()


def unparent_object(scene, obj) -> bool:
    if obj not in scene.objects or obj.parent is None:
        return False
    top = obj.parent
    while top.parent is not None:
        top = top.parent
    return scene.set_parent(obj, None, scene.children(None).index(top) + 1)


def unparent_objects(scene, objs) -> bool:
    targets = [o for o in objs if o in scene.objects and o.parent is not None]
    if not targets:
        return False
    done = False
    scene.begin_group()
    try:
        for obj in targets:
            done = unparent_object(scene, obj) or done
    finally:
        scene.end_group()
    return done


def set_enabled(scene, objs, flag: bool) -> None:
    targets = [o for o in objs if o in scene.objects]
    scene.begin_group()
    try:
        for obj in targets:
            scene.set_enabled(obj, flag)
    finally:
        scene.end_group()


def select_children(scene, obj) -> bool:
    objs = obj if isinstance(obj, (list, tuple)) else [obj]
    kids: list = []
    for o in objs:
        for kid in scene.children(o):
            if all(kid is not k for k in kids):
                kids.append(kid)
    if not kids:
        return False
    scene.select_objects(kids, "replace", active=kids[0])
    return True


def param_is_default(obj, param) -> bool:
    try:
        return param.clamp(obj.params.get(param.key, param.default)) == param.clamp(param.default)
    except (TypeError, ValueError):
        return False


def reset_param(scene, obj, key: str) -> bool:
    spec = scene._spec(obj.kind)
    param = spec.param(key) if spec is not None else None
    if param is None or obj not in scene.objects:
        return False
    return scene.set_param(obj, key, param.default)


def _binding(*action_ids: str) -> str | None:
    from quartz_studio import controls

    for action_id in action_ids:
        text = controls.binding_text(action_id)
        if text:
            return text
    return None


def _history(menu: StudioMenu, scene) -> None:
    _add(menu, "Undo", scene.undo, _binding("edit.undo"), "undo", scene.can_undo())
    _add(menu, "Redo", scene.redo, _binding("edit.redo"), "redo", scene.can_redo())


def _frame(menu: StudioMenu, canvas, selected: bool, everything: bool) -> None:
    if canvas is None:
        return
    if selected and hasattr(canvas, "frame_selection"):
        _add(menu, "Frame Selected", canvas.frame_selection, _binding("view.frame_selection"))
    if everything and hasattr(canvas, "frame_all"):
        _add(menu, "Frame All", canvas.frame_all, _binding("view.frame_all"))


def _spec_icon(spec) -> str:
    for name in (spec.icon, spec.id):
        if name and icons.has(name):
            return name
    return CATEGORY_ICONS[spec.category]


def _fill_create(menu: StudioMenu) -> None:
    for spec in objects.by_category("null"):
        _add(menu, spec.label, partial(menu_bar.create_object, spec.id), None, _spec_icon(spec))
    for category, title in CATEGORY_TITLES:
        sub = menu.add_submenu(title, [], CATEGORY_ICONS[category])
        if category == "spline":
            _add(sub, "Line", menu_bar.create_line, None, "m_line")
        if category == "mesh":
            _add(sub, "Empty Polygon", menu_bar.create_empty_polygon, None, "empty_polygon")
        for spec in objects.by_category(category):
            _add(sub, spec.label, partial(menu_bar.create_object, spec.id), None, _spec_icon(spec))


def build_create_menu(parent: QWidget | None = None) -> StudioMenu:
    menu = _new_menu("Create", parent)
    _fill_create(menu)
    return menu


def build_empty_menu(scene, canvas=None, parent: QWidget | None = None) -> StudioMenu:
    menu = _new_menu("Viewport", parent)
    _history(menu, scene)
    if canvas is not None:
        _sep(menu)
        _frame(menu, canvas, False, True)
    _sep(menu)
    sub = menu.add_submenu("Create", [], "plus")
    _fill_create(sub)
    return menu


def _object_targets(scene, obj) -> list:
    chosen = list(scene.selected_objects())
    return chosen if obj in chosen else [obj]


def build_object_menu(scene, obj, canvas=None, tree=None,
                      parent: QWidget | None = None) -> StudioMenu:
    menu = _new_menu("Object", parent)
    _history(menu, scene)
    if canvas is not None:
        _sep(menu)
        _frame(menu, canvas, True, True)
    _sep(menu)
    if not scene.is_editable(obj):
        spec = scene._spec(obj.kind)
        can = spec is not None and spec.category != "null"
        _add(menu, "Make Editable", partial(scene.make_editable, obj), None, "make_editable", can)
    targets = _object_targets(scene, obj)
    act = _add(menu, "Enabled", partial(set_enabled, scene, targets, not obj.enabled), None, None,
               True, check=bool(obj.enabled))
    act.setCheckable(True)
    act.setChecked(bool(obj.enabled))
    if tree is not None:
        _add(menu, "Rename", partial(tree.rename, obj))
    _sep(menu)
    _add(menu, "Group Objects", partial(scene.group_objects, targets))
    if any(o.parent is not None for o in targets):
        _add(menu, "Unparent", partial(unparent_objects, scene, targets))
    if any(scene.children(o) for o in targets):
        _add(menu, "Select Children", partial(select_children, scene, targets))
    _sep(menu)
    _add(menu, "Delete", partial(delete_objects, scene, targets))
    return menu


def _mesh_specs() -> dict:
    out: dict = {}
    for tool_id in tool_ids():
        spec = get_tool(tool_id)
        if spec.menu == modeling_install.PALETTE_MENU:
            out[modeling_install.LABEL_ALIASES.get(spec.name, spec.name)] = spec
            out.setdefault(spec.name, spec)
    return out


def _mesh_nodes(entries, specs: dict, mode: str) -> list:
    nodes: list = []
    for entry in entries:
        kind = entry[0]
        if kind in ("section", "sep"):
            nodes.append(("break",))
        elif kind == "submenu":
            children = _mesh_nodes(entry[2], specs, mode)
            if any(n[0] != "break" for n in children):
                nodes.append(("sub", entry[1], children))
        elif kind == "item":
            label = entry[1]
            if label == "Polygon Pen":
                nodes.append(("pen", entry[2] if len(entry) > 2 else None))
                continue
            spec = specs.get(label)
            if spec is not None and spec.id != "delete" and spec.supports(mode):
                nodes.append(("tool", spec))
    return nodes


def _emit_nodes(menu: StudioMenu, nodes: list) -> None:
    pending = False
    for node in nodes:
        if node[0] == "break":
            pending = True
            continue
        if pending:
            _sep(menu)
        pending = False
        if node[0] == "tool":
            spec = node[1]
            _add(menu, spec.name, partial(modeling_install.activate_tool, spec.id),
                 _binding("tool." + spec.id), _icon_if(icons.modeling_icon_name(spec.id)))
        elif node[0] == "pen":
            _add(menu, "Polygon Pen", menu_bar.polygon_pen, _binding("tool.pen"), "polygon_pen")
        elif node[0] == "sub":
            sub = menu.add_submenu(node[1], [])
            _emit_nodes(sub, node[2])


def _find_mesh_entries():
    for title, entries, _style in menus_data.MENU_BAR:
        if title == modeling_install.PALETTE_MENU:
            return entries
    return []


def _fill_select(menu: StudioMenu, mode: str) -> None:
    specs = {}
    for tool_id in tool_ids():
        spec = get_tool(tool_id)
        if spec.menu == "Select" and spec.supports(mode):
            specs[spec.id] = spec
    ordered: list = []
    for tool_id in SELECT_ORDER:
        if tool_id is None:
            ordered.append(None)
        elif tool_id in specs:
            ordered.append(specs.pop(tool_id))
    ordered.extend(specs.values())
    pending = False
    for item in ordered:
        if item is None:
            pending = True
            continue
        if pending:
            _sep(menu)
        pending = False
        _add(menu, item.name, partial(modeling_install.activate_tool, item.id),
             _binding("tool." + item.id), _icon_if(icons.modeling_icon_name(item.id)))


def build_component_menu(scene, canvas=None, parent: QWidget | None = None) -> StudioMenu:
    mode = scene.mode
    menu = _new_menu("Mesh", parent)
    _history(menu, scene)
    if canvas is not None:
        _sep(menu)
        _frame(menu, canvas, True, False)
    modeling_install.prepare()
    nodes = _mesh_nodes(_find_mesh_entries(), _mesh_specs(), mode)
    if any(n[0] != "break" for n in nodes):
        _sep(menu)
        _emit_nodes(menu, nodes)
    _sep(menu)
    select = menu.add_submenu("Select", [])
    _fill_select(select, mode)
    if not select.actions():
        menu.removeAction(select.menuAction())
        select.deleteLater()
    delete = get_tool("delete")
    if delete.supports(mode):
        _sep(menu)
        _add(menu, "Delete", partial(modeling_install.activate_tool, "delete"),
             _binding("tool.delete", "edit.delete"), _icon_if(icons.modeling_icon_name("delete")),
             scene.has_selection())
    return menu


def build_param_menu(scene, obj, key: str, parent: QWidget | None = None) -> StudioMenu:
    menu = _new_menu("Attribute", parent)
    spec = scene._spec(obj.kind) if obj is not None else None
    param = spec.param(key) if spec is not None else None
    if param is not None:
        _add(menu, "Reset to Default", partial(reset_param, scene, obj, key), None, None,
             not param_is_default(obj, param))
    return menu


def build_menu(scene, mode: str, target=None, *, canvas=None, tree=None,
               parent: QWidget | None = None) -> StudioMenu:
    if mode == "model":
        if target is not None:
            return build_object_menu(scene, target, canvas, tree, parent)
        return build_empty_menu(scene, canvas, parent)
    if mode in COMPONENT_MODES and scene.is_editable(scene.active):
        return build_component_menu(scene, canvas, parent)
    return build_empty_menu(scene, canvas, parent)
