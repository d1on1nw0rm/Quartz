from __future__ import annotations

import weakref

from PySide6.QtCore import QObject, QTimer, Signal

from ..ext import store
from . import data
from .brushes import BRUSH_ORDER, SHARED_KEYS, BrushSettings, default_settings

__all__ = ["SculptSession", "get_session", "SCENE_KEY"]

SCENE_KEY = "sculpt_brushes"


class SculptSession(QObject):

    activeChanged = Signal(bool)
    brushChanged = Signal(str)
    settingsChanged = Signal()
    dataChanged = Signal()

    def __init__(self, scene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self.active = False
        self._previous_tool = None
        self._target_obj = None
        self._own_tool_change = False
        self.show_mask = True
        self._brush = "pull"
        self._settings: dict[str, BrushSettings] = {b: default_settings(b) for b in BRUSH_ORDER}
        self._saved_raw = None
        self._saved_extras = None
        self._load(store.scene_extras(scene).get(SCENE_KEY))
        self._mark_synced()
        for name, slot in (("changed", self._on_scene_changed), ("objectsChanged", self._on_scene_changed),
                           ("toolChanged", self._on_tool_changed)):
            sig = getattr(scene, name, None)
            if sig is not None:
                try:
                    sig.connect(slot)
                except (TypeError, RuntimeError):
                    pass

    @property
    def brush(self) -> str:
        self._sync()
        return self._brush

    @brush.setter
    def brush(self, value: str) -> None:
        self._brush = value

    def _load(self, saved) -> bool:
        if not isinstance(saved, dict):
            return False
        fresh = {b: default_settings(b) for b in BRUSH_ORDER}
        for bid, values in (saved.get("brushes") or {}).items():
            if bid in fresh and isinstance(values, dict):
                merged = fresh[bid].to_dict()
                merged.update(store.from_json(values))
                merged["brush"] = bid
                fresh[bid] = BrushSettings.from_dict(merged)
        self._settings = fresh
        b = saved.get("brush")
        if b in self._settings:
            self._brush = b
        return True

    def _mark_synced(self) -> None:
        extras = store.scene_extras(self.scene)
        self._saved_extras = extras
        self._saved_raw = extras.get(SCENE_KEY)

    def _sync(self) -> bool:
        extras = getattr(self.scene, "extras", None)
        if not isinstance(extras, dict):
            return False
        raw = extras.get(SCENE_KEY)
        if extras is self._saved_extras and raw is self._saved_raw:
            return False
        self._saved_extras = extras
        if raw is self._saved_raw or not isinstance(raw, dict) or raw == self._saved_raw:
            self._saved_raw = raw
            return False
        old_brush = self._brush
        self._saved_raw = raw
        self._load(raw)
        if self._brush != old_brush:
            self.brushChanged.emit(self._brush)
        self.settingsChanged.emit()
        return True

    def _on_scene_changed(self) -> None:
        self._sync()

    def _save(self) -> None:
        value = {
            "brush": self._brush,
            "brushes": {b: store.to_json(s.to_dict()) for b, s in self._settings.items()},
        }
        extras = store.scene_extras(self.scene)
        extras[SCENE_KEY] = value
        self._saved_extras = extras
        self._saved_raw = value

    def target(self):
        obj = getattr(self.scene, "active", None)
        return obj if data.can_sculpt(obj) else None

    def _set_tool(self, tool: str) -> None:
        set_tool = getattr(self.scene, "set_tool", None)
        if set_tool is None:
            return
        self._own_tool_change = True
        try:
            set_tool(tool)
        finally:
            self._own_tool_change = False

    def set_active(self, flag: bool) -> None:
        flag = bool(flag)
        if flag:
            obj = getattr(self.scene, "active", None)
            if obj is not None and not data.can_sculpt(obj) and getattr(obj, "kind", "polygon") != "polygon":
                maker = getattr(self.scene, "make_editable", None)
                if maker is not None and obj.mesh is not None and obj.mesh.polygons:
                    maker(obj)
            obj = self.target()
            if obj is not None:
                data.ensure_state(obj)
            self._target_obj = getattr(self.scene, "active", None)
        if flag == self.active:
            return
        self.active = flag
        if flag:
            self._previous_tool = getattr(self.scene, "tool", None)
            self._set_tool("other")
        elif getattr(self.scene, "tool", None) == "other" and self._previous_tool:
            self._set_tool(self._previous_tool)
        self.activeChanged.emit(flag)

    def switch_target(self, obj) -> bool:
        setter = getattr(self.scene, "set_active", None)
        if setter is None or obj is getattr(self.scene, "active", None):
            return False
        self._own_tool_change = True
        try:
            setter(obj)
        finally:
            self._own_tool_change = False
        self._target_obj = getattr(self.scene, "active", None)
        if self.active and getattr(self.scene, "tool", None) != "other":
            self._set_tool("other")
        return True

    def _on_tool_changed(self, tool: str) -> None:
        if self._own_tool_change or not self.active or tool == "other":
            return
        obj = getattr(self.scene, "active", None)
        if obj is not self._target_obj and data.can_sculpt(obj):
            self._target_obj = obj
            QTimer.singleShot(0, self._reassert)
            return
        self._previous_tool = None
        self.active = False
        self.activeChanged.emit(False)

    def _reassert(self) -> None:
        if not self.active:
            return
        if getattr(self.scene, "tool", None) == "other":
            return
        if getattr(self.scene, "active", None) is not self._target_obj or not data.can_sculpt(self._target_obj):
            self.active = False
            self._previous_tool = None
            self.activeChanged.emit(False)
            return
        self._set_tool("other")

    def toggle(self) -> None:
        self.set_active(not self.active)

    def set_brush(self, brush_id: str) -> None:
        self._sync()
        if brush_id not in self._settings or brush_id == self._brush:
            return
        self._brush = brush_id
        self._save()
        self.brushChanged.emit(brush_id)
        self.settingsChanged.emit()

    def settings(self, brush_id: str | None = None) -> BrushSettings:
        self._sync()
        return self._settings[brush_id or self._brush]

    def set(self, key: str, value) -> None:
        current = self.settings()
        if not hasattr(current, key) or key == "brush":
            raise KeyError(key)
        targets = self._settings.values() if key in SHARED_KEYS else (current,)
        for s in targets:
            setattr(s, key, value)
            s.clamp()
        self._save()
        self.settingsChanged.emit()

    def set_symmetry(self, axis: int, flag: bool) -> None:
        sym = list(self.settings().symmetry)
        sym[int(axis)] = bool(flag)
        self.set("symmetry", tuple(sym))

    def scale_radius(self, factor: float) -> None:
        self.set("radius", self.settings().radius * float(factor))

    def reset_brush(self) -> None:
        keep = {k: getattr(self.settings(), k) for k in SHARED_KEYS}
        fresh = default_settings(self._brush)
        for k, v in keep.items():
            setattr(fresh, k, v)
        self._settings[self._brush] = fresh.clamp()
        self._save()
        self.settingsChanged.emit()

    def set_show_mask(self, flag: bool) -> None:
        self.show_mask = bool(flag)
        self.settingsChanged.emit()

    def notify_data(self) -> None:
        self.dataChanged.emit()


_SESSIONS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def get_session(scene=None) -> SculptSession:
    if scene is None:
        from ..scene import get_scene
        scene = get_scene()
    session = _SESSIONS.get(scene)
    if session is None:
        session = SculptSession(scene)
        _SESSIONS[scene] = session
    return session
