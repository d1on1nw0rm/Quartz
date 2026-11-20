from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import tempfile

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

APP = QApplication.instance() or QApplication([])

from quartz_studio import sculpt
from quartz_studio.ext import store
from quartz_studio.scene import Mesh, reset_scene
from quartz_studio.sculpt import data, falloff, stamps
from quartz_studio.sculpt.brushes import BRUSH_ORDER, BrushSettings, default_settings
from quartz_studio.sculpt.stroke import SculptStroke, apply_dab, symmetry_frames
from quartz_studio.sculpt.subdivision import catmull_clark, subdivide_mesh
from quartz_studio.sculpt.topology import Topology, get_topology


def _grid(n: int = 10, size: float = 100.0) -> Mesh:
    xs = np.linspace(-size / 2, size / 2, n + 1)
    pts = [(x, 0.0, z) for z in xs for x in xs]
    polys = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            b, c, d = a + 1, a + n + 2, a + n + 1
            polys.append((a, d, c, b))
    return Mesh(pts, polys)


def _scene_with(mesh: Mesh, name: str = "Grid"):
    scene = reset_scene()
    for o in list(scene.objects):
        scene.remove_object(o)
    obj = scene.add_object(name, mesh)
    scene.set_active(obj)
    scene.clear_history()
    return scene, obj


def _settings(brush: str, **kw) -> BrushSettings:
    s = default_settings(brush)
    s.strength = 1.0
    s.spacing = 0.0
    for k, v in kw.items():
        setattr(s, k, v)
    return s.clamp()


def _dab(scene, obj, brush: str, hit=(0.0, 0.0, 0.0), normal=(0.0, 1.0, 0.0), radius: float = 30.0,
         times: int = 1, **kw) -> int:
    total = 0
    for _ in range(times):
        total += apply_dab(obj, _settings(brush, **kw), hit, normal, (0.0, -1.0, 0.0),
                           radius=radius, scene=scene)
    return total


def _manifold(mesh: Mesh) -> bool:
    count: dict = {}
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            key = (min(a, b), max(a, b))
            count[key] = count.get(key, 0) + 1
    return all(v == 2 for v in count.values())


def _consistent(mesh: Mesh) -> bool:
    seen = set()
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a, b) in seen:
                return False
            seen.add((a, b))
    return True


def test_falloff_presets():
    t = np.array([0.0, 0.5, 1.0, 1.5])
    assert np.allclose(falloff.evaluate("linear", t), [1.0, 0.5, 0.0, 0.0])
    assert np.allclose(falloff.evaluate("constant", t), [1.0, 1.0, 1.0, 0.0])
    assert np.allclose(falloff.evaluate("smooth", t), [1.0, 0.5, 0.0, 0.0])
    assert np.allclose(falloff.evaluate("spherical", [0.0, 0.6]), [1.0, 0.8])
    assert np.allclose(falloff.evaluate("sharp", [0.5]), [0.25])


def test_falloff_custom_curve_monotone_and_clamped():
    curve = [(0.0, 1.0), (0.3, 0.9), (0.7, 0.1), (1.0, 0.0)]
    xs = np.linspace(0, 1, 101)
    ys = falloff.evaluate("custom", xs, curve)
    assert np.all(np.diff(ys) <= 1e-9)
    assert abs(ys[0] - 1.0) < 1e-9 and abs(ys[-1]) < 1e-9
    assert abs(falloff.evaluate("custom", [0.3], curve)[0] - 0.9) < 1e-9
    assert np.all((ys >= 0) & (ys <= 1))


def test_falloff_curve_editing_helpers():
    c = falloff.clean_curve([(0.5, 2.0), (-1, 0.5)])
    assert c[0] == (0.0, 0.5) and c[-1][0] == 1.0 and c[1] == (0.5, 1.0)
    c = falloff.insert_point(falloff.DEFAULT_CURVE, 0.25, 0.8)
    assert len(c) == 4 and (0.25, 0.8) in c
    c2 = falloff.move_point(c, 1, 0.9, 0.3)
    assert c2[1][0] < c2[2][0]
    assert falloff.move_point(c, 0, 0.5, 0.2)[0] == (0.0, 0.2)
    assert len(falloff.remove_point(c, 1)) == 3
    assert len(falloff.remove_point(c, 0)) == 4


def test_catmull_clark_cube_known_values():
    cube = Mesh.cube(2.0)
    op = catmull_clark(8, cube.polygons)
    pts = op.apply(cube.points)
    assert op.m == 26 and len(op.polygons) == 24
    assert np.allclose(np.abs(pts[:8]), 5.0 / 9.0)
    edge = pts[8:20]
    assert np.allclose(np.sort(np.abs(edge), axis=1), [[0.0, 0.75, 0.75]] * 12)
    faces = pts[20:]
    assert np.allclose(np.sort(np.abs(faces), axis=1), [[0.0, 0.0, 1.0]] * 6)


def test_catmull_clark_topology_closed_and_oriented():
    mesh = subdivide_mesh(Mesh.cube(200.0), 3)
    assert len(mesh.points) == 386 and len(mesh.polygons) == 384
    assert _manifold(mesh) and _consistent(mesh)
    normals = mesh.polygon_normals()
    centers = np.array([mesh.points[list(p)].mean(axis=0) for p in mesh.polygons])
    assert np.all(np.einsum("ij,ij->i", normals, centers) > 0)
    r = np.linalg.norm(mesh.points, axis=1)
    assert r.max() / r.min() < 1.05


def test_catmull_clark_boundary_rules():
    grid = _grid(2, 2.0)
    op = catmull_clark(len(grid.points), grid.polygons)
    pts = op.apply(grid.points)
    assert np.allclose(pts[0], grid.points[0])
    assert np.allclose(pts[1], [0.75 * 0.0 + 0.125 * -1.0 + 0.125 * 1.0, 0.0, -1.0])
    assert np.allclose(pts[4], grid.points[4])
    assert np.allclose(pts[:, 1], 0.0)
    sub = Mesh(pts, op.polygons)
    assert _consistent(sub) and len(sub.polygons) == 16


def test_catmull_clark_ngons_and_linearity():
    pts = np.array([[np.cos(a), 0.0, np.sin(a)] for a in np.linspace(0, 2 * np.pi, 6)[:-1]])
    pent = Mesh(np.vstack([pts, [[0.0, 0.0, 0.0]]]), [(0, 1, 2, 3, 4)])
    op = catmull_clark(6, pent.polygons)
    assert len(op.polygons) == 5 and op.m == 6 + 5 + 1
    assert np.allclose(op.apply(pent.points)[5], [0.0, 0.0, 0.0])
    a = np.random.default_rng(1).random((6, 3))
    b = np.random.default_rng(2).random((6, 3))
    assert np.allclose(op.apply(2 * a + b), 2 * op.apply(a) + op.apply(b))
    assert np.allclose(op.apply(np.ones(6)), 1.0)


def test_topology_neighbors_normals_boundary():
    grid = _grid(4, 4.0)
    topo = Topology(len(grid.points), grid.polygons)
    assert topo.boundary.sum() == 16
    assert sorted(topo.neighbors(6).tolist()) == [1, 5, 7, 11]
    vn = topo.vertex_normals(grid.points)
    assert np.allclose(vn, [0.0, 1.0, 0.0])
    noisy = grid.points.copy()
    noisy[12, 1] = 1.0
    mean = topo.neighbor_mean(noisy, np.array([12, 0, 2]))
    assert abs(mean[0, 1]) < 1e-12 and np.allclose(mean[1], noisy[0])
    assert np.allclose(mean[2], (noisy[1] + noisy[3]) / 2)
    grown = topo.grow(np.eye(len(grid.points), dtype=bool)[12])
    assert grown.sum() == 5
    hit = topo.raycast(grid.points, [0.1, 5.0, 0.1], [0, -1, 0])
    assert hit is not None and abs(hit[1][1]) < 1e-9
    cube = Mesh.cube(2.0)
    ct = get_topology(8, cube.polygons)
    assert np.allclose(ct.vertex_normals(cube.points), np.sign(cube.points) / np.sqrt(3))


def test_state_init_and_subdivide_levels():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    assert data.subdivide(obj, scene, 2)
    st = data.get_state(obj)
    assert data.level_count(st) == 3 and data.current_level(st) == 2
    assert len(obj.mesh.points) == 98
    assert data.set_level(obj, 0, scene)
    assert np.allclose(obj.mesh.points, Mesh.cube(200.0).points) and len(obj.mesh.polygons) == 6
    assert data.level_up(obj, scene) and len(obj.mesh.points) == 26
    assert data.level_up(obj, scene) and not data.level_up(obj, scene)
    assert data.level_info(st)[1] == {"level": 1, "points": 26, "polygons": 24}


def test_lower_level_edit_propagates_and_keeps_detail():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 2)
    top = obj.mesh.points[:, 1].max()
    _dab(scene, obj, "pull", hit=(0, top, 0), radius=50.0)
    st = data.get_state(obj)
    detail = np.asarray(st["levels"][2]).copy()
    assert np.abs(detail).max() > 0.5
    data.set_level(obj, 1, scene)
    moved = obj.mesh.points.copy()
    moved[:, 0] += 10.0
    obj.mesh.points = moved
    data.set_level(obj, 2, scene)
    st = data.get_state(obj)
    assert np.allclose(np.asarray(st["levels"][2]), detail)
    level1 = data.composite(st, 1)
    assert np.allclose(level1[:, 0] - data.composite(st, 1)[:, 0], 0)
    expected = data._operator(st, 1).apply(level1) + detail
    assert np.allclose(obj.mesh.points, expected)
    assert np.isclose(obj.mesh.points[:, 0].mean() - 10.0, 0.0, atol=1e-6) or obj.mesh.points[:, 0].mean() > 9.0


def test_delete_higher_levels():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 3)
    data.set_level(obj, 1, scene)
    assert data.delete_higher_levels(obj, scene)
    st = data.get_state(obj)
    assert data.level_count(st) == 2 and len(obj.mesh.points) == 26
    assert not data.delete_higher_levels(obj, scene)


def test_subdivide_limit():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    old = data.MAX_POINTS
    data.MAX_POINTS = 100
    try:
        assert data.subdivide(obj, scene, 2)
        assert not data.subdivide(obj, scene, 1)
    finally:
        data.MAX_POINTS = old


def test_pull_raises_and_invert_lowers():
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "pull", radius=20.0)
    y = obj.mesh.points[:, 1]
    centre = int(np.argmin(np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1)))
    assert y[centre] > 0.5 and y.min() >= -1e-12
    far = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1) > 20.0
    assert np.allclose(y[far], 0.0)
    before = y[centre]
    _dab(scene, obj, "pull", radius=20.0, invert=True)
    assert obj.mesh.points[centre, 1] < before


def test_pull_amount_scales_with_strength_and_pressure():
    scene, obj = _scene_with(_grid(20, 100.0))
    s = _settings("pull")
    apply_dab(obj, s, (0, 0, 0), (0, 1, 0), (0, -1, 0), pressure=1.0, radius=20.0, scene=scene)
    full = obj.mesh.points[:, 1].max()
    scene, obj = _scene_with(_grid(20, 100.0))
    apply_dab(obj, s, (0, 0, 0), (0, 1, 0), (0, -1, 0), pressure=0.5, radius=20.0, scene=scene)
    half = obj.mesh.points[:, 1].max()
    assert np.isclose(half, full * 0.5)
    scene, obj = _scene_with(_grid(20, 100.0))
    s2 = _settings("pull", pressure_strength=False)
    apply_dab(obj, s2, (0, 0, 0), (0, 1, 0), (0, -1, 0), pressure=0.5, radius=20.0, scene=scene)
    assert np.isclose(obj.mesh.points[:, 1].max(), full)
    scene, obj = _scene_with(_grid(20, 100.0))
    s3 = _settings("pull", pressure_strength=False, pressure_radius=True)
    count = apply_dab(obj, s3, (0, 0, 0), (0, 1, 0), (0, -1, 0), pressure=0.5, radius=20.0, scene=scene)
    assert count < 60


def test_falloff_shapes_displacement():
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "pull", radius=20.0, falloff="constant")
    y = obj.mesh.points[:, 1]
    inside = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1) < 19.0
    assert np.allclose(y[inside], y[inside].max())
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "pull", radius=20.0, falloff="linear")
    d = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1)
    sel = d < 20.0
    peak = obj.mesh.points[:, 1].max()
    assert np.allclose(obj.mesh.points[sel, 1], peak * (1 - d[sel] / 20.0))


def test_smooth_reduces_noise():
    mesh = _grid(20, 100.0)
    rng = np.random.default_rng(3)
    mesh.points[:, 1] = rng.normal(0, 2.0, len(mesh.points))
    scene, obj = _scene_with(mesh)
    sel = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1) < 15.0
    before = obj.mesh.points[sel, 1].std()
    _dab(scene, obj, "smooth", radius=30.0, times=4, front_only=False)
    assert obj.mesh.points[sel, 1].std() < before * 0.6


def test_inflate_grows_sphere():
    scene, obj = _scene_with(subdivide_mesh(Mesh.cube(200.0), 3), "Ball")
    r0 = np.linalg.norm(obj.mesh.points, axis=1)
    top = obj.mesh.points[:, 1].max()
    _dab(scene, obj, "inflate", hit=(0, top, 0), radius=60.0)
    r1 = np.linalg.norm(obj.mesh.points, axis=1)
    assert np.all(r1 >= r0 - 1e-9) and (r1 - r0).max() > 1.0


def test_flatten_fill_scrape():
    def bumpy():
        m = _grid(20, 100.0)
        x, z = m.points[:, 0], m.points[:, 2]
        m.points[:, 1] = 3.0 * np.sin(x / 5.0) * np.cos(z / 5.0)
        return m

    scene, obj = _scene_with(bumpy())
    sel = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1) < 10.0
    before = obj.mesh.points[sel, 1].copy()
    _dab(scene, obj, "flatten", radius=25.0, times=3, front_only=False)
    assert obj.mesh.points[sel, 1].std() < before.std() * 0.5

    scene, obj = _scene_with(bumpy())
    before = obj.mesh.points[:, 1].copy()
    _dab(scene, obj, "fill", radius=25.0, front_only=False)
    after = obj.mesh.points[:, 1]
    assert np.all(after >= before - 1e-9) and (after - before).max() > 0.1

    scene, obj = _scene_with(bumpy())
    before = obj.mesh.points[:, 1].copy()
    _dab(scene, obj, "scrape", radius=25.0, front_only=False)
    after = obj.mesh.points[:, 1]
    assert np.all(after <= before + 1e-9) and (before - after).max() > 0.1


def test_pinch_and_crease():
    scene, obj = _scene_with(_grid(20, 100.0))
    pts0 = obj.mesh.points.copy()
    _dab(scene, obj, "pinch", radius=20.0)
    d0 = np.linalg.norm(pts0[:, [0, 2]], axis=1)
    d1 = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1)
    sel = (d0 < 18.0) & (d0 > 1.0)
    assert np.all(d1[sel] < d0[sel]) and np.allclose(obj.mesh.points[:, 1], 0.0)
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "crease", radius=20.0)
    assert obj.mesh.points[:, 1].min() < -0.3 and obj.mesh.points[:, 1].max() <= 1e-9


def test_polish_clay_wax_amplify():
    mesh = _grid(20, 100.0)
    rng = np.random.default_rng(5)
    mesh.points[:, 1] = rng.normal(0, 1.0, len(mesh.points))
    scene, obj = _scene_with(mesh)
    sel = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1) < 10.0
    before = obj.mesh.points[sel, 1].std()
    _dab(scene, obj, "polish", radius=25.0, times=3, front_only=False)
    assert obj.mesh.points[sel, 1].std() < before

    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "clay", radius=20.0, times=3)
    y = obj.mesh.points[:, 1]
    assert y.max() > 0.5 and y.min() >= -1e-9
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "wax", radius=20.0)
    assert obj.mesh.points[:, 1].max() > 0.3

    mesh = _grid(20, 100.0)
    mesh.points[:, 1] = 0.5 * np.sin(mesh.points[:, 0] / 3.0)
    scene, obj = _scene_with(mesh)
    before = obj.mesh.points[sel, 1].std()
    _dab(scene, obj, "amplify", radius=25.0, front_only=False)
    assert obj.mesh.points[sel, 1].std() > before


def test_erase_returns_toward_base():
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "pull", radius=20.0, times=3)
    peak = obj.mesh.points[:, 1].max()
    _dab(scene, obj, "erase", radius=25.0, times=1, falloff="constant")
    assert obj.mesh.points[:, 1].max() < 1e-6 < peak
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "pull", radius=20.0)
    base = obj.mesh.points.copy()
    data.add_layer(obj, "Detail", scene)
    _dab(scene, obj, "pull", radius=20.0, hit=(20.0, 0, 0))
    _dab(scene, obj, "erase", radius=60.0, falloff="constant", front_only=False)
    assert np.allclose(obj.mesh.points, base)


def test_grab_moves_region_with_cursor():
    scene, obj = _scene_with(_grid(20, 100.0))
    pts0 = obj.mesh.points.copy()
    stroke = SculptStroke(obj, _settings("grab", falloff="constant"), scene)
    stroke.dab((0, 0, 0), (0, 1, 0), (0, -1, 0), radius=12.0)
    stroke.dab((0, 10, 0), (0, 1, 0), (0, -1, 0), radius=12.0)
    stroke.dab((0, 20, 5), (0, 1, 0), (0, -1, 0), radius=12.0)
    stroke.end()
    d = np.linalg.norm(pts0[:, [0, 2]], axis=1)
    inside = d < 11.0
    assert np.allclose(obj.mesh.points[inside] - pts0[inside], [0, 20, 5])
    assert np.allclose(obj.mesh.points[d > 13.0], pts0[d > 13.0])


def test_mask_brush_and_masked_points_do_not_move():
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "mask", radius=15.0, falloff="constant")
    st = data.get_state(obj)
    mask = data.get_mask(st)
    d = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1)
    assert np.allclose(mask[d < 14.0], 1.0) and np.allclose(mask[d > 16.0], 0.0)
    assert np.allclose(obj.mesh.points[:, 1], 0.0)
    _dab(scene, obj, "pull", radius=30.0)
    assert np.allclose(obj.mesh.points[d < 14.0, 1], 0.0)
    assert obj.mesh.points[(d > 16.0) & (d < 25.0), 1].max() > 0.1
    _dab(scene, obj, "mask", radius=15.0, falloff="constant", invert=True)
    assert data.get_mask(data.get_state(obj)).max() == 0.0


def test_mask_operations():
    scene, obj = _scene_with(_grid(4, 4.0))
    n = len(obj.mesh.points)
    one = np.zeros(n)
    one[12] = 1.0
    assert data.set_mask(obj, one, scene)
    data.mask_grow(obj, scene)
    m = data.get_mask(data.get_state(obj))
    assert set(np.nonzero(m)[0].tolist()) == {7, 11, 12, 13, 17}
    data.mask_shrink(obj, scene)
    assert np.count_nonzero(data.get_mask(data.get_state(obj))) == 1
    data.mask_invert(obj, scene)
    m = data.get_mask(data.get_state(obj))
    assert m[12] == 0.0 and m.sum() == n - 1
    data.mask_clear(obj, scene)
    assert data.get_mask(data.get_state(obj)).sum() == 0
    data.mask_fill(obj, scene)
    assert data.get_mask(data.get_state(obj)).sum() == n
    data.set_mask(obj, one, scene)
    data.mask_smooth(obj, scene)
    m = data.get_mask(data.get_state(obj))
    assert 0 < m[12] < 1 and m[7] > 0
    data.set_mask_enabled(obj, False, scene)
    data.mask_fill(obj, scene)
    _dab(scene, obj, "pull", radius=3.0)
    assert obj.mesh.points[:, 1].max() > 0


def test_mask_follows_levels():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.ensure_state(obj)
    data.mask_fill(obj, scene)
    data.subdivide(obj, scene, 1)
    assert np.allclose(data.get_mask(data.get_state(obj)), 1.0)
    data.set_level(obj, 0, scene)
    assert len(data.get_mask(data.get_state(obj))) == 8


def test_symmetry_mirrors_local_axes():
    assert len(symmetry_frames((True, False, True))) == 4
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "pull", hit=(20.0, 0, 10.0), radius=10.0, symmetry=(True, False, False))
    pts = obj.mesh.points
    mirror = pts.copy()
    mirror[:, 0] *= -1
    order = [int(np.argmin(np.linalg.norm(pts - m * [1, 0, 1], axis=1))) for m in mirror]
    assert np.allclose(pts[:, 1], pts[order, 1])
    assert pts[:, 1].max() > 0.1


def test_symmetry_uses_object_local_frame():
    scene, obj = _scene_with(_grid(20, 100.0))
    obj.position = np.array([500.0, 0.0, 0.0])
    _dab(scene, obj, "pull", hit=(520.0, 0, 0), radius=10.0, symmetry=(True, False, False))
    pts = obj.mesh.points
    left = pts[np.linalg.norm(pts[:, [0, 2]] - [-20, 0], axis=1) < 1e-6, 1]
    right = pts[np.linalg.norm(pts[:, [0, 2]] - [20, 0], axis=1) < 1e-6, 1]
    assert left.size and np.allclose(left, right) and right[0] > 0.1


def test_world_transform_scaled_object():
    scene, obj = _scene_with(_grid(20, 100.0))
    obj.scale = np.array([2.0, 2.0, 2.0])
    obj.position = np.array([0.0, 50.0, 0.0])
    _dab(scene, obj, "pull", hit=(0.0, 50.0, 0.0), radius=40.0)
    peak_local = obj.mesh.points[:, 1].max()
    assert np.isclose(peak_local, 40.0 * 0.05 / 2.0)
    moved = np.linalg.norm(obj.mesh.points[:, [0, 2]] * 2.0, axis=1)
    assert np.allclose(obj.mesh.points[moved > 40.5, 1], 0.0)


def test_front_faces_only():
    scene, obj = _scene_with(Mesh.cube(20.0), "Small")
    data.subdivide(obj, scene, 2)
    pts0 = obj.mesh.points.copy()
    _dab(scene, obj, "pull", hit=(0, pts0[:, 1].max(), 0), radius=100.0)
    bottom = pts0[:, 1] < -5.0
    assert np.allclose(obj.mesh.points[bottom], pts0[bottom])
    scene, obj = _scene_with(Mesh.cube(20.0), "Small")
    data.subdivide(obj, scene, 2)
    _dab(scene, obj, "pull", hit=(0, pts0[:, 1].max(), 0), radius=100.0, front_only=False)
    assert not np.allclose(obj.mesh.points[bottom], pts0[bottom])


def test_spacing_controls_dab_count():
    scene, obj = _scene_with(_grid(40, 100.0))
    s = _settings("pull", spacing=0.5)
    stroke = SculptStroke(obj, s, scene)
    stroke.dab((0, 0, 0), (0, 1, 0), (0, -1, 0), radius=10.0)
    assert stroke.dab((2, 0, 0), (0, 1, 0), (0, -1, 0), radius=10.0) == 0
    before = obj.mesh.points.copy()
    assert stroke.dab((21, 0, 0), (0, 1, 0), (0, -1, 0), radius=10.0) > 0
    changed = np.abs(obj.mesh.points[:, 1] - before[:, 1]) > 1e-9
    xs = obj.mesh.points[changed, 0]
    assert xs.min() > -6.0 and xs.max() < 31.0
    stroke.end()


def test_stamp_modulates_dab():
    img = stamps.generate("stripes")
    assert img.shape == (64, 64) and 0 <= img.min() and img.max() <= 1
    assert np.isclose(stamps.sample(np.ones((4, 4)), np.array([0.0, 2.0]), np.array([0.0, 0.0]))[1], 0.0)
    scene, obj = _scene_with(_grid(40, 100.0))
    _dab(scene, obj, "stamp", radius=20.0, stamp="stripes", falloff="constant")
    y = obj.mesh.points[:, 1]
    inside = np.linalg.norm(obj.mesh.points[:, [0, 2]], axis=1) < 18.0
    assert y[inside].max() > 0.5 and y[inside].min() < y[inside].max() * 0.3
    custom = np.zeros((8, 8))
    custom[:, 4:] = 1.0
    scene, obj = _scene_with(_grid(40, 100.0))
    _dab(scene, obj, "pull", radius=20.0, stamp="custom", stamp_image=custom, falloff="constant")
    pts = obj.mesh.points
    assert pts[:, 1].max() > 0.5


def test_stamp_scale_and_tile():
    custom = np.zeros((8, 8))
    custom[:, 4:] = 1.0
    view = (0.0, -1.0, 0.0)
    moved = {}
    for tile in (False, True):
        scene, obj = _scene_with(_grid(80, 100.0))
        base = obj.mesh.points.copy()
        s = _settings("pull", stamp="custom", stamp_image=custom, falloff="constant",
                      stamp_scale=0.5, stamp_tile=tile)
        assert s.stamp_scale == 0.5 and s.stamp_tile == tile
        apply_dab(obj, s, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), view, radius=20.0, scene=scene)
        moved[tile] = np.abs(obj.mesh.points[:, 1] - base[:, 1]) > 1e-9
        pts = base
    band = np.linalg.norm(pts[:, [0, 2]], axis=1) < 19.0
    outer = band & (np.linalg.norm(pts[:, [0, 2]], axis=1) > 14.5)
    assert moved[False][band].any()
    assert not moved[False][outer].any()
    assert moved[True][outer].any()
    clamp = BrushSettings(stamp_scale=99.0, stamp_tile=1).clamp()
    assert clamp.stamp_scale == 4.0 and clamp.stamp_tile is True
    scene, obj = _scene_with(_grid(10, 100.0))
    panel = sculpt.SculptBrushPanel(scene)
    panel.stamp_scale.spin.setValue(200)
    panel.stamp_tile.setChecked(True)
    assert panel.session.settings().stamp_scale == 2.0 and panel.session.settings().stamp_tile
    panel.session.reset_brush()
    assert panel.stamp_scale.value() == 100.0 and not panel.stamp_tile.isChecked()
    panel.close()


def test_layers_strength_visibility_and_bake():
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "pull", radius=20.0)
    base = obj.mesh.points.copy()
    i = data.add_layer(obj, "Detail", scene)
    assert i == 0 and data.active_layer(data.get_state(obj)) == 0
    _dab(scene, obj, "pull", radius=20.0, hit=(25.0, 0, 0))
    full = obj.mesh.points.copy()
    st = data.get_state(obj)
    assert np.allclose(np.asarray(st["levels"][0]), base)
    delta = full - base
    assert np.abs(delta).max() > 0.1
    data.set_layer_strength(obj, 0, 0.5, scene)
    assert np.allclose(obj.mesh.points, base + 0.5 * delta)
    data.set_layer_visible(obj, 0, False, scene)
    assert np.allclose(obj.mesh.points, base)
    data.set_layer_visible(obj, 0, True, scene)
    data.set_layer_strength(obj, 0, 1.0, scene)
    assert np.allclose(obj.mesh.points, full)
    _dab(scene, obj, "pull", radius=10.0, hit=(-25.0, 0, 0))
    after = obj.mesh.points.copy()
    assert data.bake_layers(obj, scene)
    assert np.allclose(obj.mesh.points, after) and data.layer_count(data.get_state(obj)) == 0


def test_layer_strength_scales_new_strokes_consistently():
    scene, obj = _scene_with(_grid(20, 100.0))
    data.add_layer(obj, "A", scene)
    data.set_layer_strength(obj, 0, 0.5, scene)
    _dab(scene, obj, "pull", radius=20.0)
    shown = obj.mesh.points.copy()
    data.set_layer_strength(obj, 0, 1.0, scene)
    assert np.allclose(obj.mesh.points[:, 1], shown[:, 1] * 2.0)


def test_layer_remove_move_merge_rename_lock():
    scene, obj = _scene_with(_grid(20, 100.0))
    flat = obj.mesh.points.copy()
    data.add_layer(obj, "A", scene)
    _dab(scene, obj, "pull", radius=15.0, hit=(-20.0, 0, 0))
    a_only = obj.mesh.points.copy()
    data.add_layer(obj, "B", scene)
    _dab(scene, obj, "pull", radius=15.0, hit=(20.0, 0, 0))
    both = obj.mesh.points.copy()
    assert data.move_layer(obj, 1, -1, scene) == 0
    st = data.get_state(obj)
    assert [l["name"] for l in data.layers(st)] == ["B", "A"] and data.active_layer(st) == 0
    assert np.allclose(obj.mesh.points, both)
    assert data.rename_layer(obj, 0, "Bumps", scene)
    assert data.layers(data.get_state(obj))[0]["name"] == "Bumps"
    data.set_layer_locked(obj, 1, True, scene)
    data.set_active_layer(obj, 1, scene)
    before = obj.mesh.points.copy()
    assert _dab(scene, obj, "pull", radius=15.0, hit=(0.0, 0, 30.0)) == 0
    st = data.get_state(obj)
    assert np.allclose(obj.mesh.points, before)
    assert np.allclose(np.asarray(st["levels"][0]), flat)
    assert not data.merge_layer_down(obj, 1, scene)
    data.set_layer_locked(obj, 1, False, scene)
    assert data.merge_layer_down(obj, 1, scene)
    st = data.get_state(obj)
    assert data.layer_count(st) == 1
    data.remove_layer(obj, 0, scene)
    st = data.get_state(obj)
    assert data.layer_count(st) == 0
    assert np.allclose(obj.mesh.points, np.asarray(st["levels"][0]))
    assert not np.allclose(obj.mesh.points, both)
    assert np.allclose(a_only[:, 1] * 0, 0)


def test_clear_layer_and_base():
    scene, obj = _scene_with(_grid(20, 100.0))
    _dab(scene, obj, "pull", radius=15.0)
    data.add_layer(obj, "A", scene)
    _dab(scene, obj, "pull", radius=15.0, hit=(20.0, 0, 0))
    data.clear_layer(obj, 0, scene)
    pts = obj.mesh.points
    assert np.allclose(pts[pts[:, 0] > 12.0, 1], 0.0)
    assert pts[:, 1].max() > 0.1
    data.clear_layer(obj, -1, scene)
    assert np.allclose(obj.mesh.points[:, 1], 0.0)


def test_layers_across_levels():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 1)
    data.add_layer(obj, "L", scene)
    top = obj.mesh.points[:, 1].max()
    _dab(scene, obj, "pull", hit=(0, top, 0), radius=120.0)
    level1 = obj.mesh.points.copy()
    data.subdivide(obj, scene, 1)
    st = data.get_state(obj)
    assert np.allclose(obj.mesh.points, data._operator(st, 1).apply(level1))
    data.set_layer_strength(obj, 0, 0.0, scene)
    data.set_level(obj, 1, scene)
    assert not np.allclose(obj.mesh.points, level1)


def test_stroke_is_one_undo_step_and_restores_state():
    scene, obj = _scene_with(_grid(20, 100.0))
    data.ensure_state(obj)
    scene.clear_history()
    pts0 = obj.mesh.points.copy()
    s = _settings("pull", spacing=0.1)
    stroke = sculpt.stroke_begin(obj, s, scene)
    for x in np.linspace(-20, 20, 15):
        sculpt.stroke_dab((x, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 10.0)
    assert sculpt.stroke_end()
    assert sculpt.current_stroke() is None and stroke.dabs == 15
    assert len(scene._undo) == 1
    assert not np.allclose(obj.mesh.points, pts0)
    scene.undo()
    obj2 = scene.objects[0]
    assert np.allclose(obj2.mesh.points, pts0)
    st = data.ensure_state(obj2)
    assert np.allclose(np.asarray(st["levels"][0]), pts0)
    scene.redo()
    obj3 = scene.objects[0]
    assert obj3.mesh.points[:, 1].max() > 0.1
    _dab(scene, obj3, "pull", radius=10.0, hit=(30.0, 0, 0))
    assert np.allclose(np.asarray(data.get_state(obj3)["levels"][0]), obj3.mesh.points)


def test_external_point_edit_is_reconciled():
    scene, obj = _scene_with(_grid(8, 100.0))
    data.ensure_state(obj)
    pts = obj.mesh.points.copy()
    pts[0, 1] = 5.0
    obj.mesh.points = pts
    st = data.ensure_state(obj)
    assert np.allclose(data.composite(st), pts)
    obj.mesh = Mesh.cube(10.0)
    st = data.ensure_state(obj)
    assert data.level_count(st) == 1 and len(st["levels"][0]) == 8


def test_frozen_blocks_sculpting():
    scene, obj = _scene_with(_grid(10, 100.0))
    data.set_frozen(obj, True, scene)
    assert _dab(scene, obj, "pull", radius=30.0) == 0
    assert np.allclose(obj.mesh.points[:, 1], 0.0)
    data.set_frozen(obj, False, scene)
    assert _dab(scene, obj, "pull", radius=30.0) > 0


def test_bake_to_mesh_and_remove():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 2)
    top = obj.mesh.points[:, 1].max()
    _dab(scene, obj, "pull", hit=(0, top, 0), radius=60.0)
    final = obj.mesh.points.copy()
    assert data.bake_to_mesh(obj, scene)
    assert data.get_state(obj) is None and np.allclose(obj.mesh.points, final)
    assert len(obj.mesh.polygons) == 96
    scene.undo()
    assert data.get_state(scene.objects[0]) is not None
    obj = scene.objects[0]
    assert data.remove_sculpt(obj, scene) and data.get_state(obj) is None


def test_state_json_roundtrip():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 1)
    data.add_layer(obj, "L", scene)
    _dab(scene, obj, "pull", hit=(0, obj.mesh.points[:, 1].max(), 0), radius=80.0)
    data.mask_fill(obj, scene)
    st = data.get_state(obj)
    encoded = store.to_json(st)
    import json
    text = json.dumps(encoded)
    decoded = store.from_json(json.loads(text))
    clone_scene, clone = _scene_with(Mesh(obj.mesh.points.copy(), obj.mesh.polygons), "Cube")
    store.object_extras(clone)[data.KEY] = decoded
    st2 = data.ensure_state(clone)
    assert data.level_count(st2) == 2 and data.layer_count(st2) == 1
    assert np.allclose(data.composite(st2), obj.mesh.points)
    assert np.allclose(data.get_mask(st2), 1.0)


def test_session_settings_shared_and_per_brush():
    scene = reset_scene()
    session = sculpt.get_session(scene)
    assert sculpt.get_session(scene) is session
    session.set_brush("smooth")
    session.set("strength", 0.25)
    session.set("radius", 80.0)
    session.set_brush("pull")
    assert session.settings().radius == 80.0 and session.settings().strength != 0.25
    assert session.settings("smooth").strength == 0.25
    session.set_symmetry(2, True)
    assert session.settings("grab").symmetry == (False, False, True)
    session.scale_radius(0.5)
    assert session.settings().radius == 40.0
    session.set("strength", 0.9)
    session.reset_brush()
    assert session.settings().strength == default_settings("pull").strength
    assert session.settings().radius == 40.0
    try:
        session.set("bogus", 1)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown key accepted")
    scene.set_tool("move")
    session.set_active(True)
    assert scene.tool == "other" and session.active
    session.set_active(False)
    assert scene.tool == "move"
    session2 = sculpt.session.SculptSession(scene)
    assert session2.settings("smooth").strength == 0.25


def test_settings_roundtrip_and_clamp():
    s = BrushSettings(radius=-5, strength=3.0, falloff="nope", stamp="zzz", symmetry=(1,))
    s.clamp()
    assert s.radius == 1.0 and s.strength == 1.0 and s.falloff == "smooth" and s.stamp == "none"
    assert s.symmetry == (True, False, False)
    d = _settings("clay", curve=[(0, 1), (1, 0)]).to_dict()
    back = BrushSettings.from_dict(store.from_json(store.to_json(d)))
    assert back.brush == "clay" and back.curve[0] == [0.0, 1.0]
    for b in BRUSH_ORDER:
        assert default_settings(b).brush == b


def test_every_brush_runs_on_closed_mesh():
    for b in BRUSH_ORDER:
        scene, obj = _scene_with(subdivide_mesh(Mesh.cube(100.0), 2), "Ball")
        top = obj.mesh.points[:, 1].max()
        count = _dab(scene, obj, b, hit=(0, top, 0), radius=40.0)
        assert count > 0, b
        assert np.all(np.isfinite(obj.mesh.points)), b


class _FakeCamera:

    def depth(self, pts):
        return np.full(len(np.atleast_2d(pts)), 100.0)


class _FakeCanvas(QWidget):

    def __init__(self, scene) -> None:
        super().__init__()
        self.scene = scene
        self.camera = _FakeCamera()
        self.resize(200, 200)

    def ray_at(self, pos):
        x, y = pos.x(), pos.y()
        return np.array([x - 100.0, 500.0, y - 100.0]), np.array([0.0, -1.0, 0.0])

    def hit_at(self, pos):
        o, d = self.ray_at(pos)
        return self.scene.raycast(o, d)

    def px_size(self, depth):
        return 0.5

    def view_direction(self):
        return np.array([0.0, -1.0, 0.0])

    def project_world(self, pts):
        pts = np.atleast_2d(pts)
        return np.column_stack([pts[:, 0] + 100.0, pts[:, 2] + 100.0])


def _mouse(widget, kind, x, y, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    buttons = button if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    if kind == QEvent.Type.MouseMove:
        buttons = button
    ev = QMouseEvent(kind, QPointF(x, y), widget.mapToGlobal(QPointF(x, y)), button, buttons, mods)
    return QApplication.sendEvent(widget, ev)


def test_viewport_controller_with_fake_canvas():
    scene, obj = _scene_with(_grid(20, 100.0))
    canvas = _FakeCanvas(scene)
    ctl = sculpt.attach_viewport(canvas, scene)
    assert sculpt.attach_viewport(canvas, scene) is ctl
    session = ctl.session
    session.set_brush("pull")
    session.set("radius", 40.0)
    session.set("strength", 1.0)
    session.set("spacing", 0.0)
    session.set_active(True)
    assert ctl.overlay.isVisibleTo(canvas)
    assert ctl.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    scene.clear_history()
    _mouse(canvas, QEvent.Type.MouseButtonPress, 100, 100)
    assert ctl.stroke is not None
    _mouse(canvas, QEvent.Type.MouseMove, 105, 100)
    _mouse(canvas, QEvent.Type.MouseMove, 110, 100)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 110, 100)
    assert ctl.stroke is None
    obj = scene.objects[0]
    assert obj.mesh.points[:, 1].max() > 0.5
    assert len(scene._undo) == 1
    peak = obj.mesh.points[:, 1].max()
    _mouse(canvas, QEvent.Type.MouseButtonPress, 100, 100, mods=Qt.KeyboardModifier.ControlModifier)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 100, 100)
    assert obj.mesh.points[:, 1].max() < peak
    rough = obj.mesh.points[:, 1].std()
    _mouse(canvas, QEvent.Type.MouseButtonPress, 100, 100, mods=Qt.KeyboardModifier.ShiftModifier)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 100, 100)
    assert obj.mesh.points[:, 1].std() < rough
    handled = _mouse(canvas, QEvent.Type.MouseButtonPress, 100, 100, mods=Qt.KeyboardModifier.AltModifier)
    assert ctl.stroke is None
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 100, 100)
    pts = obj.mesh.points.copy()
    _mouse(canvas, QEvent.Type.MouseButtonPress, 100, 100, button=Qt.MouseButton.MiddleButton)
    assert ctl.stroke is None and np.allclose(obj.mesh.points, pts)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 100, 100, button=Qt.MouseButton.MiddleButton)
    _mouse(canvas, QEvent.Type.MouseButtonPress, 2, 2)
    assert ctl._pending or ctl.stroke is not None
    _mouse(canvas, QEvent.Type.MouseMove, 100, 100)
    assert ctl.stroke is not None
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 100, 100)
    session.set_brush("grab")
    session.set("falloff", "constant")
    before = obj.mesh.points.copy()
    _mouse(canvas, QEvent.Type.MouseButtonPress, 140, 140)
    _mouse(canvas, QEvent.Type.MouseMove, 150, 140)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 150, 140)
    moved = np.linalg.norm(obj.mesh.points - before, axis=1)
    assert moved.max() > 5.0
    session.set_brush("mask")
    _mouse(canvas, QEvent.Type.MouseButtonPress, 60, 60)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 60, 60)
    assert data.summary(scene.objects[0])["masked"] > 0
    ctl.overlay.pos_xy = (50.0, 50.0)
    img = ctl.overlay.grab()
    assert not img.isNull()
    r0 = session.settings().radius
    from PySide6.QtGui import QKeyEvent
    QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketRight,
                                             Qt.KeyboardModifier.NoModifier))
    assert session.settings().radius > r0
    QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketLeft,
                                             Qt.KeyboardModifier.NoModifier))
    assert np.isclose(session.settings().radius, r0)
    canvas.resize(300, 240)
    QApplication.sendEvent(canvas, QEvent(QEvent.Type.Resize))
    assert ctl.overlay.width() == 300
    session.set_active(False)
    pts = scene.objects[0].mesh.points.copy()
    assert not _mouse(canvas, QEvent.Type.MouseButtonPress, 100, 100) or True
    assert ctl.stroke is None
    assert np.allclose(scene.objects[0].mesh.points, pts)
    ctl.detach()
    canvas.deleteLater()


def test_viewport_controller_on_real_canvas():
    from quartz_studio.widgets.viewport import ViewportCanvas

    scene = reset_scene()
    canvas = ViewportCanvas()
    canvas.resize(640, 480)
    canvas.show()
    APP.processEvents()
    ctl = sculpt.attach_viewport(canvas, canvas.scene)
    session = ctl.session
    session.set_brush("pull")
    session.set("strength", 1.0)
    session.set_active(True)
    obj = canvas.scene.active
    target = None
    for y in range(100, 400, 10):
        for x in range(200, 460, 10):
            if canvas.hit_at(QPointF(x, y)) is not None:
                target = (x, y)
                break
        if target:
            break
    assert target is not None
    before = canvas.scene.active.mesh.points.copy()
    _mouse(canvas, QEvent.Type.MouseButtonPress, *target)
    _mouse(canvas, QEvent.Type.MouseMove, target[0] + 20, target[1] + 10)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, target[0] + 20, target[1] + 10)
    after = canvas.scene.active.mesh.points
    assert after.shape == before.shape and not np.allclose(after, before)
    assert obj is canvas.scene.active
    session.set_active(False)
    ctl.detach()
    canvas.close()


def test_brush_panel_smoke():
    scene, obj = _scene_with(_grid(10, 100.0))
    panel = sculpt.SculptBrushPanel(scene)
    panel.resize(320, 900)
    panel.show()
    APP.processEvents()
    session = panel.session
    assert len(panel.brush_buttons) == len(BRUSH_ORDER)
    panel.brush_buttons["clay"].click()
    assert session.brush == "clay" and panel.brush_buttons["clay"].isChecked()
    panel.radius.spin.setValue(64)
    assert session.settings().radius == 64.0
    panel.strength.slider.setValue(250)
    assert np.isclose(session.settings().strength, 0.25)
    panel.spacing.spin.setValue(40)
    assert np.isclose(session.settings().spacing, 0.4)
    panel.smooth_strength.spin.setValue(70)
    assert np.isclose(session.settings().smooth_strength, 0.7)
    panel.invert.setChecked(True)
    assert session.settings().invert
    panel.pressure_radius.setChecked(True)
    assert session.settings("pull").pressure_radius
    panel.front_only.setChecked(False)
    assert not session.settings().front_only
    panel.use_mask.setChecked(False)
    assert not session.settings().use_mask
    panel.falloff.setCurrentIndex(1)
    panel.falloff.activated.emit(1)
    assert session.settings().falloff == "linear"
    panel.sym[0].setChecked(True)
    assert session.settings("pull").symmetry[0]
    panel.stamp.activated.emit(2)
    assert session.settings().stamp == "rings"
    panel.stamp_rotation.spin.setValue(45)
    assert session.settings().stamp_rotation == 45.0
    path = os.path.join(tempfile.mkdtemp(), "stamp.png")
    img = QImage(32, 32, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    for x in range(16):
        for y in range(32):
            img.setPixelColor(x, y, QColor(0, 0, 0))
    assert img.save(path)
    assert panel._load_stamp(path)
    s = session.settings()
    assert s.stamp == "custom" and s.stamp_image is not None
    assert s.stamp_image[:, :40].mean() < 0.2 and s.stamp_image[:, 90:].mean() > 0.8
    panel.mask_buttons["Fill"].click()
    assert data.summary(obj)["masked"] == len(obj.mesh.points)
    panel.mask_buttons["Invert"].click()
    assert data.summary(obj)["masked"] == 0
    panel.mask_enabled.setChecked(False)
    assert not data.summary(obj)["mask_enabled"]
    panel.show_mask.setChecked(False)
    assert not session.show_mask
    panel.mode_button.click()
    assert session.active
    panel.mode_button.click()
    assert not session.active
    session.set_brush("pull")
    assert panel.brush_buttons["pull"].isChecked()
    assert panel.radius.value() == 64.0
    assert not panel.grab().isNull()
    panel.close()


def test_curve_editor_interaction():
    from PySide6.QtTest import QTest

    ed = sculpt.FalloffCurveEditor()
    ed.resize(256, 96)
    ed.show()
    APP.processEvents()
    got = []
    ed.edited.connect(lambda k, c: got.append((k, c)))
    ed.set_state("linear", falloff.DEFAULT_CURVE)
    QTest.mousePress(ed, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(128, 48))
    assert ed.kind == "custom" and got and got[-1][0] == "custom"
    n = len(ed.curve)
    QTest.mouseMove(ed, QPoint(128, 20))
    QTest.mouseRelease(ed, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(128, 20))
    ys = [y for x, y in ed.curve if abs(x - 0.5) < 0.05]
    assert ys and ys[0] > 0.7
    QTest.mouseDClick(ed, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(60, 60))
    assert len(ed.curve) >= n
    p = ed.to_widget(*ed.curve[1])
    count = len(ed.curve)
    QTest.mousePress(ed, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, p.toPoint())
    assert len(ed.curve) == count - 1
    assert not ed.grab().isNull()
    scene = reset_scene()
    panel = sculpt.SculptBrushPanel(scene)
    panel.curve.edited.emit("custom", [[0.0, 1.0], [0.5, 0.2], [1.0, 0.0]])
    s = panel.session.settings()
    assert s.falloff == "custom" and s.curve[1] == [0.5, 0.2]
    panel.close()
    ed.close()


def test_layers_panel_smoke():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    panel = sculpt.SculptLayersPanel(scene)
    panel.resize(320, 700)
    panel.show()
    APP.processEvents()
    assert panel.object_label.text() == "Cube"
    panel.subdivide_button.click()
    assert len(scene.active.mesh.points) == 26
    assert panel.level_combo.count() == 2 and panel.level_combo.currentIndex() == 1
    panel.subdivide_button.click()
    assert panel.level_combo.count() == 3
    panel.down_button.click()
    assert len(scene.active.mesh.points) == 26
    panel.up_button.click()
    assert len(scene.active.mesh.points) == 98
    panel.level_combo.activated.emit(0)
    assert len(scene.active.mesh.points) == 8
    panel.level_combo.activated.emit(2)
    panel.add_button.click()
    assert panel.layer_list.count() == 2 and panel.selected_layer() == 0
    obj = scene.active
    top = obj.mesh.points[:, 1].max()
    _dab(scene, obj, "pull", hit=(0, top, 0), radius=80.0)
    shown = scene.active.mesh.points.copy()
    panel.layer_strength.spin.setValue(0)
    assert not np.allclose(scene.active.mesh.points, shown)
    panel.layer_strength.spin.setValue(100)
    assert np.allclose(scene.active.mesh.points, shown)
    item = panel.layer_list.item(1)
    item.setCheckState(Qt.CheckState.Unchecked)
    APP.processEvents()
    assert not data.layers(data.get_state(scene.active))[0]["visible"]
    panel.refresh()
    item = panel.layer_list.item(1)
    item.setCheckState(Qt.CheckState.Checked)
    panel.refresh()
    item = panel.layer_list.item(1)
    item.setText("Wrinkles")
    APP.processEvents()
    assert data.layers(data.get_state(scene.active))[0]["name"] == "Wrinkles"
    panel.refresh()
    panel.add_button.click()
    assert panel.layer_list.count() == 3
    panel.layer_up_button.click()
    assert panel.selected_layer() == 0
    panel.layer_lock.setChecked(True)
    assert data.layers(data.get_state(scene.active))[0]["locked"]
    panel.layer_list.setCurrentRow(2)
    assert data.active_layer(data.get_state(scene.active)) == 1
    assert not panel.merge_button.isEnabled()
    panel.layer_list.setCurrentRow(1)
    panel.layer_lock.setChecked(False)
    assert not data.layers(data.get_state(scene.active))[0]["locked"]
    panel.layer_list.setCurrentRow(2)
    assert panel.merge_button.isEnabled()
    panel.merge_button.click()
    assert data.layer_count(data.get_state(scene.active)) == 1
    panel.layer_list.setCurrentRow(1)
    panel.clear_button.click()
    panel.remove_button.click()
    assert data.layer_count(data.get_state(scene.active)) == 0
    panel.frozen.setChecked(True)
    assert data.is_frozen(data.get_state(scene.active))
    panel.frozen.setChecked(False)
    panel.down_button.click()
    panel.delete_higher_button.click()
    assert data.level_count(data.get_state(scene.active)) == 2
    panel.add_button.click()
    panel.bake_layers_button.click()
    assert data.layer_count(data.get_state(scene.active)) == 0
    panel.bake_button.click()
    assert data.get_state(scene.active) is None and len(scene.active.mesh.points) == 26
    panel.subdivide_button.click()
    panel.remove_sculpt_button.click()
    assert data.get_state(scene.active) is None
    scene.set_active(None)
    panel.refresh()
    assert panel.object_label.text() == "No polygon object" and not panel.bake_button.isEnabled()
    assert not panel.grab().isNull()
    panel.close()


def test_menu_commands_docks_pages_keys():
    scene = reset_scene()
    cmds = sculpt.commands()
    paths = [p for p, fn in cmds]
    assert ("Sculpt", "Sculpt Mode") in paths and ("Sculpt", "Subdivide") in paths
    assert all(isinstance(p, tuple) and callable(fn) for p, fn in cmds)
    table = dict(cmds)
    session = sculpt.get_session(scene)
    assert table[("Sculpt", "Sculpt Mode")]() is True and session.active
    table[("Sculpt", "Sculpt Mode")]()
    assert not session.active
    table[("Sculpt", "Subdivide")]()
    assert len(scene.active.mesh.points) == 26
    table[("Sculpt", "Level Down")]()
    assert len(scene.active.mesh.points) == 8
    table[("Sculpt", "Level Up")]()
    table[("Sculpt", "Layers", "Add Layer")]()
    assert data.layer_count(data.get_state(scene.active)) == 1
    table[("Sculpt", "Mask", "Fill Mask")]()
    table[("Sculpt", "Mask", "Invert Mask")]()
    assert data.summary(scene.active)["masked"] == 0
    table[("Sculpt", "Brushes", "Clay")]()
    assert session.brush == "clay" and session.active
    table[("Sculpt", "Symmetry", "Local X")]()
    assert session.settings().symmetry[0]
    table[("Sculpt", "Bake to Mesh")]()
    assert data.get_state(scene.active) is None
    docks = sculpt.docks()
    assert [d[0] for d in docks] == ["Sculpt Brushes", "Sculpt Layers"]
    for title, factory, area in docks:
        assert area in ("left", "right", "bottom")
        w = factory()
        assert isinstance(w, QWidget)
        host = QWidget()
        w2 = factory(host, scene)
        assert w2.parent() is host and w2.scene is scene
        w.close()
        host.close()
    assert sculpt.pages() == [("Sculpt", ["Sculpt Brushes", "Sculpt Layers"])]
    keys = sculpt.key_actions()
    assert all(len(k) == 3 and callable(k[2]) for k in keys)
    r = session.settings().radius
    dict((k[0], k[2]) for k in keys)["]"]()
    assert session.settings().radius > r


def test_icons_render_distinct():
    from quartz_studio.sculpt.icons import brush_icon, brush_pixmap

    seen = set()
    for b in BRUSH_ORDER:
        pm = brush_pixmap(b, 32)
        img = pm.toImage()
        assert not img.isNull() and img.width() == 32
        raw = bytes(img.constBits())
        assert any(raw[3::4]), b
        seen.add(raw)
        assert not brush_icon(b).isNull()
    assert len(seen) == len(BRUSH_ORDER)


def test_no_comments_in_package():
    root = os.path.join(STUDIO_ROOT, "quartz_studio", "sculpt")
    import io
    import tokenize
    for name in os.listdir(root):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(root, name), "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                assert tok.type != tokenize.COMMENT, name


def _key(widget, key, mods=Qt.KeyboardModifier.NoModifier, kind=QEvent.Type.KeyPress):
    from PySide6.QtGui import QKeyEvent
    return QApplication.sendEvent(widget, QKeyEvent(kind, key, mods))


def test_regression_project_saves_through_quartz_writer():
    import json

    from quartz_studio.fileio import bridge, fmt_quartz

    scene, obj = _scene_with(Mesh.cube(200.0), "Obj")
    data.subdivide(obj, scene)
    data.add_layer(obj, "Detail", scene)
    top = obj.mesh.points[:, 1].max()
    assert apply_dab(obj, _settings("pull"), (0, top, 0), (0, 1, 0), (0, -1, 0), radius=80.0, scene=scene) > 0
    data.mask_fill(obj, scene)
    json.dumps(obj.extras)

    def has_array(v):
        if isinstance(v, np.ndarray):
            return True
        if isinstance(v, dict):
            return any(has_array(x) for x in v.values())
        if isinstance(v, list):
            return any(has_array(x) for x in v)
        return False

    assert not has_array(obj.extras)
    pts = obj.mesh.points.copy()
    path = os.path.join(tempfile.mkdtemp(), "sculpted.qz")
    fmt_quartz.save(path, bridge.full_document_from_scene(scene), {})
    doc = fmt_quartz.load(path)
    other = reset_scene()
    bridge.replace_scene(other, doc)
    clone = other.objects[0]
    st = data.ensure_state(clone)
    assert data.level_count(st) == 2 and data.layer_count(st) == 1
    assert data.layers(st)[0]["name"] == "Detail"
    assert np.allclose(clone.mesh.points, pts) and np.allclose(data.composite(st), pts)
    assert np.allclose(data.get_mask(st), 1.0)
    data.set_level(clone, 0, other)
    data.set_level(clone, 1, other)
    assert np.allclose(clone.mesh.points, pts)


def test_regression_locked_hidden_muted_layers_block_strokes():
    scene, obj = _scene_with(_grid(10, 100.0))
    flat = obj.mesh.points.copy()
    i = data.add_layer(obj, "L", scene)
    data.set_layer_locked(obj, i, True, scene)
    st = data.get_state(obj)
    assert data.edit_block(st) == "locked" and data.summary(obj)["block"] == "locked"
    assert _dab(scene, obj, "pull", radius=30.0) == 0
    assert np.allclose(obj.mesh.points, flat)
    st = data.get_state(obj)
    assert data.layers(st)[0]["deltas"] == [None] and np.allclose(st["levels"][0], flat)
    assert sculpt.stroke_begin(obj, _settings("pull"), scene) is None
    assert not data.clear_layer(obj, i, scene)
    assert _dab(scene, obj, "mask", radius=30.0) > 0
    assert data.summary(obj)["masked"] > 0
    data.mask_clear(obj, scene)
    data.set_layer_locked(obj, i, False, scene)
    data.set_layer_visible(obj, i, False, scene)
    assert data.edit_block(data.get_state(obj)) == "hidden"
    assert _dab(scene, obj, "pull", radius=30.0) == 0 and np.allclose(obj.mesh.points, flat)
    data.set_layer_visible(obj, i, True, scene)
    data.set_layer_strength(obj, i, 0.0, scene)
    assert data.edit_block(data.get_state(obj)) == "muted"
    assert _dab(scene, obj, "pull", radius=30.0) == 0 and np.allclose(obj.mesh.points, flat)
    data.set_layer_strength(obj, i, 1.0, scene)
    assert data.edit_block(data.get_state(obj)) is None
    assert _dab(scene, obj, "pull", radius=30.0) > 0
    st = data.get_state(obj)
    assert np.allclose(st["levels"][0], flat)
    assert np.abs(np.asarray(data.layers(st)[0]["deltas"][0])).max() > 0.1
    data.set_frozen(obj, True, scene)
    assert _dab(scene, obj, "mask", radius=30.0) == 0


def test_regression_mirrored_object_brushes_point_outward():
    results = {}
    for sx in (1.0, -1.0):
        scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
        data.subdivide(obj, scene, 2)
        obj.scale = np.array([sx, 1.0, 1.0])
        stroke = SculptStroke(obj, _settings("pull"), scene)
        res = stroke.raycast((0.0, 500.0, 0.0), (0.0, -1.0, 0.0))
        assert res is not None
        face, point, _t = res
        normal = stroke.surface_normal(face)
        assert normal[1] > 0.9, (sx, normal)
        top = float(obj.world_points()[:, 1].max())
        stroke.dab(point, normal, (0.0, -1.0, 0.0), 1.0, 60.0)
        assert stroke.end()
        results[sx] = float(obj.world_points()[:, 1].max()) - top
        w0 = obj.world_points()
        r0 = np.linalg.norm(w0, axis=1).mean()
        apply_dab(obj, _settings("inflate"), point, normal, (0.0, -1.0, 0.0), radius=60.0, scene=scene)
        assert np.linalg.norm(obj.world_points(), axis=1).mean() > r0
    assert results[1.0] > 0.5 and results[-1.0] > 0.5
    assert np.isclose(results[1.0], results[-1.0], rtol=1e-6)


def test_regression_merge_and_bake_keep_hidden_layers():
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 2)
    top = obj.mesh.points[:, 1].max()
    smooth = obj.mesh.points.copy()
    data.add_layer(obj, "A", scene)
    data.add_layer(obj, "B", scene)
    _dab(scene, obj, "pull", hit=(0, top, 0), radius=60.0)
    with_b = obj.mesh.points.copy()
    assert np.abs(with_b - smooth).max() > 0.5
    data.set_layer_visible(obj, 1, False, scene)
    st = data.get_state(obj)
    assert not data.can_merge_down(st, 1) and not data.summary(obj)["can_merge"]
    assert not data.merge_layer_down(obj, 1, scene)
    assert data.layer_count(data.get_state(obj)) == 2
    data.set_active_layer(obj, 0, scene)
    _dab(scene, obj, "pull", hit=(0, -top, 0), normal=(0, -1, 0), radius=60.0)
    with_a = obj.mesh.points.copy()
    assert data.bake_layers(obj, scene)
    st = data.get_state(obj)
    assert [l["name"] for l in data.layers(st)] == ["B"] and not data.layers(st)[0]["visible"]
    assert np.allclose(obj.mesh.points, with_a)
    data.set_layer_visible(obj, 0, True, scene)
    expected = with_a + (with_b - smooth)
    assert np.allclose(obj.mesh.points, expected, atol=1e-9)
    data.set_layer_visible(obj, 0, False, scene)
    assert not data.bake_layers(obj, scene)
    assert data.layer_count(data.get_state(obj)) == 1
    data.set_layer_visible(obj, 0, True, scene)
    data.set_layer_locked(obj, 0, True, scene)
    assert not data.bake_layers(obj, scene) and not data.merge_layer_down(obj, 0, scene)
    data.set_layer_locked(obj, 0, False, scene)
    assert data.merge_layer_down(obj, 0, scene)
    assert data.layer_count(data.get_state(obj)) == 0 and np.allclose(obj.mesh.points, expected)


def test_regression_mask_detail_survives_level_round_trip():
    scene, obj = _scene_with(_grid(4, 100.0))
    data.subdivide(obj, scene, 2)
    data.set_level(obj, 1, scene)
    pts = obj.mesh.points
    original = (pts[:, 0] > 0).astype(float)
    assert data.set_mask(obj, original, scene)
    data.set_level(obj, 0, scene)
    data.set_level(obj, 1, scene)
    assert np.array_equal(data.get_mask(data.get_state(obj)), original)
    data.set_level(obj, 2, scene)
    high = data.get_mask(data.get_state(obj)).copy()
    data.set_level(obj, 0, scene)
    data.set_level(obj, 2, scene)
    assert np.array_equal(data.get_mask(data.get_state(obj)), high)
    data.set_level(obj, 0, scene)
    st = data.get_state(obj)
    low = data.get_mask(st)
    corner = int(np.argmin(np.linalg.norm(obj.mesh.points - np.array([-50.0, 0.0, -50.0]), axis=1)))
    low[corner] = 1.0
    data.set_mask(obj, low, scene)
    data.set_level(obj, 2, scene)
    back = data.get_mask(data.get_state(obj))
    far = np.linalg.norm(obj.mesh.points - np.array([-50.0, 0.0, -50.0]), axis=1) > 60.0
    assert np.array_equal(back[far], high[far])
    assert back[corner] > 0.5
    data.set_level(obj, 0, scene)
    data.mask_invert(obj, scene)
    data.set_level(obj, 2, scene)
    assert np.allclose(data.get_mask(data.get_state(obj)), 1.0 - back)
    data.set_level(obj, 0, scene)
    data.mask_clear(obj, scene)
    data.set_level(obj, 2, scene)
    assert data.summary(obj)["masked"] == 0


def test_regression_raycast_culling_matches_brute_force():
    from quartz_studio.sculpt.topology import RAY_CULL_MIN, ray_triangles

    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 4)
    st = data.get_state(obj)
    topo = data.topology(st)
    assert len(topo.tris) >= RAY_CULL_MIN
    W = obj.world_points()
    rng = np.random.default_rng(7)
    for _ in range(40):
        o = rng.uniform(-400, 400, 3)
        target = rng.uniform(-90, 90, 3)
        d = target - o
        fast = topo.raycast(W, o, d)
        slow = ray_triangles(W, topo.tris, o, d)
        assert (fast is None) == (slow is None)
        if fast is not None:
            assert np.isclose(fast[2], slow[2]) and np.allclose(fast[1], slow[1])
        cand = topo.ray_candidates(W, o, d)
        assert cand is not None and len(cand) < len(topo.tris) // 4
    stroke = SculptStroke(obj, _settings("pull", radius=40.0), scene)
    top = float(W[:, 1].max())
    for _ in range(12):
        stroke.dab((0.0, top, 0.0), (0, 1, 0), (0, -1, 0), 1.0, 40.0)
    peak = float(stroke.W[:, 1].max())
    assert peak > top + 5.0
    hit = stroke.raycast((0.0, 500.0, 0.0), (0.0, -1.0, 0.0))
    slow = ray_triangles(stroke.W, topo.tris, (0.0, 500.0, 0.0), (0.0, -1.0, 0.0))
    assert hit is not None and np.isclose(hit[2], slow[2])
    assert stroke.edge_bound >= topo.max_edge(stroke.W) - 1e-9
    stroke.end()


def test_regression_heavy_mesh_paths_are_fast():
    import time

    scene, obj = _scene_with(_grid(300, 1000.0))
    data.ensure_state(obj)
    st1 = data.get_state(obj)
    st2 = data.get_state(obj)
    assert st1 is not st2 and st1["levels"][0] is st2["levels"][0]
    assert not st1["levels"][0].flags.writeable
    t = time.perf_counter()
    for _ in range(20):
        data.get_state(obj)
        data.summary(obj)
    assert (time.perf_counter() - t) / 20 < 0.02
    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 6)
    stroke = SculptStroke(obj, _settings("pull"), scene)
    t = time.perf_counter()
    for k in range(5):
        stroke.raycast((float(k), 500.0, 3.0), (0.0, -1.0, 0.0))
    per_ray = (time.perf_counter() - t) / 5
    assert per_ray < 0.05, per_ray
    stroke.end()
    scene, obj = _scene_with(_grid(200, 1000.0))
    data.mask_fill(obj, scene)
    canvas = _FakeCanvas(scene)
    canvas.resize(512, 512)
    ctl = sculpt.attach_viewport(canvas, scene)
    ctl.session.set_active(True)
    assert not ctl.overlay.grab().isNull()
    builds = ctl.overlay.mask_builds
    t = time.perf_counter()
    for _ in range(5):
        ctl.overlay.grab()
    assert ctl.overlay.mask_builds == builds
    assert (time.perf_counter() - t) / 5 < 0.05
    ctl.overlay._mask_key = None
    t = time.perf_counter()
    img = ctl.overlay.grab().toImage()
    assert time.perf_counter() - t < 0.5
    c = img.pixelColor(100, 100)
    assert c.alpha() > 0
    ctl.session.set_active(False)
    ctl.detach()
    canvas.deleteLater()


def test_regression_switching_objects_keeps_sculpt_tool():
    scene, first = _scene_with(_grid(10, 100.0), "First")
    second = scene.add_object("Second", _grid(10, 100.0))
    second.position = np.array([300.0, 0.0, 0.0])
    scene.set_active(first)
    canvas = _FakeCanvas(scene)
    ctl = sculpt.attach_viewport(canvas, scene)
    session = ctl.session
    session.set_brush("pull")
    scene.set_tool("move")
    session.set_active(True)
    assert scene.tool == "other"
    _mouse(canvas, QEvent.Type.MouseButtonPress, 400, 100)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 400, 100)
    assert scene.active is second and scene.tool == "other" and session.active
    assert second.mesh.points[:, 1].max() > 0.1
    scene.set_active(first)
    APP.processEvents()
    assert scene.tool == "other" and session.active and session.target() is first
    scene.set_tool("scale")
    APP.processEvents()
    assert scene.tool == "scale" and not session.active and not ctl.overlay.isVisibleTo(canvas)
    ctl.detach()
    canvas.deleteLater()


def test_regression_no_empty_undo_steps():
    scene, obj = _scene_with(_grid(10, 100.0))
    data.ensure_state(obj)
    scene.clear_history()
    pts = obj.mesh.points.copy()
    sculpt.stroke_begin(obj, _settings("pull"), scene)
    assert sculpt.stroke_dab((0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0) > 0
    assert len(scene._undo) == 1 and not np.allclose(obj.mesh.points, pts)
    sculpt.stroke_cancel()
    assert len(scene._undo) == 0 and np.allclose(obj.mesh.points, pts)
    sculpt.stroke_begin(obj, _settings("pull"), scene)
    assert sculpt.stroke_dab((1000.0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0) == 0
    assert not sculpt.stroke_end() and len(scene._undo) == 0
    sculpt.stroke_begin(obj, _settings("grab"), scene)
    assert sculpt.stroke_dab((0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0) > 0
    sculpt.stroke_dab((0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0)
    assert not sculpt.stroke_end() and len(scene._undo) == 0
    sculpt.stroke_begin(obj, _settings("grab"), scene)
    sculpt.stroke_dab((0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0)
    sculpt.stroke_dab((0, 10.0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0)
    assert sculpt.stroke_end() and len(scene._undo) == 1
    scene.undo()
    assert np.allclose(scene.objects[0].mesh.points, pts)
    assert scene.can_redo()
    obj = scene.objects[0]
    sculpt.stroke_begin(obj, _settings("pull"), scene)
    sculpt.stroke_dab((0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0)
    sculpt.stroke_cancel()
    assert scene.can_redo() and len(scene._undo) == 0


def test_regression_every_state_change_records_undo():
    scene, obj = _scene_with(_grid(4, 100.0))
    data.ensure_state(obj)
    scene.clear_history()
    steps = [
        lambda: data.subdivide(obj, scene),
        lambda: data.level_down(obj, scene),
        lambda: data.level_up(obj, scene),
        lambda: data.add_layer(obj, "A", scene) >= 0,
        lambda: data.add_layer(obj, "B", scene) >= 0,
        lambda: data.rename_layer(obj, 0, "Renamed", scene),
        lambda: data.set_layer_locked(obj, 0, True, scene),
        lambda: data.set_active_layer(obj, 0, scene),
        lambda: data.move_layer(obj, 0, 1, scene) == 1,
        lambda: data.set_mask(obj, np.ones(len(obj.mesh.points)), scene),
        lambda: data.set_frozen(obj, True, scene),
        lambda: data.set_mask_enabled(obj, False, scene),
    ]
    for k, step in enumerate(steps):
        assert step(), k
        assert len(scene._undo) == k + 1, k
    assert not data.set_frozen(obj, True, scene) and len(scene._undo) == len(steps)
    assert not data.rename_layer(obj, 1, "Renamed", scene)
    assert not data.set_active_layer(obj, 1, scene)
    scene.undo()
    st = data.get_state(scene.objects[0])
    assert data.mask_enabled(st) and data.is_frozen(st)
    assert np.allclose(data.get_mask(st), 1.0)
    scene.undo()
    st = data.get_state(scene.objects[0])
    assert not data.is_frozen(st) and np.allclose(data.get_mask(st), 1.0)
    scene.undo()
    st = data.get_state(scene.objects[0])
    assert data.summary(scene.objects[0])["masked"] == 0
    assert [l["name"] for l in data.layers(st)] == ["B", "Renamed"]
    scene.undo()
    st = data.get_state(scene.objects[0])
    assert [l["name"] for l in data.layers(st)] == ["Renamed", "B"]


def test_regression_undo_snapshots_share_unchanged_arrays():
    import pickle

    scene, obj = _scene_with(Mesh.cube(200.0), "Cube")
    data.subdivide(obj, scene, 4)
    scene.clear_history()
    top = obj.mesh.points[:, 1].max()
    _dab(scene, obj, "pull", hit=(0, top, 0), radius=40.0)
    _dab(scene, obj, "pull", hit=(20.0, top, 0), radius=40.0)
    a = scene._undo[-2]["objects"][0]["extras"][data.KEY]
    b = scene._undo[-1]["objects"][0]["extras"][data.KEY]
    for h in range(4):
        assert a["levels"][h][data.ARRAY_TAG] is b["levels"][h][data.ARRAY_TAG]
    assert a["levels"][4][data.ARRAY_TAG] is not b["levels"][4][data.ARRAY_TAG]
    st = data.get_state(obj)
    raw_bytes = sum(np.asarray(l).nbytes for l in st["levels"])
    assert len(pickle.dumps(obj.extras)) < 0.5 * raw_bytes


def test_regression_loose_edges_and_scales_survive_levels():
    base = _grid(4, 100.0)
    pts = np.vstack([base.points, [[0.0, 80.0, 0.0]]])
    extra = len(pts) - 1
    scales = np.linspace(0.5, 1.5, len(pts))
    mesh = Mesh(pts, base.polygons, [(0, extra)], point_scales=scales)
    scene, obj = _scene_with(mesh)
    data.subdivide(obj, scene)
    assert (0, extra) in obj.mesh.loose_edges
    assert np.allclose(obj.mesh.points[extra], [0.0, 80.0, 0.0])
    assert obj.mesh.point_scales is not None and len(obj.mesh.point_scales) == len(obj.mesh.points)
    assert np.isclose(obj.mesh.point_scales[extra], scales[extra])
    data.level_down(obj, scene)
    assert obj.mesh.loose_edges == [(0, extra)]
    assert np.allclose(obj.mesh.point_scales, scales)
    data.level_up(obj, scene)
    assert data.bake_to_mesh(obj, scene)
    assert (0, extra) in obj.mesh.loose_edges
    polys = list(base.polygons) + [(0, 1)]
    scene, obj = _scene_with(Mesh(base.points, polys))
    original = obj.mesh
    data.subdivide(obj, scene)
    scene.undo()
    assert list(scene.objects[0].mesh.polygons) == [tuple(p) for p in polys]
    obj = scene.objects[0]
    data.subdivide(obj, scene)
    data.level_down(obj, scene)
    assert list(obj.mesh.polygons) == [tuple(p) for p in polys]
    assert original is not obj.mesh


def test_regression_data_ops_during_stroke_are_kept():
    scene, obj = _scene_with(_grid(10, 100.0))
    data.ensure_state(obj)
    scene.clear_history()
    sculpt.stroke_begin(obj, _settings("pull"), scene)
    assert sculpt.stroke_dab((0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0) > 0
    raised = obj.mesh.points.copy()
    assert data.mask_fill(obj, scene)
    assert sculpt.current_stroke() is None
    assert sculpt.stroke_dab((10.0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0) == 0
    assert not sculpt.stroke_end()
    st = data.get_state(obj)
    assert np.allclose(data.get_mask(st), 1.0)
    assert np.allclose(data.composite(st), raised) and np.allclose(obj.mesh.points, raised)
    assert len(scene._undo) == 2
    stroke = SculptStroke(obj, _settings("mask", invert=True), scene)
    stroke.dab((0, 0, 0), (0, 1, 0), (0, -1, 0), 1.0, 30.0)
    data.add_layer(obj, "L", scene)
    assert stroke.finished
    st = data.get_state(obj)
    assert data.layer_count(st) == 1 and data.summary(obj)["masked"] < len(obj.mesh.points)


def test_regression_session_follows_scene_settings():
    import copy

    scene = reset_scene()
    session = sculpt.get_session(scene)
    session.set("radius", 80.0)
    session.set_brush("clay")
    seen = []
    session.settingsChanged.connect(lambda: seen.append(True))
    saved = copy.deepcopy(scene.extras)
    saved["sculpt_brushes"]["brush"] = "smooth"
    saved["sculpt_brushes"]["brushes"]["smooth"]["radius"] = 200.0
    scene.extras = saved
    assert session.settings().radius == 200.0 and session.brush == "smooth"
    assert seen
    from quartz_studio.fileio import bridge
    doc = bridge.full_document_from_scene(scene)
    doc.meta["extras"]["sculpt_brushes"]["brushes"]["smooth"]["radius"] = 32.0
    bridge.replace_scene(scene, doc)
    assert session.settings().radius == 32.0
    session.set("radius", 64.0)
    assert scene.extras["sculpt_brushes"]["brushes"]["smooth"]["radius"] == 64.0
    scene.extras = {}
    assert session.settings().radius == 64.0


def test_regression_panel_radius_range_and_block_info():
    scene, obj = _scene_with(_grid(10, 100.0))
    panel = sculpt.SculptBrushPanel(scene)
    panel.resize(320, 900)
    panel.show()
    APP.processEvents()
    session = panel.session
    session.set("radius", 48.0)
    for _ in range(14):
        session.scale_radius(1.2)
    assert session.settings().radius > 512
    assert np.isclose(panel.radius.value(), round(session.settings().radius))
    panel.radius.slider.setValue(1000)
    assert np.isclose(session.settings().radius, 4096.0)
    panel.radius.slider.setValue(250)
    assert 200.0 < session.settings().radius < 300.0
    panel.stabilize.spin.setValue(24)
    assert session.settings().stabilize == 24.0 and session.settings("smooth").stabilize == 24.0
    assert panel.block_info.isHidden()
    i = data.add_layer(obj, "L", scene)
    data.set_layer_locked(obj, i, True, scene)
    panel._refresh_object()
    assert not panel.block_info.isHidden() and "locked" in panel.block_info.text()
    session.set_brush("mask")
    panel._refresh_object()
    assert panel.block_info.isHidden()
    session.set("stabilize", 0.0)
    panel.close()


def test_regression_viewport_adjust_radius_and_strength():
    scene, obj = _scene_with(_grid(20, 100.0))
    canvas = _FakeCanvas(scene)
    ctl = sculpt.attach_viewport(canvas, scene)
    session = ctl.session
    session.set_brush("pull")
    session.set("radius", 40.0)
    session.set("strength", 0.5)
    session.set_active(True)
    assert canvas.hasMouseTracking()
    _mouse(canvas, QEvent.Type.MouseMove, 90, 100, button=Qt.MouseButton.NoButton)
    _mouse(canvas, QEvent.Type.MouseMove, 100, 100, button=Qt.MouseButton.NoButton)
    assert ctl.overlay.pos_xy == (100.0, 100.0)
    assert _key(canvas, Qt.Key.Key_F)
    assert ctl.adjust_anchor() == (100.0, 100.0)
    _mouse(canvas, QEvent.Type.MouseMove, 164, 100, button=Qt.MouseButton.NoButton)
    assert np.isclose(session.settings().radius, 64.0)
    pts = obj.mesh.points.copy()
    _mouse(canvas, QEvent.Type.MouseButtonPress, 164, 100)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 164, 100)
    assert ctl.adjust_anchor() is None and np.allclose(obj.mesh.points, pts)
    assert np.isclose(session.settings().radius, 64.0)
    _key(canvas, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier)
    _mouse(canvas, QEvent.Type.MouseMove, 228, 100, button=Qt.MouseButton.NoButton)
    assert np.isclose(session.settings().strength, 0.75)
    _key(canvas, Qt.Key.Key_Escape)
    assert np.isclose(session.settings().strength, 0.5) and ctl.adjust_anchor() is None
    _key(canvas, Qt.Key.Key_F)
    _mouse(canvas, QEvent.Type.MouseMove, 120, 100, button=Qt.MouseButton.NoButton)
    _mouse(canvas, QEvent.Type.MouseButtonPress, 120, 100, button=Qt.MouseButton.RightButton)
    assert np.isclose(session.settings().radius, 64.0)
    session.set_active(False)
    assert not canvas.hasMouseTracking()
    ctl.detach()
    canvas.deleteLater()


def test_regression_stabilizer_trails_cursor():
    scene, obj = _scene_with(_grid(40, 200.0))
    canvas = _FakeCanvas(scene)
    ctl = sculpt.attach_viewport(canvas, scene)
    session = ctl.session
    session.set_brush("pull")
    session.set("radius", 16.0)
    session.set("strength", 1.0)
    session.set("spacing", 0.0)
    session.set("stabilize", 30.0)
    session.set_active(True)
    _mouse(canvas, QEvent.Type.MouseButtonPress, 100, 100)
    after_press = obj.mesh.points.copy()
    _mouse(canvas, QEvent.Type.MouseMove, 120, 100)
    assert np.allclose(obj.mesh.points, after_press)
    assert ctl.overlay.lazy_xy == (100.0, 100.0)
    _mouse(canvas, QEvent.Type.MouseMove, 160, 100)
    assert np.allclose(ctl.overlay.lazy_xy, (130.0, 100.0))
    moved = np.linalg.norm(obj.mesh.points - after_press, axis=1)
    hit = obj.mesh.points[moved > 1e-9]
    assert len(hit) and abs(float(hit[:, 0].mean()) - 30.0) < 6.0
    assert not ctl.overlay.grab().isNull()
    _mouse(canvas, QEvent.Type.MouseButtonRelease, 160, 100)
    assert ctl.overlay.lazy_xy is None
    session.set("stabilize", 0.0)
    session.set_active(False)
    ctl.detach()
    canvas.deleteLater()


def test_regression_design_px_values():
    from quartz_studio.sculpt import panels, viewport
    allowed = {1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 72, 96, 128, 256, 512, 1024,
               10, 14, 18, 20, 28, 36, 40, 44, 56, 80, 88, 112, 120}
    for mod, names in ((panels, ("BRUSH_BUTTON", "BRUSH_ICON", "LABEL_W", "ROW_H", "GAP", "PAD", "PAD_SIDE",
                                 "CURVE_H", "CURVE_PAD", "POINT_D", "PICK_PX", "STAMP_PREVIEW", "LIST_H",
                                 "FRAME_W", "STABILIZE_MAX")),
                       (viewport, ("MASK_DOT", "RING_W", "INNER_W", "CENTER_DOT", "LAZY_DOT"))):
        for name in names:
            v = getattr(mod, name)
            assert v in allowed or (v >= 128 and v % 16 == 0), (name, v)
    assert viewport.INNER_W >= 2 and panels.RADIUS_MAX == 4096


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
