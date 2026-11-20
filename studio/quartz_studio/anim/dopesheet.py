from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QContextMenuEvent, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from .. import theme
from . import core
from .player import AnimContext, get_context
from .timeline import key_menu
from .ui_common import (GAP, MARGIN, channel_color, diamond, float_spin, label_frame, nice_step, panel_qss,
                        record_button, small_font, tool_button)

__all__ = ["DopeSheet", "DopeCanvas"]

NAME_W = 192
HEADER_H = 24
ROW_H = 24
INDENT = 16
TRI_W = 24
KEY_R = 6
HIT = 6
PAD = 24


class DopeCanvas(QWidget):

    def __init__(self, ctx: AnimContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.scene = ctx.scene
        self.active_only = False
        self.expanded: dict = {}
        self.f0 = -2.0
        self.ppf = 8.0
        self.scroll = 0
        self.setMinimumSize(384, 128)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._mode = ""
        self._press = QPointF()
        self._cur = QPointF()
        self._drag_refs: list = []
        self._drag_base = None
        self._drag_delta = 0
        self._pan_origin = (0.0, 0)
        self._box_mode = "replace"
        for sig in (ctx.frameChanged, ctx.timeChanged, ctx.keysChanged, ctx.keySelectionChanged):
            sig.connect(self.update)
        if hasattr(self.scene, "selectionChanged"):
            self.scene.selectionChanged.connect(self.update)
        if hasattr(self.scene, "objectsChanged"):
            self.scene.objectsChanged.connect(self.update)

    def objects(self) -> list:
        targets = self.ctx.targets()
        if self.active_only:
            return targets
        ids = {id(o) for o in targets}
        return [o for o in self.scene.objects if core.has_animation(o) or id(o) in ids]

    def rows(self) -> list:
        out = []
        for obj in self.objects():
            out.append(("object", obj, None))
            if self.expanded.get(id(obj), True):
                for ch in core.channels_of(obj):
                    out.append(("channel", obj, ch))
        return out

    def frame_to_x(self, f: float) -> float:
        return NAME_W + (float(f) - self.f0) * self.ppf

    def x_to_frame(self, x: float) -> float:
        return self.f0 + (float(x) - NAME_W) / self.ppf

    def row_y(self, i: int) -> float:
        return HEADER_H + i * ROW_H - self.scroll

    def row_at(self, y: float) -> int:
        if y < HEADER_H:
            return -1
        i = int((y - HEADER_H + self.scroll) // ROW_H)
        return i if 0 <= i < len(self.rows()) else -1

    def row_frames(self, row) -> list:
        kind, obj, ch = row
        if kind == "object":
            return core.key_frames(obj)
        return [k["frame"] for k in core.get_track(obj, ch)]

    def row_refs(self, row, frame: float) -> list:
        kind, obj, ch = row
        if kind == "object":
            return core.refs_at_frame(obj, frame)
        i = core.find_key(obj, ch, frame)
        return [(obj, ch, core.get_track(obj, ch)[i]["frame"])] if i >= 0 else []

    def row_selected(self, row, frame: float) -> bool:
        kind, obj, ch = row
        if kind == "channel":
            return self.ctx.is_selected(obj, ch, frame)
        return self.ctx.is_frame_selected(obj, frame)

    def hit_key(self, pos: QPointF):
        i = self.row_at(pos.y())
        if i < 0 or pos.x() < NAME_W:
            return None
        row = self.rows()[i]
        best, dist = None, HIT + 1
        for f in self.row_frames(row):
            d = abs(self.frame_to_x(f) - pos.x())
            if d < dist:
                best, dist = f, d
        return (row, best) if best is not None and dist <= HIT else None

    def frame_all(self) -> None:
        objs = self.objects()
        rng = core.key_range(objs) if objs else None
        if rng is None:
            s = self.ctx.settings()
            rng = (float(s["min"]), float(s["max"]))
        lo, hi = rng
        if hi - lo < 1:
            lo, hi = lo - 5, hi + 5
        avail = max(64, self.width() - NAME_W - 2 * PAD)
        self.ppf = max(0.5, min(64.0, avail / (hi - lo)))
        self.f0 = lo - PAD / self.ppf
        self.scroll = 0
        self.update()

    def set_expanded_all(self, flag: bool) -> None:
        for obj in self.objects():
            self.expanded[id(obj)] = flag
        self.update()

    def _clamp_scroll(self) -> None:
        total = len(self.rows()) * ROW_H
        view = max(0, self.height() - HEADER_H)
        self.scroll = int(max(0, min(self.scroll, max(0, total - view))))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.SURFACE_CARD))
        s = self.ctx.settings()
        rows = self.rows()
        p.setFont(small_font(self.font()))
        p.save()
        p.setClipRect(QRectF(0, HEADER_H, w, h - HEADER_H))
        active = getattr(self.scene, "active", None)
        for i, row in enumerate(rows):
            y = self.row_y(i)
            if y + ROW_H < HEADER_H or y > h:
                continue
            kind, obj, ch = row
            band = QColor(theme.SURFACE_FIELD if i % 2 == 0 else theme.SURFACE_CARD)
            if kind == "object":
                band = QColor(theme.SURFACE_RAISED)
            p.fillRect(QRectF(0, y, w, ROW_H), band)
        x0, x1 = self.frame_to_x(s["preview_min"]), self.frame_to_x(s["preview_max"])
        shade = QColor(theme.SURFACE_PRESSED)
        shade.setAlpha(120)
        p.fillRect(QRectF(NAME_W, HEADER_H, max(0, x0 - NAME_W), h), shade)
        p.fillRect(QRectF(max(NAME_W, x1), HEADER_H, w, h), shade)
        step = nice_step(self.ppf, 48)
        p.setPen(QPen(QColor(theme.HAIRLINE), 1))
        f = self.f0 - (self.f0 % step)
        while self.frame_to_x(f) <= w:
            x = self.frame_to_x(f)
            if x >= NAME_W:
                p.drawLine(QPointF(x, HEADER_H), QPointF(x, h))
            f += step
        delta = self._drag_delta if self._mode == "drag" else 0
        for i, row in enumerate(rows):
            y = self.row_y(i)
            if y + ROW_H < HEADER_H or y > h:
                continue
            kind, obj, ch = row
            cy = y + ROW_H / 2
            frames = self.row_frames(row)
            color = QColor(theme.TEXT_SECONDARY) if kind == "object" else channel_color(ch)
            if kind == "channel" and len(frames) > 1:
                p.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 2))
                p.drawLine(QPointF(max(NAME_W, self.frame_to_x(frames[0])), cy),
                           QPointF(max(NAME_W, self.frame_to_x(frames[-1])), cy))
            for fr in frames:
                sel = self.row_selected(row, fr)
                x = self.frame_to_x(fr + (delta if sel else 0))
                if x < NAME_W - KEY_R or x > w + KEY_R:
                    continue
                p.setPen(QPen(QColor(theme.SURFACE_PRESSED), 1))
                p.setBrush(QBrush(QColor(theme.SELECT_FRONT) if sel else color))
                r = KEY_R if kind == "object" else KEY_R - 2
                p.drawPolygon(diamond(x, cy, r))
            p.fillRect(QRectF(0, y, NAME_W, ROW_H), QColor(theme.SURFACE_RAISED if kind == "object"
                                                         else theme.SURFACE_CARD))
            if kind == "object":
                tri = "-" if self.expanded.get(id(obj), True) else "+"
                p.setPen(QColor(theme.TEXT_SECONDARY))
                p.drawText(QRectF(GAP, y, TRI_W - GAP, ROW_H), Qt.AlignmentFlag.AlignCenter, tri)
                p.setPen(QColor(theme.ACCENT if obj is active else theme.TEXT_PRIMARY))
                p.setFont(small_font(self.font(), bold=True))
                p.drawText(QRectF(TRI_W, y, NAME_W - TRI_W - GAP, ROW_H),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, obj.name)
                p.setFont(small_font(self.font()))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(channel_color(ch)))
                p.drawRect(QRectF(TRI_W, y + MARGIN, GAP, MARGIN))
                p.setPen(QColor(theme.TEXT_SECONDARY))
                p.drawText(QRectF(TRI_W + INDENT, y, NAME_W - TRI_W - INDENT, ROW_H),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, core.channel_label(ch, obj))
        p.restore()
        p.fillRect(QRectF(0, 0, w, HEADER_H), QColor(theme.SURFACE_FIELD))
        f = self.f0 - (self.f0 % step)
        while self.frame_to_x(f) <= w:
            x = self.frame_to_x(f)
            if x >= NAME_W:
                p.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 1))
                p.drawLine(QPointF(x, HEADER_H - MARGIN), QPointF(x, HEADER_H))
                p.setPen(QColor(theme.TEXT_SECONDARY))
                p.drawText(QRectF(x + 2, 0, 64, HEADER_H - GAP),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label_frame(self.scene, f, "frames"))
            f += step
        p.setPen(QColor(theme.TEXT_MUTED))
        p.drawText(QRectF(MARGIN, 0, NAME_W - MARGIN, HEADER_H), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "Objects / Tracks")
        p.setPen(QPen(QColor(theme.HAIRLINE), 1))
        p.drawLine(QPointF(0, HEADER_H), QPointF(w, HEADER_H))
        p.drawLine(QPointF(NAME_W, 0), QPointF(NAME_W, h))
        cx = self.frame_to_x(s["frame"])
        if cx >= NAME_W:
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawLine(QPointF(cx, 0), QPointF(cx, h))
        if self._mode == "box":
            r = QRectF(self._press, self._cur).normalized()
            fill = QColor(theme.ACCENT)
            fill.setAlpha(40)
            p.setPen(QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(fill))
            p.drawRect(r)
        p.end()

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
            self._pan_origin = (self.f0, self.scroll)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        mode = self._mods_mode(e.modifiers())
        if pos.y() < HEADER_H and pos.x() >= NAME_W:
            self._mode = "scrub"
            self.ctx.player.stop()
            self._scrub(pos.x())
            return
        i = self.row_at(pos.y())
        if pos.x() < NAME_W:
            if i < 0:
                return
            kind, obj, ch = self.rows()[i]
            if kind == "object":
                if pos.x() < TRI_W:
                    self.expanded[id(obj)] = not self.expanded.get(id(obj), True)
                    self._clamp_scroll()
                    self.update()
                else:
                    if obj in self.scene.objects and hasattr(self.scene, "set_active"):
                        self.scene.set_active(obj)
                    self.ctx.select(core.all_refs(obj), mode)
            else:
                self.ctx.select(core.all_refs(obj, [ch]), mode)
            return
        hit = self.hit_key(pos)
        if hit is not None:
            row, f = hit
            refs = self.row_refs(row, f)
            if mode == "toggle":
                self.ctx.select(refs, "toggle")
                return
            if mode == "add":
                self.ctx.select(refs, "add")
            elif not all(self.ctx.is_selected(*r) for r in refs):
                self.ctx.select(refs, "replace")
            self._mode = "drag"
            self._press = pos
            self._drag_refs = list(self.ctx.selection)
            self._drag_delta = 0
            return
        self._mode = "box"
        self._box_mode = mode
        self._press = pos
        self._cur = pos

    def _scrub(self, x: float) -> None:
        f = float(round(self.x_to_frame(x)))
        s = self.ctx.settings()
        f = min(max(f, s["min"]), s["max"])
        if f != float(self.ctx.frame):
            self.ctx.set_frame(f)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if self._mode == "pan":
            self.f0 = self._pan_origin[0] - (pos.x() - self._press.x()) / self.ppf
            self.scroll = int(self._pan_origin[1] - (pos.y() - self._press.y()))
            self._clamp_scroll()
            self.update()
        elif self._mode == "scrub":
            self._scrub(pos.x())
        elif self._mode == "drag":
            d = int(round((pos.x() - self._press.x()) / self.ppf))
            if d != self._drag_delta:
                self._drag_delta = d
                self.update()
        elif self._mode == "box":
            self._cur = pos
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._mode == "drag" and self._drag_delta:
            with core.edit_group(self.scene):
                refs = core.move_keys(self._drag_refs, self._drag_delta)
            self.ctx.select(refs)
            self.ctx.evaluate()
        elif self._mode == "box":
            self.ctx.select(self.refs_in_rect(QRectF(self._press, e.position()).normalized()), self._box_mode)
        self._mode = ""
        self._drag_delta = 0
        self.update()

    def refs_in_rect(self, r: QRectF) -> list:
        out = []
        for i, row in enumerate(self.rows()):
            y = self.row_y(i) + ROW_H / 2
            if not r.top() - KEY_R <= y <= r.bottom() + KEY_R:
                continue
            for f in self.row_frames(row):
                x = self.frame_to_x(f)
                if r.left() - KEY_R <= x <= r.right() + KEY_R:
                    for ref in self.row_refs(row, f):
                        if ref not in out:
                            out.append(ref)
        return out

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if e.button() != Qt.MouseButton.LeftButton or pos.x() < NAME_W:
            return
        i = self.row_at(pos.y())
        if i < 0:
            return
        kind, obj, ch = self.rows()[i]
        f = float(round(self.x_to_frame(pos.x())))
        self._mode = ""
        with core.edit_group(self.scene):
            self._insert_at(kind, obj, ch, f)
        self.ctx.evaluate()

    def _insert_at(self, kind: str, obj, ch, f: float) -> None:
        if kind == "channel":
            v = core.evaluate_channel(obj, ch, f)
            core.insert_key(obj, ch, f, v, scene=self.scene)
            self.ctx.select([(obj, ch, core.get_track(obj, ch)[core.find_key(obj, ch, f)]["frame"])])
        else:
            chans = core.channels_of(obj) or list(core.TRANSFORM_CHANNELS)
            for c in chans:
                v = core.evaluate_channel(obj, c, f)
                core.insert_key(obj, c, f, v, scene=self.scene)
            self.ctx.select(core.refs_at_frame(obj, f))

    def wheelEvent(self, e: QWheelEvent) -> None:
        d = e.angleDelta().y() or e.angleDelta().x()
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            x = e.position().x()
            anchor = self.x_to_frame(x)
            self.ppf = max(0.5, min(64.0, self.ppf * (1.25 if d > 0 else 0.8)))
            self.f0 = anchor - (x - NAME_W) / self.ppf
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            self.f0 -= (d / 120.0) * 48 / self.ppf
        else:
            self.scroll -= int(d / 120.0 * ROW_H)
            self._clamp_scroll()
        self.update()
        e.accept()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        k = e.key()
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.ctx.delete_selected()
        elif k == Qt.Key.Key_C and ctrl:
            self.ctx.copy_selected()
        elif k == Qt.Key.Key_X and ctrl:
            self.ctx.cut_selected()
        elif k == Qt.Key.Key_V and ctrl:
            self.ctx.paste()
        elif k == Qt.Key.Key_A and ctrl:
            self.ctx.select([r for o in self.objects() for r in core.all_refs(o)])
        elif k == Qt.Key.Key_H:
            self.frame_all()
        elif k == Qt.Key.Key_Left:
            if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                self.ctx.move_selected(-1)
            else:
                self.ctx.player.prev_frame()
        elif k == Qt.Key.Key_Right:
            if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                self.ctx.move_selected(1)
            else:
                self.ctx.player.next_frame()
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:
        f = float(round(self.x_to_frame(e.pos().x()))) if e.pos().x() >= NAME_W else None
        menu = key_menu(self.ctx, self, f)
        menu.addSeparator()
        menu.addAction("Frame All", self.frame_all)
        menu.exec(e.globalPos())

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._clamp_scroll()


class DopeSheet(QFrame):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if scene is None:
            from ..scene import get_scene
            scene = get_scene()
        self.scene = scene
        self.ctx = get_context(scene)
        self.setObjectName("AnimDopeSheet")
        self.setStyleSheet(panel_qss())
        root = QVBoxLayout(self)
        root.setContentsMargins(GAP, GAP, GAP, GAP)
        root.setSpacing(GAP)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(GAP)
        root.addLayout(bar)
        self.canvas = DopeCanvas(self.ctx, self)
        root.addWidget(self.canvas, 1)
        c = self.ctx
        self.btn_frame = tool_button("frame_all", "Frame All", self.canvas.frame_all, parent=self)
        self.btn_active = tool_button("active", "Show Active Object Only", self._set_active_only, True, self)
        self.btn_expand = tool_button("expand", "Expand All", lambda: self.canvas.set_expanded_all(True), parent=self)
        self.btn_collapse = tool_button("collapse", "Collapse All", lambda: self.canvas.set_expanded_all(False),
                                        parent=self)
        self.btn_record = tool_button("record", "Record Active Objects", c.record, parent=self)
        self.btn_key = record_button(c, self)
        self.btn_spline = tool_button("spline", "Spline Interpolation", lambda: c.set_interp("spline"), parent=self)
        self.btn_linear = tool_button("linear", "Linear Interpolation", lambda: c.set_interp("linear"), parent=self)
        self.btn_step = tool_button("step", "Step Interpolation", lambda: c.set_interp("step"), parent=self)
        self.btn_copy = tool_button("copy", "Copy Keys", c.copy_selected, parent=self)
        self.btn_paste = tool_button("paste", "Paste Keys at Current Frame", lambda: c.paste(), parent=self)
        self.btn_delete = tool_button("delete", "Delete Selected Keys", c.delete_selected, parent=self)
        self.scale_spin = float_spin(0.01, 100.0, 2.0, "Key Scale Factor", 2, self)
        self.btn_scale = tool_button("scale", "Scale Selected Keys", self._scale, parent=self)
        self.btn_left = tool_button("prev_frame", "Move Keys Left", lambda: c.move_selected(-1), parent=self)
        self.btn_right = tool_button("next_frame", "Move Keys Right", lambda: c.move_selected(1), parent=self)
        for w in (self.btn_frame, self.btn_active, self.btn_expand, self.btn_collapse, self.btn_record, self.btn_key):
            bar.addWidget(w)
        bar.addSpacing(MARGIN)
        for w in (self.btn_spline, self.btn_linear, self.btn_step):
            bar.addWidget(w)
        bar.addSpacing(MARGIN)
        for w in (self.btn_copy, self.btn_paste, self.btn_delete, self.btn_left, self.btn_right):
            bar.addWidget(w)
        bar.addSpacing(MARGIN)
        bar.addWidget(self.scale_spin)
        bar.addWidget(self.btn_scale)
        bar.addStretch(1)
        c.keySelectionChanged.connect(self._sync)
        self._sync()

    def _set_active_only(self, on: bool) -> None:
        self.canvas.active_only = bool(on)
        self.canvas.scroll = 0
        self.canvas.update()

    def _scale(self) -> list:
        if not self.ctx.selection:
            return []
        factor = float(self.scale_spin.value())
        if factor <= 0:
            return []
        pivot = min(float(r[2]) for r in self.ctx.selection)
        return self.ctx.scale_selected(factor, pivot)

    def _sync(self) -> None:
        has = bool(self.ctx.selection)
        for b in (self.btn_spline, self.btn_linear, self.btn_step, self.btn_copy, self.btn_delete, self.btn_scale,
                  self.btn_left, self.btn_right):
            b.setEnabled(has)
