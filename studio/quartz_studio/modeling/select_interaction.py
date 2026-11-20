from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import theme

__all__ = ["SelectionToolFilter", "SelectionOverlay", "SelectionOptionsPanel", "install",
           "brush_hits", "round_even"]

OPTIONS_KEY = "selection.options"
BRUSH_TOOL = "select"
FILL_TOOL = "select_fill"
PHONG_TOOL = "select_phong"
CLICK_TOOLS = ("select_loop", "select_ring", "select_pattern", "select_fill", "select_phong")
POLYGON_TOOLS = (FILL_TOOL, PHONG_TOOL)
WHEEL_FACTOR = 1.25
MIN_NOTCH_CHANGE = 2
RADIUS_KEY_STEP = 2
SAMPLE_ANGLES = tuple(range(0, 360, 45))
PREVIEW_EDGE_PX = 2
PREVIEW_POINT_PX = 6
PREVIEW_FILL_ALPHA = 64
LABEL_WIDTH = 160
ROW_INDENT = 14
ROW_H = 24
ROW_SPACING = 4
BUTTON_H = 24
MARGIN_SIDE = 8
MARGIN_TOP = 4
MARGIN_BOTTOM = 8
MODE_MESSAGE = "switch to Polygons mode"

_SELECT_TOOLS = None


def _tools():
    global _SELECT_TOOLS
    if _SELECT_TOOLS is None:
        from . import select_tools
        _SELECT_TOOLS = select_tools
    return _SELECT_TOOLS


def _message(text: str) -> None:
    from .install import controller
    controller().message.emit(text)


def _click_threshold() -> int:
    from .. import controls
    return int(controls.cursor("drag_threshold"))


def _navigation_press(ev, held) -> bool:
    from .. import controls
    return bool(controls.is_navigation_press(ev, held))


def round_even(value: float) -> int:
    return int(2 * round(value / 2.0))


def _edge_key(a: int, b: int) -> tuple[int, int]:
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


def _segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length <= 1e-18 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _op_for(mods, fill: bool = False) -> str:
    if mods & Qt.KeyboardModifier.ControlModifier:
        return "remove"
    if fill or mods & Qt.KeyboardModifier.ShiftModifier:
        return "add"
    return "replace"


def _poly_array(canvas, view, k: int, cache: dict):
    if k in cache:
        return cache[k]
    poly, _depth = canvas._poly_screen(view, k)
    if poly is None:
        cache[k] = (None, None)
    else:
        cache[k] = (poly, np.array([(p.x(), p.y()) for p in poly], float).reshape(-1, 2))
    return cache[k]


def _brush_points(canvas, view, cx, cy, radius, visible_only) -> set:
    cand = np.asarray(view.in_front, bool).copy()
    if visible_only:
        cand &= np.asarray(view.visible_points, bool)
    idx = np.nonzero(cand)[0]
    if not len(idx):
        return set()
    d = np.hypot(view.screen[idx, 0] - cx, view.screen[idx, 1] - cy)
    idx = idx[d <= radius]
    if visible_only and len(idx):
        idx = idx[np.asarray(canvas._sight_clear(view.world[idx]), bool)]
    return {int(i) for i in idx}


def _brush_edges(canvas, view, cx, cy, radius, visible_only, tolerant) -> set:
    edges = view.visible_edges if visible_only else view.obj.mesh.edges
    hits = []
    in_front = view.in_front
    screen = view.screen
    for a, b in edges:
        if in_front[a] and in_front[b]:
            ax, ay = screen[a]
            bx, by = screen[b]
        else:
            line = canvas._edge_screen(view, (a, b))
            if line is None:
                continue
            ax, ay, bx, by = line.x1(), line.y1(), line.x2(), line.y2()
        if tolerant:
            d = _segment_distance(cx, cy, ax, ay, bx, by)
        else:
            d = math.hypot((ax + bx) / 2.0 - cx, (ay + by) / 2.0 - cy)
        if d <= radius:
            hits.append(_edge_key(a, b))
    if visible_only and hits:
        arr = np.asarray(hits, int).reshape(-1, 2)
        mids = (view.world[arr[:, 0]] + view.world[arr[:, 1]]) / 2.0
        clear = np.asarray(canvas._sight_clear(mids), bool)
        hits = [e for e, ok in zip(hits, clear) if ok]
    return set(hits)


def _brush_polygons(canvas, view, cx, cy, radius, visible_only, tolerant, cache) -> set:
    polygons = view.obj.mesh.polygons
    cand = np.nonzero(view.front)[0] if visible_only else range(len(polygons))
    hits = []
    centre = QPointF(cx, cy)
    for k in cand:
        k = int(k)
        poly, pts = _poly_array(canvas, view, k, cache)
        if poly is None or not len(pts):
            continue
        if not tolerant:
            mean = pts.mean(axis=0)
            hit = math.hypot(mean[0] - cx, mean[1] - cy) <= radius
        else:
            hit = poly.containsPoint(centre, Qt.FillRule.OddEvenFill)
            if not hit:
                hit = bool((np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) <= radius).any())
            if not hit:
                nxt = np.roll(pts, -1, axis=0)
                hit = any(_segment_distance(cx, cy, p[0], p[1], q[0], q[1]) <= radius
                          for p, q in zip(pts, nxt))
        if hit:
            hits.append(k)
    if visible_only and hits:
        cents = np.array([view.world[list(polygons[k])].mean(axis=0) for k in hits], float)
        clear = np.asarray(canvas._sight_clear(cents), bool)
        hits = [k for k, ok in zip(hits, clear) if ok]
    return set(hits)


def brush_hits(canvas, view, mode: str, centre, radius: float, visible_only: bool = True,
               tolerant: bool = False, cache: dict | None = None) -> set:
    cx, cy = float(centre.x()), float(centre.y())
    if mode == "points":
        return _brush_points(canvas, view, cx, cy, radius, visible_only)
    if mode == "edges":
        return _brush_edges(canvas, view, cx, cy, radius, visible_only, tolerant)
    if mode == "polygons":
        return _brush_polygons(canvas, view, cx, cy, radius, visible_only, tolerant,
                               {} if cache is None else cache)
    return set()


def object_under_brush(canvas, centre, radius: float):
    obj = canvas.pick_object(QPointF(centre))
    if obj is not None:
        return obj
    for r in (radius / 2.0, radius):
        for angle in SAMPLE_ANGLES:
            a = math.radians(angle)
            obj = canvas.pick_object(QPointF(centre.x() + r * math.cos(a), centre.y() + r * math.sin(a)))
            if obj is not None:
                return obj
    return None


class SelectionOverlay(QWidget):

    def __init__(self, canvas: QWidget) -> None:
        super().__init__(canvas)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.circle: tuple[QPointF, float, str] | None = None
        self.preview_obj = None
        self.preview_kind = ""
        self.preview_items: set = set()
        canvas.installEventFilter(self)
        self.setGeometry(canvas.rect())
        self.raise_()
        self.show()

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if obj is self.parentWidget() and ev.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
        return False

    def set_circle(self, centre: QPointF | None, radius: float = 0.0, color: str = "") -> None:
        value = None if centre is None else (QPointF(centre), float(radius), color)
        if value != self.circle:
            self.circle = value
            self.update()

    def set_preview(self, obj, kind: str, items) -> None:
        items = set(items or ())
        if obj is self.preview_obj and kind == self.preview_kind and items == self.preview_items:
            return
        self.preview_obj = obj if items else None
        self.preview_kind = kind if items else ""
        self.preview_items = items
        self.update()

    def clear_preview(self) -> None:
        self.set_preview(None, "", ())

    def clear(self) -> None:
        self.clear_preview()
        self.set_circle(None)

    def paintEvent(self, _e) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.preview_obj is not None and self.preview_items:
            self._paint_preview(painter)
        if self.circle is not None:
            centre, radius, color = self.circle
            painter.setPen(QPen(QColor(color), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centre, radius, radius)
        painter.end()

    def _paint_preview(self, painter: QPainter) -> None:
        obj = self.preview_obj
        canvas = self.parentWidget()
        try:
            world = obj.world_points()
        except (AttributeError, ValueError, TypeError, np.linalg.LinAlgError):
            return
        if not len(world):
            return
        screen = canvas.project_world(world)
        bad = np.isnan(screen).any(axis=1)
        soft = QColor(theme.SELECT_FRONT_SOFT)
        kind = self.preview_kind
        count = len(world)
        if kind == "edges":
            painter.setPen(QPen(soft, PREVIEW_EDGE_PX))
            for a, b in self.preview_items:
                if a >= count or b >= count or bad[a] or bad[b]:
                    continue
                painter.drawLine(QPointF(*screen[a]), QPointF(*screen[b]))
        elif kind == "polygons":
            fill = QColor(soft)
            fill.setAlpha(PREVIEW_FILL_ALPHA)
            painter.setPen(QPen(soft, 1))
            painter.setBrush(fill)
            polygons = obj.mesh.polygons
            for k in self.preview_items:
                if not 0 <= k < len(polygons):
                    continue
                idx = list(polygons[k])
                if any(i >= count for i in idx) or bad[idx].any():
                    continue
                painter.drawPolygon(QPolygonF([QPointF(*screen[i]) for i in idx]))
        elif kind == "points":
            half = PREVIEW_POINT_PX / 2.0
            for i in self.preview_items:
                if i >= count or bad[i]:
                    continue
                x, y = screen[i]
                painter.fillRect(QRectF(x - half, y - half, PREVIEW_POINT_PX, PREVIEW_POINT_PX), soft)


@dataclass
class _Stroke:
    tool: str
    op: str
    mode: str
    press: QPointF
    last: QPointF
    view: object = None
    radius: float = 0.0
    visible_only: bool = True
    tolerant: bool = False
    items: set = field(default_factory=set)
    kind: str = ""
    polys: dict = field(default_factory=dict)


class SelectionToolFilter(QObject):

    def __init__(self, canvas: QWidget, parent: QObject | None = None) -> None:
        super().__init__(parent if parent is not None else canvas)
        self.canvas = canvas
        self.scene = canvas.scene
        self.overlay = SelectionOverlay(canvas)
        self.panel = None
        self._stroke: _Stroke | None = None
        self._grouped = False
        self._hover_key = None
        self._hover_value: tuple = (None, "", set())
        self._cursor: QPointF | None = None
        tools = _tools()
        self._tools = tools
        canvas.installEventFilter(self)
        scene = self.scene
        scene.toolChanged.connect(self._on_tool)
        scene.modeChanged.connect(self._clear_cache)
        scene.objectsChanged.connect(self._clear_cache)
        scene.changed.connect(self._clear_cache)
        scene.selectionChanged.connect(self._on_selection)
        if tools.is_select_tool(scene.tool):
            self._on_tool(scene.tool)

    def active(self) -> bool:
        return bool(self._tools.is_select_tool(self.scene.tool))

    def tool(self):
        return self._tools.get(self.scene.tool)

    def _clear_cache(self, *_args) -> None:
        self._hover_key = None
        self._hover_value = (None, "", set())
        if self._stroke is None:
            self._refresh_hover()

    def _on_selection(self) -> None:
        if self._stroke is None and self.scene.tool == FILL_TOOL:
            self._hover_key = None
            self._refresh_hover()

    def _on_tool(self, tool: str) -> None:
        self._end_stroke()
        self.overlay.clear()
        self._hover_key = None
        self._hover_value = (None, "", set())
        if not self._tools.is_select_tool(tool):
            return
        self._tools.ensure_mode(self.scene, tool)
        canvas = self.canvas
        if canvas.isVisible() and canvas.underMouse():
            self._cursor = QPointF(canvas.mapFromGlobal(QCursor.pos()))
            self._refresh_hover()

    def _options(self, tool_id: str) -> dict:
        return self._tools.options(tool_id)

    def _blocked(self) -> bool:
        canvas = self.canvas
        return bool(canvas._held_keys) or canvas._nav is not None

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if obj is not self.canvas:
            return False
        kind = ev.type()
        T = QEvent.Type
        if kind == T.FocusOut:
            self._end_stroke()
            return False
        if kind == T.Leave:
            self._cursor = None
            if self._stroke is None:
                self.overlay.clear()
            return False
        if not self.active():
            if self._stroke is not None:
                self._end_stroke()
            return False
        if kind in (T.MouseButtonPress, T.MouseButtonDblClick):
            return self._press(ev)
        if kind == T.MouseMove:
            return self._move(ev)
        if kind == T.MouseButtonRelease:
            return self._release(ev)
        if kind == T.Wheel:
            return self._wheel(ev)
        if kind == T.KeyPress:
            return self._key(ev)
        return False

    def _press(self, ev) -> bool:
        if ev.button() != Qt.MouseButton.LeftButton:
            return False
        mods = ev.modifiers()
        if mods & Qt.KeyboardModifier.AltModifier or self._blocked():
            return False
        if _navigation_press(ev, self.canvas._held_keys):
            return False
        if self._stroke is not None:
            return True
        self.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = QPointF(ev.position())
        self._cursor = QPointF(pos)
        tool = self.tool()
        scene = self.scene
        mode = scene.mode
        if mode != "model" and not scene.is_editable(scene.active):
            if scene.active is not None:
                from .session import EDITABLE_MESSAGE
                _message(f"{tool.name}: {EDITABLE_MESSAGE}")
            return True
        if tool.id in POLYGON_TOOLS and mode != "polygons":
            _message(f"{tool.name}: {MODE_MESSAGE}")
            return True
        if tool.id == BRUSH_TOOL:
            self._press_brush(pos, mods)
        else:
            self._press_click(tool.id, pos, mods)
        return True

    def _begin_group(self) -> None:
        if not self._grouped:
            self.scene.begin_group()
            self._grouped = True

    def _end_stroke(self) -> None:
        self._stroke = None
        if self._grouped:
            self._grouped = False
            self.scene.end_group()
        if self.active() and self._cursor is not None:
            self._refresh_hover()

    def _press_brush(self, pos: QPointF, mods) -> None:
        scene = self.scene
        opts = self._options(BRUSH_TOOL)
        op = _op_for(mods)
        st = _Stroke(BRUSH_TOOL, op, scene.mode, QPointF(pos), QPointF(pos),
                     radius=float(opts.get("radius", 10)),
                     visible_only=bool(opts.get("visible_only", True)),
                     tolerant=bool(opts.get("tolerant", False)))
        self._begin_group()
        self._stroke = st
        if st.mode == "model":
            obj = object_under_brush(self.canvas, pos, st.radius)
            if op == "remove":
                if obj is not None:
                    self._tools.apply_selection(scene, "model", {obj}, "remove")
            elif obj is None:
                if op == "replace":
                    self._tools.apply_selection(scene, "model", set(), "replace")
            else:
                self._tools.apply_selection(scene, "model", {obj}, op)
        else:
            if scene.active is not None:
                st.view = self.canvas._object_view(scene.active)
            self._dab(pos, first=True)
        self._show_circle(pos)

    def _dab(self, pos: QPointF, first: bool = False) -> None:
        st = self._stroke
        scene = self.scene
        if st.mode == "model":
            obj = object_under_brush(self.canvas, pos, st.radius)
            if obj is not None:
                self._tools.apply_selection(scene, "model", {obj}, "remove" if st.op == "remove" else "add")
            return
        hits = set() if st.view is None else brush_hits(self.canvas, st.view, st.mode, pos, st.radius,
                                                        st.visible_only, st.tolerant, st.polys)
        if first and st.op == "replace":
            self._tools.apply_selection(scene, st.mode, hits, "replace")
        elif hits:
            self._tools.apply_selection(scene, st.mode, hits, "remove" if st.op == "remove" else "add")

    def _stroke_to(self, pos: QPointF) -> None:
        st = self._stroke
        spacing = max(1.0, st.radius / 2.0)
        dx, dy = pos.x() - st.last.x(), pos.y() - st.last.y()
        dist = math.hypot(dx, dy)
        steps = int(dist // spacing)
        if not steps:
            return
        start = QPointF(st.last)
        for i in range(1, steps + 1):
            f = i * spacing / dist
            point = QPointF(start.x() + dx * f, start.y() + dy * f)
            self._dab(point)
            st.last = point
            if self._stroke is None:
                return

    def _circle_color(self) -> str:
        st = self._stroke
        if st is None or st.tool != BRUSH_TOOL:
            return theme.TEXT_SECONDARY
        return theme.TEXT_MUTED if st.op == "remove" else theme.SELECT_FRONT

    def _show_circle(self, pos: QPointF | None) -> None:
        if pos is None or self.scene.tool != BRUSH_TOOL:
            self.overlay.set_circle(None)
            return
        radius = self._stroke.radius if self._stroke is not None else float(
            self._options(BRUSH_TOOL).get("radius", 10))
        self.overlay.set_circle(pos, radius, self._circle_color())

    def _press_click(self, tool_id: str, pos: QPointF, mods) -> None:
        op = _op_for(mods, fill=tool_id == FILL_TOOL)
        obj, kind, items = self._preview(tool_id, pos, mods)
        self._begin_group()
        self._stroke = _Stroke(tool_id, op, self.scene.mode, QPointF(pos), QPointF(pos),
                               items=set(items), kind=kind)

    def _move(self, ev) -> bool:
        pos = QPointF(ev.position())
        buttons = ev.buttons()
        st = self._stroke
        if st is not None:
            if not buttons & Qt.MouseButton.LeftButton or buttons & ~Qt.MouseButton.LeftButton \
                    or self._blocked():
                if not buttons & Qt.MouseButton.LeftButton:
                    self._end_stroke()
                return False
            self._cursor = QPointF(pos)
            if st.tool == BRUSH_TOOL:
                self._stroke_to(pos)
                self._show_circle(pos)
            return True
        self._cursor = QPointF(pos)
        if buttons != Qt.MouseButton.NoButton:
            return False
        self._refresh_hover(ev.modifiers())
        return False

    def _release(self, ev) -> bool:
        if ev.button() != Qt.MouseButton.LeftButton:
            return False
        st = self._stroke
        if st is None:
            return False
        pos = QPointF(ev.position())
        blocked = self._blocked()
        if st.tool != BRUSH_TOOL and not blocked:
            moved = abs(pos.x() - st.press.x()) + abs(pos.y() - st.press.y())
            if moved < _click_threshold() and st.items:
                self._tools.apply_selection(self.scene, st.mode, st.items, st.op)
            elif moved < _click_threshold() and st.op == "replace" and (
                    st.mode == "model" or self.canvas.pick(pos)[0] is None):
                click = getattr(self.canvas, "click_select", None)
                if click is not None:
                    click(pos, "select")
        self._cursor = QPointF(pos)
        self._end_stroke()
        return not blocked

    def _wheel(self, ev) -> bool:
        if self.scene.tool != BRUSH_TOOL or self._blocked():
            return False
        mods = ev.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if mods != Qt.KeyboardModifier.ShiftModifier:
            return False
        delta = ev.angleDelta()
        notches = (delta.y() or delta.x()) / 120.0
        if not notches:
            ev.accept()
            return True
        radius = int(self._options(BRUSH_TOOL).get("radius", 10))
        target = round_even(radius * WHEEL_FACTOR ** notches)
        least = max(MIN_NOTCH_CHANGE, round_even(MIN_NOTCH_CHANGE * abs(notches)))
        if notches > 0:
            target = max(target, radius + least)
        else:
            target = min(target, radius - least)
        self._set_radius(target)
        self._cursor = QPointF(ev.position())
        self._show_circle(self._cursor)
        ev.accept()
        return True

    def _set_radius(self, value: int) -> None:
        param = next(p for p in self._tools.get(BRUSH_TOOL).params if p.key == "radius")
        value = param.clamp(value)
        self._tools.set_option(BRUSH_TOOL, "radius", value)
        if self._stroke is not None and self._stroke.tool == BRUSH_TOOL:
            self._stroke.radius = float(value)
        if self._cursor is not None:
            self._show_circle(self._cursor)

    def _key(self, ev) -> bool:
        key = ev.key()
        if key == Qt.Key.Key_Escape and self._stroke is not None:
            self._end_stroke()
            ev.accept()
            return True
        if key not in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight):
            return False
        if self.scene.tool != BRUSH_TOOL or not self.canvas.hasFocus() or self._blocked():
            return False
        if ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            return False
        radius = int(self._options(BRUSH_TOOL).get("radius", 10))
        step = -RADIUS_KEY_STEP if key == Qt.Key.Key_BracketLeft else RADIUS_KEY_STEP
        self._set_radius(radius + step)
        ev.accept()
        return True

    def _refresh_hover(self, mods=None) -> None:
        pos = self._cursor
        tool = self.scene.tool
        if pos is None or not self._tools.is_select_tool(tool):
            self.overlay.clear()
            return
        if tool == BRUSH_TOOL:
            self.overlay.clear_preview()
            self._show_circle(pos)
            return
        self.overlay.set_circle(None)
        if mods is None:
            from PySide6.QtWidgets import QApplication
            mods = QApplication.keyboardModifiers()
        obj, kind, items = self._preview(tool, pos, mods)
        self.overlay.set_preview(obj, kind, items)

    def hovered(self, pos: QPointF):
        scene = self.scene
        obj = scene.active
        mode = scene.mode
        if obj is None or mode == "model" or not scene.is_editable(obj):
            return None
        canvas = self.canvas
        view = canvas._object_view(obj)
        x, y = float(pos.x()), float(pos.y())
        e = k = p = None
        if self.scene.tool in POLYGON_TOOLS:
            if mode != "polygons":
                return None
            k = canvas._pick_polygon(view, x, y)
            return (view, None, k, None) if k is not None else None
        if mode in ("edges", "points"):
            e = canvas._pick_edge(view, x, y)
        else:
            k = canvas._pick_polygon(view, x, y)
            if k is not None:
                e = self._nearest_side(view, k, x, y)
        if e is None:
            return None
        e = _edge_key(*e)
        if mode == "points":
            p = self._nearest_end(view, e, x, y)
        return view, e, k, p

    def _nearest_side(self, view, k: int, x: float, y: float):
        poly = list(view.obj.mesh.polygons[k])
        best, best_d = None, math.inf
        for a, b in zip(poly, poly[1:] + poly[:1]):
            line = self.canvas._edge_screen(view, (a, b))
            if line is None:
                continue
            d = _segment_distance(x, y, line.x1(), line.y1(), line.x2(), line.y2())
            if d < best_d:
                best, best_d = _edge_key(a, b), d
        return best

    @staticmethod
    def _nearest_end(view, e, x: float, y: float) -> int:
        a, b = e
        da = math.hypot(view.screen[a, 0] - x, view.screen[a, 1] - y) if view.in_front[a] else math.inf
        db = math.hypot(view.screen[b, 0] - x, view.screen[b, 1] - y) if view.in_front[b] else math.inf
        return int(a if da <= db else b)

    def _preview(self, tool_id: str, pos: QPointF, mods) -> tuple:
        found = self.hovered(pos)
        if found is None:
            return None, "", set()
        view, e, k, p = found
        scene = self.scene
        obj = view.obj
        mesh = obj.mesh
        mode = scene.mode
        opts = self._options(tool_id)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        extra: tuple = ()
        if tool_id == FILL_TOOL:
            extra = (ctrl, tuple(sorted(scene.selected_polygons)), tuple(sorted(scene.selected_edges)))
        key = (id(obj), mesh.points.tobytes(), tuple(mesh.polygons), mode, tool_id, e, k, p,
               tuple(sorted(opts.items())), extra)
        if key == self._hover_key:
            return self._hover_value
        items = self._elements(tool_id, mesh, mode, e, k, p, opts, ctrl)
        self._hover_key = key
        self._hover_value = (obj, mode, items)
        return self._hover_value

    def _elements(self, tool_id, mesh, mode, e, k, p, opts, ctrl) -> set:
        tools = self._tools
        scene = self.scene
        if tool_id == "select_loop":
            if mode == "polygons" and (k is None or len(mesh.polygons[k]) != 4):
                return set()
            return set(tools.loop_elements(mesh, mode, e, bool(opts.get("boundary", False))))
        if tool_id == "select_ring":
            return set(tools.ring_elements(mesh, mode, e, k))
        if tool_id == "select_pattern":
            return set(tools.pattern_elements(mesh, mode, e, k, p, int(opts.get("count", 1)),
                                              int(opts.get("skip", 1)), str(opts.get("direction", "Loop"))))
        if tool_id == FILL_TOOL:
            from .meshkit import region_boundary
            selected = set(scene.selected_polygons)
            if ctrl:
                if k not in selected:
                    return set()
                blocked = set(range(len(mesh.polygons))) - selected
                return set(tools.fill_region(mesh, k, set(scene.selected_edges), blocked))
            if k in selected:
                return set()
            borders = set(scene.selected_edges) | {_edge_key(*b) for b in region_boundary(mesh, selected)}
            return set(tools.fill_region(mesh, k, borders, selected))
        if tool_id == PHONG_TOOL:
            return set(tools.phong_region(mesh, k, float(opts.get("angle", 40.0))))
        return set()


class SelectionOptionsPanel(QWidget):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from .. import prefs
        from ..scene import get_scene
        from ..widgets.common import make_card

        self.scene = scene if scene is not None else get_scene()
        self.setObjectName("qsSelectionOptions")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        make_card(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._layout = lay
        self.header: QWidget | None = None
        self.body: QWidget | None = None
        self.editors: dict[str, QWidget] = {}
        self.rows: dict[str, QWidget] = {}
        self.reset_button: QPushButton | None = None
        self.tool_id = ""
        self.scene.toolChanged.connect(self._on_tool)
        prefs.changed.connect(self._on_prefs)
        self._on_tool(self.scene.tool)

    def _on_tool(self, tool: str) -> None:
        tools = _tools()
        spec = tools.get(tool) if tools.is_select_tool(tool) else None
        if spec is None or not spec.params:
            self.tool_id = ""
        else:
            if tool != self.tool_id or self.body is None:
                self.tool_id = tool
                self._build(spec)
            self.sync()
        if self.parentWidget() is not None:
            self.setVisible(bool(self.tool_id))

    def _build(self, spec) -> None:
        from ..widgets.common import FieldRow, PanelTabBar, prepare_combo
        from .panel import ScrubIntSpin, ScrubSpin

        for old in (self.header, self.body):
            if old is not None:
                self._layout.removeWidget(old)
                old.hide()
                old.deleteLater()
        self.editors.clear()
        self.rows.clear()
        self.header = PanelTabBar([spec.name.upper()], self)
        self._layout.addWidget(self.header)
        body = QWidget(self)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(MARGIN_SIDE, MARGIN_TOP, MARGIN_SIDE, MARGIN_BOTTOM)
        bl.setSpacing(ROW_SPACING)
        tool_id = spec.id
        for param in spec.params:
            key = param.key
            if param.kind == "bool":
                editor = QCheckBox(body)
                editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                editor.toggled.connect(lambda v, k=key: self._edit(k, bool(v)))
            elif param.kind == "choice":
                editor = prepare_combo(QComboBox(body))
                editor.addItems(list(param.choices))
                editor.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                editor.activated.connect(lambda i, k=key, c=editor: self._edit(k, c.itemText(i)))
            elif param.kind == "int":
                editor = ScrubIntSpin(body)
                editor.setRange(int(param.minimum), int(param.maximum))
                editor.setSingleStep(max(1, int(param.step)))
                editor.setSuffix(f" {param.unit}" if param.unit else "")
                editor.valueChanged.connect(lambda v, k=key: self._edit(k, int(v)))
            else:
                editor = ScrubSpin(body)
                editor.setRange(float(param.minimum), float(param.maximum))
                editor.setDecimals(1)
                editor.setSingleStep(float(param.step))
                editor.setSuffix(" °" if param.kind == "angle" else (f" {param.unit}" if param.unit else ""))
                editor.valueChanged.connect(lambda v, k=key: self._edit(k, float(v)))
            row = FieldRow(param.label, editor, body, label_width=LABEL_WIDTH, indent=ROW_INDENT)
            row.setFixedHeight(ROW_H)
            row.setToolTip(param.label)
            bl.addWidget(row)
            self.editors[key] = editor
            self.rows[key] = row
        foot = QWidget(body)
        foot.setFixedHeight(BUTTON_H)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(0, 0, MARGIN_SIDE, 0)
        fl.setSpacing(0)
        fl.addStretch(1)
        self.reset_button = QPushButton("Reset", foot)
        self.reset_button.setFixedHeight(BUTTON_H)
        self.reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.reset_button.clicked.connect(lambda _c=False, t=tool_id: self._reset(t))
        fl.addWidget(self.reset_button)
        bl.addWidget(foot)
        self.body = body
        self._layout.addWidget(body)
        self.updateGeometry()

    def _edit(self, key: str, value) -> None:
        if self.tool_id:
            _tools().set_option(self.tool_id, key, value)

    def _reset(self, tool_id: str) -> None:
        _tools().reset_options(tool_id)
        self.sync()

    def _on_prefs(self, key: str) -> None:
        if key == OPTIONS_KEY:
            self.sync()

    def sync(self) -> None:
        if not self.tool_id:
            return
        values = _tools().options(self.tool_id)
        for key, editor in self.editors.items():
            if key not in values:
                continue
            value = values[key]
            editor.blockSignals(True)
            try:
                if isinstance(editor, QCheckBox):
                    editor.setChecked(bool(value))
                elif isinstance(editor, QComboBox):
                    editor.setCurrentIndex(max(0, editor.findText(str(value))))
                else:
                    editor.setValue(value)
            finally:
                editor.blockSignals(False)


def install(window) -> SelectionToolFilter:
    existing = getattr(window, "selection_filter", None)
    if isinstance(existing, SelectionToolFilter):
        return existing
    viewport = getattr(window, "viewport", None)
    canvas = getattr(viewport, "canvas", viewport)
    filt = SelectionToolFilter(canvas)
    panel = SelectionOptionsPanel(canvas.scene)
    splitter = getattr(window, "manager_splitter", None)
    if splitter is not None:
        options = getattr(window, "tool_options", None)
        at = splitter.indexOf(options) if options is not None else -1
        index = at + 1 if at >= 0 else 1
        splitter.insertWidget(index, panel)
        splitter.setStretchFactor(index, 0)
    else:
        panel.setParent(window)
    panel._on_tool(canvas.scene.tool)
    filt.panel = panel
    window.selection_options = panel
    window.selection_filter = filt
    return filt
