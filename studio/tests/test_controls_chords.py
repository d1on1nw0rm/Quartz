from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

_TMP = tempfile.mkdtemp(prefix="qs-controls-chords-")
os.environ["QUARTZ_PREFS_DIR"] = os.path.join(_TMP, "prefs")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from quartz_studio import prefs
from quartz_studio.app import create_app

NO_MOD = Qt.KeyboardModifier.NoModifier
LEFT = Qt.MouseButton.LeftButton
WAIT_MS = 320

_STATE: dict = {}


def _controls():
    from quartz_studio import controls

    return controls


def _settle(n: int = 4) -> None:
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _window():
    if "window" in _STATE:
        return _STATE["window"]
    app = create_app([sys.argv[0]])
    controls = _controls()
    controls.STORE_PATH = os.path.join(_TMP, "controls.json")
    from quartz_studio.main_window import MainWindow
    from quartz_studio.modeling import install as mi

    mi.prepare()
    win = MainWindow()
    if getattr(win, "controls_filter", None) is None:
        for sc in win.findChildren(QShortcut):
            sc.setEnabled(False)
            sc.setParent(None)
            sc.deleteLater()
        controls.install(win)
    mi.install(win)
    win.resize(1500, 900)
    win.show()
    win.activateWindow()
    _settle(6)
    _STATE["window"] = win
    _STATE["app"] = app
    return win


def _select(profile_id: str) -> None:
    controls = _controls()
    if controls.active_id() != profile_id:
        controls.select(profile_id)
    _settle(2)
    _window().controls_filter.clear()


def _fresh_cube(mode: str = "polygons"):
    from quartz_studio.scene import Mesh, get_scene

    scene = get_scene()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_object("Cube", Mesh.cube(200.0))
    scene._undo.clear()
    scene._redo.clear()
    scene.set_mode(mode)
    return scene


def _focus(widget) -> None:
    win = _window()
    win.activateWindow()
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    _settle(2)


def _canvas():
    return _window().viewport.canvas


def _key(target, letter: str) -> None:
    key = QKeySequence(letter)[0].key()
    QTest.sendKeyEvent(QTest.KeyAction.Click, target, key, letter.lower(), NO_MOD)
    _settle(2)


def _menu():
    flt = _window().controls_filter
    return flt._menu if flt._menu_open() else None


def _wait() -> None:
    QTest.qWait(WAIT_MS)


def _reset(mode: str = "polygons"):
    _select("classic")
    prefs.set("controls.chord_menu", None)
    scene = _fresh_cube(mode)
    _focus(_canvas())
    _window().controls_filter.clear()
    return scene


class _Spy:

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._saved: dict = {}

    def __enter__(self) -> "_Spy":
        for aid, action in _controls().actions().items():
            self._saved[aid] = (action, action.run, action.available)
            action.run = lambda a=aid: self.calls.append(a)
            action.available = None
        return self

    def __exit__(self, *_exc) -> None:
        for action, run, available in self._saved.values():
            action.run = run
            action.available = available


def _expected(prefix: str) -> dict[str, str]:
    controls = _controls()
    resolved = controls.active()
    out: dict[str, str] = {}
    for aid in controls.actions():
        for binding, scope in resolved.keys.get(aid, ()):
            if "~" in binding and binding.split("~", 1)[0].upper() == prefix:
                out.setdefault(binding.split("~", 1)[1].upper(), aid)
    return out


def _center(menu, label: str) -> QPoint:
    act = menu.find_action(label)
    assert act is not None, label
    return menu.actionGeometry(act).center()


def test_u_popup_lists_every_continuation_with_its_key() -> None:
    win = _window()
    _reset("polygons")
    expected = _expected("U")
    assert len(expected) >= 14, expected
    _key(_canvas(), "U")
    assert _menu() is None
    _wait()
    menu = _menu()
    assert menu is not None
    assert menu.keys() == expected
    registry = _controls().actions()
    labels = [registry[aid].label for aid in expected.values()]
    shown = [t for t in menu.entries_text() if t != "---"]
    assert sorted(shown) == sorted(labels), shown
    assert "---" in menu.entries_text()
    assert expected["G"] == "tool.grow_selection" and expected["K"] == "tool.shrink_selection"
    for aid, label, _cat, second, _enabled in menu.items:
        act = menu.find_action(label)
        assert act.property("qs_shortcut") == second, (aid, second)
    assert QApplication.focusWidget() is _canvas()
    assert QApplication.activePopupWidget() is None
    assert win.isActiveWindow()
    win.controls_filter.clear()
    assert _menu() is None


def test_second_key_runs_the_command_and_closes_the_popup() -> None:
    scene = _reset("polygons")
    scene.select_components([0])
    before = len(scene.selected_polygons)
    _key(_canvas(), "U")
    _wait()
    assert _menu() is not None
    _key(_canvas(), "G")
    assert _menu() is None
    grown = len(scene.selected_polygons)
    assert grown > before, (before, grown)
    _key(_canvas(), "U")
    _wait()
    assert _menu() is not None
    _key(_canvas(), "K")
    assert _menu() is None
    assert len(scene.selected_polygons) < grown
    assert _window().controls_filter._prefix is None


def test_the_open_popup_keeps_the_prefix_alive_past_the_chord_window() -> None:
    _reset("polygons")
    with _Spy() as spy:
        _key(_canvas(), "U")
        _wait()
        assert _menu() is not None
        flt = _window().controls_filter
        flt._prefix = (flt._prefix[0], flt._prefix[1] - 60.0)
        _key(_canvas(), "W")
        assert spy.calls == ["tool.select_connected"], spy.calls
        assert _menu() is None


def test_escape_closes_the_popup_and_runs_nothing() -> None:
    _reset("polygons")
    with _Spy() as spy:
        _key(_canvas(), "U")
        _wait()
        assert _menu() is not None
        QTest.keyClick(_canvas(), Qt.Key.Key_Escape)
        _settle(2)
        assert _menu() is None
        assert spy.calls == []
        _key(_canvas(), "G")
        assert spy.calls == []
        assert _window().controls_filter._prefix is None


def test_clicking_an_entry_runs_it_and_closes_the_popup() -> None:
    _reset("polygons")
    with _Spy() as spy:
        _key(_canvas(), "U")
        _wait()
        menu = _menu()
        assert menu is not None
        QTest.mouseClick(menu, LEFT, NO_MOD, _center(menu, "Ring Selection"))
        _settle(2)
        assert spy.calls == ["tool.ring_selection"], spy.calls
        assert _menu() is None
        assert _window().controls_filter._prefix is None


def test_clicking_elsewhere_or_a_non_continuation_key_closes_it_and_runs_nothing() -> None:
    _reset("polygons")
    with _Spy() as spy:
        _key(_canvas(), "U")
        _wait()
        assert _menu() is not None
        QTest.mouseClick(_window().object_manager.tree.viewport(), LEFT, NO_MOD, QPoint(4, 4))
        _settle(2)
        assert _menu() is None
        assert spy.calls == []
        _focus(_canvas())
        _window().controls_filter.clear()
        _key(_canvas(), "U")
        _wait()
        assert _menu() is not None
        _key(_canvas(), "H")
        assert _menu() is None
        assert spy.calls == ["view.frame_all"], spy.calls
        assert _window().controls_filter._prefix is None


def test_a_fast_chord_still_runs_and_no_popup_follows() -> None:
    scene = _reset("polygons")
    scene.select_components([0])
    before = len(scene.selected_polygons)
    _key(_canvas(), "U")
    _key(_canvas(), "G")
    assert len(scene.selected_polygons) > before
    assert _menu() is None
    _wait()
    assert _menu() is None
    assert not _window().controls_filter._timer.isActive()


def test_no_popup_while_a_text_field_has_focus_or_with_the_preference_off() -> None:
    win = _window()
    _reset("polygons")
    edit = QLineEdit(win)
    edit.setGeometry(8, 8, 96, 24)
    edit.show()
    _focus(edit)
    assert QApplication.focusWidget() is edit
    QTest.keyClick(edit, Qt.Key.Key_U)
    _wait()
    assert _menu() is None
    assert edit.text().lower() == "u"
    edit.deleteLater()
    _settle(2)
    _focus(_canvas())
    win.controls_filter.clear()
    prefs.set("controls.chord_menu", False)
    try:
        with _Spy() as spy:
            _key(_canvas(), "U")
            _wait()
            assert _menu() is None
            _key(_canvas(), "W")
            assert spy.calls == ["tool.select_connected"], spy.calls
    finally:
        prefs.set("controls.chord_menu", None)
    assert prefs.get("controls.chord_menu", True) is True


def test_no_popup_while_a_mouse_button_is_down() -> None:
    _reset("polygons")
    original = QApplication.mouseButtons
    QApplication.mouseButtons = staticmethod(lambda: LEFT)
    try:
        _key(_canvas(), "U")
        _wait()
        assert _menu() is None
    finally:
        QApplication.mouseButtons = original
    _window().controls_filter.clear()


def test_m_and_k_prefixes_show_their_own_entries() -> None:
    _reset("polygons")
    for prefix in ("M", "K"):
        expected = _expected(prefix)
        assert expected, prefix
        _key(_canvas(), prefix)
        _wait()
        menu = _menu()
        assert menu is not None, prefix
        assert menu.prefix == prefix
        assert menu.keys() == expected, prefix
        assert all(act.property("qs_shortcut") in expected for act in menu.actions()
                   if not act.isSeparator()), prefix
        QTest.keyClick(_canvas(), Qt.Key.Key_Escape)
        _settle(2)
        assert _menu() is None
    assert set(_expected("K")) == {"K", "L", "J"}
    _key(_canvas(), "K")
    _wait()
    assert "---" not in _menu().entries_text()
    _window().controls_filter.clear()


def test_entries_that_do_not_apply_in_the_mode_are_disabled() -> None:
    from quartz_studio.modeling import get_tool

    for mode in ("polygons", "edges", "model"):
        _reset(mode)
        _key(_canvas(), "U")
        _wait()
        menu = _menu()
        assert menu is not None, mode
        registry = _controls().actions()
        for aid, label, _cat, _second, enabled in menu.items:
            spec = get_tool(aid[5:])
            want = mode in spec.modes
            assert enabled == want, (mode, aid)
            act = menu.find_action(registry[aid].label)
            assert act.isEnabled() == want, (mode, aid)
        by_id = {aid: enabled for aid, _l, _c, _s, enabled in menu.items}
        if mode == "polygons":
            assert by_id["tool.outline_selection"] and not by_id["tool.fill_selection"]
        if mode == "edges":
            assert by_id["tool.fill_selection"] and not by_id["tool.outline_selection"]
        if mode == "model":
            assert not by_id["tool.outline_selection"] and not by_id["tool.fill_selection"]
        _window().controls_filter.clear()
        assert _menu() is None


def test_a_disabled_entry_does_nothing_when_clicked() -> None:
    _reset("polygons")
    with _Spy() as spy:
        _key(_canvas(), "U")
        _wait()
        menu = _menu()
        QTest.mouseClick(menu, LEFT, NO_MOD, _center(menu, "Fill Selection"))
        _settle(2)
        assert spy.calls == []
    _window().controls_filter.clear()


def test_the_popup_stays_inside_the_screen() -> None:
    from PySide6.QtGui import QGuiApplication

    from quartz_studio.controls import chord_menu, dispatch

    _reset("polygons")
    flt = _window().controls_filter
    area = QGuiApplication.primaryScreen().availableGeometry()
    for corner in (QPoint(area.right(), area.bottom()), QPoint(area.left(), area.top()),
                   QPoint(area.right(), area.top())):
        menu = chord_menu.build(_window(), dispatch._index(), "U", ("global",), lambda a: None)
        chord_menu.present(menu, corner)
        frame = menu.frameGeometry()
        assert area.contains(frame.topLeft()) and area.contains(frame.bottomRight()), (corner, frame, area)
        menu.hide()
        menu.deleteLater()
    flt.clear()


def test_standard_has_no_prefix_and_both_profiles_have_no_conflict() -> None:
    controls = _controls()
    _reset("polygons")
    _select("standard")
    try:
        assert controls.conflicts("classic") == []
        assert controls.conflicts("standard") == []
        assert not _expected("U") and not _expected("M") and not _expected("K")
        assert controls.active().keys["tool.grow_selection"] == (("Ctrl+Num++", "global"),)
        assert controls.active().keys["tool.shrink_selection"] == (("Ctrl+Num+-", "global"),)
        _focus(_canvas())
        for letter in ("U", "M", "K"):
            _key(_canvas(), letter)
            _wait()
            assert _menu() is None, letter
        _window().controls_filter.clear()
    finally:
        _select("classic")
    keys = controls.active().keys
    assert keys["tool.grow_selection"] == (("U~G", "global"),)
    assert keys["tool.shrink_selection"] == (("U~K", "global"),)


def test_a_user_profile_with_its_own_prefix_gets_the_popup() -> None:
    controls = _controls()
    _reset("polygons")
    pid = controls.duplicate("standard", "Chord Probe")
    try:
        controls.set_keys(pid, "tool.invert_selection", ["J~Z"])
        controls.set_keys(pid, "tool.select_connected", ["J~X"])
        _settle(2)
        assert controls.conflicts(pid) == []
        _focus(_canvas())
        _window().controls_filter.clear()
        _key(_canvas(), "J")
        _wait()
        menu = _menu()
        assert menu is not None
        assert menu.keys() == {"Z": "tool.invert_selection", "X": "tool.select_connected"}
        _key(_canvas(), "Z")
        assert _menu() is None
    finally:
        controls.delete(pid)
        _select("classic")


def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    tests.sort(key=lambda item: item[1].__code__.co_firstlineno)
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception:
            import traceback

            failed += 1
            print("FAIL", name)
            traceback.print_exc()
        else:
            passed += 1
            print("ok  ", name)
    print(f"{passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    code = _run_all()
    sys.stdout.flush()
    os._exit(1 if code else 0)
