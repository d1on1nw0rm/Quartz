from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject

from . import data
from . import ik
from . import joints as jt
from . import skin as sk

__all__ = ["evaluate_rig", "RigUpdater", "updater_for", "unique_name", "rename_references",
           "rename_object", "ReferenceGuard", "guard_for"]


def _pose(scene) -> list[np.ndarray]:
    return [np.concatenate([o.position, o.rotation, o.scale]) for o in scene.objects if jt.is_joint(o)]


def evaluate_rig(scene, emit: bool = True) -> dict:
    before = _pose(scene)
    solved = ik.solve_all(scene)
    after = _pose(scene)
    moved = len(before) != len(after) or any(not np.allclose(a, b, atol=1e-9) for a, b in zip(before, after))
    deformed = 0
    for obj in sk.skinned_objects(scene):
        if sk.deform_skin(scene, obj):
            deformed += 1
    if emit and (moved or deformed):
        scene.changed.emit()
    return {"ik": solved, "deformed": deformed, "moved": bool(moved)}


class RigUpdater(QObject):

    def __init__(self, scene, parent: QObject | None = None) -> None:
        super().__init__(parent if parent is not None else scene)
        self.scene = scene
        self._busy = False
        self._enabled = False
        self.runs = 0

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, on: bool) -> None:
        on = bool(on)
        if on == self._enabled:
            return
        self._enabled = on
        if on:
            self.scene.changed.connect(self._on_changed)
            self._on_changed()
        else:
            try:
                self.scene.changed.disconnect(self._on_changed)
            except (RuntimeError, TypeError):
                pass

    def _on_changed(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            evaluate_rig(self.scene, emit=True)
            self.runs += 1
        finally:
            self._busy = False


_UPDATERS: dict[int, RigUpdater] = {}


def updater_for(scene) -> RigUpdater:
    u = _UPDATERS.get(id(scene))
    if u is None or u.scene is not scene:
        u = RigUpdater(scene)
        _UPDATERS[id(scene)] = u
    return u


def unique_name(scene, name: str, exclude=None) -> str:
    base = str(name).strip()
    taken = {o.name for o in scene.objects if o is not exclude}
    if base not in taken:
        return base
    n = 1
    while f"{base}.{n}" in taken:
        n += 1
    return f"{base}.{n}"


def rename_references(scene, old: str, new: str) -> int:
    if not old or old == new:
        return 0
    count = 0
    for o in scene.objects:
        names = sk.skin_joint_names(o)
        if old in names:
            s = sk.skin_of(o)
            fixed = dict(s)
            fixed["joints"] = [new if n == old else n for n in names]
            data.write_quiet(o, data.SKIN_KEY, fixed)
            count += 1
    count += ik.rename_references(scene, old, new)
    return count


def rename_object(scene, obj, name: str) -> str:
    wanted = str(name).strip()
    if not wanted or obj not in scene.objects or wanted == obj.name:
        return obj.name
    old = obj.name
    final = unique_name(scene, wanted, exclude=obj)
    guard = _GUARDS.get(id(scene))
    if guard is not None and guard.scene is scene:
        guard.pause(True)
    try:
        scene.rename_object(obj, final)
    finally:
        if guard is not None and guard.scene is scene:
            guard.pause(False)
    if obj.name != old:
        rename_references(scene, old, obj.name)
        if guard is not None and guard.scene is scene:
            guard.capture()
        scene.changed.emit()
    return obj.name


class ReferenceGuard(QObject):

    def __init__(self, scene, parent: QObject | None = None) -> None:
        super().__init__(parent if parent is not None else scene)
        self.scene = scene
        self._names: dict[int, tuple[object, str]] = {}
        self._paused = False
        self.fixed = 0
        self.capture()
        scene.objectsChanged.connect(self.check)

    def pause(self, on: bool) -> None:
        self._paused = bool(on)

    def capture(self) -> None:
        self._names = {id(o): (o, o.name) for o in self.scene.objects}

    def check(self) -> int:
        if self._paused:
            return 0
        renames = []
        for o in self.scene.objects:
            prev = self._names.get(id(o))
            if prev is not None and prev[0] is o and prev[1] != o.name:
                renames.append((prev[1], o.name))
        count = 0
        for old, new in renames:
            count += rename_references(self.scene, old, new)
        self.capture()
        if count:
            self.fixed += count
            self.scene.changed.emit()
        return count


_GUARDS: dict[int, ReferenceGuard] = {}


def guard_for(scene) -> ReferenceGuard:
    g = _GUARDS.get(id(scene))
    if g is None or g.scene is not scene:
        g = ReferenceGuard(scene)
        _GUARDS[id(scene)] = g
    return g
