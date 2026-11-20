from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.modeling import Selection, get_tool, run_tool, tool_ids
from quartz_studio.modeling.meshkit import compact, edge_faces, edge_key
from quartz_studio.modeling.primitives import cube as prim_cube, sphere
from quartz_studio.scene import Mesh

COMMAND_IDS = ("subdivide", "triangulate", "untriangulate", "reverse_normals", "align_normals",
               "spin_edge", "collapse", "mirror", "delete")


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


def _volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        ring = mesh.points[list(poly)]
        for i in range(1, len(ring) - 1):
            total += float(np.linalg.det(np.array([ring[0], ring[i], ring[i + 1]])))
    return total / 6.0


def _top_face_index(mesh: Mesh) -> int:
    return int(np.argmax(mesh.polygon_normals()[:, 1]))


def _grid(n: int = 2, size: float = 100.0) -> Mesh:
    pts = [(x * size, 0.0, z * size) for z in range(n + 1) for x in range(n + 1)]
    polys = []
    for z in range(n):
        for x in range(n):
            a = z * (n + 1) + x
            polys.append((a, a + n + 1, a + n + 2, a + 1))
    return Mesh(pts, polys)


def _tri_cube() -> Mesh:
    cube = Mesh.cube(200.0)
    return run_tool("triangulate", cube, Selection("model"), {}).mesh


def test_registry_lists_command_tools():
    ids = tool_ids()
    for tool_id in COMMAND_IDS:
        assert tool_id in ids
    assert "extrude" in ids
    assert get_tool("subdivide").section == "COMMANDS"
    assert get_tool("triangulate").section == "CONVERSION"
    assert get_tool("reverse_normals").section == "NORMALS"
    assert get_tool("mirror").section == "TRANSFORM"
    assert get_tool("spin_edge").modes == ("edges", "polygons")


def test_parameter_defaults_and_labels():
    sub = get_tool("subdivide")
    assert sub.defaults() == {"subdivision_surface": False, "subdivision": 1, "max_angle": 180.0}
    assert [p.label for p in sub.params] == ["Subdivision Surface", "Subdivision", "Maximum Angle"]
    assert sub.clamp({"subdivision": 0})["subdivision"] == 1
    unt = get_tool("untriangulate")
    assert unt.defaults() == {"evaluate_angle": False, "angle": 0.1}
    mir = get_tool("mirror")
    labels = [p.label for p in mir.params if p.kind != "runtime"]
    assert labels == ["Coordinate System", "Mirror Plane", "Duplicate Points", "Weld Points", "Tolerance"]
    d = mir.defaults()
    assert d["coordinate_system"] == "Object" and d["mirror_plane"] == "XY"
    assert d["duplicate_points"] is True and d["tolerance"] == 0.01
    assert mir.param("mirror_plane").choices == ("XY", "ZX", "YZ")
    assert set(mir.extra["runtime"]) == {"plane_origin", "object_matrix"}
    for tool_id in ("triangulate", "reverse_normals", "align_normals", "spin_edge", "collapse", "delete"):
        assert get_tool(tool_id).params == ()
        assert get_tool(tool_id).interactive is False


def test_subdivide_linear_cube():
    cube = Mesh.cube(200.0)
    res = run_tool("subdivide", cube, Selection("model"), {})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 24 and len(m.points) == 26
    assert _manifold(m) and _consistent(m)
    assert np.allclose(np.abs(m.points).max(axis=1), 100.0)
    assert abs(_volume(m) - 200.0 ** 3) < 1e-6
    assert len(cube.polygons) == 6


def test_subdivide_count_two():
    res = run_tool("subdivide", Mesh.cube(200.0), Selection("model"), {"subdivision": 2})
    assert len(res.mesh.polygons) == 96
    assert _manifold(res.mesh) and _consistent(res.mesh)


def test_subdivide_surface_smooths_cube():
    res = run_tool("subdivide", Mesh.cube(200.0), Selection("model"), {"subdivision_surface": True})
    m = res.mesh
    assert len(m.polygons) == 24 and _manifold(m) and _consistent(m)
    corners = m.points[:8]
    assert np.allclose(np.abs(corners), 100.0 * 5.0 / 9.0)
    assert np.allclose(np.abs(m.points[8:20]).max(axis=1), 75.0)
    assert np.allclose(np.abs(m.points[20:]).max(axis=1), 100.0)


def test_subdivide_max_angle_keeps_hard_edges():
    res = run_tool("subdivide", Mesh.cube(200.0), Selection("model"),
                   {"subdivision_surface": True, "max_angle": 45.0})
    assert np.allclose(res.mesh.points[:8], Mesh.cube(200.0).points)
    assert abs(_volume(res.mesh) - 200.0 ** 3) < 1e-6


def test_subdivide_selected_polygon_makes_ngon_neighbours():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("subdivide", cube, Selection("polygons", polygons={top}), {})
    m = res.mesh
    assert len(m.polygons) == 9
    assert _manifold(m) and _consistent(m)
    assert len(res.selection.polygons) == 4
    assert sorted(len(p) for p in m.polygons).count(5) == 4
    assert all(np.isclose(m.points[list(m.polygons[f])][:, 1], 100.0).all() for f in res.selection.polygons)


def test_subdivide_triangle_linear_and_smooth():
    tri = Mesh([(0, 0, 0), (100, 0, 0), (0, 0, -100)], [(0, 1, 2)])
    lin = run_tool("subdivide", tri, Selection("polygons", polygons={0}), {})
    assert len(lin.mesh.polygons) == 4 and all(len(p) == 3 for p in lin.mesh.polygons)
    assert _consistent(lin.mesh)
    smooth = run_tool("subdivide", tri, Selection("polygons", polygons={0}), {"subdivision_surface": True})
    assert len(smooth.mesh.polygons) == 3 and all(len(p) == 4 for p in smooth.mesh.polygons)
    normals = smooth.mesh.polygon_normals()
    assert np.allclose(normals, tri.polygon_normals()[0])


def test_subdivide_edges_splits_edge_in_neighbours():
    cube = Mesh.cube(200.0)
    res = run_tool("subdivide", cube, Selection("edges", edges={(0, 1)}), {"subdivision": 2})
    m = res.mesh
    assert len(m.points) == 10
    assert np.allclose(m.points[8], (-100 + 200 / 3, -100, -100))
    assert len(res.selection.edges) == 3
    assert _manifold(m) and _consistent(m)
    assert sum(len(p) == 6 for p in m.polygons) == 2


def test_triangulate_cube_and_selection():
    cube = Mesh.cube(200.0)
    res = run_tool("triangulate", cube, Selection("polygons", polygons={0}), {})
    m = res.mesh
    assert len(m.polygons) == 7
    assert res.selection.polygons == {0, 6}
    assert _manifold(m) and _consistent(m)
    full = _tri_cube()
    assert len(full.polygons) == 12 and all(len(p) == 3 for p in full.polygons)
    assert abs(_volume(full) - 200.0 ** 3) < 1e-6


def test_triangulate_ngon_keeps_normal():
    pts = [(np.cos(a) * 100, 0, -np.sin(a) * 100) for a in np.linspace(0, 2 * np.pi, 7)[:-1]]
    hexagon = Mesh(pts, [tuple(range(6))])
    res = run_tool("triangulate", hexagon, Selection("polygons"), {})
    assert len(res.mesh.polygons) == 4
    assert np.allclose(res.mesh.polygon_normals(), hexagon.polygon_normals()[0])


def test_triangulate_reports_when_nothing_to_do():
    tri = Mesh([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])
    assert not run_tool("triangulate", tri, Selection("polygons"), {}).ok


def test_untriangulate_restores_cube():
    res = run_tool("untriangulate", _tri_cube(), Selection("model"), {})
    m = res.mesh
    assert res.ok
    assert len(m.polygons) == 6 and all(len(p) == 4 for p in m.polygons)
    assert _manifold(m) and _consistent(m)
    assert abs(_volume(m) - 200.0 ** 3) < 1e-6


def test_untriangulate_prefers_diagonals_on_grid():
    grid = run_tool("triangulate", _grid(3), Selection("model"), {}).mesh
    res = run_tool("untriangulate", grid, Selection("polygons"), {})
    m = res.mesh
    assert len(m.polygons) == 9 and all(len(p) == 4 for p in m.polygons)
    assert _consistent(m)
    assert sorted(set(m.edges)) == sorted(set(_grid(3).edges))
    assert res.selection.polygons == set()


def test_untriangulate_evaluate_angle():
    fold = Mesh([(0, 0, 0), (100, 0, 0), (100, 50, -100), (0, 0, -100)], [(0, 1, 2), (0, 2, 3)])
    loose = run_tool("untriangulate", fold, Selection("polygons"), {})
    assert loose.ok and len(loose.mesh.polygons) == 1
    strict = run_tool("untriangulate", fold, Selection("polygons"), {"evaluate_angle": True, "angle": 5.0})
    assert not strict.ok and len(strict.mesh.polygons) == 2
    wide = run_tool("untriangulate", fold, Selection("polygons"), {"evaluate_angle": True, "angle": 60.0})
    assert len(wide.mesh.polygons) == 1


def test_reverse_normals_all_and_selected():
    cube = Mesh.cube(200.0)
    res = run_tool("reverse_normals", cube, Selection("model"), {})
    assert np.allclose(res.mesh.polygon_normals(), -cube.polygon_normals())
    assert _consistent(res.mesh) and _volume(res.mesh) < 0
    one = run_tool("reverse_normals", cube, Selection("polygons", polygons={2}), {})
    normals = one.mesh.polygon_normals()
    assert np.allclose(normals[2], -cube.polygon_normals()[2])
    assert np.allclose(normals[3], cube.polygon_normals()[3])
    assert one.selection.polygons == {2}


def test_align_normals_fixes_flipped_faces_outward():
    cube = Mesh.cube(200.0)
    broken = run_tool("reverse_normals", cube, Selection("polygons", polygons={1, 4}), {}).mesh
    assert not _consistent(broken)
    res = run_tool("align_normals", broken, Selection("model"), {})
    assert _consistent(res.mesh) and _volume(res.mesh) > 0
    inside = run_tool("reverse_normals", cube, Selection("model"), {}).mesh
    fixed = run_tool("align_normals", inside, Selection("polygons"), {})
    assert np.allclose(fixed.mesh.polygon_normals(), cube.polygon_normals())


def test_align_normals_open_mesh_follows_majority():
    grid = _grid(3)
    up = grid.polygon_normals()[0]
    broken = run_tool("reverse_normals", grid, Selection("polygons", polygons={4}), {}).mesh
    res = run_tool("align_normals", broken, Selection("polygons"), {})
    assert np.allclose(res.mesh.polygon_normals(), up)


def test_align_normals_selection_follows_unselected_neighbours():
    grid = _grid(3)
    up = grid.polygon_normals()[0]
    broken = run_tool("reverse_normals", grid, Selection("polygons", polygons={3, 4, 5}), {}).mesh
    res = run_tool("align_normals", broken, Selection("polygons", polygons={3, 4, 5}), {})
    assert np.allclose(res.mesh.polygon_normals(), up)


def test_spin_edge_between_two_triangles():
    quad = Mesh([(0, 0, 0), (100, 0, 0), (100, 0, -100), (0, 0, -100)], [(0, 1, 2), (0, 2, 3)])
    res = run_tool("spin_edge", quad, Selection("edges", edges={(0, 2)}), {})
    assert res.ok
    assert res.selection.edges == {(1, 3)}
    assert (0, 2) not in res.mesh.edges and (1, 3) in res.mesh.edges
    assert _consistent(res.mesh)
    assert np.allclose(res.mesh.polygon_normals(), quad.polygon_normals()[0])


def test_spin_edge_between_two_quads_on_cube():
    cube = Mesh.cube(200.0)
    e = edge_key(2, 3)
    res = run_tool("spin_edge", cube, Selection("edges", edges={e}), {})
    m = res.mesh
    assert res.ok and e not in m.edges
    new = next(iter(res.selection.edges))
    assert new in m.edges and len(m.polygons) == 6
    assert sorted(len(p) for p in m.polygons) == [4] * 6
    assert _manifold(m) and _consistent(m)


def test_spin_edge_polygon_mode_and_failure():
    quad = Mesh([(0, 0, 0), (100, 0, 0), (100, 0, -100), (0, 0, -100)], [(0, 1, 2), (0, 2, 3)])
    res = run_tool("spin_edge", quad, Selection("polygons", polygons={0, 1}), {})
    assert res.ok and (1, 3) in res.mesh.edges
    assert res.selection.polygons == {0, 1}
    border = run_tool("spin_edge", quad, Selection("edges", edges={(0, 1)}), {})
    assert not border.ok


def test_collapse_points_to_center():
    cube = Mesh.cube(200.0)
    top = cube.polygons[_top_face_index(cube)]
    res = run_tool("collapse", cube, Selection("points", points=set(top)), {})
    m = res.mesh
    assert res.ok and len(m.points) == 5
    assert len(m.polygons) == 5
    p = next(iter(res.selection.points))
    assert np.allclose(m.points[p], (0, 100, 0))
    assert _manifold(m) and _consistent(m)


def test_collapse_edge_on_cube():
    cube = Mesh.cube(200.0)
    res = run_tool("collapse", cube, Selection("edges", edges={(0, 1)}), {})
    m = res.mesh
    assert len(m.points) == 7
    assert any(np.allclose(q, (0, -100, -100)) for q in m.points)
    assert sorted(len(p) for p in m.polygons) == [3, 3, 4, 4, 4, 4]
    assert _manifold(m) and _consistent(m)
    assert res.selection.mode == "edges" and not res.selection.edges


def test_collapse_polygon_groups_separately():
    grid = _grid(3)
    res = run_tool("collapse", grid, Selection("polygons", polygons={0, 8}), {})
    m = res.mesh
    assert len(m.points) == 16 - 6
    assert len(m.polygons) == 9 - 2
    assert _consistent(m)


def test_collapse_needs_selection():
    assert not run_tool("collapse", Mesh.cube(200.0), Selection("points", points={3}), {}).ok


def test_mirror_duplicates_and_welds_half_cube():
    cube = Mesh.cube(200.0)
    half = Mesh(cube.points + (0, 0, 100), cube.polygons[1:])
    res = run_tool("mirror", half, Selection("polygons"), {})
    m = res.mesh
    assert res.ok
    assert len(m.points) == 12 and len(m.polygons) == 10
    assert _manifold(m) and _consistent(m)
    assert abs(_volume(m) - 200.0 * 200.0 * 400.0) < 1e-6
    assert res.selection.polygons == set(range(5, 10))
    loose = run_tool("mirror", half, Selection("polygons"), {"weld_points": False})
    assert len(loose.mesh.points) == 16 and not _manifold(loose.mesh)


def test_mirror_without_weld_and_planes():
    tri = Mesh([(10, 0, 0), (50, 0, 0), (10, 40, 0)], [(0, 1, 2)])
    res = run_tool("mirror", tri, Selection("polygons", polygons={0}),
                   {"mirror_plane": "YZ", "weld_points": False})
    m = res.mesh
    assert len(m.points) == 6 and len(m.polygons) == 2
    assert np.allclose(m.points[3:], [(-10, 0, 0), (-50, 0, 0), (-10, 40, 0)])
    assert np.allclose(m.polygon_normals()[1], m.polygon_normals()[0])
    zx = run_tool("mirror", tri, Selection("polygons"), {"mirror_plane": "ZX"})
    assert np.allclose(zx.mesh.points[-1], (10, -40, 0))
    assert len(zx.mesh.points) == 4


def test_mirror_in_place_keeps_normals_outward():
    cube = Mesh.cube(200.0)
    shifted = Mesh(cube.points + (0, 0, 300), cube.polygons)
    res = run_tool("mirror", shifted, Selection("polygons"), {"duplicate_points": False})
    m = res.mesh
    assert len(m.points) == 8 and np.allclose(m.points[:, 2].mean(), -300)
    assert _volume(m) > 0 and _consistent(m)


def test_mirror_world_coordinates_and_plane_origin():
    tri = Mesh([(0, 0, 0), (10, 0, 0), (0, 10, 0)], [(0, 1, 2)])
    matrix = np.eye(4)
    matrix[0, 3] = 100.0
    world = run_tool("mirror", tri, Selection("points", points={0, 1, 2}),
                     {"coordinate_system": "World", "mirror_plane": "YZ", "object_matrix": matrix})
    assert np.allclose(world.mesh.points[3:], [(-200, 0, 0), (-210, 0, 0), (-200, 10, 0)])
    assert world.selection.points == {3, 4, 5}
    moved = run_tool("mirror", tri, Selection("points", points={1}),
                     {"mirror_plane": "YZ", "plane_origin": (20, 0, 0), "duplicate_points": False})
    assert np.allclose(moved.mesh.points[1], (30, 0, 0))


def test_delete_points_removes_their_polygons():
    cube = Mesh.cube(200.0)
    res = run_tool("delete", cube, Selection("points", points={6}), {})
    m = res.mesh
    assert len(m.points) == 7 and len(m.polygons) == 3
    assert _consistent(m)
    assert not any(np.allclose(q, (100, 100, 100)) for q in m.points)


def test_delete_polygons_removes_unused_points():
    grid = _grid(2)
    res = run_tool("delete", grid, Selection("polygons", polygons={0}), {})
    m = res.mesh
    assert len(m.polygons) == 3 and len(m.points) == 8
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    one = run_tool("delete", cube, Selection("polygons", polygons={top}), {})
    assert len(one.mesh.polygons) == 5 and len(one.mesh.points) == 8


def test_delete_inner_edge_merges_into_ngon():
    grid = _grid(2)
    res = run_tool("delete", grid, Selection("edges", edges={(1, 4)}), {})
    m = res.mesh
    assert len(m.polygons) == 3 and len(m.points) == 9
    assert sorted(len(p) for p in m.polygons) == [4, 4, 6]
    assert _consistent(m)
    assert np.allclose(m.polygon_normals(), grid.polygon_normals()[0])


def test_delete_border_edge_removes_polygon():
    grid = _grid(2)
    res = run_tool("delete", grid, Selection("edges", edges={(0, 1)}), {})
    assert len(res.mesh.polygons) == 3 and len(res.mesh.points) == 8
    assert not any(np.allclose(q, (0, 0, 0)) for q in res.mesh.points)


def test_delete_cross_edges_on_cube_face_region():
    cube = Mesh.cube(200.0)
    sub = run_tool("subdivide", cube, Selection("model"), {}).mesh
    top = [f for f, n in enumerate(sub.polygon_normals()) if n[1] > 0.9]
    ef = edge_faces(sub)
    inner = {e for e, owners in ef.items() if len(owners) == 2 and all(f in top for f in owners)}
    res = run_tool("delete", sub, Selection("edges", edges=inner), {})
    m = res.mesh
    assert len(m.polygons) == 21
    assert _manifold(m) and _consistent(m)
    assert abs(_volume(m) - 200.0 ** 3) < 1e-6


def test_wrong_modes_report():
    cube = Mesh.cube(200.0)
    for tool_id in ("collapse", "mirror", "delete", "spin_edge"):
        assert not run_tool(tool_id, cube, Selection("model"), {}).ok
    assert not run_tool("delete", cube, Selection("polygons"), {}).ok


def test_inputs_are_not_mutated():
    cube = Mesh.cube(200.0)
    before_pts = cube.points.copy()
    before_polys = list(cube.polygons)
    sel = Selection("polygons", polygons={0, 1})
    for tool_id in COMMAND_IDS:
        mode = "edges" if tool_id == "spin_edge" else "polygons"
        s = Selection(mode, edges={(2, 3)}) if mode == "edges" else sel.copy()
        run_tool(tool_id, cube, s, {})
    assert np.array_equal(cube.points, before_pts) and cube.polygons == before_polys



def _ring(n: int = 8, rows: int = 2, caps: bool = False) -> Mesh:
    pts = [(100.0 * np.cos(2 * np.pi * i / n), 100.0 * j, 100.0 * np.sin(2 * np.pi * i / n))
           for j in range(rows + 1) for i in range(n)]
    polys = []
    for j in range(rows):
        for i in range(n):
            a, b = j * n + i, j * n + (i + 1) % n
            polys.append((a, a + n, b + n, b))
    if caps:
        polys.append(tuple(range(n)))
        polys.append(tuple(reversed(range(rows * n, rows * n + n))))
    return Mesh(pts, polys)


def _no_degenerates(mesh: Mesh) -> bool:
    keys = [frozenset(p) for p in mesh.polygons]
    if len(keys) != len(set(keys)):
        return False
    for poly in mesh.polygons:
        ring = mesh.points[list(poly)]
        area = np.linalg.norm(np.cross(ring, np.roll(ring, -1, axis=0)).sum(axis=0))
        if len(set(poly)) != len(poly) or area < 1e-9:
            return False
    return True


def _no_unused_points(mesh: Mesh) -> bool:
    used = {i for p in mesh.polygons for i in p} | {i for e in mesh.loose_edges for i in e}
    return used == set(range(len(mesh.points)))


def _no_overfull_edges(mesh: Mesh) -> bool:
    return all(len(v) <= 2 for v in edge_faces(mesh).values())


def test_ring_fixture_is_closed_and_outward():
    cyl = _ring(caps=True)
    assert _manifold(cyl) and _consistent(cyl) and _volume(cyl) > 0


def test_triangulate_concave_quad_uses_inside_diagonal():
    dart = Mesh([(97.6, 0, 15.8), (-76.9, 0, 66.5), (-51.7, 0, -48.8), (-79.4, 0, -82.2)], [(0, 1, 2, 3)])
    normal = dart.polygon_normals()[0]
    res = run_tool("triangulate", dart, Selection("model"), {})
    assert len(res.mesh.polygons) == 2
    assert np.all(res.mesh.polygon_normals() @ normal > 0.99)
    assert (1, 3) not in res.mesh.edges and (0, 2) in res.mesh.edges


def test_empty_polygon_selection_stays_empty():
    cube = Mesh.cube(200.0)
    for tool_id in ("subdivide", "triangulate"):
        res = run_tool(tool_id, cube, Selection("polygons"), {})
        assert res.ok and res.selection.polygons == set()
    res = run_tool("untriangulate", _tri_cube(), Selection("polygons"), {})
    assert res.ok and res.selection.polygons == set()
    picked = run_tool("subdivide", cube, Selection("polygons", polygons={0, 1}), {})
    assert len(picked.selection.polygons) == 8


def test_subdivide_every_option_on_every_fixture():
    fixtures = [(Mesh.cube(200.0), True), (_grid(4), False), (_ring(caps=True), True), (_ring(), False)]
    for mesh, closed in fixtures:
        for smooth in (False, True):
            for count in (1, 2):
                for angle in (180.0, 30.0):
                    res = run_tool("subdivide", mesh, Selection("model"),
                                   {"subdivision_surface": smooth, "subdivision": count, "max_angle": angle})
                    m = res.mesh
                    assert res.ok and _consistent(m) and _no_degenerates(m) and _no_unused_points(m)
                    assert _manifold(m) if closed else _no_overfull_edges(m)
                    if closed:
                        assert _volume(m) > 0


def test_subdivide_smooth_open_grid_keeps_corners_and_plane():
    grid = _grid(4)
    res = run_tool("subdivide", grid, Selection("model"), {"subdivision_surface": True})
    m = res.mesh
    assert np.allclose(m.points[:, 1], 0.0)
    assert np.allclose(m.points[0], (12.5, 0, 12.5))
    assert np.allclose(m.points[2], (200, 0, 0))
    assert m.points[:, 0].min() >= -1e-9 and m.points[:, 0].max() <= 400 + 1e-9
    assert np.allclose(m.polygon_normals(), grid.polygon_normals()[0])


def test_subdivide_partial_selection_on_cylinder_repeated():
    cyl = _ring(caps=True)
    sel = Selection("polygons", polygons={0, 1, 16})
    for _ in range(2):
        res = run_tool("subdivide", cyl, sel, {"subdivision_surface": True, "max_angle": 40.0})
        cyl, sel = res.mesh, res.selection
        assert _manifold(cyl) and _consistent(cyl) and _no_degenerates(cyl) and _volume(cyl) > 0
    assert len(sel.polygons) == 4 * 4 + 4 * 4 + 8 * 4


def test_subdivide_edges_on_loose_and_border_edges():
    mesh = Mesh([(0, 0, 0), (100, 0, 0), (100, 100, 0), (0, 100, 0), (300, 0, 0)],
                [(0, 1, 2, 3)], [(1, 4)])
    res = run_tool("subdivide", mesh, Selection("edges", edges={(1, 4), (0, 1)}), {"subdivision": 1})
    m = res.mesh
    assert len(m.points) == 7 and len(m.polygons[0]) == 5
    assert len(m.loose_edges) == 2 and len(res.selection.edges) == 4
    assert _consistent(m)


def test_triangulate_untriangulate_round_trip_capped_cylinder():
    cyl = _ring(caps=True)
    tri = run_tool("triangulate", cyl, Selection("model"), {}).mesh
    assert all(len(p) == 3 for p in tri.polygons)
    assert _manifold(tri) and _consistent(tri) and abs(_volume(tri) - _volume(cyl)) < 1e-6
    back = run_tool("untriangulate", tri, Selection("model"), {}).mesh
    assert _manifold(back) and _consistent(back) and abs(_volume(back) - _volume(cyl)) < 1e-6
    assert sum(len(p) == 4 for p in back.polygons) >= 16


def test_untriangulate_selected_triangles_only():
    grid = run_tool("triangulate", _grid(4), Selection("model"), {}).mesh
    ef = edge_faces(grid)
    pair = next(owners for owners in ef.values() if len(owners) == 2)
    res = run_tool("untriangulate", grid, Selection("polygons", polygons=set(pair)), {})
    assert len(res.mesh.polygons) == len(grid.polygons) - 1
    assert len(res.selection.polygons) == 1
    assert len(res.mesh.polygons[next(iter(res.selection.polygons))]) == 4
    assert _consistent(res.mesh)


def test_align_normals_random_flips_on_capped_cylinder():
    cyl = _ring(caps=True)
    flipped = run_tool("reverse_normals", cyl, Selection("polygons", polygons={0, 3, 5, 9, 16}), {}).mesh
    res = run_tool("align_normals", flipped, Selection("model"), {})
    assert np.allclose(res.mesh.polygon_normals(), cyl.polygon_normals())
    assert _consistent(res.mesh) and _volume(res.mesh) > 0


def test_reverse_normals_twice_is_identity():
    cyl = _ring(caps=True)
    once = run_tool("reverse_normals", cyl, Selection("model"), {}).mesh
    twice = run_tool("reverse_normals", once, Selection("model"), {}).mesh
    assert twice.polygons == cyl.polygons


def test_spin_edge_twice_on_triangle_pair_restores_diagonal():
    quad = Mesh([(0, 0, 0), (100, 0, 0), (100, 0, -100), (0, 0, -100)], [(0, 1, 2), (0, 2, 3)])
    first = run_tool("spin_edge", quad, Selection("edges", edges={(0, 2)}), {})
    second = run_tool("spin_edge", first.mesh, first.selection, {})
    assert second.selection.edges == {(0, 2)}
    assert _consistent(second.mesh)
    assert np.allclose(second.mesh.polygon_normals(), quad.polygon_normals()[0])


def test_spin_edge_skips_edges_of_already_spun_polygons():
    grid = _grid(4)
    inner = {e for e, owners in edge_faces(grid).items() if len(owners) == 2}
    res = run_tool("spin_edge", grid, Selection("edges", edges=inner), {})
    m = res.mesh
    assert res.ok and 0 < len(res.selection.edges) < len(inner)
    assert _consistent(m) and _no_degenerates(m)
    assert len(m.polygons) == 16 and all(len(p) == 4 for p in m.polygons)


def test_spin_edge_on_cylinder_keeps_closed_mesh():
    cyl = _ring(caps=True)
    for e in [(0, 8), (8, 9), (0, 1)]:
        res = run_tool("spin_edge", cyl, Selection("edges", edges={e}), {})
        assert res.ok, e
        assert _manifold(res.mesh) and _consistent(res.mesh) and _volume(res.mesh) > 0


def test_collapse_drops_points_orphaned_by_the_collapse():
    tri = Mesh([(0, 0, 0), (100, 0, 0), (0, 100, 0), (500, 500, 500)], [(0, 1, 2)])
    res = run_tool("collapse", tri, Selection("edges", edges={(0, 1)}), {})
    m = res.mesh
    assert m.polygons == []
    assert len(m.points) == 2
    assert any(np.allclose(q, (50, 0, 0)) for q in m.points)
    assert any(np.allclose(q, (500, 500, 500)) for q in m.points)


def test_collapse_boundary_edge_on_grid():
    grid = _grid(4)
    res = run_tool("collapse", grid, Selection("edges", edges={(0, 1)}), {})
    m = res.mesh
    assert len(m.points) == 24 and len(m.polygons) == 16
    assert sorted(len(p) for p in m.polygons).count(3) == 1
    assert _consistent(m) and _no_degenerates(m) and _no_unused_points(m)


def test_collapse_cylinder_cap_makes_closed_cone():
    cyl = _ring(caps=True)
    res = run_tool("collapse", cyl, Selection("polygons", polygons={17}), {})
    m = res.mesh
    assert len(m.points) == 17 and len(m.polygons) == 17
    assert sorted(len(p) for p in m.polygons).count(3) == 8
    assert _manifold(m) and _consistent(m) and _volume(m) > 0
    assert any(np.allclose(q, (0, 200, 0)) for q in m.points)


def test_mirror_half_cylinder_welds_into_closed_tube():
    n = 8
    k = n // 2 + 1
    pts = [(100.0 * np.cos(a), y, 100.0 * np.sin(a))
           for y in (0.0, 100.0) for a in np.linspace(-np.pi / 2, np.pi / 2, k)]
    polys = [(i, i + k, i + k + 1, i + 1) for i in range(k - 1)]
    half = Mesh(pts, polys)
    res = run_tool("mirror", half, Selection("polygons"), {"mirror_plane": "YZ"})
    m = res.mesh
    assert len(m.points) == 2 * n and len(m.polygons) == n
    assert _consistent(m) and _no_overfull_edges(m)
    assert sum(len(v) == 2 for v in edge_faces(m).values()) == n


def test_mirror_in_place_partial_selection_keeps_winding():
    grid = _grid(4)
    res = run_tool("mirror", grid, Selection("polygons", polygons={5}),
                   {"mirror_plane": "YZ", "duplicate_points": False})
    assert res.ok and _consistent(res.mesh)
    assert res.mesh.polygons == grid.polygons
    pts = run_tool("mirror", grid, Selection("points", points={0, 1, 5, 6}),
                   {"mirror_plane": "XY", "duplicate_points": False})
    assert _consistent(pts.mesh)
    assert np.allclose(pts.mesh.points[6], (100, 0, -100))


def test_mirror_every_option_combination():
    cube = Mesh.cube(200.0)
    half = Mesh(cube.points + (0, 0, 100), cube.polygons[1:])
    for plane in ("XY", "ZX", "YZ"):
        for duplicate in (True, False):
            for weld in (True, False):
                for system in ("Object", "World"):
                    for mode in ("points", "edges", "polygons"):
                        res = run_tool("mirror", half, Selection(mode),
                                       {"mirror_plane": plane, "duplicate_points": duplicate,
                                        "weld_points": weld, "coordinate_system": system})
                        assert res.ok and _consistent(res.mesh) and _no_overfull_edges(res.mesh)


def test_mirror_ignores_invalid_indices_and_singular_matrix():
    tri = Mesh([(10, 0, 0), (20, 0, 0), (10, 10, 0)], [(0, 1, 2)])
    res = run_tool("mirror", tri, Selection("points", points={0, 1, 2, 99}), {"mirror_plane": "YZ"})
    assert res.ok and len(res.mesh.points) == 6
    edges = run_tool("mirror", tri, Selection("edges", edges={(0, 1), (5, 77)}), {"mirror_plane": "YZ"})
    assert edges.ok and len(edges.mesh.points) == 5
    assert not run_tool("mirror", tri, Selection("points", points={50}), {}).ok
    flat = run_tool("mirror", tri, Selection("polygons"),
                    {"coordinate_system": "World", "mirror_plane": "YZ", "object_matrix": np.zeros((4, 4))})
    assert flat.ok and np.allclose(flat.mesh.points[3], (-10, 0, 0))


def test_delete_points_drops_orphaned_points_only():
    grid = _grid(4)
    lonely = Mesh(np.vstack([grid.points, [(900, 0, 900)]]), grid.polygons)
    res = run_tool("delete", lonely, Selection("points", points={6}), {})
    m = res.mesh
    assert len(m.polygons) == 12 and len(m.points) == 22
    assert any(np.allclose(q, (900, 0, 900)) for q in m.points)
    for gone in ((0, 0, 0), (100, 0, 0), (0, 0, 100), (100, 0, 100)):
        assert not any(np.allclose(q, gone) for q in m.points)
    assert _consistent(m)
    corner = run_tool("delete", grid, Selection("points", points={1}), {})
    assert len(corner.mesh.points) == 23 and _no_unused_points(corner.mesh)


def test_delete_star_edges_removes_center_point():
    grid = _grid(4)
    res = run_tool("delete", grid, Selection("edges", edges={(1, 6), (5, 6), (6, 7), (6, 11)}), {})
    m = res.mesh
    assert len(m.polygons) == 13 and len(m.points) == 24
    assert max(len(p) for p in m.polygons) == 8
    assert _consistent(m) and _no_unused_points(m)
    assert np.allclose(m.polygon_normals(), grid.polygon_normals()[0])


def test_delete_annulus_edges_reports_failure():
    grid = _grid(3)
    ef = edge_faces(grid)
    radial = {e for e, owners in ef.items() if len(owners) == 2 and 4 not in owners}
    res = run_tool("delete", grid, Selection("edges", edges=radial), {})
    assert not res.ok and res.mesh.polygons == grid.polygons


def test_delete_cylinder_edge_merges_column():
    cyl = _ring(caps=True)
    res = run_tool("delete", cyl, Selection("edges", edges={(8, 9)}), {})
    m = res.mesh
    assert len(m.polygons) == 17 and _manifold(m) and _consistent(m) and _volume(m) > 0


def test_tools_handle_empty_and_degenerate_meshes():
    empty = Mesh(np.zeros((0, 3)), [])
    sliver = Mesh([(0, 0, 0), (100, 0, 0), (200, 0, 0), (0, 100, 0)], [(0, 1, 2), (0, 1, 3)])
    for mesh in (empty, sliver):
        for tool_id in COMMAND_IDS:
            for mode in get_tool(tool_id).modes:
                sel = Selection(mode, points={0, 1, 99}, edges={(0, 1), (7, 70)}, polygons={0, 40})
                res = run_tool(tool_id, mesh, sel, {})
                assert isinstance(res.ok, bool)
    for tool_id in COMMAND_IDS:
        assert not run_tool(tool_id, empty, Selection(get_tool(tool_id).modes[0]), {}).ok


def test_repeated_pipeline_stays_clean():
    mesh = Mesh.cube(200.0)
    steps = [("subdivide", Selection("model"), {"subdivision_surface": True}),
             ("triangulate", Selection("model"), {}),
             ("untriangulate", Selection("model"), {}),
             ("spin_edge", Selection("edges", edges={(0, 8)}), {}),
             ("subdivide", Selection("polygons", polygons={0, 1, 2}), {}),
             ("align_normals", Selection("model"), {})]
    for tool_id, sel, params in steps:
        res = run_tool(tool_id, mesh, sel, params)
        assert res.ok, (tool_id, res.message)
        mesh = res.mesh
        assert _manifold(mesh) and _consistent(mesh) and _no_degenerates(mesh) and _volume(mesh) > 0


def test_no_tool_mutates_input_in_any_mode():
    for mesh in (Mesh.cube(200.0), _grid(3), _ring(caps=True)):
        before = (mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges), list(mesh.edges))
        for tool_id in COMMAND_IDS:
            for mode in get_tool(tool_id).modes:
                sel = Selection(mode, points={0, 1, 2, 3}, edges=set(list(mesh.edges)[:3]), polygons={0, 1})
                frozen = sel.copy()
                run_tool(tool_id, mesh, sel, {"subdivision_surface": True, "duplicate_points": False})
                assert sel.points == frozen.points and sel.edges == frozen.edges
                assert sel.polygons == frozen.polygons
        assert np.array_equal(mesh.points, before[0]) and mesh.polygons == before[1]
        assert mesh.loose_edges == before[2] and mesh.edges == before[3]


def _coincident_pairs(mesh: Mesh, tol: float = 1e-6) -> int:
    d = np.linalg.norm(mesh.points[:, None, :] - mesh.points[None, :, :], axis=2)
    rows, cols = np.triu_indices(len(mesh.points), 1)
    return int((d[rows, cols] <= tol).sum())


def test_mirror_full_grid_cube_adds_nothing():
    grid = prim_cube((200.0, 200.0, 200.0), (2, 2, 2))
    res = run_tool("mirror", grid, Selection("points", points=set(range(len(grid.points)))), {})
    m = res.mesh
    assert res.ok
    assert _coincident_pairs(m) == 0
    assert _no_overfull_edges(m) and _no_degenerates(m) and _no_unused_points(m)
    assert len(m.polygons) == len(grid.polygons) == 24
    assert len(m.points) == len(grid.points)


def test_mirror_half_grid_cube_closes_into_cube():
    grid = prim_cube((200.0, 200.0, 200.0), (2, 2, 2))
    upper = [poly for poly in grid.polygons if grid.points[list(poly), 2].min() >= -1e-9]
    half, _ = compact(Mesh(grid.points, upper))
    res = run_tool("mirror", half, Selection("polygons", polygons=set(range(len(upper)))), {})
    m = res.mesh
    assert res.ok
    assert _manifold(m) and _consistent(m) and _coincident_pairs(m) == 0
    assert len(m.polygons) == 24 and _no_degenerates(m) and _no_unused_points(m)
    assert abs(_volume(m) - 200.0 ** 3) < 1e-6


def test_untriangulate_edge_selection_is_valid_on_sphere():
    sph = sphere()
    poly = sph.polygons[0]
    edges = {edge_key(a, b) for a, b in zip(poly, poly[1:] + poly[:1])}
    res = run_tool("untriangulate", sph, Selection("edges", edges=set(edges)), {})
    m = res.mesh
    assert res.ok
    removed = edges - set(m.edges)
    assert removed
    assert res.selection.mode == "edges"
    assert res.selection.edges == edges - removed
    assert res.selection.edges <= set(m.edges)


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
