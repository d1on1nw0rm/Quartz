from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..scene import Mesh
from .meshkit import OpResult, Selection

__all__ = ["Param", "ToolSpec", "TOOLS", "register", "get_tool", "tool_ids", "run_tool"]


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1.0
    unit: str = ""
    choices: tuple[str, ...] = ()
    group: str = "Options"
    modes: tuple[str, ...] = ()

    def clamp(self, value: Any) -> Any:
        if self.kind == "runtime":
            return value
        if self.kind == "vector":
            return tuple(float(x) for x in value)
        if self.kind == "bool":
            return bool(value)
        if self.kind == "choice":
            v = str(value)
            return v if v in self.choices else self.default
        if self.kind == "int":
            v = int(round(float(value)))
        else:
            v = float(value)
        if self.minimum is not None:
            v = max(self.minimum, v)
        if self.maximum is not None:
            v = min(self.maximum, v)
        return int(v) if self.kind == "int" else float(v)


@dataclass
class ToolSpec:
    id: str
    name: str
    apply: Callable[[Mesh, Selection, dict], OpResult]
    modes: tuple[str, ...] = ("polygons",)
    params: tuple[Param, ...] = ()
    interactive: bool = True
    drag_param: str | None = None
    drag_kind: str = "distance"
    menu: str = "Mesh"
    section: str = "CREATION TOOLS"
    shortcut: str | None = None
    icon: str | None = None
    description: str = ""
    extra: dict = field(default_factory=dict)

    def defaults(self) -> dict:
        return {p.key: p.default for p in self.params}

    def param(self, key: str) -> Param | None:
        for p in self.params:
            if p.key == key:
                return p
        return None

    def clamp(self, values: dict) -> dict:
        out = self.defaults()
        for p in self.params:
            if p.key in values:
                out[p.key] = p.clamp(values[p.key])
        return out

    def supports(self, mode: str) -> bool:
        return mode in self.modes


TOOLS: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.id in TOOLS:
        raise ValueError(f"tool {spec.id!r} registered twice")
    TOOLS[spec.id] = spec
    return spec


def get_tool(tool_id: str) -> ToolSpec:
    _load_all()
    return TOOLS[tool_id]


def tool_ids() -> tuple[str, ...]:
    _load_all()
    return tuple(TOOLS)


def run_tool(tool_id: str, mesh: Mesh, sel: Selection, params: dict | None = None) -> OpResult:
    spec = get_tool(tool_id)
    values = spec.clamp(params or {})
    if not spec.supports(sel.mode):
        return OpResult(mesh, sel.copy(), False, f"{spec.name} does not work in {sel.mode} mode")
    return spec.apply(mesh, sel.copy(), values)


_LOADED = False


def _load_all() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    import importlib
    import pkgutil

    from .. import modeling as pkg

    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("ops_"):
            importlib.import_module(f"{pkg.__name__}.{info.name}")
