from __future__ import annotations

import math

import numpy as np

__all__ = ["BEVEL_SHAPES", "bevel_profile", "offset_rings", "safe_distance"]

BEVEL_SHAPES = ("Round", "Step", "Solid")

_HALVINGS = 6
_MIN_AREA = 1e-9


def bevel_profile(shape: str, size: float, segments: int, tension: float) -> list[tuple[float, float]]:
    size = float(size)
    if size <= 0.0:
        return [(0.0, 0.0)]
    n = max(1, int(segments))
    if shape == "Step":
        out = [(0.0, 0.0)]
        for j in range(1, n + 1):
            out.append((size * (j - 1) / n, size * j / n))
            out.append((size * j / n, size * j / n))
        return out
    if shape == "Solid":
        return [(0.0, size * j / n) for j in range(n + 1)]
    k = min(1.0, max(0.0, float(tension)))
    out = []
    for j in range(n + 1):
        t = j / n
        a = t * math.pi / 2.0
        inset = size * ((1.0 - k) * t + k * (1.0 - math.cos(a)))
        rise = size * ((1.0 - k) * t + k * math.sin(a))
        out.append((float(inset), float(rise)))
    out[-1] = (size, size)
    return out


def _left_normals(ring: np.ndarray) -> np.ndarray:
    d = np.roll(ring, -1, axis=0) - ring
    n = np.stack([-d[:, 1], d[:, 0]], axis=1)
    length = np.linalg.norm(n, axis=1)
    out = np.zeros_like(n)
    ok = length > 0.0
    out[ok] = n[ok] / length[ok, None]
    return out


def _offset_ring(ring: np.ndarray, distance: float) -> np.ndarray:
    count = len(ring)
    if count < 2 or distance == 0.0:
        return ring.copy()
    n_out = _left_normals(ring)
    n_in = np.roll(n_out, 1, axis=0)
    out = ring.copy()
    for i in range(count):
        n1 = n_in[i]
        n2 = n_out[i]
        z1 = not n1.any()
        z2 = not n2.any()
        if z1 and z2:
            continue
        if z1:
            n1 = n2
        if z2:
            n2 = n1
        denom = 1.0 + float(n1 @ n2)
        s = n1 + n2
        if denom < 0.5:
            length = float(np.linalg.norm(s))
            if length > 1e-12:
                m = s / length * 2.0
            else:
                back = ring[i] - ring[i - 1]
                bl = float(np.linalg.norm(back))
                m = -back / bl * 2.0 if bl > 0.0 else np.zeros(2)
        else:
            m = s / denom
        out[i] = ring[i] + distance * m
    return out


def offset_rings(rings: list[np.ndarray], distance: float) -> list[np.ndarray]:
    d = float(distance)
    return [_offset_ring(np.asarray(r, dtype=float).reshape(-1, 2), d) for r in rings]


def _area(ring: np.ndarray) -> float:
    if len(ring) < 3:
        return 0.0
    x = ring[:, 0]
    y = ring[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _segments(rings: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    starts, ends, sid, eid = [], [], [], []
    base = 0
    for r in rings:
        n = len(r)
        if n >= 2:
            idx = np.arange(n)
            starts.append(r)
            ends.append(np.roll(r, -1, axis=0))
            sid.append(base + idx)
            eid.append(base + (idx + 1) % n)
        base += n
    if not starts:
        empty = np.zeros((0, 2))
        return empty, empty, np.zeros(0, int), np.zeros(0, int)
    return np.concatenate(starts), np.concatenate(ends), np.concatenate(sid), np.concatenate(eid)


def _cross(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a[..., 0] - o[..., 0]) * (b[..., 1] - o[..., 1]) - (a[..., 1] - o[..., 1]) * (b[..., 0] - o[..., 0])


def _on(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    return ((np.minimum(a[..., 0], b[..., 0]) <= c[..., 0]) & (c[..., 0] <= np.maximum(a[..., 0], b[..., 0]))
            & (np.minimum(a[..., 1], b[..., 1]) <= c[..., 1]) & (c[..., 1] <= np.maximum(a[..., 1], b[..., 1])))


def _has_crossing(rings: list[np.ndarray]) -> bool:
    a, b, sa, sb = _segments(rings)
    if len(a) < 2:
        return False
    p = a[:, None, :]
    q = b[:, None, :]
    r = a[None, :, :]
    s = b[None, :, :]
    o1 = _cross(p, q, r)
    o2 = _cross(p, q, s)
    o3 = _cross(r, s, p)
    o4 = _cross(r, s, q)
    hit = ((o1 * o2 < 0.0) & (o3 * o4 < 0.0)) | ((o1 == 0.0) & _on(p, q, r)) | ((o2 == 0.0) & _on(p, q, s)) \
        | ((o3 == 0.0) & _on(r, s, p)) | ((o4 == 0.0) & _on(r, s, q))
    share = ((sa[:, None] == sa[None, :]) | (sa[:, None] == sb[None, :])
             | (sb[:, None] == sa[None, :]) | (sb[:, None] == sb[None, :]))
    hit &= ~share
    return bool(hit.any())


def _min_gap(rings: list[np.ndarray]) -> float:
    a, b, sa, sb = _segments(rings)
    if not len(a):
        return math.inf
    pts = np.concatenate(rings)
    gid = np.arange(len(pts))
    ab = b - a
    ll = np.einsum("ij,ij->i", ab, ab)
    ap = pts[:, None, :] - a[None, :, :]
    safe = np.where(ll > 0.0, ll, 1.0)
    t = np.clip(np.einsum("ijk,jk->ij", ap, ab) / safe[None, :], 0.0, 1.0)
    t = np.where(ll[None, :] > 0.0, t, 0.0)
    near = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    dist = np.linalg.norm(pts[:, None, :] - near, axis=2)
    touch = (gid[:, None] == sa[None, :]) | (gid[:, None] == sb[None, :])
    dist = np.where(touch, math.inf, dist)
    return float(dist.min()) if dist.size else math.inf


def _offset_ok(rings: list[np.ndarray], moved: list[np.ndarray]) -> bool:
    for before, after in zip(rings, moved):
        if len(before) < 3:
            continue
        a0 = _area(before)
        a1 = _area(after)
        if abs(a1) <= _MIN_AREA or (a0 > 0.0) != (a1 > 0.0):
            return False
        if not np.isfinite(after).all():
            return False
    return not _has_crossing(moved)


def safe_distance(rings, distance: float) -> float:
    distance = float(distance)
    if distance == 0.0 or not math.isfinite(distance):
        return 0.0
    rr = [np.asarray(r, dtype=float).reshape(-1, 2) for r in rings]
    if not rr:
        return 0.0
    sign = 1.0 if distance > 0.0 else -1.0
    d = min(abs(distance), 0.5 * _min_gap(rr))
    if not d > 0.0:
        return 0.0
    value = d
    for _ in range(_HALVINGS + 1):
        if _offset_ok(rr, offset_rings(rr, sign * value)):
            return sign * value
        value *= 0.5
    return 0.0
