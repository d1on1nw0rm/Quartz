from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Param", "PARAM_KINDS", "coerce", "defaults_of"]

PARAM_KINDS = ("float", "int", "color", "enum", "bool", "vec2", "vec3", "path", "ramp", "text")


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    kind: str
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    options: tuple = ()
    step: float = 0.01
    soft_max: float | None = None
    option_labels: tuple = field(default=())

    def __post_init__(self) -> None:
        if self.kind not in PARAM_KINDS:
            raise ValueError(f"param {self.key!r}: unknown kind {self.kind!r}")

    def labels(self) -> tuple:
        if self.option_labels and len(self.option_labels) == len(self.options):
            return self.option_labels
        return tuple(str(o).replace("_", " ").title() for o in self.options)


def _bound(p: Param, v: float) -> float:
    if p.minimum is not None:
        v = max(float(p.minimum), v)
    if p.maximum is not None:
        v = min(float(p.maximum), v)
    return v


def coerce(p: Param, value: Any) -> Any:
    if value is None:
        return copy.deepcopy(p.default)
    if p.kind == "float":
        return float(_bound(p, float(value)))
    if p.kind == "int":
        return int(round(_bound(p, float(value))))
    if p.kind == "bool":
        return bool(value)
    if p.kind == "enum":
        v = str(value)
        if p.options and v not in p.options:
            raise ValueError(f"{p.key}: {v!r} is not one of {p.options}")
        return v
    if p.kind == "color":
        vals = [float(x) for x in value][:3]
        if len(vals) != 3:
            raise ValueError(f"{p.key}: colour needs 3 values")
        return [min(max(x, 0.0), 1.0e4) for x in vals]
    if p.kind in ("vec2", "vec3"):
        size = 2 if p.kind == "vec2" else 3
        vals = [float(x) for x in value][:size]
        if len(vals) != size:
            raise ValueError(f"{p.key}: needs {size} values")
        return vals
    if p.kind in ("path", "text"):
        return str(value)
    if p.kind == "ramp":
        stops = []
        for stop in value:
            pos = min(max(float(stop[0]), 0.0), 1.0)
            col = [float(x) for x in stop[1]]
            if len(col) == 3:
                col.append(1.0)
            stops.append([pos, col[:4]])
        if not stops:
            raise ValueError(f"{p.key}: ramp needs at least one stop")
        stops.sort(key=lambda s: s[0])
        return stops
    return value


def defaults_of(params) -> dict:
    return {p.key: copy.deepcopy(p.default) for p in params}
