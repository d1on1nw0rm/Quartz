import math as _math

import numpy as np

from quartz.app import handlers
from quartz.errors import LinkError, NotImplementedInQuartz, PropertyTypeError, PropertyValueError
from quartz.math import Matrix, Vector
from quartz.math.bvhtree import BVHTree
from quartz.math.euler import EULER_ORDERS
from quartz.geometry import transform_points as _transform_points
from quartz.geometry import triangulate as _geo_triangulate
from quartz.props import (BoolProperty, BoolVectorProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                          IntProperty, PointerProperty, StringProperty)
from quartz.rna import PropCollection, Struct, builtin_struct, hooks
from quartz.rna.datapath import escape_identifier
from quartz.depsgraph import Depsgraph, depsgraph_for
from quartz.types.blenddata import IDCollection
from quartz.types.collection import Collection
from quartz.types.id import ID, _q_relabel_refs, register_id_type
from quartz.types.naming import unique_name
from quartz.types.object import (Object, _compose, _decompose_rotation_into, _raw, _raw64, _rotation_only,
                                 _write_component)
from quartz.types.world import World

__all__ = [
    "RenderSettings", "UnitSettings", "ToolSettings", "View3DCursor", "LayerCollection", "LayerObjects",
    "ViewLayer", "ViewLayers", "SceneObjects", "TimelineMarkers", "Scene", "BlendDataScenes",
]

_FMAX = 3.4028234663852886e38
_FRAME_LIMIT = 1048574
_ROTATION_MODES = ("QUATERNION", "XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX", "AXIS_ANGLE")
_VIS = {"dirty": "VISIBILITY"}


def _items(seq):
    return [(t, t, "") for t in seq]


@builtin_struct
class RenderSettings(Struct):

    _q_strict_attrs = True

    engine: EnumProperty(items=_items(("BLENDER_EEVEE",)), default="BLENDER_EEVEE", options=set())
    resolution_x: IntProperty(subtype="PIXEL", default=1920, min=4, max=65536, options=set())
    resolution_y: IntProperty(subtype="PIXEL", default=1080, min=4, max=65536, options=set())
    resolution_percentage: IntProperty(subtype="PERCENTAGE", default=100, min=1, max=32767, soft_max=100, step=10,
                                       options=set())
    fps: IntProperty(default=24, min=1, max=32767, soft_max=240, options=set())
    fps_base: FloatProperty(default=1.0, min=1e-05, max=1000000.0, soft_min=0.1, soft_max=120.0, step=2.0,
                            precision=3, options=set())
    filepath: StringProperty(subtype="FILE_PATH", default="//", maxlen=1024, options=set())
    film_transparent: BoolProperty()


@builtin_struct
class UnitSettings(Struct):

    _q_strict_attrs = True

    system: EnumProperty(items=_items(("NONE", "METRIC", "IMPERIAL")), default="NONE", options=set())
    system_rotation: EnumProperty(items=_items(("DEGREES", "RADIANS")), default="DEGREES", options=set())
    scale_length: FloatProperty(subtype="UNSIGNED", default=1.0, min=1e-09, max=1000000000.0, soft_min=0.001,
                                soft_max=100.0, step=0.1, precision=6, options=set())
    use_separate: BoolProperty(options=set())
    length_unit: EnumProperty(items=_items(("DEFAULT",)), default="DEFAULT", options=set())
    mass_unit: EnumProperty(items=_items(("DEFAULT",)), default="DEFAULT", options=set())
    time_unit: EnumProperty(items=_items(("DEFAULT",)), default="DEFAULT", options=set())
    temperature_unit: EnumProperty(items=_items(("DEFAULT",)), default="DEFAULT", options=set())


@builtin_struct
class ToolSettings(Struct):

    _q_strict_attrs = True

    mesh_select_mode: BoolVectorProperty(size=3, options=set())
    use_proportional_edit: BoolProperty(options=set())
    proportional_size: FloatProperty(default=1.0, min=1e-05, max=5000.0, step=10.0, precision=3, options=set())
    transform_pivot_point: EnumProperty(items=_items(("BOUNDING_BOX_CENTER", "CURSOR", "INDIVIDUAL_ORIGINS",
                                                      "MEDIAN_POINT", "ACTIVE_ELEMENT")),
                                        default="MEDIAN_POINT", options=set())
    use_snap: BoolProperty(options=set())
    use_keyframe_insert_auto: BoolProperty(default=True, options=set())


def _cursor_order(st) -> str:
    mode = _raw(st, "rotation_mode")
    return mode if mode in EULER_ORDERS else "XYZ"


def _cursor_get_matrix(self):
    return _compose(_raw64(self, "location"), _rotation_only(self), (1.0, 1.0, 1.0)).astype(np.float32)


def _cursor_set_matrix(self, value):
    m = np.asarray(value, dtype=np.float64).reshape(4, 4)
    _write_component(self, "location", m[:3, 3])
    m3 = m[:3, :3]
    norms = np.linalg.norm(m3, axis=0)
    _decompose_rotation_into(self, m3 / np.where(norms != 0.0, norms, 1.0), with_delta=False)


@builtin_struct
class View3DCursor(Struct):

    _q_strict_attrs = True

    location: FloatVectorProperty(subtype="XYZ_LENGTH", unit="LENGTH", size=3, soft_min=-10000.0, soft_max=10000.0,
                                  step=10.0, precision=4, options=set())
    rotation_quaternion: FloatVectorProperty(subtype="QUATERNION", size=4, default=(1.0, 0.0, 0.0, 0.0),
                                             soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3,
                                             options=set())
    rotation_axis_angle: FloatVectorProperty(subtype="AXISANGLE", size=4, default=(0.0, 0.0, 1.0, 0.0),
                                             soft_min=-10000.0, soft_max=10000.0, step=10.0, precision=3,
                                             options=set())
    rotation_euler: FloatVectorProperty(subtype="EULER", unit="ROTATION", size=3, soft_min=-_FMAX, soft_max=_FMAX,
                                        step=100.0, precision=5, options=set(), meta={"euler_order": _cursor_order})
    rotation_mode: EnumProperty(items=_items(_ROTATION_MODES), default="XYZ", options=set())
    matrix: FloatVectorProperty(subtype="MATRIX", size=(4, 4), soft_min=-10000.0, soft_max=10000.0, step=10.0,
                                precision=3, options=set(),
                                meta={"virtual_get": _cursor_get_matrix, "virtual_set": _cursor_set_matrix})


def _lc_flag_getter(index: int):
    def getter(self):
        if index == 0 and self._q_coll is self._q_vl._q_scene.collection:
            return False
        return bool(self._q_vl._q_flags_for(self._q_coll)[index])
    return getter


def _lc_flag_setter(index: int):
    def setter(self, value):
        if index == 0 and self._q_coll is self._q_vl._q_scene.collection:
            return
        self._q_vl._q_flags_for(self._q_coll)[index] = bool(value)
    return setter


def _lc_collection(self):
    return self._q_coll


def _lc_name(self):
    return self._q_coll._q_name


def _lc_is_visible(self):
    return self._q_vl._q_path_visible(self._q_cpath)


@builtin_struct
class LayerCollection(Struct):

    _q_strict_attrs = True

    collection: PointerProperty(type=Collection, options=set(), meta={"virtual_get": _lc_collection,
                                                                      "counts_user": False})
    name: StringProperty(maxlen=258, options=set(), meta={"virtual_get": _lc_name})
    exclude: BoolProperty(options=set(), meta={"virtual_get": _lc_flag_getter(0), "virtual_set": _lc_flag_setter(0),
                                               "dirty": "VISIBILITY"})
    holdout: BoolProperty(options=set(), meta={"virtual_get": _lc_flag_getter(2), "virtual_set": _lc_flag_setter(2),
                                               "dirty": "VISIBILITY"})
    indirect_only: BoolProperty(options=set(), meta={"virtual_get": _lc_flag_getter(3),
                                                     "virtual_set": _lc_flag_setter(3), "dirty": "VISIBILITY"})
    hide_viewport: BoolProperty(options=set(), meta={"virtual_get": _lc_flag_getter(1),
                                                     "virtual_set": _lc_flag_setter(1), "dirty": "VISIBILITY"})
    is_visible: BoolProperty(options=set(), meta={"virtual_get": _lc_is_visible})

    @property
    def children(self):
        coll = self.__dict__.get("_q_children_coll")
        if coll is None:
            coll = _LayerCollectionChildren(self)
            object.__setattr__(self, "_q_children_coll", coll)
        return coll

    def visible_get(self) -> bool:
        return self.is_visible

    def has_objects(self) -> bool:
        return bool(self._q_coll._q_objects)

    def has_selected_objects(self, view_layer) -> bool:
        return any(ob.select_get(view_layer) for ob in self._q_coll._q_objects)


class _LayerCollectionChildren(PropCollection):

    def __init__(self, lc: LayerCollection) -> None:
        super().__init__(owner=lc, path="children")
        self._q_lc = lc

    def _q_items(self):
        lc = self._q_lc
        return [lc._q_vl._q_layer(lc._q_cpath + (child,)) for child in lc._q_coll._q_children]

    def _q_key(self, item):
        return item._q_coll._q_name


class LayerObjects(PropCollection):

    def __init__(self, vl: "ViewLayer") -> None:
        super().__init__(owner=vl, path="objects")
        self._q_vl = vl

    def _q_items(self):
        return self._q_vl._q_objects()

    def _q_key(self, item):
        return item._q_name

    @property
    def active(self):
        ob = self._q_vl._q_active_object
        if ob is not None and (getattr(type(ob), "_q_removed", False) or self._q_vl.q_base(ob) is None):
            return None
        return ob

    @active.setter
    def active(self, value) -> None:
        vl = self._q_vl
        if value is not None:
            if getattr(type(value), "_q_removed", False):
                value.name
            if not isinstance(value, Object) or vl.q_base(value) is None:
                raise PropertyValueError(f"ViewLayer '{vl._q_name}': object "
                                         f"'{getattr(value, '_q_name', value)}' not in View Layer")
        vl._q_active_object = value
        if value is not None:
            value.q_tag("SELECT")
        vl._q_scene.q_tag("SELECT")

    @property
    def selected(self) -> tuple:
        vl = self._q_vl
        return tuple(ob for ob in vl._q_objects() if vl._q_bases.get(ob, (False, False))[0])


def _vl_get_name(self):
    return self._q_name


def _vl_set_name(self, value):
    scene = self._q_scene
    new = unique_name(value, lambda n: any(v._q_name == n for v in scene._q_view_layers if v is not self),
                      default="ViewLayer")
    self._q_name = new
    self._q_path = _vl_path(new)


def _vl_path(name: str) -> str:
    return f'view_layers["{escape_identifier(name)}"]'


def _vl_layer_collection(self):
    return self._q_layer(())


def _vl_depsgraph(self):
    return depsgraph_for(self._q_scene, self)


@builtin_struct
class ViewLayer(Struct):

    _q_strict_attrs = True

    name: StringProperty(maxlen=64, options=set(), meta={"virtual_get": _vl_get_name, "virtual_set": _vl_set_name})
    use: BoolProperty(default=True, meta=_VIS)
    layer_collection: PointerProperty(type=LayerCollection, options=set(),
                                      meta={"virtual_get": _vl_layer_collection})
    depsgraph: PointerProperty(type=Depsgraph, options={"HIDDEN"}, meta={"virtual_get": _vl_depsgraph})

    @classmethod
    def _q_create(cls, scene, name: str) -> "ViewLayer":
        vl = cls._q_new_child(owner=scene, path=_vl_path(name))
        object.__setattr__(vl, "_q_scene", scene)
        object.__setattr__(vl, "_q_name", name)
        object.__setattr__(vl, "_q_bases", {})
        object.__setattr__(vl, "_q_flags", {})
        object.__setattr__(vl, "_q_lc_cache", {})
        object.__setattr__(vl, "_q_active_path", ())
        object.__setattr__(vl, "_q_active_object", None)
        object.__setattr__(vl, "_q_objects_coll", LayerObjects(vl))
        return vl

    def _q_flags_for(self, coll) -> list:
        flags = self._q_flags.get(coll)
        if flags is None:
            flags = [False, False, False, False]
            self._q_flags[coll] = flags
        return flags

    def _q_excluded(self, coll) -> bool:
        if coll is self._q_scene.collection:
            return False
        flags = self._q_flags.get(coll)
        return bool(flags[0]) if flags is not None else False

    def _q_layer(self, cpath: tuple) -> LayerCollection:
        lc = self._q_lc_cache.get(cpath)
        if lc is None:
            if cpath:
                parent = self._q_layer(cpath[:-1])
                lc = LayerCollection._q_new_child(owner=parent,
                                                  path=f'children["{escape_identifier(cpath[-1]._q_name)}"]')
                coll = cpath[-1]
            else:
                lc = LayerCollection._q_new_child(owner=self, path="layer_collection")
                coll = self._q_scene.collection
            object.__setattr__(lc, "_q_vl", self)
            object.__setattr__(lc, "_q_cpath", cpath)
            object.__setattr__(lc, "_q_coll", coll)
            self._q_lc_cache[cpath] = lc
        elif cpath:
            lc._q_path = f'children["{escape_identifier(cpath[-1]._q_name)}"]'
        return lc

    def _q_path_valid(self, cpath: tuple) -> bool:
        node = self._q_scene.collection
        for coll in cpath:
            if not any(c is coll for c in node._q_children):
                return False
            node = coll
        return True

    def _q_path_visible(self, cpath: tuple) -> bool:
        master = self._q_scene.collection
        chain = (master,) + tuple(cpath)
        for coll in chain:
            flags = self._q_flags.get(coll)
            if flags is not None:
                if coll is not master and flags[0]:
                    return False
                if flags[1]:
                    return False
            if coll._p.get("hide_viewport", False):
                return False
        return True

    def _q_objects(self) -> list:
        out: list = []
        seen: set[int] = set()
        visited: set[int] = set()

        def walk(coll):
            if id(coll) in visited:
                return
            visited.add(id(coll))
            for ob in coll._q_objects:
                if id(ob) not in seen:
                    seen.add(id(ob))
                    out.append(ob)
            for child in coll._q_children:
                if not self._q_excluded(child):
                    walk(child)
        walk(self._q_scene.collection)
        return out

    def _q_object_in_visible_layer(self, ob) -> bool:
        def walk(coll, cpath):
            if coll is not self._q_scene.collection and self._q_excluded(coll):
                return False
            if any(o is ob for o in coll._q_objects) and self._q_path_visible(cpath):
                return True
            return any(walk(child, cpath + (child,)) for child in coll._q_children)
        return walk(self._q_scene.collection, ())

    def q_base(self, ob):
        if not any(o is ob for o in self._q_objects()):
            self._q_bases.pop(ob, None)
            return None
        base = self._q_bases.get(ob)
        if base is None:
            base = [False, False]
            self._q_bases[ob] = base
        return (base[0], base[1])

    def _q_set_base(self, ob, index: int, value: bool) -> None:
        if self.q_base(ob) is None:
            raise LinkError(f"Object '{ob._q_name}' not in View Layer '{self._q_name}'")
        self._q_bases[ob][index] = bool(value)

    @property
    def objects(self) -> LayerObjects:
        return self._q_objects_coll

    @property
    def active_layer_collection(self) -> LayerCollection:
        if not self._q_path_valid(self._q_active_path):
            self._q_active_path = ()
        return self._q_layer(self._q_active_path)

    @active_layer_collection.setter
    def active_layer_collection(self, value) -> None:
        if not isinstance(value, LayerCollection) or value._q_vl is not self or not self._q_path_valid(value._q_cpath):
            raise PropertyValueError(f"ViewLayer.active_layer_collection: layer collection not in view layer "
                                     f"'{self._q_name}'")
        self._q_active_path = value._q_cpath

    def update(self) -> None:
        depsgraph_for(self._q_scene, self).update()

    def update_render_passes(self) -> None:
        return None

    def _q_state_dict(self) -> dict:
        master = self._q_scene.collection
        objects = self._q_objects()
        bases = [[ob, bool(self._q_bases[ob][0]), bool(self._q_bases[ob][1])]
                 for ob in objects if ob in self._q_bases]
        flags = [[None if coll is master else coll, *[bool(f) for f in vals]]
                 for coll, vals in self._q_flags.items()]
        active = self._q_active_object
        if active is not None and (getattr(type(active), "_q_removed", False) or
                                   not any(o is active for o in objects)):
            active = None
        return {"name": self._q_name, "p": Struct._q_state_get(self), "bases": bases, "active": active,
                "flags": flags, "active_path": list(self._q_active_path)}

    def _q_apply_state(self, state: dict) -> None:
        master = self._q_scene.collection
        self._q_name = str(state.get("name", self._q_name))
        self._q_path = _vl_path(self._q_name)
        Struct._q_state_set(self, state.get("p", {}))
        self._q_bases.clear()
        for ob, sel, hide in state.get("bases", ()):
            self._q_bases[ob] = [bool(sel), bool(hide)]
        self._q_flags.clear()
        for entry in state.get("flags", ()):
            coll = master if entry[0] is None else entry[0]
            self._q_flags[coll] = [bool(v) for v in entry[1:5]]
        self._q_active_object = state.get("active")
        self._q_active_path = tuple(state.get("active_path", ()))
        self._q_lc_cache.clear()


class ViewLayers(PropCollection):

    def __init__(self, scene: "Scene") -> None:
        super().__init__(owner=scene, path="view_layers")
        self._q_scene = scene

    def _q_items(self):
        return self._q_scene._q_view_layers

    def _q_key(self, item):
        return item._q_name

    def new(self, name: str) -> ViewLayer:
        scene = self._q_scene
        if not isinstance(name, str):
            raise PropertyTypeError(f"ViewLayers.new(): error with argument 1, \"name\" - expected a string type, "
                                    f"not {type(name).__name__}")
        final = unique_name(name, lambda n: any(v._q_name == n for v in scene._q_view_layers), default="ViewLayer")
        vl = ViewLayer._q_create(scene, final)
        scene._q_view_layers.append(vl)
        scene.q_tag("HIERARCHY")
        return vl

    def remove(self, layer: ViewLayer) -> None:
        scene = self._q_scene
        if not any(v is layer for v in scene._q_view_layers):
            raise LinkError(f"ViewLayers.remove(): view layer '{getattr(layer, '_q_name', layer)}' not in scene "
                            f"'{scene._q_name}'")
        if len(scene._q_view_layers) <= 1:
            raise LinkError(f"ViewLayers.remove(): scene '{scene._q_name}' must have at least one view layer")
        scene._q_view_layers[:] = [v for v in scene._q_view_layers if v is not layer]
        scene.q_tag("HIERARCHY")

    def move(self, from_index: int, to_index: int) -> None:
        layers = self._q_scene._q_view_layers
        n = len(layers)
        if not (0 <= from_index < n) or not (0 <= to_index < n):
            raise IndexError(f"ViewLayers.move(): index out of range ({from_index} -> {to_index}, {n} items)")
        layers.insert(to_index, layers.pop(from_index))
        self._q_scene.q_tag("HIERARCHY")


class SceneObjects(PropCollection):

    def __init__(self, scene: "Scene") -> None:
        super().__init__(owner=scene, path="objects")
        self._q_scene = scene

    def _q_items(self):
        return list(self._q_scene.collection.all_objects)

    def _q_key(self, item):
        return item._q_name


class TimelineMarkers(PropCollection):

    def __init__(self, scene: "Scene") -> None:
        super().__init__(owner=scene, path="timeline_markers")

    def _q_items(self):
        return ()

    def new(self, name: str, frame: int = 1):
        raise NotImplementedInQuartz("TimelineMarkers.new")

    def remove(self, marker):
        raise NotImplementedInQuartz("TimelineMarkers.remove")

    def clear(self) -> None:
        return None


def _scene_collection(self):
    return self._q_master


def _get_frame_float(self):
    return float(_raw(self, "frame_current")) + float(_raw(self, "frame_subframe"))


def _set_frame_float(self, value):
    v = float(value)
    whole = _math.floor(v)
    Scene.__dict__["frame_current"].write_raw(self, int(max(-_FRAME_LIMIT, min(_FRAME_LIMIT, whole))))
    Scene.__dict__["frame_subframe"].write_raw(self, float(np.float32(v - whole)))




@builtin_struct
class Scene(ID):

    _q_strict_attrs = True

    camera: PointerProperty(type=Object, options=set(), meta={"counts_user": False})
    world: PointerProperty(type=World, options=set(), meta={"dirty": "SHADING"})
    collection: PointerProperty(type=Collection, options=set(), meta={"virtual_get": _scene_collection,
                                                                      "counts_user": False})
    frame_current: IntProperty(subtype="TIME", default=1, min=-_FRAME_LIMIT, max=_FRAME_LIMIT, options=set())
    frame_subframe: FloatProperty(subtype="TIME", unit="TIME", min=0.0, max=1.0, step=0.01, precision=2,
                                  options=set())
    frame_float: FloatProperty(subtype="TIME", unit="TIME", min=-float(_FRAME_LIMIT), max=float(_FRAME_LIMIT),
                               step=0.1, precision=2, options=set(),
                               meta={"virtual_get": _get_frame_float, "virtual_set": _set_frame_float})
    frame_start: IntProperty(subtype="TIME", default=1, min=0, max=_FRAME_LIMIT, options=set())
    frame_end: IntProperty(subtype="TIME", default=250, min=0, max=_FRAME_LIMIT, options=set())
    frame_step: IntProperty(subtype="TIME", default=1, min=0, max=_FRAME_LIMIT, soft_min=1, soft_max=100,
                            options=set())
    frame_current_final: FloatProperty(subtype="TIME", unit="TIME", min=-float(_FRAME_LIMIT),
                                       max=float(_FRAME_LIMIT), step=10.0, precision=3, options=set(),
                                       meta={"virtual_get": _get_frame_float})
    use_preview_range: BoolProperty(options=set())
    frame_preview_start: IntProperty(subtype="TIME", soft_min=-10000, soft_max=10000, options=set())
    frame_preview_end: IntProperty(subtype="TIME", soft_min=-10000, soft_max=10000, options=set())
    use_nodes: BoolProperty()
    tool_settings: PointerProperty(type=ToolSettings)
    unit_settings: PointerProperty(type=UnitSettings)
    gravity: FloatVectorProperty(subtype="ACCELERATION", unit="ACCELERATION", size=3, default=(0.0, 0.0, -9.81),
                                 soft_min=-200.0, soft_max=200.0, step=1.0, precision=2)
    use_gravity: BoolProperty(default=True)
    render: PointerProperty(type=RenderSettings)
    cursor: PointerProperty(type=View3DCursor)

    @classmethod
    def _q_construct(cls, name: str):
        inst = super()._q_construct(name)
        master = Collection._q_construct("Scene Collection")
        object.__setattr__(master, "_q_embedded_owner", inst)
        object.__setattr__(inst, "_q_master", master)
        object.__setattr__(inst, "_q_view_layers", [])
        object.__setattr__(inst, "_q_view_layers_coll", ViewLayers(inst))
        object.__setattr__(inst, "_q_objects_coll", SceneObjects(inst))
        object.__setattr__(inst, "_q_markers_coll", TimelineMarkers(inst))
        inst._q_view_layers.append(ViewLayer._q_create(inst, "ViewLayer"))
        return inst

    @property
    def objects(self) -> SceneObjects:
        return self._q_objects_coll

    @property
    def view_layers(self) -> ViewLayers:
        return self._q_view_layers_coll

    @property
    def timeline_markers(self) -> TimelineMarkers:
        return self._q_markers_coll

    @property
    def animation_data(self):
        return None

    def frame_set(self, frame: int, subframe: float = 0.0) -> None:
        if isinstance(frame, bool):
            frame = int(frame)
        if not isinstance(frame, (int, np.integer)):
            raise PropertyTypeError(f"Scene.frame_set(): error with argument 1, \"frame\" - expected an int type, "
                                    f"not {type(frame).__name__}")
        frame = int(max(-_FRAME_LIMIT, min(_FRAME_LIMIT, int(frame))))
        sub = float(np.float32(max(0.0, min(1.0, float(subframe)))))
        Scene.__dict__["frame_current"].write_raw(self, frame)
        Scene.__dict__["frame_subframe"].write_raw(self, sub)
        vl = None
        ctx = hooks.current_context()
        if ctx is not None and getattr(ctx, "scene", None) is self:
            cand = getattr(ctx, "view_layer", None)
            if cand is not None and any(v is cand for v in self._q_view_layers):
                vl = cand
        if vl is None:
            vl = self._q_view_layers[0]
        dg = depsgraph_for(self, vl)
        handlers.dispatch("frame_change_pre", self, dg)
        dg.update()
        handlers.dispatch("frame_change_post", self, dg)

    def statistics(self, view_layer) -> str:
        objects = view_layer._q_objects()
        sel = sum(1 for ob in objects if view_layer._q_bases.get(ob, (False, False))[0])
        text = f"{view_layer._q_name} | Objects:{sel}/{len(objects)}"
        verts = faces = 0
        has_geo = False
        for ob in objects:
            data = ob._p.get("data")
            geo = getattr(data, "q_geometry", None) if data is not None else None
            if geo is not None:
                has_geo = True
                verts += int(geo.num_verts)
                faces += int(geo.num_faces)
        if has_geo:
            text += f" | Verts:{verts} | Faces:{faces}"
        return text

    def ray_cast(self, depsgraph, origin, direction, distance: float = 1.70141e+38):
        best = None
        origin_a = np.asarray(origin, dtype=np.float64).ravel()
        for ob in depsgraph.objects:
            data = ob._p.get("data")
            geo = getattr(data, "q_geometry", None) if data is not None else None
            if geo is None:
                continue
            mw = np.array(ob.matrix_world, dtype=np.float64)
            positions = _transform_points(np.asarray(geo.positions, dtype=np.float64), mw)
            tris, tri_face = _geo_triangulate(geo)
            if len(tris) == 0:
                continue
            tri_verts = np.asarray(geo.corner_verts)[np.asarray(tris, dtype=np.int64)]
            bvh = BVHTree._q_from_triangles(positions, tri_verts, tri_face)
            loc, normal, index, _d = bvh.ray_cast(origin, direction, distance)
            if loc is None:
                continue
            dist = float(np.linalg.norm(np.array(loc, dtype=np.float64) - origin_a))
            if best is None or dist < best[0]:
                best = (dist, loc, normal, index, ob, Matrix(mw.tolist()))
        if best is None:
            return (False, Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0)), -1, None, Matrix.Identity(4))
        return (True, best[1], best[2], best[3], best[4], best[5])

    def update_render_engine(self) -> None:
        return None

    def sequence_editor_create(self):
        raise NotImplementedInQuartz("Scene.sequence_editor_create")

    def sequence_editor_clear(self):
        raise NotImplementedInQuartz("Scene.sequence_editor_clear")

    def uvedit_aspect(self, object):
        raise NotImplementedInQuartz("Scene.uvedit_aspect")

    def _q_refs(self):
        yield from _q_relabel_refs(super()._q_refs(), self, self._p.get("world"), "WORLD")
        yield from self._q_master._q_refs()

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        state["collection"] = self._q_master._q_state_get()
        state["view_layers"] = [vl._q_state_dict() for vl in self._q_view_layers]
        return state

    def _q_state_set(self, state: dict) -> None:
        super()._q_state_set(state)
        master = self._q_master
        ID._q_revive(master)
        if "collection" in state:
            master._q_state_set(state["collection"])
        if "view_layers" in state:
            old = list(self._q_view_layers)
            layers = []
            for i, vs in enumerate(state["view_layers"]):
                vl = old[i] if i < len(old) else ViewLayer._q_create(self, str(vs.get("name", "ViewLayer")))
                vl._q_apply_state(vs)
                layers.append(vl)
            self._q_view_layers[:] = layers


class BlendDataScenes(IDCollection):

    def new(self, name: str) -> Scene:
        return super().new(name)

    def remove(self, scene: Scene, do_unlink: bool = True) -> None:
        if isinstance(scene, Scene) and not getattr(type(scene), "_q_removed", False) and \
                any(s is scene for s in self._q_list) and len(self._q_list) <= 1:
            raise LinkError(f"BlendDataScenes.remove(): scene '{scene._q_name}' is the last scene, "
                            f"it can not be removed")
        super().remove(scene, do_unlink)


register_id_type(Scene, id_type="SCENE", collection="scenes", default_name="Scene", collection_cls=BlendDataScenes)

