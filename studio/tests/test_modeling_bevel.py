from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.modeling import Selection, get_tool, run_tool, tool_ids
from quartz_studio.modeling.meshkit import edge_faces
from quartz_studio.modeling.primitives import cylinder, plane
from quartz_studio.scene import Mesh

H = 100.0


def _manifold(mesh: Mesh) -> bool:
    ef = edge_faces(mesh)
    return all(len(v) == 2 for v in ef.values())


def _consistent(mesh: Mesh) -> bool:
    seen = set()
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a, b) in seen:
                return False
            seen.add((a, b))
    return True


def _euler(mesh: Mesh) -> int:
    return len(mesh.points) - len(edge_faces(mesh)) + len(mesh.polygons)


def _closed_ok(mesh: Mesh) -> bool:
    return _manifold(mesh) and _consistent(mesh) and _euler(mesh) == 2


def _top_face_index(mesh: Mesh) -> int:
    return int(np.argmax(mesh.polygon_normals()[:, 1]))


def _top_edge(mesh: Mesh) -> tuple[int, int]:
    for a, b in mesh.edges:
        pa, pb = mesh.points[a], mesh.points[b]
        if pa[1] > 0 and pb[1] > 0 and pa[2] > 0 and pb[2] > 0:
            return (a, b)
    raise AssertionError("no top front edge")


def _rounded_box_distance(points: np.ndarray, radius: float) -> np.ndarray:
    inner = np.clip(points, -(H - radius), H - radius)
    return np.linalg.norm(points - inner, axis=1)


def _all_edges(mesh: Mesh) -> set:
    return set(mesh.edges)


def _octahedron(r: float = 100.0) -> Mesh:
    pts = [(r, 0, 0), (-r, 0, 0), (0, r, 0), (0, -r, 0), (0, 0, r), (0, 0, -r)]
    polys = []
    for sx in (1, -1):
        for sy in (1, -1):
            for sz in (1, -1):
                tri = (0 if sx > 0 else 1, 2 if sy > 0 else 3, 4 if sz > 0 else 5)
                polys.append(tri if sx * sy * sz > 0 else tuple(reversed(tri)))
    return Mesh(pts, polys)


def _grid(n: int = 3, size: float = 300.0) -> Mesh:
    step = size / n
    pts = [(i * step, 0.0, j * step) for j in range(n + 1) for i in range(n + 1)]
    polys = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            polys.append((a, a + n + 1, a + n + 2, a + 1))
    return Mesh(pts, polys)


def _run(mesh: Mesh, mode: str, items, **params):
    key = {"points": "points", "edges": "edges", "polygons": "polygons"}[mode]
    return run_tool("bevel", mesh, Selection(mode, **{key: set(items)}), params)


def test_registry_lists_bevel_with_c4d_defaults():
    assert "bevel" in tool_ids()
    spec = get_tool("bevel")
    assert spec.name == "Bevel"
    assert spec.modes == ("points", "edges", "polygons")
    assert spec.interactive and spec.drag_param == "offset" and spec.drag_kind == "distance"
    assert spec.shortcut == "M~S" and spec.section == "CREATION TOOLS"
    d = spec.defaults()
    assert d["bevel_mode"] == "Chamfer"
    assert d["offset_mode"] == "Fixed Distance"
    assert d["offset"] == 5.0
    assert d["subdivision"] == 0
    assert d["depth"] == 100.0
    assert d["limit"] is False
    assert d["extrusion"] == 0.0
    assert d["shape"] == "Round"
    assert d["tension"] == 100.0
    assert d["mitering"] == "Default"
    assert d["ending"] == "Default"
    assert d["partial_rounding"] == "None"
    assert d["corner_ngons"] is False and d["rounding_ngons"] is False


def test_param_labels_and_order_follow_c4d():
    spec = get_tool("bevel")
    labels = [p.label for p in spec.params]
    assert labels == ["Bevel Mode", "Offset Mode", "Offset", "Subdivision", "Depth", "Limit", "Maximum Angle",
                      "Extrusion", "Preserve Groups", "Shape", "Tension", "Mitering", "Ending",
                      "Partial Rounding", "Corner N-gons", "Rounding N-gons"]
    assert spec.param("max_angle").kind == "angle" and spec.param("max_angle").default == 180.0
    assert spec.param("max_angle").modes == ("edges",)
    assert spec.param("bevel_mode").choices == ("Chamfer", "Solid")
    assert spec.param("offset_mode").choices == ("Fixed Distance", "Radial", "Proportional")
    assert spec.param("shape").choices == ("Round", "User", "Profile")
    assert spec.param("mitering").choices == ("Default", "Uniform", "Patch", "Radial")
    assert spec.param("ending").choices == ("Default", "Extend", "Inset")
    assert spec.param("partial_rounding").choices == ("None", "Full", "Convex")
    assert spec.param("offset").unit == "cm"
    assert spec.param("extrusion").modes == ("polygons",)
    assert spec.param("ending").modes == ("edges",)
    assert {p.group for p in spec.params} == {"Tool Options", "Shaping", "Topology"}


def test_single_edge_chamfer_cuts_end_faces_into_pentagons():
    cube = Mesh.cube(200.0)
    e = _top_edge(cube)
    res = _run(cube, "edges", [e], offset=20.0)
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 7
    assert len(m.points) == 10
    assert _closed_ok(m)
    assert sorted(len(q) for q in m.polygons).count(5) == 2
    news = [p for p in m.points if np.isclose(abs(p[1]), 80.0) or np.isclose(abs(p[2]), 80.0)]
    assert len(news) == 4
    assert len(cube.polygons) == 6 and len(cube.points) == 8


def test_single_edge_selects_bevel_outline_edges():
    cube = Mesh.cube(200.0)
    res = _run(cube, "edges", [_top_edge(cube)], offset=20.0)
    assert res.selection.mode == "edges"
    assert len(res.selection.edges) == 2
    assert res.selection.edges <= set(res.mesh.edges)
    for a, b in res.selection.edges:
        pa, pb = res.mesh.points[a], res.mesh.points[b]
        assert np.isclose(abs(pa[0] - pb[0]), 200.0)


def test_single_edge_round_puts_arc_on_end_faces():
    cube = Mesh.cube(200.0)
    res = _run(cube, "edges", [_top_edge(cube)], offset=20.0, subdivision=2)
    m = res.mesh
    assert len(m.polygons) == 6 + 3
    assert _closed_ok(m)
    ends = [q for q in m.polygons if len(q) == 7]
    assert len(ends) == 2
    for q in ends:
        xs = m.points[list(q)][:, 0]
        assert np.allclose(xs, xs[0])
    center = np.array([80.0, 80.0])
    yz = m.points[:, 1:]
    arc = [p for p in yz if p[0] > 80.0 + 1e-6 and p[1] > 80.0 + 1e-6]
    assert len(arc) == 4
    assert np.allclose(np.linalg.norm(np.array(arc) - center, axis=1), 20.0)


def test_all_cube_edges_chamfer_gives_corner_triangles():
    cube = Mesh.cube(200.0)
    res = _run(cube, "edges", _all_edges(cube), offset=20.0)
    m = res.mesh
    assert len(m.polygons) == 26
    assert len(m.points) == 24
    assert _closed_ok(m)
    assert sum(1 for q in m.polygons if len(q) == 3) == 8
    for p in m.points:
        assert np.allclose(sorted(np.abs(p)), [80.0, 80.0, 100.0])
    assert len(res.selection.edges) == 24


def test_all_cube_edges_round_lie_on_rounded_box():
    cube = Mesh.cube(200.0)
    for sub in (1, 2, 3):
        res = _run(cube, "edges", _all_edges(cube), offset=20.0, subdivision=sub)
        m = res.mesh
        assert _closed_ok(m)
        assert np.allclose(_rounded_box_distance(m.points, 20.0), 20.0, atol=1e-6)


def test_round_cube_counts_with_default_mitering():
    cube = Mesh.cube(200.0)
    one = _run(cube, "edges", _all_edges(cube), offset=20.0, subdivision=1).mesh
    assert len(one.polygons) == 6 + 24 + 8 * 3
    assert len(one.points) == 8 * 7
    assert all(len(q) == 4 for q in one.polygons)
    two = _run(cube, "edges", _all_edges(cube), offset=20.0, subdivision=2).mesh
    assert len(two.polygons) == 6 + 36 + 8 * 7
    assert len(two.points) == 96
    assert sum(1 for q in two.polygons if len(q) == 3) == 8


def test_mitering_modes_build_valid_corners():
    cube = Mesh.cube(200.0)
    counts = {}
    for mode in ("Default", "Uniform", "Patch", "Radial"):
        res = _run(cube, "edges", _all_edges(cube), offset=20.0, subdivision=1, mitering=mode)
        assert _closed_ok(res.mesh)
        assert np.allclose(_rounded_box_distance(res.mesh.points, 20.0), 20.0, atol=1e-6)
        counts[mode] = len(res.mesh.polygons)
    assert counts["Default"] == 54 and counts["Patch"] == 54
    assert counts["Uniform"] == 6 + 24 + 8 * 4
    assert counts["Radial"] == 6 + 24 + 8 * 6


def test_corner_ngons_makes_single_corner_polygons():
    cube = Mesh.cube(200.0)
    res = _run(cube, "edges", _all_edges(cube), offset=20.0, subdivision=2, corner_ngons=True)
    m = res.mesh
    assert len(m.polygons) == 6 + 36 + 8
    assert sum(1 for q in m.polygons if len(q) == 9) == 8
    assert _closed_ok(m)


def test_rounding_ngons_merges_strip():
    cube = Mesh.cube(200.0)
    res = _run(cube, "edges", [_top_edge(cube)], offset=20.0, subdivision=2, rounding_ngons=True)
    m = res.mesh
    assert len(m.polygons) == 7
    assert sum(1 for q in m.polygons if len(q) == 8) == 1
    assert _closed_ok(m)


def test_two_edges_meet_in_a_miter_without_corner_patch():
    cube = Mesh.cube(200.0)
    top = cube.polygons[_top_face_index(cube)]
    a, b, c = top[0], top[1], top[2]
    edges = [(a, b), (b, c)]
    flat = _run(cube, "edges", edges, offset=20.0)
    assert len(flat.mesh.points) == 11 and len(flat.mesh.polygons) == 8
    assert _closed_ok(flat.mesh)
    rnd = _run(cube, "edges", edges, offset=20.0, subdivision=2)
    assert len(rnd.mesh.points) == 17 and len(rnd.mesh.polygons) == 12
    assert _closed_ok(rnd.mesh)


def test_ending_extend_matches_default_on_square_corners():
    cube = Mesh.cube(200.0)
    e = _top_edge(cube)
    d = _run(cube, "edges", [e], offset=20.0, subdivision=1).mesh
    x = _run(cube, "edges", [e], offset=20.0, subdivision=1, ending="Extend").mesh
    assert len(d.polygons) == len(x.polygons)
    assert np.allclose(np.sort(d.points, axis=0), np.sort(x.points, axis=0))


def test_ending_inset_keeps_end_faces_and_points():
    cube = Mesh.cube(200.0)
    e = _top_edge(cube)
    res = _run(cube, "edges", [e], offset=20.0, ending="Inset")
    m = res.mesh
    assert len(m.points) == 12
    assert len(m.polygons) == 9
    assert _closed_ok(m)
    for i in e:
        assert any(np.allclose(p, cube.points[i]) for p in m.points)
    assert sum(1 for q in m.polygons if len(q) == 3) == 2


def test_solid_keeps_shape_and_adds_support_edges():
    cube = Mesh.cube(200.0)
    res = _run(cube, "edges", [_top_edge(cube)], offset=20.0, bevel_mode="Solid")
    m = res.mesh
    assert len(m.points) == 12 and len(m.polygons) == 8
    assert _closed_ok(m)
    assert np.allclose(np.abs(m.points).max(axis=1), 100.0)
    full = _run(cube, "edges", _all_edges(cube), offset=20.0, bevel_mode="Solid", subdivision=1).mesh
    assert _closed_ok(full)
    assert np.allclose(np.abs(full.points).max(axis=1), 100.0)
    assert all(len(q) == 4 for q in full.polygons)


def test_depth_and_tension_change_the_profile():
    cube = Mesh.cube(200.0)
    e = _top_edge(cube)

    def mid(mesh):
        yz = mesh.points[:, 1:]
        pick = [p for p in yz if 80.0 + 1e-6 < p[0] < 100.0 - 1e-6 and 80.0 + 1e-6 < p[1] < 100.0 - 1e-6]
        return np.array(pick)

    flat = _run(cube, "edges", [e], offset=20.0, subdivision=1, depth=0.0).mesh
    assert np.allclose(mid(flat).sum(axis=1), 180.0)
    concave = _run(cube, "edges", [e], offset=20.0, subdivision=1, depth=-100.0).mesh
    assert all(s < 180.0 for s in mid(concave).sum(axis=1))
    round_mid = mid(_run(cube, "edges", [e], offset=20.0, subdivision=1).mesh)
    assert all(s > 180.0 for s in round_mid.sum(axis=1))
    chamfer = _run(cube, "edges", [e], offset=20.0, subdivision=1, tension=0.0).mesh
    assert np.allclose(mid(chamfer).sum(axis=1), 180.0)
    profile = _run(cube, "edges", [e], offset=20.0, subdivision=1, shape="Profile").mesh
    assert np.allclose(mid(profile).sum(axis=1), 180.0)
    assert _closed_ok(concave) and _closed_ok(chamfer)


def test_offset_modes():
    cube = Mesh.cube(200.0)
    e = _top_edge(cube)
    fixed = _run(cube, "edges", [e], offset=20.0).mesh
    radial = _run(cube, "edges", [e], offset=20.0, offset_mode="Radial").mesh
    assert np.allclose(np.sort(fixed.points, axis=0), np.sort(radial.points, axis=0))
    prop = _run(cube, "edges", [e], offset=50.0, offset_mode="Proportional").mesh
    assert any(np.isclose(p[1], 50.0) for p in prop.points)
    assert any(np.isclose(p[2], 50.0) for p in prop.points)


def test_radial_offset_uses_round_radius_on_open_angle():
    pts = [(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100), (0, 100, 200), (100, 100, 200)]
    polys = [(0, 3, 2, 1), (3, 4, 5, 2)]
    mesh = Mesh(pts, polys)
    res = _run(mesh, "edges", [(2, 3)], offset=10.0, offset_mode="Radial")
    assert res.ok
    expected = 10.0 * np.tan(np.radians(45.0) / 2.0)
    zs = sorted(p[2] for p in res.mesh.points if np.isclose(p[1], 0.0) and p[2] > 1.0)
    assert np.isclose(100.0 - min(zs), expected)


def test_limit_clamps_offset():
    cube = Mesh.cube(200.0)
    e = _top_edge(cube)
    res = _run(cube, "edges", [e], offset=500.0, limit=True)
    assert res.ok
    assert np.abs(res.mesh.points).max() <= 100.0 + 1e-9
    assert _closed_ok(res.mesh)


def test_point_bevel_cuts_corner():
    cube = Mesh.cube(200.0)
    res = _run(cube, "points", [6], offset=20.0)
    m = res.mesh
    assert len(m.points) == 10 and len(m.polygons) == 7
    assert _closed_ok(m)
    assert res.selection.mode == "points" and len(res.selection.points) == 3
    for i in res.selection.points:
        assert np.isclose(np.abs(m.points[i]).sum(), 280.0)


def test_point_bevel_round_subdivision():
    cube = Mesh.cube(200.0)
    res = _run(cube, "points", [6], offset=20.0, subdivision=2)
    m = res.mesh
    assert len(m.points) == 19 and len(m.polygons) == 13
    assert _closed_ok(m)
    all_pts = _run(cube, "points", range(8), offset=20.0, subdivision=2).mesh
    assert _closed_ok(all_pts)


def test_polygon_bevel_without_extrusion_is_an_inset():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = _run(cube, "polygons", [top], offset=20.0)
    m = res.mesh
    assert len(m.polygons) == 10 and len(m.points) == 12
    assert _closed_ok(m)
    ring = m.points[list(m.polygons[top])]
    assert np.allclose(ring[:, 1], 100.0)
    assert np.allclose(np.abs(ring[:, [0, 2]]), 80.0)
    assert res.selection.polygons == {top}


def test_polygon_bevel_extrusion_rounds_rim():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = _run(cube, "polygons", [top], offset=20.0, extrusion=20.0, subdivision=2)
    m = res.mesh
    assert len(m.polygons) == 6 + 12
    assert _closed_ok(m)
    ring = m.points[list(m.polygons[top])]
    assert np.allclose(ring[:, 1], 120.0)
    assert np.allclose(np.abs(ring[:, [0, 2]]), 80.0)
    rim = [p for p in m.points if 100.0 + 1e-6 < p[1] < 120.0 - 1e-6 and p[2] > abs(p[0]) - 1e-6]
    assert len(rim) == 4
    for p in rim:
        assert np.isclose(np.hypot(p[1] - 100.0, p[2] - 80.0), 20.0)


def test_polygon_bevel_groups_adjacent_faces():
    cube = Mesh.cube(200.0)
    normals = cube.polygon_normals()
    top = int(np.argmax(normals[:, 1]))
    side = int(np.argmax(normals[:, 0]))
    res = _run(cube, "polygons", [top, side], offset=10.0, extrusion=10.0)
    assert res.ok
    assert len(res.mesh.polygons) == 6 + 6
    assert _closed_ok(res.mesh)


def test_octahedron_valence_four_corners():
    octa = _octahedron()
    for sub in (0, 1, 2):
        res = _run(octa, "edges", set(octa.edges), offset=10.0, subdivision=sub)
        assert res.ok
        assert _closed_ok(res.mesh)


def test_partial_corners_on_valence_four():
    octa = _octahedron()
    for edges in ([(0, 2), (1, 2)], [(0, 2), (2, 4), (1, 2)]):
        results = {}
        for rounding in ("None", "Full", "Convex"):
            res = _run(octa, "edges", edges, offset=10.0, subdivision=3, partial_rounding=rounding)
            assert res.ok
            assert _closed_ok(res.mesh)
            results[rounding] = res.mesh.points
        assert len(results["None"]) == len(results["Full"])
    assert np.abs(results["Full"] - results["None"]).max() > 1.0


def test_edge_loop_through_valence_four_shares_the_arc():
    octa = _octahedron()
    res = _run(octa, "edges", [(0, 2), (1, 2)], offset=10.0, subdivision=3)
    assert _closed_ok(res.mesh)
    assert len(res.mesh.polygons) == 8 + 2 * 4 + 2


def test_open_grid_interior_edges():
    grid = _grid()
    inner = [e for e in grid.edges if len(edge_faces(grid)[e]) == 2]
    for sub in (0, 2):
        res = _run(grid, "edges", inner[:3], offset=10.0, subdivision=sub)
        assert res.ok
        assert _consistent(res.mesh)
        assert all(len(v) <= 2 for v in edge_faces(res.mesh).values())
    res = _run(grid, "points", [5], offset=10.0, subdivision=1)
    assert res.ok and _consistent(res.mesh)
    border = _run(grid, "points", [0], offset=10.0)
    assert border.ok and _consistent(border.mesh)


def test_boundary_only_edges_fail():
    grid = _grid()
    res = _run(grid, "edges", [(0, 1)], offset=10.0)
    assert not res.ok


def test_input_not_mutated_and_wrong_mode_reports():
    cube = Mesh.cube(200.0)
    before = cube.points.copy()
    _run(cube, "edges", _all_edges(cube), offset=20.0, subdivision=2)
    _run(cube, "polygons", [0], offset=20.0, extrusion=30.0)
    _run(cube, "points", [0], offset=20.0)
    assert np.allclose(cube.points, before) and len(cube.polygons) == 6
    assert not run_tool("bevel", cube, Selection("model"), {}).ok
    assert not run_tool("bevel", cube, Selection("edges"), {}).ok
    assert not run_tool("bevel", cube, Selection("points"), {}).ok
    assert not run_tool("bevel", cube, Selection("polygons"), {}).ok


def _newell(points: np.ndarray) -> np.ndarray:
    return 0.5 * np.cross(points, np.roll(points, -1, axis=0)).sum(axis=0)


def _grid_loop(n: int) -> list[tuple[int, int]]:
    ring = [(1, 1), (2, 1), (3, 1), (3, 2), (3, 3), (2, 3), (1, 3), (1, 2)]
    idx = [j * (n + 1) + i for i, j in ring]
    return [tuple(sorted((idx[k], idx[(k + 1) % len(idx)]))) for k in range(len(idx))]


def _flat_quality(mesh: Mesh, normal: np.ndarray, expected: float) -> None:
    pts = mesh.points
    areas = []
    signed = 0.0
    for q in mesh.polygons:
        assert len(set(q)) == len(q)
        n = _newell(pts[list(q)])
        assert float(n @ normal) > 0.0
        areas.append(float(np.linalg.norm(n)))
        signed += float(n @ normal)
    areas = np.array(areas)
    assert not np.any(areas < 1e-9 * areas.mean())
    assert len({tuple(np.round(p, 9)) for p in pts}) == len(pts)
    assert abs(signed - expected) <= 1e-6
    assert _consistent(mesh)


def test_flat_grid_loop_has_no_degenerate_polygons():
    grid = _grid(4, 400.0)
    base = [_newell(grid.points[list(q)]) for q in grid.polygons]
    normal = base[0] / np.linalg.norm(base[0])
    expected = sum(float(n @ normal) for n in base)
    assert np.isclose(expected, 400.0 * 400.0)
    for sub in (0, 1, 2, 3, 5, 8):
        res = _run(grid, "edges", _grid_loop(4), offset=5.0, subdivision=sub)
        assert res.ok
        _flat_quality(res.mesh, normal, expected)


def test_flat_grid_loop_with_large_offset_stays_clean():
    grid = _grid(4, 400.0)
    base = [_newell(grid.points[list(q)]) for q in grid.polygons]
    normal = base[0] / np.linalg.norm(base[0])
    expected = sum(float(n @ normal) for n in base)
    for sub in (1, 5):
        res = _run(grid, "edges", _grid_loop(4), offset=20.0, subdivision=sub)
        assert res.ok
        _flat_quality(res.mesh, normal, expected)


def test_max_angle_skips_edges_above_the_limit():
    cube = Mesh.cube(200.0)
    edges = _all_edges(cube)
    none = _run(cube, "edges", edges, offset=20.0, max_angle=45.0)
    assert none.ok
    assert len(none.mesh.polygons) == 6 and len(none.mesh.points) == 8
    assert _closed_ok(none.mesh)
    assert np.allclose(np.sort(none.mesh.points, axis=0), np.sort(cube.points, axis=0))
    default = _run(cube, "edges", edges, offset=20.0).mesh
    for angle in (90.0, 180.0):
        res = _run(cube, "edges", edges, offset=20.0, max_angle=angle)
        assert res.ok and _closed_ok(res.mesh)
        assert len(res.mesh.polygons) == len(default.polygons) == 26
        assert len(res.mesh.points) == len(default.points) == 24
    single = _run(cube, "edges", [_top_edge(cube)], offset=20.0, max_angle=45.0)
    assert single.ok and len(single.mesh.polygons) == 6


def _areas(mesh: Mesh) -> np.ndarray:
    return np.array([float(np.linalg.norm(_newell(mesh.points[list(q)]))) for q in mesh.polygons])


def _t_junction_free(mesh: Mesh) -> bool:
    pts = mesh.points
    for q in mesh.polygons:
        for a, b in zip(q, q[1:] + q[:1]):
            d = pts[b] - pts[a]
            length2 = float(d @ d)
            t = (pts - pts[a]) @ d / length2
            off = np.linalg.norm(pts[a] + np.outer(t, d) - pts, axis=1)
            if np.any((t > 1e-9) & (t < 1.0 - 1e-9) & (off <= 1e-7 * np.sqrt(length2))):
                return False
    return True


def _plane_path(grid: Mesh, cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    idx = []
    for i, j in cells:
        target = (-200.0 + 100.0 * i, 0.0, -200.0 + 100.0 * j)
        idx.append(next(k for k, p in enumerate(grid.points) if np.allclose(p, target)))
    return [tuple(sorted((idx[k], idx[k + 1]))) for k in range(len(idx) - 1)]


def test_open_path_ending_on_inner_vertex_leaves_no_slivers():
    grid = plane(400.0, 400.0, 4, 4)
    total = float(_areas(grid).sum())
    path = _plane_path(grid, [(1, 1), (2, 1), (3, 1), (3, 2), (3, 3)])
    assert len(path) == 4
    for sub in (0, 1, 2, 4, 5):
        for off in (5.0, 40.0):
            res = _run(grid, "edges", path, offset=off, subdivision=sub)
            assert res.ok
            m = res.mesh
            areas = _areas(m)
            assert not np.any(areas < 1e-5 * areas.mean())
            assert len({i for q in m.polygons for i in q}) == len(m.points)
            assert abs(float(areas.sum()) - total) <= 1e-6 * total
            assert _consistent(m) and _t_junction_free(m)
            assert all(len(v) <= 2 for v in edge_faces(m).values())


def test_cylinder_partial_corners_leave_no_slivers_and_stay_closed():
    cyl = cylinder()
    for sub in (0, 1, 2, 4):
        res = _run(cyl, "edges", _all_edges(cyl), offset=8.0, subdivision=sub, max_angle=0.0)
        assert res.ok
        m = res.mesh
        areas = _areas(m)
        assert not np.any(areas < 1e-5 * areas.mean())
        assert _closed_ok(m) and _t_junction_free(m)


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
