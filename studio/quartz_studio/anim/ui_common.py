from __future__ import annotations

import math

from PySide6.QtCore import QLocale, QObject, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF)
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QMenu, QSpinBox, QToolButton, QWidget

from .. import theme
from . import core

__all__ = [
    "BUTTON",
    "ICON",
    "FIELD_W",
    "COMBO_W",
    "ROW",
    "GAP",
    "MARGIN",
    "glyph",
    "tool_button",
    "int_spin",
    "float_spin",
    "combo",
    "panel_qss",
    "small_font",
    "nice_step",
    "nice_value_step",
    "channel_color",
    "diamond",
    "label_frame",
    "EditGroup",
    "fill_record_menu",
    "record_button",
]

BUTTON = 24
ICON = 16
FIELD_W = 72
COMBO_W = 96
ROW = 24
GAP = 4
MARGIN = 8


def small_font(base: QFont | None = None, px: int = 12, bold: bool = False) -> QFont:
    f = QFont(base) if base is not None else QFont(theme.FONT_FAMILY)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def _poly(points, flip: bool) -> QPolygonF:
    return QPolygonF([QPointF(16 - x if flip else x, y) for x, y in points])


def _draw(p: QPainter, name: str, color: QColor) -> None:
    fill = QBrush(color)
    stroke = QPen(color, 2)
    stroke.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroke.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    flip = name in ("end", "next_key", "next_frame", "play")
    base = {"end": "start", "next_key": "prev_key", "next_frame": "prev_frame", "play": "play_back"}.get(name, name)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fill)
    if base == "start":
        p.drawPolygon(_poly([(2, 2), (4, 2), (4, 14), (2, 14)], flip))
        p.drawPolygon(_poly([(14, 2), (14, 14), (6, 8)], flip))
    elif base == "prev_key":
        p.drawPolygon(_poly([(4, 6), (6, 8), (4, 10), (2, 8)], flip))
        p.drawPolygon(_poly([(14, 2), (14, 14), (8, 8)], flip))
    elif base == "prev_frame":
        p.drawPolygon(_poly([(12, 4), (14, 4), (14, 12), (12, 12)], flip))
        p.drawPolygon(_poly([(10, 4), (10, 12), (4, 8)], flip))
    elif base == "play_back":
        p.drawPolygon(_poly([(12, 2), (12, 14), (2, 8)], flip))
    elif name == "pause":
        p.drawRect(QRectF(4, 2, 2, 12))
        p.drawRect(QRectF(10, 2, 2, 12))
    elif name == "stop":
        p.drawRect(QRectF(4, 4, 8, 8))
    elif name == "record":
        p.setBrush(QBrush(QColor(theme.STATUS_ERROR)))
        p.drawEllipse(QPointF(8, 8), 6, 6)
    elif name == "autokey":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(theme.STATUS_ERROR), 2))
        p.drawEllipse(QPointF(8, 8), 6, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(theme.STATUS_ERROR)))
        p.drawEllipse(QPointF(8, 8), 2, 2)
    elif name == "pla":
        p.setBrush(QBrush(QColor(theme.STATUS_ERROR)))
        for x in (2, 10):
            for y in (2, 10):
                p.drawRect(QRectF(x, y, 4, 4))
    elif name == "key":
        p.drawPolygon(_poly([(8, 2), (14, 8), (8, 14), (2, 8)], False))
    else:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(stroke)
        path = QPainterPath()
        if name == "loop":
            path.arcMoveTo(QRectF(2, 4, 12, 8), 30)
            path.arcTo(QRectF(2, 4, 12, 8), 30, 300)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawPolygon(QPolygonF([QPointF(10, 2), QPointF(14, 6), QPointF(8, 6)]))
            return
        if name == "frame_all":
            for x, y, dx, dy in ((2, 2, 1, 1), (14, 2, -1, 1), (2, 14, 1, -1), (14, 14, -1, -1)):
                path.moveTo(x, y + 4 * dy)
                path.lineTo(x, y)
                path.lineTo(x + 4 * dx, y)
        elif name == "frame_sel":
            for x, y, dx, dy in ((2, 2, 1, 1), (14, 2, -1, 1), (2, 14, 1, -1), (14, 14, -1, -1)):
                path.moveTo(x, y + 4 * dy)
                path.lineTo(x, y)
                path.lineTo(x + 4 * dx, y)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawPolygon(_poly([(8, 6), (10, 8), (8, 10), (6, 8)], False))
            return
        elif name == "spline":
            path.moveTo(2, 14)
            path.cubicTo(8, 14, 8, 2, 14, 2)
        elif name == "linear":
            path.moveTo(2, 14)
            path.lineTo(14, 2)
        elif name == "step":
            path.moveTo(2, 14)
            path.lineTo(8, 14)
            path.lineTo(8, 2)
            path.lineTo(14, 2)
        elif name == "ease_in":
            path.moveTo(2, 14)
            path.cubicTo(12, 14, 14, 6, 14, 2)
        elif name == "ease_out":
            path.moveTo(2, 14)
            path.cubicTo(2, 8, 4, 2, 14, 2)
        elif name == "ease_both":
            path.moveTo(2, 14)
            path.cubicTo(12, 14, 4, 2, 14, 2)
        elif name == "auto_tan":
            path.moveTo(2, 12)
            path.cubicTo(6, 4, 10, 4, 14, 12)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawEllipse(QPointF(8, 6), 2, 2)
            return
        elif name == "flat_tan":
            path.moveTo(2, 8)
            path.lineTo(14, 8)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            for x in (2, 14):
                p.drawEllipse(QPointF(x, 8), 2, 2)
            p.drawPolygon(_poly([(8, 4), (12, 8), (8, 12), (4, 8)], False))
            return
        elif name == "delete":
            path.moveTo(4, 4)
            path.lineTo(12, 12)
            path.moveTo(12, 4)
            path.lineTo(4, 12)
        elif name == "copy":
            path.addRect(QRectF(2, 6, 8, 8))
            path.moveTo(6, 4)
            path.lineTo(6, 2)
            path.lineTo(14, 2)
            path.lineTo(14, 10)
            path.lineTo(12, 10)
        elif name == "paste":
            path.addRect(QRectF(4, 4, 8, 10))
            path.moveTo(6, 2)
            path.lineTo(10, 2)
        elif name == "scale":
            path.moveTo(2, 8)
            path.lineTo(14, 8)
            path.moveTo(4, 6)
            path.lineTo(2, 8)
            path.lineTo(4, 10)
            path.moveTo(12, 6)
            path.lineTo(14, 8)
            path.lineTo(12, 10)
        elif name == "expand":
            path.moveTo(4, 6)
            path.lineTo(8, 10)
            path.lineTo(12, 6)
        elif name == "collapse":
            path.moveTo(6, 4)
            path.lineTo(10, 8)
            path.lineTo(6, 12)
        elif name == "active":
            path.addEllipse(QPointF(8, 8), 6, 6)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawEllipse(QPointF(8, 8), 2, 2)
            return
        else:
            path.addRect(QRectF(4, 4, 8, 8))
        p.drawPath(path)


def glyph(name: str, color: str | None = None, size: int = ICON) -> QIcon:
    icon = QIcon()
    for scale in (1, 2):
        for mode, tint in ((QIcon.Mode.Normal, color or theme.ICON_STROKE),
                           (QIcon.Mode.Disabled, theme.TEXT_MUTED),
                           (QIcon.Mode.Active, theme.TEXT_BRIGHT)):
            pm = QPixmap(size * scale, size * scale)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.scale(size * scale / 16.0, size * scale / 16.0)
            _draw(p, name, QColor(tint))
            p.end()
            pm.setDevicePixelRatio(scale)
            icon.addPixmap(pm, mode)
    return icon


def panel_qss() -> str:
    return (
        f"QToolButton {{ background: transparent; border: none; border-radius: {GAP}px; "
        f"color: {theme.TEXT_PRIMARY}; padding: 2px; }}"
        f"QToolButton:hover {{ background: {theme.SURFACE_HOVER}; }}"
        f"QToolButton:pressed {{ background: {theme.SURFACE_PRESSED}; }}"
        f"QToolButton:checked {{ background: {theme.ACCENT_TINT}; }}"
        f"QToolButton:disabled {{ color: {theme.TEXT_MUTED}; }}"
        f"#AnimTimelineBar, #AnimDopeSheet, #AnimCurveEditor {{ background: {theme.SURFACE_CARD}; "
        f"color: {theme.TEXT_PRIMARY}; }}"
        f"QListWidget {{ background: {theme.SURFACE_FIELD}; color: {theme.TEXT_PRIMARY}; "
        f"border: 1px solid {theme.HAIRLINE}; border-radius: {GAP}px; }}"
        f"QListWidget::item {{ min-height: {ROW}px; padding: 0px {GAP}px; }}"
        f"QListWidget::item:selected {{ background: {theme.ACCENT_TINT}; color: {theme.TEXT_BRIGHT}; }}"
    )


def tool_button(icon: str, tooltip: str, callback=None, checkable: bool = False,
                parent: QWidget | None = None, color: str | None = None) -> QToolButton:
    b = QToolButton(parent)
    b.setIcon(glyph(icon, color))
    b.setIconSize(QSize(ICON, ICON))
    b.setFixedSize(BUTTON, BUTTON)
    b.setToolTip(tooltip)
    b.setAccessibleName(tooltip)
    b.setAutoRaise(True)
    b.setCheckable(checkable)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setProperty("animIcon", icon)
    if callback is not None:
        if checkable:
            b.toggled.connect(callback)
        else:
            b.clicked.connect(lambda _c=False: callback())
    return b


def int_spin(lo: int, hi: int, value: int, tooltip: str, suffix: str = "", parent: QWidget | None = None,
             width: int = FIELD_W) -> QSpinBox:
    s = QSpinBox(parent)
    s.setRange(lo, hi)
    s.setValue(value)
    s.setToolTip(tooltip)
    s.setAccessibleName(tooltip)
    s.setSuffix(suffix)
    s.setFixedWidth(width)
    s.setFixedHeight(ROW)
    s.setKeyboardTracking(False)
    s.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return s


def float_spin(lo: float, hi: float, value: float, tooltip: str, decimals: int = 3,
               parent: QWidget | None = None, width: int = FIELD_W) -> QDoubleSpinBox:
    s = QDoubleSpinBox(parent)
    loc = QLocale.c()
    loc.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    s.setLocale(loc)
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setValue(value)
    s.setToolTip(tooltip)
    s.setAccessibleName(tooltip)
    s.setFixedWidth(width)
    s.setFixedHeight(ROW)
    s.setKeyboardTracking(False)
    s.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return s


def combo(items, tooltip: str, parent: QWidget | None = None, width: int = COMBO_W) -> QComboBox:
    c = QComboBox(parent)
    for text, data in items:
        c.addItem(text, data)
    c.setToolTip(tooltip)
    c.setAccessibleName(tooltip)
    c.setFixedWidth(width)
    c.setFixedHeight(ROW)
    c.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return c


def nice_step(px_per_unit: float, min_px: float = 48.0, integer: bool = True) -> float:
    if px_per_unit <= 0:
        return 1.0
    raw = min_px / px_per_unit
    if integer and raw <= 1:
        return 1.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if m * mag >= raw:
            step = m * mag
            return max(1.0, step) if integer else step
    return 10 * mag


def nice_value_step(px_per_unit: float, min_px: float = 32.0) -> float:
    return nice_step(px_per_unit, min_px, integer=False)


_PARAM_TINTS = (theme.TINT_AMETHYST, theme.TINT_CITRINE, theme.TINT_ROSE, theme.TINT_MINT)


def channel_color(channel: str) -> QColor:
    if channel.endswith(".x") and not channel.startswith(core.PARAM_PREFIX):
        return QColor(theme.AXIS_X)
    if channel.endswith(".y") and not channel.startswith(core.PARAM_PREFIX):
        return QColor(theme.AXIS_Y)
    if channel.endswith(".z") and not channel.startswith(core.PARAM_PREFIX):
        return QColor(theme.AXIS_Z)
    if channel == core.VISIBILITY:
        return QColor(theme.TEXT_SECONDARY)
    if channel == core.POINTS:
        return QColor(theme.TINT_CITRINE)
    return QColor(_PARAM_TINTS[sum(map(ord, channel)) % len(_PARAM_TINTS)])


def diamond(cx: float, cy: float, r: float) -> QPolygonF:
    return QPolygonF([QPointF(cx, cy - r), QPointF(cx + r, cy), QPointF(cx, cy + r), QPointF(cx - r, cy)])


def label_frame(scene, frame: float, mode: str) -> str:
    if mode == "frames":
        v = round(float(frame))
        return str(int(v)) if abs(v - float(frame)) < 1e-6 else f"{float(frame):.1f}"
    return core.format_time(scene, frame, mode)


class EditGroup(QObject):

    def __init__(self, scene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self._token = None
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._poll)

    @property
    def active(self) -> bool:
        return self._token is not None

    def begin(self) -> None:
        if self._token is None:
            self._token = core.begin_edit(self.scene)
            self._timer.start()

    def end(self) -> None:
        self._timer.stop()
        token, self._token = self._token, None
        if token is not None:
            core.end_edit(token)

    def _poll(self) -> None:
        if QGuiApplication.mouseButtons() == Qt.MouseButton.NoButton:
            self.end()


def fill_record_menu(ctx, menu: QMenu) -> QMenu:
    menu.clear()
    targets = ctx.targets()
    has = bool(targets)
    entries = (("Position, Rotation and Scale", None), ("Position", core.POSITION_CHANNELS),
               ("Rotation", core.ROTATION_CHANNELS), ("Scale", core.SCALE_CHANNELS))
    for text, chans in entries:
        a = menu.addAction(text, lambda c=chans: ctx.record(c))
        a.setEnabled(has)
    a = menu.addAction("Visibility", ctx.record_visibility)
    a.setEnabled(has)
    menu.addSeparator()
    params: list = []
    for o in targets:
        for ch in core.keyable_params(o):
            if ch not in params:
                params.append(ch)
    a = menu.addAction("Add Parameter Keys", lambda: ctx.record_params())
    a.setEnabled(bool(params))
    if params:
        sub = menu.addMenu("Parameter")
        ref = targets[0]
        for ch in params:
            sub.addAction(core.channel_label(ch, ref), lambda c=ch: ctx.record_params([c]))
    menu.addSeparator()
    polys = [o for o in targets if getattr(o, "kind", "") == "polygon" and len(o.mesh.points)]
    a = menu.addAction("Record Points", ctx.record_points)
    a.setEnabled(bool(polys))
    a = menu.addAction("Record Point Selection", ctx.record_point_selection)
    active = getattr(ctx.scene, "active", None)
    a.setEnabled(bool(polys) and active in polys and bool(getattr(ctx.scene, "selected_points", None)))
    a = menu.addAction("Clear Points", ctx.clear_points)
    a.setEnabled(any(core.get_track(o, core.POINTS) for o in targets))
    return menu


def record_button(ctx, parent: QWidget | None = None) -> QToolButton:
    b = tool_button("key", "Record Channel", parent=parent)
    menu = QMenu(b)
    menu.aboutToShow.connect(lambda: fill_record_menu(ctx, menu))
    b.setMenu(menu)
    b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    b.setStyleSheet("QToolButton::menu-indicator { image: none; }")
    fill_record_menu(ctx, menu)
    return b
