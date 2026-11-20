from __future__ import annotations

import math

import numpy as np

__all__ = ["STAMPS", "generate", "sample", "image_to_stamp", "load_stamp"]

STAMPS = ("none", "noise", "rings", "dots", "stripes", "custom")

_CACHE: dict = {}


def _value_noise(size: int, cells: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    grid = rng.random((cells + 1, cells + 1))
    xs = np.linspace(0.0, cells, size, endpoint=False)
    i = np.floor(xs).astype(int)
    f = xs - i
    f = f * f * (3.0 - 2.0 * f)
    a = grid[np.ix_(i, i)]
    b = grid[np.ix_(i, i + 1)]
    c = grid[np.ix_(i + 1, i)]
    d = grid[np.ix_(i + 1, i + 1)]
    fy = f[:, None]
    fx = f[None, :]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def generate(kind: str, size: int = 64) -> np.ndarray | None:
    if kind in ("none", "custom", "", None):
        return None
    key = (kind, size)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    y, x = np.mgrid[0:size, 0:size]
    u = (x + 0.5) / size * 2.0 - 1.0
    v = (y + 0.5) / size * 2.0 - 1.0
    r = np.sqrt(u * u + v * v)
    if kind == "noise":
        img = 0.5 * _value_noise(size, 4, 7) + 0.3 * _value_noise(size, 8, 11) + 0.2 * _value_noise(size, 16, 13)
        img = (img - img.min()) / max(1e-9, img.max() - img.min())
    elif kind == "rings":
        img = 0.5 + 0.5 * np.cos(r * math.pi * 6.0)
    elif kind == "dots":
        g = 4.0
        cu = (u + 1.0) * g / 2.0
        cv = (v + 1.0) * g / 2.0
        du = cu - np.floor(cu) - 0.5
        dv = cv - np.floor(cv) - 0.5
        d = np.sqrt(du * du + dv * dv)
        img = np.clip(1.0 - d / 0.4, 0.0, 1.0)
    elif kind == "stripes":
        img = 0.5 + 0.5 * np.cos(u * math.pi * 5.0)
    else:
        return None
    img = np.clip(img, 0.0, 1.0)
    _CACHE[key] = img
    return img


def sample(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    img = np.asarray(image, float)
    h, w = img.shape[:2]
    inside = (x >= -1.0) & (x <= 1.0) & (y >= -1.0) & (y <= 1.0)
    px = np.clip((x + 1.0) * 0.5 * (w - 1), 0.0, w - 1)
    py = np.clip((y + 1.0) * 0.5 * (h - 1), 0.0, h - 1)
    x0 = np.floor(px).astype(int)
    y0 = np.floor(py).astype(int)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = px - x0
    fy = py - y0
    top = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
    bot = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
    out = top * (1 - fy) + bot * fy
    return np.where(inside, out, 0.0)


def image_to_stamp(image, size: int = 128) -> np.ndarray | None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    if image is None or image.isNull():
        return None
    img = image.convertToFormat(QImage.Format.Format_Grayscale8).scaled(
        size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)[:, :w]
    return buf.astype(float) / 255.0


def load_stamp(path: str, size: int = 128) -> np.ndarray | None:
    from PySide6.QtGui import QImage

    return image_to_stamp(QImage(path), size)
