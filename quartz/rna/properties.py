from __future__ import annotations

import copy
import itertools
import sys
import traceback
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, ClassVar, Mapping

import numpy as np

from ..errors import PropertyTypeError, PropertyValueError, ReadOnlyError, RegistrationError, RemovedStructError
from . import hooks

FLOAT_MAX: float = 3.4028234663852886e38
INT_MIN: int = -2 ** 31
INT_MAX: int = 2 ** 31 - 1

OPTION_FLAGS: frozenset[str] = frozenset({
    "HIDDEN", "SKIP_SAVE", "SKIP_PRESET", "ANIMATABLE", "LIBRARY_EDITABLE",
    "PROPORTIONAL", "TEXTEDIT_UPDATE", "OUTPUT_PATH", "PATH_SUPPORTS_BLEND_RELATIVE",
    "PATH_SUPPORTS_TEMPLATES", "ENUM_FLAG",
})
OVERRIDE_FLAGS: frozenset[str] = frozenset({"LIBRARY_OVERRIDABLE", "NO_PROPERTY_NAME"})
META_KEYS: frozenset[str] = frozenset({
    "group", "parent", "enabled_if", "visible_if", "widget", "dirty", "uid", "since",
    "on_remove", "counts_user", "virtual_get", "virtual_set", "euler_order",
    "fixed_type_name", "readonly", "doc",
})

COERCE_PREFIX: str = "bpy_struct: item.attr = val: "

_FLAG_ORDER: tuple[str, ...] = (
    "is_readonly", "is_animatable", "is_hidden", "is_skip_save", "is_never_none",
    "is_registered", "is_registered_optional", "is_enum_flag",
)

_DYNAMIC_SEQ = itertools.count()


def to_float32(value) -> float:
    return float(np.float32(value))


@dataclass(frozen=True)
class EnumItem:
    identifier: str
    name: str
    description: str
    icon: str | int
    value: int


def normalize_enum_items(items, *, is_flag: bool = False) -> tuple[EnumItem, ...]:
    result: list[EnumItem] = []
    seen: set[str] = set()
    idx = 0
    for entry in items:
        if entry is None:
            continue
        if isinstance(entry, EnumItem):
            item = entry
        elif isinstance(entry, (tuple, list)):
            icon: str | int = ""
            number = None
            if len(entry) == 3:
                ident, name, desc = entry
            elif len(entry) == 4:
                ident, name, desc, fourth = entry
                if isinstance(fourth, int) and not isinstance(fourth, bool):
                    number = fourth
                else:
                    icon = fourth
            elif len(entry) == 5:
                ident, name, desc, icon, number = entry
            else:
                raise ValueError(f"invalid enum item {entry!r}")
            if number is None:
                number = (1 << idx) if is_flag else idx
            item = EnumItem(identifier=str(ident), name=str(name), description=str(desc), icon=icon, value=int(number))
        else:
            raise ValueError(f"invalid enum item {entry!r}")
        if item.identifier in seen:
            raise ValueError(f"duplicate enum identifier {item.identifier!r}")
        seen.add(item.identifier)
        result.append(item)
        idx += 1
    return tuple(result)


def _product(size: tuple[int, ...]) -> int:
    r = 1
    for s in size:
        r *= s
    return r


def _is_sequence(value: object) -> bool:
    if isinstance(value, (str, bytes, bytearray)):
        return False
    if isinstance(value, np.ndarray):
        return True
    try:
        iter(value)
    except TypeError:
        return False
    return True


def _flatten(value: object) -> list:
    if isinstance(value, np.ndarray):
        return value.reshape(-1).tolist()
    out: list = []
    for x in value:
        if _is_sequence(x):
            out.extend(_flatten(x))
        elif isinstance(x, np.generic):
            out.append(x.item())
        else:
            out.append(x)
    return out


def _py(x):
    if isinstance(x, np.generic):
        return x.item()
    return x


class PropertyDef:
    kind: ClassVar[str] = ""

    identifier: str = ""
    owner: type | None = None
    deferred: Any = None
    name: str = ""
    description: str = ""
    translation_context: str = "*"
    options: frozenset = frozenset()
    override: frozenset = frozenset()
    tags: frozenset = frozenset()
    subtype: str = "NONE"
    unit: str = "NONE"
    update: Callable | None = None
    get: Callable | None = None
    set: Callable | None = None
    get_transform: Callable | None = None
    set_transform: Callable | None = None
    meta: Mapping = MappingProxyType({})
    size: tuple = ()
    is_array: bool = False
    array_length: int = 0
    is_readonly: bool = False
    is_hidden: bool = False
    is_skip_save: bool = False
    is_animatable: bool = False
    is_enum_flag: bool = False
    is_never_none: bool = False
    default: Any = None

    hard_min: Any = INT_MIN
    hard_max: Any = INT_MAX
    soft_min: Any = INT_MIN
    soft_max: Any = INT_MAX
    step: Any = 1
    precision: int = 2
    maxlen: int = 0
    search: Callable | None = None
    search_options: frozenset = frozenset()
    items: Any = None
    is_dynamic: bool = False
    fixed_type: type | None = None
    poll: Callable | None = None
    counts_user: bool = True
    on_remove: str = "CLEAR"
    is_id_pointer: bool = False

    def _dtype(self):
        if self.kind == "BOOLEAN":
            return np.bool_
        if self.kind == "INT":
            return np.int32
        if self.kind == "FLOAT":
            return np.float32
        return object

    def _owner_name(self, inst) -> str:
        if inst is not None:
            return type(inst).__name__
        if self.owner is not None:
            return self.owner.__name__
        return "bpy_struct"

    def _readonly_error(self, inst) -> ReadOnlyError:
        return ReadOnlyError(f'bpy_struct: attribute "{self.identifier}" from "{self._owner_name(inst)}" is read-only')

    def items_for(self, inst, context=None):
        if callable(self.items):
            return normalize_enum_items(self.items(inst, context) or (), is_flag=self.is_enum_flag)
        return self.items if self.items is not None else ()

    def default_value(self, inst=None):
        if self.is_array:
            return np.array(self.default, dtype=self._dtype()).reshape(self.size)
        if self.kind == "ENUM":
            dv = self.default
            if self.is_enum_flag:
                if isinstance(dv, (set, frozenset)):
                    return frozenset(dv)
                if isinstance(dv, int) and not isinstance(dv, bool):
                    return frozenset(it.identifier for it in self.items_for(inst, None) if it.value & dv)
                return frozenset()
            if dv is None or (isinstance(dv, int) and not isinstance(dv, bool)):
                items = self.items_for(inst, None)
                if isinstance(dv, int):
                    for it in items:
                        if it.value == dv:
                            return it.identifier
                return items[0].identifier if items else None
            return dv
        if self.kind in ("POINTER", "COLLECTION"):
            return None
        return self.default

    def _coerce_scalar(self, value, T: str):
        ident = self.identifier
        kind = self.kind
        if kind == "BOOLEAN":
            if isinstance(value, (bool, np.bool_)):
                return bool(value)
            if isinstance(value, (int, np.integer)):
                if value in (0, 1):
                    return bool(value)
                raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{ident} expected True/False or 0/1, not int")
            raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{ident} expected True/False or 0/1, not {type(value).__name__}")
        if kind == "INT":
            if isinstance(value, (bool, np.bool_, int, np.integer)):
                return int(max(self.hard_min, min(self.hard_max, int(value))))
            if isinstance(value, (float, np.floating)):
                raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{ident} expected an int type, not float")
            raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{ident} expected an int type, not {type(value).__name__}")
        if kind == "FLOAT":
            if isinstance(value, (bool, np.bool_, int, float, np.integer, np.floating)):
                fv = float(value)
                fv = max(float(self.hard_min), min(float(self.hard_max), fv))
                return to_float32(fv)
            raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{ident} expected a float type, not {type(value).__name__}")
        raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{ident} unsupported value")

    def _coerce_array(self, value, T: str) -> np.ndarray:
        if not _is_sequence(value):
            raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{self.identifier} expected a sequence, not {type(value).__name__}")
        flat = _flatten(value)
        if len(flat) != self.array_length:
            raise PropertyValueError(
                f"{COERCE_PREFIX}sequences of dimension 0 should contain {self.array_length} items, not {len(flat)}")
        coerced = [self._coerce_scalar(x, T) for x in flat]
        return np.array(coerced, dtype=self._dtype()).reshape(self.size)

    def coerce(self, value, inst=None):
        T = self._owner_name(inst)
        ident = self.identifier
        if self.is_array:
            return self._coerce_array(value, T)
        kind = self.kind
        if kind in ("BOOLEAN", "INT", "FLOAT"):
            return self._coerce_scalar(value, T)
        if kind == "STRING":
            if isinstance(value, str):
                s = value
            elif self.subtype == "BYTE_STRING" and isinstance(value, (bytes, bytearray)):
                s = bytes(value).decode("utf-8", "surrogateescape")
            else:
                raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{ident} expected a string type, not {type(value).__name__}")
            if self.maxlen and self.maxlen > 0:
                while len(s.encode("utf-8", "surrogateescape")) > self.maxlen and s:
                    s = s[:-1]
            return s
        if kind == "ENUM":
            items = self.items_for(inst, hooks.current_context())
            ids = [it.identifier for it in items]
            listing = ", ".join(repr(i) for i in ids)
            if self.is_enum_flag:
                if not isinstance(value, (set, frozenset)):
                    raise PropertyTypeError(f"{COERCE_PREFIX}{T}.{ident} expected a set, not {type(value).__name__}")
                for v in value:
                    if v not in ids:
                        raise PropertyTypeError(f'{COERCE_PREFIX}enum "{v}" not found in ({listing})')
                return frozenset(value)
            if not isinstance(value, str) or value not in ids:
                raise PropertyTypeError(f'{COERCE_PREFIX}enum "{value}" not found in ({listing})')
            return value
        if kind == "POINTER":
            if value is None:
                if self.is_never_none:
                    raise PropertyValueError(f"{COERCE_PREFIX}{T}.{ident} does not support a 'None' assignment")
                return None
            if getattr(value, "_q_removed", False):
                raise RemovedStructError(f"{COERCE_PREFIX}StructRNA of type {type(value).__name__} has been removed")
            if self.fixed_type is not None and not isinstance(value, self.fixed_type):
                raise PropertyTypeError(
                    f"{COERCE_PREFIX}{T}.{ident} expected a {self.fixed_type.__name__} type, not {type(value).__name__}")
            if self.poll is not None and not self.poll(inst, value):
                raise PropertyValueError(f"{COERCE_PREFIX}{T}.{ident} value rejected by poll()")
            return value
        return value

    def read_raw(self, inst):
        if self.identifier in inst._p:
            return inst._p[self.identifier]
        return self.default_value(inst)

    def write_raw(self, inst, value):
        inst._p[self.identifier] = value
        inst._p_set.add(self.identifier)

    def _limit(self, v):
        return to_float32(v) if self.kind == "FLOAT" else v

    def to_rna_dict(self):
        d: dict[str, object] = {"type": self.kind, "subtype": self.subtype}
        if self.kind == "FLOAT" and self.unit != "NONE":
            d["unit"] = self.unit
        flag_values = {
            "is_readonly": self.is_readonly,
            "is_animatable": self.is_animatable,
            "is_hidden": self.is_hidden,
            "is_skip_save": self.is_skip_save,
            "is_never_none": self.is_never_none,
            "is_registered": False,
            "is_registered_optional": False,
            "is_enum_flag": self.is_enum_flag,
        }
        d["flags"] = [name for name in _FLAG_ORDER if flag_values[name]]
        if self.is_array:
            d["array_length"] = self.array_length
            if len(self.size) == 2:
                d["array_dimensions"] = list(self.size)
            d["default"] = self.default_value(None).reshape(-1).tolist()
        elif self.kind == "ENUM":
            if self.is_enum_flag and isinstance(self.default, (set, frozenset)):
                d["default"] = sorted(self.default)
            else:
                d["default"] = self.default
        elif self.kind in ("POINTER", "COLLECTION"):
            pass
        else:
            d["default"] = self.default
        if self.kind in ("INT", "FLOAT"):
            d["min"] = self._limit(self.hard_min)
            d["max"] = self._limit(self.hard_max)
            d["soft_min"] = self._limit(self.soft_min)
            d["soft_max"] = self._limit(self.soft_max)
            d["step"] = self.step
        if self.kind == "FLOAT":
            d["precision"] = self.precision
        if self.kind == "STRING" and self.maxlen and self.maxlen > 0:
            d["length_max"] = self.maxlen
        if self.kind == "ENUM" and not self.is_dynamic:
            d["items"] = [it.identifier for it in (self.items or ())]
        if self.kind in ("POINTER", "COLLECTION"):
            name = self.meta.get("fixed_type_name")
            if name is None:
                ft = self.fixed_type
                rna = ft.__dict__.get("bl_rna") if isinstance(ft, type) else None
                name = rna.identifier if rna is not None else getattr(ft, "__name__", "")
            d["fixed_type"] = name
        return d

    def clone_for(self, owner):
        new = copy.copy(self)
        new.owner = owner
        return new

    def __get__(self, inst, owner_cls=None):
        if inst is None:
            return self.deferred if self.deferred is not None else self
        ident = self.identifier
        vg = self.meta.get("virtual_get")
        if vg is not None:
            v = vg(inst)
            if self.is_array:
                vs = self.meta.get("virtual_set")
                arr = np.asarray(v)

                def on_write():
                    if vs is None:
                        raise self._readonly_error(inst)
                    vs(inst, arr)
                return hooks.wrap_array(arr, self, inst, on_write)
            if self.kind == "FLOAT" and v is not None:
                return to_float32(v)
            if self.kind == "ENUM" and self.is_enum_flag and isinstance(v, (set, frozenset)):
                return set(v)
            return v

        is_set = ident in inst._p_set
        if self.get is not None:
            raw = self.get(inst)
            if self.kind == "ENUM":
                if self.is_enum_flag:
                    if isinstance(raw, int) and not isinstance(raw, bool):
                        raw = {it.identifier for it in self.items_for(inst, None) if it.value & raw}
                elif isinstance(raw, int) and not isinstance(raw, bool):
                    for it in self.items_for(inst, None):
                        if it.value == raw:
                            raw = it.identifier
                            break
            if self.get_transform is not None:
                raw = self.get_transform(inst, raw, is_set)
            if self.is_array:
                arr = np.array(_flatten(raw) if _is_sequence(raw) else raw, dtype=self._dtype()).reshape(self.size)

                def on_write():
                    self.__set__(inst, arr.copy())
                return hooks.wrap_array(arr, self, inst, on_write)
            if self.kind == "ENUM" and self.is_enum_flag and isinstance(raw, (set, frozenset)):
                return set(raw)
            return raw

        p = inst._p
        if self.is_array:
            arr = p.get(ident)
            if not isinstance(arr, np.ndarray):
                arr = self.default_value(inst)
                p[ident] = arr
            view = arr
            if self.get_transform is not None:
                view = np.asarray(self.get_transform(inst, arr, is_set))

            def on_write():
                self.__set__(inst, np.array(view, copy=True))
            return hooks.wrap_array(view, self, inst, on_write)

        if ident in p:
            value = p[ident]
        elif self.kind == "POINTER" and not self.is_id_pointer:
            value = self.fixed_type._q_new_child(owner=inst, path=ident)
            p[ident] = value
            return value
        elif self.kind == "COLLECTION":
            from .collections import GroupCollection
            value = GroupCollection(self.fixed_type, owner=inst, path=ident)
            p[ident] = value
            return value
        else:
            value = self.default_value(inst)
        if self.kind in ("POINTER", "COLLECTION") and not self.is_id_pointer:
            return value
        if self.get_transform is not None:
            value = self.get_transform(inst, value, is_set)
        if self.kind == "ENUM" and self.is_enum_flag and isinstance(value, (set, frozenset)):
            return set(value)
        return value

    def __set__(self, inst, value):
        ident = self.identifier
        if self.is_readonly or self.kind == "COLLECTION" or (self.kind == "POINTER" and not self.is_id_pointer):
            raise self._readonly_error(inst)
        v = self.coerce(value, inst)
        if self.set_transform is not None:
            current = self.read_raw(inst)
            v = self.coerce(self.set_transform(inst, v, current, ident in inst._p_set), inst)
        vs = self.meta.get("virtual_set")
        if self.set is not None:
            self.set(inst, self._to_callback_value(v, inst))
        elif vs is not None:
            if self.kind == "ENUM" and self.is_enum_flag:
                vs(inst, set(v))
            else:
                vs(inst, v)
        elif self.is_array:
            cur = inst._p.get(ident)
            if isinstance(cur, np.ndarray) and cur.shape == v.shape and cur.dtype == v.dtype:
                np.copyto(cur, v)
            else:
                inst._p[ident] = v.copy()
        else:
            inst._p[ident] = v
        inst._p_set.add(ident)
        order = getattr(inst, "_q_key_order", None)
        if isinstance(order, list) and ident not in order:
            order.append(ident)
        on_change = getattr(inst, "_q_on_change", None)
        if on_change is not None:
            on_change(self)
        hooks.on_property_changed(inst, self)
        if self.update is not None:
            try:
                self.update(inst, hooks.current_context())
            except Exception:
                traceback.print_exc(file=sys.stderr)

    def _to_callback_value(self, v, inst):
        if self.kind == "ENUM":
            items = self.items_for(inst, None)
            if self.is_enum_flag:
                mask = 0
                for it in items:
                    if it.identifier in v:
                        mask |= it.value
                return mask
            for it in items:
                if it.identifier == v:
                    return it.value
            return v
        if self.is_array:
            arr = np.asarray(v)
            if arr.ndim == 2:
                return tuple(tuple(_py(x) for x in row) for row in arr)
            return tuple(_py(x) for x in arr.reshape(-1))
        return v

    def __delete__(self, inst):
        raise AttributeError(f'bpy_struct: attribute "{self.identifier}" cannot be deleted')


class BoolDef(PropertyDef):
    kind: ClassVar[str] = "BOOLEAN"


class IntDef(PropertyDef):
    kind: ClassVar[str] = "INT"


class FloatDef(PropertyDef):
    kind: ClassVar[str] = "FLOAT"


class StringDef(PropertyDef):
    kind: ClassVar[str] = "STRING"


class EnumDef(PropertyDef):
    kind: ClassVar[str] = "ENUM"


class PointerDef(PropertyDef):
    kind: ClassVar[str] = "POINTER"


class CollectionDef(PropertyDef):
    kind: ClassVar[str] = "COLLECTION"


_KIND_TO_DEF: dict[str, tuple[type, bool]] = {
    "BOOLEAN": (BoolDef, False),
    "BOOLEAN_VECTOR": (BoolDef, True),
    "INT": (IntDef, False),
    "INT_VECTOR": (IntDef, True),
    "FLOAT": (FloatDef, False),
    "FLOAT_VECTOR": (FloatDef, True),
    "STRING": (StringDef, False),
    "ENUM": (EnumDef, False),
    "POINTER": (PointerDef, False),
    "COLLECTION": (CollectionDef, False),
}


def _check_scalar_default(pdef: PropertyDef, value, where: str = "default"):
    kind = pdef.kind
    if kind == "BOOLEAN":
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, np.integer)) and value in (0, 1):
            return bool(value)
        raise TypeError(f"{where} expected a bool, not {type(value).__name__}")
    if kind == "INT":
        if isinstance(value, (bool, np.bool_, int, np.integer)):
            return int(max(pdef.hard_min, min(pdef.hard_max, int(value))))
        raise TypeError(f"{where} expected an int, not {type(value).__name__}")
    if kind == "FLOAT":
        if isinstance(value, (bool, np.bool_, int, float, np.integer, np.floating)):
            return to_float32(max(float(pdef.hard_min), min(float(pdef.hard_max), float(value))))
        raise TypeError(f"{where} expected a float, not {type(value).__name__}")
    if kind == "STRING":
        if isinstance(value, str):
            return value
        if pdef.subtype == "BYTE_STRING" and isinstance(value, (bytes, bytearray)):
            return bytes(value).decode("utf-8", "surrogateescape")
        raise TypeError(f"{where} expected a str, not {type(value).__name__}")
    return value


def _check_array_default(pdef: PropertyDef, value) -> tuple:
    if not _is_sequence(value):
        raise TypeError(f"default expected a sequence, not {type(value).__name__}")
    flat = _flatten(value)
    if len(flat) != pdef.array_length:
        raise ValueError(f"default sequence must have {pdef.array_length} items, not {len(flat)}")
    values = [_check_scalar_default(pdef, x, "default item") for x in flat]
    if len(pdef.size) == 1:
        return tuple(values)
    arr = np.array(values, dtype=object).reshape(pdef.size)
    return _nested_tuple(arr)


def _nested_tuple(arr) -> tuple:
    if arr.ndim == 1:
        return tuple(arr.tolist())
    return tuple(_nested_tuple(row) for row in arr)


def _number(value, what: str):
    if isinstance(value, (bool, int, float, np.integer, np.floating)):
        return value
    raise TypeError(f"{what} expected a number, not {type(value).__name__}")


def _build(identifier: str, deferred, owner: type) -> PropertyDef:
    kind_raw = deferred._kind
    if kind_raw not in _KIND_TO_DEF:
        raise ValueError(f"unknown property kind {kind_raw!r}")
    pdef_cls, is_vector = _KIND_TO_DEF[kind_raw]
    kind = pdef_cls.kind
    kw = dict(deferred.keywords)

    meta_raw = kw.get("meta") or {}
    if not isinstance(meta_raw, Mapping):
        raise TypeError("meta must be a mapping")
    for k in meta_raw:
        if k not in META_KEYS:
            raise KeyError(f"unknown meta key {k!r}")
    meta = MappingProxyType(dict(meta_raw))

    options = frozenset(kw.get("options", {"ANIMATABLE"}))
    for o in options:
        if o not in OPTION_FLAGS:
            raise ValueError(f"invalid option {o!r}")
    if "ENUM_FLAG" in options and kind != "ENUM":
        raise ValueError("ENUM_FLAG is only valid for EnumProperty")
    override = frozenset(kw.get("override") or ())
    for o in override:
        if o not in OVERRIDE_FLAGS:
            raise ValueError(f"invalid override {o!r}")

    if is_vector:
        size_kw = kw.get("size", 3)
        size = (size_kw,) if isinstance(size_kw, int) else tuple(size_kw)
        if not size or any(not isinstance(s, int) or isinstance(s, bool) or s < 1 for s in size):
            raise ValueError(f"invalid size {size_kw!r}")
    else:
        size = ()

    pdef = pdef_cls()
    pdef.identifier = identifier
    pdef.owner = owner
    pdef.deferred = deferred
    pdef.name = kw.get("name", "")
    pdef.description = kw.get("description", "")
    pdef.translation_context = kw.get("translation_context", "*")
    pdef.options = options
    pdef.override = override
    pdef.tags = frozenset(kw.get("tags") or ())
    pdef.subtype = kw.get("subtype", "NONE")
    pdef.unit = kw.get("unit", "NONE")
    pdef.update = kw.get("update")
    pdef.get = kw.get("get")
    pdef.set = kw.get("set")
    pdef.get_transform = kw.get("get_transform")
    pdef.set_transform = kw.get("set_transform")
    pdef.meta = meta
    pdef.size = size
    pdef.is_array = bool(size)
    pdef.array_length = _product(size) if size else 0
    pdef.is_hidden = "HIDDEN" in options
    pdef.is_skip_save = "SKIP_SAVE" in options
    pdef.is_animatable = "ANIMATABLE" in options
    pdef.is_enum_flag = "ENUM_FLAG" in options
    pdef.is_never_none = False

    if kind in ("INT", "FLOAT"):
        lo, hi = (INT_MIN, INT_MAX) if kind == "INT" else (-FLOAT_MAX, FLOAT_MAX)
        pdef.hard_min = _number(kw.get("min", lo), "min")
        pdef.hard_max = _number(kw.get("max", hi), "max")
        soft_min = kw.get("soft_min")
        soft_max = kw.get("soft_max")
        pdef.soft_min = max(_number(soft_min, "soft_min") if soft_min is not None else pdef.hard_min, pdef.hard_min)
        pdef.soft_max = min(_number(soft_max, "soft_max") if soft_max is not None else pdef.hard_max, pdef.hard_max)
        if kind == "INT":
            pdef.step = kw.get("step", 1)
        else:
            pdef.step = kw.get("step", 3)
            pdef.precision = kw.get("precision", 2)

    if kind in ("BOOLEAN", "INT", "FLOAT", "STRING"):
        if pdef.is_array:
            if "default" in kw:
                pdef.default = _check_array_default(pdef, kw["default"])
            else:
                zero = {"BOOLEAN": False, "INT": 0, "FLOAT": 0.0}[kind]
                pdef.default = _check_array_default(pdef, [_check_scalar_default(pdef, zero)] * pdef.array_length)
        else:
            base = {"BOOLEAN": False, "INT": 0, "FLOAT": 0.0, "STRING": ""}[kind]
            pdef.default = _check_scalar_default(pdef, kw.get("default", base))

    if kind == "STRING":
        maxlen = kw.get("maxlen", 0)
        if not isinstance(maxlen, int) or isinstance(maxlen, bool) or maxlen < 0:
            raise ValueError(f"invalid maxlen {maxlen!r}")
        pdef.maxlen = maxlen
        pdef.search = kw.get("search")
        pdef.search_options = frozenset(kw.get("search_options", {"SUGGESTION"}))

    if kind == "ENUM":
        items_raw = kw.get("items")
        default = kw.get("default")
        if callable(items_raw):
            pdef.items = items_raw
            pdef.is_dynamic = True
            if pdef.is_enum_flag:
                if default is not None and not isinstance(default, (set, frozenset, int)):
                    raise TypeError("ENUM_FLAG default must be a set")
                pdef.default = frozenset(default) if isinstance(default, (set, frozenset)) else default
            else:
                pdef.default = default
        else:
            pdef.items = normalize_enum_items(items_raw or (), is_flag=pdef.is_enum_flag)
            pdef.is_dynamic = False
            ids = [it.identifier for it in pdef.items]
            if pdef.is_enum_flag:
                if default is None:
                    default = frozenset()
                if not isinstance(default, (set, frozenset)):
                    raise TypeError(f"ENUM_FLAG default must be a set, not {type(default).__name__}")
                for v in default:
                    if v not in ids:
                        raise ValueError(f"default {v!r} not found in enum items")
                pdef.default = frozenset(default)
            else:
                if default is None:
                    pdef.default = ids[0] if ids else None
                elif isinstance(default, int) and not isinstance(default, bool):
                    match = [it.identifier for it in pdef.items if it.value == default]
                    if not match:
                        raise ValueError(f"default {default!r} not found in enum items")
                    pdef.default = match[0]
                elif isinstance(default, str) and default in ids:
                    pdef.default = default
                else:
                    raise ValueError(f"default {default!r} not found in enum items")

    if kind in ("POINTER", "COLLECTION"):
        ft = kw.get("type")
        if not isinstance(ft, type):
            raise TypeError(f"type expected a class, not {type(ft).__name__}")
        is_id = bool(getattr(ft, "_q_is_id", False))
        has_rna = "bl_rna" in ft.__dict__
        if kind == "POINTER" and not (is_id or has_rna):
            raise TypeError(f"{ft.__name__} is neither a registered struct nor an ID type")
        if kind == "COLLECTION" and not has_rna:
            raise TypeError(f"{ft.__name__} is not a registered struct")
        pdef.fixed_type = ft
        if kind == "POINTER":
            pdef.poll = kw.get("poll")
            pdef.is_id_pointer = is_id
            pdef.counts_user = bool(meta.get("counts_user", True))
            pdef.on_remove = meta.get("on_remove", "CLEAR")
            if pdef.on_remove not in ("CLEAR", "DELETE_OWNER"):
                raise ValueError(f"invalid on_remove {pdef.on_remove!r}")

    readonly = bool(
        (pdef.get is not None and pdef.set is None)
        or (meta.get("virtual_get") is not None and meta.get("virtual_set") is None)
        or meta.get("readonly")
    )
    if kind == "COLLECTION" or (kind == "POINTER" and not pdef.is_id_pointer):
        readonly = True
    pdef.is_readonly = readonly
    return pdef


def build_property(identifier: str, deferred, owner: type) -> PropertyDef:
    try:
        return _build(identifier, deferred, owner)
    except Exception as e:
        factory = getattr(deferred, "function", None)
        fname = getattr(factory, "__name__", "Property")
        raise RegistrationError(
            f'bpy_struct "{owner.__name__}" registration error: \'{identifier}\' {fname} could not register') from e
