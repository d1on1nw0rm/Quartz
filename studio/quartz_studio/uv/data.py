from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Any, Iterable

import numpy as np

from ..ext import store

__all__ = [
    "UV_KEY",
    "SEAMS_KEY",
    "TAG_KEY",
    "Corners",
    "corners_of",
    "edge_key",
    "edge_corners",
    "uv_is_valid",
    "uv_to_array",
    "array_to_uv",
    "get_uv",
    "get_uv_array",
    "set_uv_array",
    "has_uv",
    "ensure_uv",
    "reset_uv",
    "planar_default",
    "get_seams",
    "set_seams",
    "add_seams",
    "remove_seams",
    "clear_seams",
    "sync_seams",
    "point_groups",
    "uv_islands",
    "island_of_polys",
    "corners_of_polys",
    "expand_to_points",
    "triangulate_polygon",
    "mesh_triangles",
    "polygon_area_3d",
    "polygon_area_uv",
    "bounds_uv",
    "transform_uv",
    "move_uv",
    "rotate_uv",
    "scale_uv",
    "UnionFind",
    "sync_all",
    "write_object",
    "write_scene",
    "finite_points",
    "finite_mesh",
    "components",
]

UV_KEY = "uv"
SEAMS_KEY = "uv_seams"
TAG_KEY = "uv_tag"
WELD_EPS = 1e-6
_TARGETS: list = []


@contextmanager
def write_scene(scene):
    _TARGETS.append(scene)
    try:
        yield scene
    finally:
        _TARGETS.pop()


def write_object(obj, key: str, value: Any) -> None:
    scene = _TARGETS[-1] if _TARGETS else None
    setter = getattr(scene, "set_object_extra", None) if scene is not None else None
    if setter is not None and any(o is obj for o in getattr(scene, "objects", ())):
        setter(obj, key, None if value is None else store.to_json(value))
        store.notify(obj, key)
        return
    store.set_object(obj, key, value)


def finite_points(points) -> np.ndarray:
    pts = np.asarray(points, float)
    if not len(pts):
        return pts.reshape(-1, 3) if pts.ndim != 2 else pts
    good = np.isfinite(pts).all(axis=1)
    if good.all():
        return pts
    out = pts.copy()
    fill = out[good].mean(axis=0) if good.any() else np.zeros(pts.shape[1])
    out[~good] = fill
    return out


def finite_mesh(mesh):
    pts = getattr(mesh, "points", None)
    if pts is None or not len(pts) or np.isfinite(pts).all():
        return mesh
    from ..scene import Mesh
    return Mesh(finite_points(pts), mesh.polygons, getattr(mesh, "loose_edges", ()))


def components(n: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    parent = np.arange(n, dtype=np.int64)
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    if not len(a) or n == 0:
        return parent
    while True:
        pa, pb = parent[a], parent[b]
        diff = pa != pb
        if not diff.any():
            break
        hi = np.maximum(pa[diff], pb[diff])
        lo = np.minimum(pa[diff], pb[diff])
        np.minimum.at(parent, hi, lo)
        while True:
            nxt = parent[parent]
            if np.array_equal(nxt, parent):
                break
            parent = nxt
    return parent


class UnionFind:

    def __init__(self, n: int) -> None:
        self.parent = np.arange(n, dtype=np.int64)

    def find(self, a: int) -> int:
        parent = self.parent
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return int(root)

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb

    def labels(self) -> np.ndarray:
        n = len(self.parent)
        roots = np.array([self.find(i) for i in range(n)], dtype=np.int64)
        _, inv = np.unique(roots, return_inverse=True)
        return inv.reshape(-1)


def edge_key(a: int, b: int) -> tuple[int, int]:
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


class Corners:

    def __init__(self, mesh) -> None:
        polys = mesh.polygons
        sizes = np.array([len(p) for p in polys], dtype=np.int64)
        self.sizes = sizes
        self.starts = np.zeros(len(sizes) + 1, dtype=np.int64)
        if len(sizes):
            self.starts[1:] = np.cumsum(sizes)
        self.count = int(self.starts[-1])
        self.poly_count = len(sizes)
        if self.count:
            self.vertex = np.fromiter((i for p in polys for i in p), dtype=np.int64, count=self.count)
        else:
            self.vertex = np.zeros(0, dtype=np.int64)
        self.poly = np.repeat(np.arange(len(sizes), dtype=np.int64), sizes)
        base = self.starts[:-1][self.poly] if self.count else np.zeros(0, dtype=np.int64)
        local = np.arange(self.count, dtype=np.int64) - base
        sz = sizes[self.poly] if self.count else np.ones(0, dtype=np.int64)
        self.local = local
        self.next = base + (local + 1) % np.maximum(sz, 1)
        self.prev = base + (local - 1) % np.maximum(sz, 1)
        self._edges: dict | None = None
        self._pairs: tuple[np.ndarray, np.ndarray] | None = None

    def edge_pairs(self) -> tuple[np.ndarray, np.ndarray]:
        if self._pairs is not None:
            return self._pairs
        empty = (np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
        if not self.count:
            self._pairs = empty
            return empty
        va = self.vertex
        vb = self.vertex[self.next]
        valid = np.nonzero(va != vb)[0]
        if not len(valid):
            self._pairs = empty
            return empty
        lo = np.minimum(va[valid], vb[valid])
        hi = np.maximum(va[valid], vb[valid])
        m = int(max(int(hi.max()), 0)) + 1
        key = lo * m + hi
        order = np.argsort(key, kind="stable")
        sk = key[order]
        sc = valid[order]
        brk = np.nonzero(np.diff(sk) != 0)[0] + 1
        starts = np.concatenate([[0], brk])
        lengths = np.diff(np.concatenate([starts, [len(sk)]]))
        two = starts[lengths == 2]
        first = [sc[two]]
        second = [sc[two + 1]]
        for s, n in zip(starts[lengths > 2].tolist(), lengths[lengths > 2].tolist()):
            run = sc[s:s + n]
            ii, jj = np.triu_indices(n, 1)
            first.append(run[ii])
            second.append(run[jj])
        self._pairs = (np.concatenate(first).astype(np.int64), np.concatenate(second).astype(np.int64))
        return self._pairs

    def of(self, poly: int) -> range:
        return range(int(self.starts[poly]), int(self.starts[poly + 1]))

    def edges(self) -> dict[tuple[int, int], list[int]]:
        if self._edges is None:
            out: dict[tuple[int, int], list[int]] = {}
            vert = self.vertex.tolist()
            nxt = self.next.tolist()
            for c in range(self.count):
                a, b = vert[c], vert[nxt[c]]
                if a == b:
                    continue
                key = (a, b) if a < b else (b, a)
                lst = out.get(key)
                if lst is None:
                    out[key] = [c]
                else:
                    lst.append(c)
            self._edges = out
        return self._edges

    def corner_of(self, poly: int, vertex: int) -> int | None:
        for c in self.of(poly):
            if int(self.vertex[c]) == int(vertex):
                return c
        return None


def corners_of(mesh) -> Corners:
    return Corners(mesh)


def edge_corners(corners: Corners, a: int, b: int) -> list[int]:
    return list(corners.edges().get(edge_key(a, b), []))


def uv_is_valid(uv, mesh) -> bool:
    if not isinstance(uv, (list, tuple)) or len(uv) != len(mesh.polygons):
        return False
    for ring, poly in zip(uv, mesh.polygons):
        if not isinstance(ring, (list, tuple, np.ndarray)) or len(ring) != len(poly):
            return False
    return True


def uv_to_array(uv, corners: Corners) -> np.ndarray:
    out = np.zeros((corners.count, 2), dtype=float)
    if corners.count == 0:
        return out
    flat = [pt for ring in uv for pt in ring]
    arr = np.asarray(flat, dtype=float).reshape(-1, 2)
    out[:len(arr)] = arr[:corners.count]
    out[~np.isfinite(out)] = 0.0
    return out


def array_to_uv(arr: np.ndarray, corners: Corners) -> list:
    arr = np.asarray(arr, dtype=float).reshape(-1, 2)
    vals = arr.tolist()
    starts = corners.starts.tolist()
    return [vals[starts[p]:starts[p + 1]] for p in range(corners.poly_count)]


def has_uv(obj) -> bool:
    return uv_is_valid(store.get_object(obj, UV_KEY), obj.mesh)


def get_uv(obj) -> list | None:
    uv = store.get_object(obj, UV_KEY)
    if isinstance(uv, dict):
        uv = store.from_json(uv)
    if isinstance(uv, np.ndarray):
        uv = uv.tolist()
    return uv if isinstance(uv, (list, tuple)) else None


def _basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = np.asarray(normal, float)
    length = np.linalg.norm(n)
    n = n / length if length > 1e-12 else np.array([0.0, 0.0, 1.0])
    up = np.array([0.0, 1.0, 0.0])
    if abs(n @ up) > 0.999:
        up = np.array([0.0, 0.0, -1.0]) if n[1] > 0 else np.array([0.0, 0.0, 1.0])
    eu = np.cross(up, n)
    eu /= max(np.linalg.norm(eu), 1e-12)
    ev = np.cross(n, eu)
    return eu, ev


def planar_default(mesh, corners: Corners | None = None) -> np.ndarray:
    corners = corners or Corners(mesh)
    if corners.count == 0:
        return np.zeros((0, 2))
    pts = finite_points(mesh.points)
    size = pts.max(axis=0) - pts.min(axis=0) if len(pts) else np.ones(3)
    axis = int(np.argmin(size))
    normal = np.zeros(3)
    normal[axis] = 1.0
    eu, ev = _basis(normal)
    p = pts[corners.vertex]
    uv = np.stack([p @ eu, p @ ev], axis=1)
    lo = uv.min(axis=0)
    span = float(max((uv.max(axis=0) - lo).max(), 1e-12))
    uv = (uv - lo) / span
    extent = uv.max(axis=0)
    return uv + (1.0 - extent) / 2.0


def get_uv_array(obj, corners: Corners | None = None, *, write: bool = False) -> np.ndarray:
    mesh = obj.mesh
    corners = corners or Corners(mesh)
    uv = get_uv(obj)
    if uv is not None and uv_is_valid(uv, mesh):
        return uv_to_array(uv, corners)
    arr = _repair(uv, mesh, corners)
    if write:
        set_uv_array(obj, arr, corners)
    return arr


def _repair(uv, mesh, corners: Corners) -> np.ndarray:
    base = planar_default(mesh, corners)
    if uv is None or not isinstance(uv, (list, tuple)) or len(uv) != len(mesh.polygons):
        return base
    out = base.copy()
    for p, (ring, poly) in enumerate(zip(uv, mesh.polygons)):
        try:
            vals = np.asarray(ring, dtype=float).reshape(-1, 2)
        except (TypeError, ValueError):
            continue
        if len(vals) == len(poly) and np.all(np.isfinite(vals)):
            out[corners.starts[p]:corners.starts[p + 1]] = vals
    return out


def set_uv_array(obj, arr: np.ndarray, corners: Corners | None = None) -> None:
    corners = corners or Corners(obj.mesh)
    arr = np.asarray(arr, dtype=float).reshape(-1, 2)
    if len(arr) != corners.count:
        raise ValueError(f"uv array has {len(arr)} corners, mesh has {corners.count}")
    arr = np.where(np.isfinite(arr), arr, 0.0)
    write_object(obj, UV_KEY, array_to_uv(arr, corners))


def ensure_uv(obj) -> bool:
    uv = get_uv(obj)
    if uv is not None and uv_is_valid(uv, obj.mesh):
        changed = sync_seams(obj)
        return changed
    corners = Corners(obj.mesh)
    set_uv_array(obj, _repair(uv, obj.mesh, corners), corners)
    sync_seams(obj)
    return True


def reset_uv(obj) -> None:
    corners = Corners(obj.mesh)
    set_uv_array(obj, planar_default(obj.mesh, corners), corners)


def get_seams(obj) -> set[tuple[int, int]]:
    raw = store.get_object(obj, SEAMS_KEY)
    if isinstance(raw, dict):
        raw = store.from_json(raw)
    out: set[tuple[int, int]] = set()
    if not raw:
        return out
    for e in raw:
        try:
            a, b = int(e[0]), int(e[1])
        except (TypeError, ValueError, IndexError):
            continue
        if a != b:
            out.add(edge_key(a, b))
    return out


def set_seams(obj, seams: Iterable) -> None:
    keys = sorted({edge_key(e[0], e[1]) for e in seams if int(e[0]) != int(e[1])})
    write_object(obj, SEAMS_KEY, [list(k) for k in keys] if keys else None)


def add_seams(obj, edges: Iterable) -> int:
    seams = get_seams(obj)
    before = len(seams)
    valid = set(obj.mesh.polygon_edges())
    seams.update(edge_key(e[0], e[1]) for e in edges if edge_key(e[0], e[1]) in valid)
    set_seams(obj, seams)
    return len(seams) - before


def remove_seams(obj, edges: Iterable) -> int:
    seams = get_seams(obj)
    before = len(seams)
    seams.difference_update(edge_key(e[0], e[1]) for e in edges)
    set_seams(obj, seams)
    return before - len(seams)


def clear_seams(obj) -> None:
    write_object(obj, SEAMS_KEY, None)


def sync_seams(obj) -> bool:
    seams = get_seams(obj)
    if not seams:
        return False
    valid = set(obj.mesh.polygon_edges())
    kept = seams & valid
    if kept != seams:
        set_seams(obj, kept)
        return True
    return False


def point_groups(corners: Corners, uv: np.ndarray, eps: float = WELD_EPS) -> np.ndarray:
    if corners.count == 0:
        return np.zeros(0, dtype=np.int64)
    arr = np.asarray(uv, float)
    arr = np.where(np.isfinite(arr), arr, 0.0)
    q = np.round(np.clip(arr / eps, -4e18, 4e18)).astype(np.int64)
    key = np.stack([corners.vertex, q[:, 0], q[:, 1]], axis=1)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    return inv.reshape(-1)


def uv_islands(mesh, uv: np.ndarray, corners: Corners | None = None,
               polys: Iterable[int] | None = None, eps: float = WELD_EPS) -> list[list[int]]:
    corners = corners or Corners(mesh)
    n = corners.poly_count
    if n == 0:
        return []
    uv = np.asarray(uv, float)
    vert = corners.vertex
    nxt = corners.next
    poly = corners.poly
    c1, c2 = corners.edge_pairs()
    if polys is None:
        targets = np.arange(n, dtype=np.int64)
        allowed = None
    else:
        targets = np.array(sorted({int(p) for p in polys if 0 <= int(p) < n}), dtype=np.int64)
        allowed = np.zeros(n, dtype=bool)
        allowed[targets] = True
    if not len(targets):
        return []
    if len(c1):
        p1, p2 = poly[c1], poly[c2]
        keep = np.ones(len(c1), dtype=bool) if allowed is None else (allowed[p1] & allowed[p2])
        c1, c2, p1, p2 = c1[keep], c2[keep], p1[keep], p2[keep]
        a1, b1 = c1, nxt[c1]
        same = vert[c2] == vert[c1]
        a2 = np.where(same, c2, nxt[c2])
        b2 = np.where(same, nxt[c2], c2)
        with np.errstate(invalid="ignore"):
            match = ((np.abs(uv[a1] - uv[a2]).max(axis=1) <= eps)
                     & (np.abs(uv[b1] - uv[b2]).max(axis=1) <= eps)) if len(c1) else np.zeros(0, bool)
        labels = components(n, p1[match], p2[match])
    else:
        labels = np.arange(n, dtype=np.int64)
    lab = labels[targets]
    order = np.argsort(lab, kind="stable")
    sl = lab[order]
    st = targets[order]
    brk = np.nonzero(np.diff(sl) != 0)[0] + 1
    groups = [g.tolist() for g in np.split(st, brk)]
    groups.sort(key=lambda g: g[0])
    return groups


def island_of_polys(islands: list[list[int]], polys: Iterable[int]) -> list[list[int]]:
    wanted = set(int(p) for p in polys)
    return [isl for isl in islands if wanted.intersection(isl)]


def corners_of_polys(corners: Corners, polys: Iterable[int]) -> np.ndarray:
    idx = [c for p in polys for c in corners.of(int(p))]
    return np.array(sorted(set(idx)), dtype=np.int64)


def expand_to_points(corners: Corners, uv: np.ndarray, selected: Iterable[int]) -> np.ndarray:
    sel = np.array(sorted(set(int(c) for c in selected)), dtype=np.int64)
    if not len(sel):
        return sel
    groups = point_groups(corners, uv)
    wanted = np.zeros(groups.max() + 1, dtype=bool)
    wanted[groups[sel]] = True
    return np.nonzero(wanted[groups])[0]


def _newell(ring: np.ndarray) -> np.ndarray:
    nxt = np.roll(ring, -1, axis=0)
    return np.array([
        np.sum((ring[:, 1] - nxt[:, 1]) * (ring[:, 2] + nxt[:, 2])),
        np.sum((ring[:, 2] - nxt[:, 2]) * (ring[:, 0] + nxt[:, 0])),
        np.sum((ring[:, 0] - nxt[:, 0]) * (ring[:, 1] + nxt[:, 1])),
    ])


def _flatten_ring(ring: np.ndarray) -> np.ndarray:
    n = _newell(ring)
    if ring.shape[1] == 2:
        return ring
    eu, ev = _basis(n)
    return np.stack([ring @ eu, ring @ ev], axis=1)


def _area2(flat: np.ndarray) -> float:
    x, y = flat[:, 0], flat[:, 1]
    return float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) * 0.5


def triangulate_polygon(ring: np.ndarray) -> list[tuple[int, int, int]]:
    ring = np.asarray(ring, float)
    n = len(ring)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    flat = _flatten_ring(ring)
    if _area2(flat) < 0:
        flat = flat * np.array([1.0, -1.0])
    if n == 4:
        def convex(a, b, c):
            return ((flat[b, 0] - flat[a, 0]) * (flat[c, 1] - flat[a, 1])
                    - (flat[b, 1] - flat[a, 1]) * (flat[c, 0] - flat[a, 0]))
        d02 = float(np.linalg.norm(ring[0] - ring[2]))
        d13 = float(np.linalg.norm(ring[1] - ring[3]))
        ok02 = convex(0, 1, 2) > 0 and convex(0, 2, 3) > 0
        ok13 = convex(1, 2, 3) > 0 and convex(1, 3, 0) > 0
        if ok02 and (not ok13 or d02 <= d13 + 1e-12):
            return [(0, 1, 2), (0, 2, 3)]
        if ok13:
            return [(1, 2, 3), (1, 3, 0)]
        return [(0, 1, 2), (0, 2, 3)]
    idx = list(range(n))
    tris: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3 and guard < 4 * n * n:
        guard += 1
        best = None
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = flat[i0], flat[i1], flat[i2]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cross <= 1e-14:
                continue
            inside = False
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = flat[j]
                d1 = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
                d2 = (c[0] - b[0]) * (p[1] - b[1]) - (c[1] - b[1]) * (p[0] - b[0])
                d3 = (a[0] - c[0]) * (p[1] - c[1]) - (a[1] - c[1]) * (p[0] - c[0])
                if d1 >= 0 and d2 >= 0 and d3 >= 0:
                    inside = True
                    break
            if not inside:
                best = k
                break
        if best is None:
            break
        k = best
        tris.append((idx[k - 1], idx[k], idx[(k + 1) % len(idx)]))
        idx.pop(k)
    if len(idx) > 3:
        tris.extend((idx[0], idx[m], idx[m + 1]) for m in range(1, len(idx) - 1))
    elif len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def mesh_triangles(mesh, corners: Corners | None = None,
                   polys: Iterable[int] | None = None) -> tuple[np.ndarray, np.ndarray]:
    corners = corners or Corners(mesh)
    if polys is None:
        targets = np.arange(corners.poly_count, dtype=np.int64)
    else:
        targets = np.array(sorted({int(p) for p in polys}), dtype=np.int64)
    if not len(targets):
        return np.zeros((0, 3), dtype=np.int64), np.zeros(0, dtype=np.int64)
    sizes = corners.sizes[targets]
    starts = corners.starts
    pts = mesh.points
    tris: list[np.ndarray] = []
    owners: list[np.ndarray] = []
    tp = targets[sizes == 3]
    if len(tp):
        s = starts[tp]
        tris.append(np.stack([s, s + 1, s + 2], axis=1))
        owners.append(tp)
    qp = targets[sizes == 4]
    if len(qp):
        s = starts[qp]
        c = s[:, None] + np.arange(4)[None, :]
        q = pts[corners.vertex[c]]
        n = np.cross(q[:, 2] - q[:, 0], q[:, 3] - q[:, 1])

        def side(a: int, b: int, d: int) -> np.ndarray:
            return np.einsum("ij,ij->i", np.cross(q[:, b] - q[:, a], q[:, d] - q[:, a]), n)

        ok02 = (side(0, 1, 2) > 0) & (side(0, 2, 3) > 0)
        ok13 = (side(1, 2, 3) > 0) & (side(1, 3, 0) > 0)
        d02 = np.linalg.norm(q[:, 0] - q[:, 2], axis=1)
        d13 = np.linalg.norm(q[:, 1] - q[:, 3], axis=1)
        use02 = (ok02 & (~ok13 | (d02 <= d13 + 1e-12))) | (~ok02 & ~ok13)
        first = np.where(use02[:, None], c[:, [0, 1, 2]], c[:, [1, 2, 3]])
        second = np.where(use02[:, None], c[:, [0, 2, 3]], c[:, [1, 3, 0]])
        tris.append(np.concatenate([first, second], axis=0))
        owners.append(np.concatenate([qp, qp]))
    for p in targets[sizes > 4].tolist():
        start = int(starts[p])
        size = int(corners.sizes[p])
        ring = pts[corners.vertex[start:start + size]]
        local = triangulate_polygon(ring)
        if local:
            tris.append(np.array(local, dtype=np.int64) + start)
            owners.append(np.full(len(local), p, dtype=np.int64))
    if not tris:
        return np.zeros((0, 3), dtype=np.int64), np.zeros(0, dtype=np.int64)
    return np.concatenate(tris, axis=0).astype(np.int64), np.concatenate(owners).astype(np.int64)


def polygon_area_3d(mesh, corners: Corners | None = None) -> np.ndarray:
    corners = corners or Corners(mesh)
    out = np.zeros(corners.poly_count)
    if corners.count == 0:
        return out
    pts = finite_points(mesh.points)
    a = pts[corners.vertex]
    b = pts[corners.vertex[corners.next]]
    contrib = np.stack([(a[:, 1] - b[:, 1]) * (a[:, 2] + b[:, 2]),
                        (a[:, 2] - b[:, 2]) * (a[:, 0] + b[:, 0]),
                        (a[:, 0] - b[:, 0]) * (a[:, 1] + b[:, 1])], axis=1)
    normals = np.zeros((corners.poly_count, 3))
    np.add.at(normals, corners.poly, contrib)
    out = 0.5 * np.linalg.norm(normals, axis=1)
    out[corners.sizes < 3] = 0.0
    return out


def polygon_area_uv(uv: np.ndarray, corners: Corners) -> np.ndarray:
    uv = np.asarray(uv, float)
    out = np.zeros(corners.poly_count)
    if corners.count == 0:
        return out
    x, y = uv[:, 0], uv[:, 1]
    nx, ny = x[corners.next], y[corners.next]
    cross = x * ny - nx * y
    np.add.at(out, corners.poly, cross)
    return out * 0.5


def bounds_uv(uv: np.ndarray, idx=None) -> tuple[np.ndarray, np.ndarray]:
    uv = np.asarray(uv, float)
    pts = uv if idx is None else uv[np.asarray(idx, dtype=np.int64)]
    if not len(pts):
        return np.zeros(2), np.zeros(2)
    return pts.min(axis=0), pts.max(axis=0)


def transform_uv(uv: np.ndarray, idx, matrix: np.ndarray, pivot=(0.0, 0.0),
                 offset=(0.0, 0.0)) -> np.ndarray:
    out = np.array(uv, dtype=float, copy=True)
    idx = np.asarray(idx, dtype=np.int64)
    if not len(idx):
        return out
    piv = np.asarray(pivot, float)
    m = np.asarray(matrix, float).reshape(2, 2)
    out[idx] = (out[idx] - piv) @ m.T + piv + np.asarray(offset, float)
    return out


def move_uv(uv: np.ndarray, idx, delta) -> np.ndarray:
    return transform_uv(uv, idx, np.eye(2), offset=delta)


def rotate_uv(uv: np.ndarray, idx, degrees: float, pivot=None) -> np.ndarray:
    idx = np.asarray(idx, dtype=np.int64)
    if pivot is None:
        lo, hi = bounds_uv(uv, idx)
        pivot = (lo + hi) / 2.0
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    if abs(round(degrees / 90.0) * 90.0 - degrees) < 1e-9:
        c, s = round(c), round(s)
    return transform_uv(uv, idx, np.array([[c, -s], [s, c]]), pivot)


def scale_uv(uv: np.ndarray, idx, sx: float, sy: float | None = None, pivot=None) -> np.ndarray:
    idx = np.asarray(idx, dtype=np.int64)
    sy = sx if sy is None else sy
    if pivot is None:
        lo, hi = bounds_uv(uv, idx)
        pivot = (lo + hi) / 2.0
    return transform_uv(uv, idx, np.diag([float(sx), float(sy)]), pivot)


def sync_all(scene) -> int:
    fixed = 0
    for obj in list(getattr(scene, "objects", ())):
        if getattr(obj, "mesh", None) is None:
            continue
        if store.get_object(obj, UV_KEY) is not None and not has_uv(obj):
            ensure_uv(obj)
            fixed += 1
        elif get_seams(obj):
            if sync_seams(obj):
                fixed += 1
    return fixed
