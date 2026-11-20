import itertools
from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterator

from quartz.errors import (NotImplementedInQuartz, PropertyTypeError, PropertyValueError, RegistrationError,
                           RemovedStructError)
from quartz.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from quartz.rna import IDRef, PointerDef, Struct, builtin_struct, hooks, iter_properties
from quartz.rna.collections import GroupCollection
from quartz.types.naming import plan_rename, truncate_utf8, unique_name

__all__ = [
    "DIRTY_CHANNELS", "ID_TYPE_ITEMS", "dirty_clock", "dirty_tick",
    "ID", "IDTypeInfo", "register_id_type", "id_type_info", "iter_id_types", "removed_class_for",
]

DIRTY_CHANNELS: tuple[str, ...] = ("DATA", "TRANSFORM", "GEOMETRY", "SHADING", "SELECT", "HIERARCHY", "VISIBILITY")

ID_TYPE_ITEMS: tuple[str, ...] = (
    "ACTION", "ARMATURE", "BRUSH", "CACHEFILE", "CAMERA", "COLLECTION", "CURVE", "CURVES", "FONT", "GREASEPENCIL",
    "GREASEPENCIL_V3", "IMAGE", "KEY", "LATTICE", "LIBRARY", "LIGHT", "LIGHT_PROBE", "LINESTYLE", "MASK",
    "MATERIAL", "MESH", "META", "MOVIECLIP", "NODETREE", "OBJECT", "PAINTCURVE", "PALETTE", "PARTICLE",
    "POINTCLOUD", "SCENE", "SCREEN", "SOUND", "SPEAKER", "TEXT", "TEXTURE", "VOLUME", "WINDOWMANAGER", "WORKSPACE",
    "WORLD",
)

_UI_ID_TYPES = frozenset({"WINDOWMANAGER", "SCREEN", "WORKSPACE"})
_UPDATE_TAG_ITEMS = ("OBJECT", "DATA", "TIME")

_clock: int = 0
_uid_counter = itertools.count(1)


def dirty_clock() -> int:
    return _clock


def dirty_tick() -> int:
    global _clock
    _clock += 1
    return _clock


def _get_name(self):
    return self._q_name


def _set_name(self, value):
    self.rename(value, mode="NEVER")


def _get_id_type(self):
    return type(self).q_id_type or "ACTION"


def _get_session_uid(self):
    return self._q_session_uid


def _get_users(self):
    main = self._q_main
    count = main.q_users_of(self) if main is not None else 0
    return count + int(bool(self.use_fake_user))


def _false(self):
    return False


def _true(self):
    return True


def _get_embedded(self):
    return self._q_embedded_owner is not None


def _api_prefix() -> str:
    from quartz.app.settings import settings
    return settings.api_prefix


def _q_owner_id(owner: object) -> object:
    node = owner
    if not getattr(type(node), "_q_is_id", False):
        node = getattr(node, "id_data", None)
    if node is None:
        return None
    emb = getattr(node, "_q_embedded_owner", None)
    return emb if emb is not None else node


def _q_relabel_refs(refs, owner: object, target: object, kind: str):
    done = target is None
    for ref in refs:
        if not done and ref.owner is owner and ref.target is target:
            ref = ref._replace(kind=kind)
            done = True
        yield ref


@builtin_struct(identifier="ID")
class ID(Struct):

    _q_strict_attrs = True
    _q_is_id = True
    _q_removed = False
    _q_embedded_owner = None
    q_id_type = ""
    q_schema_version = 1

    name: StringProperty(maxlen=256, meta={"virtual_get": _get_name, "virtual_set": _set_name})
    name_full: StringProperty(maxlen=516, meta={"virtual_get": _get_name})
    id_type: EnumProperty(items=[(t, t, "") for t in ID_TYPE_ITEMS], default="ACTION",
                          meta={"virtual_get": _get_id_type})
    session_uid: IntProperty(soft_min=-10000, soft_max=10000, meta={"virtual_get": _get_session_uid})
    is_evaluated: BoolProperty(meta={"virtual_get": _false})
    users: IntProperty(subtype="UNSIGNED", min=0, soft_max=10000, meta={"virtual_get": _get_users})
    use_fake_user: BoolProperty()
    use_extra_user: BoolProperty()
    is_embedded_data: BoolProperty(meta={"virtual_get": _get_embedded})
    is_linked_packed: BoolProperty(meta={"virtual_get": _false})
    is_missing: BoolProperty(meta={"virtual_get": _false})
    is_runtime_data: BoolProperty(meta={"virtual_get": _false})
    is_editable: BoolProperty(meta={"virtual_get": _true})
    tag: BoolProperty()
    is_library_indirect: BoolProperty(meta={"virtual_get": _false})

    def __new__(cls, *args, **kwargs):
        raise TypeError(f"bpy_struct.__new__(type): {cls.__name__} can not be created directly, "
                        f"use the data-block collections")

    @property
    def original(self):
        return self

    @property
    def library(self):
        return None

    @property
    def library_weak_reference(self):
        return None

    @property
    def asset_data(self):
        return None

    @property
    def override_library(self):
        return None

    @property
    def preview(self):
        return None

    @property
    def q_dirty(self):
        return MappingProxyType(self._q_stamps)

    def q_tag(self, *channels: str) -> None:
        chans = channels or ("DATA",)
        for ch in chans:
            if ch not in DIRTY_CHANNELS:
                raise PropertyValueError(f"unknown dirty channel '{ch}'")
        stamp = dirty_tick()
        stamps = self._q_stamps
        for ch in chans:
            stamps[ch] = stamp

    def q_dirty_since(self, stamp: int) -> frozenset:
        return frozenset(ch for ch, s in self._q_stamps.items() if s > stamp)

    def _q_on_change(self, pdef) -> None:
        self.q_tag(pdef.meta.get("dirty", "DATA"))

    def _q_info(self):
        return id_type_info(type(self))

    def _q_default_name(self) -> str:
        info = self._q_info()
        return info.default_name if info is not None else type(self).bl_rna.identifier

    def _q_collection(self):
        main = self._q_main
        if main is None:
            return None
        return main.q_collection_for(self)

    def rename(self, name: str, *, mode: str = "NEVER") -> str:
        if not isinstance(name, str):
            raise PropertyTypeError(f"ID.rename(): error with argument 1, \"name\" - expected a string type, "
                                    f"not {type(name).__name__}")
        default = self._q_default_name()
        if self._q_embedded_owner is not None:
            plan_rename(self._q_name, self._q_name, lambda n: False, mode=mode, default=default)
            return "UNCHANGED"
        coll = self._q_collection()
        if coll is None or self not in coll._q_items():
            result, new, _ = plan_rename(self._q_name, name, lambda n: False, mode=mode, default=default)
            if result != "UNCHANGED":
                self._q_name = new
                self.q_tag("DATA")
            return result
        result, new, other_new = plan_rename(self._q_name, name, lambda n: coll._q_taken(n, self), mode=mode,
                                             default=default)
        if result in ("UNCHANGED", "UNCHANGED_COLLISION"):
            return result
        if other_new is not None:
            other = coll._q_by_name(new, exclude=self)
            if other is not None:
                other._q_name = other_new
                coll._q_reposition(other)
                other.q_tag("DATA")
        self._q_name = new
        coll._q_reposition(self)
        self.q_tag("DATA")
        return result

    def copy(self):
        if self._q_main is None or self._q_embedded_owner is not None or type(self).q_id_type in _UI_ID_TYPES:
            raise NotImplementedInQuartz("ID.copy")
        coll = self._q_collection()
        if coll is None:
            raise NotImplementedInQuartz("ID.copy")
        new_name = unique_name(self._q_name, lambda n: coll._q_taken(n, None), default=self._q_default_name())
        new = type(self)._q_construct(new_name)
        self._q_copy_into(new)
        coll._q_link(new)
        new.q_tag(*DIRTY_CHANNELS)
        return new

    def evaluated_get(self, depsgraph):
        return self

    def user_clear(self) -> None:
        main = self._q_main
        if main is not None:
            for ref in main.q_refs_to(self):
                ref.clear()
        self.use_fake_user = False

    def user_remap(self, new_id) -> None:
        if not getattr(type(new_id), "_q_is_id", False):
            raise PropertyTypeError(f"ID.user_remap(): error with argument 1, \"new_id\" - expected an ID type, "
                                    f"not {type(new_id).__name__}")
        if type(new_id)._q_removed:
            new_id.name
        if type(new_id).q_id_type != type(self).q_id_type:
            raise PropertyValueError(f"ID.user_remap(): new_id '{new_id._q_name}' must be of the same type "
                                     f"as '{self._q_name}'")
        if new_id is self:
            return
        main = self._q_main
        if main is None:
            return
        for ref in main.q_refs_to(self):
            ref.remap(new_id)

    def user_of_id(self, id) -> int:
        return sum(1 for ref in self._q_refs() if ref.target is id)

    def make_local(self, *, clear_proxy: bool = True, clear_liboverride: bool = False,
                   clear_asset_data: bool = True):
        return self

    def update_tag(self, *, refresh: set = frozenset()) -> None:
        items = set(refresh)
        for item in items:
            if item not in _UPDATE_TAG_ITEMS:
                listing = ", ".join(repr(i) for i in _UPDATE_TAG_ITEMS)
                raise PropertyTypeError(f'ID.update_tag(): error with keyword argument "refresh" - '
                                        f'enum "{item}" not found in ({listing})')
        if "OBJECT" in items:
            self.q_tag("DATA", "TRANSFORM")
        else:
            self.q_tag("DATA")

    def animation_data_create(self):
        raise NotImplementedInQuartz("ID.animation_data_create")

    def animation_data_clear(self) -> None:
        return None

    def asset_mark(self):
        raise NotImplementedInQuartz("ID.asset_mark")

    def asset_clear(self):
        raise NotImplementedInQuartz("ID.asset_clear")

    def asset_generate_preview(self):
        raise NotImplementedInQuartz("ID.asset_generate_preview")

    def preview_ensure(self):
        raise NotImplementedInQuartz("ID.preview_ensure")

    def override_create(self, *a, **k):
        raise NotImplementedInQuartz("ID.override_create")

    def override_hierarchy_create(self, *a, **k):
        raise NotImplementedInQuartz("ID.override_hierarchy_create")

    def __repr__(self) -> str:
        owner = self._q_embedded_owner
        if owner is not None:
            return f"{repr(owner)}.collection"
        info = self._q_info()
        if self._q_main is not None and info is not None:
            return f"{hooks.repr_root()}.data.{info.collection}['{self._q_name}']"
        return f'<bpy_struct, {type(self).bl_rna.identifier}("{self._q_name}") at 0x{id(self):016X}>'

    @classmethod
    def _q_construct(cls, name: str):
        inst = Struct.__new__(cls)
        object.__setattr__(inst, "_q_session_uid", next(_uid_counter))
        object.__setattr__(inst, "_q_name", truncate_utf8(str(name)))
        inst._q_main = None
        object.__setattr__(inst, "_q_stamps", {ch: 0 for ch in DIRTY_CHANNELS})
        return inst

    def _q_copy_into(self, new) -> None:
        state = self._q_state_get()
        state.pop("name", None)
        new._q_state_set(state)

    def _q_refs(self) -> Iterator[IDRef]:
        for pdef in iter_properties(self):
            if not isinstance(pdef, PointerDef) or not pdef.is_id_pointer:
                continue
            if pdef.meta.get("virtual_get") is not None:
                continue
            target = pdef.read_raw(self)
            if target is None:
                continue
            yield IDRef(target, self, "POINTER", pdef.counts_user, pdef.on_remove, *_raw_closures(self, pdef))
        for pdef in iter_properties(self):
            if pdef.kind not in ("POINTER", "COLLECTION") or getattr(pdef, "is_id_pointer", False):
                continue
            val = self._p.get(pdef.identifier)
            if isinstance(val, GroupCollection):
                for item in val:
                    yield from item._q_refs()
            elif isinstance(val, Struct):
                yield from val._q_refs()

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        state["name"] = self._q_name
        return state

    def _q_state_set(self, state: dict) -> None:
        old = self._q_name
        if "name" in state:
            self._q_name = str(state["name"])
        super()._q_state_set(state)
        if self._q_name != old:
            coll = self._q_collection()
            if coll is not None and self in coll._q_items():
                coll._q_reposition(self)

    def _q_tombstone(self) -> None:
        cls = type(self)
        if cls._q_removed:
            return
        self.__class__ = removed_class_for(cls)

    @staticmethod
    def _q_revive(obj) -> None:
        cls = type(obj)
        if cls._q_removed:
            obj.__class__ = cls._q_live_class

    @classmethod
    def q_upgrade(cls, state: dict, from_version: int) -> dict:
        return state


def _raw_closures(owner, pdef):
    def clear():
        pdef.write_raw(owner, None)
        owner._q_on_change(pdef)

    def remap(new):
        pdef.write_raw(owner, new)
        owner._q_on_change(pdef)
    return clear, remap


_REMOVED: dict[type, type] = {}


def removed_class_for(cls: type) -> type:
    live = cls._q_live_class if getattr(cls, "_q_removed", False) else cls
    cached = _REMOVED.get(live)
    if cached is not None:
        return cached
    ident = live.bl_rna.identifier
    message = f"StructRNA of type {ident} has been removed"

    def __getattribute__(self, name):
        if name.startswith("__") and name.endswith("__"):
            return object.__getattribute__(self, name)
        raise RemovedStructError(message)

    def __setattr__(self, name, value):
        if name.startswith("__") and name.endswith("__"):
            object.__setattr__(self, name, value)
            return
        raise RemovedStructError(message)

    def __delattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            object.__delattr__(self, name)
            return
        raise RemovedStructError(message)

    def __repr__(self):
        return f"<bpy_struct, {ident} invalid>"

    namespace = {
        "__module__": live.__module__,
        "__qualname__": live.__qualname__,
        "__getattribute__": __getattribute__,
        "__setattr__": __setattr__,
        "__delattr__": __delattr__,
        "__repr__": __repr__,
        "__hash__": object.__hash__,
        "__eq__": object.__eq__,
        "__ne__": object.__ne__,
        "_q_removed": True,
        "_q_live_class": live,
    }
    tomb = type(live)(live.__name__, (live,), namespace)
    _REMOVED[live] = tomb
    return tomb


@dataclass(frozen=True)
class IDTypeInfo:
    cls: type
    id_type: str
    collection: str
    default_name: str
    collection_cls: type | None = None


_REGISTRY: list[IDTypeInfo] = []


def register_id_type(cls: type, *, id_type: str, collection: str, default_name: str,
                     collection_cls: type | None = None) -> None:
    if id_type not in ID_TYPE_ITEMS:
        raise RegistrationError(f"register_id_type: unknown id_type '{id_type}'")
    info = IDTypeInfo(cls, id_type, collection, default_name, collection_cls)
    for existing in _REGISTRY:
        if existing.cls is cls:
            if existing == info:
                type.__setattr__(cls, "q_id_type", id_type)
                return
            raise RegistrationError(f"register_id_type: class {cls.__name__} already registered as "
                                    f"'{existing.id_type}'")
        if existing.id_type == id_type or existing.collection == collection:
            raise RegistrationError(f"register_id_type: id_type '{id_type}' / collection '{collection}' "
                                    f"already registered by {existing.cls.__name__}")
    type.__setattr__(cls, "q_id_type", id_type)
    _REGISTRY.append(info)


def id_type_info(key) -> IDTypeInfo | None:
    if isinstance(key, type):
        klass = key._q_live_class if getattr(key, "_q_removed", False) else key
        for base in klass.__mro__:
            for info in _REGISTRY:
                if info.cls is base:
                    return info
        return None
    if isinstance(key, str):
        for info in _REGISTRY:
            if info.id_type == key:
                return info
        for info in _REGISTRY:
            if info.collection == key:
                return info
    return None


def iter_id_types() -> Iterator[IDTypeInfo]:
    return iter(list(_REGISTRY))


def _q_registry_snapshot() -> object:
    return [(info, info.cls.__dict__.get("q_id_type")) for info in _REGISTRY]


def _q_registry_restore(snap: object) -> None:
    kept = {id(info.cls) for info, _ in snap}
    for info in _REGISTRY:
        if id(info.cls) not in kept and "q_id_type" in info.cls.__dict__:
            type.__delattr__(info.cls, "q_id_type")
    _REGISTRY[:] = [info for info, _ in snap]
    for info, value in snap:
        if value is not None:
            type.__setattr__(info.cls, "q_id_type", value)
