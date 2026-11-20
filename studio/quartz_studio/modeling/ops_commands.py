from __future__ import annotations

import math

import numpy as np

from ..scene import Mesh
from .meshkit import (OpResult, Selection, clean_polygons, clone, compact, directed_edges,
                      edge_faces, edge_groups, edge_key, face_area, face_normals,
                      triangulate_polygon)
from .registry import Param, ToolSpec, register

__all__ = ["subdivide", "triangulate", "untriangulate", "reverse_normals", "align_normals",
           "spin_edge", "collapse", "mirror", "delete"]

ALL_MODES = ("points", "edges", "polygons", "model")
COMPONENT_MODES = ("points", "edges", "polygons")


def _scope_faces(mesh: Mesh, sel: Selection) -> list[int]:
    if sel.mode == "polygons":
        chosen = sorted(f for f in sel.polygons if 0 <= f < len(mesh.polygons))
        if chosen:
            return chosen
    return list(range(len(mesh.polygons)))


def _had_selection(sel: Selection, mesh: Mesh) -> bool:
    return any(0 <= f < len(mesh.polygons) for f in sel.polygons)


def _polygon_result(mesh: Mesh, sel: Selection, chosen: set[int], had: bool) -> OpResult:
    return OpResult(mesh, Selection("polygons", polygons=set(chosen) if had else set()))


def _used_points(mesh: Mesh) -> set[int]:
    return {int(i) for poly in mesh.polygons for i in poly} | {int(i) for e in mesh.loose_edges for i in e}


def _drop_orphans(mesh: Mesh, before: set[int], keep: set[int] = frozenset()) -> tuple[Mesh, dict[int, int]]:
    used = _used_points(mesh)
    stay = [i for i in range(len(mesh.points)) if i not in before or i in keep or i in used]
    return compact(mesh, keep=stay)


def _valid_edges(mesh: Mesh, sel: Selection) -> list[tuple[int, int]]:
    existing = set(mesh.edges)
    return sorted({edge_key(*e) for e in sel.edges if edge_key(*e) in existing})


def _rotate_to(poly: tuple[int, ...], start: int) -> list[int]:
    k = poly.index(start)
    return list(poly[k:] + poly[:k])


def _has_directed(poly: tuple[int, ...], a: int, b: int) -> bool:
    return (a, b) in directed_edges(poly)


def _angle_deg(n0: np.ndarray, n1: np.ndarray) -> float:
    return math.degrees(math.acos(float(np.clip(n0 @ n1, -1.0, 1.0))))


def _replace_faces(mesh: Mesh, children: dict[int, list[tuple[int, ...]]]) -> set[int]:
    out: set[int] = set()
    for f, polys in sorted(children.items()):
        if not polys:
            continue
        mesh.polygons[f] = tuple(polys[0])
        out.add(f)
        for poly in polys[1:]:
            mesh.polygons.append(tuple(poly))
            out.add(len(mesh.polygons) - 1)
    return out


def _union_find(n_items: dict):
    parent = {k: k for k in n_items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    return parent, find


def _union(parent: dict, find, a, b) -> None:
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[max(ra, rb)] = min(ra, rb)


def _insert_on_edge(poly: tuple[int, ...], a: int, b: int, mids: list[int]) -> tuple[int, ...]:
    ring = list(poly)
    n = len(ring)
    for j in range(n):
        u, v = ring[j], ring[(j + 1) % n]
        if (u, v) == (a, b):
            return tuple(ring[:j + 1] + mids + ring[j + 1:])
        if (u, v) == (b, a):
            return tuple(ring[:j + 1] + list(reversed(mids)) + ring[j + 1:])
    return poly


def _smooth_edges(mesh: Mesh, fset: set[int], ef: dict, normals: np.ndarray, max_angle: float) -> set:
    out = set()
    for e, owners in ef.items():
        if len(owners) != 2 or not all(f in fset for f in owners):
            continue
        if _angle_deg(normals[owners[0]], normals[owners[1]]) <= max_angle + 1e-9:
            out.add(e)
    return out


def _face_point(mesh: Mesh, f: int) -> np.ndarray:
    return mesh.points[list(mesh.polygons[f])].mean(axis=0)


def _edge_point(mesh: Mesh, e, ef: dict, smooth: set, fpos: dict) -> np.ndarray:
    a, b = mesh.points[e[0]], mesh.points[e[1]]
    if e in smooth:
        f0, f1 = ef[e]
        return (a + b + fpos[f0] + fpos[f1]) / 4.0
    return (a + b) / 2.0


def _vertex_point(mesh: Mesh, v: int, faces: list[int], edges: list, smooth: set, fpos: dict) -> np.ndarray:
    p = mesh.points[v]
    creases = [e for e in edges if e not in smooth]
    if len(creases) > 2:
        return p.copy()
    if len(creases) == 2:
        others = [mesh.points[e[0] if e[1] == v else e[1]] for e in creases]
        return (6.0 * p + others[0] + others[1]) / 8.0
    n = len(edges)
    if n < 3 or len(faces) != n:
        return p.copy()
    q = np.mean([fpos[f] for f in faces], axis=0)
    r = np.mean([(mesh.points[e[0]] + mesh.points[e[1]]) / 2.0 for e in edges], axis=0)
    return (q + 2.0 * r + (n - 3.0) * p) / n


def _smoothed_vertices(mesh: Mesh, faces: list[int], ef: dict, smooth: set, fpos: dict) -> dict[int, np.ndarray]:
    fset = set(faces)
    v_faces: dict[int, list[int]] = {}
    for f, poly in enumerate(mesh.polygons):
        for v in poly:
            v_faces.setdefault(v, []).append(f)
    v_edges: dict[int, set] = {}
    for f in faces:
        for a, b in directed_edges(mesh.polygons[f]):
            e = edge_key(a, b)
            v_edges.setdefault(a, set()).add(e)
            v_edges.setdefault(b, set()).add(e)
    loose = {v for e in mesh.loose_edges for v in e}
    out = {}
    for v, edges in v_edges.items():
        if v in loose or any(f not in fset for f in v_faces.get(v, ())):
            continue
        out[v] = _vertex_point(mesh, v, v_faces[v], sorted(edges), smooth, fpos)
    return out


def _subdivide_face(poly: tuple[int, ...], mid, center: int | None) -> list[tuple[int, ...]]:
    n = len(poly)
    if center is None:
        m = [mid(poly[i], poly[(i + 1) % 3]) for i in range(3)]
        return [(poly[0], m[0], m[2]), (poly[1], m[1], m[0]), (poly[2], m[2], m[1]), (m[0], m[1], m[2])]
    return [(poly[i], mid(poly[i], poly[(i + 1) % n]), center, mid(poly[i - 1], poly[i])) for i in range(n)]


def _subdivide_faces_once(mesh: Mesh, faces: list[int], smooth_on: bool, max_angle: float) -> list[int]:
    fset = set(faces)
    ef = edge_faces(mesh)
    normals = face_normals(mesh)
    fpos = {f: _face_point(mesh, f) for f in faces}
    smooth = _smooth_edges(mesh, fset, ef, normals, max_angle) if smooth_on else set()
    split = sorted({edge_key(a, b) for f in faces for a, b in directed_edges(mesh.polygons[f])})
    epos = {e: _edge_point(mesh, e, ef, smooth, fpos) for e in split}
    vpos = _smoothed_vertices(mesh, faces, ef, smooth, fpos) if smooth_on else {}
    emid = {e: mesh.add_point(epos[e]) for e in split}
    centers = {}
    for f in faces:
        if smooth_on or len(mesh.polygons[f]) != 3:
            centers[f] = mesh.add_point(fpos[f])

    def mid(a: int, b: int) -> int:
        return emid[edge_key(a, b)]

    for e in split:
        for g in ef.get(e, ()):
            if g not in fset:
                mesh.polygons[g] = _insert_on_edge(mesh.polygons[g], e[0], e[1], [emid[e]])
    children = {f: _subdivide_face(mesh.polygons[f], mid, centers.get(f)) for f in faces}
    for v, p in vpos.items():
        mesh.points[v] = p
    return sorted(_replace_faces(mesh, children))


def _subdivide_edges(mesh: Mesh, sel: Selection, count: int) -> OpResult:
    edges = _valid_edges(mesh, sel)
    if not edges:
        return OpResult(mesh, sel, False, "Subdivide: no edges selected")
    ef = edge_faces(mesh)
    new_edges = set()
    loose = set(mesh.loose_edges)
    for a, b in edges:
        pa, pb = mesh.points[a], mesh.points[b]
        mids = [mesh.add_point(pa + (pb - pa) * (k / (count + 1))) for k in range(1, count + 1)]
        chain = [a] + mids + [b]
        new_edges |= {edge_key(u, v) for u, v in zip(chain, chain[1:])}
        for f in ef.get((a, b), ()):
            mesh.polygons[f] = _insert_on_edge(mesh.polygons[f], a, b, mids)
        if (a, b) in loose:
            mesh.loose_edges.remove((a, b))
            mesh.loose_edges.extend(edge_key(u, v) for u, v in zip(chain, chain[1:]))
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("edges", edges=new_edges))


def subdivide(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    count = max(1, int(p["subdivision"]))
    if sel.mode == "edges":
        return _subdivide_edges(mesh, sel, count)
    had = _had_selection(sel, mesh)
    faces = _scope_faces(mesh, sel)
    if not faces:
        return OpResult(mesh, sel, False, "Subdivide: the object has no polygons")
    for _ in range(count):
        faces = _subdivide_faces_once(mesh, faces, bool(p["subdivision_surface"]), float(p["max_angle"]))
    mesh._rebuild_edges()
    if sel.mode == "polygons":
        return _polygon_result(mesh, sel, set(faces), had)
    return OpResult(mesh, Selection(sel.mode))


def _newell(pts: np.ndarray) -> np.ndarray:
    return np.cross(pts, np.roll(pts, -1, axis=0)).sum(axis=0)


def _triangulate_face(mesh: Mesh, f: int) -> list[tuple[int, int, int]]:
    tris = triangulate_polygon(mesh, f)
    poly = mesh.polygons[f]
    if len(poly) != 4:
        return tris
    normal = _newell(mesh.points[list(poly)])
    if all(float(_newell(mesh.points[list(t)]) @ normal) > 0 for t in tris):
        return tris
    if (poly[0], poly[1], poly[2]) in tris:
        return [(poly[0], poly[1], poly[3]), (poly[1], poly[2], poly[3])]
    return [(poly[0], poly[1], poly[2]), (poly[0], poly[2], poly[3])]


def triangulate(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    had = _had_selection(sel, mesh)
    faces = _scope_faces(mesh, sel)
    targets = [f for f in faces if len(mesh.polygons[f]) > 3]
    if not targets:
        return OpResult(mesh, sel, False, "Triangulate: no quads or N-gons to triangulate")
    children = {f: _triangulate_face(mesh, f) for f in targets}
    created = _replace_faces(mesh, children)
    mesh._rebuild_edges()
    if sel.mode == "polygons":
        return _polygon_result(mesh, sel, set(faces) | created, had)
    return OpResult(mesh, sel)


def _quad_from_pair(mesh: Mesh, f: int, g: int, e) -> tuple[int, ...] | None:
    pf, pg = mesh.polygons[f], mesh.polygons[g]
    u, v = e if _has_directed(pf, *e) else (e[1], e[0])
    if not _has_directed(pg, v, u):
        return None
    w1 = [i for i in pf if i not in (u, v)][0]
    w2 = [i for i in pg if i not in (u, v)][0]
    if w1 == w2:
        return None
    return (v, w1, u, w2)


def _quad_score(mesh: Mesh, quad: tuple[int, ...]) -> float | None:
    pts = mesh.points[list(quad)]
    normal = np.cross(pts[2] - pts[0], pts[3] - pts[1])
    length = float(np.linalg.norm(normal))
    if length < 1e-12:
        return None
    normal /= length
    score = 0.0
    for i in range(4):
        d0 = pts[i - 1] - pts[i]
        d1 = pts[(i + 1) % 4] - pts[i]
        if float(np.cross(d1, d0) @ normal) <= 1e-9:
            return None
        cos = float(d0 @ d1) / max(1e-12, float(np.linalg.norm(d0) * np.linalg.norm(d1)))
        score += abs(math.degrees(math.acos(np.clip(cos, -1.0, 1.0))) - 90.0)
    return score


def _diagonal_penalty(mesh: Mesh, poly: tuple[int, ...], e) -> float:
    lengths = {edge_key(a, b): float(np.linalg.norm(mesh.points[a] - mesh.points[b]))
               for a, b in directed_edges(poly)}
    return 0.0 if lengths[e] >= max(lengths.values()) - 1e-9 else 180.0


def _untriangulate_candidates(mesh: Mesh, tris: set[int], p: dict) -> list:
    ef = edge_faces(mesh)
    normals = face_normals(mesh)
    out = []
    for e, owners in ef.items():
        if len(owners) != 2 or not all(f in tris for f in owners):
            continue
        f, g = owners
        if p["evaluate_angle"] and _angle_deg(normals[f], normals[g]) > float(p["angle"]) + 1e-9:
            continue
        quad = _quad_from_pair(mesh, f, g, e)
        score = None if quad is None else _quad_score(mesh, quad)
        if score is None:
            continue
        score += _diagonal_penalty(mesh, mesh.polygons[f], e) + _diagonal_penalty(mesh, mesh.polygons[g], e)
        out.append((score, f, g, quad))
    out.sort(key=lambda item: (item[0], item[1], item[2]))
    return out


def untriangulate(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    had = _had_selection(sel, mesh)
    faces = _scope_faces(mesh, sel)
    tris = {f for f in faces if len(mesh.polygons[f]) == 3}
    if len(tris) < 2:
        return OpResult(mesh, sel, False, "Untriangulate: needs at least two adjacent triangles")
    used: set[int] = set()
    merged: dict[int, tuple[int, ...]] = {}
    for _, f, g, quad in _untriangulate_candidates(mesh, tris, p):
        if f in used or g in used:
            continue
        used |= {f, g}
        merged[min(f, g)] = quad
    if not merged:
        return OpResult(mesh, sel, False, "Untriangulate: no triangle pairs could be joined")
    drop = used - set(merged)
    for f, quad in merged.items():
        mesh.polygons[f] = quad
    remap = _drop_faces(mesh, drop)
    mesh._rebuild_edges()
    if sel.mode == "polygons":
        return _polygon_result(mesh, sel, {remap[f] for f in faces if f in remap}, had)
    if sel.mode == "edges":
        return OpResult(mesh, Selection("edges", edges=set(_valid_edges(mesh, sel))))
    return OpResult(mesh, sel)


def _drop_faces(mesh: Mesh, drop: set[int]) -> dict[int, int]:
    remap: dict[int, int] = {}
    kept = []
    for f, poly in enumerate(mesh.polygons):
        if f in drop:
            continue
        remap[f] = len(kept)
        kept.append(poly)
    mesh.polygons = kept
    return remap


def _reversed(poly: tuple[int, ...]) -> tuple[int, ...]:
    return (poly[0],) + tuple(reversed(poly[1:]))


def reverse_normals(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    faces = _scope_faces(mesh, sel)
    if not faces:
        return OpResult(mesh, sel, False, "Reverse Normals: the object has no polygons")
    for f in faces:
        mesh.polygons[f] = _reversed(mesh.polygons[f])
    mesh._rebuild_edges()
    return OpResult(mesh, sel)


def _orient_component(mesh: Mesh, start: int, fset: set[int], ef: dict, flip: dict) -> list[int]:
    flip[start] = False
    stack = [start]
    comp = [start]
    while stack:
        f = stack.pop()
        for a, b in directed_edges(mesh.polygons[f]):
            owners = ef[edge_key(a, b)]
            if len(owners) != 2:
                continue
            g = owners[0] if owners[1] == f else owners[1]
            if g == f or g not in fset or g in flip:
                continue
            g_has_ab = _has_directed(mesh.polygons[g], a, b)
            flip[g] = g_has_ab ^ flip[f]
            comp.append(g)
            stack.append(g)
    return comp


def _effective(poly: tuple[int, ...], flipped: bool) -> tuple[int, ...]:
    return _reversed(poly) if flipped else poly


def _signed_volume(mesh: Mesh, comp: list[int], flip: dict) -> float:
    total = 0.0
    for f in comp:
        ring = mesh.points[list(_effective(mesh.polygons[f], flip[f]))]
        for i in range(1, len(ring) - 1):
            total += float(np.linalg.det(np.array([ring[0], ring[i], ring[i + 1]])))
    return total / 6.0


def _is_closed(comp: list[int], ef: dict, mesh: Mesh) -> bool:
    cset = set(comp)
    for f in comp:
        for a, b in directed_edges(mesh.polygons[f]):
            owners = ef[edge_key(a, b)]
            if len(owners) != 2 or not all(g in cset for g in owners):
                return False
    return True


def _border_votes(mesh: Mesh, comp: list[int], fset: set[int], ef: dict, flip: dict) -> int:
    votes = 0
    for f in comp:
        eff = _effective(mesh.polygons[f], flip[f])
        for a, b in directed_edges(eff):
            owners = ef[edge_key(a, b)]
            others = [g for g in owners if g != f and g not in fset]
            if len(owners) == 2 and others:
                votes += -1 if _has_directed(mesh.polygons[others[0]], a, b) else 1
    return votes


def _should_invert(mesh: Mesh, comp: list[int], fset: set[int], ef: dict, flip: dict) -> bool:
    if _is_closed(comp, ef, mesh):
        return _signed_volume(mesh, comp, flip) < 0
    votes = _border_votes(mesh, comp, fset, ef, flip)
    if votes:
        return votes < 0
    kept = sum(face_area(mesh, f) for f in comp if not flip[f])
    changed = sum(face_area(mesh, f) for f in comp if flip[f])
    return changed > kept + 1e-12


def align_normals(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    faces = _scope_faces(mesh, sel)
    if not faces:
        return OpResult(mesh, sel, False, "Align Normals: the object has no polygons")
    fset = set(faces)
    ef = edge_faces(mesh)
    flip: dict[int, bool] = {}
    for f in faces:
        if f in flip:
            continue
        comp = _orient_component(mesh, f, fset, ef, flip)
        if _should_invert(mesh, comp, fset, ef, flip):
            for g in comp:
                flip[g] = not flip[g]
    for f in faces:
        mesh.polygons[f] = _effective(mesh.polygons[f], flip[f])
    mesh._rebuild_edges()
    return OpResult(mesh, sel)


def _spin_one(mesh: Mesh, e) -> tuple[int, int] | None:
    owners = edge_faces(mesh).get(e, [])
    if len(owners) != 2:
        return None
    f, g = owners
    u, v = e if _has_directed(mesh.polygons[f], *e) else (e[1], e[0])
    if not _has_directed(mesh.polygons[g], v, u):
        return None
    seq1 = _rotate_to(mesh.polygons[f], v)
    seq2 = _rotate_to(mesh.polygons[g], u)
    ring = seq1 + seq2[1:-1]
    m = len(ring)
    if m < 4 or len(set(ring)) != m:
        return None
    i_a, i_b = 1, len(seq1) % m
    new_edge = edge_key(ring[i_a], ring[i_b])
    if new_edge in set(mesh.edges):
        return None
    mesh.polygons[f] = tuple(ring[i_a:i_b + 1]) if i_b > i_a else tuple(ring[i_a:] + ring[:i_b + 1])
    mesh.polygons[g] = tuple(ring[i_b:] + ring[:i_a + 1])
    mesh._rebuild_edges()
    return new_edge


def _spin_independent(mesh: Mesh, edges: list) -> set:
    touched: set[int] = set()
    done = set()
    for e in edges:
        owners = edge_faces(mesh).get(e, [])
        if touched & set(owners):
            continue
        new_edge = _spin_one(mesh, e)
        if new_edge is not None:
            touched |= set(owners)
            done.add(new_edge)
    return done


def _shared_selected_edges(mesh: Mesh, faces: set[int]) -> list:
    return sorted(e for e, owners in edge_faces(mesh).items()
                  if len(owners) == 2 and all(f in faces for f in owners))


def spin_edge(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode == "polygons":
        faces = {f for f in sel.polygons if 0 <= f < len(mesh.polygons)}
        edges = _shared_selected_edges(mesh, faces)
    else:
        edges = _valid_edges(mesh, sel)
    if not edges:
        return OpResult(mesh, sel, False, "Spin Edge: select edges shared by two polygons")
    done = _spin_independent(mesh, edges)
    if not done:
        return OpResult(mesh, sel, False, "Spin Edge: the selected edges cannot be spun")
    if sel.mode == "polygons":
        return OpResult(mesh, sel)
    return OpResult(mesh, Selection("edges", edges=done))


def _merge_points(mesh: Mesh, mapping: dict[int, int], positions: dict[int, np.ndarray]) -> tuple[Mesh, dict[int, int]]:
    pts = mesh.points.copy()
    for i, pos in positions.items():
        pts[i] = pos
    polys = clean_polygons([[mapping.get(i, i) for i in poly] for poly in mesh.polygons])
    polys = _drop_back_to_back(polys, set(positions))
    loose = [(mapping.get(a, a), mapping.get(b, b)) for a, b in mesh.loose_edges]
    loose = [e for e in loose if e[0] != e[1]]
    keep = [i for i in range(len(pts)) if mapping.get(i, i) == i]
    merged = Mesh(pts, polys, loose)
    out, remap = compact(merged, keep=keep)
    full = {i: remap[mapping.get(i, i)] for i in range(len(pts)) if mapping.get(i, i) in remap}
    return out, full


def _drop_back_to_back(polys: list[tuple[int, ...]], touched: set[int]) -> list[tuple[int, ...]]:
    keys: dict[frozenset, list[int]] = {}
    for k, poly in enumerate(polys):
        if touched & set(poly):
            keys.setdefault(frozenset(poly), []).append(k)
    drop = set()
    for owners in keys.values():
        if len(owners) == 2 and _canon(_reversed(polys[owners[0]])) == _canon(polys[owners[1]]):
            drop |= set(owners)
    return [poly for k, poly in enumerate(polys) if k not in drop]


def _canon(poly: tuple[int, ...]) -> tuple[int, ...]:
    k = poly.index(min(poly))
    return tuple(poly[k:] + poly[:k])


def _collapse_groups(mesh: Mesh, sel: Selection) -> list[list[int]]:
    if sel.mode == "points":
        pts = sorted(i for i in sel.points if 0 <= i < len(mesh.points))
        return [pts] if len(pts) > 1 else []
    if sel.mode == "edges":
        return [sorted({i for e in group for i in e}) for group in edge_groups(_valid_edges(mesh, sel))]
    faces = [f for f in sel.polygons if 0 <= f < len(mesh.polygons)]
    items = {i: True for f in faces for i in mesh.polygons[f]}
    parent, find = _union_find(items)
    for f in faces:
        poly = mesh.polygons[f]
        for i in poly[1:]:
            _union(parent, find, poly[0], i)
    groups: dict[int, list[int]] = {}
    for i in items:
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for g in groups.values()]


def collapse(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode not in COMPONENT_MODES:
        return OpResult(mesh, sel, False, "Collapse needs points, edges or polygons mode")
    groups = _collapse_groups(mesh, sel)
    if not groups:
        return OpResult(mesh, sel, False, "Collapse: select at least two points, an edge or a polygon")
    mapping: dict[int, int] = {}
    positions: dict[int, np.ndarray] = {}
    for group in groups:
        rep = group[0]
        positions[rep] = mesh.points[group].mean(axis=0)
        for i in group:
            mapping[i] = rep
    before = _used_points(mesh)
    out, remap = _merge_points(mesh, mapping, positions)
    reps = {remap[g[0]] for g in groups}
    after_before = {remap[i] for i in before if i in remap}
    out, second = _drop_orphans(out, after_before, reps)
    if sel.mode == "points":
        return OpResult(out, Selection("points", points={second[i] for i in reps if i in second}))
    return OpResult(out, Selection(sel.mode))


def _plane_axis(name: str) -> int:
    return {"XY": 2, "ZX": 1, "YZ": 0}.get(name, 2)


def _object_matrix(value) -> np.ndarray:
    if value is None:
        return np.eye(4)
    m = np.asarray(value, float)
    if m.shape == (3, 4):
        m = np.vstack([m, [0.0, 0.0, 0.0, 1.0]])
    if m.shape != (4, 4) or abs(float(np.linalg.det(m[:3, :3]))) < 1e-12:
        return np.eye(4)
    return m


def _reflector(p: dict):
    axis = _plane_axis(str(p["mirror_plane"]))
    normal = np.zeros(3)
    normal[axis] = 1.0
    origin = np.zeros(3) if p.get("plane_origin") is None else np.asarray(p["plane_origin"], float)
    matrix = _object_matrix(p.get("object_matrix")) if p["coordinate_system"] == "World" else np.eye(4)
    linear, offset = matrix[:3, :3], matrix[:3, 3]
    inverse = np.linalg.inv(linear)

    def reflect(pts: np.ndarray) -> np.ndarray:
        world = pts @ linear.T + offset
        world = world - 2.0 * ((world - origin) @ normal)[:, None] * normal
        return (world - offset) @ inverse.T

    return reflect


def _mirror_scope(mesh: Mesh, sel: Selection) -> tuple[list[int], list[int]]:
    if sel.mode == "polygons":
        faces = _scope_faces(mesh, sel)
        pts = sorted({i for f in faces for i in mesh.polygons[f]})
        if len(faces) == len(mesh.polygons):
            pts = list(range(len(mesh.points)))
        return pts, faces
    pts = _valid_points(mesh, sel) if not sel.is_empty() else list(range(len(mesh.points)))
    pset = set(pts)
    faces = [f for f, poly in enumerate(mesh.polygons) if all(i in pset for i in poly)]
    return pts, faces


def _valid_points(mesh: Mesh, sel: Selection) -> list[int]:
    if sel.mode == "edges":
        return sorted({i for e in _valid_edges(mesh, sel) for i in e})
    return sorted(i for i in sel.points if 0 <= i < len(mesh.points))


def _whole_components(mesh: Mesh, faces: list[int]) -> list[int]:
    fset = set(faces)
    parent, find = _union_find({f: True for f in range(len(mesh.polygons))})
    for owners in edge_faces(mesh).values():
        for g in owners[1:]:
            _union(parent, find, owners[0], g)
    inside: dict = {}
    for f in range(len(mesh.polygons)):
        root = find(f)
        inside[root] = inside.get(root, True) and f in fset
    return [f for f in faces if inside[find(f)]]


def _mirror_in_place(mesh: Mesh, sel: Selection, pts: list[int], faces: list[int], reflect) -> OpResult:
    mesh.points[pts] = reflect(mesh.points[pts])
    for f in _whole_components(mesh, faces):
        mesh.polygons[f] = _reversed(mesh.polygons[f])
    mesh._rebuild_edges()
    return OpResult(mesh, sel)


def _weld_target(points: np.ndarray, i: int, pos: np.ndarray, tol: float) -> int | None:
    dist = np.linalg.norm(points - pos, axis=1)
    if float(dist[i]) <= tol + 1e-12:
        return i
    k = int(np.argmin(dist))
    return k if float(dist[k]) <= tol + 1e-12 else None


def _mirror_copy(mesh: Mesh, sel: Selection, pts: list[int], faces: list[int], reflect, p: dict) -> OpResult:
    tol = float(p["tolerance"])
    base = mesh.points.copy()
    mirrored = reflect(base[pts])
    copy: dict[int, int] = {}
    moved: dict[int, np.ndarray] = {}
    for i, pos in zip(pts, mirrored):
        target = _weld_target(mesh.points, i, pos, tol) if p["weld_points"] else None
        if target is None:
            copy[i] = mesh.add_point(pos)
            continue
        copy[i] = target
        if target == i:
            moved[i] = (pos + base[i]) / 2.0
    for i, pos in moved.items():
        mesh.points[i] = pos
    have = {frozenset(poly) for poly in mesh.polygons}
    new_faces: set[int] = set()
    for f in faces:
        ring = clean_polygons([[copy[i] for i in mesh.polygons[f]]])
        if not ring:
            continue
        mirror_poly = _reversed(ring[0])
        key = frozenset(mirror_poly)
        if key in have:
            continue
        have.add(key)
        mesh.polygons.append(mirror_poly)
        new_faces.add(len(mesh.polygons) - 1)
    pset = set(pts)
    for a, b in list(mesh.loose_edges):
        if a in pset and b in pset and copy[a] != copy[b] and edge_key(copy[a], copy[b]) != edge_key(a, b):
            mesh.loose_edges.append(edge_key(copy[a], copy[b]))
    mesh._rebuild_edges()
    return OpResult(mesh, _mirror_selection(mesh, sel, pts, copy, new_faces))


def _mirror_selection(mesh: Mesh, sel: Selection, pts: list[int], copy: dict, new_faces: set) -> Selection:
    if sel.mode == "polygons":
        return Selection("polygons", polygons=new_faces)
    if sel.mode == "edges":
        existing = set(mesh.edges)
        edges = {edge_key(copy[a], copy[b]) for a, b in sel.edges if a in copy and b in copy}
        return Selection("edges", edges={e for e in edges if e in existing})
    return Selection("points", points={copy[i] for i in pts})


def mirror(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode not in COMPONENT_MODES:
        return OpResult(mesh, sel, False, "Mirror needs points, edges or polygons mode")
    if not len(mesh.points):
        return OpResult(mesh, sel, False, "Mirror: the object has no points")
    pts, faces = _mirror_scope(mesh, sel)
    if not pts:
        return OpResult(mesh, sel, False, "Mirror: nothing to mirror")
    reflect = _reflector(p)
    if p["duplicate_points"]:
        return _mirror_copy(mesh, sel, pts, faces, reflect, p)
    return _mirror_in_place(mesh, sel, pts, faces, reflect)


def _delete_points(mesh: Mesh, sel: Selection) -> OpResult:
    gone = {i for i in sel.points if 0 <= i < len(mesh.points)}
    if not gone:
        return OpResult(mesh, sel, False, "Delete: no points selected")
    before = _used_points(mesh)
    polys = [poly for poly in mesh.polygons if not gone & set(poly)]
    loose = [e for e in mesh.loose_edges if not gone & set(e)]
    keep = [i for i in range(len(mesh.points)) if i not in gone]
    trimmed, remap = compact(Mesh(mesh.points, polys, loose), keep=keep)
    out, _ = _drop_orphans(trimmed, {remap[i] for i in before if i in remap})
    return OpResult(out, Selection("points"))


def _delete_polygons(mesh: Mesh, sel: Selection) -> OpResult:
    gone = {f for f in sel.polygons if 0 <= f < len(mesh.polygons)}
    if not gone:
        return OpResult(mesh, sel, False, "Delete: no polygons selected")
    touched = {i for f in gone for i in mesh.polygons[f]}
    polys = [poly for f, poly in enumerate(mesh.polygons) if f not in gone]
    keep = [i for i in range(len(mesh.points)) if i not in touched]
    out, _ = compact(Mesh(mesh.points, polys, mesh.loose_edges), keep=keep)
    return OpResult(out, Selection("polygons"))


def _single_loop(boundary: list[tuple[int, int]]) -> list[int] | None:
    nxt: dict[int, int] = {}
    for u, v in boundary:
        if u in nxt:
            return None
        nxt[u] = v
    if not nxt:
        return None
    start = min(nxt)
    loop = [start]
    cur = nxt[start]
    while cur != start:
        if cur not in nxt or len(loop) > len(nxt):
            return None
        loop.append(cur)
        cur = nxt[cur]
    return loop if len(loop) == len(nxt) and len(loop) >= 3 else None


def _region_outline(mesh: Mesh, region: list[int]) -> list[int] | None:
    directed = [(u, v) for f in region for u, v in directed_edges(mesh.polygons[f])]
    present = set(directed)
    boundary = [(u, v) for u, v in directed if (v, u) not in present]
    return _single_loop(boundary)


def _edge_regions(mesh: Mesh, edges: list) -> tuple[list[list[int]], set[int]]:
    ef = edge_faces(mesh)
    faces = {f for e in edges for f in ef.get(e, ())}
    parent, find = _union_find({f: True for f in faces})
    doomed: set[int] = set()
    for e in edges:
        owners = ef.get(e, [])
        if len(owners) == 2:
            _union(parent, find, owners[0], owners[1])
        elif len(owners) == 1:
            doomed.add(owners[0])
    regions: dict[int, list[int]] = {}
    for f in faces:
        regions.setdefault(find(f), []).append(f)
    doomed_roots = {find(f) for f in doomed}
    kill = {f for root, group in regions.items() if root in doomed_roots for f in group}
    merge = [sorted(g) for root, g in regions.items() if root not in doomed_roots and len(g) > 1]
    return merge, kill


def _delete_edges(mesh: Mesh, sel: Selection) -> OpResult:
    edges = _valid_edges(mesh, sel)
    if not edges:
        return OpResult(mesh, sel, False, "Delete: no edges selected")
    eset = set(edges)
    before = _used_points(mesh)
    loose_before = len(mesh.loose_edges)
    mesh.loose_edges = [e for e in mesh.loose_edges if e not in eset]
    merge, kill = _edge_regions(mesh, edges)
    skipped = 0
    for region in merge:
        outline = _region_outline(mesh, region)
        if outline is None:
            skipped += 1
            continue
        mesh.polygons[region[0]] = tuple(outline)
        kill |= set(region[1:])
    if not kill and len(mesh.loose_edges) == loose_before:
        return OpResult(mesh, sel, False, "Delete: the selected edges cannot be removed")
    _drop_faces(mesh, kill)
    mesh._rebuild_edges()
    out, _ = _drop_orphans(mesh, before)
    message = f"Delete: {skipped} edge region(s) could not become one N-gon" if skipped else ""
    return OpResult(out, Selection("edges"), True, message)


def delete(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode == "points":
        return _delete_points(mesh, sel)
    if sel.mode == "edges":
        return _delete_edges(mesh, sel)
    if sel.mode == "polygons":
        return _delete_polygons(mesh, sel)
    return OpResult(mesh, sel, False, "Delete needs points, edges or polygons mode")


register(ToolSpec(
    id="subdivide",
    name="Subdivide",
    apply=subdivide,
    modes=ALL_MODES,
    params=(
        Param("subdivision_surface", "Subdivision Surface", "bool", False, modes=("points", "polygons", "model")),
        Param("subdivision", "Subdivision", "int", 1, 1, 100, 1),
        Param("max_angle", "Maximum Angle", "angle", 180.0, 0.0, 180.0, 1.0, "°",
              modes=("points", "polygons", "model")),
    ),
    interactive=False,
    section="COMMANDS",
    shortcut="U~S",
    description="Subdivides the selected polygons (or the whole object), optionally smoothing like a Subdivision Surface.",
))

register(ToolSpec(
    id="triangulate",
    name="Triangulate",
    apply=triangulate,
    modes=ALL_MODES,
    interactive=False,
    section="CONVERSION",
    description="Splits the selected quads and N-gons (or the whole object) into triangles.",
))

register(ToolSpec(
    id="untriangulate",
    name="Untriangulate",
    apply=untriangulate,
    modes=ALL_MODES,
    params=(
        Param("evaluate_angle", "Evaluate Angle", "bool", False),
        Param("angle", "Angle", "angle", 0.1, 0.0, 180.0, 0.1, "°"),
    ),
    interactive=False,
    section="CONVERSION",
    shortcut="U~U",
    description="Joins pairs of adjacent triangles into quads.",
))

register(ToolSpec(
    id="reverse_normals",
    name="Reverse Normals",
    apply=reverse_normals,
    modes=ALL_MODES,
    interactive=False,
    section="NORMALS",
    shortcut="U~R",
    description="Flips the direction of the selected polygons (or all polygons).",
))

register(ToolSpec(
    id="align_normals",
    name="Align Normals",
    apply=align_normals,
    modes=ALL_MODES,
    interactive=False,
    section="NORMALS",
    shortcut="U~A",
    description="Makes polygon normals consistent, pointing outward on closed meshes.",
))

register(ToolSpec(
    id="spin_edge",
    name="Spin Edge",
    apply=spin_edge,
    modes=("edges", "polygons"),
    interactive=False,
    section="COMMANDS",
    shortcut="U~V",
    description="Turns each selected edge one step inside the two polygons that share it.",
))

register(ToolSpec(
    id="collapse",
    name="Collapse",
    apply=collapse,
    modes=COMPONENT_MODES,
    interactive=False,
    section="COMMANDS",
    shortcut="U~C",
    description="Merges the selected points, or each connected group of edges or polygons, into one point at its center.",
))

register(ToolSpec(
    id="mirror",
    name="Mirror",
    apply=mirror,
    modes=COMPONENT_MODES,
    params=(
        Param("coordinate_system", "Coordinate System", "choice", "Object", choices=("Object", "World")),
        Param("mirror_plane", "Mirror Plane", "choice", "XY", choices=("XY", "ZX", "YZ")),
        Param("duplicate_points", "Duplicate Points", "bool", True),
        Param("weld_points", "Weld Points", "bool", True),
        Param("tolerance", "Tolerance", "distance", 0.01, 0.0, 1e6, 0.01, "cm"),
        Param("plane_origin", "Plane Origin", "runtime", None),
        Param("object_matrix", "Object Matrix", "runtime", None),
    ),
    interactive=True,
    drag_param=None,
    section="TRANSFORM",
    shortcut="M~H",
    description="Mirrors the selected elements across a plane, optionally duplicating and welding them.",
    extra={
        "pick": "point",
        "runtime": {
            "plane_origin": "(x, y, z) point the mirror plane passes through, in the chosen coordinate system; "
                            "set by clicking in the viewport, None means the origin",
            "object_matrix": "4x4 (or 3x4) object-to-world matrix, used when Coordinate System is World; "
                             "None means identity",
        },
    },
))

register(ToolSpec(
    id="delete",
    name="Delete",
    apply=delete,
    modes=COMPONENT_MODES,
    interactive=False,
    section="COMMANDS",
    shortcut="Delete",
    description="Deletes the selected points, edges or polygons; deleted edges merge their polygons into N-gons.",
))
