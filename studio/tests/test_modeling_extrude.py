from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.modeling import Selection, get_tool, run_tool, tool_ids
from quartz_studio.modeling import primitives as prim
from quartz_studio.modeling.meshkit import edge_faces, face_area
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


def _orphans(mesh: Mesh) -> list[int]:
    used = {int(i) for poly in mesh.polygons for i in poly} | {int(i) for e in mesh.loose_edges for i in e}
    return sorted(set(range(len(mesh.points))) - used)


def _volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        ring = mesh.points[list(poly)]
        for k in range(1, len(ring) - 1):
            total += float(np.dot(ring[0], np.cross(ring[k], ring[k + 1]))) / 6.0
    return total


def _selection_valid(mesh: Mesh, sel: Selection) -> bool:
    edges = set(mesh.edges)
    return (all(0 <= f < len(mesh.polygons) for f in sel.polygons)
            and all(0 <= i < len(mesh.points) for i in sel.points)
            and all(tuple(e) in edges for e in sel.edges))


def _all_polygons(mesh: Mesh) -> Selection:
    return Selection("polygons", polygons=set(range(len(mesh.polygons))))


def _side_polygons(mesh: Mesh, axis: int, sign: float) -> set[int]:
    normals = mesh.polygon_normals()
    return {k for k in range(len(mesh.polygons)) if sign * normals[k][axis] > 0.99}


def test_registry_lists_extrude():
    assert "extrude" in tool_ids()
    spec = get_tool("extrude")
    assert spec.drag_param == "offset"
    assert spec.defaults()["offset"] == 5.0


def test_extrude_top_face_moves_out_and_keeps_manifold():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("extrude", cube, Selection("polygons", polygons={top}), {"offset": 50.0})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 10
    assert len(m.points) == 12
    assert _manifold(m) and _consistent(m)
    ys = m.points[list(m.polygons[top])][:, 1]
    assert np.allclose(ys, 150.0)
    assert res.selection.polygons == {top}
    assert len(cube.polygons) == 6


def test_extrude_negative_offset_goes_inside():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("extrude", cube, Selection("polygons", polygons={top}), {"offset": -30.0})
    ys = res.mesh.points[list(res.mesh.polygons[top])][:, 1]
    assert np.allclose(ys, 70.0)


def test_extrude_subdivision_adds_rings():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("extrude", cube, Selection("polygons", polygons={top}),
                   {"offset": 60.0, "subdivision": 3})
    assert len(res.mesh.polygons) == 6 + 12
    assert _manifold(res.mesh) and _consistent(res.mesh)


def test_extrude_ngons_merges_side_strips():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("extrude", cube, Selection("polygons", polygons={top}),
                   {"offset": 60.0, "subdivision": 3, "create_ngons": True})
    assert len(res.mesh.polygons) == 6 + 4
    assert _manifold(res.mesh) and _consistent(res.mesh)


def test_preserve_groups_on_and_off():
    cube = Mesh.cube(200.0)
    faces = set(range(6))
    on = run_tool("extrude", cube, Selection("polygons", polygons=faces),
                  {"offset": 10.0, "max_angle": 180.0})
    assert len(on.mesh.points) == 8
    off = run_tool("extrude", cube, Selection("polygons", polygons=faces),
                   {"offset": 10.0, "preserve_groups": False})
    assert len(off.mesh.points) == 8 + 24
    assert len(off.mesh.polygons) == 6 + 24


def test_max_angle_splits_groups():
    cube = Mesh.cube(200.0)
    normals = cube.polygon_normals()
    top = int(np.argmax(normals[:, 1]))
    side = int(np.argmax(normals[:, 0]))
    res = run_tool("extrude", cube, Selection("polygons", polygons={top, side}),
                   {"offset": 10.0, "max_angle": 45.0})
    assert len(res.mesh.points) == 8 + 8
    joint = run_tool("extrude", cube, Selection("polygons", polygons={top, side}),
                     {"offset": 10.0, "max_angle": 120.0})
    assert len(joint.mesh.points) == 8 + 6


def test_create_caps_keeps_bottom():
    cube = Mesh.cube(200.0)
    top = _top_face_index(cube)
    res = run_tool("extrude", cube, Selection("polygons", polygons={top}),
                   {"offset": 50.0, "create_caps": True})
    assert len(res.mesh.polygons) == 11


def test_extrude_open_edge_builds_quad_with_matching_winding():
    mesh = Mesh([(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100)], [(0, 3, 2, 1)])
    res = run_tool("extrude", mesh, Selection("edges", edges={(0, 1)}), {"offset": 40.0})
    assert res.ok
    m = res.mesh
    assert len(m.polygons) == 2
    assert _consistent(m)
    new = next(iter(res.selection.edges))
    pts = m.points[list(new)]
    assert np.allclose(pts[:, 2], -40.0)


def test_extrude_points_creates_spikes():
    cube = Mesh.cube(200.0)
    res = run_tool("extrude", cube, Selection("points", points={6}), {"offset": 30.0})
    assert len(res.mesh.points) == 9
    assert len(res.selection.points) == 1


def test_wrong_mode_reports():
    cube = Mesh.cube(200.0)
    res = run_tool("extrude", cube, Selection("model"), {})
    assert not res.ok


def test_cube_two_segments_all_faces_leaves_no_orphans():
    cube = prim.cube(segments=(2, 2, 2))
    res = run_tool("extrude", cube, _all_polygons(cube), {"offset": 10.0})
    m = res.mesh
    assert res.ok
    assert len(cube.points) == 26 and len(cube.polygons) == 24
    assert len(m.points) == 74 and len(m.polygons) == 72
    assert _orphans(m) == []
    assert _manifold(m) and _consistent(m)
    assert _volume(m) > 0
    assert _selection_valid(m, res.selection)


def test_cube_single_and_two_adjacent_faces_leave_no_orphans():
    plain = Mesh.cube(200.0)
    top = _top_face_index(plain)
    side = int(np.argmax(plain.polygon_normals()[:, 0]))
    segmented = prim.cube(segments=(2, 2, 2))
    cases = [
        (plain, {top}),
        (plain, {top, side}),
        (segmented, _side_polygons(segmented, 1, 1.0) | _side_polygons(segmented, 0, 1.0)),
    ]
    for mesh, faces in cases:
        res = run_tool("extrude", mesh, Selection("polygons", polygons=faces), {"offset": 10.0})
        assert res.ok
        assert _orphans(res.mesh) == []
        assert _manifold(res.mesh) and _consistent(res.mesh)
        assert _selection_valid(res.mesh, res.selection)


def test_sphere_and_torus_all_faces_leave_no_orphans():
    for mesh in (prim.sphere(segments=8), prim.torus()):
        res = run_tool("extrude", mesh, _all_polygons(mesh), {"offset": 10.0})
        assert res.ok
        assert _orphans(res.mesh) == []
        assert _manifold(res.mesh) and _consistent(res.mesh)
        assert _selection_valid(res.mesh, res.selection)


def test_input_orphan_point_is_kept():
    cube = Mesh.cube(200.0)
    cube.add_point((0.0, 0.0, 0.0))
    top = _top_face_index(cube)
    res = run_tool("extrude", cube, Selection("polygons", polygons={top}), {"offset": 50.0})
    m = res.mesh
    assert len(m.points) == 13
    assert _orphans(m) == [8]
    assert np.allclose(m.points[8], 0.0)


def test_interior_edge_extrude_builds_flap_with_three_faces():
    cube = Mesh.cube(200.0)
    res = run_tool("extrude", cube, Selection("edges", edges={(2, 3)}), {"offset": 20.0})
    m = res.mesh
    assert res.ok
    assert len(m.polygons) == 7
    flap = len(m.polygons) - 1
    assert len(set(m.polygons[flap])) == 4
    assert abs(face_area(m, flap) - 4000.0) < 1e-6
    assert len(edge_faces(m)[(2, 3)]) == 3
    assert flap in edge_faces(m)[(2, 3)]
    assert _orphans(m) == []
    assert _selection_valid(m, res.selection)


def test_edges_and_points_modes_leave_no_orphans():
    cube = Mesh.cube(200.0)
    by_edges = run_tool("extrude", cube, Selection("edges", edges=set(cube.edges)), {"offset": 10.0})
    by_points = run_tool("extrude", cube, Selection("points", points=set(range(8))), {"offset": 10.0})
    assert _orphans(by_edges.mesh) == [] and _orphans(by_points.mesh) == []
    assert _selection_valid(by_edges.mesh, by_edges.selection)
    assert _selection_valid(by_points.mesh, by_points.selection)


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
