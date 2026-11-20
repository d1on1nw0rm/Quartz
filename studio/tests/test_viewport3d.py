from __future__ import annotations

import math
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import quartz_studio
import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio import theme
from quartz_studio.app import create_app

VIEW_SIZE = (1000, 640)
LEFT = Qt.MouseButton.LeftButton
MIDDLE = Qt.MouseButton.MiddleButton
RIGHT = Qt.MouseButton.RightButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier

_LIVE: list[QWidget] = []


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(app: QApplication, passes: int = 4) -> None:
    for _ in range(passes):
        app.processEvents()


def _make(mode: str = "model"):
    app = _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.viewport import Viewport

    while _LIVE:
        old = _LIVE.pop()
        old.close()
        old.deleteLater()
    scene = reset_scene()
    view = Viewport()
    view.resize(*VIEW_SIZE)
    view.show()
    _settle(app)
    _LIVE.append(view)
    if mode != "model":
        scene.set_mode(mode)
    return view.canvas, scene



def _mouse(widget: QWidget, kind: QEvent.Type, pos, button=NO_BUTTON, buttons=NO_BUTTON, mods=NO_MOD) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    glob = QPointF(widget.mapToGlobal(local))
    QApplication.sendEvent(widget, QMouseEvent(kind, local, glob, button, buttons, mods))


def _click(widget: QWidget, pos, mods=NO_MOD, button=LEFT) -> None:
    _mouse(widget, QEvent.Type.MouseButtonPress, pos, button, button, mods)
    _mouse(widget, QEvent.Type.MouseButtonRelease, pos, button, NO_BUTTON, mods)


def _drag(widget: QWidget, start, end, mods=NO_MOD, button=LEFT, steps: int = 10, release: bool = True) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    _mouse(widget, QEvent.Type.MouseButtonPress, start, button, button, mods)
    for k in range(1, steps + 1):
        _mouse(widget, QEvent.Type.MouseMove, start + (end - start) * k / steps, NO_BUTTON, button, mods)
    if release:
        _mouse(widget, QEvent.Type.MouseButtonRelease, end, button, NO_BUTTON, mods)


def _wheel(widget: QWidget, pos, notches: float) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    ev = QWheelEvent(local, QPointF(widget.mapToGlobal(local)), QPoint(0, 0), QPoint(0, int(120 * notches)),
                     NO_BUTTON, NO_MOD, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def _key(widget: QWidget, key: Qt.Key, text: str = "") -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, NO_MOD, text))



def _image(canvas) -> QImage:
    return canvas.grab().toImage()


def _rgb(img: QImage, pos) -> tuple[int, int, int]:
    c = img.pixelColor(int(round(float(pos[0]))), int(round(float(pos[1]))))
    return c.red(), c.green(), c.blue()


def _near(rgb: tuple[int, int, int], token: str, tolerance: int = 40) -> bool:
    c = QColor(token)
    return all(abs(a - b) <= tolerance for a, b in zip(rgb, (c.red(), c.green(), c.blue())))


def _gap(rgb: tuple[int, int, int], token: str) -> int:
    c = QColor(token)
    return sum((a - b) ** 2 for a, b in zip(rgb, (c.red(), c.green(), c.blue())))


def _is_citrine(rgb: tuple[int, int, int]) -> bool:
    return _near(rgb, theme.SELECT_FRONT)


def _empty_spot(canvas) -> tuple[float, float]:
    film = canvas.film_rect()
    return film.left() + film.width() * 0.12, film.top() + film.height() * 0.85


def _points_px(canvas, scene) -> np.ndarray:
    return canvas.project_world(scene.active.world_points())



def test_default_cube_visible() -> None:
    canvas, scene = _make()
    obj = scene.active
    assert obj is not None and obj.name == "Cube" and len(obj.mesh.points) == 8
    img = _image(canvas)
    background = _rgb(img, _empty_spot(canvas))
    for world in ((0.0, -50.0, -100.0), (100.0, -50.0, 50.0)):
        rgb = _rgb(img, canvas.project_world([world])[0])
        assert sum(abs(a - b) for a, b in zip(rgb, background)) > 60, (world, rgb, background)
        assert max(rgb) - min(rgb) < 12, f"faces are neutral grey, got {rgb}"
    xy = _points_px(canvas, scene)
    film = canvas.film_rect()
    frac = (xy[:, 1].max() - xy[:, 1].min()) / film.height()
    assert 0.18 < frac < 0.45, frac
    centre = canvas.project_world([[0.0, 0.0, 0.0]])[0]
    assert abs(centre[0] - film.center().x()) < 3 and abs(centre[1] - canvas.inner_rect().center().y()) < 3


def test_no_grid_lines_drawn() -> None:
    canvas, _scene = _make()
    for name in ("_paint_grid", "_grid_lines", "MAJOR_EXTENT"):
        assert not hasattr(canvas, name), name
    img = _image(canvas)
    film = canvas.film_rect()
    x0, x1 = int(film.left() + 90), int(film.left() + film.width() * 0.32)
    for frac in (0.62, 0.72, 0.82, 0.9):
        y = int(film.top() + film.height() * frac)
        lum = [sum(_rgb(img, (x, y))) for x in range(x0, x1)]
        assert max(lum) - min(lum) <= 6, f"row {y}: values {min(lum)}..{max(lum)}"


def test_horizon_follows_camera() -> None:
    canvas, _scene = _make()
    canvas.camera.pitch = 6.0
    _pos, fwd, _right, up = canvas.camera.basis()
    cx, cy, f = canvas._view_params()
    y = cy + f * fwd[1] / up[1]
    film = canvas.film_rect()
    assert film.top() < y < cy, y
    img = _image(canvas)
    x = film.left() + film.width() * 0.2
    line = max(sum(_rgb(img, (x, y + d))) for d in (-1, 0, 1))
    around = max(sum(_rgb(img, (x, y + d))) for d in (-8, 8))
    assert line >= around + 6, (line, around)


def test_points_click_selects_and_renders_citrine() -> None:
    canvas, scene = _make("points")
    xy = _points_px(canvas, scene)
    assert canvas.pick(xy[2]) == ("point", 2)
    _click(canvas, xy[2])
    assert scene.selected_points == {2}
    img = _image(canvas)
    assert _is_citrine(_rgb(img, xy[2])), _rgb(img, xy[2])
    plain = _rgb(img, xy[0])
    assert _near(plain, theme.POINT_FILL, 4) and not _is_citrine(plain), plain


def test_hidden_point_is_not_pickable() -> None:
    canvas, scene = _make("points")
    xy = _points_px(canvas, scene)
    assert canvas.pick(xy[4]) == (None, None)
    _click(canvas, xy[4])
    assert scene.selected_points == set()


def test_shift_add_ctrl_remove_and_empty_click_clears() -> None:
    canvas, scene = _make("points")
    xy = _points_px(canvas, scene)
    _click(canvas, xy[2])
    for i in (1, 6):
        assert canvas.gizmo_hit(xy[i]) is None
        _click(canvas, xy[i], SHIFT)
    assert scene.selected_points == {1, 2, 6}
    _click(canvas, xy[2], CTRL)
    assert scene.selected_points == {1, 6}
    _click(canvas, xy[3])
    assert scene.selected_points == {3}
    _click(canvas, _empty_spot(canvas))
    assert scene.selected_points == set()


def test_model_mode_click_selects_and_deselects_object() -> None:
    canvas, scene = _make()
    assert scene.object_selected
    _click(canvas, _empty_spot(canvas))
    assert not scene.object_selected
    face = canvas.project_world([[0.0, -60.0, -100.0]])[0]
    assert canvas.pick(face) == ("object", scene.active)
    _click(canvas, face)
    assert scene.object_selected
    img = _image(canvas)
    corner = canvas.project_world([[100.0, -100.0, -100.0]])[0]
    near = [_rgb(img, corner + d) for d in ((0, 0), (0, -1), (-1, 0), (1, 0), (0, 1))]
    assert any(_is_citrine(c) for c in near), near
    _click(canvas, face, CTRL)
    assert not scene.object_selected


def test_drag_axis_arrows_move_along_one_world_axis() -> None:
    canvas, scene = _make("points")
    obj = scene.active
    _click(canvas, _points_px(canvas, scene)[2])
    assert scene.selected_points == {2}
    for i, axis in enumerate("xyz"):
        before = obj.world_points()[2].copy()
        (sx, sy), (ex, ey) = canvas.gizmo_handles()[axis]
        s, e = np.array([sx, sy]), np.array([ex, ey])
        n = np.linalg.norm(e - s)
        assert 25 < n < 95, (axis, n)
        start = s + (e - s) * 0.6
        assert canvas.gizmo_hit(start) == axis
        u = (e - s) / n
        _drag(canvas, start, start + u * 40.0)
        delta = obj.world_points()[2] - before
        others = [j for j in range(3) if j != i]
        assert np.allclose(delta[others], 0.0, atol=1e-6), (axis, delta)
        assert delta[i] > 1.0, (axis, delta)
        moved = np.linalg.norm(canvas.project_world([before + delta])[0] - canvas.project_world([before])[0])
        assert abs(moved - 40.0) < 6.0, (axis, moved)
        assert scene.selected_points == {2}


def test_escape_cancels_drag() -> None:
    canvas, scene = _make("points")
    obj = scene.active
    _click(canvas, _points_px(canvas, scene)[2])
    before = obj.world_points().copy()
    (sx, sy), (ex, ey) = canvas.gizmo_handles()["x"]
    start = np.array([sx, sy]) + (np.array([ex, ey]) - np.array([sx, sy])) * 0.6
    _drag(canvas, start, start + (30.0, 12.0), release=False)
    assert not np.allclose(obj.world_points(), before)
    _key(canvas, Qt.Key.Key_Escape)
    assert np.allclose(obj.world_points(), before)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, start + (30.0, 12.0), LEFT, NO_BUTTON)
    assert np.allclose(obj.world_points(), before)


def test_drag_on_another_point_moves_the_selection_without_changing_it() -> None:
    canvas, scene = _make("points")
    obj = scene.active
    xy = _points_px(canvas, scene)
    before = obj.world_points().copy()
    _drag(canvas, xy[1], xy[1] + (35.0, -20.0))
    assert scene.selected_points == set()
    assert np.allclose(obj.world_points(), before)
    _click(canvas, xy[2])
    assert scene.selected_points == {2}
    start = next(xy[j] for j in (1, 3, 0, 6, 5, 7)
                 if canvas.pick(xy[j])[0] == "point" and canvas.gizmo_pick(xy[j]) is None)
    _drag(canvas, start, start + (35.0, -20.0))
    assert scene.selected_points == {2}
    after = obj.world_points()
    assert np.linalg.norm(after[2] - before[2]) > 5.0
    assert np.allclose(np.delete(after, 2, axis=0), np.delete(before, 2, axis=0))
    assert np.allclose(canvas.project_world([after[2]])[0], xy[2] + (35.0, -20.0), atol=0.6)


def test_model_mode_drag_moves_object() -> None:
    canvas, scene = _make()
    obj = scene.active
    press = canvas.project_world([[0.0, -60.0, -100.0]])[0]
    assert canvas.gizmo_hit(press) is None and canvas.pick(press)[0] == "object"
    origin_px = canvas.project_world([obj.position])[0]
    _drag(canvas, press, press + (50.0, 20.0))
    assert np.linalg.norm(obj.position) > 5.0, obj.position
    assert np.allclose(canvas.project_world([obj.position])[0], origin_px + (50.0, 20.0), atol=0.6)
    pos0 = obj.position.copy()
    (sx, sy), (ex, ey) = canvas.gizmo_handles()["y"]
    start = np.array([sx, sy]) + (np.array([ex, ey]) - np.array([sx, sy])) * 0.6
    _drag(canvas, start, start + (0.0, -30.0))
    d = obj.position - pos0
    assert d[1] > 1.0 and abs(d[0]) < 1e-6 and abs(d[2]) < 1e-6, d


def test_edges_picking() -> None:
    canvas, scene = _make("edges")
    w = scene.active.world_points()
    p12 = canvas.project_world([w[1] + (w[2] - w[1]) * 0.3])[0]
    assert canvas.pick(p12 + (2.0, 0.0)) == ("edge", (1, 2))
    _click(canvas, p12 + (2.0, 0.0))
    assert scene.selected_edges == {(1, 2)}
    img = _image(canvas)
    low = canvas.project_world([w[1] + (w[2] - w[1]) * 0.2])[0]
    assert _is_citrine(_rgb(img, low)), _rgb(img, low)
    p26 = canvas.project_world([(w[2] + w[6]) / 2])[0]
    assert canvas.gizmo_hit(p26) is None
    _click(canvas, p26, SHIFT)
    assert scene.selected_edges == {(1, 2), (2, 6)}
    p45 = canvas.project_world([(w[4] + w[5]) / 2])[0]
    assert canvas.pick(p45) != ("edge", (4, 5))
    _click(canvas, p45)
    assert (4, 5) not in scene.selected_edges


def test_polygons_picking() -> None:
    canvas, scene = _make("polygons")
    top = canvas.project_world([[0.0, 100.0, 0.0]])[0]
    assert canvas.pick(top) == ("polygon", 4)
    _click(canvas, top)
    assert scene.selected_polygons == {4}
    img = _image(canvas)
    rgb = _rgb(img, canvas.project_world([[-55.0, 100.0, -20.0]])[0])
    assert rgb[0] > rgb[2] + 40 and rgb[0] > 150, rgb
    assert _gap(rgb, theme.SELECT_FRONT) < _gap(rgb, theme.SELECT_BACK), rgb
    bottom = canvas.project_world([[0.0, -100.0, 0.0]])[0]
    _click(canvas, bottom)
    assert len(scene.selected_polygons) == 1 and 5 not in scene.selected_polygons, scene.selected_polygons
    assert scene.selected_polygons <= {0, 3}


def test_wheel_zoom_changes_distance() -> None:
    canvas, _scene = _make()
    centre = canvas.inner_rect().center()
    d0 = canvas.camera.distance
    _wheel(canvas, (centre.x(), centre.y()), 1)
    d1 = canvas.camera.distance
    assert d1 < d0
    _wheel(canvas, (centre.x(), centre.y()), -2)
    assert canvas.camera.distance > d1 and canvas.camera.distance > d0


def test_mouse_navigation() -> None:
    canvas, scene = _make()
    cam = canvas.camera
    centre = np.array([canvas.inner_rect().center().x(), canvas.inner_rect().center().y()])
    h0, p0 = cam.heading, cam.pitch
    _drag(canvas, centre, centre + (40.0, 0.0), ALT)
    assert cam.heading != h0 and scene.object_selected
    assert np.allclose(scene.active.position, 0.0)
    _drag(canvas, centre, centre + (0.0, 2000.0), ALT)
    assert abs(cam.pitch - 89.0) < 1e-6
    _drag(canvas, centre, centre + (0.0, -4000.0), ALT)
    assert abs(cam.pitch + 89.0) < 1e-6
    canvas.reset_camera()
    cam = canvas.camera
    assert (cam.heading, cam.pitch) == (h0, p0)
    grabbed = canvas.cursor_point(centre)
    _drag(canvas, centre, centre + (30.0, -15.0), ALT, MIDDLE)
    assert np.allclose(canvas.project_world([grabbed])[0], centre + (30.0, -15.0), atol=0.05)
    d0 = cam.distance
    _drag(canvas, centre, centre + (60.0, 0.0), ALT, RIGHT)
    assert cam.distance < d0
    _drag(canvas, centre, centre + (25.0, 0.0), NO_MOD, MIDDLE)
    assert cam.heading != h0
    _mouse(canvas, QEvent.Type.MouseButtonDblClick, centre, MIDDLE, MIDDLE)
    assert (canvas.camera.heading, canvas.camera.pitch, canvas.camera.distance) == (h0, p0, d0)
    assert np.allclose(canvas.camera.target, 0.0)


def test_nav_icons_drag_navigates() -> None:
    canvas, _scene = _make()
    bar = canvas.parentWidget().menu_bar
    pan, zoom, orbit = bar.nav_buttons[:3]
    cam = canvas.camera
    before = (cam.heading, cam.distance, cam.target.copy())
    _drag(orbit, (10, 10), (40, 10))
    assert cam.heading != before[0]
    _drag(zoom, (10, 10), (50, 10))
    assert cam.distance < before[1]
    _drag(pan, (10, 10), (30, 30))
    assert not np.allclose(cam.target, before[2])


def test_keyboard_tools_and_hud() -> None:
    canvas, scene = _make("points")
    assert canvas.hud_text == "Move"
    _key(canvas, Qt.Key.Key_R, "r")
    assert scene.tool == "rotate" and canvas.hud_text == "Rotate"
    _key(canvas, Qt.Key.Key_T, "t")
    assert scene.tool == "scale" and canvas.hud_text == "Scale"
    _key(canvas, Qt.Key.Key_E, "e")
    assert scene.tool == "move" and canvas.hud_text == "Move"
    scene.set_tool("select")
    assert canvas.hud_text == "Brush Selection"
    assert canvas.gizmo_handles() == {}
    xy = _points_px(canvas, scene)
    _click(canvas, xy[2])
    assert scene.selected_points == {2}
    _image(canvas)
    scene.set_tool("other")
    assert canvas.hud_text == "Brush Selection"
    _key(canvas, Qt.Key.Key_E, "e")
    assert scene.tool == "move" and canvas.hud_text == "Move"
    assert set(canvas.gizmo_handles()) == {"x", "y", "z"}


def test_gizmo_hover_and_constant_size() -> None:
    canvas, scene = _make()
    handles = canvas.gizmo_handles()
    length = {a: math.dist(*handles[a]) for a in handles}
    (sx, sy), (ex, ey) = handles["x"]
    on_x = (sx + (ex - sx) * 0.6, sy + (ey - sy) * 0.6)
    _mouse(canvas, QEvent.Type.MouseMove, on_x)
    assert _near(_rgb(_image(canvas), on_x), theme.GIZMO_HOVER, 20), _rgb(_image(canvas), on_x)
    canvas.camera.dolly(0.5)
    zoomed = canvas.gizmo_handles()
    for a in "xyz":
        assert abs(math.dist(*zoomed[a]) / length[a] - 1.0) < 0.12, (a, length[a], math.dist(*zoomed[a]))
    assert scene.has_selection()


def test_paint_is_fast() -> None:
    canvas, _scene = _make("points")
    _image(canvas)
    t = time.perf_counter()
    for _ in range(10):
        _image(canvas)
    per_frame = (time.perf_counter() - t) / 10 * 1000
    assert per_frame < 60.0, f"{per_frame:.1f} ms per frame"




def _real_drag(widget: QWidget, start, end, steps: int = 10, release: bool = True) -> None:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    start, end = np.asarray(start, float), np.asarray(end, float)
    p0 = QPoint(int(round(start[0])), int(round(start[1])))
    QTest.mousePress(widget, LEFT, NO_MOD, p0)
    for k in range(1, steps + 1):
        q = start + (end - start) * k / steps
        QTest.mouseMove(widget, QPoint(int(round(q[0])), int(round(q[1]))))
    assert QGuiApplication.mouseButtons() == LEFT
    if release:
        QTest.mouseRelease(widget, LEFT, NO_MOD, QPoint(int(round(end[0])), int(round(end[1]))))


def _arrow_start(canvas, axis: str) -> np.ndarray:
    (sx, sy), (ex, ey) = canvas.gizmo_handles()[axis]
    return np.array([sx, sy]) + (np.array([ex, ey]) - np.array([sx, sy])) * 0.6


def test_each_drag_is_one_undo_step() -> None:
    canvas, scene = _make()
    obj = scene.active
    depth0 = len(scene._undo)
    _real_drag(canvas, _arrow_start(canvas, "x"), _arrow_start(canvas, "x") + (60.0, 0.0))
    p1 = obj.position.copy()
    assert p1[0] > 5.0, p1
    assert len(scene._undo) == depth0 + 1
    _real_drag(canvas, _arrow_start(canvas, "y"), _arrow_start(canvas, "y") + (0.0, -60.0))
    p2 = scene.active.position.copy()
    assert p2[1] > 5.0 and abs(p2[0] - p1[0]) < 1e-6, p2
    assert len(scene._undo) == depth0 + 2
    _real_drag(canvas, _arrow_start(canvas, "x"), _arrow_start(canvas, "x") + (40.0, 0.0))
    assert len(scene._undo) == depth0 + 3
    assert scene.undo()
    assert np.allclose(scene.active.position, p2)
    assert scene.undo()
    assert np.allclose(scene.active.position, p1)
    assert scene.undo()
    assert np.allclose(scene.active.position, 0.0)
    assert scene.redo() and np.allclose(scene.active.position, p1)
    depth = len(scene._undo)
    press = canvas.project_world([[0.0, -60.0, -100.0]])[0]
    _real_drag(canvas, press, press, steps=1)
    assert len(scene._undo) == depth


def test_component_drags_are_separate_undo_steps() -> None:
    canvas, scene = _make("points")
    obj = scene.active
    xy = _points_px(canvas, scene)
    before = obj.world_points().copy()
    _click(canvas, xy[2])
    _real_drag(canvas, xy[2], xy[2] + (30.0, -15.0))
    mid = obj.world_points().copy()
    assert scene.selected_points == {2} and not np.allclose(mid, before)
    _real_drag(canvas, _arrow_start(canvas, "z"), _arrow_start(canvas, "z") + (25.0, 0.0))
    assert not np.allclose(obj.world_points(), mid)
    assert scene.undo()
    assert np.allclose(scene.active.world_points(), mid)
    assert scene.undo()
    assert np.allclose(scene.active.world_points(), before)


def test_cancelled_drag_leaves_no_undo_step() -> None:
    canvas, scene = _make()
    _real_drag(canvas, _arrow_start(canvas, "x"), _arrow_start(canvas, "x") + (40.0, 0.0))
    p1 = scene.active.position.copy()
    depth = len(scene._undo)
    start = _arrow_start(canvas, "y")
    _real_drag(canvas, start, start + (0.0, -50.0), release=False)
    assert not np.allclose(scene.active.position, p1)
    _key(canvas, Qt.Key.Key_Escape)
    from PySide6.QtTest import QTest
    QTest.mouseRelease(canvas, LEFT, NO_MOD, QPoint(int(start[0]), int(start[1] - 50)))
    assert np.allclose(scene.active.position, p1)
    assert len(scene._undo) == depth
    assert scene._group_depth == 0
    assert scene.undo() and np.allclose(scene.active.position, 0.0)
    canvas2, scene2 = _make()
    start = _arrow_start(canvas2, "x")
    _real_drag(canvas2, start, start + (40.0, 0.0), release=False)
    QTest.mousePress(canvas2, RIGHT, NO_MOD, QPoint(int(start[0] + 40), int(start[1])))
    QTest.mouseRelease(canvas2, RIGHT, NO_MOD, QPoint(int(start[0] + 40), int(start[1])))
    QTest.mouseRelease(canvas2, LEFT, NO_MOD, QPoint(int(start[0] + 40), int(start[1])))
    assert np.allclose(scene2.active.position, 0.0)
    assert len(scene2._undo) == 0 and scene2._group_depth == 0


def test_mode_or_tool_change_mid_drag_closes_the_undo_group() -> None:
    from PySide6.QtTest import QTest

    for change in (lambda s: s.set_mode("points"), lambda s: s.set_tool("rotate")):
        canvas, scene = _make()
        start = _arrow_start(canvas, "x")
        _real_drag(canvas, start, start + (40.0, 0.0), release=False)
        p1 = scene.active.position.copy()
        assert p1[0] > 5.0
        change(scene)
        QTest.mouseRelease(canvas, LEFT, NO_MOD, QPoint(int(start[0] + 40), int(start[1])))
        assert canvas._drag is None and scene._group_depth == 0
        assert len(scene._undo) == 1
        scene.set_mode("model")
        scene.set_tool("move")
        _real_drag(canvas, _arrow_start(canvas, "y"), _arrow_start(canvas, "y") + (0.0, -40.0))
        assert len(scene._undo) == 2
        assert scene.undo() and np.allclose(scene.active.position, p1)


def test_undo_during_drag_drops_the_drag() -> None:
    from PySide6.QtTest import QTest

    canvas, scene = _make()
    start = _arrow_start(canvas, "x")
    _real_drag(canvas, start, start + (40.0, 0.0), release=False)
    assert scene.active.position[0] > 5.0
    assert scene.undo()
    assert np.allclose(scene.active.position, 0.0)
    assert canvas._drag is None and scene._group_depth == 0
    QTest.mouseMove(canvas, QPoint(int(start[0] + 70), int(start[1])))
    QTest.mouseRelease(canvas, LEFT, NO_MOD, QPoint(int(start[0] + 70), int(start[1])))
    assert np.allclose(scene.active.position, 0.0)
    assert scene.redo() and scene.active.position[0] > 5.0

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
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
