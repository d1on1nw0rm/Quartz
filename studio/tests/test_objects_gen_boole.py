from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import math
import time

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio.objects import registry
from quartz_studio.objects.gen_boole import BOOLE_TYPES, boolean_meshes, fracture_mesh
from quartz_studio.scene import Mesh, Scene, rotation_matrix


def _cube(size: float) -> Mesh:
    return Mesh.cube(size)


def _uv_sphere(radius: float, segments: int = 24, rings: int = 12) -> Mesh:
    pts = [(0.0, radius, 0.0)]
    for i in range(1, rings):
        phi = math.pi * i / rings
        y = radius * math.cos(phi)
        rr = radius * math.sin(phi)
        for j in range(segments):
            th = 2.0 * math.pi * j / segments
            pts.append((rr * math.cos(th), y, -rr * math.sin(th)))
    pts.append((0.0, -radius, 0.0))
    bottom = len(pts) - 1

    def ring(i: int, j: int) -> int:
        return 1 + (i - 1) * segments + (j % segments)

    polys = []
    for j in range(segments):
        polys.append((0, ring(1, j), ring(1, j + 1)))
    for i in range(1, rings - 1):
        for j in range(segments):
            polys.append((ring(i, j), ring(i + 1, j), ring(i + 1, j + 1), ring(i, j + 1)))
    for j in range(segments):
        polys.append((bottom, ring(rings - 1, j + 1), ring(rings - 1, j)))
    return Mesh(pts, polys)


def _moved(mesh: Mesh, offset=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)) -> Mesh:
    r = rotation_matrix(rotation)
    return Mesh(mesh.points @ r.T + np.asarray(offset, float), mesh.polygons)


def _volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        r = mesh.points[list(poly)]
        for k in range(1, len(r) - 1):
            total += float(np.dot(r[0], np.cross(r[k], r[k + 1])))
    return total / 6.0


def _directed(mesh: Mesh) -> dict:
    d: dict = {}
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            d[(a, b)] = d.get((a, b), 0) + 1
    return d


def _closed(mesh: Mesh) -> bool:
    d = _directed(mesh)
    return bool(d) and all(c == 1 and d.get((b, a), 0) == 1 for (a, b), c in d.items())


def _clean(mesh: Mesh) -> bool:
    keys = {tuple(np.round(p, 6)) for p in mesh.points}
    used = {i for poly in mesh.polygons for i in poly}
    normals = mesh.polygon_normals()
    for k, poly in enumerate(mesh.polygons):
        r = mesh.points[list(poly)]
        area = 0.5 * float(np.linalg.norm(np.cross(r - r[0], np.roll(r, -1, axis=0) - r[0]).sum(axis=0)))
        if area <= 1e-9 or len(set(poly)) != len(poly) or not np.isfinite(normals[k]).all():
            return False
    return len(keys) == len(mesh.points) and len(used) == len(mesh.points)


def _solid(mesh: Mesh) -> bool:
    return _closed(mesh) and _clean(mesh) and _volume(mesh) > 0.0


def _planes(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    n = mesh.polygon_normals()
    w = np.array([float(n[k] @ mesh.points[list(p)].mean(axis=0)) for k, p in enumerate(mesh.polygons)])
    return n, w


def _inside_convex(points: np.ndarray, mesh: Mesh) -> np.ndarray:
    n, w = _planes(mesh)
    out = np.empty(len(points), bool)
    for s in range(0, len(points), 8192):
        chunk = points[s:s + 8192]
        out[s:s + 8192] = np.all(chunk @ n.T - w <= 0.0, axis=1)
    return out


def _sampled(a: Mesh, b: Mesh, kind: str, steps: int = 64) -> float:
    allp = np.vstack([a.points, b.points])
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    h = (hi - lo) / steps
    axes = [lo[i] + h[i] * (np.arange(steps) + 0.5) for i in range(3)]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    ia = _inside_convex(grid, a)
    ib = _inside_convex(grid, b)
    sel = {"A union B": ia | ib, "A subtract B": ia & ~ib, "A intersect B": ia & ib}[kind]
    return float(sel.sum()) * float(np.prod(h))


def _components(mesh: Mesh) -> list[Mesh]:
    parent = list(range(len(mesh.points)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for poly in mesh.polygons:
        r0 = find(poly[0])
        for i in poly[1:]:
            ri = find(i)
            if ri != r0:
                parent[ri] = r0
    groups: dict = {}
    for k, poly in enumerate(mesh.polygons):
        groups.setdefault(find(poly[0]), []).append(k)
    out = []
    for faces in groups.values():
        used = sorted({i for k in faces for i in mesh.polygons[k]})
        remap = {o: n for n, o in enumerate(used)}
        out.append(Mesh(mesh.points[used], [tuple(remap[i] for i in mesh.polygons[k]) for k in faces]))
    return out


def _scene() -> Scene:
    QApplication.instance() or QApplication([sys.argv[0]])
    return scene_mod.reset_scene()


def _child(scene: Scene, parent, name: str, mesh: Mesh, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    obj = scene.add_object(name, mesh)
    obj.position = np.asarray(position, float)
    obj.rotation = np.asarray(rotation, float)
    assert scene.set_parent(obj, parent)
    return obj


def _boole(children: list, kind: str = "A subtract B", **params):
    scene = _scene()
    boole = scene.add_parametric("boole")
    objs = [_child(scene, boole, f"C{k}", *c) for k, c in enumerate(children)]
    if kind != "A subtract B":
        scene.set_param(boole, "boolean_type", kind)
    for key, value in params.items():
        scene.set_param(boole, key, value)
    assert not boole.error, boole.error
    return scene, boole, objs


def _close(a: float, b: float, rel: float) -> bool:
    return abs(a - b) <= rel * max(1.0, abs(b))


def test_hand_built_children_are_solids():
    assert _solid(_cube(200.0)) and _close(_volume(_cube(200.0)), 8e6, 1e-12)
    s = _uv_sphere(100.0)
    assert _solid(s) and 0.95 * 4.0 / 3.0 * math.pi * 1e6 < _volume(s) < 4.0 / 3.0 * math.pi * 1e6


def test_specs_follow_the_object_tab():
    boole = registry.get("boole")
    assert boole.label == "Boole" and boole.category == "generator" and boole.inputs == "children"
    assert boole.param("boolean_type").choices == ("A union B", "A subtract B", "A intersect B", "A without B")
    assert boole.defaults() == {"boolean_type": "A subtract B", "high_quality": True, "hide_new_edges": False}
    vor = registry.get("voronoi_fracture")
    assert vor.label == "Voronoi Fracture" and vor.category == "generator" and vor.inputs == "children"
    assert vor.defaults() == {"point_amount": 20, "seed": 12345, "offset_fragments": 0.0, "sort_result": False}
    assert boole.clamp({"boolean_type": "nonsense"})["boolean_type"] == "A subtract B"


def test_boole_without_children_is_empty_and_one_child_is_that_child():
    scene = _scene()
    boole = scene.add_parametric("boole")
    assert not boole.error and len(boole.mesh.points) == 0
    a = _child(scene, boole, "A", _cube(200.0), (10.0, 0.0, 0.0))
    assert np.allclose(boole.mesh.points, a.mesh.points + [10.0, 0.0, 0.0])
    assert boole.mesh.polygons == a.mesh.polygons and a not in scene.render_objects()


def test_cube_minus_smaller_overlapping_cube():
    _, boole, _ = _boole([(_cube(200.0),), (_cube(100.0), (100.0, 100.0, 100.0))])
    m = boole.mesh
    assert _solid(m)
    assert _close(_volume(m), 8e6 - 50.0 ** 3, 1e-9)
    assert np.allclose(m.points.min(axis=0), -100.0) and np.allclose(m.points.max(axis=0), 100.0)


def test_cube_cube_every_type():
    a, b = _cube(200.0), _cube(100.0)
    expected = {"A union B": 8e6 + 1e6 - 125000.0, "A subtract B": 8e6 - 125000.0, "A intersect B": 125000.0}
    for kind, vol in expected.items():
        _, boole, _ = _boole([(a,), (b, (100.0, 100.0, 100.0))], kind)
        assert _solid(boole.mesh), kind
        assert _close(_volume(boole.mesh), vol, 1e-9), (kind, _volume(boole.mesh))


def test_a_without_b_cuts_without_capping():
    _, boole, _ = _boole([(_cube(200.0),), (_cube(100.0), (100.0, 100.0, 100.0))], "A without B")
    m = boole.mesh
    assert m.polygons and not _closed(m) and _clean(m)
    for poly in m.polygons:
        c = m.points[list(poly)].mean(axis=0)
        assert not np.all(c > 50.0 + 1e-6)
        assert np.isclose(np.abs(c).max(), 100.0)
    area = sum(0.5 * float(np.linalg.norm(np.cross(m.points[list(p)] - m.points[p[0]],
                                                    np.roll(m.points[list(p)], -1, axis=0) - m.points[p[0]]).sum(axis=0)))
               for p in m.polygons)
    assert _close(area, 6 * 200.0 ** 2 - 3 * 50.0 ** 2, 1e-9)


def test_cube_minus_inner_sphere_makes_a_cavity():
    s = _uv_sphere(60.0)
    _, boole, _ = _boole([(_cube(200.0),), (s,)])
    m = boole.mesh
    assert _solid(m)
    assert _close(_volume(m), 8e6 - _volume(s), 1e-9)
    assert len(_components(m)) == 2


def test_cube_minus_overlapping_sphere():
    a, s = _cube(200.0), _uv_sphere(100.0)
    _, boole, _ = _boole([(a,), (s, (90.0, 0.0, 0.0))])
    m = boole.mesh
    assert _solid(m)
    ref = _sampled(a, _moved(s, (90.0, 0.0, 0.0)), "A subtract B")
    assert _close(_volume(m), ref, 0.02), (_volume(m), ref)
    _, inter, _ = _boole([(a,), (s, (90.0, 0.0, 0.0))], "A intersect B")
    assert _solid(inter.mesh)
    assert _close(_volume(m) + _volume(inter.mesh), 8e6, 1e-8)


def test_two_overlapping_spheres_every_type():
    s = _uv_sphere(100.0)
    vs = _volume(s)
    vols = {}
    for kind in ("A union B", "A subtract B", "A intersect B"):
        _, boole, _ = _boole([(s,), (s, (80.0, 30.0, 0.0))], kind)
        assert _solid(boole.mesh), kind
        vols[kind] = _volume(boole.mesh)
        ref = _sampled(s, _moved(s, (80.0, 30.0, 0.0)), kind)
        assert _close(vols[kind], ref, 0.02), (kind, vols[kind], ref)
    assert _close(vols["A union B"] + vols["A intersect B"], 2.0 * vs, 1e-8)
    assert _close(vols["A subtract B"], vs - vols["A intersect B"], 1e-8)


def test_rotated_child_through_transform():
    a, b = _cube(200.0), _cube(150.0)
    vols = {}
    for kind in ("A union B", "A subtract B", "A intersect B"):
        _, boole, _ = _boole([(a,), (b, (60.0, 40.0, 20.0), (30.0, 45.0, 10.0))], kind)
        assert _solid(boole.mesh), kind
        vols[kind] = _volume(boole.mesh)
    assert _close(vols["A union B"] + vols["A intersect B"], 8e6 + 150.0 ** 3, 1e-8)
    assert _close(vols["A subtract B"], 8e6 - vols["A intersect B"], 1e-8)
    ref = _sampled(a, _moved(b, (60.0, 40.0, 20.0), (30.0, 45.0, 10.0)), "A intersect B")
    assert _close(vols["A intersect B"], ref, 0.02)


def test_further_children_are_united_into_b():
    _, boole, _ = _boole([(_cube(200.0),), (_cube(100.0), (100.0, 100.0, 100.0)),
                          (_cube(100.0), (-100.0, -100.0, -100.0))])
    assert _solid(boole.mesh)
    assert _close(_volume(boole.mesh), 8e6 - 2 * 125000.0, 1e-9)


def test_hide_new_edges_merges_coplanar_polygons():
    _, shown, _ = _boole([(_cube(200.0),), (_cube(200.0), (200.0, 0.0, 0.0))], "A union B")
    _, hidden, _ = _boole([(_cube(200.0),), (_cube(200.0), (200.0, 0.0, 0.0))], "A union B",
                          hide_new_edges=True)
    assert _solid(shown.mesh) and _solid(hidden.mesh)
    assert len(shown.mesh.polygons) == 10 and len(hidden.mesh.polygons) == 6
    assert _close(_volume(hidden.mesh), 16e6, 1e-12)
    s = _uv_sphere(100.0)
    _, plain, _ = _boole([(_cube(200.0),), (s, (90.0, 0.0, 0.0))])
    _, merged, _ = _boole([(_cube(200.0),), (s, (90.0, 0.0, 0.0))], hide_new_edges=True)
    assert _solid(merged.mesh) and len(merged.mesh.polygons) <= len(plain.mesh.polygons)
    assert _close(_volume(merged.mesh), _volume(plain.mesh), 1e-9)


def test_high_quality_off_keeps_a_closed_mesh():
    s = _uv_sphere(100.0)
    _, hq, _ = _boole([(s,), (s, (80.0, 30.0, 0.0))])
    _, raw, _ = _boole([(s,), (s, (80.0, 30.0, 0.0))], high_quality=False)
    assert _closed(raw.mesh) and _volume(raw.mesh) > 0.0
    assert len(raw.mesh.polygons) >= len(hq.mesh.polygons)
    assert _close(_volume(raw.mesh), _volume(hq.mesh), 1e-8)


def test_boolean_meshes_direct_matches_scene():
    a, b = _cube(200.0), _moved(_cube(100.0), (100.0, 100.0, 100.0))
    m = boolean_meshes(a, b, "A intersect B")
    assert _solid(m) and _close(_volume(m), 125000.0, 1e-9)
    assert set(BOOLE_TYPES) == set(registry.get("boole").param("boolean_type").choices)


def _named(scene: Scene, name: str):
    return next(o for o in scene.objects if o.name == name)


def test_boole_follows_child_edits_and_undo():
    scene, boole, _ = _boole([(_cube(200.0),), (_cube(100.0), (100.0, 100.0, 100.0))])
    name = boole.name
    v0 = _volume(boole.mesh)
    assert scene.set_param(boole, "boolean_type", "A union B")
    assert _close(_volume(boole.mesh), 8e6 + 1e6 - 125000.0, 1e-9)
    scene.undo()
    boole = _named(scene, name)
    assert boole.params["boolean_type"] == "A subtract B" and _close(_volume(boole.mesh), v0, 1e-12)
    scene.redo()
    boole = _named(scene, name)
    assert _close(_volume(boole.mesh), 8e6 + 1e6 - 125000.0, 1e-9)
    scene.undo()
    boole = _named(scene, name)
    scene.set_active(_named(scene, "C1"))
    scene.set_object_position(0, 300.0)
    scene.evaluate()
    assert _close(_volume(boole.mesh), 8e6, 1e-12) and _solid(boole.mesh)
    scene.undo()
    scene.evaluate()
    assert _close(_volume(_named(scene, name).mesh), v0, 1e-12)


def test_boole_make_editable():
    scene, boole, _ = _boole([(_cube(200.0),), (_cube(100.0), (100.0, 100.0, 100.0))])
    poly = scene.make_editable(boole)
    assert poly.kind == "polygon" and _solid(poly.mesh)
    scene.undo()
    assert any(o.kind == "boole" for o in scene.objects)


def _voronoi(mesh: Mesh, position=(0.0, 0.0, 0.0), **params):
    scene = _scene()
    vor = scene.add_parametric("voronoi_fracture")
    child = _child(scene, vor, "Child", mesh, position)
    for key, value in params.items():
        scene.set_param(vor, key, value)
    assert not vor.error, vor.error
    return scene, vor, child


def test_voronoi_cube_fragments_are_closed_and_fill_the_child():
    t0 = time.perf_counter()
    _, vor, _ = _voronoi(_cube(200.0), (30.0, 0.0, 0.0))
    assert time.perf_counter() - t0 < 3.0
    frags = _components(vor.mesh)
    assert len(frags) == 20
    for f in frags:
        assert _solid(f)
    assert _close(sum(_volume(f) for f in frags), 8e6, 1e-8)
    lo, hi = vor.mesh.bounds()
    assert np.allclose(lo, [-70.0, -100.0, -100.0]) and np.allclose(hi, [130.0, 100.0, 100.0])


def test_voronoi_sphere_fragments_sum_to_its_volume():
    s = _uv_sphere(100.0)
    t0 = time.perf_counter()
    frags = fracture_mesh(s, 20, 12345)
    assert time.perf_counter() - t0 < 4.0
    assert 1 < len(frags) <= 20
    for f, _ in frags:
        assert _solid(f)
    assert _close(sum(_volume(f) for f, _ in frags), _volume(s), 1e-8)


def test_voronoi_is_deterministic_per_seed():
    _, a, _ = _voronoi(_cube(200.0), point_amount=8)
    _, b, _ = _voronoi(_cube(200.0), point_amount=8)
    _, c, _ = _voronoi(_cube(200.0), point_amount=8, seed=7)
    assert np.array_equal(a.mesh.points, b.mesh.points) and a.mesh.polygons == b.mesh.polygons
    assert len(a.mesh.points) != len(c.mesh.points) or not np.allclose(a.mesh.points, c.mesh.points)
    assert len(_components(a.mesh)) == 8 and len(_components(c.mesh)) == 8


def test_voronoi_offset_opens_gaps():
    _, solid, _ = _voronoi(_cube(200.0), point_amount=10)
    _, gaps, _ = _voronoi(_cube(200.0), point_amount=10, offset_fragments=10.0)
    fs = _components(gaps.mesh)
    assert len(fs) == 10 and all(_solid(f) for f in fs)
    total = sum(_volume(f) for f in fs)
    assert total < 8e6 * 0.95
    cents = [f.points.mean(axis=0) for f in fs]
    for i, f in enumerate(fs):
        for j, g in enumerate(fs):
            if i < j:
                d = np.linalg.norm(f.points[:, None, :] - g.points[None, :, :], axis=2).min()
                assert d > 1.0, (i, j, d)
    assert len(cents) == 10 and _close(sum(_volume(f) for f in _components(solid.mesh)), 8e6, 1e-8)


def test_voronoi_sort_result_orders_fragments():
    _, plain, _ = _voronoi(_cube(200.0), point_amount=12)
    _, ordered, _ = _voronoi(_cube(200.0), point_amount=12, sort_result=True)
    a = sorted(round(_volume(f), 3) for f in _components(plain.mesh))
    b = sorted(round(_volume(f), 3) for f in _components(ordered.mesh))
    assert a == b
    keys = [tuple(np.round(f.points.mean(axis=0), 6)) for f in _components(ordered.mesh)]
    assert keys == sorted(keys)
    raw = [tuple(np.round(f.points.mean(axis=0), 6)) for f in _components(plain.mesh)]
    assert raw != sorted(raw)


def test_voronoi_undo_and_empty():
    scene = _scene()
    vor = scene.add_parametric("voronoi_fracture")
    assert not vor.error and len(vor.mesh.points) == 0
    _child(scene, vor, "Child", _cube(200.0))
    assert len(_components(vor.mesh)) == 20
    assert scene.set_param(vor, "point_amount", 5)
    assert len(_components(vor.mesh)) == 5
    scene.undo()
    vor = _named(scene, vor.name)
    assert vor.params["point_amount"] == 20 and len(_components(vor.mesh)) == 20
    scene.redo()
    vor = _named(scene, vor.name)
    assert len(_components(vor.mesh)) == 5


def _open_edge_count(mesh: Mesh) -> int:
    d = _directed(mesh)
    return sum(1 for (a, b) in d if (b, a) not in d)


def _torus_mesh() -> Mesh:
    spec = registry.get("torus")
    return spec.build(spec.defaults(), [])


def test_voronoi_fragments_of_torus_are_closed_solids():
    torus = _torus_mesh()
    for amount, seed in ((10, 0), (10, 4), (10, 7), (20, 4), (30, 5)):
        frags = fracture_mesh(torus, amount, seed)
        assert frags, (amount, seed)
        for frag, _ in frags:
            assert _open_edge_count(frag) == 0, (amount, seed)
            assert _volume(frag) > 0.0, (amount, seed)
        total = sum(_volume(f) for f, _ in frags)
        assert abs(total - _volume(torus)) <= 1e-4 * _volume(torus), (amount, seed)


def test_voronoi_nearly_coincident_cut_points_are_welded():
    import quartz_studio.objects.gen_boole as gb
    v = np.array([[0.0, 0.0, 0.0], [0.0, 0.0057, 0.0], [0.0007, 0.0, 0.001], [5.0, 0.0, 0.0]])
    pts, idx = gb._weld(v, 0.0044)
    assert len(pts) == 2 and idx[0] == idx[1] == idx[2] != idx[3]


def test_voronoi_fracture_does_not_clip_the_whole_child_per_fragment():
    import quartz_studio.objects.gen_boole as gb
    torus = _torus_mesh()
    calls = [0]
    original = gb._partition

    def counting(*args, **kwargs):
        calls[0] += 1
        return original(*args, **kwargs)

    gb._partition = counting
    try:
        fracture_mesh(torus, 30, 0)
    finally:
        gb._partition = original
    assert calls[0] < 18000, calls[0]


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
