from __future__ import annotations

import importlib as _importlib
from typing import Callable

import numpy as _np

import quartz.app.msgbus as _msgbus
import quartz.rna as _rna
from quartz.errors import RegistrationError as _RegistrationError
from quartz.math import Color as _Color, Euler as _Euler, Matrix as _Matrix, Quaternion as _Quaternion, Vector as _Vector

BUILTIN_TYPE_MODULES: tuple[str, ...] = (
    "quartz.types.id", "quartz.types.blenddata", "quartz.types.object", "quartz.types.collection",
    "quartz.types.scene", "quartz.types.world", "quartz.types.wm", "quartz.depsgraph",
    "quartz.types.mesh", "quartz.types.material", "quartz.types.camera", "quartz.types.light",
    "quartz.types.image", "quartz.types.text",
    "quartz.types.operator", "quartz.types.ui", "quartz.types.prefs", "quartz.types.stubs",
    "quartz.ui",
    "quartz.contexts",
)
RNA_REEXPORTS: tuple[str, ...] = ("PropertyGroup", "PropCollection", "PropArray")

_VECTOR_SUBTYPES = frozenset({"TRANSLATION", "DIRECTION", "VELOCITY", "ACCELERATION", "XYZ", "XYZ_LENGTH",
                              "COORDINATES"})

_loaded: dict[str, object] = {}
_catalog: dict[str, object] = {}
_catalog_key: tuple[str, ...] = ()
_first_lookup_done: bool = False
_name_resolver: Callable[[str], type | None] | None = None


def _is_missing_self(exc: ModuleNotFoundError, modname: str) -> bool:
    missing = exc.name or ""
    if not missing:
        return False
    return modname == missing or modname.startswith(missing + ".")


def load_builtin_types() -> tuple[str, ...]:
    for modname in BUILTIN_TYPE_MODULES:
        if modname in _loaded:
            continue
        try:
            module = _importlib.import_module(modname)
        except ModuleNotFoundError as exc:
            if _is_missing_self(exc, modname):
                continue
            raise
        _loaded[modname] = module
    return tuple(m for m in BUILTIN_TYPE_MODULES if m in _loaded)


def _rebuild_catalog() -> None:
    global _catalog, _catalog_key
    key = tuple(m for m in BUILTIN_TYPE_MODULES if m in _loaded)
    if key == _catalog_key and _catalog:
        return
    catalog: dict[str, object] = {}
    owners: dict[str, str] = {}
    for modname in key:
        module = _loaded[modname]
        for name in getattr(module, "__all__", ()):
            obj = getattr(module, name, None)
            if not isinstance(obj, type):
                continue
            if not ("bl_rna" in obj.__dict__ or issubclass(obj, _rna.PropCollection)):
                continue
            if name in catalog and catalog[name] is not obj:
                raise _RegistrationError(f"duplicate RNA name '{name}' in modules {owners[name]} and {modname}")
            catalog[name] = obj
            owners[name] = modname
    for name in RNA_REEXPORTS:
        catalog[name] = getattr(_rna, name)
    _catalog = catalog
    _catalog_key = key


def install_hooks() -> None:
    _rna.hooks.install(wrap_array=wrap_array, on_property_changed=on_property_changed)


def _with_change_notification(values, pdef, inst, on_write):
    if pdef.meta.get("virtual_get") is None:
        return on_write

    def write():
        on_write()
        on_change = getattr(inst, "_q_on_change", None)
        if on_change is not None:
            on_change(pdef)
        _rna.hooks.on_property_changed(inst, pdef)
    return write


def wrap_array(values: _np.ndarray, pdef, inst: object, on_write: Callable[[], None]) -> object:
    write = _with_change_notification(values, pdef, inst, on_write)
    if getattr(pdef, "kind", "") == "FLOAT" and isinstance(values, _np.ndarray):
        subtype = pdef.subtype
        shape = values.shape
        if subtype in _VECTOR_SUBTYPES and len(shape) == 1 and 2 <= shape[0] <= 4:
            return _Vector._q_wrap(values, owner=inst, on_write=write)
        if subtype == "EULER" and len(shape) == 1 and shape[0] == 3:
            order_fn = pdef.meta.get("euler_order")
            order = order_fn(inst) if order_fn is not None else "XYZ"
            return _Euler._q_wrap(values, owner=inst, on_write=write, order=order)
        if subtype == "QUATERNION" and len(shape) == 1 and shape[0] == 4:
            return _Quaternion._q_wrap(values, owner=inst, on_write=write)
        if subtype in ("COLOR", "COLOR_GAMMA") and len(shape) == 1 and shape[0] == 3:
            return _Color._q_wrap(values, owner=inst, on_write=write)
        if subtype == "MATRIX" and len(shape) == 2:
            return _Matrix._q_wrap(values, owner=inst, on_write=write)
    return _rna.PropArray(values, on_write=write, owner=inst, pdef=pdef)


def on_property_changed(inst: object, pdef) -> None:
    _msgbus.notify_changed(inst, pdef.identifier)


def set_name_resolver(fn: Callable[[str], type | None] | None) -> None:
    global _name_resolver
    _name_resolver = fn


def resolve_name(name: str) -> type | None:
    fn = _name_resolver
    return fn(name) if fn is not None else None


def __getattr__(name: str) -> object:
    global _first_lookup_done
    if name.startswith("_"):
        raise AttributeError(f"module 'quartz.types' has no attribute '{name}'")
    if not _first_lookup_done:
        _first_lookup_done = True
        load_builtin_types()
    _rebuild_catalog()
    if name in _catalog:
        return _catalog[name]
    before = len(_loaded)
    load_builtin_types()
    if len(_loaded) != before:
        _rebuild_catalog()
        if name in _catalog:
            return _catalog[name]
    resolved = resolve_name(name)
    if resolved is not None:
        return resolved
    raise AttributeError(f"module 'quartz.types' has no attribute '{name}'")


def __dir__() -> list[str]:
    load_builtin_types()
    _rebuild_catalog()
    return sorted(set(_catalog) | set(RNA_REEXPORTS))
