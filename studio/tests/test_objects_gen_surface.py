from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio.modeling.meshkit import edge_faces, face_area
from quartz_studio.objects import registry
from quartz_studio.objects.registry import BuildInput
from quartz_studio.scene import Mesh, Scene

GENERATORS = ("subdivision_surface", "symmetry", "connect", "thicken", "remesh")


def _scene() -> Scene:
    QApplication.instance() or QApplication([sys.argv[0]])
    return scene_mod.reset_scene()


def _build(spec_id: str, meshes: list, **values) -> Mesh:
    p = registry.defaults(spec_id)
    p.update(values)
    return registry.get(spec_id).build(p, [BuildInput(m, f"in{k}", "polygon") for k, m in enumerate(meshes)])


def _box(x0: float, x1: float, y0: float = -50.0, y1: float = 50.0, z0: float = -50.0,
         z1: float = 50.0) -> Mesh:
    base = Mesh.cube(1.0)
    size = np.array([x1 - x0, y1 - y0, z1 - z0])
    center = np.array([(x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0])
    return Mesh(base.points * size + center, base.polygons)


def _half_open() -> Mesh:
    m = _box(0.0, 100.0)
    polys = [poly for k, poly in enumerate(m.polygons) if k != 2]
    return Mesh(m.points, polys)


def _half_capped() -> Mesh:
    return _box(0.0, 100.0)


def _grid(n: int = 4, size: float = 100.0) -> Mesh:
    pts = [(size * i / n, 0.0, size * j / n) for j in range(n + 1) for i in range(n + 1)]
    polys = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            polys.append((a, a + n + 1, a + n + 2, a + 1))
    return Mesh(pts, polys)


def _prism(sides: int = 5) -> Mesh:
    ang = [2.0 * np.pi * k / sides for k in range(sides)]
    ring = [(50.0 * np.cos(a), 0.0, 50.0 * np.sin(a)) for a in ang]
    pts = [(x, -40.0, z) for x, _, z in ring] + [(x, 40.0, z) for x, _, z in ring]
    polys = [tuple(range(sides - 1, -1, -1)), tuple(range(sides, 2 * sides))]
    for k in range(sides):
        n = (k + 1) % sides
        polys.append((k, n, sides + n, sides + k))
    return Mesh(pts, [tuple(reversed(p)) for p in polys])


def _tetra() -> Mesh:
    pts = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (0.0, 0.0, 100.0), (0.0, 100.0, 0.0)]
    polys = [(0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2)]
    return Mesh(pts, polys)


def _line() -> Mesh:
    return Mesh([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0)], [], [(0, 1), (1, 2)])


def _volume(mesh: Mesh) -> float:
    c = mesh.points.mean(axis=0)
    total = 0.0
    for poly in mesh.polygons:
        for k in range(1, len(poly) - 1):
            a, b, d = (mesh.points[poly[0]] - c, mesh.points[poly[k]] - c, mesh.points[poly[k + 1]] - c)
            total += float(a @ np.cross(b, d)) / 6.0
    return total


def _closed(mesh: Mesh) -> bool:
    if not mesh.polygons:
        return False
    ef = edge_faces(mesh)
    if not all(len(v) == 2 for v in ef.values()):
        return False
    directed: set[tuple[int, int]] = set()
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a, b) in directed:
                return False
            directed.add((a, b))
    return all((b, a) in directed for a, b in directed)


def _clean(mesh: Mesh) -> bool:
    keys = {tuple(round(float(v), 7) for v in p) for p in mesh.points}
    if len(keys) != len(mesh.points):
        return False
    if any(face_area(mesh, k) <= 1e-9 for k in range(len(mesh.polygons))):
        return False
    used = {i for poly in mesh.polygons for i in poly}
    return used == set(range(len(mesh.points)))


def _solid(mesh: Mesh) -> bool:
    return _closed(mesh) and _clean(mesh) and _volume(mesh) > 0.0


def _boundary_edges(mesh: Mesh) -> list[tuple[int, int]]:
    return [e for e, f in edge_faces(mesh).items() if len(f) == 1]


def _sizes(mesh: Mesh) -> list[int]:
    return sorted(len(p) for p in mesh.polygons)


def _by_name(scene: Scene, name: str):
    return next(o for o in scene.objects if o.name == name)


def _add_child(scene: Scene, name: str, mesh: Mesh):
    return scene.add_object(name, mesh, activate=False)


def test_specs_registered_with_cinema_parameters():
    for sid in GENERATORS:
        spec = registry.get(sid)
        assert spec.category == "generator" and spec.inputs == "children", sid
    sub = registry.get("subdivision_surface")
    assert sub.label == "Subdivision Surface"
    assert sub.defaults() == {"type": "Catmull-Clark", "subdivision_editor": 2}
    assert sub.param("subdivision_editor").clamp(99) == 6 and sub.param("subdivision_editor").clamp(-3) == 0
    sym = registry.get("symmetry")
    assert sym.defaults() == {"mirror_plane": "ZY", "weld_points": True, "tolerance": 0.01, "flip": False}
    assert sym.param("mirror_plane").choices == ("ZY", "XY", "XZ")
    assert sym.param("mirror_plane").clamp("bad") == "ZY"
    assert registry.get("connect").defaults() == {"weld": True, "tolerance": 0.01}
    assert registry.get("thicken").defaults() == {"thickness": 10.0, "subdivision": 1, "both_sides": False}
    rem = registry.get("remesh")
    assert rem.defaults() == {"mode": "Triangles", "polygon_density": 100.0}
    assert rem.param("polygon_density").clamp(5) == 10.0 and rem.param("polygon_density").clamp(999) == 400.0
    assert rem.param("mode").choices == ("Triangles", "Quads")


def test_subdivision_cube_level_two_is_96_quads():
    m = _build("subdivision_surface", [Mesh.cube(100.0)])
    assert len(m.polygons) == 96 and all(len(p) == 4 for p in m.polygons)
    assert len(m.points) == 98
    assert _solid(m)
    assert _volume(m) < 100.0 ** 3
    assert np.allclose(m.points.mean(axis=0), 0.0, atol=1e-9)


def test_subdivision_levels_zero_to_six():
    cube = Mesh.cube(100.0)
    zero = _build("subdivision_surface", [cube], subdivision_editor=0)
    assert len(zero.polygons) == 6 and len(zero.points) == 8 and np.allclose(zero.points, cube.points)
    for level in range(1, 5):
        m = _build("subdivision_surface", [cube], subdivision_editor=level)
        assert len(m.polygons) == 6 * 4 ** level, level
        assert _solid(m), level
    six = _build("subdivision_surface", [cube], subdivision_editor=6)
    assert len(six.polygons) == 6 * 4 ** 6 and _closed(six)


def test_subdivision_converges_to_smooth_shape():
    m = _build("subdivision_surface", [Mesh.cube(100.0)], subdivision_editor=5)
    radii = np.linalg.norm(m.points, axis=1)
    assert radii.max() < 50.0 * 1.7321 and radii.min() > 30.0
    assert radii.max() - radii.min() < 12.0


def test_subdivision_ngons_triangles_and_open_boundary():
    prism = _build("subdivision_surface", [_prism(5)], subdivision_editor=1)
    assert len(prism.polygons) == 30 and all(len(p) == 4 for p in prism.polygons)
    assert _solid(prism)
    tetra = _build("subdivision_surface", [_tetra()], subdivision_editor=2)
    assert len(tetra.polygons) == 4 * 3 * 4 and _closed(tetra) and _clean(tetra) and _volume(tetra) > 0
    grid = _grid(2)
    open_m = _build("subdivision_surface", [grid], subdivision_editor=1)
    assert len(open_m.polygons) == 16 and _clean(open_m)
    assert len(_boundary_edges(open_m)) == 16
    border = open_m.points[sorted({i for e in _boundary_edges(open_m) for i in e})]
    assert np.allclose(border[:, 1], 0.0)
    assert border[:, 0].min() >= 0.0 and border[:, 0].max() <= 100.0
    assert border[:, 2].min() >= 0.0 and border[:, 2].max() <= 100.0
    on_edge = (np.isclose(border[:, 0], 0) | np.isclose(border[:, 0], 100)
               | np.isclose(border[:, 2], 0) | np.isclose(border[:, 2], 100))
    assert int(on_edge.sum()) == 12
    assert np.isclose(open_m.points[:, 0].mean(), 50.0) and np.isclose(open_m.points[:, 2].mean(), 50.0)


def test_subdivision_children_joined_and_splines_ignored():
    a, b = _box(-200, -100), _box(100, 200)
    m = _build("subdivision_surface", [a, b, _line()], subdivision_editor=1)
    assert len(m.polygons) == 48 and len(m.points) == 52 and _solid(m)
    assert m.points[:, 0].min() < -150 and m.points[:, 0].max() > 150
    assert len(_build("subdivision_surface", [_line()]).points) == 0


def test_subdivision_does_not_mutate_input():
    cube = Mesh.cube(100.0)
    before = cube.points.copy()
    polys = list(cube.polygons)
    _build("subdivision_surface", [cube])
    assert np.array_equal(cube.points, before) and cube.polygons == polys


def test_symmetry_half_open_box_welds_into_one_closed_mesh():
    m = _build("symmetry", [_half_open()])
    assert _solid(m)
    assert len(m.polygons) == 10 and len(m.points) == 12
    lo, hi = m.bounds()
    assert np.allclose(lo, (-100, -50, -50)) and np.allclose(hi, (100, 50, 50))
    assert np.isclose(_volume(m), 200 * 100 * 100)
    assert not _boundary_edges(m)


def test_symmetry_drops_faces_lying_on_plane():
    m = _build("symmetry", [_half_capped()])
    assert _solid(m) and len(m.polygons) == 10
    assert np.isclose(_volume(m), 200 * 100 * 100)
    on_plane = [k for k, poly in enumerate(m.polygons) if np.allclose(m.points[list(poly)][:, 0], 0.0)]
    assert not on_plane


def test_symmetry_planes_and_weld_off():
    base = _half_open()
    for plane, axis in (("ZY", 0), ("XY", 2), ("XZ", 1)):
        pts = base.points.copy()
        if axis == 1:
            pts = pts[:, [1, 0, 2]]
        elif axis == 2:
            pts = pts[:, [2, 1, 0]]
        polys = base.polygons
        if axis != 0:
            polys = [tuple(reversed(poly)) for poly in polys]
        half = Mesh(pts, polys)
        m = _build("symmetry", [half], mirror_plane=plane)
        assert _closed(m) and _clean(m) and len(m.polygons) == 10, plane
        lo, hi = m.bounds()
        assert np.isclose(lo[axis], -100.0) and np.isclose(hi[axis], 100.0), plane
        assert abs(_volume(m)) > 1e6, plane
    raw = _build("symmetry", [_half_open()], weld_points=False)
    assert len(raw.polygons) == 10 and len(raw.points) == 16
    assert len(_boundary_edges(raw)) == 8 and not _clean(raw)


def test_symmetry_tolerance_snaps_near_plane_points():
    half = _half_open()
    pts = half.points.copy()
    pts[pts[:, 0] < 1.0, 0] = 0.004
    near = Mesh(pts, half.polygons)
    m = _build("symmetry", [near], tolerance=0.01)
    assert _solid(m) and len(m.points) == 12
    tight = _build("symmetry", [near], tolerance=0.001)
    assert len(tight.points) == 16 and len(_boundary_edges(tight)) == 8


def test_connect_welds_coincident_points():
    two = _build("connect", [_box(-50, 50), _box(-50, 50)])
    assert len(two.points) == 8 and len(two.polygons) == 6 and _solid(two)
    apart = _build("connect", [_box(-200, -100), _box(100, 200)])
    assert len(apart.points) == 16 and len(apart.polygons) == 12 and _solid(apart)
    raw = _build("connect", [_box(-50, 50), _box(-50, 50)], weld=False)
    assert len(raw.points) == 16 and len(raw.polygons) == 12


def test_connect_tolerance_decides_the_weld():
    a = _box(-50, 50)
    pts = a.points.copy()
    pts[:, 0] += 0.005
    b = Mesh(pts, a.polygons)
    assert len(_build("connect", [a, b], tolerance=0.01).points) == 8
    assert len(_build("connect", [a, b], tolerance=0.001).points) == 16


def test_connect_joins_open_pieces_into_one_surface():
    left = _grid(2, 100.0)
    shifted = Mesh(left.points + np.array([100.0, 0.0, 0.0]), left.polygons)
    m = _build("connect", [left, shifted])
    assert len(m.polygons) == 8 and len(m.points) == 15 and _clean(m)
    assert len(_boundary_edges(m)) == 12


def test_thicken_open_surface_makes_closed_shell():
    plane = _grid(1)
    m = _build("thicken", [plane])
    assert _solid(m) and len(m.polygons) == 6 and len(m.points) == 8
    assert np.isclose(_volume(m), 100.0 * 100.0 * 10.0)
    n = plane.polygon_normals()[0]
    proj = m.points @ n
    assert np.isclose(proj.max(), 0.0) and np.isclose(proj.min(), -10.0)
    flat = [k for k, poly in enumerate(m.polygons) if np.allclose(m.polygon_normals()[k], n)]
    assert len(flat) == 1


def test_thicken_both_sides_and_subdivision():
    plane = _grid(1)
    n = plane.polygon_normals()[0]
    both = _build("thicken", [plane], both_sides=True, thickness=20.0)
    proj = both.points @ n
    assert _solid(both) and np.isclose(proj.max(), 10.0) and np.isclose(proj.min(), -10.0)
    split = _build("thicken", [plane], subdivision=4)
    assert _solid(split) and len(split.polygons) == 2 + 4 * 4
    assert len(split.points) == 8 + 4 * 3
    assert np.isclose(_volume(split), 100.0 * 100.0 * 10.0)
    layers = sorted({round(float(v), 6) for v in split.points @ n})
    assert layers == [-10.0, -7.5, -5.0, -2.5, 0.0]


def test_thicken_closed_input_gets_inverted_inner_shell():
    cube = Mesh.cube(100.0)
    m = _build("thicken", [cube], thickness=10.0)
    assert _solid(m) and len(m.polygons) == 12 and len(m.points) == 16
    assert np.isclose(_volume(m), 100.0 ** 3 - 80.0 ** 3)
    inner = [k for k in range(len(m.polygons)) if np.abs(m.points[list(m.polygons[k])]).max() < 41.0]
    assert len(inner) == 6
    normals = m.polygon_normals()
    for k in inner:
        center = m.points[list(m.polygons[k])].mean(axis=0)
        assert float(normals[k] @ center) < 0.0
    for k in set(range(12)) - set(inner):
        center = m.points[list(m.polygons[k])].mean(axis=0)
        assert float(normals[k] @ center) > 0.0
    both = _build("thicken", [cube], thickness=10.0, both_sides=True)
    assert _solid(both) and np.isclose(both.bounds()[1][0], 55.0) and np.isclose(_volume(both), 110.0 ** 3 - 90.0 ** 3)


def test_thicken_curved_open_surface_stays_valid():
    half = _build("subdivision_surface", [_half_open()], subdivision_editor=1)
    m = _build("thicken", [half], thickness=4.0, subdivision=2)
    assert _closed(m) and _clean(m) and _volume(m) > 0.0


def test_remesh_triangles_and_quads_at_full_density():
    cube = Mesh.cube(100.0)
    tri = _build("remesh", [cube])
    assert len(tri.polygons) == 12 and all(len(p) == 3 for p in tri.polygons) and len(tri.points) == 8
    assert _solid(tri) and np.isclose(_volume(tri), 100.0 ** 3)
    quad = _build("remesh", [cube], mode="Quads")
    assert len(quad.polygons) == 6 and all(len(p) == 4 for p in quad.polygons)
    assert _solid(quad) and np.isclose(_volume(quad), 100.0 ** 3)


def test_remesh_triangulates_ngons():
    m = _build("remesh", [_prism(6)])
    assert all(len(p) == 3 for p in m.polygons) and len(m.polygons) == 4 + 6 * 2 + 4
    assert _solid(m) and np.isclose(_volume(m), _volume(_prism(6)))


def test_remesh_density_changes_polygon_count_on_closed_mesh():
    sphere = _build("subdivision_surface", [Mesh.cube(100.0)])
    base = _build("remesh", [sphere])
    full = len(base.polygons)
    assert full == 192
    more = _build("remesh", [sphere], polygon_density=200.0)
    assert len(more.polygons) >= 2 * full - 2 and len(more.polygons) <= 2 * full + 2
    assert _solid(more) and np.isclose(_volume(more), _volume(base), rtol=1e-9)
    most = _build("remesh", [sphere], polygon_density=400.0)
    assert len(most.polygons) >= 4 * full - 2 and _solid(most)
    less = _build("remesh", [sphere], polygon_density=50.0)
    assert len(less.polygons) < full and len(less.polygons) <= full // 2 + 2 and _solid(less)
    least = _build("remesh", [sphere], polygon_density=10.0)
    assert 4 <= len(least.polygons) < full // 4 and _solid(least)


def test_remesh_quads_mode_after_density_keeps_manifold():
    sphere = _build("subdivision_surface", [Mesh.cube(100.0)])
    for density in (50.0, 100.0, 200.0, 400.0):
        m = _build("remesh", [sphere], mode="Quads", polygon_density=density)
        assert _solid(m), density
        assert set(len(p) for p in m.polygons) <= {3, 4}
        assert sum(1 for p in m.polygons if len(p) == 4) > 0


def test_remesh_open_surface_keeps_its_boundary():
    grid = _grid(4)
    corners = [(0, 0), (0, 100), (100, 0), (100, 100)]
    for density in (30.0, 100.0, 300.0):
        for mode in ("Triangles", "Quads"):
            m = _build("remesh", [grid], polygon_density=density, mode=mode)
            assert _clean(m) and len(m.polygons) > 0, (density, mode)
            ef = edge_faces(m)
            assert all(len(f) <= 2 for f in ef.values())
            assert np.allclose(m.points[:, 1], 0.0)
            area = sum(face_area(m, k) for k in range(len(m.polygons)))
            assert np.isclose(area, 100.0 * 100.0), (density, mode)
            border = sorted({i for e in _boundary_edges(m) for i in e})
            pts = m.points[border]
            on_edge = (np.isclose(pts[:, 0], 0) | np.isclose(pts[:, 0], 100)
                       | np.isclose(pts[:, 2], 0) | np.isclose(pts[:, 2], 100))
            assert on_edge.all(), (density, mode)
            for cx, cz in corners:
                assert any(np.allclose(p, (cx, 0, cz)) for p in m.points), (density, mode)
    base_border = {tuple(np.round(p, 6)) for p in grid.points
                   if p[0] in (0.0, 100.0) or p[2] in (0.0, 100.0)}
    kept = _build("remesh", [grid], polygon_density=30.0)
    got = {tuple(np.round(p, 6)) for p in kept.points}
    assert base_border <= got


def test_empty_and_degenerate_inputs_give_empty_mesh():
    for sid in GENERATORS:
        assert len(_build(sid, []).points) == 0, sid
        assert len(_build(sid, [_line()]).points) == 0, sid
        assert len(_build(sid, [Mesh.empty()]).points) == 0, sid
        assert len(_build(sid, [_line(), Mesh.empty()]).polygons) == 0, sid
    assert len(_build("thicken", [Mesh.cube(100.0)], thickness=0.0).points) == 0
    loose_only = Mesh(np.array([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]), [], [(0, 1)])
    for sid in GENERATORS:
        assert len(_build(sid, [loose_only]).points) == 0, sid


def test_inputs_with_unused_points_and_duplicate_indices_are_cleaned():
    cube = _box(100.0, 200.0)
    pts = np.vstack([cube.points, [(999.0, 999.0, 999.0)]])
    polys = [tuple(p) + (p[0],) for p in cube.polygons]
    dirty = Mesh(pts, polys)
    for sid in GENERATORS:
        m = _build(sid, [dirty])
        assert len(m.polygons) > 0 and abs(m.points).max() < 900.0, sid
        assert _clean(m), sid


def test_scene_subdivision_surface_with_children_edit_and_undo():
    scene = _scene()
    cube = scene.objects[0]
    gen = scene.add_parametric("subdivision_surface", adopt=cube)
    assert gen.kind == "subdivision_surface" and gen.error == ""
    assert len(gen.mesh.polygons) == 96 and _solid(gen.mesh)
    assert cube not in scene.render_objects() and gen in scene.render_objects()
    assert scene.set_param(gen, "subdivision_editor", 3)
    assert len(gen.mesh.polygons) == 6 * 64
    assert scene.set_param(gen, "subdivision_editor", 0)
    assert len(gen.mesh.polygons) == 6 and len(gen.mesh.points) == 8
    assert scene.undo() and _by_name(scene, "Subdivision Surface").params["subdivision_editor"] == 3
    gen = _by_name(scene, "Subdivision Surface")
    assert len(gen.mesh.polygons) == 384
    assert scene.undo()
    gen = _by_name(scene, "Subdivision Surface")
    assert len(gen.mesh.polygons) == 96
    before = gen.mesh.bounds()[1].copy()
    cube = _by_name(scene, "Cube")
    cube.mesh.points *= 2.0
    scene.changed.emit()
    assert np.allclose(gen.mesh.bounds()[1], before * 2.0)
    other = _add_child(scene, "Other", _box(500, 600))
    assert scene.set_parent(other, gen)
    assert len(gen.mesh.polygons) == 192
    assert scene.undo() and len(_by_name(scene, "Subdivision Surface").mesh.polygons) == 96


def test_scene_symmetry_nested_in_subdivision_surface():
    scene = _scene()
    half = _add_child(scene, "Half", _half_open())
    sub = scene.add_parametric("subdivision_surface", adopt=half)
    sym = scene.add_parametric("symmetry", adopt=sub)
    assert sub.parent is sym and half.parent is sub
    assert sym.error == "" and sub.error == ""
    assert _solid(sym.mesh) and len(sym.mesh.polygons) == 2 * len(sub.mesh.polygons)
    assert sym.mesh.bounds()[0][0] < -90.0 and sym.mesh.bounds()[1][0] > 90.0
    assert sym in scene.render_objects() and sub not in scene.render_objects()
    scene.set_param(sub, "subdivision_editor", 1)
    assert _solid(sym.mesh) and len(sym.mesh.polygons) == 2 * 20
    half.mesh.points[half.mesh.points[:, 1] > 0, 1] += 25.0
    scene.changed.emit()
    assert np.isclose(sym.mesh.bounds()[1][1], sub.mesh.bounds()[1][1]) and sym.mesh.bounds()[1][1] > 60.0
    assert _solid(sym.mesh)
    assert scene.set_param(sym, "mirror_plane", "XY")
    assert sym.mesh.bounds()[0][0] >= -1e-6
    assert scene.undo() and _by_name(scene, "Symmetry").params["mirror_plane"] == "ZY"
    assert scene.set_param(_by_name(scene, "Symmetry"), "weld_points", False)
    assert len(_boundary_edges(_by_name(scene, "Symmetry").mesh)) > 0


def test_scene_connect_with_children_and_enabled_state():
    scene = _scene()
    a = _add_child(scene, "A", _box(-300, -200))
    b = _add_child(scene, "B", _box(200, 300))
    gen = scene.add_parametric("connect")
    scene.set_parent(a, gen)
    scene.set_parent(b, gen)
    assert gen.error == "" and len(gen.mesh.polygons) == 12 and len(gen.mesh.points) == 16
    c = _add_child(scene, "C", _box(-300, -200))
    scene.set_parent(c, gen)
    assert len(gen.mesh.polygons) == 12 and len(gen.mesh.points) == 16
    scene.set_enabled(b, False)
    assert len(gen.mesh.polygons) == 6
    assert scene.set_param(gen, "weld", False)
    assert len(gen.mesh.polygons) == 12 and len(gen.mesh.points) == 16
    assert scene.undo() and len(_by_name(scene, "Connect").mesh.polygons) == 6
    outer = scene.add_parametric("subdivision_surface", adopt=_by_name(scene, "Connect"))
    scene.set_param(outer, "subdivision_editor", 1)
    assert _solid(outer.mesh) and len(outer.mesh.polygons) == 6 * 4


def test_scene_thicken_surface_then_remesh_nested():
    scene = _scene()
    plane = _add_child(scene, "Plane", _grid(3))
    thick = scene.add_parametric("thicken", adopt=plane)
    assert thick.error == "" and _solid(thick.mesh) and len(thick.mesh.polygons) == 2 * 9 + 12
    assert scene.set_param(thick, "thickness", 20.0)
    assert np.isclose(_volume(thick.mesh), 100.0 * 100.0 * 20.0)
    assert scene.set_param(thick, "both_sides", True)
    assert np.isclose(thick.mesh.bounds()[1][1] - thick.mesh.bounds()[0][1], 20.0)
    remesh = scene.add_parametric("remesh", adopt=thick)
    assert remesh.error == "" and all(len(p) == 3 for p in remesh.mesh.polygons) and _solid(remesh.mesh)
    assert scene.set_param(remesh, "mode", "Quads")
    assert any(len(p) == 4 for p in remesh.mesh.polygons) and _solid(remesh.mesh)
    assert scene.set_param(remesh, "polygon_density", 200.0)
    assert _solid(remesh.mesh) and len(remesh.mesh.polygons) > 40
    assert scene.set_param(thick, "thickness", 4.0)
    assert _solid(remesh.mesh) and np.isclose(_volume(remesh.mesh), 100.0 * 100.0 * 4.0, rtol=1e-6)
    assert scene.undo() and np.isclose(_by_name(scene, "Thicken").params["thickness"], 20.0)
    made = scene.make_editable(_by_name(scene, "Remesh"))
    assert made.kind == "polygon" and _solid(made.mesh)
    assert scene.undo() and _by_name(scene, "Remesh").kind == "remesh"


def test_scene_generators_ignore_spline_children():
    for sid in GENERATORS:
        scene = _scene()
        cube = scene.objects[0]
        line = _add_child(scene, "Line", _line())
        gen = scene.add_parametric(sid, adopt=cube)
        assert scene.set_parent(line, gen)
        assert gen.error == "" and len(gen.mesh.polygons) > 0, sid
        assert gen.mesh.loose_edges == [], sid
        assert gen.mesh.bounds()[1][0] < 150.0, sid


def test_symmetry_flip_mirrors_the_other_half():
    plain = _build("symmetry", [_half_open()])
    assert _solid(plain) and len(plain.polygons) == 10
    flipped = _build("symmetry", [_half_open()], flip=True)
    assert len(flipped.polygons) == 0 and len(flipped.points) == 0
    left = Mesh(_half_open().points * np.array([-1.0, 1.0, 1.0]),
                [tuple(reversed(poly)) for poly in _half_open().polygons])
    both = _build("symmetry", [left], flip=True)
    assert _solid(both) and len(both.polygons) == 10
    lo, hi = both.bounds()
    assert np.allclose(lo, (-100, -50, -50)) and np.allclose(hi, (100, 50, 50))
    crossing = _box(-100.0, 300.0)
    kept = _build("symmetry", [crossing], flip=True)
    full = _build("symmetry", [crossing])
    assert len(kept.polygons) != len(full.polygons)


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
