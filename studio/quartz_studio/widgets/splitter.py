from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QSplitter, QSplitterHandle, QWidget

from quartz_studio import theme

__all__ = ["StudioSplitter", "StudioSplitterHandle", "SHORT_HANDLE", "SHORT_INSET", "BAR_RADIUS"]

SHORT_HANDLE = 80
SHORT_INSET = 8
BAR_RADIUS = 2


class StudioSplitterHandle(QSplitterHandle):

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self._hover = False
        self._drag = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._sync_cursor()

    def state(self) -> str:
        if not self.isEnabled():
            return "idle"
        if self._drag:
            return "drag"
        if self._hover:
            return "hover"
        return "idle"

    def _split_cursor(self) -> Qt.CursorShape:
        if self.orientation() == Qt.Orientation.Horizontal:
            return Qt.CursorShape.SplitHCursor
        return Qt.CursorShape.SplitVCursor

    def _sync_cursor(self) -> None:
        if self.isEnabled():
            self.setCursor(self._split_cursor())
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def setOrientation(self, orientation: Qt.Orientation) -> None:
        super().setOrientation(orientation)
        self._sync_cursor()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            if not self.isEnabled():
                self._hover = False
                self._drag = False
            self._sync_cursor()
            self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:
        self._hover = False
        super().leaveEvent(event)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = True
        super().mousePressEvent(event)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = False
        super().mouseReleaseEvent(event)
        self.update()

    def bar_rect(self) -> QRectF:
        horizontal = self.orientation() == Qt.Orientation.Horizontal
        length = self.height() if horizontal else self.width()
        across = self.width() if horizontal else self.height()
        inset = theme.SPLITTER_BAR_INSET if length >= SHORT_HANDLE else SHORT_INSET
        span = max(0, length - 2 * inset)
        offset = (across - theme.SPLITTER_BAR) / 2
        if horizontal:
            return QRectF(offset, inset, theme.SPLITTER_BAR, span)
        return QRectF(inset, offset, span, theme.SPLITTER_BAR)

    def paintEvent(self, event: QPaintEvent) -> None:
        state = self.state()
        if state == "idle":
            return
        rect = self.bar_rect()
        if rect.isEmpty():
            return
        color = theme.SPLITTER_DRAG if state == "drag" else theme.SPLITTER_HOVER
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(rect, BAR_RADIUS, BAR_RADIUS)
        p.end()


class StudioSplitter(QSplitter):

    widgetsChanged = Signal()

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self.setHandleWidth(theme.CARD_GAP)
        self.setChildrenCollapsible(False)

    def createHandle(self) -> QSplitterHandle:
        return StudioSplitterHandle(self.orientation(), self)

    def addWidget(self, widget: QWidget) -> None:
        super().addWidget(widget)
        self.widgetsChanged.emit()

    def insertWidget(self, index: int, widget: QWidget) -> None:
        super().insertWidget(index, widget)
        self.widgetsChanged.emit()
