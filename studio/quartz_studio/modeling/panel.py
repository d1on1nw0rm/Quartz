from __future__ import annotations

from PySide6.QtCore import QLocale, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
                               QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox,
                               QStyle, QStyleOptionSpinBox, QVBoxLayout, QWidget)

from .. import theme
from ..widgets.common import CollapsibleGroup, FieldRow, header_font, prepare_combo
from .registry import Param, ToolSpec, get_tool
from .session import ModelingController

__all__ = ["ScrubSpin", "ScrubIntSpin", "ToolOptionsPanel"]

LABEL_WIDTH = 118
ROW_INDENT = 14
SCRUB_PX = 4.0


def _plain_locale() -> QLocale:
    loc = QLocale.c()
    loc.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    return loc


def _unit_suffix(param: Param) -> str:
    if param.kind == "distance":
        return " cm"
    if param.kind == "angle":
        return " °"
    if param.kind == "percent":
        return " %"
    return f" {param.unit}" if param.unit else ""


class _ScrubMixin:

    def _init_scrub(self) -> None:
        self._scrub_origin: QPoint | None = None
        self._scrub_start = 0.0
        self._scrubbed = False

    def _on_arrows(self, pos: QPoint) -> bool:
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        style = self.style()
        up = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                  QStyle.SubControl.SC_SpinBoxUp, self)
        down = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                    QStyle.SubControl.SC_SpinBoxDown, self)
        return up.contains(pos) or down.contains(pos)

    def _scrub_press(self, e: QMouseEvent) -> bool:
        if e.button() == Qt.MouseButton.LeftButton and self._on_arrows(e.position().toPoint()):
            self._scrub_origin = e.globalPosition().toPoint()
            self._scrub_start = float(self.value())
            self._scrubbed = False
            return True
        return False

    def _scrub_move(self, e: QMouseEvent) -> bool:
        if self._scrub_origin is None:
            return False
        delta = e.globalPosition().toPoint() - self._scrub_origin
        amount = (delta.x() - delta.y()) / SCRUB_PX
        if abs(amount) >= 1.0 or self._scrubbed:
            self._scrubbed = True
            self.setValue(self._scrub_start + amount * self.singleStep())
        return True

    def _scrub_release(self, e: QMouseEvent) -> bool:
        if self._scrub_origin is None:
            return False
        origin, self._scrub_origin = self._scrub_origin, None
        if not self._scrubbed:
            local = self.mapFromGlobal(origin)
            opt = QStyleOptionSpinBox()
            self.initStyleOption(opt)
            up = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                             QStyle.SubControl.SC_SpinBoxUp, self)
            self.stepBy(1 if up.contains(local) else -1)
        self.editingFinished.emit()
        return True


class ScrubSpin(_ScrubMixin, QDoubleSpinBox):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_scrub()
        self.setLocale(_plain_locale())
        self.setKeyboardTracking(False)
        self.setAccelerated(True)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setFixedHeight(theme.FIELD_H)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if not self._scrub_press(e):
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if not self._scrub_move(e):
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if not self._scrub_release(e):
            super().mouseReleaseEvent(e)

    def wheelEvent(self, e) -> None:
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class ScrubIntSpin(_ScrubMixin, QSpinBox):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_scrub()
        self.setLocale(_plain_locale())
        self.setKeyboardTracking(False)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setFixedHeight(theme.FIELD_H)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if not self._scrub_press(e):
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if not self._scrub_move(e):
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if not self._scrub_release(e):
            super().mouseReleaseEvent(e)

    def wheelEvent(self, e) -> None:
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


def _range(param: Param, lo_default: float, hi_default: float) -> tuple[float, float]:
    lo = param.minimum if param.minimum is not None else lo_default
    hi = param.maximum if param.maximum is not None else hi_default
    return float(lo), float(hi)


class _ParamEditor(QWidget):

    edited = Signal(str, object)

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.param = param
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.widgets: list[QWidget] = []
        kind = param.kind
        if kind == "bool":
            box = QCheckBox(self)
            box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            box.toggled.connect(lambda v: self.edited.emit(param.key, bool(v)))
            lay.addWidget(box)
            lay.addStretch(1)
            self.widgets.append(box)
        elif kind == "choice":
            combo = prepare_combo(QComboBox(self))
            combo.addItems(list(param.choices))
            combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            combo.activated.connect(lambda i, c=combo: self.edited.emit(param.key, c.itemText(i)))
            lay.addWidget(combo, 1)
            self.widgets.append(combo)
        elif kind == "int":
            spin = ScrubIntSpin(self)
            lo, hi = _range(param, -1_000_000, 1_000_000)
            spin.setRange(int(lo), int(hi))
            spin.setSingleStep(max(1, int(param.step)))
            spin.setSuffix(_unit_suffix(param))
            spin.valueChanged.connect(lambda v: self.edited.emit(param.key, int(v)))
            lay.addWidget(spin, 1)
            self.widgets.append(spin)
        elif kind == "vector":
            for axis, label in enumerate("XYZ"):
                tag = QLabel(label, self)
                tag.setObjectName("qsDimLabel")
                lay.addWidget(tag)
                spin = ScrubSpin(self)
                lo, hi = _range(param, -1e6, 1e6)
                spin.setRange(lo, hi)
                spin.setDecimals(3 if param.unit in ("", "x") else 2)
                spin.setSingleStep(param.step)
                spin.setSuffix(f" {param.unit}" if param.unit else "")
                spin.valueChanged.connect(lambda _v, s=self: s._emit_vector())
                lay.addWidget(spin, 1)
                self.widgets.append(spin)
        else:
            spin = ScrubSpin(self)
            lo, hi = _range(param, -1e6, 1e6)
            spin.setRange(lo, hi)
            spin.setDecimals(1 if kind in ("percent", "angle") else 3 if kind == "float" else 2)
            spin.setSingleStep(param.step)
            spin.setSuffix(_unit_suffix(param))
            spin.valueChanged.connect(lambda v: self.edited.emit(param.key, float(v)))
            lay.addWidget(spin, 1)
            self.widgets.append(spin)

    def _emit_vector(self) -> None:
        self.edited.emit(self.param.key, tuple(float(w.value()) for w in self.widgets))

    def set_value(self, value) -> None:
        kind = self.param.kind
        for w in self.widgets:
            w.blockSignals(True)
        try:
            if kind == "bool":
                self.widgets[0].setChecked(bool(value))
            elif kind == "choice":
                i = self.widgets[0].findText(str(value))
                self.widgets[0].setCurrentIndex(max(0, i))
            elif kind == "vector":
                vals = tuple(value) if value is not None else (0.0, 0.0, 0.0)
                for w, v in zip(self.widgets, vals):
                    w.setValue(float(v))
            elif kind == "int":
                self.widgets[0].setValue(int(value))
            else:
                self.widgets[0].setValue(float(value))
        finally:
            for w in self.widgets:
                w.blockSignals(False)

    def value(self):
        kind = self.param.kind
        if kind == "bool":
            return self.widgets[0].isChecked()
        if kind == "choice":
            return self.widgets[0].currentText()
        if kind == "vector":
            return tuple(float(w.value()) for w in self.widgets)
        if kind == "int":
            return int(self.widgets[0].value())
        return float(self.widgets[0].value())


class ToolOptionsPanel(QWidget):

    closed = Signal()

    def __init__(self, controller: ModelingController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("qsToolOptions")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QLabel#qsToolTitle {{ color: {theme.TEXT_SECONDARY}; }}"
                           "QPushButton#qsToolButton { padding: 2px 10px; }")
        self.setMinimumHeight(160)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget(self)
        head.setFixedHeight(theme.CARD_HEADER_H)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(theme.SPACE_3 + theme.SPACE_2, 0, theme.SPACE_3, 0)
        self.title = QLabel("", head)
        self.title.setObjectName("qsToolTitle")
        self.title.setFont(header_font(self.title.font()))
        hl.addWidget(self.title, 1)
        self.mode_hint = QLabel("", head)
        self.mode_hint.setObjectName("qsDimLabel")
        hl.addWidget(self.mode_hint)
        lay.addWidget(head)
        rule = QFrame(self)
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {theme.HAIRLINE};")
        lay.addWidget(rule)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self.scroll, 1)

        foot = QWidget(self)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(8, 4, 8, 6)
        fl.setSpacing(6)
        self.realtime = QCheckBox("Realtime Update", foot)
        self.realtime.setChecked(True)
        self.realtime.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        fl.addWidget(self.realtime)
        fl.addStretch(1)
        self.apply_button = QPushButton("Apply", foot)
        self.new_button = QPushButton("New Transform", foot)
        self.reset_button = QPushButton("Reset Values", foot)
        for b in (self.apply_button, self.new_button, self.reset_button):
            b.setObjectName("qsToolButton")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            fl.addWidget(b)
        lay.addWidget(foot)

        self.apply_button.clicked.connect(self._on_apply)
        self.new_button.clicked.connect(self._on_new_transform)
        self.reset_button.clicked.connect(controller.reset_values)

        self.editors: dict[str, _ParamEditor] = {}
        self.rows: dict[str, FieldRow] = {}
        self._spec: ToolSpec | None = None
        controller.toolChanged.connect(self._on_tool)
        controller.paramsChanged.connect(self._on_params)
        controller.scene.modeChanged.connect(lambda *_: self._sync_rows())
        self._on_tool(controller.tool_id or "")

    def sizeHint(self) -> QSize:
        return QSize(300, 300)

    def spec(self) -> ToolSpec | None:
        return self._spec

    def _on_tool(self, tool_id: str) -> None:
        self._spec = get_tool(tool_id) if tool_id else None
        self._build()
        self.setVisible(self._spec is not None)

    def _build(self) -> None:
        self.editors.clear()
        self.rows.clear()
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 2, 0, 6)
        bl.setSpacing(1)
        spec = self._spec
        if spec is None:
            self.title.setText("")
            self.scroll.setWidget(body)
            return
        self.title.setText(spec.name)
        self.mode_hint.setText(" / ".join(m.capitalize() for m in spec.modes))
        groups: dict[str, CollapsibleGroup] = {}
        for param in spec.params:
            if param.kind == "runtime":
                continue
            group = groups.get(param.group)
            if group is None:
                group = CollapsibleGroup(param.group, body)
                group.content_layout().setSpacing(2)
                groups[param.group] = group
                bl.addWidget(group)
            editor = _ParamEditor(param)
            editor.edited.connect(self._on_edited)
            row = FieldRow(param.label, editor, label_width=LABEL_WIDTH, indent=ROW_INDENT)
            row.setToolTip(param.label)
            group.add_widget(row)
            self.editors[param.key] = editor
            self.rows[param.key] = row
        bl.addStretch(1)
        self.scroll.setWidget(body)
        self.apply_button.setText("Apply" if spec.interactive else "Apply Again")
        self.new_button.setVisible(spec.interactive)
        self._on_params(self.controller.params())
        self._sync_rows()

    def _sync_rows(self) -> None:
        mode = self.controller.scene.mode
        for key, row in self.rows.items():
            param = self.editors[key].param
            row.setVisible(not param.modes or mode in param.modes)

    def _on_params(self, values: dict) -> None:
        for key, value in values.items():
            editor = self.editors.get(key)
            if editor is not None:
                editor.set_value(value)

    def _on_edited(self, key: str, value) -> None:
        if self.realtime.isChecked():
            self.controller.set_param(key, value)
            return
        tool = self.controller.tool_id
        if tool is not None:
            merged = self.controller.params()
            merged[key] = value
            self.controller.values[tool] = get_tool(tool).clamp(merged)

    def _on_apply(self) -> None:
        controller = self.controller
        if controller.tool_id is None:
            return
        for key, editor in self.editors.items():
            controller.values.setdefault(controller.tool_id, controller.params())[key] = editor.value()
        controller.new_transform()
        controller.apply_once()

    def _on_new_transform(self) -> None:
        self.controller.new_transform()
