from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TMP = tempfile.mkdtemp(prefix="quartz-multi-selection-")
os.environ["QUARTZ_PREFS_DIR"] = _TMP

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio.app import create_app

LEFT = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier

_STATE: dict = {}


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(passes: int = 4) -> None:
    app = QApplication.instance()
    for _ in range(passes):
        app.processEvents()


def _controls():
    from quartz_studio import controls

    return controls


def _fresh() -> None:
    controls = _controls()
    controls.STORE_PATH = os.path.join(_TMP, "controls.json")
    controls.reset()


def _close_popups() -> None:
    for _ in range(4):
        popup = QApplication.activePopupWidget()
        if popup is None:
            break
        popup.close()
        _settle()


def _window():
    if "window" in _STATE:
        return _STATE["window"]
    app = _app()
    _fresh()
    from quartz_studio.main_window import MainWindow
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import reset_scene

    reset_scene()
    mi.prepare()
    win = MainWindow()
    if getattr(win, "controls_filter", None) is None:
        for sc in win.findChildren(QShortcut):
            sc.setEnabled(False)
            sc.deleteLater()
        _controls().install(win)
    mi.install(win)
    win.resize(1500, 900)
    win.show()
    for _ in range(6):
        app.processEvents()
    _STATE["window"] = win
    return win


def _setup(tool: str = "move"):
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import Mesh, get_scene

    win = _window()
    _close_popups()
    _controls().select("classic")
    scene = get_scene()
    mi.controller().activate(None)
    scene.set_tool("move")
    scene.set_mode("model")
    for obj in list(scene.objects):
        scene.remove_object(obj)
    objs = []
    for name, x in zip("ABC", (-400.0, 0.0, 400.0)):
        obj = scene.add_object(name, Mesh.cube(150.0))
        obj.position = np.array([x, 0.0, 0.0])
        objs.append(obj)
    scene.changed.emit()
    scene.set_active(objs[0])
    canvas = win.viewport.canvas
    canvas.reset_camera()
    canvas.frame_all()
    scene.set_tool(tool)
    scene._undo.clear()
    scene._redo.clear()
    canvas.setFocus()
    _settle()
    return win, scene, canvas, objs


def _mouse(widget: QWidget, kind, pos, button=NO_BUTTON, buttons=NO_BUTTON, mods=NO_MOD) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    glob = QPointF(widget.mapToGlobal(local))
    QApplication.sendEvent(widget, QMouseEvent(kind, local, glob, button, buttons, mods))


def _drag(widget, start, end, mods=NO_MOD, steps: int = 10) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    _mouse(widget, QEvent.Type.MouseButtonPress, start, LEFT, LEFT, mods)
    for k in range(1, steps + 1):
        _mouse(widget, QEvent.Type.MouseMove, start + (end - start) * k / steps, NO_BUTTON, LEFT, mods)
    _mouse(widget, QEvent.Type.MouseButtonRelease, end, LEFT, NO_BUTTON, mods)
    _settle(2)


def _empty(canvas) -> np.ndarray:
    film = canvas.film_rect()
    spot = np.array([film.left() + film.width() * 0.5, film.top() + film.height() * 0.9])
    assert canvas.pick_object(spot) is None
    return spot


def _names(scene) -> list[str]:
    return sorted(o.name for o in scene.selected_objects())


def _by(scene, name: str):
    return next(o for o in scene.objects if o.name == name)


def _menu_action(menu, label: str):
    for act in menu.actions():
        if not act.isSeparator() and (act.property("qs_label") or act.text()) == label:
            return act
    return None


def test_scene_selection_operations_keep_the_active_object() -> None:
    win, scene, canvas, (a, b, c) = _setup()
    assert scene.selected_objects() == [a] and scene.active is a
    assert scene.select_objects([b], "add")
    assert _names(scene) == ["A", "B"] and scene.active is a
    assert scene.select_objects([c], "add", active=c)
    assert _names(scene) == ["A", "B", "C"] and scene.active is c
    assert scene.select_objects([c], "toggle")
    assert _names(scene) == ["A", "B"] and scene.active in (a, b) and scene.is_object_selected(scene.active)
    assert scene.select_objects([a], "remove")
    assert scene.selected_objects() == [b] and scene.active is b and scene.object_selected
    assert scene.select_objects([a, c], "replace", active=c)
    assert _names(scene) == ["A", "C"] and scene.active is c
    assert not scene.select_objects([a, c], "replace", active=c)
    scene.set_active(b)
    assert scene.selected_objects() == [b] and scene.extra_selected == []
    scene.select_objects([a, c], "add")
    scene.select_object(False)
    assert scene.selected_objects() == [] and scene.active is b and scene.extra_selected == []
    scene.select_objects([a, b, c], "replace", active=b)
    assert [o.name for o in scene.selected_objects()] == ["A", "B", "C"]
    assert scene.active is b and scene.object_selected
    from quartz_studio.widgets import status_bar

    assert status_bar.selection_text(scene).startswith("3 objects")
    try:
        scene.select_objects([a], "bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown operation must raise")


def test_undo_and_removal_keep_the_selection_consistent() -> None:
    win, scene, canvas, (a, b, c) = _setup()
    scene.select_objects([a, b, c], "replace", active=b)
    scene.set_transforms([(a, (10.0, 0.0, 0.0), None, None)])
    scene.select_objects([c], "replace")
    assert _names(scene) == ["C"]
    scene.undo()
    assert _names(scene) == ["A", "B", "C"] and scene.active.name == "B", _names(scene)
    scene.redo()
    assert _names(scene) == ["C"]
    scene.undo()
    a, b, c = (_by(scene, n) for n in "ABC")
    scene.remove_object(a)
    assert _names(scene) == ["B", "C"] and scene.active is b
    scene.remove_object(b)
    assert all(o in scene.objects for o in scene.selected_objects())
    assert scene.extra_selected == [] or all(o in scene.objects for o in scene.extra_selected)
    scene.undo()
    scene.undo()
    assert _names(scene) == ["A", "B", "C"], _names(scene)


def test_move_gizmo_moves_every_selected_object_in_one_step() -> None:
    win, scene, canvas, (a, b, c) = _setup()
    scene.select_objects([a, b], "replace", active=b)
    canvas.update()
    _settle()
    (sx, sy), (ex, ey) = canvas.gizmo_handles()["x"]
    grip = np.array([sx + (ex - sx) * 0.8, sy + (ey - sy) * 0.8])
    assert canvas.gizmo_pick(grip) == "x"
    _drag(canvas, grip, grip + ((ex - sx) * 0.5, (ey - sy) * 0.5))
    da, db = a.position - (-400.0, 0.0, 0.0), b.position - (0.0, 0.0, 0.0)
    assert da[0] > 1.0 and np.allclose(da, db) and np.allclose(da[1:], 0.0), (da, db)
    assert np.allclose(c.position, (400.0, 0.0, 0.0))
    assert len(scene._undo) == 1 and _names(scene) == ["A", "B"]
    scene.undo()
    assert np.allclose(_by(scene, "A").position, (-400.0, 0.0, 0.0))
    assert np.allclose(_by(scene, "B").position, 0.0)


def test_rotate_and_scale_act_on_every_selected_object() -> None:
    for tool in ("scale", "rotate"):
        win, scene, canvas, (a, b, c) = _setup(tool)
        scene.select_objects([a, b], "replace", active=b)
        start = _empty(canvas)
        _drag(canvas, start, start + (40.0, 0.0))
        if tool == "scale":
            assert a.scale[0] > 1.0 and np.allclose(a.scale, b.scale) and np.allclose(a.scale, a.scale[0])
            assert np.allclose(c.scale, 1.0)
        else:
            assert not np.allclose(a.rotation, 0.0) and np.allclose(a.rotation, b.rotation)
            assert np.allclose(c.rotation, 0.0)
        assert np.allclose(b.position, 0.0), (tool, b.position)
        reach = float(np.linalg.norm(a.position - b.position))
        if tool == "scale":
            assert abs(reach - 400.0 * a.scale[0]) < 1e-6, (reach, a.scale)
        else:
            assert abs(reach - 400.0) < 1e-6, reach
        assert not np.allclose(a.position, (-400.0, 0.0, 0.0)), tool
        assert len(scene._undo) == 1, tool


def test_hierarchy_children_move_once_with_their_parent() -> None:
    win, scene, canvas, (a, b, c) = _setup()
    scene.set_parent(b, a)
    scene.select_objects([a, b], "replace", active=a)
    wb = b.world_position().copy()
    scene.move_selection(np.array([0.0, 50.0, 0.0]))
    assert np.allclose(b.world_position() - wb, (0.0, 50.0, 0.0)), b.world_position() - wb
    assert scene.transform_roots() == [a]


def test_context_menu_commands_act_on_the_selection() -> None:
    from quartz_studio.widgets import context_menu

    win, scene, canvas, (a, b, c) = _setup()
    scene.select_objects([a, b], "replace", active=b)
    menu = context_menu.build_object_menu(scene, b)
    _menu_action(menu, "Enabled").trigger()
    assert not a.enabled and not b.enabled and c.enabled
    assert len(scene._undo) == 1
    scene.undo()
    a, b, c = (_by(scene, n) for n in "ABC")
    assert a.enabled and b.enabled
    assert _names(scene) == ["A", "B"]
    menu = context_menu.build_object_menu(scene, b)
    _menu_action(menu, "Group Objects").trigger()
    null = a.parent
    assert null is not None and b.parent is null and c.parent is None
    scene.select_objects([a, b], "replace", active=a)
    menu = context_menu.build_object_menu(scene, a)
    _menu_action(menu, "Unparent").trigger()
    assert a.parent is None and b.parent is None
    scene.set_parent(a, null)
    scene.set_parent(b, null)
    scene.set_parent(c, b)
    scene.select_objects([null], "replace")
    menu = context_menu.build_object_menu(scene, null)
    _menu_action(menu, "Select Children").trigger()
    assert _names(scene) == ["A", "B"], _names(scene)
    scene.select_objects([a, c], "replace", active=c)
    menu = context_menu.build_object_menu(scene, c)
    depth = len(scene._undo)
    _menu_action(menu, "Delete").trigger()
    assert a not in scene.objects and c not in scene.objects and b in scene.objects
    assert len(scene._undo) == depth + 1
    scene.undo()
    assert {o.name for o in scene.objects} >= {"A", "B", "C"}
    win, scene, canvas, (a, b, c) = _setup()
    scene.select_objects([a, c], "replace", active=a)
    menu = context_menu.build_object_menu(scene, b)
    _menu_action(menu, "Delete").trigger()
    assert b not in scene.objects and a in scene.objects and c in scene.objects


def test_delete_key_removes_every_selected_object() -> None:
    win, scene, canvas, (a, b, c) = _setup()
    scene.select_objects([a, c], "replace", active=c)
    assert _controls().run("edit.delete") or _controls().run("object.delete")
    _settle()
    assert [o.name for o in scene.objects] == ["B"], [o.name for o in scene.objects]
    scene.undo()
    assert [o.name for o in scene.objects] == ["A", "B", "C"]


def test_hierarchy_panel_supports_the_multi_selection() -> None:
    win, scene, canvas, (a, b, c) = _setup()
    tree = win.object_manager.tree
    assert tree.headerItem().text(0) == "Hierarchy"
    _settle()

    def click(obj, mods=NO_MOD) -> None:
        r = tree.visualItemRect(tree.item_of(obj))
        QTest.mouseClick(tree.viewport(), LEFT, mods, QPoint(60, r.center().y()))
        _settle(2)

    click(b)
    assert _names(scene) == ["B"] and scene.active is b
    click(c, SHIFT)
    assert _names(scene) == ["B", "C"] and scene.active is c
    assert tree.highlighted_names() == ["B", "C"]
    assert tree.is_highlighted(b) and tree.is_highlighted(c) and not tree.is_highlighted(a)
    assert tree.is_active_row(c) and not tree.is_active_row(b)
    click(a, CTRL)
    assert _names(scene) == ["A", "B", "C"] and scene.active is a
    click(b, CTRL)
    assert _names(scene) == ["A", "C"]
    click(b)
    assert _names(scene) == ["B"]
    scene.select_objects([a, c], "replace", active=a)
    assert tree.delete_active()
    assert [o.name for o in scene.objects] == ["B"]
    tree.window().grab()


def test_save_and_open_keep_the_selection() -> None:
    from quartz_studio.fileio import open_scene, save_scene
    from quartz_studio.scene import Scene

    win, scene, canvas, (a, b, c) = _setup()
    scene.select_objects([a, c], "replace", active=c)
    path = os.path.join(_TMP, "multi.quartz")
    save_scene(scene, path)
    other = Scene()
    open_scene(other, path)
    assert _names(other) == ["A", "C"] and other.active.name == "C", _names(other)
    scene.select_objects([b], "replace")
    save_scene(scene, path)
    other = Scene()
    open_scene(other, path)
    assert _names(other) == ["B"] and other.active.name == "B"
    scene.select_objects([a, b], "replace", active=a)
    scene.select_object(False)
    save_scene(scene, path)
    other = Scene()
    open_scene(other, path)
    assert other.selected_objects() == [] and other.active.name == "A"


def test_cards_keep_showing_the_active_object() -> None:
    win, scene, canvas, (a, b, c) = _setup()
    a.position = np.array([-400.0, 12.0, 0.0])
    scene.select_objects([a, b, c], "replace", active=a)
    scene.select_objects([b], "add", active=b)
    _settle()
    coords = win.coordinates
    coords.refresh()
    assert scene.active is b and len(scene.selected_objects()) == 3
    assert coords.field(0, 0).value() == 0.0 and coords.field(0, 1).value() == 0.0
    scene.select_objects([a], "add", active=a)
    coords.refresh()
    assert coords.field(0, 0).value() == -400.0 and coords.field(0, 1).value() == 12.0
    scene.set_object_position(0, 25.0)
    assert np.allclose(a.position, (25.0, 12.0, 0.0)) and np.allclose(b.position, 0.0)
    assert np.allclose(c.position, (400.0, 0.0, 0.0))


def _cleanup() -> None:
    _close_popups()
    win = _STATE.pop("window", None)
    if win is not None:
        win.close()
        win.deleteLater()
    _fresh()
    _controls().STORE_PATH = None


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
            print(f"FAIL {name}: {type(exc).__name__}: {exc}".encode("ascii", "replace").decode())
        else:
            print(f"ok   {name}")
    _cleanup()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
