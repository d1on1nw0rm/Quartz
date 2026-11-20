from __future__ import annotations

import itertools
import sys
from typing import Any

from ..props import _PropertyDeferred
from . import hooks

_DYNAMIC_SEQ = itertools.count()


def own_annotations(klass: type) -> dict[str, object]:
    result = {}
    try:
        import annotationlib
        mod = sys.modules.get(klass.__module__)
        g = dict(vars(mod)) if mod else {}
        l = dict(g)
        l.update(vars(klass))
        try:
            ann = annotationlib.get_annotations(klass, format=annotationlib.Format.VALUE, eval_str=True, globals=g, locals=l)
        except Exception:
            try:
                ann = annotationlib.get_annotations(klass, format=annotationlib.Format.FORWARDREF, eval_str=True, globals=g, locals=l)
            except Exception:
                ann = annotationlib.get_annotations(klass, format=annotationlib.Format.FORWARDREF, globals=g, locals=l)
        for name, val in ann.items():
            if isinstance(val, str):
                try:
                    mod = sys.modules.get(klass.__module__)
                    ns = dict(vars(mod)) if mod else {}
                    ns.update(vars(klass))
                    val = eval(val, ns)
                except Exception:
                    continue
            if type(val).__name__ == "ForwardRef":
                try:
                    val = val.evaluate(globals_=vars(sys.modules.get(klass.__module__)) if sys.modules.get(klass.__module__) else {}, locals_=dict(vars(klass)))
                except Exception:
                    try:
                        val = val.evaluate()
                    except Exception:
                        continue
            result[name] = val
    except Exception:
        raw = klass.__dict__.get("__annotations__", {})
        for name, val in raw.items():
            if isinstance(val, str):
                try:
                    mod = sys.modules.get(klass.__module__)
                    ns = dict(vars(mod)) if mod else {}
                    ns.update(vars(klass))
                    val = eval(val, ns)
                except Exception:
                    continue
            result[name] = val
    if not result:
        raw = klass.__dict__.get("__annotations__", {})
        for name, val in raw.items():
            if isinstance(val, str):
                try:
                    mod = sys.modules.get(klass.__module__)
                    ns = dict(vars(mod)) if mod else {}
                    ns.update(vars(klass))
                    val = eval(val, ns)
                except Exception:
                    continue
            result[name] = val
    return result


def collect_annotations(cls: type) -> dict[str, _PropertyDeferred]:
    result: dict[str, _PropertyDeferred] = {}
    for base in reversed(cls.__mro__):
        if base is object:
            continue
        if base is not cls and base.__dict__.get("_q_builtin", False):
            continue
        for name, val in own_annotations(base).items():
            if isinstance(val, _PropertyDeferred):
                result[name] = val
    return result


def _is_pdef(value: object) -> bool:
    from .properties import PropertyDef
    return isinstance(value, PropertyDef)


def install_properties(cls: type) -> list:
    from .properties import build_property
    installed: list = []
    try:
        for name, deferred in collect_annotations(cls).items():
            pdef = build_property(name, deferred, cls)
            type.__setattr__(cls, name, pdef)
            installed.append(pdef)
    except Exception:
        for pdef in installed:
            if cls.__dict__.get(pdef.identifier) is pdef:
                type.__delattr__(cls, pdef.identifier)
        raise
    type.__setattr__(cls, "_q_installed", [p.identifier for p in installed])
    return installed


def uninstall_properties(cls: type) -> None:
    names = list(cls.__dict__.get("_q_installed", ())) + list(cls.__dict__.get("_q_dynamic", ()))
    for name in names:
        if _is_pdef(cls.__dict__.get(name)):
            type.__delattr__(cls, name)
    type.__setattr__(cls, "_q_installed", [])
    type.__setattr__(cls, "_q_dynamic", [])


def define_property(cls: type, identifier: str, deferred: _PropertyDeferred):
    from .properties import build_property
    pdef = build_property(identifier, deferred, cls)
    pdef._q_dynamic_seq = next(_DYNAMIC_SEQ)
    type.__setattr__(cls, identifier, pdef)
    if identifier not in cls.__dict__.get("_q_installed", ()):
        dynamic = list(cls.__dict__.get("_q_dynamic", ()))
        if identifier in dynamic:
            dynamic.remove(identifier)
        dynamic.append(identifier)
        type.__setattr__(cls, "_q_dynamic", dynamic)
    hooks.on_type_property_defined(cls, identifier)
    return pdef


def remove_property(cls: type, identifier: str) -> None:
    if not _is_pdef(cls.__dict__.get(identifier)):
        raise AttributeError(f"'{cls.__name__}' has no property '{identifier}' to remove")
    type.__delattr__(cls, identifier)
    for key in ("_q_dynamic", "_q_installed"):
        names = cls.__dict__.get(key)
        if names is not None and identifier in names:
            type.__setattr__(cls, key, [n for n in names if n != identifier])
    hooks.on_type_property_removed(cls, identifier)


def get_property(cls_or_inst, identifier: str):
    cls = cls_or_inst if isinstance(cls_or_inst, type) else type(cls_or_inst)
    for c in cls.__mro__:
        if identifier in c.__dict__:
            val = c.__dict__[identifier]
            if _is_pdef(val):
                return val
    return None


def iter_properties(cls_or_inst):
    cls = cls_or_inst if isinstance(cls_or_inst, type) else type(cls_or_inst)
    declared: list[str] = []
    dynamic: list[tuple[int, int, str]] = []
    latest: dict[str, object] = {}
    for depth, c in enumerate(reversed(cls.__mro__)):
        own = c.__dict__
        dyn_names = list(own.get("_q_dynamic", ()))
        for name in list(own.get("_q_installed", ())) + [n for n in own if n not in dyn_names]:
            if _is_pdef(own.get(name)):
                latest[name] = own[name]
                if name not in declared:
                    declared.append(name)
        for pos, name in enumerate(dyn_names):
            pdef = own.get(name)
            if _is_pdef(pdef):
                latest[name] = pdef
                dynamic.append((getattr(pdef, "_q_dynamic_seq", -1), depth * 100000 + pos, name))
    dynamic.sort()
    order = list(declared)
    for _, _, name in dynamic:
        if name in order:
            order.remove(name)
        order.append(name)
    for name in order:
        yield latest[name]
