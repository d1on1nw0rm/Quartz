from __future__ import annotations

import copy
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import (QComboBox, QGraphicsItem, QGraphicsObject, QGraphicsPathItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QSplitter,
                               QStackedWidget, QStyleOptionGraphicsItem, QVBoxLayout, QWidget)

from .. import theme
from ..scene import get_scene
from ..widgets.common import prepare_combo, prepare_popup
from . import model
from . import nodes as N
from .colorutil import to_hex
from .convert import convert_to_nodes
from .editor import socket_params
from .hub import hub, watch_scene
from .preview import thumbnail
from .ui_common import FIELD_H, ROW_INDENT, ParamForm, PreviewLabel, style_surface

__all__ = ["NodeEditor", "NodeView", "NodeItem", "SocketItem", "LinkItem"]

NODE_W = N.NODE_WIDTH
HEADER = N.NODE_HEADER
ROW = N.NODE_ROW
SOCKET_R = 6.0
RADIUS = 8.0
GRID = 24.0
GRID_MAJOR = 96.0
ZOOM_MIN = 0.25
ZOOM_MAX = 4.0
PICK = 12.0
PANEL_W = 256
PREVIEW = 128

CATEGORY_TINTS = {
    "Output": theme.TINT_ROSE,
    "Shader": theme.TINT_MINT,
    "Texture": theme.TINT_CITRINE,
    "Color": theme.TINT_AMETHYST,
    "Converter": theme.AXIS_Z,
    "Vector": theme.TINT_AMETHYST,
    "Input": theme.TEXT_SECONDARY,
}


def _font(bold: bool = False) -> QFont:
    f = QFont(theme.FONT_FAMILY)
    f.setPixelSize(12)
    f.setBold(bold)
    return f


class SocketItem(QGraphicsItem):

    def __init__(self, node_item: "NodeItem", spec: N.SocketSpec, is_output: bool, row: int) -> None:
        super().__init__(node_item)
        self.node_item = node_item
        self.spec = spec
        self.name = spec.name
        self.is_output = is_output
        self.type = spec.type
        self.setPos(NODE_W if is_output else 0.0, HEADER + ROW * row + ROW / 2.0)
        self.setAcceptHoverEvents(True)
        self._hover = False
        self.setZValue(2)

    @property
    def node_id(self) -> str:
        return self.node_item.node_id

    def boundingRect(self) -> QRectF:
        r = SOCKET_R + 4
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, p: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = SOCKET_R + (2 if self._hover else 0)
        p.setPen(QPen(QColor(theme.SURFACE_FIELD), 2))
        p.setBrush(QColor(N.SOCKET_COLORS[self.type]))
        if self.type == "vector":
            p.drawRoundedRect(QRectF(-r, -r, 2 * r, 2 * r), 2, 2)
        else:
            p.drawEllipse(QPointF(0, 0), r, r)

    def hoverEnterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, e) -> None:
        self._hover = False
        self.update()


class NodeItem(QGraphicsObject):

    def __init__(self, editor: "NodeEditor", node: dict) -> None:
        super().__init__()
        self.editor = editor
        self.node_id = node["id"]
        self.type_id = node["type"]
        self.nt = N.node_type(node["type"])
        self.node = node
        self.height = N.node_height(self.nt)
        self.sockets: dict[tuple[bool, str], SocketItem] = {}
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setZValue(1)
        row = 0
        for spec in self.nt.outputs:
            self.sockets[(True, spec.name)] = SocketItem(self, spec, True, row)
            row += 1
        for spec in self.nt.inputs:
            self.sockets[(False, spec.name)] = SocketItem(self, spec, False, row)
            row += 1
        self.setPos(QPointF(float(node["pos"][0]), float(node["pos"][1])))

    def socket(self, name: str, is_output: bool) -> SocketItem | None:
        return self.sockets.get((is_output, name))

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, NODE_W + 4, self.height + 4)

    def _value_text(self, spec: N.SocketSpec) -> str:
        if isinstance(spec.default, str):
            return {"@uv": "UV", "@normal": "Normal", "@position": "Position"}.get(spec.default, "")
        value = (self.node.get("inputs") or {}).get(spec.name, spec.default)
        if spec.type == "float":
            return f"{float(value):.3g}"
        return ""

    def paint(self, p: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(0, 0, NODE_W, self.height)
        tint = QColor(CATEGORY_TINTS.get(self.nt.category, theme.TEXT_SECONDARY))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.SURFACE_RAISED))
        p.drawRoundedRect(body, RADIUS, RADIUS)
        head = QPainterPath()
        head.addRoundedRect(QRectF(0, 0, NODE_W, HEADER + RADIUS), RADIUS, RADIUS)
        clip = QPainterPath()
        clip.addRect(QRectF(0, 0, NODE_W, HEADER))
        header_color = QColor(theme.mix(tint.name(), theme.SURFACE_RAISED, 0.35))
        p.setBrush(header_color)
        p.drawPath(head.intersected(clip))
        p.setPen(QPen(QColor(theme.ACCENT if self.isSelected() else theme.HAIRLINE_STRONG),
                      2 if self.isSelected() else 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(body, RADIUS, RADIUS)
        p.setFont(_font(True))
        p.setPen(QColor(theme.TEXT_BRIGHT))
        p.drawText(QRectF(ROW_INDENT * 1.5, 0, NODE_W - ROW_INDENT * 3, HEADER),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.nt.label)
        p.setFont(_font())
        row = 0
        pad = ROW_INDENT * 1.5
        for spec in self.nt.outputs:
            r = QRectF(pad, HEADER + ROW * row, NODE_W - 2 * pad, ROW)
            p.setPen(QColor(theme.TEXT_PRIMARY))
            p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, spec.label)
            row += 1
        graph = self.editor.graph or {}
        for spec in self.nt.inputs:
            r = QRectF(pad, HEADER + ROW * row, NODE_W - 2 * pad, ROW)
            linked = N.link_into(graph, self.node_id, spec.name) is not None
            p.setPen(QColor(theme.TEXT_PRIMARY))
            p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, spec.label)
            if not linked:
                if spec.type == "color" and spec.editable():
                    value = (self.node.get("inputs") or {}).get(spec.name, spec.default)
                    sw = QRectF(r.right() - 24, r.center().y() - 6, 24, 12)
                    p.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 1))
                    p.setBrush(QColor(to_hex(value)))
                    p.drawRoundedRect(sw, 4, 4)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                else:
                    text = self._value_text(spec)
                    if text:
                        p.setPen(QColor(theme.TEXT_SECONDARY))
                        p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, text)
            row += 1

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.editor.node_moved(self)
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)


def link_path(a: QPointF, b: QPointF) -> QPainterPath:
    path = QPainterPath(a)
    dx = max(abs(b.x() - a.x()) * 0.5, 48.0)
    path.cubicTo(QPointF(a.x() + dx, a.y()), QPointF(b.x() - dx, b.y()), b)
    return path


class LinkItem(QGraphicsPathItem):

    def __init__(self, src: SocketItem, dst: SocketItem) -> None:
        super().__init__()
        self.src = src
        self.dst = dst
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(0)
        self.update_path()

    def key(self) -> tuple[str, str]:
        return self.dst.node_id, self.dst.name

    def update_path(self) -> None:
        self.setPath(link_path(self.src.scenePos(), self.dst.scenePos()))

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(PICK)
        return stroker.createStroke(self.path())

    def paint(self, p: QPainter, option, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(theme.ACCENT if self.isSelected() else N.SOCKET_COLORS[self.src.type])
        p.setPen(QPen(color, 2 if not self.isSelected() else 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(self.path())


class NodeView(QGraphicsView):

    def __init__(self, editor: "NodeEditor", scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.editor = editor
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSceneRect(QRectF(-100000, -100000, 200000, 200000))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pan_from = None
        self._drag_socket: SocketItem | None = None
        self._temp: QGraphicsPathItem | None = None
        self._moving = False

    def zoom(self) -> float:
        return float(self.transform().m11())

    def set_zoom(self, value: float) -> None:
        value = min(max(value, ZOOM_MIN), ZOOM_MAX)
        factor = value / self.zoom()
        self.scale(factor, factor)

    def zoom_by(self, steps: float) -> None:
        self.set_zoom(self.zoom() * (1.15 ** steps))

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:
        p.fillRect(rect, QColor(theme.SURFACE_FIELD))
        step = GRID if self.zoom() >= 0.5 else GRID_MAJOR
        left = math.floor(rect.left() / step) * step
        top = math.floor(rect.top() / step) * step
        minor = QPen(QColor(theme.GRID_MINOR), 0)
        major = QPen(QColor(theme.GRID_MAJOR), 0)
        x = left
        while x < rect.right():
            p.setPen(major if abs(math.fmod(x, GRID_MAJOR)) < 1e-6 else minor)
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = top
        while y < rect.bottom():
            p.setPen(major if abs(math.fmod(y, GRID_MAJOR)) < 1e-6 else minor)
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

    def socket_at(self, scene_pos: QPointF) -> SocketItem | None:
        r = PICK / max(self.zoom(), 1e-6)
        best, dist = None, float("inf")
        for item in self.scene().items(QRectF(scene_pos.x() - r, scene_pos.y() - r, 2 * r, 2 * r)):
            if isinstance(item, SocketItem):
                d = (item.scenePos() - scene_pos).manhattanLength()
                if d < dist:
                    best, dist = item, d
        return best

    def begin_link(self, socket: SocketItem) -> SocketItem:
        anchor = socket
        if not socket.is_output:
            link = N.link_into(self.editor.graph, socket.node_id, socket.name)
            if link is not None:
                src_item = self.editor.items.get(link["from"][0])
                self.editor.disconnect_input(socket.node_id, socket.name, commit=False)
                if src_item is not None:
                    found = src_item.socket(link["from"][1], True)
                    if found is not None:
                        anchor = found
        self._drag_socket = anchor
        self._temp = QGraphicsPathItem()
        self._temp.setPen(QPen(QColor(N.SOCKET_COLORS[anchor.type]), 2, Qt.PenStyle.DashLine))
        self._temp.setZValue(3)
        self.scene().addItem(self._temp)
        self.update_link(anchor.scenePos())
        return anchor

    def update_link(self, scene_pos: QPointF) -> None:
        if self._temp is None or self._drag_socket is None:
            return
        a = self._drag_socket.scenePos()
        if self._drag_socket.is_output:
            self._temp.setPath(link_path(a, scene_pos))
        else:
            self._temp.setPath(link_path(scene_pos, a))

    def end_link(self, scene_pos: QPointF) -> bool:
        start = self._drag_socket
        if self._temp is not None:
            self.scene().removeItem(self._temp)
        self._temp = None
        self._drag_socket = None
        if start is None:
            return False
        target = self.socket_at(scene_pos)
        made = False
        if target is not None and target.is_output != start.is_output and target.node_id != start.node_id:
            src, dst = (start, target) if start.is_output else (target, start)
            made = self.editor.connect_sockets(src.node_id, src.name, dst.node_id, dst.name, commit=False)
        self.editor.commit()
        self.editor.rebuild_links()
        return made

    def mousePressEvent(self, e) -> None:
        scene_pos = self.mapToScene(e.position().toPoint())
        if e.button() == Qt.MouseButton.MiddleButton or (
                e.button() == Qt.MouseButton.LeftButton and e.modifiers() & Qt.KeyboardModifier.AltModifier):
            self._pan_from = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            socket = self.socket_at(scene_pos)
            if socket is not None:
                self.begin_link(socket)
                e.accept()
                return
        self._moving = e.button() == Qt.MouseButton.LeftButton
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._pan_from is not None:
            delta = e.position() - self._pan_from
            self._pan_from = e.position()
            self.pan(delta.x(), delta.y())
            e.accept()
            return
        if self._drag_socket is not None:
            self.update_link(self.mapToScene(e.position().toPoint()))
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._pan_from is not None:
            self._pan_from = None
            self.unsetCursor()
            e.accept()
            return
        if self._drag_socket is not None:
            self.end_link(self.mapToScene(e.position().toPoint()))
            e.accept()
            return
        super().mouseReleaseEvent(e)
        if self._moving:
            self._moving = False
            self.editor.commit_positions()

    def pan(self, dx: float, dy: float) -> None:
        z = max(self.zoom(), 1e-6)
        center = self.mapToScene(self.viewport().rect().center())
        self.centerOn(center - QPointF(dx / z, dy / z))

    def wheelEvent(self, e) -> None:
        steps = e.angleDelta().y() / 120.0
        if steps:
            self.zoom_by(steps)
        e.accept()

    def keyPressEvent(self, e) -> None:
        key = e.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_X, Qt.Key.Key_Backspace):
            self.editor.delete_selected()
        elif key in (Qt.Key.Key_F, Qt.Key.Key_Home):
            self.editor.frame_all()
        elif key == Qt.Key.Key_A and e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.editor.show_add_menu(self.mapToGlobal(self.viewport().rect().center()),
                                      self.mapToScene(self.viewport().rect().center()))
        elif key == Qt.Key.Key_D and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.editor.duplicate_selected()
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e) -> None:
        scene_pos = self.mapToScene(e.pos())
        item = self.itemAt(e.pos())
        while item is not None and not isinstance(item, (NodeItem, LinkItem)):
            item = item.parentItem()
        if item is not None:
            if not item.isSelected():
                self.scene().clearSelection()
                item.setSelected(True)
            menu = prepare_popup(QMenu(self))
            if isinstance(item, NodeItem):
                menu.addAction("Duplicate", self.editor.duplicate_selected)
            menu.addAction("Delete", self.editor.delete_selected)
            menu.exec(e.globalPos())
            return
        self.editor.show_add_menu(e.globalPos(), scene_pos)


class NodeEditor(QWidget):

    graphChanged = Signal(str)

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene_ref = scene if scene is not None else get_scene()
        self.material_id: str | None = None
        self.graph: dict | None = None
        self.items: dict[str, NodeItem] = {}
        self.links: dict[tuple[str, str], LinkItem] = {}
        self._last_sig = ""
        self._form: ParamForm | None = None
        self._form_node: str | None = None
        self._rebuilding = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(16)
        self._preview_timer.timeout.connect(self.refresh_preview)
        style_surface(self, "qsNodeEditor")
        self._build()
        hub().changed.connect(self._on_store)
        self._scene_timer = watch_scene(self, self.scene_ref, self.resync)
        self.load(model.active_material_id(self.scene_ref))

    def _button(self, text: str, slot, tip: str = "") -> QPushButton:
        b = QPushButton(text, self)
        b.setFixedHeight(FIELD_H)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tip:
            b.setToolTip(tip)
        if slot is not None:
            b.clicked.connect(slot)
        return b

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.material_combo = QComboBox(self)
        self.material_combo.setFixedHeight(FIELD_H)
        self.material_combo.setMinimumWidth(160)
        self.material_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        prepare_combo(self.material_combo)
        self.material_combo.activated.connect(self._combo_picked)
        self.add_button = self._button("Add Node", None, "Add a node (Shift+A)")
        self.add_menu = self._make_add_menu()
        self.add_button.setMenu(self.add_menu)
        self.delete_button = self._button("Delete", self.delete_selected, "Delete selected nodes and links")
        self.duplicate_button = self._button("Duplicate", self.duplicate_selected, "Duplicate selected nodes")
        self.arrange_button = self._button("Arrange", self.arrange, "Lay out nodes automatically")
        self.frame_button = self._button("Frame All", self.frame_all, "Fit all nodes in view (F)")
        bar.addWidget(self.material_combo)
        bar.addWidget(self.add_button)
        bar.addWidget(self.delete_button)
        bar.addWidget(self.duplicate_button)
        bar.addWidget(self.arrange_button)
        bar.addWidget(self.frame_button)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.stack = QStackedWidget(self)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(8, 8, 8, 8)
        self.placeholder = QLabel("", holder)
        self.placeholder.setObjectName("qsDimLabel")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.convert_button = self._button("Convert to Node Material", self.convert_active)
        self.new_button = self._button("New Node Material", self.new_node_material)
        hl.addStretch(1)
        hl.addWidget(self.placeholder)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.convert_button)
        row.addWidget(self.new_button)
        row.addStretch(1)
        hl.addLayout(row)
        hl.addStretch(1)
        self.stack.addWidget(holder)
        split = QSplitter(Qt.Orientation.Horizontal, self)
        self.gscene = QGraphicsScene(self)
        self.gscene.selectionChanged.connect(self._selection_changed)
        self.view = NodeView(self, self.gscene)
        split.addWidget(self.view)
        panel = QWidget()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(8, 0, 0, 0)
        pl.setSpacing(8)
        self.preview = PreviewLabel(PREVIEW, panel)
        pl.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)
        self.node_title = QLabel("No node selected", panel)
        self.node_title.setObjectName("qsGroupTitle")
        pl.addWidget(self.node_title)
        self.form_scroll = QScrollArea(panel)
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        pl.addWidget(self.form_scroll, 1)
        panel.setMinimumWidth(PANEL_W)
        split.addWidget(panel)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([640, PANEL_W])
        self.stack.addWidget(split)
        lay.addWidget(self.stack, 1)

    def _make_add_menu(self, scene_pos: QPointF | None = None) -> QMenu:
        menu = prepare_popup(QMenu(self))
        for category, types in N.node_types_by_category().items():
            sub = prepare_popup(menu.addMenu(category))
            for nt in types:
                sub.addAction(nt.label, lambda t=nt.id, p=scene_pos: self.add_node(t, p))
        return menu

    def show_add_menu(self, global_pos, scene_pos: QPointF) -> None:
        if self.graph is None:
            return
        self._make_add_menu(scene_pos).exec(global_pos)

    def _refresh_combo(self) -> None:
        self.material_combo.blockSignals(True)
        self.material_combo.clear()
        for mat in model.materials(self.scene_ref):
            suffix = "" if mat.get("type") == "node" else "  (PBR)"
            self.material_combo.addItem(mat.get("name", "") + suffix, mat["id"])
        i = self.material_combo.findData(self.material_id)
        self.material_combo.setCurrentIndex(i)
        self.material_combo.blockSignals(False)

    def _combo_picked(self, index: int) -> None:
        mid = self.material_combo.itemData(index)
        if mid:
            model.set_active_material(self.scene_ref, mid)

    def material(self) -> dict | None:
        return model.find_material(self.scene_ref, self.material_id)

    def load(self, mid: str | None, keep_view: bool = False) -> None:
        keep_view = keep_view and mid is not None and mid == self.material_id and self.graph is not None
        saved = (self.view.transform(), self._view_center()) if keep_view else None
        self.material_id = mid
        mat = self.material()
        self._refresh_combo()
        is_node = mat is not None and mat.get("type") == "node"
        for b in (self.add_button, self.delete_button, self.duplicate_button, self.arrange_button, self.frame_button):
            b.setEnabled(is_node)
        if not is_node:
            self.graph = None
            self._clear_scene()
            self._last_sig = model.material_signature(mat) if mat else ""
            self.placeholder.setText("No material selected" if mat is None else
                                     f"'{mat.get('name')}' is a PBR material")
            self.convert_button.setVisible(mat is not None)
            self.stack.setCurrentIndex(0)
            return
        self.graph = copy.deepcopy(mat.get("graph") or N.new_graph())
        N.prune_graph(self.graph)
        self._last_sig = model.material_signature(mat)
        self.stack.setCurrentIndex(1)
        self.rebuild()
        if saved is not None:
            self.view.setTransform(saved[0])
            self.view.centerOn(saved[1])
        else:
            self.frame_all()
        self.refresh_preview()

    def _clear_scene(self) -> None:
        self._rebuilding = True
        self.gscene.clear()
        self.items.clear()
        self.links.clear()
        self._rebuilding = False
        self._show_form(None)

    def rebuild(self) -> None:
        selected = {nid for nid, it in self.items.items() if it.isSelected()}
        self._clear_scene()
        if self.graph is None:
            return
        self._rebuilding = True
        for node in self.graph.get("nodes", []):
            item = NodeItem(self, node)
            self.gscene.addItem(item)
            self.items[node["id"]] = item
            if node["id"] in selected:
                item.setSelected(True)
        self._rebuilding = False
        self.rebuild_links()
        self._selection_changed()

    def rebuild_links(self) -> None:
        for link in list(self.links.values()):
            self.gscene.removeItem(link)
        self.links.clear()
        if self.graph is None:
            return
        for link in self.graph.get("links", []):
            a = self.items.get(link["from"][0])
            b = self.items.get(link["to"][0])
            if a is None or b is None:
                continue
            sa = a.socket(link["from"][1], True)
            sb = b.socket(link["to"][1], False)
            if sa is None or sb is None:
                continue
            item = LinkItem(sa, sb)
            self.gscene.addItem(item)
            self.links[(link["to"][0], link["to"][1])] = item
        for item in self.items.values():
            item.update()

    def node_moved(self, item: NodeItem) -> None:
        if self._rebuilding:
            return
        for link in self.links.values():
            if link.src.node_item is item or link.dst.node_item is item:
                link.update_path()

    def commit_positions(self) -> bool:
        if self.graph is None:
            return False
        moved = False
        for nid, item in self.items.items():
            node = N.find_node(self.graph, nid)
            if node is None:
                continue
            pos = [float(item.pos().x()), float(item.pos().y())]
            if [round(v, 3) for v in node["pos"]] != [round(v, 3) for v in pos]:
                node["pos"] = pos
                moved = True
        if moved:
            self.commit(preview=False)
        return moved

    def commit(self, preview: bool = True, coalesce=None) -> None:
        mat = self.material()
        if mat is None or self.graph is None:
            return
        mat = copy.deepcopy(mat)
        mat["graph"] = copy.deepcopy(self.graph)
        mat["type"] = "node"
        self._last_sig = model.material_signature(mat)
        model.update_material(self.scene_ref, mat, coalesce)
        self.graphChanged.emit(mat["id"])
        if preview:
            self._preview_timer.start()

    def refresh_preview(self) -> None:
        mat = self.material()
        self.preview.set_image(thumbnail(mat, PREVIEW, (mat or {}).get("preview", "sphere")))

    def _view_center(self) -> QPointF:
        return self.view.mapToScene(self.view.viewport().rect().center())

    def add_node(self, type_id: str, pos=None) -> str | None:
        if self.graph is None:
            return None
        if pos is None:
            c = self._view_center()
            pos = (c.x() - NODE_W / 2, c.y() - HEADER)
        elif isinstance(pos, QPointF):
            pos = (pos.x(), pos.y())
        snapped = (round(pos[0] / GRID) * GRID, round(pos[1] / GRID) * GRID)
        node = N.add_node(self.graph, type_id, snapped)
        self.commit()
        item = NodeItem(self, node)
        self.gscene.addItem(item)
        self.items[node["id"]] = item
        self.gscene.clearSelection()
        item.setSelected(True)
        return node["id"]

    def connect_sockets(self, src_id: str, src_sock: str, dst_id: str, dst_sock: str, commit: bool = True) -> bool:
        if self.graph is None:
            return False
        ok, _why = N.can_connect(self.graph, src_id, src_sock, dst_id, dst_sock)
        if not ok:
            return False
        N.connect(self.graph, src_id, src_sock, dst_id, dst_sock)
        if commit:
            self.commit()
            self.rebuild_links()
        if self._form_node == dst_id:
            self._show_form(dst_id)
        return True

    def disconnect_input(self, dst_id: str, dst_sock: str, commit: bool = True) -> bool:
        if self.graph is None:
            return False
        done = N.disconnect(self.graph, dst_id, dst_sock)
        if done:
            link = self.links.pop((dst_id, dst_sock), None)
            if link is not None:
                self.gscene.removeItem(link)
            if commit:
                self.commit()
                self.rebuild_links()
            if self._form_node == dst_id:
                self._show_form(dst_id)
        return done

    def selected_node_ids(self) -> list:
        return [nid for nid, item in self.items.items() if item.isSelected()]

    def select_nodes(self, ids) -> None:
        self.gscene.clearSelection()
        for nid in ids:
            item = self.items.get(nid)
            if item is not None:
                item.setSelected(True)

    def delete_selected(self) -> int:
        if self.graph is None:
            return 0
        count = 0
        for item in list(self.gscene.selectedItems()):
            if isinstance(item, LinkItem):
                if N.disconnect(self.graph, *item.key()):
                    count += 1
        for nid in self.selected_node_ids():
            node = N.find_node(self.graph, nid)
            if node is None or not N.node_type(node["type"]).removable:
                continue
            if N.remove_node(self.graph, nid):
                count += 1
        if count:
            self.commit()
            self.rebuild()
        return count

    def remove_node(self, nid: str) -> bool:
        self.select_nodes([nid])
        return self.delete_selected() > 0

    def duplicate_selected(self) -> list:
        if self.graph is None:
            return []
        made = []
        for nid in self.selected_node_ids():
            node = N.find_node(self.graph, nid)
            if node is None or not N.node_type(node["type"]).removable:
                continue
            made.append(N.duplicate_node(self.graph, nid, (GRID * 2, GRID * 2))["id"])
        if made:
            self.commit()
            self.rebuild()
            self.select_nodes(made)
        return made

    def arrange(self) -> None:
        if self.graph is None:
            return
        N.arrange_graph(self.graph)
        self.commit(preview=False)
        self.rebuild()
        self.frame_all()

    def frame_all(self) -> None:
        if not self.items:
            self.view.resetTransform()
            self.view.centerOn(0, 0)
            return
        rect = QRectF()
        for item in self.items.values():
            rect = rect.united(item.sceneBoundingRect())
        rect = rect.adjusted(-GRID * 2, -GRID * 2, GRID * 2, GRID * 2)
        self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        z = self.view.zoom()
        if z > 1.0:
            self.view.set_zoom(1.0)
        elif z < ZOOM_MIN:
            self.view.set_zoom(ZOOM_MIN)
        self.view.centerOn(rect.center())

    def _selection_changed(self) -> None:
        if self._rebuilding:
            return
        ids = self.selected_node_ids()
        self._show_form(ids[0] if len(ids) == 1 else None)

    def _show_form(self, nid: str | None) -> None:
        old = self.form_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._form = None
        self._form_node = None
        node = N.find_node(self.graph, nid) if (self.graph is not None and nid) else None
        if node is None:
            self.node_title.setText("No node selected")
            return
        nt = N.node_type(node["type"])
        self.node_title.setText(nt.label.upper())
        props = tuple(nt.props)
        inputs = socket_params(nt, node)
        values = dict(node.get("props") or {})
        values.update({k: v for k, v in (node.get("inputs") or {}).items()})
        form = ParamForm(props + inputs, values)
        for p in inputs:
            if N.link_into(self.graph, nid, p.key) is not None:
                form.rows[p.key].setEnabled(False)
                form.rows[p.key].setToolTip("Driven by a node link")
        prop_keys = {p.key for p in props}
        form.changed.connect(lambda k, v, node_id=nid, pk=prop_keys: self._form_edit(node_id, k, v, k in pk))
        self._form = form
        self._form_node = nid
        if not props and not inputs:
            label = QLabel("This node has no settings", self)
            label.setObjectName("qsDimLabel")
            self.form_scroll.setWidget(label)
            return
        self.form_scroll.setWidget(form)

    def node_form(self) -> ParamForm | None:
        return self._form

    def _form_edit(self, nid: str, key: str, value, is_prop: bool) -> None:
        if is_prop:
            self.set_node_prop(nid, key, value)
        else:
            self.set_node_input(nid, key, value)

    def set_node_prop(self, nid: str, key: str, value) -> None:
        if self.graph is None:
            return
        N.set_node_prop(self.graph, nid, key, value)
        self.commit(coalesce=("prop", self.material_id, nid, key))
        item = self.items.get(nid)
        if item is not None:
            item.update()

    def set_node_input(self, nid: str, key: str, value) -> None:
        if self.graph is None:
            return
        N.set_node_input(self.graph, nid, key, value)
        self.commit(coalesce=("input", self.material_id, nid, key))
        item = self.items.get(nid)
        if item is not None:
            item.update()

    def convert_active(self) -> None:
        if self.material_id is None:
            return
        convert_to_nodes(self.scene_ref, self.material_id)
        self.load(self.material_id)

    def new_node_material(self) -> None:
        model.create_material(self.scene_ref, "node")

    def _on_store(self, owner, key: str) -> None:
        if owner is not self.scene_ref:
            return
        if key == model.ACTIVE_KEY:
            mid = model.active_material_id(self.scene_ref)
            if mid != self.material_id:
                self.load(mid)
            return
        if key != model.LIBRARY_KEY:
            return
        mat = self.material()
        if mat is None:
            self.load(model.active_material_id(self.scene_ref))
            return
        if model.material_signature(mat) != self._last_sig:
            self.load(self.material_id, keep_view=True)
        else:
            self._refresh_combo()

    def resync(self) -> None:
        self._on_store(self.scene_ref, model.ACTIVE_KEY)
        self._on_store(self.scene_ref, model.LIBRARY_KEY)
