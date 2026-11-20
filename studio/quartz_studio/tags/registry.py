from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "CATEGORIES",
    "PARAM_KINDS",
    "TagParam",
    "TagAction",
    "TagSpec",
    "TAG_SPECS",
    "register_tag",
    "get_tag_spec",
    "has_tag_spec",
    "tag_specs",
    "tag_ids",
    "specs_by_category",
    "make_tag",
    "clamp_tag",
]

CATEGORIES = (
    "Rendering Tags",
    "Modeling Tags",
    "Animation Tags",
    "Programming Tags",
    "Simulation Tags",
    "Character Tags",
)

PARAM_KINDS = ("bool", "int", "float", "percent", "angle", "distance", "choice", "vector",
               "text", "code", "object", "tag_ref", "data")


def _bound(v: float, lo: float | None, hi: float | None) -> float:
    if lo is not None:
        v = max(float(lo), v)
    if hi is not None:
        v = min(float(hi), v)
    return v


@dataclass(frozen=True)
class TagParam:
    key: str
    label: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1.0
    choices: tuple = ()
    group: str = "Tag"
    unit: str = ""
    ref_type: str = ""
    tooltip: str = ""
    labels: tuple = ()

    def __post_init__(self) -> None:
        if self.kind not in PARAM_KINDS:
            raise ValueError(f"param {self.key!r}: unknown kind {self.kind!r}")
        if self.kind == "choice" and self.default not in self.choices:
            raise ValueError(f"param {self.key!r}: default not in choices")
        if self.labels and len(self.labels) != len(self.choices):
            raise ValueError(f"param {self.key!r}: labels and choices differ in length")
        if self.kind == "vector" and len(tuple(self.default)) not in (2, 3, 4):
            raise ValueError(f"param {self.key!r}: vectors need 2 to 4 values")

    @property
    def size(self) -> int:
        return len(tuple(self.default)) if self.kind == "vector" else 1

    def choice_label(self, value: Any) -> str:
        if self.labels and value in self.choices:
            return str(self.labels[self.choices.index(value)])
        return str(value)

    def choice_items(self) -> list[tuple[str, Any]]:
        return [(self.choice_label(c), c) for c in self.choices]

    @property
    def visible(self) -> bool:
        return self.kind != "data"

    def initial(self) -> Any:
        if self.kind == "vector":
            return [float(x) for x in self.default]
        return copy.deepcopy(self.default)

    def clamp(self, value: Any) -> Any:
        kind = self.kind
        if kind == "data":
            return value
        if kind == "bool":
            return bool(value)
        if kind == "choice":
            v = str(value)
            if v in self.choices:
                return v
            low = v.strip().lower()
            for c, label in zip(self.choices, self.labels or self.choices):
                if low in (str(c).lower(), str(label).lower()):
                    return c
            return self.default
        if kind in ("text", "code", "object", "tag_ref"):
            return "" if value is None else str(value)
        if kind == "vector":
            vals = [float(x) for x in value]
            if len(vals) != self.size:
                raise ValueError(f"{self.key} needs {self.size} values, got {len(vals)}")
            return [_bound(v, self.minimum, self.maximum) for v in vals]
        if kind == "int":
            return int(_bound(int(round(float(value))), self.minimum, self.maximum))
        return float(_bound(float(value), self.minimum, self.maximum))


@dataclass(frozen=True)
class TagAction:
    key: str
    label: str
    run: Callable


@dataclass
class TagSpec:
    id: str
    label: str
    category: str
    params: tuple = ()
    icon: str = "tag"
    runtime: bool = False
    unique: bool = False
    actions: tuple = ()
    evaluate: Callable | None = None
    summary: Callable | None = None
    on_create: Callable | None = None
    description: str = ""
    menu_order: int = 0
    extra: dict = field(default_factory=dict)
    migrate: Callable | None = None
    captured: tuple = ()
    recapture: bool = False

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"tag {self.id!r}: unknown category {self.category!r}")
        self.params = tuple(self.params)
        self.actions = tuple(self.actions)
        self.captured = tuple(self.captured)
        keys = [p.key for p in self.params]
        reserved = {"type", "name", "enabled"}
        if len(set(keys)) != len(keys) or reserved & set(keys):
            raise ValueError(f"tag {self.id!r}: duplicate or reserved parameter key")
        if self.runtime and self.evaluate is None:
            raise ValueError(f"tag {self.id!r}: runtime tags need an evaluate hook")
        if set(self.captured) - set(keys):
            raise ValueError(f"tag {self.id!r}: captured keys must be parameters")

    def param(self, key: str) -> TagParam | None:
        for p in self.params:
            if p.key == key:
                return p
        return None

    def action(self, key: str) -> TagAction | None:
        for a in self.actions:
            if a.key == key:
                return a
        return None

    def defaults(self) -> dict:
        return {p.key: p.initial() for p in self.params}

    def groups(self) -> list[str]:
        out: list[str] = []
        for p in self.params:
            if p.visible and p.group not in out:
                out.append(p.group)
        return out


TAG_SPECS: dict[str, TagSpec] = {}


def register_tag(spec: TagSpec) -> TagSpec:
    if spec.id in TAG_SPECS:
        raise ValueError(f"tag {spec.id!r} registered twice")
    TAG_SPECS[spec.id] = spec
    return spec


def get_tag_spec(tag_id: str) -> TagSpec:
    return TAG_SPECS[tag_id]


def has_tag_spec(tag_id: str) -> bool:
    return tag_id in TAG_SPECS


def tag_specs() -> tuple[TagSpec, ...]:
    return tuple(TAG_SPECS.values())


def tag_ids() -> tuple[str, ...]:
    return tuple(TAG_SPECS)


def specs_by_category() -> list[tuple[str, list[TagSpec]]]:
    out = []
    for cat in CATEGORIES:
        items = sorted((s for s in TAG_SPECS.values() if s.category == cat),
                       key=lambda s: (s.menu_order, s.label))
        if items:
            out.append((cat, items))
    return out


def make_tag(tag_id: str, name: str | None = None, **values) -> dict:
    spec = get_tag_spec(tag_id)
    tag = {"type": spec.id, "name": name or spec.label, "enabled": True}
    tag.update(spec.defaults())
    for key, value in values.items():
        p = spec.param(key)
        if p is None:
            if key in ("name", "enabled"):
                tag[key] = str(value) if key == "name" else bool(value)
                continue
            raise KeyError(f"tag {tag_id!r} has no parameter {key!r}")
        tag[key] = p.clamp(value)
    return tag


def clamp_tag(tag: dict) -> dict:
    spec = TAG_SPECS.get(tag.get("type", "")) if isinstance(tag, dict) else None
    out = copy.deepcopy(tag)
    if spec is None:
        return out
    if spec.migrate is not None:
        spec.migrate(out)
    out["name"] = str(out.get("name") or spec.label)
    out["enabled"] = bool(out.get("enabled", True))
    for p in spec.params:
        if p.key in out:
            try:
                out[p.key] = p.clamp(out[p.key])
            except (TypeError, ValueError):
                out[p.key] = p.initial()
        else:
            out[p.key] = p.initial()
    return out
