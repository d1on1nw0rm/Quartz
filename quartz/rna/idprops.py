from __future__ import annotations

import builtins
from collections.abc import Mapping, MutableMapping
from typing import Any

import numpy as np

from ..errors import PropertyTypeError

_max = builtins.max
_min = builtins.min


_INT32_MIN = -2 ** 31
_INT32_MAX = 2 ** 31 - 1
_FLOAT_MAX = 3.4028234663852886e38


def _check_int32(v: int) -> int:
    if v < _INT32_MIN or v > _INT32_MAX:
        raise OverflowError(f"value {v} does not fit in a 32-bit ID property integer")
    return v


def _is_number(x) -> bool:
    return isinstance(x, (bool, int, float, np.bool_, np.integer, np.floating))


def _convert_value(value, key=""):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return _check_int32(int(value))
    if isinstance(value, (float, np.floating)):
        return float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (IDPropertyGroup, IDPropertyArray)):
        return value
    if getattr(type(value), "_q_is_id", False):
        return value
    if isinstance(value, Mapping):
        return IDPropertyGroup(value)
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        if all(isinstance(x, Mapping) for x in value):
            return [x if isinstance(x, IDPropertyGroup) else IDPropertyGroup(x) for x in value]
        if all(_is_number(x) for x in value):
            if all(isinstance(x, (bool, np.bool_)) for x in value):
                return IDPropertyArray(value, "b")
            if all(isinstance(x, (int, np.integer)) and not isinstance(x, (bool, np.bool_)) for x in value):
                for x in value:
                    _check_int32(int(x))
                return IDPropertyArray(value, "i")
            return IDPropertyArray(value, "d")
        raise TypeError(f"ID property '{key}': sequences may only contain numbers or dicts")
    raise TypeError(f"ID property '{key}': '{type(value).__name__}' type not supported")


_MISSING = object()


class IDPropertyGroup(MutableMapping):
    def __init__(self, data=None, *, name: str = "", owner=None):
        self._data = {}
        self._order = []
        self.name = name
        self._owner = owner
        self._ui = {}
        if data is not None:
            self.update(data)

    def __getitem__(self, key):
        if key not in self._data:
            raise KeyError(key)
        return self._data[key]

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            key = str(key)
        conv = _convert_value(value, key)
        if key not in self._data:
            self._order.append(key)
        self._data[key] = conv

    def __delitem__(self, key):
        if key not in self._data:
            raise KeyError(key)
        del self._data[key]
        if key in self._order:
            self._order.remove(key)
        self._ui.pop(key, None)

    def __iter__(self):
        return iter(self._order)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    def keys(self):
        return list(self._order)

    def values(self):
        return [self._data[k] for k in self._order]

    def items(self):
        return [(k, self._data[k]) for k in self._order]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def pop(self, key, default=_MISSING):
        if key in self._data:
            val = self._data[key]
            del self[key]
            return val
        if default is _MISSING:
            raise KeyError(key)
        return default

    def clear(self):
        self._data.clear()
        self._order.clear()
        self._ui.clear()

    def update(self, other=(), /, **kwargs):
        if isinstance(other, Mapping) or hasattr(other, "keys"):
            for k in list(other.keys()):
                self[k] = other[k]
        else:
            for k, v in other:
                self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def to_dict(self):
        res = {}
        for k in self._order:
            v = self._data[k]
            if isinstance(v, IDPropertyGroup):
                res[k] = v.to_dict()
            elif isinstance(v, IDPropertyArray):
                res[k] = v.to_list()
            elif isinstance(v, list):
                res[k] = [_item_to_dict(x) for x in v]
            else:
                res[k] = v
        return res

    @property
    def _q_ui(self):
        return self._ui


class IDPropertyArray:
    def __init__(self, values, typecode):
        self.typecode = typecode
        if typecode == "b":
            self._data = [bool(v) for v in values]
        elif typecode == "i":
            self._data = [int(v) for v in values]
        else:
            self._data = [float(v) for v in values]

    def __len__(self):
        return len(self._data)

    def __getitem__(self, index):
        return self._data[index]

    def __setitem__(self, index, value):
        if self.typecode == "b":
            if not isinstance(value, bool) and not (isinstance(value, int) and value in (0, 1)):
                raise PropertyTypeError("expected bool")
            self._data[index] = bool(value)
        elif self.typecode == "i":
            if isinstance(value, float):
                raise PropertyTypeError("expected int")
            v = int(value)
            if v < -2 ** 31 or v > 2 ** 31 - 1:
                raise OverflowError("int out of range")
            self._data[index] = v
        else:
            self._data[index] = float(value)

    def __iter__(self):
        return iter(self._data)

    def __eq__(self, other):
        try:
            return list(self._data) == list(other)
        except Exception:
            return False

    def __array__(self, dtype=None, copy=None):
        return np.asarray(self._data, dtype=dtype)

    def to_list(self):
        return list(self._data)


def _item_to_dict(x):
    if isinstance(x, IDPropertyGroup):
        return x.to_dict()
    if isinstance(x, IDPropertyArray):
        return x.to_list()
    if isinstance(x, list):
        return [_item_to_dict(i) for i in x]
    return x


class IDPropertyUIManager:
    def __init__(self, group, key):
        self._group = group
        self._key = key
        self._data = {}
        self._init_defaults()

    def _value(self):
        return self._group[self._key] if self._key in self._group else None

    def _value_type(self) -> str:
        v = self._value()
        if isinstance(v, IDPropertyArray):
            return {"b": "BOOLEAN", "i": "INT", "d": "FLOAT"}[v.typecode]
        if isinstance(v, bool):
            return "BOOLEAN"
        if isinstance(v, int):
            return "INT"
        if isinstance(v, float):
            return "FLOAT"
        if isinstance(v, str):
            return "STRING"
        if getattr(type(v), "_q_is_id", False):
            return "ID"
        return "OTHER"

    def _init_defaults(self):
        t = self._value_type()
        base = {"subtype": "NONE", "description": ""}
        if t == "FLOAT":
            base.update(min=-_FLOAT_MAX, max=_FLOAT_MAX, soft_min=-_FLOAT_MAX, soft_max=_FLOAT_MAX,
                        step=1.0, precision=3, default=0.0)
        elif t == "INT":
            base.update(min=_INT32_MIN, max=_INT32_MAX, soft_min=_INT32_MIN, soft_max=_INT32_MAX, step=1, default=0)
        elif t == "BOOLEAN":
            base.update(default=False)
        elif t == "STRING":
            base.update(default="")
        elif t == "ID":
            base.update(id_type="OBJECT")
        self._data = base

    def update(self, *, subtype=None, min=None, max=None, soft_min=None, soft_max=None, precision=None, step=None,
               default=None, description=None, id_type=None, items=None):
        t = self._value_type()
        numeric = t in ("INT", "FLOAT")
        given = {"min": min, "max": max, "soft_min": soft_min, "soft_max": soft_max, "step": step}
        if not numeric and any(v is not None for v in given.values()):
            raise TypeError(f"ID property '{self._key}': range arguments are only valid for numeric properties")
        if precision is not None and t != "FLOAT":
            raise TypeError(f"ID property '{self._key}': 'precision' is only valid for float properties")
        if id_type is not None and t != "ID":
            raise TypeError(f"ID property '{self._key}': 'id_type' is only valid for ID pointer properties")
        cast = float if t == "FLOAT" else int
        for name, v in given.items():
            if v is not None:
                self._data[name] = cast(v)
        if numeric:
            if min is not None:
                self._data["soft_min"] = _max(self._data["soft_min"], self._data["min"])
            if max is not None:
                self._data["soft_max"] = _min(self._data["soft_max"], self._data["max"])
        if precision is not None:
            self._data["precision"] = int(precision)
        if default is not None:
            self._data["default"] = self._cast_default(t, default)
        if description is not None:
            self._data["description"] = description
        if subtype is not None:
            self._data["subtype"] = subtype
        if id_type is not None:
            self._data["id_type"] = id_type
        if items is not None:
            self._data["items"] = items

    @staticmethod
    def _cast_default(t: str, default):
        cast = {"FLOAT": float, "INT": int, "BOOLEAN": bool, "STRING": str}.get(t)
        if cast is None:
            return default
        if t != "STRING" and isinstance(default, (list, tuple)):
            return [cast(x) for x in default]
        return cast(default)

    def as_dict(self):
        return dict(self._data)

    def clear(self):
        self._init_defaults()

    def update_from(self, ui_manager):
        self._data = dict(ui_manager.as_dict())


def rna_idprop_ui_create(item, prop, *, default, min=0, max=1, soft_min=None, soft_max=None, description=None,
                         overridable=False, subtype=None, step=None, precision=None, id_type=None, items=None):
    item[prop] = default
    grp = item.id_properties_ensure()
    mgr = IDPropertyUIManager(grp, prop)
    kwargs = {"description": description, "subtype": subtype, "id_type": id_type, "items": items}
    if mgr._value_type() in ("INT", "FLOAT"):
        kwargs.update(min=min, max=max, soft_min=min if soft_min is None else soft_min,
                      soft_max=max if soft_max is None else soft_max, step=step, precision=precision,
                      default=default)
    elif mgr._value_type() in ("BOOLEAN", "STRING"):
        kwargs["default"] = default
    mgr.update(**kwargs)
    grp._ui[prop] = mgr
    return mgr


def rna_idprop_value_to_python(value):
    if isinstance(value, IDPropertyGroup):
        return value.to_dict()
    if isinstance(value, IDPropertyArray):
        return value.to_list()
    if isinstance(value, list):
        return [rna_idprop_value_to_python(x) for x in value]
    return value


def rna_idprop_quote_path(prop):
    from .datapath import escape_identifier
    return f'["{escape_identifier(prop)}"]'
