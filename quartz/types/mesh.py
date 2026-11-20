import sys
from collections import defaultdict
from typing import Callable, ClassVar

import numpy as np

from quartz.errors import (
    NotImplementedInQuartz,
    PropertyTypeError,
    PropertyValueError,
    ReadOnlyError,
    RemovedStructError,
)
from quartz.geometry import (
    DATA_TYPES,
    REQUIRED_ATTRIBUTES,
    MeshGeometry,
    bounds,
    calc_edges as _calc_edges,
    corner_normals,
    default_fill,
    edge_keys as _edge_keys,
    face_areas,
    face_centers,
    face_edge_keys,
    face_normals,
    flip_faces,
    loose_edges,
    transform_points,
    triangulate,
    vertex_normals,
)
from quartz.math import Vector
from quartz.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    IntVectorProperty,
    StringProperty,
)
from quartz.rna import IDRef, PropArray, PropCollection, Struct, builtin_struct, get_property
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type
from quartz.types.material import Material
from quartz.types.object import register_object_data_type

__all__ = [
    "Mesh", "MeshVertices", "MeshEdges", "MeshLoops", "MeshPolygons", "MeshLoopTriangles",
    "MeshVertex", "MeshEdge", "MeshLoop", "MeshPolygon", "MeshLoopTriangle", "MeshNormalValue",
    "ReadOnlyInteger", "AttributeGroupMesh", "Attribute", "FloatAttributeValue", "IntAttributeValue",
    "ByteIntAttributeValue", "BoolAttributeValue", "FloatVectorAttributeValue", "Float2AttributeValue",
    "FloatColorAttributeValue", "ByteColorAttributeValue", "QuaternionAttributeValue",
    "Float4x4AttributeValue", "Short2AttributeValue", "Int2AttributeValue", "UVLoopLayers",
    "MeshUVLoopLayer", "MeshUVLoop", "IDMaterials", "BlendDataMeshes", "set_editmode_hooks",
]

_ATTR_TYPE_ITEMS = ("FLOAT", "INT", "BOOLEAN", "FLOAT_VECTOR", "FLOAT_COLOR", "QUATERNION", "FLOAT4X4",
                    "STRING", "INT8", "INT16_2D", "INT32_2D", "FLOAT2", "FLOAT4", "BYTE_COLOR")
_ATTR_DOMAIN_ITEMS = ("POINT", "EDGE", "FACE", "CORNER", "CURVE", "INSTANCE", "LAYER")
_UNSUPPORTED_TYPES = ("FLOAT4", "STRING")
_UNSUPPORTED_DOMAINS = ("CURVE", "INSTANCE", "LAYER")
_COLOR_TYPES = ("FLOAT_COLOR", "BYTE_COLOR")
_COLOR_DOMAINS = ("POINT", "CORNER")
_MAX_UV_LAYERS = 8


def _items(*identifiers):
    return [(i, i, "") for i in identifiers]


def _enum_error(value, items) -> PropertyTypeError:
    listing = ", ".join(repr(i) for i in items)
    return PropertyTypeError(f'enum "{value}" not found in ({listing})')


def _channel_for(name: str) -> str:
    if name.startswith(".select_") or name.startswith(".uv_select_"):
        return "SELECT"
    if name.startswith(".hide_"):
        return "VISIBILITY"
    return "GEOMETRY"


def _width(data_type: str) -> int:
    shape = DATA_TYPES[data_type][1]
    w = 1
    for s in shape:
        w *= s
    return w


def _default_array(data_type: str, n: int) -> np.ndarray:
    dtype, shape = DATA_TYPES[data_type]
    arr = np.empty((n, *shape), dtype=dtype)
    arr[...] = default_fill(data_type)
    return arr


def _is_uv(a) -> bool:
    return a is not None and a.domain == "CORNER" and a.data_type == "FLOAT2" and not a.is_internal


def _is_color(a) -> bool:
    return a is not None and a.data_type in _COLOR_TYPES and a.domain in _COLOR_DOMAINS and not a.is_internal


def _lin_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0.0), 1.0 / 2.4) - 0.055)


def _srgb_to_lin(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, np.power((np.maximum(c, 0.0) + 0.055) / 1.055, 2.4))


def _rgb_apply(values: np.ndarray, fn) -> np.ndarray:
    out = np.array(values, dtype=np.float64, copy=True)
    out[..., :3] = fn(out[..., :3])
    return out


def _to_bytes(values: np.ndarray) -> np.ndarray:
    return np.round(np.clip(np.asarray(values, dtype=np.float64), 0.0, 1.0) * 255.0).astype(np.uint8)



def _noop_hook(mesh) -> None:
    return None


_EDIT_HOOKS: dict[str, Callable] = {"enter": _noop_hook, "flush": _noop_hook}


def set_editmode_hooks(*, enter=None, flush=None) -> None:
    _EDIT_HOOKS["enter"] = enter if enter is not None else _noop_hook
    _EDIT_HOOKS["flush"] = flush if flush is not None else _noop_hook



class _Col:

    writable = True

    def __init__(self, domain, attr, data_type, *, lazy=False, invert=False):
        self.domain = domain
        self._attr = attr
        self.data_type = data_type
        self.lazy = lazy
        self.invert = invert
        self.width = _width(data_type)
        self.dtype = DATA_TYPES[data_type][0]

    def attr_name(self) -> str:
        return self._attr

    def channel(self) -> str:
        return _channel_for(self.attr_name())

    def size(self, mesh) -> int:
        return mesh._q_domain_len(self.domain)

    def total(self, mesh) -> int:
        return self.size(mesh) * self.width

    def read(self, mesh) -> np.ndarray:
        a = mesh._q_geometry.attributes.get(self.attr_name())
        arr = _default_array(self.data_type, self.size(mesh)) if a is None else a.data
        return np.logical_not(arr) if self.invert else arr

    def _ensure(self, mesh):
        store = mesh._q_geometry.attributes
        a = store.get(self.attr_name())
        if a is None:
            a = store.new(self.attr_name(), self.data_type, self.domain)
        return a

    def write(self, mesh, key, value) -> None:
        a = self._ensure(mesh)
        v = np.asarray(value)
        if self.invert:
            v = np.logical_not(v)
        a.data[key] = v

    def write_all(self, mesh, flat: np.ndarray) -> None:
        n = self.size(mesh)
        self.write(mesh, slice(None), flat.reshape((n, *DATA_TYPES[self.data_type][1])))


class _PinCol(_Col):

    def __init__(self, layer):
        super().__init__("CORNER", "", "BOOLEAN", lazy=True)
        self._layer = layer

    def attr_name(self) -> str:
        return ".pn." + self._layer._q_live().name


class _Derived:

    writable = False

    def __init__(self, domain, key, fn, width=1, dtype=np.float32):
        self.domain = domain
        self.key = key
        self.fn = fn
        self.width = width
        self.dtype = np.dtype(dtype)

    def channel(self) -> str:
        return "GEOMETRY"

    def size(self, mesh) -> int:
        return mesh._q_domain_len(self.domain)

    def total(self, mesh) -> int:
        return self.size(mesh) * self.width

    def read(self, mesh) -> np.ndarray:
        return mesh._q_cached(self.key, lambda: self.fn(mesh))


class _LoopStartCol:
    writable = True
    domain = "FACE"
    width = 1
    dtype = np.dtype(np.int32)

    def channel(self) -> str:
        return "GEOMETRY"

    def size(self, mesh) -> int:
        return mesh._q_geometry.num_faces

    def total(self, mesh) -> int:
        return self.size(mesh)

    def read(self, mesh) -> np.ndarray:
        return mesh._q_geometry.face_offsets[:-1]

    def write(self, mesh, key, value) -> None:
        starts = np.array(mesh._q_geometry.face_offsets[:-1], dtype=np.int64, copy=True)
        starts[key] = np.asarray(value)
        try:
            mesh._q_geometry.set_face_offsets(starts)
        except ValueError as exc:
            raise PropertyValueError(str(exc)) from exc

    def write_all(self, mesh, flat: np.ndarray) -> None:
        self.write(mesh, slice(None), flat)


class _PolyVertsCol:

    writable = True
    domain = "FACE"
    width = 1
    dtype = np.dtype(np.int32)

    def channel(self) -> str:
        return "GEOMETRY"

    def size(self, mesh) -> int:
        return mesh._q_geometry.num_faces

    def total(self, mesh) -> int:
        return mesh._q_geometry.num_corners

    def read(self, mesh) -> np.ndarray:
        return mesh._q_geometry.corner_verts

    def write_all(self, mesh, flat: np.ndarray) -> None:
        mesh._q_geometry.corner_verts[...] = flat


class _AttrDataCol:

    writable = True
    domain = None

    def __init__(self, proxy, conv=None):
        self._proxy = proxy
        self._conv = conv
        dt = proxy._q_attr.data_type
        self.data_type = dt
        self.width = _width(dt)
        self.dtype = np.dtype(np.float64) if conv else DATA_TYPES[dt][0]

    def _arr(self):
        return self._proxy._q_live()

    def channel(self) -> str:
        return _channel_for(self._arr().name)

    def size(self, mesh) -> int:
        return int(self._arr().data.shape[0])

    def total(self, mesh) -> int:
        return self.size(mesh) * self.width

    def read(self, mesh) -> np.ndarray:
        data = self._arr().data
        conv = self._conv
        if conv is None:
            return data
        if conv == "lin_to_srgb":
            return _rgb_apply(data, _lin_to_srgb).astype(np.float32)
        if conv == "byte_linear":
            return _rgb_apply(data.astype(np.float64) / 255.0, _srgb_to_lin).astype(np.float32)
        return (data.astype(np.float64) / 255.0).astype(np.float32)

    def write(self, mesh, key, value) -> None:
        data = self._arr().data
        conv = self._conv
        if conv is None:
            data[key] = np.asarray(value)
            return
        v = np.asarray(value, dtype=np.float64)
        if conv == "lin_to_srgb":
            data[key] = _rgb_apply(v, _srgb_to_lin)
        elif conv == "byte_linear":
            data[key] = _to_bytes(_rgb_apply(np.clip(v, 0.0, 1.0), _lin_to_srgb))
        else:
            data[key] = _to_bytes(v)

    def write_all(self, mesh, flat: np.ndarray) -> None:
        shape = DATA_TYPES[self.data_type][1]
        self.write(mesh, slice(None), flat.reshape((self.size(mesh), *shape)))



class _ProxyItem(Struct):

    _q_strict_attrs = True

    def _q_check(self) -> int:
        i = self._q_index
        if i >= len(self._q_coll):
            raise IndexError(f"{type(self).__name__} index {i} out of range")
        return i

    def _q_mesh(self):
        return self._q_coll._q_mesh

    def _q_get(self, name):
        coll = self._q_coll
        col = coll._q_table[name]
        i = self._q_check()
        v = col.read(coll._q_mesh)[i]
        if isinstance(v, np.ndarray):
            return v if col.writable else v.copy()
        return v.item() if isinstance(v, np.generic) else v

    def _q_set(self, name, value) -> None:
        coll = self._q_coll
        col = coll._q_table[name]
        i = self._q_check()
        mesh = coll._q_mesh
        col.write(mesh, i, value)
        mesh.q_tag(col.channel())

    def _q_on_change(self, pdef) -> None:
        return None

    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented
        return self._q_owner is other._q_owner and self._q_index == other._q_index

    def __hash__(self):
        return hash((type(self), id(self._q_owner), self._q_index))


@builtin_struct
class MeshVertex(_ProxyItem):
    co: FloatVectorProperty(subtype='TRANSLATION', unit='LENGTH', size=3, soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("co"), "virtual_set": lambda s, v: s._q_set("co", v)})
    normal: FloatVectorProperty(subtype='DIRECTION', size=3, soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("normal")})
    select: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get("select"), "virtual_set": lambda s, v: s._q_set("select", v)})
    hide: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get("hide"), "virtual_set": lambda s, v: s._q_set("hide", v)})
    index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("index")})
    undeformed_co: FloatVectorProperty(subtype='TRANSLATION', unit='LENGTH', size=3, soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("undeformed_co")})

    @property
    def groups(self):
        self._q_check()
        return _EmptyCollection(owner=self, path="groups")


@builtin_struct
class MeshEdge(_ProxyItem):
    vertices: IntVectorProperty(subtype='UNSIGNED', size=2, min=0, soft_max=10000, options=set(), meta={"virtual_get": lambda s: s._q_get("vertices"), "virtual_set": lambda s, v: s._q_set("vertices", v)})
    select: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get("select"), "virtual_set": lambda s, v: s._q_set("select", v)})
    hide: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get("hide"), "virtual_set": lambda s, v: s._q_set("hide", v)})
    use_seam: BoolProperty(meta={"virtual_get": lambda s: s._q_get("use_seam"), "virtual_set": lambda s, v: s._q_set("use_seam", v)})
    use_edge_sharp: BoolProperty(meta={"virtual_get": lambda s: s._q_get("use_edge_sharp"), "virtual_set": lambda s, v: s._q_set("use_edge_sharp", v)})
    is_loose: BoolProperty(meta={"virtual_get": lambda s: s._q_get("is_loose")})
    index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("index")})

    @property
    def key(self):
        i = self._q_check()
        a, b = (int(x) for x in self._q_mesh()._q_geometry.edges[i])
        return (a, b) if a <= b else (b, a)


@builtin_struct
class MeshLoop(_ProxyItem):
    vertex_index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, options=set(), meta={"virtual_get": lambda s: s._q_get("vertex_index"), "virtual_set": lambda s, v: s._q_set("vertex_index", v)})
    edge_index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, options=set(), meta={"virtual_get": lambda s: s._q_get("edge_index"), "virtual_set": lambda s, v: s._q_set("edge_index", v)})
    index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("index")})
    normal: FloatVectorProperty(subtype='DIRECTION', size=3, min=-1.0, max=1.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("normal")})
    tangent: FloatVectorProperty(subtype='DIRECTION', size=3, min=-1.0, max=1.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("tangent")})
    bitangent_sign: FloatProperty(min=-1.0, max=1.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("bitangent_sign")})
    bitangent: FloatVectorProperty(subtype='DIRECTION', size=3, min=-1.0, max=1.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("bitangent")})


@builtin_struct
class MeshPolygon(_ProxyItem):
    loop_start: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, options=set(), meta={"virtual_get": lambda s: s._q_get("loop_start"), "virtual_set": lambda s, v: s._q_set("loop_start", v)})
    loop_total: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("loop_total")})
    material_index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("material_index"), "virtual_set": lambda s, v: s._q_set("material_index", v)})
    select: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get("select"), "virtual_set": lambda s, v: s._q_set("select", v)})
    hide: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get("hide"), "virtual_set": lambda s, v: s._q_set("hide", v)})
    use_smooth: BoolProperty(meta={"virtual_get": lambda s: s._q_get("use_smooth"), "virtual_set": lambda s, v: s._q_set("use_smooth", v)})
    normal: FloatVectorProperty(subtype='DIRECTION', size=3, min=-1.0, max=1.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("normal")})
    center: FloatVectorProperty(subtype='XYZ', size=3, soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("center")})
    area: FloatProperty(subtype='UNSIGNED', min=0.0, soft_max=10000.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("area")})
    index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("index")})

    def _q_range(self) -> tuple[int, int]:
        i = self._q_check()
        offsets = self._q_mesh()._q_geometry.face_offsets
        return int(offsets[i]), int(offsets[i + 1])

    @property
    def vertices(self):
        start, end = self._q_range()
        mesh = self._q_mesh()
        view = mesh._q_geometry.corner_verts[start:end]
        return PropArray(view, on_write=lambda: mesh.q_tag("GEOMETRY"), owner=self)

    @vertices.setter
    def vertices(self, value):
        start, end = self._q_range()
        try:
            values = np.asarray(list(value), dtype=np.int64).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise PropertyTypeError(f"MeshPolygon.vertices expected a sequence of ints, not {type(value).__name__}") from exc
        if values.size != end - start:
            raise PropertyValueError(
                f"MeshPolygon.vertices: sequence of {values.size} items does not match loop_total {end - start}")
        mesh = self._q_mesh()
        mesh._q_geometry.corner_verts[start:end] = values
        mesh.q_tag("GEOMETRY")

    @property
    def edge_keys(self):
        i = self._q_check()
        return face_edge_keys(self._q_mesh()._q_geometry, i)

    @property
    def loop_indices(self):
        start, end = self._q_range()
        return range(start, end)

    def flip(self) -> None:
        i = self._q_check()
        mesh = self._q_mesh()
        mask = np.zeros(mesh._q_geometry.num_faces, dtype=bool)
        mask[i] = True
        flip_faces(mesh._q_geometry, mask)
        mesh.q_tag("GEOMETRY")


@builtin_struct
class MeshLoopTriangle(_ProxyItem):
    vertices: IntVectorProperty(subtype='UNSIGNED', size=3, min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("vertices")})
    loops: IntVectorProperty(subtype='UNSIGNED', size=3, min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("loops")})
    polygon_index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("polygon_index")})
    normal: FloatVectorProperty(subtype='DIRECTION', size=3, min=-1.0, max=1.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("normal")})
    split_normals: FloatVectorProperty(subtype='DIRECTION', size=(3, 3), min=-1.0, max=1.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("split_normals")})
    area: FloatProperty(subtype='UNSIGNED', min=0.0, soft_max=10000.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("area")})
    index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("index")})
    material_index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get("material_index")})
    use_smooth: BoolProperty(meta={"virtual_get": lambda s: s._q_get("use_smooth")})

    @property
    def center(self):
        i = self._q_check()
        mesh = self._q_mesh()
        verts = mesh._q_tris_data()["vertices"][i]
        pts = mesh._q_geometry.positions[verts].astype(np.float64)
        return Vector(tuple(pts.mean(axis=0)))

    @property
    def edge_keys(self):
        i = self._q_check()
        v0, v1, v2 = (int(x) for x in self._q_mesh()._q_tris_data()["vertices"][i])

        def key(a, b):
            return (a, b) if a <= b else (b, a)
        return [key(v0, v1), key(v1, v2), key(v0, v2)]


@builtin_struct
class MeshNormalValue(_ProxyItem):
    vector: FloatVectorProperty(subtype='DIRECTION', size=3, min=-1.0, max=1.0, step=10.0, precision=3, meta={"virtual_get": lambda s: s._q_get("vector")})


@builtin_struct
class ReadOnlyInteger(_ProxyItem):
    value: IntProperty(meta={"virtual_get": lambda s: s._q_get("value")})


@builtin_struct
class FloatAttributeValue(_ProxyItem):
    value: FloatProperty(meta={"virtual_get": lambda s: s._q_get("value"), "virtual_set": lambda s, v: s._q_set("value", v)})


@builtin_struct
class IntAttributeValue(_ProxyItem):
    value: IntProperty(meta={"virtual_get": lambda s: s._q_get("value"), "virtual_set": lambda s, v: s._q_set("value", v)})


@builtin_struct
class ByteIntAttributeValue(_ProxyItem):
    value: IntProperty(min=-128, max=127, meta={"virtual_get": lambda s: s._q_get("value"), "virtual_set": lambda s, v: s._q_set("value", v)})


@builtin_struct
class BoolAttributeValue(_ProxyItem):
    value: BoolProperty(meta={"virtual_get": lambda s: s._q_get("value"), "virtual_set": lambda s, v: s._q_set("value", v)})


@builtin_struct
class FloatVectorAttributeValue(_ProxyItem):
    vector: FloatVectorProperty(subtype='XYZ', size=3, meta={"virtual_get": lambda s: s._q_get("vector"), "virtual_set": lambda s, v: s._q_set("vector", v)})


@builtin_struct
class Float2AttributeValue(_ProxyItem):
    vector: FloatVectorProperty(subtype='XYZ', size=2, meta={"virtual_get": lambda s: s._q_get("vector"), "virtual_set": lambda s, v: s._q_set("vector", v)})


@builtin_struct
class FloatColorAttributeValue(_ProxyItem):
    color: FloatVectorProperty(subtype='COLOR', size=4, meta={"virtual_get": lambda s: s._q_get("color"), "virtual_set": lambda s, v: s._q_set("color", v)})
    color_srgb: FloatVectorProperty(subtype='COLOR', size=4, meta={"virtual_get": lambda s: s._q_get("color_srgb"), "virtual_set": lambda s, v: s._q_set("color_srgb", v)})


@builtin_struct
class ByteColorAttributeValue(_ProxyItem):
    color: FloatVectorProperty(subtype='COLOR', size=4, meta={"virtual_get": lambda s: s._q_get("color"), "virtual_set": lambda s, v: s._q_set("color", v)})
    color_srgb: FloatVectorProperty(subtype='COLOR', size=4, meta={"virtual_get": lambda s: s._q_get("color_srgb"), "virtual_set": lambda s, v: s._q_set("color_srgb", v)})


@builtin_struct
class QuaternionAttributeValue(_ProxyItem):
    value: FloatVectorProperty(subtype='QUATERNION', size=4, default=(1.0, 0.0, 0.0, 0.0), meta={"virtual_get": lambda s: s._q_get("value"), "virtual_set": lambda s, v: s._q_set("value", v)})


@builtin_struct
class Float4x4AttributeValue(_ProxyItem):
    value: FloatVectorProperty(subtype='MATRIX', size=(4, 4), default=((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)), meta={"virtual_get": lambda s: s._q_get("value"), "virtual_set": lambda s, v: s._q_set("value", v)})


@builtin_struct
class Short2AttributeValue(_ProxyItem):
    value: IntVectorProperty(size=2, min=-32768, max=32767, meta={"virtual_get": lambda s: s._q_get("value"), "virtual_set": lambda s, v: s._q_set("value", v)})


@builtin_struct
class Int2AttributeValue(_ProxyItem):
    value: IntVectorProperty(size=2, meta={"virtual_get": lambda s: s._q_get("value"), "virtual_set": lambda s, v: s._q_set("value", v)})


@builtin_struct
class MeshUVLoop(_ProxyItem):
    uv: FloatVectorProperty(subtype='XYZ', size=2, meta={"virtual_get": lambda s: s._q_get("uv"), "virtual_set": lambda s, v: s._q_set("uv", v)})
    select: BoolProperty(meta={"virtual_get": lambda s: s._q_get("select"), "virtual_set": lambda s, v: s._q_set("select", v)})
    select_edge: BoolProperty(meta={"virtual_get": lambda s: s._q_get("select_edge"), "virtual_set": lambda s, v: s._q_set("select_edge", v)})
    pin_uv: BoolProperty(meta={"virtual_get": lambda s: s._q_get("pin_uv"), "virtual_set": lambda s, v: s._q_set("pin_uv", v)})


_VALUE_CLASSES: dict[str, tuple[type, tuple[tuple[str, str | None], ...]]] = {
    "FLOAT": (FloatAttributeValue, (("value", None),)),
    "INT": (IntAttributeValue, (("value", None),)),
    "INT8": (ByteIntAttributeValue, (("value", None),)),
    "BOOLEAN": (BoolAttributeValue, (("value", None),)),
    "FLOAT_VECTOR": (FloatVectorAttributeValue, (("vector", None),)),
    "FLOAT2": (Float2AttributeValue, (("vector", None),)),
    "FLOAT_COLOR": (FloatColorAttributeValue, (("color", None), ("color_srgb", "lin_to_srgb"))),
    "BYTE_COLOR": (ByteColorAttributeValue, (("color", "byte_linear"), ("color_srgb", "byte_srgb"))),
    "QUATERNION": (QuaternionAttributeValue, (("value", None),)),
    "FLOAT4X4": (Float4x4AttributeValue, (("value", None),)),
    "INT16_2D": (Short2AttributeValue, (("value", None),)),
    "INT32_2D": (Int2AttributeValue, (("value", None),)),
}



class _EmptyCollection(PropCollection):
    def _q_items(self):
        return []


class _ProxyCollection(PropCollection):

    def __init__(self, mesh, owner, path, item_cls, table, length):
        PropCollection.__init__(self, owner=owner, path=path)
        self._q_mesh = mesh
        self._q_item_cls = item_cls
        self._q_table = table
        self._q_length = length

    def __len__(self) -> int:
        return int(self._q_length())

    def _q_make(self, i: int):
        item = self._q_item_cls._q_new_child(self._owner, f"{self._path}[{i}]")
        item._q_index = i
        item._q_coll = self
        return item

    def _q_items(self):
        return [self._q_make(i) for i in range(len(self))]

    def __getitem__(self, key):
        n = len(self)
        if isinstance(key, slice):
            return [self._q_make(i) for i in range(*key.indices(n))]
        if isinstance(key, str):
            raise KeyError(f'bpy_prop_collection[key]: key "{key}" not found')
        if isinstance(key, bool) or not isinstance(key, (int, np.integer)):
            raise TypeError(f"bpy_prop_collection[key]: invalid key, must be an int, not {type(key).__name__}")
        i = int(key)
        if i < 0:
            i += n
        if i < 0 or i >= n:
            raise IndexError(f"bpy_prop_collection[index]: index {int(key)} out of range, size {n}")
        return self._q_make(i)

    def __iter__(self):
        for i in range(len(self)):
            yield self._q_make(i)

    def __contains__(self, key) -> bool:
        if isinstance(key, str):
            return False
        return any(item == key for item in self)

    def keys(self) -> list:
        return []

    def __repr__(self) -> str:
        idd = self.id_data
        if idd is not None:
            return f"{repr(idd)}.{self.path_from_id()}"
        return super().__repr__()

    def _q_column(self, attr: str, setting: bool):
        col = self._q_table.get(attr) if isinstance(attr, str) else None
        if col is not None:
            return col
        if isinstance(attr, str) and get_property(self._q_item_cls, attr) is not None:
            return None
        raise AttributeError(
            f"foreach_{'set' if setting else 'get'}('{attr}', ...): '{self._q_item_cls.__name__}' object has no attribute '{attr}'")

    @staticmethod
    def _seq_len(seq) -> int:
        return int(seq.size) if isinstance(seq, np.ndarray) else len(seq)

    def foreach_get(self, attr, seq):
        col = self._q_column(attr, False)
        if col is None:
            return PropCollection.foreach_get(self, attr, seq)
        mesh = self._q_mesh
        total = col.total(mesh)
        if self._seq_len(seq) != total:
            raise PropertyValueError("foreach_get(...): sequence size mismatch")
        values = np.asarray(col.read(mesh)).reshape(-1)
        if isinstance(seq, np.ndarray):
            np.copyto(seq, values.reshape(seq.shape), casting="unsafe")
        elif isinstance(seq, list):
            seq[:] = values.tolist()
        else:
            for i, v in enumerate(values.tolist()):
                seq[i] = v

    def foreach_set(self, attr, seq):
        col = self._q_column(attr, True)
        if col is None:
            return PropCollection.foreach_set(self, attr, seq)
        if not col.writable:
            raise ReadOnlyError(
                f'foreach_set(...): attribute "{attr}" from "{self._q_item_cls.__name__}" is read-only')
        mesh = self._q_mesh
        total = col.total(mesh)
        if self._seq_len(seq) != total:
            raise PropertyValueError("foreach_set(...): sequence size mismatch")
        arr = np.asarray(seq).reshape(-1)
        if col.dtype == np.dtype(np.bool_):
            arr = arr != 0
        else:
            arr = arr.astype(col.dtype, casting="unsafe")
        col.write_all(mesh, arr)
        mesh.q_tag(col.channel())


class _ElementCollection(_ProxyCollection):
    _q_domain: ClassVar[str] = ""

    def __init__(self, mesh, path, item_cls, table):
        domain = self._q_domain
        super().__init__(mesh, mesh, path, item_cls, table, lambda: mesh._q_domain_len(domain))

    def _q_add(self, count, fn) -> None:
        if isinstance(count, bool) or not isinstance(count, (int, np.integer)):
            raise PropertyTypeError(f"add(): count expected an int type, not {type(count).__name__}")
        if count < 0:
            raise PropertyValueError(f"add(): count must be >= 0, not {int(count)}")
        fn(int(count))
        self._q_mesh._q_after_structure()


class MeshVertices(_ElementCollection):
    _q_domain = "POINT"

    def add(self, count: int) -> None:
        self._q_add(count, self._q_mesh._q_geometry.add_verts)


class MeshEdges(_ElementCollection):
    _q_domain = "EDGE"

    def add(self, count: int) -> None:
        self._q_add(count, self._q_mesh._q_geometry.add_edges)


class MeshLoops(_ElementCollection):
    _q_domain = "CORNER"

    def add(self, count: int) -> None:
        self._q_add(count, self._q_mesh._q_geometry.add_corners)


class MeshPolygons(_ElementCollection):
    _q_domain = "FACE"

    def add(self, count: int) -> None:
        self._q_add(count, self._q_mesh._q_geometry.add_faces)

    @property
    def active(self) -> int:
        return self._q_mesh._q_poly_active

    @active.setter
    def active(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise PropertyTypeError(f"MeshPolygons.active expected an int type, not {type(value).__name__}")
        self._q_mesh._q_poly_active = int(value)


class MeshLoopTriangles(_ElementCollection):
    _q_domain = "TRI"


def _tri_col(name, width=1, dtype=np.float32):
    return _Derived("TRI", "tri:" + name, lambda m: m._q_tris_data()[name], width, dtype)


def _index_col(domain):
    return _Derived(domain, "index:" + domain, lambda m: np.arange(m._q_domain_len(domain), dtype=np.int32), 1, np.int32)


def _corner_normals(mesh):
    geo = mesh._q_geometry
    sharp = geo.attributes.get("sharp_face")
    return corner_normals(geo, sharp_face=None if sharp is None else sharp.data)


_VERTEX_TABLE = {
    "co": _Col("POINT", "position", "FLOAT_VECTOR"),
    "undeformed_co": _Derived("POINT", "undeformed_co", lambda m: m._q_geometry.positions.copy(), 3),
    "normal": _Derived("POINT", "vertex_normals", lambda m: vertex_normals(m._q_geometry), 3),
    "select": _Col("POINT", ".select_vert", "BOOLEAN", lazy=True),
    "hide": _Col("POINT", ".hide_vert", "BOOLEAN", lazy=True),
    "index": _index_col("POINT"),
}
_EDGE_TABLE = {
    "vertices": _Col("EDGE", ".edge_verts", "INT32_2D"),
    "select": _Col("EDGE", ".select_edge", "BOOLEAN", lazy=True),
    "hide": _Col("EDGE", ".hide_edge", "BOOLEAN", lazy=True),
    "use_seam": _Col("EDGE", "uv_seam", "BOOLEAN", lazy=True),
    "use_edge_sharp": _Col("EDGE", "sharp_edge", "BOOLEAN", lazy=True),
    "is_loose": _Derived("EDGE", "loose_edges", lambda m: loose_edges(m._q_geometry), 1, np.bool_),
    "index": _index_col("EDGE"),
}
_LOOP_TABLE = {
    "vertex_index": _Col("CORNER", ".corner_vert", "INT"),
    "edge_index": _Col("CORNER", ".corner_edge", "INT"),
    "normal": _Derived("CORNER", "corner_normals", _corner_normals, 3),
    "tangent": _Derived("CORNER", "tangent", lambda m: np.zeros((m._q_geometry.num_corners, 3), np.float32), 3),
    "bitangent": _Derived("CORNER", "bitangent", lambda m: np.zeros((m._q_geometry.num_corners, 3), np.float32), 3),
    "bitangent_sign": _Derived("CORNER", "bitangent_sign", lambda m: np.zeros(m._q_geometry.num_corners, np.float32)),
    "index": _index_col("CORNER"),
}
_POLYGON_TABLE = {
    "loop_start": _LoopStartCol(),
    "loop_total": _Derived("FACE", "loop_total", lambda m: m._q_geometry.face_sizes(), 1, np.int32),
    "vertices": _PolyVertsCol(),
    "material_index": _Col("FACE", "material_index", "INT", lazy=True),
    "use_smooth": _Col("FACE", "sharp_face", "BOOLEAN", lazy=True, invert=True),
    "select": _Col("FACE", ".select_poly", "BOOLEAN", lazy=True),
    "hide": _Col("FACE", ".hide_poly", "BOOLEAN", lazy=True),
    "normal": _Derived("FACE", "face_normals", lambda m: face_normals(m._q_geometry), 3),
    "center": _Derived("FACE", "face_centers", lambda m: face_centers(m._q_geometry), 3),
    "area": _Derived("FACE", "face_areas", lambda m: face_areas(m._q_geometry)),
    "index": _index_col("FACE"),
}
_TRI_TABLE = {
    "vertices": _tri_col("vertices", 3, np.int32),
    "loops": _tri_col("loops", 3, np.int32),
    "polygon_index": _tri_col("polygon_index", 1, np.int32),
    "normal": _tri_col("normal", 3),
    "split_normals": _tri_col("split_normals", 9),
    "area": _tri_col("area"),
    "material_index": _tri_col("material_index", 1, np.int32),
    "use_smooth": _tri_col("use_smooth", 1, np.bool_),
    "index": _index_col("TRI"),
}
_VNORMAL_TABLE = {"vector": _VERTEX_TABLE["normal"]}
_PNORMAL_TABLE = {"vector": _POLYGON_TABLE["normal"]}
_CNORMAL_TABLE = {"vector": _LOOP_TABLE["normal"]}
_TRI_POLY_TABLE = {"value": _TRI_TABLE["polygon_index"]}

_ELEMENT_COLLECTIONS = {
    "vertices": (MeshVertices, MeshVertex, _VERTEX_TABLE),
    "edges": (MeshEdges, MeshEdge, _EDGE_TABLE),
    "loops": (MeshLoops, MeshLoop, _LOOP_TABLE),
    "polygons": (MeshPolygons, MeshPolygon, _POLYGON_TABLE),
    "loop_triangles": (MeshLoopTriangles, MeshLoopTriangle, _TRI_TABLE),
}
_DERIVED_COLLECTIONS = {
    "vertex_normals": ("POINT", MeshNormalValue, _VNORMAL_TABLE),
    "polygon_normals": ("FACE", MeshNormalValue, _PNORMAL_TABLE),
    "corner_normals": ("CORNER", MeshNormalValue, _CNORMAL_TABLE),
    "loop_triangle_polygons": ("TRI", ReadOnlyInteger, _TRI_POLY_TABLE),
}



class _LayerProxy(Struct):

    _q_strict_attrs = True
    _q_rna_label: ClassVar[str] = "Attribute"

    def _q_alive(self) -> bool:
        a = self._q_attr
        return self._q_owner._q_geometry.attributes.get(a.name) is a

    def _q_live(self):
        if not self._q_alive():
            raise RemovedStructError(f"StructRNA of type {self._q_rna_label} has been removed")
        return self._q_attr

    def _q_value_collection(self, key, path, table, item_cls):
        cache = self._q_colls
        coll = cache.get(key)
        if coll is None:
            mesh = self._q_owner
            coll = _ProxyCollection(mesh, self, path, item_cls, table, lambda: self._q_live().data.shape[0])
            cache[key] = coll
        return coll


@builtin_struct
class Attribute(_LayerProxy):
    name: StringProperty(options=set(), meta={"virtual_get": lambda s: s._q_get_name(), "virtual_set": lambda s, v: s._q_set_name(v), "dirty": "GEOMETRY"})
    data_type: EnumProperty(items=_items('FLOAT', 'INT', 'BOOLEAN', 'FLOAT_VECTOR', 'FLOAT_COLOR', 'QUATERNION', 'FLOAT4X4', 'STRING', 'INT8', 'INT16_2D', 'INT32_2D', 'FLOAT2', 'FLOAT4', 'BYTE_COLOR'), default='FLOAT', meta={"virtual_get": lambda s: s._q_get_data_type()})
    storage_type: EnumProperty(items=_items('ARRAY', 'SINGLE'), default='ARRAY', meta={"virtual_get": lambda s: s._q_get_storage_type()})
    domain: EnumProperty(items=_items('POINT', 'EDGE', 'FACE', 'CORNER', 'CURVE', 'INSTANCE', 'LAYER'), default='POINT', meta={"virtual_get": lambda s: s._q_get_domain()})
    is_internal: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_internal()})
    is_required: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_required()})

    def _q_get_name(self):
        return self._q_live().name

    def _q_set_name(self, value):
        self._q_owner._q_rename_attribute(self._q_live(), value)

    def _q_get_data_type(self):
        return self._q_live().data_type

    def _q_get_storage_type(self):
        self._q_live()
        return "ARRAY"

    def _q_get_domain(self):
        return self._q_live().domain

    def _q_get_is_internal(self):
        return self._q_live().is_internal

    def _q_get_is_required(self):
        return self._q_live().is_required

    @property
    def data(self):
        a = self._q_live()
        item_cls, specs = _VALUE_CLASSES[a.data_type]
        coll = self._q_colls.get("data")
        if coll is None:
            table = {name: _AttrDataCol(self, conv) for name, conv in specs}
            coll = self._q_value_collection("data", "data", table, item_cls)
        return coll

    def q_array(self) -> np.ndarray:
        return self._q_live().data


@builtin_struct
class MeshUVLoopLayer(_LayerProxy):
    _q_rna_label = "MeshUVLoopLayer"
    name: StringProperty(maxlen=64, options=set(), meta={"virtual_get": lambda s: s._q_get_name(), "virtual_set": lambda s, v: s._q_set_name(v), "dirty": "GEOMETRY"})
    active: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get_active(), "virtual_set": lambda s, v: s._q_set_active(v)})
    active_render: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get_active_render(), "virtual_set": lambda s, v: s._q_set_active_render(v)})
    active_clone: BoolProperty(options=set(), meta={"virtual_get": lambda s: s._q_get_active_clone(), "virtual_set": lambda s, v: s._q_set_active_clone(v)})

    def _q_get_name(self):
        return self._q_live().name

    def _q_set_name(self, value):
        self._q_owner._q_rename_attribute(self._q_live(), value)

    def _q_get_active(self):
        name = self._q_live().name
        return self._q_owner._q_layer("uv_active") == name

    def _q_set_active(self, value):
        name = self._q_live().name
        if value:
            self._q_owner._q_layers["uv_active"] = name

    def _q_get_active_render(self):
        name = self._q_live().name
        return self._q_owner._q_layer("uv_render") == name

    def _q_set_active_render(self, value):
        name = self._q_live().name
        if value:
            self._q_owner._q_layers["uv_render"] = name

    def _q_get_active_clone(self):
        self._q_live()
        return False

    def _q_set_active_clone(self, value):
        self._q_live()

    @property
    def data(self):
        self._q_live()
        table = {
            "uv": _AttrDataCol(self),
            "pin_uv": _PinCol(self),
            "select": _Col("CORNER", ".uv_select_vert", "BOOLEAN", lazy=True),
            "select_edge": _Col("CORNER", ".uv_select_edge", "BOOLEAN", lazy=True),
        }
        if "data" in self._q_colls:
            return self._q_colls["data"]
        return self._q_value_collection("data", "data", table, MeshUVLoop)

    @property
    def uv(self):
        self._q_live()
        if "uv" in self._q_colls:
            return self._q_colls["uv"]
        return self._q_value_collection("uv", "uv", {"vector": _AttrDataCol(self)}, Float2AttributeValue)

    @property
    def pin(self):
        self._q_live()
        if "pin" in self._q_colls:
            return self._q_colls["pin"]
        return self._q_value_collection("pin", "pin", {"value": _PinCol(self)}, BoolAttributeValue)

    def pin_ensure(self):
        a = self._q_live()
        mesh = self._q_owner
        store = mesh._q_geometry.attributes
        pname = ".pn." + a.name
        pin = store.get(pname)
        if pin is None:
            pin = store.new(pname, "BOOLEAN", "CORNER", fill=False)
            mesh.q_tag("GEOMETRY")
        return mesh._q_attribute_proxy(pin)


def _new_layer_proxy(cls, mesh, arr, path):
    proxy = cls._q_new_child(mesh, path)
    proxy._q_attr = arr
    proxy._q_colls = {}
    return proxy


def _attr_path(name: str) -> str:
    return f'attributes["{name}"]'


def _uv_path(name: str) -> str:
    return f'uv_layers["{name}"]'



@builtin_struct(identifier="AttributeGroupMesh")
class AttributeGroupMesh(PropCollection):
    active_index: IntProperty(min=-1, options=set(), meta={"virtual_get": lambda s: s._q_get_active_index(), "virtual_set": lambda s, v: s._q_set_active_index(v)})
    active_color_index: IntProperty(soft_min=-10000, soft_max=10000, options=set(), meta={"virtual_get": lambda s: s._q_get_active_color_index(), "virtual_set": lambda s, v: s._q_set_active_color_index(v)})
    render_color_index: IntProperty(soft_min=-10000, soft_max=10000, options=set(), meta={"virtual_get": lambda s: s._q_get_render_color_index(), "virtual_set": lambda s, v: s._q_set_render_color_index(v)})
    default_color_name: StringProperty(maxlen=64, options=set(), meta={"virtual_get": lambda s: s._q_get_default_color_name(), "virtual_set": lambda s, v: s._q_set_default_color_name(v)})
    active_color_name: StringProperty(maxlen=64, options=set(), meta={"virtual_get": lambda s: s._q_get_active_color_name(), "virtual_set": lambda s, v: s._q_set_active_color_name(v)})

    _q_strict_attrs = True

    def __init__(self, mesh, *, colors_only: bool):
        PropCollection.__init__(self, owner=mesh, path="color_attributes" if colors_only else "attributes")
        self._p = {}
        self._p_set = set()
        self._q_mesh = mesh
        self._q_colors_only = bool(colors_only)

    def __setattr__(self, name, value):
        for klass in type(self).__mro__:
            if name in klass.__dict__:
                attr = klass.__dict__[name]
                if hasattr(type(attr), "__set__"):
                    attr.__set__(self, value)
                    return
                break
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @property
    def rna_type(self):
        return type(self).bl_rna

    def _q_on_change(self, pdef) -> None:
        self._q_mesh.q_tag(pdef.meta.get("dirty", "DATA"))

    def __repr__(self) -> str:
        return f"{repr(self._q_mesh)}.{self._path}"

    def _q_arrays(self) -> list:
        arrays = list(self._q_mesh._q_geometry.attributes)
        if self._q_colors_only:
            arrays = [a for a in arrays if _is_color(a)]
        return arrays

    def _q_color_names(self) -> list[str]:
        return [a.name for a in self._q_mesh._q_geometry.attributes if _is_color(a)]

    def _q_items(self):
        mesh = self._q_mesh
        return [mesh._q_attribute_proxy(a) for a in self._q_arrays()]

    def _q_check_proxy(self, attribute, what="not found"):
        if not (isinstance(attribute, Attribute) and attribute._q_owner is self._q_mesh and attribute._q_alive()):
            raise PropertyValueError(f"AttributeGroupMesh: attribute {what}")
        return attribute._q_attr

    def new(self, name: str, type: str, domain: str):
        if type not in _ATTR_TYPE_ITEMS:
            raise _enum_error(type, _ATTR_TYPE_ITEMS)
        if domain not in _ATTR_DOMAIN_ITEMS:
            raise _enum_error(domain, _ATTR_DOMAIN_ITEMS)
        if type in _UNSUPPORTED_TYPES:
            raise NotImplementedInQuartz("AttributeGroupMesh.new", f"data type {type}")
        if domain in _UNSUPPORTED_DOMAINS:
            raise PropertyValueError(f"AttributeGroupMesh.new(): domain not supported: {domain}")
        if self._q_colors_only and (type not in _COLOR_TYPES or domain not in _COLOR_DOMAINS):
            raise PropertyValueError(
                f"AttributeGroupMesh.new(): {type} on {domain} is not a valid color attribute")
        if not isinstance(name, str):
            raise PropertyTypeError(f"AttributeGroupMesh.new(): name expected a string type, not {builtins_type(name).__name__}")
        mesh = self._q_mesh
        store = mesh._q_geometry.attributes
        try:
            arr = store.new(store.unique_name(name), type, domain)
        except ValueError as exc:
            raise PropertyValueError(str(exc)) from exc
        if _is_color(arr):
            layers = mesh._q_layers
            if layers["color_active"] is None:
                layers["color_active"] = arr.name
            if layers["color_render"] is None:
                layers["color_render"] = arr.name
        mesh._q_normalize_layers()
        mesh.q_tag("GEOMETRY")
        return mesh._q_attribute_proxy(arr)

    def remove(self, attribute) -> None:
        if not isinstance(attribute, Attribute):
            raise PropertyTypeError(
                f"AttributeGroupMesh.remove(): expected a Attribute type, not {builtins_type(attribute).__name__}")
        arr = self._q_check_proxy(attribute)
        if self._q_colors_only and not _is_color(arr):
            raise PropertyValueError(f"AttributeGroupMesh.remove(): attribute \"{arr.name}\" not found")
        if arr.name in REQUIRED_ATTRIBUTES:
            raise PropertyValueError(f"Attribute \"{arr.name}\" is required and can't be removed")
        mesh = self._q_mesh
        mesh._q_geometry.attributes.remove(arr.name)
        mesh._q_drop_proxies(arr.name)
        mesh._q_normalize_layers()
        mesh.q_tag("GEOMETRY")

    def domain_size(self, domain: str) -> int:
        if domain not in _ATTR_DOMAIN_ITEMS:
            raise _enum_error(domain, _ATTR_DOMAIN_ITEMS)
        if domain in _UNSUPPORTED_DOMAINS:
            return 0
        return self._q_mesh._q_geometry.domain_size(domain)

    @property
    def active(self):
        name = self._q_mesh._q_layer("attr_active")
        return None if name is None else self._q_mesh._q_attribute_proxy_by_name(name)

    @active.setter
    def active(self, value):
        mesh = self._q_mesh
        if value is None:
            mesh._q_layers["attr_active"] = None
        else:
            mesh._q_layers["attr_active"] = self._q_check_proxy(value).name
        mesh.q_tag("DATA")

    @property
    def active_color(self):
        name = self._q_mesh._q_layer("color_active")
        return None if name is None else self._q_mesh._q_attribute_proxy_by_name(name)

    @active_color.setter
    def active_color(self, value):
        mesh = self._q_mesh
        if value is None:
            mesh._q_layers["color_active"] = None
        else:
            arr = self._q_check_proxy(value)
            if not _is_color(arr):
                raise PropertyValueError(f"AttributeGroupMesh.active_color: \"{arr.name}\" is not a color attribute")
            mesh._q_layers["color_active"] = arr.name
        mesh.q_tag("DATA")

    def _q_get_active_index(self):
        name = self._q_mesh._q_layer("attr_active")
        names = [a.name for a in self._q_arrays()]
        return names.index(name) if name in names else -1

    def _q_set_active_index(self, value):
        names = [a.name for a in self._q_arrays()]
        self._q_mesh._q_layers["attr_active"] = names[value] if 0 <= value < len(names) else None

    def _q_index_of(self, key):
        name = self._q_mesh._q_layer(key)
        names = self._q_color_names()
        return names.index(name) if name in names else -1

    def _q_set_index_of(self, key, value):
        names = self._q_color_names()
        self._q_mesh._q_layers[key] = names[value] if 0 <= value < len(names) else None

    def _q_get_active_color_index(self):
        return self._q_index_of("color_active")

    def _q_set_active_color_index(self, value):
        self._q_set_index_of("color_active", value)

    def _q_get_render_color_index(self):
        return self._q_index_of("color_render")

    def _q_set_render_color_index(self, value):
        self._q_set_index_of("color_render", value)

    def _q_name_of(self, key):
        name = self._q_mesh._q_layer(key)
        return "" if name is None else name

    def _q_set_name_of(self, key, value):
        self._q_mesh._q_layers[key] = value if value in self._q_color_names() else None

    def _q_get_active_color_name(self):
        return self._q_name_of("color_active")

    def _q_set_active_color_name(self, value):
        self._q_set_name_of("color_active", value)

    def _q_get_default_color_name(self):
        return self._q_name_of("color_render")

    def _q_set_default_color_name(self, value):
        self._q_set_name_of("color_render", value)


builtins_type = type



class UVLoopLayers(PropCollection):
    def __init__(self, mesh):
        PropCollection.__init__(self, owner=mesh, path="uv_layers")
        self._q_mesh = mesh

    def _q_arrays(self) -> list:
        return [a for a in self._q_mesh._q_geometry.attributes if _is_uv(a)]

    def _q_items(self):
        mesh = self._q_mesh
        return [mesh._q_uv_proxy(a) for a in self._q_arrays()]

    def __repr__(self) -> str:
        return f"{repr(self._q_mesh)}.uv_layers"

    def _q_check_layer(self, layer):
        if not (isinstance(layer, MeshUVLoopLayer) and layer._q_owner is self._q_mesh and layer._q_alive()):
            raise PropertyValueError("UVLoopLayers: layer not found")
        return layer._q_attr

    def new(self, name: str = "UVMap", do_init: bool = True):
        if not isinstance(name, str):
            raise PropertyTypeError(f"UVLoopLayers.new(): name expected a string type, not {type(name).__name__}")
        mesh = self._q_mesh
        arrays = self._q_arrays()
        if len(arrays) >= _MAX_UV_LAYERS:
            return None
        store = mesh._q_geometry.attributes
        source = None
        active = mesh._q_layer("uv_active")
        if do_init and active is not None:
            source = store.get(active)
        try:
            arr = store.new(store.unique_name(name or "UVMap"), "FLOAT2", "CORNER")
        except ValueError as exc:
            raise PropertyValueError(str(exc)) from exc
        if source is not None:
            arr.data[...] = source.data
        mesh._q_normalize_layers()
        mesh.q_tag("GEOMETRY")
        return mesh._q_uv_proxy(arr)

    def remove(self, layer) -> None:
        if not isinstance(layer, MeshUVLoopLayer):
            raise PropertyTypeError(f"UVLoopLayers.remove(): expected a MeshUVLoopLayer type, not {type(layer).__name__}")
        arr = self._q_check_layer(layer)
        mesh = self._q_mesh
        store = mesh._q_geometry.attributes
        name = arr.name
        store.remove(name)
        mesh._q_drop_proxies(name)
        pin = ".pn." + name
        if pin in store:
            store.remove(pin)
            mesh._q_drop_proxies(pin)
        mesh._q_normalize_layers()
        mesh.q_tag("GEOMETRY")

    def _q_index(self, key) -> int:
        name = self._q_mesh._q_layer(key)
        names = [a.name for a in self._q_arrays()]
        return names.index(name) if name in names else -1

    def _q_set_index(self, key, value) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise PropertyTypeError(f"UVLoopLayers.{key} expected an int type, not {type(value).__name__}")
        names = [a.name for a in self._q_arrays()]
        if 0 <= value < len(names):
            self._q_mesh._q_layers[key] = names[value]
            self._q_mesh.q_tag("DATA")

    def _q_set_layer(self, key, layer) -> None:
        arr = self._q_check_layer(layer)
        self._q_mesh._q_layers[key] = arr.name
        self._q_mesh.q_tag("DATA")

    def _q_get_layer(self, key):
        name = self._q_mesh._q_layer(key)
        return None if name is None else self._q_mesh._q_uv_proxy(self._q_mesh._q_geometry.attributes[name])

    @property
    def active(self):
        return self._q_get_layer("uv_active")

    @active.setter
    def active(self, layer):
        self._q_set_layer("uv_active", layer)

    @property
    def active_index(self) -> int:
        return self._q_index("uv_active")

    @active_index.setter
    def active_index(self, value) -> None:
        self._q_set_index("uv_active", value)

    @property
    def active_render(self):
        return self._q_get_layer("uv_render")

    @active_render.setter
    def active_render(self, layer):
        self._q_set_layer("uv_render", layer)

    @property
    def active_render_index(self) -> int:
        return self._q_index("uv_render")

    @active_render_index.setter
    def active_render_index(self, value) -> None:
        self._q_set_index("uv_render", value)



class IDMaterials(PropCollection):
    def __init__(self, mesh):
        PropCollection.__init__(self, owner=mesh, path="materials")
        self._q_mesh = mesh

    def _q_items(self):
        return self._q_mesh._q_materials

    def __repr__(self) -> str:
        return f"{repr(self._q_mesh)}.materials"

    @staticmethod
    def _q_validate(material) -> None:
        if material is None:
            return
        if getattr(type(material), "_q_removed", False):
            raise RemovedStructError(f"StructRNA of type {type(material).__name__} has been removed")
        if not isinstance(material, Material):
            raise PropertyTypeError(f"IDMaterials: expected a Material type, not {type(material).__name__}")

    def _q_norm_index(self, index) -> int:
        if isinstance(index, bool) or not isinstance(index, (int, np.integer)):
            raise PropertyTypeError(f"IDMaterials: index expected an int type, not {type(index).__name__}")
        n = len(self._q_mesh._q_materials)
        i = int(index)
        if i < 0:
            i += n
        if i < 0 or i >= n:
            raise IndexError(f"IDMaterials: index {int(index)} out of range")
        return i

    def append(self, material) -> None:
        self._q_validate(material)
        self._q_mesh._q_materials.append(material)
        self._q_mesh.q_tag("SHADING")

    def pop(self, index: int = -1):
        mesh = self._q_mesh
        i = self._q_norm_index(index)
        material = mesh._q_materials.pop(i)
        channels = ["SHADING"]
        attr = mesh._q_geometry.attributes.get("material_index")
        if attr is not None:
            mask = attr.data > i
            if mask.any():
                attr.data[mask] -= 1
                channels.append("GEOMETRY")
        mesh.q_tag(*channels)
        return material

    def clear(self) -> None:
        mesh = self._q_mesh
        mesh._q_materials.clear()
        channels = ["SHADING"]
        if "material_index" in mesh._q_geometry.attributes:
            mesh._q_geometry.attributes.remove("material_index")
            channels.append("GEOMETRY")
        mesh.q_tag(*channels)

    def __setitem__(self, index, material) -> None:
        self._q_validate(material)
        i = self._q_norm_index(index)
        self._q_mesh._q_materials[i] = material
        self._q_mesh.q_tag("SHADING")



def _ni_property(symbol: str):
    def getter(self):
        raise NotImplementedInQuartz(symbol)
    return property(getter)


def _ni_method(symbol: str):
    def method(self, *args, **kwargs):
        raise NotImplementedInQuartz(symbol)
    method.__name__ = symbol.rsplit(".", 1)[-1]
    return method


@builtin_struct
class Mesh(ID):
    normals_domain: EnumProperty(items=_items('POINT', 'FACE', 'CORNER'), default='FACE', meta={"virtual_get": lambda s: s._q_get_normals_domain()})
    uv_layer_clone_index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, options=set())
    uv_layer_stencil_index: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, options=set())
    remesh_voxel_size: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.1, min=0.0, soft_min=0.0001, step=0.01, precision=4, options=set())
    remesh_voxel_adaptivity: FloatProperty(subtype='DISTANCE', unit='LENGTH', min=0.0, max=1.0, step=0.01, precision=4, options=set())
    use_remesh_fix_poles: BoolProperty(options=set())
    use_remesh_preserve_volume: BoolProperty(options=set())
    use_remesh_preserve_attributes: BoolProperty(options=set())
    remesh_mode: EnumProperty(items=_items('VOXEL', 'QUAD'), default='VOXEL', options=set())
    use_mirror_x: BoolProperty(options=set())
    use_mirror_y: BoolProperty(options=set())
    use_mirror_z: BoolProperty(options=set())
    use_mirror_vertex_groups: BoolProperty(default=True, options=set())
    radial_symmetry: IntVectorProperty(subtype='XYZ', size=3, default=(1, 1, 1), min=1, max=64, soft_max=32, options=set())
    has_custom_normals: BoolProperty(meta={"virtual_get": lambda s: s._q_get_has_custom_normals()})
    use_auto_texspace: BoolProperty(default=True)
    use_mirror_topology: BoolProperty(options=set())
    use_paint_bone_selection: BoolProperty(default=True, options=set())
    use_paint_mask: BoolProperty(options=set())
    use_paint_mask_vertex: BoolProperty(options=set())
    total_vert_sel: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get_total_vert_sel()})
    total_edge_sel: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get_total_edge_sel()})
    total_face_sel: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get_total_face_sel()})
    is_editmode: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_editmode()})
    auto_texspace: BoolProperty(default=True)
    texspace_location: FloatVectorProperty(subtype='TRANSLATION', unit='LENGTH', size=3, soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3)
    texspace_size: FloatVectorProperty(subtype='XYZ', size=3, default=(1.0, 1.0, 1.0), soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3)

    q_schema_version: ClassVar[int] = 1

    @classmethod
    def _q_construct(cls, name):
        self = super()._q_construct(name)
        self._q_geometry = MeshGeometry()
        self._q_materials = []
        self._q_layers = {"uv_active": None, "uv_render": None, "attr_active": None,
                          "color_active": None, "color_render": None}
        self._q_editmode = False
        self._q_edit_data = None
        self._q_poly_active = 0
        self._q_cache = {}
        self._q_cache_stamp = None
        self._q_colls = {}
        self._q_attr_proxies = {}
        self._q_uv_proxies = {}
        return self

    def _q_clear_caches(self) -> None:
        self._q_cache = {}
        self._q_cache_stamp = None

    def _q_cached(self, key, fn):
        stamp = self.q_dirty["GEOMETRY"]
        if stamp != self._q_cache_stamp:
            self._q_cache = {}
            self._q_cache_stamp = stamp
        cache = self._q_cache
        if key not in cache:
            cache[key] = fn()
        return cache[key]

    def _q_domain_len(self, domain: str) -> int:
        if domain == "TRI":
            return int(self._q_tris_data()["polygon_index"].shape[0])
        return self._q_geometry.domain_size(domain)

    def _q_after_structure(self) -> None:
        self._q_clear_caches()
        self.q_tag("GEOMETRY")

    def _q_tris_data(self) -> dict:
        return self._q_cached("tris", self._q_compute_tris)

    def _q_compute_tris(self) -> dict:
        geo = self._q_geometry
        tris, tri_face = triangulate(geo)
        tris = np.asarray(tris, dtype=np.int32).reshape(-1, 3)
        tri_face = np.asarray(tri_face, dtype=np.int32).reshape(-1)
        verts = geo.corner_verts[tris] if tris.size else np.zeros((0, 3), np.int32)
        pts = geo.positions.astype(np.float64)[verts] if tris.size else np.zeros((0, 3, 3))
        cross = np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]) if tris.size else np.zeros((0, 3))
        length = np.linalg.norm(cross, axis=1) if tris.size else np.zeros(0)
        safe = np.where(length > 0.0, length, 1.0)
        normal = np.where(length[:, None] > 0.0, cross / safe[:, None], 0.0)
        cn = self._q_cached("corner_normals", lambda: _corner_normals(self))
        split = cn[tris].reshape(-1, 3, 3) if tris.size else np.zeros((0, 3, 3), np.float32)
        mat = geo.attributes.get("material_index")
        sharp = geo.attributes.get("sharp_face")
        return {
            "vertices": verts.astype(np.int32),
            "loops": tris,
            "polygon_index": tri_face,
            "normal": normal.astype(np.float32),
            "split_normals": split.astype(np.float32),
            "area": (0.5 * length).astype(np.float32),
            "material_index": (mat.data[tri_face] if mat is not None else np.zeros(len(tri_face))).astype(np.int32),
            "use_smooth": (~sharp.data[tri_face] if sharp is not None else np.ones(len(tri_face), bool)).astype(bool),
        }

    def _q_layer(self, key):
        self._q_normalize_layers()
        return self._q_layers[key]

    def _q_normalize_layers(self) -> None:
        store = self._q_geometry.attributes
        layers = self._q_layers
        for key in ("uv_active", "uv_render"):
            name = layers[key]
            if name is not None and not _is_uv(store.get(name)):
                layers[key] = None
        for key in ("color_active", "color_render"):
            name = layers[key]
            if name is not None and not _is_color(store.get(name)):
                layers[key] = None
        if layers["attr_active"] is not None and layers["attr_active"] not in store:
            layers["attr_active"] = None
        uvs = [a.name for a in store if _is_uv(a)]
        if uvs:
            for key in ("uv_active", "uv_render"):
                if layers[key] is None:
                    layers[key] = uvs[0]

    def _q_attribute_proxy(self, arr):
        cache = self._q_attr_proxies
        proxy = cache.get(arr.name)
        if proxy is None or not proxy._q_alive() or proxy._q_attr is not arr:
            proxy = _new_layer_proxy(Attribute, self, arr, _attr_path(arr.name))
            cache[arr.name] = proxy
        return proxy

    def _q_attribute_proxy_by_name(self, name):
        arr = self._q_geometry.attributes.get(name)
        return None if arr is None else self._q_attribute_proxy(arr)

    def _q_uv_proxy(self, arr):
        cache = self._q_uv_proxies
        proxy = cache.get(arr.name)
        if proxy is None or not proxy._q_alive() or proxy._q_attr is not arr:
            proxy = _new_layer_proxy(MeshUVLoopLayer, self, arr, _uv_path(arr.name))
            cache[arr.name] = proxy
        return proxy

    def _q_drop_proxies(self, name: str) -> None:
        self._q_attr_proxies.pop(name, None)
        self._q_uv_proxies.pop(name, None)

    def _q_rename_attribute(self, arr, value: str) -> None:
        if arr.is_required:
            raise PropertyValueError(f"Attribute \"{arr.name}\" is required and can't be renamed")
        old = arr.name
        if value == old:
            return
        store = self._q_geometry.attributes
        new = store.unique_name(value) if value else value
        try:
            store.rename(old, new)
        except ValueError as exc:
            raise PropertyValueError(str(exc)) from exc
        for cache, path in ((self._q_attr_proxies, _attr_path), (self._q_uv_proxies, _uv_path)):
            proxy = cache.pop(old, None)
            if proxy is not None:
                proxy._q_set_owner(self, path(new))
                cache[new] = proxy
        for key, value_name in self._q_layers.items():
            if value_name == old:
                self._q_layers[key] = new
        old_pin = ".pn." + old
        if _is_uv(arr) and old_pin in store:
            new_pin = store.unique_name(".pn." + new)
            store.rename(old_pin, new_pin)
            proxy = self._q_attr_proxies.pop(old_pin, None)
            if proxy is not None:
                proxy._q_set_owner(self, _attr_path(new_pin))
                self._q_attr_proxies[new_pin] = proxy
        self._q_normalize_layers()

    def _q_element_collection(self, name):
        coll = self._q_colls.get(name)
        if coll is None:
            if name in _ELEMENT_COLLECTIONS:
                coll_cls, item_cls, table = _ELEMENT_COLLECTIONS[name]
                coll = coll_cls(self, name, item_cls, table)
            else:
                domain, item_cls, table = _DERIVED_COLLECTIONS[name]
                coll = _ProxyCollection(self, self, name, item_cls, table, lambda: self._q_domain_len(domain))
            self._q_colls[name] = coll
        return coll

    def _q_get_normals_domain(self) -> str:
        geo = self._q_geometry
        if geo.num_faces == 0:
            return "POINT"
        sharp = geo.attributes.get("sharp_face")
        flat = sharp.data if sharp is not None else np.zeros(geo.num_faces, bool)
        if bool(np.all(flat)):
            return "FACE"
        sharp_edge = geo.attributes.get("sharp_edge")
        any_sharp_edge = sharp_edge is not None and bool(np.any(sharp_edge.data))
        if not bool(np.any(flat)) and not any_sharp_edge:
            return "POINT"
        return "CORNER"

    def _q_get_has_custom_normals(self) -> bool:
        return False

    def _q_count(self, name: str) -> int:
        a = self._q_geometry.attributes.get(name)
        return 0 if a is None else int(np.count_nonzero(a.data))

    def _q_get_total_vert_sel(self) -> int:
        return self._q_count(".select_vert")

    def _q_get_total_edge_sel(self) -> int:
        return self._q_count(".select_edge")

    def _q_get_total_face_sel(self) -> int:
        return self._q_count(".select_poly")

    def _q_get_is_editmode(self) -> bool:
        return bool(self._q_editmode)

    vertices = property(lambda self: self._q_element_collection("vertices"))
    edges = property(lambda self: self._q_element_collection("edges"))
    loops = property(lambda self: self._q_element_collection("loops"))
    polygons = property(lambda self: self._q_element_collection("polygons"))
    loop_triangles = property(lambda self: self._q_element_collection("loop_triangles"))
    loop_triangle_polygons = property(lambda self: self._q_element_collection("loop_triangle_polygons"))
    vertex_normals = property(lambda self: self._q_element_collection("vertex_normals"))
    polygon_normals = property(lambda self: self._q_element_collection("polygon_normals"))
    corner_normals = property(lambda self: self._q_element_collection("corner_normals"))

    @property
    def attributes(self):
        coll = self._q_colls.get("attributes")
        if coll is None:
            coll = self._q_colls["attributes"] = AttributeGroupMesh(self, colors_only=False)
        return coll

    @property
    def color_attributes(self):
        coll = self._q_colls.get("color_attributes")
        if coll is None:
            coll = self._q_colls["color_attributes"] = AttributeGroupMesh(self, colors_only=True)
        return coll

    @property
    def uv_layers(self):
        coll = self._q_colls.get("uv_layers")
        if coll is None:
            coll = self._q_colls["uv_layers"] = UVLoopLayers(self)
        return coll

    @property
    def materials(self):
        coll = self._q_colls.get("materials")
        if coll is None:
            coll = self._q_colls["materials"] = IDMaterials(self)
        return coll

    shape_keys = property(lambda self: None)
    animation_data = property(lambda self: None)
    vertex_colors = _ni_property("Mesh.vertex_colors")
    skin_vertices = _ni_property("Mesh.skin_vertices")
    vertex_creases = _ni_property("Mesh.vertex_creases")
    edge_creases = _ni_property("Mesh.edge_creases")
    vertex_paint_mask = _ni_property("Mesh.vertex_paint_mask")
    vertex_creases_ensure = _ni_method("Mesh.vertex_creases_ensure")
    vertex_creases_remove = _ni_method("Mesh.vertex_creases_remove")
    edge_creases_ensure = _ni_method("Mesh.edge_creases_ensure")
    edge_creases_remove = _ni_method("Mesh.edge_creases_remove")
    vertex_paint_mask_ensure = _ni_method("Mesh.vertex_paint_mask_ensure")
    vertex_paint_mask_remove = _ni_method("Mesh.vertex_paint_mask_remove")
    calc_tangents = _ni_method("Mesh.calc_tangents")
    calc_smooth_groups = _ni_method("Mesh.calc_smooth_groups")
    normals_split_custom_set = _ni_method("Mesh.normals_split_custom_set")
    normals_split_custom_set_from_vertices = _ni_method("Mesh.normals_split_custom_set_from_vertices")
    unit_test_compare = _ni_method("Mesh.unit_test_compare")

    @property
    def edge_keys(self) -> list:
        return [(int(a), int(b)) for a, b in _edge_keys(self._q_geometry.edges)]

    def from_pydata(self, vertices, edges, faces, shade_flat: bool = True) -> None:
        try:
            geo = MeshGeometry.from_pydata(vertices, edges, faces, shade_flat=bool(shade_flat))
        except ValueError as exc:
            raise PropertyValueError(str(exc)) from exc
        self._q_geometry = geo
        self._q_clear_caches()
        self._q_normalize_layers()
        self.q_tag("GEOMETRY")

    def update(self, calc_edges: bool = False, calc_edges_loose: bool = False) -> None:
        geo = self._q_geometry
        if calc_edges or (geo.num_faces > 0 and geo.num_edges == 0):
            _calc_edges(geo, keep_existing=True)
        self._q_after_structure()

    def validate(self, verbose: bool = False, clean_customdata: bool = True) -> bool:
        changed, problems = self._q_geometry.validate(fix=True)
        if verbose:
            for problem in problems:
                sys.stdout.write(f"{problem}\n")
        if changed:
            self._q_after_structure()
        return bool(changed)

    def validate_material_indices(self) -> bool:
        attr = self._q_geometry.attributes.get("material_index")
        if attr is None:
            return False
        limit = max(len(self._q_materials), 1)
        mask = (attr.data >= limit) | (attr.data < 0)
        if not mask.any():
            return False
        attr.data[mask] = 0
        self.q_tag("GEOMETRY")
        return True

    def clear_geometry(self) -> None:
        self._q_geometry = MeshGeometry()
        for key in self._q_layers:
            self._q_layers[key] = None
        self._q_after_structure()

    def transform(self, matrix, shape_keys: bool = False) -> None:
        try:
            m = np.array(matrix, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise PropertyValueError("Mesh.transform(): matrix expected a 4x4 matrix") from exc
        if m.shape == (16,):
            m = m.reshape(4, 4)
        if m.shape != (4, 4):
            raise PropertyValueError("Mesh.transform(): matrix expected a 4x4 matrix")
        geo = self._q_geometry
        if geo.num_verts:
            geo.positions[...] = transform_points(geo.positions.astype(np.float64), m).astype(np.float32)
        self.q_tag("GEOMETRY")

    def flip_normals(self) -> None:
        flip_faces(self._q_geometry)
        self.q_tag("GEOMETRY")

    def shade_flat(self) -> None:
        store = self._q_geometry.attributes
        attr = store.get("sharp_face")
        if attr is None:
            attr = store.new("sharp_face", "BOOLEAN", "FACE")
        attr.data[...] = True
        self.q_tag("GEOMETRY")

    def shade_smooth(self) -> None:
        store = self._q_geometry.attributes
        for name in ("sharp_face", "sharp_edge"):
            if name in store:
                store.remove(name)
                self._q_drop_proxies(name)
        self.q_tag("GEOMETRY")

    def set_sharp_from_angle(self, angle: float = 0.523599) -> None:
        if isinstance(angle, bool) or not isinstance(angle, (int, float, np.number)):
            raise PropertyTypeError(f"Mesh.set_sharp_from_angle(): angle expected a float type, not {type(angle).__name__}")
        geo = self._q_geometry
        store = geo.attributes
        if "sharp_edge" in store:
            store.remove("sharp_edge")
            self._q_drop_proxies("sharp_edge")
        sharp = store.new("sharp_edge", "BOOLEAN", "EDGE")
        if geo.num_corners and geo.num_edges:
            normals = face_normals(geo).astype(np.float64)
            faces_of = defaultdict(list)
            for corner, (edge, face) in enumerate(zip(geo.corner_edges.tolist(), geo.corner_to_face().tolist())):
                faces_of[edge].append(face)
            limit = float(angle)
            for edge, faces in faces_of.items():
                if len(faces) == 2:
                    dot = float(np.clip(np.dot(normals[faces[0]], normals[faces[1]]), -1.0, 1.0))
                    sharp.data[edge] = bool(np.arccos(dot) > limit)
        self.q_tag("GEOMETRY")

    def calc_loop_triangles(self) -> None:
        self._q_cache.pop("tris", None)
        self._q_tris_data()

    def split_faces(self) -> None:
        geo = self._q_geometry
        num_corners = geo.num_corners
        if num_corners == 0:
            self.q_tag("GEOMETRY")
            return
        store = geo.attributes
        corner_verts = geo.corner_verts.copy()
        corner_edges = geo.corner_edges.copy()
        corner_face = geo.corner_to_face()
        offsets = geo.face_offsets
        sharp_face_attr = store.get("sharp_face")
        smooth = (~sharp_face_attr.data) if sharp_face_attr is not None else np.ones(geo.num_faces, bool)
        sharp_edge_attr = store.get("sharp_edge")
        sharp_edge = sharp_edge_attr.data.copy() if sharp_edge_attr is not None else np.zeros(geo.num_edges, bool)

        parent = list(range(num_corners))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        incident = defaultdict(list)
        for face in range(geo.num_faces):
            start, end = int(offsets[face]), int(offsets[face + 1])
            size = end - start
            for k in range(start, end):
                prev = start + (k - start - 1) % size
                v = int(corner_verts[k])
                incident[(int(corner_edges[k]), v)].append(k)
                incident[(int(corner_edges[prev]), v)].append(k)
        for (edge, _v), corners in incident.items():
            if edge < len(sharp_edge) and sharp_edge[edge]:
                continue
            keep = [c for c in corners if smooth[corner_face[c]]]
            for c in keep[1:]:
                ra, rb = find(keep[0]), find(c)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)

        groups_by_vert = defaultdict(dict)
        for c in range(num_corners):
            groups_by_vert[int(corner_verts[c])].setdefault(find(c), []).append(c)
        num_verts = geo.num_verts
        sources = []
        new_corner_verts = corner_verts.copy()
        for v in sorted(groups_by_vert):
            groups = sorted(groups_by_vert[v].values(), key=min)
            for group in groups[1:]:
                new_index = num_verts + len(sources)
                sources.append(v)
                new_corner_verts[group] = new_index
        orig_of = np.concatenate([np.arange(num_verts), np.asarray(sources, dtype=np.int64)]).astype(np.int64)

        old_edges = geo.edges.copy()
        old_keys = {}
        for index, (a, b) in enumerate(old_edges.tolist()):
            old_keys.setdefault((a, b) if a <= b else (b, a), index)
        old_edge_attrs = [(a.name, a.data.copy()) for a in store.by_domain("EDGE") if a.name != ".edge_verts"]
        used = np.zeros(len(old_edges), dtype=bool)
        if len(old_edges):
            used[corner_edges] = True
        loose = old_edges[~used] if len(old_edges) else old_edges

        if sources:
            geo.resize_domain("POINT", num_verts + len(sources))
            src = np.asarray(sources, dtype=np.int64)
            for attr in store.by_domain("POINT"):
                attr.data[num_verts:] = attr.data[src]
        geo.corner_verts[...] = new_corner_verts
        geo.resize_domain("EDGE", len(loose))
        if len(loose):
            geo.edges[...] = loose
        _calc_edges(geo, keep_existing=True)
        new_edges = geo.edges
        remap = np.full(len(new_edges), -1, dtype=np.int64)
        for index, (a, b) in enumerate(new_edges.tolist()):
            oa, ob = int(orig_of[a]), int(orig_of[b])
            remap[index] = old_keys.get((oa, ob) if oa <= ob else (ob, oa), -1)
        for name, data in old_edge_attrs:
            attr = store.get(name)
            if attr is None:
                continue
            fill = _default_array(attr.data_type, len(new_edges))
            hit = remap >= 0
            if hit.any():
                fill[hit] = data[remap[hit]]
            attr.data[...] = fill
        self._q_after_structure()

    def count_selected_items(self) -> tuple:
        return (self._q_count(".select_vert"), self._q_count(".select_edge"), self._q_count(".select_poly"))

    def update_gpu_tag(self) -> None:
        return None

    def free_tangents(self) -> None:
        return None

    @property
    def q_geometry(self) -> MeshGeometry:
        return self._q_geometry

    def q_set_geometry(self, geo) -> None:
        if not isinstance(geo, MeshGeometry):
            raise PropertyTypeError(f"Mesh.q_set_geometry(): expected a MeshGeometry, not {type(geo).__name__}")
        self._q_geometry = geo
        self._q_normalize_layers()
        self._q_after_structure()

    def q_tag_geometry(self) -> None:
        self.q_tag("GEOMETRY")

    def q_bounds(self):
        positions = self._q_geometry.positions
        if positions.shape[0] == 0:
            return np.zeros(3, dtype=np.float64), np.zeros(3, dtype=np.float64)
        lo, hi = bounds(positions.astype(np.float64))
        return np.asarray(lo, dtype=np.float64), np.asarray(hi, dtype=np.float64)

    @property
    def q_edit_data(self):
        return self._q_edit_data

    @q_edit_data.setter
    def q_edit_data(self, value) -> None:
        self._q_edit_data = value

    def q_set_editmode(self, state: bool) -> None:
        state = bool(state)
        if state == bool(self._q_editmode):
            return
        if state:
            self._q_editmode = True
            try:
                _EDIT_HOOKS["enter"](self)
            except BaseException:
                self._q_editmode = False
                raise
            return
        if self._q_edit_data is not None:
            _EDIT_HOOKS["flush"](self)
        self._q_edit_data = None
        self._q_editmode = False
        self.q_tag("GEOMETRY")

    def q_flush_edit(self) -> bool:
        if self._q_editmode and self._q_edit_data is not None:
            _EDIT_HOOKS["flush"](self)
            self.q_tag("GEOMETRY")
            return True
        return False

    def _q_slot_set(self, index: int, material) -> None:
        if 0 <= index < len(self._q_materials):
            self._q_materials[index] = material
            self.q_tag("SHADING")

    def _q_refs(self):
        yield from super()._q_refs()
        for index, material in enumerate(list(self._q_materials)):
            if material is None:
                continue
            yield IDRef(material, self, "MATERIAL", True, "CLEAR",
                        lambda i=index: self._q_slot_set(i, None),
                        lambda new, i=index: self._q_slot_set(i, new))

    def _q_copy_into(self, new) -> None:
        super()._q_copy_into(new)
        new._q_geometry = self._q_geometry.copy()
        new._q_materials = list(self._q_materials)
        new._q_layers = dict(self._q_layers)
        new._q_editmode = False
        new._q_edit_data = None
        new._q_clear_caches()

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        geo = self._q_geometry
        state["mesh_geometry"] = {
            "face_offsets": geo.face_offsets.copy(),
            "attributes": [
                {"name": a.name, "domain": a.domain, "data_type": a.data_type, "data": a.data.copy()}
                for a in geo.attributes
            ],
        }
        state["mesh_materials"] = list(self._q_materials)
        state["mesh_layers"] = dict(self._q_layers)
        state["mesh_editmode"] = bool(self._q_editmode)
        return state

    def _q_state_set(self, state: dict) -> None:
        super()._q_state_set(state)
        geo_state = state.get("mesh_geometry")
        if geo_state is not None:
            geo = MeshGeometry()
            geo.face_offsets = np.array(geo_state["face_offsets"], dtype=np.int32, copy=True)
            entries = list(geo_state.get("attributes", ()))
            for entry in entries:
                if entry["name"] in REQUIRED_ATTRIBUTES:
                    geo.attributes[entry["name"]].data = np.array(
                        entry["data"], dtype=DATA_TYPES[entry["data_type"]][0], copy=True)
            for entry in entries:
                if entry["name"] in REQUIRED_ATTRIBUTES:
                    continue
                arr = geo.attributes.new(entry["name"], entry["data_type"], entry["domain"])
                arr.data = np.array(entry["data"], dtype=DATA_TYPES[entry["data_type"]][0], copy=True)
            self._q_geometry = geo
        if "mesh_materials" in state:
            self._q_materials = list(state["mesh_materials"])
        if "mesh_layers" in state:
            layers = {"uv_active": None, "uv_render": None, "attr_active": None,
                      "color_active": None, "color_render": None}
            layers.update(state["mesh_layers"])
            self._q_layers = layers
        if "mesh_editmode" in state:
            self._q_editmode = bool(state["mesh_editmode"])
        self._q_edit_data = None
        self._q_attr_proxies = {}
        self._q_uv_proxies = {}
        self._q_clear_caches()
        self._q_normalize_layers()


class BlendDataMeshes(IDCollection):
    def new(self, name: str) -> Mesh:
        return IDCollection.new(self, name)

    def new_from_object(self, object, preserve_all_data_layers: bool = False, depsgraph: object = None) -> Mesh:
        data = getattr(object, "data", None)
        if not isinstance(data, Mesh):
            name = getattr(object, "name", "?")
            raise PropertyValueError(f"Object '{name}' does not have geometry data")
        if getattr(object, "mode", "OBJECT") == "EDIT":
            data.q_flush_edit()
        mesh = self.new(object.name)
        mesh._q_geometry = data._q_geometry.copy()
        mesh._q_materials = list(data._q_materials)
        mesh._q_layers = dict(data._q_layers)
        mesh._q_clear_caches()
        mesh._q_normalize_layers()
        return mesh

    def remove(self, mesh: Mesh, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None:
        IDCollection.remove(self, mesh, do_unlink, do_id_user, do_ui_user)


register_id_type(Mesh, id_type="MESH", collection="meshes", default_name="Mesh", collection_cls=BlendDataMeshes)
register_object_data_type(Mesh, "MESH")
