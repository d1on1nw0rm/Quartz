from __future__ import annotations

import math

import numpy as np
from PySide6.QtGui import QFont, QFontMetricsF, QPainterPath, QTransform

from ..scene import Mesh
from .registry import ObjectSpec, Param, register

TOL = 1e-7
WELD = 1e-6
ALIGNS = ("Left", "Middle", "Right")


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, float)
    if v.ndim == 1:
        n = float(np.linalg.norm(v))
        return v / n if n > 1e-12 else v.copy()
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return np.where(n > 1e-12, v / np.where(n > 1e-12, n, 1.0), v)


def _newell(pts: np.ndarray) -> np.ndarray:
    nxt = np.roll(pts, -1, axis=0)
    return np.array([
        np.sum((pts[:, 1] - nxt[:, 1]) * (pts[:, 2] + nxt[:, 2])),
        np.sum((pts[:, 2] - nxt[:, 2]) * (pts[:, 0] + nxt[:, 0])),
        np.sum((pts[:, 0] - nxt[:, 0]) * (pts[:, 1] + nxt[:, 1])),
    ])


def _basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = _unit(normal)
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = _unit(ref - (ref @ n) * n)
    return u, np.cross(n, u)


def _clean(pts: np.ndarray, closed: bool) -> np.ndarray | None:
    pts = np.asarray(pts, float).reshape(-1, 3)
    if len(pts) < 2:
        return None
    keep = np.ones(len(pts), bool)
    keep[1:] = np.linalg.norm(np.diff(pts, axis=0), axis=1) > TOL
    pts = pts[keep]
    if closed:
        while len(pts) > 1 and np.linalg.norm(pts[0] - pts[-1]) <= TOL:
            pts = pts[:-1]
    need = 3 if closed else 2
    return pts.copy() if len(pts) >= need else None


def _area2(P: np.ndarray) -> float:
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _cross2(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _inside_poly(points: np.ndarray, poly: np.ndarray) -> np.ndarray:
    x, y = points[:, 0], points[:, 1]
    inside = np.zeros(len(points), bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if yi != yj:
            cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
            inside ^= cond
        j = i
    return inside


def _nesting(rings: list[np.ndarray]) -> list[tuple[int, int | None]]:
    n = len(rings)
    areas = [abs(_area2(r)) for r in rings]
    boxes = [(r.min(axis=0), r.max(axis=0)) for r in rings]
    containers: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j or areas[j] <= areas[i]:
                continue
            lo, hi = boxes[j]
            if np.any(boxes[i][0] < lo - TOL) or np.any(boxes[i][1] > hi + TOL):
                continue
            if float(np.mean(_inside_poly(rings[i], rings[j]))) > 0.5:
                containers[i].append(j)
    out = []
    for i in range(n):
        parent = min(containers[i], key=lambda j: areas[j]) if containers[i] else None
        out.append((len(containers[i]), parent))
    return out


def _locally_inside(P, ring: list[int], t: int, b) -> bool:
    n = len(ring)
    a = P[ring[t]]
    p = P[ring[t - 1]]
    q = P[ring[(t + 1) % n]]
    if _cross2(p, a, q) >= 0:
        return _cross2(a, q, b) >= 0 and _cross2(a, b, p) >= 0
    return _cross2(a, q, b) >= 0 or _cross2(a, b, p) >= 0


def _bridge(P: np.ndarray, ring: list[int], hole: list[int]) -> list[int]:
    hm = max(range(len(hole)), key=lambda i: P[hole[i]][0])
    m = hole[hm]
    M = P[m]
    n = len(ring)
    best = None
    for k in range(n):
        A, B = P[ring[k]], P[ring[(k + 1) % n]]
        if A[1] == B[1] or M[1] < min(A[1], B[1]) or M[1] > max(A[1], B[1]):
            continue
        x = A[0] + (M[1] - A[1]) * (B[0] - A[0]) / (B[1] - A[1])
        if x < M[0] - 1e-12:
            continue
        if best is None or x < best[0]:
            best = (x, k)
    if best is None:
        c = min(range(n), key=lambda t: float(np.sum((P[ring[t]] - M) ** 2)))
    else:
        x, k = best
        A, B = P[ring[k]], P[ring[(k + 1) % n]]
        I = np.array([x, M[1]])
        if np.linalg.norm(I - A) <= 1e-12:
            c = k
        elif np.linalg.norm(I - B) <= 1e-12:
            c = (k + 1) % n
        else:
            c = k if A[0] > B[0] else (k + 1) % n
        Pc = P[ring[c]]
        if np.linalg.norm(I - Pc) > 1e-12:
            tri = (M, I, Pc)
            sign = 1.0 if _cross2(*tri) >= 0 else -1.0
            pick = None
            for t in range(n):
                if np.allclose(P[ring[t]], Pc):
                    continue
                R = P[ring[t]]
                if R[0] < M[0]:
                    continue
                if _cross2(P[ring[t - 1]], R, P[ring[(t + 1) % n]]) >= 0:
                    continue
                if (sign * _cross2(M, I, R) >= 0 and sign * _cross2(I, Pc, R) >= 0
                        and sign * _cross2(Pc, M, R) >= 0):
                    dx = R[0] - M[0]
                    ang = abs(R[1] - M[1]) / dx if dx > 1e-12 else 1e18
                    key = (ang, dx * dx + (R[1] - M[1]) ** 2)
                    if pick is None or key < pick[0]:
                        pick = (key, t)
            if pick is not None:
                c = pick[1]
    same = [t for t in range(n) if ring[t] == ring[c]]
    for t in same:
        if _locally_inside(P, ring, t, M):
            c = t
            break
    rot = hole[hm:] + hole[:hm]
    return ring[:c + 1] + rot + [m, ring[c]] + ring[c + 1:]


def _ear_clip(P: np.ndarray, ring: list[int], eps: float) -> list[tuple[int, int, int]]:
    ring = list(ring)
    m = len(ring)
    if m < 3:
        return []
    pts = np.asarray(P, float)[ring]
    prev = [(i - 1) % m for i in range(m)]
    nxt = [(i + 1) % m for i in range(m)]
    alive = np.ones(m, bool)
    _u, inverse, counts = np.unique(pts, axis=0, return_inverse=True, return_counts=True)
    dup = counts[np.asarray(inverse).reshape(-1)] > 1
    cr = np.zeros(m)
    q = np.zeros(m)
    valid = np.zeros(m, bool)
    block = np.zeros(m, bool)

    def update(idx: np.ndarray) -> None:
        a = pts[[prev[i] for i in idx]]
        b = pts[idx]
        c = pts[[nxt[i] for i in idx]]
        cr[idx] = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        block[idx] = (cr[idx] <= eps) | dup[idx]
        span = (np.sum((b - a) ** 2, axis=1) + np.sum((c - b) ** 2, axis=1) + np.sum((a - c) ** 2, axis=1))
        q[idx] = cr[idx] / np.where(span > 0.0, span, 1.0)

    def hit(idx: np.ndarray, others: np.ndarray) -> np.ndarray:
        if not len(others):
            return np.zeros(len(idx), bool)
        a = pts[[prev[i] for i in idx]][:, None, :]
        b = pts[idx][:, None, :]
        c = pts[[nxt[i] for i in idx]][:, None, :]
        x = pts[others][None, :, :]
        d1 = (b[..., 0] - a[..., 0]) * (x[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (x[..., 0] - a[..., 0])
        d2 = (c[..., 0] - b[..., 0]) * (x[..., 1] - b[..., 1]) - (c[..., 1] - b[..., 1]) * (x[..., 0] - b[..., 0])
        d3 = (a[..., 0] - c[..., 0]) * (x[..., 1] - c[..., 1]) - (a[..., 1] - c[..., 1]) * (x[..., 0] - c[..., 0])
        inside = (d1 >= -eps) & (d2 >= -eps) & (d3 >= -eps)
        near = (np.all(np.abs(x - a) < 1e-12, axis=2) | np.all(np.abs(x - b) < 1e-12, axis=2)
                | np.all(np.abs(x - c) < 1e-12, axis=2))
        return (inside & ~near).any(axis=1)

    def check(idx: np.ndarray) -> None:
        if not len(idx):
            return
        valid[idx] = False
        idx = idx[cr[idx] > eps]
        if len(idx):
            valid[idx] = ~hit(idx, np.flatnonzero(alive & block))

    def drop(k: int) -> None:
        was = bool(block[k])
        p, n = prev[k], nxt[k]
        nxt[p], prev[n] = n, p
        alive[k] = False
        valid[k] = False
        pair = np.array([p, n])
        before = block[pair].copy()
        update(pair)
        after = block[pair]
        check(pair)
        if was or (before & ~after).any():
            stale = np.flatnonzero(alive & ~valid & (cr > eps))
            check(stale[(stale != p) & (stale != n)])
        grown = pair[after & ~before]
        if len(grown):
            ok = np.flatnonzero(valid)
            ok = ok[(ok != p) & (ok != n)]
            if len(ok):
                valid[ok[hit(ok, grown)]] = False

    every = np.arange(m)
    update(every)
    check(every)
    tris: list[tuple[int, int, int]] = []
    left = m
    while left > 3:
        live = np.flatnonzero(alive & valid)
        if len(live):
            k = int(live[int(np.argmax(q[live]))])
        else:
            live = np.flatnonzero(alive)
            k = int(live[int(np.argmax(cr[live]))])
            if cr[k] <= eps:
                drop(int(live[int(np.argmin(np.abs(cr[live])))]))
                left -= 1
                continue
        tris.append((ring[prev[k]], ring[k], ring[nxt[k]]))
        drop(k)
        left -= 1
    rest = np.flatnonzero(alive)
    if len(rest) == 3:
        i0 = int(rest[0])
        i1 = nxt[i0]
        i2 = nxt[i1]
        if _cross2(pts[i0], pts[i1], pts[i2]) > eps:
            tris.append((ring[i0], ring[i1], ring[i2]))
    return tris


def _convex_merge(P: np.ndarray, tris: list[tuple[int, ...]], eps: float) -> list[tuple[int, ...]]:
    polys = {i: list(t) for i, t in enumerate(tris)}

    def convex(ring: list[int]) -> bool:
        m = len(ring)
        for k in range(m):
            if _cross2(P[ring[k - 1]], P[ring[k]], P[ring[(k + 1) % m]]) < -eps:
                return False
        return True

    changed = True
    while changed:
        changed = False
        owner: dict[tuple[int, int], int] = {}
        for pid, ring in polys.items():
            for a, b in zip(ring, ring[1:] + ring[:1]):
                owner[(a, b)] = pid
        touched: set[int] = set()
        for (a, b), pid in list(owner.items()):
            qid = owner.get((b, a))
            if qid is None or qid == pid or pid in touched or qid in touched:
                continue
            A, B = polys[pid], polys[qid]
            ia = A.index(b)
            Ar = A[ia:] + A[:ia]
            ib = B.index(a)
            Br = B[ib:] + B[:ib]
            if Ar[-1] != a or Br[-1] != b:
                continue
            merged = Ar + Br[1:-1]
            if len(set(merged)) != len(merged) or not convex(merged):
                continue
            polys[pid] = merged
            del polys[qid]
            touched.add(pid)
            touched.add(qid)
            changed = True
    return [tuple(r) for r in polys.values()]


def _incircle(a, b, c, d) -> float:
    ax, ay = a[0] - d[0], a[1] - d[1]
    bx, by = b[0] - d[0], b[1] - d[1]
    cx, cy = c[0] - d[0], c[1] - d[1]
    return ((ax * ax + ay * ay) * (bx * cy - cx * by) - (bx * bx + by * by) * (ax * cy - cx * ay)
            + (cx * cx + cy * cy) * (ax * by - bx * ay))


def _delaunay(P: np.ndarray, tris: list[tuple[int, int, int]], fixed: set, eps: float) -> list[list[int]]:
    pts = P.tolist()
    faces = [list(t) for t in tris]
    owner: dict[tuple[int, int], int] = {}
    stuck = set(fixed)
    for t, (a, b, c) in enumerate(faces):
        for u, v in ((a, b), (b, c), (c, a)):
            if (u, v) in owner:
                stuck.add((min(u, v), max(u, v)))
            owner[(u, v)] = t
    todo = [(u, v) for (u, v) in owner if u < v]
    guard = 64 * len(faces) + 64
    while todo and guard > 0:
        guard -= 1
        u, v = todo.pop()
        if (u, v) in stuck or (u, v) not in owner or (v, u) not in owner:
            continue
        t1, t2 = owner[(u, v)], owner[(v, u)]
        if t1 == t2:
            continue
        f1, f2 = faces[t1], faces[t2]
        w = f1[(f1.index(u) + 2) % 3]
        x = f2[(f2.index(v) + 2) % 3]
        if w == x:
            continue
        pu, pv, pw, px = pts[u], pts[v], pts[w], pts[x]
        scale = max(abs(pu[0] - pv[0]) + abs(pu[1] - pv[1]), 1e-300) ** 4
        if _incircle(pu, pv, pw, px) <= 1e-9 * scale:
            continue
        if _cross2(pu, px, pw) <= eps or _cross2(px, pv, pw) <= eps:
            continue
        for e in ((u, v), (v, w), (w, u), (v, u), (u, x), (x, v)):
            owner.pop(e, None)
        faces[t1] = [u, x, w]
        faces[t2] = [x, v, w]
        for t in (t1, t2):
            a, b, c = faces[t]
            for e in ((a, b), (b, c), (c, a)):
                owner[e] = t
        for a, b in ((u, x), (x, v), (v, w), (w, u)):
            todo.append((min(a, b), max(a, b)))
    return faces


def _quads(P: np.ndarray, faces: list[list[int]], fixed: set, eps: float) -> list[tuple[int, ...]]:
    owner: dict[tuple[int, int], int] = {}
    for t, (a, b, c) in enumerate(faces):
        for u, v in ((a, b), (b, c), (c, a)):
            owner[(u, v)] = t
    inner = [(u, v) for (u, v) in owner if u < v and (v, u) in owner and (u, v) not in fixed]
    inner.sort(key=lambda e: -float(np.sum((P[e[0]] - P[e[1]]) ** 2)))
    used = [False] * len(faces)
    out: list[tuple[int, ...]] = []
    for u, v in inner:
        t1, t2 = owner[(u, v)], owner[(v, u)]
        if t1 == t2 or used[t1] or used[t2]:
            continue
        f1, f2 = faces[t1], faces[t2]
        w = f1[(f1.index(u) + 2) % 3]
        x = f2[(f2.index(v) + 2) % 3]
        quad = [u, x, v, w]
        if len(set(quad)) < 4:
            continue
        if all(_cross2(P[quad[k - 1]], P[quad[k]], P[quad[(k + 1) % 4]]) > eps for k in range(4)):
            used[t1] = used[t2] = True
            out.append(tuple(quad))
    out.extend(tuple(f) for t, f in enumerate(faces) if not used[t])
    return out


def _cap(points: np.ndarray, outer: list[int], holes: list[list[int]],
         normal: np.ndarray) -> list[tuple[int, ...]]:
    normal = np.asarray(normal, float)
    if float(np.linalg.norm(normal)) < 1e-12 or len(outer) < 3:
        return []
    u, v = _basis(normal)
    ids = list(outer) + [i for h in holes for i in h]
    xyz = points[ids]
    P = np.stack([xyz @ u, xyz @ v], axis=1)
    scale = float(np.ptp(P, axis=0).max())
    if scale < 1e-12:
        return []
    key = (len(outer), tuple(len(h) for h in holes),
           np.round((P - P.min(axis=0)) / scale, 10).tobytes())
    hit = _CAP_CACHE.pop(key, None)
    if hit is None:
        hit = _cap_local(P, len(outer), [len(h) for h in holes], scale)
        while len(_CAP_CACHE) >= _CAP_LIMIT:
            _CAP_CACHE.pop(next(iter(_CAP_CACHE)))
    _CAP_CACHE[key] = hit
    return [tuple(int(ids[i]) for i in poly) for poly in hit]


_CAP_CACHE: dict = {}
_CAP_LIMIT = 512


def _cap_local(P: np.ndarray, count: int, sizes: list[int], scale: float) -> list[tuple[int, ...]]:
    eps = 1e-12 * scale * scale
    start = count
    local_outer = list(range(start))
    local_holes = []
    for size in sizes:
        local_holes.append(list(range(start, start + size)))
        start += size
    if _area2(P[local_outer]) < 0:
        local_outer.reverse()
    if abs(_area2(P[local_outer])) <= eps:
        return []
    ring = local_outer
    oriented = []
    for h in local_holes:
        if len(h) < 3:
            continue
        if _area2(P[h]) > 0:
            h = h[::-1]
        oriented.append(h)
    for h in sorted(oriented, key=lambda r: -max(P[i][0] for i in r)):
        ring = _bridge(P, ring, h)
    tris = _ear_clip(P, ring, eps)
    merged = _convex_merge(P, tris, 1e-9 * scale * scale)
    if len(merged) <= 1:
        return merged
    fixed = set()
    for loop in [local_outer] + oriented:
        for a, b in zip(loop, loop[1:] + loop[:1]):
            fixed.add((min(a, b), max(a, b)))
    return _quads(P, _delaunay(P, tris, fixed, eps), fixed, 1e-9 * scale * scale)


def _ring_cap(points: np.ndarray, ring: list[int], forward: bool) -> list[tuple[int, ...]]:
    normal = _newell(points[ring])
    return _cap(points, list(ring), [], normal if forward else -normal)


def _skin(grid, ring_closed: bool, layers_closed: bool = False,
          reverse: bool = False) -> list[tuple[int, ...]]:
    g = np.asarray(grid)
    layers, count = g.shape
    out = []
    for k in range(layers if layers_closed else layers - 1):
        k2 = (k + 1) % layers
        for i in range(count if ring_closed else count - 1):
            j = (i + 1) % count
            q = (int(g[k, i]), int(g[k, j]), int(g[k2, j]), int(g[k2, i]))
            out.append(q[::-1] if reverse else q)
    return out


class _Out:

    def __init__(self) -> None:
        self.chunks: list[np.ndarray] = []
        self.polys: list[tuple[int, ...]] = []
        self.count = 0

    def add(self, points: np.ndarray, polys) -> int:
        base = self.count
        self.chunks.append(np.asarray(points, float).reshape(-1, 3))
        self.count += len(points)
        self.polys.extend(tuple(i + base for i in poly) for poly in polys)
        return base

    def mesh(self, orient_volume: bool = False) -> Mesh:
        if not self.chunks or not self.polys:
            return Mesh.empty()
        return _finish(np.vstack(self.chunks), self.polys, orient_volume)


def _closed_consistent(polys) -> bool:
    directed: set[tuple[int, int]] = set()
    for poly in polys:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a, b) in directed:
                return False
            directed.add((a, b))
    return bool(directed) and all((b, a) in directed for a, b in directed)


def _volume(points: np.ndarray, polys) -> float:
    total = 0.0
    for poly in polys:
        p0 = points[poly[0]]
        for k in range(1, len(poly) - 1):
            total += float(p0 @ np.cross(points[poly[k]], points[poly[k + 1]]))
    return total / 6.0


def _newell_norms(pts: np.ndarray, rings: list[tuple[int, ...]]) -> np.ndarray:
    if not rings:
        return np.zeros(0)
    counts = np.fromiter((len(r) for r in rings), int, len(rings))
    flat = np.fromiter((i for r in rings for i in r), int, int(counts.sum()))
    starts = np.cumsum(counts) - counts
    pid = np.repeat(np.arange(len(rings)), counts)
    local = np.arange(len(flat)) - starts[pid]
    nxt = flat[starts[pid] + (local + 1) % counts[pid]]
    a, b = pts[flat], pts[nxt]
    parts = [(a[:, 1] - b[:, 1]) * (a[:, 2] + b[:, 2]), (a[:, 2] - b[:, 2]) * (a[:, 0] + b[:, 0]),
             (a[:, 0] - b[:, 0]) * (a[:, 1] + b[:, 1])]
    n = np.stack([np.bincount(pid, w, len(rings)) for w in parts], axis=1).astype(float)
    return np.linalg.norm(n, axis=1)


def _finish(points: np.ndarray, polys, orient_volume: bool = False) -> Mesh:
    keys = np.round(points / WELD).astype(np.int64)
    seen: dict[tuple, int] = {}
    remap = np.zeros(len(points), dtype=int)
    kept: list[int] = []
    for i, key in enumerate(map(tuple, keys)):
        j = seen.get(key)
        if j is None:
            j = len(kept)
            seen[key] = j
            kept.append(i)
        remap[i] = j
    pts = points[kept]
    rings: list[tuple[int, ...]] = []
    for poly in polys:
        ring = [int(remap[i]) for i in poly]
        ring = [v for k, v in enumerate(ring) if v != ring[k - 1]]
        if len(ring) < 3 or len(set(ring)) != len(ring):
            continue
        rings.append(tuple(ring))
    keep = _newell_norms(pts, rings) > 1e-9
    out = [r for r, k in zip(rings, keep.tolist()) if k]
    if not out:
        return Mesh.empty()
    if orient_volume and _closed_consistent(out) and _volume(pts, out) < 0:
        out = [poly[::-1] for poly in out]
    used = sorted({i for poly in out for i in poly})
    index = {old: new for new, old in enumerate(used)}
    return Mesh(pts[used], [tuple(index[i] for i in poly) for poly in out])


def _spline_chains(inputs: list) -> list[list[tuple[np.ndarray, bool]]]:
    return [inp.chains() for inp in inputs if inp.is_spline]


def _extrude_set(chains, move: np.ndarray, sub: int, start_cap: bool, end_cap: bool,
                 out: _Out) -> None:
    rings: list[np.ndarray] = []
    opens: list[np.ndarray] = []
    for pts, closed in chains:
        c = _clean(pts, closed)
        if c is None:
            continue
        if closed:
            if float(np.linalg.norm(_newell(c))) > 1e-9:
                rings.append(c)
        else:
            opens.append(c)
    if not rings and not opens:
        return
    length = float(np.linalg.norm(move))
    normal = np.array([0.0, 0.0, 1.0])
    caps_ok = False
    if rings:
        big = max((_newell(r) for r in rings), key=lambda v: float(np.linalg.norm(v)))
        normal = _unit(big)
        if normal @ move < 0:
            normal = -normal
        caps_ok = abs(float(normal @ move)) > 1e-6 * length
    depth: list[tuple[int, int | None]] = []
    if rings:
        u, v = _basis(normal)
        flat = [np.stack([r @ u, r @ v], axis=1) for r in rings]
        depth = _nesting(flat)
        for i, (d, _) in enumerate(depth):
            area = _area2(flat[i])
            if (d % 2 == 0) != (area > 0):
                rings[i] = rings[i][::-1].copy()
    shapes = rings + opens
    chunks = []
    grids = []
    base = 0
    for shape in shapes:
        n = len(shape)
        layers = [shape + move * (k / sub) for k in range(sub + 1)]
        chunks.append(np.vstack(layers))
        grids.append(base + np.arange((sub + 1) * n).reshape(sub + 1, n))
        base += (sub + 1) * n
    allpts = np.vstack(chunks)
    polys: list[tuple[int, ...]] = []
    for i, grid in enumerate(grids):
        polys.extend(_skin(grid, i < len(rings)))
    if caps_ok:
        for o, (d, _) in enumerate(depth):
            if d % 2:
                continue
            holes = [h for h, (dh, parent) in enumerate(depth) if dh == d + 1 and parent == o]
            if start_cap:
                polys.extend(_cap(allpts, list(grids[o][0]), [list(grids[h][0]) for h in holes],
                                  -normal))
            if end_cap:
                polys.extend(_cap(allpts, list(grids[o][-1]), [list(grids[h][-1]) for h in holes],
                                  normal))
    out.add(allpts, polys)


def _extrude_chains(sets, move, sub: int, start_cap: bool, end_cap: bool) -> Mesh:
    move = np.asarray(move, float)
    if float(np.linalg.norm(move)) < 1e-9:
        return Mesh.empty()
    out = _Out()
    for chains in sets:
        _extrude_set(chains, move, max(1, int(sub)), start_cap, end_cap, out)
    return out.mesh()


def build_extrude(p: dict, inputs: list) -> Mesh:
    sets = [c for c in _spline_chains(inputs) if c]
    if not sets:
        return Mesh.empty()
    if not p["hierarchical"]:
        sets = [[chain for group in sets for chain in group]]
    return _extrude_chains(sets, p["movement"], p["subdivision"], p["start_cap"], p["end_cap"])


def _flux_flip(points: np.ndarray, polys) -> bool:
    flux = 0.0
    up = 0.0
    for poly in polys:
        ring = points[list(poly)]
        n = _newell(ring)
        c = ring.mean(axis=0)
        flux += float(n[0] * c[0] + n[2] * c[2])
        up += float(n[1])
    scale = 1e-9 * max(1.0, float(np.abs(points).max()) ** 3) if len(points) else 1e-9
    if abs(flux) > scale:
        return flux < 0
    return up < 0


def build_lathe(p: dict, inputs: list) -> Mesh:
    angle = float(p["angle"])
    segs = int(p["subdivision"])
    move = float(p["movement"])
    scale = float(p["scale"]) / 100.0
    if abs(angle) < 1e-9 or segs < 1:
        return Mesh.empty()
    wrap = abs(abs(angle) - 360.0) < 1e-9 and abs(move) < 1e-9 and abs(scale - 1.0) < 1e-9
    cols = segs if wrap else segs + 1
    out = _Out()
    for chains in _spline_chains(inputs):
        for pts, closed in chains:
            c = _clean(pts, closed)
            if c is None:
                continue
            count = len(c)
            ncols = cols - 1 if closed and scale <= 1e-9 else cols
            layers = []
            for j in range(ncols):
                s = j / segs
                th = math.radians(angle) * s
                cs, sn = math.cos(th), math.sin(th)
                sc = 1.0 + (scale - 1.0) * s
                x = (c[:, 0] * cs + c[:, 2] * sn) * sc
                z = (-c[:, 0] * sn + c[:, 2] * cs) * sc
                y = c[:, 1] + move * s
                layers.append(np.stack([x, y, z], axis=1))
            pts3 = np.vstack(layers)
            grid = np.arange(ncols * count).reshape(ncols, count)
            polys = _skin(grid, closed, wrap)
            reverse = _flux_flip(pts3, polys)
            if reverse:
                polys = [q[::-1] for q in polys]
            if closed and not wrap:
                polys.extend(_ring_cap(pts3, list(grid[0]), reverse))
                polys.extend(_ring_cap(pts3, list(grid[-1]), not reverse))
            out.add(pts3, polys)
    return out.mesh()


def _path_samples(path: np.ndarray, closed: bool, g0: float, g1: float):
    loop = np.vstack([path, path[:1]]) if closed else path
    seg = np.linalg.norm(np.diff(loop, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total < 1e-9 or g1 - g0 < 1e-6:
        return None
    if closed and g0 <= 1e-9 and g1 >= 1.0 - 1e-9:
        return path.copy(), cum[:-1] / total, True
    a, b = g0 * total, g1 * total
    arcs = np.array([a] + [c for c in cum if a + 1e-9 < c < b - 1e-9] + [b])
    pos = np.stack([np.interp(arcs, cum, loop[:, d]) for d in range(3)], axis=1)
    return pos, (arcs - a) / (b - a), False


def _tangents(Q: np.ndarray, wrap: bool) -> np.ndarray:
    if wrap:
        d = _unit(np.roll(Q, -1, axis=0) - Q)
        t = _unit(d + np.roll(d, 1, axis=0))
        bad = np.linalg.norm(t, axis=1) < 1e-9
        t[bad] = d[bad]
        return t
    d = _unit(Q[1:] - Q[:-1])
    t = np.empty_like(Q)
    t[0] = d[0]
    t[-1] = d[-1]
    if len(Q) > 2:
        mid = _unit(d[:-1] + d[1:])
        bad = np.linalg.norm(mid, axis=1) < 1e-9
        mid[bad] = d[1:][bad]
        t[1:-1] = mid
    return t


def _transport(r, x0, x1, t0, t1):
    v1 = x1 - x0
    c1 = float(v1 @ v1)
    if c1 < 1e-18:
        return r
    rl = r - (2.0 / c1) * float(v1 @ r) * v1
    tl = t0 - (2.0 / c1) * float(v1 @ t0) * v1
    v2 = t1 - tl
    c2 = float(v2 @ v2)
    if c2 < 1e-18:
        return rl
    return rl - (2.0 / c2) * float(v2 @ rl) * v2


def _rotate(v: np.ndarray, axis: np.ndarray, ang: float) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    return v * c + np.cross(axis, v) * s + axis * float(axis @ v) * (1.0 - c)


def _frames(Q: np.ndarray, T: np.ndarray, wrap: bool) -> tuple[np.ndarray, np.ndarray]:
    m = len(Q)
    N = np.zeros((m, 3))
    t0 = T[0]
    ref = np.array([0.0, 0.0, 1.0]) if abs(t0[2]) < 0.99 else np.array([0.0, 1.0, 0.0])
    N[0] = _unit(ref - (ref @ t0) * t0)
    for i in range(m - 1):
        N[i + 1] = _unit(_transport(N[i], Q[i], Q[i + 1], T[i], T[i + 1]))
    if wrap:
        end = _transport(N[m - 1], Q[m - 1], Q[0], T[m - 1], T[0])
        ang = math.atan2(float(np.cross(end, N[0]) @ T[0]), float(end @ N[0]))
        for i in range(m):
            N[i] = _rotate(N[i], T[i], ang * i / m)
    return N, np.cross(T, N)


def build_sweep(p: dict, inputs: list) -> Mesh:
    if len(inputs) < 2 or not inputs[0].is_spline or not inputs[1].is_spline:
        return Mesh.empty()
    cch, pch = inputs[0].chains(), inputs[1].chains()
    if not cch or not pch:
        return Mesh.empty()
    path = _clean(*pch[0])
    if path is None:
        return Mesh.empty()
    shapes = []
    for pts, closed in cch:
        c = _clean(pts, closed)
        if c is not None:
            shapes.append([c, closed])
    if not shapes:
        return Mesh.empty()
    sampled = _path_samples(path, pch[0][1], float(p["start_growth"]) / 100.0,
                            float(p["end_growth"]) / 100.0)
    if sampled is None:
        return Mesh.empty()
    Q, S, wrap = sampled
    if len(Q) < 2:
        return Mesh.empty()
    closed_ids = [i for i, (_, closed) in enumerate(shapes) if closed]
    info = {i: (0, None) for i in closed_ids}
    if len(closed_ids) > 1:
        flat = [shapes[i][0][:, :2] for i in closed_ids]
        nest = _nesting(flat)
        for k, i in enumerate(closed_ids):
            depth, parent = nest[k]
            if (depth % 2 == 0) != (_area2(flat[k]) > 0):
                shapes[i][0] = shapes[i][0][::-1].copy()
            info[i] = (depth, None if parent is None else closed_ids[parent])
    T = _tangents(Q, wrap)
    N, B = _frames(Q, T, wrap)
    end_scale = float(p["end_scale"]) / 100.0
    rot = float(p["end_rotation"])
    chunks = []
    grids = []
    polys: list[tuple[int, ...]] = []
    base = 0
    for contour, closed in shapes:
        layers = []
        for i in range(len(Q)):
            s = float(S[i])
            a = math.radians(rot) * s
            ca, sa = math.cos(a), math.sin(a)
            x = contour[:, 0] * ca - contour[:, 1] * sa
            y = contour[:, 0] * sa + contour[:, 1] * ca
            sc = 1.0 + (end_scale - 1.0) * s
            layers.append(Q[i] + sc * (x[:, None] * N[i] + y[:, None] * B[i]
                                       + contour[:, 2:3] * T[i]))
        chunks.append(np.vstack(layers))
        grid = base + np.arange(len(Q) * len(contour)).reshape(len(Q), len(contour))
        grids.append(grid)
        base += len(Q) * len(contour)
        polys.extend(_skin(grid, closed, wrap))
    pts3 = np.vstack(chunks)
    if p["caps"] and not wrap:
        for o in closed_ids:
            depth, _ = info[o]
            if depth % 2:
                continue
            holes = [h for h in closed_ids if info[h] == (depth + 1, o)]
            first, last = list(grids[o][0]), list(grids[o][-1])
            polys.extend(_cap(pts3, first, [list(grids[h][0]) for h in holes],
                              -_newell(pts3[first])))
            polys.extend(_cap(pts3, last, [list(grids[h][-1]) for h in holes],
                              _newell(pts3[last])))
    out = _Out()
    out.add(pts3, polys)
    return out.mesh(orient_volume=True)


def _resample(pts: np.ndarray, closed: bool, count: int, corners: bool) -> np.ndarray:
    loop = np.vstack([pts, pts[:1]]) if closed else pts
    seg = np.linalg.norm(np.diff(loop, axis=0), axis=1)
    total = float(seg.sum())
    if total < 1e-9:
        return np.repeat(pts[:1], count, axis=0)
    nseg = len(seg)
    if corners and count >= len(pts):
        extras = count - len(pts)
        ideal = extras * seg / total
        base = np.floor(ideal).astype(int)
        left = extras - int(base.sum())
        order = np.argsort(-(ideal - base), kind="stable")
        for k in order[:left]:
            base[k] += 1
        out = []
        for i in range(nseg):
            a, b = loop[i], loop[i + 1]
            out.append(a)
            for q in range(1, base[i] + 1):
                out.append(a + (b - a) * (q / (base[i] + 1)))
        if not closed:
            out.append(loop[-1])
        return np.array(out)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if closed:
        ts = np.arange(count) * total / count
    else:
        ts = np.linspace(0.0, total, count)
    return np.stack([np.interp(ts, cum, loop[:, d]) for d in range(3)], axis=1)


def _catmull(p0, p1, p2, p3, t: float) -> np.ndarray:
    return 0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                  + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t ** 3)


def build_loft(p: dict, inputs: list) -> Mesh:
    raw = []
    for inp in inputs:
        if not inp.is_spline:
            continue
        chains = inp.chains()
        if chains:
            pts = _clean(*chains[0])
            if pts is not None:
                raw.append((pts, chains[0][1]))
    if len(raw) < 2:
        return Mesh.empty()
    closed = all(c for _, c in raw)
    shapes = []
    for pts, c in raw:
        if c and not closed:
            pts = np.vstack([pts, pts[:1]])
        shapes.append(pts)
    ucount = int(p["subdivision_u"])
    vcount = int(p["subdivision_v"])
    loop = bool(p["loop"]) and len(shapes) > 2
    count = ucount if closed else ucount + 1
    corners = all(len(s) <= count for s in shapes)
    secs = [_resample(s, closed, count, corners) for s in shapes]
    for k in range(1, len(secs)):
        prev, cur = secs[k - 1], secs[k]
        if closed:
            if float(_newell(cur) @ _newell(prev)) < 0:
                cur = np.vstack([cur[:1], cur[:0:-1]])
            best, shift = None, 0
            for sh in range(count):
                cost = float(np.sum((np.roll(cur, -sh, axis=0) - prev) ** 2))
                if best is None or cost < best - 1e-12:
                    best, shift = cost, sh
            cur = np.roll(cur, -shift, axis=0)
        else:
            same = np.linalg.norm(cur[0] - prev[0]) + np.linalg.norm(cur[-1] - prev[-1])
            swap = np.linalg.norm(cur[-1] - prev[0]) + np.linalg.norm(cur[0] - prev[-1])
            if swap < same:
                cur = cur[::-1].copy()
        secs[k] = cur
    K = len(secs)
    layers = []
    pairs = K if loop else K - 1
    for k in range(pairs):
        p1, p2 = secs[k], secs[(k + 1) % K]
        if loop:
            p0, p3 = secs[(k - 1) % K], secs[(k + 2) % K]
        else:
            p0 = secs[k - 1] if k > 0 else 2.0 * p1 - p2
            p3 = secs[k + 2] if k + 2 < K else 2.0 * p2 - p1
        for j in range(vcount):
            layers.append(_catmull(p0, p1, p2, p3, j / vcount))
    if not loop:
        layers.append(secs[-1])
    pts3 = np.vstack(layers)
    grid = np.arange(len(layers) * count).reshape(len(layers), count)
    polys = _skin(grid, closed, loop)
    side = sum(float(np.linalg.norm(_newell(pts3[list(q)]))) for q in polys) * 0.5
    extent = float(np.ptp(pts3, axis=0).max())
    if side <= 1e-9 * max(1.0, extent * extent):
        return Mesh.empty()
    if p["caps"] and closed and not loop:
        polys.extend(_ring_cap(pts3, list(grid[0]), False))
        polys.extend(_ring_cap(pts3, list(grid[-1]), True))
    out = _Out()
    out.add(pts3, polys)
    return out.mesh(orient_volume=True)


def text_chains(p: dict) -> list[np.ndarray]:
    text = str(p["text"])
    height = float(p["height"])
    if not text.strip() or height <= 0:
        return []
    ref = 1000.0
    font = QFont(str(p["font"]) or "Arial")
    font.setPixelSize(int(ref))
    spacing = float(p["horizontal_spacing"])
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing * ref / height)
    metrics = QFontMetricsF(font)
    s = height / ref
    fine = 4.0
    matrix = QTransform.fromScale(fine * s, -fine * s)
    out: list[np.ndarray] = []
    for row, line in enumerate(text.split("\n")):
        if not line.strip():
            continue
        path = QPainterPath()
        path.addText(0.0, 0.0, font, line)
        advance = metrics.horizontalAdvance(line)
        shift = {"Left": 0.0, "Middle": -advance / 2.0, "Right": -advance}.get(str(p["align"]), 0.0)
        down = row * (metrics.lineSpacing() * s + float(p["vertical_spacing"]))
        for poly in path.toSubpathPolygons(matrix):
            pts = np.array([(poly.at(i).x(), poly.at(i).y()) for i in range(poly.size())], float)
            if len(pts) < 3:
                continue
            ring = _clean(np.column_stack([pts[:, 0] / fine + shift * s, pts[:, 1] / fine - down,
                                           np.zeros(len(pts))]), True)
            if ring is not None:
                out.append(ring)
    return out


def build_text_spline(p: dict, _inputs: list) -> Mesh:
    rings = text_chains(p)
    if not rings:
        return Mesh.empty()
    pts = np.vstack(rings)
    edges = []
    base = 0
    for r in rings:
        n = len(r)
        edges.extend((base + i, base + (i + 1) % n) for i in range(n))
        base += n
    return Mesh(pts, [], edges)


def build_text(p: dict, _inputs: list) -> Mesh:
    depth = float(p["depth"])
    rings = text_chains(p)
    if not rings or depth <= 0:
        return Mesh.empty()
    return _extrude_chains([[(r, True) for r in rings]], (0.0, 0.0, depth), 1, True, True)


def _text_params() -> tuple:
    return (
        Param("text", "Text", "text", "Text", group="Object"),
        Param("height", "Height", "distance", 200.0, minimum=0.0, group="Object"),
        Param("font", "Font", "text", "Arial", group="Object"),
        Param("horizontal_spacing", "Horizontal Spacing", "distance", 0.0, group="Object"),
        Param("vertical_spacing", "Vertical Spacing", "distance", 0.0, group="Object"),
        Param("align", "Align", "choice", "Left", choices=ALIGNS, group="Object"),
    )


register(ObjectSpec(
    id="extrude", label="Extrude", category="generator", build=build_extrude, inputs="children",
    params=(
        Param("movement", "Movement", "vector", (0.0, 0.0, 20.0), group="Object"),
        Param("subdivision", "Subdivision", "int", 1, minimum=1, maximum=1000, group="Object"),
        Param("start_cap", "Start Cap", "bool", True, group="Caps"),
        Param("end_cap", "End Cap", "bool", True, group="Caps"),
        Param("hierarchical", "Hierarchical", "bool", False, group="Object"),
    ),
    icon="extrude"))

register(ObjectSpec(
    id="lathe", label="Lathe", category="generator", build=build_lathe, inputs="children",
    params=(
        Param("angle", "Angle", "angle", 360.0, minimum=-360.0, maximum=360.0, group="Object"),
        Param("subdivision", "Subdivision", "int", 32, minimum=3, maximum=1000, group="Object"),
        Param("movement", "Movement", "distance", 0.0, group="Object"),
        Param("scale", "Scale", "percent", 100.0, minimum=0.0, maximum=10000.0, unit="%",
              group="Object"),
    ),
    icon="lathe"))

register(ObjectSpec(
    id="sweep", label="Sweep", category="generator", build=build_sweep, inputs="children",
    params=(
        Param("end_scale", "End Scale", "percent", 100.0, minimum=0.0, maximum=10000.0, unit="%",
              group="Object"),
        Param("end_rotation", "End Rotation", "angle", 0.0, minimum=-36000.0, maximum=36000.0,
              group="Object"),
        Param("start_growth", "Start Growth", "percent", 0.0, minimum=0.0, maximum=100.0, unit="%",
              group="Object"),
        Param("end_growth", "End Growth", "percent", 100.0, minimum=0.0, maximum=100.0, unit="%",
              group="Object"),
        Param("caps", "Caps", "bool", True, group="Caps"),
    ),
    icon="sweep"))

register(ObjectSpec(
    id="loft", label="Loft", category="generator", build=build_loft, inputs="children",
    params=(
        Param("subdivision_u", "Mesh Subdivision U", "int", 30, minimum=3, maximum=1000,
              group="Object"),
        Param("subdivision_v", "Mesh Subdivision V", "int", 10, minimum=1, maximum=500,
              group="Object"),
        Param("loop", "Loop", "bool", False, group="Object"),
        Param("caps", "Caps", "bool", True, group="Caps"),
    ),
    icon="loft"))

register(ObjectSpec(
    id="text_spline", label="Text Spline", category="spline", build=build_text_spline,
    params=_text_params(), icon="text"))

register(ObjectSpec(
    id="text", label="Text", category="mesh", build=build_text,
    params=_text_params() + (Param("depth", "Depth", "distance", 20.0, minimum=0.0, group="Object"),),
    icon="text"))
