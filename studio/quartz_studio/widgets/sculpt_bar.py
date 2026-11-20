from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from quartz_studio import icons, theme
from quartz_studio.widgets.command_bar import (
    FLEX,
    GAP,
    Cmd,
    Gear,
    Item,
    PaletteStrip,
    solid,
    stroke,
    unit_painter,
)

__all__ = ["SculptBar", "SCULPT_BAR_ENTRIES", "SCULPT_BAR_HEIGHT", "SCULPT_ENABLED"]

SCULPT_BUTTON = 36
SCULPT_ICON = 31
SCULPT_GAP = 11
SCULPT_GEAR = 18
SCULPT_GEAR_ICON = 14
SCULPT_BAR_HEIGHT = 37
SCULPT_TOP_MARGIN = 1
SCULPT_LEFT_INSET = theme.PALETTE_W + 9

SCULPT_ENABLED = {"Project Mesh"}


ORANGE = theme.ICON_ACCENT_ORANGE
LIGHT = theme.ICON_STROKE
MARK_LIGHT = QColor(theme.ICON_STROKE)
MARK_LIGHT.setAlpha(235)
MARK_DARK = QColor(theme.SURFACE_FIELD)
MARK_DARK.setAlpha(200)
MARK_PEN = 1.4


def _ball(p: QPainter, c: QColor) -> QPainterPath:
    g = QRadialGradient(QPointF(9.0, 8.0), 14.0)
    g.setColorAt(0.0, QColor(c).lighter(135))
    g.setColorAt(0.55, QColor(c))
    g.setColorAt(1.0, QColor(c).darker(190))
    path = QPainterPath()
    path.addEllipse(QPointF(12, 12), 9.4, 9.4)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawPath(path)
    return path


BALL_SCALE = 7.8 / 9.4


def _brush(kind: str):
    def fn(p: QPainter, c: QColor) -> None:
        p.translate(12, 12)
        p.scale(BALL_SCALE, BALL_SCALE)
        p.translate(-12, -12)
        ball = _ball(p, c)
        if kind == "draw":
            stroke(p, ORANGE, 2.0)
            p.drawArc(QRectF(8.0, 3.2, 12.0, 12.0), -10 * 16, 110 * 16)
            stroke(p, LIGHT, 1.4)
            p.drawLine(QPointF(10.2, 13.6), QPointF(15.6, 8.2))
        elif kind == "wax":
            stroke(p, ORANGE, 3.0)
            p.drawArc(QRectF(4.4, 4.4, 15.2, 15.2), -40 * 16, 170 * 16)
        elif kind == "inflate":
            solid(p, ORANGE)
            bump = QPainterPath()
            bump.addEllipse(QPointF(16.2, 7.8), 5.0, 5.0)
            p.drawPath(bump.intersected(ball))
            stroke(p, QColor(c).darker(160), 1.0)
            p.drawArc(QRectF(11.2, 2.8, 10.0, 10.0), 180 * 16, 90 * 16)
        elif kind == "amplify":
            solid(p, ORANGE)
            p.drawPolygon(QPolygonF([QPointF(12.6, 9.4), QPointF(15.2, 2.6), QPointF(16.0, 7.4),
                                     QPointF(21.0, 4.4), QPointF(18.0, 9.6), QPointF(21.6, 11.4),
                                     QPointF(15.6, 12.2)]))
        elif kind == "knife":
            stroke(p, QColor(c).darker(220), 1.6)
            p.drawLine(QPointF(9.0, 15.0), QPointF(18.6, 5.4))
            stroke(p, LIGHT, 1.0)
            p.drawLine(QPointF(10.0, 16.0), QPointF(19.2, 6.8))
        elif kind == "repeat":
            p.save()
            p.setClipPath(ball)
            stroke(p, ORANGE, 1.3)
            for x in (14.4, 17.2, 20.0):
                p.drawArc(QRectF(x - 6.0, 2.0, 6.0, 20.0), -70 * 16, 140 * 16)
            p.restore()
        elif kind == "grab":
            piece = QPainterPath()
            piece.moveTo(12.6, 11.4)
            piece.lineTo(13.6, 2.4)
            piece.arcTo(QRectF(3.0, 2.6, 18.8, 18.8), 70, -62)
            piece.closeSubpath()
            piece.translate(1.2, -1.0)
            solid(p, MARK_LIGHT)
            p.drawPath(piece)
            stroke(p, MARK_DARK, MARK_PEN)
            p.drawLine(QPointF(13.8, 10.4), QPointF(14.8, 1.4))
        elif kind == "smooth":
            stroke(p, MARK_DARK, 2.6)
            p.drawArc(QRectF(7.4, 5.4, 11.0, 11.0), 70 * 16, 210 * 16)
            stroke(p, MARK_LIGHT, 1.8)
            p.drawArc(QRectF(7.4, 4.6, 11.0, 11.0), 70 * 16, 210 * 16)
        elif kind == "flatten":
            cut = QPainterPath()
            cut.moveTo(9.0, 2.0)
            cut.lineTo(22.0, 15.0)
            cut.lineTo(22.0, 2.0)
            cut.closeSubpath()
            solid(p, MARK_LIGHT)
            p.drawPath(cut.intersected(ball))
            stroke(p, MARK_DARK, MARK_PEN)
            p.drawLine(QPointF(9.6, 3.8), QPointF(20.6, 14.8))
        elif kind == "pinch":
            solid(p, QColor(c).darker(220))
            p.drawPolygon(QPolygonF([QPointF(12.6, 11.4), QPointF(14.2, 2.4), QPointF(21.4, 9.2)]))
            stroke(p, MARK_LIGHT, 1.8)
            p.drawLine(QPointF(12.6, 11.4), QPointF(17.6, 5.4))
        elif kind == "scrape":
            stroke(p, MARK_DARK, 1.2)
            p.drawEllipse(QPointF(12.6, 11.2), 6.6, 6.6)
            stroke(p, MARK_LIGHT, 1.7)
            p.drawEllipse(QPointF(12.6, 11.2), 5.2, 5.2)
            solid(p, MARK_LIGHT)
            p.drawEllipse(QPointF(12.6, 11.2), 1.8, 1.8)
        elif kind == "fill":
            wedge = QPainterPath()
            wedge.moveTo(12.4, 11.6)
            wedge.lineTo(12.4, 2.0)
            wedge.lineTo(22.0, 2.0)
            wedge.lineTo(22.0, 11.6)
            wedge.closeSubpath()
            solid(p, MARK_LIGHT)
            p.drawPath(wedge.intersected(ball))
            stroke(p, MARK_DARK, MARK_PEN)
            p.drawLine(QPointF(12.4, 11.6), QPointF(20.0, 6.0))
            p.drawLine(QPointF(12.4, 11.6), QPointF(12.4, 3.0))
    return fn


BRUSH_GREY = theme.ICON_STROKE
BRUSH_KINDS = ("draw", "wax", "inflate", "amplify", "knife", "repeat",
               "grab", "smooth", "flatten", "pinch", "scrape", "fill")


def register_brush_icons() -> None:
    for kind in BRUSH_KINDS:
        name = f"pal_brush_{kind}"
        if not icons.has(name):
            icons.register(name, unit_painter(_brush(kind)), BRUSH_GREY)


register_brush_icons()


def _btn(name: str, icon: str, **kw) -> Item:
    return Item(Cmd(name, icon), enabled=name in SCULPT_ENABLED, **kw)


_MASK = Cmd("Mask", "mask")

SCULPT_BAR_ENTRIES: list = [
    FLEX,
    _btn("Subdivide", "sculpt_subdivide"),
    Gear("Subdivide Settings", enabled=False),
    _btn("Decrease", "sculpt_decrease"),
    _btn("Increase", "sculpt_increase"),
    _btn("Unsubdivide", "sculpt_unsubdivide"),
    FLEX,
    _btn("Draw", "pal_brush_draw"),
    _btn("Wax", "pal_brush_wax"),
    _btn("Inflate", "pal_brush_inflate"),
    _btn("Amplify", "pal_brush_amplify"),
    _btn("Knife", "pal_brush_knife"),
    _btn("Repeat", "pal_brush_repeat"),
    GAP,
    _btn("Grab", "pal_brush_grab"),
    _btn("Smooth", "pal_brush_smooth"),
    _btn("Flatten", "pal_brush_flatten"),
    _btn("Pinch", "pal_brush_pinch"),
    _btn("Scrape", "pal_brush_scrape"),
    _btn("Fill", "pal_brush_fill"),
    GAP,
    _btn("Erase", "eraser"),
    _btn("Mask", "mask", foldout=[
        _MASK,
        Cmd("Invert Mask", "mask_invert"),
        Cmd("Clear Mask", "mask_clear"),
        Cmd("Hide Masked", "mask_hide"),
        Cmd("Show Masked", "mask_show"),
    ]),
    FLEX,
    _btn("Add Layer", "add_layer"),
    _btn("Add Folder", "add_folder"),
    GAP,
    _btn("Project Mesh", "project_mesh"),
    _btn("Bake Sculpt Objects", "bake"),
    _btn("Sculpt to Pose Morph", "pose_morph"),
    FLEX,
]


class SculptBar(PaletteStrip):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(SCULPT_BAR_ENTRIES, Qt.Orientation.Horizontal, parent,
                         button=SCULPT_BUTTON, icon=SCULPT_ICON, gap=SCULPT_GAP,
                         gear_length=SCULPT_GEAR, popup_side="above",
                         cross_align=Qt.AlignmentFlag.AlignBottom,
                         margins=(SCULPT_LEFT_INSET, SCULPT_TOP_MARGIN, 0, 0),
                         cell_dividers=True, gear_icon=SCULPT_GEAR_ICON)
        self.setObjectName("qsSculptBar")
        self.setFixedHeight(SCULPT_BAR_HEIGHT)
