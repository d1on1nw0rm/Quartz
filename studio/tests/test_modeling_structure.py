from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import math

import numpy as np

from quartz_studio.modeling import Selection, get_tool, run_tool, tool_ids
from quartz_studio.modeling.meshkit import edge_faces, edge_key, face_area
from quartz_studio.scene import Mesh

NEW_TOOLS = ("set_flow", "set_point_value", "array", "clone", "remove_ngons",
             "retriangulate_ngons", "edge_to_spline")


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


def _top_face_index(mesh: Mesh) -> int:
    normals = mesh.polygon_normals()
    return int(np.argmax(normals[:, 1]))


def _snapshot(mesh: Mesh):
    return mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges)


def _unchanged(mesh: Mesh, snap) -> bool:
    pts, polys, loose = snap
    return np.array_equal(mesh.points, pts) and mesh.polygons == polys and mesh.loose_edges == loose


def _grid_polys(nx: int, ny: int) -> list[tuple[int, int, int, int]]:
    return [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
            for j in range(ny - 1) for i in range(nx - 1)]


def _flat_grid(nx: int, ny: int, step: float = 10.0) -> Mesh:
    pts = [(i * step, 0.0, j * step) for j in range(ny) for i in range(nx)]
    return Mesh(pts, _grid_polys(nx, ny))


def _cylinder() -> Mesh:
    rows = [math.radians(d) for d in (-10.0, -5.0, 0.0, 5.0, 10.0)]
    cols = [math.radians(d) for d in (-20.0, -10.0, 0.0, 10.0, 20.0)]
    radius = 100.0
    pts = []
    for th in rows:
        for ph in cols:
            r = radius * math.cos(th)
            pts.append((r * math.cos(ph), radius * math.sin(th), r * math.sin(ph)))
    return Mesh(pts, _grid_polys(5, 5))


def _hexagon() -> Mesh:
    pts = [(100.0 * math.cos(math.radians(60.0 * k)), 0.0, 100.0 * math.sin(math.radians(60.0 * k)))
           for k in range(6)]
    return Mesh(pts, [(0, 1, 2, 3, 4, 5)])


def _hex_prism() -> Mesh:
    bottom = [(100.0 * math.cos(math.radians(60.0 * k)), 0.0, 100.0 * math.sin(math.radians(60.0 * k)))
              for k in range(6)]
    top = [(x, 50.0, z) for x, _, z in bottom]
    polys = [tuple(range(6)), tuple(range(11, 5, -1))]
    for k in range(6):
        polys.append((k, 6 + k, 6 + (k + 1) % 6, (k + 1) % 6))
    return Mesh(bottom + top, polys)


def _octagon_cube() -> Mesh:
    cube = Mesh.cube(200.0)
    corners = [cube.points[3], cube.points[7], cube.points[6], cube.points[2]]
    octa = []
    for k in range(4):
        a, b = corners[k], corners[(k + 1) % 4]
        octa.append(a + (b - a) * 0.25)
        octa.append(a + (b - a) * 0.75)
    pts = np.vstack([cube.points, np.array(octa)])
    polys = [cube.polygons[i] for i in range(6) if cube.polygons[i] != (3, 7, 6, 2)]
    polys.append(tuple(range(8, 16)))
    return Mesh(pts, polys)


def test_registry_lists_new_tools():
    ids = tool_ids()
    for tool in NEW_TOOLS:
        assert tool in ids, tool
        spec = get_tool(tool)
        assert spec.menu == "Mesh"
        assert spec.interactive is False


def test_set_flow_flat_grid_stays():
    grid = _flat_grid(5, 5)
    sel = Selection("edges", edges={edge_key(10 + i, 11 + i) for i in range(4)})
    res = run_tool("set_flow", grid, sel, {})
    assert res.ok
    assert np.allclose(res.mesh.points, grid.points)


def test_set_flow_curved_grid_lands_on_surface():
    mesh = _cylinder()
    for i in (1, 2, 3):
        mesh.points[10 + i] *= 0.9
    sel = Selection("edges", edges={edge_key(10 + i, 11 + i) for i in range(4)})
    res = run_tool("set_flow", mesh, sel, {})
    assert res.ok
    assert not np.allclose(res.mesh.points[11], mesh.points[11])
    for i in (1, 2, 3):
        x, y, z = res.mesh.points[10 + i]
        r = math.hypot(x, z)
        assert abs(math.hypot(r, y) - 100.0) < 1.0, (i, math.hypot(r, y))
    assert np.allclose(res.mesh.points[[10, 14]], mesh.points[[10, 14]])


def test_set_flow_strength_zero_keeps_points():
    mesh = _cylinder()
    mesh.points[12] *= 0.9
    sel = Selection("edges", edges={edge_key(10 + i, 11 + i) for i in range(4)})
    res = run_tool("set_flow", mesh, sel, {"strength": 0.0})
    assert np.allclose(res.mesh.points, mesh.points)


def test_set_flow_boundary_loop_stays():
    mesh = _cylinder()
    sel = Selection("edges", edges={edge_key(i, i + 1) for i in range(4)})
    res = run_tool("set_flow", mesh, sel, {})
    assert res.ok
    assert np.allclose(res.mesh.points, mesh.points)


def test_set_flow_needs_edges():
    cube = Mesh.cube(200.0)
    assert not run_tool("set_flow", cube, Selection("edges"), {}).ok
    assert not run_tool("set_flow", cube, Selection("polygons", polygons={0}), {}).ok


def test_set_point_value_set_moves_polygon():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("set_point_value", cube, Selection("polygons", polygons={top}),
                   {"y": "Set", "y_value": 50.0})
    ids = list(cube.polygons[top])
    rest = [i for i in range(8) if i not in ids]
    assert np.allclose(res.mesh.points[ids, 1], 50.0)
    assert np.allclose(res.mesh.points[rest], cube.points[rest])
    assert len(res.mesh.polygons) == 6


def test_set_point_value_center_uses_bounds_middle():
    cube = Mesh.cube(200.0)
    res = run_tool("set_point_value", cube, Selection("points", points={0, 1}), {"x": "Center"})
    assert np.allclose(res.mesh.points[[0, 1], 0], 0.0)
    assert np.allclose(res.mesh.points[[0, 1], 1:], cube.points[[0, 1], 1:])
    assert np.allclose(res.mesh.points[2:], cube.points[2:])


def test_set_point_value_quantize_rounds_to_step():
    mesh = Mesh([(12.3, 0.0, 0.0), (17.6, 0.0, 0.0), (-4.9, 0.0, 0.0)], [])
    res = run_tool("set_point_value", mesh, Selection("points", points={0, 1, 2}),
                   {"x": "Quantize", "x_value": 10.0})
    assert np.allclose(res.mesh.points[:, 0], [10.0, 20.0, 0.0])


def test_set_point_value_leave_keeps_points():
    cube = Mesh.cube(200.0)
    res = run_tool("set_point_value", cube, Selection("points", points={0, 1, 2}),
                   {"x": "Leave", "y": "Leave", "z": "Leave", "x_value": 9.0})
    assert np.allclose(res.mesh.points, cube.points)


def test_set_point_value_crumple_axial_seeded():
    cube = Mesh.cube(200.0)
    sel = Selection("points", points={0, 1, 2, 3})
    params = {"x": "Crumple (Axial)", "x_value": 5.0, "seed": 7}
    a = run_tool("set_point_value", cube, sel, params).mesh
    b = run_tool("set_point_value", cube, sel, dict(params)).mesh
    c = run_tool("set_point_value", cube, sel, {**params, "seed": 8}).mesh
    assert np.array_equal(a.points, b.points)
    assert not np.array_equal(a.points, c.points)
    assert np.allclose(a.points[4:], cube.points[4:])
    assert np.allclose(a.points[:4, 1:], cube.points[:4, 1:])
    assert np.all(np.abs(a.points[:4, 0] - cube.points[:4, 0]) <= 5.0 + 1e-9)
    assert not np.allclose(a.points[:4, 0], cube.points[:4, 0])


def test_set_point_value_crumple_radial_centre_fixed():
    mesh = Mesh([(0.0, 0.0, 0.0), (0.0, 10.0, 0.0), (0.0, -10.0, 0.0)], [])
    res = run_tool("set_point_value", mesh, Selection("points", points={0, 1, 2}),
                   {"x": "Crumple (Radial)", "x_value": 5.0, "seed": 3})
    xs = res.mesh.points[:, 0]
    assert xs[0] == 0.0
    assert abs(xs[1]) <= 5.0 and abs(xs[2]) <= 5.0


def test_set_point_value_needs_selection():
    cube = Mesh.cube(200.0)
    res = run_tool("set_point_value", cube, Selection("points"), {"x": "Set", "x_value": 1.0})
    assert not res.ok
    assert np.allclose(res.mesh.points, cube.points)


def test_array_and_clone_need_selection():
    cube = Mesh.cube(200.0)
    for tool in ("array", "clone"):
        res = run_tool(tool, cube, Selection("polygons"), {})
        assert not res.ok, tool
        assert len(res.mesh.polygons) == 6, tool
        assert np.allclose(res.mesh.points, cube.points), tool


def test_array_default_adds_nothing():
    cube = Mesh.cube(200.0)
    res = run_tool("array", cube, Selection("polygons", polygons=set(range(6))), {})
    assert res.ok
    assert len(res.mesh.polygons) == 6
    assert len(res.mesh.points) == 8


def test_array_grid_counts_and_consistency():
    cube = Mesh.cube(200.0)
    res = run_tool("array", cube, Selection("polygons", polygons=set(range(6))),
                   {"clones_x": 2, "clones_y": 3, "clones_z": 1})
    m = res.mesh
    assert len(m.polygons) == 36
    assert len(m.points) == 48
    assert _consistent(m)
    assert len(cube.polygons) == 6


def test_array_offset_places_copies():
    cube = Mesh.cube(200.0)
    res = run_tool("array", cube, Selection("polygons", polygons=set(range(6))),
                   {"clones_x": 2, "offset": (250.0, 0.0, 0.0)})
    m = res.mesh
    assert np.allclose(m.points[8:] - m.points[:8], np.array([250.0, 0.0, 0.0]))


def test_array_copies_keep_normals():
    cube = Mesh.cube(200.0)
    res = run_tool("array", cube, Selection("polygons", polygons=set(range(6))),
                   {"clones_x": 2, "clones_y": 2, "clones_z": 1})
    normals = res.mesh.polygon_normals()
    for t in range(3):
        assert np.allclose(normals[6 + 6 * t: 12 + 6 * t], normals[:6])


def test_array_points_copy_loose_edges():
    mesh = Mesh([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)], [], [(0, 1)])
    res = run_tool("array", mesh, Selection("points", points={0, 1}), {"clones_x": 2})
    assert len(res.mesh.points) == 4
    assert res.mesh.loose_edges == [(0, 1), (2, 3)]


def test_clone_copies_along_axis():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("clone", cube, Selection("polygons", polygons={top}),
                   {"clones": 2, "offset": 100.0, "axis": "Y"})
    m = res.mesh
    assert len(m.polygons) == 8
    assert len(m.points) == 16
    assert np.allclose(m.points[list(m.polygons[6])][:, 1], 200.0)
    assert np.allclose(m.points[list(m.polygons[7])][:, 1], 300.0)
    assert np.allclose(m.polygon_normals()[6:], m.polygon_normals()[top])


def test_clone_rotation_accumulates():
    mesh = Mesh([(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)], [])
    res = run_tool("clone", mesh, Selection("points", points={0, 1}),
                   {"clones": 2, "offset": 0.0, "rotation": 90.0, "axis": "Z"})
    expected = [(50.0, -50.0, 0.0), (50.0, 50.0, 0.0), (100.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
    assert np.allclose(res.mesh.points[2:], expected)


def test_clone_scale_accumulates():
    mesh = Mesh([(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)], [])
    res = run_tool("clone", mesh, Selection("points", points={0, 1}),
                   {"clones": 2, "offset": 0.0, "scale": 50.0, "axis": "X"})
    assert np.allclose(res.mesh.points[2:, 0], [25.0, 75.0, 37.5, 62.5])


def test_clone_offset_steps_along_axis():
    mesh = Mesh([(0.0, 0.0, 0.0)], [])
    res = run_tool("clone", mesh, Selection("points", points={0}),
                   {"clones": 3, "offset": 10.0, "axis": "Y"})
    assert np.allclose(res.mesh.points[1:, 1], [10.0, 20.0, 30.0])


def test_clone_zero_scale_stays_nondegenerate():
    cube = Mesh.cube(200.0)
    res = run_tool("clone", cube, Selection("polygons", polygons={0}),
                   {"clones": 2, "offset": 0.0, "scale": 0.0, "axis": "Y"})
    assert res.ok
    assert all(face_area(res.mesh, k) > 1e-6 for k in range(len(res.mesh.polygons)))
    assert _consistent(res.mesh)


def test_remove_ngons_hexagon_to_quads():
    hexa = _hexagon()
    area = face_area(hexa, 0)
    res = run_tool("remove_ngons", hexa, Selection("model"), {})
    m = res.mesh
    assert res.ok
    assert len(m.polygons) == 2
    assert all(len(poly) == 4 for poly in m.polygons)
    assert np.isclose(sum(face_area(m, k) for k in range(len(m.polygons))), area)
    old_normal = hexa.polygon_normals()[0]
    assert all(float(n @ old_normal) > 0.99 for n in m.polygon_normals())
    assert len(hexa.polygons) == 1


def test_remove_ngons_prism_closed_and_outward():
    prism = _hex_prism()
    res = run_tool("remove_ngons", prism, Selection("model"), {})
    m = res.mesh
    assert len(m.polygons) == 10
    assert all(len(poly) <= 4 for poly in m.polygons)
    assert _manifold(m) and _consistent(m)
    center = np.array([0.0, 25.0, 0.0])
    normals = m.polygon_normals()
    for k, poly in enumerate(m.polygons):
        centroid = m.points[list(poly)].mean(axis=0)
        assert float((centroid - center) @ normals[k]) > 0.0


def test_remove_ngons_octagon_keeps_others():
    cube = _octagon_cube()
    area = sum(face_area(cube, k) for k in range(len(cube.polygons)))
    res = run_tool("remove_ngons", cube, Selection("model"), {})
    m = res.mesh
    assert res.ok
    assert all(len(poly) <= 4 for poly in m.polygons)
    assert m.polygons[:5] == cube.polygons[:5]
    assert np.isclose(sum(face_area(m, k) for k in range(len(m.polygons))), area)
    assert _consistent(m)
    octa_normal = cube.polygon_normals()[5]
    assert all(float(n @ octa_normal) > 0.0 for n in m.polygon_normals()[5:])


def test_remove_ngons_rejects_repeated_index():
    mesh = Mesh([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)],
                [(0, 1, 0, 2, 3)])
    res = run_tool("remove_ngons", mesh, Selection("model"), {})
    assert not res.ok
    assert res.message == "Remove N-gons: an N-gon repeats a vertex"
    assert res.mesh.polygons == mesh.polygons


def test_retriangulate_reorders_to_lowest_index():
    mesh = Mesh(_hexagon().points, [(3, 4, 5, 0, 1, 2)])
    res = run_tool("retriangulate_ngons", mesh, Selection("model"), {})
    assert res.ok
    assert res.mesh.polygons == [(0, 1, 2, 3, 4, 5)]
    assert res.message == "Retriangulate N-gons: 1 N-gons checked, 1 re-indexed"
    assert np.allclose(res.mesh.points, mesh.points)


def test_retriangulate_leaves_cube_unchanged():
    cube = Mesh.cube(200.0)
    res = run_tool("retriangulate_ngons", cube, Selection("model"), {})
    assert res.ok
    assert res.mesh.polygons == cube.polygons


def test_retriangulate_rejects_repeated_index():
    mesh = Mesh([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)],
                [(0, 1, 0, 2, 3)])
    res = run_tool("retriangulate_ngons", mesh, Selection("model"), {})
    assert not res.ok
    assert res.mesh.polygons == mesh.polygons


def test_edge_to_spline_chain():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_to_spline", cube, Selection("edges", edges={(0, 1), (1, 2)}), {})
    m = res.mesh
    assert res.ok
    assert res.message == "Edge to Spline: 2 segments"
    assert len(m.points) == 11
    assert m.loose_edges == [(8, 9), (9, 10)]
    assert len(m.polygons) == 6
    assert np.allclose(m.points[8:], cube.points[[0, 1, 2]])


def test_edge_to_spline_needs_edges():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_to_spline", cube, Selection("edges"), {})
    assert not res.ok
    assert len(res.mesh.points) == 8


def test_edge_to_spline_ignores_missing_edges():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_to_spline", cube, Selection("edges", edges={(0, 6)}), {})
    assert not res.ok
    assert len(res.mesh.points) == 8
    assert res.mesh.loose_edges == []
    mixed = run_tool("edge_to_spline", cube, Selection("edges", edges={(0, 1), (0, 6)}), {})
    assert mixed.ok
    assert mixed.message == "Edge to Spline: 1 segments"
    assert mixed.mesh.loose_edges == [(8, 9)]


def test_inputs_untouched_by_every_tool():
    cube = Mesh.cube(200.0)
    cases = [
        ("array", Selection("polygons", polygons={0}), {"clones_x": 2}),
        ("clone", Selection("polygons", polygons={0}), {"clones": 2, "rotation": 45.0}),
        ("set_point_value", Selection("points", points={0, 1}), {"x": "Set", "x_value": 3.0}),
        ("set_flow", Selection("edges", edges={(0, 1)}), {"strength": 50.0}),
        ("remove_ngons", Selection("model"), {}),
        ("retriangulate_ngons", Selection("model"), {}),
        ("edge_to_spline", Selection("edges", edges={(0, 1)}), {}),
    ]
    for tool, sel, params in cases:
        snap = _snapshot(cube)
        run_tool(tool, cube, sel, params)
        assert _unchanged(cube, snap), tool


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
