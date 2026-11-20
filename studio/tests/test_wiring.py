from __future__ import annotations

import logging
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import quartz_studio
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QHBoxLayout, QWidget

from quartz_studio.app import create_app

NOT_IMPLEMENTED = "not implemented"
LIVE_SELECTION = "Selection"

_APP: QApplication | None = None
_HOSTS: list[QWidget] = []

MODELING_GROUPS = ["Extrude", "Bevel", "Cut", "Bridge", "Dissolve", "Slide", "Normals", "Subdivide", "Clone"]

PALETTE_BUTTONS = ["Line", "Null", "Rectangle", "Circle", "Cube", "Sphere", "Text",
                   "Subdivision Surface", "Extrude", "Voronoi Fracture"]


class _LogCapture(logging.Handler):

    def __init__(self, name: str = "quartz_studio") -> None:
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


def _app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = create_app([sys.argv[0]])
    return _APP


def _settle(passes: int = 3) -> None:
    for _ in range(passes):
        _app().processEvents()


def _build(mode: str | None = None, tool: str | None = None):
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.command_bar import CommandBar
    from quartz_studio.widgets.tool_palette import ToolPalette

    _app()
    while _HOSTS:
        old = _HOSTS.pop()
        old.close()
        old.deleteLater()
    _settle()
    scene = reset_scene()
    if mode:
        scene.set_mode(mode)
    if tool:
        scene.set_tool(tool)
    host = QWidget()
    lay = QHBoxLayout(host)
    tools = ToolPalette(host)
    bar = CommandBar(host)
    lay.addWidget(tools)
    lay.addWidget(bar, 1)
    host.resize(1500, 900)
    host.show()
    _settle()
    _HOSTS.append(host)
    return scene, bar, tools


def _click(btn: QAbstractButton) -> None:
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     btn.rect().center())
    _settle(2)


def _checked(buttons) -> list[QAbstractButton]:
    return [b for b in buttons if b.isChecked()]


def _tool_buttons(tools) -> list[QAbstractButton]:
    from quartz_studio.widgets.tool_palette import TOOLS

    return list(tools.button_groups[TOOLS].buttons())



def test_initial_state_matches_scene() -> None:
    scene, bar, tools = _build()
    assert scene.mode == "model" and bar.active_mode() == "model"
    assert _checked(bar.mode_buttons()) == [bar.button("Model")]
    assert scene.tool == "move" and tools.scene_tool() == "move"
    assert tools.active_tool() == "Move"
    assert _checked(_tool_buttons(tools)) == [tools.button("Move")]


def test_widgets_built_later_follow_the_scene() -> None:
    scene, bar, tools = _build(mode="polygons", tool="select")
    assert _checked(bar.mode_buttons()) == [bar.button("Polygons")]
    assert _checked(_tool_buttons(tools)) == [tools.button(LIVE_SELECTION)]
    assert (scene.mode, scene.tool) == ("polygons", "select")


def test_mode_buttons_set_scene_mode() -> None:
    from quartz_studio.widgets.command_bar import MODE_BUTTONS

    scene, bar, _ = _build()
    emitted: list[str] = []
    scene.modeChanged.connect(emitted.append)
    for key, mode in MODE_BUTTONS.items():
        _click(bar.button(key))
        assert scene.mode == mode, (key, scene.mode)
        assert _checked(bar.mode_buttons()) == [bar.button(key)]
        assert bar.active_mode() == mode
    assert emitted == ["points", "edges", "polygons", "model"], emitted


def test_scene_mode_checks_button() -> None:
    scene, bar, _ = _build()
    emitted: list[str] = []
    scene.modeChanged.connect(emitted.append)
    for mode, key in (("edges", "Edges"), ("points", "Points"),
                      ("polygons", "Polygons"), ("model", "Model")):
        scene.set_mode(mode)
        _settle(1)
        assert _checked(bar.mode_buttons()) == [bar.button(key)], mode
        assert scene.mode == mode
    assert emitted == ["edges", "points", "polygons", "model"], emitted


def test_tool_buttons_set_scene_tool() -> None:
    scene, _, tools = _build()
    emitted: list[str] = []
    scene.toolChanged.connect(emitted.append)
    for key, tool in ((LIVE_SELECTION, "select"), ("Move", "move")):
        _click(tools.button(key))
        assert scene.tool == tool, (key, scene.tool)
        assert _checked(_tool_buttons(tools)) == [tools.button(key)]
        assert tools.scene_tool() == tool
    assert emitted == ["select", "move"], emitted


def test_scene_tool_checks_button() -> None:
    scene, _, tools = _build()
    for tool, key in (("select", LIVE_SELECTION), ("move", "Move")):
        scene.set_tool(tool)
        _settle(1)
        assert _checked(_tool_buttons(tools)) == [tools.button(key)], tool
        assert scene.tool == tool
    scene.set_tool("other")
    _settle(1)
    assert _checked(_tool_buttons(tools)) == []
    assert scene.tool == "other"
    _click(tools.button("Move"))
    assert scene.tool == "move"
    assert _checked(_tool_buttons(tools)) == [tools.button("Move")]


def test_tool_palette_has_only_wired_tools() -> None:
    from quartz_studio.widgets.tool_palette import PEN_KEY

    _scene, _, tools = _build()
    assert tools.command_names() == [LIVE_SELECTION, "Move", "Rotate", "Scale", PEN_KEY, *MODELING_GROUPS]
    transform = [tools.button(k) for k in (LIVE_SELECTION, "Move", "Rotate", "Scale", PEN_KEY)]
    assert all(b.wired for b in transform)
    assert all(b.is_wired() for b in _tool_buttons(tools))
    pen_menu = tools.button(PEN_KEY).build_menu()
    assert [a.text() for a in pen_menu.actions()] == ["Polygon Pen", "Pen"]
    pen_menu.deleteLater()
    assert not tools.button("Move").build_menu().actions()
    with _LogCapture() as records:
        for button in transform:
            _click(button)
    assert not [r for r in records if NOT_IMPLEMENTED in r], records


def test_modeling_group_buttons_follow_the_scene_tool() -> None:
    from quartz_studio.modeling.install import palette_groups

    palette_groups()
    scene, _, tools = _build()
    extrude = tools.button("Extrude")
    assert not extrude.isChecked() and extrude.command_text() == "Extrude"
    scene.set_tool("inset")
    _settle(1)
    assert _checked(_tool_buttons(tools)) == [extrude]
    assert extrude.command_text() == "Inset" and extrude.icon_name() == "mt_inset"
    scene.set_tool("bevel")
    _settle(1)
    assert _checked(_tool_buttons(tools)) == [tools.button("Bevel")]
    scene.set_tool("subdivide")
    _settle(1)
    assert _checked(_tool_buttons(tools)) == []
    assert tools.button("Subdivide").command_text() == "Subdivide"
    _click(tools.button("Move"))
    assert scene.tool == "move" and _checked(_tool_buttons(tools)) == [tools.button("Move")]
    scene, _, tools = _build(tool="bevel")
    assert _checked(_tool_buttons(tools)) == [tools.button("Bevel")]


def _foldout_action(button, text: str):
    menu = button.build_menu()
    stack = [menu]
    while stack:
        m = stack.pop(0)
        for a in m.actions():
            if a.menu() is not None:
                stack.append(a.menu())
            elif a.text() == text:
                return menu, a
    raise AssertionError(f"{text!r} not in the fold-out of {button.command_text()!r}")


def _pick(button, text: str) -> list[str]:
    menu, action = _foldout_action(button, text)
    with _LogCapture() as records:
        action.trigger()
        _settle(1)
    menu.deleteLater()
    return records


def test_pen_button_is_the_line_pen() -> None:
    from quartz_studio.widgets.tool_palette import PEN_COMMANDS, PEN_KEY

    assert PEN_COMMANDS == {"Polygon Pen": "pen", "Pen": "line_pen"}
    scene, bar, tools = _build()
    pen = tools.button(PEN_KEY)
    assert pen.command_text() == "Pen" and pen.wired
    with _LogCapture() as records:
        _click(pen)
    assert pen.isChecked() and scene.tool == "line_pen" and tools.scene_tool() == "line_pen"
    assert scene.mode == "points" and bar.button("Points").isChecked()
    assert not [r for r in records if NOT_IMPLEMENTED in r], records


def test_pen_foldout_pick_selects_pen_tools() -> None:
    scene, _, tools = _build()
    pen = tools.button("Pen")
    emitted: list[str] = []
    scene.toolChanged.connect(emitted.append)
    records = _pick(pen, "Polygon Pen")
    assert pen.command_text() == "Polygon Pen"
    assert pen.isChecked() and scene.tool == "pen" and tools.scene_tool() == "pen"
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    records = _pick(pen, "Pen")
    assert pen.command_text() == "Pen" and scene.tool == "line_pen"
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    with _LogCapture() as records:
        _click(tools.button("Move"))
        _click(pen)
    assert scene.tool == "line_pen"
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    records = _pick(pen, "Polygon Pen")
    assert scene.tool == "pen"
    assert emitted == ["pen", "line_pen", "move", "line_pen", "pen"], emitted


def test_scene_pen_tool_syncs_foldout() -> None:
    scene, _, tools = _build()
    pen = tools.button("Pen")
    emitted: list[str] = []
    scene.toolChanged.connect(emitted.append)
    scene.set_tool("pen")
    _settle(1)
    assert _checked(_tool_buttons(tools)) == [pen]
    assert pen.command_text() == "Polygon Pen" and pen.icon_name() == "polygon_pen"
    scene.set_tool("line_pen")
    _settle(1)
    assert _checked(_tool_buttons(tools)) == [pen]
    assert pen.command_text() == "Pen" and pen.icon_name() == "pal_pen"
    scene.set_tool("move")
    assert _checked(_tool_buttons(tools)) == [tools.button("Move")]
    assert pen.command_text() == "Pen"
    assert emitted == ["pen", "line_pen", "move"], emitted
    scene, _, tools = _build(tool="pen")
    pen = tools.button("Pen")
    assert pen.isChecked() and pen.command_text() == "Polygon Pen"
    assert scene.tool == "pen" and scene.mode == "points"


def test_wired_buttons_do_not_log() -> None:
    from quartz_studio.widgets.command_bar import MODE_BUTTONS
    from quartz_studio.widgets.tool_palette import SCENE_TOOLS

    scene, bar, tools = _build()
    wired = [bar.button(k) for k in MODE_BUTTONS] + [tools.button(k) for k in SCENE_TOOLS]
    assert all(getattr(b, "wired", False) for b in wired)
    with _LogCapture() as records:
        for btn in wired:
            _click(btn)
        scene.set_mode("points")
        scene.set_tool("select")
        _settle(1)
    assert not [r for r in records if NOT_IMPLEMENTED in r], records


def test_live_selection_selects() -> None:
    scene, _, tools = _build()
    live = tools.button(LIVE_SELECTION)
    assert [a.text() for a in live.build_menu().actions()] == ["Brush Selection", "Loop Selection",
        "Ring Selection", "Pattern Selection", "Fill Selection", "Phong Angle Selection"]
    with _LogCapture() as records:
        _click(live)
    assert live.isChecked() and scene.tool == "select"
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    scene.set_tool("move")
    assert not live.isChecked()
    _click(live)
    assert scene.tool == "select" and live.isChecked()


def test_command_bar_undo_redo_buttons() -> None:
    from quartz_studio.scene import Mesh

    scene, bar, _ = _build()
    undo, redo = bar.history_buttons()
    assert (undo.command_text(), redo.command_text()) == ("Undo", "Redo")
    assert not undo.isEnabled() and not redo.isEnabled()
    scene.add_object("Cube", Mesh.cube(200.0))
    _settle(1)
    assert undo.isEnabled() and not redo.isEnabled()
    with _LogCapture() as records:
        _click(undo)
    assert [o.name for o in scene.objects] == ["Cube"]
    assert not undo.isEnabled() and redo.isEnabled()
    with _LogCapture() as more:
        _click(redo)
    assert [o.name for o in scene.objects] == ["Cube", "Cube.1"]
    assert undo.isEnabled() and not redo.isEnabled()
    assert not [r for r in records + more if NOT_IMPLEMENTED in r], records + more
    assert scene.mode == "model" and bar.button("Model").isChecked()


def test_buttons_show_press_state() -> None:
    _, bar, tools = _build()
    for btn in (bar.button("Points"), bar.button("Edges"),
                tools.button(LIVE_SELECTION), tools.button("Pen")):
        centre = btn.rect().center()
        QTest.mousePress(btn, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
        assert btn.isDown(), btn.command_text()
        QTest.mouseRelease(btn, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
        _settle(1)
        assert not btn.isDown(), btn.command_text()


def test_two_strips_share_the_scene() -> None:
    from quartz_studio.widgets.command_bar import CommandBar
    from quartz_studio.widgets.tool_palette import ToolPalette

    scene, bar, tools = _build()
    host = _HOSTS[-1]
    bar2, tools2 = CommandBar(host), ToolPalette(host)
    host.layout().addWidget(tools2)
    host.layout().addWidget(bar2, 1)
    _settle()
    _click(bar.button("Edges"))
    assert scene.mode == "edges" and bar2.button("Edges").isChecked()
    _click(tools2.button(LIVE_SELECTION))
    assert scene.tool == "select" and tools.button(LIVE_SELECTION).isChecked()
    assert _checked(_tool_buttons(tools)) == [tools.button(LIVE_SELECTION)]


def test_main_window_bars_are_wired() -> None:
    from quartz_studio.main_window import MainWindow
    from quartz_studio.scene import get_scene, reset_scene
    from quartz_studio.widgets.command_bar import CommandBar
    from quartz_studio.widgets.tool_palette import ToolPalette

    _app()
    reset_scene()
    win = MainWindow()
    try:
        win.resize(1600, 900)
        win.show()
        _settle()
        bar, tools = win.regions["command_bar"], win.regions["tool_palette"]
        assert isinstance(bar, CommandBar) and isinstance(tools, ToolPalette)
        scene = get_scene()
        _click(tools.button(LIVE_SELECTION))
        assert scene.tool == "select"
        _click(bar.button("Points"))
        assert scene.mode == "points"
        scene.set_mode("model")
        scene.set_tool("move")
        assert bar.button("Model").isChecked() and tools.button("Move").isChecked()
    finally:
        win.close()
        win.deleteLater()
        _settle()


def _menu_bar(functional_only: bool = True):
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.menu_bar import MenuBar

    _app()
    scene = reset_scene()
    host = QWidget()
    lay = QHBoxLayout(host)
    bar = MenuBar(host, functional_only=functional_only)
    lay.addWidget(bar)
    host.resize(1400, 60)
    host.show()
    _settle()
    _HOSTS.append(host)
    return scene, bar


def _trigger(bar, *path: str) -> list[str]:
    act = bar.action_at(path)
    assert act is not None, path
    assert act.isEnabled(), path
    with _LogCapture() as records:
        act.trigger()
        _settle(1)
    return records


def test_menu_creates_objects() -> None:
    scene, bar = _menu_bar()
    assert [o.name for o in scene.objects] == ["Cube"]
    records = _trigger(bar, "Create", "Mesh", "Cube")
    assert [o.name for o in scene.objects] == ["Cube", "Cube.1"]
    cube = scene.objects[-1]
    assert scene.active is cube and len(cube.mesh.points) == 8 and len(cube.mesh.polygons) == 6
    assert float(cube.size()[0]) == 200.0
    records += _trigger(bar, "Create", "Mesh", "Empty Polygon")
    poly = scene.objects[-1]
    assert poly.name == "Polygon" and scene.active is poly and not len(poly.mesh.points)
    assert scene.tool == "move"
    records += _trigger(bar, "Create", "Spline", "Line")
    line = scene.objects[-1]
    assert line.name == "Line" and scene.active is line and not line.mesh.has_faces()
    assert scene.tool == "line_pen" and scene.mode == "points"
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    spline = bar.menu_at(("Create", "Spline", "Line"))
    assert "Line" in spline.entries_text()
    from quartz_studio import icons

    assert icons.has("m_line")


def test_menu_polygon_pen_sets_tool() -> None:
    scene, bar = _menu_bar()
    records = _trigger(bar, "Mesh", "Polygon Pen")
    assert scene.tool == "pen" and scene.mode == "points"
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    from quartz_studio.widgets.tool_palette import ToolPalette

    tools = ToolPalette(_HOSTS[-1])
    assert tools.button("Pen").isChecked()
    assert tools.button("Pen").command_text() == "Polygon Pen"


def test_menu_undo_redo() -> None:
    scene, bar = _menu_bar()
    undo = bar.action_at(("Edit", "Undo"))
    redo = bar.action_at(("Edit", "Redo"))
    assert undo.property("qs_shortcut") == "Ctrl+Z" and redo.property("qs_shortcut") == "Ctrl+Y"
    edit = bar.menus["Edit"]
    edit.aboutToShow.emit()
    assert not undo.isEnabled() and not redo.isEnabled()
    _trigger(bar, "Create", "Mesh", "Cube")
    _trigger(bar, "Create", "Mesh", "Empty Polygon")
    assert len(scene.objects) == 3
    edit.aboutToShow.emit()
    assert undo.isEnabled() and not redo.isEnabled()
    records = _trigger(bar, "Edit", "Undo")
    assert [o.name for o in scene.objects] == ["Cube", "Cube.1"]
    edit.aboutToShow.emit()
    assert undo.isEnabled() and redo.isEnabled()
    records += _trigger(bar, "Edit", "Undo")
    assert [o.name for o in scene.objects] == ["Cube"]
    records += _trigger(bar, "Edit", "Redo")
    records += _trigger(bar, "Edit", "Redo")
    assert [o.name for o in scene.objects] == ["Cube", "Cube.1", "Polygon"]
    edit.aboutToShow.emit()
    assert undo.isEnabled() and not redo.isEnabled()
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    from quartz_studio.scene import reset_scene

    reset_scene()
    edit.aboutToShow.emit()
    assert not undo.isEnabled()


FILE_MENU_TEXT = ["New Project", "Open Project...", "Open Recent", "Merge Project...", "---",
                  "Save Project", "Save Project As...", "Save Incremental", "---", "Import...",
                  "Export", "---", "Exit"]

UNWIRED_MENU_PATHS = (("Create", "Generator", "Spline Mask"),
                      ("Create", "Generator", "Vectorizer"), ("Mesh", "Extrude"),
                      ("Spline", "Spline Pen"), ("File", "Close Project"))


def test_unwired_menu_items_are_hidden() -> None:
    from quartz_studio.widgets.menu_bar import SCENE_COMMANDS

    scene, bar = _menu_bar()
    wired = {path for path, _fn in SCENE_COMMANDS}
    for path in wired:
        assert bar.menu_at(path).is_wired(path[-1]), path
    assert bar.titles() == ["File", "Edit", "Create", "Mesh"]
    assert bar.menus["File"].entries_text() == FILE_MENU_TEXT
    assert bar.menus["Edit"].entries_text() == ["Undo", "Redo", "---", "Controls..."]
    from quartz_studio import objects

    create = bar.menus["Create"].entries_text()
    assert create == ["Null", "PRIMITIVES", "Spline", "Mesh", "OPERATORS", "Generator"], create
    for category, title in (("spline", "Spline"), ("mesh", "Mesh"), ("generator", "Generator")):
        shown = {t for t in bar.menu_at(("Create", title, "x")).entries_text() if t != "---"}
        wanted = {spec.label for spec in objects.by_category(category)}
        wanted |= {"Line"} if category == "spline" else {"Empty Polygon"} if category == "mesh" else set()
        assert shown == wanted, (title, shown ^ wanted)
    assert bar.menus["Mesh"].entries_text() == [
        "CONVERSION", "Make Editable", "CREATION TOOLS", "Polygon Pen"]
    for path in UNWIRED_MENU_PATHS:
        assert path not in wired
        assert bar.action_at(path) is None, path
    assert [o.name for o in scene.objects] == ["Cube"] and scene.tool == "move"


def test_file_menu_wiring_and_shortcuts() -> None:
    from PySide6.QtGui import QKeySequence

    from quartz_studio import fileio, project
    from quartz_studio.main_window import MainWindow
    from quartz_studio.widgets import menus_data
    from quartz_studio.widgets.menu_bar import SCENE_COMMANDS

    scene, bar = _menu_bar()
    export = bar.menu_at(("File", "Export", "x")).entries_text()
    labels = [menus_data.export_label(f) for f in fileio.exporters()]
    assert export == labels + ["---", "Export Selection..."], export
    assert {"FBX...", "glTF...", "glTF Binary...", "Wavefront OBJ...", "Stanford PLY...",
            "Quartz Project...", "STL..."} <= set(labels)
    wired = {path for path, _fn in SCENE_COMMANDS}
    for label in labels:
        assert ("File", "Export", label) in wired
    assert bar.menu_at(("File", "Open Recent", "x")).entries_text() == ["Clear Recent File List"]
    shown = {}
    for act in bar.menus["File"].actions():
        if act.property("qs_kind") == "item" and act.property("qs_shortcut"):
            shown[act.property("qs_label")] = act.property("qs_shortcut")
    assert shown == {"New Project": "Ctrl+N", "Open Project...": "Ctrl+O",
                     "Merge Project...": "Ctrl+Shift+O", "Save Project": "Ctrl+S",
                     "Save Project As...": "Ctrl+Shift+S", "Save Incremental": "Ctrl+Alt+S",
                     "Exit": "Alt+F4"}, shown
    win = MainWindow()
    try:
        keys = {sc.key().toString(QKeySequence.SequenceFormat.PortableText)
                for sc in win.file_shortcuts}
        wanted = {v for k, v in shown.items() if k != "Exit"}
        assert keys == wanted, (keys, wanted)
        assert win.windowTitle() == project.window_title()
    finally:
        win.close()
        win.deleteLater()
        _settle()


def test_pruning_keeps_section_headers_that_still_have_items() -> None:
    from quartz_studio.widgets.menu_bar import StudioMenu

    _app()
    entries = [("section", "ALPHA"), "A1", "A2", ("sep",), ("section", "BETA"), "B1",
               ("sep",), ("section", "GAMMA"), "C1"]
    menu = StudioMenu("Sections", None, entries)
    menu.bind("A1", lambda: None)
    menu.bind("C1", lambda: None)
    assert menu.prune_unwired()
    assert menu.entries_text() == ["ALPHA", "A1", "---", "GAMMA", "C1"]
    single = StudioMenu("Single", None, entries)
    single.bind("B1", lambda: None)
    assert single.prune_unwired()
    assert single.entries_text() == ["B1"]
    empty = StudioMenu("Empty", None, entries)
    assert not empty.prune_unwired()


def test_full_menu_tree_stays_available() -> None:
    scene, bar = _menu_bar(functional_only=False)
    assert bar.titles()[:3] == ["File", "Edit", "Create"] and len(bar.titles()) == 19
    for path in UNWIRED_MENU_PATHS[:5]:
        records = _trigger(bar, *path)
        assert f"{NOT_IMPLEMENTED}: {path[-1]}" in records, (path, records)
    assert [o.name for o in scene.objects] == ["Cube"] and scene.tool == "move"


def _object_palette():
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.object_palette import ObjectPalette

    _app()
    scene = reset_scene()
    host = QWidget()
    lay = QHBoxLayout(host)
    palette = ObjectPalette(host)
    lay.addWidget(palette)
    host.resize(900, 80)
    host.show()
    _settle()
    _HOSTS.append(host)
    return scene, palette


def test_object_palette_cube_adds_object() -> None:
    scene, palette = _object_palette()
    cube_btn = palette.button("Cube")
    with _LogCapture() as records:
        _click(cube_btn)
    assert [o.name for o in scene.objects] == ["Cube", "Cube.1"]
    assert scene.active is scene.objects[-1] and len(scene.active.mesh.polygons) == 6
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    assert scene.undo() and [o.name for o in scene.objects] == ["Cube"]
    records = _pick(cube_btn, "Empty Polygon")
    assert cube_btn.command_text() == "Empty Polygon"
    assert [o.name for o in scene.objects] == ["Cube", "Polygon"]
    _click(cube_btn)
    assert [o.name for o in scene.objects] == ["Cube", "Polygon", "Polygon.1"]
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    menu = cube_btn.build_menu()
    assert [a.text() for a in menu.actions()] == [
        "Cube", "Empty Polygon", "Plane", "Bezier", "Landscape", "Pyramid"]
    menu.deleteLater()
    assert palette.command_names() == PALETTE_BUTTONS
    records = _pick(cube_btn, "Cube")
    assert scene.objects[-1].name == "Cube.1" and cube_btn.command_text() == "Cube"
    assert not [r for r in records if NOT_IMPLEMENTED in r], records


def test_object_palette_line_adds_line_object() -> None:
    scene, palette = _object_palette()
    line_btn = palette.button("Line")
    assert line_btn.command_text() == "Line" and not line_btn.build_menu().actions()
    with _LogCapture() as records:
        _click(line_btn)
    line = scene.objects[-1]
    assert line.name == "Line" and scene.active is line and not line.mesh.has_faces()
    assert scene.tool == "line_pen"
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    _click(line_btn)
    assert [o.name for o in scene.objects] == ["Cube", "Line", "Line.1"]


def test_object_palette_orientations_share_entries() -> None:
    from quartz_studio.widgets.object_palette import ObjectPalette

    scene, dock = _object_palette()
    assert dock.floating and dock.popup_side == "above"
    assert dock.height() == dock.sizeHint().height() and dock.width() >= dock.natural_width()
    strip = ObjectPalette(_HOSTS[-1], orientation=Qt.Orientation.Vertical)
    strip.resize(strip.sizeHint())
    strip.show()
    _settle()
    assert not strip.floating and strip.popup_side == "left"
    assert strip.command_names() == dock.command_names() == PALETTE_BUTTONS
    assert all(b.popup_side() == "left" for b in strip.buttons.values())
    with _LogCapture() as records:
        _click(strip.button("Cube"))
    assert [o.name for o in scene.objects] == ["Cube", "Cube.1"]
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    strip.deleteLater()


def test_main_window_menus_and_palette_are_wired() -> None:
    from quartz_studio.main_window import MainWindow
    from quartz_studio.scene import get_scene, reset_scene

    _app()
    reset_scene()
    win = MainWindow()
    try:
        win.resize(1600, 900)
        win.show()
        _settle()
        scene = get_scene()
        menu_bar, tools = win.regions["menu_bar"], win.regions["tool_palette"]
        menu_bar.action_at(("Create", "Spline", "Line")).trigger()
        _settle(1)
        assert scene.active.name == "Line" and scene.tool == "line_pen"
        pen = tools.button("Pen")
        assert pen.isChecked() and pen.command_text() == "Pen"
        menu_bar.action_at(("Mesh", "Polygon Pen")).trigger()
        _settle(1)
        assert scene.tool == "pen" and pen.command_text() == "Polygon Pen"
        _click(win.regions["object_palette"].button("Cube"))
        assert [o.name for o in scene.objects] == ["Cube", "Line", "Cube.1"]
        menu_bar.menus["Edit"].aboutToShow.emit()
        menu_bar.action_at(("Edit", "Undo")).trigger()
        _settle(1)
        assert [o.name for o in scene.objects] == ["Cube", "Line"]
    finally:
        win.close()
        win.deleteLater()
        _settle()


def _title_row():
    from quartz_studio.widgets.title_row import TitleRow

    _app()
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    row = TitleRow(host)
    lay.addWidget(row)
    host.resize(1400, row.height())
    host.show()
    _settle()
    _HOSTS.append(host)
    return row


def _brightness(widget: QWidget) -> float:
    img = widget.grab().toImage()
    total = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
    return total / (3 * img.width() * img.height())


def test_layout_tab_dims_while_pressed() -> None:
    row = _title_row()
    for name in (row.active_layout(), next(n for n in row.layout_names()
                                           if n != row.active_layout())):
        tab = row.layout_tabs[name]
        tab.setProperty("qsPressFeedback", False)
        idle_color, idle = tab.text_color(), _brightness(tab)
        QTest.mousePress(tab, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         tab.rect().center())
        _settle(2)
        assert tab.isDown()
        assert tab.text_color().lightness() < idle_color.lightness()
        assert _brightness(tab) < idle - 0.05, f"{name!r} shows no pressed state"
        QTest.mouseRelease(tab, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                           tab.rect().center())
        _settle(2)
        assert not tab.isDown()
        assert row.active_layout() == name


def test_document_tab_hover_and_press() -> None:
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    from quartz_studio.widgets.title_row import COL_DOC_BG

    row = _title_row()
    tab = row.document_tab
    probe = (4, tab.height() // 2)

    def fill():
        return tab.grab().toImage().pixelColor(*probe)

    idle = fill()
    assert idle.name() == COL_DOC_BG and not tab.is_hovered()
    pos = QPointF(probe[0], probe[1])
    QApplication.sendEvent(tab, QEnterEvent(pos, pos, QPointF(tab.mapToGlobal(pos.toPoint()))))
    _settle(2)
    hover = fill()
    assert tab.is_hovered() and hover.lightness() > idle.lightness()

    activated: list[bool] = []
    tab.activated.connect(lambda: activated.append(True))
    QTest.mousePress(tab, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     tab.rect().center())
    _settle(2)
    assert tab.is_pressed() and activated == [True]
    pressed = fill()
    assert pressed.lightness() < idle.lightness() < hover.lightness()
    QTest.mouseRelease(tab, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       tab.rect().center())
    _settle(2)
    assert not tab.is_pressed() and fill().name() == hover.name()
    QApplication.sendEvent(tab, QEvent(QEvent.Type.Leave))
    _settle(2)
    assert not tab.is_hovered() and fill().name() == COL_DOC_BG


def test_document_tab_drag_state() -> None:
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    row = _title_row()
    tab = row.document_tab

    def move(x: float) -> None:
        local = QPointF(x, tab.height() / 2)
        ev = QMouseEvent(QEvent.Type.MouseMove, local, QPointF(tab.mapToGlobal(local.toPoint())),
                         Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tab, ev)

    QTest.mousePress(tab, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     tab.rect().center())
    assert tab.is_pressed()
    move(tab.width() + 40)
    assert not tab.is_pressed()
    move(tab.width() / 3)
    assert tab.is_pressed()
    QTest.mouseRelease(tab, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       tab.rect().center())
    assert not tab.is_pressed()


def test_sculpt_bar_matches_reference() -> None:
    from quartz_studio.widgets.common import IconButton
    from quartz_studio.widgets.sculpt_bar import SculptBar

    _app()
    bar = SculptBar()
    _HOSTS.append(bar)
    buttons = [b for b in bar.findChildren(IconButton) if b.toolTip()]
    names = {b.toolTip() for b in buttons}
    assert len([b for b in buttons if not b.toolTip().endswith("Settings")]) == 23, names
    assert "Subdivide Settings" in names
    assert {b.toolTip() for b in buttons if b.isEnabled()} == {"Project Mesh"}


def test_native_titlebar_colorref_and_noop_offscreen() -> None:
    from quartz_studio import theme
    from quartz_studio.app import apply_native_titlebar, colorref

    _app()
    assert colorref("#0f1115") == 0x0015110F
    assert colorref(theme.SURFACE_BACKDROP) == 0x0015110F
    assert colorref(theme.TEXT_PRIMARY) == 0x00F0EAE7
    assert colorref(theme.HAIRLINE) == 0x0040302A
    probe = QWidget()
    try:
        apply_native_titlebar(probe)
    finally:
        probe.deleteLater()


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
