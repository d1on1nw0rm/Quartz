from __future__ import annotations

import numpy as np

from .colorutil import as_rgb, srgb_to_linear
from .model import CHANNELS
from .nodes import (BUMP_EPS, EMISSION_LINEAR, SHADER_KEYS, apply_normal_map, bump_normal, default_shader, evaluate_graph,
                    shifted_context)
from .textures import OBJECT_UNIT, sample_texture

__all__ = [
    "OUTPUT_KEYS",
    "COLOR_KEYS",
    "make_context",
    "evaluate_pbr",
    "evaluate_material",
    "display_color",
]

OUTPUT_KEYS = SHADER_KEYS + ("displacement",)
COLOR_KEYS = ("base_color", "emission", "sheen_tint")

_NEUTRAL = {"emission": 0.0, "alpha": 1.0, "transmission": 0.0, "clearcoat": 0.0, "sheen": 0.0}


def _normalize(v: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(length > 1e-12, length, 1.0)


def _finite(arr: np.ndarray) -> np.ndarray:
    return np.nan_to_num(np.asarray(arr, float), nan=0.0, posinf=0.0, neginf=0.0)


def _rows(value) -> int:
    if value is None:
        return 1
    arr = np.asarray(value, float)
    return int(arr.shape[0]) if arr.ndim >= 2 else 1


def _vec3(value, n: int, fallback) -> np.ndarray:
    if value is None:
        arr = np.asarray(fallback, float)
    else:
        arr = np.asarray(value, float)
    if arr.ndim == 0:
        arr = np.full(3, float(arr))
    if arr.ndim == 1:
        if arr.shape[0] != 3:
            raise ValueError(f"expected 3 components, got {arr.shape[0]}")
        arr = np.broadcast_to(arr, (n, 3))
    else:
        arr = arr.reshape(-1, 3)
        if arr.shape[0] == 1 and n != 1:
            arr = np.broadcast_to(arr, (n, 3))
        elif arr.shape[0] != n:
            raise ValueError(f"expected {n} rows, got {arr.shape[0]}")
    return _finite(np.array(arr, float, copy=True))


def _unit_or(v: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(v, axis=1, keepdims=True)
    ok = length > 1e-12
    return np.where(ok, v / np.where(ok, length, 1.0), fallback)


def default_tangent(normal: np.ndarray) -> np.ndarray:
    up = np.array([0.0, 1.0, 0.0])
    t = np.cross(np.broadcast_to(up, normal.shape), normal)
    weak = np.linalg.norm(t, axis=1) < 1e-6
    if np.any(weak):
        alt = np.cross(np.broadcast_to(np.array([0.0, 0.0, -1.0]), normal.shape), normal)
        t = np.where(weak[:, None], alt, t)
    return _normalize(t)


def _uv_array(value) -> np.ndarray:
    return _finite(np.atleast_1d(np.asarray(value, float)).reshape(-1))


def make_context(u, v, pos=None, normal=None, tangent=None, view=None) -> dict:
    extra = (pos, normal, tangent, view)
    scalar = np.ndim(u) == 0 and np.ndim(v) == 0 and all(x is None or np.ndim(x) <= 1 for x in extra)
    u = _uv_array(u)
    v = _uv_array(v)
    counts = {len(u), len(v)} | {_rows(x) for x in extra}
    counts.discard(1)
    if len(counts) > 1:
        raise ValueError(f"sample counts do not match: {sorted(counts)}")
    n = counts.pop() if counts else max(len(u), len(v), 1)
    if 0 in (len(u), len(v)):
        n = 0
    u = np.broadcast_to(u, (n,)).copy() if len(u) in (1, n) else u
    v = np.broadcast_to(v, (n,)).copy() if len(v) in (1, n) else v
    up = np.broadcast_to(np.array([0.0, 0.0, 1.0]), (n, 3))
    nrm = _unit_or(_vec3(normal, n, [0.0, 0.0, 1.0]), up)
    p = _vec3(pos, n, np.stack([u, v, np.zeros(n)], axis=1))
    opos = p.copy() if pos is None else p / OBJECT_UNIT
    base_t = default_tangent(nrm)
    t = base_t if tangent is None else _vec3(tangent, n, [1.0, 0.0, 0.0])
    t = _unit_or(t - nrm * np.sum(t * nrm, axis=1, keepdims=True), base_t)
    b = np.cross(nrm, t)
    vw = nrm.copy() if view is None else _unit_or(_vec3(view, n, [0.0, 0.0, 1.0]), nrm)
    return {"u": u, "v": v, "pos": p, "opos": opos, "normal": nrm, "tangent": t, "bitangent": b,
            "view": vw, "n": n, "scalar": scalar}


def _float_channel(ch: dict, ctx: dict, texture_range=None) -> np.ndarray:
    n = ctx["n"]
    value = np.full(n, float(ch.get("value", 0.0)))
    tex = ch.get("texture")
    if tex:
        _, fac = sample_texture(tex, ctx)
        if texture_range is not None:
            lo, hi = texture_range
            fac = fac * (float(hi) - float(lo)) + float(lo)
        mix = float(ch.get("mix", 1.0))
        value = value * (1.0 - mix) + fac * mix
    return value


def _color_channel(ch: dict, ctx: dict) -> np.ndarray:
    n = ctx["n"]
    value = np.broadcast_to(as_rgb(ch.get("value", [0.0, 0.0, 0.0])), (n, 3)).copy()
    tex = ch.get("texture")
    if tex:
        col, _ = sample_texture(tex, ctx)
        mix = float(ch.get("mix", 1.0))
        value = value * (1.0 - mix) + col * mix
    return value


def _height(ch: dict, ctx: dict) -> np.ndarray:
    _, fac = sample_texture(ch.get("texture"), ctx)
    return fac


def _active(ch: dict | None, optional: bool) -> bool:
    return bool(ch) and (not optional or bool(ch.get("enabled")))


def evaluate_pbr(material: dict, ctx: dict) -> dict:
    channels = material.get("channels") or {}
    out = default_shader(ctx)
    n = ctx["n"]
    for spec in CHANNELS:
        ch = channels.get(spec.key)
        if spec.kind not in ("float", "color"):
            continue
        if not _active(ch, spec.optional):
            if spec.key in _NEUTRAL:
                neutral = _NEUTRAL[spec.key]
                out[spec.key] = np.zeros((n, 3)) if spec.kind == "color" else np.full(n, neutral)
            continue
        if spec.kind == "color":
            out[spec.key] = _color_channel(ch, ctx)
        else:
            out[spec.key] = _float_channel(ch, ctx, spec.texture_range)
    em = channels.get("emission")
    if _active(em, True):
        strength = float(em.get("strength", 1.0))
        out[EMISSION_LINEAR] = srgb_to_linear(np.maximum(out["emission"], 0.0)) * strength
        out["emission"] = out["emission"] * strength
    else:
        out[EMISSION_LINEAR] = np.zeros((n, 3))
    cc = channels.get("clearcoat")
    if _active(cc, True):
        out["clearcoat_roughness"] = np.full(n, float(cc.get("roughness", 0.03)))
    sh = channels.get("sheen")
    if _active(sh, True):
        out["sheen_tint"] = np.broadcast_to(as_rgb(sh.get("tint", [1.0, 1.0, 1.0])), (n, 3)).copy()
        out["sheen_roughness"] = np.full(n, float(sh.get("roughness", 0.5)))
    for key in ("metallic", "roughness", "specular", "alpha", "transmission", "clearcoat", "sheen"):
        out[key] = np.clip(out[key], 0.0, 1.0)
    out["ior"] = np.maximum(out["ior"], 1.0)
    normal = np.array(ctx["normal"], float, copy=True)
    nm = channels.get("normal")
    if _active(nm, True) and nm.get("texture"):
        col, _ = sample_texture(nm["texture"], ctx)
        normal = apply_normal_map(ctx, normal, col, float(nm.get("strength", 1.0)), bool(nm.get("flip_green")))
    bp = channels.get("bump")
    if _active(bp, True) and bp.get("texture"):
        h0 = _height(bp, ctx)
        hu = _height(bp, shifted_context(ctx, BUMP_EPS, 0.0))
        hv = _height(bp, shifted_context(ctx, 0.0, BUMP_EPS))
        normal = bump_normal(ctx, normal, h0, hu, hv, float(bp.get("strength", 1.0)),
                             float(bp.get("distance", 0.02)), bool(bp.get("invert")))
    out["normal"] = normal
    disp = np.zeros(n)
    dp = channels.get("displacement")
    if _active(dp, True) and dp.get("texture"):
        disp = (_height(dp, ctx) - float(dp.get("midlevel", 0.5))) * float(dp.get("height", 1.0))
    out["displacement"] = disp
    return out


def _finish(result: dict, ctx: dict, linear: bool) -> dict:
    out = {}
    for key in OUTPUT_KEYS:
        value = np.asarray(result.get(key), float)
        if linear and key == "emission" and EMISSION_LINEAR in result:
            value = np.asarray(result[EMISSION_LINEAR], float)
        elif linear and key in COLOR_KEYS:
            value = srgb_to_linear(np.maximum(value, 0.0))
        out[key] = value
    if ctx.get("scalar") and ctx["n"] == 1:
        return {k: (tuple(float(x) for x in v[0]) if v.ndim == 2 else float(v[0])) for k, v in out.items()}
    return out


def evaluate_material(material: dict | None, u, v, pos=None, normal=None, tangent=None, view=None,
                      linear: bool = True) -> dict:
    ctx = make_context(u, v, pos, normal, tangent, view)
    if not material:
        result = default_shader(ctx)
        result["displacement"] = np.zeros(ctx["n"])
    elif material.get("type") == "node":
        result = evaluate_graph(material.get("graph") or {}, ctx)
    else:
        result = evaluate_pbr(material, ctx)
    return _finish(result, ctx, linear)


def display_color(material: dict | None, samples: int = 8) -> list[float]:
    if not material:
        return [0.8, 0.8, 0.8]
    g = (np.arange(samples) + 0.5) / samples
    uu, vv = np.meshgrid(g, g)
    res = evaluate_material(material, uu.ravel(), vv.ravel(), linear=False)
    col = np.mean(np.asarray(res["base_color"]), axis=0)
    return [float(np.clip(c, 0.0, 1.0)) for c in col]
