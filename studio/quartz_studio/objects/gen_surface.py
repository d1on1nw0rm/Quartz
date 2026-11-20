from __future__ import annotations

import heapq
import itertools
import math

import numpy as np

from ..scene import Mesh, _ear_clip
from .registry import ObjectSpec, Param, register

_AXIS = {"ZY": 0, "XZ": 1, "XY": 2}
_AREA_EPS = 1e-9


def _compact(points: np.ndarray, polys: list) -> tuple[np.ndarray, list] | None:
    if not polys:
        return None
    used = sorted({int(i) for poly in polys for i in poly})
    remap = {old: new for new, old in enumerate(used)}
    return (np.asarray(points, float)[used].copy(),
            [tuple(remap[int(i)] for i in poly) for poly in polys])


def _clean_ring(poly, limit: int) -> tuple[int, ...] | None:
    ring: list[int] = []
    for i in poly:
        i = int(i)
        if not 0 <= i < limit:
            return None
        if not ring or ring[-1] != i:
            ring.append(i)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    if len(ring) < 3 or len(set(ring)) != len(ring):
        return None
    return tuple(ring)


def _clean(mesh: Mesh) -> tuple[np.ndarray, list] | None:
    if not mesh.polygons or not len(mesh.points):
        return None
    polys = []
    for poly in mesh.polygons:
        ring = _clean_ring(poly, len(mesh.points))
        if ring is not None:
            polys.append(ring)
    return _compact(mesh.points, polys)


def _sources(inputs: list) -> list[tuple[np.ndarray, list]]:
    out = []
    for inp in inputs:
        if inp.is_spline:
            continue
        got = _clean(inp.mesh)
        if got is not None:
            out.append(got)
    return out


def _join(parts: list) -> tuple[np.ndarray, list]:
    pts, polys, off = [], [], 0
    for p, q in parts:
        pts.append(p)
        polys.extend(tuple(i + off for i in poly) for poly in q)
        off += len(p)
    return np.vstack(pts), polys


def _area(points: np.ndarray, ring) -> float:
    pts = points[list(ring)]
    nxt = np.roll(pts, -1, axis=0)
    return 0.5 * float(np.linalg.norm(np.cross(pts, nxt).sum(axis=0)))


def _finish(points: np.ndarray, polys: list) -> Mesh:
    got = _compact(np.asarray(points, float).reshape(-1, 3), polys)
    if got is None:
        return Mesh.empty()
    return Mesh(got[0], got[1])


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _canonical(ring) -> tuple[int, ...]:
    k = min(range(len(ring)), key=lambda j: ring[j])
    return tuple(ring[k:]) + tuple(ring[:k])


def _remap_polys(points: np.ndarray, polys: list, rep: np.ndarray) -> list:
    out, seen = [], set()
    for poly in polys:
        ring = _clean_ring([int(rep[i]) for i in poly], len(points))
        if ring is None or _area(points, ring) <= _AREA_EPS:
            continue
        key = _canonical(ring)
        if key in seen:
            continue
        seen.add(key)
        out.append(ring)
    return out


def _weld_map(points: np.ndarray, tol: float, subset=None) -> np.ndarray:
    n = len(points)
    rep = np.arange(n)
    idx = np.arange(n) if subset is None else np.asarray(subset, dtype=int)
    if len(idx) < 2:
        return rep
    cell = max(float(tol), 1e-7)
    limit = (float(tol) + 1e-12) ** 2
    keys = np.floor(points[idx] / cell).astype(np.int64)
    coords = points.tolist()
    grid: dict[tuple[int, int, int], list[int]] = {}
    for k, i in enumerate(idx):
        grid.setdefault((int(keys[k, 0]), int(keys[k, 1]), int(keys[k, 2])), []).append(int(i))
    parent: dict[int, int] = {}

    def find(i: int) -> int:
        root = i
        while parent.get(root, root) != root:
            root = parent[root]
        while i != root:
            nxt = parent.get(i, i)
            parent[i] = root
            i = nxt
        return root

    offsets = list(itertools.product((-1, 0, 1), repeat=3))
    for k, i in enumerate(idx):
        i = int(i)
        cx, cy, cz = int(keys[k, 0]), int(keys[k, 1]), int(keys[k, 2])
        pi = coords[i]
        for dx, dy, dz in offsets:
            for j in grid.get((cx + dx, cy + dy, cz + dz), ()):
                if j <= i:
                    continue
                pj = coords[j]
                d = (pi[0] - pj[0]) ** 2 + (pi[1] - pj[1]) ** 2 + (pi[2] - pj[2]) ** 2
                if d <= limit:
                    ra, rb = find(i), find(j)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
    for i in idx:
        rep[int(i)] = find(int(i))
    return rep


def _catmull_clark(points: np.ndarray, polys: list) -> tuple[np.ndarray, list]:
    npts = len(points)
    face_pts = np.array([points[list(p)].mean(axis=0) for p in polys])
    edge_ids: dict[tuple[int, int], int] = {}
    edge_ends: list[tuple[int, int]] = []
    edge_adj: list[list[int]] = []
    vert_faces: list[list[int]] = [[] for _ in range(npts)]
    vert_edges: list[list[int]] = [[] for _ in range(npts)]
    for f, poly in enumerate(polys):
        k = len(poly)
        for j in range(k):
            a, b = poly[j], poly[(j + 1) % k]
            key = _edge_key(a, b)
            e = edge_ids.get(key)
            if e is None:
                e = len(edge_ends)
                edge_ids[key] = e
                edge_ends.append(key)
                edge_adj.append([])
                vert_edges[a].append(e)
                vert_edges[b].append(e)
            edge_adj[e].append(f)
            vert_faces[a].append(f)
    ne = len(edge_ends)
    ea = np.array([e[0] for e in edge_ends], dtype=int)
    eb = np.array([e[1] for e in edge_ends], dtype=int)
    mids = (points[ea] + points[eb]) / 2.0
    edge_pts = mids.copy()
    for e, adj in enumerate(edge_adj):
        if len(adj) == 2:
            edge_pts[e] = (points[ea[e]] + points[eb[e]] + face_pts[adj[0]] + face_pts[adj[1]]) / 4.0
    vert_pts = points.copy()
    for v in range(npts):
        es = vert_edges[v]
        counts = [len(edge_adj[e]) for e in es]
        if any(c > 2 for c in counts):
            continue
        boundary = [e for e, c in zip(es, counts) if c == 1]
        if not boundary:
            n = len(es)
            f_avg = face_pts[vert_faces[v]].mean(axis=0)
            r_avg = mids[es].mean(axis=0)
            vert_pts[v] = (f_avg + 2.0 * r_avg + (n - 3.0) * points[v]) / n
        elif len(boundary) == 2:
            other = [ea[e] if eb[e] == v else eb[e] for e in boundary]
            vert_pts[v] = (6.0 * points[v] + points[other[0]] + points[other[1]]) / 8.0
    off_e = npts
    off_f = npts + ne
    new_polys = []
    for f, poly in enumerate(polys):
        k = len(poly)
        eidx = [edge_ids[_edge_key(poly[j], poly[(j + 1) % k])] for j in range(k)]
        for j in range(k):
            new_polys.append((poly[j], off_e + eidx[j], off_f + f, off_e + eidx[j - 1]))
    return np.vstack([vert_pts, edge_pts, face_pts]), new_polys


def build_subdivision(p: dict, inputs: list) -> Mesh:
    parts = _sources(inputs)
    if not parts:
        return Mesh.empty()
    level = int(p["subdivision_editor"])
    out = []
    for pts, polys in parts:
        for _ in range(level):
            pts, polys = _catmull_clark(pts, polys)
        out.append((pts, polys))
    pts, polys = _join(out)
    return _finish(pts, polys)


def build_symmetry(p: dict, inputs: list) -> Mesh:
    parts = _sources(inputs)
    if not parts:
        return Mesh.empty()
    pts, polys = _join(parts)
    axis = _AXIS[p["mirror_plane"]]
    tol = float(p["tolerance"])
    weld = bool(p["weld_points"])
    if p["flip"]:
        polys = [poly for poly in polys if float(pts[list(poly), axis].mean()) <= tol]
        got = _compact(pts, polys)
        if got is None:
            return Mesh.empty()
        pts, polys = got
    n = len(pts)
    on = np.zeros(n, dtype=bool)
    if weld:
        on = np.abs(pts[:, axis]) <= tol
        pts = pts.copy()
        pts[on, axis] = 0.0
    mir = pts.copy()
    mir[:, axis] = 0.0 - mir[:, axis]
    all_pts = np.vstack([pts, mir])
    mir_polys = [tuple(n + i for i in reversed(poly)) for poly in polys]
    if weld:
        rep = np.arange(2 * n)
        on_idx = np.nonzero(on)[0]
        sub = _weld_map(pts, tol, on_idx)
        rep[:n] = sub
        rep[n + on_idx] = sub[on_idx]
        flat_on = np.concatenate([on, on])
        kept_orig = [poly for poly in polys if not all(flat_on[i] for i in poly)]
        kept_mir = [poly for poly in mir_polys if not all(flat_on[i] for i in poly)]
        final = _remap_polys(all_pts, kept_orig + kept_mir, rep)
    else:
        final = polys + mir_polys
    return _finish(all_pts, final)


def build_connect(p: dict, inputs: list) -> Mesh:
    parts = _sources(inputs)
    if not parts:
        return Mesh.empty()
    pts, polys = _join(parts)
    if p["weld"]:
        rep = _weld_map(pts, float(p["tolerance"]))
        polys = _remap_polys(pts, polys, rep)
    return _finish(pts, polys)


def _vertex_offsets(points: np.ndarray, polys: list) -> np.ndarray:
    nv = len(points)
    acc = np.zeros((nv, 3, 3))
    nsum = np.zeros((nv, 3))
    for poly in polys:
        ring = points[list(poly)]
        nxt = np.roll(ring, -1, axis=0)
        n = np.array([
            np.sum((ring[:, 1] - nxt[:, 1]) * (ring[:, 2] + nxt[:, 2])),
            np.sum((ring[:, 2] - nxt[:, 2]) * (ring[:, 0] + nxt[:, 0])),
            np.sum((ring[:, 0] - nxt[:, 0]) * (ring[:, 1] + nxt[:, 1])),
        ])
        length = float(np.linalg.norm(n))
        if length < 1e-12:
            continue
        n = n / length
        outer = np.outer(n, n)
        for i in poly:
            acc[i] += outer
            nsum[i] += n
    out = np.zeros((nv, 3))
    for v in range(nv):
        d = np.linalg.pinv(acc[v], rcond=1e-3) @ nsum[v]
        length = float(np.linalg.norm(d))
        if length > 3.0:
            d = d * (3.0 / length)
        out[v] = d
    return out


def _thicken_part(points: np.ndarray, polys: list, thickness: float, sub: int,
                  both: bool) -> tuple[np.ndarray, list]:
    nv = len(points)
    front = thickness / 2.0 if both else 0.0
    back = thickness / 2.0 if both else thickness
    disp = _vertex_offsets(points, polys)
    layers = [points + disp * front, points - disp * back]
    out_pts = [layers[0], layers[1]]
    out_polys = [tuple(poly) for poly in polys]
    out_polys += [tuple(nv + i for i in reversed(poly)) for poly in polys]
    count: dict[tuple[int, int], int] = {}
    directed: dict[tuple[int, int], tuple[int, int]] = {}
    for poly in polys:
        k = len(poly)
        for j in range(k):
            a, b = poly[j], poly[(j + 1) % k]
            key = _edge_key(a, b)
            count[key] = count.get(key, 0) + 1
            directed[key] = (a, b)
    walls = [directed[key] for key, c in count.items() if c == 1]
    if not walls:
        return np.vstack(out_pts), out_polys
    mid_index: dict[tuple[int, int], int] = {}
    base = 2 * nv
    extra = []
    for v in sorted({i for edge in walls for i in edge}):
        for k in range(1, sub):
            s = front - (front + back) * k / sub
            mid_index[(v, k)] = base + len(extra)
            extra.append(points[v] + disp[v] * s)

    def at(v: int, k: int) -> int:
        if k == 0:
            return v
        if k == sub:
            return nv + v
        return mid_index[(v, k)]

    for a, b in walls:
        for k in range(sub):
            out_polys.append((at(b, k), at(a, k), at(a, k + 1), at(b, k + 1)))
    if extra:
        out_pts.append(np.array(extra))
    return np.vstack(out_pts), out_polys


def build_thicken(p: dict, inputs: list) -> Mesh:
    thickness = float(p["thickness"])
    if thickness <= 1e-9:
        return Mesh.empty()
    parts = _sources(inputs)
    if not parts:
        return Mesh.empty()
    out = [_thicken_part(pts, polys, thickness, int(p["subdivision"]), bool(p["both_sides"]))
           for pts, polys in parts]
    pts, polys = _join(out)
    return _finish(pts, polys)


def _triangulate(points: np.ndarray, polys: list) -> list[tuple[int, int, int]]:
    tris = []
    for poly in polys:
        if len(poly) == 3:
            tris.append(tuple(poly))
            continue
        for a, b, c in _ear_clip(points[list(poly)]):
            tris.append((poly[a], poly[b], poly[c]))
    out = []
    for t in tris:
        if len(set(t)) == 3 and _area(points, t) > _AREA_EPS:
            out.append(t)
    return out


def _tri_edges(tri) -> list[tuple[int, int]]:
    return [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]


def _split_edges(points: list, tris: list, target: int) -> tuple[list, list]:
    faces: dict[int, tuple[int, int, int]] = {i: t for i, t in enumerate(tris)}
    edge_faces: dict[tuple[int, int], set[int]] = {}
    for f, t in faces.items():
        for a, b in _tri_edges(t):
            edge_faces.setdefault(_edge_key(a, b), set()).add(f)
    heap: list = []

    def length(a: int, b: int) -> float:
        return float(np.linalg.norm(points[a] - points[b]))

    for a, b in edge_faces:
        heapq.heappush(heap, (-length(a, b), a, b))
    next_id = len(faces)
    while len(faces) < target and heap:
        _, a, b = heapq.heappop(heap)
        key = (a, b)
        if key not in edge_faces:
            continue
        adjacent = sorted(edge_faces[key])
        mid = len(points)
        points.append((points[a] + points[b]) / 2.0)
        for f in adjacent:
            t = faces.pop(f)
            for u, w in _tri_edges(t):
                edge_faces[_edge_key(u, w)].discard(f)
            k = next(j for j in range(3) if _edge_key(t[j], t[(j + 1) % 3]) == key)
            x, y, q = t[k], t[(k + 1) % 3], t[(k + 2) % 3]
            for new in ((x, mid, q), (mid, y, q)):
                faces[next_id] = new
                for u, w in _tri_edges(new):
                    ek = _edge_key(u, w)
                    if ek not in edge_faces or not edge_faces[ek]:
                        edge_faces[ek] = set()
                        heapq.heappush(heap, (-length(u, w), ek[0], ek[1]))
                    edge_faces[ek].add(next_id)
                next_id += 1
        edge_faces.pop(key, None)
    return points, list(faces.values())


def _collapse_edges(points: list, tris: list, target: int) -> tuple[list, list]:
    faces: dict[int, tuple[int, int, int]] = {i: t for i, t in enumerate(tris)}
    vfaces: dict[int, set[int]] = {}
    for f, t in faces.items():
        for v in t:
            vfaces.setdefault(v, set()).add(f)

    def neighbours(v: int) -> dict[int, int]:
        out: dict[int, int] = {}
        for f in vfaces[v]:
            t = faces[f]
            k = t.index(v)
            for w in (t[(k + 1) % 3], t[(k + 2) % 3]):
                out[w] = out.get(w, 0) + 1
        return out

    def interior(nb: dict[int, int], v: int) -> bool:
        return all(c == 2 for c in nb.values()) and len(nb) == len(vfaces[v])

    def normal(a, b, c) -> np.ndarray:
        return np.cross(points[b] - points[a], points[c] - points[a])

    def try_collapse(v: int, u: int) -> bool:
        nv = neighbours(v)
        if u not in nv or not interior(nv, v):
            return False
        nu = neighbours(u)
        if len(set(nu) & set(nv)) != 2:
            return False
        u_inside = interior(nu, u)
        new_pos = (points[u] + points[v]) / 2.0 if u_inside else points[u]
        shared = {f for f in vfaces[v] if u in faces[f]}
        existing = {frozenset(faces[f]) for f in vfaces[u] if f not in shared}
        for f in vfaces[v] - shared:
            t = faces[f]
            new = tuple(u if w == v else w for w in t)
            if frozenset(new) in existing:
                return False
            old_n = normal(*t)
            saved = points[u]
            points[u] = new_pos
            new_n = normal(*new)
            points[u] = saved
            if np.linalg.norm(new_n) <= 1e-9 or float(old_n @ new_n) <= 0.1 * np.linalg.norm(old_n) * np.linalg.norm(new_n):
                return False
        if u_inside:
            for f in vfaces[u] - shared:
                t = faces[f]
                old_n = normal(*t)
                saved = points[u]
                points[u] = new_pos
                new_n = normal(*t)
                points[u] = saved
                if np.linalg.norm(new_n) <= 1e-9 or float(old_n @ new_n) <= 0.1 * np.linalg.norm(old_n) * np.linalg.norm(new_n):
                    return False
        points[u] = new_pos
        for f in shared:
            for w in faces[f]:
                vfaces[w].discard(f)
            del faces[f]
        for f in list(vfaces[v]):
            t = faces[f]
            faces[f] = tuple(u if w == v else w for w in t)
            vfaces[u].add(f)
        del vfaces[v]
        return True

    for _ in range(40):
        if len(faces) <= max(target, 4):
            break
        edges = set()
        for t in faces.values():
            for a, b in _tri_edges(t):
                edges.add(_edge_key(a, b))
        order = sorted(edges, key=lambda e: float(np.linalg.norm(points[e[0]] - points[e[1]])))
        progress = False
        for a, b in order:
            if len(faces) <= max(target, 4):
                break
            if a not in vfaces or b not in vfaces:
                continue
            if try_collapse(a, b) or try_collapse(b, a):
                progress = True
        if not progress:
            break
    return points, list(faces.values())


def _pair_quads(points: np.ndarray, tris: list) -> list:
    owner: dict[tuple[int, int], int] = {}
    for t, tri in enumerate(tris):
        for a, b in _tri_edges(tri):
            owner[(a, b)] = t
    norms = []
    for tri in tris:
        n = np.cross(points[tri[1]] - points[tri[0]], points[tri[2]] - points[tri[0]])
        norms.append(n / max(float(np.linalg.norm(n)), 1e-30))
    cands = []
    for (x, y), t1 in owner.items():
        t2 = owner.get((y, x))
        if t2 is None or t2 <= t1:
            continue
        p = next(i for i in tris[t1] if i not in (x, y))
        q = next(i for i in tris[t2] if i not in (x, y))
        if p == q:
            continue
        flat = float(norms[t1] @ norms[t2])
        if flat < math.cos(math.radians(30.0)):
            continue
        ring = (x, q, y, p)
        pts = points[list(ring)]
        axis = norms[t1] + norms[t2]
        worst = 0.0
        convex = True
        for i in range(4):
            e0 = pts[i] - pts[i - 1]
            e1 = pts[(i + 1) % 4] - pts[i]
            l0, l1 = float(np.linalg.norm(e0)), float(np.linalg.norm(e1))
            if l0 < 1e-12 or l1 < 1e-12:
                convex = False
                break
            c = float(np.cross(e0, e1) @ axis) / (l0 * l1)
            if c <= 1e-6:
                convex = False
                break
            worst = max(worst, abs(float(e0 @ e1)) / (l0 * l1))
        if not convex or worst > 0.8:
            continue
        cands.append((worst + (1.0 - flat), t1, t2, ring))
    cands.sort(key=lambda c: c[0])
    used: set[int] = set()
    quads = []
    for _, t1, t2, ring in cands:
        if t1 in used or t2 in used:
            continue
        used.add(t1)
        used.add(t2)
        quads.append(ring)
    return quads + [tri for t, tri in enumerate(tris) if t not in used]


def build_remesh(p: dict, inputs: list) -> Mesh:
    parts = _sources(inputs)
    if not parts:
        return Mesh.empty()
    density = float(p["polygon_density"]) / 100.0
    out = []
    for pts, polys in parts:
        tris = _triangulate(pts, polys)
        if not tris:
            continue
        plist = [row.copy() for row in pts]
        target = int(round(len(tris) * density))
        if target > len(tris):
            plist, tris = _split_edges(plist, tris, target)
        elif target < len(tris):
            plist, tris = _collapse_edges(plist, tris, target)
        arr = np.array(plist)
        faces = _pair_quads(arr, tris) if p["mode"] == "Quads" else tris
        got = _compact(arr, faces)
        if got is not None:
            out.append(got)
    if not out:
        return Mesh.empty()
    pts, polys = _join(out)
    return _finish(pts, polys)


register(ObjectSpec(
    id="subdivision_surface", label="Subdivision Surface", category="generator",
    build=build_subdivision, inputs="children",
    params=(Param("type", "Type", "choice", "Catmull-Clark", choices=("Catmull-Clark",), group="Object"),
            Param("subdivision_editor", "Subdivision Editor", "int", 2, 0, 6, 1, group="Object"))))

register(ObjectSpec(
    id="symmetry", label="Symmetry", category="generator",
    build=build_symmetry, inputs="children",
    params=(Param("mirror_plane", "Mirror Plane", "choice", "ZY", choices=("ZY", "XY", "XZ"), group="Object"),
            Param("weld_points", "Weld Points", "bool", True, group="Object"),
            Param("tolerance", "Tolerance", "distance", 0.01, 0.0, 1e6, 0.01, "cm", group="Object"),
            Param("flip", "Flip", "bool", False, group="Object"))))

register(ObjectSpec(
    id="connect", label="Connect", category="generator",
    build=build_connect, inputs="children",
    params=(Param("weld", "Weld", "bool", True, group="Object"),
            Param("tolerance", "Tolerance", "distance", 0.01, 0.0, 1e6, 0.01, "cm", group="Object"))))

register(ObjectSpec(
    id="thicken", label="Thicken", category="generator",
    build=build_thicken, inputs="children",
    params=(Param("thickness", "Thickness", "distance", 10.0, 0.0, 1e6, 1.0, "cm", group="Object"),
            Param("subdivision", "Subdivision", "int", 1, 1, 100, 1, group="Object"),
            Param("both_sides", "Both Sides", "bool", False, group="Object"))))

register(ObjectSpec(
    id="remesh", label="Remesh", category="generator",
    build=build_remesh, inputs="children",
    params=(Param("mode", "Mode", "choice", "Triangles", choices=("Triangles", "Quads"), group="Object"),
            Param("polygon_density", "Polygon Density", "percent", 100.0, 10.0, 400.0, 1.0, "%",
                  group="Object"))))
