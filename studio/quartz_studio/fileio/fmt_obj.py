from __future__ import annotations

import math
import os

import numpy as np

from ..scene import Mesh
from .model import Document, Node, baked_mesh, require_finite, triangulate, write_atomic
from .registry import FileFormat, FileFormatError, name_error, register

APP_NAME = "Quartz Studio"


class _Block:
    def __init__(self, name: str, from_object: bool) -> None:
        self.name = name
        self.from_object = from_object
        self.polygons: list[tuple[int, ...]] = []
        self.loose: list[tuple[int, int]] = []

    def empty(self) -> bool:
        return not self.polygons and not self.loose


def _scale(options: dict) -> float:
    value = float(options.get("scale", 1.0))
    if not math.isfinite(value) or value <= 0.0:
        raise FileFormatError("scale must be a positive number")
    return value


def _object_name(name: str) -> str:
    return " ".join(str(name).split()) or "Object"


def save(path: str, document: Document, options: dict) -> None:
    scale = _scale(options)
    triangles = bool(options.get("triangulate", False))
    out: list[str] = [f"# Exported by {APP_NAME}"]
    base = 0
    normal_index = 0
    for node in document.nodes:
        mesh = baked_mesh(node)
        if triangles:
            _, tris = triangulate(mesh)
            polygons = [tuple(int(i) for i in tri) for tri in tris]
        else:
            polygons = mesh.polygons
        points = mesh.points * scale
        require_finite(path, node, points)
        normals = Mesh(points, polygons).polygon_normals()
        out.append("o " + _object_name(node.name))
        out.extend(f"v {x!r} {y!r} {z!r}" for x, y, z in points.tolist())
        vn_lines: list[str] = []
        f_lines: list[str] = []
        for k, poly in enumerate(polygons):
            nx, ny, nz = normals[k].tolist()
            corners: list[str] = []
            for index in poly:
                normal_index += 1
                vn_lines.append(f"vn {nx!r} {ny!r} {nz!r}")
                corners.append(f"{base + index + 1}//{normal_index}")
            f_lines.append("f " + " ".join(corners))
        out.extend(vn_lines)
        out.extend(f_lines)
        out.extend(f"l {base + a + 1} {base + b + 1}" for a, b in mesh.loose_edges)
        base += len(points)
    write_atomic(path, ("\n".join(out) + "\n").encode("utf-8"))


def _numbers(args: list[str], low: int, high: int, number: int, keyword: str) -> list[float]:
    if not low <= len(args) <= high:
        raise FileFormatError(f"line {number}: {keyword} needs {low} to {high} numbers")
    try:
        values = [float(a) for a in args]
    except ValueError:
        raise FileFormatError(f"line {number}: {keyword} has a value that is not a number") from None
    if not all(math.isfinite(v) for v in values):
        raise FileFormatError(f"line {number}: {keyword} has a value that is not finite")
    return values


def _resolve(text: str, count: int, number: int, what: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise FileFormatError(f"line {number}: {what} index {text!r} is not an integer") from None
    if value > 0:
        index = value - 1
    elif value < 0:
        index = count + value
    else:
        index = -1
    if not 0 <= index < count:
        raise FileFormatError(f"line {number}: {what} index {text} is out of range")
    return index


def _reference(token: str, vertices: int, texcoords: int, normals: int, number: int) -> int:
    parts = token.split("/")
    if len(parts) > 3:
        raise FileFormatError(f"line {number}: bad vertex reference {token!r}")
    index = _resolve(parts[0], vertices, number, "vertex")
    if len(parts) > 1 and parts[1]:
        _resolve(parts[1], texcoords, number, "texture")
    if len(parts) > 2 and parts[2]:
        _resolve(parts[2], normals, number, "normal")
    return index


def _collapse(indices: list[int]) -> list[int]:
    out: list[int] = []
    for index in indices:
        if not out or out[-1] != index:
            out.append(index)
    while len(out) > 1 and out[-1] == out[0]:
        out.pop()
    return out


def _open_block(blocks: list[_Block], current: _Block | None, key: str, args: list[str],
                stem: str) -> _Block:
    name = " ".join(args) or stem
    if current is not None and current.empty():
        if not (key == "g" and current.from_object):
            current.name = name
            current.from_object = key == "o"
        return current
    block = _Block(name, key == "o")
    blocks.append(block)
    return block


def _node(name: str, polygons: list[tuple[int, ...]], loose: list[tuple[int, int]],
          points: np.ndarray) -> Node:
    used = sorted({i for poly in polygons for i in poly} | {i for edge in loose for i in edge})
    local = {g: k for k, g in enumerate(used)}
    selected = points[np.array(used, dtype=np.int64)]
    mesh = Mesh(selected,
                [tuple(local[i] for i in poly) for poly in polygons],
                [(local[a], local[b]) for a, b in loose])
    return Node(name, mesh)


def _logical_lines(handle):
    pending = ""
    start = 0
    for number, raw in enumerate(handle, 1):
        text = raw.rstrip("\r\n")
        if not pending:
            start = number
        if text.endswith("\\"):
            pending += text[:-1] + " "
            continue
        yield start, pending + text
        pending = ""
    if pending:
        yield start, pending


def _words(text: str) -> list[str]:
    stripped = text.lstrip()
    if stripped.startswith("#"):
        return []
    words = stripped.split(None, 1)
    if words and words[0] in ("o", "g"):
        return words[:1] + (words[1].split() if len(words) > 1 else [])
    return text.split("#", 1)[0].split()


def load(path: str) -> Document:
    try:
        return _load(path)
    except FileFormatError as exc:
        raise name_error(os.path.basename(path), exc) from None


def _load(path: str) -> Document:
    label = os.path.basename(path)
    stem = os.path.splitext(label)[0] or "Object"
    vertices: list[list[float]] = []
    texcoords = 0
    normals = 0
    blocks: list[_Block] = []
    current: _Block | None = None
    with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
        for number, text in _logical_lines(handle):
            words = _words(text)
            if not words:
                continue
            key, args = words[0], words[1:]
            if key == "v":
                vertices.append(_numbers(args, 3, 7, number, "v")[:3])
            elif key == "vn":
                _numbers(args, 3, 3, number, "vn")
                normals += 1
            elif key == "vt":
                _numbers(args, 1, 3, number, "vt")
                texcoords += 1
            elif key in ("o", "g"):
                current = _open_block(blocks, current, key, args, stem)
            elif key == "f":
                if len(args) < 3:
                    raise FileFormatError(f"line {number}: a face needs at least 3 vertices")
                if current is None:
                    current = _Block(stem, False)
                    blocks.append(current)
                refs = [_reference(t, len(vertices), texcoords, normals, number) for t in args]
                indices = _collapse(refs)
                if len(indices) >= 3:
                    current.polygons.append(tuple(indices))
            elif key == "l":
                if len(args) < 2:
                    raise FileFormatError(f"line {number}: a line needs at least 2 vertices")
                if current is None:
                    current = _Block(stem, False)
                    blocks.append(current)
                refs = [_reference(t, len(vertices), texcoords, normals, number) for t in args]
                current.loose.extend((a, b) for a, b in zip(refs, refs[1:]) if a != b)
    if not vertices:
        raise FileFormatError(f"{label}: no vertices")
    points = np.array(vertices, dtype=float).reshape(-1, 3)
    kept = [b for b in blocks if not b.empty()]
    if not kept:
        name = blocks[0].name if blocks else stem
        return Document([Node(name, Mesh(points, []))], {"unit": "cm"})
    nodes = [_node(b.name, b.polygons, b.loose, points) for b in kept]
    return Document(nodes, {"unit": "cm"})


register(FileFormat("obj", "Wavefront OBJ", (".obj",), load, save,
                    "Wavefront OBJ with objects, normals and lines"))
