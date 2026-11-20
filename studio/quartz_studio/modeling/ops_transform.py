from __future__ import annotations

import math
import random

import numpy as np

from ..scene import Mesh
from .meshkit import (OpResult, Selection, clone, directed_edges, edge_faces, edge_groups, edge_key,
                      face_groups, face_normals, point_normals_for_faces, region_boundary,
                      triangulate_polygon, vertex_normals)
from .registry import Param, ToolSpec, register

__all__ = ["slide", "equal_spacing", "straighten_edges", "fit_circle", "flatten", "iron", "smooth_edges",
           "randomize", "normal_move", "normal_scale", "normal_rotate"]


def _fail(mesh: Mesh, sel: Selection, message: str) -> OpResult:
    return OpResult(mesh, sel, False, message)


def _valid_points(mesh: Mesh, items) -> list[int]:
    return sorted({int(i) for i in items if 0 <= int(i) < len(mesh.points)})


def _valid_edges(mesh: Mesh, items) -> list[tuple[int, int]]:
    known = set(mesh.edges)
    return sorted({edge_key(*e) for e in items if edge_key(*e) in known})


def _valid_faces(mesh: Mesh, items) -> list[int]:
    return sorted({int(f) for f in items if 0 <= int(f) < len(mesh.polygons)})


def _moving_points(mesh: Mesh, sel: Selection) -> list[int]:
    if sel.mode == "points":
        return _valid_points(mesh, sel.points)
    if sel.mode == "edges":
        return sorted({i for e in _valid_edges(mesh, sel.edges) for i in e})
    if sel.mode == "polygons":
        return sorted({i for f in _valid_faces(mesh, sel.polygons) for i in mesh.polygons[f]})
    return []


def _neighbors(mesh: Mesh) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for a, b in mesh.edges:
        out.setdefault(a, []).append(b)
        out.setdefault(b, []).append(a)
    return out


def _owners(mesh: Mesh) -> dict[tuple[int, int], int]:
    out = {}
    for k, poly in enumerate(mesh.polygons):
        for a, b in directed_edges(poly):
            out[(a, b)] = k
    return out


def _succ(poly, v: int) -> int:
    i = poly.index(v)
    return poly[(i + 1) % len(poly)]


def _pred(poly, v: int) -> int:
    i = poly.index(v)
    return poly[i - 1]


def _unit(v: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(v))
    return v / length if length > 1e-12 else np.zeros(3)


def _blend(mesh: Mesh, targets: dict[int, np.ndarray], strength: float) -> None:
    s = float(strength) / 100.0
    base = mesh.points.copy()
    for i, t in targets.items():
        mesh.points[i] = base[i] + (np.asarray(t, float) - base[i]) * s


def _adjacency(edges) -> dict[int, list[int]]:
    adj: dict[int, list[int]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj


def _trace(adj: dict, stops: set, used: set, start: int, first: int) -> list[int]:
    path = [start, first]
    used.add(edge_key(start, first))
    while path[-1] not in stops:
        cur, prev = path[-1], path[-2]
        nxt = next((n for n in sorted(adj[cur]) if n != prev and edge_key(cur, n) not in used), None)
        if nxt is None:
            break
        used.add(edge_key(cur, nxt))
        path.append(nxt)
    return path


def _segments(edges) -> list[tuple[list[int], bool]]:
    edges = sorted({edge_key(*e) for e in edges if e[0] != e[1]})
    adj = _adjacency(edges)
    nodes = {v for v, n in adj.items() if len(n) != 2}
    used: set = set()
    out = []
    for start in sorted(nodes):
        for first in sorted(adj[start]):
            if edge_key(start, first) not in used:
                out.append((_trace(adj, nodes, used, start, first), False))
    for start in sorted(adj):
        for first in sorted(adj[start]):
            if edge_key(start, first) not in used:
                out.append((_trace(adj, {start}, used, start, first)[:-1], True))
    return out


def _selected_links(mesh: Mesh, sel: Selection) -> list[tuple[int, int]]:
    if sel.mode == "edges":
        return _valid_edges(mesh, sel.edges)
    pts = set(_valid_points(mesh, sel.points))
    return [e for e in mesh.edges if e[0] in pts and e[1] in pts]


def _chains(edges) -> tuple[list[tuple[list[int], bool]], bool]:
    chains = []
    branched = False
    for group in edge_groups(edges):
        adj = _adjacency(group)
        if any(len(n) > 2 for n in adj.values()):
            branched = True
            continue
        ends = sorted(i for i, n in adj.items() if len(n) == 1)
        cur = ends[0] if ends else min(adj)
        order = [cur]
        seen = {cur}
        while True:
            nxt = [n for n in sorted(adj[cur]) if n not in seen]
            if not nxt:
                break
            cur = nxt[0]
            order.append(cur)
            seen.add(cur)
        chains.append((order, not ends))
    return chains, branched


def _links(verts: list[int], closed: bool):
    n = len(verts)
    for k, v in enumerate(verts):
        prev = verts[k - 1] if (k > 0 or closed) else None
        nxt = verts[(k + 1) % n] if (k < n - 1 or closed) else None
        yield prev, v, nxt


def _chain_edges(verts: list[int], closed: bool) -> list[tuple[int, int]]:
    pairs = list(zip(verts, verts[1:]))
    if closed and len(verts) > 2:
        pairs.append((verts[-1], verts[0]))
    return pairs


def _walk(mesh: Mesh, owners: dict, f, v: int, stop: int, forward: bool):
    faces: list[int] = []
    rails: list[int] = []
    while f is not None and f not in faces:
        faces.append(f)
        poly = mesh.polygons[f]
        w = _succ(poly, v) if forward else _pred(poly, v)
        if w == stop:
            return faces, rails, True
        rails.append(w)
        f = owners.get((w, v)) if forward else owners.get((v, w))
    return faces, rails, False


def _fan(mesh: Mesh, owners: dict, prev, v: int, nxt):
    if prev is None:
        f = owners.get((v, nxt))
        return ([f], [_pred(mesh.polygons[f], v)]) if f is not None else ([], [])
    if nxt is None:
        f = owners.get((prev, v))
        return ([f], [_succ(mesh.polygons[f], v)]) if f is not None else ([], [])
    faces, rails, done = _walk(mesh, owners, owners.get((prev, v)), v, nxt, True)
    if done:
        return faces, rails
    back_faces, back_rails, _ = _walk(mesh, owners, owners.get((v, nxt)), v, prev, False)
    faces += [f for f in back_faces if f not in faces]
    rails += [w for w in reversed(back_rails) if w not in rails]
    return faces, rails


def _rail_target(points: np.ndarray, rails: list[int]):
    if not rails:
        return None
    k = len(rails)
    if k % 2:
        return points[rails[k // 2]].copy()
    return (points[rails[k // 2 - 1]] + points[rails[k // 2]]) / 2.0


def _side(mesh: Mesh, owners: dict, verts: list[int], closed: bool) -> list[dict]:
    out = []
    for prev, v, nxt in _links(verts, closed):
        faces, rails = _fan(mesh, owners, prev, v, nxt)
        out.append({"v": v, "prev": prev, "next": nxt, "faces": faces, "rails": rails,
                    "target": _rail_target(mesh.points, rails)})
    return out


def _side_direction(points: np.ndarray, side: list[dict]) -> np.ndarray:
    acc = np.zeros(3)
    for item in side:
        if item["target"] is not None:
            acc += _unit(item["target"] - points[item["v"]])
    return _unit(acc)


def _quadratic(origin, target, opposite, s: float, length: float, back: float) -> np.ndarray:
    a = origin * ((s + back) * (s - length)) / (back * -length)
    b = target * ((s + back) * s) / ((length + back) * length)
    c = opposite * (s * (s - length)) / ((-back) * (-back - length))
    return a + b + c


def _slid(origin: np.ndarray, target, opposite, p: dict, amount: float) -> np.ndarray:
    if target is None:
        return origin.copy()
    rail = target - origin
    length = float(np.linalg.norm(rail))
    if length < 1e-12:
        return origin.copy()
    t = abs(amount) / 100.0 if p["offset_mode"] == "Proportional" else abs(amount) / length
    if p["limit"]:
        t = min(t, 1.0)
    linear = origin + rail * t
    if not p["preserve_curvature"] or opposite is None:
        return linear
    back = float(np.linalg.norm(opposite - origin))
    if back < 1e-12:
        return linear
    return _quadratic(origin, target, opposite, t * length, length, back)


def _hovered(mesh: Mesh, p: dict, anchors: set[int]):
    edge = p.get("edge")
    if edge is None:
        return None
    a, b = int(edge[0]), int(edge[1])
    if not (0 <= a < len(mesh.points) and 0 <= b < len(mesh.points)) or a == b:
        return None
    flipped = b in anchors and a not in anchors
    return (b, a, flipped) if flipped else (a, b, flipped)


def _slide_amount(mesh: Mesh, p: dict, anchors: set[int]) -> float:
    hover = _hovered(mesh, p, anchors)
    pos = p.get("edge_position")
    if hover is None or pos is None:
        return float(p["offset_percent"] if p["offset_mode"] == "Proportional" else p["offset"])
    a, b, flipped = hover
    t = float(pos) / 100.0
    t = 1.0 - t if flipped else t
    if p["offset_mode"] == "Proportional":
        return t * 100.0
    return t * float(np.linalg.norm(mesh.points[b] - mesh.points[a]))


def _reference_direction(mesh: Mesh, p: dict, anchors: set[int], skip: set) -> np.ndarray | None:
    hover = _hovered(mesh, p, anchors)
    if hover is None or edge_key(hover[0], hover[1]) in skip:
        return None
    return _unit(mesh.points[hover[1]] - mesh.points[hover[0]])


def _shifted(position: np.ndarray, normal: np.ndarray, p: dict) -> np.ndarray:
    return position + normal * float(p["shift"])


def _pick_side(points, left, right, ref, flip):
    dl = float(_side_direction(points, left) @ ref)
    dr = float(_side_direction(points, right) @ ref)
    chosen, other = (left, right) if dl >= dr else (right, left)
    return (other, chosen) if flip else (chosen, other)


def _slide_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    edges = _valid_edges(mesh, sel.edges)
    if not edges:
        return _fail(mesh, sel, "Slide: no edges selected")
    chains, branched = _chains(edges)
    if branched or not chains:
        return _fail(mesh, sel, "Slide: the selected edges must form chains without branches")
    owners = _owners(mesh)
    sides = [(_side(mesh, owners, verts, closed), _side(mesh, owners, verts[::-1], closed), verts, closed)
             for verts, closed in chains]
    anchors = {v for verts, _ in chains for v in verts}
    ref = _reference_direction(mesh, p, anchors, set(edges))
    if ref is None:
        ref = _side_direction(mesh.points, sides[0][0])
        if not ref.any():
            ref = _side_direction(mesh.points, sides[0][1])
    amount = _slide_amount(mesh, p, anchors)
    normals = vertex_normals(mesh)
    if p["clone"]:
        return _slide_edges_clone(mesh, sel, sides, ref, amount, normals, p)
    new_points = mesh.points.copy()
    for left, right, verts, closed in sides:
        chosen, other = _pick_side(mesh.points, left, right, ref, amount < 0)
        opposite = {item["v"]: item["target"] for item in other}
        for item in chosen:
            v = item["v"]
            moved = _slid(mesh.points[v], item["target"], opposite.get(v), p, amount)
            new_points[v] = _shifted(moved, normals[v], p)
    mesh.points = new_points
    return OpResult(mesh, Selection("edges", edges=set(edges)))


def _slide_edges_clone(mesh: Mesh, sel: Selection, sides, ref, amount: float, normals, p: dict) -> OpResult:
    base = mesh.points.copy()
    owners = _owners(mesh)
    replace: dict[int, dict[int, int]] = {}
    inserts: dict[int, dict[tuple[int, int], list[int]]] = {}
    quads: list[tuple[int, ...]] = []
    new_edges: set[tuple[int, int]] = set()
    for left, right, verts, closed in sides:
        chosen, other = _pick_side(base, left, right, ref, amount < 0)
        on_chain = set(verts)
        if any(not item["faces"] or not item["rails"] or on_chain & set(item["rails"]) for item in chosen):
            return _fail(mesh, sel, "Slide: Clone needs a row of polygons on the side the edges slide to")
        opposite = {item["v"]: item["target"] for item in other}
        clones: dict[int, int] = {}
        for item in chosen:
            v = item["v"]
            moved = _slid(base[v], item["target"], opposite.get(v), p, amount)
            clones[v] = mesh.add_point(_shifted(moved, normals[v], p))
            for f in item["faces"]:
                replace.setdefault(f, {})[v] = clones[v]
            _endpoint_insert(owners, item, clones[v], inserts)
        order = [item["v"] for item in chosen]
        for a, b in _chain_edges(order, closed):
            quads.append((a, b, clones[b], clones[a]))
            new_edges.add(edge_key(clones[a], clones[b]))
    polys = []
    for k, poly in enumerate(mesh.polygons):
        ring = _apply_inserts(mesh.points, poly, inserts.get(k, {}))
        mapping = replace.get(k, {})
        polys.append(tuple(mapping.get(i, i) for i in ring))
    mesh.polygons = polys + quads
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("edges", edges=new_edges))


def _endpoint_insert(owners: dict, item: dict, new: int, inserts: dict) -> None:
    v = item["v"]
    if not item["rails"] or (item["prev"] is not None and item["next"] is not None):
        return
    w = item["rails"][0]
    key = (v, w) if item["prev"] is None else (w, v)
    g = owners.get(key)
    if g is not None and g not in item["faces"]:
        inserts.setdefault(g, {}).setdefault(key, []).append(new)


def _ordered_between(points: np.ndarray, a: int, b: int, mids) -> list[int]:
    lo = min(a, b)
    order = sorted(mids, key=lambda n: (float(np.linalg.norm(points[n] - points[lo])), n))
    return order if a == lo else order[::-1]


def _apply_inserts(points: np.ndarray, poly, inserts: dict) -> tuple[int, ...]:
    if not inserts:
        return tuple(poly)
    ring = []
    for a, b in directed_edges(poly):
        ring.append(a)
        ring += _ordered_between(points, a, b, inserts.get((a, b), []))
    return tuple(ring)


def _slide_points(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    pts = _valid_points(mesh, sel.points)
    if not pts:
        return _fail(mesh, sel, "Slide: no points selected")
    nbrs = _neighbors(mesh)
    pts = [i for i in pts if nbrs.get(i)]
    if not pts:
        return _fail(mesh, sel, "Slide: the selected points have no edges to slide along")
    base = mesh.points.copy()
    normals = vertex_normals(mesh)
    ref = _reference_direction(mesh, p, set(pts), set())
    if ref is None:
        ref = _unit(base[min(nbrs[pts[0]])] - base[pts[0]])
    amount = _slide_amount(mesh, p, set(pts))
    if amount < 0:
        ref = -ref
    moves = []
    for i in pts:
        fwd = max(sorted(nbrs[i]), key=lambda q: float(_unit(base[q] - base[i]) @ ref))
        rest = [q for q in sorted(nbrs[i]) if q != fwd]
        back = max(rest, key=lambda q: float(_unit(base[q] - base[i]) @ -ref)) if rest else None
        opposite = base[back] if back is not None else None
        moved = _slid(base[i], base[fwd], opposite, p, amount)
        moves.append((i, fwd, _shifted(moved, normals[i], p)))
    if p["clone"]:
        return _clone_points(mesh, moves)
    for i, _, pos in moves:
        mesh.points[i] = pos
    return OpResult(mesh, Selection("points", points=set(pts)))


def _clone_points(mesh: Mesh, moves) -> OpResult:
    splits: dict[tuple[int, int], list[int]] = {}
    created = set()
    for i, q, pos in moves:
        n = mesh.add_point(pos)
        created.add(n)
        splits.setdefault(edge_key(i, q), []).append(n)
    inserts = {}
    for k, poly in enumerate(mesh.polygons):
        for a, b in directed_edges(poly):
            if edge_key(a, b) in splits:
                inserts.setdefault(k, {})[(a, b)] = splits[edge_key(a, b)]
    mesh.polygons = [_apply_inserts(mesh.points, poly, inserts.get(k, {}))
                     for k, poly in enumerate(mesh.polygons)]
    loose = []
    for a, b in mesh.loose_edges:
        chain = [a] + _ordered_between(mesh.points, a, b, splits.get((a, b), [])) + [b]
        loose += [edge_key(u, w) for u, w in zip(chain, chain[1:])]
    mesh.loose_edges = loose
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("points", points=created))


def slide(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode == "edges":
        return _slide_edges(mesh, sel, p)
    if sel.mode == "points":
        return _slide_points(mesh, sel, p)
    return _fail(mesh, sel, "Slide works in points and edges mode")


def _resample(ring: np.ndarray, closed: bool, fractions) -> list[np.ndarray]:
    path = np.vstack([ring, ring[:1]]) if closed else ring
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    out = []
    for f in fractions:
        s = f * total
        k = int(np.clip(np.searchsorted(cum, s, side="right") - 1, 0, len(seg) - 1))
        t = (s - cum[k]) / seg[k] if seg[k] > 1e-12 else 0.0
        out.append(path[k] + (path[k + 1] - path[k]) * t)
    return out


def _hermite(ring: np.ndarray, samples: int = 24) -> np.ndarray:
    seg = np.linalg.norm(np.diff(ring, axis=0), axis=1)
    if len(ring) < 3 or np.any(seg < 1e-12):
        return ring
    t = np.concatenate([[0.0], np.cumsum(seg)])
    tangents = np.zeros_like(ring)
    tangents[0] = (ring[1] - ring[0]) / seg[0]
    tangents[-1] = (ring[-1] - ring[-2]) / seg[-1]
    for k in range(1, len(ring) - 1):
        tangents[k] = (ring[k + 1] - ring[k - 1]) / (t[k + 1] - t[k - 1])
    out = [ring[0]]
    for k in range(len(ring) - 1):
        h = seg[k]
        for s in np.linspace(0.0, 1.0, samples + 1)[1:]:
            h00 = 2 * s ** 3 - 3 * s ** 2 + 1
            h10 = s ** 3 - 2 * s ** 2 + s
            h01 = -2 * s ** 3 + 3 * s ** 2
            h11 = s ** 3 - s ** 2
            out.append(h00 * ring[k] + h10 * h * tangents[k] + h01 * ring[k + 1] + h11 * h * tangents[k + 1])
    return np.array(out)


def _column_walk(perp: dict, free: set, seen: set, start: int, first: int):
    path = []
    prev, cur = start, first
    while cur in free:
        if cur in seen:
            return None
        seen.add(cur)
        path.append(cur)
        nxt = [n for n in perp[cur] if n != prev]
        if len(nxt) != 1:
            return None
        prev, cur = cur, nxt[0]
    path.append(cur)
    return path


def _columns(perp: dict, free: set) -> list[list[int]]:
    seen: set = set()
    out = []
    for v in sorted(free):
        if v in seen:
            continue
        seen.add(v)
        a, b = sorted(perp[v])
        left = _column_walk(perp, free, seen, v, a)
        right = _column_walk(perp, free, seen, v, b)
        if left is not None and right is not None:
            out.append(left[::-1] + [v] + right)
    return out


def _column_targets(ring: np.ndarray, linear: bool) -> list[np.ndarray]:
    k = len(ring) - 1
    fractions = [j / k for j in range(1, k)]
    if linear:
        return [ring[0] + (ring[-1] - ring[0]) * f for f in fractions]
    return _resample(_hermite(ring), False, fractions)


def equal_spacing(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode != "edges":
        return _fail(mesh, sel, "Equal Spacing works in edges mode")
    edges = _valid_edges(mesh, sel.edges)
    if not edges:
        return _fail(mesh, sel, "Equal Spacing: no edges selected")
    chosen = set(edges)
    pts = {i for e in edges for i in e}
    perp: dict[int, list[int]] = {}
    for a, b in mesh.edges:
        if (a, b) in chosen or (a not in pts and b not in pts):
            continue
        perp.setdefault(a, []).append(b)
        perp.setdefault(b, []).append(a)
    free = {v for v in pts if len(perp.get(v, [])) == 2}
    columns = _columns(perp, free)
    if not columns:
        return _fail(mesh, sel, "Equal Spacing: select edge loops that have neighbouring loops on both sides")
    targets = {}
    for col in columns:
        for v, pos in zip(col[1:-1], _column_targets(mesh.points[col], bool(p["linear"]))):
            targets[v] = pos
    _blend(mesh, targets, p["strength"])
    return OpResult(mesh, Selection("edges", edges=set(edges)))


def straighten_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode not in ("points", "edges"):
        return _fail(mesh, sel, "Straighten Edges works in points and edges mode")
    segments = [v for v, closed in _segments(_selected_links(mesh, sel)) if not closed and v[0] != v[-1]]
    if not segments:
        return _fail(mesh, sel, "Straighten Edges: select an open edge chain")
    targets = {}
    for verts in segments:
        ring = mesh.points[verts]
        start, end = ring[0], ring[-1]
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(ring, axis=0), axis=1))])
        n = len(verts)
        for k, v in enumerate(verts[1:-1], start=1):
            t = k / (n - 1) if p["equal_spacing"] or cum[-1] < 1e-12 else cum[k] / cum[-1]
            targets[v] = start + (end - start) * t
    _blend(mesh, targets, p["strength"])
    return OpResult(mesh, sel.copy())


def _loops_from_directed(directed) -> list[list[int]]:
    nxt = {u: v for u, v in directed}
    loops = []
    seen = set()
    for start in sorted(nxt):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        cur = nxt[start]
        while cur != start and cur in nxt and cur not in seen:
            loop.append(cur)
            seen.add(cur)
            cur = nxt[cur]
        if cur == start and len(loop) >= 3:
            loops.append(loop)
    return loops


def _perimeter(points: np.ndarray, loop: list[int]) -> float:
    ring = points[loop]
    return float(np.linalg.norm(ring - np.roll(ring, -1, axis=0), axis=1).sum())


def _outline_sets(mesh: Mesh, faces: list[int]) -> list[tuple[list[int], list[int], list[tuple[int, int]]]]:
    out = []
    for group in face_groups(mesh, faces):
        boundary = region_boundary(mesh, group)
        loops = _loops_from_directed(boundary)
        if not loops:
            continue
        outer = max(loops, key=lambda loop: _perimeter(mesh.points, loop))
        inner = sorted({i for f in group for i in mesh.polygons[f]} - set(outer))
        out.append((outer, inner, [edge_key(*e) for e in boundary]))
    return out


def _covered_faces(mesh: Mesh, sel: Selection) -> list[int]:
    if sel.mode == "polygons":
        return _valid_faces(mesh, sel.polygons)
    if sel.mode == "edges":
        chosen = set(_valid_edges(mesh, sel.edges))
        return [k for k, poly in enumerate(mesh.polygons)
                if all(edge_key(a, b) in chosen for a, b in directed_edges(poly))]
    pts = set(_valid_points(mesh, sel.points))
    return [k for k, poly in enumerate(mesh.polygons) if all(i in pts for i in poly)]


def _fit_sets(mesh: Mesh, sel: Selection):
    faces = _covered_faces(mesh, sel)
    if faces:
        return _outline_sets(mesh, faces)
    loops = [v for v, closed in _segments(_selected_links(mesh, sel)) if closed and len(v) >= 3]
    return [(loop, [], []) for loop in loops]


def _newell(ring: np.ndarray) -> np.ndarray:
    nxt = np.roll(ring, -1, axis=0)
    return np.cross(ring, nxt).sum(axis=0)


def _loop_frame(ring: np.ndarray):
    center = ring.mean(axis=0)
    _, _, vt = np.linalg.svd(ring - center)
    u, w = vt[0], vt[1]
    if float(np.cross(u, w) @ _newell(ring - center)) < 0:
        w = -w
    return center, u, w, np.cross(u, w)


def _circle_2d(xy: np.ndarray) -> tuple[float, float, float]:
    mean = xy.mean(axis=0)
    spread = np.linalg.svd(xy - mean, compute_uv=False)
    fallback = (float(mean[0]), float(mean[1]), float(np.linalg.norm(xy - mean, axis=1).mean()))
    if len(xy) < 3 or spread[-1] < 1e-9 * max(1.0, spread[0]):
        return fallback
    a = np.column_stack([xy[:, 0], xy[:, 1], np.ones(len(xy))])
    b = -(xy ** 2).sum(axis=1)
    sol = np.linalg.lstsq(a, b, rcond=None)[0]
    cx, cy = -sol[0] / 2.0, -sol[1] / 2.0
    r2 = cx * cx + cy * cy - sol[2]
    if not np.isfinite(r2) or r2 <= 0:
        return fallback
    return float(cx), float(cy), float(math.sqrt(r2))


def _circle_targets(ring: np.ndarray, p: dict) -> np.ndarray:
    center, u, w, _ = _loop_frame(ring)
    rel = ring - center
    xy = np.column_stack([rel @ u, rel @ w])
    cx, cy, fitted = _circle_2d(xy)
    radius = float(p["radius"]) if p["exact_radius"] else fitted * float(p["scale"]) / 100.0
    d = xy - np.array([cx, cy])
    angles = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    dist = np.linalg.norm(d, axis=1)
    if p["equal_spacing"]:
        angles = angles[0] + 2.0 * math.pi * np.arange(len(ring)) / len(ring)
    angles = angles + math.radians(float(p["angle"]))
    radial = dist + (radius - dist) * float(p["roundness"]) / 100.0
    origin = center + u * cx + w * cy
    return origin + radial[:, None] * (np.cos(angles)[:, None] * u + np.sin(angles)[:, None] * w)


def _inner_targets(points: np.ndarray, loop: list[int], moved: np.ndarray, inner: list[int]) -> dict:
    if not inner:
        return {}
    src = points[loop]
    shift = moved - src
    out = {}
    for i in inner:
        d2 = ((src - points[i]) ** 2).sum(axis=1)
        weights = 1.0 / np.maximum(d2, 1e-12)
        out[i] = points[i] + (weights[:, None] * shift).sum(axis=0) / weights.sum()
    return out


def _triangles(mesh: Mesh) -> np.ndarray:
    tris = [t for k in range(len(mesh.polygons)) for t in triangulate_polygon(mesh, k)]
    if not tris:
        return np.zeros((0, 3, 3))
    return mesh.points[np.array(tris)]


def _closest_on_triangles(p: np.ndarray, tris: np.ndarray) -> np.ndarray:
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    ab, ac, ap, bp, cp = b - a, c - a, p - a, p - b, p - c
    d1, d2 = (ap * ab).sum(1), (ap * ac).sum(1)
    d3, d4 = (bp * ab).sum(1), (bp * ac).sum(1)
    d5, d6 = (cp * ab).sum(1), (cp * ac).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = va + vb + vc
        res = a + ab * (vb / denom)[:, None] + ac * (vc / denom)[:, None]
        cases = [
            (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0),
            (vb <= 0) & (d2 >= 0) & (d6 <= 0),
            (d6 >= 0) & (d5 <= d6),
            (vc <= 0) & (d1 >= 0) & (d3 <= 0),
            (d3 >= 0) & (d4 <= d3),
            (d1 <= 0) & (d2 <= 0),
        ]
        values = [
            b + (c - b) * ((d4 - d3) / ((d4 - d3) + (d5 - d6)))[:, None],
            a + ac * (d2 / (d2 - d6))[:, None],
            c,
            a + ab * (d1 / (d1 - d3))[:, None],
            b,
            a,
        ]
    for mask, value in zip(cases, values):
        res = np.where(mask[:, None], value, res)
    dist = np.linalg.norm(res - p, axis=1)
    if np.all(np.isnan(dist)):
        return p.copy()
    return res[int(np.nanargmin(dist))]


def fit_circle(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode not in ("points", "edges", "polygons"):
        return _fail(mesh, sel, "Fit Circle works in points, edges and polygons mode")
    sets = _fit_sets(mesh, sel)
    if not sets:
        return _fail(mesh, sel, "Fit Circle: the selection must form a closed loop or an open polygon region")
    base = mesh.points.copy()
    tris = _triangles(mesh) if p["project_to_surface"] else None
    targets: dict[int, np.ndarray] = {}
    outline: set = set()
    for loop, inner, boundary in sets:
        moved = _circle_targets(base[loop], p)
        targets.update(zip(loop, moved))
        if p["adjust_inner_points"]:
            targets.update(_inner_targets(base, loop, moved, inner))
        outline |= set(boundary)
    if tris is not None and len(tris):
        targets = {i: _closest_on_triangles(t, tris) for i, t in targets.items()}
    _blend(mesh, targets, p["strength"])
    out = sel.copy()
    if sel.mode == "polygons" and p["select_outline"]:
        out.edges = outline
    return OpResult(mesh, out)


def _islands(mesh: Mesh, sel: Selection, pts: list[int]) -> list[list[int]]:
    if sel.mode == "polygons":
        faces = _valid_faces(mesh, sel.polygons)
        return [sorted({i for f in g for i in mesh.polygons[f]}) for g in face_groups(mesh, faces)]
    links = _selected_links(mesh, sel)
    grouped = [sorted({i for e in g for i in e}) for g in edge_groups(links)] if links else []
    used = {i for g in grouped for i in g}
    return grouped + [[i] for i in pts if i not in used]


def _outline_points(mesh: Mesh, sel: Selection, island: list[int]) -> list[int]:
    wanted = set(island)
    if sel.mode == "polygons":
        faces = [f for f in _valid_faces(mesh, sel.polygons) if wanted & set(mesh.polygons[f])]
        rim = {i for e in region_boundary(mesh, faces) for i in e}
    else:
        nbrs = _neighbors(mesh)
        chosen = set(_moving_points(mesh, sel))
        rim = {i for i in island if any(n not in chosen for n in nbrs.get(i, []))}
    rim &= wanted
    return sorted(rim) if rim else island


def _island_normal(mesh: Mesh, sel: Selection, island: list[int]) -> np.ndarray:
    wanted = set(island)
    if sel.mode == "polygons":
        faces = [f for f in _valid_faces(mesh, sel.polygons) if wanted & set(mesh.polygons[f])]
    else:
        faces = [k for k, poly in enumerate(mesh.polygons) if set(poly) <= wanted]
        if not faces:
            faces = [k for k, poly in enumerate(mesh.polygons) if wanted & set(poly)]
    if not faces:
        return np.zeros(3)
    return _unit(face_normals(mesh)[faces].sum(axis=0))


def _best_fit_normal(ring: np.ndarray) -> np.ndarray:
    if len(ring) < 3:
        return np.zeros(3)
    _, s, vt = np.linalg.svd(ring - ring.mean(axis=0))
    if s[1] < 1e-9 * max(1.0, s[0]):
        return np.zeros(3)
    return vt[2]


_AXES = {"X": 0, "Y": 1, "Z": 2}


def _modeling_axis(p: dict, center: np.ndarray):
    value = p.get("modeling_axis")
    if value is None:
        return center, np.eye(3)
    rows = np.asarray(value, float).reshape(-1, 3)
    if len(rows) >= 4:
        return rows[0], rows[1:4]
    return center, rows[:3]


def _flatten_plane(mesh: Mesh, sel: Selection, island: list[int], p: dict):
    ref = _outline_points(mesh, sel, island) if p["outline_only"] else island
    center = mesh.points[ref].mean(axis=0)
    axis = _AXES.get(p["axis"], 1)
    mode = p["mode"]
    if mode == "Modeling Axis":
        origin, axes = _modeling_axis(p, center)
        return origin, _unit(axes[axis]), False
    normal = np.zeros(3)
    origin = center
    if mode == "World Axis":
        normal = np.eye(3)[axis]
        origin = np.zeros(3) if p["use_axis_position"] else center
    elif mode == "View" and p.get("view_direction") is not None:
        normal = _unit(np.asarray(p["view_direction"], float))
    elif mode == "Normal":
        normal = _island_normal(mesh, sel, island)
    if not normal.any():
        normal = _best_fit_normal(mesh.points[ref])
    if not normal.any():
        normal = _island_normal(mesh, sel, island)
    if not normal.any():
        return None
    return origin, normal, True


def _plane_offset(points: np.ndarray, origin: np.ndarray, normal: np.ndarray, position: float) -> np.ndarray:
    d = (points - origin) @ normal
    reach = float(d.max()) if position >= 0 else -float(d.min())
    return origin + normal * reach * position / 100.0


def flatten(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    pts = _moving_points(mesh, sel)
    if not pts:
        return _fail(mesh, sel, "Flatten: nothing selected")
    islands = _islands(mesh, sel, pts) if p["individual_islands"] and p["mode"] != "Modeling Axis" else [pts]
    base = mesh.points.copy()
    targets = {}
    for island in islands:
        plane = _flatten_plane(mesh, sel, island, p)
        if plane is None:
            continue
        origin, normal, movable = plane
        if movable:
            origin = _plane_offset(base[island], origin, normal, float(p["position"]))
        for i in island:
            targets[i] = base[i] - float((base[i] - origin) @ normal) * normal
    if not targets:
        return _fail(mesh, sel, "Flatten: could not find a plane for the selection")
    _blend(mesh, targets, p["strength"])
    return OpResult(mesh, sel.copy())


def _dihedral_max(mesh: Mesh) -> dict[int, float]:
    normals = face_normals(mesh)
    out: dict[int, float] = {}
    for (a, b), faces in edge_faces(mesh).items():
        if len(faces) != 2:
            continue
        c = float(np.clip(normals[faces[0]] @ normals[faces[1]], -1.0, 1.0))
        angle = math.degrees(math.acos(c))
        for i in (a, b):
            out[i] = max(out.get(i, 0.0), angle)
    return out


def _boundary_points(mesh: Mesh) -> set[int]:
    return {i for e, faces in edge_faces(mesh).items() if len(faces) == 1 for i in e}


def iron(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    pts = _moving_points(mesh, sel)
    if not pts:
        return _fail(mesh, sel, "Iron: nothing selected")
    if not mesh.polygons:
        return _fail(mesh, sel, "Iron needs polygons around the selection")
    bend = _dihedral_max(mesh)
    limit = float(p["angle"])
    pts = [i for i in pts if 180.0 - bend.get(i, 0.0) >= limit - 1e-6]
    if p["preserve_boundaries"]:
        rim = _boundary_points(mesh)
        pts = [i for i in pts if i not in rim]
    nbrs = _neighbors(mesh)
    normals = vertex_normals(mesh)
    s = float(p["strength"]) / 100.0
    new_points = mesh.points.copy()
    for i in pts:
        ring = nbrs.get(i, [])
        if not ring or not normals[i].any():
            continue
        centroid = mesh.points[ring].mean(axis=0)
        new_points[i] = mesh.points[i] + float((centroid - mesh.points[i]) @ normals[i]) * normals[i] * s
    mesh.points = new_points
    return OpResult(mesh, sel.copy())


def _smooth_paths(mesh: Mesh, sel: Selection):
    if sel.mode == "polygons":
        sets = _outline_sets(mesh, _valid_faces(mesh, sel.polygons))
        return [(loop, True) for loop, _, _ in sets], {e for _, _, b in sets for e in b}
    return [(v, c) for v, c in _segments(_selected_links(mesh, sel)) if len(v) >= 3], set()


def _relax(ring: np.ndarray, closed: bool, steps: int, keep: bool) -> np.ndarray:
    cur = ring.copy()
    movable = np.ones(len(cur), bool)
    if not closed:
        movable[[0, -1]] = False
    for _ in range(steps):
        prev, nxt = np.roll(cur, 1, axis=0), np.roll(cur, -1, axis=0)
        delta = ((prev + nxt) / 2.0 - cur) * 0.5
        if keep:
            tangent = nxt - prev
            length = np.linalg.norm(tangent, axis=1, keepdims=True)
            tangent = np.where(length > 1e-12, tangent / np.maximum(length, 1e-12), 0.0)
            delta -= (delta * tangent).sum(axis=1, keepdims=True) * tangent
        cur[movable] += delta[movable]
    if keep and steps > 0:
        path = np.vstack([ring, ring[:1]]) if closed else ring
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
        if cum[-1] > 1e-12:
            cur = np.array(_resample(cur, closed, cum[:len(ring)] / cum[-1]))
    return cur


def smooth_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode not in ("points", "edges", "polygons"):
        return _fail(mesh, sel, "Smooth Edges works in points, edges and polygons mode")
    paths, outline = _smooth_paths(mesh, sel)
    if not paths:
        return _fail(mesh, sel, "Smooth Edges: select an edge chain or polygons with an open outline")
    base = mesh.points.copy()
    for verts, closed in paths:
        new = _relax(base[verts], closed, int(p["iterations"]), bool(p["keep_spacing"]))
        for k, v in enumerate(verts):
            if closed or 0 < k < len(verts) - 1:
                mesh.points[v] = new[k]
    out = sel.copy()
    if sel.mode == "polygons" and p["select_outline"]:
        out.edges = outline
    return OpResult(mesh, out)


def _point_groups(mesh: Mesh, sel: Selection) -> list[tuple[list[int], list[int]]]:
    if sel.mode == "polygons":
        faces = _valid_faces(mesh, sel.polygons)
        return [(sorted({i for f in g for i in mesh.polygons[f]}), g) for g in face_groups(mesh, faces)]
    pts = _moving_points(mesh, sel)
    return [(g, []) for g in _islands(mesh, sel, pts)]


def _rotation(axis: np.ndarray, degrees: float) -> np.ndarray:
    a = math.radians(degrees)
    x, y, z = axis
    k = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return np.eye(3) + math.sin(a) * k + (1.0 - math.cos(a)) * (k @ k)


def _hpb(h: float, p: float, b: float) -> np.ndarray:
    return (_rotation(np.array([0.0, 1.0, 0.0]), h) @ _rotation(np.array([1.0, 0.0, 0.0]), p)
            @ _rotation(np.array([0.0, 0.0, 1.0]), b))


def randomize(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    groups = _point_groups(mesh, sel)
    if not groups:
        return _fail(mesh, sel, "Randomize: nothing selected")
    rng = random.Random(int(p["seed"]))
    move = [abs(float(v)) for v in p["move"]]
    scale = [abs(float(v)) for v in p["scale"]]
    rotate = [abs(float(v)) for v in p["rotate"]]
    base = mesh.points.copy()
    for pts, _ in groups:
        center = base[pts].mean(axis=0)
        factors = np.array([max(0.0, 1.0 + rng.uniform(-s, s) / 100.0) for s in scale])
        rot = _hpb(*(rng.uniform(-r, r) for r in rotate))
        for i in pts:
            offset = np.array([rng.uniform(-m, m) for m in move])
            mesh.points[i] = center + rot @ ((base[i] - center) * factors) + offset
    return OpResult(mesh, sel.copy())


def normal_move(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode != "polygons":
        return _fail(mesh, sel, "Normal Move works in polygons mode")
    faces = _valid_faces(mesh, sel.polygons)
    if not faces:
        return _fail(mesh, sel, "Normal Move: no polygons selected")
    value = float(p["move"])
    for i, d in point_normals_for_faces(mesh, faces).items():
        mesh.points[i] = mesh.points[i] + d * value
    return OpResult(mesh, sel.copy())


def _normal_frame_op(mesh: Mesh, sel: Selection, name: str, transform) -> OpResult:
    mesh = clone(mesh)
    if sel.mode != "polygons":
        return _fail(mesh, sel, f"{name} works in polygons mode")
    groups = _point_groups(mesh, sel)
    if not groups:
        return _fail(mesh, sel, f"{name}: no polygons selected")
    normals = face_normals(mesh)
    base = mesh.points.copy()
    for pts, faces in groups:
        center = base[pts].mean(axis=0)
        normal = _unit(normals[faces].sum(axis=0))
        for i in pts:
            mesh.points[i] = center + transform(base[i] - center, normal)
    return OpResult(mesh, sel.copy())


def normal_scale(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    factor = 1.0 + float(p["scale"]) / 100.0

    def scaled(d: np.ndarray, n: np.ndarray) -> np.ndarray:
        if not n.any():
            return d * factor
        along = float(d @ n) * n
        return along + (d - along) * factor

    return _normal_frame_op(mesh, sel, "Normal Scale", scaled)


def normal_rotate(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    angle = float(p["rotate"])

    def rotated(d: np.ndarray, n: np.ndarray) -> np.ndarray:
        return _rotation(n, angle) @ d if n.any() else d

    return _normal_frame_op(mesh, sel, "Normal Rotate", rotated)


_ALL = ("points", "edges", "polygons")
_BIG = 1e6

register(ToolSpec(
    id="slide",
    name="Slide",
    apply=slide,
    modes=("points", "edges"),
    params=(
        Param("offset", "Offset", "distance", 0.0, -_BIG, _BIG, 1.0, "cm"),
        Param("offset_percent", "Offset", "percent", 0.0, -1000.0, 1000.0, 1.0, "%"),
        Param("shift", "Shift", "distance", 0.0, -_BIG, _BIG, 1.0, "cm"),
        Param("offset_mode", "Offset Mode", "choice", "Fixed Distance", choices=("Fixed Distance", "Proportional")),
        Param("limit", "Limit", "bool", True),
        Param("preserve_curvature", "Preserve Curvature", "bool", False),
        Param("clone", "Clone", "bool", False),
        Param("edge", "Edge", "runtime", None),
        Param("edge_position", "Edge Position", "runtime", None),
    ),
    interactive=True,
    drag_param="offset",
    drag_kind="distance",
    section="TRANSFORM",
    shortcut="M~O",
    description="Slides the selected edges or points along their neighbouring edges.",
    extra={
        "pick": "edge",
        "edge_offset_param": "edge_position",
        "shift_drag_param": "shift",
        "ctrl_toggles": "clone",
        "offset_param_by_mode": {"Fixed Distance": "offset", "Proportional": "offset_percent"},
        "runtime": {
            "edge": "(a, b) point indices of the hovered edge next to the selection; the slide goes toward it",
            "edge_position": "0..100 position of the cursor along the hovered edge measured from edge[0]; "
                             "when set it replaces Offset, so reset it to None when Offset is typed",
        },
    },
))

register(ToolSpec(
    id="equal_spacing",
    name="Equal Spacing",
    apply=equal_spacing,
    modes=("edges",),
    params=(
        Param("strength", "Strength", "percent", 0.0, 0.0, 100.0, 1.0, "%"),
        Param("linear", "Linear", "bool", False),
    ),
    interactive=True,
    drag_param="strength",
    drag_kind="percent",
    section="TRANSFORM",
    description="Spaces the selected edge loops evenly between their neighbouring loops.",
))

register(ToolSpec(
    id="straighten_edges",
    name="Straighten Edges",
    apply=straighten_edges,
    modes=("points", "edges"),
    params=(
        Param("strength", "Strength", "percent", 0.0, 0.0, 100.0, 1.0, "%"),
        Param("equal_spacing", "Equal Spacing", "bool", False),
    ),
    interactive=True,
    drag_param="strength",
    drag_kind="percent",
    section="TRANSFORM",
    description="Places the points of each open edge chain on the line between its end points.",
))

register(ToolSpec(
    id="fit_circle",
    name="Fit Circle",
    apply=fit_circle,
    modes=_ALL,
    params=(
        Param("strength", "Strength", "percent", 100.0, 0.0, 100.0, 1.0, "%"),
        Param("roundness", "Roundness", "percent", 100.0, 0.0, 100.0, 1.0, "%"),
        Param("exact_radius", "Exact Radius", "bool", False),
        Param("scale", "Scale", "percent", 100.0, 0.0, 100000.0, 1.0, "%"),
        Param("radius", "Radius", "distance", 100.0, 0.0, _BIG, 1.0, "cm"),
        Param("angle", "Angle", "angle", 0.0, -_BIG, _BIG, 1.0, "°"),
        Param("adjust_inner_points", "Adjust Inner Points", "bool", True),
        Param("project_to_surface", "Project To Surface", "bool", False),
        Param("equal_spacing", "Equal Spacing", "bool", False),
        Param("select_outline", "Select Outline", "bool", True),
    ),
    interactive=True,
    drag_param="scale",
    drag_kind="percent",
    section="TRANSFORM",
    description="Reshapes a closed loop or the outline of a polygon region into a circle.",
    extra={"drag_param_when": {"exact_radius": "radius"}, "shift_drag_param": "angle"},
))

register(ToolSpec(
    id="flatten",
    name="Flatten",
    apply=flatten,
    modes=_ALL,
    params=(
        Param("strength", "Strength", "percent", 0.0, 0.0, 100.0, 1.0, "%"),
        Param("mode", "Mode", "choice", "Best Fit",
              choices=("Best Fit", "View", "Normal", "Modeling Axis", "World Axis")),
        Param("axis", "Axis", "choice", "Y", choices=("X", "Y", "Z")),
        Param("use_axis_position", "Use Axis Position", "bool", True),
        Param("position", "Position", "percent", 0.0, -_BIG, _BIG, 1.0, "%"),
        Param("individual_islands", "Individual Islands", "bool", False),
        Param("outline_only", "Outline Only", "bool", False),
        Param("view_direction", "View Direction", "runtime", None),
        Param("modeling_axis", "Modeling Axis", "runtime", None),
    ),
    interactive=True,
    drag_param="strength",
    drag_kind="percent",
    section="TRANSFORM",
    description="Projects the selection onto a common plane.",
    extra={
        "shift_drag_param": "position",
        "runtime": {
            "view_direction": "camera view direction in object space, used by Mode View",
            "modeling_axis": "(origin, x, y, z) rows of the modeling axis in object space, used by Mode Modeling Axis",
        },
    },
))

register(ToolSpec(
    id="iron",
    name="Iron",
    apply=iron,
    modes=_ALL,
    params=(
        Param("angle", "Angle", "angle", 90.0, 0.0, 180.0, 1.0, "°"),
        Param("strength", "Strength", "percent", 0.0, -100.0, 100.0, 1.0, "%"),
        Param("preserve_boundaries", "Preserve Boundaries", "bool", True),
    ),
    interactive=True,
    drag_param="strength",
    drag_kind="percent",
    section="TRANSFORM",
    shortcut="M~G",
    description="Irons out bumps by pulling points onto the plane of their neighbours.",
    extra={"shift_drag_param": "angle"},
))

register(ToolSpec(
    id="smooth_edges",
    name="Smooth Edges",
    apply=smooth_edges,
    modes=_ALL,
    params=(
        Param("iterations", "Iterations", "int", 0, 0, 10000, 1),
        Param("keep_spacing", "Keep Spacing", "bool", True),
        Param("select_outline", "Select Outline", "bool", True),
    ),
    interactive=True,
    drag_param="iterations",
    drag_kind="count",
    section="TRANSFORM",
    description="Relaxes selected edge chains or polygon outlines into short, corner-free curves.",
))

register(ToolSpec(
    id="randomize",
    name="Randomize",
    apply=randomize,
    modes=_ALL,
    params=(
        Param("move", "Move", "vector", (10.0, 10.0, 10.0), unit="cm"),
        Param("scale", "Scale", "vector", (0.0, 0.0, 0.0), unit="%"),
        Param("rotate", "Rotate", "vector", (0.0, 0.0, 0.0), unit="°"),
        Param("seed", "Seed", "int", 12345, 0, 2147483647, 1),
    ),
    interactive=False,
    drag_param=None,
    drag_kind="distance",
    section="COMMANDS",
    description="Moves, scales and rotates the selected elements by random amounts.",
))

register(ToolSpec(
    id="normal_move",
    name="Normal Move",
    apply=normal_move,
    modes=("polygons",),
    params=(Param("move", "Move", "distance", 0.0, -_BIG, _BIG, 1.0, "cm"),),
    interactive=True,
    drag_param="move",
    drag_kind="distance",
    section="TRANSFORM",
    shortcut="M~Z",
    description="Moves the selected polygons along their normals.",
))

register(ToolSpec(
    id="normal_scale",
    name="Normal Scale",
    apply=normal_scale,
    modes=("polygons",),
    params=(Param("scale", "Scale", "percent", 0.0, -_BIG, _BIG, 1.0, "%"),),
    interactive=True,
    drag_param="scale",
    drag_kind="percent",
    section="TRANSFORM",
    shortcut="M~#",
    description="Scales the selected polygons perpendicular to their normals.",
))

register(ToolSpec(
    id="normal_rotate",
    name="Normal Rotate",
    apply=normal_rotate,
    modes=("polygons",),
    params=(Param("rotate", "Rotate", "angle", 0.0, -_BIG, _BIG, 1.0, "°"),),
    interactive=True,
    drag_param="rotate",
    drag_kind="angle",
    section="TRANSFORM",
    shortcut="M~,",
    description="Rotates the selected polygons around their normals.",
))
