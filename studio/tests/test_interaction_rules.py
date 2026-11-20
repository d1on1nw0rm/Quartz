from __future__ import annotations

import importlib.util
import math
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TMP = tempfile.mkdtemp(prefix="quartz-interaction-rules-")
os.environ["QUARTZ_PREFS_DIR"] = _TMP

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from quartz_studio.app import create_app

LEFT = Qt.MouseButton.LeftButton
MIDDLE = Qt.MouseButton.MiddleButton
RIGHT = Qt.MouseButton.RightButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
PROFILES = ("classic", "standard")
TRANSFORMS = ("move", "rotate", "scale")

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


def _setup(profile: str, mode: str = "model", tool: str = "move", count: int = 1):
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import Mesh, get_scene

    win = _window()
    _close_popups()
    _controls().select(profile)
    scene = get_scene()
    mi.controller().activate(None)
    scene.set_tool("move")
    scene.set_mode("model")
    for obj in list(scene.objects):
        scene.remove_object(obj)
    canvas = win.viewport.canvas
    if count == 1:
        objs = [scene.add_object("Cube", Mesh.cube(200.0))]
    else:
        objs = []
        for name, x in zip("ABC", (-400.0, 0.0, 400.0)):
            obj = scene.add_object(name, Mesh.cube(150.0))
            obj.position = np.array([x, 0.0, 0.0])
            objs.append(obj)
        scene.changed.emit()
    scene.set_active(objs[0])
    canvas.reset_camera()
    if count > 1:
        canvas.frame_all()
    if mode != "model":
        scene.set_mode(mode)
    if tool in ("move", "rotate", "scale", "select", "pen"):
        scene.set_tool(tool)
    else:
        mi.activate_tool(tool)
    scene._undo.clear()
    scene._redo.clear()
    canvas.context_menu = None
    canvas.setFocus()
    _settle()
    return win, scene, canvas, objs


def _mouse(widget: QWidget, kind, pos, button=NO_BUTTON, buttons=NO_BUTTON, mods=NO_MOD) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    glob = QPointF(widget.mapToGlobal(local))
    QApplication.sendEvent(widget, QMouseEvent(kind, local, glob, button, buttons, mods))


def _press(widget, pos, button=LEFT, mods=NO_MOD) -> None:
    _mouse(widget, QEvent.Type.MouseButtonPress, pos, button, button, mods)


def _move(widget, pos, button=LEFT, mods=NO_MOD) -> None:
    _mouse(widget, QEvent.Type.MouseMove, pos, NO_BUTTON, button, mods)


def _release(widget, pos, button=LEFT, mods=NO_MOD) -> None:
    _mouse(widget, QEvent.Type.MouseButtonRelease, pos, button, NO_BUTTON, mods)
    _settle(2)


def _click(widget, pos, mods=NO_MOD, button=LEFT) -> None:
    _press(widget, pos, button, mods)
    _release(widget, pos, button, mods)


def _drag(widget, start, end, mods=NO_MOD, button=LEFT, steps: int = 10, release: bool = True) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    _press(widget, start, button, mods)
    for k in range(1, steps + 1):
        _move(widget, start + (end - start) * k / steps, button, mods)
    if release:
        _release(widget, end, button, mods)


def _key(widget, key, mods=NO_MOD, text: str = "") -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, Qt.Key(key), mods, text))
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyRelease, Qt.Key(key), mods, text))
    _settle(2)


def _px(canvas, world) -> np.ndarray:
    return canvas.project_world(np.asarray([world], float))[0]


def _obj_px(canvas, obj) -> np.ndarray:
    return _px(canvas, obj.world_position())


def _empty(canvas) -> np.ndarray:
    film = canvas.film_rect()
    spot = np.array([film.left() + film.width() * 0.5, film.top() + film.height() * 0.9])
    assert canvas.pick_object(spot) is None
    return spot


def _names(scene) -> list[str]:
    return sorted(o.name for o in scene.selected_objects())


def _transforms(objs) -> list:
    return [(o.position.copy(), o.rotation.copy(), o.scale.copy()) for o in objs]


def _same(a, b) -> bool:
    return all(np.allclose(x, y) for ta, tb in zip(a, b) for x, y in zip(ta, tb))


def _visible(canvas, scene, kind: str) -> list[tuple[int, np.ndarray]]:
    obj = scene.active
    out = []
    if kind == "point":
        for i, p in enumerate(canvas.project_world(obj.world_points())):
            if canvas.pick(p) == ("point", i):
                out.append((i, p))
        return out
    pts = obj.world_points()
    for k, poly in enumerate(obj.mesh.polygons):
        p = _px(canvas, pts[list(poly)].mean(axis=0))
        if canvas.pick(p) == ("polygon", k):
            out.append((k, p))
    return out


def _depth(scene) -> int:
    return len(scene._undo)


def test_profiles_list_the_new_gestures_and_keep_classic() -> None:
    _app()
    _fresh()
    controls = _controls()
    from quartz_studio.controls import profiles

    for pid in PROFILES:
        res = controls.resolved(pid)
        rows = {(g["button"], tuple(g["mods"]), g.get("op")) for g in res.mouse if not g["double"]}
        for row in (("left", (), "select"), ("left", ("shift",), "add"), ("left", ("ctrl",), "remove"),
                    ("right", (), "context"), ("right", ("shift",), "add"), ("right", ("ctrl",), "remove"),
                    ("right", ("alt",), "dolly")):
            assert row in rows, (pid, row)
        keys = [b for b, _scope in res.keys.get("tool.select_all", ())]
        assert "Ctrl+A" in keys, (pid, keys)
        assert profiles.is_paint_gesture(res, {"button": "right", "op": "add"})
        assert not profiles.is_paint_gesture(res, {"button": "left", "op": "add"})
        assert controls.conflicts(pid) == [], (pid, controls.conflicts(pid))
    path = os.path.join(STUDIO_ROOT, "build", "backup-pre-interaction-20261120", "quartz_studio", "controls",
                        "profiles.py")
    spec = importlib.util.spec_from_file_location("_backup_profiles", path)
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    try:
        spec.loader.exec_module(old)
    finally:
        sys.modules.pop(spec.name, None)
    new = profiles.CLASSIC
    for key, value in old.CLASSIC["keys"].items():
        if key == "tool.grow_selection":
            continue
        assert new["keys"].get(key) == value, (key, value, new["keys"].get(key))
    added = set(new["keys"]) - set(old.CLASSIC["keys"])
    assert added <= {"tool.select_all", "tool.grow_selection", "tool.shrink_selection"}, added
    assert [g for g in new["mouse"] if g in old.CLASSIC["mouse"]] == old.CLASSIC["mouse"]
    extra = [g for g in new["mouse"] if g not in old.CLASSIC["mouse"]]
    assert extra == [{"button": "right", "mods": ["ctrl"], "op": "remove"},
                     {"button": "right", "mods": ["shift"], "op": "add"}], extra
    for section in ("cursor", "modifiers", "modal"):
        assert new.get(section) == old.CLASSIC.get(section), section


def test_ctrl_a_selects_every_object_and_every_component() -> None:
    for pid in PROFILES:
        win, scene, canvas, objs = _setup(pid, count=3)
        assert _names(scene) == ["A"]
        _key(canvas, Qt.Key.Key_A, CTRL, "a")
        assert _names(scene) == ["A", "B", "C"], (pid, _names(scene))
        assert scene.active is objs[0]
        assert _depth(scene) == 1
        scene.undo()
        assert _names(scene) == ["A"], pid
        objs = list(scene.objects)
        scene.set_mode("polygons")
        _key(canvas, Qt.Key.Key_A, CTRL, "a")
        assert scene.selected_polygons == set(range(6)), (pid, scene.selected_polygons)
        scene.set_mode("points")
        scene.clear_selection()
        _key(canvas, Qt.Key.Key_A, CTRL, "a")
        assert scene.selected_points == set(range(8)), (pid, scene.selected_points)
        assert scene.active is objs[0]


def test_ctrl_a_does_not_fire_in_a_text_field() -> None:
    for pid in PROFILES:
        win, scene, canvas, objs = _setup(pid, count=3)
        field = QLineEdit(win)
        field.setText("abc")
        field.show()
        field.setFocus()
        _settle()
        try:
            QTest.keyClick(field, Qt.Key.Key_A, CTRL)
            _settle()
            assert _names(scene) == ["A"], (pid, _names(scene))
            assert field.selectedText() == "abc", pid
        finally:
            field.deleteLater()
            canvas.setFocus()
            _settle()


def test_left_click_replaces_shift_adds_ctrl_toggles_objects() -> None:
    for pid in PROFILES:
        for tool in TRANSFORMS:
            win, scene, canvas, (a, b, c) = _setup(pid, tool=tool, count=3)
            _click(canvas, _obj_px(canvas, b) + (0.0, 24.0))
            assert _names(scene) == ["B"] and scene.active is b, (pid, tool, _names(scene))
            _click(canvas, _obj_px(canvas, c) + (0.0, 24.0), SHIFT)
            assert _names(scene) == ["B", "C"] and scene.active is c, (pid, tool, _names(scene))
            _click(canvas, _obj_px(canvas, b) + (0.0, 24.0), CTRL)
            assert _names(scene) == ["C"], (pid, tool, _names(scene))
            _click(canvas, _obj_px(canvas, a) + (0.0, 24.0), CTRL)
            assert _names(scene) == ["A", "C"], (pid, tool, _names(scene))
            _click(canvas, _obj_px(canvas, b) + (0.0, 24.0))
            assert _names(scene) == ["B"], (pid, tool, _names(scene))
            _click(canvas, _empty(canvas))
            assert _names(scene) == [] and not scene.object_selected, (pid, tool)
            assert all(np.allclose(o.position[1:], 0.0) for o in (a, b, c))


def test_click_in_component_modes() -> None:
    for pid in PROFILES:
        for tool in TRANSFORMS:
            win, scene, canvas, objs = _setup(pid, "points", tool)
            pts = _visible(canvas, scene, "point")
            (i, pi), (j, pj) = pts[0], pts[1]
            _click(canvas, pi)
            assert scene.selected_points == {i}, (pid, tool)
            _click(canvas, pj, SHIFT)
            assert scene.selected_points == {i, j}, (pid, tool)
            _click(canvas, pi, CTRL)
            assert scene.selected_points == {j}, (pid, tool)
            _click(canvas, pi, CTRL)
            assert scene.selected_points == {i, j}, (pid, tool)
            _click(canvas, _empty(canvas))
            assert scene.selected_points == set(), (pid, tool)
        win, scene, canvas, (a, b, c) = _setup(pid, "polygons", count=3)
        polys = _visible(canvas, scene, "polygon")
        _click(canvas, polys[0][1])
        assert scene.selected_polygons == {polys[0][0]}
        _click(canvas, _obj_px(canvas, b) + (0.0, 24.0))
        assert scene.active is b and scene.mode == "polygons", (pid, scene.active.name, scene.mode)
        para = scene.add_parametric("cube")
        para.position = np.array([0.0, 0.0, 600.0])
        scene.changed.emit()
        scene.set_active(b)
        scene.set_mode("polygons")
        canvas.frame_all()
        _settle()
        _click(canvas, _obj_px(canvas, para))
        assert scene.active is para and scene.mode == "model", (pid, scene.active.name, scene.mode)


def test_drag_under_the_threshold_is_a_click() -> None:
    for pid in PROFILES:
        win, scene, canvas, (a, b, c) = _setup(pid, count=3)
        scene.select_objects([a, b], "replace")
        before = _transforms((a, b, c))
        threshold = canvas.drag_threshold()
        start = _obj_px(canvas, c) + (0.0, 24.0)
        _drag(canvas, start, start + (threshold / 2 - 0.5, 0.0), steps=2)
        assert _names(scene) == ["C"], (pid, _names(scene))
        assert _same(before, _transforms((a, b, c))) and _depth(scene) == 0, pid


def test_move_drag_on_empty_space_moves_in_the_view_plane() -> None:
    for pid in PROFILES:
        win, scene, canvas, (a, b, c) = _setup(pid, count=3)
        scene.select_objects([a, b], "replace", active=a)
        p0a, p0b, p0c = a.position.copy(), b.position.copy(), c.position.copy()
        screen0 = _obj_px(canvas, a)
        start = _empty(canvas)
        _drag(canvas, start, start + (64.0, -32.0))
        da, db = a.position - p0a, b.position - p0b
        assert np.linalg.norm(da) > 1.0 and np.allclose(da, db), (pid, da, db)
        assert np.allclose(c.position, p0c)
        assert abs(float(da @ canvas.view_direction())) < 1e-6 * max(1.0, float(np.linalg.norm(da)))
        moved = _obj_px(canvas, a) - screen0
        assert np.allclose(moved, (64.0, -32.0), atol=1.5), (pid, moved)
        assert _names(scene) == ["A", "B"] and scene.active is a
        assert _depth(scene) == 1, (pid, _depth(scene))
        scene.undo()
        a, b = scene.objects[:2]
        assert np.allclose(a.position, p0a) and np.allclose(b.position, p0b)


def test_move_drag_on_another_object_keeps_the_selection() -> None:
    for pid in PROFILES:
        win, scene, canvas, (a, b, c) = _setup(pid, count=3)
        p0a, p0c = a.position.copy(), c.position.copy()
        start = _obj_px(canvas, c) + (0.0, 24.0)
        _drag(canvas, start, start + (48.0, 0.0))
        assert _names(scene) == ["A"], (pid, _names(scene))
        assert np.linalg.norm(a.position - p0a) > 1.0 and np.allclose(c.position, p0c), pid
        start = _obj_px(canvas, a) + (0.0, 24.0)
        p1a = a.position.copy()
        _drag(canvas, start, start + (-48.0, 0.0))
        assert _names(scene) == ["A"] and np.linalg.norm(a.position - p1a) > 1.0, pid


def test_scale_drag_right_grows_left_shrinks() -> None:
    from quartz_studio.widgets.viewport import ViewportCanvas

    for pid in PROFILES:
        win, scene, canvas, (cube,) = _setup(pid, tool="scale")
        start = _empty(canvas)
        _drag(canvas, start, start + (32.0, 0.0))
        want = (ViewportCanvas.GIZMO_PX + 32.0) / ViewportCanvas.GIZMO_PX
        assert np.allclose(cube.scale, want, atol=1e-6), (pid, cube.scale)
        assert scene.selected_objects() == [cube] and _depth(scene) == 1
        _drag(canvas, start, start + (-64.0, 0.0))
        assert np.allclose(cube.scale, cube.scale[0]) and cube.scale[0] < 1.0, (pid, cube.scale)
        cube.scale = np.ones(3)
        _drag(canvas, start, start + (23.0, 0.0), SHIFT)
        assert np.allclose(cube.scale, round(cube.scale[0], 1)) and cube.scale[0] > 1.0, (pid, cube.scale)
        assert np.allclose(cube.position, 0.0)


def test_rotate_drag_turns_about_the_view_axis() -> None:
    from quartz_studio.scene import rotation_matrix
    from quartz_studio.widgets.viewport import ViewportCanvas

    for pid in PROFILES:
        win, scene, canvas, (cube,) = _setup(pid, tool="rotate")
        start = _empty(canvas)
        _drag(canvas, start, start + (40.0, 0.0))
        r = rotation_matrix(cube.rotation)
        view = canvas.view_direction()
        assert np.allclose(r @ view, view, atol=1e-6), (pid, cube.rotation)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(r) - 1.0) / 2.0))))
        assert abs(angle - 40.0 * ViewportCanvas.FREE_ROTATE_DEG_PER_PX) < 1e-3, (pid, angle)
        assert np.allclose(cube.position, 0.0) and _depth(scene) == 1
        cube.rotation = np.zeros(3)
        _drag(canvas, start, start + (13.0, 0.0), SHIFT)
        r = rotation_matrix(cube.rotation)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(r) - 1.0) / 2.0))))
        assert abs(angle - 5.0) < 1e-3, (pid, angle)


def test_escape_and_right_click_cancel_a_tool_drag() -> None:
    for pid in PROFILES:
        for tool in TRANSFORMS:
            win, scene, canvas, (cube,) = _setup(pid, tool=tool)
            before = _transforms((cube,))
            start = _empty(canvas)
            _drag(canvas, start, start + (40.0, -12.0), release=False)
            assert not _same(before, _transforms((cube,))), (pid, tool)
            _key(canvas, Qt.Key.Key_Escape)
            _release(canvas, start + (40.0, -12.0))
            assert _same(before, _transforms((cube,))) and _depth(scene) == 0, (pid, tool)
            assert scene.selected_objects() == [cube]
            _drag(canvas, start, start + (40.0, -12.0), release=False)
            _press(canvas, start + (40.0, -12.0), RIGHT)
            _release(canvas, start + (40.0, -12.0), RIGHT)
            _release(canvas, start + (40.0, -12.0))
            assert _same(before, _transforms((cube,))) and _depth(scene) == 0, (pid, tool)
            assert canvas.context_menu is None and QApplication.activePopupWidget() is None, (pid, tool)


def test_drag_with_nothing_selected_does_nothing() -> None:
    for pid in PROFILES:
        for tool in TRANSFORMS:
            win, scene, canvas, objs = _setup(pid, tool=tool, count=3)
            scene.select_objects([], "replace")
            before = _transforms(objs)
            start = _empty(canvas)
            _drag(canvas, start, start + (64.0, 16.0))
            assert _same(before, _transforms(objs)) and _depth(scene) == 0, (pid, tool)
            assert scene.selected_objects() == [], (pid, tool)
            assert canvas._drag is None


def test_gizmo_handles_still_constrain() -> None:
    for pid in PROFILES:
        win, scene, canvas, (cube,) = _setup(pid)
        (sx, sy), (ex, ey) = canvas.gizmo_handles()["x"]
        grip = np.array([sx + (ex - sx) * 0.8, sy + (ey - sy) * 0.8])
        assert canvas.gizmo_pick(grip) == "x"
        _drag(canvas, grip, grip + (40.0, 0.0))
        assert abs(cube.position[0]) > 1.0 and np.allclose(cube.position[1:], 0.0), (pid, cube.position)
        assert scene.selected_objects() == [cube] and _depth(scene) == 1
        win, scene, canvas, (cube,) = _setup(pid, tool="scale")
        (sx, sy), (ex, ey) = canvas.gizmo_handles()["y"]
        grip = np.array([sx + (ex - sx) * 0.95, sy + (ey - sy) * 0.95])
        assert canvas.gizmo_pick(grip) == "y", canvas.gizmo_pick(grip)
        _drag(canvas, grip, grip + ((ex - sx) * 0.5, (ey - sy) * 0.5))
        assert cube.scale[1] > 1.0 and np.allclose(cube.scale[[0, 2]], 1.0), (pid, cube.scale)


def test_component_drag_moves_the_selection_in_the_view_plane() -> None:
    for pid in PROFILES:
        win, scene, canvas, (cube,) = _setup(pid, "points")
        (i, pi), (j, pj) = _visible(canvas, scene, "point")[:2]
        _click(canvas, pi)
        before = cube.mesh.points.copy()
        start = _empty(canvas)
        _drag(canvas, start, start + (40.0, 24.0))
        delta = cube.mesh.points[i] - before[i]
        assert np.linalg.norm(delta) > 1.0 and abs(float(delta @ canvas.view_direction())) < 1e-6, (pid, delta)
        others = [k for k in range(8) if k != i]
        assert np.allclose(cube.mesh.points[others], before[others])
        assert scene.selected_points == {i} and _depth(scene) == 1, pid
        before = cube.mesh.points.copy()
        _drag(canvas, pj, pj + (24.0, 0.0))
        assert scene.selected_points == {i} and not np.allclose(cube.mesh.points[i], before[i]), pid
        assert np.allclose(cube.mesh.points[j], before[j])


def test_brush_selection_left_drag_still_paints() -> None:
    for pid in PROFILES:
        win, scene, canvas, (cube,) = _setup(pid, "polygons", "select")
        polys = _visible(canvas, scene, "polygon")
        (k0, p0), (k1, p1) = polys[0], polys[1]
        _drag(canvas, p0, p1, steps=16)
        assert {k0, k1} <= scene.selected_polygons, (pid, scene.selected_polygons)
        assert np.allclose(cube.position, 0.0)


def test_right_click_selects_and_opens_the_menu() -> None:
    for pid in PROFILES:
        win, scene, canvas, (a, b, c) = _setup(pid, count=3)
        _click(canvas, _obj_px(canvas, b) + (0.0, 24.0), button=RIGHT)
        assert _names(scene) == ["B"] and canvas.context_menu is not None, pid
        _close_popups()
        canvas.context_menu = None
        _click(canvas, _obj_px(canvas, c) + (0.0, 24.0), SHIFT, RIGHT)
        assert _names(scene) == ["B", "C"] and canvas.context_menu is not None, (pid, _names(scene))
        _close_popups()
        canvas.context_menu = None
        _click(canvas, _empty(canvas), button=RIGHT)
        assert _names(scene) == ["B", "C"] and canvas.context_menu is not None, (pid, _names(scene))
        _close_popups()
        win, scene, canvas, (cube,) = _setup(pid, "polygons")
        polys = _visible(canvas, scene, "polygon")
        _click(canvas, polys[0][1])
        _click(canvas, polys[1][1], button=RIGHT)
        assert scene.selected_polygons == {polys[1][0]} and canvas.context_menu is not None, pid
        _close_popups()


def test_right_drag_paints_the_selection_without_a_menu() -> None:
    for pid in PROFILES:
        for tool in ("move", "scale", "select"):
            win, scene, canvas, (cube,) = _setup(pid, "polygons", tool)
            polys = _visible(canvas, scene, "polygon")
            assert len(polys) >= 3, polys
            (k0, p0), (k1, p1), (k2, p2) = polys[:3]
            _click(canvas, p2)
            assert scene.selected_polygons == {k2}
            before = cube.mesh.points.copy()
            base = _depth(scene)
            _drag(canvas, p0, p1, button=RIGHT, steps=16)
            assert {k0, k1} <= scene.selected_polygons and k2 not in scene.selected_polygons, (
                pid, tool, scene.selected_polygons)
            assert _depth(scene) == base + 1 and canvas.context_menu is None, (pid, tool)
            _drag(canvas, p2, p2 + (2.0, 4.0) * np.sign(p2 - p0), SHIFT, RIGHT, steps=4)
            assert {k0, k1, k2} <= scene.selected_polygons, (pid, tool, scene.selected_polygons)
            assert _depth(scene) == base + 2 and canvas.context_menu is None
            _drag(canvas, p0, p0 + (p1 - p0) * 0.2, CTRL, RIGHT, steps=4)
            assert k0 not in scene.selected_polygons and {k1, k2} <= scene.selected_polygons, (
                pid, tool, scene.selected_polygons)
            assert _depth(scene) == base + 3 and canvas.context_menu is None
            assert QApplication.activePopupWidget() is None
            assert np.allclose(cube.mesh.points, before) and np.allclose(cube.position, 0.0)
            scene.undo()
            cube = scene.active
            assert {k0, k1, k2} <= scene.selected_polygons
        win, scene, canvas, (a, b, c) = _setup(pid, count=3)
        _drag(canvas, _obj_px(canvas, b) + (0.0, 24.0), _obj_px(canvas, c) + (0.0, 24.0), button=RIGHT, steps=24)
        assert _names(scene) == ["B", "C"] and canvas.context_menu is None, (pid, _names(scene))
        _drag(canvas, _obj_px(canvas, a) + (0.0, 24.0), _obj_px(canvas, a) + (8.0, 24.0), SHIFT, RIGHT)
        assert _names(scene) == ["A", "B", "C"], (pid, _names(scene))
        _drag(canvas, _obj_px(canvas, b) + (0.0, 24.0), _obj_px(canvas, b) + (8.0, 24.0), CTRL, RIGHT)
        assert _names(scene) == ["A", "C"] and canvas.context_menu is None, (pid, _names(scene))
        assert all(np.allclose(o.position[1:], 0.0) for o in (a, b, c))


def test_navigation_gestures_still_navigate() -> None:
    for pid in PROFILES:
        win, scene, canvas, (cube,) = _setup(pid)
        start = _empty(canvas) + (0.0, -64.0)
        rows = [(RIGHT, ALT, "distance"), (LEFT, ALT, "heading"), (MIDDLE, NO_MOD, "heading")]
        for button, mods, attr in rows:
            cam0 = canvas.camera.copy()
            _drag(canvas, start, start + (48.0, -32.0), mods, button)
            assert getattr(canvas.camera, attr) != getattr(cam0, attr), (pid, button, mods)
            assert np.allclose(cube.position, 0.0) and scene.selected_objects() == [cube]
            assert canvas.context_menu is None and _depth(scene) == 0, (pid, button, mods)
            canvas.camera = cam0
        _drag(canvas, start, start + (48.0, -32.0), release=False)
        cam0 = canvas.camera.copy()
        _press(canvas, start + (48.0, -32.0), RIGHT, ALT)
        _release(canvas, start + (48.0, -32.0), RIGHT, ALT)
        _release(canvas, start + (48.0, -32.0))
        assert np.allclose(cube.position, 0.0) and _depth(scene) == 0, pid


def test_ctrl_drag_copies_in_model_mode() -> None:
    from quartz_studio.scene import Mesh

    for pid in PROFILES:
        for tool in TRANSFORMS:
            win, scene, canvas, (a, b, c) = _setup(pid, tool=tool, count=3)
            kid = scene.add_object("Kid", Mesh.cube(50.0))
            scene.set_parent(kid, a)
            scene.select_objects([a, b], "replace", active=a)
            scene._undo.clear()
            before = _transforms((a, b, c, kid))
            count = len(scene.objects)
            start = _empty(canvas)
            _drag(canvas, start, start + (40.0, -16.0), CTRL)
            assert len(scene.objects) == count + 3, (pid, tool, [o.name for o in scene.objects])
            assert _same(before, _transforms((a, b, c, kid))), (pid, tool)
            copies = scene.selected_objects()
            assert len(copies) == 2 and all(o not in (a, b) for o in copies), (pid, tool)
            assert scene.active is not a and scene.active.name.startswith("A")
            assert any(scene.children(o) for o in copies)
            assert not _same(before[:2], _transforms(copies)), (pid, tool)
            assert _depth(scene) == 1, (pid, tool, _depth(scene))
            scene.undo()
            assert len(scene.objects) == count and _names(scene) == ["A", "B"], (pid, tool)
        win, scene, canvas, (cube,) = _setup(pid)
        (sx, sy), (ex, ey) = canvas.gizmo_handles()["x"]
        grip = np.array([sx + (ex - sx) * 0.8, sy + (ey - sy) * 0.8])
        _drag(canvas, grip, grip + (40.0, 0.0), CTRL)
        assert len(scene.objects) == 2 and np.allclose(cube.position, 0.0), pid
        assert scene.active is not cube and abs(scene.active.position[0]) > 1.0
        assert np.allclose(scene.active.position[1:], 0.0)


def test_ctrl_drag_extrudes_in_component_modes() -> None:
    for pid in PROFILES:
        win, scene, canvas, (cube,) = _setup(pid, "polygons")
        polys = _visible(canvas, scene, "polygon")
        _click(canvas, polys[0][1])
        count = len(cube.mesh.polygons)
        start = _empty(canvas)
        _drag(canvas, start, start + (0.0, -40.0), CTRL)
        assert len(cube.mesh.polygons) > count and len(scene.objects) == 1, (pid, len(cube.mesh.polygons))
        assert _depth(scene) == 1
        scene.undo()
        assert len(scene.active.mesh.polygons) == count


def test_pens_and_bevel_keep_their_behaviour() -> None:
    for pid in PROFILES:
        win, scene, canvas, (cube,) = _setup(pid, "points", "pen")
        count = len(cube.mesh.points)
        spot = _empty(canvas)
        _click(canvas, spot)
        assert len(cube.mesh.points) == count + 1 and scene.pen_active(), pid
        _click(canvas, spot + (64.0, 0.0))
        assert len(cube.mesh.points) == count + 2, pid
        _click(canvas, spot + (96.0, 0.0), button=RIGHT)
        assert not scene.pen_active() and canvas.context_menu is None, pid
        scene.pen_finish()
        scene.set_tool("move")
        win, scene, canvas, (cube,) = _setup(pid, "polygons")
        polys = _visible(canvas, scene, "polygon")
        _click(canvas, polys[0][1])
        from quartz_studio.modeling import install as mi

        mi.activate_tool("bevel")
        _settle()
        count = len(cube.mesh.polygons)
        _drag(canvas, polys[0][1], polys[0][1] + (48.0, 0.0))
        _settle()
        assert len(cube.mesh.polygons) > count, (pid, len(cube.mesh.polygons))
        assert scene.selected_polygons, pid
        mi.controller().activate(None)


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
