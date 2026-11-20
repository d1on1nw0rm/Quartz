from __future__ import annotations

import base64
import itertools
import math
from dataclasses import dataclass, replace
from typing import Iterable

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from ..ext import store
from .data import Corners, get_uv_array, triangulate_polygon, write_object

__all__ = [
    "CHANNELS",
    "TEXTURES_KEY",
    "TEXTURE_SIZES",
    "Brush",
    "TextureCanvas",
    "checker_pixels",
    "checker_image",
    "color_tuple",
    "uv_at_hit",
    "paint_hit",
    "paint_ray",
    "save_canvas",
    "load_canvas",
    "texture_channels",
    "remove_canvas",
]

CHANNELS = ("Color", "Roughness", "Metal", "Bump", "Normal", "Alpha", "Emission")
TEXTURES_KEY = "uv_textures"
TEXTURE_SIZES = (256, 512, 1024, 2048, 4096)
TILE = 64
CHUNK_PIXELS = 1 << 18
_REV = itertools.count(1)


def color_tuple(color) -> tuple[float, float, float, float]:
    if isinstance(color, QColor):
        return (color.redF(), color.greenF(), color.blueF(), color.alphaF())
    if isinstance(color, str):
        return color_tuple(QColor(color))
    raw = list(color)
    integral = bool(raw) and all(isinstance(c, (int, np.integer)) and not isinstance(c, (bool, np.bool_))
                                 for c in raw)
    vals = [float(c) for c in raw]
    vals = [v if math.isfinite(v) else 0.0 for v in vals]
    if integral and any(v > 1.0 for v in vals):
        vals = [v / 255.0 for v in vals]
    if len(vals) == 3:
        vals.append(1.0)
    return tuple(min(1.0, max(0.0, v)) for v in vals[:4])


@dataclass
class Brush:
    radius: float = 16.0
    hardness: float = 0.5
    opacity: float = 1.0
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    mode: str = "paint"
    spacing: float = 0.25
    tolerance: float = 0.1
    wrap: bool = False

    def copy(self) -> "Brush":
        return replace(self, color=tuple(self.color))

    def falloff(self, d: np.ndarray) -> np.ndarray:
        h = min(max(float(self.hardness), 0.0), 1.0)
        r = max(float(self.radius), 0.5)
        x = d / r
        if h >= 0.999:
            edge = 1.0 / r
            return np.clip((1.0 - x) / max(edge, 1e-9) + 0.5, 0.0, 1.0)
        t = np.clip((x - h) / max(1.0 - h, 1e-9), 0.0, 1.0)
        return 1.0 - t * t * (3.0 - 2.0 * t)


def checker_pixels(size: int = 512, cells: int = 8, color_a=(0.86, 0.88, 0.92, 1.0),
                   color_b=(0.16, 0.18, 0.23, 1.0), height: int | None = None) -> np.ndarray:
    w = int(size)
    h = int(height or size)
    cells = max(1, int(cells))
    ys = (np.arange(h) * cells) // h
    xs = (np.arange(w) * cells) // w
    mask = ((ys[:, None] + xs[None, :]) % 2 == 0)
    a = np.asarray(color_tuple(color_a), np.float32)
    b = np.asarray(color_tuple(color_b), np.float32)
    return np.where(mask[:, :, None], a, b).astype(np.float32)


def checker_image(size: int = 512, cells: int = 8, color_a=(0.86, 0.88, 0.92, 1.0),
                  color_b=(0.16, 0.18, 0.23, 1.0)) -> QImage:
    return TextureCanvas.from_pixels(checker_pixels(size, cells, color_a, color_b)).to_qimage()


class TextureCanvas:

    def __init__(self, width: int = 1024, height: int | None = None, fill=(0.5, 0.5, 0.5, 1.0)) -> None:
        w = max(1, int(width))
        h = max(1, int(height or width))
        self.pixels = np.empty((h, w, 4), dtype=np.float32)
        self.pixels[:] = np.asarray(color_tuple(fill), np.float32)
        self.revision = next(_REV)
        self.path = ""
        self._stroke_base: dict | None = None
        self._stroke_mask: dict | None = None
        self._stroke_brush: Brush | None = None
        self._last: tuple[float, float] | None = None
        self._carry = 0.0
        self.dirty = False

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])

    @classmethod
    def from_pixels(cls, pixels: np.ndarray) -> "TextureCanvas":
        arr = np.asarray(pixels, np.float32)
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr, np.ones_like(arr)], axis=2)
        if arr.shape[2] == 3:
            arr = np.concatenate([arr, np.ones(arr.shape[:2] + (1,), np.float32)], axis=2)
        canvas = cls(arr.shape[1], arr.shape[0])
        canvas.pixels[:] = np.clip(arr, 0.0, 1.0)
        return canvas

    @classmethod
    def from_qimage(cls, image: QImage) -> "TextureCanvas":
        img = image.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        bpl = img.bytesPerLine()
        buf = np.frombuffer(bytes(img.constBits()), dtype=np.uint8, count=bpl * h).reshape(h, bpl)
        arr = buf[:, :w * 4].reshape(h, w, 4).astype(np.float32) / 255.0
        return cls.from_pixels(arr)

    @classmethod
    def from_png(cls, path: str) -> "TextureCanvas":
        img = QImage(str(path))
        if img.isNull():
            raise OSError(f"cannot read image {path!r}")
        canvas = cls.from_qimage(img)
        canvas.path = str(path)
        return canvas

    @classmethod
    def from_bytes(cls, data: bytes) -> "TextureCanvas":
        img = QImage()
        if not img.loadFromData(QByteArray(data), "PNG"):
            raise ValueError("invalid PNG data")
        return cls.from_qimage(img)

    def copy(self) -> "TextureCanvas":
        out = TextureCanvas.from_pixels(self.pixels.copy())
        out.path = self.path
        return out

    def bytes8(self) -> np.ndarray:
        return np.ascontiguousarray(np.clip(np.rint(self.pixels * 255.0), 0, 255).astype(np.uint8))

    def to_qimage(self) -> QImage:
        data = self.bytes8()
        h, w = data.shape[:2]
        img = QImage(data.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        return img.copy()

    def to_png_bytes(self) -> bytes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        self.to_qimage().save(buf, "PNG")
        buf.close()
        return bytes(ba.data())

    def save_png(self, path: str) -> bool:
        ok = bool(self.to_qimage().save(str(path), "PNG"))
        if ok:
            self.path = str(path)
        return ok

    def load_png(self, path: str) -> None:
        other = TextureCanvas.from_png(path)
        self.pixels = other.pixels
        self.path = str(path)
        self.touch()

    def resize(self, width: int, height: int | None = None) -> None:
        w, h = max(1, int(width)), max(1, int(height or width))
        if (w, h) == (self.width, self.height):
            return
        ys = np.clip(((np.arange(h) + 0.5) * self.height / h).astype(int), 0, self.height - 1)
        xs = np.clip(((np.arange(w) + 0.5) * self.width / w).astype(int), 0, self.width - 1)
        self.pixels = self.pixels[ys][:, xs].copy()
        self.touch()

    def touch(self) -> None:
        self.revision = next(_REV)
        self.dirty = True

    def uv_to_px(self, u: float, v: float) -> tuple[float, float]:
        return float(u) * self.width - 0.5, (1.0 - float(v)) * self.height - 0.5

    def px_to_uv(self, x: float, y: float) -> tuple[float, float]:
        return (float(x) + 0.5) / self.width, 1.0 - (float(y) + 0.5) / self.height

    def sample(self, u: float, v: float) -> tuple[float, float, float, float]:
        x, y = self.uv_to_px(u % 1.0 if u != 1.0 else u, v % 1.0 if v != 1.0 else v)
        xi = int(min(max(round(x), 0), self.width - 1))
        yi = int(min(max(round(y), 0), self.height - 1))
        return tuple(float(c) for c in self.pixels[yi, xi])

    def _row_chunks(self):
        step = max(1, CHUNK_PIXELS // max(self.width, 1))
        for y0 in range(0, self.height, step):
            yield slice(y0, min(self.height, y0 + step))

    def fill(self, color, opacity: float = 1.0) -> None:
        c = np.asarray(color_tuple(color), np.float32)
        a = float(opacity) * float(c[3])
        xs = slice(0, self.width)
        for ys in self._row_chunks():
            alpha = np.full((ys.stop - ys.start, self.width), a, np.float32)
            self._blend_region(ys, xs, alpha, c, "paint", self.pixels[ys, xs])
        self.touch()

    def clear(self, color=(0.0, 0.0, 0.0, 0.0)) -> None:
        self.pixels[:] = np.asarray(color_tuple(color), np.float32)
        self.touch()

    def flood_fill(self, u: float, v: float, color, tolerance: float = 0.1,
                   opacity: float = 1.0) -> int:
        x, y = self.uv_to_px(u, v)
        xi, yi = int(round(x)), int(round(y))
        if not (0 <= xi < self.width and 0 <= yi < self.height):
            return 0
        seed = self.pixels[yi, xi].copy()
        similar = np.zeros((self.height, self.width), dtype=bool)
        for ys in self._row_chunks():
            diff = np.abs(self.pixels[ys] - seed[None, None, :]).max(axis=2)
            similar[ys] = diff <= float(tolerance) + 1e-6
        region = np.zeros_like(similar)
        stack = [(xi, yi)]
        w = self.width
        while stack:
            sx, sy = stack.pop()
            if region[sy, sx] or not similar[sy, sx]:
                continue
            row_ok = similar[sy] & ~region[sy]
            left = sx
            while left > 0 and row_ok[left - 1]:
                left -= 1
            right = sx
            while right < w - 1 and row_ok[right + 1]:
                right += 1
            region[sy, left:right + 1] = True
            for ny in (sy - 1, sy + 1):
                if 0 <= ny < self.height:
                    cand = similar[ny, left:right + 1] & ~region[ny, left:right + 1]
                    if cand.any():
                        xs = np.nonzero(cand)[0] + left
                        starts = xs[np.concatenate([[True], np.diff(xs) > 1])]
                        stack.extend((int(s), ny) for s in starts)
        c = np.asarray(color_tuple(color), np.float32)
        strength = float(opacity) * float(c[3])
        rows = np.nonzero(region.any(axis=1))[0]
        if len(rows):
            y0, y1 = int(rows[0]), int(rows[-1]) + 1
            step = max(1, CHUNK_PIXELS // max(w, 1))
            for s in range(y0, y1, step):
                ys = slice(s, min(y1, s + step))
                alpha = region[ys].astype(np.float32) * strength
                self._blend_region(ys, slice(0, w), alpha, c, "paint", self.pixels[ys, 0:w])
        self.touch()
        return int(region.sum())

    def _blend_region(self, ys: slice, xs: slice, alpha: np.ndarray, color: np.ndarray, mode: str,
                      base: np.ndarray) -> None:
        a = np.clip(alpha, 0.0, 1.0)[:, :, None]
        if mode == "erase":
            out = base.copy()
            out[:, :, 3:4] = base[:, :, 3:4] * (1.0 - a)
        else:
            ba = base[:, :, 3:4]
            out_a = a + ba * (1.0 - a)
            safe = np.where(out_a > 1e-8, out_a, 1.0)
            rgb = (color[None, None, :3] * a + base[:, :, :3] * ba * (1.0 - a)) / safe
            rgb = np.where(out_a > 1e-8, rgb, base[:, :, :3])
            out = np.concatenate([rgb, out_a], axis=2)
        self.pixels[ys, xs] = out.astype(np.float32)

    def _dab_mask(self, x: float, y: float, brush: Brush) -> tuple[slice, slice, np.ndarray] | None:
        r = max(float(brush.radius), 0.5)
        x0 = max(int(math.floor(x - r - 1)), 0)
        x1 = min(int(math.ceil(x + r + 1)), self.width - 1)
        y0 = max(int(math.floor(y - r - 1)), 0)
        y1 = min(int(math.ceil(y + r + 1)), self.height - 1)
        if x0 > x1 or y0 > y1:
            return None
        gx = np.arange(x0, x1 + 1, dtype=np.float32)
        gy = np.arange(y0, y1 + 1, dtype=np.float32)
        d = np.hypot(gx[None, :] - x, gy[:, None] - y)
        return slice(y0, y1 + 1), slice(x0, x1 + 1), brush.falloff(d).astype(np.float32)

    def begin_stroke(self, brush: Brush) -> None:
        self._stroke_base = {}
        self._stroke_mask = {}
        self._stroke_brush = brush.copy()
        self._last = None
        self._carry = 0.0

    def in_stroke(self) -> bool:
        return self._stroke_base is not None

    def stroke_memory(self) -> int:
        if self._stroke_base is None:
            return 0
        return sum(t.nbytes for t in self._stroke_base.values()) + sum(t.nbytes for t in self._stroke_mask.values())

    def _tile_keys(self, ys: slice, xs: slice):
        for ty in range(ys.start // TILE, (ys.stop - 1) // TILE + 1):
            for tx in range(xs.start // TILE, (xs.stop - 1) // TILE + 1):
                yield ty, tx

    def _gather(self, tiles: dict, ys: slice, xs: slice, mask: bool) -> np.ndarray:
        h, w = ys.stop - ys.start, xs.stop - xs.start
        out = np.zeros((h, w), np.float32) if mask else np.empty((h, w, 4), np.float32)
        for ty, tx in self._tile_keys(ys, xs):
            key = (ty, tx)
            ty0, tx0 = ty * TILE, tx * TILE
            tile = tiles.get(key)
            if tile is None:
                if mask:
                    tile = np.zeros((min(TILE, self.height - ty0), min(TILE, self.width - tx0)), np.float32)
                else:
                    tile = self.pixels[ty0:ty0 + TILE, tx0:tx0 + TILE].copy()
                tiles[key] = tile
            y0, y1 = max(ys.start, ty0), min(ys.stop, ty0 + tile.shape[0])
            x0, x1 = max(xs.start, tx0), min(xs.stop, tx0 + tile.shape[1])
            out[y0 - ys.start:y1 - ys.start, x0 - xs.start:x1 - xs.start] = tile[y0 - ty0:y1 - ty0, x0 - tx0:x1 - tx0]
        return out

    def _scatter(self, tiles: dict, ys: slice, xs: slice, values: np.ndarray) -> None:
        for ty, tx in self._tile_keys(ys, xs):
            tile = tiles[(ty, tx)]
            ty0, tx0 = ty * TILE, tx * TILE
            y0, y1 = max(ys.start, ty0), min(ys.stop, ty0 + tile.shape[0])
            x0, x1 = max(xs.start, tx0), min(xs.stop, tx0 + tile.shape[1])
            tile[y0 - ty0:y1 - ty0, x0 - tx0:x1 - tx0] = values[y0 - ys.start:y1 - ys.start, x0 - xs.start:x1 - xs.start]

    def _stamp(self, x: float, y: float) -> None:
        brush = self._stroke_brush
        if not getattr(brush, "wrap", False):
            self._stamp_at(x, y)
            return
        r = max(float(brush.radius), 0.5) + 1.0
        x = x % self.width
        y = y % self.height
        for dx in (-self.width, 0, self.width):
            for dy in (-self.height, 0, self.height):
                cx, cy = x + dx, y + dy
                if cx + r < 0 or cy + r < 0 or cx - r > self.width - 1 or cy - r > self.height - 1:
                    continue
                self._stamp_at(cx, cy)

    def _stamp_at(self, x: float, y: float) -> None:
        brush = self._stroke_brush
        hit = self._dab_mask(x, y, brush)
        if hit is None:
            return
        ys, xs, m = hit
        base = self._gather(self._stroke_base, ys, xs, mask=False)
        region = self._gather(self._stroke_mask, ys, xs, mask=True)
        np.maximum(region, m, out=region)
        self._scatter(self._stroke_mask, ys, xs, region)
        color = np.asarray(color_tuple(brush.color), np.float32)
        alpha = region * float(brush.opacity) * (1.0 if brush.mode == "erase" else float(color[3]))
        self._blend_region(ys, xs, alpha, color, brush.mode, base)

    def stroke_to(self, u: float, v: float) -> None:
        if self._stroke_base is None:
            return
        x, y = self.uv_to_px(u, v)
        if self._last is None:
            self._stamp(x, y)
            self._last = (x, y)
            self.touch()
            return
        lx, ly = self._last
        dist = math.hypot(x - lx, y - ly)
        step = max(1.0, float(self._stroke_brush.radius) * max(float(self._stroke_brush.spacing), 0.01))
        travelled = step - self._carry
        while travelled <= dist + 1e-9:
            t = travelled / dist if dist > 0 else 1.0
            self._stamp(lx + (x - lx) * t, ly + (y - ly) * t)
            travelled += step
        self._carry = dist - (travelled - step)
        self._last = (x, y)
        self.touch()

    def end_stroke(self) -> None:
        self._stroke_base = None
        self._stroke_mask = None
        self._stroke_brush = None
        self._last = None
        self._carry = 0.0

    def dab(self, u: float, v: float, brush: Brush) -> None:
        self.begin_stroke(brush)
        self.stroke_to(u, v)
        self.end_stroke()

    def stroke(self, points: Iterable[tuple[float, float]], brush: Brush) -> None:
        self.begin_stroke(brush)
        for u, v in points:
            self.stroke_to(u, v)
        self.end_stroke()

    def to_record(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "png": base64.b64encode(self.to_png_bytes()).decode("ascii"),
            "path": self.path,
            "rev": int(self.revision),
        }

    @classmethod
    def from_record(cls, rec: dict) -> "TextureCanvas":
        canvas = cls.from_bytes(base64.b64decode(rec["png"]))
        canvas.path = str(rec.get("path", ""))
        return canvas


def texture_channels(obj) -> list[str]:
    rec = store.get_object(obj, TEXTURES_KEY)
    return sorted(rec) if isinstance(rec, dict) else []


def save_canvas(obj, channel: str, canvas: TextureCanvas) -> dict:
    rec = dict(store.get_object(obj, TEXTURES_KEY) or {})
    entry = canvas.to_record()
    rec[str(channel)] = entry
    write_object(obj, TEXTURES_KEY, rec)
    canvas.dirty = False
    return entry


def load_canvas(obj, channel: str) -> TextureCanvas | None:
    rec = store.get_object(obj, TEXTURES_KEY)
    if not isinstance(rec, dict) or channel not in rec:
        return None
    try:
        canvas = TextureCanvas.from_record(rec[channel])
    except (KeyError, ValueError, TypeError):
        return None
    canvas.revision = int(rec[channel].get("rev", canvas.revision))
    canvas.dirty = False
    return canvas


def remove_canvas(obj, channel: str) -> bool:
    rec = dict(store.get_object(obj, TEXTURES_KEY) or {})
    if channel not in rec:
        return False
    del rec[channel]
    write_object(obj, TEXTURES_KEY, rec or None)
    return True


def _barycentric(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-300:
        return np.array([1.0, 0.0, 0.0])
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return np.array([1.0 - v - w, v, w])


def uv_at_hit(obj, poly: int, point, world: bool = True, uv: np.ndarray | None = None) -> tuple[float, float] | None:
    mesh = obj.mesh
    if not (0 <= int(poly) < len(mesh.polygons)):
        return None
    corners = Corners(mesh)
    uv = get_uv_array(obj, corners) if uv is None else uv
    ids = list(corners.of(int(poly)))
    ring = mesh.points[corners.vertex[ids]]
    if world:
        ring = obj.to_world(ring)
    p = np.asarray(point, float)
    best = None
    for a, b, c in triangulate_polygon(ring):
        bc = _barycentric(p, ring[a], ring[b], ring[c])
        err = -min(bc.min(), 0.0)
        if best is None or err < best[0]:
            best = (err, bc, (a, b, c))
    if best is None:
        return None
    _, bc, (a, b, c) = best
    bc = np.clip(bc, 0.0, None)
    bc = bc / max(bc.sum(), 1e-300)
    val = bc[0] * uv[ids[a]] + bc[1] * uv[ids[b]] + bc[2] * uv[ids[c]]
    return float(val[0]), float(val[1])


def paint_hit(canvas: TextureCanvas, obj, poly: int, point, brush: Brush, *, continue_stroke: bool = False,
              uv: np.ndarray | None = None) -> tuple[float, float] | None:
    hit = uv_at_hit(obj, poly, point, uv=uv)
    if hit is None:
        return None
    if continue_stroke and canvas.in_stroke():
        canvas.stroke_to(*hit)
    else:
        canvas.dab(hit[0], hit[1], brush)
    return hit


def paint_ray(scene, origin, direction, canvas: TextureCanvas, brush: Brush, obj=None,
              continue_stroke: bool = False) -> tuple[float, float] | None:
    objects = None if obj is None else [obj]
    hit = scene.raycast(origin, direction, objects)
    if hit is None:
        return None
    target, poly, point, _t = hit
    if obj is not None and target is not obj:
        return None
    return paint_hit(canvas, target, poly, point, brush, continue_stroke=continue_stroke)
