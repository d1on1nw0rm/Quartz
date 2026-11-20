from __future__ import annotations

import logging
from typing import Iterable, Sequence

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QIconEngine,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from quartz_studio import icons, theme

log = logging.getLogger("quartz_studio")

GroupEntry = tuple[str, str]

__all__ = [
    "Chip",
    "CollapsibleGroup",
    "FieldRow",
    "IconButton",
    "PanelMenuBar",
    "PanelTabBar",
    "Segment",
    "Separator",
    "ToggleSwitch",
    "add_menu_section",
    "is_card",
    "make_card",
    "prepare_popup",
    "check_row",
    "combo_row",
    "header_font",
    "prepare_combo",
    "restyle",
    "state_icon",
    "line_edit_row",
    "not_implemented",
    "populate_menu",
    "slider_row",
]


def not_implemented(name: str) -> None:
    log.info("not implemented: %s", name)


CARD_PROPERTY = "qsCard"


def make_card(widget: QWidget) -> QWidget:
    if not widget.property(CARD_PROPERTY):
        widget.setProperty(CARD_PROPERTY, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
    return widget


def is_card(widget: QWidget) -> bool:
    return bool(widget.property(CARD_PROPERTY))


POPUP_PROPERTY = "qsPopup"


def prepare_popup(menu: QMenu) -> QMenu:
    if not menu.property(POPUP_PROPERTY):
        menu.setProperty(POPUP_PROPERTY, True)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    return menu


def prepare_combo(combo: QComboBox) -> QComboBox:
    container = combo.view().window()
    if container is not combo.window() and not container.property(POPUP_PROPERTY):
        container.setProperty(POPUP_PROPERTY, True)
        container.setWindowFlags(container.windowFlags() | Qt.WindowType.FramelessWindowHint
                                 | Qt.WindowType.NoDropShadowWindowHint)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    return combo


def restyle(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def header_font(base: QFont | None = None) -> QFont:
    font = QFont(base) if base is not None else QFont(theme.FONT_FAMILY)
    font.setPointSizeF(theme.FONT_GROUP_POINT_SIZE)
    font.setWeight(QFont.Weight.DemiBold)
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, theme.HEADER_LETTER_SPACING)
    return font


class _StateIconEngine(QIconEngine):

    def __init__(self, name: str, color: str | None, group_mark: bool) -> None:
        super().__init__()
        self._name = name
        self._color = color
        self._group = group_mark

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        checked = state == QIcon.State.On
        disabled = mode == QIcon.Mode.Disabled
        color = theme.ACCENT if checked and not disabled else self._color
        icons.render(painter, QRectF(rect), self._name, color, self._group, disabled)

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pm

    def scaledPixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State,
                     scale: float) -> QPixmap:
        real = QSize(round(size.width() * scale), round(size.height() * scale))
        pm = self.pixmap(real, mode, state)
        pm.setDevicePixelRatio(scale)
        return pm

    def actualSize(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QSize:
        return size

    def clone(self) -> QIconEngine:
        return _StateIconEngine(self._name, self._color, self._group)

    def key(self) -> str:
        return "quartz_state_vector"


def state_icon(name: str, color: str | None = None, group_mark: bool = False) -> QIcon:
    return QIcon(_StateIconEngine(name, color, group_mark))


def add_menu_section(menu: QMenu, title: str) -> QWidgetAction:
    label = QLabel(title, menu)
    label.setObjectName("qsMenuSection")
    label.setFont(header_font(label.font()))
    action = QWidgetAction(menu)
    action.setDefaultWidget(label)
    action.setEnabled(False)
    menu.addAction(action)
    return action


def populate_menu(menu: QMenu, entries: Iterable) -> QMenu:
    for entry in entries:
        if isinstance(entry, str):
            entry = ("item", entry)
        kind = entry[0]
        if kind == "sep":
            menu.addSeparator()
        elif kind == "section":
            add_menu_section(menu, entry[1])
        elif kind == "submenu":
            text, children = entry[1], entry[2]
            icon_name = entry[3] if len(entry) > 3 else None
            enabled = entry[4] if len(entry) > 4 else True
            sub = menu.addMenu(text)
            prepare_popup(sub)
            if icon_name:
                sub.setIcon(icons.icon(icon_name, theme.MENU_ICON))
            sub.setEnabled(bool(enabled))
            populate_menu(sub, children)
        elif kind == "item":
            text = entry[1]
            shortcut = entry[2] if len(entry) > 2 else None
            icon_name = entry[3] if len(entry) > 3 else None
            enabled = entry[4] if len(entry) > 4 else True
            label = f"{text}\t{shortcut}" if shortcut else text
            action = QAction(label, menu)
            if icon_name:
                action.setIcon(icons.icon(icon_name, theme.MENU_ICON))
            action.setEnabled(bool(enabled))
            action.triggered.connect(lambda _=False, t=text: not_implemented(t))
            menu.addAction(action)
        else:
            log.warning("unknown menu entry %r", entry)
    return menu



class IconButton(QToolButton):

    commandChosen = Signal(str)
    HOLD_MS = 380

    def __init__(self, icon_name: str = "", tooltip: str = "", checkable: bool = False,
                 parent: QWidget | None = None, *, group: Sequence | None = None,
                 size: int | None = None, icon_size: int | None = None,
                 color: str | None = None, enabled: bool = True, flat: bool = False,
                 popup_side: str = "auto") -> None:
        super().__init__(parent)
        self.setObjectName("qsIconButton")
        self.setProperty("flat", "true" if flat else "false")
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._size = size or theme.COMMAND_BUTTON
        self._icon_px = icon_size or theme.COMMAND_ICON
        self._color = color
        self._popup_side = popup_side
        self.group_mark_color: str = icons.GROUP_MARK_COLOR
        self._group: list[GroupEntry] = self._normalise_group(group)
        self._icon_name = icon_name or (self._group[0][0] if self._group else "")
        self._text = tooltip or (self._group[0][1] if self._group else "")
        self._held = False
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.setInterval(self.HOLD_MS)
        self._hold_timer.timeout.connect(self._on_hold)
        self.setFixedSize(self._size, self._size)
        self.setIconSize(QSize(self._icon_px, self._icon_px))
        self.setCheckable(checkable)
        self.setEnabled(enabled)
        self._refresh()
        self.clicked.connect(self._on_clicked)

    def icon_name(self) -> str:
        return self._icon_name

    def popup_side(self) -> str:
        return self._popup_side

    def set_popup_side(self, side: str) -> None:
        self._popup_side = side

    def command_text(self) -> str:
        return self._text

    def group(self) -> list[GroupEntry]:
        return list(self._group)

    def set_group(self, group: Sequence | None) -> None:
        self._group = self._normalise_group(group)
        self._refresh()

    def set_command(self, icon_name: str, text: str) -> None:
        self._icon_name = icon_name
        self._text = text
        self._refresh()

    def set_icon_color(self, color: str | None) -> None:
        self._color = color
        self._refresh()

    def open_group_menu(self) -> None:
        if not self._group:
            return
        menu = prepare_popup(QMenu(self))
        menu.setObjectName("qsFoldout")
        for entry in self._group:
            if entry is None:
                menu.addSeparator()
                continue
            name, text = entry
            act = menu.addAction(icons.icon(name, theme.MENU_ICON), text)
            act.setCheckable(False)
            act.triggered.connect(lambda _=False, n=name, t=text: self._choose(n, t))
        menu.exec(self._popup_pos(menu))
        self.setDown(False)

    @staticmethod
    def _normalise_group(group: Sequence | None) -> list:
        out: list = []
        for item in group or []:
            if item is None or item == "sep":
                out.append(None)
            elif isinstance(item, str):
                out.append(("", item))
            elif isinstance(item, dict):
                out.append((item.get("icon", ""), item.get("name") or item.get("text", "")))
            else:
                out.append((item[0], item[1]))
        return out

    def _refresh(self) -> None:
        has_group = any(e is not None for e in self._group)
        self.setIcon(state_icon(self._icon_name, self._color))
        self.setToolTip(self._text)
        self.setStatusTip(self._text)
        self.setAccessibleName(self._text)
        self._has_group = has_group
        self.update()

    def _choose(self, name: str, text: str) -> None:
        self.set_command(name, text)
        self.commandChosen.emit(text)
        not_implemented(text)

    def _on_clicked(self) -> None:
        if self._text:
            not_implemented(self._text)

    def _on_hold(self) -> None:
        self._held = True
        self.open_group_menu()

    def _in_triangle(self, pos: QPoint) -> bool:
        zone = max(7, self.width() // 3)
        return pos.x() >= self.width() - zone and pos.y() >= self.height() - zone

    def _popup_pos(self, menu: QMenu) -> QPoint:
        side = self._popup_side
        if side == "auto":
            parent = self.parentWidget()
            side = "right" if parent is not None and parent.height() > parent.width() * 2 else "below"
        if side == "right":
            return self.mapToGlobal(QPoint(self.width() + 1, 0))
        if side == "left":
            return self.mapToGlobal(QPoint(-menu.sizeHint().width() - 1, 0))
        if side == "above":
            return self.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 1))
        return self.mapToGlobal(QPoint(0, self.height() + 1))

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if self._has_group and e.button() == Qt.MouseButton.LeftButton:
            if self._in_triangle(e.position().toPoint()):
                e.accept()
                self.open_group_menu()
                return
            self._held = False
            from quartz_studio import controls

            self._hold_timer.setInterval(int(controls.cursor("hold_ms")))
            self._hold_timer.start()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._hold_timer.stop()
        if self._held:
            self._held = False
            self.setDown(False)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def paintEvent(self, e: QPaintEvent) -> None:
        super().paintEvent(e)
        if self._has_group:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if not self.isEnabled():
                p.setOpacity(icons.DISABLED_OPACITY)
            m = 1.5
            icons.draw_group_mark(p, QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m),
                                  self.group_mark_color)
            p.end()

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)


class Separator(QWidget):

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Vertical,
                 parent: QWidget | None = None, *, line: bool = False,
                 gap: int = theme.SEPARATOR_GAP, color: str = theme.HAIRLINE) -> None:
        super().__init__(parent)
        self._orientation = orientation
        self._line = line
        self._color = QColor(color)
        if orientation == Qt.Orientation.Vertical:
            self.setFixedWidth(gap)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        else:
            self.setFixedHeight(gap)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def paintEvent(self, e: QPaintEvent) -> None:
        if not self._line:
            return
        p = QPainter(self)
        p.setPen(self._color)
        if self._orientation == Qt.Orientation.Vertical:
            x = self.width() // 2
            p.drawLine(x, 3, x, self.height() - 4)
        else:
            y = self.height() // 2
            p.drawLine(0, y, self.width(), y)
        p.end()


class Segment(QFrame):

    DIVIDER_COLOR = theme.HAIRLINE

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal,
                 parent: QWidget | None = None, *, dividers: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("qsSegment")
        self._orientation = orientation
        self._dividers = dividers
        if orientation == Qt.Orientation.Horizontal:
            lay = QHBoxLayout(self)
        else:
            lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._layout = lay

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    addWidget = add

    def paintEvent(self, e: QPaintEvent) -> None:
        super().paintEvent(e)
        if not self._dividers or self.property("qsRole") == "modes":
            return
        cells = [self._layout.itemAt(i).widget() for i in range(self._layout.count())]
        cells = [w for w in cells if w is not None and not w.isHidden()]
        p = QPainter(self)
        p.setPen(QColor(self.DIVIDER_COLOR))
        for w in cells[1:]:
            g = w.geometry()
            if self._orientation == Qt.Orientation.Horizontal:
                p.drawLine(g.left(), 0, g.left(), self.height() - 1)
            else:
                p.drawLine(0, g.top(), self.width() - 1, g.top())
        p.end()


class Chip(QPushButton):

    def __init__(self, text: str, parent: QWidget | None = None, checked: bool = False) -> None:
        super().__init__(text, parent)
        self.setObjectName("qsChip")
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)


class ToggleSwitch(QAbstractButton):

    qs_feedback_look = ("capsule", 0.0, 0.0, 1.0)

    def __init__(self, parent: QWidget | None = None, checked: bool = False) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(30, 16)
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        on = self.isChecked()
        if on:
            track = theme.ACCENT_PRESSED if self.isDown() else (
                theme.ACCENT_HOVER if self._hover else theme.ACCENT)
        else:
            track = theme.SURFACE_PRESSED if self.isDown() else (
                theme.SURFACE_HOVER if self._hover else theme.SURFACE_RAISED)
        if not self.isEnabled():
            p.setOpacity(0.5)
        p.setPen(Qt.PenStyle.NoPen if on else QColor(theme.HAIRLINE))
        p.setBrush(QColor(track))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.right() - d - 3 if on else r.left() + 3
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT_ON if on else theme.TEXT_SECONDARY))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(30, 16)



PANEL_TAB_SPACING = theme.SPACE_1


class PanelTabBar(QWidget):

    currentChanged = Signal(int)

    def __init__(self, tabs: Sequence[str] = (), parent: QWidget | None = None,
                 current: int = 0) -> None:
        super().__init__(parent)
        self.setObjectName("qsPanelTabBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(theme.CARD_HEADER_H)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(theme.SPACE_1, 0, theme.SPACE_1, 0)
        self._layout.setSpacing(PANEL_TAB_SPACING)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._on_clicked)
        self._buttons: list[QPushButton] = []
        self._layout.addStretch(1)
        for text in tabs:
            self.add_tab(text)
        if self._buttons:
            self.setCurrentIndex(current)

    def add_tab(self, text: str) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setObjectName("qsPanelTab")
        btn.setCheckable(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFont(header_font(btn.font()))
        idx = len(self._buttons)
        self._group.addButton(btn, idx)
        self._layout.insertWidget(idx, btn)
        self._buttons.append(btn)
        multi = "true" if len(self._buttons) > 1 else "false"
        for b in self._buttons:
            b.setProperty("multi", multi)
            restyle(b)
        return btn

    def add_right_widget(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def tab_texts(self) -> list[str]:
        return [b.text() for b in self._buttons]

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)

    def _on_clicked(self, idx: int) -> None:
        self.currentChanged.emit(idx)


PANEL_RIGHT_BUTTON = theme.PANEL_MENU_H
PANEL_RIGHT_COLOR = theme.TEXT_SECONDARY
PANEL_RIGHT_ICON = 18


class PanelMenuBar(QWidget):

    def __init__(self, menus: Sequence = (), right_icons: Sequence = (),
                 parent: QWidget | None = None, *, hamburger: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("qsPanelMenuBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(theme.PANEL_MENU_H)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(theme.SPACE_1, 0, theme.SPACE_1, 0)
        self._layout.setSpacing(theme.SPACE_1 // 2)
        self.hamburger: IconButton | None = None
        if hamburger:
            self.hamburger = IconButton("hamburger", "Menu", parent=self, size=theme.PANEL_MENU_H,
                                        icon_size=14, flat=True, color=theme.TEXT_SECONDARY)
            self._layout.addWidget(self.hamburger)
            self._layout.addSpacing(theme.SPACE_1)
        self._menus_end = self._layout.count()
        self._layout.addStretch(1)
        self.menus: dict[str, QMenu] = {}
        self.right_buttons: list[IconButton] = []
        for m in menus:
            if isinstance(m, str):
                self.add_menu(m)
            else:
                self.add_menu(*m)
        for r in right_icons:
            if isinstance(r, str):
                self.add_right_icon(r)
            else:
                self.add_right_icon(*r)

    def add_menu(self, text: str, entries: Iterable | None = None,
                 highlight: bool = False) -> QMenu:
        btn = QPushButton(text, self)
        btn.setObjectName("qsPanelMenu")
        btn.setProperty("highlight", "true" if highlight else "false")
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        menu = prepare_popup(QMenu(btn))
        populate_menu(menu, entries or [("item", text, None, None, False)])
        btn.setMenu(menu)
        self._layout.insertWidget(self._menus_end, btn)
        self._menus_end += 1
        self.menus[text] = menu
        return menu

    def add_right_icon(self, icon_name: str, tooltip: str = "", enabled: bool = True,
                       checkable: bool = False) -> IconButton:
        btn = IconButton(icon_name, tooltip, checkable, self, size=PANEL_RIGHT_BUTTON,
                         icon_size=PANEL_RIGHT_ICON, color=PANEL_RIGHT_COLOR,
                         enabled=enabled, flat=True)
        self._layout.addWidget(btn)
        self.right_buttons.append(btn)
        return btn

    def add_right_widget(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget



class _GroupHeader(QWidget):

    clicked = Signal()
    hovered = Signal(bool)
    qs_feedback_look = ("rect", 0.0, 1.0, 0.75)

    def enterEvent(self, e) -> None:
        self.hovered.emit(True)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self.hovered.emit(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class CollapsibleGroup(QWidget):

    toggled = Signal(bool)

    def __init__(self, title: str, parent: QWidget | None = None, expanded: bool = True,
                 separator: bool = True) -> None:
        super().__init__(parent)
        self._expanded = expanded
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = _GroupHeader(self)
        self.header.setFixedHeight(theme.ROW_H)
        self.header.setCursor(Qt.CursorShape.ArrowCursor)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(theme.SPACE_3, 0, theme.SPACE_2 - 2, 0)
        hl.setSpacing(theme.SPACE_2 - 2)
        self.chevron = QLabel(self.header)
        self.chevron.setFixedSize(10, 10)
        self.title_label = QLabel(title.upper(), self.header)
        self.title_label.setObjectName("qsGroupTitle")
        self.title_label.setFont(header_font(self.title_label.font()))
        hl.addWidget(self.chevron)
        hl.addWidget(self.title_label)
        hl.addStretch(1)
        outer.addWidget(self.header)
        self.body = QWidget(self)
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, 2, 0, 8)
        self._body_layout.setSpacing(3)
        outer.addWidget(self.body)
        if separator:
            line = Separator(Qt.Orientation.Horizontal, self, line=True, gap=1,
                             color=theme.GROUP_LINE)
            outer.addWidget(line)
        self._hover = False
        self.header.clicked.connect(self.toggle)
        self.header.hovered.connect(self._set_hover)
        self._apply()

    def content_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_widget(self, widget: QWidget) -> QWidget:
        self._body_layout.addWidget(widget)
        return widget

    addWidget = add_widget

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._apply()
        self.toggled.emit(expanded)

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def _set_hover(self, hover: bool) -> None:
        if hover == self._hover:
            return
        self._hover = hover
        self.title_label.setProperty("qsHover", "true" if hover else "false")
        restyle(self.title_label)
        self._apply()

    def _apply(self) -> None:
        name = "chevron_down" if self._expanded else "chevron_right"
        color = theme.TEXT_PRIMARY if self._hover else theme.TEXT_SECONDARY
        self.chevron.setPixmap(icons.pixmap(name, 10, color, device_pixel_ratio=self.devicePixelRatioF()))
        self.body.setVisible(self._expanded)


class FieldRow(QWidget):

    LABEL_WIDTH = 112
    INDENT = 34

    def __init__(self, label: str, editor: QWidget | None = None,
                 parent: QWidget | None = None, *, label_width: int | None = None,
                 indent: int | None = None, enabled: bool = True) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(self.INDENT if indent is None else indent, 0, 8, 0)
        lay.setSpacing(6)
        self.label = QLabel(label, self)
        self.label.setObjectName("qsDimLabel")
        self.label.setFixedWidth(self.LABEL_WIDTH if label_width is None else label_width)
        lay.addWidget(self.label)
        self._layout = lay
        self.editor: QWidget | None = None
        self.setFixedHeight(theme.FIELD_H + 2)
        if editor is not None:
            self.editor = editor
            lay.addWidget(editor, 1)
        self.setEnabled(enabled)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._layout.addWidget(widget, stretch)
        return widget

    def add_stretch(self, stretch: int = 1) -> None:
        self._layout.addStretch(stretch)


def line_edit_row(label: str, text: str = "", parent: QWidget | None = None,
                  **kw) -> FieldRow:
    edit = QLineEdit(text)
    return FieldRow(label, edit, parent, **kw)


def combo_row(label: str, items: Sequence[str], current: int = 0,
              parent: QWidget | None = None, **kw) -> FieldRow:
    combo = QComboBox()
    combo.addItems(list(items))
    combo.setCurrentIndex(current)
    combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    prepare_combo(combo)
    return FieldRow(label, combo, parent, **kw)


def check_row(label: str, checked: bool = False, parent: QWidget | None = None,
              **kw) -> FieldRow:
    row = FieldRow(label, None, parent, **kw)
    box = QCheckBox()
    box.setChecked(checked)
    box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    row.editor = box
    row.add_widget(box)
    row.add_stretch(1)
    return row


def slider_row(label: str, value_text: str = "0 %", value: int = 0,
               parent: QWidget | None = None, *, field_width: int = 76, **kw) -> FieldRow:
    edit = QLineEdit(value_text)
    edit.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    edit.setFixedWidth(field_width)
    row = FieldRow(label, None, parent, **kw)
    row.editor = edit
    row.add_widget(edit)
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(value)
    slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    row.slider = slider
    row.add_widget(slider, 1)
    return row
