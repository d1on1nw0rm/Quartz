from __future__ import annotations

import math
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TMP = tempfile.mkdtemp(prefix="quartz-controls-viewport-")
os.environ["QUARTZ_PREFS_DIR"] = _TMP

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QMouseEvent, QShortcut, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

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
KEY_1, KEY_2, KEY_3 = int(Qt.Key.Key_1), int(Qt.Key.Key_2), int(Qt.Key.Key_3)
X = np.array([1.0, 0.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])

_LIVE: list[QWidget] = []
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


def _user(base: str, cursor: dict | None = None, modifiers: dict | None = None) -> str:
    controls = _controls()
    pid = controls.duplicate(base)
    for key, value in (cursor or {}).items():
        controls.set_cursor(pid, key, value)
    for role, mod in (modifiers or {}).items():
        controls.set_modifier(pid, role, mod)
    return pid


def _make(mode: str = "model"):
    _app()
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
    _settle()
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


def _release(widget, pos, button=LEFT, mods=NO_MOD) -> None:
    _mouse(widget, QEvent.Type.MouseButtonRelease, pos, button, NO_BUTTON, mods)


def _click(widget, pos, mods=NO_MOD, button=LEFT) -> None:
    _press(widget, pos, button, mods)
    _release(widget, pos, button, mods)


def _double(widget, pos, button=LEFT, mods=NO_MOD) -> None:
    _press(widget, pos, button, mods)
    _release(widget, pos, button, mods)
    _mouse(widget, QEvent.Type.MouseButtonDblClick, pos, button, button, mods)
    _release(widget, pos, button, mods)


def _drag(widget, start, end, mods=NO_MOD, button=LEFT, steps: int = 10, move_mods=None,
          release: bool = True) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    move_mods = mods if move_mods is None else move_mods
    _press(widget, start, button, mods)
    for k in range(1, steps + 1):
        _mouse(widget, QEvent.Type.MouseMove, start + (end - start) * k / steps, NO_BUTTON, button, move_mods)
    if release:
        _release(widget, end, button, move_mods)


def _wheel(widget: QWidget, pos, notches: float) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    ev = QWheelEvent(local, QPointF(widget.mapToGlobal(local)), QPoint(0, 0), QPoint(0, int(120 * notches)),
                     NO_BUTTON, NO_MOD, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def _key(widget: QWidget, key: int, text: str = "", mods=NO_MOD, release: bool = False) -> None:
    kind = QEvent.Type.KeyRelease if release else QEvent.Type.KeyPress
    QApplication.sendEvent(widget, QKeyEvent(kind, Qt.Key(key), mods, text))


def _key_code(text: str) -> int:
    return int(QKeySequence(text)[0].key())


def _centre(canvas) -> np.ndarray:
    c = canvas.inner_rect().center()
    return np.array([c.x(), c.y()])


def _px(canvas, world) -> np.ndarray:
    return canvas.project_world([world])[0]


def _visible_points(canvas, scene) -> list[tuple[int, np.ndarray]]:
    xy = canvas.project_world(scene.active.world_points())
    out = []
    for i, p in enumerate(xy):
        kind, item = canvas.pick(p)
        if kind == "point" and item == i:
            out.append((i, p))
    return out


def _nav_kind(canvas, scene, button, mods=NO_MOD, held=()) -> str | None:
    for code in held:
        _key(canvas, code, chr(code))
    cam0 = canvas.camera.copy()
    sel0 = set(scene.selected_points), set(scene.selected_polygons)
    start = _centre(canvas) + (-180.0, 150.0)
    _press(canvas, start, button, mods)
    nav = canvas._nav
    mode = nav.mode if nav is not None else None
    for k in range(1, 9):
        _mouse(canvas, QEvent.Type.MouseMove, start + (8.0 * k, -5.0 * k), NO_BUTTON, button, mods)
    _release(canvas, start + (64.0, -40.0), button, mods)
    for code in held:
        _key(canvas, code, chr(code), release=True)
    assert canvas._nav is None
    assert (set(scene.selected_points), set(scene.selected_polygons)) == sel0
    cam = canvas.camera
    if mode == "orbit":
        assert abs(cam.heading - cam0.heading) > 1e-6
    elif mode == "pan":
        assert abs(cam.heading - cam0.heading) < 1e-9 and abs(cam.pitch - cam0.pitch) < 1e-9
        assert not np.allclose(cam.target, cam0.target)
    elif mode == "zoom":
        assert abs(cam.heading - cam0.heading) < 1e-9
        assert abs(cam.distance - cam0.distance) > 1e-6
    canvas.camera = cam0
    canvas.update()
    return mode


CLASSIC_PRESSES = [
    ("left", {"alt"}, set(), False, "orbit"),
    ("left", {"alt", "shift"}, set(), False, "orbit"),
    ("left", {"alt", "ctrl"}, set(), False, "orbit"),
    ("left", {"alt", "shift", "ctrl"}, set(), False, "orbit"),
    ("middle", {"alt"}, set(), False, "pan"),
    ("middle", {"alt", "shift"}, set(), False, "pan"),
    ("right", {"alt"}, set(), False, "dolly"),
    ("left", set(), {KEY_1}, False, "pan"),
    ("left", set(), {KEY_2}, False, "dolly"),
    ("left", set(), {KEY_3}, False, "orbit"),
    ("left", set(), {KEY_1, KEY_3}, False, "orbit"),
    ("left", set(), {KEY_1, KEY_2}, False, "dolly"),
    ("left", {"shift"}, {KEY_1}, False, "pan"),
    ("left", {"ctrl"}, {KEY_2}, False, "dolly"),
    ("left", {"alt"}, {KEY_1}, False, "orbit"),
    ("left", {"alt"}, {KEY_3}, False, "orbit"),
    ("middle", set(), set(), False, "orbit"),
    ("middle", {"shift"}, set(), False, "orbit"),
    ("middle", {"ctrl"}, set(), False, "orbit"),
    ("middle", set(), {KEY_1}, False, "orbit"),
    ("left", set(), set(), False, "select"),
    ("left", {"shift"}, set(), False, "add"),
    ("left", {"ctrl"}, set(), False, "remove"),
    ("left", {"ctrl", "shift"}, set(), False, "remove"),
    ("right", set(), set(), False, "context"),
    ("right", {"shift"}, set(), False, "add"),
    ("right", {"ctrl"}, set(), False, "remove"),
    ("right", {"shift", "alt"}, set(), False, "dolly"),
    ("right", {"shift"}, {KEY_1}, False, None),
    ("right", set(), {KEY_1}, False, None),
    ("right", set(), {KEY_3}, False, None),
    ("middle", set(), set(), True, "view.frame_default"),
    ("middle", {"shift"}, set(), True, "view.frame_default"),
    ("middle", {"ctrl"}, set(), True, "view.frame_default"),
    ("middle", {"shift", "ctrl"}, set(), True, "view.frame_default"),
    ("middle", {"alt"}, set(), True, "pan"),
    ("left", set(), set(), True, "select"),
    ("left", {"shift"}, set(), True, "add"),
    ("right", set(), set(), True, "context"),
]

STANDARD_PRESSES = [
    ("left", {"alt"}, set(), False, "orbit"),
    ("left", {"alt", "shift"}, set(), False, "orbit"),
    ("middle", {"alt"}, set(), False, "pan"),
    ("right", {"alt"}, set(), False, "dolly"),
    ("middle", {"shift"}, set(), False, "pan"),
    ("middle", {"ctrl"}, set(), False, "dolly"),
    ("middle", set(), set(), False, "orbit"),
    ("left", set(), set(), False, "select"),
    ("left", {"shift"}, set(), False, "add"),
    ("left", {"ctrl"}, set(), False, "remove"),
    ("right", set(), set(), False, "context"),
    ("left", set(), {KEY_1}, False, "select"),
    ("left", set(), set(), True, "tool.loop_selection"),
    ("left", {"shift"}, set(), True, "add"),
    ("middle", set(), set(), True, "orbit"),
]


def _check_presses(rows) -> None:
    controls = _controls()
    for button, mods, held, double, want in rows:
        got = controls.match_press(button, set(mods), set(held), double)
        result = None if got is None else (got.get("op") or got.get("action"))
        assert result == want, (controls.active_id(), button, sorted(mods), sorted(held), double, got)


def test_classic_mouse_rows_through_match_press() -> None:
    _app()
    _fresh()
    assert _controls().active_id() == "classic"
    _check_presses(CLASSIC_PRESSES)


def test_classic_navigation_through_real_events() -> None:
    _fresh()
    canvas, scene = _make()
    assert canvas.nav_pivot == "Cursor"
    assert _nav_kind(canvas, scene, LEFT, ALT) == "orbit"
    assert _nav_kind(canvas, scene, LEFT, ALT | SHIFT) == "orbit"
    assert _nav_kind(canvas, scene, MIDDLE, ALT) == "pan"
    assert _nav_kind(canvas, scene, RIGHT, ALT) == "zoom"
    assert _nav_kind(canvas, scene, LEFT, held=(KEY_1,)) == "pan"
    assert _nav_kind(canvas, scene, LEFT, held=(KEY_2,)) == "zoom"
    assert _nav_kind(canvas, scene, LEFT, held=(KEY_3,)) == "orbit"
    assert _nav_kind(canvas, scene, LEFT, held=(KEY_1, KEY_3)) == "orbit"
    assert _nav_kind(canvas, scene, LEFT, SHIFT, held=(KEY_1,)) == "pan"
    assert _nav_kind(canvas, scene, MIDDLE) == "orbit"
    assert _nav_kind(canvas, scene, MIDDLE, SHIFT) == "orbit"
    assert _nav_kind(canvas, scene, MIDDLE, CTRL) == "orbit"
    start = _centre(canvas)
    _press(canvas, start, LEFT, ALT)
    assert canvas._nav is not None and canvas._nav.mode == "orbit"
    _press(canvas, start, MIDDLE)
    assert canvas._nav.mode == "orbit"
    _release(canvas, start, LEFT, ALT)
    assert canvas._nav is None


def test_classic_selection_presses_through_real_events() -> None:
    _fresh()
    canvas, scene = _make("points")
    scene.set_tool("select")
    pts = _visible_points(canvas, scene)
    assert len(pts) >= 3, pts
    (a, pa), (b, pb), (c, pc) = pts[:3]
    _click(canvas, pa)
    assert scene.selected_points == {a}
    _click(canvas, pb, SHIFT)
    assert scene.selected_points == {a, b}
    _click(canvas, pc, SHIFT)
    assert scene.selected_points == {a, b, c}
    _click(canvas, pa, CTRL)
    assert scene.selected_points == {b, c}
    _click(canvas, pb, CTRL | SHIFT)
    assert scene.selected_points == {c}
    _click(canvas, pa)
    assert scene.selected_points == {a}
    film = canvas.film_rect()
    empty = (film.left() + film.width() * 0.1, film.top() + film.height() * 0.9)
    _click(canvas, empty, SHIFT)
    assert scene.selected_points == {a}
    _click(canvas, empty)
    assert scene.selected_points == set()


def test_classic_context_double_click_and_wheel_through_real_events() -> None:
    _fresh()
    canvas, scene = _make()
    opened: list = []
    canvas.open_context_menu = lambda pos, global_pos=None: opened.append(QPointF(pos))
    spot = _centre(canvas) + (200.0, 200.0)
    _click(canvas, spot, button=RIGHT)
    assert len(opened) == 1
    _press(canvas, spot, RIGHT)
    _mouse(canvas, QEvent.Type.MouseMove, spot + (3.0, 2.0), NO_BUTTON, RIGHT)
    _release(canvas, spot + (3.0, 2.0), RIGHT)
    assert len(opened) == 2
    _press(canvas, spot, RIGHT)
    _mouse(canvas, QEvent.Type.MouseMove, spot + (4.0, 0.0), NO_BUTTON, RIGHT)
    _release(canvas, spot + (4.0, 0.0), RIGHT)
    assert len(opened) == 2
    _key(canvas, KEY_1, "1")
    _click(canvas, spot, button=RIGHT)
    _key(canvas, KEY_1, "1", release=True)
    assert len(opened) == 2
    _drag(canvas, spot, spot + (40.0, 0.0), ALT, RIGHT)
    assert len(opened) == 2
    default = canvas._preset_camera("Perspective", default=True).state()
    canvas.begin_navigation("orbit")
    canvas.navigate("orbit", 40.0, 10.0)
    canvas.end_navigation()
    assert canvas.camera.state() != default
    _double(canvas, spot, MIDDLE)
    assert canvas.camera.state() == default and canvas._nav is None
    canvas.begin_navigation("orbit")
    canvas.navigate("orbit", 40.0, 10.0)
    canvas.end_navigation()
    _double(canvas, spot, MIDDLE, SHIFT | CTRL)
    assert canvas.camera.state() == default
    canvas.begin_navigation("orbit")
    canvas.navigate("orbit", 40.0, 10.0)
    canvas.end_navigation()
    moved = canvas.camera.state()
    _double(canvas, spot, MIDDLE, ALT)
    assert canvas.camera.state() == moved and canvas._nav is None
    d0 = canvas.camera.distance
    _wheel(canvas, _centre(canvas), 1)
    assert canvas.camera.distance < d0


def test_classic_pen_and_drag_cancel_rows() -> None:
    _fresh()
    canvas, scene = _make("points")
    scene.set_tool("move")
    obj = scene.active
    pts = _visible_points(canvas, scene)
    i, p = pts[0]
    _click(canvas, p)
    assert scene.selected_points == {i}
    before = obj.world_points().copy()
    _drag(canvas, p, p + (60.0, 0.0), release=False)
    assert canvas._drag is not None and not np.allclose(obj.world_points(), before)
    _press(canvas, p + (60.0, 0.0), RIGHT)
    assert canvas._drag is None and np.allclose(obj.world_points(), before)
    _release(canvas, p + (60.0, 0.0), LEFT)
    scene.set_tool("pen")
    film = canvas.film_rect()
    empty = (film.left() + film.width() * 0.1, film.top() + film.height() * 0.9)
    _press(canvas, empty)
    assert canvas._pen_press is not None
    _release(canvas, empty)
    assert canvas._pen_press is None
    _press(canvas, p, LEFT, SHIFT)
    assert canvas._pen_press is None
    _release(canvas, p, LEFT, SHIFT)


def test_standard_mouse_through_real_events() -> None:
    _fresh()
    canvas, scene = _make()
    _controls().select("standard")
    try:
        _check_presses(STANDARD_PRESSES)
        assert canvas.nav_pivot == "Center"
        assert _nav_kind(canvas, scene, MIDDLE, SHIFT) == "pan"
        assert _nav_kind(canvas, scene, MIDDLE, CTRL) == "zoom"
        assert _nav_kind(canvas, scene, MIDDLE) == "orbit"
        assert _nav_kind(canvas, scene, LEFT, ALT) == "orbit"
        assert _nav_kind(canvas, scene, LEFT, ALT | SHIFT) == "orbit"
        assert _nav_kind(canvas, scene, MIDDLE, ALT) == "pan"
        assert _nav_kind(canvas, scene, RIGHT, ALT) == "zoom"
        assert _nav_kind(canvas, scene, LEFT, held=(KEY_1,)) is None
    finally:
        _fresh()
    assert canvas.nav_pivot == "Cursor"


def test_cursor_orbit_style_free_passes_the_pitch_limit() -> None:
    from quartz_studio.widgets.viewport import PITCH_LIMIT, OrbitCamera

    cam = OrbitCamera()
    cam.orbit(0.0, 400.0)
    assert abs(cam.pitch - PITCH_LIMIT) < 1e-9
    cam = OrbitCamera()
    cam.orbit(0.0, 400.0, clamp=False)
    assert cam.pitch > PITCH_LIMIT + 1.0, cam.pitch
    _fresh()
    canvas, _scene = _make()
    try:
        canvas.begin_navigation("orbit")
        canvas.navigate("orbit", 0.0, 300.0)
        canvas.end_navigation()
        assert canvas.camera.pitch <= PITCH_LIMIT + 1e-9
        canvas.reset_camera()
        _user("classic", {"orbit_style": "free"})
        canvas.begin_navigation("orbit")
        canvas.navigate("orbit", 0.0, 300.0)
        canvas.end_navigation()
        assert canvas.camera.pitch > PITCH_LIMIT + 1.0, canvas.camera.pitch
    finally:
        _fresh()


def test_cursor_orbit_speed_and_inversion() -> None:
    _fresh()
    canvas, _scene = _make()
    try:
        def turn(dx: float, dy: float) -> tuple[float, float]:
            canvas.reset_camera()
            h0, p0 = canvas.camera.heading, canvas.camera.pitch
            canvas.begin_navigation("orbit")
            canvas.navigate("orbit", dx, dy)
            canvas.end_navigation()
            return canvas.camera.heading - h0, canvas.camera.pitch - p0

        dh, dp = turn(10.0, 10.0)
        assert abs(dh + 3.0) < 1e-6 and abs(dp - 3.0) < 1e-6, (dh, dp)
        pid = _user("classic", {"invert_orbit_x": True})
        ih, ip = turn(10.0, 10.0)
        assert abs(ih - (-dh)) < 1e-6 and abs(ip - dp) < 1e-6, (ih, ip)
        _controls().set_cursor(pid, "invert_orbit_y", True)
        ih, ip = turn(10.0, 10.0)
        assert abs(ih - (-dh)) < 1e-6 and abs(ip - (-dp)) < 1e-6, (ih, ip)
        _controls().reset_cursor(pid, "invert_orbit_x")
        _controls().reset_cursor(pid, "invert_orbit_y")
        _controls().set_cursor(pid, "orbit_speed", 0.6)
        fh, fp = turn(10.0, 10.0)
        assert abs(fh - 2.0 * dh) < 1e-6 and abs(fp - 2.0 * dp) < 1e-6, (fh, fp)
    finally:
        _fresh()


def test_cursor_invert_pan_and_dolly_speed() -> None:
    _fresh()
    canvas, _scene = _make()
    try:
        start = _centre(canvas) + (-100.0, 80.0)
        end = start + (120.0, 0.0)
        right = canvas.camera.basis()[2]
        t0 = np.array(canvas.camera.target, float)
        _drag(canvas, start, end, ALT, MIDDLE)
        plain = float((np.asarray(canvas.camera.target) - t0) @ right)
        assert plain < -1.0, plain
        canvas.reset_camera()
        _user("classic", {"invert_pan": True})
        t0 = np.array(canvas.camera.target, float)
        _drag(canvas, start, end, ALT, MIDDLE)
        inverted = float((np.asarray(canvas.camera.target) - t0) @ right)
        assert inverted > 1.0, inverted
        assert abs(inverted + plain) < 0.05 * abs(plain), (plain, inverted)
        canvas.reset_camera()
        d0 = canvas.camera.distance
        canvas.begin_navigation("zoom")
        canvas.navigate("zoom", 20.0, 0.0)
        canvas.end_navigation()
        slow = canvas.camera.distance / d0
        canvas.reset_camera()
        _controls().set_cursor(_controls().active_id(), "dolly_speed", 0.01)
        canvas.begin_navigation("zoom")
        canvas.navigate("zoom", 20.0, 0.0)
        canvas.end_navigation()
        fast = canvas.camera.distance / d0
        assert abs(math.log(fast) - 2.0 * math.log(slow)) < 1e-6, (slow, fast)
    finally:
        _fresh()


def test_cursor_wheel_settings() -> None:
    _fresh()
    canvas, _scene = _make()
    try:
        off = _px(canvas, (100.0, 100.0, 100.0))
        t0 = np.array(canvas.camera.target, float)
        d0 = canvas.camera.distance
        _wheel(canvas, off, 1)
        assert not np.allclose(canvas.camera.target, t0)
        assert canvas.camera.distance < d0
        canvas.reset_camera()
        pid = _user("classic", {"zoom_to_cursor": False})
        t0 = np.array(canvas.camera.target, float)
        _wheel(canvas, off, 1)
        assert np.allclose(canvas.camera.target, t0, atol=1e-6), (canvas.camera.target, t0)
        assert abs(canvas.camera.distance - d0 * 0.88) < 1e-6
        canvas.reset_camera()
        _controls().set_cursor(pid, "wheel_step", 0.5)
        canvas._wheel_merge_until = 0.0
        _wheel(canvas, off, 1)
        assert abs(canvas.camera.distance - d0 * 0.5) < 1e-6, canvas.camera.distance
        canvas.reset_camera()
        _controls().set_cursor(pid, "wheel_invert", True)
        canvas._wheel_merge_until = 0.0
        _wheel(canvas, off, 1)
        assert abs(canvas.camera.distance - d0 / 0.5) < 1e-6, canvas.camera.distance
        canvas.reset_camera()
        _wheel(canvas, off, -1)
        assert abs(canvas.camera.distance - d0 * 0.5) < 1e-6, canvas.camera.distance
    finally:
        _fresh()


def test_cursor_drag_threshold_and_click_tolerance() -> None:
    from quartz_studio.widgets.viewport import ViewportCanvas

    _fresh()
    canvas, scene = _make("points")
    try:
        scene.set_tool("move")
        obj = scene.active
        i, p = _visible_points(canvas, scene)[0]
        _click(canvas, p)
        assert scene.selected_points == {i}
        before = obj.world_points().copy()
        local = obj.mesh.points.copy()

        def restore() -> None:
            obj.mesh.points[:] = local
            scene.changed.emit()

        _drag(canvas, p, p + (3.0, 3.0), steps=2)
        assert not np.allclose(obj.world_points(), before)
        restore()
        assert ViewportCanvas.DRAG_THRESHOLD == 3 and ViewportCanvas.CONTEXT_DRAG_PX == 4
        pid = _user("classic", {"drag_threshold": 8})
        _drag(canvas, p, p + (3.0, 3.0), steps=2)
        assert np.allclose(obj.world_points(), before)
        _drag(canvas, p, p + (6.0, 4.0), steps=2)
        assert not np.allclose(obj.world_points(), before)
        restore()
        opened: list = []
        canvas.open_context_menu = lambda pos, global_pos=None: opened.append(pos)
        spot = _centre(canvas) + (220.0, 200.0)
        _controls().set_cursor(pid, "click_tolerance", 10)
        _drag(canvas, spot, spot + (8.0, 0.0), button=RIGHT, steps=2)
        assert len(opened) == 1
        _drag(canvas, spot, spot + (12.0, 0.0), button=RIGHT, steps=2)
        assert len(opened) == 1
    finally:
        _fresh()


def test_cursor_orbit_pivot_follows_the_selected_profile() -> None:
    _fresh()
    canvas, _scene = _make()
    try:
        assert canvas.nav_pivot == "Cursor"
        pivots: list[str] = []
        canvas.navPivotChanged.connect(pivots.append)
        _user("classic", {"orbit_pivot": "Object"})
        assert canvas.nav_pivot == "Object"
        _controls().select("standard")
        assert canvas.nav_pivot == "Center"
        _controls().select("classic")
        assert canvas.nav_pivot == "Cursor"
        assert pivots == ["Object", "Center", "Cursor"], pivots
        canvas.set_nav_pivot("Camera")
        assert canvas.nav_pivot == "Camera"
    finally:
        _fresh()


def test_modifier_role_snap_on_ctrl() -> None:
    _fresh()
    canvas, scene = _make()
    try:
        scene.set_tool("rotate")
        _user("classic", modifiers={"snap": "ctrl"})
        centre = scene.selection_center()
        start = canvas.gizmo_rings()["y"][6]
        end = _plane_point(canvas, centre, Z, X, 45.0 + 37.0)
        _drag(canvas, start, end, move_mods=CTRL)
        assert abs(scene.active.rotation[1] - 35.0) < 1e-6, scene.active.rotation
        scene.undo()
        assert np.allclose(scene.active.rotation, 0.0)
        start = canvas.gizmo_rings()["y"][6]
        _drag(canvas, start, end, move_mods=SHIFT)
        rot = scene.active.rotation[1]
        assert abs(rot - 35.0) > 0.5 and abs(rot - 37.0) < 1.0, scene.active.rotation
    finally:
        _fresh()


def test_modal_keys_cancel_and_confirm() -> None:
    _fresh()
    canvas, scene = _make("points")
    scene.set_tool("move")
    obj = scene.active
    i, p = _visible_points(canvas, scene)[0]
    _click(canvas, p)
    before = obj.world_points().copy()
    _drag(canvas, p, p + (60.0, 0.0), release=False)
    assert canvas._drag is not None
    _key(canvas, int(Qt.Key.Key_Escape))
    assert canvas._drag is None and np.allclose(obj.world_points(), before)
    _release(canvas, p + (60.0, 0.0))


def _plane_point(canvas, centre, u, v, deg: float, radius: float = 60.0) -> np.ndarray:
    t = math.radians(deg)
    world = np.asarray(centre, float) + radius * (math.cos(t) * np.asarray(u, float)
                                                  + math.sin(t) * np.asarray(v, float))
    return canvas.project_world([world])[0]


def _ensure_controls(win) -> None:
    if getattr(win, "controls_filter", None) is not None:
        return
    for sc in win.findChildren(QShortcut):
        sc.setEnabled(False)
        sc.deleteLater()
    _controls().install(win)


def _window():
    if "window" in _STATE:
        return _STATE["window"]
    app = _app()
    _fresh()
    from quartz_studio.main_window import MainWindow
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import reset_scene

    while _LIVE:
        old = _LIVE.pop()
        old.close()
        old.deleteLater()
    reset_scene()
    mi.prepare()
    win = MainWindow()
    _ensure_controls(win)
    mi.install(win)
    win.resize(1500, 900)
    win.show()
    for _ in range(6):
        app.processEvents()
    _STATE["window"] = win
    return win


def _window_setup(mode: str):
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import Mesh, get_scene

    win = _window()
    scene = get_scene()
    ctl = mi.controller()
    ctl.activate(None)
    scene.set_tool("move")
    scene.set_mode("model")
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_object("Cube", Mesh.cube(200.0))
    scene._undo.clear()
    scene._redo.clear()
    if mode != "model":
        scene.set_mode(mode)
    canvas = win.viewport.canvas
    canvas.reset_camera()
    canvas.setFocus()
    _settle()
    return win, scene, canvas


def test_standard_left_double_click_runs_loop_selection() -> None:
    controls = _controls()
    win, scene, canvas = _window_setup("polygons")
    ran: list[str] = []
    original = controls.run

    def spy(action_id: str) -> bool:
        ran.append(action_id)
        return original(action_id)

    controls.select("standard")
    controls.run = spy
    try:
        top = _px(canvas, (0.0, 100.0, 0.0))
        _click(canvas, top)
        assert scene.selected_polygons == {4}, scene.selected_polygons
        _double(canvas, top)
        assert "tool.loop_selection" in ran, ran
        assert len(scene.selected_polygons) == 4 and 4 in scene.selected_polygons, scene.selected_polygons
        win, scene, canvas = _window_setup("model")
        ran.clear()
        scene.select_object(False)
        _double(canvas, _px(canvas, (0.0, 0.0, 0.0)))
        assert "tool.loop_selection" not in ran, ran
        assert scene.mode == "model"
        assert scene.active is not None and scene.active.name == "Cube"
    finally:
        controls.run = original
        _fresh()


def test_tool_filter_yields_to_every_navigation_gesture() -> None:
    from quartz_studio.modeling import install as mi

    controls = _controls()
    names = {"left": LEFT, "middle": MIDDLE, "right": RIGHT}
    flags = {"shift": SHIFT, "ctrl": CTRL, "alt": ALT}
    try:
        for profile in ("classic", "standard"):
            controls.select(profile)
            win, scene, canvas = _window_setup("polygons")
            scene.select_components([4])
            mi.activate_tool("extrude")
            _settle()
            tool_filter = win.modeling_filter
            assert scene.tool == "extrude"
            gestures = [g for g in controls.active().mouse
                        if not g.get("double") and g.get("op") in ("orbit", "pan", "dolly")]
            assert gestures, profile
            for g in gestures:
                mods = NO_MOD
                for m in g.get("mods") or ():
                    mods |= flags[m]
                held = (_key_code(g["key"]),) if g.get("key") else ()
                for code in held:
                    _key(canvas, code, g["key"])
                start = _centre(canvas) + (-200.0, 160.0)
                _press(canvas, start, names[g["button"]], mods)
                assert canvas._nav is not None, (profile, g)
                assert tool_filter._press is None, (profile, g)
                _release(canvas, start, names[g["button"]], mods)
                for code in held:
                    _key(canvas, code, g["key"], release=True)
                assert canvas._nav is None
            top = _px(canvas, (0.0, 100.0, 0.0))
            _press(canvas, top)
            assert canvas._nav is None and tool_filter._press is not None, profile
            _release(canvas, top)
            mi.controller().activate(None)
            scene.set_tool("move")
    finally:
        _fresh()


def test_view_menu_shows_the_active_profile_bindings() -> None:
    win, scene, canvas = _window_setup("model")
    controls = _controls()
    bar = win.viewport.menu_bar

    def texts() -> dict[str, str]:
        return {t: bar.menu_action("View", t).property("qs_shortcut") for t, _a in bar.VIEW_ACTION_IDS}

    try:
        assert texts() == {"Undo View": "Ctrl+Shift+Z", "Redo View": "Ctrl+Shift+Y",
                           "Frame Default": "Shift+H", "Frame Geometry": "H",
                           "Frame Selected Elements": "S", "Frame Selected Objects": "O"}, texts()
        controls.select("standard")
        got = texts()
        assert got["Frame Default"] == "Home" and got["Frame Geometry"] == "A", got
        assert got["Frame Selected Elements"] == "F" and got["Frame Selected Objects"] == "Shift+F", got
        assert bar.menu_action("View", "Frame Geometry").text() == "Frame Geometry\tA"
        controls.select("classic")
        assert texts()["Frame Geometry"] == "H"
    finally:
        _fresh()


def test_canvas_keys_follow_the_profile_with_and_without_a_window() -> None:
    controls = _controls()
    win, scene, canvas = _window_setup("model")
    try:
        _key(canvas, int(Qt.Key.Key_R), "r")
        assert scene.tool == "rotate"
        controls.select("standard")
        _key(canvas, int(Qt.Key.Key_W), "w")
        assert scene.tool == "move"
        _key(canvas, int(Qt.Key.Key_E), "e")
        assert scene.tool == "rotate"
        _key(canvas, int(Qt.Key.Key_Q), "q")
        assert scene.tool == "select"
        default = canvas._preset_camera("Perspective", default=True).state()
        canvas.begin_navigation("orbit")
        canvas.navigate("orbit", 40.0, 10.0)
        canvas.end_navigation()
        assert canvas.camera.state() != default
        _key(canvas, int(Qt.Key.Key_Home))
        assert canvas.camera.state() == default
        _key(canvas, int(Qt.Key.Key_7), "7", Qt.KeyboardModifier.KeypadModifier)
        assert canvas.view_name == "Top", canvas.view_name
    finally:
        _fresh()
    canvas2, scene2 = _make()
    controls.select("standard")
    try:
        _key(canvas2, int(Qt.Key.Key_E), "e")
        assert scene2.tool == "rotate"
        _key(canvas2, int(Qt.Key.Key_W), "w")
        assert scene2.tool == "move"
        _key(canvas2, int(Qt.Key.Key_1), "1", Qt.KeyboardModifier.KeypadModifier)
        assert canvas2.view_name == "Front", canvas2.view_name
        assert KEY_1 not in canvas2._held_keys
    finally:
        _fresh()
    _key(canvas2, int(Qt.Key.Key_E), "e")
    assert scene2.tool == "move"
    _key(canvas2, int(Qt.Key.Key_F2))
    assert canvas2.view_name == "Top"


def _cleanup() -> None:
    win = _STATE.pop("window", None)
    if win is not None:
        win.close()
        win.deleteLater()
    while _LIVE:
        old = _LIVE.pop()
        old.close()
        old.deleteLater()
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
