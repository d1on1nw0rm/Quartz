from __future__ import annotations

import datetime
import hashlib
import itertools
import math
import os
import re
import struct
import zlib

import numpy as np

from ..scene import Mesh
from .model import Document, Node, decompose, require_finite, write_atomic
from .registry import FileFormat, FileFormatError, register

MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
VERSION = 7400
FILE_ID = b"\x28\xb3\x2a\xeb\xb6\x24\xcc\xc2\xbf\xc8\xb0\x2a\xa9\x2b\xfc\xf1"
FOOT_ID = b"\xfa\xbc\xab\x09\xd0\xc8\xd4\x66\xb1\x76\xfb\x83\x1c\xf7\x26\x7e"
FOOT_MAGIC = b"\xf8\x5a\x8c\x6a\xde\xf5\xd9\x7e\xec\xe9\x0c\xe3\x75\x8f\x29\x0b"
TIME_ID = "1970-01-01 10:00:00:000"
SKIPPED_MODELS = frozenset(("Camera", "Light", "CameraSwitcher"))
CREATOR = "Quartz Studio FBX"

_ARRAY_DTYPES = {"f": "<f4", "d": "<f8", "i": "<i4", "l": "<i8", "b": "u1", "c": "u1"}
_SCALARS = {"Y": struct.Struct("<h"), "I": struct.Struct("<i"), "L": struct.Struct("<q"),
            "F": struct.Struct("<f"), "D": struct.Struct("<d")}
_ARRAY_HEAD = struct.Struct("<3I")
_U32 = struct.Struct("<I")


class _Bad(Exception):
    pass


class Elem:
    __slots__ = ("name", "props", "children")

    def __init__(self, name: str, props: list | None = None, children: list | None = None) -> None:
        self.name = name
        self.props = props if props is not None else []
        self.children = children if children is not None else []

    def child(self, name: str) -> "Elem | None":
        for c in self.children:
            if c.name == name:
                return c
        return None

    def all(self, name: str) -> list["Elem"]:
        return [c for c in self.children if c.name == name]


class _W:
    __slots__ = ("name", "props", "children", "size", "plen")

    def __init__(self, name: str, values: tuple = ()) -> None:
        self.name = name.encode("ascii")
        self.props = list(values)
        self.children: list[_W] = []
        self.size = 0
        self.plen = 0

    def add(self, name: str, *values) -> "_W":
        w = _W(name, values)
        self.children.append(w)
        return w


def _encode_prop(value, compress: bool) -> bytes:
    if isinstance(value, tuple):
        code, v = value
    elif isinstance(value, (bool, np.bool_)):
        code, v = "C", value
    elif isinstance(value, (int, np.integer)):
        code, v = ("I" if -2 ** 31 <= int(value) < 2 ** 31 else "L"), int(value)
    elif isinstance(value, (float, np.floating)):
        code, v = "D", float(value)
    elif isinstance(value, str):
        code, v = "S", value
    elif isinstance(value, (bytes, bytearray)):
        code, v = "R", bytes(value)
    elif isinstance(value, np.ndarray):
        kind = value.dtype
        if kind == np.bool_:
            code = "b"
        elif kind == np.float32:
            code = "f"
        elif kind.kind == "f":
            code = "d"
        elif kind == np.int32:
            code = "i"
        else:
            code = "l"
        v = value
    else:
        raise TypeError(f"cannot store {type(value).__name__} in FBX")
    if code == "C":
        return b"C" + bytes((1 if v else 0,))
    if code in _SCALARS:
        return code.encode() + _SCALARS[code].pack(v)
    if code in ("S", "R"):
        raw = v.encode("utf-8") if isinstance(v, str) else bytes(v)
        return code.encode() + _U32.pack(len(raw)) + raw
    arr = np.ascontiguousarray(np.asarray(v).reshape(-1), dtype=_ARRAY_DTYPES[code])
    raw = arr.tobytes()
    if compress and len(raw) > 128:
        packed = zlib.compress(raw, 1)
        return code.encode() + _ARRAY_HEAD.pack(arr.size, 1, len(packed)) + packed
    return code.encode() + _ARRAY_HEAD.pack(arr.size, 0, len(raw)) + raw


def _measure(w: _W, last: bool, compress: bool, meta: int) -> int:
    w.props = [_encode_prop(v, compress) for v in w.props]
    w.plen = sum(len(p) for p in w.props)
    size = meta + 1 + len(w.name) + w.plen
    if w.children:
        final = len(w.children) - 1
        for k, c in enumerate(w.children):
            size += _measure(c, k == final, compress, meta)
        size += meta + 1
    elif not w.props and not last:
        size += meta + 1
    w.size = size
    return size


def _emit(w: _W, offset: int, last: bool, out: list, meta: struct.Struct) -> None:
    sentinel = b"\x00" * (meta.size + 1)
    out.append(meta.pack(offset + w.size, len(w.props), w.plen))
    out.append(bytes((len(w.name),)))
    out.append(w.name)
    out.extend(w.props)
    pos = offset + meta.size + 1 + len(w.name) + w.plen
    if w.children:
        final = len(w.children) - 1
        for k, c in enumerate(w.children):
            _emit(c, pos, k == final, out, meta)
            pos += c.size
        out.append(sentinel)
    elif not w.props and not last:
        out.append(sentinel)


def encode_binary(top: list[_W], version: int = VERSION, compress: bool = True) -> bytes:
    meta = struct.Struct("<3Q" if version >= 7500 else "<3I")
    out: list[bytes] = [MAGIC, _U32.pack(version)]
    offset = len(MAGIC) + 4
    final = len(top) - 1
    for k, w in enumerate(top):
        _measure(w, k == final, compress, meta.size)
    for k, w in enumerate(top):
        _emit(w, offset, k == final, out, meta)
        offset += w.size
    out.append(b"\x00" * (meta.size + 1))
    offset += meta.size + 1
    out.append(FOOT_ID)
    out.append(b"\x00" * 4)
    offset += 20
    pad = ((offset + 15) & ~15) - offset
    out.append(b"\x00" * (pad or 16))
    out.append(_U32.pack(version))
    out.append(b"\x00" * 120)
    out.append(FOOT_MAGIC)
    return b"".join(out)


_PTYPES = {
    "bool": ("bool", ""), "int": ("int", "Integer"), "double": ("double", "Number"), "enum": ("enum", ""),
    "Vector3D": ("Vector3D", "Vector"), "ColorRGB": ("ColorRGB", "Color"), "KString": ("KString", ""),
    "Url": ("KString", "Url"), "KTime": ("KTime", "Time"), "DateTime": ("DateTime", ""),
    "object": ("object", ""), "Compound": ("Compound", ""),
    "Lcl Translation": ("Lcl Translation", ""), "Lcl Rotation": ("Lcl Rotation", ""),
    "Lcl Scaling": ("Lcl Scaling", ""), "Visibility": ("Visibility", ""),
    "Visibility Inheritance": ("Visibility Inheritance", ""),
}
_VECTOR_KINDS = ("Vector3D", "ColorRGB", "Lcl Translation", "Lcl Rotation", "Lcl Scaling")
_V0 = (0.0, 0.0, 0.0)
_V1 = (1.0, 1.0, 1.0)


def _p(props: _W, name: str, kind: str, value=None, animatable: bool = False) -> None:
    type_name, label = _PTYPES[kind]
    if kind in ("bool", "int", "enum", "Visibility Inheritance"):
        values = [("I", int(value))]
    elif kind in ("double", "Visibility"):
        values = [float(value)]
    elif kind in _VECTOR_KINDS:
        values = [float(v) for v in value]
    elif kind in ("KString", "Url", "DateTime"):
        values = [str(value)]
    elif kind == "KTime":
        values = [("L", int(value))]
    else:
        values = []
    props.add("P", name, type_name, label, "A" if animatable else "", *values)


def _model_template() -> list[tuple]:
    t: list[tuple] = [("QuaternionInterpolate", "enum", 0), ("RotationOffset", "Vector3D", _V0),
                      ("RotationPivot", "Vector3D", _V0), ("ScalingOffset", "Vector3D", _V0),
                      ("ScalingPivot", "Vector3D", _V0), ("TranslationActive", "bool", 0),
                      ("TranslationMin", "Vector3D", _V0), ("TranslationMax", "Vector3D", _V0)]
    t += [(f"Translation{m}{a}", "bool", 0) for m in ("Min", "Max") for a in "XYZ"]
    t += [("RotationOrder", "enum", 0), ("RotationSpaceForLimitOnly", "bool", 0)]
    t += [(f"RotationStiffness{a}", "double", 0.0) for a in "XYZ"]
    t += [("AxisLen", "double", 10.0), ("PreRotation", "Vector3D", _V0), ("PostRotation", "Vector3D", _V0),
          ("RotationActive", "bool", 0), ("RotationMin", "Vector3D", _V0), ("RotationMax", "Vector3D", _V0)]
    t += [(f"Rotation{m}{a}", "bool", 0) for m in ("Min", "Max") for a in "XYZ"]
    t += [("InheritType", "enum", 0), ("ScalingActive", "bool", 0), ("ScalingMin", "Vector3D", _V0),
          ("ScalingMax", "Vector3D", _V1)]
    t += [(f"Scaling{m}{a}", "bool", 0) for m in ("Min", "Max") for a in "XYZ"]
    t += [("GeometricTranslation", "Vector3D", _V0), ("GeometricRotation", "Vector3D", _V0),
          ("GeometricScaling", "Vector3D", _V1)]
    t += [(f"{k}{a}", "double", 0.0) for k in ("MinDampRange", "MaxDampRange", "MinDampStrength",
                                              "MaxDampStrength", "PreferedAngle") for a in "XYZ"]
    t += [("LookAtProperty", "object", None), ("UpVectorProperty", "object", None), ("Show", "bool", 1),
          ("NegativePercentShapeSupport", "bool", 1), ("DefaultAttributeIndex", "int", -1),
          ("Freeze", "bool", 0), ("LODBox", "bool", 0),
          ("Lcl Translation", "Lcl Translation", _V0, True), ("Lcl Rotation", "Lcl Rotation", _V0, True),
          ("Lcl Scaling", "Lcl Scaling", _V1, True), ("Visibility", "Visibility", 1.0, True),
          ("Visibility Inheritance", "Visibility Inheritance", 1)]
    return t


_GEOMETRY_TEMPLATE = [("Color", "ColorRGB", (0.8, 0.8, 0.8)), ("BBoxMin", "Vector3D", _V0),
                      ("BBoxMax", "Vector3D", _V0), ("Primary Visibility", "bool", 1),
                      ("Casts Shadows", "bool", 1), ("Receive Shadows", "bool", 1)]


def _template(definitions: _W, type_name: str, count: int, class_name: str, entries: list) -> None:
    obj = definitions.add("ObjectType", type_name)
    obj.add("Count", ("I", count))
    if class_name:
        props = obj.add("PropertyTemplate", class_name).add("Properties70")
        for entry in entries:
            _p(props, entry[0], entry[1], entry[2], len(entry) > 3 and entry[3])


def _valid_parents(nodes: list[Node]) -> list[int | None]:
    n = len(nodes)

    def index(p) -> int | None:
        if isinstance(p, (bool, np.bool_)) or not isinstance(p, (int, np.integer)):
            return None
        return int(p) if 0 <= int(p) < n else None

    out: list[int | None] = []
    for i, node in enumerate(nodes):
        p = index(node.parent)
        seen = {i}
        q = p
        while q is not None:
            if q in seen:
                p = None
                break
            seen.add(q)
            q = index(nodes[q].parent)
        out.append(p)
    return out


def _local_trs(nodes: list[Node], parents: list[int | None], i: int):
    node = nodes[i]
    if node.position is not None and node.rotation is not None and node.scale is not None:
        return (np.asarray(node.position, float), np.asarray(node.rotation, float),
                np.asarray(node.scale, float))
    m = np.asarray(node.matrix, float)
    if parents[i] is not None:
        try:
            m = np.linalg.inv(np.asarray(nodes[parents[i]].matrix, float)) @ m
        except np.linalg.LinAlgError:
            pass
    return decompose(m)


def _geometry_arrays(mesh: Mesh):
    pts = np.asarray(mesh.points, float).reshape(-1, 3)
    keep = [k for k, p in enumerate(mesh.polygons) if len(p) >= 3]
    polys = [mesh.polygons[k] for k in keep]
    edges = [(int(a), int(b)) for a, b in mesh.loose_edges if a != b]
    if not polys and not edges:
        return pts, np.zeros(0, np.int32), np.zeros((0, 3))
    lengths = np.fromiter((len(p) for p in polys), np.int64, len(polys))
    flat = np.fromiter(itertools.chain.from_iterable(polys), np.int64, int(lengths.sum()))
    ends = np.cumsum(lengths) - 1
    flat[ends] = ~flat[ends]
    normals = np.repeat(mesh.polygon_normals()[keep] if polys else np.zeros((0, 3)), lengths, axis=0)
    if edges:
        pairs = np.array(edges, dtype=np.int64).reshape(-1, 2)
        pairs[:, 1] = ~pairs[:, 1]
        flat = np.concatenate([flat, pairs.reshape(-1)])
        normals = np.vstack([normals, np.zeros((2 * len(edges), 3))])
    return pts, flat.astype(np.int32), normals


def _clean_name(name) -> str:
    text = str(name or "Object").replace("\x00", "").replace("\x01", "")
    return text or "Object"


def _uid_factory():
    used: set[int] = {0}

    def uid(key: str) -> int:
        h = int.from_bytes(hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest(), "little")
        h = (h & ((1 << 62) - 1)) | (1 << 40)
        while h in used:
            h += 1
        used.add(h)
        return h

    return uid


def build_tree(document: Document, path: str = "") -> list[_W]:
    nodes = list(document.nodes)
    parents = _valid_parents(nodes)
    uid = _uid_factory()
    now = datetime.datetime.now()
    root = _W("")

    head = root.add("FBXHeaderExtension")
    head.add("FBXHeaderVersion", ("I", 1003))
    head.add("FBXVersion", ("I", VERSION))
    head.add("EncryptionType", ("I", 0))
    stamp = head.add("CreationTimeStamp")
    for key, value in (("Version", 1000), ("Year", now.year), ("Month", now.month), ("Day", now.day),
                       ("Hour", now.hour), ("Minute", now.minute), ("Second", now.second),
                       ("Millisecond", now.microsecond // 1000)):
        stamp.add(key, ("I", value))
    head.add("Creator", CREATOR)
    info = head.add("SceneInfo", "GlobalInfo\x00\x01SceneInfo", "UserData")
    info.add("Type", "UserData")
    info.add("Version", ("I", 100))
    meta = info.add("MetaData")
    meta.add("Version", ("I", 100))
    for key in ("Title", "Subject", "Author", "Keywords", "Revision", "Comment"):
        meta.add(key, "")
    props = info.add("Properties70")
    url = os.path.abspath(path) if path else "/untitled.fbx"
    _p(props, "DocumentUrl", "Url", url)
    _p(props, "SrcDocumentUrl", "Url", url)
    for group in ("Original", "LastSaved"):
        _p(props, group, "Compound")
        _p(props, f"{group}|ApplicationVendor", "KString", "Quartz")
        _p(props, f"{group}|ApplicationName", "KString", "Quartz Studio")
        _p(props, f"{group}|ApplicationVersion", "KString", "1.0")
        _p(props, f"{group}|DateTime_GMT", "DateTime", "01/01/1970 00:00:00.000")
    _p(props, "Original|FileName", "KString", url)
    root.add("FileId", FILE_ID)
    root.add("CreationTime", TIME_ID)
    root.add("Creator", CREATOR)

    settings = root.add("GlobalSettings")
    settings.add("Version", ("I", 1000))
    props = settings.add("Properties70")
    for key, value in (("UpAxis", 1), ("UpAxisSign", 1), ("FrontAxis", 2), ("FrontAxisSign", 1),
                       ("CoordAxis", 0), ("CoordAxisSign", 1), ("OriginalUpAxis", 1),
                       ("OriginalUpAxisSign", 1)):
        _p(props, key, "int", value)
    _p(props, "UnitScaleFactor", "double", 1.0)
    _p(props, "OriginalUnitScaleFactor", "double", 1.0)
    _p(props, "AmbientColor", "ColorRGB", _V0)
    _p(props, "DefaultCamera", "KString", "Producer Perspective")
    _p(props, "TimeMode", "enum", 11)
    _p(props, "TimeSpanStart", "KTime", 0)
    _p(props, "TimeSpanStop", "KTime", 46186158000)
    _p(props, "CustomFrameRate", "double", 24.0)

    docs = root.add("Documents")
    docs.add("Count", ("I", 1))
    doc = docs.add("Document", ("L", uid("document")), "Scene", "Scene")
    props = doc.add("Properties70")
    _p(props, "SourceObject", "object")
    _p(props, "ActiveAnimStackName", "KString", "")
    doc.add("RootNode", ("L", 0))
    root.add("References")

    model_ids = [uid(f"model:{i}:{_clean_name(n.name)}") for i, n in enumerate(nodes)]
    has_mesh = [n.mesh is not None and len(n.mesh.points) > 0 for n in nodes]
    geom_count = sum(has_mesh)
    for node in nodes:
        require_finite(path, node, np.asarray(node.matrix, float).reshape(-1, 4))

    definitions = root.add("Definitions")
    definitions.add("Version", ("I", 100))
    definitions.add("Count", ("I", 1 + len(nodes) + geom_count))
    _template(definitions, "GlobalSettings", 1, "", [])
    if nodes:
        _template(definitions, "Model", len(nodes), "FbxNode", _model_template())
    if geom_count:
        _template(definitions, "Geometry", geom_count, "FbxMesh", _GEOMETRY_TEMPLATE)

    objects = root.add("Objects")
    links: list[tuple[int, int]] = []
    for i, node in enumerate(nodes):
        if not has_mesh[i]:
            continue
        name = _clean_name(node.name)
        gid = uid(f"geometry:{i}:{name}")
        require_finite(path, node, np.asarray(node.mesh.points, float))
        pts, pvi, normals = _geometry_arrays(node.mesh)
        geom = objects.add("Geometry", ("L", gid), f"{name}\x00\x01Geometry", "Mesh")
        geom.add("Properties70")
        geom.add("GeometryVersion", ("I", 124))
        geom.add("Vertices", np.ascontiguousarray(pts, dtype=np.float64).reshape(-1))
        geom.add("PolygonVertexIndex", pvi)
        if len(pvi):
            layer_normal = geom.add("LayerElementNormal", ("I", 0))
            layer_normal.add("Version", ("I", 101))
            layer_normal.add("Name", "")
            layer_normal.add("MappingInformationType", "ByPolygonVertex")
            layer_normal.add("ReferenceInformationType", "Direct")
            layer_normal.add("Normals", np.ascontiguousarray(normals, dtype=np.float64).reshape(-1))
            layer = geom.add("Layer", ("I", 0))
            layer.add("Version", ("I", 100))
            element = layer.add("LayerElement")
            element.add("Type", "LayerElementNormal")
            element.add("TypedIndex", ("I", 0))
        links.append((gid, model_ids[i]))
    for i, node in enumerate(nodes):
        name = _clean_name(node.name)
        position, rotation, scale = _local_trs(nodes, parents, i)
        model = objects.add("Model", ("L", model_ids[i]), f"{name}\x00\x01Model",
                            "Mesh" if has_mesh[i] else "Null")
        model.add("Version", ("I", 232))
        props = model.add("Properties70")
        _p(props, "Lcl Translation", "Lcl Translation", position, True)
        _p(props, "Lcl Rotation", "Lcl Rotation", rotation, True)
        _p(props, "Lcl Scaling", "Lcl Scaling", scale, True)
        _p(props, "DefaultAttributeIndex", "int", 0)
        _p(props, "InheritType", "enum", 1)
        model.add("MultiLayer", ("I", 0))
        model.add("MultiTake", ("I", 0))
        model.add("Shading", True)
        model.add("Culling", "CullingOff")
        links.append((model_ids[i], 0 if parents[i] is None else model_ids[parents[i]]))

    connections = root.add("Connections")
    for child, parent in links:
        connections.add("C", "OO", ("L", child), ("L", parent))
    takes = root.add("Takes")
    takes.add("Current", "")
    return root.children


def save(path: str, document: Document, options: dict) -> None:
    compress = bool(options.get("compress", True)) if options else True
    data = encode_binary(build_tree(document, path), VERSION, compress)
    write_atomic(path, data)


def _read_prop(data: bytes, p: int, limit: int):
    if p >= limit:
        raise _Bad("property list overruns its record")
    code = chr(data[p])
    p += 1
    if code == "C":
        if p + 1 > limit:
            raise _Bad("truncated property")
        return data[p], p + 1
    scalar = _SCALARS.get(code)
    if scalar is not None:
        if p + scalar.size > limit:
            raise _Bad("truncated property")
        return scalar.unpack_from(data, p)[0], p + scalar.size
    if code in ("S", "R"):
        if p + 4 > limit:
            raise _Bad("truncated property")
        n = _U32.unpack_from(data, p)[0]
        p += 4
        if p + n > limit:
            raise _Bad("string runs past its record")
        raw = data[p:p + n]
        return (raw.decode("utf-8", "replace") if code == "S" else bytes(raw)), p + n
    dtype = _ARRAY_DTYPES.get(code)
    if dtype is None:
        raise _Bad(f"unknown property type {code!r}")
    if p + 12 > limit:
        raise _Bad("truncated array header")
    count, encoding, size = _ARRAY_HEAD.unpack_from(data, p)
    p += 12
    if p + size > limit:
        raise _Bad("array runs past its record")
    expected = count * np.dtype(dtype).itemsize
    raw = data[p:p + size]
    if encoding == 0:
        if size != expected:
            raise _Bad("array size does not match its length")
    elif encoding == 1:
        try:
            inflater = zlib.decompressobj()
            raw = inflater.decompress(raw, expected + 1)
        except zlib.error as exc:
            raise _Bad(f"corrupt compressed array ({exc})") from None
        if len(raw) != expected:
            raise _Bad("compressed array has the wrong length")
    else:
        raise _Bad(f"unknown array encoding {encoding}")
    return np.frombuffer(raw, dtype=dtype).copy(), p + size


def _parse_binary(data: bytes) -> tuple[int, list[Elem]]:
    if len(data) < 27 or data[:23] != MAGIC:
        raise _Bad("bad binary FBX header")
    version = _U32.unpack_from(data, 23)[0]
    if not 6000 <= version < 10000:
        raise _Bad(f"unsupported FBX version {version}")
    meta = struct.Struct("<3Q" if version >= 7500 else "<3I")
    msize = meta.size
    size = len(data)

    def read(pos: int, depth: int):
        if depth > 64:
            raise _Bad("records nested too deeply")
        if pos + msize + 1 > size:
            raise _Bad("unexpected end of file")
        end, nprops, plen = meta.unpack_from(data, pos)
        namelen = data[pos + msize]
        if end == 0:
            if nprops or plen or namelen:
                raise _Bad("corrupt null record")
            return None, pos + msize + 1
        p = pos + msize + 1
        if end > size:
            raise _Bad("record runs past the end of the file")
        if end < p + namelen + plen:
            raise _Bad("record end offset is inconsistent")
        name = data[p:p + namelen].decode("ascii", "replace")
        p += namelen
        pend = p + plen
        props = []
        for _ in range(nprops):
            value, p = _read_prop(data, p, pend)
            props.append(value)
        if p != pend:
            raise _Bad(f"property list of {name!r} has the wrong length")
        children = []
        while p < end:
            child, p = read(p, depth + 1)
            if child is None:
                break
            children.append(child)
        if p != end:
            raise _Bad(f"record {name!r} does not end at its offset")
        return Elem(name, props, children), end

    top: list[Elem] = []
    pos = 27
    while True:
        elem, pos = read(pos, 0)
        if elem is None:
            break
        top.append(elem)
    return version, top


_NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_TOKEN = re.compile(
    r"(?P<skip>(?:\s+|;[^\n]*)+)"
    r"|(?P<key>[A-Za-z_][\w|\-]*)[ \t]*:"
    r'|"(?P<str>[^"]*)"'
    r"|(?P<num>" + _NUM + r"(?:\s*,\s*" + _NUM + r")*)"
    r"|(?P<open>\{)|(?P<close>\})|(?P<comma>,)"
    r'|(?P<bare>[^\s,{}:";]+)')


def _scalar(text: str):
    text = text.strip()
    if "." in text or "e" in text or "E" in text:
        return float(text)
    return int(text)


def _add_numbers(out: list, seg: str) -> None:
    count = seg.count(",") + 1
    if count <= 16:
        out.extend(_scalar(s) for s in seg.split(","))
        return
    is_float = "." in seg or "e" in seg or "E" in seg
    arr = np.fromstring(seg, dtype=np.float64 if is_float else np.int64, sep=",")
    if arr.size != count:
        raise _Bad("malformed number list")
    out.append(arr)


def _parse_ascii(text: str) -> list[Elem]:
    root = Elem("")
    stack = [root]
    cur: Elem | None = None
    pos, n = 0, len(text)
    match = _TOKEN.match
    while pos < n:
        m = match(text, pos)
        if m is None:
            line = text.count("\n", 0, pos) + 1
            raise _Bad(f"unexpected character {text[pos]!r} on line {line}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "skip" or kind == "comma":
            continue
        if kind == "key":
            cur = Elem(m.group("key"))
            stack[-1].children.append(cur)
        elif kind == "open":
            if cur is None:
                raise _Bad("block without a name")
            stack.append(cur)
            cur = None
        elif kind == "close":
            if len(stack) == 1:
                raise _Bad("unbalanced closing brace")
            stack.pop()
            cur = None
        else:
            if cur is None:
                raise _Bad("value without a name")
            if kind == "str":
                cur.props.append(m.group("str"))
            elif kind == "num":
                _add_numbers(cur.props, m.group("num"))
            else:
                cur.props.append(m.group("bare"))
    if len(stack) != 1:
        raise _Bad("unexpected end of file (unclosed block)")
    return root.children


def _ascii_version(top: list[Elem], text: str) -> int:
    for e in top:
        if e.name == "FBXHeaderExtension":
            v = e.child("FBXVersion")
            if v is not None and v.props and isinstance(v.props[0], int):
                return int(v.props[0])
    m = re.search(r";\s*FBX\s+(\d+)\.(\d+)\.(\d+)", text[:2048])
    if m:
        return int(m.group(1)) * 1000 + int(m.group(2)) * 100 + int(m.group(3)) * 10
    return 7400


def read_tree(data: bytes) -> tuple[int, list[Elem]]:
    if data[:18] == MAGIC[:18]:
        return _parse_binary(data)
    if not data.strip() or b"\x00" in data[:4096]:
        raise _Bad("not an FBX file")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if text.startswith("﻿"):
        text = text[1:]
    top = _parse_ascii(text)
    if not {e.name for e in top} & {"FBXHeaderExtension", "Objects"}:
        raise _Bad("not an FBX file")
    return _ascii_version(top, text), top


def _flat(values: list) -> list:
    out: list = []
    for v in values:
        if isinstance(v, np.ndarray):
            out.extend(v.reshape(-1).tolist())
        else:
            out.append(v)
    return out


def _props(elem: Elem | None) -> dict:
    out: dict = {}
    if elem is None:
        return out
    for block in elem.children:
        if block.name == "Properties70":
            start = 4
        elif block.name == "Properties60":
            start = 3
        else:
            continue
        for p in block.children:
            if p.name in ("P", "Property") and p.props and isinstance(p.props[0], str):
                out[p.props[0]] = _flat(p.props[start:])
    return out


def _num(props: dict, name: str, default: float) -> float:
    values = props.get(name)
    if not values:
        return default
    try:
        value = float(values[0])
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _vec(props: dict, name: str, default: float) -> np.ndarray:
    values = props.get(name)
    if values and len(values) >= 3:
        try:
            out = np.array([float(v) for v in values[:3]])
        except (TypeError, ValueError):
            out = None
        if out is not None and np.all(np.isfinite(out)):
            return out
    return np.full(3, float(default))


def _numbers(elem: Elem | None, dtype) -> np.ndarray:
    if elem is None:
        return np.zeros(0, dtype)
    holder = elem.child("a")
    values = holder.props if holder is not None else elem.props
    parts = []
    for v in values:
        if isinstance(v, np.ndarray):
            parts.append(v.reshape(-1))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            parts.append(np.array([v]))
    if not parts:
        return np.zeros(0, dtype)
    return np.concatenate(parts).astype(dtype)


def _translate(v) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = v
    return m


def _scaling(v) -> np.ndarray:
    return np.diag([float(v[0]), float(v[1]), float(v[2]), 1.0])


_ORDERS = {0: "xyz", 1: "xzy", 2: "yzx", 3: "yxz", 4: "zxy", 5: "zyx", 6: "xyz"}


def _euler(deg, order: int = 0) -> np.ndarray:
    x, y, z = (math.radians(float(a)) for a in deg)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    axes = {"x": np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], float),
            "y": np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], float),
            "z": np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], float)}
    m = np.eye(4)
    for axis in _ORDERS.get(order, "xyz"):
        r = np.eye(4)
        r[:3, :3] = axes[axis]
        m = r @ m
    return m


def _model_matrix(props: dict) -> np.ndarray:
    t = _vec(props, "Lcl Translation", 0.0)
    r = _vec(props, "Lcl Rotation", 0.0)
    s = _vec(props, "Lcl Scaling", 1.0)
    roff = _vec(props, "RotationOffset", 0.0)
    rp = _vec(props, "RotationPivot", 0.0)
    pre = _vec(props, "PreRotation", 0.0)
    post = _vec(props, "PostRotation", 0.0)
    soff = _vec(props, "ScalingOffset", 0.0)
    sp = _vec(props, "ScalingPivot", 0.0)
    order = int(_num(props, "RotationOrder", 0))
    return (_translate(t) @ _translate(roff) @ _translate(rp) @ _euler(pre) @ _euler(r, order)
            @ _euler(post).T @ _translate(-rp) @ _translate(soff) @ _translate(sp) @ _scaling(s)
            @ _translate(-sp))


def _geometric_matrix(props: dict) -> np.ndarray:
    return (_translate(_vec(props, "GeometricTranslation", 0.0))
            @ _euler(_vec(props, "GeometricRotation", 0.0))
            @ _scaling(_vec(props, "GeometricScaling", 1.0)))


def _axes(settings: dict) -> np.ndarray:
    up = int(_num(settings, "UpAxis", 1))
    front = int(_num(settings, "FrontAxis", 2))
    coord = int(_num(settings, "CoordAxis", 0))
    if sorted((up, front, coord)) != [0, 1, 2]:
        return np.eye(3)
    a = np.zeros((3, 3))
    a[0, coord] = -1.0 if _num(settings, "CoordAxisSign", 1) < 0 else 1.0
    a[1, up] = -1.0 if _num(settings, "UpAxisSign", 1) < 0 else 1.0
    a[2, front] = -1.0 if _num(settings, "FrontAxisSign", 1) < 0 else 1.0
    return a


def _object_name(text) -> str:
    text = str(text)
    if "\x00\x01" in text:
        text = text.split("\x00\x01", 1)[0]
    elif "::" in text:
        text = text.split("::", 1)[1]
    return text


def _geometry_polygons(elem: Elem, count: int, offset: int):
    pvi = _numbers(elem.child("PolygonVertexIndex"), np.int64)
    if pvi.size == 0:
        return [], []
    ends = pvi < 0
    idx = np.where(ends, ~pvi, pvi)
    if int(idx.max()) >= count:
        raise _Bad("polygon vertex index out of range")
    ends[-1] = True
    stops = (np.flatnonzero(ends) + 1).tolist()
    starts = [0] + stops[:-1]
    flat = (idx + offset).tolist()
    polys, loose = [], []
    for a, b in zip(starts, stops):
        if b - a >= 3:
            polys.append(tuple(flat[a:b]))
        elif b - a == 2 and flat[a] != flat[a + 1]:
            loose.append((flat[a], flat[a + 1]))
    return polys, loose


def _model_mesh(geoms: list[Elem], geo: np.ndarray, conv: np.ndarray, flip: bool) -> Mesh | None:
    chunks, polys, loose = [], [], []
    offset = 0
    for g in geoms:
        verts = _numbers(g.child("Vertices"), np.float64)
        if verts.size % 3:
            raise _Bad("vertex list length is not a multiple of 3")
        pts = verts.reshape(-1, 3)
        p, l = _geometry_polygons(g, len(pts), offset)
        chunks.append(pts)
        polys += p
        loose += l
        offset += len(pts)
    if offset == 0:
        return None
    pts = np.vstack(chunks)
    pts = pts @ geo[:3, :3].T + geo[:3, 3]
    pts = pts @ conv.T
    if flip:
        polys = [p[::-1] for p in polys]
    return Mesh(pts, polys, loose)


def build_document(version: int, top: list[Elem]) -> Document:
    meta = {"unit": "cm", "up": "y", "handedness": "right", "source": f"FBX {version}"}
    first: dict[str, Elem] = {}
    for e in top:
        first.setdefault(e.name, e)
    objects = first.get("Objects")
    if objects is None:
        return Document([], meta)
    settings_elem = first.get("GlobalSettings") or objects.child("GlobalSettings")
    settings = _props(settings_elem)
    axes = _axes(settings)
    unit = _num(settings, "UnitScaleFactor", 1.0)
    if not unit > 0.0:
        unit = 1.0
    conv = unit * axes
    conv4 = np.eye(4)
    conv4[:3, :3] = conv
    conv4_inv = np.eye(4)
    conv4_inv[:3, :3] = axes.T / unit
    template: dict = {}
    definitions = first.get("Definitions")
    if definitions is not None:
        for obj in definitions.all("ObjectType"):
            if obj.props and obj.props[0] == "Model":
                for tmpl in obj.all("PropertyTemplate"):
                    template.update(_props(tmpl))

    models: dict = {}
    order: list = []
    geometries: dict = {}
    legacy = any(e.name == "Model" and e.props and isinstance(e.props[0], str) for e in objects.children)
    for e in objects.children:
        if e.name == "Model" and e.props:
            if legacy:
                mid, name, kind = e.props[0], _object_name(e.props[0]), (e.props[1] if len(e.props) > 1 else "")
            else:
                mid = e.props[0]
                name = _object_name(e.props[1]) if len(e.props) > 1 else ""
                kind = e.props[2] if len(e.props) > 2 else ""
            if mid in models:
                continue
            props = dict(template)
            props.update(_props(e))
            models[mid] = (name, str(kind), props)
            order.append(mid)
            if legacy and e.child("Vertices") is not None:
                geometries[mid] = e
        elif e.name == "Geometry" and e.props and not legacy:
            kind = e.props[2] if len(e.props) > 2 else ""
            if kind == "Mesh" or e.child("PolygonVertexIndex") is not None:
                geometries[e.props[0]] = e

    parent_of: dict = {}
    geoms_of: dict = {mid: [mid] for mid in models if mid in geometries}
    connections = first.get("Connections")
    if connections is not None:
        for c in connections.children:
            if c.name not in ("C", "Connect") or len(c.props) < 3 or c.props[0] != "OO":
                continue
            child, parent = c.props[1], c.props[2]
            if parent not in models:
                continue
            if child in models:
                if child not in parent_of and child != parent:
                    parent_of[child] = parent
            elif child in geometries:
                geoms_of.setdefault(parent, []).append(child)

    world: dict = {}
    for mid in order:
        chain, seen, cur = [], set(), mid
        while cur is not None and cur not in world:
            if cur in seen:
                raise _Bad("the Model hierarchy has a cycle")
            seen.add(cur)
            chain.append(cur)
            cur = parent_of.get(cur)
        base = world[cur] if cur is not None else np.eye(4)
        for m in reversed(chain):
            base = base @ _model_matrix(models[m][2])
            world[m] = base

    kept = [mid for mid in order if models[mid][1] not in SKIPPED_MODELS]
    kept_set = set(kept)

    def kept_parent(mid):
        p = parent_of.get(mid)
        while p is not None and p not in kept_set:
            p = parent_of.get(p)
        return p

    kids: dict = {}
    roots = []
    for mid in kept:
        p = kept_parent(mid)
        if p is None:
            roots.append(mid)
        else:
            kids.setdefault(p, []).append(mid)
    ordered = []
    stack = list(reversed(roots))
    while stack:
        mid = stack.pop()
        ordered.append(mid)
        stack.extend(reversed(kids.get(mid, [])))

    index = {mid: i for i, mid in enumerate(ordered)}
    axes_flip = float(np.linalg.det(axes)) < 0.0
    nodes = []
    for mid in ordered:
        name, _kind, props = models[mid]
        geo = _geometric_matrix(props)
        flip = axes_flip != (float(np.linalg.det(geo[:3, :3])) < 0.0)
        mesh = _model_mesh([geometries[g] for g in geoms_of.get(mid, [])], geo, conv, flip)
        matrix = conv4 @ world[mid] @ conv4_inv
        p = kept_parent(mid)
        nodes.append(Node(name or "Object", mesh, matrix, index[p] if p is not None else None))
    return Document(nodes, meta)


def load(path: str) -> Document:
    label = os.path.basename(path)
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        version, top = read_tree(data)
        return build_document(version, top)
    except _Bad as exc:
        raise FileFormatError(f"{label}: {exc}") from None
    except OSError as exc:
        raise FileFormatError(f"{label}: {exc.strerror or exc}") from None
    except (struct.error, zlib.error, ValueError, IndexError, KeyError, TypeError, OverflowError,
            RecursionError, MemoryError, np.linalg.LinAlgError) as exc:
        raise FileFormatError(f"{label}: malformed FBX file ({type(exc).__name__}: {exc})") from None


register(FileFormat("fbx", "FBX", (".fbx",), load, save, "Autodesk FBX (binary 7400 export; binary and ASCII import)"))
