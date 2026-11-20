from __future__ import annotations

import importlib
import pkgutil

from .registry import (CATEGORIES, INPUTS, SPECS, BuildInput, ObjectSpec, Param, all_specs,
                       by_category, defaults, get, mesh_chains, mesh_is_spline, register)

__all__ = ["CATEGORIES", "INPUTS", "SPECS", "BuildInput", "ObjectSpec", "Param", "all_specs",
           "by_category", "defaults", "get", "mesh_chains", "mesh_is_spline", "register"]

PREFIXES = ("prim_", "spline_", "gen_")

importlib.import_module(f"{__name__}.builtin")
for _info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    if _info.name.startswith(PREFIXES):
        importlib.import_module(f"{__name__}.{_info.name}")
