from __future__ import annotations

import math
import random

import numpy as np

from ..scene import Mesh
from .meshkit import (OpResult, Selection, clone, compact, directed_edges, face_groups,
                      face_normals, region_boundary)
from .registry import Param, ToolSpec, register

__all__ = ["inset", "smooth_shift", "thicken", "matrix_extrude"]


def _rng(p: dict) -> random.Random:
    return random.Random(int(p.get("seed", 12345)))


def _variance(rng: random.Random, variance: float) -> float:
    return rng.uniform(-variance, variance) if variance > 0 else 0.0


def _selected_faces(mesh: Mesh, sel: Selection) -> list[int]:
    return sorted(int(f) for f in sel.polygons if 0 <= int(f) < len(mesh.polygons))


def _used_points(mesh: Mesh) -> set[int]:
    return ({int(i) for poly in mesh.polygons for i in poly}
            | {int(i) for e in mesh.loose_edges for i in e})


def _free_points(mesh: Mesh) -> set[int]:
    return set(range(len(mesh.points))) - _used_points(mesh)


def _finish(mesh: Mesh, free: set[int]) -> Mesh:
    mesh._rebuild_edges()
    if len(_used_points(mesh) | free) == len(mesh.points):
        return mesh
    out, _ = compact(mesh, keep=free)
    return out


def _owner_map(mesh: Mesh, faces) -> dict[tuple[int, int], int]:
    return {(a, b): f for f in faces for a, b in directed_edges(mesh.polygons[f])}


def _prev(poly: tuple[int, ...], v: int) -> int:
    return poly[poly.index(v) - 1]


def _next(poly: tuple[int, ...], v: int) -> int:
    return poly[(poly.index(v) + 1) % len(poly)]


def _incoming(mesh: Mesh, owner: dict, f: int, v: int):
    prv = _prev(mesh.polygons[f], v)
    for _ in range(len(owner) + 1):
        g = owner.get((v, prv))
        if g is None:
            return (prv, v), f
        f = g
        prv = _prev(mesh.polygons[f], v)
    return None


def _outgoing(mesh: Mesh, owner: dict, f: int, v: int):
    nxt = _next(mesh.polygons[f], v)
    for _ in range(len(owner) + 1):
        g = owner.get((nxt, v))
        if g is None:
            return (v, nxt), f
        f = g
        nxt = _next(mesh.polygons[f], v)
    return None


def _unit(v: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(v))
    return v / length if length > 1e-12 else np.zeros(3)


def _inward(mesh: Mesh, normals: np.ndarray, edge: tuple[int, int], f: int) -> np.ndarray:
    a, b = edge
    return _unit(np.cross(normals[f], mesh.points[b] - mesh.points[a]))


def _miter(d1: np.ndarray, d2: np.ndarray) -> np.ndarray:
    s = d1 + d2
    length = float(np.linalg.norm(s))
    if length < 1e-9:
        return d1
    d = s / length
    c = float(d @ d1)
    return d / c if c > 0.1 else d


def _merge_strips(polys: list[tuple[int, ...]], steps: int) -> list[tuple[int, ...]]:
    if steps <= 1:
        return polys
    out: list[tuple[int, ...]] = []
    for k in range(0, len(polys), steps):
        strip = polys[k:k + steps]
        left = [strip[0][0]] + [q[3] for q in strip]
        right = [strip[0][1]] + [q[2] for q in strip]
        out.append(tuple(left[:1] + right + list(reversed(left[1:]))))
    return out


def _inset_group(mesh: Mesh, group: list[int], normals: np.ndarray, dist: float, steps: int):
    owner = _owner_map(mesh, group)
    corner_of: dict[tuple[int, int], tuple[int, int]] = {}
    in_face: dict[tuple[int, int], int] = {}
    for f in group:
        for v in mesh.polygons[f]:
            found = _incoming(mesh, owner, f, v)
            if found is not None:
                corner_of[(f, v)] = found[0]
                in_face.setdefault(found[0], found[1])
    rings: dict[tuple[int, int], list[int]] = {}
    for key, f_in in in_face.items():
        v = key[1]
        out_edge, f_out = _outgoing(mesh, owner, f_in, v)
        d = _miter(_inward(mesh, normals, key, f_in), _inward(mesh, normals, out_edge, f_out))
        base = mesh.points[v].copy()
        rings[key] = [v] + [mesh.add_point(base + d * dist * s / steps) for s in range(1, steps + 1)]
    sides: list[tuple[int, ...]] = []
    for u, v in region_boundary(mesh, group):
        f = owner[(u, v)]
        ru, rv = rings[corner_of[(f, u)]], rings[corner_of[(f, v)]]
        for s in range(steps):
            sides.append((ru[s], rv[s], rv[s + 1], ru[s + 1]))
    for f in group:
        mesh.polygons[f] = tuple(rings[corner_of[(f, v)]][-1] if (f, v) in corner_of else v
                                 for v in mesh.polygons[f])
    return sides


def inset(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    free = _free_points(mesh)
    if sel.mode != "polygons":
        return OpResult(mesh, sel, False, "Inset works in polygons mode")
    faces = _selected_faces(mesh, sel)
    if not faces:
        return OpResult(mesh, sel, False, "Inset: no polygons selected")
    steps = max(1, int(p["subdivision"]))
    rng = _rng(p)
    normals = face_normals(mesh)
    groups = face_groups(mesh, faces, float(p["max_angle"])) if p["preserve_groups"] else [[f] for f in faces]
    sides: list[tuple[int, ...]] = []
    for group in groups:
        dist = float(p["offset"]) + _variance(rng, float(p["variance"]))
        strip = _inset_group(mesh, group, normals, dist, steps)
        sides.extend(_merge_strips(strip, steps) if p["create_ngons"] else strip)
    mesh.polygons.extend(sides)
    mesh = _finish(mesh, free)
    return OpResult(mesh, Selection("polygons", polygons=set(faces)))


class _Union:

    def __init__(self) -> None:
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _angle(n0: np.ndarray, n1: np.ndarray) -> float:
    return math.degrees(math.acos(float(np.clip(n0 @ n1, -1.0, 1.0))))


def _corner_clusters(mesh: Mesh, group: list[int], owner: dict, normals: np.ndarray, max_angle: float) -> _Union:
    uf = _Union()
    for f in group:
        for v in mesh.polygons[f]:
            uf.find((f, v))
        for a, b in directed_edges(mesh.polygons[f]):
            g = owner.get((b, a))
            if g is not None and _angle(normals[f], normals[g]) <= max_angle + 1e-9:
                uf.join((f, a), (g, a))
                uf.join((f, b), (g, b))
    return uf


def _cluster_members(uf: _Union) -> dict:
    members: dict = {}
    for corner in list(uf.parent):
        members.setdefault(uf.find(corner), []).append(corner)
    return members


def _cluster_direction(normals: np.ndarray, corners) -> np.ndarray:
    uniq: list[np.ndarray] = []
    for f, _ in corners:
        if not any(float(normals[f] @ u) > 1 - 1e-9 for u in uniq):
            uniq.append(normals[f])
    d = _unit(np.sum(uniq, axis=0))
    if float(np.linalg.norm(d)) > 0:
        c = min(float(d @ n) for n in uniq)
        d = d / c if c > 0.05 else d
    return d


def _cluster_points(mesh: Mesh, uf: _Union, normals: np.ndarray, dist: float):
    new_of: dict[tuple[int, int], int] = {}
    family: dict[int, int] = {}
    for root, corners in _cluster_members(uf).items():
        v = root[1]
        q = mesh.add_point(mesh.points[v] + _cluster_direction(normals, corners) * dist)
        family[q] = v
        for corner in corners:
            new_of[corner] = q
    return new_of, family


def _ring(points) -> tuple[int, ...] | None:
    out: list[int] = []
    for i in points:
        if not out or out[-1] != i:
            out.append(i)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return tuple(out) if len(out) >= 3 and len(set(out)) == len(out) else None


def _shift_walls(mesh: Mesh, group: list[int], owner: dict, new_of: dict) -> list[tuple[int, ...]]:
    walls: list[tuple[int, ...]] = []
    for f in group:
        for u, v in directed_edges(mesh.polygons[f]):
            g = owner.get((v, u))
            fu, fv = new_of[(f, u)], new_of[(f, v)]
            if g is None:
                walls.append((u, v, fv, fu))
                continue
            if u > v:
                continue
            gu, gv = new_of[(g, u)], new_of[(g, v)]
            if fu == gu and fv == gv:
                continue
            ring = _ring((fv, fu, gu, gv))
            if ring is not None:
                walls.append(ring)
    return walls


def _corner_fills(walls: list[tuple[int, ...]], family: dict[int, int]) -> list[tuple[int, ...]]:
    fam = lambda i: family.get(i, i)
    present = {(a, b) for w in walls for a, b in directed_edges(w) if a != b and fam(a) == fam(b)}
    nxt: dict[int, int] = {}
    for a, b in present:
        if (b, a) in present:
            continue
        if b in nxt:
            return []
        nxt[b] = a
    fills: list[tuple[int, ...]] = []
    seen: set[int] = set()
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
            fills.append(tuple(loop))
    return fills


def smooth_shift(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    free = _free_points(mesh)
    if sel.mode != "polygons":
        return OpResult(mesh, sel, False, "Smooth Shift works in polygons mode")
    faces = _selected_faces(mesh, sel)
    if not faces:
        return OpResult(mesh, sel, False, "Smooth Shift: no polygons selected")
    rng = _rng(p)
    normals = face_normals(mesh)
    groups = face_groups(mesh, faces) if p["preserve_groups"] else [[f] for f in faces]
    added: list[tuple[int, ...]] = []
    for group in groups:
        dist = float(p["offset"]) + _variance(rng, float(p["variance"]))
        owner = _owner_map(mesh, group)
        uf = _corner_clusters(mesh, group, owner, normals, float(p["max_angle"]))
        new_of, family = _cluster_points(mesh, uf, normals, dist)
        walls = _shift_walls(mesh, group, owner, new_of)
        added.extend(walls)
        added.extend(_corner_fills(walls, family))
        for f in group:
            mesh.polygons[f] = tuple(new_of[(f, v)] for v in mesh.polygons[f])
    mesh.polygons.extend(added)
    mesh = _finish(mesh, free)
    return OpResult(mesh, Selection("polygons", polygons=set(faces)))


THICKEN_DIRECTIONS = ("Normal", "Inverse", "Both")


def _thicken_span(direction: str, thickness: float) -> tuple[float, float]:
    if direction == "Inverse":
        return -thickness, 0.0
    if direction == "Both":
        return -thickness / 2.0, thickness / 2.0
    return 0.0, thickness


def _thicken_faces(mesh: Mesh, sel: Selection) -> list[int]:
    faces = _selected_faces(mesh, sel) if sel.mode == "polygons" else []
    return faces or list(range(len(mesh.polygons)))


def _thicken_layers(mesh: Mesh, dirs: dict, rim: set, span: tuple[float, float], steps: int) -> list[dict]:
    back, front = span
    layers: list[dict] = []
    for s in range(steps + 1):
        depth = back + (front - back) * s / steps
        use = dirs if s in (0, steps) else {r: dirs[r] for r in rim}
        layers.append({r: mesh.add_point(mesh.points[r[1]] + d * depth) for r, d in use.items()})
    return layers


def thicken(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    free = _free_points(mesh)
    if sel.mode not in ("polygons", "model"):
        return OpResult(mesh, sel, False, "Thicken works in polygons or model mode")
    faces = _thicken_faces(mesh, sel)
    if not faces:
        return OpResult(mesh, sel, False, "Thicken: the object has no polygons")
    steps = max(1, int(p["subdivision"]))
    normals = face_normals(mesh)
    owner = _owner_map(mesh, faces)
    uf = _corner_clusters(mesh, faces, owner, normals, 180.0)
    dirs = {root: _cluster_direction(normals, corners) for root, corners in _cluster_members(uf).items()}
    boundary = [(uf.find((f, u)), uf.find((f, v))) for f in faces
                for u, v in directed_edges(mesh.polygons[f]) if (v, u) not in owner] if p["create_caps"] else []
    rim = {r for e in boundary for r in e}
    layers = _thicken_layers(mesh, dirs, rim, _thicken_span(str(p["direction"]), float(p["thickness"])), steps)
    original = {f: tuple(mesh.polygons[f]) for f in faces}
    for f in faces:
        mesh.polygons[f] = tuple(layers[-1][uf.find((f, v))] for v in original[f])
    for f in faces:
        mesh.polygons.append(tuple(layers[0][uf.find((f, v))] for v in reversed(original[f])))
    for ru, rv in boundary:
        for s in range(steps):
            lo, hi = layers[s], layers[s + 1]
            mesh.polygons.append((lo[ru], lo[rv], hi[rv], hi[ru]))
    mesh = _finish(mesh, free)
    if sel.mode == "model":
        return OpResult(mesh, Selection("model"))
    return OpResult(mesh, Selection("polygons", polygons=set(faces)))


MATRIX_VARIANCE = ("None", "Initial", "Per Step")


def _polygon_frame(mesh: Mesh, poly: tuple[int, ...], normal: np.ndarray) -> np.ndarray:
    z = _unit(normal)
    if not np.any(z):
        return np.eye(3)
    edge = mesh.points[poly[1]] - mesh.points[poly[0]]
    x = _unit(edge - z * float(edge @ z))
    if not np.any(x):
        x = _unit(np.cross(z, [0.0, 1.0, 0.0] if abs(z[1]) < 0.9 else [1.0, 0.0, 0.0]))
    return np.column_stack([x, np.cross(z, x), z])


def _hpb(h: float, p: float, b: float) -> np.ndarray:
    h, p, b = (math.radians(x) for x in (h, p, b))
    ch, sh, cp, sp, cb, sb = math.cos(h), math.sin(h), math.cos(p), math.sin(p), math.cos(b), math.sin(b)
    ry = np.array([[ch, 0.0, sh], [0.0, 1.0, 0.0], [-sh, 0.0, ch]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]])
    rz = np.array([[cb, -sb, 0.0], [sb, cb, 0.0], [0.0, 0.0, 1.0]])
    return ry @ rx @ rz


def _sample(rng: random.Random, lo, hi) -> np.ndarray:
    return np.array([rng.uniform(min(a, b), max(a, b)) for a, b in zip(lo, hi)], float)


def _step_values(p: dict, rng: random.Random):
    if p["variance"] == "None":
        return np.array(p["move"], float), np.array(p["scale"], float), np.array(p["rotate"], float)
    return (_sample(rng, p["move"], p["move_max"]), _sample(rng, p["scale"], p["scale_max"]),
            _sample(rng, p["rotate"], p["rotate_max"]))


def _matrix_polygon(mesh: Mesh, f: int, normal: np.ndarray, p: dict, rng: random.Random) -> list[tuple[int, ...]]:
    ring = list(mesh.polygons[f])
    frame = _polygon_frame(mesh, tuple(ring), normal) if p["polygon_coordinates"] else np.eye(3)
    center = mesh.points[ring].mean(axis=0)
    values = _step_values(p, rng)
    walls: list[tuple[int, ...]] = []
    for _ in range(int(p["steps"])):
        if p["variance"] == "Per Step":
            values = _step_values(p, rng)
        move, scale, rotate = values
        rot = _hpb(*rotate)
        local = (mesh.points[ring] - center) @ frame
        moved = (rot @ (local * (scale / 100.0)).T).T
        center = center + frame @ move
        world = center + moved @ frame.T
        new = [mesh.add_point(q) for q in world]
        n = len(ring)
        for j in range(n):
            k = (j + 1) % n
            walls.append((ring[j], ring[k], new[k], new[j]))
        ring = new
        if p["polygon_coordinates"]:
            frame = frame @ rot
    mesh.polygons[f] = tuple(ring)
    return walls


def matrix_extrude(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    free = _free_points(mesh)
    if sel.mode != "polygons":
        return OpResult(mesh, sel, False, "Matrix Extrude works in polygons mode")
    faces = _selected_faces(mesh, sel)
    if not faces:
        return OpResult(mesh, sel, False, "Matrix Extrude: no polygons selected")
    if int(p["steps"]) < 1:
        return OpResult(mesh, sel, False, "Matrix Extrude: Steps must be at least 1")
    rng = _rng(p)
    normals = face_normals(mesh)
    walls: list[tuple[int, ...]] = []
    for f in faces:
        walls.extend(_matrix_polygon(mesh, f, normals[f], p, rng))
    mesh.polygons.extend(walls)
    mesh = _finish(mesh, free)
    return OpResult(mesh, Selection("polygons", polygons=set(faces)))


register(ToolSpec(
    id="inset",
    name="Inset",
    apply=inset,
    modes=("polygons",),
    params=(
        Param("max_angle", "Maximum Angle", "angle", 89.0, 0.0, 180.0, 1.0, "°"),
        Param("offset", "Offset", "distance", 5.0, -1e6, 1e6, 1.0, "cm"),
        Param("variance", "Variance", "distance", 0.0, 0.0, 1e6, 1.0, "cm"),
        Param("subdivision", "Subdivision", "int", 1, 1, 1000, 1),
        Param("create_ngons", "Create N-gons", "bool", False),
        Param("preserve_groups", "Preserve Groups", "bool", True),
    ),
    interactive=True,
    drag_param="offset",
    drag_kind="distance",
    section="CREATION TOOLS",
    shortcut="M~W",
    description="Insets the selected polygons inside their own surface, framing them with a ring of new polygons.",
))

register(ToolSpec(
    id="smooth_shift",
    name="Smooth Shift",
    apply=smooth_shift,
    modes=("polygons",),
    params=(
        Param("max_angle", "Maximum Angle", "angle", 89.0, 0.0, 180.0, 1.0, "°"),
        Param("offset", "Offset", "distance", 5.0, -1e6, 1e6, 1.0, "cm"),
        Param("variance", "Variance", "distance", 0.0, 0.0, 1e6, 1.0, "cm"),
        Param("preserve_groups", "Preserve Groups", "bool", True),
    ),
    interactive=True,
    drag_param="offset",
    drag_kind="distance",
    section="CREATION TOOLS",
    shortcut="M~Y",
    description="Extrudes the selected polygons and fills the gaps between neighbours steeper than the Maximum Angle with new polygons.",
))

register(ToolSpec(
    id="thicken",
    name="Thicken",
    apply=thicken,
    modes=("polygons", "model"),
    params=(
        Param("thickness", "Thickness", "distance", 10.0, 0.0, 1e6, 1.0, "cm"),
        Param("subdivision", "Subdivision", "int", 1, 1, 1000, 1),
        Param("direction", "Direction", "choice", "Normal", choices=THICKEN_DIRECTIONS),
        Param("create_caps", "Create Caps", "bool", True),
    ),
    interactive=True,
    drag_param="thickness",
    drag_kind="distance",
    section="CREATION TOOLS",
    shortcut=None,
    description="Turns the selected polygons, or the whole object, into a solid shell of the given thickness.",
))

register(ToolSpec(
    id="matrix_extrude",
    name="Matrix Extrude",
    apply=matrix_extrude,
    modes=("polygons",),
    params=(
        Param("steps", "Steps", "int", 5, 1, 1000, 1),
        Param("polygon_coordinates", "Polygon Coordinates", "bool", True),
        Param("variance", "Variance", "choice", "None", choices=MATRIX_VARIANCE),
        Param("move", "Move", "vector", (0.0, 0.0, 5.0), unit="cm"),
        Param("scale", "Scale", "vector", (90.0, 90.0, 90.0), unit="%"),
        Param("rotate", "Rotate", "vector", (0.0, 0.0, 0.0), unit="°"),
        Param("move_max", "Move Max", "vector", (0.0, 0.0, 10.0), unit="cm"),
        Param("scale_max", "Scale Max", "vector", (100.0, 100.0, 100.0), unit="%"),
        Param("rotate_max", "Rotate Max", "vector", (10.0, 10.0, 10.0), unit="°"),
    ),
    interactive=True,
    drag_param=None,
    drag_kind="count",
    section="CREATION TOOLS",
    shortcut="M~X",
    description="Repeats extrude, scale and rotate steps on each selected polygon, building tentacle-like chains.",
    extra={"variance_params": {"Initial": ("move_max", "scale_max", "rotate_max"),
                               "Per Step": ("move_max", "scale_max", "rotate_max")}},
))
