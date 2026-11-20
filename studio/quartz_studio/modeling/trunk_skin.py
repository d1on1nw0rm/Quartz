from __future__ import annotations

import heapq
import math
from typing import Sequence

import numpy as np

__all__ = ["profile_radii", "build_skin"]

_TINY = 1e-6
_INTERIOR_MIN = 1e-3
_FOLD_MARGIN = 0.02
_MIN_SETBACK = 0.5
_SHARP_COS = -0.6
_STRETCH_MAX = 2.0
_END_BUDGET = 0.85
_PAIR_BUDGET = 0.9
_MITRE_GAP = 0.1
_COPLANAR = 1e-9
_MAX_SWEEPS = 400
_ANG_REL = 0.1
_ANG_ABS = 0.02
_GROW = 1.15
_FACING = 0.3
_ANCHORS = np.array([(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)
                     if (x, y, z) != (0, 0, 0)], dtype=float)
_ANCHORS = _ANCHORS / np.linalg.norm(_ANCHORS, axis=1)[:, None]


def _unique_edges(edges, n: int) -> np.ndarray:
    if edges is None:
        return np.zeros((0, 2), dtype=np.int64)
    e = np.asarray(list(edges) if not isinstance(edges, np.ndarray) else edges, dtype=np.int64)
    if e.size == 0 or n == 0:
        return np.zeros((0, 2), dtype=np.int64)
    e = e.reshape(-1, 2)
    ok = (e[:, 0] != e[:, 1]) & (e.min(axis=1) >= 0) & (e.max(axis=1) < n)
    e = np.sort(e[ok], axis=1)
    if len(e) == 0:
        return e
    return np.unique(e, axis=0)


def profile_radii(points, edges, base: float, tip: float, taper: float = 1.0,
                  root: str = "first", scales=None) -> np.ndarray:
    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    n = len(pts)
    out = np.zeros(n)
    e = _unique_edges(edges, n)
    if len(e) == 0:
        return out
    lengths = np.linalg.norm(pts[e[:, 1]] - pts[e[:, 0]], axis=1)
    lengths = np.where(np.isfinite(lengths), lengths, 0.0)
    adj: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    for (a, b), w in zip(e.tolist(), lengths.tolist()):
        adj[a].append((b, w))
        adj[b].append((a, w))
    t = np.zeros(n)
    used = np.zeros(n, dtype=bool)
    seen = np.zeros(n, dtype=bool)
    for start in range(n):
        if seen[start] or not adj[start]:
            continue
        comp = []
        stack = [start]
        seen[start] = True
        while stack:
            p = stack.pop()
            comp.append(p)
            for q, _ in adj[p]:
                if not seen[q]:
                    seen[q] = True
                    stack.append(q)
        comp.sort()
        ends = [p for p in comp if len(adj[p]) == 1]
        if root == "lowest":
            r0 = min(ends or comp, key=lambda p: (float(pts[p, 1]), p))
        else:
            r0 = ends[0] if ends else comp[0]
        dist = {r0: 0.0}
        parent = {r0: -1}
        order = []
        done = set()
        heap = [(0.0, r0)]
        while heap:
            d, p = heapq.heappop(heap)
            if p in done:
                continue
            done.add(p)
            order.append(p)
            for q, w in adj[p]:
                nd = d + w
                if q not in done and (q not in dist or nd < dist[q]):
                    dist[q] = nd
                    parent[q] = p
                    heapq.heappush(heap, (nd, q))
        down = {p: 0.0 for p in order}
        for p in reversed(order):
            par = parent[p]
            if par >= 0:
                down[par] = max(down[par], down[p] + dist[p] - dist[par])
        for p in order:
            total = dist[p] + down[p]
            t[p] = dist[p] / total if total > 0.0 else 0.0
            used[p] = True
    t = np.clip(t, 0.0, 1.0)
    k = max(float(taper), 1e-6)
    rad = float(tip) + (float(base) - float(tip)) * (1.0 - t) ** k
    if scales is not None:
        s = np.ones(n)
        given = np.asarray(scales, dtype=float).reshape(-1)
        m = min(n, len(given))
        s[:m] = given[:m]
        rad = rad * s
    out[used] = rad[used]
    return out


def _cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a0, a1, a2 = a[..., 0], a[..., 1], a[..., 2]
    b0, b1, b2 = b[..., 0], b[..., 1], b[..., 2]
    return np.stack([a1 * b2 - a2 * b1, a2 * b0 - a0 * b2, a0 * b1 - a1 * b0], axis=-1)


def _unit(v: np.ndarray) -> np.ndarray:
    ln = float(np.linalg.norm(v))
    return v / ln if ln > 0.0 else v


def _perp(t: np.ndarray) -> np.ndarray:
    a = np.zeros(3)
    a[int(np.argmin(np.abs(t)))] = 1.0
    u = a - t * float(a @ t)
    return u / float(np.linalg.norm(u))


def _transport(u: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    c = float(a @ b)
    axis = _cross(a, b)
    s = float(np.linalg.norm(axis))
    if s > 1e-12:
        k = axis / s
        u = u * c + _cross(k, u) * s + k * float(k @ u) * (1.0 - c)
    u = u - b * float(u @ b)
    return u / float(np.linalg.norm(u))


def _rotate(u: np.ndarray, k: np.ndarray, angle: float) -> np.ndarray:
    c = math.cos(angle)
    s = math.sin(angle)
    return u * c + _cross(k, u) * s + k * float(k @ u) * (1.0 - c)


def _hull(X: np.ndarray, eps: float):
    k = len(X)
    if k < 4:
        return None
    i0 = int(np.lexsort((X[:, 2], X[:, 1], X[:, 0]))[0])
    rel = X - X[i0]
    d1 = np.linalg.norm(rel, axis=1)
    i1 = int(np.argmax(d1))
    if d1[i1] <= eps:
        return None
    a = rel[i1] / d1[i1]
    d2 = np.linalg.norm(rel - np.outer(rel @ a, a), axis=1)
    i2 = int(np.argmax(d2))
    if d2[i2] <= eps:
        return None
    nrm = _unit(_cross(rel[i1], rel[i2]))
    d3 = rel @ nrm
    i3 = int(np.argmax(np.abs(d3)))
    if abs(d3[i3]) <= eps:
        return None
    cap = 64 + 16 * k
    NN = np.zeros((cap, 3))
    OFF = np.zeros(cap)
    alive = np.zeros(cap, dtype=bool)
    faces: list[tuple[int, int, int]] = []
    edge: dict[tuple[int, int], int] = {}
    area_eps = eps * eps

    def add(tris):
        nonlocal NN, OFF, alive
        T = np.asarray(tris, dtype=np.int64)
        nv = _cross(X[T[:, 1]] - X[T[:, 0]], X[T[:, 2]] - X[T[:, 0]])
        ln = np.linalg.norm(nv, axis=1)
        if np.any(ln <= area_eps):
            return False
        nv = nv / ln[:, None]
        start = len(faces)
        need = start + len(tris)
        if need > len(OFF):
            grow = max(need, 2 * len(OFF))
            NN = np.vstack([NN, np.zeros((grow - len(OFF), 3))])
            OFF = np.concatenate([OFF, np.zeros(grow - len(OFF))])
            alive = np.concatenate([alive, np.zeros(grow - len(alive), dtype=bool)])
        NN[start:need] = nv
        OFF[start:need] = np.einsum("ij,ij->i", nv, X[T[:, 0]])
        alive[start:need] = True
        for j, (p, q, r) in enumerate(tris):
            f = start + j
            faces.append((p, q, r))
            edge[(p, q)] = f
            edge[(q, r)] = f
            edge[(r, p)] = f
        return True

    simplex = [i0, i1, i2, i3]
    tet = []
    for opp in range(4):
        tri = [simplex[j] for j in range(4) if j != opp]
        p, q, r = tri
        nv = _cross(X[q] - X[p], X[r] - X[p])
        if float(nv @ (X[simplex[opp]] - X[p])) > 0.0:
            q, r = r, q
        tet.append((p, q, r))
    if not add(tet):
        return None
    taken = set(simplex)
    for i in range(k):
        if i in taken:
            continue
        nf = len(faces)
        dist = NN[:nf] @ X[i] - OFF[:nf]
        vis = alive[:nf] & (dist > eps)
        vidx = np.flatnonzero(vis).tolist()
        if not vidx:
            continue
        visset = set(vidx)
        horizon = []
        for f in vidx:
            p, q, r = faces[f]
            for e0, e1 in ((p, q), (q, r), (r, p)):
                if edge.get((e1, e0)) not in visset:
                    horizon.append((e0, e1))
        for f in vidx:
            alive[f] = False
            p, q, r = faces[f]
            for key in ((p, q), (q, r), (r, p)):
                if edge.get(key) == f:
                    del edge[key]
        nxt = {}
        for e0, e1 in horizon:
            if e0 in nxt:
                return None
            nxt[e0] = e1
        cur = horizon[0][0]
        steps = 0
        while True:
            cur = nxt.get(cur)
            steps += 1
            if cur is None or steps > len(horizon):
                return None
            if cur == horizon[0][0]:
                break
        if steps != len(horizon):
            return None
        if not add([(e0, e1, i) for e0, e1 in horizon]):
            return None
    return [faces[f] for f in range(len(faces)) if alive[f]]


def _pair_quads(X: np.ndarray, tris: list[tuple[int, int, int]]) -> list[tuple[int, ...]]:
    if not tris:
        return []
    T = np.asarray(tris, dtype=np.int64)
    N = _cross(X[T[:, 1]] - X[T[:, 0]], X[T[:, 2]] - X[T[:, 0]])
    N = N / np.linalg.norm(N, axis=1)[:, None]
    owner = {}
    for i, (a, b, c) in enumerate(tris):
        owner[(a, b)] = i
        owner[(b, c)] = i
        owner[(c, a)] = i
    used = [False] * len(tris)
    out: list[tuple[int, ...]] = []
    for i, (a, b, c) in enumerate(tris):
        if used[i]:
            continue
        used[i] = True
        merged = None
        for e0, e1, opp in ((a, b, c), (b, c, a), (c, a, b)):
            j = owner.get((e1, e0))
            if j is None or used[j]:
                continue
            if float(N[i] @ N[j]) < 1.0 - _COPLANAR:
                continue
            d = [x for x in tris[j] if x != e0 and x != e1][0]
            quad = (e0, d, e1, opp)
            if _convex(X, quad, N[i]):
                used[j] = True
                merged = quad
                break
        out.append(merged if merged is not None else (a, b, c))
    return out


def _convex(X: np.ndarray, poly: tuple[int, ...], nrm: np.ndarray) -> bool:
    m = len(poly)
    for k in range(m):
        p0 = X[poly[k]]
        p1 = X[poly[(k + 1) % m]]
        p2 = X[poly[(k + 2) % m]]
        e1 = p1 - p0
        e2 = p2 - p1
        cr = float(_cross(e1, e2) @ nrm)
        if cr <= 1e-6 * float(np.linalg.norm(e1)) * float(np.linalg.norm(e2)):
            return False
    return True


class _Station:
    __slots__ = ("kind", "c", "n", "t", "r", "key", "t2")

    def __init__(self, kind, c, n, t, r, key, t2=None):
        self.kind = kind
        self.c = c
        self.n = n
        self.t = t
        self.r = r
        self.key = key
        self.t2 = t2


def _ring_max(st: _Station, c: np.ndarray, nrm: np.ndarray) -> float:
    const = float((st.c - c) @ nrm)
    if st.kind == "apex":
        return const
    w = nrm - st.n * (float(st.t @ nrm) / float(st.t @ st.n))
    w = w - st.t * float(w @ st.t)
    return const + st.r * float(np.linalg.norm(w))


class _Skin:
    def __init__(self, P: np.ndarray, E: np.ndarray, R: np.ndarray, sides: int, caps: bool):
        self.sides = sides
        self.caps = caps
        n = len(P)
        adj: list[list[int]] = [[] for _ in range(n)]
        for a, b in E.tolist():
            adj[a].append(b)
            adj[b].append(a)
        comp = [-1] * n
        rmax = []
        for s in range(n):
            if comp[s] >= 0 or not adj[s]:
                continue
            cid = len(rmax)
            comp[s] = cid
            stack = [s]
            best = 0.0
            while stack:
                p = stack.pop()
                best = max(best, float(R[p]))
                for q in adj[p]:
                    if comp[q] < 0:
                        comp[q] = cid
                        stack.append(q)
            rmax.append(best)
        keep = [a for a in range(len(E)) if rmax[comp[E[a, 0]]] >= _TINY]
        E = E[keep]
        adj = [[] for _ in range(n)]
        for a, b in E.tolist():
            adj[a].append(b)
            adj[b].append(a)
        for lst in adj:
            lst.sort()
        self.P = P
        self.adj = adj
        self.deg = [len(x) for x in adj]
        floor = np.array([_INTERIOR_MIN * rmax[comp[v]] if comp[v] >= 0 else 0.0 for v in range(n)])
        self.floor = floor
        self.rint = np.maximum(R, floor)
        self.apex = [self.deg[v] == 1 and float(R[v]) < _TINY for v in range(n)]
        used = [v for v in range(n) if self.deg[v]]
        if used:
            up = P[used]
            self.scale = max(float(np.linalg.norm(up.max(axis=0) - up.min(axis=0))), float(np.max(R[used])), 1e-12)
        else:
            self.scale = 1.0
        self.n = n
        self.hub = [False] * n
        self.core = [False] * n
        self.parent = list(range(n))
        self.members: dict[int, list[int]] = {}
        self.sol: dict[int, tuple] = {}
        self.octa: set[int] = set()
        self.dead: set[int] = set()
        self.dirty: set[int] = set()
        ang = 2.0 * math.pi * np.arange(sides) / sides
        self.cos = np.cos(ang)
        self.sin = np.sin(ang)
        fine = 2.0 * math.pi * np.arange(24) / 24
        self.cs = np.cos(fine)
        self.sn = np.sin(fine)
        for v in range(n):
            d = self.deg[v]
            if d >= 3 or (d == 2 and self._sharp(v)):
                self._make_hub(v)
                self.core[v] = True
        self.dirty = set(self.members)

    def _find(self, v: int) -> int:
        while self.parent[v] != v:
            self.parent[v] = self.parent[self.parent[v]]
            v = self.parent[v]
        return v

    def _make_hub(self, v: int) -> None:
        if not self.hub[v]:
            self.hub[v] = True
            self.parent[v] = v
            self.members[v] = [v]

    def _union(self, a: int, b: int) -> int:
        self._make_hub(a)
        self._make_hub(b)
        ra = self._find(a)
        rb = self._find(b)
        if ra == rb:
            return ra
        root, other = min(ra, rb), max(ra, rb)
        self.parent[other] = root
        self.members[root] = sorted(self.members[root] + self.members.pop(other))
        self.sol.pop(other, None)
        if other in self.octa:
            self.octa.discard(other)
            self.octa.add(root)
        return root

    def _touch(self, root: int) -> None:
        self.dirty.add(root)
        for u in self.members[root]:
            for w in self.adj[u]:
                if self.hub[w]:
                    self.dirty.add(self._find(w))

    def _budget(self, u: int, v: int, L: float) -> float:
        if self.hub[v]:
            return _PAIR_BUDGET * L
        if self.deg[v] == 1:
            return _END_BUDGET * L
        a, b = self.adj[v]
        w = b if a == u else a
        t1 = _unit(self.P[v] - self.P[u])
        t2 = _unit(self.P[w] - self.P[v])
        c = float(t1 @ t2)
        half = math.sqrt(max(0.0, (1.0 - c) / max(1.0 + c, 1e-12)))
        sin_half = math.sqrt(max(0.0, (1.0 - c) * 0.5))
        ext = float(self.rint[v]) * min(half, _STRETCH_MAX * sin_half)
        return (1.0 - _MITRE_GAP) * L - ext

    def _statics(self, root: int):
        circles = []
        pts = []
        for u in self.members[root]:
            if self.deg[u] == 1:
                w = self.adj[u][0]
                nrm = _unit(self.P[u] - self.P[w])
                if self.apex[u]:
                    pts.append(self.P[u])
                else:
                    circles.append((self.P[u], nrm, float(self.rint[u])))
            elif self.deg[u] == 2 and root not in self.octa and not self._sharp(u):
                circles.append((self.P[u], self._bisector(u), float(self.rint[u])))
            elif self.deg[u] == 2 or root in self.octa:
                pts.extend(self._octa(u))
        return circles, pts

    def _bisector(self, u: int) -> np.ndarray:
        a, b = self.adj[u]
        return _unit(_unit(self.P[u] - self.P[a]) + _unit(self.P[b] - self.P[u]))

    def _sharp(self, u: int) -> bool:
        a, b = self.adj[u]
        return float(_unit(self.P[u] - self.P[a]) @ _unit(self.P[b] - self.P[u])) < _SHARP_COS

    def _octa(self, u: int) -> list[np.ndarray]:
        r = float(self.rint[u])
        if self.deg[u] == 2:
            a, b = self.adj[u]
            t1 = _unit(self.P[u] - self.P[a])
            t2 = _unit(self.P[b] - self.P[u])
            n = t1 + t2
            n = _unit(n) if float(np.linalg.norm(n)) > 1e-6 else _perp(t2)
            bd = t2 - t1
            bd = bd - n * float(bd @ n)
            bd = _unit(bd) if float(np.linalg.norm(bd)) > 1e-6 else _perp(n)
            axes = [n, bd, _cross(n, bd)]
        else:
            axes = list(np.eye(3))
        out = []
        for ax in axes:
            for sgn in (1.0, -1.0):
                out.append(self.P[u] + sgn * r * ax)
        return out

    def _solve(self, root: int):
        mem = self.members[root]
        memset = set(mem)
        exits = [(u, w) for u in mem for w in self.adj[u] if w not in memset]
        if not exits:
            circles, pts = self._statics(root)
            self.sol[root] = ([], None, None, None, None)
            if root not in self.octa and self._degenerate([], circles, pts):
                self.octa.add(root)
                return self._solve(root)
            return None
        O = self._center(root)
        us = [u for u, _ in exits]
        U = self.P[us]
        V = self.P[[v for _, v in exits]]
        L = np.linalg.norm(V - U, axis=1)
        D = (V - U) / L[:, None]
        Ru = self.rint[us]
        Rv = np.array([0.0 if self.apex[v] else float(self.rint[v]) for _, v in exits])
        fl = self.floor[us]
        budget = np.array([self._budget(u, v, float(L[k])) for k, (u, v) in enumerate(exits)])
        k = len(exits)
        core = np.array([self.core[u] for u in us])
        s = np.where(core, _MIN_SETBACK * Ru, 0.05 * L)
        diag = np.eye(k, dtype=bool)
        if k > 1:
            ang = np.arccos(np.clip(D @ D.T, -1.0, 1.0))
            ang[diag] = np.inf
            est = ((Ru[:, None] + Ru[None, :]) * 1.15 / np.maximum(ang, 1e-3)).max(axis=1, initial=0.0, where=~diag)
            s = np.where(core, np.maximum(s, np.minimum(est, 0.95 * budget)), s)
        converged = False
        grow = np.zeros(k, dtype=bool)
        for _ in range(_MAX_SWEEPS):
            r = np.maximum(Ru + (Rv - Ru) * s / L, fl)
            C = U + s[:, None] * D
            a, beta, valid = self._caps(C, D, r, O)
            grow = ~valid
            if k > 1:
                A = np.arccos(np.clip(a @ a.T, -1.0, 1.0))
                bs = beta[:, None] + beta[None, :]
                bad = (A < bs * (1.0 + _ANG_REL) + _ANG_ABS) & ~diag
                bad &= beta[:, None] >= 0.8 * beta[None, :]
                grow |= bad.any(axis=1)
            if not grow.any():
                converged = True
                break
            s = np.where(grow, s * _GROW + 0.02 * r, s)
            if np.any(s > budget):
                break
        if not converged:
            ratio = np.where(budget > 0.0, s / np.maximum(budget, 1e-300), np.inf)
            ratio = np.where(grow | (s > budget), ratio, -np.inf)
            return exits[int(np.argmax(ratio))]
        r = np.maximum(Ru + (Rv - Ru) * s / L, fl)
        C = U + s[:, None] * D
        self.sol[root] = (exits, s, C, D, r)
        return None

    def _center(self, root: int) -> np.ndarray:
        mem = self.members[root]
        core = [u for u in mem if self.core[u]] or mem
        return self.P[core].mean(axis=0)

    def _caps(self, C: np.ndarray, D: np.ndarray, r: np.ndarray, O: np.ndarray):
        k = len(C)
        ax = np.zeros((k, 3))
        ax[np.arange(k), np.argmin(np.abs(D), axis=1)] = 1.0
        E1 = ax - D * np.einsum("ij,ij->i", ax, D)[:, None]
        E1 = E1 / np.linalg.norm(E1, axis=1)[:, None]
        E2 = _cross(D, E1)
        Q = C[:, None, :] + r[:, None, None] * (self.cs[None, :, None] * E1[:, None, :] + self.sn[None, :, None] * E2[:, None, :])
        Vc = C - O
        dist = np.linalg.norm(Vc, axis=1)
        a = Vc / np.maximum(dist, 1e-300)[:, None]
        W = Q - O
        wn = np.linalg.norm(W, axis=2)
        cosb = np.einsum("kmj,kj->km", W, a) / np.maximum(wn, 1e-300)
        beta = np.arccos(np.clip(cosb.min(axis=1), -1.0, 1.0))
        facing = np.einsum("ij,ij->i", Vc, D) / np.maximum(dist, 1e-300)
        valid = (dist > 1.05 * r) & (facing > _FACING) & (wn.min(axis=1) > 1e-6 * self.scale)
        return a, beta, valid

    def _degenerate(self, rings, circles, pts) -> bool:
        sample = list(pts)
        for c, nn, rr in list(rings) + list(circles):
            u = _perp(nn)
            v = _cross(nn, u)
            sample.extend([c + rr * u, c - rr * u, c + rr * v, c - rr * v])
        if len(sample) < 4:
            return True
        A = np.array(sample)
        A = A - A.mean(axis=0)
        sv = np.linalg.svd(A, compute_uv=False)
        return bool(sv[-1] <= 1e-6 * max(float(sv[0]), 1e-300))

    def _solve_dirty(self) -> None:
        while self.dirty:
            root = min(self.dirty)
            self.dirty.discard(root)
            if not self.hub[root] or self._find(root) != root:
                continue
            res = self._solve(root)
            if res is not None:
                self._touch(self._union(res[0], res[1]))

    def _walk(self, st: list, prev: int, cur: int, visited: set) -> list:
        P = self.P
        while True:
            if self.hub[cur]:
                c, d, r = self.info[(cur, prev)]
                st.append(_Station("hub", c, -d, -d, r, (cur, prev)))
                return st
            if self.deg[cur] == 1:
                t = _unit(P[cur] - P[prev])
                kind = "apex" if self.apex[cur] else "end"
                r = 0.0 if self.apex[cur] else float(self.rint[cur])
                st.append(_Station(kind, P[cur], t, t, r, cur))
                return st
            a, b = self.adj[cur]
            nxt = b if a == prev else a
            t1 = _unit(P[cur] - P[prev])
            t2 = _unit(P[nxt] - P[cur])
            st.append(_Station("mitre", P[cur], _unit(t1 + t2), t1, float(self.rint[cur]), cur, t2))
            visited.add((min(cur, nxt), max(cur, nxt)))
            prev, cur = cur, nxt

    def _limbs(self) -> list:
        info = {}
        for root in sorted(self.members):
            exits, s, C, D, r = self.sol[root]
            for k, key in enumerate(exits):
                info[key] = (C[k], D[k], float(r[k]))
        self.info = info
        P = self.P
        visited: set = set()
        limbs = []
        for u, v in sorted(info):
            key = (min(u, v), max(u, v))
            if key in visited:
                continue
            visited.add(key)
            c, d, r = info[(u, v)]
            limbs.append((self._walk([_Station("hub", c, d, d, r, (u, v))], u, v, visited), False))
        for e in range(self.n):
            if self.deg[e] != 1 or self.hub[e]:
                continue
            w = self.adj[e][0]
            key = (min(e, w), max(e, w))
            if key in visited:
                continue
            visited.add(key)
            t = _unit(P[w] - P[e])
            kind = "apex" if self.apex[e] else "end"
            r = 0.0 if self.apex[e] else float(self.rint[e])
            limbs.append((self._walk([_Station(kind, P[e], t, t, r, e)], e, w, visited), False))
        for v in range(self.n):
            if self.deg[v] != 2 or self.hub[v]:
                continue
            w0 = self.adj[v][0]
            if (min(v, w0), max(v, w0)) in visited:
                continue
            order = [v]
            prev, cur = v, w0
            visited.add((min(v, w0), max(v, w0)))
            while cur != v:
                order.append(cur)
                a, b = self.adj[cur]
                nxt = b if a == prev else a
                visited.add((min(cur, nxt), max(cur, nxt)))
                prev, cur = cur, nxt
            m = len(order)
            st = []
            for i in range(m):
                p0 = order[i - 1]
                p1 = order[i]
                p2 = order[(i + 1) % m]
                t1 = _unit(P[p1] - P[p0])
                t2 = _unit(P[p2] - P[p1])
                st.append(_Station("mitre", P[p1], _unit(t1 + t2), t1, float(self.rint[p1]), p1, t2))
            limbs.append((st, True))
        return limbs

    def _fold(self, limbs) -> bool:
        actions = []
        for st, closed in limbs:
            m = len(st)
            pairs = [(i, i + 1) for i in range(m - 1)]
            if closed:
                pairs.append((m - 1, 0))
            for i, j in pairs:
                A = st[i]
                B = st[j]
                mg = _FOLD_MARGIN * max(A.r, B.r)
                bad = False
                if B.kind != "apex" and _ring_max(A, B.c, B.n) > -mg:
                    bad = True
                if A.kind != "apex" and _ring_max(B, A.c, -A.n) > -mg:
                    bad = True
                if not bad:
                    continue
                if A.kind == "mitre" or B.kind == "mitre":
                    if A.kind == "mitre":
                        actions.append((A.key,))
                    if B.kind == "mitre":
                        actions.append((B.key,))
                else:
                    na = A.key[0] if A.kind == "hub" else A.key
                    nb = B.key[0] if B.kind == "hub" else B.key
                    actions.append((na, nb))
        for act in actions:
            if len(act) == 1:
                if not self.hub[act[0]]:
                    self._make_hub(act[0])
                    self.core[act[0]] = True
                    self._touch(act[0])
            else:
                self._touch(self._union(act[0], act[1]))
        return bool(actions)

    def _ring(self, st: _Station, u: np.ndarray) -> np.ndarray:
        v = _cross(st.t, u)
        Y = st.r * (self.cos[:, None] * u + self.sin[:, None] * v)
        if st.kind == "mitre":
            tn = float(st.t @ st.n)
            Y = Y - np.outer((Y @ st.n) / tn, st.t)
            stretch = 1.0 / tn
            if stretch > _STRETCH_MAX:
                bd = _unit(st.t2 - st.t)
                Y = Y - np.outer((Y @ bd) * (1.0 - _STRETCH_MAX / stretch), bd)
        return st.c + Y

    def _frames(self, st: list, closed: bool) -> list:
        u = _perp(st[0].t)
        frames = [u]
        for i in range(1, len(st)):
            u = _transport(u, st[i - 1].t, st[i].t)
            frames.append(u)
        if closed:
            m = len(st)
            back = _transport(u, st[-1].t, st[0].t)
            t0 = st[0].t
            phi = math.atan2(float(_cross(frames[0], back) @ t0), float(frames[0] @ back))
            for i in range(1, m):
                frames[i] = _rotate(frames[i], st[i].t, -phi * i / m)
        return frames

    def _emit(self, limbs):
        n = self.sides
        blocks: list[np.ndarray] = []
        count = [0]

        def alloc(arr: np.ndarray) -> list[int]:
            ids = list(range(count[0], count[0] + len(arr)))
            blocks.append(arr)
            count[0] += len(arr)
            return ids

        polys: list[tuple[int, ...]] = []
        attach: dict[int, list] = {}
        for st, closed in limbs:
            frames = self._frames(st, closed)
            rings = []
            coords = []
            for s, u in zip(st, frames):
                if s.kind == "apex":
                    pts = s.c[None, :].copy()
                else:
                    pts = self._ring(s, u)
                ids = alloc(pts)
                rings.append(ids)
                coords.append(pts)
                if s.kind == "hub":
                    attach.setdefault(self._find(s.key[0]), []).append((s.key, ids, pts))
            m = len(st)
            pairs = [(i, i + 1) for i in range(m - 1)]
            if closed:
                pairs.append((m - 1, 0))
            for i, j in pairs:
                a = rings[i]
                b = rings[j]
                if st[i].kind == "apex":
                    polys.extend((a[0], b[(q + 1) % n], b[q]) for q in range(n))
                elif st[j].kind == "apex":
                    polys.extend((a[q], a[(q + 1) % n], b[0]) for q in range(n))
                else:
                    polys.extend((a[q], a[(q + 1) % n], b[(q + 1) % n], b[q]) for q in range(n))
            if self.caps and not closed:
                if st[0].kind == "end":
                    polys.append(tuple(reversed(rings[0])))
                if st[-1].kind == "end":
                    polys.append(tuple(rings[-1]))
        failures = []
        for root in sorted(self.members):
            if root in self.dead:
                continue
            res = self._patch(root, sorted(attach.get(root, []), key=lambda x: x[0]), alloc)
            if res[0]:
                polys.extend(res[1])
            else:
                failures.append((root, res[1]))
        failed = bool(failures)
        for root, bad in failures:
            if self._find(root) != root or root not in self.members:
                continue
            exits = self.sol[root][0]
            if bad is None:
                if not exits and root not in self.octa:
                    self.octa.add(root)
                    self._touch(root)
                    continue
                bad = list(exits)
                if not bad:
                    self.dead.add(root)
                    continue
            for u, v in bad:
                self._touch(self._union(u, v))
        if failed:
            return None
        if not polys:
            return np.zeros((0, 3)), []
        coords = np.vstack(blocks)
        used = sorted({i for p in polys for i in p})
        remap = {old: new for new, old in enumerate(used)}
        return coords[used].copy(), [tuple(remap[i] for i in p) for p in polys]

    def _patch(self, root: int, rings: list, alloc):
        if rings:
            return self._patch_star(root, rings, alloc)
        return self._patch_convex(root, alloc)

    def _patch_star(self, root: int, rings: list, alloc):
        O = self._center(root)
        groups = [("attach", ids, pts, key) for key, ids, pts in rings]
        CA = []
        CB = []
        for _, ids, pts, _ in groups:
            a = _unit(pts.mean(axis=0) - O)
            W = pts - O
            cb = (W @ a) / np.linalg.norm(W, axis=1)
            CA.append(a)
            CB.append(math.acos(max(-1.0, min(1.0, float(cb.min())))))
        CA = np.array(CA)
        limit = np.array(CB) * (1.0 + _ANG_REL) + _ANG_ABS
        X0 = np.vstack([g[2] for g in groups]) - O
        dirs = [X0 / np.linalg.norm(X0, axis=1)[:, None]]
        floor = 1e-6 * self.scale

        def clear(pts: np.ndarray, spread: float):
            W = pts - O
            wn = np.linalg.norm(W, axis=1)
            ok = wn > floor
            d = W / np.maximum(wn, 1e-300)[:, None]
            ang = np.arccos(np.clip(d @ CA.T, -1.0, 1.0))
            ok &= (ang > limit[None, :]).all(axis=1)
            near = (d @ np.vstack(dirs).T).max(axis=1)
            ok &= near < math.cos(spread)
            return ok, d

        def star(glist):
            X = np.vstack([g[2] for g in glist])
            W = X - O
            Xp = W / np.linalg.norm(W, axis=1)[:, None]
            faces = _hull(Xp, 1e-10)
            if faces is None:
                return None
            T = np.asarray(faces, dtype=np.int64)
            nv = _cross(Xp[T[:, 1]] - Xp[T[:, 0]], Xp[T[:, 2]] - Xp[T[:, 0]])
            off = np.einsum("ij,ij->i", nv, Xp[T[:, 0]]) / np.linalg.norm(nv, axis=1)
            if float(off.min()) <= 1e-7:
                return None
            return faces, X, Xp, T

        base = star(groups)
        if base is None:
            core = [u for u in self.members[root] if self.core[u]] or self.members[root]
            ra = float(np.mean(self.rint[core]))
            ok, d = clear(O + ra * _ANCHORS, 0.1)
            if not ok.any():
                return False, None
            pts = O + ra * _ANCHORS[ok]
            groups.append(("point", None, pts, -1))
            dirs.append(d[ok])
            base = star(groups)
            if base is None:
                return False, None
        kept = []
        for u in self.members[root]:
            if self.deg[u] == 1:
                if self.apex[u]:
                    pts = self.P[u][None, :].copy()
                    kind = "point"
                else:
                    w = self.adj[u][0]
                    nrm = _unit(self.P[u] - self.P[w])
                    uu = _perp(nrm)
                    vv = _cross(nrm, uu)
                    pts = self.P[u] + float(self.rint[u]) * (self.cos[:, None] * uu + self.sin[:, None] * vv)
                    kind = "cap"
            elif self.deg[u] == 2 and self._sharp(u):
                pts = np.array(self._octa(u))
                kind = "point"
            else:
                continue
            ok, d = clear(pts, 1e-4)
            ok &= self._outside(pts, O, base[1], base[2], base[3])
            if not ok.any():
                continue
            if not ok.all():
                pts = pts[ok]
                d = d[ok]
                kind = "point"
            kept.append((kind, None, pts, u))
            dirs.append(d)
        result = base
        if kept:
            more = star(groups + kept)
            if more is not None:
                groups = groups + kept
                result = more
        final = []
        for kind, ids, pts, key in groups:
            final.append((kind, ids if ids is not None else alloc(pts), pts, key))
        return self._finish(final, result[0], result[1])

    def _outside(self, pts: np.ndarray, O: np.ndarray, X: np.ndarray, Xp: np.ndarray, T: np.ndarray) -> np.ndarray:
        W = pts - O
        wn = np.linalg.norm(W, axis=1)
        d = W / np.maximum(wn, 1e-300)[:, None]
        A = Xp[T[:, 0]]
        B = Xp[T[:, 1]]
        C = Xp[T[:, 2]]
        s1 = d @ _cross(A, B).T
        s2 = d @ _cross(B, C).T
        s3 = d @ _cross(C, A).T
        inside = (s1 >= -1e-12) & (s2 >= -1e-12) & (s3 >= -1e-12)
        nT = _cross(X[T[:, 1]] - X[T[:, 0]], X[T[:, 2]] - X[T[:, 0]])
        num = np.einsum("ij,ij->i", nT, X[T[:, 0]] - O)
        den = d @ nT.T
        t = np.where(den > 1e-300, num[None, :] / np.where(den > 1e-300, den, 1.0), np.inf)
        t = np.where(inside, t, np.inf).min(axis=1)
        return wn > t * (1.0 + 1e-3) + 1e-9 * self.scale

    def _patch_convex(self, root: int, alloc):
        groups = []
        for u in self.members[root]:
            if self.deg[u] == 1:
                w = self.adj[u][0]
                nrm = _unit(self.P[u] - self.P[w])
                if self.apex[u]:
                    pts = self.P[u][None, :].copy()
                    groups.append(("point", alloc(pts), pts, u))
                else:
                    uu = _perp(nrm)
                    vv = _cross(nrm, uu)
                    r = float(self.rint[u])
                    pts = self.P[u] + r * (self.cos[:, None] * uu + self.sin[:, None] * vv)
                    groups.append(("cap", alloc(pts), pts, u))
            elif self.deg[u] == 2 and root not in self.octa and not self._sharp(u):
                nrm = self._bisector(u)
                uu = _perp(nrm)
                vv = _cross(nrm, uu)
                pts = self.P[u] + float(self.rint[u]) * (self.cos[:, None] * uu + self.sin[:, None] * vv)
                groups.append(("point", alloc(pts), pts, u))
            elif self.deg[u] == 2 or root in self.octa:
                pts = np.array(self._octa(u))
                groups.append(("point", alloc(pts), pts, u))
        if not groups:
            return False, None
        X = np.vstack([g[2] for g in groups])
        Xc = X - X.mean(axis=0)
        ext = float(np.max(np.linalg.norm(Xc, axis=1)))
        eps = 1e-9 * max(ext, 1e-12) + 1e-13 * float(np.max(np.abs(X)))
        faces = _hull(Xc, eps)
        if faces is None:
            return False, None
        return self._finish(groups, faces, Xc)

    def _finish(self, groups: list, faces: list, X: np.ndarray):
        n = self.sides
        gids = [i for g in groups for i in g[1]]
        grp = np.concatenate([np.full(len(g[1]), k) for k, g in enumerate(groups)])
        local = {}
        offset = 0
        for k, g in enumerate(groups):
            local[k] = list(range(offset, offset + len(g[1])))
            offset += len(g[1])
        disc: dict[int, list] = {}
        side = []
        for f in faces:
            ga = grp[f[0]]
            if ga == grp[f[1]] == grp[f[2]] and groups[ga][0] in ("attach", "cap"):
                disc.setdefault(int(ga), []).append(f)
            else:
                side.append(f)
        bad = []
        out: list[tuple[int, ...]] = []
        for k, g in enumerate(groups):
            if g[0] not in ("attach", "cap"):
                continue
            ring = local[k]
            loop = {(min(ring[q], ring[(q + 1) % n]), max(ring[q], ring[(q + 1) % n])) for q in range(n)}
            count = {}
            for f in disc.get(k, []):
                for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                    key = (min(a, b), max(a, b))
                    count[key] = count.get(key, 0) + 1
            border = {key for key, c in count.items() if c == 1}
            clean = border == loop and all(c <= 2 for c in count.values())
            if g[0] == "attach":
                if not clean:
                    bad.append(g[3])
                continue
            if not clean:
                side.extend(disc.get(k, []))
            elif self.caps:
                directed = {(f[j], f[(j + 1) % 3]) for f in disc.get(k, []) for j in range(3)}
                out.append(tuple(ring) if (ring[0], ring[1]) in directed else tuple(reversed(ring)))
        if bad:
            return False, bad
        out.extend(_pair_quads(X, side))
        return True, [tuple(gids[i] for i in p) for p in out]

    def run(self):
        guard = 4 * self.n + 20
        for _ in range(guard):
            self._solve_dirty()
            limbs = self._limbs()
            if self._fold(limbs):
                continue
            res = self._emit(limbs)
            if res is not None:
                return res
        return np.zeros((0, 3)), []


def _weld(pts: np.ndarray, e: np.ndarray, rad: np.ndarray):
    used = np.unique(e)
    up = pts[used]
    diag = float(np.linalg.norm(up.max(axis=0) - up.min(axis=0)))
    tol = max(diag * 1e-6, 1e-12)
    parent = {int(i): int(i) for i in used}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cells: dict[tuple[int, int, int], list[int]] = {}
    keys = np.floor(up / tol).astype(np.int64)
    for idx, key in zip(used.tolist(), map(tuple, keys.tolist())):
        x, y, z = key
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in cells.get((x + dx, y + dy, z + dz), ()):
                        if float(np.linalg.norm(pts[idx] - pts[other])) <= tol:
                            ra = find(idx)
                            rb = find(other)
                            if ra != rb:
                                parent[max(ra, rb)] = min(ra, rb)
        cells.setdefault(key, []).append(idx)
    rep = np.arange(len(pts))
    for i in used.tolist():
        rep[i] = find(i)
    e2 = np.sort(rep[e], axis=1)
    e2 = e2[e2[:, 0] != e2[:, 1]]
    if len(e2) == 0:
        return None
    e2 = np.unique(e2, axis=0)
    nodes = np.unique(e2)
    index = np.full(len(pts), -1, dtype=np.int64)
    index[nodes] = np.arange(len(nodes))
    return pts[nodes].copy(), index[e2], rad[nodes].copy()


def build_skin(points, edges: Sequence, radii, sides: int = 8, caps: bool = True):
    sides = max(3, int(sides))
    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    n = len(pts)
    empty = (np.zeros((0, 3)), [])
    rad = np.zeros(n)
    if radii is not None:
        given = np.asarray(radii, dtype=float).reshape(-1)
        m = min(n, len(given))
        rad[:m] = given[:m]
    rad = np.where(np.isfinite(rad), np.abs(rad), 0.0)
    e = _unique_edges(edges, n)
    if len(e):
        e = e[np.isfinite(pts[e]).all(axis=(1, 2))]
    if len(e) == 0:
        return empty
    welded = _weld(pts, e, rad)
    if welded is None:
        return empty
    P, E, R = welded
    return _Skin(P, E, R, sides, bool(caps)).run()
