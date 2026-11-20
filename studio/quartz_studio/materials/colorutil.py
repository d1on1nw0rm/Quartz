from __future__ import annotations

import numpy as np

__all__ = [
    "LUMA",
    "as_rgb",
    "srgb_to_linear",
    "linear_to_srgb",
    "luminance",
    "rgb_to_hsv",
    "hsv_to_rgb",
    "to_hex",
    "from_hex",
    "clamp01",
    "smoothstep",
]

LUMA = np.array([0.2126, 0.7152, 0.0722])


def as_rgb(value, n: int | None = None) -> np.ndarray:
    arr = np.asarray(value, float)
    if arr.ndim == 0:
        arr = np.full(3, float(arr))
    if arr.shape[-1] == 4:
        arr = arr[..., :3]
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)
    if n is not None and arr.ndim == 1:
        arr = np.broadcast_to(arr, (n, 3)).copy()
    return arr


def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def smoothstep(e0, e1, x):
    e0 = np.asarray(e0, float)
    e1 = np.asarray(e1, float)
    span = np.where(np.abs(e1 - e0) < 1e-12, 1e-12, e1 - e0)
    t = np.clip((np.asarray(x, float) - e0) / span, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def srgb_to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((np.maximum(c, 0.0) + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.maximum(np.asarray(c, float), 0.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)


def luminance(c) -> np.ndarray:
    c = np.asarray(c, float)
    return c[..., :3] @ LUMA


def rgb_to_hsv(c) -> np.ndarray:
    c = np.asarray(c, float)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    mx = np.max(c[..., :3], axis=-1)
    mn = np.min(c[..., :3], axis=-1)
    d = mx - mn
    safe = np.where(d > 1e-12, d, 1.0)
    h = np.where(mx == r, ((g - b) / safe) % 6.0,
                 np.where(mx == g, (b - r) / safe + 2.0, (r - g) / safe + 4.0))
    h = np.where(d > 1e-12, h / 6.0, 0.0) % 1.0
    s = np.where(mx > 1e-12, d / np.where(mx > 1e-12, mx, 1.0), 0.0)
    return np.stack([h, s, mx], axis=-1)


def hsv_to_rgb(c) -> np.ndarray:
    c = np.asarray(c, float)
    h, s, v = c[..., 0] % 1.0, c[..., 1], c[..., 2]
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i.astype(int) % 6
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def to_hex(rgb) -> str:
    vals = np.clip(np.asarray(rgb, float)[:3], 0.0, 1.0)
    return "#" + "".join(f"{int(round(v * 255)):02x}" for v in vals)


def from_hex(text: str) -> list[float]:
    t = text.strip().lstrip("#")
    if len(t) == 3:
        t = "".join(ch * 2 for ch in t)
    if len(t) < 6:
        raise ValueError(f"bad colour {text!r}")
    return [int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
