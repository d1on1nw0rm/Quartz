from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from ..ext import store
from .core import find_object, sync_renames, tags_of, watch_scene
from .mathutil import (blend_rotation, compose, decompose, euler_from_matrix, look_rotation,
                       orthonormal, rotation_matrix, smooth_noise)
from .registry import TAG_SPECS

__all__ = [
    "BASE_KEY",
    "MAX_SCALE_AMPLITUDE",
    "TagContext",
    "TransformState",
    "evaluate_tags",
    "evaluate_object",
    "reset_runtime",
    "base_transform",
    "dependency_order",
    "find_camera_position",
    "runtime_tags",
    "vibrate_offsets",
]

BASE_KEY = "tags_base"
TOL = 1e-6
MAX_SCALE_AMPLITUDE = 0.99


@dataclass
class TagContext:
    scene: object
    frame: float = 0.0
    fps: float = 30.0
    camera_position: np.ndarray | None = None
    cache: dict = field(default_factory=dict)

    @property
    def time(self) -> float:
        return float(self.frame) / float(self.fps) if self.fps else 0.0

    def object(self, name: str):
        return find_object(self.scene, name)

    def camera(self) -> np.ndarray | None:
        if self.camera_position is not None:
            return np.asarray(self.camera_position, float)
        return find_camera_position(self.scene)


def _axis_index(aim_axis: str | None) -> int | None:
    if not aim_axis:
        return None
    letter = str(aim_axis).strip().upper()[-1:]
    return "XYZ".index(letter) if letter and letter in "XYZ" else None


class TransformState:

    def __init__(self, position, rotation, scale, parent: np.ndarray | None = None) -> None:
        self.position = np.asarray(position, float).copy()
        self._rotation = np.asarray(rotation, float).copy()
        self.scale = np.asarray(scale, float).copy()
        self.parent = np.eye(4) if parent is None else np.asarray(parent, float).copy()
        self.rotation_touched = False

    @property
    def rotation(self) -> np.ndarray:
        return self._rotation

    @rotation.setter
    def rotation(self, value) -> None:
        self._rotation = orthonormal(np.asarray(value, float))
        self.rotation_touched = True

    def local_matrix(self) -> np.ndarray:
        return compose(self.position, self._rotation, self.scale)

    def world_matrix(self) -> np.ndarray:
        return self.parent @ self.local_matrix()

    def world_position(self) -> np.ndarray:
        return self.world_matrix()[:3, 3].copy()

    def world_rotation(self) -> np.ndarray:
        return orthonormal(self.parent[:3, :3]) @ self._rotation

    def set_world_rotation(self, world_rotation: np.ndarray, aim_axis: str | None = None) -> None:
        rw = np.asarray(world_rotation, float)
        lin = self.parent[:3, :3]
        k = _axis_index(aim_axis)
        if k is None:
            self.rotation = orthonormal(lin).T @ rw
            return
        local = np.linalg.pinv(lin) @ rw
        s, t = (k + 1) % 3, (k + 2) % 3
        a = local[:, k]
        na = np.linalg.norm(a)
        if na < 1e-12:
            self.rotation = orthonormal(lin).T @ rw
            return
        a = a / na
        b = local[:, s] - float(np.dot(local[:, s], a)) * a
        nb = np.linalg.norm(b)
        if nb < 1e-9:
            b = np.cross(a, local[:, t])
            nb = np.linalg.norm(b)
            if nb < 1e-9:
                self.rotation = orthonormal(lin).T @ rw
                return
        b = b / nb
        out = np.zeros((3, 3))
        out[:, k] = a
        out[:, s] = b
        out[:, t] = np.cross(a, b)
        self._rotation = out
        self.rotation_touched = True

    def to_local_direction(self, world_vector) -> np.ndarray:
        return np.linalg.pinv(self.parent[:3, :3]) @ np.asarray(world_vector, float)

    def local_aim(self, forward, up=(0.0, 1.0, 0.0), aim_axis: str = "+Z") -> np.ndarray | None:
        return look_rotation(self.to_local_direction(forward), self.to_local_direction(up), aim_axis)

    def aim(self, forward, up=(0.0, 1.0, 0.0), aim_axis: str = "+Z") -> bool:
        r = self.local_aim(forward, up, aim_axis)
        if r is None:
            return False
        self.rotation = r
        return True

    def set_world_position(self, world_position: Iterable[float]) -> None:
        p = np.append(np.asarray(world_position, float), 1.0)
        self.position = np.linalg.solve(self.parent, p)[:3]

    def set_world_matrix(self, world: np.ndarray) -> None:
        local = np.linalg.solve(self.parent, np.asarray(world, float))
        pos, rot, scale = decompose(local)
        self.position = pos
        self.rotation = rot
        self.scale = scale


def find_camera_position(scene) -> np.ndarray | None:
    if scene is None:
        return None
    name = store.get_scene_data(scene, "active_camera")
    cam = find_object(scene, name) if isinstance(name, str) else None
    if cam is None:
        for o in getattr(scene, "objects", ()):
            if o.kind == "camera" and getattr(o, "enabled", True):
                cam = o
                break
    if cam is None:
        pos = store.get_scene_data(scene, "camera_position")
        if pos is not None:
            return np.asarray(pos, float).reshape(3)
        return None
    return cam.world_position()


def runtime_tags(obj) -> list[tuple[dict, object]]:
    out = []
    for t in tags_of(obj):
        spec = TAG_SPECS.get(t.get("type", ""))
        if spec is not None and spec.runtime and t.get("enabled", True):
            out.append((t, spec))
    return out


def _referenced(obj) -> list[str]:
    names = []
    for t in tags_of(obj):
        spec = TAG_SPECS.get(t.get("type", ""))
        if spec is None or not t.get("enabled", True):
            continue
        for p in spec.params:
            if p.kind == "object" and t.get(p.key):
                names.append(str(t[p.key]))
    return names


def dependency_order(scene) -> list:
    objs = list(getattr(scene, "objects", ()))
    by_name = {}
    for o in objs:
        by_name.setdefault(o.name, o)
    done: set[int] = set()
    active: set[int] = set()
    out = []

    def visit(o) -> None:
        key = id(o)
        if key in done or key in active:
            return
        active.add(key)
        deps = []
        if o.parent is not None:
            deps.append(o.parent)
        for n in _referenced(o):
            d = by_name.get(n)
            if d is not None and d is not o:
                deps.append(d)
        for d in deps:
            visit(d)
        active.discard(key)
        done.add(key)
        out.append(o)

    for o in objs:
        visit(o)
    return out


def _channels(obj) -> dict:
    return {"position": np.asarray(obj.position, float).copy(),
            "rotation": np.asarray(obj.rotation, float).copy(),
            "scale": np.asarray(obj.scale, float).copy()}


def _as_lists(ch: dict) -> dict:
    return {k: [float(x) for x in np.asarray(v, float)] for k, v in ch.items()}


def _as_arrays(ch: dict) -> dict:
    return {k: np.asarray(ch[k], float).copy() for k in ("position", "rotation", "scale")}


def _same(a: dict, b: dict) -> bool:
    try:
        return all(np.allclose(np.asarray(a[k], float), np.asarray(b[k], float), atol=TOL)
                   for k in ("position", "rotation", "scale"))
    except (KeyError, ValueError, TypeError):
        return False


def base_transform(obj) -> dict:
    rec = store.object_extras(obj).get(BASE_KEY)
    cur = _channels(obj)
    if isinstance(rec, dict) and _same(cur, rec.get("applied", {})):
        return _as_arrays(rec["base"])
    return cur


def _apply(obj, ch: dict) -> None:
    obj.position = np.asarray(ch["position"], float).copy()
    obj.rotation = np.asarray(ch["rotation"], float).copy()
    obj.scale = np.asarray(ch["scale"], float).copy()


def evaluate_object(ctx: TagContext, obj) -> bool:
    extras = store.object_extras(obj)
    rec = extras.get(BASE_KEY)
    cur = _channels(obj)
    if isinstance(rec, dict) and _same(cur, rec.get("applied", {})):
        base = _as_arrays(rec["base"])
    else:
        base = _as_arrays(cur)
    active = runtime_tags(obj)
    if not active:
        if isinstance(rec, dict):
            extras.pop(BASE_KEY, None)
            if not _same(cur, base):
                _apply(obj, base)
                return True
        return False
    for tag, spec in active:
        if spec.extra.get("stage") == "base":
            spec.evaluate(ctx, obj, tag, base)
    parent = obj.parent.world_matrix() if obj.parent is not None else np.eye(4)
    state = TransformState(base["position"], rotation_matrix(base["rotation"]), base["scale"], parent)
    for tag, spec in active:
        if spec.extra.get("stage") != "base":
            spec.evaluate(ctx, obj, tag, state)
    result = {
        "position": state.position.copy(),
        "rotation": (euler_from_matrix(state.rotation, reference=base["rotation"])
                     if state.rotation_touched else base["rotation"].copy()),
        "scale": state.scale.copy(),
    }
    extras[BASE_KEY] = {"base": _as_lists(base), "applied": _as_lists(result)}
    if _same(cur, result):
        return False
    _apply(obj, result)
    return True


def evaluate_tags(scene, frame: float = 0.0, camera_position=None, fps: float = 30.0) -> list:
    watch_scene(scene)
    sync_renames(scene)
    ctx = TagContext(scene, float(frame), float(fps) if fps else 30.0,
                     None if camera_position is None else np.asarray(camera_position, float))
    changed = []
    for obj in dependency_order(scene):
        if evaluate_object(ctx, obj):
            changed.append(obj)
    return changed


def reset_runtime(scene) -> int:
    count = 0
    for obj in getattr(scene, "objects", ()):
        extras = store.object_extras(obj)
        rec = extras.get(BASE_KEY)
        if not isinstance(rec, dict):
            continue
        if _same(_channels(obj), rec.get("applied", {})):
            _apply(obj, _as_arrays(rec["base"]))
            count += 1
        extras.pop(BASE_KEY, None)
    return count


def _seed_list(tag: dict) -> list[int]:
    seeds = tag.get("seed", [1.0, 2.0, 3.0])
    return [int(round(float(s))) for s in seeds]


def vibrate_offsets(tag: dict, time: float) -> dict:
    freq = max(0.0, float(tag.get("frequency", 2.0)))
    t = time * freq
    seeds = _seed_list(tag)
    regular = bool(tag.get("regular", False))

    def wave(axis: int, channel: int) -> float:
        s = seeds[axis] * 7919 + channel * 104729
        if regular:
            phase = (smooth_noise(0.5, s) + 1.0) * math.pi
            return math.sin(2.0 * math.pi * t + phase)
        return smooth_noise(t + 0.5 * (channel + 1), s)

    out = {"position": np.zeros(3), "rotation": np.zeros(3), "scale": np.ones(3)}
    if tag.get("enable_position", True):
        amp = np.asarray(tag.get("position_amplitude", [0.0, 0.0, 0.0]), float)
        out["position"] = amp * np.array([wave(a, 0) for a in range(3)])
    if tag.get("enable_rotation", False):
        amp = np.asarray(tag.get("rotation_amplitude", [0.0, 0.0, 0.0]), float)
        out["rotation"] = amp * np.array([wave(a, 1) for a in range(3)])
    if tag.get("enable_scale", False):
        amp = np.clip(np.asarray(tag.get("scale_amplitude", [0.0, 0.0, 0.0]), float), 0.0, MAX_SCALE_AMPLITUDE)
        if tag.get("uniform_scale", True):
            out["scale"] = np.full(3, 1.0 + amp[0] * wave(0, 2))
        else:
            out["scale"] = 1.0 + amp * np.array([wave(a, 2) for a in range(3)])
    return out
