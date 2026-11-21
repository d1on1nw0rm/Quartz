from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QModelIndex, QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QLineEdit,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from quartz_studio import icons, theme
from quartz_studio.scene import EDITABLE_KIND, SceneObject, get_scene
from quartz_studio.widgets.common import PanelMenuBar, PanelTabBar, populate_menu

__all__ = ["ObjectManager", "ObjectTree", "ObjectRowDelegate", "HeaderRule",
           "OBJECT_MANAGER_MENUS", "object_icon_name", "object_icon", "spec_icon"]

EMPTY_TOP = 24
OBJECT_ICON = "empty_polygon"
LINE_OBJECT_ICON = "m_line"
OBJECT_ROLE = Qt.ItemDataRole.UserRole + 1
DRAG_MIME = "application/x-quartz-object"
ROW_H = 26
ROW_INSET = 1
ICON_LEFT = 6
ICON_SIZE = 18
NAME_LEFT = ICON_LEFT + ICON_SIZE + 8
STATUS_W = 32
INDENT = 16
CHEVRON_SIZE = 10
ROW_SELECTED_BG = theme.ACCENT_TINT
ROW_SELECTED_HOVER_BG = theme.ACCENT_TINT_HOVER
ROW_HOVER_BG = theme.SURFACE_RAISED
CHECK_COLOR = theme.STATUS_OK
CROSS_COLOR = theme.STATUS_ERROR
DROP_COLOR = theme.ACCENT
DROP_INVALID_COLOR = theme.STATUS_ERROR
DROP_LINE_H = 2

OBJECT_MANAGER_MENUS: list[tuple[str, list, bool]] = [
    ("File", [
        ("item", "Merge Objects...", None, "file_open"),
        ("item", "Save Selected Objects As...", None, "file_save", False),
        ("sep",),
        ("item", "Export Selection...", None, None, False),
        ("sep",),
        ("item", "Close Manager"),
    ], False),
    ("Edit", [
        ("item", "Undo", "Ctrl+Z", "undo"),
        ("item", "Redo", "Ctrl+Y", "redo", False),
        ("sep",),
        ("item", "Cut", "Ctrl+X", None, False),
        ("item", "Copy", "Ctrl+C", None, False),
        ("item", "Paste", "Ctrl+V"),
        ("item", "Delete", "Delete", None, False),
        ("sep",),
        ("item", "Select All", "Ctrl+A"),
        ("item", "Deselect All", "Ctrl+Shift+A"),
        ("item", "Select Children", None, None, False),
        ("item", "Invert Selection", None, None, False),
    ], False),
    ("View", [
        ("item", "Expand All"),
        ("item", "Collapse All"),
        ("sep",),
        ("item", "Scroll to First Active", None, None, False),
        ("item", "Show Search Bar", None, "search"),
        ("sep",),
        ("submenu", "Display Mode", [
            ("item", "Objects"),
            ("item", "Layers"),
            ("item", "Takes"),
        ]),
        ("item", "Show Tag Icons"),
        ("item", "Configure Columns..."),
    ], False),
    ("Object", [
        ("item", "Group Objects", "Alt+G", None, False),
        ("item", "Ungroup Objects", "Shift+G", None, False),
        ("item", "Delete Without Children", None, None, False),
        ("sep",),
        ("item", "Make Editable", "C", "make_editable", False),
        ("item", "Connect Objects", None, "connect_objects", False),
        ("item", "Connect Objects + Delete", None, None, False),
        ("sep",),
        ("item", "Rename", None, None, False),
        ("item", "Visible in Editor", None, "eye", False),
        ("item", "Visible in Renderer", None, None, False),
        ("sep",),
        ("item", "Object Information...", None, "info", False),
    ], False),
    ("Tags", [
        ("submenu", "Rendering Tags", [
            ("item", "Texture Tag", None, "material"),
            ("item", "Compositing Tag"),
            ("item", "Display Tag"),
        ]),
        ("submenu", "Animation Tags", [
            ("item", "Align to Spline Tag"),
            ("item", "Vibrate Tag"),
            ("item", "Target Tag", None, "target"),
        ]),
        ("submenu", "Simulation Tags", [
            ("item", "Rigid Body Tag"),
            ("item", "Soft Body Tag"),
            ("item", "Collider Tag"),
        ]),
        ("submenu", "Programming Tags", [
            ("item", "Python Tag", None, "python"),
            ("item", "Expression Tag"),
        ]),
        ("sep",),
        ("item", "Protection Tag", None, "lock", False),
        ("item", "Phong Tag", None, None, False),
        ("item", "Selection Tag", None, "tag", False),
    ], True),
    ("Favorites", [
        ("item", "Add Selection to Favorites", None, "star_favorite", False),
        ("item", "Manage Favorites..."),
        ("sep",),
        ("item", "(no favorites)", None, None, False),
    ], False),
]

HAMBURGER_MENU: list = [
    ("item", "Show Tabs"),
    ("item", "Show Menu Bar"),
    ("item", "Show Search Bar", None, "search"),
    ("sep",),
    ("item", "Undock Manager", None, "popout"),
    ("item", "Close Manager", None, "close"),
]

OBJECT_MANAGER_ICONS: list[tuple[str, str, bool]] = [
    ("search", "Search", True),
    ("home_small", "Home", True),
    ("filter", "Filter", True),
    ("popout", "Undock Manager", True),
]


def _spec_of(obj: SceneObject | None):
    if obj is None or obj.kind == EDITABLE_KIND:
        return None
    from quartz_studio.objects import registry
    return registry.SPECS.get(obj.kind)


def object_category(obj: SceneObject | None) -> str:
    spec = _spec_of(obj)
    if spec is not None:
        return spec.category
    if obj is not None and not obj.mesh.has_faces():
        return "spline"
    return "mesh"


def spec_icon(spec) -> tuple[str, str | None]:
    from quartz_studio.widgets import object_palette

    return object_palette._icon_name(spec), object_palette.CATEGORY_COLORS[spec.category]


def object_icon(obj: SceneObject | None) -> tuple[str, str | None]:
    spec = _spec_of(obj)
    if spec is not None:
        return spec_icon(spec)
    if obj is not None and not obj.mesh.has_faces():
        if obj.extras.get("icon") == OBJECT_ICON and len(obj.mesh.points) == 0:
            return OBJECT_ICON, theme.ICON_MESH
        return LINE_OBJECT_ICON, None
    if icons.has(OBJECT_ICON):
        return OBJECT_ICON, theme.ICON_MESH
    return "cube", theme.ICON_MESH


def object_icon_name(obj: SceneObject | None) -> str:
    return object_icon(obj)[0]


class HeaderRule(QFrame):

    def __init__(self, parent: QWidget | None = None, height: int = 1,
                 color: str = theme.HAIRLINE) -> None:
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setStyleSheet(f"background: {color}; border: none;")


def _paint_toggle(p: QPainter, r: QRectF, enabled: bool) -> None:
    cx, cy = r.center().x(), r.center().y()
    p.setBrush(Qt.BrushStyle.NoBrush)
    if enabled:
        p.setPen(QPen(QColor(CHECK_COLOR), theme.ICON_STROKE_W, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(cx - 4, cy + 0.5), QPointF(cx - 1, cy + 3.5),
                                  QPointF(cx + 4, cy - 3.5)]))
    else:
        p.setPen(QPen(QColor(CROSS_COLOR), theme.ICON_STROKE_W, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(cx - 3.5, cy - 3.5), QPointF(cx + 3.5, cy + 3.5))
        p.drawLine(QPointF(cx + 3.5, cy - 3.5), QPointF(cx - 3.5, cy + 3.5))


class ObjectRowDelegate(QStyledItemDelegate):

    def __init__(self, tree: "ObjectTree") -> None:
        super().__init__(tree)
        self._tree = tree

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.column() != 0:
            return
        tree = self._tree
        r = QRectF(option.rect)
        highlighted = tree.is_index_highlighted(index)
        obj = tree.object_of(tree.itemFromIndex(index.siblingAtColumn(0)))
        toggle_left = tree.viewport().width() - STATUS_W
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        icon_rect = QRectF(r.left() + ICON_LEFT, r.center().y() - ICON_SIZE / 2,
                           ICON_SIZE, ICON_SIZE)
        name, color = object_icon(obj)
        icons.render(p, icon_rect, name, color=color,
                     disabled=obj is not None and not obj.enabled)
        name_left = r.left() + NAME_LEFT
        name_rect = QRectF(name_left, r.top(),
                           max(0.0, min(r.right(), toggle_left) - name_left - 4), r.height())
        p.setFont(tree.font())
        if obj is not None and not obj.enabled:
            text_color = theme.TEXT_MUTED
        else:
            text_color = theme.TEXT_PRIMARY
        p.setPen(QColor(text_color))
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        text = tree.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight,
                                             int(name_rect.width()))
        p.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        if obj is not None:
            _paint_toggle(p, QRectF(toggle_left, r.top(), STATUS_W, r.height()), obj.enabled)
        p.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(super().sizeHint(option, index).width(), ROW_H)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem,
                     index: QModelIndex) -> QWidget:
        editor = QLineEdit(parent)
        editor.setObjectName("qsObjectRename")
        editor.setFrame(False)
        editor.setStyleSheet(
            f"QLineEdit#qsObjectRename {{ background: {theme.SURFACE_FIELD};"
            f" color: {theme.TEXT_PRIMARY};"
            f" border: {theme.FOCUS_RING_W}px solid {theme.FOCUS_RING};"
            f" border-radius: {theme.CONTROL_RADIUS - 2}px; padding: 0px 6px;"
            f" selection-background-color: {theme.ACCENT_TINT_HOVER}; }}")
        return editor

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem,
                             index: QModelIndex) -> None:
        r = option.rect
        left = r.left() + NAME_LEFT - 7
        right = r.right() - STATUS_W
        editor.setGeometry(QRect(left, r.top() + 2, max(48, right - left), r.height() - 4))


class ObjectTree(QTreeWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsObjectTree")
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setHeaderLabels(["Objects"])
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRootIsDecorated(True)
        self.setIndentation(INDENT)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        header = self.header()
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(20)
        self.setStyleSheet(
            "QTreeWidget#qsObjectTree { background: transparent; border: none; }"
        )
        self.viewport().setAutoFillBackground(False)
        self.setItemDelegate(ObjectRowDelegate(self))

        self._scene = get_scene()
        self._hover_obj: SceneObject | None = None
        self._syncing = False
        self._press_obj: SceneObject | None = None
        self._press_pos: QPoint | None = None
        self._drag_obj: SceneObject | None = None
        self._drop: tuple[str, SceneObject, bool] | None = None
        self.context_menu = None
        self.itemChanged.connect(self._on_item_changed)
        self._scene.changed.connect(self.sync)
        self._scene.objectsChanged.connect(self.sync)
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self.sync()

    def _walk(self, parent: QTreeWidgetItem | None = None, depth: int = 0):
        count = self.topLevelItemCount() if parent is None else parent.childCount()
        for i in range(count):
            item = self.topLevelItem(i) if parent is None else parent.child(i)
            yield item, depth
            yield from self._walk(item, depth + 1)

    def _rows(self) -> list[tuple[SceneObject, int]]:
        rows: list[tuple[SceneObject, int]] = []

        def visit(parent: SceneObject | None, depth: int) -> None:
            for child in self._scene.children(parent):
                rows.append((child, depth))
                visit(child, depth + 1)

        visit(None, 0)
        return rows

    def _shape_matches(self, rows: list[tuple[SceneObject, int]]) -> bool:
        items = list(self._walk())
        return len(items) == len(rows) and all(
            self._stored(item) is obj and depth == d
            for (item, depth), (obj, d) in zip(items, rows))

    def _rebuild(self, rows: list[tuple[SceneObject, int]]) -> None:
        opened = [self._stored(item) for item, _ in self._walk() if item.isExpanded()]
        opened = [o for o in opened if o is not None]
        ids = {id(o) for o in opened}
        names = {o.name for o in opened}
        self._hover_obj = None
        self.clear()
        stack: list[QTreeWidgetItem] = []
        to_open: list[QTreeWidgetItem] = []
        for obj, depth in rows:
            item = QTreeWidgetItem([obj.name])
            item.setData(0, OBJECT_ROLE, obj)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable)
            if depth == 0:
                self.addTopLevelItem(item)
            else:
                stack[depth - 1].addChild(item)
            del stack[depth:]
            stack.append(item)
            if id(obj) in ids or obj.name in names:
                to_open.append(item)
        for item in to_open:
            item.setExpanded(True)

    def _refresh_names(self) -> None:
        for item, _ in self._walk():
            obj = self.object_of(item)
            if obj is not None and item.text(0) != obj.name:
                item.setText(0, obj.name)

    def sync(self) -> None:
        rows = self._rows()
        self._syncing = True
        try:
            if self._shape_matches(rows):
                self._refresh_names()
            else:
                self._rebuild(rows)
        finally:
            self._syncing = False
        self.viewport().update()

    def row_names(self) -> list[str]:
        return [item.text(0) for item, _ in self._walk()]

    @staticmethod
    def _stored(item: QTreeWidgetItem | None) -> SceneObject | None:
        if item is None:
            return None
        obj = item.data(0, OBJECT_ROLE)
        return obj if isinstance(obj, SceneObject) else None

    def object_of(self, item: QTreeWidgetItem | None) -> SceneObject | None:
        obj = self._stored(item)
        return obj if obj is not None and obj in self._scene.objects else None

    def item_of(self, obj: SceneObject | None) -> QTreeWidgetItem | None:
        if obj is None:
            return None
        for item, _ in self._walk():
            if self.object_of(item) is obj:
                return item
        return None

    def is_highlighted(self, obj: SceneObject | None) -> bool:
        return self._scene.is_object_selected(obj)

    def is_active_row(self, obj: SceneObject | None) -> bool:
        scene = self._scene
        return obj is not None and obj is scene.active and scene.object_selected

    def is_index_highlighted(self, index: QModelIndex) -> bool:
        return self.is_highlighted(self.object_of(self.itemFromIndex(index.siblingAtColumn(0))))

    def highlighted_names(self) -> list[str]:
        return [obj.name for obj in self._scene.selected_objects()]

    def select(self, obj: SceneObject | None, op: str = "replace") -> None:
        scene = self._scene
        if obj is None:
            if op == "replace":
                scene.select_object(False)
        elif op == "replace" and obj is scene.active and not scene.extra_selected:
            scene.select_object(True)
        else:
            scene.select_objects([obj], op, active=obj)

    @staticmethod
    def _click_op(mods) -> str:
        if mods & Qt.KeyboardModifier.ControlModifier:
            return "toggle"
        if mods & Qt.KeyboardModifier.ShiftModifier:
            return "add"
        return "replace"

    def _on_selection_changed(self) -> None:
        self.viewport().update()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._syncing or column != 0:
            return
        obj = self.object_of(item)
        if obj is None:
            return
        self._scene.rename_object(obj, item.text(0))
        if item.text(0) != obj.name:
            self._syncing = True
            try:
                item.setText(0, obj.name)
            finally:
                self._syncing = False

    def delete_active(self) -> bool:
        scene = self._scene
        obj = scene.active
        if obj is None or obj not in scene.objects:
            return False
        targets = scene.selected_objects() or [obj]
        if len(targets) == 1:
            scene.remove_object(targets[0])
            return True
        from quartz_studio.widgets import context_menu

        context_menu.delete_objects(scene, targets)
        return True

    def rename(self, obj: SceneObject | None = None) -> bool:
        item = self.item_of(obj if obj is not None else self._scene.active)
        if item is None:
            return False
        self.editItem(item, 0)
        return True

    def toggle_enabled(self, obj: SceneObject | None) -> bool:
        if obj is None or obj not in self._scene.objects:
            return False
        self._scene.set_enabled(obj, not obj.enabled)
        return True

    def move_object(self, obj: SceneObject, parent: SceneObject | None,
                    index: int | None = None) -> bool:
        moved = self._scene.set_parent(obj, parent, index)
        if moved and parent is not None:
            parent_item = self.item_of(parent)
            if parent_item is not None:
                parent_item.setExpanded(True)
        return moved

    def _drop_plan(self, obj: SceneObject, pos: QPoint) -> tuple[str, SceneObject | None,
                                                                 SceneObject | None,
                                                                 int | None] | None:
        item = self.itemAt(pos)
        if item is None:
            return "root", None, None, None
        target = self.object_of(item)
        if target is None or target is obj:
            return None
        rect = self.visualItemRect(item)
        band = rect.height() / 4
        offset = pos.y() - rect.top()
        if offset < band:
            mode = "above"
        elif offset > rect.height() - band:
            mode = "below"
        else:
            mode = "onto"
        if mode == "onto":
            return mode, target, target, None
        parent = target.parent
        siblings = [o for o in self._scene.children(parent) if o is not obj]
        at = siblings.index(target)
        return mode, target, parent, at if mode == "above" else at + 1

    def _can_drop(self, obj: SceneObject, parent: SceneObject | None) -> bool:
        if parent is None:
            return True
        return parent is not obj and all(d is not parent for d in self._scene.descendants(obj))

    def drop_object(self, obj: SceneObject, pos: QPoint) -> bool:
        plan = self._drop_plan(obj, pos)
        if plan is None or not self._can_drop(obj, plan[2]):
            return False
        return self.move_object(obj, plan[2], plan[3])

    def _set_drop(self, plan, valid: bool = True) -> None:
        state = None
        if plan is not None and plan[0] != "root":
            state = (plan[0], plan[1], valid)
        if state != self._drop:
            self._drop = state
            self.viewport().update()

    def _begin_drag(self, obj: SceneObject) -> None:
        self._drag_obj = obj
        self._press_obj = None
        self._press_pos = None
        mime = QMimeData()
        mime.setData(DRAG_MIME, QByteArray(obj.name.encode("utf-8")))
        mime.setText(obj.name)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_obj = None
        self._set_drop(None)

    def startDrag(self, supported_actions) -> None:
        if self._press_obj is not None:
            self._begin_drag(self._press_obj)

    def _in_toggle(self, pos: QPoint) -> bool:
        return pos.x() >= self.viewport().width() - STATUS_W

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position().toPoint()
            obj = self.object_of(self.itemAt(pos))
            if obj is not None and self._in_toggle(pos):
                self.toggle_enabled(obj)
                e.accept()
                return
            self.select(obj, self._click_op(e.modifiers()))
            self._press_obj = obj
            self._press_pos = pos
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._press_obj = None
        self._press_pos = None
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:
        from quartz_studio.widgets import context_menu

        obj = self.object_of(self.itemAt(e.pos()))
        scene = self._scene
        if obj is None:
            menu = context_menu.build_create_menu(self)
        else:
            if obj not in scene.selected_objects():
                self.select(obj)
            menu = context_menu.build_object_menu(scene, obj, context_menu.find_canvas(self), self, self)
        self.context_menu = context_menu.show_menu(menu, e.globalPos())
        e.accept()

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position().toPoint()
            item = self.itemAt(pos)
            obj = self.object_of(item)
            if obj is not None and self._in_toggle(pos):
                e.accept()
                return
            if obj is not None and self.columnAt(pos.x()) == 0:
                self.select(obj)
                self.editItem(item, 0)
                e.accept()
                return
        super().mouseDoubleClickEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if (self._press_obj is not None and self._press_pos is not None
                and bool(e.buttons() & Qt.MouseButton.LeftButton)
                and (e.position().toPoint() - self._press_pos).manhattanLength()
                >= QApplication.startDragDistance()):
            self._begin_drag(self._press_obj)
            e.accept()
            return
        self._set_hover(self.object_of(self.itemAt(e.position().toPoint())))
        super().mouseMoveEvent(e)

    def viewportEvent(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.Leave:
            self._set_hover(None)
        return super().viewportEvent(e)

    def _set_hover(self, obj: SceneObject | None) -> None:
        if obj is not self._hover_obj:
            self._hover_obj = obj
            self.viewport().update()

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if self._drag_obj is not None and e.mimeData().hasFormat(DRAG_MIME):
            e.setDropAction(Qt.DropAction.MoveAction)
            e.accept()
            return
        e.ignore()

    def dragMoveEvent(self, e: QDragMoveEvent) -> None:
        obj = self._drag_obj
        if obj is None or not e.mimeData().hasFormat(DRAG_MIME):
            self._set_drop(None)
            e.ignore()
            return
        plan = self._drop_plan(obj, e.position().toPoint())
        valid = plan is not None and self._can_drop(obj, plan[2])
        self._set_drop(plan, valid)
        if valid:
            e.setDropAction(Qt.DropAction.MoveAction)
            e.accept()
        else:
            e.ignore()

    def dragLeaveEvent(self, e: QDragLeaveEvent) -> None:
        self._set_drop(None)
        e.accept()

    def dropEvent(self, e: QDropEvent) -> None:
        obj = self._drag_obj
        self._set_drop(None)
        if obj is None or not e.mimeData().hasFormat(DRAG_MIME):
            e.ignore()
            return
        self.drop_object(obj, e.position().toPoint())
        e.setDropAction(Qt.DropAction.MoveAction)
        e.accept()

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.ShortcutOverride:
            from quartz_studio import controls

            if controls.lookup(e, "objects") is not None:
                e.accept()
                return True
        return super().event(e)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        from quartz_studio import controls

        action_id = controls.lookup(e, "objects")
        if action_id == "object.rename":
            if self._scene.object_selected and self.rename():
                e.accept()
                return
        elif action_id == "object.delete":
            if self.state() != QAbstractItemView.State.EditingState:
                self.delete_active()
                e.accept()
                return
        elif action_id is not None and controls.run(action_id):
            e.accept()
            return
        super().keyPressEvent(e)

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        if self.topLevelItemCount() == 0:
            p = QPainter(self.viewport())
            p.setPen(QColor(theme.TEXT_SECONDARY))
            area = self.viewport().rect().adjusted(0, EMPTY_TOP, 0, 0)
            p.drawText(area, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "No objects")
            p.end()

    def drawRow(self, painter: QPainter, option: QStyleOptionViewItem,
                index: QModelIndex) -> None:
        obj = self.object_of(self.itemFromIndex(index.siblingAtColumn(0)))
        highlighted = self.is_highlighted(obj)
        marked = highlighted and self.is_active_row(obj)
        hovered = obj is not None and obj is self._hover_obj
        color = None
        if highlighted:
            color = ROW_SELECTED_HOVER_BG if hovered else ROW_SELECTED_BG
        elif hovered:
            color = ROW_HOVER_BG
        cell = self.visualRect(index)
        if color is not None:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            band = QRectF(0, cell.top() + ROW_INSET, self.viewport().width(),
                          cell.height() - 2 * ROW_INSET)
            painter.drawRoundedRect(band, theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)
            if marked:
                painter.setBrush(QColor(theme.ACCENT))
                painter.drawRoundedRect(
                    QRectF(0, band.top() + 4, theme.ACCENT_BAR_W, band.height() - 8),
                    theme.ACCENT_BAR_W / 2, theme.ACCENT_BAR_W / 2)
            painter.restore()
        super().drawRow(painter, option, index)
        self._paint_drop(painter, cell, obj)

    def drawBranches(self, painter: QPainter, rect: QRect, index: QModelIndex) -> None:
        item = self.itemFromIndex(index.siblingAtColumn(0))
        if item is None or item.childCount() == 0:
            return
        step = self.indentation()
        cell = QRectF(rect.right() - step + 1, rect.top(), step, rect.height())
        box = QRectF(cell.center().x() - CHEVRON_SIZE / 2, cell.center().y() - CHEVRON_SIZE / 2,
                     CHEVRON_SIZE, CHEVRON_SIZE)
        name = "chevron_down" if self.isExpanded(index) else "chevron_right"
        icons.render(painter, box, name, color=theme.TEXT_SECONDARY)

    def _paint_drop(self, painter: QPainter, cell: QRect, obj: SceneObject | None) -> None:
        drop = self._drop
        if drop is None or obj is None or drop[1] is not obj:
            return
        color = QColor(DROP_COLOR if drop[2] else DROP_INVALID_COLOR)
        width = self.viewport().width()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if drop[0] == "above":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(0, cell.top() - DROP_LINE_H / 2, width, DROP_LINE_H),
                                    DROP_LINE_H / 2, DROP_LINE_H / 2)
        elif drop[0] == "below":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(
                QRectF(0, cell.bottom() + 1 - DROP_LINE_H / 2, width, DROP_LINE_H),
                DROP_LINE_H / 2, DROP_LINE_H / 2)
        else:
            fill = QColor(color)
            fill.setAlpha(theme.ACCENT_ALPHA)
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(fill)
            painter.drawRoundedRect(
                QRectF(1, cell.top() + ROW_INSET + 0.5, width - 2, cell.height() - 2 * ROW_INSET - 1),
                theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)
        painter.restore()


class ObjectManager(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsObjectManager")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(260, 120)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.CARD_PADDING, theme.SPACE_1, theme.CARD_PADDING,
                               theme.CARD_PADDING)
        lay.setSpacing(0)

        self.tabs = PanelTabBar(["Objects"], self)
        lay.addWidget(self.tabs)

        lay.addWidget(HeaderRule(self))
        lay.addSpacing(theme.SPACE_1)

        self.tree = ObjectTree(self)
        lay.addWidget(self.tree, 1)
