from __future__ import annotations

import base64
import hashlib
import zlib
from collections import OrderedDict
from typing import Any

import numpy as np

from ..ext import store
from ..scene import Mesh
from .subdivision import catmull_clark, polygon_arrays, ramp
from .topology import Topology, get_topology

__all__ = [
    "KEY", "MAX_POINTS", "VERSION", "ARRAY_TAG", "BLOCK_TEXT",
    "get_state", "has_sculpt", "can_sculpt", "init_state", "ensure_state", "save_state",
    "encode_state", "decode_state",
    "level_count", "current_level", "level_info", "level_topology", "composite",
    "subdivide", "set_level", "level_up", "level_down", "delete_higher_levels",
    "layer_count", "layers", "add_layer", "remove_layer", "rename_layer", "set_layer_strength",
    "set_layer_visible", "set_layer_locked", "set_active_layer", "active_layer", "move_layer",
    "clear_layer", "bake_layers", "merge_layer_down", "layer_editable", "edit_block",
    "can_merge_down", "bakeable_layers",
    "get_mask", "set_mask", "mask_fill", "mask_clear", "mask_invert", "mask_grow", "mask_shrink",
    "mask_smooth", "set_mask_enabled", "mask_enabled", "set_frozen", "is_frozen",
    "erase_target", "commit_stroke", "bake_to_mesh", "remove_sculpt", "summary", "orientation",
]

KEY = "sculpt"
VERSION = 2
MAX_POINTS = 2_000_000
ARRAY_TAG = "__qsarr__"
POOL_BYTES = 384 * 1024 * 1024
COMPOSITE_CACHE = 6
STATE_CACHE = 64

BLOCK_TEXT = {
    "frozen": "The object is frozen",
    "locked": "The active layer is locked",
    "hidden": "The active layer is hidden",
    "muted": "The active layer strength is 0",
}

_LEVELS: dict[str, list] = {}


def _scene(scene):
    if scene is not None:
        return scene
    from ..scene import get_scene
    return get_scene()


def _record(scene) -> None:
    fn = getattr(scene, "_record", None)
    if fn is not None:
        fn("sculpt")


def _changed(scene) -> None:
    sig = getattr(scene, "changed", None)
    if sig is not None:
        sig.emit()


def _frozen(arr) -> np.ndarray:
    a = np.asarray(arr)
    if a.flags.writeable:
        a = a.copy()
        a.flags.writeable = False
    return a


def _own(arr) -> np.ndarray:
    a = np.asarray(arr)
    if a.flags.writeable:
        a.flags.writeable = False
    return a


class _ArrayPool:

    def __init__(self, limit: int) -> None:
        self.limit = int(limit)
        self.items: OrderedDict = OrderedDict()
        self.by_text: dict[int, int] = {}
        self.bytes = 0

    def _add(self, arr: np.ndarray, packed: dict) -> None:
        key = id(arr)
        old = self.items.pop(key, None)
        if old is not None:
            self.by_text.pop(id(old[1][ARRAY_TAG]), None)
            self.bytes -= old[0].nbytes
        self.items[key] = (arr, packed)
        self.by_text[id(packed[ARRAY_TAG])] = key
        self.bytes += arr.nbytes
        while self.bytes > self.limit and len(self.items) > 1:
            _k, (a, p) = self.items.popitem(last=False)
            self.by_text.pop(id(p[ARRAY_TAG]), None)
            self.bytes -= a.nbytes

    def pack(self, arr) -> tuple[np.ndarray, dict]:
        hit = self.items.get(id(arr))
        if hit is not None and hit[0] is arr:
            self.items.move_to_end(id(arr))
            return arr, hit[1]
        a = _frozen(arr)
        c = np.ascontiguousarray(a)
        text = base64.b64encode(zlib.compress(c.tobytes(), 1)).decode("ascii")
        packed = {ARRAY_TAG: text, "dtype": c.dtype.str, "shape": [int(s) for s in c.shape]}
        self._add(a, packed)
        return a, packed

    def unpack(self, packed: dict) -> np.ndarray | None:
        text = packed.get(ARRAY_TAG)
        if not isinstance(text, str):
            return None
        key = self.by_text.get(id(text))
        if key is not None:
            hit = self.items.get(key)
            if hit is not None and hit[1][ARRAY_TAG] is text:
                self.items.move_to_end(key)
                return hit[0]
        try:
            raw = zlib.decompress(base64.b64decode(text.encode("ascii")))
            dtype = np.dtype(str(packed.get("dtype", "<f8")))
            shape = tuple(int(s) for s in packed.get("shape") or (-1,))
            arr = np.frombuffer(raw, dtype=dtype).reshape(shape)
        except (ValueError, TypeError, zlib.error):
            return None
        if arr.flags.writeable:
            arr.flags.writeable = False
        self._add(arr, {ARRAY_TAG: text, "dtype": packed.get("dtype"), "shape": packed.get("shape")})
        return arr

    def clear(self) -> None:
        self.items.clear()
        self.by_text.clear()
        self.bytes = 0


_POOL = _ArrayPool(POOL_BYTES)


def _encode(value):
    if isinstance(value, np.ndarray):
        frozen, packed = _POOL.pack(value)
        return packed, frozen
    if isinstance(value, dict):
        enc, plain = {}, {}
        for k, v in value.items():
            enc[str(k)], plain[k] = _encode(v)
        return enc, plain
    if isinstance(value, (list, tuple)):
        pairs = [_encode(v) for v in value]
        return [p[0] for p in pairs], [p[1] for p in pairs]
    if isinstance(value, np.bool_):
        return bool(value), bool(value)
    if isinstance(value, np.integer):
        return int(value), int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        f = f if np.isfinite(f) else 0.0
        return f, f
    return value, value


def _decode(value):
    if isinstance(value, dict):
        if ARRAY_TAG in value:
            return _POOL.unpack(value)
        if "__ndarray__" in value:
            try:
                return _frozen(np.array(store.from_json(value)))
            except (ValueError, TypeError):
                return None
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if isinstance(value, np.ndarray):
        return _frozen(value)
    return value


def encode_state(state: dict) -> tuple[dict, dict]:
    return _encode(state)


def decode_state(raw) -> dict | None:
    return _normalize(_decode(raw)) if isinstance(raw, dict) else None


def _signature(n: int, sizes: np.ndarray, flat: np.ndarray) -> str:
    h = hashlib.sha1()
    h.update(str(int(n)).encode())
    h.update(np.ascontiguousarray(sizes, np.int64).tobytes())
    h.update(np.ascontiguousarray(flat, np.int64).tobytes())
    return h.hexdigest()


def _float_points(a) -> np.ndarray | None:
    try:
        arr = np.asarray(a, float)
    except (ValueError, TypeError):
        return None
    if arr.ndim != 2 or arr.shape[1] != 3:
        try:
            arr = arr.reshape(-1, 3)
        except ValueError:
            return None
    return _frozen(arr)


def _normalize(state) -> dict | None:
    if not isinstance(state, dict):
        return None
    raw_levels = state.get("levels")
    if not isinstance(raw_levels, list) or not raw_levels:
        return None
    levels = [_float_points(l) for l in raw_levels]
    if any(l is None for l in levels):
        return None
    state["levels"] = levels
    if state.get("base_flat") is None or state.get("base_sizes") is None:
        polys = state.get("base_polygons") or []
        sizes, flat = polygon_arrays([list(int(i) for i in p) for p in polys]) if polys else (
            np.zeros(0, np.int64), np.zeros(0, np.int64))
        state["base_sizes"] = _frozen(np.asarray(sizes, np.int64))
        state["base_flat"] = _frozen(np.asarray(flat, np.int64))
    else:
        state["base_sizes"] = _frozen(np.asarray(state["base_sizes"], np.int64).reshape(-1))
        state["base_flat"] = _frozen(np.asarray(state["base_flat"], np.int64).reshape(-1))
    state.pop("base_polygons", None)
    n0 = len(levels[0])
    if not state.get("base_sig"):
        state["base_sig"] = _signature(n0, state["base_sizes"], state["base_flat"])
    origin = state.get("origin")
    origin = _float_points(origin) if origin is not None else None
    state["origin"] = origin if origin is not None and len(origin) == n0 else levels[0]
    for k in ("raw_sizes", "raw_flat"):
        if state.get(k) is not None:
            state[k] = _frozen(np.asarray(state[k], np.int64).reshape(-1))
        else:
            state[k] = None
    state.setdefault("raw_sig", None)
    loose = state.get("base_loose")
    state["base_loose"] = None if loose is None or not len(loose) else _frozen(
        np.asarray(loose, np.int64).reshape(-1, 2))
    scales = state.get("base_scales")
    state["base_scales"] = None if scales is None else _frozen(np.asarray(scales, float).reshape(-1))
    lays = []
    for layer in state.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        layer = dict(layer)
        layer["name"] = str(layer.get("name", "Layer"))
        layer["strength"] = float(layer.get("strength", 1.0))
        layer["visible"] = bool(layer.get("visible", True))
        layer["locked"] = bool(layer.get("locked", False))
        deltas = []
        for d in layer.get("deltas") or []:
            deltas.append(None if d is None else _float_points(d))
        deltas = deltas[:len(levels)] + [None] * (len(levels) - len(deltas))
        layer["deltas"] = deltas
        lays.append(layer)
    state["layers"] = lays
    mask = state.get("mask")
    state["mask"] = None if mask is None else _frozen(np.asarray(mask, float).reshape(-1))
    ml = state.get("mask_levels")
    ml = list(ml) if isinstance(ml, list) else []
    ml = [None if m is None else _frozen(np.asarray(m, float).reshape(-1)) for m in ml[:len(levels)]]
    state["mask_levels"] = ml + [None] * (len(levels) - len(ml))
    state["version"] = VERSION
    state["level"] = int(min(max(0, int(state.get("level", 0) or 0)), len(levels) - 1))
    active = state.get("active_layer")
    state["active_layer"] = -1 if active is None else int(active)
    state["mask_enabled"] = bool(state.get("mask_enabled", True))
    state["frozen"] = bool(state.get("frozen", False))
    return state


def _clone(state: dict) -> dict:
    out = dict(state)
    out["levels"] = list(state["levels"])
    out["layers"] = [dict(l, deltas=list(l.get("deltas") or [])) for l in state.get("layers") or []]
    out["mask_levels"] = list(state.get("mask_levels") or [])
    return out


_STATES: OrderedDict = OrderedDict()


def _cache_state(obj, raw: dict, state: dict) -> None:
    _STATES[id(obj)] = (raw, state)
    _STATES.move_to_end(id(obj))
    while len(_STATES) > STATE_CACHE:
        _STATES.popitem(last=False)


def get_state(obj) -> dict | None:
    extras = getattr(obj, "extras", None)
    if not isinstance(extras, dict):
        return None
    raw = extras.get(KEY)
    if not isinstance(raw, dict):
        return None
    hit = _STATES.get(id(obj))
    if hit is not None and hit[0] is raw:
        return _clone(hit[1])
    state = decode_state(raw)
    if state is None:
        return None
    _cache_state(obj, raw, state)
    return _clone(state)


def has_sculpt(obj) -> bool:
    return obj is not None and get_state(obj) is not None


def can_sculpt(obj) -> bool:
    if obj is None or getattr(obj, "kind", "polygon") != "polygon":
        return False
    mesh = getattr(obj, "mesh", None)
    return mesh is not None and bool(mesh.polygons) and len(mesh.points) > 0


def orientation(obj) -> float:
    try:
        m = np.asarray(obj.world_matrix(), float)[:3, :3]
    except Exception:
        return 1.0
    return -1.0 if float(np.linalg.det(m)) < 0.0 else 1.0


def _base_polys(state: dict) -> list:
    sizes = np.asarray(state["base_sizes"], np.int64)
    flat = np.asarray(state["base_flat"], np.int64)
    if len(sizes) and int(sizes.min()) == int(sizes.max()):
        return [tuple(p) for p in flat.reshape(len(sizes), int(sizes[0])).tolist()]
    fl = flat.tolist()
    out = []
    i = 0
    for s in sizes.tolist():
        out.append(tuple(fl[i:i + s]))
        i += s
    return out


def _chain(state: dict) -> list:
    sig = state["base_sig"]
    chain = _LEVELS.get(sig)
    if chain is None:
        if len(_LEVELS) > 32:
            _LEVELS.clear()
        chain = _LEVELS[sig] = [(len(state["levels"][0]), _base_polys(state), sig)]
    return chain


def level_topology(state: dict, level: int) -> tuple[int, list, str]:
    chain = _chain(state)
    while len(chain) <= level:
        n, polys, sig = chain[-1]
        op = catmull_clark(n, polys, key=sig)
        sizes, flat = polygon_arrays(op.quads)
        chain.append((op.m, op.polygons, _signature(op.m, sizes, flat)))
    return chain[level]


def _level_sigs(state: dict, level: int) -> tuple[str, ...]:
    sig = level_topology(state, level)[2]
    if level == 0 and state.get("raw_sig"):
        return sig, state["raw_sig"]
    return (sig,)


def _operator(state: dict, level: int):
    n, polys, sig = level_topology(state, level)
    return catmull_clark(n, polys, key=sig)


def topology(state: dict, level: int | None = None) -> Topology:
    lv = current_level(state) if level is None else level
    n, polys, sig = level_topology(state, lv)
    return get_topology(n, polys, key=sig)


def level_count(state: dict | None) -> int:
    return len(state["levels"]) if state else 0


def current_level(state: dict | None) -> int:
    if not state:
        return 0
    return int(min(max(0, int(state.get("level", 0))), len(state["levels"]) - 1))


def _factor(layer: dict) -> float:
    return float(layer.get("strength", 1.0)) if layer.get("visible", True) else 0.0


def _layer_delta(layer: dict, level: int):
    deltas = layer.get("deltas") or []
    if level < len(deltas) and deltas[level] is not None:
        return deltas[level]
    return None


def composite(state: dict, level: int | None = None, *, skip_layer: int | None = None,
              skip_detail: bool = False) -> np.ndarray:
    lv = current_level(state) if level is None else int(level)
    lays = state.get("layers") or []
    pts = None
    for h in range(lv + 1):
        base = np.asarray(state["levels"][h], float)
        if h == 0:
            pts = base.copy()
            if skip_detail and h == lv:
                pts = np.asarray(state.get("origin", base), float).copy()
        else:
            pts = _operator(state, h - 1).apply(pts)
            if not (skip_detail and h == lv):
                pts = pts + base
        for i, layer in enumerate(lays):
            if skip_layer is not None and i == skip_layer and h == lv:
                continue
            d = _layer_delta(layer, h)
            f = _factor(layer)
            if d is not None and f != 0.0 and len(d) == len(pts):
                pts = pts + f * d
    return pts


_COMP: OrderedDict = OrderedDict()


def _comp_key(state: dict, level: int):
    refs = []
    parts: list = [state.get("base_sig"), int(level)]
    for h in range(level + 1):
        a = state["levels"][h]
        refs.append(a)
        parts.append(id(a))
    for layer in state.get("layers") or []:
        f = _factor(layer)
        if f == 0.0:
            continue
        for h in range(level + 1):
            d = _layer_delta(layer, h)
            if d is not None:
                refs.append(d)
                parts.append((h, id(d), f))
    return tuple(parts), refs


def _remember(state: dict, level: int, pts) -> np.ndarray:
    key, refs = _comp_key(state, level)
    arr = _frozen(np.asarray(pts, float))
    _COMP[key] = (refs, arr)
    _COMP.move_to_end(key)
    while len(_COMP) > COMPOSITE_CACHE:
        _COMP.popitem(last=False)
    return arr


def _cached_composite(state: dict, level: int) -> np.ndarray:
    key, _refs = _comp_key(state, level)
    hit = _COMP.get(key)
    if hit is not None:
        _COMP.move_to_end(key)
        return hit[1]
    return _remember(state, level, _own(composite(state, level)))


def save_state(obj, state: dict | None) -> None:
    extras = store.object_extras(obj)
    if state is None:
        extras.pop(KEY, None)
        _STATES.pop(id(obj), None)
    else:
        raw, plain = encode_state(state)
        for k in ("levels", "layers", "mask", "mask_levels", "origin"):
            if k in plain:
                state[k] = plain[k]
        extras[KEY] = raw
        _cache_state(obj, raw, _clone(plain))
    store.notify(obj, KEY)


def _mesh_arrays(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    sizes, flat = polygon_arrays(mesh.polygons) if mesh.polygons else (
        np.zeros(0, np.int64), np.zeros(0, np.int64))
    return np.asarray(sizes, np.int64), np.asarray(flat, np.int64)


def init_state(obj, *, save: bool = True) -> dict | None:
    if not can_sculpt(obj):
        return None
    mesh = obj.mesh
    pts = _frozen(np.asarray(mesh.points, float).copy())
    sizes, flat = _mesh_arrays(mesh)
    raw_sig = _signature(len(pts), sizes, flat)
    raw_sizes = raw_flat = None
    if len(sizes) and int(sizes.min()) < 3:
        keep = sizes >= 3
        starts = np.cumsum(sizes) - sizes
        raw_sizes, raw_flat = _frozen(sizes), _frozen(flat)
        flat = flat[np.repeat(starts[keep], sizes[keep]) + ramp(sizes[keep])]
        sizes = sizes[keep]
    loose = np.asarray(mesh.loose_edges, np.int64).reshape(-1, 2) if mesh.loose_edges else None
    scales = mesh.point_scales
    state = {
        "version": VERSION,
        "base_sizes": _frozen(sizes),
        "base_flat": _frozen(flat),
        "base_sig": _signature(len(pts), sizes, flat),
        "raw_sizes": raw_sizes,
        "raw_flat": raw_flat,
        "raw_sig": raw_sig if raw_sizes is not None else None,
        "base_loose": None if loose is None else _frozen(loose),
        "base_scales": None if scales is None else _frozen(np.asarray(scales, float)),
        "origin": pts,
        "levels": [pts],
        "level": 0,
        "layers": [],
        "active_layer": -1,
        "mask": None,
        "mask_levels": [None],
        "mask_enabled": True,
        "frozen": False,
    }
    _remember(state, 0, pts)
    if save:
        save_state(obj, state)
    return state


_SIGS: dict = {}


def _mesh_sig(mesh: Mesh) -> str:
    key = (id(mesh), id(mesh.polygons), id(mesh.edges), len(mesh.polygons), len(mesh.points))
    hit = _SIGS.get(key)
    if hit is not None and hit[0] is mesh:
        return hit[1]
    sizes, flat = _mesh_arrays(mesh)
    sig = _signature(len(mesh.points), sizes, flat)
    if len(_SIGS) > 64:
        _SIGS.clear()
    _SIGS[key] = (mesh, sig)
    return sig


def _find_level(state: dict, mesh: Mesh) -> int | None:
    n = len(mesh.points)
    sig = None
    for lv in range(level_count(state)):
        ln = level_topology(state, lv)[0]
        if ln != n:
            continue
        if sig is None:
            sig = _mesh_sig(mesh)
        if sig in _level_sigs(state, lv):
            return lv
    return None


def _mask_store(state: dict) -> list:
    n = level_count(state)
    ml = state.get("mask_levels")
    ml = list(ml) if isinstance(ml, list) else []
    ml = ml[:n] + [None] * (n - len(ml))
    state["mask_levels"] = ml
    return ml


def _transfer_mask(state: dict, old: int, new: int) -> None:
    if old == new:
        return
    stored = _mask_store(state)
    m = state.get("mask")
    m = None if m is None else np.asarray(m, float)
    if new < old:
        for h in range(old, new, -1):
            stored[h] = None if m is None else _frozen(m)
            if m is not None:
                low = level_topology(state, h - 1)[0]
                m = m[:low] if len(m) >= low else None
    else:
        for h in range(old, new):
            n_h = level_topology(state, h)[0]
            op = _operator(state, h)
            keep = stored[h + 1]
            if keep is not None and len(keep) != op.m:
                keep = None
            if m is not None and len(m) != n_h:
                m = None
            if keep is None:
                up = None if m is None else op.apply(m)
            else:
                cur = np.zeros(n_h) if m is None else m
                changed = np.abs(cur - np.asarray(keep[:n_h], float)) > 1e-9
                if not changed.any():
                    up = np.asarray(keep, float)
                else:
                    reach = op.apply(changed.astype(float)) > 0.0
                    up = np.where(reach, op.apply(cur), keep)
            stored[h + 1] = None
            m = up
    state["mask"] = None if m is None or not np.any(m > 0.0) else _own(np.clip(m, 0.0, 1.0))


def layer_editable(layer: dict | None) -> bool:
    if not isinstance(layer, dict):
        return False
    return (bool(layer.get("visible", True)) and not bool(layer.get("locked", False))
            and abs(float(layer.get("strength", 1.0))) > 1e-6)


def edit_block(state: dict | None) -> str | None:
    if not state:
        return None
    if is_frozen(state):
        return "frozen"
    i = active_layer(state)
    if i < 0:
        return None
    layer = state["layers"][i]
    if layer.get("locked", False):
        return "locked"
    if not layer.get("visible", True):
        return "hidden"
    if abs(float(layer.get("strength", 1.0))) <= 1e-6:
        return "muted"
    return None


def _attribute(state: dict, level: int, diff: np.ndarray) -> None:
    lays = state.get("layers") or []
    i = int(state.get("active_layer", -1))
    if 0 <= i < len(lays) and layer_editable(lays[i]):
        layer = lays[i]
        f = _factor(layer)
        deltas = layer.setdefault("deltas", [])
        while len(deltas) <= level:
            deltas.append(None)
        cur = deltas[level]
        cur = np.zeros_like(diff) if cur is None else np.asarray(cur, float)
        deltas[level] = _own(cur + diff / f)
        return
    state["levels"][level] = _own(np.asarray(state["levels"][level], float) + diff)


def _stroking(obj) -> bool:
    from . import stroke as _stroke
    return _stroke.has_live_stroke(obj)


def _flush(obj) -> None:
    from . import stroke as _stroke
    _stroke.end_strokes(obj)


def _reconcile(obj, state: dict) -> bool:
    mesh = obj.mesh
    lv = _find_level(state, mesh)
    if lv is None:
        return False
    old = current_level(state)
    if lv != old:
        _transfer_mask(state, old, lv)
        state["level"] = lv
    if _stroking(obj):
        return True
    pts = _cached_composite(state, lv)
    diff = np.asarray(mesh.points, float) - pts
    if diff.size and float(np.max(np.abs(diff))) > 1e-9:
        _attribute(state, lv, diff)
        _remember(state, lv, mesh.points)
        state["_dirty"] = True
    mask = state.get("mask")
    if mask is not None and len(mask) != len(mesh.points):
        state["mask"] = None
    if lv != old:
        state["_dirty"] = True
    return True


def ensure_state(obj, *, create: bool = True, save: bool = True) -> dict | None:
    if not can_sculpt(obj):
        return None
    state = get_state(obj)
    if state is not None and _reconcile(obj, state):
        if state.pop("_dirty", False) and save:
            save_state(obj, state)
        return state
    if not create:
        return None
    return init_state(obj, save=save)


def _level_mesh(state: dict, level: int, pts: np.ndarray) -> Mesh:
    n, polys, _sig = level_topology(state, level)
    if level == 0 and state.get("raw_sizes") is not None:
        polys = _base_polys({"base_sizes": state["raw_sizes"], "base_flat": state["raw_flat"]})
    loose = state.get("base_loose")
    loose = [] if loose is None else [tuple(e) for e in np.asarray(loose).tolist()]
    scales = state.get("base_scales")
    if scales is not None:
        scales = np.asarray(scales, float)
        for h in range(level):
            scales = _operator(state, h).apply(scales)
    return Mesh(np.array(pts, float, copy=True), polys, loose, point_scales=scales)


def _apply_mesh(obj, state: dict) -> None:
    lv = current_level(state)
    n = level_topology(state, lv)[0]
    pts = _cached_composite(state, lv)
    mesh = obj.mesh
    if len(mesh.points) == n and _mesh_sig(mesh) in _level_sigs(state, lv):
        mesh.points = np.array(pts, float, copy=True)
    else:
        obj.mesh = _level_mesh(state, lv, pts)


def _begin(obj, scene):
    scene = _scene(scene)
    _flush(obj)
    state = ensure_state(obj, save=False)
    return state, scene


def _finish(obj, state: dict, scene, geometry: bool = True) -> None:
    state.pop("_dirty", None)
    if geometry:
        _apply_mesh(obj, state)
    save_state(obj, state)
    _changed(scene)


def level_info(state: dict | None) -> list[dict]:
    if not state:
        return []
    out = []
    for lv in range(level_count(state)):
        n, polys, _sig = level_topology(state, lv)
        out.append({"level": lv, "points": n, "polygons": len(polys)})
    return out


def subdivide(obj, scene=None, levels: int = 1) -> bool:
    state, scene = _begin(obj, scene)
    if state is None or levels < 1:
        return False
    top = level_count(state) - 1
    n_top = level_topology(state, top)[0]
    faces_top = len(level_topology(state, top)[1])
    estimate = n_top
    for _ in range(levels):
        estimate = estimate + faces_top * 3
        faces_top *= 4
    if estimate > MAX_POINTS:
        return False
    _record(scene)
    _transfer_mask(state, current_level(state), top)
    state["level"] = top
    for _ in range(levels):
        nxt = top + 1
        m = level_topology(state, nxt)[0]
        state["levels"].append(_own(np.zeros((m, 3))))
        for layer in state.get("layers") or []:
            deltas = layer.setdefault("deltas", [])
            while len(deltas) < nxt + 1:
                deltas.append(None)
        _mask_store(state)
        _transfer_mask(state, top, nxt)
        top = nxt
        state["level"] = top
    _finish(obj, state, scene)
    return True


def set_level(obj, level: int, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None:
        return False
    level = int(min(max(0, level), level_count(state) - 1))
    old = current_level(state)
    if level == old:
        return False
    _record(scene)
    _transfer_mask(state, old, level)
    state["level"] = level
    _finish(obj, state, scene)
    return True


def level_up(obj, scene=None) -> bool:
    state = ensure_state(obj)
    return state is not None and set_level(obj, current_level(state) + 1, scene)


def level_down(obj, scene=None) -> bool:
    state = ensure_state(obj)
    return state is not None and set_level(obj, current_level(state) - 1, scene)


def delete_higher_levels(obj, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None:
        return False
    lv = current_level(state)
    if lv >= level_count(state) - 1:
        return False
    _record(scene)
    state["levels"] = state["levels"][:lv + 1]
    for layer in state.get("layers") or []:
        layer["deltas"] = list(layer.get("deltas") or [])[:lv + 1]
    _mask_store(state)
    _finish(obj, state, scene)
    return True


def layers(state: dict | None) -> list[dict]:
    return list(state.get("layers") or []) if state else []


def layer_count(state: dict | None) -> int:
    return len(layers(state))


def active_layer(state: dict | None) -> int:
    if not state:
        return -1
    i = int(state.get("active_layer", -1))
    return i if 0 <= i < layer_count(state) else -1


def _unique_layer_name(state: dict, base: str) -> str:
    names = {l.get("name") for l in state.get("layers") or []}
    if base not in names:
        return base
    k = 2
    while f"{base} {k}" in names:
        k += 1
    return f"{base} {k}"


def add_layer(obj, name: str | None = None, scene=None) -> int:
    state, scene = _begin(obj, scene)
    if state is None:
        return -1
    _record(scene)
    lays = state.setdefault("layers", [])
    label = _unique_layer_name(state, name or f"Layer {len(lays) + 1}")
    lays.append({"name": label, "strength": 1.0, "visible": True, "locked": False,
                 "deltas": [None] * level_count(state)})
    state["active_layer"] = len(lays) - 1
    _finish(obj, state, scene, geometry=False)
    return len(lays) - 1


def _layer(state: dict, index: int) -> dict | None:
    lays = state.get("layers") or []
    return lays[index] if 0 <= index < len(lays) else None


def remove_layer(obj, index: int, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None or _layer(state, index) is None:
        return False
    _record(scene)
    state["layers"].pop(index)
    a = int(state.get("active_layer", -1))
    if a == index:
        state["active_layer"] = min(index, len(state["layers"]) - 1)
    elif a > index:
        state["active_layer"] = a - 1
    _finish(obj, state, scene)
    return True


def rename_layer(obj, index: int, name: str, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    layer = _layer(state, index) if state else None
    label = str(name).strip()
    if layer is None or not label or layer.get("name") == label:
        return False
    _record(scene)
    layer["name"] = label
    _finish(obj, state, scene, geometry=False)
    return True


def set_layer_strength(obj, index: int, value: float, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    layer = _layer(state, index) if state else None
    if layer is None:
        return False
    value = float(min(max(value, 0.0), 2.0))
    if abs(float(layer.get("strength", 1.0)) - value) < 1e-12:
        return False
    rec = getattr(scene, "_record", None)
    if rec is not None:
        rec(f"scales:sculpt:{index}")
    layer["strength"] = value
    _finish(obj, state, scene)
    return True


def set_layer_visible(obj, index: int, flag: bool, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    layer = _layer(state, index) if state else None
    if layer is None or bool(layer.get("visible", True)) == bool(flag):
        return False
    _record(scene)
    layer["visible"] = bool(flag)
    _finish(obj, state, scene)
    return True


def set_layer_locked(obj, index: int, flag: bool, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    layer = _layer(state, index) if state else None
    if layer is None or bool(layer.get("locked", False)) == bool(flag):
        return False
    _record(scene)
    layer["locked"] = bool(flag)
    _finish(obj, state, scene, geometry=False)
    return True


def set_active_layer(obj, index: int, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None:
        return False
    index = int(index)
    if _layer(state, index) is None:
        index = -1
    if active_layer(state) == index:
        return False
    _record(scene)
    state["active_layer"] = index
    _finish(obj, state, scene, geometry=False)
    return True


def move_layer(obj, index: int, step: int, scene=None) -> int:
    state, scene = _begin(obj, scene)
    if state is None or _layer(state, index) is None:
        return index
    lays = state["layers"]
    new = int(min(max(0, index + step), len(lays) - 1))
    if new == index:
        return index
    _record(scene)
    layer = lays.pop(index)
    lays.insert(new, layer)
    a = int(state.get("active_layer", -1))
    if a == index:
        state["active_layer"] = new
    elif index < a <= new:
        state["active_layer"] = a - 1
    elif new <= a < index:
        state["active_layer"] = a + 1
    _finish(obj, state, scene, geometry=False)
    return new


def clear_layer(obj, index: int | None = None, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None or is_frozen(state):
        return False
    if index is None:
        index = active_layer(state)
    lv = current_level(state)
    if index < 0:
        cur = np.asarray(state["levels"][lv], float)
        goal = np.asarray(state["origin"], float) if lv == 0 else np.zeros_like(cur)
        if cur.shape == goal.shape and np.array_equal(cur, goal):
            return False
        _record(scene)
        state["levels"][lv] = _frozen(goal)
    else:
        layer = _layer(state, index)
        if layer is None or layer.get("locked", False):
            return False
        deltas = layer.setdefault("deltas", [])
        if lv >= len(deltas) or deltas[lv] is None:
            return False
        _record(scene)
        deltas[lv] = None
    _finish(obj, state, scene)
    return True


def _fold(state: dict, indices: list[int], into: int | None) -> None:
    lays = state.get("layers") or []
    for h in range(level_count(state)):
        add = None
        for i in indices:
            d = _layer_delta(lays[i], h)
            f = _factor(lays[i])
            if d is not None and f != 0.0:
                add = f * np.asarray(d, float) if add is None else add + f * np.asarray(d, float)
        if add is None:
            continue
        if into is None:
            state["levels"][h] = _own(np.asarray(state["levels"][h], float) + add)
        else:
            target = lays[into]
            ft = _factor(target)
            deltas = target.setdefault("deltas", [])
            while len(deltas) <= h:
                deltas.append(None)
            cur = deltas[h]
            cur = np.zeros_like(add) if cur is None else np.asarray(cur, float)
            deltas[h] = _own(cur + add / ft)


def bakeable_layers(state: dict | None) -> list[int]:
    return [i for i, l in enumerate(layers(state)) if layer_editable(l)]


def bake_layers(obj, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None:
        return False
    picked = bakeable_layers(state)
    if not picked:
        return False
    _record(scene)
    _fold(state, picked, None)
    a = active_layer(state)
    keep = [i for i in range(len(state["layers"])) if i not in picked]
    state["layers"] = [state["layers"][i] for i in keep]
    state["active_layer"] = keep.index(a) if a in keep else -1
    _finish(obj, state, scene)
    return True


def can_merge_down(state: dict | None, index: int) -> bool:
    if not state:
        return False
    layer = _layer(state, index)
    if not layer_editable(layer):
        return False
    return index == 0 or layer_editable(_layer(state, index - 1))


def merge_layer_down(obj, index: int, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None or not can_merge_down(state, index):
        return False
    _record(scene)
    _fold(state, [index], None if index == 0 else index - 1)
    state["layers"].pop(index)
    state["active_layer"] = index - 1
    _finish(obj, state, scene)
    return True


def get_mask(state: dict | None, n: int | None = None) -> np.ndarray:
    if not state:
        return np.zeros(0 if n is None else n)
    if n is None:
        n = level_topology(state, current_level(state))[0]
    mask = state.get("mask")
    if mask is None or len(mask) != n:
        return np.zeros(n)
    return np.array(mask, float, copy=True)


def _set_mask_value(state: dict, arr: np.ndarray | None) -> None:
    state["mask"] = None if arr is None or not np.any(arr > 0.0) else _own(np.clip(arr, 0.0, 1.0))


def set_mask(obj, values, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None:
        return False
    n = level_topology(state, current_level(state))[0]
    arr = np.clip(np.asarray(values, float).reshape(-1), 0.0, 1.0)
    if len(arr) != n:
        return False
    old = get_mask(state, n)
    if np.array_equal(old, arr):
        return False
    _record(scene)
    _set_mask_value(state, arr)
    _finish(obj, state, scene, geometry=False)
    return True


def _mask_op(obj, fn, scene=None, stored=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None:
        return False
    n = level_topology(state, current_level(state))[0]
    mask = get_mask(state, n)
    out = np.clip(fn(state, mask), 0.0, 1.0)
    ml = _mask_store(state)
    lv = current_level(state)
    new_ml = list(ml)
    if stored is not None:
        for h in range(lv + 1, len(ml)):
            new_ml[h] = stored(ml[h])
    same_ml = all(a is b for a, b in zip(ml, new_ml))
    if np.array_equal(out, mask) and same_ml:
        return False
    _record(scene)
    state["mask_levels"] = new_ml
    _set_mask_value(state, out)
    _finish(obj, state, scene, geometry=False)
    return True


def mask_fill(obj, scene=None) -> bool:
    return _mask_op(obj, lambda s, m: np.ones_like(m), scene, stored=lambda keep: None)


def mask_clear(obj, scene=None) -> bool:
    return _mask_op(obj, lambda s, m: np.zeros_like(m), scene, stored=lambda keep: None)


def mask_invert(obj, scene=None) -> bool:
    return _mask_op(obj, lambda s, m: 1.0 - m, scene,
                    stored=lambda keep: None if keep is None else _own(1.0 - np.asarray(keep, float)))


def mask_grow(obj, scene=None) -> bool:
    def fn(s, m):
        topo = topology(s)
        if not len(topo.edges):
            return m
        out = m.copy()
        a, b = topo.edges[:, 0], topo.edges[:, 1]
        np.maximum.at(out, a, m[b])
        np.maximum.at(out, b, m[a])
        return out
    return _mask_op(obj, fn, scene)


def mask_shrink(obj, scene=None) -> bool:
    def fn(s, m):
        topo = topology(s)
        if not len(topo.edges):
            return m
        out = m.copy()
        a, b = topo.edges[:, 0], topo.edges[:, 1]
        np.minimum.at(out, a, m[b])
        np.minimum.at(out, b, m[a])
        return out
    return _mask_op(obj, fn, scene)


def mask_smooth(obj, scene=None, iterations: int = 1) -> bool:
    def fn(s, m):
        topo = topology(s)
        out = m.copy()
        for _ in range(max(1, int(iterations))):
            out = 0.5 * out + 0.5 * topo.neighbor_mean(out, keep_boundary=False)
        return out
    return _mask_op(obj, fn, scene)


def set_mask_enabled(obj, flag: bool, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None or mask_enabled(state) == bool(flag):
        return False
    _record(scene)
    state["mask_enabled"] = bool(flag)
    _finish(obj, state, scene, geometry=False)
    return True


def mask_enabled(state: dict | None) -> bool:
    return bool(state.get("mask_enabled", True)) if state else True


def set_frozen(obj, flag: bool, scene=None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None or is_frozen(state) == bool(flag):
        return False
    _record(scene)
    state["frozen"] = bool(flag)
    _finish(obj, state, scene, geometry=False)
    return True


def is_frozen(state: dict | None) -> bool:
    return bool(state.get("frozen", False)) if state else False


def erase_target(state: dict) -> np.ndarray:
    lv = current_level(state)
    i = active_layer(state)
    if i >= 0:
        return composite(state, lv, skip_layer=i)
    return composite(state, lv, skip_detail=True)


def commit_stroke(obj, state: dict | None, before: np.ndarray, after: np.ndarray,
                  mask: np.ndarray | None = None, scene=None) -> bool:
    fresh = get_state(obj)
    if fresh is None:
        fresh = state
    if fresh is None:
        return False
    lv = current_level(fresh)
    n = level_topology(fresh, lv)[0]
    after = np.asarray(after, float)
    if len(after) != n or len(before) != n:
        return False
    diff = after - np.asarray(before, float)
    if diff.size and float(np.max(np.abs(diff))) > 0.0:
        _attribute(fresh, lv, diff)
    _remember(fresh, lv, after)
    if mask is not None:
        _set_mask_value(fresh, np.asarray(mask, float))
    if obj.mesh.points is not after:
        obj.mesh.points = after
    save_state(obj, fresh)
    if scene is not None:
        _changed(scene)
    return True


def bake_to_mesh(obj, scene=None, level: int | None = None) -> bool:
    state, scene = _begin(obj, scene)
    if state is None:
        return False
    _record(scene)
    lv = current_level(state) if level is None else int(min(max(0, level), level_count(state) - 1))
    obj.mesh = _level_mesh(state, lv, composite(state, lv))
    save_state(obj, None)
    _changed(scene)
    return True


def remove_sculpt(obj, scene=None) -> bool:
    _flush(obj)
    if get_state(obj) is None:
        return False
    scene = _scene(scene)
    _record(scene)
    save_state(obj, None)
    _changed(scene)
    return True


def summary(obj) -> dict[str, Any]:
    state = get_state(obj) if obj is not None else None
    if state is None:
        return {"sculpt": False, "level": 0, "levels": 0, "points": len(obj.mesh.points) if obj is not None else 0,
                "layers": [], "active_layer": -1, "masked": 0, "mask_enabled": True, "frozen": False,
                "block": None, "can_merge": False, "bakeable": 0}
    lv = current_level(state)
    n = level_topology(state, lv)[0]
    mask = state.get("mask")
    masked = int(np.count_nonzero(np.asarray(mask) > 0.5)) if mask is not None and len(mask) == n else 0
    a = active_layer(state)
    return {
        "sculpt": True,
        "level": lv,
        "levels": level_count(state),
        "points": n,
        "layers": [{"name": l.get("name", ""), "strength": float(l.get("strength", 1.0)),
                    "visible": bool(l.get("visible", True)), "locked": bool(l.get("locked", False))}
                   for l in state.get("layers") or []],
        "active_layer": a,
        "masked": masked,
        "mask_enabled": mask_enabled(state),
        "frozen": is_frozen(state),
        "block": edit_block(state),
        "can_merge": a >= 0 and can_merge_down(state, a),
        "bakeable": len(bakeable_layers(state)),
    }
