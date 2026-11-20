from __future__ import annotations

import base64
import binascii
import json
import math
import os
import struct
from urllib.parse import unquote, urlsplit

import numpy as np

from ..scene import Mesh
from .model import Document, Node, compose, decompose, triangulate_ring, weld, write_atomic
from .registry import FileFormat, FileFormatError, register

GENERATOR = "Quartz Studio glTF exporter"
CM_TO_M = 0.01
M_TO_CM = 100.0

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942

ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
COMPONENT_FLOAT = 5126
COMPONENT_UBYTE = 5121
COMPONENT_USHORT = 5123
COMPONENT_UINT = 5125

COMPONENTS = {
    5120: ("i1", 1),
    5121: ("u1", 1),
    5122: ("i2", 2),
    5123: ("u2", 2),
    5125: ("u4", 4),
    5126: ("f4", 4),
}
COMPONENT_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
UNSUPPORTED_REQUIRED = ("KHR_draco_mesh_compression", "EXT_meshopt_compression")
MODE_NAMES = {0: "POINTS", 1: "LINES", 2: "LINE_LOOP", 3: "LINE_STRIP", 4: "TRIANGLES",
              5: "TRIANGLE_STRIP", 6: "TRIANGLE_FAN"}


class _Bad(Exception):
    pass


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise _Bad(message)


def _is_int(value) -> bool:
    return isinstance(value, (int, np.integer)) and not isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool) \
        and math.isfinite(float(value))


def _index(value, count: int, what: str) -> int:
    _need(_is_int(value), f"{what} must be an integer")
    _need(0 <= int(value) < count, f"{what} {value} is out of range (0 to {count - 1})" if count
          else f"{what} {value} refers to nothing")
    return int(value)


def _numbers(value, length: int, what: str) -> list[float]:
    _need(isinstance(value, list) and len(value) == length and all(_is_number(v) for v in value),
          f"{what} must be a list of {length} finite numbers")
    return [float(v) for v in value]


def _quaternion_matrix(x: float, y: float, z: float, w: float) -> np.ndarray:
    n = math.sqrt(x * x + y * y + z * z + w * w)
    _need(n > 1e-12, "rotation quaternion has zero length")
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _matrix_quaternion(q: np.ndarray) -> list[float]:
    trace = q[0, 0] + q[1, 1] + q[2, 2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w, x, y, z = s / 4.0, (q[2, 1] - q[1, 2]) / s, (q[0, 2] - q[2, 0]) / s, (q[1, 0] - q[0, 1]) / s
    elif q[0, 0] > q[1, 1] and q[0, 0] > q[2, 2]:
        s = math.sqrt(1.0 + q[0, 0] - q[1, 1] - q[2, 2]) * 2.0
        w, x, y, z = (q[2, 1] - q[1, 2]) / s, s / 4.0, (q[0, 1] + q[1, 0]) / s, (q[0, 2] + q[2, 0]) / s
    elif q[1, 1] > q[2, 2]:
        s = math.sqrt(1.0 + q[1, 1] - q[0, 0] - q[2, 2]) * 2.0
        w, x, y, z = (q[0, 2] - q[2, 0]) / s, (q[0, 1] + q[1, 0]) / s, s / 4.0, (q[1, 2] + q[2, 1]) / s
    else:
        s = math.sqrt(1.0 + q[2, 2] - q[0, 0] - q[1, 1]) * 2.0
        w, x, y, z = (q[1, 0] - q[0, 1]) / s, (q[0, 2] + q[2, 0]) / s, (q[1, 2] + q[2, 1]) / s, s / 4.0
    n = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / n, y / n, z / n, w / n
    if w < 0.0:
        x, y, z, w = -x, -y, -z, -w
    return [float(x), float(y), float(z), float(w)]


def _trs(local: np.ndarray):
    if not np.isfinite(local).all():
        return None
    if np.abs(local[3] - np.array([0.0, 0.0, 0.0, 1.0])).max() > 1e-9:
        return None
    lin = local[:3, :3]
    scale = np.linalg.norm(lin, axis=0)
    if scale.min() < 1e-9:
        return None
    q = lin / scale
    if np.abs(q.T @ q - np.eye(3)).max() > 1e-6:
        return None
    if np.linalg.det(q) < 0.0:
        k = int(np.argmin(np.diag(q)))
        scale[k] = -scale[k]
        q[:, k] = -q[:, k]
    return local[:3, 3].copy(), _matrix_quaternion(q), scale


class _Builder:
    def __init__(self) -> None:
        self.data = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []

    def add(self, array: np.ndarray, target: int, component: int, kind: str, limits: bool = False) -> int:
        raw = np.ascontiguousarray(array).tobytes()
        offset = len(self.data)
        self.data += raw
        self.data += b"\x00" * (-len(raw) % 4)
        self.views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw), "target": target})
        accessor = {"bufferView": len(self.views) - 1, "byteOffset": 0, "componentType": component,
                    "count": int(len(array)), "type": kind}
        if limits:
            accessor["min"] = [float(v) for v in array.min(axis=0)]
            accessor["max"] = [float(v) for v in array.max(axis=0)]
        self.accessors.append(accessor)
        return len(self.accessors) - 1

    def indices(self, values: np.ndarray, count: int) -> int:
        if count <= 65535:
            return self.add(values.astype("<u2"), ELEMENT_ARRAY_BUFFER, COMPONENT_USHORT, "SCALAR")
        return self.add(values.astype("<u4"), ELEMENT_ARRAY_BUFFER, COMPONENT_UINT, "SCALAR")


def _triangle_arrays(points: np.ndarray, polygons: list) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    count = len(points)
    positions: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    indices: list[np.ndarray] = []
    base = 0
    simple = [p for p in polygons if len(p) == 3]
    if simple:
        t = np.array(simple, dtype=np.int64)
        if t.min() < 0 or t.max() >= count:
            raise FileFormatError("a polygon refers to a point that does not exist")
        v = points[t]
        n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        length = np.linalg.norm(n, axis=1)
        good = length > 1e-18
        n[good] = n[good] / length[good][:, None]
        n[~good] = (0.0, 1.0, 0.0)
        positions.append(v.reshape(-1, 3))
        normals.append(np.repeat(n, 3, axis=0))
        indices.append(np.arange(len(t) * 3, dtype=np.int64))
        base = len(t) * 3
    for poly in polygons:
        k = len(poly)
        if k <= 3:
            continue
        ids = list(poly)
        if min(ids) < 0 or max(ids) >= count:
            raise FileFormatError("a polygon refers to a point that does not exist")
        ring = points[ids]
        nxt = np.roll(ring, -1, axis=0)
        n = np.array([
            np.sum((ring[:, 1] - nxt[:, 1]) * (ring[:, 2] + nxt[:, 2])),
            np.sum((ring[:, 2] - nxt[:, 2]) * (ring[:, 0] + nxt[:, 0])),
            np.sum((ring[:, 0] - nxt[:, 0]) * (ring[:, 1] + nxt[:, 1])),
        ])
        length = float(np.linalg.norm(n))
        n = n / length if length > 1e-18 else np.array([0.0, 1.0, 0.0])
        tris = triangulate_ring(ring)
        if not tris:
            continue
        positions.append(ring)
        normals.append(np.tile(n, (k, 1)))
        indices.append(np.array(tris, dtype=np.int64).reshape(-1) + base)
        base += k
    if not positions:
        return None
    return np.vstack(positions), np.vstack(normals), np.concatenate(indices)


def _write_mesh(builder: _Builder, points: np.ndarray, polygons: list, loose: list, material: dict) -> dict | None:
    if len(points) and not np.isfinite(points).all():
        raise FileFormatError("the mesh has coordinates that are not finite numbers")
    primitives: list[dict] = []
    built = _triangle_arrays(points, polygons)
    if built is not None:
        pos, nrm, idx = built
        pos32 = (pos * CM_TO_M).astype("<f4")
        position = builder.add(pos32, ARRAY_BUFFER, COMPONENT_FLOAT, "VEC3", True)
        normal = builder.add(nrm.astype("<f4"), ARRAY_BUFFER, COMPONENT_FLOAT, "VEC3")
        index = builder.indices(idx, len(pos32))
        material["used"] = True
        primitives.append({"attributes": {"POSITION": position, "NORMAL": normal}, "indices": index,
                           "mode": 4, "material": 0})
    if loose:
        e = np.array(loose, dtype=np.int64).reshape(-1, 2)
        if e.min() < 0 or e.max() >= len(points):
            raise FileFormatError("a loose edge refers to a point that does not exist")
        used = np.unique(e)
        remap = np.searchsorted(used, e).reshape(-1)
        pos32 = (points[used] * CM_TO_M).astype("<f4")
        position = builder.add(pos32, ARRAY_BUFFER, COMPONENT_FLOAT, "VEC3", True)
        index = builder.indices(remap, len(pos32))
        primitives.append({"attributes": {"POSITION": position}, "indices": index, "mode": 1})
    if not primitives:
        return None
    return {"primitives": primitives}


def _export_order(parents: list[int | None]) -> list[int]:
    done: set[int] = set()
    order: list[int] = []
    for i in range(len(parents)):
        chain: list[int] = []
        j: int | None = i
        while j is not None and j not in done:
            if j in chain:
                raise FileFormatError("the node hierarchy contains a cycle")
            chain.append(j)
            j = parents[j]
        order.extend(reversed(chain))
        done.update(chain)
    return order


def _build_gltf(document: Document) -> tuple[dict, bytes]:
    nodes = document.nodes
    count = len(nodes)
    parents: list[int | None] = []
    for node in nodes:
        p = node.parent
        if p is None:
            parents.append(None)
            continue
        if not _is_int(p) or not 0 <= int(p) < count:
            raise FileFormatError(f"{node.name or 'Node'}: invalid parent index {p!r}")
        parents.append(int(p))
    order = _export_order(parents)
    builder = _Builder()
    material = {"used": False}
    exported = [np.eye(4) for _ in nodes]
    gltf_nodes: list[dict] = [{} for _ in nodes]
    meshes: list[dict] = []
    children: list[list[int]] = [[] for _ in nodes]
    for i in order:
        node = nodes[i]
        world = np.array(node.matrix, float).reshape(4, 4)
        if not np.isfinite(world).all():
            raise FileFormatError(f"{node.name or 'Node'}: the transform has values that are not finite numbers")
        parent_world = exported[parents[i]] if parents[i] is not None else np.eye(4)
        local = np.linalg.inv(parent_world) @ world
        entry: dict = {"name": str(node.name) if node.name else f"Node {i}"}
        mesh = node.mesh
        points = np.asarray(mesh.points, float).reshape(-1, 3) if mesh is not None else np.zeros((0, 3))
        polygons = list(mesh.polygons) if mesh is not None else []
        loose = list(mesh.loose_edges) if mesh is not None else []
        solved = _trs(local)
        if solved is not None:
            t, q, s = solved
            if np.abs(t).max() > 0.0:
                entry["translation"] = [float(v) * CM_TO_M for v in t]
            if abs(q[3] - 1.0) > 1e-12:
                entry["rotation"] = q
            if np.abs(s - 1.0).max() > 1e-12:
                entry["scale"] = [float(v) for v in s]
            exported[i] = parent_world @ local
        else:
            lin = local[:3, :3]
            shift = local[:3, 3] if np.isfinite(local[:3, 3]).all() else np.zeros(3)
            if np.abs(shift).max() > 0.0:
                entry["translation"] = [float(v) * CM_TO_M for v in shift]
            placed = np.eye(4)
            placed[:3, 3] = shift
            exported[i] = parent_world @ placed
            if len(points):
                points = points @ lin.T
            if float(np.linalg.det(lin)) < 0.0:
                polygons = [tuple(reversed(p)) for p in polygons]
        gltf_mesh = _write_mesh(builder, points, polygons, loose, material) if mesh is not None else None
        if gltf_mesh is not None:
            gltf_mesh["name"] = entry["name"]
            entry["mesh"] = len(meshes)
            meshes.append(gltf_mesh)
        gltf_nodes[i] = entry
        if parents[i] is not None:
            children[parents[i]].append(i)
    for i, kids in enumerate(children):
        if kids:
            gltf_nodes[i]["children"] = sorted(kids)
    roots = [i for i in range(count) if parents[i] is None]
    gltf: dict = {"asset": {"version": "2.0", "generator": GENERATOR},
                  "scene": 0, "scenes": [{"nodes": roots}]}
    if gltf_nodes:
        gltf["nodes"] = gltf_nodes
    if meshes:
        gltf["meshes"] = meshes
    if material["used"]:
        gltf["materials"] = [{"name": "Default", "pbrMetallicRoughness": {
            "baseColorFactor": [0.8, 0.8, 0.8, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.6}}]
    if builder.accessors:
        gltf["accessors"] = builder.accessors
        gltf["bufferViews"] = builder.views
        gltf["buffers"] = [{"byteLength": len(builder.data)}]
    return gltf, bytes(builder.data)


def _dumps(gltf: dict) -> bytes:
    return json.dumps(gltf, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _built(path: str, document: Document) -> tuple[dict, bytes]:
    try:
        return _build_gltf(document)
    except FileFormatError as exc:
        raise FileFormatError(f"{os.path.basename(path)}: {exc}") from None


def save_gltf(path: str, document: Document, options: dict) -> None:
    gltf, blob = _built(path, document)
    if blob:
        uri = "data:application/octet-stream;base64," + base64.b64encode(blob).decode("ascii")
        gltf["buffers"][0]["uri"] = uri
    write_atomic(path, _dumps(gltf))


def save_glb(path: str, document: Document, options: dict) -> None:
    gltf, blob = _built(path, document)
    text = _dumps(gltf)
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<II", len(text), CHUNK_JSON) + text
    if blob:
        chunks += struct.pack("<II", len(blob), CHUNK_BIN) + blob
    write_atomic(path, struct.pack("<4sII", GLB_MAGIC, 2, 12 + len(chunks)) + chunks)


def _split_container(data: bytes) -> tuple[dict, bytes | None]:
    blob: bytes | None = None
    if data[:4] == GLB_MAGIC:
        _need(len(data) >= 20, "GLB file is too short")
        _, version, length = struct.unpack_from("<4sII", data, 0)
        _need(version == 2, f"GLB version {version} is not supported (only 2)")
        _need(12 <= length <= len(data),
              f"GLB is truncated or corrupt: header says {length} bytes, the file has {len(data)}")
        pos = 12
        raw: bytes | None = None
        while pos + 8 <= length:
            size, kind = struct.unpack_from("<II", data, pos)
            pos += 8
            _need(pos + size <= length, "GLB chunk runs past the end of the file")
            body = data[pos:pos + size]
            pos += size
            if raw is None:
                _need(kind == CHUNK_JSON, "the first GLB chunk is not JSON")
                raw = body
            elif kind == CHUNK_BIN and blob is None:
                blob = body
        _need(pos == length, "GLB chunk table is corrupt")
        _need(raw is not None, "GLB has no JSON chunk")
        text = raw.decode("utf-8").rstrip(" " + chr(0) + chr(9) + chr(10) + chr(13))
    else:
        text = data.decode("utf-8-sig")
    try:
        gltf = json.loads(text)
    except ValueError as exc:
        raise _Bad(f"invalid JSON: {exc}") from None
    _need(isinstance(gltf, dict), "the top level of a glTF file must be an object")
    return gltf, blob


class _Reader:
    def __init__(self, gltf: dict, base_dir: str, blob: bytes | None) -> None:
        self.gltf = gltf
        self.base_dir = base_dir
        self.blob = blob
        self.cache: dict[int, bytes] = {}
        self.accessors = self._list("accessors")
        self.views = self._list("bufferViews")
        self.buffers = self._list("buffers")

    def _list(self, key: str) -> list:
        value = self.gltf.get(key, [])
        _need(isinstance(value, list), f"{key} must be a list")
        return value

    def buffer(self, i: int) -> bytes:
        i = _index(i, len(self.buffers), "buffer index")
        if i in self.cache:
            return self.cache[i]
        entry = self.buffers[i]
        _need(isinstance(entry, dict), f"buffer {i} must be an object")
        length = entry.get("byteLength")
        _need(_is_int(length) and length >= 1, f"buffer {i} needs a byteLength of at least 1")
        uri = entry.get("uri")
        if uri is None:
            _need(i == 0 and self.blob is not None, f"buffer {i} has no uri and the file has no BIN chunk")
            data = self.blob
        else:
            _need(isinstance(uri, str), f"buffer {i} uri must be a string")
            if uri.startswith("data:"):
                head, sep, payload = uri.partition(",")
                _need(sep != "" and head.endswith(";base64"), f"buffer {i} has an unsupported data URI")
                try:
                    data = base64.b64decode(payload, validate=True)
                except (binascii.Error, ValueError):
                    raise _Bad(f"buffer {i} has invalid base64 data") from None
            else:
                parts = urlsplit(uri)
                rel = unquote(parts.path)
                _need(not parts.scheme and not parts.netloc and rel != "" and not os.path.isabs(rel)
                      and not rel.startswith(("/", chr(92))),
                      f"buffer {i} uri {uri!r} is remote or absolute and cannot be loaded")
                full = os.path.join(self.base_dir, rel)
                try:
                    with open(full, "rb") as handle:
                        data = handle.read()
                except OSError:
                    raise _Bad(f"buffer file {rel!r} was not found next to the glTF file") from None
        _need(len(data) >= length, f"buffer {i} declares {length} bytes but only {len(data)} are available")
        self.cache[i] = data
        return data

    def raw(self, view_index, offset: int, code: str, size: int, parts: int, count: int,
            use_stride: bool) -> np.ndarray:
        v = _index(view_index, len(self.views), "bufferView index")
        view = self.views[v]
        _need(isinstance(view, dict), f"bufferView {v} must be an object")
        data = self.buffer(view.get("buffer"))
        start_view = view.get("byteOffset", 0)
        length = view.get("byteLength")
        _need(_is_int(start_view) and start_view >= 0, f"bufferView {v} has an invalid byteOffset")
        _need(_is_int(length) and length >= 1, f"bufferView {v} has an invalid byteLength")
        _need(start_view + length <= len(data), f"bufferView {v} runs past the end of its buffer")
        element = size * parts
        stride = view.get("byteStride") if use_stride else None
        if stride is None:
            stride = element
        else:
            _need(_is_int(stride) and stride >= element, f"bufferView {v} has an invalid byteStride {stride!r}")
        _need(_is_int(offset) and offset >= 0, "accessor byteOffset must be a non-negative integer")
        start = start_view + offset
        _need(start + (count - 1) * stride + element <= start_view + length,
              f"an accessor reads past the end of bufferView {v}")
        dt = np.dtype("<" + code)
        if stride == element:
            return np.frombuffer(data, dtype=dt, count=count * parts, offset=start).reshape(count, parts)
        out = np.empty((count, parts), dtype=dt)
        for j in range(parts):
            out[:, j] = np.ndarray((count,), dtype=dt, buffer=data, offset=start + j * size, strides=(stride,))
        return out

    def accessor(self, i, kinds: tuple[str, ...], component_types: tuple[int, ...]) -> np.ndarray:
        i = _index(i, len(self.accessors), "accessor index")
        a = self.accessors[i]
        _need(isinstance(a, dict), f"accessor {i} must be an object")
        ctype = a.get("componentType")
        _need(ctype in COMPONENTS and ctype in component_types,
              f"accessor {i} has an unusable componentType {ctype!r}")
        kind = a.get("type")
        _need(kind in kinds, f"accessor {i} has type {kind!r}, expected {' or '.join(kinds)}")
        count = a.get("count")
        _need(_is_int(count) and count >= 1, f"accessor {i} needs a count of at least 1")
        parts = COMPONENT_COUNT[kind]
        code, size = COMPONENTS[ctype]
        if a.get("bufferView") is None:
            values = np.zeros((count, parts), dtype=np.dtype("<" + code))
        else:
            values = self.raw(a["bufferView"], a.get("byteOffset", 0), code, size, parts, count, True)
        sparse = a.get("sparse")
        if sparse is not None:
            _need(isinstance(sparse, dict), f"accessor {i} sparse must be an object")
            n = sparse.get("count")
            _need(_is_int(n) and 1 <= n <= count, f"accessor {i} sparse count is invalid")
            ind = sparse.get("indices")
            val = sparse.get("values")
            _need(isinstance(ind, dict) and isinstance(val, dict), f"accessor {i} sparse needs indices and values")
            ict = ind.get("componentType")
            _need(ict in (COMPONENT_UBYTE, COMPONENT_USHORT, COMPONENT_UINT),
                  f"accessor {i} sparse indices have an unusable componentType {ict!r}")
            icode, isize = COMPONENTS[ict]
            where = self.raw(ind.get("bufferView"), ind.get("byteOffset", 0), icode, isize, 1, n, False)
            where = where.reshape(-1).astype(np.int64)
            _need(int(where.max()) < count, f"accessor {i} sparse index is out of range")
            patch = self.raw(val.get("bufferView"), val.get("byteOffset", 0), code, size, parts, n, False)
            values = values.copy()
            values[where] = patch
        return self._convert(values, ctype, bool(a.get("normalized", False)))

    @staticmethod
    def _convert(values: np.ndarray, ctype: int, normalized: bool) -> np.ndarray:
        if ctype == COMPONENT_FLOAT:
            return values.astype(np.float64)
        if not normalized:
            return values.astype(np.int64)
        out = values.astype(np.float64)
        if ctype == 5120:
            return np.maximum(out / 127.0, -1.0)
        if ctype == 5122:
            return np.maximum(out / 32767.0, -1.0)
        if ctype == COMPONENT_UBYTE:
            return out / 255.0
        if ctype == COMPONENT_USHORT:
            return out / 65535.0
        return out / 4294967295.0

    def primitive(self, prim, where: str):
        _need(isinstance(prim, dict), f"{where} must be an object")
        mode = prim.get("mode", 4)
        _need(_is_int(mode) and 0 <= mode <= 6, f"{where} has an invalid mode {mode!r}")
        if mode == 0:
            return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), np.zeros((0, 2), dtype=np.int64)
        ext = prim.get("extensions")
        if isinstance(ext, dict):
            for name in UNSUPPORTED_REQUIRED:
                _need(name not in ext, f"{where} uses {name}, which is not supported")
        attrs = prim.get("attributes")
        _need(isinstance(attrs, dict) and "POSITION" in attrs, f"{where} has no POSITION attribute")
        pos = self.accessor(attrs["POSITION"], ("VEC3",), tuple(COMPONENTS))
        _need(bool(np.isfinite(pos).all()), f"{where} has positions that are not finite numbers")
        n = len(pos)
        if prim.get("indices") is not None:
            idx = self.accessor(prim["indices"], ("SCALAR",), (COMPONENT_UBYTE, COMPONENT_USHORT, COMPONENT_UINT))
            idx = idx.reshape(-1)
            _need(int(idx.max()) < n, f"{where} has an index past the last vertex ({int(idx.max())} >= {n})")
        else:
            idx = np.arange(n, dtype=np.int64)
        name = MODE_NAMES[mode]
        empty_t = np.zeros((0, 3), dtype=np.int64)
        empty_l = np.zeros((0, 2), dtype=np.int64)
        m = len(idx)
        if mode == 4:
            _need(m % 3 == 0, f"{where}: a {name} primitive needs a multiple of 3 indices, got {m}")
            return pos, idx.reshape(-1, 3), empty_l
        if mode == 5:
            _need(m >= 3, f"{where}: a {name} primitive needs at least 3 indices, got {m}")
            i = np.arange(m - 2)
            even = (i % 2) == 0
            a = np.where(even, idx[i], idx[i + 1])
            b = np.where(even, idx[i + 1], idx[i])
            return pos, np.stack([a, b, idx[i + 2]], axis=1), empty_l
        if mode == 6:
            _need(m >= 3, f"{where}: a {name} primitive needs at least 3 indices, got {m}")
            i = np.arange(1, m - 1)
            return pos, np.stack([np.full(len(i), idx[0]), idx[i], idx[i + 1]], axis=1), empty_l
        if mode == 1:
            _need(m % 2 == 0, f"{where}: a {name} primitive needs an even number of indices, got {m}")
            return pos, empty_t, idx.reshape(-1, 2)
        _need(m >= 2, f"{where}: a {name} primitive needs at least 2 indices, got {m}")
        pairs = np.stack([idx[:-1], idx[1:]], axis=1)
        if mode == 2:
            pairs = np.vstack([pairs, [[idx[-1], idx[0]]]])
        return pos, empty_t, pairs

    def mesh(self, index: int) -> Mesh | None:
        meshes = self._list("meshes")
        mi = _index(index, len(meshes), "mesh index")
        entry = meshes[mi]
        _need(isinstance(entry, dict), f"mesh {mi} must be an object")
        prims = entry.get("primitives")
        _need(isinstance(prims, list) and len(prims) >= 1, f"mesh {mi} needs at least one primitive")
        positions, tris, lines = [], [], []
        base = 0
        for k, prim in enumerate(prims):
            pos, t, e = self.primitive(prim, f"mesh {mi} primitive {k}")
            positions.append(pos)
            tris.append(t + base)
            lines.append(e + base)
            base += len(pos)
        allpos = np.vstack(positions)
        t_all = np.vstack(tris)
        l_all = np.vstack(lines)
        used = np.unique(np.concatenate([t_all.reshape(-1), l_all.reshape(-1)]))
        if len(used) == 0:
            return None
        remap = np.full(len(allpos), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        unique, welded = weld(allpos[used] + 0.0, 0.0)
        final = welded[remap.clip(min=0)]
        t_all = final[t_all]
        l_all = final[l_all]
        keep = (t_all[:, 0] != t_all[:, 1]) & (t_all[:, 1] != t_all[:, 2]) & (t_all[:, 0] != t_all[:, 2])
        t_all = t_all[keep]
        l_all = l_all[l_all[:, 0] != l_all[:, 1]]
        if len(l_all):
            l_all = np.unique(np.sort(l_all, axis=1), axis=0)
        if len(t_all) == 0 and len(l_all) == 0:
            return None
        return Mesh(unique * M_TO_CM, t_all.tolist(), l_all.tolist())


def _local_matrix(entry: dict, where: str) -> np.ndarray:
    raw = entry.get("matrix")
    if raw is not None:
        values = _numbers(raw, 16, f"{where} matrix")
        m = np.array(values, dtype=float).reshape(4, 4).T
        _need(np.abs(m[3] - np.array([0.0, 0.0, 0.0, 1.0])).max() < 1e-6, f"{where} matrix is not an affine transform")
    else:
        t = _numbers(entry.get("translation", [0.0, 0.0, 0.0]), 3, f"{where} translation")
        r = _numbers(entry.get("rotation", [0.0, 0.0, 0.0, 1.0]), 4, f"{where} rotation")
        s = _numbers(entry.get("scale", [1.0, 1.0, 1.0]), 3, f"{where} scale")
        m = np.eye(4)
        m[:3, :3] = _quaternion_matrix(*r) @ np.diag(s)
        m[:3, 3] = t
    m[:3, 3] *= M_TO_CM
    return m


def _scene_roots(gltf: dict, nodes: list) -> list[int]:
    scenes = gltf.get("scenes")
    if scenes:
        _need(isinstance(scenes, list), "scenes must be a list")
        si = _index(gltf.get("scene", 0), len(scenes), "scene index")
        scene = scenes[si]
        _need(isinstance(scene, dict), f"scene {si} must be an object")
        roots = scene.get("nodes", [])
        _need(isinstance(roots, list), f"scene {si} nodes must be a list")
        return [_index(r, len(nodes), f"scene {si} node index") for r in roots]
    child_ids: set[int] = set()
    for entry in nodes:
        if isinstance(entry, dict) and isinstance(entry.get("children"), list):
            child_ids.update(c for c in entry["children"] if _is_int(c))
    return [i for i in range(len(nodes)) if i not in child_ids]


def _load(path: str) -> Document:
    with open(path, "rb") as handle:
        data = handle.read()
    gltf, blob = _split_container(data)
    asset = gltf.get("asset")
    _need(isinstance(asset, dict), "this is not a glTF file: the asset object is missing")
    version = asset.get("version")
    _need(isinstance(version, str) and version.split(".")[0] == "2",
          f"glTF version {version!r} is not supported (only 2.x)")
    required = gltf.get("extensionsRequired", [])
    if isinstance(required, list):
        for name in UNSUPPORTED_REQUIRED:
            _need(name not in required, f"the file requires {name}, which is not supported")
    reader = _Reader(gltf, os.path.dirname(os.path.abspath(path)), blob)
    nodes = gltf.get("nodes", [])
    _need(isinstance(nodes, list), "nodes must be a list")
    roots = _scene_roots(gltf, nodes)
    cache: dict[int, Mesh | None] = {}
    out: list[Node] = []
    seen: set[int] = set()
    stack: list[tuple[int, int | None, np.ndarray]] = [(r, None, np.eye(4)) for r in reversed(roots)]
    while stack:
        i, parent, parent_world = stack.pop()
        _need(i not in seen, f"node {i} appears more than once in the hierarchy")
        seen.add(i)
        entry = nodes[i]
        _need(isinstance(entry, dict), f"node {i} must be an object")
        local = _local_matrix(entry, f"node {i}")
        world = parent_world @ local
        mesh = None
        if entry.get("mesh") is not None:
            mi = _index(entry["mesh"], len(reader._list("meshes")), f"node {i} mesh index")
            if mi not in cache:
                cache[mi] = reader.mesh(mi)
            shared = cache[mi]
            if shared is not None:
                mesh = Mesh(shared.points.copy(), list(shared.polygons), list(shared.loose_edges))
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            mesh_name = None
            if entry.get("mesh") is not None:
                mesh_name = reader._list("meshes")[entry["mesh"]].get("name")
            name = mesh_name if isinstance(mesh_name, str) and mesh_name else f"Node {i}"
        position, rotation, scale = decompose(local)
        exact = np.allclose(compose(position, rotation, scale), local, rtol=0.0,
                            atol=1e-7 * (1.0 + float(np.abs(local).max())))
        index = len(out)
        out.append(Node(
            name, mesh, world, parent, "polygon", None, True,
            tuple(float(v) for v in position) if exact else None,
            tuple(float(v) for v in rotation) if exact else None,
            tuple(float(v) for v in scale) if exact else None,
        ))
        kids = entry.get("children", [])
        _need(isinstance(kids, list), f"node {i} children must be a list")
        for c in reversed(kids):
            _need(_is_int(c) and 0 <= c < len(nodes), f"node {i} has an invalid child index {c!r}")
            stack.append((int(c), index, world))
    return Document(out, {"unit": "cm", "up": "y", "handedness": "right", "source": "glTF"})


def load(path: str) -> Document:
    name = os.path.basename(path)
    try:
        return _load(path)
    except _Bad as exc:
        raise FileFormatError(f"{name}: {exc}") from None
    except FileFormatError:
        raise
    except OSError as exc:
        raise FileFormatError(f"{name}: cannot read the file ({exc.strerror or exc})") from None
    except UnicodeDecodeError:
        raise FileFormatError(f"{name}: the file is not valid UTF-8 text") from None
    except Exception as exc:
        raise FileFormatError(f"{name}: malformed glTF ({type(exc).__name__}: {exc})") from None


register(FileFormat("gltf", "glTF", (".gltf",), load, save_gltf, "glTF 2.0, JSON with an embedded buffer"))
register(FileFormat("glb", "glTF Binary", (".glb",), load, save_glb, "glTF 2.0, single binary file"))
