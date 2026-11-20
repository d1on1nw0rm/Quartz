from __future__ import annotations

import heapq
import math
from typing import Iterable

import numpy as np

from .data import (Corners, UnionFind, components, corners_of_polys, edge_key, finite_mesh, finite_points,
                   get_seams, get_uv_array, mesh_triangles, point_groups, set_uv_array, triangulate_polygon,
                   uv_islands)

__all__ = [
    "UNWRAP_METHODS",
    "RELAX_METHODS",
    "Chart",
    "angle_seams",
    "seam_islands",
    "build_chart",
    "chart_from_uv",
    "chart_topology",
    "cut_to_disc",
    "lscm",
    "arap",
    "spring_relax",
    "unwrap",
    "relax",
]

UNWRAP_METHODS = ("Conformal", "Isometric")
RELAX_METHODS = ("ARAP", "Springs")
DENSE_LIMIT = 900


class Chart:

    def __init__(self, corner_index: np.ndarray, labels: np.ndarray, positions: np.ndarray,
                 faces: list[list[int]], tris: np.ndarray, polys: list[int], vertex_of: np.ndarray) -> None:
        self.corner_index = corner_index
        self.labels = labels
        self.positions = positions
        self.faces = faces
        self.tris = tris
        self.polys = polys
        self.vertex_of = vertex_of
        self._edges: dict | None = None

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    def edge_use(self) -> dict[tuple[int, int], int]:
        if self._edges is None:
            out: dict[tuple[int, int], int] = {}
            for f in self.faces:
                for a, b in zip(f, f[1:] + f[:1]):
                    if a != b:
                        k = (a, b) if a < b else (b, a)
                        out[k] = out.get(k, 0) + 1
            self._edges = out
        return self._edges

    def boundary_edges(self) -> list[tuple[int, int]]:
        return [k for k, n in self.edge_use().items() if n == 1]

    def interior_edges(self) -> list[tuple[int, int]]:
        return [k for k, n in self.edge_use().items() if n == 2]

    def boundary_vertices(self) -> np.ndarray:
        flags = np.zeros(self.vertex_count, dtype=bool)
        for a, b in self.boundary_edges():
            flags[a] = flags[b] = True
        return flags


def angle_seams(mesh, angle_deg: float, corners: Corners | None = None) -> set[tuple[int, int]]:
    corners = corners or Corners(mesh)
    normals = mesh.polygon_normals()
    limit = math.cos(math.radians(float(angle_deg)))
    out: set[tuple[int, int]] = set()
    for key, cs in corners.edges().items():
        polys = sorted({int(corners.poly[c]) for c in cs})
        if len(polys) != 2:
            if len(polys) > 2:
                out.add(key)
            continue
        if float(normals[polys[0]] @ normals[polys[1]]) < limit - 1e-9:
            out.add(key)
    return out


def seam_islands(mesh, seams: set, corners: Corners | None = None,
                 polys: Iterable[int] | None = None) -> list[list[int]]:
    corners = corners or Corners(mesh)
    n = corners.poly_count
    if n == 0:
        return []
    if polys is None:
        targets = np.arange(n, dtype=np.int64)
    else:
        targets = np.array(sorted({int(p) for p in polys if 0 <= int(p) < n}), dtype=np.int64)
    if not len(targets):
        return []
    allowed = np.zeros(n, dtype=bool)
    allowed[targets] = True
    vert, nxt, poly = corners.vertex, corners.next, corners.poly
    nv = int(vert.max()) + 1 if len(vert) else 1
    for e in seams:
        nv = max(nv, int(e[0]) + 1, int(e[1]) + 1)
    va, vb = vert, vert[nxt]
    good = (va != vb) & allowed[poly]
    keys_all = np.minimum(va[good], vb[good]) * nv + np.maximum(va[good], vb[good])
    uk, counts = np.unique(keys_all, return_counts=True)
    c1, c2 = corners.edge_pairs()
    p1, p2 = poly[c1], poly[c2]
    keep = allowed[p1] & allowed[p2] & (p1 != p2)
    c1, p1, p2 = c1[keep], p1[keep], p2[keep]
    pk = np.minimum(vert[c1], vert[nxt[c1]]) * nv + np.maximum(vert[c1], vert[nxt[c1]])
    if len(uk):
        pos = np.clip(np.searchsorted(uk, pk), 0, len(uk) - 1)
        ok = (uk[pos] == pk) & (counts[pos] == 2)
    else:
        ok = np.zeros(len(pk), dtype=bool)
    if seams:
        seam_keys = np.array([min(int(a), int(b)) * nv + max(int(a), int(b)) for a, b in seams], dtype=np.int64)
        ok &= ~np.isin(pk, seam_keys)
    labels = components(n, p1[ok], p2[ok])
    lab = labels[targets]
    order = np.argsort(lab, kind="stable")
    brk = np.nonzero(np.diff(lab[order]) != 0)[0] + 1
    groups = [g.tolist() for g in np.split(targets[order], brk)]
    groups.sort(key=lambda g: g[0])
    return groups


def _chart(mesh, corners: Corners, polys: list[int], cidx: np.ndarray, labels: np.ndarray) -> Chart:
    local = {int(c): i for i, c in enumerate(cidx)}
    nv = int(labels.max()) + 1 if len(labels) else 0
    positions = np.zeros((nv, 3))
    vertex_of = np.zeros(nv, dtype=np.int64)
    verts = corners.vertex[cidx]
    positions[labels] = finite_points(mesh.points)[verts]
    vertex_of[labels] = verts
    faces: list[list[int]] = []
    lab = labels.tolist()
    for p in polys:
        faces.append([lab[local[c]] for c in corners.of(p)])
    tri_c, _ = mesh_triangles(mesh, corners, polys)
    tris = labels[np.searchsorted(cidx, tri_c)] if len(tri_c) else np.zeros((0, 3), dtype=np.int64)
    return Chart(cidx, labels, positions, faces, np.asarray(tris, dtype=np.int64).reshape(-1, 3),
                 list(polys), vertex_of)


def build_chart(mesh, corners: Corners, polys: Iterable[int], cuts: set) -> Chart:
    polys = sorted({int(p) for p in polys})
    cidx = corners_of_polys(corners, polys)
    if not len(cidx):
        return _chart(mesh, corners, polys, cidx, np.zeros(0, dtype=np.int64))
    inset = np.zeros(corners.poly_count, dtype=bool)
    inset[polys] = True
    vert = corners.vertex
    nxt = corners.next
    nv = int(vert.max()) + 1 if len(vert) else 1
    for e in cuts:
        nv = max(nv, int(e[0]) + 1, int(e[1]) + 1)
    va, vb = vert[cidx], vert[nxt[cidx]]
    good = va != vb
    own_keys = np.minimum(va[good], vb[good]) * nv + np.maximum(va[good], vb[good])
    uk, counts = np.unique(own_keys, return_counts=True)
    c1, c2 = corners.edge_pairs()
    keep = inset[corners.poly[c1]] & inset[corners.poly[c2]]
    c1, c2 = c1[keep], c2[keep]
    pa, pb = vert[c1], vert[nxt[c1]]
    pk = np.minimum(pa, pb) * nv + np.maximum(pa, pb)
    pos = np.clip(np.searchsorted(uk, pk), 0, max(len(uk) - 1, 0))
    ok = (uk[pos] == pk) & (counts[pos] == 2) if len(uk) else np.zeros(len(pk), bool)
    if cuts:
        cut_keys = np.array([min(int(a), int(b)) * nv + max(int(a), int(b)) for a, b in cuts], dtype=np.int64)
        ok &= ~np.isin(pk, cut_keys)
    c1, c2 = c1[ok], c2[ok]
    n1, n2 = nxt[c1], nxt[c2]
    same = vert[c1] == vert[c2]
    left = np.concatenate([c1, n1])
    right = np.concatenate([np.where(same, c2, n2), np.where(same, n2, c2)])
    li = np.searchsorted(cidx, left)
    ri = np.searchsorted(cidx, right)
    roots = components(len(cidx), li, ri)
    _, labels = np.unique(roots, return_inverse=True)
    return _chart(mesh, corners, polys, cidx, labels.reshape(-1).astype(np.int64))


def chart_from_uv(mesh, corners: Corners, uv: np.ndarray, polys: Iterable[int]) -> Chart:
    polys = sorted({int(p) for p in polys})
    cidx = corners_of_polys(corners, polys)
    groups = point_groups(corners, uv)[cidx]
    _, labels = np.unique(groups, return_inverse=True)
    return _chart(mesh, corners, polys, cidx, labels.reshape(-1))


def chart_topology(chart: Chart) -> tuple[int, int]:
    use = chart.edge_use()
    used_vertices = {v for f in chart.faces for v in f}
    chi = len(used_vertices) - len(use) + len(chart.faces)
    bnd = [k for k, n in use.items() if n == 1]
    uf = UnionFind(chart.vertex_count)
    touched = set()
    for a, b in bnd:
        uf.union(a, b)
        touched.add(a)
        touched.add(b)
    loops = len({uf.find(v) for v in touched})
    return chi, loops


def _adjacency(chart: Chart, edges: Iterable[tuple[int, int]]) -> list[list[tuple[int, float]]]:
    adj: list[list[tuple[int, float]]] = [[] for _ in range(chart.vertex_count)]
    pos = chart.positions
    for a, b in edges:
        w = float(np.linalg.norm(pos[a] - pos[b])) + 1e-9
        adj[a].append((b, w))
        adj[b].append((a, w))
    return adj


def _dijkstra(adj, sources: Iterable[int], stop=None) -> tuple[np.ndarray, np.ndarray, int | None]:
    n = len(adj)
    dist = np.full(n, np.inf)
    prev = np.full(n, -1, dtype=np.int64)
    heap: list[tuple[float, int]] = []
    for s in sources:
        dist[s] = 0.0
        heap.append((0.0, int(s)))
    heapq.heapify(heap)
    done = np.zeros(n, dtype=bool)
    while heap:
        d, v = heapq.heappop(heap)
        if done[v]:
            continue
        done[v] = True
        if stop is not None and stop(v):
            return dist, prev, v
        for w, length in adj[v]:
            nd = d + length
            if nd < dist[w] - 1e-15:
                dist[w] = nd
                prev[w] = v
                heapq.heappush(heap, (nd, w))
    return dist, prev, None


def _path(prev: np.ndarray, end: int) -> list[tuple[int, int]]:
    out = []
    v = int(end)
    while prev[v] >= 0:
        out.append((int(prev[v]), v))
        v = int(prev[v])
    return out


def _mesh_edges(chart: Chart, class_edges: Iterable[tuple[int, int]]) -> set[tuple[int, int]]:
    return {edge_key(chart.vertex_of[a], chart.vertex_of[b]) for a, b in class_edges
            if chart.vertex_of[a] != chart.vertex_of[b]}


def _loop_labels(chart: Chart) -> dict[int, int]:
    uf = UnionFind(chart.vertex_count)
    touched = set()
    for a, b in chart.boundary_edges():
        uf.union(a, b)
        touched.update((a, b))
    return {v: uf.find(v) for v in touched}


def _cut_paths(chart: Chart) -> set[tuple[int, int]]:
    chi, loops = chart_topology(chart)
    interior = chart.interior_edges()
    adj = _adjacency(chart, interior)
    used = sorted({v for f in chart.faces for v in f})
    if not used:
        return set()
    if loops == 0:
        dist, _, _ = _dijkstra(adj, [used[0]])
        finite = np.where(np.isfinite(dist), dist, -1.0)
        a = int(np.argmax(finite))
        dist, prev, _ = _dijkstra(adj, [a])
        finite = np.where(np.isfinite(dist), dist, -1.0)
        b = int(np.argmax(finite))
        if b == a:
            return set()
        return _mesh_edges(chart, _path(prev, b))
    if loops >= 2:
        labels = _loop_labels(chart)
        groups: dict[int, list[int]] = {}
        for v, lab in labels.items():
            groups.setdefault(lab, []).append(v)
        order = sorted(groups.values(), key=lambda g: -len(g))
        first = set(order[0])
        others = {v for v in labels if v not in first}
        _, prev, hit = _dijkstra(adj, sorted(first), stop=lambda v: v in others)
        if hit is None:
            return set()
        return _mesh_edges(chart, _path(prev, hit))
    return set()


def _tree_cotree(chart: Chart) -> set[tuple[int, int]]:
    use = chart.edge_use()
    face_edges: dict[tuple[int, int], list[int]] = {}
    for fi, f in enumerate(chart.faces):
        for a, b in zip(f, f[1:] + f[:1]):
            if a != b:
                face_edges.setdefault((a, b) if a < b else (b, a), []).append(fi)
    interior = [k for k, n in use.items() if n == 2 and len(face_edges.get(k, ())) == 2]
    nbrs: list[list[tuple[int, tuple[int, int]]]] = [[] for _ in chart.faces]
    for k in interior:
        f1, f2 = face_edges[k]
        nbrs[f1].append((f2, k))
        nbrs[f2].append((f1, k))
    seen = np.zeros(len(chart.faces), dtype=bool)
    cotree: set[tuple[int, int]] = set()
    centroids = np.array([chart.positions[f].mean(axis=0) for f in chart.faces])
    root = int(np.argmin(np.linalg.norm(centroids - centroids.mean(axis=0), axis=1)))
    queue = [root]
    seen[root] = True
    head = 0
    while head < len(queue):
        f = queue[head]
        head += 1
        for g, k in nbrs[f]:
            if not seen[g]:
                seen[g] = True
                cotree.add(k)
                queue.append(g)
    cut = {k for k in interior if k not in cotree}
    degree = np.zeros(chart.vertex_count, dtype=np.int64)
    for a, b in list(cut) + [k for k, n in use.items() if n != 2]:
        degree[a] += 1
        degree[b] += 1
    changed = True
    while changed:
        changed = False
        for k in list(cut):
            a, b = k
            if degree[a] == 1 or degree[b] == 1:
                cut.discard(k)
                degree[a] -= 1
                degree[b] -= 1
                changed = True
    return _mesh_edges(chart, cut)


def cut_to_disc(mesh, corners: Corners, polys: list[int], seams: set,
                max_rounds: int = 16) -> tuple[Chart, set[tuple[int, int]]]:
    cuts = set(seams)
    chart = build_chart(mesh, corners, polys, cuts)
    for _ in range(max_rounds):
        chi, loops = chart_topology(chart)
        if chi == 1 and loops == 1:
            return chart, cuts
        extra = _cut_paths(chart) - cuts
        if not extra:
            break
        cuts |= extra
        chart = build_chart(mesh, corners, polys, cuts)
    chi, loops = chart_topology(chart)
    if chi != 1 or loops != 1:
        extra = _tree_cotree(chart) - cuts
        if extra:
            cuts |= extra
            chart = build_chart(mesh, corners, polys, cuts)
    return chart, cuts


def _local_frames(P: np.ndarray, tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p0, p1, p2 = P[tris[:, 0]], P[tris[:, 1]], P[tris[:, 2]]
    e1 = p1 - p0
    e2 = p2 - p0
    n = np.cross(e1, e2)
    area2 = np.linalg.norm(n, axis=1)
    l1 = np.linalg.norm(e1, axis=1)
    ok = (area2 > 1e-14 * np.maximum(l1 * l1, 1e-300)) & (l1 > 0)
    ex = e1 / np.maximum(l1, 1e-300)[:, None]
    nn = n / np.maximum(area2, 1e-300)[:, None]
    ey = np.cross(nn, ex)
    q = np.zeros((len(tris), 3, 2))
    q[:, 1, 0] = l1
    q[:, 2, 0] = np.einsum("ij,ij->i", e2, ex)
    q[:, 2, 1] = np.einsum("ij,ij->i", e2, ey)
    return q, ok


class _Coo:

    def __init__(self, rows, cols, vals, size: int) -> None:
        rows = np.asarray(rows, dtype=np.int64)
        cols = np.asarray(cols, dtype=np.int64)
        vals = np.asarray(vals, dtype=float)
        if len(rows):
            key = rows * max(size, 1) + cols
            uniq, inv = np.unique(key, return_inverse=True)
            vals = np.bincount(inv.reshape(-1), weights=vals, minlength=len(uniq))
            rows = uniq // max(size, 1)
            cols = uniq % max(size, 1)
        self.rows = rows
        self.cols = cols
        self.vals = vals
        self.size = size

    def matvec(self, x: np.ndarray) -> np.ndarray:
        if x.ndim == 1:
            return np.bincount(self.rows, weights=self.vals * x[self.cols], minlength=self.size)
        return np.stack([self.matvec(x[:, k]) for k in range(x.shape[1])], axis=1)

    def diagonal(self) -> np.ndarray:
        mask = self.rows == self.cols
        return np.bincount(self.rows[mask], weights=self.vals[mask], minlength=self.size)

    def dense(self) -> np.ndarray:
        out = np.zeros((self.size, self.size))
        np.add.at(out, (self.rows, self.cols), self.vals)
        return out


def _pcg(A: _Coo, b: np.ndarray, x0: np.ndarray, tol: float = 1e-10, max_iter: int = 4000) -> np.ndarray:
    diag = A.diagonal()
    inv = np.where(np.abs(diag) > 1e-300, 1.0 / np.where(np.abs(diag) > 1e-300, diag, 1.0), 1.0)
    if b.ndim == 2:
        return np.stack([_pcg(A, b[:, k], x0[:, k], tol, max_iter) for k in range(b.shape[1])], axis=1)
    x = x0.astype(float).copy()
    r = b - A.matvec(x)
    z = inv * r
    p = z.copy()
    rz = float(r @ z)
    anorm = float(np.abs(np.bincount(A.rows, weights=np.abs(A.vals), minlength=A.size)).max()) if A.size else 0.0
    bnorm = max(float(np.linalg.norm(b)), 1e-300)
    for _ in range(max_iter):
        if float(np.linalg.norm(r)) <= tol * (bnorm + anorm * float(np.linalg.norm(x))):
            break
        Ap = A.matvec(p)
        denom = float(p @ Ap)
        if abs(denom) < 1e-300:
            break
        alpha = rz / denom
        x += alpha * p
        r -= alpha * Ap
        z = inv * r
        rz_new = float(r @ z)
        p = z + (rz_new / max(rz, 1e-300)) * p
        rz = rz_new
    return x


def _solve(rows, cols, vals, size: int, b: np.ndarray, x0: np.ndarray) -> np.ndarray:
    A = _Coo(rows, cols, vals, size)
    diag = A.diagonal()
    reg = 1e-12 * max(float(np.abs(diag).mean()) if size else 1.0, 1e-300)
    if size <= DENSE_LIMIT:
        M = A.dense()
        M[np.diag_indices(size)] += reg
        try:
            return np.linalg.solve(M, b)
        except np.linalg.LinAlgError:
            return np.linalg.lstsq(M, b, rcond=None)[0]
    A = _Coo(np.concatenate([A.rows, np.arange(size)]), np.concatenate([A.cols, np.arange(size)]),
             np.concatenate([A.vals, np.full(size, reg)]), size)
    return _pcg(A, b, x0)


def _far_pair(P: np.ndarray, candidates: np.ndarray) -> tuple[int, int]:
    c = np.asarray(candidates, dtype=np.int64)
    if len(c) < 2:
        return int(c[0]) if len(c) else 0, int(c[0]) if len(c) else 0
    pts = P[c]
    a = int(np.argmax(np.linalg.norm(pts - pts.mean(axis=0), axis=1)))
    b = int(np.argmax(np.linalg.norm(pts - pts[a], axis=1)))
    a = int(np.argmax(np.linalg.norm(pts - pts[b], axis=1)))
    return int(c[a]), int(c[b])


def _initial_guess(Q: np.ndarray, used: np.ndarray, tris: np.ndarray, pins: dict) -> np.ndarray:
    n = len(Q)
    out = np.zeros((n, 2))
    if not used.any():
        return out
    center = Q[used].mean(axis=0)
    d = Q[used] - center
    try:
        _, _, vt = np.linalg.svd(d, full_matrices=False)
    except np.linalg.LinAlgError:
        return out
    axes = vt[:2] if len(vt) >= 2 else np.eye(3)[:2]
    Y = (Q - center) @ axes.T
    if len(tris):
        a, b, c = Y[tris[:, 0]], Y[tris[:, 1]], Y[tris[:, 2]]
        signed = ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])).sum()
        if signed < 0:
            Y[:, 1] = -Y[:, 1]
    keys = list(pins)
    if len(keys) >= 2:
        ka, kb = keys[0], keys[1]
        za, zb = complex(*Y[ka]), complex(*Y[kb])
        wa, wb = complex(*pins[ka]), complex(*pins[kb])
        alpha = (wb - wa) / (zb - za) if abs(zb - za) > 1e-300 else 1.0 + 0j
        beta = wa - alpha * za
        z = alpha * (Y[:, 0] + 1j * Y[:, 1]) + beta
        Y = np.stack([z.real, z.imag], axis=1)
    elif len(keys) == 1:
        Y = Y - Y[keys[0]] + np.asarray(pins[keys[0]], float)
    out[:] = np.where(np.isfinite(Y), Y, 0.0)
    return out


def lscm(P: np.ndarray, tris: np.ndarray, pins: dict[int, tuple[float, float]] | None = None,
         boundary: np.ndarray | None = None) -> np.ndarray:
    P = np.asarray(P, float)
    tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
    n = len(P)
    if n == 0:
        return np.zeros((0, 2))
    used = np.zeros(n, dtype=bool)
    used[tris.reshape(-1)] = True
    scale = 1.0
    if len(tris):
        e = P[tris[:, 1]] - P[tris[:, 0]]
        scale = float(np.mean(np.linalg.norm(e, axis=1))) or 1.0
    Q = (P - P[used].mean(axis=0) if used.any() else P) / scale
    q, ok = _local_frames(Q, tris)
    if pins is None:
        cand = np.nonzero(boundary & used)[0] if boundary is not None and (boundary & used).any() \
            else np.nonzero(used)[0]
        a, b = _far_pair(Q, cand)
        if a == b:
            others = np.nonzero(used)[0]
            b = int(others[others != a][0]) if np.any(others != a) else a
        d = float(np.linalg.norm(Q[a] - Q[b]))
        pins = {a: (0.0, 0.0), b: (d, 0.0)}
    else:
        pins = {int(k): (float(v[0]) / scale, float(v[1]) / scale) for k, v in pins.items()}
    t_ok = tris[ok]
    q = q[ok]
    area2 = q[:, 1, 0] * q[:, 2, 1] - q[:, 2, 0] * q[:, 1, 1]
    inv = 1.0 / np.sqrt(np.maximum(area2, 1e-300))
    xs, ys = q[:, :, 0], q[:, :, 1]
    wr = np.stack([xs[:, 2] - xs[:, 1], xs[:, 0] - xs[:, 2], xs[:, 1] - xs[:, 0]], axis=1) * inv[:, None]
    wi = np.stack([ys[:, 2] - ys[:, 1], ys[:, 0] - ys[:, 2], ys[:, 1] - ys[:, 0]], axis=1) * inv[:, None]
    pinned = np.zeros(n, dtype=bool)
    pin_val = np.zeros((n, 2))
    for k, v in pins.items():
        pinned[k] = True
        pin_val[k] = v
    free = np.nonzero(~pinned & used)[0]
    col = np.full(n, -1, dtype=np.int64)
    col[free] = np.arange(len(free))
    m = len(free)
    vid = t_ok
    row_real = np.concatenate([wr, -wi], axis=1)
    row_imag = np.concatenate([wi, wr], axis=1)
    var_vertex = np.concatenate([vid, vid], axis=1)
    var_comp = np.concatenate([np.zeros_like(vid), np.ones_like(vid)], axis=1)
    rows_all = np.concatenate([row_real, row_imag], axis=0)
    vv = np.concatenate([var_vertex, var_vertex], axis=0)
    vc = np.concatenate([var_comp, var_comp], axis=0)
    is_pin = pinned[vv]
    var_index = np.where(is_pin, -1, col[vv] + vc * m)
    known = np.where(is_pin, pin_val[vv, vc], 0.0)
    rhs_rows = -(rows_all * known).sum(axis=1)
    coeff = np.where(is_pin, 0.0, rows_all)
    k6 = coeff.shape[1]
    ri = np.repeat(var_index, k6, axis=1).reshape(-1)
    ci = np.tile(var_index, (1, k6)).reshape(-1)
    vals = (coeff[:, :, None] * coeff[:, None, :]).reshape(-1)
    keep = (ri >= 0) & (ci >= 0) & (vals != 0.0)
    b = np.zeros(2 * m)
    valid = var_index >= 0
    np.add.at(b, var_index[valid], (coeff * rhs_rows[:, None])[valid])
    guess = np.zeros(2 * m)
    if m:
        start = _initial_guess(Q, used, t_ok, pins)
        guess[:m] = start[free, 0]
        guess[m:] = start[free, 1]
    x = _solve(ri[keep], ci[keep], vals[keep], 2 * m, b, guess) if m else np.zeros(0)
    uv = np.zeros((n, 2))
    uv[pinned] = pin_val[pinned]
    if m:
        uv[free, 0] = x[:m]
        uv[free, 1] = x[m:]
    if len(t_ok):
        a = uv[t_ok[:, 0]]
        bb = uv[t_ok[:, 1]]
        c = uv[t_ok[:, 2]]
        signed = ((bb[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (bb[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])).sum()
        if signed < 0:
            uv[:, 0] = -uv[:, 0]
    if (~used).any() and used.any():
        uv[~used] = uv[used].mean(axis=0)
    return uv * scale


def _cot_weights(q: np.ndarray) -> np.ndarray:
    w = np.zeros((len(q), 3))
    for k in range(3):
        i, j = (k + 1) % 3, (k + 2) % 3
        a = q[:, i] - q[:, k]
        b = q[:, j] - q[:, k]
        dot = np.einsum("ij,ij->i", a, b)
        cross = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
        w[:, k] = 0.5 * dot / np.maximum(cross, 1e-300)
    return np.clip(w, 1e-4, 1e4)


def arap(P: np.ndarray, tris: np.ndarray, uv0: np.ndarray, iterations: int = 10,
         pins: Iterable[int] | None = None) -> np.ndarray:
    P = np.asarray(P, float)
    tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
    uv = np.array(uv0, dtype=float, copy=True)
    n = len(P)
    if n == 0 or not len(tris) or iterations <= 0:
        return uv
    q, ok = _local_frames(P, tris)
    tris = tris[ok]
    q = q[ok]
    if not len(tris):
        return uv
    w = _cot_weights(q)
    used = np.zeros(n, dtype=bool)
    used[tris.reshape(-1)] = True
    pin_set = np.zeros(n, dtype=bool)
    if pins is not None:
        for p in pins:
            pin_set[int(p)] = True
    if not (pin_set & used).any():
        pin_set[int(np.nonzero(used)[0][0])] = True
    free = np.nonzero(used & ~pin_set)[0]
    if not len(free):
        return uv
    col = np.full(n, -1, dtype=np.int64)
    col[free] = np.arange(len(free))
    pairs = [((k + 1) % 3, (k + 2) % 3, k) for k in range(3)]
    rows, cols, vals = [], [], []
    for i, j, k in pairs:
        vi, vj, wk = tris[:, i], tris[:, j], w[:, k]
        for a, b, sgn in ((vi, vi, 1.0), (vj, vj, 1.0), (vi, vj, -1.0), (vj, vi, -1.0)):
            rows.append(a)
            cols.append(b)
            vals.append(sgn * wk)
    rows = np.concatenate(rows)
    cols = np.concatenate(cols)
    vals = np.concatenate(vals)
    cr, cc = col[rows], col[cols]
    keep = (cr >= 0) & (cc >= 0)
    fixed_mask = (cr >= 0) & (cc < 0)
    size = len(free)
    L = _Coo(cr[keep], cc[keep], vals[keep], size)
    dense_inv = None
    if size <= DENSE_LIMIT:
        M = L.dense()
        M[np.diag_indices(size)] += 1e-12 * max(float(np.abs(np.diag(M)).mean()), 1e-300)
        try:
            dense_inv = np.linalg.inv(M)
        except np.linalg.LinAlgError:
            dense_inv = np.linalg.pinv(M)
    for _ in range(int(iterations)):
        S = np.zeros((len(tris), 2, 2))
        for i, j, k in pairs:
            du = uv[tris[:, i]] - uv[tris[:, j]]
            dq = q[:, i] - q[:, j]
            S += w[:, k][:, None, None] * du[:, :, None] * dq[:, None, :]
        U, _, Vt = np.linalg.svd(S)
        R = U @ Vt
        det = np.linalg.det(R)
        flip = det < 0
        if flip.any():
            U2 = U.copy()
            U2[flip, :, 1] *= -1
            R[flip] = U2[flip] @ Vt[flip]
        b = np.zeros((n, 2))
        for i, j, k in pairs:
            rd = np.einsum("tab,tb->ta", R, q[:, i] - q[:, j]) * w[:, k][:, None]
            np.add.at(b, tris[:, i], rd)
            np.add.at(b, tris[:, j], -rd)
        rhs = b[free].copy()
        if fixed_mask.any():
            fr = cr[fixed_mask]
            fc = cols[fixed_mask]
            fv = vals[fixed_mask]
            np.add.at(rhs, fr, -(fv[:, None] * uv[fc]))
        if dense_inv is not None:
            sol = dense_inv @ rhs
        else:
            sol = _pcg(L, rhs, uv[free], tol=1e-9, max_iter=800)
        uv[free] = sol
    return uv


def spring_relax(P: np.ndarray, faces: list[list[int]], uv0: np.ndarray, iterations: int = 50,
                 pins: Iterable[int] | None = None, strength: float = 0.5) -> np.ndarray:
    uv = np.array(uv0, dtype=float, copy=True)
    pairs: set[tuple[int, int]] = set()
    for f in faces:
        m = len(f)
        if m <= 6:
            for i in range(m):
                for j in range(i + 1, m):
                    if f[i] != f[j]:
                        pairs.add((min(f[i], f[j]), max(f[i], f[j])))
        else:
            for a, b, c in triangulate_polygon(P[f]):
                for x, y in ((f[a], f[b]), (f[b], f[c]), (f[c], f[a])):
                    if x != y:
                        pairs.add((min(x, y), max(x, y)))
    if not pairs:
        return uv
    e = np.array(sorted(pairs), dtype=np.int64)
    rest = np.linalg.norm(P[e[:, 0]] - P[e[:, 1]], axis=1)
    cur = np.linalg.norm(uv[e[:, 0]] - uv[e[:, 1]], axis=1)
    k = float(cur.sum() / max(rest.sum(), 1e-300))
    target = rest * k
    pinned = np.zeros(len(uv), dtype=bool)
    if pins is not None:
        for p in pins:
            pinned[int(p)] = True
    deg = np.bincount(e.reshape(-1), minlength=len(uv)).astype(float)
    deg = np.maximum(deg, 1.0)
    for _ in range(int(iterations)):
        d = uv[e[:, 1]] - uv[e[:, 0]]
        length = np.linalg.norm(d, axis=1)
        safe = np.maximum(length, 1e-300)
        corr = ((length - target) / safe)[:, None] * d * 0.5
        acc = np.zeros_like(uv)
        np.add.at(acc, e[:, 0], corr)
        np.add.at(acc, e[:, 1], -corr)
        step = acc / deg[:, None] * float(strength) * 2.0
        step[pinned] = 0.0
        uv += step
    return uv


def _write_chart(uv_all: np.ndarray, chart: Chart, chart_uv: np.ndarray) -> None:
    uv_all[chart.corner_index] = chart_uv[chart.labels]


def unwrap(obj, polys: Iterable[int] | None = None, *, method: str = "Conformal",
           seams: set | None = None, angle: float | None = None, pack: bool = True,
           margin: float = 0.01, rotate: bool = True, iterations: int = 8,
           write: bool = True) -> tuple[np.ndarray, dict]:
    from .arrange import min_area_angle, pack_islands
    mesh = finite_mesh(obj.mesh)
    corners = Corners(mesh)
    uv = get_uv_array(obj, corners)
    seam_set = set(get_seams(obj) if seams is None else {edge_key(*e) for e in seams})
    if angle is not None and angle > 0:
        seam_set |= angle_seams(mesh, angle, corners)
    targets = list(range(corners.poly_count)) if polys is None else sorted({int(p) for p in polys})
    islands = seam_islands(mesh, seam_set, corners, targets)
    info = {"islands": 0, "cuts": 0, "non_disc": 0}
    total3d = 0.0
    done_polys: list[int] = []
    results: list[tuple[Chart, np.ndarray]] = []
    for isl in islands:
        if not isl:
            continue
        chart, cuts = cut_to_disc(mesh, corners, isl, seam_set)
        info["cuts"] += len(cuts - seam_set)
        chi, loops = chart_topology(chart)
        if chi != 1 or loops != 1:
            info["non_disc"] += 1
        if chart.vertex_count < 3 or not len(chart.tris):
            continue
        cuv = lscm(chart.positions, chart.tris, boundary=chart.boundary_vertices())
        if str(method).lower().startswith("iso") or str(method).upper() == "ARAP":
            cuv = arap(chart.positions, chart.tris, cuv, iterations=iterations)
        q, ok = _local_frames(chart.positions, chart.tris)
        a3 = float((0.5 * (q[ok, 1, 0] * q[ok, 2, 1] - q[ok, 2, 0] * q[ok, 1, 1])).sum())
        t = chart.tris
        p0, p1, p2 = cuv[t[:, 0]], cuv[t[:, 1]], cuv[t[:, 2]]
        auv = float(np.abs(0.5 * ((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1])
                                  - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0]))).sum())
        if auv > 1e-300 and a3 > 0:
            cuv = cuv * math.sqrt(a3 / auv)
        used = np.unique(chart.tris.reshape(-1))
        ang = min_area_angle(cuv[used])
        c, s = math.cos(-ang), math.sin(-ang)
        cuv = cuv @ np.array([[c, -s], [s, c]]).T
        span = cuv[used].max(axis=0) - cuv[used].min(axis=0)
        if span[1] > span[0] + 1e-12:
            cuv = np.stack([-cuv[:, 1], cuv[:, 0]], axis=1)
        total3d += a3
        results.append((chart, cuv))
        done_polys.extend(chart.polys)
        info["islands"] += 1
    if not results:
        return uv, info
    k = 1.0 / math.sqrt(max(total3d, 1e-300))
    for chart, cuv in results:
        c = cuv * k
        lo, hi = c.min(axis=0), c.max(axis=0)
        c = c - (lo + hi) / 2.0 + 0.5
        _write_chart(uv, chart, c)
    if pack:
        uv = pack_islands(mesh, uv, corners, polys=done_polys, margin=margin, rotate=rotate,
                          equalize=polys is not None, avoid=polys is not None)
    if write:
        set_uv_array(obj, uv, corners)
    return uv, info


def relax(obj, polys: Iterable[int] | None = None, *, method: str = "ARAP", iterations: int = 10,
          pin_boundary: bool = False, pinned_corners: Iterable[int] | None = None,
          write: bool = True) -> np.ndarray:
    mesh = finite_mesh(obj.mesh)
    corners = Corners(mesh)
    uv = get_uv_array(obj, corners)
    targets = list(range(corners.poly_count)) if polys is None else sorted({int(p) for p in polys})
    pinned_c = set(int(c) for c in pinned_corners) if pinned_corners is not None else set()
    for isl in uv_islands(mesh, uv, corners, targets):
        chart = chart_from_uv(mesh, corners, uv, isl)
        if chart.vertex_count < 3 or not len(chart.tris):
            continue
        cuv = np.zeros((chart.vertex_count, 2))
        cuv[chart.labels] = uv[chart.corner_index]
        pins = set()
        if pin_boundary:
            pins.update(np.nonzero(chart.boundary_vertices())[0].tolist())
        if pinned_c:
            for i, c in enumerate(chart.corner_index.tolist()):
                if c in pinned_c:
                    pins.add(int(chart.labels[i]))
        if str(method).lower().startswith("spring"):
            new = spring_relax(chart.positions, chart.faces, cuv, iterations=max(1, iterations) * 5,
                               pins=pins)
        else:
            q, ok = _local_frames(chart.positions, chart.tris)
            a3 = float((0.5 * (q[ok, 1, 0] * q[ok, 2, 1] - q[ok, 2, 0] * q[ok, 1, 1])).sum())
            t = chart.tris
            p0, p1, p2 = cuv[t[:, 0]], cuv[t[:, 1]], cuv[t[:, 2]]
            auv = float(np.abs(0.5 * ((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1])
                                      - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0]))).sum())
            if auv <= 1e-300 or a3 <= 0:
                continue
            s = math.sqrt(auv / a3)
            if pins:
                new = arap(chart.positions * s, chart.tris, cuv, iterations=iterations, pins=pins)
            else:
                center = cuv.mean(axis=0)
                new = arap(chart.positions * s, chart.tris, cuv, iterations=iterations)
                new = new - new.mean(axis=0) + center
        uv[chart.corner_index] = new[chart.labels]
    if write:
        set_uv_array(obj, uv, corners)
    return uv
