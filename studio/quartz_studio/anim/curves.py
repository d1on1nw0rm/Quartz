from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QContextMenuEvent, QIcon, QKeyEvent, QMouseEvent, QPainter,
                           QPainterPath, QPen, QPixmap, QWheelEvent)
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from .. import theme
from . import core
from .player import AnimContext, get_context
from .timeline import key_menu
from .ui_common import (GAP, MARGIN, EditGroup, channel_color, combo, float_spin, label_frame, nice_step,
                        nice_value_step, panel_qss, record_button, small_font, tool_button)

__all__ = ["CurveEditor", "CurveCanvas"]

RULER_H = 24
AXIS_W = 48
KEY_R = 4
HANDLE_R = 4
HIT = 6
PAD = 24
LIST_W = 192


def _fmt(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v:.0f}"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


class CurveCanvas(QWidget):

    viewChanged = Signal()

    def __init__(self, ctx: AnimContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.scene = ctx.scene
        self.channels: list = []
        self.f0 = -2.0
        self.ppf = 8.0
        self.v0 = -10.0
        self.ppv = 2.0
        self.setMinimumSize(256, 128)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._mode = ""
        self._press = QPointF()
        self._cur = QPointF()
        self._base = None
        self._refs: list = []
        self._handle = None
        self._pan = (0.0, 0.0)
        self._box_mode = "replace"
        self.group = EditGroup(ctx.scene, self)
        for sig in (ctx.frameChanged, ctx.timeChanged, ctx.keysChanged, ctx.keySelectionChanged):
            sig.connect(self.update)

    def set_channels(self, pairs: list) -> None:
        self.channels = [(o, ch) for o, ch in pairs if core.is_scalar_channel(o, ch)]
        self.update()

    def fx(self, f: float) -> float:
        return AXIS_W + (float(f) - self.f0) * self.ppf

    def vy(self, v: float) -> float:
        return self.height() - (float(v) - self.v0) * self.ppv

    def xf(self, x: float) -> float:
        return self.f0 + (float(x) - AXIS_W) / self.ppf

    def yv(self, y: float) -> float:
        return self.v0 + (self.height() - float(y)) / self.ppv

    def frame_all(self, selected_only: bool = False) -> None:
        pairs = self.channels
        frames: list = []
        values: list = []
        if selected_only and self.ctx.selection:
            ids = {(id(o), ch) for o, ch in pairs}
            for o, ch, f in self.ctx.selection:
                if (id(o), ch) not in ids:
                    continue
                i = core.find_key(o, ch, f)
                if i >= 0:
                    frames.append(float(f))
                    values.append(float(core.get_track(o, ch)[i]["value"]))
        if not frames:
            for o, ch in pairs:
                keys = core.get_track(o, ch)
                if not keys:
                    continue
                f0, f1 = float(keys[0]["frame"]), float(keys[-1]["frame"])
                frames += [f0, f1]
                vr = core.value_range(o, ch, f0, f1)
                if vr:
                    values += list(vr)
        if not frames:
            s = self.ctx.settings()
            frames = [float(s["min"]), float(s["max"])]
        if not values:
            values = [-1.0, 1.0]
        lo, hi = min(frames), max(frames)
        if hi - lo < 1:
            lo, hi = lo - 5, hi + 5
        vlo, vhi = min(values), max(values)
        if vhi - vlo < 1e-6:
            pad = max(1.0, abs(vlo) * 0.5)
            vlo, vhi = vlo - pad, vhi + pad
        w = max(64, self.width() - AXIS_W - 2 * PAD)
        h = max(64, self.height() - RULER_H - 2 * PAD)
        self.ppf = max(0.05, w / (hi - lo))
        self.f0 = lo - PAD / self.ppf
        self.ppv = max(1e-6, h / (vhi - vlo))
        self.v0 = vlo - PAD / self.ppv
        self.viewChanged.emit()
        self.update()

    def _keys_screen(self):
        for o, ch in self.channels:
            keys = core.get_track(o, ch)
            for i, k in enumerate(keys):
                yield o, ch, i, k, QPointF(self.fx(k["frame"]), self.vy(k["value"]))

    def _handles(self):
        for o, ch in self.channels:
            keys = core.get_track(o, ch)
            if not keys or not all(core._is_number(k["value"]) for k in keys):
                continue
            slopes = core.auto_slopes([float(k["frame"]) for k in keys], [k["value"] for k in keys])
            for i, k in enumerate(keys):
                if not self.ctx.is_selected(o, ch, k["frame"]):
                    continue
                tin, tout = core.key_tangents(keys, i, slopes)
                kp = QPointF(self.fx(k["frame"]), self.vy(k["value"]))
                if i > 0 and keys[i - 1].get("interp") == "spline":
                    yield o, ch, k, "in", kp, QPointF(self.fx(k["frame"] + tin[0]), self.vy(k["value"] + tin[1]))
                if i < len(keys) - 1 and k.get("interp") == "spline":
                    yield o, ch, k, "out", kp, QPointF(self.fx(k["frame"] + tout[0]), self.vy(k["value"] + tout[1]))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.SURFACE_FIELD))
        p.setFont(small_font(self.font()))
        fstep = nice_step(self.ppf, 48)
        vstep = nice_value_step(self.ppv, 32)
        grid = QPen(QColor(theme.GRID_MINOR), 1)
        p.setPen(grid)
        f = self.f0 - (self.f0 % fstep)
        while self.fx(f) <= w:
            p.drawLine(QPointF(self.fx(f), RULER_H), QPointF(self.fx(f), h))
            f += fstep
        v = self.v0 - (self.v0 % vstep)
        vtop = self.yv(RULER_H)
        while v <= vtop + vstep:
            y = self.vy(v)
            p.setPen(QPen(QColor(theme.HAIRLINE_STRONG if abs(v) < vstep * 1e-6 else theme.GRID_MINOR), 1))
            p.drawLine(QPointF(AXIS_W, y), QPointF(w, y))
            v += vstep
        s = self.ctx.settings()
        cx = self.fx(s["frame"])
        for o, ch in self.channels:
            keys = core.get_track(o, ch)
            if not keys:
                continue
            before, after = core.loop_mode(o, ch)
            color = channel_color(ch)
            fa, fb = float(keys[0]["frame"]), float(keys[-1]["frame"])
            inside = QPainterPath()
            outside_l = QPainterPath()
            outside_r = QPainterPath()
            x = AXIS_W
            while x <= w + 2:
                fr = self.xf(x)
                val = core.evaluate_track(keys, fr, before, after)
                if core._is_number(val):
                    pt = QPointF(x, self.vy(val))
                    path = inside if fa <= fr <= fb else (outside_l if fr < fa else outside_r)
                    if path.elementCount() == 0:
                        path.moveTo(pt)
                    else:
                        path.lineTo(pt)
                x += 2
            for path, dim in ((outside_l, True), (outside_r, True), (inside, False)):
                c = QColor(color)
                if dim:
                    c.setAlpha(110)
                p.setPen(QPen(c, 2, Qt.PenStyle.DashLine if dim else Qt.PenStyle.SolidLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
        for o, ch, k, side, kp, hp in self._handles():
            p.setPen(QPen(QColor(theme.TEXT_SECONDARY), 1))
            p.drawLine(kp, hp)
            p.setBrush(QBrush(QColor(theme.TEXT_PRIMARY)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(hp, HANDLE_R, HANDLE_R)
        for o, ch, i, k, pt in self._keys_screen():
            sel = self.ctx.is_selected(o, ch, k["frame"])
            p.setPen(QPen(channel_color(ch), 2))
            p.setBrush(QBrush(QColor(theme.SELECT_FRONT) if sel else QColor(theme.SURFACE_FIELD)))
            p.drawRect(QRectF(pt.x() - KEY_R, pt.y() - KEY_R, 2 * KEY_R, 2 * KEY_R))
        p.fillRect(QRectF(0, 0, AXIS_W, h), QColor(theme.SURFACE_CARD))
        v = self.v0 - (self.v0 % vstep)
        p.setPen(QColor(theme.TEXT_SECONDARY))
        while v <= vtop + vstep:
            y = self.vy(v)
            if y > RULER_H + MARGIN:
                p.drawText(QRectF(0, y - MARGIN, AXIS_W - GAP, 2 * MARGIN),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _fmt(v))
            v += vstep
        p.fillRect(QRectF(0, 0, w, RULER_H), QColor(theme.SURFACE_CARD))
        f = self.f0 - (self.f0 % fstep)
        while self.fx(f) <= w:
            x = self.fx(f)
            if x >= AXIS_W:
                p.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 1))
                p.drawLine(QPointF(x, RULER_H - MARGIN), QPointF(x, RULER_H))
                p.setPen(QColor(theme.TEXT_SECONDARY))
                p.drawText(QRectF(x + 2, 0, 64, RULER_H - GAP), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           label_frame(self.scene, f, "frames"))
            f += fstep
        p.setPen(QPen(QColor(theme.HAIRLINE), 1))
        p.drawLine(QPointF(0, RULER_H), QPointF(w, RULER_H))
        p.drawLine(QPointF(AXIS_W, 0), QPointF(AXIS_W, h))
        if cx >= AXIS_W:
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawLine(QPointF(cx, 0), QPointF(cx, h))
        if not self.channels:
            p.setPen(QColor(theme.TEXT_MUTED))
            p.drawText(QRectF(AXIS_W, RULER_H, w - AXIS_W, h - RULER_H), Qt.AlignmentFlag.AlignCenter,
                       "No animated channels")
        if self._mode == "box":
            r = QRectF(self._press, self._cur).normalized()
            fill = QColor(theme.ACCENT)
            fill.setAlpha(40)
            p.setPen(QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(fill))
            p.drawRect(r)
        p.end()

    def hit_handle(self, pos: QPointF):
        for o, ch, k, side, kp, hp in self._handles():
            if math.hypot(hp.x() - pos.x(), hp.y() - pos.y()) <= HIT:
                return o, ch, k["frame"], side
        return None

    def hit_key(self, pos: QPointF):
        best, dist = None, HIT + 1
        for o, ch, i, k, pt in self._keys_screen():
            d = max(abs(pt.x() - pos.x()), abs(pt.y() - pos.y()))
            if d < dist:
                best, dist = (o, ch, k["frame"]), d
        return best if dist <= HIT else None

    def _mods_mode(self, mods) -> str:
        if mods & Qt.KeyboardModifier.ControlModifier:
            return "toggle"
        if mods & Qt.KeyboardModifier.ShiftModifier:
            return "add"
        return "replace"

    def mousePressEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        self.setFocus()
        if e.button() == Qt.MouseButton.MiddleButton or (e.button() == Qt.MouseButton.LeftButton and
                                                         e.modifiers() & Qt.KeyboardModifier.AltModifier):
            self._mode = "pan"
            self._press = pos
            self._pan = (self.f0, self.v0)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if pos.y() < RULER_H and pos.x() >= AXIS_W:
            self._mode = "scrub"
            self.ctx.player.stop()
            self._scrub(pos.x())
            return
        h = self.hit_handle(pos)
        if h is not None:
            self._mode = "tangent"
            self._handle = h
            self.group.begin()
            return
        hit = self.hit_key(pos)
        mode = self._mods_mode(e.modifiers())
        if hit is not None:
            if mode == "toggle":
                self.ctx.select([hit], "toggle")
                return
            if mode == "add":
                self.ctx.select([hit], "add")
            elif not self.ctx.is_selected(*hit):
                self.ctx.select([hit], "replace")
            self._mode = "move"
            self._press = pos
            self._refs = list(self.ctx.selection)
            self._base = core.snapshot_tracks({id(r[0]): r[0] for r in self._refs}.values())
            self.group.begin()
            return
        self._mode = "box"
        self._box_mode = mode
        self._press = pos
        self._cur = pos

    def _scrub(self, x: float) -> None:
        s = self.ctx.settings()
        f = min(max(float(round(self.xf(x))), s["min"]), s["max"])
        if f != float(self.ctx.frame):
            self.ctx.set_frame(f)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if self._mode == "pan":
            self.f0 = self._pan[0] - (pos.x() - self._press.x()) / self.ppf
            self.v0 = self._pan[1] + (pos.y() - self._press.y()) / self.ppv
            self.viewChanged.emit()
            self.update()
        elif self._mode == "scrub":
            self._scrub(pos.x())
        elif self._mode == "box":
            self._cur = pos
            self.update()
        elif self._mode == "tangent":
            self.drag_tangent(pos, bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        elif self._mode == "move":
            dx = pos.x() - self._press.x()
            dy = pos.y() - self._press.y()
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if abs(dx) > abs(dy):
                    dy = 0.0
                else:
                    dx = 0.0
            self.drag_keys(int(round(dx / self.ppf)), -dy / self.ppv)

    def drag_keys(self, dframe: int, dvalue: float) -> list:
        if self._base is None:
            self._refs = list(self.ctx.selection)
            self._base = core.snapshot_tracks({id(r[0]): r[0] for r in self._refs}.values())
        with core.edit_group(self.scene):
            core.restore_tracks(self._base)
            refs = core.move_keys(self._refs, dframe) if dframe else core.refs_exist(self._refs)
            if dvalue:
                core.offset_key_values(refs, dvalue)
        self.ctx.select(refs)
        self.ctx.evaluate()
        return refs

    def drag_tangent(self, pos: QPointF, broken: bool) -> None:
        if self._handle is None:
            return
        o, ch, frame, side = self._handle
        i = core.find_key(o, ch, frame)
        if i < 0:
            return
        keys = core.get_track(o, ch)
        k = keys[i]
        dt = self.xf(pos.x()) - float(k["frame"])
        dv = self.yv(pos.y()) - float(k["value"])
        tin, tout = core.key_tangents(keys, i)
        if side == "out":
            dt = max(dt, 1e-3)
            new_out = [dt, dv]
            new_in = None
            if not broken:
                slope = dv / dt
                new_in = [tin[0], tin[0] * slope]
            core.set_tangents(o, ch, frame, new_in, new_out)
        else:
            dt = min(dt, -1e-3)
            new_in = [dt, dv]
            new_out = None
            if not broken:
                slope = dv / dt
                new_out = [tout[0], tout[0] * slope]
            core.set_tangents(o, ch, frame, new_in, new_out)
        self.ctx.evaluate()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._mode == "box":
            self.ctx.select(self.refs_in_rect(QRectF(self._press, e.position()).normalized()), self._box_mode)
        self._mode = ""
        self._base = None
        self._handle = None
        self.group.end()
        self.update()

    def hideEvent(self, e) -> None:
        self._mode = ""
        self._base = None
        self._handle = None
        self.group.end()
        super().hideEvent(e)

    def refs_in_rect(self, r: QRectF) -> list:
        out = []
        for o, ch, i, k, pt in self._keys_screen():
            if r.adjusted(-KEY_R, -KEY_R, KEY_R, KEY_R).contains(pt):
                out.append((o, ch, k["frame"]))
        return out

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if e.button() != Qt.MouseButton.LeftButton or pos.y() < RULER_H or not self.channels:
            return
        f = float(round(self.xf(pos.x())))
        self._mode = ""
        self.group.end()
        best, dist = None, None
        for o, ch in self.channels:
            v = core.evaluate_channel(o, ch, f)
            if not core._is_number(v):
                continue
            d = abs(self.vy(v) - pos.y())
            if dist is None or d < dist:
                best, dist = (o, ch, v), d
        if best is None:
            return
        o, ch, v = best
        core.insert_key(o, ch, f, v, scene=self.scene)
        self.ctx.select([(o, ch, core.get_track(o, ch)[core.find_key(o, ch, f)]["frame"])])
        self.ctx.evaluate()

    def wheelEvent(self, e: QWheelEvent) -> None:
        d = e.angleDelta().y() or e.angleDelta().x()
        if not d:
            return
        factor = 1.25 if d > 0 else 0.8
        mods = e.modifiers()
        pos = e.position()
        af, av = self.xf(pos.x()), self.yv(pos.y())
        if not mods & Qt.KeyboardModifier.ShiftModifier:
            self.ppf = max(0.05, min(256.0, self.ppf * factor))
            self.f0 = af - (pos.x() - AXIS_W) / self.ppf
        if not mods & Qt.KeyboardModifier.ControlModifier:
            self.ppv = max(1e-6, min(1e6, self.ppv * factor))
            self.v0 = av - (self.height() - pos.y()) / self.ppv
        self.viewChanged.emit()
        self.update()
        e.accept()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        k = e.key()
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.ctx.delete_selected()
        elif k == Qt.Key.Key_C and ctrl:
            self.ctx.copy_selected()
        elif k == Qt.Key.Key_V and ctrl:
            self.ctx.paste()
        elif k == Qt.Key.Key_A and ctrl:
            self.ctx.select([(o, ch, kk["frame"]) for o, ch in self.channels for kk in core.get_track(o, ch)])
        elif k == Qt.Key.Key_H:
            self.frame_all()
        elif k == Qt.Key.Key_S and not ctrl:
            self.frame_all(True)
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:
        menu = key_menu(self.ctx, self, float(round(self.xf(e.pos().x()))))
        menu.addSeparator()
        menu.addAction("Frame All", self.frame_all)
        menu.addAction("Frame Selected", lambda: self.frame_all(True))
        menu.exec(e.globalPos())


def _swatch(color: QColor) -> QIcon:
    pm = QPixmap(12, 12)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawRoundedRect(QRectF(2, 2, 8, 8), 2, 2)
    p.end()
    return QIcon(pm)


class CurveEditor(QFrame):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if scene is None:
            from ..scene import get_scene
            scene = get_scene()
        self.scene = scene
        self.ctx = get_context(scene)
        self.active_only = True
        self._pairs: list = []
        self._framed = False
        self.setObjectName("AnimCurveEditor")
        self.setStyleSheet(panel_qss())
        root = QVBoxLayout(self)
        root.setContentsMargins(GAP, GAP, GAP, GAP)
        root.setSpacing(GAP)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(GAP)
        root.addLayout(bar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.list = QListWidget(self.splitter)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(12, 12))
        self.list.setMinimumWidth(128)
        self.canvas = CurveCanvas(self.ctx, self.splitter)
        self.splitter.addWidget(self.list)
        self.splitter.addWidget(self.canvas)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([LIST_W, 640])
        root.addWidget(self.splitter, 1)
        c = self.ctx
        self.btn_frame = tool_button("frame_all", "Frame All", self.canvas.frame_all, parent=self)
        self.btn_frame_sel = tool_button("frame_sel", "Frame Selected", lambda: self.canvas.frame_all(True),
                                         parent=self)
        self.btn_active = tool_button("active", "Show Active Object Only", self._set_active_only, True, self)
        self.btn_key = record_button(c, self)
        self.btn_active.blockSignals(True)
        self.btn_active.setChecked(True)
        self.btn_active.blockSignals(False)
        self.btn_spline = tool_button("spline", "Spline Interpolation", lambda: c.set_interp("spline"), parent=self)
        self.btn_linear = tool_button("linear", "Linear Interpolation", lambda: c.set_interp("linear"), parent=self)
        self.btn_step = tool_button("step", "Step Interpolation", lambda: c.set_interp("step"), parent=self)
        self.btn_ease_in = tool_button("ease_in", "Ease In", lambda: c.set_ease("in"), parent=self)
        self.btn_ease_out = tool_button("ease_out", "Ease Out", lambda: c.set_ease("out"), parent=self)
        self.btn_ease_both = tool_button("ease_both", "Ease In Out", lambda: c.set_ease("both"), parent=self)
        self.btn_auto = tool_button("auto_tan", "Auto Tangents", c.reset_tangents, parent=self)
        self.btn_flat = tool_button("flat_tan", "Flat Tangents", c.flatten_tangents, parent=self)
        self.btn_delete = tool_button("delete", "Delete Selected Keys", c.delete_selected, parent=self)
        loops = (("Constant", "constant"), ("Repeat", "repeat"), ("Offset", "offset"), ("Oscillate", "oscillate"))
        self.before_combo = combo(loops, "Before Track Loop", self)
        self.after_combo = combo(loops, "After Track Loop", self)
        self.before_combo.activated.connect(lambda _i: self._apply_loop("before", self.before_combo.currentData()))
        self.after_combo.activated.connect(lambda _i: self._apply_loop("after", self.after_combo.currentData()))
        self.key_frame = float_spin(-100000, 100000, 0, "Key Frame", 0, self)
        self.key_value = float_spin(-1e9, 1e9, 0, "Key Value", 3, self, 96)
        self.key_frame.valueChanged.connect(self._edit_frame)
        self.key_value.valueChanged.connect(self._edit_value)
        self.key_label = QLabel("Key", self)
        self.key_label.setFont(small_font(self.font()))
        self.key_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        for w in (self.btn_frame, self.btn_frame_sel, self.btn_active, self.btn_key):
            bar.addWidget(w)
        bar.addSpacing(MARGIN)
        for w in (self.btn_spline, self.btn_linear, self.btn_step, self.btn_ease_in, self.btn_ease_out,
                  self.btn_ease_both, self.btn_auto, self.btn_flat, self.btn_delete):
            bar.addWidget(w)
        bar.addSpacing(MARGIN)
        bar.addWidget(self.before_combo)
        bar.addWidget(self.after_combo)
        bar.addSpacing(MARGIN)
        bar.addWidget(self.key_label)
        bar.addWidget(self.key_frame)
        bar.addWidget(self.key_value)
        bar.addStretch(1)
        self.list.itemSelectionChanged.connect(self._on_list)
        c.keysChanged.connect(self._on_keys)
        c.keySelectionChanged.connect(self._sync_key)
        if hasattr(scene, "selectionChanged"):
            scene.selectionChanged.connect(self.rebuild)
        if hasattr(scene, "objectsChanged"):
            scene.objectsChanged.connect(self.rebuild)
        self.rebuild()
        self._sync_key()

    def objects(self) -> list:
        targets = self.ctx.targets()
        if self.active_only:
            return targets
        ids = {id(o) for o in targets}
        return [o for o in self.scene.objects if core.has_animation(o) or id(o) in ids]

    def _set_active_only(self, on: bool) -> None:
        self.active_only = bool(on)
        self.rebuild()

    def rebuild(self, *_a) -> None:
        pairs = []
        for o in self.objects():
            for ch in core.channels_of(o):
                if core.is_scalar_channel(o, ch):
                    pairs.append((o, ch))
        old = [(id(o), ch) for o, ch in self.selected_pairs()] if self._pairs else []
        if [(id(o), ch) for o, ch in pairs] != [(id(o), ch) for o, ch in self._pairs]:
            self.list.blockSignals(True)
            self.list.clear()
            for o, ch in pairs:
                item = QListWidgetItem(_swatch(channel_color(ch)), f"{o.name}  {core.channel_label(ch, o)}")
                self.list.addItem(item)
                if (id(o), ch) in old:
                    item.setSelected(True)
            self.list.blockSignals(False)
            self._pairs = pairs
        self._on_list()
        if pairs and not self._framed and self.canvas.width() > 0:
            self._framed = True
            self.canvas.frame_all()

    def selected_pairs(self) -> list:
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        return [self._pairs[r] for r in rows if 0 <= r < len(self._pairs)]

    def shown_pairs(self) -> list:
        return self.selected_pairs() or list(self._pairs)

    def _on_list(self) -> None:
        self.canvas.set_channels(self.shown_pairs())
        pairs = self.shown_pairs()
        if pairs:
            b, a = core.loop_mode(*pairs[0])
            for cmb, v in ((self.before_combo, b), (self.after_combo, a)):
                cmb.blockSignals(True)
                cmb.setCurrentIndex(max(0, cmb.findData(v)))
                cmb.blockSignals(False)

    def _on_keys(self) -> None:
        self.rebuild()
        self._sync_key()

    def _apply_loop(self, side: str, mode: str) -> int:
        pairs = self.ctx.selected_channels() or self.shown_pairs()
        return self.ctx.set_loop(**{side: mode}, channels=pairs)

    def _single(self):
        sel = [r for r in self.ctx.selection if core.is_scalar_channel(r[0], r[1])]
        return sel[0] if len(sel) == 1 else None

    def _sync_key(self) -> None:
        ref = self._single()
        has = bool(self.ctx.selection)
        for b in (self.btn_spline, self.btn_linear, self.btn_step, self.btn_ease_in, self.btn_ease_out,
                  self.btn_ease_both, self.btn_auto, self.btn_flat, self.btn_delete):
            b.setEnabled(has)
        self.key_frame.setEnabled(ref is not None)
        self.key_value.setEnabled(ref is not None)
        if ref is None:
            return
        o, ch, f = ref
        i = core.find_key(o, ch, f)
        if i < 0:
            return
        k = core.get_track(o, ch)[i]
        for spin, v in ((self.key_frame, float(k["frame"])), (self.key_value, float(k["value"]))):
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)

    def _edit_frame(self, v: float) -> None:
        ref = self._single()
        if ref is None:
            return
        d = round(v) - float(ref[2])
        if d:
            self.ctx.move_selected(d)

    def _edit_value(self, v: float) -> None:
        ref = self._single()
        if ref is None:
            return
        core.set_key_value(ref[0], ref[1], ref[2], float(v))
        self.ctx.evaluate()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self._pairs and not self._framed:
            self._framed = True
            self.canvas.frame_all()
