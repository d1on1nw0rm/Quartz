from __future__ import annotations

import math
import os
import weakref

import shiboken6
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QToolButton,
                               QVBoxLayout, QWidget)

from .. import theme
from ..widgets.common import CollapsibleGroup, FieldRow, prepare_combo
from . import engine
from .settings import (AA_LEVELS, BACKGROUNDS, BUCKET_ORDERS, DEFAULT_LIGHTS, FORMATS, MAX_SIZE, MAX_TRANSPARENCY,
                       PASSES, PRESETS, TONEMAPS, default_settings, get_settings, set_settings, update_settings)
from .snapshot import camera_objects
from .worker import RenderManager, RenderRecord, get_manager

__all__ = ["ColorButton", "ImagePane", "PictureViewer", "RenderSettingsPanel", "RenderView", "PASS_LABELS",
           "ZOOM_LEVELS"]

ROW_H = 24
GAP = 8
PAD = 8
LABEL_W = 112
INDENT = 12
SWATCH_W = 48
THUMB = 48
HISTORY_W = 224
CHECKER = 8
FIELD_W = 96
ZOOM_LEVELS = (0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
PASS_LABELS = {"beauty": "Beauty", "depth": "Depth", "normal": "Normal", "albedo": "Albedo",
               "ao": "Ambient Occlusion"}
BACKGROUND_LABELS = {"color": "Color", "gradient": "Gradient", "transparent": "Transparent"}
TONEMAP_LABELS = {"standard": "Standard", "filmic": "Filmic", "aces": "ACES"}
LIGHT_LABELS = {"auto": "Auto", "on": "Always", "off": "Off"}
ORDER_LABELS = {"spiral": "Spiral", "rows": "Rows"}
SHADOW_SIZES = (256, 512, 1024, 2048, 4096)
BUCKET_SIZES = (32, 64, 128, 256)
VIEW_SCALES = (("25%", 0.25), ("50%", 0.5), ("100%", 1.0))


def _scene_or_default(scene):
    if scene is not None:
        return scene
    from ..scene import get_scene
    return get_scene()


def _combo(parent: QWidget, items, data=None) -> QComboBox:
    combo = prepare_combo(QComboBox(parent))
    for i, text in enumerate(items):
        combo.addItem(str(text), None if data is None else data[i])
    combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    combo.setFixedHeight(ROW_H)
    return combo


def _spin(parent: QWidget, lo: int, hi: int, step: int = 1, suffix: str = "") -> QSpinBox:
    spin = QSpinBox(parent)
    spin.setRange(lo, hi)
    spin.setSingleStep(step)
    spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)
    spin.setFixedHeight(ROW_H)
    spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    return spin


def _dspin(parent: QWidget, lo: float, hi: float, step: float, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    spin = QDoubleSpinBox(parent)
    spin.setRange(lo, hi)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)
    spin.setFixedHeight(ROW_H)
    spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    return spin


def _button(text: str, parent: QWidget, tip: str = "") -> QPushButton:
    b = QPushButton(text, parent)
    b.setFixedHeight(ROW_H)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if tip:
        b.setToolTip(tip)
    return b


def _set_combo_data(combo: QComboBox, value) -> None:
    for i in range(combo.count()):
        if combo.itemData(i) == value or (combo.itemData(i) is None and combo.itemText(i) == str(value)):
            combo.setCurrentIndex(i)
            return


class ColorButton(QPushButton):

    colorChanged = Signal(list)

    def __init__(self, rgb=(1.0, 1.0, 1.0), parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rgb = [float(c) for c in list(rgb)[:3]]
        self.setFixedSize(SWATCH_W, ROW_H)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self.pick)
        self._refresh_tip()

    def color(self) -> list[float]:
        return list(self._rgb)

    def set_color(self, rgb, emit: bool = False) -> None:
        self._rgb = [max(0.0, min(1.0, float(c))) for c in list(rgb)[:3]]
        self._refresh_tip()
        self.update()
        if emit:
            self.colorChanged.emit(self.color())

    def _refresh_tip(self) -> None:
        q = self.qcolor()
        self.setToolTip(q.name())

    def qcolor(self) -> QColor:
        return QColor.fromRgbF(*self._rgb)

    def pick(self) -> None:
        chosen = QColorDialog.getColor(self.qcolor(), self, "Choose Color")
        if chosen.isValid():
            self.set_color([chosen.redF(), chosen.greenF(), chosen.blueF()], emit=True)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QColor(theme.HAIRLINE_STRONG))
        p.setBrush(self.qcolor())
        p.drawRoundedRect(r, theme.CONTROL_RADIUS, theme.CONTROL_RADIUS)
        p.end()


def checker_pixmap() -> QPixmap:
    pix = QPixmap(2 * CHECKER, 2 * CHECKER)
    pix.fill(QColor(theme.SURFACE_RAISED))
    p = QPainter(pix)
    dark = QColor(theme.SURFACE_FIELD)
    p.fillRect(CHECKER, 0, CHECKER, CHECKER, dark)
    p.fillRect(0, CHECKER, CHECKER, CHECKER, dark)
    p.end()
    return pix


def sync_pass_combo(combo: QComboBox, available) -> None:
    avail = list(available)
    model = combo.model()
    for i in range(combo.count()):
        item = model.item(i) if hasattr(model, "item") else None
        if item is not None:
            item.setEnabled(combo.itemData(i) in avail)
    if combo.currentData() not in avail and "beauty" in avail:
        combo.blockSignals(True)
        _set_combo_data(combo, "beauty")
        combo.blockSignals(False)


_LIVE_VIEWS: list = []


def live_render_views() -> list:
    out = []
    for ref in list(_LIVE_VIEWS):
        view = ref()
        if view is None or not shiboken6.isValid(view):
            _LIVE_VIEWS.remove(ref)
            continue
        out.append(view)
    return out


def visible_render_view():
    for view in live_render_views():
        if view.isVisible():
            return view
    return None


class _ImageCanvas(QWidget):

    def __init__(self, pane: "ImagePane") -> None:
        super().__init__(pane)
        self.pane = pane
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.SURFACE_BACKDROP))
        img = self.pane.image
        if img is None or img.isNull():
            p.setPen(QColor(theme.TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.pane.placeholder)
            p.end()
            return
        target = self.pane.image_rect()
        exposed = target.intersected(QRectF(event.rect()))
        if exposed.isEmpty() or target.width() <= 0 or target.height() <= 0:
            p.end()
            return
        brush = QBrush(checker_pixmap())
        brush.setTransform(QTransform.fromTranslate(target.left(), target.top()))
        p.fillRect(exposed, brush)
        zx = target.width() / img.width()
        zy = target.height() / img.height()
        sx0 = max(0, int(math.floor((exposed.left() - target.left()) / zx)))
        sy0 = max(0, int(math.floor((exposed.top() - target.top()) / zy)))
        sx1 = min(img.width(), int(math.ceil((exposed.right() - target.left()) / zx)))
        sy1 = min(img.height(), int(math.ceil((exposed.bottom() - target.top()) / zy)))
        if sx1 > sx0 and sy1 > sy0:
            src = QRectF(sx0, sy0, sx1 - sx0, sy1 - sy0)
            dst = QRectF(target.left() + sx0 * zx, target.top() + sy0 * zy, (sx1 - sx0) * zx, (sy1 - sy0) * zy)
            p.setClipRect(exposed)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.pane.zoom < 1.0)
            p.drawImage(dst, img, src)
        p.end()


class ImagePane(QScrollArea):

    zoomChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None, placeholder: str = "No render yet") -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder = placeholder
        self.image: QImage | None = None
        self.zoom = 1.0
        self.fit = True
        self.canvas = _ImageCanvas(self)
        self.setWidget(self.canvas)
        self.setMinimumSize(128, 96)
        self._relayout()

    def set_image(self, image: QImage | None) -> None:
        self.image = image
        self._relayout()
        self.canvas.update()

    def image_rect(self) -> QRectF:
        if self.image is None:
            return QRectF()
        w = self.image.width() * self.zoom
        h = self.image.height() * self.zoom
        cw, ch = self.canvas.width(), self.canvas.height()
        return QRectF((cw - w) / 2.0, (ch - h) / 2.0, w, h)

    def fit_zoom(self) -> float:
        if self.image is None or self.image.isNull():
            return 1.0
        vw = max(1, self.viewport().width() - 2 * PAD)
        vh = max(1, self.viewport().height() - 2 * PAD)
        return max(0.01, min(vw / self.image.width(), vh / self.image.height()))

    def set_fit(self) -> None:
        self.fit = True
        self._relayout()
        self.zoomChanged.emit(self.zoom)

    def set_zoom(self, zoom: float) -> None:
        self.fit = False
        self.zoom = max(0.01, min(32.0, float(zoom)))
        self._relayout()
        self.zoomChanged.emit(self.zoom)

    def zoom_in(self) -> None:
        bigger = [z for z in ZOOM_LEVELS if z > self.zoom + 1e-6]
        self.set_zoom(bigger[0] if bigger else self.zoom * 2.0)

    def zoom_out(self) -> None:
        smaller = [z for z in ZOOM_LEVELS if z < self.zoom - 1e-6]
        self.set_zoom(smaller[-1] if smaller else self.zoom / 2.0)

    def _relayout(self) -> None:
        if self.fit:
            self.zoom = self.fit_zoom()
        vw, vh = self.viewport().width(), self.viewport().height()
        if self.image is None or self.image.isNull():
            self.canvas.resize(vw, vh)
        else:
            w = int(self.image.width() * self.zoom) + 2 * PAD
            h = int(self.image.height() * self.zoom) + 2 * PAD
            self.canvas.resize(max(w, vw), max(h, vh))
        self.canvas.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)


class PictureViewer(QWidget):

    def __init__(self, scene=None, parent: QWidget | None = None, manager: RenderManager | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsPictureViewer")
        self.scene = _scene_or_default(scene)
        self.manager = manager or get_manager()
        self.record: RenderRecord | None = None
        self.preview: QImage | None = None
        self.last_saved = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(PAD, PAD, PAD, PAD)
        root.setSpacing(GAP)
        bar = QHBoxLayout()
        bar.setSpacing(GAP)
        self.render_button = _button("Render", self, "Render to Picture Viewer (Shift+R)")
        self.cancel_button = _button("Cancel", self, "Stop the running render")
        self.pass_combo = _combo(self, [PASS_LABELS[p] for p in PASSES], list(PASSES))
        self.zoom_combo = _combo(self, ["Fit"] + [f"{int(z * 100)}%" for z in ZOOM_LEVELS],
                                 ["fit"] + list(ZOOM_LEVELS))
        self.zoom_out_button = _button("Zoom Out", self, "Show the picture smaller (Ctrl+Wheel)")
        self.zoom_in_button = _button("Zoom In", self, "Show the picture larger (Ctrl+Wheel)")
        self.save_button = _button("Save As...", self, "Save the shown pass as PNG or JPG")
        for w in (self.render_button, self.cancel_button, self.pass_combo, self.zoom_combo,
                  self.zoom_out_button, self.zoom_in_button, self.save_button):
            bar.addWidget(w)
        bar.addStretch(1)
        root.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal, self)
        self.pane = ImagePane(split, "Render a picture with Shift+R")
        side = QWidget(split)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(GAP)
        title = QLabel("HISTORY", side)
        title.setObjectName("qsGroupTitle")
        side_l.addWidget(title)
        self.history_list = QListWidget(side)
        self.history_list.setIconSize(QSize(THUMB, THUMB))
        side_l.addWidget(self.history_list, 1)
        hb = QHBoxLayout()
        hb.setSpacing(GAP)
        self.remove_button = _button("Remove", side, "Remove the selected render from the history")
        self.clear_button = _button("Clear", side, "Remove every render from the history")
        hb.addWidget(self.remove_button)
        hb.addWidget(self.clear_button)
        side_l.addLayout(hb)
        side.setMinimumWidth(HISTORY_W)
        split.addWidget(self.pane)
        split.addWidget(side)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        root.addWidget(split, 1)
        status = QHBoxLayout()
        status.setSpacing(GAP)
        self.info_label = QLabel("", self)
        self.info_label.setObjectName("qsDimLabel")
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(PAD)
        self.progress_bar.setFixedWidth(HISTORY_W)
        status.addWidget(self.info_label, 1)
        status.addWidget(self.progress_bar)
        root.addLayout(status)
        self.render_button.clicked.connect(self.render)
        self.cancel_button.clicked.connect(self.manager.cancel)
        self.pass_combo.currentIndexChanged.connect(self._show_current)
        self.zoom_combo.activated.connect(self._zoom_chosen)
        self.zoom_in_button.clicked.connect(self.pane.zoom_in)
        self.zoom_out_button.clicked.connect(self.pane.zoom_out)
        self.pane.zoomChanged.connect(self._zoom_shown)
        self.save_button.clicked.connect(self.save_as)
        self.history_list.currentRowChanged.connect(self._history_picked)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.manager.clear_history)
        self.manager.started.connect(self._on_started)
        self.manager.progress.connect(self._on_progress)
        self.manager.bucketReady.connect(self._on_bucket)
        self.manager.finished.connect(self._on_finished)
        self.manager.failed.connect(self._on_failed)
        self.manager.cancelled.connect(self._on_cancelled)
        self.manager.historyChanged.connect(self._rebuild_history)
        self.manager.busyChanged.connect(self._sync_buttons)
        self._rebuild_history()
        if self.manager.history:
            self.show_record(self.manager.history[0])
        self._sync_buttons()

    def render(self) -> None:
        self.manager.render(self.scene, target="viewer")

    def current_pass(self) -> str:
        return str(self.pass_combo.currentData() or "beauty")

    def set_pass(self, name: str) -> bool:
        if name not in self._available_passes():
            return False
        _set_combo_data(self.pass_combo, name)
        return self.current_pass() == name

    def _accepts(self, target) -> bool:
        return target != "view" or visible_render_view() is None

    def _sync_buttons(self, *_args) -> None:
        busy = self.manager.is_running()
        self.cancel_button.setEnabled(busy)
        self.save_button.setEnabled(self.record is not None)
        self.remove_button.setEnabled(self.history_list.currentRow() >= 0)
        self.clear_button.setEnabled(bool(self.manager.history))
        if not busy:
            self.progress_bar.setValue(0)

    def _zoom_chosen(self, index: int) -> None:
        data = self.zoom_combo.itemData(index)
        if data == "fit":
            self.pane.set_fit()
        else:
            self.pane.set_zoom(float(data))

    def _zoom_shown(self, zoom: float) -> None:
        self.zoom_combo.blockSignals(True)
        custom = self.zoom_combo.count() - 1 if self.zoom_combo.count() > len(ZOOM_LEVELS) + 1 else -1
        if self.pane.fit:
            if custom >= 0:
                self.zoom_combo.removeItem(custom)
            self.zoom_combo.setCurrentIndex(0)
        else:
            idx = next((i for i in range(1, len(ZOOM_LEVELS) + 1)
                        if abs(float(self.zoom_combo.itemData(i)) - zoom) < 1e-6), -1)
            if idx < 0:
                label = f"{zoom * 100:.0f}%" if zoom * 100 >= 1 else f"{zoom * 100:.1f}%"
                if custom < 0:
                    self.zoom_combo.addItem(label, float(zoom))
                    custom = self.zoom_combo.count() - 1
                else:
                    self.zoom_combo.setItemText(custom, label)
                    self.zoom_combo.setItemData(custom, float(zoom))
                self.zoom_combo.setCurrentIndex(custom)
            else:
                if custom >= 0:
                    self.zoom_combo.removeItem(custom)
                self.zoom_combo.setCurrentIndex(idx)
        self.zoom_combo.blockSignals(False)

    def _available_passes(self) -> list[str]:
        if self.record is None:
            return ["beauty"]
        return [p for p in PASSES if p in self.record.result.passes]

    def _sync_pass_items(self) -> None:
        sync_pass_combo(self.pass_combo, self._available_passes())

    def show_record(self, record: RenderRecord | None) -> None:
        self.record = record
        self.preview = None
        self._sync_pass_items()
        self._show_current()
        if record is not None and record in self.manager.history:
            row = self.manager.history.index(record)
            if self.history_list.currentRow() != row:
                self.history_list.blockSignals(True)
                self.history_list.setCurrentRow(row)
                self.history_list.blockSignals(False)
        self._sync_buttons()

    def _show_current(self, *_args) -> None:
        if self.record is None:
            self.pane.set_image(self.preview)
            return
        if self.current_pass() not in self.record.result.passes:
            self._sync_pass_items()
        self.pane.set_image(self.record.image(self.current_pass()))
        r = self.record.result
        frame = f"   Frame {r.frame}" if r.frame is not None else ""
        saved = f"   Saved {os.path.basename(self.record.saved[0])}" if self.record.saved else ""
        warnings = r.stats.get("warnings") or []
        note = f"   {warnings[0]}" if warnings else ""
        self.info_label.setText(f"{self.record.title}   {r.width} x {r.height}   {r.seconds:.2f} s   "
                                f"{r.stats.get('triangles', 0)} triangles{frame}{saved}{note}")

    def _rebuild_history(self) -> None:
        self.history_list.blockSignals(True)
        self.history_list.clear()
        for rec in self.manager.history:
            pix = QPixmap.fromImage(rec.thumbnail())
            item = QListWidgetItem(QIcon(pix), rec.summary())
            item.setToolTip(rec.summary())
            self.history_list.addItem(item)
        if self.record is not None and self.record in self.manager.history:
            self.history_list.setCurrentRow(self.manager.history.index(self.record))
        self.history_list.blockSignals(False)
        if self.record is not None and self.record not in self.manager.history:
            self.show_record(self.manager.history[0] if self.manager.history else None)
        self._sync_buttons()

    def _history_picked(self, row: int) -> None:
        if 0 <= row < len(self.manager.history):
            self.show_record(self.manager.history[row])
        self._sync_buttons()

    def remove_selected(self) -> None:
        row = self.history_list.currentRow()
        if 0 <= row < len(self.manager.history):
            self.manager.remove(self.manager.history[row])

    def _on_started(self, info: dict) -> None:
        self._tracking = self._accepts(info.get("target"))
        if not self._tracking:
            self._sync_buttons()
            return
        self.record = None
        self.preview = QImage(int(info["width"]), int(info["height"]), QImage.Format.Format_RGBA8888)
        self.preview.fill(QColor(theme.SURFACE_FIELD))
        self._sync_pass_items()
        self.pane.set_image(self.preview)
        frame = f"   Frame {info['frame']}" if info.get("frame") is not None else ""
        self.info_label.setText(f"Rendering {info.get('label', '')}   {info['width']} x {info['height']}{frame}")
        self._sync_buttons()

    def _on_progress(self, value: float, stage: str) -> None:
        if not getattr(self, "_tracking", True):
            return
        self.progress_bar.setValue(int(value * 1000))
        if self.record is None:
            self.info_label.setText(f"{stage}   {int(value * 100)}%")

    def _on_bucket(self, rect, image: QImage) -> None:
        if not getattr(self, "_tracking", True) or self.preview is None or self.record is not None:
            return
        p = QPainter(self.preview)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(int(rect[0]), int(rect[1]), image)
        p.end()
        self.pane.canvas.update()

    def _on_finished(self, record: RenderRecord) -> None:
        if not self._accepts(record.target):
            self._rebuild_history()
            return
        self.show_record(record)

    def _on_failed(self, message: str) -> None:
        self.info_label.setText("Render failed: " + message.splitlines()[0])
        self._sync_buttons()

    def _on_cancelled(self) -> None:
        self.info_label.setText("Render cancelled")
        self._sync_buttons()

    def save_current(self, path: str, fmt: str | None = None) -> bool:
        if self.record is None or not path:
            return False
        s = self.record.result.settings
        if fmt:
            path = engine.format_path(path, fmt)
        ok = engine.save_result(self.record.result, path, fmt, self.current_pass(), int(s.get("jpg_quality", 92)))
        if ok:
            self.last_saved = path
            self.info_label.setText(f"Saved {path}")
        return ok

    def save_as(self) -> None:
        if self.record is None:
            return
        s = get_settings(self.scene)
        start = s.get("output_path") or os.path.join(os.path.expanduser("~"), "render.png")
        path, chosen = QFileDialog.getSaveFileName(self, "Save Picture", start, "PNG Image (*.png);;JPG Image (*.jpg)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            fmt = "jpg"
        elif ext == ".png":
            fmt = "png"
        else:
            fmt = "jpg" if "jpg" in chosen.lower() else "png"
        self.save_current(engine.format_path(path, fmt), fmt)


class RenderSettingsPanel(QWidget):

    renderRequested = Signal(str)

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsRenderSettings")
        self.scene = _scene_or_default(scene)
        self._loading = False
        self.controls: dict[str, QWidget] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 0, PAD)
        self.body_layout.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        self.groups: dict[str, CollapsibleGroup] = {}
        self._build_output()
        self._build_camera()
        self._build_animation()
        self._build_passes()
        self._build_lighting()
        self._build_background()
        self._build_ao()
        self._build_color()
        self._build_shading()
        self._build_performance()
        self.body_layout.addStretch(1)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(PAD, PAD, PAD, PAD)
        buttons.setSpacing(GAP)
        self.view_button = _button("Render View", self, "Render the active view (Ctrl+R)")
        self.picture_button = _button("Render", self, "Render to Picture Viewer (Shift+R)")
        self.reset_button = _button("Defaults", self, "Reset every render setting")
        buttons.addWidget(self.view_button)
        buttons.addWidget(self.picture_button)
        buttons.addStretch(1)
        buttons.addWidget(self.reset_button)
        root.addLayout(buttons)
        self.view_button.clicked.connect(lambda: self._request("view"))
        self.picture_button.clicked.connect(lambda: self._request("viewer"))
        self.reset_button.clicked.connect(self.reset_defaults)
        self.scene.changed.connect(self.refresh)
        self.scene.objectsChanged.connect(self._fill_cameras)
        self.refresh()

    def _request(self, target: str) -> None:
        self.renderRequested.emit(target)
        from . import actions
        if target == "view":
            actions.render_view(self.scene)
        else:
            actions.render_to_picture_viewer(self.scene)

    def _group(self, title: str) -> CollapsibleGroup:
        g = CollapsibleGroup(title, self)
        self.groups[title] = g
        self.body_layout.addWidget(g)
        return g

    def _row(self, group: CollapsibleGroup, label: str, key: str, editor: QWidget, extra: QWidget | None = None) -> FieldRow:
        row = FieldRow(label, None, group, label_width=LABEL_W, indent=INDENT)
        row.setFixedHeight(ROW_H + 4)
        row.editor = editor
        row.add_widget(editor, 1 if extra is None else 1)
        if extra is not None:
            row.add_widget(extra)
        group.add_widget(row)
        self.controls[key] = editor
        return row

    def _check(self, group: CollapsibleGroup, label: str, key: str) -> QCheckBox:
        box = QCheckBox(group)
        box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row = FieldRow(label, None, group, label_width=LABEL_W, indent=INDENT)
        row.setFixedHeight(ROW_H + 4)
        row.editor = box
        row.add_widget(box)
        row.add_stretch(1)
        group.add_widget(row)
        self.controls[key] = box
        box.toggled.connect(lambda v, k=key: self._set(k, bool(v)))
        return box

    def _bind_combo(self, combo: QComboBox, key: str, cast=None) -> None:
        def chosen(i, c=combo, k=key):
            value = c.itemData(i)
            self._set(k, cast(value) if cast is not None else value)
        combo.activated.connect(chosen)

    def _bind_spin(self, spin, key: str) -> None:
        spin.valueChanged.connect(lambda v, k=key: self._set(k, v))

    def _bind_color(self, button: ColorButton, key: str) -> None:
        button.colorChanged.connect(lambda c, k=key: self._set(k, list(c)))

    def _set(self, key: str, value) -> None:
        if self._loading:
            return
        update_settings(self.scene, **{key: value})
        self.refresh()

    def set_value(self, key: str, value) -> None:
        update_settings(self.scene, **{key: value})
        self.refresh()

    def _build_output(self) -> None:
        g = self._group("Output")
        self.preset_combo = _combo(g, list(PRESETS), list(PRESETS))
        self._row(g, "Resolution", "preset", self.preset_combo)
        self._bind_combo(self.preset_combo, "preset")
        self.width_spin = _spin(g, 16, MAX_SIZE, 16, " px")
        self._row(g, "Width", "width", self.width_spin)
        self._bind_spin(self.width_spin, "width")
        self.height_spin = _spin(g, 16, MAX_SIZE, 16, " px")
        self._row(g, "Height", "height", self.height_spin)
        self._bind_spin(self.height_spin, "height")
        self.aa_combo = _combo(g, [f"{a} x {a}" if a > 1 else "None" for a in AA_LEVELS], list(AA_LEVELS))
        self._row(g, "Anti-Aliasing", "aa", self.aa_combo)
        self._bind_combo(self.aa_combo, "aa", int)
        self.format_combo = _combo(g, [f.upper() for f in FORMATS], list(FORMATS))
        self._row(g, "Format", "format", self.format_combo)
        self.format_combo.activated.connect(lambda i: self.set_format(self.format_combo.itemData(i)))
        self.quality_spin = _spin(g, 1, 100, 1, " %")
        self._row(g, "JPG Quality", "jpg_quality", self.quality_spin)
        self._bind_spin(self.quality_spin, "jpg_quality")
        self.path_edit = QLineEdit(g)
        self.path_edit.setFixedHeight(ROW_H)
        self.path_edit.setPlaceholderText("Choose a file to save renders")
        self.browse_button = _button("Browse", g, "Choose the output file")
        self._row(g, "Output Path", "output_path", self.path_edit, self.browse_button)
        self.path_edit.editingFinished.connect(lambda: self.set_output_path(self.path_edit.text()))
        self.browse_button.clicked.connect(self.browse_output)
        self.auto_save_check = self._check(g, "Save Automatically", "auto_save")
        self.save_passes_check = self._check(g, "Save Passes", "save_passes")

    def set_format(self, fmt) -> None:
        if self._loading or fmt not in FORMATS:
            return
        s = get_settings(self.scene)
        values = {"format": fmt}
        if s["output_path"]:
            fixed = engine.format_path(s["output_path"], fmt)
            if fixed != s["output_path"]:
                values["output_path"] = fixed
        update_settings(self.scene, **values)
        self.refresh()

    def set_output_path(self, path: str, chosen_filter: str = "") -> None:
        if self._loading:
            return
        path = str(path or "").strip()
        s = get_settings(self.scene)
        values = {"output_path": path}
        ext = os.path.splitext(path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            values["format"] = "jpg"
        elif ext == ".png":
            values["format"] = "png"
        elif path:
            fmt = "jpg" if "jpg" in chosen_filter.lower() else ("png" if chosen_filter else s["format"])
            values["format"] = fmt
            values["output_path"] = engine.format_path(path, fmt)
        if values["output_path"] == s["output_path"] and values.get("format", s["format"]) == s["format"]:
            self.refresh()
            return
        update_settings(self.scene, **values)
        self.refresh()

    def browse_output(self) -> None:
        s = get_settings(self.scene)
        start = s["output_path"] or os.path.join(os.path.expanduser("~"), "render." + s["format"])
        path, chosen = QFileDialog.getSaveFileName(self, "Output File", start,
                                                   "PNG Image (*.png);;JPG Image (*.jpg)")
        if path:
            self.set_output_path(path, chosen)

    def _build_camera(self) -> None:
        g = self._group("Camera")
        self.camera_combo = _combo(g, [])
        self._row(g, "Render Camera", "camera", self.camera_combo)
        self.camera_combo.activated.connect(lambda i: self.set_camera(self.camera_combo.itemData(i)))
        self._fill_cameras()

    def set_camera(self, name) -> None:
        if self._loading:
            return
        name = str(name or "")
        s = get_settings(self.scene)
        obj = engine.find_camera_object(self.scene, name, s["camera_id"] if name == s["camera"] else "")
        if not name or obj is None:
            update_settings(self.scene, camera=name, camera_id="")
            self.refresh()
            return
        group = hasattr(self.scene, "begin_group") and hasattr(self.scene, "end_group")
        if group:
            self.scene.begin_group()
        try:
            uid = engine.camera_uid(obj, create=True, scene=self.scene)
            update_settings(self.scene, camera=obj.name, camera_id=uid)
        finally:
            if group:
                self.scene.end_group()
        self.refresh()

    def _fill_cameras(self) -> None:
        s = get_settings(self.scene)
        current = s["camera"]
        cams = camera_objects(self.scene)
        chosen = engine.find_camera_object(self.scene, current, s["camera_id"]) if current else None
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        self.camera_combo.addItem("Active View", "")
        for obj in cams:
            self.camera_combo.addItem(obj.name, obj.name)
        if not current:
            self.camera_combo.setCurrentIndex(0)
        elif chosen is not None:
            self.camera_combo.setCurrentIndex(1 + cams.index(chosen))
        else:
            self.camera_combo.addItem(f"{current} (missing)", current)
            self.camera_combo.setCurrentIndex(self.camera_combo.count() - 1)
        self.camera_combo.blockSignals(False)

    def _build_animation(self) -> None:
        g = self._group("Animation")
        self.anim_check = self._check(g, "Frame Range", "animation")
        self.start_spin = _spin(g, -100000, 100000)
        self._row(g, "From", "frame_start", self.start_spin)
        self._bind_spin(self.start_spin, "frame_start")
        self.end_spin = _spin(g, -100000, 100000)
        self._row(g, "To", "frame_end", self.end_spin)
        self._bind_spin(self.end_spin, "frame_end")
        self.step_spin = _spin(g, 1, 10000)
        self._row(g, "Step", "frame_step", self.step_spin)
        self._bind_spin(self.step_spin, "frame_step")
        self.timeline_button = _button("Use Timeline Range", g, "Copy the preview range of the timeline")
        row = FieldRow("", None, g, label_width=LABEL_W, indent=INDENT)
        row.setFixedHeight(ROW_H + 4)
        row.add_widget(self.timeline_button)
        row.add_stretch(1)
        g.add_widget(row)
        self.timeline_button.clicked.connect(self.use_timeline_range)

    def use_timeline_range(self) -> bool:
        from .bridges import timeline_range
        rng = timeline_range(self.scene)
        if rng is None:
            return False
        update_settings(self.scene, frame_start=rng[0], frame_end=rng[1], animation=True)
        self.refresh()
        return True

    def _build_passes(self) -> None:
        g = self._group("Passes")
        self.pass_checks: dict[str, QCheckBox] = {}
        for name in PASSES:
            box = QCheckBox(g)
            box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row = FieldRow(PASS_LABELS[name], None, g, label_width=LABEL_W, indent=INDENT)
            row.setFixedHeight(ROW_H + 4)
            row.editor = box
            row.add_widget(box)
            row.add_stretch(1)
            g.add_widget(row)
            self.pass_checks[name] = box
            self.controls["pass_" + name] = box
            if name == "beauty":
                box.setEnabled(False)
            box.toggled.connect(self._passes_changed)

    def _passes_changed(self, *_args) -> None:
        if self._loading:
            return
        chosen = [p for p in PASSES if self.pass_checks[p].isChecked()]
        self._set("passes", chosen)

    def _build_lighting(self) -> None:
        g = self._group("Lighting")
        self.lights_combo = _combo(g, [LIGHT_LABELS[k] for k in DEFAULT_LIGHTS], list(DEFAULT_LIGHTS))
        self._row(g, "Default Lights", "default_lights", self.lights_combo)
        self._bind_combo(self.lights_combo, "default_lights")
        self.shadows_check = self._check(g, "Shadows", "shadows")
        self.shadow_combo = _combo(g, [str(s) for s in SHADOW_SIZES], list(SHADOW_SIZES))
        self._row(g, "Shadow Map", "shadow_map", self.shadow_combo)
        self._bind_combo(self.shadow_combo, "shadow_map", int)
        self.softness_spin = _dspin(g, 0.0, 8.0, 0.25)
        self._row(g, "Shadow Softness", "shadow_softness", self.softness_spin)
        self._bind_spin(self.softness_spin, "shadow_softness")
        self.ambient_spin = _dspin(g, 0.0, 10.0, 0.05)
        self._row(g, "Ambient", "ambient", self.ambient_spin)
        self._bind_spin(self.ambient_spin, "ambient")
        self.sky_button = ColorButton(parent=g)
        self._row(g, "Sky Light", "sky_color", self.sky_button)
        self._bind_color(self.sky_button, "sky_color")
        self.ground_button = ColorButton(parent=g)
        self._row(g, "Ground Light", "ground_color", self.ground_button)
        self._bind_color(self.ground_button, "ground_color")

    def _build_background(self) -> None:
        g = self._group("Background")
        self.bg_combo = _combo(g, [BACKGROUND_LABELS[b] for b in BACKGROUNDS], list(BACKGROUNDS))
        self._row(g, "Mode", "background", self.bg_combo)
        self._bind_combo(self.bg_combo, "background")
        self.bg_button = ColorButton(parent=g)
        self._row(g, "Color", "bg_color", self.bg_button)
        self._bind_color(self.bg_button, "bg_color")
        self.top_button = ColorButton(parent=g)
        self._row(g, "Top", "bg_top", self.top_button)
        self._bind_color(self.top_button, "bg_top")
        self.bottom_button = ColorButton(parent=g)
        self._row(g, "Bottom", "bg_bottom", self.bottom_button)
        self._bind_color(self.bottom_button, "bg_bottom")

    def _build_ao(self) -> None:
        g = self._group("Ambient Occlusion")
        self.ao_check = self._check(g, "Enabled", "ao")
        self.ao_radius_spin = _dspin(g, 0.1, 100000.0, 5.0, 1, " cm")
        self._row(g, "Radius", "ao_radius", self.ao_radius_spin)
        self._bind_spin(self.ao_radius_spin, "ao_radius")
        self.ao_samples_spin = _spin(g, 1, 64)
        self._row(g, "Samples", "ao_samples", self.ao_samples_spin)
        self._bind_spin(self.ao_samples_spin, "ao_samples")
        self.ao_strength_spin = _dspin(g, 0.0, 4.0, 0.1)
        self._row(g, "Strength", "ao_strength", self.ao_strength_spin)
        self._bind_spin(self.ao_strength_spin, "ao_strength")

    def _build_color(self) -> None:
        g = self._group("Color")
        self.tonemap_combo = _combo(g, [TONEMAP_LABELS[t] for t in TONEMAPS], list(TONEMAPS))
        self._row(g, "Tone Mapping", "tonemap", self.tonemap_combo)
        self._bind_combo(self.tonemap_combo, "tonemap")
        self.exposure_spin = _dspin(g, -16.0, 16.0, 0.25, 2, " EV")
        self._row(g, "Exposure", "exposure", self.exposure_spin)
        self._bind_spin(self.exposure_spin, "exposure")
        self.gamma_spin = _dspin(g, 0.1, 5.0, 0.1)
        self._row(g, "Gamma", "gamma", self.gamma_spin)
        self._bind_spin(self.gamma_spin, "gamma")

    def _build_shading(self) -> None:
        g = self._group("Shading")
        self.phong_check = self._check(g, "Auto Smoothing", "auto_phong")
        self.phong_spin = _dspin(g, 0.0, 180.0, 5.0, 1, " deg")
        self._row(g, "Smoothing Angle", "phong_angle", self.phong_spin)
        self._bind_spin(self.phong_spin, "phong_angle")
        self.cull_check = self._check(g, "Backface Culling", "backface_culling")
        self.transparency_spin = _spin(g, 0, MAX_TRANSPARENCY)
        self.transparency_spin.setToolTip("Surfaces seen through transparent materials (0 shows the background)")
        self._row(g, "Transparency Depth", "transparency_depth", self.transparency_spin)
        self._bind_spin(self.transparency_spin, "transparency_depth")

    def _build_performance(self) -> None:
        g = self._group("Buckets")
        self.bucket_combo = _combo(g, [str(b) for b in BUCKET_SIZES], list(BUCKET_SIZES))
        self._row(g, "Bucket Size", "bucket_size", self.bucket_combo)
        self._bind_combo(self.bucket_combo, "bucket_size", int)
        self.order_combo = _combo(g, [ORDER_LABELS[o] for o in BUCKET_ORDERS], list(BUCKET_ORDERS))
        self._row(g, "Order", "bucket_order", self.order_combo)
        self._bind_combo(self.order_combo, "bucket_order")
        self.seed_spin = _spin(g, 0, 2 ** 31 - 1)
        self._row(g, "Noise Seed", "seed", self.seed_spin)
        self._bind_spin(self.seed_spin, "seed")
        g.set_expanded(False)

    def reset_defaults(self) -> None:
        set_settings(self.scene, default_settings())
        self.refresh()

    def refresh(self) -> None:
        s = get_settings(self.scene)
        self._loading = True
        try:
            widgets = [w for w in self.controls.values()]
            for w in widgets:
                w.blockSignals(True)
            _set_combo_data(self.preset_combo, s["preset"])
            self.width_spin.setValue(s["width"])
            self.height_spin.setValue(s["height"])
            _set_combo_data(self.aa_combo, s["aa"])
            _set_combo_data(self.format_combo, s["format"])
            self.quality_spin.setValue(s["jpg_quality"])
            self.quality_spin.setEnabled(s["format"] == "jpg")
            if not self.path_edit.hasFocus():
                self.path_edit.setText(s["output_path"])
            self.auto_save_check.setChecked(s["auto_save"])
            self.save_passes_check.setChecked(s["save_passes"])
            self.save_passes_check.setEnabled(s["auto_save"])
            self._fill_cameras()
            self.anim_check.setChecked(s["animation"])
            self.start_spin.setValue(s["frame_start"])
            self.end_spin.setValue(s["frame_end"])
            self.step_spin.setValue(s["frame_step"])
            for spin in (self.start_spin, self.end_spin, self.step_spin):
                spin.setEnabled(s["animation"])
            from .bridges import timeline_range
            self.timeline_button.setEnabled(timeline_range(self.scene) is not None)
            for name, box in self.pass_checks.items():
                box.setChecked(name in s["passes"])
            _set_combo_data(self.lights_combo, s["default_lights"])
            self.shadows_check.setChecked(s["shadows"])
            _set_combo_data(self.shadow_combo, s["shadow_map"])
            self.softness_spin.setValue(s["shadow_softness"])
            for w in (self.shadow_combo, self.softness_spin):
                w.setEnabled(s["shadows"])
            self.ambient_spin.setValue(s["ambient"])
            self.sky_button.set_color(s["sky_color"])
            self.ground_button.set_color(s["ground_color"])
            _set_combo_data(self.bg_combo, s["background"])
            self.bg_button.set_color(s["bg_color"])
            self.top_button.set_color(s["bg_top"])
            self.bottom_button.set_color(s["bg_bottom"])
            self.bg_button.setEnabled(s["background"] == "color")
            self.top_button.setEnabled(s["background"] == "gradient")
            self.bottom_button.setEnabled(s["background"] == "gradient")
            self.ao_check.setChecked(s["ao"])
            self.ao_radius_spin.setValue(s["ao_radius"])
            self.ao_samples_spin.setValue(s["ao_samples"])
            self.ao_strength_spin.setValue(s["ao_strength"])
            for w in (self.ao_radius_spin, self.ao_samples_spin, self.ao_strength_spin):
                w.setEnabled(s["ao"])
            _set_combo_data(self.tonemap_combo, s["tonemap"])
            self.exposure_spin.setValue(s["exposure"])
            self.gamma_spin.setValue(s["gamma"])
            self.phong_check.setChecked(s["auto_phong"])
            self.phong_spin.setValue(s["phong_angle"])
            self.phong_spin.setEnabled(s["auto_phong"])
            self.cull_check.setChecked(s["backface_culling"])
            self.transparency_spin.setValue(s["transparency_depth"])
            _set_combo_data(self.bucket_combo, s["bucket_size"])
            _set_combo_data(self.order_combo, s["bucket_order"])
            self.seed_spin.setValue(s["seed"])
        finally:
            for w in self.controls.values():
                w.blockSignals(False)
            self._loading = False


class RenderView(QWidget):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsRenderView")
        self.scene = _scene_or_default(scene)
        self.manager = RenderManager(self, keep_history=False)
        self.shared = get_manager()
        self.record: RenderRecord | None = None
        self.preview: QImage | None = None
        self.scale = 0.5
        root = QVBoxLayout(self)
        root.setContentsMargins(PAD, PAD, PAD, PAD)
        root.setSpacing(GAP)
        bar = QHBoxLayout()
        bar.setSpacing(GAP)
        self.render_button = _button("Render", self, "Render the active view")
        self.cancel_button = _button("Cancel", self, "Stop the running render")
        self.auto_check = QCheckBox("Auto Update", self)
        self.auto_check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.auto_check.setToolTip("Render again whenever the scene changes")
        self.scale_combo = _combo(self, [t for t, _v in VIEW_SCALES], [v for _t, v in VIEW_SCALES])
        _set_combo_data(self.scale_combo, self.scale)
        self.pass_combo = _combo(self, [PASS_LABELS[p] for p in PASSES], list(PASSES))
        for w in (self.render_button, self.cancel_button, self.auto_check, self.scale_combo, self.pass_combo):
            bar.addWidget(w)
        bar.addStretch(1)
        root.addLayout(bar)
        self.pane = ImagePane(self, "Render the active view with Ctrl+R")
        root.addWidget(self.pane, 1)
        status = QHBoxLayout()
        status.setSpacing(GAP)
        self.info_label = QLabel("", self)
        self.info_label.setObjectName("qsDimLabel")
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(PAD)
        self.progress_bar.setFixedWidth(HISTORY_W)
        status.addWidget(self.info_label, 1)
        status.addWidget(self.progress_bar)
        root.addLayout(status)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.render)
        self.render_button.clicked.connect(self.render)
        self.cancel_button.clicked.connect(self.cancel)
        self.auto_check.toggled.connect(self._auto_toggled)
        self.scale_combo.activated.connect(self._scale_chosen)
        self.pass_combo.currentIndexChanged.connect(self._show)
        self._active = None
        self.manager.started.connect(self._own_started)
        self.manager.progress.connect(self._own_progress)
        self.manager.bucketReady.connect(self._own_bucket)
        self.manager.finished.connect(self._own_finished)
        self.manager.busyChanged.connect(self._sync_buttons)
        self.shared.started.connect(self._shared_started)
        self.shared.progress.connect(self._shared_progress)
        self.shared.bucketReady.connect(self._shared_bucket)
        self.shared.finished.connect(self._shared_finished)
        self.shared.busyChanged.connect(self._sync_buttons)
        self.scene.changed.connect(self._scene_changed)
        _LIVE_VIEWS.append(weakref.ref(self))
        self._sync_buttons()

    def _own_started(self, info: dict) -> None:
        self._on_started(self.manager, info)

    def _own_progress(self, value: float, stage: str) -> None:
        self._on_progress(self.manager, value, stage)

    def _own_bucket(self, rect, image: QImage) -> None:
        self._on_bucket(self.manager, rect, image)

    def _own_finished(self, record) -> None:
        self._on_finished(self.manager, record)

    def _shared_started(self, info: dict) -> None:
        self._on_started(self.shared, info)

    def _shared_progress(self, value: float, stage: str) -> None:
        self._on_progress(self.shared, value, stage)

    def _shared_bucket(self, rect, image: QImage) -> None:
        self._on_bucket(self.shared, rect, image)

    def _shared_finished(self, record) -> None:
        self._on_finished(self.shared, record)

    def current_pass(self) -> str:
        return str(self.pass_combo.currentData() or "beauty")

    def set_pass(self, name: str) -> bool:
        avail = list(self.record.result.passes) if self.record is not None else ["beauty"]
        if name not in avail:
            return False
        _set_combo_data(self.pass_combo, name)
        return self.current_pass() == name

    def _ours(self, manager, target=None) -> bool:
        if manager is self.manager:
            return True
        return target == "view"

    def view_size(self) -> tuple[int, int]:
        canvas = engine.active_canvas()
        if canvas is not None:
            rect = canvas.film_rect()
            w, h = int(rect.width()), int(rect.height())
        else:
            s = get_settings(self.scene)
            w, h = s["width"], s["height"]
        w = max(16, int(w * self.scale))
        h = max(16, int(h * self.scale))
        return w, h

    def render(self) -> None:
        w, h = self.view_size()
        canvas = engine.active_canvas()
        cam = canvas if canvas is not None else None
        self.manager.render(self.scene, camera=cam, width=w, height=h, target="view",
                            animation=False, label="View")

    def cancel(self) -> None:
        self.manager.cancel()
        self.shared.cancel()

    def _auto_toggled(self, on: bool) -> None:
        if on:
            self.render()
        else:
            self._timer.stop()

    def _scale_chosen(self, index: int) -> None:
        self.scale = float(self.scale_combo.itemData(index))
        if self.auto_check.isChecked():
            self.render()

    def _scene_changed(self) -> None:
        if self.auto_check.isChecked():
            self._timer.start()

    def _sync_buttons(self, *_args) -> None:
        busy = self.manager.is_running()
        self.cancel_button.setEnabled(busy or self.shared.is_running())
        if not busy:
            self.progress_bar.setValue(0)

    def _on_started(self, manager, info: dict) -> None:
        if not self._ours(manager, info.get("target")):
            return
        self.record = None
        self.preview = QImage(int(info["width"]), int(info["height"]), QImage.Format.Format_RGBA8888)
        self.preview.fill(QColor(theme.SURFACE_FIELD))
        self.pane.set_image(self.preview)
        self.info_label.setText(f"Rendering view   {info['width']} x {info['height']}")
        self._active = manager
        self._sync_buttons()

    def _on_progress(self, manager, value: float, stage: str) -> None:
        if getattr(self, "_active", None) is manager and self.record is None:
            self.progress_bar.setValue(int(value * 1000))

    def _on_bucket(self, manager, rect, image: QImage) -> None:
        if getattr(self, "_active", None) is not manager or self.preview is None or self.record is not None:
            return
        p = QPainter(self.preview)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(int(rect[0]), int(rect[1]), image)
        p.end()
        self.pane.canvas.update()

    def _on_finished(self, manager, record: RenderRecord) -> None:
        if not self._ours(manager, record.target):
            return
        self.record = record
        sync_pass_combo(self.pass_combo, list(record.result.passes))
        self._show()
        self._sync_buttons()

    def _show(self, *_args) -> None:
        if self.record is None:
            return
        if self.current_pass() not in self.record.result.passes:
            sync_pass_combo(self.pass_combo, list(self.record.result.passes))
        self.pane.set_image(self.record.image(self.current_pass()))
        r = self.record.result
        warnings = r.stats.get("warnings") or []
        note = f"   {warnings[0]}" if warnings else ""
        self.info_label.setText(f"{r.camera}   {r.width} x {r.height}   {r.seconds:.2f} s{note}")
