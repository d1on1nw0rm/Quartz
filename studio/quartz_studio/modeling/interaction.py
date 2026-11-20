from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QEvent, QLineF, QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .. import theme
from ..scene import _edge_key
from .registry import get_tool
from .session import EDITABLE_MESSAGE, ModelingController, editable

__all__ = ["ToolOverlay", "ViewportToolFilter", "drag_amount"]

DRAG_THRESHOLD = 3.0
PERCENT_PER_PX = 0.5
ANGLE_PER_PX = 0.5
COUNT_PX = 18.0
EDGE_PICK_PX = 10.0
POINT_PICK_PX = 10.0
HOVER_COLOR = theme.SELECT_FRONT
PREVIEW_COLOR = theme.SELECT_FRONT_SOFT
PREVIEW_WIRE_WIDTH = 1.0
SKIN_PREVIEW = "skin_wire"
SKIN_PREVIEW_BUDGET = 600
HUD_COLOR = theme.TEXT_PRIMARY

PICK_LINE = "line"
PICK_EDGE = "edge"
PICK_POINT = "point"
PICK_PLANE = "plane"
PICK_KINDS = (PICK_LINE, PICK_EDGE, PICK_POINT, PICK_PLANE)

RUNTIME_SOURCES = {
    "edge": "edge pick: (a, b) indices of the edge under the cursor",
    "path": "edge pick in clicks: edges clicked so far in the current session",
    "edge_position": "edge pick: 0..100 cursor position along the edge, sent with the edge",
    "edge_a": "edge pick: first edge (first click, or drag start)",
    "edge_b": "edge pick: second edge (second click, or drag end)",
    "start": "line pick: world point where the drag starts",
    "end": "line pick: world point where the drag ends",
    "view_dir": "canvas: world view direction of the camera",
    "view_direction": "canvas: view direction converted to object space",
    "target": "point pick: index of the vertex under the cursor",
    "plane_origin": "point pick: clicked point in the tool's coordinate system",
    "position": "not sent by the viewport: None welds onto the target point",
    "modeling_axis": "not sent by the viewport: None uses the selection center and world axes",
    "object_linear": "active object: 3x3 linear() matrix",
    "object_position": "active object: world position",
    "object_matrix": "active object: 4x4 object-to-world matrix",
    "camera_rotation": "canvas: camera rotation with columns right, up and toward the viewer",
}


def drag_amount(kind: str, dx: float, cm_per_px: float) -> float:
    if kind == "distance":
        return dx * cm_per_px
    if kind == "percent":
        return dx * PERCENT_PER_PX
    if kind == "angle":
        return dx * ANGLE_PER_PX
    if kind == "count":
        return math.floor(dx / COUNT_PX)
    return dx * cm_per_px


def _controls():
    from .. import controls

    return controls


def _drag_threshold() -> float:
    return float(_controls().cursor("drag_threshold"))


def _vec(value) -> tuple:
    return tuple(float(x) for x in np.asarray(value, float).reshape(-1))


def _rows(matrix) -> tuple:
    return tuple(_vec(row) for row in np.asarray(matrix, float))


def _matrix4(obj) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = obj.linear()
    m[:3, 3] = obj.position
    return m


class ToolOverlay(QWidget):

    def __init__(self, canvas: QWidget) -> None:
        super().__init__(canvas)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hover_edge: tuple[QPointF, QPointF] | None = None
        self.preview_line: tuple[QPointF, QPointF] | None = None
        self.preview_wire: tuple[np.ndarray, np.ndarray] | None = None
        self.hud = ""
        self.hud_pos = QPointF()
        canvas.installEventFilter(self)
        self.setGeometry(canvas.rect())
        self.raise_()
        self.show()

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if obj is self.parentWidget() and ev.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
        return False

    def clear(self) -> None:
        if self.hover_edge or self.preview_line or self.hud or self.preview_wire is not None:
            self.hover_edge = None
            self.preview_line = None
            self.preview_wire = None
            self.hud = ""
            self.update()

    def _wire_lines(self) -> list[QLineF]:
        if self.preview_wire is None:
            return []
        points, edges = self.preview_wire
        if not len(points) or not len(edges):
            return []
        screen = self.parentWidget().project_world(points)
        a, b = screen[edges[:, 0]], screen[edges[:, 1]]
        ok = ~(np.isnan(a).any(axis=1) | np.isnan(b).any(axis=1))
        return [QLineF(float(x0), float(y0), float(x1), float(y1))
                for (x0, y0), (x1, y1) in zip(a[ok], b[ok])]

    def paintEvent(self, _e) -> None:
        if not (self.hover_edge or self.preview_line or self.hud or self.preview_wire is not None):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.preview_wire is not None:
            lines = self._wire_lines()
            if lines:
                p.setPen(QPen(QColor(PREVIEW_COLOR), PREVIEW_WIRE_WIDTH))
                p.drawLines(lines)
        if self.hover_edge is not None:
            p.setPen(QPen(QColor(HOVER_COLOR), 3.0))
            p.drawLine(*self.hover_edge)
        if self.preview_line is not None:
            pen = QPen(QColor(PREVIEW_COLOR), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(*self.preview_line)
        if self.hud:
            f = QFont(self.font())
            f.setPixelSize(12)
            p.setFont(f)
            r = QRectF(self.hud_pos.x() + 14, self.hud_pos.y() + 10, 240, 20)
            p.setPen(QColor(theme.SHADOW))
            p.drawText(r.translated(1, 1), Qt.AlignmentFlag.AlignLeft, self.hud)
            p.setPen(QColor(HUD_COLOR))
            p.drawText(r, Qt.AlignmentFlag.AlignLeft, self.hud)
        p.end()


class ViewportToolFilter(QObject):

    def __init__(self, canvas: QWidget, controller: ModelingController) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.controller = controller
        self.overlay = ToolOverlay(canvas)
        self._press: QPointF | None = None
        self._press_event: QMouseEvent | None = None
        self._dragging = False
        self._start_value = 0.0
        self._cm_per_px = 1.0
        self._line_a: np.ndarray | None = None
        self._pending_edge: tuple[int, int] | None = None
        self._path_edges: list[tuple[int, int]] = []
        self._replaying = False
        self._preview_pending = False
        self._preview_key: tuple | None = None
        self._preview_skipped = False
        canvas.installEventFilter(self)
        canvas.setMouseTracking(True)
        controller.toolChanged.connect(self._on_tool_changed)
        controller.sessionChanged.connect(self._reset_path)
        scene = controller.scene
        for signal in (scene.changed, scene.selectionChanged, scene.modeChanged, scene.objectsChanged,
                       controller.paramsChanged, controller.toolChanged):
            signal.connect(self._schedule_preview)

    def _on_tool_changed(self, *_args) -> None:
        self.overlay.clear()
        self._pending_edge = None
        self._preview_key = None
        self._reset_path()

    def _schedule_preview(self, *_args) -> None:
        if self._preview_pending:
            return
        self._preview_pending = True
        QTimer.singleShot(0, self._refresh_preview)

    def _preview_spec(self):
        spec = self._spec()
        if spec is None or (spec.extra or {}).get("preview") != SKIN_PREVIEW:
            return None
        scene = self.controller.scene
        obj = scene.active
        if scene.mode != "points" or obj is None or not editable(scene, obj) or not obj.mesh.loose_edges:
            return None
        return spec

    def _hide_preview(self) -> None:
        self._preview_key = None
        self._preview_skipped = False
        if self.overlay.preview_wire is not None:
            self.overlay.preview_wire = None
            self.overlay.update()

    def _refresh_preview(self) -> None:
        self._preview_pending = False
        spec = self._preview_spec()
        if spec is None:
            self._hide_preview()
            return
        from .ops_trunk import preview_wire

        obj = self.controller.scene.active
        mesh = obj.mesh
        if len(mesh.points) > SKIN_PREVIEW_BUDGET:
            self._preview_key = None
            if self.overlay.preview_wire is not None:
                self.overlay.preview_wire = None
                self.overlay.update()
            if not self._preview_skipped:
                self._preview_skipped = True
                self.controller.message.emit(
                    f"{spec.name}: preview skipped, the Line has more than {SKIN_PREVIEW_BUDGET} points")
            return
        self._preview_skipped = False
        params = self.controller.params()
        scales = mesh.point_scales
        key = (id(obj), mesh.points.tobytes(), tuple(mesh.loose_edges),
               None if scales is None else scales.tobytes(),
               tuple(sorted(params.items())), obj.position.tobytes(), obj.rotation.tobytes(),
               obj.scale.tobytes())
        if key == self._preview_key and self.overlay.preview_wire is not None:
            return
        self._preview_key = key
        points, edges = preview_wire(mesh, params)
        if len(edges):
            self.overlay.preview_wire = (obj.to_world(points), edges)
        else:
            self.overlay.preview_wire = None
        self.overlay.update()

    def _reset_path(self) -> None:
        self._path_edges = []

    def _spec(self):
        tool = self.controller.tool_id
        if tool is None or self.controller.scene.tool != tool:
            return None
        return get_tool(tool)

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if obj is not self.canvas or self._replaying:
            return False
        spec = self._spec()
        if spec is None:
            return False
        t = ev.type()
        active = self.controller.scene.active
        if active is not None and not editable(self.controller.scene, active):
            if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                self.controller.message.emit(f"{spec.name}: {EDITABLE_MESSAGE}")
            self.overlay.clear()
            return False
        if t == QEvent.Type.MouseButtonPress:
            return self._on_press(spec, ev)
        if t == QEvent.Type.MouseMove:
            return self._on_move(spec, ev)
        if t == QEvent.Type.MouseButtonRelease:
            return self._on_release(spec, ev)
        if t == QEvent.Type.KeyPress and self._press is not None and _controls().modal_key(ev, "cancel"):
            self._abort()
            return True
        return False

    def _pick_kind(self, spec) -> str:
        return str(spec.extra.get("pick", "")) if spec.extra else ""

    def _two_edges(self, spec) -> bool:
        return spec.param("edge_a") is not None and spec.param("edge_b") is not None

    def _blocked(self, ev: QMouseEvent) -> bool:
        held = getattr(self.canvas, "_held_keys", None)
        return _controls().is_navigation_press(ev, held if held is not None else set())

    def _on_press(self, spec, ev: QMouseEvent) -> bool:
        if ev.button() != Qt.MouseButton.LeftButton or self._blocked(ev):
            if self._press is not None and ev.button() == Qt.MouseButton.RightButton:
                self._abort()
                return True
            return False
        if ev.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
            return False
        self.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
        self._press = QPointF(ev.position())
        self._press_event = QMouseEvent(ev.type(), ev.position(), ev.globalPosition(), ev.button(),
                                        ev.buttons(), ev.modifiers())
        self._dragging = False
        if self._pick_kind(spec) == PICK_LINE:
            self._line_a = self._world_on_view_plane(ev.position())
        return True

    def _on_move(self, spec, ev: QMouseEvent) -> bool:
        pos = QPointF(ev.position())
        kind = self._pick_kind(spec)
        if self._press is None:
            if kind == PICK_EDGE:
                self._update_hover(pos)
            return False
        if not ev.buttons() & Qt.MouseButton.LeftButton:
            return False
        delta = pos - self._press
        if not self._dragging:
            if abs(delta.x()) + abs(delta.y()) < _drag_threshold():
                return True
            if kind in (PICK_POINT, PICK_PLANE) or self._two_edges(spec):
                self._dragging = True
            elif self._begin_drag(spec, kind):
                self._dragging = True
            else:
                self._press = None
                return True
        if kind == PICK_LINE or self._two_edges(spec):
            self.overlay.preview_line = (self._press, pos)
            self.overlay.update()
            return True
        if kind == PICK_EDGE and not self._edge_drag_sets_param(spec):
            self._apply_edge(spec, self._press, pos)
            return True
        if kind in (PICK_POINT, PICK_PLANE):
            return True
        drag_key = self._drag_param(spec)
        if drag_key:
            amount = drag_amount(spec.drag_kind, delta.x(), self._cm_per_px)
            param = spec.param(drag_key)
            value = self._start_value + amount
            if param is not None and param.kind == "int":
                value = int(round(value))
            values = {**self._context(spec), drag_key: value}
            if kind == PICK_EDGE and spec.param("edge") is not None:
                found = self._edge_under(self._press)
                if found is not None:
                    values["edge"] = found[0]
            self.controller.apply_live(values)
            self.overlay.hud = f"{param.label if param else drag_key}: {self._format(param, value)}"
            self.overlay.hud_pos = pos
            self.overlay.update()
        return True

    def _on_release(self, spec, ev: QMouseEvent) -> bool:
        if self._press is None or ev.button() != Qt.MouseButton.LeftButton:
            return False
        press, self._press = self._press, None
        kind = self._pick_kind(spec)
        pos = QPointF(ev.position())
        if kind == PICK_LINE:
            self.overlay.preview_line = None
            if self._dragging:
                self._apply_line(spec, press, pos)
            self.overlay.update()
            return True
        if self._two_edges(spec):
            self.overlay.preview_line = None
            self._finish_two_edges(spec, press, pos)
            self.overlay.update()
            return True
        if kind == PICK_EDGE:
            if not self._dragging:
                self._apply_edge(spec, press, press, click=True)
            self.overlay.hud = ""
            self.overlay.update()
            return True
        if kind in (PICK_POINT, PICK_PLANE):
            if not self._dragging:
                self._apply_pick(spec, kind, press)
            self.overlay.update()
            return True
        if not self._dragging:
            self._replay_click(ev)
            return True
        self.overlay.hud = ""
        self.overlay.update()
        return True

    def _abort(self) -> None:
        self._press = None
        self._dragging = False
        self._pending_edge = None
        self.controller.cancel()
        self.overlay.clear()

    def _replay_click(self, release: QMouseEvent) -> None:
        press = self._press_event
        self._press_event = None
        if press is None:
            return
        self._replaying = True
        try:
            QApplication.sendEvent(self.canvas, press)
            rel = QMouseEvent(release.type(), release.position(), release.globalPosition(),
                              release.button(), release.buttons(), release.modifiers())
            QApplication.sendEvent(self.canvas, rel)
        finally:
            self._replaying = False

    def _format(self, param, value) -> str:
        if param is None:
            return f"{value:.2f}"
        if param.kind == "distance":
            return f"{value:.2f} cm"
        if param.kind == "percent":
            return f"{value:.1f} %"
        if param.kind == "angle":
            return f"{value:.1f}°"
        if param.kind == "int":
            return str(int(value))
        return f"{value:.3f}"

    def _selection_depth(self) -> float:
        scene = self.controller.scene
        center = scene.selection_center()
        if center is None and scene.active is not None:
            center = scene.active.position
        if center is None:
            return float(self.canvas.camera.eye_distance())
        return float(self.canvas.camera.depth(np.atleast_2d(center))[0])

    def _edge_drag_sets_param(self, spec) -> bool:
        return bool(spec.drag_param) and not (spec.extra and spec.extra.get("edge_offset_param"))

    def _begin_drag(self, spec, kind: str) -> bool:
        if kind == PICK_LINE:
            return self._line_a is not None
        self.controller.new_transform()
        session = self.controller.begin()
        if session is None:
            return False
        self._cm_per_px = float(self.canvas.px_size(max(self._selection_depth(), 1e-3)))
        drag_key = self._drag_param(spec)
        if drag_key:
            self._start_value = float(self.controller.params().get(drag_key, 0.0) or 0.0)
            param = spec.param(drag_key)
            if param is not None and param.kind in ("distance", "angle"):
                self._start_value = 0.0
            if param is not None and param.kind == "int":
                self._start_value = float(param.default)
            if param is not None and drag_key in (spec.extra or {}).get("drag_from_default", ()):
                self._start_value = float(param.default)
        return True

    def _drag_param(self, spec) -> str | None:
        per_mode = spec.extra.get("drag_params") if spec.extra else None
        if per_mode:
            return per_mode.get(self.controller.scene.mode, spec.drag_param)
        return spec.drag_param

    def _world_on_view_plane(self, pos) -> np.ndarray | None:
        scene = self.controller.scene
        center = scene.selection_center()
        if center is None and scene.active is not None:
            center = scene.active.world_points().mean(axis=0) if len(scene.active.mesh.points) else scene.active.position
        if center is None:
            center = np.zeros(3)
        normal = self.canvas.view_direction()
        return self.canvas.unproject(pos, (np.asarray(center, float), normal))

    def _context(self, spec) -> dict:
        obj = self.controller.scene.active
        if obj is None:
            return {}
        _pos, fwd, right, up = self.canvas.camera.basis()
        values: dict = {}
        if spec.param("object_linear") is not None:
            values["object_linear"] = _rows(obj.linear())
        if spec.param("object_position") is not None:
            values["object_position"] = _vec(obj.position)
        if spec.param("object_matrix") is not None:
            values["object_matrix"] = _rows(_matrix4(obj))
        if spec.param("camera_rotation") is not None:
            values["camera_rotation"] = _rows(np.column_stack([right, up, -fwd]))
        if spec.param("view_dir") is not None:
            values["view_dir"] = _vec(fwd)
        if spec.param("view_direction") is not None:
            values["view_direction"] = _vec(obj.to_local_vector(fwd))
        return values

    def _ensure_session(self) -> bool:
        session = self.controller.session
        if session is not None and not session.closed:
            return True
        self.controller.new_transform()
        return self.controller.begin() is not None

    def _send(self, spec, values: dict) -> None:
        if not self._ensure_session():
            return
        self.controller.apply_live({**self._context(spec), **values})

    def _refuse(self, spec, text: str) -> None:
        self.controller.message.emit(f"{spec.name}: {text}")

    def _apply_line(self, spec, a_pos: QPointF, b_pos: QPointF) -> None:
        a = self._line_a
        b = self._world_on_view_plane(b_pos)
        self._line_a = None
        if a is None or b is None or float(np.linalg.norm(b - a)) < 1e-6:
            self._refuse(spec, "draw a cut line in the viewport first")
            return
        self.controller.new_transform()
        self._send(spec, {"start": _vec(a), "end": _vec(b)})

    def _vertex_under(self, pos: QPointF) -> int | None:
        obj = self.controller.scene.active
        if obj is None or not len(obj.mesh.points):
            return None
        world = obj.world_points()
        hit = self.canvas.hit_at(pos)
        if hit is not None and hit[0] is obj:
            poly = obj.mesh.polygons[hit[1]]
            point = np.asarray(hit[2], float)
            return int(min(poly, key=lambda i: float(np.linalg.norm(world[i] - point))))
        screen = self.canvas.project_world(world)
        d = np.hypot(screen[:, 0] - float(pos.x()), screen[:, 1] - float(pos.y()))
        d = np.where(np.isnan(d), np.inf, d)
        j = int(np.argmin(d))
        return j if d[j] <= POINT_PICK_PX else None

    def _origin(self, obj, pos: QPointF, local: bool) -> tuple:
        world = self.canvas.cursor_point(pos)
        return _vec(obj.to_local_point(world) if local else world)

    def _pick_values(self, spec, kind: str, pos: QPointF) -> tuple[dict, str | None]:
        obj = self.controller.scene.active
        if obj is None:
            return {}, "select an object first"
        params = self.controller.params()
        values: dict = {}
        if kind == PICK_POINT:
            if spec.param("target") is not None:
                vertex = self._vertex_under(pos)
                if vertex is None:
                    return {}, "no point under the cursor"
                values["target"] = vertex
            if spec.param("plane_origin") is not None:
                values["plane_origin"] = self._origin(obj, pos, params.get("coordinate_system") != "World")
        elif kind == PICK_PLANE and spec.param("plane_position") is not None:
            values["plane_position"] = self._origin(obj, pos, params.get("mode") == "Local")
        return values, None

    def _apply_pick(self, spec, kind: str, pos: QPointF) -> None:
        values, error = self._pick_values(spec, kind, pos)
        if error:
            self._refuse(spec, error)
            return
        self._send(spec, values)

    def _finish_two_edges(self, spec, press: QPointF, pos: QPointF) -> None:
        if self._dragging:
            self._pending_edge = None
            first = self._edge_under(press)
            second = self._edge_under(pos)
            if first is None or second is None:
                self._refuse(spec, "drag from one edge to another edge")
                return
            if first[0] == second[0]:
                self._refuse(spec, "pick a different second edge")
                return
            self._send(spec, {"edge_a": first[0], "edge_b": second[0]})
            return
        found = self._edge_under(press)
        if found is None:
            self._refuse(spec, "no edge under the cursor")
            return
        edge = found[0]
        if self._pending_edge is None:
            self._pending_edge = edge
            self.controller.message.emit(f"{spec.name}: click the second edge")
            return
        if edge == self._pending_edge:
            self._refuse(spec, "pick a different second edge")
            return
        first, self._pending_edge = self._pending_edge, None
        self._send(spec, {"edge_a": first, "edge_b": edge})

    def _edge_under(self, pos: QPointF):
        scene = self.controller.scene
        obj = scene.active
        if obj is None or not len(obj.mesh.points):
            return None
        hit = self.canvas.hit_at(pos)
        world = obj.world_points()
        screen = self.canvas.project_world(world)
        x, y = float(pos.x()), float(pos.y())
        candidates = []
        if hit is not None and hit[0] is obj:
            poly = obj.mesh.polygons[hit[1]]
            candidates = [_edge_key(a, b) for a, b in zip(poly, poly[1:] + poly[:1])]
        else:
            candidates = list(obj.mesh.edges)
        best = None
        for e in candidates:
            a, b = screen[e[0]], screen[e[1]]
            if np.any(np.isnan(a)) or np.any(np.isnan(b)):
                continue
            d, t = _point_segment(x, y, a, b)
            limit = math.inf if hit is not None and hit[0] is obj else EDGE_PICK_PX
            if d <= limit and (best is None or d < best[0]):
                best = (d, e, t)
        if best is None:
            return None
        return best[1], best[2], screen

    def _update_hover(self, pos: QPointF) -> None:
        found = self._edge_under(pos)
        if found is None:
            if self.overlay.hover_edge is not None:
                self.overlay.hover_edge = None
                self.overlay.update()
            return
        e, _t, screen = found
        a, b = screen[e[0]], screen[e[1]]
        self.overlay.hover_edge = (QPointF(float(a[0]), float(a[1])), QPointF(float(b[0]), float(b[1])))
        self.overlay.update()

    def _apply_edge(self, spec, press: QPointF, pos: QPointF, click: bool = False) -> None:
        found = self._edge_under(press)
        if found is None:
            if click:
                self._refuse(spec, "no edge under the cursor")
            return
        e, t, _screen = found
        if not click and self._dragging:
            found_now = self._edge_under_on(e, pos)
            if found_now is not None:
                t = found_now
        offset_key = spec.extra.get("edge_offset_param") if spec.extra else None
        values: dict = {"edge": e}
        if offset_key:
            values[offset_key] = float(np.clip(t, 0.0, 1.0)) * 100.0
        if not self._ensure_session():
            return
        if click and spec.param("path") is not None and self.controller.params().get("mode") == "Path":
            if e not in self._path_edges:
                self._path_edges.append(e)
            values["path"] = list(self._path_edges)
        self._send(spec, values)

    def _edge_under_on(self, e, pos: QPointF) -> float | None:
        obj = self.controller.scene.active
        if obj is None:
            return None
        screen = self.canvas.project_world(obj.world_points()[[e[0], e[1]]])
        if np.any(np.isnan(screen)):
            return None
        _d, t = _point_segment(float(pos.x()), float(pos.y()), screen[0], screen[1])
        return t


def _point_segment(x: float, y: float, a, b) -> tuple[float, float]:
    ax, ay, bx, by = float(a[0]), float(a[1]), float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1e-12:
        return math.hypot(x - ax, y - ay), 0.0
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy)), t
