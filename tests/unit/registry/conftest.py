import inspect
import math
from types import SimpleNamespace

import pytest

_FLAG_SET = {"is_readonly", "is_hidden", "is_skip_save", "is_never_none", "is_enum_flag"}
_FIELDS = ("type", "subtype", "unit", "array_length", "array_dimensions", "default", "min", "max", "soft_min",
           "soft_max", "step", "precision", "items", "length_max", "fixed_type")


def _f32(x):
    import numpy as np
    return float(np.float32(x))


def _equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        fa, fb = _f32(a), _f32(b)
        if fa == fb:
            return True
        if math.isinf(fa) or math.isinf(fb):
            return False
        return math.isclose(fa, fb, rel_tol=1e-6)
    if isinstance(a, (set, frozenset)) or isinstance(b, (set, frozenset)):
        return set(a) == set(b)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return a == b


def _local_rna_schema_diff(cls, dump_props, *, require_all=False, divergences=None):
    from quartz.rna.properties import PropertyDef
    div = divergences or {}
    T = cls.bl_rna.identifier
    out = []
    declared = [v for v in cls.__dict__.values() if isinstance(v, PropertyDef)]
    names = {p.identifier for p in declared}

    def emit(key, msg):
        ident = key.rsplit(".", 1)[0] if key.count(".") >= 2 else key
        if key in div or ident in div:
            return
        out.append(msg)

    for p in declared:
        ident = p.identifier
        if ident not in dump_props:
            if not ident.startswith("q_"):
                emit(f"{T}.{ident}", f"{T}.{ident}: not in dump (Quartz-only props need the 'q_' prefix)")
            continue
        exp = dump_props[ident]
        got = p.to_rna_dict()
        for fld in _FIELDS:
            e = exp.get(fld, "NONE" if fld == "unit" else None)
            g = got.get(fld, "NONE" if fld == "unit" else None)
            if fld not in exp and fld not in got:
                continue
            if fld == "unit":
                if e != g:
                    emit(f"{T}.{ident}.unit", f"{T}.{ident}.unit: expected {e!r} got {g!r}")
                continue
            if (fld in exp) != (fld in got) or not _equal(e, g):
                emit(f"{T}.{ident}.{fld}", f"{T}.{ident}.{fld}: expected {e!r} got {g!r}")
        ef = sorted(set(exp.get("flags", ())) & _FLAG_SET)
        gf = sorted(set(got.get("flags", ())) & _FLAG_SET)
        if ef != gf:
            emit(f"{T}.{ident}.flags", f"{T}.{ident}.flags: expected {ef!r} got {gf!r}")
    if require_all:
        for ident in dump_props:
            if ident not in names:
                emit(f"{T}.{ident}", f"{T}.{ident}: missing (declared by Blender)")
    return sorted(out)


def _local_function_signature_diff(func, dump_func, *, divergences=None):
    div = divergences or {}
    q = func.__qualname__
    expected = [p for p in dump_func.get("params", ()) if not p.get("output")]
    enames = [p["name"] for p in expected]
    params = [p for p in inspect.signature(func).parameters.values()
              if p.name not in ("self", "cls") and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    gnames = [p.name for p in params]
    out = []

    def emit(param, msg):
        if q in div or (param and f"{q}.{param}" in div):
            return
        out.append(f"{q}: {msg}")

    for n in enames:
        if n not in gnames:
            emit(n, f"missing parameter '{n}'")
    last_expected = max((gnames.index(n) for n in enames if n in gnames), default=-1)
    for i, p in enumerate(params):
        if p.name not in enames:
            if not (p.kind == p.KEYWORD_ONLY and p.default is not p.empty and i > last_expected):
                emit(p.name, f"unexpected parameter '{p.name}'")
    common_e = [n for n in enames if n in gnames]
    common_g = [n for n in gnames if n in enames]
    if common_e != common_g:
        emit("", "parameter order differs")
    by_name = {p.name: p for p in params}
    for spec in expected:
        p = by_name.get(spec["name"])
        if p is None:
            continue
        if spec.get("required") and p.default is not p.empty:
            emit(p.name, f"parameter '{p.name}' should be required")
        if not spec.get("required") and p.default is p.empty:
            emit(p.name, f"parameter '{p.name}' should have a default")
    return sorted(out)


@pytest.fixture(scope="session")
def schema_tools():
    try:
        import quartz.testing as testing_mod
    except ModuleNotFoundError as exc:
        if not (exc.name or "").startswith("quartz"):
            raise
        return SimpleNamespace(rna_schema_diff=_local_rna_schema_diff,
                               function_signature_diff=_local_function_signature_diff, source="local")
    return SimpleNamespace(rna_schema_diff=testing_mod.rna_schema_diff,
                           function_signature_diff=testing_mod.function_signature_diff, source="quartz.testing")
