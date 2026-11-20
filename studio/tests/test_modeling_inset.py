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


def _top_face_index(mesh: Mesh) -> int:
    normals = mesh.polygon_normals()
    return int(np.argmax(normals[:, 1]))


def _volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        p = mesh.points[list(poly)]
        for k in range(1, len(p) - 1):
            total += float(np.dot(p[0], np.cross(p[k], p[k + 1])))
    return total / 6.0


def _grid(n: int = 2, size: float = 100.0) -> Mesh:
    pts = [(i * size, 0.0, j * size) for j in range(n + 1) for i in range(n + 1)]
    polys = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            polys.append((a, a + n + 1, a + n + 2, a + 1))
    return Mesh(pts, polys)


def _all_faces(mesh: Mesh) -> set[int]:
    return set(range(len(mesh.polygons)))


def test_registry_lists_group_tools():
    ids = tool_ids()
    for tid in ("inset", "smooth_shift", "thicken", "matrix_extrude"):
        assert tid in ids
    assert "extrude" in ids


def test_inset_defaults():
    spec = get_tool("inset")
    assert spec.name == "Inset"
    assert spec.drag_param == "offset" and spec.interactive
    assert [p.label for p in spec.params] == ["Maximum Angle", "Offset", "Variance", "Subdivision",
                                              "Create N-gons", "Preserve Groups"]
    d = spec.defaults()
    assert d["offset"] == 5.0 and d["variance"] == 0.0 and d["subdivision"] == 1
    assert d["create_ngons"] is False and d["preserve_groups"] is True
    assert spec.modes == ("polygons",)


def test_inset_single_face_moves_ring_inward():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("inset", cube, Selection("polygons", polygons={top}), {"offset": 20.0})
    assert res.ok
    m = res.mesh
    assert len(m.points) == 12 and len(m.polygons) == 10
    assert _manifold(m) and _consistent(m)
    inner = m.points[list(m.polygons[top])]
    assert np.allclose(inner[:, 1], 100.0)
    assert np.allclose(np.abs(inner[:, 0]), 80.0) and np.allclose(np.abs(inner[:, 2]), 80.0)
    assert res.selection.polygons == {top}
    assert len(cube.polygons) == 6 and len(cube.points) == 8


def test_inset_negative_offset_grows():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("inset", cube, Selection("polygons", polygons={top}), {"offset": -10.0})
    inner = res.mesh.points[list(res.mesh.polygons[top])]
    assert np.allclose(np.abs(inner[:, 0]), 110.0)


def test_inset_subdivision_adds_rings_and_ngons_merge():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("inset", cube, Selection("polygons", polygons={top}), {"offset": 30.0, "subdivision": 3})
    assert len(res.mesh.polygons) == 6 + 12
    assert len(res.mesh.points) == 8 + 12
    assert _manifold(res.mesh) and _consistent(res.mesh)
    ng = run_tool("inset", cube, Selection("polygons", polygons={top}),
                  {"offset": 30.0, "subdivision": 3, "create_ngons": True})
    assert len(ng.mesh.polygons) == 6 + 4
    assert _manifold(ng.mesh) and _consistent(ng.mesh)


def test_inset_preserve_groups_keeps_interior_points():
    grid = _grid(2)
    res = run_tool("inset", grid, Selection("polygons", polygons=_all_faces(grid)), {"offset": 10.0})
    m = res.mesh
    assert len(m.points) == 9 + 8
    assert len(m.polygons) == 4 + 8
    assert _consistent(m)
    assert np.allclose(m.points[4], [100.0, 0.0, 100.0])
    xs = [m.points[i] for f in range(4) for i in m.polygons[f] if i != 4]
    for q in xs:
        assert 10.0 - 1e-6 <= q[0] <= 190.0 + 1e-6 and 10.0 - 1e-6 <= q[2] <= 190.0 + 1e-6
    corners = {tuple(np.round(m.points[i], 6)) for f in range(4) for i in m.polygons[f]}
    assert (10.0, 0.0, 10.0) in corners and (190.0, 0.0, 190.0) in corners


def test_inset_preserve_groups_off_insets_each_polygon():
    grid = _grid(2)
    res = run_tool("inset", grid, Selection("polygons", polygons=_all_faces(grid)),
                   {"offset": 10.0, "preserve_groups": False})
    m = res.mesh
    assert len(m.points) == 9 + 16
    assert len(m.polygons) == 4 + 16
    assert _consistent(m)
    for f in range(4):
        q = m.points[list(m.polygons[f])]
        assert np.isclose(q[:, 0].max() - q[:, 0].min(), 80.0)


def test_inset_max_angle_splits_groups():
    cube = Mesh.cube(200.0)
    normals = cube.polygon_normals()
    top = int(np.argmax(normals[:, 1]))
    side = int(np.argmax(normals[:, 0]))
    split = run_tool("inset", cube, Selection("polygons", polygons={top, side}),
                     {"offset": 10.0, "max_angle": 45.0})
    assert len(split.mesh.points) == 8 + 8
    joint = run_tool("inset", cube, Selection("polygons", polygons={top, side}),
                     {"offset": 10.0, "max_angle": 120.0})
    assert len(joint.mesh.points) == 8 + 6
    assert _manifold(joint.mesh) and _consistent(joint.mesh)
    assert _manifold(split.mesh) and _consistent(split.mesh)


def test_inset_variance_changes_offset():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("inset", cube, Selection("polygons", polygons={top}), {"offset": 20.0, "variance": 10.0})
    inner = res.mesh.points[list(res.mesh.polygons[top])]
    width = float(np.abs(inner[:, 0]).max())
    assert 70.0 - 1e-6 <= width <= 90.0 + 1e-6


def test_inset_rejects_wrong_mode_and_empty():
    cube = Mesh.cube(200.0)
    assert not run_tool("inset", cube, Selection("edges", edges={(0, 1)}), {}).ok
    assert not run_tool("inset", cube, Selection("polygons"), {}).ok


def test_smooth_shift_defaults():
    spec = get_tool("smooth_shift")
    assert spec.name == "Smooth Shift"
    assert [p.label for p in spec.params] == ["Maximum Angle", "Offset", "Variance", "Preserve Groups"]
    d = spec.defaults()
    assert d["max_angle"] == 89.0 and d["offset"] == 5.0 and d["preserve_groups"] is True
    assert spec.drag_param == "offset" and spec.shortcut == "M~Y"


def test_smooth_shift_single_face_like_extrude():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("smooth_shift", cube, Selection("polygons", polygons={top}), {"offset": 40.0})
    m = res.mesh
    assert len(m.points) == 12 and len(m.polygons) == 10
    assert _manifold(m) and _consistent(m)
    assert np.allclose(m.points[list(m.polygons[top])][:, 1], 140.0)


def test_smooth_shift_whole_cube_sharp_builds_chamfer():
    cube = Mesh.cube(200.0)
    res = run_tool("smooth_shift", cube, Selection("polygons", polygons=_all_faces(cube)), {"offset": 10.0})
    m = res.mesh
    assert len(m.points) == 24
    assert len(m.polygons) == 6 + 12 + 8
    assert sum(1 for p in m.polygons if len(p) == 3) == 8
    assert _manifold(m) and _consistent(m)
    assert _volume(m) > 0
    assert np.isclose(np.abs(m.points).max(), 110.0)


def test_smooth_shift_whole_cube_smooth_inflates():
    cube = Mesh.cube(200.0)
    res = run_tool("smooth_shift", cube, Selection("polygons", polygons=_all_faces(cube)),
                   {"offset": 10.0, "max_angle": 180.0})
    m = res.mesh
    assert len(m.polygons) == 6
    assert _manifold(m) and _consistent(m)
    assert np.allclose(np.abs(m.points[list({i for p in m.polygons for i in p})]), 110.0)


def test_smooth_shift_two_faces_sharp_corner():
    cube = Mesh.cube(200.0)
    normals = cube.polygon_normals()
    top = int(np.argmax(normals[:, 1]))
    side = int(np.argmax(normals[:, 0]))
    res = run_tool("smooth_shift", cube, Selection("polygons", polygons={top, side}), {"offset": 10.0})
    m = res.mesh
    assert _manifold(m) and _consistent(m)
    assert len(m.points) == 8 + 8
    assert _volume(m) > 8e6


def test_smooth_shift_preserve_groups_off():
    grid = _grid(2)
    res = run_tool("smooth_shift", grid, Selection("polygons", polygons=_all_faces(grid)),
                   {"offset": 10.0, "preserve_groups": False})
    m = res.mesh
    assert len(m.points) == 9 + 16
    assert len(m.polygons) == 4 + 16
    on = run_tool("smooth_shift", grid, Selection("polygons", polygons=_all_faces(grid)), {"offset": 10.0})
    assert len(on.mesh.points) == 8 + 9 and len(on.mesh.polygons) == 4 + 8
    assert _consistent(on.mesh)


def test_thicken_defaults():
    spec = get_tool("thicken")
    assert spec.name == "Thicken"
    assert [p.label for p in spec.params] == ["Thickness", "Subdivision", "Direction", "Create Caps"]
    d = spec.defaults()
    assert d["thickness"] == 10.0 and d["subdivision"] == 1 and d["direction"] == "Normal"
    assert d["create_caps"] is True
    assert set(spec.modes) == {"polygons", "model"}


def test_thicken_plane_makes_closed_box():
    plane = Mesh([(0, 0, 0), (0, 0, 100), (100, 0, 100), (100, 0, 0)], [(0, 1, 2, 3)])
    assert plane.polygon_normals()[0][1] > 0
    res = run_tool("thicken", plane, Selection("model"), {"thickness": 20.0})
    m = res.mesh
    assert len(m.points) == 8 and len(m.polygons) == 6
    assert _manifold(m) and _consistent(m)
    assert np.isclose(m.points[:, 1].min(), 0.0) and np.isclose(m.points[:, 1].max(), 20.0)
    assert np.isclose(_volume(m), 100 * 100 * 20)
    assert res.selection.mode == "model"


def test_thicken_directions():
    plane = Mesh([(0, 0, 0), (0, 0, 100), (100, 0, 100), (100, 0, 0)], [(0, 1, 2, 3)])
    inv = run_tool("thicken", plane, Selection("model"), {"thickness": 20.0, "direction": "Inverse"}).mesh
    assert np.isclose(inv.points[:, 1].min(), -20.0) and np.isclose(inv.points[:, 1].max(), 0.0)
    both = run_tool("thicken", plane, Selection("model"), {"thickness": 20.0, "direction": "Both"}).mesh
    assert np.isclose(both.points[:, 1].min(), -10.0) and np.isclose(both.points[:, 1].max(), 10.0)
    assert np.isclose(_volume(inv), 200000.0) and np.isclose(_volume(both), 200000.0)


def test_thicken_subdivision_and_no_caps():
    plane = Mesh([(0, 0, 0), (0, 0, 100), (100, 0, 100), (100, 0, 0)], [(0, 1, 2, 3)])
    sub = run_tool("thicken", plane, Selection("model"), {"thickness": 20.0, "subdivision": 4}).mesh
    assert len(sub.polygons) == 2 + 16 and len(sub.points) == 4 * 5
    assert _manifold(sub) and _consistent(sub)
    open_ = run_tool("thicken", plane, Selection("model"), {"create_caps": False}).mesh
    assert len(open_.polygons) == 2 and len(open_.points) == 8 and _consistent(open_)


def test_thicken_closed_cube_makes_hollow_shell():
    cube = Mesh.cube(200.0)
    res = run_tool("thicken", cube, Selection("model"), {"thickness": 10.0})
    m = res.mesh
    assert len(m.polygons) == 12 and len(m.points) == 16
    assert _manifold(m) and _consistent(m)
    assert np.isclose(_volume(m), 220.0 ** 3 - 200.0 ** 3)


def test_thicken_polygon_selection_only():
    grid = _grid(2)
    res = run_tool("thicken", grid, Selection("polygons", polygons={0}), {"thickness": 5.0})
    m = res.mesh
    assert res.ok and res.selection.polygons == {0}
    assert len(m.polygons) == 4 + 1 + 4
    assert _consistent(m)
    assert np.allclose(m.points[list(m.polygons[0])][:, 1], 5.0)
    empty = run_tool("thicken", grid, Selection("polygons"), {"thickness": 5.0})
    assert len(empty.mesh.polygons) == 4 + 4 + 8


def test_thicken_rejects_edges_mode():
    assert not run_tool("thicken", Mesh.cube(), Selection("edges", edges={(0, 1)}), {}).ok


def test_matrix_extrude_defaults():
    spec = get_tool("matrix_extrude")
    assert spec.name == "Matrix Extrude"
    labels = [p.label for p in spec.params]
    assert labels[:6] == ["Steps", "Polygon Coordinates", "Variance", "Move", "Scale", "Rotate"]
    d = spec.defaults()
    assert d["steps"] == 5 and d["polygon_coordinates"] is True and d["variance"] == "None"
    assert d["move"] == (0.0, 0.0, 5.0) and d["scale"] == (90.0, 90.0, 90.0)
    assert spec.shortcut == "M~X"


def test_matrix_extrude_steps_move_and_scale():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("matrix_extrude", cube, Selection("polygons", polygons={top}),
                   {"steps": 3, "move": (0.0, 0.0, 10.0), "scale": (50.0, 50.0, 100.0)})
    m = res.mesh
    assert res.ok
    assert len(m.points) == 8 + 12 and len(m.polygons) == 6 + 12
    assert _manifold(m) and _consistent(m)
    tip = m.points[list(m.polygons[top])]
    assert np.allclose(tip[:, 1], 130.0)
    assert np.allclose(np.abs(tip[:, 0]), 12.5) and np.allclose(np.abs(tip[:, 2]), 12.5)
    assert res.selection.polygons == {top}


def test_matrix_extrude_rotation_bends_chain():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("matrix_extrude", cube, Selection("polygons", polygons={top}),
                   {"steps": 2, "move": (0.0, 0.0, 50.0), "scale": (100.0, 100.0, 100.0),
                    "rotate": (0.0, 45.0, 0.0)})
    m = res.mesh
    assert _manifold(m) and _consistent(m)
    tip_normal = m.polygon_normals()[top]
    assert abs(tip_normal[1]) < 1e-6
    straight = run_tool("matrix_extrude", cube, Selection("polygons", polygons={top}),
                        {"steps": 2, "move": (0.0, 0.0, 50.0), "scale": (100.0, 100.0, 100.0),
                         "rotate": (0.0, 0.0, 22.5)}).mesh
    assert np.isclose(straight.polygon_normals()[top][1], 1.0)
    tip = straight.points[list(straight.polygons[top])]
    assert np.allclose(tip[:, 1], 200.0)
    assert np.allclose(np.abs(tip[:, 0]).max(), 100.0 * np.sqrt(2.0))


def test_matrix_extrude_world_coordinates_follow_object_axes():
    cube = Mesh.cube(200.0)
    side = int(np.argmax(cube.polygon_normals()[:, 0]))
    res = run_tool("matrix_extrude", cube, Selection("polygons", polygons={side}),
                   {"steps": 2, "polygon_coordinates": False, "move": (0.0, 30.0, 0.0),
                    "scale": (100.0, 100.0, 100.0)})
    tip = res.mesh.points[list(res.mesh.polygons[side])]
    assert np.allclose(tip[:, 0], 100.0)
    assert np.isclose(tip[:, 1].mean(), 60.0)


def test_matrix_extrude_variance_ranges():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("matrix_extrude", cube, Selection("polygons", polygons={top}),
                   {"steps": 4, "variance": "Per Step", "move": (0.0, 0.0, 5.0), "move_max": (0.0, 0.0, 15.0),
                    "scale": (100.0, 100.0, 100.0), "scale_max": (100.0, 100.0, 100.0),
                    "rotate": (0.0, 0.0, 0.0), "rotate_max": (0.0, 0.0, 0.0)})
    tip = res.mesh.points[list(res.mesh.polygons[top])]
    assert np.allclose(tip[:, 1], tip[0, 1])
    assert 120.0 - 1e-6 <= tip[0, 1] <= 160.0 + 1e-6
    assert _consistent(res.mesh)


def test_matrix_extrude_each_polygon_separately():
    grid = _grid(2)
    res = run_tool("matrix_extrude", grid, Selection("polygons", polygons={0, 3}), {"steps": 2})
    m = res.mesh
    assert len(m.points) == 9 + 16 and len(m.polygons) == 4 + 16
    assert _consistent(m)


def test_matrix_extrude_rejects_wrong_mode():
    assert not run_tool("matrix_extrude", Mesh.cube(), Selection("model"), {}).ok


def _prism(n: int = 6, r: float = 100.0, h: float = 100.0) -> Mesh:
    ring = [(r * np.cos(2 * np.pi * k / n), 0.0, r * np.sin(2 * np.pi * k / n)) for k in range(n)]
    pts = ring + [(x, h, z) for x, _, z in ring]
    top = tuple(n + k for k in reversed(range(n)))
    sides = [(k, n + k, n + (k + 1) % n, (k + 1) % n) for k in range(n)]
    return Mesh(pts, [tuple(range(n)), top] + sides)


def _tube(n: int = 8, r: float = 100.0, h: float = 100.0) -> Mesh:
    ring = [(r * np.cos(2 * np.pi * k / n), 0.0, r * np.sin(2 * np.pi * k / n)) for k in range(n)]
    pts = ring + [(x, h, z) for x, _, z in ring]
    return Mesh(pts, [(k, n + k, n + (k + 1) % n, (k + 1) % n) for k in range(n)])


def _no_fan_edges(mesh: Mesh) -> bool:
    return all(len(v) <= 2 for v in edge_faces(mesh).values())


def _no_unused_points(mesh: Mesh) -> bool:
    return len({i for p in mesh.polygons for i in p}) == len(mesh.points)


def _no_degenerate(mesh: Mesh) -> bool:
    canon = [tuple(sorted(p)) for p in mesh.polygons]
    return (all(len(p) >= 3 and len(set(p)) == len(p) for p in mesh.polygons)
            and len(set(canon)) == len(canon))


def _sound(mesh: Mesh, closed: bool) -> bool:
    ok = _consistent(mesh) and _no_fan_edges(mesh) and _no_degenerate(mesh) and _no_unused_points(mesh)
    return ok and (not closed or (_manifold(mesh) and _volume(mesh) > 0))


def _snapshot(mesh: Mesh):
    return mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges)


def _same(mesh: Mesh, snap) -> bool:
    return np.array_equal(mesh.points, snap[0]) and mesh.polygons == snap[1] and mesh.loose_edges == snap[2]


TOGGLES = {
    "inset": [{}, {"preserve_groups": False}, {"subdivision": 3}, {"subdivision": 3, "create_ngons": True},
              {"offset": -5.0}, {"max_angle": 30.0}, {"max_angle": 180.0}, {"variance": 3.0}],
    "smooth_shift": [{}, {"preserve_groups": False}, {"max_angle": 180.0}, {"max_angle": 0.0},
                     {"offset": -5.0}, {"variance": 3.0}],
    "matrix_extrude": [{}, {"polygon_coordinates": False}, {"variance": "Initial"}, {"variance": "Per Step"},
                       {"rotate": (0.0, 20.0, 0.0)}, {"steps": 1}],
}


def _closed_cases():
    cube = Mesh.cube(200.0)
    prism = _prism()
    return [(cube, {4}), (cube, _all_faces(cube)), (cube, {4, 3}), (cube, {4, 3, 1}),
            (prism, {1}), (prism, _all_faces(prism)), (prism, set(range(2, 8)))]


def test_every_toggle_keeps_closed_meshes_sound():
    for tool, options in TOGGLES.items():
        for mesh, faces in _closed_cases():
            for opts in options:
                res = run_tool(tool, mesh, Selection("polygons", polygons=set(faces)), opts)
                assert res.ok, (tool, opts)
                assert _sound(res.mesh, True), (tool, sorted(faces), opts)
                again = run_tool(tool, res.mesh, res.selection, opts)
                assert again.ok and _sound(again.mesh, True), (tool, sorted(faces), opts, "again")


def test_every_toggle_keeps_open_meshes_sound():
    grid = _grid(4)
    tube = _tube()
    cases = [(grid, _all_faces(grid)), (grid, {5, 6, 9, 10}), (grid, {0}), (grid, {0, 1, 2, 3}),
             (grid, {0, 5}), (grid, {0, 1, 4}), (grid, {0, 1, 2, 4, 6, 8, 9, 10}),
             (tube, _all_faces(tube)), (tube, {0}), (tube, {0, 1, 2, 3})]
    for tool, options in TOGGLES.items():
        for mesh, faces in cases:
            for opts in options:
                res = run_tool(tool, mesh, Selection("polygons", polygons=set(faces)), opts)
                assert res.ok and _sound(res.mesh, False), (tool, sorted(faces), opts)


def test_tools_never_mutate_input():
    cube = Mesh.cube(200.0)
    grid = _grid(4)
    snaps = (_snapshot(cube), _snapshot(grid))
    for tool in ("inset", "smooth_shift", "thicken", "matrix_extrude"):
        run_tool(tool, cube, Selection("polygons", polygons=_all_faces(cube)), {})
        run_tool(tool, grid, Selection("polygons", polygons={0, 5, 6}), {})
    run_tool("thicken", grid, Selection("model"), {})
    assert _same(cube, snaps[0]) and _same(grid, snaps[1])


def test_empty_and_out_of_range_selection_is_rejected():
    cube = Mesh.cube(200.0)
    for tool in ("inset", "smooth_shift", "matrix_extrude"):
        assert not run_tool(tool, cube, Selection("polygons"), {}).ok
        assert not run_tool(tool, cube, Selection("polygons", polygons={99}), {}).ok
    res = run_tool("inset", cube, Selection("polygons", polygons={4, 99}), {"offset": 10.0})
    assert res.ok and res.selection.polygons == {4}


def test_inset_l_shape_mitres_concave_corner():
    grid = _grid(4)
    res = run_tool("inset", grid, Selection("polygons", polygons={0, 1, 4}), {"offset": 10.0})
    m = res.mesh
    corners = {tuple(np.round(m.points[i], 6)) for f in (0, 1, 4) for i in m.polygons[f]}
    for x, z in ((10, 10), (190, 10), (190, 90), (90, 90), (90, 190), (10, 190)):
        assert (float(x), 0.0, float(z)) in corners
    assert np.allclose(m.polygon_normals()[16:], [0.0, 1.0, 0.0])
    assert _sound(m, False)


def test_inset_ngon_shrinks_by_offset():
    prism = _prism(6, 100.0)
    res = run_tool("inset", prism, Selection("polygons", polygons={1}), {"offset": 10.0})
    m = res.mesh
    assert _sound(m, True) and len(m.polygons) == 8 + 6
    assert len(m.polygons[1]) == 6
    inner = m.points[list(m.polygons[1])]
    apothem = 100.0 * np.cos(np.pi / 6)
    radius = (apothem - 10.0) / np.cos(np.pi / 6)
    assert np.allclose(np.linalg.norm(inner[:, [0, 2]], axis=1), radius)
    assert np.allclose(inner[:, 1], 100.0)


def test_inset_open_tube_insets_both_borders():
    tube = _tube()
    res = run_tool("inset", tube, Selection("polygons", polygons=_all_faces(tube)), {"offset": 10.0})
    m = res.mesh
    assert len(m.polygons) == 8 + 16 and len(m.points) == 16 + 16
    assert _sound(m, False)
    inner_y = sorted({round(float(m.points[i][1]), 6) for f in range(8) for i in m.polygons[f]})
    assert inner_y == [10.0, 90.0]


def test_inset_boundary_face_of_open_grid():
    grid = _grid(4)
    res = run_tool("inset", grid, Selection("polygons", polygons={0}), {"offset": 10.0})
    m = res.mesh
    assert _sound(m, False) and len(m.polygons) == 16 + 4
    q = m.points[list(m.polygons[0])]
    assert np.isclose(q[:, 0].min(), 10.0) and np.isclose(q[:, 2].max(), 90.0)


def test_inset_repeated_application_nests_rings():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    first = run_tool("inset", cube, Selection("polygons", polygons={top}), {"offset": 20.0})
    second = run_tool("inset", first.mesh, first.selection, {"offset": 20.0})
    m = second.mesh
    assert _sound(m, True) and len(m.polygons) == 14
    assert np.allclose(np.abs(m.points[list(m.polygons[top])][:, [0, 2]]), 60.0)


def test_smooth_shift_leaves_no_unused_points():
    cube = Mesh.cube(200.0)
    for faces in (_all_faces(cube), {4, 3, 1}):
        res = run_tool("smooth_shift", cube, Selection("polygons", polygons=faces), {"offset": 10.0})
        assert _no_unused_points(res.mesh) and _sound(res.mesh, True)


def test_smooth_shift_prism_keeps_volume_growing():
    prism = _prism()
    res = run_tool("smooth_shift", prism, Selection("polygons", polygons=_all_faces(prism)), {"offset": 10.0})
    assert _sound(res.mesh, True) and _volume(res.mesh) > _volume(prism)
    inward = run_tool("smooth_shift", prism, Selection("polygons", polygons=_all_faces(prism)), {"offset": -10.0})
    assert _sound(inward.mesh, True) and _volume(inward.mesh) < _volume(prism)


def test_thicken_vertex_touching_faces_make_separate_solids():
    grid = _grid(4)
    res = run_tool("thicken", grid, Selection("polygons", polygons={0, 5}), {"thickness": 10.0})
    m = res.mesh
    assert _consistent(m) and _no_fan_edges(m) and _no_degenerate(m)
    assert len(m.polygons) == 16 + 2 + 8
    assert np.isclose(_volume(m), 2 * 100.0 * 100.0 * 10.0)
    solid = [p for k, p in enumerate(m.polygons) if k in (0, 5) or k >= 16]
    ef = edge_faces(Mesh(m.points, solid))
    assert all(len(v) == 2 for v in ef.values())


def test_thicken_whole_open_grid_makes_closed_slab():
    grid = _grid(4)
    for direction in ("Normal", "Inverse", "Both"):
        res = run_tool("thicken", grid, Selection("model"), {"thickness": 10.0, "direction": direction,
                                                            "subdivision": 2})
        assert _sound(res.mesh, True)
        assert np.isclose(_volume(res.mesh), 400.0 * 400.0 * 10.0)


def test_thicken_keeps_free_points_and_drops_orphans():
    plane = Mesh([(0, 0, 0), (0, 0, 100), (100, 0, 100), (100, 0, 0), (500, 500, 500)], [(0, 1, 2, 3)])
    res = run_tool("thicken", plane, Selection("model"), {"thickness": 20.0})
    m = res.mesh
    assert len(m.points) == 1 + 8
    assert any(np.allclose(q, [500.0, 500.0, 500.0]) for q in m.points)


def test_thicken_repeated_on_hollow_shell_stays_consistent():
    cube = Mesh.cube(200.0)
    shell = run_tool("thicken", cube, Selection("model"), {"thickness": 10.0}).mesh
    again = run_tool("thicken", shell, Selection("model"), {"thickness": 5.0}).mesh
    assert _manifold(again) and _consistent(again) and _no_unused_points(again)
    assert len(again.polygons) == 24


def test_matrix_extrude_ngon_chain_closed():
    prism = _prism(5)
    res = run_tool("matrix_extrude", prism, Selection("polygons", polygons={1}), {"steps": 4})
    m = res.mesh
    assert _sound(m, True) and len(m.polygons) == 7 + 20
    tip = m.points[list(m.polygons[1])]
    assert np.allclose(tip[:, 1], 120.0)
    assert np.allclose(np.linalg.norm(tip[:, [0, 2]], axis=1), 100.0 * 0.9 ** 4)


def test_ops_files_have_no_comments():
    import ast
    import io
    import tokenize
    for rel in (("quartz_studio", "modeling", "ops_inset.py"), ("tests", "test_modeling_inset.py")):
        with open(os.path.join(STUDIO_ROOT, *rel), encoding="utf-8") as fh:
            source = fh.read()
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        assert not any(t.type == tokenize.COMMENT for t in tokens), rel
        bare = [n for n in ast.walk(ast.parse(source))
                if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
        assert not bare, rel


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
