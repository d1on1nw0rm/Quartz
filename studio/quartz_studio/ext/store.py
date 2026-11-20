from __future__ import annotations

import copy
from typing import Any

import numpy as np

__all__ = [
    "object_extras",
    "scene_extras",
    "get_object",
    "set_object",
    "get_scene_data",
    "set_scene_data",
    "to_json",
    "from_json",
    "deep_copy",
    "notify",
]

_LISTENERS: list = []


def object_extras(obj) -> dict:
    data = getattr(obj, "extras", None)
    if not isinstance(data, dict):
        data = {}
        try:
            obj.extras = data
        except AttributeError:
            pass
    return data


def scene_extras(scene) -> dict:
    data = getattr(scene, "extras", None)
    if not isinstance(data, dict):
        data = {}
        try:
            scene.extras = data
        except AttributeError:
            pass
    return data


def get_object(obj, key: str, default: Any = None) -> Any:
    extras = object_extras(obj)
    if key not in extras:
        return default
    return from_json(extras[key])


def _scene():
    try:
        from ..scene import get_scene
    except ImportError:
        return None
    return get_scene()


def set_object(obj, key: str, value: Any) -> None:
    value = None if value is None else to_json(value)
    scene = _scene()
    setter = getattr(scene, "set_object_extra", None) if scene is not None else None
    if setter is not None and obj in getattr(scene, "objects", ()):
        setter(obj, key, value)
    else:
        extras = object_extras(obj)
        if value is None:
            extras.pop(key, None)
        else:
            extras[key] = value
    notify(obj, key)


def get_scene_data(scene, key: str, default: Any = None) -> Any:
    extras = scene_extras(scene)
    if key not in extras:
        return default
    return from_json(extras[key])


def set_scene_data(scene, key: str, value: Any) -> None:
    value = None if value is None else to_json(value)
    setter = getattr(scene, "set_extra", None)
    if setter is not None:
        setter(key, value)
    else:
        extras = scene_extras(scene)
        if value is None:
            extras.pop(key, None)
        else:
            extras[key] = value
    notify(scene, key)


def notify(owner, key: str) -> None:
    for fn in list(_LISTENERS):
        try:
            fn(owner, key)
        except Exception:
            pass


def to_json(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return {"__ndarray__": value.tolist(), "dtype": str(value.dtype)}
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return f if f == f and f not in (float("inf"), float("-inf")) else 0.0
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]
    if isinstance(value, set):
        return {"__set__": [to_json(v) for v in sorted(value, key=repr)]}
    return value


def from_json(value: Any) -> Any:
    if isinstance(value, dict):
        if "__ndarray__" in value:
            return np.asarray(value["__ndarray__"], dtype=value.get("dtype", "float64"))
        if "__set__" in value:
            return {_hashable(from_json(v)) for v in value["__set__"]}
        return {k: from_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_json(v) for v in value]
    return value


def _hashable(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(_hashable(x) for x in v)
    return v


def deep_copy(value: Any) -> Any:
    return copy.deepcopy(value)
