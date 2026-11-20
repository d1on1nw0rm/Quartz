from __future__ import annotations

import copy

import numpy as np

from ..ext import store
from . import hub as _hub

__all__ = [
    "TAGS_KEY",
    "SELECTIONS_KEY",
    "PROJECTIONS",
    "new_material_tag",
    "object_tags",
    "material_tags",
    "apply_material",
    "add_material_tag",
    "set_tag_field",
    "remove_material_tags",
    "remove_tag",
    "assign_to_selected",
    "remove_from_selected",
    "objects_using",
    "polygon_selection",
    "tag_enabled",
    "active_material_tags",
    "resolve_material_ref",
    "effective_material_id",
    "polygon_material_ids",
    "tag_uv",
    "project_uv",
    "object_uvs",
]

TAGS_KEY = "tags"
SELECTIONS_KEY = "selections"
PROJECTIONS = ("uvw", "spherical", "cylindrical", "cubic", "flat", "frontal", "shrinkwrap")


def new_material_tag(mid: str, projection: str = "uvw", offset=(0.0, 0.0), tiling=(1.0, 1.0),
                     selection: str = "") -> dict:
    if projection not in PROJECTIONS:
        raise ValueError(f"unknown projection {projection!r}")
    return {"type": "material", "material": str(mid), "projection": projection,
            "offset": [float(offset[0]), float(offset[1])],
            "tiling": [float(tiling[0]), float(tiling[1])], "selection": str(selection or "")}


def object_tags(obj) -> list:
    tags = store.get_object(obj, TAGS_KEY, None)
    return tags if isinstance(tags, list) else []


def material_tags(obj) -> list:
    return [t for t in object_tags(obj) if isinstance(t, dict) and t.get("type") == "material"]


def tag_enabled(tag: dict) -> bool:
    return bool(tag.get("enabled", True))


def active_material_tags(obj) -> list:
    return [t for t in material_tags(obj) if tag_enabled(t)]


def _commit(obj, tags: list) -> None:
    store.set_object(obj, TAGS_KEY, tags)
    _hub.emit(obj, TAGS_KEY)


def _clean_fields(fields: dict) -> dict:
    out = {}
    for key, value in fields.items():
        if key == "projection":
            if value not in PROJECTIONS:
                raise ValueError(f"unknown projection {value!r}")
            out[key] = str(value)
        elif key in ("offset", "tiling"):
            vals = [float(x) for x in value]
            if len(vals) != 2:
                raise ValueError(f"{key} needs 2 values")
            out[key] = vals
        elif key in ("selection", "material"):
            out[key] = str(value or "")
        elif key == "enabled":
            out[key] = bool(value)
        else:
            raise KeyError(f"material tag has no field {key!r}")
    return out


def apply_material(obj, mid: str, **fields) -> dict:
    fields = _clean_fields(fields)
    selection = fields.get("selection", "")
    tags = copy.deepcopy(object_tags(obj))
    target = None
    for i in range(len(tags) - 1, -1, -1):
        t = tags[i]
        if (isinstance(t, dict) and t.get("type") == "material" and t.get("selection", "") == selection
                and tag_enabled(t)):
            target = i
            break
    if target is None:
        tag = new_material_tag(mid)
        tag.update(fields)
        tag["material"] = str(mid)
        tags.append(tag)
    else:
        tag = tags[target]
        for k, v in new_material_tag(mid).items():
            tag.setdefault(k, v)
        tag.update(fields)
        tag["material"] = str(mid)
    _commit(obj, tags)
    return copy.deepcopy(tag)


def add_material_tag(obj, mid: str, **fields) -> dict:
    tag = new_material_tag(mid)
    tag.update(_clean_fields(fields))
    tag["material"] = str(mid)
    tags = copy.deepcopy(object_tags(obj))
    tags.append(tag)
    _commit(obj, tags)
    return copy.deepcopy(tag)


def _material_tag_positions(obj) -> list[int]:
    return [i for i, t in enumerate(object_tags(obj)) if isinstance(t, dict) and t.get("type") == "material"]


def set_tag_field(obj, index: int, key: str, value) -> dict:
    positions = _material_tag_positions(obj)
    if not 0 <= index < len(positions):
        raise IndexError(f"no material tag {index}")
    tags = copy.deepcopy(object_tags(obj))
    tag = tags[positions[index]]
    tag.update(_clean_fields({key: value}))
    _commit(obj, tags)
    return copy.deepcopy(tag)


def remove_tag(obj, index: int) -> bool:
    positions = _material_tag_positions(obj)
    if not 0 <= index < len(positions):
        return False
    tags = copy.deepcopy(object_tags(obj))
    tags.pop(positions[index])
    _commit(obj, tags)
    return True


def remove_material_tags(obj, mid: str | None = None) -> int:
    tags = object_tags(obj)
    keep = [t for t in tags if not (isinstance(t, dict) and t.get("type") == "material"
                                    and (mid is None or t.get("material") == mid))]
    removed = len(tags) - len(keep)
    if removed:
        _commit(obj, copy.deepcopy(keep))
    return removed


def _selected(scene) -> list:
    fn = getattr(scene, "selected_objects", None)
    if callable(fn):
        return list(fn())
    active = getattr(scene, "active", None)
    return [active] if active is not None else []


def assign_to_selected(scene, mid: str | None = None, **fields) -> int:
    from .model import active_material_id, find_material
    mid = mid or active_material_id(scene)
    if not mid or find_material(scene, mid) is None:
        return 0
    from .model import undo_group
    count = 0
    with undo_group(scene):
        for obj in _selected(scene):
            apply_material(obj, mid, **fields)
            count += 1
    return count


def remove_from_selected(scene, mid: str | None = None) -> int:
    from .model import undo_group
    with undo_group(scene):
        return sum(remove_material_tags(obj, mid) for obj in _selected(scene))


def objects_using(scene, mid: str) -> list:
    return [o for o in getattr(scene, "objects", []) if any(t.get("material") == mid for t in material_tags(o))]


def _tag_selection(obj, name: str) -> set | None:
    for t in object_tags(obj):
        if isinstance(t, dict) and t.get("type") == "polygon_selection" and t.get("name") == name:
            count = len(getattr(getattr(obj, "mesh", None), "polygons", []) or [])
            out = set()
            for i in t.get("selection") or []:
                try:
                    k = int(i)
                except (TypeError, ValueError):
                    continue
                if 0 <= k < count:
                    out.add(k)
            return out
    return None


def polygon_selection(obj, name: str) -> set | None:
    found = _tag_selection(obj, name)
    if found is not None:
        return found
    sels = store.get_object(obj, SELECTIONS_KEY, None)
    if not isinstance(sels, dict) or name not in sels:
        return None
    entry = sels[name]
    if isinstance(entry, dict):
        if entry.get("type", "polygons") not in ("polygons", "polygon"):
            return None
        entry = entry.get("indices", [])
    try:
        return {int(i) for i in entry}
    except TypeError:
        return None


def resolve_material_ref(scene, ref) -> str | None:
    from .model import find_material, materials
    if not isinstance(ref, str) or not ref:
        return None
    if find_material(scene, ref) is not None:
        return ref
    for m in materials(scene):
        if m.get("name") == ref:
            return m.get("id")
    return None


def effective_material_id(scene, obj, polygon: int | None = None) -> str | None:
    node = obj
    while node is not None:
        found = None
        for tag in active_material_tags(node):
            mid = resolve_material_ref(scene, tag.get("material"))
            if mid is None:
                continue
            sel = tag.get("selection", "")
            if not sel:
                found = mid
            elif polygon is not None and node is obj:
                members = polygon_selection(obj, sel)
                if members is not None and polygon in members:
                    found = mid
        if found is not None:
            return found
        node = getattr(node, "parent", None)
    return None


def polygon_material_ids(scene, obj) -> list:
    count = len(getattr(getattr(obj, "mesh", None), "polygons", []) or [])
    base = None
    parent = getattr(obj, "parent", None)
    if parent is not None:
        base = effective_material_id(scene, parent)
    out = [base] * count
    for tag in active_material_tags(obj):
        mid = resolve_material_ref(scene, tag.get("material"))
        if mid is None:
            continue
        sel = tag.get("selection", "")
        if not sel:
            out = [mid] * count
            continue
        members = polygon_selection(obj, sel)
        if members is None:
            continue
        for i in members:
            if 0 <= i < count:
                out[i] = mid
    return out


def tag_uv(tag: dict | None, u, v) -> tuple[np.ndarray, np.ndarray]:
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    if not tag:
        return u, v
    tu, tv = tag.get("tiling", [1.0, 1.0])
    ou, ov = tag.get("offset", [0.0, 0.0])
    return u * float(tu) + float(ou), v * float(tv) + float(ov)


def _frontal_uv(pts, center, size, view) -> tuple[np.ndarray, np.ndarray]:
    f = np.asarray(view, float).reshape(-1)[:3] if view is not None else np.array([0.0, 0.0, -1.0])
    norm = float(np.linalg.norm(f))
    f = f / norm if norm > 1e-12 else np.array([0.0, 0.0, -1.0])
    up = np.array([0.0, 1.0, 0.0])
    right = np.cross(f, up)
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1.0, 0.0, 0.0])
    right = right / np.linalg.norm(right)
    upv = np.cross(right, f)
    d = pts - center
    sx = d @ right
    sy = d @ upv
    ext = np.abs(size @ np.abs(np.column_stack([right, upv])))
    ext = np.where(ext > 1e-12, ext, 1.0)
    return sx / ext[0] + 0.5, sy / ext[1] + 0.5


def project_uv(projection: str, points, normals=None, bounds=None, view=None) -> tuple[np.ndarray, np.ndarray]:
    pts = np.atleast_2d(np.asarray(points, float))
    if bounds is None:
        lo, hi = pts.min(axis=0), pts.max(axis=0)
    else:
        lo, hi = (np.asarray(b, float) for b in bounds)
    center = (lo + hi) * 0.5
    size = np.where(hi - lo > 1e-12, hi - lo, 1.0)
    q = (pts - center) / size
    if projection == "frontal":
        return _frontal_uv(pts, center, size, view)
    if projection in ("spherical", "shrinkwrap"):
        d = pts - center
        r = np.linalg.norm(d, axis=1)
        r = np.where(r > 1e-12, r, 1.0)
        u = 0.5 + np.arctan2(d[:, 0], d[:, 2]) / (2.0 * np.pi)
        v = 0.5 + np.arcsin(np.clip(d[:, 1] / r, -1.0, 1.0)) / np.pi
        return u, v
    if projection == "cylindrical":
        d = pts - center
        u = 0.5 + np.arctan2(d[:, 0], d[:, 2]) / (2.0 * np.pi)
        v = q[:, 1] + 0.5
        return u, v
    if projection == "cubic":
        n = np.atleast_2d(np.asarray(normals, float)) if normals is not None else pts - center
        axis = np.argmax(np.abs(n), axis=1)
        sign = np.sign(n[np.arange(len(n)), axis])
        sign = np.where(sign == 0, 1.0, sign)
        u = np.where(axis == 0, -sign * q[:, 2], np.where(axis == 1, q[:, 0], sign * q[:, 0])) + 0.5
        v = np.where(axis == 1, -sign * q[:, 2], q[:, 1]) + 0.5
        return u, v
    if projection == "flat":
        return q[:, 0] + 0.5, q[:, 1] + 0.5
    return q[:, 0] + 0.5, q[:, 1] + 0.5


def object_uvs(obj, tag: dict | None = None) -> tuple[np.ndarray, np.ndarray]:
    mesh = obj.mesh
    pts = np.asarray(mesh.points, float)
    projection = (tag or {}).get("projection", "uvw")
    stored = store.get_object(obj, "uvw", None)
    if projection == "uvw" and stored is not None:
        arr = np.asarray(stored, float).reshape(-1, 2)
        if len(arr) == len(pts):
            return tag_uv(tag, arr[:, 0], arr[:, 1])
    normals = None
    if projection in ("cubic", "uvw") and len(pts):
        acc = np.zeros_like(pts)
        pn = mesh.polygon_normals() if mesh.polygons else np.zeros((0, 3))
        for k, poly in enumerate(mesh.polygons):
            acc[list(poly)] += pn[k]
        normals = acc
    proj = projection if projection != "uvw" else "cubic"
    if len(pts) == 0:
        return np.zeros(0), np.zeros(0)
    u, v = project_uv(proj, pts, normals)
    return tag_uv(tag, u, v)
