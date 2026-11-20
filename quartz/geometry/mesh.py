from __future__ import annotations

from typing import Sequence

import numpy as np

from .attributes import AttributeStore

_REQUIRED_ATTRIBUTES: tuple[tuple[str, str, str], ...] = (
    ("position", "FLOAT_VECTOR", "POINT"),
    (".edge_verts", "INT32_2D", "EDGE"),
    (".corner_vert", "INT", "CORNER"),
    (".corner_edge", "INT", "CORNER"),
)


class MeshGeometry:

    face_offsets: np.ndarray
    attributes: AttributeStore

    def __init__(self) -> None:
        self.face_offsets = np.zeros(1, dtype=np.int32)
        self.attributes = AttributeStore(self.domain_size)
        for name, data_type, domain in _REQUIRED_ATTRIBUTES:
            self.attributes.new(name, data_type, domain)

    @classmethod
    def empty(cls) -> MeshGeometry:
        return cls()


    @property
    def positions(self) -> np.ndarray:
        return self.attributes["position"].data

    @property
    def edges(self) -> np.ndarray:
        return self.attributes[".edge_verts"].data

    @property
    def corner_verts(self) -> np.ndarray:
        return self.attributes[".corner_vert"].data

    @property
    def corner_edges(self) -> np.ndarray:
        return self.attributes[".corner_edge"].data


    def domain_size(self, domain: str) -> int:
        if domain == "FACE":
            return max(int(self.face_offsets.shape[0]) - 1, 0)
        if domain == "POINT":
            attr = self.attributes.get("position")
        elif domain == "EDGE":
            attr = self.attributes.get(".edge_verts")
        elif domain == "CORNER":
            attr = self.attributes.get(".corner_vert")
        else:
            raise ValueError(f"unknown attribute domain {domain!r}")
        return 0 if attr is None else int(attr.data.shape[0])

    @property
    def num_verts(self) -> int:
        return self.domain_size("POINT")

    @property
    def num_edges(self) -> int:
        return self.domain_size("EDGE")

    @property
    def num_faces(self) -> int:
        return self.domain_size("FACE")

    @property
    def num_corners(self) -> int:
        return self.domain_size("CORNER")

    def face_sizes(self) -> np.ndarray:
        return np.diff(self.face_offsets).astype(np.int32, copy=False)

    def corner_to_face(self) -> np.ndarray:
        return np.repeat(
            np.arange(self.num_faces, dtype=np.int32), self.face_sizes()
        )


    @classmethod
    def from_pydata(
        cls,
        vertices: Sequence[Sequence[float]] | np.ndarray,
        edges: Sequence[Sequence[int]] = (),
        faces: Sequence[Sequence[int]] = (),
        *,
        shade_flat: bool = True,
    ) -> MeshGeometry:
        geo = cls()
        verts = np.asarray(vertices, dtype=np.float32)
        if verts.size == 0:
            verts = verts.reshape(0, 3)
        if verts.ndim != 2 or verts.shape[1] != 3:
            raise ValueError("vertices must be a sequence of 3D coordinates")
        num_verts = int(verts.shape[0])
        geo.resize_domain("POINT", num_verts)
        geo.positions[...] = verts

        edge_rows: list[tuple[int, int]] = []
        seen_edges: set[tuple[int, int]] = set()
        for edge in edges:
            pair = tuple(int(value) for value in edge)
            if len(pair) != 2:
                raise ValueError("edges must have exactly two vertex indices")
            for value in pair:
                if value < 0 or value >= num_verts:
                    raise ValueError(f"edge vertex index {value} out of range")
            key = (pair[0], pair[1]) if pair[0] <= pair[1] else (pair[1], pair[0])
            if key not in seen_edges:
                seen_edges.add(key)
                edge_rows.append(key)

        corner_rows: list[int] = []
        face_sizes: list[int] = []
        for face in faces:
            indices = [int(value) for value in face]
            if len(indices) < 3:
                raise ValueError("faces must have at least 3 vertex indices")
            for value in indices:
                if value < 0 or value >= num_verts:
                    raise ValueError(f"face vertex index {value} out of range")
            corner_rows.extend(indices)
            face_sizes.append(len(indices))

        geo.resize_domain("CORNER", len(corner_rows))
        if corner_rows:
            geo.corner_verts[...] = np.asarray(corner_rows, dtype=np.int32)
        starts = np.zeros(len(face_sizes), dtype=np.int64)
        if face_sizes:
            starts[1:] = np.cumsum(face_sizes, dtype=np.int64)[:-1]
        geo.set_face_offsets(starts)

        edge_index = {}
        for row in edge_rows:
            edge_index[row] = len(edge_index)

        for face_start, face_end in _face_ranges(geo.face_offsets):
            verts_of_face = geo.corner_verts[face_start:face_end]
            count = len(verts_of_face)
            for i in range(count):
                a = int(verts_of_face[i])
                b = int(verts_of_face[(i + 1) % count])
                key = (a, b) if a <= b else (b, a)
                if key not in edge_index:
                    edge_index[key] = len(edge_index)

        geo.resize_domain("EDGE", len(edge_index))
        if edge_index:
            geo.edges[...] = np.asarray(list(edge_index.keys()), dtype=np.int32)

        corner_edges = np.empty(geo.num_corners, dtype=np.int32)
        for face_start, face_end in _face_ranges(geo.face_offsets):
            verts_of_face = geo.corner_verts[face_start:face_end]
            count = len(verts_of_face)
            for i in range(count):
                a = int(verts_of_face[i])
                b = int(verts_of_face[(i + 1) % count])
                key = (a, b) if a <= b else (b, a)
                corner_edges[face_start + i] = edge_index[key]
        if geo.num_corners:
            geo.corner_edges[...] = corner_edges

        geo.attributes.new(
            ".select_vert", "BOOLEAN", "POINT"
        ).data[...] = False
        geo.attributes.new(
            ".select_edge", "BOOLEAN", "EDGE"
        ).data[...] = False
        geo.attributes.new(
            ".select_poly", "BOOLEAN", "FACE"
        ).data[...] = False
        geo.attributes.new("sharp_face", "BOOLEAN", "FACE").data[...] = bool(shade_flat)
        return geo

    def resize_domain(self, domain: str, size: int) -> None:
        size = int(size)
        if size < 0:
            raise ValueError("domain size cannot be negative")
        if domain == "FACE":
            old = self.face_offsets
            last = int(old[-1]) if old.size else 0
            if size == 0:
                offsets = np.zeros(1, dtype=np.int32)
            else:
                offsets = np.empty(size + 1, dtype=np.int32)
                keep = min(int(old.shape[0]) - 1, size)
                offsets[:keep] = old[:keep]
                offsets[keep:] = last
                offsets[0] = 0
                if size < int(old.shape[0]) - 1:
                    offsets[-1] = last
            self.face_offsets = offsets
            self.attributes.resize("FACE", size)
            return
        self.attributes.resize(domain, size)

    def add_verts(self, count: int) -> slice:
        count = _check_count(count)
        start = self.num_verts
        self.resize_domain("POINT", start + count)
        return slice(start, start + count)

    def add_edges(self, count: int) -> slice:
        count = _check_count(count)
        start = self.num_edges
        self.resize_domain("EDGE", start + count)
        return slice(start, start + count)

    def add_corners(self, count: int) -> slice:
        count = _check_count(count)
        start = self.num_corners
        self.resize_domain("CORNER", start + count)
        return slice(start, start + count)

    def add_faces(self, sizes: Sequence[int] | int) -> slice:
        if isinstance(sizes, (int, np.integer)):
            count = _check_count(sizes)
            start = self.num_faces
            self.resize_domain("FACE", start + count)
            return slice(start, start + count)
        values = [int(size) for size in sizes]
        if any(size <= 0 for size in values):
            raise ValueError("face sizes must be positive")
        start_face = self.num_faces
        start_corner = self.num_corners
        total = sum(values)
        self.resize_domain("CORNER", start_corner + total)
        self.attributes.resize("FACE", start_face + len(values))
        offsets = np.empty(start_face + len(values) + 1, dtype=np.int32)
        offsets[: start_face + 1] = self.face_offsets[: start_face + 1]
        offsets[start_face + 1 :] = start_corner + np.cumsum(values, dtype=np.int64)
        self.face_offsets = offsets
        return slice(start_face, start_face + len(values))

    def set_face_offsets(self, loop_starts: Sequence[int] | np.ndarray) -> None:
        starts = np.asarray(loop_starts, dtype=np.int64).reshape(-1)
        if starts.size == 0:
            if self.num_corners:
                raise ValueError("corners without faces are not allowed")
            self.attributes.resize("FACE", 0)
            self.face_offsets = np.zeros(1, dtype=np.int32)
            return
        if int(starts[0]) != 0:
            raise ValueError("face offsets must start at 0")
        if not np.all(np.diff(starts) >= 0):
            raise ValueError("face offsets must be non-decreasing")
        if int(starts[-1]) > self.num_corners:
            raise ValueError("face offset is beyond the number of corners")
        offsets = np.empty(starts.size + 1, dtype=np.int32)
        offsets[:-1] = starts
        offsets[-1] = self.num_corners
        self.attributes.resize("FACE", int(starts.size))
        self.face_offsets = offsets


    def copy(self) -> MeshGeometry:
        clone = object.__new__(MeshGeometry)
        clone.face_offsets = self.face_offsets.copy()
        clone.attributes = self.attributes.copy(clone.domain_size)
        return clone

    def clear(self) -> None:
        self.face_offsets = np.zeros(1, dtype=np.int32)
        for domain in ("POINT", "EDGE", "FACE", "CORNER"):
            self.attributes.resize(domain, 0)
        self.face_offsets = np.zeros(1, dtype=np.int32)

    def validate(self, *, fix: bool = False) -> tuple[bool, list[str]]:
        problems: list[str] = []
        verts = self.num_verts
        edges = self.num_edges
        corners = self.num_corners

        positions = self.positions
        bad_pos = ~np.isfinite(positions).all(axis=1) if verts else np.zeros(0, bool)
        if bad_pos.any():
            problems.append(f"{int(bad_pos.sum())} non-finite vertex positions")

        offsets = self.face_offsets
        offsets_ok = True
        if offsets.ndim != 1 or offsets.size < 1:
            offsets_ok = False
        else:
            if int(offsets[0]) != 0:
                offsets_ok = False
            if np.any(np.diff(offsets) < 0):
                offsets_ok = False
            if int(offsets[-1]) != corners:
                offsets_ok = False
        if not offsets_ok:
            problems.append("face offsets are invalid")

        sizes = self.face_sizes()
        if np.any(sizes < 3):
            problems.append(f"{int(np.count_nonzero(sizes < 3))} faces with fewer than 3 corners")

        corner_verts = self.corner_verts
        if corners and (corner_verts.min() < 0 or corner_verts.max() >= max(verts, 1)):
            problems.append("corner vertex index out of range")

        edge_verts = self.edges
        if edges:
            if edge_verts.min() < 0 or edge_verts.max() >= max(verts, 1):
                problems.append("edge vertex index out of range")
            degenerate = int(np.count_nonzero(edge_verts[:, 0] == edge_verts[:, 1]))
            if degenerate:
                problems.append(f"{degenerate} degenerate edges")
            keys = np.sort(edge_verts, axis=1)
            if np.unique(keys, axis=0).shape[0] != keys.shape[0]:
                problems.append("duplicate edges")

        if corners and offsets_ok:
            lookup = {}
            if edges:
                for index, (a, b) in enumerate(keys):
                    lookup[(int(a), int(b))] = index
            bad = 0
            for face_start, face_end in _face_ranges(offsets):
                face_corners = corner_verts[face_start:face_end]
                count = len(face_corners)
                for i in range(count):
                    a = int(face_corners[i])
                    b = int(face_corners[(i + 1) % count])
                    key = (a, b) if a <= b else (b, a)
                    expected = lookup.get(key)
                    if expected is None or int(self.corner_edges[face_start + i]) != expected:
                        bad += 1
            if bad:
                problems.append(f"{bad} inconsistent corner edges")

        if not fix or not problems:
            return False, problems

        if bad_pos.any():
            positions[bad_pos] = 0.0

        offs = np.asarray(self.face_offsets, dtype=np.int64).reshape(-1)
        if offs.size == 0:
            offs = np.zeros(1, dtype=np.int64)
        offs = np.clip(offs, 0, corners)
        offs[0] = 0
        offs = np.maximum.accumulate(offs)
        offs[-1] = corners

        num_faces = int(offs.size - 1)
        face_keep = np.zeros(num_faces, dtype=bool)
        corner_keep = np.zeros(corners, dtype=bool)
        new_starts: list[int] = []
        total = 0
        for face in range(num_faces):
            start, end = int(offs[face]), int(offs[face + 1])
            if end - start < 3:
                continue
            face_corners = corner_verts[start:end]
            if face_corners.min() < 0 or face_corners.max() >= verts:
                continue
            face_keep[face] = True
            corner_keep[start:end] = True
            new_starts.append(total)
            total += end - start

        _filter_domain(self.attributes, "CORNER", corner_keep)
        _filter_domain(self.attributes, "FACE", face_keep)
        offsets_new = np.empty(len(new_starts) + 1, dtype=np.int32)
        offsets_new[:-1] = new_starts
        offsets_new[-1] = total
        self.face_offsets = offsets_new

        edge_verts = self.edges
        edge_keep = np.zeros(int(edge_verts.shape[0]), dtype=bool)
        seen: set[tuple[int, int]] = set()
        for index, (a, b) in enumerate(edge_verts):
            a, b = int(a), int(b)
            if a < 0 or b < 0 or a >= verts or b >= verts or a == b:
                continue
            key = (a, b) if a <= b else (b, a)
            if key in seen:
                continue
            seen.add(key)
            edge_keep[index] = True
        _filter_domain(self.attributes, "EDGE", edge_keep)

        from .topology import calc_edges

        calc_edges(self, keep_existing=True)
        return True, problems


def _filter_domain(store: AttributeStore, domain: str, keep: np.ndarray) -> None:
    size = int(np.count_nonzero(keep))
    for attr in store.by_domain(domain):
        if int(attr.data.shape[0]) == keep.shape[0]:
            attr.data = np.ascontiguousarray(attr.data[keep])
    store.resize(domain, size)


def _check_count(count: int) -> int:
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)):
        raise TypeError("count must be an integer")
    count = int(count)
    if count < 0:
        raise ValueError("count cannot be negative")
    return count


def _face_ranges(offsets: np.ndarray):
    for face in range(int(offsets.shape[0]) - 1):
        yield int(offsets[face]), int(offsets[face + 1])
