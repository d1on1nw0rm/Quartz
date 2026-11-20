from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Iterable, Iterator, Sequence, Union

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSignalBlocker, QSize, Qt, SignalInstance
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QMoveEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QBoxLayout,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSpacerItem,
    QWidget,
)

from quartz_studio import icons, theme
from quartz_studio.scene import get_scene
from quartz_studio.widgets.common import IconButton, Segment, prepare_popup
from quartz_studio.widgets.menu_bar import can_make_editable, make_editable

__all__ = [
    "Cmd",
    "Group",
    "Item",
    "Gear",
    "FLEX",
    "GAP",
    "SEP",
    "COLUMN",
    "FoldoutButton",
    "PaletteStrip",
    "SceneBinding",
    "CommandBar",
    "ProjectChip",
    "COMMAND_BAR_ENTRIES",
    "MODE_BUTTONS",
    "iter_commands",
]


ICON_GREY = theme.ICON_STROKE
RENDER_GREY = theme.ICON_STROKE
HISTORY_GREY = theme.ICON_STROKE


def unit_painter(fn: Callable[[QPainter, QColor], None]):
    def painter(p: QPainter, r: QRectF, c: QColor) -> None:
        p.save()
        side = min(r.width(), r.height())
        p.translate(r.x() + (r.width() - side) / 2, r.y() + (r.height() - side) / 2)
        p.scale(side / 24.0, side / 24.0)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fn(p, QColor(c))
        p.restore()
    return painter


def _alpha(color: str, opacity: float) -> QColor:
    out = QColor(color)
    out.setAlphaF(opacity)
    return out


def stroke(p: QPainter, c: QColor | str, w: float) -> None:
    p.setPen(QPen(QColor(c), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)


def solid(p: QPainter, c: QColor | str) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))


def _hex(cx: float = 12, cy: float = 12, r: float = 9.1) -> list[QPointF]:
    out = []
    for k in range(6):
        a = math.radians(-90 + 60 * k)
        out.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def _letter_path(text: str, cx: float, baseline: float, px: float) -> QPainterPath:
    f = QFont("Segoe UI")
    f.setPixelSize(64)
    f.setWeight(QFont.Weight.DemiBold)
    path = QPainterPath()
    path.addText(0, 0, f, text)
    br = path.boundingRect()
    k = px / br.height() if br.height() else 1.0
    out = QPainterPath()
    for poly in path.toFillPolygons():
        out.addPolygon(QPolygonF([QPointF(cx + (pt.x() - br.center().x()) * k,
                                          baseline + (pt.y() - br.bottom()) * k) for pt in poly]))
    out.setFillRule(Qt.FillRule.WindingFill)
    return out


def _icon_commander(p: QPainter, c: QColor) -> None:
    stroke(p, c, 2.1)
    p.drawEllipse(QPointF(10.2, 10.2), 5.6, 5.6)
    stroke(p, c, 2.7)
    p.drawLine(QPointF(14.4, 14.4), QPointF(19.6, 19.6))


def _axis_icon(letter: str, axis: str):
    def fn(p: QPainter, c: QColor) -> None:
        solid(p, c)
        p.drawPath(_letter_path(letter, 12, 15.2, 10.6))
        solid(p, axis)
        p.drawRoundedRect(QRectF(4.6, 18.4, 14.8, 2.4), 0.8, 0.8)
    return fn


def _icon_coord_system(p: QPainter, c: QColor) -> None:
    h = _hex(12, 6.0, 4.6)
    o = QPointF(12, 6.0)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_alpha(theme.TINT_MINT, 0.25))
    p.drawPolygon(QPolygonF([h[5], h[0], h[1], o]))
    stroke(p, c, theme.ICON_STROKE_W)
    p.drawPolygon(QPolygonF(h))
    p.drawLine(o, h[3])
    p.drawLine(QPointF(12, 10.5), QPointF(12, 13.5))
    p.drawLine(QPointF(5, 13.5), QPointF(19, 13.5))
    for x in (5.0, 12.0, 19.0):
        p.drawLine(QPointF(x, 13.5), QPointF(x, 16.5))
    solid(p, c)
    for x in (5.0, 12.0, 19.0):
        p.drawRect(QRectF(x - 1.8, 16.5, 3.6, 3.6))


def _icon_axis_enable(p: QPainter, c: QColor) -> None:
    o = QPointF(12, 13)
    ends = (QPointF(12, 4.4), QPointF(4.8, 19.2), QPointF(19.2, 19.2))
    stroke(p, c, 2.0)
    for e in ends:
        p.drawLine(o, e)
    solid(p, c)
    for e in ends:
        p.drawEllipse(e, 2.2, 2.2)
    p.drawEllipse(o, 1.6, 1.6)


def _icon_gear(p: QPainter, c: QColor) -> None:
    teeth, r_out, r_in, hole = 6, 9.4, 7.0, 3.2
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a0 = i * step - math.pi / 2
        for frac, rad in ((0.0, r_in), (0.14, r_out), (0.36, r_out), (0.5, r_in), (1.0, r_in)):
            a = a0 + frac * step
            pts.append(QPointF(12 + rad * math.cos(a), 12 + rad * math.sin(a)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    path.addEllipse(QPointF(12, 12), hole, hole)
    path.setFillRule(Qt.FillRule.OddEvenFill)
    solid(p, c)
    p.drawPath(path)


def _icon_mode_points(p: QPainter, c: QColor) -> None:
    stroke(p, c, theme.ICON_STROKE_W)
    p.drawPolygon(QPolygonF(_hex()))
    solid(p, theme.TINT_MINT)
    p.drawEllipse(QPointF(12, 12), 2.6, 2.6)


def _icon_mode_edges(p: QPainter, c: QColor) -> None:
    h = _hex()
    stroke(p, c, theme.ICON_STROKE_W)
    p.drawPolygon(QPolygonF(h))
    stroke(p, theme.TINT_MINT, theme.ICON_STROKE_W + 0.9)
    p.drawLine(h[2], h[3])
    solid(p, theme.TINT_MINT)
    for pt in (h[2], h[3]):
        p.drawEllipse(pt, 1.7, 1.7)


def _icon_mode_polygons(p: QPainter, c: QColor) -> None:
    h = _hex()
    face = QPolygonF([QPointF(12, 12), h[1], h[2], h[3]])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_alpha(theme.TINT_MINT, 0.25))
    p.drawPolygon(face)
    stroke(p, c, theme.ICON_STROKE_W)
    p.drawPolygon(QPolygonF(h))
    stroke(p, theme.TINT_MINT, theme.ICON_STROKE_W)
    p.drawPolygon(face)


def _icon_mode_model(p: QPainter, c: QColor) -> None:
    h = _hex(r=8.8)
    o = QPointF(12, 12)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.TINT_MINT)
    p.drawPolygon(QPolygonF([h[5], h[0], h[1], o]))
    stroke(p, c, theme.ICON_STROKE_W)
    p.drawPolygon(QPolygonF(h))
    for k in (1, 3, 5):
        p.drawLine(o, h[k])


def _icon_symmetry(p: QPainter, c: QColor) -> None:
    solid(p, c)
    p.drawRoundedRect(QRectF(11.4, 3.0, 1.2, 18.0), 0.5, 0.5)
    for sgn in (-1, 1):
        x0 = 12 + sgn * 1.6
        upper = QPainterPath()
        upper.moveTo(x0, 4.6)
        upper.cubicTo(x0 + sgn * 2.5, 3.4, x0 + sgn * 7.2, 3.0, x0 + sgn * 7.0, 6.2)
        upper.cubicTo(x0 + sgn * 6.8, 9.2, x0 + sgn * 3.0, 11.2, x0, 11.4)
        upper.closeSubpath()
        lower = QPainterPath()
        lower.moveTo(x0, 12.6)
        lower.cubicTo(x0 + sgn * 3.0, 12.6, x0 + sgn * 6.4, 14.0, x0 + sgn * 6.0, 17.2)
        lower.cubicTo(x0 + sgn * 5.6, 20.2, x0 + sgn * 1.6, 19.8, x0, 18.6)
        lower.closeSubpath()
        if sgn > 0:
            solid(p, c)
        else:
            stroke(p, c, 1.3)
        p.drawPath(upper)
        p.drawPath(lower)


def _icon_render_region(p: QPainter, c: QColor) -> None:
    lo, hi, hs = 4.6, 19.4, 2.1
    p.setPen(QPen(c, 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    inset = hs + 0.4
    p.drawLine(QPointF(lo + inset, lo), QPointF(hi - inset, lo))
    p.drawLine(QPointF(lo + inset, hi), QPointF(hi - inset, hi))
    p.drawLine(QPointF(lo, lo + inset), QPointF(lo, hi - inset))
    p.drawLine(QPointF(hi, lo + inset), QPointF(hi, hi - inset))
    p.setPen(QPen(c, 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.MiterJoin))
    for x, y in ((lo, lo), (hi, lo), (lo, hi), (hi, hi)):
        p.drawRect(QRectF(x - hs, y - hs, 2 * hs, 2 * hs))


def _clapper_body(p: QPainter, c: QColor) -> QRectF:
    p.translate(12, 12.4)
    p.scale(1.1, 1.1)
    p.translate(-12, -12)
    body = QRectF(3.6, 8.4, 16.8, 12.0)
    solid(p, c)
    p.drawRoundedRect(body, 1.0, 1.0)
    top = QPainterPath()
    top.addRoundedRect(QRectF(3.6, 3.6, 16.8, 4.0), 0.8, 0.8)
    notch = QPainterPath()
    for x in (6.0, 10.2, 14.4, 18.6):
        notch.addPolygon(QPolygonF([QPointF(x - 1.6, 3.6), QPointF(x + 1.6, 3.6), QPointF(x, 6.6)]))
    p.drawPath(top.subtracted(notch))
    return body


def _icon_render_view(p: QPainter, c: QColor) -> None:
    body = _clapper_body(p, c)
    solid(p, theme.SURFACE_FIELD)
    cx, cy = body.center().x(), body.center().y()
    p.drawPolygon(QPolygonF([QPointF(cx - 2.0, cy - 2.8), QPointF(cx + 3.0, cy),
                             QPointF(cx - 2.0, cy + 2.8)]))


def _icon_render_settings(p: QPainter, c: QColor) -> None:
    body = _clapper_body(p, c)
    cx, cy = body.center().x(), body.center().y()
    stroke(p, theme.SURFACE_FIELD, 1.8)
    p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)
    solid(p, theme.SURFACE_FIELD)
    for k in range(6):
        a = math.radians(60 * k)
        p.drawEllipse(QPointF(cx + 4.0 * math.cos(a), cy + 4.0 * math.sin(a)), 0.9, 0.9)


def register_bar_icons() -> None:
    table = {
        "pal_commander": (_icon_commander, ICON_GREY),
        "pal_axis_x": (_axis_icon("X", theme.AXIS_X), ICON_GREY),
        "pal_axis_y": (_axis_icon("Y", theme.AXIS_Y), ICON_GREY),
        "pal_axis_z": (_axis_icon("Z", theme.AXIS_Z), ICON_GREY),
        "pal_coord_system": (_icon_coord_system, ICON_GREY),
        "pal_axis_enable": (_icon_axis_enable, ICON_GREY),
        "pal_gear": (_icon_gear, ICON_GREY),
        "pal_mode_points": (_icon_mode_points, ICON_GREY),
        "pal_mode_edges": (_icon_mode_edges, ICON_GREY),
        "pal_mode_polygons": (_icon_mode_polygons, ICON_GREY),
        "pal_mode_model": (_icon_mode_model, ICON_GREY),
        "pal_symmetry": (_icon_symmetry, ICON_GREY),
        "pal_render_region": (_icon_render_region, ICON_GREY),
        "pal_render_view": (_icon_render_view, RENDER_GREY),
        "pal_render_settings": (_icon_render_settings, RENDER_GREY),
    }
    for name, (fn, col) in table.items():
        if not icons.has(name):
            icons.register(name, unit_painter(fn), col)


register_bar_icons()



SEP = "sep"
COLUMN = "column"
FLEX = "flex"
GAP = "gap"
FLEX_WEIGHT = 100


@dataclass(frozen=True)
class Cmd:

    name: str
    icon: str
    color: str | None = None


@dataclass
class Group:

    shown: Cmd
    items: list = field(default_factory=list)


Node = Union[Cmd, Group, str]


@dataclass
class Item:

    cmd: Cmd
    foldout: list | None = None
    checkable: bool = False
    checked: bool = False
    exclusive: str | None = None
    enabled: bool = True
    visible: bool = True
    key: str | None = None


@dataclass
class Gear:

    tooltip: str
    enabled: bool = True


def iter_commands(nodes: Iterable[Node] | None) -> Iterator[Cmd]:
    for n in nodes or ():
        if isinstance(n, Cmd):
            yield n
        elif isinstance(n, Group):
            yield from iter_commands(n.items)



class FoldoutButton(IconButton):

    wired: bool = False
    wired_commands: frozenset[str] | None = None
    tooltips: dict[str, str] = {}

    def __init__(self, item: Item, parent: QWidget | None = None, *, size: int,
                 icon_size: int, popup_side: str = "auto") -> None:
        tree = list(item.foldout or [])
        flat = [(c.icon, c.name) for c in iter_commands(tree)] or None
        super().__init__(item.cmd.icon, item.cmd.name, item.checkable, parent,
                         group=flat, size=size, icon_size=icon_size,
                         color=item.cmd.color, enabled=item.enabled,
                         popup_side=popup_side)
        self._tree: list = tree
        self.item = item
        self._actions: dict[str, Callable[[], None]] = {}
        if item.checkable and item.checked:
            self.setChecked(True)

    def foldout(self) -> list:
        return list(self._tree)

    def find_command(self, name: str) -> Cmd | None:
        if name == self.item.cmd.name:
            return self.item.cmd
        return next((c for c in iter_commands(self._tree) if c.name == name), None)

    def show_command(self, name: str) -> bool:
        cmd = self.find_command(name)
        if cmd is None:
            return False
        self._color = cmd.color
        self.set_command(cmd.icon, cmd.name)
        return True

    def set_command_action(self, name: str, action: Callable[[], None]) -> None:
        self._actions[name] = action

    def set_tooltips(self, tips: dict[str, str]) -> None:
        self.tooltips = dict(tips)
        self._refresh()

    def command_action(self, name: str) -> Callable[[], None] | None:
        return self._actions.get(name)

    def is_wired(self, name: str | None = None) -> bool:
        name = self.command_text() if name is None else name
        if name in self._actions:
            return True
        if self.wired_commands is not None:
            return name in self.wired_commands
        return self.wired

    DIM_OPACITY = 0.2

    def _refresh(self) -> None:
        super()._refresh()
        tip = self.tooltips.get(self._text)
        if tip:
            self.setToolTip(tip)
        if not self.isEnabled():
            self.setIcon(self._dimmed_icon())

    def _dimmed_icon(self) -> QIcon:
        dpr = 2.0
        normal = icons.pixmap(self._icon_name, self._icon_px, self._color,
                              device_pixel_ratio=dpr)
        dim = QPixmap(normal.size())
        dim.fill(Qt.GlobalColor.transparent)
        dim.setDevicePixelRatio(dpr)
        p = QPainter(dim)
        p.setOpacity(self.DIM_OPACITY)
        p.drawPixmap(0, 0, normal)
        p.end()
        out = QIcon()
        out.addPixmap(normal, QIcon.Mode.Normal)
        out.addPixmap(dim, QIcon.Mode.Disabled)
        return out

    def changeEvent(self, e: QEvent) -> None:
        super().changeEvent(e)
        if e.type() == QEvent.Type.EnabledChange:
            self._refresh()

    def build_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("qsFoldout")
        prepare_popup(menu)
        self._fill(menu, self._tree)
        return menu

    def open_group_menu(self) -> None:
        if not self._tree:
            return
        menu = self.build_menu()
        menu.exec(self._popup_pos(menu))
        self.setDown(False)

    def _fill(self, menu: QMenu, nodes: Sequence[Node]) -> None:
        last_sep = True
        for n in nodes:
            if n in (SEP, COLUMN):
                if not last_sep:
                    menu.addSeparator()
                last_sep = True
                continue
            last_sep = False
            if isinstance(n, Group):
                sub = menu.addMenu(icons.icon(n.shown.icon, 18, n.shown.color), n.shown.name)
                sub.setObjectName("qsFoldout")
                prepare_popup(sub)
                self._fill(sub, n.items)
            else:
                act = menu.addAction(icons.icon(n.icon, 18, n.color), n.name)
                act.setToolTip(self.tooltips.get(n.name, n.name))
                act.triggered.connect(partial(self._pick, n))

    def _pick(self, cmd: Cmd, _checked: bool = False) -> None:
        self.set_icon_color(cmd.color)
        if self.is_wired(cmd.name):
            self.set_command(cmd.icon, cmd.name)
            self.commandChosen.emit(cmd.name)
            action = self._actions.get(cmd.name)
            if action is not None:
                action()
        else:
            self._choose(cmd.icon, cmd.name)

    def _on_clicked(self) -> None:
        action = self._actions.get(self.command_text())
        if action is not None:
            action()
        elif not self.is_wired():
            super()._on_clicked()


class GearButton(IconButton):

    def __init__(self, gear: Gear, orientation: Qt.Orientation, thickness: int,
                 length: int, parent: QWidget | None = None, icon_size: int | None = None) -> None:
        super().__init__("pal_gear", gear.tooltip, False, parent, size=thickness,
                         icon_size=icon_size or max(10, min(length, round(thickness * 0.62))),
                         enabled=gear.enabled)
        if orientation == Qt.Orientation.Horizontal:
            self.setFixedSize(length, thickness)
        else:
            self.setFixedSize(thickness, length)

    def sizeHint(self) -> QSize:
        return self.size()



class PaletteStrip(QWidget):

    def __init__(self, entries: Sequence, orientation: Qt.Orientation,
                 parent: QWidget | None = None, *, button: int, icon: int,
                 gap: int, gear_length: int | None = None, popup_side: str = "auto",
                 cross_align: Qt.AlignmentFlag | None = None,
                 margins: tuple[int, int, int, int] = (0, 0, 0, 0),
                 cell_dividers: bool = False, gear_icon: int | None = None) -> None:
        super().__init__(parent)
        self._cell_dividers = cell_dividers
        self._gear_icon = gear_icon
        self._orientation = orientation
        horizontal = orientation == Qt.Orientation.Horizontal
        direction = QBoxLayout.Direction.LeftToRight if horizontal else QBoxLayout.Direction.TopToBottom
        self._layout = QBoxLayout(direction, self)
        self._layout.setContentsMargins(*margins)
        self._layout.setSpacing(0)
        if cross_align is None:
            cross_align = Qt.AlignmentFlag.AlignVCenter if horizontal else Qt.AlignmentFlag.AlignHCenter
        self._cross = cross_align
        self._button = button
        self._icon = icon
        self._gap = gap
        self._gear_length = gear_length or max(12, round(button * 0.58))
        self._popup_side = popup_side
        self.buttons: dict[str, FoldoutButton] = {}
        self.gears: list[GearButton] = []
        self.segments: list[Segment] = []
        self.button_groups: dict[str, QButtonGroup] = {}
        self._segment: Segment | None = None
        self._segment_widgets: dict[int, list[QWidget]] = {}
        for entry in entries:
            self._add(entry)
        self._sync_segments()
        if horizontal:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def button(self, key: str) -> FoldoutButton:
        return self.buttons[key]

    def command_names(self) -> list[str]:
        return list(self.buttons)

    def _new_segment(self) -> Segment:
        seg = Segment(self._orientation, self, dividers=self._cell_dividers)
        self._layout.addWidget(seg, 0, self._cross)
        self.segments.append(seg)
        self._segment_widgets[id(seg)] = []
        self._segment = seg
        return seg

    def _add(self, entry) -> None:
        if entry == FLEX:
            self._layout.addStretch(FLEX_WEIGHT)
            self._segment = None
        elif isinstance(entry, tuple) and entry and entry[0] == FLEX:
            self._layout.addStretch(int(entry[1]))
            self._segment = None
        elif entry == GAP:
            self._layout.addSpacing(self._gap)
            self._segment = None
        elif isinstance(entry, Gear):
            seg = self._segment or self._new_segment()
            gb = GearButton(entry, self._orientation, self._button, self._gear_length, seg,
                            icon_size=self._gear_icon)
            seg.add(gb)
            self._segment_widgets[id(seg)].append(gb)
            self.gears.append(gb)
        elif isinstance(entry, Item):
            seg = self._segment or self._new_segment()
            btn = FoldoutButton(entry, seg, size=self._button, icon_size=self._icon,
                                popup_side=self._popup_side)
            seg.add(btn)
            self._segment_widgets[id(seg)].append(btn)
            btn.setVisible(entry.visible)
            self.buttons[entry.key or entry.cmd.name] = btn
            if entry.exclusive:
                grp = self.button_groups.get(entry.exclusive)
                if grp is None:
                    grp = QButtonGroup(self)
                    grp.setExclusive(True)
                    self.button_groups[entry.exclusive] = grp
                grp.addButton(btn)
        elif isinstance(entry, QWidget):
            self._layout.addWidget(entry, 0, self._cross)
            self._segment = None
        else:
            raise TypeError(f"unknown palette entry {entry!r}")

    def _sync_segments(self) -> None:
        for seg in self.segments:
            widgets = self._segment_widgets.get(id(seg), [])
            seg.setVisible(any(not w.isHidden() for w in widgets))

    def set_item_visible(self, key: str, visible: bool) -> None:
        self.buttons[key].setVisible(visible)
        self._sync_segments()



class SceneBinding(QObject):

    def __init__(self, group: QButtonGroup, values: dict[QAbstractButton, str], current: str,
                 write: Callable[[str], None], changed: SignalInstance, *,
                 inert: Iterable[str] = (),
                 commands: dict[QAbstractButton, dict[str, str]] | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._group = group
        self._values = dict(values)
        self._commands = {b: dict(m) for b, m in (commands or {}).items()}
        self._write = write
        inert = set(inert)
        for btn, value in self._values.items():
            cmap = self._commands.get(btn)
            if cmap is not None:
                live = frozenset(n for n, v in cmap.items() if v not in inert)
                btn.wired_commands = live
                btn.wired = bool(live)
            else:
                btn.wired = value not in inert
            if isinstance(btn, IconButton):
                btn.commandChosen.connect(partial(self._on_chosen, btn))
        group.buttonToggled.connect(self._on_toggled)
        changed.connect(self.show_value)
        self.show_value(current)

    def button_value(self, button: QAbstractButton | None) -> str | None:
        if button not in self._values:
            return None
        cmap = self._commands.get(button)
        if cmap is not None and isinstance(button, IconButton):
            return cmap.get(button.command_text(), self._values[button])
        return self._values[button]

    def value(self) -> str | None:
        return self.button_value(self._group.checkedButton())

    def button_for(self, value: str) -> QAbstractButton | None:
        for b, v in self._values.items():
            if v == value or value in self._commands.get(b, {}).values():
                return b
        return None

    def show_value(self, value: str) -> None:
        if self.value() == value:
            return
        target = self.button_for(value)
        if target is None:
            checked = self._group.checkedButton()
            if checked is not None:
                with QSignalBlocker(self._group):
                    self._group.setExclusive(False)
                    checked.setChecked(False)
                    self._group.setExclusive(True)
            return
        cmap = self._commands.get(target)
        if cmap and self.button_value(target) != value and isinstance(target, FoldoutButton):
            name = next((n for n, v in cmap.items() if v == value), None)
            if name is not None:
                target.show_command(name)
        with QSignalBlocker(self._group):
            target.setChecked(True)

    def _on_toggled(self, button: QAbstractButton, checked: bool) -> None:
        value = self.button_value(button)
        if checked and value is not None:
            self._write(value)

    def _on_chosen(self, button: QAbstractButton, _text: str) -> None:
        if not button.isCheckable():
            return
        if button.isChecked():
            value = self.button_value(button)
            if value is not None:
                self._write(value)
        else:
            button.setChecked(True)



MODES = "modes"

_UNDO = Cmd("Undo", "undo", HISTORY_GREY)
_REDO = Cmd("Redo", "redo", HISTORY_GREY)
_MAKE_EDITABLE = Cmd("Make Editable", "make_editable", ICON_GREY)

COMMAND_BAR_ENTRIES: list = [
    Item(Cmd("Points", "pal_mode_points"), checkable=True, exclusive=MODES),
    Item(Cmd("Edges", "pal_mode_edges"), checkable=True, exclusive=MODES),
    Item(Cmd("Polygons", "pal_mode_polygons"), checkable=True, exclusive=MODES),
    Item(Cmd("Model", "pal_mode_model"), checkable=True, checked=True, exclusive=MODES),
    FLEX,
    Item(_UNDO),
    Item(_REDO),
    GAP,
    Item(_MAKE_EDITABLE),
]

COMMAND_BUTTON = theme.COMMAND_BUTTON
COMMAND_ICON = theme.COMMAND_ICON
COMMAND_GAP = theme.SPACE_2
COMMAND_GEAR = 17
MODE_ROLE = "modes"
HISTORY_ROLE = "history"
ROLE_PROPERTY = "qsRole"
CHIP_NAME_MAX = 240
MODE_SEGMENT_PAD = 2
MODE_BUTTON_W = 34
MODE_BUTTON_H = theme.SEGMENT_H - 2 * MODE_SEGMENT_PAD

MODE_BUTTONS: dict[str, str] = {
    "Points": "points",
    "Edges": "edges",
    "Polygons": "polygons",
    "Model": "model",
}


class _Dot(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsProjectDot")
        self.setFixedSize(theme.SPACE_2, theme.SPACE_2)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawEllipse(QRectF(1, 1, self.width() - 2, self.height() - 2))
        p.end()


class ProjectChip(QFrame):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsProjectChip")
        self.setFixedHeight(theme.CHIP_H)
        self._name = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.SPACE_3, 0, theme.SPACE_3, 0)
        lay.setSpacing(theme.SPACE_2)
        self.dot = _Dot(self)
        self.name_label = QLabel(self)
        self.name_label.setObjectName("qsProjectName")
        lay.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.name_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.refresh()

    def refresh(self, *_args) -> None:
        from quartz_studio import project

        name = project.project_name()
        modified = project.is_modified()
        self._name = name
        self.name_label.setText(self.name_label.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideMiddle, CHIP_NAME_MAX))
        self.dot.setVisible(modified)
        path = project.current_path()
        tip = path if path else f"{name} (not saved yet)"
        self.setToolTip(f"{tip} - unsaved changes" if modified else tip)
        self.updateGeometry()

    def text(self) -> str:
        return self._name

    def shows_unsaved(self) -> bool:
        return not self.dot.isHidden()


class CommandBar(PaletteStrip):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(COMMAND_BAR_ENTRIES, Qt.Orientation.Horizontal, parent,
                         button=COMMAND_BUTTON, icon=COMMAND_ICON, gap=COMMAND_GAP,
                         gear_length=COMMAND_GEAR, popup_side="below")
        self.setObjectName("qsCommandBar")
        self.setFixedHeight(theme.COMMAND_BAR_H)
        self._lead = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._layout.insertSpacerItem(0, self._lead)
        self.mode_switcher = self.buttons["Points"].parentWidget()
        self._set_role(self.mode_switcher, MODE_ROLE)
        self.mode_switcher.setFixedHeight(theme.SEGMENT_H)
        self.mode_switcher.installEventFilter(self)
        self._fit_mode_margins()
        for key in MODE_BUTTONS:
            self.buttons[key].setFixedSize(MODE_BUTTON_W, MODE_BUTTON_H)
        self._set_role(self.buttons[_UNDO.name].parentWidget(), HISTORY_ROLE)
        self.project_chip = ProjectChip(self)
        self._layout.addSpacing(theme.SPACE_2)
        self._layout.addWidget(self.project_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        scene = get_scene()
        self.mode_binding = SceneBinding(
            self.button_groups[MODES],
            {self.buttons[key]: mode for key, mode in MODE_BUTTONS.items()},
            scene.mode, scene.set_mode, scene.modeChanged, parent=self)
        self._history: dict[str, tuple[Callable[[], object], Callable[[], bool]]] = {
            _UNDO.name: (scene.undo, scene.can_undo),
            _REDO.name: (scene.redo, scene.can_redo),
        }
        for name, (run, _can) in self._history.items():
            self.buttons[name].set_command_action(name, run)
        self._can_make_editable = can_make_editable
        edit_button = self.buttons[_MAKE_EDITABLE.name]
        edit_button.set_command_action(_MAKE_EDITABLE.name, make_editable)
        for signal in (scene.changed, scene.selectionChanged, scene.objectsChanged,
                       scene.modeChanged, scene.toolChanged):
            signal.connect(self.refresh_history)
        self.refresh_history()

    def _fit_mode_margins(self) -> None:
        inset = max(0, MODE_SEGMENT_PAD - self.mode_switcher.frameWidth())
        self.mode_switcher.layout().setContentsMargins(inset, inset, inset, inset)

    def eventFilter(self, obj: QObject, e: QEvent) -> bool:
        if obj is self.mode_switcher and e.type() in (QEvent.Type.StyleChange, QEvent.Type.Polish,
                                                       QEvent.Type.Show):
            self._fit_mode_margins()
        return super().eventFilter(obj, e)

    def _set_role(self, widget: QWidget, role: str) -> None:
        widget.setProperty(ROLE_PROPERTY, role)
        for w in (widget, *widget.findChildren(QWidget)):
            w.style().unpolish(w)
            w.style().polish(w)
        if widget is self.mode_switcher:
            self._fit_mode_margins()

    def history_buttons(self) -> list[FoldoutButton]:
        return [self.buttons[n] for n in self._history]

    def refresh_history(self, *_args) -> None:
        for name, (_run, can) in self._history.items():
            self.buttons[name].setEnabled(bool(can()))
        self.buttons[_MAKE_EDITABLE.name].setEnabled(bool(self._can_make_editable()))

    def refresh_project(self, *_args) -> None:
        self.project_chip.refresh()
        self.center_modes()

    def mode_buttons(self) -> list[FoldoutButton]:
        return [self.buttons[n] for n in MODE_BUTTONS]

    def active_mode(self) -> str:
        return self.mode_binding.value() or ""

    def center_modes(self) -> None:
        host = self.parentWidget()
        if host is not None and host.layout() is not None and host.layout().indexOf(self) >= 0:
            centre = host.width() / 2 - self.x()
        else:
            centre = self.width() / 2
        lead_now = self._lead.sizeHint().width()
        wanted = round(centre - self.mode_switcher.sizeHint().width() / 2)
        natural = self._layout.sizeHint().width() - lead_now
        lead = max(0, min(wanted, self.width() - natural))
        if lead != lead_now:
            self._lead.changeSize(lead, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            self._layout.invalidate()

    def resizeEvent(self, e: QResizeEvent) -> None:
        super().resizeEvent(e)
        self.center_modes()

    def moveEvent(self, e: QMoveEvent) -> None:
        super().moveEvent(e)
        self.center_modes()

    def showEvent(self, e: QShowEvent) -> None:
        super().showEvent(e)
        self.center_modes()
