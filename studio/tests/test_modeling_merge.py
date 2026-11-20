from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.modeling import Selection, get_tool, primitives, run_tool, tool_ids
from quartz_studio.modeling import ops_merge
from quartz_studio.modeling.meshkit import edge_faces, edge_key, face_area
from quartz_studio.scene import Mesh

MERGE_TOOLS = {
    "weld": "Weld",
    "bridge": "Bridge",
    "stitch_and_sew": "Stitch and Sew",
    "close_polygon_hole": "Close Polygon Hole",
    "connect_points_edges": "Connect Points/Edges",
    "melt": "Melt",
    "dissolve": "Dissolve",
    "optimize": "Optimize",
    "disconnect": "Disconnect",
    "split": "Split",
}


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


def _grid(nx: int, nz: int, size: float = 100.0) -> Mesh:
    pts = [(i * size, 0.0, j * size) for i in range(nx + 1) for j in range(nz + 1)]

    def at(i: int, j: int) -> int:
        return i * (nz + 1) + j

    polys = [(at(i, j), at(i, j + 1), at(i + 1, j + 1), at(i + 1, j)) for i in range(nx) for j in range(nz)]
    return Mesh(pts, polys)


def _two_quads(dx: float) -> Mesh:
    pts = [(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100),
           (dx, 0, 0), (dx + 100, 0, 0), (dx + 100, 0, 100), (dx, 0, 100)]
    return Mesh(pts, [(0, 3, 2, 1), (4, 7, 6, 5)])


def _two_cubes() -> Mesh:
    a = Mesh.cube(100.0)
    pts = np.vstack([a.points, a.points + np.array([300.0, 0.0, 0.0])])
    polys = list(a.polygons) + [tuple(i + 8 for i in p) for p in a.polygons]
    return Mesh(pts, polys)


def _open_cube() -> Mesh:
    cube = Mesh.cube(200.0)
    return Mesh(cube.points, [p for k, p in enumerate(cube.polygons) if k != 4])


def test_registry_lists_all_merge_tools():
    ids = tool_ids()
    for tool_id, name in MERGE_TOOLS.items():
        assert tool_id in ids
        assert get_tool(tool_id).name == name
    assert "extrude" in ids


def test_merge_tool_metadata():
    assert get_tool("weld").interactive and get_tool("weld").shortcut == "M~Q"
    assert get_tool("bridge").interactive and get_tool("bridge").section == "CREATION TOOLS"
    assert get_tool("close_polygon_hole").shortcut == "M~D"
    assert not get_tool("melt").interactive and get_tool("melt").section == "COMMANDS"
    assert get_tool("connect_points_edges").modes == ("points", "edges")
    for tool_id in MERGE_TOOLS:
        assert get_tool(tool_id).drag_param is None
    assert get_tool("bridge").extra["pick"] == "edge"


def test_parameter_defaults():
    assert get_tool("bridge").defaults()["delete_original"] is True
    assert get_tool("close_polygon_hole").defaults()["create_ngons"] is True
    assert get_tool("connect_points_edges").defaults()["preserve_ngons"] is False
    assert get_tool("disconnect").defaults()["preserve_groups"] is True
    opt = get_tool("optimize")
    assert [p.key for p in opt.params] == ["polygons", "unused_points", "points", "tolerance"]
    assert opt.defaults() == {"polygons": True, "unused_points": True, "points": True, "tolerance": 0.01}
    assert opt.param("tolerance").unit == "cm"
    sew = get_tool("stitch_and_sew").defaults()
    assert sew["weld_to"] == "Center" and sew["create_polygons"] is False
    assert get_tool("weld").defaults()["target"] is None


def test_weld_points_to_center():
    cube = Mesh.cube(200.0)
    res = run_tool("weld", cube, Selection("points", points={2, 3, 6, 7}), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 5 and len(m.polygons) == 5
    assert _manifold(m) and _consistent(m)
    (p,) = res.selection.points
    assert np.allclose(m.points[p], [0.0, 100.0, 0.0])
    assert len(cube.points) == 8 and len(cube.polygons) == 6


def test_weld_to_target_point():
    cube = Mesh.cube(200.0)
    res = run_tool("weld", cube, Selection("points", points={2, 3, 7}), {"target": 6})
    assert res.ok
    (p,) = res.selection.points
    assert np.allclose(res.mesh.points[p], [100.0, 100.0, 100.0])
    assert len(res.mesh.points) == 5


def test_weld_polygon_mode_collapses_face():
    cube = Mesh.cube(200.0)
    res = run_tool("weld", cube, Selection("polygons", polygons={4}), {})
    assert res.ok
    assert len(res.mesh.polygons) == 5 and _manifold(res.mesh)
    assert res.selection.mode == "polygons" and not res.selection.polygons


def test_weld_needs_two_points():
    res = run_tool("weld", Mesh.cube(200.0), Selection("points", points={1}), {})
    assert not res.ok


def test_bridge_polygons_joins_two_cubes():
    mesh = _two_cubes()
    res = run_tool("bridge", mesh, Selection("polygons", polygons={3, 8}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 14 and len(m.points) == 16
    assert _manifold(m) and _consistent(m)
    assert res.selection.polygons == {10, 11, 12, 13}
    xs = m.points[[i for f in res.selection.polygons for i in m.polygons[f]]][:, 0]
    assert np.isclose(xs.min(), 50.0) and np.isclose(xs.max(), 250.0)


def test_bridge_keep_original_polygons():
    res = run_tool("bridge", _two_cubes(), Selection("polygons", polygons={3, 8}), {"delete_original": False})
    assert res.ok and len(res.mesh.polygons) == 16


def test_bridge_polygons_needs_two_groups():
    res = run_tool("bridge", Mesh.cube(200.0), Selection("polygons", polygons={4}), {})
    assert not res.ok


def test_bridge_border_loops_closes_box():
    quads = Mesh([(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100),
                  (0, 100, 0), (100, 100, 0), (100, 100, 100), (0, 100, 100)],
                 [(0, 1, 2, 3), (4, 7, 6, 5)])
    edges = {(0, 1), (1, 2), (2, 3), (0, 3), (4, 5), (5, 6), (6, 7), (4, 7)}
    res = run_tool("bridge", quads, Selection("edges", edges=edges), {})
    assert res.ok
    assert len(res.mesh.polygons) == 6
    assert _manifold(res.mesh) and _consistent(res.mesh)
    assert all(np.isclose(abs(float(n @ n)), 1.0) for n in res.mesh.polygon_normals())


def test_bridge_unequal_loops_mixes_triangles():
    mesh = Mesh([(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100),
                 (0, 100, 0), (100, 100, 50), (0, 100, 100)], [(0, 1, 2, 3), (4, 6, 5)])
    edges = {(0, 1), (1, 2), (2, 3), (0, 3), (4, 6), (5, 6), (4, 5)}
    res = run_tool("bridge", mesh, Selection("edges", edges=edges), {})
    assert res.ok
    assert len(res.mesh.polygons) == 8
    assert _manifold(res.mesh) and _consistent(res.mesh)


def test_bridge_open_edges_matches_winding():
    res = run_tool("bridge", _two_quads(200.0), Selection("edges", edges={(1, 2), (4, 7)}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 3 and _consistent(m)
    assert len(edge_faces(m)[(1, 2)]) == 2 and len(edge_faces(m)[(4, 7)]) == 2
    assert np.all(m.polygon_normals()[:, 1] > 0.99)


def test_bridge_four_points_makes_quad():
    res = run_tool("bridge", _two_quads(200.0), Selection("points", points={1, 2, 4, 7}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 3 and _consistent(m)
    assert set(m.polygons[2]) == {1, 2, 4, 7}
    assert m.polygon_normals()[2][1] > 0.99


def test_bridge_runtime_edges():
    res = run_tool("bridge", _two_quads(200.0), Selection("edges"), {"edge_a": (1, 2), "edge_b": (7, 4)})
    assert res.ok
    assert len(res.mesh.polygons) == 3 and _consistent(res.mesh)


def test_stitch_and_sew_welds_to_center():
    res = run_tool("stitch_and_sew", _two_quads(120.0), Selection("edges", edges={(1, 2), (4, 7)}), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 6 and len(m.polygons) == 2
    assert _consistent(m)
    (e,) = res.selection.edges
    assert len(edge_faces(m)[e]) == 2
    assert np.allclose(m.points[list(e)][:, 0], 110.0)


def test_stitch_and_sew_to_first_edge():
    res = run_tool("stitch_and_sew", _two_quads(120.0), Selection("edges", edges={(1, 2), (4, 7)}),
                   {"weld_to": "First Edge"})
    (e,) = res.selection.edges
    assert np.allclose(res.mesh.points[list(e)][:, 0], 100.0)


def test_stitch_and_sew_runtime_edges_and_polygons():
    res = run_tool("stitch_and_sew", _two_quads(120.0), Selection("edges"),
                   {"edge_a": (1, 2), "edge_b": (4, 7), "create_polygons": True})
    assert res.ok
    assert len(res.mesh.polygons) == 3 and len(res.mesh.points) == 8
    assert _consistent(res.mesh)


def test_stitch_and_sew_needs_matching_sides():
    res = run_tool("stitch_and_sew", _two_quads(120.0), Selection("edges", edges={(1, 2)}), {})
    assert not res.ok


def test_close_polygon_hole_from_selection():
    mesh = _open_cube()
    res = run_tool("close_polygon_hole", mesh, Selection("points", points={3}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 6 and _manifold(m) and _consistent(m)
    assert m.polygon_normals()[5][1] > 0.99
    assert len(mesh.polygons) == 5


def test_close_polygon_hole_triangles():
    res = run_tool("close_polygon_hole", _open_cube(), Selection("polygons"),
                   {"edge": (3, 7), "create_ngons": False})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 7 and _manifold(m) and _consistent(m)
    assert res.selection.polygons == {5, 6}
    assert all(len(m.polygons[f]) == 3 for f in res.selection.polygons)


def test_close_polygon_hole_needs_a_hole():
    res = run_tool("close_polygon_hole", Mesh.cube(200.0), Selection("points", points={0}), {})
    assert not res.ok


def test_connect_points_cuts_polygon():
    quad = Mesh([(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100)], [(0, 3, 2, 1)])
    res = run_tool("connect_points_edges", quad, Selection("points", points={0, 2}), {})
    assert res.ok
    assert sorted(len(p) for p in res.mesh.polygons) == [3, 3]
    assert edge_key(0, 2) in res.mesh.edges and _consistent(res.mesh)


def test_connect_points_on_cube_keeps_manifold():
    res = run_tool("connect_points_edges", Mesh.cube(200.0), Selection("points", points={3, 6}), {})
    assert res.ok
    assert len(res.mesh.polygons) == 7 and _manifold(res.mesh) and _consistent(res.mesh)
    assert res.selection.points == {3, 6}


def test_connect_points_without_shared_polygon_fails():
    res = run_tool("connect_points_edges", Mesh.cube(200.0), Selection("points", points={0, 6}), {})
    assert not res.ok


def test_connect_edges_ring_cuts_loop():
    cube = Mesh.cube(200.0)
    res = run_tool("connect_points_edges", cube,
                   Selection("edges", edges={(0, 3), (1, 2), (5, 6), (4, 7)}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 10 and len(m.points) == 12
    assert _manifold(m) and _consistent(m)
    assert len(res.selection.edges) == 4
    for e in res.selection.edges:
        assert np.allclose(m.points[list(e)][:, 1], 0.0)


def test_connect_all_edges_of_quad_adds_center():
    quad = Mesh([(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100)], [(0, 3, 2, 1)])
    res = run_tool("connect_points_edges", quad,
                   Selection("edges", edges={(0, 1), (1, 2), (2, 3), (0, 3)}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 4 and all(len(p) == 4 for p in m.polygons)
    assert len(m.points) == 9 and _consistent(m)
    assert np.allclose(m.points[8], [50.0, 0.0, 50.0])


def test_connect_single_edge_preserve_ngons():
    grid = _grid(2, 1)
    shared = edge_key(2, 3)
    on = run_tool("connect_points_edges", grid, Selection("edges", edges={shared}), {"preserve_ngons": True})
    assert on.ok
    assert len(on.mesh.polygons) == 2 and all(len(p) == 5 for p in on.mesh.polygons)
    off = run_tool("connect_points_edges", grid, Selection("edges", edges={shared}), {})
    assert len(off.mesh.polygons) == 6 and all(len(p) == 3 for p in off.mesh.polygons)
    assert _consistent(on.mesh) and _consistent(off.mesh)


def test_melt_polygons_into_ngon():
    res = run_tool("melt", _grid(2, 2), Selection("polygons", polygons={0, 1, 2, 3}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 1 and len(m.polygons[0]) == 8 and len(m.points) == 8
    assert res.selection.polygons == {0}
    assert m.polygon_normals()[0][1] > 0.99


def test_melt_adjacent_cube_faces_keeps_manifold():
    res = run_tool("melt", Mesh.cube(200.0), Selection("polygons", polygons={1, 4}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 5 and _manifold(m) and _consistent(m)
    assert sorted(len(p) for p in m.polygons) == [4, 4, 4, 4, 6]


def test_melt_ring_of_faces_reports():
    res = run_tool("melt", Mesh.cube(200.0), Selection("polygons", polygons={0, 1, 2, 3}), {})
    assert not res.ok


def test_melt_edge_keeps_points():
    grid = _grid(2, 1)
    res = run_tool("melt", grid, Selection("edges", edges={edge_key(2, 3)}), {})
    assert res.ok
    assert len(res.mesh.polygons) == 1 and len(res.mesh.polygons[0]) == 6
    assert len(res.mesh.points) == 6


def test_melt_point_merges_fan():
    res = run_tool("melt", _grid(2, 2), Selection("points", points={4}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 1 and len(m.polygons[0]) == 8 and len(m.points) == 8


def test_dissolve_edge_removes_leftover_points():
    res = run_tool("dissolve", _grid(2, 1), Selection("edges", edges={edge_key(2, 3)}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 1 and len(m.polygons[0]) == 4 and len(m.points) == 4
    assert m.polygon_normals()[0][1] > 0.99


def test_dissolve_connected_loop_restores_cube():
    cube = Mesh.cube(200.0)
    cut = run_tool("connect_points_edges", cube, Selection("edges", edges={(0, 3), (1, 2), (5, 6), (4, 7)}), {})
    res = run_tool("dissolve", cut.mesh, Selection("edges", edges=cut.selection.edges), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 6 and len(m.points) == 8
    assert all(len(p) == 4 for p in m.polygons)
    assert _manifold(m) and _consistent(m)


def test_dissolve_point():
    res = run_tool("dissolve", _grid(2, 2), Selection("points", points={4}), {})
    assert res.ok
    assert len(res.mesh.polygons) == 1 and len(res.mesh.points) == 8


def _dirty_mesh(dx: float = 100.0) -> Mesh:
    mesh = _two_quads(dx)
    mesh.points = np.vstack([mesh.points, [[999.0, 999.0, 999.0]]])
    mesh.polygons.append((3, 2, 1, 0))
    mesh._rebuild_edges()
    return mesh


def test_optimize_defaults_clean_everything():
    res = run_tool("optimize", _dirty_mesh(), Selection("model"), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 6 and len(m.polygons) == 2
    assert _consistent(m)
    assert sum(1 for v in edge_faces(m).values() if len(v) == 2) == 1


def test_optimize_options_switch_off():
    keep_unused = run_tool("optimize", _dirty_mesh(), Selection("model"), {"unused_points": False})
    assert len(keep_unused.mesh.points) == 7
    keep_points = run_tool("optimize", _dirty_mesh(), Selection("model"), {"points": False})
    assert len(keep_points.mesh.points) == 8 and len(keep_points.mesh.polygons) == 2
    keep_polys = run_tool("optimize", _dirty_mesh(), Selection("model"), {"polygons": False})
    assert len(keep_polys.mesh.polygons) == 3 and len(keep_polys.mesh.points) == 6


def test_optimize_tolerance():
    near = run_tool("optimize", _dirty_mesh(100.005), Selection("model"), {})
    assert len(near.mesh.points) == 6
    far = run_tool("optimize", _dirty_mesh(100.5), Selection("model"), {})
    assert len(far.mesh.points) == 8
    wide = run_tool("optimize", _dirty_mesh(100.5), Selection("model"), {"tolerance": 1.0})
    assert len(wide.mesh.points) == 6


def test_optimize_selected_points_only():
    res = run_tool("optimize", _dirty_mesh(), Selection("points", points={1, 4}), {})
    assert len(res.mesh.points) == 7
    assert len(res.selection.points) == 1


def test_disconnect_single_face():
    cube = Mesh.cube(200.0)
    res = run_tool("disconnect", cube, Selection("polygons", polygons={4}), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 12 and len(m.polygons) == 6
    assert all(i >= 8 for i in m.polygons[4])
    assert np.allclose(m.points[list(m.polygons[4])][:, 1], 100.0)
    assert res.selection.polygons == {4} and _consistent(m)
    assert len(cube.points) == 8


def test_disconnect_preserve_groups():
    on = run_tool("disconnect", Mesh.cube(200.0), Selection("polygons", polygons={1, 4}), {})
    assert len(on.mesh.points) == 14
    assert len(set(on.mesh.polygons[1]) & set(on.mesh.polygons[4])) == 2
    off = run_tool("disconnect", Mesh.cube(200.0), Selection("polygons", polygons={1, 4}),
                   {"preserve_groups": False})
    assert len(off.mesh.points) == 16
    assert not set(off.mesh.polygons[1]) & set(off.mesh.polygons[4])


def test_disconnect_point_and_edge():
    pts = run_tool("disconnect", Mesh.cube(200.0), Selection("points", points={6}), {})
    assert len(pts.mesh.points) == 10 and len(pts.selection.points) == 3
    edge = run_tool("disconnect", _grid(2, 1), Selection("edges", edges={edge_key(2, 3)}), {})
    assert len(edge.mesh.points) == 8 and len(edge.selection.edges) == 2
    assert not any(len(v) == 2 for v in edge_faces(edge.mesh).values())


def test_split_copies_polygons():
    cube = Mesh.cube(200.0)
    res = run_tool("split", cube, Selection("polygons", polygons={4}), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 12 and len(m.polygons) == 7
    assert res.selection.polygons == {6}
    assert np.allclose(m.points[list(m.polygons[6])], m.points[list(m.polygons[4])])
    assert _manifold(Mesh(m.points, m.polygons[:6])) and _consistent(m)
    assert len(cube.polygons) == 6


def test_split_from_points():
    res = run_tool("split", Mesh.cube(200.0), Selection("points", points={2, 3, 6, 7}), {})
    assert res.ok and len(res.mesh.polygons) == 7 and len(res.selection.points) == 4


def test_wrong_mode_reports():
    cube = Mesh.cube(200.0)
    for tool_id in ("weld", "bridge", "melt", "split", "connect_points_edges"):
        assert not run_tool(tool_id, cube, Selection("model"), {}).ok
    assert not run_tool("connect_points_edges", cube, Selection("polygons", polygons={0}), {}).ok


def _tube(seg: int = 8, rows: int = 1, radius: float = 100.0, height: float = 100.0) -> Mesh:
    pts = []
    for j in range(rows + 1):
        for k in range(seg):
            a = 2.0 * np.pi * k / seg
            pts.append((radius * np.cos(a), j * height, radius * np.sin(a)))

    def at(j: int, k: int) -> int:
        return j * seg + k % seg

    polys = [(at(j, k), at(j + 1, k), at(j + 1, k + 1), at(j, k + 1)) for j in range(rows) for k in range(seg)]
    return Mesh(pts, polys)


def _hexagon() -> Mesh:
    pts = [(100.0 * np.cos(np.pi * k / 3), 0.0, -100.0 * np.sin(np.pi * k / 3)) for k in range(6)]
    return Mesh(pts, [tuple(range(6))])


def _no_unused(mesh: Mesh) -> bool:
    used = {i for p in mesh.polygons for i in p} | {i for e in mesh.loose_edges for i in e}
    return used == set(range(len(mesh.points)))


def _no_degenerate(mesh: Mesh) -> bool:
    sets = [tuple(sorted(p)) for p in mesh.polygons]
    return all(len(set(p)) == len(p) >= 3 for p in mesh.polygons) and len(set(sets)) == len(sets)


def _max_edge_use(mesh: Mesh) -> int:
    return max(len(v) for v in edge_faces(mesh).values())


def _outward(mesh: Mesh) -> bool:
    center = mesh.points.mean(axis=0)
    normals = mesh.polygon_normals()
    for k, poly in enumerate(mesh.polygons):
        if float(normals[k] @ (mesh.points[list(poly)].mean(axis=0) - center)) < -1e-6:
            return False
    return True


def _sample_cases():
    cube = Mesh.cube(200.0)
    grid = _grid(4, 4)
    return [
        ("weld", cube, Selection("points", points={2, 3}), {}),
        ("bridge", _two_cubes(), Selection("polygons", polygons={3, 8}), {}),
        ("stitch_and_sew", _two_quads(120.0), Selection("edges", edges={(1, 2), (4, 7)}), {}),
        ("close_polygon_hole", _open_cube(), Selection("points", points={3}), {}),
        ("connect_points_edges", grid, Selection("edges", edges={(5, 6), (10, 11)}), {}),
        ("melt", grid, Selection("polygons", polygons={0, 1}), {}),
        ("dissolve", grid, Selection("edges", edges={(6, 11)}), {}),
        ("optimize", _dirty_mesh(), Selection("model"), {}),
        ("disconnect", cube, Selection("polygons", polygons={1, 4}), {"preserve_groups": False}),
        ("split", cube, Selection("polygons", polygons={0}), {}),
    ]


def test_inputs_are_never_mutated():
    for tool_id, mesh, sel, params in _sample_cases():
        pts, polys, loose = mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges)
        before = sel.copy()
        res = run_tool(tool_id, mesh, sel, params)
        assert res.ok, tool_id
        assert np.array_equal(mesh.points, pts) and mesh.polygons == polys and mesh.loose_edges == loose, tool_id
        assert (sel.points, sel.edges, sel.polygons) == (before.points, before.edges, before.polygons), tool_id
        assert res.mesh is not mesh
        res.selection.points.add(999)
        assert 999 not in sel.points


def test_direct_calls_do_not_mutate():
    from quartz_studio.modeling import ops_merge
    cube = Mesh.cube(200.0)
    sel = Selection("polygons", polygons={4})
    res = ops_merge.disconnect(cube, sel, get_tool("disconnect").defaults())
    assert len(cube.points) == 8 and len(res.mesh.points) == 12
    fail = ops_merge.weld(cube, Selection("points", points={1}), {})
    assert not fail.ok and fail.selection is not sel


def test_results_have_no_unused_or_degenerate_geometry():
    for tool_id, mesh, sel, params in _sample_cases():
        res = run_tool(tool_id, mesh, sel, params)
        assert _no_unused(res.mesh), tool_id
        assert _no_degenerate(res.mesh), tool_id
        assert _consistent(res.mesh), tool_id
        s = res.selection
        assert all(0 <= i < len(res.mesh.points) for i in s.points), tool_id
        assert all(0 <= f < len(res.mesh.polygons) for f in s.polygons), tool_id
        assert all(e in set(res.mesh.edges) for e in s.edges), tool_id


def test_empty_selection_reports_for_every_tool():
    cube = Mesh.cube(200.0)
    for tool_id in MERGE_TOOLS:
        if tool_id == "optimize":
            continue
        for mode in get_tool(tool_id).modes:
            res = run_tool(tool_id, cube, Selection(mode), {})
            assert not res.ok and res.message, (tool_id, mode)


def test_optimize_with_empty_point_selection_uses_whole_mesh():
    res = run_tool("optimize", _dirty_mesh(), Selection("points"), {})
    assert res.ok and len(res.mesh.points) == 6


def test_c4d_option_labels():
    assert get_tool("bridge").param("delete_original").label == "Delete Original Polygons"
    assert get_tool("close_polygon_hole").param("create_ngons").label == "Create N-gons"
    assert get_tool("connect_points_edges").param("preserve_ngons").label == "Preserve N-gons"
    assert get_tool("disconnect").param("preserve_groups").label == "Preserve Groups"
    assert get_tool("disconnect").param("preserve_groups").modes == ("polygons",)
    opt = get_tool("optimize")
    assert opt.param("tolerance").label == "Tolerance" and opt.param("tolerance").minimum == 0.0
    assert [p.label for p in opt.params] == ["Polygons", "Unused Points", "Points", "Tolerance"]
    for tool_id in ("melt", "dissolve", "split"):
        assert get_tool(tool_id).params == ()
    for tool_id in ("weld", "bridge", "stitch_and_sew", "close_polygon_hole"):
        spec = get_tool(tool_id)
        assert spec.interactive and "runtime" in spec.extra
        for p in spec.params:
            if p.kind == "runtime":
                assert p.default is None and p.key in spec.extra["runtime"]
    for tool_id in ("connect_points_edges", "melt", "dissolve", "optimize", "disconnect", "split"):
        assert not get_tool(tool_id).interactive


def test_shortcuts_are_unique_across_registry():
    shortcuts = [get_tool(t).shortcut for t in tool_ids() if get_tool(t).shortcut]
    assert len(shortcuts) == len(set(shortcuts))
    expected = {"weld": "M~Q", "bridge": "M~B", "stitch_and_sew": "M~P", "close_polygon_hole": "M~D",
                "connect_points_edges": "M~M", "melt": "U~Z", "dissolve": "M~N", "optimize": "U~O",
                "disconnect": "U~D", "split": "U~P"}
    for tool_id, key in expected.items():
        assert get_tool(tool_id).shortcut == key


def test_weld_edge_collapse_on_grid():
    grid = _grid(4, 4)
    res = run_tool("weld", grid, Selection("edges", edges={(6, 7)}), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 24 and len(m.polygons) == 16
    assert sorted(len(p) for p in m.polygons).count(3) == 2
    assert _consistent(m) and _no_unused(m) and _max_edge_use(m) <= 2
    assert np.all(m.polygon_normals()[:, 1] > 0.99)
    assert res.selection.mode == "edges" and not res.selection.edges


def test_weld_runtime_position_and_boundary_points():
    grid = _grid(4, 4)
    res = run_tool("weld", grid, Selection("points", points={0, 1}), {"position": (0.0, 0.0, 0.0)})
    assert res.ok
    (p,) = res.selection.points
    assert np.allclose(res.mesh.points[p], 0.0)
    assert len(res.mesh.polygons) == 16 and len(res.mesh.polygons[0]) == 3
    assert _consistent(res.mesh) and _no_unused(res.mesh)


def test_weld_keeps_previously_isolated_points():
    cube = Mesh.cube(200.0)
    cube.points = np.vstack([cube.points, [[500.0, 0.0, 0.0]]])
    res = run_tool("weld", cube, Selection("points", points={2, 3}), {})
    assert res.ok and len(res.mesh.points) == 8
    assert np.allclose(res.mesh.points[-1], [500.0, 0.0, 0.0])


def test_weld_repeated_until_single_point():
    m = Mesh.cube(200.0)
    for _ in range(3):
        res = run_tool("weld", m, Selection("points", points={0, 1}), {})
        assert res.ok and _no_degenerate(res.mesh) and _no_unused(res.mesh)
        m = res.mesh
    assert len(m.points) == 5


def test_bridge_coplanar_polygons_keeps_winding():
    grid = _grid(4, 4)
    res = run_tool("bridge", grid, Selection("polygons", polygons={0, 15}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 18 and len(m.points) == 25
    assert _consistent(m) and _max_edge_use(m) <= 2
    assert res.selection.polygons == {14, 15, 16, 17}


def test_bridge_tube_border_loops_builds_inner_wall():
    tube = _tube(8, 2)
    bottom = {edge_key(k, (k + 1) % 8) for k in range(8)}
    top = {edge_key(16 + k, 16 + (k + 1) % 8) for k in range(8)}
    res = run_tool("bridge", tube, Selection("edges", edges=bottom | top), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 24 and _manifold(m) and _consistent(m)
    assert res.selection.edges == bottom | top
    single = run_tool("bridge", _tube(8, 1), Selection("edges", edges=bottom | {edge_key(8 + k, 8 + (k + 1) % 8) for k in range(8)}), {})
    assert not single.ok


def test_bridge_rotated_loop_pairs_nearest_points():
    sq = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 100.0), (0.0, 0.0, 100.0)]
    top = [(x, 200.0, z) for x, _, z in sq]
    top = top[2:] + top[:2]
    mesh = Mesh(sq + top, [(0, 1, 2, 3), (4, 7, 6, 5)])
    edges = {(0, 1), (1, 2), (2, 3), (0, 3), (4, 5), (5, 6), (6, 7), (4, 7)}
    res = run_tool("bridge", mesh, Selection("edges", edges=edges), {})
    assert res.ok
    m = res.mesh
    assert _manifold(m) and _consistent(m) and _outward(m)
    for poly in m.polygons[2:]:
        ring = m.points[list(poly)]
        assert np.isclose(np.ptp(ring[:, 0]) * np.ptp(ring[:, 2]), 0.0)


def test_bridge_refuses_duplicate_polygons():
    cube = Mesh.cube(200.0)
    assert not run_tool("bridge", cube, Selection("edges", edges={(0, 3), (4, 7)}), {}).ok
    assert not run_tool("bridge", cube, Selection("polygons", polygons={0, 1}), {}).ok
    assert not run_tool("bridge", cube, Selection("points", points={0, 3, 4, 7}), {}).ok
    assert not run_tool("bridge", cube, Selection("edges"), {"edge_a": (0, 3), "edge_b": (0, 3)}).ok


def test_bridge_collinear_border_edges_breaks_tie_by_winding():
    grid = _grid(4, 4)
    res = run_tool("bridge", grid, Selection("polygons"), {"edge_a": (9, 14), "edge_b": (19, 24)})
    assert res.ok
    assert _consistent(res.mesh) and res.selection.polygons == {16}


def test_bridge_runtime_edges_must_exist():
    res = run_tool("bridge", _two_quads(200.0), Selection("edges"), {"edge_a": (0, 2), "edge_b": (4, 7)})
    assert not res.ok


def test_bridge_unequal_open_chains():
    a = [(0.0, 0.0, z) for z in (0.0, 100.0, 200.0)]
    b = [(300.0, 0.0, z) for z in (0.0, 200.0)]
    left = Mesh(a + [(-100.0, 0.0, 0.0), (-100.0, 0.0, 100.0), (-100.0, 0.0, 200.0)] + b
                + [(400.0, 0.0, 0.0), (400.0, 0.0, 200.0)],
                [(0, 3, 4, 1), (1, 4, 5, 2), (6, 7, 9, 8)])
    res = run_tool("bridge", left, Selection("edges", edges={(0, 1), (1, 2), (6, 7)}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 5 and _consistent(m) and _max_edge_use(m) <= 2
    assert sorted(len(p) for p in m.polygons[3:]) == [3, 4]
    assert np.all(m.polygon_normals()[:, 1] > 0.99)


def test_stitch_rejects_interior_edges():
    cube = Mesh.cube(200.0)
    assert not run_tool("stitch_and_sew", cube, Selection("edges", edges={(0, 1), (6, 7)}), {}).ok
    assert not run_tool("stitch_and_sew", cube, Selection("edges", edges={(0, 1), (4, 5)}),
                        {"create_polygons": True}).ok


def test_stitch_restores_disconnected_edge():
    cut = run_tool("disconnect", _grid(2, 1), Selection("edges", edges={edge_key(2, 3)}), {})
    assert len(cut.mesh.points) == 8
    res = run_tool("stitch_and_sew", cut.mesh, Selection("edges", edges=cut.selection.edges), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 6 and len(m.polygons) == 2 and _consistent(m)
    assert sum(1 for v in edge_faces(m).values() if len(v) == 2) == 1
    assert np.all(m.polygon_normals()[:, 1] > 0.99)


def test_stitch_zipper_with_shared_point():
    grid = _grid(2, 2)
    cut = run_tool("disconnect", grid, Selection("edges", edges={edge_key(3, 4)}), {})
    assert len(cut.mesh.points) == 10 and len(cut.selection.edges) == 2
    for weld_to in ("Center", "First Edge", "Second Edge"):
        res = run_tool("stitch_and_sew", cut.mesh, Selection("edges", edges=cut.selection.edges),
                       {"weld_to": weld_to})
        assert res.ok
        m = res.mesh
        assert len(m.points) == 9 and len(m.polygons) == 4
        assert _consistent(m) and _no_unused(m) and _max_edge_use(m) == 2
        assert np.allclose(sorted(map(tuple, m.points)), sorted(map(tuple, grid.points)))
    picked = run_tool("stitch_and_sew", cut.mesh, Selection("edges"), {"edge_a": (3, 4), "edge_b": (9, 4)})
    assert picked.ok and len(picked.mesh.points) == 9 and _consistent(picked.mesh)
    odd = run_tool("stitch_and_sew", cut.mesh, Selection("edges", edges={(3, 4)}), {})
    assert not odd.ok


def test_stitch_points_mode_closes_tube_into_torus():
    tube = _tube(8, 3)
    rings = set(range(8)) | set(range(24, 32))
    res = run_tool("stitch_and_sew", tube, Selection("points", points=rings), {"weld_to": "First Edge"})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 24 and len(m.polygons) == 24
    assert _manifold(m) and _consistent(m)
    assert len(res.selection.points) == 8


def test_stitch_create_polygons_between_chains():
    res = run_tool("stitch_and_sew", _two_quads(200.0), Selection("edges", edges={(1, 2), (4, 7)}),
                   {"create_polygons": True})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 3 and len(m.points) == 8 and _consistent(m)
    assert np.all(m.polygon_normals()[:, 1] > 0.99)
    assert res.selection.edges == {(1, 2), (4, 7)}


def test_close_hole_tube_ends_outward():
    tube = _tube(8, 2)
    res = run_tool("close_polygon_hole", tube, Selection("points", points={0, 16}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 18 and _manifold(m) and _consistent(m) and _outward(m)
    assert sorted(len(p) for p in m.polygons[16:]) == [8, 8]


def test_close_hole_triangles_on_tube_stay_closed():
    res = run_tool("close_polygon_hole", _tube(8, 1), Selection("polygons", polygons={0}),
                   {"create_ngons": False})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 8 + 12 and _manifold(m) and _consistent(m) and _outward(m)
    assert res.selection.polygons == set(range(8, 20))


def test_close_hole_refuses_backface_of_single_polygon():
    assert not run_tool("close_polygon_hole", _hexagon(), Selection("points", points={0}), {}).ok
    two = _two_quads(300.0)
    assert not run_tool("close_polygon_hole", two, Selection("edges"), {"edge": (1, 2)}).ok


def test_close_hole_grid_outer_border():
    grid = _grid(4, 4)
    res = run_tool("close_polygon_hole", grid, Selection("points", points={0}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 17 and len(m.polygons[16]) == 16
    assert _manifold(m) and _consistent(m)
    assert m.polygon_normals()[16][1] < -0.99


def test_close_hole_pinched_border_fills_both_holes():
    grid = _grid(4, 4)
    holes = {5, 10}
    mesh = Mesh(grid.points, [p for k, p in enumerate(grid.polygons) if k not in holes])
    pinch = 12
    assert all(pinch in grid.polygons[k] for k in holes)
    res = run_tool("close_polygon_hole", mesh, Selection("points", points={pinch}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 16 and _consistent(m) and _no_degenerate(m)
    assert _max_edge_use(m) == 2
    assert np.all(m.polygon_normals()[:, 1] > 0.99)


def test_border_walk_splits_figure_eight_loops():
    from quartz_studio.modeling import ops_merge
    assert ops_merge._split_pinches([1, 2, 3, 9, 4, 5, 9, 6]) == [[9, 4, 5], [1, 2, 3, 9, 6]]
    assert ops_merge._split_pinches([1, 2, 3]) == [[1, 2, 3]]
    assert ops_merge._split_pinches([]) == []


def test_close_hole_repeat_reports():
    first = run_tool("close_polygon_hole", _open_cube(), Selection("points", points={3}), {})
    again = run_tool("close_polygon_hole", first.mesh, Selection("points", points={3}), {})
    assert not again.ok


def test_connect_points_across_ngon():
    res = run_tool("connect_points_edges", _hexagon(), Selection("points", points={0, 3}), {})
    assert res.ok
    m = res.mesh
    assert sorted(len(p) for p in m.polygons) == [4, 4] and _consistent(m)
    assert np.all(m.polygon_normals()[:, 1] > 0.99)


def test_connect_points_adjacent_does_nothing():
    res = run_tool("connect_points_edges", Mesh.cube(200.0), Selection("points", points={0, 1}), {})
    assert not res.ok


def test_connect_edges_ring_on_tube():
    tube = _tube(8, 1)
    ring = {edge_key(k, 8 + k) for k in range(8)}
    res = run_tool("connect_points_edges", tube, Selection("edges", edges=ring), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 16 and len(m.points) == 24 and _consistent(m) and _no_unused(m)
    assert len(res.selection.edges) == 8
    for e in res.selection.edges:
        assert np.allclose(m.points[list(e)][:, 1], 50.0)
    again = run_tool("connect_points_edges", m, Selection("edges", edges={edge_key(k, 16 + k) for k in range(8)}), {})
    assert again.ok and len(again.mesh.polygons) == 24 and _consistent(again.mesh)


def test_connect_edges_preserve_ngons_on_cube_stays_manifold():
    for preserve in (False, True):
        res = run_tool("connect_points_edges", Mesh.cube(200.0), Selection("edges", edges={(0, 1)}),
                       {"preserve_ngons": preserve})
        assert res.ok
        assert _manifold(res.mesh) and _consistent(res.mesh) and _outward(res.mesh)


def test_melt_border_point_of_grid():
    res = run_tool("melt", _grid(2, 2), Selection("points", points={1}), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 3 and len(m.points) == 8
    assert sorted(len(p) for p in m.polygons) == [4, 4, 5]
    assert _consistent(m) and np.all(m.polygon_normals()[:, 1] > 0.99)


def test_melt_repeated_on_result():
    first = run_tool("melt", _grid(4, 4), Selection("polygons", polygons={0, 1}), {})
    (f,) = first.selection.polygons
    second = run_tool("melt", first.mesh, Selection("polygons", polygons={f, 0}), {})
    assert second.ok
    assert len(second.mesh.polygons) == 14 and _consistent(second.mesh)
    assert np.all(second.mesh.polygon_normals()[:, 1] > 0.99)


def test_melt_cube_point_keeps_manifold():
    res = run_tool("melt", Mesh.cube(200.0), Selection("points", points={6}), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 7 and len(m.polygons) == 4
    assert _manifold(m) and _consistent(m)


def test_dissolve_tube_edge_ring():
    tube = _tube(8, 2)
    ring = {edge_key(8 + k, 8 + (k + 1) % 8) for k in range(8)}
    res = run_tool("dissolve", tube, Selection("edges", edges=ring), {})
    assert res.ok
    assert len(res.mesh.polygons) == 8 and len(res.mesh.points) == 16
    assert all(len(p) == 4 for p in res.mesh.polygons) and _consistent(res.mesh)
    assert sorted(set(np.round(res.mesh.points[:, 1], 6))) == [0.0, 200.0]
    one = run_tool("dissolve", tube, Selection("edges", edges={edge_key(8, 9)}), {})
    assert one.ok
    m = one.mesh
    assert len(m.polygons) == 15 and _consistent(m) and _no_unused(m)


def test_dissolve_border_edge_reports():
    res = run_tool("dissolve", _grid(2, 2), Selection("edges", edges={edge_key(0, 1)}), {})
    assert not res.ok


def test_optimize_after_disconnect_restores_cube():
    cut = run_tool("disconnect", Mesh.cube(200.0), Selection("polygons", polygons={1, 4}),
                   {"preserve_groups": False})
    res = run_tool("optimize", cut.mesh, Selection("polygons", polygons={1, 4}), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 8 and len(m.polygons) == 6
    assert _manifold(m) and _consistent(m) and _outward(m)
    assert res.selection.polygons == {1, 4}


def test_optimize_keeps_flat_but_valid_polygons():
    mesh = Mesh([(0, 0, 0), (100, 0, 0), (200, 0, 0), (100, 0, 100)], [(0, 3, 1), (1, 3, 2), (0, 1, 2)])
    res = run_tool("optimize", mesh, Selection("model"), {})
    assert len(res.mesh.polygons) == 3


def test_disconnect_boundary_point_of_grid():
    res = run_tool("disconnect", _grid(2, 2), Selection("points", points={1}), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 10 and _consistent(m) and _no_unused(m)
    assert len(res.selection.points) == 2


def test_disconnect_edge_loop_separates_tube():
    tube = _tube(8, 2)
    ring = {edge_key(8 + k, 8 + (k + 1) % 8) for k in range(8)}
    res = run_tool("disconnect", tube, Selection("edges", edges=ring), {})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 32 and len(m.polygons) == 16
    assert _consistent(m) and _no_unused(m) and _max_edge_use(m) <= 2
    assert len(res.selection.edges) == 16
    assert all(len(edge_faces(m)[e]) == 1 for e in res.selection.edges)


def test_disconnect_repeated_is_stable():
    first = run_tool("disconnect", Mesh.cube(200.0), Selection("polygons", polygons={4}), {})
    second = run_tool("disconnect", first.mesh, first.selection, {})
    assert second.ok and len(second.mesh.points) == len(first.mesh.points)


def test_split_repeated_and_edges_mode():
    cube = Mesh.cube(200.0)
    first = run_tool("split", cube, Selection("polygons", polygons={0, 1}), {})
    second = run_tool("split", first.mesh, first.selection, {})
    assert len(second.mesh.polygons) == 10 and len(second.mesh.points) == 24
    assert _consistent(Mesh(second.mesh.points, second.mesh.polygons[6:]))
    edges = {(0, 3), (2, 3), (1, 2), (0, 1)}
    res = run_tool("split", cube, Selection("edges", edges=edges), {})
    assert res.ok and len(res.mesh.polygons) == 7 and len(res.selection.edges) == 4


def test_no_comments_or_docstrings_in_merge_files():
    import ast
    import io
    import tokenize
    paths = [os.path.join(STUDIO_ROOT, "quartz_studio", "modeling", "ops_merge.py"), os.path.abspath(__file__)]
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        assert not any(t.type == tokenize.COMMENT for t in tokens), path
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                assert ast.get_docstring(node) is None, path


def _no_flat(mesh: Mesh) -> bool:
    return all(face_area(mesh, k) > 1e-6 for k in range(len(mesh.polygons)))


def _all_points(mesh: Mesh) -> Selection:
    return Selection("points", points=set(range(len(mesh.points))))


def _clean_or_refused(tool_id: str, mesh: Mesh, sel: Selection):
    res = run_tool(tool_id, mesh, sel, {})
    if not res.ok:
        assert res.message, tool_id
        assert res.mesh.polygons == mesh.polygons and np.array_equal(res.mesh.points, mesh.points), tool_id
        return res
    assert _no_unused(res.mesh) and _no_degenerate(res.mesh) and _no_flat(res.mesh), tool_id
    assert _consistent(res.mesh) and res.mesh is not mesh, tool_id
    return res


def test_all_points_of_cube_sphere_cylinder_are_refused():
    shapes = (Mesh.cube(200.0), primitives.sphere(), primitives.cylinder())
    for mesh in shapes:
        for tool_id in ("dissolve", "melt"):
            res = run_tool(tool_id, mesh, _all_points(mesh), {})
            assert not res.ok and res.message, tool_id
            assert res.mesh.polygons == mesh.polygons and np.array_equal(res.mesh.points, mesh.points), tool_id


def test_all_points_of_torus_stay_clean_and_closed():
    torus = primitives.torus()
    for tool_id in ("dissolve", "melt"):
        res = _clean_or_refused(tool_id, torus, _all_points(torus))
        assert res.ok and len(res.mesh.polygons) == 24 and _manifold(res.mesh), tool_id


def test_dissolve_one_cube_edge_stays_closed():
    res = run_tool("dissolve", Mesh.cube(200.0), Selection("edges", edges={edge_key(0, 1)}), {})
    assert res.ok and _manifold(res.mesh) and _consistent(res.mesh)
    assert len(res.mesh.polygons) == 5


def test_all_points_of_plane_refuse_collinear_triangle():
    plane = primitives.plane(400.0, 400.0, 4, 4)
    for tool_id in ("dissolve", "melt"):
        res = run_tool(tool_id, plane, _all_points(plane), {})
        assert not res.ok and res.message
        assert res.mesh.polygons == plane.polygons and np.array_equal(res.mesh.points, plane.points)


def test_prune_drops_fresh_degenerate_and_duplicate_polygons():
    pts = np.array([[0, 0, 0], [100, 0, 0], [200, 0, 0], [0, 0, 100], [100, 0, 100], [0, 100, 0]], float)
    polys = [(0, 1, 3), (0, 3, 1), (0, 1, 2), (3, 4, 5)]
    out, index = ops_merge._prune(pts, polys, [False, True, True, True])
    assert out == [(0, 1, 3), (3, 4, 5)]
    assert index == {0: 0, 3: 1}


def test_dissolve_keeps_unselected_geometry():
    mesh = _two_cubes()
    res = run_tool("dissolve", mesh, Selection("edges", edges={edge_key(0, 1)}), {})
    assert res.ok
    far = [p for p in res.mesh.polygons if np.all(res.mesh.points[list(p)][:, 0] > 150.0)]
    assert len(far) == 6 and _consistent(res.mesh)


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
