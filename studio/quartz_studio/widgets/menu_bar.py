from __future__ import annotations

import importlib
import logging
import os
from functools import partial
from typing import Callable, Iterable

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
    QShortcut,
)
from PySide6.QtWidgets import QApplication, QMenu, QMenuBar, QSizePolicy, QWidget, QWidgetAction

from quartz_studio import fileio, icons, objects, project, theme
from quartz_studio.widgets import menus_data
from quartz_studio.widgets.common import header_font, not_implemented, prepare_popup

log = logging.getLogger("quartz_studio.menu_bar")

__all__ = ["MenuBar", "StudioMenu", "build_menu", "menu_font", "SCENE_COMMANDS", "SCENE_ENABLED",
           "create_line", "create_empty_polygon", "create_object", "make_editable",
           "can_make_editable", "object_menu_path"]


UI_POINT_SIZE = theme.FONT_POINT_SIZE
BAR_ITEM_PAD = theme.SPACE_2 + 2
BAR_LEFT_PAD = 0
BAR_ITEM_INSET = 3

MENU_ROW_H = theme.MENU_ROW_H
MENU_TOP_PAD = theme.SPACE_1
MENU_BOTTOM_PAD = theme.SPACE_1
MENU_INSET = theme.SPACE_1
MENU_ICON_COLUMN = theme.MENU_ROW_H
MENU_TEXT_X = MENU_INSET + MENU_ICON_COLUMN + theme.SPACE_1
MENU_ICON = theme.MENU_ICON
MENU_ICON_X = MENU_INSET + (MENU_ICON_COLUMN - MENU_ICON) // 2
MENU_SECTION_X = theme.SPACE_3
MENU_SECTION_H = theme.ROW_H
MENU_RIGHT_PAD = 32
MENU_RIGHT_COL = 18
MENU_SHORTCUT_R = 32
MENU_POPOUT_W = 28
MENU_POPOUT_CX = 22
MENU_BADGE_PAD = 3
OVERFLOW_LABEL = "More Menus"
OVERFLOW_ICON = 16


def menu_font(bold: bool = False, point_size: float = UI_POINT_SIZE) -> QFont:
    f = QFont(theme.FONT_FAMILY)
    f.setPointSizeF(point_size)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


def _menu_qss() -> str:
    return f"""
QMenu {{
    background: transparent;
    border: 1px solid {theme.HAIRLINE};
    padding: {MENU_TOP_PAD}px 0px {MENU_BOTTOM_PAD}px 0px;
    font-size: {UI_POINT_SIZE}pt;
}}
QMenu::item {{
    min-height: {MENU_ROW_H}px;
    padding: 0px {MENU_RIGHT_PAD}px 0px {MENU_TEXT_X}px;
    margin: 0px;
    border: none;
}}
QMenu::separator {{
    height: 1px;
    margin: {theme.SPACE_1}px 0px;
}}
"""


def _soft(c, alpha: int = 64) -> QColor:
    out = QColor(c)
    out.setAlpha(alpha)
    return out



def _unit(fn: Callable[[QPainter, QColor], None]):
    def wrapped(p: QPainter, r: QRectF, c: QColor) -> None:
        p.save()
        side = min(r.width(), r.height())
        p.translate(r.x() + (r.width() - side) / 2, r.y() + (r.height() - side) / 2)
        p.scale(side / 24.0, side / 24.0)
        fn(p, c)
        p.restore()
    return wrapped


def _pen(p: QPainter, c, w: float = 1.6) -> None:
    p.setPen(QPen(QColor(c), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)


def _fill(p: QPainter, c) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))


def _poly(*pts) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _i_fullscreen(p, c):
    _pen(p, c, 1.7)
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        x0, y0 = 12 - sx * 8, 12 - sy * 8
        p.drawPolyline(_poly((x0, y0 + sy * 4), (x0, y0), (x0 + sx * 4, y0)))


def _i_asset_browser(p, c):
    _pen(p, c, 1.6)
    p.drawRect(QRectF(4.5, 5, 15, 4.5))
    p.drawPolyline(_poly((5.5, 9.5), (5.5, 19), (18.5, 19), (18.5, 9.5)))
    p.drawLine(QPointF(9.5, 12.5), QPointF(14.5, 12.5))


def _i_asset_inspector(p, c):
    _pen(p, c, 1.5)
    p.drawRoundedRect(QRectF(3.5, 6, 17, 12.5), 1.5, 1.5)
    p.drawLine(QPointF(3.5, 9), QPointF(20.5, 9))
    p.drawRect(QRectF(6.5, 11.5, 4.5, 4))
    p.drawLine(QPointF(13, 12.5), QPointF(18, 12.5))
    p.drawLine(QPointF(13, 15), QPointF(16.5, 15))


def _i_object_manager(p, c):
    _pen(p, c, 1.6)
    p.drawRoundedRect(QRectF(4, 4.5, 16, 4.5), 1.5, 1.5)
    p.drawRoundedRect(QRectF(8, 10.5, 12, 4), 1.5, 1.5)
    p.drawRoundedRect(QRectF(8, 16, 12, 4), 1.5, 1.5)
    _fill(p, theme.TINT_MINT)
    p.drawEllipse(QPointF(5, 14.5), 1.5, 1.5)
    p.drawEllipse(QPointF(5, 18), 1.5, 1.5)


def _i_profiler(p, c):
    _pen(p, c, 1.6)
    p.drawEllipse(QPointF(12, 13.5), 7, 7)
    p.drawLine(QPointF(12, 13.5), QPointF(12, 9.5))
    p.drawLine(QPointF(10, 3.8), QPointF(14, 3.8))
    p.drawLine(QPointF(12, 3.8), QPointF(12, 6.5))


def _i_node_editor(p, c):
    _pen(p, c, 1.4)
    p.drawRect(QRectF(3, 4, 6, 5))
    p.drawRect(QRectF(15, 13, 6, 5))
    p.drawRect(QRectF(3, 15, 6, 5))
    path = QPainterPath(QPointF(9, 6.5))
    path.cubicTo(QPointF(13, 6.5), QPointF(11, 15.5), QPointF(15, 15.5))
    p.drawPath(path)
    p.drawLine(QPointF(9, 17.5), QPointF(15, 16.5))


def _i_attribute_manager(p, c):
    _pen(p, c, 1.6)
    p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2.5, 2.5)
    for y in (8.5, 12, 15.5):
        p.drawLine(QPointF(6.5, y), QPointF(9.5, y))
    p.drawLine(QPointF(12, 12), QPointF(17.5, 12))
    p.drawLine(QPointF(12, 15.5), QPointF(17.5, 15.5))
    _pen(p, theme.TINT_MINT, 1.6)
    p.drawLine(QPointF(12, 8.5), QPointF(17.5, 8.5))


def _i_task_manager(p, c):
    _pen(p, c, 1.6)
    p.drawEllipse(QPointF(12, 12), 8, 8)
    p.drawPolyline(_poly((8.2, 12.3), (11, 15), (16, 9.2)))


def _i_material_manager(p, c):
    _pen(p, c, 1.7)
    p.drawArc(QRectF(4.5, 5.5, 14, 14), 40 * 16, 280 * 16)
    p.drawArc(QRectF(8.5, 9.5, 6, 6), 40 * 16, 280 * 16)
    _fill(p, theme.TINT_MINT)
    p.drawEllipse(QPointF(17.5, 5.5), 2.3, 2.3)


def _i_material_editor(p, c):
    _pen(p, c, 1.7)
    p.drawArc(QRectF(4.5, 5, 14, 14), 40 * 16, 280 * 16)
    p.drawArc(QRectF(8.5, 9, 6, 6), 40 * 16, 280 * 16)
    p.drawLine(QPointF(13, 13), QPointF(19.5, 6.5))


def _i_timeline_dope(p, c):
    _pen(p, c, 1.6)
    p.drawPolygon(_poly((12, 4.5), (19.5, 12), (12, 19.5), (4.5, 12)))


def _i_timeline_curve(p, c):
    _pen(p, c, 1.6)
    p.drawPolyline(_poly((3, 13), (7, 13), (9.5, 5), (13.5, 19), (16, 10), (18, 13), (21, 13)))


def _i_coordinates(p, c):
    _pen(p, c, 1.6)
    p.drawLine(QPointF(6, 4), QPointF(6, 18))
    p.drawLine(QPointF(6, 18), QPointF(20, 18))
    p.drawLine(QPointF(6, 18), QPointF(15, 9))
    _fill(p, c)
    p.drawPolygon(_poly((6, 3), (3.8, 7), (8.2, 7)))
    p.drawPolygon(_poly((21, 18), (17, 15.8), (17, 20.2)))
    p.drawPolygon(_poly((16.5, 7.5), (12.4, 8.7), (15.3, 11.6)))


def _i_structure(p, c):
    _pen(p, c, 1.5)
    for v in (8, 12.5, 17):
        p.drawLine(QPointF(v, 4), QPointF(v, 20))
        p.drawLine(QPointF(4, v), QPointF(20, v))


def _i_sculpt_layers(p, c):
    _pen(p, c, 2.6)
    p.drawLine(QPointF(5, 19), QPointF(14, 10))
    _fill(p, c)
    p.drawEllipse(QPointF(16.5, 7.5), 3.6, 3.6)


def _i_take_manager(p, c):
    _pen(p, c, 1.6)
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    _fill(p, c)
    for dx, dy in ((0, -4.4), (4.2, -1.3), (2.6, 3.6), (-2.6, 3.6), (-4.2, -1.3)):
        p.drawEllipse(QPointF(12 + dx, 12 + dy), 1.3, 1.3)


def _i_picture_viewer(p, c):
    _pen(p, c, 1.6)
    p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 1.5, 1.5)
    _fill(p, c)
    p.drawPolygon(_poly((10, 8.8), (15.5, 12), (10, 15.2)))


def _i_uv_editor(p, c):
    _pen(p, c, 1.5)
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 1.5, 1.5)
    _fill(p, c)
    p.drawPolygon(_poly((6.5, 17.5), (10.5, 11.5), (13.5, 15), (15.5, 13), (17.5, 17.5)))
    p.drawEllipse(QPointF(15.5, 8.5), 1.6, 1.6)


def _i_color_settings(p, c):
    _pen(p, c, 1.5)
    path = QPainterPath(QPointF(12, 4))
    path.cubicTo(QPointF(4, 4), QPointF(2.5, 14), QPointF(7, 18))
    path.cubicTo(QPointF(10, 20.5), QPointF(12, 18), QPointF(13, 16))
    path.cubicTo(QPointF(14, 14), QPointF(20.5, 16), QPointF(20.5, 11))
    path.cubicTo(QPointF(20.5, 6.5), QPointF(16.5, 4), QPointF(12, 4))
    p.drawPath(path)
    _fill(p, c)
    for x, y in ((8, 10), (11.5, 7.5), (15.5, 8.5)):
        p.drawEllipse(QPointF(x, y), 1.3, 1.3)


def _i_uv_layers(p, c):
    _pen(p, c, 1.6)
    p.drawRoundedRect(QRectF(8, 3.5, 12.5, 12.5), 2, 2)
    p.setBrush(_soft(c))
    p.drawRoundedRect(QRectF(3.5, 8, 12.5, 12.5), 2, 2)


def _i_projection(p, c):
    _pen(p, c, 1.4)
    p.drawRect(QRectF(4, 6, 16, 12))
    _fill(p, c)
    p.drawPolygon(_poly((5.5, 16.5), (9.5, 11), (12.5, 14), (14.5, 12.5), (18.5, 16.5)))
    p.drawEllipse(QPointF(15.5, 9), 1.4, 1.4)


def _i_xref(p, c):
    _pen(p, c, 1.6)
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2)
    p.drawLine(QPointF(8.5, 8.5), QPointF(15.5, 15.5))
    p.drawLine(QPointF(15.5, 8.5), QPointF(8.5, 15.5))


def _i_bake_alembic(p, c):
    _pen(p, c, 1.6)
    p.drawRoundedRect(QRectF(4, 5, 16, 15), 1.5, 1.5)
    p.drawLine(QPointF(4, 9.5), QPointF(20, 9.5))
    p.drawLine(QPointF(8, 3), QPointF(8, 6.5))
    p.drawLine(QPointF(16, 3), QPointF(16, 6.5))
    _fill(p, theme.TINT_MINT)
    p.drawRect(QRectF(7, 12, 3, 3))
    p.drawRect(QRectF(11, 12, 3, 3))


def _i_bake_set(p, c):
    _pen(p, c, 1.6)
    p.drawRoundedRect(QRectF(4, 5, 16, 14), 1.5, 1.5)
    _fill(p, c)
    p.drawRect(QRectF(4, 5, 16, 4))


def _i_proxy(p, c):
    _pen(p, c, 1.7)
    p.save()
    p.translate(12, 12)
    p.rotate(-45)
    p.drawRoundedRect(QRectF(-3.5, -9, 7, 14), 3.5, 3.5)
    p.drawRoundedRect(QRectF(-1.5, -5.5, 3, 12.5), 1.5, 1.5)
    p.restore()


def _i_mode_object(p, c):
    _pen(p, c, 1.6)
    p.setBrush(QColor(theme.TINT_MINT))
    p.drawPolygon(_poly((12, 3.5), (19.5, 7.5), (12, 11.5), (4.5, 7.5)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(_poly((4.5, 7.5), (12, 11.5), (12, 20.5), (4.5, 16.5)))
    p.drawPolygon(_poly((12, 11.5), (19.5, 7.5), (19.5, 16.5), (12, 20.5)))


def _i_mode_animation(p, c):
    _pen(p, c, 1.6)
    p.drawRoundedRect(QRectF(4.5, 4, 15, 16), 1.5, 1.5)
    p.drawRect(QRectF(9.5, 7, 5, 10))
    _fill(p, c)
    for y in (6.5, 10, 14, 17.5):
        p.drawRect(QRectF(5.8, y - 0.8, 2, 1.6))
        p.drawRect(QRectF(16.2, y - 0.8, 2, 1.6))


def _i_mode_texture(p, c):
    _pen(p, c, 1.6)
    p.drawEllipse(QPointF(11, 12.5), 7.5, 7.5)
    _fill(p, c)
    for x, y in ((8.5, 9.5), (13, 10), (9.5, 15)):
        p.drawEllipse(QPointF(x, y), 1.3, 1.3)
    p.drawRect(QRectF(15, 14, 6, 6))


def _i_mode_uv(p, c):
    _pen(p, c, 1.4)
    p.drawRect(QRectF(4, 4, 16, 16))
    p.drawLine(QPointF(12, 4), QPointF(12, 20))
    p.drawLine(QPointF(4, 12), QPointF(20, 12))


def _i_snap(p, c):
    _pen(p, c, 1.4)
    for v in (7, 12, 17):
        p.drawLine(QPointF(v, 3.5), QPointF(v, 20.5))
        p.drawLine(QPointF(3.5, v), QPointF(20.5, v))
    _fill(p, theme.TINT_MINT)
    p.drawEllipse(QPointF(12, 12), 2.6, 2.6)


def _i_modeling_settings(p, c):
    _pen(p, c, 1.6)
    p.drawLine(QPointF(12, 3.5), QPointF(12, 8))
    _fill(p, c)
    p.drawPolygon(_poly((12, 2.5), (9.8, 6), (14.2, 6)))
    _pen(p, c, 1.6)
    p.drawEllipse(QPointF(12, 14.5), 6, 6)
    _fill(p, c)
    p.drawEllipse(QPointF(12, 14.5), 1.6, 1.6)


def _i_workplane(p, c):
    _pen(p, c, 1.6)
    p.drawLine(QPointF(7, 4), QPointF(7, 20))
    p.drawLine(QPointF(17, 4), QPointF(17, 20))
    p.drawLine(QPointF(4, 7.5), QPointF(20, 7.5))
    p.drawLine(QPointF(4, 16.5), QPointF(20, 16.5))


def _i_symmetry_settings(p, c):
    _pen(p, c, 1.8)
    p.drawArc(QRectF(3.5, 4.5, 8, 15), 100 * 16, 160 * 16)
    _pen(p, c, 1.6)
    p.drawEllipse(QPointF(15, 12), 4.8, 4.8)
    _fill(p, c)
    p.drawEllipse(QPointF(15, 12), 1.5, 1.5)


def _i_normal_edit(p, c):
    _pen(p, c, 1.6)
    p.drawLine(QPointF(4, 19.5), QPointF(20, 19.5))
    for x in (7.5, 16.5):
        p.drawLine(QPointF(x, 19.5), QPointF(x, 6))
        p.drawPolyline(_poly((x - 2.5, 8.5), (x, 5.5), (x + 2.5, 8.5)))
    p.drawLine(QPointF(7.5, 12), QPointF(16.5, 12))


def _i_solo(p, c):
    _pen(p, c, 1.5)
    p.drawEllipse(QPointF(12, 12), 8, 8)
    _fill(p, c)
    p.drawRoundedRect(QRectF(8, 9.5, 8, 5), 2.5, 2.5)


def _i_solo_hierarchy(p, c):
    _pen(p, c, 1.5)
    p.drawEllipse(QPointF(12, 12), 8, 8)
    p.drawLine(QPointF(9, 8.5), QPointF(15, 8.5))
    p.drawLine(QPointF(9, 12), QPointF(15, 12))
    p.drawLine(QPointF(9, 15.5), QPointF(15, 15.5))


def _i_solo_auto(p, c):
    _pen(p, c, 1.5)
    p.drawEllipse(QPointF(12, 12), 8, 8)
    p.drawPolyline(_poly((8.5, 16.5), (12, 7.5), (15.5, 16.5)))
    p.drawLine(QPointF(9.8, 13.3), QPointF(14.2, 13.3))


def _i_reset_transform(p, c):
    _pen(p, c, 1.6)
    p.drawArc(QRectF(5, 5, 14, 14), 60 * 16, 270 * 16)
    _fill(p, c)
    p.drawPolygon(_poly((15.5, 3.5), (16.5, 8.5), (12, 7)))


def _i_freeze(p, c):
    _pen(p, c, 1.5)
    for a in (0, 60, 120):
        p.save()
        p.translate(12, 12)
        p.rotate(a)
        p.drawLine(QPointF(0, -8.5), QPointF(0, 8.5))
        p.drawPolyline(_poly((-2.5, -7), (0, -4.8), (2.5, -7)))
        p.drawPolyline(_poly((-2.5, 7), (0, 4.8), (2.5, 7)))
        p.restore()


def _i_unfreeze(p, c):
    _i_freeze(p, c)
    _pen(p, c, 1.6)
    p.drawLine(QPointF(5, 19), QPointF(19, 5))


def _i_arrange(p, c):
    _fill(p, c)
    p.drawRect(QRectF(4, 5, 5, 5))
    p.drawRect(QRectF(13, 14, 5, 5))
    _pen(p, c, 1.4)
    p.drawPolyline(_poly((9, 7.5), (15.5, 7.5), (15.5, 12)))


def _i_center(p, c):
    _pen(p, c, 1.6)
    p.drawLine(QPointF(4, 20), QPointF(20, 20))
    p.drawLine(QPointF(12, 4), QPointF(12, 20))
    _fill(p, c)
    p.drawRect(QRectF(5, 9, 5, 7))
    p.drawRect(QRectF(14, 11, 5, 5))


def _i_duplicate(p, c):
    _fill(p, c)
    p.drawRect(QRectF(4, 4, 6, 6))
    p.drawRect(QRectF(14, 14, 6, 6))
    _fill(p, theme.TINT_MINT)
    p.drawRect(QRectF(9, 9, 6, 6))


def _i_transfer(p, c):
    _pen(p, c, 1.5)
    p.drawRect(QRectF(4, 4, 6, 6))
    p.drawRect(QRectF(14, 14, 6, 6))
    p.drawLine(QPointF(10, 7), QPointF(17, 7))
    p.drawLine(QPointF(17, 7), QPointF(17, 14))


def _i_randomize(p, c):
    _pen(p, c, 1.5)
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
    _fill(p, c)
    for x, y in ((8, 8), (16, 8), (12, 12), (8, 16), (16, 16)):
        p.drawEllipse(QPointF(x, y), 1.4, 1.4)


def _i_replace(p, c):
    _pen(p, c, 1.5)
    p.drawRect(QRectF(4, 4, 11, 11))
    p.drawRect(QRectF(9, 9, 11, 11))


def _i_project_object(p, c):
    _pen(p, c, 1.5)
    p.drawRect(QRectF(3.5, 6, 13, 11))
    p.drawPolyline(_poly((16.5, 9), (20.5, 6.5), (20.5, 16.5), (16.5, 14)))


def _i_naming(p, c):
    _pen(p, c, 2.0)
    p.drawLine(QPointF(5, 5), QPointF(19, 5))
    p.drawLine(QPointF(12, 5), QPointF(12, 20))
    p.drawLine(QPointF(9, 20), QPointF(15, 20))


def _i_annotation(p, c):
    _pen(p, c, 1.6)
    p.drawPolyline(_poly((14, 20), (4.5, 20), (4.5, 4), (19.5, 4), (19.5, 14.5), (14, 20), (14, 14.5),
                         (19.5, 14.5)))
    p.drawLine(QPointF(8, 8.5), QPointF(16, 8.5))
    p.drawLine(QPointF(8, 12), QPointF(13, 12))


def _i_line(p, c):
    _pen(p, c, 1.7)
    p.drawPolyline(_poly((3.5, 18.5), (10, 12), (19.5, 15.5)))
    p.drawLine(QPointF(10, 12), QPointF(15, 4.5))
    _fill(p, theme.TINT_ROSE)
    for x, y in ((3.5, 18.5), (10, 12), (19.5, 15.5), (15, 4.5)):
        p.drawEllipse(QPointF(x, y), 1.9, 1.9)


def _i_effector(p, c):
    _pen(p, c, 1.6)
    p.drawEllipse(QPointF(12, 12), 7.5, 7.5)
    _fill(p, theme.TINT_AMETHYST)
    p.drawPolygon(_poly((12, 6.5), (16.5, 15), (7.5, 15)))


_MENU_ICONS: dict[str, tuple[Callable, str | None]] = {
    "m_fullscreen": (_i_fullscreen, None),
    "m_asset_browser": (_i_asset_browser, None),
    "m_asset_inspector": (_i_asset_inspector, None),
    "m_object_manager": (_i_object_manager, None),
    "m_profiler": (_i_profiler, None),
    "m_node_editor": (_i_node_editor, None),
    "m_attribute_manager": (_i_attribute_manager, None),
    "m_task_manager": (_i_task_manager, None),
    "m_material_manager": (_i_material_manager, None),
    "m_material_editor": (_i_material_editor, None),
    "m_timeline_dope": (_i_timeline_dope, None),
    "m_timeline_curve": (_i_timeline_curve, None),
    "m_coordinates": (_i_coordinates, None),
    "m_structure": (_i_structure, None),
    "m_sculpt_layers": (_i_sculpt_layers, None),
    "m_take_manager": (_i_take_manager, None),
    "m_picture_viewer": (_i_picture_viewer, None),
    "m_uv_editor": (_i_uv_editor, None),
    "m_color_settings": (_i_color_settings, None),
    "m_uv_layers": (_i_uv_layers, None),
    "m_projection": (_i_projection, None),
    "m_xref": (_i_xref, None),
    "m_bake_alembic": (_i_bake_alembic, None),
    "m_bake_set": (_i_bake_set, None),
    "m_proxy": (_i_proxy, None),
    "m_mode_object": (_i_mode_object, None),
    "m_mode_animation": (_i_mode_animation, None),
    "m_mode_texture": (_i_mode_texture, None),
    "m_mode_uv": (_i_mode_uv, None),
    "m_snap": (_i_snap, None),
    "m_modeling_settings": (_i_modeling_settings, None),
    "m_workplane": (_i_workplane, None),
    "m_symmetry_settings": (_i_symmetry_settings, None),
    "m_normal_edit": (_i_normal_edit, None),
    "m_solo": (_i_solo, None),
    "m_solo_hierarchy": (_i_solo_hierarchy, None),
    "m_solo_auto": (_i_solo_auto, None),
    "m_reset_transform": (_i_reset_transform, None),
    "m_freeze": (_i_freeze, None),
    "m_unfreeze": (_i_unfreeze, None),
    "m_arrange": (_i_arrange, None),
    "m_center": (_i_center, None),
    "m_duplicate": (_i_duplicate, None),
    "m_transfer": (_i_transfer, None),
    "m_randomize": (_i_randomize, None),
    "m_replace": (_i_replace, None),
    "m_project_object": (_i_project_object, None),
    "m_naming": (_i_naming, None),
    "m_annotation": (_i_annotation, None),
    "m_effector": (_i_effector, None),
    "m_line": (_i_line, None),
}


def register_menu_icons() -> None:
    for name, (fn, color) in _MENU_ICONS.items():
        if not icons.has(name):
            icons.register(name, _unit(fn), color)


register_menu_icons()



P_KIND = "qs_kind"
P_ICON = "qs_icon"
P_SHORTCUT = "qs_shortcut"
P_LABEL = "qs_label"


def _flag(action: QAction, name: str) -> bool:
    return bool(action.property("qs_" + name))


class _SectionLabel(QWidget):

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._font = header_font(menu_font())
        self.setFixedHeight(MENU_SECTION_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def title(self) -> str:
        return self._title

    def sizeHint(self) -> QSize:
        w = QFontMetrics(self._font).horizontalAdvance(self._title)
        return QSize(MENU_SECTION_X + w + MENU_SECTION_X, MENU_SECTION_H)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setFont(self._font)
        p.setPen(QColor(theme.TEXT_SECONDARY))
        p.drawText(QRect(MENU_SECTION_X, 4, self.width() - MENU_SECTION_X, self.height() - 4),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title)
        p.end()


class StudioMenu(QMenu):

    commandTriggered = Signal(str)

    def __init__(self, title: str = "", parent: QWidget | None = None,
                 entries: Iterable | None = None) -> None:
        super().__init__(title, parent)
        prepare_popup(self)
        self.setStyleSheet(_menu_qss())
        self.setFont(menu_font())
        self.setSeparatorsCollapsible(False)
        self._has_popout = False
        self._handlers: dict[QAction, Callable[[], object]] = {}
        if entries is not None:
            self.populate(entries)

    def populate(self, entries: Iterable) -> "StudioMenu":
        for entry in entries:
            if isinstance(entry, str):
                entry = ("item", entry)
            kind = entry[0]
            if kind == "sep":
                self.addSeparator()
            elif kind == "section":
                self.add_section(entry[1])
            elif kind == "submenu":
                text, children = entry[1], entry[2]
                icon_name = entry[3] if len(entry) > 3 else None
                enabled = entry[4] if len(entry) > 4 else True
                flags = entry[5] if len(entry) > 5 else {}
                self.add_submenu(text, children, icon_name, enabled, **flags)
            elif kind == "item":
                text = entry[1]
                shortcut = entry[2] if len(entry) > 2 else None
                icon_name = entry[3] if len(entry) > 3 else None
                enabled = entry[4] if len(entry) > 4 else True
                flags = entry[5] if len(entry) > 5 else {}
                self.add_item(text, shortcut, icon_name, enabled, **flags)
            else:
                log.warning("unknown menu entry %r", entry)
        return self

    def add_section(self, title: str) -> QWidgetAction:
        act = QWidgetAction(self)
        act.setText(title)
        act.setDefaultWidget(_SectionLabel(title))
        act.setEnabled(False)
        act.setProperty(P_KIND, "section")
        act.setProperty(P_LABEL, title)
        self.addAction(act)
        return act

    def add_item(self, text: str, shortcut: str | None = None, icon_name: str | None = None,
                 enabled: bool = True, **flags) -> QAction:
        act = QAction(f"{text}\t{shortcut}" if shortcut else text, self)
        act.setProperty(P_KIND, "item")
        act.setProperty(P_LABEL, text)
        act.setProperty(P_SHORTCUT, shortcut or "")
        act.setProperty(P_ICON, icon_name or "")
        for key, value in flags.items():
            act.setProperty("qs_" + key, bool(value))
        if flags.get("popout"):
            self._has_popout = True
        act.setEnabled(bool(enabled))
        act.setStatusTip(text)
        act.triggered.connect(lambda _=False, a=act, t=text: self._on_triggered(t, a))
        self.addAction(act)
        return act

    def add_submenu(self, text: str, entries: Iterable, icon_name: str | None = None,
                    enabled: bool = True, **flags) -> "StudioMenu":
        sub = StudioMenu(text, self, entries)
        sub.commandTriggered.connect(self.commandTriggered)
        act = self.addMenu(sub)
        act.setProperty(P_KIND, "submenu")
        act.setProperty(P_LABEL, text)
        act.setProperty(P_ICON, icon_name or "")
        for key, value in flags.items():
            act.setProperty("qs_" + key, bool(value))
        act.setEnabled(bool(enabled))
        return sub

    def _on_triggered(self, text: str, action: QAction | None = None) -> None:
        handler = self._handlers.get(action) if action is not None else None
        if handler is not None:
            handler()
        else:
            not_implemented(text)
        self.commandTriggered.emit(text)

    def bind(self, label: str, handler: Callable[[], object]) -> QAction | None:
        act = self.find_action(label)
        if act is None:
            log.warning("menu item %r not found in %r", label, self.title())
            return None
        self._handlers[act] = handler
        return act

    def find_action(self, label: str) -> QAction | None:
        return next((a for a in self.actions()
                     if not a.isSeparator() and (a.property(P_LABEL) or a.text()) == label), None)

    def submenu(self, label: str) -> "StudioMenu | None":
        act = self.find_action(label)
        menu = act.menu() if act is not None else None
        return menu if isinstance(menu, StudioMenu) else None

    def is_wired(self, label: str) -> bool:
        act = self.find_action(label)
        return act is not None and act in self._handlers

    def prune_unwired(self) -> bool:
        for act in list(self.actions()):
            if act.isSeparator() or act.property(P_KIND) == "section":
                continue
            sub = act.menu()
            if isinstance(sub, StudioMenu):
                if not sub.prune_unwired():
                    self.removeAction(act)
            elif act not in self._handlers:
                self.removeAction(act)
        remaining = self.actions()
        for i, act in enumerate(remaining):
            if act.property(P_KIND) != "section":
                continue
            following = remaining[i + 1] if i + 1 < len(remaining) else None
            if (following is None or following.isSeparator()
                    or following.property(P_KIND) == "section"):
                self.removeAction(act)
        sections = [a for a in self.actions() if a.property(P_KIND) == "section"]
        if len(sections) == 1:
            self.removeAction(sections[0])
        previous_sep = True
        for act in list(self.actions()):
            if act.isSeparator() and previous_sep:
                self.removeAction(act)
            else:
                previous_sep = act.isSeparator()
        acts = self.actions()
        if acts and acts[-1].isSeparator():
            self.removeAction(acts[-1])
        return any(not a.isSeparator() and a.property(P_KIND) != "section"
                   for a in self.actions())

    def entries_text(self) -> list[str]:
        out = []
        for act in self.actions():
            if act.isSeparator():
                out.append("---")
            else:
                out.append(act.property(P_LABEL) or act.text())
        return out

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        w, h = self.width(), self.height()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QPen(QColor(theme.HAIRLINE), 1))
        p.setBrush(QColor(theme.SURFACE_MENU))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), theme.MENU_RADIUS, theme.MENU_RADIUS)
        clip = e.rect()
        active = self.activeAction()
        for act in self.actions():
            if not act.isVisible():
                continue
            r = self.actionGeometry(act)
            if r.isEmpty() or not r.intersects(clip):
                continue
            if act.isSeparator():
                p.fillRect(QRect(r.x() - 1 + theme.SPACE_2, r.center().y(),
                                 r.width() + 2 - 2 * theme.SPACE_2, 1), QColor(theme.HAIRLINE))
                continue
            if (act.property(P_KIND) or "item") == "section":
                continue
            self._paint_item(p, act, r, act is active)
        p.end()

    def _paint_item(self, p: QPainter, act: QAction, r: QRect, hover: bool) -> None:
        ox = r.x() - 1
        w = r.width() + 2
        enabled = act.isEnabled()
        popout = _flag(act, "popout")
        hover = hover and enabled
        cy = r.y() + r.height() / 2.0
        if hover:
            right = w - MENU_POPOUT_W - MENU_INSET if popout else w - MENU_INSET
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.ACCENT_TINT_MENU))
            p.drawRoundedRect(QRectF(ox + MENU_INSET, r.y(), right - MENU_INSET, r.height()),
                              theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)

        icon_rect = QRectF(ox + MENU_ICON_X, cy - MENU_ICON / 2.0, MENU_ICON, MENU_ICON)
        checked = _flag(act, "checked")
        if checked:
            p.save()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.ACCENT_TINT_HOVER if hover else theme.ACCENT_TINT_MENU))
            p.drawRoundedRect(icon_rect.adjusted(-MENU_BADGE_PAD, -MENU_BADGE_PAD,
                                                 MENU_BADGE_PAD, MENU_BADGE_PAD),
                              theme.CONTROL_RADIUS - 1, theme.CONTROL_RADIUS - 1)
            p.restore()
        icon_name = act.property(P_ICON)
        if icon_name:
            icons.render(p, icon_rect, icon_name, theme.ACCENT if checked and enabled else None,
                         disabled=not enabled)
        elif _flag(act, "check"):
            icons.render(p, icon_rect.adjusted(2, 2, -2, -2), "check",
                         theme.ACCENT if enabled else theme.TEXT_MUTED)

        if not enabled:
            col = theme.TEXT_MUTED
        elif hover:
            col = theme.TEXT_BRIGHT
        else:
            col = theme.TEXT_PRIMARY
        p.setFont(self.font())
        p.setPen(QColor(col))
        text_r = QRect(ox + MENU_TEXT_X, r.y(), w - MENU_TEXT_X - MENU_SHORTCUT_R, r.height())
        p.drawText(text_r, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   act.property(P_LABEL) or act.text())

        shortcut = act.property(P_SHORTCUT)
        if shortcut:
            p.setPen(QColor(theme.TEXT_SECONDARY if enabled else theme.TEXT_MUTED))
            p.drawText(text_r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, shortcut)

        cx = ox + w - MENU_RIGHT_COL
        if act.menu() is not None:
            icons.render(p, QRectF(cx - 5.5, cy - 5.5, 11, 11), "chevron_right",
                         theme.ICON_STROKE if enabled else theme.TEXT_MUTED)
        elif _flag(act, "gear"):
            icons.render(p, QRectF(cx - 8, cy - 8, 16, 16), "gear", theme.ICON_STROKE,
                         disabled=not enabled)
        elif popout:
            px = ox + w - MENU_POPOUT_CX
            icons.render(p, QRectF(px - 8.5, cy - 8.5, 17, 17), "popout", theme.ICON_STROKE,
                         disabled=not enabled)


def build_menu(entries: Iterable, parent: QWidget | None = None, title: str = "") -> StudioMenu:
    return StudioMenu(title, parent, entries)



def _scene():
    from quartz_studio.scene import get_scene

    return get_scene()


def create_line() -> None:
    scene = _scene()
    scene.new_line_object()
    scene.set_tool("line_pen")


def create_empty_polygon() -> None:
    _scene().add_object("Polygon")


def create_object(spec_id: str, modifiers=None):
    from quartz_studio import controls

    scene = _scene()
    spec = objects.get(spec_id)
    mods = QApplication.keyboardModifiers() if modifiers is None else modifiers
    active = scene.active if scene.active in scene.objects else None
    parent = adopt = None
    if active is not None:
        if spec.inputs == "children" and controls.modifier_held(mods, "create_adopt"):
            adopt = active
        elif controls.modifier_held(mods, "create_child"):
            parent = active
    return scene.add_parametric(spec_id, parent=parent, adopt=adopt)


def can_make_editable() -> bool:
    scene = _scene()
    obj = scene.active
    if obj is None or obj not in scene.objects or scene.is_editable(obj):
        return False
    spec = scene._spec(obj.kind)
    return spec is not None and spec.category != "null"


def make_editable() -> None:
    scene = _scene()
    if can_make_editable():
        scene.make_editable(scene.active)


def polygon_pen() -> None:
    _scene().set_tool("pen")


def undo() -> None:
    _scene().undo()


def redo() -> None:
    _scene().redo()


def open_controls() -> None:
    from quartz_studio import controls

    controls.run("app.controls")


def _control_actions():
    return importlib.import_module("quartz_studio.controls.actions")


def _trigger_path(path: tuple[str, ...], fallback: QAction) -> None:
    from quartz_studio import controls

    bar = getattr(controls.window(), "menu_bar", None)
    act = bar.action_at(path) if isinstance(bar, MenuBar) else None
    if act is None:
        try:
            act = fallback if fallback.parent() is not None else None
        except RuntimeError:
            act = None
    if act is not None:
        act.trigger()


def _menu_action_id(path: Iterable[str], handler=None) -> str:
    control_actions = _control_actions()

    if isinstance(handler, partial) and handler.args:
        func = handler.func
        if (getattr(func, "__name__", "") == "activate"
                and (getattr(func, "__module__", "") or "").endswith("select_tools")):
            return "tool." + str(handler.args[0])
    return control_actions.menu_action_id(tuple(path), handler)


CREATE_SUBMENUS = {"spline": "Spline", "mesh": "Mesh", "generator": "Generator"}


def object_menu_path(spec) -> tuple[str, ...]:
    if spec.category == "null":
        return ("Create", spec.label)
    return ("Create", CREATE_SUBMENUS[spec.category], spec.label)


def _object_commands() -> list[tuple[tuple[str, ...], Callable[[], object]]]:
    return [(object_menu_path(spec), partial(create_object, spec.id)) for spec in objects.all_specs()]


def _file_commands() -> list[tuple[tuple[str, ...], Callable[[], object]]]:
    commands = [
        (("File", "New Project"), project.new_project),
        (("File", "Open Project..."), project.open_project),
        (("File", "Open Recent", "Clear Recent File List"), project.clear_recent),
        (("File", "Merge Project..."), project.merge_project),
        (("File", "Save Project"), project.save_project),
        (("File", "Save Project As..."), project.save_project_as),
        (("File", "Save Incremental"), project.save_incremental),
        (("File", "Import..."), project.import_files),
        (("File", "Export", "Export Selection..."), project.export_selection),
        (("File", "Exit"), project.exit_app),
    ]
    for fmt in fileio.exporters():
        commands.append((("File", "Export", menus_data.export_label(fmt)), partial(project.export_as, fmt.id)))
    return commands


def _has_selection() -> bool:
    scene = _scene()
    return scene.active is not None and bool(scene.object_selected)


SCENE_COMMANDS: list[tuple[tuple[str, ...], Callable[[], object]]] = _file_commands() + [
    (("Edit", "Undo"), undo),
    (("Edit", "Redo"), redo),
    (("Edit", "Controls..."), open_controls),
    (("Create", "Spline", "Line"), create_line),
    (("Create", "Mesh", "Empty Polygon"), create_empty_polygon),
    (("Mesh", "Make Editable"), make_editable),
    (("Mesh", "Polygon Pen"), polygon_pen),
] + _object_commands()

SCENE_ENABLED: dict[tuple[str, ...], Callable[[], bool]] = {
    ("Edit", "Undo"): lambda: _scene().can_undo(),
    ("Edit", "Redo"): lambda: _scene().can_redo(),
    ("Mesh", "Make Editable"): can_make_editable,
    ("File", "Export", "Export Selection..."): _has_selection,
    ("File", "Open Recent", "Clear Recent File List"): lambda: bool(project.recent_files()),
}



class MenuBar(QMenuBar):

    commandTriggered = Signal(str)
    menusChanged = Signal()

    def __init__(self, parent: QWidget | None = None,
                 menus: Iterable | None = None, *, functional_only: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("qsMenuBar")
        self.setNativeMenuBar(False)
        self.setFont(menu_font())
        self.setStyleSheet(f"""
QMenuBar#qsMenuBar {{
    background: {theme.SURFACE_BACKDROP};
    border: none;
    padding: 0px 0px 0px {BAR_LEFT_PAD}px;
    spacing: 0px;
    font-size: {UI_POINT_SIZE}pt;
}}
QMenuBar#qsMenuBar::item {{
    background: transparent;
    padding: {(theme.MENU_BAR_H - 15) // 2}px {BAR_ITEM_PAD}px;
    margin: 0px;
    border: none;
}}
""")
        self.setFixedHeight(theme.MENU_BAR_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.menus: dict[str, StudioMenu] = {}
        self._styles: dict[str, str | None] = {}
        self.extension_shortcuts: list[QShortcut] = []
        self._extension_ids: dict[tuple[str, ...], str] = {}
        self._widths: dict[QAction, int] = {}
        self._limit: int | None = None
        self.overflow_menu = StudioMenu(OVERFLOW_LABEL, self)
        self.overflow_menu.setObjectName("qsMenuOverflow")
        self.overflow_action = self.addMenu(self.overflow_menu)
        self.overflow_action.setText("")
        self.overflow_action.setIcon(icons.icon("chevron_down", OVERFLOW_ICON))
        self.overflow_action.setProperty(P_LABEL, OVERFLOW_LABEL)
        self.overflow_action.setToolTip(OVERFLOW_LABEL)
        self.overflow_action.setVisible(False)
        for title, entries, style in (menus if menus is not None else menus_data.MENU_BAR):
            self.add_studio_menu(title, entries, style)
        self._wire_scene_commands()
        if functional_only:
            self.prune_unwired()
        from quartz_studio import controls

        controls.hub().profileChanged.connect(self.refresh_bindings)

    def prune_unwired(self) -> None:
        for title, menu in list(self.menus.items()):
            if not menu.prune_unwired():
                self.removeAction(menu.menuAction())
                self.overflow_menu.removeAction(menu.menuAction())
                self._widths.pop(menu.menuAction(), None)
                del self.menus[title]
                self._styles.pop(title, None)

    def add_studio_menu(self, title: str, entries: Iterable, style: str | None = None) -> StudioMenu:
        menu = StudioMenu(title, self, entries)
        menu.commandTriggered.connect(self.commandTriggered)
        act = self.insertMenu(self.overflow_action, menu)
        act.setProperty("qs_style", style or "")
        self.menus[title] = menu
        self._styles[title] = style
        if self._limit is not None:
            self._apply_limit()
        self.menusChanged.emit()
        return menu

    def _menu_actions(self) -> list[QAction]:
        return [menu.menuAction() for menu in self.menus.values()]

    def _measure(self) -> None:
        for act in self.actions():
            if act is not self.overflow_action and act.isVisible() and act not in self._widths:
                r = self.actionGeometry(act)
                if not r.isEmpty():
                    self._widths[act] = r.width()

    def _bar_width(self) -> int:
        right = 0
        for act in self.actions():
            if act.isVisible():
                r = self.actionGeometry(act)
                if not r.isEmpty():
                    right = max(right, r.x() + r.width())
        return right

    def natural_width(self) -> int:
        self._measure()
        acts = self._menu_actions()
        return sum(self._widths.get(a, 0) for a in acts) + self._left_inset()

    def _left_inset(self) -> int:
        firsts = [self.actionGeometry(a) for a in self.actions() if a.isVisible()]
        firsts = [r for r in firsts if not r.isEmpty()]
        return min((r.x() for r in firsts), default=0)

    def hidden_titles(self) -> list[str]:
        return [a.text() for a in self.overflow_menu.actions()]

    def width_limit(self) -> int | None:
        return self._limit

    def set_width_limit(self, limit: int | None) -> None:
        self._limit = None if limit is None else max(0, int(limit))
        self._apply_limit()

    def _place(self, keep: int) -> None:
        acts = self._menu_actions()
        shown, hidden = acts[:keep], acts[keep:]
        for act in hidden:
            if act in self.actions():
                self.removeAction(act)
        for act in self.overflow_menu.actions():
            if act not in hidden:
                self.overflow_menu.removeAction(act)
        for act in shown:
            if act not in self.actions():
                self.insertAction(self.overflow_action, act)
        current = self.actions()
        order = [a for a in current if a in shown]
        if order != shown:
            for act in shown:
                self.removeAction(act)
                self.insertAction(self.overflow_action, act)
        now = self.overflow_menu.actions()
        if now != hidden:
            for act in now:
                self.overflow_menu.removeAction(act)
            self.overflow_menu.addActions(hidden)
        self.overflow_action.setVisible(bool(hidden))
        self.updateGeometry()
        self.update()

    def _apply_limit(self) -> None:
        acts = self._menu_actions()
        self._place(len(acts))
        self._measure()
        if self._limit is None:
            return
        inset = self._left_inset()
        widths = [self._widths.get(a, 0) for a in acts]
        if inset + sum(widths) <= self._limit:
            return
        self.overflow_action.setVisible(True)
        more = self.actionGeometry(self.overflow_action).width()
        room = self._limit - inset - more
        keep, used = 0, 0
        for w in widths:
            if used + w > room:
                break
            used += w
            keep += 1
        self._place(keep)

    def add_menu(self, title: str, entries: Iterable) -> StudioMenu:
        if title in self.menus:
            raise ValueError(f"menu {title!r} already exists; use add_entries")
        menu = self.add_studio_menu(title, ())
        from quartz_studio import controls

        with controls.deferred_refresh():
            self._add_extension_entries(menu, entries, (title,))
        self.updateGeometry()
        return menu

    def add_entries(self, menu_title: str, entries: Iterable) -> StudioMenu:
        menu = self.menus.get(menu_title)
        if menu is None:
            raise KeyError(f"no top-level menu {menu_title!r}")
        if menu.actions():
            menu.addSeparator()
        from quartz_studio import controls

        with controls.deferred_refresh():
            self._add_extension_entries(menu, entries, (menu_title,))
        return menu

    def _add_extension_entries(self, menu: StudioMenu, entries: Iterable,
                               prefix: tuple[str, ...]) -> None:
        from quartz_studio import controls
        control_actions = _control_actions()

        for entry in entries:
            if entry is None:
                menu.addSeparator()
                continue
            label, target = entry[0], entry[1]
            path = prefix + (label,)
            if isinstance(target, (list, tuple)):
                self._add_extension_entries(menu.add_submenu(label, ()), target, path)
                continue
            shortcut = entry[2] if len(entry) > 2 else None
            act = menu.add_item(label, shortcut)
            if target is None:
                continue
            menu._handlers[act] = target
            action_id = control_actions.slug(path)
            self._extension_ids[path] = action_id
            installed = getattr(self.window(), "controls_filter", None) is not None
            if shortcut and not installed:
                sc = QShortcut(QKeySequence(shortcut), self.window())
                sc.setContext(Qt.ShortcutContext.WindowShortcut)
                sc.activated.connect(act.trigger)
                self.extension_shortcuts.append(sc)
            controls.register_action(action_id, control_actions.menu_label(label), path[0],
                                     partial(_trigger_path, path, act),
                                     keys=(shortcut,) if shortcut else (), path=path)
        self.refresh_bindings()

    def titles(self) -> list[str]:
        return [a.text() for a in self._menu_actions()]

    def menu_at(self, path: Iterable[str]) -> StudioMenu | None:
        path = list(path)
        menu = self.menus.get(path[0]) if path else None
        for label in path[1:-1]:
            menu = menu.submenu(label) if menu is not None else None
        return menu

    def action_at(self, path: Iterable[str]) -> QAction | None:
        path = list(path)
        menu = self.menu_at(path)
        return menu.find_action(path[-1]) if menu is not None and len(path) > 1 else None

    def _wire_scene_commands(self) -> None:
        for path, handler in SCENE_COMMANDS:
            menu = self.menu_at(path)
            if menu is not None:
                menu.bind(path[-1], handler)
        watched: list[StudioMenu] = []
        for path in SCENE_ENABLED:
            menu = self.menu_at(path)
            if menu is not None and menu not in watched:
                watched.append(menu)
                menu.aboutToShow.connect(self.refresh_enabled)
        recent = self.menu_at(("File", "Open Recent", "x"))
        if recent is not None:
            recent.aboutToShow.connect(self.refresh_recent)
        self.refresh_enabled()
        self.refresh_bindings()

    def refresh_bindings(self, *_args) -> None:
        from quartz_studio import controls

        for title, menu in self.menus.items():
            self._refresh_menu_bindings(controls, menu, (title,))

    def _refresh_menu_bindings(self, controls, menu: StudioMenu, prefix: tuple[str, ...]) -> None:
        for act in menu.actions():
            if act.isSeparator() or act.property(P_KIND) == "section":
                continue
            label = act.property(P_LABEL) or act.text()
            path = prefix + (label,)
            sub = act.menu()
            if isinstance(sub, StudioMenu):
                self._refresh_menu_bindings(controls, sub, path)
                continue
            if act.property("qs_recent"):
                continue
            handler = menu._handlers.get(act)
            if handler is None:
                continue
            action_id = self._extension_ids.get(path) or _menu_action_id(path, handler)
            text = controls.binding_text(action_id)
            act.setProperty(P_SHORTCUT, text)
            act.setText(f"{label}\t{text}" if text else label)

    def refresh_recent(self) -> None:
        menu = self.menu_at(("File", "Open Recent", "x"))
        if not isinstance(menu, StudioMenu):
            return
        for act in list(menu.actions()):
            if act.property("qs_recent"):
                menu._handlers.pop(act, None)
                menu.removeAction(act)
        clear = menu.find_action("Clear Recent File List")
        paths = project.recent_files()
        names = [os.path.basename(p) for p in paths]
        for path, name in zip(paths, names):
            text = path if names.count(name) > 1 else name
            act = menu.add_item(text)
            menu.removeAction(act)
            menu.insertAction(clear, act)
            act.setProperty("qs_recent", True)
            act.setStatusTip(path)
            act.setToolTip(path)
            menu._handlers[act] = partial(project.open_recent, path)
        if paths:
            sep = QAction(menu)
            sep.setSeparator(True)
            sep.setProperty("qs_recent", True)
            menu.insertAction(clear, sep)
        self.refresh_enabled()

    def refresh_enabled(self) -> None:
        for path, check in SCENE_ENABLED.items():
            act = self.action_at(path)
            if act is not None:
                act.setEnabled(bool(check()))

    def sizeHint(self) -> QSize:
        return QSize(self._bar_width() + self._left_inset(), theme.MENU_BAR_H)

    def minimumSizeHint(self) -> QSize:
        return QSize(super().minimumSizeHint().width(), theme.MENU_BAR_H)

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor(theme.SURFACE_BACKDROP))
        p.setFont(self.font())
        active = self.activeAction()
        h = self.height()
        for act in self.actions():
            if not act.isVisible():
                continue
            r = self.actionGeometry(act)
            if r.isEmpty():
                continue
            full = QRect(r.x(), 0, r.width(), h)
            pill = QRectF(full.adjusted(0, BAR_ITEM_INSET, 0, -BAR_ITEM_INSET))
            menu = act.menu()
            is_open = menu is not None and menu.isVisible()
            enabled = act.isEnabled()
            col = theme.TEXT_SECONDARY
            p.setPen(Qt.PenStyle.NoPen)
            if not enabled:
                col = theme.TEXT_MUTED
            elif is_open:
                p.setBrush(QColor(theme.ACCENT_TINT_BACKDROP))
                p.drawRoundedRect(pill, theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)
                col = theme.ACCENT
            elif act is active and self.underMouse():
                p.setBrush(QColor(theme.SURFACE_RAISED))
                p.drawRoundedRect(pill, theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)
                col = theme.TEXT_PRIMARY
            elif act is active and self.hasFocus():
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(theme.FOCUS_RING), theme.FOCUS_RING_W))
                p.drawRoundedRect(pill.adjusted(0.5, 0.5, -0.5, -0.5), theme.CONTROL_RADIUS,
                                  theme.CONTROL_RADIUS)
                col = theme.TEXT_PRIMARY
            if act is self.overflow_action:
                icons.render(p, QRectF(full.center().x() + 1 - OVERFLOW_ICON / 2,
                                       full.center().y() + 1 - OVERFLOW_ICON / 2,
                                       OVERFLOW_ICON, OVERFLOW_ICON), "chevron_down", col)
                continue
            p.setPen(QColor(col))
            p.drawText(full, Qt.AlignmentFlag.AlignCenter, act.text())
        p.end()
