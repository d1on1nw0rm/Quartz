from __future__ import annotations

import math

import numpy as np

from ..scene import Mesh, rotation_matrix
from .registry import ObjectSpec, Param, register

MAX_CLONES = 2000
MAX_CELLS = 70000
MAX_BALLS = 256
SAMPLES_PER_CHILD = 48
FALLOFF_AT_RADIUS = 0.75 ** 3

CLONER_MODES = ("Linear", "Radial", "Grid Array")
CLONER_PLANES = ("XY", "ZY", "XZ")
CLONER_CLONES = ("Iterate", "Random", "Blend", "Sort")
FRACTURE_MODES = ("Straight", "Explode Segments", "Explode Segments and Connect")

TETS = ((0, 1, 3, 7), (0, 1, 5, 7), (0, 2, 3, 7), (0, 2, 6, 7), (0, 4, 5, 7), (0, 4, 6, 7))


class _Acc:

    def __init__(self) -> None:
        self.points: list[np.ndarray] = []
        self.polygons: list[tuple[int, ...]] = []
        self.loose: list[tuple[int, int]] = []
        self.offset = 0

    def add(self, points: np.ndarray, polygons, loose) -> None:
        o = self.offset
        self.points.append(np.asarray(points, float).reshape(-1, 3))
        self.polygons.extend(tuple(i + o for i in poly) for poly in polygons)
        self.loose.extend((a + o, b + o) for a, b in loose)
        self.offset += len(points)

    def mesh(self) -> Mesh:
        if not self.points or self.offset == 0:
            return Mesh.empty()
        return Mesh(np.vstack(self.points), self.polygons, self.loose)


def _usable(inputs: list) -> list:
    return [i for i in inputs if len(i.mesh.points) > 0]


def _pivot(inp) -> np.ndarray:
    return np.asarray(inp.matrix, float)[:3, 3].copy()


def _placed(mesh: Mesh, pivot: np.ndarray, rot: np.ndarray, scl: np.ndarray,
            trans: np.ndarray) -> np.ndarray:
    return pivot + ((mesh.points - pivot) * scl) @ rot.T + trans


def _add_clone(acc: _Acc, inp, rot: np.ndarray, scl: np.ndarray, trans: np.ndarray) -> None:
    mesh = inp.mesh
    acc.add(_placed(mesh, _pivot(inp), rot, scl, trans), mesh.polygons, mesh.loose_edges)


def _same_topology(kids: list) -> bool:
    first = kids[0].mesh
    return all(len(k.mesh.points) == len(first.points) and list(k.mesh.polygons) == list(first.polygons)
               and list(k.mesh.loose_edges) == list(first.loose_edges) for k in kids[1:])


def _add_blend(acc: _Acc, a, b, f: float, rot: np.ndarray, scl: np.ndarray,
               trans: np.ndarray) -> None:
    pts = (1.0 - f) * a.mesh.points + f * b.mesh.points
    pivot = (1.0 - f) * _pivot(a) + f * _pivot(b)
    acc.add(pivot + ((pts - pivot) * scl) @ rot.T + trans, a.mesh.polygons, a.mesh.loose_edges)


def _cloner_steps(p: dict) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    mode = p["mode"]
    steps: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    if mode == "Linear":
        n = int(p["linear_count"])
        pos = np.array(p["linear_position"], float)
        scl = np.array(p["linear_scale"], float) / 100.0
        h, pit, b = (float(v) for v in p["linear_rotation"])
        for i in range(n):
            steps.append((rotation_matrix((pit * i, h * i, b * i)), scl ** i, pos * i))
    elif mode == "Radial":
        n = int(p["radial_count"])
        r = float(p["radial_radius"])
        a0, a1 = float(p["radial_start"]), float(p["radial_end"])
        plane = p["radial_plane"]
        full = abs(a1 - a0) >= 360.0 - 1e-9
        for i in range(n):
            if n == 1:
                deg = a0
            elif full:
                deg = a0 + (a1 - a0) * i / n
            else:
                deg = a0 + (a1 - a0) * i / (n - 1)
            a = math.radians(deg)
            c, s = math.cos(a) * r, math.sin(a) * r
            if plane == "XY":
                pos, turn = (c, s, 0.0), (0.0, 0.0, deg)
            elif plane == "ZY":
                pos, turn = (0.0, s, c), (-deg, 0.0, 0.0)
            else:
                pos, turn = (c, 0.0, s), (0.0, -deg, 0.0)
            rot = rotation_matrix(turn) if p["radial_align"] else np.eye(3)
            steps.append((rot, np.ones(3), np.array(pos, float)))
    else:
        nx, ny, nz = (int(round(v)) for v in p["grid_count"])
        sx, sy, sz = (float(v) for v in p["grid_size"])

        def axis(n: int, size: float) -> np.ndarray:
            return np.zeros(1) if n == 1 else np.linspace(-size / 2.0, size / 2.0, n)

        xs, ys, zs = axis(nx, sx), axis(ny, sy), axis(nz, sz)
        for z in zs:
            for y in ys:
                for x in xs:
                    steps.append((np.eye(3), np.ones(3), np.array((x, y, z), float)))
    return steps[:MAX_CLONES]


def build_cloner(p: dict, inputs: list) -> Mesh:
    kids = _usable(inputs)
    if not kids:
        return Mesh.empty()
    acc = _Acc()
    steps = _cloner_steps(p)
    count = len(steps)
    n = len(kids)
    how = p["clones"]
    if how == "Blend" and n > 1 and _same_topology(kids):
        for k, (rot, scl, trans) in enumerate(steps):
            pos = k / (count - 1) * (n - 1) if count > 1 else 0.0
            i = min(int(pos), n - 2)
            _add_blend(acc, kids[i], kids[i + 1], pos - i, rot, scl, trans)
        return acc.mesh()
    if how == "Random":
        picks = np.random.default_rng(int(p["seed"])).integers(0, n, count).tolist()
    elif how == "Sort":
        picks = [min(n - 1, k * n // count) for k in range(count)]
    else:
        picks = [k % n for k in range(count)]
    for pick, (rot, scl, trans) in zip(picks, steps):
        _add_clone(acc, kids[pick], rot, scl, trans)
    return acc.mesh()


def build_array(p: dict, inputs: list) -> Mesh:
    kids = _usable(inputs)
    if not kids:
        return Mesh.empty()
    n = int(p["copies"])
    radius, amp, freq = float(p["radius"]), float(p["amplitude"]), float(p["frequency"])
    acc = _Acc()
    for i in range(n):
        a = 2.0 * math.pi * i / n
        y = amp * math.sin(2.0 * math.pi * freq * i / n)
        rot = rotation_matrix((0.0, -math.degrees(a), 0.0))
        trans = np.array((radius * math.cos(a), y, radius * math.sin(a)), float)
        for inp in kids:
            _add_clone(acc, inp, rot, np.ones(3), trans)
    return acc.mesh()


def _components(mesh: Mesh) -> list[tuple[np.ndarray, list[tuple[int, ...]], list[tuple[int, int]]]]:
    n = len(mesh.points)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    used = set()
    for poly in mesh.polygons:
        used.update(poly)
        for i in poly[1:]:
            union(poly[0], i)
    for a, b in mesh.loose_edges:
        used.update((a, b))
        union(a, b)
    groups: dict[int, list[int]] = {}
    for i in sorted(used):
        groups.setdefault(find(i), []).append(i)
    polys: dict[int, list[tuple[int, ...]]] = {}
    for poly in mesh.polygons:
        polys.setdefault(find(poly[0]), []).append(poly)
    loose: dict[int, list[tuple[int, int]]] = {}
    for a, b in mesh.loose_edges:
        loose.setdefault(find(a), []).append((a, b))
    out = []
    for root in sorted(groups):
        idx = groups[root]
        remap = {old: new for new, old in enumerate(idx)}
        out.append((mesh.points[idx],
                    [tuple(remap[i] for i in poly) for poly in polys.get(root, [])],
                    [(remap[a], remap[b]) for a, b in loose.get(root, [])]))
    return out


def _weld(mesh: Mesh, tolerance: float = 1e-5) -> Mesh:
    if len(mesh.points) == 0:
        return mesh
    keys = np.round(mesh.points / tolerance).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    order = np.argsort(first, kind="stable")
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order))
    new_index = rank[inverse]
    points = mesh.points[first[order]]
    polygons = []
    for poly in mesh.polygons:
        ring: list[int] = []
        for i in poly:
            j = int(new_index[i])
            if not ring or ring[-1] != j:
                ring.append(j)
        while len(ring) > 1 and ring[0] == ring[-1]:
            ring.pop()
        if len(ring) >= 3 and len(set(ring)) == len(ring):
            polygons.append(tuple(ring))
    loose = [(int(new_index[a]), int(new_index[b])) for a, b in mesh.loose_edges
             if new_index[a] != new_index[b]]
    keep = sorted({i for poly in polygons for i in poly} | {i for e in loose for i in e})
    remap = {old: new for new, old in enumerate(keep)}
    return Mesh(points[keep], [tuple(remap[i] for i in poly) for poly in polygons],
                [(remap[a], remap[b]) for a, b in loose])


def build_fracture(p: dict, inputs: list) -> Mesh:
    kids = _usable(inputs)
    if not kids:
        return Mesh.empty()
    mode = p["mode"]
    if mode == "Straight":
        acc = _Acc()
        for inp in kids:
            acc.add(inp.mesh.points, inp.mesh.polygons, inp.mesh.loose_edges)
        return acc.mesh()
    parts = []
    for inp in kids:
        parts.extend(_components(inp.mesh))
    if not parts:
        return Mesh.empty()
    every = np.vstack([part[0] for part in parts])
    centre = (every.min(axis=0) + every.max(axis=0)) / 2.0
    offset = float(p["offset"])
    acc = _Acc()
    for pts, polys, loose in parts:
        mid = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
        d = mid - centre
        length = float(np.linalg.norm(d))
        shift = d / length * offset if length > 1e-9 else np.zeros(3)
        acc.add(pts + shift, polys, loose)
    mesh = acc.mesh()
    if mode == "Explode Segments and Connect":
        return _weld(mesh)
    return mesh


def _ball_list(inputs: list) -> list[tuple[np.ndarray, float]]:
    per_child = min(SAMPLES_PER_CHILD, max(8, MAX_BALLS // max(1, len(inputs))))
    balls: list[tuple[np.ndarray, float]] = []
    for inp in inputs:
        pts = inp.mesh.points
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        centre = (lo + hi) / 2.0
        bound = float(np.max(np.linalg.norm(pts - centre, axis=1)))
        if bound < 1e-6:
            continue
        if "sphere" in str(inp.kind).lower():
            balls.append((centre, float(np.max(hi - lo)) / 2.0))
            continue
        sample = _farthest_points(pts, per_child)
        radius = 0.6 * bound / max(1.0, (len(sample) / 8.0) ** (1.0 / 3.0))
        for q in sample:
            balls.append((q.copy(), radius))
        if len(sample) > 1:
            balls.append((centre, 0.6 * bound))
    return balls


def _farthest_points(pts: np.ndarray, count: int) -> np.ndarray:
    if len(pts) <= count:
        return pts
    chosen = [0]
    dist = np.linalg.norm(pts - pts[0], axis=1)
    for _ in range(count - 1):
        k = int(np.argmax(dist))
        chosen.append(k)
        dist = np.minimum(dist, np.linalg.norm(pts - pts[k], axis=1))
    return pts[chosen]


def _field(balls: list[tuple[np.ndarray, float]], origin: np.ndarray, cell: float,
           shape: tuple[int, int, int]) -> np.ndarray:
    xs = origin[0] + cell * np.arange(shape[0])
    ys = origin[1] + cell * np.arange(shape[1])
    zs = origin[2] + cell * np.arange(shape[2])
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    field = np.zeros(shape)
    for centre, radius in balls:
        reach = 2.0 * radius
        d2 = (gx - centre[0]) ** 2 + (gy - centre[1]) ** 2 + (gz - centre[2]) ** 2
        t = 1.0 - d2 / (reach * reach)
        np.maximum(t, 0.0, out=t)
        field += t ** 3
    return field


def _polygonise(field: np.ndarray, origin: np.ndarray, cell: float, iso: float) -> Mesh:
    nx, ny, nz = field.shape
    total = nx * ny * nz
    ids = np.arange(total, dtype=np.int64).reshape(field.shape)
    flat = field.reshape(-1)
    cx, cy, cz = nx - 1, ny - 1, nz - 1
    corner_ids, corner_vals = [], []
    for c in range(8):
        ox, oy, oz = c & 1, (c >> 1) & 1, (c >> 2) & 1
        sl = (slice(ox, ox + cx), slice(oy, oy + cy), slice(oz, oz + cz))
        corner_ids.append(ids[sl].reshape(-1))
        corner_vals.append(field[sl].reshape(-1))
    vals = np.stack(corner_vals, axis=1)
    inside_all = vals >= iso
    mixed = inside_all.any(axis=1) & ~inside_all.all(axis=1)
    if not mixed.any():
        return Mesh.empty()
    gid = np.stack(corner_ids, axis=1)[mixed]
    tet_ids = np.concatenate([gid[:, list(t)] for t in TETS], axis=0)
    tet_in = np.concatenate([(vals[mixed] >= iso)[:, list(t)] for t in TETS], axis=0)
    count = tet_in.sum(axis=1)
    keep = (count >= 1) & (count <= 3)
    tet_ids, tet_in, count = tet_ids[keep], tet_in[keep], count[keep]
    order = np.argsort(~tet_in, axis=1, kind="stable")
    tet_ids = np.take_along_axis(tet_ids, order, axis=1)

    def grid_pos(g: np.ndarray) -> np.ndarray:
        ix, rest = np.divmod(g, ny * nz)
        iy, iz = np.divmod(rest, nz)
        return origin + cell * np.stack([ix, iy, iz], axis=-1).astype(float)

    edge_keys: list[np.ndarray] = []
    tri_tet: list[np.ndarray] = []
    patterns = {1: ([(0, 1), (0, 2), (0, 3)],),
                3: ([(0, 3), (1, 3), (2, 3)],),
                2: ([(0, 2), (0, 3), (1, 3)], [(0, 2), (1, 3), (1, 2)])}
    for n_in, tris in patterns.items():
        sel = np.nonzero(count == n_in)[0]
        if len(sel) == 0:
            continue
        for tri in tris:
            cols = []
            for u, v in tri:
                a, b = tet_ids[sel, u], tet_ids[sel, v]
                lo, hi = np.minimum(a, b), np.maximum(a, b)
                cols.append(lo * total + hi)
            edge_keys.append(np.stack(cols, axis=1))
            tri_tet.append(sel)
    keys = np.concatenate(edge_keys, axis=0)
    owner = np.concatenate(tri_tet)
    unique, inverse = np.unique(keys.reshape(-1), return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1, 3)
    lo, hi = unique // total, unique % total
    flo, fhi = flat[lo], flat[hi]
    t = np.clip((iso - flo) / (fhi - flo), 0.02, 0.98)
    plo, phi = grid_pos(lo), grid_pos(hi)
    points = plo + (phi - plo) * t[:, None]
    tri = inverse
    inside_pos = grid_pos(tet_ids)
    weights_in = (np.arange(4)[None, :] < count[:, None]).astype(float)
    weights_out = 1.0 - weights_in
    mean_in = (inside_pos * weights_in[:, :, None]).sum(axis=1) / weights_in.sum(axis=1)[:, None]
    mean_out = (inside_pos * weights_out[:, :, None]).sum(axis=1) / weights_out.sum(axis=1)[:, None]
    toward_out = (mean_out - mean_in)[owner]
    p0, p1, p2 = points[tri[:, 0]], points[tri[:, 1]], points[tri[:, 2]]
    normal = np.cross(p1 - p0, p2 - p0)
    area = np.linalg.norm(normal, axis=1)
    flip = np.einsum("ij,ij->i", normal, toward_out) < 0.0
    tri = np.where(flip[:, None], tri[:, ::-1], tri)
    good = (area > 1e-9) & (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    tri = tri[good]
    if len(tri) == 0:
        return Mesh.empty()
    used, remap = np.unique(tri.reshape(-1), return_inverse=True)
    return Mesh(points[used], [tuple(int(i) for i in row) for row in remap.reshape(-1, 3)])


def build_metaball(p: dict, inputs: list) -> Mesh:
    kids = _usable(inputs)
    if not kids:
        return Mesh.empty()
    balls = _ball_list(kids)
    if not balls:
        return Mesh.empty()
    iso = FALLOFF_AT_RADIUS * float(p["hull_value"]) / 100.0
    cell = max(2.0, float(p["editor_subdivision"]))
    lo = np.min([c - 2.0 * r for c, r in balls], axis=0)
    hi = np.max([c + 2.0 * r for c, r in balls], axis=0)
    lo, hi = lo - cell, hi + cell
    for _ in range(4):
        dims = np.maximum(np.ceil((hi - lo) / cell).astype(int), 1)
        cells = int(np.prod(dims))
        if cells <= MAX_CELLS:
            break
        cell *= (cells / MAX_CELLS) ** (1.0 / 3.0) * 1.02
    dims = np.maximum(np.ceil((hi - lo) / cell).astype(int), 1)
    shape = (int(dims[0]) + 1, int(dims[1]) + 1, int(dims[2]) + 1)
    field = _field(balls, lo, cell, shape)
    return _polygonise(field, lo, cell, iso)


register(ObjectSpec(
    id="cloner", label="Cloner", category="generator", build=build_cloner, inputs="children",
    icon="cloner",
    params=(
        Param("mode", "Mode", "choice", "Linear", choices=CLONER_MODES, group="Object"),
        Param("clones", "Clones", "choice", "Iterate", choices=CLONER_CLONES, group="Object"),
        Param("seed", "Seed", "int", 1234567, minimum=0, maximum=2147483647, group="Object"),
        Param("linear_count", "Count", "int", 3, minimum=1, maximum=MAX_CLONES, group="Linear"),
        Param("linear_position", "Position", "vector", (0.0, 50.0, 0.0), group="Linear",
              unit="cm"),
        Param("linear_scale", "Scale", "vector", (100.0, 100.0, 100.0), minimum=1.0,
              maximum=10000.0, group="Linear", unit="%"),
        Param("linear_rotation", "Rotation (H, P, B)", "vector", (0.0, 0.0, 0.0), group="Linear",
              unit="deg"),
        Param("radial_count", "Count", "int", 5, minimum=1, maximum=MAX_CLONES, group="Radial"),
        Param("radial_radius", "Radius", "distance", 50.0, minimum=0.0, group="Radial"),
        Param("radial_plane", "Plane", "choice", "XZ", choices=CLONER_PLANES, group="Radial"),
        Param("radial_start", "Start Angle", "angle", 0.0, group="Radial"),
        Param("radial_end", "End Angle", "angle", 360.0, group="Radial"),
        Param("radial_align", "Align", "bool", True, group="Radial"),
        Param("grid_count", "Count (X, Y, Z)", "vector", (3.0, 1.0, 3.0), minimum=1.0,
              maximum=100.0, group="Grid Array"),
        Param("grid_size", "Size (X, Y, Z)", "vector", (200.0, 200.0, 200.0), minimum=0.0,
              group="Grid Array", unit="cm"))))

register(ObjectSpec(
    id="array", label="Array", category="generator", build=build_array, inputs="children",
    icon="array",
    params=(
        Param("radius", "Radius", "distance", 250.0, minimum=0.0, group="Object"),
        Param("copies", "Copies", "int", 7, minimum=1, maximum=500, group="Object"),
        Param("amplitude", "Amplitude", "distance", 0.0, group="Object"),
        Param("frequency", "Frequency", "float", 0.0, group="Object"))))

register(ObjectSpec(
    id="fracture", label="Fracture", category="generator", build=build_fracture, inputs="children",
    icon="fracture",
    params=(
        Param("mode", "Mode", "choice", "Straight", choices=FRACTURE_MODES, group="Object"),
        Param("offset", "Offset", "distance", 0.0, group="Object"))))

register(ObjectSpec(
    id="metaball", label="Metaball", category="generator", build=build_metaball, inputs="children",
    icon="metaball",
    params=(
        Param("hull_value", "Hull Value", "percent", 100.0, minimum=10.0, maximum=200.0,
              group="Object"),
        Param("editor_subdivision", "Editor Subdivision", "distance", 20.0, minimum=2.0,
              maximum=1000.0, group="Object"))))
