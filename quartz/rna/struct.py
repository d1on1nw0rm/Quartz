from __future__ import annotations

from typing import Callable, ClassVar, NamedTuple

import numpy as np

from ..errors import NotImplementedInQuartz
from ..props import StringProperty, _PropertyDeferred
from . import annotations as _annotations
from . import hooks
from .properties import PropertyDef


class IDRef(NamedTuple):
    target: object
    owner: object
    kind: str
    counts_user: bool
    on_remove: str
    clear: Callable[[], None]
    remap: Callable[[object], None]


MISSING = object()


class StructMeta(type):
    def __setattr__(cls, name: str, value: object) -> None:
        if isinstance(value, _PropertyDeferred) and "bl_rna" in cls.__dict__:
            _annotations.define_property(cls, name, value)
            return
        type.__setattr__(cls, name, value)

    def __delattr__(cls, name: str) -> None:
        if isinstance(cls.__dict__.get(name), PropertyDef):
            _annotations.remove_property(cls, name)
            return
        type.__delattr__(cls, name)

    @property
    def is_registered(cls) -> bool:
        return "bl_rna" in cls.__dict__


def builtin_struct(cls=None, *, identifier=None):
    def wrap(c):
        _annotations.install_properties(c)
        type.__setattr__(c, "_q_builtin", True)
        from .rnainfo import RNAStruct
        type.__setattr__(c, "bl_rna", RNAStruct(c, identifier or c.__name__))
        return c

    if cls is None:
        return wrap
    return wrap(cls)


def _is_id(obj: object) -> bool:
    return bool(getattr(type(obj), "_q_is_id", False))


def _copy_plain(v):
    if isinstance(v, np.ndarray):
        return v.copy()
    if isinstance(v, list):
        return [_copy_plain(x) for x in v]
    if isinstance(v, tuple):
        return tuple(_copy_plain(x) for x in v)
    if isinstance(v, dict):
        return {k: _copy_plain(x) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return type(v)(v)
    return v


@builtin_struct
class Struct(metaclass=StructMeta):
    _q_strict_attrs: ClassVar[bool] = False
    _q_is_id: ClassVar[bool] = False
    _q_registrable: ClassVar[bool] = False

    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls)
        object.__setattr__(inst, "_p", {})
        object.__setattr__(inst, "_p_set", set())
        object.__setattr__(inst, "_q_idprops", None)
        object.__setattr__(inst, "_q_owner", None)
        object.__setattr__(inst, "_q_path", "")
        object.__setattr__(inst, "_q_key_order", [])
        return inst

    def __init__(self, *args, **kwargs):
        pass

    @property
    def rna_type(self):
        return type(self).bl_rna

    @property
    def id_data(self):
        if _is_id(self):
            return self
        owner = self._q_owner
        while owner is not None:
            if _is_id(owner):
                return owner
            owner = getattr(owner, "_q_owner", None)
        return None

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
        if type(self)._q_strict_attrs:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        object.__setattr__(self, name, value)

    def __repr__(self):
        idd = self.id_data
        if idd is not None and idd is not self:
            try:
                path = self.path_from_id()
            except ValueError:
                path = ""
            if path:
                return f"{repr(idd)}.{path}"
        return f"<bpy_struct, {type(self).__name__} at 0x{id(self):016X}>"

    def as_pointer(self):
        return id(self)

    def path_from_id(self, property=""):
        if _is_id(self):
            return property or ""
        if self.id_data is None:
            raise ValueError(f"{type(self).__name__}.path_from_id() does not support path creation for this type")
        parts = []
        node = self
        while node is not None and not _is_id(node):
            if node._q_path:
                parts.append(node._q_path)
            node = node._q_owner
        parts.reverse()
        if property:
            parts.append(property)
        return ".".join(parts)

    def path_from_module(self, property="", index=-1):
        root = hooks.repr_root()
        path = self.path_from_id(property)
        if index is not None and index >= 0:
            path = f"{path}[{index}]"
        idd = self.id_data
        base = repr(idd) if idd is not None else f"{root}.data"
        if not base.startswith(root + "."):
            base = f"{root}.data"
        return f"{base}.{path}" if path else base

    def path_resolve(self, path, coerce=True):
        from .datapath import resolve
        return resolve(self, path, coerce=coerce)

    def is_property_set(self, property, ghost=True):
        if property in self._p_set:
            return True
        return self._q_idprops is not None and property in self._q_idprops

    def property_unset(self, property):
        self._p.pop(property, None)
        self._p_set.discard(property)
        if self._q_idprops is not None and property in self._q_idprops:
            del self._q_idprops[property]
        if property in self._q_key_order:
            self._q_key_order.remove(property)

    def is_property_readonly(self, property):
        pdef = _annotations.get_property(self, property)
        return pdef.is_readonly if pdef is not None else False

    def is_property_hidden(self, property):
        pdef = _annotations.get_property(self, property)
        return pdef.is_hidden if pdef is not None else False

    def is_property_overridable_library(self, property):
        return False

    def property_overridable_library_set(self, property, overridable):
        return True

    def keys(self):
        idkeys = list(self._q_idprops.keys()) if self._q_idprops is not None else []
        if _is_id(self) or not isinstance(self, PropertyGroup):
            return idkeys
        res = [k for k in self._q_key_order if k in self._p_set or k in idkeys]
        res.extend(k for k in idkeys if k not in res)
        return res

    def values(self):
        return [self[k] for k in self.keys()]

    def items(self):
        return [(k, self[k]) for k in self.keys()]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, default=MISSING):
        if key in self:
            val = self[key]
            self.property_unset(key)
            return val
        if default is MISSING:
            raise KeyError(f'bpy_struct[key]: key "{key}" not found')
        return default

    def __getitem__(self, key):
        if isinstance(key, str) and key in self.keys():
            if self._q_idprops is not None and key in self._q_idprops:
                return self._q_idprops[key]
            if _annotations.get_property(self, key) is not None:
                return getattr(self, key)
        raise KeyError(f'bpy_struct[key]: key "{key}" not found')

    def __setitem__(self, key, value):
        if isinstance(self, PropertyGroup) and _annotations.get_property(self, key) is not None:
            setattr(self, key, value)
            return
        self.id_properties_ensure()[key] = value
        if key not in self._q_key_order:
            self._q_key_order.append(key)

    def __delitem__(self, key):
        if self._q_idprops is not None and key in self._q_idprops:
            del self._q_idprops[key]
            if key in self._q_key_order:
                self._q_key_order.remove(key)
            return
        if key in self._p_set:
            self.property_unset(key)
            return
        raise KeyError(f'bpy_struct[key]: key "{key}" not found')

    def __contains__(self, key):
        return key in self.keys()

    def id_properties_ensure(self):
        if self._q_idprops is None:
            from .idprops import IDPropertyGroup
            self._q_idprops = IDPropertyGroup(owner=self)
        return self._q_idprops

    def id_properties_clear(self):
        if self._q_idprops is not None:
            for k in list(self._q_idprops.keys()):
                if k in self._q_key_order:
                    self._q_key_order.remove(k)
        self._q_idprops = None

    def id_properties_ui(self, key):
        if self._q_idprops is None or key not in self._q_idprops:
            raise KeyError(f'bpy_struct[key]: key "{key}" not found')
        from .idprops import IDPropertyUIManager
        ui = self._q_idprops._ui
        if key not in ui:
            ui[key] = IDPropertyUIManager(self._q_idprops, key)
        return ui[key]

    def _q_written_values(self) -> dict:
        from .collections import GroupCollection
        out = {}
        for k, v in self._p.items():
            if k not in self._p_set:
                continue
            pdef = _annotations.get_property(self, k)
            if isinstance(v, np.ndarray):
                v = v.tolist()
            elif isinstance(v, GroupCollection):
                v = [item._q_written_values() for item in v]
            elif isinstance(v, Struct) and not _is_id(v):
                v = v._q_written_values()
            elif isinstance(v, (set, frozenset)):
                items = pdef.items_for(self, None) if pdef is not None else ()
                v = sum(it.value for it in items if it.identifier in v)
            out[k] = v
        return out

    def bl_system_properties_get(self, *, do_create=False):
        values = self._q_written_values()
        if not values and not do_create:
            return None
        from .idprops import IDPropertyGroup
        return IDPropertyGroup(values, owner=self)

    def type_recast(self):
        return self

    def rna_ancestors(self):
        chain = []
        node = self._q_owner
        while node is not None:
            chain.append(node)
            if _is_id(node):
                break
            node = getattr(node, "_q_owner", None)
        chain.reverse()
        return chain

    @classmethod
    def bl_rna_get_subclass(cls, id, default=None):
        for sub in cls.__subclasses__():
            rna = sub.__dict__.get("bl_rna")
            if rna is not None and rna.identifier == id:
                return rna
            found = sub.bl_rna_get_subclass(id, MISSING)
            if found is not MISSING:
                return found
        return default

    @classmethod
    def bl_rna_get_subclass_py(cls, id, default=None):
        for sub in cls.__subclasses__():
            rna = sub.__dict__.get("bl_rna")
            if rna is not None and rna.identifier == id:
                return sub
            found = sub.bl_rna_get_subclass_py(id, MISSING)
            if found is not MISSING:
                return found
        return default

    def keyframe_insert(self, data_path, index=-1, frame=None, group="", options=frozenset(), keytype="KEYFRAME"):
        raise NotImplementedInQuartz("bpy_struct.keyframe_insert")

    def keyframe_delete(self, data_path, index=-1, frame=None, group=""):
        raise NotImplementedInQuartz("bpy_struct.keyframe_delete")

    def driver_add(self, path, index=-1):
        raise NotImplementedInQuartz("bpy_struct.driver_add")

    def driver_remove(self, path, index=-1):
        return False

    def _q_on_change(self, pdef):
        idd = self.id_data
        if idd is not None and idd is not self:
            idd._q_on_change(pdef)

    def _q_refs(self):
        from .collections import GroupCollection
        from .properties import PointerDef
        for pdef in _annotations.iter_properties(self):
            if isinstance(pdef, PointerDef) and pdef.is_id_pointer:
                target = getattr(self, pdef.identifier)
                if target is not None:
                    yield IDRef(target, self, "POINTER", pdef.counts_user, pdef.on_remove,
                                *_pointer_closures(self, pdef.identifier))
        for pdef in _annotations.iter_properties(self):
            if pdef.kind not in ("POINTER", "COLLECTION") or pdef.is_id_pointer:
                continue
            val = self._p.get(pdef.identifier)
            if isinstance(val, GroupCollection):
                for item in val:
                    yield from item._q_refs()
            elif isinstance(val, Struct):
                yield from val._q_refs()

    def _q_state_get(self):
        from .collections import GroupCollection
        p = {}
        for k, v in self._p.items():
            if isinstance(v, GroupCollection):
                p[k] = [item._q_state_get() for item in v]
            elif isinstance(v, Struct) and not _is_id(v):
                p[k] = v._q_state_get()
            else:
                p[k] = _copy_plain(v)
        return {
            "p": p,
            "set": sorted(self._p_set),
            "idprops": self._q_idprops.to_dict() if self._q_idprops is not None else None,
            "order": list(self._q_key_order),
        }

    def _q_state_set(self, state):
        from .collections import GroupCollection
        p_state = state.get("p", {})
        for k in list(self._p):
            if k in p_state:
                continue
            cur = self._p[k]
            if isinstance(cur, GroupCollection):
                cur.clear()
            elif isinstance(cur, Struct) and not _is_id(cur):
                cur._q_state_set({})
            else:
                del self._p[k]
        for k, sv in p_state.items():
            cur = self._p.get(k)
            pdef = _annotations.get_property(self, k)
            is_coll = isinstance(cur, GroupCollection) or (pdef is not None and pdef.kind == "COLLECTION")
            is_child = (isinstance(cur, Struct) and not _is_id(cur)) or (
                pdef is not None and pdef.kind == "POINTER" and not pdef.is_id_pointer)
            if is_coll and isinstance(sv, list):
                if not isinstance(cur, GroupCollection):
                    cur = GroupCollection(pdef.fixed_type, owner=self, path=k)
                    self._p[k] = cur
                cur.clear()
                for item_state in sv:
                    cur.add()._q_state_set(item_state)
            elif is_child and isinstance(sv, dict):
                if not isinstance(cur, Struct):
                    cur = pdef.fixed_type._q_new_child(owner=self, path=k)
                    self._p[k] = cur
                cur._q_state_set(sv)
            elif isinstance(sv, np.ndarray) and isinstance(cur, np.ndarray) and cur.shape == sv.shape:
                np.copyto(cur, sv.astype(cur.dtype, copy=False))
            else:
                self._p[k] = _copy_plain(sv)
        self._p_set.clear()
        self._p_set.update(state.get("set", ()))
        self._q_key_order[:] = list(state.get("order", ()))
        idprops = state.get("idprops")
        if idprops is None:
            self._q_idprops = None
        else:
            from .idprops import IDPropertyGroup
            if self._q_idprops is None:
                self._q_idprops = IDPropertyGroup(owner=self)
            self._q_idprops.clear()
            self._q_idprops.update(idprops)

    @classmethod
    def _q_new_child(cls, owner, path):
        inst = cls.__new__(cls)
        inst._q_set_owner(owner, path)
        return inst

    def _q_set_owner(self, owner, path):
        self._q_owner = owner
        self._q_path = path


def _pointer_closures(owner: Struct, identifier: str):
    def clear():
        setattr(owner, identifier, None)

    def remap(new):
        setattr(owner, identifier, new)
    return clear, remap


@builtin_struct
class PropertyGroup(Struct):
    _q_registrable = True
    name: StringProperty(name="Name", description="")
