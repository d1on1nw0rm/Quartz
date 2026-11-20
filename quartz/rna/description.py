from __future__ import annotations

from typing import Any, Iterator

from .annotations import iter_properties
from .properties import PropertyDef


class Description:
    def __init__(self, owner):
        if isinstance(owner, type):
            self.owner = owner
        else:
            self.owner = type(owner)

    def __iter__(self) -> Iterator[PropertyDef]:
        return iter_properties(self.owner)

    def __len__(self) -> int:
        return sum(1 for _ in iter_properties(self.owner))

    def __contains__(self, identifier: str) -> bool:
        return any(p.identifier == identifier for p in iter_properties(self.owner))

    def __getitem__(self, identifier: str) -> PropertyDef:
        for p in iter_properties(self.owner):
            if p.identifier == identifier:
                return p
        raise KeyError(identifier)

    def groups(self) -> tuple[str, ...]:
        seen = []
        for p in iter_properties(self.owner):
            g = ""
            try:
                g = p.meta.get("group", "") if isinstance(p.meta, dict) or hasattr(p.meta, "get") else ""
            except Exception:
                g = ""
            if g not in seen:
                seen.append(g)
        return tuple(seen)

    def in_group(self, group: str) -> tuple[PropertyDef, ...]:
        return tuple(p for p in iter_properties(self.owner) if (p.meta.get("group", "") if hasattr(p.meta, "get") else "") == group)

    def children_of(self, identifier: str) -> tuple[PropertyDef, ...]:
        return tuple(p for p in iter_properties(self.owner) if (p.meta.get("parent") if hasattr(p.meta, "get") else None) == identifier)

    def is_enabled(self, inst: object, identifier: str) -> bool:
        p = self[identifier]
        meta = p.meta if hasattr(p.meta, "get") else {}
        enabled_if = meta.get("enabled_if") if hasattr(meta, "get") else None
        if callable(enabled_if):
            try:
                return bool(enabled_if(inst))
            except Exception:
                return True
        parent = meta.get("parent") if hasattr(meta, "get") else None
        if isinstance(parent, str) and parent:
            try:
                val = getattr(inst, parent, None)
                if isinstance(val, bool):
                    return bool(val)
            except Exception:
                pass
        return True

    def is_visible(self, inst: object, identifier: str) -> bool:
        p = self[identifier]
        meta = p.meta if hasattr(p.meta, "get") else {}
        visible_if = meta.get("visible_if") if hasattr(meta, "get") else None
        if callable(visible_if):
            try:
                return bool(visible_if(inst))
            except Exception:
                return True
        return not getattr(p, "is_hidden", False)

    def to_rna_dict(self) -> dict[str, dict]:
        return {p.identifier: p.to_rna_dict() for p in iter_properties(self.owner)}


def describe(cls_or_inst):
    return Description(cls_or_inst)
