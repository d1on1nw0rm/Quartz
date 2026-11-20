from __future__ import annotations

import math
import random

import numpy as np

from ..scene import Mesh
from .meshkit import (OpResult, Selection, clone, directed_edges, edge_faces, edge_key,
                      edge_loop, point_edges, selection_points, triangulate_polygon)
from .registry import Param, ToolSpec, register

__all__ = ["set_flow", "set_point_value", "array_copies", "clone_copies", "remove_ngons",
           "retriangulate_ngons", "edge_to_spline"]

_AXES = ("x", "y", "z")
_AXIS_MODES = ("Leave", "Set", "Center", "Quantize", "Crumple (Axial)", "Crumple (Radial)")
_AXIS_VECTORS = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def _fail(mesh: Mesh, sel: Selection, message: str) -> OpResult:
    return OpResult(clone(mesh), sel.copy(), False, message)


def _catmull_rom(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, t: float) -> np.ndarray:
    return 0.5 * (2.0 * p1
                  + (p2 - p0) * t
                  + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                  + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t)


def _opposite_index(pe: dict, ef: dict, at: int, q: tuple[int, int]) -> int | None:
    if len(pe.get(at, ())) != 4:
        return None
    faces_q = set(ef.get(q, ()))
    for g in pe[at]:
        if g == q:
            continue
        if not faces_q & set(ef.get(g, ())):
            return g[1] if g[0] == at else g[0]
    return None


def _flow_target(mesh: Mesh, pe: dict, ef: dict, i: int, loop_set: set) -> np.ndarray | None:
    if len(pe.get(i, ())) != 4:
        return None
    perp = [e for e in pe[i] if e not in loop_set]
    if len(perp) != 2 or any(len(ef.get(q, ())) != 2 for q in perp):
        return None
    sides = []
    for q in perp:
        a = q[0] if q[1] == i else q[1]
        sides.append((a, _opposite_index(pe, ef, a, q)))
    (ia, ja), (ib, jb) = sides
    p = mesh.points[i]
    a1, b1 = mesh.points[ia], mesh.points[ib]
    p0 = mesh.points[ja] if ja is not None else 2.0 * a1 - b1
    p3 = mesh.points[jb] if jb is not None else 2.0 * b1 - a1
    da = float(np.linalg.norm(p - a1))
    db = float(np.linalg.norm(p - b1))
    total = da + db
    s = da / total if total > 1e-12 else 0.5
    return _catmull_rom(p0, a1, b1, p3, s)


def set_flow(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    edges = sorted({edge_key(*e) for e in sel.edges})
    if not edges:
        return _fail(mesh, sel, "Set Flow: no edges selected")
    pe = point_edges(mesh)
    ef = edge_faces(mesh)
    strength = float(p["strength"]) / 100.0
    targets: dict[int, np.ndarray] = {}
    done: set[tuple] = set()
    for e in edges:
        loop = edge_loop(mesh, e)
        key = tuple(sorted(loop))
        if key in done:
            continue
        done.add(key)
        loop_set = set(loop)
        for i in sorted({v for ed in loop for v in ed}):
            target = _flow_target(mesh, pe, ef, i, loop_set)
            if target is not None:
                targets[i] = target
    m = clone(mesh)
    for i, target in targets.items():
        base = mesh.points[i]
        m.points[i] = base + (target - base) * strength
    return OpResult(m, sel.copy())


def _selected(mesh: Mesh, sel: Selection) -> tuple[list[int], list[int]]:
    if sel.mode == "polygons":
        faces = sorted(f for f in sel.polygons if 0 <= f < len(mesh.polygons))
        ids = sorted({int(i) for f in faces for i in mesh.polygons[f]})
        return faces, ids
    return [], sorted(int(i) for i in sel.points if 0 <= i < len(mesh.points))


def _duplicate(mesh: Mesh, sel: Selection, transforms: list) -> Mesh:
    faces, ids = _selected(mesh, sel)
    m = clone(mesh)
    base = mesh.points[ids]
    keep = set(ids)
    loose = []
    if sel.mode == "points":
        loose = [e for e in mesh.loose_edges if e[0] in keep and e[1] in keep]
    rows: list[np.ndarray] = []
    polys: list[tuple[int, ...]] = []
    edges: list[tuple[int, int]] = []
    count = len(mesh.points)
    for transform in transforms:
        pos = transform(base)
        mapping: dict[int, int] = {}
        for k, old in enumerate(ids):
            mapping[old] = count
            rows.append(pos[k])
            count += 1
        for f in faces:
            polys.append(tuple(mapping[i] for i in mesh.polygons[f]))
        for a, b in loose:
            edges.append((mapping[a], mapping[b]))
    if rows:
        m.points = np.vstack([m.points, np.array(rows, float)])
    m.polygons.extend(polys)
    m.loose_edges.extend(edges)
    m._rebuild_edges()
    return m


def _shift(shift: np.ndarray):
    def transform(pts: np.ndarray) -> np.ndarray:
        return pts + shift
    return transform


def _rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    t = 1.0 - c
    return np.array([
        [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
        [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
        [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
    ])


def _spin(pivot: np.ndarray, rot: np.ndarray, factor: float, shift: np.ndarray):
    def transform(pts: np.ndarray) -> np.ndarray:
        return (pts - pivot) @ rot.T * factor + pivot + shift
    return transform


def set_point_value(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    ids = selection_points(mesh, sel)
    if not ids:
        return _fail(mesh, sel, "Set Point Value: nothing selected")
    m = clone(mesh)
    rows = np.array(ids, dtype=int)
    orig = mesh.points[rows].copy()
    lo, hi = orig.min(axis=0), orig.max(axis=0)
    centre = (lo + hi) / 2.0
    rng = random.Random(int(p["seed"]))
    for a, key in enumerate(_AXES):
        mode = p[key]
        value = float(p[key + "_value"])
        col = orig[:, a]
        if mode == "Set":
            new = np.full(len(rows), value)
        elif mode == "Center":
            new = np.full(len(rows), centre[a])
        elif mode == "Quantize":
            new = np.round(col / value) * value if value > 0 else col.copy()
        elif mode == "Crumple (Axial)":
            new = col + np.array([value * rng.uniform(-1.0, 1.0) for _ in rows])
        elif mode == "Crumple (Radial)":
            others = [b for b in range(3) if b != a]
            dist = np.linalg.norm(orig[:, others] - centre[others], axis=1)
            top = float(dist.max())
            ratio = dist / top if top > 1e-12 else np.zeros(len(rows))
            new = col + np.array([value * rng.uniform(-1.0, 1.0) * r for r in ratio])
        else:
            continue
        m.points[rows, a] = new
    return OpResult(m, sel.copy())


def array_copies(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    faces, ids = _selected(mesh, sel)
    if not ids:
        return _fail(mesh, sel, "Array: nothing selected")
    counts = [max(1, int(p[k])) for k in ("clones_x", "clones_y", "clones_z")]
    offset = np.asarray(p["offset"], float)
    transforms = []
    for ix in range(counts[0]):
        for iy in range(counts[1]):
            for iz in range(counts[2]):
                if ix == iy == iz == 0:
                    continue
                transforms.append(_shift(offset * np.array([ix, iy, iz], float)))
    return OpResult(_duplicate(mesh, sel, transforms), sel.copy())


def clone_copies(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    faces, ids = _selected(mesh, sel)
    if not ids:
        return _fail(mesh, sel, "Clone: nothing selected")
    axis = np.array(_AXIS_VECTORS[p["axis"]], float)
    pivot = mesh.points[ids].mean(axis=0)
    step = axis * float(p["offset"])
    angle = math.radians(float(p["rotation"]))
    scale = float(p["scale"]) / 100.0
    transforms = []
    for k in range(1, max(1, int(p["clones"])) + 1):
        transforms.append(_spin(pivot, _rotation(axis, k * angle), scale ** k, k * step))
    return OpResult(_duplicate(mesh, sel, transforms), sel.copy())


def _quad_from(points: np.ndarray, tri: tuple[int, int, int], other: tuple[int, int, int],
               u: int, v: int) -> tuple[int, int, int, int] | None:
    w = next(x for x in tri if x != u and x != v)
    z = next(x for x in other if x != u and x != v)
    quad = (u, z, v, w)
    n = np.cross(points[v] - points[u], points[w] - points[u])
    for k in range(4):
        a, b, c = quad[k - 1], quad[k], quad[(k + 1) % 4]
        turn = np.cross(points[b] - points[a], points[c] - points[b])
        if float(turn @ n) <= 1e-9:
            return None
    return quad


def _split_ngon(mesh: Mesh, k: int, normal: np.ndarray) -> list[tuple[int, ...]]:
    pts = mesh.points
    tris: list[tuple[int, int, int]] = []
    for a, b, c in triangulate_polygon(mesh, k):
        n = np.cross(pts[b] - pts[a], pts[c] - pts[a])
        tris.append((a, c, b) if float(n @ normal) < 0 else (a, b, c))
    owner: dict[tuple[int, int], int] = {}
    for t, tri in enumerate(tris):
        for u, v in directed_edges(tri):
            owner[(u, v)] = t
    used = [False] * len(tris)
    pieces: list[tuple[int, ...]] = []
    for t, tri in enumerate(tris):
        if used[t]:
            continue
        used[t] = True
        merged = None
        for u, v in directed_edges(tri):
            s = owner.get((v, u))
            if s is None or used[s]:
                continue
            quad = _quad_from(pts, tri, tris[s], u, v)
            if quad is not None:
                merged = (s, quad)
                break
        if merged is None:
            pieces.append(tuple(tri))
        else:
            used[merged[0]] = True
            pieces.append(merged[1])
    return pieces


def remove_ngons(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    for poly in mesh.polygons:
        if len(poly) > 4 and len(set(poly)) != len(poly):
            return _fail(mesh, sel, "Remove N-gons: an N-gon repeats a vertex")
    normals = mesh.polygon_normals()
    out: list[tuple[int, ...]] = []
    mapping: dict[int, list[int]] = {}
    converted = 0
    for k, poly in enumerate(mesh.polygons):
        if len(poly) <= 4:
            pieces = [tuple(poly)]
        else:
            converted += 1
            pieces = _split_ngon(mesh, k, normals[k])
        mapping[k] = list(range(len(out), len(out) + len(pieces)))
        out.extend(pieces)
    m = clone(mesh)
    m.polygons = out
    m._rebuild_edges()
    new_sel = sel.copy()
    new_sel.polygons = {j for k in sel.polygons if k in mapping for j in mapping[k]}
    return OpResult(m, new_sel, True, f"Remove N-gons: {converted} converted")


def retriangulate_ngons(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    for poly in mesh.polygons:
        if len(poly) > 4 and len(set(poly)) != len(poly):
            return _fail(mesh, sel, "Retriangulate N-gons: an N-gon repeats a vertex")
    m = clone(mesh)
    count = 0
    changed = 0
    polys: list[tuple[int, ...]] = []
    for poly in mesh.polygons:
        if len(poly) > 4:
            count += 1
            k = poly.index(min(poly))
            rotated = tuple(poly[k:]) + tuple(poly[:k])
            if rotated != tuple(poly):
                changed += 1
            polys.append(rotated)
        else:
            polys.append(tuple(poly))
    m.polygons = polys
    m._rebuild_edges()
    return OpResult(m, sel.copy(), True,
                    f"Retriangulate N-gons: {count} N-gons checked, {changed} re-indexed")


def edge_to_spline(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    known = set(mesh.edges)
    edges = sorted({edge_key(*e) for e in sel.edges if edge_key(*e) in known})
    if not edges:
        return _fail(mesh, sel, "Edge to Spline: no edges selected")
    m = clone(mesh)
    base = len(mesh.points)
    mapping: dict[int, int] = {}
    rows: list[np.ndarray] = []
    for a, b in edges:
        for i in (a, b):
            if i not in mapping:
                mapping[i] = base + len(rows)
                rows.append(mesh.points[i])
    m.points = np.vstack([m.points, np.array(rows, float)])
    new_edges = [edge_key(mapping[a], mapping[b]) for a, b in edges]
    m.loose_edges.extend(new_edges)
    m._rebuild_edges()
    return OpResult(m, Selection("edges", edges=set(new_edges)), True,
                    f"Edge to Spline: {len(edges)} segments")


register(ToolSpec(
    id="set_flow",
    name="Set Flow",
    apply=set_flow,
    modes=("edges",),
    params=(
        Param("strength", "Strength", "percent", 100.0, 0.0, 100.0, 1.0, "%"),
    ),
    interactive=False,
    menu="Mesh",
    section="TRANSFORM",
    description="Bends the selected edge loops onto the curvature of the neighbouring loops.",
))

register(ToolSpec(
    id="set_point_value",
    name="Set Point Value",
    apply=set_point_value,
    modes=("points", "edges", "polygons"),
    params=(
        Param("x", "X", "choice", "Leave", choices=_AXIS_MODES),
        Param("x_value", "X Value", "float", 0.0, -1e6, 1e6, 1.0, "cm"),
        Param("y", "Y", "choice", "Leave", choices=_AXIS_MODES),
        Param("y_value", "Y Value", "float", 0.0, -1e6, 1e6, 1.0, "cm"),
        Param("z", "Z", "choice", "Leave", choices=_AXIS_MODES),
        Param("z_value", "Z Value", "float", 0.0, -1e6, 1e6, 1.0, "cm"),
        Param("seed", "Seed", "int", 0, 0, 1000000, 1),
    ),
    interactive=False,
    menu="Mesh",
    section="TRANSFORM",
    description="Sets, centres, quantizes or crumples the coordinates of the selected points.",
))

register(ToolSpec(
    id="array",
    name="Array",
    apply=array_copies,
    modes=("points", "polygons"),
    params=(
        Param("clones_x", "Clones X", "int", 1, 1, 100, 1),
        Param("clones_y", "Clones Y", "int", 1, 1, 100, 1),
        Param("clones_z", "Clones Z", "int", 1, 1, 100, 1),
        Param("offset", "Offset", "vector", (250.0, 250.0, 250.0), unit="cm"),
    ),
    interactive=False,
    menu="Mesh",
    section="CREATION TOOLS",
    description="Duplicates the selection in a grid, keeping the originals.",
))

register(ToolSpec(
    id="clone",
    name="Clone",
    apply=clone_copies,
    modes=("points", "polygons"),
    params=(
        Param("clones", "Clones", "int", 1, 1, 1000, 1),
        Param("offset", "Offset", "distance", 100.0, -1e6, 1e6, 1.0, "cm"),
        Param("axis", "Axis", "choice", "X", choices=("X", "Y", "Z")),
        Param("rotation", "Rotation", "angle", 0.0, -360.0, 360.0, 1.0, "°"),
        Param("scale", "Scale", "percent", 100.0, 1.0, 1000.0, 1.0, "%"),
    ),
    interactive=False,
    menu="Mesh",
    section="CREATION TOOLS",
    description="Creates copies in sequence along an axis, each with accumulated offset, rotation and scale.",
))

register(ToolSpec(
    id="remove_ngons",
    name="Remove N-gons",
    apply=remove_ngons,
    modes=("points", "edges", "polygons", "model"),
    interactive=False,
    menu="Mesh",
    section="COMMANDS",
    description="Splits every N-gon into triangles and quads.",
))

register(ToolSpec(
    id="retriangulate_ngons",
    name="Retriangulate N-gons",
    apply=retriangulate_ngons,
    modes=("points", "edges", "polygons", "model"),
    interactive=False,
    menu="Mesh",
    section="COMMANDS",
    description="Validates every N-gon and re-indexes it to start at its lowest vertex index.",
))

register(ToolSpec(
    id="edge_to_spline",
    name="Edge to Spline",
    apply=edge_to_spline,
    modes=("edges",),
    interactive=False,
    menu="Mesh",
    section="COMMANDS",
    description="Adds the selected edges as loose edges on duplicated points, leaving the mesh otherwise intact.",
))
