from __future__ import annotations

import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Iterator, Mapping, Sequence

from quartz.errors import (
    ClassValidationError,
    MissingClassAttributeError,
    RegistrationError,
    RegistrationRuntimeError,
)
from quartz.rna import hooks
from quartz.rna.annotations import (
    define_property,
    get_property,
    install_properties,
    remove_property,
    uninstall_properties,
)
from quartz.rna.properties import PropertyDef
from quartz.rna.rnainfo import RNAStruct
from quartz.rna.struct import PropertyGroup, Struct

__all__ = [
    "register_base", "registrable_base_of", "iter_bases", "base_callbacks", "register_class",
    "unregister_class", "is_registered", "rna_name_of", "lookup", "operator_class", "operator_rna_name",
    "operator_idname_py", "validate_operator_idname", "iter_classes", "iter_operators",
    "operator_submodules", "counts_by_base", "owner_scope", "current_owner", "owner_of",
    "classes_owned_by", "type_props_owned_by", "set_missing_type_resolver", "subscribe", "snapshot",
    "restore", "install_hooks",
]

_VALID_KINDS = ("OPERATOR", "UI", "GENERIC")
_IDNAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_.")


@dataclass
class _BaseInfo:
    base: type
    required: tuple[str, ...]
    rna_name: Callable[[type], str] | None
    validate: Callable[[type], None] | None
    kind: str
    callbacks: Mapping[str, tuple[bool, bool]]
    prepare: Callable[[type, str], None] | None
    cleanup: Callable[[type], None] | None


@dataclass
class _Entry:
    rna_name: str
    owner: str | None
    base: type
    kind: str
    idname_py: str | None = None


@dataclass(frozen=True)
class _Snapshot:
    classes: tuple[tuple[type, str, str | None], ...]
    props: tuple[tuple[type, str, object, str | None], ...]
    extensions: object = None
    has_extensions: bool = False


_BASES: dict[type, _BaseInfo] = {}
_REGISTERED: dict[type, _Entry] = {}
_BY_NAME: dict[str, type] = {}
_BY_IDNAME: dict[str, type] = {}
_OWNER_STACK: list[str | None] = []
_PROP_RECORDS: list[tuple[type, str, object, str | None]] = []
_SUBSCRIBERS: list[list] = []
_RESOLVER: list[Callable[[str], type | None] | None] = [None]


def register_base(base: type, *, required: Sequence[str] = (), rna_name: Callable[[type], str] | None = None,
                  validate: Callable[[type], None] | None = None, kind: str = "GENERIC",
                  callbacks: Mapping[str, tuple[bool, bool]] | None = None,
                  prepare: Callable[[type, str], None] | None = None,
                  cleanup: Callable[[type], None] | None = None) -> None:
    if not (isinstance(base, type) and issubclass(base, Struct) and "bl_rna" in base.__dict__):
        raise TypeError(f"register_base() expects a builtin Struct subclass, not {base!r}")
    if kind not in _VALID_KINDS:
        raise ValueError(f"register_base(): invalid kind {kind!r}")
    cbs = {str(k): (bool(v[0]), bool(v[1])) for k, v in dict(callbacks or {}).items()}
    _BASES[base] = _BaseInfo(base=base, required=tuple(required), rna_name=rna_name, validate=validate,
                             kind=kind, callbacks=MappingProxyType(cbs), prepare=prepare, cleanup=cleanup)


def registrable_base_of(cls: type) -> type | None:
    if not isinstance(cls, type):
        return None
    for klass in cls.__mro__:
        if klass in _BASES:
            return klass
    return None


def iter_bases() -> Iterator[type]:
    return iter(list(_BASES))


def base_callbacks(base: type) -> Mapping[str, tuple[bool, bool]]:
    return _BASES[base].callbacks


def operator_rna_name(idname: str) -> str:
    if not isinstance(idname, str) or "." not in idname:
        raise ValueError(f"operator_rna_name(): invalid operator idname {idname!r} (expected 'module.name')")
    mod, op = idname.split(".", 1)
    return f"{mod.upper()}_OT_{op}"


def operator_idname_py(rna_name: str) -> str:
    if not isinstance(rna_name, str) or "_OT_" not in rna_name:
        raise ValueError(f"operator_idname_py(): {rna_name!r} is not an operator RNA name (no '_OT_')")
    head, tail = rna_name.split("_OT_", 1)
    return f"{head.lower()}.{tail}"


def validate_operator_idname(idname: str, class_name: str) -> None:
    s = idname[:63]

    def fail(reason: str) -> RegistrationRuntimeError:
        return RegistrationRuntimeError(
            f"Registering operator class '{class_name}', invalid bl_idname '{s}', {reason}")

    for i, ch in enumerate(s):
        if ch not in _IDNAME_CHARS:
            raise fail(f"Invalid character at position {i}")
    if s.count(".") != 1:
        raise fail("Must contain 1 '.' character")
    if len(s) > 60:
        raise fail("Identifier too long, maximum length is 60")


def _default_rna_name(cls: type) -> str:
    idname = getattr(cls, "bl_idname", "")
    if isinstance(idname, str) and idname:
        return idname
    return cls.__name__


def _computed_rna_name(cls: type, info: _BaseInfo) -> str:
    if info.kind == "OPERATOR":
        return operator_rna_name(getattr(cls, "bl_idname", cls.__name__))
    if info.rna_name is not None:
        return info.rna_name(cls)
    return cls.__name__


def rna_name_of(cls: type) -> str:
    entry = _REGISTERED.get(cls) if isinstance(cls, type) else None
    if entry is not None and "bl_rna" in cls.__dict__:
        return entry.rna_name
    fallback = getattr(cls, "__name__", None)
    if not isinstance(fallback, str):
        fallback = type(cls).__name__
    base = registrable_base_of(cls)
    if base is None:
        return fallback
    info = _BASES[base]
    try:
        if info.kind == "OPERATOR":
            idname = getattr(cls, "bl_idname", cls.__name__)
            if isinstance(idname, str) and "." in idname:
                return operator_rna_name(idname)
            return fallback
        name = _computed_rna_name(cls, info)
        return name if isinstance(name, str) and name else fallback
    except Exception:
        return fallback


def is_registered(cls: type) -> bool:
    return isinstance(cls, type) and cls in _REGISTERED and "bl_rna" in cls.__dict__


def lookup(rna_name: str, *, resolve: bool = True) -> type | None:
    cls = _BY_NAME.get(rna_name)
    if cls is not None:
        return cls
    fn = _RESOLVER[0]
    if resolve and fn is not None:
        return fn(rna_name)
    return None


def operator_class(idname: str) -> type | None:
    if not isinstance(idname, str):
        return None
    if "_OT_" in idname:
        idname = operator_idname_py(idname)
    return _BY_IDNAME.get(idname)


def iter_classes(base: type | None = None) -> Iterator[type]:
    classes = list(_REGISTERED)
    if base is None:
        return iter(classes)
    return iter([c for c in classes if issubclass(c, base)])


def iter_operators() -> Iterator[tuple[str, type]]:
    return iter([(e.idname_py, c) for c, e in list(_REGISTERED.items()) if e.kind == "OPERATOR"])


def operator_submodules() -> list[str]:
    return sorted({e.idname_py.split(".", 1)[0] for e in _REGISTERED.values() if e.kind == "OPERATOR"})


def _is_quartz_owner(owner: str | None) -> bool:
    return isinstance(owner, str) and owner.startswith("quartz.")


def counts_by_base() -> dict[str, int]:
    out: dict[str, int] = {}
    for entry in _REGISTERED.values():
        if _is_quartz_owner(entry.owner):
            continue
        out[entry.base.__name__] = out.get(entry.base.__name__, 0) + 1
    return out


@contextmanager
def owner_scope(owner: str | None) -> Iterator[None]:
    depth = len(_OWNER_STACK)
    _OWNER_STACK.append(owner)
    try:
        yield
    finally:
        del _OWNER_STACK[depth:]


def current_owner() -> str | None:
    return _OWNER_STACK[-1] if _OWNER_STACK else None


def owner_of(cls: type) -> str | None:
    entry = _REGISTERED.get(cls) if isinstance(cls, type) else None
    return entry.owner if entry is not None else None


def classes_owned_by(owner: str) -> list[type]:
    return [c for c, e in _REGISTERED.items() if e.owner == owner]


def _record_present(rec: tuple) -> bool:
    cls, ident = rec[0], rec[1]
    return isinstance(cls.__dict__.get(ident), PropertyDef)


def type_props_owned_by(owner: str) -> list[tuple[type, str]]:
    return [(r[0], r[1]) for r in list(_PROP_RECORDS) if r[3] == owner and _record_present(r)]


def set_missing_type_resolver(fn: Callable[[str], type | None] | None) -> None:
    _RESOLVER[0] = fn


def subscribe(callback: Callable[[str, type], None]) -> Callable[[], None]:
    cell = [callback]
    _SUBSCRIBERS.append(cell)

    def cancel() -> None:
        if cell in _SUBSCRIBERS:
            _SUBSCRIBERS.remove(cell)
        cell.clear()
    return cancel


def _notify(event: str, cls: type) -> None:
    for cell in list(_SUBSCRIBERS):
        if not cell:
            continue
        try:
            cell[0](event, cls)
        except Exception:
            traceback.print_exc(file=sys.stderr)


def _on_defined(cls: type, identifier: str) -> None:
    pdef = get_property(cls, identifier)
    deferred = pdef.deferred if pdef is not None else None
    _PROP_RECORDS[:] = [r for r in _PROP_RECORDS if not (r[0] is cls and r[1] == identifier)]
    _PROP_RECORDS.append((cls, identifier, deferred, current_owner()))


def _on_removed(cls: type, identifier: str) -> None:
    _PROP_RECORDS[:] = [r for r in _PROP_RECORDS if not (r[0] is cls and r[1] == identifier)]


def install_hooks() -> None:
    hooks.install(on_type_property_defined=_on_defined, on_type_property_removed=_on_removed)


def _missing_bl_rna(func: str, obj: object) -> RegistrationRuntimeError:
    return RegistrationRuntimeError(
        f"{func}(...):, missing bl_rna attribute from '{type(obj).__name__}' instance (may not be registered)")


def _enum_listing(items: Sequence[str]) -> str:
    return ", ".join(repr(i) for i in items)


def _check_class_enums(cls: type, base: type) -> None:
    spec = base.__dict__.get("_q_class_enums") or {}
    for attr, (mode, items) in spec.items():
        if not hasattr(cls, attr):
            continue
        value = getattr(cls, attr)
        if mode == "SET":
            if not isinstance(value, (set, frozenset)):
                raise ClassValidationError(
                    f"validating class: {cls.__name__}.{attr} expected a set, not {type(value).__name__}")
            for v in sorted(value, key=str):
                if v not in items:
                    raise ClassValidationError(f'validating class: enum "{v}" not found in ({_enum_listing(items)})')
        else:
            if not isinstance(value, str):
                raise ClassValidationError(
                    f"validating class: {cls.__name__}.{attr} expected a string, not {type(value).__name__}")
            if value not in items:
                raise ClassValidationError(f'validating class: enum "{value}" not found in ({_enum_listing(items)})')


def _has_tag(name: str, tag: str) -> bool:
    token = f"_{tag}_"
    start = name.find(token)
    while start != -1:
        if start > 0 and start + len(token) < len(name):
            return True
        start = name.find(token, start + 1)
    return False


def _defines_above(cls: type, base: type, attr: str) -> bool:
    for klass in cls.__mro__:
        if klass is base:
            return False
        if attr in klass.__dict__:
            return True
    return False


def _validate(cls: type, base: type, info: _BaseInfo) -> None:
    for name in info.required:
        if not hasattr(cls, name):
            raise MissingClassAttributeError(
                f'expected {base.__name__}, {cls.__name__} class to have an "{name}" attribute')
    _check_class_enums(cls, base)
    if info.kind == "OPERATOR":
        idname = getattr(cls, "bl_idname", cls.__name__)
        if not isinstance(idname, str):
            raise ClassValidationError(
                f"validating class: {cls.__name__}.bl_idname expected a string, not {type(idname).__name__}")
        validate_operator_idname(idname, cls.__name__)
    if base.__dict__.get("_q_has_parent_id", False):
        parent = getattr(cls, "bl_parent_id", "")
        if parent:
            found = lookup(parent) if isinstance(parent, str) else None
            if not (isinstance(found, type) and issubclass(found, base) and is_registered(found)):
                raise RegistrationRuntimeError(
                    f"Registering panel class: parent '{parent}' for '{rna_name_of(cls)}' not found")
    if info.validate is not None:
        info.validate(cls)
    tag = base.__dict__.get("_q_name_tag")
    if info.kind == "UI" and tag:
        name = rna_name_of(cls)
        if not _has_tag(name, tag):
            print(f"Warning: '{name}' does not contain '_{tag}_' with prefix and suffix", file=sys.stderr)


def _index(cls: type, rna_name: str, owner: str | None, base: type, info: _BaseInfo) -> None:
    idname_py = operator_idname_py(rna_name) if info.kind == "OPERATOR" else None
    _REGISTERED[cls] = _Entry(rna_name=rna_name, owner=owner, base=base, kind=info.kind, idname_py=idname_py)
    _BY_NAME[rna_name] = cls
    if idname_py is not None:
        _BY_IDNAME[idname_py] = cls


def _attach(cls: type, rna_name: str, owner: str | None) -> None:
    base = registrable_base_of(cls)
    info = _BASES[base]
    install_properties(cls)
    if info.prepare is not None:
        try:
            info.prepare(cls, rna_name)
        except BaseException:
            uninstall_properties(cls)
            raise
    type.__setattr__(cls, "bl_rna", RNAStruct(cls, rna_name))
    _index(cls, rna_name, owner, base, info)


def register_class(cls: type) -> None:
    base = registrable_base_of(cls)
    if base is None:
        raise _missing_bl_rna("register_class", cls)
    if "bl_rna" in cls.__dict__:
        raise RegistrationError(f"register_class(...): already registered as a subclass '{cls.__name__}'")
    info = _BASES[base]
    _validate(cls, base, info)
    rna_name = _computed_rna_name(cls, info)
    previous = _BY_NAME.get(rna_name)
    if previous is not None and previous is not cls:
        unregister_class(previous)
    _attach(cls, rna_name, current_owner())
    if _defines_above(cls, base, "register"):
        cls.register()
    _notify("register", cls)


def _detach(cls: type) -> None:
    entry = _REGISTERED.pop(cls)
    if _BY_NAME.get(entry.rna_name) is cls:
        del _BY_NAME[entry.rna_name]
    if entry.idname_py is not None and _BY_IDNAME.get(entry.idname_py) is cls:
        del _BY_IDNAME[entry.idname_py]
    uninstall_properties(cls)
    if "bl_rna" in cls.__dict__:
        type.__delattr__(cls, "bl_rna")
    info = _BASES.get(entry.base)
    if info is not None and info.cleanup is not None:
        info.cleanup(cls)


def unregister_class(cls: type) -> None:
    if not is_registered(cls):
        raise _missing_bl_rna("unregister_class", cls)
    base = _REGISTERED[cls].base
    error: BaseException | None = None
    if _defines_above(cls, base, "unregister"):
        try:
            cls.unregister()
        except BaseException as exc:
            error = exc
    _detach(cls)
    _notify("unregister", cls)
    if error is not None:
        raise error


def _ui_module():
    try:
        import quartz.types.ui as ui_mod
    except ModuleNotFoundError:
        return None
    return ui_mod


def snapshot() -> object:
    classes = tuple((c, e.rna_name, e.owner) for c, e in _REGISTERED.items())
    props = tuple(r for r in _PROP_RECORDS if _record_present(r))
    ui_mod = _ui_module()
    if ui_mod is None:
        return _Snapshot(classes, props)
    return _Snapshot(classes, props, ui_mod.extensions_snapshot(), True)


def restore(snap: object) -> None:
    if not isinstance(snap, _Snapshot):
        raise TypeError("restore() expects an object returned by registry.snapshot()")
    wanted = {c: (name, owner) for c, name, owner in snap.classes}
    for cls in reversed(list(_REGISTERED)):
        if cls not in wanted:
            _detach(cls)
            _notify("unregister", cls)
    for cls, name, owner in snap.classes:
        if not is_registered(cls):
            occupant = _BY_NAME.get(name)
            if occupant is not None and occupant is not cls:
                _detach(occupant)
                _notify("unregister", occupant)
            if "bl_rna" in cls.__dict__:
                type.__delattr__(cls, "bl_rna")
            _attach(cls, name, owner)
            _notify("register", cls)
    snap_keys = {(r[0], r[1]): r for r in snap.props}
    for rec in list(_PROP_RECORDS):
        cls, ident = rec[0], rec[1]
        if not _record_present(rec):
            continue
        target = snap_keys.get((cls, ident))
        if target is None or cls.__dict__[ident].deferred is not target[2]:
            remove_property(cls, ident)
    for cls, ident, deferred, _owner in snap.props:
        current = cls.__dict__.get(ident)
        if isinstance(current, PropertyDef) and current.deferred is deferred:
            continue
        if "bl_rna" in cls.__dict__ and deferred is not None:
            define_property(cls, ident, deferred)
    _PROP_RECORDS[:] = list(snap.props)
    entries = {c: _REGISTERED[c] for c in _REGISTERED}
    _REGISTERED.clear()
    for cls, name, owner in snap.classes:
        entry = entries[cls]
        entry.owner = owner
        _REGISTERED[cls] = entry
    if snap.has_extensions:
        ui_mod = _ui_module()
        if ui_mod is not None:
            ui_mod.extensions_restore(snap.extensions)


register_base(PropertyGroup, kind="GENERIC", rna_name=lambda cls: cls.__name__, callbacks={})
