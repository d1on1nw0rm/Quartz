from __future__ import annotations

import weakref

from PySide6.QtCore import QEvent, QLocale, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import theme
from ..scene import get_scene
from ..widgets.common import Chip, CollapsibleGroup, FieldRow, prepare_combo
from .project import AXES, PROJECTIONS, TAG_PROJECTIONS, look_at
from .session import UVSession, session_for
from .texture import CHANNELS, TEXTURE_SIZES, color_tuple
from .unwrap import RELAX_METHODS, UNWRAP_METHODS

__all__ = ["UVToolsPanel", "TexturePaintPanel", "ViewportPainter", "STAT_LABELS"]

LABEL_W = 112
INDENT = 16

STAT_LABELS = (
    ("polygons", "Polygons", "{:d}"),
    ("uv_points", "UV points", "{:d}"),
    ("islands", "Islands", "{:d}"),
    ("seams", "Seam edges", "{:d}"),
    ("coverage", "Coverage", "{:.1%}"),
    ("overlap", "Overlap", "{:.1%}"),
    ("out_of_bounds", "Out of 0..1", "{:d}"),
    ("flipped", "Flipped", "{:d}"),
    ("mean_stretch", "Mean stretch", "{:.3f}"),
    ("max_stretch", "Max stretch", "{:.3f}"),
    ("mean_conformal", "Mean angle error", "{:.3f}"),
    ("max_conformal", "Max angle error", "{:.3f}"),
)


def _button(text: str, parent: QWidget, fn) -> QPushButton:
    b = QPushButton(text, parent)
    b.setObjectName("qsToolButton")
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setFixedHeight(theme.FIELD_H + 2)
    b.clicked.connect(lambda _c=False: fn())
    return b


def _combo(items, parent: QWidget) -> QComboBox:
    c = prepare_combo(QComboBox(parent))
    c.addItems(list(items))
    c.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    return c


def _locale() -> QLocale:
    loc = QLocale.c()
    loc.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    return loc


def _spin(lo: float, hi: float, value: float, step: float, decimals: int, parent: QWidget,
          suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox(parent)
    s.setLocale(_locale())
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    s.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    s.setFixedHeight(theme.FIELD_H)
    return s


def _ispin(lo: int, hi: int, value: int, parent: QWidget, suffix: str = "") -> QSpinBox:
    s = QSpinBox(parent)
    s.setLocale(_locale())
    s.setRange(lo, hi)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    s.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    s.setFixedHeight(theme.FIELD_H)
    return s


def _check(text: str, checked: bool, parent: QWidget) -> QCheckBox:
    c = QCheckBox(text, parent)
    c.setChecked(checked)
    c.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return c


def _row(label: str, editor: QWidget | None = None) -> FieldRow:
    return FieldRow(label, editor, label_width=LABEL_W, indent=INDENT)


def _buttons(parent: QWidget, *buttons: QPushButton) -> QWidget:
    w = QWidget(parent)
    lay = QHBoxLayout(w)
    lay.setContentsMargins(INDENT, 0, 8, 0)
    lay.setSpacing(4)
    for b in buttons:
        lay.addWidget(b, 1)
    return w


class _Panel(QWidget):

    def __init__(self, scene, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self.session: UVSession = session_for(self.scene)
        self.title = title
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll, 1)
        self.body = QWidget()
        self.body.setObjectName("qsUVPanelBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 2, 0, 8)
        self.body_layout.setSpacing(2)
        self.scroll.setWidget(self.body)
        self.status = QLabel("", self)
        self.status.setObjectName("qsDimLabel")
        self.status.setContentsMargins(8, 0, 8, 0)
        self.status.setFixedHeight(theme.ROW_H)
        self.status.setWordWrap(False)
        outer.addWidget(self.status)
        self.session.message.connect(self.status.setText)
        self.groups: dict[str, CollapsibleGroup] = {}
        self.setStyleSheet(f"#qsUVPanelBody, QScrollArea {{ background: {theme.SURFACE_CARD}; }}")

    def group(self, title: str, expanded: bool = True) -> CollapsibleGroup:
        g = CollapsibleGroup(title, self.body, expanded=expanded)
        g.content_layout().setSpacing(2)
        self.body_layout.addWidget(g)
        self.groups[title] = g
        return g

    def finish(self) -> None:
        self.body_layout.addStretch(1)

    def sizeHint(self) -> QSize:
        return QSize(320, 512)


class UVToolsPanel(_Panel):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(scene, "UV Tools", parent)
        self.setObjectName("qsUVTools")
        self.camera_provider = None
        s = self.session

        g = self.group("Projection")
        self.proj_kind = _combo(PROJECTIONS, self)
        self.proj_axis = _combo(AXES, self)
        self.proj_fit = _check("Fit to 0..1", True, self)
        self.proj_aspect = _check("Keep aspect", True, self)
        self.proj_atlas = _check("Box atlas layout", True, self)
        g.add_widget(_row("Type", self.proj_kind))
        g.add_widget(_row("Axis", self.proj_axis))
        g.add_widget(_row("", self.proj_fit))
        g.add_widget(_row("", self.proj_aspect))
        g.add_widget(_row("", self.proj_atlas))
        self.project_button = _button("Project", self, self.do_project)
        self.reset_button = _button("Reset UVs", self, s.reset)
        g.add_widget(_buttons(self, self.project_button, self.reset_button))

        g = self.group("Material Tag")
        self.tag_kind = _combo(TAG_PROJECTIONS, self)
        self.tag_axis = _combo(AXES, self)
        self.tag_tile_u = _spin(0.01, 1000.0, 1.0, 0.1, 3, self)
        self.tag_tile_v = _spin(0.01, 1000.0, 1.0, 0.1, 3, self)
        self.tag_off_u = _spin(-1000.0, 1000.0, 0.0, 0.05, 3, self)
        self.tag_off_v = _spin(-1000.0, 1000.0, 0.0, 0.05, 3, self)
        g.add_widget(_row("Projection", self.tag_kind))
        g.add_widget(_row("Axis", self.tag_axis))
        g.add_widget(_row("Tiles U", self.tag_tile_u))
        g.add_widget(_row("Tiles V", self.tag_tile_v))
        g.add_widget(_row("Offset U", self.tag_off_u))
        g.add_widget(_row("Offset V", self.tag_off_v))
        self.tag_button = _button("Generate UVW from Tag", self, self.do_uvw_from_tag)
        g.add_widget(_buttons(self, self.tag_button))
        self._tag_target = None
        self._tag_timer = QTimer(self)
        self._tag_timer.setSingleShot(True)
        self._tag_timer.setInterval(400)
        self._tag_timer.timeout.connect(self.flush_tag)
        for w in (self.tag_kind, self.tag_axis):
            w.activated.connect(lambda _i: self.store_tag())
        for w in (self.tag_tile_u, self.tag_tile_v, self.tag_off_u, self.tag_off_v):
            w.valueChanged.connect(lambda _v: self.queue_tag())

        g = self.group("Seams")
        self.seam_angle = _spin(1.0, 180.0, 60.0, 5.0, 1, self, " deg")
        g.add_widget(_row("Angle", self.seam_angle))
        self.seam_add = _button("From Selection", self, lambda: s.seams_from_selection(False))
        self.seam_remove = _button("Remove Selected", self, s.remove_selected_seams)
        g.add_widget(_buttons(self, self.seam_add, self.seam_remove))
        self.seam_by_angle = _button("By Angle", self, lambda: s.seams_by_angle(self.seam_angle.value()))
        self.seam_islands = _button("From Islands", self, s.seams_from_islands)
        self.seam_clear = _button("Clear", self, s.clear_seams)
        g.add_widget(_buttons(self, self.seam_by_angle, self.seam_islands, self.seam_clear))

        g = self.group("Unwrap")
        self.unwrap_method = _combo(UNWRAP_METHODS, self)
        self.unwrap_angle = _check("Cut sharp edges", False, self)
        self.unwrap_pack = _check("Pack after unwrap", True, self)
        g.add_widget(_row("Method", self.unwrap_method))
        g.add_widget(_row("", self.unwrap_angle))
        g.add_widget(_row("", self.unwrap_pack))
        self.unwrap_button = _button("Unwrap", self, self.do_unwrap)
        g.add_widget(_buttons(self, self.unwrap_button))

        g = self.group("Relax")
        self.relax_method = _combo(RELAX_METHODS, self)
        self.relax_iter = _ispin(1, 500, 10, self)
        self.relax_pin_boundary = _check("Pin border", False, self)
        self.relax_pin_selected = _check("Pin selected points", False, self)
        g.add_widget(_row("Method", self.relax_method))
        g.add_widget(_row("Iterations", self.relax_iter))
        g.add_widget(_row("", self.relax_pin_boundary))
        g.add_widget(_row("", self.relax_pin_selected))
        self.relax_button = _button("Relax", self, self.do_relax)
        g.add_widget(_buttons(self, self.relax_button))

        g = self.group("Arrange")
        self.pack_margin = _spin(0.0, 0.25, 0.01, 0.005, 3, self)
        self.pack_rotate = _check("Allow rotation", True, self)
        self.pack_equalize = _check("Equalize texel density", True, self)
        self.pack_align = _check("Align islands first", False, self)
        self.align_mode = _combo(("Auto", "U", "V"), self)
        g.add_widget(_row("Margin", self.pack_margin))
        g.add_widget(_row("", self.pack_rotate))
        g.add_widget(_row("", self.pack_equalize))
        g.add_widget(_row("", self.pack_align))
        self.pack_button = _button("Pack Islands", self, self.do_pack)
        g.add_widget(_buttons(self, self.pack_button))
        g.add_widget(_row("Align to", self.align_mode))
        self.align_button = _button("Align Islands", self, lambda: s.align_islands(self.align_mode.currentText()))
        self.rectify_button = _button("Rectify Grid", self, s.rectify)
        g.add_widget(_buttons(self, self.align_button, self.rectify_button))

        g = self.group("Transform")
        self.flip_u = _button("Flip U", self, lambda: s.flip("U"))
        self.flip_v = _button("Flip V", self, lambda: s.flip("V"))
        self.rot_ccw = _button("Rotate -90", self, lambda: s.rotate90(True))
        self.rot_cw = _button("Rotate +90", self, lambda: s.rotate90(False))
        g.add_widget(_buttons(self, self.flip_u, self.flip_v))
        g.add_widget(_buttons(self, self.rot_ccw, self.rot_cw))
        self.move_u = _spin(-10.0, 10.0, 0.0, 0.01, 4, self)
        self.move_v = _spin(-10.0, 10.0, 0.0, 0.01, 4, self)
        g.add_widget(_row("Move U", self.move_u))
        g.add_widget(_row("Move V", self.move_v))
        self.rot_angle = _spin(-360.0, 360.0, 45.0, 5.0, 2, self, " deg")
        g.add_widget(_row("Angle", self.rot_angle))
        self.scale_u = _spin(-100.0, 100.0, 1.0, 0.1, 4, self)
        self.scale_v = _spin(-100.0, 100.0, 1.0, 0.1, 4, self)
        g.add_widget(_row("Scale U", self.scale_u))
        g.add_widget(_row("Scale V", self.scale_v))
        self.move_button = _button("Move", self, lambda: s.move(self.move_u.value(), self.move_v.value()))
        self.rotate_button = _button("Rotate", self, lambda: s.rotate(self.rot_angle.value()))
        self.scale_button = _button("Scale", self, lambda: s.scale(self.scale_u.value(), self.scale_v.value()))
        g.add_widget(_buttons(self, self.move_button, self.rotate_button, self.scale_button))
        self.fit_aspect = _check("Keep aspect", True, self)
        self.fit_margin = _spin(0.0, 0.45, 0.0, 0.01, 3, self)
        g.add_widget(_row("", self.fit_aspect))
        g.add_widget(_row("Fit margin", self.fit_margin))
        self.fit_button = _button("Fit to Bounds", self,
                                  lambda: s.fit(self.fit_aspect.isChecked(), self.fit_margin.value()))
        g.add_widget(_buttons(self, self.fit_button))
        self.align_u = _button("Align U", self, lambda: s.align_points("U"))
        self.align_v = _button("Align V", self, lambda: s.align_points("V"))
        self.straighten_button = _button("Straighten", self, s.straighten)
        g.add_widget(_buttons(self, self.align_u, self.align_v, self.straighten_button))
        self.stitch_move = _combo(("smaller", "first", "second"), self)
        g.add_widget(_row("Stitch moves", self.stitch_move))
        self.stitch_button = _button("Stitch", self, lambda: s.stitch(self.stitch_move.currentText()))
        g.add_widget(_buttons(self, self.stitch_button))

        g = self.group("Statistics")
        grid_host = QWidget(self)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(INDENT, 0, 8, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        self.stat_values: dict[str, QLabel] = {}
        for row, (key, label, _fmt) in enumerate(STAT_LABELS):
            name = QLabel(label, grid_host)
            name.setObjectName("qsDimLabel")
            value = QLabel("-", grid_host)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self.stat_values[key] = value
        g.add_widget(grid_host)
        self.auto_stats = _check("Update automatically", True, self)
        g.add_widget(_row("", self.auto_stats))
        self.stats_button = _button("Refresh", self, self.refresh_stats)
        g.add_widget(_buttons(self, self.stats_button))
        self.finish()

        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(200)
        self._stats_timer.timeout.connect(self.refresh_stats)
        s.uvChanged.connect(self._queue_stats)
        s.objectChanged.connect(self._on_object)
        s.objectChanged.connect(self._queue_stats)
        self._loading = False
        self._load_tag()
        self._queue_stats()

    def _on_object(self) -> None:
        self.flush_tag()
        self._load_tag()

    def queue_tag(self) -> None:
        if self._loading or self.session.obj is None:
            return
        if self._tag_target is None or self._tag_target() is not self.session.obj:
            self.flush_tag()
            self._tag_target = weakref.ref(self.session.obj)
        self._tag_timer.start()

    def tag_pending(self) -> bool:
        return self._tag_timer.isActive()

    def flush_tag(self) -> dict | None:
        self._tag_timer.stop()
        target = self._tag_target() if self._tag_target is not None else None
        self._tag_target = None
        if target is None:
            return None
        scene = self.session.scene
        if scene is not None and not any(o is target for o in getattr(scene, "objects", ())):
            return None
        return self.store_tag(target)

    def _queue_stats(self) -> None:
        if self.auto_stats.isChecked():
            self._stats_timer.start()

    def refresh_stats(self) -> dict:
        stats = self.session.stats()
        for key, _label, fmt in STAT_LABELS:
            lab = self.stat_values[key]
            if key in stats:
                val = stats[key]
                lab.setText(fmt.format(int(val) if "d" in fmt else float(val)))
            else:
                lab.setText("-")
        return stats

    def camera(self):
        if self.camera_provider is not None:
            cam = self.camera_provider()
            if cam is not None:
                return cam
        return look_at((0.0, 0.0, -1000.0), (0.0, 0.0, 0.0))

    def do_project(self) -> bool:
        kind = self.proj_kind.currentText()
        options = {"axis": self.proj_axis.currentText(), "fit": self.proj_fit.isChecked(),
                   "keep_aspect": self.proj_aspect.isChecked(), "atlas": self.proj_atlas.isChecked()}
        if kind == "Frontal":
            options["camera"] = self.camera()
        return self.session.project(kind, **options)

    def _load_tag(self) -> None:
        tag = self.session.tag()
        self._loading = True
        try:
            self.tag_kind.setCurrentIndex(max(0, self.tag_kind.findText(tag["projection"])))
            self.tag_axis.setCurrentIndex(max(0, self.tag_axis.findText(str(tag.get("axis", "Auto")))))
            self.tag_tile_u.setValue(tag["tiles"][0])
            self.tag_tile_v.setValue(tag["tiles"][1])
            self.tag_off_u.setValue(tag["offset"][0])
            self.tag_off_v.setValue(tag["offset"][1])
        finally:
            self._loading = False

    def store_tag(self, target=None) -> dict | None:
        if self._loading:
            return None
        if target is None:
            self._tag_timer.stop()
            self._tag_target = None
            target = self.session.obj
        if target is None:
            return None
        values = {"projection": self.tag_kind.currentText(), "axis": self.tag_axis.currentText(),
                  "tiles": [self.tag_tile_u.value(), self.tag_tile_v.value()],
                  "offset": [self.tag_off_u.value(), self.tag_off_v.value()]}
        if values["projection"] == "Frontal":
            values["camera"] = self.camera()
        return self.session.set_tag(target=target, **values)

    def do_uvw_from_tag(self) -> bool:
        with self.session.grouped():
            self.store_tag()
            ok = self.session.uvw_from_tag()
        self._load_tag()
        return ok

    def do_unwrap(self) -> dict:
        angle = self.seam_angle.value() if self.unwrap_angle.isChecked() else None
        return self.session.unwrap(self.unwrap_method.currentText(), angle=angle,
                                   pack=self.unwrap_pack.isChecked(), margin=self.pack_margin.value(),
                                   rotate=self.pack_rotate.isChecked())

    def do_relax(self) -> bool:
        return self.session.relax(self.relax_method.currentText(), self.relax_iter.value(),
                                  self.relax_pin_boundary.isChecked(), self.relax_pin_selected.isChecked())

    def do_pack(self) -> bool:
        return self.session.pack(self.pack_margin.value(), self.pack_rotate.isChecked(),
                                 self.pack_equalize.isChecked(), self.pack_align.isChecked())


class _ColorButton(QPushButton):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme.FIELD_H)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._color = QColor(255, 255, 255)
        self._refresh()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color) -> None:
        r, g, b, a = color_tuple(color)
        self._color = QColor.fromRgbF(r, g, b, a)
        self._refresh()

    def _refresh(self) -> None:
        c = self._color
        text = "#000000" if c.lightnessF() > 0.6 else "#ffffff"
        self.setText(c.name().upper())
        self.setStyleSheet(f"QPushButton {{ background: {c.name()}; color: {text}; "
                           f"border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 6px; }}")


class TexturePaintPanel(_Panel):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(scene, "Texture Paint", parent)
        self.setObjectName("qsTexturePaint")
        s = self.session

        g = self.group("Texture")
        self.channel_combo = _combo(CHANNELS, self)
        self.size_combo = _combo([str(v) for v in TEXTURE_SIZES], self)
        self.size_combo.setCurrentText(str(s.texture_size))
        self.cells_spin = _ispin(1, 128, 8, self)
        g.add_widget(_row("Channel", self.channel_combo))
        g.add_widget(_row("Size", self.size_combo))
        g.add_widget(_row("Checker cells", self.cells_spin))
        self.new_button = _button("New", self, self.new_texture)
        self.checker_button = _button("New Checker", self, self.new_checker)
        self.clear_button = _button("Clear", self, self.clear_texture)
        g.add_widget(_buttons(self, self.new_button, self.checker_button, self.clear_button))
        self.load_button = _button("Load PNG", self, self.load_dialog)
        self.save_button = _button("Save PNG", self, self.save_dialog)
        g.add_widget(_buttons(self, self.load_button, self.save_button))
        self.info = QLabel("", self)
        self.info.setObjectName("qsDimLabel")
        self.info.setContentsMargins(INDENT, 0, 8, 0)
        g.add_widget(self.info)

        g = self.group("Brush")
        host = QWidget(self)
        hl = QHBoxLayout(host)
        hl.setContentsMargins(INDENT, 0, 8, 0)
        hl.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_chips: dict[str, Chip] = {}
        for tool in ("paint", "erase", "fill"):
            chip = Chip(tool.capitalize(), host, checked=s.tool == tool)
            chip.clicked.connect(lambda _c=False, t=tool: s.set_tool(t))
            self.tool_group.addButton(chip)
            self.tool_chips[tool] = chip
            hl.addWidget(chip, 1)
        g.add_widget(host)
        self.color_button = _ColorButton(self)
        self.color_button.clicked.connect(self.pick_color)
        self.radius_spin = _spin(0.5, 1024.0, s.brush.radius, 1.0, 1, self, " px")
        self.hardness_spin = _spin(0.0, 100.0, s.brush.hardness * 100.0, 5.0, 1, self, " %")
        self.opacity_spin = _spin(0.0, 100.0, s.brush.opacity * 100.0, 5.0, 1, self, " %")
        self.spacing_spin = _spin(1.0, 400.0, s.brush.spacing * 100.0, 5.0, 1, self, " %")
        self.tolerance_spin = _spin(0.0, 100.0, s.brush.tolerance * 100.0, 1.0, 1, self, " %")
        g.add_widget(_row("Color", self.color_button))
        g.add_widget(_row("Radius", self.radius_spin))
        g.add_widget(_row("Hardness", self.hardness_spin))
        g.add_widget(_row("Opacity", self.opacity_spin))
        g.add_widget(_row("Spacing", self.spacing_spin))
        g.add_widget(_row("Fill tolerance", self.tolerance_spin))
        self.wrap_check = _check("Wrap at borders", bool(s.brush.wrap), self)
        g.add_widget(_row("", self.wrap_check))
        self.fill_button = _button("Fill Canvas", self, s.fill_canvas)
        g.add_widget(_buttons(self, self.fill_button))

        g = self.group("3D Painting")
        self.project_check = _check("Paint on the object in the 3D view", False, self)
        g.add_widget(_row("", self.project_check))
        self.finish()

        self.channel_combo.currentTextChanged.connect(s.set_channel)
        self.size_combo.currentTextChanged.connect(self._on_size)
        self.radius_spin.valueChanged.connect(lambda v: s.set_brush(radius=float(v)))
        self.hardness_spin.valueChanged.connect(lambda v: s.set_brush(hardness=float(v) / 100.0))
        self.opacity_spin.valueChanged.connect(lambda v: s.set_brush(opacity=float(v) / 100.0))
        self.spacing_spin.valueChanged.connect(lambda v: s.set_brush(spacing=float(v) / 100.0))
        self.tolerance_spin.valueChanged.connect(lambda v: s.set_brush(tolerance=float(v) / 100.0))
        self.wrap_check.toggled.connect(lambda on: s.set_brush(wrap=bool(on)))
        self.project_check.toggled.connect(lambda on: setattr(s, "project_paint", bool(on)))
        s.toolChanged.connect(self._sync_tool)
        s.textureChanged.connect(self._sync_info)
        s.channelChanged.connect(self._sync_channel)
        s.objectChanged.connect(self._sync_info)
        s.brushChanged.connect(self._sync_brush)
        self.color_button.set_color(s.brush.color)
        self._sync_info()

    def _sync_brush(self) -> None:
        b = self.session.brush
        for spin, value in ((self.radius_spin, float(b.radius)), (self.hardness_spin, float(b.hardness) * 100.0),
                            (self.opacity_spin, float(b.opacity) * 100.0),
                            (self.spacing_spin, float(b.spacing) * 100.0),
                            (self.tolerance_spin, float(b.tolerance) * 100.0)):
            if abs(spin.value() - value) > 1e-9:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        if self.wrap_check.isChecked() != bool(b.wrap):
            self.wrap_check.blockSignals(True)
            self.wrap_check.setChecked(bool(b.wrap))
            self.wrap_check.blockSignals(False)
        self.color_button.set_color(b.color)

    def _on_size(self, text: str) -> None:
        try:
            self.session.texture_size = int(text)
        except ValueError:
            return
        canvas = self.session.canvas(create=False)
        size = int(text)
        if canvas is None or max(canvas.width, canvas.height) == size:
            return
        k = size / float(max(canvas.width, canvas.height))
        w = max(1, int(round(canvas.width * k)))
        h = max(1, int(round(canvas.height * k)))
        canvas.resize(w, h)
        self.session.commit_texture(canvas)
        self._sync_info()

    def _sync_tool(self, tool: str) -> None:
        chip = self.tool_chips.get(tool)
        if chip is not None:
            chip.setChecked(True)
        else:
            self.tool_group.setExclusive(False)
            for c in self.tool_chips.values():
                c.setChecked(False)
            self.tool_group.setExclusive(True)

    def _sync_channel(self, channel: str) -> None:
        if self.channel_combo.currentText() != channel:
            self.channel_combo.setCurrentText(channel)

    def _sync_info(self) -> None:
        canvas = self.session.canvas(create=False)
        if self.session.obj is None:
            self.info.setText("No polygon object")
        elif canvas is None:
            self.info.setText(f"No {self.session.channel} texture yet")
        else:
            path = f"  {canvas.path}" if canvas.path else ""
            self.info.setText(f"{canvas.width} x {canvas.height}{path}")

    def set_color(self, color) -> None:
        self.color_button.set_color(color)
        self.session.set_brush(color=color_tuple(color))

    def pick_color(self) -> None:
        chosen = QColorDialog.getColor(self.color_button.color(), self, "Brush Color",
                                       QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if chosen.isValid():
            self.set_color(chosen)

    def new_texture(self):
        return self.session.new_canvas(int(self.size_combo.currentText()), fill=self.session.brush.color)

    def new_checker(self):
        return self.session.new_canvas(int(self.size_combo.currentText()), checker=True,
                                       cells=self.cells_spin.value())

    def clear_texture(self) -> bool:
        canvas = self.session.canvas(create=True)
        if canvas is None:
            return False
        canvas.clear()
        self.session.commit_texture(canvas)
        return True

    def load_from(self, path: str) -> bool:
        ok = self.session.load_texture(path)
        if ok:
            canvas = self.session.canvas(create=False)
            self.size_combo.blockSignals(True)
            longest = str(max(canvas.width, canvas.height)) if canvas is not None else ""
            if canvas is not None and longest in [self.size_combo.itemText(i)
                                                  for i in range(self.size_combo.count())]:
                self.size_combo.setCurrentText(longest)
            self.size_combo.blockSignals(False)
        self._sync_info()
        return ok

    def save_to(self, path: str) -> bool:
        ok = self.session.save_texture(path)
        self._sync_info()
        return ok

    def load_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Texture", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.load_from(path)

    def save_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Texture", f"{self.session.channel.lower()}.png",
                                              "PNG (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            self.save_to(path)


class ViewportPainter(QObject):

    def __init__(self, viewport, scene=None, parent: QObject | None = None) -> None:
        super().__init__(parent or viewport)
        self.viewport = viewport
        self.session = session_for(scene if scene is not None else get_scene())
        self._active = False
        viewport.installEventFilter(self)

    def _ray(self, pos):
        fn = getattr(self.viewport, "ray_at", None)
        if fn is None:
            return None
        return fn(pos)

    def eventFilter(self, watched, event) -> bool:
        s = self.session
        if not s.project_paint or s.tool not in ("paint", "erase", "fill"):
            if self._active and event.type() == QEvent.Type.MouseButtonRelease:
                self._active = False
                s.paint_end()
            return False
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            ray = self._ray(event.position())
            if ray is None:
                return False
            hit = s.paint_ray(ray[0], ray[1], continue_stroke=False)
            self._active = hit is not None and s.tool != "fill"
            return hit is not None
        if kind == QEvent.Type.MouseMove and self._active:
            ray = self._ray(event.position())
            if ray is not None:
                s.paint_ray(ray[0], ray[1], continue_stroke=True)
            return True
        if kind == QEvent.Type.MouseButtonRelease and self._active:
            self._active = False
            s.paint_end()
            return True
        return False
