from __future__ import annotations

import base64
import copy
import math
import weakref
from contextlib import contextmanager
from typing import Any, Iterable

import numpy as np

from ..ext import store

__all__ = [
    "ANIM_KEY",
    "TRACKS_KEY",
    "MODES_KEY",
    "INTERPS",
    "EASES",
    "LOOPS",
    "PLAY_MODES",
    "POSITION_CHANNELS",
    "ROTATION_CHANNELS",
    "SCALE_CHANNELS",
    "TRANSFORM_CHANNELS",
    "VISIBILITY",
    "POINTS",
    "PARAM_PREFIX",
    "DEFAULT_TIME",
    "time_settings",
    "set_time_settings",
    "current_frame",
    "set_frame",
    "fps",
    "frame_to_seconds",
    "seconds_to_frame",
    "format_time",
    "make_key",
    "tracks",
    "get_track",
    "set_track",
    "track_modes",
    "loop_mode",
    "set_loop",
    "has_animation",
    "animated_objects",
    "channels_of",
    "param_channels",
    "is_scalar_channel",
    "channel_label",
    "channel_sort_key",
    "channel_value",
    "apply_channel",
    "auto_slopes",
    "key_tangents",
    "evaluate_track",
    "evaluate_channel",
    "evaluate",
    "is_evaluating",
    "insert_key",
    "set_key",
    "record_objects",
    "record_active",
    "record_points",
    "find_key",
    "delete_key",
    "delete_keys",
    "delete_keys_at",
    "clear_tracks",
    "move_keys",
    "scale_keys",
    "reverse_keys",
    "offset_key_values",
    "set_key_value",
    "set_key_attrs",
    "set_tangents",
    "reset_tangents",
    "flatten_tangents",
    "copy_keys",
    "paste_keys",
    "key_frames",
    "all_refs",
    "refs_at_frame",
    "refs_exist",
    "next_key_frame",
    "prev_key_frame",
    "key_range",
    "value_range",
    "bake_object",
    "snapshot_tracks",
    "restore_tracks",
    "edit_group",
    "begin_edit",
    "end_edit",
    "keyable_params",
    "keyable_channels",
    "record_params",
    "record_visibility",
    "record_point_selection",
    "clear_points",
    "PLAYBACK_MODES",
    "playback_mode",
    "set_playback_mode",
    "retime_document",
]

ANIM_KEY = "anim"
TRACKS_KEY = "tracks"
MODES_KEY = "track_modes"
INTERPS = ("spline", "linear", "step")
EASES = ("none", "in", "out", "both")
LOOPS = ("constant", "repeat", "offset", "oscillate")
PLAY_MODES = ("realtime", "all_frames")
AXES = ("x", "y", "z")
POSITION_CHANNELS = tuple(f"position.{a}" for a in AXES)
ROTATION_CHANNELS = tuple(f"rotation.{a}" for a in AXES)
SCALE_CHANNELS = tuple(f"scale.{a}" for a in AXES)
TRANSFORM_CHANNELS = POSITION_CHANNELS + ROTATION_CHANNELS + SCALE_CHANNELS
VISIBILITY = "visibility"
POINTS = "points"
PARAM_PREFIX = "param."
FRAME_EPS = 1e-6

DEFAULT_TIME = {
    "fps": 30,
    "min": 0,
    "max": 90,
    "preview_min": 0,
    "preview_max": 90,
    "frame": 0,
    "loop": True,
    "pingpong": False,
    "play_mode": "realtime",
    "default_interp": "spline",
}
PLAYBACK_MODES = ("simple", "loop", "pingpong")
PACK_KEY = "__pla__"
_SKIP_PARAM_KINDS = ("text", "runtime")

_VECTOR_ATTRS = {"position": "position", "rotation": "rotation", "scale": "scale"}
_BUSY: set[int] = set()
_CACHE: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _global_scene():
    try:
        from ..scene import get_scene
    except ImportError:
        return None
    return get_scene()


def begin_edit(scene=None) -> list:
    scenes = []
    for sc in (_global_scene(), scene):
        if sc is not None and not any(sc is x for x in scenes) and callable(getattr(sc, "begin_group", None)):
            scenes.append(sc)
    for sc in scenes:
        sc.begin_group()
    return scenes


def end_edit(token: list) -> None:
    for sc in token or ():
        try:
            sc.end_group()
        except RuntimeError:
            pass


@contextmanager
def edit_group(scene=None):
    token = begin_edit(scene)
    try:
        yield
    finally:
        end_edit(token)


def _num(value: Any, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if not math.isfinite(v):
        return float(fallback)
    return v


def _intish(v: float) -> int | float:
    r = round(v)
    return int(r) if abs(v - r) < FRAME_EPS else float(v)


def time_settings(scene) -> dict:
    raw = store.get_scene_data(scene, ANIM_KEY, None)
    out = dict(DEFAULT_TIME)
    if isinstance(raw, dict):
        out.update({k: v for k, v in raw.items() if k in DEFAULT_TIME})
    return _sanitize(out)


def _sanitize(s: dict) -> dict:
    out = dict(s)
    out["fps"] = int(min(240, max(1, round(_num(out["fps"], 30)))))
    lo = int(round(_num(out["min"], 0)))
    hi = int(round(_num(out["max"], 90)))
    if hi < lo:
        hi = lo
    out["min"], out["max"] = lo, hi
    pmin = int(round(_num(out["preview_min"], lo)))
    pmax = int(round(_num(out["preview_max"], hi)))
    pmin = min(max(pmin, lo), hi)
    pmax = min(max(pmax, lo), hi)
    if pmax < pmin:
        pmax = pmin
    out["preview_min"], out["preview_max"] = pmin, pmax
    out["frame"] = _intish(min(max(_num(out["frame"], lo), lo), hi))
    out["loop"] = bool(out["loop"])
    out["pingpong"] = bool(out["pingpong"])
    if out["play_mode"] not in PLAY_MODES:
        out["play_mode"] = "realtime"
    if out["default_interp"] not in INTERPS:
        out["default_interp"] = "spline"
    return out


def set_time_settings(scene, **changes) -> dict:
    return _apply_settings(scene, changes, True)


def _write_frame_direct(scene, frame: float) -> None:
    ex = store.scene_extras(scene)
    raw = ex.get(ANIM_KEY)
    if isinstance(raw, dict):
        if "frame" in raw and _same(raw["frame"], frame):
            return
        base = dict(raw)
    else:
        base = store.to_json(time_settings(scene))
    base["frame"] = frame
    ex[ANIM_KEY] = base
    store.notify(scene, ANIM_KEY)


def _apply_settings(scene, changes: dict, evaluate_scene: bool) -> dict:
    cur = time_settings(scene)
    new = dict(cur)
    for k, v in changes.items():
        if k not in DEFAULT_TIME:
            raise KeyError(f"unknown time setting {k!r}")
        new[k] = v
    if "min" in changes and "max" not in changes and _num(new["min"], 0) > new["max"]:
        new["max"] = new["min"]
    if "max" in changes and "min" not in changes and _num(new["max"], 0) < new["min"]:
        new["min"] = new["max"]
    if "min" in changes and "preview_min" not in changes and cur["preview_min"] == cur["min"]:
        new["preview_min"] = new["min"]
    if "max" in changes and "preview_max" not in changes and cur["preview_max"] == cur["max"]:
        new["preview_max"] = new["max"]
    if "preview_min" in changes and "preview_max" not in changes and _num(new["preview_min"], 0) > new["preview_max"]:
        new["preview_max"] = new["preview_min"]
    if "preview_max" in changes and "preview_min" not in changes and _num(new["preview_max"], 0) < new["preview_min"]:
        new["preview_min"] = new["preview_max"]
    new = _sanitize(new)
    stored = store.get_scene_data(scene, ANIM_KEY, None)
    only_frame = all(new[k] == cur[k] and type(new[k]) is type(cur[k]) for k in new if k != "frame")
    if not only_frame:
        store.set_scene_data(scene, ANIM_KEY, new)
    elif not isinstance(stored, dict) or not _same(new["frame"], cur["frame"]) or "frame" not in stored:
        _write_frame_direct(scene, new["frame"])
    if evaluate_scene and not _same(new["frame"], cur["frame"]):
        evaluate(scene, new["frame"])
    return new


def playback_mode(scene) -> str:
    s = time_settings(scene)
    if s["pingpong"]:
        return "pingpong"
    return "loop" if s["loop"] else "simple"


def set_playback_mode(scene, mode: str) -> str:
    if mode not in PLAYBACK_MODES:
        raise ValueError(f"unknown playback mode {mode!r}")
    set_time_settings(scene, loop=mode == "loop", pingpong=mode == "pingpong")
    return mode


def retime_document(scene, new_fps: float) -> int:
    s = time_settings(scene)
    old = s["fps"]
    new = int(min(240, max(1, round(_num(new_fps, old)))))
    if new == old:
        return 0
    r = new / old
    n = 0
    with edit_group(scene):
        for obj in list(scene.objects):
            data = _tracks_copy(obj)
            if not data:
                continue
            for keys in data.values():
                for k in keys:
                    k["frame"] = _intish(float(k["frame"]) * r)
                    for t in ("in_tan", "out_tan"):
                        if k.get(t) is not None:
                            k[t] = [float(k[t][0]) * r, float(k[t][1])]
                    n += 1
            _write_tracks(obj, data)
        _apply_settings(scene, {"fps": new, "min": round(s["min"] * r), "max": round(s["max"] * r),
                                "preview_min": round(s["preview_min"] * r),
                                "preview_max": round(s["preview_max"] * r),
                                "frame": float(s["frame"]) * r}, False)
    evaluate(scene)
    return n


def current_frame(scene) -> float:
    return time_settings(scene)["frame"]


def fps(scene) -> int:
    return time_settings(scene)["fps"]


def frame_to_seconds(scene, frame: float) -> float:
    return float(frame) / fps(scene)


def seconds_to_frame(scene, seconds: float) -> float:
    return float(seconds) * fps(scene)


def format_time(scene, frame: float, mode: str = "frames") -> str:
    f = _num(frame, 0.0)
    if mode == "frames":
        v = _intish(f)
        return f"{v} F" if isinstance(v, int) else f"{v:.2f} F"
    rate = fps(scene)
    if mode == "seconds":
        return f"{f / rate:.2f} s"
    n = int(round(abs(f)))
    sign = "-" if f < 0 and n else ""
    minutes, rest = divmod(n, rate * 60)
    seconds, frames = divmod(rest, rate)
    return f"{sign}{minutes:02d}:{seconds:02d}:{frames:02d}"


def set_frame(scene, frame: float, evaluate_scene: bool = True) -> float:
    s = _apply_settings(scene, {"frame": frame}, False)
    if evaluate_scene:
        evaluate(scene, s["frame"])
    return s["frame"]


def make_key(frame: float, value: Any, interp: str = "spline", ease: str = "none",
             in_tan: Iterable[float] | None = None, out_tan: Iterable[float] | None = None) -> dict:
    if interp not in INTERPS:
        raise ValueError(f"unknown interpolation {interp!r}")
    if ease not in EASES:
        raise ValueError(f"unknown ease {ease!r}")
    return {
        "frame": _intish(float(frame)),
        "value": _clean_value(value),
        "interp": interp,
        "in_tan": None if in_tan is None else [float(x) for x in in_tan],
        "out_tan": None if out_tan is None else [float(x) for x in out_tan],
        "ease": ease,
    }


def _clean_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return np.array(value, dtype=float)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    if isinstance(value, (list, tuple)):
        if all(isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) for v in value):
            return [float(v) for v in value]
        return list(value)
    return value


def _copy_key(key: dict) -> dict:
    out = dict(key)
    v = key.get("value")
    if isinstance(v, np.ndarray):
        out["value"] = v.copy()
    elif isinstance(v, list):
        out["value"] = list(v)
    for t in ("in_tan", "out_tan"):
        if key.get(t) is not None:
            out[t] = list(key[t])
    return out


def _normalize_key(key: dict) -> dict:
    out = _copy_key(key)
    out["frame"] = _intish(_num(out.get("frame", 0), 0))
    out["value"] = _clean_value(_as_value(out.get("value")))
    if out.get("interp") not in INTERPS:
        out["interp"] = "spline"
    if out.get("ease") not in EASES:
        out["ease"] = "none"
    out.setdefault("in_tan", None)
    out.setdefault("out_tan", None)
    return out


def _pack(arr: np.ndarray) -> dict:
    a = np.ascontiguousarray(arr, dtype=np.float64)
    return {PACK_KEY: base64.b64encode(a.tobytes()).decode("ascii"), "shape": [int(x) for x in a.shape]}


def _unpack(d: dict) -> np.ndarray:
    try:
        arr = np.frombuffer(base64.b64decode(d[PACK_KEY]), dtype=np.float64)
    except (TypeError, ValueError):
        return np.zeros(0)
    shape = tuple(int(x) for x in d.get("shape") or ())
    if shape and int(np.prod(shape)) == arr.size:
        return arr.reshape(shape)
    return arr


def _as_value(v: Any) -> Any:
    if isinstance(v, dict):
        if PACK_KEY in v:
            return _unpack(v)
        if "__ndarray__" in v:
            return store.from_json(v)
    if isinstance(v, list) and v and isinstance(v[0], list):
        return np.asarray(v, float)
    return v


def _decode_tracks(raw: dict) -> dict:
    out: dict = {}
    for ch, keys in raw.items():
        if not isinstance(keys, list):
            continue
        lst = []
        for k in keys:
            if not isinstance(k, dict) or "frame" not in k:
                continue
            d = {}
            for name, v in k.items():
                if name == "value":
                    d[name] = _as_value(v)
                elif isinstance(v, (dict, list)):
                    d[name] = store.from_json(v)
                else:
                    d[name] = v
            d.setdefault("value", None)
            lst.append(d)
        out[ch] = lst
    return out


def tracks(obj) -> dict:
    raw = store.object_extras(obj).get(TRACKS_KEY)
    if not isinstance(raw, dict):
        return {}
    try:
        hit = _CACHE.get(obj)
    except TypeError:
        return _decode_tracks(raw)
    if hit is not None and hit[0] is raw:
        return hit[1]
    data = _decode_tracks(raw)
    try:
        _CACHE[obj] = (raw, data)
    except TypeError:
        pass
    return data


def get_track(obj, channel: str) -> list:
    keys = tracks(obj).get(channel)
    return keys if isinstance(keys, list) else []


def _encode_tracks(data: dict) -> dict:
    out: dict = {}
    for ch, keys in data.items():
        if not keys:
            continue
        enc = []
        for k in keys:
            d = dict(k)
            v = d.get("value")
            if isinstance(v, np.ndarray):
                d["value"] = _pack(v)
            enc.append(d)
        out[ch] = enc
    return out


def _write_tracks(obj, data: dict) -> None:
    clean = _encode_tracks(data)
    with edit_group():
        store.set_object(obj, TRACKS_KEY, clean if clean else None)
        modes = track_modes(obj)
        if modes and any(ch not in clean for ch in modes):
            kept = {ch: m for ch, m in modes.items() if ch in clean}
            store.set_object(obj, MODES_KEY, kept if kept else None)


def _tracks_copy(obj) -> dict:
    return {ch: [_normalize_key(k) for k in keys] for ch, keys in tracks(obj).items() if isinstance(keys, list)}


def set_track(obj, channel: str, keys: Iterable[dict]) -> list:
    data = _tracks_copy(obj)
    clean = sorted((_normalize_key(k) for k in keys), key=lambda k: k["frame"])
    merged: list[dict] = []
    for k in clean:
        if merged and abs(merged[-1]["frame"] - k["frame"]) < FRAME_EPS:
            merged[-1] = k
        else:
            merged.append(k)
    data[channel] = merged
    _write_tracks(obj, data)
    return merged


def track_modes(obj) -> dict:
    raw = store.get_object(obj, MODES_KEY, None)
    return raw if isinstance(raw, dict) else {}


def loop_mode(obj, channel: str) -> tuple[str, str]:
    m = track_modes(obj).get(channel) or {}
    before = m.get("before", "constant")
    after = m.get("after", "constant")
    return (before if before in LOOPS else "constant", after if after in LOOPS else "constant")


def set_loop(obj, channel: str, before: str | None = None, after: str | None = None) -> tuple[str, str]:
    for v in (before, after):
        if v is not None and v not in LOOPS:
            raise ValueError(f"unknown loop mode {v!r}")
    cur_b, cur_a = loop_mode(obj, channel)
    b = cur_b if before is None else before
    a = cur_a if after is None else after
    modes = {ch: dict(m) for ch, m in track_modes(obj).items()}
    if b == "constant" and a == "constant":
        modes.pop(channel, None)
    else:
        modes[channel] = {"before": b, "after": a}
    store.set_object(obj, MODES_KEY, modes if modes else None)
    return b, a


def has_animation(obj) -> bool:
    return any(bool(k) for k in tracks(obj).values())


def animated_objects(scene) -> list:
    return [o for o in scene.objects if has_animation(o)]


def channel_sort_key(channel: str) -> tuple:
    if channel in TRANSFORM_CHANNELS:
        return (0, TRANSFORM_CHANNELS.index(channel), channel)
    if channel == VISIBILITY:
        return (1, 0, channel)
    if channel.startswith(PARAM_PREFIX):
        return (2, 0, channel)
    if channel == POINTS:
        return (3, 0, channel)
    return (4, 0, channel)


def channels_of(obj) -> list[str]:
    return sorted((ch for ch, keys in tracks(obj).items() if keys), key=channel_sort_key)


def _spec(obj):
    try:
        from ..objects import registry
    except Exception:
        return None
    return registry.SPECS.get(getattr(obj, "kind", ""))


def param_channels(obj, numeric_only: bool = False) -> list[str]:
    out = []
    spec = _spec(obj)
    keys = [p.key for p in spec.params] if spec is not None else list(getattr(obj, "params", {}))
    for k in keys:
        if numeric_only:
            v = obj.params.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
        out.append(PARAM_PREFIX + k)
    return out


def is_scalar_channel(obj, channel: str) -> bool:
    if channel in TRANSFORM_CHANNELS or channel == VISIBILITY:
        return True
    if channel == POINTS:
        return False
    keys = get_track(obj, channel)
    if keys:
        return all(_is_number(k["value"]) for k in keys)
    v = channel_value(obj, channel)
    return _is_number(v)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_))


def _is_vector(v: Any) -> bool:
    if isinstance(v, np.ndarray):
        return v.dtype.kind in "fiu"
    if isinstance(v, (list, tuple)) and v:
        return all(_is_number(x) for x in v)
    return False


def channel_label(channel: str, obj=None) -> str:
    if "." in channel and channel.split(".", 1)[0] in _VECTOR_ATTRS:
        attr, axis = channel.split(".", 1)
        return f"{attr.capitalize()} {axis.upper()}"
    if channel == VISIBILITY:
        return "Visibility"
    if channel == POINTS:
        return "Point Level"
    if channel.startswith(PARAM_PREFIX):
        key = channel[len(PARAM_PREFIX):]
        spec = _spec(obj) if obj is not None else None
        p = spec.param(key) if spec is not None else None
        return p.label if p is not None else key.replace("_", " ").title()
    return channel


def channel_value(obj, channel: str) -> Any:
    head, _, tail = channel.partition(".")
    if head in _VECTOR_ATTRS and tail in AXES:
        return float(getattr(obj, _VECTOR_ATTRS[head])[AXES.index(tail)])
    if channel == VISIBILITY:
        return 1.0 if getattr(obj, "enabled", True) else 0.0
    if channel == POINTS:
        return np.array(obj.mesh.points, dtype=float)
    if channel.startswith(PARAM_PREFIX):
        key = channel[len(PARAM_PREFIX):]
        if key not in obj.params:
            return None
        return _clean_value(obj.params[key])
    return None


def apply_channel(obj, channel: str, value: Any) -> str:
    head, _, tail = channel.partition(".")
    if head in _VECTOR_ATTRS and tail in AXES:
        if not _is_number(value):
            return ""
        attr = _VECTOR_ATTRS[head]
        vec = np.array(getattr(obj, attr), dtype=float)
        i = AXES.index(tail)
        v = float(value)
        if abs(vec[i] - v) <= 1e-12:
            return ""
        vec[i] = v
        setattr(obj, attr, vec)
        return "transform"
    if channel == VISIBILITY:
        flag = bool(value >= 0.5) if _is_number(value) else bool(value)
        if bool(getattr(obj, "enabled", True)) == flag:
            return ""
        obj.enabled = flag
        return "visibility"
    if channel == POINTS:
        arr = np.asarray(value, dtype=float)
        pts = obj.mesh.points
        if arr.shape != pts.shape:
            return ""
        if np.array_equal(arr, pts):
            return ""
        obj.mesh.points = arr.copy()
        return "points"
    if channel.startswith(PARAM_PREFIX):
        key = channel[len(PARAM_PREFIX):]
        spec = _spec(obj)
        p = spec.param(key) if spec is not None else None
        v = value
        if p is not None:
            if p.kind == "bool" and _is_number(v):
                v = bool(v >= 0.5)
            elif p.kind == "choice" and _is_number(v) and p.choices:
                v = p.choices[int(min(max(round(v), 0), len(p.choices) - 1))]
            elif p.kind == "vector" and isinstance(v, np.ndarray):
                v = tuple(float(x) for x in v)
            try:
                v = p.clamp(v)
            except (TypeError, ValueError):
                return ""
        elif isinstance(v, np.ndarray):
            v = tuple(float(x) for x in v)
        old = obj.params.get(key)
        if _same(old, v):
            return ""
        obj.params[key] = v
        if hasattr(obj, "_dirty"):
            obj._dirty = True
        return "param"
    return ""


def _same(a: Any, b: Any) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return abs(a - b) <= 1e-12
    return a == b


def _vals(keys: list) -> list:
    out = []
    for k in keys:
        v = k["value"]
        out.append(np.asarray(v, float) if isinstance(v, (list, tuple, np.ndarray)) else v)
    return out


def _zero_like(v: Any) -> Any:
    return np.zeros_like(v, dtype=float) if isinstance(v, np.ndarray) else 0.0


def _slope3(fa: float, fi: float, fb: float, a: Any, v: Any, b: Any) -> Any:
    df0 = fi - fa
    df1 = fb - fi
    if _is_number(v):
        if not (_is_number(a) and _is_number(b)) or df0 <= 0 or df1 <= 0:
            return 0.0
        d0 = (float(v) - float(a)) / df0
        d1 = (float(b) - float(v)) / df1
        if d0 * d1 <= 0:
            return 0.0
        lim = 3.0 * min(abs(d0), abs(d1))
        s = (float(b) - float(a)) / (df0 + df1)
        return max(-lim, min(lim, s))
    if not isinstance(v, np.ndarray):
        return 0.0
    if df0 <= 0 or df1 <= 0:
        return np.zeros_like(v, dtype=float)
    try:
        va = np.asarray(a, float)
        vb = np.asarray(b, float)
    except (TypeError, ValueError):
        return np.zeros_like(v, dtype=float)
    vv = np.asarray(v, float)
    if va.shape != vv.shape or vb.shape != vv.shape:
        return np.zeros_like(vv)
    d0 = (vv - va) / df0
    d1 = (vb - vv) / df1
    s = (vb - va) / (df0 + df1)
    limit = 3.0 * np.minimum(np.abs(d0), np.abs(d1))
    return np.asarray(np.where(d0 * d1 <= 0, 0.0, np.clip(s, -limit, limit)), float)


def _vec(v: Any) -> Any:
    return np.asarray(v, float) if isinstance(v, (list, tuple, np.ndarray)) and _is_vector(v) else v


def _slope_at(keys: list, i: int) -> Any:
    v = _vec(keys[i]["value"])
    if i <= 0 or i >= len(keys) - 1:
        return _zero_like(v)
    return _slope3(float(keys[i - 1]["frame"]), float(keys[i]["frame"]), float(keys[i + 1]["frame"]),
                   _vec(keys[i - 1]["value"]), v, _vec(keys[i + 1]["value"]))


def auto_slopes(frames: list[float], values: list) -> list:
    n = len(frames)
    vals = [_vec(v) for v in values]
    out: list = []
    for i in range(n):
        if i == 0 or i == n - 1:
            out.append(_zero_like(vals[i]))
            continue
        out.append(_slope3(float(frames[i - 1]), float(frames[i]), float(frames[i + 1]),
                           vals[i - 1], vals[i], vals[i + 1]))
    return out


def _seg_len(keys: list, i: int, side: int) -> float:
    j = i + side
    if 0 <= j < len(keys):
        return abs(float(keys[j]["frame"]) - float(keys[i]["frame"]))
    if 0 <= i - side < len(keys):
        return abs(float(keys[i]["frame"]) - float(keys[i - side]["frame"]))
    return 3.0


def key_tangents(keys: list, i: int, slopes: list | None = None) -> tuple[list[float], list[float]]:
    k = keys[i]
    s = slopes[i] if slopes is not None else _slope_at(keys, i)
    s = float(s) if _is_number(s) else 0.0
    ease = k.get("ease", "none")
    s_in = 0.0 if ease in ("in", "both") else s
    s_out = 0.0 if ease in ("out", "both") else s
    lin = _seg_len(keys, i, -1) / 3.0
    lout = _seg_len(keys, i, 1) / 3.0
    tin = k.get("in_tan")
    tout = k.get("out_tan")
    in_tan = [float(tin[0]), float(tin[1])] if tin is not None else [-lin, -lin * s_in]
    out_tan = [float(tout[0]), float(tout[1])] if tout is not None else [lout, lout * s_out]
    if ease in ("in", "both") and tin is None:
        in_tan[1] = 0.0
    if ease in ("out", "both") and tout is None:
        out_tan[1] = 0.0
    return in_tan, out_tan


def _bezier_scalar(f: float, fa: float, va: float, out_tan: list, fb: float, vb: float, in_tan: list) -> float:
    span = fb - fa
    odt = min(max(out_tan[0], 0.0), span)
    idt = min(max(-in_tan[0], 0.0), span)
    ov = out_tan[1] * (odt / out_tan[0]) if out_tan[0] > 1e-12 else 0.0
    iv = in_tan[1] * (idt / -in_tan[0]) if in_tan[0] < -1e-12 else 0.0
    x0, x1, x2, x3 = fa, fa + odt, fb - idt, fb
    y0, y1, y2, y3 = va, va + ov, vb + iv, vb
    lo, hi = 0.0, 1.0
    t = (f - fa) / span if span > 0 else 0.0
    for _ in range(64):
        mt = 1.0 - t
        x = mt * mt * mt * x0 + 3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t * t * t * x3
        err = x - f
        if abs(err) < 1e-9:
            break
        if err > 0:
            hi = t
        else:
            lo = t
        dx = 3 * mt * mt * (x1 - x0) + 6 * mt * t * (x2 - x1) + 3 * t * t * (x3 - x2)
        nt = t - err / dx if abs(dx) > 1e-12 else -1.0
        t = nt if lo < nt < hi else 0.5 * (lo + hi)
    mt = 1.0 - t
    return mt * mt * mt * y0 + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t * t * t * y3


def _hermite(f: float, fa: float, va, sa, fb: float, vb, sb):
    h = fb - fa
    u = (f - fa) / h
    u2, u3 = u * u, u * u * u
    h00 = 2 * u3 - 3 * u2 + 1
    h10 = u3 - 2 * u2 + u
    h01 = -2 * u3 + 3 * u2
    h11 = u3 - u2
    return h00 * va + h10 * h * sa + h01 * vb + h11 * h * sb


def _eval_inside(keys: list, f: float):
    n = len(keys)
    if f <= float(keys[0]["frame"]):
        return _out(keys[0]["value"])
    if f >= float(keys[-1]["frame"]):
        return _out(keys[-1]["value"])
    lo, hi = 0, n - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if float(keys[mid]["frame"]) <= f:
            lo = mid
        else:
            hi = mid
    a, b = keys[lo], keys[hi]
    fa, fb = float(a["frame"]), float(b["frame"])
    va, vb = a["value"], b["value"]
    interp = a.get("interp", "spline")
    numeric = _is_number(va) and _is_number(vb)
    vector = _is_vector(va) and _is_vector(vb) and np.shape(np.asarray(va)) == np.shape(np.asarray(vb))
    if interp == "step" or not (numeric or vector):
        return _out(va)
    u = (f - fa) / (fb - fa)
    if interp == "linear":
        if numeric:
            return float(va) + (float(vb) - float(va)) * u
        return np.asarray(va, float) + (np.asarray(vb, float) - np.asarray(va, float)) * u
    if numeric:
        _, out_a = key_tangents(keys, lo)
        in_b, _ = key_tangents(keys, hi)
        return float(_bezier_scalar(f, fa, float(va), out_a, fb, float(vb), in_b))
    va_arr = np.asarray(va, float)
    vb_arr = np.asarray(vb, float)
    sa = np.asarray(_slope_at(keys, lo), float)
    sb = np.asarray(_slope_at(keys, hi), float)
    if sa.shape != va_arr.shape:
        sa = np.zeros_like(va_arr)
    if sb.shape != vb_arr.shape:
        sb = np.zeros_like(vb_arr)
    if a.get("ease") in ("out", "both"):
        sa = np.zeros_like(sa)
    if b.get("ease") in ("in", "both"):
        sb = np.zeros_like(sb)
    return _hermite(f, fa, va_arr, sa, fb, vb_arr, sb)


def _out(v):
    if isinstance(v, np.ndarray):
        return v.copy()
    if isinstance(v, list):
        return np.asarray(v, float) if _is_vector(v) else list(v)
    return v


def _wrap(f: float, f0: float, f1: float, mode: str) -> tuple[float, int]:
    span = f1 - f0
    if span <= FRAME_EPS or mode == "constant":
        return min(max(f, f0), f1), 0
    k = math.floor((f - f0) / span)
    r = (f - f0) - k * span
    if mode == "oscillate":
        return (f1 - r if k % 2 else f0 + r), 0
    return f0 + r, k


def evaluate_track(keys: list, frame: float, before: str = "constant", after: str = "constant"):
    if not keys:
        return None
    f = _num(frame, float("nan")) if not isinstance(frame, (int, float)) else float(frame)
    f0 = float(keys[0]["frame"])
    f1 = float(keys[-1]["frame"])
    if math.isnan(f):
        f = f0
    cycles = 0
    mode = "constant"
    if f < f0:
        mode = before
    elif f > f1:
        mode = after
    if mode != "constant" and math.isfinite(f):
        f, cycles = _wrap(f, f0, f1, mode)
    v = _eval_inside(keys, f)
    if mode == "offset" and cycles:
        v0, v1 = keys[0]["value"], keys[-1]["value"]
        if _is_number(v0) and _is_number(v1):
            v = float(v) + cycles * (float(v1) - float(v0))
        elif _is_vector(v0) and _is_vector(v1):
            v = np.asarray(v, float) + cycles * (np.asarray(v1, float) - np.asarray(v0, float))
    return v


def evaluate_channel(obj, channel: str, frame: float):
    keys = get_track(obj, channel)
    if not keys:
        return None
    before, after = loop_mode(obj, channel)
    return evaluate_track(keys, frame, before, after)


def is_evaluating(scene) -> bool:
    return id(scene) in _BUSY


def evaluate(scene, frame: float | None = None, emit: bool = True) -> list:
    f = current_frame(scene) if frame is None else float(frame)
    touched = []
    rebuild = False
    _BUSY.add(id(scene))
    try:
        for obj in list(scene.objects):
            data = tracks(obj)
            if not data:
                continue
            changed = False
            for ch in sorted(data, key=channel_sort_key):
                keys = data[ch]
                if not keys:
                    continue
                before, after = loop_mode(obj, ch)
                value = evaluate_track(keys, f, before, after)
                if value is None:
                    continue
                kind = apply_channel(obj, ch, value)
                if kind:
                    changed = True
                    if kind in ("param", "visibility", "points"):
                        rebuild = True
            if changed:
                touched.append(obj)
        if rebuild:
            ev = getattr(scene, "evaluate", None)
            if callable(ev):
                ev()
        if touched and emit:
            sig = getattr(scene, "changed", None)
            if sig is not None:
                sig.emit()
    finally:
        _BUSY.discard(id(scene))
    return touched


def _default_interp(scene, channel: str) -> str:
    if channel == VISIBILITY:
        return "step"
    if channel == POINTS:
        return "linear"
    if scene is None:
        return "spline"
    return time_settings(scene)["default_interp"]


def _find(keys: list, frame: float) -> int:
    f = float(frame)
    lo, hi = 0, len(keys)
    while lo < hi:
        mid = (lo + hi) // 2
        if float(keys[mid]["frame"]) < f - FRAME_EPS:
            lo = mid + 1
        else:
            hi = mid
    if lo < len(keys) and abs(float(keys[lo]["frame"]) - f) < FRAME_EPS:
        return lo
    return -1


def find_key(obj, channel: str, frame: float) -> int:
    return _find(get_track(obj, channel), frame)


def insert_key(obj, channel: str, frame: float, value: Any = None, interp: str | None = None,
               ease: str | None = None, scene=None) -> dict:
    if value is None:
        value = channel_value(obj, channel)
    if value is None:
        raise KeyError(f"{getattr(obj, 'name', obj)!r} has no channel {channel!r}")
    data = _tracks_copy(obj)
    keys = data.setdefault(channel, [])
    f = _intish(float(frame))
    for k in keys:
        if abs(float(k["frame"]) - f) < FRAME_EPS:
            k["value"] = _clean_value(value)
            if interp is not None:
                k["interp"] = interp
            if ease is not None:
                k["ease"] = ease
            _write_tracks(obj, data)
            return k
    if interp is None:
        interp = _default_interp(scene, channel)
    if not _is_number(value) and not _is_vector(value) and interp != "step":
        interp = "step"
    key = make_key(f, value, interp, ease or "none")
    keys.append(key)
    keys.sort(key=lambda k: k["frame"])
    _write_tracks(obj, data)
    return key


def _scene_or_default(scene):
    if scene is not None:
        return scene
    from ..scene import get_scene
    return get_scene()


def set_key(obj, channels: Iterable[str] | None = None, frame: float | None = None, scene=None,
            interp: str | None = None) -> int:
    scene = _scene_or_default(scene)
    f = current_frame(scene) if frame is None else float(frame)
    chans = list(TRANSFORM_CHANNELS if channels is None else channels)
    data = _tracks_copy(obj)
    count = 0
    for ch in chans:
        value = channel_value(obj, ch)
        if value is None:
            continue
        keys = data.setdefault(ch, [])
        fi = _intish(f)
        hit = next((k for k in keys if abs(float(k["frame"]) - fi) < FRAME_EPS), None)
        if hit is not None:
            hit["value"] = _clean_value(value)
            if interp is not None:
                hit["interp"] = interp
        else:
            mode = interp or _default_interp(scene, ch)
            if not _is_number(value) and not _is_vector(value):
                mode = "step"
            keys.append(make_key(fi, value, mode))
            keys.sort(key=lambda k: k["frame"])
        count += 1
    if count:
        _write_tracks(obj, data)
    return count


def _targets(scene) -> list:
    objs = list(scene.selected_objects()) if hasattr(scene, "selected_objects") else []
    if not objs and getattr(scene, "active", None) is not None:
        objs = [scene.active]
    return [o for o in objs if o in scene.objects]


def record_objects(scene, objects: Iterable, channels: Iterable[str] | None = None,
                   frame: float | None = None) -> int:
    chans = None if channels is None else list(channels)
    with edit_group(scene):
        return sum(set_key(o, chans, frame, scene) for o in list(objects))


def record_active(scene, channels: Iterable[str] | None = None, frame: float | None = None) -> int:
    return record_objects(scene, _targets(scene), channels, frame)


def record_points(scene, frame: float | None = None) -> int:
    objs = [o for o in _targets(scene) if getattr(o, "kind", "") == "polygon" and len(o.mesh.points)]
    return record_objects(scene, objs, [POINTS], frame)


def _keyable_value(v: Any) -> bool:
    if isinstance(v, (bool, np.bool_)) or _is_number(v):
        return True
    if isinstance(v, str):
        return True
    return _is_vector(v)


def keyable_params(obj) -> list[str]:
    spec = _spec(obj)
    params = getattr(obj, "params", {}) or {}
    out = []
    if spec is not None:
        for p in spec.params:
            if p.kind in _SKIP_PARAM_KINDS or p.key not in params:
                continue
            v = params[p.key]
            if p.kind == "choice" or (not isinstance(v, str) and _keyable_value(v)):
                out.append(PARAM_PREFIX + p.key)
        return out
    for k, v in params.items():
        if isinstance(v, str):
            continue
        if _keyable_value(v):
            out.append(PARAM_PREFIX + k)
    return out


def keyable_channels(obj) -> list[str]:
    out = list(TRANSFORM_CHANNELS) + [VISIBILITY] + keyable_params(obj)
    if getattr(obj, "kind", "") == "polygon" and len(getattr(obj.mesh, "points", ())):
        out.append(POINTS)
    return out


def record_params(scene, keys: Iterable[str] | None = None, frame: float | None = None,
                  objects: Iterable | None = None) -> int:
    objs = _targets(scene) if objects is None else list(objects)
    wanted = None if keys is None else {k if k.startswith(PARAM_PREFIX) else PARAM_PREFIX + k for k in keys}
    n = 0
    with edit_group(scene):
        for o in objs:
            chans = [ch for ch in keyable_params(o) if wanted is None or ch in wanted]
            if chans:
                n += set_key(o, chans, frame, scene)
    return n


def record_visibility(scene, frame: float | None = None, objects: Iterable | None = None) -> int:
    objs = _targets(scene) if objects is None else list(objects)
    return record_objects(scene, objs, [VISIBILITY], frame)


def record_point_selection(scene, frame: float | None = None) -> int:
    obj = getattr(scene, "active", None)
    if obj is None or obj not in scene.objects or getattr(obj, "kind", "") != "polygon":
        return 0
    pts = np.array(obj.mesh.points, dtype=float)
    sel = sorted(i for i in getattr(scene, "selected_points", ()) if 0 <= i < len(pts))
    if not sel or not len(pts):
        return 0
    f = current_frame(scene) if frame is None else float(frame)
    base = evaluate_channel(obj, POINTS, f)
    if isinstance(base, np.ndarray) and base.shape == pts.shape:
        value = np.array(base, dtype=float)
        value[sel] = pts[sel]
    else:
        value = pts
    insert_key(obj, POINTS, f, value, scene=scene)
    return 1


def clear_points(scene, objects: Iterable | None = None) -> int:
    objs = _targets(scene) if objects is None else list(objects)
    n = 0
    with edit_group(scene):
        for o in objs:
            if get_track(o, POINTS):
                n += clear_tracks(o, [POINTS])
    return n


def delete_key(obj, channel: str, frame: float) -> bool:
    data = _tracks_copy(obj)
    keys = data.get(channel, [])
    kept = [k for k in keys if abs(float(k["frame"]) - float(frame)) >= FRAME_EPS]
    if len(kept) == len(keys):
        return False
    data[channel] = kept
    _write_tracks(obj, data)
    return True


def _group(refs: Iterable) -> dict:
    out: dict = {}
    for obj, ch, f in refs:
        entry = out.setdefault(id(obj), (obj, {}))
        entry[1].setdefault(ch, []).append(float(f))
    return out


def _in(frames: list[float], f: float) -> bool:
    return any(abs(float(f) - x) < FRAME_EPS for x in frames)


def delete_keys(refs: Iterable) -> int:
    count = 0
    with edit_group():
        for obj, chans in _group(refs).values():
            data = _tracks_copy(obj)
            n = 0
            for ch, frames in chans.items():
                keys = data.get(ch, [])
                kept = [k for k in keys if not _in(frames, k["frame"])]
                n += len(keys) - len(kept)
                data[ch] = kept
            if n:
                _write_tracks(obj, data)
            count += n
    return count


def delete_keys_at(obj, frame: float, channels: Iterable[str] | None = None) -> int:
    chans = channels_of(obj) if channels is None else list(channels)
    return delete_keys((obj, ch, frame) for ch in chans)


def clear_tracks(obj, channels: Iterable[str] | None = None) -> int:
    if channels is None:
        n = sum(len(k) for k in tracks(obj).values())
        with edit_group():
            store.set_object(obj, TRACKS_KEY, None)
            store.set_object(obj, MODES_KEY, None)
        return n
    data = _tracks_copy(obj)
    n = 0
    for ch in channels:
        n += len(data.pop(ch, []))
    _write_tracks(obj, data)
    return n


def _remap(refs: Iterable, fn, snap: bool) -> list:
    with edit_group():
        return _remap_inner(refs, fn, snap)


def _remap_inner(refs: Iterable, fn, snap: bool) -> list:
    out = []
    for obj, chans in _group(refs).values():
        data = _tracks_copy(obj)
        for ch, frames in chans.items():
            keys = data.get(ch, [])
            moving = [k for k in keys if _in(frames, k["frame"])]
            staying = [k for k in keys if not _in(frames, k["frame"])]
            moved = []
            gap = 1.0 if snap else 1e-3
            last = None
            for k in moving:
                nf = fn(float(k["frame"]))
                if snap:
                    nf = float(round(nf))
                if last is not None and nf < last + gap:
                    nf = last + gap
                last = nf
                k["frame"] = _intish(nf)
                moved.append(k)
            merged = {}
            for k in staying:
                merged[round(float(k["frame"]) / FRAME_EPS)] = k
            for k in moved:
                merged[round(float(k["frame"]) / FRAME_EPS)] = k
            data[ch] = sorted(merged.values(), key=lambda k: k["frame"])
            for k in moved:
                ref = (obj, ch, k["frame"])
                if not any(r[0] is obj and r[1] == ch and abs(float(r[2]) - float(k["frame"])) < FRAME_EPS for r in out):
                    out.append(ref)
        _write_tracks(obj, data)
    return out


def move_keys(refs: Iterable, delta: float, snap: bool = True) -> list:
    d = float(delta)
    return _remap(refs, lambda f: f + d, snap)


def scale_keys(refs: Iterable, factor: float, pivot: float | None = None, snap: bool = True) -> list:
    refs = list(refs)
    if not refs:
        return []
    s = _num(factor, 0.0)
    if s <= 0:
        raise ValueError(f"scale factor must be positive, got {factor!r}")
    p = min(float(r[2]) for r in refs) if pivot is None else float(pivot)
    return _remap(refs, lambda f: p + (f - p) * s, snap)


def reverse_keys(refs: Iterable) -> list:
    refs = list(refs)
    if not refs:
        return []
    lo = min(float(r[2]) for r in refs)
    hi = max(float(r[2]) for r in refs)
    out: list = []
    swap = {"in": "out", "out": "in"}
    with edit_group():
        for obj, chans in _group(refs).values():
            data = _tracks_copy(obj)
            for ch, frames in chans.items():
                keys = data.get(ch, [])
                moving = sorted((k for k in keys if _in(frames, k["frame"])), key=lambda k: float(k["frame"]))
                if not moving:
                    continue
                staying = [k for k in keys if not _in(frames, k["frame"])]
                interps = [k.get("interp", "spline") for k in moving]
                for k in moving:
                    k["frame"] = _intish(lo + hi - float(k["frame"]))
                    tin, tout = k.get("in_tan"), k.get("out_tan")
                    k["in_tan"] = None if tout is None else [-float(tout[0]), float(tout[1])]
                    k["out_tan"] = None if tin is None else [-float(tin[0]), float(tin[1])]
                    k["ease"] = swap.get(k.get("ease", "none"), k.get("ease", "none"))
                for i in range(len(moving) - 1):
                    moving[i + 1]["interp"] = interps[i]
                merged = {}
                for k in staying:
                    merged[round(float(k["frame"]) / FRAME_EPS)] = k
                for k in moving:
                    merged[round(float(k["frame"]) / FRAME_EPS)] = k
                data[ch] = sorted(merged.values(), key=lambda k: k["frame"])
                out.extend((obj, ch, k["frame"]) for k in sorted(moving, key=lambda k: float(k["frame"])))
            _write_tracks(obj, data)
    return out


def offset_key_values(refs: Iterable, delta: float) -> int:
    n = 0
    d = float(delta)
    with edit_group():
        for obj, chans in _group(refs).values():
            data = _tracks_copy(obj)
            for ch, frames in chans.items():
                for k in data.get(ch, []):
                    if _in(frames, k["frame"]) and _is_number(k["value"]):
                        k["value"] = float(k["value"]) + d
                        n += 1
            _write_tracks(obj, data)
    return n


def set_key_value(obj, channel: str, frame: float, value: Any) -> bool:
    data = _tracks_copy(obj)
    for k in data.get(channel, []):
        if abs(float(k["frame"]) - float(frame)) < FRAME_EPS:
            k["value"] = _clean_value(value)
            _write_tracks(obj, data)
            return True
    return False


def set_key_attrs(refs: Iterable, interp: str | None = None, ease: str | None = None,
                  reset_tangents: bool = False) -> int:
    if interp is not None and interp not in INTERPS:
        raise ValueError(f"unknown interpolation {interp!r}")
    if ease is not None and ease not in EASES:
        raise ValueError(f"unknown ease {ease!r}")
    with edit_group():
        return _set_key_attrs(refs, interp, ease, reset_tangents)


def _set_key_attrs(refs, interp, ease, reset_tangents) -> int:
    n = 0
    for obj, chans in _group(refs).values():
        data = _tracks_copy(obj)
        for ch, frames in chans.items():
            for k in data.get(ch, []):
                if not _in(frames, k["frame"]):
                    continue
                if interp is not None:
                    k["interp"] = interp if (_is_number(k["value"]) or _is_vector(k["value"])) else "step"
                if ease is not None:
                    k["ease"] = ease
                    if ease != "none":
                        if ease in ("in", "both"):
                            k["in_tan"] = None
                        if ease in ("out", "both"):
                            k["out_tan"] = None
                if reset_tangents:
                    k["in_tan"] = None
                    k["out_tan"] = None
                n += 1
        _write_tracks(obj, data)
    return n


def set_tangents(obj, channel: str, frame: float, in_tan: Iterable[float] | None = None,
                 out_tan: Iterable[float] | None = None) -> bool:
    data = _tracks_copy(obj)
    keys = data.get(channel, [])
    for i, k in enumerate(keys):
        if abs(float(k["frame"]) - float(frame)) >= FRAME_EPS:
            continue
        cur_in, cur_out = key_tangents(keys, i)
        if in_tan is not None:
            t = [float(x) for x in in_tan]
            t[0] = min(t[0], -1e-3)
            k["in_tan"] = t
        elif k.get("in_tan") is None and out_tan is not None:
            k["in_tan"] = cur_in
        if out_tan is not None:
            t = [float(x) for x in out_tan]
            t[0] = max(t[0], 1e-3)
            k["out_tan"] = t
        elif k.get("out_tan") is None and in_tan is not None:
            k["out_tan"] = cur_out
        k["ease"] = "none"
        _write_tracks(obj, data)
        return True
    return False


def reset_tangents(refs: Iterable) -> int:
    return set_key_attrs(refs, ease="none", reset_tangents=True)


def flatten_tangents(refs: Iterable) -> int:
    with edit_group():
        return _flatten_tangents(refs)


def _flatten_tangents(refs: Iterable) -> int:
    n = 0
    for obj, chans in _group(refs).values():
        data = _tracks_copy(obj)
        for ch, frames in chans.items():
            keys = data.get(ch, [])
            for i, k in enumerate(keys):
                if not _in(frames, k["frame"]) or not _is_number(k["value"]):
                    continue
                cur_in, cur_out = key_tangents(keys, i)
                k["in_tan"] = [cur_in[0], 0.0]
                k["out_tan"] = [cur_out[0], 0.0]
                n += 1
        _write_tracks(obj, data)
    return n


def copy_keys(refs: Iterable) -> dict:
    refs = list(refs)
    if not refs:
        return {"base": 0, "items": []}
    base = min(float(r[2]) for r in refs)
    items = []
    for obj, ch, f in refs:
        i = find_key(obj, ch, f)
        if i < 0:
            continue
        key = _copy_key(get_track(obj, ch)[i])
        items.append({"object": obj.name, "channel": ch, "offset": float(key["frame"]) - base, "key": key})
    return {"base": base, "items": items}


def paste_keys(scene, clip: dict, frame: float | None = None, targets: Iterable | None = None) -> list:
    items = list((clip or {}).get("items", []))
    if not items:
        return []
    f0 = current_frame(scene) if frame is None else float(frame)
    sources = sorted({it["object"] for it in items})
    chosen = list(targets) if targets is not None else _targets(scene)
    plan: list = []
    if len(sources) == 1:
        dest = chosen or [o for o in scene.objects if o.name == sources[0]]
        for obj in dest:
            plan.extend((obj, it) for it in items)
    else:
        explicit = list(targets) if targets else []
        pool = {o.name: o for o in (explicit or scene.objects)}
        for it in items:
            obj = pool.get(it["object"])
            if obj is not None:
                plan.append((obj, it))
    out = []
    grouped: dict = {}
    for obj, it in plan:
        grouped.setdefault(id(obj), (obj, []))[1].append(it)
    with edit_group(scene):
        _paste_into(grouped, f0, out)
    return out


def _paste_into(grouped: dict, f0: float, out: list) -> None:
    for obj, its in grouped.values():
        data = _tracks_copy(obj)
        for it in its:
            ch = it["channel"]
            if channel_value(obj, ch) is None:
                continue
            if ch == POINTS:
                v = it["key"]["value"]
                if np.shape(np.asarray(v)) != np.shape(obj.mesh.points):
                    continue
            key = _normalize_key(it["key"])
            key["frame"] = _intish(f0 + float(it["offset"]))
            keys = [k for k in data.get(ch, []) if abs(float(k["frame"]) - key["frame"]) >= FRAME_EPS]
            keys.append(key)
            keys.sort(key=lambda k: k["frame"])
            data[ch] = keys
            out.append((obj, ch, key["frame"]))
        _write_tracks(obj, data)


def key_frames(objects, channels: Iterable[str] | None = None) -> list:
    if not isinstance(objects, (list, tuple, set)):
        objects = [objects]
    chans = None if channels is None else set(channels)
    frames: set = set()
    for obj in objects:
        for ch, keys in tracks(obj).items():
            if chans is not None and ch not in chans:
                continue
            for k in keys:
                frames.add(_intish(float(k["frame"])))
    return sorted(frames)


def all_refs(obj, channels: Iterable[str] | None = None) -> list:
    chans = channels_of(obj) if channels is None else list(channels)
    return [(obj, ch, k["frame"]) for ch in chans for k in get_track(obj, ch)]


def refs_at_frame(objects, frame: float, channels: Iterable[str] | None = None) -> list:
    if not isinstance(objects, (list, tuple, set)):
        objects = [objects]
    out = []
    for obj in objects:
        for ch in (channels_of(obj) if channels is None else channels):
            i = find_key(obj, ch, frame)
            if i >= 0:
                out.append((obj, ch, get_track(obj, ch)[i]["frame"]))
    return out


def refs_exist(refs: Iterable) -> list:
    return [r for r in refs if find_key(r[0], r[1], r[2]) >= 0]


def next_key_frame(objects, frame: float) -> float | None:
    for f in key_frames(objects):
        if f > float(frame) + FRAME_EPS:
            return f
    return None


def prev_key_frame(objects, frame: float) -> float | None:
    for f in reversed(key_frames(objects)):
        if f < float(frame) - FRAME_EPS:
            return f
    return None


def key_range(objects, channels: Iterable[str] | None = None) -> tuple[float, float] | None:
    frames = key_frames(objects, channels)
    if not frames:
        return None
    return float(frames[0]), float(frames[-1])


def value_range(obj, channel: str, f0: float, f1: float, samples: int = 64) -> tuple[float, float] | None:
    keys = get_track(obj, channel)
    if not keys or not all(_is_number(k["value"]) for k in keys):
        return None
    before, after = loop_mode(obj, channel)
    vals = [float(k["value"]) for k in keys]
    for i in range(samples + 1):
        f = f0 + (f1 - f0) * i / max(1, samples)
        v = evaluate_track(keys, f, before, after)
        if _is_number(v):
            vals.append(float(v))
    for i in range(len(keys)):
        tin, tout = key_tangents(keys, i)
        if keys[i].get("interp") == "spline" or (i and keys[i - 1].get("interp") == "spline"):
            vals.append(float(keys[i]["value"]) + tin[1])
            vals.append(float(keys[i]["value"]) + tout[1])
    return min(vals), max(vals)


def bake_object(scene, obj, start: float | None = None, end: float | None = None, step: int = 1,
                channels: Iterable[str] | None = None) -> int:
    s = time_settings(scene)
    f0 = int(s["min"] if start is None else start)
    f1 = int(s["max"] if end is None else end)
    chans = list(channels_of(obj) if channels is None else channels)
    samples: dict = {ch: [] for ch in chans}
    for f in range(f0, f1 + 1, max(1, int(step))):
        for ch in chans:
            v = evaluate_channel(obj, ch, f)
            if v is None:
                v = channel_value(obj, ch)
            if v is not None:
                samples[ch].append(make_key(f, v, "linear" if (_is_number(v) or _is_vector(v)) else "step"))
    data = _tracks_copy(obj)
    n = 0
    for ch, keys in samples.items():
        if keys:
            data[ch] = keys
            n += len(keys)
    _write_tracks(obj, data)
    return n


def snapshot_tracks(objects: Iterable) -> list:
    return [(o, _tracks_copy(o), copy.deepcopy(track_modes(o))) for o in objects]


def restore_tracks(snapshot: list) -> None:
    with edit_group():
        for obj, data, modes in snapshot:
            enc = _encode_tracks(data) if data else {}
            store.set_object(obj, TRACKS_KEY, enc if enc else None)
            store.set_object(obj, MODES_KEY, copy.deepcopy(modes) if modes else None)
