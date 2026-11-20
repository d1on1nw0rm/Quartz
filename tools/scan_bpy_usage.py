from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_SCRIPTS = "C:/Program Files/Blender Foundation/Blender 5.2/5.2/scripts"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = PROJECT_ROOT / "data" / "bpy_usage.json"
DEFAULT_MD = PROJECT_ROOT / "docs" / "research" / "bpy_usage.md"

PRIMARY_ROOTS = (
    "bpy", "mathutils", "bmesh", "bpy_extras", "gpu", "blf",
    "idprop", "aud", "gpu_extras", "addon_utils",
)
EXTRA_BLENDER_MODULES = {
    "bl_math", "imbuf", "freestyle", "_bpy", "_cycles", "bgl", "bl_ui",
    "bl_operators", "bpy_types", "_bpy_types", "rna_prop_ui", "nodeitems_utils",
    "rna_keymap_ui", "bl_keymap_utils", "bl_i18n_utils", "bl_app_override",
    "bpy_restrict_state", "_bpy_restrict_state", "keyingsets_utils",
    "_keyingsets_utils", "rna_info", "_rna_info", "bl_previews_utils",
    "_bl_previews_utils", "bl_rna_utils", "_bl_rna_utils", "bl_ui_utils",
    "_bl_ui_utils", "_bl_i18n_utils", "_bpy_internal", "bl_app_template_utils",
    "blend_render_info", "_bl_console_utils", "_bl_text_utils", "hydra",
    "_hydra_storm", "bl_pkg",
}

LAYOUT_CONTAINERS = {
    "row", "column", "box", "split", "column_flow", "grid_flow", "menu_pie",
    "panel", "panel_prop", "layout_panel",
}

EASY_CORE_EXACT = {
    "bpy.types.Operator", "bpy.types.Panel", "bpy.types.Menu", "bpy.types.Header",
    "bpy.types.PropertyGroup", "bpy.types.AddonPreferences", "bpy.types.UIList",
    "bpy.utils.register_class", "bpy.utils.unregister_class",
    "bpy.utils.register_classes_factory", "bpy.utils.register_submodule_factory",
    "bpy.types.ID", "bpy.types.Object", "bpy.types.Mesh", "bpy.types.Material",
    "bpy.types.Scene", "bpy.types.Collection", "bpy.types.Camera",
    "bpy.types.Light", "bpy.types.Context", "bpy.types.Event",
    "bpy.types.WindowManager", "bpy.types.ViewLayer", "bpy.types.Image",
    "bpy.data.objects", "bpy.data.meshes", "bpy.data.materials",
    "bpy.data.collections", "bpy.data.scenes", "bpy.data.cameras",
    "bpy.data.lights", "bpy.data.images", "bpy.data.filepath",
    "bpy.data.is_saved", "bpy.data.is_dirty",
    "bpy.context.scene", "bpy.context.object", "bpy.context.active_object",
    "bpy.context.selected_objects", "bpy.context.view_layer",
    "bpy.context.collection", "bpy.context.preferences",
    "bpy.context.window_manager", "bpy.context.mode",
    "bpy.app.version", "bpy.app.version_string", "bpy.app.version_file",
    "bpy.app.background", "bpy.app.binary_path", "bpy.app.debug",
    "bpy.app.handlers.persistent", "bpy.app.handlers.load_post",
    "bpy.app.handlers.load_pre", "bpy.app.handlers.save_pre",
    "bpy.app.handlers.save_post", "bpy.app.handlers.depsgraph_update_post",
    "bpy.app.translations.pgettext", "bpy.app.translations.pgettext_iface",
    "bpy.app.translations.pgettext_tip", "bpy.app.translations.pgettext_data",
    "bpy.app.translations.pgettext_rpt", "bpy.app.translations.pgettext_n",
    "bpy.app.translations.contexts", "bpy.app.translations.register",
    "bpy.app.translations.unregister",
    "mathutils.Vector", "mathutils.Matrix", "mathutils.Quaternion",
    "mathutils.Euler", "mathutils.Color",
    "bpy_extras.io_utils.ImportHelper", "bpy_extras.io_utils.ExportHelper",
    "bpy_extras.io_utils.axis_conversion", "bpy_extras.io_utils.orientation_helper",
    "bpy_extras.io_utils.unpack_list", "bpy_extras.io_utils.unpack_face_list",
    "bpy_extras.io_utils.path_reference", "bpy_extras.io_utils.path_reference_mode",
    "bpy_extras.io_utils.poll_file_object_drop",
    "bpy_extras.object_utils.object_data_add",
    "bpy_extras.object_utils.AddObjectHelper",
}
EASY_CORE_PREFIXES = ("bpy.props.", "bpy.path.")

UI_CLASS_RE = re.compile(r"^[A-Z0-9]+_(MT|PT|HT|UL|OT|AST|GT|GGT)_")


def is_easy_core(sym: str) -> bool:
    return sym in EASY_CORE_EXACT or sym.startswith(EASY_CORE_PREFIXES)


def cut_depth(parts: list[str]) -> int:
    root = parts[0]
    sub = parts[1] if len(parts) > 1 else ""
    third = parts[2] if len(parts) > 2 else ""
    if root == "bpy":
        if sub == "ops":
            return 4
        if sub == "utils" and third in ("previews", "units", "toolsystem"):
            return 4
        if sub == "app" and third in ("handlers", "translations", "timers", "icons", "driver_namespace"):
            return 4
        if sub in ("types", "props", "data", "context", "utils", "app", "path", "msgbus"):
            return 3
        return 2
    if root == "mathutils":
        return 3 if sub in ("geometry", "kdtree", "bvhtree", "noise", "interpolate") else 2
    if root == "bmesh":
        return 3 if sub in ("ops", "types", "utils", "geometry") else 2
    if root in ("bpy_extras", "gpu", "gpu_extras", "idprop"):
        return 3
    return 2


def dotted(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        parts.reverse()
        return parts
    return None


def iter_scope(node: ast.AST):
    stack = list(ast.iter_child_nodes(node))
    while stack:
        cur = stack.pop()
        yield cur
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(cur))


class GroupStats:

    def __init__(self, name: str, kind: str):
        self.name = name
        self.kind = kind
        self.files = 0
        self.lines = 0
        self.parse_errors: list[str] = []
        self.refs: Counter[str] = Counter()
        self.calls: Counter[str] = Counter()
        self.detail: Counter[str] = Counter()
        self.other_mod_refs: Counter[str] = Counter()
        self.imports_std: Counter[str] = Counter()
        self.imports_blender: Counter[str] = Counter()
        self.imports_third: Counter[str] = Counter()
        self.star_imports: Counter[str] = Counter()
        self.dynamic_getattr: Counter[str] = Counter()
        self.context_attrs: Counter[str] = Counter()
        self.layout_attrs: Counter[str] = Counter()
        self.event_attrs: Counter[str] = Counter()
        self.self_report = 0
        self.rna_extensions: Counter[str] = Counter()
        self.classes: list[dict] = []

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "files": self.files,
            "lines": self.lines,
            "parse_errors": self.parse_errors,
            "symbols": {
                s: {"refs": self.refs[s], "calls": self.calls[s]}
                for s in sorted(self.refs)
            },
            "data_detail": dict(sorted(self.detail.items())),
            "other_blender_module_refs": dict(sorted(self.other_mod_refs.items())),
            "imports": {
                "stdlib": dict(sorted(self.imports_std.items())),
                "blender": dict(sorted(self.imports_blender.items())),
                "third_party_or_local": dict(sorted(self.imports_third.items())),
                "star": dict(sorted(self.star_imports.items())),
            },
            "dynamic_getattr_on_api": dict(sorted(self.dynamic_getattr.items())),
            "implicit": {
                "context": dict(sorted(self.context_attrs.items())),
                "layout": dict(sorted(self.layout_attrs.items())),
                "event": dict(sorted(self.event_attrs.items())),
                "operator_self_report": self.self_report,
            },
            "rna_extensions": dict(sorted(self.rna_extensions.items())),
        }


class ModuleScanner:

    def __init__(self, stats: GroupStats, blender_modules: set[str], local_names: set[str]):
        self.st = stats
        self.blender_modules = blender_modules
        self.local_names = local_names
        self.tracked_roots = set(PRIMARY_ROOTS) | blender_modules
        self.aliases: dict[str, str] = {}

    def _classify_import(self, mod: str, level: int) -> None:
        if level > 0:
            return
        root = mod.split(".")[0]
        if root in PRIMARY_ROOTS or root in self.blender_modules:
            self.st.imports_blender[root] += 1
        elif root in sys.stdlib_module_names:
            self.st.imports_std[root] += 1
        elif root in self.local_names:
            return
        else:
            self.st.imports_third[root] += 1

    def collect_imports(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self._classify_import(a.name, 0)
                    root = a.name.split(".")[0]
                    if root not in self.tracked_roots:
                        continue
                    if a.asname:
                        self.aliases[a.asname] = a.name
                    else:
                        self.aliases[root] = root
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self._classify_import(mod, node.level)
                if node.level or not mod:
                    continue
                root = mod.split(".")[0]
                if root not in self.tracked_roots:
                    continue
                for a in node.names:
                    if a.name == "*":
                        self.st.star_imports[mod] += 1
                        continue
                    self.aliases[a.asname or a.name] = f"{mod}.{a.name}"

    def collect_namespace_aliases(self, tree: ast.Module) -> None:
        stack = list(tree.body)
        top_level: list[ast.stmt] = []
        while stack:
            st = stack.pop()
            top_level.append(st)
            if isinstance(st, (ast.If, ast.Try, ast.With)):
                for field in ("body", "orelse", "finalbody"):
                    stack.extend(getattr(st, field, []) or [])
                for h in getattr(st, "handlers", []) or []:
                    stack.extend(h.body)
        for node in top_level:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name) or tgt.id in self.aliases:
                continue
            chain = self.resolve(node.value)
            if chain is None:
                continue
            parts = chain.split(".")
            if parts[0] in PRIMARY_ROOTS and len(parts) < cut_depth(parts):
                self.aliases[tgt.id] = chain

    def resolve(self, node: ast.AST) -> str | None:
        parts = dotted(node)
        if not parts:
            return None
        base = self.aliases.get(parts[0])
        if base is None:
            return None
        return ".".join([base] + parts[1:])

    def scan(self, tree: ast.Module) -> None:
        self.collect_imports(tree)
        self.collect_namespace_aliases(tree)
        parents: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node

        for node in ast.walk(tree):
            if isinstance(node, (ast.Attribute, ast.Name)):
                parent = parents.get(id(node))
                if isinstance(parent, ast.Attribute) and parent.value is node:
                    continue
                if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
                    continue
                full = self.resolve(node)
                if full is None:
                    continue
                parts = full.split(".")
                if len(parts) < 2:
                    continue
                depth = cut_depth(parts)
                sym = ".".join(parts[:depth])
                is_call = isinstance(parent, ast.Call) and parent.func is node and len(parts) <= depth
                if parts[0] in PRIMARY_ROOTS:
                    self.st.refs[sym] += 1
                    if is_call:
                        self.st.calls[sym] += 1
                    if parts[:2] == ["bpy", "data"] and len(parts) > 3:
                        self.st.detail[".".join(parts[:4])] += 1
                    if parts[:2] == ["bpy", "context"] and len(parts) > 2:
                        key = ".".join(parts[2:4] if parts[2] == "window_manager" else parts[2:3])
                        self.st.context_attrs[key] += 1
                else:
                    self.st.other_mod_refs[".".join(parts[:2])] += 1
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id in ("getattr", "hasattr") and node.args:
                    target = self.resolve(node.args[0])
                    if target and target.split(".")[0] in PRIMARY_ROOTS:
                        self.st.dynamic_getattr[f"{fn.id}({target}, ...)"] += 1
            if isinstance(node, (ast.Assign, ast.Delete)):
                targets = node.targets
                for t in targets:
                    if isinstance(t, ast.Attribute):
                        full = self.resolve(t)
                        if full and full.startswith("bpy.types.") and len(full.split(".")) == 4:
                            self.st.rna_extensions[full.split(".")[2]] += 1

        self.scan_functions(tree)
        self.collect_classes(tree)

    def scan_functions(self, tree: ast.Module) -> None:
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = {a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs}
            body_nodes = list(iter_scope(fn))
            layout_vars: set[str] = {"layout"} if "layout" in params else set()

            def is_layout(expr: ast.AST) -> bool:
                if isinstance(expr, ast.Attribute) and expr.attr == "layout" and \
                        isinstance(expr.value, ast.Name) and expr.value.id == "self":
                    return True
                if isinstance(expr, ast.Name) and expr.id in layout_vars:
                    return True
                if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and \
                        expr.func.attr in LAYOUT_CONTAINERS and is_layout(expr.func.value):
                    return True
                return False

            changed = True
            while changed:
                changed = False
                for n in body_nodes:
                    if isinstance(n, ast.Assign) and is_layout(n.value):
                        for t in n.targets:
                            names = [t] if isinstance(t, ast.Name) else (
                                list(t.elts) if isinstance(t, ast.Tuple) else [])
                            for nm in names:
                                if isinstance(nm, ast.Name) and nm.id not in layout_vars:
                                    layout_vars.add(nm.id)
                                    changed = True
                    elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and \
                            isinstance(n.targets[0], ast.Tuple) and isinstance(n.value.func, ast.Attribute) \
                            and n.value.func.attr in ("panel", "panel_prop", "layout_panel") \
                            and is_layout(n.value.func.value):
                        for nm in n.targets[0].elts:
                            if isinstance(nm, ast.Name) and nm.id not in layout_vars:
                                layout_vars.add(nm.id)
                                changed = True

            for n in body_nodes:
                if not isinstance(n, ast.Attribute):
                    continue
                v = n.value
                if is_layout(v):
                    self.st.layout_attrs[n.attr] += 1
                elif isinstance(v, ast.Name) and v.id == "context" and "context" in params:
                    self.st.context_attrs[n.attr] += 1
                elif isinstance(v, ast.Attribute) and v.attr == "window_manager" and \
                        isinstance(v.value, ast.Name) and v.value.id == "context" and "context" in params:
                    self.st.context_attrs[f"window_manager.{n.attr}"] += 1
                elif isinstance(v, ast.Name) and v.id == "event" and "event" in params:
                    self.st.event_attrs[n.attr] += 1
                elif isinstance(v, ast.Name) and v.id == "self" and n.attr == "report":
                    self.st.self_report += 1

    def collect_classes(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = []
            for b in node.bases:
                expr = b.value if isinstance(b, ast.Subscript) else b
                full = self.resolve(expr)
                if full is not None:
                    bases.append(("api", full))
                else:
                    parts = dotted(expr)
                    bases.append(("local", parts[-1] if parts else "?"))
            methods = sorted(
                n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
            attrs = set()
            for n in node.body:
                if isinstance(n, ast.Assign):
                    for t in n.targets:
                        if isinstance(t, ast.Name):
                            attrs.add(t.id)
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                    attrs.add(n.target.id)
            self.st.classes.append({
                "name": node.name,
                "bases": bases,
                "methods": methods,
                "bl_attrs": sorted(a for a in attrs if a.startswith("bl_")),
                "n_annotations": sum(1 for n in node.body if isinstance(n, ast.AnnAssign)),
            })


def discover_blender_modules(scripts: Path) -> set[str]:
    found = set(EXTRA_BLENDER_MODULES)
    for sub in ("modules", "startup"):
        d = scripts / sub
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.name == "__pycache__":
                continue
            name = p.stem if p.suffix == ".py" else p.name
            if p.is_dir() or p.suffix == ".py":
                found.add(name)
    found -= set(PRIMARY_ROOTS)
    return found


def build_groups(scripts: Path) -> list[tuple[str, str, list[Path], Path]]:
    groups = []
    addons = scripts / "addons_core"
    for entry in sorted(addons.iterdir()):
        if entry.name.startswith((".", "__")):
            continue
        if entry.is_dir():
            files = sorted(p for p in entry.rglob("*.py") if "__pycache__" not in p.parts)
            groups.append((entry.name, "addon", files, entry))
        elif entry.suffix == ".py":
            groups.append((entry.stem, "addon", [entry], addons))
    tpl = scripts / "templates_py"
    for f in sorted(tpl.rglob("*.py")):
        rel = f.relative_to(tpl).with_suffix("").as_posix()
        groups.append((f"templates_py/{rel}", "template", [f], f.parent))
    ops = scripts / "startup" / "bl_operators"
    files = sorted(p for p in ops.rglob("*.py") if "__pycache__" not in p.parts)
    groups.append(("bl_operators", "bl_operators", files, ops))
    return groups


def resolve_class_bases(stats: GroupStats) -> tuple[Counter, Counter, dict]:
    by_name: dict[str, list[dict]] = defaultdict(list)
    for c in stats.classes:
        by_name[c["name"]].append(c)

    memo: dict[str, set[str]] = {}

    def api_bases(name: str, seen: frozenset) -> set[str]:
        if name in memo:
            return memo[name]
        out: set[str] = set()
        for c in by_name.get(name, []):
            for kind, val in c["bases"]:
                if kind == "api":
                    out.add(val)
                elif val not in seen:
                    out |= api_bases(val, seen | {val})
        memo[name] = out
        return out

    direct: Counter[str] = Counter()
    effective: Counter[str] = Counter()
    per_base: dict[str, dict] = defaultdict(lambda: {"methods": Counter(), "bl_attrs": Counter(), "classes": 0})
    for c in stats.classes:
        for kind, val in c["bases"]:
            if kind == "api":
                direct[val] += 1
        eff = set()
        for kind, val in c["bases"]:
            if kind == "api":
                eff.add(val)
            else:
                eff |= api_bases(val, frozenset({c["name"], val}))
        for b in eff:
            effective[b] += 1
            if b.startswith("bpy.types."):
                pb = per_base[b]
                pb["classes"] += 1
                pb["methods"].update(c["methods"])
                pb["bl_attrs"].update(c["bl_attrs"])
    return direct, effective, per_base


def scan(scripts: Path) -> dict:
    blender_modules = discover_blender_modules(scripts)
    groups_out = []
    all_stats: list[GroupStats] = []
    t0 = time.time()
    for name, kind, files, pkg_root in build_groups(scripts):
        st = GroupStats(name, kind)
        local_names = {p.stem for p in files} | {p.name for p in pkg_root.rglob("*") if p.is_dir()}
        local_names.add(pkg_root.name)
        for f in files:
            try:
                src = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                src = f.read_text(encoding="latin-1")
            st.files += 1
            st.lines += src.count("\n") + 1
            try:
                tree = ast.parse(src, filename=str(f))
            except SyntaxError as exc:
                st.parse_errors.append(f"{f.name}: {exc.msg} (line {exc.lineno})")
                continue
            ModuleScanner(st, blender_modules, local_names).scan(tree)
        all_stats.append(st)

    sym_groups: dict[str, set[str]] = defaultdict(set)
    sym_refs: Counter[str] = Counter()
    sym_calls: Counter[str] = Counter()
    kinds = {}
    base_groups: dict[str, set[str]] = defaultdict(set)
    base_direct_total: Counter[str] = Counter()
    base_effective_total: Counter[str] = Counter()
    base_detail: dict[str, dict] = defaultdict(lambda: {"methods": Counter(), "bl_attrs": Counter(), "classes": 0})
    implicit = {"context": (Counter(), defaultdict(set)), "layout": (Counter(), defaultdict(set)),
                "event": (Counter(), defaultdict(set))}
    rna_ext_groups: dict[str, set[str]] = defaultdict(set)
    other_mods: dict[str, set[str]] = defaultdict(set)
    third_party: dict[str, set[str]] = defaultdict(set)

    for st in all_stats:
        kinds[st.name] = st.kind
        direct, effective, per_base = resolve_class_bases(st)
        js = st.to_json()
        js["subclassed_direct"] = dict(sorted(direct.items()))
        js["subclassed_effective"] = dict(sorted(effective.items()))
        js["classes_total"] = len(st.classes)
        distinct = sorted(st.refs)
        non_core = sorted(s for s in distinct if not is_easy_core(s))
        js["footprint"] = {
            "distinct_symbols": len(distinct),
            "non_core_symbols": len(non_core),
            "non_core": non_core,
            "ops_calls": sorted(s for s in distinct if s.startswith("bpy.ops.")),
            "uses_bmesh": any(s.startswith("bmesh") for s in distinct),
            "uses_gpu": any(s.startswith(("gpu", "blf", "gpu_extras")) for s in distinct),
        }
        groups_out.append(js)
        for s in st.refs:
            sym_groups[s].add(st.name)
            sym_refs[s] += st.refs[s]
            sym_calls[s] += st.calls[s]
        for b, n in effective.items():
            base_groups[b].add(st.name)
            base_effective_total[b] += n
        for b, n in direct.items():
            base_direct_total[b] += n
        for b, d in per_base.items():
            base_detail[b]["classes"] += d["classes"]
            base_detail[b]["methods"].update(d["methods"])
            base_detail[b]["bl_attrs"].update(d["bl_attrs"])
        for key, counter in (("context", st.context_attrs), ("layout", st.layout_attrs), ("event", st.event_attrs)):
            tot, grp = implicit[key]
            for a, n in counter.items():
                tot[a] += n
                grp[a].add(st.name)
        for t in st.rna_extensions:
            rna_ext_groups[t].add(st.name)
        for m in st.imports_blender:
            if m not in PRIMARY_ROOTS:
                other_mods[m].add(st.name)
        for m in st.imports_third:
            third_party[m].add(st.name)

    def count_kind(names: set[str], kind: str) -> int:
        return sum(1 for n in names if kinds[n] == kind)

    symbols = {}
    for s in sym_refs:
        g = sym_groups[s]
        symbols[s] = {
            "groups": len(g),
            "addons": count_kind(g, "addon"),
            "templates": count_kind(g, "template"),
            "bl_operators": count_kind(g, "bl_operators"),
            "refs": sym_refs[s],
            "calls": sym_calls[s],
            "easy_core": is_easy_core(s),
            "ui_class_ref": bool(s.startswith("bpy.types.") and UI_CLASS_RE.match(s.split(".")[2])),
            "used_by": sorted(g),
        }

    bases = {}
    for b in base_effective_total:
        g = base_groups[b]
        d = base_detail.get(b)
        bases[b] = {
            "classes_effective": base_effective_total[b],
            "classes_direct": base_direct_total[b],
            "groups": len(g),
            "addons": count_kind(g, "addon"),
            "templates": count_kind(g, "template"),
            "bl_operators": count_kind(g, "bl_operators"),
            "used_by": sorted(g),
            "methods": dict(d["methods"].most_common()) if d else {},
            "bl_attrs": dict(d["bl_attrs"].most_common()) if d else {},
        }

    def implicit_table(key: str) -> dict:
        tot, grp = implicit[key]
        return {a: {"refs": tot[a], "groups": len(grp[a]), "addons": count_kind(grp[a], "addon")}
                for a, _ in tot.most_common()}

    n_kind = Counter(kinds.values())
    return {
        "generator": "tools/scan_bpy_usage.py",
        "author": "D1on1n",
        "scripts_root": scripts.as_posix(),
        "scan_seconds": round(time.time() - t0, 2),
        "population": {
            "addons": n_kind["addon"], "templates": n_kind["template"],
            "bl_operators": n_kind["bl_operators"], "groups": len(kinds),
            "files": sum(s.files for s in all_stats), "lines": sum(s.lines for s in all_stats),
            "parse_errors": sum(len(s.parse_errors) for s in all_stats),
        },
        "easy_core": {"exact": sorted(EASY_CORE_EXACT), "prefixes": list(EASY_CORE_PREFIXES)},
        "symbols": dict(sorted(symbols.items(), key=lambda kv: (-kv[1]["addons"], -kv[1]["groups"], -kv[1]["refs"], kv[0]))),
        "base_classes": dict(sorted(bases.items(), key=lambda kv: (-kv[1]["groups"], -kv[1]["classes_effective"]))),
        "implicit": {k: implicit_table(k) for k in implicit},
        "rna_extensions": {t: sorted(g) for t, g in sorted(rna_ext_groups.items(), key=lambda kv: -len(kv[1]))},
        "other_blender_modules": {m: sorted(g) for m, g in sorted(other_mods.items(), key=lambda kv: -len(kv[1]))},
        "third_party_imports": {m: sorted(g) for m, g in sorted(third_party.items(), key=lambda kv: -len(kv[1]))},
        "groups": groups_out,
    }



def compute_tiers(result: dict) -> dict:
    n_pkg = result["population"]["addons"] + result["population"]["bl_operators"]
    t1_min = max(2, (n_pkg + 1) // 2)
    tiers = {"tier1": [], "tier2": [], "tier3": [], "tail": []}
    for s, info in result["symbols"].items():
        pkg = info["addons"] + info["bl_operators"]
        tpl = info["templates"]
        if pkg >= t1_min:
            tiers["tier1"].append(s)
        elif pkg >= 3 or (pkg >= 2 and tpl >= 2) or tpl >= 5:
            tiers["tier2"].append(s)
        elif pkg >= 2 or tpl >= 2 or (pkg == 1 and info["refs"] >= 10):
            tiers["tier3"].append(s)
        else:
            tiers["tail"].append(s)
    tiers["rules"] = {
        "packages": n_pkg, "tier1_min_packages": t1_min,
        "tier2": "packages >= 3, or (packages >= 2 and templates >= 2), or templates >= 5",
        "tier3": "packages >= 2, or templates >= 2, or (1 package with >= 10 references)",
    }
    return tiers


def fmt_int(n: int) -> str:
    return f"{n:,}"


def pct(x: float) -> str:
    return f"{x:.1f}"


def compute_summary(result: dict, tiers: dict) -> dict:
    syms = result["symbols"]
    pkg_groups = [g for g in result["groups"] if g["kind"] != "template"]
    pkg_refs = Counter()
    for g in pkg_groups:
        for s, d in g["symbols"].items():
            pkg_refs[s] += d["refs"]
    total = sum(pkg_refs.values()) or 1
    core_refs = sum(n for s, n in pkg_refs.items() if is_easy_core(s))
    t12 = set(tiers["tier1"]) | set(tiers["tier2"])
    t12_refs = sum(n for s, n in pkg_refs.items() if s in t12)
    t123 = t12 | set(tiers["tier3"])
    t123_refs = sum(n for s, n in pkg_refs.items() if s in t123)
    ops = [s for s in syms if s.startswith("bpy.ops.")]
    ui_refs = [s for s, i in syms.items() if i["ui_class_ref"]]
    bases = result["base_classes"]
    op_b = bases.get("bpy.types.Operator", {})
    n_add = result["population"]["addons"]
    addons = [g for g in result["groups"] if g["kind"] == "addon"]
    core_only_tpl = [g["name"] for g in result["groups"]
                     if g["kind"] == "template" and g["footprint"]["non_core_symbols"] == 0]
    return {
        "distinct_symbols": len(syms),
        "single_group_symbols": len(tiers["tail"]),
        "package_refs_total": total,
        "package_refs_easy_core_pct": round(100 * core_refs / total, 1),
        "package_refs_tier12_pct": round(100 * t12_refs / total, 1),
        "package_refs_tier123_pct": round(100 * t123_refs / total, 1),
        "tier_sizes": {k: len(tiers[k]) for k in ("tier1", "tier2", "tier3", "tail")},
        "distinct_ops": len(ops),
        "ops_used_by_2plus_groups": sum(1 for s in ops if syms[s]["groups"] >= 2),
        "ui_class_refs": len(ui_refs),
        "operator_subclasses": op_b.get("classes_effective", 0),
        "operator_addons": op_b.get("addons", 0),
        "n_addons": n_add,
        "base_class_kinds_bpy_types": sum(1 for b in bases if b.startswith("bpy.types.")),
        "addons_using_bmesh": sum(1 for g in addons if g["footprint"]["uses_bmesh"]),
        "addons_using_gpu": sum(1 for g in addons if g["footprint"]["uses_gpu"]),
        "addons_with_le8_non_core": sorted(g["name"] for g in addons if g["footprint"]["non_core_symbols"] <= 8),
        "templates_core_only": len(core_only_tpl),
        "context_member_names": len(result["implicit"]["context"]),
        "layout_member_names": len(result["implicit"]["layout"]),
        "layout_prop_refs": result["implicit"]["layout"].get("prop", {}).get("refs", 0),
        "rna_extended_types": len(result["rna_extensions"]),
    }


def area_of(sym: str) -> str:
    parts = sym.split(".")
    if parts[0] == "bpy":
        return ".".join(parts[:2])
    return parts[0] if parts[0] != "mathutils" or len(parts) == 2 else ".".join(parts[:2])


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_markdown(result: dict) -> str:
    pop = result["population"]
    syms = result["symbols"]
    groups = result["groups"]
    tiers = compute_tiers(result)
    result["tiers"] = tiers
    sm = compute_summary(result, tiers)
    result["summary"] = sm
    addons = [g for g in groups if g["kind"] == "addon"]
    L: list[str] = []
    w = L.append

    w("# Real Blender API usage by add-ons (bpy usage)")
    w("")
    w("> Quartz - author: D1on1n. Report generated by `tools/scan_bpy_usage.py` "
      "(static analysis with `ast`, without running the analysed code). "
      "Raw data in `data/bpy_usage.json`.")
    w("")
    w("## 0. Key findings")
    w("")
    ts = sm["tier_sizes"]
    w(f"- Found **{sm['distinct_symbols']} distinct symbols** under the tracked roots; "
      f"**{sm['single_group_symbols']}** of them ({round(100 * sm['single_group_symbols'] / max(1, sm['distinct_symbols']))}%) "
      "appear in a single group. The tail is long, but the core is small.")
    w(f"- In the real packages (add-ons + `bl_operators`, {fmt_int(sm['package_refs_total'])} references), "
      f"the 'easy core' set covers **{pct(sm['package_refs_easy_core_pct'])}%** of the references; "
      f"Tier 1+2 ({ts['tier1'] + ts['tier2']} symbols) cover **{pct(sm['package_refs_tier12_pct'])}%** and "
      f"Tier 1+2+3 ({ts['tier1'] + ts['tier2'] + ts['tier3']} symbols) cover **{pct(sm['package_refs_tier123_pct'])}%**.")
    w(f"- `bpy.types.Operator` is subclassed by **{sm['operator_addons']} of {sm['n_addons']} add-ons** "
      f"({sm['operator_subclasses']} classes). Registration (`register_class`/`unregister_class`), `bpy.props.*` "
      "and `Panel`/`Menu`/`PropertyGroup` are the backbone of almost every add-on.")
    w(f"- `bpy.ops` is wide and shallow: **{sm['distinct_ops']} distinct operators** called, only "
      f"{sm['ops_used_by_2plus_groups']} in 2+ groups. `bpy.ops.object.mode_set` is the exception (Tier 1): "
      "Quartz needs a mode concept (Object/Edit/Pose) early.")
    w(f"- The implicit surface weighs as much as the imported one: {sm['context_member_names']} `context` members "
      f"and {sm['layout_member_names']} `UILayout` members (`layout.prop` alone has {sm['layout_prop_refs']} references). "
      "Even headless, the shim needs a 'recorder' `UILayout` (a no-op that records calls).")
    w(f"- The `bpy.app.translations.pgettext_*` family is in Tier 1: it is trivial (identity) and should ship on day one.")
    w(f"- `bmesh` is used directly by only {sm['addons_using_bmesh']} add-on(s) and `gpu`/`blf` by "
      f"{sm['addons_using_gpu']}; both can stay in Tier 3 / stubs at first.")
    w(f"- {sm['ui_class_refs']} symbols are references to native UI classes (`*_MT_*`, `*_PT_*`, `*_HT_*`), "
      "almost always for `append`/`remove` on menus. The shim must provide 'ghost' menus that accept extensions.")
    w(f"- Add-ons with <= 8 symbols outside the core (easy wins): {', '.join('`' + n + '`' for n in sm['addons_with_le8_non_core'])}. "
      f"{sm['templates_core_only']} templates use only the core.")
    w("")
    w("## 1. Scope and method")
    w("")
    w(f"- Source: `{result['scripts_root']}` (Blender 5.2.2 LTS, read-only).")
    w(f"- Units analysed: **{pop['addons']} add-ons** from `addons_core`, "
      f"**{pop['templates']} templates** from `templates_py` (each file is a group) and "
      f"**`bl_operators`** as a group of its own: {pop['groups']} groups in total, "
      f"{pop['files']} files, {fmt_int(pop['lines'])} lines; parse errors: {pop['parse_errors']}.")
    w("- Tracked roots: `bpy`, `mathutils`, `bmesh`, `bpy_extras`, `gpu`, `blf`, `idprop`, "
      "`aud`, `gpu_extras`, `addon_utils`. Import aliases are resolved "
      "(`from bpy.props import FloatProperty`, `import bmesh as bm`, `C = bpy.context`).")
    w("- Cut depth: `bpy.ops.<mod>.<op>` (4), `bpy.types.X`, `bpy.props.X`, `bpy.data.X`, "
      "`bpy.context.X`, `bpy.utils.X`, `bpy.app.X` (3; `bpy.app.handlers.X`, `bpy.app.translations.X`, "
      "`bpy.app.timers.X`, `bpy.utils.previews.X` go to 4), `mathutils.X` (2; submodules to 3), "
      "`bmesh.X` (2; `bmesh.ops/types/utils/geometry` to 3), `gpu.*`, `gpu_extras.*`, `bpy_extras.*` (3).")
    w("- `refs` = every occurrence of the symbol in the code (includes property annotations and class bases); "
      "`calls` = times the symbol itself is called (`FloatProperty(...)`, `bpy.ops.x.y(...)`).")
    w("- Known limitations: import aliases are flat per module (no scope); namespace aliases "
      "(`C = bpy.context`) are only accepted at module level; `from X import *` is not "
      "resolved; dynamic accesses (`getattr(bpy.ops, name)`) are only counted; the implicit surface "
      "(`context`, `event`, `UILayout`) is detected by a name heuristic. The numbers are therefore "
      "a reliable **lower bound** of real usage.")
    w("")

    w("## 2. Top 80 symbols by number of add-ons")
    w("")
    w(f"Columns: `add-ons` (of {pop['addons']}), `tpl` (templates, of {pop['templates']}), "
      "`ops` (bl_operators 0/1), `groups` (total), `refs`, `calls`, `core` (yes = belongs to the 'easy core' set).")
    w("")
    rows = []
    for i, (s, info) in enumerate(list(syms.items())[:80], 1):
        rows.append([i, f"`{s}`", info["addons"], info["templates"], info["bl_operators"], info["groups"],
                     info["refs"], info["calls"], "yes" if info["easy_core"] else ""])
    w(md_table(["#", "symbol", "add-ons", "tpl", "ops", "groups", "refs", "calls", "core"], rows))
    w("")

    w("## 3. Top 80 symbols by usage volume (refs) and calls")
    w("")
    by_refs = sorted(syms.items(), key=lambda kv: (-kv[1]["refs"], -kv[1]["calls"], kv[0]))[:80]
    rows = [[i, f"`{s}`", info["refs"], info["calls"], info["groups"], info["addons"],
             "yes" if info["easy_core"] else ""] for i, (s, info) in enumerate(by_refs, 1)]
    w(md_table(["#", "symbol", "refs", "calls", "groups", "add-ons", "core"], rows))
    w("")
    w("Top 30 by number of direct **calls**:")
    w("")
    by_calls = sorted(((s, i) for s, i in syms.items() if i["calls"]), key=lambda kv: (-kv[1]["calls"], kv[0]))[:30]
    rows = [[i, f"`{s}`", info["calls"], info["groups"]] for i, (s, info) in enumerate(by_calls, 1)]
    w(md_table(["#", "symbol", "calls", "groups"], rows))
    w("")

    w("## 4. Summary by API area")
    w("")
    area_syms: dict[str, set] = defaultdict(set)
    area_groups: dict[str, set] = defaultdict(set)
    area_refs: Counter = Counter()
    for s, info in syms.items():
        a = area_of(s)
        area_syms[a].add(s)
        area_groups[a].update(info["used_by"])
        area_refs[a] += info["refs"]
    kinds = {g["name"]: g["kind"] for g in groups}
    rows = []
    for a in sorted(area_syms, key=lambda a: (-len(area_groups[a]), -area_refs[a])):
        n_add = sum(1 for n in area_groups[a] if kinds[n] == "addon")
        rows.append([f"`{a}`", len(area_syms[a]), n_add, len(area_groups[a]), area_refs[a]])
    w(md_table(["area", "distinct symbols", "add-ons", "groups", "refs"], rows))
    w("")

    w("## 5. Blender base classes that are subclassed")
    w("")
    w("`effective` includes indirect inheritance through the add-on's own local classes "
      "(e.g. `class MyBase(bpy.types.Operator)` → `class X(MyBase)`).")
    w("")
    rows = []
    for b, info in result["base_classes"].items():
        top_m = ", ".join(f"{m}({n})" for m, n in list(info["methods"].items())[:6])
        rows.append([f"`{b}`", info["classes_effective"], info["classes_direct"], info["addons"],
                     info["templates"], info["bl_operators"], top_m])
    w(md_table(["base", "classes (effective)", "direct", "add-ons", "tpl", "ops", "most defined methods"], rows))
    w("")
    w("Most declared `bl_*` attributes per base (top 5 bases):")
    w("")
    for b, info in list(result["base_classes"].items())[:5]:
        if info["bl_attrs"]:
            attrs = ", ".join(f"`{a}`({n})" for a, n in list(info["bl_attrs"].items())[:10])
            w(f"- `{b}`: {attrs}")
    w("")

    w("## 6. Implicit surface (not imported, but required)")
    w("")
    w("Add-ons use much more API through the `context` parameter, `event` and `UILayout` objects "
      "than through `bpy.*` directly. Heuristic count:")
    w("")
    for key, title in (("context", "Members of `context` / `bpy.context`"),
                       ("layout", "Methods/attributes of `UILayout`"),
                       ("event", "Attributes of `Event`")):
        tab = result["implicit"][key]
        w(f"**{title}**: {len(tab)} distinct names; top 25:")
        w("")
        rows = [[f"`{a}`", d["refs"], d["addons"], d["groups"]] for a, d in list(tab.items())[:25]]
        w(md_table(["name", "refs", "add-ons", "groups"], rows))
        w("")
    ext = result["rna_extensions"]
    if ext:
        w("**RNA type extension** (`bpy.types.X.prop = Property(...)`): " + ", ".join(
            f"`{t}`({len(g)})" for t, g in list(ext.items())[:15]))
        w("")

    w("## 7. Footprint per add-on")
    w("")
    w("`distinct` = different tracked symbols; `outside core` = the ones not in the 'easy core' set "
      "(see section 10); `ops` = distinct `bpy.ops.*` operators called.")
    w("")
    rows = []
    for g in sorted([g for g in groups if g["kind"] != "template"], key=lambda g: g["footprint"]["distinct_symbols"]):
        f = g["footprint"]
        sample = ", ".join(f"`{s}`" for s in f["non_core"][:8]) + (" …" if len(f["non_core"]) > 8 else "")
        rows.append([f"`{g['name']}`", g["files"], g["lines"], f["distinct_symbols"], f["non_core_symbols"],
                     len(f["ops_calls"]), "yes" if f["uses_bmesh"] else "", "yes" if f["uses_gpu"] else "", sample])
    w(md_table(["group", "files", "lines", "distinct", "outside core", "ops", "bmesh", "gpu/blf", "outside core sample"], rows))
    w("")
    w("Templates (`templates_py`), one per row:")
    w("")
    rows = []
    for g in sorted([g for g in groups if g["kind"] == "template"], key=lambda g: g["footprint"]["non_core_symbols"]):
        f = g["footprint"]
        rows.append([f"`{g['name']}`", f["distinct_symbols"], f["non_core_symbols"],
                     ", ".join(f"`{s}`" for s in f["non_core"][:6]) + (" …" if len(f["non_core"]) > 6 else "")])
    w(md_table(["template", "distinct", "outside core", "outside core (sample)"], rows))
    w("")

    w("## 8. Easy wins: add-ons with a small surface (initial target)")
    w("")
    w("Sorted by number of symbols outside the core, then by `bpy.ops` operators and gpu/bmesh use. "
      "The smaller it is, the sooner the add-on can run in Quartz through the `bpy`-lite layer.")
    w("")

    def ease_key(g):
        f = g["footprint"]
        return (f["non_core_symbols"] + 2 * f["uses_gpu"] + f["uses_bmesh"], len(f["ops_calls"]), g["lines"])

    rows = []
    for i, g in enumerate(sorted(addons, key=ease_key), 1):
        f = g["footprint"]
        ctx_n = len(g["implicit"]["context"])
        lay_n = len(g["implicit"]["layout"])
        rows.append([i, f"`{g['name']}`", g["lines"], f["distinct_symbols"], f["non_core_symbols"],
                     len(f["ops_calls"]), ctx_n, lay_n,
                     ", ".join(f"`{s}`" for s in f["non_core"][:10]) + (" …" if len(f["non_core"]) > 10 else "")])
    w(md_table(["#", "add-on", "lines", "distinct", "outside core", "ops", "context.*", "layout.*", "what is missing (sample)"], rows))
    w("")
    tpl_easy = sorted([g for g in groups if g["kind"] == "template"], key=ease_key)
    w("Templates that already fit almost entirely in the core (<= 3 symbols outside the core): " + ", ".join(
        f"`{g['name'].split('/', 1)[1]}`" for g in tpl_easy if g["footprint"]["non_core_symbols"] <= 3) + ".")
    w("")

    w("## 9. Recommended priority tiers")
    w("")
    r = tiers["rules"]
    w(f"Criterion (packages = add-ons + `bl_operators` = {r['packages']}): **Tier 1** = used by >= "
      f"{r['tier1_min_packages']} packages; **Tier 2** = {r['tier2']}; **Tier 3** = {r['tier3']}; "
      "the rest is the long tail (implement on demand).")
    w("")
    for key, title in (("tier1", "Tier 1: needed by most"),
                       ("tier2", "Tier 2: common"),
                       ("tier3", "Tier 3: specific, but recurring")):
        lst = tiers[key]
        w(f"### {title} ({len(lst)} symbols)")
        w("")
        by_area: dict[str, list[str]] = defaultdict(list)
        for s in lst:
            by_area[area_of(s)].append(s)
        for a in sorted(by_area, key=lambda a: -len(by_area[a])):
            items = by_area[a]
            shown = ", ".join(
                f"`{s[len(a) + 1:]}`" if s.startswith(a + ".") else f"`{s}` (whole namespace)"
                for s in items[:40])
            more = f" … (+{len(items) - 40})" if len(items) > 40 else ""
            w(f"- **`{a}`** ({len(items)}): {shown}{more}")
        w("")
    w(f"Long tail: {len(tiers['tail'])} symbols used by a single group (full list in the JSON, key `tiers.tail`).")
    w("")
    w("### Recommended reading of the tiers for Quartz")
    w("")
    w("Manual curation on top of the numbers above: it groups whole families (e.g. all of `bpy.props`) and promotes "
      "cheap or structural items even when the raw count leaves them in a lower tier.")
    w("")
    w("- **Tier 1 (current milestone)**: all of `bpy.props.*` (including `*VectorProperty`), `bpy.types.Operator/Panel/"
      "Menu/PropertyGroup/AddonPreferences/UIList`, `bpy.utils.register_class/unregister_class/"
      "register_classes_factory`, `mathutils.Vector/Matrix/Quaternion/Euler`, `bpy.data.objects/meshes/materials/"
      "collections/scenes/cameras/lights`, `bpy.context.scene/object/active_object/view_layer/preferences/"
      "window_manager`, `bpy.app.version`, `bpy.app.handlers.persistent`, `pgettext_*` (identity), "
      "`bpy.ops.object.mode_set`. Plus the implicit surface: `Operator.report`, `bl_idname/bl_label/bl_options`, "
      "`execute/invoke/poll/draw`, `UILayout.prop/label/operator/row/column/separator/box/split` (recorder).")
    w("- **Tier 2 (next milestone)**: `bpy_extras.io_utils.ImportHelper/ExportHelper/axis_conversion/"
      "orientation_helper`, `OperatorFileListElement`, `FileHandler`, menus `TOPBAR_MT_file_import/export` "
      "(extensible), `bpy.path.*`, `bpy.data.images/actions/armatures/texts`, `bpy.utils.user_resource/"
      "escape_identifier`, `addon_utils.modules/module_bl_info`, `bmesh.new`, basic animation "
      "(`Action`, `FCurve`, `Keyframe`, `ActionSlot`, `ActionChannelbag`).")
    w("- **Tier 3 (on demand)**: `gpu`/`gpu_extras`/`blf` (stubs that do not draw), `bmesh.from_edit_mesh/"
      "update_edit_mesh`, `bpy.utils.previews`, `bpy.msgbus`, `mathutils.kdtree/geometry`, `idprop.types`, "
      "Gizmos/WorkSpaceTool/AssetShelf, nodes (`Node`, `NodeTree`, `NodeSocket`).")
    w("- **Out of initial scope**: `RenderEngine`/`HydraRenderEngine` (no renderer), XR, `bl_pkg` (Blender's own "
      "extension manager, uses a private `addon_utils` API), operators of specific editors.")
    w("")

    w("## 10. The 'easy core' set used in this analysis")
    w("")
    w("Curated definition (what the first Quartz milestone, data model + registration + props + "
      "math + IO helpers, should offer naturally):")
    w("")
    w("- Whole prefixes: " + ", ".join(f"`{p}*`" for p in EASY_CORE_PREFIXES))
    w("- Exact symbols (" + str(len(EASY_CORE_EXACT)) + "): " + ", ".join(f"`{s}`" for s in sorted(EASY_CORE_EXACT)))
    w("")

    w("## 11. Other imported modules")
    w("")
    om = result["other_blender_modules"]
    w("Blender's own Python modules (outside the main roots): " + (", ".join(
        f"`{m}`({len(g)})" for m, g in om.items()) or "none") + ".")
    w("")
    tp = result["third_party_imports"]
    w("Non-stdlib, non-Blender modules (external, or internal to the add-on but not detected as local): " + (", ".join(
        f"`{m}`({len(g)})" for m, g in list(tp.items())[:30]) or "none") + ".")
    w("")
    dyn = Counter()
    for g in groups:
        dyn.update(g["dynamic_getattr_on_api"])
    if dyn:
        w("Dynamic accesses detected: " + ", ".join(f"`{k}`×{v}" for k, v in dyn.most_common(10)) + ".")
        w("")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Static (ast-based) scanner that measures which Blender Python API symbols real add-ons use.")
    ap.add_argument("--scripts", default=DEFAULT_SCRIPTS, help="Blender scripts directory (read-only)")
    ap.add_argument("--json", default=str(DEFAULT_JSON), help="output JSON path")
    ap.add_argument("--md", default=str(DEFAULT_MD), help="output Markdown report path")
    args = ap.parse_args(argv)

    scripts = Path(args.scripts)
    if not (scripts / "addons_core").is_dir():
        print(f"error: {scripts} does not look like a Blender scripts directory", file=sys.stderr)
        return 2
    result = scan(scripts)
    md = render_markdown(result)
    out_json = Path(args.json)
    out_md = Path(args.md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    out_md.write_text(md, encoding="utf-8")
    pop = result["population"]
    print(f"scanned {pop['groups']} groups, {pop['files']} files, {pop['lines']} lines, "
          f"{len(result['symbols'])} distinct symbols in {result['scan_seconds']}s")
    print(f"json: {out_json}")
    print(f"md:   {out_md}")
    print(json.dumps(result["summary"], indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
