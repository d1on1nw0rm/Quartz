import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHIM_SET = {"bpy", "mathutils", "bmesh", "bpy_extras", "addon_utils", "idprop",
            "rna_prop_ui", "bl_math", "bl_ui", "bl_operators", "gpu", "gpu_extras",
            "blf", "aud", "bl_ext"}


def _path_to_mod(rel: str) -> str:
    parts = rel.split("/")
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


_L2_PACKAGES = ("quartz.types", "quartz.utils", "quartz.io", "quartz.operators")
_L2_MODULES = ("quartz.depsgraph", "quartz.registry", "quartz.ui", "quartz.session",
               "quartz.contexts", "quartz.ops", "quartz.undo", "quartz.testing")
_L3_PACKAGES = ("quartz.compat", "quartz.extras", "quartz.bmesh", "quartz.addons")
_L3_MODULES = ("quartz.cli", "quartz.sweep", "quartz.scan")


def _in_package(modname: str, pkg: str) -> bool:
    return modname == pkg or modname.startswith(pkg + ".")


def _quartz_group(modname: str) -> str | None:
    if modname == "quartz":
        return "facade"
    if modname in ("quartz._version", "quartz.path") or _in_package(modname, "quartz.app"):
        return "L1-app"
    if modname in ("quartz.errors", "quartz.props") or _in_package(modname, "quartz.rna"):
        return "L1-rna"
    if _in_package(modname, "quartz.math"):
        return "L1-math"
    if _in_package(modname, "quartz.geometry"):
        return "L1-geometry"
    if modname in _L2_MODULES or any(_in_package(modname, p) for p in _L2_PACKAGES):
        return "L2"
    if modname in _L3_MODULES or any(_in_package(modname, p) for p in _L3_PACKAGES):
        return "L3"
    return None


def _source_group(rel: str) -> str:
    if rel.startswith("compat/"):
        return "shim"
    modname = _path_to_mod(rel)
    if modname == "quartz":
        return "facade"
    g = _quartz_group(modname)
    return g if g is not None else "L3"


def _resolve_rel(modname: str, node: ast.ImportFrom, is_package: bool = False) -> str | None:
    if node.level == 0:
        return node.module
    parts = modname.split(".")
    pkg_parts = parts if is_package else parts[:-1]
    if node.level > len(pkg_parts):
        return None
    base_parts = pkg_parts[: len(pkg_parts) - node.level + 1]
    if node.module:
        return ".".join(base_parts + node.module.split("."))
    return ".".join(base_parts)


def _iter_import_nodes(node: ast.AST, module_level_only: bool = False):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            yield child
        if module_level_only and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield from _iter_import_nodes(child, module_level_only)


def _collect_imports(tree: ast.AST, modname: str, is_package: bool = False,
                     module_level_only: bool = False) -> list[tuple[int, str]]:
    out = []
    for node in _iter_import_nodes(tree, module_level_only):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_rel(modname, node, is_package)
            if base:
                out.append((node.lineno, base))
            elif node.names:
                for alias in node.names:
                    out.append((node.lineno, alias.name))
    return out


def _classify(modname: str) -> tuple[str, str | None]:
    top = modname.split(".")[0]
    if top in sys.stdlib_module_names:
        return ("stdlib", None)
    if top == "numpy":
        return ("numpy", None)
    if top == "quartz":
        return ("quartz", _quartz_group(modname))
    if top in SHIM_SET:
        return ("shim", "shim")
    return ("other", None)


def _allowed(source_group: str, kind: str, target_group: str | None, modname: str) -> bool:
    if source_group == "facade":
        if kind == "stdlib":
            return True
        if kind == "quartz":
            return modname == "quartz._version"
        return False
    allowed_sets = {
        "L1-app": {"stdlib"},
        "L1-rna": {"stdlib", "numpy", "self"},
        "L1-math": {"stdlib", "numpy", "self"},
        "L1-geometry": {"stdlib", "numpy", "self"},
        "L2": {"stdlib", "numpy", "L1", "L2"},
        "L3": {"stdlib", "numpy", "L1", "L2", "L3"},
        "shim": {"stdlib", "quartz", "shim"},
    }
    aset = allowed_sets.get(source_group, set())
    if kind == "stdlib":
        return "stdlib" in aset
    if kind == "numpy":
        return "numpy" in aset
    if kind == "quartz":
        if source_group == "shim":
            return True
        if source_group.startswith("L1-"):
            return target_group == source_group
        if source_group == "L2":
            return target_group is not None and (target_group.startswith("L1-") or target_group == "L2")
        if source_group == "L3":
            return True
        if source_group == "L1-app":
            return False
        return False
    if kind == "shim":
        return source_group == "shim"
    return False


def test_layering():
    violations = []
    for base in ("quartz", "compat"):
        root = ROOT / base
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(ROOT).as_posix()
            sg = _source_group(rel)
            modname = _path_to_mod(rel)
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                violations.append(f"{rel}: syntax error {exc}")
                continue
            is_pkg = (p.name == "__init__.py")
            module_level_only = (sg == "facade")
            for lineno, imp in _collect_imports(tree, modname, is_pkg, module_level_only):
                kind, tg = _classify(imp)
                if not _allowed(sg, kind, tg, imp):
                    violations.append(f"{rel}:{lineno} {imp}")
    assert not violations, "\n".join(violations)
