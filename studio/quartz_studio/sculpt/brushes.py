from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Callable

import numpy as np

from . import falloff as _falloff
from . import stamps as _stamps

__all__ = ["BrushDef", "BrushSettings", "BRUSHES", "BRUSH_ORDER", "brush", "brush_ids",
           "DabContext", "DRAW_RATE", "SHARED_KEYS", "default_settings"]

DRAW_RATE = 0.05

SHARED_KEYS = ("radius", "symmetry", "pressure_strength", "pressure_radius", "stabilize")
STABILIZE_MAX = 256.0


@dataclass
class BrushSettings:
    brush: str = "pull"
    radius: float = 48.0
    strength: float = 0.5
    falloff: str = "smooth"
    curve: list = field(default_factory=lambda: [list(p) for p in _falloff.DEFAULT_CURVE])
    invert: bool = False
    spacing: float = 0.1
    pressure_strength: bool = True
    pressure_radius: bool = False
    symmetry: tuple = (False, False, False)
    use_mask: bool = True
    front_only: bool = True
    stamp: str = "none"
    stamp_rotation: float = 0.0
    stamp_scale: float = 1.0
    stamp_tile: bool = False
    stamp_image: Any = None
    smooth_strength: float = 0.5
    stabilize: float = 0.0

    def copy(self) -> "BrushSettings":
        out = BrushSettings(**{f.name: getattr(self, f.name) for f in fields(self)})
        out.curve = [list(p) for p in self.curve]
        out.symmetry = tuple(bool(s) for s in self.symmetry)
        out.stamp_image = None if self.stamp_image is None else np.asarray(self.stamp_image, float).copy()
        return out

    def clamp(self) -> "BrushSettings":
        self.radius = float(min(max(self.radius, 1.0), 4096.0))
        self.strength = float(min(max(self.strength, 0.0), 1.0))
        self.spacing = float(min(max(self.spacing, 0.0), 4.0))
        self.smooth_strength = float(min(max(self.smooth_strength, 0.0), 1.0))
        try:
            self.stabilize = float(min(max(float(self.stabilize), 0.0), STABILIZE_MAX))
        except (TypeError, ValueError):
            self.stabilize = 0.0
        try:
            self.stamp_scale = float(min(max(float(self.stamp_scale), 0.1), 4.0))
        except (TypeError, ValueError):
            self.stamp_scale = 1.0
        self.stamp_tile = bool(self.stamp_tile)
        if self.falloff not in _falloff.FALLOFFS:
            self.falloff = "smooth"
        if self.stamp not in _stamps.STAMPS:
            self.stamp = "none"
        self.curve = [list(p) for p in _falloff.clean_curve(self.curve)]
        sym = tuple(bool(s) for s in tuple(self.symmetry)[:3])
        self.symmetry = sym + (False,) * (3 - len(sym))
        return self

    def to_dict(self) -> dict:
        out = {f.name: getattr(self, f.name) for f in fields(self)}
        out["curve"] = [list(p) for p in self.curve]
        out["symmetry"] = list(self.symmetry)
        out["stamp_image"] = None if self.stamp_image is None else np.asarray(self.stamp_image, float)
        return out

    @classmethod
    def from_dict(cls, data: dict | None) -> "BrushSettings":
        out = cls()
        names = {f.name for f in fields(cls)}
        for k, v in (data or {}).items():
            if k in names:
                setattr(out, k, v)
        if out.stamp_image is not None:
            out.stamp_image = np.asarray(out.stamp_image, float)
        return out.clamp()

    def weight(self, t) -> np.ndarray:
        return _falloff.evaluate(self.falloff, t, self.curve)

    def stamp_array(self) -> np.ndarray | None:
        if self.stamp == "custom":
            return None if self.stamp_image is None else np.asarray(self.stamp_image, float)
        return _stamps.generate(self.stamp)


@dataclass
class DabContext:
    W: np.ndarray
    idx: np.ndarray
    w: np.ndarray
    center: np.ndarray
    normal: np.ndarray
    area_center: np.ndarray
    radius: float
    view_dir: np.ndarray
    sign: float
    topo: Any
    target: np.ndarray | None = None
    mask: np.ndarray | None = None


def _plane_dist(ctx: DabContext, offset: float = 0.0) -> np.ndarray:
    base = ctx.area_center + ctx.normal * offset
    return (ctx.W[ctx.idx] - base) @ ctx.normal


def _pull(ctx: DabContext) -> np.ndarray:
    return ctx.normal[None, :] * (ctx.sign * ctx.w * ctx.radius * DRAW_RATE)[:, None]


def _inflate(ctx: DabContext) -> np.ndarray:
    vn = ctx.topo.vertex_normals(ctx.W, ctx.idx)
    return vn * (ctx.sign * ctx.w * ctx.radius * DRAW_RATE)[:, None]


def _laplace(ctx: DabContext) -> np.ndarray:
    return ctx.topo.neighbor_mean(ctx.W, ctx.idx) - ctx.W[ctx.idx]


def _smooth(ctx: DabContext) -> np.ndarray:
    return _laplace(ctx) * np.clip(ctx.w, 0.0, 1.0)[:, None]


def _flatten(ctx: DabContext) -> np.ndarray:
    d = _plane_dist(ctx)
    return -ctx.normal[None, :] * (d * np.clip(ctx.w, 0.0, 1.0) * ctx.sign)[:, None]


def _fill(ctx: DabContext) -> np.ndarray:
    d = _plane_dist(ctx)
    d = np.minimum(d, 0.0) if ctx.sign > 0 else np.maximum(d, 0.0)
    return -ctx.normal[None, :] * (d * np.clip(ctx.w, 0.0, 1.0))[:, None]


def _scrape(ctx: DabContext) -> np.ndarray:
    d = _plane_dist(ctx)
    d = np.maximum(d, 0.0) if ctx.sign > 0 else np.minimum(d, 0.0)
    return -ctx.normal[None, :] * (d * np.clip(ctx.w, 0.0, 1.0))[:, None]


def _tangent_pull(ctx: DabContext) -> np.ndarray:
    v = ctx.center[None, :] - ctx.W[ctx.idx]
    v = v - np.outer(v @ ctx.normal, ctx.normal)
    return v


def _pinch(ctx: DabContext) -> np.ndarray:
    return _tangent_pull(ctx) * (np.clip(ctx.w, 0.0, 1.0) * 0.25 * ctx.sign)[:, None]


def _crease(ctx: DabContext) -> np.ndarray:
    pinch = _tangent_pull(ctx) * (np.clip(ctx.w, 0.0, 1.0) * 0.2)[:, None]
    cut = -ctx.normal[None, :] * (ctx.sign * ctx.w * ctx.radius * DRAW_RATE * 0.6)[:, None]
    return pinch + cut


def _polish(ctx: DabContext) -> np.ndarray:
    d = _plane_dist(ctx)
    w = np.clip(ctx.w, 0.0, 1.0)
    flat = -ctx.normal[None, :] * (d * w * 0.5)[:, None]
    lap = _laplace(ctx)
    tang = lap - np.outer(lap @ ctx.normal, ctx.normal)
    return flat + tang * (w * 0.5)[:, None]


def _clay(ctx: DabContext) -> np.ndarray:
    offset = ctx.radius * DRAW_RATE * 2.0 * ctx.sign * float(np.max(ctx.w) if len(ctx.w) else 0.0)
    d = _plane_dist(ctx, offset)
    d = np.minimum(d, 0.0) if ctx.sign > 0 else np.maximum(d, 0.0)
    return -ctx.normal[None, :] * (d * np.clip(ctx.w, 0.0, 1.0) * 0.5)[:, None]


def _wax(ctx: DabContext) -> np.ndarray:
    lift = ctx.normal[None, :] * (ctx.sign * ctx.w * ctx.radius * DRAW_RATE * 0.6)[:, None]
    return lift + _laplace(ctx) * (np.clip(ctx.w, 0.0, 1.0) * 0.3)[:, None]


def _amplify(ctx: DabContext) -> np.ndarray:
    return -_laplace(ctx) * (np.clip(ctx.w, 0.0, 1.0) * 0.5 * ctx.sign)[:, None]


def _erase(ctx: DabContext) -> np.ndarray:
    if ctx.target is None:
        return np.zeros((len(ctx.idx), 3))
    return (ctx.target[ctx.idx] - ctx.W[ctx.idx]) * np.clip(ctx.w, 0.0, 1.0)[:, None]


@dataclass(frozen=True)
class BrushDef:
    id: str
    label: str
    apply: Callable[[DabContext], np.ndarray] | None
    kind: str = "displace"
    description: str = ""
    strength: float = 0.5
    falloff: str = "smooth"


BRUSH_ORDER = ("pull", "grab", "smooth", "inflate", "flatten", "fill", "scrape", "pinch",
               "crease", "polish", "clay", "wax", "amplify", "erase", "mask", "stamp")

BRUSHES: dict[str, BrushDef] = {
    "pull": BrushDef("pull", "Pull", _pull, description="Raise the surface along its normal"),
    "grab": BrushDef("grab", "Grab", None, kind="grab", strength=1.0,
                     description="Drag a region of points with the cursor"),
    "smooth": BrushDef("smooth", "Smooth", _smooth, description="Relax points toward their neighbours"),
    "inflate": BrushDef("inflate", "Inflate", _inflate,
                        description="Push points out along their own normals"),
    "flatten": BrushDef("flatten", "Flatten", _flatten,
                        description="Press points onto the brush plane"),
    "fill": BrushDef("fill", "Fill", _fill, description="Raise points below the brush plane"),
    "scrape": BrushDef("scrape", "Scrape", _scrape, description="Lower points above the brush plane"),
    "pinch": BrushDef("pinch", "Pinch", _pinch, description="Pull points toward the brush centre"),
    "crease": BrushDef("crease", "Knife", _crease, strength=0.4, falloff="sharp",
                       description="Cut a sharp crease into the surface"),
    "polish": BrushDef("polish", "Polish", _polish, description="Flatten and relax high spots"),
    "clay": BrushDef("clay", "Clay", _clay, falloff="spherical",
                     description="Build up flat layers of material"),
    "wax": BrushDef("wax", "Wax", _wax, description="Add soft melted material"),
    "amplify": BrushDef("amplify", "Amplify", _amplify, strength=0.3,
                        description="Exaggerate existing detail"),
    "erase": BrushDef("erase", "Erase", _erase,
                      description="Remove sculpting from the active layer or level"),
    "mask": BrushDef("mask", "Mask", None, kind="mask", strength=1.0,
                     description="Paint a mask that protects points from other brushes"),
    "stamp": BrushDef("stamp", "Stamp", _pull, strength=0.6, falloff="constant",
                      description="Pull through a stamp image projected from the view"),
}


def brush(brush_id: str) -> BrushDef:
    return BRUSHES.get(brush_id, BRUSHES["pull"])


def brush_ids() -> tuple[str, ...]:
    return BRUSH_ORDER


def default_settings(brush_id: str) -> BrushSettings:
    b = brush(brush_id)
    s = BrushSettings(brush=b.id, strength=b.strength, falloff=b.falloff)
    if b.id == "stamp":
        s.stamp = "noise"
        s.spacing = 0.5
    if b.id == "grab":
        s.spacing = 0.0
    return s.clamp()

