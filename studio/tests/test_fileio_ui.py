from __future__ import annotations

import json
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QMimeData, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

import quartz_studio
from quartz_studio import fileio, project
from quartz_studio.app import create_app
from quartz_studio.scene import Scene, get_scene, reset_scene

TMP = tempfile.mkdtemp(prefix="qz_fileio_ui_")
SETTINGS = os.path.join(TMP, "settings.ini")
project.SETTINGS_FILE = SETTINGS

_STATE: dict = {}


class FakeDialogs:

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.open_answers: list = []
        self.save_answers: list = []
        self.ask_answers: list = []
        self.open_calls: list = []
        self.save_calls: list = []
        self.ask_calls: list = []
        self.messages: list = []
        self.quits = 0

    def choose_open_files(self, title, directory, filters, multiple=False):
        self.open_calls.append((title, list(filters), multiple))
        return list(self.open_answers.pop(0)) if self.open_answers else []

    def choose_save_file(self, title, path, filters):
        self.save_calls.append((title, path, list(filters)))
        return self.save_answers.pop(0) if self.save_answers else None

    def ask_save_changes(self, name):
        self.ask_calls.append(name)
        return self.ask_answers.pop(0) if self.ask_answers else "cancel"

    def show_message(self, kind, text):
        self.messages.append((kind, text))

    def quit_application(self):
        self.quits += 1

    NAMES = ("choose_open_files", "choose_save_file", "ask_save_changes", "show_message",
             "quit_application")

    def install(self) -> None:
        for name in self.NAMES:
            setattr(project, name, getattr(self, name))


FAKE = FakeDialogs()


def _path(name: str) -> str:
    return os.path.join(TMP, name)


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(passes: int = 3) -> None:
    app = _app()
    for _ in range(passes):
        app.processEvents()


def _window():
    if "window" not in _STATE:
        _app()
        reset_scene()
        from quartz_studio.main_window import MainWindow

        win = MainWindow()
        win.resize(1500, 900)
        win.show()
        _settle(6)
        _STATE["window"] = win
    return _STATE["window"]


def _fresh():
    win = _window()
    FAKE.reset()
    FAKE.install()
    project.SETTINGS_FILE = SETTINGS
    project.clear_recent()
    FAKE.ask_answers = ["discard"]
    assert project.new_project()
    FAKE.reset()
    assert project.current_path() is None and not project.is_modified()
    return win, get_scene()


def _canvas():
    return _window().viewport.canvas


def _names(scene) -> list[str]:
    return [o.name for o in scene.objects]


def _build_scene(scene) -> None:
    scene.add_parametric("sphere", name="Ball")
    scene.add_parametric("null", name="Group")


def _points(scene) -> dict:
    return {o.name: (o.kind, np.round(o.mesh.points, 6).tolist(), list(o.position),
                     list(o.rotation), list(o.scale)) for o in scene.objects}


def _same_scene(a: dict, b: dict) -> None:
    assert a.keys() == b.keys(), (sorted(a), sorted(b))
    for name in a:
        assert a[name][0] == b[name][0], name
        assert np.allclose(np.array(a[name][1]), np.array(b[name][1]), atol=1e-5), name
        for i in (2, 3, 4):
            assert np.allclose(a[name][i], b[name][i], atol=1e-6), (name, i)


def test_default_title_and_clean_state() -> None:
    win, scene = _fresh()
    assert quartz_studio.WINDOW_TITLE == "Untitled - Quartz"
    assert win.windowTitle() == quartz_studio.WINDOW_TITLE == project.window_title()
    _settle(4)
    assert not project.is_modified() and project.current_path() is None


def test_title_asterisk_follows_changes() -> None:
    win, scene = _fresh()
    scene.add_object("Extra")
    assert project.is_modified()
    assert win.windowTitle() == "Untitled* - Quartz"
    target = _path("title.quartz")
    FAKE.save_answers = [target]
    assert project.save_project()
    assert win.windowTitle() == "title.quartz - Quartz"
    assert not project.is_modified()
    scene.add_object("Again")
    assert win.windowTitle() == "title.quartz* - Quartz"
    assert project.save_project()
    assert win.windowTitle() == "title.quartz - Quartz"
    assert len(FAKE.save_calls) == 1


def test_selection_and_tool_changes_do_not_mark_modified() -> None:
    win, scene = _fresh()
    scene.set_tool("move")
    scene.set_mode("points")
    scene.set_mode("model")
    scene.set_active(scene.objects[0])
    _settle(4)
    assert not project.is_modified()


def test_new_project_asks_when_modified() -> None:
    win, scene = _fresh()
    scene.add_object("Extra")
    FAKE.ask_answers = ["cancel"]
    assert not project.new_project()
    assert "Extra" in _names(scene) and project.is_modified()
    assert FAKE.ask_calls == ["Untitled"]
    FAKE.ask_answers = ["discard"]
    assert project.new_project()
    assert _names(scene) == ["Cube"] and not project.is_modified()
    assert not scene.can_undo()
    assert win.windowTitle() == quartz_studio.WINDOW_TITLE
    scene.add_object("Other")
    target = _path("new_save.quartz")
    FAKE.ask_answers = ["save"]
    FAKE.save_answers = [target]
    assert project.new_project()
    assert os.path.isfile(target) and _names(scene) == ["Cube"] and project.current_path() is None
    scene.add_object("Other")
    FAKE.ask_answers = ["save"]
    FAKE.save_answers = [None]
    assert not project.new_project()
    assert "Other" in _names(scene)
    calls = len(FAKE.ask_calls)
    assert project.is_modified()
    FAKE.ask_answers = ["discard"]
    assert project.new_project()
    assert len(FAKE.ask_calls) == calls + 1


def test_unmodified_project_never_asks() -> None:
    win, scene = _fresh()
    assert project.new_project()
    assert FAKE.ask_calls == []


def test_save_as_open_round_trip() -> None:
    win, scene = _fresh()
    _build_scene(scene)
    before = _points(scene)
    target = _path("round")
    FAKE.save_answers = [target]
    assert project.save_project_as()
    saved = _path("round.quartz")
    assert os.path.isfile(saved) and project.current_path() == saved
    assert FAKE.save_calls[0][2] == [fileio.file_filter(fileio.get("quartz"))]
    FAKE.ask_answers = ["discard"]
    assert project.new_project()
    assert _names(scene) == ["Cube"]
    FAKE.open_answers = [[saved]]
    assert project.open_project()
    _same_scene(before, _points(scene))
    assert project.current_path() == saved and not project.is_modified()
    assert not scene.can_undo()
    assert FAKE.open_calls[0][1] == [fileio.file_filter(fileio.get("quartz"))]
    assert project.window_title() == "round.quartz - Quartz"


def test_save_as_cancel_and_open_cancel() -> None:
    win, scene = _fresh()
    scene.add_object("Extra")
    FAKE.save_answers = [None]
    assert not project.save_project_as()
    assert project.current_path() is None and project.is_modified()
    assert not project.save_project()
    FAKE.ask_answers = ["discard"]
    FAKE.open_answers = [[]]
    assert not project.open_project()
    assert "Extra" in _names(scene)


def test_save_project_writes_to_the_current_path() -> None:
    win, scene = _fresh()
    target = _path("same.quartz")
    FAKE.save_answers = [target]
    assert project.save_project()
    scene.add_object("Later")
    assert project.save_project()
    assert len(FAKE.save_calls) == 1
    probe = Scene()
    fileio.open_scene(probe, target)
    assert "Later" in _names(probe)


def test_save_incremental() -> None:
    win, scene = _fresh()
    FAKE.save_answers = [_path("inc.quartz")]
    assert project.save_incremental()
    assert FAKE.save_calls and project.current_path() == _path("inc.quartz")
    scene.add_object("One")
    assert project.save_incremental()
    assert os.path.isfile(_path("inc_0001.quartz")) and project.current_path() == _path("inc_0001.quartz")
    assert not project.is_modified()
    assert project.save_incremental()
    assert os.path.isfile(_path("inc_0002.quartz"))
    assert project.window_title() == "inc_0002.quartz - Quartz"
    assert len(FAKE.save_calls) == 1
    assert project.next_incremental(_path("take_0009.quartz")) == _path("take_0010.quartz")
    assert project.next_incremental(_path("plain.quartz")) == _path("plain_0001.quartz")


def test_open_recent_list() -> None:
    win, scene = _fresh()
    names = [f"recent{i}.quartz" for i in range(12)]
    for name in names:
        FAKE.save_answers = [_path(name)]
        assert project.save_project_as()
    recent = project.recent_files()
    assert len(recent) == 10 and recent[0] == _path(names[-1]) and recent[-1] == _path(names[2])
    menu_bar = win.regions["menu_bar"]
    recent_menu = menu_bar.menu_at(("File", "Open Recent", "x"))
    recent_menu.aboutToShow.emit()
    texts = recent_menu.entries_text()
    assert texts[:10] == [n for n in reversed(names[2:])] and texts[-1] == "Clear Recent File List"
    assert texts[10] == "---"
    FAKE.ask_answers = []
    target = recent_menu.find_action("recent5.quartz")
    scene.add_object("Dirty")
    FAKE.ask_answers = ["cancel"]
    target.trigger()
    assert project.current_path() == _path("recent11.quartz") and "Dirty" in _names(scene)
    FAKE.ask_answers = ["discard"]
    target.trigger()
    assert project.current_path() == _path("recent5.quartz") and "Dirty" not in _names(scene)
    assert project.recent_files()[0] == _path("recent5.quartz")
    os.remove(_path("recent7.quartz"))
    FAKE.ask_answers = ["discard"]
    assert not project.open_recent(_path("recent7.quartz"))
    assert _path("recent7.quartz") not in project.recent_files()
    assert FAKE.messages and FAKE.messages[-1][0] == "error" and "recent7.quartz" in FAKE.messages[-1][1]
    recent_menu.aboutToShow.emit()
    clear = recent_menu.find_action("Clear Recent File List")
    assert clear.isEnabled()
    clear.trigger()
    assert project.recent_files() == []
    recent_menu.aboutToShow.emit()
    assert recent_menu.entries_text() == ["Clear Recent File List"]
    assert not recent_menu.find_action("Clear Recent File List").isEnabled()


def test_menu_items_run_the_commands() -> None:
    win, scene = _fresh()
    bar = win.regions["menu_bar"]
    scene.add_object("Extra")
    FAKE.save_answers = [_path("menu.quartz")]
    bar.action_at(("File", "Save Project")).trigger()
    assert project.current_path() == _path("menu.quartz")
    FAKE.save_answers = [_path("menu_as.quartz")]
    bar.action_at(("File", "Save Project As...")).trigger()
    assert project.current_path() == _path("menu_as.quartz")
    bar.action_at(("File", "Save Incremental")).trigger()
    assert project.current_path() == _path("menu_as_0001.quartz")
    FAKE.ask_answers = ["discard"]
    bar.action_at(("File", "New Project")).trigger()
    assert project.current_path() is None
    FAKE.open_answers = [[_path("menu_as.quartz")]]
    bar.action_at(("File", "Open Project...")).trigger()
    assert project.current_path() == _path("menu_as.quartz") and "Extra" in _names(scene)
    FAKE.open_answers = [[_path("menu_as_0001.quartz")]]
    bar.action_at(("File", "Merge Project...")).trigger()
    assert "Extra.1" in _names(scene)
    FAKE.open_answers = [[]]
    bar.action_at(("File", "Import...")).trigger()
    assert FAKE.open_calls[-1][2] is True
    assert FAKE.open_calls[-1][1] == fileio.import_filters()


def test_merge_project_adds_objects_in_one_undo_step() -> None:
    win, scene = _fresh()
    _build_scene(scene)
    FAKE.save_answers = [_path("merge_src.quartz")]
    assert project.save_project_as()
    FAKE.ask_answers = ["discard"]
    assert project.new_project()
    assert project.current_path() is None
    FAKE.open_answers = [[_path("merge_src.quartz")]]
    added = project.merge_project()
    assert len(added) >= 3
    assert {"Cube.1", "Ball", "Group"} <= set(_names(scene)), _names(scene)
    assert project.current_path() is None and project.is_modified()
    scene.undo()
    assert _names(scene) == ["Cube"]
    assert not scene.can_undo()


def test_every_exporter_writes_a_file_with_its_filter() -> None:
    win, scene = _fresh()
    _build_scene(scene)
    exporters = fileio.exporters()
    assert len(exporters) >= 7
    for fmt in exporters:
        FAKE.save_answers = [_path(f"export_{fmt.id}")]
        assert project.export_as(fmt.id), fmt.id
        assert FAKE.save_calls[-1][2] == [fileio.file_filter(fmt)], fmt.id
        written = _path(f"export_{fmt.id}") + fmt.extensions[0]
        assert os.path.isfile(written) and os.path.getsize(written) > 0, fmt.id
        doc = fmt.load(written) if fmt.load is not None else None
        if doc is not None and fmt.id != "quartz":
            assert doc.nodes, fmt.id
    assert not FAKE.messages, FAKE.messages
    assert project.current_path() is None


def test_export_menu_has_one_item_per_exporter() -> None:
    win, scene = _fresh()
    bar = win.regions["menu_bar"]
    FAKE.reset()
    FAKE.install()
    from quartz_studio.widgets import menus_data

    for fmt in fileio.exporters():
        FAKE.save_answers = [_path(f"menu_export_{fmt.id}")]
        bar.action_at(("File", "Export", menus_data.export_label(fmt))).trigger()
        assert os.path.isfile(_path(f"menu_export_{fmt.id}") + fmt.extensions[0]), fmt.id
        assert FAKE.save_calls[-1][2] == [fileio.file_filter(fmt)]


def test_export_selection() -> None:
    win, scene = _fresh()
    _build_scene(scene)
    scene.set_active(scene.objects[0], select=False)
    assert not project.export_selection()
    assert FAKE.messages and FAKE.messages[-1][0] == "error" and not FAKE.save_calls
    scene.set_active(scene.objects[0])
    FAKE.save_answers = [_path("selection.obj")]
    assert project.export_selection()
    assert FAKE.save_calls[-1][2] == fileio.export_filters()
    probe = Scene()
    before = len(probe.objects)
    fileio.import_file(probe, _path("selection.obj"))
    assert len(probe.objects) == before + 1


def test_export_nothing_is_a_message() -> None:
    win, scene = _fresh()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    FAKE.save_answers = [_path("empty.obj")]
    assert not project.export_as("obj")
    assert FAKE.messages and FAKE.messages[-1][0] == "error"
    assert "nothing to export" in FAKE.messages[-1][1]
    assert not os.path.exists(_path("empty.obj"))


def test_import_every_importer_as_one_undo_step_and_frames() -> None:
    win, scene = _fresh()
    scene.add_parametric("sphere", name="Far")
    far = scene.objects[-1]
    far.position = np.array([6000.0, 0.0, 0.0])
    scene.changed.emit()
    scene.set_active(far)
    importers = fileio.importers()
    assert len(importers) >= 7
    written = {}
    for fmt in fileio.exporters():
        FAKE.save_answers = [_path(f"far_{fmt.id}")]
        assert project.export_as(fmt.id), fmt.id
        written[fmt.id] = _path(f"far_{fmt.id}") + fmt.extensions[0]
    for fmt in importers:
        assert fmt.id in written, fmt.id
        project.new_project()
        FAKE.ask_answers = ["discard"]
        project.new_project()
        FAKE.messages.clear()
        before = len(scene.objects)
        FAKE.open_answers = [[written[fmt.id]]]
        project.import_files()
        assert FAKE.open_calls[-1][1] == fileio.import_filters()
        assert len(scene.objects) > before, fmt.id
        assert not [m for m in FAKE.messages if m[0] == "error"], (fmt.id, FAKE.messages)
        assert project.is_modified()
        target = _canvas().camera.target
        assert abs(float(target[0]) - 3000.0) < 200.0, (fmt.id, target)
        scene.undo()
        assert len(scene.objects) == before, fmt.id


def test_import_unknown_and_broken_files_show_messages() -> None:
    win, scene = _fresh()
    before = _names(scene)
    odd = _path("odd.xyz")
    with open(odd, "w", encoding="utf-8") as handle:
        handle.write("nothing")
    broken = _path("broken.obj")
    with open(broken, "w", encoding="utf-8") as handle:
        handle.write("v 1 2\nf 1 2 3\n")
    FAKE.open_answers = [[odd, broken, _path("missing.obj")]]
    added = project.import_files()
    assert added == [] and _names(scene) == before
    assert len(FAKE.messages) == 1 and FAKE.messages[0][0] == "error"
    text = FAKE.messages[0][1]
    assert "odd.xyz" in text and "broken.obj" in text and "missing.obj" in text, text
    assert not project.is_modified()


def test_broken_project_keeps_the_current_scene() -> None:
    win, scene = _fresh()
    _build_scene(scene)
    FAKE.save_answers = [_path("good.quartz")]
    assert project.save_project()
    names = _names(scene)
    bad = _path("bad.quartz")
    with open(bad, "w", encoding="utf-8") as handle:
        handle.write('{"format": "quartz", "version": 1, "scene": ')
    FAKE.open_answers = [[bad]]
    assert not project.open_project()
    assert _names(scene) == names and project.current_path() == _path("good.quartz")
    assert FAKE.messages[-1][0] == "error" and "bad.quartz" in FAKE.messages[-1][1]
    FAKE.open_answers = [[_path("far_obj.obj")]]
    assert not project.open_project()
    assert FAKE.messages[-1][0] == "error" and "not a Quartz project" in FAKE.messages[-1][1]
    assert _names(scene) == names


def test_unknown_object_kind_warning_is_shown_once() -> None:
    win, scene = _fresh()
    _build_scene(scene)
    FAKE.save_answers = [_path("warn_src.quartz")]
    assert project.save_project()
    with open(_path("warn_src.quartz"), "r", encoding="utf-8") as handle:
        data = json.load(handle)
    for entry in data["scene"]["objects"]:
        if entry.get("name") == "Ball":
            entry["kind"] = "future_kind_xyz"
    warn = _path("warn.quartz")
    with open(warn, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    FAKE.ask_answers = ["discard"]
    FAKE.open_answers = [[warn]]
    assert project.open_project()
    warnings = [m for m in FAKE.messages if m[0] == "warning"]
    assert len(warnings) == 1 and "future_kind_xyz" in warnings[0][1], FAKE.messages
    assert not [m for m in FAKE.messages if m[0] == "error"]
    FAKE.messages.clear()
    FAKE.open_answers = [[warn]]
    project.merge_project()
    warnings = [m for m in FAKE.messages if m[0] == "warning"]
    assert len(warnings) == 1


def _set_camera(canvas, heading, pitch, distance, target) -> None:
    canvas.camera.heading = heading
    canvas.camera.pitch = pitch
    canvas.camera.distance = distance
    canvas.camera.target = np.array(target, float)


def test_camera_round_trip() -> None:
    win, scene = _fresh()
    canvas = _canvas()
    _set_camera(canvas, 33.0, -12.0, 777.0, (10.0, 20.0, 30.0))
    saved = _path("camera.quartz")
    FAKE.save_answers = [saved]
    assert project.save_project()
    with open(saved, "r", encoding="utf-8") as handle:
        view = json.load(handle)["view"]
    for key in ("position", "target", "heading", "pitch", "distance", "name"):
        assert key in view, key
    assert view["name"] == "Perspective" and abs(view["heading"] - 33.0) < 1e-9
    _set_camera(canvas, -80.0, 40.0, 100.0, (0.0, 0.0, 0.0))
    scene.add_object("Dirty")
    FAKE.ask_answers = ["discard"]
    FAKE.open_answers = [[saved]]
    assert project.open_project()
    cam = canvas.camera
    assert abs(cam.heading - 33.0) < 1e-9 and abs(cam.pitch + 12.0) < 1e-9
    assert abs(cam.distance - 777.0) < 1e-9
    assert np.allclose(cam.target, (10.0, 20.0, 30.0))
    assert canvas.view_name == "Perspective" and not cam.ortho
    assert np.allclose(cam.position(), view["position"], atol=1e-6)
    canvas.set_view("Top")
    top = canvas.camera
    saved_top = _path("camera_top.quartz")
    FAKE.save_answers = [saved_top]
    assert project.save_project_as()
    canvas.set_view("Perspective")
    FAKE.open_answers = [[saved_top]]
    assert project.open_project()
    assert canvas.view_name == "Top" and canvas.camera.ortho
    assert abs(canvas.camera.pitch - top.pitch) < 1e-9
    assert not canvas.can_undo_view()
    FAKE.ask_answers = ["discard"]
    assert project.new_project()
    assert canvas.view_name == "Perspective" and not canvas.camera.ortho


def test_project_without_a_stored_view_is_framed() -> None:
    win, scene = _fresh()
    scene.objects[0].position = np.array([4000.0, 0.0, 0.0])
    scene.changed.emit()
    saved = _path("noview.quartz")
    probe = scene
    fileio.save_scene(probe, saved)
    FAKE.ask_answers = ["discard"]
    FAKE.open_answers = [[saved]]
    assert project.open_project()
    assert abs(float(_canvas().camera.target[0]) - 4000.0) < 200.0


def test_command_line_and_drops() -> None:
    win, scene = _fresh()
    _build_scene(scene)
    saved = _path("cli.quartz")
    FAKE.save_answers = [saved]
    assert project.save_project()
    FAKE.save_answers = [_path("cli_part")]
    assert project.export_as("obj")
    obj = _path("cli_part.obj")
    argv = [sys.argv[0], saved, "-platform", "offscreen", obj, _path("notes.txt"), "-x.obj"]
    assert project.paths_from_argv(argv) == [saved, obj]
    FAKE.ask_answers = ["discard"]
    assert project.new_project()
    project.open_paths(project.paths_from_argv(argv))
    assert project.current_path() == saved
    assert {"Ball", "Group"} <= set(_names(scene))
    assert any(n.startswith("Cube") for n in _names(scene)) and len(scene.objects) > 4
    assert not [m for m in FAKE.messages if m[0] == "error"], FAKE.messages
    FAKE.ask_answers = ["discard"]
    assert project.new_project()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(saved)])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    win.dropEvent(event)
    assert project.current_path() == saved and "Ball" in _names(scene)
    assert win.acceptDrops()
    count = len(scene.objects)
    mime2 = QMimeData()
    mime2.setUrls([QUrl.fromLocalFile(obj)])
    win.dropEvent(QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime2,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert len(scene.objects) > count and project.current_path() == saved and project.is_modified()


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


def test_main_opens_a_path_from_the_command_line() -> None:
    win, scene = _fresh()
    scene.add_parametric("sphere", name="FromCli")
    saved = _path("main_cli.quartz")
    FAKE.save_answers = [saved]
    assert project.save_project()
    qapp = _app()
    QTimer.singleShot(1500, qapp.quit)
    assert _isolated_main([sys.argv[0], saved]) == 0
    assert project.current_path() == saved
    assert "FromCli" in _names(get_scene())
    for w in QApplication.topLevelWidgets():
        if w is not win and w.isWindow():
            w.close()
    _STATE["window"].show()
    project.attach(_STATE["window"])
    from quartz_studio import controls

    controls.install(_STATE["window"])


def test_exit_with_the_three_answers() -> None:
    win, scene = _fresh()
    assert project.exit_app()
    assert FAKE.quits == 1 and FAKE.ask_calls == []
    scene.add_object("Dirty")
    FAKE.ask_answers = ["cancel"]
    assert not project.exit_app()
    assert FAKE.quits == 1 and len(FAKE.ask_calls) == 1
    FAKE.ask_answers = ["discard"]
    assert project.exit_app()
    assert FAKE.quits == 2 and project.current_path() is None
    FAKE.ask_answers = ["save"]
    FAKE.save_answers = [None]
    assert not project.exit_app()
    assert FAKE.quits == 2 and project.is_modified()
    FAKE.ask_answers = ["save"]
    FAKE.save_answers = [_path("exit_save.quartz")]
    assert project.exit_app()
    assert FAKE.quits == 3 and os.path.isfile(_path("exit_save.quartz"))
    assert not project.is_modified()
    scene.add_object("Dirty2")
    bar = win.regions["menu_bar"]
    FAKE.ask_answers = ["cancel"]
    bar.action_at(("File", "Exit")).trigger()
    assert FAKE.quits == 3
    FAKE.ask_answers = ["discard"]
    bar.action_at(("File", "Exit")).trigger()
    assert FAKE.quits == 4


def test_closing_the_window_asks() -> None:
    win, scene = _fresh()
    from quartz_studio.main_window import MainWindow

    other = MainWindow()
    other.resize(1200, 800)
    other.show()
    _settle(4)
    FAKE.reset()
    FAKE.install()
    scene.add_object("Dirty")
    FAKE.ask_answers = ["cancel"]
    other.close()
    assert other.isVisible() and len(FAKE.ask_calls) == 1
    FAKE.ask_answers = ["discard"]
    other.close()
    assert not other.isVisible() and len(FAKE.ask_calls) == 2
    other.deleteLater()
    _settle(2)
    project.attach(win)


def test_exit_asks_once_when_the_real_quit_closes_the_windows() -> None:
    win, scene = _fresh()
    scene.add_object("Dirty")
    assert project.is_modified()
    calls = {"quit": 0}

    def real_like_quit() -> None:
        calls["quit"] += 1
        QApplication.closeAllWindows()

    project.quit_application = real_like_quit
    FAKE.ask_answers = ["discard"]
    try:
        assert project.exit_app()
    finally:
        FAKE.install()
    assert calls["quit"] == 1 and len(FAKE.ask_calls) == 1, FAKE.ask_calls
    assert not win.isVisible()
    win.show()
    _settle(4)
    assert project.is_modified()
    FAKE.ask_answers = ["cancel"]
    win.close()
    assert win.isVisible() and len(FAKE.ask_calls) == 2


def test_open_project_asks_about_saving_only_after_a_file_is_chosen() -> None:
    win, scene = _fresh()
    saved = _path("late_ask.quartz")
    FAKE.save_answers = [saved]
    assert project.save_project()
    scene.add_object("Dirty")
    FAKE.ask_answers = ["save"]
    FAKE.open_answers = [[]]
    assert not project.open_project()
    assert FAKE.ask_calls == [] and project.is_modified()
    FAKE.open_answers = [[saved]]
    FAKE.ask_answers = ["cancel"]
    assert not project.open_project()
    assert len(FAKE.ask_calls) == 1 and project.is_modified()
    FAKE.open_answers = [[saved]]
    FAKE.ask_answers = ["discard"]
    assert project.open_project()
    assert len(FAKE.ask_calls) == 2 and not project.is_modified()
    scene.add_object("Dirty2")
    missing = _path("gone.quartz")
    FAKE.ask_answers = ["save"]
    assert not project.open_recent(missing)
    assert len(FAKE.ask_calls) == 2 and project.is_modified()
    assert any("not found" in m[1] for m in FAKE.messages)


def test_keyboard_shortcuts_run_the_commands() -> None:
    win, scene = _fresh()
    scene.add_object("Extra")
    FAKE.save_answers = [_path("keys.quartz")]
    by_key = {sc.key().toString(): sc for sc in win.file_shortcuts}
    by_key["Ctrl+S"].activated.emit()
    assert project.current_path() == _path("keys.quartz")
    FAKE.ask_answers = ["discard"]
    by_key["Ctrl+N"].activated.emit()
    assert project.current_path() is None
    FAKE.open_answers = [[_path("keys.quartz")]]
    by_key["Ctrl+O"].activated.emit()
    assert project.current_path() == _path("keys.quartz")
    FAKE.save_answers = [_path("keys2.quartz")]
    by_key["Ctrl+Shift+S"].activated.emit()
    assert project.current_path() == _path("keys2.quartz")
    by_key["Ctrl+Alt+S"].activated.emit()
    assert project.current_path() == _path("keys2_0001.quartz")
    FAKE.open_answers = [[_path("keys.quartz")]]
    by_key["Ctrl+Shift+O"].activated.emit()
    assert len(FAKE.open_calls) == 2


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
