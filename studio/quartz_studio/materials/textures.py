from __future__ import annotations

import copy
import os

import numpy as np

from .colorutil import as_rgb, luminance, smoothstep
from .noise import NOISE_TYPES, fractal, rand01, voronoi
from .params import Param, coerce, defaults_of
from .ramp import DEFAULT_RAMP, INTERPOLATIONS, evaluate_ramp

__all__ = [
    "TEXTURE_TYPES",
    "TEXTURE_LABELS",
    "GRADIENT_TYPES",
    "VORONOI_FEATURES",
    "VORONOI_METRICS",
    "EXTENSIONS",
    "texture_params",
    "new_texture",
    "set_texture_param",
    "sample_texture",
    "checker_mask",
    "gradient_value",
    "brick_pattern",
    "voronoi_pattern",
    "load_image",
    "sample_image",
    "clear_image_cache",
    "MISSING_COLOR",
    "OBJECT_UNIT",
    "IMAGE_SEARCH_PATHS",
    "add_image_search_path",
    "resolve_image_path",
]

GRADIENT_TYPES = ("linear", "vertical", "diagonal", "radial", "spherical", "quadratic", "easing", "box")
VORONOI_FEATURES = ("f1", "f2", "f2_f1")
VORONOI_METRICS = ("euclidean", "manhattan", "chebyshev")
EXTENSIONS = ("repeat", "extend", "clip", "mirror")
SPACES = ("uv", "object")
MISSING_COLOR = (1.0, 0.0, 1.0)
OBJECT_UNIT = 100.0
IMAGE_SEARCH_PATHS: list = []

_MAPPING = (
    Param("tiling", "Tiling", "vec2", [1.0, 1.0], step=0.1),
    Param("offset", "Offset", "vec2", [0.0, 0.0], step=0.01),
)

_SPACE = Param("space", "Space", "enum", "uv", options=SPACES, option_labels=("UV", "Object"))

TEXTURE_LABELS = {
    "checker": "Checker",
    "noise": "Noise",
    "gradient": "Gradient",
    "brick": "Brick",
    "voronoi": "Voronoi",
    "image": "Image",
}

_SPECS: dict[str, tuple] = {
    "checker": (
        Param("color1", "Color 1", "color", [0.9, 0.9, 0.9]),
        Param("color2", "Color 2", "color", [0.1, 0.1, 0.1]),
        Param("scale", "Scale", "float", 8.0, 0.0, 1000.0, step=0.5, soft_max=64.0),
        _SPACE,
    ),
    "noise": (
        Param("color1", "Color 1", "color", [0.0, 0.0, 0.0]),
        Param("color2", "Color 2", "color", [1.0, 1.0, 1.0]),
        Param("noise_type", "Type", "enum", "fbm", options=NOISE_TYPES,
              option_labels=("Value", "Perlin", "FBM", "Turbulence", "Ridged")),
        Param("scale", "Scale", "float", 4.0, 0.0, 1000.0, step=0.5, soft_max=64.0),
        Param("detail", "Detail", "float", 4.0, 0.0, 12.0, step=0.5),
        Param("roughness", "Roughness", "float", 0.5, 0.0, 1.0),
        Param("lacunarity", "Lacunarity", "float", 2.0, 1.0, 6.0, step=0.1),
        Param("distortion", "Distortion", "float", 0.0, 0.0, 10.0, step=0.1),
        Param("contrast", "Contrast", "float", 1.0, 0.0, 8.0, step=0.1),
        Param("seed", "Seed", "int", 0, 0, 9999, step=1),
        _SPACE,
    ),
    "gradient": (
        Param("gradient_type", "Type", "enum", "linear", options=GRADIENT_TYPES),
        Param("ramp", "Colors", "ramp", copy.deepcopy(DEFAULT_RAMP)),
        Param("interpolation", "Interpolation", "enum", "linear", options=INTERPOLATIONS),
        Param("repeat", "Repeat", "bool", False),
    ),
    "brick": (
        Param("color1", "Brick 1", "color", [0.62, 0.24, 0.16]),
        Param("color2", "Brick 2", "color", [0.48, 0.18, 0.12]),
        Param("mortar_color", "Mortar", "color", [0.78, 0.76, 0.72]),
        Param("bricks", "Bricks per Row", "float", 4.0, 0.1, 256.0, step=0.5),
        Param("rows", "Rows", "float", 8.0, 0.1, 256.0, step=0.5),
        Param("mortar", "Mortar Size", "float", 0.08, 0.0, 0.5),
        Param("smooth", "Mortar Smooth", "float", 0.02, 0.0, 0.5),
        Param("row_offset", "Row Offset", "float", 0.5, 0.0, 1.0),
        Param("variation", "Variation", "float", 0.6, 0.0, 1.0),
        Param("seed", "Seed", "int", 0, 0, 9999, step=1),
    ),
    "voronoi": (
        Param("color1", "Color 1", "color", [0.0, 0.0, 0.0]),
        Param("color2", "Color 2", "color", [1.0, 1.0, 1.0]),
        Param("feature", "Feature", "enum", "f1", options=VORONOI_FEATURES,
              option_labels=("F1", "F2", "F2 - F1")),
        Param("metric", "Metric", "enum", "euclidean", options=VORONOI_METRICS),
        Param("coloring", "Coloring", "enum", "distance", options=("distance", "cells")),
        Param("scale", "Scale", "float", 5.0, 0.0, 1000.0, step=0.5, soft_max=64.0),
        Param("randomness", "Randomness", "float", 1.0, 0.0, 1.0),
        Param("seed", "Seed", "int", 0, 0, 9999, step=1),
        _SPACE,
    ),
    "image": (
        Param("path", "File", "path", ""),
        Param("interpolation", "Interpolation", "enum", "linear", options=("linear", "closest")),
        Param("extension", "Extension", "enum", "repeat", options=EXTENSIONS),
        Param("use_alpha", "Value From Alpha", "bool", False),
    ),
}

TEXTURE_TYPES = tuple(_SPECS)


def texture_params(kind: str) -> tuple:
    if kind not in _SPECS:
        raise KeyError(f"unknown texture type {kind!r}")
    return _SPECS[kind] + _MAPPING


def new_texture(kind: str, **values) -> dict:
    tex = {"type": kind}
    tex.update(defaults_of(texture_params(kind)))
    for key, value in values.items():
        set_texture_param(tex, key, value)
    return tex


def set_texture_param(tex: dict, key: str, value) -> dict:
    for p in texture_params(tex["type"]):
        if p.key == key:
            tex[key] = coerce(p, value)
            return tex
    raise KeyError(f"texture {tex['type']!r} has no parameter {key!r}")


def _get(tex: dict, p: Param):
    value = tex.get(p.key)
    if value is None:
        return copy.deepcopy(p.default)
    return value


def _values(tex: dict) -> dict:
    return {p.key: _get(tex, p) for p in texture_params(tex["type"])}


def _mapped_uv(vals: dict, ctx: dict) -> tuple[np.ndarray, np.ndarray]:
    tu, tv = vals.get("tiling", [1.0, 1.0])
    ou, ov = vals.get("offset", [0.0, 0.0])
    return ctx["u"] * float(tu) + float(ou), ctx["v"] * float(tv) + float(ov)


def _coords(vals: dict, ctx: dict) -> tuple[np.ndarray, int]:
    if vals.get("space") == "object":
        p = np.array(ctx.get("opos", ctx["pos"]), float, copy=True)
        tu, tv = vals.get("tiling", [1.0, 1.0])
        ou, ov = vals.get("offset", [0.0, 0.0])
        p[:, 0] = p[:, 0] * float(tu) + float(ou)
        p[:, 1] = p[:, 1] * float(tv) + float(ov)
        return p, 3
    u, v = _mapped_uv(vals, ctx)
    return np.stack([u, v, np.zeros_like(u)], axis=1), 2


def checker_mask(p: np.ndarray, scale: float, dims: int = 2) -> np.ndarray:
    q = np.floor(np.asarray(p, float) * float(scale) + 1e-9).astype(np.int64)
    s = q[:, 0] + q[:, 1] + (q[:, 2] if dims == 3 else 0)
    return (s & 1).astype(float)


def gradient_value(u: np.ndarray, v: np.ndarray, kind: str, repeat: bool = False) -> np.ndarray:
    if repeat:
        u = u - np.floor(u)
        v = v - np.floor(v)
    if kind == "vertical":
        t = v
    elif kind == "diagonal":
        t = (u + v) * 0.5
    elif kind == "radial":
        t = np.arctan2(v - 0.5, u - 0.5) / (2.0 * np.pi) + 0.5
    elif kind == "spherical":
        t = 1.0 - np.sqrt((u - 0.5) ** 2 + (v - 0.5) ** 2) * 2.0
    elif kind == "quadratic":
        t = np.clip(u, 0.0, 1.0) ** 2
    elif kind == "easing":
        t = smoothstep(0.0, 1.0, u)
    elif kind == "box":
        t = 1.0 - np.maximum(np.abs(u - 0.5), np.abs(v - 0.5)) * 2.0
    else:
        t = u
    return np.clip(t, 0.0, 1.0)


def brick_pattern(u: np.ndarray, v: np.ndarray, bricks: float, rows: float, mortar: float,
                  smooth: float, row_offset: float, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    y = v * float(rows)
    row = np.floor(y).astype(np.int64)
    shift = np.where((row & 1) == 1, float(row_offset), 0.0)
    x = u * float(bricks) + shift
    col = np.floor(x).astype(np.int64)
    fx = x - col
    fy = y - row
    aspect = float(bricks) / max(float(rows), 1e-9)
    dx = np.minimum(fx, 1.0 - fx) / max(aspect, 1e-9)
    dy = np.minimum(fy, 1.0 - fy)
    d = np.minimum(dx, dy)
    half = float(mortar) * 0.5
    edge = max(float(smooth), 1e-6)
    mask = 1.0 - smoothstep(half, half + edge, d) if half > 0.0 else np.zeros_like(d)
    rnd = rand01(col, row, np.zeros_like(col), int(seed), 9)
    return mask, rnd


def voronoi_pattern(p: np.ndarray, dims: int, feature: str, metric: str, randomness: float,
                    seed: int) -> dict:
    res = voronoi(p, randomness, metric, int(seed), dims)
    if feature == "f2":
        dist = res["f2"]
    elif feature == "f2_f1":
        dist = res["f2"] - res["f1"]
    else:
        dist = res["f1"]
    res["distance"] = dist
    return res


_IMAGE_CACHE: dict = {}


def clear_image_cache() -> None:
    _IMAGE_CACHE.clear()


def add_image_search_path(folder: str) -> None:
    if not folder:
        return
    folder = os.path.abspath(folder)
    if folder in IMAGE_SEARCH_PATHS:
        IMAGE_SEARCH_PATHS.remove(folder)
    IMAGE_SEARCH_PATHS.insert(0, folder)


def _project_dir() -> str | None:
    try:
        from ..project import current_path
        path = current_path()
    except Exception:
        return None
    return os.path.dirname(path) if path else None


def resolve_image_path(path: str) -> str | None:
    if not path:
        return None
    expanded = os.path.expanduser(str(path))
    if os.path.isabs(expanded):
        return expanded if os.path.isfile(expanded) else None
    roots = []
    project = _project_dir()
    if project:
        roots.append(project)
    roots.extend(IMAGE_SEARCH_PATHS)
    roots.append(os.getcwd())
    for root in roots:
        candidate = os.path.join(root, expanded)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def load_image(path: str) -> np.ndarray | None:
    path = resolve_image_path(path)
    if not path:
        return None
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    key = os.path.abspath(path)
    hit = _IMAGE_CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    from PySide6.QtGui import QImage
    img = QImage(path)
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    raw = np.frombuffer(img.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)
    arr = raw[:, :w * 4].reshape(h, w, 4).astype(np.float32) / 255.0
    _IMAGE_CACHE[key] = (stamp, arr)
    return arr


def _wrap(i: np.ndarray, n: int, extension: str) -> np.ndarray:
    if extension == "mirror":
        period = 2 * n
        m = np.mod(i, period)
        return np.where(m >= n, period - 1 - m, m)
    if extension in ("extend", "clip"):
        return np.clip(i, 0, n - 1)
    return np.mod(i, n)


def sample_image(img: np.ndarray, u: np.ndarray, v: np.ndarray, interpolation: str = "linear",
                 extension: str = "repeat") -> np.ndarray:
    h, w = img.shape[:2]
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    x = u * w - 0.5
    y = (1.0 - v) * h - 0.5
    if interpolation == "closest":
        xi = _wrap(np.floor(x + 0.5).astype(np.int64), w, extension)
        yi = _wrap(np.floor(y + 0.5).astype(np.int64), h, extension)
        out = img[yi, xi].astype(float)
    else:
        x0 = np.floor(x).astype(np.int64)
        y0 = np.floor(y).astype(np.int64)
        fx = (x - x0)[:, None]
        fy = (y - y0)[:, None]
        xa, xb = _wrap(x0, w, extension), _wrap(x0 + 1, w, extension)
        ya, yb = _wrap(y0, h, extension), _wrap(y0 + 1, h, extension)
        top = img[ya, xa] * (1.0 - fx) + img[ya, xb] * fx
        bottom = img[yb, xa] * (1.0 - fx) + img[yb, xb] * fx
        out = (top * (1.0 - fy) + bottom * fy).astype(float)
    if extension == "clip":
        outside = (u < 0.0) | (u > 1.0) | (v < 0.0) | (v > 1.0)
        out = np.where(outside[:, None], 0.0, out)
    return out


def _mix(c1, c2, t: np.ndarray) -> np.ndarray:
    a = as_rgb(c1)
    b = as_rgb(c2)
    return a[None, :] * (1.0 - t)[:, None] + b[None, :] * t[:, None]


def sample_texture(tex: dict | None, ctx: dict) -> tuple[np.ndarray, np.ndarray]:
    n = len(ctx["u"])
    if not tex:
        return np.zeros((n, 3)), np.zeros(n)
    kind = tex.get("type")
    if kind not in _SPECS:
        return np.broadcast_to(np.array(MISSING_COLOR), (n, 3)).copy(), np.ones(n)
    vals = _values(tex)
    if kind == "checker":
        p, dims = _coords(vals, ctx)
        m = checker_mask(p, vals["scale"], dims)
        col = _mix(vals["color1"], vals["color2"], m)
        return col, luminance(col)
    if kind == "noise":
        p, _ = _coords(vals, ctx)
        t = fractal(p * float(vals["scale"]), vals["noise_type"], vals["detail"], vals["roughness"],
                    vals["lacunarity"], vals["distortion"], int(vals["seed"]))
        c = float(vals.get("contrast", 1.0))
        if c != 1.0:
            t = np.clip((t - 0.5) * c + 0.5, 0.0, 1.0)
        col = _mix(vals["color1"], vals["color2"], t)
        return col, luminance(col)
    if kind == "gradient":
        u, v = _mapped_uv(vals, ctx)
        t = gradient_value(u, v, vals["gradient_type"], bool(vals["repeat"]))
        rgba = evaluate_ramp(vals["ramp"], t, vals["interpolation"])
        col = rgba[:, :3]
        return col, luminance(col)
    if kind == "brick":
        u, v = _mapped_uv(vals, ctx)
        mask, rnd = brick_pattern(u, v, vals["bricks"], vals["rows"], vals["mortar"], vals["smooth"],
                                  vals["row_offset"], int(vals["seed"]))
        pick = np.clip(rnd * float(vals["variation"]) * 2.0, 0.0, 1.0)
        brick = _mix(vals["color1"], vals["color2"], pick)
        mortar = as_rgb(vals["mortar_color"])
        col = brick * (1.0 - mask)[:, None] + mortar[None, :] * mask[:, None]
        return col, luminance(col)
    if kind == "voronoi":
        p, _ = _coords(vals, ctx)
        dims = 2 if bool(np.all(p[:, 2] == 0.0)) else 3
        res = voronoi_pattern(p * float(vals["scale"]), dims, vals["feature"], vals["metric"],
                              vals["randomness"], int(vals["seed"]))
        if vals["coloring"] == "cells":
            col = res["color"]
        else:
            col = _mix(vals["color1"], vals["color2"], np.clip(res["distance"], 0.0, 1.0))
        return col, luminance(col)
    if kind == "image":
        img = load_image(vals["path"])
        if img is None:
            col = np.broadcast_to(np.array(MISSING_COLOR), (n, 3)).copy()
            return col, (np.ones(n) if vals["use_alpha"] else luminance(col))
        u, v = _mapped_uv(vals, ctx)
        rgba = sample_image(img, u, v, vals["interpolation"], vals["extension"])
        col = rgba[:, :3]
        fac = rgba[:, 3] if vals["use_alpha"] else luminance(col)
        return col, fac
    return np.zeros((n, 3)), np.zeros(n)
