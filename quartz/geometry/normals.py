from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .mesh import MeshGeometry


def _newell(points: np.ndarray) -> np.ndarray:
    following = np.roll(points, -1, axis=0)
    nx = np.sum((points[:, 1] - following[:, 1]) * (points[:, 2] + following[:, 2]))
    ny = np.sum((points[:, 2] - following[:, 2]) * (points[:, 0] + following[:, 0]))
    nz = np.sum((points[:, 0] - following[:, 0]) * (points[:, 1] + following[:, 1]))
    return np.array([nx, ny, nz], dtype=np.float64)


def _face_point_lists(geo: MeshGeometry):
    positions = geo.positions.astype(np.float64)
    verts = geo.corner_verts
    offsets = geo.face_offsets
    for face in range(geo.num_faces):
        start, end = int(offsets[face]), int(offsets[face + 1])
        if end - start < 3:
            continue
        yield face, start, end, positions[verts[start:end]]


def face_normals(geo: MeshGeometry) -> np.ndarray:
    out = np.zeros((geo.num_faces, 3), dtype=np.float64)
    for face, _start, _end, points in _face_point_lists(geo):
        normal = _newell(points)
        length = float(np.linalg.norm(normal))
        if length > 0.0:
            out[face] = normal / length
    return out.astype(np.float32)


def vertex_normals(geo: MeshGeometry) -> np.ndarray:
    normals = face_normals(geo).astype(np.float64)
    out = np.zeros((geo.num_verts, 3), dtype=np.float64)
    for face, _start, _end, points in _face_point_lists(geo):
        count = points.shape[0]
        for i in range(count):
            previous = points[i - 1] - points[i]
            following = points[(i + 1) % count] - points[i]
            len_a = float(np.linalg.norm(previous))
            len_b = float(np.linalg.norm(following))
            if len_a <= 0.0 or len_b <= 0.0:
                weight = 1.0
            else:
                cosine = float(np.dot(previous, following) / (len_a * len_b))
                weight = float(np.arccos(min(1.0, max(-1.0, cosine))))
            out[geo.corner_verts[int(geo.face_offsets[face]) + i]] += normals[face] * weight
    lengths = np.linalg.norm(out, axis=1)
    nonzero = lengths > 0.0
    out[nonzero] /= lengths[nonzero, None]
    loose = ~nonzero
    if loose.any():
        positions = geo.positions.astype(np.float64)[loose]
        lengths = np.linalg.norm(positions, axis=1)
        safe = lengths > 0.0
        normalized = np.zeros_like(positions)
        normalized[safe] = positions[safe] / lengths[safe, None]
        out[loose] = normalized
    return out.astype(np.float32)


def corner_normals(geo: MeshGeometry, *, sharp_face: np.ndarray | None = None) -> np.ndarray:
    face_n = face_normals(geo).astype(np.float64)
    if sharp_face is None:
        attribute = geo.attributes.get("sharp_face")
        if attribute is None:
            sharp = np.ones(geo.num_faces, dtype=bool)
        else:
            sharp = np.asarray(attribute.data, dtype=bool).reshape(-1)
    else:
        sharp = np.asarray(sharp_face, dtype=bool).reshape(-1)
    if sharp.size != geo.num_faces:
        raise ValueError("sharp_face must have one entry per face")
    smooth = vertex_normals(geo)
    out = np.empty((geo.num_corners, 3), dtype=np.float64)
    offsets = geo.face_offsets
    for face in range(geo.num_faces):
        start, end = int(offsets[face]), int(offsets[face + 1])
        if sharp[face]:
            out[start:end] = face_n[face]
        else:
            out[start:end] = smooth[geo.corner_verts[start:end]]
    return out.astype(np.float32)


def face_centers(geo: MeshGeometry) -> np.ndarray:
    out = np.zeros((geo.num_faces, 3), dtype=np.float64)
    verts = geo.corner_verts
    offsets = geo.face_offsets
    positions = geo.positions.astype(np.float64)
    for face in range(geo.num_faces):
        start, end = int(offsets[face]), int(offsets[face + 1])
        if end > start:
            out[face] = positions[verts[start:end]].mean(axis=0)
    return out.astype(np.float32)


def face_areas(geo: MeshGeometry) -> np.ndarray:
    out = np.zeros(geo.num_faces, dtype=np.float64)
    for face, _start, _end, points in _face_point_lists(geo):
        out[face] = 0.5 * float(np.linalg.norm(_newell(points)))
    return out.astype(np.float32)
