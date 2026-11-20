from __future__ import annotations

from collections import OrderedDict
from typing import Any

import numpy as np

from ..ext import store

__all__ = ["SKIN_KEY", "IK_KEY", "read", "write", "write_quiet", "clear_cache"]

SKIN_KEY = "skin"
IK_KEY = "ik"

_CACHE: "OrderedDict[int, tuple[Any, Any]]" = OrderedDict()
_CACHE_SIZE = 64


def _clone(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.copy()
    if isinstance(value, dict):
        return {k: _clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone(v) for v in value]
    return value


def clear_cache() -> None:
    _CACHE.clear()


def read(obj, key: str, default: Any = None) -> Any:
    extras = store.object_extras(obj)
    if key not in extras:
        return default
    raw = extras[key]
    if not isinstance(raw, (dict, list)):
        return store.from_json(raw)
    hit = _CACHE.get(id(raw))
    if hit is not None and hit[0] is raw:
        _CACHE.move_to_end(id(raw))
        return _clone(hit[1])
    value = store.from_json(raw)
    _CACHE[id(raw)] = (raw, value)
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return _clone(value)


def write(scene, obj, key: str, value: Any) -> None:
    encoded = None if value is None else store.to_json(value)
    setter = getattr(scene, "set_object_extra", None) if scene is not None else None
    if setter is not None and obj in getattr(scene, "objects", ()):
        setter(obj, key, encoded)
        store.notify(obj, key)
    else:
        store.set_object(obj, key, encoded)


def write_quiet(obj, key: str, value: Any) -> None:
    extras = store.object_extras(obj)
    if value is None:
        extras.pop(key, None)
    else:
        extras[key] = store.to_json(value)
