from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import math

import numpy as np

from quartz_studio.modeling.meshkit import edge_faces, face_area
from quartz_studio.modeling.primitives import (PRIMITIVES, capsule, cone, cube, cylinder, disc,
                                               oil_tank, platonic, plane, pyramid, sphere, torus, tube)
from quartz_studio.scene import Mesh


def _closed(mesh: Mesh) -> bool:
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


def _outward(mesh: Mesh, reference=None) -> bool:
    normals = mesh.polygon_normals()
    for k, poly in enumerate(mesh.polygons):
        center = mesh.points[list(poly)].mean(axis=0)
        ref = np.zeros(3) if reference is None else reference(center)
        if float(normals[k] @ (center - ref)) <= 0.0:
            return False
    return True


def _tube_reference(inner: float, outer: float):
    mid = (inner + outer) / 2.0

    def ref(c: np.ndarray) -> np.ndarray:
        rho = math.hypot(c[0], c[2])
        if rho < 1e-12:
            return np.zeros(3)
        return np.array([mid * c[0] / rho, 0.0, mid * c[2] / rho])

    return ref


def _torus_reference(big: float):
    def ref(c: np.ndarray) -> np.ndarray:
        theta = math.atan2(c[2], c[0])
        return np.array([big * math.cos(theta), 0.0, big * math.sin(theta)])

    return ref


def _unique_points(mesh: Mesh) -> bool:
    keys = {tuple(round(float(v), 9) for v in p) for p in mesh.points}
    return len(keys) == len(mesh.points)


def _nondegenerate(mesh: Mesh) -> bool:
    return all(face_area(mesh, k) > 1e-9 for k in range(len(mesh.polygons)))


def _box_matches(mesh: Mesh, size: tuple[float, float, float], tol: float = 1e-6) -> bool:
    lo, hi = mesh.bounds()
    half = np.asarray(size, float) / 2.0
    return bool(np.allclose(lo, -half, atol=tol) and np.allclose(hi, half, atol=tol))


def test_plane_default_counts_and_normal():
    m = plane()
    assert len(m.points) == 121 and len(m.polygons) == 100
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _box_matches(m, (400.0, 0.0, 400.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_plane_custom_segments_counts():
    m = plane(width=100.0, height=60.0, width_segments=3, height_segments=2)
    assert len(m.points) == 12 and len(m.polygons) == 6
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _box_matches(m, (100.0, 0.0, 60.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_disc_default_is_single_ngon():
    m = disc()
    assert len(m.points) == 16 and len(m.polygons) == 1
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _box_matches(m, (200.0, 0.0, 200.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_disc_annulus_counts_and_normal():
    m = disc(inner_radius=50.0, outer_radius=100.0, disc_segments=2, rotation_segments=8)
    assert len(m.points) == 24 and len(m.polygons) == 16
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _unique_points(m) and _nondegenerate(m)


def test_disc_with_center_has_ngon_and_quads():
    m = disc(inner_radius=0.0, outer_radius=100.0, disc_segments=3, rotation_segments=8)
    assert len(m.points) == 24 and len(m.polygons) == 17
    assert np.allclose(m.polygon_normals(), [0.0, 1.0, 0.0])
    assert _unique_points(m) and _nondegenerate(m)


def test_sphere_counts_euler_and_outward():
    m = sphere()
    assert len(m.points) == 114 and len(m.polygons) == 128
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_sphere_poles_are_triangles_and_body_quads():
    m = sphere()
    triangles = sum(1 for p in m.polygons if len(p) == 3)
    quads = sum(1 for p in m.polygons if len(p) == 4)
    assert triangles == 32 and quads == 96


def test_cylinder_default_counts_euler_and_outward():
    m = cylinder()
    assert len(m.points) == 80 and len(m.polygons) == 66
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (100.0, 200.0, 100.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_cylinder_without_caps_is_open():
    m = cylinder(caps=False)
    assert len(m.points) == 80 and len(m.polygons) == 64
    assert not _closed(m)


def test_cylinder_cap_segments_counts():
    m = cylinder(cap_segments=3)
    assert len(m.points) == 144 and len(m.polygons) == 130
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _unique_points(m) and _nondegenerate(m)


def test_cone_default_apex_counts_and_outward():
    m = cone()
    assert len(m.points) == 65 and len(m.polygons) == 65
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_cone_frustum_counts_and_outward():
    m = cone(top_radius=40.0, bottom_radius=100.0, height=200.0, height_segments=2, rotation_segments=12)
    assert len(m.points) == 36 and len(m.polygons) == 26
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _unique_points(m) and _nondegenerate(m)


def test_tube_default_counts_euler_and_outward():
    m = tube()
    assert len(m.points) == 64 and len(m.polygons) == 64
    assert _closed(m) and _euler(m) == 0
    assert _outward(m, _tube_reference(50.0, 100.0))
    assert _box_matches(m, (200.0, 100.0, 200.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_tube_custom_counts_euler_and_outward():
    m = tube(inner_radius=40.0, outer_radius=80.0, height=60.0, rotation_segments=12,
             cap_segments=3, height_segments=2)
    assert len(m.points) == 120 and len(m.polygons) == 120
    assert _closed(m) and _euler(m) == 0
    assert _outward(m, _tube_reference(40.0, 80.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_torus_default_counts_euler_and_outward():
    m = torus()
    assert len(m.points) == 128 and len(m.polygons) == 128
    assert _closed(m) and _euler(m) == 0
    assert _outward(m, _torus_reference(100.0))
    assert _box_matches(m, (300.0, 100.0, 300.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_pyramid_default_counts_and_outward():
    m = pyramid()
    assert len(m.points) == 5 and len(m.polygons) == 5
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_pyramid_segments_counts_and_outward():
    m = pyramid(segments=3)
    assert len(m.points) == 41 and len(m.polygons) == 45
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _unique_points(m) and _nondegenerate(m)


def test_capsule_default_counts_euler_and_outward():
    m = capsule()
    assert len(m.points) == 178 and len(m.polygons) == 192
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (100.0, 300.0, 100.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_capsule_small_counts_and_outward():
    m = capsule(radius=30.0, height=100.0, height_segments=1, cap_segments=2, rotation_segments=8)
    assert len(m.points) == 34 and len(m.polygons) == 40
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _unique_points(m) and _nondegenerate(m)


def test_oil_tank_default_counts_euler_and_outward():
    m = oil_tank()
    assert len(m.points) == 178 and len(m.polygons) == 192
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (100.0, 200.0, 100.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_oil_tank_cap_height_is_clamped():
    m = oil_tank(radius=50.0, height=40.0, height_segments=2, cap_height=-5.0,
                 cap_segments=2, rotation_segments=8)
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (100.0, 40.0, 100.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_platonic_solids_counts_and_outward():
    expected = {
        "Tetrahedron": (4, 4),
        "Hexahedron": (8, 6),
        "Octahedron": (6, 8),
        "Dodecahedron": (20, 12),
        "Icosahedron": (12, 20),
    }
    for kind, (vertices, faces) in expected.items():
        m = platonic(radius=100.0, kind=kind)
        assert len(m.points) == vertices, kind
        assert len(m.polygons) == faces, kind
        assert _closed(m) and _euler(m) == 2, kind
        assert _outward(m), kind
        assert np.allclose(np.linalg.norm(m.points, axis=1), 100.0), kind
        assert _unique_points(m) and _nondegenerate(m), kind


def test_cube_default_counts_euler_and_outward():
    m = cube()
    assert len(m.points) == 8 and len(m.polygons) == 6
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (200.0, 200.0, 200.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_cube_segments_counts_and_box():
    m = cube(size=(200.0, 100.0, 60.0), segments=(2, 3, 4))
    assert len(m.points) == 54 and len(m.polygons) == 52
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (200.0, 100.0, 60.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_primitives_table_names_and_callables():
    assert set(PRIMITIVES) == {"Plane", "Disc", "Sphere", "Cylinder", "Cone", "Tube", "Torus",
                               "Pyramid", "Capsule", "Oil Tank", "Platonic"}
    for menu, (object_name, fn) in PRIMITIVES.items():
        assert object_name == menu
        m = fn()
        assert isinstance(m, Mesh) and len(m.polygons) > 0, menu


def test_all_primitives_unique_points_and_nondegenerate():
    for menu, (_, fn) in PRIMITIVES.items():
        m = fn()
        assert _unique_points(m), menu
        assert _nondegenerate(m), menu


def test_invalid_arguments_do_not_raise():
    results = [
        sphere(segments=0),
        cylinder(height_segments=-2, rotation_segments=1, cap_segments=0),
        cone(top_radius=-5.0, rotation_segments=0, height_segments=0),
        tube(inner_radius=200.0, outer_radius=100.0, cap_segments=0, height_segments=-1),
        torus(ring_segments=0, pipe_segments=-1),
        capsule(height_segments=0, cap_segments=0, rotation_segments=2),
        oil_tank(cap_height=1e9),
        platonic(kind="Nope"),
        cube(size=(0.0, 0.0, 0.0), segments=(0, 0, 0)),
        pyramid(segments=0),
        plane(width_segments=0, height_segments=-3),
        disc(disc_segments=0, rotation_segments=0),
    ]
    assert all(isinstance(m, Mesh) for m in results)
    assert len(results[0].polygons) > 0
    assert len(results[7].polygons) == 20


def test_generators_are_pure_and_repeatable():
    a = sphere()
    b = sphere()
    assert np.array_equal(a.points, b.points)
    assert a.polygons == b.polygons


def test_tube_zero_inner_is_closed_cylinder():
    m = tube(inner_radius=0.0, outer_radius=100.0, height=100.0, rotation_segments=16,
             cap_segments=1, height_segments=1)
    assert len(m.points) == 32 and len(m.polygons) == 18
    assert _closed(m) and _euler(m) == 2
    assert _outward(m, _tube_reference(0.0, 100.0))
    assert _box_matches(m, (200.0, 100.0, 200.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_tube_zero_inner_multi_cap_segments_is_closed():
    m = tube(inner_radius=0.0, outer_radius=60.0, height=40.0, rotation_segments=8,
             cap_segments=3, height_segments=2)
    assert _closed(m) and _euler(m) == 2
    assert _outward(m, _tube_reference(0.0, 60.0))
    assert _unique_points(m) and _nondegenerate(m)


def test_tube_inner_not_below_outer_is_empty():
    for inner, outer in ((100.0, 100.0), (200.0, 100.0)):
        m = tube(inner_radius=inner, outer_radius=outer)
        assert len(m.points) == 0 and len(m.polygons) == 0, (inner, outer)


def test_disc_inner_not_below_outer_is_empty():
    for inner, outer in ((100.0, 50.0), (50.0, 50.0)):
        m = disc(inner_radius=inner, outer_radius=outer, disc_segments=2, rotation_segments=8)
        assert len(m.points) == 0 and len(m.polygons) == 0, (inner, outer)


def test_cylinder_zero_radius_is_empty():
    m = cylinder(radius=0.0)
    assert len(m.points) == 0 and len(m.polygons) == 0


def test_platonic_zero_radius_is_empty():
    m = platonic(radius=0.0, kind="Icosahedron")
    assert len(m.points) == 0 and len(m.polygons) == 0


def test_oil_tank_cap_height_above_half_is_clamped():
    m = oil_tank(radius=50.0, height=40.0, cap_height=1e9)
    assert _closed(m) and _euler(m) == 2
    assert _outward(m)
    assert _box_matches(m, (100.0, 40.0, 100.0))
    assert _unique_points(m) and _nondegenerate(m)


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
