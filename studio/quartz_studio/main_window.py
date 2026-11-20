from __future__ import annotations

import importlib
import logging
import math
import os
import sys

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QPainter,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quartz_studio import WINDOW_TITLE, icons, project, theme
from quartz_studio.widgets.common import make_card
from quartz_studio.widgets.splitter import StudioSplitter

log = logging.getLogger("quartz_studio.main_window")

RIGHT_COLUMN_RATIO = 370 / 1456
RIGHT_COLUMN_MIN = 300
ATTRIBUTE_SHARE = 0.26
ATTRIBUTE_FRACTION = 0.58
ATTRIBUTE_FIRST_ROW = 44

REGIONS: dict[str, tuple[str, str, tuple]] = {
    "menu_bar": ("quartz_studio.widgets.menu_bar", "MenuBar", ("h", theme.MENU_BAR_H)),
    "command_bar": ("quartz_studio.widgets.command_bar", "CommandBar", ("h", theme.COMMAND_BAR_H)),
    "tool_palette": ("quartz_studio.widgets.tool_palette", "ToolPalette", ("w", theme.RAIL_W)),
    "viewport": ("quartz_studio.widgets.viewport", "Viewport", ("x", 400, 300)),
    "object_palette": ("quartz_studio.widgets.object_palette", "ObjectPalette", ("h", theme.DOCK_H)),
    "object_manager": ("quartz_studio.widgets.object_manager", "ObjectManager", ("x", 260, 120)),
    "attribute_manager": ("quartz_studio.widgets.attribute_manager", "AttributeManager", ("x", 260, 120)),
    "coordinates": ("quartz_studio.widgets.coordinates", "CoordinatesManager", ("x", 260, theme.COORDINATES_H)),
    "status_bar": ("quartz_studio.widgets.status_bar", "StatusBar", ("h", theme.STATUS_BAR_H)),
}

CARD_REGIONS = ("tool_palette", "viewport", "object_manager", "attribute_manager", "coordinates")

PLACEHOLDER_BG: dict[str, str] = {
    "Viewport": theme.BG_VIEWPORT_TOP,
    "ObjectManager": theme.BG_PANEL,
    "AttributeManager": theme.BG_PANEL,
    "CoordinatesManager": theme.BG_PANEL,
}


class Placeholder(QFrame):

    def __init__(self, class_name: str, geometry: tuple, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsPlaceholder")
        self.class_name = class_name
        bg = PLACEHOLDER_BG.get(class_name, theme.BG_WINDOW)
        self.setStyleSheet(f"QFrame#qsPlaceholder {{ background: {bg}; border: 1px dashed {theme.HAIRLINE}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        vertical_strip = geometry[0] == "w"
        text = class_name if geometry[0] != "x" else f"{class_name}\n(module pending)"
        label = QLabel("\n".join(class_name[:6]) if vertical_strip else text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(label)
        kind = geometry[0]
        if kind == "h":
            self.setFixedHeight(geometry[1])
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        elif kind == "w":
            self.setFixedWidth(geometry[1])
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setMinimumSize(geometry[1], geometry[2])
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


def load_region(attr: str, parent: QWidget | None = None) -> QWidget:
    module_name, class_name, geometry = REGIONS[attr]
    try:
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        widget = cls(parent)
        if not isinstance(widget, QWidget):
            raise TypeError(f"{class_name} is not a QWidget")
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            log.exception("region %s: dependency missing", attr)
        else:
            log.info("region %s: module %s not available yet", attr, module_name)
        widget = Placeholder(class_name, geometry, parent)
    except Exception:
        log.exception("region %s: failed to build %s", attr, class_name)
        widget = Placeholder(class_name, geometry, parent)
    widget.setObjectName(widget.objectName() or f"qs_{attr}")
    return widget


MODEL_PAGE = "model"
MODEL_PAGE_TITLE = "Model"
DOCK_AREAS = ("bottom", "left", "right")
LEFT_DOCK_W = 256
PAGE_BUTTON_H = theme.SEGMENT_H - 2 * theme.SEGMENT_PAD
PAGE_RADIUS = theme.SEGMENT_H // 2 - theme.SEGMENT_PAD
PAGE_MARGIN = theme.SEGMENT_PAD - theme.SEGMENT_BORDER
PAGE_BUTTON_PAD = theme.SPACE_3
PAGE_CHEVRON = 12
PAGE_CHEVRON_GAP = 2
PAGE_CHEVRON_RIGHT = 11
PAGE_TEXT_LIFT = 2
PAGE_COMPACT_RIGHT = PAGE_CHEVRON_RIGHT + PAGE_CHEVRON + PAGE_CHEVRON_GAP
TOP_ROW_GAP = theme.SPACE_2


def _page_switcher_qss() -> str:
    pill = PAGE_RADIUS
    return f"""
QFrame#qsPageSwitcher {{
    background: {theme.SURFACE_CARD};
    border: 1px solid {theme.HAIRLINE};
    border-radius: {theme.SEGMENT_H // 2}px;
}}
QToolButton#qsPageButton {{
    background: transparent;
    border: none;
    border-radius: {pill}px;
    color: {theme.TEXT_SECONDARY};
    padding: 0px {PAGE_BUTTON_PAD}px {PAGE_TEXT_LIFT}px {PAGE_BUTTON_PAD}px;
}}
QToolButton#qsPageButton:hover {{
    background: {theme.SURFACE_HOVER};
    color: {theme.TEXT_PRIMARY};
}}
QToolButton#qsPageButton:pressed {{
    background: {theme.SURFACE_PRESSED};
}}
QToolButton#qsPageButton:checked {{
    background: {theme.ACCENT_TINT};
    color: {theme.ACCENT};
}}
QToolButton#qsPageButton:checked:hover {{
    background: {theme.ACCENT_TINT_HOVER};
}}
QToolButton#qsPageCompact {{
    background: {theme.ACCENT_TINT};
    border: none;
    border-radius: {pill}px;
    color: {theme.ACCENT};
    padding: 0px {PAGE_COMPACT_RIGHT}px {PAGE_TEXT_LIFT}px {PAGE_BUTTON_PAD}px;
}}
QToolButton#qsPageCompact:hover {{
    background: {theme.ACCENT_TINT_HOVER};
}}
QToolButton#qsPageCompact:pressed {{
    background: {theme.SURFACE_PRESSED};
}}
"""


class CompactPageButton(QToolButton):

    def sizeHint(self) -> QSize:
        text = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(PAGE_BUTTON_PAD + text + PAGE_COMPACT_RIGHT, PAGE_BUTTON_H)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        p = QPainter(self)
        size = PAGE_CHEVRON
        x = self.width() - PAGE_CHEVRON_RIGHT - size
        y = (self.height() - size) / 2
        icons.render(p, QRectF(x, y, size, size), "chevron_down", theme.ACCENT)
        p.end()


class PageSwitcher(QFrame):

    pageRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsPageSwitcher")
        self.setStyleSheet(_page_switcher_qss())
        self.setFixedHeight(theme.SEGMENT_H)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
        lay.setSpacing(theme.SEGMENT_PAD)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        self._titles: dict[str, str] = {}
        self._current: str | None = None
        self._compact = False
        self.compact_button = CompactPageButton(self)
        self.compact_button.setObjectName("qsPageCompact")
        self.compact_button.setFixedHeight(PAGE_BUTTON_H)
        self.compact_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compact_button.clicked.connect(self.open_page_menu)
        self.compact_button.hide()
        lay.addWidget(self.compact_button)
        self.page_menu = None

    def add_page(self, page_id: str, title: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("qsPageButton")
        btn.setText(title)
        btn.setToolTip(title)
        btn.setCheckable(True)
        btn.setFixedHeight(PAGE_BUTTON_H)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, pid=page_id: self.pageRequested.emit(pid))
        self._group.addButton(btn)
        self.layout().addWidget(btn)
        self.buttons[page_id] = btn
        self._titles[page_id] = title
        btn.setVisible(not self._compact)
        self._sync_compact()
        return btn

    def set_current(self, page_id: str) -> None:
        btn = self.buttons.get(page_id)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        if btn is not None:
            self._current = page_id
            self._sync_compact()

    def current(self) -> str | None:
        return self._current

    def is_compact(self) -> bool:
        return self._compact

    def full_width(self) -> int:
        lay = self.layout()
        m = lay.contentsMargins()
        widths = [b.sizeHint().width() for b in self.buttons.values()]
        frame = 2 * theme.SEGMENT_BORDER
        return frame + m.left() + m.right() + sum(widths) + lay.spacing() * max(0, len(widths) - 1)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        for btn in self.buttons.values():
            btn.setVisible(not compact)
        self.compact_button.setVisible(compact)
        self._sync_compact()
        self.adjustSize()
        self.updateGeometry()

    def _sync_compact(self) -> None:
        title = self._titles.get(self._current or "", "")
        self.compact_button.setText(title)
        self.compact_button.setToolTip(title)

    def build_page_menu(self):
        from functools import partial

        from quartz_studio.widgets.menu_bar import StudioMenu

        menu = StudioMenu("Pages", self)
        for page_id, title in self._titles.items():
            act = menu.add_item(title, None, None, True, check=page_id == self._current)
            menu._handlers[act] = partial(self.pageRequested.emit, page_id)
        return menu

    def open_page_menu(self) -> None:
        if self.page_menu is not None:
            self.page_menu.deleteLater()
        menu = self.build_page_menu()
        self.page_menu = menu
        menu.popup(self.mapToGlobal(QPoint(0, self.height() + theme.SPACE_1)))


def window_icon() -> QIcon:
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    path = os.path.join(base, "assets", "quartzInstance.ico")
    return QIcon(path) if os.path.exists(path) else icons.icon("app_logo", 32)


class MainWindow(QMainWindow):

    pageChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(window_icon())
        self.setMinimumSize(theme.WINDOW_MIN_W, theme.WINDOW_MIN_H)
        self._user_sized = False
        self.regions: dict[str, QWidget] = {}
        self._pages: dict[str, QWidget] = {}
        self._page_titles: dict[str, str] = {}
        self._docks: dict[str, QWidget] = {}
        self._dock_areas: dict[str, str] = {}
        self.bottom_splitter: QSplitter | None = None
        self.left_dock_column: QSplitter | None = None
        self._fitting = False
        self.setAcceptDrops(True)
        self._build()
        project.attach(self)
        refresh = getattr(self.command_bar, "refresh_project", None)
        if refresh is not None:
            self.windowTitleChanged.connect(refresh)
            refresh()
        from quartz_studio import controls

        controls.install(self)

    def closeEvent(self, event: QCloseEvent) -> None:
        if project.confirm_discard():
            event.accept()
            super().closeEvent(event)
        else:
            event.ignore()

    @staticmethod
    def _dropped_paths(event) -> list[str]:
        return [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and self._dropped_paths(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._dropped_paths(event)
        if not paths:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        project.open_paths(paths)

    def _region(self, attr: str, parent: QWidget) -> QWidget:
        w = load_region(attr, parent)
        self.regions[attr] = w
        setattr(self, attr, w)
        return w

    def _build(self) -> None:
        central = QWidget(self)
        central.setObjectName("qsCentral")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget(central)
        top.setObjectName("qsTopBar")
        top.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        top.setFixedHeight(theme.TOP_BAR_H)
        top_h = QHBoxLayout(top)
        top_h.setContentsMargins(theme.WINDOW_MARGIN, 0, theme.WINDOW_MARGIN, 0)
        top_h.setSpacing(theme.SPACE_2)
        self.top_bar = top
        menu = self._region("menu_bar", top)
        menu.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        top_h.addWidget(menu, 0, Qt.AlignmentFlag.AlignVCenter)
        switcher = PageSwitcher(top)
        switcher.pageRequested.connect(self.show_page)
        switcher.hide()
        self.page_switcher = switcher
        top_h.addWidget(switcher, 0, Qt.AlignmentFlag.AlignVCenter)
        top_h.addWidget(self._region("command_bar", top), 1)
        root.addWidget(top)
        top.installEventFilter(self)
        menus_changed = getattr(menu, "menusChanged", None)
        if menus_changed is not None:
            menus_changed.connect(self.fit_top_row)

        stack = QStackedWidget(central)
        stack.setObjectName("qsPages")
        self.page_stack = stack
        frame = QWidget(stack)
        frame.setObjectName("qsBody")
        frame_h = QHBoxLayout(frame)
        frame_h.setContentsMargins(theme.WINDOW_MARGIN, 0, theme.WINDOW_MARGIN, 0)
        frame_h.setSpacing(0)

        body = StudioSplitter(Qt.Orientation.Horizontal, frame)
        body.setObjectName("qsBodySplitter")
        self.body_splitter = body

        left = QWidget(body)
        left.setObjectName("qsLeftBlock")
        left_h = QHBoxLayout(left)
        left_h.setContentsMargins(0, 0, 0, 0)
        left_h.setSpacing(theme.CARD_GAP)
        left_h.addWidget(self._region("tool_palette", left))
        viewport = self._region("viewport", left)
        left_h.addWidget(viewport, 1)
        self._left_layout = left_h
        dock = self._region("object_palette", viewport)
        self._dock_hosts: list[QObject] = [viewport]
        canvas = getattr(viewport, "canvas", None)
        if isinstance(canvas, QWidget):
            self._dock_hosts.append(canvas)
            hud_signal = getattr(canvas, "hudChanged", None)
            if hud_signal is not None:
                hud_signal.connect(self.place_object_dock)
        for host in self._dock_hosts:
            host.installEventFilter(self)
        dock.raise_()

        right = StudioSplitter(Qt.Orientation.Vertical, body)
        right.setObjectName("qsManagerSplitter")
        right.addWidget(self._region("object_manager", right))
        right.addWidget(self._region("attribute_manager", right))
        right.addWidget(self._region("coordinates", right))
        right.setStretchFactor(0, 1)
        right.setStretchFactor(1, 1)
        right.setStretchFactor(2, 0)
        self.manager_splitter = right
        right.widgetsChanged.connect(self._lock_coordinates_handle)
        self._lock_coordinates_handle()
        self._right_min_w = max(self.object_manager.minimumSizeHint().width(),
                                self.attribute_manager.minimumSizeHint().width(),
                                self.coordinates.minimumSizeHint().width(), RIGHT_COLUMN_MIN)
        right.setMinimumWidth(self._right_min_w)

        body.addWidget(left)
        body.addWidget(right)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 0)
        body.splitterMoved.connect(self._on_user_split)
        right.splitterMoved.connect(self._on_user_split)
        frame_h.addWidget(body, 1)
        stack.addWidget(frame)
        self._pages[MODEL_PAGE] = frame
        self._page_titles[MODEL_PAGE] = MODEL_PAGE_TITLE
        self.model_page = frame
        switcher.add_page(MODEL_PAGE, MODEL_PAGE_TITLE)
        switcher.set_current(MODEL_PAGE)
        root.addWidget(stack, 1)

        for name in CARD_REGIONS:
            make_card(self.regions[name])

        status = self._region("status_bar", self)
        if isinstance(status, QStatusBar):
            self.setStatusBar(status)
        else:
            root.addWidget(status)
        self.setCentralWidget(central)

    def add_page(self, page_id: str, title: str, widget: QWidget) -> QWidget:
        if not isinstance(page_id, str) or not page_id:
            raise ValueError("page_id must be a non-empty string")
        if page_id in self._pages:
            raise ValueError(f"page {page_id!r} already exists")
        self.page_stack.addWidget(widget)
        self._pages[page_id] = widget
        self._page_titles[page_id] = title
        self.page_switcher.add_page(page_id, title)
        self.page_switcher.setVisible(len(self._pages) > 1)
        self.fit_top_row()
        return widget

    def show_page(self, page_id: str) -> None:
        widget = self._pages.get(page_id)
        if widget is None:
            raise KeyError(f"no page {page_id!r}")
        self.page_switcher.set_current(page_id)
        self.fit_top_row()
        if self.page_stack.currentWidget() is widget:
            return
        self.page_stack.setCurrentWidget(widget)
        self.pageChanged.emit(page_id)

    def current_page(self) -> str:
        current = self.page_stack.currentWidget()
        return next((pid for pid, w in self._pages.items() if w is current), MODEL_PAGE)

    def page_ids(self) -> list[str]:
        return list(self._pages)

    def page(self, page_id: str) -> QWidget | None:
        return self._pages.get(page_id)

    def add_dock(self, dock_id: str, title: str, widget: QWidget, area: str = "bottom") -> QWidget:
        if not isinstance(dock_id, str) or not dock_id:
            raise ValueError("dock_id must be a non-empty string")
        if dock_id in self._docks:
            raise ValueError(f"dock {dock_id!r} already exists")
        if area not in DOCK_AREAS:
            raise ValueError(f"area must be one of {DOCK_AREAS}, not {area!r}")
        widget.setObjectName(widget.objectName() or f"qs_dock_{dock_id}")
        widget.setWindowTitle(title)
        if area == "bottom":
            host = self._bottom_host()
            host.addWidget(widget)
            host.setStretchFactor(host.indexOf(widget), 0)
        elif area == "left":
            self._left_host().addWidget(widget)
        else:
            splitter = self.manager_splitter
            splitter.addWidget(widget)
            splitter.setStretchFactor(splitter.indexOf(widget), 0)
        make_card(widget)
        self._docks[dock_id] = widget
        self._dock_areas[dock_id] = area
        self._sync_left_column()
        self._relayout()
        return widget

    def dock(self, dock_id: str) -> QWidget | None:
        return self._docks.get(dock_id)

    def dock_ids(self) -> list[str]:
        return list(self._docks)

    def set_dock_visible(self, dock_id: str, visible: bool) -> None:
        widget = self._docks.get(dock_id)
        if widget is None:
            raise KeyError(f"no dock {dock_id!r}")
        widget.setVisible(bool(visible))
        self._sync_left_column()
        self._relayout()

    def is_dock_visible(self, dock_id: str) -> bool:
        widget = self._docks.get(dock_id)
        return widget is not None and not widget.isHidden()

    def _bottom_host(self) -> QSplitter:
        if self.bottom_splitter is None:
            viewport = self.viewport
            splitter = StudioSplitter(Qt.Orientation.Vertical, viewport.parentWidget())
            splitter.setObjectName("qsBottomSplitter")
            self._left_layout.replaceWidget(viewport, splitter)
            splitter.addWidget(viewport)
            splitter.setStretchFactor(0, 1)
            self._left_layout.setStretchFactor(splitter, 1)
            self.bottom_splitter = splitter
        return self.bottom_splitter

    def _left_host(self) -> QSplitter:
        if self.left_dock_column is None:
            column = StudioSplitter(Qt.Orientation.Vertical, self.body_splitter)
            column.setObjectName("qsLeftDockSplitter")
            self.body_splitter.insertWidget(0, column)
            self.body_splitter.setStretchFactor(0, 0)
            self.body_splitter.setStretchFactor(1, 1)
            self.body_splitter.setStretchFactor(2, 0)
            self.left_dock_column = column
        return self.left_dock_column

    def _lock_coordinates_handle(self) -> None:
        splitter = self.manager_splitter
        index = splitter.indexOf(self.coordinates)
        for i in range(splitter.count()):
            splitter.handle(i).setEnabled(i != index)

    def _sync_left_column(self) -> None:
        column = self.left_dock_column
        if column is None:
            return
        shown = any(not column.widget(i).isHidden() for i in range(column.count()))
        column.setVisible(shown)

    def _relayout(self) -> None:
        if self.isVisible() and not self._user_sized:
            self.apply_default_sizes()

    def fit_top_row(self) -> None:
        bar = self.regions.get("menu_bar")
        if self._fitting or not hasattr(bar, "set_width_limit"):
            return
        self._fitting = True
        try:
            lay = self.top_bar.layout()
            space = lay.spacing()
            pill = getattr(self.command_bar, "mode_switcher", None)
            pill_w = pill.sizeHint().width() if isinstance(pill, QWidget) else 0
            pill_left = round(self.top_bar.width() / 2 - pill_w / 2)
            start = lay.contentsMargins().left()
            room = pill_left - TOP_ROW_GAP - space - start
            switcher = self.page_switcher
            if len(self._pages) > 1:
                bar.set_width_limit(None)
                if bar.natural_width() + space + switcher.full_width() <= room:
                    switcher.set_compact(False)
                    return
                switcher.set_compact(True)
                room -= space + switcher.sizeHint().width()
            else:
                switcher.set_compact(False)
            bar.set_width_limit(room)
        finally:
            self._fitting = False
            self.top_bar.layout().invalidate()
            center = getattr(self.command_bar, "center_modes", None)
            if center is not None:
                center()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is getattr(self, "top_bar", None) and event.type() == QEvent.Type.Resize:
            self.fit_top_row()
        if obj in self._dock_hosts and event.type() in (QEvent.Type.Resize, QEvent.Type.Show,
                                                         QEvent.Type.Move):
            self.place_object_dock()
        return super().eventFilter(obj, event)

    def dock_area(self) -> QRect:
        host = self.object_palette.parentWidget()
        canvas = getattr(host, "canvas", None)
        if isinstance(canvas, QWidget) and canvas.parentWidget() is host and canvas.isVisibleTo(host):
            return canvas.geometry()
        return host.rect()

    def place_object_dock(self) -> None:
        dock = self.object_palette
        if dock.parentWidget() is None:
            return
        area = self.dock_area()
        natural = dock.sizeHint()
        width = max(1, min(natural.width(), area.width() - 2 * theme.SPACE_3))
        height = natural.height()
        x = area.left() + (area.width() - width) // 2
        y = area.top() + area.height() - theme.DOCK_BOTTOM - height
        canvas = getattr(self.object_palette.parentWidget(), "canvas", None)
        hud_rect = getattr(canvas, "hud_rect", None)
        if hud_rect is not None and canvas.geometry() == area:
            hud = hud_rect().translated(area.left(), area.top())
            if x < hud.right() + theme.SPACE_2:
                y = min(y, int(hud.top()) - theme.SPACE_2 - height)
        dock.setGeometry(x, max(area.top(), y), width, height)
        dock.raise_()

    def _size_bottom_docks(self) -> None:
        bottom = self.bottom_splitter
        if bottom is None:
            return
        total = max(bottom.height(), 1)
        heights = []
        for i in range(bottom.count()):
            panel = bottom.widget(i)
            if panel is self.viewport or panel.isHidden():
                heights.append(0)
            else:
                want = max(panel.sizeHint().height(), panel.minimumHeight(), 1)
                heights.append(min(want, max(1, total // 3)))
        used = sum(heights) + theme.CARD_GAP * sum(1 for h in heights if h)
        heights[bottom.indexOf(self.viewport)] = max(1, total - used)
        bottom.setSizes(heights)

    def _on_user_split(self, *_args) -> None:
        self._user_sized = True

    def apply_default_sizes(self) -> None:
        body_w = max(1, self.width() - 2 * theme.WINDOW_MARGIN)
        column = self.left_dock_column
        dock_w = 0
        if column is not None and not column.isHidden():
            dock_w = max(LEFT_DOCK_W, column.minimumSizeHint().width())
            body_w = max(1, body_w - dock_w - theme.CARD_GAP)
        right_w = round(self.width() * RIGHT_COLUMN_RATIO)
        managers = (self.object_manager, self.attribute_manager, self.coordinates)
        wanted = max(m.sizeHint().width() for m in managers)
        left_min = self.body_splitter.widget(self.body_splitter.count() - 2).minimumSizeHint().width()
        room = body_w - left_min - theme.CARD_GAP
        right_w = max(right_w, min(wanted, room), self._right_min_w)
        sizes = [max(1, body_w - right_w - theme.CARD_GAP), right_w]
        if column is not None:
            sizes.insert(0, dock_w)
        self.body_splitter.setSizes(sizes)
        self._size_bottom_docks()
        splitter = self.manager_splitter
        for i in range(splitter.count()):
            make_card(splitter.widget(i))
        total_h = max(splitter.height(), 1)
        coord_h = theme.COORDINATES_H
        fixed = {self.coordinates: coord_h}
        taken = coord_h + theme.CARD_GAP
        core = (self.object_manager, self.attribute_manager, self.coordinates)
        for i in range(splitter.count()):
            panel = splitter.widget(i)
            if panel in core:
                continue
            fixed[panel] = min(max(panel.sizeHint().height(), 1), max(1, panel.minimumHeight(), total_h // 4))
            if not panel.isHidden():
                taken += fixed[panel] + theme.CARD_GAP
        taken += theme.CARD_GAP
        rest = max(2, total_h - taken)
        attr_min = self.attribute_manager.minimumSizeHint().height()
        object_min = self.object_manager.minimumSizeHint().height()
        attr_want = max(round(rest * ATTRIBUTE_FRACTION), attr_min + ATTRIBUTE_FIRST_ROW, math.ceil(total_h * ATTRIBUTE_SHARE))
        fixed[self.attribute_manager] = max(1, min(attr_want, max(rest - object_min, rest // 2), rest - 1))
        fixed[self.object_manager] = max(1, rest - fixed[self.attribute_manager])
        splitter.setSizes([fixed[splitter.widget(i)] for i in range(splitter.count())])
        self.place_object_dock()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self._user_sized:
            self.apply_default_sizes()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._user_sized:
            self.apply_default_sizes()
        self.place_object_dock()
