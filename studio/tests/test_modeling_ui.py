from __future__ import annotations

import logging
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidgetAction

from quartz_studio.app import create_app

LEFT = Qt.MouseButton.LeftButton
NO_MOD = Qt.KeyboardModifier.NoModifier

_STATE: dict = {}


def _window():
    if "window" in _STATE:
        return _STATE["window"]
    app = create_app([sys.argv[0]])
    from quartz_studio.modeling import install as mi
    from quartz_studio.main_window import MainWindow

    mi.prepare()
    win = MainWindow()
    mi.install(win)
    win.resize(1500, 900)
    win.show()
    for _ in range(6):
        app.processEvents()
    _STATE["window"] = win
    _STATE["app"] = app
    return win


def _settle():
    app = _STATE["app"]
    for _ in range(4):
        app.processEvents()


def _fresh_cube():
    from quartz_studio.scene import Mesh, get_scene

    scene = get_scene()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_object("Cube", Mesh.cube(200.0))
    scene._undo.clear()
    scene._redo.clear()
    return scene


def _send(canvas, kind, pos, buttons=LEFT):
    p = QPointF(*pos)
    ev = QMouseEvent(kind, p, canvas.mapToGlobal(p), LEFT if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton,
                     buttons, NO_MOD)
    QApplication.sendEvent(canvas, ev)


def test_mesh_menu_lists_modeling_tools():
    win = _window()
    from quartz_studio.modeling import get_tool, tool_ids

    labels = set()

    def walk(menu):
        for act in menu.actions():
            if act.menu() is not None:
                walk(act.menu())
            elif not act.isSeparator():
                labels.add(act.property("qs_label") or act.text())

    for title in ("Mesh", "Select"):
        menu = win.menu_bar.menus.get(title)
        assert menu is not None, title
        walk(menu)
    texts = {t.split("\t")[0] for t in labels}
    from quartz_studio.modeling.install import LABEL_ALIASES

    for tool_id in tool_ids():
        name = get_tool(tool_id).name
        assert name in texts or LABEL_ALIASES.get(name) in texts, name


def test_activating_extrude_shows_panel():
    win = _window()
    scene = _fresh_cube()
    from quartz_studio.modeling import install as mi

    mi.activate_tool("extrude")
    _settle()
    assert scene.tool == "extrude"
    assert scene.mode == "polygons"
    assert win.tool_options.isVisible()
    assert "offset" in win.tool_options.editors


def test_tool_options_panel_sits_between_the_managers():
    win = _window()
    splitter = win.manager_splitter
    order = [splitter.widget(i) for i in range(splitter.count())]
    assert order == [win.object_manager, win.tool_options, win.selection_options, win.attribute_manager,
                     win.coordinates]
    _fresh_cube()
    from quartz_studio.modeling import install as mi

    mi.activate_tool("extrude")
    _settle()
    win.apply_default_sizes()
    _settle()
    assert win.tool_options.isVisible()
    assert win.tool_options.height() > 0
    assert win.attribute_manager.height() >= 0.25 * splitter.height()
    assert order.index(win.coordinates) == len(order) - 1
    _fresh_cube().set_tool("move")
    _settle()


def test_drag_in_viewport_extrudes_selected_face():
    win = _window()
    scene = _fresh_cube()
    from quartz_studio.modeling import install as mi

    mi.activate_tool("extrude")
    normals = scene.active.mesh.polygon_normals()
    top = int(np.argmax(normals[:, 1]))
    scene.select_components([top])
    canvas = win.viewport.canvas
    _settle()
    c = canvas.rect().center()
    x, y = float(c.x()), float(c.y())
    _send(canvas, QEvent.Type.MouseButtonPress, (x, y))
    for k in range(1, 8):
        _send(canvas, QEvent.Type.MouseMove, (x + 10 * k, y))
    _send(canvas, QEvent.Type.MouseButtonRelease, (x + 70, y), Qt.MouseButton.NoButton)
    _settle()
    mesh = scene.active.mesh
    assert len(mesh.polygons) == 10
    ys = mesh.points[list(mesh.polygons[top])][:, 1]
    assert np.all(ys > 100.0)
    offset = mi.controller().params()["offset"]
    assert offset > 0


def test_panel_edit_updates_live_and_undo_restores():
    win = _window()
    scene = _fresh_cube()
    from quartz_studio.modeling import install as mi

    mi.activate_tool("extrude")
    normals = scene.active.mesh.polygon_normals()
    top = int(np.argmax(normals[:, 1]))
    scene.select_components([top])
    ctl = mi.controller()
    ctl.new_transform()
    win.tool_options._on_apply()
    _settle()
    ctl.set_param("offset", 40.0)
    ys = scene.active.mesh.points[list(scene.active.mesh.polygons[top])][:, 1]
    assert np.allclose(ys, 140.0)
    ctl.set_param("offset", 10.0)
    ys = scene.active.mesh.points[list(scene.active.mesh.polygons[top])][:, 1]
    assert np.allclose(ys, 110.0)
    assert len(scene.active.mesh.polygons) == 10
    ctl.new_transform()
    scene.undo()
    assert len(scene.active.mesh.polygons) == 6


def test_click_without_drag_still_selects():
    win = _window()
    scene = _fresh_cube()
    from quartz_studio.modeling import install as mi

    mi.activate_tool("extrude")
    scene.clear_selection()
    canvas = win.viewport.canvas
    _settle()
    c = canvas.rect().center()
    _send(canvas, QEvent.Type.MouseButtonPress, (float(c.x()), float(c.y())))
    _send(canvas, QEvent.Type.MouseButtonRelease, (float(c.x()), float(c.y())), Qt.MouseButton.NoButton)
    _settle()
    assert len(scene.active.mesh.polygons) == 6
    assert scene.selected_polygons


def test_switching_to_move_deactivates_tool():
    win = _window()
    scene = _fresh_cube()
    from quartz_studio.modeling import install as mi

    mi.activate_tool("extrude")
    scene.set_tool("move")
    _settle()
    assert mi.controller().tool_id is None
    assert not win.tool_options.isVisible()


def test_every_tool_activates_without_error():
    win = _window()
    from quartz_studio.modeling import install as mi
    from quartz_studio.modeling import tool_ids

    for tool_id in tool_ids():
        scene = _fresh_cube()
        scene.set_mode("polygons")
        scene.select_components([0])
        mi.activate_tool(tool_id)
        _settle()
        assert win.tool_options.spec().id == tool_id
        scene.set_tool("move")


class _LogCapture(logging.Handler):

    def __init__(self, name: str) -> None:
        super().__init__(logging.DEBUG)
        self._logger = logging.getLogger(name)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())

    def __enter__(self) -> list[str]:
        self._old_level = self._logger.level
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self)
        return self.records

    def __exit__(self, *exc) -> None:
        self._logger.removeHandler(self)
        self._logger.setLevel(self._old_level)


def _leaf_actions(menu) -> list:
    out = []
    stack = [menu]
    while stack:
        for action in stack.pop().actions():
            if action.menu() is not None:
                stack.append(action.menu())
            elif not action.isSeparator():
                out.append(action)
    return out


def test_app_path_controls_are_all_wired():
    win = _window()
    from quartz_studio.modeling import install as mi

    with _LogCapture("quartz_studio") as records:
        for menu in win.menu_bar.menus.values():
            menu.aboutToShow.emit()
            for action in _leaf_actions(menu):
                if isinstance(action, QWidgetAction):
                    continue
                assert (menu.is_wired(action.property("qs_label"))
                        or action.parent() is not menu), action.property("qs_label")
                if action.isEnabled():
                    scene = _fresh_cube()
                    scene.set_mode("polygons")
                    scene.select_components([0])
                    action.trigger()
                    _settle()
        panel = win.tool_options
        for tool_id in ("extrude",):
            scene = _fresh_cube()
            mi.activate_tool(tool_id)
            scene.select_components([0])
            for button in (panel.apply_button, panel.new_button, panel.reset_button):
                if button.isVisible() and button.isEnabled():
                    button.click()
                    _settle()
        _fresh_cube().set_tool("move")
    assert not [r for r in records if "not implemented" in r], records


def test_palette_runs_the_same_function_as_the_menu():
    win = _window()
    from quartz_studio.modeling import install as mi
    from quartz_studio.widgets import menu_bar as mb

    paths = {h.args[0]: path for path, h in mb.SCENE_COMMANDS
             if getattr(h, "func", None) is mi.activate_tool}
    palette = win.tool_palette
    button = palette.buttons["Extrude"]
    states = []
    for source in ("palette", "menu"):
        scene = _fresh_cube()
        scene.set_mode("polygons")
        scene.select_components([0])
        scene.set_tool("move")
        _settle()
        if source == "palette":
            menu = button.build_menu()
            next(a for a in menu.actions() if a.text() == "Extrude").trigger()
        else:
            win.menu_bar.action_at(paths["extrude"]).trigger()
        _settle()
        states.append((scene.tool, scene.mode, mi.controller().tool_id, win.tool_options.isVisible(),
                       win.tool_options.spec().id))
    assert states[0] == states[1] == ("extrude", "polygons", "extrude", True, "extrude"), states
    assert button.isChecked() and palette.active_tool() == "Extrude"
    _fresh_cube().set_tool("move")
    _settle()
    assert not button.isChecked() and not win.tool_options.isVisible()


def test_prepare_is_idempotent():
    _window()
    from quartz_studio.modeling import install as mi
    from quartz_studio.widgets import menu_bar as mb

    before = len(mb.SCENE_COMMANDS)
    mi.prepare()
    mi.prepare()
    assert len(mb.SCENE_COMMANDS) == before


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
