from __future__ import annotations

import os

import numpy as np

from .colorutil import from_hex, linear_to_srgb, srgb_to_linear
from .evaluate import evaluate_material
from .model import material_signature
from .textures import OBJECT_UNIT, resolve_image_path

__all__ = [
    "SHAPES",
    "LIGHTS",
    "render_preview_array",
    "render_preview",
    "thumbnail",
    "to_qimage",
    "clear_thumbnail_cache",
    "ggx_specular",
    "env_brdf",
    "tonemap",
]

SHAPES = ("sphere", "cube", "plane")

LIGHTS = (
    (np.array([-0.55, 0.65, 0.75]), np.array([3.2, 3.05, 2.85])),
    (np.array([0.8, 0.15, 0.45]), np.array([0.55, 0.65, 0.85])),
    (np.array([0.35, 0.55, -0.75]), np.array([1.6, 1.6, 1.7])),
)

SKY_TOP = np.array([0.42, 0.47, 0.56])
SKY_HORIZON = np.array([0.22, 0.23, 0.26])
SKY_GROUND = np.array([0.05, 0.05, 0.055])
BG_A = "#171a21"
BG_B = "#1f2430"


def _normalize(v: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(length > 1e-12, length, 1.0)


def _rot(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    y, p = np.radians(yaw_deg), np.radians(pitch_deg)
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
    return rx @ ry


def sky(direction: np.ndarray) -> np.ndarray:
    y = direction[..., 1:2]
    up = np.clip(y, 0.0, 1.0)
    down = np.clip(-y, 0.0, 1.0)
    col = SKY_HORIZON + (SKY_TOP - SKY_HORIZON) * np.sqrt(up)
    col = col + (SKY_GROUND - SKY_HORIZON) * np.sqrt(down)
    key = np.clip(np.sum(direction * _normalize(LIGHTS[0][0]), axis=-1, keepdims=True), 0.0, 1.0)
    return col + np.power(key, 48.0) * 6.0


def env_brdf(f0: np.ndarray, rough: np.ndarray, ndv: np.ndarray) -> np.ndarray:
    c0 = np.array([-1.0, -0.0275, -0.572, 0.022])
    c1 = np.array([1.0, 0.0425, 1.04, -0.04])
    r = rough[:, None] * c0 + c1
    a004 = np.minimum(r[:, 0] * r[:, 0], np.exp2(-9.28 * ndv)) * r[:, 0] + r[:, 1]
    a = a004 * -1.04 + r[:, 2]
    b = a004 * 1.04 + r[:, 3]
    return f0 * a[:, None] + b[:, None]


def ggx_specular(n: np.ndarray, v: np.ndarray, l: np.ndarray, rough: np.ndarray,
                 f0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h = _normalize(l + v)
    ndl = np.clip(np.sum(n * l, axis=-1), 0.0, 1.0)
    ndv = np.clip(np.sum(n * v, axis=-1), 1e-4, 1.0)
    ndh = np.clip(np.sum(n * h, axis=-1), 0.0, 1.0)
    vdh = np.clip(np.sum(v * h, axis=-1), 0.0, 1.0)
    a = np.maximum(rough * rough, 2e-3)
    a2 = a * a
    d = a2 / (np.pi * (ndh * ndh * (a2 - 1.0) + 1.0) ** 2)
    k = (rough + 1.0) ** 2 / 8.0
    g = (ndv / (ndv * (1.0 - k) + k)) * (ndl / (ndl * (1.0 - k) + k))
    f = f0 + (1.0 - f0) * ((1.0 - vdh) ** 5)[:, None]
    spec = (d * g / (4.0 * ndv * np.maximum(ndl, 1e-4)))[:, None] * f
    return spec * ndl[:, None], f


def tonemap(x: np.ndarray) -> np.ndarray:
    x = np.maximum(x, 0.0)
    return np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0)


def _background(xs: np.ndarray, ys: np.ndarray, size: int) -> np.ndarray:
    a = np.array(from_hex(BG_A))
    b = np.array(from_hex(BG_B))
    cells = max(4, size // 16)
    cx = np.floor((xs * 0.5 + 0.5) * cells).astype(int)
    cy = np.floor((ys * 0.5 + 0.5) * cells).astype(int)
    m = ((cx + cy) & 1).astype(float)[..., None]
    col = a * (1.0 - m) + b * m
    return srgb_to_linear(col)


def _geometry(shape: str, xs: np.ndarray, ys: np.ndarray):
    if shape == "plane":
        half = 0.8
        mask = (np.abs(xs) <= half) & (np.abs(ys) <= half)
        n = len(xs)
        pos = np.stack([xs, ys, np.zeros(n)], axis=1)
        normal = np.broadcast_to([0.0, 0.0, 1.0], (n, 3)).copy()
        tangent = np.broadcast_to([1.0, 0.0, 0.0], (n, 3)).copy()
        u = (xs + half) / (2 * half)
        v = (ys + half) / (2 * half)
        return mask, u, v, pos, normal, tangent, np.eye(3)
    if shape == "cube":
        rot = _rot(-35.0, 25.0)
        inv = rot.T
        h = 0.5
        origin = np.stack([xs, ys, np.full_like(xs, 3.0)], axis=1) @ inv.T
        d = np.array([0.0, 0.0, -1.0]) @ inv.T
        safe = np.where(np.abs(d) > 1e-9, d, 1e-9)
        t1 = (-h - origin) / safe
        t2 = (h - origin) / safe
        tmin = np.minimum(t1, t2)
        tmax = np.maximum(t1, t2)
        tnear = np.max(tmin, axis=1)
        tfar = np.min(tmax, axis=1)
        mask = (tnear <= tfar) & (tfar > 0)
        axis = np.argmax(tmin, axis=1)
        p = origin + tnear[:, None] * d
        normal = np.zeros_like(p)
        idx = np.arange(len(p))
        normal[idx, axis] = -np.sign(d[axis])
        q = np.clip(p / h, -1.0, 1.0) * 0.5 + 0.5
        sgn = normal[idx, axis]
        u = np.where(axis == 0, np.where(sgn > 0, 1.0 - q[:, 2], q[:, 2]),
                     np.where(axis == 1, q[:, 0], np.where(sgn > 0, q[:, 0], 1.0 - q[:, 0])))
        v = np.where(axis == 1, np.where(sgn > 0, 1.0 - q[:, 2], q[:, 2]), q[:, 1])
        tangent = np.zeros_like(p)
        tangent[:, 0] = np.where(axis == 0, 0.0, np.where(axis == 1, 1.0, sgn))
        tangent[:, 2] = np.where(axis == 0, -sgn, 0.0)
        return mask, u, v, p, normal, tangent, rot
    radius = 0.9
    r2 = (xs * xs + ys * ys) / (radius * radius)
    mask = r2 < 1.0
    nz = np.sqrt(np.clip(1.0 - r2, 0.0, 1.0))
    view_n = np.stack([xs / radius, ys / radius, nz], axis=1)
    rot = _rot(-20.0, 15.0)
    obj_n = view_n @ rot
    u = 0.5 + np.arctan2(obj_n[:, 0], obj_n[:, 2]) / (2.0 * np.pi)
    v = 0.5 + np.arcsin(np.clip(obj_n[:, 1], -1.0, 1.0)) / np.pi
    tangent = np.stack([obj_n[:, 2], np.zeros(len(obj_n)), -obj_n[:, 0]], axis=1)
    return mask, u, v, obj_n.copy(), obj_n, tangent, rot


def _shade(res: dict, n: np.ndarray, xs: np.ndarray, ys: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    count = len(n)
    v = np.broadcast_to([0.0, 0.0, 1.0], (count, 3))
    base = np.asarray(res["base_color"], float)
    metal = np.asarray(res["metallic"], float)
    rough = np.clip(np.asarray(res["roughness"], float), 0.02, 1.0)
    spec_lvl = np.asarray(res["specular"], float)
    ior = np.asarray(res["ior"], float)
    trans = np.asarray(res["transmission"], float)
    f0_d = ((ior - 1.0) / (ior + 1.0)) ** 2 * 2.0 * spec_lvl
    f0 = f0_d[:, None] * (1.0 - metal[:, None]) + base * metal[:, None]
    diffuse_w = ((1.0 - metal) * (1.0 - trans))[:, None]
    ndv = np.clip(np.sum(n * v, axis=1), 1e-4, 1.0)
    color = np.zeros((count, 3))
    cc = np.asarray(res["clearcoat"], float)
    ccr = np.clip(np.asarray(res["clearcoat_roughness"], float), 0.02, 1.0)
    for direction, intensity in LIGHTS:
        l = np.broadcast_to(_normalize(direction), (count, 3))
        spec, f = ggx_specular(n, v, l, rough, f0)
        ndl = np.clip(np.sum(n * l, axis=1), 0.0, 1.0)[:, None]
        diff = (1.0 - f) * diffuse_w * base / np.pi * ndl
        coat, fc = ggx_specular(n, v, l, ccr, np.full((count, 3), 0.04))
        layer = (diff + spec) * (1.0 - fc * cc[:, None]) + coat * cc[:, None]
        color += layer * intensity
    refl = 2.0 * ndv[:, None] * n - v
    env_spec = sky(refl) * (1.0 - rough[:, None]) + sky(n) * rough[:, None]
    spec_amb = env_spec * env_brdf(f0, rough, ndv)
    fr = f0 + (1.0 - f0) * ((1.0 - ndv) ** 5)[:, None]
    diff_amb = sky(n) * 0.8 * base * diffuse_w * (1.0 - fr)
    coat_amb = sky(refl) * env_brdf(np.full((count, 3), 0.04), ccr, ndv) * cc[:, None]
    color += diff_amb + spec_amb + coat_amb
    sheen = np.asarray(res["sheen"], float)
    if np.any(sheen > 0):
        sr = np.asarray(res["sheen_roughness"], float)
        power = 1.0 + 5.0 * (1.0 - sr)
        rim = (1.0 - ndv) ** power
        color += (sheen * rim)[:, None] * np.asarray(res["sheen_tint"], float) * 0.9
    if np.any(trans > 0):
        k = 0.35 * (1.0 - 1.0 / np.maximum(ior, 1.0))
        bx = xs - n[:, 0] * k
        by = ys - n[:, 1] * k
        behind = _background(bx, by, size) * 1.6
        color += behind * base * (1.0 - fr) * trans[:, None]
    color += np.asarray(res["emission"], float)
    return color, np.clip(np.asarray(res["alpha"], float), 0.0, 1.0)


def render_preview_array(material: dict | None, size: int = 64, shape: str = "sphere",
                         background: bool = True, supersample: int | None = None) -> np.ndarray:
    size = max(4, int(size))
    ss = supersample if supersample is not None else (2 if size <= 96 else 1)
    full = size * ss
    coords = (np.arange(full) + 0.5) / full * 2.0 - 1.0
    gx, gy = np.meshgrid(coords, -coords)
    xs, ys = gx.ravel(), gy.ravel()
    bg = _background(xs, ys, full) if background else np.zeros((len(xs), 3))
    mask, u, v, pos, normal, tangent, rot = _geometry(shape if shape in SHAPES else "sphere", xs, ys)
    out = bg.copy()
    coverage = np.zeros(len(xs))
    idx = np.nonzero(mask)[0]
    if len(idx):
        view_obj = np.broadcast_to(np.array([0.0, 0.0, 1.0]) @ rot, (len(idx), 3))
        res = evaluate_material(material, u[idx], v[idx], pos[idx] * OBJECT_UNIT, normal[idx], tangent[idx],
                                view_obj)
        n_view = _normalize(np.asarray(res["normal"], float) @ rot.T)
        geo_view = _normalize(normal[idx] @ rot.T)
        facing = np.sum(n_view * geo_view, axis=1) < 0.0
        n_view = np.where(facing[:, None], geo_view, n_view)
        color, alpha = _shade(res, n_view, xs[idx], ys[idx], full)
        out[idx] = color * alpha[:, None] + bg[idx] * (1.0 - alpha[:, None])
        coverage[idx] = alpha if not background else 1.0
    rgb = linear_to_srgb(tonemap(out))
    if background:
        coverage[:] = 1.0
    img = np.concatenate([rgb, coverage[:, None]], axis=1).reshape(full, full, 4)
    if ss > 1:
        img = img.reshape(size, ss, size, ss, 4).mean(axis=(1, 3))
    return np.clip(np.round(img * 255.0), 0, 255).astype(np.uint8)


def to_qimage(arr: np.ndarray):
    from PySide6.QtGui import QImage
    arr = np.ascontiguousarray(arr, np.uint8)
    h, w = arr.shape[:2]
    img = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return img.copy()


def render_preview(material: dict | None, size: int = 64, shape: str = "sphere", background: bool = True):
    return to_qimage(render_preview_array(material, size, shape, background))


def _image_stamps(value, out: list) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "path" and isinstance(v, str) and v:
                resolved = resolve_image_path(v)
                try:
                    out.append((v, resolved, os.path.getmtime(resolved) if resolved else None))
                except OSError:
                    out.append((v, resolved, None))
            else:
                _image_stamps(v, out)
    elif isinstance(value, list):
        for v in value:
            _image_stamps(v, out)


_CACHE: dict = {}
_CACHE_LIMIT = 256


def clear_thumbnail_cache() -> None:
    _CACHE.clear()


def thumbnail(material: dict | None, size: int = 64, shape: str | None = None):
    shape = shape or (material or {}).get("preview", "sphere")
    stamps: list = []
    _image_stamps(material, stamps)
    key = (material_signature(material) if material else "", int(size), shape, tuple(stamps))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    img = render_preview(material, size, shape)
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = img
    return img
