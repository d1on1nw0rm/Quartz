from __future__ import annotations

import contextlib
import os
import re
from functools import partial

from PySide6.QtCore import QEvent, QKeyCombination, QLocale, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QKeySequence, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCompleter,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quartz_studio import controls, icons, theme
from quartz_studio.widgets.common import (
    CollapsibleGroup,
    PanelTabBar,
    ToggleSwitch,
    header_font,
    make_card,
    prepare_combo,
    restyle,
)

FILE_FILTER = "Quartz Controls (*.json)"
DIALOG_W = 960
DIALOG_H = 640
INSET = 16
HEADER_H = 48
HEADER_PAD = 16
HEADER_GAP = 8
BUTTON_H = 28
BUTTON_PAD = 12
COMBO_W = 256
NOTE_H = 24
TAB_H = 28
FOOTER_H = 48
PAGE_GAP = 8
SEARCH_W = 320
SEARCH_ROW_H = 40
CATEGORY_W = 192
ROW_H = 28
KEYS_W = 320
SCOPE_W = 96
RESET_W = 32
CHIP_H = 24
CHIP_RADIUS = 12
CHIP_PAD = 8
CHIP_GAP = 4
CHIP_CLOSE = 12
SMALL_BUTTON = 24
SMALL_ICON = 16
BANNER_H = 40
BANNER_PAD = 12
BANNER_BUTTON_H = 24
GESTURE_ROW_H = 32
OP_COMBO_W = 192
PAD_W = 256
PAD_H = 96
PAD_RADIUS = 10
FORM_ROW_H = 28
LABEL_W = 192
FIELD_W = 128
TOGGLE_W = 32
TOGGLE_H = 16
ROW_PAD = 8
TEXT_PAD = 6

NOTE_TEXT = "Built-in profiles cannot be changed. Duplicate one to edit it."
RECORDING_TEXT = "Press keys..."
PAD_TEXT = "Press a mouse button here, holding modifiers or a key"
GESTURE_USED = "This gesture is already used."
SEARCH_PLACEHOLDER = "Search actions or keys"
TABS = ("Keyboard", "Mouse", "Cursor")
CATEGORIES = ("All", "File", "Edit", "Modes", "Tools", "Mesh", "Select", "Create", "View", "Cameras",
              "Objects")
SCOPE_TEXT = {"global": "Window", "viewport": "Viewport", "objects": "Objects"}
OPS = (("Orbit", "orbit"), ("Pan", "pan"), ("Dolly", "dolly"), ("Select", "select"),
       ("Add to Selection", "add"), ("Remove from Selection", "remove"), ("Context Menu", "context"))
DRAG_OPS = ("orbit", "pan", "dolly")
BUTTONS = {Qt.MouseButton.LeftButton: "left", Qt.MouseButton.MiddleButton: "middle",
           Qt.MouseButton.RightButton: "right"}
MOD_ORDER = (("shift", "Shift"), ("ctrl", "Ctrl"), ("alt", "Alt"))
MODIFIER_KEYS = {Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                 Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock, Qt.Key.Key_ScrollLock,
                 Qt.Key.Key_Super_L, Qt.Key.Key_Super_R, Qt.Key.Key_unknown}
HEAVY = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier
COMBO_MODS = HEAVY | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.KeypadModifier

CURSOR_GROUPS = (
    ("Orbit", (
        ("orbit_pivot", "Pivot", "combo", (("Cursor", "Cursor"), ("Center", "Center"), ("Object", "Object"),
                                           ("Camera", "Camera"))),
        ("orbit_style", "Style", "combo", (("Turntable", "turntable"), ("Free", "free"))),
        ("orbit_speed", "Speed", "float", (0.05, 2.0, 0.05, 2, "°/px")),
        ("invert_orbit_x", "Invert Horizontal", "bool", None),
        ("invert_orbit_y", "Invert Vertical", "bool", None),
    )),
    ("Pan and Dolly", (
        ("invert_pan", "Invert Pan", "bool", None),
        ("dolly_speed", "Dolly Speed", "float", (0.001, 0.05, 0.001, 3, "")),
    )),
    ("Wheel", (
        ("zoom_to_cursor", "Zoom Toward Cursor", "bool", None),
        ("wheel_step", "Step", "float", (0.5, 0.98, 0.01, 2, "")),
        ("wheel_invert", "Invert Wheel", "bool", None),
    )),
    ("Clicks", (
        ("drag_threshold", "Drag Threshold", "int", (1, 16, 1, " px")),
        ("click_tolerance", "Click Tolerance", "int", (1, 16, 1, " px")),
        ("hold_ms", "Hold Delay", "int", (150, 1000, 10, " ms")),
        ("chord_ms", "Chord Time", "int", (500, 3000, 100, " ms")),
    )),
)
MODIFIER_ROWS = (("snap", "Snap"), ("extrude", "Extrude While Moving"), ("create_child", "Create as Child"),
                 ("create_adopt", "Create and Adopt"))
MODIFIER_CHOICES = (("Shift", "shift"), ("Ctrl", "ctrl"), ("Alt", "alt"))
MODAL_ROWS = (("cancel", "Cancel"), ("confirm", "Confirm"))


def _qss() -> str:
    return f"""
QDialog#qsControlsDialog {{ background: {theme.SURFACE_BACKDROP}; }}
QPushButton#qsCtlButton {{ padding: 0px {BUTTON_PAD}px; }}
QLabel#qsCtlHeader {{ color: {theme.TEXT_SECONDARY}; }}
QLabel#qsCtlNote {{ color: {theme.TEXT_SECONDARY}; padding: 0px {HEADER_PAD}px; }}
QFrame#qsBindingChip {{
    background: {theme.SURFACE_RAISED};
    border: 1px solid {theme.HAIRLINE};
    border-radius: {CHIP_RADIUS}px;
}}
QFrame#qsBindingChip[qsState="recording"] {{
    background: {theme.ACCENT_TINT};
    border: 1px solid {theme.ACCENT};
}}
QLabel#qsBindingText {{ color: {theme.TEXT_PRIMARY}; }}
QLabel#qsBindingText[qsState="conflict"] {{ color: {theme.STATUS_ERROR}; }}
QLabel#qsBindingText[qsState="recording"] {{ color: {theme.ACCENT}; }}
QLabel#qsBindingText:disabled {{ color: {theme.TEXT_MUTED}; }}
QFrame#qsCtlBanner {{
    background: {theme.SURFACE_MENU};
    border: 1px solid {theme.STATUS_ERROR};
    border-radius: {theme.MENU_RADIUS}px;
}}
QLabel#qsCtlBannerText {{ color: {theme.TEXT_PRIMARY}; }}
QLabel#qsCtlAction {{
    color: {theme.TEXT_PRIMARY};
    border-left: {theme.ACCENT_BAR_W}px solid transparent;
    padding-left: {TEXT_PAD}px;
}}
QLabel#qsCtlAction[qsOverridden="true"] {{ border-left: {theme.ACCENT_BAR_W}px solid {theme.ACCENT}; }}
QFrame#qsCtlRow {{ border-left: {theme.ACCENT_BAR_W}px solid transparent; }}
QFrame#qsCtlRow[qsOverridden="true"] {{ border-left: {theme.ACCENT_BAR_W}px solid {theme.ACCENT}; }}
QLabel#qsCtlGesture {{ color: {theme.TEXT_PRIMARY}; }}
QFrame#qsCtlPad {{
    background: {theme.SURFACE_FIELD};
    border: 1px solid {theme.HAIRLINE};
    border-radius: {PAD_RADIUS}px;
}}
QLabel#qsCtlPadText {{ color: {theme.TEXT_SECONDARY}; }}
QListWidget#qsCtlCategories::item {{ min-height: {ROW_H}px; max-height: {ROW_H}px; padding: 0px {ROW_PAD}px; }}
QTableWidget#qsCtlTable {{ gridline-color: transparent; }}
QTableWidget#qsCtlTable::item {{ padding: 0px {ROW_PAD}px; }}
"""


def _interactive() -> bool:
    return QGuiApplication.platformName() not in ("offscreen", "minimal")


def _file_stem(name: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .")
    return stem or "Controls"


def choose_import_file() -> str | None:
    from quartz_studio import project

    paths = project.choose_open_files("Import Controls", os.path.expanduser("~"), [FILE_FILTER])
    return paths[0] if paths else None


def choose_export_file(name: str) -> str | None:
    from quartz_studio import project

    path = os.path.join(os.path.expanduser("~"), _file_stem(name) + ".json")
    return project.choose_save_file("Export Controls", path, [FILE_FILTER])


def ask_profile_name(parent: QWidget | None, current: str) -> str | None:
    if not _interactive():
        return None
    text, ok = QInputDialog.getText(parent, "Rename Profile", "Name", QLineEdit.EchoMode.Normal, current)
    return text if ok else None


def confirm(parent: QWidget | None, text: str) -> bool:
    if not _interactive():
        return True
    answer = QMessageBox.question(parent, "Controls", text,
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
    return answer == QMessageBox.StandardButton.Yes


def show_error(text: str) -> None:
    from quartz_studio import project

    project.show_message("error", text)


def norm_binding(text: str) -> str:
    if len(text) > 2 and "~" in text[1:-1]:
        idx = text.index("~", 1)
        return text[:idx].upper() + "~" + text[idx + 1:].upper()
    return QKeySequence(text).toString(QKeySequence.SequenceFormat.PortableText)


def chord_prefix(text: str) -> str | None:
    if len(text) > 2 and "~" in text[1:-1]:
        return norm_binding(text).split("~", 1)[0]
    return None


def bindings_clash(a: str, b: str) -> bool:
    na, nb = norm_binding(a), norm_binding(b)
    return na == nb or chord_prefix(a) == nb or chord_prefix(b) == na


def combination_text(key: int, mods) -> str:
    mods = Qt.KeyboardModifier(mods) & COMBO_MODS
    seq = QKeySequence(QKeyCombination(mods, Qt.Key(key)))
    return seq.toString(QKeySequence.SequenceFormat.PortableText)


def key_name(key: int) -> str:
    return QKeySequence(QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key(key))).toString(
        QKeySequence.SequenceFormat.PortableText)


def gesture_text(g: dict) -> str:
    parts = []
    if g.get("key"):
        parts.append(f"{g['key']} held")
    mods = set(g.get("mods") or ())
    parts.extend(name for mod, name in MOD_ORDER if mod in mods)
    button = str(g.get("button", "left")).capitalize()
    if g.get("double"):
        parts.append(f"{button} double-click")
    elif g.get("op") in DRAG_OPS:
        parts.append(f"{button} drag")
    else:
        parts.append(f"{button} click")
    return " + ".join(parts)


def gesture_identity(g: dict) -> tuple:
    key = g.get("key")
    return (g.get("button"), frozenset(g.get("mods") or ()), str(key).upper() if key else None,
            bool(g.get("double")))


def overridden(res, section: str, key: str | None = None) -> bool:
    marks = res.overridden
    if key is None:
        return section in marks
    return f"{section}.{key}" in marks or (section, key) in marks


def _tool_button(icon_name: str, tooltip: str, parent: QWidget, size: int = SMALL_BUTTON,
                 icon_px: int = SMALL_ICON, color: str = theme.TEXT_SECONDARY) -> QToolButton:
    btn = QToolButton(parent)
    btn.setObjectName("qsCtlIconButton")
    btn.setAutoRaise(True)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setFixedSize(size, size)
    btn.setIconSize(QSize(icon_px, icon_px))
    btn.setIcon(icons.icon(icon_name, icon_px, color))
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    return btn


class FixedButton(QPushButton):

    def __init__(self, text: str, parent: QWidget, height: int) -> None:
        super().__init__(text, parent)
        self._height = height
        self.setObjectName("qsCtlButton")
        self.setAutoDefault(False)
        self.setDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(height)

    def event(self, e: QEvent) -> bool:
        result = super().event(e)
        if e.type() in (QEvent.Type.Polish, QEvent.Type.StyleChange, QEvent.Type.EnabledChange,
                        QEvent.Type.Show):
            if self.minimumHeight() != self._height or self.maximumHeight() != self._height:
                self.setFixedHeight(self._height)
        return result


def _push(text: str, parent: QWidget, height: int = BUTTON_H) -> QPushButton:
    return FixedButton(text, parent, height)


def _hbox(widget: QWidget, margins=(0, 0, 0, 0), spacing: int = 0) -> QHBoxLayout:
    lay = QHBoxLayout(widget)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return lay


def _vbox(widget: QWidget, margins=(0, 0, 0, 0), spacing: int = 0) -> QVBoxLayout:
    lay = QVBoxLayout(widget)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return lay


def _mark_editing(widget: QWidget, editable: bool) -> QWidget:
    widget.setProperty("qsEditing", True)
    widget.setEnabled(editable)
    return widget


class BindingChip(QFrame):

    clicked = Signal()
    removed = Signal()

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsBindingChip")
        self.setFixedHeight(CHIP_H)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.binding = text
        lay = _hbox(self, (CHIP_PAD, 0, CHIP_PAD, 0), CHIP_GAP)
        self.label = QLabel(text, self)
        self.label.setObjectName("qsBindingText")
        lay.addWidget(self.label)
        self.close_button = _tool_button("close", "Remove", self, CHIP_CLOSE, CHIP_CLOSE)
        self.close_button.clicked.connect(self.removed.emit)
        lay.addWidget(self.close_button)
        self.state = "normal"
        self.setProperty("qsState", "normal")
        self.label.setProperty("qsState", "normal")

    def set_state(self, state: str, text: str | None = None) -> None:
        if state != self.state:
            self.state = state
            self.setProperty("qsState", state)
            self.label.setProperty("qsState", state)
            restyle(self)
            restyle(self.label)
        self.label.setText(self.binding if text is None else text)
        self.close_button.setVisible(state != "recording")

    def text(self) -> str:
        return self.label.text()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            e.accept()
            self.clicked.emit()
            return
        super().mouseReleaseEvent(e)


class Banner(QFrame):

    def __init__(self, parent: QWidget | None = None, buttons: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("qsCtlBanner")
        self.setFixedHeight(BANNER_H)
        lay = _hbox(self, (BANNER_PAD, 0, BANNER_PAD, 0), HEADER_GAP)
        self.label = QLabel("", self)
        self.label.setObjectName("qsCtlBannerText")
        lay.addWidget(self.label, 1)
        self.replace_button = self.keep_button = self.cancel_button = None
        if buttons:
            self.replace_button = _push("Replace", self, BANNER_BUTTON_H)
            self.keep_button = _push("Keep Both", self, BANNER_BUTTON_H)
            self.cancel_button = _push("Cancel", self, BANNER_BUTTON_H)
            for b in (self.replace_button, self.keep_button, self.cancel_button):
                lay.addWidget(b)

    def text(self) -> str:
        return self.label.text()


class KeyRecorder(QObject):

    def __init__(self, dialog: QDialog) -> None:
        super().__init__(dialog)
        self.dialog = dialog
        self.chip: BindingChip | None = None
        self.single = False
        self.pending: tuple[str, str] | None = None
        self._commit = None
        self._cancel = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)

    def active(self) -> bool:
        return self.chip is not None

    def start(self, chip: BindingChip, commit, cancel, single: bool = False) -> None:
        if self.active():
            self.cancel()
        self.chip = chip
        self.single = single
        self.pending = None
        self._commit = commit
        self._cancel = cancel
        chip.set_state("recording", RECORDING_TEXT)
        self.dialog.grabKeyboard()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _finish(self) -> None:
        self.timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if QWidget.keyboardGrabber() is self.dialog:
            self.dialog.releaseKeyboard()
        self.chip = None
        self.pending = None

    def cancel(self) -> None:
        if not self.active():
            return
        callback = self._cancel
        self._finish()
        if callback is not None:
            callback()

    def commit(self, text: str) -> None:
        callback = self._commit
        self._finish()
        if callback is not None:
            callback(text)

    def _timeout(self) -> None:
        if self.active() and self.pending is not None:
            self.commit(self.pending[1])

    def handle(self, e: QKeyEvent) -> None:
        key = e.key()
        if key in MODIFIER_KEYS or e.isAutoRepeat():
            return
        mods = e.modifiers()
        heavy = bool(mods & HEAVY)
        if key == Qt.Key.Key_Escape and not (mods & (HEAVY | Qt.KeyboardModifier.ShiftModifier)):
            self.cancel()
            return
        if self.single:
            if heavy or mods & Qt.KeyboardModifier.ShiftModifier:
                return
            self.commit(key_name(key))
            return
        text = e.text()
        printable = (bool(text) and text.isprintable() and not text.isspace()
                     and not mods & Qt.KeyboardModifier.KeypadModifier)
        if self.pending is not None:
            if heavy:
                self.commit(combination_text(key, mods))
                return
            second = text.upper() if printable else key_name(key)
            self.commit(f"{self.pending[0]}~{second}")
            return
        if heavy or not printable:
            self.commit(combination_text(key, mods))
            return
        first = text.upper()
        self.pending = (first, combination_text(key, mods))
        self.chip.set_state("recording", f"{first} then...")
        self.timer.start(int(controls.cursor("chord_ms")))

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if (ev.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick)
                and isinstance(obj, QWidget) and self.chip is not None):
            chip = self.chip
            if obj is chip or chip.isAncestorOf(obj):
                return False
            self.cancel()
        return False


class ChipCell(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_ = _hbox(self, (0, 0, 0, 0), CHIP_GAP)
        self.chips: list[BindingChip] = []
        self.add_button = _tool_button("plus", "Add Binding", self)
        self.layout_.addWidget(self.add_button)
        self.layout_.addStretch(1)

    def add_chip(self, text: str) -> BindingChip:
        chip = BindingChip(text, self)
        self.layout_.insertWidget(len(self.chips), chip)
        self.chips.append(chip)
        return chip


class KeyboardPage(QWidget):

    def __init__(self, dialog: "ControlsDialog") -> None:
        super().__init__(dialog)
        self.dialog = dialog
        self._ids: list[str] = []
        self._row: dict[str, int] = {}
        self._actions: dict = {}
        self._search_text: dict[str, str] = {}
        self._sig: dict[str, tuple] = {}
        self._conflict_cache: tuple | None = None
        self.pending: dict | None = None
        lay = _vbox(self, (INSET, 0, INSET, INSET), PAGE_GAP)
        self.top = QStackedWidget(self)
        self.top.setFixedHeight(SEARCH_ROW_H)
        self.top.layout().setContentsMargins(0, 0, 0, 0)
        self.top.layout().setSpacing(0)
        search_row = QWidget(self.top)
        srl = _hbox(search_row)
        self.search = QLineEdit(search_row)
        self.search.setObjectName("qsCtlSearch")
        self.search.setPlaceholderText(SEARCH_PLACEHOLDER)
        self.search.setFixedSize(SEARCH_W, BUTTON_H)
        self.search.setClearButtonEnabled(False)
        self.search.textChanged.connect(self.apply_filter)
        srl.addWidget(self.search)
        srl.addStretch(1)
        self.top.addWidget(search_row)
        self.banner = Banner(self.top)
        self.banner.replace_button.clicked.connect(self.replace_conflict)
        self.banner.keep_button.clicked.connect(self.keep_conflict)
        self.banner.cancel_button.clicked.connect(self.cancel_conflict)
        self.top.addWidget(self.banner)
        lay.addWidget(self.top)
        body = QWidget(self)
        bl = _hbox(body, (0, 0, 0, 0), PAGE_GAP)
        self.categories = QListWidget(body)
        self.categories.setObjectName("qsCtlCategories")
        self.categories.setFixedWidth(CATEGORY_W)
        self.categories.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.categories.setUniformItemSizes(True)
        self.categories.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.currentRowChanged.connect(lambda _row: self.apply_filter())
        bl.addWidget(self.categories)
        self.table = QTableWidget(0, 4, body)
        self.table.setObjectName("qsCtlTable")
        self.table.setHorizontalHeaderLabels(["Action", "Keys", "Scope", ""])
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        vh = self.table.verticalHeader()
        vh.setVisible(False)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vh.setMinimumSectionSize(ROW_H)
        vh.setDefaultSectionSize(ROW_H)
        hh = self.table.horizontalHeader()
        hh.setFixedHeight(ROW_H)
        hh.setHighlightSections(False)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, KEYS_W), (2, SCOPE_W), (3, RESET_W)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, width)
        bl.addWidget(self.table, 1)
        lay.addWidget(body, 1)

    def rebuild(self) -> None:
        self._actions = dict(controls.actions())
        self._ids = list(self._actions)
        self._row = {aid: r for r, aid in enumerate(self._ids)}
        self._sig = {}
        self.table.clearContents()
        self.table.setRowCount(len(self._ids))
        for r, aid in enumerate(self._ids):
            action = self._actions[aid]
            item = QTableWidgetItem(SCOPE_TEXT.get(action.scope, action.scope.capitalize()))
            item.setForeground(QColor(theme.TEXT_SECONDARY))
            self.table.setItem(r, 2, item)
        self._fill_categories()
        self.refresh_rows()

    def refresh(self) -> None:
        if list(controls.actions()) != self._ids:
            self.rebuild()
        else:
            self.refresh_rows()

    def _fill_categories(self) -> None:
        current = self.categories.currentItem().text() if self.categories.currentItem() else "All"
        names = list(CATEGORIES)
        for action in self._actions.values():
            if action.category not in names:
                names.append(action.category)
        self.categories.blockSignals(True)
        self.categories.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setSizeHint(QSize(0, ROW_H))
            self.categories.addItem(item)
        row = names.index(current) if current in names else 0
        self.categories.setCurrentRow(row)
        self.categories.blockSignals(False)

    def label_of(self, action_id: str) -> str:
        action = self._actions.get(action_id) or controls.actions().get(action_id)
        return action.label if action is not None else action_id

    def conflicts(self, res=None) -> list:
        res = controls.active() if res is None else res
        cached = self._conflict_cache
        if cached is None or cached[0] is not res:
            cached = (res, list(controls.conflicts(res.id)))
            self._conflict_cache = cached
        return cached[1]

    def _marks(self, res) -> dict[tuple[str, int], str]:
        marks: dict[tuple[str, int], str] = {}
        for binding, a, b in self.conflicts(res):
            for aid, other in ((a, b), (b, a)):
                for i, (text, _scope) in enumerate(res.keys.get(aid, ())):
                    if (aid, i) not in marks and bindings_clash(text, binding):
                        marks[(aid, i)] = self.label_of(other)
        return marks

    def _set_row_enabled(self, aid: str, editable: bool, over: bool) -> None:
        cell = self.cell(aid)
        for chip in cell.chips:
            chip.setEnabled(editable)
        cell.add_button.setEnabled(editable)
        reset = self.reset_button(aid)
        reset.setEnabled(editable)
        reset.setVisible(over and editable)

    def editing_controls(self) -> list[QWidget]:
        out: list[QWidget] = []
        for aid in self._ids:
            cell = self.cell(aid)
            out.extend(cell.chips)
            out.append(cell.add_button)
            out.append(self.reset_button(aid))
        return out

    def refresh_rows(self, ids=None, force: bool = False) -> None:
        res = controls.active()
        editable = not res.builtin
        marks = self._marks(res)
        targets = self._ids if ids is None else [i for i in ids if i in self._row]
        for aid in targets:
            r = self._row[aid]
            action = self._actions[aid]
            over = aid in res.overridden
            pairs = res.keys.get(aid, ())
            sig = (over, tuple(pairs), tuple(marks.get((aid, i)) for i in range(len(pairs))))
            old = self._sig.get(aid)
            if old is not None and old[0] == sig and not force:
                if old[1] != editable:
                    self._set_row_enabled(aid, editable, over)
                    self._sig[aid] = (sig, editable)
                continue
            self._sig[aid] = (sig, editable)
            label = QLabel(action.label)
            label.setObjectName("qsCtlAction")
            label.setProperty("qsOverridden", "true" if over else "false")
            self.table.setCellWidget(r, 0, label)
            cell = ChipCell()
            for i, (text, _scope) in enumerate(pairs):
                chip = cell.add_chip(text)
                other = marks.get((aid, i))
                if other:
                    chip.set_state("conflict")
                    chip.setToolTip(f"Also used by {other}")
                _mark_editing(chip, editable)
                chip.clicked.connect(partial(self.record, aid, i))
                chip.removed.connect(partial(self.remove_binding, aid, i))
            _mark_editing(cell.add_button, editable)
            cell.add_button.clicked.connect(partial(self.record, aid, None))
            self.table.setCellWidget(r, 1, cell)
            holder = QWidget()
            hl = _hbox(holder)
            reset = _tool_button("undo", "Reset to Profile Base", holder)
            reset.setVisible(over and editable)
            _mark_editing(reset, editable)
            reset.clicked.connect(partial(self.reset_binding, aid))
            hl.addWidget(reset, 0, Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(r, 3, holder)
            words = [action.label, aid] + [t for t, _s in pairs]
            self._search_text[aid] = " ".join(words).casefold()
        self.apply_filter()

    def apply_filter(self, *_args) -> None:
        item = self.categories.currentItem()
        category = item.text() if item is not None else "All"
        query = self.search.text().strip().casefold()
        for aid, r in self._row.items():
            action = self._actions[aid]
            show = category == "All" or action.category == category
            if show and query:
                show = query in self._search_text.get(aid, "")
            self.table.setRowHidden(r, not show)

    def visible_ids(self) -> list[str]:
        return [aid for aid, r in self._row.items() if not self.table.isRowHidden(r)]

    def cell(self, action_id: str) -> ChipCell:
        return self.table.cellWidget(self._row[action_id], 1)

    def chips(self, action_id: str) -> list[BindingChip]:
        return list(self.cell(action_id).chips)

    def add_button(self, action_id: str) -> QToolButton:
        return self.cell(action_id).add_button

    def reset_button(self, action_id: str) -> QToolButton:
        return self.table.cellWidget(self._row[action_id], 3).findChild(QToolButton)

    def action_label(self, action_id: str) -> QLabel:
        return self.table.cellWidget(self._row[action_id], 0)

    def scroll_to(self, action_id: str) -> None:
        r = self._row.get(action_id)
        if r is not None:
            self.table.scrollToItem(self.table.item(r, 2), QAbstractItemView.ScrollHint.EnsureVisible)

    def _encode(self, action_id: str, pairs) -> list:
        scope = self._actions[action_id].scope if action_id in self._actions else "global"
        return [text if s == scope else {"key": text, "scope": s} for text, s in pairs]

    def record(self, action_id: str, index: int | None) -> None:
        if self.pending is not None:
            self.keep_conflict()
        if controls.active().builtin:
            return
        cell = self.cell(action_id)
        if index is None:
            chip = cell.add_chip("")
        else:
            chip = cell.chips[index]
        self.dialog.recorder.start(chip, partial(self.commit, action_id, index),
                                   partial(self.refresh_rows, [action_id], True))

    def commit(self, action_id: str, index: int | None, text: str) -> None:
        res = controls.active()
        pairs = list(res.keys.get(action_id, ()))
        if not text or any(norm_binding(t) == norm_binding(text)
                           for j, (t, _s) in enumerate(pairs) if j != index):
            self.refresh_rows([action_id], True)
            return
        old = list(pairs)
        was_over = action_id in res.overridden
        before = set(self.conflicts(res))
        if index is None:
            pairs.append((text, self._actions[action_id].scope))
        else:
            pairs[index] = (text, pairs[index][1])
        with self.dialog.quiet():
            controls.set_keys(res.id, action_id, self._encode(action_id, pairs))
        after = self.conflicts()
        fresh = [c for c in after if c not in before and action_id in (c[1], c[2])
                 and bindings_clash(text, c[0])]
        touched = {action_id}
        for c in set(after) | before:
            touched.update((c[1], c[2]))
        if fresh:
            others: list[str] = []
            for _b, a, b in fresh:
                other = b if a == action_id else a
                if other not in others:
                    others.append(other)
            self.pending = {"action": action_id, "text": text, "old": old, "was_over": was_over,
                            "others": others}
            self.banner.label.setText(f"{text} is already used by {self.label_of(others[0])}.")
            self.top.setCurrentWidget(self.banner)
        self.refresh_rows(touched)

    def _close_banner(self) -> dict | None:
        pending = self.pending
        self.pending = None
        self.top.setCurrentIndex(0)
        return pending

    def replace_conflict(self) -> None:
        pending = self._close_banner()
        if pending is None:
            return
        res = controls.active()
        touched = {pending["action"]}
        with self.dialog.quiet():
            for other in pending["others"]:
                pairs = [p for p in res.keys.get(other, ()) if not bindings_clash(p[0], pending["text"])]
                controls.set_keys(res.id, other, self._encode(other, pairs))
                touched.add(other)
        self.refresh_rows(touched)

    def keep_conflict(self) -> None:
        self._close_banner()

    def cancel_conflict(self) -> None:
        pending = self._close_banner()
        if pending is None:
            return
        res = controls.active()
        aid = pending["action"]
        touched = {aid} | set(pending["others"])
        with self.dialog.quiet():
            if pending["was_over"]:
                controls.set_keys(res.id, aid, self._encode(aid, pending["old"]))
            else:
                controls.reset_action(res.id, aid)
        self.refresh_rows(touched)

    def remove_binding(self, action_id: str, index: int) -> None:
        res = controls.active()
        if res.builtin:
            return
        pairs = list(res.keys.get(action_id, ()))
        if not 0 <= index < len(pairs):
            return
        removed = pairs.pop(index)
        touched = {action_id}
        for c in self.conflicts(res):
            if action_id in (c[1], c[2]) and bindings_clash(removed[0], c[0]):
                touched.update((c[1], c[2]))
        with self.dialog.quiet():
            controls.set_keys(res.id, action_id, self._encode(action_id, pairs))
        self.refresh_rows(touched)

    def reset_binding(self, action_id: str) -> None:
        res = controls.active()
        if res.builtin:
            return
        touched = {action_id}
        for c in self.conflicts(res):
            touched.update((c[1], c[2]))
        with self.dialog.quiet():
            controls.reset_action(res.id, action_id)
        for c in self.conflicts():
            touched.update((c[1], c[2]))
        self.refresh_rows(touched)


class RecordPad(QFrame):

    recorded = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsCtlPad")
        self.setFixedSize(PAD_W, PAD_H)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        lay = _vbox(self, (BANNER_PAD, 0, BANNER_PAD, 0))
        self.label = QLabel(PAD_TEXT, self)
        self.label.setObjectName("qsCtlPadText")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label)
        self.held: dict[int, str] = {}

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if not e.isAutoRepeat() and e.key() not in MODIFIER_KEYS and not e.modifiers() & HEAVY:
            self.held[e.key()] = key_name(e.key())
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent) -> None:
        if not e.isAutoRepeat():
            self.held.pop(e.key(), None)
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e) -> None:
        self.held.clear()
        super().focusOutEvent(e)

    def _held_key(self) -> str | None:
        if self.held:
            return next(iter(self.held.values()))
        try:
            shared = controls.held_set()
        except ImportError:
            return None
        for code in shared:
            return key_name(code)
        return None

    def _gesture(self, e: QMouseEvent, double: bool) -> dict | None:
        button = BUTTONS.get(e.button())
        if button is None:
            return None
        mods = e.modifiers()
        names = []
        if mods & Qt.KeyboardModifier.ShiftModifier:
            names.append("shift")
        if mods & Qt.KeyboardModifier.ControlModifier:
            names.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            names.append("alt")
        return {"button": button, "mods": names, "key": self._held_key(), "double": double, "op": "orbit"}

    def mousePressEvent(self, e: QMouseEvent) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        g = self._gesture(e, False)
        e.accept()
        if g is not None and self.isEnabled():
            self.recorded.emit(g)

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        g = self._gesture(e, True)
        e.accept()
        if g is not None and self.isEnabled():
            self.recorded.emit(g)


class GestureRow(QFrame):

    def __init__(self, page: "MousePage", index: int, gesture: dict, editable: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsCtlRow")
        self.setFixedHeight(GESTURE_ROW_H)
        self.gesture = gesture
        lay = _hbox(self, (ROW_PAD, 0, ROW_PAD, 0), HEADER_GAP)
        self.label = QLabel(gesture_text(gesture), self)
        self.label.setObjectName("qsCtlGesture")
        lay.addWidget(self.label, 1)
        self.combo = QComboBox(self)
        self.combo.setFixedSize(OP_COMBO_W, BUTTON_H)
        self.combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        prepare_combo(self.combo)
        self._fill(gesture)
        _mark_editing(self.combo, editable)
        self.combo.currentIndexChanged.connect(lambda i: page.set_choice(index, self.combo.itemData(i)))
        lay.addWidget(self.combo)
        self.up_button = _mark_editing(_tool_button("arrow_up", "Move Up", self), editable)
        self.down_button = _mark_editing(_tool_button("arrow_down", "Move Down", self), editable)
        self.remove_button = _mark_editing(_tool_button("close", "Remove Gesture", self), editable)
        self.up_button.clicked.connect(partial(page.move, index, -1))
        self.down_button.clicked.connect(partial(page.move, index, 1))
        self.remove_button.clicked.connect(partial(page.remove, index))
        for b in (self.up_button, self.down_button, self.remove_button):
            lay.addWidget(b)

    def _fill(self, g: dict) -> None:
        self.combo.blockSignals(True)
        if g.get("double"):
            self.combo.setEditable(True)
            self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            for text, op in OPS:
                self.combo.addItem(text, "op:" + op)
            for aid, action in controls.actions().items():
                self.combo.addItem(action.label, "action:" + aid)
            completer = self.combo.completer()
            if completer is not None:
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        else:
            for text, op in OPS:
                self.combo.addItem(text, "op:" + op)
        if g.get("action"):
            wanted = "action:" + str(g["action"])
        else:
            wanted = "op:" + str(g.get("op"))
        idx = self.combo.findData(wanted)
        self.combo.setCurrentIndex(max(idx, 0))
        self.combo.blockSignals(False)


class MousePage(QWidget):

    def __init__(self, dialog: "ControlsDialog") -> None:
        super().__init__(dialog)
        self.dialog = dialog
        self.rows: list[GestureRow] = []
        self._last: tuple | None = None
        lay = _vbox(self, (INSET, 0, INSET, INSET), PAGE_GAP)
        self.banner = Banner(self, buttons=False)
        self.banner.setVisible(False)
        lay.addWidget(self.banner)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget = QWidget()
        self.list_layout = _vbox(self.list_widget)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_widget)
        lay.addWidget(self.scroll, 1)
        bottom = QWidget(self)
        bl = _hbox(bottom, (0, 0, 0, 0), INSET)
        self.pad = RecordPad(bottom)
        self.pad.recorded.connect(self.add_gesture)
        bl.addWidget(self.pad)
        bl.addStretch(1)
        self.reset_button = _push("Reset Mouse", bottom)
        self.reset_button.clicked.connect(self.reset_mouse)
        bl.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addWidget(bottom)

    def gestures(self) -> list[dict]:
        return [dict(g) for g in controls.active().mouse]

    def editing_controls(self) -> list[QWidget]:
        out: list[QWidget] = []
        for row in self.rows:
            out.extend((row.combo, row.up_button, row.down_button, row.remove_button))
        out.extend((self.pad, self.reset_button))
        return out

    def refresh(self) -> None:
        res = controls.active()
        editable = not res.builtin
        for row in self.rows:
            row.setParent(None)
            row.deleteLater()
        self.rows = []
        for i, g in enumerate(res.mouse):
            row = GestureRow(self, i, dict(g), editable, self.list_widget)
            self.list_layout.insertWidget(i, row)
            self.rows.append(row)
        _mark_editing(self.pad, editable)
        _mark_editing(self.reset_button, editable)

    def _write(self, gestures: list[dict]) -> None:
        res = controls.active()
        if res.builtin:
            return
        with self.dialog.quiet():
            controls.set_mouse(res.id, gestures)
        self.refresh()

    def _hide_banner(self) -> None:
        self.banner.setVisible(False)

    def set_choice(self, index: int, data) -> None:
        self._hide_banner()
        gestures = self.gestures()
        if not 0 <= index < len(gestures) or data is None:
            return
        g = gestures[index]
        kind, _sep, value = str(data).partition(":")
        g.pop("op", None)
        g.pop("action", None)
        if kind == "action" and g.get("double"):
            g["action"] = value
        else:
            g["op"] = value
        self._write(gestures)

    def move(self, index: int, step: int) -> None:
        self._hide_banner()
        gestures = self.gestures()
        j = index + step
        if not (0 <= index < len(gestures) and 0 <= j < len(gestures)):
            return
        gestures[index], gestures[j] = gestures[j], gestures[index]
        self._write(gestures)

    def remove(self, index: int) -> None:
        self._hide_banner()
        gestures = self.gestures()
        if 0 <= index < len(gestures):
            gestures.pop(index)
            self._write(gestures)

    def add_gesture(self, g: dict) -> None:
        res = controls.active()
        if res.builtin:
            return
        gestures = self.gestures()
        if g.get("double") and self._last is not None:
            base = gesture_identity(dict(g, double=False))
            if self._last == base:
                for i in range(len(gestures) - 1, -1, -1):
                    if gesture_identity(gestures[i]) == base:
                        gestures.pop(i)
                        break
        self._last = None
        ident = gesture_identity(g)
        if any(gesture_identity(x) == ident for x in gestures):
            self.banner.label.setText(GESTURE_USED)
            self.banner.setVisible(True)
            if len(gestures) != len(res.mouse):
                self._write(gestures)
            return
        self._hide_banner()
        gestures.append(dict(g))
        if not g.get("double"):
            self._last = ident
        self._write(gestures)

    def reset_mouse(self) -> None:
        self._hide_banner()
        res = controls.active()
        if res.builtin:
            return
        with self.dialog.quiet():
            controls.reset_mouse(res.id)
        self.refresh()


class SettingRow(QFrame):

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsCtlRow")
        self.setFixedHeight(FORM_ROW_H)
        self.layout_ = _hbox(self, (INSET, 0, ROW_PAD, 0), HEADER_GAP)
        self.label = QLabel(label, self)
        self.label.setObjectName("qsDimLabel")
        self.label.setFixedWidth(LABEL_W)
        self.layout_.addWidget(self.label)
        self.control_slot = QHBoxLayout()
        self.control_slot.setContentsMargins(0, 0, 0, 0)
        self.control_slot.setSpacing(CHIP_GAP)
        self.layout_.addLayout(self.control_slot)
        self.layout_.addStretch(1)
        self.reset_button = _tool_button("undo", "Reset to Profile Base", self)
        self.layout_.addWidget(self.reset_button)

    def set_overridden(self, over: bool, editable: bool) -> None:
        self.setProperty("qsOverridden", "true" if over else "false")
        restyle(self)
        self.reset_button.setVisible(over and editable)
        _mark_editing(self.reset_button, editable)


class CursorPage(QWidget):

    def __init__(self, dialog: "ControlsDialog") -> None:
        super().__init__(dialog)
        self.dialog = dialog
        self.controls: dict[str, QWidget] = {}
        self.rows: dict[str, SettingRow] = {}
        self.kinds: dict[str, str] = {}
        self.modifier_combos: dict[str, QComboBox] = {}
        self.modal_cells: dict[str, ChipCell] = {}
        self.groups: list[CollapsibleGroup] = []
        lay = _vbox(self, (0, 0, 0, INSET))
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        il = _vbox(inner)
        for title, rows in CURSOR_GROUPS:
            group = self._group(title, inner)
            for key, label, kind, spec in rows:
                row = SettingRow(label, group.body)
                widget = self._make_control(key, kind, spec, row)
                row.control_slot.addWidget(widget)
                row.reset_button.clicked.connect(partial(self.reset_cursor, key))
                group.add_widget(row)
                self.controls[key] = widget
                self.rows[key] = row
                self.kinds[key] = kind
            il.addWidget(group)
        group = self._group("Modifiers", inner)
        for role, label in MODIFIER_ROWS:
            row = SettingRow(label, group.body)
            combo = QComboBox(row)
            combo.setFixedSize(FIELD_W, BUTTON_H)
            combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            prepare_combo(combo)
            for text, mod in MODIFIER_CHOICES:
                combo.addItem(text, mod)
            combo.currentIndexChanged.connect(
                lambda i, r=role, c=combo: self.set_modifier(r, c.itemData(i)))
            row.control_slot.addWidget(combo)
            row.reset_button.clicked.connect(partial(self.reset_modifier, role))
            group.add_widget(row)
            self.modifier_combos[role] = combo
            self.rows["modifiers." + role] = row
        il.addWidget(group)
        group = self._group("Modal Keys", inner)
        for key, label in MODAL_ROWS:
            row = SettingRow(label, group.body)
            cell = ChipCell(row)
            cell.add_button.clicked.connect(partial(self.record_modal, key, None))
            row.control_slot.addWidget(cell)
            row.reset_button.clicked.connect(partial(self.reset_modal, key))
            group.add_widget(row)
            self.modal_cells[key] = cell
            self.rows["modal." + key] = row
        il.addWidget(group)
        il.addStretch(1)
        self.scroll.setWidget(inner)
        lay.addWidget(self.scroll, 1)

    def editing_controls(self) -> list[QWidget]:
        out: list[QWidget] = list(self.controls.values()) + list(self.modifier_combos.values())
        for cell in self.modal_cells.values():
            out.extend(cell.chips)
            out.append(cell.add_button)
        out.extend(row.reset_button for row in self.rows.values())
        return out

    def _group(self, title: str, parent: QWidget) -> CollapsibleGroup:
        group = CollapsibleGroup(title, parent)
        group.content_layout().setSpacing(0)
        self.groups.append(group)
        return group

    def _make_control(self, key: str, kind: str, spec, parent: QWidget) -> QWidget:
        if kind == "combo":
            combo = QComboBox(parent)
            combo.setFixedSize(FIELD_W, BUTTON_H)
            combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            prepare_combo(combo)
            for text, value in spec:
                combo.addItem(text, value)
            combo.currentIndexChanged.connect(lambda i, k=key, c=combo: self.set_cursor(k, c.itemData(i)))
            return combo
        if kind == "bool":
            toggle = ToggleSwitch(parent)
            toggle.setFixedSize(TOGGLE_W, TOGGLE_H)
            toggle.toggled.connect(lambda on, k=key: self.set_cursor(k, bool(on)))
            return toggle
        if kind == "float":
            low, high, step, decimals, suffix = spec
            spin = QDoubleSpinBox(parent)
            spin.setLocale(QLocale.c())
            spin.setDecimals(decimals)
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setSuffix(suffix)
            spin.setKeyboardTracking(False)
            spin.setFixedSize(FIELD_W, BUTTON_H)
            spin.valueChanged.connect(lambda v, k=key, d=decimals: self.set_cursor(k, round(float(v), d)))
            return spin
        low, high, step, suffix = spec
        spin = QSpinBox(parent)
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        spin.setFixedSize(FIELD_W, BUTTON_H)
        spin.valueChanged.connect(lambda v, k=key: self.set_cursor(k, int(v)))
        return spin

    def refresh(self) -> None:
        res = controls.active()
        editable = not res.builtin
        for key, widget in self.controls.items():
            value = res.cursor.get(key)
            widget.blockSignals(True)
            kind = self.kinds[key]
            if kind == "combo":
                idx = widget.findData(value)
                widget.setCurrentIndex(max(idx, 0))
            elif kind == "bool":
                widget.setChecked(bool(value))
                widget.update()
            elif value is not None:
                widget.setValue(value)
            widget.blockSignals(False)
            _mark_editing(widget, editable)
            self.rows[key].set_overridden(overridden(res, "cursor", key), editable)
        for role, combo in self.modifier_combos.items():
            combo.blockSignals(True)
            idx = combo.findData(res.modifiers.get(role))
            combo.setCurrentIndex(max(idx, 0))
            combo.blockSignals(False)
            _mark_editing(combo, editable)
            self.rows["modifiers." + role].set_overridden(overridden(res, "modifiers", role), editable)
        for key in list(self.modal_cells):
            self._refresh_modal(key, res, editable)

    def _refresh_modal(self, key: str, res, editable: bool) -> None:
        old = self.modal_cells[key]
        row = self.rows["modal." + key]
        cell = ChipCell(row)
        for i, text in enumerate(res.modal.get(key, ())):
            chip = cell.add_chip(text)
            _mark_editing(chip, editable)
            chip.clicked.connect(partial(self.record_modal, key, i))
            chip.removed.connect(partial(self.remove_modal, key, i))
        _mark_editing(cell.add_button, editable)
        cell.add_button.clicked.connect(partial(self.record_modal, key, None))
        row.control_slot.replaceWidget(old, cell)
        old.setParent(None)
        old.deleteLater()
        self.modal_cells[key] = cell
        row.set_overridden(overridden(res, "modal", key), editable)

    def _apply(self, fn, *args) -> None:
        res = controls.active()
        if res.builtin:
            return
        with self.dialog.quiet():
            fn(res.id, *args)
        self.refresh()

    def set_cursor(self, key: str, value) -> None:
        self._apply(controls.set_cursor, key, value)

    def reset_cursor(self, key: str) -> None:
        self._apply(controls.reset_cursor, key)

    def set_modifier(self, role: str, mod) -> None:
        self._apply(controls.set_modifier, role, mod)

    def reset_modifier(self, role: str) -> None:
        self._apply(controls.reset_modifier, role)

    def reset_modal(self, key: str) -> None:
        self._apply(controls.reset_modal, key)

    def record_modal(self, key: str, index: int | None) -> None:
        if controls.active().builtin:
            return
        cell = self.modal_cells[key]
        chip = cell.add_chip("") if index is None else cell.chips[index]
        self.dialog.recorder.start(chip, partial(self.commit_modal, key, index), self.refresh, single=True)

    def commit_modal(self, key: str, index: int | None, text: str) -> None:
        res = controls.active()
        keys = list(res.modal.get(key, ()))
        if not text or any(norm_binding(t) == norm_binding(text) for j, t in enumerate(keys) if j != index):
            self.refresh()
            return
        if index is None:
            keys.append(text)
        else:
            keys[index] = text
        self._apply(controls.set_modal, key, keys)

    def remove_modal(self, key: str, index: int) -> None:
        keys = list(controls.active().modal.get(key, ()))
        if 0 <= index < len(keys):
            keys.pop(index)
            self._apply(controls.set_modal, key, keys)


class ControlsDialog(QDialog):

    def __init__(self, window: QWidget | None = None) -> None:
        super().__init__(window)
        self.setObjectName("qsControlsDialog")
        self.setWindowTitle("Controls")
        self.setModal(False)
        self.setFixedSize(DIALOG_W, DIALOG_H)
        self.setStyleSheet(_qss())
        self._quiet = 0
        self._placed = False
        self.recorder = KeyRecorder(self)
        outer = _vbox(self, (INSET, INSET, INSET, INSET))
        self.body = make_card(QFrame(self))
        self.body.setObjectName("qsControlsBody")
        outer.addWidget(self.body)
        bl = _vbox(self.body)
        header = QWidget(self.body)
        header.setFixedHeight(HEADER_H)
        hl = _hbox(header, (HEADER_PAD, 0, HEADER_PAD, 0), HEADER_GAP)
        self.profile_label = QLabel("Profile", header)
        self.profile_label.setObjectName("qsCtlHeader")
        self.profile_label.setFont(header_font(self.profile_label.font()))
        hl.addWidget(self.profile_label)
        self.profile_combo = QComboBox(header)
        self.profile_combo.setObjectName("qsCtlProfile")
        self.profile_combo.setFixedSize(COMBO_W, BUTTON_H)
        self.profile_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        prepare_combo(self.profile_combo)
        self.profile_combo.currentIndexChanged.connect(self._combo_changed)
        hl.addWidget(self.profile_combo)
        self.duplicate_button = _push("Duplicate", header)
        self.rename_button = _push("Rename", header)
        self.delete_button = _push("Delete", header)
        self.import_button = _push("Import...", header)
        self.export_button = _push("Export...", header)
        for b in (self.duplicate_button, self.rename_button, self.delete_button, self.import_button,
                  self.export_button):
            hl.addWidget(b)
        hl.addStretch(1)
        self.duplicate_button.clicked.connect(self.duplicate_profile)
        self.rename_button.clicked.connect(self.rename_profile)
        self.delete_button.clicked.connect(self.delete_profile)
        self.import_button.clicked.connect(self.import_profile)
        self.export_button.clicked.connect(self.export_profile)
        bl.addWidget(header)
        self.note = QLabel(NOTE_TEXT, self.body)
        self.note.setObjectName("qsCtlNote")
        self.note.setFixedHeight(NOTE_H)
        bl.addWidget(self.note)
        self.tabs = PanelTabBar(TABS, self.body)
        self.tabs.setFixedHeight(TAB_H)
        bl.addWidget(self.tabs)
        self.pages = QStackedWidget(self.body)
        self.pages.layout().setContentsMargins(0, 0, 0, 0)
        self.pages.layout().setSpacing(0)
        self.keyboard = KeyboardPage(self)
        self.mouse = MousePage(self)
        self.cursor_page = CursorPage(self)
        for page in (self.keyboard, self.mouse, self.cursor_page):
            self.pages.addWidget(page)
        self.tabs.currentChanged.connect(self.set_page)
        bl.addWidget(self.pages, 1)
        footer = QWidget(self.body)
        footer.setFixedHeight(FOOTER_H)
        fl = _hbox(footer, (HEADER_PAD, 0, HEADER_PAD, 0), HEADER_GAP)
        self.reset_profile_button = _push("Reset Profile", footer)
        self.reset_profile_button.clicked.connect(self.reset_profile)
        fl.addWidget(self.reset_profile_button)
        fl.addStretch(1)
        self.close_button = _push("Close", footer)
        self.close_button.clicked.connect(self.close)
        fl.addWidget(self.close_button)
        bl.addWidget(footer)
        controls.hub().profileChanged.connect(self._on_profile_changed)
        self.keyboard.rebuild()
        self.reload()

    @contextlib.contextmanager
    def quiet(self):
        self._quiet += 1
        try:
            yield
        finally:
            self._quiet -= 1

    def _on_profile_changed(self, _pid: str) -> None:
        if self._quiet:
            return
        try:
            from shiboken6 import isValid
        except ImportError:
            isValid = None
        if isValid is not None and not isValid(self):
            return
        self.reload()

    def set_page(self, index: int) -> None:
        self.recorder.cancel()
        self.tabs.setCurrentIndex(index)
        self.pages.setCurrentIndex(index)

    def page_names(self) -> list[str]:
        return self.tabs.tab_texts()

    def reload(self) -> None:
        self.recorder.cancel()
        self.keyboard._close_banner()
        self.mouse._hide_banner()
        res = controls.active()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for doc in controls.profiles():
            self.profile_combo.addItem(doc["name"], doc["id"])
        idx = self.profile_combo.findData(res.id)
        self.profile_combo.setCurrentIndex(max(idx, 0))
        self.profile_combo.blockSignals(False)
        editable = not res.builtin
        _mark_editing(self.rename_button, editable)
        _mark_editing(self.delete_button, editable)
        _mark_editing(self.reset_profile_button, editable)
        self.note.setVisible(not editable)
        self.keyboard.refresh()
        self.mouse.refresh()
        self.cursor_page.refresh()

    def editing_controls(self) -> list[QWidget]:
        out: list[QWidget] = [self.rename_button, self.delete_button, self.reset_profile_button]
        out.extend(self.keyboard.editing_controls())
        out.extend(self.mouse.editing_controls())
        out.extend(self.cursor_page.editing_controls())
        return out

    def _combo_changed(self, index: int) -> None:
        pid = self.profile_combo.itemData(index)
        if pid and pid != controls.active_id():
            with self.quiet():
                controls.select(pid)
            self.reload()

    def choose_profile(self, profile_id: str) -> None:
        idx = self.profile_combo.findData(profile_id)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

    def duplicate_profile(self) -> str:
        with self.quiet():
            pid = controls.duplicate(controls.active_id())
        self.reload()
        return pid

    def rename_profile(self) -> None:
        res = controls.active()
        if res.builtin:
            return
        name = ask_profile_name(self, res.name)
        if name is None:
            return
        try:
            with self.quiet():
                controls.rename(res.id, name)
        except ValueError as exc:
            show_error(str(exc))
        self.reload()

    def delete_profile(self) -> None:
        res = controls.active()
        if res.builtin or not confirm(self, f"Delete the profile {res.name}?"):
            return
        with self.quiet():
            controls.delete(res.id)
        self.reload()

    def reset_profile(self) -> None:
        res = controls.active()
        if res.builtin or not confirm(self, f"Remove every change made to {res.name}?"):
            return
        with self.quiet():
            controls.reset_profile(res.id)
        self.reload()

    def import_profile(self) -> str | None:
        path = choose_import_file()
        if not path:
            return None
        try:
            with self.quiet():
                pid = controls.import_profile(path)
        except (ValueError, OSError) as exc:
            show_error(str(exc))
            return None
        self.reload()
        return pid

    def export_profile(self) -> str | None:
        res = controls.active()
        path = choose_export_file(res.name)
        if not path:
            return None
        try:
            controls.export_profile(res.id, path)
        except (ValueError, OSError) as exc:
            show_error(str(exc))
            return None
        return path

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if self.recorder.active():
            self.recorder.handle(e)
            e.accept()
            return
        super().keyPressEvent(e)

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.ShortcutOverride and self.recorder.active():
            e.accept()
            return True
        return super().event(e)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if not self._placed:
            self._placed = True
            parent = self.parentWidget()
            if parent is not None:
                center = parent.frameGeometry().center()
                self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
            try:
                from quartz_studio.app import apply_native_titlebar
            except ImportError:
                apply_native_titlebar = None
            if apply_native_titlebar is not None:
                apply_native_titlebar(self)

    def hideEvent(self, e) -> None:
        self.recorder.cancel()
        super().hideEvent(e)
        if not e.spontaneous():
            QTimer.singleShot(0, self, self._release)

    def _release(self) -> None:
        if not self.isVisible():
            self.deleteLater()


_LOOSE: list = [None]


def _valid(widget) -> bool:
    if widget is None:
        return False
    try:
        from shiboken6 import isValid
    except ImportError:
        return True
    return isValid(widget)


def dialog_for(window=None) -> ControlsDialog | None:
    if window is None:
        dlg = _LOOSE[0]
    else:
        dlg = getattr(window, "_qs_controls_dialog", None)
    return dlg if _valid(dlg) else None


def open_editor(window=None) -> ControlsDialog:
    if window is None:
        window = controls.window()
    dlg = dialog_for(window)
    if dlg is None:
        dlg = ControlsDialog(window)
        if window is None:
            _LOOSE[0] = dlg
        else:
            window._qs_controls_dialog = dlg
    if dlg.isVisible():
        dlg.raise_()
        dlg.activateWindow()
        return dlg
    dlg.reload()
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg


def is_recording() -> bool:
    for dlg in [_LOOSE[0]] + [w for w in QApplication.topLevelWidgets() if isinstance(w, ControlsDialog)]:
        if _valid(dlg) and dlg.recorder.active():
            return True
    return False
