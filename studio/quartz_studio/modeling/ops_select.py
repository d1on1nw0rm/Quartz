from __future__ import annotations

import heapq
import math

import numpy as np

from ..scene import Mesh
from .meshkit import (OpResult, Selection, clone, directed_edges, edge_faces, edge_key, edge_loop,
                      edge_ring, face_area, point_faces, region_boundary)
from .registry import Param, ToolSpec, register

__all__ = ["select_all", "deselect_all", "invert_selection", "select_connected", "grow_selection",
           "shrink_selection", "loop_selection", "ring_selection", "outline_selection",
           "fill_selection", "path_selection", "convert_selection"]

ALL_MODES = ("points", "edges", "polygons")
TARGET_MODES = {"Points": "points", "Edges": "edges", "Polygons": "polygons"}


def _done(mesh: Mesh, selection: Selection) -> OpResult:
    return OpResult(clone(mesh), selection)


def _fail(mesh: Mesh, sel: Selection, message: str) -> OpResult:
    return OpResult(clone(mesh), sel.copy(), False, message)


def _sel(mode: str, items) -> Selection:
    items = set(items)
    if mode == "points":
        return Selection(mode, points=items)
    if mode == "edges":
        return Selection(mode, edges=items)
    return Selection(mode, polygons=items)


def _items(mesh: Mesh, sel: Selection) -> set:
    if sel.mode == "points":
        return {int(i) for i in sel.points if 0 <= int(i) < len(mesh.points)}
    if sel.mode == "edges":
        return {edge_key(*e) for e in sel.edges} & set(mesh.edges)
    return {int(f) for f in sel.polygons if 0 <= int(f) < len(mesh.polygons)}


def _universe(mesh: Mesh, mode: str) -> set:
    if mode == "points":
        return set(range(len(mesh.points)))
    if mode == "edges":
        return set(mesh.edges)
    return set(range(len(mesh.polygons)))


def _touched(mesh: Mesh, mode: str, items: set) -> set:
    if mode == "points":
        return set(items)
    if mode == "edges":
        return {i for e in items for i in e}
    return {i for f in items for i in mesh.polygons[f]}


def _adjacency(mesh: Mesh) -> dict[int, set[int]]:
    adj: dict[int, set[int]] = {}
    for a, b in mesh.edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def _incident(mesh: Mesh) -> dict[int, list]:
    inc: dict[int, list] = {}
    for e in mesh.edges:
        inc.setdefault(e[0], []).append(e)
        inc.setdefault(e[1], []).append(e)
    return inc


def _islands(mesh: Mesh) -> list[int]:
    parent = list(range(len(mesh.points)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in mesh.edges:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return [root(i) for i in range(len(mesh.points))]


def _grow(mesh: Mesh, mode: str, items: set) -> set:
    if mode == "points":
        adj = _adjacency(mesh)
        out = set(items)
        for i in items:
            out |= adj.get(i, set())
        return out
    if mode == "edges":
        inc = _incident(mesh)
        return {e for i in _touched(mesh, mode, items) for e in inc.get(i, [])}
    pf = point_faces(mesh)
    return {g for i in _touched(mesh, mode, items) for g in pf.get(i, [])}


def _shrink(mesh: Mesh, mode: str, items: set) -> set:
    if mode == "points":
        adj = _adjacency(mesh)
        return {i for i in items if adj.get(i, set()) <= items}
    if mode == "edges":
        inc = _incident(mesh)
        inner = {i for i, es in inc.items() if all(e in items for e in es)}
        return {e for e in items if e[0] in inner and e[1] in inner}
    boundary = {edge_key(u, v) for u, v in region_boundary(mesh, items)}
    return {f for f in items
            if not any(edge_key(a, b) in boundary for a, b in directed_edges(mesh.polygons[f]))}


def _opposite(poly: tuple[int, ...], e) -> tuple[int, int] | None:
    if len(poly) != 4:
        return None
    for j in range(4):
        a, b = poly[j], poly[(j + 1) % 4]
        if edge_key(a, b) == e:
            return edge_key(poly[(j + 2) % 4], poly[(j + 3) % 4])
    return None


def _belt(mesh: Mesh, ef: dict, face: int, e) -> set:
    poly = mesh.polygons[face]
    if len(poly) != 4:
        return set()
    out = {face}
    for start in (e, _opposite(poly, e)):
        cur, edge = face, start
        while edge is not None:
            nbrs = [g for g in ef.get(edge, []) if g != cur]
            if not nbrs or nbrs[0] in out or len(mesh.polygons[nbrs[0]]) != 4:
                break
            cur = nbrs[0]
            out.add(cur)
            edge = _opposite(mesh.polygons[cur], edge)
    return out


def _adjacent_edge(poly: tuple[int, ...], e) -> tuple[int, int] | None:
    if len(poly) != 4:
        return None
    for j in range(4):
        if edge_key(poly[j], poly[(j + 1) % 4]) == e:
            return edge_key(poly[(j + 1) % 4], poly[(j + 2) % 4])
    return None


def _shared_pairs(ef: dict, items: set) -> dict:
    return {e: owners for e, owners in ef.items() if len(owners) == 2 and all(f in items for f in owners)}


def _polygon_loop_faces(mesh: Mesh, items: set) -> set:
    ef = edge_faces(mesh)
    pairs = _shared_pairs(ef, items)
    covered = {f for owners in pairs.values() for f in owners}
    out = set(items)
    for e, owners in pairs.items():
        for f in owners:
            out |= _belt(mesh, ef, f, e)
    for f in items - covered:
        out |= _belt(mesh, ef, f, edge_key(*directed_edges(mesh.polygons[f])[0]))
    return out


def _polygon_ring_faces(mesh: Mesh, items: set) -> set:
    ef = edge_faces(mesh)
    pairs = _shared_pairs(ef, items)
    covered = {f for owners in pairs.values() for f in owners}
    out = set(items)
    for e, owners in pairs.items():
        for f in owners:
            side = _adjacent_edge(mesh.polygons[f], e)
            if side is not None:
                out |= _belt(mesh, ef, f, side)
    for f in items - covered:
        out |= _belt(mesh, ef, f, edge_key(*directed_edges(mesh.polygons[f])[1]))
    return out


def _point_flow(mesh: Mesh, items: set, flow) -> set:
    seeds = [e for e in mesh.edges if e[0] in items and e[1] in items]
    out: set[int] = set()
    for e in seeds:
        for a, b in flow(mesh, e):
            out.add(a)
            out.add(b)
    return out


def _closed_contour(edges: set) -> bool:
    deg: dict[int, int] = {}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    return bool(edges) and all(v == 2 for v in deg.values())


def _shortest_path(mesh: Mesh, start: int, goal: int) -> list[int] | None:
    adj = _adjacency(mesh)
    dist = {start: 0.0}
    prev: dict[int, int] = {}
    heap = [(0.0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == goal:
            break
        if d > dist[u]:
            continue
        for v in adj.get(u, ()):
            nd = d + float(np.linalg.norm(mesh.points[u] - mesh.points[v]))
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return path[::-1]


def select_all(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    return _done(mesh, _sel(sel.mode, _universe(mesh, sel.mode)))


def deselect_all(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    return _done(mesh, _sel(sel.mode, set()))


def invert_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    return _done(mesh, _sel(sel.mode, _universe(mesh, sel.mode) - _items(mesh, sel)))


def select_connected(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    if not items:
        return _fail(mesh, sel, "Select Connected: select at least one element")
    roots = _islands(mesh)
    if sel.mode == "points":
        keys = {roots[i] for i in items}
        out = {i for i in range(len(mesh.points)) if roots[i] in keys}
    elif sel.mode == "edges":
        keys = {roots[e[0]] for e in items}
        out = {e for e in mesh.edges if roots[e[0]] in keys}
    else:
        keys = {roots[mesh.polygons[f][0]] for f in items}
        out = {f for f, poly in enumerate(mesh.polygons) if roots[poly[0]] in keys}
    return _done(mesh, _sel(sel.mode, out))


def grow_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    if not items:
        return _fail(mesh, sel, "Grow Selection: select at least one element")
    return _done(mesh, _sel(sel.mode, _grow(mesh, sel.mode, items)))


def shrink_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    if not items:
        return _fail(mesh, sel, "Shrink Selection: select at least one element")
    return _done(mesh, _sel(sel.mode, _shrink(mesh, sel.mode, items)))


def loop_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    if not items:
        return _fail(mesh, sel, "Loop Selection: select at least one element")
    if sel.mode == "edges":
        out: set = set()
        for e in items:
            out.update(edge_loop(mesh, e))
        return _done(mesh, _sel("edges", out))
    if sel.mode == "polygons":
        if not any(len(mesh.polygons[f]) == 4 for f in items):
            return _fail(mesh, sel, "Loop Selection: polygons need quad topology")
        return _done(mesh, _sel("polygons", _polygon_loop_faces(mesh, items)))
    out = _point_flow(mesh, items, edge_loop)
    if not out:
        return _fail(mesh, sel, "Loop Selection: select two neighbouring points")
    return _done(mesh, _sel("points", out))


def ring_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    if not items:
        return _fail(mesh, sel, "Ring Selection: select at least one element")
    if sel.mode == "edges":
        out: set = set()
        for e in items:
            out.update(edge_ring(mesh, e))
        return _done(mesh, _sel("edges", out))
    if sel.mode == "polygons":
        if not any(len(mesh.polygons[f]) == 4 for f in items):
            return _fail(mesh, sel, "Ring Selection: polygons need quad topology")
        return _done(mesh, _sel("polygons", _polygon_ring_faces(mesh, items)))
    out = _point_flow(mesh, items, edge_ring)
    if not out:
        return _fail(mesh, sel, "Ring Selection: select two neighbouring points")
    return _done(mesh, _sel("points", out))


def outline_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    if not items:
        return _fail(mesh, sel, "Outline Selection: select polygons")
    boundary = {edge_key(u, v) for u, v in region_boundary(mesh, items)}
    return _done(mesh, Selection("edges", edges=boundary))


def fill_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    if not items:
        return _fail(mesh, sel, "Fill Selection: select edges that form a closed contour")
    if not _closed_contour(items):
        return _fail(mesh, sel, "Fill Selection: select edges that form a closed contour")
    ef = edge_faces(mesh)
    parent = list(range(len(mesh.polygons)))

    def root(f: int) -> int:
        while parent[f] != f:
            parent[f] = parent[parent[f]]
            f = parent[f]
        return f

    for e, owners in ef.items():
        if e in items:
            continue
        for g in owners[1:]:
            parent[root(g)] = root(owners[0])
    touching = {root(f) for e in items for f in ef.get(e, [])}
    if not touching:
        return _fail(mesh, sel, "Fill Selection: the contour does not border any polygon")
    regions: dict[int, list[int]] = {}
    for f in range(len(mesh.polygons)):
        regions.setdefault(root(f), []).append(f)
    sizes = {r: sum(face_area(mesh, f) for f in regions[r]) for r in touching}
    if p.get("side", "Smaller") == "Larger":
        pick = max(touching, key=lambda r: sizes[r])
    else:
        pick = min(touching, key=lambda r: sizes[r])
    return _done(mesh, _sel("polygons", regions[pick]))


def path_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    pts = sorted(_touched(mesh, sel.mode, items))
    if len(pts) != 2:
        return _fail(mesh, sel, "Path Selection: select exactly two points")
    path = _shortest_path(mesh, pts[0], pts[1])
    if path is None:
        return _fail(mesh, sel, "Path Selection: the two points are not connected")
    if sel.mode == "edges":
        return _done(mesh, _sel("edges", {edge_key(a, b) for a, b in zip(path, path[1:])}))
    return _done(mesh, _sel("points", path))


def convert_selection(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    items = _items(mesh, sel)
    if not items:
        return _fail(mesh, sel, "Convert Selection: select at least one element")
    target = TARGET_MODES[str(p.get("to", "Points"))]
    pts = _touched(mesh, sel.mode, items)
    if target == "points":
        out = pts
    elif target == "edges":
        if sel.mode == "points":
            out = {e for e in mesh.edges if e[0] in pts and e[1] in pts}
        elif sel.mode == "edges":
            out = items
        else:
            out = {edge_key(a, b) for f in items for a, b in directed_edges(mesh.polygons[f])}
    elif sel.mode == "polygons":
        out = items
    elif sel.mode == "edges":
        test = any if p.get("tolerant", True) else all
        out = {f for f, poly in enumerate(mesh.polygons)
               if test(edge_key(a, b) in items for a, b in directed_edges(poly))}
    else:
        test = any if p.get("tolerant", True) else all
        out = {f for f, poly in enumerate(mesh.polygons) if test(i in pts for i in poly)}
    return _done(mesh, _sel(target, out))


register(ToolSpec(
    id="select_all",
    name="Select All",
    apply=select_all,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="Ctrl+A",
    description="Selects every point, edge or polygon of the object.",
))

register(ToolSpec(
    id="deselect_all",
    name="Deselect All",
    apply=deselect_all,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut=None,
    description="Clears the selection.",
))

register(ToolSpec(
    id="invert_selection",
    name="Invert",
    apply=invert_selection,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~I",
    description="Selects everything that is not selected and deselects the rest.",
))

register(ToolSpec(
    id="select_connected",
    name="Select Connected",
    apply=select_connected,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~W",
    description="Extends the selection to every element of the connected islands it touches.",
))

register(ToolSpec(
    id="grow_selection",
    name="Grow Selection",
    apply=grow_selection,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~G",
    description="Adds one ring of neighbouring elements around the selection.",
))

register(ToolSpec(
    id="shrink_selection",
    name="Shrink Selection",
    apply=shrink_selection,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~K",
    description="Removes the outer ring of the selection.",
))

register(ToolSpec(
    id="loop_selection",
    name="Loop Selection",
    apply=loop_selection,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~L",
    description="Selects the edge loops, polygon loops or point loops defined by the selection.",
))

register(ToolSpec(
    id="ring_selection",
    name="Ring Selection",
    apply=ring_selection,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~B",
    description="Selects the edge rings, or the polygon rings, through the selection.",
))

register(ToolSpec(
    id="outline_selection",
    name="Outline Selection",
    apply=outline_selection,
    modes=("polygons",),
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~Q",
    description="Selects the edges that bound the selected polygons.",
))

register(ToolSpec(
    id="fill_selection",
    name="Fill Selection",
    apply=fill_selection,
    modes=("edges",),
    params=(
        Param("side", "Side", "choice", "Smaller", choices=("Smaller", "Larger")),
    ),
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~F",
    description="Selects the polygons on one side of a closed edge contour.",
))

register(ToolSpec(
    id="path_selection",
    name="Path Selection",
    apply=path_selection,
    modes=ALL_MODES,
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~M",
    description="Selects the shortest edge path between two selected points.",
))

register(ToolSpec(
    id="convert_selection",
    name="Convert Selection",
    apply=convert_selection,
    modes=ALL_MODES,
    params=(
        Param("to", "To", "choice", "Points", choices=("Points", "Edges", "Polygons")),
        Param("tolerant", "Tolerant", "bool", True),
    ),
    interactive=False,
    menu="Select",
    section="SELECTION",
    shortcut="U~X",
    description="Converts the selection to points, edges or polygons.",
))
