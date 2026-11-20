from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

from quartz_studio import DOCUMENT_NAME, icons, theme
from quartz_studio.widgets import menus_data
from quartz_studio.widgets.common import not_implemented
from quartz_studio.widgets.menu_bar import StudioMenu, menu_font

__all__ = ["DocumentTab", "GlyphButton", "LayoutTab", "TitleRow"]

ROW_H = theme.TITLE_ROW_H
LEFT_MARGIN = 10
GLYPH_W = 19
HOME_GAP = 13
DOC_GAP = 16
DOC_TAB_W = 112
DOC_TEXT_X = 12
DOC_CLOSE_CX = 99
PLUS_GAP = 8
LAYOUT_PAD = 20
KEBAB_GAP = 13
KEBAB_W = 26
RIGHT_MARGIN = 25
UNDERLINE_H = 2
UNDERLINE_EXTRA = 6

COL_ROW_BG = theme.BG_TITLE
COL_DOC_BG = theme.BG_TAB_ACTIVE
COL_DOC_HOVER_BG = theme.SURFACE_HOVER
COL_DOC_PRESSED_BG = theme.SURFACE_PRESSED
COL_DOC_TEXT = theme.TEXT_PRIMARY
COL_GLYPH = theme.ICON_STROKE
COL_GLYPH_HOVER_BG = theme.SURFACE_HOVER
COL_GLYPH_PRESSED_BG = theme.SURFACE_PRESSED
COL_UNDO = theme.TEXT_MUTED
COL_HOME = theme.TEXT_MUTED
COL_KEBAB = theme.TEXT_SECONDARY
COL_LAYOUT_TEXT = theme.TEXT_SECONDARY
COL_LAYOUT_HOVER = theme.TEXT_PRIMARY
COL_LAYOUT_ACTIVE = theme.ACCENT
LAYOUT_PRESSED_DARKER = 135
COL_UNDERLINE = theme.ACCENT_UNDERLINE



def _pen(p: QPainter, c: QColor, w: float) -> None:
    p.setPen(QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)


def _unit(fn):
    def wrapped(p: QPainter, r: QRectF, c: QColor) -> None:
        p.save()
        side = min(r.width(), r.height())
        p.translate(r.x() + (r.width() - side) / 2, r.y() + (r.height() - side) / 2)
        p.scale(side / 24.0, side / 24.0)
        fn(p, c)
        p.restore()
    return wrapped


def _g_undo(p: QPainter, c: QColor) -> None:
    _pen(p, c, 1.6)
    path = QPainterPath(QPointF(8.2, 9.5))
    path.lineTo(QPointF(13.6, 9.5))
    path.arcTo(QRectF(10.1, 9.5, 7.0, 7.0), 90, -180)
    path.lineTo(QPointF(8.0, 16.5))
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(5.2, 9.5), QPointF(8.8, 6.9), QPointF(8.8, 12.1)]))


def _g_redo(p: QPainter, c: QColor) -> None:
    p.translate(24, 0)
    p.scale(-1, 1)
    _g_undo(p, c)


def _g_home(p: QPainter, c: QColor) -> None:
    _pen(p, c, 1.5)
    path = QPainterPath(QPointF(7, 18.2))
    path.lineTo(QPointF(7, 11.2))
    path.lineTo(QPointF(12, 6.4))
    path.lineTo(QPointF(17, 11.2))
    path.lineTo(QPointF(17, 18.2))
    path.lineTo(QPointF(14, 18.2))
    path.lineTo(QPointF(14, 14.6))
    path.arcTo(QRectF(10, 12.6, 4, 4), 0, 180)
    path.lineTo(QPointF(10, 18.2))
    path.closeSubpath()
    p.drawPath(path)


def _g_close(p: QPainter, c: QColor) -> None:
    _pen(p, c, 2.2)
    p.drawLine(QPointF(8.6, 8.6), QPointF(15.4, 15.4))
    p.drawLine(QPointF(15.4, 8.6), QPointF(8.6, 15.4))


def _g_plus(p: QPainter, c: QColor) -> None:
    _pen(p, c, 2.3)
    p.drawLine(QPointF(12, 7), QPointF(12, 17))
    p.drawLine(QPointF(7, 12), QPointF(17, 12))


def _g_kebab(p: QPainter, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    for y in (6.2, 12.0, 17.8):
        p.drawEllipse(QPointF(12, y), 2.0, 2.0)


for _name, _fn in (("tr_undo", _g_undo), ("tr_redo", _g_redo), ("tr_home", _g_home),
                   ("tr_close", _g_close), ("tr_plus", _g_plus), ("tr_kebab", _g_kebab)):
    if not icons.has(_name):
        icons.register(_name, _unit(_fn))


def _doc_font() -> QFont:
    f = QFont(theme.FONT_FAMILY)
    f.setPointSizeF(9)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


class GlyphButton(QAbstractButton):

    def __init__(self, icon_name: str, tooltip: str = "", parent: QWidget | None = None, *,
                 width: int = GLYPH_W, height: int = ROW_H, icon_size: int = 16,
                 color: str | None = None, enabled: bool = True, hover_bg: bool = True) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._color = color
        self._hover_bg = hover_bg
        self._hover = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(width, height)
        self.setToolTip(tooltip)
        self.setStatusTip(tooltip)
        self.setAccessibleName(tooltip or icon_name)
        self.setEnabled(enabled)
        if tooltip:
            self.clicked.connect(lambda: not_implemented(tooltip))

    def icon_name(self) -> str:
        return self._icon_name

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def sizeHint(self) -> QSize:
        return self.size()

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        s = self._icon_size
        if self.isEnabled() and self._hover_bg and (self._hover or self.isDown()):
            box = min(self.width(), s + 6)
            bg = QRectF((self.width() - box) / 2, (self.height() - box) / 2, box, box)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(COL_GLYPH_PRESSED_BG if self.isDown() else COL_GLYPH_HOVER_BG))
            p.drawRoundedRect(bg, 3, 3)
        color = self._color
        if self.isEnabled() and self._hover and color is not None:
            color = QColor(color).lighter(135).name()
        rect = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        icons.render(p, rect, self._icon_name, color, disabled=False)
        p.end()


class DocumentTab(QWidget):

    closeRequested = Signal()
    activated = Signal()

    def __init__(self, title: str = DOCUMENT_NAME, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._hover = False
        self._pressed = False
        self.setFixedSize(DOC_TAB_W, ROW_H)
        self.setToolTip(title)
        self.close_button = GlyphButton("tr_close", "Close Project", self, width=16, height=16,
                                        icon_size=24, color=COL_GLYPH)
        self.close_button.move(DOC_CLOSE_CX - 8, 1 + (ROW_H - 1 - 16) // 2)
        self.close_button.clicked.connect(self.closeRequested)
        self._menu = StudioMenu("", self, menus_data.DOCUMENT_TAB_MENU)

    def title(self) -> str:
        return self._title

    def set_title(self, title: str) -> None:
        self._title = title
        self.setToolTip(title)
        self.update()

    def is_hovered(self) -> bool:
        return self._hover

    def is_pressed(self) -> bool:
        return self._pressed

    def background_color(self) -> QColor:
        if self._pressed:
            return QColor(COL_DOC_PRESSED_BG)
        if self._hover:
            return QColor(COL_DOC_HOVER_BG)
        return QColor(COL_DOC_BG)

    def _set_pressed(self, pressed: bool) -> None:
        if pressed != self._pressed:
            self._pressed = pressed
            self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._set_pressed(True)
            self.activated.emit()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._set_pressed(self.rect().contains(e.position().toPoint()))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._set_pressed(False)
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:
        self._menu.exec(e.globalPos())

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def hideEvent(self, e) -> None:
        self._hover = False
        self._pressed = False
        super().hideEvent(e)

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.fillRect(QRect(0, 1, self.width(), self.height() - 1), self.background_color())
        p.setFont(_doc_font())
        p.setPen(QColor(COL_DOC_TEXT))
        text_w = DOC_CLOSE_CX - 8 - DOC_TEXT_X - 2
        fm = QFontMetrics(p.font())
        text = fm.elidedText(self._title, Qt.TextElideMode.ElideRight, text_w)
        p.drawText(QRect(DOC_TEXT_X, 1, text_w, self.height() - 1),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        p.end()


class LayoutTab(QAbstractButton):

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(f"Layout: {text}")
        self.setAccessibleName(text)
        self._hover = False
        self.setFixedHeight(ROW_H)
        self.setFixedWidth(self._natural_width())
        self.toggled.connect(lambda _c: self.update())

    def _font(self) -> QFont:
        f = menu_font()
        return f

    def _natural_width(self) -> int:
        return round(QFontMetrics(self._font()).horizontalAdvance(self.text())) + 2 * LAYOUT_PAD

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def sizeHint(self) -> QSize:
        return QSize(self._natural_width(), ROW_H)

    def text_color(self) -> QColor:
        if self.isChecked():
            col = QColor(COL_LAYOUT_ACTIVE)
        elif self._hover:
            col = QColor(COL_LAYOUT_HOVER)
        else:
            col = QColor(COL_LAYOUT_TEXT)
        return col.darker(LAYOUT_PRESSED_DARKER) if self.isDown() else col

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        f = self._font()
        checked = self.isChecked()
        f.setItalic(checked)
        if checked:
            f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(self.text())
        x0 = (self.width() - tw) // 2
        p.setPen(self.text_color())
        p.drawText(QRect(x0, 0, tw + 4, self.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        if checked:
            p.fillRect(QRect(x0 - UNDERLINE_EXTRA, self.height() - UNDERLINE_H,
                             tw + 2 * UNDERLINE_EXTRA, UNDERLINE_H), QColor(COL_UNDERLINE))
        p.end()


class TitleRow(QWidget):

    layoutChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None,
                 layouts: Iterable[str] | None = None,
                 active: str = menus_data.ACTIVE_LAYOUT) -> None:
        super().__init__(parent)
        self.setObjectName("qsTitleRow")
        self.setFixedHeight(ROW_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(LEFT_MARGIN, 0, RIGHT_MARGIN, 0)
        lay.setSpacing(0)

        self.undo_button = GlyphButton("tr_undo", "Undo", self, icon_size=24, color=COL_UNDO)
        self.redo_button = GlyphButton("tr_redo", "Redo", self, icon_size=24, color=COL_UNDO)
        self.home_button = GlyphButton("tr_home", "Home", self, icon_size=24,
                                       color=COL_HOME)
        lay.addWidget(self.undo_button)
        lay.addWidget(self.redo_button)
        lay.addSpacing(HOME_GAP)
        lay.addWidget(self.home_button)
        lay.addSpacing(DOC_GAP)

        self.document_tab = DocumentTab(DOCUMENT_NAME, self)
        self.document_tab.closeRequested.connect(lambda: not_implemented("Close Project"))
        lay.addWidget(self.document_tab)
        lay.addSpacing(PLUS_GAP)
        self.new_tab_button = GlyphButton("tr_plus", "New Project", self, width=20,
                                          icon_size=24, color=COL_GLYPH)
        lay.addWidget(self.new_tab_button)
        lay.addStretch(1)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.layout_tabs: dict[str, LayoutTab] = {}
        for name in (layouts if layouts is not None else menus_data.LAYOUTS):
            tab = LayoutTab(name, self)
            self._group.addButton(tab)
            self.layout_tabs[name] = tab
            lay.addWidget(tab)
            tab.clicked.connect(lambda _=False, n=name: self._on_layout_clicked(n))
        lay.addSpacing(KEBAB_GAP)

        self.layout_menu = StudioMenu("", self, menus_data.LAYOUT_MENU)
        self.kebab_button = GlyphButton("tr_kebab", "Layouts", self, width=KEBAB_W,
                                        icon_size=24, color=COL_KEBAB)
        self.kebab_button.clicked.connect(self._open_layout_menu)
        lay.addWidget(self.kebab_button)

        self.set_active_layout(active)

    def active_layout(self) -> str:
        btn = self._group.checkedButton()
        return btn.text() if btn is not None else ""

    def set_active_layout(self, name: str) -> None:
        tab = self.layout_tabs.get(name)
        if tab is not None:
            tab.setChecked(True)

    def layout_names(self) -> list[str]:
        return list(self.layout_tabs)

    def _on_layout_clicked(self, name: str) -> None:
        self.set_active_layout(name)
        self.layoutChanged.emit(name)

    def _open_layout_menu(self) -> None:
        menu = self.layout_menu
        btn = self.kebab_button
        x = btn.width() - menu.sizeHint().width()
        menu.exec(btn.mapToGlobal(QPoint(x, btn.height())))

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(COL_ROW_BG))
        p.end()
