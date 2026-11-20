from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.modeling import Selection, get_tool, run_tool, tool_ids
from quartz_studio.modeling.meshkit import edge_faces, edge_key
from quartz_studio.modeling.primitives import cylinder, torus
from quartz_studio.scene import Mesh

SELECT_IDS = (
    "select_all", "deselect_all", "invert_selection", "select_connected", "grow_selection",
    "shrink_selection", "loop_selection", "ring_selection", "outline_selection", "fill_selection",
    "path_selection", "convert_selection",
)
EMPTY_FAILS = (
    "select_connected", "grow_selection", "shrink_selection", "loop_selection", "ring_selection",
    "outline_selection", "fill_selection", "path_selection", "convert_selection",
)
SAMPLE = {"points": {7, 12}, "edges": {(7, 12)}, "polygons": {5}}


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


def _same_mesh(a: Mesh, b: Mesh) -> bool:
    return (np.array_equal(a.points, b.points)
            and list(a.polygons) == list(b.polygons)
            and list(a.loose_edges) == list(b.loose_edges))


def _grid(n: int, size: float = 100.0) -> Mesh:
    points = [(i * size, 0.0, j * size) for i in range(n + 1) for j in range(n + 1)]
    polygons = []
    for i in range(n):
        for j in range(n):
            a = i * (n + 1) + j
            b = (i + 1) * (n + 1) + j
            c = b + 1
            d = a + 1
            polygons.append((a, b, c, d))
    return Mesh(points, polygons)


def _top(mesh: Mesh) -> int:
    return int(np.argmax(mesh.polygon_normals()[:, 1]))


def _bottom(mesh: Mesh) -> int:
    return int(np.argmin(mesh.polygon_normals()[:, 1]))


def _poly_edges(mesh: Mesh, f: int) -> set:
    poly = mesh.polygons[f]
    return {edge_key(a, b) for a, b in zip(poly, poly[1:] + poly[:1])}


def _valid_selection(mesh: Mesh, sel: Selection) -> bool:
    if sel.mode == "points":
        return all(0 <= int(i) < len(mesh.points) for i in sel.points)
    if sel.mode == "edges":
        edges = set(mesh.edges)
        return all(e in edges for e in sel.edges)
    return all(0 <= int(f) < len(mesh.polygons) for f in sel.polygons)


def _tetra() -> Mesh:
    points = [(0.0, 0.0, 0.0), (200.0, 0.0, 0.0), (0.0, 200.0, 0.0), (0.0, 0.0, 200.0)]
    return Mesh(points, [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)])


def _pentagon() -> Mesh:
    points = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (150.0, 0.0, 80.0), (50.0, 0.0, 130.0), (-50.0, 0.0, 80.0)]
    return Mesh(points, [(0, 1, 2, 3, 4)])


def test_select_tools_are_registered():
    assert set(SELECT_IDS) <= set(tool_ids())
    for tool_id in SELECT_IDS:
        spec = get_tool(tool_id)
        assert spec.interactive is False
        assert spec.menu == "Select"
        assert spec.section == "SELECTION"
    assert get_tool("select_all").shortcut == "Ctrl+A"
    assert get_tool("invert_selection").shortcut == "U~I"
    assert get_tool("convert_selection").param("to").choices == ("Points", "Edges", "Polygons")


def test_select_all_cube_points():
    cube = Mesh.cube(200.0)
    assert _manifold(cube) and _consistent(cube)
    res = run_tool("select_all", cube, Selection("points", points={0}), {})
    assert res.ok
    assert res.selection.mode == "points"
    assert res.selection.points == set(range(8))
    assert _same_mesh(cube, res.mesh)


def test_select_all_grid_polygons_and_edges():
    grid = _grid(4)
    res = run_tool("select_all", grid, Selection("polygons", polygons={0}), {})
    assert res.selection.polygons == set(range(16))
    res = run_tool("select_all", grid, Selection("edges", edges={(0, 1)}), {})
    assert len(res.selection.edges) == 40
    assert res.selection.edges == set(grid.edges)


def test_select_all_is_idempotent():
    cube = Mesh.cube(200.0)
    first = run_tool("select_all", cube, Selection("polygons", polygons={0}), {})
    second = run_tool("select_all", first.mesh, first.selection, {})
    assert first.selection.polygons == set(range(6))
    assert second.selection.polygons == first.selection.polygons


def test_deselect_all_clears_edges():
    cube = Mesh.cube(200.0)
    res = run_tool("deselect_all", cube, Selection("edges", edges={(0, 1)}), {})
    assert res.ok
    assert res.selection.mode == "edges"
    assert res.selection.edges == set()
    assert _same_mesh(cube, res.mesh)


def test_deselect_all_clears_grid_polygons():
    grid = _grid(4)
    res = run_tool("deselect_all", grid, Selection("polygons", polygons={0, 5}), {})
    assert res.ok
    assert res.selection.polygons == set()
    assert _same_mesh(grid, res.mesh)


def test_invert_cube_points():
    cube = Mesh.cube(200.0)
    res = run_tool("invert_selection", cube, Selection("points", points={0, 1}), {})
    assert res.selection.points == set(range(2, 8))


def test_invert_twice_restores_grid_polygons():
    grid = _grid(4)
    sel = Selection("polygons", polygons={0, 5, 15})
    once = run_tool("invert_selection", grid, sel, {})
    assert once.selection.polygons == set(range(16)) - {0, 5, 15}
    twice = run_tool("invert_selection", grid, once.selection, {})
    assert twice.selection.polygons == {0, 5, 15}


def test_invert_grid_edges_complement():
    grid = _grid(4)
    res = run_tool("invert_selection", grid, Selection("edges", edges={(0, 1)}), {})
    assert len(res.selection.edges) == 39
    assert edge_key(0, 1) not in res.selection.edges


def test_select_connected_cube_points():
    cube = Mesh.cube(200.0)
    res = run_tool("select_connected", cube, Selection("points", points={0}), {})
    assert res.ok
    assert res.selection.points == set(range(8))


def test_select_connected_keeps_islands_apart():
    grid = _grid(2)
    extra = np.array([(1000.0, 0.0, 0.0), (1100.0, 0.0, 0.0), (1100.0, 0.0, 100.0), (1000.0, 0.0, 100.0)])
    mesh = Mesh(np.vstack([grid.points, extra]), list(grid.polygons) + [(9, 10, 11, 12)])
    res = run_tool("select_connected", mesh, Selection("polygons", polygons={0}), {})
    assert res.selection.polygons == {0, 1, 2, 3}


def test_select_connected_grid_edges():
    grid = _grid(4)
    res = run_tool("select_connected", grid, Selection("edges", edges={(7, 12)}), {})
    assert res.selection.edges == set(grid.edges)


def test_grow_cube_top_then_shrink_back():
    cube = Mesh.cube(200.0)
    top = _top(cube)
    bottom = _bottom(cube)
    grown = run_tool("grow_selection", cube, Selection("polygons", polygons={top}), {})
    assert grown.selection.polygons == set(range(6)) - {bottom}
    shrunk = run_tool("shrink_selection", grown.mesh, grown.selection, {})
    assert shrunk.selection.polygons == {top}


def test_grow_grid_center_face():
    grid = _grid(4)
    res = run_tool("grow_selection", grid, Selection("polygons", polygons={5}), {})
    assert res.selection.polygons == {0, 1, 2, 4, 5, 6, 8, 9, 10}


def test_shrink_grid_block_leaves_center():
    grid = _grid(4)
    block = {0, 1, 2, 4, 5, 6, 8, 9, 10}
    res = run_tool("shrink_selection", grid, Selection("polygons", polygons=block), {})
    assert res.selection.polygons == {5}


def test_grow_then_shrink_grid_interior_block_round_trip():
    grid = _grid(4)
    start = {5, 6, 9, 10}
    grown = run_tool("grow_selection", grid, Selection("polygons", polygons=start), {})
    assert grown.selection.polygons == set(range(16))
    back = run_tool("shrink_selection", grown.mesh, grown.selection, {})
    assert back.selection.polygons == start


def test_grow_points_grid_plus_shape():
    grid = _grid(4)
    res = run_tool("grow_selection", grid, Selection("points", points={12}), {})
    assert res.selection.points == {7, 11, 12, 13, 17}


def test_grow_then_shrink_points_round_trip():
    grid = _grid(4)
    grown = run_tool("grow_selection", grid, Selection("points", points={12}), {})
    back = run_tool("shrink_selection", grid, grown.selection, {})
    assert back.selection.points == {12}


def test_grow_edges_touching_selected_points():
    grid = _grid(4)
    res = run_tool("grow_selection", grid, Selection("edges", edges={(7, 12)}), {})
    assert len(res.selection.edges) == 7
    assert edge_key(7, 12) in res.selection.edges


def test_grow_then_shrink_edges_round_trip():
    grid = _grid(4)
    grown = run_tool("grow_selection", grid, Selection("edges", edges={(7, 12)}), {})
    back = run_tool("shrink_selection", grid, grown.selection, {})
    assert back.selection.edges == {edge_key(7, 12)}


def test_loop_grid_edge_has_row_length():
    grid = _grid(4)
    res = run_tool("loop_selection", grid, Selection("edges", edges={(7, 12)}), {})
    assert res.ok
    assert res.selection.edges == {(2, 7), (7, 12), (12, 17), (17, 22)}
    assert len(res.selection.edges) == 4


def test_loop_cube_edge_stays_single():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_selection", cube, Selection("edges", edges={(0, 1)}), {})
    assert res.selection.edges == {edge_key(0, 1)}


def test_loop_polygons_pair_follows_shared_edge():
    grid = _grid(4)
    res = run_tool("loop_selection", grid, Selection("polygons", polygons={5, 6}), {})
    assert res.selection.polygons == {4, 5, 6, 7}


def test_loop_polygons_single_face_is_one_belt_of_four():
    grid = _grid(4)
    res = run_tool("loop_selection", grid, Selection("polygons", polygons={5}), {})
    assert res.ok
    assert res.selection.polygons == {4, 5, 6, 7}


def test_loop_cube_face_is_belt_of_four():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_selection", cube, Selection("polygons", polygons={0}), {})
    assert res.ok
    assert res.selection.polygons == {0, 1, 2, 3}
    assert len(res.selection.polygons) == 4


def test_loop_torus_face_is_closed_belt():
    tor = torus(100.0, 8, 50.0, 6)
    res = run_tool("loop_selection", tor, Selection("polygons", polygons={0}), {})
    assert res.ok
    assert res.selection.polygons == {0, 1, 2, 3, 4, 5}


def test_ring_cube_face_is_one_belt_of_four():
    cube = Mesh.cube(200.0)
    res = run_tool("ring_selection", cube, Selection("polygons", polygons={0}), {})
    assert res.ok
    assert res.selection.polygons == {0, 1, 4, 5}
    assert len(res.selection.polygons) == 4


def test_ring_grid_face_selects_column():
    grid = _grid(4)
    res = run_tool("ring_selection", grid, Selection("polygons", polygons={5}), {})
    assert res.ok
    assert res.selection.polygons == {1, 5, 9, 13}


def test_ring_grid_adjacent_pair_goes_perpendicular_from_each_face():
    grid = _grid(4)
    res = run_tool("ring_selection", grid, Selection("polygons", polygons={5, 6}), {})
    assert res.ok
    assert res.selection.polygons == {1, 2, 5, 6, 9, 10, 13, 14}


def test_loop_single_point_selects_nothing():
    grid = _grid(4)
    res = run_tool("loop_selection", grid, Selection("points", points={7}), {})
    assert not res.ok
    assert res.selection.points == {7}


def test_loop_grid_column_edge_border_to_border():
    grid = _grid(4)
    res = run_tool("loop_selection", grid, Selection("edges", edges={(8, 9)}), {})
    assert res.ok
    assert res.selection.edges == {(5, 6), (6, 7), (7, 8), (8, 9)}


def _every_point_degree_two(edges) -> bool:
    deg: dict[int, int] = {}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    return bool(edges) and all(v == 2 for v in deg.values())


def test_loop_torus_edge_is_closed_ring():
    tor = torus(100.0, 8, 50.0, 6)
    edge = edge_key(*tor.polygons[0][:2])
    res = run_tool("loop_selection", tor, Selection("edges", edges={edge}), {})
    assert res.ok
    assert len(res.selection.edges) == 8
    assert _every_point_degree_two(res.selection.edges)


def test_ring_torus_edge_is_closed_ring():
    tor = torus(100.0, 8, 50.0, 6)
    edge = edge_key(*tor.polygons[0][1:3])
    res = run_tool("ring_selection", tor, Selection("edges", edges={edge}), {})
    assert res.ok
    assert res.selection.edges == {(0, 1), (6, 7), (12, 13), (18, 19), (24, 25), (30, 31), (36, 37), (42, 43)}


def test_loop_and_ring_on_non_quads_fail_instead_of_empty():
    for mesh in (_tetra(), _pentagon()):
        for tool_id in ("loop_selection", "ring_selection"):
            res = run_tool(tool_id, mesh, Selection("polygons", polygons={0}), {})
            assert not res.ok, tool_id
            assert res.selection.polygons == {0}, tool_id
            assert _same_mesh(mesh, res.mesh)
    res = run_tool("loop_selection", _tetra(), Selection("polygons", polygons={0, 1}), {})
    assert not res.ok
    assert res.selection.polygons == {0, 1}


def test_ring_torus_face_is_closed_other_belt():
    tor = torus(100.0, 8, 50.0, 6)
    res = run_tool("ring_selection", tor, Selection("polygons", polygons={0}), {})
    assert res.ok
    assert res.selection.polygons == {0, 6, 12, 18, 24, 30, 36, 42}


def test_non_quad_seed_keeps_whole_input_selection():
    cyl = cylinder()
    cap = next(i for i, p in enumerate(cyl.polygons) if len(p) != 4)
    side = next(i for i, p in enumerate(cyl.polygons) if len(p) == 4)
    for tool_id, size in (("loop_selection", 5), ("ring_selection", 17)):
        res = run_tool(tool_id, cyl, Selection("polygons", polygons={cap, side}), {})
        assert res.ok, tool_id
        assert {cap, side} <= res.selection.polygons, tool_id
        assert len(res.selection.polygons) == size, tool_id
        assert _same_mesh(cyl, res.mesh)


def test_non_quad_only_selection_fails_and_keeps_cap():
    cyl = cylinder()
    cap = next(i for i, p in enumerate(cyl.polygons) if len(p) != 4)
    for tool_id in ("loop_selection", "ring_selection"):
        res = run_tool(tool_id, cyl, Selection("polygons", polygons={cap}), {})
        assert not res.ok, tool_id
        assert res.selection.polygons == {cap}, tool_id


def test_loop_points_row_through_neighbours():
    grid = _grid(4)
    res = run_tool("loop_selection", grid, Selection("points", points={7, 12}), {})
    assert res.selection.points == {2, 7, 12, 17, 22}


def test_loop_points_without_neighbours_fails():
    grid = _grid(4)
    res = run_tool("loop_selection", grid, Selection("points", points={0, 24}), {})
    assert not res.ok
    assert res.selection.points == {0, 24}


def test_ring_grid_edge_column():
    grid = _grid(4)
    res = run_tool("ring_selection", grid, Selection("edges", edges={(7, 12)}), {})
    assert res.selection.edges == {(5, 10), (6, 11), (7, 12), (8, 13), (9, 14)}


def test_ring_cube_edge_is_belt_of_four():
    cube = Mesh.cube(200.0)
    res = run_tool("ring_selection", cube, Selection("edges", edges={(0, 1)}), {})
    assert res.selection.edges == {(0, 1), (2, 3), (6, 7), (4, 5)}


def test_outline_top_face_cube_edges():
    cube = Mesh.cube(200.0)
    top = _top(cube)
    res = run_tool("outline_selection", cube, Selection("polygons", polygons={top}), {})
    assert res.ok
    assert res.selection.mode == "edges"
    assert res.selection.edges == _poly_edges(cube, top)


def test_outline_grid_block_perimeter():
    grid = _grid(4)
    res = run_tool("outline_selection", grid, Selection("polygons", polygons={5, 6, 9, 10}), {})
    assert res.selection.mode == "edges"
    assert len(res.selection.edges) == 8


def test_outline_only_in_polygons_mode():
    cube = Mesh.cube(200.0)
    res = run_tool("outline_selection", cube, Selection("edges", edges={(0, 1)}), {})
    assert not res.ok


def test_fill_cube_top_border_smaller_and_larger():
    cube = Mesh.cube(200.0)
    top = _top(cube)
    border = _poly_edges(cube, top)
    smaller = run_tool("fill_selection", cube, Selection("edges", edges=border), {"side": "Smaller"})
    assert smaller.ok
    assert smaller.selection.mode == "polygons"
    assert smaller.selection.polygons == {top}
    larger = run_tool("fill_selection", cube, Selection("edges", edges=border), {"side": "Larger"})
    assert larger.selection.polygons == set(range(6)) - {top}


def test_fill_grid_block_inside_and_outside():
    grid = _grid(4)
    block = {5, 6, 9, 10}
    outline = run_tool("outline_selection", grid, Selection("polygons", polygons=block), {}).selection
    inside = run_tool("fill_selection", grid, Selection("edges", edges=outline.edges), {"side": "Smaller"})
    assert inside.selection.polygons == block
    outside = run_tool("fill_selection", grid, Selection("edges", edges=outline.edges), {"side": "Larger"})
    assert outside.selection.polygons == set(range(16)) - block


def test_fill_open_edge_chain_fails():
    grid = _grid(4)
    res = run_tool("fill_selection", grid, Selection("edges", edges={(0, 1)}), {})
    assert not res.ok
    assert res.selection.edges == {edge_key(0, 1)}


def test_path_grid_corners_six_edges():
    grid = _grid(3)
    res = run_tool("path_selection", grid, Selection("points", points={0, 15}), {})
    assert res.ok
    assert res.selection.mode == "points"
    assert len(res.selection.points) == 7
    assert {0, 15} <= res.selection.points


def test_path_grid_corners_eight_edges():
    grid = _grid(4)
    res = run_tool("path_selection", grid, Selection("points", points={0, 24}), {})
    assert len(res.selection.points) == 9


def test_path_cube_edge_in_edges_mode():
    cube = Mesh.cube(200.0)
    res = run_tool("path_selection", cube, Selection("edges", edges={(0, 1)}), {})
    assert res.selection.mode == "edges"
    assert res.selection.edges == {edge_key(0, 1)}


def test_path_requires_exactly_two_points():
    cube = Mesh.cube(200.0)
    res = run_tool("path_selection", cube, Selection("points", points={0, 1, 2}), {})
    assert not res.ok


def test_convert_points_to_edges():
    cube = Mesh.cube(200.0)
    res = run_tool("convert_selection", cube, Selection("points", points={0, 1}), {"to": "Edges"})
    assert res.selection.mode == "edges"
    assert res.selection.edges == {edge_key(0, 1)}


def test_convert_point_to_polygons_tolerant_and_strict():
    cube = Mesh.cube(200.0)
    tolerant = run_tool("convert_selection", cube, Selection("points", points={0}),
                        {"to": "Polygons", "tolerant": True})
    assert tolerant.selection.mode == "polygons"
    assert tolerant.selection.polygons == {0, 2, 5}
    strict = run_tool("convert_selection", cube, Selection("points", points={0}),
                      {"to": "Polygons", "tolerant": False})
    assert strict.ok
    assert strict.selection.polygons == set()


def test_convert_polygon_top_to_points_and_edges():
    cube = Mesh.cube(200.0)
    top = _top(cube)
    pts = run_tool("convert_selection", cube, Selection("polygons", polygons={top}), {"to": "Points"})
    assert pts.selection.points == set(cube.polygons[top])
    edges = run_tool("convert_selection", cube, Selection("polygons", polygons={top}), {"to": "Edges"})
    assert edges.selection.edges == _poly_edges(cube, top)


def test_convert_edges_to_polygons_tolerant_and_strict():
    grid = _grid(4)
    edges = _poly_edges(grid, 5)
    tolerant = run_tool("convert_selection", grid, Selection("edges", edges=edges),
                        {"to": "Polygons", "tolerant": True})
    assert tolerant.selection.polygons == {1, 4, 5, 6, 9}
    strict = run_tool("convert_selection", grid, Selection("edges", edges=edges),
                      {"to": "Polygons", "tolerant": False})
    assert strict.selection.polygons == {5}


def test_convert_single_edge_to_polygons():
    grid = _grid(4)
    edge = {edge_key(7, 12)}
    tolerant = run_tool("convert_selection", grid, Selection("edges", edges=edge),
                        {"to": "Polygons", "tolerant": True})
    assert tolerant.selection.polygons == {5, 6}
    strict = run_tool("convert_selection", grid, Selection("edges", edges=edge),
                      {"to": "Polygons", "tolerant": False})
    assert strict.selection.polygons == set()


def test_every_command_keeps_mesh_unchanged():
    grid = _grid(4)
    before_points = grid.points.copy()
    before_polys = list(grid.polygons)
    for tool_id in SELECT_IDS:
        spec = get_tool(tool_id)
        for mode in ("points", "edges", "polygons"):
            if not spec.supports(mode):
                continue
            sel = Selection(mode, **{mode: SAMPLE[mode]})
            res = run_tool(tool_id, grid, sel, {})
            assert _same_mesh(grid, res.mesh), (tool_id, mode)
            assert _valid_selection(grid, res.selection), (tool_id, mode)
            assert np.array_equal(grid.points, before_points)
            assert list(grid.polygons) == before_polys


def test_empty_selection_reports_failure():
    cube = Mesh.cube(200.0)
    for tool_id in EMPTY_FAILS:
        spec = get_tool(tool_id)
        for mode in spec.modes:
            res = run_tool(tool_id, cube, Selection(mode), {})
            assert not res.ok, (tool_id, mode)
            assert res.selection.is_empty(), (tool_id, mode)
            assert _same_mesh(cube, res.mesh)


def test_wrong_mode_reports():
    cube = Mesh.cube(200.0)
    res = run_tool("fill_selection", cube, Selection("polygons", polygons={0}), {})
    assert not res.ok


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
