from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..scene import Mesh

__all__ = ["SubdivOperator", "catmull_clark", "subdivide_mesh", "polygon_signature", "polygon_arrays", "ramp"]

_CACHE: dict = {}
_CACHE_LIMIT = 32


def ramp(counts: np.ndarray) -> np.ndarray:
    counts = np.asarray(counts, np.int64)
    total = int(counts.sum())
    if total == 0:
        return np.zeros(0, np.int64)
    starts = np.cumsum(counts) - counts
    return np.arange(total, dtype=np.int64) - np.repeat(starts, counts)


def polygon_arrays(polygons) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(polygons, np.ndarray) and polygons.ndim == 2:
        arr = polygons.astype(np.int64, copy=False)
        return np.full(len(arr), arr.shape[1], np.int64), arr.reshape(-1)
    count = len(polygons)
    if count:
        first = len(polygons[0])
        try:
            arr = np.asarray(polygons, dtype=np.int64)
        except (ValueError, TypeError):
            arr = None
        if arr is not None and arr.ndim == 2 and arr.shape[1] == first:
            return np.full(count, first, np.int64), arr.reshape(-1)
    sizes = np.fromiter((len(p) for p in polygons), np.int64, count)
    flat = np.fromiter((int(i) for p in polygons for i in p), np.int64, int(sizes.sum()))
    return sizes, flat


def polygon_signature(n_points: int, polygons) -> str:
    h = hashlib.sha1()
    h.update(str(int(n_points)).encode())
    sizes, flat = polygon_arrays(polygons)
    h.update(sizes.tobytes())
    h.update(flat.tobytes())
    return h.hexdigest()


@dataclass
class SubdivOperator:
    n: int
    m: int
    rows: np.ndarray
    cols: np.ndarray
    vals: np.ndarray
    polygons: list
    quads: np.ndarray

    def apply(self, values) -> np.ndarray:
        arr = np.asarray(values, float)
        if arr.shape[0] != self.n:
            raise ValueError(f"operator expects {self.n} rows, got {arr.shape[0]}")
        if arr.ndim == 1:
            return np.bincount(self.rows, weights=self.vals * arr[self.cols], minlength=self.m)
        out = np.empty((self.m,) + arr.shape[1:], float)
        flat = arr.reshape(self.n, -1)
        res = out.reshape(self.m, -1)
        for k in range(flat.shape[1]):
            res[:, k] = np.bincount(self.rows, weights=self.vals * flat[self.cols, k], minlength=self.m)
        return out


def _expand(fstart: np.ndarray, sizes: np.ndarray, cv: np.ndarray, faces: np.ndarray,
            rows: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    counts = sizes[faces]
    idx = np.repeat(fstart[faces], counts) + ramp(counts)
    return np.repeat(rows, counts), cv[idx], np.repeat(weights / counts, counts)


def _build(n: int, polygons: Sequence[Sequence[int]]) -> SubdivOperator:
    sizes, cv = polygon_arrays(polygons)
    if len(sizes) and sizes.min() < 3:
        keep = sizes >= 3
        starts = np.cumsum(sizes) - sizes
        cv = cv[np.repeat(starts[keep], sizes[keep]) + ramp(sizes[keep])]
        sizes = sizes[keep]
    F = len(sizes)
    if F == 0:
        rows = np.arange(n, dtype=np.int64)
        return SubdivOperator(n, n, rows, rows.copy(), np.ones(n), [], np.zeros((0, 4), np.int64))
    C = len(cv)
    fc = np.repeat(np.arange(F, dtype=np.int64), sizes)
    fstart = np.cumsum(sizes) - sizes
    li = np.arange(C, dtype=np.int64) - fstart[fc]
    nxt = fstart[fc] + (li + 1) % sizes[fc]
    prv = fstart[fc] + (li - 1) % sizes[fc]
    cn = cv[nxt]
    lo = np.minimum(cv, cn)
    hi = np.maximum(cv, cn)
    keys = lo * np.int64(max(n, 1)) + hi
    uniq, ec = np.unique(keys, return_inverse=True)
    ec = ec.reshape(-1)
    E = len(uniq)
    ea = uniq // max(n, 1)
    eb = uniq % max(n, 1)
    efc = np.bincount(ec, minlength=E)
    interior_e = efc == 2
    m = n + E + F

    R: list[np.ndarray] = []
    Cc: list[np.ndarray] = []
    V: list[np.ndarray] = []

    R.append(n + E + fc)
    Cc.append(cv)
    V.append(1.0 / sizes[fc])

    be = np.nonzero(~interior_e)[0]
    R.extend([n + be, n + be])
    Cc.extend([ea[be], eb[be]])
    V.extend([np.full(len(be), 0.5), np.full(len(be), 0.5)])
    ie = np.nonzero(interior_e)[0]
    R.extend([n + ie, n + ie])
    Cc.extend([ea[ie], eb[ie]])
    V.extend([np.full(len(ie), 0.25), np.full(len(ie), 0.25)])
    ic = np.nonzero(interior_e[ec])[0]
    r, c, v = _expand(fstart, sizes, cv, fc[ic], n + ec[ic], np.full(len(ic), 0.25))
    R.append(r)
    Cc.append(c)
    V.append(v)

    deg = np.bincount(ea, minlength=n) + np.bincount(eb, minlength=n)
    bdeg = np.bincount(ea[be], minlength=n) + np.bincount(eb[be], minlength=n)
    fcount = np.bincount(cv, minlength=n)
    interior_v = (fcount > 0) & (bdeg == 0) & (deg >= 3)
    crease_v = (fcount > 0) & (bdeg == 2) & (deg > 2)
    other_v = ~(interior_v | crease_v)

    iv = np.nonzero(interior_v)[0]
    nv = deg.astype(float)
    R.append(iv)
    Cc.append(iv)
    V.append((nv[iv] - 3.0) / nv[iv])
    qc = np.nonzero(interior_v[cv])[0]
    if len(qc):
        vq = cv[qc]
        r, c, v = _expand(fstart, sizes, cv, fc[qc], vq, 1.0 / (nv[vq] * fcount[vq]))
        R.append(r)
        Cc.append(c)
        V.append(v)
    for u, w in ((ea, eb), (eb, ea)):
        sel = interior_v[u]
        uu, ww = u[sel], w[sel]
        k = 1.0 / (nv[uu] ** 2)
        R.extend([uu, uu])
        Cc.extend([uu, ww])
        V.extend([k, k])

    cvx = np.nonzero(crease_v)[0]
    R.append(cvx)
    Cc.append(cvx)
    V.append(np.full(len(cvx), 0.75))
    for u, w in ((ea[be], eb[be]), (eb[be], ea[be])):
        sel = crease_v[u]
        R.append(u[sel])
        Cc.append(w[sel])
        V.append(np.full(int(sel.sum()), 0.125))

    ov = np.nonzero(other_v)[0]
    R.append(ov)
    Cc.append(ov)
    V.append(np.ones(len(ov)))

    rows = np.concatenate(R).astype(np.int64)
    cols = np.concatenate(Cc).astype(np.int64)
    vals = np.concatenate(V).astype(float)
    quads = np.stack([cv, n + ec, n + E + fc, n + ec[prv]], axis=1)
    polys_out = list(map(tuple, quads.tolist()))
    return SubdivOperator(n, m, rows, cols, vals, polys_out, quads)


def catmull_clark(n_points: int, polygons: Sequence[Sequence[int]], *, key: str | None = None) -> SubdivOperator:
    sig = key or polygon_signature(n_points, polygons)
    op = _CACHE.get(sig)
    if op is None:
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        op = _CACHE[sig] = _build(int(n_points), polygons)
    return op


def subdivide_mesh(mesh: Mesh, levels: int = 1) -> Mesh:
    pts = np.asarray(mesh.points, float)
    polys = list(mesh.polygons)
    for _ in range(max(0, int(levels))):
        op = catmull_clark(len(pts), polys)
        pts = op.apply(pts)
        polys = op.polygons
    return Mesh(pts, polys)
