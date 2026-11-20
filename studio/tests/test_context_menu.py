from __future__ import annotations

import logging
import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QWidget

from quartz_studio import objects
from quartz_studio.app import create_app
from quartz_studio.modeling import get_tool, tool_ids
from quartz_studio.scene import Mesh

LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier
ALT = Qt.KeyboardModifier.AltModifier

_STATE: dict = {}


def _window():
    if "window" in _STATE:
        return _STATE["window"]
    app = create_app([sys.argv[0]])
    from quartz_studio.main_window import MainWindow
    from quartz_studio.modeling import install as mi

    mi.prepare()
    win = MainWindow()
    mi.install(win)
    win.resize(1500, 900)
    win.show()
    for _ in range(6):
        app.processEvents()
    _STATE["window"] = win
    _STATE["app"] = app
    return win


def _settle() -> None:
    app = _STATE["app"]
    for _ in range(4):
        app.processEvents()


def _close_popups() -> None:
    for _ in range(4):
        popup = QApplication.activePopupWidget()
        if popup is None:
            break
        popup.close()
        _settle()
    _settle()


def _setup(mode: str = "model"):
    win = _window()
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import get_scene

    _close_popups()
    scene = get_scene()
    ctl = mi.controller()
    ctl.activate(None)
    scene.set_tool("move")
    scene.set_mode("model")
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene._undo.clear()
    scene._redo.clear()
    canvas = win.viewport.canvas
    canvas.context_menu = None
    if mode != "model":
        scene.add_object("Object", Mesh.cube(200.0))
        scene.set_mode(mode)
    _settle()
    return win, scene, canvas, win.object_manager.tree


def _labels(menu) -> list[str]:
    out = []
    for act in menu.actions():
        out.append("---" if act.isSeparator() else (act.property("qs_label") or act.text()))
    return out


def _find(menu, label: str):
    for act in menu.actions():
        if not act.isSeparator() and (act.property("qs_label") or act.text()) == label:
            return act
    return None


def _enabled(menu, label: str) -> bool:
    act = _find(menu, label)
    assert act is not None, f"{label!r} missing from {_labels(menu)}"
    return act.isEnabled()


def _walk(menu, trail=()):
    for act in menu.actions():
        if act.isSeparator() or act.property("qs_kind") == "section":
            continue
        label = act.property("qs_label") or act.text()
        if act.menu() is not None:
            yield from _walk(act.menu(), trail + (label,))
        else:
            yield trail + (label,), act


def _leaf_names(menu) -> list[str]:
    return [path[-1] for path, _act in _walk(menu)]


def _move_to(obj, x: float) -> None:
    obj.position[0] = x


def _two_objects(scene, canvas):
    a = scene.add_parametric("cube")
    b = scene.add_parametric("cube")
    _move_to(a, -300.0)
    _move_to(b, 300.0)
    scene.changed.emit()
    canvas.frame_all()
    _settle()
    return a, b


def _screen(canvas, obj) -> QPoint:
    xy = canvas.project_world(np.asarray([obj.world_position()], float))[0]
    return QPoint(int(round(xy[0])), int(round(xy[1])))


def _empty_spot(canvas) -> QPoint:
    film = canvas.film_rect()
    return QPoint(int(film.left() + film.width() * 0.5), int(film.top() + film.height() * 0.93))


def _popup():
    popup = QApplication.activePopupWidget()
    return popup


def _right_click(canvas, pos: QPoint, mods=NO_MOD) -> None:
    QTest.mouseClick(canvas, RIGHT, mods, pos)
    _settle()


def _mouse(widget: QWidget, kind, pos, button=NO_BUTTON, buttons=NO_BUTTON, mods=NO_MOD) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    glob = QPointF(widget.mapToGlobal(local))
    QApplication.sendEvent(widget, QMouseEvent(kind, local, glob, button, buttons, mods))


def _right_drag(canvas, start, end, mods=NO_MOD, steps: int = 8) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    _mouse(canvas, QEvent.Type.MouseButtonPress, start, RIGHT, RIGHT, mods)
    for k in range(1, steps + 1):
        _mouse(canvas, QEvent.Type.MouseMove, start + (end - start) * k / steps, NO_BUTTON, RIGHT, mods)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, end, RIGHT, NO_BUTTON, mods)
    _settle()


def _context_event(widget: QWidget, pos: QPoint) -> None:
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, widget.mapToGlobal(pos))
    QApplication.sendEvent(widget, ev)
    _settle()


def _mesh_entries():
    from quartz_studio.widgets import menus_data

    for title, entries, _style in menus_data.MENU_BAR:
        if title == "Mesh":
            return entries
    return []


def _flat_mesh_order(entries) -> list[str]:
    out = []
    for entry in entries:
        if entry[0] == "submenu":
            out.extend(_flat_mesh_order(entry[2]))
        elif entry[0] == "item":
            out.append(entry[1])
    return out


def _mesh_tool_names(mode: str) -> set[str]:
    return {get_tool(i).name for i in tool_ids()
            if get_tool(i).menu == "Mesh" and get_tool(i).id != "delete" and mode in get_tool(i).modes}


def test_object_menu_content_parametric() -> None:
    win, scene, canvas, tree = _setup()
    obj = scene.add_parametric("cube")
    from quartz_studio.widgets import context_menu as cm

    menu = cm.build_object_menu(scene, obj, canvas, tree)
    assert _labels(menu) == ["Undo", "Redo", "---", "Frame Selected", "Frame All", "---",
                             "Make Editable", "Enabled", "Rename", "---", "Group Objects", "---",
                             "Delete"]
    assert _enabled(menu, "Undo") and not _enabled(menu, "Redo")
    assert _enabled(menu, "Make Editable")
    enabled = _find(menu, "Enabled")
    assert enabled.isCheckable() and enabled.isChecked()
    other = scene.add_parametric("cube")
    scene.set_enabled(other, False)
    off = cm.build_object_menu(scene, other, canvas, tree)
    assert not _find(off, "Enabled").isChecked()
    scene.undo()
    again = cm.build_object_menu(scene, scene.active, canvas, tree)
    assert _enabled(again, "Redo")


def test_object_menu_content_editable_null_and_hierarchy() -> None:
    win, scene, canvas, tree = _setup()
    from quartz_studio.widgets import context_menu as cm

    poly = scene.add_object("Poly", Mesh.cube(100.0))
    menu = cm.build_object_menu(scene, poly, canvas, tree)
    assert _find(menu, "Make Editable") is None
    assert _find(menu, "Unparent") is None and _find(menu, "Select Children") is None
    null = scene.add_parametric("null")
    nm = cm.build_object_menu(scene, null, canvas, tree)
    assert _find(nm, "Make Editable") is not None and not _enabled(nm, "Make Editable")
    child = scene.add_parametric("cube", parent=null)
    parent_menu = cm.build_object_menu(scene, null, canvas, tree)
    assert _find(parent_menu, "Select Children") is not None and _find(parent_menu, "Unparent") is None
    child_menu = cm.build_object_menu(scene, child, canvas, tree)
    assert _find(child_menu, "Unparent") is not None and _find(child_menu, "Select Children") is None
    assert _labels(child_menu).index("Group Objects") < _labels(child_menu).index("Unparent") \
        < _labels(child_menu).index("Delete")
    bare = cm.build_object_menu(scene, poly)
    assert _find(bare, "Frame Selected") is None and _find(bare, "Frame All") is None
    assert _find(bare, "Rename") is None


def test_empty_menu_and_create_submenu_content() -> None:
    win, scene, canvas, tree = _setup()
    from quartz_studio.widgets import context_menu as cm

    menu = cm.build_menu(scene, "model", None, canvas=canvas, tree=tree)
    assert _labels(menu) == ["Undo", "Redo", "---", "Frame All", "---", "Create"]
    create = _find(menu, "Create").menu()
    assert _labels(create) == ["Null", "Spline", "Mesh", "Generator"]
    for category, title in (("spline", "Spline"), ("mesh", "Mesh"), ("generator", "Generator")):
        sub = _find(create, title).menu()
        names = _leaf_names(sub)
        expected = [s.label for s in objects.by_category(category)]
        assert all(n in names for n in expected), (title, names)
        assert len(names) == len(expected) + (1 if category in ("spline", "mesh") else 0)
    assert "Line" in _leaf_names(_find(create, "Spline").menu())
    assert "Empty Polygon" in _leaf_names(_find(create, "Mesh").menu())
    plain = cm.build_menu(scene, "model", None)
    assert _labels(plain) == ["Undo", "Redo", "---", "Create"]
    assert _labels(cm.build_create_menu()) == ["Null", "Spline", "Mesh", "Generator"]


def test_context_menus_share_the_popup_preparation() -> None:
    win, scene, canvas, tree = _setup("polygons")
    from quartz_studio.widgets import context_menu as cm
    from quartz_studio.widgets.common import POPUP_PROPERTY

    menus = [cm.build_menu(scene, "polygons", None, canvas=canvas, tree=tree),
             cm.build_menu(scene, "polygons", scene.active, canvas=canvas, tree=tree),
             cm.build_create_menu()]
    scene.set_mode("model")
    menus.append(cm.build_menu(scene, "model", scene.active, canvas=canvas, tree=tree))
    menus.append(cm.build_menu(scene, "model", None, canvas=canvas, tree=tree))
    for menu in menus:
        assert menu is not None
        assert menu.objectName() == "qsContextMenu"
        assert menu.property(POPUP_PROPERTY) is True


def test_create_entries_use_the_palette_function() -> None:
    win, scene, canvas, tree = _setup()
    from quartz_studio.widgets import context_menu as cm

    menu = cm.build_create_menu()
    for title, label, kind in (("Spline", "Circle", "circle"), ("Mesh", "Cube", "cube"),
                               ("Generator", "Cloner", "cloner")):
        before = len(scene.objects)
        _find(_find(menu, title).menu(), label).trigger()
        assert len(scene.objects) == before + 1 and scene.active.kind == kind
    before = len(scene.objects)
    _find(menu, "Null").trigger()
    assert scene.active.kind == "null" and len(scene.objects) == before + 1
    _find(_find(menu, "Mesh").menu(), "Empty Polygon").trigger()
    assert scene.active.kind == "polygon"
    _find(_find(menu, "Spline").menu(), "Line").trigger()
    assert scene.active.name.startswith("Line") and scene.tool == "line_pen"


def test_component_menu_content_per_mode() -> None:
    from quartz_studio.widgets import context_menu as cm

    for mode in ("points", "edges", "polygons"):
        win, scene, canvas, tree = _setup(mode)
        scene.select_components([0] if mode != "edges" else [(0, 1)])
        menu = cm.build_menu(scene, mode, None, canvas=canvas, tree=tree)
        labels = _labels(menu)
        assert labels[:5] == ["Undo", "Redo", "---", "Frame Selected", "---"]
        assert labels[-1] == "Delete" and labels[-2] == "---" and labels[-3] == "Select"
        assert _enabled(menu, "Delete")
        fixed = ("Undo", "Redo", "Frame Selected", "Select", "Delete")
        tool_paths = [(path, act) for path, act in _walk(menu) if path[0] not in fixed]
        names = {path[-1] for path, _ in tool_paths}
        expected = _mesh_tool_names(mode) | {"Polygon Pen"}
        assert names == expected, (mode, names ^ expected)
        for other in tool_ids():
            spec = get_tool(other)
            if spec.menu == "Mesh" and mode not in spec.modes:
                assert spec.name not in names
        order = _flat_mesh_order(_mesh_entries())
        aliases = {"Convert Selection": "Convert Selection Mode..."}
        positions = [order.index(aliases.get(path[-1], path[-1])) for path, _ in tool_paths]
        assert positions == sorted(positions), (mode, positions)
        for path, act in tool_paths:
            if path[-1] == "Polygon Pen":
                assert act.property("qs_shortcut") == "M~E" and act.property("qs_icon") == "polygon_pen"
                continue
            spec = next(get_tool(i) for i in tool_ids()
                        if get_tool(i).menu == "Mesh" and get_tool(i).name == path[-1])
            assert (act.property("qs_shortcut") or None) == spec.shortcut, path
            assert act.text().replace("\t", " ").endswith(spec.shortcut or spec.name)
        shortcuts = [a.property("qs_shortcut") for _p, a in tool_paths if a.property("qs_shortcut")]
        assert shortcuts
        from quartz_studio import icons

        shown = [a for _p, a in tool_paths if a.property("qs_icon")]
        assert any(icons.has(a.property("qs_icon")) for a in shown)
        assert any(a.property("qs_icon") == icons.modeling_icon_name("bevel") for _p, a in tool_paths
                   if a.property("qs_label") == "Bevel") or not icons.has(icons.modeling_icon_name("bevel"))
        select = _leaf_names(_find(menu, "Select").menu())
        for name in ("Select All", "Deselect All", "Invert", "Select Connected", "Grow Selection",
                     "Shrink Selection", "Loop Selection", "Ring Selection", "Convert Selection"):
            assert name in select, (mode, name, select)
        assert ("Fill Selection" in select) == (mode == "edges")
        assert ("Outline Selection" in select) == (mode == "polygons")
        scene.clear_selection()
        empty = cm.build_menu(scene, mode, None, canvas=canvas, tree=tree)
        assert not _enabled(empty, "Delete")


def test_component_menu_requires_an_editable_object() -> None:
    win, scene, canvas, tree = _setup()
    from quartz_studio.widgets import context_menu as cm

    scene.add_parametric("cube")
    scene.set_mode("polygons")
    menu = cm.build_menu(scene, "polygons", None, canvas=canvas, tree=tree)
    assert _labels(menu)[-1] == "Create"
    scene.set_mode("model")


def _all_menus(scene, canvas, tree):
    from quartz_studio.widgets import context_menu as cm

    parent = scene.add_parametric("null")
    child = scene.add_parametric("cube", parent=parent)
    poly = scene.add_object("Poly", Mesh.cube(100.0))
    scene.set_active(poly)
    scene.set_mode("model")
    return {
        "object": lambda: cm.build_object_menu(scene, scene.objects[0], canvas, tree),
        "child": lambda: cm.build_object_menu(scene, scene.objects[1], canvas, tree),
        "poly": lambda: cm.build_object_menu(scene, scene.objects[2], canvas, tree),
        "empty": lambda: cm.build_menu(scene, "model", None, canvas=canvas, tree=tree),
        "create": lambda: cm.build_create_menu(),
    }, child


class _Capture(logging.Handler):

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record) -> None:
        self.lines.append(record.getMessage())


def _fresh_scene_for(kind: str):
    win, scene, canvas, tree = _setup("model" if kind in ("object", "child", "poly", "empty", "create")
                                      else kind)
    if kind in ("object", "child", "poly", "empty", "create"):
        builders, _child = _all_menus(scene, canvas, tree)
        return scene, canvas, tree, builders[kind]
    from quartz_studio.widgets import context_menu as cm

    scene.select_components([0] if kind != "edges" else [(0, 1)])
    return scene, canvas, tree, lambda: cm.build_menu(scene, kind, None, canvas=canvas, tree=tree)


def test_every_entry_triggers_without_error() -> None:
    from quartz_studio.modeling import install as mi

    caught: list = []
    messages: list[str] = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda *args: caught.append(args)
    handler = _Capture()
    logger = logging.getLogger("quartz_studio")
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    mi.controller().message.connect(messages.append)
    triggered = 0
    try:
        for kind in ("object", "child", "poly", "empty", "create", "points", "edges", "polygons"):
            scene, canvas, tree, build = _fresh_scene_for(kind)
            paths = [path for path, act in _walk(build()) if act.isEnabled()]
            assert paths, kind
            for path in paths:
                scene, canvas, tree, build = _fresh_scene_for(kind)
                menu = build()
                act = None
                for path_item, candidate in _walk(menu):
                    if path_item == path:
                        act = candidate
                assert act is not None, (kind, path)
                owner = act.parent()
                assert act in owner._handlers, (kind, path)
                act.trigger()
                _settle()
                _close_popups()
                triggered += 1
                assert not caught, (kind, path, caught)
                mi.controller().activate(None)
    finally:
        sys.excepthook = previous_hook
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        try:
            mi.controller().message.disconnect(messages.append)
        except (RuntimeError, TypeError):
            pass
    assert triggered > 60, triggered
    assert not [m for m in handler.lines if "not implemented" in m.lower()], handler.lines
    assert not [m for m in messages if "not implemented" in m.lower()], messages


def test_viewport_right_click_selects_the_object_under_the_cursor() -> None:
    win, scene, canvas, tree = _setup()
    a, b = _two_objects(scene, canvas)
    scene.set_active(a)
    spot = _screen(canvas, b)
    assert canvas.pick_object(spot) is b
    depth = len(scene._undo)
    _right_click(canvas, spot)
    assert scene.active is b and scene.object_selected
    menu = _popup()
    assert menu is not None and "Rename" in _labels(menu) and "Group Objects" in _labels(menu)
    assert canvas.context_menu is menu
    _close_popups()
    assert len(scene._undo) == depth
    scene.select_object(False)
    _right_click(canvas, _screen(canvas, a))
    assert scene.active is a and scene.object_selected
    assert _popup() is not None
    _close_popups()


def test_viewport_right_click_on_empty_space_opens_the_create_menu() -> None:
    win, scene, canvas, tree = _setup()
    a, b = _two_objects(scene, canvas)
    scene.set_active(b)
    spot = _empty_spot(canvas)
    assert canvas.pick_object(spot) is None
    _right_click(canvas, spot)
    menu = _popup()
    assert menu is not None
    assert _labels(menu) == ["Undo", "Redo", "---", "Frame All", "---", "Create"]
    assert scene.active is b
    _close_popups()


def test_viewport_right_click_in_component_mode_opens_the_mesh_menu() -> None:
    win, scene, canvas, tree = _setup("polygons")
    _right_click(canvas, _empty_spot(canvas))
    menu = _popup()
    assert menu is not None
    labels = _labels(menu)
    assert "Frame Selected" in labels and "Select" in labels and "Delete" in labels
    assert "Bevel" in _leaf_names(menu)
    _close_popups()


def test_viewport_right_click_lists_trunk_in_points_and_edges_modes_only() -> None:
    for mode, listed in (("points", True), ("edges", True), ("polygons", False)):
        win, scene, canvas, tree = _setup(mode)
        _right_click(canvas, _empty_spot(canvas))
        menu = _popup()
        assert menu is not None, mode
        assert ("Trunk" in _leaf_names(menu)) == listed, (mode, _leaf_names(menu))
        _close_popups()


def test_alt_right_drag_zooms_and_opens_no_menu() -> None:
    win, scene, canvas, tree = _setup()
    _two_objects(scene, canvas)
    before = canvas.camera.distance
    start = _empty_spot(canvas)
    _right_drag(canvas, (start.x(), start.y()), (start.x() + 80, start.y() - 80), mods=ALT)
    assert abs(canvas.camera.distance - before) > 1e-6
    assert _popup() is None and canvas.context_menu is None
    _right_drag(canvas, (start.x(), start.y()), (start.x(), start.y()), mods=ALT, steps=1)
    assert _popup() is None


def test_right_drag_over_the_threshold_opens_no_menu() -> None:
    win, scene, canvas, tree = _setup()
    _two_objects(scene, canvas)
    start = _empty_spot(canvas)
    _right_drag(canvas, (start.x(), start.y()), (start.x() + 12, start.y()))
    assert _popup() is None and canvas.context_menu is None
    _right_drag(canvas, (start.x(), start.y()), (start.x() + 2, start.y() + 1), steps=2)
    assert _popup() is not None
    _close_popups()


def test_right_click_cancels_a_gizmo_drag_without_a_menu() -> None:
    win, scene, canvas, tree = _setup()
    obj = scene.add_object("Object", Mesh.cube(200.0))
    scene.set_tool("move")
    scene._undo.clear()
    (sx, sy), (ex, ey) = canvas.gizmo_handles()["x"]
    start = np.array([sx, sy]) + (np.array([ex, ey]) - np.array([sx, sy])) * 0.6
    p0 = QPoint(int(round(start[0])), int(round(start[1])))
    QTest.mousePress(canvas, LEFT, NO_MOD, p0)
    for k in range(1, 8):
        QTest.mouseMove(canvas, QPoint(p0.x() + 6 * k, p0.y()))
    assert canvas._drag is not None and abs(obj.position[0]) > 1.0
    end = QPoint(p0.x() + 42, p0.y())
    QTest.mousePress(canvas, RIGHT, NO_MOD, end)
    QTest.mouseRelease(canvas, RIGHT, NO_MOD, end)
    _settle()
    assert canvas._drag is None
    assert np.allclose(obj.position, 0.0)
    assert _popup() is None and canvas.context_menu is None
    QTest.mouseRelease(canvas, LEFT, NO_MOD, end)
    _settle()
    assert _popup() is None and np.allclose(obj.position, 0.0)


def test_right_click_cancels_a_tool_drag_without_a_menu() -> None:
    win, scene, canvas, tree = _setup("polygons")
    from quartz_studio.modeling import install as mi

    obj = scene.active
    scene.select_components([0])
    mi.activate_tool("extrude")
    _settle()
    points_before = len(obj.mesh.points)
    xy = canvas.project_world(obj.world_points()[list(obj.mesh.polygons[0])])
    centre = xy.mean(axis=0)
    p0 = QPoint(int(round(centre[0])), int(round(centre[1])))
    QTest.mousePress(canvas, LEFT, NO_MOD, p0)
    for k in range(1, 8):
        QTest.mouseMove(canvas, QPoint(p0.x() + 8 * k, p0.y()))
    _settle()
    end = QPoint(p0.x() + 56, p0.y())
    QTest.mousePress(canvas, RIGHT, NO_MOD, end)
    QTest.mouseRelease(canvas, RIGHT, NO_MOD, end)
    _settle()
    assert _popup() is None and canvas.context_menu is None
    assert win.modeling_filter._press is None
    QTest.mouseRelease(canvas, LEFT, NO_MOD, end)
    _settle()
    assert _popup() is None
    assert len(obj.mesh.points) == points_before
    mi.controller().activate(None)


def test_pens_keep_their_right_click_and_open_no_menu() -> None:
    win, scene, canvas, tree = _setup("points")
    scene.set_tool("pen")
    film = canvas.film_rect()
    first = QPoint(int(film.left() + film.width() * 0.3), int(film.top() + film.height() * 0.4))
    second = QPoint(first.x() + 90, first.y())
    QTest.mouseClick(canvas, LEFT, NO_MOD, first)
    QTest.mouseClick(canvas, LEFT, NO_MOD, second)
    _settle()
    assert scene.pen_active()
    QTest.mouseClick(canvas, RIGHT, NO_MOD, QPoint(second.x(), second.y() + 60))
    _settle()
    assert not scene.pen_active()
    assert _popup() is None and canvas.context_menu is None
    QTest.mouseClick(canvas, RIGHT, NO_MOD, QPoint(second.x(), second.y() + 60))
    _settle()
    assert _popup() is None
    scene.set_tool("line_pen")
    QTest.mouseClick(canvas, LEFT, NO_MOD, first)
    _settle()
    assert scene.pen_active()
    QTest.mouseClick(canvas, RIGHT, NO_MOD, second)
    _settle()
    assert not scene.pen_active() and _popup() is None
    scene.set_tool("move")


def test_object_manager_right_click_on_a_row_selects_it() -> None:
    win, scene, canvas, tree = _setup()
    a, b = _two_objects(scene, canvas)
    scene.set_active(a)
    item = tree.item_of(b)
    pos = tree.visualItemRect(item).center()
    depth = len(scene._undo)
    _context_event(tree.viewport(), pos)
    assert scene.active is b and scene.object_selected
    menu = _popup()
    assert menu is not None and tree.context_menu is menu
    assert "Rename" in _labels(menu) and "Frame Selected" in _labels(menu)
    _close_popups()
    _context_event(tree.viewport(), pos)
    assert scene.selected_objects() == [b] and scene.active is b
    _close_popups()
    assert len(scene._undo) == depth


def test_object_manager_right_click_on_empty_area_shows_create() -> None:
    win, scene, canvas, tree = _setup()
    _two_objects(scene, canvas)
    active = scene.active
    pos = QPoint(tree.viewport().width() // 2, tree.viewport().height() - 4)
    assert tree.itemAt(pos) is None
    _context_event(tree.viewport(), pos)
    menu = _popup()
    assert menu is not None
    assert _labels(menu) == ["Null", "Spline", "Mesh", "Generator"]
    assert scene.active is active
    _close_popups()


def test_object_menu_actions_work() -> None:
    from quartz_studio.widgets import context_menu as cm

    win, scene, canvas, tree = _setup()
    a, b = _two_objects(scene, canvas)
    menu = cm.build_object_menu(scene, b, canvas, tree)
    _find(menu, "Enabled").trigger()
    assert not b.enabled
    _find(cm.build_object_menu(scene, b, canvas, tree), "Enabled").trigger()
    assert b.enabled
    _find(cm.build_object_menu(scene, b, canvas, tree), "Make Editable").trigger()
    new_b = scene.active
    assert scene.is_editable(new_b) and new_b.name == b.name
    assert _find(cm.build_object_menu(scene, new_b, canvas, tree), "Make Editable") is None
    _find(cm.build_object_menu(scene, new_b, canvas, tree), "Rename").trigger()
    _settle()
    assert tree.state() == tree.State.EditingState
    tree.closePersistentEditor(tree.item_of(new_b), 0)
    tree.setState(tree.State.NoState)
    count = len(scene.objects)
    _find(cm.build_object_menu(scene, new_b, canvas, tree), "Delete").trigger()
    assert len(scene.objects) == count - 1 and new_b not in scene.objects
    assert scene.undo() and new_b.name in [o.name for o in scene.objects]


def _named(scene, name: str):
    return next(o for o in scene.objects if o.name == name)


def test_group_unparent_and_select_children_are_single_undo_steps() -> None:
    from quartz_studio.widgets import context_menu as cm

    win, scene, canvas, tree = _setup()
    a, b = _two_objects(scene, canvas)
    name_a, name_b = a.name, b.name
    scene.set_active(b)
    world_b = b.world_position().copy()
    scene._undo.clear()
    _find(cm.build_object_menu(scene, b, canvas, tree), "Group Objects").trigger()
    group = scene.active
    assert group.kind == "null" and b.parent is group and a.parent is None
    assert np.allclose(b.world_position(), world_b)
    assert len(scene._undo) == 1
    assert scene.undo()
    assert _named(scene, name_b).parent is None and all(o.kind != "null" for o in scene.objects)
    assert not scene.can_undo()
    assert scene.redo()
    b = _named(scene, name_b)
    group = b.parent
    assert group is not None and group.kind == "null"
    scene._undo.clear()
    scene.set_active(group)
    select = _find(cm.build_object_menu(scene, group, canvas, tree), "Select Children")
    assert select is not None
    select.trigger()
    assert scene.active is b and scene.object_selected
    scene._undo.clear()
    _find(cm.build_object_menu(scene, b, canvas, tree), "Unparent").trigger()
    assert b.parent is None and np.allclose(b.world_position(), world_b)
    assert len(scene._undo) == 1
    assert scene.undo()
    assert _named(scene, name_b).parent is not None and not scene.can_undo()
    scene._undo.clear()
    a, b = _named(scene, name_a), _named(scene, name_b)
    scene.set_active(a)
    both = scene.group_objects([a, b])
    assert both is not None and a.parent is both and b.parent is both
    assert len(scene._undo) == 1
    assert scene.undo() and _named(scene, name_a).parent is None


def test_attribute_manager_reset_to_default() -> None:
    from quartz_studio.widgets import context_menu as cm

    win, scene, canvas, tree = _setup()
    obj = scene.add_parametric("cube")
    scene.set_active(obj)
    _settle()
    manager = win.attribute_manager
    _settle()
    row = manager.object_rows["size_x"]
    editor = manager.object_editors["size_x"]
    default = 200.0
    scene.set_param(obj, "size_x", 350.0)
    _settle()
    scene._undo.clear()
    spin = editor.widgets[0]
    assert isinstance(spin, QDoubleSpinBox)
    assert abs(spin.value() - 350.0) < 1e-6
    _context_event(spin.lineEdit(), QPoint(3, 3))
    menu = _popup()
    assert menu is not None and manager.context_menu is menu
    assert _labels(menu) == ["Reset to Default"] and _enabled(menu, "Reset to Default")
    _find(menu, "Reset to Default").trigger()
    _settle()
    _close_popups()
    assert obj.params["size_x"] == default
    assert len(scene._undo) == 1
    assert abs(spin.value() - default) < 1e-6
    _context_event(row.label, QPoint(3, 3))
    menu = _popup()
    assert menu is not None and not _enabled(menu, "Reset to Default")
    _close_popups()
    assert scene.undo()
    assert _named(scene, obj.name).params["size_x"] == 350.0
    obj = _named(scene, obj.name)
    assert _enabled(cm.build_param_menu(scene, obj, "size_x"), "Reset to Default")
    assert _labels(cm.build_param_menu(scene, obj, "missing")) == []
    scene.set_param(obj, "size_x", default)
    assert not _enabled(cm.build_param_menu(scene, obj, "size_x"), "Reset to Default")
    scene.set_param(obj, "fillet", True)
    scene._undo.clear()
    reset = _find(cm.build_param_menu(scene, obj, "fillet"), "Reset to Default")
    assert reset.isEnabled()
    reset.trigger()
    assert obj.params["fillet"] is False and len(scene._undo) == 1


def _run_as_script() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    tests.sort(key=lambda item: item[1].__code__.co_firstlineno)
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failures += 1
            line = traceback.extract_tb(exc.__traceback__)[-1].lineno
            print(f"FAIL {name} (line {line}): {type(exc).__name__}: {exc}".encode("ascii", "replace").decode())
        else:
            print(f"ok   {name}")
        finally:
            _close_popups() if "app" in _STATE else None
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
