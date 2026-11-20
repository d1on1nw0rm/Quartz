from __future__ import annotations

from typing import Sequence

import numpy as np

from .subdivision import polygon_arrays, polygon_signature, ramp

__all__ = ["Topology", "get_topology", "ray_triangles"]

_CACHE: dict = {}
_CACHE_LIMIT = 16
RAY_CULL_MIN = 2048


class Topology:

    def __init__(self, n_points: int, polygons: Sequence[Sequence[int]]) -> None:
        self.n = int(n_points)
        sizes, cv = polygon_arrays(polygons)
        if len(sizes) and sizes.min() < 3:
            keep = sizes >= 3
            starts = np.cumsum(sizes) - sizes
            cv = cv[np.repeat(starts[keep], sizes[keep]) + ramp(sizes[keep])]
            sizes = sizes[keep]
        F = len(sizes)
        n = self.n
        fc = np.repeat(np.arange(F, dtype=np.int64), sizes)
        fstart = np.cumsum(sizes) - sizes
        if len(cv):
            li = np.arange(len(cv), dtype=np.int64) - fstart[fc]
            nxt = fstart[fc] + (li + 1) % sizes[fc]
            cn = cv[nxt]
        else:
            cn = cv
        self.sizes = sizes
        self.corner_vertex = cv
        self.corner_face = fc
        self.face_start = fstart
        self.corner_next = cn
        self.vf_ptr, self.vf = self._csr(cv, fc, n)
        tri_counts = np.maximum(sizes - 2, 0)
        tf = np.repeat(np.arange(F, dtype=np.int64), tri_counts)
        tk = ramp(tri_counts)
        if len(tf):
            t0 = cv[fstart[tf]]
            t1 = cv[fstart[tf] + tk + 1]
            t2 = cv[fstart[tf] + tk + 2]
            self.tris = np.stack([t0, t1, t2], axis=1)
        else:
            self.tris = np.zeros((0, 3), np.int64)
        self.tri_face = tf
        lo = np.minimum(cv, cn)
        hi = np.maximum(cv, cn)
        base = np.int64(max(n, 1))
        if len(cv):
            uniq, counts = np.unique(lo * base + hi, return_counts=True)
        else:
            uniq = np.zeros(0, np.int64)
            counts = np.zeros(0, np.int64)
        ea = uniq // base
        eb = uniq % base
        keep = ea != eb
        ea, eb, counts = ea[keep], eb[keep], counts[keep]
        self.edges = np.stack([ea, eb], axis=1) if len(ea) else np.zeros((0, 2), np.int64)
        self.edge_faces = counts
        self.nbr_ptr, self.nbr = self._csr(np.concatenate([ea, eb]), np.concatenate([eb, ea]), n)
        bmask = counts != 2
        ba, bb = ea[bmask], eb[bmask]
        self.boundary = np.zeros(n, bool)
        self.boundary[ba] = True
        self.boundary[bb] = True
        self.bnbr_ptr, self.bnbr = self._csr(np.concatenate([ba, bb]), np.concatenate([bb, ba]), n)
        T = len(self.tris)
        self.vt_ptr, self.vt = self._csr(self.tris.reshape(-1),
                                         np.repeat(np.arange(T, dtype=np.int64), 3), n)

    @staticmethod
    def _csr(src: np.ndarray, dst: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
        src = np.asarray(src, np.int64)
        dst = np.asarray(dst, np.int64)
        order = np.argsort(src, kind="stable")
        counts = np.bincount(src, minlength=n) if len(src) else np.zeros(n, np.int64)
        ptr = np.zeros(n + 1, np.int64)
        np.cumsum(counts, out=ptr[1:])
        return ptr, dst[order]

    @staticmethod
    def _gather(ptr: np.ndarray, data: np.ndarray, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        idx = np.asarray(idx, np.int64)
        counts = ptr[idx + 1] - ptr[idx]
        flat = data[np.repeat(ptr[idx], counts) + ramp(counts)]
        group = np.repeat(np.arange(len(idx), dtype=np.int64), counts)
        return flat, group

    def neighbors(self, i: int) -> np.ndarray:
        return self.nbr[self.nbr_ptr[i]:self.nbr_ptr[i + 1]].copy()

    def valence(self) -> np.ndarray:
        return np.diff(self.nbr_ptr)

    @staticmethod
    def _group_mean(values: np.ndarray, flat: np.ndarray, group: np.ndarray, count: int,
                    fallback: np.ndarray) -> np.ndarray:
        cnt = np.bincount(group, minlength=count).astype(float)
        out = fallback.copy()
        ok = cnt > 0
        if values.ndim == 1:
            s = np.bincount(group, weights=values[flat], minlength=count)
            out[ok] = s[ok] / cnt[ok]
            return out
        for k in range(values.shape[1]):
            s = np.bincount(group, weights=values[flat, k], minlength=count)
            out[ok, k] = s[ok] / cnt[ok]
        return out

    def neighbor_mean(self, pts: np.ndarray, idx: np.ndarray | None = None,
                      keep_boundary: bool = True) -> np.ndarray:
        pts = np.asarray(pts, float)
        if idx is None:
            idx = np.arange(self.n, dtype=np.int64)
        idx = np.asarray(idx, np.int64)
        if not len(idx):
            return pts[idx].copy()
        flat, group = self._gather(self.nbr_ptr, self.nbr, idx)
        out = self._group_mean(pts, flat, group, len(idx), pts[idx])
        if keep_boundary:
            bsel = np.nonzero(self.boundary[idx])[0]
            if len(bsel):
                bidx = idx[bsel]
                bflat, bgroup = self._gather(self.bnbr_ptr, self.bnbr, bidx)
                bcnt = np.bincount(bgroup, minlength=len(bidx))
                vals = self._group_mean(pts, bflat, bgroup, len(bidx), pts[bidx])
                fixed = (bcnt < 2) | ((self.nbr_ptr[bidx + 1] - self.nbr_ptr[bidx]) <= 2)
                vals[fixed] = pts[bidx][fixed]
                out[bsel] = vals
        return out

    def tri_normals(self, pts: np.ndarray, tris: np.ndarray | None = None) -> np.ndarray:
        t = self.tris if tris is None else self.tris[tris]
        a, b, c = pts[t[:, 0]], pts[t[:, 1]], pts[t[:, 2]]
        return np.cross(b - a, c - a)

    def face_normals(self, pts: np.ndarray, faces: np.ndarray | None = None) -> np.ndarray:
        pts = np.asarray(pts, float)
        if faces is None:
            faces = np.arange(len(self.sizes), dtype=np.int64)
        faces = np.asarray(faces, np.int64)
        counts = self.sizes[faces]
        cidx = np.repeat(self.face_start[faces], counts) + ramp(counts)
        group = np.repeat(np.arange(len(faces), dtype=np.int64), counts)
        a = pts[self.corner_vertex[cidx]]
        b = pts[self.corner_next[cidx]]
        terms = np.stack([
            (a[:, 1] - b[:, 1]) * (a[:, 2] + b[:, 2]),
            (a[:, 2] - b[:, 2]) * (a[:, 0] + b[:, 0]),
            (a[:, 0] - b[:, 0]) * (a[:, 1] + b[:, 1]),
        ], axis=1)
        out = np.zeros((len(faces), 3))
        for k in range(3):
            out[:, k] = np.bincount(group, weights=terms[:, k], minlength=len(faces))
        return out

    def vertex_normals(self, pts: np.ndarray, idx: np.ndarray | None = None) -> np.ndarray:
        pts = np.asarray(pts, float)
        if idx is None:
            idx = np.arange(self.n, dtype=np.int64)
        idx = np.asarray(idx, np.int64)
        flat, group = self._gather(self.vf_ptr, self.vf, idx)
        out = np.zeros((len(idx), 3))
        if len(flat):
            faces, inv = np.unique(flat, return_inverse=True)
            fn = self.face_normals(pts, faces)[inv.reshape(-1)]
            for k in range(3):
                out[:, k] = np.bincount(group, weights=fn[:, k], minlength=len(idx))
        length = np.linalg.norm(out, axis=1)
        ok = length > 1e-12
        out[ok] /= length[ok][:, None]
        return out

    def face_vertices(self, face: int) -> np.ndarray:
        start = int(self.face_start[face])
        return self.corner_vertex[start:start + int(self.sizes[face])]

    def face_normal(self, pts: np.ndarray, face: int) -> np.ndarray:
        if not 0 <= face < len(self.sizes):
            return np.zeros(3)
        ring = np.asarray(pts, float)[self.face_vertices(face)]
        nxt = np.roll(ring, -1, axis=0)
        n = np.array([
            np.sum((ring[:, 1] - nxt[:, 1]) * (ring[:, 2] + nxt[:, 2])),
            np.sum((ring[:, 2] - nxt[:, 2]) * (ring[:, 0] + nxt[:, 0])),
            np.sum((ring[:, 0] - nxt[:, 0]) * (ring[:, 1] + nxt[:, 1])),
        ])
        length = float(np.linalg.norm(n))
        return n / length if length > 1e-12 else n

    def grow(self, sel: np.ndarray) -> np.ndarray:
        sel = np.asarray(sel, bool)
        out = sel.copy()
        if not len(self.edges):
            return out
        a, b = self.edges[:, 0], self.edges[:, 1]
        out[b[sel[a]]] = True
        out[a[sel[b]]] = True
        return out

    def _edge_columns(self) -> tuple[np.ndarray, np.ndarray]:
        cols = getattr(self, "_edge_cols", None)
        if cols is None:
            cols = self._edge_cols = (np.ascontiguousarray(self.edges[:, 0]),
                                      np.ascontiguousarray(self.edges[:, 1]))
        return cols

    def max_edge(self, pts: np.ndarray, idx: np.ndarray | None = None) -> float:
        pts = np.asarray(pts, float)
        if idx is None:
            if not len(self.edges):
                return 0.0
            a, b = self._edge_columns()
            d = np.take(pts, a, axis=0)
            d -= np.take(pts, b, axis=0)
        else:
            idx = np.asarray(idx, np.int64)
            if not len(idx):
                return 0.0
            flat, group = self._gather(self.nbr_ptr, self.nbr, idx)
            if not len(flat):
                return 0.0
            d = np.take(pts, np.take(idx, group), axis=0)
            d -= np.take(pts, flat, axis=0)
        d *= d
        return float(np.sqrt(np.max(d[:, 0] + d[:, 1] + d[:, 2])))

    def ray_candidates(self, pts: np.ndarray, origin, direction, bound: float | None = None) -> np.ndarray | None:
        if len(self.tris) < RAY_CULL_MIN:
            return None
        o = np.asarray(origin, float).reshape(3)
        d = np.asarray(direction, float).reshape(3)
        length = float(np.linalg.norm(d))
        if length < 1e-12:
            return None
        d = d / length
        reach = self.max_edge(pts) if bound is None else float(bound)
        if not np.isfinite(reach):
            return None
        reach = reach * (1.0 + 1e-6) + 1e-9
        a = np.array([1.0, 0.0, 0.0]) if abs(float(d[0])) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = np.cross(d, a)
        u /= float(np.linalg.norm(u))
        v = np.cross(d, u)
        basis = np.stack([u, v, d], axis=1)
        q = np.asarray(pts, float) @ basis
        q -= o @ basis
        near = np.nonzero((q[:, 0] * q[:, 0] + q[:, 1] * q[:, 1] <= reach * reach) & (q[:, 2] >= -reach))[0]
        if not len(near):
            return np.zeros(0, np.int64)
        flat, _group = self._gather(self.vt_ptr, self.vt, near)
        return np.unique(flat)

    def raycast(self, pts: np.ndarray, origin, direction,
                bound: float | None = None) -> tuple[int, np.ndarray, float] | None:
        cand = self.ray_candidates(pts, origin, direction, bound)
        if cand is None:
            hit = ray_triangles(pts, self.tris, origin, direction)
            if hit is None:
                return None
            j, point, t = hit
            return int(self.tri_face[j]), point, t
        if not len(cand):
            return None
        hit = ray_triangles(pts, self.tris[cand], origin, direction)
        if hit is None:
            return None
        j, point, t = hit
        return int(self.tri_face[cand[j]]), point, t


def ray_triangles(pts: np.ndarray, tris: np.ndarray, origin, direction):
    if not len(tris):
        return None
    o = np.asarray(origin, float)
    d = np.asarray(direction, float)
    length = float(np.linalg.norm(d))
    if length < 1e-12:
        return None
    d = d / length
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    e1, e2 = b - a, c - a
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) >= 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - a
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    ok &= (u >= -1e-9) & (u <= 1 + 1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 1e-9)
    if not ok.any():
        return None
    j = int(np.argmin(np.where(ok, t, np.inf)))
    return j, o + d * float(t[j]), float(t[j])


def get_topology(n_points: int, polygons: Sequence[Sequence[int]], key: str | None = None) -> Topology:
    sig = key or polygon_signature(n_points, polygons)
    topo = _CACHE.get(sig)
    if topo is None:
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        topo = _CACHE[sig] = Topology(n_points, polygons)
    return topo
