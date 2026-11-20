import inspect
import json
import math
import os
import re
import sys
import time
import traceback

import bpy

OUT_PATH = os.environ.get(
    "QUARTZ_DUMP_OUT",
    "D:/Claude/reverseEngineering/Quartz/data/blender_api_dump.json",
)
TMP_DIR = "D:/Claude/reverseEngineering/Quartz/tmp"

ID_TYPES = [
    "ID", "Object", "Mesh", "Scene", "Collection", "Material", "Camera", "Light",
    "PointLight", "SunLight", "SpotLight", "AreaLight", "World", "Image", "Text",
    "Action", "Armature", "Curve", "TextCurve", "SurfaceCurve", "NodeTree", "Library",
]
SUB_STRUCTS = [
    "MeshVertex", "MeshEdge", "MeshPolygon", "MeshLoop", "MeshLoopTriangle", "MeshUVLoopLayer",
    "Attribute", "AttributeGroupMesh", "MaterialSlot", "ViewLayer", "LayerCollection",
    "RenderSettings", "Modifier", "AnimData", "FCurve", "Keyframe", "Bone", "EditBone",
    "PoseBone", "Spline", "SplinePoint", "BezierSplinePoint", "CameraDOFSettings",
    "ObjectConstraints", "Constraint", "ToolSettings", "UnitSettings", "View3DCursor",
    "BlendData", "Context", "WindowManager", "Preferences", "Addon", "Event", "KeyMap",
    "KeyMapItem", "OperatorProperties", "Depsgraph", "DepsgraphUpdate", "ActionSlot",
    "ActionLayer", "ActionStrip", "ActionChannelbag",
]
BASE_CLASSES = [
    "bpy_struct", "Operator", "Macro", "Panel", "Menu", "Header", "PropertyGroup",
    "AddonPreferences", "UIList", "KeyingSetInfo", "RenderEngine", "Node", "NodeSocket",
    "NodeTree", "Gizmo", "GizmoGroup", "WorkSpaceTool", "FileHandler", "AssetShelf",
]
OPS_DETAIL_PREFIXES = ("mesh.primitive_", "object.", "transform.")



def _clean(value, depth=0):
    if depth > 40:
        return repr(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if isinstance(value, (set, frozenset)):
        return sorted(_clean(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return {str(k): _clean(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v, depth + 1) for v in value]
    if isinstance(value, bpy.types.ID):
        return {"__id__": type(value).__name__, "name": value.name}
    if isinstance(value, bpy.types.bpy_struct):
        return {"__struct__": type(value).__name__}
    try:
        return [_clean(v, depth + 1) for v in value]
    except TypeError:
        return repr(value)


def _err(ex):
    return "{}: {}".format(type(ex).__name__, ex)



PROP_FLAGS = (
    "is_readonly", "is_never_none", "is_animatable", "is_hidden", "is_skip_save",
    "is_library_editable", "is_registered", "is_registered_optional",
    "is_required", "is_output", "is_argument_optional", "is_enum_flag", "is_path_output",
)


def rna_prop_info(prop, detail=True):
    info = {"type": prop.type}
    if not detail:
        return info
    info["subtype"] = getattr(prop, "subtype", None)
    unit = getattr(prop, "unit", "NONE")
    if unit and unit != "NONE":
        info["unit"] = unit
    flags = [f for f in PROP_FLAGS if getattr(prop, f, False)]
    if flags:
        info["flags"] = flags
    ptype = prop.type
    try:
        if ptype in {"BOOLEAN", "INT", "FLOAT"}:
            alen = getattr(prop, "array_length", 0)
            if alen:
                info["array_length"] = alen
                dims = [d for d in getattr(prop, "array_dimensions", ()) if d]
                if len(dims) > 1:
                    info["array_dimensions"] = list(dims)
                info["default"] = _clean(list(prop.default_array))
            else:
                info["default"] = _clean(prop.default)
            if ptype in {"INT", "FLOAT"}:
                info["min"] = _clean(prop.hard_min)
                info["max"] = _clean(prop.hard_max)
                info["soft_min"] = _clean(prop.soft_min)
                info["soft_max"] = _clean(prop.soft_max)
                info["step"] = _clean(prop.step)
            if ptype == "FLOAT":
                info["precision"] = prop.precision
        elif ptype == "STRING":
            info["default"] = prop.default
            if prop.length_max:
                info["length_max"] = prop.length_max
        elif ptype == "ENUM":
            items = [it.identifier for it in prop.enum_items]
            info["items"] = items
            if prop.is_enum_flag:
                info["default"] = sorted(prop.default_flag)
            else:
                info["default"] = prop.default
        elif ptype in {"POINTER", "COLLECTION"}:
            ft = prop.fixed_type
            info["fixed_type"] = ft.identifier if ft else None
            if ptype == "COLLECTION":
                srna = getattr(prop, "srna", None)
                if srna is not None:
                    info["collection_api"] = {
                        "struct": srna.identifier,
                        "functions": {f.identifier: rna_func_info(f) for f in srna.functions},
                        "properties": sorted(p.identifier for p in srna.properties
                                             if p.identifier != "rna_type"),
                    }
    except Exception as ex:
        info["introspection_error"] = _err(ex)
    return info


def rna_func_info(func):
    params = []
    for p in func.parameters:
        entry = {"name": p.identifier, "type": p.type}
        if p.type in {"POINTER", "COLLECTION"} and p.fixed_type:
            entry["fixed_type"] = p.fixed_type.identifier
        if p.type == "ENUM":
            entry["items"] = [it.identifier for it in p.enum_items]
        if getattr(p, "is_output", False):
            entry["output"] = True
        if getattr(p, "is_required", False):
            entry["required"] = True
        params.append(entry)
    info = {"params": params}
    for flag in ("use_self", "use_self_type", "is_registered", "is_registered_optional"):
        if getattr(func, flag, False):
            info[flag] = True
    return info


def rna_struct_info(name, detail=True):
    cls = getattr(bpy.types, name, None)
    if cls is None:
        return {"missing": True}
    try:
        srna = cls.bl_rna
    except Exception as ex:
        return {"error": _err(ex)}
    base = srna.base
    base_props = set(base.properties.keys()) if base else set()
    base_funcs = set(base.functions.keys()) if base else set()
    own_props = {}
    for p in srna.properties:
        if p.identifier == "rna_type" or p.identifier in base_props:
            continue
        own_props[p.identifier] = rna_prop_info(p, detail)
    own_funcs = {}
    for f in srna.functions:
        if f.identifier in base_funcs:
            continue
        own_funcs[f.identifier] = rna_func_info(f)
    rna_names = set(srna.properties.keys()) | set(srna.functions.keys())
    py_only = sorted(
        a for a in cls.__dict__.keys()
        if not a.startswith("_") and a not in rna_names and a not in {"bl_rna"}
    )
    return {
        "base": base.identifier if base else None,
        "properties": own_props,
        "functions": own_funcs,
        "python_members": py_only,
    }


def base_class_info(name):
    cls = getattr(bpy.types, name, None)
    if cls is None:
        return {"missing": True}
    if "bl_rna" not in dir(cls):
        return {
            "no_bl_rna": True,
            "dir": sorted(a for a in dir(cls) if not a.startswith("__")),
            "mro": [c.__name__ for c in cls.__mro__],
            "metaclass": type(cls).__name__,
        }
    info = rna_struct_info(name, detail=True)
    srna = cls.bl_rna
    registered_props = [p.identifier for p in srna.properties if p.is_registered]
    optional_props = [p.identifier for p in srna.properties if p.is_registered_optional]
    callbacks = {
        f.identifier: {
            "optional": bool(f.is_registered_optional),
            "classmethod": not bool(f.use_self),
            "params": [p.identifier for p in f.parameters],
        }
        for f in srna.functions if f.is_registered or f.is_registered_optional
    }
    info["registration"] = {
        "bl_props_required": [p for p in registered_props if p not in optional_props],
        "bl_props_optional": optional_props,
        "callbacks": callbacks,
    }
    info["dir"] = sorted(a for a in dir(cls) if not a.startswith("__"))
    info["mro"] = [c.__name__ for c in cls.__mro__]
    info["metaclass"] = type(cls).__name__
    return info



SIG_RE = re.compile(r"\.\.\s*function::\s*(\w+)\((.*?)\)\s*$", re.M | re.S)


def props_info():
    out = {}
    for name in sorted(dir(bpy.props)):
        if name.startswith("_"):
            continue
        fn = getattr(bpy.props, name)
        if not callable(fn):
            continue
        entry = {"kwargs": None, "signature_source": None}
        try:
            sig = inspect.signature(fn)
            entry["kwargs"] = [p for p in sig.parameters]
            entry["signature_source"] = "inspect"
        except (TypeError, ValueError):
            doc = fn.__doc__ or ""
            m = SIG_RE.search(doc)
            if m:
                raw = m.group(2)
                parts, depth, cur = [], 0, ""
                for ch in raw:
                    if ch in "([{":
                        depth += 1
                    elif ch in ")]}":
                        depth -= 1
                    if ch == "," and depth == 0:
                        parts.append(cur)
                        cur = ""
                    else:
                        cur += ch
                if cur.strip():
                    parts.append(cur)
                kw = []
                defaults = {}
                for part in parts:
                    part = " ".join(part.split())
                    if not part or part == "*":
                        continue
                    key, _, default = part.partition("=")
                    kw.append(key.strip())
                    if default:
                        defaults[key.strip()] = default.strip()
                entry["kwargs"] = kw
                entry["defaults"] = defaults
                entry["signature_source"] = "docstring"
        out[name] = entry
    try:
        d = bpy.props.IntProperty(name="x", default=3)
        out["__deferred__"] = {
            "type": type(d).__name__,
            "attrs": sorted(a for a in dir(d) if not a.startswith("__")),
            "function": getattr(getattr(d, "function", None), "__name__", None),
            "keywords": _clean(getattr(d, "keywords", None)),
        }
    except Exception as ex:
        out["__deferred__"] = {"error": _err(ex)}
    return out



def app_info():
    app = bpy.app
    out = {"attributes": {}}
    for name in sorted(dir(app)):
        if name.startswith("_"):
            continue
        try:
            v = getattr(app, name)
        except Exception as ex:
            out["attributes"][name] = {"error": _err(ex)}
            continue
        if isinstance(v, (bool, int, float, str, tuple)) or v is None:
            out["attributes"][name] = {"type": type(v).__name__, "value": _clean(v)}
        else:
            out["attributes"][name] = {"type": type(v).__name__}
    h = app.handlers
    out["handlers"] = {
        n: type(getattr(h, n)).__name__
        for n in dir(h) if not n.startswith("_")
    }
    out["handler_lists"] = sorted(
        n for n in dir(h) if not n.startswith("_") and isinstance(getattr(h, n), list)
    )
    out["timers"] = sorted(n for n in dir(app.timers) if not n.startswith("_"))
    out["translations"] = sorted(n for n in dir(app.translations) if not n.startswith("_"))
    out["icons"] = sorted(n for n in dir(getattr(app, "icons", object())) if not n.startswith("_"))
    return out


def module_callables(mod):
    out = {}
    for name in sorted(dir(mod)):
        if name.startswith("_"):
            continue
        v = getattr(mod, name)
        kind = type(v).__name__
        entry = {"kind": kind}
        if callable(v) and not isinstance(v, type):
            try:
                sig = inspect.signature(v)
                entry["params"] = [
                    ("*" if p.kind == p.VAR_POSITIONAL else "**" if p.kind == p.VAR_KEYWORD else "")
                    + p.name + ("=" if p.default is not p.empty else "")
                    for p in sig.parameters.values()
                ]
            except (TypeError, ValueError):
                pass
        out[name] = entry
    return out


def context_info():
    ctx = bpy.context
    out = {}
    for name in sorted(dir(ctx)):
        if name.startswith("_") or name in {"bl_rna", "rna_type"}:
            continue
        try:
            v = getattr(ctx, name)
        except Exception as ex:
            out[name] = {"error": _err(ex)}
            continue
        if callable(v) and not isinstance(v, bpy.types.bpy_struct):
            out[name] = {"kind": "method"}
            continue
        entry = {"value_type": type(v).__name__, "is_none": v is None}
        if isinstance(v, bpy.types.ID):
            entry["name"] = v.name
        elif isinstance(v, list):
            entry["len"] = len(v)
            if v:
                entry["item_type"] = type(v[0]).__name__
        elif isinstance(v, (str, int, float, bool)):
            entry["value"] = _clean(v)
        out[name] = entry
    return out


def data_info():
    data = bpy.data
    srna = data.bl_rna
    collections = {}
    for p in srna.properties:
        if p.type != "COLLECTION":
            continue
        coll = getattr(data, p.identifier)
        entry = {
            "fixed_type": p.fixed_type.identifier if p.fixed_type else None,
            "len_factory": len(coll),
            "items_factory": [i.name for i in coll][:20],
        }
        csrna = getattr(p, "srna", None)
        if csrna is not None:
            entry["struct"] = csrna.identifier
            entry["functions"] = {f.identifier: rna_func_info(f) for f in csrna.functions}
        entry["python_methods"] = sorted(
            a for a in dir(coll) if not a.startswith("_") and callable(getattr(coll, a, None))
        )
        collections[p.identifier] = entry
    other_props = {p.identifier: rna_prop_info(p) for p in srna.properties
                   if p.type != "COLLECTION" and p.identifier != "rna_type"}
    funcs = {f.identifier: rna_func_info(f) for f in srna.functions}
    py_methods = sorted(
        a for a in dir(data)
        if not a.startswith("_") and a not in collections and a not in other_props
        and a not in funcs
    )
    return {
        "collections": collections,
        "properties": other_props,
        "functions": funcs,
        "python_members": py_methods,
    }


def ops_info():
    out = {"submodules": {}, "counts": {}}
    detail = {}
    poll_bg = {}
    for sub in sorted(dir(bpy.ops)):
        if sub.startswith("_"):
            continue
        submod = getattr(bpy.ops, sub)
        names = sorted(dir(submod))
        ops = {}
        for opname in names:
            full = "{}.{}".format(sub, opname)
            try:
                op = getattr(submod, opname)
                rna = op.get_rna_type()
                is_detail = full.startswith(OPS_DETAIL_PREFIXES)
                props = {}
                for p in rna.properties:
                    if p.identifier == "rna_type":
                        continue
                    props[p.identifier] = rna_prop_info(p, detail=is_detail)
                entry = {"props": props}
                try:
                    entry["bl_idname"] = op.idname()
                except Exception:
                    pass
                bl_opts = getattr(op, "bl_options", None)
                if bl_opts is not None:
                    entry["bl_options"] = _clean(bl_opts)
                ops[opname] = entry
                if is_detail:
                    detail[full] = True
                    try:
                        poll_bg[full] = bool(op.poll())
                    except Exception as ex:
                        poll_bg[full] = _err(ex)
            except Exception as ex:
                ops[opname] = {"error": _err(ex)}
        out["submodules"][sub] = ops
        out["counts"][sub] = len(ops)
    out["total"] = sum(out["counts"].values())
    out["detail_ops"] = sorted(detail)
    out["poll_in_background"] = poll_bg
    out["groups"] = {
        "mesh.primitive_*_add": sorted(
            k for k in out["submodules"].get("mesh", {}) if k.startswith("primitive_") and k.endswith("_add")
        ),
        "object.*": sorted(out["submodules"].get("object", {})),
        "transform.*": sorted(out["submodules"].get("transform", {})),
    }
    return out


def extras_info():
    out = {}
    try:
        import mathutils
        mu = {}
        for cname in ("Vector", "Matrix", "Quaternion", "Euler", "Color"):
            cls = getattr(mathutils, cname)
            mu[cname] = sorted(a for a in dir(cls) if not a.startswith("__"))
        mu["__module__"] = sorted(a for a in dir(mathutils) if not a.startswith("_"))
        for sub in ("geometry", "kdtree", "bvhtree", "noise", "interpolate"):
            m = getattr(mathutils, sub, None)
            if m is not None:
                mu[sub] = sorted(a for a in dir(m) if not a.startswith("_"))
        out["mathutils"] = mu
    except Exception as ex:
        out["mathutils"] = {"error": _err(ex)}
    try:
        import bmesh
        bm = {"__module__": sorted(a for a in dir(bmesh) if not a.startswith("_"))}
        bm["types"] = {
            n: sorted(a for a in dir(getattr(bmesh.types, n)) if not a.startswith("__"))
            for n in dir(bmesh.types) if n.startswith("BM")
        }
        bm["ops"] = sorted(a for a in dir(bmesh.ops) if not a.startswith("_"))
        bm["utils"] = sorted(a for a in dir(bmesh.utils) if not a.startswith("_"))
        bm["geometry"] = sorted(a for a in dir(bmesh.geometry) if not a.startswith("_"))
        out["bmesh"] = bm
    except Exception as ex:
        out["bmesh"] = {"error": _err(ex)}
    for modname in ("gpu", "blf", "bpy_extras", "bpy.path", "idprop", "bl_math", "aud", "imbuf"):
        try:
            mod = __import__(modname, fromlist=["_"])
            out[modname] = sorted(a for a in dir(mod) if not a.startswith("_"))
        except Exception as ex:
            out[modname] = {"error": _err(ex)}
    try:
        out["bpy.msgbus"] = sorted(a for a in dir(bpy.msgbus) if not a.startswith("_"))
    except Exception as ex:
        out["bpy.msgbus"] = {"error": _err(ex)}
    out["UILayout_functions"] = {
        f.identifier: [p.identifier for p in f.parameters]
        for f in bpy.types.UILayout.bl_rna.functions
    }
    return out


def factory_scene_info():
    out = {
        "scenes": [s.name for s in bpy.data.scenes],
        "objects": [{"name": o.name, "type": o.type, "data": o.data.name if o.data else None,
                     "location": _clean(list(o.location)),
                     "users_collection": [c.name for c in o.users_collection]}
                    for o in bpy.data.objects],
        "collections": [c.name for c in bpy.data.collections],
        "materials": [m.name for m in bpy.data.materials],
        "worlds": [w.name for w in bpy.data.worlds],
        "meshes": [{"name": m.name, "verts": len(m.vertices), "edges": len(m.edges),
                    "faces": len(m.polygons), "loops": len(m.loops),
                    "attributes": [(a.name, a.domain, a.data_type) for a in m.attributes]}
                   for m in bpy.data.meshes],
        "scene_collection_children": [c.name for c in bpy.context.scene.collection.children],
        "frame": [bpy.context.scene.frame_start, bpy.context.scene.frame_end,
                  bpy.context.scene.frame_current],
        "render_engine": bpy.context.scene.render.engine,
        "unit_system": bpy.context.scene.unit_settings.system,
    }
    return out



PROBES = {}


def probe(fn):
    PROBES[fn.__name__] = fn
    return fn


def _try_register(cls):
    try:
        bpy.utils.register_class(cls)
        return "ok"
    except Exception as ex:
        return _err(ex)


def _safe_unregister(cls):
    try:
        bpy.utils.unregister_class(cls)
        return "ok"
    except Exception as ex:
        return _err(ex)


@probe
def operator_basic():
    calls = []

    class QUARTZPROBE_OT_hello(bpy.types.Operator):
        bl_idname = "quartz_probe.hello"
        bl_label = "Hello"
        bl_options = {"REGISTER", "UNDO"}
        count: bpy.props.IntProperty(default=2, min=0, max=10)
        mode: bpy.props.EnumProperty(items=[("A", "A", ""), ("B", "B", "")], default="B")

        @classmethod
        def poll(cls, context):
            calls.append("poll")
            return True

        def invoke(self, context, event):
            calls.append(("invoke", event.type if event else None))
            return self.execute(context)

        def execute(self, context):
            calls.append(("execute", self.as_keywords(), sorted(self.properties.keys()),
                          self.properties.is_property_set("count")))
            self.report({"INFO"}, "probe report")
            return {"FINISHED"}

    res = {"register": _try_register(QUARTZPROBE_OT_hello)}
    res["is_registered"] = QUARTZPROBE_OT_hello.is_registered
    res["has_bl_rna"] = "bl_rna" in QUARTZPROBE_OT_hello.__dict__
    res["in_bpy_types_as"] = [n for n in ("QUARTZPROBE_OT_hello", "QUARTZ_PROBE_OT_hello")
                              if hasattr(bpy.types, n)]
    res["op_idname"] = bpy.ops.quartz_probe.hello.idname()
    res["call_default"] = _clean(bpy.ops.quartz_probe.hello())
    res["call_kwargs"] = _clean(bpy.ops.quartz_probe.hello(count=5, mode="A"))
    res["call_exec_default"] = _clean(bpy.ops.quartz_probe.hello("EXEC_DEFAULT"))
    try:
        res["call_invoke_default"] = _clean(bpy.ops.quartz_probe.hello("INVOKE_DEFAULT"))
    except Exception as ex:
        res["call_invoke_default"] = _err(ex)
    try:
        res["call_undo_positional"] = _clean(bpy.ops.quartz_probe.hello("EXEC_DEFAULT", True))
    except Exception as ex:
        res["call_undo_positional"] = _err(ex)
    for label, kwargs in (("bad_kwarg", {"nope": 1}), ("out_of_range", {"count": 99}),
                          ("bad_enum", {"mode": "Z"}), ("bad_type", {"count": "x"})):
        try:
            r = bpy.ops.quartz_probe.hello(**kwargs)
            res["call_" + label] = _clean(r)
        except Exception as ex:
            res["call_" + label] = _err(ex)
    try:
        res["call_dict_override_positional"] = _clean(bpy.ops.quartz_probe.hello({"scene": bpy.context.scene}))
    except Exception as ex:
        res["call_dict_override_positional"] = _err(ex)
    res["calls"] = _clean(calls)
    res["unregister"] = _safe_unregister(QUARTZPROBE_OT_hello)
    res["is_registered_after"] = QUARTZPROBE_OT_hello.is_registered
    try:
        res["call_after_unregister"] = _clean(bpy.ops.quartz_probe.hello())
    except Exception as ex:
        res["call_after_unregister"] = _err(ex)
    res["unregister_twice"] = _safe_unregister(QUARTZPROBE_OT_hello)
    return res


@probe
def operator_poll_false_and_returns():
    class QUARTZPROBE_OT_nopoll(bpy.types.Operator):
        bl_idname = "quartz_probe.nopoll"
        bl_label = "No poll"

        @classmethod
        def poll(cls, context):
            cls.poll_message_set("probe poll message")
            return False

        def execute(self, context):
            return {"FINISHED"}

    class QUARTZPROBE_OT_badret(bpy.types.Operator):
        bl_idname = "quartz_probe.badret"
        bl_label = "Bad return"

        def execute(self, context):
            return {"DONE"}

    class QUARTZPROBE_OT_noneret(bpy.types.Operator):
        bl_idname = "quartz_probe.noneret"
        bl_label = "None return"

        def execute(self, context):
            return None

    class QUARTZPROBE_OT_cancel(bpy.types.Operator):
        bl_idname = "quartz_probe.cancel"
        bl_label = "Cancel"

        def execute(self, context):
            return {"CANCELLED"}

    class QUARTZPROBE_OT_raises(bpy.types.Operator):
        bl_idname = "quartz_probe.raises"
        bl_label = "Raises"

        def execute(self, context):
            raise ValueError("probe failure")

    class QUARTZPROBE_OT_error_report(bpy.types.Operator):
        bl_idname = "quartz_probe.error_report"
        bl_label = "Error report"

        def execute(self, context):
            self.report({"ERROR"}, "probe error report")
            return {"CANCELLED"}

    res = {}
    classes = (QUARTZPROBE_OT_nopoll, QUARTZPROBE_OT_badret, QUARTZPROBE_OT_noneret,
               QUARTZPROBE_OT_cancel, QUARTZPROBE_OT_raises, QUARTZPROBE_OT_error_report)
    for c in classes:
        res["register_" + c.__name__] = _try_register(c)
    for name in ("nopoll", "badret", "noneret", "cancel", "raises", "error_report"):
        op = getattr(bpy.ops.quartz_probe, name)
        try:
            res["call_" + name] = _clean(op())
        except Exception as ex:
            res["call_" + name] = _err(ex)
    try:
        res["poll_nopoll"] = bpy.ops.quartz_probe.nopoll.poll()
    except Exception as ex:
        res["poll_nopoll"] = _err(ex)
    for c in classes:
        _safe_unregister(c)
    return res


@probe
def registration_errors():
    res = {}

    def attempt(label, cls):
        r = _try_register(cls)
        res[label] = r
        if r == "ok":
            _safe_unregister(cls)

    for label, idname in (("no_dot", "quartzprobe"), ("upper", "Quartz.Probe"),
                          ("two_dots", "quartz.probe.x"), ("ot_form", "QUARTZ_OT_probe"),
                          ("long", "quartz." + "x" * 80), ("leading_digit", "1quartz.probe")):
        cls = type("QUARTZPROBE_OT_v_" + label, (bpy.types.Operator,),
                   {"bl_idname": idname, "bl_label": "v", "execute": lambda self, c: {"FINISHED"}})
        attempt("operator_idname_" + label, cls)

    cls = type("QUARTZPROBE_OT_nolabel", (bpy.types.Operator,),
               {"bl_idname": "quartz_probe.nolabel", "execute": lambda self, c: {"FINISHED"}})
    attempt("operator_without_bl_label", cls)
    cls = type("QUARTZPROBE_OT_noidname", (bpy.types.Operator,),
               {"bl_label": "x", "execute": lambda self, c: {"FINISHED"}})
    attempt("operator_without_bl_idname", cls)

    def panel(name, **attrs):
        d = {"bl_label": "P", "draw": lambda self, c: None}
        d.update(attrs)
        return type(name, (bpy.types.Panel,), d)

    attempt("panel_ok", panel("QUARTZPROBE_PT_ok", bl_space_type="VIEW_3D", bl_region_type="UI",
                              bl_category="Quartz"))
    attempt("panel_bad_class_name", panel("QuartzProbePanel", bl_space_type="VIEW_3D",
                                          bl_region_type="UI"))
    attempt("panel_bad_class_name_with_idname", panel("QuartzProbePanel2", bl_idname="QUARTZPROBE_PT_x",
                                                      bl_space_type="VIEW_3D", bl_region_type="UI"))
    attempt("panel_missing_space", panel("QUARTZPROBE_PT_nospace", bl_region_type="UI"))
    attempt("panel_bad_space_enum", panel("QUARTZPROBE_PT_badspace", bl_space_type="NOPE",
                                          bl_region_type="UI"))
    attempt("panel_parent_missing", panel("QUARTZPROBE_PT_child", bl_space_type="VIEW_3D",
                                          bl_region_type="UI", bl_parent_id="QUARTZPROBE_PT_none"))
    attempt("menu_ok", type("QUARTZPROBE_MT_ok", (bpy.types.Menu,), {"bl_label": "M",
                                                                     "draw": lambda s, c: None}))
    attempt("menu_bad_name", type("QuartzProbeMenu", (bpy.types.Menu,), {"bl_label": "M",
                                                                         "draw": lambda s, c: None}))
    attempt("uilist_ok", type("QUARTZPROBE_UL_ok", (bpy.types.UIList,), {}))
    attempt("header_ok", type("QUARTZPROBE_HT_ok", (bpy.types.Header,),
                              {"bl_space_type": "VIEW_3D", "draw": lambda s, c: None}))
    cls = type("QUARTZPROBE_OT_twice", (bpy.types.Operator,),
               {"bl_idname": "quartz_probe.twice", "bl_label": "t",
                "execute": lambda self, c: {"FINISHED"}})
    res["register_first"] = _try_register(cls)
    res["register_second_same_class"] = _try_register(cls)
    cls2 = type("QUARTZPROBE_OT_twice", (bpy.types.Operator,),
                {"bl_idname": "quartz_probe.twice", "bl_label": "t2",
                 "execute": lambda self, c: {"FINISHED"}})
    res["register_new_class_same_idname"] = _try_register(cls2)
    res["unregister_new"] = _safe_unregister(cls2)
    res["unregister_first"] = _safe_unregister(cls)
    cls3 = type("QUARTZPROBE_OT_never", (bpy.types.Operator,),
                {"bl_idname": "quartz_probe.never", "bl_label": "n",
                 "execute": lambda self, c: {"FINISHED"}})
    res["unregister_never_registered"] = _safe_unregister(cls3)
    res["register_plain_class"] = _try_register(type("NotAStruct", (), {}))
    return res


@probe
def required_bl_attrs():
    def noop_draw(self, context):
        pass

    def noop_exec(self, context):
        return {"FINISHED"}

    def noop_item(self, context, layout, data, item, icon, active_data, active_propname):
        pass

    specs = {
        "Operator": ("QUARTZPROBE_OT_req", {"bl_idname": "quartz_probe.req", "bl_label": "R",
                                            "execute": noop_exec}),
        "Panel": ("QUARTZPROBE_PT_req", {"bl_idname": "QUARTZPROBE_PT_req", "bl_label": "R",
                                         "bl_space_type": "VIEW_3D", "bl_region_type": "UI",
                                         "draw": noop_draw}),
        "Menu": ("QUARTZPROBE_MT_req", {"bl_idname": "QUARTZPROBE_MT_req", "bl_label": "R",
                                        "draw": noop_draw}),
        "Header": ("QUARTZPROBE_HT_req", {"bl_idname": "QUARTZPROBE_HT_req", "bl_space_type": "VIEW_3D",
                                          "bl_region_type": "HEADER", "draw": noop_draw}),
        "UIList": ("QUARTZPROBE_UL_req", {"bl_idname": "QUARTZPROBE_UL_req", "draw_item": noop_item}),
        "AddonPreferences": ("QuartzProbeReqPrefs", {"bl_idname": "quartz_probe_req"}),
        "PropertyGroup": ("QuartzProbeReqGroup", {}),
    }
    res = {}
    for base_name, (cls_name, attrs) in specs.items():
        base = getattr(bpy.types, base_name)
        entry = {"full": None, "without": {}}
        cls = type(cls_name, (base,), dict(attrs))
        entry["full"] = _try_register(cls)
        if entry["full"] == "ok":
            entry["registered_name_in_bpy_types"] = [
                n for n in (cls_name, attrs.get("bl_idname", "")) if n and hasattr(bpy.types, n)]
            _safe_unregister(cls)
        for key in attrs:
            reduced = {k: v for k, v in attrs.items() if k != key}
            cls = type(cls_name, (base,), reduced)
            r = _try_register(cls)
            entry["without"][key] = r
            if r == "ok":
                _safe_unregister(cls)
        res[base_name] = entry
    return res


@probe
def idprop_storage():
    res = {}
    ob = bpy.data.objects.get("Cube")
    bpy.types.Object.quartz_probe_val = bpy.props.IntProperty(default=1)
    res["default_read"] = ob.quartz_probe_val
    ob.quartz_probe_val = 5
    res["keys_after_rna_set"] = _clean(ob.keys())
    res["contains_after_rna_set"] = "quartz_probe_val" in ob
    try:
        res["getitem_after_rna_set"] = _clean(ob["quartz_probe_val"])
    except Exception as ex:
        res["getitem_after_rna_set"] = _err(ex)
    ob["quartz_custom"] = 3.5
    ob["quartz_custom_list"] = [1, 2, 3]
    ob["quartz_custom_dict"] = {"a": 1, "b": "x"}
    res["keys_after_custom"] = _clean(ob.keys())
    res["custom_list_type"] = type(ob["quartz_custom_list"]).__name__
    res["custom_dict_type"] = type(ob["quartz_custom_dict"]).__name__
    res["custom_dict_to_dict"] = _clean(ob["quartz_custom_dict"].to_dict())
    try:
        res["custom_as_attr"] = repr(getattr(ob, "quartz_custom", "<missing>"))
    except Exception as ex:
        res["custom_as_attr"] = _err(ex)
    res["is_property_set_rna"] = ob.is_property_set("quartz_probe_val")
    ob.property_unset("quartz_probe_val")
    res["after_property_unset"] = ob.quartz_probe_val
    try:
        ui = ob.id_properties_ui("quartz_custom")
        ui.update(min=0.0, max=10.0, description="")
        res["id_properties_ui_as_dict"] = _clean(ui.as_dict())
    except Exception as ex:
        res["id_properties_ui_as_dict"] = _err(ex)
    for name in ("bl_system_properties_get", "id_properties_ensure"):
        res["has_" + name] = hasattr(ob, name)
    try:
        sysprops = ob.bl_system_properties_get()
        res["system_props_keys"] = _clean(sysprops.keys()) if sysprops is not None else None
    except Exception as ex:
        res["system_props_keys"] = _err(ex)
    for k in ("quartz_custom", "quartz_custom_list", "quartz_custom_dict"):
        del ob[k]
    del bpy.types.Object.quartz_probe_val
    res["keys_after_cleanup"] = _clean(ob.keys())
    return res


@probe
def property_semantics():
    res = {}
    log = []

    class QUARTZPROBE_PG_assign(bpy.types.PropertyGroup):
        x = bpy.props.IntProperty()

    res["assign_style_register"] = _try_register(QUARTZPROBE_PG_assign)
    res["assign_style_has_rna_prop"] = (
        "x" in QUARTZPROBE_PG_assign.bl_rna.properties.keys()
        if QUARTZPROBE_PG_assign.is_registered else None
    )
    _safe_unregister(QUARTZPROBE_PG_assign)

    class QUARTZPROBE_PG_item(bpy.types.PropertyGroup):
        value: bpy.props.FloatProperty(default=1.5)

    def upd(self, context):
        log.append(("update", self.level, context is not None))

    def getter(self):
        log.append("get")
        return self.get("_shadow", 7)

    def setter(self, value):
        log.append(("set", value))
        self["_shadow"] = value

    class QUARTZPROBE_PG_main(bpy.types.PropertyGroup):
        level: bpy.props.IntProperty(default=3, min=0, max=10, update=upd)
        computed: bpy.props.IntProperty(get=getter, set=setter)
        ro: bpy.props.IntProperty(get=lambda self: 42)
        items: bpy.props.CollectionProperty(type=QUARTZPROBE_PG_item)
        entries: bpy.props.CollectionProperty(type=QUARTZPROBE_PG_item)
        active_index: bpy.props.IntProperty()
        target: bpy.props.PointerProperty(type=bpy.types.Object)
        kind: bpy.props.EnumProperty(items=lambda self, ctx: [("P", "P", ""), ("Q", "Q", "")])
        flags: bpy.props.EnumProperty(items=[("A", "A", ""), ("B", "B", "")], options={"ENUM_FLAG"},
                                      default={"A"})
        vec: bpy.props.FloatVectorProperty(size=3, subtype="XYZ")
        mat: bpy.props.FloatVectorProperty(size=(4, 4), subtype="MATRIX")
        text: bpy.props.StringProperty(default="hi", maxlen=8)

    try:
        bpy.types.Scene.quartz_probe_early = bpy.props.PointerProperty(type=QUARTZPROBE_PG_main)
        res["pointer_before_register"] = "ok"
        res["pointer_before_register_value"] = repr(getattr(bpy.context.scene, "quartz_probe_early", "<missing>"))
        del bpy.types.Scene.quartz_probe_early
    except Exception as ex:
        res["pointer_before_register"] = _err(ex)

    class QUARTZPROBE_PG_early(bpy.types.PropertyGroup):
        ok_prop: bpy.props.IntProperty()
        coll: bpy.props.CollectionProperty(type=QUARTZPROBE_PG_item)

    res["register_container_before_item"] = _try_register(QUARTZPROBE_PG_early)
    if res["register_container_before_item"] == "ok":
        res["container_before_item_rna_props"] = sorted(
            k for k in QUARTZPROBE_PG_early.bl_rna.properties.keys() if k != "rna_type")
        _safe_unregister(QUARTZPROBE_PG_early)
    res["register_item"] = _try_register(QUARTZPROBE_PG_item)
    res["reregister_container_after_item"] = _try_register(QUARTZPROBE_PG_early)
    if res["reregister_container_after_item"] == "ok":
        res["container_after_item_rna_props"] = sorted(
            k for k in QUARTZPROBE_PG_early.bl_rna.properties.keys() if k != "rna_type")
        _safe_unregister(QUARTZPROBE_PG_early)
    res["register_main"] = _try_register(QUARTZPROBE_PG_main)

    scene = bpy.context.scene
    bpy.types.Scene.quartz_probe = bpy.props.PointerProperty(type=QUARTZPROBE_PG_main)
    bpy.types.Scene.quartz_level = bpy.props.IntProperty(default=5)
    pg = scene.quartz_probe
    res["pg_type"] = type(pg).__name__
    res["scene_int_default"] = scene.quartz_level
    res["idprop_key_before_set"] = "quartz_level" in scene.keys()
    scene.quartz_level = 9
    res["idprop_key_after_set"] = "quartz_level" in scene.keys()
    res["idprop_raw_after_set"] = _clean(scene.get("quartz_level"))
    res["level_default"] = pg.level
    pg.level = 4
    pg.level = 4
    try:
        pg.level = 50
        res["level_after_out_of_range"] = pg.level
    except Exception as ex:
        res["level_after_out_of_range"] = _err(ex)
    try:
        pg.level = "x"
    except Exception as ex:
        res["level_set_wrong_type"] = _err(ex)
    res["computed_get"] = pg.computed
    pg.computed = 11
    res["computed_after_set"] = pg.computed
    try:
        pg.ro = 1
        res["readonly_set"] = "no error"
    except Exception as ex:
        res["readonly_set"] = _err(ex)
    res["name_collision_items_attr_type"] = type(pg.items).__name__
    res["name_collision_items_in_rna"] = "items" in QUARTZPROBE_PG_main.bl_rna.properties.keys()
    try:
        res["name_collision_items_via_path_resolve"] = type(pg.path_resolve("items")).__name__
    except Exception as ex:
        res["name_collision_items_via_path_resolve"] = _err(ex)
    it = pg.entries.add()
    it.name = "first"
    pg.entries.add().name = "second"
    res["collection_len"] = len(pg.entries)
    res["collection_keys"] = pg.entries.keys()
    res["collection_item_value"] = pg.entries["first"].value
    res["collection_find"] = pg.entries.find("second")
    pg.entries.move(0, 1)
    res["collection_after_move"] = pg.entries.keys()
    pg.entries.remove(0)
    res["collection_after_remove"] = pg.entries.keys()
    pg.entries.clear()
    res["collection_after_clear"] = len(pg.entries)
    res["pointer_default"] = repr(pg.target)
    pg.target = bpy.data.objects[0]
    res["pointer_set"] = pg.target.name
    try:
        pg.target = bpy.data.meshes[0]
        res["pointer_wrong_type"] = "no error"
    except Exception as ex:
        res["pointer_wrong_type"] = _err(ex)
    res["dynamic_enum_default"] = pg.kind
    try:
        pg.kind = "Q"
        res["dynamic_enum_set"] = pg.kind
        pg.kind = "Z"
    except Exception as ex:
        res["dynamic_enum_bad_set"] = _err(ex)
    res["flag_enum_default"] = _clean(pg.flags)
    pg.flags = {"A", "B"}
    res["flag_enum_set"] = _clean(pg.flags)
    res["vec_type"] = type(pg.vec).__name__
    res["mat_type"] = type(pg.mat).__name__
    pg.text = "0123456789abc"
    res["string_maxlen_truncation"] = pg.text
    res["pg_idprops"] = _clean(pg.keys())
    res["pg_path_from_id"] = pg.path_from_id()
    res["pg_id_data"] = pg.id_data.name
    res["update_log"] = _clean(log)
    res["rna_props_on_pg"] = sorted(QUARTZPROBE_PG_main.bl_rna.properties.keys())

    try:
        bpy.types.Scene.quartz_bad_enum = bpy.props.EnumProperty(items=[("A", "A", "")], default="Z")
        res["enum_default_not_in_items"] = "ok"
        del bpy.types.Scene.quartz_bad_enum
    except Exception as ex:
        res["enum_default_not_in_items"] = _err(ex)

    res["unregister_item_while_used"] = _safe_unregister(QUARTZPROBE_PG_item)
    del bpy.types.Scene.quartz_probe
    del bpy.types.Scene.quartz_level
    res["has_attr_after_del"] = hasattr(bpy.types.Scene, "quartz_probe")
    res["unregister_main"] = _safe_unregister(QUARTZPROBE_PG_main)
    res["unregister_item"] = _safe_unregister(QUARTZPROBE_PG_item)
    res["scene_idprops_left"] = _clean(scene.keys())
    return res


@probe
def id_semantics():
    res = {}
    m1 = bpy.data.meshes.new("QProbe")
    m2 = bpy.data.meshes.new("QProbe")
    m3 = bpy.data.meshes.new("QProbe")
    res["dup_names"] = [m1.name, m2.name, m3.name]
    res["new_mesh_users"] = m1.users
    ob = bpy.data.objects.new("QProbeOb", m1)
    res["mesh_users_after_object"] = m1.users
    res["object_users_unlinked"] = ob.users
    res["object_type"] = ob.type
    bpy.context.scene.collection.objects.link(ob)
    res["object_users_linked"] = ob.users
    try:
        bpy.context.scene.collection.objects.link(ob)
        res["link_twice"] = "no error"
    except Exception as ex:
        res["link_twice"] = _err(ex)
    empty = bpy.data.objects.new("QProbeEmpty", None)
    res["object_none_data_type"] = empty.type
    m2.name = "QProbe"
    res["rename_to_existing"] = [m1.name, m2.name]
    long_name = "N" * 300
    m3.name = long_name
    res["name_len_after_300"] = len(m3.name)
    res["name_bytes_after_300"] = len(m3.name.encode("utf-8"))
    m3.name = "Ã" * 200
    res["name_len_multibyte_200"] = len(m3.name)
    res["name_bytes_multibyte_200"] = len(m3.name.encode("utf-8"))
    m3.name = ""
    res["empty_name_becomes"] = m3.name
    res["fake_user_default"] = m2.use_fake_user
    m2.use_fake_user = True
    res["users_with_fake_user"] = m2.users
    m2.use_fake_user = False
    res["id_type"] = ob.id_type
    res["session_uid_type"] = type(getattr(ob, "session_uid", None)).__name__
    res["is_evaluated"] = ob.is_evaluated
    res["original_is_self"] = ob.original == ob
    res["name_full"] = getattr(ob, "name_full", None)
    res["get_by_name"] = bpy.data.meshes.get("QProbe") is not None
    res["contains"] = "QProbe" in bpy.data.meshes
    res["index_by_name_missing"] = None
    try:
        bpy.data.meshes["__nope__"]
    except Exception as ex:
        res["index_by_name_missing"] = _err(ex)
    mc = m1.copy()
    res["copy_name"] = mc.name
    res["copy_users"] = mc.users
    try:
        bpy.data.meshes.remove(m1)
        res["remove_used_mesh"] = "ok"
        res["object_data_after_mesh_remove"] = repr(ob.data)
    except Exception as ex:
        res["remove_used_mesh"] = _err(ex)
    try:
        _ = m1.name
        res["access_removed"] = "no error"
    except Exception as ex:
        res["access_removed"] = _err(ex)
    try:
        bpy.data.meshes.remove(m1)
        res["remove_twice"] = "no error"
    except Exception as ex:
        res["remove_twice"] = _err(ex)
    try:
        res["orphans_purge_returns"] = _clean(bpy.data.orphans_purge(do_recursive=True))
    except Exception as ex:
        res["orphans_purge_returns"] = _err(ex)
    for idb in (ob, empty):
        try:
            bpy.data.objects.remove(idb)
        except Exception:
            pass
    for name in ("QProbe", "QProbe.001", "QProbe.002", "QProbe.003"):
        m = bpy.data.meshes.get(name)
        if m is not None:
            bpy.data.meshes.remove(m)
    try:
        um = bpy.data.user_map(subset=[bpy.data.meshes[0]])
        res["user_map_sample"] = {k.name: sorted(u.name for u in v) for k, v in um.items()}
    except Exception as ex:
        res["user_map_sample"] = _err(ex)
    me = bpy.data.meshes.new("QProbeBuild")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    res["from_pydata_counts"] = [len(me.vertices), len(me.edges), len(me.loops), len(me.polygons)]
    res["from_pydata_validate"] = me.validate()
    res["from_pydata_attributes"] = [(a.name, a.domain, a.data_type) for a in me.attributes]
    res["polygon0"] = {"loop_start": me.polygons[0].loop_start, "loop_total": me.polygons[0].loop_total,
                       "vertices": list(me.polygons[0].vertices),
                       "edge_keys": _clean(me.polygons[0].edge_keys)}
    res["edge_keys"] = _clean(me.edge_keys)
    buf = [0.0] * (len(me.vertices) * 3)
    me.vertices.foreach_get("co", buf)
    res["foreach_get_co"] = buf
    try:
        import numpy as np
        arr = np.zeros(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", arr)
        res["foreach_get_numpy"] = "ok"
    except Exception as ex:
        res["foreach_get_numpy"] = _err(ex)
    bpy.data.meshes.remove(me)
    return res


@probe
def context_semantics():
    res = {}
    ctx = bpy.context
    res["window_is_none"] = ctx.window is None
    res["area_is_none"] = ctx.area is None
    res["active_object"] = ctx.active_object.name if ctx.active_object else None
    res["has_temp_override"] = hasattr(ctx, "temp_override")
    cam = bpy.data.objects.get("Camera")
    try:
        with ctx.temp_override(active_object=cam, object=cam, selected_objects=[cam]):
            res["inside_override_active"] = bpy.context.active_object.name
            res["inside_override_selected"] = [o.name for o in bpy.context.selected_objects]
        res["after_override_active"] = bpy.context.active_object.name if bpy.context.active_object else None
    except Exception as ex:
        res["temp_override"] = _err(ex)
    try:
        with ctx.temp_override(not_a_member=1):
            res["override_unknown_member"] = getattr(bpy.context, "not_a_member", "<missing>")
    except Exception as ex:
        res["override_unknown_member"] = _err(ex)
    try:
        ctx.scene = None
    except Exception as ex:
        res["context_assign"] = _err(ex)
    res["copy_keys_sample"] = sorted(ctx.copy().keys())[:40]
    try:
        res["path_resolve"] = repr(ctx.path_resolve("scene.frame_current"))
    except Exception as ex:
        res["path_resolve"] = _err(ex)
    ob = bpy.data.objects.get("Cube")
    res["cube_mode"] = ob.mode if ob else None
    try:
        res["mode_set_edit"] = _clean(bpy.ops.object.mode_set(mode="EDIT"))
        res["mode_after"] = bpy.context.object.mode
        res["edit_object"] = bpy.context.edit_object.name if bpy.context.edit_object else None
        res["mode_set_object"] = _clean(bpy.ops.object.mode_set(mode="OBJECT"))
    except Exception as ex:
        res["mode_set"] = _err(ex)
    n_before = len(bpy.data.objects)
    try:
        res["primitive_cube_add"] = _clean(bpy.ops.mesh.primitive_cube_add(size=1, location=(3, 0, 0)))
        newob = bpy.context.active_object
        res["primitive_new_active"] = [newob.name, newob.data.name, len(newob.data.vertices),
                                       _clean(list(newob.location)), newob.select_get()]
        res["object_count_delta"] = len(bpy.data.objects) - n_before
        res["transform_translate"] = _clean(bpy.ops.transform.translate(value=(1, 0, 0)))
        res["location_after_translate"] = _clean(list(newob.location))
        res["object_delete"] = _clean(bpy.ops.object.delete())
        res["object_count_after_delete"] = len(bpy.data.objects) - n_before
        res["orphan_mesh_left"] = [m.name for m in bpy.data.meshes if m.users == 0]
    except Exception as ex:
        res["standard_ops"] = _err(ex)
    for m in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(m)
    return res


@probe
def undo_and_handlers():
    res = {}
    for name in ("undo", "redo", "undo_push", "undo_history"):
        op = getattr(bpy.ops.ed, name, None)
        try:
            res["ed_" + name + "_poll"] = bool(op.poll()) if op else None
        except Exception as ex:
            res["ed_" + name + "_poll"] = _err(ex)
    try:
        res["ed_undo_call"] = _clean(bpy.ops.ed.undo())
    except Exception as ex:
        res["ed_undo_call"] = _err(ex)
    try:
        res["ed_undo_push_call"] = _clean(bpy.ops.ed.undo_push(message="probe"))
    except Exception as ex:
        res["ed_undo_push_call"] = _err(ex)
    res["use_global_undo"] = bpy.context.preferences.edit.use_global_undo
    log = []

    @bpy.app.handlers.persistent
    def on_frame_pre(scene, depsgraph=None):
        log.append(("frame_change_pre", scene.frame_current, depsgraph is not None))

    def on_frame_post(*args):
        log.append(("frame_change_post", len(args), [type(a).__name__ for a in args]))

    def on_depsgraph(*args):
        log.append(("depsgraph_update_post", [type(a).__name__ for a in args]))

    res["persistent_marks"] = sorted(a for a in dir(on_frame_pre) if "persistent" in a) or \
        repr(getattr(on_frame_pre, "_bpy_persistent", None))
    bpy.app.handlers.frame_change_pre.append(on_frame_pre)
    bpy.app.handlers.frame_change_post.append(on_frame_post)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph)
    scene = bpy.context.scene
    scene.frame_set(7)
    bpy.context.view_layer.update()
    bpy.data.objects[0].location.x += 0.0
    bpy.context.view_layer.update()
    scene.frame_set(1)
    bpy.app.handlers.frame_change_pre.remove(on_frame_pre)
    bpy.app.handlers.frame_change_post.remove(on_frame_post)
    bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph)
    res["handler_log"] = _clean(log)
    res["handler_list_type"] = type(bpy.app.handlers.load_post).__name__
    fired = []
    bpy.app.timers.register(lambda: fired.append(1), first_interval=0.0)
    res["timer_registered"] = True
    res["timer_fired_immediately"] = bool(fired)
    try:
        res["timer_is_registered_api"] = "is_registered" in dir(bpy.app.timers)
    except Exception as ex:
        res["timer_is_registered_api"] = _err(ex)
    notes = []
    owner = object()
    try:
        bpy.msgbus.subscribe_rna(key=(bpy.types.Object, "location"), owner=owner, args=(1,),
                                 notify=lambda *a: notes.append(a))
        bpy.data.objects[0].location.x += 0.0
        bpy.msgbus.publish_rna(key=(bpy.types.Object, "location"))
        res["msgbus_subscribe"] = "ok"
        res["msgbus_notified_sync"] = len(notes)
        bpy.msgbus.clear_by_owner(owner)
    except Exception as ex:
        res["msgbus_subscribe"] = _err(ex)
    return res


@probe
def ui_extension_points():
    res = {}
    def fn(self, context):
        pass
    menu = bpy.types.VIEW3D_MT_mesh_add
    res["is_extended_before"] = menu.is_extended()
    menu.append(fn)
    res["is_extended_after"] = menu.is_extended()
    res["draw_funcs_len"] = len(getattr(menu.draw, "_draw_funcs", []))
    menu.remove(fn)
    menu.remove(fn)
    res["remove_twice"] = "silent"
    res["builtin_menu_count"] = len([n for n in dir(bpy.types) if "_MT_" in n])
    res["builtin_panel_count"] = len([n for n in dir(bpy.types) if "_PT_" in n])
    res["builtin_header_count"] = len([n for n in dir(bpy.types) if "_HT_" in n])
    res["builtin_uilist_count"] = len([n for n in dir(bpy.types) if "_UL_" in n])
    res["common_menus_present"] = {n: hasattr(bpy.types, n) for n in (
        "VIEW3D_MT_mesh_add", "VIEW3D_MT_object", "VIEW3D_MT_add", "TOPBAR_MT_file_import",
        "TOPBAR_MT_file_export", "VIEW3D_MT_editor_menus", "VIEW3D_PT_tools_active",
        "OBJECT_PT_context_object", "VIEW3D_MT_edit_mesh", "NODE_MT_add")}
    kc = bpy.context.window_manager.keyconfigs
    res["keyconfigs_addon_is_none"] = kc.addon is None
    try:
        km = kc.addon.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new("object.select_all", "A", "PRESS", ctrl=True)
        res["keymap_item"] = [kmi.idname, kmi.type, kmi.value, kmi.ctrl]
        km.keymap_items.remove(kmi)
    except Exception as ex:
        res["keymap_item"] = _err(ex)
    return res


@probe
def addon_lifecycle():
    import addon_utils
    res = {}
    base = os.path.join(TMP_DIR, "probe_addons")
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, "quartz_probe_addon.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            '"""Throw-away add-on used by the Quartz API dump."""\n'
            "# Quartz - author: D1on1n\n"
            "bl_info = {\n"
            '    "name": "Quartz Probe", "author": "D1on1n <x@y.z>", "version": (0, 1, 0),\n'
            '    "blender": (4, 2, 0), "category": "Development",\n'
            "}\n"
            "import bpy\n"
            "LOG = []\n"
            "class QuartzProbePrefs(bpy.types.AddonPreferences):\n"
            "    bl_idname = __name__\n"
            "    flag: bpy.props.BoolProperty(default=True)\n"
            "def register():\n"
            "    LOG.append('register')\n"
            "    bpy.utils.register_class(QuartzProbePrefs)\n"
            "def unregister():\n"
            "    LOG.append('unregister')\n"
            "    bpy.utils.unregister_class(QuartzProbePrefs)\n"
        )
    if base not in sys.path:
        sys.path.append(base)
    res["check_before"] = _clean(addon_utils.check("quartz_probe_addon"))
    mod = addon_utils.enable("quartz_probe_addon", default_set=True, refresh_handled=True)
    res["enable_returns_module"] = mod is not None
    if mod is not None:
        res["module_flags"] = {
            "__addon_enabled__": getattr(mod, "__addon_enabled__", None),
            "__addon_persistent__": getattr(mod, "__addon_persistent__", None),
            "has___time__": hasattr(mod, "__time__"),
        }
        res["log_after_enable"] = list(mod.LOG)
        res["check_after_enable"] = _clean(addon_utils.check("quartz_probe_addon"))
        addon = bpy.context.preferences.addons.get("quartz_probe_addon")
        res["in_preferences_addons"] = addon is not None
        if addon is not None:
            prefs = addon.preferences
            res["prefs_type"] = type(prefs).__name__ if prefs else None
            res["prefs_flag"] = getattr(prefs, "flag", None)
        res["module_bl_info"] = _clean(addon_utils.module_bl_info(mod))
        addon_utils.disable("quartz_probe_addon", default_set=True, refresh_handled=True)
        res["log_after_disable"] = list(mod.LOG)
        res["check_after_disable"] = _clean(addon_utils.check("quartz_probe_addon"))
        res["still_in_sys_modules"] = "quartz_probe_addon" in sys.modules
    try:
        mod_missing = addon_utils.enable("quartz_no_such_addon", refresh_handled=True,
                                         handle_error=lambda ex: res.__setitem__("missing_error", _err(ex)))
        res["enable_missing_returns"] = repr(mod_missing)
    except Exception as ex:
        res["enable_missing_returns"] = _err(ex)
    res["addon_utils_public"] = sorted(a for a in dir(addon_utils) if not a.startswith("_"))
    res["bl_info_basis"] = _clean(addon_utils._bl_info_basis())
    res["ext_base_pkg"] = getattr(addon_utils, "_ext_base_pkg_idname", None)
    res["ext_manifest_filename"] = getattr(addon_utils, "_ext_manifest_filename_toml", None)
    res["extension_repos"] = [
        {"module": r.module, "enabled": r.enabled, "source": r.source, "use_remote_url": r.use_remote_url}
        for r in bpy.context.preferences.extensions.repos
    ]
    try:
        sys.path.remove(base)
    except ValueError:
        pass
    sys.modules.pop("quartz_probe_addon", None)
    return res



def main():
    t0 = time.time()
    dump = {
        "meta": {
            "blender_version": list(bpy.app.version),
            "version_string": bpy.app.version_string,
            "version_file": list(bpy.app.version_file),
            "python": sys.version,
            "background": bpy.app.background,
            "factory_startup": bpy.app.factory_startup,
            "generated_by": "Quartz tools/dump_bpy_api.py (author: D1on1n)",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": "Facts only (names/types/defaults/ranges/enum ids/probe results). No description text.",
        },
    }
    sections = (
        ("factory_scene", factory_scene_info),
        ("id_types", lambda: {n: rna_struct_info(n) for n in ID_TYPES}),
        ("sub_structs", lambda: {n: rna_struct_info(n) for n in SUB_STRUCTS}),
        ("base_classes", lambda: {n: base_class_info(n) for n in BASE_CLASSES}),
        ("bpy_struct_methods", lambda: sorted(a for a in dir(bpy.types.bpy_struct) if not a.startswith("__"))),
        ("ID_python_dir", lambda: sorted(a for a in dir(bpy.types.ID) if not a.startswith("__"))),
        ("props", props_info),
        ("utils", lambda: module_callables(bpy.utils)),
        ("utils_units", lambda: module_callables(bpy.utils.units)),
        ("path", lambda: module_callables(bpy.path)),
        ("app", app_info),
        ("context", context_info),
        ("data", data_info),
        ("types_names", lambda: sorted(n for n in dir(bpy.types) if not n.startswith("_"))),
        ("ops", ops_info),
        ("extras", extras_info),
    )
    errors = {}
    for key, fn in sections:
        try:
            dump[key] = fn()
        except Exception:
            errors[key] = traceback.format_exc()
    probes = {}
    for name, fn in PROBES.items():
        try:
            probes[name] = fn()
        except Exception:
            probes[name] = {"probe_crashed": traceback.format_exc()}
    dump["probes"] = probes
    dump["errors"] = errors
    dump["meta"]["seconds"] = round(time.time() - t0, 2)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(_clean(dump), fh, indent=1, ensure_ascii=False, sort_keys=False)
    print("QUARTZ_DUMP_OK", OUT_PATH, "errors:", list(errors), "seconds:", dump["meta"]["seconds"])


if __name__ == "__main__":
    main()
