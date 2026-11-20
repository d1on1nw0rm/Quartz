from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from ..scene import Mesh, _ear_clip, _edge_key

Edge = tuple[int, int]

__all__ = [
    "Edge",
    "Selection",
    "OpResult",
    "edge_key",
    "clone",
    "carry_point_scales",
    "face_normals",
    "face_centers",
    "face_area",
    "edge_faces",
    "point_faces",
    "point_edges",
    "directed_edges",
    "region_boundary",
    "face_groups",
    "edge_groups",
    "vertex_normals",
    "point_normals_for_faces",
    "compact",
    "weld",
    "clean_polygons",
    "triangulate_polygon",
    "edge_loop",
    "edge_ring",
    "polygon_loop",
    "boundary_loops",
    "selection_points",
]


def edge_key(a: int, b: int) -> Edge:
    return _edge_key(a, b)


@dataclass
class Selection:
    mode: str
    points: set[int] = field(default_factory=set)
    edges: set[Edge] = field(default_factory=set)
    polygons: set[int] = field(default_factory=set)

    def copy(self) -> "Selection":
        return Selection(self.mode, set(self.points), set(self.edges), set(self.polygons))

    def items(self) -> set:
        return {"points": self.points, "edges": self.edges, "polygons": self.polygons}.get(self.mode, set())

    def is_empty(self) -> bool:
        return not self.items()


@dataclass
class OpResult:
    mesh: Mesh
    selection: Selection
    ok: bool = True
    message: str = ""


def clone(mesh: Mesh) -> Mesh:
    return Mesh(mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges),
                point_scales=mesh.point_scales)


def carry_point_scales(source: Mesh, result: Mesh) -> Mesh:
    scales = source.point_scales
    if scales is None or result.point_scales_explicit or not len(result.points):
        return result
    if (len(result.points) == len(source.points) and result.polygons == source.polygons
            and result.loose_edges == source.loose_edges):
        result.point_scales = scales
        return result
    lookup: dict[bytes, float] = {}
    for row, value in zip(np.ascontiguousarray(source.points, dtype=float) + 0.0, scales):
        lookup.setdefault(row.tobytes(), float(value))
    pts = np.ascontiguousarray(result.points, dtype=float) + 0.0
    result.point_scales = [lookup.get(row.tobytes(), 1.0) for row in pts]
    return result


def face_normals(mesh: Mesh) -> np.ndarray:
    return mesh.polygon_normals()


def face_centers(mesh: Mesh) -> np.ndarray:
    out = np.zeros((len(mesh.polygons), 3))
    for k, poly in enumerate(mesh.polygons):
        out[k] = mesh.points[list(poly)].mean(axis=0)
    return out


def face_area(mesh: Mesh, k: int) -> float:
    ring = mesh.points[list(mesh.polygons[k])]
    nxt = np.roll(ring, -1, axis=0)
    return 0.5 * float(np.linalg.norm(np.cross(ring, nxt).sum(axis=0)))


def directed_edges(poly: Iterable[int]) -> list[Edge]:
    p = list(poly)
    return list(zip(p, p[1:] + p[:1]))


def edge_faces(mesh: Mesh) -> dict[Edge, list[int]]:
    out: dict[Edge, list[int]] = {}
    for k, poly in enumerate(mesh.polygons):
        for a, b in directed_edges(poly):
            out.setdefault(_edge_key(a, b), []).append(k)
    return out


def point_faces(mesh: Mesh) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for k, poly in enumerate(mesh.polygons):
        for i in poly:
            out.setdefault(int(i), []).append(k)
    return out


def point_edges(mesh: Mesh) -> dict[int, list[Edge]]:
    out: dict[int, list[Edge]] = {}
    for e in mesh.edges:
        out.setdefault(e[0], []).append(e)
        out.setdefault(e[1], []).append(e)
    return out


def region_boundary(mesh: Mesh, faces: Iterable[int]) -> list[Edge]:
    faces = list(faces)
    directed = [(u, v) for f in faces for u, v in directed_edges(mesh.polygons[f])]
    present = set(directed)
    return [(u, v) for u, v in directed if (v, u) not in present]


def _angle_between(n0: np.ndarray, n1: np.ndarray) -> float:
    c = float(np.clip(n0 @ n1, -1.0, 1.0))
    return math.degrees(math.acos(c))


def face_groups(mesh: Mesh, faces: Iterable[int], max_angle: float | None = None) -> list[list[int]]:
    faces = sorted(set(int(f) for f in faces))
    if not faces:
        return []
    fset = set(faces)
    normals = face_normals(mesh) if max_angle is not None else None
    ef = edge_faces(mesh)
    seen: set[int] = set()
    groups: list[list[int]] = []
    for start in faces:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        group: list[int] = []
        while stack:
            f = stack.pop()
            group.append(f)
            for a, b in directed_edges(mesh.polygons[f]):
                for g in ef.get(_edge_key(a, b), ()):
                    if g in seen or g not in fset:
                        continue
                    if normals is not None and _angle_between(normals[f], normals[g]) > max_angle + 1e-9:
                        continue
                    seen.add(g)
                    stack.append(g)
        groups.append(sorted(group))
    return groups


def edge_groups(edges: Iterable[Edge]) -> list[list[Edge]]:
    edges = sorted({_edge_key(*e) for e in edges})
    by_point: dict[int, list[Edge]] = {}
    for e in edges:
        by_point.setdefault(e[0], []).append(e)
        by_point.setdefault(e[1], []).append(e)
    seen: set[Edge] = set()
    out: list[list[Edge]] = []
    for e in edges:
        if e in seen:
            continue
        stack = [e]
        seen.add(e)
        group: list[Edge] = []
        while stack:
            cur = stack.pop()
            group.append(cur)
            for p in cur:
                for nxt in by_point[p]:
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
        out.append(sorted(group))
    return out


def vertex_normals(mesh: Mesh) -> np.ndarray:
    normals = face_normals(mesh)
    out = np.zeros((len(mesh.points), 3))
    for k, poly in enumerate(mesh.polygons):
        for i in poly:
            out[i] += normals[k]
    lengths = np.linalg.norm(out, axis=1)
    mask = lengths > 1e-12
    out[mask] /= lengths[mask][:, None]
    return out


def point_normals_for_faces(mesh: Mesh, faces: Iterable[int], offset_correct: bool = True) -> dict[int, np.ndarray]:
    normals = face_normals(mesh)
    acc: dict[int, list[np.ndarray]] = {}
    for f in faces:
        for i in mesh.polygons[f]:
            acc.setdefault(int(i), []).append(normals[f])
    out: dict[int, np.ndarray] = {}
    for i, ns in acc.items():
        uniq: list[np.ndarray] = []
        for n in ns:
            if not any(float(n @ u) > 1 - 1e-9 for u in uniq):
                uniq.append(n)
        s = np.sum(uniq, axis=0)
        length = float(np.linalg.norm(s))
        if length < 1e-12:
            out[i] = np.zeros(3)
            continue
        d = s / length
        if offset_correct:
            cos = min(float(d @ n) for n in uniq)
            if cos > 0.05:
                d = d / cos
        out[i] = d
    return out


def clean_polygons(polygons: Iterable[Iterable[int]]) -> list[tuple[int, ...]]:
    out: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for poly in polygons:
        ring: list[int] = []
        for i in poly:
            i = int(i)
            if not ring or ring[-1] != i:
                ring.append(i)
        while len(ring) > 1 and ring[0] == ring[-1]:
            ring.pop()
        if len(ring) < 3 or len(set(ring)) != len(ring):
            continue
        k = ring.index(min(ring))
        canon = tuple(ring[k:] + ring[:k])
        if canon in seen:
            continue
        seen.add(canon)
        out.append(tuple(ring))
    return out


def compact(mesh: Mesh, keep: Iterable[int] = ()) -> tuple[Mesh, dict[int, int]]:
    used = sorted({int(i) for poly in mesh.polygons for i in poly}
                  | {int(i) for e in mesh.loose_edges for i in e}
                  | {int(i) for i in keep if 0 <= int(i) < len(mesh.points)})
    remap = {old: new for new, old in enumerate(used)}
    pts = mesh.points[used] if used else np.zeros((0, 3))
    polys = [tuple(remap[i] for i in poly) for poly in mesh.polygons]
    loose = [(remap[a], remap[b]) for a, b in mesh.loose_edges]
    out = Mesh(pts, polys, loose)
    if mesh.point_scales_explicit:
        scales = mesh.point_scales
        out.point_scales = None if scales is None or not used else scales[used]
    return out, remap


def weld(mesh: Mesh, mapping: dict[int, int], positions: dict[int, np.ndarray] | None = None) -> tuple[Mesh, dict[int, int]]:
    def root(i: int) -> int:
        seen = 0
        while i in mapping and mapping[i] != i and seen < len(mapping) + 1:
            i = mapping[i]
            seen += 1
        return i

    pts = mesh.points.copy()
    if positions:
        for i, p in positions.items():
            pts[int(i)] = np.asarray(p, float)
    polys = clean_polygons([[root(i) for i in poly] for poly in mesh.polygons])
    loose = []
    for a, b in mesh.loose_edges:
        ra, rb = root(a), root(b)
        if ra != rb:
            loose.append((ra, rb))
    merged = Mesh(pts, polys, loose)
    if mesh.point_scales_explicit:
        merged.point_scales = mesh.point_scales
    out, remap = compact(merged)
    full = {i: remap[root(i)] for i in range(len(mesh.points)) if root(i) in remap}
    return out, full


def triangulate_polygon(mesh: Mesh, k: int) -> list[tuple[int, int, int]]:
    poly = mesh.polygons[k]
    if len(poly) == 3:
        return [tuple(poly)]
    if len(poly) == 4:
        p = mesh.points[list(poly)]
        d02 = float(np.linalg.norm(p[0] - p[2]))
        d13 = float(np.linalg.norm(p[1] - p[3]))
        if d02 <= d13 + 1e-9:
            return [(poly[0], poly[1], poly[2]), (poly[0], poly[2], poly[3])]
        return [(poly[0], poly[1], poly[3]), (poly[1], poly[2], poly[3])]
    tris = _ear_clip(mesh.points[list(poly)])
    return [(poly[a], poly[b], poly[c]) for a, b, c in tris]


def _quad_opposite(poly: tuple[int, ...], e: Edge) -> Edge | None:
    if len(poly) != 4:
        return None
    for j in range(4):
        a, b = poly[j], poly[(j + 1) % 4]
        if _edge_key(a, b) == e:
            return _edge_key(poly[(j + 2) % 4], poly[(j + 3) % 4])
    return None


def edge_ring(mesh: Mesh, e: Edge) -> list[Edge]:
    e = _edge_key(*e)
    ef = edge_faces(mesh)
    ring = [e]
    seen_e = {e}
    seen_f: set[int] = set()
    for first in list(ef.get(e, [])):
        cur, face = e, first
        while face is not None and face not in seen_f:
            seen_f.add(face)
            nxt = _quad_opposite(mesh.polygons[face], cur)
            if nxt is None or nxt in seen_e:
                break
            seen_e.add(nxt)
            if first == ef[e][0]:
                ring.append(nxt)
            else:
                ring.insert(0, nxt)
            others = [g for g in ef.get(nxt, []) if g != face]
            face = others[0] if others else None
            cur = nxt
    return ring


def edge_loop(mesh: Mesh, e: Edge) -> list[Edge]:
    e = _edge_key(*e)
    ef = edge_faces(mesh)
    pf = point_faces(mesh)
    pe = point_edges(mesh)
    loop = [e]
    seen = {e}

    def step(cur: Edge, at: int) -> Edge | None:
        faces_at = pf.get(at, [])
        edges_at = pe.get(at, [])
        if len(edges_at) != 4 or len(faces_at) != 4:
            return None
        cur_faces = set(ef.get(cur, []))
        for cand in edges_at:
            if cand == cur:
                continue
            if not cur_faces & set(ef.get(cand, [])):
                return cand
        return None

    for direction in (0, 1):
        cur = e
        at = e[1] if direction == 0 else e[0]
        while True:
            nxt = step(cur, at)
            if nxt is None or nxt in seen:
                break
            seen.add(nxt)
            if direction == 0:
                loop.append(nxt)
            else:
                loop.insert(0, nxt)
            at = nxt[1] if nxt[0] == at else nxt[0]
            cur = nxt
    return loop


def polygon_loop(mesh: Mesh, e: Edge) -> list[int]:
    ring = edge_ring(mesh, e)
    ef = edge_faces(mesh)
    faces: list[int] = []
    for a, b in zip(ring, ring[1:]):
        common = set(ef.get(a, [])) & set(ef.get(b, []))
        for f in common:
            if f not in faces:
                faces.append(f)
    return faces


def boundary_loops(mesh: Mesh, edges: Iterable[Edge] | None = None) -> list[list[int]]:
    ef = edge_faces(mesh)
    nxt: dict[int, int] = {}
    allowed = None if edges is None else {_edge_key(*x) for x in edges}
    for k, poly in enumerate(mesh.polygons):
        for a, b in directed_edges(poly):
            key = _edge_key(a, b)
            if len(ef[key]) == 1 and (allowed is None or key in allowed):
                nxt[b] = a
    loops: list[list[int]] = []
    seen: set[int] = set()
    for start in sorted(nxt):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        cur = nxt[start]
        guard = 0
        while cur != start and cur in nxt and cur not in seen and guard < len(nxt) + 1:
            loop.append(cur)
            seen.add(cur)
            cur = nxt[cur]
            guard += 1
        if cur == start and len(loop) >= 3:
            loops.append(loop)
    return loops


def selection_points(mesh: Mesh, sel: Selection) -> list[int]:
    if sel.mode == "points":
        pts = set(sel.points)
    elif sel.mode == "edges":
        pts = {i for e in sel.edges for i in e}
    elif sel.mode == "polygons":
        pts = {i for p in sel.polygons for i in mesh.polygons[p]}
    else:
        pts = set(range(len(mesh.points)))
    return sorted(pts)
