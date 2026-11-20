from __future__ import annotations

import copy

from PySide6.QtCore import QLocale, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSizePolicy, QSlider, QSpinBox, QVBoxLayout,
                               QWidget)

from .. import theme
from ..widgets.common import FieldRow, prepare_combo
from .colorutil import from_hex, to_hex
from .params import Param, coerce
from .ramp import add_stop, normalize_ramp, remove_stop

__all__ = [
    "FIELD_H",
    "ROW_INDENT",
    "LABEL_W",
    "IMAGE_FILTER",
    "ColorButton",
    "FloatField",
    "VecField",
    "PathField",
    "RampBar",
    "RampEditor",
    "ParamForm",
    "PreviewLabel",
    "make_row",
    "style_surface",
]

FIELD_H = 24
ROW_INDENT = 8
LABEL_W = 112
SPIN_W = 72
SWATCH_W = 48
PLAIN_LOCALE = QLocale.c()
PLAIN_LOCALE.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff *.webp);;All Files (*)"


def make_row(label: str, editor: QWidget, parent: QWidget | None = None) -> FieldRow:
    row = FieldRow(label, editor, parent, label_width=LABEL_W, indent=ROW_INDENT)
    return row


class ColorButton(QPushButton):

    colorChanged = Signal(list)

    def __init__(self, color=(0.8, 0.8, 0.8), parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = [float(c) for c in color][:3]
        self.setFixedHeight(FIELD_H)
        self.setMinimumWidth(SWATCH_W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self.pick)
        self._sync_tip()

    def color(self) -> list:
        return list(self._color)

    def set_color(self, color, emit: bool = False) -> None:
        new = [min(max(float(c), 0.0), 1.0e4) for c in list(color)[:3]]
        if new == self._color:
            return
        self._color = new
        self._sync_tip()
        self.update()
        if emit:
            self.colorChanged.emit(self.color())

    def _sync_tip(self) -> None:
        self.setToolTip(to_hex(self._color))

    def pick(self) -> None:
        initial = QColor(to_hex(self._color))
        chosen = QColorDialog.getColor(initial, self, "Pick Color")
        if chosen.isValid():
            self.set_color(from_hex(chosen.name()), emit=True)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(theme.HAIRLINE_STRONG if self.underMouse() else theme.HAIRLINE), 1))
        p.setBrush(QColor(to_hex([min(c, 1.0) for c in self._color])))
        p.drawRoundedRect(r, theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(SWATCH_W * 2, FIELD_H)


class FloatField(QWidget):

    valueChanged = Signal(float)

    STEPS = 1000

    def __init__(self, value: float = 0.0, minimum: float = 0.0, maximum: float = 1.0,
                 step: float = 0.01, soft_max: float | None = None, decimals: int = 3,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.spin = QDoubleSpinBox(self)
        self.spin.setLocale(PLAIN_LOCALE)
        self.spin.setDecimals(decimals)
        self.spin.setRange(float(minimum), float(maximum))
        self.spin.setSingleStep(float(step))
        self.spin.setFixedWidth(SPIN_W)
        self.spin.setFixedHeight(FIELD_H)
        self.spin.setKeyboardTracking(False)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(0, self.STEPS)
        self.slider.setMinimumWidth(32)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._lo = float(minimum)
        self._hi = float(soft_max if soft_max is not None else maximum)
        if self._hi <= self._lo:
            self._hi = self._lo + 1.0
        lay.addWidget(self.spin)
        lay.addWidget(self.slider, 1)
        self._block = False
        self.spin.valueChanged.connect(self._from_spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.set_value(value)

    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, value: float, emit: bool = False) -> None:
        self._block = True
        self.spin.setValue(float(value))
        self._sync_slider()
        self._block = False
        if emit:
            self.valueChanged.emit(self.value())

    def _sync_slider(self) -> None:
        t = (self.spin.value() - self._lo) / (self._hi - self._lo)
        self.slider.setValue(int(round(min(max(t, 0.0), 1.0) * self.STEPS)))

    def _from_spin(self, value: float) -> None:
        if self._block:
            return
        self._block = True
        self._sync_slider()
        self._block = False
        self.valueChanged.emit(float(value))

    def _from_slider(self, pos: int) -> None:
        if self._block:
            return
        value = self._lo + (self._hi - self._lo) * pos / self.STEPS
        self._block = True
        self.spin.setValue(value)
        self._block = False
        self.valueChanged.emit(self.value())


class VecField(QWidget):

    valueChanged = Signal(list)

    def __init__(self, value=(0.0, 0.0), step: float = 0.01, minimum: float = -1.0e6,
                 maximum: float = 1.0e6, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.spins: list[QDoubleSpinBox] = []
        for _ in range(len(value)):
            s = QDoubleSpinBox(self)
            s.setLocale(PLAIN_LOCALE)
            s.setMinimumWidth(SWATCH_W)
            s.setDecimals(3)
            s.setRange(minimum, maximum)
            s.setSingleStep(step)
            s.setFixedHeight(FIELD_H)
            s.setKeyboardTracking(False)
            s.valueChanged.connect(self._changed)
            lay.addWidget(s, 1)
            self.spins.append(s)
        self._block = False
        self.set_value(value)

    def value(self) -> list:
        return [float(s.value()) for s in self.spins]

    def set_value(self, value, emit: bool = False) -> None:
        self._block = True
        for s, v in zip(self.spins, value):
            s.setValue(float(v))
        self._block = False
        if emit:
            self.valueChanged.emit(self.value())

    def _changed(self, _v: float) -> None:
        if not self._block:
            self.valueChanged.emit(self.value())


class PathField(QWidget):

    pathChanged = Signal(str)

    def __init__(self, path: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = QLineEdit(path, self)
        self.edit.setFixedHeight(FIELD_H)
        self.edit.setPlaceholderText("Image file")
        self.button = QPushButton("Browse", self)
        self.button.setFixedHeight(FIELD_H)
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.button)
        self.edit.editingFinished.connect(lambda: self.pathChanged.emit(self.edit.text().strip()))
        self.button.clicked.connect(self.browse)

    def path(self) -> str:
        return self.edit.text().strip()

    def set_path(self, path: str, emit: bool = False) -> None:
        self.edit.setText(path or "")
        if emit:
            self.pathChanged.emit(self.path())

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose Image", self.path(), IMAGE_FILTER)
        if path:
            self.set_path(path, emit=True)


class RampBar(QWidget):

    stopMoved = Signal(int, float)
    stopSelected = Signal(int)
    stopAdded = Signal(float)

    MARK = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.stops: list = normalize_ramp(None)
        self.current = 0
        self._drag: int | None = None
        self.setFixedHeight(FIELD_H + self.MARK + 4)
        self.setMinimumWidth(128)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_stops(self, stops, current: int | None = None) -> None:
        self.stops = normalize_ramp(stops)
        if current is not None:
            self.current = current
        self.current = min(max(self.current, 0), len(self.stops) - 1)
        self.update()

    def _bar(self) -> QRectF:
        return QRectF(self.MARK, 2, max(self.width() - 2 * self.MARK, 1), FIELD_H - 4)

    def x_of(self, pos: float) -> float:
        bar = self._bar()
        return bar.left() + bar.width() * pos

    def pos_of(self, x: float) -> float:
        bar = self._bar()
        return min(max((x - bar.left()) / bar.width(), 0.0), 1.0)

    def stop_at(self, x: float) -> int | None:
        best, dist = None, float(self.MARK)
        for i, (pos, _c) in enumerate(self.stops):
            d = abs(self.x_of(pos) - x)
            if d <= dist:
                best, dist = i, d
        return best

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = self._bar()
        grad = QLinearGradient(bar.topLeft(), bar.topRight())
        for pos, col in self.stops:
            c = QColor.fromRgbF(*[min(max(x, 0.0), 1.0) for x in col[:3]])
            grad.setColorAt(pos, c)
        p.setPen(QPen(QColor(theme.HAIRLINE), 1))
        p.setBrush(grad)
        p.drawRoundedRect(bar, 4, 4)
        for i, (pos, col) in enumerate(self.stops):
            x = self.x_of(pos)
            y = bar.bottom() + 2
            path = QPainterPath(QPointF(x, y))
            path.lineTo(x - self.MARK / 2, y + self.MARK)
            path.lineTo(x + self.MARK / 2, y + self.MARK)
            path.closeSubpath()
            p.setPen(QPen(QColor(theme.ACCENT if i == self.current else theme.TEXT_SECONDARY), 1))
            p.setBrush(QColor.fromRgbF(*[min(max(v, 0.0), 1.0) for v in col[:3]]))
            p.drawPath(path)
        p.end()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        x = e.position().x()
        hit = self.stop_at(x)
        if hit is not None:
            self.current = hit
            self._drag = hit
            self.stopSelected.emit(hit)
            self.update()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag is not None:
            self.stopMoved.emit(self._drag, self.pos_of(e.position().x()))

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag = None

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if self.stop_at(e.position().x()) is None:
            self.stopAdded.emit(self.pos_of(e.position().x()))


class RampEditor(QWidget):

    rampChanged = Signal(list)

    def __init__(self, stops=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(ROW_INDENT, 0, ROW_INDENT, 0)
        lay.setSpacing(4)
        self.bar = RampBar(self)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.position = QDoubleSpinBox(self)
        self.position.setLocale(PLAIN_LOCALE)
        self.position.setRange(0.0, 1.0)
        self.position.setDecimals(3)
        self.position.setSingleStep(0.01)
        self.position.setFixedSize(SPIN_W, FIELD_H)
        self.position.setKeyboardTracking(False)
        self.color = ColorButton((1.0, 1.0, 1.0), self)
        self.alpha = QDoubleSpinBox(self)
        self.alpha.setLocale(PLAIN_LOCALE)
        self.alpha.setRange(0.0, 1.0)
        self.alpha.setDecimals(3)
        self.alpha.setSingleStep(0.05)
        self.alpha.setFixedSize(SWATCH_W, FIELD_H)
        self.alpha.setKeyboardTracking(False)
        self.alpha.setToolTip("Alpha")
        self.add_button = QPushButton("Add", self)
        self.remove_button = QPushButton("Remove", self)
        for b in (self.add_button, self.remove_button):
            b.setFixedHeight(FIELD_H)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self.position)
        row.addWidget(self.color, 1)
        row.addWidget(self.alpha)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        lay.addLayout(row)
        self._block = False
        self.bar.stopSelected.connect(lambda _i: self._sync_controls())
        self.bar.stopMoved.connect(self.move_stop)
        self.bar.stopAdded.connect(self.add_at)
        self.position.valueChanged.connect(lambda v: self.move_stop(self.bar.current, v))
        self.color.colorChanged.connect(self._set_color)
        self.alpha.valueChanged.connect(self._set_alpha)
        self.add_button.clicked.connect(self._add_mid)
        self.remove_button.clicked.connect(self.remove_current)
        self.set_stops(stops if stops is not None else normalize_ramp(None))

    def stops(self) -> list:
        return copy.deepcopy(self.bar.stops)

    def set_stops(self, stops, current: int | None = None) -> None:
        self.bar.set_stops(stops, current)
        self._sync_controls()

    def _sync_controls(self) -> None:
        self._block = True
        pos, col = self.bar.stops[self.bar.current]
        self.position.setValue(pos)
        self.color.set_color(col[:3])
        self.alpha.setValue(col[3] if len(col) > 3 else 1.0)
        self.remove_button.setEnabled(len(self.bar.stops) > 1)
        self._block = False

    def _emit(self, stops: list, current_pos: float | None = None, current_col=None) -> None:
        stops = normalize_ramp(stops)
        current = 0
        for i, (pos, col) in enumerate(stops):
            if current_pos is not None and abs(pos - current_pos) < 1e-12 and (current_col is None or col == current_col):
                current = i
                break
        self.bar.set_stops(stops, current)
        self._sync_controls()
        self.rampChanged.emit(self.stops())

    def move_stop(self, index: int, position: float) -> None:
        if self._block or not 0 <= index < len(self.bar.stops):
            return
        stops = self.stops()
        stops[index][0] = float(min(max(position, 0.0), 1.0))
        moved = stops[index]
        self._emit(stops, moved[0], moved[1])
        self.bar._drag = self.bar.current if self.bar._drag is not None else None

    def _set_color(self, color: list) -> None:
        if self._block:
            return
        stops = self.stops()
        stops[self.bar.current][1][:3] = [float(c) for c in color]
        self._emit(stops, stops[self.bar.current][0], stops[self.bar.current][1])

    def _set_alpha(self, value: float) -> None:
        if self._block:
            return
        stops = self.stops()
        stops[self.bar.current][1][3] = float(value)
        self._emit(stops, stops[self.bar.current][0], stops[self.bar.current][1])

    def add_at(self, position: float) -> None:
        stops = add_stop(self.stops(), position)
        added = [s for s in stops if abs(s[0] - position) < 1e-12]
        self._emit(stops, position, added[0][1] if added else None)

    def _add_mid(self) -> None:
        stops = self.stops()
        i = self.bar.current
        if i + 1 < len(stops):
            pos = (stops[i][0] + stops[i + 1][0]) / 2.0
        elif i > 0:
            pos = (stops[i][0] + stops[i - 1][0]) / 2.0
        else:
            pos = 0.5 if stops[i][0] != 0.5 else 0.25
        self.add_at(pos)

    def remove_current(self) -> None:
        if len(self.bar.stops) <= 1:
            return
        stops = remove_stop(self.stops(), self.bar.current)
        self.bar.current = max(0, self.bar.current - 1)
        self.bar.set_stops(stops)
        self._sync_controls()
        self.rampChanged.emit(self.stops())


class ParamForm(QWidget):

    changed = Signal(str, object)

    def __init__(self, params, values: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.params: tuple[Param, ...] = tuple(params)
        self.editors: dict[str, QWidget] = {}
        self.rows: dict[str, QWidget] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._block = False
        for p in self.params:
            editor = self._make_editor(p)
            self.editors[p.key] = editor
            if p.kind == "ramp":
                label = QLabel(p.label, self)
                label.setObjectName("qsDimLabel")
                label.setContentsMargins(ROW_INDENT, 0, 0, 0)
                box = QWidget(self)
                bl = QVBoxLayout(box)
                bl.setContentsMargins(0, 0, 0, 0)
                bl.setSpacing(4)
                bl.addWidget(label)
                bl.addWidget(editor)
                self.rows[p.key] = box
                lay.addWidget(box)
            else:
                row = make_row(p.label, editor, self)
                self.rows[p.key] = row
                lay.addWidget(row)
        self.set_values(values or {})

    def _emit(self, key: str, value) -> None:
        if not self._block:
            self.changed.emit(key, value)

    def _make_editor(self, p: Param) -> QWidget:
        if p.kind == "float":
            lo = p.minimum if p.minimum is not None else -1.0e6
            hi = p.maximum if p.maximum is not None else 1.0e6
            soft = p.soft_max if p.soft_max is not None else (hi if hi < 1.0e5 else lo + 1.0)
            w = FloatField(p.default or 0.0, lo, hi, p.step, soft)
            w.valueChanged.connect(lambda v, k=p.key: self._emit(k, float(v)))
            return w
        if p.kind == "int":
            w = QSpinBox()
            w.setLocale(PLAIN_LOCALE)
            w.setRange(int(p.minimum if p.minimum is not None else -10 ** 6),
                       int(p.maximum if p.maximum is not None else 10 ** 6))
            w.setFixedHeight(FIELD_H)
            w.setKeyboardTracking(False)
            w.valueChanged.connect(lambda v, k=p.key: self._emit(k, int(v)))
            return w
        if p.kind == "color":
            w = ColorButton(p.default or (0.0, 0.0, 0.0))
            w.colorChanged.connect(lambda v, k=p.key: self._emit(k, list(v)))
            return w
        if p.kind == "enum":
            w = QComboBox()
            for opt, label in zip(p.options, p.labels()):
                w.addItem(label, opt)
            w.setFixedHeight(FIELD_H)
            w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            prepare_combo(w)
            w.currentIndexChanged.connect(lambda i, k=p.key, cb=w: self._emit(k, cb.itemData(i)))
            return w
        if p.kind == "bool":
            w = QCheckBox()
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            w.toggled.connect(lambda v, k=p.key: self._emit(k, bool(v)))
            return w
        if p.kind in ("vec2", "vec3"):
            w = VecField(p.default or ((0.0, 0.0) if p.kind == "vec2" else (0.0, 0.0, 0.0)), p.step)
            w.valueChanged.connect(lambda v, k=p.key: self._emit(k, list(v)))
            return w
        if p.kind == "path":
            w = PathField(p.default or "")
            w.pathChanged.connect(lambda v, k=p.key: self._emit(k, str(v)))
            return w
        if p.kind == "ramp":
            w = RampEditor(p.default)
            w.rampChanged.connect(lambda v, k=p.key: self._emit(k, v))
            return w
        w = QLineEdit(str(p.default or ""))
        w.setFixedHeight(FIELD_H)
        w.editingFinished.connect(lambda k=p.key, e=w: self._emit(k, e.text()))
        return w

    def value(self, key: str):
        w = self.editors[key]
        p = next(p for p in self.params if p.key == key)
        if p.kind == "float":
            return w.value()
        if p.kind == "int":
            return int(w.value())
        if p.kind == "color":
            return w.color()
        if p.kind == "enum":
            return w.currentData()
        if p.kind == "bool":
            return w.isChecked()
        if p.kind in ("vec2", "vec3"):
            return w.value()
        if p.kind == "path":
            return w.path()
        if p.kind == "ramp":
            return w.stops()
        return w.text()

    def set_values(self, values: dict) -> None:
        self._block = True
        try:
            for p in self.params:
                if p.key not in values and p.default is None:
                    continue
                value = coerce(p, values.get(p.key, p.default))
                w = self.editors[p.key]
                if p.kind == "float":
                    w.set_value(value)
                elif p.kind == "int":
                    w.setValue(int(value))
                elif p.kind == "color":
                    w.set_color(value)
                elif p.kind == "enum":
                    i = w.findData(value)
                    w.setCurrentIndex(max(i, 0))
                elif p.kind == "bool":
                    w.setChecked(bool(value))
                elif p.kind in ("vec2", "vec3"):
                    w.set_value(value)
                elif p.kind == "path":
                    w.set_path(value)
                elif p.kind == "ramp":
                    w.set_stops(value)
                else:
                    w.setText(str(value))
        finally:
            self._block = False

    def set_value(self, key: str, value, emit: bool = True) -> None:
        self.set_values({key: value})
        if emit:
            self.changed.emit(key, self.value(key))


class PreviewLabel(QLabel):

    def __init__(self, size: int = 128, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview_size = int(size)
        self.setFixedSize(self.preview_size, self.preview_size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_image(self, image) -> None:
        if image is None:
            self.clear()
            return
        self.setPixmap(QPixmap.fromImage(image))


def style_surface(widget: QWidget, name: str) -> QWidget:
    widget.setObjectName(name)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setStyleSheet(f"QWidget#{name} {{ background: {theme.SURFACE_CARD}; }}")
    return widget
