from __future__ import annotations

import math
import os
import struct

import numpy as np

from ..scene import Mesh
from .model import (Document, Node, baked_mesh, from_z_up, require_finite, to_z_up, weld,
                    write_atomic)
from .registry import FileFormat, FileFormatError, register

_CODES = {
    "char": "b", "int8": "b", "uchar": "B", "uint8": "B",
    "short": "h", "int16": "h", "ushort": "H", "uint16": "H",
    "int": "i", "int32": "i", "uint": "I", "uint32": "I",
    "int64": "q", "uint64": "Q",
    "float": "f", "float32": "f", "double": "d", "float64": "d",
}
_NUMPY = {"b": "i1", "B": "u1", "h": "i2", "H": "u2", "i": "i4", "I": "u4",
          "q": "i8", "Q": "u8", "f": "f4", "d": "f8"}
_INTEGER_CODES = "bBhHiIqQ"
_FLOAT_CODES = "fd"
_ORDERS = {"ascii": "", "binary_little_endian": "<", "binary_big_endian": ">"}
_INDEX_PROPERTIES = ("vertex_indices", "vertex_index")


def _scale(options: dict) -> float:
    value = float(options.get("scale", 1.0))
    if not math.isfinite(value) or value <= 0.0:
        raise FileFormatError("scale must be a positive number")
    return value


def save(path: str, document: Document, options: dict) -> None:
    scale = _scale(options)
    chunks: list[np.ndarray] = []
    faces: list[list[int]] = []
    edges: list[tuple[int, int]] = []
    base = 0
    for node in document.nodes:
        mesh = baked_mesh(node)
        scaled = mesh.points * scale
        require_finite(path, node, scaled)
        chunks.append(to_z_up(scaled))
        for poly in mesh.polygons:
            faces.append([base + i for i in poly])
        for a, b in mesh.loose_edges:
            edges.append((base + a, base + b))
        base += len(mesh.points)
    points = np.vstack(chunks) if chunks else np.zeros((0, 3))
    longest = max((len(f) for f in faces), default=0)
    count_type = "uchar" if longest <= 255 else "int"
    lines = [
        "ply",
        "format ascii 1.0",
        "comment Exported by Quartz Studio",
        f"element vertex {len(points)}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {len(faces)}",
        f"property list {count_type} int vertex_indices",
    ]
    if edges:
        lines.extend([f"element edge {len(edges)}", "property int vertex1", "property int vertex2"])
    lines.append("end_header")
    lines.extend(f"{x!r} {y!r} {z!r}" for x, y, z in points.tolist())
    lines.extend(str(len(f)) + " " + " ".join(str(i) for i in f) for f in faces)
    lines.extend(f"{a} {b}" for a, b in edges)
    write_atomic(path, ("\n".join(lines) + "\n").encode("utf-8"))


def _property(words: list[str], line_no: int, label: str) -> dict:
    if len(words) == 3 and words[1] in _CODES:
        return {"name": words[2], "list": False, "type": _CODES[words[1]]}
    if (len(words) == 5 and words[1] == "list" and words[2] in _CODES
            and _CODES[words[2]] in _INTEGER_CODES and words[3] in _CODES):
        return {"name": words[4], "list": True, "count": _CODES[words[2]], "type": _CODES[words[3]]}
    raise FileFormatError(f"{label}: line {line_no}: bad property line")


def _parse_header(data: bytes, label: str) -> tuple[str, list[dict], bytes, int]:
    position = 0
    line_no = 0
    fmt: str | None = None
    elements: list[dict] = []
    while True:
        end = data.find(b"\n", position)
        if end < 0:
            raise FileFormatError(f"{label}: line {line_no + 1}: header is not closed by end_header")
        words = data[position:end].decode("ascii", errors="replace").split()
        position = end + 1
        line_no += 1
        if line_no == 1:
            if words != ["ply"]:
                raise FileFormatError(f"{label}: line 1: not a PLY file")
            continue
        if not words:
            continue
        key = words[0]
        if key == "end_header":
            break
        if key == "format":
            if len(words) < 2 or words[1] not in _ORDERS:
                raise FileFormatError(f"{label}: line {line_no}: unknown PLY format")
            fmt = words[1]
        elif key == "element":
            if len(words) != 3 or not words[2].isdigit():
                raise FileFormatError(f"{label}: line {line_no}: bad element line")
            elements.append({"name": words[1], "count": int(words[2]), "props": []})
        elif key == "property":
            if not elements:
                raise FileFormatError(f"{label}: line {line_no}: property before any element")
            elements[-1]["props"].append(_property(words, line_no, label))
        elif key not in ("comment", "obj_info"):
            raise FileFormatError(f"{label}: line {line_no}: unknown header keyword {key!r}")
    if fmt is None:
        raise FileFormatError(f"{label}: line {line_no}: missing format line")
    return fmt, elements, data[position:], line_no


def _integer(token: str, number: int, label: str) -> int:
    try:
        return int(token)
    except ValueError:
        raise FileFormatError(f"{label}: line {number}: {token!r} is not an integer") from None


def _scalar(token: str, code: str, number: int, label: str) -> float | int:
    if code in _FLOAT_CODES:
        try:
            value = float(token)
        except ValueError:
            raise FileFormatError(f"{label}: line {number}: {token!r} is not a number") from None
        if not math.isfinite(value):
            raise FileFormatError(f"{label}: line {number}: value is not finite")
        return value
    return _integer(token, number, label)


def _check_indices(element: str, prop: str, values, vertex_count: int, where: str, label: str) -> None:
    if element == "face" and prop in _INDEX_PROPERTIES:
        for value in values:
            if not 0 <= value < vertex_count:
                raise FileFormatError(f"{label}: {where}: vertex index {value} is out of range")


def _read_ascii(body: bytes, first_line: int, elements: list[dict], label: str,
                vertex_count: int) -> dict:
    lines = body.decode("utf-8", errors="replace").splitlines()
    cursor = 0
    result: dict = {}
    for element in elements:
        name = element["name"]
        columns: dict[str, list] = {p["name"]: [] for p in element["props"]}
        for _ in range(element["count"]):
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
            if cursor >= len(lines):
                raise FileFormatError(f"{label}: unexpected end of file in element {name}")
            number = first_line + cursor + 1
            tokens = lines[cursor].split()
            cursor += 1
            pos = 0
            for prop in element["props"]:
                if prop["list"]:
                    if pos >= len(tokens):
                        raise FileFormatError(f"{label}: line {number}: missing list length")
                    length = _integer(tokens[pos], number, label)
                    pos += 1
                    if length < 0 or pos + length > len(tokens):
                        raise FileFormatError(f"{label}: line {number}: list of {length} values does not fit")
                    values = tuple(_scalar(t, prop["type"], number, label) for t in tokens[pos:pos + length])
                    pos += length
                    _check_indices(name, prop["name"], values, vertex_count, f"line {number}", label)
                    columns[prop["name"]].append(values)
                else:
                    if pos >= len(tokens):
                        raise FileFormatError(f"{label}: line {number}: missing value for {prop['name']}")
                    columns[prop["name"]].append(_scalar(tokens[pos], prop["type"], number, label))
                    pos += 1
            if pos != len(tokens):
                raise FileFormatError(f"{label}: line {number}: {len(tokens) - pos} extra values")
        result[name] = (element["count"], columns)
    return result


def _record_dtype(props: list[dict], order: str, label: str) -> np.dtype:
    try:
        return np.dtype([(p["name"], order + _NUMPY[p["type"]]) for p in props])
    except (ValueError, TypeError):
        raise FileFormatError(f"{label}: invalid property list") from None


def _unpack(fmt: str, body: bytes, pos: int, label: str, name: str) -> tuple[tuple, int]:
    size = struct.calcsize(fmt)
    if pos + size > len(body):
        raise FileFormatError(f"{label}: unexpected end of file in element {name}")
    return struct.unpack_from(fmt, body, pos), pos + size


def _read_binary(body: bytes, elements: list[dict], order: str, label: str,
                 vertex_count: int) -> dict:
    pos = 0
    result: dict = {}
    for element in elements:
        name = element["name"]
        props = element["props"]
        count = element["count"]
        if not any(p["list"] for p in props):
            columns: dict = {}
            if props and count:
                dtype = _record_dtype(props, order, label)
                size = dtype.itemsize * count
                if pos + size > len(body):
                    raise FileFormatError(f"{label}: unexpected end of file in element {name}")
                records = np.frombuffer(body, dtype=dtype, count=count, offset=pos)
                pos += size
                columns = {p["name"]: records[p["name"]] for p in props}
            result[name] = (count, columns)
            continue
        columns = {p["name"]: [] for p in props}
        for k in range(count):
            row: dict = {}
            for prop in props:
                if prop["list"]:
                    (length,), pos = _unpack(order + prop["count"], body, pos, label, name)
                    itemsize = struct.calcsize(order + prop["type"])
                    if length < 0 or pos + length * itemsize > len(body):
                        raise FileFormatError(f"{label}: unexpected end of file in element {name}")
                    values, pos = _unpack(f"{order}{length}{prop['type']}", body, pos, label, name)
                    _check_indices(name, prop["name"], values, vertex_count, f"element {k + 1}", label)
                    row[prop["name"]] = values
                else:
                    (value,), pos = _unpack(order + prop["type"], body, pos, label, name)
                    row[prop["name"]] = value
            for key, value in row.items():
                columns[key].append(value)
        result[name] = (count, columns)
    return result


def _collapse(indices: list[int]) -> list[int]:
    out: list[int] = []
    for index in indices:
        if not out or out[-1] != index:
            out.append(index)
    while len(out) > 1 and out[-1] == out[0]:
        out.pop()
    return out


def _geometry(result: dict, label: str):
    if "vertex" not in result:
        raise FileFormatError(f"{label}: no vertex element")
    _, columns = result["vertex"]
    for axis in ("x", "y", "z"):
        if axis not in columns:
            raise FileFormatError(f"{label}: vertex element has no {axis} property")
    points = np.column_stack([np.asarray(columns[a], dtype=float) for a in ("x", "y", "z")])
    points = points.reshape(-1, 3)
    if not np.isfinite(points).all():
        raise FileFormatError(f"{label}: vertex coordinates are not finite")
    raw_polygons: list[list[int]] = []
    raw_edges: list[tuple[int, int]] = []
    if "face" in result:
        count, columns = result["face"]
        listed = columns.get("vertex_indices", columns.get("vertex_index"))
        if listed is None:
            if count:
                raise FileFormatError(f"{label}: face element has no vertex_indices list")
            listed = []
        raw_polygons = [[int(i) for i in values] for values in listed]
    if "edge" in result:
        count, columns = result["edge"]
        if count and "vertex1" in columns and "vertex2" in columns:
            first = [int(v) for v in columns["vertex1"]]
            second = [int(v) for v in columns["vertex2"]]
            for value in first + second:
                if not 0 <= value < len(points):
                    raise FileFormatError(f"{label}: edge vertex index {value} is out of range")
            raw_edges = list(zip(first, second))
    unique, index = weld(points, 0.0)
    polygons: list[tuple[int, ...]] = []
    for values in raw_polygons:
        indices = _collapse([int(index[i]) for i in values])
        if len(indices) >= 3:
            polygons.append(tuple(indices))
    loose = []
    seen = set()
    for a, b in raw_edges:
        ia, ib = int(index[a]), int(index[b])
        key = (min(ia, ib), max(ia, ib))
        if ia != ib and key not in seen:
            seen.add(key)
            loose.append((ia, ib))
    if not polygons and not loose:
        return from_z_up(unique), [], []
    used = np.array(sorted({i for poly in polygons for i in poly} | {i for e in loose for i in e}),
                    dtype=np.int64)
    local = np.full(len(unique), -1, dtype=np.int64)
    local[used] = np.arange(len(used))
    remapped = [tuple(int(local[i]) for i in poly) for poly in polygons]
    remapped_edges = [(int(local[a]), int(local[b])) for a, b in loose]
    return from_z_up(unique[used]), remapped, remapped_edges


def load(path: str) -> Document:
    label = os.path.basename(path)
    stem = os.path.splitext(label)[0] or "Object"
    with open(path, "rb") as handle:
        data = handle.read()
    fmt, elements, body, header_lines = _parse_header(data, label)
    vertex_count = next((e["count"] for e in elements if e["name"] == "vertex"), 0)
    if fmt == "ascii":
        result = _read_ascii(body, header_lines, elements, label, vertex_count)
    else:
        result = _read_binary(body, elements, _ORDERS[fmt], label, vertex_count)
    points, polygons, loose = _geometry(result, label)
    if not len(points):
        raise FileFormatError(f"{label}: no vertices")
    return Document([Node(stem, Mesh(points, polygons, loose))], {"unit": "cm"})


register(FileFormat("ply", "Stanford PLY", (".ply",), load, save,
                    "Stanford PLY, ASCII export, ASCII or binary import, point clouds"))
