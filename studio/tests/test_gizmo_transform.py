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
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio import theme
from quartz_studio.app import create_app

VIEW_SIZE = (1000, 640)
LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
X = np.array([1.0, 0.0, 0.0])
Y = np.array([0.0, 1.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])

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


def _key(widget: QWidget, key: Qt.Key, text: str = "") -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, NO_MOD, text))


def _image(canvas) -> QImage:
    return canvas.grab().toImage()


def _near_matches(img: QImage, pos, pred) -> bool:
    x, y = int(round(float(pos[0]))), int(round(float(pos[1])))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            c = img.pixelColor(x + dx, y + dy)
            if pred((c.red(), c.green(), c.blue())):
                return True
    return False


def _channels(token: str) -> tuple[int, int, int]:
    c = QColor(token)
    return c.red(), c.green(), c.blue()


def _distance(rgb: tuple[int, int, int], token: str) -> int:
    return sum(abs(a - b) for a, b in zip(rgb, _channels(token)))


def _is_hover(rgb: tuple[int, int, int]) -> bool:
    return _distance(rgb, theme.GIZMO_HOVER) <= 40


def _is_hover_fill(rgb: tuple[int, int, int]) -> bool:
    return _distance(rgb, theme.GIZMO_HOVER) <= 75


def _is_view_ring(rgb: tuple[int, int, int]) -> bool:
    return _distance(rgb, theme.TEXT_BRIGHT) <= 40


def _is_axis(token: str):
    def pred(rgb: tuple[int, int, int]) -> bool:
        return _distance(rgb, token) <= 40

    return pred


def _ring_radius(points) -> float:
    pts = np.asarray(points, float)
    centre = pts.mean(axis=0)
    return float(np.mean(np.linalg.norm(pts - centre, axis=1)))


def _plane_point(canvas, centre, u, v, deg: float, radius: float = 60.0) -> np.ndarray:
    t = math.radians(deg)
    world = np.asarray(centre, float) + radius * (math.cos(t) * np.asarray(u, float)
                                                  + math.sin(t) * np.asarray(v, float))
    return canvas.project_world([world])[0]


def _press(btn) -> None:
    QTest.mouseClick(btn, LEFT, NO_MOD, btn.rect().center())
    _settle(QApplication.instance(), 2)


def _palette():
    from quartz_studio.widgets.tool_palette import ToolPalette

    host = QWidget()
    _LIVE.append(host)
    tools = ToolPalette(host)
    host.resize(200, 800)
    host.show()
    _settle(QApplication.instance(), 2)
    return tools


def test_palette_buttons_switch_tool_and_keys_check_their_button() -> None:
    canvas, scene = _make()
    tools = _palette()
    _press(tools.button("Rotate"))
    assert scene.tool == "rotate" and tools.active_tool() == "Rotate"
    _press(tools.button("Scale"))
    assert scene.tool == "scale" and tools.active_tool() == "Scale"
    _press(tools.button("Move"))
    assert scene.tool == "move" and tools.active_tool() == "Move"
    _key(canvas, Qt.Key.Key_R, "r")
    assert tools.button("Rotate").isChecked() and tools.scene_tool() == "rotate"
    assert canvas.hud_text == "Rotate"
    _key(canvas, Qt.Key.Key_T, "t")
    assert tools.button("Scale").isChecked() and tools.scene_tool() == "scale"
    assert canvas.hud_text == "Scale"
    _key(canvas, Qt.Key.Key_E, "e")
    assert tools.button("Move").isChecked() and tools.scene_tool() == "move"
    assert canvas.hud_text == "Move"


def test_rotate_gizmo_has_xyz_rings_and_white_view_ring() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    rings = canvas.gizmo_rings()
    assert set(rings) == {"x", "y", "z", "view"}, rings.keys()
    assert canvas.gizmo_handles() == {}
    assert _ring_radius(rings["view"]) > 1.1 * _ring_radius(rings["x"])
    img = _image(canvas)
    assert _near_matches(img, rings["view"][0], _is_view_ring), "view ring is not the view ring colour"
    assert _near_matches(img, rings["x"][18], _is_axis(theme.AXIS_X)), "x ring is not the X axis colour"


def test_hovered_ring_turns_yellow() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    point = canvas.gizmo_rings()["x"][6]
    _mouse(canvas, QEvent.Type.MouseMove, point)
    assert canvas._hover == "x", canvas._hover
    assert _near_matches(_image(canvas), point, _is_hover), "hovered ring is not the hover colour"


def test_hovered_scale_cube_turns_yellow() -> None:
    canvas, scene = _make()
    scene.set_tool("scale")
    tip = canvas.gizmo_handles()["x"][1]
    _mouse(canvas, QEvent.Type.MouseMove, tip)
    assert canvas._hover == "x", canvas._hover
    assert _near_matches(_image(canvas), tip, _is_hover), "hovered cube is not the hover colour"


def test_rotate_model_quarter_turn_about_y_and_one_undo_step() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    depth = len(scene._undo)
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, scene.selection_center(), Z, X, 135.0)
    _drag(canvas, start, end)
    rot = scene.active.rotation
    assert abs(rot[1] - 90.0) < 1.0, rot
    assert np.allclose(rot[[0, 2]], 0.0, atol=1e-6), rot
    assert len(scene._undo) == depth + 1
    assert scene.undo() and np.allclose(scene.active.rotation, 0.0)
    assert scene._group_depth == 0


def test_rotate_past_ninety_keeps_matrix_and_canonical_euler() -> None:
    from quartz_studio.scene import rotation_matrix

    canvas, scene = _make()
    scene.set_tool("rotate")
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, scene.selection_center(), Z, X, 165.0)
    _drag(canvas, start, end)
    rot = scene.active.rotation
    assert np.allclose(rot, [0.0, 120.0, 0.0], atol=1e-6), rot
    assert np.allclose(rotation_matrix(rot), rotation_matrix([0.0, 120.0, 0.0]), atol=1e-9)


def test_rotate_shift_snaps_to_five_degrees() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, scene.selection_center(), Z, X, 45.0 + 37.0)
    _drag(canvas, start, end, mods=SHIFT)
    assert abs(scene.active.rotation[1] - 35.0) < 1e-6, scene.active.rotation


def test_rotate_polygon_face_keeps_distance_to_axis() -> None:
    canvas, scene = _make("polygons")
    scene.set_tool("rotate")
    _click(canvas, canvas.project_world([[0.0, 100.0, 0.0]])[0])
    assert scene.selected_polygons == {4}, scene.selected_polygons
    obj = scene.active
    before = obj.world_points().copy()
    idx = scene.affected_points()
    centre = scene.selection_center()
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, centre, Z, X, 135.0)
    _drag(canvas, start, end)
    after = obj.world_points()
    others = [i for i in range(len(before)) if i not in idx]
    assert not np.allclose(after[idx], before[idx]), "face did not rotate"
    assert np.allclose(after[others], before[others])

    def axis_distance(pts) -> np.ndarray:
        rel = np.asarray(pts, float) - centre
        return np.linalg.norm(rel[:, [0, 2]], axis=1)

    assert np.allclose(axis_distance(after[idx]), axis_distance(before[idx]), atol=1e-6)


def test_rotate_ctrl_during_gizmo_drag_does_not_extrude() -> None:
    canvas, scene = _make("polygons")
    scene.set_tool("rotate")
    _click(canvas, canvas.project_world([[0.0, 100.0, 0.0]])[0])
    faces = len(scene.active.mesh.polygons)
    before = scene.active.world_points().copy()
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, scene.selection_center(), Z, X, 135.0)
    _mouse(canvas, QEvent.Type.MouseButtonPress, start, LEFT, LEFT, NO_MOD)
    for k in range(1, 11):
        _mouse(canvas, QEvent.Type.MouseMove, start + (end - start) * k / 10, NO_BUTTON, LEFT, CTRL)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, end, LEFT, NO_BUTTON, CTRL)
    assert not np.allclose(scene.active.world_points(), before), "face did not rotate"
    assert len(scene.active.mesh.polygons) == faces
    assert canvas._drag is None and scene._group_depth == 0


def test_escape_cancels_rotate_drag_and_restores() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    depth = len(scene._undo)
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, scene.selection_center(), Z, X, 135.0)
    _drag(canvas, start, end, release=False)
    assert abs(scene.active.rotation[1] - 90.0) < 1.0
    _key(canvas, Qt.Key.Key_Escape)
    assert np.allclose(scene.active.rotation, 0.0)
    assert canvas._drag is None and scene._group_depth == 0 and len(scene._undo) == depth
    _mouse(canvas, QEvent.Type.MouseButtonRelease, end, LEFT, NO_BUTTON)
    assert np.allclose(scene.active.rotation, 0.0) and len(scene._undo) == depth


def _two_points_apart_in_x(canvas, scene) -> tuple[int, int]:
    pts = scene.active.world_points()
    j = next(i for i in range(len(pts)) if i != 2 and abs(pts[i, 0] - pts[2, 0]) > 1.0)
    return 2, j


def test_right_click_cancels_scale_drag_in_points_mode() -> None:
    canvas, scene = _make("points")
    obj = scene.active
    xy = canvas.project_world(obj.world_points())
    a, b = _two_points_apart_in_x(canvas, scene)
    _click(canvas, xy[a])
    _click(canvas, xy[b], SHIFT)
    scene.set_tool("scale")
    before = obj.world_points().copy()
    depth = len(scene._undo)
    c = np.array(canvas.gizmo_center())
    tip = np.array(canvas.gizmo_handles()["x"][1])
    _drag(canvas, c + 0.5 * (tip - c), tip + (30.0, 0.0), release=False)
    assert not np.allclose(obj.world_points(), before)
    _mouse(canvas, QEvent.Type.MouseButtonPress, tip, RIGHT, RIGHT)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, tip, RIGHT, NO_BUTTON)
    assert np.allclose(scene.active.world_points(), before)
    assert canvas._drag is None and scene._group_depth == 0 and len(scene._undo) == depth
    _mouse(canvas, QEvent.Type.MouseButtonRelease, tip, LEFT, NO_BUTTON)
    assert np.allclose(scene.active.world_points(), before)


def test_scale_axis_changes_only_that_axis_and_undoes_in_one_step() -> None:
    canvas, scene = _make()
    scene.set_tool("scale")
    obj = scene.active
    depth = len(scene._undo)
    c = np.array(canvas.gizmo_center())
    tip = np.array(canvas.gizmo_handles()["x"][1])
    _drag(canvas, c + 0.5 * (tip - c), tip)
    assert np.allclose(obj.scale, [2.0, 1.0, 1.0], atol=1e-6), obj.scale
    assert len(scene._undo) == depth + 1
    assert scene.undo() and np.allclose(scene.active.scale, 1.0)


def test_scale_centre_cube_scales_all_axes_uniformly() -> None:
    canvas, scene = _make()
    scene.set_tool("scale")
    obj = scene.active
    size0 = obj.size().copy()
    c = np.array(canvas.gizmo_center())
    _drag(canvas, c + (3.0, 0.0), c + (6.0, 0.0))
    assert np.allclose(obj.scale, 2.0, atol=1e-6), obj.scale
    assert np.allclose(obj.size(), 2.0 * size0, atol=1e-6)


def test_scale_shift_snaps_to_tenths() -> None:
    canvas, scene = _make()
    scene.set_tool("scale")
    c = np.array(canvas.gizmo_center())
    tip = np.array(canvas.gizmo_handles()["y"][1])
    _drag(canvas, c + 0.5 * (tip - c), c + 0.685 * (tip - c), mods=SHIFT)
    scale = scene.active.scale
    assert abs(scale[1] - 1.4) < 1e-6, scale
    assert np.allclose(scale[[0, 2]], 1.0), scale


def test_scale_points_scales_selection_about_its_centre() -> None:
    canvas, scene = _make("points")
    obj = scene.active
    xy = canvas.project_world(obj.world_points())
    a, b = _two_points_apart_in_x(canvas, scene)
    _click(canvas, xy[a])
    _click(canvas, xy[b], SHIFT)
    before = obj.world_points().copy()
    scene.set_tool("scale")
    c = np.array(canvas.gizmo_center())
    tip = np.array(canvas.gizmo_handles()["x"][1])
    _drag(canvas, c + 0.5 * (tip - c), tip)
    after = obj.world_points()
    sel = [a, b]
    centre = before[sel].mean(axis=0)
    assert np.abs(before[sel, 0] - centre[0]).max() > 1.0
    assert np.allclose(after[sel, 0] - centre[0], 2.0 * (before[sel, 0] - centre[0]), atol=1e-3)
    assert np.allclose(after[sel, 1:], before[sel, 1:], atol=1e-6)
    others = [i for i in range(len(before)) if i not in sel]
    assert np.allclose(after[others], before[others])


def test_rotate_and_scale_gizmos_keep_constant_screen_size() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    near = {n: _ring_radius(p) for n, p in canvas.gizmo_rings().items()}
    canvas.camera.dolly(0.5)
    close = {n: _ring_radius(p) for n, p in canvas.gizmo_rings().items()}
    assert set(near) == {"x", "y", "z", "view"}
    for name in near:
        assert abs(close[name] / near[name] - 1.0) < 0.12, (name, near[name], close[name])
    scene.set_tool("scale")
    before = {a: math.dist(*canvas.gizmo_handles()[a]) for a in "xyz"}
    canvas.camera.dolly(2.0)
    after = {a: math.dist(*canvas.gizmo_handles()[a]) for a in "xyz"}
    for axis in "xyz":
        assert abs(after[axis] / before[axis] - 1.0) < 0.12, (axis, before[axis], after[axis])


def test_rotate_and_scale_gizmos_hidden_without_selection() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    ring = canvas.gizmo_rings()["x"][0]
    scene.clear_selection()
    assert not scene.has_selection()
    assert canvas.gizmo_rings() == {}
    assert canvas.gizmo_pick(ring) is None
    scene.set_tool("scale")
    assert canvas.gizmo_handles() == {} and canvas.gizmo_center() is None
    assert canvas.gizmo_pick(ring) is None


def test_scale_handles_follow_rotated_object_axes() -> None:
    canvas, scene = _make()
    scene.set_object_rotation(2, 90.0)
    scene.set_tool("scale")
    c = np.array(canvas.gizmo_center())
    tip = np.array(canvas.gizmo_handles()["x"][1])
    centre = scene.selection_center()
    along_y = np.array(canvas.project_world([centre + Y * 100.0])[0]) - c
    cos = abs(float(np.dot(tip - c, along_y))) / (np.linalg.norm(tip - c) * np.linalg.norm(along_y))
    assert cos > 0.999, cos
    _drag(canvas, c + 0.5 * (tip - c), tip)
    assert np.allclose(scene.active.scale, [2.0, 1.0, 1.0], atol=1e-6), scene.active.scale
    extent = np.ptp(scene.active.world_points(), axis=0)
    assert np.allclose(extent, [200.0, 400.0, 200.0], atol=1e-6), extent


def test_ring_hit_on_crossing_resolves_to_first_ring() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    rings = canvas.gizmo_rings()
    assert canvas.ring_hit(rings["x"][0]) == "x", canvas.ring_hit(rings["x"][0])
    assert canvas.ring_hit(rings["z"][12]) == "x", canvas.ring_hit(rings["z"][12])


def test_tool_key_during_rotate_drag_cancels_and_restores() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    depth = len(scene._undo)
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, scene.selection_center(), Z, X, 135.0)
    _drag(canvas, start, end, release=False)
    assert abs(scene.active.rotation[1] - 90.0) < 1.0, scene.active.rotation
    _key(canvas, Qt.Key.Key_T, "t")
    assert scene.tool == "scale"
    assert np.allclose(scene.active.rotation, 0.0), scene.active.rotation
    assert canvas._drag is None and scene._group_depth == 0 and len(scene._undo) == depth
    _mouse(canvas, QEvent.Type.MouseButtonRelease, end, LEFT, NO_BUTTON)
    assert np.allclose(scene.active.rotation, 0.0) and len(scene._undo) == depth


def test_move_key_during_rotate_drag_cancels_and_restores() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    depth = len(scene._undo)
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, scene.selection_center(), Z, X, 135.0)
    _drag(canvas, start, end, release=False)
    assert abs(scene.active.rotation[1] - 90.0) < 1.0, scene.active.rotation
    _key(canvas, Qt.Key.Key_E, "e")
    assert scene.tool == "move"
    assert np.allclose(scene.active.rotation, 0.0), scene.active.rotation
    assert canvas._drag is None and scene._group_depth == 0 and len(scene._undo) == depth


def test_right_click_cancels_rotate_drag_and_restores() -> None:
    canvas, scene = _make()
    scene.set_tool("rotate")
    depth = len(scene._undo)
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, scene.selection_center(), Z, X, 135.0)
    _drag(canvas, start, end, release=False)
    assert abs(scene.active.rotation[1] - 90.0) < 1.0, scene.active.rotation
    _mouse(canvas, QEvent.Type.MouseButtonPress, end, RIGHT, RIGHT)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, end, RIGHT, NO_BUTTON)
    assert np.allclose(scene.active.rotation, 0.0), scene.active.rotation
    assert canvas._drag is None and scene._group_depth == 0 and len(scene._undo) == depth


def test_rotate_points_keeps_distance_to_axis() -> None:
    canvas, scene = _make("points")
    obj = scene.active
    xy = canvas.project_world(obj.world_points())
    a, b = _two_points_apart_in_x(canvas, scene)
    _click(canvas, xy[a])
    _click(canvas, xy[b], SHIFT)
    scene.set_tool("rotate")
    before = obj.world_points().copy()
    sel = [a, b]
    centre = scene.selection_center()
    start = canvas.gizmo_rings()["y"][6]
    end = _plane_point(canvas, centre, Z, X, 135.0)
    _drag(canvas, start, end)
    after = obj.world_points()
    others = [i for i in range(len(before)) if i not in sel]
    assert not np.allclose(after[sel], before[sel]), "points did not rotate"
    assert np.allclose(after[others], before[others])

    def axis_distance(pts) -> np.ndarray:
        rel = np.asarray(pts, float) - centre
        return np.linalg.norm(rel[:, [0, 2]], axis=1)

    assert np.allclose(axis_distance(after[sel]), axis_distance(before[sel]), atol=1e-6)


PLANE_NAMES = ("plane_x", "plane_y", "plane_z")
PLANE_COLORS = {"plane_x": theme.AXIS_X, "plane_y": theme.AXIS_Y, "plane_z": theme.AXIS_Z}
PLANE_OFFSET = (37.0, -23.0)


def _nearest_axis(token: str):
    others = [t for t in (theme.AXIS_X, theme.AXIS_Y, theme.AXIS_Z) if t != token]

    def pred(rgb: tuple[int, int, int]) -> bool:
        return all(_distance(rgb, token) < _distance(rgb, other) for other in others)

    return pred


def _quad_centre(canvas, name: str) -> np.ndarray:
    return np.asarray(canvas.gizmo_plane_handles()[name], float).mean(axis=0)


def _ray_on_plane(canvas, point, axis: int, pos) -> np.ndarray:
    o, r = canvas.ray_at(QPointF(float(pos[0]), float(pos[1])))
    normal = np.eye(3)[axis]
    t = float((np.asarray(point, float) - o) @ normal) / float(r @ normal)
    return o + r * t


def _predicted_delta(canvas, centre, name: str, start, end) -> np.ndarray:
    axis = "xyz".index(name[-1])
    return _ray_on_plane(canvas, centre, axis, end) - _ray_on_plane(canvas, centre, axis, start)


def _parented(scene):
    null = scene.add_parametric("null", name="Group", activate=False)
    null.position = np.array([120.0, 30.0, -60.0])
    null.rotation = np.array([20.0, 40.0, 10.0])
    cube = scene.active
    scene.set_parent(cube, null)
    scene.set_active(cube)
    return cube


def _seg_dist(pt, seg) -> float:
    from quartz_studio.widgets.viewport import _segment_distance

    (sx, sy), (ex, ey) = seg
    n = math.hypot(ex - sx, ey - sy)
    ux, uy = (ex - sx) / n, (ey - sy) / n
    tip = (ex + ux * 12.0, ey + uy * 12.0)
    return _segment_distance(float(pt[0]), float(pt[1]), sx + ux * 4.0, sy + uy * 4.0, *tip)


def test_move_gizmo_draws_three_plane_handles_in_axis_colours() -> None:
    canvas, scene = _make()
    handles = canvas.gizmo_plane_handles()
    assert set(handles) == set(PLANE_NAMES), handles.keys()
    img = _image(canvas)
    for name in PLANE_NAMES:
        assert _near_matches(img, _quad_centre(canvas, name), _nearest_axis(PLANE_COLORS[name])), name
    scene.set_tool("scale")
    assert canvas.gizmo_plane_handles() == {}
    scene.set_tool("rotate")
    assert canvas.gizmo_plane_handles() == {}


def test_plane_handles_sit_near_the_origin_and_keep_screen_size() -> None:
    canvas, _scene = _make()
    c = np.array(canvas.gizmo_center())
    for name in PLANE_NAMES:
        quad = np.asarray(canvas.gizmo_plane_handles()[name], float)
        assert np.linalg.norm(quad.mean(axis=0) - c) < 60.0, name
    before = {n: float(np.ptp(q[:, 0]) + np.ptp(q[:, 1])) for n, q in canvas.gizmo_plane_handles().items()}
    canvas.camera.dolly(0.5)
    after = {n: float(np.ptp(q[:, 0]) + np.ptp(q[:, 1])) for n, q in canvas.gizmo_plane_handles().items()}
    for name in PLANE_NAMES:
        assert abs(after[name] / before[name] - 1.0) < 0.15, (name, before[name], after[name])


def test_plane_handle_hover_turns_yellow() -> None:
    canvas, _scene = _make()
    point = _quad_centre(canvas, "plane_z")
    _mouse(canvas, QEvent.Type.MouseMove, point)
    assert canvas._hover == "plane_z", canvas._hover
    assert _near_matches(_image(canvas), point, _is_hover_fill), "hovered plane handle is not the hover colour"


def test_plane_drag_moves_exactly_two_axes_in_object_mode() -> None:
    for name in PLANE_NAMES:
        canvas, scene = _make()
        obj = scene.active
        before = obj.world_position().copy()
        start = _quad_centre(canvas, name)
        assert canvas.gizmo_pick(start) == name, (name, canvas.gizmo_pick(start))
        end = start + PLANE_OFFSET
        expected = _predicted_delta(canvas, before, name, start, end)
        depth = len(scene._undo)
        _drag(canvas, start, end)
        moved = obj.world_position() - before
        axis = "xyz".index(name[-1])
        assert abs(moved[axis]) < 1e-6, (name, moved)
        assert np.allclose(moved, expected, atol=1e-6), (name, moved, expected)
        assert np.count_nonzero(np.abs(moved) > 1.0) == 2, (name, moved)
        assert len(scene._undo) == depth + 1 and scene._group_depth == 0 and canvas._drag is None
        assert scene.undo() and np.allclose(scene.active.world_position(), before)


def test_plane_drag_cursor_point_follows_the_cursor() -> None:
    canvas, scene = _make()
    before = scene.active.world_position().copy()
    start = _quad_centre(canvas, "plane_y")
    end = start + (-41.0, 18.0)
    hit0 = _ray_on_plane(canvas, before, 1, start)
    _drag(canvas, start, end)
    moved_hit = hit0 + (scene.active.world_position() - before)
    assert np.allclose(moved_hit, _ray_on_plane(canvas, before, 1, end), atol=1e-6)


def test_plane_drag_moves_polygon_selection_in_two_axes_only() -> None:
    for name in PLANE_NAMES:
        canvas, scene = _make("polygons")
        _click(canvas, canvas.project_world([[0.0, 100.0, 0.0]])[0])
        assert scene.selected_polygons == {4}, scene.selected_polygons
        obj = scene.active
        idx = scene.affected_points()
        before = obj.world_points().copy()
        centre = scene.selection_center().copy()
        start = _quad_centre(canvas, name)
        assert canvas.gizmo_pick(start) == name, (name, canvas.gizmo_pick(start))
        end = start + PLANE_OFFSET
        expected = _predicted_delta(canvas, centre, name, start, end)
        depth = len(scene._undo)
        _drag(canvas, start, end)
        after = obj.world_points()
        others = [i for i in range(len(before)) if i not in idx]
        assert np.allclose(after[others], before[others])
        assert np.allclose(after[idx] - before[idx], expected, atol=1e-6), name
        assert abs(expected["xyz".index(name[-1])]) < 1e-9
        assert len(scene._undo) == depth + 1
        assert scene.undo() and np.allclose(scene.active.world_points(), before)


def test_plane_drag_under_rotated_parent_moves_in_world_axes() -> None:
    for name in PLANE_NAMES:
        canvas, scene = _make()
        cube = _parented(scene)
        before = cube.world_position().copy()
        local_before = cube.position.copy()
        start = _quad_centre(canvas, name)
        assert canvas.gizmo_pick(start) == name, (name, canvas.gizmo_pick(start))
        end = start + PLANE_OFFSET
        expected = _predicted_delta(canvas, before, name, start, end)
        _drag(canvas, start, end)
        moved = cube.world_position() - before
        assert np.allclose(moved, expected, atol=1e-6), (name, moved, expected)
        assert abs(moved["xyz".index(name[-1])]) < 1e-6
        assert not np.allclose(cube.position - local_before, moved, atol=1e-3)


def test_plane_drag_under_rotated_parent_in_polygons_mode() -> None:
    canvas, scene = _make("polygons")
    cube = _parented(scene)
    top = cube.world_points()[list(cube.mesh.polygons[4])].mean(axis=0)
    _click(canvas, canvas.project_world([top])[0])
    assert scene.selected_polygons == {4}, scene.selected_polygons
    idx = scene.affected_points()
    before = cube.world_points().copy()
    centre = scene.selection_center().copy()
    start = _quad_centre(canvas, "plane_x")
    assert canvas.gizmo_pick(start) == "plane_x"
    end = start + PLANE_OFFSET
    expected = _predicted_delta(canvas, centre, "plane_x", start, end)
    _drag(canvas, start, end)
    after = cube.world_points()
    assert np.allclose(after[idx] - before[idx], expected, atol=1e-6)
    others = [i for i in range(len(before)) if i not in idx]
    assert np.allclose(after[others], before[others])


def test_escape_and_right_click_cancel_plane_drag() -> None:
    for cancel in ("escape", "right"):
        canvas, scene = _make()
        obj = scene.active
        before = obj.world_position().copy()
        depth = len(scene._undo)
        start = _quad_centre(canvas, "plane_x")
        end = start + PLANE_OFFSET
        _drag(canvas, start, end, release=False)
        assert not np.allclose(obj.world_position(), before)
        if cancel == "escape":
            _key(canvas, Qt.Key.Key_Escape)
        else:
            _mouse(canvas, QEvent.Type.MouseButtonPress, end, RIGHT, RIGHT)
            _mouse(canvas, QEvent.Type.MouseButtonRelease, end, RIGHT, NO_BUTTON)
        assert np.allclose(obj.world_position(), before), cancel
        assert canvas._drag is None and scene._group_depth == 0 and len(scene._undo) == depth
        _mouse(canvas, QEvent.Type.MouseButtonRelease, end, LEFT, NO_BUTTON)
        assert np.allclose(obj.world_position(), before) and len(scene._undo) == depth


def test_plane_drag_cancel_in_polygons_mode_restores_points() -> None:
    canvas, scene = _make("polygons")
    _click(canvas, canvas.project_world([[0.0, 100.0, 0.0]])[0])
    obj = scene.active
    before = obj.world_points().copy()
    depth = len(scene._undo)
    start = _quad_centre(canvas, "plane_z")
    _drag(canvas, start, start + PLANE_OFFSET, release=False)
    assert not np.allclose(obj.world_points(), before)
    _key(canvas, Qt.Key.Key_Escape)
    assert np.allclose(obj.world_points(), before)
    assert len(scene._undo) == depth and scene._group_depth == 0


def test_edge_on_plane_handle_is_hidden_and_not_pickable() -> None:
    canvas, scene = _make()
    canvas.camera.heading = 0.0
    canvas.camera.pitch = -30.0
    handles = canvas.gizmo_plane_handles()
    assert "plane_x" not in handles and {"plane_y", "plane_z"} <= set(handles), handles.keys()
    centre = scene.selection_center()
    spot = canvas.project_world([centre + np.array([0.0, 60.0, 60.0])])[0]
    assert canvas.gizmo_pick(spot) != "plane_x"
    _mouse(canvas, QEvent.Type.MouseButtonPress, spot, LEFT, LEFT)
    assert canvas._drag is None or canvas._drag.handle != "plane_x"
    _mouse(canvas, QEvent.Type.MouseButtonRelease, spot, LEFT, NO_BUTTON)
    canvas.camera.heading = 0.0
    canvas.camera.pitch = 0.0
    assert set(canvas.gizmo_plane_handles()) == {"plane_z"}, canvas.gizmo_plane_handles().keys()


def test_axis_arrows_still_drag_one_axis_and_win_over_plane_handles() -> None:
    canvas, scene = _make()
    for axis in "xyz":
        before = scene.active.world_position().copy()
        a, b = (np.array(p) for p in canvas.gizmo_handles()[axis])
        start = a + 0.5 * (b - a)
        assert canvas.gizmo_hit(start) == axis
        _drag(canvas, start, start + 0.3 * (b - a))
        moved = scene.active.world_position() - before
        i = "xyz".index(axis)
        assert abs(moved[i]) > 1.0 and np.allclose(np.delete(moved, i), 0.0, atol=1e-6), (axis, moved)
        scene.undo()
    found = 0
    for heading, pitch in ((20.0, -20.0), (35.0, -15.0), (10.0, -45.0), (60.0, -10.0), (45.0, -35.0)):
        canvas.camera.heading, canvas.camera.pitch = heading, pitch
        geo = canvas._gizmo_geometry()
        for name, quad in geo["planes"].items():
            for u in np.linspace(0.0, 1.0, 11):
                for v in np.linspace(0.0, 1.0, 11):
                    pt = quad[0] + u * (quad[1] - quad[0]) + v * (quad[3] - quad[0])
                    near_axis = [a for a in "xyz" if a in geo and _seg_dist(pt, geo[a]) <= canvas.GIZMO_AXIS_FIRST_PX]
                    in_core = any(canvas._plane_inside(canvas._plane_core(q), pt[0], pt[1])
                                  for q in geo["planes"].values())
                    if near_axis and not in_core:
                        assert canvas.gizmo_hit(pt) in near_axis + ["center"], (name, near_axis)
                        found += 1
    assert found > 0, "no overlapping arrow and plane handle found in the sampled views"


def test_plane_handles_are_clickable_over_their_whole_area_not_only_beside_the_arrows() -> None:
    from PySide6.QtCore import QPointF, Qt as QtCore
    from PySide6.QtGui import QPolygonF

    canvas, scene = _make()
    canvas.parent().resize(1920, 1010)
    _settle(_app())
    assert scene.tool == "move"
    for heading, pitch in ((30.0, 30.0), (200.0, -25.0), (315.0, 30.0), (30.0, 10.0), (30.0, 11.0)):
        canvas.camera.heading, canvas.camera.pitch = heading, pitch
        geo = canvas._gizmo_geometry()
        for name, quad in geo["planes"].items():
            centre = quad.mean(axis=0)
            others = [q for n, q in geo["planes"].items() if n != name]
            if any(canvas._plane_inside(canvas._plane_core(q), centre[0], centre[1]) for q in others):
                continue
            assert canvas.gizmo_pick(centre) == name, (heading, pitch, name, canvas.gizmo_pick(centre))
            poly = QPolygonF([QPointF(float(a), float(b)) for a, b in quad])
            lo, hi = quad.min(axis=0), quad.max(axis=0)
            total = taken = 0
            for x in np.arange(lo[0], hi[0], 1.0):
                for y in np.arange(lo[1], hi[1], 1.0):
                    if poly.containsPoint(QPointF(x, y), QtCore.FillRule.OddEvenFill):
                        total += 1
                        taken += canvas.gizmo_pick((x, y)) == name
            assert total == 0 or taken / total >= 0.6, (heading, pitch, name, taken, total)


def test_plane_handle_centre_drag_moves_two_axes_at_the_reported_angles() -> None:
    canvas, scene = _make()
    canvas.parent().resize(1920, 1010)
    _settle(_app())
    for heading, pitch, name in ((30.0, 30.0, "plane_z"), (200.0, -25.0, "plane_z"), (315.0, 30.0, "plane_y")):
        canvas.camera.heading, canvas.camera.pitch = heading, pitch
        before = scene.active.world_position().copy()
        start = _quad_centre(canvas, name)
        assert canvas.gizmo_pick(start) == name, (heading, pitch, canvas.gizmo_pick(start))
        _drag(canvas, start, start + PLANE_OFFSET)
        moved = scene.active.world_position() - before
        assert np.count_nonzero(np.abs(moved) > 1.0) == 2, (heading, pitch, moved)
        assert scene.undo()


def test_other_tool_click_selects_object_and_switches_to_move() -> None:
    canvas, scene = _make()
    scene.set_tool("other")
    scene.clear_selection()
    assert scene.tool == "other" and not scene.object_selected
    _click(canvas, canvas.project_world([[0.0, 100.0, 0.0]])[0])
    assert scene.object_selected and scene.tool == "move", scene.tool
    assert canvas.hud_text == "Move"
    assert set(canvas.gizmo_handles()) == {"x", "y", "z"} and len(canvas.gizmo_plane_handles()) == 3
    assert canvas._drag is None


def test_object_manager_style_selection_falls_back_to_move() -> None:
    _canvas, scene = _make()
    scene.set_tool("other")
    scene.select_object(False)
    scene.set_active(scene.active)
    assert scene.tool == "move" and scene.object_selected
    other = scene.add_object("Second", activate=False)
    scene.set_tool("other")
    scene.set_active(other)
    assert scene.tool == "move" and scene.active is other


def test_active_tools_keep_their_behaviour_on_object_click() -> None:
    for tool in ("rotate", "scale", "select"):
        canvas, scene = _make()
        scene.set_tool(tool)
        scene.clear_selection()
        _click(canvas, canvas.project_world([[0.0, 100.0, 0.0]])[0])
        assert scene.object_selected and scene.tool == tool, (tool, scene.tool)


def test_empty_space_click_does_not_change_the_tool() -> None:
    canvas, scene = _make()
    scene.set_tool("other")
    _click(canvas, (6.0, 6.0))
    assert scene.tool == "other" and not scene.object_selected


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
