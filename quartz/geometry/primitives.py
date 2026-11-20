from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .mesh import MeshGeometry

_FILL_TYPES = ("NOTHING", "NGON", "TRIFAN")


def _positive(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _count(value: int, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    value = int(value)
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _build(
    positions: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    *,
    edges: Sequence[Sequence[int]] = (),
    uv_vertex: np.ndarray | None = None,
    corner_uvs: Sequence[Sequence[float]] | None = None,
    calc_uvs: bool = True,
) -> MeshGeometry:
    geo = MeshGeometry.from_pydata(positions, edges, faces, shade_flat=True)
    if calc_uvs:
        if corner_uvs is not None:
            uvs = np.asarray(corner_uvs, dtype=np.float32).reshape(-1, 2)
        elif uv_vertex is not None:
            uvs = np.asarray(uv_vertex, dtype=np.float32)[geo.corner_verts]
        else:
            uvs = np.zeros((geo.num_corners, 2), dtype=np.float32)
        if uvs.shape[0] != geo.num_corners:
            raise ValueError("corner UV count does not match the face corners")
        geo.attributes.new("UVMap", "FLOAT2", "CORNER").data[...] = uvs
    return geo


def plane(size: float = 2.0, *, calc_uvs: bool = True) -> MeshGeometry:
    half = _positive(size, "size") / 2.0
    positions = [(-half, -half, 0.0), (half, -half, 0.0), (half, half, 0.0), (-half, half, 0.0)]
    faces = [[0, 1, 2, 3]]
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    return _build(positions, faces, corner_uvs=uvs, calc_uvs=calc_uvs)


def cube(size: float = 2.0, *, calc_uvs: bool = True) -> MeshGeometry:
    half = _positive(size, "size") / 2.0
    positions = [
        (-half, -half, -half),
        (half, -half, -half),
        (half, half, -half),
        (-half, half, -half),
        (-half, -half, half),
        (half, -half, half),
        (half, half, half),
        (-half, half, half),
    ]
    faces = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [3, 0, 4, 7],
    ]
    quad_uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    uvs = quad_uv * len(faces)
    return _build(positions, faces, corner_uvs=uvs, calc_uvs=calc_uvs)


def circle(
    vertices: int = 32,
    radius: float = 1.0,
    fill_type: str = "NOTHING",
    *,
    calc_uvs: bool = True,
) -> MeshGeometry:
    count = _count(vertices, "vertices", 3)
    radius = _positive(radius, "radius")
    if fill_type not in _FILL_TYPES:
        raise ValueError(f"fill_type must be one of {_FILL_TYPES}")
    ring = [
        (radius * math.cos(2.0 * math.pi * i / count), radius * math.sin(2.0 * math.pi * i / count), 0.0)
        for i in range(count)
    ]
    ring_uv = np.array(
        [
            (
                0.5 + 0.5 * math.cos(2.0 * math.pi * i / count),
                0.5 + 0.5 * math.sin(2.0 * math.pi * i / count),
            )
            for i in range(count)
        ],
        dtype=np.float32,
    )
    if fill_type == "NOTHING":
        edges = [(i, (i + 1) % count) for i in range(count)]
        return _build(ring, (), edges=edges, uv_vertex=ring_uv, calc_uvs=calc_uvs)
    if fill_type == "NGON":
        return _build(ring, [list(range(count))], uv_vertex=ring_uv, calc_uvs=calc_uvs)
    positions = ring + [(0.0, 0.0, 0.0)]
    center = count
    uv_vertex = np.vstack([ring_uv, np.array([[0.5, 0.5]], dtype=np.float32)])
    faces = [[center, i, (i + 1) % count] for i in range(count)]
    return _build(positions, faces, uv_vertex=uv_vertex, calc_uvs=calc_uvs)


def uv_sphere(
    segments: int = 32,
    ring_count: int = 16,
    radius: float = 1.0,
    *,
    calc_uvs: bool = True,
) -> MeshGeometry:
    segs = _count(segments, "segments", 3)
    rings = _count(ring_count, "ring_count", 2)
    radius = _positive(radius, "radius")
    positions: list[tuple[float, float, float]] = [(0.0, 0.0, radius)]
    uv_vertex: list[tuple[float, float]] = [(0.5, 1.0)]
    ring_starts: list[int] = []
    for ring in range(1, rings):
        phi = math.pi * ring / rings
        z = radius * math.cos(phi)
        ring_radius = radius * math.sin(phi)
        ring_starts.append(len(positions))
        for i in range(segs):
            angle = 2.0 * math.pi * i / segs
            positions.append(
                (ring_radius * math.cos(angle), ring_radius * math.sin(angle), z)
            )
            uv_vertex.append((i / segs, 1.0 - ring / rings))
    bottom = len(positions)
    positions.append((0.0, 0.0, -radius))
    uv_vertex.append((0.5, 0.0))

    faces: list[list[int]] = []
    first = ring_starts[0]
    for i in range(segs):
        faces.append([0, first + i, first + (i + 1) % segs])
    for ring in range(len(ring_starts) - 1):
        upper = ring_starts[ring]
        lower = ring_starts[ring + 1]
        for i in range(segs):
            nxt = (i + 1) % segs
            faces.append([upper + i, lower + i, lower + nxt, upper + nxt])
    last = ring_starts[-1]
    for i in range(segs):
        faces.append([bottom, last + (i + 1) % segs, last + i])
    return _build(
        positions, faces, uv_vertex=np.array(uv_vertex, dtype=np.float32), calc_uvs=calc_uvs
    )


def ico_sphere(
    subdivisions: int = 2,
    radius: float = 1.0,
    *,
    calc_uvs: bool = True,
) -> MeshGeometry:
    levels = _count(subdivisions, "subdivisions", 1) - 1
    radius = _positive(radius, "radius")
    t = (1.0 + math.sqrt(5.0)) / 2.0
    base = np.array(
        [
            [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
            [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
            [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1],
        ],
        dtype=np.float64,
    )
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    faces = _orient_outward(base, faces)
    vertices = base.tolist()
    current = [tuple(face) for face in faces]
    for _ in range(levels):
        cache: dict[tuple[int, int], int] = {}
        next_faces: list[tuple[int, int, int]] = []

        def midpoint(a: int, b: int) -> int:
            key = (a, b) if a <= b else (b, a)
            if key not in cache:
                point = (np.array(vertices[a]) + np.array(vertices[b])) / 2.0
                vertices.append(point.tolist())
                cache[key] = len(vertices) - 1
            return cache[key]

        for a, b, c in current:
            ab = midpoint(a, b)
            bc = midpoint(b, c)
            ca = midpoint(c, a)
            next_faces.extend(
                [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
            )
        current = next_faces
    points = np.array(vertices, dtype=np.float64)
    points /= np.linalg.norm(points, axis=1)[:, None]
    points *= radius
    uv = _spherical_uv(points)
    return _build(
        points, [list(face) for face in current], uv_vertex=uv, calc_uvs=calc_uvs
    )


def _orient_outward(points: np.ndarray, faces) -> list[tuple[int, int, int]]:
    out = []
    for a, b, c in faces:
        normal = np.cross(points[b] - points[a], points[c] - points[a])
        centroid = (points[a] + points[b] + points[c]) / 3.0
        if float(np.dot(normal, centroid)) < 0.0:
            out.append((a, c, b))
        else:
            out.append((a, b, c))
    return out


def _spherical_uv(points: np.ndarray) -> np.ndarray:
    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]
    length = np.linalg.norm(points, axis=1)
    safe = np.where(length == 0.0, 1.0, length)
    u = np.arctan2(y, x) / (2.0 * math.pi) + 0.5
    v = z / safe * 0.5 + 0.5
    return np.stack([u, v], axis=1).astype(np.float32)


def cylinder(
    vertices: int = 32,
    radius: float = 1.0,
    depth: float = 2.0,
    end_fill_type: str = "NGON",
    *,
    calc_uvs: bool = True,
) -> MeshGeometry:
    return _revolved(
        vertices,
        _positive(radius, "radius"),
        _positive(radius, "radius"),
        depth,
        end_fill_type,
        calc_uvs=calc_uvs,
    )


def cone(
    vertices: int = 32,
    radius1: float = 1.0,
    radius2: float = 0.0,
    depth: float = 2.0,
    end_fill_type: str = "NGON",
    *,
    calc_uvs: bool = True,
) -> MeshGeometry:
    if not math.isfinite(float(radius1)) or float(radius1) <= 0.0:
        raise ValueError("radius1 must be a positive number")
    if not math.isfinite(float(radius2)) or float(radius2) < 0.0:
        raise ValueError("radius2 cannot be negative")
    return _revolved(
        vertices,
        float(radius1),
        float(radius2),
        depth,
        end_fill_type,
        calc_uvs=calc_uvs,
    )


def _revolved(
    vertices: int,
    radius1: float,
    radius2: float,
    depth: float,
    end_fill_type: str,
    *,
    calc_uvs: bool,
) -> MeshGeometry:
    count = _count(vertices, "vertices", 3)
    depth = _positive(depth, "depth")
    if end_fill_type not in _FILL_TYPES:
        raise ValueError(f"end_fill_type must be one of {_FILL_TYPES}")
    half = depth / 2.0
    apex = radius2 == 0.0
    positions = [
        (
            radius1 * math.cos(2.0 * math.pi * i / count),
            radius1 * math.sin(2.0 * math.pi * i / count),
            -half,
        )
        for i in range(count)
    ]
    if apex:
        top_start = len(positions)
        positions.append((0.0, 0.0, half))
    else:
        top_start = len(positions)
        for i in range(count):
            angle = 2.0 * math.pi * i / count
            positions.append(
                (radius2 * math.cos(angle), radius2 * math.sin(angle), half)
            )

    def radial(index: int) -> tuple[float, float]:
        angle = 2.0 * math.pi * index / count
        return (0.5 + 0.5 * math.cos(angle), 0.5 + 0.5 * math.sin(angle))

    faces: list[list[int]] = []
    corner_uvs: list[tuple[float, float]] = []
    for i in range(count):
        nxt = (i + 1) % count
        if apex:
            faces.append([i, nxt, top_start])
            corner_uvs.extend([(i / count, 0.0), (nxt / count, 0.0), (0.5, 1.0)])
        else:
            faces.append([i, nxt, top_start + nxt, top_start + i])
            corner_uvs.extend(
                [
                    (i / count, 0.0),
                    (nxt / count, 0.0),
                    (nxt / count, 1.0),
                    (i / count, 1.0),
                ]
            )
    if end_fill_type == "NGON":
        faces.append(list(range(count))[::-1])
        corner_uvs.extend(radial(i) for i in range(count - 1, -1, -1))
        if not apex:
            faces.append([top_start + i for i in range(count)])
            corner_uvs.extend(radial(i) for i in range(count))
    elif end_fill_type == "TRIFAN":
        center_bottom = len(positions)
        positions.append((0.0, 0.0, -half))
        for i in range(count):
            nxt = (i + 1) % count
            faces.append([center_bottom, nxt, i])
            corner_uvs.extend([(0.5, 0.5), radial(nxt), radial(i)])
        if not apex:
            center_top = len(positions)
            positions.append((0.0, 0.0, half))
            for i in range(count):
                nxt = (i + 1) % count
                faces.append([center_top, top_start + i, top_start + nxt])
                corner_uvs.extend([(0.5, 0.5), radial(i), radial(nxt)])
    return _build(positions, faces, corner_uvs=corner_uvs, calc_uvs=calc_uvs)


def grid(
    x_subdivisions: int = 10,
    y_subdivisions: int = 10,
    size: float = 2.0,
    *,
    calc_uvs: bool = True,
) -> MeshGeometry:
    x_count = _count(x_subdivisions, "x_subdivisions", 1)
    y_count = _count(y_subdivisions, "y_subdivisions", 1)
    size = _positive(size, "size")
    half = size / 2.0
    positions = []
    uv_vertex = []
    for iy in range(y_count + 1):
        for ix in range(x_count + 1):
            x = -half + size * ix / x_count
            y = -half + size * iy / y_count
            positions.append((x, y, 0.0))
            uv_vertex.append((ix / x_count, iy / y_count))
    stride = x_count + 1
    faces = []
    for iy in range(y_count):
        for ix in range(x_count):
            index = iy * stride + ix
            faces.append([index, index + 1, index + 1 + stride, index + stride])
    return _build(
        positions, faces, uv_vertex=np.array(uv_vertex, np.float32), calc_uvs=calc_uvs
    )


def torus(
    major_segments: int = 48,
    minor_segments: int = 12,
    major_radius: float = 1.0,
    minor_radius: float = 0.25,
    *,
    calc_uvs: bool = True,
) -> MeshGeometry:
    major = _count(major_segments, "major_segments", 3)
    minor = _count(minor_segments, "minor_segments", 3)
    major_radius = _positive(major_radius, "major_radius")
    minor_radius = _positive(minor_radius, "minor_radius")
    positions = []
    uv_vertex = []
    for i in range(major):
        u = 2.0 * math.pi * i / major
        for j in range(minor):
            v = 2.0 * math.pi * j / minor
            radius = major_radius + minor_radius * math.cos(v)
            positions.append(
                (radius * math.cos(u), radius * math.sin(u), minor_radius * math.sin(v))
            )
            uv_vertex.append((i / major, j / minor))
    faces = []
    for i in range(major):
        i_next = (i + 1) % major
        for j in range(minor):
            j_next = (j + 1) % minor
            a = i * minor + j
            b = i_next * minor + j
            c = i_next * minor + j_next
            d = i * minor + j_next
            faces.append([a, b, c, d])
    return _build(
        positions, faces, uv_vertex=np.array(uv_vertex, np.float32), calc_uvs=calc_uvs
    )
