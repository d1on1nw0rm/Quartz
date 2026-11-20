from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from ..scene import Mesh, _merge_into_quads, _plane_2d, rotation_matrix
from .meshkit import (OpResult, Selection, clone, compact, directed_edges, edge_faces, edge_key,
                      face_centers, face_normals, triangulate_polygon)
from .registry import Param, ToolSpec, register

__all__ = ["loop_path_cut", "line_cut", "plane_cut", "edge_cut"]

_T_MIN = 1e-3
_SLICE_MODES = ("Cut", "Split", "Remove A", "Remove B")
_PLANE_AXIS = {"XY": 2, "ZX": 1, "YZ": 0}


def _append_points(mesh: Mesh, positions: list) -> None:
    if positions:
        mesh.points = np.vstack([mesh.points, np.asarray(positions, float).reshape(-1, 3)])


def _other(key: tuple[int, int], v: int) -> int:
    return key[1] if v == key[0] else key[0]


def _seq(edge_points: dict, key: tuple[int, int], first: int) -> list[int]:
    pts = edge_points.get(key, [])
    return list(pts) if first == key[0] else list(reversed(pts))


def _insert_ring(poly, edge_points: dict) -> list[int]:
    ring: list[int] = []
    for a, b in directed_edges(poly):
        ring.append(a)
        ring.extend(_seq(edge_points, edge_key(a, b), a))
    return ring


def _adjacent(n: int, i: int, j: int) -> bool:
    return (i - j) % n in (1, n - 1)


def _split_rings(ring: list[int], chords) -> tuple[list[list[int]], set]:
    rings = [list(ring)]
    made = set()
    for p, q in chords:
        for k, r in enumerate(rings):
            if p == q or p not in r or q not in r:
                continue
            i, j = sorted((r.index(p), r.index(q)))
            if not _adjacent(len(r), i, j):
                rings[k:k + 1] = [r[i:j + 1], r[j:] + r[:i + 1]]
                made.add(edge_key(p, q))
            break
    return rings, made


def _cross2(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _on_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray, tol: float) -> bool:
    ab = b - a
    length2 = float(ab @ ab)
    if length2 <= tol * tol:
        return False
    s = float((p - a) @ ab) / length2
    return 0.0 < s < 1.0 and abs(_cross2(a, b, p)) / np.sqrt(length2) <= tol


def _blocks(p: np.ndarray, tri: tuple, tol: float) -> bool:
    a, b, c = tri
    if min(float(np.linalg.norm(p - v)) for v in tri) <= tol:
        return False
    inside = _cross2(a, b, p) > 0 and _cross2(b, c, p) > 0 and _cross2(c, a, p) > 0
    return inside or _on_segment(p, c, a, tol)


def _ear_quality(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    area = _cross2(a, b, c)
    return area / max(1e-300, float((b - a) @ (b - a) + (c - b) @ (c - b) + (a - c) @ (a - c)))


def _best_ear(flat: np.ndarray, idx: list[int], tol: float, strict: bool) -> int:
    best, best_q = -1, 0.0
    for k in range(len(idx)):
        tri_idx = (idx[k - 1], idx[k], idx[(k + 1) % len(idx)])
        tri = tuple(flat[i] for i in tri_idx)
        q = _ear_quality(*tri)
        if q <= 1e-9 or q <= best_q:
            continue
        if strict and any(_blocks(flat[j], tri, tol) for j in idx if j not in tri_idx):
            continue
        best, best_q = k, q
    return best


def _ear_triangles(ring3: np.ndarray) -> list[tuple[int, int, int]]:
    flat = _plane_2d(ring3)
    tol = 1e-9 * max(1.0, float(np.ptp(flat, axis=0).max()))
    idx = list(range(len(flat)))
    tris: list[tuple[int, int, int]] = []
    while len(idx) > 3:
        k = _best_ear(flat, idx, tol, True)
        if k < 0:
            k = _best_ear(flat, idx, tol, False)
        if k < 0:
            k = 0
        tris.append((idx[k - 1], idx[k], idx[(k + 1) % len(idx)]))
        idx.pop(k)
    tris.append(tuple(idx))
    return tris


def _quadrangulate(points: np.ndarray, ring: list[int]) -> list[list[int]]:
    if len(ring) <= 4:
        return [ring]
    flat = points[ring]
    diagonals = _merge_into_quads(flat, _ear_triangles(flat))
    rings, _ = _split_rings(ring, [(ring[a], ring[b]) for a, b in diagonals])
    return rings


def _rebuild(mesh: Mesh, edge_points: dict, chords: dict, replace: dict,
             create_ngons: bool) -> tuple[list[int], set]:
    polys = list(mesh.polygons)
    parent = list(range(len(polys)))
    made: set = set()
    for k, poly in enumerate(mesh.polygons):
        rings = replace.get(k)
        if rings is None:
            ring = _insert_ring(poly, edge_points)
            rings, cut = _split_rings(ring, chords.get(k, ()))
            made |= cut
            if len(ring) == len(poly) and not cut:
                continue
        if not create_ngons:
            rings = [r for ring in rings for r in _quadrangulate(mesh.points, ring)]
        polys[k] = tuple(rings[0])
        for r in rings[1:]:
            polys.append(tuple(r))
            parent.append(k)
    mesh.polygons = polys
    mesh._rebuild_edges()
    return parent, made


def _segments(edge_points: dict, keys) -> set:
    out = set()
    for key in keys:
        chain = [key[0]] + list(edge_points.get(key, [])) + [key[1]]
        out |= {edge_key(a, b) for a, b in zip(chain, chain[1:])}
    return out


def _clean_ts(ts) -> list[float]:
    out: list[float] = []
    for t in sorted(min(1.0 - _T_MIN, max(_T_MIN, float(t))) for t in ts):
        if not out or t - out[-1] > 1e-6:
            out.append(t)
    return out


def _cut_infos(poly, cut: set) -> list[tuple]:
    out = []
    for j, (a, b) in enumerate(directed_edges(poly)):
        key = edge_key(a, b)
        if key in cut:
            out.append((key, a, j))
    return out


def _opposite_pair(infos: list[tuple]) -> tuple:
    js = {info[2] for info in infos}
    pair = [info for info in infos if (info[2] + 2) % 4 in js]
    return pair[0], pair[1]


def _face_plan(mesh: Mesh, cut: set, connect, allow_grid: bool) -> tuple[dict, list[int]]:
    pairs: dict = {}
    grids: list[int] = []
    for f, poly in enumerate(mesh.polygons):
        if connect is not None and f not in connect:
            continue
        infos = _cut_infos(poly, cut)
        if len(infos) == 2:
            pairs[f] = [(infos[0], infos[1])]
        elif len(poly) == 4 and len(infos) == 4 and allow_grid:
            grids.append(f)
        elif len(poly) == 4 and len(infos) == 3:
            pairs[f] = [_opposite_pair(infos)]
    return pairs, grids


def _orient(cut: set, links: list, seed: dict) -> dict:
    adj: dict = {}
    for (k1, r1, _), (k2, r2, _) in links:
        adj.setdefault(k1, []).append((r1, k2, r2))
        adj.setdefault(k2, []).append((r2, k1, r1))
    start: dict = {}
    for key in list(seed) + sorted(cut):
        if key in start or key not in cut:
            continue
        start[key] = seed.get(key, key[0])
        queue = [key]
        while queue:
            cur = queue.pop()
            for r_cur, nb, r_nb in adj.get(cur, ()):
                if nb in start:
                    continue
                start[nb] = _other(nb, r_nb) if start[cur] == r_cur else r_nb
                queue.append(nb)
    return start


def _subdivide(mesh: Mesh, cut: set, start: dict, ts: list[float]) -> dict:
    edge_points: dict = {}
    positions: list = []
    base = len(mesh.points)
    for key in sorted(cut):
        s = start[key]
        ps, po = mesh.points[s], mesh.points[_other(key, s)]
        ids = []
        for t in ts:
            ids.append(base + len(positions))
            positions.append(ps + (po - ps) * t)
        edge_points[key] = ids if s == key[0] else ids[::-1]
    _append_points(mesh, positions)
    return edge_points


def _pair_chords(edge_points: dict, info1: tuple, info2: tuple) -> list[tuple[int, int]]:
    p = _seq(edge_points, info1[0], info1[1])
    q = _seq(edge_points, info2[0], info2[1])
    n = min(len(p), len(q))
    return [(p[i], q[len(q) - 1 - i]) for i in range(n)]


def _closest_mid(a, b, c, d) -> np.ndarray:
    u, w = b - a, d - c
    m = np.column_stack([u, -w])
    st, *_ = np.linalg.lstsq(m, c - a, rcond=None)
    return 0.5 * ((a + u * st[0]) + (c + w * st[1]))


def _grid_sides(poly, edge_points: dict) -> list[list[int]]:
    v = list(poly)
    s = [_seq(edge_points, edge_key(v[j], v[(j + 1) % 4]), v[j]) for j in range(4)]
    bottom = [v[0]] + s[0] + [v[1]]
    right = [v[1]] + s[1] + [v[2]]
    top = [v[3]] + s[2][::-1] + [v[2]]
    left = [v[0]] + s[3][::-1] + [v[3]]
    return [bottom, right, top, left]


def _grid(mesh: Mesh, poly, edge_points: dict):
    bottom, right, top, left = _grid_sides(poly, edge_points)
    m = len(bottom)
    if not len(right) == len(top) == len(left) == m:
        return None
    grid = [[0] * m for _ in range(m)]
    for i in range(m):
        grid[i][0], grid[i][m - 1], grid[0][i], grid[m - 1][i] = bottom[i], top[i], left[i], right[i]
    base = len(mesh.points)
    pts = mesh.points
    positions = []
    for i in range(1, m - 1):
        for j in range(1, m - 1):
            grid[i][j] = base + len(positions)
            positions.append(_closest_mid(pts[bottom[i]], pts[top[i]], pts[left[j]], pts[right[j]]))
    _append_points(mesh, positions)
    rings = [[grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]]
             for i in range(m - 1) for j in range(m - 1)]
    made = {edge_key(a, b) for r in rings for a, b in directed_edges(r) if a >= base or b >= base}
    return rings, made


def _edge_engine(mesh: Mesh, cut: set, ts: list[float], seed: dict, connect,
                 allow_grid: bool, create_ngons: bool):
    base = len(mesh.points)
    pairs, grids = _face_plan(mesh, cut, connect, allow_grid)
    links = [pair for plist in pairs.values() for pair in plist]
    for f in grids:
        infos = _cut_infos(mesh.polygons[f], cut)
        links += [(infos[0], infos[2]), (infos[1], infos[3])]
    edge_points = _subdivide(mesh, cut, _orient(cut, links, seed), ts)
    chords = {f: [c for i1, i2 in plist for c in _pair_chords(edge_points, i1, i2)]
              for f, plist in pairs.items()}
    replace: dict = {}
    made: set = set()
    for f in grids:
        built = _grid(mesh, mesh.polygons[f], edge_points)
        if built is not None:
            replace[f], cells = built
            made |= cells
    parent, chord_made = _rebuild(mesh, edge_points, chords, replace, create_ngons)
    return parent, made | chord_made, set(range(base, len(mesh.points))), edge_points


def _component_selection(mesh: Mesh, mode: str, polys: set, points: set, edges: set) -> Selection:
    if mode == "points":
        return Selection("points", points={int(i) for i in points if 0 <= i < len(mesh.points)})
    if mode == "edges":
        valid = set(mesh.edges)
        return Selection("edges", edges={e for e in edges if e in valid})
    return Selection("polygons", polygons={int(f) for f in polys if 0 <= f < len(mesh.polygons)})


def _children(parent: list[int], faces: set) -> set:
    return {i for i, q in enumerate(parent) if q in faces}


def _across(poly, u: int, v: int):
    if len(poly) != 4:
        return None
    for j in range(4):
        a, b = poly[j], poly[(j + 1) % 4]
        if (a, b) == (u, v):
            return poly[(j + 3) % 4], poly[(j + 2) % 4]
        if (a, b) == (v, u):
            return poly[(j + 2) % 4], poly[(j + 3) % 4]
    return None


def _walk(mesh: Mesh, ef: dict, edge, face, face_ok, start, edges: set, faces: list, seen: set) -> bool:
    u, v = edge
    while face is not None and face not in seen and face_ok(face):
        nxt = _across(mesh.polygons[face], u, v)
        if nxt is None:
            return False
        seen.add(face)
        faces.append(face)
        key = edge_key(*nxt)
        if key == start:
            return True
        if key in edges:
            return False
        edges.add(key)
        owners = ef.get(key, [])
        face = next((g for g in owners if g != face), None) if len(owners) == 2 else None
        u, v = nxt
    return False


def _ring(mesh: Mesh, a: int, b: int, face_ok) -> tuple[set, list[int]]:
    ef = edge_faces(mesh)
    start = edge_key(a, b)
    edges, faces, seen = {start}, [], set()
    for first in ef.get(start, [])[:2]:
        if _walk(mesh, ef, (a, b), first, face_ok, start, edges, faces, seen):
            break
    return edges, faces


def _picked_edge(mesh: Mesh, sel: Selection, runtime):
    valid = set(mesh.polygon_edges())
    if runtime is not None and len(runtime) == 2 and edge_key(*runtime) in valid:
        return int(runtime[0]), int(runtime[1])
    if sel.mode == "edges":
        chosen = sorted(edge_key(*e) for e in sel.edges if edge_key(*e) in valid)
        return chosen[0] if chosen else None
    if sel.mode == "polygons":
        faces = sorted(f for f in sel.polygons if 0 <= f < len(mesh.polygons))
        return directed_edges(mesh.polygons[faces[0]])[0] if faces else None
    if sel.mode == "points":
        return next((e for e in sorted(valid) if e[0] in sel.points and e[1] in sel.points), None)
    return None


def _loop_positions(p: dict) -> list[float]:
    offset = float(p["offset"]) / 100.0
    if p["quantize"]:
        q = max(1, int(p["quantize_subdivision"]))
        offset = round(offset * q) / q
    n = max(1, int(p["cuts"]))
    spacing = 1.0 / (n + 1) if p["evenly_distribute"] else float(p["spacing"]) / 100.0
    ts = [offset + (k - (n - 1) / 2.0) * spacing for k in range(n)]
    if p["symmetric"]:
        ts += [1.0 - t for t in ts]
    return _clean_ts(ts)


def _restrict_faces(sel: Selection, restrict: bool, count: int):
    if restrict and sel.mode == "polygons":
        faces = {f for f in sel.polygons if 0 <= f < count}
        return faces, (lambda f: f in faces)
    return None, (lambda f: True)


def _path_edges(mesh: Mesh, sel: Selection, runtime) -> set:
    valid = set(mesh.polygon_edges())
    source = runtime if runtime is not None else (sel.edges if sel.mode == "edges" else ())
    return {edge_key(*e) for e in source if edge_key(*e) in valid}


def loop_path_cut(source: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(source)
    picked = _picked_edge(mesh, sel, p.get("edge"))
    if picked is None:
        return OpResult(mesh, sel, False, "Loop/Path Cut: hover or select an edge to cut")
    a, b = picked
    allowed, face_ok = _restrict_faces(sel, bool(p["restrict_to_selection"]), len(mesh.polygons))
    ts = _loop_positions(p)
    path = _path_edges(mesh, sel, p.get("path")) | {edge_key(a, b)}
    if p["mode"] == "Path" and len(path) >= 2:
        result = _edge_engine(mesh, path, ts, {edge_key(a, b): a}, allowed, False, True)
    else:
        ring, faces = _ring(mesh, a, b, face_ok)
        if not faces:
            return OpResult(mesh, sel, False, "Loop/Path Cut: no quad loop runs through this edge")
        result = _edge_engine(mesh, ring, ts, {edge_key(a, b): a}, set(faces), False, True)
    parent, made, new_points, _ = result
    if not made:
        return OpResult(clone(source), sel, False, "Loop/Path Cut: nothing to cut along this path")
    polys = _children(parent, set(sel.polygons))
    return OpResult(mesh, _component_selection(mesh, sel.mode, polys, new_points, made))


def _edge_cut_positions(p: dict) -> list[float]:
    n = max(1, int(p["subdivision"]))
    offset = float(p["offset"]) / 100.0
    scale = float(p["scale"]) / 100.0
    return _clean_ts(offset + ((k + 1) / (n + 1) - 0.5) * scale for k in range(n))


def edge_cut(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode != "edges":
        return OpResult(mesh, sel, False, "Edge Cut works in edges mode")
    valid = set(mesh.polygon_edges())
    cut = {edge_key(*e) for e in sel.edges if edge_key(*e) in valid}
    if not cut:
        return OpResult(mesh, sel, False, "Edge Cut: no edges selected")
    ts = _edge_cut_positions(p)
    _, made, _, edge_points = _edge_engine(mesh, cut, ts, {}, None, True, bool(p["create_ngons"]))
    chosen = made or _segments(edge_points, cut)
    return OpResult(mesh, _component_selection(mesh, "edges", set(), set(), chosen))


@dataclass
class _CutRules:
    face_ok: Callable[[int], bool]
    edge_ok: Callable[[tuple[int, int]], bool]
    accept: Callable[[np.ndarray], bool]
    create_ngons: bool


@dataclass
class _Track:
    faces: set | None
    edges: set | None
    points: set | None
    selected: set
    cut_points: set = field(default_factory=set)
    cut_edges: set = field(default_factory=set)

    def face_ok(self, f: int) -> bool:
        return self.faces is None or f in self.faces

    def edge_ok(self, key: tuple[int, int]) -> bool:
        if self.edges is not None:
            return key in self.edges
        if self.points is not None:
            return key[0] in self.points and key[1] in self.points
        return True

    def advance(self, parent: list[int], made: set, used: set, edge_points: dict) -> None:
        self.selected = _children(parent, self.selected)
        if self.faces is not None:
            self.faces = _children(parent, self.faces)
        if self.edges is not None:
            split = [key for key in edge_points if key in self.edges]
            self.edges = (self.edges - set(split)) | _segments(edge_points, split)
        if self.points is not None:
            self.points |= used
        self.cut_points |= used
        self.cut_edges |= made


def _new_track(sel: Selection, restrict: bool, visible: set | None) -> _Track:
    faces = set(sel.polygons) if restrict and sel.mode == "polygons" else None
    if visible is not None:
        faces = set(visible) if faces is None else faces & visible
    edges = {edge_key(*e) for e in sel.edges} if restrict and sel.mode == "edges" else None
    points = set(sel.points) if restrict and sel.mode == "points" else None
    return _Track(faces, edges, points, set(sel.polygons))


def _nonzero_sign(ring: list[int], d: np.ndarray, i: int, step: int) -> int:
    n = len(ring)
    for k in range(1, n):
        val = d[ring[(i + step * k) % n]]
        if val != 0.0:
            return 1 if val > 0 else -1
    return 0


def _crossings(ring: list[int], d: np.ndarray) -> list[int]:
    out = []
    for i, v in enumerate(ring):
        if d[v] == 0.0 and _nonzero_sign(ring, d, i, -1) * _nonzero_sign(ring, d, i, 1) < 0:
            out.append(v)
    return out


def _pair_along(points: np.ndarray, hits: list[int], direction: np.ndarray) -> list[tuple[int, int]]:
    if len(hits) < 2 or float(np.linalg.norm(direction)) < 1e-12:
        return []
    order = sorted(hits, key=lambda v: float(points[v] @ direction))
    return [(order[k], order[k + 1]) for k in range(0, len(order) - 1, 2)]


def _edge_crossings(mesh: Mesh, d: np.ndarray, rules: _CutRules) -> tuple[dict, list]:
    edge_points: dict = {}
    positions: list = []
    base = len(mesh.points)
    for key, owners in edge_faces(mesh).items():
        a, b = key
        if d[a] * d[b] >= 0 or not rules.edge_ok(key) or not any(rules.face_ok(f) for f in owners):
            continue
        t = d[a] / (d[a] - d[b])
        pos = mesh.points[a] + (mesh.points[b] - mesh.points[a]) * t
        if rules.accept(pos):
            edge_points[key] = [base + len(positions)]
            positions.append(pos)
    return edge_points, positions


def _distance_cut(mesh: Mesh, plane: tuple, rules: _CutRules):
    g, c, eps = plane
    d = mesh.points @ g + c
    d[np.abs(d) < eps] = 0.0
    base = len(mesh.points)
    edge_points, positions = _edge_crossings(mesh, d, rules)
    normals = face_normals(mesh)
    _append_points(mesh, positions)
    d = np.concatenate([d, np.zeros(len(positions))])
    chords: dict = {}
    used = set(range(base, len(mesh.points)))
    for f, poly in enumerate(mesh.polygons):
        if not rules.face_ok(f):
            continue
        hits = [v for v in _crossings(_insert_ring(poly, edge_points), d)
                if v >= base or rules.accept(mesh.points[v])]
        pairs = _pair_along(mesh.points, hits, np.cross(normals[f], g))
        if pairs:
            chords[f] = pairs
            used |= {v for pair in pairs for v in pair}
    parent, made = _rebuild(mesh, edge_points, chords, {}, rules.create_ngons)
    return parent, made, used, edge_points


def _split_slabs(mesh: Mesh, allowed, planes: list[tuple]) -> None:
    d = np.stack([mesh.points @ g + c for g, c, _ in planes], axis=1)
    on = np.any(np.abs(d) < planes[0][2], axis=1)
    slab_of = {f: int(np.sum(d[list(mesh.polygons[f])].mean(axis=0) > 0)) for f in allowed}
    users: dict = {}
    for f, s in slab_of.items():
        for v in mesh.polygons[f]:
            if on[v]:
                users.setdefault(v, set()).add(s)
    copies: dict = {}
    positions: list = []
    for v, slabs in sorted(users.items()):
        for s in sorted(slabs)[1:]:
            copies[(v, s)] = len(mesh.points) + len(positions)
            positions.append(mesh.points[v].copy())
    _append_points(mesh, positions)
    for f, s in slab_of.items():
        mesh.polygons[f] = tuple(copies.get((v, s), v) for v in mesh.polygons[f])
    mesh._rebuild_edges()


def _remove_side(mesh: Mesh, track: _Track, allowed, plane: tuple, sign: float) -> Mesh:
    g, c, _ = plane
    doomed = {f for f in allowed
              if sign * float(np.mean(mesh.points[list(mesh.polygons[f])] @ g + c)) > plane[2]}
    keep = [f for f in range(len(mesh.polygons)) if f not in doomed]
    poly_map = {old: new for new, old in enumerate(keep)}
    out, remap = compact(Mesh(mesh.points, [mesh.polygons[f] for f in keep], mesh.loose_edges))
    track.selected = {poly_map[f] for f in track.selected if f in poly_map}
    track.cut_points = {remap[v] for v in track.cut_points if v in remap}
    track.cut_edges = {edge_key(remap[a], remap[b]) for a, b in track.cut_edges if a in remap and b in remap}
    return out


def _apply_slice(mesh: Mesh, track: _Track, planes: list[tuple], mode: str) -> Mesh:
    allowed = range(len(mesh.polygons)) if track.faces is None else sorted(track.faces)
    if mode == "Split":
        _split_slabs(mesh, allowed, planes)
    elif mode == "Remove A":
        return _remove_side(mesh, track, allowed, planes[-1], 1.0)
    elif mode == "Remove B":
        return _remove_side(mesh, track, allowed, planes[0], -1.0)
    return mesh


def _cut_with_planes(mesh: Mesh, sel: Selection, planes: list[tuple], p: dict,
                     accept, visible, name: str) -> OpResult:
    track = _new_track(sel, bool(p["restrict_to_selection"]), visible)
    for plane in planes:
        rules = _CutRules(track.face_ok, track.edge_ok, accept, bool(p["create_ngons"]))
        track.advance(*_distance_cut(mesh, plane, rules))
    if not track.cut_points:
        return OpResult(mesh, sel, False, f"{name}: the cut does not cross any polygon")
    mesh = _apply_slice(mesh, track, planes, p["slice_mode"])
    selection = _component_selection(mesh, sel.mode, track.selected, track.cut_points, track.cut_edges)
    return OpResult(mesh, selection)


def _object_frame(p: dict) -> tuple[np.ndarray, np.ndarray]:
    lin = p.get("object_linear")
    pos = p.get("object_position")
    lin = np.eye(3) if lin is None else np.asarray(lin, float).reshape(3, 3)
    pos = np.zeros(3) if pos is None else np.asarray(pos, float).reshape(3)
    return lin, pos


def _tolerance(mesh: Mesh, lin: np.ndarray) -> float:
    lo, hi = mesh.bounds()
    return 1e-7 * max(1.0, float(np.linalg.norm(hi - lo)) * float(np.linalg.norm(lin, 2)))


def _plane_frame(p: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rot = rotation_matrix(p["plane_rotation"])
    lin, pos = _object_frame(p)
    if p["mode"] == "Local":
        lin, pos = np.eye(3), np.zeros(3)
    elif p["mode"] == "Screen" and p.get("camera_rotation") is not None:
        rot = np.asarray(p["camera_rotation"], float).reshape(3, 3) @ rot
    normal = rot[:, _PLANE_AXIS.get(p["plane"], 2)]
    return lin, pos, np.asarray(p["plane_position"], float), normal / np.linalg.norm(normal)


def _plane_offsets(p: dict) -> list[float]:
    n = max(1, int(p["cuts"]))
    spacing = float(p["spacing"])
    return [(k - (n - 1) / 2.0) * spacing for k in range(n)]


def plane_cut(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if not mesh.polygons:
        return OpResult(mesh, sel, False, "Plane Cut: the object has no polygons")
    lin, pos, origin, normal = _plane_frame(p)
    g = lin.T @ normal
    c = float((pos - origin) @ normal)
    eps = _tolerance(mesh, lin)
    planes = [(g, c - off, eps) for off in _plane_offsets(p)]
    return _cut_with_planes(mesh, sel, planes, p, lambda x: True, None, "Plane Cut")


def _line_frame(p: dict):
    lin, pos = _object_frame(p)
    inv = np.linalg.inv(lin)
    view = p.get("view_dir")
    view = np.array([0.0, 0.0, 1.0]) if view is None else np.asarray(view, float).reshape(3)
    a = inv @ (np.asarray(p["start"], float).reshape(3) - pos)
    b = inv @ (np.asarray(p["end"], float).reshape(3) - pos)
    v = inv @ view
    g = np.cross(b - a, v)
    length = float(np.linalg.norm(g))
    if length < 1e-12:
        return None
    g = g / length
    return lin, a, b - a, v, g


def _segment_test(a: np.ndarray, along: np.ndarray, v: np.ndarray, g: np.ndarray):
    inv = np.linalg.inv(np.column_stack([along, v, g]))

    def accept(x: np.ndarray) -> bool:
        s = float((inv @ (x - a))[0])
        return -1e-9 <= s <= 1.0 + 1e-9

    return accept


def _triangles(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    owners, tris = [], []
    for f in range(len(mesh.polygons)):
        for tri in triangulate_polygon(mesh, f):
            owners.append(f)
            tris.append(tri)
    return np.asarray(owners, int), mesh.points[np.asarray(tris, int).reshape(-1, 3)]


def _occluded(origin: np.ndarray, direction: np.ndarray, tri: np.ndarray, mask: np.ndarray,
              tol: float) -> bool:
    a, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    pvec = np.cross(direction, e2)
    det = np.einsum("ij,ij->i", e1, pvec)
    ok = mask & (np.abs(det) > 1e-12)
    inv = 1.0 / np.where(ok, det, 1.0)
    s = origin - a
    u = np.einsum("ij,ij->i", s, pvec) * inv
    q = np.cross(s, e1)
    w = (q @ direction) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1 + 1e-9) & (t > tol)
    return bool(hit.any())


def _visible_faces(mesh: Mesh, view: np.ndarray, flip: float, tol: float) -> set:
    view = view / max(1e-12, float(np.linalg.norm(view)))
    normals = face_normals(mesh)
    centers = face_centers(mesh)
    owners, tris = _triangles(mesh)
    out = set()
    for f in range(len(mesh.polygons)):
        if float(normals[f] @ view) * flip >= -1e-9:
            continue
        if not _occluded(centers[f], -view, tris, owners != f, tol):
            out.add(f)
    return out


def line_cut(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if p.get("start") is None or p.get("end") is None:
        return OpResult(mesh, sel, False, "Line Cut: draw a cut line in the viewport first")
    if not mesh.polygons:
        return OpResult(mesh, sel, False, "Line Cut: the object has no polygons")
    frame = _line_frame(p)
    if frame is None:
        return OpResult(mesh, sel, False, "Line Cut: the cut line is parallel to the view")
    lin, a, along, v, g = frame
    eps = _tolerance(mesh, np.eye(3))
    infinite = bool(p["infinite_cut"]) or p["slice_mode"] != "Cut"
    accept = (lambda x: True) if infinite else _segment_test(a, along, v, g)
    visible = None
    if p["visible_only"]:
        visible = _visible_faces(mesh, v, 1.0 if np.linalg.det(lin) >= 0 else -1.0, eps * 10)
    planes = [(g, -float(a @ g), eps)]
    return _cut_with_planes(mesh, sel, planes, p, accept, visible, "Line Cut")


_OBJECT_RUNTIME = {
    "object_linear": "3x3 matrix of the object's rotation and scale (SceneObject.linear()); None means identity",
    "object_position": "object position in world space; None means the origin",
}


register(ToolSpec(
    id="loop_path_cut",
    name="Loop/Path Cut",
    apply=loop_path_cut,
    modes=("points", "edges", "polygons"),
    params=(
        Param("mode", "Mode", "choice", "Loop", choices=("Loop", "Path")),
        Param("offset", "Offset", "percent", 50.0, 0.0, 100.0, 1.0, "%"),
        Param("cuts", "Cuts", "int", 1, 1, 100, 1),
        Param("evenly_distribute", "Evenly Distribute", "bool", True),
        Param("spacing", "Spacing", "percent", 10.0, 0.0, 100.0, 1.0, "%"),
        Param("symmetric", "Symmetric Cut", "bool", False),
        Param("quantize", "Quantize", "bool", False),
        Param("quantize_subdivision", "Quantize Subdivision", "int", 10, 1, 1000, 1),
        Param("restrict_to_selection", "Restrict To Selection", "bool", False),
        Param("edge", "Edge", "runtime", None, group="Runtime"),
        Param("path", "Path", "runtime", None, group="Runtime"),
    ),
    interactive=True,
    drag_param="offset",
    drag_kind="percent",
    section="CUT",
    shortcut="K~L",
    description="Cuts a loop or a path of edges across the polygon ring under the cursor.",
    extra={
        "pick": "edge",
        "runtime": {
            "edge": "(a, b) point indices of the hovered edge; Offset is measured from a toward b",
            "path": "list of (a, b) edges clicked in Path mode; defaults to the selected edges",
        },
    },
))


register(ToolSpec(
    id="line_cut",
    name="Line Cut",
    apply=line_cut,
    modes=("points", "edges", "polygons"),
    params=(
        Param("visible_only", "Visible Only", "bool", True),
        Param("restrict_to_selection", "Restrict To Selection", "bool", False),
        Param("infinite_cut", "Infinite Cut", "bool", False),
        Param("slice_mode", "Slice Mode", "choice", "Cut", choices=_SLICE_MODES),
        Param("auto_snap", "Auto Snap", "bool", False),
        Param("create_ngons", "Create N-gons", "bool", False),
        Param("start", "Start", "runtime", None, group="Runtime"),
        Param("end", "End", "runtime", None, group="Runtime"),
        Param("view_dir", "View Direction", "runtime", None, group="Runtime"),
        Param("object_linear", "Object Matrix", "runtime", None, group="Runtime"),
        Param("object_position", "Object Position", "runtime", None, group="Runtime"),
    ),
    interactive=True,
    drag_param=None,
    drag_kind="distance",
    section="CUT",
    shortcut="K~K",
    description="Cuts every polygon crossed by a line drawn in the viewport.",
    extra={
        "pick": "line",
        "runtime": {
            "start": "first world point of the cut line",
            "end": "second world point of the cut line",
            "view_dir": "world direction the camera looks along; None means +Z",
            **_OBJECT_RUNTIME,
        },
    },
))


register(ToolSpec(
    id="plane_cut",
    name="Plane Cut",
    apply=plane_cut,
    modes=("points", "edges", "polygons"),
    params=(
        Param("mode", "Mode", "choice", "Local", choices=("Local", "World", "Screen")),
        Param("plane", "Plane", "choice", "XY", choices=("XY", "ZX", "YZ")),
        Param("plane_position", "Plane Position", "vector", (0.0, 0.0, 0.0), unit="cm"),
        Param("plane_rotation", "Plane Rotation", "vector", (0.0, 0.0, 0.0), unit="°"),
        Param("cuts", "Cuts", "int", 1, 1, 1000, 1),
        Param("spacing", "Spacing", "distance", 10.0, 0.0, 1e6, 1.0, "cm"),
        Param("restrict_to_selection", "Restrict To Selection", "bool", False),
        Param("slice_mode", "Slice Mode", "choice", "Cut", choices=_SLICE_MODES),
        Param("create_ngons", "Create N-gons", "bool", False),
        Param("object_linear", "Object Matrix", "runtime", None, group="Runtime"),
        Param("object_position", "Object Position", "runtime", None, group="Runtime"),
        Param("camera_rotation", "Camera Rotation", "runtime", None, group="Runtime"),
    ),
    interactive=True,
    drag_param=None,
    drag_kind="distance",
    section="CUT",
    shortcut="K~J",
    description="Cuts the object with one or more parallel planes.",
    extra={
        "pick": "plane",
        "runtime": {
            **_OBJECT_RUNTIME,
            "camera_rotation": "3x3 world rotation of the camera, used by Screen mode; None means identity",
        },
    },
))


register(ToolSpec(
    id="edge_cut",
    name="Edge Cut",
    apply=edge_cut,
    modes=("edges",),
    params=(
        Param("offset", "Offset", "percent", 50.0, 0.0, 100.0, 1.0, "%"),
        Param("scale", "Scale", "percent", 100.0, 0.0, 100.0, 1.0, "%"),
        Param("subdivision", "Subdivision", "int", 1, 1, 100, 1),
        Param("create_ngons", "Create N-gons", "bool", False),
    ),
    interactive=True,
    drag_param="offset",
    drag_kind="percent",
    section="CREATION TOOLS",
    shortcut="M~F",
    description="Subdivides the selected edges and connects the new points across their polygons.",
))
