from __future__ import annotations

from typing import Any, Callable, Mapping

from .errors import PropertyTypeError, RegistrationError

__all__ = [
    "BoolProperty", "BoolVectorProperty", "IntProperty", "IntVectorProperty",
    "FloatProperty", "FloatVectorProperty", "StringProperty", "EnumProperty",
    "PointerProperty", "CollectionProperty", "RemoveProperty",
    "_PropertyDeferred", "make_deferred", "FACTORY_NAMES", "PROPERTY_KWARGS",
    "NATIVE_KWARGS", "POSITIONAL_PARAM",
]


class _PropertyDeferred:
    __slots__ = ("function", "keywords", "_kind")

    def __init__(self, function: Callable, keywords: dict[str, object], kind: str) -> None:
        self.function = function
        self.keywords = keywords
        self._kind = kind

    def __repr__(self) -> str:
        return f"<_PropertyDeferred, {self.function.__name__}, {self.keywords!r}>"


FACTORY_NAMES: dict[str, str] = {
    "BOOLEAN": "BoolProperty",
    "BOOLEAN_VECTOR": "BoolVectorProperty",
    "INT": "IntProperty",
    "INT_VECTOR": "IntVectorProperty",
    "FLOAT": "FloatProperty",
    "FLOAT_VECTOR": "FloatVectorProperty",
    "STRING": "StringProperty",
    "ENUM": "EnumProperty",
    "POINTER": "PointerProperty",
    "COLLECTION": "CollectionProperty",
}

PROPERTY_KWARGS: dict[str, tuple[str, ...]] = {
    "BoolProperty": ("name", "description", "translation_context", "default", "options", "override", "tags", "subtype", "update", "get", "set", "get_transform", "set_transform"),
    "BoolVectorProperty": ("name", "description", "translation_context", "default", "options", "override", "tags", "subtype", "size", "update", "get", "set", "get_transform", "set_transform"),
    "CollectionProperty": ("type", "name", "description", "translation_context", "options", "override", "tags"),
    "EnumProperty": ("items", "name", "description", "translation_context", "default", "options", "override", "tags", "update", "get", "set", "get_transform", "set_transform"),
    "FloatProperty": ("name", "description", "translation_context", "default", "min", "max", "soft_min", "soft_max", "step", "precision", "options", "override", "tags", "subtype", "unit", "update", "get", "set", "get_transform", "set_transform"),
    "FloatVectorProperty": ("name", "description", "translation_context", "default", "min", "max", "soft_min", "soft_max", "step", "precision", "options", "override", "tags", "subtype", "unit", "size", "update", "get", "set", "get_transform", "set_transform"),
    "IntProperty": ("name", "description", "translation_context", "default", "min", "max", "soft_min", "soft_max", "step", "options", "override", "tags", "subtype", "update", "get", "set", "get_transform", "set_transform"),
    "IntVectorProperty": ("name", "description", "translation_context", "default", "min", "max", "soft_min", "soft_max", "step", "options", "override", "tags", "subtype", "size", "update", "get", "set", "get_transform", "set_transform"),
    "PointerProperty": ("type", "name", "description", "translation_context", "options", "override", "tags", "poll", "update"),
    "StringProperty": ("name", "description", "translation_context", "default", "maxlen", "options", "override", "tags", "subtype", "update", "get", "set", "get_transform", "set_transform", "search", "search_options"),
}

NATIVE_KWARGS: frozenset[str] = frozenset({"meta"})

POSITIONAL_PARAM: dict[str, str] = {
    "EnumProperty": "items",
    "PointerProperty": "type",
    "CollectionProperty": "type",
}


def make_deferred(function: Callable, kind: str, args: tuple, kwargs: dict, *, allow_meta: bool = True) -> _PropertyDeferred:
    factory = function.__name__
    allowed = set(PROPERTY_KWARGS.get(factory, ()))
    if allow_meta:
        allowed.add("meta")
    for k in kwargs:
        if k not in allowed:
            raise PropertyTypeError(f"{factory}() got an unexpected keyword argument '{k}'")
    kw = dict(kwargs)
    if args:
        if len(args) > 1:
            raise PropertyTypeError(f"{factory}() takes 0 positional arguments")
        if factory in POSITIONAL_PARAM:
            param = POSITIONAL_PARAM[factory]
            if param in kw:
                raise PropertyTypeError(f"{factory}() got multiple values for argument '{param}'")
            kw[param] = args[0]
        else:
            raise PropertyTypeError(f"{factory}() takes 0 positional arguments")
    if factory == "EnumProperty" and "items" not in kw:
        raise PropertyTypeError("EnumProperty() missing required argument 'items'")
    if factory == "PointerProperty" and "type" not in kw:
        raise PropertyTypeError("PointerProperty() missing required argument 'type'")
    if factory == "CollectionProperty" and "type" not in kw:
        raise PropertyTypeError("CollectionProperty() missing required argument 'type'")
    return _PropertyDeferred(function, kw, kind)


def BoolProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(BoolProperty, "BOOLEAN", args, kwargs)


def BoolVectorProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(BoolVectorProperty, "BOOLEAN_VECTOR", args, kwargs)


def IntProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(IntProperty, "INT", args, kwargs)


def IntVectorProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(IntVectorProperty, "INT_VECTOR", args, kwargs)


def FloatProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(FloatProperty, "FLOAT", args, kwargs)


def FloatVectorProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(FloatVectorProperty, "FLOAT_VECTOR", args, kwargs)


def StringProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(StringProperty, "STRING", args, kwargs)


def EnumProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(EnumProperty, "ENUM", args, kwargs)


def PointerProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(PointerProperty, "POINTER", args, kwargs)


def CollectionProperty(*args, **kwargs) -> _PropertyDeferred:
    return make_deferred(CollectionProperty, "COLLECTION", args, kwargs)


def RemoveProperty(cls, *, attr: str) -> None:
    from .rna import remove_property
    remove_property(cls, attr)
