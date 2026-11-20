from __future__ import annotations

import math
import os
import struct

import numpy as np

from ..scene import Mesh
from .model import (Document, Node, baked_mesh, from_z_up, require_finite, to_z_up, triangulate,
                    write_atomic)
from .registry import FileFormat, FileFormatError, name_error, register

HEADER_BYTES = 80
COUNT_BYTES = 4
RECORD_BYTES = 50
DEGENERATE_AREA = 1e-12
APP_LABEL = b"Quartz Studio binary STL"
RECORD = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])


def _scale(options: dict) -> float:
    value = float(options.get("scale", 1.0))
    if not math.isfinite(value) or value <= 0.0:
        raise FileFormatError("scale must be a positive number")
    return value


def save(path: str, document: Document, options: dict) -> None:
    scale = _scale(options)
    chunks: list[np.ndarray] = []
    for node in document.nodes:
        points, tris = triangulate(baked_mesh(node))
        require_finite(path, node, points * scale)
        if len(tris):
            chunks.append(to_z_up(points * scale)[tris])
    if not chunks:
        raise FileFormatError(f"{os.path.basename(path)}: nothing to export")
    coords = np.concatenate(chunks)
    records = np.zeros(len(coords), dtype=RECORD)
    records["vertices"] = coords
    normal = np.cross(coords[:, 1] - coords[:, 0], coords[:, 2] - coords[:, 0])
    length = np.linalg.norm(normal, axis=1)
    ok = length > 0.0
    normal[ok] /= length[ok][:, None]
    records["normal"] = normal
    header = APP_LABEL.ljust(HEADER_BYTES, b" ")
    write_atomic(path, header + struct.pack("<I", len(coords)) + records.tobytes())


def _binary_size(count: int) -> int:
    return HEADER_BYTES + COUNT_BYTES + RECORD_BYTES * count


def _is_binary(data: bytes) -> bool:
    if len(data) < HEADER_BYTES + COUNT_BYTES:
        return False
    count = struct.unpack_from("<I", data, HEADER_BYTES)[0]
    if len(data) == _binary_size(count):
        return True
    if data[:256].lstrip().startswith(b"solid"):
        return False
    return len(data) > _binary_size(count)


def _binary_coords(data: bytes) -> np.ndarray:
    count = struct.unpack_from("<I", data, HEADER_BYTES)[0]
    if count == 0:
        return np.zeros((0, 3, 3))
    records = np.frombuffer(data, dtype=RECORD, count=count, offset=HEADER_BYTES + COUNT_BYTES)
    coords = np.array(records["vertices"], dtype=float)
    if not np.isfinite(coords).all():
        raise FileFormatError("binary STL has coordinates that are not finite")
    return coords


def _floats(words: list[str], number: int) -> list[float]:
    try:
        values = [float(w) for w in words]
    except ValueError:
        raise FileFormatError(f"line {number}: expected a number") from None
    if not all(math.isfinite(v) for v in values):
        raise FileFormatError(f"line {number}: coordinates must be finite")
    return values


def _ascii_solids(data: bytes, stem: str) -> list[tuple[str, np.ndarray]]:
    text = data.decode("utf-8", errors="replace")
    solids: list[tuple[str, np.ndarray]] = []
    name: str | None = None
    facets: list[list[list[float]]] = []
    facet: list[list[float]] | None = None
    number = 0
    for number, raw in enumerate(text.splitlines(), 1):
        words = raw.split()
        if not words:
            continue
        key = words[0].lower()
        if key == "solid":
            if name is not None:
                raise FileFormatError(f"line {number}: solid starts before the previous endsolid")
            name = " ".join(words[1:]) or stem
            facets = []
        elif key == "facet":
            if name is None or facet is not None:
                raise FileFormatError(f"line {number}: facet outside a solid or inside a facet")
            if len(words) != 5 or words[1].lower() != "normal":
                raise FileFormatError(f"line {number}: facet needs a normal with 3 numbers")
            _floats(words[2:5], number)
            facet = []
        elif key == "vertex":
            if facet is None:
                raise FileFormatError(f"line {number}: vertex outside a facet")
            if len(words) != 4:
                raise FileFormatError(f"line {number}: vertex needs 3 coordinates")
            if len(facet) >= 3:
                raise FileFormatError(f"line {number}: facet has more than 3 vertices")
            facet.append(_floats(words[1:4], number))
        elif key == "endfacet":
            if facet is None or len(facet) != 3:
                raise FileFormatError(f"line {number}: facet needs exactly 3 vertices")
            facets.append(facet)
            facet = None
        elif key in ("outer", "endloop"):
            if facet is None:
                raise FileFormatError(f"line {number}: {words[0]} outside a facet")
        elif key == "endsolid":
            if name is None or facet is not None:
                raise FileFormatError(f"line {number}: endsolid without a matching solid")
            if facets:
                solids.append((name, np.array(facets, dtype=float).reshape(-1, 3, 3)))
            name = None
        else:
            raise FileFormatError(f"line {number}: unexpected {words[0]!r}")
    if name is not None:
        raise FileFormatError(f"line {number}: solid is not closed by endsolid")
    return solids


def _mesh_from_triangles(coords: np.ndarray) -> Mesh | None:
    if not len(coords):
        return None
    unique, inverse = np.unique(coords.reshape(-1, 3), axis=0, return_inverse=True)
    index = np.asarray(inverse, dtype=np.int64).reshape(-1, 3)
    corners = unique[index]
    area = np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    keep = ((index[:, 0] != index[:, 1]) & (index[:, 1] != index[:, 2])
            & (index[:, 0] != index[:, 2]) & (area > DEGENERATE_AREA))
    index = index[keep]
    if not len(index):
        return None
    used, local = np.unique(index, return_inverse=True)
    local = np.asarray(local, dtype=np.int64).reshape(-1, 3)
    return Mesh(from_z_up(unique[used]), local.tolist())


def load(path: str) -> Document:
    try:
        return _load(path)
    except FileFormatError as exc:
        raise name_error(os.path.basename(path), exc) from None


def _load(path: str) -> Document:
    label = os.path.basename(path)
    stem = os.path.splitext(label)[0] or "Object"
    with open(path, "rb") as handle:
        data = handle.read()
    if _is_binary(data):
        solids = [(stem, _binary_coords(data))]
    else:
        solids = _ascii_solids(data, stem)
    nodes = []
    for name, coords in solids:
        mesh = _mesh_from_triangles(coords)
        if mesh is not None:
            nodes.append(Node(name, mesh))
    if not nodes:
        raise FileFormatError(f"{label}: no usable facets")
    return Document(nodes, {"unit": "cm"})


register(FileFormat("stl", "STL", (".stl",), load, save,
                    "Stereolithography triangles, binary export, binary or ASCII import"))
