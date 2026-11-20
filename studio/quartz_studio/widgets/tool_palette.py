from __future__ import annotations

import math
from functools import partial

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSignalBlocker, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen, QPolygonF, QResizeEvent
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QToolButton, QWidget

from quartz_studio import icons, theme
from quartz_studio.modeling import install as modeling_install
from quartz_studio.modeling import select_tools
from quartz_studio.scene import get_scene
from quartz_studio.widgets.command_bar import (
    FLEX,
    GAP,
    Cmd,
    Item,
    PaletteStrip,
    SceneBinding,
    solid,
    stroke,
    unit_painter,
)
from quartz_studio.widgets.common import make_card

__all__ = ["ToolPalette", "TOOL_PALETTE_ENTRIES", "TOOLS", "SCENE_TOOLS", "OTHER_TOOL",
           "PEN_KEY", "PEN_COMMANDS", "SELECT_KEY", "SELECT_COMMANDS", "modeling_entries"]

TOOLS = "tools"


TOOL_GREY = theme.ICON_STROKE
TOOL_TINT = theme.ICON_TOOL
STROKE_W = theme.ICON_STROKE_W


def _chevron(p: QPainter, c: QColor, tip: QPointF, dx: float, dy: float,
             size: float = 3.4, w: float = STROKE_W) -> None:
    nx, ny = -dy, dx
    stroke(p, c, w)
    p.drawPolyline(QPolygonF([
        QPointF(tip.x() - dx * size + nx * size, tip.y() - dy * size + ny * size),
        tip,
        QPointF(tip.x() - dx * size - nx * size, tip.y() - dy * size - ny * size),
    ]))


def _dot(p: QPainter, color: str | QColor, cx: float, cy: float, r: float) -> None:
    solid(p, color)
    p.drawEllipse(QPointF(cx, cy), r, r)


def four_arrows(p: QPainter, c: QColor, cx: float, cy: float, r: float, w: float = STROKE_W) -> None:
    head = r * 0.4
    stroke(p, c, w)
    p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
    p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        _chevron(p, c, QPointF(cx + dx * r, cy + dy * r), dx, dy, head, w)


def cursor(p: QPainter, c: QColor, x: float, y: float, s: float = 1.0) -> None:
    pts = [(0, 0), (0, 10), (2.5, 7.8), (4.3, 11.4), (5.9, 10.7), (4.2, 7.2), (7.6, 7.2)]
    p.setPen(QPen(c, 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(x + a * s, y + b * s) for a, b in pts]))


def _icon_live_selection(p: QPainter, c: QColor) -> None:
    pen = QPen(QColor(TOOL_TINT), STROKE_W, Qt.PenStyle.CustomDashLine, Qt.PenCapStyle.RoundCap)
    pen.setDashPattern([0.2, 2.0])
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(12, 12), 8.8, 8.8)
    cursor(p, c, 8.6, 6.2, 1.0)


def _icon_move(p: QPainter, c: QColor) -> None:
    four_arrows(p, c, 12, 12, 9.0)
    _dot(p, TOOL_TINT, 12, 12, 1.9)


def _icon_rotate(p: QPainter, c: QColor) -> None:
    stroke(p, c, STROKE_W)
    rad = 7.8
    r = QRectF(12 - rad, 12 - rad, 2 * rad, 2 * rad)
    p.drawArc(r, -72 * 16, 122 * 16)
    p.drawArc(r, 108 * 16, 122 * 16)
    for ang in (50, 230):
        a = math.radians(ang)
        tip = QPointF(12 + rad * math.cos(a), 12 - rad * math.sin(a))
        tx, ty = -math.sin(a), -math.cos(a)
        _chevron(p, c, QPointF(tip.x() + tx * 1.6, tip.y() + ty * 1.6), tx, ty, 3.0)
    _dot(p, TOOL_TINT, 12, 12, 1.9)


def _icon_scale(p: QPainter, c: QColor) -> None:
    stroke(p, c, STROKE_W)
    p.drawRoundedRect(QRectF(3.6, 3.6, 16.8, 16.8), 2.0, 2.0)
    p.drawLine(QPointF(12.6, 11.4), QPointF(17.0, 7.0))
    _chevron(p, c, QPointF(17.0, 7.0), 0.7071, -0.7071, 3.4)
    solid(p, TOOL_TINT)
    p.drawRoundedRect(QRectF(6.6, 12.4, 5.8, 5.8), 1.2, 1.2)


def _icon_placement(p: QPainter, c: QColor) -> None:
    cursor(p, c, 3.2, 3.0, 0.95)
    four_arrows(p, c, 15.0, 15.0, 6.2)
    _dot(p, TOOL_TINT, 15.0, 15.0, 1.5)


def _icon_dynamic_place(p: QPainter, c: QColor) -> None:
    four_arrows(p, c, 14.2, 14.6, 6.4)
    _dot(p, TOOL_TINT, 14.2, 14.6, 1.5)
    solid(p, c)
    for cx, cy, r in ((5.4, 6.4, 3.8), (17.8, 4.4, 3.2), (5.2, 17.8, 3.6)):
        a = math.atan2(14.2 - cy, 14.6 - cx)
        moon = QPainterPath()
        moon.addEllipse(QPointF(cx, cy), r, r)
        cut = QPainterPath()
        cut.addEllipse(QPointF(cx + r * 0.5 * math.cos(a), cy + r * 0.5 * math.sin(a)), r * 0.75, r * 0.75)
        p.drawPath(moon.subtracted(cut))


def _icon_pen(p: QPainter, c: QColor) -> None:
    head = QPainterPath()
    head.moveTo(8.8, 15.2)
    head.lineTo(10.0, 9.6)
    head.cubicTo(11.5, 6.6, 14.0, 4.4, 16.4, 3.8)
    head.cubicTo(19.0, 3.4, 20.6, 5.0, 20.2, 7.6)
    head.cubicTo(19.6, 10.0, 17.4, 12.5, 14.4, 14.0)
    head.closeSubpath()
    stroke(p, c, STROKE_W)
    p.drawPath(head)
    p.drawLine(QPointF(8.8, 15.2), QPointF(12.8, 11.2))
    _dot(p, c, 13.6, 10.4, 1.3)
    solid(p, TOOL_TINT)
    p.drawRoundedRect(QRectF(3.4, 15.8, 5.2, 5.2), 1.4, 1.4)


def _icon_paint(p: QPainter, c: QColor) -> None:
    stroke(p, c, 2.4)
    p.drawLine(QPointF(19.0, 5.0), QPointF(9.6, 14.4))
    stroke(p, TOOL_TINT, STROKE_W)
    p.drawEllipse(QPointF(6.6, 17.4), 2.5, 2.5)


def register_tool_icons() -> None:
    table = {
        "pal_live_selection": (_icon_live_selection, TOOL_GREY),
        "pal_move": (_icon_move, TOOL_GREY),
        "pal_rotate": (_icon_rotate, TOOL_GREY),
        "pal_scale": (_icon_scale, TOOL_GREY),
        "pal_placement": (_icon_placement, TOOL_GREY),
        "pal_dynamic_place": (_icon_dynamic_place, TOOL_GREY),
        "pal_pen": (_icon_pen, TOOL_GREY),
        "pal_paint": (_icon_paint, TOOL_GREY),
    }
    for name, (fn, col) in table.items():
        if not icons.has(name):
            icons.register(name, unit_painter(fn), col)


register_tool_icons()


SELECT_KEY = "Selection"
_SELECT_CMDS = [Cmd(tool.name, tool.icon) for tool in select_tools.TOOLS]
_LIVE_SELECTION = _SELECT_CMDS[0]
_PEN = Cmd("Pen", "pal_pen")

TOOL_PALETTE_ENTRIES: list = [
    Item(_LIVE_SELECTION, checkable=True, exclusive=TOOLS, key=SELECT_KEY, foldout=list(_SELECT_CMDS)),
    GAP,
    Item(Cmd("Move", "pal_move"), checkable=True, checked=True, exclusive=TOOLS),
    GAP,
    Item(Cmd("Rotate", "pal_rotate"), checkable=True, exclusive=TOOLS),
    GAP,
    Item(Cmd("Scale", "pal_scale"), checkable=True, exclusive=TOOLS),
    GAP,
    Item(_PEN, checkable=True, exclusive=TOOLS, foldout=[
        Cmd("Polygon Pen", "polygon_pen"),
        _PEN,
    ]),
    FLEX,
]

TOOL_BUTTON = theme.PALETTE_BUTTON
TOOL_ICON = theme.PALETTE_ICON
TOOL_GAP = 10
TOOL_MIN_GAP = 3
TOOL_TOP_MARGIN = theme.RAIL_PAD
RAIL_PAD = theme.RAIL_PAD
DIVIDER_HEIGHT = 19
DIVIDER_INSET = 2
DIVIDER_COLOR = theme.HAIRLINE
ARROW_HEIGHT = 14
ARROW_ICON = 10
SCROLL_STEP = 36


def confine_popup(button, shift: tuple[int, int] = (0, 0)) -> None:
    base = button._popup_pos

    def placed(menu) -> QPoint:
        pos = base(menu) + QPoint(*shift)
        window = button.window()
        area = QRect(window.mapToGlobal(QPoint(0, 0)), window.size())
        size = menu.sizeHint()
        x = max(area.left(), min(pos.x(), area.right() + 1 - size.width()))
        y = max(area.top(), min(pos.y(), area.bottom() + 1 - size.height()))
        return QPoint(x, y)

    button._popup_pos = placed


def rail_stylesheet() -> str:
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
QToolButton#qsIconButton:checked {{
    background: {theme.ACCENT_TINT};
}}
QToolButton#qsIconButton:checked:hover {{
    background: {theme.ACCENT_TINT_HOVER};
}}
QToolButton#qsIconButton:disabled {{
    background: transparent;
}}
QToolButton#qsToolScrollArrow {{
    background: transparent;
    border: none;
    border-radius: {r}px;
}}
QToolButton#qsToolScrollArrow:hover {{
    background: {theme.SURFACE_RAISED};
}}
QToolButton#qsToolScrollArrow:pressed {{
    background: {theme.SURFACE_PRESSED};
}}
QToolButton#qsToolScrollArrow:disabled {{
    background: transparent;
}}
QScrollArea#qsToolScroll {{
    background: transparent;
    border: none;
}}
"""

SCENE_TOOLS: dict[str, str] = {
    SELECT_KEY: "select",
    "Move": "move",
    "Rotate": "rotate",
    "Scale": "scale",
    _PEN.name: "line_pen",
}
OTHER_TOOL = "other"

PEN_KEY = _PEN.name
PEN_COMMANDS: dict[str, str] = {
    "Polygon Pen": "pen",
    _PEN.name: "line_pen",
}

SELECT_COMMANDS: dict[str, str] = {tool.name: tool.id for tool in select_tools.TOOLS}


def _tool_key(item: Item) -> str:
    return item.key or item.cmd.name


def modeling_entries(groups) -> list:
    out: list = []
    for k, group in enumerate(groups):
        cmds = [Cmd(spec.name, icons.modeling_icon_name(spec.id)) for spec in group.specs]
        if k:
            out.append(GAP)
        out.append(Item(cmds[0], foldout=cmds if len(cmds) > 1 else None, checkable=True,
                        exclusive=TOOLS, key=group.name))
    return out


RAIL_ACTIONS: dict[str, str] = {
    "Move": "tool.move",
    "Rotate": "tool.rotate",
    "Scale": "tool.scale",
}
PEN_ACTIONS: dict[str, str] = {
    "Polygon Pen": "tool.pen",
    _PEN.name: "tool.line_pen",
}


def _tooltip(name: str, action_id: str) -> str:
    try:
        from quartz_studio import controls
        return controls.tooltip(name, action_id)
    except (ImportError, AttributeError, KeyError):
        return name


def _select_tooltip(tool) -> str:
    return _tooltip(tool.name, "tool." + tool.id)


class _Divider(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(TOOL_BUTTON, DIVIDER_HEIGHT)

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setPen(QColor(DIVIDER_COLOR))
        y = self.height() // 2
        p.drawLine(DIVIDER_INSET, y, self.width() - DIVIDER_INSET - 1, y)
        p.end()


class _ScrollArrow(QToolButton):

    def __init__(self, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsToolScrollArrow")
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoRepeat(True)
        self.setAutoRepeatDelay(250)
        self.setAutoRepeatInterval(45)
        self.setFixedSize(TOOL_BUTTON, ARROW_HEIGHT)
        self.setIconSize(QSize(ARROW_ICON, ARROW_ICON))
        self.setIcon(icons.icon(icon_name, ARROW_ICON, theme.TEXT_SECONDARY))
        self.hide()


class ToolPalette(PaletteStrip):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__([], Qt.Orientation.Vertical, parent,
                         button=TOOL_BUTTON, icon=TOOL_ICON, gap=TOOL_GAP,
                         popup_side="right", cross_align=Qt.AlignmentFlag.AlignLeft,
                         margins=(RAIL_PAD, TOOL_TOP_MARGIN, RAIL_PAD, RAIL_PAD))
        self.setObjectName("qsToolPalette")
        self.setFixedWidth(theme.RAIL_W)
        make_card(self)
        scene = get_scene()
        groups = modeling_install.palette_groups()
        extra = modeling_entries(groups)
        entries = list(TOOL_PALETTE_ENTRIES[:-1])
        if extra:
            entries.append(_Divider())
            entries.extend(extra)
        entries.append(FLEX)
        self.strip = PaletteStrip(entries, Qt.Orientation.Vertical, self,
                                  button=TOOL_BUTTON, icon=TOOL_ICON, gap=TOOL_GAP,
                                  popup_side="right", cross_align=Qt.AlignmentFlag.AlignLeft)
        self.strip.setObjectName("qsToolStrip")
        self.buttons = self.strip.buttons
        self.button_groups = self.strip.button_groups
        self.segments = self.strip.segments
        self.gears = self.strip.gears
        inner = self.strip._layout
        self._gap_items = [item for item in (inner.itemAt(i) for i in range(inner.count()))
                           if item.spacerItem() is not None and item.sizeHint().height() == TOOL_GAP]
        self._up = _ScrollArrow("arrow_up", self)
        self._down = _ScrollArrow("arrow_down", self)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("qsToolScroll")
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self.strip)
        self.setStyleSheet(rail_stylesheet())
        for button in self.buttons.values():
            button.group_mark_color = theme.TEXT_SECONDARY
            confine_popup(button, (theme.RAIL_PAD + theme.SPACE_1 - 1, 0))
        self._scroll.viewport().setAutoFillBackground(False)
        self.strip.setAutoFillBackground(False)
        self._layout.addWidget(self._up)
        self._layout.addWidget(self._scroll, 1)
        self._layout.addWidget(self._down)
        bar = self._scroll.verticalScrollBar()
        bar.valueChanged.connect(self._update_arrows)
        bar.rangeChanged.connect(self._update_arrows)
        self._up.clicked.connect(partial(self._scroll_by, -SCROLL_STEP))
        self._down.clicked.connect(partial(self._scroll_by, SCROLL_STEP))
        values = {self.buttons[_tool_key(e)]: SCENE_TOOLS.get(_tool_key(e), OTHER_TOOL)
                  for e in TOOL_PALETTE_ENTRIES if isinstance(e, Item) and e.exclusive == TOOLS}
        self.tool_binding = SceneBinding(
            self.button_groups[TOOLS], values, scene.tool, self._set_scene_tool, scene.toolChanged,
            inert=(OTHER_TOOL,),
            commands={self.buttons[PEN_KEY]: PEN_COMMANDS, self.buttons[SELECT_KEY]: SELECT_COMMANDS},
            parent=self)
        self._groups = groups
        self._modeling: dict[str, tuple] = {}
        self._modeling_buttons: list = []
        for group in groups:
            button = self.buttons[group.name]
            self._modeling_buttons.append(button)
            for spec in group.specs:
                button.set_command_action(spec.name, partial(self._run, spec.id))
                self._modeling[spec.id] = (button, spec.name, spec.interactive)
        self.refresh_tooltips()
        self._watch_profiles()
        scene.toolChanged.connect(self._sync_modeling)
        self._sync_modeling(scene.tool)
        self._fit()

    def _watch_profiles(self) -> None:
        try:
            from quartz_studio import controls
            hub = controls.hub()
        except (ImportError, AttributeError):
            return
        hub.profileChanged.connect(self.refresh_tooltips)

    def refresh_tooltips(self, *_args) -> None:
        for group in self._groups:
            self.buttons[group.name].set_tooltips(
                {spec.name: modeling_install.tool_tooltip(spec) for spec in group.specs})
        self.buttons[SELECT_KEY].set_tooltips(
            {tool.name: _select_tooltip(tool) for tool in select_tools.TOOLS})
        for name, action_id in RAIL_ACTIONS.items():
            self.buttons[name].set_tooltips({name: _tooltip(name, action_id)})
        self.buttons[PEN_KEY].set_tooltips({name: _tooltip(name, aid) for name, aid in PEN_ACTIONS.items()})

    def _set_scene_tool(self, tool: str) -> None:
        if select_tools.is_select_tool(tool):
            select_tools.activate(tool)
        else:
            get_scene().set_tool(tool)

    def scene_tool(self) -> str:
        return self.tool_binding.value() or ""

    def active_tool(self) -> str:
        btn = self.button_groups[TOOLS].checkedButton()
        return btn.command_text() if btn is not None else ""

    def modeling_buttons(self) -> list:
        return list(self._modeling_buttons)

    def modeling_tool_ids(self) -> list[str]:
        return list(self._modeling)

    def scroll_bar(self):
        return self._scroll.verticalScrollBar()

    def arrows_visible(self) -> bool:
        return not self._up.isHidden()

    def _run(self, tool_id: str) -> None:
        modeling_install.activate_tool(tool_id)
        tool = get_scene().tool
        self._sync_modeling(tool)
        if tool not in self._modeling:
            self.tool_binding.show_value(tool)

    def _sync_modeling(self, tool: str) -> None:
        entry = self._modeling.get(tool)
        if entry is None:
            self._uncheck_modeling()
            return
        button, name, interactive = entry
        button.show_command(name)
        if interactive:
            with QSignalBlocker(self.button_groups[TOOLS]):
                button.setChecked(True)
        else:
            self._uncheck_modeling()

    def _uncheck_modeling(self) -> None:
        group = self.button_groups[TOOLS]
        for button in self._modeling_buttons:
            if button.isChecked():
                with QSignalBlocker(group):
                    group.setExclusive(False)
                    button.setChecked(False)
                    group.setExclusive(True)

    def _scroll_by(self, delta: int, _checked: bool = False) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.value() + delta)

    def _update_arrows(self, *_args) -> None:
        bar = self._scroll.verticalScrollBar()
        self._up.setEnabled(bar.value() > bar.minimum())
        self._down.setEnabled(bar.value() < bar.maximum())

    def _fit(self) -> None:
        lay = self.strip._layout
        fixed = 0
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item.spacerItem() is None:
                fixed += item.sizeHint().height()
        count = len(self._gap_items)
        margins = self._layout.contentsMargins()
        avail = self.height() - margins.top() - margins.bottom()
        gap = TOOL_GAP
        overflow = False
        if count and avail < fixed + count * TOOL_GAP:
            gap = max(TOOL_MIN_GAP, min(TOOL_GAP, (avail - fixed) // count))
            overflow = fixed + count * gap > avail
        for item in self._gap_items:
            item.spacerItem().changeSize(0, gap, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        lay.invalidate()
        self._up.setVisible(overflow)
        self._down.setVisible(overflow)
        self._update_arrows()
        if not overflow:
            self._scroll.verticalScrollBar().setValue(0)

    def resizeEvent(self, e: QResizeEvent) -> None:
        super().resizeEvent(e)
        self._fit()
