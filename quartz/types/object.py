import math as _math

import numpy as np

from quartz.errors import (LinkError, NotImplementedInQuartz, PropertyTypeError, PropertyValueError,
                           RegistrationError)
from quartz.geometry import bound_box as _geo_bound_box
from quartz.geometry import triangulate as _geo_triangulate
from quartz.math import Euler, Matrix, Quaternion, Vector
from quartz.math.bvhtree import BVHTree
from quartz.math.euler import EULER_ORDERS
from quartz.props import (BoolProperty, BoolVectorProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                          IntProperty, PointerProperty, StringProperty)
from quartz.rna import PropCollection, Struct, builtin_struct, get_property, hooks
from quartz.rna.datapath import escape_identifier
from quartz.types.blenddata import IDCollection
from quartz.types.collection import Collection
from quartz.types.id import DIRTY_CHANNELS, ID, _q_relabel_refs, register_id_type
from quartz.types.naming import unique_name

__all__ = [
    "OBJECT_TYPES", "OBJECT_MODES", "EULER_ORDERS", "MODIFIER_TYPES",
    "register_object_data_type", "object_type_for", "object_modes_for", "context_mode_for",
    "Object", "ObjectModifiers", "Modifier", "ObjectConstraints", "VertexGroups", "VertexGroup", "MaterialSlot",
    "BlendDataObjects",
]

OBJECT_TYPES: tuple[str, ...] = (
    "MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME", "GREASEPENCIL", "ARMATURE",
    "LATTICE", "EMPTY", "LIGHT", "LIGHT_PROBE", "CAMERA", "SPEAKER",
)
OBJECT_MODES: tuple[str, ...] = (
    "OBJECT", "EDIT", "POSE", "SCULPT", "VERTEX_PAINT", "WEIGHT_PAINT", "TEXTURE_PAINT", "PARTICLE_EDIT",
    "EDIT_GPENCIL", "SCULPT_GREASE_PENCIL", "PAINT_GREASE_PENCIL", "WEIGHT_GREASE_PENCIL", "VERTEX_GREASE_PENCIL",
    "SCULPT_CURVES",
)
MODIFIER_TYPES: tuple[str, ...] = (
    "GREASE_PENCIL_VERTEX_WEIGHT_PROXIMITY", "DATA_TRANSFER", "MESH_CACHE", "MESH_SEQUENCE_CACHE", "NORMAL_EDIT",
    "WEIGHTED_NORMAL", "UV_PROJECT", "UV_WARP", "VERTEX_WEIGHT_EDIT", "VERTEX_WEIGHT_MIX",
    "VERTEX_WEIGHT_PROXIMITY", "GREASE_PENCIL_COLOR", "GREASE_PENCIL_TINT", "GREASE_PENCIL_OPACITY",
    "GREASE_PENCIL_VERTEX_WEIGHT_ANGLE", "GREASE_PENCIL_TIME", "GREASE_PENCIL_TEXTURE", "ARRAY", "BEVEL", "BOOLEAN",
    "BUILD", "DECIMATE", "EDGE_SPLIT", "NODES", "MASK", "MIRROR", "MESH_TO_VOLUME", "MULTIRES", "REMESH", "SCREW",
    "SKIN", "SOLIDIFY", "SUBSURF", "TRIANGULATE", "VOLUME_TO_MESH", "WELD", "WIREFRAME", "GREASE_PENCIL_ARRAY",
    "GREASE_PENCIL_BUILD", "GREASE_PENCIL_LENGTH", "LINEART", "GREASE_PENCIL_MIRROR", "GREASE_PENCIL_MULTIPLY",
    "GREASE_PENCIL_SIMPLIFY", "GREASE_PENCIL_SUBDIV", "GREASE_PENCIL_ENVELOPE", "GREASE_PENCIL_OUTLINE", "ARMATURE",
    "CAST", "CURVE", "DISPLACE", "HOOK", "LAPLACIANDEFORM", "LATTICE", "MESH_DEFORM", "SHRINKWRAP", "SIMPLE_DEFORM",
    "SMOOTH", "CORRECTIVE_SMOOTH", "LAPLACIANSMOOTH", "SURFACE_DEFORM", "WARP", "WAVE", "VOLUME_DISPLACE",
    "GREASE_PENCIL_HOOK", "GREASE_PENCIL_NOISE", "GREASE_PENCIL_OFFSET", "GREASE_PENCIL_SMOOTH",
    "GREASE_PENCIL_THICKNESS", "GREASE_PENCIL_LATTICE", "GREASE_PENCIL_DASH", "GREASE_PENCIL_ARMATURE",
    "GREASE_PENCIL_SHRINKWRAP", "CLOTH", "COLLISION", "DYNAMIC_PAINT", "EXPLODE", "FLUID", "OCEAN",
    "PARTICLE_INSTANCE", "PARTICLE_SYSTEM", "SOFT_BODY", "SURFACE",
)

_ROTATION_MODES = ("QUATERNION", "XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX", "AXIS_ANGLE")
_MODES_BY_TYPE = {
    "MESH": ("OBJECT", "EDIT", "SCULPT", "VERTEX_PAINT", "WEIGHT_PAINT", "TEXTURE_PAINT"),
    "CURVE": ("OBJECT", "EDIT"), "SURFACE": ("OBJECT", "EDIT"), "FONT": ("OBJECT", "EDIT"),
    "META": ("OBJECT", "EDIT"), "LATTICE": ("OBJECT", "EDIT"),
    "ARMATURE": ("OBJECT", "EDIT", "POSE"),
}
_EDIT_CONTEXT = {
    "MESH": "EDIT_MESH", "CURVE": "EDIT_CURVE", "SURFACE": "EDIT_SURFACE", "FONT": "EDIT_TEXT",
    "META": "EDIT_METABALL", "LATTICE": "EDIT_LATTICE", "ARMATURE": "EDIT_ARMATURE", "CURVES": "EDIT_CURVES",
    "POINTCLOUD": "EDIT_POINTCLOUD", "GREASEPENCIL": "EDIT_GREASE_PENCIL",
}
_MODE_CONTEXT = {"POSE": "POSE", "SCULPT": "SCULPT", "VERTEX_PAINT": "PAINT_VERTEX",
                 "WEIGHT_PAINT": "PAINT_WEIGHT", "TEXTURE_PAINT": "PAINT_TEXTURE", "PARTICLE_EDIT": "PARTICLE"}
_SPACES = ("WORLD", "POSE", "LOCAL_WITH_PARENT", "LOCAL")
_VG_ADD_TYPES = ("REPLACE", "ADD", "SUBTRACT")
_MATERIAL_SLOT_LINKS = ("OBJECT", "DATA")
_FMAX = 3.4028234663852886e38


def _enum_listing(items) -> str:
    return ", ".join(repr(i) for i in items)


_DATA_TYPES: list[tuple[type, str]] = []


def register_object_data_type(cls: type, object_type: str) -> None:
    if object_type not in OBJECT_TYPES or object_type == "EMPTY":
        raise RegistrationError(f"register_object_data_type: invalid object type '{object_type}'")
    for klass, t in _DATA_TYPES:
        if klass is cls and t == object_type:
            return
        if klass is cls or t == object_type:
            raise RegistrationError(f"register_object_data_type: '{object_type}' / {cls.__name__} "
                                    f"already registered ({klass.__name__} -> '{t}')")
    _DATA_TYPES.append((cls, object_type))


def object_type_for(data) -> str:
    if data is None:
        return "EMPTY"
    klass = type(data)
    if getattr(klass, "_q_removed", False):
        klass = klass._q_live_class
    for base in klass.__mro__:
        for cls, t in _DATA_TYPES:
            if cls is base:
                return t
    raise PropertyTypeError(f"ID '{getattr(data, '_q_name', data)}' of type {klass.__name__} "
                            f"can not be used as object data")


def object_modes_for(ob) -> tuple:
    return _MODES_BY_TYPE.get(ob.type, ("OBJECT",))


def context_mode_for(ob) -> str:
    if ob is None:
        return "OBJECT"
    mode = ob.mode
    if mode == "OBJECT":
        return "OBJECT"
    if mode == "EDIT":
        return _EDIT_CONTEXT.get(ob.type, "EDIT")
    return _MODE_CONTEXT.get(mode, mode)


def _q_registry_snapshot() -> object:
    return list(_DATA_TYPES)


def _q_registry_restore(snap: object) -> None:
    _DATA_TYPES[:] = list(snap)


def _raw(st, ident):
    return get_property(st, ident).read_raw(st)


def _raw64(ob, ident) -> np.ndarray:
    return np.asarray(_raw(ob, ident), dtype=np.float64)


def _write_component(inst, ident, values) -> None:
    arr = np.asarray(values, dtype=np.float32)
    cur = inst._p.get(ident)
    if isinstance(cur, np.ndarray) and cur.shape == arr.shape:
        np.copyto(cur, arr)
    else:
        inst._p[ident] = arr.copy()
    inst._p_set.add(ident)


def _m3(m) -> np.ndarray:
    return np.array(m, dtype=np.float64)


def _euler_m3(angles, order) -> np.ndarray:
    return _m3(Euler(np.asarray(angles, dtype=np.float64).tolist(), order).to_matrix())


def _quat_m3(q) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    n = float(np.linalg.norm(q))
    if n == 0.0:
        return np.eye(3)
    return _m3(Quaternion((q / n).tolist()).to_matrix())


def _axis_angle_m3(aa) -> np.ndarray:
    aa = np.asarray(aa, dtype=np.float64)
    axis = aa[1:4]
    if float(np.linalg.norm(axis)) == 0.0:
        return np.eye(3)
    return _m3(Quaternion(axis.tolist(), float(aa[0])).to_matrix())


def _inv(m: np.ndarray) -> np.ndarray:
    try:
        if abs(float(np.linalg.det(m))) < 1e-12:
            raise np.linalg.LinAlgError
        return np.linalg.inv(m)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(m)


def _rotation_m3(ob) -> np.ndarray:
    mode = _raw(ob, "rotation_mode")
    if mode in EULER_ORDERS:
        return _euler_m3(_raw(ob, "delta_rotation_euler"), mode) @ _euler_m3(_raw(ob, "rotation_euler"), mode)
    if mode == "QUATERNION":
        q = np.asarray(_raw(ob, "rotation_quaternion"), dtype=np.float64)
        n = float(np.linalg.norm(q))
        if n == 0.0:
            return np.eye(3)
        total = Quaternion(np.asarray(_raw(ob, "delta_rotation_quaternion"), dtype=np.float64).tolist()) @             Quaternion((q / n).tolist())
        return _quat_m3(np.array(total, dtype=np.float64))
    return _euler_m3(_raw(ob, "delta_rotation_euler"), "XYZ") @ _axis_angle_m3(_raw(ob, "rotation_axis_angle"))


def _rotation_only(st) -> np.ndarray:
    mode = _raw(st, "rotation_mode")
    if mode in EULER_ORDERS:
        return _euler_m3(_raw(st, "rotation_euler"), mode)
    if mode == "QUATERNION":
        return _quat_m3(_raw(st, "rotation_quaternion"))
    return _axis_angle_m3(_raw(st, "rotation_axis_angle"))


def _compose(t, r3, s) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = r3 @ np.diag(np.asarray(s, dtype=np.float64))
    m[:3, 3] = t
    return m


def _basis64(ob) -> np.ndarray:
    t = _raw64(ob, "location") + _raw64(ob, "delta_location")
    s = _raw64(ob, "scale") * _raw64(ob, "delta_scale")
    return _compose(t, _rotation_m3(ob), s)


def _local64(ob) -> np.ndarray:
    return _raw64(ob, "matrix_parent_inverse") @ _basis64(ob)


def _world64(ob, _seen=None) -> np.ndarray:
    parent = ob._p.get("parent")
    local = _local64(ob)
    if parent is None:
        return local
    seen = _seen or set()
    if id(ob) in seen:
        return local
    seen.add(id(ob))
    return _world64(parent, seen) @ local


def _decompose_rotation_into(st, r_total: np.ndarray, *, with_delta: bool) -> None:
    mode = _raw(st, "rotation_mode")
    if mode in EULER_ORDERS:
        r = r_total
        if with_delta:
            r = _euler_m3(_raw(st, "delta_rotation_euler"), mode).T @ r_total
        compat = Euler(np.asarray(_raw(st, "rotation_euler"), dtype=np.float64).tolist(), mode)
        e = Matrix(r.tolist()).to_euler(mode, compat)
        _write_component(st, "rotation_euler", np.array(e, dtype=np.float64))
    elif mode == "QUATERNION":
        q_total = Matrix(r_total.tolist()).to_quaternion()
        if with_delta:
            qd = np.asarray(_raw(st, "delta_rotation_quaternion"), dtype=np.float64)
            if float(np.linalg.norm(qd)) > 0.0:
                q_total = Quaternion(qd.tolist()).inverted() @ q_total
        _write_component(st, "rotation_quaternion", np.array(q_total, dtype=np.float64))
    else:
        r = r_total
        if with_delta:
            r = _euler_m3(_raw(st, "delta_rotation_euler"), "XYZ").T @ r_total
        axis, angle = Matrix(r.tolist()).to_quaternion().to_axis_angle()
        ax = np.array(axis, dtype=np.float64)
        _write_component(st, "rotation_axis_angle", [angle, ax[0], ax[1], ax[2]])


def _set_basis64(ob, m) -> None:
    m = np.asarray(m, dtype=np.float64).reshape(4, 4)
    _write_component(ob, "location", m[:3, 3] - _raw64(ob, "delta_location"))
    m3 = m[:3, :3]
    norms = np.linalg.norm(m3, axis=0)
    if float(np.linalg.det(m3)) < 0.0:
        norms = -norms
    dscale = _raw64(ob, "delta_scale")
    cur = _raw64(ob, "scale")
    scale = np.where(dscale != 0.0, norms / np.where(dscale != 0.0, dscale, 1.0), cur)
    _write_component(ob, "scale", scale)
    r_total = m3 / np.where(norms != 0.0, norms, 1.0)
    _decompose_rotation_into(ob, r_total, with_delta=True)


def _get_type(self):
    return object_type_for(self._p.get("data"))


def _get_mode(self):
    return self._q_mode


def _get_basis(self):
    return _basis64(self).astype(np.float32)


def _set_basis(self, value):
    _set_basis64(self, value)


def _get_local(self):
    return _local64(self).astype(np.float32)


def _set_local(self, value):
    _set_basis64(self, _inv(_raw64(self, "matrix_parent_inverse")) @ np.asarray(value, dtype=np.float64))


def _get_world(self):
    return _world64(self).astype(np.float32)


def _set_world(self, value):
    m = np.asarray(value, dtype=np.float64).reshape(4, 4)
    parent = self._p.get("parent")
    local = _inv(_world64(parent)) @ m if parent is not None else m
    _set_local(self, local)


def _local_bounds(data):
    if data is None:
        return None
    fn = getattr(data, "q_bounds", None)
    if fn is None:
        return None
    mn, mx = fn()
    return np.asarray(mn, dtype=np.float64), np.asarray(mx, dtype=np.float64)


def _get_dimensions(self):
    b = _local_bounds(self._p.get("data"))
    if b is None:
        return np.zeros(3, dtype=np.float32)
    ext = b[1] - b[0]
    scale = np.linalg.norm(_world64(self)[:3, :3], axis=0)
    return (ext * scale).astype(np.float32)


def _set_dimensions(self, value):
    b = _local_bounds(self._p.get("data"))
    if b is None:
        return
    ext = b[1] - b[0]
    value = np.asarray(value, dtype=np.float64)
    scale = _raw64(self, "scale").copy()
    for i in range(3):
        if ext[i] > 0.0:
            scale[i] = _math.copysign(value[i] / ext[i], scale[i])
    _write_component(self, "scale", scale)


def _get_bound_box(self):
    b = _local_bounds(self._p.get("data"))
    if b is None:
        return np.zeros((8, 3), dtype=np.float32)
    return _geo_bound_box(np.stack([b[0], b[1]])).astype(np.float32)


def _euler_order(ob) -> str:
    mode = _raw(ob, "rotation_mode")
    return mode if mode in EULER_ORDERS else "XYZ"


def _is_material(value) -> bool:
    for klass in type(value).__mro__:
        rna = klass.__dict__.get("bl_rna")
        if rna is not None and getattr(rna, "identifier", None) == "Material":
            return True
    return False


def _data_materials(ob):
    data = ob._p.get("data")
    if data is None:
        return None
    return getattr(data, "materials", None)


def _set_slot_material(ob, index: int, material) -> None:
    if material is not None and not _is_material(material):
        raise PropertyTypeError(f"bpy_struct: item.attr = val: MaterialSlot.material expected a Material type, "
                                f"not {type(material).__name__}")
    mats = _data_materials(ob)
    if mats is None:
        return
    if index < len(mats):
        mats[index] = material
    else:
        mats.append(material)


def _get_active_material(self):
    mats = _data_materials(self)
    if mats is None:
        return None
    i = _raw(self, "active_material_index")
    return mats[i] if i < len(mats) else None


def _set_active_material(self, value):
    _set_slot_material(self, _raw(self, "active_material_index"), value)


def _data_poll(self, value) -> bool:
    if value is None:
        return True
    current = self._p.get("data")
    if current is None:
        return False
    try:
        return object_type_for(value) == object_type_for(current)
    except PropertyTypeError:
        return False


def _parent_poll(self, value) -> bool:
    if value is None:
        return True
    node = value
    seen = set()
    while node is not None and id(node) not in seen:
        if node is self:
            return False
        seen.add(id(node))
        node = node._p.get("parent")
    return True


_T = {"dirty": "TRANSFORM"}
_TE = {"dirty": "TRANSFORM", "euler_order": _euler_order}
_V = {"dirty": "VISIBILITY"}
_S = {"dirty": "SHADING"}
_H = {"dirty": "HIERARCHY"}
_ID4 = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


class Object(ID):

    _q_strict_attrs = True

    data: PointerProperty(type=ID, poll=_data_poll, options=set(),
                          meta={"on_remove": "DELETE_OWNER", "counts_user": True, "dirty": "GEOMETRY"})
    type: EnumProperty(items=[(t, t, "") for t in OBJECT_TYPES], default="EMPTY", meta={"virtual_get": _get_type})
    mode: EnumProperty(items=[(t, t, "") for t in OBJECT_MODES], default="OBJECT", meta={"virtual_get": _get_mode})
    bound_box: FloatVectorProperty(size=(8, 3), soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3,
                                   meta={"virtual_get": _get_bound_box})
    parent: "PointerProperty(type=Object, poll=_parent_poll, options=set(), meta={'counts_user': False, 'dirty': 'HIERARCHY'})"
    parent_type: EnumProperty(items=[(t, t, "") for t in ("OBJECT", "ARMATURE", "LATTICE", "VERTEX", "VERTEX_3",
                                                          "BONE")], default="OBJECT", meta=_T)
    active_material: PointerProperty(type=ID, options=set(),
                                     meta={"virtual_get": _get_active_material, "virtual_set": _set_active_material,
                                           "fixed_type_name": "Material", "counts_user": False, "dirty": "SHADING"})
    active_material_index: IntProperty(subtype="UNSIGNED", min=0, soft_max=10000, options=set(), meta=_S)
    location: FloatVectorProperty(subtype="TRANSLATION", unit="LENGTH", size=3, soft_min=-_FMAX, soft_max=_FMAX,
                                  step=1.0, precision=5, meta=_T)
    rotation_quaternion: FloatVectorProperty(subtype="QUATERNION", size=4, default=(1.0, 0.0, 0.0, 0.0),
                                             soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3, meta=_T)
    rotation_axis_angle: FloatVectorProperty(subtype="AXISANGLE", size=4, default=(0.0, 0.0, 1.0, 0.0),
                                             soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3, meta=_T)
    rotation_euler: FloatVectorProperty(subtype="EULER", unit="ROTATION", size=3, soft_min=-_FMAX, soft_max=_FMAX,
                                        step=100.0, precision=5, meta=_TE)
    rotation_mode: EnumProperty(items=[(t, t, "") for t in _ROTATION_MODES], default="XYZ", meta=_T)
    scale: FloatVectorProperty(subtype="XYZ", size=3, default=(1.0, 1.0, 1.0), soft_min=-_FMAX, soft_max=_FMAX,
                               step=1.0, precision=3, meta=_T)
    dimensions: FloatVectorProperty(subtype="XYZ_LENGTH", unit="LENGTH", size=3, soft_min=0.0, soft_max=_FMAX,
                                    step=1.0, precision=5, options=set(),
                                    meta={"virtual_get": _get_dimensions, "virtual_set": _set_dimensions,
                                          "dirty": "TRANSFORM"})
    delta_location: FloatVectorProperty(subtype="TRANSLATION", unit="LENGTH", size=3, soft_min=-_FMAX,
                                        soft_max=_FMAX, step=1.0, precision=5, meta=_T)
    delta_rotation_euler: FloatVectorProperty(subtype="EULER", unit="ROTATION", size=3, soft_min=-_FMAX,
                                              soft_max=_FMAX, step=100.0, precision=5, meta=_TE)
    delta_rotation_quaternion: FloatVectorProperty(subtype="QUATERNION", size=4, default=(1.0, 0.0, 0.0, 0.0),
                                                   soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3,
                                                   meta=_T)
    delta_scale: FloatVectorProperty(subtype="XYZ", size=3, default=(1.0, 1.0, 1.0), soft_min=-_FMAX,
                                     soft_max=_FMAX, step=1.0, precision=3, meta=_T)
    lock_location: BoolVectorProperty(size=3)
    lock_rotation: BoolVectorProperty(size=3)
    lock_rotation_w: BoolProperty()
    lock_rotations_4d: BoolProperty(default=True)
    lock_scale: BoolVectorProperty(size=3)
    matrix_world: FloatVectorProperty(subtype="MATRIX", size=(4, 4), soft_min=-10000.0, soft_max=10000.0, step=10.0,
                                      precision=3, options=set(),
                                      meta={"virtual_get": _get_world, "virtual_set": _set_world, "dirty": "TRANSFORM"})
    matrix_local: FloatVectorProperty(subtype="MATRIX", size=(4, 4), soft_min=-10000.0, soft_max=10000.0, step=10.0,
                                      precision=3, options=set(),
                                      meta={"virtual_get": _get_local, "virtual_set": _set_local, "dirty": "TRANSFORM"})
    matrix_basis: FloatVectorProperty(subtype="MATRIX", size=(4, 4), soft_min=-10000.0, soft_max=10000.0, step=10.0,
                                      precision=3, options=set(),
                                      meta={"virtual_get": _get_basis, "virtual_set": _set_basis, "dirty": "TRANSFORM"})
    matrix_parent_inverse: FloatVectorProperty(subtype="MATRIX", size=(4, 4), default=_ID4, soft_min=-10000.0,
                                               soft_max=10000.0, step=10.0, precision=3, meta=_T)
    empty_display_type: EnumProperty(items=[(t, t, "") for t in ("PLAIN_AXES", "ARROWS", "SINGLE_ARROW", "CIRCLE",
                                                                 "CUBE", "SPHERE", "CONE", "IMAGE")],
                                     default="PLAIN_AXES")
    empty_display_size: FloatProperty(subtype="DISTANCE", unit="LENGTH", default=1.0, min=0.0001, max=1000.0,
                                      soft_min=0.01, soft_max=100.0, step=1.0, precision=2)
    pass_index: IntProperty(subtype="UNSIGNED", min=0, max=32767)
    color: FloatVectorProperty(subtype="COLOR", size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, soft_max=1.0,
                               step=10.0, precision=3, meta=_S)
    hide_viewport: BoolProperty(meta=_V)
    hide_select: BoolProperty(options=set(), meta=_V)
    hide_render: BoolProperty(meta=_V)
    instance_type: EnumProperty(items=[(t, t, "") for t in ("NONE", "VERTS", "FACES", "COLLECTION")],
                                default="NONE", meta=_H)
    instance_collection: PointerProperty(type=Collection, options=set(), meta={"counts_user": True,
                                                                               "dirty": "HIERARCHY"})
    display_type: EnumProperty(items=[(t, t, "") for t in ("BOUNDS", "WIRE", "SOLID", "TEXTURED")],
                               default="TEXTURED", meta=_S)
    show_bounds: BoolProperty()
    show_name: BoolProperty()
    show_axis: BoolProperty()
    show_wire: BoolProperty()
    show_in_front: BoolProperty()

    @classmethod
    def _q_construct(cls, name: str):
        inst = super()._q_construct(name)
        object.__setattr__(inst, "_q_mode", "OBJECT")
        object.__setattr__(inst, "_q_modifiers", [])
        object.__setattr__(inst, "_q_active_modifier", None)
        object.__setattr__(inst, "_q_modifier_uid", 0)
        object.__setattr__(inst, "_q_vgroups", [])
        object.__setattr__(inst, "_q_active_vgroup", -1)
        object.__setattr__(inst, "_q_slots", [])
        object.__setattr__(inst, "_q_temp_mesh", None)
        object.__setattr__(inst, "_q_modifiers_coll", ObjectModifiers(inst))
        object.__setattr__(inst, "_q_constraints_coll", ObjectConstraints(inst))
        object.__setattr__(inst, "_q_vgroups_coll", VertexGroups(inst))
        object.__setattr__(inst, "_q_slots_coll", _MaterialSlots(inst))
        return inst

    def _q_on_change(self, pdef) -> None:
        if pdef.identifier == "parent":
            self.q_tag("HIERARCHY", "TRANSFORM")
            return
        super()._q_on_change(pdef)

    @property
    def children(self) -> tuple:
        main = self._q_main
        if main is None:
            return ()
        return tuple(ob for ob in main.objects if ob._p.get("parent") is self)

    @property
    def children_recursive(self) -> list:
        out: list = []
        seen: set[int] = set()

        def walk(node):
            for child in node.children:
                if id(child) not in seen:
                    seen.add(id(child))
                    out.append(child)
                    walk(child)
        walk(self)
        return out

    @property
    def users_collection(self) -> tuple:
        main = self._q_main
        if main is None:
            return ()
        out = [c for c in main.collections if any(o is self for o in c._q_objects)]
        for scene in main.scenes:
            master = scene.collection
            if any(o is self for o in master._q_objects):
                out.append(master)
        return tuple(out)

    @property
    def users_scene(self) -> tuple:
        main = self._q_main
        if main is None:
            return ()
        return tuple(s for s in main.scenes if any(o is self for o in s.collection.all_objects))

    @property
    def material_slots(self):
        return self._q_slots_coll

    @property
    def modifiers(self):
        return self._q_modifiers_coll

    @property
    def constraints(self):
        return self._q_constraints_coll

    @property
    def vertex_groups(self):
        return self._q_vgroups_coll

    @property
    def animation_data(self):
        return None

    def _q_resolve_view_layer(self, view_layer):
        if view_layer is not None:
            return view_layer
        ctx = hooks.current_context()
        vl = getattr(ctx, "view_layer", None) if ctx is not None else None
        if vl is not None:
            return vl
        main = self._q_main
        if main is None:
            return None
        for scene in main.scenes:
            for layer in scene.view_layers:
                if layer.q_base(self) is not None:
                    return layer
        return None

    def select_get(self, view_layer=None) -> bool:
        vl = self._q_resolve_view_layer(view_layer)
        base = vl.q_base(self) if vl is not None else None
        return bool(base[0]) if base is not None else False

    def select_set(self, state: bool, view_layer=None) -> None:
        vl = self._q_resolve_view_layer(view_layer)
        if vl is None or vl.q_base(self) is None:
            raise LinkError(f"Object '{self._q_name}' can't be selected because it is not in View Layer "
                            f"'{getattr(vl, 'name', '')}'!")
        vl._q_set_base(self, 0, bool(state))
        self.q_tag("SELECT")

    def hide_get(self, view_layer=None) -> bool:
        vl = self._q_resolve_view_layer(view_layer)
        base = vl.q_base(self) if vl is not None else None
        return bool(base[1]) if base is not None else False

    def hide_set(self, state: bool, view_layer=None) -> None:
        vl = self._q_resolve_view_layer(view_layer)
        if vl is None or vl.q_base(self) is None:
            raise LinkError(f"Object '{self._q_name}' can't be hidden because it is not in View Layer "
                            f"'{getattr(vl, 'name', '')}'!")
        vl._q_set_base(self, 1, bool(state))
        self.q_tag("VISIBILITY")

    def visible_get(self, view_layer=None, viewport=None) -> bool:
        vl = self._q_resolve_view_layer(view_layer)
        if vl is None:
            return False
        base = vl.q_base(self)
        if base is None or base[1] or self._p.get("hide_viewport", False):
            return False
        return bool(vl._q_object_in_visible_layer(self))

    def holdout_get(self, view_layer=None) -> bool:
        return False

    def indirect_only_get(self, view_layer=None) -> bool:
        return False

    def to_mesh(self, preserve_all_data_layers: bool = False, depsgraph=None):
        if self.type != "MESH":
            raise NotImplementedInQuartz("Object.to_mesh")
        data = self._p.get("data")
        self.to_mesh_clear()
        new = type(data)._q_construct(data._q_name)
        data._q_copy_into(new)
        self._q_temp_mesh = new
        return new

    def to_mesh_clear(self) -> None:
        tmp = self._q_temp_mesh
        if tmp is not None:
            self._q_temp_mesh = None
            tmp._q_tombstone()

    def convert_space(self, pose_bone=None, matrix=None, from_space: str = "WORLD", to_space: str = "WORLD"):
        for space, arg in ((from_space, "from_space"), (to_space, "to_space")):
            if space not in _SPACES:
                raise PropertyTypeError(f'Object.convert_space(): error with keyword argument "{arg}" - '
                                        f'enum "{space}" not found in ({_enum_listing(_SPACES)})')
        if "POSE" in (from_space, to_space):
            raise NotImplementedInQuartz("Object.convert_space")
        m = np.eye(4) if matrix is None else np.asarray(matrix, dtype=np.float64).reshape(4, 4)
        parent = self._p.get("parent")
        p = _world64(parent) if parent is not None else np.eye(4)
        mpi = _raw64(self, "matrix_parent_inverse")
        to_world = {"WORLD": np.eye(4), "LOCAL_WITH_PARENT": p, "LOCAL": p @ mpi}
        world = to_world[from_space] @ m
        result = _inv(to_world[to_space]) @ world
        return Matrix(result.tolist())

    def update_from_editmode(self) -> bool:
        data = self._p.get("data")
        if self._q_mode == "EDIT" and data is not None and hasattr(data, "q_flush_edit"):
            return data.q_flush_edit()
        return False

    def _q_bvh(self):
        data = self._p.get("data")
        geo = getattr(data, "q_geometry", None) if data is not None else None
        if geo is None:
            return None
        tris, tri_face = _geo_triangulate(geo)
        tri_verts = np.asarray(geo.corner_verts)[np.asarray(tris, dtype=np.int64)] if len(tris) else \
            np.zeros((0, 3), dtype=np.int64)
        return BVHTree._q_from_triangles(np.asarray(geo.positions), tri_verts, tri_face)

    def ray_cast(self, origin, direction, distance: float = 1.70141e+38, depsgraph=None):
        miss = (False, Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0)), -1)
        bvh = self._q_bvh()
        if bvh is None:
            return miss
        loc, normal, index, _dist = bvh.ray_cast(origin, direction, distance)
        if loc is None:
            return miss
        return (True, loc, normal, index)

    def closest_point_on_mesh(self, origin, distance: float = 1.84467e+19, depsgraph=None):
        miss = (False, Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0)), -1)
        bvh = self._q_bvh()
        if bvh is None:
            return miss
        loc, normal, index, _dist = bvh.find_nearest(origin, distance)
        if loc is None:
            return miss
        return (True, loc, normal, index)

    def is_modified(self, scene, settings: str) -> bool:
        return False

    def is_deform_modified(self, scene, settings: str) -> bool:
        return False

    def find_armature(self):
        return None

    def cache_release(self) -> None:
        return None

    def shape_key_add(self, *a, **k):
        raise NotImplementedInQuartz("Object.shape_key_add")

    def shape_key_remove(self, *a, **k):
        raise NotImplementedInQuartz("Object.shape_key_remove")

    def shape_key_clear(self, *a, **k):
        raise NotImplementedInQuartz("Object.shape_key_clear")

    def shape_keys_selected(self, *a, **k):
        raise NotImplementedInQuartz("Object.shape_keys_selected")

    def local_view_get(self, *a, **k):
        raise NotImplementedInQuartz("Object.local_view_get")

    def local_view_set(self, *a, **k):
        raise NotImplementedInQuartz("Object.local_view_set")

    def visible_in_viewport_get(self, *a, **k):
        raise NotImplementedInQuartz("Object.visible_in_viewport_get")

    def calc_matrix_camera(self, *a, **k):
        raise NotImplementedInQuartz("Object.calc_matrix_camera")

    def camera_fit_coords(self, *a, **k):
        raise NotImplementedInQuartz("Object.camera_fit_coords")

    def crazyspace_eval(self, *a, **k):
        raise NotImplementedInQuartz("Object.crazyspace_eval")

    def crazyspace_displacement_to_deformed(self, *a, **k):
        raise NotImplementedInQuartz("Object.crazyspace_displacement_to_deformed")

    def crazyspace_displacement_to_original(self, *a, **k):
        raise NotImplementedInQuartz("Object.crazyspace_displacement_to_original")

    def crazyspace_eval_clear(self, *a, **k):
        raise NotImplementedInQuartz("Object.crazyspace_eval_clear")

    def to_curve(self, *a, **k):
        raise NotImplementedInQuartz("Object.to_curve")

    def to_curve_clear(self, *a, **k):
        raise NotImplementedInQuartz("Object.to_curve_clear")

    def q_set_mode(self, mode: str) -> None:
        if mode not in object_modes_for(self):
            raise PropertyValueError(f'Object.q_set_mode(): mode "{mode}" not supported for object type '
                                     f'"{self.type}"')
        old = self._q_mode
        if mode == old:
            return
        data = self._p.get("data")
        hook = getattr(data, "q_set_editmode", None) if data is not None else None
        if old == "EDIT" and hook is not None:
            hook(False)
        self._q_mode = mode
        if mode == "EDIT" and hook is not None:
            hook(True)
        self.q_tag("DATA")

    def _q_refs(self):
        return _q_relabel_refs(super()._q_refs(), self, self._p.get("data"), "DATA")

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        state["mode"] = self._q_mode
        mods = []
        for m in self._q_modifiers:
            ms = m._q_state_get()
            ms["name"] = m._q_name
            ms["type"] = type(m).__dict__["type"].read_raw(m)
            mods.append(ms)
        state["modifiers"] = mods
        state["modifier_uid"] = self._q_modifier_uid
        groups = []
        for g in self._q_vgroups:
            keys = sorted(g._q_weights)
            groups.append({
                "name": g._q_name,
                "lock_weight": bool(g._p.get("lock_weight", False)),
                "indices": np.array(keys, dtype=np.int32),
                "weights": np.array([g._q_weights[k] for k in keys], dtype=np.float32),
            })
        state["vertex_groups"] = groups
        return state

    def _q_state_set(self, state: dict) -> None:
        super()._q_state_set(state)
        if "mode" in state:
            self._q_mode = str(state["mode"])
        if "modifiers" in state:
            old = list(self._q_modifiers)
            new_list = []
            for i, ms in enumerate(state["modifiers"]):
                mod = old[i] if i < len(old) else Modifier._q_new_child(owner=self, path="")
                mod._q_state_set(ms)
                mod._q_name = str(ms.get("name", ""))
                type(mod).__dict__["type"].write_raw(mod, ms.get("type", MODIFIER_TYPES[0]))
                mod._q_set_owner(self, _modifier_path(mod._q_name))
                new_list.append(mod)
            self._q_modifiers[:] = new_list
            if self._q_active_modifier not in new_list:
                self._q_active_modifier = new_list[-1] if new_list else None
        if "modifier_uid" in state:
            self._q_modifier_uid = int(state["modifier_uid"])
        if "vertex_groups" in state:
            old = list(self._q_vgroups)
            new_groups = []
            for i, gs in enumerate(state["vertex_groups"]):
                g = old[i] if i < len(old) else VertexGroup._q_new_child(owner=self, path="")
                g._q_name = str(gs.get("name", "Group"))
                type(g).__dict__["lock_weight"].write_raw(g, bool(gs.get("lock_weight", False)))
                idx = np.asarray(gs.get("indices", ()), dtype=np.int64).tolist()
                wts = np.asarray(gs.get("weights", ()), dtype=np.float32).tolist()
                g._q_weights = dict(zip(idx, wts))
                g._q_set_owner(self, _vgroup_path(g._q_name))
                new_groups.append(g)
            self._q_vgroups[:] = new_groups
            if self._q_active_vgroup >= len(new_groups):
                self._q_active_vgroup = len(new_groups) - 1

    def _q_copy_into(self, new) -> None:
        super()._q_copy_into(new)
        new._q_mode = "OBJECT"


Object = builtin_struct(Object)


def _modifier_path(name: str) -> str:
    return f'modifiers["{escape_identifier(name)}"]'


def _vgroup_path(name: str) -> str:
    return f'vertex_groups["{escape_identifier(name)}"]'


def _mod_get_name(self):
    return self._q_name


def _mod_set_name(self, value):
    ob = self._q_owner
    if ob is None:
        self._q_name = value
        return
    new = unique_name(value, lambda n: any(m._q_name == n for m in ob._q_modifiers if m is not self),
                      default=self._q_name or "Modifier")
    self._q_name = new
    self._q_path = _modifier_path(new)


def _mod_get_active(self):
    ob = self._q_owner
    return ob is not None and ob._q_active_modifier is self


def _mod_set_active(self, value):
    ob = self._q_owner
    if ob is None:
        return
    if value:
        ob._q_active_modifier = self
    elif ob._q_active_modifier is self:
        ob._q_active_modifier = None


def _zero(self):
    return 0.0


def _true(self):
    return True


_G = {"dirty": "GEOMETRY"}


@builtin_struct
class Modifier(Struct):

    _q_strict_attrs = True

    name: StringProperty(maxlen=64, options=set(), meta={"virtual_get": _mod_get_name, "virtual_set": _mod_set_name,
                                                         "dirty": "GEOMETRY"})
    type: EnumProperty(items=[(t, t, "") for t in MODIFIER_TYPES], default=MODIFIER_TYPES[0],
                       meta={"readonly": True, "dirty": "GEOMETRY"})
    show_viewport: BoolProperty(meta=_G)
    show_render: BoolProperty(meta=_G)
    show_in_editmode: BoolProperty(meta=_G)
    show_on_cage: BoolProperty(meta=_G)
    show_expanded: BoolProperty(meta=_G)
    is_active: BoolProperty(options=set(), meta={"virtual_get": _mod_get_active, "virtual_set": _mod_set_active,
                                                 "dirty": "GEOMETRY"})
    use_pin_to_last: BoolProperty(options=set(), meta=_G)
    is_override_data: BoolProperty(meta={"virtual_get": _true, "dirty": "GEOMETRY"})
    use_apply_on_spline: BoolProperty(meta=_G)
    execution_time: FloatProperty(subtype="TIME_ABSOLUTE", unit="TIME_ABSOLUTE", soft_min=-10000.0,
                                  soft_max=10000.0, step=10.0, precision=3, options=set(),
                                  meta={"virtual_get": _zero, "dirty": "GEOMETRY"})
    persistent_uid: IntProperty(soft_min=-10000, soft_max=10000, meta={"readonly": True, "dirty": "GEOMETRY"})

    @classmethod
    def _q_new_child(cls, owner, path):
        inst = super()._q_new_child(owner, path)
        object.__setattr__(inst, "_q_name", "")
        return inst


class ObjectModifiers(PropCollection):

    def __init__(self, ob: Object) -> None:
        super().__init__(owner=ob, path="modifiers")
        self._q_ob = ob

    def _q_items(self):
        return self._q_ob._q_modifiers

    def _q_key(self, item):
        return item._q_name

    @property
    def active(self):
        return self._q_ob._q_active_modifier

    @active.setter
    def active(self, value):
        if value is not None and not any(m is value for m in self._q_ob._q_modifiers):
            raise LinkError("ObjectModifiers.active: modifier not in object")
        self._q_ob._q_active_modifier = value

    def new(self, name: str, type: str):
        ob = self._q_ob
        if type not in MODIFIER_TYPES:
            raise PropertyTypeError(f'ObjectModifiers.new(): error with argument 2, "type" - enum "{type}" '
                                    f'not found in ({_enum_listing(MODIFIER_TYPES)})')
        if not isinstance(name, str):
            raise PropertyTypeError(f"ObjectModifiers.new(): error with argument 1, \"name\" - expected a string "
                                    f"type, not {name.__class__.__name__}")
        final = unique_name(name, lambda n: any(m._q_name == n for m in ob._q_modifiers), default=type.title())
        mod = Modifier._q_new_child(owner=ob, path=_modifier_path(final))
        mod._q_name = final
        pdefs = Modifier.__dict__
        pdefs["type"].write_raw(mod, type)
        for flag in ("show_viewport", "show_render", "show_in_editmode", "show_expanded"):
            pdefs[flag].write_raw(mod, True)
        ob._q_modifier_uid += 1
        pdefs["persistent_uid"].write_raw(mod, ob._q_modifier_uid)
        ob._q_modifiers.append(mod)
        ob._q_active_modifier = mod
        ob.q_tag("GEOMETRY")
        return mod

    def remove(self, modifier) -> None:
        ob = self._q_ob
        for i, m in enumerate(ob._q_modifiers):
            if m is modifier:
                del ob._q_modifiers[i]
                if ob._q_active_modifier is modifier:
                    ob._q_active_modifier = ob._q_modifiers[-1] if ob._q_modifiers else None
                modifier._q_set_owner(None, "")
                ob.q_tag("GEOMETRY")
                return
        raise LinkError(f"ObjectModifiers.remove(): modifier '{getattr(modifier, '_q_name', modifier)}' "
                        f"not in object '{ob._q_name}'")

    def clear(self) -> None:
        ob = self._q_ob
        for m in ob._q_modifiers:
            m._q_set_owner(None, "")
        ob._q_modifiers.clear()
        ob._q_active_modifier = None
        ob.q_tag("GEOMETRY")

    def move(self, from_index: int, to_index: int) -> None:
        mods = self._q_ob._q_modifiers
        n = len(mods)
        if not (0 <= from_index < n) or not (0 <= to_index < n):
            raise IndexError(f"ObjectModifiers.move(): index out of range ({from_index} -> {to_index}, {n} items)")
        mods.insert(to_index, mods.pop(from_index))
        self._q_ob.q_tag("GEOMETRY")


class ObjectConstraints(PropCollection):

    def __init__(self, ob: Object) -> None:
        super().__init__(owner=ob, path="constraints")
        self._q_ob = ob

    def _q_items(self):
        return ()

    @property
    def active(self):
        return None

    def new(self, type: str):
        raise NotImplementedInQuartz("ObjectConstraints.new")

    def remove(self, constraint) -> None:
        raise LinkError("ObjectConstraints.remove(): constraint not in object")

    def clear(self) -> None:
        return None

    def move(self, from_index: int, to_index: int) -> None:
        raise IndexError("ObjectConstraints.move(): index out of range (0 items)")

    def copy(self, constraint):
        raise NotImplementedInQuartz("ObjectConstraints.copy")


def _vg_get_name(self):
    return self._q_name


def _vg_set_name(self, value):
    ob = self._q_owner
    if ob is None:
        self._q_name = value
        return
    new = unique_name(value, lambda n: any(g._q_name == n for g in ob._q_vgroups if g is not self),
                      default="Group")
    self._q_name = new
    self._q_path = _vgroup_path(new)


def _vg_get_index(self):
    ob = self._q_owner
    if ob is None:
        return -1
    for i, g in enumerate(ob._q_vgroups):
        if g is self:
            return i
    return -1


@builtin_struct
class VertexGroup(Struct):

    _q_strict_attrs = True

    name: StringProperty(maxlen=64, meta={"virtual_get": _vg_get_name, "virtual_set": _vg_set_name})
    index: IntProperty(meta={"virtual_get": _vg_get_index})
    lock_weight: BoolProperty()

    @classmethod
    def _q_new_child(cls, owner, path):
        inst = super()._q_new_child(owner, path)
        object.__setattr__(inst, "_q_name", "Group")
        object.__setattr__(inst, "_q_weights", {})
        return inst

    def _q_touch(self) -> None:
        ob = self._q_owner
        if ob is not None:
            ob.q_tag("DATA")

    def add(self, index, weight: float, type: str) -> None:
        if type not in _VG_ADD_TYPES:
            raise PropertyTypeError(f'VertexGroup.add(): error with argument 3, "type" - enum "{type}" not found '
                                    f'in ({_enum_listing(_VG_ADD_TYPES)})')
        w = float(np.float32(weight))
        for i in index:
            i = int(i)
            cur = self._q_weights.get(i)
            if type == "REPLACE":
                new = w
            elif type == "ADD":
                new = (cur or 0.0) + w
            else:
                if cur is None:
                    continue
                new = cur - w
            self._q_weights[i] = float(np.float32(min(1.0, max(0.0, new))))
        self._q_touch()

    def remove(self, index) -> None:
        for i in index:
            self._q_weights.pop(int(i), None)
        self._q_touch()

    def weight(self, index: int) -> float:
        i = int(index)
        if i not in self._q_weights:
            raise LinkError(f"VertexGroup.weight(): vertex {i} not in group '{self._q_name}'")
        return self._q_weights[i]


class VertexGroups(PropCollection):

    def __init__(self, ob: Object) -> None:
        super().__init__(owner=ob, path="vertex_groups")
        self._q_ob = ob

    def _q_items(self):
        return self._q_ob._q_vgroups

    def _q_key(self, item):
        return item._q_name

    @property
    def active_index(self) -> int:
        return self._q_ob._q_active_vgroup

    @active_index.setter
    def active_index(self, value: int) -> None:
        n = len(self._q_ob._q_vgroups)
        self._q_ob._q_active_vgroup = max(-1, min(int(value), n - 1))

    @property
    def active(self):
        i = self._q_ob._q_active_vgroup
        groups = self._q_ob._q_vgroups
        return groups[i] if 0 <= i < len(groups) else None

    @active.setter
    def active(self, value) -> None:
        for i, g in enumerate(self._q_ob._q_vgroups):
            if g is value:
                self._q_ob._q_active_vgroup = i
                return
        raise LinkError("VertexGroups.active: group not in object")

    def new(self, name: str = "Group"):
        ob = self._q_ob
        final = unique_name(name, lambda n: any(g._q_name == n for g in ob._q_vgroups), default="Group")
        g = VertexGroup._q_new_child(owner=ob, path=_vgroup_path(final))
        g._q_name = final
        ob._q_vgroups.append(g)
        ob._q_active_vgroup = len(ob._q_vgroups) - 1
        ob.q_tag("DATA")
        return g

    def remove(self, group) -> None:
        ob = self._q_ob
        for i, g in enumerate(ob._q_vgroups):
            if g is group:
                del ob._q_vgroups[i]
                group._q_set_owner(None, "")
                if ob._q_active_vgroup >= len(ob._q_vgroups):
                    ob._q_active_vgroup = len(ob._q_vgroups) - 1
                ob.q_tag("DATA")
                return
        raise LinkError(f"VertexGroups.remove(): group '{getattr(group, '_q_name', group)}' not in object "
                        f"'{ob._q_name}'")

    def clear(self) -> None:
        ob = self._q_ob
        for g in ob._q_vgroups:
            g._q_set_owner(None, "")
        ob._q_vgroups.clear()
        ob._q_active_vgroup = -1
        ob.q_tag("DATA")


def _slot_ob(slot):
    return slot._q_owner


def _slot_get_material(self):
    mats = _data_materials(_slot_ob(self))
    i = self._q_index
    if mats is None or i >= len(mats):
        return None
    return mats[i]


def _slot_set_material(self, value):
    _set_slot_material(_slot_ob(self), self._q_index, value)


def _slot_get_index(self):
    return self._q_index


def _slot_get_name(self):
    mat = _slot_get_material(self)
    return mat._q_name if mat is not None else ""


def _slot_get_link(self):
    return "DATA"


def _slot_set_link(self, value):
    if value == "OBJECT":
        raise NotImplementedInQuartz("MaterialSlot.link")


@builtin_struct
class MaterialSlot(Struct):

    _q_strict_attrs = True

    link: EnumProperty(items=[(t, t, "") for t in _MATERIAL_SLOT_LINKS], default="DATA", options=set(),
                       meta={"virtual_get": _slot_get_link, "virtual_set": _slot_set_link})
    material: PointerProperty(type=ID, options=set(),
                              meta={"virtual_get": _slot_get_material, "virtual_set": _slot_set_material,
                                    "fixed_type_name": "Material", "counts_user": False, "dirty": "SHADING"})
    slot_index: IntProperty(soft_min=-10000, soft_max=10000, options=set(), meta={"virtual_get": _slot_get_index})
    name: StringProperty(options=set(), meta={"virtual_get": _slot_get_name})


class _MaterialSlots(PropCollection):

    def __init__(self, ob: Object) -> None:
        super().__init__(owner=ob, path="material_slots")
        self._q_ob = ob

    def _q_items(self):
        ob = self._q_ob
        mats = _data_materials(ob)
        n = len(mats) if mats is not None else 0
        slots = ob._q_slots
        while len(slots) < n:
            i = len(slots)
            slot = MaterialSlot._q_new_child(owner=ob, path=f"material_slots[{i}]")
            object.__setattr__(slot, "_q_index", i)
            slots.append(slot)
        del slots[n:]
        return list(slots)

    def _q_key(self, item):
        return _slot_get_name(item)


class BlendDataObjects(IDCollection):

    def new(self, name: str, object_data):
        if getattr(type(object_data), "_q_removed", False):
            object_data.name
        object_type_for(object_data)
        if not isinstance(name, str):
            raise PropertyTypeError(f"BlendDataObjects.new(): error with argument 1, \"name\" - expected a string "
                                    f"type, not {type(name).__name__}")
        info = self.q_info
        ob = info.cls._q_construct(unique_name(name, lambda n: self._q_taken(n), default=info.default_name))
        Object.__dict__["data"].write_raw(ob, object_data)
        self._q_link(ob)
        ob.q_tag(*DIRTY_CHANNELS)
        return ob

    def remove(self, object: Object, do_unlink: bool = True, do_id_user: bool = True,
               do_ui_user: bool = True) -> None:
        super().remove(object, do_unlink, do_id_user, do_ui_user)


register_id_type(Object, id_type="OBJECT", collection="objects", default_name="Object",
                 collection_cls=BlendDataObjects)
