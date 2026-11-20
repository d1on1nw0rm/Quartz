from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import types
from contextlib import redirect_stderr

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from quartz_studio.app import create_app
from quartz_studio.fileio import FileFormatError, open_scene, save_scene
from quartz_studio.scene import Scene

TMP = tempfile.mkdtemp(prefix="qz_hooks_")
EXT_NAME = "quartz_studio.ext.install"


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(passes: int = 6) -> None:
    app = _app()
    for _ in range(passes):
        app.processEvents()


def _scene() -> Scene:
    _app()
    return Scene()


def _window(width: int = 1280, height: int = 720):
    from quartz_studio.main_window import MainWindow

    _app()
    win = MainWindow()
    win.setMinimumSize(1, 1)
    win.resize(width, height)
    win.show()
    _settle()
    win.apply_default_sizes()
    _settle()
    return win


def _close(win) -> None:
    win.close()
    win.deleteLater()
    _settle()


def _rect(win: QWidget, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(win, QPoint(0, 0)), widget.size())


def _model_rects(win) -> dict:
    names = ("tool_palette", "viewport", "object_manager", "attribute_manager", "coordinates",
             "object_palette", "menu_bar", "command_bar")
    out = {n: _rect(win, win.regions[n]) for n in names}
    out["mode_switcher"] = _rect(win, win.command_bar.mode_switcher)
    return out


def _tmp(name: str) -> str:
    return os.path.join(TMP, name)


def test_extras_default_empty() -> None:
    scene = _scene()
    assert scene.extras == {}
    assert all(o.extras == {} for o in scene.objects)
    assert not scene.can_undo()


def test_object_extra_set_undo_redo() -> None:
    scene = _scene()
    cube = scene.objects[0]
    changes = []
    scene.changed.connect(lambda: changes.append(1))
    assert scene.set_object_extra(cube, "material", {"color": [1, 0, 0]}) is True
    assert changes
    assert cube.extras == {"material": {"color": [1, 0, 0]}}
    assert scene.undo()
    assert scene.objects[0].extras == {}
    assert scene.redo()
    assert scene.objects[0].extras == {"material": {"color": [1, 0, 0]}}


def test_scene_extra_set_undo_redo() -> None:
    scene = _scene()
    assert scene.set_extra("fps", 24) is True
    assert scene.extras == {"fps": 24}
    assert scene.undo()
    assert scene.extras == {}
    assert scene.redo()
    assert scene.extras == {"fps": 24}


def test_none_removes_the_key() -> None:
    scene = _scene()
    cube = scene.objects[0]
    scene.set_object_extra(cube, "tag", "a")
    scene.set_extra("k", 1)
    assert scene.set_object_extra(cube, "tag", None) is True
    assert scene.set_extra("k", None) is True
    assert "tag" not in scene.objects[0].extras
    assert "k" not in scene.extras
    depth = len(scene._undo)
    assert scene.set_extra("missing", None) is False
    assert len(scene._undo) == depth
    scene.undo()
    assert scene.extras == {"k": 1}


def test_equal_value_adds_no_undo_step() -> None:
    scene = _scene()
    cube = scene.objects[0]
    scene.set_object_extra(cube, "data", {"a": [1, 2]})
    scene.set_extra("data", [1, 2.5])
    depth = len(scene._undo)
    assert scene.set_object_extra(cube, "data", {"a": [1, 2]}) is False
    assert scene.set_extra("data", [1, 2.5]) is False
    assert len(scene._undo) == depth
    assert scene.set_extra("data", [1, 2.5, 3]) is True
    assert len(scene._undo) == depth + 1


def test_deep_copy_isolation() -> None:
    scene = _scene()
    cube = scene.objects[0]
    value = {"list": [1, 2]}
    scene.set_object_extra(cube, "v", value)
    value["list"].append(3)
    assert cube.extras["v"] == {"list": [1, 2]}
    scene.set_extra("s", {"n": 1})
    cube.extras["v"]["list"].append(99)
    scene.extras["s"]["n"] = 2
    snap = scene._snapshot()
    cube.extras["v"]["list"].append(100)
    scene.extras["s"]["n"] = 3
    assert snap["objects"][0]["extras"]["v"]["list"] == [1, 2, 99]
    assert snap["extras"]["s"]["n"] == 2
    scene._restore(snap)
    restored = scene.objects[0]
    restored.extras["v"]["list"].append(7)
    scene.extras["s"]["n"] = 9
    assert snap["objects"][0]["extras"]["v"]["list"] == [1, 2, 99]
    assert snap["extras"]["s"]["n"] == 2


def test_make_editable_carries_extras() -> None:
    scene = _scene()
    sphere = scene.add_parametric("sphere")
    scene.set_object_extra(sphere, "uv", {"seams": [1, 2]})
    new = scene.make_editable(sphere)
    assert new is not sphere
    assert new.extras == {"uv": {"seams": [1, 2]}}
    new.extras["uv"]["seams"].append(3)
    assert sphere.extras["uv"]["seams"] == [1, 2]


def test_replace_clears_scene_extras() -> None:
    scene = _scene()
    scene.set_extra("fps", 30)
    scene.insert_objects([], [], activate=False, replace=True)
    assert scene.extras == {}


def test_quartz_roundtrip_with_extras() -> None:
    scene = _scene()
    cube = scene.objects[0]
    null = scene.add_parametric("null")
    scene.set_object_extra(cube, "material", {"name": "Red", "rgb": [1.0, 0.0, 0.0]})
    scene.set_object_extra(null, "tags", ["a", "b"])
    scene.set_extra("timeline", {"fps": 24, "range": [0, 90], "loop": True, "note": None})
    path = _tmp("extras.quartz")
    save_scene(scene, path)
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["scene"]["extras"]["timeline"]["fps"] == 24
    assert data["scene"]["objects"][0]["extras"]["material"]["name"] == "Red"
    other = _scene()
    other.set_extra("stale", 1)
    open_scene(other, path)
    by_name = {o.name: o for o in other.objects}
    assert by_name[cube.name].extras == {"material": {"name": "Red", "rgb": [1.0, 0.0, 0.0]}}
    assert by_name[null.name].extras == {"tags": ["a", "b"]}
    assert other.extras == {"timeline": {"fps": 24, "range": [0, 90], "loop": True, "note": None}}
    assert not other.can_undo()


def test_scene_without_extras_writes_no_extras_keys() -> None:
    scene = _scene()
    null = scene.add_parametric("null")
    scene.add_parametric("sphere", parent=null)
    path = _tmp("plain.quartz")
    save_scene(scene, path)
    raw = open(path, "rb").read()
    assert b"extras" not in raw
    data = json.loads(raw.decode("utf-8"))
    assert "extras" not in data["scene"]
    assert all("extras" not in o for o in data["scene"]["objects"])
    scene.set_extra("k", 1)
    scene.set_extra("k", None)
    again = _tmp("plain_again.quartz")
    save_scene(scene, again)
    assert open(again, "rb").read() == raw


def test_old_file_opens_without_extras() -> None:
    path = _tmp("old.quartz")
    payload = {"format": "quartz", "version": 1, "app": "0.0", "scene": {
        "unit": "cm", "objects": [{"name": "Old", "kind": "polygon", "parent": None, "enabled": True,
                                   "position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1],
                                   "mesh": None}]}, "view": {}}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    scene = _scene()
    open_scene(scene, path)
    assert scene.extras == {}
    assert [o.extras for o in scene.objects] == [{}]


def test_non_json_extra_is_refused_on_save() -> None:
    scene = _scene()
    path = _tmp("refused.quartz")
    save_scene(scene, path)
    before = open(path, "rb").read()
    for bad in ({1, 2}, object(), float("nan"), {3: "int key"}):
        scene.objects[0].extras = {"bad": bad}
        try:
            save_scene(scene, path)
        except FileFormatError:
            pass
        else:
            raise AssertionError(f"{bad!r} was accepted")
        assert open(path, "rb").read() == before
    scene.objects[0].extras = {}
    scene.extras = {"bad": b"bytes"}
    try:
        save_scene(scene, path)
    except FileFormatError:
        pass
    else:
        raise AssertionError("bytes in scene extras were accepted")
    assert open(path, "rb").read() == before


def test_pages_add_show_and_switcher() -> None:
    win = _window()
    try:
        assert win.page_ids() == ["model"]
        assert win.current_page() == "model"
        assert win.page_switcher.isHidden()
        before = _model_rects(win)
        seen = []
        win.pageChanged.connect(seen.append)
        page = QLabel("Material page")
        assert win.add_page("materials", "Materials", page) is page
        _settle()
        assert win.page_ids() == ["model", "materials"]
        assert not win.page_switcher.isHidden()
        assert win.current_page() == "model"
        assert seen == []
        win.show_page("materials")
        _settle()
        assert win.current_page() == "materials"
        assert seen == ["materials"]
        assert page.isVisible()
        assert not win.model_page.isVisible()
        assert win.page_switcher.buttons["materials"].isChecked()
        win.show_page("materials")
        assert seen == ["materials"]
        win.page_switcher.buttons["model"].click()
        _settle()
        assert win.current_page() == "model"
        assert seen == ["materials", "model"]
        win.apply_default_sizes()
        _settle()
        after = _model_rects(win)
        for name in before:
            if name in ("menu_bar", "command_bar"):
                continue
            assert before[name] == after[name], (name, before[name], after[name])
        mode_before, mode_after = before["mode_switcher"], after["mode_switcher"]
        assert abs(mode_before.center().x() - mode_after.center().x()) <= 1
        switch = _rect(win, win.page_switcher)
        assert switch.right() < mode_after.left()
        assert switch.left() > _rect(win, win.menu_bar).right()
        try:
            win.show_page("nope")
        except KeyError:
            pass
        else:
            raise AssertionError("unknown page accepted")
        try:
            win.add_page("materials", "Again", QLabel())
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate page accepted")
    finally:
        _close(win)


def test_docks_bottom_left_right() -> None:
    win = _window()
    try:
        assert win.bottom_splitter is None and win.left_dock_column is None
        timeline = QLabel("Timeline")
        timeline.setMinimumHeight(96)
        assert win.add_dock("timeline", "Timeline", timeline, "bottom") is timeline
        lib = QLabel("Library")
        win.add_dock("library", "Library", lib, "left")
        mats = QLabel("Materials")
        win.add_dock("materials", "Materials", mats, "right")
        _settle()
        win.apply_default_sizes()
        _settle()
        assert win.dock("timeline") is timeline and win.dock("nope") is None
        assert win.bottom_splitter.indexOf(win.viewport) == 0
        assert win.bottom_splitter.indexOf(timeline) == 1
        assert win.body_splitter.widget(0) is win.left_dock_column
        assert win.manager_splitter.indexOf(mats) >= 0
        from quartz_studio.widgets.common import is_card

        assert all(is_card(w) for w in (timeline, lib, mats))
        vp, tl = _rect(win, win.viewport), _rect(win, timeline)
        assert tl.top() > vp.bottom() and tl.height() >= 96
        assert abs(tl.left() - vp.left()) <= 1
        assert _rect(win, lib).right() < _rect(win, win.tool_palette).left()
        assert _rect(win, mats).left() >= _rect(win, win.object_manager).left()
        assert win.object_palette.parentWidget() is win.viewport
        for dock_id, widget in (("timeline", timeline), ("library", lib), ("materials", mats)):
            win.set_dock_visible(dock_id, False)
            _settle()
            assert not win.is_dock_visible(dock_id) and not widget.isVisible()
        assert win.left_dock_column.isHidden()
        win.apply_default_sizes()
        _settle()
        assert _rect(win, win.viewport).bottom() > vp.bottom()
        win.set_dock_visible("library", True)
        _settle()
        assert lib.isVisible() and not win.left_dock_column.isHidden()
        try:
            win.add_dock("x", "X", QLabel(), "top")
        except ValueError:
            pass
        else:
            raise AssertionError("bad area accepted")
    finally:
        _close(win)


def test_menu_add_menu_with_handler_separator_submenu_and_shortcut() -> None:
    win = _window()
    try:
        calls = []
        bar = win.menu_bar
        menu = bar.add_menu("Render", [
            ("Render View", lambda: calls.append("view"), "Ctrl+Alt+Shift+R"),
            None,
            ("Settings", [("Quality", lambda: calls.append("quality"), None)]),
        ])
        assert bar.menus["Render"] is menu
        assert "Render" in bar.titles()
        from quartz_studio.widgets.menu_bar import StudioMenu

        assert isinstance(menu, StudioMenu)
        assert menu.entries_text() == ["Render View", "---", "Settings"]
        sub = menu.submenu("Settings")
        assert isinstance(sub, StudioMenu)
        menu.find_action("Render View").trigger()
        sub.find_action("Quality").trigger()
        assert calls == ["view", "quality"]
        win.activateWindow()
        win.setFocus()
        _settle()
        QTest.keyClick(win, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
        _settle()
        assert calls == ["view", "quality", "view"], calls
        try:
            bar.add_menu("Render", [])
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate menu accepted")
    finally:
        _close(win)


def test_menu_add_entries_on_file() -> None:
    win = _window()
    try:
        calls = []
        bar = win.menu_bar
        before = bar.menus["File"].entries_text()
        menu = bar.add_entries("File", [("Export Animation", lambda: calls.append(1), None)])
        assert menu is bar.menus["File"]
        after = menu.entries_text()
        assert after[:len(before)] == before
        assert after[len(before):] == ["---", "Export Animation"]
        menu.find_action("Export Animation").trigger()
        assert calls == [1]
        try:
            bar.add_entries("Nope", [])
        except KeyError:
            pass
        else:
            raise AssertionError("unknown menu accepted")
    finally:
        _close(win)


class _ExtModule:

    def __enter__(self):
        import quartz_studio.ext as ext_pkg

        self.pkg = ext_pkg
        self.saved_module = sys.modules.get(EXT_NAME, False)
        self.saved_attr = ext_pkg.__dict__.get("install", False)
        ext_pkg.__dict__.pop("install", None)
        return self

    def set(self, module) -> None:
        sys.modules[EXT_NAME] = module

    def __exit__(self, *exc) -> None:
        if self.saved_module is False:
            sys.modules.pop(EXT_NAME, None)
        else:
            sys.modules[EXT_NAME] = self.saved_module
        self.pkg.__dict__.pop("install", None)
        if self.saved_attr is not False:
            self.pkg.install = self.saved_attr


def _fake(fn) -> types.ModuleType:
    module = types.ModuleType(EXT_NAME)
    module.install = fn
    return module


def test_extension_hook_calls_install() -> None:
    from quartz_studio import app as app_module

    seen = []
    with _ExtModule() as ext:
        ext.set(_fake(seen.append))
        win = object()
        assert app_module.install_extensions(win) is True
    assert seen == [win]


def test_extension_hook_without_package_does_nothing() -> None:
    from quartz_studio import app as app_module

    with _ExtModule() as ext:
        ext.set(None)
        err = io.StringIO()
        with redirect_stderr(err):
            assert app_module.install_extensions(object()) is False
        assert err.getvalue() == ""


def test_extension_hook_survives_a_raising_install() -> None:
    from quartz_studio import app as app_module

    def boom(_window):
        raise RuntimeError("extension exploded")

    with _ExtModule() as ext:
        ext.set(_fake(boom))
        err = io.StringIO()
        with redirect_stderr(err):
            assert app_module.install_extensions(object()) is False
        assert "extension exploded" in err.getvalue()


def _isolated_main(argv: list[str]) -> int:
    from quartz_studio import app as app_module
    from quartz_studio import controls, prefs

    folder = tempfile.mkdtemp(prefix="quartz-main-")
    saved_env = os.environ.get("QUARTZ_PREFS_DIR")
    saved_store = controls.STORE_PATH
    os.environ["QUARTZ_PREFS_DIR"] = folder
    controls.STORE_PATH = os.path.join(folder, "controls.json")
    try:
        return app_module.main(argv)
    finally:
        controls.STORE_PATH = saved_store
        if saved_env is None:
            os.environ.pop("QUARTZ_PREFS_DIR", None)
        else:
            os.environ["QUARTZ_PREFS_DIR"] = saved_env
        prefs._state["user"] = False
        prefs.reload()
        controls.reset()


def test_main_runs_with_a_raising_extension() -> None:
    calls = []

    def boom(window):
        calls.append(window)
        raise RuntimeError("extension exploded in main")

    qapp = _app()
    with _ExtModule() as ext:
        ext.set(_fake(boom))
        QTimer.singleShot(500, qapp.quit)
        err = io.StringIO()
        with redirect_stderr(err):
            assert _isolated_main([sys.argv[0]]) == 0
    assert len(calls) == 1
    from quartz_studio.main_window import MainWindow

    assert isinstance(calls[0], MainWindow)
    assert "extension exploded in main" in err.getvalue()
    for w in QApplication.topLevelWidgets():
        if w.isWindow():
            w.close()
    _settle()


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
