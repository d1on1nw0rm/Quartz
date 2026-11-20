from __future__ import annotations

import math

import numpy as np

from ..scene import Mesh
from .meshkit import (OpResult, Selection, clean_polygons, clone, compact, directed_edges, edge_faces,
                      edge_groups, edge_key, face_groups, point_faces, selection_points,
                      triangulate_polygon)
from .registry import Param, ToolSpec, register

__all__ = ["weld", "bridge", "stitch_and_sew", "close_polygon_hole", "connect_points_edges", "melt",
           "dissolve", "optimize", "disconnect", "split"]

COMPONENTS = ("points", "edges", "polygons")


def _fail(mesh: Mesh, sel: Selection, message: str) -> OpResult:
    return OpResult(mesh, sel.copy(), False, message)


def _point_set_index(polygons) -> set[tuple[int, ...]]:
    return {tuple(sorted(poly)) for poly in polygons}


def _duplicates(polys, polygons) -> bool:
    known = _point_set_index(polygons)
    for poly in polys:
        key = tuple(sorted(poly))
        if key in known:
            return True
        known.add(key)
    return False


def _used_points(mesh: Mesh) -> set[int]:
    return ({int(i) for poly in mesh.polygons for i in poly}
            | {int(i) for e in mesh.loose_edges for i in e})


def _find(mapping: dict[int, int], i: int) -> int:
    steps = 0
    while i in mapping and mapping[i] != i and steps <= len(mapping):
        i = mapping[i]
        steps += 1
    return i


def _collapse_ring(ring) -> list[int]:
    out: list[int] = []
    for i in ring:
        i = int(i)
        if not out or out[-1] != i:
            out.append(i)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _valid_ring(ring: list[int]) -> bool:
    return len(ring) >= 3 and len(set(ring)) == len(ring)


def _canon(ring) -> tuple[int, ...]:
    ring = list(ring)
    k = ring.index(min(ring))
    return tuple(ring[k:] + ring[:k])


def _directed_set(polygons) -> set[tuple[int, int]]:
    return {e for poly in polygons for e in directed_edges(poly)}


def _valid_points(mesh: Mesh, points) -> list[int]:
    return sorted({int(i) for i in points if 0 <= int(i) < len(mesh.points)})


def _valid_edges(mesh: Mesh, edges) -> list[tuple[int, int]]:
    known = set(mesh.edges)
    return sorted({edge_key(*e) for e in edges if edge_key(*e) in known})


def _valid_faces(mesh: Mesh, faces) -> list[int]:
    return sorted({int(f) for f in faces if 0 <= int(f) < len(mesh.polygons)})


def _finish(mesh: Mesh, polygons, before_used: set[int], loose=None) -> tuple[Mesh, dict[int, int]]:
    n = len(mesh.points)
    rebuilt = Mesh(mesh.points.copy(), polygons, mesh.loose_edges if loose is None else loose)
    keep = [i for i in range(n) if i not in before_used]
    return compact(rebuilt, keep)


def _merge_points(mesh: Mesh, mapping: dict[int, int], positions=None, clean: bool = True,
                  orphans: str = "keep_old") -> tuple[Mesh, dict[int, int]]:
    n = len(mesh.points)
    before = _used_points(mesh)
    pts = mesh.points.copy()
    for i, pos in (positions or {}).items():
        pts[int(i)] = np.asarray(pos, float)
    roots = [_find(mapping, i) for i in range(n)]
    rings = [[roots[i] for i in poly] for poly in mesh.polygons]
    if clean:
        polys = clean_polygons(rings)
    else:
        polys = [tuple(r) for r in map(_collapse_ring, rings) if _valid_ring(r)]
    loose = [(roots[a], roots[b]) for a, b in mesh.loose_edges if roots[a] != roots[b]]
    merged = Mesh(pts, polys, loose)
    keep = [i for i in range(n) if roots[i] == i
            and (orphans == "keep_all" or (orphans == "keep_old" and i not in before))]
    out, remap = compact(merged, keep)
    full = {i: remap[roots[i]] for i in range(n) if roots[i] in remap}
    return out, full


def _map_selection(old: Mesh, new: Mesh, sel: Selection, remap: dict[int, int]) -> Selection:
    known = set(new.edges)
    points = {remap[i] for i in sel.points if i in remap}
    edges = set()
    for a, b in sel.edges:
        if a in remap and b in remap and remap[a] != remap[b]:
            key = edge_key(remap[a], remap[b])
            if key in known:
                edges.add(key)
    index = {_canon(p): k for k, p in enumerate(new.polygons)}
    polys = set()
    for f in sel.polygons:
        if not 0 <= f < len(old.polygons):
            continue
        ring = _collapse_ring(remap.get(i, -1) for i in old.polygons[f])
        if -1 in ring or not _valid_ring(ring):
            continue
        k = index.get(_canon(ring))
        if k is not None:
            polys.add(k)
    return Selection(sel.mode, points, edges, polys)


def _without_faces(polygons, drop: set[int]) -> tuple[list[tuple[int, ...]], dict[int, int]]:
    kept: list[tuple[int, ...]] = []
    index: dict[int, int] = {}
    for k, poly in enumerate(polygons):
        if k in drop:
            continue
        index[k] = len(kept)
        kept.append(tuple(poly))
    return kept, index


def _flat(points: np.ndarray, poly) -> bool:
    ring = points[list(poly)]
    ring = ring - ring.mean(axis=0)
    nxt = np.roll(ring, -1, axis=0)
    twice = float(np.linalg.norm(np.cross(ring, nxt).sum(axis=0)))
    span = float(np.linalg.norm(nxt - ring, axis=1).max())
    return twice <= 1e-9 * span * span


def _prune(points: np.ndarray, polys: list[tuple[int, ...]], fresh: list[bool]
           ) -> tuple[list[tuple[int, ...]], dict[int, int]]:
    count: dict[tuple[int, ...], int] = {}
    for poly in polys:
        key = tuple(sorted(poly))
        count[key] = count.get(key, 0) + 1
    out: list[tuple[int, ...]] = []
    index: dict[int, int] = {}
    for k, poly in enumerate(polys):
        if fresh[k] and (count[tuple(sorted(poly))] > 1 or _flat(points, poly)):
            continue
        index[k] = len(out)
        out.append(poly)
    return out, index


def _closed(polygons) -> bool:
    count: dict[tuple[int, int], int] = {}
    for poly in polygons:
        for a, b in directed_edges(poly):
            key = edge_key(a, b)
            count[key] = count.get(key, 0) + 1
    return bool(count) and all(v == 2 for v in count.values())


def _refusal(before, polys, name: str) -> str | None:
    if not polys:
        return f"{name}: the result would only contain degenerate or duplicate polygons"
    if _closed(before) and not _closed(polys):
        return f"{name}: the result would be an open or fragmented mesh, so nothing was changed"
    return None


def _region_edges(polygons, faces) -> list[tuple[int, int]]:
    directed = [e for f in faces for e in directed_edges(polygons[f])]
    present = set(directed)
    return [(u, v) for u, v in directed if (v, u) not in present]


def _directed_loops(directed) -> list[list[int]] | None:
    nxt: dict[int, int] = {}
    order: list[int] = []
    for u, v in directed:
        if u in nxt:
            return None
        nxt[u] = v
        order.append(u)
    loops: list[list[int]] = []
    seen: set[int] = set()
    for start in order:
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        cur = nxt[start]
        while cur != start:
            if cur in seen or cur not in nxt:
                return None
            loop.append(cur)
            seen.add(cur)
            cur = nxt[cur]
        loops.append(loop)
    return loops


def _order_edges(edges) -> tuple[list[int] | None, bool]:
    adj: dict[int, list[int]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if not adj or any(len(v) > 2 for v in adj.values()):
        return None, False
    ends = sorted(p for p, v in adj.items() if len(v) == 1)
    if len(ends) not in (0, 2):
        return None, False
    closed = not ends
    chain = [ends[0] if ends else min(adj)]
    seen = {chain[0]}
    while True:
        options = [q for q in adj[chain[-1]] if q not in seen]
        if not options:
            break
        chain.append(min(options))
        seen.add(chain[-1])
    if len(chain) != len(adj) or (closed and len(chain) < 3):
        return None, False
    return chain, closed


def _strip(a: list[int], b: list[int], closed: bool) -> list[tuple[int, ...]]:
    na, nb = len(a), len(b)
    sa, sb = (na, nb) if closed else (na - 1, nb - 1)
    i = j = 0
    polys: list[tuple[int, ...]] = []
    while i < sa or j < sb:
        ta = (i + 1) / sa if i < sa else math.inf
        tb = (j + 1) / sb if j < sb else math.inf
        if abs(ta - tb) < 1e-9:
            ring = [a[i % na], a[(i + 1) % na], b[(j + 1) % nb], b[j % nb]]
            i += 1
            j += 1
        elif ta < tb:
            ring = [a[i % na], a[(i + 1) % na], b[j % nb]]
            i += 1
        else:
            ring = [a[i % na], b[(j + 1) % nb], b[j % nb]]
            j += 1
        ring = _collapse_ring(ring)
        if _valid_ring(ring):
            polys.append(tuple(ring))
    return polys


def _conflicts(polys, existing: set[tuple[int, int]]) -> int:
    used = set(existing)
    bad = 0
    for poly in polys:
        for e in directed_edges(poly):
            if e in used:
                bad += 1
            used.add(e)
    return bad


def _orient(polys, existing: set[tuple[int, int]]) -> list[tuple[int, ...]]:
    flipped = [tuple(reversed(p)) for p in polys]
    return flipped if _conflicts(flipped, existing) < _conflicts(polys, existing) else list(polys)


def _loop_cost(pts: np.ndarray, a: list[int], b: list[int]) -> float:
    n, m = len(a), len(b)
    idx = [int(round(i * m / n)) % m for i in range(n)]
    return float(np.linalg.norm(pts[a] - pts[[b[k] for k in idx]], axis=1).sum())


def _align_loop(pts: np.ndarray, a: list[int], b: list[int], directions=(1, -1)) -> list[int]:
    m = len(b)
    best: tuple[float, list[int]] | None = None
    for d in directions:
        for s in range(m):
            cand = [b[(s + d * k) % m] for k in range(m)]
            cost = _loop_cost(pts, a, cand)
            if best is None or cost < best[0] - 1e-9:
                best = (cost, cand)
    return best[1]


def _ends_cost(pts: np.ndarray, a: list[int], b: list[int]) -> float:
    return float(np.linalg.norm(pts[a[0]] - pts[b[0]]) + np.linalg.norm(pts[a[-1]] - pts[b[-1]]))


def _align_chain(pts: np.ndarray, a: list[int], b: list[int]) -> list[int]:
    flipped = list(reversed(b))
    return list(b) if _ends_cost(pts, a, b) <= _ends_cost(pts, a, flipped) + 1e-9 else flipped


def _bridge_chain(pts: np.ndarray, a: list[int], b: list[int],
                  existing: set[tuple[int, int]]) -> list[tuple[int, ...]]:
    options = []
    for cand in (list(b), list(reversed(b))):
        polys = _orient(_strip(a, cand, False), existing)
        options.append((_ends_cost(pts, a, cand), _conflicts(polys, existing), polys))
    (c0, k0, p0), (c1, k1, p1) = options
    tie = abs(c0 - c1) <= 1e-6 * max(1.0, c0, c1)
    if tie:
        return p0 if k0 <= k1 else p1
    return p0 if c0 < c1 else p1


def _loop_sense(loop: list[int], existing: set[tuple[int, int]]) -> int:
    score = 0
    for u, v in zip(loop, loop[1:] + loop[:1]):
        score += ((v, u) in existing) - ((u, v) in existing)
    return (score > 0) - (score < 0)


def _bridge_polys(mesh: Mesh, a: list[int], b: list[int], closed: bool,
                  existing: set[tuple[int, int]], sense_from: set[tuple[int, int]] | None = None
                  ) -> list[tuple[int, ...]]:
    if not closed:
        return _bridge_chain(mesh.points, a, b, existing)
    ref = existing if sense_from is None else sense_from
    sa, sb = _loop_sense(a, ref), _loop_sense(b, ref)
    if sa == 0 or sb == 0:
        return _orient(_strip(a, _align_loop(mesh.points, a, b), True), existing)
    a = a if sa > 0 else list(reversed(a))
    b = b if sb < 0 else list(reversed(b))
    return _strip(a, _align_loop(mesh.points, a, b, directions=(1,)), True)


def _edge_chains(edges) -> list[tuple[list[int], bool]] | None:
    out = []
    for group in edge_groups(edges):
        chain, closed = _order_edges(group)
        if chain is None:
            return None
        out.append((chain, closed))
    return out


def _runtime_edge(mesh: Mesh, value) -> list[int] | None:
    if value is None:
        return None
    try:
        a, b = (int(value[0]), int(value[1]))
    except (TypeError, ValueError, IndexError):
        return None
    if a == b or edge_key(a, b) not in set(mesh.edges):
        return None
    return [a, b]


def _runtime_point(mesh: Mesh, value) -> int | None:
    if value is None:
        return None
    try:
        i = int(value)
    except (TypeError, ValueError):
        return None
    return i if 0 <= i < len(mesh.points) else None


def _planar_order(pts: np.ndarray, ids: list[int]) -> list[int]:
    ring = pts[ids]
    center = ring.mean(axis=0)
    _, _, vt = np.linalg.svd(ring - center)
    u, v = vt[0], vt[1]
    angles = [math.atan2(float((p - center) @ v), float((p - center) @ u)) for p in ring]
    return [ids[k] for k in np.argsort(angles)]


def weld(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode not in COMPONENTS:
        return _fail(mesh, sel, "Weld needs points, edges or polygons mode")
    pts = [i for i in selection_points(mesh, sel) if 0 <= i < len(mesh.points)]
    target = _runtime_point(mesh, p.get("target"))
    members = sorted(set(pts) | ({target} if target is not None else set()))
    if len(members) < 2:
        return _fail(mesh, sel, "Weld: select at least two points (or a target point)")
    if p.get("position") is not None:
        position = np.asarray(p["position"], float).reshape(3)
    elif target is not None:
        position = mesh.points[target].copy()
    else:
        position = mesh.points[members].mean(axis=0)
    root = target if target is not None else members[0]
    mapping = {i: root for i in members}
    out, remap = _merge_points(mesh, mapping, {root: position})
    if sel.mode == "points" and root in remap:
        return OpResult(out, Selection("points", points={remap[root]}))
    return OpResult(out, Selection(sel.mode))


def _bridge_faces(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    faces = _valid_faces(mesh, sel.polygons)
    groups = face_groups(mesh, faces)
    if len(groups) != 2:
        return _fail(mesh, sel, "Bridge: select two separate polygons or polygon groups")
    loops = []
    for group in groups:
        found = _directed_loops(_region_edges(mesh.polygons, group))
        if not found or len(found) != 1:
            return _fail(mesh, sel, "Bridge: each polygon group needs exactly one border")
        loops.append(found[0])
    open_mesh, _ = _without_faces(mesh.polygons, set(faces))
    kept = open_mesh if p["delete_original"] else list(mesh.polygons)
    polys = _bridge_polys(mesh, loops[0], loops[1], True, _directed_set(kept), _directed_set(open_mesh))
    if _duplicates(polys, open_mesh):
        return _fail(mesh, sel, "Bridge: the new polygons would lie on existing polygons")
    start = len(kept)
    before = _used_points(mesh)
    out, remap = _finish(mesh, kept + polys, before)
    new_faces = set(range(start, start + len(polys)))
    return OpResult(out, Selection("polygons", polygons=new_faces))


def _bridge_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    chains = _edge_chains(_valid_edges(mesh, sel.edges))
    if chains is None or len(chains) != 2:
        return _fail(mesh, sel, "Bridge: select two edge chains or two border loops")
    (a, ca), (b, cb) = chains
    if ca != cb:
        return _fail(mesh, sel, "Bridge: cannot bridge an open chain with a closed loop")
    polys = _bridge_polys(mesh, a, b, ca, _directed_set(mesh.polygons))
    if _duplicates(polys, mesh.polygons):
        return _fail(mesh, sel, "Bridge: these edges are already connected by a polygon")
    mesh.polygons.extend(polys)
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("edges", edges=set(_valid_edges(mesh, sel.edges))))


def _bridge_points(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    pts = _valid_points(mesh, sel.points)
    if len(pts) not in (3, 4):
        return _fail(mesh, sel, "Bridge: select three or four points")
    existing = _directed_set(mesh.polygons)
    known = set(mesh.edges)
    polys = None
    if len(pts) == 4:
        x = pts[0]
        for y in pts[1:]:
            z, w = [q for q in pts[1:] if q != y]
            if edge_key(x, y) in known and edge_key(z, w) in known:
                polys = _bridge_polys(mesh, [x, y], [z, w], False, existing)
                break
    if polys is None:
        polys = _orient([tuple(_planar_order(mesh.points, pts))], existing)
    if _duplicates(polys, mesh.polygons):
        return _fail(mesh, sel, "Bridge: these points already form a polygon")
    mesh.polygons.extend(polys)
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("points", points=set(pts)))


def bridge(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    ea, eb = _runtime_edge(mesh, p.get("edge_a")), _runtime_edge(mesh, p.get("edge_b"))
    if ea is not None and eb is not None:
        polys = _bridge_polys(mesh, ea, eb, False, _directed_set(mesh.polygons))
        if not polys or _duplicates(polys, mesh.polygons):
            return _fail(mesh, sel, "Bridge: these edges are already connected by a polygon")
        start = len(mesh.polygons)
        mesh.polygons.extend(polys)
        mesh._rebuild_edges()
        if sel.mode == "polygons":
            return OpResult(mesh, Selection("polygons", polygons=set(range(start, len(mesh.polygons)))))
        return OpResult(mesh, sel.copy())
    if sel.mode == "polygons":
        return _bridge_faces(mesh, sel, p)
    if sel.mode == "edges":
        return _bridge_edges(mesh, sel, p)
    if sel.mode == "points":
        return _bridge_points(mesh, sel, p)
    return _fail(mesh, sel, "Bridge needs points, edges or polygons mode")


def _chain_direction(mesh: Mesh, chain: list[int], closed: bool) -> int:
    ef = edge_faces(mesh)
    pairs = list(zip(chain, chain[1:] + (chain[:1] if closed else [])))
    vote = 0
    for a, b in pairs:
        owners = ef.get(edge_key(a, b), [])
        if len(owners) != 1:
            continue
        vote += 1 if (a, b) in directed_edges(mesh.polygons[owners[0]]) else -1
    return (vote > 0) - (vote < 0)


def _sew_pairs(mesh: Mesh, a: list[int], b: list[int], closed: bool) -> tuple[list[int], list[int]]:
    da, db = _chain_direction(mesh, a, closed), _chain_direction(mesh, b, closed)
    if da == 0 or db == 0:
        if closed:
            return a, _align_loop(mesh.points, a, b)
        return a, _align_chain(mesh.points, a, b)
    if da > 0:
        a = list(reversed(a))
    if db < 0:
        b = list(reversed(b))
    if closed:
        b = _align_loop(mesh.points, a, b, directions=(1,))
    return a, b


def _open_chain(mesh: Mesh, chain: list[int], closed: bool) -> bool:
    ef = edge_faces(mesh)
    pairs = zip(chain, chain[1:] + (chain[:1] if closed else []))
    return all(len(ef.get(edge_key(x, y), [])) <= 1 for x, y in pairs)


def _sew_chains(mesh: Mesh, sel: Selection, p: dict):
    ea, eb = _runtime_edge(mesh, p.get("edge_a")), _runtime_edge(mesh, p.get("edge_b"))
    if ea is not None and eb is not None:
        return [(ea, False), (eb, False)]
    if sel.mode == "edges":
        edges = _valid_edges(mesh, sel.edges)
    elif sel.mode == "points":
        chosen = set(sel.points)
        ef = edge_faces(mesh)
        edges = [e for e, owners in ef.items() if len(owners) == 1 and e[0] in chosen and e[1] in chosen]
    else:
        return None
    chains = _edge_chains(edges)
    if chains is not None and len(chains) == 1:
        return _split_slit(*chains[0])
    return chains if chains is not None and len(chains) == 2 else None


def _split_slit(chain: list[int], closed: bool):
    if closed or len(chain) < 3 or len(chain) % 2 == 0:
        return None
    mid = len(chain) // 2
    return [(list(reversed(chain[:mid + 1])), False), (chain[mid:], False)]


def stitch_and_sew(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode not in COMPONENTS:
        return _fail(mesh, sel, "Stitch and Sew needs points, edges or polygons mode")
    chains = _sew_chains(mesh, sel, p)
    if chains is None:
        return _fail(mesh, sel, "Stitch and Sew: pick two edges or select two border edge chains")
    (a, ca), (b, cb) = chains
    if ca != cb or len(a) != len(b):
        return _fail(mesh, sel, "Stitch and Sew: both sides need the same number of points")
    if not _open_chain(mesh, a, ca) or not _open_chain(mesh, b, cb):
        return _fail(mesh, sel, "Stitch and Sew: both sides must be border edges")
    a, b = _sew_pairs(mesh, a, b, ca)
    if p["create_polygons"]:
        polys = _orient(_strip(a, b, ca), _directed_set(mesh.polygons))
        if not polys or _duplicates(polys, mesh.polygons):
            return _fail(mesh, sel, "Stitch and Sew: these edges are already connected by a polygon")
        mesh.polygons.extend(polys)
        mesh._rebuild_edges()
        return OpResult(mesh, sel.copy())
    mode = p["weld_to"]
    mapping = {}
    positions = {}
    for x, y in zip(a, b):
        if x == y:
            continue
        mapping[y] = x
        if mode == "Center":
            positions[x] = (mesh.points[x] + mesh.points[y]) * 0.5
        elif mode == "Second Edge":
            positions[x] = mesh.points[y].copy()
    out, remap = _merge_points(mesh, mapping, positions)
    pairs = list(zip(a, a[1:] + (a[:1] if ca else [])))
    known = set(out.edges)
    edges = {edge_key(remap[x], remap[y]) for x, y in pairs if x in remap and y in remap}
    points = {remap[x] for x in a if x in remap}
    return OpResult(out, Selection(sel.mode, points=points if sel.mode == "points" else set(),
                                   edges={e for e in edges if e in known} if sel.mode == "edges" else set()))


def _hole_loops(mesh: Mesh, sel: Selection, p: dict) -> list[list[int]]:
    loops = _border_loops(mesh)
    edge = _runtime_edge(mesh, p.get("edge"))
    if edge is not None:
        key = edge_key(*edge)
        found = [lp for lp in loops if key in {edge_key(x, y) for x, y in zip(lp, lp[1:] + lp[:1])}]
    else:
        touched = set(selection_points(mesh, sel)) if sel.mode in COMPONENTS else set()
        found = [lp for lp in loops if touched & set(lp)]
    known = _point_set_index(mesh.polygons)
    return [lp for lp in found if tuple(sorted(lp)) not in known]


def _split_pinches(loop: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    stack: list[int] = []
    where: dict[int, int] = {}
    for i in loop:
        if i in where:
            k = where[i]
            out.append(stack[k:])
            for j in stack[k + 1:]:
                where.pop(j, None)
            del stack[k + 1:]
            continue
        where[i] = len(stack)
        stack.append(i)
    out.append(stack)
    return [lp for lp in out if len(lp) >= 3]


def _border_loops(mesh: Mesh) -> list[list[int]]:
    ef = edge_faces(mesh)
    free = [(b, a) for poly in mesh.polygons for a, b in directed_edges(poly)
            if len(ef[edge_key(a, b)]) == 1]
    nxt: dict[int, list[int]] = {}
    for u, v in free:
        nxt.setdefault(u, []).append(v)
    used: set[tuple[int, int]] = set()
    loops = []
    for u, v in free:
        if (u, v) in used:
            continue
        loop = [u]
        used.add((u, v))
        cur = v
        while cur != u:
            options = [w for w in nxt.get(cur, []) if (cur, w) not in used]
            if not options:
                loop = []
                break
            loop.append(cur)
            used.add((cur, options[0]))
            cur = options[0]
        loops.extend(_split_pinches(loop))
    return loops


def close_polygon_hole(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    loops = _hole_loops(mesh, sel, p)
    if not loops:
        return _fail(mesh, sel, "Close Polygon Hole: point at a hole border or select elements on it")
    start = len(mesh.polygons)
    for loop in loops:
        mesh.polygons.append(tuple(loop))
        if not p["create_ngons"] and len(loop) > 3:
            k = len(mesh.polygons) - 1
            tris = triangulate_polygon(mesh, k)
            mesh.polygons[k:] = [tuple(t) for t in tris]
    mesh._rebuild_edges()
    if sel.mode == "polygons":
        return OpResult(mesh, Selection("polygons", polygons=set(range(start, len(mesh.polygons)))))
    return OpResult(mesh, sel.copy())


def _cut_ring(ring: list[int], marks: list[int]) -> list[tuple[int, ...]]:
    n = len(ring)
    pieces = []
    for s, t in zip(marks, marks[1:] + marks[:1]):
        span = (t - s) % n or n
        if span >= 2:
            pieces.append(tuple(ring[(s + k) % n] for k in range(span + 1)))
    if len(marks) >= 3:
        pieces.append(tuple(ring[m] for m in marks))
    return pieces


def _connect_points(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    chosen = set(_valid_points(mesh, sel.points))
    if len(chosen) < 2:
        return _fail(mesh, sel, "Connect Points/Edges: select at least two points of a polygon")
    polys = []
    changed = False
    for poly in mesh.polygons:
        ring = list(poly)
        marks = [k for k, i in enumerate(ring) if i in chosen]
        pieces = _cut_ring(ring, marks) if len(marks) >= 2 else []
        if len(pieces) > 1:
            polys.extend(pieces)
            changed = True
        else:
            polys.append(tuple(poly))
    if not changed:
        return _fail(mesh, sel, "Connect Points/Edges: the selected points do not share a polygon")
    mesh.polygons = polys
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("points", points=chosen))


def _connect_face(ring: list[int], mids: dict, mesh: Mesh, preserve: bool, new_edges: set):
    out_ring: list[int] = []
    marks: list[int] = []
    for a, b in zip(ring, ring[1:] + ring[:1]):
        out_ring.append(a)
        m = mids.get(edge_key(a, b))
        if m is not None:
            marks.append(len(out_ring))
            out_ring.append(m)
    if not marks:
        return [tuple(ring)]
    if len(marks) == 1:
        if preserve:
            return [tuple(out_ring)]
        k = marks[0]
        fan = out_ring[k:] + out_ring[:k]
        return [(fan[0], fan[t], fan[t + 1]) for t in range(1, len(fan) - 1)]
    if len(marks) == 2:
        new_edges.add(edge_key(out_ring[marks[0]], out_ring[marks[1]]))
        return _cut_ring(out_ring, marks)
    center = mesh.add_point(mesh.points[list(ring)].mean(axis=0))
    pieces = []
    n = len(out_ring)
    for s, t in zip(marks, marks[1:] + marks[:1]):
        span = (t - s) % n or n
        pieces.append(tuple(out_ring[(s + k) % n] for k in range(span + 1)) + (center,))
        new_edges.add(edge_key(out_ring[s], center))
    return pieces


def _connect_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    ef = edge_faces(mesh)
    edges = [e for e in _valid_edges(mesh, sel.edges) if ef.get(e)]
    if not edges:
        return _fail(mesh, sel, "Connect Points/Edges: select edges of polygons")
    mids = {e: mesh.add_point((mesh.points[e[0]] + mesh.points[e[1]]) * 0.5) for e in edges}
    new_edges: set = set()
    polys = []
    for poly in list(mesh.polygons):
        polys.extend(_connect_face(list(poly), mids, mesh, bool(p["preserve_ngons"]), new_edges))
    mesh.polygons = polys
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("edges", edges=new_edges))


def connect_points_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode == "points":
        return _connect_points(mesh, sel, p)
    if sel.mode == "edges":
        return _connect_edges(mesh, sel, p)
    return _fail(mesh, sel, "Connect Points/Edges needs points or edges mode")


def _merge_groups(polygons, groups) -> tuple[list[tuple[int, ...]], list[int], int]:
    drop: set[int] = set()
    merged: list[tuple[int, ...]] = []
    skipped = 0
    for group in groups:
        if len(group) < 2:
            continue
        loops = _directed_loops(_region_edges(polygons, group))
        if not loops or len(loops) != 1 or len(loops[0]) < 3:
            skipped += 1
            continue
        drop |= set(group)
        merged.append(tuple(loops[0]))
    kept, _ = _without_faces(polygons, drop)
    start = len(kept)
    return kept + merged, list(range(start, start + len(merged))), skipped


def _face_union(mesh: Mesh, edges) -> list[list[int]]:
    ef = edge_faces(mesh)
    parent = list(range(len(mesh.polygons)))

    def root(f: int) -> int:
        while parent[f] != f:
            parent[f] = parent[parent[f]]
            f = parent[f]
        return f

    touched: set[int] = set()
    for e in edges:
        owners = ef.get(e, [])
        if len(owners) == 2 and owners[0] != owners[1]:
            parent[root(owners[0])] = root(owners[1])
            touched.update(owners)
    groups: dict[int, list[int]] = {}
    for f in sorted(touched):
        groups.setdefault(root(f), []).append(f)
    return list(groups.values())


def _melt_faces(mesh: Mesh, faces) -> tuple[list[tuple[int, ...]], list[int], int]:
    return _merge_groups(mesh.polygons, face_groups(mesh, faces))


def _melt_points(polygons, points) -> tuple[list[tuple[int, ...]], list[bool], int]:
    polys = [tuple(p) for p in polygons]
    fresh = [False] * len(polys)
    done = 0
    for pt in points:
        fan = [k for k, poly in enumerate(polys) if pt in poly]
        if not fan:
            continue
        loops = _directed_loops(_region_edges(polys, fan))
        if not loops or len(loops) != 1:
            continue
        ring = [i for i in loops[0] if i != pt]
        if not _valid_ring(ring):
            continue
        drop = set(fan)
        keep = [k for k in range(len(polys)) if k not in drop]
        polys = [polys[k] for k in keep] + [tuple(ring)]
        fresh = [fresh[k] for k in keep] + [True]
        done += 1
    return polys, fresh, done


def _valence(polygons) -> dict[int, int]:
    out: dict[int, int] = {}
    seen: set[tuple[int, int]] = set()
    for poly in polygons:
        for a, b in directed_edges(poly):
            key = edge_key(a, b)
            if key in seen:
                continue
            seen.add(key)
            out[a] = out.get(a, 0) + 1
            out[b] = out.get(b, 0) + 1
    return out


def _drop_midpoints(polygons, candidates, before: dict[int, int]) -> list[tuple[int, ...]]:
    polys = [tuple(p) for p in polygons]
    for pt in sorted(candidates):
        after = _valence(polys)
        if after.get(pt) != 2 or before.get(pt, 0) <= 2:
            continue
        trimmed = [tuple(i for i in poly if i != pt) if pt in poly else poly for poly in polys]
        if all(len(poly) >= 3 for poly in trimmed):
            polys = trimmed
    return polys


def _merge_command(mesh: Mesh, sel: Selection, name: str, cleanup: bool) -> OpResult:
    mesh = clone(mesh)
    before_used = _used_points(mesh)
    before_valence = _valence(mesh.polygons)
    if sel.mode == "polygons":
        faces = _valid_faces(mesh, sel.polygons)
        if not faces:
            return _fail(mesh, sel, f"{name}: no polygons selected")
        polys, new_faces, skipped = _melt_faces(mesh, faces)
        if not new_faces:
            return _fail(mesh, sel, f"{name}: selected polygons must be neighbours forming a single region")
        if cleanup:
            polys = _drop_midpoints(polys, {i for f in faces for i in mesh.polygons[f]}, before_valence)
        created = set(new_faces)
        polys, index = _prune(mesh.points, polys, [k in created for k in range(len(polys))])
        refusal = _refusal(mesh.polygons, polys, name)
        if refusal:
            return _fail(mesh, sel, refusal)
        out, _ = _finish(mesh, polys, before_used)
        return OpResult(out, Selection("polygons", polygons={index[k] for k in created if k in index}))
    if sel.mode == "edges":
        edges = _valid_edges(mesh, sel.edges)
        if not edges:
            return _fail(mesh, sel, f"{name}: no edges selected")
        polys, new_faces, skipped = _merge_groups(mesh.polygons, _face_union(mesh, edges))
        if not new_faces:
            return _fail(mesh, sel, f"{name}: the selected edges do not separate two polygons")
        if cleanup:
            polys = _drop_midpoints(polys, {i for e in edges for i in e}, before_valence)
        created = set(new_faces)
        polys, _ = _prune(mesh.points, polys, [k in created for k in range(len(polys))])
        refusal = _refusal(mesh.polygons, polys, name)
        if refusal:
            return _fail(mesh, sel, refusal)
        out, _ = _finish(mesh, polys, before_used)
        return OpResult(out, Selection("edges"))
    if sel.mode == "points":
        pts = _valid_points(mesh, sel.points)
        if not pts:
            return _fail(mesh, sel, f"{name}: no points selected")
        polys, fresh, done = _melt_points(mesh.polygons, pts)
        if not done:
            return _fail(mesh, sel, f"{name}: the selected points could not be removed")
        polys, _ = _prune(mesh.points, polys, fresh)
        refusal = _refusal(mesh.polygons, polys, name)
        if refusal:
            return _fail(mesh, sel, refusal)
        loose = [e for e in mesh.loose_edges if e[0] not in pts and e[1] not in pts]
        out, _ = _finish(mesh, polys, before_used, loose)
        return OpResult(out, Selection("points"))
    return _fail(mesh, sel, f"{name} needs points, edges or polygons mode")


def melt(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    return _merge_command(mesh, sel, "Melt", False)


def dissolve(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    return _merge_command(mesh, sel, "Dissolve", True)


def _close_clusters(pts: np.ndarray, ids: list[int], tolerance: float) -> dict[int, int]:
    tol = max(float(tolerance), 1e-9)
    cells: dict[tuple[int, int, int], list[int]] = {}
    for i in ids:
        cells.setdefault(tuple(int(c) for c in np.floor(pts[i] / tol)), []).append(i)
    parent = {i: i for i in ids}

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    offsets = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
    for cell, members in cells.items():
        for off in offsets:
            other = cells.get((cell[0] + off[0], cell[1] + off[1], cell[2] + off[2]), [])
            for i in members:
                for j in other:
                    if j <= i or float(np.linalg.norm(pts[i] - pts[j])) > tol:
                        continue
                    ri, rj = root(i), root(j)
                    if ri != rj:
                        parent[max(ri, rj)] = min(ri, rj)
    return {i: root(i) for i in ids if root(i) != i}


def optimize(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    ids = _valid_points(mesh, sel.points) if sel.mode == "points" and sel.points else list(range(len(mesh.points)))
    mapping = _close_clusters(mesh.points, ids, p["tolerance"]) if p["points"] else {}
    n_polys = len(mesh.polygons)
    out, remap = _merge_points(mesh, mapping, clean=bool(p["polygons"]),
                               orphans="drop_all" if p["unused_points"] else "keep_all")
    merged = len(mapping)
    removed_polys = n_polys - len(out.polygons)
    removed_pts = len(mesh.points) - len(out.points) - merged
    message = f"Optimize: {merged} points merged, {removed_polys} polygons and {removed_pts} unused points removed"
    return OpResult(out, _map_selection(mesh, out, sel, remap), True, message)


def _fan_components(polygons, faces: list[int], pt: int, cut: set) -> list[list[int]]:
    by_edge: dict[tuple[int, int], list[int]] = {}
    for f in faces:
        ring = polygons[f]
        k = ring.index(pt)
        for q in (ring[k - 1], ring[(k + 1) % len(ring)]):
            key = edge_key(pt, q)
            if key not in cut:
                by_edge.setdefault(key, []).append(f)
    parent = {f: f for f in faces}

    def root(f: int) -> int:
        while parent[f] != f:
            parent[f] = parent[parent[f]]
            f = parent[f]
        return f

    for owners in by_edge.values():
        for g in owners[1:]:
            parent[root(g)] = root(owners[0])
    comps: dict[int, list[int]] = {}
    for f in faces:
        comps.setdefault(root(f), []).append(f)
    return list(comps.values())


def _split_points(mesh: Mesh, cut: set, points, prefer: set[int]) -> dict[int, int]:
    pf = point_faces(mesh)
    rings = [list(poly) for poly in mesh.polygons]
    origin: dict[int, int] = {}
    for pt in sorted(points):
        faces = pf.get(pt, [])
        if len(faces) < 2:
            continue
        comps = _fan_components(mesh.polygons, faces, pt, cut)
        comps.sort(key=lambda c: (not any(f not in prefer for f in c), min(c)))
        for comp in comps[1:]:
            q = mesh.add_point(mesh.points[pt])
            origin[q] = pt
            for f in comp:
                rings[f] = [q if i == pt else i for i in rings[f]]
    mesh.polygons = [tuple(r) for r in rings]
    mesh._rebuild_edges()
    return origin


def disconnect(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    ef = edge_faces(mesh)
    if sel.mode == "polygons":
        faces = set(_valid_faces(mesh, sel.polygons))
        if not faces:
            return _fail(mesh, sel, "Disconnect: no polygons selected")
        mine = {edge_key(a, b) for f in faces for a, b in directed_edges(mesh.polygons[f])}
        if p["preserve_groups"]:
            cut = {e for e in mine if any(g not in faces for g in ef.get(e, []))}
        else:
            cut = mine
        _split_points(mesh, cut, {i for f in faces for i in mesh.polygons[f]}, faces)
        return OpResult(mesh, Selection("polygons", polygons=faces))
    if sel.mode == "points":
        pts = _valid_points(mesh, sel.points)
        if not pts:
            return _fail(mesh, sel, "Disconnect: no points selected")
        cut = {e for e in ef if e[0] in pts or e[1] in pts}
        origin = _split_points(mesh, cut, pts, set())
        return OpResult(mesh, Selection("points", points=set(pts) | set(origin)))
    if sel.mode == "edges":
        edges = set(_valid_edges(mesh, sel.edges))
        if not edges:
            return _fail(mesh, sel, "Disconnect: no edges selected")
        origin = _split_points(mesh, edges, {i for e in edges for i in e}, set())
        back = lambda i: origin.get(i, i)
        out = {e for e in mesh.edges if edge_key(back(e[0]), back(e[1])) in edges}
        return OpResult(mesh, Selection("edges", edges=out))
    return _fail(mesh, sel, "Disconnect needs points, edges or polygons mode")


def _faces_for_split(mesh: Mesh, sel: Selection) -> list[int]:
    if sel.mode == "polygons":
        return _valid_faces(mesh, sel.polygons)
    if sel.mode == "points":
        chosen = set(sel.points)
        return [k for k, poly in enumerate(mesh.polygons) if set(poly) <= chosen]
    if sel.mode == "edges":
        chosen = {edge_key(*e) for e in sel.edges}
        return [k for k, poly in enumerate(mesh.polygons)
                if all(edge_key(a, b) in chosen for a, b in directed_edges(poly))]
    return []


def split(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode not in COMPONENTS:
        return _fail(mesh, sel, "Split needs points, edges or polygons mode")
    faces = _faces_for_split(mesh, sel)
    if not faces:
        return _fail(mesh, sel, "Split: select polygons (or all points/edges of polygons)")
    copy: dict[int, int] = {}
    for i in sorted({i for f in faces for i in mesh.polygons[f]}):
        copy[i] = mesh.add_point(mesh.points[i])
    start = len(mesh.polygons)
    for f in faces:
        mesh.polygons.append(tuple(copy[i] for i in mesh.polygons[f]))
    mesh._rebuild_edges()
    new_faces = set(range(start, len(mesh.polygons)))
    if sel.mode == "points":
        return OpResult(mesh, Selection("points", points=set(copy.values())))
    if sel.mode == "edges":
        edges = {edge_key(a, b) for f in new_faces for a, b in directed_edges(mesh.polygons[f])}
        return OpResult(mesh, Selection("edges", edges=edges))
    return OpResult(mesh, Selection("polygons", polygons=new_faces))


register(ToolSpec(
    id="weld",
    name="Weld",
    apply=weld,
    modes=COMPONENTS,
    params=(
        Param("target", "Target Point", "runtime", None),
        Param("position", "Point", "runtime", None),
    ),
    interactive=True,
    drag_param=None,
    drag_kind="distance",
    section="TRANSFORM",
    shortcut="M~Q",
    description="Welds the selected elements into one point at the selection center or at the clicked point.",
    extra={"pick": "point", "runtime": {
        "target": "index of the point clicked in the view; the selection welds onto it",
        "position": "optional (x, y, z) local position for the welded point"}},
))

register(ToolSpec(
    id="bridge",
    name="Bridge",
    apply=bridge,
    modes=COMPONENTS,
    params=(
        Param("delete_original", "Delete Original Polygons", "bool", True),
        Param("edge_a", "Start Edge", "runtime", None),
        Param("edge_b", "End Edge", "runtime", None),
    ),
    interactive=True,
    drag_param=None,
    drag_kind="distance",
    section="CREATION TOOLS",
    shortcut="M~B",
    description="Joins two polygons, edge chains, border loops or a set of points with new polygons.",
    extra={"pick": "edge", "runtime": {
        "edge_a": "(a, b) point indices of the edge where the drag starts",
        "edge_b": "(a, b) point indices of the edge where the drag ends"}},
))

register(ToolSpec(
    id="stitch_and_sew",
    name="Stitch and Sew",
    apply=stitch_and_sew,
    modes=COMPONENTS,
    params=(
        Param("weld_to", "Weld To", "choice", "Center", choices=("Center", "First Edge", "Second Edge")),
        Param("create_polygons", "Create Polygons", "bool", False),
        Param("edge_a", "First Edge", "runtime", None),
        Param("edge_b", "Second Edge", "runtime", None),
    ),
    interactive=True,
    drag_param=None,
    drag_kind="distance",
    section="TRANSFORM",
    shortcut="M~P",
    description="Sews two edges or two border chains together by welding their points pairwise.",
    extra={"pick": "edge", "runtime": {
        "edge_a": "(a, b) point indices of the edge where the drag starts",
        "edge_b": "(a, b) point indices of the edge where the drag ends"},
        "modifiers": {"ctrl": "weld_to=First Edge", "shift": "create_polygons=True"}},
))

register(ToolSpec(
    id="close_polygon_hole",
    name="Close Polygon Hole",
    apply=close_polygon_hole,
    modes=COMPONENTS,
    params=(
        Param("create_ngons", "Create N-gons", "bool", True),
        Param("edge", "Border Edge", "runtime", None),
    ),
    interactive=True,
    drag_param=None,
    drag_kind="distance",
    section="CREATION TOOLS",
    shortcut="M~D",
    description="Fills the hole under the cursor (or touching the selection) with a single N-gon or triangles.",
    extra={"pick": "edge", "runtime": {"edge": "(a, b) point indices of the hovered border edge"}},
))

register(ToolSpec(
    id="connect_points_edges",
    name="Connect Points/Edges",
    apply=connect_points_edges,
    modes=("points", "edges"),
    params=(
        Param("preserve_ngons", "Preserve N-gons", "bool", False),
    ),
    interactive=False,
    drag_param=None,
    drag_kind="count",
    section="COMMANDS",
    shortcut="M~M",
    description="Cuts polygons between selected points, or connects the midpoints of selected edges.",
))

register(ToolSpec(
    id="melt",
    name="Melt",
    apply=melt,
    modes=COMPONENTS,
    params=(),
    interactive=False,
    drag_param=None,
    drag_kind="count",
    section="COMMANDS",
    shortcut="U~Z",
    description="Merges the selected polygons, or the polygons around selected edges or points, into N-gons.",
))

register(ToolSpec(
    id="dissolve",
    name="Dissolve",
    apply=dissolve,
    modes=COMPONENTS,
    params=(),
    interactive=False,
    drag_param=None,
    drag_kind="count",
    section="COMMANDS",
    shortcut="M~N",
    description="Removes the selected edges or points, merging their polygons and cleaning up leftover points.",
))

register(ToolSpec(
    id="optimize",
    name="Optimize",
    apply=optimize,
    modes=("points", "edges", "polygons", "model"),
    params=(
        Param("polygons", "Polygons", "bool", True),
        Param("unused_points", "Unused Points", "bool", True),
        Param("points", "Points", "bool", True),
        Param("tolerance", "Tolerance", "distance", 0.01, 0.0, 1e6, 0.01, "cm"),
    ),
    interactive=False,
    drag_param=None,
    drag_kind="distance",
    section="COMMANDS",
    shortcut="U~O",
    description="Merges coincident points and removes degenerate polygons and unused points.",
))

register(ToolSpec(
    id="disconnect",
    name="Disconnect",
    apply=disconnect,
    modes=COMPONENTS,
    params=(
        Param("preserve_groups", "Preserve Groups", "bool", True, modes=("polygons",)),
    ),
    interactive=False,
    drag_param=None,
    drag_kind="count",
    section="COMMANDS",
    shortcut="U~D",
    description="Gives the selected polygons their own points so they come loose from the rest of the mesh.",
))

register(ToolSpec(
    id="split",
    name="Split",
    apply=split,
    modes=COMPONENTS,
    params=(),
    interactive=False,
    drag_param=None,
    drag_kind="count",
    section="COMMANDS",
    shortcut="U~P",
    description="Copies the selected polygons into a separate shell, leaving the originals in place.",
))
