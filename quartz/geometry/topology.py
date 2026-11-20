from __future__ import annotations

from typing import Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .mesh import MeshGeometry


def edge_keys(edges: np.ndarray) -> np.ndarray:
    data = np.asarray(edges, dtype=np.int32).reshape(-1, 2)
    return np.sort(data, axis=1)


def face_edge_keys(geo: MeshGeometry, face_index: int) -> list[tuple[int, int]]:
    if face_index < 0 or face_index >= geo.num_faces:
        raise IndexError(f"face index {face_index} out of range")
    start = int(geo.face_offsets[face_index])
    end = int(geo.face_offsets[face_index + 1])
    verts = [int(value) for value in geo.corner_verts[start:end]]
    out: list[tuple[int, int]] = []
    for i, a in enumerate(verts):
        b = verts[(i + 1) % len(verts)]
        out.append((a, b) if a <= b else (b, a))
    return out


def faces_to_offsets(
    faces: Sequence[Sequence[int]],
) -> tuple[np.ndarray, np.ndarray]:
    sizes = [len(face) for face in faces]
    offsets = np.zeros(len(sizes) + 1, dtype=np.int32)
    if sizes:
        offsets[1:] = np.cumsum(sizes, dtype=np.int64)
        corners = np.concatenate([np.asarray(face, dtype=np.int32) for face in faces])
    else:
        corners = np.zeros(0, dtype=np.int32)
    return offsets, corners


def calc_edges(geo: MeshGeometry, *, keep_existing: bool = True) -> None:
    lookup: dict[tuple[int, int], int] = {}
    rows: list[tuple[int, int]] = []

    if keep_existing:
        for a, b in geo.edges:
            key = (int(a), int(b))
            key = key if key[0] <= key[1] else (key[1], key[0])
            if key not in lookup:
                lookup[key] = len(rows)
                rows.append(key)

    offsets = geo.face_offsets
    verts = geo.corner_verts
    for face in range(geo.num_faces):
        start, end = int(offsets[face]), int(offsets[face + 1])
        face_verts = verts[start:end]
        count = len(face_verts)
        for i in range(count):
            a = int(face_verts[i])
            b = int(face_verts[(i + 1) % count])
            key = (a, b) if a <= b else (b, a)
            if key not in lookup:
                lookup[key] = len(rows)
                rows.append(key)

    geo.resize_domain("EDGE", len(rows))
    if rows:
        geo.edges[...] = np.asarray(rows, dtype=np.int32)

    corner_edges = np.empty(geo.num_corners, dtype=np.int32)
    for face in range(geo.num_faces):
        start, end = int(offsets[face]), int(offsets[face + 1])
        face_verts = verts[start:end]
        count = len(face_verts)
        for i in range(count):
            a = int(face_verts[i])
            b = int(face_verts[(i + 1) % count])
            key = (a, b) if a <= b else (b, a)
            corner_edges[start + i] = lookup[key]
    if geo.num_corners:
        geo.corner_edges[...] = corner_edges


def loose_edges(geo: MeshGeometry) -> np.ndarray:
    used = np.zeros(geo.num_edges, dtype=bool)
    if geo.num_corners:
        used[geo.corner_edges] = True
    return ~used


def loose_verts(geo: MeshGeometry) -> np.ndarray:
    used = np.zeros(geo.num_verts, dtype=bool)
    if geo.num_edges:
        used[geo.edges.reshape(-1)] = True
    return ~used


def flip_faces(geo: MeshGeometry, mask: np.ndarray | None = None) -> None:
    selected = (
        np.ones(geo.num_faces, dtype=bool)
        if mask is None
        else np.asarray(mask, dtype=bool).reshape(-1)
    )
    if selected.size != geo.num_faces:
        raise ValueError("mask must have one entry per face")
    verts = geo.corner_verts
    for face in range(geo.num_faces):
        if not selected[face]:
            continue
        start = int(geo.face_offsets[face])
        end = int(geo.face_offsets[face + 1])
        if end - start > 1:
            verts[start + 1 : end] = verts[start + 1 : end][::-1].copy()
    calc_edges(geo, keep_existing=True)


def join(
    geos: Sequence[MeshGeometry],
    matrices: Sequence[np.ndarray] | None = None,
) -> MeshGeometry:
    from .mesh import MeshGeometry
    from .transform import transform_points

    items = list(geos)
    if not items:
        return MeshGeometry()
    if matrices is None:
        matrices = [np.eye(4)] * len(items)
    if len(matrices) != len(items):
        raise ValueError("matrices must have one entry per geometry")

    domains = ("POINT", "EDGE", "CORNER", "FACE")
    starts: dict[str, list[int]] = {}
    totals: dict[str, int] = {}
    for domain in domains:
        running = 0
        offsets = []
        for geo in items:
            offsets.append(running)
            running += geo.domain_size(domain)
        starts[domain] = offsets
        totals[domain] = running

    result = MeshGeometry()
    for domain in domains:
        result.resize_domain(domain, totals[domain])

    definitions: dict[str, tuple[str, str]] = {}
    order: list[str] = []
    for geo in items:
        for attr in geo.attributes:
            known = definitions.get(attr.name)
            if known is None:
                definitions[attr.name] = (attr.domain, attr.data_type)
                order.append(attr.name)
            elif known != (attr.domain, attr.data_type):
                raise ValueError(f"attribute {attr.name!r} has conflicting definitions")

    for name in order:
        domain, data_type = definitions[name]
        target = result.attributes.get(name)
        if target is None:
            target = result.attributes.new(name, data_type, domain)
        for index, geo in enumerate(items):
            attr = geo.attributes.get(name)
            count = geo.domain_size(domain)
            if attr is None or count == 0:
                continue
            values = attr.data
            if name == "position":
                values = transform_points(values, matrices[index])
            elif name in (".edge_verts", ".corner_vert"):
                values = values.astype(np.int64) + starts["POINT"][index]
            elif name == ".corner_edge":
                values = values.astype(np.int64) + starts["EDGE"][index]
            target.data[starts[domain][index] : starts[domain][index] + count] = values

    face_starts = [0]
    for geo in items:
        for size in geo.face_sizes():
            face_starts.append(face_starts[-1] + int(size))
    result.set_face_offsets(np.asarray(face_starts[:-1], dtype=np.int64))
    return result


def merge_by_distance(geo: MeshGeometry, distance: float) -> np.ndarray:
    if distance < 0:
        raise ValueError("distance cannot be negative")
    positions = geo.positions.astype(np.float64)
    count = geo.num_verts
    mapping = np.arange(count, dtype=np.int32)
    if count == 0 or distance == 0:
        return mapping
    cell_size = float(distance)
    cells: dict[tuple[int, int, int], list[int]] = {}
    for index in range(count):
        point = positions[index]
        cell = tuple(int(np.floor(point[axis] / cell_size)) for axis in range(3))
        found = -1
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for candidate in cells.get(
                        (cell[0] + dx, cell[1] + dy, cell[2] + dz), ()
                    ):
                        if np.linalg.norm(point - positions[candidate]) <= distance:
                            found = candidate
                            break
                    if found >= 0:
                        break
                if found >= 0:
                    break
            if found >= 0:
                break
        if found >= 0:
            mapping[index] = mapping[found]
        else:
            cells.setdefault(cell, []).append(index)
    representatives = np.unique(mapping)
    compact = {int(old): new for new, old in enumerate(representatives)}
    return np.array([compact[int(value)] for value in mapping], dtype=np.int32)
