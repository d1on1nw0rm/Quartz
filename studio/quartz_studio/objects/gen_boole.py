from __future__ import annotations

import math

import numpy as np

from ..modeling.meshkit import triangulate_polygon
from ..scene import Mesh
from .registry import ObjectSpec, Param, register

__all__ = ["BOOLE_TYPES", "boolean_meshes", "build_boole", "build_voronoi_fracture", "fracture_mesh"]

BOOLE_TYPES = ("A union B", "A subtract B", "A intersect B", "A without B")
MAX_VORONOI_POINTS = 500


class _Batch:
    __slots__ = ("v", "cnt", "n", "w", "src")

    def __init__(self, v: np.ndarray, cnt: np.ndarray, n: np.ndarray, w: np.ndarray, src: np.ndarray) -> None:
        self.v = v
        self.cnt = cnt
        self.n = n
        self.w = w
        self.src = src

    def __len__(self) -> int:
        return len(self.cnt)

    def starts(self) -> np.ndarray:
        return np.cumsum(self.cnt) - self.cnt


def _empty() -> _Batch:
    return _Batch(np.zeros((0, 3)), np.zeros(0, int), np.zeros((0, 3)), np.zeros(0), np.zeros(0, int))


def _from_list(items: list) -> _Batch:
    if not items:
        return _empty()
    return _Batch(np.vstack([it[0] for it in items]),
                  np.array([len(it[0]) for it in items], int),
                  np.array([it[1] for it in items], float).reshape(-1, 3),
                  np.array([it[2] for it in items], float),
                  np.array([it[3] for it in items], int))


def _concat(batches: list) -> _Batch:
    batches = [b for b in batches if len(b)]
    if not batches:
        return _empty()
    if len(batches) == 1:
        return batches[0]
    return _Batch(np.vstack([b.v for b in batches]), np.concatenate([b.cnt for b in batches]),
                  np.vstack([b.n for b in batches]), np.concatenate([b.w for b in batches]),
                  np.concatenate([b.src for b in batches]))


def _select(b: _Batch, mask: np.ndarray) -> _Batch:
    if not mask.any():
        return _empty()
    if mask.all():
        return b
    vm = np.repeat(mask, b.cnt)
    return _Batch(b.v[vm], b.cnt[mask], b.n[mask], b.w[mask], b.src[mask])


def _flip(b: _Batch) -> _Batch:
    if not len(b):
        return b
    starts = b.starts()
    pid = np.repeat(np.arange(len(b.cnt)), b.cnt)
    local = np.arange(len(b.v)) - starts[pid]
    idx = starts[pid] + b.cnt[pid] - 1 - local
    return _Batch(b.v[idx], b.cnt.copy(), -b.n, -b.w, b.src.copy())


def _split(verts: np.ndarray, d: np.ndarray, t: np.ndarray):
    front: list = []
    back: list = []
    k = len(verts)
    for i in range(k):
        j = (i + 1) % k
        ti, tj = int(t[i]), int(t[j])
        vi = verts[i]
        if ti != 2:
            front.append(vi)
        if ti != 1:
            back.append(vi)
        if (ti | tj) == 3:
            s = d[i] / (d[i] - d[j])
            p = vi + s * (verts[j] - vi)
            front.append(p)
            back.append(p)
    fv = np.array(front) if len(front) >= 3 else None
    bv = np.array(back) if len(back) >= 3 else None
    return fv, bv


def _partition(b: _Batch, pn: np.ndarray, pw: float, eps: float, coplanar: bool):
    starts = b.starts()
    d = b.v @ pn - pw
    t = np.where(d > eps, 1, np.where(d < -eps, 2, 0)).astype(np.int8)
    ptype = np.bitwise_or.reduceat(t, starts)
    lo = int(ptype.min())
    hi = int(ptype.max())
    if lo == hi:
        if lo == 1:
            return b, _empty()
        if lo == 2:
            return _empty(), b
    front_mask = ptype == 1
    back_mask = ptype == 2
    if coplanar:
        cop = ptype == 0
        facing = (b.n @ pn) > 0.0
        front_mask = front_mask | (cop & facing)
        back_mask = back_mask | (cop & ~facing)
    front = _select(b, front_mask)
    back = _select(b, back_mask)
    span = np.flatnonzero(ptype == 3)
    if span.size:
        fl: list = []
        bl: list = []
        for k in span:
            s = starts[k]
            e = s + b.cnt[k]
            fv, bv = _split(b.v[s:e], d[s:e], t[s:e])
            if fv is not None:
                fl.append((fv, b.n[k], b.w[k], b.src[k]))
            if bv is not None:
                bl.append((bv, b.n[k], b.w[k], b.src[k]))
        front = _concat([front, _from_list(fl)])
        back = _concat([back, _from_list(bl)])
    return front, back


def _pick_splitter(b: _Batch, eps: float) -> int:
    count = len(b)
    if count <= 24:
        return 0
    starts = b.starts()
    best = 0
    best_score = None
    for k in np.unique(np.linspace(0, count - 1, 9).astype(int)):
        d = b.v @ b.n[k] - b.w[k]
        t = np.where(d > eps, 1, np.where(d < -eps, 2, 0)).astype(np.int8)
        ptype = np.bitwise_or.reduceat(t, starts)
        span = int((ptype == 3).sum())
        score = 3 * span + abs(int((ptype == 1).sum()) - int((ptype == 2).sum()))
        if best_score is None or score < best_score:
            best_score = score
            best = int(k)
    return best


def _build_tree(b: _Batch, eps: float):
    if not len(b):
        return None
    nn: list = []
    nw: list = []
    fr: list = []
    bk: list = []
    stack = [(b, -1, 0)]
    while stack:
        batch, parent, side = stack.pop()
        idx = len(nn)
        pick = _pick_splitter(batch, eps)
        pn = batch.n[pick].copy()
        pw = float(batch.w[pick])
        nn.append(pn)
        nw.append(pw)
        fr.append(-1)
        bk.append(-1)
        if parent >= 0:
            (fr if side == 0 else bk)[parent] = idx
        front, back = _partition(batch, pn, pw, eps, False)
        if len(front):
            stack.append((front, idx, 0))
        if len(back):
            stack.append((back, idx, 1))
    return np.array(nn), np.array(nw), fr, bk


def _clip(b: _Batch, tree, sign: float, eps: float) -> _Batch:
    if tree is None or not len(b):
        return b
    nn, nw, fr, bk = tree
    out: list = []
    stack = [(0, b)]
    while stack:
        i, batch = stack.pop()
        front, back = _partition(batch, sign * nn[i], sign * nw[i], eps, True)
        fi, bi = (fr[i], bk[i]) if sign > 0 else (bk[i], fr[i])
        if len(front):
            if fi >= 0:
                stack.append((fi, front))
            else:
                out.append(front)
        if len(back) and bi >= 0:
            stack.append((bi, back))
    return _concat(out)


def _newell(ring: np.ndarray) -> np.ndarray:
    nxt = np.concatenate([ring[1:], ring[:1]])
    x, y, z = ring[:, 0], ring[:, 1], ring[:, 2]
    nx, ny, nz = nxt[:, 0], nxt[:, 1], nxt[:, 2]
    return np.array([float(((y - ny) * (z + nz)).sum()), float(((z - nz) * (x + nx)).sum()),
                     float(((x - nx) * (y + ny)).sum())])


def _ring_normals(pts: np.ndarray, rings: list) -> np.ndarray:
    if not rings:
        return np.zeros((0, 3))
    cnt = np.array([len(r) for r in rings], int)
    flat = np.fromiter((i for r in rings for i in r), int, int(cnt.sum()))
    nxt = np.fromiter((r[(k + 1) % len(r)] for r in rings for k in range(len(r))), int, int(cnt.sum()))
    a = pts[flat]
    b = pts[nxt]
    starts = np.cumsum(cnt) - cnt
    return np.add.reduceat(np.cross(a, b), starts, axis=0)


class _Src:

    def __init__(self) -> None:
        self.next = 0

    def take(self) -> int:
        self.next += 1
        return self.next - 1


def _convex_planar(ring: np.ndarray, n: np.ndarray, eps: float) -> bool:
    if float(np.max(np.abs((ring - ring[0]) @ n))) > eps:
        return False
    if len(ring) == 3:
        return True
    e = np.roll(ring, -1, axis=0) - ring
    c = np.cross(e, np.roll(e, -1, axis=0)) @ n
    return bool(np.all(c >= -eps * float(np.max(np.linalg.norm(e, axis=1)))))


def _mesh_batch(mesh: Mesh, src: _Src, eps: float) -> _Batch:
    pts = mesh.points
    items: list = []
    for k, poly in enumerate(mesh.polygons):
        if len(poly) < 3:
            continue
        ring = pts[list(poly)]
        nv = _newell(ring)
        length = float(np.linalg.norm(nv))
        if length <= 1e-12:
            continue
        n = nv / length
        if _convex_planar(ring, n, eps):
            items.append((ring.copy(), n, float(n @ ring.mean(axis=0)), src.take()))
            continue
        planar = float(np.max(np.abs((ring - ring[0]) @ n))) <= eps
        shared = src.take()
        for tri in triangulate_polygon(mesh, k):
            tr = pts[list(tri)]
            tn = np.cross(tr[1] - tr[0], tr[2] - tr[0])
            tl = float(np.linalg.norm(tn))
            if tl <= 1e-12:
                continue
            tn = tn / tl
            items.append((tr.copy(), tn, float(tn @ tr[0]), shared if planar else src.take()))
    return _from_list(items)


def _overlaps(b: _Batch, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    if not len(b):
        return np.zeros(0, bool)
    starts = b.starts()
    vmin = np.minimum.reduceat(b.v, starts, axis=0)
    vmax = np.maximum.reduceat(b.v, starts, axis=0)
    return np.all((vmax >= lo) & (vmin <= hi), axis=1)


def _scale_of(*meshes: Mesh) -> float:
    pts = [m.points for m in meshes if len(m.points)]
    if not pts:
        return 1.0
    allp = np.vstack(pts)
    return max(1e-6, float(np.linalg.norm(allp.max(axis=0) - allp.min(axis=0))))


def _near(x: _Batch, solid: _Batch, closed: bool, eps: float) -> _Batch:
    if not closed or not len(x) or not len(solid):
        return x
    return _select(x, _overlaps(x, solid.v.min(axis=0) - eps, solid.v.max(axis=0) + eps))


def _bool_batches(a: _Batch, b: _Batch, op: str, eps: float, ta=None, tb=None,
                  closed_a: bool = False, closed_b: bool = False) -> _Batch:
    if ta is None:
        ta = _build_tree(a, eps)
    if tb is None:
        tb = _build_tree(b, eps)
    if op == "union":
        pa = _clip(a, tb, 1.0, eps)
        pb = _clip(b, ta, 1.0, eps)
        pb = _flip(_clip(_flip(pb), ta, 1.0, eps))
        return _concat([pa, pb])
    if op == "subtract":
        pa = _clip(_flip(a), tb, 1.0, eps)
        pb = _clip(_near(b, a, closed_a, eps), ta, -1.0, eps)
        pb = _flip(_clip(_flip(pb), ta, -1.0, eps))
        return _flip(_concat([pa, pb]))
    if op == "intersect":
        pb = _flip(_clip(_near(b, a, closed_a, eps), ta, -1.0, eps))
        pa = _clip(_flip(_near(a, b, closed_b, eps)), tb, -1.0, eps)
        pb = _clip(pb, ta, -1.0, eps)
        return _flip(_concat([pa, pb]))
    return _clip(a, tb, 1.0, eps)


def _weld(v: np.ndarray, tol: float) -> tuple[np.ndarray, np.ndarray]:
    m = len(v)
    cell = 2.0 * tol
    keys = []
    for ox in (0.0, 0.5):
        for oy in (0.0, 0.5):
            for oz in (0.0, 0.5):
                q = np.floor(v / cell + np.array([ox, oy, oz])).astype(np.int64)
                q -= q.min(axis=0)
                dims = q.max(axis=0) + 1
                key = (q[:, 0] * dims[1] + q[:, 1]) * dims[2] + q[:, 2]
                _, inv = np.unique(key, return_inverse=True)
                keys.append(inv.reshape(-1))
    lab = np.arange(m)
    while True:
        new = lab
        for inv in keys:
            g = np.full(int(inv.max()) + 1, m)
            np.minimum.at(g, inv, new)
            new = g[inv]
        if np.array_equal(new, lab):
            break
        lab = new
    reps, idx = np.unique(lab, return_inverse=True)
    return v[reps], idx.reshape(-1)


def _clean_ring(ring: list) -> list:
    changed = True
    while changed and len(ring) >= 3:
        changed = False
        out: list = []
        for i in ring:
            if not out or out[-1] != i:
                out.append(i)
        while len(out) > 1 and out[0] == out[-1]:
            out.pop()
        n = len(out)
        if n >= 3:
            for k in range(n):
                if out[k - 1] == out[(k + 1) % n]:
                    drop = {k, (k + 1) % n}
                    out = [x for j, x in enumerate(out) if j not in drop]
                    changed = True
                    break
        if len(out) != len(ring):
            changed = True
        ring = out
    return ring if len(ring) >= 3 else []


def _tjunctions(pts: np.ndarray, rings: list, tol: float) -> list:
    directed = set()
    for ring in rings:
        n = len(ring)
        for k in range(n):
            directed.add((ring[k], ring[(k + 1) % n]))
    edges = {}
    cand = set()
    for a, b in directed:
        if (b, a) not in directed:
            edges[(a, b) if a < b else (b, a)] = None
            cand.add(a)
            cand.add(b)
    if not edges:
        return rings
    keys = np.array(list(edges.keys()), int)
    cidx = np.array(sorted(cand), int)
    cp = pts[cidx]
    npts = len(cp)
    sq = np.einsum("ij,ij->i", cp, cp)
    chunk = max(1, int(2_000_000 // max(1, npts)))
    found: dict = {}
    for s in range(0, len(keys), chunk):
        ek = keys[s:s + chunk]
        a = pts[ek[:, 0]]
        d = pts[ek[:, 1]] - a
        l2 = np.einsum("ij,ij->i", d, d)
        ln = np.sqrt(l2)
        ad = np.einsum("ij,ij->i", a, d)
        aa = np.einsum("ij,ij->i", a, a)
        xd = cp @ d.T
        xa = cp @ a.T
        t = (xd - ad) / l2
        dist2 = sq[:, None] - 2.0 * xa + aa - t * t * l2
        along = t * ln
        mask = (along > tol) & (along < ln - tol) & (dist2 < tol * tol)
        pi, ei = np.nonzero(mask)
        for p, e in zip(pi.tolist(), ei.tolist()):
            found.setdefault(s + e, []).append((float(t[p, e]), int(cidx[p])))
    if not found:
        return rings
    inserts = {}
    for e, lst in found.items():
        lst.sort()
        inserts[(int(keys[e, 0]), int(keys[e, 1]))] = [p for _, p in lst]
    out: list = []
    for ring in rings:
        n = len(ring)
        new: list = []
        for k in range(n):
            a, b = ring[k], ring[(k + 1) % n]
            new.append(a)
            if a < b:
                mid = inserts.get((a, b))
                if mid:
                    new.extend(mid)
            else:
                mid = inserts.get((b, a))
                if mid:
                    new.extend(reversed(mid))
        out.append(new)
    return out


def _join(p: list, q: list):
    n = len(p)
    qe = {(q[k], q[(k + 1) % len(q)]) for k in range(len(q))}
    s = [(p[(i + 1) % n], p[i]) in qe for i in range(n)]
    if all(s) or not any(s):
        return None
    heads = [i for i in range(n) if s[i] and not s[i - 1]]
    if len(heads) != 1:
        return None
    start = heads[0]
    run = 0
    while s[(start + run) % n]:
        run += 1
    sv = p[start]
    ev = p[(start + run) % n]
    part = [p[(start + run + k) % n] for k in range(n - run + 1)]
    m = len(q)
    j = q.index(sv)
    k = (j + 1) % m
    steps = 0
    while q[k] != ev:
        part.append(q[k])
        k = (k + 1) % m
        steps += 1
        if steps > m:
            return None
    if len(part) < 3 or len(set(part)) != len(part):
        return None
    return part


def _merge(pts: np.ndarray, rings: list, srcs: list, by_plane: bool, tol: float) -> list:
    nv = _ring_normals(pts, rings)
    nv = nv / np.maximum(1e-300, np.linalg.norm(nv, axis=1))[:, None]
    normals = list(nv)
    offsets = [float(nv[k] @ pts[r[0]]) for k, r in enumerate(rings)]
    alive = {i: list(r) for i, r in enumerate(rings)}
    owner = {}
    for i, r in alive.items():
        for k in range(len(r)):
            owner[(r[k], r[(k + 1) % len(r)])] = i

    def edges(r: list):
        return [(r[k], r[(k + 1) % len(r)]) for k in range(len(r))]

    def compatible(i: int, j: int) -> bool:
        if srcs[i] == srcs[j]:
            return True
        if not by_plane:
            return False
        if float(normals[i] @ normals[j]) < 1.0 - 1e-9:
            return False
        return abs(offsets[i] - float(normals[i] @ pts[alive[j][0]])) <= tol

    queue = list(alive)
    while queue:
        i = queue.pop()
        if i not in alive:
            continue
        ring = alive[i]
        for a, b in edges(ring):
            j = owner.get((b, a))
            if j is None or j == i or j not in alive or not compatible(i, j):
                continue
            new = _join(ring, alive[j])
            if new is None:
                continue
            for e in edges(ring):
                if owner.get(e) == i:
                    del owner[e]
            for e in edges(alive[j]):
                if owner.get(e) == j:
                    del owner[e]
            del alive[j]
            alive[i] = new
            for e in edges(new):
                owner[e] = i
            queue.append(i)
            break
    return list(alive.values())


def _drop_collinear(pts: np.ndarray, rings: list, tol: float) -> list:
    rings = [list(r) for r in rings]
    pl = pts.tolist()
    nbrs: dict = {}
    where: dict = {}
    for pi, r in enumerate(rings):
        n = len(r)
        for k in range(n):
            a, b = r[k], r[(k + 1) % n]
            nbrs.setdefault(a, set()).add(b)
            nbrs.setdefault(b, set()).add(a)
            where.setdefault(r[k], set()).add(pi)
    work = [v for v, s in nbrs.items() if len(s) == 2]
    while work:
        v = work.pop()
        s = nbrs.get(v)
        if s is None or len(s) != 2:
            continue
        a, b = tuple(s)
        pa, pb, pv = pl[a], pl[b], pl[v]
        ab = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        av = (pv[0] - pa[0], pv[1] - pa[1], pv[2] - pa[2])
        l2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2]
        if l2 <= tol * tol:
            continue
        cx = ab[1] * av[2] - ab[2] * av[1]
        cy = ab[2] * av[0] - ab[0] * av[2]
        cz = ab[0] * av[1] - ab[1] * av[0]
        if cx * cx + cy * cy + cz * cz > tol * tol * l2:
            continue
        t = (av[0] * ab[0] + av[1] * ab[1] + av[2] * ab[2]) / l2
        if t <= 0.0 or t >= 1.0:
            continue
        polys = where.get(v, set())
        if any(len(rings[pi]) <= 3 for pi in polys):
            continue
        for pi in polys:
            rings[pi] = [x for x in rings[pi] if x != v]
        del nbrs[v]
        del where[v]
        nbrs[a].discard(v)
        nbrs[a].add(b)
        nbrs[b].discard(v)
        nbrs[b].add(a)
        work.extend((a, b))
    return rings


def _to_mesh(b: _Batch, scale: float, mode: str) -> Mesh:
    if not len(b):
        return Mesh.empty()
    tol = 1e-5 * scale
    pts, idx = _weld(b.v, tol)
    starts = b.starts()
    rings: list = []
    srcs: list = []
    for k in range(len(b.cnt)):
        ring = _clean_ring(idx[starts[k]:starts[k] + b.cnt[k]].tolist())
        if ring:
            rings.append(ring)
            srcs.append(int(b.src[k]))
    rings = _tjunctions(pts, rings, tol)
    cleaned = [(_clean_ring(r), s) for r, s in zip(rings, srcs)]
    cleaned = [(r, s) for r, s in cleaned if r]
    areas = np.linalg.norm(_ring_normals(pts, [r for r, _ in cleaned]), axis=1) * 0.5
    keep = [c for c, area in zip(cleaned, areas) if area > tol * tol]
    rings = [r for r, _ in keep]
    keep_s = [s for _, s in keep]
    if mode != "raw":
        rings = _merge(pts, rings, keep_s, mode == "plane", tol)
        rings = _drop_collinear(pts, rings, tol)
    used = sorted({i for r in rings for i in r})
    remap = {old: new for new, old in enumerate(used)}
    out_pts = pts[used] if used else np.zeros((0, 3))
    return Mesh(out_pts, [tuple(remap[i] for i in r) for r in rings])


def _short_cycle(a: int, b: int, nxt: dict, used: set):
    for c in nxt.get(b, ()):
        if c == a or (b, c) in used:
            continue
        if a in nxt.get(c, ()) and (c, a) not in used:
            return [a, b, c]
    for c in nxt.get(b, ()):
        if c == a or (b, c) in used:
            continue
        for d in nxt.get(c, ()):
            if d in (a, b) or (c, d) in used:
                continue
            if a in nxt.get(d, ()) and (d, a) not in used:
                return [a, b, c, d]
    return None


def _seal(mesh: Mesh) -> Mesh:
    polys = [tuple(poly) for poly in mesh.polygons]
    directed = set()
    for poly in polys:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            directed.add((a, b))
    gaps = sorted((a, b) for a, b in directed if (b, a) not in directed)
    if not gaps:
        return mesh
    nxt: dict = {}
    for a, b in gaps:
        nxt.setdefault(a, []).append(b)
    used: set = set()
    extra: list = []
    for a, b in gaps:
        if (a, b) in used:
            continue
        cyc = _short_cycle(a, b, nxt, used)
        if cyc is None:
            continue
        if float(np.linalg.norm(_newell(mesh.points[cyc]))) <= 1e-9:
            continue
        for x, y in zip(cyc, cyc[1:] + cyc[:1]):
            used.add((x, y))
        extra.append(tuple(cyc[::-1]))
    if not extra:
        return mesh
    return Mesh(mesh.points, polys + extra)


def _closed_mesh_parts(meshes: list) -> list:
    return [m for m in meshes if m.polygons]


def boolean_meshes(a: Mesh, b: Mesh, kind: str = "A subtract B", high_quality: bool = True,
                   hide_new_edges: bool = False) -> Mesh:
    op = {"A union B": "union", "A subtract B": "subtract", "A intersect B": "intersect",
          "A without B": "without"}.get(kind, "subtract")
    scale = _scale_of(a, b)
    eps = 1e-6 * 2.0 ** math.ceil(math.log2(scale))
    ba, na, ta, closed_a = _prepared(a, eps)
    bb, _nb, tb, closed_b = _prepared(b, eps)
    bb = _Batch(bb.v, bb.cnt, bb.n, bb.w, bb.src + na)
    result = _bool_batches(ba, bb, op, eps, ta, tb, closed_a, closed_b)
    mode = "plane" if hide_new_edges else ("source" if high_quality else "raw")
    return _to_mesh(result, scale, mode)


_PREPARED: dict = {}
_PREPARED_LIMIT = 32


def _prepared(mesh: Mesh, eps: float):
    key = (mesh.points.tobytes(), tuple(mesh.polygons), eps)
    hit = _PREPARED.get(key)
    if hit is None:
        src = _Src()
        batch = _mesh_batch(mesh, src, eps)
        if len(_PREPARED) >= _PREPARED_LIMIT:
            _PREPARED.clear()
        hit = _PREPARED[key] = (batch, src.next, _build_tree(batch, eps), _is_closed(mesh))
    return hit


def _is_closed(mesh: Mesh) -> bool:
    directed: dict = {}
    for poly in mesh.polygons:
        for u, v in zip(poly, poly[1:] + poly[:1]):
            directed[(u, v)] = directed.get((u, v), 0) + 1
    return bool(directed) and all(c == 1 and directed.get((v, u)) == 1 for (u, v), c in directed.items())


def _copy(mesh: Mesh) -> Mesh:
    return Mesh(mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges))


def build_boole(p: dict, inputs: list) -> Mesh:
    meshes = _closed_mesh_parts([inp.mesh for inp in inputs])
    if not meshes:
        return Mesh.empty()
    if len(meshes) == 1:
        return _copy(meshes[0])
    hq = bool(p["high_quality"])
    hide = bool(p["hide_new_edges"])
    b = meshes[1]
    for extra in meshes[2:]:
        b = boolean_meshes(b, extra, "A union B", hq, hide)
    return boolean_meshes(meshes[0], b, p["boolean_type"], hq, hide)


def _box_faces(lo: np.ndarray, hi: np.ndarray) -> list:
    c = np.array([[lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
                  [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]])
    quads = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3), (1, 2, 6, 5), (3, 7, 6, 2), (0, 1, 5, 4))
    return [c[list(q)] for q in quads]


def _dedupe(ring: np.ndarray, tol: float):
    out: list = []
    for p in ring:
        if not out or float(np.linalg.norm(p - out[-1])) > tol:
            out.append(p)
    while len(out) > 1 and float(np.linalg.norm(out[0] - out[-1])) <= tol:
        out.pop()
    return np.array(out) if len(out) >= 3 else None


def _cut_convex(faces: list, n: np.ndarray, w: float, eps: float, tol: float):
    allp = np.vstack(faces)
    d = allp @ n - w
    if float(d.max()) <= eps:
        return faces
    if float(d.min()) >= -eps:
        return []
    out: list = []
    cap: list = []
    for f in faces:
        dd = f @ n - w
        inside = dd <= eps
        cap.extend(f[np.abs(dd) <= eps])
        if inside.all():
            out.append(f)
            continue
        if not inside.any():
            continue
        ring: list = []
        k = len(f)
        for i in range(k):
            j = (i + 1) % k
            if inside[i]:
                ring.append(f[i])
            if inside[i] != inside[j]:
                s = dd[i] / (dd[i] - dd[j])
                q = f[i] + s * (f[j] - f[i])
                ring.append(q)
                cap.append(q)
        r = _dedupe(np.array(ring), tol)
        if r is not None:
            out.append(r)
    if len(cap) >= 3:
        cp = np.array(cap)
        u = np.cross(n, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 0.5:
            u = np.cross(n, [0.0, 1.0, 0.0])
        u = u / np.linalg.norm(u)
        v = np.cross(n, u)
        c = cp.mean(axis=0)
        ang = np.arctan2((cp - c) @ v, (cp - c) @ u)
        uniq: list = []
        for p in cp[np.argsort(ang)]:
            if all(float(np.linalg.norm(p - x)) > tol for x in uniq):
                uniq.append(p)
        r = _dedupe(np.array(uniq), tol) if len(uniq) >= 3 else None
        if r is not None:
            out.append(r)
    return out


def fracture_mesh(mesh: Mesh, amount: int, seed: int, offset: float = 0.0) -> list:
    if not mesh.polygons or amount < 1:
        return []
    lo, hi = mesh.bounds()
    scale = _scale_of(mesh)
    eps = 1e-6 * scale
    tol = 1e-5 * scale
    rng = np.random.default_rng(int(seed))
    seeds = lo + rng.random((int(amount), 3)) * (hi - lo)
    margin = 0.01 * scale + tol
    src = _Src()
    child = _mesh_batch(mesh, src, eps)
    tree = _build_tree(child, eps)
    if len(seeds) == 1:
        return [(_copy(mesh), seeds[0])]
    out: list = []
    for i, si in enumerate(seeds):
        faces = _box_faces(lo - margin, hi + margin)
        others = np.delete(seeds, i, axis=0)
        dist = np.linalg.norm(others - si, axis=1)
        reach = float(np.linalg.norm(np.vstack(faces) - si, axis=1).max())
        for k in np.argsort(dist):
            dk = float(dist[k])
            if dk <= tol:
                continue
            if 0.5 * (dk - offset) > reach + eps:
                break
            n = (others[k] - si) / dk
            w = float(n @ ((others[k] + si) * 0.5)) - offset * 0.5
            cut = _cut_convex(faces, n, w, eps, tol)
            if not cut:
                faces = cut
                break
            if cut is not faces:
                faces = cut
                reach = float(np.linalg.norm(np.vstack(faces) - si, axis=1).max())
        if len(faces) < 4:
            continue
        base = src.next
        items = []
        for f in faces:
            nv = _newell(f)
            ln = float(np.linalg.norm(nv))
            if ln <= 1e-12:
                continue
            nv = nv / ln
            items.append((f, nv, float(nv @ f.mean(axis=0)), src.take()))
        cell = _from_list(items)
        if src.next == base:
            continue
        cp = np.vstack(faces)
        near = _select(child, _overlaps(child, cp.min(axis=0) - eps, cp.max(axis=0) + eps))
        frag = _to_mesh(_bool_batches(near, cell, "intersect", eps, ta=tree), scale, "source")
        if frag.polygons:
            out.append((_seal(frag), si))
    return out


def build_voronoi_fracture(p: dict, inputs: list) -> Mesh:
    pieces: list = []
    for k, inp in enumerate(inputs):
        m = inp.mesh
        if not m.polygons:
            continue
        frags = fracture_mesh(m, int(p["point_amount"]), int(p["seed"]) + k, float(p["offset_fragments"]))
        if p["sort_result"]:
            frags.sort(key=lambda fs: tuple(np.round(fs[0].points.mean(axis=0), 6)))
        pieces.extend(f for f, _ in frags)
    if not pieces:
        return Mesh.empty()
    pts: list = []
    polys: list = []
    off = 0
    for m in pieces:
        pts.append(m.points)
        polys.extend(tuple(i + off for i in poly) for poly in m.polygons)
        off += len(m.points)
    return Mesh(np.vstack(pts), polys)


BOOLE = register(ObjectSpec(
    id="boole",
    label="Boole",
    category="generator",
    build=build_boole,
    params=(
        Param("boolean_type", "Boolean Type", "choice", "A subtract B", choices=BOOLE_TYPES, group="Object"),
        Param("high_quality", "High Quality", "bool", True, group="Object"),
        Param("hide_new_edges", "Hide New Edges", "bool", False, group="Object"),
    ),
    inputs="children",
    icon="boolean",
    description="Combines the first child (A) with the following children (B) by union, subtraction or intersection",
))

VORONOI_FRACTURE = register(ObjectSpec(
    id="voronoi_fracture",
    label="Voronoi Fracture",
    category="generator",
    build=build_voronoi_fracture,
    params=(
        Param("point_amount", "Point Amount", "int", 20, minimum=1, maximum=MAX_VORONOI_POINTS, group="Object"),
        Param("seed", "Seed", "int", 12345, minimum=0, group="Object"),
        Param("offset_fragments", "Offset Fragments", "distance", 0.0, minimum=0.0, group="Object"),
        Param("sort_result", "Sort Result", "bool", False, group="Object"),
    ),
    inputs="children",
    icon="voronoi",
    description="Breaks each child into closed Voronoi fragments around random points in its bounding box",
))
