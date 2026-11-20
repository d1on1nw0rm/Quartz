import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from quartz.math import Color, Euler, Matrix, Quaternion, Vector
from quartz.math import bvhtree, geometry, interpolate, noise

ROOT = Path(__file__).resolve().parents[3]
ORDERS = ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"]
TRI = ((0, 0, 0), (1, 0, 0), (0, 1, 0))


def close(a, b, tol=1e-5):
    a = np.asarray(list(a), dtype=np.float64)
    b = np.asarray(list(b), dtype=np.float64)
    return a.shape == b.shape and bool(np.allclose(a, b, atol=tol))


class _Owner:
    pass


@pytest.mark.parametrize("rot", [Quaternion((0, 0, 1), math.pi / 2), Euler((0, 0, math.pi / 2)),
                                 Matrix.Rotation(math.pi / 2, 3, "Z"), Matrix.Rotation(math.pi / 2, 4, "Z")])
def test_m01_vector_rotate(rot):
    v = Vector((1, 0, 0))
    assert v.rotate(rot) is None
    assert close(v, (0, 1, 0))


def test_m01_vector_rotation_difference():
    q = Vector((1, 0, 0)).rotation_difference((0, 1, 0))
    assert isinstance(q, Quaternion)
    assert close(q @ Vector((1, 0, 0)), (0, 1, 0))


def test_m02_matrix_scalar_mul():
    m = Matrix(((1, 2), (3, 4)))
    assert close(np.ravel(m * 2), (2, 4, 6, 8))
    assert close(np.ravel(2.0 * m), (2, 4, 6, 8))


@pytest.mark.parametrize("factory,name", [(lambda: Matrix.Identity(3), "Matrix"),
                                          (lambda: Euler((0.1, 0.2, 0.3)), "Euler"),
                                          (lambda: Color((0.1, 0.2, 0.3)), "Color")])
def test_m03_hash(factory, name):
    with pytest.raises(TypeError) as ei:
        hash(factory())
    assert f"{name} is not frozen (mutable), call freeze first" in str(ei.value)
    assert hash(factory().freeze()) == hash(factory().freeze())


@pytest.mark.parametrize("order", ORDERS)
def test_m04_to_euler_roundtrip(order):
    e = Euler((0.1, 0.2, 0.3), order)
    assert close(e.to_matrix().to_euler(order), (0.1, 0.2, 0.3))
    assert close(e.to_quaternion().to_euler(order), (0.1, 0.2, 0.3))
    big = Euler((-2.5, 1.2, 3.0), order)
    back = big.to_quaternion().to_euler(order)
    assert np.allclose(np.asarray(back.to_matrix()), np.asarray(big.to_matrix()), atol=1e-5)


VERTS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (5, 0, 0), (6, 0, 0), (5, 1, 0)]
POLYS = [(0, 1, 2, 3), (4, 5, 6)]


def test_m05_bvh_polygon_index():
    t = bvhtree.BVHTree.FromPolygons(VERTS, POLYS)
    assert t.ray_cast((0.2, 0.8, 1), (0, 0, -1))[2] == 0
    assert t.ray_cast((0.8, 0.2, 1), (0, 0, -1))[2] == 0
    assert t.ray_cast((5.2, 0.2, 1), (0, 0, -1))[2] == 1
    assert {r[2] for r in t.find_nearest_range((0.5, 0.5, 1), 1.5)} == {0}


def test_m27_bvh_overlap_exact():
    a = bvhtree.BVHTree.FromPolygons(TRI, [(0, 1, 2)])
    near = bvhtree.BVHTree.FromPolygons([(0.9, 0.9, -0.5), (0.9, 0.9, 0.5), (0.95, 0.8, 0)], [(0, 1, 2)])
    cross = bvhtree.BVHTree.FromPolygons([(0.2, 0.2, -1), (0.2, 0.2, 1), (0.3, 0.6, 0)], [(0, 1, 2)])
    coplanar = bvhtree.BVHTree.FromPolygons([(0.2, 0.2, 0), (2, 0.2, 0), (0.2, 2, 0)], [(0, 1, 2)])
    assert a.overlap(near) == []
    assert a.overlap(cross) == [(0, 0)]
    assert a.overlap(coplanar) == [(0, 0)]


def test_m06_matrix_eq_not_sequence():
    m = Matrix.Identity(2)
    assert (m == ((1, 0), (0, 1))) is False
    assert (m == [[1, 0], [0, 1]]) is False
    assert m == Matrix.Identity(2)
    assert m != Matrix.Identity(3)


def test_m07_vector_compare_length():
    a = Vector((1, 0, 0))
    b = Vector((0, 2, 0))
    assert a < b and a <= b and b > a and b >= a and not (a > b)


def test_m08_resize_zero_fill():
    v = Vector((1, 2))
    v.resize(5)
    assert close(v, (1, 2, 0, 0, 0))
    assert close(Vector((1, 2, 3)).resized(4), (1, 2, 3, 0))
    w = Vector((1, 2, 3))
    w.resize_4d()
    assert close(w, (1, 2, 3, 1))


def test_m09_swizzle_write_errors():
    v = Vector((1, 2, 3))
    with pytest.raises(AttributeError):
        v.xx = (1, 2)
    with pytest.raises(AttributeError):
        Vector((1, 2)).xz = (1, 2)
    assert close(v, (1, 2, 3))
    assert "xx" not in vars(v)


@pytest.mark.parametrize("track,up", [("Z", "Z"), ("-Y", "Y"), ("X", "X")])
def test_m10_track_quat_same_axis(track, up):
    with pytest.raises(ValueError):
        Vector((0, 1, 0)).to_track_quat(track, up)


def test_m11_quaternion_mul_elementwise():
    assert close(Quaternion((1, 2, 3, 4)) * Quaternion((2, 3, 4, 5)), (2, 6, 12, 20))
    a = Quaternion((0, 0, 1), 0.3)
    b = Quaternion((1, 0, 0), 0.5)
    assert close(a.cross(b), a @ b)


def test_m12_quaternion_rotate():
    q = Quaternion()
    q.rotate(Euler((0, 0, math.pi / 2)))
    assert close(q, (0.707107, 0, 0, 0.707107))


@pytest.mark.parametrize("op", ["transpose", "invert", "invert_safe", "adjugate", "normalize"])
def test_m13_wrapped_inplace(op):
    view = np.array([[2, 1, 0], [0, 2, 0], [0, 0, 2]], dtype=np.float32)
    ref = Matrix(view.copy())
    getattr(ref, op)()
    calls = []
    m = Matrix._q_wrap(view, owner=_Owner(), on_write=lambda: calls.append(1))
    getattr(m, op)()
    assert np.shares_memory(m._data, view)
    assert np.allclose(view, np.asarray(ref), atol=1e-6) and calls


def test_m13_wrapped_rotate():
    view = np.eye(4, dtype=np.float32)
    m = Matrix._q_wrap(view, owner=_Owner())
    m.rotate(Matrix.Rotation(math.pi / 2, 4, "Z"))
    assert np.allclose(view[:3, :3], [[0, -1, 0], [1, 0, 0], [0, 0, 1]], atol=1e-6)


def test_m14_wrapped_resize():
    m = Matrix._q_wrap(np.eye(3, dtype=np.float32), owner=_Owner())
    with pytest.raises(TypeError):
        m.resize_4x4()


def test_m15_frozen_row_col():
    m = Matrix.Identity(4).freeze()
    with pytest.raises(TypeError):
        m[0][0] = 5.0
    with pytest.raises(TypeError):
        m.col[0][1] = 5.0
    with pytest.raises(TypeError):
        m.row[2].z = 7.0
    assert np.array_equal(m._data, np.eye(4, dtype=np.float32))


def test_m16_ortho_projection_size():
    m4 = Matrix.OrthoProjection("XY", 4)
    assert np.allclose(np.asarray(m4), np.diag([1, 1, 0, 1]))


def test_m17_intersect_line_line():
    p, q = geometry.intersect_line_line((0, 0, 0), (1, 0, 0), (0, 1, 1), (0, 1, 2))
    assert close(p, (0, 0, 0)) and close(q, (0, 1, 0))


def test_m18_intersect_point_tri_projection():
    assert close(geometry.intersect_point_tri((0.2, 0.2, 1.0), *TRI), (0.2, 0.2, 0))


@pytest.mark.parametrize("pt,exp", [((2, 0.5, 0), (1, 0, 0)), ((3, -1, 0), (1, 0, 0)),
                                    ((0.5, -1, 0), (0.5, 0, 0)), ((2, 2, 0), (0.5, 0.5, 0)),
                                    ((-1, 0.5, 2), (0, 0.5, 0))])
def test_m19_closest_point_on_tri(pt, exp):
    assert close(geometry.closest_point_on_tri(pt, *TRI), exp)


def _area2d(pts, t):
    a, b, c = (np.asarray(pts[i][:2], dtype=np.float64) for i in t)
    return 0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


@pytest.mark.parametrize("loops,area", [
    ([[(0, 0, 0), (2, 0, 0), (2, 2, 0), (1, 0.5, 0), (0, 2, 0)]], 2.5),
    ([[(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)], [(1, 1, 0), (1, 3, 0), (3, 3, 0), (3, 1, 0)]], 12.0),
])
def test_m20_tessellate_polygon(loops, area):
    pts = [p for loop in loops for p in loop]
    areas = [_area2d(pts, t) for t in geometry.tessellate_polygon(loops)]
    assert all(a > 0 for a in areas) or all(a < 0 for a in areas)
    assert sum(abs(a) for a in areas) == pytest.approx(area)


def test_m21_poly_3d_calc():
    assert close(interpolate.poly_3d_calc(TRI, (0.2, 0.3, 0)), (0.5, 0.2, 0.3))
    assert close(interpolate.poly_3d_calc(TRI, (1, 0, 0)), (0, 1, 0))
    quad = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    w = interpolate.poly_3d_calc(quad, (0.3, 0.6, 0))
    assert sum(w) == pytest.approx(1.0)
    assert close(np.asarray(w) @ np.asarray(quad, dtype=np.float64), (0.3, 0.6, 0))
    assert close(interpolate.poly_3d_calc(quad, (1, 1, 0)), (0, 0, 1, 0))


def test_m22_noise_seeded_unit_vector():
    noise.seed_set(7)
    a = noise.random_unit_vector()
    noise.seed_set(7)
    assert a == noise.random_unit_vector()


def test_m22_noise_default_seed_across_processes():
    code = ("import sys; sys.path.insert(0, r'%s'); from quartz.math import noise; "
            "print(noise.random(), list(noise.random_unit_vector()), list(noise.random_vector()))" % ROOT)
    outs = [subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60).stdout
            for _ in range(2)]
    assert outs[0] and outs[0] == outs[1]


def test_m23_rotate_axis_local():
    e = Euler((0.0, 0.0, math.pi / 2))
    base = np.asarray(e.to_matrix(), dtype=np.float64)
    e.rotate_axis("X", 0.4)
    exp = base @ np.asarray(Matrix.Rotation(0.4, 3, "X"), dtype=np.float64)
    assert np.allclose(np.asarray(e.to_matrix()), exp, atol=1e-5)


def test_m24_vector_iterable():
    assert close(Vector(x for x in (1, 2, 3)), (1, 2, 3))
    assert close(Vector(range(4)), (0, 1, 2, 3))
    with pytest.raises(ValueError):
        Vector(x for x in (1,))


def test_m25_median_scale_rotated():
    m = Matrix.Rotation(math.pi / 2, 3, "Z") @ Matrix.Scale(2, 3)
    assert m.median_scale == pytest.approx(2.0, abs=1e-5)


def test_m26_color_conversion_new():
    c = Color((0.5, 0.5, 0.5))
    r = c.from_scene_linear_to_srgb()
    assert isinstance(r, Color) and r is not c
    assert close(c, (0.5, 0.5, 0.5))
    back = r.from_srgb_to_scene_linear()
    assert close(back, (0.5, 0.5, 0.5), tol=1e-5)
