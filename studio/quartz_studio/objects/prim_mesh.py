from __future__ import annotations

import math

import numpy as np

from ..modeling import primitives as prim
from ..modeling.meshkit import clean_polygons
from ..scene import Mesh
from .registry import ObjectSpec, Param, register

ORIENTATIONS = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
ORIENT_MAPS = {
    "+Y": ((0, 1.0), (1, 1.0), (2, 1.0)),
    "-Y": ((0, -1.0), (1, -1.0), (2, 1.0)),
    "+X": ((1, 1.0), (0, -1.0), (2, 1.0)),
    "-X": ((1, -1.0), (0, 1.0), (2, 1.0)),
    "+Z": ((0, 1.0), (2, -1.0), (1, 1.0)),
    "-Z": ((0, 1.0), (2, 1.0), (1, -1.0)),
}
SPHERE_TYPES = ("Standard", "Tetrahedron", "Hexahedron", "Octahedron", "Icosahedron", "Hemisphere")
PLATONIC_TYPES = {
    "Tetra": "Tetrahedron",
    "Hexa": "Hexahedron",
    "Octa": "Octahedron",
    "Dodeca": "Dodecahedron",
    "Icosa": "Icosahedron",
    "Soccer": "Bucky",
}
DISTANCE_MAX = 1000000.0
SEGMENTS_MAX = 100
ROTATION_MAX = 128
GEODESIC_MAX = 16
TAU = 2.0 * math.pi
PHI = (1.0 + 5.0 ** 0.5) / 2.0


class _Builder:

    def __init__(self) -> None:
        self.points: list[tuple[float, float, float]] = []
        self.index: dict[tuple[float, float, float], int] = {}
        self.polygons: list[tuple[int, ...]] = []

    def vertex(self, p) -> int:
        x, y, z = (float(c) for c in p)
        key = (round(x, 9), round(y, 9), round(z, 9))
        found = self.index.get(key)
        if found is None:
            found = len(self.points)
            self.index[key] = found
            self.points.append((x, y, z))
        return found

    def face(self, ids, hint=None) -> None:
        ids = list(ids)
        pts = np.array([self.points[i] for i in ids], float)
        nxt = np.roll(pts, -1, axis=0)
        normal = np.array([
            np.sum((pts[:, 1] - nxt[:, 1]) * (pts[:, 2] + nxt[:, 2])),
            np.sum((pts[:, 2] - nxt[:, 2]) * (pts[:, 0] + nxt[:, 0])),
            np.sum((pts[:, 0] - nxt[:, 0]) * (pts[:, 1] + nxt[:, 1])),
        ])
        target = pts.mean(axis=0) if hint is None else np.asarray(hint, float)
        if float(normal @ target) < 0.0:
            ids.reverse()
        self.polygons.append(tuple(ids))

    def mesh(self) -> Mesh:
        return Mesh(np.array(self.points, float).reshape(-1, 3), clean_polygons(self.polygons))


def _orient(mesh: Mesh, orientation: str) -> Mesh:
    if orientation == "+Y" or not len(mesh.points):
        return mesh
    src = mesh.points
    cols = [sign * src[:, axis] for axis, sign in ORIENT_MAPS[orientation]]
    return Mesh(np.column_stack(cols), mesh.polygons, mesh.loose_edges)


def _ring(b: _Builder, y: float, radius: float, rot: int) -> list[int]:
    if radius <= 1e-12:
        return [b.vertex((0.0, y, 0.0))]
    return [b.vertex((radius * math.cos(TAU * j / rot), y, radius * math.sin(TAU * j / rot)))
            for j in range(rot)]


def _strip(b: _Builder, lo: list[int], hi: list[int], normal=None, sign: float = 1.0) -> None:
    count = max(len(lo), len(hi))
    for j in range(count):
        ids = [lo[j % len(lo)], lo[(j + 1) % len(lo)], hi[(j + 1) % len(hi)], hi[j % len(hi)]]
        if normal is None:
            pts = [b.points[i] for i in ids]
            cx = sum(q[0] for q in pts) / 4.0
            cz = sum(q[2] for q in pts) / 4.0
            hint = (sign * cx, 0.0, sign * cz)
        else:
            hint = normal
        b.face(ids, hint)


def _cap(b: _Builder, y: float, radius: float, rot: int, segs: int, up: bool) -> None:
    hint = (0.0, 1.0 if up else -1.0, 0.0)
    rings = [_ring(b, y, radius * k / segs, rot) for k in range(1, segs + 1)]
    b.face(rings[0], hint)
    for lo, hi in zip(rings, rings[1:]):
        _strip(b, lo, hi, normal=hint)


def _rounded_point(q: list[float], half: list[float], r: float) -> list[float]:
    inner = [h - r for h in half]
    clamped = [min(max(q[k], -inner[k]), inner[k]) for k in range(3)]
    d = [q[k] - clamped[k] for k in range(3)]
    length = math.sqrt(sum(c * c for c in d))
    return [clamped[k] + r * d[k] / length for k in range(3)]


def _axis_nodes(half: float, r: float, segs: int, arc: int) -> list[float]:
    inner = half - r
    if inner <= 1e-6 * half:
        flat = [0.0]
    else:
        flat = [-inner + 2.0 * inner * i / segs for i in range(segs + 1)]
    bend = [inner + r * math.tan(math.pi / 4.0 * j / arc) for j in range(1, arc + 1)]
    bend[-1] = half
    return [-x for x in reversed(bend)] + flat + bend


def _rounded_cube(size, segs, radius: float, sub: int) -> Mesh:
    half = [s / 2.0 for s in size]
    r = min(float(radius), min(half))
    arc = max(1, int(sub))
    nodes = [_axis_nodes(half[k], r, max(1, int(segs[k])), arc) for k in range(3)]
    b = _Builder()
    for axis in range(3):
        u = (axis + 1) % 3
        v = (axis + 2) % 3
        for sign in (-1.0, 1.0):
            hint = [0.0, 0.0, 0.0]
            hint[axis] = sign
            grid = []
            for qv in nodes[v]:
                row = []
                for qu in nodes[u]:
                    q = [0.0, 0.0, 0.0]
                    q[axis] = sign * half[axis]
                    q[u] = qu
                    q[v] = qv
                    row.append(b.vertex(_rounded_point(q, half, r)))
                grid.append(row)
            for j in range(len(grid) - 1):
                for i in range(len(grid[0]) - 1):
                    b.face([grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]], hint)
    return b.mesh()


def _build_cube(p: dict, _inputs: list) -> Mesh:
    size = (p["size_x"], p["size_y"], p["size_z"])
    if min(size) <= 0.0:
        return Mesh.empty()
    segs = (p["segments_x"], p["segments_y"], p["segments_z"])
    if p["fillet"] and p["fillet_radius"] > 0.0:
        return _rounded_cube(size, segs, p["fillet_radius"], p["fillet_subdivision"])
    return prim.cube(size, segs)


def _build_plane(p: dict, _inputs: list) -> Mesh:
    if p["width"] <= 0.0 or p["height"] <= 0.0:
        return Mesh.empty()
    m = prim.plane(p["width"], p["height"], p["width_segments"], p["height_segments"])
    return _orient(m, p["orientation"])


def _build_polygon(p: dict, _inputs: list) -> Mesh:
    w, h = p["width"], p["height"]
    if w <= 0.0 or h <= 0.0:
        return Mesh.empty()
    hw, hh = w / 2.0, h / 2.0
    if p["triangle"]:
        pts = [(-hw, -hh, 0.0), (hw, -hh, 0.0), (0.0, hh, 0.0)]
    else:
        pts = [(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0)]
    ids = list(range(len(pts)))
    if p["reverse"]:
        ids.reverse()
    return Mesh(np.array(pts, float), [tuple(ids)])


def _build_disc(p: dict, _inputs: list) -> Mesh:
    m = prim.disc(p["inner_radius"], p["outer_radius"], p["disc_segments"], p["rotation_segments"])
    return _orient(m, p["orientation"])


def _build_pyramid(p: dict, _inputs: list) -> Mesh:
    size = (p["size_x"], p["size_y"], p["size_z"])
    if min(size) <= 0.0:
        return Mesh.empty()
    return _orient(prim.pyramid(size, p["segments"]), p["orientation"])


def _torus(big: float, ring_segments: int, small: float, pipe_segments: int) -> Mesh:
    rs = max(3, int(ring_segments))
    ps = max(3, int(pipe_segments))
    b = _Builder()
    grid = []
    for i in range(rs):
        theta = TAU * i / rs
        row = []
        for j in range(ps):
            phi = TAU * j / ps
            rho = big + small * math.cos(phi)
            row.append(b.vertex((rho * math.cos(theta), small * math.sin(phi), rho * math.sin(theta))))
        grid.append(row)
    polygons = []
    for i in range(rs):
        i2 = (i + 1) % rs
        for j in range(ps):
            j2 = (j + 1) % ps
            polygons.append((grid[i][j], grid[i][j2], grid[i2][j2], grid[i2][j]))
    return Mesh(np.array(b.points, float).reshape(-1, 3), clean_polygons(polygons))


def _build_torus(p: dict, _inputs: list) -> Mesh:
    if p["ring_radius"] <= 0.0 or p["pipe_radius"] <= 0.0:
        return Mesh.empty()
    return _orient(_torus(p["ring_radius"], p["ring_segments"], p["pipe_radius"], p["pipe_segments"]),
                   p["orientation"])


def _build_cone(p: dict, _inputs: list) -> Mesh:
    top, bottom, h = p["top_radius"], p["bottom_radius"], p["height"]
    if h <= 0.0 or max(top, bottom) <= 0.0:
        return Mesh.empty()
    hs = int(p["height_segments"])
    rot = int(p["rotation_segments"])
    cs = int(p["cap_segments"])
    b = _Builder()
    rings = [_ring(b, -h / 2.0 + h * k / hs, bottom + (top - bottom) * k / hs, rot)
             for k in range(hs + 1)]
    for lo, hi in zip(rings, rings[1:]):
        _strip(b, lo, hi)
    if p["caps"]:
        if bottom > 0.0:
            _cap(b, -h / 2.0, bottom, rot, cs, False)
        if top > 0.0:
            _cap(b, h / 2.0, top, rot, cs, True)
    return _orient(b.mesh(), p["orientation"])


def _build_cylinder(p: dict, _inputs: list) -> Mesh:
    if p["radius"] <= 0.0 or p["height"] <= 0.0:
        return Mesh.empty()
    m = prim.cylinder(p["radius"], p["height"], p["height_segments"], p["rotation_segments"],
                      p["caps"], p["cap_segments"])
    return _orient(m, p["orientation"])


def _build_tube(p: dict, _inputs: list) -> Mesh:
    if p["outer_radius"] <= p["inner_radius"] or p["height"] <= 0.0:
        return Mesh.empty()
    m = prim.tube(p["inner_radius"], p["outer_radius"], p["height"], p["rotation_segments"],
                  p["cap_segments"], p["height_segments"])
    return _orient(m, p["orientation"])


def _build_oil_tank(p: dict, _inputs: list) -> Mesh:
    if p["radius"] <= 0.0 or p["height"] <= 0.0:
        return Mesh.empty()
    m = prim.oil_tank(p["radius"], p["height"], p["height_segments"], p["cap_height"],
                      p["cap_segments"], p["rotation_segments"])
    return _orient(m, p["orientation"])


def _build_capsule(p: dict, _inputs: list) -> Mesh:
    if p["radius"] <= 0.0:
        return Mesh.empty()
    body = max(0.0, p["height"] - 2.0 * p["radius"])
    m = prim.capsule(p["radius"], body, p["height_segments"], p["cap_segments"],
                     p["rotation_segments"])
    return _orient(m, p["orientation"])


def _hemisphere(radius: float, segments: int) -> Mesh:
    seg = max(3, int(segments))
    bands = max(1, max(2, seg // 2) // 2)
    b = _Builder()
    levels: list[list[int]] = []
    for i in range(bands + 1):
        phi = (math.pi / 2.0) * i / bands
        y = radius * math.cos(phi)
        rho = radius * math.sin(phi)
        if i == 0:
            levels.append([b.vertex((0.0, y, 0.0))])
        else:
            levels.append([b.vertex((rho * math.cos(TAU * j / seg), y, rho * math.sin(TAU * j / seg)))
                           for j in range(seg)])
    for lo, hi in zip(levels, levels[1:]):
        _strip(b, lo, hi)
    b.face(levels[-1], (0.0, -1.0, 0.0))
    return b.mesh()


def _triangle_grid(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, n: int) -> list[list[np.ndarray]]:
    def at(i: int, j: int) -> np.ndarray:
        return p0 + (p1 - p0) * (i / n) + (p2 - p0) * (j / n)

    rings: list[list[np.ndarray]] = []
    for i in range(n):
        for j in range(n - i):
            rings.append([at(i, j), at(i + 1, j), at(i, j + 1)])
            if i + j + 2 <= n:
                rings.append([at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)])
    return rings


def _quad_grid(corners: list[np.ndarray], n: int) -> list[list[np.ndarray]]:
    c0, c1, c2, c3 = corners

    def at(i: int, j: int) -> np.ndarray:
        u = i / n
        v = j / n
        return (1.0 - u) * (1.0 - v) * c0 + u * (1.0 - v) * c1 + u * v * c2 + (1.0 - u) * v * c3

    rings: list[list[np.ndarray]] = []
    for i in range(n):
        for j in range(n):
            rings.append([at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)])
    return rings


def _subdivide(corners: list[np.ndarray], segs: int) -> list[list[np.ndarray]]:
    if segs <= 1:
        return [list(corners)]
    if len(corners) == 3:
        return _triangle_grid(corners[0], corners[1], corners[2], segs)
    if len(corners) == 4:
        return _quad_grid(corners, segs)
    centre = sum(corners) / len(corners)
    out: list[list[np.ndarray]] = []
    for k in range(len(corners)):
        out.extend(_triangle_grid(centre, corners[k], corners[(k + 1) % len(corners)], segs))
    return out


def _polyhedron(pts: np.ndarray, faces: list[list[int]], segs: int, radius: float | None = None) -> Mesh:
    b = _Builder()
    for face in faces:
        corners = [np.asarray(pts[i], float) for i in face]
        for ring in _subdivide(corners, segs):
            if radius is not None:
                ring = [radius * q / np.linalg.norm(q) for q in ring]
            b.face([b.vertex(q) for q in ring])
    return b.mesh()


def _cyclic(pts: np.ndarray, idx: list[int], normal: np.ndarray) -> list[int]:
    centre = pts[idx].mean(axis=0)
    u = pts[idx[0]] - centre
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)
    angles = [math.atan2(float((pts[i] - centre) @ v), float((pts[i] - centre) @ u)) for i in idx]
    return [idx[k] for k in sorted(range(len(idx)), key=lambda k: angles[k])]


def _bucky() -> tuple[np.ndarray, list[list[int]]]:
    seeds = ((0.0, 1.0, 3.0 * PHI), (1.0, 2.0 + PHI, 2.0 * PHI), (PHI, 2.0, 2.0 * PHI + 1.0))
    found: dict[tuple[float, float, float], tuple[float, float, float]] = {}
    for seed in seeds:
        for shift in range(3):
            base = seed[shift:] + seed[:shift]
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    for sz in (-1.0, 1.0):
                        q = (sx * base[0], sy * base[1], sz * base[2])
                        found.setdefault(tuple(round(c, 9) for c in q), q)
    pts = np.array(list(found.values()), float)
    pts = pts / np.linalg.norm(pts, axis=1)[:, None]
    bases = ((0.0, 1.0, PHI), (0.0, PHI, 1.0), (0.0, 1.0 / PHI, PHI), (0.0, PHI, 1.0 / PHI), (1.0, 1.0, 1.0))
    directions: list[tuple[float, float, float]] = []
    for base in bases:
        for perm in (base, base[1:] + base[:1], base[2:] + base[:2]):
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    for sz in (-1.0, 1.0):
                        directions.append((sx * perm[0], sy * perm[1], sz * perm[2]))
    faces: dict[frozenset, np.ndarray] = {}
    for d in directions:
        n = np.asarray(d, float)
        n = n / np.linalg.norm(n)
        dots = pts @ n
        idx = np.flatnonzero(dots > dots.max() - 1e-7).tolist()
        if len(idx) in (5, 6):
            faces.setdefault(frozenset(idx), n)
    ordered = [_cyclic(pts, sorted(members), normal) for members, normal in faces.items()]
    return pts, ordered


def _base_solid(name: str) -> tuple[np.ndarray, list[list[int]]]:
    if name == "Bucky":
        return _bucky()
    m = prim.platonic(1.0, name)
    return m.points, [list(poly) for poly in m.polygons]


def _build_sphere(p: dict, _inputs: list) -> Mesh:
    r = p["radius"]
    if r <= 0.0:
        return Mesh.empty()
    kind = p["type"]
    seg = int(p["segments"])
    if kind == "Standard":
        return prim.sphere(r, seg)
    if kind == "Hemisphere":
        return _hemisphere(r, seg)
    pts, faces = _base_solid(kind)
    return _polyhedron(pts * r, faces, min(seg, GEODESIC_MAX), r)


def _build_platonic(p: dict, _inputs: list) -> Mesh:
    r = p["radius"]
    if r <= 0.0:
        return Mesh.empty()
    pts, faces = _base_solid(PLATONIC_TYPES[p["type"]])
    return _polyhedron(pts * r, faces, int(p["segments"]))


def _value_noise(seed: int, cells: int, uu: np.ndarray, vv: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(seed)
    table = rng.uniform(-1.0, 1.0, size=(cells + 1, cells + 1))
    gu = uu * cells
    gv = vv * cells
    iu = np.minimum(np.floor(gu).astype(int), cells - 1)
    iv = np.minimum(np.floor(gv).astype(int), cells - 1)
    fu = gu - iu
    fv = gv - iv
    su = fu * fu * (3.0 - 2.0 * fu)
    sv = fv * fv * (3.0 - 2.0 * fv)
    top = table[iv, iu] + (table[iv, iu + 1] - table[iv, iu]) * su
    bottom = table[iv + 1, iu] + (table[iv + 1, iu + 1] - table[iv + 1, iu]) * su
    return top + (bottom - top) * sv


def _height_field(p: dict, uu: np.ndarray, vv: np.ndarray) -> np.ndarray:
    seed = int(p["seed"])
    scale = float(p["scale"])
    rough = float(p["rough_furrows"]) / 100.0
    fine = float(p["fine_furrows"]) / 100.0
    layers = ((2, 1.0, rough), (4, 0.5, rough), (8, 1.0, fine), (16, 0.5, fine), (32, 0.25, fine))
    acc = np.zeros_like(uu)
    norm = 0.0
    for k, (cells, weight, amp) in enumerate(layers):
        if amp <= 0.0:
            continue
        n = max(1, int(round(cells * scale)))
        acc = acc + amp * weight * _value_noise((seed * 131 + k + 1) % 4294967296, n, uu, vv)
        norm += amp * weight
    hn = 0.5 + 0.5 * acc / norm if norm > 0.0 else np.zeros_like(uu)
    low, high = float(hn.min()), float(hn.max())
    if high - low > 1e-12:
        hn = (hn - low) / (high - low)
    else:
        hn = np.zeros_like(uu)
    sea = min(max(float(p["sea_level"]) / 100.0, 0.0), 1.0)
    plateau = min(max(float(p["plateau_level"]) / 100.0, 0.0), 1.0)
    if plateau - sea <= 1e-9:
        return np.zeros_like(uu)
    return (np.clip(hn, sea, plateau) - sea) / (plateau - sea)


def _build_landscape(p: dict, _inputs: list) -> Mesh:
    sx, sy, sz = p["size_x"], p["size_y"], p["size_z"]
    if sx <= 0.0 or sz <= 0.0:
        return Mesh.empty()
    ws = int(p["width_segments"])
    ds = int(p["depth_segments"])
    xs = np.linspace(-sx / 2.0, sx / 2.0, ws + 1)
    zs = np.linspace(-sz / 2.0, sz / 2.0, ds + 1)
    uu, vv = np.meshgrid(np.linspace(0.0, 1.0, ws + 1), np.linspace(0.0, 1.0, ds + 1))
    hn = _height_field(p, uu, vv)
    X, Z = np.meshgrid(xs, zs)
    pts = np.column_stack([X.ravel(), (sy * hn).ravel(), Z.ravel()])
    idx = np.arange(len(pts)).reshape(ds + 1, ws + 1)
    polys = []
    for j in range(ds):
        for i in range(ws):
            polys.append((idx[j, i], idx[j + 1, i], idx[j + 1, i + 1], idx[j, i + 1]))
    return _orient(Mesh(pts, polys), p["orientation"])


def _bernstein(n: int, t: np.ndarray) -> np.ndarray:
    deg = n - 1
    return np.column_stack([math.comb(deg, i) * t ** i * (1.0 - t) ** (deg - i) for i in range(n)])


def _build_bezier(p: dict, _inputs: list) -> Mesh:
    su = int(p["subdivision_x"])
    sv = int(p["subdivision_y"])
    gx = int(p["grid_x"])
    gy = int(p["grid_y"])
    spacing = float(p["spacing"])
    if spacing <= 0.0:
        return Mesh.empty()
    half_x = (gx - 1) * spacing / 2.0
    half_z = (gy - 1) * spacing / 2.0
    xs = np.linspace(-half_x, half_x, gx)
    zs = np.linspace(-half_z, half_z, gy)
    control = np.zeros((gx, gy, 3))
    control[:, :, 0] = xs[:, None]
    control[:, :, 2] = zs[None, :]
    bu = _bernstein(gx, np.linspace(0.0, 1.0, su + 1))
    bv = _bernstein(gy, np.linspace(0.0, 1.0, sv + 1))
    grid = np.einsum("ki,lj,ijc->klc", bu, bv, control)
    pts = grid.reshape(-1, 3)
    idx = np.arange(len(pts)).reshape(su + 1, sv + 1)
    polys = []
    for k in range(su):
        for l in range(sv):
            polys.append((idx[k, l], idx[k, l + 1], idx[k + 1, l + 1], idx[k + 1, l]))
    return Mesh(pts, polys)


def _build_figure(p: dict, _inputs: list) -> Mesh:
    h = float(p["height"])
    if h <= 0.0:
        return Mesh.empty()
    s = int(p["segments"])
    boxes = [
        ((0.0, 0.925 * h, 0.0), (0.15 * h, 0.15 * h, 0.15 * h)),
        ((0.0, 0.64 * h, 0.0), (0.24 * h, 0.36 * h, 0.12 * h)),
        ((-0.17 * h, 0.64 * h, 0.0), (0.08 * h, 0.36 * h, 0.08 * h)),
        ((0.17 * h, 0.64 * h, 0.0), (0.08 * h, 0.36 * h, 0.08 * h)),
        ((-0.06 * h, 0.225 * h, 0.0), (0.09 * h, 0.45 * h, 0.09 * h)),
        ((0.06 * h, 0.225 * h, 0.0), (0.09 * h, 0.45 * h, 0.09 * h)),
    ]
    pts: list[np.ndarray] = []
    polys: list[tuple[int, ...]] = []
    offset = 0
    for centre, size in boxes:
        m = prim.cube(size, (s, s, s))
        pts.append(m.points + np.asarray(centre, float))
        polys.extend(tuple(i + offset for i in poly) for poly in m.polygons)
        offset += len(m.points)
    return Mesh(np.vstack(pts), polys)


def _param_distance(key: str, label: str, default: float, minimum: float | None = 0.0,
                    group: str = "Object") -> Param:
    return Param(key, label, "distance", float(default), minimum=minimum, maximum=DISTANCE_MAX,
                 group=group)


def _param_count(key: str, label: str, default: int, minimum: int = 1,
                 group: str = "Object", maximum: int = SEGMENTS_MAX) -> Param:
    return Param(key, label, "int", int(default), minimum=float(minimum), maximum=float(maximum),
                 group=group)


def _param_rotation(default: int) -> Param:
    return _param_count("rotation_segments", "Rotation Segments", default, minimum=3,
                        maximum=ROTATION_MAX)


def _param_percent(key: str, label: str, default: float) -> Param:
    return Param(key, label, "percent", float(default), minimum=0.0, maximum=100.0, group="Object")


def _param_orientation() -> Param:
    return Param("orientation", "Orientation", "choice", "+Y", choices=ORIENTATIONS, group="Object")


def _register(object_id: str, label: str, build, params: tuple, description: str) -> ObjectSpec:
    return register(ObjectSpec(id=object_id, label=label, category="mesh", build=build,
                               params=params, icon=object_id, description=description))


_register("cube", "Cube", _build_cube, (
    _param_distance("size_x", "Size X", 200.0),
    _param_distance("size_y", "Size Y", 200.0),
    _param_distance("size_z", "Size Z", 200.0),
    _param_count("segments_x", "Segments X", 1, maximum=50),
    _param_count("segments_y", "Segments Y", 1, maximum=50),
    _param_count("segments_z", "Segments Z", 1, maximum=50),
    Param("fillet", "Fillet", "bool", False, group="Fillet"),
    _param_distance("fillet_radius", "Fillet Radius", 40.0, group="Fillet"),
    _param_count("fillet_subdivision", "Fillet Subdivision", 5, group="Fillet", maximum=32),
), "Cube with optional rounded edges and corners")

_register("plane", "Plane", _build_plane, (
    _param_distance("width", "Width", 400.0),
    _param_distance("height", "Height", 400.0),
    _param_count("width_segments", "Width Segments", 10),
    _param_count("height_segments", "Height Segments", 10),
    _param_orientation(),
), "Flat grid of quads")

register(ObjectSpec(
    id="polygon_object", label="Polygon", category="mesh", build=_build_polygon,
    params=(
        _param_distance("width", "Width", 400.0),
        _param_distance("height", "Height", 400.0),
        Param("triangle", "Triangle", "bool", False, group="Object"),
        Param("reverse", "Reverse", "bool", False, group="Object"),
    ), icon="plane", description="Single quad or triangle"))

_register("disc", "Disc", _build_disc, (
    _param_distance("inner_radius", "Inner Radius", 0.0),
    _param_distance("outer_radius", "Outer Radius", 100.0),
    _param_count("disc_segments", "Disc Segments", 1),
    _param_rotation(32),
    _param_orientation(),
), "Flat disc or ring")

_register("pyramid", "Pyramid", _build_pyramid, (
    _param_distance("size_x", "Size X", 200.0),
    _param_distance("size_y", "Size Y", 200.0),
    _param_distance("size_z", "Size Z", 200.0),
    _param_count("segments", "Segments", 1),
    _param_orientation(),
), "Square-based pyramid")

_register("sphere", "Sphere", _build_sphere, (
    _param_distance("radius", "Radius", 100.0),
    _param_count("segments", "Segments", 16, minimum=3, maximum=64),
    Param("type", "Type", "choice", "Standard", choices=SPHERE_TYPES, group="Object"),
), "Sphere, geodesic polyhedron or hemisphere")

_register("torus", "Torus", _build_torus, (
    _param_distance("ring_radius", "Ring Radius", 100.0),
    _param_count("ring_segments", "Ring Segments", 32, minimum=3, maximum=ROTATION_MAX),
    _param_distance("pipe_radius", "Pipe Radius", 50.0),
    _param_count("pipe_segments", "Pipe Segments", 16, minimum=3, maximum=ROTATION_MAX),
    _param_orientation(),
), "Torus around the orientation axis")

_register("cone", "Cone", _build_cone, (
    _param_distance("top_radius", "Top Radius", 0.0),
    _param_distance("bottom_radius", "Bottom Radius", 100.0),
    _param_distance("height", "Height", 200.0),
    _param_count("height_segments", "Height Segments", 4),
    _param_rotation(16),
    _param_orientation(),
    Param("caps", "Caps", "bool", True, group="Object"),
    _param_count("cap_segments", "Cap Segments", 1),
), "Cone or truncated cone")

_register("tube", "Tube", _build_tube, (
    _param_distance("inner_radius", "Inner Radius", 50.0),
    _param_distance("outer_radius", "Outer Radius", 100.0),
    _param_rotation(16),
    _param_count("cap_segments", "Cap Segments", 1),
    _param_distance("height", "Height", 100.0),
    _param_count("height_segments", "Height Segments", 1),
    _param_orientation(),
), "Hollow cylinder")

_register("cylinder", "Cylinder", _build_cylinder, (
    _param_distance("radius", "Radius", 50.0),
    _param_distance("height", "Height", 200.0),
    _param_count("height_segments", "Height Segments", 4),
    _param_rotation(16),
    _param_orientation(),
    Param("caps", "Caps", "bool", True, group="Object"),
    _param_count("cap_segments", "Cap Segments", 1),
), "Cylinder")

_register("oil_tank", "Oil Tank", _build_oil_tank, (
    _param_distance("radius", "Radius", 50.0),
    _param_distance("height", "Height", 200.0),
    _param_count("height_segments", "Height Segments", 4),
    _param_distance("cap_height", "Cap Height", 25.0),
    _param_count("cap_segments", "Cap Segments", 8),
    _param_rotation(16),
    _param_orientation(),
), "Cylinder with domed caps")

_register("capsule", "Capsule", _build_capsule, (
    _param_distance("radius", "Radius", 50.0),
    _param_distance("height", "Height", 200.0),
    _param_count("height_segments", "Height Segments", 4),
    _param_count("cap_segments", "Cap Segments", 8),
    _param_rotation(16),
    _param_orientation(),
), "Cylinder with hemispherical caps")

_register("platonic", "Platonic", _build_platonic, (
    _param_distance("radius", "Radius", 100.0),
    _param_count("segments", "Segments", 1, maximum=GEODESIC_MAX),
    Param("type", "Type", "choice", "Tetra", choices=tuple(PLATONIC_TYPES), group="Object"),
), "Platonic solid, optionally subdivided")

_register("landscape", "Landscape", _build_landscape, (
    _param_distance("size_x", "Size X", 600.0),
    _param_distance("size_y", "Size Y", 100.0),
    _param_distance("size_z", "Size Z", 600.0),
    _param_count("width_segments", "Width Segments", 100, maximum=200),
    _param_count("depth_segments", "Depth Segments", 100, maximum=200),
    _param_percent("rough_furrows", "Rough Furrows", 50.0),
    _param_percent("fine_furrows", "Fine Furrows", 50.0),
    Param("scale", "Scale", "float", 1.0, minimum=0.1, maximum=10.0, step=0.1, group="Object"),
    _param_percent("sea_level", "Sea Level", 0.0),
    _param_percent("plateau_level", "Plateau Level", 100.0),
    _param_orientation(),
    Param("seed", "Seed", "int", 0, group="Object"),
), "Deterministic noise terrain")

_register("bezier", "Bezier", _build_bezier, (
    _param_count("subdivision_x", "Subdivision X", 24),
    _param_count("subdivision_y", "Subdivision Y", 24),
    _param_count("grid_x", "Grid Points X", 3, minimum=2, maximum=16),
    _param_count("grid_y", "Grid Points Y", 3, minimum=2, maximum=16),
    _param_distance("spacing", "Grid Spacing", 200.0),
), "Flat bicubic patch from a regular control grid")

_register("figure", "Figure", _build_figure, (
    _param_distance("height", "Height", 200.0),
    _param_count("segments", "Segments", 2, maximum=20),
), "Mannequin made of closed boxes")
