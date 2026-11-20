from __future__ import annotations

import copy
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

from ..ext import store
from . import hub as _hub
from .params import Param, coerce
from .textures import TEXTURE_TYPES, add_image_search_path, new_texture, set_texture_param

__all__ = [
    "ChannelSpec",
    "CHANNELS",
    "CHANNEL_KEYS",
    "MATERIAL_KINDS",
    "PRESETS",
    "LIBRARY_KEY",
    "ACTIVE_KEY",
    "channel_spec",
    "new_id",
    "new_material",
    "preset_material",
    "materials",
    "find_material",
    "material_index",
    "active_material",
    "active_material_id",
    "set_active_material",
    "add_material",
    "create_material",
    "update_material",
    "delete_material",
    "duplicate_material",
    "rename_material",
    "unique_material_name",
    "set_channel",
    "set_channel_texture",
    "set_texture_value",
    "material_signature",
    "save_library",
    "load_library",
    "unused_materials",
    "delete_unused",
    "undo_group",
    "end_coalescing",
    "sanitize_material",
    "sanitize_texture",
    "COALESCE_SECONDS",
]

LIBRARY_KEY = "materials"
ACTIVE_KEY = "active_material"
MATERIAL_KINDS = ("pbr", "node")


@dataclass(frozen=True)
class ChannelSpec:
    key: str
    label: str
    kind: str
    default: object = None
    optional: bool = False
    enabled: bool = True
    textured: bool = True
    minimum: float = 0.0
    maximum: float = 1.0
    extras: tuple = field(default=())
    texture_range: tuple | None = None

    def value_param(self) -> Param | None:
        if self.kind == "color":
            return Param("value", self.label, "color", list(self.default))
        if self.kind == "float":
            return Param("value", self.label, "float", float(self.default), self.minimum, self.maximum)
        return None

    def params(self) -> tuple:
        out = []
        vp = self.value_param()
        if vp is not None:
            out.append(vp)
        if self.textured:
            out.append(Param("mix", "Texture Mix", "float", 1.0, 0.0, 1.0))
        out.extend(self.extras)
        return tuple(out)


CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec("base_color", "Base Color", "color", (0.8, 0.8, 0.8)),
    ChannelSpec("metallic", "Metallic", "float", 0.0),
    ChannelSpec("roughness", "Roughness", "float", 0.5),
    ChannelSpec("specular", "Specular", "float", 0.5),
    ChannelSpec("ior", "IOR", "float", 1.45, minimum=1.0, maximum=4.0, texture_range=(1.0, 2.5)),
    ChannelSpec("normal", "Normal", "normal", optional=True, enabled=False, extras=(
        Param("strength", "Strength", "float", 1.0, 0.0, 8.0, step=0.05),
        Param("flip_green", "Flip Green", "bool", False),
    )),
    ChannelSpec("bump", "Bump", "height", optional=True, enabled=False, extras=(
        Param("strength", "Strength", "float", 1.0, 0.0, 16.0, step=0.05),
        Param("distance", "Distance", "float", 0.02, 0.0, 1.0, step=0.005),
        Param("invert", "Invert", "bool", False),
    )),
    ChannelSpec("emission", "Emission", "color", (1.0, 1.0, 1.0), optional=True, enabled=False, extras=(
        Param("strength", "Strength", "float", 1.0, 0.0, 1000.0, step=0.1, soft_max=20.0),
    )),
    ChannelSpec("alpha", "Alpha", "float", 1.0, optional=True, enabled=False),
    ChannelSpec("transmission", "Transmission", "float", 1.0, optional=True, enabled=False),
    ChannelSpec("clearcoat", "Clearcoat", "float", 1.0, optional=True, enabled=False, extras=(
        Param("roughness", "Coat Roughness", "float", 0.03, 0.0, 1.0),
    )),
    ChannelSpec("sheen", "Sheen", "float", 1.0, optional=True, enabled=False, extras=(
        Param("tint", "Sheen Tint", "color", [1.0, 1.0, 1.0]),
        Param("roughness", "Sheen Roughness", "float", 0.5, 0.0, 1.0),
    )),
    ChannelSpec("displacement", "Displacement", "height", optional=True, enabled=False, extras=(
        Param("height", "Height", "float", 1.0, 0.0, 10000.0, step=0.1, soft_max=50.0),
        Param("midlevel", "Mid Level", "float", 0.5, 0.0, 1.0),
    )),
)

CHANNEL_KEYS = tuple(c.key for c in CHANNELS)


def channel_spec(key: str) -> ChannelSpec:
    for c in CHANNELS:
        if c.key == key:
            return c
    raise KeyError(f"unknown channel {key!r}")


def new_id(prefix: str = "mat") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _default_channel(spec: ChannelSpec) -> dict:
    ch: dict = {"enabled": bool(spec.enabled)}
    vp = spec.value_param()
    if vp is not None:
        ch["value"] = copy.deepcopy(vp.default)
    if spec.textured:
        ch["texture"] = None
        ch["mix"] = 1.0
    for p in spec.extras:
        ch[p.key] = copy.deepcopy(p.default)
    return ch


def default_channels() -> dict:
    return {c.key: _default_channel(c) for c in CHANNELS}


def new_material(kind: str = "pbr", name: str = "Mat") -> dict:
    if kind not in MATERIAL_KINDS:
        raise ValueError(f"unknown material kind {kind!r}")
    mat = {"id": new_id(), "name": str(name), "type": kind, "channels": default_channels(),
           "preview": "sphere"}
    if kind == "node":
        from .nodes import new_graph
        mat["graph"] = new_graph()
    return mat


def _preset(name: str, **channels) -> dict:
    return {"name": name, "channels": channels}


PRESETS = {
    "plastic": _preset("Plastic", base_color={"value": [0.75, 0.12, 0.1]}, roughness={"value": 0.35}),
    "metal": _preset("Metal", base_color={"value": [0.91, 0.92, 0.92]}, metallic={"value": 1.0},
                     roughness={"value": 0.25}),
    "gold": _preset("Gold", base_color={"value": [1.0, 0.77, 0.34]}, metallic={"value": 1.0},
                    roughness={"value": 0.2}),
    "glass": _preset("Glass", base_color={"value": [1.0, 1.0, 1.0]}, roughness={"value": 0.0},
                     ior={"value": 1.5}, transmission={"enabled": True, "value": 1.0}),
    "rubber": _preset("Rubber", base_color={"value": [0.06, 0.06, 0.07]}, roughness={"value": 0.85},
                      specular={"value": 0.3}),
    "emissive": _preset("Emissive", base_color={"value": [0.05, 0.05, 0.05]},
                        emission={"enabled": True, "value": [0.37, 0.9, 0.78], "strength": 4.0}),
    "car_paint": _preset("Car Paint", base_color={"value": [0.05, 0.15, 0.55]}, metallic={"value": 0.6},
                         roughness={"value": 0.4}, clearcoat={"enabled": True, "value": 1.0, "roughness": 0.03}),
    "velvet": _preset("Velvet", base_color={"value": [0.35, 0.04, 0.12]}, roughness={"value": 0.9},
                      sheen={"enabled": True, "value": 1.0, "tint": [1.0, 0.7, 0.8]}),
    "checker": _preset("Checker", base_color={"texture": "checker"}),
    "marble": _preset("Marble", base_color={"texture": "noise"}, roughness={"value": 0.15}),
    "bricks": _preset("Bricks", base_color={"texture": "brick"}, roughness={"value": 0.8},
                      bump={"enabled": True, "texture": "brick", "strength": 1.0}),
}


def preset_material(preset: str) -> dict:
    if preset not in PRESETS:
        raise KeyError(f"unknown preset {preset!r}")
    spec = PRESETS[preset]
    mat = new_material("pbr", spec["name"])
    for key, values in spec["channels"].items():
        ch = mat["channels"][key]
        for k, v in values.items():
            if k == "texture":
                ch["texture"] = new_texture(v)
                if preset == "marble":
                    ch["texture"].update({"color1": [0.92, 0.92, 0.9], "color2": [0.35, 0.36, 0.4],
                                          "noise_type": "turbulence", "distortion": 1.5})
                if preset == "bricks" and key == "bump":
                    ch["texture"].update({"color1": [1.0, 1.0, 1.0], "color2": [1.0, 1.0, 1.0],
                                          "mortar_color": [0.0, 0.0, 0.0]})
            else:
                ch[k] = copy.deepcopy(v)
    return mat


def materials(scene) -> list:
    lib = store.get_scene_data(scene, LIBRARY_KEY, None)
    return lib if isinstance(lib, list) else []


COALESCE_SECONDS = 1.5
_BURSTS: dict = {}


def _undo_top(scene):
    stack = getattr(scene, "_undo", None)
    try:
        return stack[-1] if stack else None
    except (IndexError, TypeError):
        return None


def end_coalescing(scene=None) -> None:
    if scene is None:
        _BURSTS.clear()
    else:
        _BURSTS.pop(id(scene), None)


@contextmanager
def undo_group(scene):
    begin = getattr(scene, "begin_group", None)
    end = getattr(scene, "end_group", None)
    end_coalescing(scene)
    if not callable(begin) or not callable(end):
        yield
        return
    begin()
    try:
        yield
    finally:
        end()
        end_coalescing(scene)


def _burst_ok(scene, coalesce) -> bool:
    if coalesce is None or getattr(scene, "_group_depth", 0):
        return False
    rec = _BURSTS.get(id(scene))
    if not rec or rec["scene"] is not scene or rec["key"] != coalesce:
        return False
    if time.monotonic() - rec["time"] > COALESCE_SECONDS:
        return False
    top = _undo_top(scene)
    return top is not None and top is rec["top"]


def _write_scene(scene, key: str, value, coalesce=None) -> None:
    if _burst_ok(scene, coalesce):
        extras = store.scene_extras(scene)
        if value is None:
            extras.pop(key, None)
        else:
            extras[key] = store.to_json(value)
        _BURSTS[id(scene)]["time"] = time.monotonic()
        changed = getattr(scene, "changed", None)
        if changed is not None:
            changed.emit()
        store.notify(scene, key)
        return
    before = _undo_top(scene)
    store.set_scene_data(scene, key, value)
    after = _undo_top(scene)
    grouped = bool(getattr(scene, "_group_depth", 0))
    if coalesce is not None and after is not None and after is not before and not grouped:
        _BURSTS[id(scene)] = {"scene": scene, "key": coalesce, "time": time.monotonic(), "top": after}
    else:
        end_coalescing(scene)


def _commit(scene, lib: list, coalesce=None) -> None:
    _write_scene(scene, LIBRARY_KEY, lib, coalesce)
    _hub.emit(scene, LIBRARY_KEY)


def material_index(scene, mid: str) -> int:
    for i, m in enumerate(materials(scene)):
        if m.get("id") == mid:
            return i
    return -1


def find_material(scene, mid: str | None) -> dict | None:
    if not mid:
        return None
    i = material_index(scene, mid)
    return materials(scene)[i] if i >= 0 else None


def active_material_id(scene) -> str | None:
    mid = store.get_scene_data(scene, ACTIVE_KEY, None)
    return mid if find_material(scene, mid) is not None else None


def active_material(scene) -> dict | None:
    return find_material(scene, active_material_id(scene))


def set_active_material(scene, mid: str | None) -> None:
    if mid is not None and find_material(scene, mid) is None:
        raise KeyError(f"no material {mid!r}")
    if store.get_scene_data(scene, ACTIVE_KEY, None) == mid:
        return
    _write_scene(scene, ACTIVE_KEY, mid)
    _hub.emit(scene, ACTIVE_KEY)


def unique_material_name(scene, name: str, exclude: str | None = None) -> str:
    taken = {m.get("name") for m in materials(scene) if m.get("id") != exclude}
    if name not in taken:
        return name
    base = re.sub(r"\.\d+$", "", name) or "Mat"
    k = 1
    while f"{base}.{k}" in taken:
        k += 1
    return f"{base}.{k}"


def add_material(scene, material: dict, activate: bool = True) -> dict:
    mat = copy.deepcopy(material)
    ids = {m.get("id") for m in materials(scene)}
    if not mat.get("id") or mat["id"] in ids:
        mat["id"] = new_id()
    mat["name"] = unique_material_name(scene, str(mat.get("name") or "Mat"))
    lib = list(materials(scene))
    lib.append(mat)
    with undo_group(scene):
        _commit(scene, lib)
        if activate:
            set_active_material(scene, mat["id"])
    return mat


def create_material(scene, kind: str = "pbr", name: str | None = None, preset: str | None = None,
                    activate: bool = True) -> dict:
    if preset:
        mat = preset_material(preset)
        if name:
            mat["name"] = name
    else:
        mat = new_material(kind, name or "Mat")
    return add_material(scene, mat, activate)


def update_material(scene, material: dict, coalesce=None) -> dict:
    i = material_index(scene, material.get("id"))
    if i < 0:
        raise KeyError(f"no material {material.get('id')!r}")
    lib = list(materials(scene))
    lib[i] = copy.deepcopy(material)
    _commit(scene, lib, coalesce)
    return lib[i]


def _all_objects(scene) -> list:
    return list(getattr(scene, "objects", []) or [])


def delete_material(scene, mid: str) -> bool:
    i = material_index(scene, mid)
    if i < 0:
        return False
    lib = list(materials(scene))
    lib.pop(i)
    from .tags import remove_material_tags
    with undo_group(scene):
        _commit(scene, lib)
        for obj in _all_objects(scene):
            remove_material_tags(obj, mid)
        if store.get_scene_data(scene, ACTIVE_KEY, None) == mid:
            nxt = lib[min(i, len(lib) - 1)]["id"] if lib else None
            _write_scene(scene, ACTIVE_KEY, nxt)
            _hub.emit(scene, ACTIVE_KEY)
    return True


def duplicate_material(scene, mid: str, activate: bool = True) -> dict:
    src = find_material(scene, mid)
    if src is None:
        raise KeyError(f"no material {mid!r}")
    mat = copy.deepcopy(src)
    mat["id"] = new_id()
    i = material_index(scene, mid)
    mat["name"] = unique_material_name(scene, src.get("name", "Mat"))
    lib = list(materials(scene))
    lib.insert(i + 1, mat)
    with undo_group(scene):
        _commit(scene, lib)
        if activate:
            set_active_material(scene, mat["id"])
    return mat


def rename_material(scene, mid: str, name: str) -> str:
    mat = find_material(scene, mid)
    if mat is None:
        raise KeyError(f"no material {mid!r}")
    name = str(name).strip() or "Mat"
    final = unique_material_name(scene, name, exclude=mid)
    if mat.get("name") != final:
        new = copy.deepcopy(mat)
        new["name"] = final
        update_material(scene, new)
    return final


def set_channel(material: dict, key: str, field_name: str, value) -> dict:
    spec = channel_spec(key)
    ch = material.setdefault("channels", default_channels()).setdefault(key, _default_channel(spec))
    if field_name == "enabled":
        ch["enabled"] = bool(value) if spec.optional else True
        return material
    if field_name == "texture":
        return set_channel_texture(material, key, value)
    for p in spec.params():
        if p.key == field_name:
            ch[field_name] = coerce(p, value)
            return material
    raise KeyError(f"channel {key!r} has no field {field_name!r}")


def set_channel_texture(material: dict, key: str, texture) -> dict:
    spec = channel_spec(key)
    if not spec.textured:
        raise ValueError(f"channel {key!r} takes no texture")
    ch = material["channels"].setdefault(key, _default_channel(spec))
    if texture is None or texture == "" or texture == "none":
        ch["texture"] = None
    elif isinstance(texture, str):
        old = ch.get("texture") or {}
        tex = new_texture(texture)
        for k in ("tiling", "offset"):
            if k in old:
                tex[k] = copy.deepcopy(old[k])
        ch["texture"] = tex
    else:
        ch["texture"] = copy.deepcopy(texture)
    if ch["texture"] is not None and spec.optional:
        ch["enabled"] = True
    return material


def set_texture_value(material: dict, key: str, param: str, value) -> dict:
    from .textures import set_texture_param
    tex = material["channels"][key].get("texture")
    if not tex:
        raise ValueError(f"channel {key!r} has no texture")
    set_texture_param(tex, param, value)
    return material


def material_signature(material: dict) -> str:
    body = {k: v for k, v in material.items() if k not in ("name", "id")}
    return json.dumps(store.to_json(body), sort_keys=True, default=str)


def save_library(scene, path: str, ids=None) -> int:
    chosen = [m for m in materials(scene) if ids is None or m.get("id") in set(ids)]
    data = {"format": "quartz-materials", "version": 1, "materials": store.to_json(chosen)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return len(chosen)


def sanitize_texture(tex) -> dict | None:
    if isinstance(tex, str) and tex in TEXTURE_TYPES:
        return new_texture(tex)
    if not isinstance(tex, dict) or tex.get("type") not in TEXTURE_TYPES:
        return None
    out = new_texture(tex["type"])
    for key, value in tex.items():
        if key == "type":
            continue
        try:
            set_texture_param(out, key, value)
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return out


def _finite(value) -> bool:
    return value == value and abs(value) != float("inf")


def _sanitize_channel(spec: ChannelSpec, raw) -> dict:
    ch = _default_channel(spec)
    if not isinstance(raw, dict):
        return ch
    if spec.optional and "enabled" in raw:
        ch["enabled"] = bool(raw["enabled"])
    for p in spec.params():
        if p.key not in raw:
            continue
        try:
            value = coerce(p, raw[p.key])
        except (TypeError, ValueError, IndexError):
            continue
        if p.kind == "float" and not _finite(value):
            continue
        if p.kind == "color" and not all(_finite(c) for c in value):
            continue
        ch[p.key] = value
    if spec.textured:
        ch["texture"] = sanitize_texture(raw.get("texture"))
    return ch


def sanitize_material(raw) -> dict | None:
    if not isinstance(raw, dict) or raw.get("type") not in MATERIAL_KINDS:
        return None
    mat = {"id": str(raw.get("id") or new_id()), "name": str(raw.get("name") or "Mat"), "type": raw["type"]}
    given = raw.get("channels") if isinstance(raw.get("channels"), dict) else {}
    mat["channels"] = {spec.key: _sanitize_channel(spec, given.get(spec.key)) for spec in CHANNELS}
    preview = raw.get("preview")
    mat["preview"] = preview if preview in ("sphere", "cube", "plane") else "sphere"
    if mat["type"] == "node":
        from .nodes import sanitize_graph
        mat["graph"] = sanitize_graph(raw.get("graph"))
    return mat


def _library_items(data) -> list:
    if isinstance(data, dict):
        if data.get("format") not in (None, "quartz-materials"):
            raise ValueError(f"unsupported library format {data.get('format')!r}")
        items = data.get("materials", [])
    else:
        items = data
    if not isinstance(items, list):
        raise ValueError("a material library must hold a list of materials")
    return items


def load_library(scene, path: str) -> list:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    items = _library_items(data)
    add_image_search_path(os.path.dirname(os.path.abspath(path)))
    added = []
    with undo_group(scene):
        for raw in items:
            mat = sanitize_material(store.from_json(raw))
            if mat is None:
                continue
            added.append(add_material(scene, mat, activate=False))
        if added:
            set_active_material(scene, added[-1]["id"])
    return added


def unused_materials(scene) -> list:
    from .tags import material_tags
    used = set()
    for obj in _all_objects(scene):
        for tag in material_tags(obj):
            used.add(tag.get("material"))
    return [m for m in materials(scene) if m.get("id") not in used]


def delete_unused(scene) -> int:
    gone = [m["id"] for m in unused_materials(scene)]
    with undo_group(scene):
        for mid in gone:
            delete_material(scene, mid)
    return len(gone)


