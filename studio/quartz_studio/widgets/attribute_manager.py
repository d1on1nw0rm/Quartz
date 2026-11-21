from __future__ import annotations

from functools import partial

from PySide6.QtCore import QLocale, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPaintEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QStyle,
    QStyleOptionSpinBox,
    QVBoxLayout,
    QWidget,
)

from quartz_studio import icons, theme
from quartz_studio.modeling.panel import ScrubIntSpin, ScrubSpin
from quartz_studio.objects import registry
from quartz_studio.scene import get_scene
from quartz_studio.widgets.common import CollapsibleGroup, FieldRow, PanelTabBar, prepare_combo
from quartz_studio.widgets.coordinates import format_number
from quartz_studio.widgets.object_manager import HeaderRule, object_icon

__all__ = [
    "AttributeManager",
    "ObjectHeader",
    "ParamEditor",
    "mesh_summary",
]

LABEL_WIDTH = 120
LABEL_INDENT = 10
HEADER_H = 28
HEADER_ICON = 18
GROUP_SPACING = 2
ERROR_COLOR = theme.STATUS_ERROR
AXIS_COLORS = (theme.AXIS_X, theme.AXIS_Y, theme.AXIS_Z)
DECIMALS = 4
BIG = 1e9
BIG_INT = 1_000_000_000
VECTOR_SPIN_MIN = 32
ARROW_W = 16
ARROW_HALF = 3.0
SPIN_BUTTONS_STYLE = (
    "QAbstractSpinBox::up-button, QAbstractSpinBox::down-button"
    " { width: 0px; border: none; }"
)
SPIN_TEXT_MARGIN = 6
SPIN_STYLE = (
    "QAbstractSpinBox::up-button { subcontrol-origin: border;"
    f" subcontrol-position: top right; width: {ARROW_W}px; border: none;"
    " background: transparent; }"
    "QAbstractSpinBox::down-button { subcontrol-origin: border;"
    f" subcontrol-position: bottom right; width: {ARROW_W}px; border: none;"
    " background: transparent; }"
)
VECTOR_TEXT_MARGIN = 4
VECTOR_SPIN_STYLE = "QAbstractSpinBox { padding: 2px 2px; }" + SPIN_BUTTONS_STYLE


def _on(key: str):
    return lambda values: bool(values.get(key))


def _is(key: str, *allowed: str):
    return lambda values: values.get(key) in allowed


PARAM_APPLIES = {
    "cube": {"fillet_radius": _on("fillet"), "fillet_subdivision": _on("fillet")},
    "rectangle": {"radius": _on("rounding"), "points_per_90": _on("rounding")},
    "n_side": {"rounding_radius": _on("rounding"), "points_per_90": _on("rounding")},
    "circle": {"radius_y": _on("ellipse"), "inner_radius": _on("ring")},
    "cloner": {
        "linear_count": _is("mode", "Linear"), "linear_position": _is("mode", "Linear"),
        "linear_scale": _is("mode", "Linear"), "linear_rotation": _is("mode", "Linear"),
        "radial_count": _is("mode", "Radial"), "radial_radius": _is("mode", "Radial"),
        "radial_plane": _is("mode", "Radial"), "radial_start": _is("mode", "Radial"),
        "radial_end": _is("mode", "Radial"), "radial_align": _is("mode", "Radial"),
        "grid_count": _is("mode", "Grid Array"), "grid_size": _is("mode", "Grid Array"),
    },
}


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def mesh_summary(mesh) -> str:
    points = _count(len(mesh.points), "point")
    if mesh.polygons:
        return f"{points} · {_count(len(mesh.polygons), 'polygon')}"
    if mesh.loose_edges:
        return f"{points} · {_count(len(mesh.loose_edges), 'edge')}"
    return points


def _unit_suffix(param) -> str:
    if param.kind == "distance":
        return " cm"
    if param.kind == "angle":
        return " °"
    if param.kind == "percent":
        return " %"
    return f" {param.unit}" if param.unit else ""


def _bounds(param, default: float) -> tuple[float, float]:
    lo = param.minimum if param.minimum is not None else -default
    hi = param.maximum if param.maximum is not None else default
    return float(lo), float(hi)


class _ArrowsMixin:

    def paintEvent(self, e: QPaintEvent) -> None:
        super().paintEvent(e)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        style = self.style()
        up = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, option,
                                  QStyle.SubControl.SC_SpinBoxUp, self)
        down = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, option,
                                    QStyle.SubControl.SC_SpinBoxDown, self)
        if up.width() < ARROW_W // 2:
            return
        color = QColor(theme.TEXT_SECONDARY if self.isEnabled() else theme.TEXT_MUTED)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, 1.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        for rect, sign in ((up, -1.0), (down, 1.0)):
            cx, cy = rect.center().x() + 0.5, rect.center().y() + 0.5
            p.drawPolyline(QPolygonF([QPointF(cx - ARROW_HALF, cy - sign * ARROW_HALF / 2),
                                      QPointF(cx, cy + sign * ARROW_HALF / 2),
                                      QPointF(cx + ARROW_HALF, cy - sign * ARROW_HALF / 2)]))
        p.end()


class _Spin(_ArrowsMixin, ScrubSpin):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setLocale(QLocale.c())

    def textFromValue(self, value: float) -> str:
        return format_number(value, self.decimals())


class _IntSpin(_ArrowsMixin, ScrubIntSpin):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setLocale(QLocale.c())


class _Combo(QComboBox):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_combo(self)

    def wheelEvent(self, e) -> None:
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


def _widget_busy(w: QWidget) -> bool:
    if isinstance(w, QAbstractSpinBox):
        if getattr(w, "_scrub_origin", None) is not None:
            return True
        edit = w.lineEdit()
        return edit.hasFocus() and edit.isModified()
    if isinstance(w, QLineEdit):
        return w.hasFocus() and w.isModified()
    if isinstance(w, QComboBox):
        return w.view().isVisible()
    return False


def _show_spin(spin: QAbstractSpinBox, value) -> None:
    spin.setValue(value)
    want = spin.prefix() + spin.textFromValue(spin.value()) + spin.suffix()
    edit = spin.lineEdit()
    if edit.text() != want:
        edit.setText(want)
    edit.setModified(False)


def _show_line(edit: QLineEdit, text: str) -> None:
    if edit.text() != text:
        edit.setText(text)
    edit.setModified(False)


class ParamEditor(QWidget):

    edited = Signal(str, object)

    def __init__(self, param, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.param = param
        self.widgets: list[QWidget] = []
        self._vector = [0.0, 0.0, 0.0]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        kind = param.kind
        key = param.key
        if kind == "bool":
            box = QCheckBox(self)
            box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            box.toggled.connect(lambda v: self.edited.emit(key, bool(v)))
            lay.addWidget(box)
            lay.addStretch(1)
            self.widgets.append(box)
        elif kind == "choice":
            combo = _Combo(self)
            combo.addItems(list(param.choices))
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            combo.currentIndexChanged.connect(
                lambda i, c=combo: self.edited.emit(key, c.itemText(i)))
            lay.addWidget(combo, 1)
            self.widgets.append(combo)
        elif kind == "int":
            spin = _IntSpin(self)
            lo, hi = _bounds(param, BIG_INT)
            spin.setRange(int(lo), int(hi))
            spin.setSingleStep(max(1, int(param.step)))
            spin.setSuffix(_unit_suffix(param))
            spin.setStyleSheet(SPIN_STYLE)
            spin.lineEdit().setTextMargins(SPIN_TEXT_MARGIN, 0, 0, 0)
            spin.valueChanged.connect(lambda v: self.edited.emit(key, int(v)))
            lay.addWidget(spin, 1)
            self.widgets.append(spin)
        elif kind == "vector":
            for axis, label in enumerate("XYZ"):
                tag = QLabel(label, self)
                tag.setObjectName("qsDimLabel")
                tag.setFixedWidth(10)
                tag.setStyleSheet(
                    f"QLabel#qsDimLabel {{ color: {AXIS_COLORS[axis]}; font-weight: 600; }}")
                lay.addWidget(tag)
                spin = _Spin(self)
                lo, hi = _bounds(param, BIG)
                spin.setRange(lo, hi)
                spin.setDecimals(DECIMALS)
                spin.setSingleStep(param.step)
                spin.setSuffix(f" {param.unit}" if param.unit else "")
                spin.setMinimumWidth(VECTOR_SPIN_MIN)
                spin.setStyleSheet(VECTOR_SPIN_STYLE)
                spin.lineEdit().setTextMargins(VECTOR_TEXT_MARGIN, 0, 0, 0)
                spin.valueChanged.connect(lambda v, i=axis: self._on_component(i, v))
                lay.addWidget(spin, 1)
                self.widgets.append(spin)
        elif kind == "text":
            edit = QLineEdit(self)
            edit.editingFinished.connect(lambda e=edit: self.edited.emit(key, e.text()))
            lay.addWidget(edit, 1)
            self.widgets.append(edit)
        else:
            spin = _Spin(self)
            lo, hi = _bounds(param, BIG)
            spin.setRange(lo, hi)
            spin.setDecimals(DECIMALS)
            spin.setSingleStep(param.step)
            spin.setSuffix(_unit_suffix(param))
            spin.setStyleSheet(SPIN_STYLE)
            spin.lineEdit().setTextMargins(SPIN_TEXT_MARGIN, 0, 0, 0)
            spin.valueChanged.connect(lambda v: self.edited.emit(key, float(v)))
            lay.addWidget(spin, 1)
            self.widgets.append(spin)

    def _on_component(self, axis: int, value: float) -> None:
        vec = list(self._vector)
        vec[axis] = float(value)
        self._vector = vec
        self.edited.emit(self.param.key, tuple(vec))

    def spins(self) -> list[QAbstractSpinBox]:
        return [w for w in self.widgets if isinstance(w, QAbstractSpinBox)]

    def is_busy(self) -> bool:
        return any(_widget_busy(w) for w in self.widgets)

    def set_value(self, value, force: bool = False) -> None:
        kind = self.param.kind
        for w in self.widgets:
            w.blockSignals(True)
        try:
            if kind == "bool":
                self.widgets[0].setChecked(bool(value))
            elif kind == "choice":
                combo = self.widgets[0]
                if force or not _widget_busy(combo):
                    combo.setCurrentIndex(max(0, combo.findText(str(value))))
            elif kind == "text":
                edit = self.widgets[0]
                if force or not _widget_busy(edit):
                    _show_line(edit, "" if value is None else str(value))
            elif kind == "vector":
                vals = [float(v) for v in value] if value is not None else [0.0, 0.0, 0.0]
                self._vector = vals
                for w, v in zip(self.spins(), vals):
                    if force or not _widget_busy(w):
                        _show_spin(w, v)
            elif kind == "int":
                spin = self.widgets[0]
                if force or not _widget_busy(spin):
                    _show_spin(spin, int(value))
            else:
                spin = self.widgets[0]
                if force or not _widget_busy(spin):
                    _show_spin(spin, float(value))
        finally:
            for w in self.widgets:
                w.blockSignals(False)

    def value(self):
        kind = self.param.kind
        if kind == "bool":
            return self.widgets[0].isChecked()
        if kind == "choice":
            return self.widgets[0].currentText()
        if kind == "text":
            return self.widgets[0].text()
        if kind == "vector":
            return tuple(float(w.value()) for w in self.spins())
        if kind == "int":
            return int(self.widgets[0].value())
        return float(self.widgets[0].value())


class ObjectHeader(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsObjectHeader")
        self.setFixedHeight(HEADER_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.SPACE_2, 0, theme.SPACE_2, 0)
        lay.setSpacing(theme.SPACE_2)
        self.icon = QLabel(self)
        self.icon.setFixedSize(HEADER_ICON, HEADER_ICON)
        lay.addWidget(self.icon)
        self.title = QLabel("", self)
        self.title.setObjectName("qsObjectHeaderTitle")
        self.title.setStyleSheet(
            f"QLabel#qsObjectHeaderTitle {{ color: {theme.TEXT_PRIMARY}; font-weight: 600; }}")
        lay.addWidget(self.title, 1)
        self._icon_name = ""
        self._icon_color: str | None = None
        self._type = ""
        self._name = ""

    def set_object(self, type_text: str, name: str, icon_name: str,
                   color: str | None = None) -> None:
        self._type = type_text
        self._name = name
        text = f"{type_text} [{name}]"
        if self.title.text() != text:
            self.title.setText(text)
        if (icon_name, color) != (self._icon_name, self._icon_color):
            self._icon_name = icon_name
            self._icon_color = color
            self.icon.setPixmap(icons.pixmap(icon_name, HEADER_ICON, color,
                                             device_pixel_ratio=self.devicePixelRatioF()))

    def text(self) -> str:
        return self.title.text()

    def type_text(self) -> str:
        return self._type

    def name(self) -> str:
        return self._name

    def icon_name(self) -> str:
        return self._icon_name


class AttributeManager(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsAttributeManager")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(256, 160)
        self._scene = get_scene()
        self._obj = None
        self._spec = None
        self._key: str | None = "\0"
        self._editing = False
        self._expanded: dict[tuple[str, str], bool] = {}
        self.context_menu = None
        self.rebuild_count = 0
        self.object_editors: dict[str, ParamEditor] = {}
        self.object_rows: dict[str, FieldRow] = {}
        self.object_groups: dict[str, CollapsibleGroup] = {}
        self.object_page: QWidget | None = None
        self._pages: dict[str, tuple] = {}
        self._shown: tuple | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.CARD_PADDING, theme.SPACE_1, theme.CARD_PADDING,
                               theme.CARD_PADDING)
        lay.setSpacing(0)

        self.tabs = PanelTabBar(("Attributes",), self)
        lay.addWidget(self.tabs)
        lay.addWidget(HeaderRule(self))
        lay.addSpacing(theme.SPACE_1)

        self.header = ObjectHeader(self)
        self.object_header = self.header
        lay.addWidget(self.header)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("qsAttributeError")
        self.error_label.setWordWrap(True)
        self.error_label.setContentsMargins(theme.SPACE_2, theme.SPACE_1, theme.SPACE_2,
                                            theme.SPACE_1)
        self.error_label.setStyleSheet(
            f"QLabel#qsAttributeError {{ color: {ERROR_COLOR};"
            f" background: {theme.mix(theme.STATUS_ERROR, theme.SURFACE_CARD, 0.14)};"
            f" border-radius: {theme.CONTROL_RADIUS}px; }}")
        lay.addWidget(self.error_label)
        lay.addSpacing(theme.SPACE_1)

        self.summary_label = QLabel("", self)
        self.summary_label.setObjectName("qsDimLabel")
        self.summary_label.setFixedHeight(theme.ROW_H)
        self.summary_label.setContentsMargins(theme.SPACE_2, 0, theme.SPACE_2, 0)
        lay.addWidget(self.summary_label)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self.object_host = QWidget(body)
        self.object_host_layout = QVBoxLayout(self.object_host)
        self.object_host_layout.setContentsMargins(0, 0, 0, 0)
        self.object_host_layout.setSpacing(0)
        bl.addWidget(self.object_host)
        bl.addStretch(1)
        self.scroll.setWidget(body)
        lay.addWidget(self.scroll, 1)

        self.empty_label = QLabel("No object selected", self)
        self.empty_label.setObjectName("qsDimLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.empty_label.setContentsMargins(0, 24, 0, 0)
        lay.addWidget(self.empty_label, 1)

        self._filler = QWidget(self)
        lay.addWidget(self._filler, 1)

        self._scene.changed.connect(self.refresh)
        self._scene.selectionChanged.connect(self.refresh)
        self._scene.objectsChanged.connect(self.refresh)
        self._update()

    @staticmethod
    def _row(label: str, editor: QWidget | None = None) -> FieldRow:
        return FieldRow(label, editor, label_width=LABEL_WIDTH, indent=LABEL_INDENT)

    def _target(self):
        scene = self._scene
        obj = scene.active
        if obj is None or obj not in scene.objects:
            return None
        if scene.mode == "model" and not scene.object_selected:
            return None
        return obj

    @staticmethod
    def _spec_of(obj):
        if obj is None or obj.kind == "polygon":
            return None
        return registry.SPECS.get(obj.kind)

    def _type_text(self, obj) -> str:
        if obj.kind == "polygon":
            return "Polygon Object"
        spec = self._spec_of(obj)
        return spec.label if spec is not None else obj.kind

    def _icon_for(self, obj) -> tuple[str, str | None]:
        return object_icon(obj)

    def refresh(self, *_args) -> None:
        if self._editing:
            return
        self._update()

    def _fingerprint(self, obj) -> tuple | None:
        if obj is None:
            return None
        mesh = obj.mesh
        counts = (len(mesh.points), len(mesh.polygons), len(mesh.loose_edges))             if obj.kind == "polygon" else ()
        return (getattr(obj, "_uid", id(obj)), obj.kind, obj.name, getattr(obj, "error", ""),
                repr(obj.params), counts, self._scene.mode, self._scene.object_selected)

    def _update(self) -> None:
        obj = self._target()
        spec = self._spec_of(obj)
        key = None if obj is None else obj.kind
        retarget = obj is not self._obj
        shown = self._fingerprint(obj)
        if not retarget and key == self._key and spec is self._spec and shown == self._shown:
            return
        self._shown = shown
        self._obj = obj
        paged = False
        if key != self._key or spec is not self._spec:
            self._key = key
            self._spec = spec
            self._show_page()
            paged = True
        has = obj is not None
        rows = has and self.object_page is not None
        self.header.setVisible(has)
        self.summary_label.setVisible(has and obj.kind == "polygon")
        self.scroll.setVisible(rows)
        self.empty_label.setVisible(not has)
        self._filler.setVisible(has and not rows)
        if has:
            self._load(obj, retarget or paged)
        else:
            self.error_label.setVisible(False)

    def _show_page(self) -> None:
        old = self.object_page
        if old is not None:
            old.hide()
        self.object_editors = {}
        self.object_rows = {}
        self.object_groups = {}
        self.object_page = None
        spec = self._spec
        if spec is None or not spec.params:
            return
        entry = self._pages.get(spec.id)
        if entry is not None and entry[0] is not spec:
            entry[1].setParent(None)
            entry[1].deleteLater()
            entry = None
        if entry is None:
            entry = self._build_page(spec)
            self._pages[spec.id] = entry
        _spec, page, editors, rows, groups = entry
        self.object_editors = editors
        self.object_rows = rows
        self.object_groups = groups
        self.object_page = page
        page.show()

    def _build_page(self, spec) -> tuple:
        self.rebuild_count += 1
        editors: dict[str, ParamEditor] = {}
        rows: dict[str, FieldRow] = {}
        page = QWidget(self.object_host)
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        titles = list(dict.fromkeys(p.group for p in spec.params))
        groups: dict[str, CollapsibleGroup] = {}
        for param in spec.params:
            group = groups.get(param.group)
            if group is None:
                group = self._make_group(spec.id, param.group, page, not groups, len(titles) > 1)
                groups[param.group] = group
                pl.addWidget(group)
            editor = ParamEditor(param, page)
            editor.edited.connect(self._on_param)
            row = self._row(param.label, editor)
            row.setToolTip(param.label)
            self._hook_row_menu(param.key, row, editor)
            group.add_widget(row)
            editors[param.key] = editor
            rows[param.key] = row
        page.hide()
        self.object_host_layout.addWidget(page)
        return (spec, page, editors, rows, groups)

    def _make_group(self, spec_id: str, title: str, page: QWidget, first: bool,
                    several: bool) -> CollapsibleGroup:
        if first:
            group = CollapsibleGroup(title, page, separator=several)
            group.header.setVisible(False)
        else:
            state = (spec_id, title)
            group = CollapsibleGroup(title, page, expanded=self._expanded.get(state, True))
            group.toggled.connect(partial(self._store_expanded, state))
        group.content_layout().setSpacing(GROUP_SPACING)
        return group

    def _store_expanded(self, state: tuple[str, str], expanded: bool) -> None:
        self._expanded[state] = bool(expanded)

    def _hook_row_menu(self, key: str, row: QWidget, editor: ParamEditor) -> None:
        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(partial(self._on_row_menu, key, row))
        for child in row.findChildren(QWidget):
            if isinstance(child, QLineEdit) and child in editor.widgets:
                continue
            child.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def _on_row_menu(self, key: str, row: QWidget, pos) -> None:
        from quartz_studio.widgets import context_menu

        obj = self._live()
        if obj is None:
            return
        menu = context_menu.build_param_menu(self._scene, obj, key, self)
        self.context_menu = context_menu.show_menu(menu, row.mapToGlobal(pos))

    def _load(self, obj, force: bool, force_key: str | None = None) -> None:
        self.header.set_object(self._type_text(obj), obj.name, *self._icon_for(obj))
        error = getattr(obj, "error", "") or ""
        self.error_label.setText(error)
        self.error_label.setVisible(bool(error))
        if obj.kind == "polygon":
            text = mesh_summary(obj.mesh)
            if self.summary_label.text() != text:
                self.summary_label.setText(text)
        self._load_params(obj, force, force_key)

    def _load_params(self, obj, force: bool, force_key: str | None = None) -> None:
        for key, editor in self.object_editors.items():
            param = editor.param
            value = obj.params.get(key, param.default)
            editor.set_value(value, force or key == force_key)
        self._apply_applicable(obj)

    def param_applies(self, key: str, obj=None) -> bool:
        obj = obj if obj is not None else self._obj
        spec = self._spec
        if obj is None or spec is None:
            return False
        param = spec.param(key)
        if param is None:
            return False
        if param.kind == "choice" and len(param.choices) < 2:
            return False
        values = {**spec.defaults(), **obj.params}
        visible = getattr(param, "visible", None)
        if callable(visible) and not visible(values):
            return False
        rules = getattr(spec, "applies", None) or {}
        rule = rules.get(key) or PARAM_APPLIES.get(spec.id, {}).get(key)
        if rule is None:
            return True
        return bool(rule(values))

    def _apply_applicable(self, obj) -> None:
        shown: dict[str, bool] = {}
        for key, row in self.object_rows.items():
            applies = self.param_applies(key, obj)
            row.setVisible(applies)
            group = self.object_editors[key].param.group
            shown[group] = shown.get(group, False) or applies
        for title, group in self.object_groups.items():
            group.setVisible(shown.get(title, False))

    def _live(self):
        obj = self._obj
        if obj is None or obj is not self._scene.active:
            return None
        return obj

    def _on_param(self, key: str, value) -> None:
        obj = self._live()
        if obj is None:
            return
        self._editing = True
        try:
            self._scene.set_param(obj, key, value)
        except (ValueError, TypeError, KeyError):
            pass
        finally:
            self._editing = False
        self._shown = self._fingerprint(obj)
        self._load(obj, False, key)
