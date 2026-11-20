from __future__ import annotations

from typing import Any

from .collections import PropCollection
from .properties import PropertyDef


class RNAEnumItem:
    def __init__(self, identifier, name, description="", icon="", value=0):
        self.identifier = identifier
        self.name = name
        self.description = description
        self.icon = icon
        self.value = value


class RNAProperty:
    def __init__(self, pdef: PropertyDef | None, *, owner_rna: "RNAStruct | None" = None):
        self._pdef = pdef
        self.q_definition = pdef
        self.icon = ""
        self.is_library_editable = False
        self.is_overridable = False
        self.is_registered = False
        self.is_registered_optional = False
        self.is_required = False
        self.is_argument_optional = False
        self.is_output = False
        self.is_runtime = False
        if pdef is None:
            self._init_rna_type(owner_rna)
            return
        self.identifier = pdef.identifier
        self.name = pdef.name
        self.description = pdef.description
        self.translation_context = pdef.translation_context
        self.type = pdef.kind
        self.subtype = pdef.subtype
        self.unit = pdef.unit
        self.tags = pdef.tags
        self.is_readonly = pdef.is_readonly
        self.is_hidden = pdef.is_hidden
        self.is_skip_save = pdef.is_skip_save
        self.is_animatable = pdef.is_animatable
        self.is_enum_flag = pdef.is_enum_flag
        self.is_never_none = pdef.is_never_none
        self.is_runtime = True
        if pdef.is_array:
            arr = pdef.default_value(None)
            self.default_array = tuple(arr.reshape(-1).tolist())
            self.default = self.default_array[0] if self.default_array else None
        else:
            self.default_array = ()
            self.default = pdef.default_value(None)
        self.array_length = pdef.array_length
        self.array_dimensions = (tuple(pdef.size) + (0, 0, 0))[:3] if pdef.is_array else (0, 0, 0)
        numeric = pdef.kind in ("INT", "FLOAT")
        self.hard_min = pdef.hard_min if numeric else 0
        self.hard_max = pdef.hard_max if numeric else 0
        self.soft_min = pdef.soft_min if numeric else 0
        self.soft_max = pdef.soft_max if numeric else 0
        self.step = pdef.step if numeric else 0
        self.precision = pdef.precision if pdef.kind == "FLOAT" else 0
        self.length_max = pdef.maxlen if pdef.kind == "STRING" else 0
        self.enum_items = _EnumItemsCollection(pdef)
        self.enum_items_static = self.enum_items
        ft = pdef.fixed_type if pdef.kind in ("POINTER", "COLLECTION") else None
        self.fixed_type = ft.__dict__.get("bl_rna") if isinstance(ft, type) else None

    def _init_rna_type(self, owner_rna):
        self.identifier = "rna_type"
        self.name = "RNA"
        self.description = "RNA type definition"
        self.translation_context = "*"
        self.type = "POINTER"
        self.subtype = "NONE"
        self.unit = "NONE"
        self.tags = frozenset()
        self.is_readonly = True
        self.is_hidden = True
        self.is_skip_save = False
        self.is_animatable = False
        self.is_enum_flag = False
        self.is_never_none = True
        self.default = None
        self.default_array = ()
        self.array_length = 0
        self.array_dimensions = (0, 0, 0)
        self.hard_min = self.hard_max = self.soft_min = self.soft_max = self.step = 0
        self.precision = 0
        self.length_max = 0
        self.enum_items = _EmptyCollection()
        self.enum_items_static = self.enum_items
        self.fixed_type = None
        try:
            from .struct import Struct
            self.fixed_type = Struct.__dict__.get("bl_rna")
        except ImportError:
            pass


class _EnumItemsCollection(PropCollection):
    def __init__(self, pdef):
        super().__init__(owner=None, path="")
        self._pdef = pdef

    def _q_items(self):
        try:
            items = self._pdef.items_for(None, None)
        except Exception:
            items = self._pdef.items or ()
        res = []
        for it in items:
            res.append(RNAEnumItem(it.identifier, it.name, it.description, it.icon, it.value))
        return res

    def _q_key(self, item):
        return item.identifier


class RNAStruct:
    def __init__(self, py_class, identifier=None):
        self._py_class = py_class
        self.identifier = identifier or py_class.__name__
        self.name = getattr(py_class, "bl_label", self.identifier)
        doc = getattr(py_class, "__doc__", "") or ""
        self.description = doc.strip().splitlines()[0] if doc.strip() else ""
        self.translation_context = "*"
        self.nested = None
        self.properties = _LivePropCollection(self, py_class)
        self.functions = _EmptyCollection()
        self.q_py_class = py_class

    @property
    def base(self):
        for klass in self._py_class.__mro__[1:]:
            rna = klass.__dict__.get("bl_rna")
            if isinstance(rna, RNAStruct):
                return rna
        return None

    def __repr__(self):
        return f'<bpy_struct, Struct("{self.identifier}") at 0x{id(self):016X}>'


class _LivePropCollection(PropCollection):
    def __init__(self, rna_struct, py_class):
        super().__init__(owner=None, path="")
        self._rna = rna_struct
        self._py_class = py_class

    def _q_items(self):
        from .annotations import iter_properties
        res = [RNAProperty(None, owner_rna=self._rna)]
        res.extend(RNAProperty(pdef) for pdef in iter_properties(self._py_class))
        return res

    def _q_key(self, item):
        return item.identifier


class _EmptyCollection(PropCollection):
    def _q_items(self):
        return []
