from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit,
                               QSpinBox, QStyle, QStyleOptionSpinBox)

import quartz_studio.scene as scene_mod
from quartz_studio.objects import registry
from quartz_studio.objects.registry import ObjectSpec, Param
from quartz_studio.scene import Mesh
from quartz_studio.widgets import attribute_manager as am_mod
from quartz_studio.widgets.attribute_manager import AttributeManager, ParamEditor, mesh_summary
from quartz_studio.widgets.common import Chip, CollapsibleGroup
from quartz_studio.widgets.coordinates import CoordField

ALL_ID = "test_am_all"
BOX_ID = "test_am_box"
FAIL_ID = "test_am_fail"
BARE_ID = "test_am_bare"
RULE_ID = "test_am_rule"
SHOW_ID = "test_am_show"


def _build_all(p: dict, _inputs: list) -> Mesh:
    if p["size"] <= 0:
        return Mesh.empty()
    m = Mesh.cube(float(p["size"]))
    pts = m.points
    pts[:, 0] *= float(p["ratio"]) * (2.0 if p["mode"] == "Wide" else 1.0)
    pts[:, 1] *= 2.0 if p["mode"] == "Tall" else 1.0
    pts[:, 0] += float(p["twist"]) + float(p["fill"])
    pts[:, 1] += int(p["count"]) * 10.0
    tint = p["tint"]
    pts[:, 2] += tint[0] * 100.0 + tint[1] * 10.0 + tint[2] + (500.0 if p["flip"] else 0.0)
    return m


def _build_box(p: dict, _inputs: list) -> Mesh:
    return Mesh.cube(float(p["edge"]))


def _build_fail(p: dict, _inputs: list) -> Mesh:
    if p["boom"]:
        raise RuntimeError("test build failed")
    return Mesh.cube(50.0)


def _build_bare(_p: dict, _inputs: list) -> Mesh:
    return Mesh.cube(10.0)


registry.register(ObjectSpec(
    ALL_ID, "Test All", "mesh", _build_all,
    params=(
        Param("size", "Size", "distance", 100.0, minimum=0.0, maximum=1000.0, step=5.0, group="Shape"),
        Param("twist", "Twist", "angle", 0.0, minimum=-360.0, maximum=360.0, group="Shape"),
        Param("fill", "Fill", "percent", 50.0, minimum=0.0, maximum=100.0, group="Shape"),
        Param("ratio", "Ratio", "float", 1.0, minimum=0.1, maximum=10.0, step=0.1, group="Shape"),
        Param("count", "Count", "int", 2, minimum=1, maximum=20, group="Shape"),
        Param("flip", "Flip", "bool", False, group="Shape"),
        Param("mode", "Mode", "choice", "Narrow", choices=("Narrow", "Wide", "Tall"), group="Shape"),
        Param("caption", "Caption", "text", "hello", group="Look"),
        Param("tint", "Tint", "vector", (0.5, 0.5, 0.5), minimum=0.0, maximum=1.0, step=0.1,
              group="Look"),
    ), icon="cube"))
registry.register(ObjectSpec(
    BOX_ID, "Test Box", "mesh", _build_box,
    params=(Param("edge", "Edge", "distance", 80.0, minimum=1.0, maximum=500.0, group="Box"),)))
registry.register(ObjectSpec(
    FAIL_ID, "Test Fail", "mesh", _build_fail,
    params=(Param("boom", "Boom", "bool", False, group="Fail"),)))
registry.register(ObjectSpec(BARE_ID, "Test Bare", "mesh", _build_bare))
registry.register(ObjectSpec(
    RULE_ID, "Test Rule", "mesh", _build_bare,
    params=(Param("a", "A", "bool", False, group="Rule"),
            Param("b", "B", "distance", 10.0, minimum=0.0, maximum=100.0, group="Rule"))))
registry.register(ObjectSpec(
    SHOW_ID, "Test Show", "mesh", _build_bare,
    params=(Param("mode", "Mode", "choice", "One", choices=("One", "Two"), group="Show"),
            Param("extra", "Extra", "distance", 5.0, minimum=0.0, maximum=100.0, group="More",
                  show=(("mode", ("Two",)),)))))


def _app() -> QApplication:
    return QApplication.instance() or QApplication([sys.argv[0]])


def _settle(n: int = 2) -> None:
    app = _app()
    for _ in range(n):
        app.processEvents()


def _make(kind: str | None = ALL_ID):
    _app()
    scene = scene_mod.reset_scene()
    am = AttributeManager()
    am.resize(480, 600)
    am.show()
    obj = None
    if kind is not None:
        obj = scene.add_parametric(kind)
    _settle()
    return scene, am, obj


def _done(am: AttributeManager) -> None:
    am.close()
    am.deleteLater()
    _settle()


def _center(mesh: Mesh) -> np.ndarray:
    lo, hi = mesh.bounds()
    return (lo + hi) / 2.0


def _extent(mesh: Mesh) -> np.ndarray:
    lo, hi = mesh.bounds()
    return hi - lo


def _signature(obj) -> tuple:
    return tuple(np.round(obj.mesh.points, 6).ravel().tolist())


def _spin(am: AttributeManager, key: str, index: int = 0):
    return am.object_editors[key].spins()[index]


def _field_text(widget) -> str:
    return widget.lineEdit().text()


def _focus(widget) -> None:
    window = widget.window()
    window.activateWindow()
    window.raise_()
    _settle(3)
    widget.setFocus(Qt.FocusReason.MouseFocusReason)
    _settle(3)


def test_constructible_without_arguments_and_bound_to_scene() -> None:
    _app()
    scene = scene_mod.reset_scene()
    am = AttributeManager()
    assert am._scene is scene_mod.get_scene() is scene
    am.show()
    _settle()
    assert am.header.isVisibleTo(am)
    assert am.header.text() == "Polygon Object [Cube]"
    assert am.object_header.icon_name() == "empty_polygon"
    assert not am.empty_label.isVisibleTo(am)
    _done(am)


def test_header_shows_type_label_and_name() -> None:
    scene, am, obj = _make(ALL_ID)
    assert am.header.text() == f"Test All [{obj.name}]"
    assert am.header.type_text() == "Test All" and am.header.name() == obj.name
    from quartz_studio.widgets.object_manager import object_icon_name

    assert am.header.icon_name() == object_icon_name(obj)
    scene.rename_object(obj, "Renamed")
    assert am.header.text() == "Test All [Renamed]"
    scene.set_active(scene.objects[0])
    assert am.header.text() == "Polygon Object [Cube]"
    _done(am)


def test_rows_built_per_kind() -> None:
    scene, am, obj = _make(ALL_ID)
    spec = registry.get(ALL_ID)
    assert list(am.object_editors) == [p.key for p in spec.params]
    assert list(am.object_rows) == [p.key for p in spec.params]
    for p in spec.params:
        assert am.object_rows[p.key].label.text() == p.label
        assert am.object_rows[p.key].isVisibleTo(am)
    expect = {"size": QDoubleSpinBox, "twist": QDoubleSpinBox, "fill": QDoubleSpinBox,
              "ratio": QDoubleSpinBox, "count": QSpinBox, "flip": QCheckBox,
              "mode": QComboBox, "caption": QLineEdit}
    for key, cls in expect.items():
        widgets = am.object_editors[key].widgets
        assert len(widgets) == 1 and type(widgets[0]).__mro__.count(cls) == 1, key
    assert len(am.object_editors["tint"].spins()) == 3
    assert _spin(am, "size").suffix() == " cm"
    assert _spin(am, "twist").suffix() == " °"
    assert _spin(am, "fill").suffix() == " %"
    assert _spin(am, "count").suffix() == ""
    assert [am.object_editors["mode"].widgets[0].itemText(i)
            for i in range(am.object_editors["mode"].widgets[0].count())] == ["Narrow", "Wide", "Tall"]
    groups = am.object_page.findChildren(CollapsibleGroup)
    assert [g.title_label.text() for g in groups] == ["SHAPE", "LOOK"]
    titles = [g.title_label.text() for g in groups if g.header.isVisibleTo(am)]
    assert titles == ["LOOK"], titles
    assert _field_text(_spin(am, "size")) == "100 cm"
    assert _field_text(_spin(am, "fill")) == "50 %"
    assert am.object_editors["mode"].widgets[0].currentText() == "Narrow"
    assert am.object_editors["caption"].widgets[0].text() == "hello"
    assert [s.value() for s in am.object_editors["tint"].spins()] == [0.5, 0.5, 0.5]
    assert not am.object_editors["flip"].widgets[0].isChecked()
    _done(am)


def test_editing_each_kind_changes_params_and_mesh() -> None:
    scene, am, obj = _make(ALL_ID)
    sig = _signature(obj)

    def changed() -> bool:
        nonlocal sig
        now = _signature(obj)
        flag = now != sig
        sig = now
        return flag

    _spin(am, "size").setValue(300.0)
    assert obj.params["size"] == 300.0 and changed()
    assert abs(_extent(obj.mesh)[1] - 300.0) < 1e-6

    _spin(am, "twist").setValue(40.0)
    assert obj.params["twist"] == 40.0 and changed()
    assert abs(_center(obj.mesh)[0] - 90.0) < 1e-6

    _spin(am, "fill").setValue(10.0)
    assert obj.params["fill"] == 10.0 and changed()
    assert abs(_center(obj.mesh)[0] - 50.0) < 1e-6

    _spin(am, "ratio").setValue(2.5)
    assert obj.params["ratio"] == 2.5 and changed()
    assert abs(_extent(obj.mesh)[0] - 750.0) < 1e-6

    _spin(am, "count").setValue(7)
    assert obj.params["count"] == 7 and isinstance(obj.params["count"], int) and changed()
    assert abs(_center(obj.mesh)[1] - 70.0) < 1e-6

    am.object_editors["flip"].widgets[0].setChecked(True)
    assert obj.params["flip"] is True and changed()
    assert _center(obj.mesh)[2] > 500.0

    combo = am.object_editors["mode"].widgets[0]
    combo.setCurrentIndex(combo.findText("Wide"))
    assert obj.params["mode"] == "Wide" and changed()
    assert abs(_extent(obj.mesh)[0] - 1500.0) < 1e-6

    edit = am.object_editors["caption"].widgets[0]
    edit.setText("changed text")
    edit.editingFinished.emit()
    assert obj.params["caption"] == "changed text"

    sig = _signature(obj)
    tint = am.object_editors["tint"].spins()
    tint[1].setValue(0.9)
    assert obj.params["tint"] == (0.5, 0.9, 0.5) and changed()
    tint[0].setValue(0.2)
    tint[2].setValue(0.7)
    assert obj.params["tint"] == (0.2, 0.9, 0.7)
    assert isinstance(obj.params["tint"], tuple)
    expected_z = 0.2 * 100.0 + 0.9 * 10.0 + 0.7 + 500.0
    assert abs(_center(obj.mesh)[2] - expected_z) < 1e-6
    _done(am)


def test_vector_edit_keeps_other_components_exact() -> None:
    scene, am, obj = _make(ALL_ID)
    scene.set_param(obj, "tint", (0.123456789, 0.5, 0.25))
    _settle()
    am.object_editors["tint"].spins()[2].setValue(0.75)
    assert obj.params["tint"][0] == 0.123456789
    assert obj.params["tint"][2] == 0.75
    _done(am)


def test_clamping_and_field_shows_stored_value() -> None:
    scene, am, obj = _make(ALL_ID)
    ed = am.object_editors["size"]
    ed.edited.emit("size", 5000.0)
    assert obj.params["size"] == 1000.0
    assert ed.spins()[0].value() == 1000.0 and _field_text(ed.spins()[0]) == "1000 cm"
    ed.edited.emit("size", -40.0)
    assert obj.params["size"] == 0.0 and _field_text(ed.spins()[0]) == "0 cm"
    assert obj.mesh.points.shape[0] == 0
    _spin(am, "twist").setValue(900.0)
    assert obj.params["twist"] == 360.0 and _field_text(_spin(am, "twist")) == "360 °"
    am.object_editors["count"].edited.emit("count", 99)
    assert obj.params["count"] == 20 and _spin(am, "count").value() == 20
    am.object_editors["count"].edited.emit("count", 0)
    assert obj.params["count"] == 1 and _spin(am, "count").value() == 1
    am.object_editors["tint"].edited.emit("tint", (5.0, -3.0, 0.25))
    assert obj.params["tint"] == (1.0, 0.0, 0.25)
    assert [s.value() for s in am.object_editors["tint"].spins()] == [1.0, 0.0, 0.25]
    am.object_editors["mode"].edited.emit("mode", "Nonsense")
    assert obj.params["mode"] == "Narrow"
    assert am.object_editors["mode"].widgets[0].currentText() == "Narrow"
    _spin(am, "ratio").lineEdit().setText("0")
    _spin(am, "ratio").interpretText()
    assert obj.params["ratio"] == 1.0 and _field_text(_spin(am, "ratio")) == "1"
    am.object_editors["ratio"].edited.emit("ratio", 0.0)
    assert obj.params["ratio"] == 0.1 and _field_text(_spin(am, "ratio")) == "0.1"
    _done(am)


def test_undo_and_redo_update_the_fields() -> None:
    scene, am, obj = _make(ALL_ID)
    _spin(am, "size").setValue(250.0)
    am.object_editors["flip"].widgets[0].setChecked(True)
    am.object_editors["tint"].spins()[0].setValue(0.9)
    combo = am.object_editors["mode"].widgets[0]
    combo.setCurrentIndex(2)
    assert obj.params["mode"] == "Tall"
    scene.undo()
    _settle()
    assert combo.currentText() == "Narrow"
    scene.undo()
    assert am.object_editors["tint"].spins()[0].value() == 0.5
    scene.undo()
    assert not am.object_editors["flip"].widgets[0].isChecked()
    assert _spin(am, "size").value() == 250.0
    scene.undo()
    assert _spin(am, "size").value() == 100.0 and _field_text(_spin(am, "size")) == "100 cm"
    scene.redo()
    scene.redo()
    scene.redo()
    scene.redo()
    live = scene.active
    assert live.params["size"] == 250.0 and live.params["flip"] is True
    assert _spin(am, "size").value() == 250.0
    assert am.object_editors["flip"].widgets[0].isChecked()
    assert am.object_editors["tint"].spins()[0].value() == 0.9
    assert combo.currentText() == "Tall"
    assert am.header.name() == live.name
    _done(am)


def test_undo_does_not_rebuild_rows_of_same_kind() -> None:
    scene, am, obj = _make(ALL_ID)
    editors = dict(am.object_editors)
    count = am.rebuild_count
    _spin(am, "size").setValue(250.0)
    scene.undo()
    scene.redo()
    assert am.rebuild_count == count
    assert all(am.object_editors[k] is v for k, v in editors.items())
    _done(am)


def test_switching_objects_rebuilds_object_tab() -> None:
    scene, am, a = _make(ALL_ID)
    first_editors = dict(am.object_editors)
    box = scene.add_parametric(BOX_ID)
    _settle()
    assert list(am.object_editors) == ["edge"]
    assert all(old is not am.object_editors.get(k) for k, old in first_editors.items())
    assert am.header.text() == f"Test Box [{box.name}]"
    assert _spin(am, "edge").value() == 80.0
    _spin(am, "edge").setValue(120.0)
    assert box.params["edge"] == 120.0 and a.params["size"] == 100.0
    scene.set_active(a)
    _settle()
    assert list(am.object_editors) == [p.key for p in registry.get(ALL_ID).params]
    assert _spin(am, "size").value() == 100.0
    scene.set_active(box)
    _settle()
    assert _spin(am, "edge").value() == 120.0
    other = scene.add_parametric(BOX_ID)
    scene.set_param(other, "edge", 33.0)
    scene.set_active(other)
    _settle()
    assert _spin(am, "edge").value() == 33.0
    scene.set_active(scene.objects[0])
    _settle()
    assert not am.object_editors and not am.scroll.isVisibleTo(am)
    _done(am)


def test_object_without_params_has_no_object_tab() -> None:
    scene, am, obj = _make(BARE_ID)
    assert not am.object_editors
    assert not am.scroll.isVisibleTo(am)
    assert am.header.isVisibleTo(am)
    assert not am.summary_label.isVisibleTo(am)
    assert am.header.text() == f"Test Bare [{obj.name}]"
    _done(am)


def test_error_message_is_visible() -> None:
    scene, am, obj = _make(FAIL_ID)
    assert not obj.error and not am.error_label.isVisibleTo(am)
    am.object_editors["boom"].widgets[0].setChecked(True)
    assert obj.error
    assert am.error_label.isVisibleTo(am)
    assert obj.error in am.error_label.text()
    am.object_editors["boom"].widgets[0].setChecked(False)
    assert not obj.error and not am.error_label.isVisibleTo(am)
    scene.set_param(obj, "boom", True)
    assert am.error_label.isVisibleTo(am)
    scene.undo()
    _settle()
    assert not am.error_label.isVisibleTo(am) and am.error_label.text() == ""
    _done(am)


def test_empty_state_has_no_controls() -> None:
    scene, am, obj = _make(ALL_ID)
    scene.set_active(None)
    _settle()
    assert am.empty_label.isVisibleTo(am)
    assert not am.header.isVisibleTo(am)
    assert not am.summary_label.isVisibleTo(am)
    assert not am.scroll.isVisibleTo(am)
    assert not am.error_label.isVisibleTo(am)
    assert not am.object_editors and not am.object_rows
    for cls in (QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox):
        assert not [w for w in am.findChildren(cls) if w.isVisibleTo(am)], cls
    scene.set_active(obj)
    _settle()
    assert not am.empty_label.isVisibleTo(am) and am.header.isVisibleTo(am)
    assert am.object_editors
    scene.select_object(False)
    _settle()
    assert am.empty_label.isVisibleTo(am) and not am.object_editors
    scene.select_object(True)
    _settle()
    assert am.object_editors and am.header.isVisibleTo(am)
    scene.remove_object(obj)
    _settle()
    assert scene.active is None or scene.active is not obj
    _done(am)


def test_empty_scene_state() -> None:
    _app()
    scene = scene_mod.reset_scene()
    scene.remove_object(scene.objects[0])
    am = AttributeManager()
    am.show()
    _settle()
    assert scene.active is None
    assert am.empty_label.isVisibleTo(am) and not am.header.isVisibleTo(am)
    scene.add_parametric(BOX_ID)
    _settle()
    assert not am.empty_label.isVisibleTo(am) and am.header.isVisibleTo(am)
    _done(am)


def test_no_row_rebuild_during_edits() -> None:
    scene, am, obj = _make(ALL_ID)
    editors = dict(am.object_editors)
    rows = dict(am.object_rows)
    widgets = {k: list(e.widgets) for k, e in editors.items()}
    page = am.object_page
    count = am.rebuild_count

    def same() -> bool:
        return (am.rebuild_count == count and am.object_page is page
                and all(am.object_editors[k] is e for k, e in editors.items())
                and all(am.object_rows[k] is r for k, r in rows.items())
                and all(list(am.object_editors[k].widgets) == w for k, w in widgets.items()))

    _spin(am, "size").setValue(200.0)
    assert same()
    am.object_editors["flip"].widgets[0].setChecked(True)
    assert same()
    am.object_editors["mode"].widgets[0].setCurrentIndex(1)
    assert same()
    scene.set_param(obj, "count", 9)
    assert same() and _spin(am, "count").value() == 9
    scene.set_object_position(0, 3.0)
    scene.changed.emit()
    scene.selectionChanged.emit()
    scene.objectsChanged.emit()
    assert same()
    _done(am)


def test_refresh_alone_makes_no_edits() -> None:
    scene, am, obj = _make(ALL_ID)
    scene.set_param(obj, "tint", (0.123456789, 0.5, 0.25))
    steps = len(scene._undo)
    params = dict(obj.params)
    calls = []
    original = scene.set_param

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    scene.set_param = spy
    try:
        for _ in range(3):
            scene.changed.emit()
            scene.selectionChanged.emit()
            scene.objectsChanged.emit()
        scene.set_active(scene.objects[0])
        scene.set_active(obj)
    finally:
        del scene.set_param
    assert not calls
    assert len(scene._undo) == steps
    assert obj.params == params
    _done(am)


def test_typing_is_not_overwritten_and_focus_is_kept() -> None:
    scene, am, obj = _make(ALL_ID)
    spin = _spin(am, "size")
    _focus(spin)
    assert spin.lineEdit().hasFocus(), "offscreen focus did not work"
    spin.lineEdit().selectAll()
    QTest.keyClicks(spin.lineEdit(), "42")
    assert spin.lineEdit().isModified()
    typed = spin.lineEdit().text()
    assert "42" in typed
    scene.set_param(obj, "twist", 15.0)
    scene.set_param(obj, "size", 300.0)
    scene.changed.emit()
    assert spin.lineEdit().text() == typed
    assert spin.lineEdit().hasFocus()
    assert _field_text(_spin(am, "twist")) == "15 °"
    QTest.keyClick(spin.lineEdit(), Qt.Key.Key_Return)
    assert obj.params["size"] == 42.0
    assert _field_text(spin) == "42 cm"
    assert spin.lineEdit().hasFocus()
    scene.set_param(obj, "size", 77.0)
    assert _field_text(spin) == "77 cm"
    _done(am)


def test_spin_step_wheel_and_arrows_change_the_value() -> None:
    scene, am, obj = _make(ALL_ID)
    spin = _spin(am, "size")
    spin.stepBy(2)
    assert obj.params["size"] == 110.0
    spin.stepBy(-1)
    assert obj.params["size"] == 105.0
    _focus(spin)
    assert spin.hasFocus(), "offscreen focus did not work"
    local = QPointF(spin.width() / 2, spin.height() / 2)
    event = QWheelEvent(local, spin.mapToGlobal(local), QPoint(0, 0), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(spin, event)
    assert obj.params["size"] == 110.0, obj.params["size"]
    int_spin = _spin(am, "count")
    int_spin.stepBy(3)
    assert obj.params["count"] == 5
    _done(am)


def test_wheel_without_focus_does_not_change_anything() -> None:
    scene, am, obj = _make(ALL_ID)
    spin = _spin(am, "size")
    combo = am.object_editors["mode"].widgets[0]
    spin.clearFocus()
    combo.clearFocus()
    _settle()
    for widget in (spin, combo):
        local = QPointF(widget.width() / 2, widget.height() / 2)
        event = QWheelEvent(local, widget.mapToGlobal(local), QPoint(0, 0), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(widget, event)
    assert obj.params["size"] == 100.0 and obj.params["mode"] == "Narrow"
    _done(am)


def test_drag_on_the_arrows_changes_the_value_in_one_undo_step() -> None:
    scene, am, obj = _make(ALL_ID)
    spin = _spin(am, "size")
    opt = QStyleOptionSpinBox()
    spin.initStyleOption(opt)
    up = spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                     QStyle.SubControl.SC_SpinBoxUp, spin)
    start = up.center()
    before = len(scene._undo)
    QTest.mousePress(spin, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for dx in (8, 16, 24, 32, 40):
        QTest.mouseMove(spin, QPoint(start.x() + dx, start.y()))
        _settle(1)
    QTest.mouseRelease(spin, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       QPoint(start.x() + 40, start.y()))
    _settle()
    assert obj.params["size"] > 100.0, obj.params["size"]
    assert _spin(am, "size").value() == obj.params["size"]
    assert len(scene._undo) - before == 1, len(scene._undo) - before
    scene.undo()
    _settle()
    assert scene.active.params["size"] == 100.0
    assert _spin(am, "size").value() == 100.0
    _done(am)


def test_no_chips_basic_or_coordinates() -> None:
    scene, am, obj = _make(ALL_ID)
    assert not am.findChildren(Chip)
    assert not am.findChildren(CoordField)
    text_edits = set(am.object_editors["caption"].widgets)
    spin_edits = {s.lineEdit() for s in am.findChildren(QDoubleSpinBox) + am.findChildren(QSpinBox)}
    combo_edits = {c.lineEdit() for c in am.findChildren(QComboBox) if c.lineEdit() is not None}
    extra = [e for e in am.findChildren(QLineEdit)
             if e not in text_edits and e not in spin_edits and e not in combo_edits]
    assert not extra, extra
    for name in ("chips", "chip_bar", "chip_group", "name_edit", "enabled_box", "coord_fields",
                 "page_basic", "page_coord", "section_title", "current_tab", "tab_available"):
        assert not hasattr(am, name), name
    for name in ("TAB_NAMES", "TAB_TITLES", "COORD_ROWS", "CHIP_BAR_H", "SECTION_H"):
        assert not hasattr(am_mod, name), name
    assert "mesh_summary" in am_mod.__all__
    assert "TAB_NAMES" not in am_mod.__all__ and "COORD_ROWS" not in am_mod.__all__
    assert am.tabs.tab_texts() == ["Attributes"]
    assert am.header.isVisibleTo(am) and am.scroll.isVisibleTo(am)
    _done(am)


def test_first_group_has_no_header_and_later_groups_collapse() -> None:
    scene, am, a = _make(ALL_ID)
    shape, look = am.object_groups["Shape"], am.object_groups["Look"]
    assert not shape.header.isVisibleTo(am) and shape.is_expanded()
    assert look.header.isVisibleTo(am) and look.body.isVisibleTo(am)
    assert shape.content_layout().spacing() == 2 and look.content_layout().spacing() == 2
    QTest.mouseClick(look.header, Qt.MouseButton.LeftButton)
    _settle()
    assert not look.body.isVisibleTo(am) and not look.is_expanded()
    assert shape.body.isVisibleTo(am)
    box = scene.add_parametric(BOX_ID)
    _settle()
    only = am.object_groups["Box"]
    assert not only.header.isVisibleTo(am) and only.body.isVisibleTo(am)
    scene.set_active(a)
    _settle()
    look = am.object_groups["Look"]
    assert look.header.isVisibleTo(am) and not look.is_expanded()
    assert not look.body.isVisibleTo(am)
    assert am.object_rows["size"].isVisibleTo(am)
    look.header.clicked.emit()
    _settle()
    scene.set_active(box)
    scene.set_active(a)
    _settle()
    assert am.object_groups["Look"].is_expanded()
    assert am.object_groups["Look"].body.isVisibleTo(am)
    _done(am)


def test_editable_mesh_shows_summary() -> None:
    scene, am, _ = _make(None)
    cube = scene.active
    assert cube.kind == "polygon"
    assert am.summary_label.isVisibleTo(am)
    assert am.summary_label.text() == "8 points · 6 polygons"
    assert am.summary_label.objectName() == "qsDimLabel"
    assert am.summary_label.height() == 24
    assert not am.object_editors and not am.scroll.isVisibleTo(am)
    assert am.header.text() == "Polygon Object [Cube]"
    dot = Mesh(np.zeros((1, 3)), [])
    assert mesh_summary(dot) == "1 point"
    line = Mesh(np.array([[0.0, 0, 0], [1.0, 0, 0], [2.0, 0, 0]]), [], [(0, 1), (1, 2)])
    assert mesh_summary(line) == "3 points · 2 edges"
    one = Mesh(np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0]]), [(0, 1, 2)])
    assert mesh_summary(one) == "3 points · 1 polygon"
    edge = Mesh(np.array([[0.0, 0, 0], [1.0, 0, 0]]), [], [(0, 1)])
    assert mesh_summary(edge) == "2 points · 1 edge"
    assert mesh_summary(Mesh.empty()) == "0 points"
    cube.mesh = line
    scene.changed.emit()
    assert am.summary_label.text() == "3 points · 2 edges"
    box = scene.add_parametric(BOX_ID)
    _settle()
    assert not am.summary_label.isVisibleTo(am) and am.scroll.isVisibleTo(am)
    scene.set_active(cube)
    _settle()
    assert am.summary_label.isVisibleTo(am) and not am.scroll.isVisibleTo(am)
    scene.set_active(box)
    _settle()
    _done(am)


def test_spec_applies_attribute_hides_rows() -> None:
    spec = registry.get(RULE_ID)
    old = getattr(spec, "applies", None)
    spec.applies = {"b": lambda v: v["a"]}
    try:
        scene, am, obj = _make(RULE_ID)
        assert am.object_rows["a"].isVisibleTo(am)
        assert not am.object_rows["b"].isVisibleTo(am) and not am.param_applies("b")
        am.object_editors["a"].widgets[0].setChecked(True)
        _settle()
        assert obj.params["a"] is True
        assert am.object_rows["b"].isVisibleTo(am) and am.param_applies("b")
        scene.set_param(obj, "a", False)
        _settle()
        assert not am.object_rows["b"].isVisibleTo(am)
        _done(am)
    finally:
        spec.applies = {} if old is None else old


def test_param_show_hides_rows_and_empty_groups() -> None:
    scene, am, obj = _make(SHOW_ID)
    assert am.object_rows["mode"].isVisibleTo(am)
    assert not am.object_rows["extra"].isVisibleTo(am)
    assert not am.object_groups["More"].isVisibleTo(am)
    combo = am.object_editors["mode"].widgets[0]
    combo.setCurrentIndex(combo.findText("Two"))
    _settle()
    assert obj.params["mode"] == "Two"
    assert am.object_rows["extra"].isVisibleTo(am) and am.object_groups["More"].isVisibleTo(am)
    _done(am)


_MAIN_PX = (2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 72, 96, 128, 256, 512, 1024)
_BELOW_128 = (0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72,
              80, 88, 96, 112, 120)


def _allowed_px(v: int) -> bool:
    if v < 128:
        return v in _BELOW_128
    if v % 16 == 0:
        return True
    return any(a + b == v or a - b == v for a in _MAIN_PX for b in _MAIN_PX)


def test_pixel_constants() -> None:
    assert am_mod.LABEL_WIDTH == 120 and am_mod.HEADER_H == 28
    assert am_mod.VECTOR_SPIN_MIN == 32
    assert am_mod.SPIN_TEXT_MARGIN == 6 and am_mod.VECTOR_TEXT_MARGIN == 4
    assert "padding: 2px 2px" in am_mod.VECTOR_SPIN_STYLE
    sizes = ("LABEL_WIDTH", "LABEL_INDENT", "HEADER_H", "HEADER_ICON", "VECTOR_SPIN_MIN",
             "ARROW_W", "SPIN_TEXT_MARGIN", "VECTOR_TEXT_MARGIN", "GROUP_SPACING")
    for name in sizes:
        value = getattr(am_mod, name)
        assert isinstance(value, int) and _allowed_px(value), (name, value)
    scene, am, obj = _make(ALL_ID)
    assert am.minimumWidth() == 256 and am.minimumHeight() == 160
    assert am.header.height() == 28
    assert am.object_rows["size"].label.width() == 120
    assert all(e.layout().spacing() == 4 for e in am.findChildren(ParamEditor))
    _done(am)


def _run_as_script() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    tests.sort(key=lambda item: item[1].__code__.co_firstlineno)
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}".encode("ascii", "replace").decode())
        else:
            print(f"ok   {name}")
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
