from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from ..scene import rotation_matrix

__all__ = [
    "EPS",
    "normalize",
    "perpendicular",
    "axis_angle_matrix",
    "arc_matrix",
    "euler_from_matrix",
    "matrix_from_euler",
    "quat_from_matrix",
    "matrix_from_quat",
    "quat_slerp",
    "orthonormalize",
    "transform_points",
    "aim_matrix",
    "rotation_part",
]

EPS = 1e-9


def normalize(v: Iterable[float]) -> np.ndarray:
    a = np.asarray(v, float)
    n = float(np.linalg.norm(a))
    if n < EPS:
        return np.zeros_like(a)
    return a / n


def perpendicular(v: Iterable[float]) -> np.ndarray:
    a = normalize(v)
    if not np.any(a):
        return np.array([1.0, 0.0, 0.0])
    other = np.array([0.0, 1.0, 0.0]) if abs(a[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    return normalize(np.cross(a, other))


def axis_angle_matrix(axis: Iterable[float], angle: float) -> np.ndarray:
    k = normalize(axis)
    if not np.any(k):
        return np.eye(3)
    x, y, z = k
    kx = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return np.eye(3) + math.sin(angle) * kx + (1.0 - math.cos(angle)) * (kx @ kx)


def arc_matrix(u: Iterable[float], v: Iterable[float]) -> np.ndarray:
    a = normalize(u)
    b = normalize(v)
    if not np.any(a) or not np.any(b):
        return np.eye(3)
    c = float(np.clip(a @ b, -1.0, 1.0))
    axis = np.cross(a, b)
    s = float(np.linalg.norm(axis))
    if s < 1e-12:
        if c > 0.0:
            return np.eye(3)
        return axis_angle_matrix(perpendicular(a), math.pi)
    return axis_angle_matrix(axis / s, math.atan2(s, c))


def euler_from_matrix(m: np.ndarray) -> np.ndarray:
    r = np.asarray(m, float)[:3, :3]
    cy = math.hypot(r[0, 0], r[1, 0])
    y = math.atan2(-r[2, 0], cy)
    if cy > 1e-9:
        x = math.atan2(r[2, 1], r[2, 2])
        z = math.atan2(r[1, 0], r[0, 0])
    else:
        x = 0.0
        z = math.atan2(-r[0, 1], r[1, 1])
    out = np.degrees(np.array([x, y, z], float))
    out[np.abs(out) < 1e-10] = 0.0
    return out


def matrix_from_euler(rotation_deg: Iterable[float]) -> np.ndarray:
    return rotation_matrix(rotation_deg)


def quat_from_matrix(m: np.ndarray) -> np.ndarray:
    r = np.asarray(m, float)[:3, :3]
    t = float(np.trace(r))
    if t > 0.0:
        s = math.sqrt(t + 1.0) * 2.0
        q = np.array([0.25 * s, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s])
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(max(1.0 + r[0, 0] - r[1, 1] - r[2, 2], 0.0)) * 2.0
        q = np.array([(r[2, 1] - r[1, 2]) / s, 0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s])
    elif r[1, 1] > r[2, 2]:
        s = math.sqrt(max(1.0 + r[1, 1] - r[0, 0] - r[2, 2], 0.0)) * 2.0
        q = np.array([(r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s])
    else:
        s = math.sqrt(max(1.0 + r[2, 2] - r[0, 0] - r[1, 1], 0.0)) * 2.0
        q = np.array([(r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s])
    q = q / max(float(np.linalg.norm(q)), EPS)
    return q if q[0] >= 0.0 else -q


def matrix_from_quat(q: Iterable[float]) -> np.ndarray:
    w, x, y, z = normalize(q) if np.any(np.asarray(q, float)) else (1.0, 0.0, 0.0, 0.0)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], float)


def quat_slerp(a: Iterable[float], b: Iterable[float], t: float) -> np.ndarray:
    qa = normalize(a)
    qb = normalize(b)
    d = float(qa @ qb)
    if d < 0.0:
        qb = -qb
        d = -d
    if d > 0.9995:
        return normalize(qa + (qb - qa) * t)
    theta = math.acos(min(1.0, d))
    s = math.sin(theta)
    return (math.sin((1.0 - t) * theta) / s) * qa + (math.sin(t * theta) / s) * qb


def orthonormalize(m: np.ndarray) -> np.ndarray:
    u, _s, vt = np.linalg.svd(np.asarray(m, float)[:3, :3])
    r = u @ vt
    if np.linalg.det(r) < 0.0:
        u[:, -1] = -u[:, -1]
        r = u @ vt
    return r


def rotation_part(linear: np.ndarray, scale: Iterable[float] | None = None) -> np.ndarray:
    lin = np.asarray(linear, float)[:3, :3]
    if scale is None:
        return orthonormalize(lin)
    s = np.asarray(scale, float)
    safe = np.where(np.abs(s) > EPS, s, 1.0)
    return orthonormalize(lin / safe[None, :])


def transform_points(m: np.ndarray, pts: np.ndarray) -> np.ndarray:
    p = np.atleast_2d(np.asarray(pts, float))
    return p @ m[:3, :3].T + m[:3, 3]


def aim_matrix(direction: Iterable[float], up: Iterable[float] = (0.0, 1.0, 0.0)) -> np.ndarray:
    x = normalize(direction)
    if not np.any(x):
        return np.eye(3)
    hint = normalize(up)
    if not np.any(hint) or abs(float(x @ hint)) > 0.999:
        hint = np.array([0.0, 0.0, -1.0]) if abs(x[2]) < 0.999 else np.array([0.0, 1.0, 0.0])
    z = normalize(np.cross(x, hint))
    y = np.cross(z, x)
    return np.column_stack([x, y, z])
