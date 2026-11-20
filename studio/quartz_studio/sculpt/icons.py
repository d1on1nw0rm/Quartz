from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from .. import theme

__all__ = ["paint_brush_icon", "brush_pixmap", "brush_icon", "ICON_GRID"]

ICON_GRID = 32.0


def _pen(color, width: float = 2.0, dash: bool = False) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if dash:
        pen.setDashPattern([2.0, 2.0])
    return pen


def _arrow(p: QPainter, a: QPointF, b: QPointF, color, head: float = 4.0) -> None:
    p.setPen(_pen(color))
    p.drawLine(a, b)
    ang = math.atan2(b.y() - a.y(), b.x() - a.x())
    for s in (-1, 1):
        t = ang + math.pi + s * math.radians(38)
        p.drawLine(b, QPointF(b.x() + head * math.cos(t), b.y() + head * math.sin(t)))


def _curve(points) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for i in range(1, len(points), 3):
        c1, c2, e = points[i], points[i + 1], points[i + 2]
        path.cubicTo(QPointF(*c1), QPointF(*c2), QPointF(*e))
    return path


def _poly(points) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for pt in points[1:]:
        path.lineTo(QPointF(*pt))
    return path


def _flat(p: QPainter, line, y: float = 24.0) -> None:
    p.setPen(_pen(line))
    p.drawLine(QPointF(4, y), QPointF(28, y))


def paint_brush_icon(p: QPainter, brush_id: str, line=None, accent=None) -> None:
    line = QColor(line or theme.ICON_STROKE)
    accent = QColor(accent or theme.ACCENT)
    soft = QColor(line)
    soft.setAlpha(110)
    fill = QColor(accent)
    fill.setAlpha(90)
    p.setBrush(Qt.BrushStyle.NoBrush)
    b = brush_id
    if b == "pull":
        p.setPen(_pen(line))
        p.drawPath(_curve([(4, 24), (10, 24), (12, 14), (16, 14), (20, 14), (22, 24), (28, 24)]))
        _arrow(p, QPointF(16, 12), QPointF(16, 4), accent)
    elif b == "grab":
        p.setPen(_pen(line))
        p.drawPath(_curve([(4, 24), (12, 24), (14, 16), (20, 16), (24, 16), (24, 24), (28, 24)]))
        _arrow(p, QPointF(16, 10), QPointF(8, 10), accent)
        _arrow(p, QPointF(16, 10), QPointF(24, 10), accent)
        _arrow(p, QPointF(16, 10), QPointF(16, 2), accent)
    elif b == "smooth":
        p.setPen(_pen(soft))
        p.drawPath(_poly([(4, 14), (8, 10), (12, 16), (16, 8), (20, 16), (24, 10), (28, 14)]))
        p.setPen(_pen(accent))
        p.drawPath(_curve([(4, 22), (12, 18), (20, 26), (28, 22)]))
    elif b == "inflate":
        _flat(p, line, 26)
        p.setPen(_pen(line))
        p.drawEllipse(QPointF(16, 14), 8, 8)
        p.setPen(_pen(accent))
        for ang in (200, 250, 290, 340):
            r = math.radians(ang)
            p.drawLine(QPointF(16 + 10 * math.cos(r), 14 + 10 * math.sin(r)),
                       QPointF(16 + 12 * math.cos(r), 14 + 12 * math.sin(r)))
    elif b == "flatten":
        p.setPen(_pen(soft))
        p.drawPath(_curve([(4, 22), (10, 12), (14, 12), (16, 18), (20, 24), (24, 12), (28, 22)]))
        p.setPen(_pen(accent, 4.0))
        p.drawLine(QPointF(6, 18), QPointF(26, 18))
    elif b == "fill":
        dip = _curve([(4, 16), (10, 16), (12, 26), (16, 26), (20, 26), (22, 16), (28, 16)])
        area = QPainterPath(dip)
        area.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPath(area)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(line))
        p.drawPath(dip)
        _arrow(p, QPointF(16, 24), QPointF(16, 18), accent)
    elif b == "scrape":
        p.setPen(_pen(line))
        p.drawPath(_poly([(4, 24), (10, 24), (12, 16), (20, 16), (22, 24), (28, 24)]))
        p.setPen(_pen(soft, 2.0, dash=True))
        p.drawPath(_curve([(12, 16), (12, 8), (20, 8), (20, 16)]))
        p.setPen(_pen(accent))
        p.drawLine(QPointF(6, 14), QPointF(26, 14))
        p.drawLine(QPointF(26, 14), QPointF(26, 10))
    elif b == "pinch":
        p.setPen(_pen(line))
        p.drawPath(_poly([(4, 24), (12, 24), (16, 14), (20, 24), (28, 24)]))
        _arrow(p, QPointF(4, 10), QPointF(12, 10), accent)
        _arrow(p, QPointF(28, 10), QPointF(20, 10), accent)
    elif b == "crease":
        p.setPen(_pen(line))
        p.drawPath(_poly([(4, 18), (12, 18), (16, 26), (20, 18), (28, 18)]))
        blade = QPolygonF([QPointF(12, 4), QPointF(20, 4), QPointF(16, 14)])
        p.setPen(_pen(accent))
        p.setBrush(fill)
        p.drawPolygon(blade)
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif b == "polish":
        p.setPen(_pen(line))
        p.drawPath(_curve([(4, 24), (12, 20), (20, 20), (28, 24)]))
        star = QPainterPath(QPointF(16, 4))
        star.quadTo(QPointF(18, 10), QPointF(22, 12))
        star.quadTo(QPointF(18, 14), QPointF(16, 20))
        star.quadTo(QPointF(14, 14), QPointF(10, 12))
        star.quadTo(QPointF(14, 10), QPointF(16, 4))
        p.setPen(_pen(accent))
        p.setBrush(fill)
        p.drawPath(star)
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif b == "clay":
        _flat(p, line, 26)
        p.setPen(_pen(accent))
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(6, 18, 20, 4), 2, 2)
        p.drawRoundedRect(QRectF(8, 12, 16, 4), 2, 2)
        p.setPen(_pen(line))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(10, 6, 12, 4), 2, 2)
    elif b == "wax":
        p.setPen(_pen(line))
        p.drawPath(_curve([(4, 26), (10, 26), (12, 22), (16, 22), (20, 22), (22, 26), (28, 26)]))
        drop = QPainterPath(QPointF(16, 4))
        drop.cubicTo(QPointF(20, 10), QPointF(22, 14), QPointF(16, 18))
        drop.cubicTo(QPointF(10, 14), QPointF(12, 10), QPointF(16, 4))
        p.setPen(_pen(accent))
        p.setBrush(fill)
        p.drawPath(drop)
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif b == "amplify":
        p.setPen(_pen(soft))
        p.drawPath(_poly([(4, 18), (8, 16), (12, 20), (16, 16), (20, 20), (24, 16), (28, 18)]))
        p.setPen(_pen(accent))
        p.drawPath(_poly([(4, 18), (8, 10), (12, 26), (16, 10), (20, 26), (24, 10), (28, 18)]))
    elif b == "erase":
        _flat(p, line, 26)
        p.save()
        p.translate(16, 14)
        p.rotate(-30)
        p.setPen(_pen(line))
        p.drawRoundedRect(QRectF(-10, -6, 20, 12), 2, 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(2, -4, 6, 8), 2, 2)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif b == "mask":
        p.setPen(_pen(line))
        p.drawEllipse(QPointF(16, 16), 10, 10)
        half = QPainterPath()
        half.moveTo(16, 6)
        half.arcTo(QRectF(6, 6, 20, 20), 90, 180)
        half.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawPath(half)
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif b == "stamp":
        p.setPen(_pen(line))
        p.drawRoundedRect(QRectF(6, 14, 20, 10), 2, 2)
        p.drawLine(QPointF(16, 14), QPointF(16, 8))
        p.drawRoundedRect(QRectF(12, 4, 8, 4), 2, 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        for x in (10, 16, 22):
            p.drawEllipse(QPointF(x, 28), 2, 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
    else:
        p.setPen(_pen(line))
        p.drawEllipse(QPointF(16, 16), 10, 10)


def brush_pixmap(brush_id: str, size: int = 32, line=None, accent=None,
                 device_pixel_ratio: float = 1.0) -> QPixmap:
    dpr = max(1.0, float(device_pixel_ratio))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / ICON_GRID, size / ICON_GRID)
    paint_brush_icon(p, brush_id, line, accent)
    p.end()
    return pm


def brush_icon(brush_id: str, size: int = 32) -> QIcon:
    icon = QIcon()
    icon.addPixmap(brush_pixmap(brush_id, size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(brush_pixmap(brush_id, size, theme.TEXT_BRIGHT, theme.ACCENT_HOVER),
                   QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(brush_pixmap(brush_id, size, theme.TEXT_MUTED, theme.TEXT_MUTED),
                   QIcon.Mode.Disabled, QIcon.State.Off)
    return icon
