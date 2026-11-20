from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

_TMP = tempfile.mkdtemp(prefix="qs-controls-dispatch-")
os.environ["QUARTZ_PREFS_DIR"] = os.path.join(_TMP, "prefs")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from quartz_studio.app import create_app

PORTABLE = QKeySequence.SequenceFormat.PortableText
NO_MOD = Qt.KeyboardModifier.NoModifier
PROFILES = ("classic", "standard")

_STATE: dict = {}


def _controls():
    from quartz_studio import controls

    return controls


def _actions_module():
    import importlib

    return importlib.import_module("quartz_studio.controls.actions")


def _ensure_controls(win) -> None:
    if getattr(win, "controls_filter", None) is not None:
        return
    for sc in win.findChildren(QShortcut):
        sc.setEnabled(False)
        sc.setParent(None)
        sc.deleteLater()
    _controls().install(win)


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
    _ensure_controls(win)
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
    win = _window()
    win.controls_filter.clear()


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


class _Spy:

    def __init__(self, win) -> None:
        self.win = win
        self.calls: list[str] = []
        self._saved: dict = {}
        self._tree: dict = {}

    def __enter__(self) -> "_Spy":
        for aid, action in _controls().actions().items():
            self._saved[aid] = (action, action.run, action.available)
            action.run = lambda a=aid: self.calls.append(a)
            action.available = None
        tree = self.win.object_manager.tree
        for name, aid in (("rename", "object.rename"), ("delete_active", "object.delete")):
            self._tree[name] = tree.__dict__.get(name)
            setattr(tree, name, lambda a=aid: self.calls.append(a) or True)
        return self

    def __exit__(self, *_exc) -> None:
        for action, run, available in self._saved.values():
            action.run = run
            action.available = available
        tree = self.win.object_manager.tree
        for name, saved in self._tree.items():
            if saved is None:
                tree.__dict__.pop(name, None)
            else:
                setattr(tree, name, saved)

    def take(self) -> list[str]:
        out, self.calls = self.calls, []
        return out


def _combo(text: str):
    seq = QKeySequence(text)
    assert seq.count() == 1, text
    comb = seq[0]
    return comb.key(), comb.keyboardModifiers()


def _part_event(part: str):
    if part == "#":
        return Qt.Key.Key_NumberSign, Qt.KeyboardModifier.ShiftModifier, "#"
    if part == ",":
        return Qt.Key.Key_Comma, NO_MOD, ","
    key, mods = _combo(part)
    return key, mods, part.lower() if len(part) == 1 else ""


def _click(target, key, mods=NO_MOD, text: str | None = None) -> None:
    if text is None:
        QTest.keyClick(target, key, mods)
    else:
        QTest.sendKeyEvent(QTest.KeyAction.Click, target, key, text, mods)
    _settle(2)


def _chord(target, chord: str) -> None:
    first, second = chord.split("~", 1)
    for part in (first, second):
        key, mods, text = _part_event(part)
        _click(target, key, mods, text)


def _focus(widget) -> None:
    win = _window()
    win.activateWindow()
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    _settle(2)


def _target(win, scope: str):
    if scope == "viewport":
        return win.viewport.canvas
    if scope == "objects":
        return win.object_manager.tree
    return win


def _live_bindings() -> list[tuple[str, str, str]]:
    controls = _controls()
    resolved = controls.active()
    taken: dict[tuple[str, str], str] = {}
    out = []
    for aid in controls.actions():
        for binding, scope in resolved.keys.get(aid, ()):
            key = (scope, binding.upper() if "~" in binding else QKeySequence(binding).toString(PORTABLE))
            if key in taken:
                continue
            taken[key] = aid
            out.append((aid, binding, scope))
    return out


def test_every_binding_runs_its_action_in_both_profiles() -> None:
    win = _window()
    try:
        for pid in PROFILES:
            _select(pid)
            scene = _fresh_cube("polygons")
            scene.select_components([0])
            live = _live_bindings()
            assert live, pid
            with _Spy(win) as spy:
                for aid, binding, scope in live:
                    target = _target(win, scope)
                    _focus(target)
                    assert QApplication.focusWidget() is target, (pid, aid, QApplication.focusWidget())
                    spy.take()
                    if "~" in binding:
                        _chord(target, binding)
                    else:
                        key, mods = _combo(binding)
                        _click(target, key, mods)
                    got = spy.take()
                    assert got == [aid], (pid, aid, binding, scope, got)
                    win.controls_filter.clear()
    finally:
        _select("classic")


def test_wired_menu_rail_and_dock_entries_map_to_actions() -> None:
    win = _window()
    controls = _controls()
    actions_module = _actions_module()
    from quartz_studio.widgets import menu_bar as mb

    registry = controls.actions()
    missing = []
    for path, _handler in mb.SCENE_COMMANDS:
        if win.menu_bar.action_at(path) is None:
            continue
        aid = actions_module.action_for_path(path)
        if aid is None or aid not in registry:
            missing.append(("menu", path, aid))
    from quartz_studio.widgets import tool_palette as tp

    rail = ["tool." + t for t in tp.SCENE_TOOLS.values()]
    rail += ["tool." + t for t in tp.PEN_COMMANDS.values()]
    rail += ["tool." + t for t in getattr(tp, "SELECT_COMMANDS", {}).values()]
    for group in win.tool_palette._groups:
        rail += ["tool." + spec.id for spec in group.specs]
    for aid in rail:
        if aid not in registry:
            missing.append(("rail", aid))
    from quartz_studio.widgets import object_palette as op

    for key, handler in op.CREATE_COMMANDS.items():
        if handler is mb.create_line:
            aid = "create.line"
        elif handler is mb.create_empty_polygon:
            aid = "create.empty_polygon"
        else:
            aid = actions_module.menu_action_id(("Create",) + tuple(key), handler)
        if aid not in registry:
            missing.append(("dock", key, aid))
    assert not missing, missing


def test_file_shortcuts_follow_the_active_profile() -> None:
    win = _window()
    controls = _controls()
    from quartz_studio.controls.dispatch import FILE_ORDER

    try:
        for pid in PROFILES:
            _select(pid)
            got = [sc.key().toString(PORTABLE) for sc in win.file_shortcuts]
            want = [QKeySequence(controls.binding_text(aid)).toString(PORTABLE) for aid in FILE_ORDER]
            assert len(got) == 6, (pid, got)
            assert got == want, (pid, got, want)
            assert got == ["Ctrl+N", "Ctrl+O", "Ctrl+Shift+O", "Ctrl+S", "Ctrl+Shift+S", "Ctrl+Alt+S"], got
    finally:
        _select("classic")


def test_single_k_press_runs_nothing() -> None:
    win = _window()
    _select("classic")
    _fresh_cube("polygons").select_components([0])
    with _Spy(win) as spy:
        for target in (win, win.viewport.canvas):
            _focus(target)
            spy.take()
            _click(target, Qt.Key.Key_K)
            assert spy.take() == [], target
            win.controls_filter.clear()
            _click(target, Qt.Key.Key_U)
            assert spy.take() == [], target
            win.controls_filter.clear()


def test_chords_fixed_by_the_new_filter() -> None:
    win = _window()
    _select("classic")
    _fresh_cube("polygons").select_components([0])
    cases = (("K~L", "tool.loop_path_cut"), ("K~J", "tool.plane_cut"), ("K~K", "tool.line_cut"),
             ("U~C", "tool.collapse"), ("U~S", "tool.subdivide"), ("U~U", "tool.untriangulate"),
             ("M~#", "tool.normal_scale"), ("M~,", "tool.normal_rotate"), ("M~E", "tool.pen"))
    with _Spy(win) as spy:
        for target in (win, win.viewport.canvas):
            for chord, aid in cases:
                _focus(target)
                spy.take()
                _chord(target, chord)
                got = spy.take()
                assert got == [aid], (target, chord, got)
                assert "object.make_editable" not in got


def test_u_c_runs_collapse_and_not_make_editable() -> None:
    win = _window()
    _select("classic")
    scene = _fresh_cube("points")
    scene.select_components([0, 1])
    before = len(scene.active.mesh.points)
    _focus(win)
    _chord(win, "U~C")
    _settle(4)
    assert scene.tool == "collapse", scene.tool
    assert len(scene.active.mesh.points) < before, (len(scene.active.mesh.points), before)


def test_real_key_press_through_the_window_runs_once() -> None:
    win = _window()
    handle = win.windowHandle()
    assert handle is not None
    try:
        _select("classic")
        _fresh_cube("polygons").select_components([0])
        with _Spy(win) as spy:
            _focus(win.viewport.canvas)
            spy.take()
            QTest.keyClick(handle, Qt.Key.Key_K)
            _settle(2)
            assert spy.take() == []
            QTest.keyClick(handle, Qt.Key.Key_L)
            _settle(2)
            assert spy.take() == ["tool.loop_path_cut"]
            QTest.keyClick(handle, Qt.Key.Key_Delete)
            _settle(2)
            assert spy.take() == ["tool.delete"]
            QTest.keyClick(handle, Qt.Key.Key_E)
            _settle(2)
            assert spy.take() == ["tool.move"]
            QTest.keyClick(handle, Qt.Key.Key_C)
            _settle(2)
            assert spy.take() == ["object.make_editable"]
        _select("standard")
        with _Spy(win) as spy:
            _focus(win.viewport.canvas)
            spy.take()
            QTest.keyClick(handle, Qt.Key.Key_W)
            _settle(2)
            assert spy.take() == ["tool.move"]
            QTest.keyClick(handle, Qt.Key.Key_K)
            _settle(2)
            assert spy.take() == ["tool.line_cut"]
            QTest.keyClick(handle, Qt.Key.Key_1, Qt.KeyboardModifier.KeypadModifier)
            _settle(2)
            assert spy.take() == ["camera.front"]
    finally:
        _select("classic")


def test_press_delivered_to_canvas_and_propagated_runs_once() -> None:
    win = _window()
    canvas = win.viewport.canvas
    try:
        for pid in PROFILES:
            _select(pid)
            _fresh_cube("polygons").select_components([0])
            with _Spy(win) as spy:
                _focus(canvas)
                spy.take()
                QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_K, NO_MOD, "k"))
                _settle(2)
                got = spy.take()
                want = [] if pid == "classic" else ["tool.line_cut"]
                assert got == want, (pid, got)
                if pid == "classic":
                    QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_K, NO_MOD, "k"))
                    _settle(2)
                    got = spy.take()
                    assert got == ["tool.line_cut"], (pid, got)
                win.controls_filter.clear()
                QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, NO_MOD, ""))
                _settle(2)
                want = ["tool.delete"] if pid == "classic" else ["edit.delete"]
                got = spy.take()
                assert got == want, (pid, got)
                _focus(win.viewport)
                spy.take()
                QApplication.sendEvent(win.viewport,
                                       QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, NO_MOD, ""))
                _settle(2)
                got = spy.take()
                assert got == want, (pid, got)
    finally:
        _select("classic")


def test_typing_in_a_line_edit_never_runs_a_binding() -> None:
    win = _window()
    edit = QLineEdit(win.object_manager)
    edit.show()
    try:
        for pid in PROFILES:
            _select(pid)
            with _Spy(win) as spy:
                _focus(edit)
                assert QApplication.focusWidget() is edit
                spy.take()
                QTest.keyClicks(edit, "mekulcuc1234qwertpfhso")
                _click(edit, Qt.Key.Key_NumberSign, Qt.KeyboardModifier.ShiftModifier, "#")
                _click(edit, Qt.Key.Key_Comma, NO_MOD, ",")
                assert spy.take() == [], pid
                assert edit.text().startswith("mekulcuc1234"), edit.text()
                edit.clear()
    finally:
        edit.deleteLater()
        _settle(2)
        _select("classic")


def test_ctrl_z_in_unmodified_coordinate_field_undoes_scene() -> None:
    win = _window()
    try:
        for pid in PROFILES:
            _select(pid)
            scene = _fresh_cube("model")
            scene.add_object("Extra")
            count = len(scene.objects)
            assert scene.can_undo()
            field = win.coordinates.field(0, 0)
            _focus(field)
            assert QApplication.focusWidget() is field
            QTest.keyClick(field, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            _settle(4)
            assert len(scene.objects) == count - 1, (pid, len(scene.objects), count)
    finally:
        _select("classic")


def test_switching_profile_live_changes_menus_tooltips_and_shortcuts() -> None:
    win = _window()
    controls = _controls()
    from quartz_studio.modeling import install as mi
    from quartz_studio.modeling.registry import get_tool

    canvas = win.viewport.canvas
    extrude = get_tool("extrude")
    expected = {
        "classic": {"redo": "Ctrl+Y", "extrude": "M~T", "editable": "C"},
        "standard": {"redo": "Ctrl+Shift+Z", "extrude": "Ctrl+E", "editable": "Alt+C"},
    }
    try:
        for pid in PROFILES:
            _select(pid)
            want = expected[pid]
            redo = win.menu_bar.action_at(("Edit", "Redo"))
            assert redo is not None
            assert redo.property("qs_shortcut") == want["redo"], (pid, redo.property("qs_shortcut"))
            item = win.menu_bar.action_at(("Mesh", "Extrude")) or win.menu_bar.action_at(
                ("Mesh", "Commands", "Extrude"))
            if item is not None:
                assert item.property("qs_shortcut") == want["extrude"], (pid, item.property("qs_shortcut"))
            assert mi.tool_tooltip(extrude) == f"Extrude ({want['extrude']})"
            button = win.tool_palette.buttons.get("Extrude")
            assert button is not None
            assert button.toolTip() == f"Extrude ({want['extrude']})", (pid, button.toolTip())
            keys = [sc.key().toString(PORTABLE) for sc in win.key_shortcuts.get("object.make_editable", ())]
            assert keys == [want["editable"]], (pid, keys)
            scene = _fresh_cube("model")
            _focus(canvas)
            scene.set_tool("scale")
            if pid == "classic":
                _click(canvas, Qt.Key.Key_E)
                assert scene.tool == "move", scene.tool
            else:
                _click(canvas, Qt.Key.Key_W)
                assert scene.tool == "move", scene.tool
                _click(canvas, Qt.Key.Key_E)
                assert scene.tool == "rotate", scene.tool
            assert controls.active_id() == pid
    finally:
        _select("classic")


def test_extension_item_gets_menu_slug_and_its_shortcut_fires() -> None:
    win = _window()
    controls = _controls()
    calls: list[str] = []
    bar = win.menu_bar
    if "Dispatch Probe" not in bar.menus:
        bar.add_menu("Dispatch Probe", [("Run Probe Item", lambda: calls.append("run"), "Ctrl+Alt+Shift+K")])
    _settle(2)
    aid = "menu.dispatch_probe.run_probe_item"
    assert aid in controls.actions(), sorted(a for a in controls.actions() if a.startswith("menu.dispatch"))
    try:
        for pid in PROFILES:
            _select(pid)
            assert controls.binding_text(aid) == "Ctrl+Alt+Shift+K", (pid, controls.binding_text(aid))
            assert any(sc.key().toString(PORTABLE) == "Ctrl+Alt+Shift+K" for sc in bar.extension_shortcuts)
            _focus(win)
            calls.clear()
            QTest.keyClick(win, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier
                           | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
            _settle(2)
            assert calls == ["run"], (pid, calls)
    finally:
        _select("classic")


def test_extension_menus_rebuild_shortcuts_once_per_install() -> None:
    from quartz_studio.controls import dispatch

    win = _window()
    controls = _controls()
    bar = win.menu_bar
    count = [0]
    orig = dispatch.refresh

    def counted() -> None:
        count[0] += 1
        orig()

    calls: list[str] = []
    entries = [(f"Batch Item {i}", lambda i=i: calls.append(i)) for i in range(40)]
    entries.append(("Batch Keyed", lambda: calls.append("keyed"), "Ctrl+Alt+Shift+J"))
    dispatch.refresh = counted
    try:
        if "Batch Probe" not in bar.menus:
            bar.add_menu("Batch Probe", [("Nested", entries[:20])] + entries[20:])
        assert count[0] == 1, count[0]
        count[0] = 0
        with controls.deferred_refresh():
            if "Batch Probe Two" not in bar.menus:
                bar.add_menu("Batch Probe Two", entries[:10])
            bar.add_entries("Batch Probe Two", entries[10:20])
            assert count[0] == 0, count[0]
        assert count[0] == 1, count[0]
    finally:
        dispatch.refresh = orig
    _settle(2)
    assert "menu.batch_probe.batch_keyed" in controls.actions()
    assert any(sc.key().toString(PORTABLE) == "Ctrl+Alt+Shift+J" for sc in bar.extension_shortcuts)
    _focus(win)
    QTest.keyClick(win, Qt.Key.Key_J, Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
    _settle(2)
    assert calls == ["keyed"], calls


def test_dropped_window_is_freed_with_its_key_filter() -> None:
    import gc
    import weakref

    from PySide6.QtWidgets import QWidget

    from quartz_studio.controls import dispatch

    win = _window()
    controls = _controls()

    def make():
        probe = QWidget()
        controls.install(probe)
        return weakref.ref(probe), weakref.ref(probe.controls_filter)

    try:
        first, first_filter = make()
        second, _second_filter = make()
        gc.collect()
        _settle(2)
        gc.collect()
        assert first() is None and first_filter() is None
        assert second() is not None
        assert all(w is not first() for w in dispatch._windows())
    finally:
        controls.install(win)
        gc.collect()
        _settle(2)
    assert second() is None
    assert win in dispatch._windows() and controls.window() is win


def test_held_set_is_shared_and_tracks_hold_keys() -> None:
    win = _window()
    controls = _controls()
    held = controls.held_set()
    assert held is controls.held_set()
    assert win.viewport.canvas._held_keys is held
    _select("classic")
    assert controls.hold_keys() == {int(Qt.Key.Key_1.value), int(Qt.Key.Key_2.value), int(Qt.Key.Key_3.value)}
    _focus(win.object_manager.tree)
    QTest.keyPress(win.object_manager.tree, Qt.Key.Key_3)
    _settle(2)
    assert int(Qt.Key.Key_3.value) in held
    QTest.keyRelease(win.object_manager.tree, Qt.Key.Key_3)
    _settle(2)
    assert int(Qt.Key.Key_3.value) not in held
    held.add(int(Qt.Key.Key_2.value))
    QApplication.sendEvent(QApplication.instance(), QEvent(QEvent.Type.ApplicationDeactivate))
    assert not held
    try:
        _select("standard")
        assert controls.hold_keys() == set()
    finally:
        _select("classic")


def test_modal_and_modifier_lookups() -> None:
    _window()
    controls = _controls()
    for pid in PROFILES:
        _select(pid)
        esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NO_MOD)
        ret = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, NO_MOD)
        ent = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)
        assert controls.modal_key(esc, "cancel") and not controls.modal_key(esc, "confirm")
        assert controls.modal_key(ret, "confirm") and controls.modal_key(ent, "confirm")
        assert not controls.modal_key(ret, "cancel")
        assert controls.modifier_held(Qt.KeyboardModifier.ShiftModifier, "snap")
        assert not controls.modifier_held(Qt.KeyboardModifier.ControlModifier, "snap")
        assert controls.modifier_held(Qt.KeyboardModifier.ControlModifier, "extrude")
        assert controls.tooltip("Undo", "edit.undo") == "Undo (Ctrl+Z)"
        assert controls.bindings("edit.undo") == [("Ctrl+Z", "global")]
        assert controls.tooltip("Nothing", "no.such.action") == "Nothing"
        assert controls.binding_text("no.such.action") == ""
    _select("classic")


def test_keypad_keys_fall_back_to_the_plain_key() -> None:
    _window()
    controls = _controls()
    pad = Qt.KeyboardModifier.KeypadModifier
    keys = (Qt.Key.Key_Enter, Qt.Key.Key_Plus, Qt.Key.Key_Minus, Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3,
            Qt.Key.Key_Delete, Qt.Key.Key_Asterisk)
    try:
        for pid in PROFILES:
            _select(pid)
            for scope in ("global", "viewport", "objects"):
                for key in keys:
                    padded = QKeyEvent(QEvent.Type.KeyPress, key, pad)
                    plain = QKeyEvent(QEvent.Type.KeyPress, key, NO_MOD)
                    hit = controls.lookup(padded, scope)
                    exact = controls.lookup(plain, scope)
                    assert hit is not None or exact is None, (pid, scope, key)
                    if hit is not None and exact is not None:
                        assert hit == exact or hit.startswith("camera."), (pid, scope, key, hit, exact)
            ent = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Enter, pad | Qt.KeyboardModifier.ShiftModifier)
            controls.lookup(ent, "viewport")
    finally:
        _select("classic")


def test_navigation_press_follows_the_profile() -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    _window()
    controls = _controls()

    def press(button, mods=NO_MOD):
        return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), button, button, mods)

    left, middle = Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton
    alt, shift = Qt.KeyboardModifier.AltModifier, Qt.KeyboardModifier.ShiftModifier
    k3 = int(Qt.Key.Key_3.value)
    try:
        _select("classic")
        assert controls.is_navigation_press(press(left, alt), set())
        assert controls.is_navigation_press(press(left), {k3})
        assert not controls.is_navigation_press(press(left), set())
        assert not controls.is_navigation_press(press(left, shift), set())
        assert controls.is_navigation_press(press(middle), set())
        _select("standard")
        assert controls.is_navigation_press(press(middle, shift), set())
        assert controls.is_navigation_press(press(left, alt), set())
        assert not controls.is_navigation_press(press(left), {k3})
    finally:
        _select("classic")


def test_modeling_filter_yields_to_navigation_and_keeps_threshold() -> None:
    win = _window()
    from quartz_studio.modeling import interaction

    assert interaction.DRAG_THRESHOLD == 3.0
    flt = win.modeling_filter
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    left = Qt.MouseButton.LeftButton
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), left, left,
                     Qt.KeyboardModifier.AltModifier)
    assert flt._blocked(ev)
    plain = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), left, left, NO_MOD)
    assert not flt._blocked(plain)
    assert _controls().cursor("drag_threshold") == 3


def test_no_shortcut_filter_left_in_the_package() -> None:
    from quartz_studio.modeling import install as mi

    for name in ("_ShortcutFilter", "_select_pen", "_key_text", "_key_of_event", "SHORTCUT_WINDOW", "PEN_CHORD"):
        assert not hasattr(mi, name), name
    win = _window()
    assert win.modeling_shortcuts is win.controls_filter


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
    try:
        _controls().reset()
    except Exception:
        pass
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
