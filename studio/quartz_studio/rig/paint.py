from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ..scene import SceneObject
from . import data
from . import skin as sk

__all__ = ["WeightBrush", "WeightPainter"]


@dataclass
class WeightBrush:
    joint: int = 0
    mode: str = "Add"
    radius: float = 20.0
    strength: float = 0.25
    falloff: str = "Smooth"
    normalize: bool = True

    def clamp(self) -> "WeightBrush":
        self.mode = self.mode if self.mode in sk.PAINT_MODES else "Add"
        self.falloff = self.falloff if self.falloff in sk.FALLOFFS else "Smooth"
        self.radius = max(0.0, float(self.radius))
        self.strength = float(np.clip(self.strength, 0.0, 1.0))
        self.joint = max(0, int(self.joint))
        return self


class WeightPainter:

    UNDO_LIMIT = 32

    def __init__(self, scene, brush: WeightBrush | None = None) -> None:
        self.scene = scene
        self.brush = brush if brush is not None else WeightBrush()
        self.target: SceneObject | None = None
        self._target_name = ""
        self._stroke_before: np.ndarray | None = None
        self._undo: list[tuple[str, np.ndarray, np.ndarray]] = []
        self.dabs = 0

    def set_target(self, obj: SceneObject | None) -> bool:
        if obj is not None and not sk.is_skinned(obj):
            return False
        if obj is not self.target:
            self.end_stroke()
            self.target = obj
        self._target_name = obj.name if obj is not None else ""
        return True

    def _find(self, name: str) -> SceneObject | None:
        if not name:
            return None
        for o in self.scene.objects:
            if o.name == name and sk.is_skinned(o):
                return o
        return None

    def _resolve(self) -> None:
        if self.target is not None and self.target in self.scene.objects:
            self._target_name = self.target.name
            return
        if self._target_name:
            found = self._find(self._target_name)
            if found is not None:
                self.target = found
                return
        if self.target is not None and self.target not in self.scene.objects:
            self.target = None
            self._stroke_before = None

    def valid(self) -> bool:
        self._resolve()
        return (self.target is not None and self.target in self.scene.objects
                and sk.is_skinned(self.target))

    def skin(self) -> dict | None:
        self._resolve()
        return sk.skin_of(self.target) if self.target is not None else None

    def joint_names(self) -> list[str]:
        s = self.skin()
        return list(s["joints"]) if s else []

    def weights(self) -> np.ndarray | None:
        s = self.skin()
        return None if s is None else np.asarray(s["weights"], float)

    def world_points(self) -> np.ndarray:
        return self.target.world_points() if self.target is not None else np.zeros((0, 3))

    def in_stroke(self) -> bool:
        return self._stroke_before is not None

    def begin_stroke(self) -> bool:
        if not self.valid():
            return False
        if self._stroke_before is None:
            self._stroke_before = self.weights().copy()
        return True

    def end_stroke(self) -> bool:
        if self._stroke_before is None:
            return False
        before, self._stroke_before = self._stroke_before, None
        if not self.valid():
            return False
        obj = self.target
        s = sk.skin_of(obj)
        now = np.asarray(s["weights"], float)
        if before.shape != now.shape or np.array_equal(before, now):
            return False
        quiet = dict(s)
        quiet["weights"] = before
        data.write_quiet(obj, data.SKIN_KEY, quiet)
        sk.deform_skin(self.scene, obj)
        sk.apply_weights(self.scene, obj, now)
        sk.deform_skin(self.scene, obj)
        self.scene.changed.emit()
        self._undo.append((obj.name, before, now.copy()))
        del self._undo[:-self.UNDO_LIMIT]
        return True

    def can_undo(self) -> bool:
        return bool(self._undo)

    def undo(self) -> bool:
        self.end_stroke()
        while self._undo:
            name, before, after = self._undo.pop()
            obj = self._find(name)
            if obj is None:
                continue
            current = np.asarray(sk.skin_of(obj)["weights"], float)
            if current.shape != after.shape or not np.allclose(current, after, atol=1e-12, rtol=0.0):
                continue
            sk.apply_weights(self.scene, obj, before)
            if sk.deform_skin(self.scene, obj):
                self.scene.changed.emit()
            return True
        return False

    def _live(self, obj: SceneObject, w: np.ndarray) -> None:
        s = sk.skin_of(obj)
        if s is None:
            return
        new = dict(s)
        new["weights"] = np.asarray(w, float).copy()
        data.write_quiet(obj, data.SKIN_KEY, new)
        sk.deform_skin(self.scene, obj)
        self.scene.changed.emit()

    def apply_falloff(self, falloff: np.ndarray) -> bool:
        if not self.valid():
            return False
        b = self.brush.clamp()
        w = self.weights()
        if w.shape[1] == 0:
            return False
        joint = min(b.joint, w.shape[1] - 1)
        adj = sk.adjacency(self.target.mesh) if b.mode == "Smooth" else None
        new = sk.paint_weights(w, joint, falloff, b.mode, b.strength, b.normalize, adj)
        if np.array_equal(new, w):
            return False
        own = not self.in_stroke()
        if own:
            self.begin_stroke()
        self._live(self.target, new)
        self.dabs += 1
        if own:
            self.end_stroke()
        return True

    def dab_sphere(self, center: Iterable[float], radius: float | None = None) -> bool:
        if not self.valid():
            return False
        r = self.brush.radius if radius is None else float(radius)
        d = sk.sphere_distances(self.world_points(), center)
        return self.apply_falloff(sk.brush_falloff(d, r, self.brush.falloff))

    def dab_cylinder(self, origin: Iterable[float], direction: Iterable[float],
                     radius: float | None = None) -> bool:
        if not self.valid():
            return False
        r = self.brush.radius if radius is None else float(radius)
        d = sk.cylinder_distances(self.world_points(), origin, direction)
        return self.apply_falloff(sk.brush_falloff(d, r, self.brush.falloff))

    def flood(self) -> bool:
        if not self.valid():
            return False
        return self.apply_falloff(np.ones(len(self.target.mesh.points)))

    def normalize_all(self) -> bool:
        if not self.valid():
            return False
        w = self.weights()
        new = sk.normalize_weights(w)
        if np.allclose(new, w):
            return False
        self._commit_once(new)
        return True

    def smooth_all(self, iterations: int = 1, strength: float = 0.5) -> bool:
        if not self.valid():
            return False
        w = self.weights()
        new = sk.normalize_weights(sk.smooth_weights(w, sk.adjacency(self.target.mesh), iterations, strength))
        if np.allclose(new, w):
            return False
        self._commit_once(new)
        return True

    def prune(self, threshold: float = 0.05) -> bool:
        if not self.valid():
            return False
        w = self.weights()
        new = sk.prune_weights(w, threshold)
        if np.array_equal(new, w):
            return False
        self._commit_once(new)
        return True

    def limit(self, count: int) -> bool:
        if not self.valid():
            return False
        w = self.weights()
        new = sk.normalize_weights(sk.limit_influences(w, count))
        if np.allclose(new, w):
            return False
        self._commit_once(new)
        return True

    def _commit_once(self, new: np.ndarray) -> None:
        self.begin_stroke()
        self._live(self.target, new)
        self.end_stroke()
