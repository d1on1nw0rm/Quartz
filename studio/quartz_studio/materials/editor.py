from __future__ import annotations

import copy

from PySide6.QtCore import SIGNAL, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea, QSplitter, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import theme
from ..scene import get_scene
from ..widgets.common import CollapsibleGroup, prepare_combo
from . import model
from .convert import convert_to_nodes
from .hub import hub, watch_scene
from .nodes import find_node, link_into, node_type, output_node, set_node_input
from .params import Param
from .preview import SHAPES, thumbnail
from .textures import TEXTURE_LABELS, TEXTURE_TYPES, texture_params
from .ui_common import FIELD_H, ROW_INDENT, ParamForm, PreviewLabel, make_row, style_surface

__all__ = ["MaterialEditor", "ChannelPage", "socket_params"]

PREVIEW_SIZE = 128
LIST_W = 128


def socket_params(nt, node: dict) -> tuple:
    out = []
    for s in nt.inputs:
        if not s.editable():
            continue
        if s.type == "float":
            lo = s.minimum if s.minimum is not None else -1.0e6
            hi = s.maximum if s.maximum is not None else 1.0e6
            out.append(Param(s.name, s.label, "float", float(s.default), lo, hi,
                             soft_max=None if hi <= 100.0 else max(lo + 1.0, 10.0)))
        elif s.type == "color":
            out.append(Param(s.name, s.label, "color", list(s.default)))
        elif s.type == "vector":
            out.append(Param(s.name, s.label, "vec3", list(s.default)[:3]))
    return tuple(out)


class ChannelPage(QWidget):

    edited = Signal(str, str, object)
    textureTypeChanged = Signal(str, str)
    textureEdited = Signal(str, str, object)

    def __init__(self, spec: model.ChannelSpec, channel: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.key = spec.key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, ROW_INDENT, 0, ROW_INDENT)
        lay.setSpacing(4)
        title = QLabel(spec.label, self)
        title.setObjectName("qsGroupTitle")
        title.setContentsMargins(ROW_INDENT, 0, 0, 0)
        lay.addWidget(title)
        self.enabled_box: QCheckBox | None = None
        if spec.optional:
            self.enabled_box = QCheckBox()
            self.enabled_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.enabled_box.setChecked(bool(channel.get("enabled")))
            self.enabled_box.toggled.connect(lambda v: self.edited.emit(self.key, "enabled", bool(v)))
            lay.addWidget(make_row("Enabled", self.enabled_box, self))
        self.form = ParamForm(spec.params(), channel, self)
        self.form.changed.connect(lambda k, v: self.edited.emit(self.key, k, v))
        lay.addWidget(self.form)
        self.texture_combo: QComboBox | None = None
        self.texture_form: ParamForm | None = None
        if spec.textured:
            self.texture_group = CollapsibleGroup("Texture", self)
            combo = QComboBox()
            combo.addItem("None", "")
            for t in TEXTURE_TYPES:
                combo.addItem(TEXTURE_LABELS[t], t)
            combo.setFixedHeight(FIELD_H)
            combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            prepare_combo(combo)
            tex = channel.get("texture") or {}
            combo.setCurrentIndex(max(0, combo.findData(tex.get("type", ""))))
            combo.currentIndexChanged.connect(
                lambda i: self.textureTypeChanged.emit(self.key, combo.itemData(i) or ""))
            self.texture_combo = combo
            self.texture_group.add_widget(make_row("Type", combo, self))
            if tex.get("type") in TEXTURE_TYPES:
                self.texture_form = ParamForm(texture_params(tex["type"]), tex, self)
                self.texture_form.changed.connect(lambda k, v: self.textureEdited.emit(self.key, k, v))
                self.texture_group.add_widget(self.texture_form)
            lay.addWidget(self.texture_group)
            mix_row = self.form.rows.get("mix")
            if mix_row is not None:
                mix_row.setVisible(bool(tex))
        lay.addStretch(1)

    def update_values(self, channel: dict) -> None:
        if self.enabled_box is not None:
            self.enabled_box.blockSignals(True)
            self.enabled_box.setChecked(bool(channel.get("enabled")))
            self.enabled_box.blockSignals(False)
        self.form.set_values(channel)
        if self.texture_form is not None and channel.get("texture"):
            self.texture_form.set_values(channel["texture"])


class MaterialEditor(QWidget):

    openNodeEditorRequested = Signal(str)
    materialEdited = Signal(str)

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self.material_id: str | None = None
        self._last_sig = ""
        self._channel = "base_color"
        self._page: ChannelPage | None = None
        self._node_form: ParamForm | None = None
        self._node_target: str | None = None
        self._floating = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(16)
        self._preview_timer.timeout.connect(self.refresh_preview)
        style_surface(self, "qsMaterialEditor")
        self._build()
        hub().changed.connect(self._on_store)
        self._scene_timer = watch_scene(self, self.scene, self.resync)
        self.load(model.active_material_id(self.scene))

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(12)
        self.preview = PreviewLabel(PREVIEW_SIZE, self)
        head.addWidget(self.preview)
        side = QVBoxLayout()
        side.setSpacing(4)
        self.name_edit = QLineEdit(self)
        self.name_edit.setFixedHeight(FIELD_H)
        self.name_edit.setPlaceholderText("Material name")
        self.name_edit.editingFinished.connect(self._rename)
        self.kind_label = QLabel("", self)
        self.kind_label.setObjectName("qsDimLabel")
        self.shape_combo = QComboBox(self)
        for s in SHAPES:
            self.shape_combo.addItem(s.title(), s)
        self.shape_combo.setFixedHeight(FIELD_H)
        self.shape_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        prepare_combo(self.shape_combo)
        self.shape_combo.currentIndexChanged.connect(self._shape_changed)
        self.action_button = QPushButton("Convert to Nodes", self)
        self.action_button.setFixedHeight(FIELD_H)
        self.action_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.action_button.clicked.connect(self._action)
        self.apply_button = QPushButton("Apply to Selected", self)
        self.apply_button.setFixedHeight(FIELD_H)
        self.apply_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_button.clicked.connect(self.apply_to_selected)
        side.addWidget(self.name_edit)
        side.addWidget(self.kind_label)
        side.addWidget(self.shape_combo)
        side.addWidget(self.action_button)
        side.addWidget(self.apply_button)
        side.addStretch(1)
        head.addLayout(side, 1)
        outer.addLayout(head)
        self.stack = QStackedWidget(self)
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setContentsMargins(8, 8, 8, 8)
        msg = QLabel("No material selected", empty)
        msg.setObjectName("qsDimLabel")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.new_button = QPushButton("New Material", empty)
        self.new_button.setFixedHeight(FIELD_H)
        self.new_button.clicked.connect(lambda: model.create_material(self.scene, "pbr"))
        el.addStretch(1)
        el.addWidget(msg)
        el.addWidget(self.new_button, 0, Qt.AlignmentFlag.AlignHCenter)
        el.addStretch(1)
        self.stack.addWidget(empty)
        split = QSplitter(Qt.Orientation.Horizontal, self)
        self.channel_list = QListWidget(split)
        self.channel_list.setMinimumWidth(LIST_W // 2)
        for spec in model.CHANNELS:
            item = QListWidgetItem(spec.label)
            item.setData(Qt.ItemDataRole.UserRole, spec.key)
            if spec.optional:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
            self.channel_list.addItem(item)
        self.channel_list.currentItemChanged.connect(self._channel_selected)
        self.channel_list.itemChanged.connect(self._channel_checked)
        self.page_scroll = QScrollArea(split)
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        split.addWidget(self.channel_list)
        split.addWidget(self.page_scroll)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([LIST_W, 512])
        self.stack.addWidget(split)
        node_page = QWidget()
        nl = QVBoxLayout(node_page)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(4)
        self.node_summary = QLabel("", node_page)
        self.node_summary.setObjectName("qsDimLabel")
        self.node_summary.setContentsMargins(ROW_INDENT, 0, 0, 0)
        nl.addWidget(self.node_summary)
        self.node_scroll = QScrollArea(node_page)
        self.node_scroll.setWidgetResizable(True)
        self.node_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        nl.addWidget(self.node_scroll, 1)
        self.stack.addWidget(node_page)
        outer.addWidget(self.stack, 1)

    def material(self) -> dict | None:
        return model.find_material(self.scene, self.material_id)

    def load(self, mid: str | None) -> None:
        self.material_id = mid
        mat = self.material()
        has = mat is not None
        for w in (self.name_edit, self.shape_combo, self.action_button, self.apply_button):
            w.setEnabled(has)
        if not has:
            self.material_id = None
            self.name_edit.setText("")
            self.kind_label.setText("")
            self.stack.setCurrentIndex(0)
            self.preview.set_image(thumbnail(None, PREVIEW_SIZE, "sphere"))
            self._last_sig = ""
            return
        self._last_sig = model.material_signature(mat)
        self.name_edit.setText(mat.get("name", ""))
        is_node = mat.get("type") == "node"
        self.kind_label.setText("Node material" if is_node else "PBR material")
        self.action_button.setText("Edit Nodes" if is_node else "Convert to Nodes")
        self.shape_combo.blockSignals(True)
        self.shape_combo.setCurrentIndex(max(0, self.shape_combo.findData(mat.get("preview", "sphere"))))
        self.shape_combo.blockSignals(False)
        if is_node:
            self.stack.setCurrentIndex(2)
            self._build_node_page(mat)
        else:
            self.stack.setCurrentIndex(1)
            self._sync_checks(mat)
            self.select_channel(self._channel, force=True)
        self.refresh_preview()

    def _sync_checks(self, mat: dict) -> None:
        self.channel_list.blockSignals(True)
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            key = item.data(Qt.ItemDataRole.UserRole)
            spec = model.channel_spec(key)
            ch = mat["channels"].get(key, {})
            on = not spec.optional or bool(ch.get("enabled"))
            if spec.optional:
                item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            item.setForeground(QColor(theme.TEXT_PRIMARY if on else theme.TEXT_MUTED))
            textured = bool(ch.get("texture"))
            item.setText(spec.label + ("  [T]" if textured else ""))
        self.channel_list.blockSignals(False)

    def select_channel(self, key: str, force: bool = False) -> None:
        mat = self.material()
        if mat is None or mat.get("type") == "node":
            self._channel = key
            return
        if key == self._channel and self._page is not None and not force:
            return
        self._channel = key
        for i in range(self.channel_list.count()):
            if self.channel_list.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.channel_list.blockSignals(True)
                self.channel_list.setCurrentRow(i)
                self.channel_list.blockSignals(False)
                break
        page = ChannelPage(model.channel_spec(key), mat["channels"][key])
        page.edited.connect(self.set_channel_field)
        page.textureTypeChanged.connect(self.set_texture_type)
        page.textureEdited.connect(self.set_texture_field)
        old = self.page_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.page_scroll.setWidget(page)
        self._page = page

    def channel_page(self) -> ChannelPage | None:
        return self._page

    def _channel_selected(self, item, _prev) -> None:
        if item is not None:
            self.select_channel(item.data(Qt.ItemDataRole.UserRole))

    def _channel_checked(self, item) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        if model.channel_spec(key).optional:
            self.set_channel_field(key, "enabled", item.checkState() == Qt.CheckState.Checked)

    def _commit(self, mat: dict, rebuild_page: bool = False, coalesce=None) -> None:
        self._last_sig = model.material_signature(mat)
        model.update_material(self.scene, mat, coalesce)
        if mat.get("type") != "node":
            self._sync_checks(mat)
            if rebuild_page:
                self.select_channel(self._channel, force=True)
            elif self._page is not None:
                self._page.update_values(mat["channels"][self._channel])
        self.materialEdited.emit(mat["id"])
        self._preview_timer.start()

    def set_channel_field(self, key: str, field_name: str, value) -> None:
        mat = self.material()
        if mat is None:
            return
        mat = copy.deepcopy(mat)
        model.set_channel(mat, key, field_name, value)
        coalesce = None if field_name == "enabled" else ("channel", mat["id"], key, field_name)
        self._commit(mat, coalesce=coalesce)

    def set_texture_type(self, key: str, kind: str) -> None:
        mat = self.material()
        if mat is None:
            return
        mat = copy.deepcopy(mat)
        model.set_channel_texture(mat, key, kind or None)
        self._commit(mat, rebuild_page=True)

    def set_texture_field(self, key: str, param: str, value) -> None:
        mat = self.material()
        if mat is None:
            return
        mat = copy.deepcopy(mat)
        model.set_texture_value(mat, key, param, value)
        self._commit(mat, coalesce=("texture", mat["id"], key, param))

    def _rename(self) -> None:
        if self.material_id is None:
            return
        final = model.rename_material(self.scene, self.material_id, self.name_edit.text())
        self.name_edit.setText(final)

    def rename(self, name: str) -> str:
        self.name_edit.setText(name)
        self._rename()
        return self.name_edit.text()

    def _shape_changed(self, index: int) -> None:
        mat = self.material()
        if mat is None:
            return
        mat = copy.deepcopy(mat)
        mat["preview"] = self.shape_combo.itemData(index)
        self._commit(mat)
        self.refresh_preview()

    def set_preview_shape(self, shape: str) -> None:
        self.shape_combo.setCurrentIndex(max(0, self.shape_combo.findData(shape)))

    def _action(self) -> None:
        mat = self.material()
        if mat is None:
            return
        if mat.get("type") == "node":
            self.open_node_editor()
        else:
            convert_to_nodes(self.scene, mat["id"])
            self.load(mat["id"])

    def open_node_editor(self):
        if self.material_id is None:
            return None
        if self.receivers(SIGNAL("openNodeEditorRequested(QString)")) > 0:
            self.openNodeEditorRequested.emit(self.material_id)
            return None
        from .node_editor import NodeEditor
        if self._floating is None:
            self._floating = NodeEditor(self.scene)
            self._floating.setWindowTitle("Node Editor")
            self._floating.resize(896, 512)
        self._floating.load(self.material_id)
        self._floating.show()
        self._floating.raise_()
        return self._floating

    def apply_to_selected(self) -> int:
        from .tags import assign_to_selected
        if self.material_id is None:
            return 0
        return assign_to_selected(self.scene, self.material_id)

    def _shader_node(self, graph: dict) -> dict | None:
        out = output_node(graph)
        if out is not None:
            link = link_into(graph, out["id"], "surface")
            if link is not None:
                node = find_node(graph, link["from"][0])
                if node is not None and node.get("type") == "principled":
                    return node
        for node in graph.get("nodes", []):
            if node.get("type") == "principled":
                return node
        return None

    def _build_node_page(self, mat: dict) -> None:
        graph = mat.get("graph") or {}
        node = self._shader_node(graph)
        self.node_summary.setText(f"{len(graph.get('nodes', []))} nodes, {len(graph.get('links', []))} links")
        old = self.node_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._node_form = None
        self._node_target = None
        if node is None:
            label = QLabel("No Principled BSDF in this graph", self)
            label.setObjectName("qsDimLabel")
            label.setContentsMargins(ROW_INDENT, 0, 0, 0)
            self.node_scroll.setWidget(label)
            return
        nt = node_type("principled")
        params = socket_params(nt, node)
        values = dict(node.get("inputs") or {})
        form = ParamForm(params, values)
        for p in params:
            if link_into(graph, node["id"], p.key) is not None:
                row = form.rows[p.key]
                row.setEnabled(False)
                row.setToolTip("Driven by a node link")
        form.changed.connect(self.set_node_input)
        self._node_form = form
        self._node_target = node["id"]
        self.node_scroll.setWidget(form)

    def node_form(self) -> ParamForm | None:
        return self._node_form

    def set_node_input(self, name: str, value) -> None:
        mat = self.material()
        if mat is None or mat.get("type") != "node" or self._node_target is None:
            return
        mat = copy.deepcopy(mat)
        set_node_input(mat["graph"], self._node_target, name, value)
        self._commit(mat, coalesce=("node", mat["id"], self._node_target, name))

    def refresh_preview(self) -> None:
        mat = self.material()
        shape = (mat or {}).get("preview", "sphere")
        self.preview.set_image(thumbnail(mat, PREVIEW_SIZE, shape))

    def _on_store(self, owner, key: str) -> None:
        if owner is not self.scene:
            return
        if key == model.ACTIVE_KEY:
            mid = model.active_material_id(self.scene)
            if mid != self.material_id:
                self.load(mid)
            return
        if key != model.LIBRARY_KEY:
            return
        mat = self.material()
        if mat is None:
            self.load(model.active_material_id(self.scene))
            return
        sig = model.material_signature(mat)
        if sig != self._last_sig:
            self.load(self.material_id)
        elif self.name_edit.text() != mat.get("name", "") and not self.name_edit.hasFocus():
            self.name_edit.setText(mat.get("name", ""))

    def sizeHint(self) -> QSize:
        return QSize(480, 512)

    def resync(self) -> None:
        self._on_store(self.scene, model.ACTIVE_KEY)
        self._on_store(self.scene, model.LIBRARY_KEY)
