from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QTextCursor
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget)

from ..scene import get_scene
from . import examples
from .console import BUTTON_H, panel_qss
from .editor import CodeEditor, FindBar
from .highlight import mono_font
from .library import SCRIPT_TEMPLATE, ScriptLibrary, sanitize_name
from .runner import ExecResult
from .shortcuts import ShortcutBinder, get_binder

__all__ = ["CodeEditor", "FindBar", "ScriptManager", "ShortcutBinder", "MAX_TIME_LIMIT"]

LIST_MIN_W = 192
MAX_TIME_LIMIT = 3600


class ScriptManager(QWidget):

    scriptRun = Signal(str, object)

    def __init__(self, scene=None, parent: QWidget | None = None, library: ScriptLibrary | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self.library = library or ScriptLibrary()
        self.setObjectName("qsScriptManager")
        self.setStyleSheet(panel_qss())
        self.current: str | None = None
        self.buffers: dict[str, str] = {}
        self.last_result: ExecResult | None = None
        self._loading = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.new_button = QPushButton("New", self)
        self.open_button = QPushButton("Open", self)
        self.save_button = QPushButton("Save", self)
        self.run_button = QPushButton("Run", self)
        self.delete_button = QPushButton("Delete", self)
        self.examples_button = QPushButton("Install Examples", self)
        for b in (self.new_button, self.open_button, self.save_button, self.run_button,
                  self.delete_button, self.examples_button):
            b.setFixedHeight(BUTTON_H)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            bar.addWidget(b)
        bar.addStretch(1)
        limit_label = QLabel("Time Limit", self)
        limit_label.setObjectName("qsDimLabel")
        bar.addWidget(limit_label)
        self.timeout_spin = QSpinBox(self)
        self.timeout_spin.setRange(0, MAX_TIME_LIMIT)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setSpecialValueText("None")
        self.timeout_spin.setFixedHeight(BUTTON_H)
        self.timeout_spin.setToolTip("Stop a script that runs longer than this; None never stops it")
        current_limit = self.library.timeout()
        self.timeout_spin.setValue(0 if current_limit is None else int(round(current_limit)))
        bar.addWidget(self.timeout_spin)
        lay.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.setChildrenCollapsible(False)
        self.list = QListWidget(split)
        self.list.setMinimumWidth(LIST_MIN_W)
        right = QWidget(split)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        name_label = QLabel("Name", right)
        name_label.setObjectName("qsDimLabel")
        meta.addWidget(name_label)
        self.name_edit = QLineEdit(right)
        self.name_edit.setFixedHeight(BUTTON_H)
        meta.addWidget(self.name_edit, 1)
        key_label = QLabel("Shortcut", right)
        key_label.setObjectName("qsDimLabel")
        meta.addWidget(key_label)
        self.shortcut_edit = QKeySequenceEdit(right)
        self.shortcut_edit.setFixedHeight(BUTTON_H)
        meta.addWidget(self.shortcut_edit, 1)
        self.clear_shortcut_button = QPushButton("Clear Shortcut", right)
        self.clear_shortcut_button.setFixedHeight(BUTTON_H)
        self.clear_shortcut_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        meta.addWidget(self.clear_shortcut_button)
        rl.addLayout(meta)

        vsplit = QSplitter(Qt.Orientation.Vertical, right)
        vsplit.setChildrenCollapsible(False)
        top = QWidget(vsplit)
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        self.editor = CodeEditor(top)
        tl.addWidget(self.editor, 1)
        self.find_bar = FindBar(self.editor, top)
        self.find_bar.hide()
        tl.addWidget(self.find_bar)
        self.output = QPlainTextEdit(vsplit)
        self.output.setReadOnly(True)
        self.output.setFont(mono_font())
        self.output.setPlaceholderText("Script output")
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 1)
        rl.addWidget(vsplit, 1)

        self.status = QLabel("", right)
        self.status.setObjectName("qsScriptStatus")
        rl.addWidget(self.status)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

        self.binder = get_binder()
        self.binder.attach(self.library)
        self.binder.triggered.connect(self._on_triggered)

        self.new_button.clicked.connect(lambda: self.new_script())
        self.open_button.clicked.connect(self._open_dialog)
        self.save_button.clicked.connect(self.save)
        self.run_button.clicked.connect(self.run)
        self.delete_button.clicked.connect(lambda: self.delete_current(confirm=True))
        self.examples_button.clicked.connect(self.install_examples)
        self.clear_shortcut_button.clicked.connect(self.clear_shortcut)
        self.list.currentItemChanged.connect(self._on_current)
        self.editor.textChanged.connect(self._on_text)
        self.editor.cursorPositionChanged.connect(self._update_status)
        self.editor.runRequested.connect(self.run)
        self.editor.saveRequested.connect(self.save)
        self.editor.findRequested.connect(self.find_bar.open)
        self.timeout_spin.valueChanged.connect(self._on_timeout)
        self.name_edit.editingFinished.connect(self._on_name)
        self.shortcut_edit.editingFinished.connect(self._on_shortcut)

        self.refresh()
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._set_editor_enabled(False)

    def _set_editor_enabled(self, on: bool) -> None:
        for w in (self.editor, self.name_edit, self.shortcut_edit, self.save_button, self.run_button,
                  self.delete_button, self.clear_shortcut_button):
            w.setEnabled(on)

    def is_dirty(self, name: str | None = None) -> bool:
        name = name or self.current
        if name is None or name not in self.buffers:
            return False
        try:
            return self.buffers[name] != self.library.load(name)
        except OSError:
            return True

    def refresh(self) -> list[str]:
        names = self.library.list()
        keep = self.current
        self.list.blockSignals(True)
        self.list.clear()
        shortcuts = self.library.shortcuts()
        for name in names:
            label = name[:-3]
            if self.is_dirty(name):
                label += " *"
            if name in shortcuts:
                label += f"    {shortcuts[name]}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(str(self.library.path(name)))
            self.list.addItem(item)
        self.list.blockSignals(False)
        if keep in names:
            self._select_row(names.index(keep), load=False)
        elif keep is not None:
            self.current = None
            self._show(None)
        self.binder.rebuild()
        return names

    def _select_row(self, row: int, load: bool = True) -> None:
        self.list.blockSignals(True)
        self.list.setCurrentRow(row)
        self.list.blockSignals(False)
        if load:
            item = self.list.item(row)
            self._show(item.data(Qt.ItemDataRole.UserRole) if item else None)

    def names(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def select(self, name: str) -> bool:
        name = sanitize_name(name)
        names = self.names()
        if name not in names:
            return False
        self._select_row(names.index(name))
        return True

    def _on_current(self, item, _prev) -> None:
        self._show(item.data(Qt.ItemDataRole.UserRole) if item is not None else None)

    def _show(self, name: str | None) -> None:
        self.current = name
        self._loading = True
        try:
            if name is None:
                self.editor.setPlainText("")
                self.name_edit.setText("")
                self.shortcut_edit.clear()
                self._set_editor_enabled(False)
                return
            self._set_editor_enabled(True)
            text = self.buffers.get(name)
            if text is None:
                try:
                    text = self.library.load(name)
                except OSError as exc:
                    text = ""
                    self.status.setText(f"Cannot read {name}: {exc}")
            self.editor.setPlainText(text)
            self.name_edit.setText(name[:-3])
            self.shortcut_edit.setKeySequence(QKeySequence(self.library.shortcut(name)))
        finally:
            self._loading = False
        self._update_status()

    def _on_text(self) -> None:
        if self._loading or self.current is None:
            return
        was = self.is_dirty()
        self.buffers[self.current] = self.editor.toPlainText()
        if was != self.is_dirty():
            self._relabel()

    def _relabel(self) -> None:
        shortcuts = self.library.shortcuts()
        for i in range(self.list.count()):
            item = self.list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            label = name[:-3] + (" *" if self.is_dirty(name) else "")
            if name in shortcuts:
                label += f"    {shortcuts[name]}"
            item.setText(label)

    def _update_status(self) -> None:
        if self.current is None:
            self.status.setText("No script")
            return
        c = self.editor.textCursor()
        state = "modified" if self.is_dirty() else "saved"
        self.status.setText(f"{self.current}  |  line {c.blockNumber() + 1}, column "
                            f"{c.positionInBlock() + 1}  |  {state}")

    def new_script(self, base: str = "Untitled", text: str = SCRIPT_TEMPLATE) -> str:
        name = self.library.create(base, text)
        self.refresh()
        self.select(name)
        self.status.setText(f"Created {name}")
        return name

    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Script", str(self.library.folder),
                                              "Python scripts (*.py)")
        if path:
            self.open_file(path)

    def open_file(self, path: str | Path) -> str:
        name = self.library.import_file(path)
        self.buffers.pop(name, None)
        self.refresh()
        self.select(name)
        self.status.setText(f"Opened {name}")
        return name

    def save(self) -> bool:
        if self.current is None:
            return False
        text = self.editor.toPlainText()
        self.library.save(self.current, text)
        self.buffers.pop(self.current, None)
        self._relabel()
        self._update_status()
        self.status.setText(f"Saved {self.current}")
        return True

    def run(self) -> ExecResult | None:
        if self.current is None:
            return None
        return self.run_script(self.current, self.editor.toPlainText())

    def run_script(self, name: str, text: str | None = None) -> ExecResult:
        if text is None:
            text = self.buffers.get(name)
        result = self.library.run(name, self.scene, text=text)
        self._show_result(name, result)
        return result

    def _show_result(self, name: str, result: ExecResult) -> None:
        self.output.setPlainText(result.output)
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.status.setText(result.summary())
        self.last_result = result
        self.scriptRun.emit(name, result)

    def _on_triggered(self, name: str, result: ExecResult) -> None:
        try:
            if name in self.names():
                self._show_result(name, result)
        except RuntimeError:
            pass

    def run_shortcut(self, keys: str) -> ExecResult | None:
        return self.binder.activate(keys)

    def delete_current(self, confirm: bool = True) -> bool:
        if self.current is None:
            return False
        if confirm:
            answer = QMessageBox.question(self, "Delete Script",
                                          f"Delete {self.current} from the scripts folder?")
            if answer != QMessageBox.StandardButton.Yes:
                return False
        name = self.current
        self.library.delete(name)
        self.buffers.pop(name, None)
        self.current = None
        names = self.refresh()
        if names:
            self._select_row(0)
        else:
            self._show(None)
        self.status.setText(f"Deleted {name}")
        return True

    def rename_current(self, new: str) -> str | None:
        if self.current is None:
            return None
        new_name = sanitize_name(new)
        if new_name == self.current:
            return self.current
        try:
            final = self.library.rename(self.current, new_name)
        except (FileExistsError, FileNotFoundError, ValueError) as exc:
            self.status.setText(f"Cannot rename: {exc}")
            self.name_edit.setText(self.current[:-3])
            return None
        if self.current in self.buffers:
            self.buffers[final] = self.buffers.pop(self.current)
        self.current = final
        self.refresh()
        self.select(final)
        return final

    def _on_name(self) -> None:
        text = self.name_edit.text().strip()
        if self.current is not None and text:
            try:
                self.rename_current(text)
            except ValueError:
                self.name_edit.setText(self.current[:-3])

    def set_shortcut(self, keys: str) -> str:
        if self.current is None:
            return ""
        seq = QKeySequence(keys)
        text = seq.toString(QKeySequence.SequenceFormat.PortableText)
        self.library.set_shortcut(self.current, text or None)
        self._loading = True
        try:
            self.shortcut_edit.setKeySequence(seq)
        finally:
            self._loading = False
        self.binder.rebuild()
        self._relabel()
        self.status.setText(f"Shortcut for {self.current}: {text or 'none'}")
        return text

    def _on_shortcut(self) -> None:
        if self._loading:
            return
        seq = self.shortcut_edit.keySequence()
        self.set_shortcut(seq.toString(QKeySequence.SequenceFormat.PortableText))

    def clear_shortcut(self) -> None:
        self.shortcut_edit.clear()
        self.set_shortcut("")

    def set_time_limit(self, seconds: float | None) -> float:
        value = self.library.set_timeout(seconds)
        self.timeout_spin.blockSignals(True)
        self.timeout_spin.setValue(int(round(value)))
        self.timeout_spin.blockSignals(False)
        self.status.setText(f"Time limit: {int(round(value))} s" if value > 0 else "Time limit: none")
        return value

    def _on_timeout(self, value: int) -> None:
        self.set_time_limit(float(value))

    def install_examples(self) -> list:
        written = examples.install_examples()
        self.refresh()
        if self.current is None and self.list.count():
            self._select_row(0)
        self.status.setText(f"Installed {len(written)} example files")
        return written
