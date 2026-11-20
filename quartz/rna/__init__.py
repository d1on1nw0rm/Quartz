from __future__ import annotations

from . import annotations, collections, datapath, description, hooks, idprops, properties, rnainfo, struct
from . import datapath as datapath_mod
from .annotations import (
    collect_annotations,
    define_property,
    get_property,
    install_properties,
    iter_properties,
    own_annotations,
    remove_property,
    uninstall_properties,
)
from .collections import GroupCollection, PropArray, PropCollection
from .datapath import PathToken, PropertyRef, escape_identifier, format as format_path, parse, resolve, unescape_identifier
from .description import Description, describe
from .hooks import HOOK_NAMES, install as install_hooks, note_missing, reset as reset_hooks, restore as restore_hooks, snapshot as snapshot_hooks
from .idprops import (
    IDPropertyArray,
    IDPropertyGroup,
    IDPropertyUIManager,
    rna_idprop_quote_path,
    rna_idprop_ui_create,
    rna_idprop_value_to_python,
)
from .properties import (
    BoolDef,
    CollectionDef,
    EnumDef,
    EnumItem,
    FloatDef,
    FloatDef as FloatDef,
    INT_MAX,
    INT_MIN,
    IntDef,
    META_KEYS,
    OPTION_FLAGS,
    OVERRIDE_FLAGS,
    PointerDef,
    PropertyDef,
    StringDef,
    build_property,
    normalize_enum_items,
    to_float32,
)
from .rnainfo import RNAEnumItem, RNAProperty, RNAStruct
from .struct import IDRef, MISSING, PropertyGroup, Struct, StructMeta, builtin_struct

__all__ = [
    "Struct", "StructMeta", "PropertyGroup", "builtin_struct", "IDRef",
    "PropertyDef", "BoolDef", "IntDef", "FloatDef", "StringDef", "EnumDef",
    "PointerDef", "CollectionDef", "EnumItem", "PropCollection", "GroupCollection",
    "PropArray", "IDPropertyGroup", "IDPropertyArray", "IDPropertyUIManager",
    "rna_idprop_ui_create", "rna_idprop_value_to_python", "rna_idprop_quote_path",
    "RNAStruct", "RNAProperty", "RNAEnumItem", "Description", "describe",
    "collect_annotations", "install_properties", "uninstall_properties",
    "define_property", "remove_property", "get_property", "iter_properties",
    "PathToken", "PropertyRef", "escape_identifier", "parse", "format_path",
    "resolve", "unescape_identifier", "HOOK_NAMES", "hooks", "datapath",
]
import quartz.rna.hooks as hooks_mod
hooks = hooks_mod
