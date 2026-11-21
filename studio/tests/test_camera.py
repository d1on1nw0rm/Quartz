from __future__ import annotations

import math
import os
import sys

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


def _press(widget, pos, button=LEFT, mods=NO_MOD) -> None:
    _mouse(widget, QEvent.Type.MouseButtonPress, pos, button, button, mods)


def _move(widget, pos, button=LEFT, mods=NO_MOD) -> None:
    _mouse(widget, QEvent.Type.MouseMove, pos, NO_BUTTON, button, mods)


def _release(widget, pos, button=LEFT, mods=NO_MOD) -> None:
    _mouse(widget, QEvent.Type.MouseButtonRelease, pos, button, NO_BUTTON, mods)


def _drag(widget, start, end, mods=NO_MOD, button=LEFT, steps: int = 10, release: bool = True) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    _press(widget, start, button, mods)
    for k in range(1, steps + 1):
        _move(widget, start + (end - start) * k / steps, button, mods)
    if release:
        _release(widget, end, button, mods)


def _wheel(widget: QWidget, pos, notches: float) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    ev = QWheelEvent(local, QPointF(widget.mapToGlobal(local)), QPoint(0, 0), QPoint(0, int(120 * notches)),
                     NO_BUTTON, NO_MOD, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def _key(widget: QWidget, key: Qt.Key, text: str = "", mods=NO_MOD, release: bool = False) -> None:
    kind = QEvent.Type.KeyRelease if release else QEvent.Type.KeyPress
    QApplication.sendEvent(widget, QKeyEvent(kind, key, mods, text))


def _image(canvas) -> QImage:
    return canvas.grab().toImage()


def _rgb(img: QImage, pos) -> tuple[int, int, int]:
    c = img.pixelColor(int(round(float(pos[0]))), int(round(float(pos[1]))))
    return c.red(), c.green(), c.blue()


def _px(canvas, world) -> np.ndarray:
    return canvas.project_world([world])[0]


def _centre(canvas) -> np.ndarray:
    c = canvas.inner_rect().center()
    return np.array([c.x(), c.y()])


def _empty_spot(canvas) -> np.ndarray:
    film = canvas.film_rect()
    return np.array([film.left() + film.width() * 0.12, film.top() + film.height() * 0.85])


def _in_film(canvas, pts) -> bool:
    film = canvas.film_rect()
    xy = canvas.project_world(pts)
    return bool(np.all(np.isfinite(xy))
                and np.all(xy[:, 0] >= film.left()) and np.all(xy[:, 0] <= film.right())
                and np.all(xy[:, 1] >= film.top()) and np.all(xy[:, 1] <= film.bottom()))


FRONT_SPOT = (40.0, -50.0, -100.0)



def test_lens_is_36mm_on_36mm_film() -> None:
    canvas, scene = _make()
    cam = canvas.camera
    assert abs(cam.focal - 1.0) < 1e-12 and not cam.ortho
    fov = math.degrees(2 * math.atan(0.5 / cam.focal))
    assert abs(fov - 53.13) < 0.01, fov
    film = canvas.film_rect()
    o, d = canvas.ray_at((film.right(), canvas.inner_rect().center().y()))
    ang = math.degrees(math.acos(float(d @ canvas.view_direction())))
    assert abs(ang - fov / 2) < 0.05, ang
    xy = canvas.project_world(scene.active.world_points())
    frac = (xy[:, 1].max() - xy[:, 1].min()) / film.height()
    assert 0.2 < frac < 0.4, frac


def test_orbit_pivot_under_clicked_point_stays_fixed() -> None:
    canvas, scene = _make()
    press = _px(canvas, FRONT_SPOT)
    h0, p0 = canvas.camera.heading, canvas.camera.pitch
    _press(canvas, press, LEFT, ALT)
    pivot = canvas._nav.pivot.copy()
    assert np.allclose(pivot, FRONT_SPOT, atol=1e-6), pivot
    for k in range(1, 9):
        _move(canvas, press + (14.0 * k, -9.0 * k), LEFT, ALT)
        assert np.allclose(_px(canvas, pivot), press, atol=1e-6), (k, _px(canvas, pivot))
        assert np.allclose(canvas.pivot_screen(), press, atol=1e-6)
    _release(canvas, press + (112.0, -72.0), LEFT, ALT)
    cam = canvas.camera
    assert cam.heading != h0 and cam.pitch != p0
    assert np.allclose(_px(canvas, pivot), press, atol=1e-6)
    assert np.allclose(scene.active.position, 0.0) and canvas.pivot_screen() is None


def test_orbit_pitch_clamps_and_mmb_orbits_around_cursor() -> None:
    canvas, _scene = _make()
    c = _centre(canvas)
    _drag(canvas, c, c + (0.0, 3000.0), ALT)
    assert abs(canvas.camera.pitch - 89.0) < 1e-9
    _drag(canvas, c, c + (0.0, -6000.0), ALT)
    assert abs(canvas.camera.pitch + 89.0) < 1e-9
    canvas.reset_camera()
    press = _px(canvas, FRONT_SPOT)
    _press(canvas, press, MIDDLE)
    pivot = canvas._nav.pivot.copy()
    for k in range(1, 6):
        _move(canvas, press + (-20.0 * k, 6.0 * k), MIDDLE)
    _release(canvas, press + (-100.0, 30.0), MIDDLE)
    assert np.allclose(pivot, FRONT_SPOT, atol=1e-6)
    assert np.allclose(_px(canvas, pivot), press, atol=1e-6)


def test_empty_space_pivot_sits_at_target_depth() -> None:
    canvas, _scene = _make()
    press = _empty_spot(canvas)
    assert canvas.hit_at(press) is None
    _press(canvas, press, LEFT, ALT)
    pivot = canvas._nav.pivot.copy()
    depth = float(canvas.camera.depth(pivot)[0])
    assert abs(depth - canvas.camera.eye_distance()) < 1e-6, depth
    assert np.allclose(_px(canvas, pivot), press, atol=1e-6)
    for k in range(1, 6):
        _move(canvas, press + (10.0 * k, 4.0 * k), LEFT, ALT)
        assert np.allclose(_px(canvas, pivot), press, atol=1e-6)
    _release(canvas, press + (50.0, 20.0), LEFT, ALT)


def test_alt_mmb_pan_keeps_grabbed_point_under_mouse() -> None:
    canvas, _scene = _make()
    for start in (_px(canvas, FRONT_SPOT), _empty_spot(canvas)):
        grabbed = canvas.cursor_point(start)
        _press(canvas, start, MIDDLE, ALT)
        for k in range(1, 8):
            mouse = start + (17.0 * k, -11.0 * k)
            _move(canvas, mouse, MIDDLE, ALT)
            assert np.allclose(_px(canvas, grabbed), mouse, atol=1e-6), (k, _px(canvas, grabbed), mouse)
        _release(canvas, start + (119.0, -77.0), MIDDLE, ALT)


def test_alt_rmb_dolly_moves_toward_the_pivot() -> None:
    canvas, _scene = _make()
    press = _px(canvas, FRONT_SPOT)
    eye0 = canvas.camera.position()
    reach0 = np.linalg.norm(eye0 - np.array(FRONT_SPOT))
    _drag(canvas, press, press + (80.0, 0.0), ALT, RIGHT)
    reach1 = np.linalg.norm(canvas.camera.position() - np.array(FRONT_SPOT))
    assert reach1 < reach0 * 0.8, (reach0, reach1)
    assert np.allclose(_px(canvas, FRONT_SPOT), press, atol=1e-6)
    _drag(canvas, press, press + (-200.0, 0.0), ALT, RIGHT)
    assert np.linalg.norm(canvas.camera.position() - np.array(FRONT_SPOT)) > reach0


def test_wheel_zoom_keeps_point_under_mouse() -> None:
    canvas, _scene = _make()
    for spot_px in (_px(canvas, FRONT_SPOT), _empty_spot(canvas)):
        point = canvas.cursor_point(spot_px)
        eye_reach = np.linalg.norm(canvas.camera.position() - point)
        d0 = canvas.camera.distance
        _wheel(canvas, spot_px, 1)
        assert abs(canvas.camera.distance / d0 - 0.88) < 1e-9, canvas.camera.distance / d0
        assert abs(np.linalg.norm(canvas.camera.position() - point) / eye_reach - 0.88) < 1e-9
        assert np.allclose(_px(canvas, point), spot_px, atol=1e-6)
        _wheel(canvas, spot_px, -1)
        assert abs(canvas.camera.distance - d0) < 1e-6
        assert np.allclose(_px(canvas, point), spot_px, atol=1e-6)


def test_wheel_never_passes_through_the_point() -> None:
    from quartz_studio.widgets.viewport import reach_floor

    canvas, _scene = _make()
    spot = _px(canvas, FRONT_SPOT)
    for _ in range(80):
        _wheel(canvas, spot, 1)
    reach = np.linalg.norm(canvas.camera.position() - np.array(FRONT_SPOT))
    assert reach_floor(FRONT_SPOT) < reach < 1618.0 * 0.88 ** 79, reach
    assert float(canvas.camera.depth(FRONT_SPOT)[0]) > 0
    assert np.allclose(_px(canvas, FRONT_SPOT), spot, atol=1e-4)


def test_number_keys_with_left_drag_navigate() -> None:
    canvas, scene = _make("points")
    start = _px(canvas, FRONT_SPOT)
    grabbed = canvas.cursor_point(start)
    _key(canvas, Qt.Key.Key_1, "1")
    _drag(canvas, start, start + (40.0, 25.0))
    _key(canvas, Qt.Key.Key_1, "1", release=True)
    assert np.allclose(_px(canvas, grabbed), start + (40.0, 25.0), atol=1e-6)
    assert scene.selected_points == set() and np.allclose(scene.active.position, 0.0)
    start = _px(canvas, FRONT_SPOT)
    d0 = canvas.camera.distance
    _key(canvas, Qt.Key.Key_2, "2")
    _drag(canvas, start, start + (60.0, 0.0))
    _key(canvas, Qt.Key.Key_2, "2", release=True)
    assert canvas.camera.distance < d0
    assert np.allclose(_px(canvas, FRONT_SPOT), start, atol=1e-6)
    h0 = canvas.camera.heading
    _key(canvas, Qt.Key.Key_3, "3")
    _drag(canvas, start, start + (50.0, 10.0))
    _key(canvas, Qt.Key.Key_3, "3", release=True)
    assert canvas.camera.heading != h0
    assert np.allclose(_px(canvas, FRONT_SPOT), start, atol=1e-6)
    xy = canvas.project_world(scene.active.world_points())
    _press(canvas, xy[2])
    _release(canvas, xy[2])
    assert scene.selected_points == {2}


def test_frame_keys_h_s_o() -> None:
    from quartz_studio.scene import Mesh

    canvas, scene = _make()
    cube = scene.active
    scene.set_object_position(0, 3000.0)
    other = scene.add_object("Cube", Mesh.cube(100.0))
    scene.set_object_position(1, 900.0)
    scene.set_object_position(2, -1500.0)
    assert not _in_film(canvas, cube.world_points())
    _key(canvas, Qt.Key.Key_H, "h")
    lo, hi = scene.world_bounds()
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    assert _in_film(canvas, corners)
    assert np.allclose(canvas.camera.target, (lo + hi) / 2)
    _key(canvas, Qt.Key.Key_O, "o")
    pts = other.world_points()
    assert _in_film(canvas, pts) and np.allclose(canvas.camera.target, pts.mean(axis=0))
    xy = canvas.project_world(pts)
    assert (xy[:, 1].max() - xy[:, 1].min()) > canvas.film_rect().height() * 0.4
    scene.set_active(cube)
    scene.set_mode("points")
    scene.select_components([2])
    _key(canvas, Qt.Key.Key_S, "s")
    p2 = cube.world_points()[2]
    assert np.allclose(canvas.camera.target, p2)
    assert np.allclose(_px(canvas, p2), _centre(canvas), atol=1e-6)
    _key(canvas, Qt.Key.Key_H, "H", SHIFT)
    assert np.allclose(canvas.camera.target, 0.0) and canvas.camera.heading == 45.0


def test_function_keys_switch_views() -> None:
    canvas, _scene = _make()
    canvas.navigate("orbit", 30.0, 10.0)
    persp = canvas.camera.state()
    _key(canvas, Qt.Key.Key_F2)
    cam = canvas.camera
    assert canvas.view_name == "Top" and cam.ortho and cam.pitch == 90.0
    o = _px(canvas, (0.0, 0.0, 0.0))
    assert _px(canvas, (100.0, 0.0, 0.0))[0] > o[0] + 10
    assert _px(canvas, (0.0, 0.0, 100.0))[1] < o[1] - 10
    assert np.allclose(_px(canvas, (0.0, 500.0, 0.0)), o)
    _key(canvas, Qt.Key.Key_F3)
    assert canvas.view_name == "Right" and canvas.camera.ortho
    o = _px(canvas, (0.0, 0.0, 0.0))
    assert _px(canvas, (0.0, 0.0, 100.0))[0] > o[0] + 10
    assert _px(canvas, (0.0, 100.0, 0.0))[1] < o[1] - 10
    _key(canvas, Qt.Key.Key_F4)
    assert canvas.view_name == "Front"
    o = _px(canvas, (0.0, 0.0, 0.0))
    assert _px(canvas, (100.0, 0.0, 0.0))[0] > o[0] + 10
    assert np.allclose(_px(canvas, (0.0, 0.0, 700.0)), o)
    _key(canvas, Qt.Key.Key_F1)
    assert canvas.view_name == "Perspective" and canvas.camera.state() == persp
    img = _image(canvas)
    assert not img.isNull()


def test_camera_menu_switches_views_and_pivot_mode() -> None:
    canvas, _scene = _make()
    bar = canvas.parentWidget().menu_bar
    for name in ("Perspective", "Parallel", "Left", "Right", "Front", "Back", "Top", "Bottom"):
        assert name in bar.view_actions, name
    assert bar.view_actions["Perspective"].isChecked()
    bar.view_actions["Left"].trigger()
    assert canvas.view_name == "Left" and canvas.camera.ortho and canvas.camera.heading == -90.0
    assert bar.view_actions["Left"].isChecked() and not bar.view_actions["Perspective"].isChecked()
    _image(canvas)
    bar.view_actions["Bottom"].trigger()
    assert canvas.view_name == "Bottom" and canvas.camera.pitch == -90.0
    bar.view_actions["Parallel"].trigger()
    assert canvas.view_name == "Parallel" and canvas.camera.ortho
    _key(canvas, Qt.Key.Key_F1)
    assert bar.view_actions["Perspective"].isChecked()
    canvas.camera.target = np.array([5000.0, 0.0, 0.0])
    bar.menu_action("View", "Frame Geometry").trigger()
    assert np.allclose(canvas.camera.target, 0.0)
    assert bar.nav_pivot_actions["Cursor"].isChecked() and canvas.nav_pivot == "Cursor"
    bar.nav_pivot_actions["Center"].trigger()
    assert canvas.nav_pivot == "Center" and bar.nav_pivot_actions["Center"].isChecked()
    press = _px(canvas, FRONT_SPOT)
    target = canvas.camera.target.copy()
    _press(canvas, press, LEFT, ALT)
    assert np.allclose(canvas._nav.pivot, target)
    _move(canvas, press + (30.0, 0.0), LEFT, ALT)
    _release(canvas, press + (30.0, 0.0), LEFT, ALT)
    assert np.allclose(canvas.camera.target, target)


def test_orbit_in_an_axis_view_turns_it_parallel() -> None:
    canvas, _scene = _make()
    _key(canvas, Qt.Key.Key_F4)
    press = _px(canvas, FRONT_SPOT)
    _drag(canvas, press, press + (40.0, 20.0), ALT)
    assert canvas.view_name == "Parallel" and canvas.camera.ortho
    assert np.allclose(_px(canvas, FRONT_SPOT), press, atol=1e-6)
    _key(canvas, Qt.Key.Key_F2)
    _drag(canvas, _centre(canvas), _centre(canvas) + (0.0, 40.0), ALT)
    assert canvas.camera.pitch <= 90.0
    _drag(canvas, _centre(canvas), _centre(canvas) + (0.0, -40.0), ALT)
    assert canvas.camera.pitch < 89.0


def test_parallel_views_zoom_and_pan_exactly() -> None:
    canvas, _scene = _make()
    _key(canvas, Qt.Key.Key_F4)
    o, d = canvas.ray_at((100.0, 100.0))
    o2, d2 = canvas.ray_at((500.0, 300.0))
    assert np.allclose(d, d2) and not np.allclose(o, o2)
    spot = _px(canvas, FRONT_SPOT)
    size0 = canvas.px_size(1.0)
    _wheel(canvas, spot, 2)
    assert abs(canvas.px_size(1.0) / size0 - 0.88 ** 2) < 1e-9
    assert np.allclose(_px(canvas, FRONT_SPOT), spot, atol=1e-6)
    empty = _empty_spot(canvas)
    point = canvas.cursor_point(empty)
    _wheel(canvas, empty, -1)
    assert np.allclose(_px(canvas, point), empty, atol=1e-6)
    grabbed = canvas.cursor_point(spot)
    _drag(canvas, spot, spot + (-35.0, 22.0), ALT, MIDDLE)
    assert np.allclose(_px(canvas, grabbed), spot + (-35.0, 22.0), atol=1e-6)
    for _ in range(200):
        _wheel(canvas, spot, 1)
    assert canvas.camera.distance > 0 and np.all(np.isfinite(canvas.project_world([FRONT_SPOT])))


def test_parallel_view_picking_and_gizmo_drags_are_exact() -> None:
    canvas, scene = _make("points")
    obj = scene.active
    _key(canvas, Qt.Key.Key_F4)
    xy = canvas.project_world(obj.world_points())
    assert np.allclose(xy[0], xy[4])
    assert canvas.pick(xy[0]) == ("point", 0)
    _press(canvas, xy[0])
    _release(canvas, xy[0])
    assert scene.selected_points == {0}
    for axis in "xy":
        i = "xyz".index(axis)
        before = obj.world_points()[0].copy()
        (sx, sy), (ex, ey) = canvas.gizmo_handles()[axis]
        s, e = np.array([sx, sy]), np.array([ex, ey])
        u = (e - s) / np.linalg.norm(e - s)
        start = s + (e - s) * 0.6
        assert canvas.gizmo_hit(start) == axis
        _drag(canvas, start, start + u * 40.0)
        delta = obj.world_points()[0] - before
        assert np.allclose(np.delete(delta, i), 0.0, atol=1e-9), (axis, delta)
        moved = np.linalg.norm(_px(canvas, before + delta) - _px(canvas, before))
        assert abs(moved - 40.0) < 1e-6, (axis, moved)
    p = _px(canvas, obj.world_points()[0])
    _drag(canvas, p, p + (23.0, -31.0))
    assert np.allclose(_px(canvas, obj.world_points()[0]), p + (23.0, -31.0), atol=1e-6)
    _key(canvas, Qt.Key.Key_F2)
    before = obj.world_points()[0].copy()
    (sx, sy), (ex, ey) = canvas.gizmo_handles()["z"]
    assert ey < sy - 30 and abs(ex - sx) < 1e-6
    start = np.array([sx, sy]) + (np.array([ex, ey]) - np.array([sx, sy])) * 0.6
    _drag(canvas, start, start + (0.0, -30.0))
    delta = obj.world_points()[0] - before
    assert delta[2] > 1.0 and abs(delta[0]) < 1e-9 and abs(delta[1]) < 1e-9, delta
    assert abs(delta[2] / canvas.px_size(1.0) - 30.0) < 1e-6
    scene.set_mode("polygons")
    assert canvas.pick(_px(canvas, (0.0, 100.0, 0.0))) == ("polygon", 4)


def test_view_undo_redo_is_separate_from_scene_undo() -> None:
    canvas, scene = _make()
    depth = len(scene._undo)
    s0 = canvas.camera.state()
    c = _centre(canvas)
    _drag(canvas, c, c + (40.0, 10.0), ALT)
    s1 = canvas.camera.state()
    _wheel(canvas, c, 1)
    _wheel(canvas, c, 1)
    s2 = canvas.camera.state()
    _key(canvas, Qt.Key.Key_F2)
    assert canvas.view_name == "Top"
    ctrl_shift = CTRL | SHIFT
    _key(canvas, Qt.Key.Key_Z, "Z", ctrl_shift)
    assert canvas.view_name == "Perspective" and canvas.camera.state() == s2
    _key(canvas, Qt.Key.Key_Z, "Z", ctrl_shift)
    assert canvas.camera.state() == s1
    _key(canvas, Qt.Key.Key_Z, "Z", ctrl_shift)
    assert canvas.camera.state() == s0 and not canvas.can_undo_view()
    _key(canvas, Qt.Key.Key_Y, "Y", ctrl_shift)
    assert canvas.camera.state() == s1
    _key(canvas, Qt.Key.Key_Y, "Y", ctrl_shift)
    _key(canvas, Qt.Key.Key_Y, "Y", ctrl_shift)
    assert canvas.view_name == "Top" and canvas.camera.pitch == 90.0
    assert len(scene._undo) == depth
    n = len(canvas._view_undo)
    _press(canvas, c, LEFT, ALT)
    _release(canvas, c, LEFT, ALT)
    assert len(canvas._view_undo) == n
    for k in range(140):
        canvas.navigate("orbit", 1.0, 0.0)
        canvas._push_view()
    assert len(canvas._view_undo) == 128


def test_view_keys_win_over_window_shortcuts() -> None:
    from PySide6.QtTest import QTest

    from quartz_studio.main_window import MainWindow
    from quartz_studio.scene import reset_scene

    app = _app()
    scene = reset_scene()
    win = MainWindow()
    win.resize(1600, 900)
    win.show()
    _settle(app)
    try:
        canvas = win.regions["viewport"].canvas
        canvas.setFocus()
        _settle(app)
        scene.set_object_position(0, 50.0)
        s0 = canvas.camera.state()
        canvas.begin_navigation("orbit")
        canvas.navigate("orbit", 30.0, 0.0)
        canvas.end_navigation()
        QTest.keyClick(canvas, Qt.Key.Key_Z, CTRL | SHIFT)
        assert canvas.camera.state() == s0 and canvas.can_redo_view()
        assert scene.active.position[0] == 50.0
        QTest.keyClick(canvas, Qt.Key.Key_Z, CTRL)
        assert scene.active.position[0] == 0.0
        QTest.keyClick(canvas, Qt.Key.Key_F2)
        assert canvas.view_name == "Top"
    finally:
        win.close()
        win.deleteLater()
        _settle(app)


def test_pivot_marker_drawn_only_while_navigating() -> None:
    canvas, _scene = _make()
    press = _px(canvas, FRONT_SPOT)
    assert canvas.pivot_screen() is None
    _press(canvas, press, LEFT, ALT)
    _move(canvas, press + (12.0, 4.0), LEFT, ALT)
    at = canvas.pivot_screen()
    assert at is not None and np.allclose(at, press, atol=1e-6)
    img = _image(canvas)
    cx, cy = int(at[0]), int(at[1])
    r, g, b = _rgb(img, (cx, cy))
    assert min(r, g, b) > min(QColor(theme.TEXT_BRIGHT).getRgb()[:3]) - 20, (r, g, b)
    ring = [_rgb(img, (cx + dx, cy + dy)) for dx, dy in ((3, 0), (-3, 0), (0, 3), (0, -3))]
    assert sum(max(c) < 90 for c in ring) >= 3, ring
    tick = _rgb(img, (cx + 7, cy))
    assert min(tick) > 150, tick
    _release(canvas, press + (12.0, 4.0), LEFT, ALT)
    assert canvas.pivot_screen() is None
    r, g, b = _rgb(_image(canvas), (cx, cy))
    assert max(r, g, b) < 215, (r, g, b)


def test_nav_icon_stays_down_while_dragging() -> None:
    canvas, _scene = _make()
    bar = canvas.parentWidget().menu_bar
    orbit = bar.nav_buttons[2]
    clicks: list[bool] = []
    orbit.clicked.connect(lambda *_: clicks.append(True))
    h0 = canvas.camera.heading
    _press(orbit, (10, 10))
    for k in range(1, 6):
        _move(orbit, (10 + 30 * k, 10 + 5 * k))
        assert orbit.isDown(), k
    assert canvas.pivot_screen() is not None
    _release(orbit, (160, 35))
    assert not orbit.isDown() and clicks == []
    assert canvas.camera.heading != h0 and canvas.pivot_screen() is None
    assert canvas.can_undo_view()
    _press(orbit, (10, 10))
    _move(orbit, (40, 10))
    _move(orbit, (10, 10))
    _release(orbit, (10, 10))
    assert clicks == [] and not orbit.isDown()


def test_viewport_draws_no_mode_and_tool_footer() -> None:
    canvas, scene = _make()
    assert not hasattr(canvas, "footer_left") and not hasattr(canvas, "footer_right")
    inner = canvas.inner_rect()
    row = int(inner.bottom()) - 14
    xs = range(int(inner.right()) - 260, int(inner.right()) - 12)
    for mode, tool in (("model", "move"), ("points", "move"), ("polygons", "rotate")):
        scene.set_tool(tool)
        scene.set_mode(mode)
        img = _image(canvas)
        values = {_rgb(img, (x, row)) for x in xs}
        assert len(values) == 1, (mode, tool, sorted(values)[:4])


def test_ray_and_unproject_helpers() -> None:
    canvas, _scene = _make()
    for view in (None, Qt.Key.Key_F2):
        if view is not None:
            _key(canvas, view)
        spot = _px(canvas, FRONT_SPOT) if view is None else _px(canvas, (30.0, 100.0, -20.0))
        o, d = canvas.ray_at(spot)
        assert abs(np.linalg.norm(d) - 1.0) < 1e-12
        p = canvas.unproject(spot, 700.0)
        assert abs(float(canvas.camera.depth(p)[0]) - 700.0) < 1e-6
        assert np.allclose(_px(canvas, p), spot, atol=1e-6)
        q = canvas.unproject(spot, ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        assert q is not None and abs(q[1]) < 1e-6 and np.allclose(_px(canvas, q), spot, atol=1e-6)
        hit = canvas.hit_at(spot)
        assert hit is not None and np.allclose(canvas.cursor_point(spot), hit[2])
        toward = canvas.toward_camera(hit[2])
        assert float(toward @ canvas.view_direction()) < 0



def _far_cube(scene, canvas, size: float = 1000.0, behind: float = 3000.0):
    from quartz_studio.scene import Mesh

    eye, fwd, _r, _u = canvas.camera.basis()
    far = scene.add_object("Cube", Mesh.cube(size))
    far.position = np.asarray(canvas.camera.target, float) + fwd * behind
    scene.changed.emit()
    scene.set_active(scene.objects[0])
    return far


def test_wheel_zoom_never_stalls_on_a_close_target() -> None:
    from quartz_studio.widgets.viewport import reach_floor

    canvas, scene = _make()
    far = _far_cube(scene, canvas)
    empty = np.array([500.0, 120.0])
    assert canvas.hit_at(empty) is None
    for k in range(20):
        eye = canvas.camera.position()
        _wheel(canvas, empty, 1)
        step = float(np.linalg.norm(canvas.camera.position() - eye))
        assert step > 0.5, (k, step, canvas.camera.distance)
        assert canvas.camera.distance >= canvas.carry_depth() - 1e-9
    assert canvas.hit_at(empty) is None
    centre = _px(canvas, far.position)
    hit = canvas.hit_at(centre)
    assert hit is not None and hit[0] is far, hit
    point = hit[2]
    reach0 = float(np.linalg.norm(canvas.camera.position() - point))
    assert reach0 > 1000.0, reach0
    for _ in range(80):
        _wheel(canvas, centre, 1)
    reach = float(np.linalg.norm(canvas.camera.position() - point))
    assert reach_floor(point) < reach < reach0 * 0.88 ** 79, (reach0, reach)
    assert np.allclose(_px(canvas, point), centre, atol=1e-4)


def test_dolly_and_pan_keep_moving_after_zooming_into_empty_space() -> None:
    canvas, _scene = _make()
    spot = _empty_spot(canvas)
    for _ in range(80):
        _wheel(canvas, spot, 1)
    assert canvas.hit_at(spot) is None
    eye0 = canvas.camera.position()
    _drag(canvas, spot, spot + (300.0, 0.0), ALT, RIGHT)
    moved = float(np.linalg.norm(canvas.camera.position() - eye0))
    assert moved > 20.0, moved
    grabbed = canvas.cursor_point(spot)
    eye0 = canvas.camera.position()
    _drag(canvas, spot, spot + (120.0, -60.0), ALT, MIDDLE)
    assert np.allclose(_px(canvas, grabbed), spot + (120.0, -60.0), atol=1e-6)
    assert float(np.linalg.norm(canvas.camera.position() - eye0)) > 10.0


def test_camera_navigation_mode_dolly_walks_along_the_view() -> None:
    canvas, _scene = _make()
    canvas.parent().menu_bar.nav_pivot_actions["Camera"].trigger()
    assert canvas.nav_pivot == "Camera"
    centre = _centre(canvas)
    eye0, fwd0 = canvas.camera.position(), canvas.view_direction()
    corner = _px(canvas, (100.0, 100.0, -100.0))
    _drag(canvas, centre, centre + (120.0, 0.0), ALT, RIGHT)
    step = canvas.camera.position() - eye0
    assert float(step @ fwd0) > 300.0, step
    assert np.allclose(np.cross(step, fwd0), 0.0, atol=1e-6)
    assert np.allclose(canvas.view_direction(), fwd0)
    assert float(np.linalg.norm(_px(canvas, (100.0, 100.0, -100.0)) - corner)) > 5.0
    eye1 = canvas.camera.position()
    _key(canvas, Qt.Key.Key_2, "2")
    _drag(canvas, centre, centre + (-120.0, 0.0))
    _key(canvas, Qt.Key.Key_2, "2", release=True)
    assert float((canvas.camera.position() - eye1) @ fwd0) < -300.0


def _main_window():
    from quartz_studio.main_window import MainWindow
    from quartz_studio.scene import reset_scene

    app = _app()
    scene = reset_scene()
    win = MainWindow()
    win.resize(1600, 1000)
    win.show()
    win.activateWindow()
    _settle(app, 8)
    return app, scene, win


def test_view_keys_work_without_clicking_the_view() -> None:
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtWidgets import QLineEdit

    from quartz_studio.widgets.viewport import ViewportCanvas

    app, _scene, win = _main_window()
    try:
        canvas = win.findChild(ViewportCanvas)
        assert QApplication.focusWidget() is canvas, QApplication.focusWidget()
        _key(QApplication.focusWidget(), Qt.Key.Key_F2)
        assert canvas.view_name == "Top"
        other = win.regions["object_manager"] if "object_manager" in win.regions else win.centralWidget()
        other.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        other.setFocus()
        _settle(app)
        assert not canvas.hasFocus()
        local = QPointF(300.0, 200.0)
        QApplication.sendEvent(canvas, QEnterEvent(local, local, QPointF(canvas.mapToGlobal(local))))
        _settle(app)
        assert canvas.hasFocus()
        _key(QApplication.focusWidget(), Qt.Key.Key_F1)
        assert canvas.view_name == "Perspective"
        other.setFocus()
        _settle(app)
        _wheel(canvas, (300.0, 200.0), 1)
        assert canvas.hasFocus()
        field = win.findChild(QLineEdit)
        assert field is not None
        field.setFocus()
        _settle(app)
        QApplication.sendEvent(canvas, QEnterEvent(local, local, QPointF(canvas.mapToGlobal(local))))
        _wheel(canvas, (300.0, 200.0), 1)
        _settle(app)
        assert QApplication.focusWidget() is field
    finally:
        win.close()
        win.deleteLater()
        _settle(app)


def test_held_number_key_navigates_even_without_focus() -> None:
    from quartz_studio.widgets.viewport import ViewportCanvas

    app, scene, win = _main_window()
    try:
        canvas = win.findChild(ViewportCanvas)
        other = win.centralWidget()
        other.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        other.setFocus()
        _settle(app)
        assert not canvas.hasFocus()
        cam0 = canvas.camera.state()
        pos0 = scene.active.position.copy()
        undo0 = len(scene._undo)
        _key(QApplication.focusWidget(), Qt.Key.Key_1, "1")
        start = _px(canvas, (0.0, 0.0, -100.0))
        _drag(canvas, start, start + (120.0, 0.0))
        _key(other, Qt.Key.Key_1, "1", release=True)
        assert canvas.camera.state() != cam0
        assert np.allclose(scene.active.position, pos0) and len(scene._undo) == undo0
        start = _px(canvas, (0.0, 0.0, -100.0))
        _drag(canvas, start, start + (60.0, 0.0))
        assert not np.allclose(scene.active.position, pos0)
    finally:
        win.close()
        win.deleteLater()
        _settle(app)


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
