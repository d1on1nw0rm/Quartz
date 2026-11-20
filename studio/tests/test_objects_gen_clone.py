from __future__ import annotations

import math
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio import objects
from quartz_studio.objects import registry
from quartz_studio.objects.registry import BuildInput, ObjectSpec, Param
from quartz_studio.scene import Mesh, Scene


def _uv_sphere(radius: float, rings: int = 12, segs: int = 16) -> Mesh:
    pts = [(0.0, radius, 0.0)]
    for i in range(1, rings):
        phi = math.pi * i / rings
        for j in range(segs):
            th = 2.0 * math.pi * j / segs
            pts.append((radius * math.sin(phi) * math.cos(th), radius * math.cos(phi),
                        radius * math.sin(phi) * math.sin(th)))
    pts.append((0.0, -radius, 0.0))
    last = len(pts) - 1
    polys = []
    for j in range(segs):
        polys.append((0, 1 + (j + 1) % segs, 1 + j))
    for i in range(rings - 2):
        for j in range(segs):
            a = 1 + i * segs + j
            b = 1 + i * segs + (j + 1) % segs
            polys.append((a, b, b + segs, a + segs))
    base = 1 + (rings - 2) * segs
    for j in range(segs):
        polys.append((last, base + j, base + (j + 1) % segs))
    return Mesh(pts, polys)


def _sphere_build(p: dict, _inputs: list) -> Mesh:
    if p["radius"] <= 0:
        return Mesh.empty()
    return _uv_sphere(float(p["radius"]))


SPHERE = registry.register(ObjectSpec(
    "test_gen_clone_sphere", "Test Sphere", "mesh", _sphere_build,
    params=(Param("radius", "Radius", "distance", 100.0, minimum=0.0),)))


def _box(lo, hi) -> Mesh:
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    pts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
           (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    polys = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3), (1, 2, 6, 5), (3, 7, 6, 2), (0, 1, 5, 4)]
    return Mesh(pts, polys)


def _tetra(scale: float = 10.0) -> Mesh:
    s = scale
    pts = [(s, s, s), (s, -s, -s), (-s, s, -s), (-s, -s, s)]
    polys = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    return Mesh(pts, polys)


def _inp(mesh: Mesh, name: str = "child", kind: str = "polygon") -> BuildInput:
    return BuildInput(mesh, name, kind)


def _build(spec_id: str, inputs: list, **values) -> Mesh:
    spec = registry.get(spec_id)
    return spec.build(spec.clamp(values), inputs)


def _scene() -> Scene:
    QApplication.instance() or QApplication([sys.argv[0]])
    return scene_mod.reset_scene()


def _volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        pts = mesh.points[list(poly)]
        for k in range(1, len(poly) - 1):
            total += float(np.dot(pts[0], np.cross(pts[k], pts[k + 1]))) / 6.0
    return total


def _closed(mesh: Mesh) -> bool:
    directed: dict[tuple[int, int], int] = {}
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            directed[(a, b)] = directed.get((a, b), 0) + 1
    if any(v != 1 for v in directed.values()):
        return False
    return all((b, a) in directed for a, b in directed)


def _valid(mesh: Mesh) -> bool:
    if len(mesh.points) == 0:
        return not mesh.polygons
    used = {i for poly in mesh.polygons for i in poly} | {i for e in mesh.loose_edges for i in e}
    if used != set(range(len(mesh.points))):
        return False
    if len({tuple(np.round(p, 6)) for p in mesh.points}) != len(mesh.points):
        return False
    for poly in mesh.polygons:
        if len(set(poly)) != len(poly) or len(poly) < 3:
            return False
        pts = mesh.points[list(poly)]
        nxt = np.roll(pts, -1, axis=0)
        newell = np.array([np.sum((pts[:, 1] - nxt[:, 1]) * (pts[:, 2] + nxt[:, 2])),
                           np.sum((pts[:, 2] - nxt[:, 2]) * (pts[:, 0] + nxt[:, 0])),
                           np.sum((pts[:, 0] - nxt[:, 0]) * (pts[:, 1] + nxt[:, 1]))])
        if np.linalg.norm(newell) < 1e-9:
            return False
    return True


def _components(mesh: Mesh) -> int:
    parent = list(range(len(mesh.points)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for poly in mesh.polygons:
        for i in poly[1:]:
            parent[find(i)] = find(poly[0])
    return len({find(i) for poly in mesh.polygons for i in poly})


def _bounds(mesh: Mesh):
    return mesh.points.min(axis=0), mesh.points.max(axis=0)


def _close(a, b, tol=1e-6) -> bool:
    return bool(np.allclose(a, b, atol=tol))


def _centroids(mesh: Mesh, per: int) -> np.ndarray:
    return mesh.points.reshape(-1, per, 3).mean(axis=1)


def test_specs_registered_with_contract():
    for sid, label in (("cloner", "Cloner"), ("array", "Array"), ("fracture", "Fracture"),
                       ("metaball", "Metaball")):
        spec = registry.get(sid)
        assert spec.label == label and spec.category == "generator" and spec.inputs == "children"
        assert spec in registry.by_category("generator")
    cl = registry.defaults("cloner")
    assert cl["mode"] == "Linear" and cl["clones"] == "Iterate" and cl["linear_count"] == 3
    assert cl["linear_position"] == (0.0, 50.0, 0.0) and cl["linear_scale"] == (100.0, 100.0, 100.0)
    assert cl["linear_rotation"] == (0.0, 0.0, 0.0) and cl["radial_count"] == 5
    assert cl["radial_radius"] == 50.0 and cl["radial_plane"] == "XZ" and cl["radial_align"] is True
    assert cl["radial_start"] == 0.0 and cl["radial_end"] == 360.0
    assert cl["grid_count"] == (3.0, 1.0, 3.0) and cl["grid_size"] == (200.0, 200.0, 200.0)
    assert registry.get("cloner").param("mode").choices == ("Linear", "Radial", "Grid Array")
    assert registry.get("cloner").param("radial_plane").choices == ("XY", "ZY", "XZ")
    ar = registry.defaults("array")
    assert (ar["radius"], ar["copies"], ar["amplitude"], ar["frequency"]) == (250.0, 7, 0.0, 0.0)
    fr = registry.get("fracture")
    assert fr.defaults() == {"mode": "Straight", "offset": 0.0}
    assert fr.param("mode").choices == ("Straight", "Explode Segments", "Explode Segments and Connect")
    mb = registry.get("metaball")
    assert mb.defaults() == {"hull_value": 100.0, "editor_subdivision": 20.0}
    assert mb.param("editor_subdivision").clamp(0.5) == 2.0
    assert objects.get is registry.get


def test_no_children_gives_empty_mesh():
    for sid in ("cloner", "array", "fracture", "metaball"):
        m = _build(sid, [])
        assert isinstance(m, Mesh) and len(m.points) == 0 and not m.polygons
        m = _build(sid, [_inp(Mesh.empty())])
        assert len(m.points) == 0


def test_cloner_linear_default_counts_and_positions():
    cube = _box((-50, -50, -50), (50, 50, 50))
    m = _build("cloner", [_inp(cube)])
    assert len(m.points) == 24 and len(m.polygons) == 18
    assert _closed(m)
    c = _centroids(m, 8)
    assert _close(c, [(0, 0, 0), (0, 50, 0), (0, 100, 0)])
    lo, hi = _bounds(m)
    assert _close(lo, (-50, -50, -50)) and _close(hi, (50, 150, 50))
    m = _build("cloner", [_inp(cube)], linear_count=6, linear_position=(10, 0, 20))
    assert len(m.points) == 48 and _close(_centroids(m, 8)[5], (50, 0, 100))


def test_cloner_linear_scale_and_rotation_step():
    box = _box((-10, -10, -50), (10, 10, 50))
    m = _build("cloner", [_inp(box)], linear_count=3, linear_position=(0, 0, 0),
               linear_scale=(200, 200, 200))
    c = _centroids(m, 8)
    assert _close(c, np.zeros((3, 3)))
    sizes = [np.ptp(m.points[8 * k:8 * k + 8], axis=0) for k in range(3)]
    assert _close(sizes[0], (20, 20, 100)) and _close(sizes[1], (40, 40, 200))
    assert _close(sizes[2], (80, 80, 400))
    m = _build("cloner", [_inp(box)], linear_count=2, linear_position=(0, 0, 0),
               linear_rotation=(90, 0, 0))
    second = m.points[8:16]
    assert _close(np.ptp(second, axis=0), (100, 20, 20))
    assert abs(_volume(Mesh(second, box.polygons)) - _volume(box)) < 1e-6


def test_cloner_iterates_children_in_order():
    a, b = _box((-5, -5, -5), (5, 5, 5)), _tetra(7.0)
    m = _build("cloner", [_inp(a, "a"), _inp(b, "b")], linear_count=5)
    assert len(m.points) == 8 + 4 + 8 + 4 + 8 and len(m.polygons) == 6 + 4 + 6 + 4 + 6
    assert _valid(m)
    first_b = m.points[8:12]
    assert _close(first_b, b.points + (0, 50, 0))
    m = _build("cloner", [_inp(a, "a"), _inp(b, "b")], linear_count=1)
    assert len(m.points) == 8


def test_cloner_radial_counts_plane_and_angles():
    marker = _tetra(5.0)
    m = _build("cloner", [_inp(marker)], mode="Radial")
    assert len(m.points) == 20 and len(m.polygons) == 20 and _valid(m)
    c = _centroids(m, 4)
    for k in range(5):
        a = math.radians(72 * k)
        assert _close(c[k], (50 * math.cos(a), 0, 50 * math.sin(a)), 1e-9)
    m = _build("cloner", [_inp(marker)], mode="Radial", radial_plane="XY", radial_count=4,
               radial_radius=80)
    c = _centroids(m, 4)
    assert _close(c[1], (0, 80, 0), 1e-9) and _close(c[2], (-80, 0, 0), 1e-9)
    m = _build("cloner", [_inp(marker)], mode="Radial", radial_plane="ZY", radial_count=4,
               radial_radius=80)
    c = _centroids(m, 4)
    assert _close(c[1], (0, 80, 0), 1e-9) and _close(c[0], (0, 0, 80), 1e-9)
    m = _build("cloner", [_inp(marker)], mode="Radial", radial_count=3, radial_start=0,
               radial_end=90, radial_radius=100)
    c = _centroids(m, 4)
    assert len(c) == 3 and _close(c[0], (100, 0, 0), 1e-9) and _close(c[2], (0, 0, 100), 1e-9)


def test_cloner_radial_align_toggle():
    arrow = Mesh([(100, 0, 0), (0, 5, 0), (0, -5, 0), (0, 0, 5)],
                 [(0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)])
    aligned = _build("cloner", [_inp(arrow)], mode="Radial", radial_count=4, radial_radius=200)
    flat = _build("cloner", [_inp(arrow)], mode="Radial", radial_count=4, radial_radius=200,
                  radial_align=False)
    for k in range(4):
        a = math.pi / 2 * k
        tip = aligned.points[4 * k]
        assert _close(tip[[0, 2]], (300 * math.cos(a), 300 * math.sin(a)), 1e-9)
        assert _close(flat.points[4 * k], (100 + 200 * math.cos(a), 0, 200 * math.sin(a)), 1e-9)


def test_cloner_grid_array_counts_and_bounds():
    cube = _box((-10, -10, -10), (10, 10, 10))
    m = _build("cloner", [_inp(cube)], mode="Grid Array")
    assert len(m.points) == 9 * 8 and len(m.polygons) == 9 * 6 and _valid(m)
    c = _centroids(m, 8)
    assert sorted({round(v, 6) for v in c[:, 0]}) == [-100, 0, 100]
    assert sorted({round(v, 6) for v in c[:, 1]}) == [0]
    assert sorted({round(v, 6) for v in c[:, 2]}) == [-100, 0, 100]
    lo, hi = _bounds(m)
    assert _close(lo, (-110, -10, -110)) and _close(hi, (110, 10, 110))
    m = _build("cloner", [_inp(cube)], mode="Grid Array", grid_count=(2, 2, 2),
               grid_size=(60, 40, 20))
    assert len(m.points) == 64
    lo, hi = _bounds(m)
    assert _close(lo, (-40, -30, -20)) and _close(hi, (40, 30, 20))
    m = _build("cloner", [_inp(cube)], mode="Grid Array", grid_count=(1, 1, 1))
    assert len(m.points) == 8 and _close(_bounds(m)[0], (-10, -10, -10))


def test_cloner_keeps_splines_and_clamps_count():
    line = Mesh([(0, 0, 0), (10, 0, 0), (10, 10, 0)], [], [(0, 1), (1, 2)])
    m = _build("cloner", [_inp(line)], linear_count=4)
    assert len(m.points) == 12 and not m.polygons and len(m.loose_edges) == 8
    big = _build("cloner", [_inp(_tetra())], linear_count=100000)
    assert len(big.points) == 4 * 2000


def test_array_counts_circle_and_facing():
    arrow = Mesh([(100, 0, 0), (0, 5, 0), (0, -5, 0), (0, 0, 5)],
                 [(0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)])
    m = _build("array", [_inp(arrow)])
    assert len(m.points) == 28 and len(m.polygons) == 28 and _valid(m)
    for k in range(7):
        a = 2 * math.pi * k / 7
        base = m.points[4 * k + 1:4 * k + 3].mean(axis=0)
        assert _close(base[[0, 2]], (250 * math.cos(a), 250 * math.sin(a)), 1e-9)
        tip = m.points[4 * k]
        assert abs(math.hypot(tip[0], tip[2]) - 350.0) < 1e-9
    two = _build("array", [_inp(arrow), _inp(_tetra())], copies=3)
    assert len(two.points) == 3 * 8


def test_array_wave_amplitude_and_frequency():
    marker = _tetra(2.0)
    m = _build("array", [_inp(marker)], copies=8, amplitude=30, frequency=1)
    c = _centroids(m, 4)
    for k in range(8):
        assert abs(c[k][1] - 30 * math.sin(2 * math.pi * k / 8)) < 1e-9
    flat = _build("array", [_inp(marker)], copies=8, amplitude=30, frequency=0)
    assert _close(_centroids(flat, 4)[:, 1], 0.0)
    one = _build("array", [_inp(marker)], copies=1, radius=0)
    assert len(one.points) == 4 and _close(_centroids(one, 4), [(0, 0, 0)])


def test_fracture_straight_merges_children():
    a, b = _box((-5, -5, -5), (5, 5, 5)), _tetra(3.0)
    m = _build("fracture", [_inp(a), _inp(b)])
    assert len(m.points) == 12 and len(m.polygons) == 10
    assert _close(m.points[:8], a.points) and _close(m.points[8:], b.points)
    far = _build("fracture", [_inp(a), _inp(b)], offset=500)
    assert _close(far.points, m.points)


def test_fracture_explode_segments_moves_parts_apart():
    two = Mesh(np.vstack([_box((-60, -5, -5), (-40, 5, 5)).points,
                          _box((40, -5, -5), (60, 5, 5)).points]),
               [tuple(i for i in poly) for poly in _box((0, 0, 0), (1, 1, 1)).polygons]
               + [tuple(i + 8 for i in poly) for poly in _box((0, 0, 0), (1, 1, 1)).polygons])
    same = _build("fracture", [_inp(two)], mode="Explode Segments")
    assert len(same.points) == 16 and len(same.polygons) == 12 and _close(same.points, two.points)
    m = _build("fracture", [_inp(two)], mode="Explode Segments", offset=100)
    assert len(m.points) == 16 and len(m.polygons) == 12 and _valid(m)
    left, right = m.points[:8].mean(axis=0), m.points[8:].mean(axis=0)
    assert _close(left, (-150, 0, 0)) and _close(right, (150, 0, 0))
    assert _close(np.ptp(m.points[:8], axis=0), (20, 10, 10))
    pulled = _build("fracture", [_inp(two)], mode="Explode Segments", offset=-20)
    assert _close(pulled.points[:8].mean(axis=0), (-30, 0, 0))


def test_fracture_explode_splits_children_and_keeps_loose_edges():
    a = _box((-30, -5, -5), (-20, 5, 5))
    b = Mesh([(40, 0, 0), (60, 0, 0)], [], [(0, 1)])
    m = _build("fracture", [_inp(a), _inp(b)], mode="Explode Segments", offset=50)
    assert len(m.points) == 10 and len(m.polygons) == 6 and m.loose_edges == [(8, 9)]
    assert m.points[:8].mean(axis=0)[0] < -25.0 - 49.0
    assert m.points[8:].mean(axis=0)[0] > 50.0 + 49.0


def test_fracture_connect_welds_touching_parts():
    a, b = _box((-10, -10, -10), (0, 10, 10)), _box((0, -10, -10), (10, 10, 10))
    split = _build("fracture", [_inp(a), _inp(b)], mode="Explode Segments")
    assert len(split.points) == 16
    joined = _build("fracture", [_inp(a), _inp(b)], mode="Explode Segments and Connect")
    assert len(joined.points) == 12 and len(joined.polygons) == 12 and _valid(joined)
    apart = _build("fracture", [_inp(a), _inp(b)], mode="Explode Segments and Connect", offset=30)
    assert len(apart.points) == 16


def test_metaball_single_sphere_is_closed_manifold():
    sphere = _inp(_uv_sphere(100.0), "ball", "test_gen_clone_sphere")
    t0 = time.time()
    m = _build("metaball", [sphere])
    assert time.time() - t0 < 2.0
    assert len(m.points) > 50 and _valid(m) and _closed(m)
    assert len(m.points) - len(m.edges) + len(m.polygons) == 2
    vol = _volume(m)
    assert vol > 0
    lo, hi = _bounds(m)
    assert np.all(hi - lo > 150.0) and np.all(hi - lo < 260.0)
    assert abs(vol - 4.0 / 3.0 * math.pi * 100.0 ** 3) / (4.0 / 3.0 * math.pi * 100.0 ** 3) < 0.35
    centre = (lo + hi) / 2.0
    assert np.linalg.norm(centre) < 12.0
    for k, poly in enumerate(m.polygons):
        pts = m.points[list(poly)]
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        assert float(n @ (pts.mean(axis=0) - centre)) > 0.0


def test_metaball_hull_value_and_subdivision():
    sphere = _inp(_uv_sphere(100.0), "ball", "test_gen_clone_sphere")
    base = _volume(_build("metaball", [sphere]))
    small = _volume(_build("metaball", [sphere], hull_value=150))
    large = _volume(_build("metaball", [sphere], hull_value=60))
    assert small < base < large
    fine = _build("metaball", [sphere], editor_subdivision=8)
    coarse = _build("metaball", [sphere], editor_subdivision=40)
    assert len(fine.polygons) > len(coarse.polygons) > 0
    assert _closed(fine) and _closed(coarse) and _volume(fine) > 0 and _volume(coarse) > 0
    assert _build("metaball", [sphere], editor_subdivision=0.1).polygons


def test_metaball_two_overlapping_children_merge():
    a = _inp(_uv_sphere(100.0), "a", "test_gen_clone_sphere")
    moved = _uv_sphere(100.0)
    moved.points = moved.points + np.array([120.0, 0.0, 0.0])
    b = _inp(moved, "b", "test_gen_clone_sphere")
    one = _build("metaball", [a])
    two = _build("metaball", [a, b])
    assert _valid(two) and _closed(two) and _components(two) == 1
    assert len(two.points) - len(two.edges) + len(two.polygons) == 2
    assert _volume(two) > _volume(one) * 1.3
    lo, hi = _bounds(two)
    assert hi[0] - lo[0] > 300.0 and abs((lo[0] + hi[0]) / 2.0 - 60.0) < 15.0
    far = moved.points + np.array([800.0, 0.0, 0.0])
    split = _build("metaball", [a, _inp(Mesh(far, moved.polygons), "far", "test_gen_clone_sphere")])
    assert _closed(split) and _components(split) == 2 and _volume(split) > 0


def test_metaball_mesh_child_through_points():
    cube = _inp(_box((-100, -100, -100), (100, 100, 100)), "cube")
    m = _build("metaball", [cube])
    assert _valid(m) and _closed(m) and _volume(m) > 0 and _components(m) == 1
    lo, hi = _bounds(m)
    assert np.all(hi - lo > 200.0)
    second = _inp(_box((50, -100, -100), (250, 100, 100)), "cube2")
    both = _build("metaball", [cube, second])
    assert _valid(both) and _closed(both) and _volume(both) > _volume(m) and _components(both) == 1
    dense = _inp(_uv_sphere(80.0, 24, 32), "dense")
    d = _build("metaball", [dense])
    assert _valid(d) and _closed(d) and _volume(d) > 0


def test_metaball_cell_count_is_bounded():
    huge = _inp(_uv_sphere(100000.0), "huge", "test_gen_clone_sphere")
    t0 = time.time()
    m = _build("metaball", [huge], editor_subdivision=2)
    assert time.time() - t0 < 3.0
    assert len(m.polygons) > 0 and len(m.polygons) < 400000 and _closed(m) and _volume(m) > 0
    many = [_inp(_uv_sphere(30.0), f"s{k}", "test_gen_clone_sphere") for k in range(30)]
    for k, inp in enumerate(many):
        inp.mesh.points = inp.mesh.points + np.array([25.0 * k, 0.0, 0.0])
    t0 = time.time()
    m = _build("metaball", many, editor_subdivision=2)
    assert time.time() - t0 < 3.0 and _closed(m) and _volume(m) > 0


def test_cloner_through_scene_with_real_children():
    scene = _scene()
    cube = scene.objects[0]
    cloner = scene.add_parametric("cloner", adopt=cube)
    assert cube.parent is cloner and cube not in scene.render_objects()
    assert cloner in scene.render_objects() and not cloner.error
    assert len(cloner.mesh.points) == 24 and len(cloner.mesh.polygons) == 18
    lo, hi = _bounds(cloner.mesh)
    assert _close(lo, (-100, -100, -100)) and _close(hi, (100, 200, 100))
    assert scene.set_param(cloner, "mode", "Grid Array")
    assert len(cloner.mesh.points) == 72
    assert scene.set_param(cloner, "mode", "Radial")
    assert len(cloner.mesh.points) == 40 and _valid(cloner.mesh)
    cube.position = np.array([0.0, 300.0, 0.0])
    scene.changed.emit()
    assert _bounds(cloner.mesh)[0][1] > 150.0
    second = scene.add_parametric("test_gen_clone_sphere", parent=cloner)
    assert second.parent is cloner
    assert scene.set_param(cloner, "mode", "Linear")
    assert len(cloner.mesh.points) == 8 + len(second.mesh.points) + 8


def test_array_fracture_through_scene():
    scene = _scene()
    cube = scene.objects[0]
    arr = scene.add_parametric("array", adopt=cube)
    assert len(arr.mesh.points) == 56 and not arr.error and _valid(arr.mesh)
    assert scene.set_param(arr, "copies", 3) and len(arr.mesh.points) == 24
    lo, hi = _bounds(arr.mesh)
    assert hi[0] > 340.0 and lo[0] < -90.0
    scene.set_param(arr, "radius", 0)
    root = scene.add_parametric("null", name="Box")
    frac = scene.add_parametric("fracture", adopt=arr)
    assert arr.parent is frac and root.parent is None
    assert len(frac.mesh.points) == len(arr.mesh.points)
    scene.set_param(arr, "radius", 400)
    scene.set_param(frac, "mode", "Explode Segments")
    scene.set_param(frac, "offset", 100)
    assert len(frac.mesh.points) == 24
    straight = frac.mesh.points.copy()
    scene.set_param(frac, "offset", 0)
    assert not _close(straight, frac.mesh.points)


def test_metaball_through_scene():
    scene = _scene()
    sphere = scene.add_parametric("test_gen_clone_sphere")
    ball = scene.add_parametric("metaball", adopt=sphere)
    assert sphere.parent is ball and not ball.error
    assert _closed(ball.mesh) and _volume(ball.mesh) > 0
    sphere.position = np.array([200.0, 0.0, 0.0])
    scene.changed.emit()
    assert abs(np.mean(_bounds(ball.mesh)[0][0] + _bounds(ball.mesh)[1][0]) / 2.0 - 200.0) < 15.0
    other = scene.add_parametric("test_gen_clone_sphere", parent=ball)
    other.position = np.array([600.0, 0.0, 0.0])
    scene.changed.emit()
    assert _closed(ball.mesh) and _components(ball.mesh) == 2
    scene.set_param(other, "radius", 0)
    assert _components(ball.mesh) == 1


def test_undo_redo_of_generators():
    scene = _scene()
    cube = scene.objects[0]
    cloner = scene.add_parametric("cloner", adopt=cube)
    assert len(cloner.mesh.points) == 24
    scene.set_param(cloner, "linear_count", 5)
    assert len(cloner.mesh.points) == 40
    assert scene.undo()
    cloner = next(o for o in scene.objects if o.kind == "cloner")
    assert cloner.params["linear_count"] == 3 and len(cloner.mesh.points) == 24
    assert scene.redo()
    cloner = next(o for o in scene.objects if o.kind == "cloner")
    assert len(cloner.mesh.points) == 40
    assert scene.undo() and scene.undo()
    assert [o.kind for o in scene.objects] == ["polygon"] and scene.objects[0].parent is None
    assert scene.redo()
    cloner = next(o for o in scene.objects if o.kind == "cloner")
    assert len(cloner.mesh.points) == 24
    ball = scene.add_parametric("metaball", adopt=cloner)
    assert len(ball.mesh.polygons) > 0
    scene.set_param(ball, "hull_value", 150)
    smaller = len(ball.mesh.polygons)
    assert scene.undo()
    ball = next(o for o in scene.objects if o.kind == "metaball")
    assert ball.params["hull_value"] == 100.0 and len(ball.mesh.polygons) > smaller
    assert scene.undo()
    assert not any(o.kind == "metaball" for o in scene.objects)


def test_make_editable_keeps_generator_result():
    scene = _scene()
    cube = scene.objects[0]
    arr = scene.add_parametric("array", adopt=cube)
    expected = len(arr.mesh.points)
    poly = scene.make_editable(arr)
    assert poly.kind == "polygon" and len(poly.mesh.points) == expected and len(scene.objects) == 1
    assert scene.undo()
    assert any(o.kind == "array" for o in scene.objects)


def test_cloner_clones_option_list_matches_reference():
    spec = registry.get("cloner")
    assert spec.param("clones").choices == ("Iterate", "Random", "Blend", "Sort")
    assert spec.param("clones").clamp("Nonsense") == "Iterate"
    assert spec.param("seed").default == 1234567


def _three_kids() -> list:
    return [_inp(_box((-5, -5, -5), (5, 5, 5)), "a"), _inp(_box((-8, -8, -8), (8, 8, 8)), "b"),
            _inp(_box((-12, -12, -12), (12, 12, 12)), "c")]


def _kid_sizes(mesh: Mesh) -> list:
    return [round(float(np.ptp(mesh.points[8 * k:8 * k + 8, 0])), 6) for k in range(len(mesh.points) // 8)]


def test_cloner_sort_groups_children_in_blocks():
    m = _build("cloner", _three_kids(), linear_count=6, clones="Sort")
    assert _kid_sizes(m) == [10.0, 10.0, 16.0, 16.0, 24.0, 24.0]
    it = _build("cloner", _three_kids(), linear_count=6, clones="Iterate")
    assert _kid_sizes(it) == [10.0, 16.0, 24.0, 10.0, 16.0, 24.0]


def test_cloner_random_is_seeded_and_differs_from_iterate():
    kids = _three_kids()
    a = _build("cloner", kids, linear_count=30, clones="Random", seed=5)
    b = _build("cloner", kids, linear_count=30, clones="Random", seed=5)
    c = _build("cloner", kids, linear_count=30, clones="Random", seed=6)
    it = _build("cloner", kids, linear_count=30, clones="Iterate")
    assert _kid_sizes(a) == _kid_sizes(b)
    assert _kid_sizes(a) != _kid_sizes(c) and _kid_sizes(a) != _kid_sizes(it)
    assert set(_kid_sizes(a)) == {10.0, 16.0, 24.0}


def test_cloner_blend_interpolates_between_children():
    kids = _three_kids()
    m = _build("cloner", kids, linear_count=5, clones="Blend", linear_position=(0, 0, 0))
    assert _kid_sizes(m) == [10.0, 13.0, 16.0, 20.0, 24.0]
    assert _closed(m)
    odd = [_inp(_box((-5, -5, -5), (5, 5, 5)), "a"), _inp(_tetra(7.0), "b")]
    fallback = _build("cloner", odd, linear_count=4, clones="Blend")
    assert len(fallback.points) == 8 + 4 + 8 + 4


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
