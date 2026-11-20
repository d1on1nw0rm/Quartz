from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .mesh import MeshGeometry


def triangulate(geo: MeshGeometry) -> tuple[np.ndarray, np.ndarray]:
    triangles: list[tuple[int, int, int]] = []
    owners: list[int] = []
    positions = geo.positions.astype(np.float64)
    verts = geo.corner_verts
    offsets = geo.face_offsets
    for face in range(geo.num_faces):
        start, end = int(offsets[face]), int(offsets[face + 1])
        count = end - start
        if count < 3:
            continue
        corners = np.arange(start, end, dtype=np.int32)
        if count == 3:
            triangles.append((int(corners[0]), int(corners[1]), int(corners[2])))
            owners.append(face)
            continue
        if count == 4:
            diagonal_a = _distance(positions[verts[corners[0]]], positions[verts[corners[2]]])
            diagonal_b = _distance(positions[verts[corners[1]]], positions[verts[corners[3]]])
            if diagonal_a <= diagonal_b:
                pairs = ((0, 1, 2), (0, 2, 3))
            else:
                pairs = ((1, 2, 3), (1, 3, 0))
            for a, b, c in pairs:
                triangles.append((int(corners[a]), int(corners[b]), int(corners[c])))
                owners.append(face)
            continue
        for a, b, c in _ear_clip(corners, verts, positions):
            triangles.append((int(a), int(b), int(c)))
            owners.append(face)
    if not triangles:
        return np.zeros((0, 3), dtype=np.int32), np.zeros(0, dtype=np.int32)
    return (
        np.asarray(triangles, dtype=np.int32),
        np.asarray(owners, dtype=np.int32),
    )


def _distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def _ear_clip(
    corners: np.ndarray, verts: np.ndarray, positions: np.ndarray
) -> list[tuple[int, int, int]]:
    points = positions[verts[corners]].copy()
    normal = _newell(points)
    axis = int(np.argmax(np.abs(normal)))
    keep = [index for index in range(3) if index != axis]
    projected = points[:, keep]
    area = _signed_area(projected)
    orientation = 1.0 if area >= 0.0 else -1.0
    order = list(range(len(corners)))
    out: list[tuple[int, int, int]] = []
    guard = 0
    while len(order) > 3 and guard < 4 * len(order) + 16:
        guard += 1
        ear_found = False
        for index in range(len(order)):
            previous = order[index - 1]
            current = order[index]
            following = order[(index + 1) % len(order)]
            if orientation * _cross(projected, previous, current, following) <= 0.0:
                continue
            if _contains_any(projected, previous, current, following, order):
                continue
            out.append((int(corners[previous]), int(corners[current]), int(corners[following])))
            order.pop(index)
            ear_found = True
            break
        if not ear_found:
            break
    if len(order) == 3:
        out.append((int(corners[order[0]]), int(corners[order[1]]), int(corners[order[2]])))
    elif len(order) > 3:
        for index in range(1, len(order) - 1):
            out.append(
                (
                    int(corners[order[0]]),
                    int(corners[order[index]]),
                    int(corners[order[index + 1]]),
                )
            )
    return out


def _newell(points: np.ndarray) -> np.ndarray:
    following = np.roll(points, -1, axis=0)
    return np.array(
        [
            np.sum((points[:, 1] - following[:, 1]) * (points[:, 2] + following[:, 2])),
            np.sum((points[:, 2] - following[:, 2]) * (points[:, 0] + following[:, 0])),
            np.sum((points[:, 0] - following[:, 0]) * (points[:, 1] + following[:, 1])),
        ],
        dtype=np.float64,
    )


def _signed_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _cross(points: np.ndarray, a: int, b: int, c: int) -> float:
    ab = points[b] - points[a]
    bc = points[c] - points[b]
    return float(ab[0] * bc[1] - ab[1] * bc[0])


def _contains_any(
    points: np.ndarray, a: int, b: int, c: int, order: list[int]
) -> bool:
    tri = points[[a, b, c]]
    for index in order:
        if index in (a, b, c):
            continue
        point = points[index]
        if _point_in_triangle(tri, point):
            return True
    return False


def _point_in_triangle(tri: np.ndarray, point: np.ndarray) -> bool:
    a, b, c = tri
    v0 = c - a
    v1 = b - a
    v2 = point - a
    denominator = v0[0] * v1[1] - v1[0] * v0[1]
    if abs(denominator) < 1e-20:
        return False
    u = (v2[0] * v1[1] - v1[0] * v2[1]) / denominator
    v = (v0[0] * v2[1] - v2[0] * v0[1]) / denominator
    return u >= 0.0 and v >= 0.0 and (u + v) <= 1.0


def triangulated(geo: MeshGeometry) -> MeshGeometry:
    from .mesh import MeshGeometry
    from .topology import calc_edges, edge_keys

    triangles, tri_face = triangulate(geo)
    result = MeshGeometry()
    result.resize_domain("POINT", geo.num_verts)
    result.positions[...] = geo.positions
    result.resize_domain("CORNER", int(triangles.size))
    corner_source = triangles.reshape(-1)
    result.corner_verts[...] = geo.corner_verts[corner_source]
    starts = np.arange(0, int(triangles.size), 3, dtype=np.int64)
    result.set_face_offsets(starts)
    calc_edges(result, keep_existing=False)

    for attr in geo.attributes:
        if attr.name in ("position", ".edge_verts", ".corner_vert", ".corner_edge"):
            continue
        if attr.domain == "POINT":
            target = result.attributes.new(attr.name, attr.data_type, "POINT")
            target.data[...] = attr.data
        elif attr.domain == "FACE":
            target = result.attributes.new(attr.name, attr.data_type, "FACE")
            target.data[...] = attr.data[tri_face]
        elif attr.domain == "CORNER":
            target = result.attributes.new(attr.name, attr.data_type, "CORNER")
            target.data[...] = attr.data[corner_source]
        else:
            target = result.attributes.new(attr.name, attr.data_type, "EDGE")
            source_keys = {tuple(int(v) for v in row): i for i, row in enumerate(edge_keys(geo.edges))}
            values = attr.data
            for index, (a, b) in enumerate(edge_keys(result.edges)):
                source = source_keys.get((int(a), int(b)))
                if source is not None:
                    target.data[index] = values[source]
    return result
