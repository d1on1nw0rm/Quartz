from __future__ import annotations

import time

import numpy as np
from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import theme
from . import data
from .session import get_session
from .stroke import SculptStroke, oriented_topology

__all__ = ["BrushOverlay", "ViewportSculptController", "attach_viewport", "MASK_DOT_LIMIT"]

MASK_DOT_LIMIT = 200000
MASK_DOT = 4
RING_W = 2
INNER_W = 2
CENTER_DOT = 2
LAZY_DOT = 4
TABLET_HOLD = 0.25
RADIUS_STEP = 1.2
MASK_THROTTLE = 0.06
ADJUST_STRENGTH_PX = 256.0


def _xy(pos) -> tuple[float, float]:
    if hasattr(pos, "x") and callable(pos.x):
        return float(pos.x()), float(pos.y())
    return float(pos[0]), float(pos[1])


def _premultiplied(color: QColor, alpha: np.ndarray) -> np.ndarray:
    a = np.clip(alpha, 0, 255).astype(np.uint32)
    r = (a * color.red() // 255).astype(np.uint32)
    g = (a * color.green() // 255).astype(np.uint32)
    b = (a * color.blue() // 255).astype(np.uint32)
    return (a << 24) | (r << 16) | (g << 8) | b


class BrushOverlay(QWidget):

    def __init__(self, canvas: QWidget, controller: "ViewportSculptController") -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.controller = controller
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pos_xy: tuple[float, float] | None = None
        self.lazy_xy: tuple[float, float] | None = None
        self.mods = Qt.KeyboardModifier.NoModifier
        self._mask_key = None
        self._mask_image: QImage | None = None
        self._mask_time = 0.0
        self.mask_builds = 0
        self.setGeometry(canvas.rect())

    def ring_color(self) -> QColor:
        s = self.controller.session
        if self.mods & Qt.KeyboardModifier.ShiftModifier:
            return QColor(theme.TINT_AMETHYST)
        invert = s.settings().invert != bool(self.mods & Qt.KeyboardModifier.ControlModifier)
        if s.brush == "mask":
            return QColor(theme.TINT_CITRINE)
        return QColor(theme.TINT_ROSE if invert else theme.ACCENT)

    def _camera_key(self):
        project = getattr(self.canvas, "project_world", None)
        if project is None:
            return None
        try:
            ref = np.asarray(project(np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0],
                                               [0.0, 100.0, 0.0], [0.0, 0.0, 100.0]])), float)
        except Exception:
            return None
        return tuple(np.round(ref.reshape(-1), 3).tolist())

    def mask_points(self) -> tuple[np.ndarray, np.ndarray] | None:
        s = self.controller.session
        if not s.show_mask:
            return None
        obj = s.target()
        state = data.get_state(obj) if obj is not None else None
        if state is None:
            return None
        stroke = self.controller.stroke
        if stroke is not None and stroke.obj is obj and stroke.valid:
            mask = stroke.mask
            world = stroke.W
        else:
            mask = data.get_mask(state, len(obj.mesh.points))
            world = None
        sel = np.nonzero(mask > 0.02)[0]
        if not len(sel):
            return None
        if len(sel) > MASK_DOT_LIMIT:
            sel = sel[np.linspace(0, len(sel) - 1, MASK_DOT_LIMIT).astype(int)]
        project = getattr(self.canvas, "project_world", None)
        if project is None:
            return None
        if world is None:
            world = obj.world_points()
        view = getattr(self.canvas, "view_direction", None)
        topo = data.topology(state)
        if view is not None and topo.n == len(world):
            topo = oriented_topology(topo, data.orientation(obj))
            normals = topo.vertex_normals(world, sel)
            sel = sel[normals @ np.asarray(view(), float) < 0.05]
            if not len(sel):
                return None
        try:
            xy = np.asarray(project(world[sel]), float)
        except Exception:
            return None
        return xy, mask[sel]

    def mask_image(self) -> QImage | None:
        s = self.controller.session
        obj = s.target()
        if not s.show_mask or obj is None:
            self._mask_key = None
            self._mask_image = None
            return None
        stroke = self.controller.stroke
        extras = getattr(obj, "extras", {}) or {}
        key = (id(obj), id(obj.mesh), id(obj.mesh.points), id(extras.get(data.KEY)),
               None if stroke is None else (id(stroke), stroke.dabs),
               self._camera_key(), self.width(), self.height(),
               tuple(np.round(obj.world_matrix().reshape(-1), 6).tolist()))
        if key == self._mask_key:
            return self._mask_image
        now = time.monotonic()
        if (stroke is not None and self._mask_key is not None and self._mask_key[:2] == key[:2]
                and key[5:] == self._mask_key[5:] and now - self._mask_time < MASK_THROTTLE):
            return self._mask_image
        self._mask_key = key
        self._mask_time = now
        self._mask_image = self._build_mask_image()
        self.mask_builds += 1
        return self._mask_image

    def _build_mask_image(self) -> QImage | None:
        dots = self.mask_points()
        w, h = max(1, self.width()), max(1, self.height())
        if dots is None:
            return None
        xy, values = dots
        ok = np.all(np.isfinite(xy), axis=1)
        xy, values = xy[ok], values[ok]
        if not len(xy):
            return None
        buf = np.zeros((h, w), np.uint32)
        base = QColor(theme.TINT_CITRINE)
        colors = _premultiplied(base, 60 + 160 * values)
        cx = np.floor(xy[:, 0]).astype(np.int64)
        cy = np.floor(xy[:, 1]).astype(np.int64)
        half = MASK_DOT // 2
        order = np.argsort(values, kind="stable")
        cx, cy, colors = cx[order], cy[order], colors[order]
        for dy in range(-half, MASK_DOT - half):
            for dx in range(-half, MASK_DOT - half):
                if (dx + 0.5) ** 2 + (dy + 0.5) ** 2 > (MASK_DOT / 2.0) ** 2:
                    continue
                x = cx + dx
                y = cy + dy
                inside = (x >= 0) & (x < w) & (y >= 0) & (y < h)
                buf[y[inside], x[inside]] = colors[inside]
        img = QImage(buf.data, w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        return img

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        img = self.mask_image()
        if img is not None:
            p.drawImage(0, 0, img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ctl = self.controller
        center = ctl.adjust_anchor() or self.lazy_xy or self.pos_xy
        if center is not None:
            x, y = center
            r = float(ctl.session.settings().radius)
            color = self.ring_color()
            p.setBrush(Qt.BrushStyle.NoBrush)
            shadow = QColor(theme.SURFACE_PRESSED)
            shadow.setAlpha(160)
            p.setPen(QPen(shadow, RING_W + 2))
            p.drawEllipse(QPointF(x, y), r, r)
            p.setPen(QPen(color, RING_W))
            p.drawEllipse(QPointF(x, y), r, r)
            inner = QColor(color)
            inner.setAlpha(110)
            p.setPen(QPen(inner, INNER_W))
            s = float(ctl.session.settings().strength)
            p.drawEllipse(QPointF(x, y), r * max(0.05, s), r * max(0.05, s))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(x, y), CENTER_DOT, CENTER_DOT)
            if self.lazy_xy is not None and self.pos_xy is not None and ctl.adjust_anchor() is None:
                faint = QColor(color)
                faint.setAlpha(140)
                p.setPen(QPen(faint, RING_W, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(*self.lazy_xy), QPointF(*self.pos_xy))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(faint)
                p.drawEllipse(QPointF(*self.pos_xy), LAZY_DOT / 2, LAZY_DOT / 2)
        p.end()


class ViewportSculptController(QObject):

    def __init__(self, canvas: QWidget, scene=None, parent: QObject | None = None) -> None:
        super().__init__(parent if parent is not None else canvas)
        if scene is None:
            scene = getattr(canvas, "scene", None)
            if scene is None or not hasattr(scene, "objects"):
                from ..scene import get_scene
                scene = get_scene()
        self.canvas = canvas
        self.scene = scene
        self.session = get_session(scene)
        self.overlay = BrushOverlay(canvas, self)
        self.overlay.setVisible(self.session.active)
        self.stroke: SculptStroke | None = None
        self._pending = False
        self._pending_mods = Qt.KeyboardModifier.NoModifier
        self._grab_plane: tuple[np.ndarray, np.ndarray] | None = None
        self._pressure = 1.0
        self._pressure_time = 0.0
        self._lazy: tuple[float, float] | None = None
        self._adjust: dict | None = None
        self._tracking = bool(canvas.hasMouseTracking())
        if self.session.active:
            canvas.setMouseTracking(True)
        canvas.installEventFilter(self)
        self.session.activeChanged.connect(self._on_active)
        self.session.settingsChanged.connect(self.overlay.update)
        changed = getattr(scene, "changed", None)
        if changed is not None:
            changed.connect(self._on_scene_changed)

    @property
    def active(self) -> bool:
        return bool(self.session.active)

    def adjust_anchor(self) -> tuple[float, float] | None:
        return None if self._adjust is None else self._adjust["anchor"]

    def _on_active(self, flag: bool) -> None:
        if not flag:
            self.finish_stroke()
            self.cancel_adjust()
        try:
            self.canvas.setMouseTracking(True if flag else self._tracking)
        except RuntimeError:
            pass
        self.overlay.setVisible(bool(flag))
        self.overlay.raise_()
        self.overlay.update()
        try:
            self.canvas.setCursor(Qt.CursorShape.CrossCursor if flag else Qt.CursorShape.ArrowCursor)
        except Exception:
            pass

    def _on_scene_changed(self) -> None:
        if self.session.active and self.session.show_mask:
            self.overlay.update()

    def detach(self) -> None:
        self.finish_stroke()
        self.cancel_adjust()
        self.canvas.removeEventFilter(self)
        self.canvas.setMouseTracking(self._tracking)
        self.overlay.hide()
        self.overlay.deleteLater()

    def pressure(self) -> float:
        if time.monotonic() - self._pressure_time <= TABLET_HOLD:
            return self._pressure
        return 1.0

    def _ray(self, pos) -> tuple[np.ndarray, np.ndarray]:
        o, d = self.canvas.ray_at(QPointF(*_xy(pos)))
        return np.asarray(o, float), np.asarray(d, float)

    def _view_dir(self, d: np.ndarray) -> np.ndarray:
        n = float(np.linalg.norm(d))
        return d / n if n > 1e-12 else np.asarray(self.canvas.view_direction(), float)

    def world_radius(self, point: np.ndarray) -> float:
        depth = float(np.asarray(self.canvas.camera.depth(np.asarray(point, float).reshape(1, 3))).reshape(-1)[0])
        return float(self.session.settings().radius) * float(self.canvas.px_size(depth))

    def _pick(self, pos):
        hit = self.canvas.hit_at(QPointF(*_xy(pos)))
        if hit is None:
            return None
        obj = hit[0]
        if not data.can_sculpt(obj):
            return None
        return hit

    def _surface_hit(self, pos):
        if self.stroke is None:
            return None
        o, d = self._ray(pos)
        res = self.stroke.raycast(o, d)
        if res is None:
            return None
        face, point, _t = res
        return point, self.stroke.surface_normal(face), self._view_dir(d)

    def begin_stroke(self, pos, mods=Qt.KeyboardModifier.NoModifier) -> bool:
        self._lazy = _xy(pos)
        hit = self._pick(pos)
        if hit is None:
            target = self.session.target()
            if target is None:
                return False
            self._pending = True
            self._pending_mods = mods
            return True
        obj, _k, point, _t = hit
        if obj is not getattr(self.scene, "active", None):
            self.session.switch_target(obj)
        return self._start(obj, np.asarray(point, float), pos, mods)

    def _start(self, obj, point: np.ndarray, pos, mods) -> bool:
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        settings = self.session.settings()
        stroke = SculptStroke(obj, settings, self.scene, smooth=shift,
                              invert=settings.invert != ctrl)
        if not stroke.valid:
            return False
        self.stroke = stroke
        self._pending = False
        self._lazy = _xy(pos)
        o, d = self._ray(pos)
        view = self._view_dir(d)
        self._grab_plane = (point.copy(), view.copy())
        res = stroke.raycast(o, d)
        if res is not None:
            face, p2, _t = res
            point = p2
            normal = stroke.surface_normal(face)
        else:
            normal = -view
        stroke.dab(point, normal, view, self.pressure(), self.world_radius(point))
        return True

    def _stabilized(self, pos):
        lazy_r = float(self.session.settings().stabilize)
        x, y = _xy(pos)
        if lazy_r <= 0.0 or self._lazy is None or (self.stroke is not None and self.stroke.brush.kind == "grab"):
            self._lazy = (x, y)
            self.overlay.lazy_xy = None
            return QPointF(x, y)
        lx, ly = self._lazy
        dx, dy = x - lx, y - ly
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= lazy_r:
            self.overlay.lazy_xy = self._lazy
            return None
        k = (dist - lazy_r) / dist
        self._lazy = (lx + dx * k, ly + dy * k)
        self.overlay.lazy_xy = self._lazy
        return QPointF(*self._lazy)

    def drag_stroke(self, pos) -> int:
        if self.stroke is None:
            if self._pending:
                target = self.session.target()
                if target is None:
                    return 0
                o, d = self._ray(pos)
                st = data.ensure_state(target)
                if st is None:
                    return 0
                topo = data.topology(st)
                world = target.world_points()
                res = topo.raycast(world, o, d)
                if res is None:
                    return 0
                self._start(target, res[1], pos, self._pending_mods)
            return 0
        if self.stroke.finished:
            self.stroke = None
            return 0
        if self.stroke.brush.kind == "grab":
            o, d = self._ray(pos)
            origin, normal = self._grab_plane
            denom = float(d @ normal)
            if abs(denom) < 1e-9:
                return 0
            point = o + d * (float((origin - o) @ normal) / denom)
            return self.stroke.dab(point, None, self._view_dir(d), self.pressure(),
                                   self.world_radius(origin))
        lazy = self._stabilized(pos)
        if lazy is None:
            return 0
        hit = self._surface_hit(lazy)
        if hit is None:
            return 0
        point, normal, view = hit
        return self.stroke.dab(point, normal, view, self.pressure(), self.world_radius(point))

    def finish_stroke(self) -> bool:
        self._pending = False
        self._lazy = None
        self.overlay.lazy_xy = None
        stroke, self.stroke = self.stroke, None
        if stroke is None:
            return False
        ok = stroke.end()
        self.session.notify_data()
        self.overlay.update()
        return ok

    def cancel_stroke(self) -> None:
        self._pending = False
        self._lazy = None
        self.overlay.lazy_xy = None
        stroke, self.stroke = self.stroke, None
        if stroke is not None:
            stroke.cancel()
        self.overlay.update()

    def begin_adjust(self, kind: str, pos=None) -> bool:
        if self.stroke is not None or kind not in ("radius", "strength"):
            return False
        anchor = _xy(pos) if pos is not None else self.overlay.pos_xy
        if anchor is None:
            anchor = (self.canvas.width() / 2.0, self.canvas.height() / 2.0)
        s = self.session.settings()
        start = float(s.radius if kind == "radius" else s.strength)
        self._adjust = {"kind": kind, "anchor": anchor, "start": start, "x": anchor[0]}
        self.overlay.update()
        return True

    def update_adjust(self, pos) -> None:
        if self._adjust is None:
            return
        a = self._adjust
        x, y = _xy(pos)
        if a["kind"] == "radius":
            ax, ay = a["anchor"]
            value = max(1.0, ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5)
            self.session.set("radius", value)
        else:
            value = a["start"] + (x - a["x"]) / ADJUST_STRENGTH_PX
            self.session.set("strength", min(1.0, max(0.0, value)))
        self.overlay.update()

    def confirm_adjust(self) -> None:
        self._adjust = None
        self.overlay.update()

    def cancel_adjust(self) -> None:
        a, self._adjust = self._adjust, None
        if a is not None:
            self.session.set(a["kind"], a["start"])
        self.overlay.update()

    def _hover(self, pos, mods) -> None:
        self.overlay.pos_xy = _xy(pos)
        self.overlay.mods = mods
        self.overlay.update()

    def eventFilter(self, obj, ev) -> bool:
        if obj is not self.canvas:
            return False
        t = ev.type()
        if t == QEvent.Type.Resize:
            self.overlay.setGeometry(self.canvas.rect())
            return False
        if not self.session.active:
            return False
        if t in (QEvent.Type.TabletPress, QEvent.Type.TabletMove, QEvent.Type.TabletRelease):
            self._pressure = float(ev.pressure())
            self._pressure_time = time.monotonic()
            return False
        if t == QEvent.Type.Leave:
            self.overlay.pos_xy = None
            self.overlay.update()
            return False
        if self._adjust is not None:
            if t == QEvent.Type.MouseMove:
                self._hover(ev.position(), ev.modifiers())
                self.update_adjust(ev.position())
                return True
            if t == QEvent.Type.MouseButtonPress:
                if ev.button() == Qt.MouseButton.LeftButton:
                    self.confirm_adjust()
                else:
                    self.cancel_adjust()
                return True
            if t in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
                return True
            if t == QEvent.Type.KeyPress:
                if ev.key() == Qt.Key.Key_Escape:
                    self.cancel_adjust()
                elif ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F):
                    self.confirm_adjust()
                return True
        if t == QEvent.Type.MouseButtonPress:
            mods = ev.modifiers()
            if ev.button() != Qt.MouseButton.LeftButton or mods & Qt.KeyboardModifier.AltModifier:
                return False
            self._hover(ev.position(), mods)
            self.begin_stroke(ev.position(), mods)
            return True
        if t == QEvent.Type.MouseMove:
            self._hover(ev.position(), ev.modifiers())
            if self.stroke is not None or self._pending:
                self.drag_stroke(ev.position())
                return True
            return False
        if t == QEvent.Type.MouseButtonRelease:
            if ev.button() == Qt.MouseButton.LeftButton and (self.stroke is not None or self._pending):
                self.finish_stroke()
                return True
            return False
        if t == QEvent.Type.MouseButtonDblClick:
            return ev.button() == Qt.MouseButton.LeftButton and not (
                ev.modifiers() & Qt.KeyboardModifier.AltModifier)
        if t == QEvent.Type.KeyPress:
            key = ev.key()
            if key == Qt.Key.Key_BracketLeft:
                self.session.scale_radius(1.0 / RADIUS_STEP)
                self.overlay.update()
                return True
            if key == Qt.Key.Key_BracketRight:
                self.session.scale_radius(RADIUS_STEP)
                self.overlay.update()
                return True
            if key == Qt.Key.Key_F and not ev.isAutoRepeat() and self.stroke is None:
                shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                return self.begin_adjust("strength" if shift else "radius")
            if key == Qt.Key.Key_Escape and self.stroke is not None:
                self.cancel_stroke()
                return True
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift):
                self.overlay.mods = ev.modifiers()
                self.overlay.update()
            return False
        if t == QEvent.Type.KeyRelease:
            if ev.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift):
                self.overlay.mods = ev.modifiers()
                self.overlay.update()
            return False
        return False


def attach_viewport(canvas: QWidget, scene=None) -> ViewportSculptController:
    existing = getattr(canvas, "_qs_sculpt_controller", None)
    if isinstance(existing, ViewportSculptController):
        return existing
    controller = ViewportSculptController(canvas, scene)
    try:
        canvas._qs_sculpt_controller = controller
    except AttributeError:
        pass
    return controller
