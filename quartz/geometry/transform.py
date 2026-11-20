from __future__ import annotations

from typing import Sequence

import numpy as np

_AXES = {"X": 0, "Y": 1, "Z": 2}


def _axis_rotation(axis: str, angle: float) -> np.ndarray:
    a = _AXES[axis]
    c = float(np.cos(angle))
    s = float(np.sin(angle))
    if a == 0:
        return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=np.float64)
    if a == 1:
        return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.float64)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def euler_to_matrix3(angles: Sequence[float], order: str = "XYZ") -> np.ndarray:
    if not isinstance(order, str) or len(order) != 3:
        raise ValueError(f"invalid rotation order {order!r}")
    order = order.upper()
    if any(axis not in _AXES for axis in order):
        raise ValueError(f"invalid rotation order {order!r}")
    if sorted(order) != ["X", "Y", "Z"]:
        raise ValueError(f"invalid rotation order {order!r}")
    values = [float(value) for value in angles]
    if len(values) != 3:
        raise ValueError("angles must have exactly 3 components")
    by_axis = dict(zip("XYZ", values))
    result = np.eye(3, dtype=np.float64)
    for axis in order:
        result = _axis_rotation(axis, by_axis[axis]) @ result
    return result


def quat_to_matrix3(q: Sequence[float]) -> np.ndarray:
    values = np.asarray(q, dtype=np.float64).reshape(-1)
    if values.size != 4:
        raise ValueError("quaternion must have exactly 4 components")
    w, x, y, z = values
    length = float(np.sqrt(w * w + x * x + y * y + z * z))
    if length > 0.0:
        w, x, y, z = w / length, x / length, y / length, z / length
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def matrix3_to_quat(m: Sequence[Sequence[float]]) -> np.ndarray:
    matrix = np.asarray(m, dtype=np.float64)
    if matrix.shape != (3, 3):
        raise ValueError("matrix must be 3x3")
    trace = float(matrix[0, 0] + matrix[1, 1] + matrix[2, 2])
    if trace > 0.0:
        scale = np.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (matrix[2, 1] - matrix[1, 2]) / scale
        y = (matrix[0, 2] - matrix[2, 0]) / scale
        z = (matrix[1, 0] - matrix[0, 1]) / scale
    elif matrix[0, 0] > matrix[1, 1] and matrix[0, 0] > matrix[2, 2]:
        scale = np.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
        w = (matrix[2, 1] - matrix[1, 2]) / scale
        x = 0.25 * scale
        y = (matrix[0, 1] + matrix[1, 0]) / scale
        z = (matrix[0, 2] + matrix[2, 0]) / scale
    elif matrix[1, 1] > matrix[2, 2]:
        scale = np.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
        w = (matrix[0, 2] - matrix[2, 0]) / scale
        x = (matrix[0, 1] + matrix[1, 0]) / scale
        y = 0.25 * scale
        z = (matrix[1, 2] + matrix[2, 1]) / scale
    else:
        scale = np.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
        w = (matrix[1, 0] - matrix[0, 1]) / scale
        x = (matrix[0, 2] + matrix[2, 0]) / scale
        y = (matrix[1, 2] + matrix[2, 1]) / scale
        z = 0.25 * scale
    quat = np.array([w, x, y, z], dtype=np.float64)
    length = float(np.linalg.norm(quat))
    if length > 0.0:
        quat /= length
    return quat


def compose_trs(
    location: Sequence[float],
    rotation3: Sequence[Sequence[float]],
    scale: Sequence[float],
) -> np.ndarray:
    loc = np.asarray(location, dtype=np.float64).reshape(-1)
    if loc.size != 3:
        raise ValueError("location must have 3 components")
    rot = np.asarray(rotation3, dtype=np.float64)
    if rot.shape != (3, 3):
        raise ValueError("rotation must be 3x3")
    scl = np.asarray(scale, dtype=np.float64).reshape(-1)
    if scl.size != 3:
        raise ValueError("scale must have 3 components")
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = rot * scl[None, :]
    result[:3, 3] = loc
    return result


def decompose_trs(
    m4: Sequence[Sequence[float]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrix = np.asarray(m4, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError("matrix must be 4x4")
    location = matrix[:3, 3].copy()
    linear = matrix[:3, :3].copy()
    scale = np.linalg.norm(linear, axis=0)
    if float(np.linalg.det(linear)) < 0.0:
        scale = -scale
    safe = np.where(scale == 0.0, 1.0, scale)
    rotation = linear / safe[None, :]
    quat = matrix3_to_quat(rotation)
    return location, quat, scale


def transform_points(points: np.ndarray, m4: Sequence[Sequence[float]]) -> np.ndarray:
    data = np.asarray(points)
    matrix = np.asarray(m4, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError("matrix must be 4x4")
    flat = data.reshape(-1, 3)
    result = flat.astype(np.float64) @ matrix[:3, :3].T + matrix[:3, 3]
    return result.astype(data.dtype)


def transform_directions(
    dirs: np.ndarray,
    m4: Sequence[Sequence[float]],
    *,
    normalize: bool = False,
) -> np.ndarray:
    data = np.asarray(dirs)
    matrix = np.asarray(m4, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError("matrix must be 4x4")
    result = data.reshape(-1, 3).astype(np.float64) @ matrix[:3, :3].T
    if normalize:
        lengths = np.linalg.norm(result, axis=1)
        safe = lengths > 0.0
        result[safe] /= lengths[safe, None]
    return result.astype(data.dtype)


def transform_normals(normals: np.ndarray, m4: Sequence[Sequence[float]]) -> np.ndarray:
    data = np.asarray(normals)
    matrix = np.asarray(m4, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError("matrix must be 4x4")
    linear = matrix[:3, :3]
    try:
        inverse = np.linalg.inv(linear).T
    except np.linalg.LinAlgError:
        inverse = np.linalg.pinv(linear).T
    result = data.reshape(-1, 3).astype(np.float64) @ inverse.T
    lengths = np.linalg.norm(result, axis=1)
    safe = lengths > 0.0
    result[safe] /= lengths[safe, None]
    return result.astype(data.dtype)


def bounds(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    data = np.asarray(points)
    flat = data.reshape(-1, 3)
    if flat.shape[0] == 0:
        empty = np.zeros(3, dtype=flat.dtype)
        return empty, empty.copy()
    return flat.min(axis=0), flat.max(axis=0)


def bound_box(points: np.ndarray) -> np.ndarray:
    low, high = bounds(points)
    corners = np.empty((8, 3), dtype=np.float64)
    for index, use_high in enumerate(
        [
            (False, False, False),
            (False, False, True),
            (False, True, True),
            (False, True, False),
            (True, False, False),
            (True, False, True),
            (True, True, True),
            (True, True, False),
        ]
    ):
        for axis in range(3):
            corners[index, axis] = high[axis] if use_high[axis] else low[axis]
    return corners
