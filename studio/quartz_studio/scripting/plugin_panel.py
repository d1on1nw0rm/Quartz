from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget)

from .. import theme
from ..scene import get_scene
from . import api, examples
from .console import BUTTON_H, panel_qss
from .highlight import mono_font
from .plugins import PluginLoader, PluginRecord, get_loader

__all__ = ["PluginManager", "describe"]

LIST_MIN_W = 192


def describe(record: PluginRecord) -> str:
    lines = [record.title]
    meta = ", ".join(p for p in (record.type or "unknown type",
                                  f"version {record.version}" if record.version else "",
                                  f"by {record.author}" if record.author else "") if p)
    lines.append(meta)
    lines.append(f"File: {record.path}")
    lines.append("State: " + ("enabled" if record.enabled else "disabled")
                 + (", loaded" if record.loaded else ""))
    if record.description:
        lines += ["", record.description]
    if record.commands:
        lines += ["", "Commands:"] + ["  " + " > ".join(p) for p, _f, _k in record.commands]
    if record.objects:
        lines += ["", "Objects: " + ", ".join(record.objects)]
    if record.tools:
        lines += ["", "Tools: " + ", ".join(record.tools)]
    if record.tags:
        lines += ["", "Tags: " + ", ".join(record.tags)]
    if record.error:
        lines += ["", "Error:", record.error.rstrip()]
    return "\n".join(lines) + "\n"


class PluginManager(QWidget):

    pluginsChanged = Signal()

    def __init__(self, scene=None, parent: QWidget | None = None, loader: PluginLoader | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self.loader = loader or get_loader()
        self.setObjectName("qsPluginManager")
        self.setStyleSheet(panel_qss())
        self._filling = False
        self.opened_urls: list[str] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.reload_button = QPushButton("Reload All", self)
        self.reload_one_button = QPushButton("Reload Selected", self)
        self.folder_button = QPushButton("Open Folder", self)
        self.examples_button = QPushButton("Install Examples", self)
        for b in (self.reload_button, self.reload_one_button, self.folder_button, self.examples_button):
            b.setFixedHeight(BUTTON_H)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.setChildrenCollapsible(False)
        self.list = QListWidget(split)
        self.list.setMinimumWidth(LIST_MIN_W)
        right = QWidget(split)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self.details = QPlainTextEdit(right)
        self.details.setReadOnly(True)
        self.details.setFont(mono_font())
        rl.addWidget(self.details, 1)
        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(8)
        self.command_combo = QComboBox(right)
        self.command_combo.setFixedHeight(BUTTON_H)
        cmd_row.addWidget(self.command_combo, 1)
        self.run_command_button = QPushButton("Run Command", right)
        self.run_command_button.setFixedHeight(BUTTON_H)
        self.run_command_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cmd_row.addWidget(self.run_command_button)
        rl.addLayout(cmd_row)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        self.status = QLabel("", self)
        self.status.setObjectName("qsScriptStatus")
        lay.addWidget(self.status)

        self.reload_button.clicked.connect(self.reload)
        self.reload_one_button.clicked.connect(self.reload_selected)
        self.folder_button.clicked.connect(lambda: self.open_folder())
        self.examples_button.clicked.connect(self.install_examples)
        self.run_command_button.clicked.connect(self.run_selected_command)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.currentItemChanged.connect(lambda *_a: self._show_current())
        self.loader.add_listener(self.refresh)
        self.destroyed.connect(lambda *_a, ld=self.loader, fn=self.refresh: ld.remove_listener(fn))

        self.loader.ensure_loaded()
        self.refresh()

    def refresh(self) -> None:
        keep = self.current_stem()
        self._filling = True
        try:
            self.list.clear()
            for stem, record in self.loader.records.items():
                label = record.title
                if record.type:
                    label += f"  ({record.type})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, stem)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if record.enabled else Qt.CheckState.Unchecked)
                item.setToolTip(str(record.path))
                if record.error:
                    item.setForeground(QColor(theme.STATUS_ERROR))
                elif not record.enabled:
                    item.setForeground(QColor(theme.TEXT_MUTED))
                self.list.addItem(item)
        finally:
            self._filling = False
        stems = self.stems()
        if keep in stems:
            self.list.setCurrentRow(stems.index(keep))
        elif stems:
            self.list.setCurrentRow(0)
        self._show_current()
        errors = len(self.loader.errors())
        self.status.setText(f"{len(stems)} plugins in {self.loader.folder}"
                            + (f", {errors} with errors" if errors else ""))
        self.pluginsChanged.emit()

    def stems(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def current_stem(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def current_record(self) -> PluginRecord | None:
        stem = self.current_stem()
        return self.loader.get(stem) if stem else None

    def _show_current(self) -> None:
        record = self.current_record()
        self.command_combo.clear()
        if record is None:
            self.details.setPlainText("No plugins. Put .py files with a PLUGIN dictionary and a "
                                      f"register(api) function in\n{self.loader.folder}\n")
            self.run_command_button.setEnabled(False)
            self.reload_one_button.setEnabled(False)
            return
        self.details.setPlainText(describe(record))
        for path, _fn, _keys in record.commands:
            self.command_combo.addItem(" > ".join(path[1:]), "/".join(path))
        self.run_command_button.setEnabled(self.command_combo.count() > 0 and record.loaded)
        self.reload_one_button.setEnabled(record.enabled)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._filling:
            return
        stem = item.data(Qt.ItemDataRole.UserRole)
        self.set_enabled(stem, item.checkState() == Qt.CheckState.Checked)

    def set_enabled(self, stem: str, enabled: bool) -> bool:
        ok = self.loader.set_enabled(stem, enabled)
        record = self.loader.get(stem)
        word = "Enabled" if enabled else "Disabled"
        self.status.setText(f"{word} {record.title if record else stem}" + ("" if ok else " with errors"))
        return ok

    def reload(self) -> None:
        self.loader.reload()
        api.message(f"Reloaded {len(self.loader.records)} plugins")

    def reload_selected(self) -> bool:
        stem = self.current_stem()
        if stem is None:
            return False
        ok = self.loader.reload_one(stem)
        self.status.setText(f"Reloaded {stem}" + ("" if ok else " with errors"))
        return ok

    def run_selected_command(self):
        key = self.command_combo.currentData()
        if not key:
            return None
        with api.bind_scene(self.scene):
            value = self.loader.run_command(key)
        self.status.setText(f"Ran {self.command_combo.currentText()}")
        self._show_current()
        return value

    def open_folder(self, launch: bool = True) -> str:
        folder = str(self.loader.folder)
        url = QUrl.fromLocalFile(folder)
        self.opened_urls.append(url.toString())
        if launch:
            QDesktopServices.openUrl(url)
        return folder

    def install_examples(self) -> list:
        written = examples.install_examples()
        self.loader.reload()
        self.status.setText(f"Installed {len(written)} example files")
        return written
