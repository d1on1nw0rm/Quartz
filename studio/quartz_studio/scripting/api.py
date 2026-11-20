from __future__ import annotations

import contextlib
import copy
import fnmatch
import math
import uuid
from collections import deque
from typing import Any, Callable, Iterable, Iterator

import numpy as np

from ..ext import store
from ..scene import EDITABLE_KIND, MODES, Mesh, Scene, SceneObject, get_scene

__all__ = [
    "API_VERSION",
    "ScriptError",
    "Mesh",
    "Scene",
    "SceneObject",
    "np",
    "document",
    "doc",
    "bind_scene",
    "objects",
    "iter_objects",
    "roots",
    "children",
    "descendants",
    "parent",
    "set_parent",
    "find",
    "find_all",
    "active_object",
    "set_active",
    "object_kinds",
    "kind_info",
    "create",
    "create_polygon_object",
    "duplicate",
    "delete",
    "rename",
    "make_editable",
    "set_enabled",
    "params",
    "get_param",
    "set_param",
    "position",
    "rotation",
    "scale",
    "set_position",
    "set_rotation",
    "set_scale",
    "set_transform",
    "move",
    "world_matrix",
    "world_position",
    "set_world_position",
    "mesh",
    "points",
    "set_points",
    "polygons",
    "set_polygons",
    "edges",
    "set_mesh",
    "point_count",
    "polygon_count",
    "polygon_normals",
    "bounds",
    "mode",
    "set_mode",
    "selected_objects",
    "select",
    "deselect",
    "selected_points",
    "selected_edges",
    "selected_polygons",
    "select_points",
    "select_edges",
    "select_polygons",
    "select_all",
    "selection",
    "all_selection",
    "tool_ids",
    "tool_info",
    "run_tool",
    "get_data",
    "set_data",
    "get_scene_data",
    "set_scene_data",
    "tags",
    "set_tags",
    "add_tag",
    "find_tags",
    "remove_tag",
    "update_tag",
    "add_python_tag",
    "materials",
    "find_material",
    "add_material",
    "assign_material",
    "unassign_material",
    "material_of",
    "tracks",
    "track_channels",
    "set_key",
    "remove_key",
    "clear_tracks",
    "track_value",
    "apply_tracks",
    "current_frame",
    "set_frame",
    "time_settings",
    "begin_undo",
    "end_undo",
    "undo_group",
    "suppress_undo",
    "is_undo_suppressed",
    "undo",
    "redo",
    "refresh",
    "update",
    "message",
    "log",
    "warn",
    "log_lines",
    "add_message_listener",
    "remove_message_listener",
]

API_VERSION = "1.0"

TRANSFORM_CHANNELS = ("position", "rotation", "scale")
AXES = "xyz"


class ScriptError(RuntimeError):
    pass


_BOUND: list[Scene] = []
_SUPPRESSED: dict[int, list] = {}
_MISSING = object()
_MESSAGE_LISTENERS: list[Callable[[str], None]] = []
_LOG: deque = deque(maxlen=1000)
INTERPOLATIONS = ("spline", "linear", "step")
_INTERP_ALIASES = {"smooth": "spline", "bezier": "spline", "spline": "spline", "linear": "linear",
                   "step": "step", "constant": "step"}
EASES = ("none", "in", "out", "both")
EXTRA_CHANNELS = ("visibility", "points")
TRACKS_KEY = "tracks"
TRACK_MODES_KEY = "track_modes"
FRAME_EPS = 1e-6
LEGACY_FRAME_KEYS = ("frame", "current_frame", "time")


def _anim():
    try:
        from ..anim import core as acore
    except Exception:
        return None
    return acore


def _materials():
    try:
        from ..materials import model as mmodel
        from ..materials import tags as mtags
    except Exception:
        return None
    return mmodel, mtags


def _tags_core():
    try:
        from ..tags import core as tcore
        from ..tags import registry as treg
    except Exception:
        return None
    return tcore, treg


def document() -> Scene:
    return _BOUND[-1] if _BOUND else get_scene()


doc = document


@contextlib.contextmanager
def bind_scene(scene: Scene | None) -> Iterator[Scene]:
    if scene is None:
        yield document()
        return
    _BOUND.append(scene)
    try:
        yield scene
    finally:
        _BOUND.pop()


def _sc(scene: Scene | None) -> Scene:
    return document() if scene is None else scene


def _record(scene: Scene, kind: str) -> None:
    if id(scene) in _SUPPRESSED:
        return
    rec = getattr(scene, "_record", None)
    if rec is not None:
        rec(kind)


def _no_record(kind: str = "") -> None:
    return None


def is_undo_suppressed(scene: Scene | None = None) -> bool:
    return id(_sc(scene)) in _SUPPRESSED


def _undo_mark(scene: Scene) -> tuple:
    return (len(getattr(scene, "_undo", ())), list(getattr(scene, "_redo", [])),
            getattr(scene, "_group_recorded", None))


def _undo_restore(scene: Scene, mark: tuple) -> None:
    stack = getattr(scene, "_undo", None)
    if stack is not None:
        while len(stack) > mark[0]:
            stack.pop()
    redo_ = getattr(scene, "_redo", None)
    if isinstance(redo_, list):
        redo_[:] = mark[1]
    if mark[2] is not None and hasattr(scene, "_group_recorded"):
        scene._group_recorded = mark[2]


def _write_object(obj: SceneObject, key: str, value: Any, scene: Scene | None = None) -> None:
    scene = _sc(scene)
    value = None if value is None else store.to_json(value)
    setter = getattr(scene, "set_object_extra", None)
    if setter is not None and obj in getattr(scene, "objects", ()):
        setter(obj, key, value)
    else:
        extras = store.object_extras(obj)
        if value is None:
            extras.pop(key, None)
        else:
            extras[key] = value
    store.notify(obj, key)


def _owner(obj: SceneObject, scene: Scene | None) -> Scene:
    scene = _sc(scene)
    if obj not in scene.objects:
        raise ScriptError(f"{getattr(obj, 'name', obj)!r} is not in the document")
    return scene


def _resolve(obj, scene: Scene | None = None) -> SceneObject:
    scene = _sc(scene)
    if obj is None:
        if scene.active is None:
            raise ScriptError("no active object")
        return scene.active
    if isinstance(obj, str):
        found = find(obj, scene)
        if found is None:
            raise ScriptError(f"no object named {obj!r}")
        return found
    return obj


def objects(scene: Scene | None = None) -> list[SceneObject]:
    return list(_sc(scene).objects)


def iter_objects(scene: Scene | None = None, kind: str | None = None) -> Iterator[SceneObject]:
    for o in list(_sc(scene).objects):
        if kind is None or o.kind == kind:
            yield o


def roots(scene: Scene | None = None) -> list[SceneObject]:
    return _sc(scene).roots()


def children(obj, scene: Scene | None = None) -> list[SceneObject]:
    scene = _sc(scene)
    return scene.children(None if obj is None else _resolve(obj, scene))


def descendants(obj, scene: Scene | None = None) -> list[SceneObject]:
    scene = _sc(scene)
    return scene.descendants(_resolve(obj, scene))


def parent(obj, scene: Scene | None = None) -> SceneObject | None:
    return _resolve(obj, scene).parent


def set_parent(obj, new_parent, index: int | None = None, scene: Scene | None = None) -> bool:
    scene = _sc(scene)
    obj = _resolve(obj, scene)
    target = None if new_parent is None else _resolve(new_parent, scene)
    _owner(obj, scene)
    if target is not None:
        _owner(target, scene)
        _inverse(target.world_matrix()[:3, :3], f"the new parent {target.name!r}")
    return bool(scene.set_parent(obj, target, index))


def find(name: str, scene: Scene | None = None) -> SceneObject | None:
    objs = _sc(scene).objects
    for o in objs:
        if o.name == name:
            return o
    low = str(name).lower()
    for o in objs:
        if o.name.lower() == low:
            return o
    return None


def find_all(pattern: str = "*", scene: Scene | None = None, kind: str | None = None) -> list[SceneObject]:
    pat = str(pattern).lower()
    return [o for o in _sc(scene).objects
            if fnmatch.fnmatchcase(o.name.lower(), pat) and (kind is None or o.kind == kind)]


def active_object(scene: Scene | None = None) -> SceneObject | None:
    return _sc(scene).active


def set_active(obj, scene: Scene | None = None) -> SceneObject | None:
    scene = _sc(scene)
    target = None if obj is None else _resolve(obj, scene)
    scene.set_active(target)
    return target


def _registry():
    from .. import objects as objpkg
    return objpkg.registry


def object_kinds(category: str | None = None) -> tuple[str, ...]:
    reg = _registry()
    if category is None:
        return (EDITABLE_KIND,) + tuple(s.id for s in reg.all_specs())
    return tuple(s.id for s in reg.by_category(category))


def kind_info(kind: str) -> dict:
    if kind == EDITABLE_KIND:
        return {"id": EDITABLE_KIND, "label": "Polygon Object", "category": "mesh", "params": []}
    spec = _registry().SPECS.get(kind)
    if spec is None:
        raise ScriptError(f"unknown object kind {kind!r}")
    return {
        "id": spec.id, "label": spec.label, "category": spec.category, "inputs": spec.inputs,
        "description": spec.description,
        "params": [{"key": p.key, "label": p.label, "kind": p.kind, "default": p.default,
                    "minimum": p.minimum, "maximum": p.maximum, "choices": list(p.choices)}
                   for p in spec.params],
    }


def _vec3(value, name: str) -> np.ndarray:
    arr = np.asarray(value, float).reshape(-1)
    if arr.size == 1:
        arr = np.repeat(arr, 3)
    if arr.size != 3 or not np.all(np.isfinite(arr)):
        raise ScriptError(f"{name} needs three finite numbers")
    return arr.astype(float)


def create(kind: str = "cube", name: str | None = None, parent=None, params: dict | None = None,
           position=None, rotation=None, scale=None, activate: bool = True,
           scene: Scene | None = None, **kw) -> SceneObject:
    scene = _sc(scene)
    values = dict(params or {})
    values.update(kw)
    target = None if parent is None else _resolve(parent, scene)
    if target is not None:
        _owner(target, scene)
    if kind == EDITABLE_KIND and values:
        raise ScriptError("polygon objects take no parameters")
    spec = None
    if kind != EDITABLE_KIND:
        spec = _registry().SPECS.get(kind)
        if spec is None:
            raise ScriptError(f"unknown object kind {kind!r}; see quartz.object_kinds()")
        values = {key: _checked_param(spec, kind, key, value) for key, value in values.items()}
    transform = {}
    if position is not None:
        transform["position"] = _vec3(position, "position")
    if rotation is not None:
        transform["rotation"] = _vec3(rotation, "rotation")
    if scale is not None:
        transform["scale"] = _vec3(scale, "scale")
    mark = _undo_mark(scene)
    prev_active, prev_selected = scene.active, scene.object_selected
    obj = None
    began = begin_undo(scene)
    try:
        if spec is None:
            obj = scene.add_object(name or "Polygon", Mesh.empty(), activate=activate)
            if target is not None:
                scene.set_parent(obj, target)
        else:
            obj = scene.add_parametric(kind, name, parent=target, activate=activate)
            for key, value in values.items():
                scene.set_param(obj, key, value)
        if transform:
            set_transform(obj, transform.get("position"), transform.get("rotation"),
                          transform.get("scale"), scene=scene)
    except BaseException as exc:
        _discard(scene, obj, mark, prev_active, prev_selected)
        if isinstance(exc, (KeyError, ValueError, TypeError)):
            raise ScriptError(f"could not create {kind!r}: {_exc_text(exc)}") from None
        raise
    finally:
        if began:
            end_undo(scene)
    return obj


def _exc_text(exc: BaseException) -> str:
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


def _checked_param(spec, kind: str, key: str, value: Any) -> Any:
    p = spec.param(key)
    if p is None:
        raise ScriptError(f"{kind!r} has no parameter {key!r}")
    try:
        p.clamp(value)
    except (TypeError, ValueError) as exc:
        raise ScriptError(f"bad value {value!r} for {kind}.{key}: {_exc_text(exc)}") from None
    return value


def _discard(scene: Scene, obj, mark, prev_active, prev_selected) -> None:
    with suppress_undo(scene):
        if obj is not None and obj in scene.objects:
            scene.remove_object(obj)
        if prev_active is not None and prev_active in scene.objects:
            scene.set_active(prev_active, select=prev_selected)
    _undo_restore(scene, mark)


def create_polygon_object(name: str, points_, polygons_=(), loose_edges=(), parent=None,
                          position=None, activate: bool = True,
                          scene: Scene | None = None) -> SceneObject:
    scene = _sc(scene)
    m = _checked_mesh(points_, polygons_, loose_edges)
    target = None if parent is None else _resolve(parent, scene)
    if target is not None:
        _owner(target, scene)
    pos = None if position is None else _vec3(position, "position")
    began = begin_undo(scene)
    try:
        obj = scene.add_object(name, m, activate=activate)
        if target is not None:
            scene.set_parent(obj, target)
        if pos is not None:
            set_position(obj, pos, scene=scene)
    finally:
        if began:
            end_undo(scene)
    return obj


def _checked_mesh(points_, polygons_, loose_edges=()) -> Mesh:
    pts = np.asarray(points_, float).reshape(-1, 3)
    if not np.all(np.isfinite(pts)):
        raise ScriptError("points must be finite")
    n = len(pts)
    polys = [tuple(int(i) for i in p) for p in polygons_]
    for p in polys:
        if len(p) < 3:
            raise ScriptError(f"polygon {p} needs at least three points")
        if len(set(p)) != len(p):
            raise ScriptError(f"polygon {p} repeats a point")
        if any(i < 0 or i >= n for i in p):
            raise ScriptError(f"polygon {p} uses a point index outside 0..{n - 1}")
    loose = [tuple(int(i) for i in e) for e in loose_edges]
    for e in loose:
        if len(e) != 2 or any(i < 0 or i >= n for i in e):
            raise ScriptError(f"edge {e} is invalid")
    return Mesh(pts, polys, loose)


def _clone_node(src: SceneObject, name: str | None = None) -> SceneObject:
    m = src.mesh
    scales = m.point_scales
    new = SceneObject(name or src.name,
                      Mesh(m.points.copy(), list(m.polygons), list(m.loose_edges),
                           point_scales=None if scales is None else np.array(scales, float)),
                      src.kind, copy.deepcopy(src.params))
    new.position = src.position.copy()
    new.rotation = src.rotation.copy()
    new.scale = src.scale.copy()
    new.enabled = src.enabled
    new.extras = copy.deepcopy(store.object_extras(src))
    if hasattr(new, "_dirty"):
        new._dirty = src.kind != EDITABLE_KIND
    return new


def duplicate(obj, name: str | None = None, scene: Scene | None = None,
              children: bool = True, activate: bool = True) -> SceneObject:
    scene = _sc(scene)
    src = _resolve(obj, scene)
    _owner(src, scene)
    nodes = [src] + (scene.descendants(src) if children else [])
    index = {id(o): i for i, o in enumerate(nodes)}
    copies = [_clone_node(o, name if i == 0 else None) for i, o in enumerate(nodes)]
    parents = [None] + [index.get(id(o.parent)) for o in nodes[1:]]
    root = copies[0]
    began = begin_undo(scene)
    try:
        scene.insert_objects(copies, parents, activate=False)
        siblings = [o for o in scene.children(src.parent) if o is not root]
        pos = siblings.index(src) + 1 if src in siblings else None
        scene.set_parent(root, src.parent, pos)
        root.position = src.position.copy()
        root.rotation = src.rotation.copy()
        root.scale = src.scale.copy()
        if activate:
            scene.set_active(root)
        scene.changed.emit()
    finally:
        if began:
            end_undo(scene)
    return root


def delete(obj, scene: Scene | None = None) -> None:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    _owner(target, scene)
    scene.remove_object(target)


def rename(obj, name: str, scene: Scene | None = None) -> SceneObject:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    scene.rename_object(target, str(name))
    return target


def make_editable(obj=None, scene: Scene | None = None) -> SceneObject:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    _owner(target, scene)
    extras = copy.deepcopy(store.object_extras(target))
    new = scene.make_editable(target)
    if new is not target and extras and not store.object_extras(new):
        for key, value in extras.items():
            store.set_object(new, key, value)
    return new


def set_enabled(obj, flag: bool, scene: Scene | None = None) -> None:
    scene = _sc(scene)
    scene.set_enabled(_resolve(obj, scene), bool(flag))


def params(obj=None, scene: Scene | None = None) -> dict:
    return copy.deepcopy(_resolve(obj, scene).params)


def get_param(obj, key: str, default: Any = None, scene: Scene | None = None) -> Any:
    return copy.deepcopy(_resolve(obj, scene).params.get(key, default))


def set_param(obj, key: str, value: Any, scene: Scene | None = None) -> bool:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    try:
        return bool(scene.set_param(target, key, value))
    except (KeyError, ValueError, TypeError) as exc:
        raise ScriptError(_exc_text(exc)) from None


def position(obj=None, scene: Scene | None = None) -> np.ndarray:
    return _resolve(obj, scene).position.copy()


def rotation(obj=None, scene: Scene | None = None) -> np.ndarray:
    return _resolve(obj, scene).rotation.copy()


def scale(obj=None, scene: Scene | None = None) -> np.ndarray:
    return _resolve(obj, scene).scale.copy()


def set_transform(obj, position=None, rotation=None, scale=None,
                  scene: Scene | None = None) -> SceneObject:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    _owner(target, scene)
    new = {}
    if position is not None:
        new["position"] = _vec3(position, "position")
    if rotation is not None:
        new["rotation"] = _vec3(rotation, "rotation")
    if scale is not None:
        new["scale"] = _vec3(scale, "scale")
    if all(np.array_equal(getattr(target, k), v) for k, v in new.items()):
        return target
    _record(scene, "script:transform")
    for k, v in new.items():
        setattr(target, k, v)
    scene.changed.emit()
    return target


def set_position(obj, value, scene: Scene | None = None) -> SceneObject:
    return set_transform(obj, position=value, scene=scene)


def set_rotation(obj, value, scene: Scene | None = None) -> SceneObject:
    return set_transform(obj, rotation=value, scene=scene)


def set_scale(obj, value, scene: Scene | None = None) -> SceneObject:
    return set_transform(obj, scale=value, scene=scene)


def move(obj, delta, scene: Scene | None = None) -> SceneObject:
    target = _resolve(obj, scene)
    return set_transform(target, position=target.position + _vec3(delta, "delta"), scene=scene)


def world_matrix(obj=None, scene: Scene | None = None) -> np.ndarray:
    return _resolve(obj, scene).world_matrix()


def world_position(obj=None, scene: Scene | None = None) -> np.ndarray:
    return _resolve(obj, scene).world_position()


def set_world_position(obj, value, scene: Scene | None = None) -> SceneObject:
    target = _resolve(obj, scene)
    world = _vec3(value, "position")
    pm = target.parent_matrix()
    inv = _inverse(pm[:3, :3], f"the parent of {target.name!r}")
    local = inv @ (world - pm[:3, 3])
    return set_transform(target, position=local, scene=scene)


def _inverse(m: np.ndarray, what: str) -> np.ndarray:
    m = np.asarray(m, float)
    if not np.all(np.isfinite(m)) or not np.abs(m).max() > 0 or np.linalg.cond(m) > 1e12:
        raise ScriptError(f"{what} has a singular transform (zero scale); world space is undefined")
    try:
        inv = np.linalg.inv(m)
    except np.linalg.LinAlgError:
        raise ScriptError(f"{what} has a singular transform (zero scale); world space is undefined") from None
    if not np.all(np.isfinite(inv)):
        raise ScriptError(f"{what} has a singular transform (zero scale); world space is undefined")
    return inv


def mesh(obj=None, scene: Scene | None = None) -> Mesh:
    return _resolve(obj, scene).mesh


def _editable(obj, scene: Scene | None) -> tuple[SceneObject, Scene]:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    _owner(target, scene)
    if target.kind != EDITABLE_KIND:
        raise ScriptError(f"{target.name!r} is a {target.kind} object; call quartz.make_editable first")
    return target, scene


def points(obj=None, world: bool = False, scene: Scene | None = None) -> np.ndarray:
    target = _resolve(obj, scene)
    return target.world_points() if world else target.mesh.points.copy()


def set_points(obj, values, world: bool = False, scene: Scene | None = None) -> SceneObject:
    target, scene = _editable(obj, scene)
    arr = np.asarray(values, float).reshape(-1, 3)
    if len(arr) != len(target.mesh.points):
        raise ScriptError(f"expected {len(target.mesh.points)} points, got {len(arr)}")
    if not np.all(np.isfinite(arr)):
        raise ScriptError("points must be finite")
    if world:
        m = target.world_matrix()
        arr = (arr - m[:3, 3]) @ _inverse(m[:3, :3], repr(target.name)).T
    if np.array_equal(arr, target.mesh.points):
        return target
    _record(scene, "script:points")
    target.mesh.points = arr.copy()
    scene.changed.emit()
    return target


def polygons(obj=None, scene: Scene | None = None) -> list[tuple[int, ...]]:
    return list(_resolve(obj, scene).mesh.polygons)


def edges(obj=None, scene: Scene | None = None) -> list[tuple[int, int]]:
    return list(_resolve(obj, scene).mesh.edges)


def set_mesh(obj, new_mesh: Mesh, scene: Scene | None = None) -> SceneObject:
    target, scene = _editable(obj, scene)
    checked = _checked_mesh(new_mesh.points, new_mesh.polygons, new_mesh.loose_edges)
    if new_mesh.point_scales is not None:
        checked.point_scales = new_mesh.point_scales
    _record(scene, "script:mesh")
    target.mesh = checked
    if target is scene.active:
        _clip_selection(scene)
    scene.changed.emit()
    scene.selectionChanged.emit()
    return target


def set_polygons(obj, values, loose_edges=None, scene: Scene | None = None) -> SceneObject:
    target, scene = _editable(obj, scene)
    loose = target.mesh.loose_edges if loose_edges is None else loose_edges
    return set_mesh(target, _checked_mesh(target.mesh.points, values, loose), scene=scene)


def point_count(obj=None, scene: Scene | None = None) -> int:
    return int(len(_resolve(obj, scene).mesh.points))


def polygon_count(obj=None, scene: Scene | None = None) -> int:
    return int(len(_resolve(obj, scene).mesh.polygons))


def polygon_normals(obj=None, scene: Scene | None = None) -> np.ndarray:
    return _resolve(obj, scene).mesh.polygon_normals()


def bounds(obj=None, world: bool = True, scene: Scene | None = None) -> tuple[np.ndarray, np.ndarray]:
    target = _resolve(obj, scene)
    pts = target.world_points() if world else target.mesh.points
    if len(pts) == 0:
        origin = target.world_position() if world else np.zeros(3)
        return origin.copy(), origin.copy()
    return pts.min(axis=0), pts.max(axis=0)


def _clip_selection(scene: Scene) -> None:
    obj = scene.active
    if obj is None:
        return
    m = obj.mesh
    valid = set(m.edges)
    scene.selected_points = {i for i in scene.selected_points if 0 <= i < len(m.points)}
    scene.selected_edges = {e for e in scene.selected_edges if e in valid}
    scene.selected_polygons = {i for i in scene.selected_polygons if 0 <= i < len(m.polygons)}


def mode(scene: Scene | None = None) -> str:
    return _sc(scene).mode


def set_mode(value: str, scene: Scene | None = None) -> str:
    if value not in MODES:
        raise ScriptError(f"mode must be one of {', '.join(MODES)}")
    scene = _sc(scene)
    scene.set_mode(value)
    return scene.mode


def selected_objects(scene: Scene | None = None) -> list[SceneObject]:
    return _sc(scene).selected_objects()


def select(obj, scene: Scene | None = None) -> SceneObject:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    scene.set_active(target, select=True)
    return target


def deselect(scene: Scene | None = None) -> None:
    scene = _sc(scene)
    if scene.mode == "model":
        scene.select_object(False)
    else:
        scene.clear_selection()


def selected_points(scene: Scene | None = None) -> list[int]:
    return sorted(_sc(scene).selected_points)


def selected_edges(scene: Scene | None = None) -> list[tuple[int, int]]:
    return sorted(_sc(scene).selected_edges)


def selected_polygons(scene: Scene | None = None) -> list[int]:
    return sorted(_sc(scene).selected_polygons)


def _select_components(kind: str, items, obj, add: bool, scene: Scene | None) -> int:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    if target.kind != EDITABLE_KIND:
        raise ScriptError(f"{target.name!r} is not editable; call quartz.make_editable first")
    if scene.active is not target:
        scene.set_active(target)
    scene.set_mode(kind)
    m = target.mesh
    if kind == "points":
        norm = [int(i) for i in items]
        bad = [i for i in norm if not 0 <= i < len(m.points)]
    elif kind == "polygons":
        norm = [int(i) for i in items]
        bad = [i for i in norm if not 0 <= i < len(m.polygons)]
    else:
        valid = set(m.edges)
        norm = [tuple(sorted((int(e[0]), int(e[1])))) for e in items]
        bad = [e for e in norm if e not in valid]
    if bad:
        raise ScriptError(f"invalid {kind}: {bad[:8]}")
    scene.select_components(norm, add=add)
    return len(scene._component_set(kind))


def select_points(indices: Iterable[int], obj=None, add: bool = False, scene: Scene | None = None) -> int:
    return _select_components("points", indices, obj, add, scene)


def select_edges(items: Iterable, obj=None, add: bool = False, scene: Scene | None = None) -> int:
    return _select_components("edges", items, obj, add, scene)


def select_polygons(indices: Iterable[int], obj=None, add: bool = False, scene: Scene | None = None) -> int:
    return _select_components("polygons", indices, obj, add, scene)


def select_all(kind: str | None = None, obj=None, scene: Scene | None = None) -> int:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    kind = kind or (scene.mode if scene.mode != "model" else "polygons")
    m = target.mesh
    items = {"points": range(len(m.points)), "edges": list(m.edges),
             "polygons": range(len(m.polygons))}.get(kind)
    if items is None:
        raise ScriptError("select_all needs points, edges or polygons")
    return _select_components(kind, items, target, False, scene)


def _selection_types():
    from ..modeling.meshkit import Selection
    return Selection


def selection(scene: Scene | None = None):
    scene = _sc(scene)
    Selection = _selection_types()
    return Selection(scene.mode, set(scene.selected_points), set(scene.selected_edges),
                     set(scene.selected_polygons))


def all_selection(obj=None, kind: str = "polygons", scene: Scene | None = None):
    target = _resolve(obj, scene)
    Selection = _selection_types()
    m = target.mesh
    if kind == "points":
        return Selection("points", points=set(range(len(m.points))))
    if kind == "edges":
        return Selection("edges", edges=set(m.edges))
    if kind == "polygons":
        return Selection("polygons", polygons=set(range(len(m.polygons))))
    if kind == "model":
        return Selection("model")
    raise ScriptError(f"unknown selection kind {kind!r}")


def _as_selection(value, target: SceneObject, scene: Scene, tool_modes: tuple):
    Selection = _selection_types()
    if value is None:
        if target is scene.active and (scene.mode != "model" or "model" in tool_modes):
            return selection(scene)
        value = "all"
    if isinstance(value, Selection):
        return value.copy()
    if isinstance(value, str):
        if value == "all":
            kind = next((k for k in ("polygons", "edges", "points") if k in tool_modes), "model")
            return all_selection(target, kind, scene)
        return all_selection(target, value, scene)
    if isinstance(value, dict):
        kind = value.get("mode")
        if kind is None:
            kind = next((k for k in ("polygons", "edges", "points") if value.get(k)), "model")
        return Selection(kind,
                         {int(i) for i in value.get("points", ())},
                         {tuple(sorted((int(e[0]), int(e[1])))) for e in value.get("edges", ())},
                         {int(i) for i in value.get("polygons", ())})
    raise ScriptError("selection must be None, 'all', a mode name, a dict or a Selection")


def tool_ids() -> tuple[str, ...]:
    from ..modeling import registry as mreg
    return mreg.tool_ids()


def tool_info(tool_id: str) -> dict:
    from ..modeling import registry as mreg
    try:
        spec = mreg.get_tool(tool_id)
    except KeyError:
        raise ScriptError(f"unknown tool {tool_id!r}") from None
    return {
        "id": spec.id, "name": spec.name, "modes": list(spec.modes), "menu": spec.menu,
        "description": spec.description,
        "params": [{"key": p.key, "label": p.label, "kind": p.kind, "default": p.default}
                   for p in spec.params if p.kind != "runtime"],
    }


def run_tool(tool_id: str, params: dict | None = None, obj=None, selection=None,
             scene: Scene | None = None):
    from ..modeling import registry as mreg
    from ..modeling.meshkit import carry_point_scales, clone
    scene = _sc(scene)
    target, scene = _editable(obj, scene)
    try:
        spec = mreg.get_tool(tool_id)
    except KeyError:
        raise ScriptError(f"unknown tool {tool_id!r}; see quartz.tool_ids()") from None
    values = dict(params or {})
    usable = [p.key for p in spec.params if p.kind != "runtime"]
    for key, value in values.items():
        p = spec.param(key)
        if p is None:
            raise ScriptError(f"tool {tool_id!r} has no parameter {key!r}; it takes "
                              f"{', '.join(usable) if usable else 'no parameters'}")
        try:
            p.clamp(value)
        except (TypeError, ValueError) as exc:
            raise ScriptError(f"bad value {value!r} for {tool_id}.{key}: {_exc_text(exc)}") from None
    sel = _as_selection(selection, target, scene, spec.modes)
    base = clone(target.mesh)
    result = mreg.run_tool(tool_id, clone(base), sel, values)
    if not result.ok:
        return result
    _record(scene, "modeling")
    target.mesh = carry_point_scales(base, result.mesh)
    if target is scene.active:
        res = result.selection
        n_pts, n_polys = len(target.mesh.points), len(target.mesh.polygons)
        valid = set(target.mesh.edges)
        scene.selected_points = {int(i) for i in res.points if 0 <= int(i) < n_pts}
        scene.selected_edges = {tuple(sorted((int(e[0]), int(e[1])))) for e in res.edges
                                if tuple(sorted((int(e[0]), int(e[1])))) in valid}
        scene.selected_polygons = {int(i) for i in res.polygons if 0 <= int(i) < n_polys}
        if res.mode in ("points", "edges", "polygons") and res.mode != scene.mode:
            scene.set_mode(res.mode)
    scene.changed.emit()
    scene.selectionChanged.emit()
    return result


def get_data(obj, key: str, default: Any = None, scene: Scene | None = None) -> Any:
    return copy.deepcopy(store.get_object(_resolve(obj, scene), key, default))


def set_data(obj, key: str, value: Any, scene: Scene | None = None) -> None:
    scene = _sc(scene)
    _write_object(_resolve(obj, scene), str(key), copy.deepcopy(value), scene)


def get_scene_data(key: str, default: Any = None, scene: Scene | None = None) -> Any:
    return copy.deepcopy(store.get_scene_data(_sc(scene), key, default))


def set_scene_data(key: str, value: Any, scene: Scene | None = None) -> None:
    store.set_scene_data(_sc(scene), str(key), copy.deepcopy(value))


def tags(obj=None, scene: Scene | None = None) -> list[dict]:
    value = store.get_object(_resolve(obj, scene), "tags", [])
    return copy.deepcopy(value) if isinstance(value, list) else []


def _tag_spec(tag_type: str):
    pair = _tags_core()
    if pair is None:
        return None
    return pair[1].TAG_SPECS.get(str(tag_type))


def set_tags(obj, values: list, scene: Scene | None = None) -> None:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    clean = []
    for t in values:
        if not isinstance(t, dict) or not t.get("type"):
            raise ScriptError("every tag must be a dict with a 'type'")
        clean.append(copy.deepcopy(t))
    pair = _tags_core()
    if pair is not None and target in scene.objects:
        try:
            pair[0].set_tags(target, clean, scene=scene)
        except (TypeError, ValueError, KeyError) as exc:
            raise ScriptError(f"bad tag data: {_exc_text(exc)}") from None
        return
    _write_object(target, "tags", clean if clean else None, scene)


def add_tag(obj, tag_type: str, name: str | None = None, scene: Scene | None = None, **fields) -> dict:
    if not tag_type:
        raise ScriptError("tag type is required")
    scene = _sc(scene)
    target = _resolve(obj, scene)
    tag_type = str(tag_type)
    spec = _tag_spec(tag_type)
    current = tags(target, scene)
    if spec is not None:
        if spec.unique and any(t.get("type") == tag_type for t in current):
            raise ScriptError(f"{target.name!r} already has a {spec.label} tag and it can only have one")
        tcore, treg = _tags_core()
        label = name or spec.label
        try:
            tag = treg.make_tag(tag_type, tcore.unique_tag_name(target, label), **copy.deepcopy(fields))
        except (KeyError, TypeError, ValueError) as exc:
            raise ScriptError(f"bad {tag_type} tag: {_exc_text(exc)}") from None
        if spec.on_create is not None:
            try:
                spec.on_create(scene, target, tag)
            except Exception:
                pass
    else:
        tag = {"type": tag_type, "name": name or tag_type.replace("_", " ").title(), "enabled": True}
        tag.update(copy.deepcopy(fields))
    current.append(tag)
    set_tags(target, current, scene=scene)
    return copy.deepcopy(tags(target, scene)[-1])


def find_tags(obj=None, tag_type: str | None = None, scene: Scene | None = None) -> list[dict]:
    return [t for t in tags(obj, scene) if tag_type is None or t.get("type") == tag_type]


def remove_tag(obj, which, scene: Scene | None = None) -> int:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    current = tags(target, scene)
    if isinstance(which, bool):
        raise ScriptError("remove_tag needs an index, a tag dict, a type or a name")
    if isinstance(which, int):
        if not -len(current) <= which < len(current):
            raise ScriptError(f"no tag at index {which}")
        keep = [t for i, t in enumerate(current) if i != which % len(current)]
    elif isinstance(which, dict):
        keep = list(current)
        for i, t in enumerate(keep):
            if t == which:
                del keep[i]
                break
    else:
        keep = [t for t in current if t.get("type") != which and t.get("name") != which]
    removed = len(current) - len(keep)
    if removed:
        set_tags(target, keep, scene=scene)
    return removed


def update_tag(obj, index: int, scene: Scene | None = None, **fields) -> dict:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    current = tags(target, scene)
    if not -len(current) <= index < len(current):
        raise ScriptError(f"no tag at index {index}")
    spec = _tag_spec(current[index].get("type", ""))
    if spec is not None:
        for key, value in fields.items():
            p = spec.param(key)
            if p is None and key not in ("name", "enabled"):
                raise ScriptError(f"{spec.label} tags have no parameter {key!r}")
            if p is not None:
                try:
                    p.clamp(value)
                except (TypeError, ValueError) as exc:
                    raise ScriptError(f"bad value {value!r} for {spec.id}.{key}: {_exc_text(exc)}") from None
    current[index].update(copy.deepcopy(fields))
    set_tags(target, current, scene=scene)
    return copy.deepcopy(tags(target, scene)[index])


def add_python_tag(obj, code: str, name: str = "Python", scene: Scene | None = None,
                   priority: str | None = None) -> dict:
    compile(code, f"<python tag {name}>", "exec")
    fields = {"code": str(code)}
    if priority is not None:
        fields["priority"] = str(priority)
    return add_tag(obj, "python", name=name, scene=scene, **fields)


def _library(scene: Scene) -> list[dict]:
    value = store.get_scene_data(scene, "materials", [])
    if isinstance(value, dict):
        return [dict(v, name=k) if isinstance(v, dict) else {"name": k} for k, v in value.items()]
    return [m for m in value if isinstance(m, dict)] if isinstance(value, list) else []


def materials(scene: Scene | None = None) -> list[dict]:
    return copy.deepcopy(_library(_sc(scene)))


def find_material(material, scene: Scene | None = None) -> dict | None:
    scene = _sc(scene)
    if isinstance(material, dict):
        material = material.get("id") or material.get("name")
    if not material:
        return None
    lib = _library(scene)
    key = str(material)
    for m in lib:
        if m.get("id") == key:
            return copy.deepcopy(m)
    for m in lib:
        if m.get("name") == key:
            return copy.deepcopy(m)
    low = key.lower()
    for m in lib:
        if str(m.get("name", "")).lower() == low:
            return copy.deepcopy(m)
    return None


def _material_color(mat: dict) -> list[float] | None:
    ch = mat.get("channels", {}).get("base_color") if isinstance(mat.get("channels"), dict) else None
    if isinstance(ch, dict) and "value" in ch:
        return [float(c) for c in ch["value"]]
    if "color" in mat:
        return [float(c) for c in mat["color"]]
    return None


def _apply_material_props(mm, mat: dict, color, props: dict) -> None:
    if color is not None:
        rgb = [float(min(1.0, max(0.0, c))) for c in _vec3(color, "color")]
        mm.set_channel(mat, "base_color", "value", rgb)
    for key, value in props.items():
        if key in mm.CHANNEL_KEYS:
            spec = mm.channel_spec(key)
            fields = dict(value) if isinstance(value, dict) else {"value": value}
            if spec.optional and "enabled" not in fields:
                fields["enabled"] = True
            for field_name, v in fields.items():
                try:
                    mm.set_channel(mat, key, field_name, v)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ScriptError(f"bad material value for {key}.{field_name}: {_exc_text(exc)}") from None
        elif key == "preview":
            mat["preview"] = str(value)
        else:
            raise ScriptError(f"materials have no property {key!r}; channels are {', '.join(mm.CHANNEL_KEYS)}")


def add_material(name: str, color=None, scene: Scene | None = None, preset: str | None = None,
                 activate: bool = False, **props) -> dict:
    scene = _sc(scene)
    name = str(name).strip()
    if not name:
        raise ScriptError("material name is required")
    pair = _materials()
    if pair is None:
        rgb = [float(min(1.0, max(0.0, c))) for c in _vec3((0.8, 0.8, 0.8) if color is None else color, "color")]
        mat = {"id": f"mat_{uuid.uuid4().hex[:12]}", "name": name, "color": rgb}
        mat.update(copy.deepcopy(props))
        current = [m for m in _library(scene) if m.get("name") != name]
        current.append(mat)
        store.set_scene_data(scene, "materials", current)
        return copy.deepcopy(mat)
    mm = pair[0]
    existing = next((m for m in _library(scene) if m.get("name") == name), None)
    if preset is not None:
        try:
            mat = mm.preset_material(str(preset))
        except KeyError:
            raise ScriptError(f"unknown material preset {preset!r}; presets are {', '.join(mm.PRESETS)}") from None
        mat["name"] = name
        if existing is not None:
            mat["id"] = existing["id"]
    elif existing is not None:
        mat = copy.deepcopy(existing)
    else:
        mat = mm.new_material("pbr", name)
    _apply_material_props(mm, mat, color, props)
    began = begin_undo(scene)
    try:
        if existing is not None:
            mat = mm.update_material(scene, mat)
            if activate:
                mm.set_active_material(scene, mat["id"])
        else:
            mat = mm.add_material(scene, mat, activate)
    finally:
        if began:
            end_undo(scene)
    return copy.deepcopy(mat)


def _material_tag(mid: str, fields: dict) -> dict:
    pair = _materials()
    if pair is not None:
        mtags = pair[1]
        tag = mtags.new_material_tag(mid)
        try:
            tag.update(mtags._clean_fields(fields))
        except (KeyError, TypeError, ValueError) as exc:
            raise ScriptError(f"bad material tag field: {_exc_text(exc)}") from None
    else:
        tag = {"type": "material", "selection": ""}
        tag.update(copy.deepcopy(fields))
    tag["material"] = str(mid)
    return tag


def assign_material(obj, material, selection: str = "", scene: Scene | None = None, **fields) -> dict:
    scene = _sc(scene)
    mat = find_material(material, scene)
    if mat is None:
        raise ScriptError(f"no material named {material!r}; see quartz.materials()")
    mid = mat.get("id") or mat.get("name")
    target = _resolve(obj, scene)
    _owner(target, scene)
    selection = str(selection or "")
    current = tags(target, scene)
    tag = _material_tag(mid, dict(fields, selection=selection))
    for i in range(len(current) - 1, -1, -1):
        t = current[i]
        if t.get("type") == "material" and str(t.get("selection", "") or "") == selection:
            merged = dict(t)
            merged.update(tag)
            current[i] = merged
            tag = merged
            break
    else:
        current.append(tag)
    _write_object(target, "tags", current, scene)
    return copy.deepcopy(tag)


def unassign_material(obj, material=None, scene: Scene | None = None) -> int:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    mid = None
    if material is not None:
        mat = find_material(material, scene)
        if mat is None:
            return 0
        mid = mat.get("id") or mat.get("name")
    current = tags(target, scene)
    keep = [t for t in current if not (t.get("type") == "material" and (mid is None or t.get("material") == mid))]
    removed = len(current) - len(keep)
    if removed:
        _write_object(target, "tags", keep if keep else None, scene)
    return removed


def material_of(obj=None, polygon: int | None = None, scene: Scene | None = None) -> dict | None:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    pair = _materials()
    if pair is not None:
        mid = pair[1].effective_material_id(scene, target, polygon)
        return find_material(mid, scene) if mid else None
    node = target
    while node is not None:
        for t in reversed(tags(node, scene)):
            if t.get("type") == "material" and t.get("enabled", True) and not t.get("selection"):
                found = find_material(t.get("material"), scene)
                if found is not None:
                    return found
        node = node.parent
    return None


def _check_target(target: str, obj: SceneObject | None = None) -> str:
    target = str(target)
    head, _, tail = target.partition(".")
    if head in TRANSFORM_CHANNELS and tail in AXES and tail:
        return target
    if target in EXTRA_CHANNELS:
        return target
    if head == "param" and tail:
        if obj is not None:
            spec = _registry().SPECS.get(obj.kind)
            if spec is None or spec.param(tail) is None:
                raise ScriptError(f"{obj.name!r} has no parameter {tail!r} to animate")
        return target
    raise ScriptError(f"track target {target!r} must be position|rotation|scale.x|y|z, "
                      f"visibility, points or param.<key>")


def _interp_name(value: str | None) -> str | None:
    if value is None:
        return None
    name = _INTERP_ALIASES.get(str(value).lower())
    if name is None:
        raise ScriptError("interpolation must be spline (smooth), linear or step")
    return name


def _legacy_tracks(value: list) -> dict:
    out: dict = {}
    for t in value:
        if not isinstance(t, dict) or not t.get("target"):
            continue
        keys = []
        for k in t.get("keys", []):
            if not isinstance(k, dict) or "frame" not in k:
                continue
            interp = _INTERP_ALIASES.get(str(k.get("interpolation", k.get("interp", "linear"))), "linear")
            keys.append({"frame": float(k["frame"]), "value": k.get("value"), "interp": interp,
                         "in_tan": None, "out_tan": None, "ease": "none"})
        if keys:
            out[str(t["target"])] = sorted(keys, key=lambda k: k["frame"])
    return out


def _normalize_key(key: dict) -> dict:
    ac = _anim()
    norm = getattr(ac, "_normalize_key", None) if ac is not None else None
    if norm is not None:
        return norm(key)
    out = copy.deepcopy(key)
    out["frame"] = float(out.get("frame", 0.0))
    out.setdefault("interp", "spline")
    out.setdefault("ease", "none")
    out.setdefault("in_tan", None)
    out.setdefault("out_tan", None)
    return out


def _raw_tracks(obj: SceneObject) -> dict:
    value = store.get_object(obj, TRACKS_KEY, None)
    if isinstance(value, list):
        return _legacy_tracks(value)
    if not isinstance(value, dict):
        return {}
    return {str(ch): [_normalize_key(k) for k in keys if isinstance(k, dict)]
            for ch, keys in value.items() if isinstance(keys, list)}


def tracks(obj=None, scene: Scene | None = None) -> dict:
    return copy.deepcopy(_raw_tracks(_resolve(obj, scene)))


def track_channels(obj=None, scene: Scene | None = None) -> list[str]:
    data = _raw_tracks(_resolve(obj, scene))
    ac = _anim()
    chans = [ch for ch, keys in data.items() if keys]
    if ac is not None:
        return sorted(chans, key=ac.channel_sort_key)
    return sorted(chans)


def _write_tracks(obj: SceneObject, data: dict, scene: Scene) -> None:
    clean = {ch: keys for ch, keys in data.items() if keys}
    began = begin_undo(scene)
    try:
        _write_object(obj, TRACKS_KEY, clean if clean else None, scene)
        modes = store.get_object(obj, TRACK_MODES_KEY, None)
        if isinstance(modes, dict) and any(ch not in clean for ch in modes):
            kept = {ch: m for ch, m in modes.items() if ch in clean}
            _write_object(obj, TRACK_MODES_KEY, kept if kept else None, scene)
    finally:
        if began:
            end_undo(scene)


def _channel_value(obj: SceneObject, channel: str) -> Any:
    ac = _anim()
    if ac is not None:
        return ac.channel_value(obj, channel)
    head, _, tail = channel.partition(".")
    if head in TRANSFORM_CHANNELS and tail in AXES:
        return float(getattr(obj, head)[AXES.index(tail)])
    if channel == "visibility":
        return 1.0 if obj.enabled else 0.0
    if channel == "points":
        return obj.mesh.points.copy()
    if head == "param":
        return copy.deepcopy(obj.params.get(tail))
    return None


def _checked_key_value(obj: SceneObject, channel: str, value: Any) -> Any:
    head, _, tail = channel.partition(".")
    if head in TRANSFORM_CHANNELS or channel == "visibility":
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ScriptError(f"{channel} keys need a number, got {value!r}") from None
        if not math.isfinite(v):
            raise ScriptError(f"{channel} keys need a finite number")
        return v
    if channel == "points":
        arr = np.asarray(value, float)
        if arr.shape != obj.mesh.points.shape or not np.all(np.isfinite(arr)):
            raise ScriptError(f"points keys need a finite {len(obj.mesh.points)}x3 array")
        return arr
    spec = _registry().SPECS.get(obj.kind)
    p = spec.param(tail) if spec is not None else None
    if p is not None:
        try:
            p.clamp(value)
        except (TypeError, ValueError) as exc:
            raise ScriptError(f"bad value {value!r} for {obj.kind}.{tail}: {_exc_text(exc)}") from None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    return copy.deepcopy(value)


def _default_interp(scene: Scene, channel: str, value: Any) -> str:
    if channel == "visibility":
        return "step"
    if channel == "points":
        return "linear"
    if not isinstance(value, (int, float, np.ndarray)) or isinstance(value, bool):
        return "step"
    ac = _anim()
    if ac is not None:
        return ac.time_settings(scene)["default_interp"]
    return "spline"


def _make_key(frame: float, value: Any, interp: str, ease: str) -> dict:
    ac = _anim()
    if ac is not None:
        return ac.make_key(frame, value, interp, ease)
    return {"frame": float(frame), "value": value, "interp": interp, "in_tan": None,
            "out_tan": None, "ease": ease}


def set_key(obj, target: str, frame: float | None = None, value: Any = None,
            interpolation: str | None = None, ease: str | None = None,
            scene: Scene | None = None) -> dict:
    scene = _sc(scene)
    target_obj = _resolve(obj, scene)
    channel = _check_target(target, target_obj)
    interp = _interp_name(interpolation)
    if ease is not None and ease not in EASES:
        raise ScriptError(f"ease must be one of {', '.join(EASES)}")
    f = current_frame(scene) if frame is None else float(frame)
    if not math.isfinite(f):
        raise ScriptError("frame must be finite")
    if value is None:
        value = _channel_value(target_obj, channel)
        if value is None:
            raise ScriptError(f"{target_obj.name!r} has no value for {channel}")
    value = _checked_key_value(target_obj, channel, value)
    data = _raw_tracks(target_obj)
    keys = data.setdefault(channel, [])
    hit = next((k for k in keys if abs(float(k["frame"]) - f) < FRAME_EPS), None)
    if hit is not None:
        hit["value"] = _make_key(f, value, "step", "none")["value"]
        if interp is not None:
            hit["interp"] = interp
        if ease is not None:
            hit["ease"] = ease
        key = hit
    else:
        key = _make_key(f, value, interp or _default_interp(scene, channel, value), ease or "none")
        keys.append(key)
        keys.sort(key=lambda k: float(k["frame"]))
    _write_tracks(target_obj, data, scene)
    return copy.deepcopy(key)


def remove_key(obj, target: str, frame: float, scene: Scene | None = None) -> bool:
    scene = _sc(scene)
    target_obj = _resolve(obj, scene)
    data = _raw_tracks(target_obj)
    keys = data.get(str(target), [])
    kept = [k for k in keys if abs(float(k["frame"]) - float(frame)) >= FRAME_EPS]
    if len(kept) == len(keys):
        return False
    data[str(target)] = kept
    _write_tracks(target_obj, data, scene)
    return True


def clear_tracks(obj, target: str | None = None, scene: Scene | None = None) -> int:
    scene = _sc(scene)
    target_obj = _resolve(obj, scene)
    data = _raw_tracks(target_obj)
    if target is None:
        removed = sum(len(k) for k in data.values())
        data = {}
    else:
        removed = len(data.pop(str(target), []))
    if removed:
        _write_tracks(target_obj, data, scene)
    return removed


def _loop_mode(obj: SceneObject, channel: str) -> tuple[str, str]:
    ac = _anim()
    if ac is not None:
        return ac.loop_mode(obj, channel)
    return "constant", "constant"


def _fallback_eval(keys: list, frame: float):
    frame = float(frame)
    if frame <= float(keys[0]["frame"]):
        return keys[0]["value"]
    if frame >= float(keys[-1]["frame"]):
        return keys[-1]["value"]
    for a, b in zip(keys, keys[1:]):
        fa, fb = float(a["frame"]), float(b["frame"])
        if fa <= frame <= fb:
            va, vb = a["value"], b["value"]
            if a.get("interp") == "step" or fb == fa or not isinstance(va, (int, float, np.ndarray)):
                return va if frame < fb else vb
            t = (frame - fa) / (fb - fa)
            if a.get("interp") == "spline":
                t = t * t * (3.0 - 2.0 * t)
            return np.asarray(va, float) + (np.asarray(vb, float) - np.asarray(va, float)) * t
    return keys[-1]["value"]


def _evaluate(obj: SceneObject, channel: str, keys: list, frame: float):
    if not keys:
        return None
    ac = _anim()
    if ac is not None:
        before, after = _loop_mode(obj, channel)
        value = ac.evaluate_track(keys, frame, before, after)
    else:
        value = _fallback_eval(keys, frame)
    if isinstance(value, np.ndarray) and value.ndim == 0:
        return float(value)
    if isinstance(value, (np.floating, np.integer)):
        return float(value)
    return value


def track_value(obj, target: str, frame: float | None = None, scene: Scene | None = None) -> Any:
    scene = _sc(scene)
    target_obj = _resolve(obj, scene)
    f = current_frame(scene) if frame is None else float(frame)
    return _evaluate(target_obj, str(target), _raw_tracks(target_obj).get(str(target), []), f)


def _same_value(a: Any, b: Any) -> bool:
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        try:
            return np.array_equal(np.asarray(a, float), np.asarray(b, float))
        except (TypeError, ValueError):
            return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= 1e-12
    return a == b


def _apply_value(obj: SceneObject, channel: str, value: Any) -> str:
    ac = _anim()
    if ac is not None:
        return ac.apply_channel(obj, channel, value)
    head, _, tail = channel.partition(".")
    if head in TRANSFORM_CHANNELS:
        vec = getattr(obj, head).copy()
        vec[AXES.index(tail)] = float(value)
        setattr(obj, head, vec)
        return "transform"
    if channel == "visibility":
        obj.enabled = bool(float(value) >= 0.5)
        return "visibility"
    if channel == "points":
        obj.mesh.points = np.asarray(value, float).copy()
        return "points"
    spec = _registry().SPECS.get(obj.kind)
    p = spec.param(tail) if spec is not None else None
    obj.params[tail] = p.clamp(value) if p is not None else value
    if hasattr(obj, "_dirty"):
        obj._dirty = True
    return "param"


def apply_tracks(obj, frame: float | None = None, scene: Scene | None = None) -> int:
    scene = _sc(scene)
    target = _resolve(obj, scene)
    _owner(target, scene)
    f = current_frame(scene) if frame is None else float(frame)
    data = _raw_tracks(target)
    ac = _anim()
    order = sorted(data, key=ac.channel_sort_key) if ac is not None else sorted(data)
    values = []
    for channel in order:
        _check_target(channel, target)
        value = _evaluate(target, channel, data[channel], f)
        if value is None:
            continue
        if channel == "points" and np.shape(value) != target.mesh.points.shape:
            raise ScriptError(f"the points track of {target.name!r} does not match its point count")
        values.append((channel, value))
    pending = [(ch, v) for ch, v in values if not _same_value(_channel_value(target, ch), v)]
    if pending:
        _record(scene, "script:tracks")
        rebuild = False
        for channel, value in pending:
            if _apply_value(target, channel, value) in ("param", "visibility", "points"):
                rebuild = True
        if rebuild:
            scene.evaluate()
            scene.objectsChanged.emit()
        scene.changed.emit()
    return len(values)


def time_settings(scene: Scene | None = None) -> dict:
    scene = _sc(scene)
    ac = _anim()
    if ac is not None:
        return dict(ac.time_settings(scene))
    return {"fps": 30, "min": 0, "max": 90, "frame": current_frame(scene)}


def current_frame(scene: Scene | None = None) -> float:
    scene = _sc(scene)
    raw = store.get_scene_data(scene, "anim")
    if isinstance(raw, dict) and "frame" in raw:
        ac = _anim()
        if ac is not None:
            return float(ac.current_frame(scene))
        value = raw.get("frame")
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    for key in LEGACY_FRAME_KEYS:
        value = store.get_scene_data(scene, key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return float(value)
    return 0.0


def set_frame(frame: float, scene: Scene | None = None, evaluate: bool = True) -> float:
    scene = _sc(scene)
    f = float(frame)
    if not math.isfinite(f):
        raise ScriptError("frame must be finite")
    ac = _anim()
    with suppress_undo(scene):
        if ac is not None:
            return float(ac.set_frame(scene, f, evaluate_scene=evaluate))
        store.set_scene_data(scene, "frame", f)
    return f


def begin_undo(scene: Scene | None = None) -> bool:
    scene = _sc(scene)
    begin = getattr(scene, "begin_group", None)
    if begin is None:
        return False
    begin()
    return True


def end_undo(scene: Scene | None = None) -> None:
    scene = _sc(scene)
    end = getattr(scene, "end_group", None)
    if end is not None:
        end()


@contextlib.contextmanager
def undo_group(scene: Scene | None = None) -> Iterator[Scene]:
    scene = _sc(scene)
    began = begin_undo(scene)
    try:
        yield scene
    finally:
        if began:
            end_undo(scene)


@contextlib.contextmanager
def suppress_undo(scene: Scene | None = None) -> Iterator[Scene]:
    scene = _sc(scene)
    key = id(scene)
    entry = _SUPPRESSED.get(key)
    if entry is None:
        entry = [0, scene.__dict__.get("_record", _MISSING)]
        _SUPPRESSED[key] = entry
        scene._record = _no_record
    entry[0] += 1
    try:
        yield scene
    finally:
        entry[0] -= 1
        if entry[0] <= 0:
            _SUPPRESSED.pop(key, None)
            if entry[1] is _MISSING:
                try:
                    del scene._record
                except AttributeError:
                    pass
            else:
                scene._record = entry[1]


def undo(scene: Scene | None = None) -> bool:
    return bool(_sc(scene).undo())


def redo(scene: Scene | None = None) -> bool:
    return bool(_sc(scene).redo())


def refresh(scene: Scene | None = None, soft: bool = False) -> None:
    scene = _sc(scene)
    if soft:
        scene.changed.emit()
        return
    scene.evaluate()
    scene.objectsChanged.emit()
    scene.changed.emit()
    scene.selectionChanged.emit()


update = refresh


def add_message_listener(fn: Callable[[str], None]) -> None:
    if fn not in _MESSAGE_LISTENERS:
        _MESSAGE_LISTENERS.append(fn)


def remove_message_listener(fn: Callable[[str], None]) -> None:
    if fn in _MESSAGE_LISTENERS:
        _MESSAGE_LISTENERS.remove(fn)


def _status_bar_message(text: str) -> None:
    try:
        from PySide6.QtWidgets import QApplication, QMainWindow
    except ImportError:
        return
    app = QApplication.instance()
    if app is None or not hasattr(app, "topLevelWidgets"):
        return
    for w in app.topLevelWidgets():
        if isinstance(w, QMainWindow):
            bar = w.statusBar()
            show = getattr(bar, "showMessage", None)
            if show is not None:
                show(text, 4000)
            return


def message(*parts: Any) -> str:
    text = " ".join(str(p) for p in parts)
    _LOG.append(("message", text))
    for fn in list(_MESSAGE_LISTENERS):
        try:
            fn(text)
        except Exception:
            pass
    _status_bar_message(text)
    return text


def log(*parts: Any) -> str:
    text = " ".join(str(p) for p in parts)
    _LOG.append(("log", text))
    print(text)
    return text


def warn(*parts: Any) -> str:
    import sys
    text = " ".join(str(p) for p in parts)
    _LOG.append(("warning", text))
    print(f"Warning: {text}", file=sys.stderr)
    return text


def log_lines(limit: int | None = None) -> list[tuple[str, str]]:
    items = list(_LOG)
    return items if limit is None else items[-int(limit):]


def __getattr__(name: str):
    if name in ("Selection", "OpResult", "ToolSpec", "ToolParam"):
        from ..modeling import registry as mreg
        from ..modeling.meshkit import OpResult, Selection
        return {"Selection": Selection, "OpResult": OpResult, "ToolSpec": mreg.ToolSpec,
                "ToolParam": mreg.Param}[name]
    if name in ("ObjectSpec", "ObjectParam"):
        reg = _registry()
        return {"ObjectSpec": reg.ObjectSpec, "ObjectParam": reg.Param}[name]
    raise AttributeError(f"quartz has no attribute {name!r}")
