from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

TMP = tempfile.mkdtemp(prefix="qz_controls_widgets_")
os.environ["QUARTZ_PREFS_DIR"] = os.path.join(TMP, "prefs")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog, QWidget

from quartz_studio.app import create_app

SEP = " · "
_KEEP: list[QWidget] = []
_STORE_COUNT = [0]


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


def _controls():
    from quartz_studio import controls

    return controls


def _fresh_store() -> None:
    controls = _controls()
    controls.reset()
    _STORE_COUNT[0] += 1
    controls.STORE_PATH = os.path.join(TMP, f"store{_STORE_COUNT[0]}", "controls.json")


def _end_store() -> None:
    controls = _controls()
    controls.reset()
    controls.STORE_PATH = None


def _user_profile(base: str = "classic") -> str:
    _fresh_store()
    return _controls().duplicate(base)


def _install_controls(win) -> None:
    if getattr(win, "controls_filter", None) is not None:
        return
    for sc in win.findChildren(QShortcut):
        sc.setEnabled(False)
        sc.setParent(None)
        sc.deleteLater()
    _controls().install(win)


def _window(width: int = 1280, height: int = 720):
    from quartz_studio.main_window import MainWindow
    from quartz_studio.scene import reset_scene

    _app()
    reset_scene()
    win = MainWindow()
    win.setMinimumSize(1, 1)
    win.resize(width, height)
    win.show()
    _settle()
    _install_controls(win)
    _settle()
    return win


def _close(win) -> None:
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, QDialog) and widget.objectName() == "qsControlsDialog":
            widget.close()
            widget.deleteLater()
    win.close()
    win.deleteLater()
    _settle()


def _shortcut(menu, label: str) -> str:
    act = menu.find_action(label)
    assert act is not None, label
    return act.property("qs_shortcut") or ""


def _override_accepted(widget: QWidget, key: Qt.Key, mods=Qt.KeyboardModifier.NoModifier) -> bool:
    ev = QKeyEvent(QEvent.Type.ShortcutOverride, key, mods)
    ev.ignore()
    QApplication.sendEvent(widget, ev)
    return ev.isAccepted()


def _tree_window():
    win = _window()
    tree = win.object_manager.tree
    scene = tree._scene
    scene.set_active(scene.objects[0])
    scene.select_object(True)
    tree.setFocus()
    _settle()
    return win, tree, scene


def test_object_manager_answers_rename_and_delete_from_classic() -> None:
    _fresh_store()
    win, tree, scene = _tree_window()
    try:
        assert _controls().active_id() == "classic"
        assert _override_accepted(tree, Qt.Key.Key_F2)
        assert _override_accepted(tree, Qt.Key.Key_Delete)
        assert not _override_accepted(tree, Qt.Key.Key_F6)
        QTest.keyClick(tree, Qt.Key.Key_F2)
        _settle()
        assert tree.state() == QAbstractItemView.State.EditingState
        editor = QApplication.focusWidget()
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        _settle()
        tree.setFocus()
        _settle()
        assert tree.state() != QAbstractItemView.State.EditingState
        count = len(scene.objects)
        QTest.keyClick(tree, Qt.Key.Key_Delete)
        _settle()
        assert len(scene.objects) == count - 1
        assert scene.undo()
        _settle()
        scene.set_active(scene.objects[0])
        scene.select_object(True)
        tree.setFocus()
        QTest.keyClick(tree, Qt.Key.Key_Backspace)
        _settle()
        assert len(scene.objects) == count - 1
    finally:
        _close(win)
        _end_store()


def test_object_manager_follows_a_changed_profile() -> None:
    pid = _user_profile()
    controls = _controls()
    controls.set_keys(pid, "object.rename", ["F6"])
    controls.set_keys(pid, "object.delete", ["X"])
    win, tree, scene = _tree_window()
    try:
        assert _override_accepted(tree, Qt.Key.Key_F6)
        assert _override_accepted(tree, Qt.Key.Key_X)
        assert not _override_accepted(tree, Qt.Key.Key_Delete)
        count = len(scene.objects)
        QTest.keyClick(tree, Qt.Key.Key_F2)
        _settle()
        assert tree.state() != QAbstractItemView.State.EditingState
        QTest.keyClick(tree, Qt.Key.Key_Delete)
        _settle()
        assert len(scene.objects) == count
        QTest.keyClick(tree, Qt.Key.Key_F6)
        _settle()
        assert tree.state() == QAbstractItemView.State.EditingState
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Escape)
        _settle()
        tree.setFocus()
        _settle()
        QTest.keyClick(tree, Qt.Key.Key_X)
        _settle()
        assert len(scene.objects) == count - 1
        controls.select("standard")
        _settle()
        scene.undo()
        scene.set_active(scene.objects[0])
        scene.select_object(True)
        tree.setFocus()
        _settle()
        QTest.keyClick(tree, Qt.Key.Key_Delete)
        _settle()
        assert len(scene.objects) == count - 1
    finally:
        _close(win)
        _end_store()


def _group_button():
    from quartz_studio.widgets.common import IconButton

    _app()
    host = QWidget()
    button = IconButton("move", "Move", parent=host, group=[("move", "Move"), ("rotate", "Rotate")])
    button.move(8, 8)
    host.resize(120, 120)
    host.show()
    _settle()
    _KEEP.append(host)
    opened: list[int] = []
    button.open_group_menu = lambda: opened.append(1)
    return button, opened


def _hold(button, wait_ms: int) -> None:
    QTest.mousePress(button, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(4, 4))
    QTest.qWait(wait_ms)
    QTest.mouseRelease(button, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(4, 4))
    _settle()


def test_icon_button_hold_follows_hold_ms() -> None:
    from quartz_studio.widgets.common import IconButton

    _fresh_store()
    try:
        assert IconButton.HOLD_MS == 380
        button, opened = _group_button()
        _hold(button, 260)
        assert button._hold_timer.interval() == 380
        assert not opened
        pid = _controls().duplicate("classic")
        _controls().set_cursor(pid, "hold_ms", 200)
        assert _controls().cursor("hold_ms") == 200
        _hold(button, 260)
        assert button._hold_timer.interval() == 200
        assert opened == [1]
        assert IconButton.HOLD_MS == 380
    finally:
        _end_store()


def test_status_bar_hints_are_todays_in_classic_and_standard() -> None:
    from quartz_studio.widgets import status_bar as sb

    _app()
    _fresh_store()
    try:
        for profile in ("classic", "standard"):
            _controls().select(profile)
            for (tool, mode), text in sb.TOOL_HINTS.items():
                modes = ("model", "points") if mode == "any" else (
                    ("model",) if mode == "model" else ("points", "edges", "polygons"))
                for m in modes:
                    if (tool, m) in sb.MODE_HINTS:
                        continue
                    assert sb.tool_hint(tool, m) == text, (profile, tool, m)
            for (tool, mode), text in sb.MODE_HINTS.items():
                assert sb.tool_hint(tool, mode) == text, (profile, tool, mode)
        assert sb.tool_hint("move", "model") == "Drag to move" + SEP + "Hold Ctrl to copy" + SEP + "Esc cancels"
        assert sb.tool_hint("move", "points") == ("Drag to move" + SEP + "Hold Ctrl to extrude" + SEP
                                                  + "Esc cancels")
        assert sb.tool_hint("rotate", "model") == ("Drag to rotate" + SEP + "Shift snaps to 5°" + SEP
                                                   + "Esc cancels")
        assert sb.tool_hint("scale", "edges") == ("Drag to scale" + SEP + "Shift snaps to 0.1" + SEP
                                                  + "Esc cancels")
        assert sb.tool_hint("pen", "points").endswith("Enter finishes")
        assert sb.tool_hint("line_pen", "points").endswith("Right click or Enter ends the line")
    finally:
        _end_store()


def test_status_bar_hints_follow_changed_roles() -> None:
    from quartz_studio.widgets import status_bar as sb

    _app()
    pid = _user_profile()
    controls = _controls()
    try:
        controls.set_modifier(pid, "snap", "ctrl")
        assert controls.modifier_name("snap") == "Ctrl"
        assert sb.tool_hint("rotate", "model") == ("Drag to rotate" + SEP + "Ctrl snaps to 5°" + SEP
                                                   + "Esc cancels")
        assert "Ctrl snaps to 0.1" in sb.tool_hint("scale", "model")
        assert "Shift snaps" not in sb.tool_hint("rotate", "points")
        controls.set_modifier(pid, "extrude", "alt")
        assert "Hold Alt to extrude" in sb.tool_hint("move", "polygons")
        assert "Hold Alt to copy" in sb.tool_hint("move", "model")
        mouse = [dict(g) for g in controls.active().mouse]
        for g in mouse:
            if g.get("button") == "left" and not g.get("key") and not g.get("double"):
                if g.get("op") == "add":
                    g["mods"] = ["ctrl"]
                elif g.get("op") == "remove":
                    g["mods"] = ["shift"]
        controls.set_mouse(pid, mouse)
        hint = sb.tool_hint("select", "polygons")
        assert "Ctrl adds" in hint and "Shift removes" in hint, hint
        assert "Shift deselects" in sb.tool_hint("select", "model")
        controls.reset_profile(pid)
        assert sb.tool_hint("rotate", "model") == sb.TOOL_HINTS[("rotate", "any")]
    finally:
        _end_store()


def test_status_bar_widget_refreshes_on_profile_change() -> None:
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.status_bar import StatusBar

    _app()
    pid = _user_profile()
    try:
        scene = reset_scene()
        bar = StatusBar()
        _KEEP.append(bar)
        scene.set_mode("model")
        scene.set_tool("rotate")
        _settle()
        assert "Shift snaps" in bar.hint_text()
        _controls().set_modifier(pid, "snap", "alt")
        _settle()
        assert "Alt snaps" in bar.hint_text(), bar.hint_text()
    finally:
        _end_store()


def test_status_bar_names_and_selection_hints() -> None:
    from quartz_studio.widgets import status_bar as sb

    _app()
    names = {"select": "Brush Selection", "select_loop": "Loop Selection", "select_ring": "Ring Selection",
             "select_pattern": "Pattern Selection", "select_fill": "Fill Selection",
             "select_phong": "Phong Angle Selection"}
    for tool, name in names.items():
        assert sb.TOOL_NAMES[tool] == name
        assert sb.tool_name(tool) == name
    brush_model = ("Paint over an object to select it" + SEP + "Ctrl deselects" + SEP
                   + "Shift+wheel sizes the brush")
    brush = "Paint to select" + SEP + "Shift adds" + SEP + "Ctrl removes" + SEP + "Shift+wheel sizes the brush"
    assert sb.TOOL_HINTS[("select", "model")] == brush_model
    assert sb.TOOL_HINTS[("select", "components")] == brush
    others = {
        "select_loop": "Click an edge to select its loop" + SEP + "Shift adds" + SEP + "Ctrl removes",
        "select_ring": "Click an edge to select its ring" + SEP + "Shift adds" + SEP + "Ctrl removes",
        "select_pattern": ("Click an edge to select a pattern along its loop" + SEP + "Shift adds" + SEP
                           + "Ctrl removes"),
        "select_fill": "Click a polygon to fill up to the selected edges" + SEP + "Ctrl removes",
        "select_phong": "Click a polygon to select its smooth area" + SEP + "Shift adds" + SEP + "Ctrl removes",
    }
    for tool, text in others.items():
        assert sb.TOOL_HINTS[(tool, "any")] == text
        for mode in ("model", "points", "edges", "polygons"):
            assert sb.tool_hint(tool, mode) == text
    assert sb.tool_hint("select", "model") == brush_model
    for mode in ("points", "edges", "polygons"):
        assert sb.tool_hint("select", mode) == brush
    assert not [k for k in sb.TOOL_HINTS if k[0] == "select" and k[1] not in ("model", "components")]
    try:
        from quartz_studio.modeling import select_tools
    except ImportError:
        return
    for tool in select_tools.TOOLS:
        assert sb.TOOL_NAMES[tool.id] == tool.name, tool.id
        if tool.id == "select":
            assert sb.TOOL_HINTS[("select", "components")] == tool.hint
            assert sb.TOOL_HINTS[("select", "model")] == tool.hint_model
        else:
            assert sb.TOOL_HINTS[(tool.id, "any")] == tool.hint, tool.id


def _texts(menu) -> dict[str, str]:
    out = {}
    for act in menu.actions():
        if act.isSeparator():
            continue
        out[act.property("qs_label") or act.text()] = act.property("qs_shortcut") or ""
    return out


def _component_texts(win, scene) -> dict[str, str]:
    from quartz_studio.widgets import context_menu

    menu = context_menu.build_component_menu(scene, win.viewport.canvas)
    try:
        texts = _texts(menu)
        select = menu.submenu("Select")
        if select is not None:
            texts.update({"Select/" + k: v for k, v in _texts(select).items()})
        return texts
    finally:
        menu.deleteLater()


def test_context_menus_show_the_active_profile_bindings() -> None:
    from quartz_studio.modeling import get_tool
    from quartz_studio.widgets import context_menu

    _fresh_store()
    win = _window()
    try:
        scene = win.object_manager.tree._scene
        obj = scene.objects[0]
        canvas = win.viewport.canvas
        menu = context_menu.build_object_menu(scene, obj, canvas)
        texts = _texts(menu)
        menu.deleteLater()
        assert texts["Undo"] == "Ctrl+Z" and texts["Redo"] == "Ctrl+Y"
        assert texts["Frame Selected"] == "S" and texts["Frame All"] == "H"
        empty = context_menu.build_empty_menu(scene, canvas)
        assert _texts(empty)["Frame All"] == "H"
        empty.deleteLater()
        scene.set_active(obj)
        scene.make_editable(obj)
        obj = scene.active
        scene.set_mode("polygons")
        scene.select_components([0])
        _settle()
        texts = _component_texts(win, scene)
        assert texts["Polygon Pen"] == "M~E"
        assert texts["Extrude"] == get_tool("extrude").shortcut == "M~T"
        assert texts["Delete"] == "Delete"
        assert texts["Select/Loop Selection"] == "U~L"
        _controls().select("standard")
        _settle()
        menu = context_menu.build_object_menu(scene, obj, canvas)
        texts = _texts(menu)
        menu.deleteLater()
        assert texts["Undo"] == "Ctrl+Z" and texts["Redo"] == "Ctrl+Shift+Z"
        assert texts["Frame Selected"] == "F" and texts["Frame All"] == "A"
        texts = _component_texts(win, scene)
        assert texts["Polygon Pen"] == "P"
        assert texts["Extrude"] == "Ctrl+E" and texts["Bevel"] == "Ctrl+B"
        assert texts["Delete"] == "Delete"
        assert texts["Select/Loop Selection"] == ""
        assert texts["Select/Invert"] == "Ctrl+I"
    finally:
        _close(win)
        _end_store()


def _controls_dialogs() -> list:
    return [w for w in QApplication.topLevelWidgets()
            if isinstance(w, QDialog) and w.objectName() == "qsControlsDialog" and w.isVisible()]


def test_edit_controls_exists_in_both_profiles_and_opens_one_dialog() -> None:
    _fresh_store()
    win = _window()
    try:
        bar = win.menu_bar
        edit = bar.menus["Edit"]
        assert edit.entries_text() == ["Undo", "Redo", "---", "Controls..."], edit.entries_text()
        act = bar.action_at(("Edit", "Controls..."))
        assert act.property("qs_shortcut") == "Shift+F12"
        assert act.text() == "Controls...\tShift+F12"
        act.trigger()
        _settle()
        assert len(_controls_dialogs()) == 1
        act.trigger()
        _settle()
        assert len(_controls_dialogs()) == 1
        for dialog in _controls_dialogs():
            dialog.close()
        _settle()
        _controls().select("standard")
        _settle()
        assert edit.entries_text() == ["Undo", "Redo", "---", "Controls..."]
        assert act.property("qs_shortcut") == "Ctrl+,"
        act.trigger()
        _settle()
        assert len(_controls_dialogs()) == 1
    finally:
        _close(win)
        _end_store()


def test_main_menu_shows_the_active_profile_bindings_live() -> None:
    _fresh_store()
    win = _window()
    try:
        bar = win.menu_bar
        checks = {("Edit", "Undo"): ("Ctrl+Z", "Ctrl+Z"), ("Edit", "Redo"): ("Ctrl+Y", "Ctrl+Shift+Z"),
                  ("File", "Exit"): ("Alt+F4", "Ctrl+Q"), ("File", "Import..."): ("", "Ctrl+Shift+I"),
                  ("Mesh", "Make Editable"): ("C", "Alt+C"), ("Mesh", "Polygon Pen"): ("M~E", "P")}
        for path, (classic, _standard) in checks.items():
            act = bar.action_at(path)
            assert act is not None, path
            assert (act.property("qs_shortcut") or "") == classic, (path, act.property("qs_shortcut"))
        _controls().select("standard")
        _settle()
        for path, (_classic, standard) in checks.items():
            act = bar.action_at(path)
            assert (act.property("qs_shortcut") or "") == standard, (path, act.property("qs_shortcut"))
            label = path[-1]
            assert act.text() == (f"{label}\t{standard}" if standard else label)
        _controls().select("classic")
        _settle()
        assert bar.action_at(("Mesh", "Make Editable")).property("qs_shortcut") == "C"
    finally:
        _close(win)
        _end_store()


def test_rail_transform_and_pen_tooltips_follow_the_profile() -> None:
    _fresh_store()
    win = _window()
    try:
        rail = win.tool_palette
        controls = _controls()
        expected = {"classic": {"Move": "E", "Rotate": "R", "Scale": "T"},
                    "standard": {"Move": "W", "Rotate": "E", "Scale": "R"}}
        for pid in ("classic", "standard", "classic"):
            controls.select(pid)
            _settle()
            for name, key in expected[pid].items():
                assert rail.buttons[name].toolTip() == f"{name} ({key})", (pid, name, rail.buttons[name].toolTip())
            pen = rail.buttons["Pen"]
            for label, aid in (("Polygon Pen", "tool.pen"), ("Pen", "tool.line_pen")):
                text = controls.binding_text(aid)
                assert pen.tooltips.get(label) == (f"{label} ({text})" if text else label), (pid, label)
            assert pen.toolTip() == pen.tooltips[pen.command_text()], (pid, pen.toolTip())
    finally:
        _close(win)
        _end_store()


def test_extension_items_register_actions_and_fire_in_both_profiles() -> None:
    _fresh_store()
    win = _window()
    try:
        calls: list[str] = []
        bar = win.menu_bar
        bar.add_menu("Render", [("Render View", lambda: calls.append("view"), "Ctrl+Alt+Shift+R"), None,
                                ("Settings", [("Quality...", lambda: calls.append("quality"), None)])])
        actions = _controls().actions()
        assert "menu.render.render_view" in actions
        assert "menu.render.settings.quality" in actions
        view = actions["menu.render.render_view"]
        assert view.category == "Render" and view.default_keys == ("Ctrl+Alt+Shift+R",)
        assert actions["menu.render.settings.quality"].label == "Quality"
        assert bar.extension_shortcuts
        assert all(isinstance(sc, QShortcut) for sc in bar.extension_shortcuts)
        assert bar.action_at(("Render", "Render View")).property("qs_shortcut") == "Ctrl+Alt+Shift+R"
        for profile in ("classic", "standard"):
            _controls().select(profile)
            _settle()
            calls.clear()
            win.activateWindow()
            win.setFocus()
            _settle()
            QTest.keyClick(win, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier
                           | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
            _settle()
            assert calls == ["view"], (profile, calls)
            assert bar.action_at(("Render", "Render View")).property("qs_shortcut") == "Ctrl+Alt+Shift+R"
        assert _controls().run("menu.render.settings.quality")
        assert calls[-1] == "quality"
        bar.add_entries("File", [("Export Animation", lambda: calls.append("anim"), None)])
        assert "menu.file.export_animation" in _controls().actions()
        assert _controls().actions()["menu.file.export_animation"].category == "File"
    finally:
        _close(win)
        _end_store()


def test_create_object_reads_the_create_roles() -> None:
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets import menu_bar

    _app()
    pid = _user_profile()
    controls = _controls()
    try:
        scene = reset_scene()
        base = scene.active
        child = menu_bar.create_object("cube", Qt.KeyboardModifier.ShiftModifier)
        assert child.parent is base
        scene.set_active(base)
        plain = menu_bar.create_object("cube", Qt.KeyboardModifier.ControlModifier)
        assert plain.parent is None
        controls.set_modifier(pid, "create_child", "ctrl")
        scene.set_active(base)
        plain = menu_bar.create_object("cube", Qt.KeyboardModifier.ShiftModifier)
        assert plain.parent is None
        scene.set_active(base)
        child = menu_bar.create_object("cube", Qt.KeyboardModifier.ControlModifier)
        assert child.parent is base
        from quartz_studio import objects

        gen = next((s for s in objects.all_specs() if s.inputs == "children"), None)
        if gen is not None:
            scene.set_active(base)
            made = menu_bar.create_object(gen.id, Qt.KeyboardModifier.AltModifier)
            assert base.parent is made
            controls.set_modifier(pid, "create_adopt", "shift")
            target = menu_bar.create_object("cube")
            scene.set_active(target)
            made = menu_bar.create_object(gen.id, Qt.KeyboardModifier.ShiftModifier)
            assert target.parent is made
    finally:
        _end_store()


def test_menus_data_select_and_edit_entries() -> None:
    from quartz_studio.widgets import menus_data
    from quartz_studio.widgets.menu_bar import SCENE_COMMANDS, open_controls

    labels = [e[1] for e in menus_data.SELECT_MENU if e[0] == "item"]
    assert labels.index("Pattern Selection") == labels.index("Ring Selection") + 1
    assert "Phong Angle Selection" in labels and "Phong Break Selection" not in labels
    edit = [e for e in menus_data.EDIT_MENU if e[0] == "item"]
    controls_item = next(e for e in edit if e[1] == "Controls...")
    assert controls_item[2] == "Shift+F12"
    assert "Customize Commands..." not in [e[1] for e in edit]
    assert (("Edit", "Controls..."), open_controls) in SCENE_COMMANDS
    paths = [p for p, _fn in SCENE_COMMANDS]
    assert paths.index(("Edit", "Controls...")) == paths.index(("Edit", "Redo")) + 1


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
