from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

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


def _settle(passes: int = 3) -> None:
    app = _app()
    for _ in range(passes):
        app.processEvents()


def _show(widget: QWidget, w: int = 480, h: int = 300) -> QWidget:
    widget.resize(w, h)
    widget.show()
    widget.activateWindow()
    _settle(4)
    _KEEP.append(widget)
    return widget


def _register_specs() -> None:
    from quartz_studio.objects import registry
    from quartz_studio.scene import Mesh

    if "om_test_generator" not in registry.SPECS:
        registry.register(registry.ObjectSpec(
            id="om_test_generator", label="Test Generator", category="generator",
            build=lambda p, inputs: Mesh.cube(100.0) if inputs else Mesh.empty(),
            inputs="children"))
    if "om_test_null" not in registry.SPECS:
        registry.register(registry.ObjectSpec(
            id="om_test_null", label="Test Null", category="null",
            build=lambda p, inputs: Mesh.empty()))


def _fresh():
    _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.object_manager import ObjectManager

    _register_specs()
    scene = reset_scene()
    om = _show(ObjectManager())
    return scene, om.tree


def _hierarchy():
    from quartz_studio.scene import Mesh

    scene, tree = _fresh()
    gen = scene.add_parametric("om_test_generator", name="Gen")
    child = scene.add_object("B", Mesh.cube(50.0))
    scene.set_parent(child, gen)
    null = scene.add_parametric("om_test_null", name="Null")
    _settle()
    tree.item_of(gen).setExpanded(True)
    _settle()
    return scene, tree, gen, child, null


def _by_name(scene, name: str):
    return next(o for o in scene.objects if o.name == name)


def _walk_names(tree) -> list[tuple[str, int]]:
    return [(tree.object_of(item).name, depth) for item, depth in tree._walk()]


def _rect(tree, obj):
    return tree.visualItemRect(tree.item_of(obj))


def _point(tree, obj, band: str = "center") -> QPoint:
    r = _rect(tree, obj)
    y = {"top": r.top() + 2, "bottom": r.bottom() - 2, "center": r.center().y()}[band]
    return QPoint(tree.viewport().width() // 2, y)


def _click(tree, obj, toggle: bool = False) -> None:
    r = _rect(tree, obj)
    x = tree.viewport().width() - 12 if toggle else 60
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(x, r.center().y()))
    _settle(2)


def test_tree_mirrors_scene() -> None:
    scene, tree, gen, child, null = _hierarchy()
    assert tree.row_names() == ["Cube", "Gen", "B", "Null"]
    assert _walk_names(tree) == [("Cube", 0), ("Gen", 0), ("B", 1), ("Null", 0)]
    assert tree.item_of(gen).childCount() == 1
    assert tree.object_of(tree.item_of(child).parent()) is gen
    assert tree.object_of(tree.item_of(gen)) is gen
    assert tree.topLevelItemCount() == 3
    tree.window().grab()


def test_icons_follow_kind_and_category() -> None:
    from quartz_studio import theme
    from quartz_studio.scene import Mesh
    from quartz_studio.widgets.object_manager import LINE_OBJECT_ICON, OBJECT_ICON, object_icon

    scene, tree, gen, child, null = _hierarchy()
    cube = _by_name(scene, "Cube")
    line = scene.add_object("Line")
    _settle(2)
    assert object_icon(cube) == (OBJECT_ICON, theme.ICON_MESH)
    assert object_icon(child) == (OBJECT_ICON, theme.ICON_MESH)
    assert object_icon(line) == (LINE_OBJECT_ICON, theme.ICON_SPLINE)
    assert object_icon(gen) == (OBJECT_ICON, theme.ICON_GENERATOR)
    assert object_icon(null) == ("null", None)
    tree.window().grab()


def test_drop_onto_row_reparents_through_move_path() -> None:
    scene, tree, gen, child, null = _hierarchy()
    cube = _by_name(scene, "Cube")
    assert tree.drop_object(cube, _point(tree, null))
    assert [o.name for o in scene.children(null)] == ["Cube"]
    assert tree.object_of(tree.item_of(cube).parent()).name == "Null"
    assert tree.item_of(null).isExpanded()
    assert tree.row_names() == ["Gen", "B", "Null", "Cube"]


def test_drop_events_reach_move_path() -> None:
    from PySide6.QtCore import QByteArray, QMimeData, QPointF
    from PySide6.QtGui import QDragMoveEvent, QDropEvent
    from quartz_studio.widgets.object_manager import DRAG_MIME

    scene, tree, gen, child, null = _hierarchy()
    cube = _by_name(scene, "Cube")
    mime = QMimeData()
    mime.setData(DRAG_MIME, QByteArray(b"Cube"))
    tree._drag_obj = cube
    pos = QPointF(_point(tree, null))
    move = QDragMoveEvent(pos.toPoint(), Qt.DropAction.MoveAction, mime,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dragMoveEvent(move)
    assert move.isAccepted()
    drop = QDropEvent(pos, Qt.DropAction.MoveAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(drop)
    _settle(2)
    tree._drag_obj = None
    assert drop.isAccepted()
    assert [o.name for o in scene.children(_by_name(scene, "Null"))] == ["Cube"]
    assert tree.row_names() == ["Gen", "B", "Null", "Cube"]

    cycle = QDragMoveEvent(_point(tree, _by_name(scene, "B")), Qt.DropAction.MoveAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree._drag_obj = _by_name(scene, "Gen")
    tree.dragMoveEvent(cycle)
    tree._drag_obj = None
    assert not cycle.isAccepted()


def test_drop_on_empty_space_makes_root() -> None:
    scene, tree, gen, child, null = _hierarchy()
    empty = QPoint(10, tree.viewport().height() - 2)
    assert tree.itemAt(empty) is None
    assert tree.drop_object(child, empty)
    assert child.parent is None
    assert [o.name for o in scene.roots()] == ["Cube", "Gen", "Null", "B"]
    assert tree.row_names() == ["Cube", "Gen", "Null", "B"]


def test_cycle_is_refused() -> None:
    scene, tree, gen, child, null = _hierarchy()
    before = [(o.name, o.parent.name if o.parent else None) for o in scene.objects]
    assert not tree.drop_object(gen, _point(tree, child))
    assert not tree.move_object(gen, child)
    assert not tree.drop_object(gen, _point(tree, gen))
    assert [(o.name, o.parent.name if o.parent else None) for o in scene.objects] == before
    assert gen.parent is None


def test_reorder_between_rows() -> None:
    scene, tree, gen, child, null = _hierarchy()
    cube = _by_name(scene, "Cube")
    assert tree.drop_object(cube, _point(tree, null, "top"))
    assert [o.name for o in scene.roots()] == ["Gen", "Cube", "Null"]
    assert tree.row_names() == ["Gen", "B", "Cube", "Null"]
    assert tree.drop_object(cube, _point(tree, null, "bottom"))
    assert [o.name for o in scene.roots()] == ["Gen", "Null", "Cube"]
    assert tree.row_names() == ["Gen", "B", "Null", "Cube"]
    assert tree.drop_object(cube, _point(tree, _by_name(scene, "Gen"), "top"))
    assert [o.name for o in scene.roots()] == ["Cube", "Gen", "Null"]
    assert tree.row_names() == ["Cube", "Gen", "B", "Null"]


def test_drop_between_rows_can_change_level() -> None:
    scene, tree, gen, child, null = _hierarchy()
    cube = _by_name(scene, "Cube")
    assert tree.drop_object(child, _point(tree, cube, "bottom"))
    assert child.parent is None
    assert [o.name for o in scene.roots()] == ["Cube", "B", "Gen", "Null"]
    assert tree.row_names() == ["Cube", "B", "Gen", "Null"]


def test_enable_toggle_click_and_undo() -> None:
    scene, tree, gen, child, null = _hierarchy()
    assert null.enabled
    _click(tree, null, toggle=True)
    assert not _by_name(scene, "Null").enabled
    assert null not in scene.render_objects()
    assert scene.undo()
    _settle(2)
    assert _by_name(scene, "Null").enabled
    _click(tree, _by_name(scene, "Null"), toggle=True)
    assert not _by_name(scene, "Null").enabled
    assert tree.toggle_enabled(_by_name(scene, "Null"))
    assert _by_name(scene, "Null").enabled
    tree.window().grab()


def test_delete_removes_subtree_and_undo_restores() -> None:
    scene, tree, gen, child, null = _hierarchy()
    _click(tree, gen)
    assert scene.active is gen
    tree.setFocus()
    _settle(2)
    QTest.keyClick(tree, Qt.Key.Key_Delete)
    _settle(2)
    assert [o.name for o in scene.objects] == ["Cube", "Null"]
    assert tree.row_names() == ["Cube", "Null"]
    assert scene.undo()
    _settle(2)
    assert tree.row_names() == ["Cube", "Gen", "B", "Null"]
    assert tree.object_of(tree.item_of(_by_name(scene, "B")).parent()).name == "Gen"


def test_rename_through_editor_and_undo() -> None:
    scene, tree, gen, child, null = _hierarchy()
    _click(tree, child)
    assert scene.active is child
    assert tree.rename(child)
    _settle(2)
    editors = [e for e in tree.viewport().findChildren(QLineEdit) if e.isVisible()]
    assert editors, "rename editor did not open"
    editor = editors[0]
    editor.selectAll()
    QTest.keyClicks(editor, "Kid")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    _settle(3)
    assert _by_name(scene, "Kid") is scene.active
    assert tree.row_names() == ["Cube", "Gen", "Kid", "Null"]
    assert scene.undo()
    _settle(2)
    assert tree.row_names() == ["Cube", "Gen", "B", "Null"]


def test_selection_follows_tree_and_scene() -> None:
    scene, tree, gen, child, null = _hierarchy()
    _click(tree, child)
    assert scene.active is child
    assert tree.highlighted_names() == ["B"]
    scene.set_active(null)
    _settle(2)
    assert tree.highlighted_names() == ["Null"]
    scene.set_active(gen)
    _settle(2)
    assert tree.highlighted_names() == ["Gen"]
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(10, tree.viewport().height() - 2))
    _settle(2)
    assert tree.highlighted_names() == []


def test_expanded_state_survives_refresh_and_undo() -> None:
    from quartz_studio.scene import Mesh

    scene, tree, gen, child, null = _hierarchy()
    tree.item_of(gen).setExpanded(True)
    _settle(2)
    scene.add_object("Extra", Mesh.cube())
    _settle(2)
    assert tree.item_of(_by_name(scene, "Gen")).isExpanded()
    assert tree.row_names() == ["Cube", "Gen", "B", "Null", "Extra"]
    assert scene.undo()
    _settle(2)
    assert tree.item_of(_by_name(scene, "Gen")).isExpanded()
    assert tree.row_names() == ["Cube", "Gen", "B", "Null"]
    tree.item_of(_by_name(scene, "Gen")).setExpanded(False)
    scene.add_object("Extra2", Mesh.cube())
    _settle(2)
    assert not tree.item_of(_by_name(scene, "Gen")).isExpanded()


def test_drop_undo_redo_is_one_step() -> None:
    scene, tree, gen, child, null = _hierarchy()
    cube = _by_name(scene, "Cube")
    assert tree.drop_object(cube, _point(tree, null))
    assert scene.undo()
    _settle(2)
    assert [o.name for o in scene.roots()] == ["Cube", "Gen", "Null"]
    assert tree.row_names() == ["Cube", "Gen", "B", "Null"]
    assert scene.redo()
    _settle(2)
    assert _by_name(scene, "Cube").parent.name == "Null"
    assert tree.row_names() == ["Gen", "B", "Null", "Cube"]


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
