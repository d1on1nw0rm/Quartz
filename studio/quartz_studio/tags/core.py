from __future__ import annotations

import copy
import time
import weakref
from contextlib import contextmanager
from typing import Any, Iterable

from ..ext import store
from .registry import TAG_SPECS, clamp_tag, get_tag_spec, has_tag_spec, make_tag

__all__ = [
    "TAGS_KEY",
    "CURRENT_KEY",
    "COALESCE_SECONDS",
    "watch_scene",
    "owner_scene",
    "undo_group",
    "end_coalescing",
    "write_extra",
    "sync_renames",
    "rename_references",
    "write_hooks",
    "display_name",
    "SELECTION_TYPES",
    "MODE_FOR_TYPE",
    "tags_of",
    "get_tags",
    "set_tags",
    "tag_at",
    "unique_tag_name",
    "add_tag",
    "remove_tag",
    "move_tag",
    "duplicate_tag",
    "update_tag",
    "set_tag_enabled",
    "rename_tag",
    "find_tags",
    "find_tag_by_name",
    "first_tag",
    "copy_tags",
    "clear_tags",
    "find_object",
    "set_current_tag",
    "current_tag",
    "run_action",
    "tag_summary",
    "selection_items",
    "store_selection",
    "restore_selection",
    "selection_tag_for_mode",
    "new_selection_tag",
    "selection_from_tag_name",
    "serialize_tags",
    "deserialize_tags",
]

TAGS_KEY = "tags"
CURRENT_KEY = "tags_current"

SELECTION_TYPES = ("point_selection", "edge_selection", "polygon_selection")
MODE_FOR_TYPE = {"point_selection": "points", "edge_selection": "edges",
                 "polygon_selection": "polygons"}


COALESCE_SECONDS = 1.0

_CURRENT: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_SCENES: "weakref.WeakSet" = weakref.WeakSet()
_NAMES: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_BURST: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_SLOTS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_HOOKS: list = []


def write_hooks() -> list:
    return _HOOKS


def _global_scene():
    try:
        from ..scene import get_scene
    except ImportError:
        return None
    try:
        return get_scene()
    except Exception:
        return None


def _name_map(scene) -> dict:
    out = weakref.WeakKeyDictionary()
    for o in getattr(scene, "objects", ()):
        try:
            out[o] = o.name
        except TypeError:
            pass
    return out


def watch_scene(scene) -> None:
    if scene is None:
        return
    try:
        if scene in _SCENES:
            return
        _SCENES.add(scene)
        _NAMES[scene] = _name_map(scene)
    except TypeError:
        return
    signal = getattr(scene, "objectsChanged", None)
    if signal is None:
        return
    ref = weakref.ref(scene)

    def on_objects() -> None:
        s = ref()
        if s is not None:
            sync_renames(s)
    try:
        signal.connect(on_objects)
        _SLOTS[scene] = on_objects
    except (AttributeError, RuntimeError, TypeError):
        pass


def owner_scene(obj):
    g = _global_scene()
    if g is not None and obj in getattr(g, "objects", ()):
        return g
    for s in list(_SCENES):
        if obj in getattr(s, "objects", ()):
            return s
    return None


def _resolve(scene, obj):
    if scene is not None and obj in getattr(scene, "objects", ()):
        return scene
    return owner_scene(obj)


@contextmanager
def undo_group(scene):
    begin = getattr(scene, "begin_group", None) if scene is not None else None
    end = getattr(scene, "end_group", None) if scene is not None else None
    if begin is None or end is None:
        yield
        return
    begin()
    try:
        yield
    finally:
        end()


def end_coalescing(scene=None) -> None:
    if scene is None:
        _BURST.clear()
        return
    try:
        _BURST.pop(scene, None)
    except TypeError:
        pass


def _undo_top(scene):
    stack = getattr(scene, "_undo", None)
    if stack is None:
        return None
    try:
        return stack[-1] if len(stack) else None
    except (IndexError, TypeError):
        return None


def _burst_valid(scene, obj, coalesce) -> bool:
    if coalesce is None or getattr(scene, "_group_depth", 0):
        return False
    try:
        rec = _BURST.get(scene)
    except TypeError:
        return False
    if not rec or rec["key"] != (id(obj), coalesce):
        return False
    if time.monotonic() - rec["time"] > COALESCE_SECONDS:
        return False
    top = _undo_top(scene)
    return top is not None and top is rec["top"]


def _remember_burst(scene, obj, coalesce) -> None:
    try:
        if coalesce is None:
            _BURST.pop(scene, None)
        else:
            _BURST[scene] = {"key": (id(obj), coalesce), "time": time.monotonic(),
                             "top": _undo_top(scene)}
    except TypeError:
        pass


def _quiet_write(obj, key: str, value) -> None:
    extras = store.object_extras(obj)
    if value is None:
        extras.pop(key, None)
    else:
        extras[key] = value


def write_extra(obj, key: str, value, coalesce=None, scene=None, quiet: bool = False) -> None:
    value = None if value is None else store.to_json(value)
    scene = _resolve(scene, obj)
    setter = getattr(scene, "set_object_extra", None) if scene is not None else None
    if quiet or setter is None:
        _quiet_write(obj, key, value)
        if scene is not None and not quiet:
            changed = getattr(scene, "changed", None)
            if changed is not None:
                changed.emit()
    elif _burst_valid(scene, obj, coalesce):
        _quiet_write(obj, key, value)
        _BURST[scene]["time"] = time.monotonic()
        scene.changed.emit()
    else:
        setter(obj, key, value)
        if coalesce is not None or not getattr(scene, "_group_depth", 0):
            _remember_burst(scene, obj, coalesce)
    store.notify(obj, key)


def tags_of(obj) -> list:
    tags = store.object_extras(obj).get(TAGS_KEY)
    return tags if isinstance(tags, list) else []


def get_tags(obj) -> list:
    return copy.deepcopy(tags_of(obj))


def display_name(tag: dict) -> str:
    name = tag.get("name") if isinstance(tag, dict) else None
    if name:
        return str(name)
    t = tag.get("type", "") if isinstance(tag, dict) else ""
    return TAG_SPECS[t].label if t in TAG_SPECS else (str(t) or "Tag")


def _clean_list(obj, tags: Iterable) -> list:
    stored = tags_of(obj)
    out = []
    for t in tags:
        if any(t == old for old in stored):
            out.append(t)
        else:
            out.append(clamp_tag(t))
    return out


def set_tags(obj, tags: Iterable[dict], coalesce=None, scene=None) -> None:
    clean = _clean_list(obj, tags)
    owner = _resolve(scene, obj)
    watch_scene(owner)
    if owner is not None and _burst_valid(owner, obj, coalesce):
        write_extra(obj, TAGS_KEY, clean if clean else None, coalesce=coalesce, scene=owner)
        for hook in list(_HOOKS):
            try:
                hook(None, obj)
            except Exception:
                pass
        return
    with undo_group(owner):
        write_extra(obj, TAGS_KEY, clean if clean else None, coalesce=coalesce, scene=owner)
        for hook in list(_HOOKS):
            try:
                hook(owner, obj)
            except Exception:
                pass


def tag_at(obj, index: int) -> dict | None:
    tags = tags_of(obj)
    if 0 <= index < len(tags):
        return tags[index]
    return None


def unique_tag_name(obj, name: str, skip: int | None = None) -> str:
    taken = {t.get("name") for i, t in enumerate(tags_of(obj)) if i != skip}
    if name not in taken:
        return name
    n = 1
    while f"{name}.{n}" in taken:
        n += 1
    return f"{name}.{n}"


def add_tag(obj, tag_id: str, index: int | None = None, name: str | None = None,
            scene=None, **values) -> int:
    spec = get_tag_spec(tag_id)
    tags = get_tags(obj)
    if spec.unique:
        for i, t in enumerate(tags):
            if t.get("type") == tag_id:
                return i
    tag = make_tag(tag_id, unique_tag_name(obj, name or spec.label), **values)
    if spec.on_create is not None:
        spec.on_create(scene, obj, tag)
    pos = len(tags) if index is None else max(0, min(int(index), len(tags)))
    tags.insert(pos, tag)
    set_tags(obj, tags, scene=scene)
    return pos


def remove_tag(obj, index: int) -> dict | None:
    tags = get_tags(obj)
    if not 0 <= index < len(tags):
        return None
    gone = tags.pop(index)
    set_tags(obj, tags)
    return gone


def move_tag(obj, index: int, new_index: int) -> bool:
    tags = get_tags(obj)
    if not 0 <= index < len(tags):
        return False
    new_index = max(0, min(int(new_index), len(tags) - 1))
    if new_index == index:
        return False
    tag = tags.pop(index)
    tags.insert(new_index, tag)
    set_tags(obj, tags)
    return True


def duplicate_tag(obj, index: int) -> int | None:
    tags = get_tags(obj)
    if not 0 <= index < len(tags):
        return None
    src = tags[index]
    spec = TAG_SPECS.get(src.get("type", ""))
    if spec is not None and spec.unique:
        return None
    dup = copy.deepcopy(src)
    dup["name"] = unique_tag_name(obj, src.get("name", "Tag"))
    tags.insert(index + 1, dup)
    set_tags(obj, tags)
    return index + 1


def update_tag(obj, index: int, _coalesce=None, **values) -> dict | None:
    tags = get_tags(obj)
    if not 0 <= index < len(tags):
        return None
    tag = tags[index]
    spec = TAG_SPECS.get(tag.get("type", ""))
    changed = False
    for key, value in values.items():
        if key == "name":
            v = unique_tag_name(obj, str(value).strip() or tag.get("name", "Tag"), skip=index)
        elif key == "enabled":
            v = bool(value)
        elif key == "type":
            continue
        else:
            p = spec.param(key) if spec is not None else None
            if p is None:
                if spec is not None:
                    raise KeyError(f"tag {tag.get('type')!r} has no parameter {key!r}")
                v = copy.deepcopy(value)
            else:
                v = p.clamp(value)
        if tag.get(key) != v:
            tag[key] = v
            changed = True
    old_name = tags_of(obj)[index].get("name")
    if changed and tag.get("name") != old_name and old_name:
        _retarget_refs(tags, index, str(old_name), str(tag["name"]))
    if changed:
        set_tags(obj, tags, coalesce=_coalesce)
    return tags_of(obj)[index]


def _retarget_refs(tags: list, index: int, old: str, new: str) -> int:
    kind = tags[index].get("type", "")
    count = 0
    for i, t in enumerate(tags):
        if i == index or not isinstance(t, dict):
            continue
        spec = TAG_SPECS.get(t.get("type", ""))
        if spec is None:
            continue
        for p in spec.params:
            if p.kind == "tag_ref" and (not p.ref_type or p.ref_type == kind) and t.get(p.key) == old:
                t[p.key] = new
                count += 1
    return count


def set_tag_enabled(obj, index: int, flag: bool) -> None:
    update_tag(obj, index, enabled=bool(flag))


def rename_tag(obj, index: int, name: str) -> str:
    tag = update_tag(obj, index, name=name)
    return "" if tag is None else tag["name"]


def find_tags(obj, tag_id: str | None = None, enabled_only: bool = False) -> list[tuple[int, dict]]:
    out = []
    for i, t in enumerate(tags_of(obj)):
        if tag_id is not None and t.get("type") != tag_id:
            continue
        if enabled_only and not t.get("enabled", True):
            continue
        out.append((i, t))
    return out


def find_tag_by_name(obj, name: str, tag_id: str | None = None) -> tuple[int, dict] | None:
    for i, t in find_tags(obj, tag_id):
        if t.get("name") == name:
            return i, t
    return None


def first_tag(obj, tag_id: str, enabled_only: bool = True) -> dict | None:
    found = find_tags(obj, tag_id, enabled_only)
    return found[0][1] if found else None


def copy_tags(src, dst, replace: bool = False, scene=None) -> int:
    tags = [] if replace else get_tags(dst)
    added = 0
    for t in get_tags(src):
        spec = TAG_SPECS.get(t.get("type", ""))
        if spec is not None and spec.unique and any(x.get("type") == t["type"] for x in tags):
            continue
        if spec is not None:
            for key in spec.captured:
                p = spec.param(key)
                t[key] = p.initial() if p is not None else None
            if spec.recapture and spec.on_create is not None:
                spec.on_create(scene, dst, t)
        taken = {x.get("name") for x in tags}
        name = t.get("name", "Tag")
        base, n = name, 1
        while name in taken:
            name = f"{base}.{n}"
            n += 1
        t["name"] = name
        tags.append(t)
        added += 1
    set_tags(dst, tags)
    return added


def clear_tags(obj) -> None:
    set_tags(obj, [])


def find_object(scene, name: str):
    if not name or scene is None:
        return None
    for o in getattr(scene, "objects", ()):
        if o.name == name:
            return o
    return None


def set_current_tag(scene, obj, index: int | None) -> None:
    if scene is None:
        return
    watch_scene(scene)
    value = None if obj is None else {"object": obj.name,
                                      "index": None if index is None else int(index),
                                      "id": id(obj)}
    try:
        _CURRENT[scene] = value
    except TypeError:
        scene.__dict__["_tags_current"] = value
    store.notify(scene, CURRENT_KEY)


def current_tag(scene) -> tuple[Any, int | None]:
    if scene is None:
        return None, None
    try:
        data = _CURRENT.get(scene)
    except TypeError:
        data = getattr(scene, "__dict__", {}).get("_tags_current")
    if not isinstance(data, dict):
        return None, None
    obj = None
    for o in getattr(scene, "objects", ()):
        if id(o) == data.get("id"):
            obj = o
            break
    if obj is None:
        obj = find_object(scene, data.get("object", ""))
        if obj is not None:
            data["id"] = id(obj)
    if obj is None:
        return None, None
    data["object"] = obj.name
    idx = data.get("index")
    if idx is None or not 0 <= int(idx) < len(tags_of(obj)):
        return obj, None
    return obj, int(idx)


def run_action(scene, obj, index: int, action_key: str):
    tag = tag_at(obj, index)
    if tag is None:
        raise IndexError("no tag at that index")
    spec = get_tag_spec(tag["type"])
    action = spec.action(action_key)
    if action is None:
        raise KeyError(f"tag {tag['type']!r} has no action {action_key!r}")
    with undo_group(_resolve(scene, obj)):
        return action.run(scene, obj, index)


def _renamed_tag(tag: dict, mapping: dict) -> dict | None:
    spec = TAG_SPECS.get(tag.get("type", ""))
    if spec is None:
        return None
    out = None
    for p in spec.params:
        if p.kind != "object":
            continue
        v = tag.get(p.key)
        if isinstance(v, str) and v in mapping:
            out = out if out is not None else copy.deepcopy(tag)
            out[p.key] = mapping[v]
    for key in spec.extra.get("name_keyed", ()):
        d = tag.get(key)
        if isinstance(d, dict) and any(k in mapping for k in d):
            out = out if out is not None else copy.deepcopy(tag)
            out[key] = {mapping.get(k, k): v for k, v in d.items()}
    return out


def rename_references(scene, mapping: dict, quiet: bool = True) -> int:
    mapping = {str(a): str(b) for a, b in mapping.items() if a and b and a != b}
    if not mapping or scene is None:
        return 0
    count = 0
    for o in list(getattr(scene, "objects", ())):
        new = []
        hit = False
        for t in tags_of(o):
            r = _renamed_tag(t, mapping) if isinstance(t, dict) else None
            if r is not None:
                hit = True
                count += 1
                new.append(r)
            else:
                new.append(t)
        if hit:
            write_extra(o, TAGS_KEY, new, scene=scene, quiet=quiet)
            for hook in list(_HOOKS):
                try:
                    hook(None if quiet else scene, o)
                except Exception:
                    pass
    if count and quiet:
        changed = getattr(scene, "changed", None)
        if changed is not None:
            changed.emit()
    return count


def sync_renames(scene) -> int:
    if scene is None:
        return 0
    try:
        old = _NAMES.get(scene)
    except TypeError:
        return 0
    now = _name_map(scene)
    _NAMES[scene] = now
    if not old:
        return 0
    taken = set(now.values())
    mapping = {}
    for key, name in now.items():
        before = old.get(key)
        if before is not None and before != name and before not in taken:
            mapping[before] = name
    return rename_references(scene, mapping) if mapping else 0


def tag_summary(obj, index: int) -> str:
    tag = tag_at(obj, index)
    if tag is None or not has_tag_spec(tag.get("type", "")):
        return ""
    spec = get_tag_spec(tag["type"])
    if spec.summary is None:
        return ""
    try:
        return str(spec.summary(obj, tag))
    except Exception:
        return ""


def _valid_items(obj, mode: str, items: Iterable) -> list:
    mesh = obj.mesh
    if mode == "points":
        n = len(mesh.points)
        return sorted({int(i) for i in items if 0 <= int(i) < n})
    if mode == "polygons":
        n = len(mesh.polygons)
        return sorted({int(i) for i in items if 0 <= int(i) < n})
    edges = set(mesh.edges)
    out = set()
    for e in items:
        a, b = int(e[0]), int(e[1])
        key = (a, b) if a < b else (b, a)
        if key in edges:
            out.add(key)
    return sorted(out)


def selection_items(obj, tag: dict) -> list:
    mode = MODE_FOR_TYPE.get(tag.get("type", ""))
    if mode is None:
        return []
    return _valid_items(obj, mode, tag.get("selection", []))


def _scene_set(scene, mode: str) -> set:
    return {"points": scene.selected_points, "edges": scene.selected_edges,
            "polygons": scene.selected_polygons}[mode]


def store_selection(scene, obj, index: int) -> int:
    tag = tag_at(obj, index)
    if tag is None or tag.get("type") not in SELECTION_TYPES:
        raise ValueError("not a selection tag")
    mode = MODE_FOR_TYPE[tag["type"]]
    items = _valid_items(obj, mode, _scene_set(scene, mode)) if scene.active is obj else []
    data = [list(e) for e in items] if mode == "edges" else list(items)
    update_tag(obj, index, selection=data)
    return len(items)


def restore_selection(scene, obj, index: int, how: str = "replace") -> int:
    tag = tag_at(obj, index)
    if tag is None or tag.get("type") not in SELECTION_TYPES:
        raise ValueError("not a selection tag")
    mode = MODE_FOR_TYPE[tag["type"]]
    items = selection_items(obj, tag)
    if obj not in scene.objects:
        return 0
    if scene.active is not obj:
        scene.set_active(obj)
    if scene.mode != mode:
        scene.set_mode(mode)
    target = _scene_set(scene, mode)
    before = set(target)
    if how == "add":
        target.update(items)
    elif how == "remove":
        target.difference_update(items)
    else:
        target.clear()
        target.update(items)
    if target != before:
        scene.selectionChanged.emit()
    return len(items)


def selection_tag_for_mode(mode: str) -> str | None:
    for t, m in MODE_FOR_TYPE.items():
        if m == mode:
            return t
    return None


def new_selection_tag(scene, obj=None) -> int | None:
    obj = scene.active if obj is None else obj
    if obj is None:
        return None
    tag_id = selection_tag_for_mode(scene.mode)
    if tag_id is None:
        return None
    index = add_tag(obj, tag_id, scene=scene)
    store_selection(scene, obj, index)
    return index


def selection_from_tag_name(obj, name: str, tag_id: str = "polygon_selection") -> set | None:
    if not name:
        return None
    found = find_tag_by_name(obj, name, tag_id)
    if found is None:
        return set()
    items = selection_items(obj, found[1])
    return {tuple(e) for e in items} if tag_id == "edge_selection" else set(items)


def serialize_tags(obj) -> Any:
    return store.to_json(get_tags(obj))


def deserialize_tags(obj, data: Any) -> None:
    tags = store.from_json(data) if data is not None else []
    set_tags(obj, [t for t in tags if isinstance(t, dict) and "type" in t])
