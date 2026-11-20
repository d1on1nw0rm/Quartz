from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import quartz_studio
import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from quartz_studio.app import create_app

_KEEP: list[QWidget] = []


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None or not app.property("qsTestThemed"):
        app = create_app([sys.argv[0]])
        app.setProperty("qsTestThemed", True)
    return app


def _settle(passes: int = 4) -> None:
    app = _app()
    for _ in range(passes):
        app.processEvents()


def _show(widget: QWidget, w: int = 480, h: int = 140) -> QWidget:
    widget.resize(w, h)
    widget.show()
    widget.activateWindow()
    _settle()
    _KEEP.append(widget)
    return widget


def _fresh_coordinates():
    _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.coordinates import CoordinatesManager

    scene = reset_scene()
    return scene, _show(CoordinatesManager())


def _texts(cm, column: int) -> list[str]:
    return [cm.field(column, axis).text() for axis in range(3)]


def _type(field: QLineEdit, text: str, key: Qt.Key | None = Qt.Key.Key_Return) -> None:
    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, text)
    if key is not None:
        QTest.keyClick(field, key)
    _settle(2)



def test_format_number() -> None:
    from quartz_studio.widgets.coordinates import format_number, format_value

    assert format_value(0, "cm") == "0 cm"
    assert format_value(-0.0, "cm") == "0 cm"
    assert format_value(-0.0001, "cm") == "0 cm"
    assert format_value(12.5, "cm") == "12.5 cm"
    assert format_value(-37.3333333, "°") == "-37.333 °"
    assert format_value(200.0, "cm") == "200 cm"
    assert format_value(0.1 + 0.2, "cm") == "0.3 cm"
    assert format_number(1234.5678) == "1234.568"
    assert format_number(float("nan")) == "0"


def test_parse_accepts_comma_dot_units_and_arithmetic() -> None:
    from quartz_studio.widgets.coordinates import parse_value

    assert parse_value("150") == 150
    assert parse_value("12,5") == 12.5
    assert parse_value("12.5") == 12.5
    assert parse_value("  12,5 cm  ") == 12.5
    assert parse_value("-37,333 °", "°") == -37.333
    assert parse_value(" -37.333° ", "°") == -37.333
    assert parse_value("45º", "°") == 45
    assert parse_value("100+50") == 150
    assert parse_value("100 + 50 cm") == 150
    assert parse_value("(1+2)*3") == 9
    assert parse_value("2*-3") == -6
    assert parse_value("10/4") == 2.5
    assert parse_value("1,5 m") == 150
    assert parse_value("10mm") == 1


def test_parse_rejects_invalid_input() -> None:
    from quartz_studio.widgets.coordinates import parse_value

    for text in ("", "   ", "abc", "1/0", "1.000,5", "12 °", "5 cm cm", "1+", "(1",
                 "__import__('os')", "eval(1)", "1e3", "(" * 200 + "1" + ")" * 200,
                 "-" * 500 + "1", "(" * 50 + "1" + ")" * 50, "-" * 60 + "1"):
        assert parse_value(text) is None, text
    assert parse_value("10 cm", "°") is None
    assert parse_value("(" * 20 + "1" + ")" * 20) == 1



def test_default_cube_fields() -> None:
    from quartz_studio.widgets.coordinates import COLUMN_TITLES, STATE_OBJECT

    scene, cm = _fresh_coordinates()
    assert scene.mode == "model" and scene.object_selected
    assert cm.state() == STATE_OBJECT
    assert _texts(cm, 0) == ["0 cm"] * 3
    assert _texts(cm, 1) == ["0 °"] * 3
    assert _texts(cm, 2) == ["200 cm"] * 3
    assert all(f.isEnabled() for row in cm.fields for f in row)
    assert [t.text() for t in cm.column_titles] == list(COLUMN_TITLES)
    assert not cm.reset_button.isEnabled()
    scene.set_object_position(0, 25.0)
    _settle(2)
    assert cm.reset_button.isEnabled()
    scene.undo()
    _settle(2)
    assert not cm.reset_button.isEnabled()


def test_position_x_enter_moves_object() -> None:
    scene, cm = _fresh_coordinates()
    changes: list[int] = []
    scene.changed.connect(lambda: changes.append(1))
    _type(cm.field(0, 0), "150")
    assert scene.active.position[0] == 150
    assert scene.active.position[1] == 0 and scene.active.position[2] == 0
    assert cm.field(0, 0).text() == "150 cm"
    assert changes, "scene.changed was not emitted"


def test_rotation_y_and_expression() -> None:
    scene, cm = _fresh_coordinates()
    _type(cm.field(1, 1), "45")
    assert scene.active.rotation[1] == 45
    assert cm.field(1, 1).text() == "45 °"
    _type(cm.field(0, 1), "100+50")
    assert scene.active.position[1] == 150
    assert cm.field(0, 1).text() == "150 cm"
    _type(cm.field(0, 2), "-12.5 cm")
    assert scene.active.position[2] == -12.5
    assert cm.field(0, 2).text() == "-12.5 cm"


def test_scale_column_edits_size() -> None:
    scene, cm = _fresh_coordinates()
    _type(cm.field(2, 0), "400")
    assert np.isclose(scene.active.size()[0], 400)
    assert np.isclose(scene.active.scale[0], 2)
    assert cm.field(2, 0).text() == "400 cm"
    for bad in ("0", "-5"):
        _type(cm.field(2, 0), bad)
        assert np.isclose(scene.active.scale[0], 2)
        assert cm.field(2, 0).text() == "400 cm"


def test_invalid_entry_and_escape_revert() -> None:
    scene, cm = _fresh_coordinates()
    field = cm.field(0, 0)
    _type(field, "abc")
    assert field.text() == "0 cm"
    assert scene.active.position[0] == 0
    _type(field, "999", key=Qt.Key.Key_Escape)
    assert field.text() == "0 cm"
    assert scene.active.position[0] == 0
    QTest.keyClick(field, Qt.Key.Key_Tab)
    _settle(2)
    assert scene.active.position[0] == 0


def test_focus_out_commits() -> None:
    scene, cm = _fresh_coordinates()
    field = cm.field(0, 2)
    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, "30")
    field.clearFocus()
    _settle(2)
    assert scene.active.position[2] == 30
    assert field.text() == "30 cm"


def test_refresh_keeps_field_being_edited() -> None:
    scene, cm = _fresh_coordinates()
    field = cm.field(0, 0)
    other = cm.field(0, 1)
    field.setFocus()
    _settle(2)
    assert field.hasFocus(), "the offscreen window did not take focus"
    field.selectAll()
    QTest.keyClicks(field, "12")
    scene.move_selection([10.0, 20.0, 0.0])
    _settle(2)
    assert field.text() == "12", field.text()
    assert other.text() == "20 cm"
    QTest.keyClick(field, Qt.Key.Key_Escape)
    _settle(2)
    assert field.text() == "10 cm"
    assert scene.active.position[0] == 10


def test_points_mode_selected_point() -> None:
    from quartz_studio.widgets.coordinates import STATE_COMPONENTS

    scene, cm = _fresh_coordinates()
    obj = scene.active
    obj.position = np.array([50.0, 0.0, 0.0])
    scene.set_mode("points")
    scene.select_components([6])
    _settle(2)
    assert cm.state() == STATE_COMPONENTS
    assert _texts(cm, 0) == ["150 cm", "100 cm", "100 cm"]
    assert _texts(cm, 1) == ["0 °"] * 3
    assert _texts(cm, 2) == ["0 cm"] * 3
    assert all(cm.field(0, a).isEnabled() for a in range(3))
    assert not any(cm.field(c, a).isEnabled() for c in (1, 2) for a in range(3))
    assert not cm.reset_button.isEnabled()

    before = obj.mesh.points.copy()
    _type(cm.field(0, 0), "250")
    assert np.allclose(obj.position, [50, 0, 0]), "the object must not move"
    assert np.isclose(obj.mesh.points[6][0], 200)
    others = [i for i in range(len(before)) if i != 6]
    assert np.allclose(obj.mesh.points[others], before[others]), "only point 6 may move"
    assert np.allclose(obj.mesh.points[6][1:], before[6][1:])
    assert cm.field(0, 0).text() == "250 cm"

    scene.select_components([0, 7])
    _settle(2)
    assert _texts(cm, 2) == ["0 cm", "200 cm", "200 cm"]
    assert _texts(cm, 0) == ["-50 cm", "0 cm", "0 cm"]


def test_nothing_selected_disables_fields() -> None:
    from quartz_studio.widgets.coordinates import COORDINATE_COLUMNS, STATE_NONE

    scene, cm = _fresh_coordinates()
    scene.active.position = np.array([10.0, 0.0, 0.0])
    scene.select_object(False)
    _settle(2)
    assert cm.state() == STATE_NONE
    for c, text in enumerate(COORDINATE_COLUMNS):
        assert _texts(cm, c) == [text] * 3
    assert not any(f.isEnabled() for row in cm.fields for f in row)
    assert not cm.reset_button.isEnabled()
    assert not any(label.isEnabled() for label in cm.axis_labels)

    scene.select_object(True)
    scene.set_mode("edges")
    _settle(2)
    assert cm.state() == STATE_NONE
    assert not any(f.isEnabled() for row in cm.fields for f in row)
    scene.set_mode("model")
    _settle(2)
    assert _texts(cm, 0) == ["10 cm", "0 cm", "0 cm"]


def test_reset_transform_button() -> None:
    scene, cm = _fresh_coordinates()
    _type(cm.field(0, 0), "75")
    _type(cm.field(1, 2), "30")
    _type(cm.field(2, 1), "100")
    assert not np.allclose(scene.active.scale, 1)
    QTest.mouseClick(cm.reset_button, Qt.MouseButton.LeftButton)
    _settle(2)
    assert np.allclose(scene.active.position, 0)
    assert np.allclose(scene.active.rotation, 0)
    assert np.allclose(scene.active.scale, 1)
    assert _texts(cm, 2) == ["200 cm"] * 3


def test_header_has_only_the_reset_button() -> None:
    from PySide6.QtWidgets import QAbstractButton, QComboBox

    scene, cm = _fresh_coordinates()
    assert not cm.findChildren(QComboBox)
    assert cm.findChildren(QAbstractButton) == [cm.reset_button]
    assert np.allclose(scene.active.position, 0) and _texts(cm, 2) == ["200 cm"] * 3


def test_object_manager_row_click_selects() -> None:
    _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.coordinates import CoordinatesManager
    from quartz_studio.widgets.object_manager import ObjectManager

    scene = reset_scene()
    om = _show(ObjectManager(), 480, 300)
    cm = _show(CoordinatesManager())
    tree = om.tree
    assert tree.topLevelItemCount() == 1
    item = tree.topLevelItem(0)
    assert item.text(0) == "Cube"
    assert tree.highlighted_names() == ["Cube"]

    row = tree.visualItemRect(item)
    empty = QPoint(row.center().x(), row.bottom() + 60)
    assert tree.itemAt(empty) is None
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     empty)
    _settle(2)
    assert not scene.object_selected
    assert tree.highlighted_names() == []
    assert not cm.field(0, 0).isEnabled()

    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     row.center())
    _settle(2)
    assert scene.object_selected
    assert tree.highlighted_names() == ["Cube"]
    assert cm.field(0, 0).isEnabled()

    scene.set_mode("points")
    _settle(2)
    assert tree.highlighted_names() == ["Cube"]
    om.grab()


def test_object_rename_and_attribute_header() -> None:
    _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.attribute_manager import AttributeManager
    from quartz_studio.widgets.object_manager import ObjectManager

    scene = reset_scene()
    om = _show(ObjectManager(), 480, 300)
    am = _show(AttributeManager(), 480, 500)
    header = am.object_header
    assert header.isVisibleTo(am)
    assert header.text() == "Polygon Object [Cube]"

    scene.select_object(False)
    _settle(2)
    assert not header.isVisibleTo(am)
    scene.select_object(True)
    _settle(2)
    assert header.isVisibleTo(am)

    tree = om.tree
    assert tree.rename()
    _settle(2)
    editors = [e for e in tree.viewport().findChildren(QLineEdit) if e.isVisible()]
    assert editors, "rename editor did not open"
    editor = editors[0]
    editor.selectAll()
    QTest.keyClicks(editor, "  Box ")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    _settle(3)
    assert scene.active.name == "Box"
    assert tree.topLevelItem(0).text(0) == "Box"
    assert header.text() == "Polygon Object [Box]"

    tree.topLevelItem(0).setText(0, "   ")
    _settle(2)
    assert scene.active.name == "Box"
    assert tree.topLevelItem(0).text(0) == "Box"


def test_typed_text_never_reaches_another_target() -> None:
    scene, cm = _fresh_coordinates()
    obj = scene.active
    field = cm.field(0, 1)

    scene.set_mode("points")
    scene.select_components([6])
    _settle(2)
    before = obj.mesh.points.copy()
    field.setFocus()
    _settle(2)
    assert field.hasFocus(), "the offscreen window did not take focus"
    field.selectAll()
    QTest.keyClicks(field, "250")
    scene.set_mode("model")
    _settle(2)
    assert field.text() == "0 cm", field.text()
    field.clearFocus()
    _settle(2)
    assert np.allclose(obj.position, [0, 0, 0]), obj.position
    assert np.allclose(obj.mesh.points, before)

    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, "50")
    scene.set_mode("points")
    _settle(2)
    assert field.text() == "100 cm", field.text()
    field.clearFocus()
    _settle(2)
    assert np.allclose(obj.position, [0, 0, 0])
    assert np.allclose(obj.mesh.points, before)

    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, "75")
    scene.select_components([1])
    _settle(2)
    assert field.text() == _cm_text(obj.world_points()[1][1]), field.text()
    QTest.keyClick(field, Qt.Key.Key_Return)
    _settle(2)
    assert np.allclose(obj.mesh.points, before)

    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, "75")
    scene.changed.emit()
    _settle(2)
    assert field.text() == "75"
    QTest.keyClick(field, Qt.Key.Key_Return)
    _settle(2)
    assert np.isclose(obj.world_points()[1][1], 75)


def _cm_text(value: float) -> str:
    from quartz_studio.widgets.coordinates import format_value

    return format_value(value, "cm")


def test_object_manager_rename_goes_through_scene() -> None:
    _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.attribute_manager import AttributeManager
    from quartz_studio.widgets.object_manager import ObjectManager

    scene = reset_scene()
    om = _show(ObjectManager(), 480, 300)
    am = _show(AttributeManager(), 480, 500)
    tree = om.tree
    scene.set_object_position(0, 50.0)
    tree.topLevelItem(0).setText(0, " Box ")
    _settle(2)
    assert scene.active.name == "Box"
    assert tree.topLevelItem(0).text(0) == "Box"

    assert scene.undo()
    _settle(2)
    assert scene.active.name == "Cube"
    assert np.allclose(scene.active.position, [50, 0, 0])
    assert tree.topLevelItem(0).text(0) == "Cube"
    assert am.object_header.text() == "Polygon Object [Cube]"
    assert scene.undo()
    _settle(2)
    assert np.allclose(scene.active.position, [0, 0, 0])

    scene.rename_object(scene.active, "Block")
    _settle(2)
    assert tree.topLevelItem(0).text(0) == "Block"
    assert am.object_header.text() == "Polygon Object [Block]"


def test_object_manager_click_selects_other_object() -> None:
    _app()
    from quartz_studio.scene import Mesh, reset_scene
    from quartz_studio.widgets.coordinates import STATE_OBJECT, CoordinatesManager
    from quartz_studio.widgets.object_manager import ObjectManager

    scene = reset_scene()
    om = _show(ObjectManager(), 480, 300)
    cm = _show(CoordinatesManager())
    tree = om.tree
    first = scene.active
    second = scene.add_object("Cube", Mesh.cube())
    second.position = np.array([300.0, 0.0, 0.0])
    _settle(2)
    assert tree.row_names() == ["Cube", "Cube.1"]
    assert scene.active is second

    _click_row(tree, 0)
    assert scene.active is first
    assert scene.object_selected
    assert tree.highlighted_names() == ["Cube"]
    assert cm.state() == STATE_OBJECT
    assert cm.field(0, 0).text() == "0 cm"

    _click_row(tree, 1)
    assert scene.active is second
    assert tree.highlighted_names() == ["Cube.1"]
    assert cm.field(0, 0).text() == "300 cm"


def _click_row(tree, row: int, double: bool = False) -> None:
    rect = tree.visualItemRect(tree.topLevelItem(row))
    pos = QPoint(min(rect.center().x(), tree.columnWidth(0) - 40), rect.center().y())
    if double:
        QTest.mouseDClick(tree.viewport(), Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier, pos)
    else:
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, pos)
    _settle(2)


def _managers():
    _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.attribute_manager import AttributeManager
    from quartz_studio.widgets.coordinates import CoordinatesManager
    from quartz_studio.widgets.object_manager import ObjectManager

    scene = reset_scene()
    om = _show(ObjectManager(), 480, 300)
    am = _show(AttributeManager(), 480, 500)
    cm = _show(CoordinatesManager())
    return scene, om.tree, am, cm


def _row_icons(tree) -> list[str]:
    from quartz_studio.widgets.object_manager import object_icon_name

    return [object_icon_name(tree.object_of(tree.topLevelItem(r)))
            for r in range(tree.topLevelItemCount())]


def test_object_manager_lists_all_objects_with_kind_icons() -> None:
    from quartz_studio.scene import Mesh
    from quartz_studio.widgets.object_manager import LINE_OBJECT_ICON, OBJECT_ICON

    scene, tree, am, cm = _managers()
    scene.add_object("Cube", Mesh.cube(100.0))
    line = scene.new_line_object()
    _settle(2)
    assert tree.row_names() == ["Cube", "Cube.1", "Line"]
    assert _row_icons(tree) == [OBJECT_ICON, OBJECT_ICON, LINE_OBJECT_ICON]
    assert scene.active is line and tree.highlighted_names() == ["Line"]
    assert am.object_header.text() == "Polygon Object [Line]"
    assert am.object_header.icon_name() == LINE_OBJECT_ICON
    tree.window().grab()

    for r, name in enumerate(tree.row_names()):
        assert tree.object_of(tree.topLevelItem(r)).name == name
    _click_row(tree, 0)
    assert scene.active is scene.objects[0] and scene.active.name == "Cube"
    assert am.object_header.text() == "Polygon Object [Cube]"
    assert am.object_header.icon_name() == OBJECT_ICON
    assert _texts(cm, 2) == ["200 cm"] * 3
    _click_row(tree, 1)
    assert scene.active.name == "Cube.1" and _texts(cm, 2) == ["100 cm"] * 3

    rect = tree.visualItemRect(tree.topLevelItem(2))
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(rect.center().x(), rect.bottom() + 60))
    _settle(2)
    assert not scene.object_selected and scene.active.name == "Cube.1"
    assert tree.highlighted_names() == []

    _click_row(tree, 2)
    scene.set_tool("pen")
    for x, y in ((0, 0), (100, 0), (100, 100)):
        scene.pen_add_point((x, y, 0), toward_camera=(0, 0, -1))
    scene.pen_finish()
    _settle(2)
    assert scene.active.name == "Line" and scene.active.mesh.has_faces()
    assert _row_icons(tree)[2] == OBJECT_ICON
    assert am.object_header.icon_name() == OBJECT_ICON


def test_object_manager_double_click_rename_and_undo() -> None:
    from quartz_studio.scene import Mesh

    scene, tree, am, _cm = _managers()
    scene.add_object("Cube", Mesh.cube())
    _settle(2)
    _click_row(tree, 0, double=True)
    assert scene.active is scene.objects[0]
    editors = [e for e in tree.viewport().findChildren(QLineEdit) if e.isVisible()]
    assert editors, "double-click did not open the rename editor"
    editor = editors[0]
    editor.selectAll()
    QTest.keyClicks(editor, "Base")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    _settle(3)
    assert [o.name for o in scene.objects] == ["Base", "Cube.1"]
    assert tree.row_names() == ["Base", "Cube.1"]
    assert am.object_header.text() == "Polygon Object [Base]"

    assert scene.undo()
    _settle(2)
    assert [o.name for o in scene.objects] == ["Cube", "Cube.1"]
    assert tree.row_names() == ["Cube", "Cube.1"]
    assert am.object_header.text() == "Polygon Object [Cube]"
    assert tree.object_of(tree.topLevelItem(0)) is scene.objects[0]
    assert tree.highlighted_names() == ["Cube"]
    _click_row(tree, 1)
    assert scene.active is scene.objects[1]

    assert scene.redo()
    _settle(2)
    assert tree.row_names() == ["Base", "Cube.1"]


def test_object_manager_delete_and_undo() -> None:
    from quartz_studio.scene import Mesh
    from quartz_studio.widgets.coordinates import STATE_NONE

    scene, tree, am, cm = _managers()
    scene.add_object("Cube", Mesh.cube())
    scene.active.position = np.array([300.0, 0.0, 0.0])
    scene.new_line_object()
    _settle(2)
    assert tree.row_names() == ["Cube", "Cube.1", "Line"]
    undo_depth = len(scene._undo)

    _click_row(tree, 1)
    tree.setFocus()
    QTest.keyClick(tree, Qt.Key.Key_Delete)
    _settle(2)
    assert [o.name for o in scene.objects] == ["Cube", "Line"]
    assert tree.row_names() == ["Cube", "Line"]
    assert len(scene._undo) == undo_depth + 1, "a delete must be one undo step"
    assert scene.active is not None and scene.active.name == "Line"
    tree.window().grab()

    assert scene.undo()
    _settle(2)
    assert tree.row_names() == ["Cube", "Cube.1", "Line"]
    assert scene.active.name == "Cube.1" and scene.object_selected
    assert tree.highlighted_names() == ["Cube.1"]
    assert cm.field(0, 0).text() == "300 cm"
    assert am.object_header.text() == "Polygon Object [Cube.1]"

    for _ in range(3):
        tree.setFocus()
        QTest.keyClick(tree, Qt.Key.Key_Backspace)
        _settle(2)
    assert scene.objects == [] and scene.active is None
    assert tree.topLevelItemCount() == 0 and tree.row_names() == []
    assert cm.state() == STATE_NONE
    assert not am.object_header.isVisibleTo(am)
    QTest.keyClick(tree, Qt.Key.Key_Delete)
    _settle(2)
    tree.window().grab()

    for _ in range(3):
        assert scene.undo()
    _settle(2)
    assert tree.row_names() == ["Cube", "Cube.1", "Line"]


def test_line_object_coordinates() -> None:
    from quartz_studio.widgets.coordinates import STATE_COMPONENTS, STATE_OBJECT

    scene, tree, am, cm = _managers()
    line = scene.new_line_object()
    _settle(2)
    assert cm.state() == STATE_OBJECT
    assert _texts(cm, 0) == ["0 cm"] * 3
    assert _texts(cm, 2) == ["0 cm"] * 3

    scene.set_tool("line_pen")
    assert scene.mode == "points"
    scene.pen_add_point((50.0, 0.0, 0.0))
    assert scene.active is line, "the stroke must go into the empty Line"
    assert cm.state() == STATE_COMPONENTS
    assert _texts(cm, 0) == ["50 cm", "0 cm", "0 cm"]
    scene.pen_add_point((50.0, 100.0, 20.0))
    assert _texts(cm, 0) == ["50 cm", "100 cm", "20 cm"]
    scene.pen_finish()
    assert not line.mesh.has_faces() and len(line.mesh.edges) == 1

    _type(cm.field(0, 0), "80")
    assert np.allclose(line.mesh.points[1], [80, 100, 20])
    assert np.allclose(line.mesh.points[0], [50, 0, 0])

    scene.set_mode("model")
    scene.select_object(True)
    _settle(2)
    assert cm.state() == STATE_OBJECT
    assert _texts(cm, 2) == ["30 cm", "100 cm", "20 cm"]
    _type(cm.field(0, 1), "40")
    assert np.allclose(line.position, [0, 40, 0])
    _type(cm.field(2, 1), "200")
    assert np.isclose(line.scale[1], 2) and _texts(cm, 2)[1] == "200 cm"
    assert scene.undo()
    _settle(2)
    assert _texts(cm, 2)[1] == "100 cm"


def test_empty_object_coordinates_no_crash() -> None:
    from quartz_studio.widgets.coordinates import STATE_NONE, STATE_OBJECT
    from quartz_studio.widgets.object_manager import LINE_OBJECT_ICON

    scene, tree, am, cm = _managers()
    empty = scene.add_object("Empty")
    _settle(2)
    assert tree.row_names() == ["Cube", "Empty"]
    assert _row_icons(tree)[1] == LINE_OBJECT_ICON
    assert cm.state() == STATE_OBJECT
    assert _texts(cm, 2) == ["0 cm"] * 3
    for text in ("100", "0", "-5"):
        _type(cm.field(2, 0), text)
        assert np.allclose(empty.scale, 1) and cm.field(2, 0).text() == "0 cm"
    _type(cm.field(0, 2), "25")
    assert np.allclose(empty.position, [0, 0, 25])
    QTest.mouseClick(cm.reset_button, Qt.MouseButton.LeftButton)
    _settle(2)
    assert np.allclose(empty.position, 0)

    for mode in ("points", "edges", "polygons"):
        scene.set_mode(mode)
        scene.select_components([0] if mode != "edges" else [(0, 1)])
        _settle(2)
        assert cm.state() in (STATE_NONE, "components")
        tree.window().grab()
        cm.grab()
        scene.clear_selection()
    scene.set_mode("model")
    assert not scene.extrude_selection()
    _settle(2)
    am.grab()
    assert am.object_header.text() == "Polygon Object [Empty]"


def test_main_window_coordinates_not_clipped() -> None:
    _app()
    from quartz_studio.main_window import MainWindow
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.coordinates import MIN_H

    reset_scene()
    win = MainWindow()
    win.setMinimumSize(1, 1)
    win.resize(1920, 1007)
    win.show()
    _settle(6)
    win.apply_default_sizes()
    _settle(6)
    _KEEP.append(win)
    cm = win.coordinates
    assert cm.height() == MIN_H == 120, cm.height()
    last = cm.field(2, 2)
    bottom = last.mapTo(cm, QPoint(0, last.height())).y()
    assert bottom <= cm.height(), (bottom, cm.height())
    assert cm.field(2, 2).text() == "200 cm"
    om = win.object_manager
    assert om.tree.topLevelItem(0).text(0) == "Cube"


def test_ctrl_z_y_in_focused_field_undo_scene() -> None:
    _app()
    from quartz_studio.main_window import MainWindow
    from quartz_studio.scene import reset_scene

    scene = reset_scene()
    win = MainWindow()
    win.resize(1600, 900)
    win.show()
    win.activateWindow()
    _settle(6)
    _KEEP.append(win)
    cm = win.coordinates
    field = cm.field(0, 0)
    QTest.mouseClick(field, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     field.rect().center())
    _settle(2)
    field.selectAll()
    QTest.keyClicks(field, "400")
    QTest.keyClick(field, Qt.Key.Key_Return)
    _settle(2)
    assert QApplication.focusWidget() is field
    assert np.allclose(scene.active.position, [400, 0, 0]), scene.active.position
    assert len(scene._undo) == 1, len(scene._undo)

    QTest.keyClick(field, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    _settle(2)
    assert np.allclose(scene.active.position, [0, 0, 0]), scene.active.position
    assert field.text() == "0 cm", field.text()
    assert len(scene._undo) == 0 and scene.can_redo()

    QTest.keyClick(field, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    _settle(2)
    assert np.allclose(scene.active.position, [400, 0, 0]), scene.active.position
    assert field.text() == "400 cm", field.text()

    QTest.keyClick(field, Qt.Key.Key_Tab)
    _settle(2)
    other = QApplication.focusWidget()
    assert isinstance(other, QLineEdit) and other is not field
    QTest.keyClick(other, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    _settle(2)
    assert np.allclose(scene.active.position, [0, 0, 0]), scene.active.position
    assert field.text() == "0 cm", field.text()

    field.setFocus()
    _settle(2)
    QTest.keyClick(field, Qt.Key.Key_End)
    QTest.keyClicks(field, "5")
    assert field.isModified()
    typed = field.text()
    QTest.keyClick(field, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    _settle(2)
    assert field.text() != typed, field.text()
    assert np.allclose(scene.active.position, [0, 0, 0]), scene.active.position
    assert scene.can_redo(), "text undo must not touch the scene history"
    QTest.keyClick(field, Qt.Key.Key_Escape)
    _settle(2)


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
    for w in _KEEP:
        w.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
