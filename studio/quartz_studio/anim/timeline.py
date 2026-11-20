from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QContextMenuEvent, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QVBoxLayout, QWidget

from .. import theme
from . import core
from .player import AnimContext, get_context
from .ui_common import (GAP, MARGIN, EditGroup, combo, diamond, fill_record_menu, int_spin, label_frame,
                        nice_step, panel_qss, record_button, small_font, tool_button)

__all__ = ["FrameRuler", "PreviewStrip", "TimelineBar", "key_menu"]

RULER_H = 48
STRIP_H = 12
SIDE = 16
LABEL_ROW = 16
KEY_ROW_Y = 32
KEY_R = 6
HIT = 6
CHIP_H = 16
CHIP_W = 32


def key_menu(ctx: AnimContext, parent: QWidget, frame: float | None = None) -> QMenu:
    menu = QMenu(parent)
    has = bool(ctx.selection)
    menu.addAction("Record Active Objects", ctx.record)
    fill_record_menu(ctx, menu.addMenu("Record Channel"))
    a = menu.addAction("Delete Selected Keys", ctx.delete_selected)
    a.setEnabled(has)
    menu.addAction("Delete Keys at Current Frame", ctx.delete_at_frame)
    menu.addAction("Delete Tracks of Active Objects", ctx.delete_tracks)
    a = menu.addAction("Reverse Keys", ctx.reverse_selected)
    a.setEnabled(len(ctx.selection) > 1)
    menu.addSeparator()
    a = menu.addAction("Copy Keys", ctx.copy_selected)
    a.setEnabled(has)
    a = menu.addAction("Cut Keys", ctx.cut_selected)
    a.setEnabled(has)
    a = menu.addAction("Paste Keys", lambda: ctx.paste(frame))
    a.setEnabled(bool(ctx.clipboard.get("items")))
    menu.addSeparator()
    interp = menu.addMenu("Interpolation")
    for text, mode in (("Spline", "spline"), ("Linear", "linear"), ("Step", "step")):
        a = interp.addAction(text, lambda m=mode: ctx.set_interp(m))
        a.setEnabled(has)
    ease = menu.addMenu("Ease")
    for text, mode in (("None", "none"), ("Ease In", "in"), ("Ease Out", "out"), ("Ease In Out", "both")):
        a = ease.addAction(text, lambda m=mode: ctx.set_ease(m))
        a.setEnabled(has)
    tan = menu.addMenu("Tangents")
    a = tan.addAction("Auto", ctx.reset_tangents)
    a.setEnabled(has)
    a = tan.addAction("Flat", ctx.flatten_tangents)
    a.setEnabled(has)
    for title, side in (("Before", "before"), ("After", "after")):
        sub = menu.addMenu(f"Loop {title}")
        for text, mode in (("Constant", "constant"), ("Repeat", "repeat"), ("Offset Repeat", "offset"),
                           ("Oscillate", "oscillate")):
            a = sub.addAction(text, lambda m=mode, s=side: ctx.set_loop(**{s: m}))
            a.setEnabled(has)
    return menu


class FrameRuler(QWidget):

    scrubbed = Signal(float)

    def __init__(self, ctx: AnimContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.scene = ctx.scene
        self.time_mode = "frames"
        self.setFixedHeight(RULER_H)
        self.setMinimumWidth(256)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self._mode = ""
        self._drag_base = None
        self._drag_refs: list = []
        self._drag_origin = 0.0
        self._drag_delta = 0
        ctx.frameChanged.connect(self.update)
        ctx.timeChanged.connect(self.update)
        ctx.keysChanged.connect(self.update)
        ctx.keySelectionChanged.connect(self.update)
        if hasattr(self.scene, "selectionChanged"):
            self.scene.selectionChanged.connect(self.update)

    def doc_range(self) -> tuple[float, float]:
        s = self.ctx.settings()
        lo, hi = float(s["min"]), float(s["max"])
        return (lo, hi) if hi > lo else (lo, lo + 1.0)

    def ppf(self) -> float:
        lo, hi = self.doc_range()
        return max(1e-6, (self.width() - 2 * SIDE) / (hi - lo))

    def frame_to_x(self, f: float) -> float:
        lo, _hi = self.doc_range()
        return SIDE + (float(f) - lo) * self.ppf()

    def x_to_frame(self, x: float) -> float:
        lo, hi = self.doc_range()
        return min(max(lo + (float(x) - SIDE) / self.ppf(), lo), hi)

    def targets(self) -> list:
        return self.ctx.targets()

    def key_frames(self) -> list:
        return core.key_frames(self.targets())

    def selected_frames(self) -> set:
        ids = {id(o) for o in self.targets()}
        return {round(float(r[2]), 6) for r in self.ctx.selection if id(r[0]) in ids}

    def key_at(self, x: float) -> float | None:
        best, dist = None, HIT + 1
        for f in self.key_frames():
            d = abs(self.frame_to_x(f) - x)
            if d < dist:
                best, dist = f, d
        return best if dist <= HIT else None

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.SURFACE_FIELD))
        s = self.ctx.settings()
        lo, hi = self.doc_range()
        x0, x1 = self.frame_to_x(s["preview_min"]), self.frame_to_x(s["preview_max"])
        shade = QColor(theme.SURFACE_PRESSED)
        shade.setAlpha(160)
        p.fillRect(QRectF(0, 0, x0, h), shade)
        p.fillRect(QRectF(x1, 0, w - x1, h), shade)
        ppf = self.ppf()
        step = nice_step(ppf, 48)
        p.setFont(small_font(self.font()))
        minor_pen = QPen(QColor(theme.HAIRLINE), 1)
        major_pen = QPen(QColor(theme.HAIRLINE_STRONG), 1)
        if ppf >= 4:
            p.setPen(minor_pen)
            f = int(lo)
            while f <= hi:
                x = self.frame_to_x(f)
                p.drawLine(QPointF(x, h - 4), QPointF(x, h))
                f += 1
        f = lo - (lo % step) if lo % step else lo
        while f <= hi + 1e-9:
            if f >= lo:
                x = self.frame_to_x(f)
                p.setPen(major_pen)
                p.drawLine(QPointF(x, LABEL_ROW + 2), QPointF(x, h))
                p.setPen(QColor(theme.TEXT_SECONDARY))
                p.drawText(QRectF(x + 2, 2, 64, LABEL_ROW), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           label_frame(self.scene, f, self.time_mode))
            f += step
        p.setPen(QPen(QColor(theme.HAIRLINE), 1))
        p.drawLine(QPointF(0, h - 1), QPointF(w, h - 1))
        sel = self.selected_frames()
        delta = self._drag_delta if self._mode == "keys" else 0
        for f in self.key_frames():
            selected = round(float(f), 6) in sel
            x = self.frame_to_x(f)
            if selected and delta:
                ghost = QColor(theme.SELECT_FRONT)
                ghost.setAlpha(96)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ghost)
                p.drawPolygon(diamond(x, KEY_ROW_Y, KEY_R))
                continue
            p.setPen(QPen(QColor(theme.SURFACE_PRESSED), 1))
            p.setBrush(QBrush(QColor(theme.SELECT_FRONT if selected else theme.TEXT_SECONDARY)))
            p.drawPolygon(diamond(x, KEY_ROW_Y, KEY_R))
        if self._mode == "keys" and delta:
            p.setPen(QPen(QColor(theme.SURFACE_PRESSED), 1))
            p.setBrush(QBrush(QColor(theme.SELECT_FRONT)))
            for f in sel:
                p.drawPolygon(diamond(self.frame_to_x(f + delta), KEY_ROW_Y, KEY_R))
        cur = s["frame"]
        x = self.frame_to_x(cur)
        p.setPen(QPen(QColor(theme.ACCENT), 2))
        p.drawLine(QPointF(x, CHIP_H), QPointF(x, h))
        chip = QRectF(x - CHIP_W / 2, 0, CHIP_W, CHIP_H)
        if chip.left() < 0:
            chip.moveLeft(0)
        if chip.right() > w:
            chip.moveRight(w)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(theme.ACCENT)))
        p.drawRoundedRect(chip, GAP, GAP)
        p.setPen(QColor(theme.ACCENT_ON))
        p.setFont(small_font(self.font(), bold=True))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, label_frame(self.scene, cur, "frames"))
        p.end()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(e)
            return
        pos = e.position()
        mods = e.modifiers()
        hit = self.key_at(pos.x()) if pos.y() >= LABEL_ROW + 2 else None
        if hit is not None:
            refs = core.refs_at_frame(self.targets(), hit)
            if mods & Qt.KeyboardModifier.ControlModifier:
                self.ctx.select(refs, "toggle")
                return
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self.ctx.select(refs, "add")
            elif not all(self.ctx.is_selected(*r) for r in refs):
                self.ctx.select(refs, "replace")
            self._mode = "keys"
            ids = {id(o) for o in self.targets()}
            self._drag_refs = [r for r in self.ctx.selection if id(r[0]) in ids]
            self._drag_base = core.snapshot_tracks(self.targets())
            self._drag_origin = self.x_to_frame(pos.x())
            self._drag_delta = 0
            return
        if not mods & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
            self.ctx.clear_selection()
        self._mode = "scrub"
        self.ctx.player.stop()
        self._scrub(pos.x())

    def _scrub(self, x: float) -> None:
        f = float(round(self.x_to_frame(x)))
        if f != float(self.ctx.frame):
            self.ctx.set_frame(f)
            self.scrubbed.emit(f)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if self._mode == "scrub":
            self._scrub(pos.x())
        elif self._mode == "keys":
            d = int(round(self.x_to_frame(pos.x()) - self._drag_origin))
            if d != self._drag_delta:
                self._drag_delta = d
                self.update()
        else:
            hit = self.key_at(pos.x())
            self.setCursor(Qt.CursorShape.SizeHorCursor if hit is not None and pos.y() >= LABEL_ROW
                           else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._mode == "keys" and self._drag_delta:
            with core.edit_group(self.scene):
                refs = core.move_keys(self._drag_refs, self._drag_delta)
            keep = [r for r in self.ctx.selection if not any(r[0] is d[0] and r[1] == d[1] and r[2] == d[2]
                                                               for d in self._drag_refs)]
            self.ctx.select(core.refs_exist(keep) + refs)
            self.ctx.evaluate()
        self._mode = ""
        self._drag_delta = 0
        self._drag_base = None
        self.update()

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            f = float(round(self.x_to_frame(e.position().x())))
            self.ctx.set_frame(f)
            self.ctx.record()
            self._mode = ""

    def wheelEvent(self, e: QWheelEvent) -> None:
        d = e.angleDelta().y() or e.angleDelta().x()
        if d:
            self.ctx.player.step(1 if d < 0 else -1)
        e.accept()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        k = e.key()
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.ctx.delete_selected()
        elif k == Qt.Key.Key_C and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.ctx.copy_selected()
        elif k == Qt.Key.Key_V and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.ctx.paste()
        elif k == Qt.Key.Key_A and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.ctx.select([r for o in self.targets() for r in core.all_refs(o)])
        elif k == Qt.Key.Key_Left:
            self.ctx.player.prev_frame()
        elif k == Qt.Key.Key_Right:
            self.ctx.player.next_frame()
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:
        f = float(round(self.x_to_frame(e.pos().x())))
        key_menu(self.ctx, self, f).exec(e.globalPos())


class PreviewStrip(QWidget):

    def __init__(self, ctx: AnimContext, ruler: FrameRuler, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.ruler = ruler
        self.setFixedHeight(STRIP_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._mode = ""
        self._origin = 0.0
        self._start = (0, 0)
        self.group = EditGroup(ctx.scene, self)
        ctx.timeChanged.connect(self.update)

    def _part(self, x: float) -> str:
        s = self.ctx.settings()
        x0, x1 = self.ruler.frame_to_x(s["preview_min"]), self.ruler.frame_to_x(s["preview_max"])
        if abs(x - x0) <= HIT:
            return "min"
        if abs(x - x1) <= HIT:
            return "max"
        if x0 < x < x1:
            return "move"
        return ""

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(theme.SURFACE_CARD))
        s = self.ctx.settings()
        x0, x1 = self.ruler.frame_to_x(s["preview_min"]), self.ruler.frame_to_x(s["preview_max"])
        bar = QRectF(x0, 2, max(GAP, x1 - x0), STRIP_H - GAP)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(theme.ACCENT_TINT_HOVER)))
        p.drawRoundedRect(bar, 2, 2)
        p.setBrush(QBrush(QColor(theme.ACCENT)))
        p.drawRoundedRect(QRectF(x0 - 2, 2, GAP, STRIP_H - GAP), 2, 2)
        p.drawRoundedRect(QRectF(x1 - 2, 2, GAP, STRIP_H - GAP), 2, 2)
        p.end()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self._mode = self._part(e.position().x())
        self._origin = self.ruler.x_to_frame(e.position().x())
        s = self.ctx.settings()
        self._start = (s["preview_min"], s["preview_max"])
        if self._mode:
            self.group.begin()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        x = e.position().x()
        if not self._mode:
            part = self._part(x)
            self.setCursor(Qt.CursorShape.SizeHorCursor if part in ("min", "max")
                           else Qt.CursorShape.OpenHandCursor if part == "move" else Qt.CursorShape.ArrowCursor)
            return
        f = int(round(self.ruler.x_to_frame(x)))
        lo, hi = self._start
        if self._mode == "min":
            self.ctx.set_settings(preview_min=min(f, hi))
        elif self._mode == "max":
            self.ctx.set_settings(preview_max=max(f, lo))
        else:
            s = self.ctx.settings()
            d = int(round(self.ruler.x_to_frame(x) - self._origin))
            d = max(s["min"] - lo, min(s["max"] - hi, d))
            self.ctx.set_settings(preview_min=lo + d, preview_max=hi + d)

    def mouseReleaseEvent(self, _e) -> None:
        self._mode = ""
        self.group.end()

    def hideEvent(self, e) -> None:
        self._mode = ""
        self.group.end()
        super().hideEvent(e)

    def mouseDoubleClickEvent(self, _e) -> None:
        self.group.end()
        self._mode = ""
        s = self.ctx.settings()
        self.ctx.set_settings(preview_min=s["min"], preview_max=s["max"])


class TimelineBar(QFrame):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if scene is None:
            from ..scene import get_scene
            scene = get_scene()
        self.scene = scene
        self.ctx = get_context(scene)
        self.setObjectName("AnimTimelineBar")
        self.setStyleSheet(panel_qss())
        self.setAutoFillBackground(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(MARGIN, GAP, MARGIN, GAP)
        root.setSpacing(GAP)
        self.ruler = FrameRuler(self.ctx, self)
        self.strip = PreviewStrip(self.ctx, self.ruler, self)
        root.addWidget(self.ruler)
        root.addWidget(self.strip)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GAP)
        root.addLayout(row)
        s = self.ctx.settings()
        self.min_spin = int_spin(-100000, 100000, s["min"], "Minimum Time", " F", self)
        self.pmin_spin = int_spin(-100000, 100000, s["preview_min"], "Preview Min Time", " F", self)
        self.pmax_spin = int_spin(-100000, 100000, s["preview_max"], "Preview Max Time", " F", self)
        self.max_spin = int_spin(-100000, 100000, s["max"], "Maximum Time", " F", self)
        self.frame_spin = int_spin(-100000, 100000, int(round(s["frame"])), "Current Frame", " F", self)
        self.fps_spin = int_spin(1, 240, s["fps"], "Frame Rate", " fps", self)
        self.min_spin.valueChanged.connect(lambda v: self.ctx.set_settings(min=v))
        self.max_spin.valueChanged.connect(lambda v: self.ctx.set_settings(max=v))
        self.pmin_spin.valueChanged.connect(lambda v: self.ctx.set_settings(preview_min=v))
        self.pmax_spin.valueChanged.connect(lambda v: self.ctx.set_settings(preview_max=v))
        self.frame_spin.valueChanged.connect(lambda v: self.ctx.set_frame(v))
        self.fps_spin.valueChanged.connect(self._set_fps)
        pl = self.ctx.player
        self.btn_start = tool_button("start", "Go To Start", pl.go_start, parent=self)
        self.btn_prev_key = tool_button("prev_key", "Previous Key", pl.prev_key, parent=self)
        self.btn_prev = tool_button("prev_frame", "Previous Frame", pl.prev_frame, parent=self)
        self.btn_back = tool_button("play_back", "Play Backwards", lambda: pl.toggle(-1), parent=self)
        self.btn_play = tool_button("play", "Play Forwards", lambda: pl.toggle(1), parent=self)
        self.btn_next = tool_button("next_frame", "Next Frame", pl.next_frame, parent=self)
        self.btn_next_key = tool_button("next_key", "Next Key", pl.next_key, parent=self)
        self.btn_end = tool_button("end", "Go To End", pl.go_end, parent=self)
        self.btn_back.setCheckable(True)
        self.btn_play.setCheckable(True)
        self.btn_record = tool_button("record", "Record Active Objects", self.ctx.record, parent=self)
        self.btn_autokey = tool_button("autokey", "Autokeying", self.ctx.autokey.set_enabled, True, self)
        self.btn_pla = tool_button("pla", "Record Point Level Animation", self.ctx.record_points, parent=self)
        self.btn_key = record_button(self.ctx, self)
        self.btn_loop = tool_button("loop", "Loop Playback", self._set_loop, True, self)
        self.btn_loop.setChecked(s["loop"] and not s["pingpong"])
        self.loop_combo = combo((("Simple", "simple"), ("Loop", "loop"), ("Ping-Pong", "pingpong")),
                                "Playback Mode at the End of the Preview Range", self)
        self.loop_combo.currentIndexChanged.connect(
            lambda _i: self.ctx.set_playback_mode(self.loop_combo.currentData()))
        self.interp_combo = combo((("Spline", "spline"), ("Linear", "linear"), ("Step", "step")),
                                  "Default Interpolation for New Keys", self)
        self.interp_combo.currentIndexChanged.connect(
            lambda _i: self.ctx.set_settings(default_interp=self.interp_combo.currentData()))
        self.mode_combo = combo((("Frames", "frames"), ("Seconds", "seconds"), ("SMPTE", "smpte")),
                                "Time Display", self)
        self.mode_combo.currentIndexChanged.connect(self._set_time_mode)
        self.play_combo = combo((("Realtime", "realtime"), ("All Frames", "all_frames")), "Playback Mode", self)
        self.play_combo.currentIndexChanged.connect(
            lambda _i: self.ctx.set_settings(play_mode=self.play_combo.currentData()))
        self.readout = QLabel(self)
        self.readout.setFont(small_font(self.font()))
        self.readout.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self.readout.setMinimumWidth(96)
        for w in (self.min_spin, self.pmin_spin):
            row.addWidget(w)
        row.addStretch(1)
        for w in (self.btn_start, self.btn_prev_key, self.btn_prev, self.btn_back, self.btn_play, self.btn_next,
                  self.btn_next_key, self.btn_end):
            row.addWidget(w)
        row.addSpacing(MARGIN)
        for w in (self.btn_record, self.btn_key, self.btn_autokey, self.btn_pla, self.btn_loop):
            row.addWidget(w)
        row.addSpacing(MARGIN)
        row.addWidget(self.frame_spin)
        row.addWidget(self.readout)
        row.addWidget(self.fps_spin)
        row.addWidget(self.interp_combo)
        row.addWidget(self.play_combo)
        row.addWidget(self.loop_combo)
        row.addWidget(self.mode_combo)
        row.addStretch(1)
        for w in (self.pmax_spin, self.max_spin):
            row.addWidget(w)
        root.addStretch(1)
        self.ctx.timeChanged.connect(self.sync)
        self.ctx.frameChanged.connect(self.sync)
        pl.stateChanged.connect(self._sync_play)
        self.ctx.autokey.toggled.connect(self._sync_autokey)
        self.sync()

    def _set_loop(self, on: bool) -> None:
        self.ctx.set_playback_mode("loop" if on else "simple")

    def _set_fps(self, v: int) -> None:
        self.ctx.set_settings(fps=v)
        if self.ctx.player.is_playing():
            self.ctx.player.play(self.ctx.player.direction)

    def _set_time_mode(self, _i: int) -> None:
        self.ruler.time_mode = self.mode_combo.currentData()
        self.ruler.update()
        self.sync()

    def _sync_play(self, direction: int) -> None:
        for b, d in ((self.btn_play, 1), (self.btn_back, -1)):
            b.blockSignals(True)
            b.setChecked(direction == d)
            b.blockSignals(False)

    def _sync_autokey(self, on: bool) -> None:
        self.btn_autokey.blockSignals(True)
        self.btn_autokey.setChecked(on)
        self.btn_autokey.blockSignals(False)

    def sync(self, *_a) -> None:
        s = self.ctx.settings()
        pairs = ((self.min_spin, s["min"]), (self.max_spin, s["max"]), (self.pmin_spin, s["preview_min"]),
                 (self.pmax_spin, s["preview_max"]), (self.frame_spin, int(round(s["frame"]))),
                 (self.fps_spin, s["fps"]))
        for spin, v in pairs:
            if spin.value() != v:
                spin.blockSignals(True)
                spin.setValue(v)
                spin.blockSignals(False)
        mode_now = "pingpong" if s["pingpong"] else ("loop" if s["loop"] else "simple")
        for c, v in ((self.interp_combo, s["default_interp"]), (self.play_combo, s["play_mode"]),
                     (self.loop_combo, mode_now)):
            i = c.findData(v)
            if i >= 0 and i != c.currentIndex():
                c.blockSignals(True)
                c.setCurrentIndex(i)
                c.blockSignals(False)
        self.btn_loop.blockSignals(True)
        self.btn_loop.setChecked(mode_now == "loop")
        self.btn_loop.blockSignals(False)
        mode = self.mode_combo.currentData()
        self.readout.setText(core.format_time(self.scene, s["frame"], "smpte" if mode == "frames" else mode))
        self._sync_play(self.ctx.player.direction)
        self._sync_autokey(self.ctx.autokey.enabled)
        self.ruler.update()
        self.strip.update()
