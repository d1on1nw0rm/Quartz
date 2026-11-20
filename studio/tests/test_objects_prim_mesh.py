from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.modeling.meshkit import edge_faces, face_area
from quartz_studio.objects import registry
from quartz_studio.objects.prim_mesh import ORIENTATIONS
from quartz_studio.scene import Mesh, reset_scene

IDS = ("cube", "plane", "disc", "pyramid", "sphere", "torus", "cone", "tube", "cylinder",
       "oil_tank", "capsule", "platonic", "landscape", "bezier", "figure", "polygon_object")
ORIENTED = ("plane", "disc", "pyramid", "torus", "cone", "tube", "cylinder", "oil_tank",
            "capsule", "landscape")


def _build(spec_id: str, **params) -> Mesh:
    spec = registry.get(spec_id)
    return spec.build(spec.clamp(params), [])


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


def _euler(mesh: Mesh) -> int:
    return len(mesh.points) - len(mesh.edges) + len(mesh.polygons)


def _volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        p0 = mesh.points[poly[0]]
        for a, b in zip(poly[1:-1], poly[2:]):
            total += float(np.dot(p0, np.cross(mesh.points[a], mesh.points[b])))
    return total / 6.0


def _unique_points(mesh: Mesh) -> bool:
    keys = {tuple(round(float(v), 9) for v in p) for p in mesh.points}
    return len(keys) == len(mesh.points)


def _all_used(mesh: Mesh) -> bool:
    used = {i for poly in mesh.polygons for i in poly}
    return len(used) == len(mesh.points)


def _nondegenerate(mesh: Mesh) -> bool:
    return all(face_area(mesh, k) > 1e-9 for k in range(len(mesh.polygons)))


def _valid(mesh: Mesh) -> bool:
    return bool(len(mesh.points)) and _unique_points(mesh) and _all_used(mesh) and _nondegenerate(mesh)


def _solid(mesh: Mesh, euler: int) -> bool:
    return _valid(mesh) and _closed(mesh) and _euler(mesh) == euler and _volume(mesh) > 0.0


def _size(mesh: Mesh) -> np.ndarray:
    lo, hi = mesh.bounds()
    return hi - lo


def _size_matches(mesh: Mesh, size, tol: float = 1e-6) -> bool:
    return bool(np.allclose(_size(mesh), np.asarray(size, float), atol=tol))


def _box_matches(mesh: Mesh, size, tol: float = 1e-6) -> bool:
    lo, hi = mesh.bounds()
    half = np.asarray(size, float) / 2.0
    return bool(np.allclose(lo, -half, atol=tol) and np.allclose(hi, half, atol=tol))


def _axis(orientation: str) -> np.ndarray:
    sign = -1.0 if orientation.startswith("-") else 1.0
    vec = np.zeros(3)
    vec["XYZ".index(orientation[1])] = sign
    return vec


def _oriented_size(base: np.ndarray, orientation: str) -> np.ndarray:
    x, y, z = base
    if orientation in ("+X", "-X"):
        return np.array([y, x, z])
    if orientation in ("+Z", "-Z"):
        return np.array([x, z, y])
    return np.array([x, y, z])


def test_cube_defaults_are_a_closed_box():
    m = _build("cube")
    assert len(m.points) == 8 and len(m.polygons) == 6
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _solid(m, 2) and abs(_volume(m) - 8000000.0) < 1e-3


def test_cube_sizes_and_segments_counts():
    m = _build("cube", size_x=100.0, size_y=50.0, size_z=80.0,
               segments_x=2, segments_y=3, segments_z=1)
    assert len(m.polygons) == 22
    assert _box_matches(m, (100.0, 50.0, 80.0))
    assert _solid(m, 2)


def test_cube_fillet_default_is_rounded_closed_solid():
    m = _build("cube", fillet=True)
    assert len(m.points) == 728 and len(m.polygons) == 726
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _solid(m, 2)
    assert 0.0 < _volume(m) < 8000000.0


def test_cube_fillet_other_parameters_stay_closed():
    m = _build("cube", size_x=300.0, size_y=120.0, size_z=200.0, fillet=True, fillet_radius=90.0,
               segments_x=2, segments_y=3, fillet_subdivision=2)
    assert _box_matches(m, (300.0, 120.0, 200.0))
    assert _solid(m, 2)
    small = _build("cube", fillet=True, fillet_radius=10.0, fillet_subdivision=1)
    assert _box_matches(small, (200.0, 200.0, 200.0)) and _solid(small, 2)


def test_cube_fillet_with_zero_radius_is_plain_cube():
    m = _build("cube", fillet=True, fillet_radius=0.0)
    assert len(m.points) == 8 and len(m.polygons) == 6


def test_cube_zero_size_is_empty():
    m = _build("cube", size_x=0.0)
    assert len(m.points) == 0 and len(m.polygons) == 0


def test_plane_defaults_face_up():
    m = _build("plane")
    assert len(m.points) == 121 and len(m.polygons) == 100
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _box_matches(m, (400.0, 0.0, 400.0))
    assert _valid(m)


def test_plane_other_parameters():
    m = _build("plane", width=100.0, height=60.0, width_segments=3, height_segments=2)
    assert len(m.points) == 12 and len(m.polygons) == 6
    assert _box_matches(m, (100.0, 0.0, 60.0))
    assert _valid(m)


def test_plane_zero_width_is_empty():
    m = _build("plane", width=0.0)
    assert len(m.points) == 0


def test_disc_defaults_single_ngon():
    m = _build("disc")
    assert len(m.points) == 32 and len(m.polygons) == 1
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _box_matches(m, (200.0, 0.0, 200.0))
    assert _valid(m)


def test_disc_annulus_counts_and_normal():
    m = _build("disc", inner_radius=50.0, outer_radius=100.0, disc_segments=2, rotation_segments=8)
    assert len(m.points) == 24 and len(m.polygons) == 16
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _box_matches(m, (200.0, 0.0, 200.0))
    assert _valid(m)


def test_pyramid_defaults_closed_with_expected_volume():
    m = _build("pyramid")
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _solid(m, 2)
    assert abs(_volume(m) - 200.0 * 200.0 * 200.0 / 3.0) < 1.0


def test_pyramid_other_parameters():
    m = _build("pyramid", size_x=100.0, size_y=150.0, size_z=60.0, segments=3)
    assert _size_matches(m, (100.0, 150.0, 60.0))
    assert _solid(m, 2)


def test_sphere_standard_defaults():
    m = _build("sphere")
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _solid(m, 2)


def test_sphere_standard_other_parameters():
    m = _build("sphere", radius=50.0, segments=8)
    assert _box_matches(m, (100.0, 100.0, 100.0))
    assert _solid(m, 2)


def test_sphere_geodesic_types_lie_on_radius():
    for kind in ("Tetrahedron", "Hexahedron", "Octahedron", "Icosahedron"):
        m = _build("sphere", radius=100.0, segments=2, type=kind)
        radii = np.linalg.norm(m.points, axis=1)
        assert _solid(m, 2), kind
        assert np.allclose(radii, 100.0, atol=1e-6), kind


def test_sphere_hemisphere_is_closed_upper_half():
    m = _build("sphere", radius=100.0, segments=16, type="Hemisphere")
    lo, hi = m.bounds()
    assert np.allclose(lo, [-100.0, 0.0, -100.0], atol=1e-6)
    assert np.allclose(hi, [100.0, 100.0, 100.0], atol=1e-6)
    assert _solid(m, 2)


def test_sphere_unknown_type_falls_back_to_standard():
    m = _build("sphere", type="Nonsense")
    assert registry.get("sphere").clamp({"type": "Nonsense"})["type"] == "Standard"
    assert _solid(m, 2)


def test_torus_defaults_genus_one():
    m = _build("torus")
    assert len(m.points) == 512 and len(m.polygons) == 512
    assert _box_matches(m, (300.0, 100.0, 300.0))
    assert _solid(m, 0)


def test_torus_other_parameters():
    m = _build("torus", ring_radius=60.0, ring_segments=8, pipe_radius=20.0, pipe_segments=8)
    assert _box_matches(m, (160.0, 40.0, 160.0))
    assert _solid(m, 0)


def test_cone_defaults_closed():
    m = _build("cone")
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _solid(m, 2)


def test_cone_other_parameters_with_cap_segments():
    m = _build("cone", top_radius=30.0, bottom_radius=80.0, height=150.0, height_segments=3,
               rotation_segments=12, caps=True, cap_segments=3)
    assert _box_matches(m, (160.0, 150.0, 160.0))
    assert _solid(m, 2)


def test_cone_without_caps_is_open():
    m = _build("cone", top_radius=0.0, bottom_radius=50.0, caps=False)
    assert _valid(m) and not _closed(m)


def test_tube_defaults_hollow_closed():
    m = _build("tube")
    assert _box_matches(m, (200.0, 100.0, 200.0))
    assert _solid(m, 0)


def test_tube_zero_inner_radius_is_solid_cylinder():
    m = _build("tube", inner_radius=0.0, outer_radius=40.0, height=80.0, height_segments=2,
               cap_segments=2, rotation_segments=12)
    assert _box_matches(m, (80.0, 80.0, 80.0))
    assert _solid(m, 2)


def test_cylinder_defaults_closed():
    m = _build("cylinder")
    assert _box_matches(m, (100.0, 200.0, 100.0))
    assert _solid(m, 2)


def test_cylinder_other_parameters_and_open_without_caps():
    m = _build("cylinder", radius=30.0, height=80.0, height_segments=2, rotation_segments=12,
               caps=True, cap_segments=3)
    assert _box_matches(m, (60.0, 80.0, 60.0))
    assert _solid(m, 2)
    open_m = _build("cylinder", radius=30.0, height=80.0, caps=False)
    assert _valid(open_m) and not _closed(open_m)


def test_oil_tank_defaults_closed():
    m = _build("oil_tank")
    assert _box_matches(m, (100.0, 200.0, 100.0))
    assert _solid(m, 2)


def test_oil_tank_other_parameters_and_cap_height_clamp():
    m = _build("oil_tank", radius=40.0, height=120.0, cap_height=20.0, cap_segments=3,
               height_segments=2, rotation_segments=12)
    assert _box_matches(m, (80.0, 120.0, 80.0))
    assert _solid(m, 2)
    clamped = _build("oil_tank", radius=40.0, height=80.0, cap_height=1000.0)
    assert _box_matches(clamped, (80.0, 80.0, 80.0))
    assert _solid(clamped, 2)


def test_capsule_defaults_closed_body_plus_caps():
    m = _build("capsule")
    assert _box_matches(m, (100.0, 200.0, 100.0))
    assert _solid(m, 2)


def test_capsule_other_parameters():
    m = _build("capsule", radius=30.0, height=100.0, height_segments=3, cap_segments=4,
               rotation_segments=12)
    assert _box_matches(m, (60.0, 100.0, 60.0))
    assert _solid(m, 2)


def test_capsule_zero_body_is_closed():
    m = _build("capsule", radius=20.0, height=0.0)
    assert _box_matches(m, (40.0, 40.0, 40.0))
    assert _solid(m, 2)


def test_platonic_face_counts_and_radius():
    counts = {"Tetra": 4, "Hexa": 6, "Octa": 8, "Dodeca": 12, "Icosa": 20, "Soccer": 32}
    for kind, faces in counts.items():
        m = _build("platonic", radius=100.0, segments=1, type=kind)
        assert len(m.polygons) == faces, kind
        assert _solid(m, 2), kind
        assert np.allclose(np.linalg.norm(m.points, axis=1), 100.0, atol=1e-6), kind


def test_platonic_bucky_vertex_and_edge_counts():
    m = _build("platonic", radius=100.0, segments=1, type="Soccer")
    assert len(m.points) == 60 and len(m.edges) == 90


def test_platonic_subdivided_types_stay_closed():
    for kind in ("Tetra", "Hexa", "Octa", "Dodeca", "Icosa", "Soccer"):
        m = _build("platonic", radius=80.0, segments=2, type=kind)
        assert _solid(m, 2), kind


def test_platonic_zero_radius_is_empty():
    m = _build("platonic", radius=0.0)
    assert len(m.points) == 0


def test_landscape_defaults_terrain_range():
    m = _build("landscape")
    assert len(m.points) == 10201 and len(m.polygons) == 10000
    lo, hi = m.bounds()
    assert np.allclose(lo[[0, 2]], [-300.0, -300.0]) and np.allclose(hi[[0, 2]], [300.0, 300.0])
    assert abs(lo[1]) < 1e-9 and abs(hi[1] - 100.0) < 1e-9
    assert _valid(m) and not _closed(m)
    assert np.all(m.polygon_normals()[:, 1] > 0.0)


def test_landscape_other_parameters_and_sea_plateau():
    m = _build("landscape", size_x=200.0, size_y=50.0, size_z=100.0, width_segments=7,
               depth_segments=4, rough_furrows=0.0, fine_furrows=100.0, seed=5,
               sea_level=50.0, plateau_level=100.0)
    assert len(m.points) == 8 * 5 and len(m.polygons) == 28
    lo, hi = m.bounds()
    assert np.allclose(lo, [-100.0, 0.0, -50.0], atol=1e-9)
    assert np.allclose(hi, [100.0, 50.0, 50.0], atol=1e-9)
    assert _valid(m)


def test_landscape_seed_is_deterministic():
    a = _build("landscape", width_segments=20, depth_segments=20, seed=7)
    b = _build("landscape", width_segments=20, depth_segments=20, seed=7)
    c = _build("landscape", width_segments=20, depth_segments=20, seed=8)
    assert np.array_equal(a.points, b.points)
    assert not np.array_equal(a.points, c.points)


def test_landscape_zero_furrows_is_flat_at_sea_level():
    m = _build("landscape", rough_furrows=0.0, fine_furrows=0.0)
    assert np.allclose(m.points[:, 1], 0.0)


def test_bezier_defaults_flat_patch():
    m = _build("bezier")
    assert len(m.points) == 625 and len(m.polygons) == 576
    assert _box_matches(m, (400.0, 0.0, 400.0))
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _valid(m)


def test_bezier_other_parameters():
    m = _build("bezier", subdivision_x=3, subdivision_y=2, grid_x=4, grid_y=2, spacing=100.0)
    assert len(m.points) == 12 and len(m.polygons) == 6
    assert _box_matches(m, (300.0, 0.0, 100.0))
    assert _valid(m)


def test_bezier_minimal_patch():
    m = _build("bezier", subdivision_x=1, subdivision_y=1, grid_x=2, grid_y=2)
    assert len(m.points) == 4 and len(m.polygons) == 1


def test_figure_defaults_six_closed_boxes():
    m = _build("figure")
    assert len(m.points) == 156 and len(m.polygons) == 144
    assert _size_matches(m, (84.0, 200.0, 30.0))
    lo, _ = m.bounds()
    assert abs(lo[1]) < 1e-9
    assert _valid(m) and _closed(m) and _euler(m) == 12


def test_figure_other_parameters():
    m = _build("figure", height=100.0, segments=1)
    assert len(m.points) == 48 and len(m.polygons) == 36
    assert _size_matches(m, (42.0, 100.0, 15.0))
    assert _valid(m) and _closed(m) and _euler(m) == 12


def test_figure_finer_segments_stay_closed():
    m = _build("figure", height=150.0, segments=3)
    assert _size_matches(m, (63.0, 150.0, 22.5))
    assert _valid(m) and _closed(m) and _euler(m) == 12


def _winding_consistent(mesh: Mesh) -> bool:
    directed: dict[tuple[int, int], int] = {}
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            directed[(a, b)] = directed.get((a, b), 0) + 1
    return all(v == 1 and (b, a) in directed for (a, b), v in directed.items())


def test_polygon_object_does_not_collide_with_editable_kind():
    from quartz_studio.scene import EDITABLE_KIND
    assert EDITABLE_KIND not in registry.SPECS
    spec = registry.get("polygon_object")
    assert spec.category == "mesh" and spec.label == "Polygon"
    assert [p.key for p in spec.params] == ["width", "height", "triangle", "reverse"]
    scene = reset_scene()
    obj = scene.add_parametric("polygon_object")
    assert obj.kind == "polygon_object" and not scene.is_editable(obj)


def test_polygon_object_quad_triangle_and_reverse():
    m = _build("polygon_object")
    assert len(m.points) == 4 and len(m.polygons) == 1
    assert _box_matches(m, (400.0, 400.0, 0.0))
    assert np.allclose(m.polygon_normals(), [0.0, 0.0, 1.0])
    flipped = _build("polygon_object", reverse=True)
    assert np.allclose(flipped.polygon_normals(), [0.0, 0.0, -1.0])
    tri = _build("polygon_object", width=100.0, height=60.0, triangle=True)
    assert len(tri.points) == 3 and len(tri.polygons) == 1
    assert _box_matches(tri, (100.0, 60.0, 0.0))
    assert np.allclose(tri.polygon_normals(), [0.0, 0.0, 1.0])
    assert abs(face_area(tri, 0) - 3000.0) < 1e-9
    assert len(_build("polygon_object", width=0.0).points) == 0


def test_capsule_height_is_overall_height():
    for radius, height in ((50.0, 200.0), (30.0, 100.0), (20.0, 61.0), (10.0, 500.0)):
        m = _build("capsule", radius=radius, height=height)
        assert _box_matches(m, (2.0 * radius, height, 2.0 * radius)), (radius, height)
        assert _solid(m, 2), (radius, height)
    sphere_like = _build("capsule", radius=50.0, height=50.0)
    assert _box_matches(sphere_like, (100.0, 100.0, 100.0))
    assert _solid(sphere_like, 2)
    assert np.allclose(_size(_build("capsule"))[1], _size(_build("oil_tank"))[1])


def test_torus_winding_is_consistent_for_every_radius_pair():
    for ring, pipe in ((37.5, 50.0), (0.5, 50.0), (50.0, 50.0), (100.0, 50.0), (60.0, 59.0), (10.0, 90.0)):
        for orientation in ("+Y", "+X", "-Z"):
            m = _build("torus", ring_radius=ring, pipe_radius=pipe, orientation=orientation)
            assert _valid(m), (ring, pipe)
            assert _winding_consistent(m), (ring, pipe, orientation)
            assert all(len(v) == 2 for v in edge_faces(m).values()), (ring, pipe, orientation)
            assert _volume(m) > 0.0, (ring, pipe, orientation)


def test_bezier_grid_parameters_change_the_result():
    shapes = {}
    for gx, gy in ((2, 3), (3, 3), (4, 3), (20, 3), (3, 2), (3, 4), (3, 20)):
        m = _build("bezier", grid_x=gx, grid_y=gy)
        shapes[(gx, gy)] = tuple(np.round(_size(m), 6))
        assert _valid(m), (gx, gy)
    assert len(set(shapes.values())) == len(shapes)
    assert shapes[(3, 3)] == (400.0, 0.0, 400.0)
    assert len(_build("bezier", spacing=0.0).points) == 0


def test_cube_fillet_subdivision_changes_the_mesh_at_every_step():
    counts = [len(_build("cube", fillet=True, fillet_subdivision=k).points) for k in range(1, 9)]
    assert all(b > a for a, b in zip(counts, counts[1:])), counts
    for k in (1, 2, 3, 4):
        assert _solid(_build("cube", fillet=True, fillet_subdivision=k), 2), k


def test_cube_fillet_radius_at_half_size_is_a_clean_round():
    cases = (dict(size_x=0.5, size_y=0.5, size_z=281.0, fillet_radius=0.5),
             dict(size_x=0.5, size_y=0.5, size_z=281.0, fillet_radius=5.0),
             dict(fillet_radius=100.0), dict(fillet_radius=5000.0),
             dict(size_x=100.0, size_y=60.0, size_z=40.0, fillet_radius=20.0))
    for kw in cases:
        for sub in (1, 2, 5):
            m = _build("cube", fillet=True, fillet_subdivision=sub, **kw)
            size = np.array([kw.get("size_x", 200.0), kw.get("size_y", 200.0), kw.get("size_z", 200.0)])
            assert _box_matches(m, size), (kw, sub)
            assert _solid(m, 2), (kw, sub)
            gaps = np.linalg.norm(m.points[:, None] - m.points[None], axis=2) + np.eye(len(m.points)) * 1e9
            assert gaps.min() > 1e-3, (kw, sub, gaps.min())
            assert min(face_area(m, k) for k in range(len(m.polygons))) > 1e-4, (kw, sub)


def test_sphere_segments_minimum_is_three_and_each_value_differs():
    assert registry.get("sphere").param("segments").minimum == 3.0
    assert registry.get("sphere").clamp({"segments": 1})["segments"] == 3
    counts = [len(_build("sphere", segments=k).points) for k in (3, 4, 5, 6)]
    assert len(set(counts)) == len(counts), counts


def test_distances_reject_non_finite_and_counts_have_maximums():
    for spec_id in IDS:
        spec = registry.get(spec_id)
        for param in spec.params:
            if param.kind == "distance":
                for bad in (float("inf"), float("-inf"), float("nan")):
                    value = spec.clamp({param.key: bad})[param.key]
                    assert np.isfinite(value), (spec_id, param.key, bad)
            if param.kind == "int" and (param.key.endswith("segments") or param.key.startswith("subdivision")):
                assert param.maximum is not None, (spec_id, param.key)
    m = _build("cube", size_x=float("inf"))
    assert np.all(np.isfinite(m.points))
    assert registry.get("sphere").clamp({"segments": 100000})["segments"] <= 128


def test_platonic_soccer_replaces_bucky():
    choices = registry.get("platonic").param("type").choices
    assert "Soccer" in choices and "Bucky" not in choices
    assert registry.get("platonic").clamp({"type": "Bucky"})["type"] == "Tetra"


def test_orientation_rotates_plane_and_disc_normals():
    for spec_id in ("plane", "disc"):
        for o in ORIENTATIONS:
            m = _build(spec_id, orientation=o)
            normals = m.polygon_normals()
            assert np.allclose(normals, np.tile(_axis(o), (len(normals), 1)), atol=1e-9), (spec_id, o)
            assert _valid(m), (spec_id, o)


def test_orientation_rotates_solid_extents():
    for spec_id in ORIENTED:
        base = _build(spec_id)
        base_size = _size(base)
        for o in ORIENTATIONS:
            m = _build(spec_id, orientation=o)
            assert _size_matches(m, _oriented_size(base_size, o)), (spec_id, o)
            assert _valid(m), (spec_id, o)


def test_orientation_keeps_solids_outward_and_closed():
    for spec_id, euler in (("pyramid", 2), ("cone", 2), ("cylinder", 2), ("oil_tank", 2),
                           ("capsule", 2), ("torus", 0), ("tube", 0)):
        for o in ORIENTATIONS:
            m = _build(spec_id, orientation=o)
            assert _solid(m, euler), (spec_id, o)


def test_orientation_axis_is_height_axis_of_cylinder():
    m = _build("cylinder", orientation="+X")
    assert _size_matches(m, (200.0, 100.0, 100.0))
    m = _build("cylinder", orientation="-Z")
    assert _size_matches(m, (100.0, 100.0, 200.0))


def test_every_id_is_registered_as_mesh_and_creates_through_scene():
    for spec_id in IDS:
        spec = registry.get(spec_id)
        assert spec.category == "mesh" and spec.inputs == "none", spec_id
        assert spec.clamp(spec.defaults()) == spec.defaults(), spec_id
        scene = reset_scene()
        obj = scene.add_parametric(spec_id)
        assert obj.kind == spec_id and not obj.error, spec_id
        assert len(obj.mesh.points) > 0, spec_id


def test_scene_set_param_rebuilds_each_object():
    cases = (
        ("cube", "size_x", 300.0, (300.0, 200.0, 200.0)),
        ("plane", "width", 100.0, (100.0, 0.0, 400.0)),
        ("disc", "outer_radius", 50.0, (100.0, 0.0, 100.0)),
        ("pyramid", "size_x", 50.0, (50.0, 200.0, 200.0)),
        ("sphere", "radius", 50.0, (100.0, 100.0, 100.0)),
        ("torus", "ring_radius", 50.0, (200.0, 100.0, 200.0)),
        ("cone", "height", 50.0, (200.0, 50.0, 200.0)),
        ("tube", "height", 40.0, (200.0, 40.0, 200.0)),
        ("cylinder", "radius", 20.0, (40.0, 200.0, 40.0)),
        ("oil_tank", "radius", 20.0, (40.0, 200.0, 40.0)),
        ("capsule", "radius", 20.0, (40.0, 200.0, 40.0)),
        ("landscape", "size_x", 300.0, (300.0, 100.0, 600.0)),
        ("figure", "height", 100.0, (42.0 * 0.5 * 2, 100.0, 15.0 * 0.5 * 2)),
    )
    for spec_id, key, value, expected in cases:
        scene = reset_scene()
        obj = scene.add_parametric(spec_id)
        assert scene.set_param(obj, key, value) is True, spec_id
        assert _size_matches(obj.mesh, expected, tol=1e-3), (spec_id, _size(obj.mesh), expected)
        assert scene.set_param(obj, key, value) is False, spec_id


def test_scene_set_param_platonic_and_bezier_and_sphere_type():
    scene = reset_scene()
    obj = scene.add_parametric("platonic")
    assert scene.set_param(obj, "type", "Icosa")
    assert len(obj.mesh.polygons) == 20
    obj = scene.add_parametric("bezier")
    assert scene.set_param(obj, "subdivision_x", 4)
    assert len(obj.mesh.points) == 5 * 25
    obj = scene.add_parametric("sphere")
    assert scene.set_param(obj, "type", "Hemisphere")
    assert abs(obj.mesh.bounds()[0][1]) < 1e-9


def test_scene_set_param_orientation_rotates_object():
    scene = reset_scene()
    obj = scene.add_parametric("cylinder")
    assert scene.set_param(obj, "orientation", "+X")
    assert _size_matches(obj.mesh, (200.0, 100.0, 100.0))


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
