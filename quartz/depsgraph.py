import zlib

import numpy as np

from quartz.app import handlers
from quartz.errors import PropertyTypeError, PropertyValueError
from quartz.props import (BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, IntVectorProperty,
                          PointerProperty)
from quartz.rna import Struct, builtin_struct
from quartz.types.id import ID, ID_TYPE_ITEMS, dirty_clock
from quartz.types.object import Object
import quartz.types.world

__all__ = ["UPDATE_FLAG_CHANNELS", "Depsgraph", "DepsgraphUpdate", "DepsgraphObjectInstance", "depsgraph_for"]

UPDATE_FLAG_CHANNELS: dict[str, str] = {"is_updated_transform": "TRANSFORM", "is_updated_geometry": "GEOMETRY",
                                        "is_updated_shading": "SHADING"}


def _dg_scene(self):
    return self._q_scene


def _dg_view_layer(self):
    return self._q_view_layer


def _dg_mode(self):
    return "VIEWPORT"


@builtin_struct
class Depsgraph(Struct):

    _q_strict_attrs = True

    mode: EnumProperty(items=[("VIEWPORT", "Viewport", ""), ("RENDER", "Render", "")], default="VIEWPORT",
                       meta={"virtual_get": _dg_mode})
    scene: PointerProperty(type=ID, options=set(), meta={"virtual_get": _dg_scene, "fixed_type_name": "Scene",
                                                         "counts_user": False})
    view_layer: PointerProperty(type=Struct, options=set(), meta={"virtual_get": _dg_view_layer,
                                                                  "fixed_type_name": "ViewLayer"})
    scene_eval: PointerProperty(type=ID, options=set(), meta={"virtual_get": _dg_scene, "fixed_type_name": "Scene",
                                                              "counts_user": False})
    view_layer_eval: PointerProperty(type=Struct, options=set(), meta={"virtual_get": _dg_view_layer,
                                                                       "fixed_type_name": "ViewLayer"})

    def _q_reachable(self) -> list:
        scene = self._q_scene
        vl = self._q_view_layer
        out: list = []
        seen: set[int] = set()

        def add(x):
            if x is not None and getattr(type(x), "_q_is_id", False) and id(x) not in seen:
                seen.add(id(x))
                out.append(x)
        add(scene)
        add(scene._p.get("world"))
        master = scene.collection
        add(master)
        for coll in master.children_recursive:
            add(coll)
        for ob in vl.objects:
            add(ob)
            data = ob._p.get("data")
            if data is not None and getattr(type(data), "_q_is_id", False):
                add(data)
                mats = getattr(data, "materials", None)
                if mats is not None:
                    for m in list(mats):
                        add(m)
        return out

    @property
    def ids(self) -> tuple:
        return tuple(self._q_reachable())

    @property
    def objects(self) -> tuple:
        vl = self._q_view_layer
        return tuple(ob for ob in vl.objects if ob.visible_get(vl))

    @property
    def object_instances(self) -> tuple:
        out = []
        for i, ob in enumerate(self.objects):
            inst = DepsgraphObjectInstance._q_new_child(owner=self, path=f"object_instances[{i}]")
            object.__setattr__(inst, "_q_object", ob)
            object.__setattr__(inst, "_q_index", i)
            object.__setattr__(inst, "_q_matrix", np.array(ob.matrix_world, dtype=np.float32))
            out.append(inst)
        return tuple(out)

    @property
    def updates(self) -> tuple:
        return self._q_updates

    def update(self) -> None:
        now = dirty_clock()
        last = self._q_last_stamp
        reachable = self._q_reachable()
        changed = {id(x): x.q_dirty_since(last) for x in reachable}
        self._q_last_stamp = now
        if not any(changed.values()):
            return
        scene = self._q_scene
        handlers.dispatch("depsgraph_update_pre", scene, self)
        updates = []
        for x in reachable:
            chans = set(changed[id(x)])
            include = bool(chans)
            if isinstance(x, Object):
                data = x._p.get("data")
                if data is not None and id(data) in changed:
                    extra = changed[id(data)] & {"GEOMETRY", "SHADING"}
                    if extra:
                        chans |= extra
                        include = True
                node = x._p.get("parent")
                guard: set[int] = set()
                while node is not None and id(node) not in guard:
                    guard.add(id(node))
                    if node.q_dirty_since(last) & {"TRANSFORM", "HIERARCHY"}:
                        chans.add("TRANSFORM")
                        include = True
                        break
                    node = node._p.get("parent")
            if not include:
                continue
            upd = DepsgraphUpdate._q_new_child(owner=self, path=f"updates[{len(updates)}]")
            object.__setattr__(upd, "_q_id", x)
            object.__setattr__(upd, "_q_flags", frozenset(f for f, ch in UPDATE_FLAG_CHANNELS.items() if ch in chans))
            updates.append(upd)
        self._q_updates = tuple(updates)
        handlers.dispatch("depsgraph_update_post", scene, self)

    def id_eval_get(self, id):
        return id

    def id_type_updated(self, id_type: str) -> bool:
        if id_type not in ID_TYPE_ITEMS:
            listing = ", ".join(repr(t) for t in ID_TYPE_ITEMS)
            raise PropertyTypeError(f'Depsgraph.id_type_updated(): error with argument 1, "id_type" - '
                                    f'enum "{id_type}" not found in ({listing})')
        return any(type(u._q_id).q_id_type == id_type for u in self._q_updates)

    def debug_relations_graphviz(self, filepath: str = "") -> str:
        lines = ["digraph depsgraph {\n"]
        for x in self._q_reachable():
            lines.append(f'  "{x._q_name}";\n')
        lines.append("}\n")
        return "".join(lines)

    def debug_stats_gnuplot(self, filepath: str, output_filepath: str) -> None:
        return None

    def debug_tag_update(self) -> None:
        for x in self._q_reachable():
            x.q_tag("DATA")

    def debug_stats(self) -> str:
        return f"Approximate {len(self._q_reachable())} IDs, {len(self.objects)} objects"


def _upd_id(self):
    return self._q_id


def _flag_getter(flag: str):
    def getter(self):
        return flag in self._q_flags
    return getter


@builtin_struct
class DepsgraphUpdate(Struct):

    _q_strict_attrs = True

    id: PointerProperty(type=ID, options=set(), meta={"virtual_get": _upd_id, "counts_user": False})
    is_updated_transform: BoolProperty(options=set(), meta={"virtual_get": _flag_getter("is_updated_transform")})
    is_updated_geometry: BoolProperty(options=set(), meta={"virtual_get": _flag_getter("is_updated_geometry")})
    is_updated_shading: BoolProperty(options=set(), meta={"virtual_get": _flag_getter("is_updated_shading")})


def _inst_object(self):
    return self._q_object


def _none(self):
    return None


def _false(self):
    return False


def _true(self):
    return True


def _inst_matrix(self):
    return self._q_matrix


def _inst_persistent_id(self):
    return np.array([self._q_index, 0, 0, 0, 0, 0, 0, 0], dtype=np.int32)


def _inst_random_id(self):
    value = zlib.crc32(f"{self._q_object._q_name}:{self._q_index}".encode("utf-8"))
    return int(value & 0x7FFFFFFF)


def _zeros2(self):
    return np.zeros(2, dtype=np.float32)


def _zeros3(self):
    return np.zeros(3, dtype=np.float32)


@builtin_struct
class DepsgraphObjectInstance(Struct):

    _q_strict_attrs = True

    object: PointerProperty(type=Object, options=set(), meta={"virtual_get": _inst_object, "counts_user": False})
    instance_object: PointerProperty(type=Object, options=set(), meta={"virtual_get": _none, "counts_user": False})
    parent: PointerProperty(type=Object, options=set(), meta={"virtual_get": _none, "counts_user": False})
    is_instance: BoolProperty(options=set(), meta={"virtual_get": _false})
    show_self: BoolProperty(options=set(), meta={"virtual_get": _true})
    show_particles: BoolProperty(options=set(), meta={"virtual_get": _false})
    matrix_world: FloatVectorProperty(subtype="MATRIX", size=(4, 4), options=set(), meta={"virtual_get": _inst_matrix})
    persistent_id: IntVectorProperty(size=8, options=set(), meta={"virtual_get": _inst_persistent_id})
    random_id: IntProperty(options=set(), meta={"virtual_get": _inst_random_id})
    uv: FloatVectorProperty(size=2, options=set(), meta={"virtual_get": _zeros2})
    orco: FloatVectorProperty(subtype="TRANSLATION", size=3, options=set(), meta={"virtual_get": _zeros3})


def depsgraph_for(scene, view_layer) -> Depsgraph:
    if not any(vl is view_layer for vl in scene.view_layers):
        raise PropertyValueError(f"depsgraph_for(): view layer '{getattr(view_layer, 'name', view_layer)}' "
                                 f"not in scene '{scene.name}'")
    dg = view_layer.__dict__.get("_q_depsgraph")
    if dg is None:
        dg = Depsgraph.__new__(Depsgraph)
        object.__setattr__(dg, "_q_scene", scene)
        object.__setattr__(dg, "_q_view_layer", view_layer)
        object.__setattr__(dg, "_q_last_stamp", dirty_clock())
        object.__setattr__(dg, "_q_updates", ())
        object.__setattr__(view_layer, "_q_depsgraph", dg)
    return dg
