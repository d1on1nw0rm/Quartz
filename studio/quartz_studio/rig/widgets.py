from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QEvent, QLocale, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import theme
from ..scene import get_scene
from ..widgets.common import CollapsibleGroup, FieldRow, prepare_combo
from . import ik
from . import joints as jt
from . import mathutil as mu
from . import runtime
from . import skin as sk
from .paint import WeightBrush, WeightPainter

__all__ = [
    "RigPanel",
    "JointList",
    "WeightPaintPanel",
    "WeightPreview",
    "WeightPaintController",
    "weight_color",
    "find_canvas",
    "rename_joint",
]

GAP = 4
MARGIN = 8
PREVIEW_MIN_H = 256
BRUSH_PEN = 2
POINT_SIZE = 4
TREE_INDENT = 12

_RAMP = (theme.TEXT_MUTED, theme.AXIS_Z, theme.ACCENT, theme.TINT_CITRINE, theme.AXIS_X)


def weight_color(value: float) -> QColor:
    v = float(np.clip(value, 0.0, 1.0)) * (len(_RAMP) - 1)
    i = min(int(math.floor(v)), len(_RAMP) - 2)
    t = v - i
    a, b = QColor(_RAMP[i]), QColor(_RAMP[i + 1])
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def find_canvas():
    app = QApplication.instance()
    if app is None:
        return None
    for w in app.allWidgets():
        if type(w).__name__ == "ViewportCanvas" and hasattr(w, "ray_at"):
            return w
    return None


def _button(text: str, slot, parent: QWidget | None = None, checkable: bool = False) -> QPushButton:
    b = QPushButton(text, parent)
    b.setFixedHeight(theme.ROW_H)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setCheckable(checkable)
    if checkable:
        b.toggled.connect(slot)
    else:
        b.clicked.connect(lambda _c=False: slot())
    return b


def _plain_locale() -> QLocale:
    loc = QLocale.c()
    loc.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    return loc


def _spin(lo: float, hi: float, value: float, step: float = 1.0, decimals: int = 1,
          suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setLocale(_plain_locale())
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    s.setFixedHeight(theme.FIELD_H)
    s.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    return s


def _ispin(lo: int, hi: int, value: int) -> QSpinBox:
    s = QSpinBox()
    s.setLocale(_plain_locale())
    s.setRange(lo, hi)
    s.setValue(value)
    s.setKeyboardTracking(False)
    s.setFixedHeight(theme.FIELD_H)
    s.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    return s


def _combo(items) -> QComboBox:
    c = QComboBox()
    c.addItems(list(items))
    c.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    c.setFixedHeight(theme.FIELD_H)
    prepare_combo(c)
    return c


def _check(checked: bool) -> QCheckBox:
    c = QCheckBox()
    c.setChecked(checked)
    c.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return c


def _row(*widgets: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(MARGIN, 0, MARGIN, 0)
    lay.setSpacing(GAP)
    for x in widgets:
        lay.addWidget(x, 1)
    return w


def _check_row(label: str, box: QCheckBox) -> FieldRow:
    row = FieldRow(label)
    row.editor = box
    row.add_widget(box)
    row.add_stretch(1)
    return row


def _fill_combo(combo: QComboBox, items: list[str], keep: str | None = None) -> None:
    current = combo.currentText() if keep is None else keep
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(items)
    if current in items:
        combo.setCurrentIndex(items.index(current))
    combo.blockSignals(False)


class _Panel(QWidget):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self.guard = runtime.guard_for(self.scene)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, MARGIN)
        self.body_layout.setSpacing(0)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)
        self.status = QLabel("", self)
        self.status.setObjectName("qsDimLabel")
        self.status.setWordWrap(True)
        self.status.setContentsMargins(MARGIN, GAP, MARGIN, GAP)
        outer.addWidget(self.status)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self.refresh)

    def group(self, title: str) -> CollapsibleGroup:
        g = CollapsibleGroup(title, self.body)
        self.body_layout.addWidget(g)
        return g

    def finish(self) -> None:
        self.body_layout.addStretch(1)

    def schedule_refresh(self, *_a) -> None:
        self._refresh_timer.start()

    def refresh(self) -> None:
        pass

    def say(self, text: str) -> None:
        self.status.setText(text)

    def run(self, fn, *args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
            self.say(str(exc))
            return None
        self.refresh()
        return result


class RigPanel(_Panel):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.updater = runtime.updater_for(self.scene)

        g = self.group("Joints")
        self.joint_name = QLineEdit("Joint")
        self.joint_name.setFixedHeight(theme.FIELD_H)
        g.add_widget(FieldRow("Name", self.joint_name))
        self.joint_radius = _spin(0.0, 1000.0, 4.0, 0.5, 1, " cm")
        g.add_widget(FieldRow("Radius", self.joint_radius))
        self.chain_order = _combo(("Index", "Nearest"))
        g.add_widget(FieldRow("Point Order", self.chain_order))
        self.orient = _check(True)
        g.add_widget(_check_row("Orient", self.orient))
        g.add_widget(_row(_button("Create Joint", self.create_joint),
                          _button("Chain from Points", self.chain_from_points)))
        g.add_widget(_row(_button("Orient Joints", self.orient_joints),
                          _button("Align Bones", self.align_bones)))

        g = self.group("Skin")
        self.skeleton = _combo(("All Joints",))
        g.add_widget(FieldRow("Skeleton", self.skeleton))
        self.method = _combo(sk.SKIN_METHODS)
        self.method.currentTextChanged.connect(self._method_changed)
        g.add_widget(FieldRow("Method", self.method))
        self.falloff = _spin(0.5, 16.0, 4.0, 0.5, 1)
        g.add_widget(FieldRow("Falloff", self.falloff))
        self.influences = _ispin(1, 16, 4)
        g.add_widget(FieldRow("Max Influences", self.influences))
        self.smooth = _ispin(0, 20, 1)
        g.add_widget(FieldRow("Smooth Passes", self.smooth))
        self.mirror_dir = _combo(("Left to Right", "Right to Left"))
        g.add_widget(FieldRow("Mirror", self.mirror_dir))
        g.add_widget(_row(_button("Bind Skin", self.bind), _button("Auto Weights", self.auto_weights)))
        g.add_widget(_row(_button("Unbind", self.unbind), _button("Mirror Weights", self.mirror)))
        g.add_widget(_row(_button("Set Bind Pose", self.set_bind_pose),
                          _button("Go to Bind Pose", self.reset_pose)))

        g = self.group("IK")
        self.ik_start = _combo(())
        self.ik_start.currentTextChanged.connect(self._ik_start_changed)
        g.add_widget(FieldRow("Start", self.ik_start))
        self.ik_end = _combo(())
        g.add_widget(FieldRow("End", self.ik_end))
        self.ik_solver = _combo(ik.SOLVERS)
        self.ik_solver.currentTextChanged.connect(lambda v: self._ik_edit(solver=v))
        g.add_widget(FieldRow("Solver", self.ik_solver))
        self.ik_goal = _check(True)
        g.add_widget(_check_row("Create Goal", self.ik_goal))
        self.ik_pole = _check(True)
        g.add_widget(_check_row("Create Pole", self.ik_pole))
        self.ik_blend = _spin(0.0, 100.0, 100.0, 5.0, 0, " %")
        self.ik_blend.valueChanged.connect(lambda v: self._ik_edit(blend=v / 100.0))
        g.add_widget(FieldRow("FK / IK Blend", self.ik_blend))
        self.ik_iterations = _ispin(1, 500, 24)
        self.ik_iterations.valueChanged.connect(lambda v: self._ik_edit(iterations=v))
        g.add_widget(FieldRow("Iterations", self.ik_iterations))
        self.ik_twist = _spin(-180.0, 180.0, 0.0, 5.0, 1, " °")
        self.ik_twist.valueChanged.connect(lambda v: self._ik_edit(twist=v))
        g.add_widget(FieldRow("Pole Twist", self.ik_twist))
        self.ik_match = _check(False)
        self.ik_match.toggled.connect(lambda v: self._ik_edit(match_goal_rotation=bool(v)))
        g.add_widget(_check_row("Match Goal Rotation", self.ik_match))
        g.add_widget(_row(_button("Add IK", self.add_ik), _button("Remove IK", self.remove_ik)))
        g.add_widget(_row(_button("Store FK Pose", self.store_fk), _button("Solve", self.solve)))

        g = self.group("Character")
        self.biped_height = _spin(10.0, 10000.0, 180.0, 5.0, 1, " cm")
        g.add_widget(FieldRow("Height", self.biped_height))
        self.biped_prefix = QLineEdit("")
        self.biped_prefix.setFixedHeight(theme.FIELD_H)
        g.add_widget(FieldRow("Prefix", self.biped_prefix))
        self.biped_ik = _check(True)
        g.add_widget(_check_row("Limb IK", self.biped_ik))
        g.add_widget(_row(_button("Build Biped", self.build_biped)))

        g = self.group("Pose")
        self.live = _check(self.updater.is_enabled())
        self.live.toggled.connect(self.set_live)
        g.add_widget(_check_row("Live Update", self.live))
        g.add_widget(_row(_button("Update Rig", self.update_rig)))
        self.finish()

        self._ik_loading = False
        self.scene.objectsChanged.connect(self.schedule_refresh)
        self.scene.selectionChanged.connect(self.schedule_refresh)
        self.refresh()

    def _active(self):
        a = self.scene.active
        return a if a is not None and a in self.scene.objects else None

    def refresh(self) -> None:
        names = [j.name for j in jt.joints(self.scene)]
        _fill_combo(self.skeleton, ["All Joints"] + [r.name for r in jt.root_joints(self.scene)])
        _fill_combo(self.ik_start, names)
        _fill_combo(self.ik_end, names)
        a = self._active()
        if a is not None and sk.is_skinned(a):
            self.method.blockSignals(True)
            self.method.setCurrentText(sk.skin_of(a).get("method", "Linear"))
            self.method.blockSignals(False)
        self._ik_start_changed(self.ik_start.currentText())
        if self.live.isChecked() != self.updater.is_enabled():
            self.live.blockSignals(True)
            self.live.setChecked(self.updater.is_enabled())
            self.live.blockSignals(False)

    def _joint(self, name: str):
        return jt.find_joint(self.scene, name)

    def _ik_start_changed(self, name: str) -> None:
        start = self._joint(name)
        tag = ik.ik_tag(start) if start is not None else None
        if tag is None:
            return
        self._ik_loading = True
        try:
            self.ik_end.setCurrentText(tag.get("end", ""))
            self.ik_solver.setCurrentText(tag.get("solver", "Auto"))
            self.ik_blend.setValue(float(tag.get("blend", 1.0)) * 100.0)
            self.ik_iterations.setValue(int(tag.get("iterations", 24)))
            self.ik_twist.setValue(float(tag.get("twist", 0.0)))
            self.ik_match.setChecked(bool(tag.get("match_goal_rotation", False)))
        finally:
            self._ik_loading = False

    def _ik_edit(self, **values) -> None:
        if self._ik_loading:
            return
        start = self._joint(self.ik_start.currentText())
        if start is None or ik.ik_tag(start) is None:
            return
        ik.set_ik(self.scene, start, **values)
        runtime.evaluate_rig(self.scene)

    def create_joint(self):
        a = self._active()
        parent = a if jt.is_joint(a) else None
        where = None
        if parent is not None:
            tip = np.asarray(parent.params.get("tip", (0.0, 0.0, 0.0)), float)
            where = mu.transform_points(parent.world_matrix(), tip)[0]
        obj = self.run(jt.create_joint, self.scene, self.joint_name.text().strip() or "Joint",
                       parent=parent, world_position=where, radius=self.joint_radius.value())
        if obj is not None:
            self.say(f"Created {obj.name}")
        return obj

    def chain_from_points(self):
        made = self.run(jt.chain_from_selection, self.scene, self.chain_order.currentText(),
                        self.orient.isChecked(), self.joint_name.text().strip() or "Joint")
        if made:
            for j in made:
                j.params["radius"] = float(self.joint_radius.value())
                j._dirty = True
            self.scene.evaluate()
            self.scene.changed.emit()
            self.say(f"Created a chain of {len(made)} joints")
        return made

    def orient_joints(self):
        a = self._active()
        targets = jt.joint_hierarchy(self.scene, a) if jt.is_joint(a) else None
        n = self.run(jt.orient_joints, self.scene, targets)
        if n is not None:
            self.say(f"Oriented {n} joints")
        return n

    def align_bones(self):
        n = self.run(jt.update_bone_display, self.scene)
        if n is not None:
            self.say(f"Updated {n} bones")
        return n

    def _skeleton_joints(self):
        name = self.skeleton.currentText()
        root = self._joint(name) if name != "All Joints" else None
        return jt.joint_hierarchy(self.scene, root) if root is not None else None

    def bind(self):
        a = self._active()
        if a is None:
            self.say("Select the object to bind")
            return None
        obj = self.run(sk.bind_skin, self.scene, a, self._skeleton_joints(), True,
                       self.method.currentText(), self.falloff.value(), self.influences.value(),
                       self.smooth.value())
        if obj is not None:
            runtime.evaluate_rig(self.scene)
            self.say(f"Bound {obj.name} to {len(sk.skin_of(obj)['joints'])} joints")
        return obj

    def _skinned_active(self):
        a = self._active()
        if a is None or not sk.is_skinned(a):
            self.say("Select a skinned object")
            return None
        return a

    def auto_weights(self):
        a = self._skinned_active()
        if a is None:
            return None
        w = self.run(sk.auto_weights, self.scene, a, self.falloff.value(), self.influences.value(),
                     self.smooth.value())
        if w is not None:
            runtime.evaluate_rig(self.scene)
            self.say(f"Computed weights for {w.shape[0]} points")
        return w

    def unbind(self):
        a = self._skinned_active()
        if a is None:
            return False
        ok = bool(self.run(sk.unbind_skin, self.scene, a))
        if ok:
            self.say(f"Unbound {a.name}")
        return ok

    def mirror(self):
        a = self._skinned_active()
        if a is None:
            return None
        w = self.run(sk.mirror_weights, self.scene, a, 0, self.mirror_dir.currentIndex() == 1)
        if w is not None:
            runtime.evaluate_rig(self.scene)
            self.say("Mirrored weights")
        return w

    def set_bind_pose(self):
        a = self._skinned_active()
        if a is None:
            return False
        ok = bool(self.run(sk.rebind_skin, self.scene, a))
        if ok:
            self.say(f"Stored the current pose of {a.name} as bind pose")
        return ok

    def reset_pose(self):
        n = self.run(sk.reset_bind_pose, self.scene, None)
        if n is not None:
            self.say(f"Restored {n} joints to the bind pose")
        return n

    def _method_changed(self, method: str) -> None:
        a = self._active()
        if a is not None and sk.is_skinned(a):
            sk.set_skin_method(self.scene, a, method)
            runtime.evaluate_rig(self.scene)

    def add_ik(self):
        start = self._joint(self.ik_start.currentText())
        end = self._joint(self.ik_end.currentText())
        if start is None or end is None:
            self.say("Choose a start and an end joint")
            return None
        tag = self.run(ik.add_ik, self.scene, start, end, self.ik_solver.currentText(),
                       create_goal=self.ik_goal.isChecked(), create_pole=self.ik_pole.isChecked(),
                       blend=self.ik_blend.value() / 100.0, iterations=self.ik_iterations.value(),
                       twist=self.ik_twist.value(), match_goal_rotation=self.ik_match.isChecked())
        if tag is not None:
            runtime.evaluate_rig(self.scene)
            self.say(f"IK from {start.name} to {end.name}")
        return tag

    def remove_ik(self):
        start = self._joint(self.ik_start.currentText())
        if start is None:
            return False
        ok = bool(self.run(ik.remove_ik, self.scene, start, True))
        self.say(f"Removed IK from {start.name}" if ok else f"{start.name} has no IK")
        if ok:
            runtime.evaluate_rig(self.scene)
        return ok

    def store_fk(self):
        start = self._joint(self.ik_start.currentText())
        tag = ik.store_fk(self.scene, start) if start is not None else None
        self.say("Stored the FK pose" if tag else "The start joint has no IK")
        return tag

    def solve(self):
        result = self.run(runtime.evaluate_rig, self.scene)
        if result is not None:
            self.say(f"Solved {result['ik']} IK chains, deformed {result['deformed']} objects")
        return result

    def build_biped(self):
        made = self.run(jt.build_biped, self.scene, self.biped_height.value(), True,
                        self.biped_prefix.text().strip(), (0.0, 0.0, 0.0), self.biped_ik.isChecked())
        if made:
            runtime.evaluate_rig(self.scene)
            self.say(f"Built a biped with {len(made)} joints")
        return made

    def set_live(self, on: bool) -> None:
        self.updater.set_enabled(bool(on))
        self.say("Live update on" if on else "Live update off")

    def update_rig(self):
        return self.solve()


class JointList(QWidget):

    jointActivated = Signal(object)

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self.guard = runtime.guard_for(self.scene)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GAP)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Filter joints")
        self.filter.setFixedHeight(theme.FIELD_H)
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(_row(self.filter))
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Joint", "Info"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(TREE_INDENT)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tree, 1)
        lay.addWidget(_row(_button("Add Child", self.add_child), _button("Delete", self.delete_joint)))
        self.count_label = QLabel("", self)
        self.count_label.setObjectName("qsDimLabel")
        self.count_label.setContentsMargins(MARGIN, 0, MARGIN, GAP)
        lay.addWidget(self.count_label)
        self._items: dict[int, QTreeWidgetItem] = {}
        self._objects: dict[int, object] = {}
        self._building = False
        self.tree.itemSelectionChanged.connect(self._on_select)
        self.tree.itemChanged.connect(self._on_rename)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.refresh)
        self._info_timer = QTimer(self)
        self._info_timer.setSingleShot(True)
        self._info_timer.setInterval(0)
        self._info_timer.timeout.connect(self.update_info)
        self.scene.objectsChanged.connect(self._timer.start)
        self.scene.changed.connect(self._info_timer.start)
        self.scene.selectionChanged.connect(self._sync_selection)
        self.refresh()

    def _skin_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for o in self.scene.objects:
            for name in set(sk.skin_joint_names(o)):
                counts[name] = counts.get(name, 0) + 1
        return counts

    def _info(self, j, counts: dict[str, int] | None = None) -> str:
        bits = []
        raw = j.extras.get("ik") if isinstance(getattr(j, "extras", None), dict) else None
        if isinstance(raw, dict):
            bits.append(f"IK to {raw.get('end', '')}")
        n = (self._skin_counts() if counts is None else counts).get(j.name, 0)
        if n:
            bits.append(f"skins {n}")
        return ", ".join(bits)

    def update_info(self) -> int:
        counts = self._skin_counts()
        updated = 0
        self._building = True
        try:
            for key, item in self._items.items():
                j = self._objects.get(key)
                if j is None or j not in self.scene.objects:
                    continue
                text = self._info(j, counts)
                if item.text(1) != text:
                    item.setText(1, text)
                    updated += 1
        finally:
            self._building = False
        return updated

    def refresh(self) -> None:
        self._building = True
        try:
            self.tree.clear()
            self._items.clear()
            self._objects.clear()
            counts = self._skin_counts()

            def add(j, parent_item) -> None:
                item = QTreeWidgetItem([j.name, self._info(j, counts)])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setData(0, Qt.ItemDataRole.UserRole, id(j))
                self._items[id(j)] = item
                self._objects[id(j)] = j
                if parent_item is None:
                    self.tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
                for c in jt.joint_children(self.scene, j):
                    add(c, item)

            for r in jt.root_joints(self.scene):
                add(r, None)
            self.tree.expandAll()
            self.count_label.setText(f"{len(self._items)} joints")
        finally:
            self._building = False
        self._apply_filter(self.filter.text())
        self._sync_selection()

    def item_for(self, joint) -> QTreeWidgetItem | None:
        return self._items.get(id(joint))

    def joint_at(self, item: QTreeWidgetItem | None):
        if item is None:
            return None
        return self._objects.get(item.data(0, Qt.ItemDataRole.UserRole))

    def selected_joint(self):
        items = self.tree.selectedItems()
        return self.joint_at(items[0]) if items else None

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for item in self._items.values():
            item.setHidden(bool(needle) and needle not in item.text(0).lower())
        if needle:
            for item in self._items.values():
                if not item.isHidden():
                    p = item.parent()
                    while p is not None:
                        p.setHidden(False)
                        p = p.parent()

    def _sync_selection(self) -> None:
        a = self.scene.active
        item = self._items.get(id(a)) if jt.is_joint(a) else None
        self._building = True
        try:
            self.tree.clearSelection()
            if item is not None:
                item.setSelected(True)
                self.tree.setCurrentItem(item)
        finally:
            self._building = False

    def _on_select(self) -> None:
        if self._building:
            return
        j = self.selected_joint()
        if j is not None and j in self.scene.objects:
            self.scene.set_active(j)
            self.jointActivated.emit(j)

    def _on_rename(self, item: QTreeWidgetItem, column: int) -> None:
        if self._building or column != 0:
            return
        j = self.joint_at(item)
        if j is None:
            return
        new = item.text(0).strip()
        if new and new != j.name:
            rename_joint(self.scene, j, new)
        self._timer.start()

    def add_child(self):
        parent = self.selected_joint()
        where = None
        if parent is not None:
            tip = np.asarray(parent.params.get("tip", (0.0, 0.0, 0.0)), float)
            if float(np.linalg.norm(tip)) < mu.EPS:
                tip = np.array([float(parent.params.get("radius", 4.0)) * 4.0, 0.0, 0.0])
            where = mu.transform_points(parent.world_matrix(), tip)[0]
        j = jt.create_joint(self.scene, "Joint", parent=parent, world_position=where)
        if parent is not None:
            jt.update_bone_display(self.scene, [parent])
        self.refresh()
        return j

    def delete_joint(self) -> bool:
        j = self.selected_joint()
        if j is None:
            return False
        self.scene.remove_object(j)
        self.refresh()
        return True


def rename_joint(scene, joint, name: str) -> str:
    return runtime.rename_object(scene, joint, name)


class WeightPreview(QWidget):

    stroked = Signal()

    def __init__(self, painter: WeightPainter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.painter = painter
        self.setMinimumHeight(PREVIEW_MIN_H)
        self.setMouseTracking(True)
        self.yaw = 0.0
        self.pitch = 0.0
        self.zoom = 1.0
        self._hover: QPointF | None = None
        self._orbit: QPointF | None = None
        self._painting = False

    def view_rotation(self) -> np.ndarray:
        return mu.matrix_from_euler((self.pitch, self.yaw, 0.0)).T

    def _frame(self, pts: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
        rot = self.view_rotation()
        if not len(pts):
            return rot, 1.0, np.zeros(3)
        center = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
        cam = (pts - center) @ rot.T
        extent = max(float(np.abs(cam[:, :2]).max()), 1e-6)
        usable = max(min(self.width(), self.height()) / 2.0 - MARGIN * 2, 1.0)
        return rot, usable / extent * self.zoom, center

    def project(self, pts: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
        pts = np.asarray(pts, float).reshape(-1, 3)
        rot, scale, center = self._frame(pts)
        cam = (pts - center) @ rot.T
        xy = np.column_stack([self.width() / 2.0 + cam[:, 0] * scale, self.height() / 2.0 - cam[:, 1] * scale])
        return xy, scale, center, rot

    def screen_ray(self, pos: QPointF) -> tuple[np.ndarray, np.ndarray, float] | None:
        if not self.painter.valid():
            return None
        pts = self.painter.world_points()
        _xy, scale, center, rot = self.project(pts)
        local = np.array([(pos.x() - self.width() / 2.0) / scale, -(pos.y() - self.height() / 2.0) / scale, 0.0])
        origin = center + rot.T @ local
        direction = rot.T @ np.array([0.0, 0.0, 1.0])
        return origin, direction, scale

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(theme.SURFACE_FIELD))
        if not self.painter.valid():
            p.setPen(QColor(theme.TEXT_MUTED))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "Select a skinned object")
            p.end()
            return
        obj = self.painter.target
        xy, scale, _c, _r = self.project(self.painter.world_points())
        p.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 1))
        for a, b in obj.mesh.edges:
            p.drawLine(QPointF(*xy[a]), QPointF(*xy[b]))
        w = self.painter.weights()
        joint = min(self.painter.brush.joint, max(w.shape[1] - 1, 0)) if w is not None else 0
        values = w[:, joint] if w is not None and w.shape[1] else np.zeros(len(xy))
        p.setPen(Qt.PenStyle.NoPen)
        half = POINT_SIZE / 2.0
        for (x, y), v in zip(xy, values):
            p.setBrush(weight_color(v))
            p.drawEllipse(QRectF(x - half, y - half, POINT_SIZE, POINT_SIZE))
        if self._hover is not None:
            r = self.painter.brush.radius * scale
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(theme.ACCENT), BRUSH_PEN))
            p.drawEllipse(self._hover, r, r)
        p.end()

    def dab(self, pos: QPointF) -> bool:
        ray = self.screen_ray(pos)
        if ray is None:
            return False
        origin, direction, _s = ray
        return self.painter.dab_cylinder(origin, direction)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton and not (e.modifiers() & Qt.KeyboardModifier.AltModifier):
            if self.painter.begin_stroke():
                self._painting = True
                self.dab(e.position())
                self.update()
            e.accept()
            return
        if e.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) or e.button() == Qt.MouseButton.LeftButton:
            self._orbit = e.position()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        self._hover = e.position()
        if self._painting:
            self.dab(e.position())
        elif self._orbit is not None:
            d = e.position() - self._orbit
            self._orbit = e.position()
            self.yaw = (self.yaw + d.x() * 0.5) % 360.0
            self.pitch = float(np.clip(self.pitch + d.y() * 0.5, -89.0, 89.0))
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._painting:
            self._painting = False
            if self.painter.end_stroke():
                self.stroked.emit()
        self._orbit = None
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = None
        self.update()
        super().leaveEvent(e)

    def wheelEvent(self, e) -> None:
        step = e.angleDelta().y() / 120.0
        self.zoom = float(np.clip(self.zoom * (1.15 ** step), 0.1, 20.0))
        self.update()
        e.accept()


class WeightPaintController(QObject):

    painted = Signal()

    def __init__(self, canvas, scene=None, painter: WeightPainter | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.canvas = canvas
        self.scene = scene if scene is not None else get_scene()
        self.painter = painter if painter is not None else WeightPainter(self.scene)
        self.enabled = False
        self._stroke = False
        if canvas is not None:
            canvas.installEventFilter(self)

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)
        if not self.enabled and self._stroke:
            self._finish()

    def detach(self) -> None:
        self.set_enabled(False)
        if self.canvas is not None:
            self.canvas.removeEventFilter(self)
            self.canvas = None

    def _hit(self, pos):
        if self.canvas is None or not self.painter.valid():
            return None
        ray_at = getattr(self.canvas, "ray_at", None)
        if ray_at is None:
            return None
        origin, direction = ray_at(pos)
        caster = getattr(self.canvas, "raycast", None) or self.scene.raycast
        hit = caster(origin, direction, [self.painter.target])
        if hit is None:
            return None
        return np.asarray(hit[2], float)

    def paint_at(self, pos) -> bool:
        point = self._hit(pos)
        if point is None:
            return False
        if self.painter.dab_sphere(point):
            self.painted.emit()
        return True

    def _finish(self) -> None:
        self._stroke = False
        self.painter.end_stroke()
        self.painted.emit()

    def eventFilter(self, obj, ev) -> bool:
        if not self.enabled or obj is not self.canvas:
            return False
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress and isinstance(ev, QMouseEvent):
            if ev.button() != Qt.MouseButton.LeftButton or ev.modifiers() & Qt.KeyboardModifier.AltModifier:
                return False
            if self._hit(ev.position()) is None:
                return False
            self._stroke = self.painter.begin_stroke()
            self.paint_at(ev.position())
            return True
        if t == QEvent.Type.MouseMove and self._stroke and isinstance(ev, QMouseEvent):
            self.paint_at(ev.position())
            return True
        if t == QEvent.Type.MouseButtonRelease and self._stroke:
            self._finish()
            return True
        return False


class WeightPaintPanel(_Panel):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.brush = WeightBrush()
        self.painter = WeightPainter(self.scene, self.brush)
        self.controller: WeightPaintController | None = None

        g = self.group("Target")
        self.target_label = QLabel("None")
        g.add_widget(FieldRow("Object", self.target_label))
        g.add_widget(_row(_button("Use Active Object", self.pick_active)))
        self.joint_combo = _combo(())
        self.joint_combo.currentIndexChanged.connect(self._joint_changed)
        g.add_widget(FieldRow("Joint", self.joint_combo))

        g = self.group("Brush")
        self.mode = _combo(sk.PAINT_MODES)
        self.mode.currentTextChanged.connect(self._sync_brush)
        g.add_widget(FieldRow("Mode", self.mode))
        self.radius = _spin(0.1, 10000.0, self.brush.radius, 1.0, 1, " cm")
        self.radius.valueChanged.connect(self._sync_brush)
        g.add_widget(FieldRow("Radius", self.radius))
        self.strength = _spin(0.0, 100.0, self.brush.strength * 100.0, 5.0, 0, " %")
        self.strength.valueChanged.connect(self._sync_brush)
        g.add_widget(FieldRow("Strength", self.strength))
        self.falloff = _combo(sk.FALLOFFS)
        self.falloff.currentTextChanged.connect(self._sync_brush)
        g.add_widget(FieldRow("Falloff", self.falloff))
        self.normalize = _check(True)
        self.normalize.toggled.connect(self._sync_brush)
        g.add_widget(_check_row("Normalize", self.normalize))
        self.viewport_toggle = _button("Paint in Viewport", self.set_viewport_paint, checkable=True)
        g.add_widget(_row(self.viewport_toggle))

        g = self.group("Preview")
        self.preview = WeightPreview(self.painter)
        self.preview.stroked.connect(self._after_edit)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(MARGIN, 0, MARGIN, 0)
        hl.addWidget(self.preview)
        g.add_widget(holder)

        g = self.group("Tools")
        self.threshold = _spin(0.0, 100.0, 5.0, 1.0, 1, " %")
        g.add_widget(FieldRow("Prune Below", self.threshold))
        self.limit_count = _ispin(1, 16, 4)
        g.add_widget(FieldRow("Max Influences", self.limit_count))
        g.add_widget(_row(_button("Flood", self.flood), _button("Smooth All", self.smooth_all)))
        g.add_widget(_row(_button("Normalize All", self.normalize_all), _button("Prune", self.prune)))
        g.add_widget(_row(_button("Limit Influences", self.limit), _button("Undo Stroke", self.undo)))
        self.info = QLabel("")
        self.info.setObjectName("qsDimLabel")
        self.info.setWordWrap(True)
        self.info.setContentsMargins(MARGIN, 0, MARGIN, 0)
        g.add_widget(self.info)
        self.finish()

        self.scene.selectionChanged.connect(self._follow_selection)
        self.scene.objectsChanged.connect(self.schedule_refresh)
        self.scene.changed.connect(self._on_scene_changed)
        self._follow_selection()

    def _on_scene_changed(self) -> None:
        if not self.painter.valid():
            a = self.scene.active
            if (a is not None and sk.is_skinned(a)) or self.painter.target is not None:
                self._follow_selection()
        self.preview.update()

    def _sync_brush(self, *_a) -> None:
        self.brush.mode = self.mode.currentText()
        self.brush.radius = float(self.radius.value())
        self.brush.strength = float(self.strength.value()) / 100.0
        self.brush.falloff = self.falloff.currentText()
        self.brush.normalize = self.normalize.isChecked()
        self.brush.joint = max(0, self.joint_combo.currentIndex())
        self.brush.clamp()
        self.preview.update()

    def _joint_changed(self, _i: int) -> None:
        self._sync_brush()
        self._update_info()

    def set_target(self, obj) -> bool:
        if obj is not None and not sk.is_skinned(obj):
            return False
        self.painter.set_target(obj)
        self.refresh()
        return True

    def pick_active(self) -> bool:
        a = self.scene.active
        ok = a is not None and self.set_target(a)
        if not ok:
            self.say("The active object is not skinned")
        return ok

    def select_joint(self, name: str) -> bool:
        names = self.painter.joint_names()
        if name not in names:
            return False
        self.joint_combo.setCurrentIndex(names.index(name))
        return True

    def _follow_selection(self) -> None:
        a = self.scene.active
        if a is not None and sk.is_skinned(a):
            if a is not self.painter.target:
                self.set_target(a)
        elif jt.is_joint(a) and self.painter.valid():
            self.select_joint(a.name)
        elif self.painter.target is None:
            for o in sk.skinned_objects(self.scene):
                self.set_target(o)
                break
        self.refresh()

    def refresh(self) -> None:
        if self.painter.target is not None and self.painter.target not in self.scene.objects:
            self.painter.set_target(None)
        valid = self.painter.valid()
        self.target_label.setText(self.painter.target.name if valid else "None")
        current = self.joint_combo.currentText()
        _fill_combo(self.joint_combo, self.painter.joint_names() if valid else [], current)
        self._sync_brush()
        self._update_info()

    def _update_info(self) -> None:
        if not self.painter.valid():
            self.info.setText("No skinned object")
            return
        s = self.painter.skin()
        w = np.asarray(s["weights"], float)
        j = min(self.brush.joint, w.shape[1] - 1) if w.shape[1] else 0
        counts = sk.influence_counts(s)
        total = float(w[:, j].sum()) if w.shape[1] else 0.0
        affected = int((w[:, j] > 1e-6).sum()) if w.shape[1] else 0
        self.info.setText(f"{len(w)} points, {affected} weighted to this joint (sum {total:.2f}), "
                          f"up to {int(counts.max()) if len(counts) else 0} influences per point")

    def _after_edit(self) -> None:
        self._update_info()
        self.preview.update()

    def _tool(self, label: str, fn, *args) -> bool:
        if not self.painter.valid():
            self.say("Select a skinned object")
            return False
        self.status.setText("")
        ok = bool(self.run(fn, *args))
        if ok:
            self.say(f"{label}: weights changed on {self.painter.target.name}")
        elif not self.status.text():
            self.say(f"{label}: nothing to change")
        self._after_edit()
        return ok

    def flood(self) -> bool:
        return self._tool("Flood", self.painter.flood)

    def smooth_all(self) -> bool:
        return self._tool("Smooth All", self.painter.smooth_all, 1, max(self.brush.strength, 0.1))

    def normalize_all(self) -> bool:
        return self._tool("Normalize All", self.painter.normalize_all)

    def prune(self) -> bool:
        return self._tool("Prune", self.painter.prune, self.threshold.value() / 100.0)

    def limit(self) -> bool:
        return self._tool("Limit Influences", self.painter.limit, self.limit_count.value())

    def undo(self) -> bool:
        ok = self.painter.undo()
        self.say("Undid the last stroke" if ok else "Nothing to undo")
        self._after_edit()
        return ok

    def attach_canvas(self, canvas) -> WeightPaintController:
        if self.controller is not None:
            self.controller.detach()
        self.controller = WeightPaintController(canvas, self.scene, self.painter, self)
        self.controller.painted.connect(self._after_edit)
        return self.controller

    def set_viewport_paint(self, on: bool) -> bool:
        if on and (self.controller is None or self.controller.canvas is None):
            canvas = find_canvas()
            if canvas is None:
                self.say("No viewport found")
                self.viewport_toggle.blockSignals(True)
                self.viewport_toggle.setChecked(False)
                self.viewport_toggle.blockSignals(False)
                return False
            self.attach_canvas(canvas)
        if self.controller is not None:
            self.controller.set_enabled(on)
        self.say("Painting in the viewport" if on else "Viewport painting off")
        return True
