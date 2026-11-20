from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSlider,
                               QSpinBox, QToolButton, QVBoxLayout, QWidget)

from .. import theme
from ..widgets.common import CollapsibleGroup, FieldRow, header_font, prepare_combo
from . import data
from . import falloff as _falloff
from . import stamps as _stamps
from .brushes import BRUSH_ORDER, brush
from .icons import brush_icon
from .session import get_session

__all__ = ["FalloffCurveEditor", "SculptBrushPanel", "SculptLayersPanel", "stamp_pixmap"]

BRUSH_BUTTON = 40
BRUSH_ICON = 32
BRUSH_COLUMNS = 4
LABEL_W = 96
ROW_H = 24
GAP = 4
PAD = 8
PAD_SIDE = 12
CURVE_H = 96
CURVE_PAD = 8
POINT_D = 8
PICK_PX = 8
STAMP_PREVIEW = 48
LIST_H = 128
FRAME_W = 1
RADIUS_MAX = 4096
STABILIZE_MAX = 256


def _scene(scene):
    if scene is not None:
        return scene
    from ..scene import get_scene
    return get_scene()


def _row(label: str, editor: QWidget) -> FieldRow:
    row = FieldRow(label, editor, label_width=LABEL_W, indent=PAD_SIDE)
    row.setFixedHeight(ROW_H)
    return row


def _button(text: str, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setFixedHeight(ROW_H)
    if tip:
        b.setToolTip(tip)
    return b


def _check(text: str = "") -> QCheckBox:
    box = QCheckBox(text)
    box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return box


def _spin(lo: float, hi: float, decimals: int = 0, suffix: str = "", step: float = 1.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    s.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    s.setFixedHeight(ROW_H - GAP)
    return s


class _SliderField(QWidget):

    valueChanged = Signal(float)

    def __init__(self, lo: float, hi: float, decimals: int = 0, suffix: str = "",
                 parent: QWidget | None = None, power: float = 1.0) -> None:
        super().__init__(parent)
        self._power = max(1e-3, float(power))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GAP)
        self.spin = _spin(lo, hi, decimals, suffix)
        self.spin.setFixedWidth(LABEL_W - 16)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._lo, self._hi = float(lo), float(hi)
        self.slider.setRange(0, 1000)
        lay.addWidget(self.spin)
        lay.addWidget(self.slider, 1)
        self.spin.valueChanged.connect(self._from_spin)
        self.slider.valueChanged.connect(self._from_slider)

    def _position(self, v: float) -> int:
        f = min(1.0, max(0.0, (float(v) - self._lo) / max(1e-9, self._hi - self._lo)))
        return int(round(f ** (1.0 / self._power) * 1000))

    def _from_spin(self, v: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(self._position(v))
        self.slider.blockSignals(False)
        self.valueChanged.emit(float(v))

    def _from_slider(self, i: int) -> None:
        v = self._lo + (self._hi - self._lo) * (i / 1000.0) ** self._power
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.valueChanged.emit(float(self.spin.value()))

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, v: float) -> None:
        self.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(float(v))
        self.slider.setValue(self._position(v))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)
        self.blockSignals(False)


class FalloffCurveEditor(QWidget):

    edited = Signal(str, list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = "smooth"
        self.curve: list = [list(p) for p in _falloff.DEFAULT_CURVE]
        self._drag: int | None = None
        self.setFixedHeight(CURVE_H)
        self.setMinimumWidth(128)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setToolTip("Drag to edit the falloff, double-click to add a point, right-click to remove one")

    def sizeHint(self) -> QSize:
        return QSize(256, CURVE_H)

    def set_state(self, kind: str, curve) -> None:
        self.kind = kind if kind in _falloff.FALLOFFS else "smooth"
        self.curve = [list(p) for p in _falloff.clean_curve(curve)]
        self.update()

    def _plot(self) -> QRectF:
        return QRectF(self.rect()).adjusted(CURVE_PAD, CURVE_PAD, -CURVE_PAD, -CURVE_PAD)

    def to_widget(self, x: float, y: float) -> QPointF:
        r = self._plot()
        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def to_curve(self, pos: QPointF) -> tuple[float, float]:
        r = self._plot()
        x = (pos.x() - r.left()) / max(1.0, r.width())
        y = (r.bottom() - pos.y()) / max(1.0, r.height())
        return min(1.0, max(0.0, x)), min(1.0, max(0.0, y))

    def _pick(self, pos: QPointF) -> int | None:
        if self.kind != "custom":
            return None
        best, best_d = None, float(PICK_PX)
        for i, (x, y) in enumerate(self.curve):
            q = self.to_widget(x, y)
            d = ((q.x() - pos.x()) ** 2 + (q.y() - pos.y()) ** 2) ** 0.5
            if d <= best_d:
                best, best_d = i, d
        return best

    def _to_custom(self) -> None:
        if self.kind == "custom":
            return
        xs = np.linspace(0.0, 1.0, 5)
        ys = _falloff.evaluate(self.kind, xs, self.curve)
        self.curve = [[float(x), float(y)] for x, y in zip(xs, ys)]
        self.kind = "custom"

    def _emit(self) -> None:
        self.update()
        self.edited.emit(self.kind, [list(p) for p in self.curve])

    def mousePressEvent(self, e) -> None:
        pos = e.position()
        if e.button() == Qt.MouseButton.RightButton:
            i = self._pick(pos)
            if i is not None:
                self.curve = [list(p) for p in _falloff.remove_point(self.curve, i)]
                self._emit()
            e.accept()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        if self.kind != "custom":
            self._to_custom()
            self._emit()
        i = self._pick(pos)
        if i is None:
            x, y = self.to_curve(pos)
            self.curve = [list(p) for p in _falloff.insert_point(self.curve, x, y)]
            i = min(range(len(self.curve)), key=lambda k: abs(self.curve[k][0] - x))
            self._emit()
        self._drag = i
        e.accept()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is None:
            self.setCursor(Qt.CursorShape.PointingHandCursor if self._pick(e.position()) is not None
                           else Qt.CursorShape.CrossCursor)
            return
        x, y = self.to_curve(e.position())
        self.curve = [list(p) for p in _falloff.move_point(self.curve, self._drag, x, y)]
        self._emit()

    def mouseReleaseEvent(self, e) -> None:
        self._drag = None

    def mouseDoubleClickEvent(self, e) -> None:
        if self._pick(e.position()) is None:
            self._to_custom()
            x, y = self.to_curve(e.position())
            self.curve = [list(p) for p in _falloff.insert_point(self.curve, x, y)]
            self._emit()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.HAIRLINE))
        p.drawRoundedRect(QRectF(self.rect()), theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)
        p.setBrush(QColor(theme.SURFACE_FIELD))
        inner = theme.CONTROL_RADIUS
        p.drawRoundedRect(QRectF(self.rect()).adjusted(FRAME_W, FRAME_W, -FRAME_W, -FRAME_W), inner, inner)
        r = self._plot()
        p.setPen(QPen(QColor(theme.GRID_MINOR), 1))
        for k in range(1, 4):
            x = r.left() + r.width() * k / 4.0
            y = r.top() + r.height() * k / 4.0
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        pts = _falloff.sample(self.kind, 96, self.curve)
        path = QPainterPath(self.to_widget(*pts[0]))
        for x, y in pts[1:]:
            path.lineTo(self.to_widget(x, y))
        area = QPainterPath(path)
        area.lineTo(self.to_widget(1.0, 0.0))
        area.lineTo(self.to_widget(0.0, 0.0))
        area.closeSubpath()
        tint = QColor(theme.ACCENT)
        tint.setAlpha(40)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(tint)
        p.drawPath(area)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(theme.ACCENT), 2))
        p.drawPath(path)
        if self.kind == "custom":
            p.setPen(QPen(QColor(theme.SURFACE_FIELD), 2))
            p.setBrush(QColor(theme.TEXT_PRIMARY))
            for i, (x, y) in enumerate(self.curve):
                q = self.to_widget(x, y)
                if i == self._drag:
                    p.setBrush(QColor(theme.ACCENT_HOVER))
                p.drawEllipse(q, POINT_D / 2, POINT_D / 2)
                p.setBrush(QColor(theme.TEXT_PRIMARY))
        p.end()


def stamp_pixmap(image, size: int = STAMP_PREVIEW) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(theme.SURFACE_FIELD))
    if image is None:
        return pm
    arr = np.clip(np.asarray(image, float), 0.0, 1.0)
    g = (arr * 255).astype(np.uint8)
    h, w = g.shape
    g = np.ascontiguousarray(g)
    img = QImage(g.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    return QPixmap.fromImage(img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))


class _Header(QWidget):

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme.CARD_HEADER_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(PAD_SIDE, 0, PAD, 0)
        lay.setSpacing(GAP)
        self.title = QLabel(title, self)
        self.title.setFont(header_font(self.title.font()))
        self.title.setObjectName("qsGroupTitle")
        lay.addWidget(self.title, 1)
        self._layout = lay

    def add(self, w: QWidget) -> QWidget:
        self._layout.addWidget(w)
        return w


def _scroll_body(owner: QWidget) -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea(owner)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(0, GAP, 0, PAD)
    lay.setSpacing(0)
    scroll.setWidget(body)
    return scroll, lay


class SculptBrushPanel(QWidget):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = _scene(scene)
        self.session = get_session(self.scene)
        self.setObjectName("qsSculptBrushPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        head = _Header("Sculpt", self)
        self.mode_button = head.add(QPushButton("Sculpt Mode"))
        self.mode_button.setCheckable(True)
        self.mode_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mode_button.setFixedHeight(ROW_H)
        self.mode_button.toggled.connect(self.session.set_active)
        outer.addWidget(head)
        self.scroll, body = _scroll_body(self)
        outer.addWidget(self.scroll, 1)

        g = CollapsibleGroup("Brushes")
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, GAP)
        grid.setSpacing(GAP)
        self.brush_group = QButtonGroup(self)
        self.brush_group.setExclusive(True)
        self.brush_buttons: dict[str, QToolButton] = {}
        for i, bid in enumerate(BRUSH_ORDER):
            spec = brush(bid)
            b = QToolButton(grid_host)
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setFixedSize(BRUSH_BUTTON, BRUSH_BUTTON)
            b.setIcon(brush_icon(bid, BRUSH_ICON))
            b.setIconSize(QSize(BRUSH_ICON, BRUSH_ICON))
            b.setToolTip(f"{spec.label}: {spec.description}")
            b.setObjectName(f"qsSculptBrush_{bid}")
            self.brush_group.addButton(b)
            grid.addWidget(b, i // BRUSH_COLUMNS, i % BRUSH_COLUMNS)
            b.clicked.connect(lambda _c=False, x=bid: self.session.set_brush(x))
            self.brush_buttons[bid] = b
        grid.setColumnStretch(BRUSH_COLUMNS, 1)
        g.add_widget(grid_host)
        self.brush_label = QLabel("")
        self.brush_label.setObjectName("qsDimLabel")
        self.brush_label.setContentsMargins(PAD_SIDE, 0, PAD_SIDE, 0)
        self.brush_label.setWordWrap(True)
        g.add_widget(self.brush_label)
        self.block_info = QLabel("")
        self.block_info.setObjectName("qsWarningLabel")
        self.block_info.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, 0)
        self.block_info.setWordWrap(True)
        self.block_info.setStyleSheet(f"color: {theme.TINT_ROSE};")
        self.block_info.setVisible(False)
        g.add_widget(self.block_info)
        body.addWidget(g)

        g = CollapsibleGroup("Settings")
        self.radius = _SliderField(1, RADIUS_MAX, 0, " px", power=2.0)
        self.strength = _SliderField(0, 100, 0, " %")
        self.spacing = _SliderField(0, 200, 0, " %")
        self.smooth_strength = _SliderField(0, 100, 0, " %")
        self.stabilize = _SliderField(0, STABILIZE_MAX, 0, " px")
        self.stabilize.setToolTip("Lazy mouse: the brush trails the cursor by this distance")
        self.invert = _check()
        self.pressure_strength = _check()
        self.pressure_radius = _check()
        self.front_only = _check()
        self.use_mask = _check()
        for label, w in (("Radius", self.radius), ("Strength", self.strength),
                         ("Spacing", self.spacing), ("Shift Smooth", self.smooth_strength),
                         ("Stabilize", self.stabilize),
                         ("Invert", self.invert), ("Pressure Str.", self.pressure_strength),
                         ("Pressure Size", self.pressure_radius), ("Front Faces", self.front_only),
                         ("Use Mask", self.use_mask)):
            g.add_widget(_row(label, w))
        self.radius.valueChanged.connect(lambda v: self.session.set("radius", float(v)))
        self.strength.valueChanged.connect(lambda v: self.session.set("strength", float(v) / 100.0))
        self.spacing.valueChanged.connect(lambda v: self.session.set("spacing", float(v) / 100.0))
        self.smooth_strength.valueChanged.connect(
            lambda v: self.session.set("smooth_strength", float(v) / 100.0))
        self.stabilize.valueChanged.connect(lambda v: self.session.set("stabilize", float(v)))
        self.invert.toggled.connect(lambda f: self.session.set("invert", bool(f)))
        self.pressure_strength.toggled.connect(lambda f: self.session.set("pressure_strength", bool(f)))
        self.pressure_radius.toggled.connect(lambda f: self.session.set("pressure_radius", bool(f)))
        self.front_only.toggled.connect(lambda f: self.session.set("front_only", bool(f)))
        self.use_mask.toggled.connect(lambda f: self.session.set("use_mask", bool(f)))
        reset = _button("Reset Brush", "Restore the default settings of this brush")
        reset.clicked.connect(self.session.reset_brush)
        host = QWidget()
        hl = QHBoxLayout(host)
        hl.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, 0)
        hl.addStretch(1)
        hl.addWidget(reset)
        g.add_widget(host)
        body.addWidget(g)

        g = CollapsibleGroup("Falloff")
        self.falloff = prepare_combo(QComboBox())
        self.falloff.addItems([f.capitalize() for f in _falloff.FALLOFFS])
        self.falloff.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.falloff.activated.connect(
            lambda i: self.session.set("falloff", _falloff.FALLOFFS[i]))
        g.add_widget(_row("Type", self.falloff))
        self.curve = FalloffCurveEditor()
        holder = QWidget()
        cl = QHBoxLayout(holder)
        cl.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, GAP)
        cl.addWidget(self.curve)
        g.add_widget(holder)
        self.curve.edited.connect(self._on_curve)
        body.addWidget(g)

        g = CollapsibleGroup("Stamp", expanded=False)
        self.stamp = prepare_combo(QComboBox())
        self.stamp.addItems([s.capitalize() for s in _stamps.STAMPS])
        self.stamp.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.stamp.activated.connect(lambda i: self.session.set("stamp", _stamps.STAMPS[i]))
        g.add_widget(_row("Image", self.stamp))
        self.stamp_rotation = _SliderField(-180, 180, 0, " deg")
        self.stamp_rotation.valueChanged.connect(lambda v: self.session.set("stamp_rotation", float(v)))
        g.add_widget(_row("Rotation", self.stamp_rotation))
        self.stamp_scale = _SliderField(10, 400, 0, " %")
        self.stamp_scale.setToolTip("Stamp size relative to the brush")
        self.stamp_scale.valueChanged.connect(lambda v: self.session.set("stamp_scale", float(v) / 100.0))
        g.add_widget(_row("Scale", self.stamp_scale))
        self.stamp_tile = _check()
        self.stamp_tile.setToolTip("Repeat the stamp in a fixed grid instead of centring it on each dab")
        self.stamp_tile.toggled.connect(lambda f: self.session.set("stamp_tile", bool(f)))
        g.add_widget(_row("Tile", self.stamp_tile))
        host = QWidget()
        hl = QHBoxLayout(host)
        hl.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, GAP)
        hl.setSpacing(PAD)
        self.stamp_preview = QLabel()
        self.stamp_preview.setFixedSize(STAMP_PREVIEW, STAMP_PREVIEW)
        hl.addWidget(self.stamp_preview)
        self.load_stamp_button = _button("Load Image...", "Use a grayscale image as the stamp")
        self.load_stamp_button.clicked.connect(self._load_stamp)
        hl.addWidget(self.load_stamp_button)
        hl.addStretch(1)
        g.add_widget(host)
        body.addWidget(g)

        g = CollapsibleGroup("Symmetry")
        host = QWidget()
        hl = QHBoxLayout(host)
        hl.setContentsMargins(PAD_SIDE, 0, PAD_SIDE, 0)
        hl.setSpacing(PAD_SIDE)
        self.sym: list[QCheckBox] = []
        for axis, name in enumerate("XYZ"):
            box = _check(f"Local {name}")
            box.toggled.connect(lambda f, a=axis: self.session.set_symmetry(a, f))
            hl.addWidget(box)
            self.sym.append(box)
        hl.addStretch(1)
        g.add_widget(host)
        body.addWidget(g)

        g = CollapsibleGroup("Mask")
        self.mask_enabled = _check()
        self.mask_enabled.toggled.connect(self._on_mask_enabled)
        g.add_widget(_row("Enable Mask", self.mask_enabled))
        self.show_mask = _check()
        self.show_mask.toggled.connect(self.session.set_show_mask)
        g.add_widget(_row("Show Mask", self.show_mask))
        host = QWidget()
        mg = QGridLayout(host)
        mg.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, GAP)
        mg.setSpacing(GAP)
        self.mask_buttons: dict[str, QPushButton] = {}
        for i, (name, fn) in enumerate((("Invert", data.mask_invert), ("Clear", data.mask_clear),
                                        ("Fill", data.mask_fill), ("Grow", data.mask_grow),
                                        ("Shrink", data.mask_shrink), ("Smooth", data.mask_smooth))):
            b = _button(name, f"{name} the mask of the active object")
            b.clicked.connect(lambda _c=False, f=fn: self._mask_action(f))
            mg.addWidget(b, i // 3, i % 3)
            self.mask_buttons[name] = b
        g.add_widget(host)
        self.mask_info = QLabel("")
        self.mask_info.setObjectName("qsDimLabel")
        self.mask_info.setContentsMargins(PAD_SIDE, 0, PAD_SIDE, 0)
        g.add_widget(self.mask_info)
        body.addWidget(g)
        body.addStretch(1)

        self.session.settingsChanged.connect(self.refresh)
        self.session.brushChanged.connect(lambda *_: self.refresh())
        self.session.activeChanged.connect(self._on_active)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._refresh_object)
        for sig in ("changed", "selectionChanged", "objectsChanged"):
            s = getattr(self.scene, sig, None)
            if s is not None:
                s.connect(self._timer.start)
        self.refresh()
        self._on_active(self.session.active)

    def sizeHint(self) -> QSize:
        return QSize(256 + 64, 512)

    def _on_active(self, flag: bool) -> None:
        self.mode_button.blockSignals(True)
        self.mode_button.setChecked(bool(flag))
        self.mode_button.blockSignals(False)
        self._refresh_object()

    def _on_curve(self, kind: str, curve: list) -> None:
        self.session.set("curve", curve)
        if self.session.settings().falloff != kind:
            self.session.set("falloff", kind)

    def _load_stamp(self, path: str | None = None) -> bool:
        if not path:
            path, _f = QFileDialog.getOpenFileName(self, "Load Stamp Image", "",
                                                   "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if not path:
            return False
        arr = _stamps.load_stamp(path)
        if arr is None:
            return False
        self.session.set("stamp_image", arr)
        self.session.set("stamp", "custom")
        return True

    def _mask_action(self, fn) -> None:
        obj = self.session.target()
        if obj is not None:
            fn(obj, self.scene)
            self.session.notify_data()

    def _on_mask_enabled(self, flag: bool) -> None:
        obj = self.session.target()
        if obj is not None:
            data.set_mask_enabled(obj, flag, self.scene)

    def refresh(self) -> None:
        s = self.session.settings()
        b = self.brush_buttons.get(self.session.brush)
        if b is not None and not b.isChecked():
            b.setChecked(True)
        spec = brush(self.session.brush)
        self.brush_label.setText(f"{spec.label}: {spec.description}")
        self.radius.setValue(s.radius)
        self.strength.setValue(s.strength * 100.0)
        self.spacing.setValue(s.spacing * 100.0)
        self.smooth_strength.setValue(s.smooth_strength * 100.0)
        self.stabilize.setValue(s.stabilize)
        for box, value in ((self.invert, s.invert), (self.pressure_strength, s.pressure_strength),
                           (self.pressure_radius, s.pressure_radius), (self.front_only, s.front_only),
                           (self.use_mask, s.use_mask), (self.show_mask, self.session.show_mask)):
            box.blockSignals(True)
            box.setChecked(bool(value))
            box.blockSignals(False)
        for box, value in zip(self.sym, s.symmetry):
            box.blockSignals(True)
            box.setChecked(bool(value))
            box.blockSignals(False)
        self.falloff.blockSignals(True)
        self.falloff.setCurrentIndex(_falloff.FALLOFFS.index(s.falloff))
        self.falloff.blockSignals(False)
        if self.curve._drag is None:
            self.curve.set_state(s.falloff, s.curve)
        self.stamp.blockSignals(True)
        self.stamp.setCurrentIndex(_stamps.STAMPS.index(s.stamp))
        self.stamp.blockSignals(False)
        self.stamp_rotation.setValue(s.stamp_rotation)
        self.stamp_scale.setValue(s.stamp_scale * 100.0)
        self.stamp_tile.blockSignals(True)
        self.stamp_tile.setChecked(bool(s.stamp_tile))
        self.stamp_tile.blockSignals(False)
        self.stamp_preview.setPixmap(stamp_pixmap(s.stamp_array()))
        self._refresh_object()

    def _refresh_object(self) -> None:
        obj = getattr(self.scene, "active", None)
        ok = data.can_sculpt(obj)
        info = data.summary(obj) if ok else None
        for b in self.mask_buttons.values():
            b.setEnabled(ok)
        self.mask_enabled.setEnabled(ok)
        self.mask_enabled.blockSignals(True)
        self.mask_enabled.setChecked(bool(info["mask_enabled"]) if info else True)
        self.mask_enabled.blockSignals(False)
        if info is None:
            self.mask_info.setText("Select a polygon object to sculpt")
        else:
            self.mask_info.setText(f"{info['masked']} of {info['points']} points masked")
        block = info.get("block") if info else None
        if block == "frozen" or (block and self.session.brush != "mask"):
            self.block_info.setText(data.BLOCK_TEXT.get(block, "") + ": strokes are disabled")
            self.block_info.setVisible(True)
        else:
            self.block_info.setText("")
            self.block_info.setVisible(False)


class SculptLayersPanel(QWidget):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = _scene(scene)
        self.session = get_session(self.scene)
        self.setObjectName("qsSculptLayersPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        head = _Header("Sculpt Layers", self)
        self.object_label = head.add(QLabel(""))
        self.object_label.setObjectName("qsDimLabel")
        outer.addWidget(head)
        self.scroll, body = _scroll_body(self)
        outer.addWidget(self.scroll, 1)

        g = CollapsibleGroup("Subdivision")
        self.level_combo = prepare_combo(QComboBox())
        self.level_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.level_combo.activated.connect(self._on_level)
        g.add_widget(_row("Level", self.level_combo))
        host = QWidget()
        gl = QGridLayout(host)
        gl.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, GAP)
        gl.setSpacing(GAP)
        self.subdivide_button = _button("Subdivide", "Add a Catmull-Clark subdivision level")
        self.down_button = _button("Level Down", "Step down one subdivision level")
        self.up_button = _button("Level Up", "Step up one subdivision level")
        self.delete_higher_button = _button("Delete Higher", "Remove the levels above the current one")
        gl.addWidget(self.subdivide_button, 0, 0)
        gl.addWidget(self.delete_higher_button, 0, 1)
        gl.addWidget(self.down_button, 1, 0)
        gl.addWidget(self.up_button, 1, 1)
        g.add_widget(host)
        self.subdivide_button.clicked.connect(lambda: self._run(data.subdivide))
        self.down_button.clicked.connect(lambda: self._run(data.level_down))
        self.up_button.clicked.connect(lambda: self._run(data.level_up))
        self.delete_higher_button.clicked.connect(lambda: self._run(data.delete_higher_levels))
        self.level_info = QLabel("")
        self.level_info.setObjectName("qsDimLabel")
        self.level_info.setContentsMargins(PAD_SIDE, 0, PAD_SIDE, 0)
        g.add_widget(self.level_info)
        body.addWidget(g)

        g = CollapsibleGroup("Layers")
        self.layer_list = QListWidget()
        self.layer_list.setFixedHeight(LIST_H)
        self.layer_list.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        holder = QWidget()
        ll = QHBoxLayout(holder)
        ll.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, GAP)
        ll.addWidget(self.layer_list)
        g.add_widget(holder)
        self.layer_list.currentRowChanged.connect(self._on_row)
        self.layer_list.itemChanged.connect(self._on_item)
        self.layer_strength = _SliderField(0, 200, 0, " %")
        self.layer_strength.valueChanged.connect(self._on_strength)
        g.add_widget(_row("Strength", self.layer_strength))
        self.layer_lock = _check()
        self.layer_lock.toggled.connect(self._on_lock)
        g.add_widget(_row("Locked", self.layer_lock))
        host = QWidget()
        gl = QGridLayout(host)
        gl.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, GAP)
        gl.setSpacing(GAP)
        self.add_button = _button("Add", "Add a sculpt layer")
        self.remove_button = _button("Remove", "Delete the selected layer")
        self.layer_up_button = _button("Move Up", "Move the selected layer up")
        self.layer_down_button = _button("Move Down", "Move the selected layer down")
        self.clear_button = _button("Clear", "Clear the selected layer on this level")
        self.merge_button = _button("Merge Down", "Merge the selected layer into the one below")
        for i, b in enumerate((self.add_button, self.remove_button, self.layer_up_button,
                               self.layer_down_button, self.clear_button, self.merge_button)):
            gl.addWidget(b, i // 2, i % 2)
        g.add_widget(host)
        self.add_button.clicked.connect(self._add_layer)
        self.remove_button.clicked.connect(lambda: self._layer_op(data.remove_layer))
        self.layer_up_button.clicked.connect(lambda: self._move(-1))
        self.layer_down_button.clicked.connect(lambda: self._move(1))
        self.clear_button.clicked.connect(self._clear)
        self.merge_button.clicked.connect(lambda: self._layer_op(data.merge_layer_down))
        body.addWidget(g)

        g = CollapsibleGroup("Object")
        self.frozen = _check()
        self.frozen.toggled.connect(self._on_frozen)
        g.add_widget(_row("Frozen", self.frozen))
        host = QWidget()
        gl = QGridLayout(host)
        gl.setContentsMargins(PAD_SIDE, GAP, PAD_SIDE, GAP)
        gl.setSpacing(GAP)
        self.bake_layers_button = _button("Bake Layers", "Merge every visible, unlocked layer into the base sculpt")
        self.bake_button = _button("Bake to Mesh", "Replace the object with the current level")
        self.remove_sculpt_button = _button("Drop Sculpt", "Discard sculpt levels and layers")
        gl.addWidget(self.bake_layers_button, 0, 0)
        gl.addWidget(self.bake_button, 0, 1)
        gl.addWidget(self.remove_sculpt_button, 1, 0)
        g.add_widget(host)
        self.bake_layers_button.clicked.connect(lambda: self._run(data.bake_layers))
        self.bake_button.clicked.connect(lambda: self._run(data.bake_to_mesh))
        self.remove_sculpt_button.clicked.connect(lambda: self._run(data.remove_sculpt))
        body.addWidget(g)
        body.addStretch(1)

        self._syncing = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.refresh)
        for sig in ("changed", "selectionChanged", "objectsChanged"):
            s = getattr(self.scene, sig, None)
            if s is not None:
                s.connect(self._timer.start)
        self.session.dataChanged.connect(self._timer.start)
        self.refresh()

    def sizeHint(self) -> QSize:
        return QSize(256 + 64, 448)

    def target(self):
        obj = getattr(self.scene, "active", None)
        return obj if data.can_sculpt(obj) else None

    def _run(self, fn) -> bool:
        obj = self.target()
        if obj is None:
            return False
        ok = bool(fn(obj, self.scene))
        self.session.notify_data()
        self.refresh()
        return ok

    def _on_level(self, index: int) -> None:
        obj = self.target()
        if obj is not None:
            data.set_level(obj, index, self.scene)
            self.refresh()

    def selected_layer(self) -> int:
        return self.layer_list.currentRow() - 1

    def _on_row(self, row: int) -> None:
        if self._syncing:
            return
        obj = self.target()
        if obj is not None and row >= 0:
            data.set_active_layer(obj, row - 1, self.scene)
            self.refresh()

    def _on_item(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        obj = self.target()
        row = self.layer_list.row(item)
        if obj is None or row <= 0:
            return
        index = row - 1
        state = data.get_state(obj)
        layer = data.layers(state)[index] if state and index < data.layer_count(state) else None
        if layer is None:
            return
        visible = item.checkState() == Qt.CheckState.Checked
        if visible != bool(layer.get("visible", True)):
            data.set_layer_visible(obj, index, visible, self.scene)
        name = item.text().strip()
        if name and name != layer.get("name"):
            data.rename_layer(obj, index, name, self.scene)
        self._timer.start()

    def _on_strength(self, value: float) -> None:
        if self._syncing:
            return
        obj = self.target()
        i = self.selected_layer()
        if obj is not None and i >= 0:
            data.set_layer_strength(obj, i, value / 100.0, self.scene)

    def _on_lock(self, flag: bool) -> None:
        if self._syncing:
            return
        obj = self.target()
        i = self.selected_layer()
        if obj is not None and i >= 0:
            data.set_layer_locked(obj, i, flag, self.scene)

    def _on_frozen(self, flag: bool) -> None:
        if self._syncing:
            return
        obj = self.target()
        if obj is not None:
            data.set_frozen(obj, flag, self.scene)

    def _add_layer(self) -> int:
        obj = self.target()
        if obj is None:
            return -1
        i = data.add_layer(obj, None, self.scene)
        self.refresh()
        return i

    def _layer_op(self, fn) -> bool:
        obj = self.target()
        i = self.selected_layer()
        if obj is None or i < 0:
            return False
        ok = bool(fn(obj, i, self.scene))
        self.refresh()
        return ok

    def _move(self, step: int) -> int:
        obj = self.target()
        i = self.selected_layer()
        if obj is None or i < 0:
            return i
        new = data.move_layer(obj, i, step, self.scene)
        self.refresh()
        return new

    def _clear(self) -> bool:
        obj = self.target()
        if obj is None:
            return False
        ok = data.clear_layer(obj, self.selected_layer(), self.scene)
        self.refresh()
        return ok

    def refresh(self) -> None:
        self._syncing = True
        try:
            self._refresh()
        finally:
            self._syncing = False

    def _refresh(self) -> None:
        obj = self.target()
        state = data.get_state(obj) if obj is not None else None
        enabled = obj is not None
        for w in (self.subdivide_button, self.add_button, self.level_combo):
            w.setEnabled(enabled)
        if obj is None:
            self.object_label.setText("No polygon object")
            self.level_combo.clear()
            self.layer_list.clear()
            self.level_info.setText("")
            for w in (self.down_button, self.up_button, self.delete_higher_button, self.remove_button,
                      self.layer_up_button, self.layer_down_button, self.clear_button, self.merge_button,
                      self.bake_layers_button, self.bake_button, self.remove_sculpt_button,
                      self.layer_strength, self.layer_lock, self.frozen):
                w.setEnabled(False)
            return
        self.object_label.setText(obj.name)
        levels = data.level_info(state) if state else [{"level": 0, "points": len(obj.mesh.points),
                                                         "polygons": len(obj.mesh.polygons)}]
        lv = data.current_level(state)
        self.level_combo.clear()
        for info in levels:
            self.level_combo.addItem(f"Level {info['level']}  ({info['points']} points)")
        self.level_combo.setCurrentIndex(lv)
        cur = levels[lv]
        self.level_info.setText(f"{len(levels)} levels, {cur['polygons']} polygons on this level")
        self.down_button.setEnabled(lv > 0)
        self.up_button.setEnabled(lv < len(levels) - 1)
        self.delete_higher_button.setEnabled(lv < len(levels) - 1)
        lays = data.layers(state)
        active = data.active_layer(state)
        self.layer_list.clear()
        base = QListWidgetItem("Base")
        base.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.layer_list.addItem(base)
        for layer in lays:
            item = QListWidgetItem(str(layer.get("name", "Layer")))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                          | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if layer.get("visible", True) else Qt.CheckState.Unchecked)
            if layer.get("locked", False):
                item.setForeground(QColor(theme.TEXT_MUTED))
            self.layer_list.addItem(item)
        self.layer_list.setCurrentRow(active + 1)
        has_layer = active >= 0
        locked = has_layer and bool(lays[active].get("locked", False))
        self.remove_button.setEnabled(has_layer)
        self.merge_button.setEnabled(has_layer and data.can_merge_down(state, active))
        self.layer_up_button.setEnabled(has_layer and active > 0)
        self.layer_down_button.setEnabled(has_layer and active < len(lays) - 1)
        self.clear_button.setEnabled(state is not None and not locked and not data.is_frozen(state))
        self.layer_strength.setEnabled(has_layer)
        self.layer_lock.setEnabled(has_layer)
        if has_layer:
            self.layer_strength.setValue(float(lays[active].get("strength", 1.0)) * 100.0)
            self.layer_lock.setChecked(bool(lays[active].get("locked", False)))
        else:
            self.layer_strength.setValue(100.0)
            self.layer_lock.setChecked(False)
        self.bake_layers_button.setEnabled(bool(data.bakeable_layers(state)))
        self.bake_button.setEnabled(state is not None)
        self.remove_sculpt_button.setEnabled(state is not None)
        self.frozen.setEnabled(True)
        self.frozen.setChecked(data.is_frozen(state))
