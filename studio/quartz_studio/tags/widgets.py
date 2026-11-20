from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QCheckBox, QComboBox,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from .. import icons, theme
from ..ext import store
from ..modeling.panel import ScrubIntSpin, ScrubSpin
from ..widgets.common import CollapsibleGroup, FieldRow, prepare_combo, prepare_popup
from . import core
from .registry import TAG_SPECS, get_tag_spec, has_tag_spec, specs_by_category
from .runtime import evaluate_tags, reset_runtime

__all__ = [
    "CATEGORY_TINTS",
    "ROW_H",
    "TagChip",
    "EnableToggle",
    "TagRow",
    "ParamEditor",
    "TagsPanel",
    "TagAttributes",
    "build_add_menu",
    "current_frame",
]

COALESCE_KINDS = ("int", "float", "percent", "angle", "distance", "vector", "code")

ROW_H = 32
CHIP = 24
CHIP_ICON = 16
FIELD = 24
LABEL_W = 112
INDENT = 16
TOOL = 24
TOOL_ICON = 16

CATEGORY_TINTS = {
    "Rendering Tags": theme.TINT_CITRINE,
    "Modeling Tags": theme.TINT_MINT,
    "Animation Tags": theme.TINT_ROSE,
    "Programming Tags": theme.TEXT_SECONDARY,
    "Simulation Tags": theme.TINT_AMETHYST,
    "Character Tags": theme.AXIS_Z,
}

FRAME_KEYS = ("frame", "current_frame")


def current_frame(scene) -> float:
    for key in FRAME_KEYS:
        v = store.get_scene_data(scene, key)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _font(px: int = 12, bold: bool = False, mono: bool = False) -> QFont:
    if mono:
        f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    else:
        f = QFont(theme.FONT_FAMILY)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


def _header_font() -> QFont:
    f = _font(12, True)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, theme.HEADER_LETTER_SPACING)
    return f


def _tint_for(tag_type: str) -> str:
    if has_tag_spec(tag_type):
        return CATEGORY_TINTS.get(get_tag_spec(tag_type).category, theme.TEXT_SECONDARY)
    return theme.TEXT_SECONDARY


def _icon_for(tag_type: str) -> str:
    return get_tag_spec(tag_type).icon if has_tag_spec(tag_type) else "tag"


def _tool_button(icon_name: str, tip: str, parent: QWidget) -> QToolButton:
    b = QToolButton(parent)
    b.setIcon(icons.icon(icon_name, TOOL_ICON, theme.TEXT_SECONDARY))
    b.setIconSize(QSize(TOOL_ICON, TOOL_ICON))
    b.setFixedSize(TOOL, TOOL)
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


def _hairline(parent: QWidget) -> QFrame:
    rule = QFrame(parent)
    rule.setFixedHeight(1)
    rule.setStyleSheet(f"background: {theme.HAIRLINE}; border: none;")
    return rule


class TagChip(QWidget):

    def __init__(self, tag_type: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(CHIP, CHIP)
        self._type = tag_type
        self._dim = False

    def set_type(self, tag_type: str) -> None:
        if tag_type != self._type:
            self._type = tag_type
            self.update()

    def tag_type(self) -> str:
        return self._type

    def set_dim(self, dim: bool) -> None:
        if dim != self._dim:
            self._dim = dim
            self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tint = _tint_for(self._type)
        if self._dim:
            p.setOpacity(0.4)
        r = QRectF(0, 0, CHIP, CHIP)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.mix(tint, theme.SURFACE_CARD, 0.24)))
        p.drawRoundedRect(r, theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)
        inset = (CHIP - CHIP_ICON) / 2
        icons.render(p, QRectF(inset, inset, CHIP_ICON, CHIP_ICON), _icon_for(self._type), tint)
        p.end()


class EnableToggle(QAbstractButton):

    def __init__(self, parent: QWidget | None = None, checked: bool = True) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(32, 16)
        self.setToolTip("Enable")

    def sizeHint(self) -> QSize:
        return QSize(32, 16)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        on = self.isChecked()
        r = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT if on else theme.HAIRLINE_STRONG))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = 12.0
        x = r.right() - d - 2 if on else r.left() + 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT_ON if on else theme.TEXT_SECONDARY))
        p.drawEllipse(QRectF(x, r.top() + (r.height() - d) / 2, d, d))
        p.end()


class TagRow(QWidget):

    toggled = Signal(int, bool)
    renamed = Signal(int, str)

    def __init__(self, index: int, tag: dict, summary: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.setFixedHeight(ROW_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.SPACE_2, 0, theme.SPACE_2, 0)
        lay.setSpacing(theme.SPACE_2)
        self.chip = TagChip(tag.get("type", ""), self)
        lay.addWidget(self.chip)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(0)
        self.name = QLabel(tag.get("name", ""), self)
        self.name.setFont(_font(12, True))
        self.name_edit = QLineEdit(tag.get("name", ""), self)
        self.name_edit.setFont(_font(12, True))
        self.name_edit.setFixedHeight(FIELD)
        self.name_edit.setVisible(False)
        self.name_edit.editingFinished.connect(self._finish_rename)
        self.name_edit.installEventFilter(self)
        self.summary = QLabel(summary, self)
        self.summary.setObjectName("qsDimLabel")
        self.summary.setFont(_font(12))
        text.addWidget(self.name)
        text.addWidget(self.name_edit)
        text.addWidget(self.summary)
        self.summary.setVisible(bool(summary))
        lay.addLayout(text, 1)
        self.toggle = EnableToggle(self, bool(tag.get("enabled", True)))
        self.toggle.toggled.connect(lambda v: self.toggled.emit(self.index, bool(v)))
        lay.addWidget(self.toggle)
        self.set_enabled_look(bool(tag.get("enabled", True)))

    def is_renaming(self) -> bool:
        return self.name_edit.isVisible()

    def start_rename(self) -> None:
        self.name_edit.setText(self.name.text())
        self.name.setVisible(False)
        self.summary.setVisible(False)
        self.name_edit.setVisible(True)
        self.name_edit.selectAll()
        self.name_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def cancel_rename(self) -> None:
        self.name_edit.setVisible(False)
        self.name.setVisible(True)
        self.summary.setVisible(bool(self.summary.text()))

    def _finish_rename(self) -> None:
        if not self.name_edit.isVisible():
            return
        text = self.name_edit.text().strip()
        self.cancel_rename()
        if text and text != self.name.text():
            self.renamed.emit(self.index, text)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.name_edit and event.type() == QEvent.Type.KeyPress                 and event.key() == Qt.Key.Key_Escape:
            self.cancel_rename()
            return True
        return False

    def mouseDoubleClickEvent(self, e) -> None:
        self.start_rename()

    def set_enabled_look(self, on: bool) -> None:
        self.chip.set_dim(not on)
        color = theme.TEXT_PRIMARY if on else theme.TEXT_MUTED
        self.name.setStyleSheet(f"color: {color};")


def build_add_menu(menu: QMenu, callback) -> QMenu:
    for category, specs in specs_by_category():
        sub = prepare_popup(menu.addMenu(category))
        for spec in specs:
            act = sub.addAction(icons.icon(spec.icon, TOOL_ICON, CATEGORY_TINTS.get(category)),
                                spec.label)
            act.setData(spec.id)
            act.setToolTip(spec.description)
            act.triggered.connect(lambda _c=False, tid=spec.id: callback(tid))
    return menu


class _Listener:

    def __init__(self, fn) -> None:
        self.fn = fn
        self.alive = True

    def __call__(self, owner, key) -> None:
        if self.alive:
            self.fn(owner, key)


def _listen(widget: QWidget, fn) -> _Listener:
    lis = _Listener(fn)
    store._LISTENERS.append(lis)

    def drop(*_a) -> None:
        lis.alive = False
        try:
            store._LISTENERS.remove(lis)
        except ValueError:
            pass

    widget.destroyed.connect(drop)
    return lis


def _scene_or_default(scene):
    if scene is None:
        from ..scene import get_scene
        scene = get_scene()
    return scene


class TagsPanel(QWidget):

    currentTagChanged = Signal(object, int)

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = _scene_or_default(scene)
        core.watch_scene(self.scene)
        self.setObjectName("qsTagsPanel")
        self.setMinimumWidth(256)
        self._syncing = False
        self._evaluating = False
        self._obj = None
        self._memory: dict[int, int] = {}
        self.rows: list[TagRow] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget(self)
        head.setFixedHeight(theme.CARD_HEADER_H)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(theme.SPACE_3, 0, theme.SPACE_2, 0)
        hl.setSpacing(theme.SPACE_2)
        self.title = QLabel("Tags", head)
        self.title.setFont(_header_font())
        self.title.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        hl.addWidget(self.title)
        self.object_label = QLabel("", head)
        self.object_label.setObjectName("qsDimLabel")
        self.object_label.setFont(_font(12))
        hl.addWidget(self.object_label, 1)
        lay.addWidget(head)
        lay.addWidget(_hairline(self))

        bar = QWidget(self)
        bar.setFixedHeight(ROW_H)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(theme.SPACE_2, 0, theme.SPACE_2, 0)
        bl.setSpacing(theme.SPACE_1)
        self.add_button = _tool_button("plus", "Add Tag", bar)
        self.add_menu = prepare_popup(QMenu(self.add_button))
        build_add_menu(self.add_menu, self.add_tag)
        self.add_button.setMenu(self.add_menu)
        self.add_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.remove_button = _tool_button("close", "Remove Tag", bar)
        self.duplicate_button = _tool_button("add_layer", "Duplicate Tag", bar)
        self.up_button = _tool_button("arrow_up", "Move Up", bar)
        self.down_button = _tool_button("arrow_down", "Move Down", bar)
        for b in (self.add_button, self.remove_button, self.duplicate_button, self.up_button,
                  self.down_button):
            bl.addWidget(b)
        bl.addStretch(1)
        self.count_label = QLabel("", bar)
        self.count_label.setObjectName("qsDimLabel")
        self.count_label.setFont(_font(12))
        bl.addWidget(self.count_label)
        lay.addWidget(bar)

        self.list = QListWidget(self)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        self.list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; outline: none; }}"
            f"QListWidget::item {{ border-radius: {theme.CONTROL_RADIUS}px; margin: 2px 4px; }}"
            f"QListWidget::item:selected {{ background: {theme.ACCENT_TINT}; }}"
            f"QListWidget::item:hover:!selected {{ background: {theme.SURFACE_HOVER}; }}")
        lay.addWidget(self.list, 1)
        self.empty_label = QLabel("No object selected", self)
        self.empty_label.setObjectName("qsDimLabel")
        self.empty_label.setFont(_font(12))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setFixedHeight(48)
        lay.addWidget(self.empty_label)

        lay.addWidget(_hairline(self))
        foot = QWidget(self)
        foot.setFixedHeight(ROW_H)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(theme.SPACE_2, 0, theme.SPACE_2, 0)
        fl.setSpacing(theme.SPACE_2)
        flabel = QLabel("Frame", foot)
        flabel.setObjectName("qsDimLabel")
        flabel.setFont(_font(12))
        fl.addWidget(flabel)
        self.frame_spin = ScrubSpin(foot)
        self.frame_spin.setFixedHeight(FIELD)
        self.frame_spin.setFixedWidth(72)
        self.frame_spin.setDecimals(0)
        self.frame_spin.setRange(-100000, 100000)
        self.frame_spin.setValue(current_frame(self.scene))
        fl.addWidget(self.frame_spin)
        self.live_box = QCheckBox("Live", foot)
        self.live_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.live_box.setToolTip("Evaluate runtime tags whenever the scene changes")
        fl.addWidget(self.live_box)
        fl.addStretch(1)
        self.evaluate_button = QPushButton("Evaluate", foot)
        self.reset_button = QPushButton("Reset", foot)
        self.reset_button.setToolTip("Put objects back to their base transform")
        for b in (self.evaluate_button, self.reset_button):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setFixedHeight(FIELD)
            fl.addWidget(b)
        lay.addWidget(foot)

        self.remove_button.clicked.connect(self.remove_current)
        self.duplicate_button.clicked.connect(self.duplicate_current)
        self.up_button.clicked.connect(lambda: self.move_current(-1))
        self.down_button.clicked.connect(lambda: self.move_current(1))
        self.list.currentRowChanged.connect(self._on_row)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.evaluate_button.clicked.connect(self.evaluate_now)
        self.reset_button.clicked.connect(self.reset_runtime)
        self.frame_spin.valueChanged.connect(self._on_frame)
        self.live_box.toggled.connect(self.set_live)

        self.scene.selectionChanged.connect(self.refresh)
        self.scene.objectsChanged.connect(self.refresh)
        self.scene.changed.connect(self._on_scene_changed)
        _listen(self, self._on_store)
        self.refresh()

    def sizeHint(self) -> QSize:
        return QSize(320, 384)

    def obj(self):
        a = self.scene.active
        return a if a is not None and a in self.scene.objects else None

    def current_index(self) -> int | None:
        row = self.list.currentRow()
        return row if row >= 0 and self._obj is not None and row < len(core.tags_of(self._obj)) else None

    def refresh(self) -> None:
        core.watch_scene(self.scene)
        core.sync_renames(self.scene)
        obj = self.obj()
        same = obj is self._obj
        self._obj = obj
        tags = core.tags_of(obj) if obj is not None else []
        keep = self.list.currentRow() if same else self._memory.get(id(obj), 0)
        cur_obj, cur_idx = core.current_tag(self.scene)
        if cur_obj is obj and cur_idx is not None:
            keep = cur_idx
        self._syncing = True
        try:
            self.list.clear()
            self.rows = []
            for i, tag in enumerate(tags):
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, ROW_H + 4))
                item.setData(Qt.ItemDataRole.UserRole, i)
                self.list.addItem(item)
                row = TagRow(i, tag, core.tag_summary(obj, i))
                row.toggled.connect(self._on_toggled)
                row.renamed.connect(self._on_renamed)
                self.list.setItemWidget(item, row)
                self.rows.append(row)
            if tags:
                self.list.setCurrentRow(max(0, min(keep, len(tags) - 1)) if keep is not None else 0)
        finally:
            self._syncing = False
        self.object_label.setText(obj.name if obj is not None else "")
        self.count_label.setText(f"{len(tags)} tags" if obj is not None else "")
        self.empty_label.setVisible(obj is None or not tags)
        self.empty_label.setText("No object selected" if obj is None else "No tags, use + to add one")
        self.add_button.setEnabled(obj is not None)
        self._sync_buttons()
        self._publish()

    def _sync_buttons(self) -> None:
        idx = self.current_index()
        n = len(core.tags_of(self._obj)) if self._obj is not None else 0
        self.remove_button.setEnabled(idx is not None)
        dup_ok = idx is not None
        if dup_ok:
            t = core.tag_at(self._obj, idx)
            spec = TAG_SPECS.get(t.get("type", ""))
            dup_ok = spec is None or not spec.unique
        self.duplicate_button.setEnabled(dup_ok)
        self.up_button.setEnabled(idx is not None and idx > 0)
        self.down_button.setEnabled(idx is not None and idx < n - 1)

    def _publish(self) -> None:
        idx = self.current_index()
        if self._obj is not None and idx is not None:
            self._memory[id(self._obj)] = idx
        cur_obj, cur_idx = core.current_tag(self.scene)
        if cur_obj is not self._obj or cur_idx != idx:
            self._syncing = True
            try:
                core.set_current_tag(self.scene, self._obj, idx)
            finally:
                self._syncing = False
        self.currentTagChanged.emit(self._obj, -1 if idx is None else idx)

    def _on_row(self, _row: int) -> None:
        if self._syncing:
            return
        self._sync_buttons()
        self._publish()

    def select_index(self, index: int) -> None:
        if 0 <= index < self.list.count():
            self.list.setCurrentRow(index)

    def _on_toggled(self, index: int, flag: bool) -> None:
        if self._obj is None:
            return
        core.set_tag_enabled(self._obj, index, flag)

    def _on_renamed(self, index: int, name: str) -> None:
        if self._obj is None or core.tag_at(self._obj, index) is None:
            return
        core.rename_tag(self._obj, index, name)
        self.refresh()

    def rename_current(self) -> bool:
        idx = self.current_index()
        if idx is None or idx >= len(self.rows):
            return False
        self.rows[idx].start_rename()
        return True

    def _on_rows_moved(self, _parent, start: int, end: int, _dest, row: int) -> None:
        if self._syncing or self._obj is None:
            return
        target = row if row < start else row - (end - start + 1)
        if target == start:
            return
        if core.move_tag(self._obj, start, target):
            core.set_current_tag(self.scene, self._obj, target)
        QTimer.singleShot(0, self.refresh)

    def drop_move(self, index: int, new_index: int) -> bool:
        if self._obj is None or not 0 <= index < self.list.count():
            return False
        dest = max(0, min(int(new_index), self.list.count() - 1))
        dest = dest + 1 if dest > index else dest
        return self.list.model().moveRows(self.list.rootIndex(), index, 1, self.list.rootIndex(), dest)

    def add_tag(self, tag_id: str) -> int | None:
        obj = self.obj()
        if obj is None:
            return None
        index = core.add_tag(obj, tag_id, scene=self.scene)
        core.set_current_tag(self.scene, obj, index)
        self.refresh()
        self.select_index(index)
        return index

    def remove_current(self) -> None:
        idx = self.current_index()
        if idx is None:
            return
        core.remove_tag(self._obj, idx)
        n = len(core.tags_of(self._obj))
        core.set_current_tag(self.scene, self._obj, min(idx, n - 1) if n else None)
        self.refresh()

    def duplicate_current(self) -> None:
        idx = self.current_index()
        if idx is None:
            return
        new = core.duplicate_tag(self._obj, idx)
        if new is not None:
            core.set_current_tag(self.scene, self._obj, new)
            self.refresh()

    def move_current(self, delta: int) -> None:
        idx = self.current_index()
        if idx is None:
            return
        target = idx + int(delta)
        if core.move_tag(self._obj, idx, target):
            core.set_current_tag(self.scene, self._obj, target)
            self.refresh()

    def _context_menu(self, pos) -> None:
        menu = self.context_menu()
        menu.popup(self.list.viewport().mapToGlobal(pos))

    def context_menu(self) -> QMenu:
        menu = prepare_popup(QMenu(self))
        add = prepare_popup(menu.addMenu("Add Tag"))
        build_add_menu(add, self.add_tag)
        add.setEnabled(self._obj is not None)
        idx = self.current_index()
        if idx is not None:
            tag = core.tag_at(self._obj, idx)
            menu.addSeparator()
            menu.addAction("Disable" if tag.get("enabled", True) else "Enable",
                           lambda: core.set_tag_enabled(self._obj, idx, not tag.get("enabled", True)))
            menu.addAction("Rename", self.rename_current)
            menu.addAction("Duplicate", self.duplicate_current).setEnabled(
                self.duplicate_button.isEnabled())
            menu.addAction("Move Up", lambda: self.move_current(-1)).setEnabled(idx > 0)
            menu.addAction("Move Down", lambda: self.move_current(1)).setEnabled(
                idx < len(core.tags_of(self._obj)) - 1)
            menu.addAction("Remove", self.remove_current)
            if has_tag_spec(tag.get("type", "")):
                spec = get_tag_spec(tag["type"])
                if spec.actions:
                    menu.addSeparator()
                    for a in spec.actions:
                        menu.addAction(a.label, lambda key=a.key: self.run_action(key))
        return menu

    def run_action(self, key: str):
        idx = self.current_index()
        if idx is None:
            return None
        result = core.run_action(self.scene, self._obj, idx, key)
        self.scene.changed.emit()
        return result

    def _on_store(self, owner, key) -> None:
        if self._syncing:
            return
        if key == core.TAGS_KEY and owner is self._obj and owner is not None:
            self.refresh()
            if self.live_box.isChecked():
                self.evaluate_now()
        elif key in FRAME_KEYS and owner is self.scene:
            frame = current_frame(self.scene)
            if frame != self.frame_spin.value():
                self.frame_spin.blockSignals(True)
                self.frame_spin.setValue(frame)
                self.frame_spin.blockSignals(False)
                if self.live_box.isChecked():
                    self.evaluate_now()
        elif key == core.CURRENT_KEY and owner is self.scene:
            obj, idx = core.current_tag(self.scene)
            if obj is self._obj and idx is not None and idx != self.list.currentRow():
                self._syncing = True
                try:
                    self.list.setCurrentRow(idx)
                finally:
                    self._syncing = False
                self._sync_buttons()
                self.currentTagChanged.emit(self._obj, idx)

    def _on_frame(self, value: float) -> None:
        if self.live_box.isChecked():
            self.evaluate_now()

    def frame(self) -> float:
        return float(self.frame_spin.value())

    def set_live(self, flag: bool) -> None:
        if self.live_box.isChecked() != bool(flag):
            self.live_box.setChecked(bool(flag))
            return
        if flag:
            self.evaluate_now()

    def is_live(self) -> bool:
        return self.live_box.isChecked()

    def _on_scene_changed(self) -> None:
        if self._evaluating:
            return
        if self.live_box.isChecked():
            self.evaluate_now()
        elif self._obj is not None:
            for i, row in enumerate(self.rows):
                row.summary.setText(core.tag_summary(self._obj, i))

    def evaluate_now(self) -> list:
        if self._evaluating:
            return []
        self._evaluating = True
        try:
            changed = evaluate_tags(self.scene, self.frame())
            if changed:
                self.scene.changed.emit()
        finally:
            self._evaluating = False
        return changed

    def reset_runtime(self) -> int:
        self.live_box.setChecked(False)
        self._evaluating = True
        try:
            n = reset_runtime(self.scene)
            if n:
                self.scene.changed.emit()
        finally:
            self._evaluating = False
        return n


class ParamEditor(QWidget):

    edited = Signal(str, object)

    def __init__(self, param, scene=None, obj=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.param = param
        self.scene = scene
        self.obj = obj
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.SPACE_1)
        self.widgets: list[QWidget] = []
        self._timer: QTimer | None = None
        self._value = None
        kind = param.kind
        if kind == "bool":
            box = QCheckBox(self)
            box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            box.toggled.connect(lambda v: self.edited.emit(param.key, bool(v)))
            lay.addWidget(box)
            lay.addStretch(1)
            self.widgets.append(box)
        elif kind in ("choice", "object", "tag_ref"):
            combo = prepare_combo(QComboBox(self))
            self._value = param.initial()
            combo.setFixedHeight(FIELD)
            combo.setMinimumWidth(64)
            combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            self._fill_combo(combo)
            combo.activated.connect(lambda i, c=combo: self._on_combo(c, i))
            lay.addWidget(combo, 1)
            self.widgets.append(combo)
        elif kind == "int":
            spin = ScrubIntSpin(self)
            spin.setFixedHeight(FIELD)
            spin.setRange(int(param.minimum if param.minimum is not None else -1_000_000),
                          int(param.maximum if param.maximum is not None else 1_000_000))
            spin.setSingleStep(max(1, int(param.step)))
            spin.setSuffix(self._suffix())
            spin.valueChanged.connect(lambda v: self.edited.emit(param.key, int(v)))
            spin.setMinimumWidth(64)
            lay.addWidget(spin, 1)
            self.widgets.append(spin)
        elif kind == "vector":
            for label in ("UV" if param.size == 2 else "XYZW"[:param.size]):
                tag = QLabel(label, self)
                tag.setObjectName("qsDimLabel")
                tag.setFont(_font(12))
                lay.addWidget(tag)
                spin = self._float_spin()
                spin.valueChanged.connect(lambda _v: self._emit_vector())
                lay.addWidget(spin, 1)
                self.widgets.append(spin)
        elif kind == "text":
            edit = QLineEdit(self)
            edit.setFixedHeight(FIELD)
            edit.editingFinished.connect(lambda e=edit: self.edited.emit(param.key, e.text()))
            lay.addWidget(edit, 1)
            self.widgets.append(edit)
        elif kind == "code":
            edit = QPlainTextEdit(self)
            edit.setFont(_font(12, mono=True))
            edit.setMinimumHeight(192)
            edit.setTabStopDistance(32)
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(400)
            self._timer.timeout.connect(self.commit)
            edit.textChanged.connect(self._on_code_changed)
            edit.installEventFilter(self)
            lay.addWidget(edit, 1)
            self.widgets.append(edit)
        else:
            spin = self._float_spin()
            spin.valueChanged.connect(lambda v: self.edited.emit(param.key, float(v)))
            lay.addWidget(spin, 1)
            self.widgets.append(spin)

    def _on_combo(self, combo: QComboBox, i: int) -> None:
        self._value = self._combo_value(combo, i)
        self.edited.emit(self.param.key, self._value)

    def _on_code_changed(self) -> None:
        if self._timer is not None and not self.signalsBlocked():
            self._timer.start()

    def has_pending(self) -> bool:
        return self._timer is not None and self._timer.isActive()

    def flush(self) -> bool:
        if self.has_pending():
            self.commit()
            return True
        return False

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.FocusOut and self.widgets and watched is self.widgets[0]:
            self.flush()
        return False

    def _suffix(self) -> str:
        kind = self.param.kind
        if kind == "distance":
            return " cm"
        if kind == "angle":
            return " deg"
        if kind == "percent":
            return " %"
        return f" {self.param.unit}" if self.param.unit else ""

    def _float_spin(self) -> ScrubSpin:
        p = self.param
        spin = ScrubSpin(self)
        spin.setFixedHeight(FIELD)
        spin.setMinimumWidth(48 if p.kind == "vector" else 64)
        spin.setRange(float(p.minimum) if p.minimum is not None else -1e7,
                      float(p.maximum) if p.maximum is not None else 1e7)
        spin.setSingleStep(p.step)
        if p.kind == "vector":
            spin.setDecimals(3 if p.step < 0.1 else 2)
        else:
            spin.setDecimals(1 if p.kind in ("percent", "angle") else 3 if p.kind == "float" else 2)
            spin.setSuffix(self._suffix())
        return spin

    def _choices(self) -> list[tuple[str, str]]:
        p = self.param
        if p.kind == "choice":
            return p.choice_items()
        if p.kind == "object":
            names = [o.name for o in getattr(self.scene, "objects", ())
                     if o is not self.obj and (not p.ref_type or o.kind == p.ref_type)]
            return [("None", "")] + [(n, n) for n in names]
        if p.kind == "tag_ref":
            names = [t.get("name", "") for _i, t in core.find_tags(self.obj, p.ref_type or None)] \
                if self.obj is not None else []
            return [("All", "")] + [(n, n) for n in names]
        return []

    def _fill_combo(self, combo: QComboBox, value=None) -> None:
        combo.blockSignals(True)
        current = combo.currentData() if value is None else value
        combo.clear()
        for label, data in self._choices():
            combo.addItem(label, data)
        i = combo.findData(current) if current is not None else -1
        if i < 0 and self.param.kind != "choice" and current:
            combo.addItem(f"{current} (missing)", current)
            i = combo.count() - 1
        combo.setCurrentIndex(max(0, i))
        combo.blockSignals(False)

    def refresh_choices(self, value=None) -> None:
        if self.param.kind in ("object", "tag_ref"):
            self._fill_combo(self.widgets[0], self._value if value is None else value)

    def is_missing(self) -> bool:
        if self.param.kind not in ("object", "tag_ref"):
            return False
        w0 = self.widgets[0]
        return w0.count() > 0 and w0.itemText(w0.currentIndex()).endswith(" (missing)")

    @staticmethod
    def _combo_value(combo: QComboBox, i: int):
        v = combo.itemData(i)
        return combo.itemText(i) if v is None else v

    def _emit_vector(self) -> None:
        self.edited.emit(self.param.key, [float(w.value()) for w in self.widgets])

    def commit(self) -> None:
        if self.param.kind == "code":
            if self._timer is not None:
                self._timer.stop()
            self.edited.emit(self.param.key, self.widgets[0].toPlainText())
        elif self.param.kind == "text":
            self.edited.emit(self.param.key, self.widgets[0].text())
        else:
            self.edited.emit(self.param.key, self.value())

    def set_value(self, value) -> None:
        kind = self.param.kind
        for w in self.widgets:
            w.blockSignals(True)
        try:
            w0 = self.widgets[0]
            if kind == "bool":
                w0.setChecked(bool(value))
            elif kind in ("choice", "object", "tag_ref"):
                self._value = value
                self._fill_combo(w0, "" if value is None else value)
            elif kind == "vector":
                vals = list(value) if value is not None else [0.0, 0.0, 0.0]
                for w, v in zip(self.widgets, vals):
                    w.setValue(float(v))
            elif kind == "int":
                w0.setValue(int(value))
            elif kind == "text":
                if w0.text() != str(value or ""):
                    w0.setText(str(value or ""))
            elif kind == "code":
                if w0.toPlainText() != str(value or ""):
                    w0.setPlainText(str(value or ""))
            else:
                w0.setValue(float(value))
        finally:
            for w in self.widgets:
                w.blockSignals(False)

    def value(self):
        kind = self.param.kind
        w0 = self.widgets[0]
        if kind == "bool":
            return w0.isChecked()
        if kind in ("choice", "object", "tag_ref"):
            return self._combo_value(w0, w0.currentIndex()) if w0.count() else ""
        if kind == "vector":
            return [float(w.value()) for w in self.widgets]
        if kind == "int":
            return int(w0.value())
        if kind == "text":
            return w0.text()
        if kind == "code":
            return w0.toPlainText()
        return float(w0.value())


class TagAttributes(QWidget):

    def __init__(self, scene=None, parent: QWidget | None = None, panel: TagsPanel | None = None) -> None:
        super().__init__(parent)
        self.scene = _scene_or_default(scene)
        core.watch_scene(self.scene)
        self.setObjectName("qsTagAttributes")
        self.setMinimumWidth(256)
        self.obj = None
        self.index: int | None = None
        self._type = ""
        self._syncing = False
        self.editors: dict[str, ParamEditor] = {}
        self.rows: dict[str, FieldRow] = {}
        self.action_buttons: dict[str, QPushButton] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget(self)
        head.setFixedHeight(theme.CARD_HEADER_H + theme.SPACE_2)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(theme.SPACE_3, 0, theme.SPACE_2, 0)
        hl.setSpacing(theme.SPACE_2)
        self.chip = TagChip("", head)
        hl.addWidget(self.chip)
        self.title = QLabel("Tag", head)
        self.title.setFont(_header_font())
        self.title.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        hl.addWidget(self.title)
        self.object_label = QLabel("", head)
        self.object_label.setObjectName("qsDimLabel")
        self.object_label.setFont(_font(12))
        hl.addWidget(self.object_label, 1)
        lay.addWidget(head)
        lay.addWidget(_hairline(self))

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self.scroll, 1)

        self.empty_label: QLabel | None = None

        self.name_edit: QLineEdit | None = None
        self.enabled_box: QCheckBox | None = None
        self.summary_label: QLabel | None = None

        self.scene.objectsChanged.connect(self._on_objects)
        self.scene.selectionChanged.connect(self._on_selection)
        _listen(self, self._on_store)
        if panel is not None:
            panel.currentTagChanged.connect(lambda o, i: self.set_tag(o, None if i < 0 else i))
        obj, idx = core.current_tag(self.scene)
        self.set_tag(obj, idx, force=True)

    def sizeHint(self) -> QSize:
        return QSize(320, 448)

    def tag(self) -> dict | None:
        if self.obj is None or self.index is None:
            return None
        return core.tag_at(self.obj, self.index)

    def flush_pending(self) -> int:
        if self.obj is None or self.obj not in self.scene.objects or self.tag() is None:
            for editor in self.editors.values():
                if editor._timer is not None:
                    editor._timer.stop()
            return 0
        count = 0
        for editor in list(self.editors.values()):
            if editor.flush():
                count += 1
        return count

    def set_tag(self, obj, index: int | None, force: bool = False) -> None:
        if obj is not self.obj or index != self.index or force:
            self.flush_pending()
        if obj is not None and obj not in self.scene.objects:
            obj, index = None, None
        tag = core.tag_at(obj, index) if obj is not None and index is not None else None
        if tag is None:
            index = None
        new_type = tag.get("type", "") if tag else ""
        if not force and obj is self.obj and index == self.index and new_type == self._type:
            self.sync_values()
            return
        self.obj, self.index, self._type = obj, index, new_type
        self._build()

    def _build(self) -> None:
        for editor in self.editors.values():
            if editor._timer is not None:
                editor._timer.stop()
        self.editors.clear()
        self.rows.clear()
        self.action_buttons.clear()
        self.name_edit = None
        self.enabled_box = None
        self.summary_label = None
        self.empty_label = None
        tag = self.tag()
        self.object_label.setText(self.obj.name if self.obj is not None else "")
        self.chip.set_type(self._type)
        self.chip.setVisible(tag is not None)
        if tag is None:
            self.title.setText("Tag")
            body = QWidget()
            bl = QVBoxLayout(body)
            self.empty_label = QLabel("Select a tag to edit it" if self.obj is not None
                                      else "No object selected", body)
            self.empty_label.setObjectName("qsDimLabel")
            self.empty_label.setFont(_font(12))
            self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(self.empty_label)
            bl.addStretch(1)
            self.scroll.setWidget(body)
            return
        spec = get_tag_spec(self._type) if has_tag_spec(self._type) else None
        self.title.setText(spec.label if spec else self._type or "Tag")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, theme.SPACE_1, 0, theme.SPACE_2)
        bl.setSpacing(theme.SPACE_1)

        basic = CollapsibleGroup("Basic", body)
        basic.content_layout().setSpacing(theme.SPACE_1)
        self.name_edit = QLineEdit(tag.get("name", ""))
        self.name_edit.setFixedHeight(FIELD)
        self.name_edit.editingFinished.connect(self._on_name)
        basic.add_widget(FieldRow("Name", self.name_edit, label_width=LABEL_W, indent=INDENT))
        self.enabled_box = QCheckBox()
        self.enabled_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.enabled_box.setChecked(bool(tag.get("enabled", True)))
        self.enabled_box.toggled.connect(self._on_enabled)
        row = FieldRow("Enabled", None, label_width=LABEL_W, indent=INDENT)
        row.add_widget(self.enabled_box)
        row.add_stretch(1)
        basic.add_widget(row)
        self.summary_label = QLabel(core.tag_summary(self.obj, self.index))
        self.summary_label.setObjectName("qsDimLabel")
        self.summary_label.setFont(_font(12))
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        srow = FieldRow("Info", self.summary_label, label_width=LABEL_W, indent=INDENT)
        srow.setVisible(spec is not None and spec.summary is not None)
        basic.add_widget(srow)
        if spec is not None and spec.description:
            basic.setToolTip(spec.description)
        bl.addWidget(basic)

        if spec is not None:
            groups: dict[str, CollapsibleGroup] = {}
            for p in spec.params:
                if not p.visible:
                    continue
                group = groups.get(p.group)
                if group is None:
                    group = CollapsibleGroup(p.group, body)
                    group.content_layout().setSpacing(theme.SPACE_1)
                    groups[p.group] = group
                    bl.addWidget(group)
                editor = ParamEditor(p, self.scene, self.obj)
                editor.set_value(tag.get(p.key, p.initial()))
                editor.edited.connect(self._on_edited)
                if p.kind == "code":
                    group.add_widget(editor)
                    row = None
                else:
                    label = f"{p.label} ({p.unit})" if p.kind == "vector" and p.unit else p.label
                    row = FieldRow(label, editor, label_width=LABEL_W, indent=INDENT)
                    row.setToolTip(p.tooltip or p.label)
                    group.add_widget(row)
                self.editors[p.key] = editor
                if row is not None:
                    self.rows[p.key] = row
            if spec.actions:
                group = CollapsibleGroup("Actions", body)
                holder = QWidget(group)
                grid = QGridLayout(holder)
                grid.setContentsMargins(INDENT, 0, theme.SPACE_2, 0)
                grid.setHorizontalSpacing(theme.SPACE_2)
                grid.setVerticalSpacing(theme.SPACE_1)
                for i, a in enumerate(spec.actions):
                    b = QPushButton(a.label, holder)
                    b.setFixedHeight(FIELD)
                    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                    b.clicked.connect(lambda _c=False, key=a.key: self.run_action(key))
                    grid.addWidget(b, i // 2, i % 2)
                    self.action_buttons[a.key] = b
                group.add_widget(holder)
                bl.addWidget(group)
        bl.addStretch(1)
        self.scroll.setWidget(body)

    def sync_values(self) -> None:
        tag = self.tag()
        if tag is None:
            return
        self._syncing = True
        try:
            if self.name_edit is not None and not self.name_edit.hasFocus():
                self.name_edit.setText(tag.get("name", ""))
            if self.enabled_box is not None:
                self.enabled_box.blockSignals(True)
                self.enabled_box.setChecked(bool(tag.get("enabled", True)))
                self.enabled_box.blockSignals(False)
            if self.summary_label is not None:
                self.summary_label.setText(core.tag_summary(self.obj, self.index))
            spec = get_tag_spec(self._type) if has_tag_spec(self._type) else None
            for key, editor in self.editors.items():
                p = spec.param(key) if spec else None
                if p is not None and p.kind == "code" and editor.widgets[0].hasFocus():
                    continue
                editor.set_value(tag.get(key, p.initial() if p else None))
        finally:
            self._syncing = False

    def _on_name(self) -> None:
        if self.name_edit is None or self.tag() is None:
            return
        name = core.rename_tag(self.obj, self.index, self.name_edit.text())
        self.name_edit.setText(name)

    def _on_enabled(self, flag: bool) -> None:
        if self.tag() is not None:
            core.set_tag_enabled(self.obj, self.index, flag)

    def _on_edited(self, key: str, value) -> None:
        if self._syncing or self.tag() is None:
            return
        spec = get_tag_spec(self._type) if has_tag_spec(self._type) else None
        p = spec.param(key) if spec is not None else None
        coalesce = (self.index, key) if p is not None and p.kind in COALESCE_KINDS else None
        self._syncing = True
        try:
            core.update_tag(self.obj, self.index, _coalesce=coalesce, **{key: value})
        finally:
            self._syncing = False
        self.sync_values()
        self.scene.changed.emit()

    def run_action(self, key: str):
        if self.tag() is None:
            return None
        result = core.run_action(self.scene, self.obj, self.index, key)
        self.sync_values()
        self.scene.changed.emit()
        return result

    def _relink(self):
        obj, idx = core.current_tag(self.scene)
        if obj is not None:
            return obj, idx
        old = self.obj
        if old is None:
            return None, None
        match = core.find_object(self.scene, getattr(old, "name", ""))
        if match is None:
            active = self.scene.active
            return (active, None) if active in self.scene.objects else (None, None)
        return match, self.index

    def _on_objects(self) -> None:
        core.watch_scene(self.scene)
        core.sync_renames(self.scene)
        if self.obj is not None and self.obj not in self.scene.objects:
            obj, idx = self._relink()
            self.set_tag(obj, idx, force=True)
            return
        tag = self.tag()
        for key, editor in self.editors.items():
            editor.refresh_choices(tag.get(key) if tag is not None else None)
        self.object_label.setText(self.obj.name if self.obj is not None else "")

    def _on_selection(self) -> None:
        if self.obj is not None and self.scene.active is not self.obj:
            obj, idx = core.current_tag(self.scene)
            if obj is not self.obj:
                self.set_tag(obj, idx)

    def _on_store(self, owner, key) -> None:
        if key == core.CURRENT_KEY and owner is self.scene:
            obj, idx = core.current_tag(self.scene)
            self.set_tag(obj, idx)
        elif key == core.TAGS_KEY and owner is self.obj and owner is not None:
            if self._syncing:
                return
            tag = self.tag()
            if tag is None or tag.get("type", "") != self._type:
                obj, idx = core.current_tag(self.scene)
                if obj is self.obj:
                    self.set_tag(obj, idx, force=True)
                else:
                    self.set_tag(self.obj, None, force=True)
            else:
                for editor in self.editors.values():
                    editor.refresh_choices()
                self.sync_values()
