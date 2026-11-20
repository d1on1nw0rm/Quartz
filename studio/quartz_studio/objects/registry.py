from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..modeling.registry import Param as _ToolParam
from ..scene import Mesh

__all__ = [
    "CATEGORIES",
    "INPUTS",
    "SPECS",
    "Param",
    "ObjectSpec",
    "BuildInput",
    "register",
    "get",
    "all_specs",
    "by_category",
    "defaults",
    "mesh_chains",
    "mesh_is_spline",
    "curve_value",
    "link_keys",
    "CURVE_MAX_POINTS",
]

CATEGORIES = ("null", "spline", "mesh", "generator")
INPUTS = ("none", "children")


CURVE_MAX_POINTS = 32


def _finite(value: Any, key: str) -> float:
    if isinstance(value, (str, bytes)) or value is None:
        raise ValueError(f"{key} needs numbers, got {value!r}")
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{key} needs finite numbers, got {value!r}")
    return v


def _unit(v: float) -> float:
    return min(1.0, max(0.0, v))


def _clamp_curve(value: Any, key: str) -> tuple:
    if value is None or isinstance(value, (str, bytes)):
        raise ValueError(f"{key} needs a list of points")
    pts = []
    for item in value:
        if isinstance(item, (str, bytes)):
            raise ValueError(f"{key} needs pairs of numbers, got {item!r}")
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(f"{key} needs pairs of numbers, got {item!r}")
        pts.append((_unit(_finite(pair[0], key)), _unit(_finite(pair[1], key))))
    pts.sort(key=lambda p: p[0])
    out: list[tuple[float, float]] = []
    for p in pts:
        if out and p[0] == out[-1][0]:
            continue
        out.append(p)
    if len(out) < 2:
        raise ValueError(f"{key} needs at least 2 points")
    if len(out) > CURVE_MAX_POINTS:
        out = out[:CURVE_MAX_POINTS - 1] + [out[-1]]
    out[0] = (0.0, out[0][1])
    out[-1] = (1.0, out[-1][1])
    return tuple(out)


def curve_value(curve: Any, x: float) -> float:
    xs = [float(p[0]) for p in curve]
    ys = [float(p[1]) for p in curve]
    return float(np.interp(float(x), xs, ys))


@dataclass(frozen=True)
class Param(_ToolParam):
    show: tuple = ()
    axes: tuple = ("X", "Y", "Z")
    ref: str = ""

    def visible(self, values: dict) -> bool:
        return all(values.get(k) in allowed for k, allowed in self.show)

    def _bound(self, v: float) -> float:
        if self.minimum is not None:
            v = max(float(self.minimum), v)
        if self.maximum is not None:
            v = min(float(self.maximum), v)
        return float(v)

    def clamp(self, value: Any) -> Any:
        if self.kind == "text":
            return "" if value is None else str(value)
        if self.kind == "font":
            v = "" if value is None else str(value)
            return v if v else self.default
        if self.kind in ("font_style", "link"):
            return "" if value is None else str(value)
        if self.kind == "curve":
            return _clamp_curve(value, self.key)
        if self.kind == "color":
            if value is None or isinstance(value, (str, bytes)):
                raise ValueError(f"{self.key} needs 3 numbers")
            vals = tuple(value)
            if len(vals) != 3:
                raise ValueError(f"{self.key} needs 3 values, got {len(vals)}")
            return tuple(_unit(_finite(v, self.key)) for v in vals)
        if self.kind == "vector":
            vals = tuple(float(x) for x in value)
            if len(vals) != 3:
                raise ValueError(f"{self.key} needs 3 values, got {len(vals)}")
            return tuple(self._bound(v) for v in vals)
        return super().clamp(value)


@dataclass
class ObjectSpec:
    id: str
    label: str
    category: str
    build: Callable[[dict, list], Mesh]
    params: tuple = ()
    inputs: str = "none"
    icon: str = ""
    description: str = ""
    applies: dict = field(default_factory=dict)
    migrate: Callable[[dict], dict] | None = None

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"object {self.id!r}: unknown category {self.category!r}")
        if self.inputs not in INPUTS:
            raise ValueError(f"object {self.id!r}: unknown inputs {self.inputs!r}")
        self.params = tuple(self.params)
        keys = [p.key for p in self.params]
        if len(set(keys)) != len(keys):
            raise ValueError(f"object {self.id!r}: duplicate parameter key")

    def param(self, key: str) -> Param | None:
        for p in self.params:
            if p.key == key:
                return p
        return None

    def defaults(self) -> dict:
        return {p.key: p.default for p in self.params}

    def clamp(self, values: dict) -> dict:
        if self.migrate is not None:
            values = self.migrate(dict(values))
        out = self.defaults()
        for p in self.params:
            if p.key in values:
                out[p.key] = p.clamp(values[p.key])
        return out


def link_keys(spec: ObjectSpec) -> tuple[str, ...]:
    return tuple(p.key for p in spec.params if p.kind == "link")


SPECS: dict[str, ObjectSpec] = {}


def register(spec: ObjectSpec) -> ObjectSpec:
    if spec.id in SPECS:
        raise ValueError(f"object {spec.id!r} registered twice")
    SPECS[spec.id] = spec
    return spec


def get(spec_id: str) -> ObjectSpec:
    return SPECS[spec_id]


def all_specs() -> tuple[ObjectSpec, ...]:
    return tuple(SPECS.values())


def by_category(category: str) -> tuple[ObjectSpec, ...]:
    return tuple(s for s in SPECS.values() if s.category == category)


def defaults(spec: ObjectSpec | str) -> dict:
    if isinstance(spec, str):
        spec = get(spec)
    return spec.defaults()


def mesh_is_spline(mesh: Mesh) -> bool:
    return not mesh.polygons and bool(mesh.loose_edges)


def mesh_chains(mesh: Mesh) -> list[tuple[np.ndarray, bool]]:
    adj: dict[int, list[int]] = {}
    for a, b in mesh.loose_edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    for n in adj.values():
        n.sort()
    used: set[tuple[int, int]] = set()
    out: list[tuple[list[int], bool]] = []

    def key(a: int, b: int) -> tuple[int, int]:
        return (a, b) if a < b else (b, a)

    def walk(start: int, nxt: int) -> tuple[list[int], bool]:
        chain = [start]
        prev, cur = start, nxt
        used.add(key(prev, cur))
        while True:
            if cur == start:
                return chain, True
            chain.append(cur)
            if len(adj[cur]) != 2:
                return chain, False
            step = [n for n in adj[cur] if key(cur, n) not in used]
            if not step:
                return chain, False
            prev, cur = cur, step[0]
            used.add(key(prev, cur))

    for p in sorted(adj):
        if len(adj[p]) == 2:
            continue
        for n in adj[p]:
            if key(p, n) not in used:
                out.append(walk(p, n))
    for p in sorted(adj):
        for n in adj[p]:
            if key(p, n) not in used:
                out.append(walk(p, n))
    pts = mesh.points
    return [(pts[idx].astype(float).copy(), closed) for idx, closed in out]


class BuildInput:

    def __init__(self, mesh: Mesh, name: str, kind: str, obj: Any = None,
                 matrix: np.ndarray | None = None) -> None:
        self.mesh = mesh
        self.name = name
        self.kind = kind
        self.obj = obj
        self.matrix = np.eye(4) if matrix is None else np.asarray(matrix, float)

    @property
    def is_spline(self) -> bool:
        return mesh_is_spline(self.mesh)

    def chains(self) -> list[tuple[np.ndarray, bool]]:
        return mesh_chains(self.mesh)

    def __repr__(self) -> str:
        return f"BuildInput({self.name!r}, {self.kind!r}, points={len(self.mesh.points)})"
