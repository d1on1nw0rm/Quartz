from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from ..scene import rotation_matrix

__all__ = [
    "AIM_AXES",
    "rotation_matrix",
    "euler_from_matrix",
    "compose",
    "decompose",
    "orthonormal",
    "look_rotation",
    "quat_from_matrix",
    "matrix_from_quat",
    "slerp",
    "blend_rotation",
    "angle_between",
    "hash_unit",
    "smooth_noise",
]

AIM_AXES = ("+Z", "-Z", "+X", "-X", "+Y", "-Y")


def _wrap_near(a: float, ref: float) -> float:
    return a + 360.0 * round((ref - a) / 360.0)


def euler_from_matrix(m: np.ndarray, reference: Iterable[float] | None = None) -> np.ndarray:
    m = np.asarray(m, float)
    xy = math.hypot(m[0, 0], m[1, 0])
    b = math.atan2(-m[2, 0], xy)
    if xy > 1e-9:
        a = math.atan2(m[2, 1], m[2, 2])
        c = math.atan2(m[1, 0], m[0, 0])
    else:
        a = 0.0
        c = math.atan2(-m[0, 1], m[1, 1])
    first = np.degrees([a, b, c])
    second = np.degrees([a + math.pi, math.pi - b, c + math.pi])
    if reference is None:
        def norm(v):
            return np.array([(x + 180.0) % 360.0 - 180.0 for x in v])
        first, second = norm(first), norm(second)
        best = min((first, second), key=lambda t: float(np.sum(np.abs(t))))
        out = np.array(best, float)
    else:
        ref = np.asarray(reference, float)
        cands = []
        for sol in (first, second):
            cands.append(np.array([_wrap_near(float(x), float(r)) for x, r in zip(sol, ref)]))
        out = min(cands, key=lambda t: float(np.sum(np.abs(t - ref))))
    out[np.abs(out) < 1e-9] = 0.0
    return out


def compose(position: Iterable[float], rotation: np.ndarray, scale: Iterable[float]) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = np.asarray(rotation, float) @ np.diag(np.asarray(scale, float))
    m[:3, 3] = np.asarray(position, float)
    return m


def orthonormal(m: np.ndarray) -> np.ndarray:
    u, _s, vt = np.linalg.svd(np.asarray(m, float)[:3, :3])
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1.0
        r = u @ vt
    return r


def decompose(m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    m = np.asarray(m, float)
    lin = m[:3, :3]
    scale = np.linalg.norm(lin, axis=0)
    safe = np.where(scale > 1e-12, scale, 1.0)
    rot = lin / safe
    if np.linalg.det(rot) < 0:
        scale[0] = -scale[0]
        rot[:, 0] = -rot[:, 0]
    return m[:3, 3].copy(), orthonormal(rot), scale


def _basis(forward: np.ndarray, up: np.ndarray) -> np.ndarray | None:
    f = np.asarray(forward, float)
    n = np.linalg.norm(f)
    if n < 1e-12:
        return None
    z = f / n
    candidates = [np.asarray(up, float), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0]),
                  np.array([1.0, 0.0, 0.0])]
    for u in candidates:
        x = np.cross(u, z)
        ln = np.linalg.norm(x)
        if ln > 1e-6 * max(1.0, np.linalg.norm(u)):
            x = x / ln
            y = np.cross(z, x)
            return np.column_stack([x, y, z])
    return None


def look_rotation(forward: Iterable[float], up: Iterable[float] = (0.0, 1.0, 0.0),
                  aim_axis: str = "+Z") -> np.ndarray | None:
    b = _basis(np.asarray(forward, float), np.asarray(up, float))
    if b is None:
        return None
    x, y, z = b[:, 0], b[:, 1], b[:, 2]
    if aim_axis == "-Z":
        cols = (-x, y, -z)
    elif aim_axis == "+X":
        cols = (z, y, -x)
    elif aim_axis == "-X":
        cols = (-z, y, x)
    elif aim_axis == "+Y":
        cols = (x, z, -y)
    elif aim_axis == "-Y":
        cols = (x, -z, y)
    else:
        cols = (x, y, z)
    return np.column_stack(cols)


def quat_from_matrix(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, float)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2.0
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = np.asarray(q, float)
    return q / np.linalg.norm(q)


def matrix_from_quat(q: Iterable[float]) -> np.ndarray:
    w, x, y, z = np.asarray(q, float) / np.linalg.norm(np.asarray(q, float))
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def slerp(q0: Iterable[float], q1: Iterable[float], t: float) -> np.ndarray:
    a = np.asarray(q0, float)
    b = np.asarray(q1, float)
    dot = float(np.dot(a, b))
    if dot < 0.0:
        b = -b
        dot = -dot
    if dot > 0.9995:
        out = a + t * (b - a)
        return out / np.linalg.norm(out)
    theta = math.acos(min(1.0, dot))
    s = math.sin(theta)
    return (math.sin((1 - t) * theta) / s) * a + (math.sin(t * theta) / s) * b


def blend_rotation(r0: np.ndarray, r1: np.ndarray, t: float) -> np.ndarray:
    if t >= 1.0:
        return np.asarray(r1, float).copy()
    if t <= 0.0:
        return np.asarray(r0, float).copy()
    return matrix_from_quat(slerp(quat_from_matrix(r0), quat_from_matrix(r1), t))


def angle_between(a: Iterable[float], b: Iterable[float]) -> float:
    u = np.asarray(a, float)
    v = np.asarray(b, float)
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu < 1e-12 or nv < 1e-12:
        return 0.0
    c = float(np.dot(u, v) / (nu * nv))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


_MASK = 0xFFFFFFFF


def hash_unit(i: int, seed: int) -> float:
    h = (int(i) * 374761393 + int(seed) * 668265263 + 0x9E3779B9) & _MASK
    h = ((h ^ (h >> 15)) * 2246822519) & _MASK
    h = ((h ^ (h >> 13)) * 3266489917) & _MASK
    h ^= h >> 16
    return (h & _MASK) / float(_MASK) * 2.0 - 1.0


def smooth_noise(t: float, seed: int) -> float:
    i = math.floor(t)
    f = t - i
    a = hash_unit(i, seed)
    b = hash_unit(i + 1, seed)
    w = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
    return a + (b - a) * w
