import numpy as np
import pytest

from quartz.geometry import (
    bound_box,
    bounds,
    compose_trs,
    decompose_trs,
    euler_to_matrix3,
    matrix3_to_quat,
    quat_to_matrix3,
    transform_directions,
    transform_normals,
    transform_points,
)

EULER_XYZ = np.array(
    [
        [0.936293, -0.275096, 0.218351],
        [0.289629, 0.956425, -0.036957],
        [-0.198669, 0.097843, 0.975170],
    ]
)
EULER_ZYX = np.array(
    [
        [0.936293, -0.289629, 0.198669],
        [0.312992, 0.944703, -0.097843],
        [-0.159345, 0.153792, 0.975170],
    ]
)


def test_euler_to_matrix3_matches_golden():
    np.testing.assert_allclose(euler_to_matrix3((0.1, 0.2, 0.3)), EULER_XYZ, atol=1e-5)
    np.testing.assert_allclose(euler_to_matrix3((0.1, 0.2, 0.3), "ZYX"), EULER_ZYX, atol=1e-5)
    assert euler_to_matrix3((0.1, 0.2, 0.3)).dtype == np.float64


def test_euler_to_matrix3_invalid_order():
    with pytest.raises(ValueError):
        euler_to_matrix3((0.0, 0.0, 0.0), "XYZQ")
    with pytest.raises(ValueError):
        euler_to_matrix3((0.0, 0.0, 0.0), "XXY")
    with pytest.raises(ValueError):
        euler_to_matrix3((0.0, 0.0), "XYZ")


def test_quat_to_matrix3_rotation_z():
    quat = (np.cos(np.pi / 4), 0.0, 0.0, np.sin(np.pi / 4))
    matrix = quat_to_matrix3(quat)
    np.testing.assert_allclose(matrix, np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]]), atol=1e-12)
    with pytest.raises(ValueError):
        quat_to_matrix3((1.0, 0.0, 0.0))


def test_matrix3_to_quat_round_trip():
    quat = np.array([0.983347, 0.034271, 0.106021, 0.143572])
    back = matrix3_to_quat(quat_to_matrix3(quat))
    np.testing.assert_allclose(np.abs(back), np.abs(quat), atol=1e-5)
    np.testing.assert_allclose(quat_to_matrix3(back), quat_to_matrix3(quat), atol=1e-6)
    with pytest.raises(ValueError):
        matrix3_to_quat(np.eye(4))


def test_compose_and_decompose_trs():
    rotation = euler_to_matrix3((0.1, 0.2, 0.3))
    matrix = compose_trs((1.0, 2.0, 3.0), rotation, (2.0, 2.0, 2.0))
    location, quat, scale = decompose_trs(matrix)
    np.testing.assert_allclose(location, [1.0, 2.0, 3.0], atol=1e-12)
    np.testing.assert_allclose(quat, [0.983347, 0.034271, 0.106021, 0.143572], atol=1e-5)
    np.testing.assert_allclose(scale, [2.0, 2.0, 2.0], atol=1e-12)
    np.testing.assert_allclose(compose_trs(location, quat_to_matrix3(quat), scale), matrix, atol=1e-6)


def test_decompose_negative_determinant_negates_scales():
    matrix = np.diag([-2.0, 1.0, 3.0, 1.0])
    _location, quat, scale = decompose_trs(matrix)
    assert np.all(scale < 0)
    rebuilt = compose_trs((0, 0, 0), quat_to_matrix3(quat), scale)
    np.testing.assert_allclose(rebuilt, matrix, atol=1e-9)


def test_compose_trs_validation():
    with pytest.raises(ValueError):
        compose_trs((0, 0), np.eye(3), (1, 1, 1))
    with pytest.raises(ValueError):
        compose_trs((0, 0, 0), np.eye(4), (1, 1, 1))
    with pytest.raises(ValueError):
        compose_trs((0, 0, 0), np.eye(3), (1, 1))


def test_transform_points_and_dtype():
    points = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    matrix = np.eye(4)
    matrix[:3, 3] = (1.0, 2.0, 3.0)
    moved = transform_points(points, matrix)
    np.testing.assert_allclose(moved, np.array([[2, 2, 3], [1, 3, 3]], np.float32))
    assert moved.dtype == np.float32


def test_transform_directions_and_normals():
    matrix = np.diag([2.0, 1.0, 1.0, 1.0])
    directions = np.array([[1.0, 0.0, 0.0]])
    np.testing.assert_allclose(transform_directions(directions, matrix), [[2.0, 0.0, 0.0]])
    normalized = transform_directions(directions, matrix, normalize=True)
    np.testing.assert_allclose(normalized, [[1.0, 0.0, 0.0]])
    normals = transform_normals(directions, matrix)
    np.testing.assert_allclose(normals, [[1.0, 0.0, 0.0]])


def test_bounds_and_bound_box_order():
    points = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]])
    low, high = bounds(points)
    np.testing.assert_allclose(low, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(high, [1.0, 2.0, 3.0])
    box = bound_box(points)
    assert box.shape == (8, 3)
    np.testing.assert_allclose(box[0], [0, 0, 0])
    np.testing.assert_allclose(box[1], [0, 0, 3])
    np.testing.assert_allclose(box[2], [0, 2, 3])
    np.testing.assert_allclose(box[3], [0, 2, 0])
    np.testing.assert_allclose(box[4], [1, 0, 0])
    np.testing.assert_allclose(box[5], [1, 0, 3])
    np.testing.assert_allclose(box[6], [1, 2, 3])
    np.testing.assert_allclose(box[7], [1, 2, 0])


def test_bounds_empty():
    low, high = bounds(np.zeros((0, 3), np.float32))
    np.testing.assert_array_equal(low, np.zeros(3))
    np.testing.assert_array_equal(high, np.zeros(3))


def test_transform_directions_keyword_names():
    m4 = np.diag([2.0, 2.0, 2.0, 1.0])
    out = transform_directions(dirs=np.array([[1.0, 0.0, 0.0]]), m4=m4, normalize=True)
    assert np.allclose(out, [[1.0, 0.0, 0.0]])
