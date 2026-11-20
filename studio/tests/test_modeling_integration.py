from __future__ import annotations

import logging
import os
import sys
import tomllib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidgetAction

from quartz_studio.app import create_app

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


def _find(menu, label):
    for act in menu.actions():
        if act.menu() is None and not act.isSeparator() and (act.property("qs_label") or act.text()) == label:
            return act
    for act in menu.actions():
        if act.menu() is not None:
            found = _find(act.menu(), label)
            if found is not None:
                return found
    return None


def _leaves(menu) -> list:
    out = []
    for act in menu.actions():
        if act.menu() is not None:
            out.extend(_leaves(act.menu()))
        elif not act.isSeparator() and not isinstance(act, QWidgetAction):
            out.append(act)
    return out


def _item_labels(entries) -> list[str]:
    out: list[str] = []
    for entry in entries:
        if isinstance(entry, tuple) and entry and entry[0] == "item":
            out.append(entry[1])
        elif isinstance(entry, tuple) and entry and entry[0] == "submenu":
            out.extend(_item_labels(entry[2]))
    return out


def _press(target, key, text: str) -> None:
    QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, key, NO_MOD, text))


def _run_select(label: str, mode: str, selection) -> object:
    win = _window()
    scene = _fresh_cube()
    scene.set_mode(mode)
    scene.clear_selection()
    scene.select_components(selection)
    act = win.menu_bar.action_at(("Select", label))
    assert act is not None, label
    act.trigger()
    _settle()
    return scene


def _run_select_command(tool_id: str, mode: str, selection) -> object:
    from quartz_studio import controls

    _window()
    scene = _fresh_cube()
    scene.set_mode(mode)
    scene.clear_selection()
    scene.select_components(selection)
    assert controls.run("tool." + tool_id), tool_id
    _settle()
    return scene


def test_select_menu_opens_the_interactive_selection_tools():
    for label, tool, mode in (("Loop Selection", "select_loop", "edges"),
                              ("Ring Selection", "select_ring", "edges"),
                              ("Fill Selection", "select_fill", "polygons")):
        scene = _run_select(label, mode, [])
        assert scene.tool == tool, (label, scene.tool)
        assert scene.mode == mode, (label, scene.mode)
    _fresh_cube().set_tool("move")


def test_select_menu_is_in_menu_bar():
    win = _window()
    titles = win.menu_bar.titles()
    assert "Select" in titles
    assert titles.index("Edit") < titles.index("Select") < titles.index("Mesh")
    assert len(_leaves(win.menu_bar.menus["Select"])) >= 12


def test_select_all_selects_every_face():
    scene = _run_select("Select All", "polygons", [0])
    assert sorted(scene.selected_polygons) == [0, 1, 2, 3, 4, 5]


def test_deselect_all_clears_selection():
    scene = _run_select("Deselect All", "polygons", [0, 1])
    assert not scene.selected_polygons


def test_invert_flips_selection():
    scene = _run_select("Invert", "polygons", [0])
    assert sorted(scene.selected_polygons) == [1, 2, 3, 4, 5]


def test_select_connected_takes_whole_cube():
    scene = _run_select("Select Connected", "polygons", [0])
    assert sorted(scene.selected_polygons) == [0, 1, 2, 3, 4, 5]


def test_grow_selection_adds_neighbour_faces():
    scene = _run_select("Grow Selection", "polygons", [0])
    assert 0 in scene.selected_polygons
    assert sorted(scene.selected_polygons) == [0, 2, 3, 4, 5]


def test_shrink_selection_keeps_interior_face():
    scene = _run_select("Shrink Selection", "polygons", [0, 1, 2, 3, 4])
    assert sorted(scene.selected_polygons) == [4]


def test_loop_selection_grows_polygon_selection():
    scene = _run_select_command("loop_selection", "polygons", [0])
    assert sorted(scene.selected_polygons) == [0, 1, 2, 3]


def test_ring_selection_takes_four_parallel_edges():
    scene = _run_select_command("ring_selection", "edges", [(0, 3)])
    assert len(scene.selected_edges) == 4
    assert (0, 3) in scene.selected_edges


def test_outline_selection_returns_face_outline_edges():
    scene = _run_select("Outline Selection", "polygons", [0])
    assert scene.mode == "edges"
    assert set(scene.selected_edges) == {(0, 1), (0, 3), (1, 2), (2, 3)}


def test_fill_selection_fills_top_face():
    scene = _run_select_command("fill_selection", "edges", [(2, 3), (6, 7), (3, 7), (2, 6)])
    assert scene.mode == "polygons"
    assert sorted(scene.selected_polygons) == [4]


def test_path_selection_connects_two_points():
    scene = _run_select("Path Selection", "points", [0, 6])
    assert scene.mode == "points"
    assert {0, 6} <= set(scene.selected_points)
    assert len(scene.selected_points) == 4


def test_convert_selection_to_points():
    scene = _run_select("Convert Selection Mode...", "polygons", [0])
    assert scene.mode == "points"
    assert set(scene.selected_points) == {0, 1, 2, 3}


def test_create_mesh_menu_adds_parametric_objects():
    win = _window()
    from quartz_studio import objects

    mesh_menu = win.menu_bar.menus["Create"].submenu("Mesh")
    assert mesh_menu is not None
    for spec in objects.by_category("mesh"):
        scene = _fresh_cube()
        before = len(scene.objects)
        act = _find(mesh_menu, spec.label)
        assert act is not None, spec.label
        act.trigger()
        _settle()
        assert len(scene.objects) == before + 1, spec.label
        assert scene.active.kind == spec.id, spec.label
        assert len(scene.active.mesh.points) > 0, spec.label


def test_fixed_primitives_are_no_longer_wired_into_the_window():
    win = _window()
    from quartz_studio.modeling import install as mi

    assert not hasattr(mi, "add_primitive")
    sphere = win.regions["object_palette"].buttons["Sphere"]
    names = [c.name for c in sphere.foldout()]
    assert len(names) == len(set(names))
    menu = sphere.build_menu()
    texts = [act.text() for act in menu.actions() if not act.isSeparator()]
    for name in ("Sphere", "Torus", "Capsule"):
        assert name in texts, name
    scene = _fresh_cube()
    before = len(scene.objects)
    _find(menu, "Torus").trigger()
    _settle()
    assert len(scene.objects) == before + 1
    assert scene.active.kind == "torus"
    assert len(scene.active.mesh.points) > 0


def test_every_tool_menu_item_shows_registry_shortcut():
    win = _window()
    from quartz_studio.modeling import get_tool, tool_ids
    from quartz_studio.modeling import install as mi
    from quartz_studio.modeling import select_tools

    select_names = {t.name for t in select_tools.TOOLS}
    for tool_id in tool_ids():
        spec = get_tool(tool_id)
        menu = win.menu_bar.menus[spec.menu]
        label = mi.LABEL_ALIASES.get(spec.name, spec.name)
        if label in select_names or spec.name in select_names:
            continue
        act = _find(menu, label) or _find(menu, spec.name)
        assert act is not None, spec.name
        assert (act.property("qs_shortcut") or None) == spec.shortcut, (spec.name, spec.shortcut)


def test_registry_chords_are_shown_on_menu_items():
    win = _window()
    expected = {
        ("Mesh", "Line Cut"): "K~K",
        ("Mesh", "Loop/Path Cut"): "K~L",
        ("Mesh", "Plane Cut"): "K~J",
        ("Mesh", "Edge Cut"): "M~F",
        ("Mesh", "Polygon Pen"): "M~E",
        ("Select", "Shrink Selection"): "U~K",
    }
    for (title, label), chord in expected.items():
        act = _find(win.menu_bar.menus[title], label)
        assert act is not None, label
        assert act.property("qs_shortcut") == chord, (label, act.property("qs_shortcut"))


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


def test_visible_modeling_items_never_log_not_implemented():
    win = _window()
    with _LogCapture("quartz_studio") as records:
        for title in ("Select", "Mesh", "Create"):
            menu = win.menu_bar.menus[title]
            menu.aboutToShow.emit()
            for action in _leaves(menu):
                if action.isEnabled():
                    scene = _fresh_cube()
                    scene.set_mode("polygons")
                    scene.select_components([0])
                    action.trigger()
                    _settle()
        _fresh_cube().set_tool("move")
    assert not [r for r in records if "not implemented" in r], records


def test_delete_key_removes_selected_face_in_polygons():
    win = _window()
    scene = _fresh_cube()
    scene.set_mode("polygons")
    scene.select_components([0])
    canvas = win.viewport.canvas
    canvas.setFocus()
    _settle()
    _press(canvas, Qt.Key.Key_Delete, "")
    _settle()
    assert len(scene.active.mesh.polygons) == 5
    assert scene.tool == "delete"


def test_delete_key_with_viewport_focus_removes_face():
    win = _window()
    scene = _fresh_cube()
    scene.set_mode("polygons")
    scene.select_components([0])
    win.viewport.setFocus()
    _settle()
    assert QApplication.focusWidget() is win.viewport
    _press(win.viewport, Qt.Key.Key_Delete, "")
    _settle()
    assert len(scene.active.mesh.polygons) == 5
    assert scene.tool == "delete"


def test_command_with_parameters_applies_defaults_and_keeps_panel():
    win = _window()
    from quartz_studio.modeling import install as mi

    scene = _fresh_cube()
    scene.set_mode("polygons")
    scene.select_components([0])
    before = len(scene.active.mesh.polygons)
    mi.activate_tool("clone")
    _settle()
    applied = len(scene.active.mesh.polygons)
    assert applied > before
    assert win.tool_options.isVisible()
    assert "clones" in win.tool_options.editors
    win.tool_options.apply_button.click()
    _settle()
    assert len(scene.active.mesh.polygons) > applied


def test_delete_key_in_model_mode_keeps_mesh():
    win = _window()
    scene = _fresh_cube()
    scene.set_mode("model")
    canvas = win.viewport.canvas
    canvas.setFocus()
    _settle()
    _press(canvas, Qt.Key.Key_Delete, "")
    _settle()
    assert len(scene.active.mesh.polygons) == 6


def test_pen_chord_m_e_activates_pen_tool():
    win = _window()
    scene = _fresh_cube()
    scene.set_tool("move")
    canvas = win.viewport.canvas
    _press(canvas, Qt.Key.Key_M, "M")
    _press(canvas, Qt.Key.Key_E, "E")
    _settle()
    assert scene.tool == "pen"


def test_prepare_twice_keeps_command_and_menu_counts():
    _window()
    from quartz_studio.modeling import install as mi
    from quartz_studio.widgets import menu_bar as mb
    from quartz_studio.widgets import menus_data as md

    def counts():
        return (len(mb.SCENE_COMMANDS), len(_item_labels(md.MESH_MENU)),
                len(_item_labels(md.SELECT_MENU)), len(_item_labels(md.CREATE_MENU)))

    before = counts()
    mi.prepare()
    mi.prepare()
    assert counts() == before


def test_set_flow_is_listed_once_in_mesh_menu():
    _window()
    from quartz_studio.widgets import menus_data as md

    assert _item_labels(md.MESH_MENU).count("Set Flow") == 1


def test_command_with_parameters_shows_options_panel():
    win = _window()
    from quartz_studio.modeling import install as mi

    scene = _fresh_cube()
    scene.set_mode("points")
    scene.select_components([0])
    mi.activate_tool("set_point_value")
    _settle()
    assert win.tool_options.isVisible()
    assert win.tool_options.spec().id == "set_point_value"
    assert {"x_value", "y_value", "z_value"} <= set(win.tool_options.editors)
    mi.activate_tool("convert_selection")
    _settle()
    assert "to" in win.tool_options.editors


def test_pyproject_packages_include_modeling():
    with open(os.path.join(STUDIO_ROOT, "pyproject.toml"), "rb") as handle:
        data = tomllib.load(handle)
    assert "quartz_studio.modeling" in data["tool"]["setuptools"]["packages"]


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
