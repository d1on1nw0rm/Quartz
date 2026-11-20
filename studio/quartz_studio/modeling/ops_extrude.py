from __future__ import annotations

import math
import random

import numpy as np

from ..scene import Mesh
from .meshkit import (OpResult, Selection, clone, compact, directed_edges, edge_faces, edge_key,
                      face_groups, face_normals, point_normals_for_faces, region_boundary)
from .registry import Param, ToolSpec, register

__all__ = ["extrude"]


def _variance(rng: random.Random, variance: float) -> float:
    return rng.uniform(-variance, variance) if variance > 0 else 0.0


def _extrude_polygons(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    faces = sorted(f for f in sel.polygons if 0 <= f < len(mesh.polygons))
    if not faces:
        return OpResult(mesh, sel, False, "Extrude: no polygons selected")
    offset = float(p["offset"])
    steps = max(1, int(p["subdivision"]))
    rng = random.Random(int(p.get("seed", 12345)))
    groups = face_groups(mesh, faces, float(p["max_angle"])) if p["preserve_groups"] else [[f] for f in faces]
    original = {f: tuple(mesh.polygons[f]) for f in faces}
    referenced = {int(i) for poly in mesh.polygons for i in poly} | {int(i) for e in mesh.loose_edges for i in e}
    input_orphans = [i for i in range(len(mesh.points)) if i not in referenced]
    new_polys: list[tuple[int, ...]] = []
    caps: list[tuple[int, ...]] = []
    for group in groups:
        dist = offset + _variance(rng, float(p["variance"]))
        dirs = point_normals_for_faces(mesh, group)
        layers: list[dict[int, int]] = []
        for s in range(1, steps + 1):
            t = s / steps
            layer = {}
            for i, d in dirs.items():
                layer[i] = mesh.add_point(mesh.points[i] + d * dist * t)
            layers.append(layer)
        top = layers[-1]
        boundary = region_boundary(mesh, group)
        chain = [{i: i for i in dirs}] + layers
        for u, v in boundary:
            for s in range(steps):
                lo, hi = chain[s], chain[s + 1]
                new_polys.append((lo[u], lo[v], hi[v], hi[u]))
        for f in group:
            if p["create_caps"]:
                caps.append(tuple(reversed(original[f])))
            mesh.polygons[f] = tuple(top[i] for i in original[f])
    if p["create_ngons"]:
        new_polys = _merge_side_strips(new_polys, steps)
    first_side = len(mesh.polygons)
    mesh.polygons.extend(new_polys)
    mesh.polygons.extend(caps)
    mesh, _ = compact(mesh, keep=input_orphans)
    out = Selection("polygons", polygons=set(faces))
    if p["select_sides"]:
        out.polygons |= set(range(first_side, first_side + len(new_polys)))
    return OpResult(mesh, out)


def _merge_side_strips(polys: list[tuple[int, ...]], steps: int) -> list[tuple[int, ...]]:
    if steps <= 1:
        return polys
    out: list[tuple[int, ...]] = []
    for k in range(0, len(polys), steps):
        strip = polys[k:k + steps]
        left = [strip[0][0]] + [q[3] for q in strip]
        right = [strip[0][1]] + [q[2] for q in strip]
        out.append(tuple(left[:1] + right + list(reversed(left[1:]))))
    return out


def _extrude_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    edges = sorted(edge_key(*e) for e in sel.edges if edge_key(*e) in set(mesh.edges))
    if not edges:
        return OpResult(mesh, sel, False, "Extrude: no edges selected")
    offset = float(p["offset"])
    angle = math.radians(float(p["edge_angle"]))
    steps = max(1, int(p["subdivision"]))
    ef = edge_faces(mesh)
    normals = face_normals(mesh)
    pt_dir: dict[int, list[np.ndarray]] = {}
    edge_info: list[tuple[int, int, bool]] = []
    for a, b in edges:
        owners = ef.get((a, b), [])
        pa, pb = mesh.points[a], mesh.points[b]
        along = pb - pa
        length = float(np.linalg.norm(along))
        if length < 1e-12:
            continue
        along /= length
        flip = False
        if owners:
            f = owners[0]
            n = normals[f]
            center = mesh.points[list(mesh.polygons[f])].mean(axis=0)
            out_dir = np.cross(along, n)
            if float(out_dir @ (center - pa)) > 0:
                out_dir = -out_dir
            directed = (a, b) in directed_edges(mesh.polygons[f])
            flip = directed
        else:
            n = np.array([0.0, 1.0, 0.0]) if abs(along[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
            out_dir = np.cross(along, n)
            out_dir /= max(1e-12, float(np.linalg.norm(out_dir)))
            n = np.cross(out_dir, along)
        d = out_dir * math.cos(angle) + n * math.sin(angle)
        for i in (a, b):
            pt_dir.setdefault(i, []).append(d)
        edge_info.append((a, b, flip))
    if not edge_info:
        return OpResult(mesh, sel, False, "Extrude: edges have no length")
    dirs = {}
    for i, ds in pt_dir.items():
        s = np.sum(ds, axis=0)
        length = float(np.linalg.norm(s))
        d = s / length if length > 1e-12 else ds[0]
        cos = min(float(d @ x) for x in ds)
        dirs[i] = d / cos if cos > 0.05 else d
    layers = [{i: i for i in dirs}]
    for s in range(1, steps + 1):
        t = s / steps
        layers.append({i: mesh.add_point(mesh.points[i] + dirs[i] * offset * t) for i in dirs})
    new_edges = set()
    for a, b, flip in edge_info:
        for s in range(steps):
            lo, hi = layers[s], layers[s + 1]
            if flip:
                quad = (lo[b], lo[a], hi[a], hi[b])
            else:
                quad = (lo[a], lo[b], hi[b], hi[a])
            mesh.polygons.append(quad)
        top = layers[-1]
        new_edges.add(edge_key(top[a], top[b]))
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("edges", edges=new_edges))


def _extrude_points(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    pts = sorted(i for i in sel.points if 0 <= i < len(mesh.points))
    if not pts:
        return OpResult(mesh, sel, False, "Extrude: no points selected")
    normals = face_normals(mesh)
    offset = float(p["offset"])
    new_sel = set()
    for i in pts:
        ring = [k for k, poly in enumerate(mesh.polygons) if i in poly]
        if ring:
            d = normals[ring].sum(axis=0)
            length = float(np.linalg.norm(d))
            d = d / length if length > 1e-12 else np.zeros(3)
        else:
            d = np.zeros(3)
        q = mesh.add_point(mesh.points[i] + d * offset)
        mesh.loose_edges.append(edge_key(i, q))
        new_sel.add(q)
    mesh._rebuild_edges()
    return OpResult(mesh, Selection("points", points=new_sel))


def extrude(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode == "polygons":
        return _extrude_polygons(mesh, sel, p)
    if sel.mode == "edges":
        return _extrude_edges(mesh, sel, p)
    if sel.mode == "points":
        return _extrude_points(mesh, sel, p)
    return OpResult(mesh, sel, False, "Extrude needs points, edges or polygons mode")


register(ToolSpec(
    id="extrude",
    name="Extrude",
    apply=extrude,
    modes=("points", "edges", "polygons"),
    params=(
        Param("max_angle", "Maximum Angle", "angle", 89.0, 0.0, 180.0, 1.0, "°", modes=("polygons",)),
        Param("offset", "Offset", "distance", 5.0, -1e6, 1e6, 1.0, "cm"),
        Param("variance", "Variance", "distance", 0.0, 0.0, 1e6, 1.0, "cm", modes=("polygons",)),
        Param("subdivision", "Subdivision", "int", 1, 1, 1000, 1),
        Param("edge_angle", "Edge Angle", "angle", 0.0, -180.0, 180.0, 1.0, "°", modes=("edges",)),
        Param("create_ngons", "Create N-gons", "bool", False, modes=("polygons",)),
        Param("create_caps", "Create Caps", "bool", False, modes=("polygons",)),
        Param("preserve_groups", "Preserve Groups", "bool", True, modes=("polygons",)),
        Param("select_sides", "Select Sides", "bool", False, modes=("polygons",)),
    ),
    drag_param="offset",
    drag_kind="distance",
    shortcut="M~T",
    description="Extrudes the selected polygons, edges or points. Drag in the view to set the offset.",
))
