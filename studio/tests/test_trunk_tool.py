from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from quartz_studio import icons, theme
from quartz_studio.app import create_app
from quartz_studio.modeling import Selection, get_tool, run_tool, tool_ids
from quartz_studio.modeling.ops_trunk import preview_wire
from quartz_studio.scene import Mesh
from tests.test_trunk_skin import _check

LEFT = Qt.MouseButton.LeftButton
NO_MOD = Qt.KeyboardModifier.NoModifier

_STATE: dict = {}

PARAM_KEYS = ["sides", "base_radius", "tip_radius", "taper", "caps", "root", "thickness", "point_scale"]


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


def _settle():
    _window()
    for _ in range(5):
        _STATE["app"].processEvents()


def _setup(mesh: Mesh, mode: str, select=None, tool: str = "trunk"):
    win = _window()
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import get_scene

    scene = get_scene()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_object("Line", mesh)
    scene._undo.clear()
    scene._redo.clear()
    ctl = mi.controller()
    scene.set_tool("move")
    ctl.activate(None)
    ctl.new_transform()
    ctl.values.pop("trunk", None)
    scene.set_mode(mode)
    if select is not None:
        scene.select_components(list(select))
    if tool:
        mi.activate_tool(tool)
    _settle()
    return win, scene, win.viewport.canvas, ctl


class _Messages:

    def __init__(self, ctl) -> None:
        self.ctl = ctl
        self.items: list[str] = []
        ctl.message.connect(self.items.append)

    def close(self) -> None:
        self.ctl.message.disconnect(self.items.append)


def _chain(points) -> Mesh:
    pts = np.array(points, float)
    edges = [(i, i + 1) for i in range(len(pts) - 1)]
    return Mesh(pts, [], edges)


def _straight() -> Mesh:
    return _chain([(0, 0, 0), (0, 100, 0), (0, 200, 0), (0, 300, 0)])


def _branched() -> Mesh:
    pts = [(0, -120, 0), (0, 0, 0), (0, 100, 0), (0, 180, 0), (70, 280, 30), (-70, 270, -20),
           (60, 120, 0), (130, 190, 20)]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (3, 5), (2, 6), (6, 7)]
    return Mesh(pts, [], edges)


def _two_chains() -> Mesh:
    pts = [(-200, 0, 0), (-200, 100, 0), (-200, 200, 0), (100, 0, 0), (100, 100, 0), (100, 200, 0)]
    return Mesh(pts, [], [(0, 1), (1, 2), (3, 4), (4, 5)])


def _quad_and_chain() -> Mesh:
    pts = [(-100, 0, -100), (100, 0, -100), (100, 0, 100), (-100, 0, 100),
           (0, 50, 0), (0, 150, 0), (40, 250, 0)]
    return Mesh(pts, [(0, 1, 2, 3)], [(4, 5), (5, 6)])


def _params(**over) -> dict:
    values = get_tool("trunk").defaults()
    values.update(over)
    return values


def _run(mesh: Mesh, mode: str, items=(), **over):
    sel = Selection(mode)
    if mode == "points":
        sel.points = set(items)
    elif mode == "edges":
        sel.edges = {tuple(sorted(e)) for e in items}
    return run_tool("trunk", mesh, sel, _params(**over))


def _axis_radius(points: np.ndarray) -> np.ndarray:
    return np.hypot(points[:, 0], points[:, 2])


def _qp(xy) -> QPoint:
    return QPoint(int(round(xy[0])), int(round(xy[1])))


def _drag(canvas, a, b, steps: int = 6) -> None:
    QTest.mousePress(canvas, LEFT, NO_MOD, _qp(a))
    for k in range(1, steps + 1):
        t = k / steps
        QTest.mouseMove(canvas, _qp((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)))
    QTest.mouseRelease(canvas, LEFT, NO_MOD, _qp(b))
    _settle()


def _center(canvas) -> tuple[float, float]:
    r = canvas.rect().center()
    return float(r.x()), float(r.y())


def _overlay_image(overlay) -> QImage:
    img = QImage(overlay.size(), QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    overlay.render(img, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
    return img


def _overlay_pixels(overlay) -> np.ndarray:
    img = _overlay_image(overlay)
    h, w = img.height(), img.width()
    raw = np.frombuffer(img.constBits(), np.uint8, count=img.bytesPerLine() * h)
    return raw.reshape(h, img.bytesPerLine() // 4, 4)[:, :w].copy()


def _painted(overlay) -> int:
    return int((_overlay_pixels(overlay)[..., 3] > 0).sum())


def _entries(entries):
    for entry in entries:
        yield entry
        if isinstance(entry, tuple) and entry and entry[0] == "submenu":
            yield from _entries(entry[2])


def _action_texts(menu) -> list[str]:
    out = []
    for act in menu.actions():
        out.append(act.text().split("\t")[0])
        if act.menu() is not None:
            out.extend(_action_texts(act.menu()))
    return out


def test_registry_entry_and_params():
    spec = get_tool("trunk")
    assert "trunk" in tool_ids()
    assert spec.name == "Trunk" and spec.menu == "Mesh" and spec.section == "CREATION TOOLS"
    assert spec.modes == ("edges", "points") and spec.interactive
    assert spec.drag_param == "thickness" and spec.drag_kind == "percent"
    assert spec.shortcut == "M~R" and spec.icon is None
    assert spec.extra["drag_params"] == {"edges": "thickness", "points": "point_scale"}
    assert tuple(spec.extra["drag_from_default"]) == ("point_scale",)
    assert spec.extra["preview"] == "skin_wire"
    assert [p.key for p in spec.params] == PARAM_KEYS
    d = spec.defaults()
    assert d == {"sides": 8, "base_radius": 10.0, "tip_radius": 2.0, "taper": 1.0, "caps": True,
                 "root": "First Point", "thickness": 100.0, "point_scale": 100.0}
    assert (spec.param("sides").minimum, spec.param("sides").maximum) == (3, 64)
    assert (spec.param("taper").minimum, spec.param("taper").maximum) == (0.1, 10.0)
    assert spec.param("root").choices == ("First Point", "Lowest Point")
    assert spec.param("point_scale").modes == ("points",)
    assert all(not spec.param(k).modes for k in PARAM_KEYS if k != "point_scale")
    assert spec.clamp({"sides": 1000, "taper": 0.0})["sides"] == 64
    assert spec.clamp({"taper": 0.0})["taper"] == 0.1


def test_edges_mode_straight_line_radii_and_manifold():
    mesh = _straight()
    before = (mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges))
    res = _run(mesh, "edges")
    assert res.ok, res.message
    out = res.mesh
    assert not out.loose_edges
    assert len(out.points) == 4 * 8 and len(out.polygons) == 3 * 8 + 2
    assert _check(out.points, out.polygons, euler=[2]) == [2]
    radius = _axis_radius(out.points)
    assert abs(radius.max() - 10.0) < 1e-6 and abs(radius.min() - 2.0) < 1e-6
    assert np.allclose(sorted(set(np.round(out.points[:, 1], 6))), [0, 100, 200, 300])
    assert res.selection.mode == "edges" and not res.selection.edges
    assert np.array_equal(mesh.points, before[0]) and mesh.polygons == before[1]
    assert mesh.loose_edges == before[2]


def test_edges_mode_params_sides_thickness_caps_root_taper():
    out = _run(_straight(), "edges", sides=12).mesh
    assert len(out.points) == 4 * 12
    out = _run(_straight(), "edges", thickness=200.0).mesh
    radius = _axis_radius(out.points)
    assert abs(radius.max() - 20.0) < 1e-6 and abs(radius.min() - 4.0) < 1e-6
    capped = _run(_straight(), "edges", caps=True).mesh
    open_ = _run(_straight(), "edges", caps=False).mesh
    assert len(open_.polygons) == len(capped.polygons) - 2
    _check(open_.points, open_.polygons, caps=False)
    down = _chain([(0, 300, 0), (0, 200, 0), (0, 100, 0), (0, 0, 0)])
    first = _run(down, "edges", root="First Point").mesh
    lowest = _run(down, "edges", root="Lowest Point").mesh
    r_first = _axis_radius(first.points)[np.isclose(first.points[:, 1], 0.0)]
    r_lowest = _axis_radius(lowest.points)[np.isclose(lowest.points[:, 1], 0.0)]
    assert np.allclose(r_first, 2.0) and np.allclose(r_lowest, 10.0)
    thin = _run(_straight(), "edges", taper=4.0).mesh
    linear = _run(_straight(), "edges", taper=1.0).mesh
    mid_thin = _axis_radius(thin.points)[np.isclose(thin.points[:, 1], 100.0)].max()
    mid_linear = _axis_radius(linear.points)[np.isclose(linear.points[:, 1], 100.0)].max()
    assert mid_thin < mid_linear


def test_edges_mode_branched_line_is_one_closed_manifold():
    mesh = _branched()
    res = _run(mesh, "edges", sides=8)
    assert res.ok, res.message
    out = res.mesh
    assert not out.loose_edges and not any(len(p) < 3 for p in out.polygons)
    assert _check(out.points, out.polygons, euler=[2]) == [2]
    quads = sum(1 for p in out.polygons if len(p) == 4)
    assert quads > len(out.polygons) // 2
    for sides in (3, 5, 16):
        again = _run(mesh, "edges", sides=sides).mesh
        _check(again.points, again.polygons, euler=[2])


def test_edges_mode_partial_selection_keeps_the_rest():
    mesh = _two_chains()
    mesh.point_scales = [1.0, 2.0, 1.0, 1.0, 3.0, 1.0]
    res = _run(mesh, "edges", items=[(3, 4), (4, 5)])
    assert res.ok, res.message
    out = res.mesh
    assert out.loose_edges == [(0, 1), (1, 2)]
    assert np.array_equal(out.points[:3], mesh.points[:3])
    assert np.allclose(out.point_scale_array()[:3], [1.0, 2.0, 1.0])
    assert np.allclose(out.point_scale_array()[3:], 1.0)
    skin_pts = out.points[3:]
    skin = [tuple(i - 3 for i in p) for p in out.polygons]
    assert min(i for p in out.polygons for i in p) >= 3
    _check(skin_pts, skin, euler=[2])
    assert skin_pts[:, 0].min() > 50.0

    single = _run(mesh, "edges", items=[(3, 4)])
    assert single.ok
    kept = single.mesh
    assert kept.loose_edges == [(0, 1), (1, 2), (3, 4)]
    assert np.array_equal(kept.points[:5], mesh.points[[0, 1, 2, 4, 5]])
    assert np.allclose(kept.point_scale_array()[:5], [1.0, 2.0, 1.0, 3.0, 1.0])
    skin_pts = kept.points[5:]
    _check(skin_pts, [tuple(i - 5 for i in p) for p in kept.polygons], euler=[2])


def test_edges_mode_line_with_polygons_keeps_them():
    mesh = _quad_and_chain()
    res = _run(mesh, "edges")
    assert res.ok, res.message
    out = res.mesh
    assert out.polygons[0] == (0, 1, 2, 3)
    assert np.array_equal(out.points[:4], mesh.points[:4])
    assert not out.loose_edges
    skin_pts = out.points[4:]
    _check(skin_pts, [tuple(i - 4 for i in p) for p in out.polygons[1:]], euler=[2])
    assert skin_pts[:, 1].max() > 240.0


def test_edges_mode_unused_points_survive_and_skinned_points_go():
    mesh = _straight()
    mesh.add_point((500.0, 0.0, 0.0))
    out = _run(mesh, "edges").mesh
    assert np.allclose(out.points[0], [500.0, 0.0, 0.0])
    assert len(out.points) == 1 + 4 * 8
    assert not any(0 in p for p in out.polygons)


def test_edges_mode_point_scales_change_radii():
    mesh = _straight()
    mesh.point_scales = [1.0, 2.0, 1.0, 1.0]
    out = _run(mesh, "edges").mesh
    at = np.isclose(out.points[:, 1], 100.0)
    assert abs(_axis_radius(out.points)[at].max() - (10.0 - 8.0 / 3.0) * 2.0) < 1e-6
    assert np.allclose(out.point_scale_array(), 1.0)


def test_edges_mode_refusals():
    cube = run_tool("trunk", Mesh.cube(100.0), Selection("edges"), _params())
    assert not cube.ok and cube.message == "Trunk: the object has no loose edges"
    mixed = _quad_and_chain()
    poly_edge = run_tool("trunk", mixed, Selection("edges", edges={(0, 1)}), _params())
    assert not poly_edge.ok and poly_edge.message == "Trunk: select loose edges of a Line"
    zero = _run(_straight(), "edges", base_radius=0.0, tip_radius=0.0)
    assert not zero.ok and zero.message == "Trunk: Base Radius and Tip Radius are both 0"
    polygons = run_tool("trunk", _straight(), Selection("polygons"), _params())
    assert not polygons.ok and "does not work" in polygons.message
    segment = _chain([(0, 0, 0), (0, 100, 0)])
    segment.point_scales = [0.0, 0.0]
    empty = _run(segment, "edges")
    assert not empty.ok and empty.message == "Trunk: the radii leave nothing to skin"
    assert segment.loose_edges == [(0, 1)]


def test_points_mode_scales_only_selected_points_and_stays_a_line():
    mesh = _branched()
    res = _run(mesh, "points", items=[2, 3], point_scale=150.0)
    assert res.ok, res.message
    out = res.mesh
    assert np.array_equal(out.points, mesh.points)
    assert out.polygons == [] and out.loose_edges == mesh.loose_edges
    scales = out.point_scale_array()
    expect = np.ones(len(mesh.points))
    expect[[2, 3]] = 1.5
    assert np.allclose(scales, expect)
    assert mesh.point_scales is None
    again = _run(out, "points", items=[3, 6], point_scale=200.0).mesh.point_scale_array()
    assert np.allclose(again[[2, 3, 6]], [1.5, 3.0, 2.0])
    assert res.selection.points == {2, 3}


def test_points_mode_refusals():
    cube = run_tool("trunk", Mesh.cube(100.0), Selection("points", points={0}), _params())
    assert not cube.ok and cube.message == "Trunk: the object has no loose edges"
    none = _run(_straight(), "points")
    assert not none.ok and none.message == "Trunk: select points to scale their thickness"
    outside = _run(_straight(), "points", items=[99])
    assert not outside.ok and outside.message == "Trunk: select points to scale their thickness"


def test_session_edges_mode_undo_restores_the_line():
    win, scene, canvas, ctl = _setup(_branched(), "edges")
    base_pts = scene.active.mesh.points.copy()
    base_loose = list(scene.active.mesh.loose_edges)
    steps = len(scene._undo)
    assert ctl.begin() is not None
    result = ctl.apply_live({})
    assert result is not None and result.ok
    ctl.new_transform()
    assert len(scene._undo) == steps + 1
    mesh = scene.active.mesh
    assert mesh.polygons and not mesh.loose_edges
    _check(mesh.points, mesh.polygons, euler=[2])
    assert scene.undo()
    mesh = scene.active.mesh
    assert np.array_equal(mesh.points, base_pts) and mesh.loose_edges == base_loose
    assert mesh.polygons == []
    assert scene.redo()
    assert scene.active.mesh.polygons and not scene.active.mesh.loose_edges


def test_session_live_reapply_with_other_params_is_one_undo_step():
    win, scene, canvas, ctl = _setup(_branched(), "edges")
    base_pts = scene.active.mesh.points.copy()
    steps = len(scene._undo)
    assert ctl.begin() is not None
    ctl.apply_live({})
    small = len(scene.active.mesh.points)
    ctl.set_param("sides", 14)
    big = len(scene.active.mesh.points)
    assert big > small
    ctl.set_param("thickness", 300.0)
    assert len(scene._undo) == steps + 1
    _check(scene.active.mesh.points, scene.active.mesh.polygons, euler=[2])
    assert not scene.active.mesh.loose_edges
    ctl.set_param("sides", 8)
    assert len(scene.active.mesh.points) == small
    ctl.cancel()
    assert np.array_equal(scene.active.mesh.points, base_pts)
    assert scene.active.mesh.loose_edges and len(scene._undo) == steps


def test_viewport_drag_in_edges_mode_sets_thickness():
    win, scene, canvas, ctl = _setup(_straight(), "edges")
    x, y = _center(canvas)
    steps = len(scene._undo)
    _drag(canvas, (x, y), (x + 40, y))
    assert abs(ctl.params()["thickness"] - 120.0) < 1e-6
    mesh = scene.active.mesh
    assert not mesh.loose_edges and len(scene._undo) == steps + 1
    radius = _axis_radius(mesh.points)
    assert abs(radius.max() - 12.0) < 1e-6 and abs(radius.min() - 2.4) < 1e-6
    assert scene.mode == "edges"


def test_viewport_drag_in_points_mode_scales_selected_and_undoes():
    win, scene, canvas, ctl = _setup(_branched(), "points", select=[2, 3])
    x, y = _center(canvas)
    steps = len(scene._undo)
    _drag(canvas, (x, y), (x + 60, y))
    mesh = scene.active.mesh
    assert mesh.polygons == [] and mesh.loose_edges == _branched().loose_edges
    scales = mesh.point_scale_array()
    assert np.allclose(scales[[2, 3]], 1.3)
    assert np.allclose(np.delete(scales, [2, 3]), 1.0)
    assert len(scene._undo) == steps + 1
    assert scene.selected_points == {2, 3} and scene.mode == "points"
    _drag(canvas, (x, y), (x + 60, y))
    scales = scene.active.mesh.point_scale_array()
    assert np.allclose(scales[[2, 3]], 1.69)
    assert len(scene._undo) == steps + 2
    assert scene.undo()
    assert np.allclose(scene.active.mesh.point_scale_array()[[2, 3]], 1.3)
    assert scene.undo()
    assert scene.active.mesh.point_scales is None
    assert scene.active.mesh.loose_edges == _branched().loose_edges


def test_viewport_drag_without_points_refuses():
    win, scene, canvas, ctl = _setup(_branched(), "points")
    msgs = _Messages(ctl)
    try:
        x, y = _center(canvas)
        steps = len(scene._undo)
        _drag(canvas, (x, y), (x + 50, y))
        assert "Trunk: select points to scale their thickness" in msgs.items
        assert scene.active.mesh.point_scales is None and len(scene._undo) == steps
    finally:
        msgs.close()


def test_not_editable_object_is_refused():
    win, scene, canvas, ctl = _setup(_straight(), "edges", tool=None)
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_parametric("cube")
    from quartz_studio.modeling import install as mi

    msgs = _Messages(ctl)
    try:
        mi.activate_tool("trunk")
        _settle()
        assert msgs.items == ["Trunk: Make Editable first"], msgs.items
        assert ctl.tool_id is None
    finally:
        msgs.close()


def test_mesh_without_loose_edges_is_refused_in_the_viewport():
    win, scene, canvas, ctl = _setup(Mesh.cube(100.0), "edges", select=[(0, 1)])
    msgs = _Messages(ctl)
    try:
        x, y = _center(canvas)
        _drag(canvas, (x, y), (x + 40, y))
        assert "Trunk: the object has no loose edges" in msgs.items
        assert len(scene.active.mesh.points) == 8
    finally:
        msgs.close()


def test_preview_appears_follows_the_inputs_and_disappears():
    win, scene, canvas, ctl = _setup(_branched(), "points", select=[2])
    overlay = win.modeling_filter.overlay
    assert overlay.preview_wire is not None
    pts, edges = overlay.preview_wire
    assert pts.ndim == 2 and pts.shape[1] == 3 and edges.ndim == 2 and edges.shape[1] == 2
    assert len(edges) > 0 and edges.min() >= 0 and edges.max() < len(pts)
    want_pts, want_edges = preview_wire(scene.active.mesh, ctl.params())
    assert np.allclose(pts, scene.active.to_world(want_pts)) and np.array_equal(edges, want_edges)
    assert _painted(overlay) > 50
    first = pts.copy()

    ctl.set_param("sides", 12)
    _settle()
    assert len(overlay.preview_wire[0]) > len(first)
    ctl.set_param("sides", 8)
    _settle()
    assert np.allclose(overlay.preview_wire[0], first)

    scene.active.mesh.points[3] += (25.0, 0.0, 0.0)
    scene.changed.emit()
    _settle()
    assert not np.allclose(overlay.preview_wire[0], first)
    scene.active.mesh.points[3] -= (25.0, 0.0, 0.0)
    scene.changed.emit()
    _settle()
    assert np.allclose(overlay.preview_wire[0], first)

    assert scene.multiply_point_scales([2], 2.0)
    _settle()
    scaled = overlay.preview_wire[0].copy()
    assert not np.allclose(scaled, first)
    assert scene.undo()
    _settle()
    assert np.allclose(overlay.preview_wire[0], first)

    scene.set_mode("edges")
    _settle()
    assert overlay.preview_wire is None and _painted(overlay) == 0
    scene.set_mode("points")
    _settle()
    assert overlay.preview_wire is not None
    scene.set_tool("move")
    _settle()
    assert overlay.preview_wire is None and _painted(overlay) == 0


def test_preview_hides_for_another_object_and_returns():
    win, scene, canvas, ctl = _setup(_branched(), "points", select=[2])
    overlay = win.modeling_filter.overlay
    line = scene.active
    assert overlay.preview_wire is not None
    scene.add_object("Other", Mesh.cube(100.0))
    _settle()
    assert overlay.preview_wire is None
    scene.set_active(line)
    _settle()
    assert overlay.preview_wire is not None
    for obj in list(scene.objects):
        if obj is not line:
            scene.remove_object(obj)
    _settle()
    assert overlay.preview_wire is not None


def test_preview_uses_the_theme_color_and_the_object_transform():
    win, scene, canvas, ctl = _setup(_branched(), "points", select=[2])
    overlay = win.modeling_filter.overlay
    from quartz_studio.modeling import interaction

    assert interaction.PREVIEW_COLOR == theme.SELECT_FRONT_SOFT
    before = overlay.preview_wire[0].copy()
    scene.active.position = np.array([40.0, 0.0, 0.0])
    scene.changed.emit()
    _settle()
    assert np.allclose(overlay.preview_wire[0], before + np.array([40.0, 0.0, 0.0]))
    pixels = _overlay_pixels(overlay)
    solid = pixels[pixels[..., 3] >= 200]
    assert len(solid) > 20
    want = QColor(theme.SELECT_FRONT_SOFT)
    distance = (np.abs(solid[:, 2].astype(int) - want.red()) + np.abs(solid[:, 1].astype(int) - want.green())
                + np.abs(solid[:, 0].astype(int) - want.blue()))
    assert int(distance.min()) <= 12, int(distance.min())


def test_preview_is_skipped_on_very_large_lines_with_a_message():
    from quartz_studio.modeling import install as mi
    from quartz_studio.modeling.interaction import SKIN_PREVIEW_BUDGET

    msgs = _Messages(mi.controller())
    try:
        n = SKIN_PREVIEW_BUDGET + 50
        pts = [(0.0, 3.0 * i, 0.0) for i in range(n)]
        win, scene, canvas, ctl = _setup(_chain(pts), "points", select=[1])
        overlay = win.modeling_filter.overlay
        assert overlay.preview_wire is None
        skipped = [m for m in msgs.items if "preview skipped" in m]
        assert len(skipped) == 1, msgs.items
        ctl.set_param("sides", 6)
        _settle()
        assert overlay.preview_wire is None
        assert len([m for m in msgs.items if "preview skipped" in m]) == 1
    finally:
        msgs.close()


def test_no_preview_for_other_tools_or_without_loose_edges():
    win, scene, canvas, ctl = _setup(Mesh.cube(100.0), "points", select=[0])
    assert win.modeling_filter.overlay.preview_wire is None
    win, scene, canvas, ctl = _setup(_branched(), "points", select=[2], tool="extrude")
    assert win.modeling_filter.overlay.preview_wire is None


def test_tool_is_in_the_mesh_menu_with_its_shortcut():
    _window()
    from quartz_studio.widgets import menu_bar as mb
    from quartz_studio.widgets import menus_data as md

    mesh_menu = next(entries for title, entries, _style in md.MENU_BAR if title == "Mesh")
    items = [e for e in _entries(mesh_menu) if isinstance(e, tuple) and e and e[0] == "item"
             and e[1] == "Trunk"]
    assert len(items) == 1 and items[0][2] == "M~R"
    assert any(path == ("Mesh", "Trunk") for path, _fn in mb.SCENE_COMMANDS)


def test_tool_has_a_rail_button_in_the_extrude_foldout():
    win = _window()
    from quartz_studio.modeling import install as mi
    from quartz_studio.modeling.install import PALETTE_GROUPS, palette_groups

    table = dict(PALETTE_GROUPS)["Extrude"]
    assert table[-2:] == ("thicken", "trunk")
    group = next(g for g in palette_groups() if g.name == "Extrude")
    assert [s.id for s in group.specs][-2:] == ["thicken", "trunk"]
    button = win.tool_palette.buttons["Extrude"]
    menu = button.build_menu()
    try:
        names = [a.text() for a in menu.actions()]
        assert names.index("Trunk") == names.index("Thicken") + 1
        action = next(a for a in menu.actions() if a.text() == "Trunk")
        assert not action.icon().isNull()
        from quartz_studio.scene import get_scene

        get_scene().set_mode("points")
        action.trigger()
        _settle()
        assert get_scene().tool == "trunk" and mi.controller().tool_id == "trunk"
    finally:
        menu.deleteLater()


def test_tool_is_in_the_points_and_edges_context_menus_only():
    win, scene, canvas, ctl = _setup(_branched(), "points", tool=None)
    from quartz_studio.widgets.context_menu import build_component_menu

    for mode, expected in (("points", True), ("edges", True), ("polygons", False)):
        scene.set_mode(mode)
        menu = build_component_menu(scene, canvas)
        texts = _action_texts(menu)
        assert ("Trunk" in texts) == expected, (mode, texts)
        menu.deleteLater()


def test_activating_from_the_model_mode_switches_to_edges():
    win, scene, canvas, ctl = _setup(_branched(), "model", tool=None)
    from quartz_studio.modeling import install as mi

    mi.activate_tool("trunk")
    _settle()
    assert scene.mode == "edges" and scene.tool == "trunk"


def test_status_bar_hints_per_mode():
    from quartz_studio.widgets import status_bar as sb

    assert sb.tool_hint("trunk", "edges") == sb.MODE_HINTS[("trunk", "edges")]
    assert sb.tool_hint("trunk", "points") == sb.MODE_HINTS[("trunk", "points")]
    assert "Thickness" in sb.tool_hint("trunk", "edges") and "Apply" in sb.tool_hint("trunk", "edges")
    assert "scale their thickness" in sb.tool_hint("trunk", "points")
    assert sb.tool_hint("trunk", "polygons") == sb.modeling_hint(get_tool("trunk"))
    assert sb.tool_hint("extrude", "points") == sb.modeling_hint(get_tool("extrude"))
    win, scene, canvas, ctl = _setup(_branched(), "points", select=[1])
    left, hint, _sel = sb.status_texts(scene)
    assert "Trunk" in left and hint == sb.MODE_HINTS[("trunk", "points")]


def test_icons_exist_render_and_are_distinct():
    from PySide6.QtGui import QImage

    _window()
    assert icons.has("mt_trunk") and icons.has("trunk")
    assert icons.modeling_icon_name("trunk") == "mt_trunk"
    assert icons.family_tint("mt_trunk") == theme.TINT_CITRINE
    assert icons.family_tint("trunk") == theme.TINT_AMETHYST

    def image(name: str, size: int) -> QImage:
        return icons.pixmap(name, size).toImage()

    for name in ("mt_trunk", "trunk"):
        for size in (16, 24, 48):
            img = image(name, size)
            lit = sum(1 for y in range(img.height()) for x in range(img.width())
                      if QColor.fromRgba(img.pixel(x, y)).alpha() > 40)
            assert size < lit < size * size * 0.8, (name, size, lit)
    assert image("mt_trunk", 48) != image("trunk", 48)
    for other in icons.names():
        if other in ("mt_trunk", "trunk"):
            continue
        assert image(other, 24) != image("mt_trunk", 24), other
        assert image(other, 24) != image("trunk", 24), other


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
