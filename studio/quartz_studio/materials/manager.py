from __future__ import annotations

import os

from PySide6.QtCore import QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..scene import get_scene
from ..widgets.common import prepare_popup
from . import model
from .convert import convert_to_nodes
from .hub import hub, watch_scene
from .preview import thumbnail
from .tags import assign_to_selected, objects_using, remove_from_selected
from .textures import new_texture
from .ui_common import FIELD_H, style_surface

__all__ = ["MaterialManager", "MaterialList", "MATERIAL_MIME", "IMAGE_SUFFIXES", "LIBRARY_FILTER",
           "material_from_image"]

MATERIAL_MIME = "application/x-quartz-material"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".webp")
LIBRARY_FILTER = "Quartz Materials (*.qmat.json *.json);;All Files (*)"
THUMB = 64
GRID_W = 96
GRID_H = 112


def material_from_image(scene, path: str) -> dict:
    mat = model.new_material("pbr", os.path.splitext(os.path.basename(path))[0] or "Image")
    model.set_channel_texture(mat, "base_color", new_texture("image", path=path))
    return model.add_material(scene, mat)


class MaterialList(QListWidget):

    filesDropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setGridSize(QSize(GRID_W, GRID_H))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def mimeTypes(self) -> list:
        return [MATERIAL_MIME, "text/plain", "text/uri-list"]

    def mimeData(self, items) -> QMimeData:
        data = QMimeData()
        ids = [it.data(Qt.ItemDataRole.UserRole) for it in items]
        data.setData(MATERIAL_MIME, "\n".join(ids).encode("utf-8"))
        data.setText("\n".join(f"material:{i}" for i in ids))
        return data

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            self.filesDropped.emit(paths)
            e.acceptProposedAction()
            return
        e.ignore()


class MaterialManager(QWidget):

    materialActivated = Signal(str)

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self._block = False
        style_surface(self, "qsMaterialManager")
        self._build()
        hub().changed.connect(self._on_store)
        self._scene_timer = watch_scene(self, self.scene, self.refresh)
        selection_changed = getattr(self.scene, "selectionChanged", None)
        if selection_changed is not None:
            selection_changed.connect(self._sync_buttons)
        self.refresh()

    def _button(self, text: str, tip: str = "") -> QPushButton:
        b = QPushButton(text, self)
        b.setFixedHeight(FIELD_H)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tip:
            b.setToolTip(tip)
        return b

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.create_button = self._button("Create", "Create a new material")
        self.create_menu = self._make_create_menu()
        self.create_button.setMenu(self.create_menu)
        self.edit_button = self._button("Edit", "Edit the selected materials")
        self.edit_menu = self._make_edit_menu()
        self.edit_button.setMenu(self.edit_menu)
        self.apply_button = self._button("Apply to Selected", "Assign the active material to the selected objects")
        self.apply_button.clicked.connect(self.apply_to_selected)
        self.remove_button = self._button("Remove", "Remove material tags from the selected objects")
        self.remove_button.clicked.connect(self.remove_from_selected)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Filter")
        self.search.setFixedHeight(FIELD_H)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        bar.addWidget(self.create_button)
        bar.addWidget(self.edit_button)
        bar.addWidget(self.apply_button)
        bar.addWidget(self.remove_button)
        bar.addStretch(1)
        bar.addWidget(self.search)
        lay.addLayout(bar)
        self.list = MaterialList(self)
        self.list.itemSelectionChanged.connect(self._selection_changed)
        self.list.itemDoubleClicked.connect(self._double_clicked)
        self.list.itemChanged.connect(self._item_renamed)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.filesDropped.connect(self.import_files)
        lay.addWidget(self.list, 1)
        self.status = QLabel("", self)
        self.status.setObjectName("qsDimLabel")
        lay.addWidget(self.status)
        for text, keys, slot in (("Delete", QKeySequence.StandardKey.Delete, self.delete_selected),
                                 ("Rename", QKeySequence(Qt.Key.Key_F2), self.rename_current),
                                 ("Duplicate", QKeySequence("Ctrl+D"), self.duplicate_selected)):
            act = QAction(text, self.list)
            act.setShortcut(keys)
            act.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
            act.triggered.connect(slot)
            self.list.addAction(act)

    def _make_create_menu(self) -> QMenu:
        menu = prepare_popup(QMenu(self))
        menu.addAction("New PBR Material", lambda: self.create("pbr"))
        menu.addAction("New Node Material", lambda: self.create("node"))
        presets = prepare_popup(menu.addMenu("Presets"))
        for key, spec in model.PRESETS.items():
            presets.addAction(spec["name"], lambda k=key: self.create(preset=k))
        menu.addSeparator()
        menu.addAction("Material From Image...", self._image_dialog)
        menu.addAction("Load Library...", self._load_dialog)
        return menu

    def _make_edit_menu(self) -> QMenu:
        menu = prepare_popup(QMenu(self))
        self.act_rename = menu.addAction("Rename", self.rename_current)
        self.act_duplicate = menu.addAction("Duplicate", self.duplicate_selected)
        self.act_delete = menu.addAction("Delete", self.delete_selected)
        self.act_convert = menu.addAction("Convert to Nodes", self.convert_selected)
        menu.addSeparator()
        self.act_select_objects = menu.addAction("Select Object Using", self.select_user)
        self.act_delete_unused = menu.addAction("Delete Unused", self.delete_unused)
        menu.addSeparator()
        self.act_save = menu.addAction("Save Library...", self._save_dialog)
        return menu

    def item_for(self, mid: str) -> QListWidgetItem | None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == mid:
                return item
        return None

    def selected_ids(self) -> list:
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.list.selectedItems()]

    def current_id(self) -> str | None:
        return model.active_material_id(self.scene)

    def _tooltip(self, mat: dict) -> str:
        users = objects_using(self.scene, mat["id"])
        kind = "Node material" if mat.get("type") == "node" else "PBR material"
        names = ", ".join(o.name for o in users[:4]) + (" ..." if len(users) > 4 else "")
        return f"{mat.get('name')}\n{kind}\nUsed by {len(users)} object(s)" + (f": {names}" if users else "")

    def refresh(self) -> None:
        self._block = True
        try:
            mats = model.materials(self.scene)
            active = model.active_material_id(self.scene)
            existing = {self.list.item(i).data(Qt.ItemDataRole.UserRole): self.list.item(i)
                        for i in range(self.list.count())}
            wanted = [m["id"] for m in mats]
            if list(existing) != wanted:
                self.list.clear()
                for mat in mats:
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.UserRole, mat["id"])
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                    self.list.addItem(item)
            for mat in mats:
                item = self.item_for(mat["id"])
                if item.text() != mat.get("name", ""):
                    item.setText(mat.get("name", ""))
                img = thumbnail(mat, THUMB)
                key = img.cacheKey()
                if item.data(Qt.ItemDataRole.UserRole + 1) != key:
                    item.setIcon(QIcon(QPixmap.fromImage(img)))
                    item.setData(Qt.ItemDataRole.UserRole + 1, key)
                item.setToolTip(self._tooltip(mat))
            selected = set(self.selected_ids())
            if active is not None and active not in selected:
                self.list.clearSelection()
                item = self.item_for(active)
                if item is not None:
                    item.setSelected(True)
                    self.list.setCurrentItem(item)
            self._apply_filter(self.search.text())
            self.status.setText(f"{len(mats)} material(s)")
        finally:
            self._block = False
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has_active = model.active_material_id(self.scene) is not None
        selected = list(getattr(self.scene, "selected_objects", lambda: [])())
        self.apply_button.setEnabled(has_active and bool(selected))
        self.remove_button.setEnabled(bool(selected))
        has_sel = bool(self.list.selectedItems())
        for act in (self.act_rename, self.act_duplicate, self.act_delete, self.act_convert, self.act_select_objects):
            act.setEnabled(has_sel)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _selection_changed(self) -> None:
        if self._block:
            return
        current = self.list.currentItem()
        ids = self.selected_ids()
        if current is not None and current.isSelected():
            mid = current.data(Qt.ItemDataRole.UserRole)
        elif ids:
            mid = ids[-1]
        else:
            mid = None
        if mid is not None and mid != model.active_material_id(self.scene):
            model.set_active_material(self.scene, mid)
        self._sync_buttons()

    def select(self, mid: str) -> None:
        item = self.item_for(mid)
        if item is None:
            return
        self.list.clearSelection()
        item.setSelected(True)
        self.list.setCurrentItem(item)

    def _double_clicked(self, item: QListWidgetItem) -> None:
        mid = item.data(Qt.ItemDataRole.UserRole)
        model.set_active_material(self.scene, mid)
        self.materialActivated.emit(mid)

    def _item_renamed(self, item: QListWidgetItem) -> None:
        if self._block:
            return
        mid = item.data(Qt.ItemDataRole.UserRole)
        mat = model.find_material(self.scene, mid)
        if mat is not None and item.text() != mat.get("name"):
            model.rename_material(self.scene, mid, item.text())

    def _on_store(self, owner, key: str) -> None:
        if owner is self.scene and key in (model.LIBRARY_KEY, model.ACTIVE_KEY):
            self.refresh()
        elif key == "tags" and owner in getattr(self.scene, "objects", []):
            self.refresh()

    def create(self, kind: str = "pbr", preset: str | None = None) -> dict:
        mat = model.create_material(self.scene, kind, preset=preset)
        self.select(mat["id"])
        return mat

    def rename_current(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.list.editItem(item)

    def rename(self, mid: str, name: str) -> str:
        return model.rename_material(self.scene, mid, name)

    def duplicate_selected(self) -> list:
        with model.undo_group(self.scene):
            made = [model.duplicate_material(self.scene, mid) for mid in self.selected_ids()]
        if made:
            self.select(made[-1]["id"])
        return made

    def delete_selected(self) -> int:
        ids = self.selected_ids()
        with model.undo_group(self.scene):
            for mid in ids:
                model.delete_material(self.scene, mid)
        return len(ids)

    def convert_selected(self) -> int:
        count = 0
        with model.undo_group(self.scene):
            for mid in self.selected_ids():
                mat = model.find_material(self.scene, mid)
                if mat is not None and mat.get("type") != "node":
                    convert_to_nodes(self.scene, mid)
                    count += 1
        return count

    def delete_unused(self) -> int:
        return model.delete_unused(self.scene)

    def select_user(self) -> object:
        ids = self.selected_ids()
        if not ids:
            return None
        users = objects_using(self.scene, ids[0])
        if not users:
            self.status.setText("Material is not used by any object")
            return None
        set_active = getattr(self.scene, "set_active", None)
        if callable(set_active):
            set_active(users[0])
        return users[0]

    def apply_to_selected(self) -> int:
        count = assign_to_selected(self.scene)
        self.status.setText(f"Applied to {count} object(s)" if count else "Select an object first")
        return count

    def remove_from_selected(self) -> int:
        count = remove_from_selected(self.scene)
        self.status.setText(f"Removed {count} material tag(s)")
        return count

    def import_files(self, paths: list) -> list:
        made = []
        with model.undo_group(self.scene):
            for path in paths:
                low = path.lower()
                if low.endswith(IMAGE_SUFFIXES):
                    made.append(material_from_image(self.scene, path))
                elif low.endswith(".json"):
                    try:
                        made.extend(model.load_library(self.scene, path))
                    except (OSError, ValueError, TypeError, KeyError) as exc:
                        self.status.setText(f"Could not load {os.path.basename(path)}: {exc}")
        if made:
            self.select(made[-1]["id"])
        return made

    def _image_dialog(self) -> None:
        from .ui_common import IMAGE_FILTER
        paths, _ = QFileDialog.getOpenFileNames(self, "Material From Image", "", IMAGE_FILTER)
        if paths:
            self.import_files(paths)

    def _load_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Material Library", "", LIBRARY_FILTER)
        if path:
            self.import_files([path])

    def save_library(self, path: str, selected_only: bool = False) -> int:
        ids = self.selected_ids() if selected_only else None
        count = model.save_library(self.scene, path, ids)
        self.status.setText(f"Saved {count} material(s)")
        return count

    def _save_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Material Library", "materials.qmat.json", LIBRARY_FILTER)
        if not path:
            return
        selected_only = False
        if len(self.selected_ids()) > 1:
            answer = QMessageBox.question(self, "Save Library", "Save only the selected materials?")
            selected_only = answer == QMessageBox.StandardButton.Yes
        self.save_library(path, selected_only)

    def _context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.select(item.data(Qt.ItemDataRole.UserRole))
        menu = prepare_popup(QMenu(self))
        if item is not None:
            menu.addAction("Apply to Selected", self.apply_to_selected)
            menu.addAction("Rename", self.rename_current)
            menu.addAction("Duplicate", self.duplicate_selected)
            menu.addAction("Convert to Nodes", self.convert_selected)
            menu.addAction("Delete", self.delete_selected)
            menu.addSeparator()
        menu.addAction("New PBR Material", lambda: self.create("pbr"))
        menu.addAction("New Node Material", lambda: self.create("node"))
        menu.exec(self.list.viewport().mapToGlobal(pos))
