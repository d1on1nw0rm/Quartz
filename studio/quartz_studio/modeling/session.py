from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..scene import Scene, _edge_key
from .meshkit import OpResult, Selection, carry_point_scales, clone
from .registry import get_tool

__all__ = ["ToolSession", "ModelingController", "selection_from_scene"]


def selection_from_scene(scene: Scene) -> Selection:
    return Selection(scene.mode, set(scene.selected_points), set(scene.selected_edges),
                     set(scene.selected_polygons))


EDITABLE_MESSAGE = "Make Editable first"


def editable(scene: Scene, obj) -> bool:
    check = getattr(scene, "is_editable", None)
    return obj is not None and (check is None or bool(check(obj)))


def _push_selection(scene: Scene, sel: Selection) -> None:
    mesh = scene.active.mesh
    n_pts = len(mesh.points)
    n_polys = len(mesh.polygons)
    valid_edges = set(mesh.edges)
    scene.selected_points = {int(i) for i in sel.points if 0 <= int(i) < n_pts}
    scene.selected_edges = {_edge_key(*e) for e in sel.edges if _edge_key(*e) in valid_edges}
    scene.selected_polygons = {int(i) for i in sel.polygons if 0 <= int(i) < n_polys}
    if sel.mode in ("points", "edges", "polygons") and sel.mode != scene.mode:
        scene.set_mode(sel.mode)


class ToolSession:

    def __init__(self, scene: Scene, tool_id: str, params: dict | None = None) -> None:
        self.scene = scene
        self.spec = get_tool(tool_id)
        self.obj = scene.active
        self.base_mesh = clone(self.obj.mesh) if self.obj is not None else None
        self.base_selection = selection_from_scene(scene)
        self.params = self.spec.clamp(params or {})
        self.recorded = False
        self.result: OpResult | None = None
        self.closed = False

    def valid(self) -> bool:
        return (self.obj is not None and self.obj in self.scene.objects
                and editable(self.scene, self.obj)
                and self.spec.supports(self.base_selection.mode))

    def apply(self, params: dict | None = None) -> OpResult | None:
        if self.closed or not self.valid():
            return None
        if params is not None:
            merged = dict(self.params)
            merged.update(params)
            self.params = self.spec.clamp(merged)
        result = self.spec.apply(clone(self.base_mesh), self.base_selection.copy(), dict(self.params))
        self.result = result
        if not result.ok:
            if self.recorded:
                self._restore_base()
            return result
        if not self.recorded:
            self.scene._record("modeling")
            self.recorded = True
        self.obj.mesh = carry_point_scales(self.base_mesh, result.mesh)
        _push_selection(self.scene, result.selection)
        self.scene.changed.emit()
        self.scene.selectionChanged.emit()
        return result

    def _restore_base(self) -> None:
        self.obj.mesh = clone(self.base_mesh)
        _push_selection(self.scene, self.base_selection)
        self.scene.changed.emit()
        self.scene.selectionChanged.emit()

    def commit(self) -> bool:
        if self.closed:
            return False
        self.closed = True
        return self.recorded

    def cancel(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.recorded and self.obj in self.scene.objects:
            self._restore_base()
            undo = getattr(self.scene, "_undo", None)
            if undo:
                undo.pop()


class ModelingController(QObject):

    toolChanged = Signal(str)
    paramsChanged = Signal(dict)
    sessionChanged = Signal()
    message = Signal(str)

    def __init__(self, scene: Scene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self.tool_id: str | None = None
        self.values: dict[str, dict] = {}
        self.session: ToolSession | None = None
        self._busy = False
        scene.selectionChanged.connect(self._on_scene_selection)
        scene.modeChanged.connect(self._on_scene_selection)
        scene.objectsChanged.connect(self._on_scene_selection)

    def params(self, tool_id: str | None = None) -> dict:
        tool_id = tool_id or self.tool_id
        if tool_id is None:
            return {}
        spec = get_tool(tool_id)
        if tool_id not in self.values:
            self.values[tool_id] = spec.defaults()
        return dict(self.values[tool_id])

    def activate(self, tool_id: str | None) -> None:
        if tool_id == self.tool_id:
            return
        self.new_transform()
        self.tool_id = tool_id
        self.toolChanged.emit(tool_id or "")
        if tool_id is not None:
            self.paramsChanged.emit(self.params())

    def set_param(self, key: str, value) -> None:
        if self.tool_id is None:
            return
        spec = get_tool(self.tool_id)
        merged = self.params()
        merged[key] = value
        self.values[self.tool_id] = spec.clamp(merged)
        self.paramsChanged.emit(dict(self.values[self.tool_id]))
        if self.session is not None and not self.session.closed:
            self._busy = True
            try:
                self.session.apply(self.values[self.tool_id])
            finally:
                self._busy = False

    def reset_values(self) -> None:
        if self.tool_id is None:
            return
        spec = get_tool(self.tool_id)
        self.values[self.tool_id] = spec.defaults()
        self.paramsChanged.emit(dict(self.values[self.tool_id]))
        if self.session is not None and not self.session.closed:
            self._busy = True
            try:
                self.session.apply(self.values[self.tool_id])
            finally:
                self._busy = False

    def begin(self) -> ToolSession | None:
        if self.tool_id is None:
            return None
        self.new_transform()
        active = self.scene.active
        if active is not None and not editable(self.scene, active):
            self.message.emit(f"{get_tool(self.tool_id).name}: {EDITABLE_MESSAGE}")
            return None
        session = ToolSession(self.scene, self.tool_id, self.params())
        if not session.valid():
            spec = get_tool(self.tool_id)
            self.message.emit(f"{spec.name}: select {' or '.join(spec.modes)} first")
            return None
        self.session = session
        self.sessionChanged.emit()
        return session

    def apply_live(self, params: dict | None = None):
        if self.session is None or self.session.closed:
            return None
        if params:
            merged = self.params()
            merged.update(params)
            self.values[self.tool_id] = get_tool(self.tool_id).clamp(merged)
            self.paramsChanged.emit(dict(self.values[self.tool_id]))
        self._busy = True
        try:
            result = self.session.apply(self.values[self.tool_id])
        finally:
            self._busy = False
        if result is not None and not result.ok and result.message:
            self.message.emit(result.message)
        return result

    def apply_once(self) -> bool:
        session = self.begin()
        if session is None:
            return False
        result = self.apply_live()
        ok = bool(result is not None and result.ok)
        if not interactive_keeps_session(session):
            self.new_transform()
        return ok

    def new_transform(self) -> None:
        if self.session is not None:
            self.session.commit()
            self.session = None
            self.sessionChanged.emit()

    def cancel(self) -> None:
        if self.session is not None:
            self._busy = True
            try:
                self.session.cancel()
            finally:
                self._busy = False
            self.session = None
            self.sessionChanged.emit()

    def _on_scene_selection(self, *_args) -> None:
        if self._busy or self.session is None:
            return
        self.new_transform()


def interactive_keeps_session(session: ToolSession) -> bool:
    return session.spec.interactive
