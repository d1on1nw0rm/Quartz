from __future__ import annotations

from functools import partial
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from quartz_studio import icons, objects, theme
from quartz_studio.widgets.command_bar import FLEX, GAP, Cmd, Item, PaletteStrip
from quartz_studio.widgets.menu_bar import create_empty_polygon, create_line, create_object
from quartz_studio.widgets.tool_palette import confine_popup

__all__ = ["ObjectPalette", "OBJECT_PALETTE_ENTRIES", "CREATE_COMMANDS"]

P = theme.ICON_MESH
G = theme.ICON_GENERATOR
NEUTRAL = theme.ICON_STROKE
STROKE_W = theme.ICON_STROKE_W


def _unit(fn):
    def painter(p: QPainter, r: QRectF, c: QColor) -> None:
        p.save()
        side = min(r.width(), r.height())
        p.translate(r.x() + (r.width() - side) / 2, r.y() + (r.height() - side) / 2)
        p.scale(side / 24.0, side / 24.0)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fn(p, QColor(c))
        p.restore()
    return painter


def _line(p: QPainter, c: QColor | str, w: float = STROKE_W) -> None:
    p.setPen(QPen(QColor(c), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)


def _fill(p: QPainter, c: QColor | str) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))


def _arrow_head(p: QPainter, c: QColor, tip: QPointF, dx: float, dy: float, s: float = 3.4) -> None:
    nx, ny = -dy, dx
    _line(p, c)
    p.drawPolyline(QPolygonF([QPointF(tip.x() - dx * s + nx * s, tip.y() - dy * s + ny * s), tip,
                              QPointF(tip.x() - dx * s - nx * s, tip.y() - dy * s - ny * s)]))


def _null(p: QPainter, c: QColor) -> None:
    _line(p, c)
    p.drawPolyline(QPolygonF([QPointF(5.0, 4.4), QPointF(5.0, 19.0), QPointF(19.6, 19.0)]))
    _arrow_head(p, c, QPointF(5.0, 3.6), 0, -1, 3.2)
    _arrow_head(p, c, QPointF(20.6, 19.0), 1, 0, 3.2)
    _line(p, c)
    p.drawEllipse(QPointF(13.6, 10.6), 4.2, 4.2)


def _cube_outline(p: QPainter, cx: float, cy: float, s: float, top: QColor | str | None) -> None:
    pts = [QPointF(cx, cy - s), QPointF(cx + s * 0.9, cy - s * 0.5), QPointF(cx + s * 0.9, cy + s * 0.5),
           QPointF(cx, cy + s), QPointF(cx - s * 0.9, cy + s * 0.5), QPointF(cx - s * 0.9, cy - s * 0.5)]
    if top is not None:
        _fill(p, top)
        p.drawPolygon(QPolygonF([pts[0], pts[1], QPointF(cx, cy), pts[5]]))
    _line(p, NEUTRAL, 1.3)
    p.drawPolygon(QPolygonF(pts))
    p.drawPolyline(QPolygonF([pts[1], QPointF(cx, cy), pts[5]]))
    p.drawLine(QPointF(cx, cy), pts[3])


def _volume_blobs(p: QPainter, c: QColor) -> None:
    _cube_outline(p, 7.4, 15.4, 4.4, None)
    _cube_outline(p, 16.6, 15.4, 4.4, None)
    _cube_outline(p, 12.0, 8.4, 4.4, c)


def _voronoi(p: QPainter, c: QColor) -> None:
    path = QPainterPath()
    path.addEllipse(QPointF(12, 12), 8.4, 8.4)
    p.save()
    p.setClipPath(path)
    p.translate(12, 12)
    p.scale(8.4 / 8.8, 8.4 / 8.8)
    p.translate(-12, -12)
    _fill(p, c)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in ((9, 10), (12, 8), (15, 11), (12, 14))]))
    _line(p, NEUTRAL, 1.3)
    edges = [((11, 4), (12, 8), (16, 5), (17, 2)), ((16, 5), (18, 9), (22, 9)),
             ((7, 6), (9, 10), (12, 8)), ((9, 10), (4, 11), (2, 12)),
             ((18, 9), (15, 11), (12, 14), (9, 10)), ((15, 11), (19, 12), (22, 13)),
             ((19, 12), (17, 16), (13, 16), (12, 14)), ((12, 14), (8, 15), (4, 15), (3, 18)),
             ((8, 15), (9, 19), (13, 18), (13, 16)), ((17, 16), (19, 20)), ((9, 19), (8, 22)),
             ((13, 18), (15, 22)), ((3, 7), (7, 6), (11, 4), (11, 2))]
    for line in edges:
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in line]))
    p.restore()
    _line(p, NEUTRAL)
    p.drawPath(path)


def _sphere_band(p: QPainter, c: QColor) -> None:
    _line(p, NEUTRAL)
    p.drawEllipse(QPointF(12, 12), 8.6, 8.6)
    _line(p, c)
    p.drawArc(QRectF(3.4, 7.6, 17.2, 8.8), 180 * 16, 180 * 16)
    _line(p, NEUTRAL, 1.2)
    p.drawArc(QRectF(3.4, 7.6, 17.2, 8.8), 0, 180 * 16)


def _extrude(p: QPainter, c: QColor) -> None:
    top = QPolygonF([QPointF(12, 3.4), QPointF(20.0, 7.6), QPointF(12, 11.8), QPointF(4.0, 7.6)])
    _fill(p, c)
    p.drawPolygon(top)
    _line(p, NEUTRAL)
    p.drawPolyline(QPolygonF([QPointF(4.0, 7.6), QPointF(4.0, 16.6), QPointF(12, 20.8),
                              QPointF(20.0, 16.6), QPointF(20.0, 7.6)]))
    p.drawLine(QPointF(12, 11.8), QPointF(12, 20.8))
    p.drawPolygon(top)


def register_palette_icons() -> None:
    if not icons.has("pal_null"):
        icons.register("pal_null", _unit(_null), NEUTRAL)
    if not icons.has("pal_volume_builder"):
        icons.register("pal_volume_builder", _unit(_volume_blobs), G)
    if not icons.has("pal_voronoi"):
        icons.register("pal_voronoi", _unit(_voronoi), G)
    if not icons.has("pal_extrude"):
        icons.register("pal_extrude", _unit(_extrude), G)
    if not icons.has("pal_sphere"):
        icons.register("pal_sphere", _unit(_sphere_band), P)


register_palette_icons()



def _c(name: str, icon: str, color: str | None = None) -> Cmd:
    return Cmd(name, icon, color)


ICON_OVERRIDES = {
    "null": "pal_null",
    "sphere": "pal_sphere",
    "extrude": "pal_extrude",
    "voronoi_fracture": "pal_voronoi",
    "symmetry": "symmetry_generator",
    "text_spline": "text_spline",
}
ICON_FALLBACKS = {"null": "null", "spline": "spline", "mesh": "primitive", "generator": "generator"}
CATEGORY_COLORS = {"null": None, "spline": theme.ICON_SPLINE, "mesh": P, "generator": G}

PALETTE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Rectangle", ("rectangle", "text_spline", "profile", "four_side", "n_side", "star", "cogwheel")),
    ("Circle", ("circle", "arc", "cissoid", "cycloid", "formula", "helix", "flower")),
    ("Cube", ("cube", "empty_polygon", "plane", "bezier", "landscape", "pyramid")),
    ("Sphere", ("sphere", "disc", "torus", "cone", "tube", "cylinder", "oil_tank", "capsule")),
    ("Text", ("text", "figure", "platonic")),
    ("Subdivision Surface", ("subdivision_surface", "boole", "symmetry", "remesh", "connect",
                             "cloner", "thicken")),
    ("Extrude", ("extrude", "sweep", "lathe", "loft", "spline_mask", "trunk")),
    ("Voronoi Fracture", ("voronoi_fracture", "fracture", "metaball", "array")),
)
SHAPE_GROUP_COUNT = 5

_LINE = _c("Line", "m_line")
_EMPTY_POLYGON = _c("Empty Polygon", "empty_polygon", P)


def _icon_name(spec) -> str:
    for name in (ICON_OVERRIDES.get(spec.id), spec.icon, spec.id):
        if name and icons.has(name):
            return name
    return ICON_FALLBACKS[spec.category]


def _spec_entry(spec_id: str) -> tuple[Cmd, Callable[[], None]] | None:
    if spec_id == "empty_polygon":
        return _EMPTY_POLYGON, create_empty_polygon
    spec = objects.SPECS.get(spec_id)
    if spec is None:
        return None
    return (_c(spec.label, _icon_name(spec), CATEGORY_COLORS[spec.category]),
            partial(create_object, spec.id))


def _build_palette() -> tuple[list, dict[tuple[str, str], Callable[[], None]]]:
    entries: list = [FLEX, Item(_LINE)]
    commands: dict[tuple[str, str], Callable[[], None]] = {(_LINE.name, _LINE.name): create_line}
    null = _spec_entry("null")
    if null is not None:
        entries.append(Item(null[0]))
        commands[(null[0].name, null[0].name)] = null[1]
    for index, (key, ids) in enumerate(PALETTE_GROUPS):
        if index in (0, SHAPE_GROUP_COUNT):
            entries.append(GAP)
        found = [e for e in (_spec_entry(i) for i in ids) if e is not None]
        if not found:
            continue
        cmds = [cmd for cmd, _action in found]
        entries.append(Item(cmds[0], foldout=cmds, key=key))
        for cmd, action in found:
            commands[(key, cmd.name)] = action
    entries.append(FLEX)
    return entries, commands


OBJECT_PALETTE_ENTRIES, CREATE_COMMANDS = _build_palette()

OBJECT_BUTTON = theme.DOCK_BUTTON
OBJECT_ICON = theme.DOCK_ICON
OBJECT_GAP = theme.DOCK_GAP
OBJECT_PAD = theme.DOCK_PAD
DIVIDER_LENGTH = 24
DIVIDER_COLOR = theme.HAIRLINE


def dock_stylesheet() -> str:
    r = theme.CONTROL_RADIUS
    return f"""
QFrame#qsSegment {{
    background: transparent;
    border: none;
    border-radius: 0px;
}}
QToolButton#qsIconButton {{
    background: transparent;
    border: none;
    border-radius: {r}px;
}}
QToolButton#qsIconButton:hover {{
    background: {theme.SURFACE_RAISED};
}}
QToolButton#qsIconButton:pressed {{
    background: {theme.SURFACE_PRESSED};
}}
QToolButton#qsIconButton:disabled {{
    background: transparent;
}}
"""


class _DockDivider(QWidget):

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._horizontal = orientation == Qt.Orientation.Horizontal
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if self._horizontal:
            self.setFixedSize(OBJECT_GAP, DIVIDER_LENGTH)
        else:
            self.setFixedSize(DIVIDER_LENGTH, OBJECT_GAP)

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setPen(QColor(DIVIDER_COLOR))
        if self._horizontal:
            x = self.width() // 2
            p.drawLine(x, 0, x, self.height() - 1)
        else:
            y = self.height() // 2
            p.drawLine(0, y, self.width() - 1, y)
        p.end()


def _with_dividers(entries: list, orientation: Qt.Orientation) -> list:
    return [_DockDivider(orientation) if entry == GAP else entry for entry in entries]


class ObjectPalette(PaletteStrip):

    def __init__(self, parent: QWidget | None = None, *,
                 orientation: Qt.Orientation = Qt.Orientation.Horizontal,
                 popup_side: str | None = None) -> None:
        horizontal = orientation == Qt.Orientation.Horizontal
        side = popup_side or ("above" if horizontal else "left")
        cross = Qt.AlignmentFlag.AlignVCenter if horizontal else Qt.AlignmentFlag.AlignHCenter
        super().__init__(_with_dividers(OBJECT_PALETTE_ENTRIES, orientation), orientation, parent,
                         button=OBJECT_BUTTON, icon=OBJECT_ICON, gap=OBJECT_GAP,
                         popup_side=side, cross_align=cross,
                         margins=(OBJECT_PAD, OBJECT_PAD, OBJECT_PAD, OBJECT_PAD))
        self.setObjectName("qsObjectPalette")
        self.popup_side = side
        self.floating = horizontal
        if horizontal:
            self.setFixedHeight(theme.DOCK_H)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        else:
            self.setFixedWidth(OBJECT_BUTTON + 2 * OBJECT_PAD)
        self.setStyleSheet(dock_stylesheet())
        for button in self.buttons.values():
            button.group_mark_color = theme.TEXT_SECONDARY
            confine_popup(button, (0, -(theme.DOCK_PAD + theme.SPACE_1 - 1)))
        for (key, name), action in CREATE_COMMANDS.items():
            self.buttons[key].set_command_action(name, action)

    def natural_width(self) -> int:
        return self._layout.sizeHint().width()

    def paintEvent(self, e: QPaintEvent) -> None:
        if not self.floating:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(theme.HAIRLINE), 1.0))
        p.setBrush(QColor(theme.DOCK_BG))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.drawRoundedRect(r, theme.DOCK_RADIUS, theme.DOCK_RADIUS)
        p.end()
