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
from quartz_studio.scene import Mesh


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


def _open_edges(mesh: Mesh) -> int:
    return sum(1 for v in edge_faces(mesh).values() if len(v) == 1)


def _new_points(res, before: int) -> np.ndarray:
    return res.mesh.points[before:]


def _grid_plane(n: int, size: float = 100.0) -> Mesh:
    pts = [(i * size, 0.0, j * size) for j in range(n + 1) for i in range(n + 1)]
    polys = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            polys.append((a, a + n + 1, a + n + 2, a + 1))
    return Mesh(pts, polys)


def _two_cubes() -> Mesh:
    a = Mesh.cube(100.0)
    b = Mesh.cube(100.0)
    pts = np.vstack([a.points + (0, 0, 300.0), b.points])
    polys = list(a.polygons) + [tuple(i + 8 for i in p) for p in b.polygons]
    return Mesh(pts, polys)


def test_registry_lists_cut_tools():
    ids = tool_ids()
    for tool in ("loop_path_cut", "line_cut", "plane_cut", "edge_cut", "extrude"):
        assert tool in ids


def test_loop_cut_defaults():
    spec = get_tool("loop_path_cut")
    d = spec.defaults()
    assert spec.name == "Loop/Path Cut"
    assert d["mode"] == "Loop" and d["offset"] == 50.0 and d["cuts"] == 1
    assert d["evenly_distribute"] is True and d["symmetric"] is False and d["quantize"] is False
    assert d["quantize_subdivision"] == 10 and d["restrict_to_selection"] is False
    assert d["edge"] is None and d["path"] is None
    assert spec.interactive and spec.drag_param == "offset" and spec.drag_kind == "percent"
    assert spec.shortcut == "K~L" and spec.section == "CUT"
    assert spec.extra["pick"] == "edge"


def test_loop_cut_around_cube_closes_ring():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("edges"), {"edge": (0, 1)})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 12 and len(m.polygons) == 10
    assert _manifold(m) and _consistent(m)
    assert np.allclose(_new_points(res, 8)[:, 0], 0.0)
    assert len(res.selection.edges) == 4
    assert len(cube.points) == 8 and len(cube.polygons) == 6


def test_loop_cut_offset_follows_picked_direction():
    cube = Mesh.cube(200.0)
    fwd = run_tool("loop_path_cut", cube, Selection("edges"), {"edge": (0, 1), "offset": 25.0})
    assert np.allclose(_new_points(fwd, 8)[:, 0], -50.0)
    back = run_tool("loop_path_cut", cube, Selection("edges"), {"edge": (1, 0), "offset": 25.0})
    assert np.allclose(_new_points(back, 8)[:, 0], 50.0)


def test_loop_cut_uses_selected_edge_by_default():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("edges", edges={(0, 1)}), {})
    assert res.ok and len(res.mesh.polygons) == 10
    assert np.allclose(_new_points(res, 8)[:, 0], 0.0)


def test_loop_cut_multiple_even_cuts():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("edges"), {"edge": (0, 1), "cuts": 3})
    m = res.mesh
    assert len(m.points) == 20 and len(m.polygons) == 18
    assert _manifold(m) and _consistent(m)
    xs = sorted(set(np.round(_new_points(res, 8)[:, 0], 6)))
    assert np.allclose(xs, [-50.0, 0.0, 50.0])
    assert len(res.selection.edges) == 12


def test_loop_cut_spacing_without_even_distribution():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("edges"),
                   {"edge": (0, 1), "cuts": 2, "evenly_distribute": False, "spacing": 20.0})
    xs = sorted(set(np.round(_new_points(res, 8)[:, 0], 6)))
    assert np.allclose(xs, [-20.0, 20.0])


def test_loop_cut_symmetric_mirrors_offset():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("edges"),
                   {"edge": (0, 1), "offset": 25.0, "symmetric": True})
    xs = sorted(set(np.round(_new_points(res, 8)[:, 0], 6)))
    assert np.allclose(xs, [-50.0, 50.0])
    assert _manifold(res.mesh) and _consistent(res.mesh)


def test_loop_cut_quantize_snaps_offset():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("edges"),
                   {"edge": (0, 1), "offset": 33.0, "quantize": True, "quantize_subdivision": 10})
    assert np.allclose(_new_points(res, 8)[:, 0], -40.0)


def test_loop_cut_open_ring_stops_at_border():
    plane = _grid_plane(2)
    res = run_tool("loop_path_cut", plane, Selection("edges"), {"edge": (0, 1)})
    m = res.mesh
    assert res.ok and len(m.polygons) == 6 and len(m.points) == 9 + 3
    assert _consistent(m)
    assert np.allclose(_new_points(res, 9)[:, 0], 50.0)


def test_loop_cut_restrict_to_selection():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("polygons", polygons={0, 5}),
                   {"edge": (0, 1), "restrict_to_selection": True})
    m = res.mesh
    assert res.ok and len(m.points) == 11 and len(m.polygons) == 8
    assert _manifold(m) and _consistent(m)
    assert len(res.selection.polygons) == 4


def test_path_cut_follows_given_edges_only():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("edges"),
                   {"mode": "Path", "edge": (0, 1), "path": [(0, 1), (2, 3)]})
    m = res.mesh
    assert res.ok and len(m.points) == 10 and len(m.polygons) == 7
    assert _manifold(m) and _consistent(m)
    assert len(res.selection.edges) == 1


def test_path_cut_turns_corner():
    plane = _grid_plane(2)
    res = run_tool("loop_path_cut", plane, Selection("edges"),
                   {"mode": "Path", "edge": (0, 1), "path": [(0, 1), (1, 4)]})
    assert res.ok and len(res.selection.edges) == 1
    assert _consistent(res.mesh)


def test_loop_cut_without_edge_fails():
    cube = Mesh.cube(200.0)
    res = run_tool("loop_path_cut", cube, Selection("edges"), {})
    assert not res.ok and res.message


def test_edge_cut_defaults():
    spec = get_tool("edge_cut")
    d = spec.defaults()
    assert spec.name == "Edge Cut" and spec.modes == ("edges",)
    assert d == {"offset": 50.0, "scale": 100.0, "subdivision": 1, "create_ngons": False}
    assert spec.drag_param == "offset" and spec.shortcut == "M~F"


def test_edge_cut_connects_opposite_edges():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_cut", cube, Selection("edges", edges={(0, 1), (2, 3)}), {})
    m = res.mesh
    assert res.ok and len(m.points) == 10 and len(m.polygons) == 9
    assert _manifold(m) and _consistent(m)
    assert all(len(p) <= 4 for p in m.polygons)
    assert res.selection.edges == {(8, 9)}


def test_edge_cut_ngons_keep_neighbours():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_cut", cube, Selection("edges", edges={(0, 1), (2, 3)}), {"create_ngons": True})
    m = res.mesh
    assert len(m.polygons) == 7
    assert sorted(len(p) for p in m.polygons).count(5) == 2
    assert _manifold(m) and _consistent(m)


def test_edge_cut_offset_keeps_cuts_parallel():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_cut", cube, Selection("edges", edges={(0, 1), (2, 3)}), {"offset": 25.0})
    assert np.allclose(_new_points(res, 8)[:, 0], -50.0)


def test_edge_cut_subdivision_and_scale():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_cut", cube, Selection("edges", edges={(0, 1), (2, 3)}),
                   {"subdivision": 2, "scale": 50.0})
    m = res.mesh
    assert len(m.points) == 12
    assert _manifold(m) and _consistent(m)
    xs = sorted(set(np.round(_new_points(res, 8)[:, 0], 4)))
    assert np.allclose(xs, [-200.0 / 12.0, 200.0 / 12.0], atol=1e-3)
    assert len(res.selection.edges) == 2


def test_edge_cut_all_edges_builds_grid():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_cut", cube, Selection("edges", edges=set(cube.edges)), {})
    m = res.mesh
    assert len(m.points) == 26 and len(m.polygons) == 24
    assert _manifold(m) and _consistent(m)
    assert all(len(p) == 4 for p in m.polygons)


def test_edge_cut_single_edge_selects_halves():
    cube = Mesh.cube(200.0)
    res = run_tool("edge_cut", cube, Selection("edges", edges={(0, 1)}), {})
    m = res.mesh
    assert res.ok and len(m.points) == 9 and len(m.polygons) == 8
    assert _manifold(m) and _consistent(m)
    assert res.selection.edges == {(0, 8), (1, 8)}


def test_edge_cut_wrong_mode_reports():
    cube = Mesh.cube(200.0)
    assert not run_tool("edge_cut", cube, Selection("polygons", polygons={0}), {}).ok
    assert not run_tool("edge_cut", cube, Selection("edges"), {}).ok


def test_plane_cut_defaults():
    spec = get_tool("plane_cut")
    d = spec.defaults()
    assert spec.name == "Plane Cut" and spec.shortcut == "K~J"
    assert d["mode"] == "Local" and d["plane"] == "XY"
    assert d["plane_position"] == (0.0, 0.0, 0.0) and d["plane_rotation"] == (0.0, 0.0, 0.0)
    assert d["cuts"] == 1 and d["spacing"] == 10.0
    assert d["restrict_to_selection"] is False and d["slice_mode"] == "Cut" and d["create_ngons"] is False


def test_plane_cut_xy_halves_cube():
    cube = Mesh.cube(200.0)
    res = run_tool("plane_cut", cube, Selection("edges"), {})
    m = res.mesh
    assert res.ok and len(m.points) == 12 and len(m.polygons) == 10
    assert _manifold(m) and _consistent(m)
    assert np.allclose(_new_points(res, 8)[:, 2], 0.0)
    assert len(res.selection.edges) == 4


def test_plane_cut_position_and_plane_axis():
    cube = Mesh.cube(200.0)
    res = run_tool("plane_cut", cube, Selection("edges"), {"plane_position": (0, 0, 50)})
    assert np.allclose(_new_points(res, 8)[:, 2], 50.0)
    zx = run_tool("plane_cut", cube, Selection("edges"), {"plane": "ZX", "plane_position": (0, 30, 0)})
    assert np.allclose(_new_points(zx, 8)[:, 1], 30.0)
    yz = run_tool("plane_cut", cube, Selection("edges"), {"plane": "YZ"})
    assert np.allclose(_new_points(yz, 8)[:, 0], 0.0)


def test_plane_cut_multiple_cuts_spacing():
    cube = Mesh.cube(200.0)
    res = run_tool("plane_cut", cube, Selection("edges"), {"cuts": 3, "spacing": 50.0})
    m = res.mesh
    assert len(m.points) == 20 and len(m.polygons) == 18
    assert _manifold(m) and _consistent(m)
    zs = sorted(set(np.round(_new_points(res, 8)[:, 2], 6)))
    assert np.allclose(zs, [-50.0, 0.0, 50.0])


def test_plane_cut_through_vertices_uses_existing_points():
    cube = Mesh.cube(200.0)
    res = run_tool("plane_cut", cube, Selection("edges"), {"plane_rotation": (0, 45, 0)})
    m = res.mesh
    assert res.ok and len(m.points) == 8 and len(m.polygons) == 8
    assert _manifold(m) and _consistent(m)
    assert res.selection.edges == {(2, 7), (1, 4)}


def test_plane_cut_world_mode_uses_object_transform():
    cube = Mesh.cube(200.0)
    world = run_tool("plane_cut", cube, Selection("edges"),
                     {"mode": "World", "object_position": (0, 0, 50)})
    assert np.allclose(_new_points(world, 8)[:, 2], -50.0)
    local = run_tool("plane_cut", cube, Selection("edges"),
                     {"mode": "Local", "object_position": (0, 0, 50)})
    assert np.allclose(_new_points(local, 8)[:, 2], 0.0)


def test_plane_cut_screen_mode_uses_camera():
    cube = Mesh.cube(200.0)
    cam = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
    res = run_tool("plane_cut", cube, Selection("edges"), {"mode": "Screen", "camera_rotation": cam})
    assert np.allclose(_new_points(res, 8)[:, 0], 0.0)


def test_plane_cut_restrict_to_selection():
    cube = Mesh.cube(200.0)
    res = run_tool("plane_cut", cube, Selection("polygons", polygons={3}), {"restrict_to_selection": True})
    m = res.mesh
    assert res.ok and len(m.points) == 10 and len(m.polygons) == 9
    assert _manifold(m) and _consistent(m)
    assert len(res.selection.polygons) == 2
    ngon = run_tool("plane_cut", cube, Selection("polygons", polygons={3}),
                    {"restrict_to_selection": True, "create_ngons": True})
    assert len(ngon.mesh.polygons) == 7 and _manifold(ngon.mesh)


def test_plane_cut_remove_sides():
    cube = Mesh.cube(200.0)
    a = run_tool("plane_cut", cube, Selection("edges"), {"slice_mode": "Remove A"})
    assert len(a.mesh.polygons) == 5 and len(a.mesh.points) == 8
    assert np.all(a.mesh.points[:, 2] <= 1e-9)
    assert _consistent(a.mesh) and _open_edges(a.mesh) == 4
    b = run_tool("plane_cut", cube, Selection("edges"), {"slice_mode": "Remove B"})
    assert np.all(b.mesh.points[:, 2] >= -1e-9)
    assert len(b.selection.edges) == 4


def test_plane_cut_split_separates_parts():
    cube = Mesh.cube(200.0)
    res = run_tool("plane_cut", cube, Selection("edges"), {"slice_mode": "Split"})
    m = res.mesh
    assert len(m.polygons) == 10 and len(m.points) == 16
    assert _consistent(m) and _open_edges(m) == 8


def test_plane_cut_missing_mesh_fails():
    cube = Mesh.cube(200.0)
    res = run_tool("plane_cut", cube, Selection("edges"), {"plane_position": (0, 0, 500)})
    assert not res.ok and res.message


def test_line_cut_defaults_and_missing_runtime():
    spec = get_tool("line_cut")
    d = spec.defaults()
    assert spec.name == "Line Cut" and spec.shortcut == "K~K"
    assert d["visible_only"] is True and d["restrict_to_selection"] is False
    assert d["infinite_cut"] is False and d["slice_mode"] == "Cut"
    assert d["auto_snap"] is False and d["create_ngons"] is False
    assert {"start", "end", "view_dir"} <= set(spec.extra["runtime"])
    res = run_tool("line_cut", Mesh.cube(200.0), Selection("edges"), {})
    assert not res.ok and res.message


def _vertical_line(**extra) -> dict:
    params = {"start": (0, -300, 0), "end": (0, 300, 0), "view_dir": (0, 0, -1)}
    params.update(extra)
    return params


def test_line_cut_through_whole_object():
    cube = Mesh.cube(200.0)
    res = run_tool("line_cut", cube, Selection("edges"), _vertical_line(visible_only=False))
    m = res.mesh
    assert res.ok and len(m.points) == 12 and len(m.polygons) == 10
    assert _manifold(m) and _consistent(m)
    assert np.allclose(_new_points(res, 8)[:, 0], 0.0)


def test_line_cut_visible_only_cuts_front():
    cube = Mesh.cube(200.0)
    res = run_tool("line_cut", cube, Selection("edges"), _vertical_line())
    m = res.mesh
    assert res.ok and len(m.points) == 10 and len(m.polygons) == 9
    assert _manifold(m) and _consistent(m)
    assert np.allclose(_new_points(res, 8)[:, 2], 100.0)
    assert len(res.selection.edges) == 1


def test_line_cut_visible_only_skips_occluded():
    mesh = _two_cubes()
    res = run_tool("line_cut", mesh, Selection("edges"), _vertical_line())
    m = res.mesh
    assert res.ok and len(m.points) == 18
    assert np.allclose(_new_points(res, 16)[:, 2], 350.0)
    assert _manifold(m) and _consistent(m)


def test_line_cut_finite_segment_only_inserts_crossed_edge():
    cube = Mesh.cube(200.0)
    short = run_tool("line_cut", cube, Selection("edges"), _vertical_line(end=(0, 0, 0)))
    assert short.ok and len(short.mesh.points) == 9
    assert _manifold(short.mesh) and _consistent(short.mesh)
    infinite = run_tool("line_cut", cube, Selection("edges"), _vertical_line(end=(0, 0, 0), infinite_cut=True))
    assert len(infinite.mesh.points) == 10


def test_line_cut_restrict_to_polygons():
    cube = Mesh.cube(200.0)
    res = run_tool("line_cut", cube, Selection("polygons", polygons={5}),
                   _vertical_line(visible_only=False, restrict_to_selection=True))
    m = res.mesh
    assert res.ok and len(m.points) == 10
    assert _manifold(m) and _consistent(m)
    assert len(res.selection.polygons) == 2


def test_line_cut_object_transform():
    cube = Mesh.cube(200.0)
    res = run_tool("line_cut", cube, Selection("points"),
                   {"start": (50, -300, 0), "end": (50, 300, 0), "view_dir": (0, 0, -1),
                    "visible_only": False, "object_position": (50, 0, 0)})
    assert np.allclose(_new_points(res, 8)[:, 0], 0.0)
    assert len(res.selection.points) == 4


def test_line_cut_ngons_option():
    cube = Mesh.cube(200.0)
    res = run_tool("line_cut", cube, Selection("edges"), _vertical_line(create_ngons=True))
    m = res.mesh
    assert len(m.polygons) == 7
    assert sorted(len(p) for p in m.polygons).count(5) == 2


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
