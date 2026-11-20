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
from PySide6.QtGui import QColor, QGuiApplication, QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio import theme
from quartz_studio.app import create_app

VIEW_SIZE = (1000, 640)
LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton
NO_MOD = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier

_LIVE: list[QWidget] = []


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(app: QApplication, passes: int = 4) -> None:
    for _ in range(passes):
        app.processEvents()


def _make(mode: str | None = None, tool: str | None = None):
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
    if tool is not None:
        scene.set_tool(tool)
    if mode is not None:
        scene.set_mode(mode)
    return view.canvas, scene



def _pt(pos) -> QPoint:
    return QPoint(int(round(float(pos[0]))), int(round(float(pos[1]))))


def _click(widget: QWidget, pos, mods=NO_MOD) -> None:
    QTest.mouseClick(widget, LEFT, mods, _pt(pos))


def _press(widget: QWidget, pos, mods=NO_MOD) -> None:
    QTest.mousePress(widget, LEFT, mods, _pt(pos))


def _move_to(widget: QWidget, start, end, steps: int = 8) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    for k in range(1, steps + 1):
        QTest.mouseMove(widget, _pt(start + (end - start) * k / steps))
    assert QGuiApplication.mouseButtons() == LEFT


def _release(widget: QWidget, pos) -> None:
    QTest.mouseRelease(widget, LEFT, NO_MOD, _pt(pos))


def _move_with_ctrl(widget: QWidget, pos) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    ev = QMouseEvent(QEvent.Type.MouseMove, local, QPointF(widget.mapToGlobal(local)),
                     Qt.MouseButton.NoButton, LEFT, CTRL)
    QApplication.sendEvent(widget, ev)


def _hover(widget: QWidget, pos) -> None:
    QTest.mouseMove(widget, _pt(pos))



def _image(canvas) -> QImage:
    return canvas.grab().toImage()


def _rgb(img: QImage, pos) -> tuple[int, int, int]:
    c = img.pixelColor(int(round(float(pos[0]))), int(round(float(pos[1]))))
    return c.red(), c.green(), c.blue()


def _any_pixel(img: QImage, pos, test, radius: int = 2) -> bool:
    x0, y0 = int(round(float(pos[0]))), int(round(float(pos[1])))
    return any(test(_rgb(img, (x0 + dx, y0 + dy)))
               for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1))


def _channels(token: str) -> tuple[int, int, int]:
    c = QColor(token)
    return c.red(), c.green(), c.blue()


def _distance(rgb, token: str) -> int:
    return sum(abs(a - b) for a, b in zip(rgb, _channels(token)))


def _is_guide(rgb) -> bool:
    ar, ag, ab = _channels(theme.ACCENT)
    r, g, b = rgb
    return g > r + (ag - ar) // 2 and b > r + (ab - ar) // 2 and g > 150


def _is_hover(rgb) -> bool:
    return _distance(rgb, theme.GIZMO_HOVER) <= 40


LIGHT_ABOVE_BACKGROUND = 110


def _is_light(rgb) -> bool:
    from PySide6.QtGui import QColor

    from quartz_studio import theme

    floor = max(QColor(c).value() for c in (theme.BG_VIEWPORT_TOP, theme.BG_VIEWPORT_BOTTOM))
    return min(rgb) > floor + LIGHT_ABOVE_BACKGROUND


def _is_line(rgb) -> bool:
    return min(rgb) > 140 and max(rgb) - min(rgb) < 30


def _is_citrine(rgb) -> bool:
    return _distance(rgb, theme.SELECT_FRONT) <= 120 and rgb[0] > rgb[2] + 80


def _is_point(rgb) -> bool:
    return _distance(rgb, theme.POINT_FILL) <= 30


def _image_after_leave(canvas) -> QImage:
    QApplication.sendEvent(canvas, QEvent(QEvent.Type.Leave))
    return _image(canvas)


def _px(canvas, world) -> np.ndarray:
    return canvas.project_world(np.atleast_2d(np.asarray(world, float)))[0]


def _points_px(canvas, scene) -> np.ndarray:
    return canvas.project_world(scene.active.world_points())


def _pentagon(canvas, radius: float = 60.0) -> list[np.ndarray]:
    film = canvas.film_rect()
    cx, cy = film.left() + film.width() * 0.25, film.top() + film.height() * 0.68
    return [np.array([cx + radius * math.sin(a), cy - radius * math.cos(a)])
            for a in np.radians([0.0, 72.0, 144.0, 216.0, 288.0])]


def _line_spots(canvas) -> list[np.ndarray]:
    film = canvas.film_rect()
    y = film.top() + film.height() * 0.8
    return [np.array([film.left() + film.width() * f, y]) for f in (0.66, 0.76, 0.86)]


def _fwd(canvas) -> np.ndarray:
    return canvas.view_direction()


def _arrow_start(canvas, axis: str) -> np.ndarray:
    (sx, sy), (ex, ey) = canvas.gizmo_handles()[axis]
    return np.array([sx, sy]) + (np.array([ex, ey]) - np.array([sx, sy])) * 0.6



def test_pen_hud_cursor_and_mode() -> None:
    canvas, scene = _make(tool="pen")
    assert scene.mode == "points"
    assert canvas.hud_text == "Polygon Pen"
    assert canvas.cursor().shape() == Qt.CursorShape.CrossCursor
    scene.set_tool("line_pen")
    assert canvas.hud_text == "Pen"
    _image(canvas)
    scene.set_tool("move")
    assert canvas.hud_text == "Move" and canvas.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_polygon_pen_point_line_tri_quad_ngon() -> None:
    canvas, scene = _make(tool="pen")
    mesh = scene.active.mesh
    n0, p0, e0 = len(mesh.points), len(mesh.polygons), len(mesh.edges)
    spots = _pentagon(canvas)
    depth0 = len(scene._undo)
    _click(canvas, spots[0])
    assert len(mesh.points) == n0 + 1 and len(mesh.edges) == e0 and len(mesh.polygons) == p0
    assert scene.pen_active() and scene.selected_points == {n0}
    _click(canvas, spots[1])
    assert len(mesh.points) == n0 + 2 and len(mesh.edges) == e0 + 1 and len(mesh.polygons) == p0
    assert (n0, n0 + 1) in mesh.loose_edges
    _click(canvas, spots[2])
    assert len(mesh.polygons) == p0 + 1 and len(mesh.polygons[-1]) == 3
    assert not mesh.loose_edges
    _click(canvas, spots[3])
    assert len(mesh.polygons) == p0 + 1 and len(mesh.polygons[-1]) == 4
    _click(canvas, spots[4])
    assert len(mesh.polygons) == p0 + 1 and len(mesh.polygons[-1]) == 5
    assert len(scene._undo) == depth0 + 5
    k = len(mesh.polygons) - 1
    world = scene.active.world_points()
    normal = mesh.polygon_normals(world)[k]
    assert float(normal @ -_fwd(canvas)) > 0.99
    assert np.allclose(canvas.project_world(world[n0:n0 + 5]), spots, atol=0.75)
    guides = mesh.ngon_guides(k, world)
    assert guides
    img = _image(canvas)
    for a, b in guides:
        mid = canvas.project_world(world[[a, b]]).mean(axis=0)
        assert _any_pixel(img, mid, _is_guide), (a, b, _rgb(img, mid))
    film = canvas.film_rect()
    _click(canvas, (film.left() + film.width() * 0.25 - 75.0, film.top() + film.height() * 0.68 - 30.0))
    assert len(mesh.polygons[k]) == 6 and len(mesh.ngon_guides(k, scene.active.world_points())) >= 1


def test_polygon_pen_closes_on_first_point() -> None:
    canvas, scene = _make(tool="pen")
    mesh = scene.active.mesh
    spots = _pentagon(canvas)
    for s in spots[:4]:
        _click(canvas, s)
    n_points, n_polys = len(mesh.points), len(mesh.polygons)
    first = scene.pen_chain[0]
    _hover(canvas, spots[0])
    assert canvas.pen_target(spots[0]) == ("close", first)
    img = _image(canvas)
    assert _any_pixel(img, spots[0] + (3.0, 3.0), _is_hover, radius=1), _rgb(img, spots[0] + (3.0, 3.0))
    assert not _any_pixel(_image_after_leave(canvas), spots[0] + (3.0, 3.0), _is_hover, radius=1)
    _hover(canvas, spots[0])
    _click(canvas, spots[0])
    assert not scene.pen_active()
    assert len(mesh.points) == n_points and len(mesh.polygons) == n_polys
    assert len(mesh.polygons[-1]) == 4
    _click(canvas, spots[4])
    assert scene.pen_chain == [n_points] and len(mesh.points) == n_points + 1


def test_pen_camera_plane_placement() -> None:
    canvas, scene = _make(tool="pen")
    spots = _pentagon(canvas)
    _click(canvas, spots[0])
    world = scene.active.world_points()
    p = world[-1]
    fwd = _fwd(canvas)
    origin_depth = float(canvas.camera.depth([[0.0, 0.0, 0.0]])[0])
    assert abs(float(canvas.camera.depth([p])[0]) - origin_depth) < 1e-6
    assert np.allclose(_px(canvas, p), spots[0], atol=0.75)
    canvas.camera.heading += 25.0
    canvas.camera.pitch -= 10.0
    canvas.update()
    fwd2 = _fwd(canvas)
    spot = _px(canvas, p) + (-80.0, 40.0)
    _click(canvas, spot)
    q = scene.active.world_points()[-1]
    assert abs(float((q - p) @ fwd2)) < 1e-6 and float(np.linalg.norm(q - p)) > 10.0
    assert np.allclose(_px(canvas, q), spot, atol=0.75)
    assert not np.allclose(fwd, fwd2)


def test_pen_snaps_onto_cube_surface() -> None:
    canvas, scene = _make(tool="pen")
    on_front = _px(canvas, (20.0, -40.0, -100.0))
    _click(canvas, on_front)
    p = scene.active.world_points()[-1]
    assert abs(p[2] + 100.0) < 1e-6 and abs(p[0]) <= 100.0 and abs(p[1]) <= 100.0, p
    assert np.allclose(p, (20.0, -40.0, -100.0), atol=3.0)
    on_right = _px(canvas, (100.0, 30.0, 40.0))
    _click(canvas, on_right)
    q = scene.active.world_points()[-1]
    assert abs(q[0] - 100.0) < 1e-6 and np.allclose(q, (100.0, 30.0, 40.0), atol=3.0), q


def test_line_pen_creates_line_object_without_faces() -> None:
    canvas, scene = _make(tool="line_pen")
    cube = scene.active
    depth0 = len(scene._undo)
    a, b, c = _line_spots(canvas)
    _click(canvas, a)
    assert len(scene.objects) == 2 and scene.active is not cube and scene.active.name == "Line"
    assert len(scene._undo) == depth0 + 1
    _click(canvas, b)
    _click(canvas, c)
    line = scene.active
    mesh = line.mesh
    assert len(mesh.points) == 3 and not mesh.has_faces() and len(mesh.loose_edges) == 2
    assert len(cube.mesh.points) == 8 and len(cube.mesh.polygons) == 6
    img = _image(canvas)
    mid = (a + b) / 2
    assert _any_pixel(img, mid, _is_line), _rgb(img, mid)
    assert canvas.pick(b) == ("point", 1)
    assert scene.undo() and len(scene.active.mesh.points) == 2
    assert scene.undo() and len(scene.active.mesh.points) == 1
    assert scene.undo() and len(scene.objects) == 1


def test_line_pen_branches_and_closes() -> None:
    canvas, scene = _make(tool="line_pen")
    a, b, c = _line_spots(canvas)
    for s in (a, b, c):
        _click(canvas, s)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert not scene.pen_active()
    mesh = scene.active.mesh
    middle = 1
    assert mesh.point_valence(middle) == 2
    _click(canvas, b)
    assert scene.pen_chain == [middle]
    _click(canvas, b + (0.0, -70.0))
    assert mesh.point_valence(middle) == 3 and len(mesh.points) == 4
    assert not mesh.has_faces()
    QTest.keyClick(canvas, Qt.Key.Key_Return)
    assert not scene.pen_active()
    d = (a + c) / 2 + (0.0, 60.0)
    for s in (d, d + (60.0, 0.0), d + (30.0, 45.0)):
        _click(canvas, s)
    first = scene.pen_chain[0]
    _click(canvas, d)
    assert not scene.pen_active()
    assert mesh.point_valence(first) == 2 and len(mesh.points) == 7


def test_esc_enter_and_right_click_end_stroke() -> None:
    canvas, scene = _make(tool="pen")
    spots = _pentagon(canvas)
    _click(canvas, spots[0])
    _click(canvas, spots[1])
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert not scene.pen_active()
    _click(canvas, spots[2])
    assert scene.pen_chain and len(scene.pen_chain) == 1
    QTest.mouseClick(canvas, RIGHT, NO_MOD, _pt(spots[3]))
    assert not scene.pen_active()
    _click(canvas, spots[3])
    scene.set_tool("move")
    assert not scene.pen_active()


def test_pen_preview_rubber_band() -> None:
    canvas, scene = _make(tool="line_pen")
    a, _b, c = _line_spots(canvas)
    _click(canvas, a)
    _hover(canvas, c)
    target = canvas.pen_preview_world()
    assert target is not None and np.allclose(_px(canvas, target), c, atol=0.75)
    img = _image(canvas)
    lit = 0
    for t in np.linspace(0.2, 0.8, 13):
        if _any_pixel(img, a + (c - a) * t, _is_light, radius=1):
            lit += 1
    assert 3 <= lit <= 12, lit
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.pen_preview_world() is not None
    img = _image(canvas)
    assert not any(_any_pixel(img, a + (c - a) * t, _is_light, radius=1) for t in (0.3, 0.5, 0.7))


def test_pen_drag_moves_existing_point_in_camera_plane() -> None:
    canvas, scene = _make(tool="pen")
    obj = scene.active
    before = obj.world_points().copy()
    xy = _points_px(canvas, scene)
    _press(canvas, xy[2])
    _move_to(canvas, xy[2], xy[2] + (40.0, -25.0))
    _release(canvas, xy[2] + (40.0, -25.0))
    after = obj.world_points()
    assert len(after) == 8 and not scene.pen_active()
    assert scene.selected_points == {2}
    delta = after[2] - before[2]
    assert float(np.linalg.norm(delta)) > 10.0 and abs(float(delta @ _fwd(canvas))) < 1e-6
    assert np.allclose(_px(canvas, after[2]), xy[2] + (40.0, -25.0), atol=1.0)
    assert np.allclose(np.delete(after, 2, axis=0), np.delete(before, 2, axis=0))
    assert scene.undo() and np.allclose(scene.active.world_points(), before)


def test_pen_drag_on_empty_space_places_at_release() -> None:
    canvas, scene = _make(tool="pen")
    spots = _pentagon(canvas)
    n0 = len(scene.active.mesh.points)
    _press(canvas, spots[0])
    _move_to(canvas, spots[0], spots[1])
    assert len(scene.active.mesh.points) == n0
    _release(canvas, spots[1])
    assert len(scene.active.mesh.points) == n0 + 1
    assert np.allclose(_px(canvas, scene.active.world_points()[-1]), spots[1], atol=0.75)


def _move_extrude(mode: str, select, via_key: bool):
    canvas, scene = _make(mode)
    select(canvas, scene)
    obj = scene.active
    before = obj.mesh.points.copy()
    polys0 = list(obj.mesh.polygons)
    depth0 = len(scene._undo)
    start = _arrow_start(canvas, "x")
    mid, end = start + (25.0, 0.0), start + (60.0, 0.0)
    _press(canvas, start)
    _move_to(canvas, start, mid)
    if via_key:
        QTest.keyPress(canvas, Qt.Key.Key_Control)
    else:
        _move_with_ctrl(canvas, mid + (2.0, 0.0))
    _move_to(canvas, mid, end)
    _release(canvas, end)
    if via_key:
        QTest.keyRelease(canvas, Qt.Key.Key_Control)
    return canvas, scene, obj, before, polys0, depth0


def test_move_ctrl_after_press_extrudes_points_along_x() -> None:
    def select(canvas, scene):
        _click(canvas, _points_px(canvas, scene)[2])

    canvas, scene, obj, before, _polys, depth0 = _move_extrude("points", select, via_key=True)
    mesh = obj.mesh
    assert len(mesh.points) == 9 and (2, 8) in mesh.loose_edges
    assert np.allclose(mesh.points[:8], before)
    delta = mesh.points[8] - before[2]
    assert delta[0] > 10.0 and abs(delta[1]) < 1e-9 and abs(delta[2]) < 1e-9, delta
    assert scene.selected_points == {8}
    assert len(scene._undo) == depth0 + 1
    assert scene.undo() and len(scene.active.mesh.points) == 8
    assert np.allclose(scene.active.mesh.points, before)


def test_move_ctrl_after_press_extrudes_edges_along_x() -> None:
    def select(canvas, scene):
        xy = _points_px(canvas, scene)
        _click(canvas, (xy[1] + xy[2]) / 2)

    canvas, scene, obj, before, polys0, _depth = _move_extrude("edges", select, via_key=False)
    mesh = obj.mesh
    assert len(mesh.points) == 10 and len(mesh.polygons) == len(polys0) + 1
    assert np.allclose(mesh.points[:8], before)
    (a2, b2), = scene.selected_edges
    assert {a2, b2} == {8, 9}
    for new, src in ((8, 1), (9, 2)):
        delta = mesh.points[new] - before[src]
        assert delta[0] > 10.0 and abs(delta[1]) < 1e-9 and abs(delta[2]) < 1e-9, (new, delta)
    quad = mesh.polygons[-1]
    assert len(quad) == 4 and {1, 2, 8, 9} == set(quad)


def test_move_ctrl_after_press_extrudes_faces_along_x() -> None:
    def select(canvas, scene):
        _click(canvas, _px(canvas, (100.0, 0.0, 20.0)))

    canvas, scene, obj, before, polys0, depth0 = _move_extrude("polygons", select, via_key=True)
    mesh = obj.mesh
    assert scene.selected_polygons == {3}
    assert len(mesh.points) == 12 and len(mesh.polygons) == 10
    face = mesh.polygons[3]
    assert set(face) == {8, 9, 10, 11}
    moved = mesh.points[list(face)]
    assert np.all(moved[:, 0] > 110.0) and np.allclose(moved[:, 0], moved[0, 0])
    assert np.allclose(np.sort(moved[:, 1:], axis=0), np.sort(before[[1, 2, 6, 5]][:, 1:], axis=0))
    assert np.allclose(mesh.points[:8], before)
    assert len(scene._undo) == depth0 + 1
    assert scene.undo() and len(scene.active.mesh.polygons) == 6


def test_pen_ctrl_after_press_extrudes_in_camera_plane() -> None:
    canvas, scene = _make(tool="pen")
    xy = _points_px(canvas, scene)
    before = scene.active.mesh.points.copy()
    _press(canvas, xy[2])
    _move_to(canvas, xy[2], xy[2] + (20.0, -10.0))
    QTest.keyPress(canvas, Qt.Key.Key_Control)
    _move_to(canvas, xy[2] + (20.0, -10.0), xy[2] + (50.0, -30.0))
    _release(canvas, xy[2] + (50.0, -30.0))
    QTest.keyRelease(canvas, Qt.Key.Key_Control)
    mesh = scene.active.mesh
    assert len(mesh.points) == 9 and (2, 8) in mesh.loose_edges and np.allclose(mesh.points[:8], before)
    d = mesh.points[8] - before[2]
    assert float(np.linalg.norm(d)) > 10.0 and abs(float(d @ _fwd(canvas))) < 1e-6
    assert np.allclose(_px(canvas, mesh.points[8]), xy[2] + (50.0, -30.0), atol=1.0)
    assert not scene.pen_active()
    canvas, scene = _make("edges", tool="pen")
    xy = _points_px(canvas, scene)
    on_edge = (xy[1] + xy[2]) / 2
    _press(canvas, on_edge)
    _move_to(canvas, on_edge, on_edge + (10.0, 0.0))
    _move_with_ctrl(canvas, on_edge + (12.0, 0.0))
    _move_to(canvas, on_edge + (12.0, 0.0), on_edge + (45.0, 10.0))
    _release(canvas, on_edge + (45.0, 10.0))
    mesh = scene.active.mesh
    assert len(mesh.points) == 10 and len(mesh.polygons) == 7
    assert scene.selected_edges == {(8, 9)}
    d8, d9 = mesh.points[8] - mesh.points[1], mesh.points[9] - mesh.points[2]
    assert np.allclose(d8, d9) and float(np.linalg.norm(d8)) > 10.0
    assert abs(float(d8 @ _fwd(canvas))) < 1e-6
    canvas, scene = _make("polygons", tool="pen")
    on_face = _px(canvas, (0.0, -40.0, -100.0))
    _press(canvas, on_face)
    _move_to(canvas, on_face, on_face + (0.0, 10.0))
    QTest.keyPress(canvas, Qt.Key.Key_Control)
    _move_to(canvas, on_face + (0.0, 10.0), on_face + (-30.0, 40.0))
    _release(canvas, on_face + (-30.0, 40.0))
    QTest.keyRelease(canvas, Qt.Key.Key_Control)
    mesh = scene.active.mesh
    assert scene.selected_polygons == {0} and len(mesh.polygons) == 10 and len(mesh.points) == 12
    from quartz_studio.scene import Mesh

    cube = Mesh.cube(200.0).points
    assert np.allclose(mesh.points[:8], cube)
    lifted = mesh.points[list(mesh.polygons[0])] - cube[[0, 3, 2, 1]]
    assert np.allclose(lifted, lifted[0]) and float(np.linalg.norm(lifted[0])) > 10.0
    assert abs(float(lifted[0] @ _fwd(canvas))) < 1e-6


def test_ctrl_at_press_still_deselects() -> None:
    canvas, scene = _make("points", tool="pen")
    xy = _points_px(canvas, scene)
    scene.select_components([2])
    before = scene.active.mesh.points.copy()
    _press(canvas, xy[2], CTRL)
    _move_to(canvas, xy[2], xy[2] + (40.0, 0.0))
    QTest.mouseRelease(canvas, LEFT, CTRL, _pt(xy[2] + (40.0, 0.0)))
    assert scene.selected_points == set()
    assert len(scene.active.mesh.points) == 8 and np.allclose(scene.active.mesh.points, before)
    assert not scene.pen_active()
    canvas, scene = _make("points", tool="move")
    xy = _points_px(canvas, scene)
    _click(canvas, xy[2])
    assert scene.selected_points == {2}
    before = scene.active.mesh.points.copy()
    _press(canvas, xy[2], CTRL)
    _move_to(canvas, xy[2], xy[2] + (40.0, 0.0))
    QTest.mouseRelease(canvas, LEFT, CTRL, _pt(xy[2] + (40.0, 0.0)))
    assert len(scene.active.mesh.points) == 9
    assert scene.selected_points and 2 not in scene.selected_points
    scene.undo()
    assert len(scene.active.mesh.points) == 8 and np.allclose(scene.active.mesh.points, before)
    assert not scene.pen_active()


def test_escape_cancels_extrude_drag() -> None:
    canvas, scene = _make("points")
    _click(canvas, _points_px(canvas, scene)[2])
    before = scene.active.mesh.points.copy()
    depth = len(scene._undo)
    start = _arrow_start(canvas, "x")
    _press(canvas, start)
    _move_to(canvas, start, start + (20.0, 0.0))
    QTest.keyPress(canvas, Qt.Key.Key_Control)
    _move_to(canvas, start + (20.0, 0.0), start + (50.0, 0.0))
    assert len(scene.active.mesh.points) == 9
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    _release(canvas, start + (50.0, 0.0))
    assert len(scene.active.mesh.points) == 8 and np.allclose(scene.active.mesh.points, before)
    assert len(scene._undo) == depth and not scene.can_redo()
    assert scene._group_depth == 0


def test_extrude_drag_is_one_ctrl_z_in_main_window() -> None:
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
        scene.set_mode("polygons")
        _settle(app)
        _click(canvas, _px(canvas, (100.0, 0.0, 20.0)))
        assert scene.selected_polygons == {3}
        before = scene.active.mesh.points.copy()
        start = _arrow_start(canvas, "x")
        _press(canvas, start)
        _move_to(canvas, start, start + (15.0, 0.0))
        QTest.keyPress(canvas, Qt.Key.Key_Control)
        _move_to(canvas, start + (15.0, 0.0), start + (60.0, 0.0))
        _release(canvas, start + (60.0, 0.0))
        QTest.keyRelease(canvas, Qt.Key.Key_Control)
        assert len(scene.active.mesh.polygons) == 10
        canvas.setFocus()
        _settle(app)
        QTest.keyClick(canvas, Qt.Key.Key_Z, CTRL)
        mesh = scene.active.mesh
        assert len(mesh.polygons) == 6 and len(mesh.points) == 8 and np.allclose(mesh.points, before)
        QTest.keyClick(canvas, Qt.Key.Key_Y, CTRL)
        assert len(scene.active.mesh.polygons) == 10
    finally:
        win.close()
        win.deleteLater()
        _settle(app)


def test_model_click_switches_active_object() -> None:
    canvas, scene = _make()
    from quartz_studio.scene import Mesh

    cube = scene.active
    small = scene.add_object("Cube", Mesh.cube(100.0))
    small.position = np.array([-400.0, 0.0, 0.0])
    line = scene.add_object("Line")
    line.mesh.add_point((300.0, -150.0, -200.0))
    line.mesh.add_point((500.0, -150.0, -200.0))
    line.mesh.add_point((500.0, 50.0, -200.0))
    line.mesh.add_loose_edge(0, 1)
    line.mesh.add_loose_edge(1, 2)
    scene.set_active(cube)
    canvas.update()
    _click(canvas, _px(canvas, (-400.0, 0.0, -50.0)))
    assert scene.active is small and scene.object_selected
    _click(canvas, _px(canvas, (400.0, -150.0, -200.0)) + (0.0, 4.0))
    assert scene.active is line and scene.object_selected
    img = _image(canvas)
    assert _any_pixel(img, _px(canvas, (450.0, -150.0, -200.0)), _is_citrine)
    _click(canvas, _px(canvas, (0.0, -40.0, -100.0)))
    assert scene.active is cube
    img = _image(canvas)
    assert _any_pixel(img, _px(canvas, (450.0, -150.0, -200.0)), _is_line)
    scene.set_mode("polygons")
    _click(canvas, _px(canvas, (-400.0, 0.0, -50.0)))
    assert scene.active is small and scene.mode == "polygons" and scene.selected_polygons == set()


def test_pen_places_points_on_other_objects_surface() -> None:
    canvas, scene = _make()
    from quartz_studio.scene import Mesh

    cube = scene.active
    other = scene.add_object("Cube", Mesh.cube(100.0))
    other.position = np.array([-400.0, 0.0, 0.0])
    scene.set_active(cube)
    scene.set_tool("pen")
    _click(canvas, _px(canvas, (-410.0, 10.0, -50.0)))
    p = cube.world_points()[-1]
    assert scene.active is cube and len(cube.mesh.points) == 9
    assert abs(p[2] + 50.0) < 1e-6 and np.allclose(p, (-410.0, 10.0, -50.0), atol=3.0), p



def _ctrl_drag(canvas, start, end) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    _press(canvas, start)
    _move_to(canvas, start, start + (10.0, 0.0), 2)
    _move_with_ctrl(canvas, start + (20.0, -10.0))
    _move_to(canvas, start + (20.0, -10.0), end, 4)
    _release(canvas, end)


def test_ctrl_extrude_of_the_open_stroke_keeps_its_cap() -> None:
    for mode in ("polygons", "points", "edges"):
        canvas, scene = _make(tool="pen", mode=mode)
        scene.remove_object(scene.active)
        spots = _pentagon(canvas)
        for s in spots[:3]:
            _click(canvas, s)
        mesh = scene.active.mesh
        assert scene.pen_chain == [0, 1, 2] and len(mesh.polygons) == 1
        grab = {"polygons": np.mean(spots[:3], axis=0), "points": spots[2],
                "edges": (spots[1] + spots[2]) / 2}[mode]
        _ctrl_drag(canvas, grab, grab + (40.0, -40.0))
        assert not scene.pen_active(), mode
        after = [tuple(p) for p in mesh.polygons]
        loose = list(mesh.loose_edges)
        if mode == "polygons":
            assert after[0] == (3, 4, 5) and len(after) == 4, after
        n = len(mesh.points)
        _click(canvas, spots[3])
        assert [tuple(p) for p in mesh.polygons] == after, (mode, mesh.polygons)
        assert mesh.loose_edges == loose and len(mesh.points) == n + 1
        assert scene.pen_chain == [n], (mode, scene.pen_chain)
        scene.undo()
        scene.undo()
        assert scene.active.mesh.polygons == [(0, 1, 2)] and scene.pen_chain == [0, 1, 2]
        assert len(scene.active.mesh.points) == 3


def _quad_seen_from_behind(mode: str = "points"):
    canvas, scene = _make(tool="pen")
    scene.add_object("Polygon")
    for xy in ((150, 150), (300, 150), (300, 260), (150, 260)):
        _click(canvas, xy)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    quad = scene.active
    assert quad.mesh.polygons == [(0, 1, 2, 3)] or len(quad.mesh.polygons[0]) == 4
    centre = quad.world_points().mean(axis=0)
    canvas.camera.heading += 180.0
    canvas.camera.target = centre
    canvas.update()
    scene.set_tool("move")
    scene.set_mode(mode)
    view = canvas._object_view(quad)
    assert not view.front[0]
    return canvas, scene, quad


def test_open_faces_are_edited_from_behind() -> None:
    canvas, scene, quad = _quad_seen_from_behind("points")
    xy = canvas.project_world(quad.world_points())
    for i in range(4):
        assert canvas.pick(xy[i]) == ("point", i)
    img = _image_after_leave(canvas)
    shown = [_any_pixel(img, xy[i], lambda c: _is_point(c) or _is_citrine(c), radius=2) for i in range(4)]
    assert all(shown), shown
    _click(canvas, xy[1])
    assert scene.selected_points == {1}
    scene.set_mode("edges")
    mid = (xy[0] + xy[1]) / 2
    kind, edge = canvas.pick(mid)
    assert kind == "edge" and set(edge) == {0, 1}
    scene.set_mode("polygons")
    assert canvas.pick(xy.mean(axis=0)) == ("polygon", 0)
    scene.set_mode("model")
    scene.set_active(scene.objects[0])
    _click(canvas, xy.mean(axis=0))
    assert scene.active is quad and scene.object_selected
    cube_view = canvas._object_view(scene.objects[0])
    assert not cube_view.visible_points.all()


def test_extruded_line_face_stays_editable_from_behind() -> None:
    canvas, scene = _make(tool="line_pen")
    a, b, _c = _line_spots(canvas)
    _click(canvas, a)
    _click(canvas, b)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    scene.set_tool("move")
    scene.set_mode("edges")
    _click(canvas, (a + b) / 2)
    start = _arrow_start(canvas, "y")
    _ctrl_drag(canvas, start, start + (0.0, -60.0))
    line = scene.active
    mesh = line.mesh
    assert len(mesh.polygons) == 1 and len(mesh.points) == 4
    view = canvas._object_view(line)
    assert not view.front[0] and view.visible_points.all()
    (new_edge,) = scene.selected_edges
    xy = canvas.project_world(line.world_points())
    img = _image_after_leave(canvas)
    assert _any_pixel(img, (xy[new_edge[0]] + xy[new_edge[1]]) / 2, _is_citrine)
    kind, edge = canvas.pick((xy[new_edge[0]] + xy[new_edge[1]]) / 2)
    assert kind == "edge" and tuple(sorted(edge)) == new_edge
    scene.set_mode("points")
    for i in range(4):
        assert canvas.pick(xy[i]) == ("point", i)
    scene.set_mode("polygons")
    assert canvas.pick(xy.mean(axis=0)) == ("polygon", 0)


def test_polygon_pen_closes_on_first_point_from_behind() -> None:
    canvas, scene = _make(tool="pen")
    scene.add_object("Polygon")
    for xy in ((150, 150), (300, 150), (300, 260), (150, 260)):
        _click(canvas, xy)
    assert scene.pen_chain == [0, 1, 2, 3]
    QTest.mousePress(canvas, LEFT, Qt.KeyboardModifier.AltModifier, QPoint(225, 205))
    for k in range(1, 61):
        pos = QPointF(225.0 + 10.0 * k, 205.0)
        QApplication.sendEvent(canvas, QMouseEvent(QEvent.Type.MouseMove, pos, QPointF(canvas.mapToGlobal(pos)),
                                                   Qt.MouseButton.NoButton, LEFT, Qt.KeyboardModifier.AltModifier))
    QTest.mouseRelease(canvas, LEFT, Qt.KeyboardModifier.AltModifier, QPoint(825, 205))
    assert not canvas._object_view(scene.active).front[0]
    first = _px(canvas, scene.active.world_points()[0])
    _hover(canvas, first)
    assert canvas.pen_target(QPointF(*first))[0] == "close"
    _click(canvas, first)
    mesh = scene.active.mesh
    assert not scene.pen_active() and len(mesh.points) == 4 and [len(p) for p in mesh.polygons] == [4]


def test_line_pen_branches_from_an_inactive_line() -> None:
    canvas, scene = _make(tool="line_pen")
    spots = _line_spots(canvas)
    for s in spots:
        _click(canvas, s)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    line = scene.active
    assert line.name == "Line" and line.mesh.point_valence(1) == 2
    scene.set_active(scene.objects[0])
    depth = len(scene._undo)
    mid = _px(canvas, line.world_points()[1])
    _hover(canvas, mid)
    assert canvas.pen_target(QPointF(*mid))[0] == "start"
    _click(canvas, mid)
    assert [o.name for o in scene.objects] == ["Cube", "Line"]
    assert scene.active is line and scene.pen_chain == [1]
    assert len(scene._undo) == depth + 1
    _click(canvas, mid + (0.0, -80.0))
    assert line.mesh.point_valence(1) == 3 and len(line.mesh.points) == 4
    cube = scene.objects[0]
    corner = cube.world_points()[2]
    _click(canvas, _px(canvas, corner))
    assert scene.active is line and np.allclose(line.world_points()[-1], corner, atol=1e-6)


def test_other_button_cancel_never_places_a_pen_point() -> None:
    canvas, scene = _make(tool="pen")
    xy = _points_px(canvas, scene)
    depth = len(scene._undo)
    before = scene.active.mesh.points.copy()
    _press(canvas, xy[2])
    _move_to(canvas, xy[2], xy[2] + (50.0, 0.0), 5)
    assert not np.allclose(scene.active.mesh.points, before)
    QTest.mousePress(canvas, RIGHT, NO_MOD, _pt(xy[2] + (50.0, 0.0)))
    QTest.mouseRelease(canvas, RIGHT, NO_MOD, _pt(xy[2] + (50.0, 0.0)))
    _release(canvas, xy[2] + (50.0, 0.0))
    assert np.allclose(scene.active.mesh.points, before)
    assert len(scene.active.mesh.points) == 8 and not scene.pen_active()
    assert len(scene._undo) == depth


def _star(canvas, n: int, radius: float = 150.0) -> list[np.ndarray]:
    film = canvas.film_rect()
    cx, cy = film.left() + film.width() * 0.3, film.top() + film.height() * 0.5
    return [np.array([cx + radius * (1.0 if k % 2 else 0.55) * math.sin(2 * math.pi * k / n),
                      cy - radius * (1.0 if k % 2 else 0.55) * math.cos(2 * math.pi * k / n)])
            for k in range(n)]


def test_large_ngon_cached_raycast_guides_and_hover_speed() -> None:
    import time

    canvas, scene = _make(tool="pen")
    scene.add_object("Polygon")
    for s in _star(canvas, 80, 200.0):
        _click(canvas, s)
    obj = scene.active
    mesh = obj.mesh
    assert len(mesh.polygons) == 1 and len(mesh.polygons[0]) == 80, [len(p) for p in mesh.polygons]
    guides = canvas.ngon_guides(mesh, 0)
    assert sorted(map(sorted, guides)) == sorted(map(sorted, mesh.ngon_guides(0)))
    assert guides and canvas.ngon_guides(mesh, 0) is guides
    film = canvas.film_rect()
    for fx in np.linspace(0.05, 0.95, 9):
        for fy in np.linspace(0.1, 0.9, 7):
            o, d = canvas.ray_at((film.left() + film.width() * fx, film.top() + film.height() * fy))
            mine, ref = canvas.raycast(o, d), scene.raycast(o, d)
            assert (mine is None) == (ref is None), (fx, fy)
            if ref is not None:
                assert mine[0] is ref[0] and mine[1] == ref[1] and abs(mine[3] - ref[3]) < 1e-6
    _hover(canvas, (film.left() + 20.0, film.top() + 20.0))
    t0 = time.perf_counter()
    for k in range(10):
        _hover(canvas, (film.left() + film.width() * 0.3 + 3.0 * k, film.top() + film.height() * 0.5))
        canvas.repaint()
    per_move = (time.perf_counter() - t0) / 10.0
    assert per_move < 0.25, per_move


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
