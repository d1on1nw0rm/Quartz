from __future__ import annotations

import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.modeling import Selection, get_tool, run_tool, tool_ids
from quartz_studio.modeling.meshkit import edge_faces, edge_key
from quartz_studio.scene import Mesh

TRANSFORM_IDS = ("slide", "equal_spacing", "straighten_edges", "fit_circle", "flatten", "iron",
                 "smooth_edges", "randomize", "normal_move", "normal_scale", "normal_rotate")


def _manifold(mesh: Mesh) -> bool:
    ef = edge_faces(mesh)
    return all(len(v) == 2 for v in ef.values())


def _at_most_two(mesh: Mesh) -> bool:
    return all(len(v) <= 2 for v in edge_faces(mesh).values())


def _consistent(mesh: Mesh) -> bool:
    seen = set()
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a, b) in seen:
                return False
            seen.add((a, b))
    return True


def _no_unused_points(mesh: Mesh) -> bool:
    used = {i for poly in mesh.polygons for i in poly} | {i for e in mesh.loose_edges for i in e}
    return used == set(range(len(mesh.points)))


def _clean_polygons(mesh: Mesh) -> bool:
    canon = set()
    for poly in mesh.polygons:
        if len(poly) < 3 or len(set(poly)) != len(poly):
            return False
        k = poly.index(min(poly))
        key = tuple(poly[k:] + poly[:k])
        if key in canon:
            return False
        canon.add(key)
    return True


def _signed_volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        p = mesh.points[list(poly)]
        for k in range(1, len(p) - 1):
            total += float(np.dot(p[0], np.cross(p[k], p[k + 1])))
    return total / 6.0


def _oriented(points, polygons) -> Mesh:
    mesh = Mesh(points, polygons)
    center = mesh.points.mean(axis=0)
    normals = mesh.polygon_normals()
    fixed = []
    for k, poly in enumerate(mesh.polygons):
        face_center = mesh.points[list(poly)].mean(axis=0)
        fixed.append(poly if float(normals[k] @ (face_center - center)) > 0 else tuple(reversed(poly)))
    return Mesh(points, fixed)


def _tube(profile=((50.0, 0.0), (50.0, 100.0), (50.0, 200.0))) -> Mesh:
    points = []
    for r, y in profile:
        points += [(-r, y, -r), (r, y, -r), (r, y, r), (-r, y, r)]
    polys = []
    for k in range(len(profile) - 1):
        for j in range(4):
            a, b = 4 * k + j, 4 * k + (j + 1) % 4
            polys.append((a, b, b + 4, a + 4))
    top = 4 * (len(profile) - 1)
    polys.append((0, 1, 2, 3))
    polys.append((top, top + 1, top + 2, top + 3))
    return _oriented(points, polys)


def _ring_edges(k: int) -> set:
    return {edge_key(4 * k + j, 4 * k + (j + 1) % 4) for j in range(4)}


def _grid(nx: int, nz: int, size: float = 100.0) -> Mesh:
    points = [(c * size, 0.0, r * size) for r in range(nz + 1) for c in range(nx + 1)]
    polys = []
    for r in range(nz):
        for c in range(nx):
            i = r * (nx + 1) + c
            polys.append((i, i + nx + 1, i + nx + 2, i + 1))
    mesh = Mesh(points, polys)
    assert np.allclose(mesh.polygon_normals()[:, 1], 1.0)
    return mesh


def _gid(nx: int, c: int, r: int) -> int:
    return r * (nx + 1) + c


def _row_edges(nx: int, r: int) -> set:
    return {edge_key(_gid(nx, c, r), _gid(nx, c + 1, r)) for c in range(nx)}


def _ngon(n: int = 6, radius: float = 100.0) -> Mesh:
    pts = [(radius * math.cos(2 * math.pi * k / n), 0.0, -radius * math.sin(2 * math.pi * k / n)) for k in range(n)]
    mesh = Mesh(pts, [tuple(range(n))])
    assert mesh.polygon_normals()[0, 1] > 0.99
    return mesh


def _top_face_index(mesh: Mesh) -> int:
    return int(np.argmax(mesh.polygon_normals()[:, 1]))


def _line(xs, zs=None) -> Mesh:
    zs = zs or [0.0] * len(xs)
    pts = [(x, 0.0, z) for x, z in zip(xs, zs)]
    return Mesh(pts, [], [(k, k + 1) for k in range(len(pts) - 1)])


def _circumcenter(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    ab, ac = b - a, c - a
    n = np.cross(ab, ac)
    return a + (np.cross(n, ab) * (ac @ ac) + np.cross(ac, n) * (ab @ ab)) / (2.0 * (n @ n))


def _same_topology(a: Mesh, b: Mesh) -> bool:
    return a.polygons == b.polygons and len(a.points) == len(b.points)


def test_registry_lists_transform_tools():
    ids = tool_ids()
    for tid in TRANSFORM_IDS:
        assert tid in ids
    assert "smooth" not in ids
    assert "extrude" in ids
    assert get_tool("slide").name == "Slide"
    assert get_tool("normal_move").name == "Normal Move"
    assert get_tool("straighten_edges").name == "Straighten Edges"
    assert get_tool("smooth_edges").name == "Smooth Edges"


def test_parameter_defaults():
    slide = get_tool("slide")
    d = slide.defaults()
    assert d["offset_mode"] == "Fixed Distance" and d["offset"] == 0.0 and d["offset_percent"] == 0.0
    assert d["shift"] == 0.0 and d["limit"] is True and d["clone"] is False and d["preserve_curvature"] is False
    assert d["edge"] is None and d["edge_position"] is None and "curvature" not in d
    assert slide.drag_param == "offset" and slide.shortcut == "M~O" and slide.interactive
    assert slide.extra["pick"] == "edge" and slide.extra["edge_offset_param"] == "edge_position"
    assert slide.param("offset_mode").choices == ("Fixed Distance", "Proportional")
    assert get_tool("iron").defaults() == {"angle": 90.0, "strength": 0.0, "preserve_boundaries": True}
    assert get_tool("iron").param("strength").minimum == -100.0
    assert get_tool("iron").shortcut == "M~G"
    assert get_tool("smooth_edges").defaults() == {"iterations": 0, "keep_spacing": True, "select_outline": True}
    assert get_tool("smooth_edges").drag_kind == "count"
    assert get_tool("equal_spacing").defaults() == {"strength": 0.0, "linear": False}
    assert get_tool("equal_spacing").modes == ("edges",)
    assert get_tool("straighten_edges").defaults() == {"strength": 0.0, "equal_spacing": False}
    flat = get_tool("flatten").defaults()
    assert flat["mode"] == "Best Fit" and flat["strength"] == 0.0 and flat["axis"] == "Y"
    assert flat["position"] == 0.0 and flat["individual_islands"] is False and flat["outline_only"] is False
    assert get_tool("randomize").defaults() == {"move": (10.0, 10.0, 10.0), "scale": (0.0, 0.0, 0.0),
                                                "rotate": (0.0, 0.0, 0.0), "seed": 12345}
    fc = get_tool("fit_circle").defaults()
    assert fc["strength"] == 100.0 and fc["roundness"] == 100.0 and fc["exact_radius"] is False
    assert fc["scale"] == 100.0 and fc["angle"] == 0.0 and fc["equal_spacing"] is False
    assert get_tool("fit_circle").drag_param == "scale"
    assert get_tool("normal_move").defaults() == {"move": 0.0}
    assert get_tool("normal_scale").defaults() == {"scale": 0.0}
    assert get_tool("normal_rotate").defaults() == {"rotate": 0.0}
    assert get_tool("normal_move").drag_kind == "distance"
    assert get_tool("normal_scale").drag_kind == "percent"
    assert get_tool("normal_rotate").drag_kind == "angle"
    for tid in ("normal_move", "normal_scale", "normal_rotate"):
        assert get_tool(tid).modes == ("polygons",)
    assert not get_tool("randomize").interactive and get_tool("randomize").drag_param is None
    for tid in TRANSFORM_IDS:
        spec = get_tool(tid)
        assert spec.drag_param is None or spec.param(spec.drag_param) is not None


def test_param_labels_in_order():
    assert [p.label for p in get_tool("slide").params][:7] == [
        "Offset", "Offset", "Shift", "Offset Mode", "Limit", "Preserve Curvature", "Clone"]
    assert [p.label for p in get_tool("iron").params] == ["Angle", "Strength", "Preserve Boundaries"]
    assert [p.label for p in get_tool("fit_circle").params] == [
        "Strength", "Roundness", "Exact Radius", "Scale", "Radius", "Angle", "Adjust Inner Points",
        "Project To Surface", "Equal Spacing", "Select Outline"]
    assert [p.label for p in get_tool("flatten").params][:7] == [
        "Strength", "Mode", "Axis", "Use Axis Position", "Position", "Individual Islands", "Outline Only"]
    assert [p.label for p in get_tool("smooth_edges").params] == ["Iterations", "Keep Spacing", "Select Outline"]
    assert [p.label for p in get_tool("normal_move").params] == ["Move"]
    assert [p.label for p in get_tool("normal_scale").params] == ["Scale"]
    assert [p.label for p in get_tool("normal_rotate").params] == ["Rotate"]


def test_slide_loop_toward_hovered_edge():
    tube = _tube()
    up = run_tool("slide", tube, Selection("edges", edges=_ring_edges(1)), {"offset": 30.0, "edge": (5, 9)})
    assert up.ok
    assert np.allclose(up.mesh.points[4:8, 1], 130.0)
    assert np.allclose(np.abs(up.mesh.points[4:8, [0, 2]]), 50.0)
    assert up.selection.edges == _ring_edges(1)
    down = run_tool("slide", tube, Selection("edges", edges=_ring_edges(1)), {"offset": 30.0, "edge": (1, 5)})
    assert np.allclose(down.mesh.points[4:8, 1], 70.0)
    neg = run_tool("slide", tube, Selection("edges", edges=_ring_edges(1)), {"offset": -30.0, "edge": (5, 9)})
    assert np.allclose(neg.mesh.points[4:8, 1], 70.0)
    assert np.allclose(tube.points[4:8, 1], 100.0)


def test_slide_default_side_is_consistent():
    tube = _tube()
    res = run_tool("slide", tube, Selection("edges", edges=_ring_edges(1)), {"offset": 25.0})
    ys = res.mesh.points[4:8, 1]
    assert np.allclose(ys, ys[0]) and abs(ys[0] - 100.0) == 25.0


def test_slide_limit_clamps_to_neighbour():
    tube = _tube()
    sel = Selection("edges", edges=_ring_edges(1))
    clamped = run_tool("slide", tube, sel, {"offset": 500.0, "edge": (5, 9)})
    assert np.allclose(clamped.mesh.points[4:8, 1], 200.0)
    free = run_tool("slide", tube, sel, {"offset": 500.0, "edge": (5, 9), "limit": False})
    assert np.allclose(free.mesh.points[4:8, 1], 600.0)


def test_slide_proportional_offset():
    tube = _tube()
    res = run_tool("slide", tube, Selection("edges", edges=_ring_edges(1)),
                   {"offset_mode": "Proportional", "offset_percent": 25.0, "edge": (5, 9)})
    assert np.allclose(res.mesh.points[4:8, 1], 125.0)
    ignored = run_tool("slide", tube, Selection("edges", edges=_ring_edges(1)),
                       {"offset_mode": "Proportional", "offset": 25.0, "edge": (5, 9)})
    assert np.allclose(ignored.mesh.points, tube.points)


def test_slide_preserve_curvature_follows_profile():
    tube = _tube(((50.0, 0.0), (80.0, 100.0), (50.0, 200.0)))
    sel = Selection("edges", edges=_ring_edges(1))
    base = {"offset_mode": "Proportional", "offset_percent": 50.0, "edge": (5, 9)}
    linear = run_tool("slide", tube, sel, base)
    assert np.allclose(np.abs(linear.mesh.points[4:8, [0, 2]]), 65.0)
    curved = run_tool("slide", tube, sel, dict(base, preserve_curvature=True))
    assert np.allclose(np.abs(curved.mesh.points[4:8, [0, 2]]), 72.5)
    assert np.allclose(curved.mesh.points[4:8, 1], 150.0)


def test_slide_edge_position_drives_offset():
    tube = _tube()
    sel = Selection("edges", edges=_ring_edges(1))
    a = run_tool("slide", tube, sel, {"edge": (5, 9), "edge_position": 30.0})
    assert np.allclose(a.mesh.points[4:8, 1], 130.0)
    b = run_tool("slide", tube, sel, {"edge": (9, 5), "edge_position": 30.0})
    assert np.allclose(b.mesh.points[4:8, 1], 170.0)
    c = run_tool("slide", tube, sel, {"edge": (5, 9), "edge_position": 40.0, "offset_mode": "Proportional"})
    assert np.allclose(c.mesh.points[4:8, 1], 140.0)


def test_slide_shift_moves_along_point_normals():
    tube = _tube()
    res = run_tool("slide", tube, Selection("edges", edges=_ring_edges(1)), {"shift": 10.0})
    assert np.allclose(res.mesh.points[4:8, 1], 100.0)
    assert np.allclose(np.abs(res.mesh.points[4:8, [0, 2]]), 50.0 + 10.0 / math.sqrt(2.0))
    assert np.allclose(res.mesh.points[:4], tube.points[:4])


def test_slide_clone_inserts_new_loop():
    tube = _tube()
    res = run_tool("slide", tube, Selection("edges", edges=_ring_edges(1)),
                   {"offset": 30.0, "edge": (5, 9), "clone": True})
    m = res.mesh
    assert res.ok
    assert len(m.points) == 16 and len(m.polygons) == 14
    assert _manifold(m) and _consistent(m) and _clean_polygons(m) and _no_unused_points(m)
    assert np.isclose(_signed_volume(m), _signed_volume(tube))
    assert np.allclose(m.points[4:8, 1], 100.0)
    assert np.allclose(m.points[12:16, 1], 130.0)
    assert len(res.selection.edges) == 4
    assert all(a >= 12 and b >= 12 for a, b in res.selection.edges)
    assert len(tube.points) == 12


def test_slide_clone_repeated_builds_arc():
    mesh = _tube()
    sel = Selection("edges", edges=_ring_edges(1))
    for _ in range(3):
        res = run_tool("slide", mesh, sel, {"offset": 20.0, "edge": (5, 9), "clone": True})
        assert res.ok
        mesh, sel = res.mesh, res.selection
        assert _manifold(mesh) and _consistent(mesh) and _clean_polygons(mesh) and _no_unused_points(mesh)
    assert len(mesh.points) == 24 and len(mesh.polygons) == 22
    new = sorted({i for e in sel.edges for i in e})
    assert np.allclose(mesh.points[new][:, 1], 160.0)


def test_slide_clone_open_chain_inside_grid():
    grid = _grid(4, 4)
    chain = [_gid(4, c, 2) for c in (1, 2, 3)]
    edges = {edge_key(chain[0], chain[1]), edge_key(chain[1], chain[2])}
    hover = (chain[1], _gid(4, 2, 3))
    res = run_tool("slide", grid, Selection("edges", edges=edges), {"offset": 50.0, "edge": hover, "clone": True})
    m = res.mesh
    assert res.ok and _consistent(m) and _at_most_two(m) and _clean_polygons(m) and _no_unused_points(m)
    assert len(m.points) == len(grid.points) + 3 and len(m.polygons) == len(grid.polygons) + 2
    new = sorted({i for e in res.selection.edges for i in e})
    assert np.allclose(m.points[new][:, 2], 250.0)
    assert np.allclose(sorted(m.points[new][:, 0]), [100.0, 200.0, 300.0])
    inner = sum(1 for v in edge_faces(m).values() if len(v) == 1)
    outer = sum(1 for v in edge_faces(grid).values() if len(v) == 1)
    assert inner == outer
    assert np.all(m.polygon_normals()[:, 1] > 0.99)


def test_slide_clone_open_chain_to_boundary():
    grid = _grid(3, 2)
    chain = [_gid(3, c, 1) for c in range(4)]
    edges = {edge_key(a, b) for a, b in zip(chain, chain[1:])}
    res = run_tool("slide", grid, Selection("edges", edges=edges),
                   {"offset": 40.0, "edge": (chain[0], _gid(3, 0, 0)), "clone": True})
    m = res.mesh
    assert _consistent(m) and _at_most_two(m) and _no_unused_points(m)
    assert len(m.polygons) == 9
    new = sorted({i for e in res.selection.edges for i in e})
    assert np.allclose(m.points[new][:, 2], 60.0)
    assert np.all(m.polygon_normals()[:, 1] > 0.99)


def test_slide_boundary_chain_slides_inward():
    grid = _grid(3, 3)
    sel = Selection("edges", edges=_row_edges(3, 0))
    res = run_tool("slide", grid, sel, {"offset": 40.0})
    row = [_gid(3, c, 0) for c in range(4)]
    assert res.ok and np.allclose(res.mesh.points[row][:, 2], 40.0)
    cloned = run_tool("slide", grid, sel, {"offset": 40.0, "clone": True})
    m = cloned.mesh
    assert cloned.ok and _consistent(m) and _at_most_two(m) and _no_unused_points(m)
    assert len(m.polygons) == 12 and np.all(m.polygon_normals()[:, 1] > 0.99)
    outward = run_tool("slide", grid, sel, {"offset": -40.0, "clone": True})
    assert not outward.ok
    stay = run_tool("slide", grid, sel, {"offset": -40.0})
    assert stay.ok and np.allclose(stay.mesh.points, grid.points)


def test_slide_point_along_hovered_edge():
    grid = _grid(2, 2)
    mid = _gid(2, 1, 1)
    right = _gid(2, 2, 1)
    res = run_tool("slide", grid, Selection("points", points={mid}), {"offset": 30.0, "edge": (mid, right)})
    assert res.ok
    assert np.allclose(res.mesh.points[mid], (130.0, 0.0, 100.0))
    back = run_tool("slide", grid, Selection("points", points={mid}), {"offset": -30.0, "edge": (mid, right)})
    assert np.allclose(back.mesh.points[mid], (70.0, 0.0, 100.0))
    assert np.allclose(grid.points[mid], (100.0, 0.0, 100.0))


def test_slide_point_clone_splits_edge():
    grid = _grid(2, 2)
    mid = _gid(2, 1, 1)
    right = _gid(2, 2, 1)
    res = run_tool("slide", grid, Selection("points", points={mid}),
                   {"offset": 30.0, "edge": (mid, right), "clone": True})
    m = res.mesh
    assert len(m.points) == 10 and len(m.polygons) == 4
    assert _consistent(m) and _at_most_two(m) and _no_unused_points(m)
    new = next(iter(res.selection.points))
    assert np.allclose(m.points[new], (130.0, 0.0, 100.0))
    assert np.allclose(m.points[mid], (100.0, 0.0, 100.0))
    assert sum(len(p) for p in m.polygons) == 18


def test_slide_point_clone_two_points_on_one_edge():
    line = Mesh([(0, 0, 0), (100, 0, 0)], [], [(0, 1)])
    res = run_tool("slide", line, Selection("points", points={0, 1}), {"offset": 30.0, "clone": True})
    m = res.mesh
    assert res.ok and len(m.points) == 4 and _no_unused_points(m)
    assert sorted(m.loose_edges) == sorted([edge_key(0, 2), edge_key(2, 3), edge_key(3, 1)])
    assert np.allclose(m.points[2], (30, 0, 0)) and np.allclose(m.points[3], (70, 0, 0))
    cube = Mesh.cube(200.0)
    same_spot = run_tool("slide", cube, Selection("points", points={0, 1, 2, 3}),
                         {"edge": (0, 1), "edge_position": 50.0, "clone": True})
    c = same_spot.mesh
    assert same_spot.ok and len(c.points) == 12
    assert _consistent(c) and _manifold(c) and _no_unused_points(c) and _clean_polygons(c)


def test_slide_rejects_bad_input():
    tube = _tube()
    assert not run_tool("slide", tube, Selection("polygons", polygons={0}), {"offset": 5.0}).ok
    assert not run_tool("slide", tube, Selection("edges"), {"offset": 5.0}).ok
    assert not run_tool("slide", tube, Selection("points"), {"offset": 5.0}).ok
    star = {edge_key(4, 5), edge_key(5, 6), edge_key(5, 9)}
    assert not run_tool("slide", tube, Selection("edges", edges=star), {"offset": 5.0}).ok
    assert not run_tool("slide", tube, Selection("edges", edges={(0, 99)}), {"offset": 5.0}).ok


def test_equal_spacing_centers_single_loop():
    grid = _grid(4, 4)
    row = [_gid(4, c, 2) for c in range(5)]
    grid.points[row, 2] = 130.0
    res = run_tool("equal_spacing", grid, Selection("edges", edges=_row_edges(4, 2)), {"strength": 100.0})
    assert res.ok and np.allclose(res.mesh.points[row][:, 2], 200.0)
    assert res.selection.edges == _row_edges(4, 2)
    half = run_tool("equal_spacing", grid, Selection("edges", edges=_row_edges(4, 2)), {"strength": 50.0})
    assert np.allclose(half.mesh.points[row][:, 2], 165.0)
    assert np.allclose(grid.points[row][:, 2], 130.0)
    assert _same_topology(res.mesh, grid)


def test_equal_spacing_several_loops():
    grid = _grid(4, 4)
    for r, z in ((1, 50.0), (2, 90.0), (3, 350.0)):
        grid.points[[_gid(4, c, r) for c in range(5)], 2] = z
    edges = _row_edges(4, 1) | _row_edges(4, 2) | _row_edges(4, 3)
    for linear in (False, True):
        res = run_tool("equal_spacing", grid, Selection("edges", edges=edges), {"strength": 100.0, "linear": linear})
        for r in (1, 2, 3):
            assert np.allclose(res.mesh.points[[_gid(4, c, r) for c in range(5)]][:, 2], 100.0 * r)


def test_equal_spacing_keeps_curvature_unless_linear():
    profile = []
    for y in (0.0, 20.0, 60.0, 200.0):
        profile.append((math.sqrt(150.0 ** 2 - (y - 100.0) ** 2), y))
    tube = _tube(tuple(profile))
    edges = _ring_edges(1) | _ring_edges(2)
    curved = run_tool("equal_spacing", tube, Selection("edges", edges=edges), {"strength": 100.0})
    linear = run_tool("equal_spacing", tube, Selection("edges", edges=edges), {"strength": 100.0, "linear": True})
    assert curved.ok and linear.ok
    col = [2, 6, 10, 14]
    lp = linear.mesh.points[col]
    assert np.allclose(lp[1], lp[0] + (lp[3] - lp[0]) / 3.0)
    cp = curved.mesh.points[col]
    straight_x = lp[1:3, 0]
    assert np.all(cp[1:3, 0] > straight_x + 5.0)
    seg = np.linalg.norm(np.diff(cp, axis=0), axis=1)
    assert seg.max() / seg.min() < 1.1


def test_equal_spacing_rejects_bad_input():
    grid = _grid(4, 4)
    assert not run_tool("equal_spacing", grid, Selection("points", points={1, 2}), {"strength": 100.0}).ok
    assert not run_tool("equal_spacing", grid, Selection("edges"), {"strength": 100.0}).ok
    boundary = run_tool("equal_spacing", grid, Selection("edges", edges=_row_edges(4, 0)), {"strength": 100.0})
    assert not boundary.ok


def test_straighten_edges_puts_chain_on_line():
    line = _line([0.0, 50.0, 100.0, 200.0], [0.0, 40.0, -30.0, 0.0])
    res = run_tool("straighten_edges", line, Selection("points", points={0, 1, 2, 3}), {"strength": 100.0})
    m = res.mesh
    assert res.ok
    assert np.allclose(m.points[:, 2], 0.0)
    assert np.allclose(m.points[[0, 3]], line.points[[0, 3]])
    assert 0.0 < m.points[1, 0] < m.points[2, 0] < 200.0
    even = run_tool("straighten_edges", line, Selection("points", points={0, 1, 2, 3}),
                    {"strength": 100.0, "equal_spacing": True})
    assert np.allclose(even.mesh.points[:, 0], [0.0, 200.0 / 3, 400.0 / 3, 200.0])
    none = run_tool("straighten_edges", line, Selection("points", points={0, 1, 2, 3}), {})
    assert np.allclose(none.mesh.points, line.points)


def test_straighten_splits_at_crossings():
    grid = _grid(4, 4)
    center = _gid(4, 2, 2)
    arms = [[_gid(4, 2, 2), _gid(4, c, 2), _gid(4, e, 2)] for c, e in ((1, 0), (3, 4))]
    arms += [[_gid(4, 2, 2), _gid(4, 2, r), _gid(4, 2, e)] for r, e in ((1, 0), (3, 4))]
    edges = {edge_key(a, b) for arm in arms for a, b in zip(arm, arm[1:])}
    for arm in arms:
        grid.points[arm[1], 1] = 25.0
    res = run_tool("straighten_edges", grid, Selection("edges", edges=edges), {"strength": 100.0})
    assert res.ok
    assert np.allclose(res.mesh.points[:, 1], 0.0)
    assert np.allclose(res.mesh.points[center], grid.points[center])
    cube = Mesh.cube(200.0)
    same = run_tool("straighten_edges", cube, Selection("points", points=set(range(8))), {"strength": 100.0})
    assert same.ok and np.allclose(same.mesh.points, cube.points)


def test_straighten_rejects_closed_loop():
    tube = _tube()
    assert not run_tool("straighten_edges", tube, Selection("edges", edges=_ring_edges(1)), {"strength": 100.0}).ok
    assert not run_tool("straighten_edges", tube, Selection("points", points={0}), {"strength": 100.0}).ok


def test_fit_circle_round_loop():
    rng = np.random.default_rng(3)
    n = 8
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        r = 100.0 + rng.uniform(-15, 15)
        pts.append((r * math.cos(a), rng.uniform(-5, 5), r * math.sin(a)))
    mesh = Mesh(pts, [], [(k, (k + 1) % n) for k in range(n)])
    res = run_tool("fit_circle", mesh, Selection("points", points=set(range(n))), {})
    p = res.mesh.points
    center = _circumcenter(p[0], p[3], p[5])
    d = np.linalg.norm(p - center, axis=1)
    assert np.allclose(d, d[0], atol=1e-6)
    assert np.linalg.svd(p - p.mean(axis=0), compute_uv=False)[-1] < 1e-6
    fixed = run_tool("fit_circle", mesh, Selection("edges", edges={(k, (k + 1) % n) for k in range(n)}),
                     {"exact_radius": True, "radius": 50.0, "equal_spacing": True})
    q = fixed.mesh.points
    assert np.allclose(np.linalg.norm(q - q.mean(axis=0), axis=1), 50.0, atol=1e-6)
    seg = np.linalg.norm(q - np.roll(q, -1, axis=0), axis=1)
    assert np.allclose(seg, seg[0])
    again = run_tool("fit_circle", fixed.mesh, Selection("points", points=set(range(n))),
                     {"exact_radius": True, "radius": 50.0, "equal_spacing": True})
    assert np.allclose(again.mesh.points, q, atol=1e-6)


def test_fit_circle_polygon_boundary():
    mesh = Mesh([(0, 0, 0), (0, 0, 100), (150, 0, 120), (100, 0, -20)], [(0, 1, 2, 3)])
    res = run_tool("fit_circle", mesh, Selection("polygons", polygons={0}), {"equal_spacing": True})
    p = res.mesh.points
    d = np.linalg.norm(p - p.mean(axis=0), axis=1)
    assert np.allclose(d, d[0])
    assert np.allclose(p[:, 1], 0.0)
    seg = np.linalg.norm(p - np.roll(p, -1, axis=0), axis=1)
    assert np.allclose(seg, seg[0])
    assert res.mesh.polygon_normals()[0, 1] > 0.99


def test_fit_circle_scale_angle_roundness():
    quad = Mesh([(-50, 0, -50), (-50, 0, 50), (50, 0, 50), (50, 0, -50)], [(0, 1, 2, 3)])
    sel = Selection("polygons", polygons={0})
    same = run_tool("fit_circle", quad, sel, {})
    assert np.allclose(same.mesh.points, quad.points)
    half = run_tool("fit_circle", quad, sel, {"scale": 50.0})
    assert np.allclose(half.mesh.points, quad.points * 0.5)
    turned = run_tool("fit_circle", quad, sel, {"angle": 45.0})
    r = 50.0 * math.sqrt(2.0)
    assert np.allclose(np.sort(np.abs(turned.mesh.points[:, [0, 2]]).max(axis=1)), r)
    assert np.allclose(np.abs(turned.mesh.points[:, [0, 2]]).min(axis=1), 0.0, atol=1e-9)
    flat = run_tool("fit_circle", quad, sel, {"roundness": 0.0, "exact_radius": True, "radius": 10.0})
    assert np.allclose(flat.mesh.points, quad.points)
    weak = run_tool("fit_circle", quad, sel, {"strength": 0.0, "scale": 10.0})
    assert np.allclose(weak.mesh.points, quad.points)


def test_fit_circle_region_moves_outline_and_inner_points():
    grid = _grid(4, 4)
    faces = {k for k, poly in enumerate(grid.polygons) if all(100 <= grid.points[i, 0] <= 300 and
                                                              100 <= grid.points[i, 2] <= 300 for i in poly)}
    assert len(faces) == 4
    res = run_tool("fit_circle", grid, Selection("polygons", polygons=faces), {})
    m = res.mesh
    center = _gid(4, 2, 2)
    rim = sorted({i for f in faces for i in grid.polygons[f]} - {center})
    d = np.linalg.norm(m.points[rim] - m.points[center], axis=1)
    assert np.allclose(d, d[0]) and np.allclose(m.points[center], grid.points[center])
    assert len(res.selection.edges) == 8 and res.selection.polygons == faces
    assert _same_topology(m, grid) and np.all(m.polygon_normals()[:, 1] > 0.99)
    no_outline = run_tool("fit_circle", grid, Selection("polygons", polygons=faces), {"select_outline": False})
    assert not no_outline.selection.edges
    by_points = run_tool("fit_circle", grid, Selection("points", points=set(rim) | {center}), {})
    assert np.allclose(by_points.mesh.points, m.points)


def test_fit_circle_adjust_inner_points_toggle():
    grid = _grid(4, 4)
    faces = set(range(16))
    on = run_tool("fit_circle", grid, Selection("polygons", polygons=faces), {"scale": 50.0})
    off = run_tool("fit_circle", grid, Selection("polygons", polygons=faces), {"scale": 50.0,
                                                                              "adjust_inner_points": False})
    inner = _gid(4, 1, 1)
    assert not np.allclose(on.mesh.points[inner], grid.points[inner])
    assert np.allclose(off.mesh.points[inner], grid.points[inner])
    assert np.allclose(on.mesh.points[_gid(4, 2, 2)], grid.points[_gid(4, 2, 2)])


def test_fit_circle_project_to_surface():
    tube = _tube()
    sel = Selection("edges", edges=_ring_edges(1))
    res = run_tool("fit_circle", tube, sel, {"scale": 80.0, "angle": 30.0, "project_to_surface": True})
    p = res.mesh.points[4:8]
    assert res.ok
    assert np.allclose(np.abs(p[:, [0, 2]]).max(axis=1), 50.0)
    assert np.allclose(p[:, 1], 100.0)


def test_fit_circle_rejects_bad_input():
    cube = Mesh.cube(200.0)
    assert not run_tool("fit_circle", cube, Selection("polygons", polygons=set(range(6))), {}).ok
    grid = _grid(4, 4)
    assert not run_tool("fit_circle", grid, Selection("edges", edges=_row_edges(4, 2)), {}).ok
    assert not run_tool("fit_circle", grid, Selection("points", points={0, 1}), {}).ok
    collinear = Mesh([(0, 0, 0), (100, 0, 0), (200, 0, 0)], [], [(0, 1), (1, 2), (2, 0)])
    res = run_tool("fit_circle", collinear, Selection("points", points={0, 1, 2}), {})
    assert np.all(np.isfinite(res.mesh.points))


def test_flatten_best_fit_and_strength():
    grid = _grid(2, 2)
    grid.points[:, 1] = [0, 5, 0, 10, 40, -10, 0, -5, 0]
    allp = set(range(9))
    free = run_tool("flatten", grid, Selection("points", points=allp), {"strength": 100.0})
    p = free.mesh.points
    assert np.linalg.svd(p - p.mean(axis=0), compute_uv=False)[-1] < 1e-6
    normal = run_tool("flatten", grid, Selection("polygons", polygons={0, 1, 2, 3}),
                      {"mode": "Normal", "strength": 100.0})
    n = normal.mesh.points
    assert np.linalg.svd(n - n.mean(axis=0), compute_uv=False)[-1] < 1e-6
    half = run_tool("flatten", grid, Selection("points", points=allp), {"strength": 50.0})
    assert np.allclose(half.mesh.points, (grid.points + p) / 2.0)
    none = run_tool("flatten", grid, Selection("points", points=allp), {})
    assert np.allclose(none.mesh.points, grid.points)


def test_flatten_normal_mode_uses_face_normals():
    grid = _grid(2, 2)
    grid.points[4, 1] = 30.0
    res = run_tool("flatten", grid, Selection("polygons", polygons={0, 1, 2, 3}), {"mode": "Normal", "strength": 100.0})
    assert np.allclose(res.mesh.points[:, 1], 30.0 / 9.0)


def test_flatten_world_and_modeling_axis():
    grid = _grid(2, 2)
    grid.points[:, 1] = np.arange(9) * 10.0
    sel = Selection("points", points=set(range(9)))
    world = run_tool("flatten", grid, sel, {"mode": "World Axis", "strength": 100.0})
    assert np.allclose(world.mesh.points[:, 1], 0.0)
    local = run_tool("flatten", grid, sel, {"mode": "World Axis", "use_axis_position": False, "strength": 100.0})
    assert np.allclose(local.mesh.points[:, 1], 40.0)
    xs = run_tool("flatten", grid, sel, {"mode": "World Axis", "axis": "X", "strength": 100.0})
    assert np.allclose(xs.mesh.points[:, 0], 0.0) and np.allclose(xs.mesh.points[:, 1], grid.points[:, 1])
    axis = run_tool("flatten", grid, sel, {"mode": "Modeling Axis", "strength": 100.0, "position": 100.0,
                                           "modeling_axis": ((0, 55, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))})
    assert np.allclose(axis.mesh.points[:, 1], 55.0)
    default_axis = run_tool("flatten", grid, sel, {"mode": "Modeling Axis", "strength": 100.0})
    assert np.allclose(default_axis.mesh.points[:, 1], 40.0)
    view = run_tool("flatten", grid, sel, {"mode": "View", "strength": 100.0, "view_direction": (0, 0, -1)})
    assert np.allclose(view.mesh.points[:, 2], 100.0)
    fallback = run_tool("flatten", grid, sel, {"mode": "View", "strength": 100.0})
    assert fallback.ok


def test_flatten_position_moves_plane():
    grid = _grid(2, 2)
    grid.points[:, 1] = [0, 0, 0, 0, 30, 0, 0, 0, 0]
    sel = Selection("points", points=set(range(9)))
    top = run_tool("flatten", grid, sel, {"mode": "World Axis", "use_axis_position": False, "position": 100.0,
                                          "strength": 100.0})
    assert np.allclose(top.mesh.points[:, 1], 30.0)
    bottom = run_tool("flatten", grid, sel, {"mode": "World Axis", "use_axis_position": False,
                                             "position": -100.0, "strength": 100.0})
    assert np.allclose(bottom.mesh.points[:, 1], 0.0)


def test_flatten_individual_islands_and_outline():
    grid = _grid(4, 1)
    left = list(grid.polygons[0])
    right = list(grid.polygons[3])
    grid.points[left, 1] += [0.0, 10.0, 0.0, 10.0]
    grid.points[right, 1] += [50.0, 60.0, 50.0, 60.0]
    sel = Selection("polygons", polygons={0, 3})
    opts = {"mode": "World Axis", "use_axis_position": False, "strength": 100.0}
    shared = run_tool("flatten", grid, sel, opts)
    assert np.allclose(shared.mesh.points[left + right, 1], 30.0)
    apart = run_tool("flatten", grid, sel, dict(opts, individual_islands=True))
    assert np.allclose(apart.mesh.points[left, 1], 5.0) and np.allclose(apart.mesh.points[right, 1], 55.0)
    bump = _grid(2, 2)
    bump.points[4, 1] = 30.0
    rim = run_tool("flatten", bump, Selection("polygons", polygons={0, 1, 2, 3}),
                   {"outline_only": True, "strength": 100.0})
    assert np.allclose(rim.mesh.points[:, 1], 0.0)


def test_iron_flattens_bump_and_respects_angle():
    grid = _grid(2, 2)
    grid.points[4, 1] = 30.0
    mid = Selection("points", points={4})
    still = run_tool("iron", grid, mid, {})
    assert np.allclose(still.mesh.points, grid.points)
    res = run_tool("iron", grid, mid, {"strength": 100.0})
    assert abs(res.mesh.points[4, 1]) < 1e-9
    half = run_tool("iron", grid, mid, {"strength": 50.0})
    assert 0.0 < half.mesh.points[4, 1] < 30.0
    worse = run_tool("iron", grid, mid, {"strength": -50.0})
    assert worse.mesh.points[4, 1] > 30.0
    cube = Mesh.cube(200.0)
    corner = run_tool("iron", cube, Selection("points", points={6}), {"strength": 100.0})
    assert not np.allclose(corner.mesh.points[6], cube.points[6])
    strict = run_tool("iron", cube, Selection("points", points={6}), {"strength": 100.0, "angle": 120.0})
    assert np.allclose(strict.mesh.points, cube.points)


def test_iron_preserve_boundaries():
    grid = _grid(2, 2)
    grid.points[1, 1] = 30.0
    sel = Selection("points", points={1})
    kept = run_tool("iron", grid, sel, {"strength": 100.0})
    assert np.allclose(kept.mesh.points, grid.points)
    moved = run_tool("iron", grid, sel, {"strength": 100.0, "preserve_boundaries": False})
    assert moved.mesh.points[1, 1] < 30.0


def test_smooth_edges_relaxes_chain_with_fixed_ends():
    grid = _grid(6, 2)
    row = [_gid(6, c, 1) for c in range(7)]
    grid.points[row, 2] += [0.0, 40.0, -40.0, 40.0, -40.0, 40.0, 0.0]
    edges = {edge_key(a, b) for a, b in zip(row, row[1:])}
    before = np.abs(grid.points[row, 2] - 100.0).max()
    res = run_tool("smooth_edges", grid, Selection("edges", edges=edges), {"iterations": 20})
    after = np.abs(res.mesh.points[row, 2] - 100.0).max()
    assert res.ok and after < before / 2.0
    assert np.allclose(res.mesh.points[[row[0], row[-1]]], grid.points[[row[0], row[-1]]])
    zero = run_tool("smooth_edges", grid, Selection("edges", edges=edges), {})
    assert np.allclose(zero.mesh.points, grid.points)
    more = run_tool("smooth_edges", grid, Selection("points", points=set(row)), {"iterations": 60})
    assert np.abs(more.mesh.points[row, 2] - 100.0).max() < after


def test_smooth_edges_keep_spacing():
    line = _line([0.0, 10.0, 20.0, 150.0, 200.0])
    sel = Selection("points", points=set(range(5)))
    kept = run_tool("smooth_edges", line, sel, {"iterations": 10})
    assert np.allclose(kept.mesh.points, line.points)
    loose = run_tool("smooth_edges", line, sel, {"iterations": 200, "keep_spacing": False})
    assert np.allclose(loose.mesh.points[:, 0], [0.0, 50.0, 100.0, 150.0, 200.0], atol=1e-3)


def test_smooth_edges_polygon_outline():
    grid = _grid(4, 4)
    faces = {k for k, poly in enumerate(grid.polygons) if all(100 <= grid.points[i, 0] <= 300 and
                                                              100 <= grid.points[i, 2] <= 300 for i in poly)}
    res = run_tool("smooth_edges", grid, Selection("polygons", polygons=faces), {"iterations": 5})
    corner = _gid(4, 1, 1)
    assert res.ok and not np.allclose(res.mesh.points[corner], grid.points[corner])
    assert np.allclose(res.mesh.points[_gid(4, 2, 2)], grid.points[_gid(4, 2, 2)])
    assert len(res.selection.edges) == 8 and _same_topology(res.mesh, grid)
    assert not run_tool("smooth_edges", Mesh.cube(200.0), Selection("polygons", polygons=set(range(6))),
                        {"iterations": 3}).ok


def test_randomize_is_seeded_and_bounded():
    grid = _grid(2, 2)
    sel = Selection("points", points={0, 4, 8})
    a = run_tool("randomize", grid, sel, {"move": (20.0, 20.0, 20.0), "seed": 7})
    b = run_tool("randomize", grid, sel, {"move": (20.0, 20.0, 20.0), "seed": 7})
    c = run_tool("randomize", grid, sel, {"move": (20.0, 20.0, 20.0), "seed": 8})
    assert np.allclose(a.mesh.points, b.mesh.points)
    assert not np.allclose(a.mesh.points, c.mesh.points)
    delta = np.abs(a.mesh.points - grid.points)
    assert delta.max() <= 20.0 + 1e-9
    assert np.allclose(delta[[1, 2, 3, 5, 6, 7]], 0.0)
    zero = run_tool("randomize", grid, sel, {"move": (0.0, 0.0, 0.0)})
    assert np.allclose(zero.mesh.points, grid.points)
    only_x = run_tool("randomize", grid, sel, {"move": (20.0, 0.0, 0.0)})
    assert np.allclose(only_x.mesh.points[:, 1:], grid.points[:, 1:])
    assert not np.allclose(only_x.mesh.points[:, 0], grid.points[:, 0])


def test_randomize_scale_and_rotate_keep_group_shape():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("randomize", cube, Selection("polygons", polygons={top}),
                   {"move": (0.0, 0.0, 0.0), "scale": (50.0, 0.0, 50.0), "rotate": (45.0, 0.0, 0.0), "seed": 3})
    pts = res.mesh.points[list(cube.polygons[top])]
    side = np.linalg.norm(pts - np.roll(pts, -1, axis=0), axis=1)
    assert np.allclose(pts[:, 1], 100.0)
    assert np.allclose(pts.mean(axis=0), (0.0, 100.0, 0.0))
    assert not np.allclose(side, 200.0)
    assert _consistent(res.mesh) and _manifold(res.mesh)


def test_normal_move_polygons():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("normal_move", cube, Selection("polygons", polygons={top}), {"move": 20.0})
    assert np.allclose(res.mesh.points[list(cube.polygons[top])][:, 1], 120.0)
    assert len(res.mesh.points) == 8 and res.selection.polygons == {top}
    grow = run_tool("normal_move", cube, Selection("polygons", polygons=set(range(6))), {"move": 10.0})
    assert np.allclose(np.abs(grow.mesh.points), 110.0)
    assert np.allclose(cube.points[6], (100.0, 100.0, 100.0))
    assert not run_tool("normal_move", cube, Selection("points", points={6}), {"move": 5.0}).ok


def test_normal_scale_in_tangent_plane():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("normal_scale", cube, Selection("polygons", polygons={top}), {"scale": -50.0})
    pts = res.mesh.points[list(cube.polygons[top])]
    assert np.allclose(pts[:, 1], 100.0)
    assert np.allclose(np.abs(pts[:, [0, 2]]), 50.0)
    double = run_tool("normal_scale", cube, Selection("polygons", polygons={top}), {"scale": 100.0})
    assert np.allclose(np.abs(double.mesh.points[list(cube.polygons[top])][:, [0, 2]]), 200.0)
    same = run_tool("normal_scale", cube, Selection("polygons", polygons={top}), {})
    assert np.allclose(same.mesh.points, cube.points)
    assert not run_tool("normal_scale", cube, Selection("edges", edges={edge_key(6, 7)}), {"scale": 10.0}).ok


def test_normal_rotate_around_face_normal():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("normal_rotate", cube, Selection("polygons", polygons={top}), {"rotate": 90.0})
    ids = list(cube.polygons[top])
    before = cube.points[ids]
    after = res.mesh.points[ids]
    assert np.allclose(after[:, 1], 100.0)
    expected = np.column_stack([before[:, 2], before[:, 1], -before[:, 0]])
    assert np.allclose(after, expected)
    small = run_tool("normal_rotate", cube, Selection("polygons", polygons={top}), {"rotate": 45.0})
    assert np.allclose(np.linalg.norm(small.mesh.points[ids][:, [0, 2]], axis=1), 100.0 * math.sqrt(2))


def test_tools_reject_wrong_mode_and_empty_selection():
    cube = Mesh.cube(200.0)
    for tid in TRANSFORM_IDS:
        assert not run_tool(tid, cube, Selection("model"), {}).ok
        for mode in get_tool(tid).modes:
            assert not run_tool(tid, cube, Selection(mode), {}).ok
    empty = Mesh.empty()
    for tid in TRANSFORM_IDS:
        for mode in get_tool(tid).modes:
            assert not run_tool(tid, empty, Selection(mode, points={0}, edges={(0, 1)}, polygons={0}), {}).ok


def _meshes():
    grid = _grid(4, 4)
    grid.points[:, 1] = np.sin(grid.points[:, 0] / 70.0) * 20.0
    return {"cube": Mesh.cube(200.0), "grid": grid, "ngon": _ngon(), "tube": _tube()}


def _selections(mesh: Mesh, mode: str):
    if mode == "points":
        n = len(mesh.points)
        return [Selection("points", points={0}), Selection("points", points={0, 1}),
                Selection("points", points=set(range(n // 2))), Selection("points", points=set(range(n)))]
    if mode == "edges":
        edges = list(mesh.edges)
        poly0 = mesh.polygons[0]
        loop = {edge_key(a, b) for a, b in zip(poly0, poly0[1:] + poly0[:1])}
        return [Selection("edges", edges={edges[0]}), Selection("edges", edges=set(edges[:3])),
                Selection("edges", edges=loop), Selection("edges", edges=set(edges))]
    n = len(mesh.polygons)
    return [Selection("polygons", polygons={0}), Selection("polygons", polygons=set(range(max(1, n // 2)))),
            Selection("polygons", polygons=set(range(n)))]


def _variants(tid: str) -> list[dict]:
    spec = get_tool(tid)
    base = spec.defaults()
    if spec.drag_param:
        param = spec.param(spec.drag_param)
        base[spec.drag_param] = 7 if param.kind == "int" else (60.0 if param.kind == "percent" else 25.0)
    for key in ("strength", "offset", "offset_percent"):
        if key in base:
            base[key] = 60.0
    out = [base]
    for p in spec.params:
        if p.kind == "bool":
            out.append(dict(base, **{p.key: not base[p.key]}))
        elif p.kind == "choice":
            out += [dict(base, **{p.key: c}) for c in p.choices if c != base[p.key]]
    if tid == "slide":
        out.append(dict(base, offset=-60.0, clone=True))
        out.append(dict(base, edge=(0, 1), edge_position=50.0, clone=True))
    if tid == "randomize":
        out.append(dict(base, scale=(30.0, 30.0, 30.0), rotate=(20.0, 20.0, 20.0)))
    return out


def test_all_tools_keep_meshes_valid():
    for name, mesh in _meshes().items():
        closed = _manifold(mesh)
        volume = _signed_volume(mesh) if closed else None
        snapshot = (mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges))
        for tid in TRANSFORM_IDS:
            for mode in get_tool(tid).modes:
                for sel in _selections(mesh, mode):
                    for params in _variants(tid):
                        res = run_tool(tid, mesh, sel, params)
                        where = f"{tid} {name} {mode} {params}"
                        assert np.array_equal(mesh.points, snapshot[0]), where
                        assert mesh.polygons == snapshot[1] and mesh.loose_edges == snapshot[2], where
                        if not res.ok:
                            assert res.message, where
                            continue
                        m = res.mesh
                        assert m is not mesh, where
                        assert np.all(np.isfinite(m.points)), where
                        assert _consistent(m) and _at_most_two(m), where
                        assert _clean_polygons(m) and _no_unused_points(m), where
                        assert res.selection.mode == sel.mode, where
                        if closed:
                            assert _manifold(m), where
                        if tid != "slide" or not params.get("clone"):
                            assert m.polygons == mesh.polygons, where
                        elif closed and tid == "slide":
                            assert _signed_volume(m) * volume > 0, where


def test_repeated_application_is_stable():
    tube = _tube()
    sel = Selection("edges", edges=_ring_edges(1))
    once = run_tool("fit_circle", tube, sel, {"equal_spacing": True})
    twice = run_tool("fit_circle", once.mesh, sel, {"equal_spacing": True})
    assert np.allclose(once.mesh.points, twice.mesh.points, atol=1e-6)
    grid = _grid(4, 4)
    grid.points[[_gid(4, c, 2) for c in range(5)], 2] = 130.0
    es = Selection("edges", edges=_row_edges(4, 2))
    a = run_tool("equal_spacing", grid, es, {"strength": 100.0})
    b = run_tool("equal_spacing", a.mesh, es, {"strength": 100.0})
    assert np.allclose(a.mesh.points, b.mesh.points)
    line = _line([0.0, 50.0, 100.0, 200.0], [0.0, 40.0, -30.0, 0.0])
    s1 = run_tool("straighten_edges", line, Selection("points", points={0, 1, 2, 3}), {"strength": 100.0})
    s2 = run_tool("straighten_edges", s1.mesh, Selection("points", points={0, 1, 2, 3}), {"strength": 100.0})
    assert np.allclose(s1.mesh.points, s2.mesh.points)


def test_degenerate_input_does_not_crash():
    mesh = Mesh([(0, 0, 0), (0, 0, 0), (100, 0, 0), (100, 0, 100)], [(0, 1, 2, 3)])
    for tid in TRANSFORM_IDS:
        for mode in get_tool(tid).modes:
            for sel in (Selection(mode, points={0, 1, 2, 3}, edges=set(mesh.edges), polygons={0}),
                        Selection(mode, points={0}, edges={mesh.edges[0]}, polygons={0})):
                for params in _variants(tid):
                    res = run_tool(tid, mesh, sel, params)
                    assert res.ok or res.message
                    assert np.all(np.isfinite(res.mesh.points)), f"{tid} {mode} {params}"


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
