from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

os.environ["QUARTZ_HOME"] = tempfile.mkdtemp(prefix="quartz_scripting_")

import json
import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow

APP = QApplication.instance() or QApplication([])

from quartz_studio import scripting
from quartz_studio.ext import store
from quartz_studio.modeling import registry as mreg
from quartz_studio.modeling.meshkit import OpResult
from quartz_studio.objects import registry as oreg
from quartz_studio.scene import Mesh, Scene, reset_scene
from quartz_studio.scripting import api, examples, paths, pytags
from quartz_studio.scripting.api import ScriptError
from quartz_studio.scripting.console import ConsoleInput, ScriptConsole
from quartz_studio.scripting.highlight import COLORS, PythonHighlighter
from quartz_studio.scripting.library import ScriptLibrary, sanitize_name
from quartz_studio.scripting.manager import ScriptManager
from quartz_studio.scripting.plugin_panel import PluginManager
from quartz_studio.scripting.plugins import PluginLoader
from quartz_studio.scripting.runner import execute, is_complete, make_namespace


def _fresh_home() -> Path:
    scripting.reset_loader()
    home = Path(tempfile.mkdtemp(prefix="quartz_scripting_"))
    os.environ["QUARTZ_HOME"] = str(home)
    return home


def _scene() -> Scene:
    return Scene()


def _close(a, b, tol=1e-6) -> bool:
    return np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol)


def _write_plugin(home: Path, stem: str, text: str) -> Path:
    path = home / "plugins" / f"{stem}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_paths_honour_quartz_home():
    home = _fresh_home()
    assert paths.quartz_home() == home
    assert paths.scripts_dir() == home / "scripts" and (home / "scripts").is_dir()
    assert paths.plugins_dir() == home / "plugins" and (home / "plugins").is_dir()
    paths.update_settings("alpha", [1, 2])
    assert paths.read_settings()["alpha"] == [1, 2]
    paths.update_settings("alpha", None)
    assert "alpha" not in paths.read_settings()


def test_sanitize_name():
    assert sanitize_name("hello") == "hello.py"
    assert sanitize_name("hello.py") == "hello.py"
    assert sanitize_name("..\\evil/name?.py") == "name_.py"
    assert sanitize_name("A b (2)") == "A b (2).py"
    try:
        sanitize_name("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("empty name accepted")


def test_library_crud_and_shortcuts():
    home = _fresh_home()
    lib = ScriptLibrary()
    assert lib.list() == []
    a = lib.create("Tool")
    b = lib.create("Tool")
    assert (a, b) == ("Tool.py", "Tool 1.py")
    assert lib.list() == ["Tool 1.py", "Tool.py"]
    lib.save("Tool", "print('x')\n")
    assert lib.load("Tool.py") == "print('x')\n"
    lib.set_shortcut("Tool", "Ctrl+Alt+T")
    assert lib.shortcut("Tool.py") == "Ctrl+Alt+T"
    lib.set_shortcut("Tool 1", "Ctrl+Alt+T")
    assert lib.shortcut("Tool") == "" and lib.shortcut("Tool 1") == "Ctrl+Alt+T"
    new = lib.rename("Tool 1", "Renamed")
    assert new == "Renamed.py" and lib.shortcut("Renamed") == "Ctrl+Alt+T"
    assert lib.list() == ["Renamed.py", "Tool.py"]
    try:
        lib.rename("Renamed", "Tool")
    except FileExistsError:
        pass
    else:
        raise AssertionError("rename overwrote a script")
    outside = home / "outside.py"
    outside.write_text("value = 5\n", encoding="utf-8")
    imported = lib.import_file(outside)
    assert imported == "outside.py" and lib.load(imported) == "value = 5\n"
    assert lib.delete("Renamed") and not lib.exists("Renamed")
    assert lib.shortcuts() == {}
    assert not lib.delete("Renamed")


def test_execute_captures_output_and_errors():
    _fresh_home()
    sc = _scene()
    ns = make_namespace(sc)
    assert ns["doc"] is sc and ns["op"] is sc.active and ns["np"] is np and ns["quartz"] is api
    r = execute("import sys\nprint('hello')\nprint('oops', file=sys.stderr)\n", ns, "t.py", scene=sc)
    assert r.ok and r.stdout == "hello\n" and r.stderr == "oops\n" and r.error == ""
    r = execute("x = 1\n\ndef f():\n    return 1 / 0\n\nf()\n", ns, "boom.py", scene=sc)
    assert not r.ok
    assert "ZeroDivisionError" in r.error and "boom.py" in r.error and "line 4" in r.error
    assert "return 1 / 0" in r.error
    assert "runner.py" not in r.error
    r = execute("def broken(:\n", ns, "syn.py", scene=sc)
    assert not r.ok and "SyntaxError" in r.error
    r = execute("raise SystemExit(0)", ns, scene=sc)
    assert r.ok
    r = execute("raise SystemExit('stop here')", ns, scene=sc)
    assert not r.ok and "stop here" in r.error
    r = execute("2 + 3", ns, interactive=True, scene=sc)
    assert r.ok and r.has_value and r.value == 5 and ns["_"] == 5
    r = execute("y = 7", ns, interactive=True, scene=sc)
    assert r.ok and not r.has_value and ns["y"] == 7
    r = execute("y * 2", ns, interactive=True, scene=sc)
    assert r.value == 14
    r = execute("quartz.message('hi there')", ns, scene=sc)
    assert r.messages == ["hi there"]
    assert "boom.py" in r.summary() or r.summary().startswith("<script>")


def test_is_complete():
    assert is_complete("x = 1")
    assert not is_complete("for i in range(3):")
    assert not is_complete("for i in range(3):\n    print(i)")
    assert is_complete("for i in range(3):\n    print(i)\n")
    assert not is_complete("foo(1,")
    assert is_complete("def (:")
    assert is_complete("")


def test_script_run_is_one_undo_step():
    _fresh_home()
    sc = _scene()
    lib = ScriptLibrary()
    lib.save("three", "for i in range(3):\n    quartz.create('cube', name=f'C{i}')\n")
    before = len(sc.objects)
    r = lib.run("three", sc)
    assert r.ok, r.error
    assert len(sc.objects) == before + 3
    assert sc.undo()
    assert len(sc.objects) == before


def test_api_objects_and_find():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        assert api.document() is sc
        cube = api.find("cube")
        assert cube is sc.objects[0]
        s = api.create("sphere", name="Ball", radius=50.0, segments=8)
        assert s.kind == "sphere" and s.params["radius"] == 50.0 and s.params["segments"] == 8
        lo, hi = api.bounds(s, world=False)
        assert _close(hi - lo, [100.0, 100.0, 100.0], 1e-6)
        assert api.find_all("b*") == [s]
        assert api.find_all("*", kind="polygon") == [cube]
        assert "cube" in api.object_kinds() and "polygon" in api.object_kinds()
        assert "null" in api.object_kinds("null")
        info = api.kind_info("cube")
        assert any(p["key"] == "size_x" for p in info["params"])
        try:
            api.create("nonsense")
        except ScriptError as exc:
            assert "nonsense" in str(exc)
        else:
            raise AssertionError("unknown kind accepted")
        try:
            api.create("cube", wrong_param=1)
        except ScriptError:
            pass
        else:
            raise AssertionError("unknown parameter accepted")
        api.set_param(s, "radius", 25.0)
        lo, hi = api.bounds(s, world=False)
        assert _close(hi - lo, [50.0, 50.0, 50.0], 1e-6)
        api.set_param(s, "segments", -5)
        assert api.get_param(s, "segments") >= 3
        api.rename(s, "Ball Two")
        assert api.find("Ball Two") is s
    assert api.document() is not sc


def test_api_create_with_params_and_transform_in_one_undo():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        n = len(sc.objects)
        box = api.create("cube", name="Box", size_x=40.0, size_y=60.0, size_z=80.0,
                         position=(10, 20, 30), rotation=(0, 90, 0), scale=2)
        assert _close(api.position(box), [10, 20, 30])
        assert _close(api.scale(box), [2, 2, 2])
        assert _close(box.mesh.size(), [40, 60, 80])
        world = api.points(box, world=True)
        lo, hi = world.min(axis=0), world.max(axis=0)
        assert _close(hi - lo, [160, 120, 80], 1e-6)
        assert _close((hi + lo) / 2, [10, 20, 30], 1e-6)
        assert api.undo()
        assert len(sc.objects) == n


def test_api_polygon_object_points_and_world_space():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        tri = api.create_polygon_object("Tri", [(0, 0, 0), (100, 0, 0), (0, 100, 0)], [(0, 1, 2)])
        assert api.point_count(tri) == 3 and api.polygon_count(tri) == 1
        assert _close(api.polygon_normals(tri)[0], [0, 0, 1])
        api.set_transform(tri, position=(5, 0, 0), rotation=(0, 0, 90))
        world = api.points(tri, world=True)
        assert _close(world[1], [5, 100, 0], 1e-9)
        api.set_points(tri, [(0, 0, 0), (0, 200, 0), (0, 0, 50)], world=True)
        local = api.points(tri)
        assert _close(api.points(tri, world=True), [(0, 0, 0), (0, 200, 0), (0, 0, 50)], 1e-9)
        assert _close(local[0], [0, 5, 0], 1e-9)
        try:
            api.set_points(tri, np.zeros((2, 3)))
        except ScriptError:
            pass
        else:
            raise AssertionError("wrong point count accepted")
        try:
            api.create_polygon_object("Bad", [(0, 0, 0), (1, 0, 0)], [(0, 1, 2)])
        except ScriptError:
            pass
        else:
            raise AssertionError("bad polygon accepted")
        api.set_polygons(tri, [(0, 2, 1)])
        assert api.polygons(tri) == [(0, 2, 1)]
        api.set_mesh(tri, Mesh.cube(10.0))
        assert api.point_count(tri) == 8 and len(api.edges(tri)) == 12
        sphere = api.create("sphere")
        try:
            api.set_points(sphere, api.points(sphere))
        except ScriptError as exc:
            assert "make_editable" in str(exc)
        else:
            raise AssertionError("parametric points edited")


def test_api_hierarchy_world_preserved():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        null = api.create("null", name="Root", position=(100, 0, 0), rotation=(0, 90, 0))
        child = api.create("cube", name="Kid", position=(0, 0, 50))
        before = api.world_position(child)
        assert api.set_parent(child, null)
        assert api.parent(child) is null and api.children(null) == [child]
        assert _close(api.world_position(child), before, 1e-9)
        api.set_world_position(child, (0, 10, 0))
        assert _close(api.world_position(child), [0, 10, 0], 1e-9)
        assert api.descendants(null) == [child]
        assert api.set_parent(child, None)
        assert child in api.roots()
        api.move(child, (1, 2, 3))
        assert _close(api.world_position(child), [1, 12, 3], 1e-9)


def test_api_duplicate_delete_make_editable_keep_data():
    _fresh_home()
    sc = reset_scene()
    with api.bind_scene(sc):
        cube = api.create("cube", name="Src", size_x=30.0, position=(1, 2, 3))
        api.add_tag(cube, "note", text="hello")
        dup = api.duplicate(cube, name="Copy")
        assert dup.kind == "cube" and dup.params["size_x"] == 30.0
        assert _close(dup.position, [1, 2, 3])
        assert api.tags(dup)[0]["text"] == "hello"
        poly = api.make_editable(dup)
        assert poly.kind == "polygon" and api.point_count(poly) == 8
        assert api.find_tags(poly, "note")[0]["text"] == "hello"
        n = len(sc.objects)
        api.delete(poly)
        assert len(sc.objects) == n - 1 and api.find("Copy") is None


def test_api_selection_and_run_tool():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        cube = sc.objects[0]
        normals = api.polygon_normals(cube)
        top = int(np.argmax(normals[:, 1]))
        assert api.select_polygons([top], obj=cube) == 1
        assert api.mode() == "polygons" and api.selected_polygons() == [top]
        r = api.run_tool("extrude", {"offset": 50.0})
        assert isinstance(r, OpResult) and r.ok
        assert api.polygon_count(cube) == 10 and api.point_count(cube) == 12
        assert math.isclose(float(api.points(cube)[:, 1].max()), 150.0, abs_tol=1e-6)
        assert sc.can_undo()
        sc.undo()
        cube = sc.objects[0]
        assert api.polygon_count(cube) == 6
        r = api.run_tool("subdivide", {"subdivision": 1}, obj=cube, selection="model")
        assert r.ok and api.polygon_count(cube) == 24
        r = api.run_tool("triangulate", selection="all")
        assert r.ok and api.polygon_count(cube) == 48
        assert all(len(p) == 3 for p in api.polygons(cube))
        bad = api.run_tool("inset", selection={"mode": "points", "points": [0]})
        assert not bad.ok and api.polygon_count(cube) == 48
        try:
            api.run_tool("no_such_tool")
        except ScriptError:
            pass
        else:
            raise AssertionError("unknown tool accepted")
        info = api.tool_info("extrude")
        assert info["name"] and any(p["key"] == "offset" for p in info["params"])
        assert "bevel" in api.tool_ids()
        n = api.select_all("points")
        assert n == api.point_count(cube) and api.selected_points() == list(range(n))
        assert api.select_edges([cube.mesh.edges[0]]) == 1
        try:
            api.select_points([10_000])
        except ScriptError:
            pass
        else:
            raise AssertionError("invalid point accepted")
        api.set_mode("model")
        api.deselect()
        assert api.selected_objects() == []
        api.select(cube)
        assert api.selected_objects() == [cube]
        sel = api.all_selection(cube, "edges")
        assert len(sel.edges) == len(cube.mesh.edges)


def test_api_tags_materials():
    _fresh_home()
    sc = reset_scene()
    with api.bind_scene(sc):
        cube = sc.objects[0]
        t = api.add_tag(cube, "phong", angle=40.0)
        assert t["type"] == "phong" and t["name"] == "Phong" and t["enabled"] and t["angle"] == 40.0
        assert t["angle_limit"] is True
        try:
            api.add_tag(cube, "phong")
        except ScriptError as exc:
            assert "only have one" in str(exc)
        else:
            raise AssertionError("second unique tag accepted")
        try:
            api.add_tag(cube, "display", no_such_field=1)
        except ScriptError:
            pass
        else:
            raise AssertionError("unknown tag field accepted")
        api.add_tag(cube, "display", name="Show")
        assert [x["type"] for x in api.tags(cube)] == ["phong", "display"]
        assert store.get_object(cube, "tags")[0]["angle"] == 40.0
        assert api.update_tag(cube, 0, angle=60.0)["angle"] == 60.0
        assert api.update_tag(cube, 0, angle=500.0)["angle"] == 180.0
        note = api.add_tag(cube, "note", text="free form")
        assert note == {"type": "note", "name": "Note", "enabled": True, "text": "free form"}
        assert api.remove_tag(cube, "note") == 1
        assert api.remove_tag(cube, "display") == 1
        assert api.remove_tag(cube, 0) == 1
        assert api.tags(cube) == []
        red = api.add_material("Red", (1.0, 0.0, 0.0), roughness=0.3)
        again = api.add_material("Red", (2.0, -1.0, 0.5))
        mats = api.materials()
        assert len(mats) == 1 and again["id"] == red["id"]
        assert mats[0]["channels"]["base_color"]["value"] == [1.0, 0.0, 0.5]
        assert math.isclose(mats[0]["channels"]["roughness"]["value"], 0.3)
        api.assign_material(cube, "Red")
        assert api.material_of(cube)["name"] == "Red"
        try:
            api.assign_material(cube, "Missing")
        except ScriptError:
            pass
        else:
            raise AssertionError("missing material assigned")
        api.set_data(cube, "custom", {"a": np.arange(3)})
        got = api.get_data(cube, "custom")
        assert list(got["a"]) == [0, 1, 2]
        api.set_scene_data("answer", 42)
        assert api.get_scene_data("answer") == 42
        try:
            api.add_python_tag(cube, "def main(:\n")
        except SyntaxError:
            pass
        else:
            raise AssertionError("invalid python tag accepted")


def test_api_tracks_interpolation():
    _fresh_home()
    sc = reset_scene()
    with api.bind_scene(sc):
        cube = sc.objects[0]
        api.set_key(cube, "position.x", 0, 0.0, interpolation="linear")
        api.set_key(cube, "position.x", 10, 100.0)
        assert api.tracks(cube)["position.x"][1]["interp"] == "spline"
        api.set_key(cube, "position.y", 0, 0.0, interpolation="step")
        api.set_key(cube, "position.y", 10, 50.0)
        api.set_key(cube, "rotation.z", 0, 0.0, interpolation="smooth")
        api.set_key(cube, "rotation.z", 10, 90.0)
        assert math.isclose(api.track_value(cube, "position.x", 2.5), 25.0)
        assert math.isclose(api.track_value(cube, "position.x", -5), 0.0)
        assert math.isclose(api.track_value(cube, "position.x", 20), 100.0)
        assert math.isclose(api.track_value(cube, "position.y", 9.9), 0.0)
        assert math.isclose(api.track_value(cube, "position.y", 10), 50.0)
        t = 0.25
        assert math.isclose(api.track_value(cube, "rotation.z", 2.5), 90.0 * t * t * (3 - 2 * t))
        assert api.track_value(cube, "scale.x", 3) is None
        assert api.apply_tracks(cube, 5) == 3
        assert _close(cube.position, [50.0, 0.0, 0.0])
        assert math.isclose(cube.rotation[2], 45.0)
        api.set_key(cube, "position.x", 10, 200.0)
        assert len(api.tracks(cube)["position.x"]) == 2
        assert api.track_channels(cube) == ["position.x", "position.y", "rotation.z"]
        assert math.isclose(api.track_value(cube, "position.x", 5), 100.0)
        assert api.remove_key(cube, "position.x", 10)
        assert not api.remove_key(cube, "position.x", 99)
        try:
            api.set_key(cube, "color.r", 0, 1.0)
        except ScriptError:
            pass
        else:
            raise AssertionError("bad target accepted")
        sph = api.create("sphere")
        api.set_key(sph, "param.radius", 0, 10.0)
        api.set_key(sph, "param.radius", 4, 50.0)
        api.apply_tracks(sph, 2)
        assert math.isclose(sph.params["radius"], 30.0)
        api.set_frame(12)
        assert api.current_frame() == 12.0
        assert store.get_scene_data(sc, "anim")["frame"] == 12
        api.set_key(cube, "position.z", value=7.0)
        assert api.tracks(cube)["position.z"][0]["frame"] == 12
        assert api.clear_tracks(cube, "position.z") == 1 and "position.z" not in api.tracks(cube)


def test_api_undo_group_suppress_and_messages():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        n = len(sc.objects)
        with api.undo_group():
            api.create("cube")
            api.create("cube")
        assert len(sc.objects) == n + 2
        api.undo()
        assert len(sc.objects) == n
        api.redo()
        assert len(sc.objects) == n + 2
        depth = len(sc._undo)
        with api.suppress_undo():
            api.set_position(sc.objects[0], (9, 9, 9))
        assert len(sc._undo) == depth
        api.set_position(sc.objects[0], (1, 1, 1))
        assert len(sc._undo) == depth + 1
        got = []
        api.add_message_listener(got.append)
        api.message("a", 1)
        api.remove_message_listener(got.append)
        api.message("b")
        assert got == ["a 1"]
        assert api.log_lines(1)[-1] == ("message", "b")
        hits = []
        sc.objectsChanged.connect(lambda: hits.append(1))
        api.refresh()
        assert hits


def test_api_lazy_types():
    assert api.Selection.__name__ == "Selection"
    assert api.ToolSpec is mreg.ToolSpec and api.ObjectSpec is oreg.ObjectSpec
    assert api.ObjectParam is oreg.Param and api.ToolParam is mreg.Param
    try:
        api.not_a_thing
    except AttributeError:
        pass
    else:
        raise AssertionError("missing attribute resolved")
    import quartz
    assert quartz is api


def test_python_tags_run_per_frame():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        cube = sc.objects[0]
        api.add_python_tag(cube, "op.position = np.array([frame * 10.0, 0.0, 0.0])\n")
        api.add_python_tag(cube, "def main():\n    print('frame', frame, op.name, tag['name'])\n",
                           name="Printer")
        api.add_python_tag(cube, "raise ValueError('bad tag')\n", name="Broken")
        api.add_tag(cube, "python", name="Off", code="op.scale = np.array([5.0, 5.0, 5.0])",
                    enabled=False)
        depth = len(sc._undo)
        results = scripting.run_python_tags(sc, 3)
        assert len(results) == 3
        assert _close(cube.position, [30.0, 0.0, 0.0])
        assert results[1].ok and results[1].output == "frame 3.0 Cube Printer\n"
        assert not results[2].ok and "bad tag" in results[2].error and "ValueError" in results[2].error
        assert _close(cube.scale, [1, 1, 1])
        assert len(sc._undo) == depth
        api.set_scene_data("frame", 7)
        results = scripting.run_python_tags(sc)
        assert _close(cube.position, [70.0, 0.0, 0.0])


def test_custom_tag_types_and_frame_driver():
    _fresh_home()
    sc = _scene()
    calls = []

    def spin(op, tag, doc, frame):
        calls.append((op.name, tag["speed"], frame))
        op.rotation = np.array([0.0, frame * tag["speed"], 0.0])

    scripting.register_tag_type("spin", "Spin", {"speed": 2.0}, spin, owner="test")
    try:
        with api.bind_scene(sc):
            cube = sc.objects[0]
            api.add_tag(cube, "spin")
            assert scripting.run_python_tags(sc, 4) == []
            res = scripting.run_tags(sc, 4)
            assert len(res) == 1 and res[0].ok and math.isclose(cube.rotation[1], 8.0)
            api.update_tag(cube, 0, speed=3.0)
            driver = pytags.FrameDriver(sc, deferred=False)
            try:
                store.set_scene_data(sc, "frame", 10)
                assert driver.runs == 1 and math.isclose(cube.rotation[1], 30.0)
                driver.enabled = False
                store.set_scene_data(sc, "frame", 11)
                assert driver.runs == 1
            finally:
                driver.uninstall()
            store.set_scene_data(sc, "frame", 12)
            assert driver.runs == 1
        assert "spin" in {t.id for t in scripting.tag_types()}
        assert "python" in {t.id for t in scripting.tag_types()}
        assert not scripting.unregister_tag_type("python")
    finally:
        scripting.unregister_tag_type("spin")
    assert "spin" not in pytags.TAG_TYPES


PLUGIN_COMMAND = '''
PLUGIN = {"name": "Counter", "type": "command", "version": "2.1", "description": "counts"}
COUNT = [0]


def register(api):
    def bump():
        COUNT[0] += 1
        return COUNT[0]
    api.register_command("Bump", bump, shortcut="Ctrl+Alt+B")
    api.register_command("Fail", lambda: 1 / 0, menu=("Debug",))
'''

PLUGIN_RUN = '''
PLUGIN = {"name": "Runner", "type": "command"}


def register(api):
    pass


def run(api):
    return api.API_VERSION
'''

PLUGIN_OBJECT = '''
PLUGIN = {"name": "Wedge Maker", "type": "object"}


def build(params, inputs):
    from quartz_studio.scene import Mesh
    s = params["size"]
    return Mesh([(0, 0, 0), (s, 0, 0), (0, s, 0), (0, 0, s)], [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)])


def register(api):
    api.register_object(id="test_wedge", label="Wedge", build=build, category="mesh",
                        params=(api.ObjectParam("size", "Size", "distance", 100.0, 0.0),))
'''

PLUGIN_TOOL = '''
PLUGIN = {"name": "Lift Tool", "type": "tool"}


def lift(mesh, sel, params):
    from quartz_studio.modeling.meshkit import OpResult, clone
    out = clone(mesh)
    out.points[:, 1] += params["height"]
    return OpResult(out, sel)


def register(api):
    api.register_tool(id="test_lift", name="Lift", apply=lift, modes=("points", "edges", "polygons", "model"),
                      params=(api.ToolParam("height", "Height", "distance", 10.0),), menu="Mesh")
'''

PLUGIN_TAG = '''
PLUGIN = {"name": "Bounce Tag", "type": "tag"}


def bounce(op, tag, doc, frame):
    import math
    op.position = op.position * 0 + [0.0, abs(math.sin(frame)) * tag["height"], 0.0]


def register(api):
    api.register_tag("test_bounce", "Bounce", {"height": 100.0}, bounce)
'''

PLUGIN_BROKEN = '''
PLUGIN = {"name": "Broken", "type": "command"}


def register(api):
    raise RuntimeError("cannot start")
'''

PLUGIN_NO_META = '''
def register(api):
    pass
'''


def _install_test_plugins(home: Path) -> None:
    _write_plugin(home, "counter", PLUGIN_COMMAND)
    _write_plugin(home, "runner", PLUGIN_RUN)
    _write_plugin(home, "wedge", PLUGIN_OBJECT)
    _write_plugin(home, "lift", PLUGIN_TOOL)
    _write_plugin(home, "bounce", PLUGIN_TAG)
    _write_plugin(home, "broken", PLUGIN_BROKEN)
    _write_plugin(home, "nometa", PLUGIN_NO_META)
    _write_plugin(home, "_private", PLUGIN_BROKEN)


def test_plugin_loader_all_types():
    home = _fresh_home()
    _install_test_plugins(home)
    loader = scripting.get_loader()
    records = loader.load_all()
    assert [r.stem for r in records] == ["bounce", "broken", "counter", "lift", "nometa", "runner", "wedge"]
    errors = loader.errors()
    assert set(errors) == {"broken", "nometa"}
    assert "cannot start" in errors["broken"] and "PLUGIN" in errors["nometa"]
    counter = loader.get("counter")
    assert counter.name == "Counter" and counter.version == "2.1" and counter.type == "command"
    assert "test_wedge" in oreg.SPECS and "test_lift" in mreg.TOOLS and "test_bounce" in pytags.TAG_TYPES
    cmds = dict(loader.commands())
    assert ("Extensions", "Bump") in cmds and ("Extensions", "Debug", "Fail") in cmds
    assert ("Extensions", "Runner") in cmds
    assert cmds[("Extensions", "Bump")]() == 1
    assert loader.run_command("Bump") == 2
    assert cmds[("Extensions", "Runner")]() == api.API_VERSION
    got = []
    api.add_message_listener(got.append)
    try:
        assert cmds[("Extensions", "Debug", "Fail")]() is None
    finally:
        api.remove_message_listener(got.append)
    assert got and "ZeroDivisionError" in got[0] and "ZeroDivisionError" in counter.error
    assert [k for k, _f, _l in loader.shortcuts()] == ["Ctrl+Alt+B"]
    sc = _scene()
    with api.bind_scene(sc):
        wedge = api.create("test_wedge", size=50.0)
        assert api.point_count(wedge) == 4 and math.isclose(api.bounds(wedge, world=False)[1][0], 50.0)
        cube = sc.objects[0]
        before = api.points(cube)
        r = api.run_tool("test_lift", {"height": 25.0}, obj=cube, selection="model")
        assert r.ok and _close(api.points(cube), before + [0, 25.0, 0])
        api.add_tag(cube, "test_bounce", height=10.0)
        scripting.run_tags(sc, math.pi / 2)
        assert _close(cube.position, [0, 10.0, 0])


def test_plugin_enable_disable_persist_and_reload():
    home = _fresh_home()
    _install_test_plugins(home)
    loader = scripting.get_loader()
    loader.load_all()
    events = []
    loader.add_listener(lambda: events.append(1))
    assert loader.set_enabled("wedge", False)
    assert "test_wedge" not in oreg.SPECS
    state = json.loads((home / "plugins.json").read_text(encoding="utf-8"))
    assert state["disabled"] == ["wedge"]
    assert events
    fresh = PluginLoader()
    fresh_records = {r.stem: r for r in fresh.load_all()}
    assert not fresh_records["wedge"].enabled and not fresh_records["wedge"].loaded
    assert fresh_records["wedge"].name == "Wedge Maker"
    for rec in fresh_records.values():
        if rec.loaded:
            fresh._unregister(rec)
    loader.load_all()
    assert "test_wedge" not in oreg.SPECS
    assert loader.set_enabled("wedge", True)
    assert "test_wedge" in oreg.SPECS
    state = json.loads((home / "plugins.json").read_text(encoding="utf-8"))
    assert state["disabled"] == []
    path = home / "plugins" / "counter.py"
    path.write_text(PLUGIN_COMMAND.replace('"Bump"', '"Bump Again"'), encoding="utf-8")
    assert loader.reload_one("counter")
    labels = [p[-1] for p, _f in loader.commands()]
    assert "Bump Again" in labels and "Bump" not in labels
    loader.set_enabled("lift", False)
    assert "test_lift" not in mreg.TOOLS
    loader.set_enabled("bounce", False)
    assert "test_bounce" not in pytags.TAG_TYPES
    scripting.reset_loader()
    assert "test_wedge" not in oreg.SPECS


def test_examples_install_and_run():
    home = _fresh_home()
    written = examples.install_examples()
    assert len(written) == 4
    assert examples.install_examples() == []
    (home / "scripts" / "Scene Report.py").write_text("print('mine')\n", encoding="utf-8")
    assert examples.install_examples() == []
    assert (home / "scripts" / "Scene Report.py").read_text(encoding="utf-8") == "print('mine')\n"
    assert len(examples.install_examples(overwrite=True)) == 4
    for text in list(examples.EXAMPLE_SCRIPTS.values()) + list(examples.EXAMPLE_PLUGINS.values()):
        assert "#" not in text
        compile(text, "example", "exec")
    sc = reset_scene()
    lib = ScriptLibrary()
    r = lib.run("Ring Of Cubes", sc)
    assert r.ok, r.error
    ring = api.find("Cube Ring", sc)
    kids = sc.children(ring)
    assert len(kids) == 8
    radii = [float(np.hypot(k.position[0], k.position[2])) for k in kids]
    assert _close(radii, [400.0] * 8, 1e-9)
    assert all(_close(k.mesh.size(), [80.0, 80.0, 80.0]) for k in kids)
    sc.set_active(sc.objects[0])
    r = lib.run("Extrude Upward Faces", sc)
    assert r.ok, r.error
    assert api.polygon_count(sc.objects[0], scene=sc) == 10
    r = lib.run("Scene Report", sc)
    assert r.ok and "Cube Ring" in r.stdout and "10 objects" in r.stdout
    loader = scripting.get_loader()
    loader.load_all()
    cmds = dict(loader.commands())
    cube = sc.objects[0]
    api.set_position(cube, (0, 500, 0), scene=sc)
    sc.set_active(cube)
    cmds[("Extensions", "Drop To Floor")]()
    assert math.isclose(float(api.points(cube, world=True, scene=sc)[:, 1].min()), 0.0, abs_tol=1e-9)
    before = api.points(cube, scene=sc)
    cmds[("Extensions", "Jitter Points")]()
    after = api.points(cube, scene=sc)
    assert after.shape == before.shape and not np.allclose(after, before)
    assert float(np.abs(after - before).max()) <= 0.02 * float(np.max(np.ptp(before, axis=0))) + 1e-9


def test_package_commands_docks_pages_keys():
    home = _fresh_home()
    examples.install_examples()
    ScriptLibrary().set_shortcut("Scene Report", "Ctrl+Alt+R")
    cmds = scripting.commands()
    paths_ = [p for p, _f in cmds]
    for title in ("Script Manager", "Console", "Plugin Manager", "Reload Plugins"):
        assert ("Extensions", title) in paths_
    for name in ("Ring Of Cubes", "Extrude Upward Faces", "Scene Report"):
        assert ("Extensions", "Scripts", name) in paths_
    assert ("Extensions", "Drop To Floor") in paths_
    assert all(callable(f) for _p, f in cmds)
    assert len(paths_) == len(set(paths_))
    docks = scripting.docks()
    assert [d[0] for d in docks] == ["Script Manager", "Console", "Plugin Manager"]
    assert all(area in ("left", "right", "bottom") for _t, _f, area in docks)
    assert scripting.pages() == [("Script", ["Script Manager", "Console"])]
    keys = scripting.key_actions()
    assert ("Ctrl+Alt+R" in [k for k, _f, _l in keys]) and ("Ctrl+Alt+B" not in [k for k, _f, _l in keys])
    reset_scene()
    fn = dict((p, f) for p, f in cmds)[("Extensions", "Scripts", "Scene Report")]
    result = fn()
    assert result.ok
    records = dict(cmds)[("Extensions", "Reload Plugins")]()
    assert [r.stem for r in records] == ["example_tools"]
    assert scripting.open_scripts_folder(launch=False) == str(home / "scripts")
    sc = reset_scene()
    api.add_python_tag(sc.objects[0], "op.position = np.array([1.0, 2.0, 3.0])", scene=sc)
    res = dict(cmds)[("Extensions", "Run Python Tags")]()
    assert len(res) == 1 and _close(sc.objects[0].position, [1, 2, 3])
    driver = scripting.install_frame_driver(sc)
    try:
        assert scripting.install_frame_driver(sc) is driver
    finally:
        driver.uninstall()


def test_docks_build_widgets():
    _fresh_home()
    sc = _scene()
    for title, factory, _area in scripting.docks():
        w = factory(sc)
        assert w.scene is sc
        w.resize(768, 512)
        w.show()
        APP.processEvents()
        w.close()
        w.deleteLater()
    APP.processEvents()


def test_highlighter_formats():
    from PySide6.QtGui import QTextDocument
    doc = QTextDocument()
    hl = PythonHighlighter(doc)
    doc.setPlainText("def run(x):\n    s = 'text'  # note\n    return 42 + quartz.x\n\"\"\"open\nstill\n\"\"\" + 1\n")
    hl.rehighlight()

    def color_at(block_no: int, col: int):
        block = doc.findBlockByNumber(block_no)
        for fr in block.layout().formats():
            if fr.start <= col < fr.start + fr.length:
                return fr.format.foreground().color().name()
        return None

    assert color_at(0, 0) == QColor(COLORS["keyword"]).name()
    assert color_at(0, 4) == QColor(COLORS["definition"]).name()
    assert color_at(1, 9) == QColor(COLORS["string"]).name()
    assert color_at(1, 18) == QColor(COLORS["comment"]).name()
    assert color_at(2, 11) == QColor(COLORS["number"]).name()
    assert color_at(2, 16) == QColor(COLORS["api"]).name()
    assert color_at(4, 1) == QColor(COLORS["string"]).name()
    assert color_at(5, 1) == QColor(COLORS["string"]).name()
    assert color_at(5, 6) == QColor(COLORS["number"]).name()
    assert doc.findBlockByNumber(4).userState() == PythonHighlighter.STATE_TRIPLE_DOUBLE


def test_console_widget_execute_and_keys():
    _fresh_home()
    sc = _scene()
    con = ScriptConsole(sc)
    con.resize(768, 512)
    con.show()
    APP.processEvents()
    r = con.execute("1 + 2")
    assert r.ok and "3\n" in con.text() and ">>> 1 + 2" in con.text()
    con.input.setFocus()
    QTest.keyClicks(con.input, "value = op.name")
    QTest.keyClick(con.input, Qt.Key.Key_Return)
    assert con.namespace["value"] == "Cube" and con.input.toPlainText() == ""
    QTest.keyClicks(con.input, "for i in range(2):")
    QTest.keyClick(con.input, Qt.Key.Key_Return)
    assert con.input.toPlainText() == "for i in range(2):\n    "
    QTest.keyClicks(con.input, "print('row', i)")
    QTest.keyClick(con.input, Qt.Key.Key_Return)
    assert "\n    print('row', i)\n" in con.input.toPlainText()
    QTest.keyClick(con.input, Qt.Key.Key_Return)
    assert "row 0\nrow 1\n" in con.text() and con.input.toPlainText() == ""
    QTest.keyClicks(con.input, "a = 5")
    QTest.keyClick(con.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClicks(con.input, "b = a * 3")
    assert con.input.toPlainText() == "a = 5\nb = a * 3"
    QTest.keyClick(con.input, Qt.Key.Key_Return)
    assert con.namespace["b"] == 15
    QTest.keyClick(con.input, Qt.Key.Key_Up)
    assert con.input.toPlainText() == "a = 5\nb = a * 3"
    con.input.moveCursor(con.input.textCursor().MoveOperation.Start)
    QTest.keyClick(con.input, Qt.Key.Key_Up)
    assert con.input.toPlainText().startswith("for i in range(2):")
    QTest.keyClick(con.input, Qt.Key.Key_Down)
    assert con.input.toPlainText() == "a = 5\nb = a * 3"
    QTest.keyClick(con.input, Qt.Key.Key_Down)
    assert con.input.toPlainText() == ""
    QTest.keyClicks(con.input, "x = 1")
    QTest.keyClick(con.input, Qt.Key.Key_Escape)
    assert con.input.toPlainText() == ""
    QTest.keyClicks(con.input, "missing_name")
    QTest.mouseClick(con.run_button, Qt.MouseButton.LeftButton)
    assert "NameError" in con.text() and con.status.text() == "Error"
    n = len(sc.objects)
    con.execute("quartz.create('cube'); quartz.create('cube')")
    assert len(sc.objects) == n + 2
    sc.undo()
    assert len(sc.objects) == n
    api.message("from elsewhere")
    assert "from elsewhere" in con.text()
    saved = paths.read_settings()["console_history"]
    assert "a = 5\nb = a * 3" in saved and "missing_name" in saved
    con2 = ScriptConsole(sc)
    assert con2.input.history == con.input.history
    QTest.mouseClick(con.reset_button, Qt.MouseButton.LeftButton)
    assert "b" not in con.namespace and con.namespace["doc"] is sc
    QTest.mouseClick(con.clear_button, Qt.MouseButton.LeftButton)
    assert con.text() == ""
    sc.set_active(None)
    con.execute("op")
    assert con.namespace["op"] is None
    con.close()
    con2.close()


def test_console_input_tab_and_fit():
    inp = ConsoleInput()
    inp.show()
    h1 = inp.height()
    QTest.keyClick(inp, Qt.Key.Key_Tab)
    assert inp.toPlainText() == "    "
    for _ in range(4):
        QTest.keyClick(inp, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert inp.height() > h1
    seen = []
    inp.submitted.connect(seen.append)
    QTest.keyClick(inp, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert len(seen) == 1
    inp.close()


def test_script_manager_widget_flow():
    home = _fresh_home()
    sc = _scene()
    man = ScriptManager(sc)
    man.resize(1024, 512)
    man.show()
    APP.processEvents()
    assert man.names() == [] and not man.editor.isEnabled()
    QTest.mouseClick(man.new_button, Qt.MouseButton.LeftButton)
    assert man.current == "Untitled.py" and (home / "scripts" / "Untitled.py").is_file()
    assert man.editor.isEnabled() and "def main" in man.editor.toPlainText()
    man.editor.setPlainText("print('size', quartz.point_count(op))\nquartz.create('cube', name='Made')\n")
    assert man.is_dirty() and man.list.currentItem().text().startswith("Untitled *")
    QTest.mouseClick(man.run_button, Qt.MouseButton.LeftButton)
    assert man.last_result.ok and "size 8" in man.output.toPlainText()
    assert api.find("Made", sc) is not None
    assert "Untitled.py" in man.status.text()
    man.editor.setFocus()
    QTest.keyClick(man.editor, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert not man.is_dirty()
    assert (home / "scripts" / "Untitled.py").read_text(encoding="utf-8").startswith("print('size'")
    man.name_edit.setText("Maker")
    man.name_edit.editingFinished.emit()
    assert man.current == "Maker.py" and man.names() == ["Maker.py"]
    assert man.set_shortcut("Ctrl+Shift+M") == "Ctrl+Shift+M"
    assert ScriptLibrary().shortcut("Maker") == "Ctrl+Shift+M"
    assert set(man.binder.shortcuts) == {"Maker.py"}
    assert "Ctrl+Shift+M" in man.list.currentItem().text()
    n = len(sc.objects)
    with api.bind_scene(sc):
        QTest.keyClick(man.list, Qt.Key.Key_M,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert len(sc.objects) == n + 1 and man.last_result.ok
    assert man.run_shortcut("Ctrl+Shift+X") is None
    QTest.mouseClick(man.clear_shortcut_button, Qt.MouseButton.LeftButton)
    assert ScriptLibrary().shortcut("Maker") == "" and man.binder.shortcuts == {}
    second = man.new_script("Second", "x = 1\n")
    assert man.current == second
    man.editor.setPlainText("x = 2\n")
    man.select("Maker")
    assert man.editor.toPlainText().startswith("print('size'")
    man.select("Second")
    assert man.editor.toPlainText() == "x = 2\n" and man.is_dirty()
    man.editor.moveCursor(man.editor.textCursor().MoveOperation.End)
    QTest.keyClicks(man.editor, "if x:")
    QTest.keyClick(man.editor, Qt.Key.Key_Return)
    QTest.keyClicks(man.editor, "y = x")
    assert man.editor.toPlainText().endswith("if x:\n    y = x")
    man.editor.selectAll()
    QTest.keyClick(man.editor, Qt.Key.Key_Backtab)
    assert man.editor.toPlainText().endswith("if x:\ny = x")
    man.editor.selectAll()
    QTest.keyClick(man.editor, Qt.Key.Key_Tab)
    assert man.editor.toPlainText().startswith("    x = 2")
    man.editor.setPlainText("raise RuntimeError('nope')\n")
    QTest.keyClick(man.editor, Qt.Key.Key_F5)
    assert not man.last_result.ok and "nope" in man.output.toPlainText()
    assert "RuntimeError" in man.status.text()
    ext = home / "external.py"
    ext.write_text("print('external')\n", encoding="utf-8")
    assert man.open_file(ext) == "external.py" and man.current == "external.py"
    assert man.editor.toPlainText() == "print('external')\n"
    assert man.delete_current(confirm=False)
    assert "external.py" not in man.names() and man.current is not None
    QTest.mouseClick(man.examples_button, Qt.MouseButton.LeftButton)
    assert {"Ring Of Cubes.py", "Scene Report.py", "Extrude Upward Faces.py"} <= set(man.names())
    assert (home / "plugins" / "example_tools.py").is_file()
    assert man.rename_current("Scene Report") is None
    man.close()


def test_plugin_manager_widget_flow():
    home = _fresh_home()
    _install_test_plugins(home)
    sc = _scene()
    panel = PluginManager(sc)
    panel.resize(768, 512)
    panel.show()
    APP.processEvents()
    assert panel.stems() == ["bounce", "broken", "counter", "lift", "nometa", "runner", "wedge"]
    assert "with errors" in panel.status.text()
    row = panel.stems().index("broken")
    assert panel.list.item(row).foreground().color().name() == QColor(scripting_theme().STATUS_ERROR).name()
    panel.list.setCurrentRow(panel.stems().index("counter"))
    assert "Counter" in panel.details.toPlainText() and "Extensions > Bump" in panel.details.toPlainText()
    assert panel.command_combo.count() == 2 and panel.run_command_button.isEnabled()
    panel.command_combo.setCurrentIndex(0)
    QTest.mouseClick(panel.run_command_button, Qt.MouseButton.LeftButton)
    assert "Ran" in panel.status.text()
    mod = panel.loader.get("counter").module
    assert mod.COUNT[0] == 1
    item = panel.list.item(panel.stems().index("wedge"))
    item.setCheckState(Qt.CheckState.Unchecked)
    assert not panel.loader.get("wedge").enabled and "test_wedge" not in oreg.SPECS
    assert panel.list.item(panel.stems().index("wedge")).checkState() == Qt.CheckState.Unchecked
    panel.list.item(panel.stems().index("wedge")).setCheckState(Qt.CheckState.Checked)
    assert "test_wedge" in oreg.SPECS
    panel.list.setCurrentRow(panel.stems().index("lift"))
    QTest.mouseClick(panel.reload_one_button, Qt.MouseButton.LeftButton)
    assert "Reloaded lift" in panel.status.text() and "test_lift" in mreg.TOOLS
    _write_plugin(home, "late", PLUGIN_RUN.replace("Runner", "Late"))
    QTest.mouseClick(panel.reload_button, Qt.MouseButton.LeftButton)
    assert "late" in panel.stems()
    assert panel.open_folder(launch=False) == str(home / "plugins")
    assert panel.opened_urls and panel.opened_urls[-1].startswith("file:")
    written = panel.install_examples()
    assert len(written) == 4 and "example_tools" in panel.stems()
    panel.close()
    scripting.reset_loader()


def scripting_theme():
    from quartz_studio import theme
    return theme


def test_show_panel_dock_and_window():
    _fresh_home()
    w = scripting.show_panel("Console")
    assert isinstance(w, ScriptConsole) and w.isVisible() and w.windowTitle() == "Console"
    assert scripting.show_panel("Console") is w
    w.close()
    win = QMainWindow()
    dock = QDockWidget("Plugin Manager", win)
    dock.setWidget(QLabel("x"))
    win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    win.show()
    dock.hide()
    APP.processEvents()
    got = scripting.show_panel("Plugin Manager")
    assert got is dock and dock.isVisible()
    try:
        scripting.show_panel("Nope")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown panel opened")
    win.close()
    win.deleteLater()
    APP.processEvents()


def test_regression_tracks_share_anim_format():
    from quartz_studio.anim import core as acore
    _fresh_home()
    sc = reset_scene()
    cube = sc.objects[0]
    cube.position = np.array([3.0, 0.0, 0.0])
    acore.set_key(cube, ["position.x"], 0, scene=sc)
    cube.position = np.array([13.0, 0.0, 0.0])
    acore.set_key(cube, ["position.x"], 10, scene=sc)
    assert set(api.tracks(cube, scene=sc)) == {"position.x"}
    api.set_key(cube, "position.y", 10, 5.0, scene=sc)
    raw = store.get_object(cube, "tracks")
    assert isinstance(raw, dict) and set(raw) == {"position.x", "position.y"}
    assert set(acore.tracks(cube)) == {"position.x", "position.y"}
    assert len(acore.get_track(cube, "position.x")) == 2
    for f in (0.0, 2.5, 5.0, 7.5, 10.0, 14.0):
        assert math.isclose(api.track_value(cube, "position.x", f, scene=sc),
                            float(acore.evaluate_channel(cube, "position.x", f)), abs_tol=1e-12)
    acore.set_loop(cube, "position.x", after="repeat")
    assert math.isclose(api.track_value(cube, "position.x", 12.5, scene=sc),
                        float(acore.evaluate_channel(cube, "position.x", 12.5)), abs_tol=1e-12)
    assert api.remove_key(cube, "position.x", 10, scene=sc)
    assert len(acore.get_track(cube, "position.x")) == 1
    api.clear_tracks(cube, "position.x", scene=sc)
    assert "position.x" not in acore.track_modes(cube)
    sph = api.create("sphere", scene=sc)
    api.set_key(sph, "param.radius", 0, 10.0, interpolation="linear", scene=sc)
    api.set_key(sph, "param.radius", 4, 50.0, scene=sc)
    acore.evaluate(sc, 2)
    assert math.isclose(sph.params["radius"], 30.0)
    poly = api.create_polygon_object("Tri", [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)], scene=sc)
    api.set_key(poly, "points", 0, scene=sc)
    api.set_key(poly, "points", 10, api.points(poly, scene=sc) * 3.0, scene=sc)
    assert _close(api.track_value(poly, "points", 5, scene=sc)[1], [2.0, 0.0, 0.0])
    assert api.apply_tracks(poly, 10, scene=sc) == 1
    assert _close(poly.mesh.points[1], [3.0, 0.0, 0.0])
    api.set_key(cube, "visibility", 0, 1.0, scene=sc)
    api.set_key(cube, "visibility", 5, 0.0, scene=sc)
    assert api.tracks(cube, scene=sc)["visibility"][0]["interp"] == "step"
    legacy = reset_scene()
    lcube = legacy.objects[0]
    store.set_object(lcube, "tracks", [{"target": "position.x", "keys": [
        {"frame": 0, "value": 0.0, "interpolation": "linear"},
        {"frame": 10, "value": 100.0, "interpolation": "linear"}]}])
    assert math.isclose(api.track_value(lcube, "position.x", 5, scene=legacy), 50.0)
    api.set_key(lcube, "position.y", 0, 1.0, scene=legacy)
    assert set(acore.tracks(lcube)) == {"position.x", "position.y"}


def test_regression_frame_follows_anim_and_driver_runs_tags():
    from quartz_studio.anim import core as acore
    _fresh_home()
    sc = _scene()
    cube = sc.objects[0]
    with api.bind_scene(sc):
        api.set_key(cube, "position.x", 0, 0.0, interpolation="linear")
        api.set_key(cube, "position.x", 30, 300.0, interpolation="linear")
        api.add_python_tag(cube, "def main(op, frame):\n    op.position[1] = op.position[0] * 2.0\n")
    driver = scripting.install_frame_driver(sc)
    try:
        assert driver.deferred
        acore.set_frame(sc, 20)
        assert api.current_frame(sc) == 20.0
        APP.processEvents()
        assert driver.runs == 1 and driver.last_results[0].ok, driver.last_results
        assert _close(cube.position, [200.0, 400.0, 0.0])
        acore.set_time_settings(sc, fps=24)
        APP.processEvents()
        assert driver.runs == 1
        depth = len(sc._undo)
        api.set_frame(10, scene=sc)
        APP.processEvents()
        assert len(sc._undo) == depth
        assert driver.runs == 2 and _close(cube.position, [100.0, 200.0, 0.0])
        assert api.set_frame(500, scene=sc) == 90
    finally:
        driver.uninstall()
    glob = scripting.install_frame_driver()
    assert glob.follow_global and scripting.frame_driver() is glob
    first = reset_scene()
    api.add_python_tag(first.objects[0], "op.scale = np.array([2.0, 2.0, 2.0])", scene=first)
    acore.set_frame(first, 5)
    APP.processEvents()
    assert _close(first.objects[0].scale, [2, 2, 2])
    assert scripting.set_tags_on_frame_change(False) is False
    second = reset_scene()
    api.add_python_tag(second.objects[0], "op.scale = np.array([3.0, 3.0, 3.0])", scene=second)
    acore.set_frame(second, 6)
    APP.processEvents()
    assert _close(second.objects[0].scale, [1, 1, 1])
    assert scripting.set_tags_on_frame_change() is True
    acore.set_frame(second, 7)
    APP.processEvents()
    assert _close(second.objects[0].scale, [3, 3, 3])
    glob.uninstall()


def test_regression_python_tag_main_signature_and_priority():
    _fresh_home()
    sc = _scene()
    order = []
    with api.bind_scene(sc):
        cube = sc.objects[0]
        api.add_tag(cube, "python", name="Template")
        api.add_python_tag(cube, "order.append('late')", name="Late", priority="Generators")
        api.add_python_tag(cube, "order.append('early')", name="Early", priority="Initial")
        api.add_python_tag(cube, "def main(op, frame, doc, tag):\n    order.append((op.name, frame, doc is not None, tag['name']))\n",
                           name="Full")
        api.add_python_tag(cube, "def main(missing):\n    pass\n", name="Bad")
    import builtins
    builtins.order = order
    try:
        results = scripting.run_python_tags(sc, 2)
    finally:
        del builtins.order
    names = [r.tag_name for r in results]
    assert names[0] == "Early" and names[-1] == "Late"
    assert all(r.ok for r in results if r.tag_name != "Bad")
    bad = next(r for r in results if r.tag_name == "Bad")
    assert not bad.ok and "missing" in bad.error
    assert order[0] == "early" and order[-1] == "late"
    assert ("Cube", 2.0, True, "Full") in order


def test_regression_tag_plugin_reaches_tags_registry():
    from quartz_studio.tags import core as tcore
    from quartz_studio.tags import registry as treg
    home = _fresh_home()
    _write_plugin(home, "bouncer", '''
PLUGIN = {"name": "Bouncer", "type": "tag"}


def run(op, tag, doc, frame):
    op.position = op.position * 0 + [0.0, tag["amp"] * frame, 0.0]


def register(api):
    api.register_tag("bouncer", "Bouncer", {"amp": 1.0, "label": "x", "on": True, "count": 2,
                                           "offset": [0.0, 1.0, 2.0]}, run)
''')
    _write_plugin(home, "steal", '''
PLUGIN = {"name": "Steal", "type": "tag"}


def register(api):
    api.register_tag("phong", "Fake Phong", {}, lambda *a: None)
''')
    loader = scripting.get_loader()
    loader.load_all()
    try:
        spec = treg.TAG_SPECS.get("bouncer")
        assert spec is not None and spec.label == "Bouncer" and spec.category == "Programming Tags"
        kinds = {p.key: p.kind for p in spec.params}
        assert kinds == {"amp": "float", "label": "text", "on": "bool", "count": "int", "offset": "vector"}
        assert "steal" in loader.errors() and treg.TAG_SPECS["phong"].label == "Phong"
        sc = _scene()
        cube = sc.objects[0]
        tcore.add_tag(cube, "bouncer", scene=sc)
        assert tcore.tags_of(cube)[0]["amp"] == 1.0
        res = scripting.run_tags(sc, 4)
        assert len(res) == 1 and res[0].ok and _close(cube.position, [0, 4.0, 0])
        loader.set_enabled("bouncer", False)
        assert "bouncer" not in treg.TAG_SPECS and "bouncer" not in pytags.TAG_TYPES
        loader.set_enabled("bouncer", True)
        assert "bouncer" in treg.TAG_SPECS
    finally:
        scripting.reset_loader()
    assert "bouncer" not in treg.TAG_SPECS and "phong" in treg.TAG_SPECS


def test_regression_materials_use_ids():
    from quartz_studio.materials import model as mmodel
    from quartz_studio.materials import tags as mtags
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        cube = sc.objects[0]
        red = mmodel.create_material(sc, name="Red")
        mtags.apply_material(cube, red["id"], selection="Top")
        tag = api.assign_material(cube, "Red")
        assert tag["material"] == red["id"]
        found = [mmodel.find_material(sc, t["material"]) for t in mtags.material_tags(cube)]
        assert all(m is not None for m in found) and len(found) == 2
        assert {t["selection"] for t in mtags.material_tags(cube)} == {"", "Top"}
        assert mtags.effective_material_id(sc, cube) == red["id"]
        blue = api.add_material("Blue", (0.0, 0.0, 1.0), roughness=0.2, emission={"strength": 3.0})
        assert blue["id"] and mmodel.find_material(sc, blue["id"])["name"] == "Blue"
        assert blue["channels"]["emission"]["enabled"] and blue["channels"]["emission"]["strength"] == 3.0
        api.assign_material(cube, blue["id"])
        assert len(mtags.material_tags(cube)) == 2
        assert api.material_of(cube)["name"] == "Blue"
        assert api.find_material("blue")["id"] == blue["id"]
        gold = api.add_material("Shiny", preset="gold")
        assert gold["channels"]["metallic"]["value"] == 1.0
        try:
            api.add_material("Odd", glitter=1.0)
        except ScriptError as exc:
            assert "glitter" in str(exc)
        else:
            raise AssertionError("unknown material property accepted")
        try:
            api.add_material("Odd", preset="nope")
        except ScriptError:
            pass
        else:
            raise AssertionError("unknown preset accepted")
        assert api.unassign_material(cube, "Blue") == 1
        assert api.material_of(cube) is None
        api.assign_material(cube, "Red")
        assert api.material_of(cube)["name"] == "Red"
        assert api.unassign_material(cube) == 2 and api.material_of(cube) is None
        n = len(sc._undo)
        api.assign_material(cube, "Red")
        assert len(sc._undo) == n + 1


def test_regression_suppress_undo_covers_scene_methods():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        cube = sc.objects[0]
        api.set_position(cube, (1, 0, 0))
        api.undo()
        cube = sc.objects[0]
        redo_depth = len(sc._redo)
        depth = len(sc._undo)
        with api.suppress_undo():
            with api.suppress_undo():
                api.set_data(cube, "foo", 1)
            c = api.create("cube")
            api.set_param(c, "size_x", 50)
            api.set_scene_data("bar", 2)
            api.rename(c, "Quiet")
            api.set_parent(c, cube)
            api.delete(c)
            assert api.is_undo_suppressed()
        assert not api.is_undo_suppressed()
        assert len(sc._undo) == depth and len(sc._redo) == redo_depth
        assert "_record" not in sc.__dict__
        api.set_data(cube, "foo", 3)
        assert len(sc._undo) == depth + 1
        api.add_python_tag(cube, "quartz.set_data(op, 'count', frame)\nquartz.set_param(quartz.find('Sph'), 'radius', frame + 1)\n")
        api.create("sphere", name="Sph")
    depth = len(sc._undo)
    res = scripting.run_python_tags(sc, 5)
    assert res[0].ok, res[0].error
    assert len(sc._undo) == depth
    assert api.get_data(cube, "count", scene=sc) == 5.0
    assert api.find("Sph", sc).params["radius"] == 6.0


def test_regression_bound_scene_data_undo_and_plugin_command_group():
    home = _fresh_home()
    sc = Scene()
    with api.bind_scene(sc):
        cube = sc.objects[0]
        n = len(sc._undo)
        api.set_data(cube, "q", 5)
        assert len(sc._undo) == n + 1
        api.undo()
        assert api.get_data(sc.objects[0], "q") is None
    _write_plugin(home, "multi", '''
PLUGIN = {"name": "Multi", "type": "command"}


def register(api):
    def many():
        for i in range(3):
            api.create("cube", name=f"M{i}")
    api.register_command("Make Three", many)
''')
    loader = scripting.get_loader()
    loader.load_all()
    try:
        g = reset_scene()
        before = len(g.objects)
        loader.run_command("Make Three")
        assert len(g.objects) == before + 3
        assert g.undo() and len(g.objects) == before
    finally:
        scripting.reset_loader()


def test_regression_create_and_apply_tracks_are_atomic():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        n, depth = len(sc.objects), len(sc._undo)
        try:
            api.create("cube", size_x="abc")
        except ScriptError as exc:
            assert "size_x" in str(exc)
        else:
            raise AssertionError("bad parameter accepted")
        assert len(sc.objects) == n and len(sc._undo) == depth
        try:
            api.create("cube", position=(1, 2))
        except ScriptError:
            pass
        else:
            raise AssertionError("bad position accepted")
        assert len(sc.objects) == n and len(sc._undo) == depth
        cube = sc.objects[0]
        api.set_key(cube, "position.x", 0, 0.0)
        api.set_key(cube, "position.x", 10, 10.0)
        tr = store.get_object(cube, "tracks")
        tr["param.zzz"] = [{"frame": 0, "value": 1.0, "interp": "linear"}]
        store.set_object(cube, "tracks", tr)
        before = cube.position.copy()
        depth = len(sc._undo)
        try:
            api.apply_tracks(cube, 5)
        except ScriptError as exc:
            assert "'zzz'" in str(exc)
        else:
            raise AssertionError("bad track applied")
        assert _close(cube.position, before) and len(sc._undo) == depth
        try:
            api.set_key(cube, "param.nothing", 0, 1.0)
        except ScriptError:
            pass
        else:
            raise AssertionError("missing parameter keyed")


def test_regression_duplicate_copies_children():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        root = api.create("null", name="Group", position=(10, 0, 0))
        cl = api.create("cloner", parent=root)
        api.create("cube", parent=cl, size_x=20.0)
        sc.evaluate()
        depth = len(sc._undo)
        d = api.duplicate(cl)
        sc.evaluate()
        assert len(sc._undo) == depth + 1
        assert len(cl.mesh.points) > 0 and len(d.mesh.points) == len(cl.mesh.points)
        assert len(api.children(d)) == 1 and api.children(d)[0].params["size_x"] == 20.0
        assert api.parent(d) is root and _close(api.world_position(d), api.world_position(cl))
        g = api.duplicate(root, name="Group Copy")
        assert len(api.descendants(g)) == 4
        assert _close(api.world_position(g), [10, 0, 0])
        lone = api.duplicate(root, children=False)
        assert api.children(lone) == []
        api.undo()
        assert api.find("Group Copy") is not None


def test_regression_plugins_and_scripts_import_helpers():
    home = _fresh_home()
    _write_plugin(home, "_helper", "VALUE = 42\n")
    _write_plugin(home, "uses_helper", '''
import _helper

PLUGIN = {"name": "Uses Helper", "type": "command"}


def register(api):
    api.register_command("Helper Value", lambda: _helper.VALUE)
''')
    loader = scripting.get_loader()
    loader.load_all()
    try:
        assert not loader.errors(), loader.errors()
        assert loader.run_command("Helper Value") == 42
        _write_plugin(home, "_helper", "VALUE = 43\n")
        assert loader.reload_one("uses_helper")
        assert loader.run_command("Helper Value") == 43
    finally:
        scripting.reset_loader()
    lib = ScriptLibrary()
    assert lib.folder == home / "scripts"
    (home / "scripts" / "mod_a.py").write_text("NUMBER = 7\n", encoding="utf-8")
    lib.save("Main", "import mod_a\nprint(mod_a.NUMBER * 2)\n")
    folder = str((home / "scripts").resolve())
    r = lib.run("Main", _scene())
    assert r.ok, r.error
    assert r.stdout == "14\n" and folder not in sys.path
    (home / "scripts" / "mod_a.py").write_text("NUMBER = 8\n", encoding="utf-8")
    r = lib.run("Main", _scene())
    assert r.ok and r.stdout == "16\n"


def test_regression_execute_binds_scene():
    _fresh_home()
    sc = Scene()
    other = reset_scene()
    ns = make_namespace(sc)
    depth = len(sc._undo)
    n_other = len(other.objects)
    r = execute("import quartz\nquartz.create('cube')\nquartz.create('cube')\n", ns, scene=sc, undo_group=True)
    assert r.ok, r.error
    assert len(sc.objects) == 3 and len(other.objects) == n_other
    assert len(sc._undo) == depth + 1
    r = execute("quartz.create('cube', name='ViaDoc')", make_namespace(sc))
    assert r.ok and api.find("ViaDoc", sc) is not None and api.find("ViaDoc", other) is None
    assert api.document() is other


def test_regression_messages_keep_quotes_and_singular_parents():
    _fresh_home()
    sc = _scene()
    with api.bind_scene(sc):
        null = api.create("null")
        try:
            api.set_param(null, "radius", "x")
        except ScriptError as exc:
            assert "'x'" in str(exc)
        else:
            raise AssertionError("bad radius accepted")
        try:
            api.set_param(null, "zzz", 1)
        except ScriptError as exc:
            assert str(exc) == "'null' has no parameter 'zzz'"
        else:
            raise AssertionError("unknown parameter accepted")
        p = api.create("null", name="Flat")
        api.set_scale(p, (0, 0, 0))
        c = api.make_editable(api.create("cube", parent=p))
        for call in (lambda: api.set_world_position(c, (0, 0, 0)),
                     lambda: api.set_points(c, api.points(c), world=True),
                     lambda: api.set_parent(api.create("cube"), p)):
            try:
                call()
            except ScriptError as exc:
                assert "singular" in str(exc)
            else:
                raise AssertionError("singular transform accepted")
        cyl = api.make_editable(api.create("cylinder"))
        try:
            api.run_tool("extrude", {"nonexistent": 1}, cyl, "all")
        except ScriptError as exc:
            assert "nonexistent" in str(exc) and "offset" in str(exc)
        else:
            raise AssertionError("unknown tool parameter accepted")
        other = api.make_editable(api.create("cube", name="Other"))
        api.set_active(cyl)
        r = api.run_tool("extrude", {"offset": 10.0}, other)
        assert r.ok and api.polygon_count(other) > 6
        r = api.run_tool("bevel", None, other)
        assert r.ok


def test_regression_shortcuts_work_hidden_and_once():
    from PySide6.QtWidgets import QWidget
    home = _fresh_home()
    lib = ScriptLibrary()
    lib.save("Hit", "quartz.set_scene_data('hits', quartz.get_scene_data('hits', 0) + 1)\n")
    g = reset_scene()
    m1 = ScriptManager(g)
    m1.select("Hit")
    assert m1.set_shortcut("Ctrl+Shift+H") == "Ctrl+Shift+H"
    host = QWidget()
    host.resize(256, 128)
    host.show()
    host.activateWindow()
    APP.processEvents()
    combo = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    QTest.keyClick(host, Qt.Key.Key_H, combo)
    assert api.get_scene_data("hits", scene=g) == 1
    m1.show()
    m2 = ScriptManager(g)
    m2.show()
    APP.processEvents()
    QTest.keyClick(host, Qt.Key.Key_H, combo)
    assert api.get_scene_data("hits", scene=g) == 2
    assert m1.last_result is not None and m2.last_result is not None
    assert m1.binder is m2.binder
    m2.select("Hit")
    m2.set_shortcut("Ctrl+Alt+J")
    QTest.keyClick(host, Qt.Key.Key_H, combo)
    assert api.get_scene_data("hits", scene=g) == 2
    QTest.keyClick(host, Qt.Key.Key_J, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    assert api.get_scene_data("hits", scene=g) == 3
    ScriptLibrary().set_shortcut("Hit", "Ctrl+Alt+K")
    from PySide6.QtGui import QAction, QKeySequence
    fired = []
    action = QAction("Integrator copy", host)
    action.setShortcut(QKeySequence("Ctrl+Alt+K"))
    action.triggered.connect(lambda: fired.append(1))
    host.addAction(action)
    QTest.keyClick(host, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    assert api.get_scene_data("hits", scene=g) == 4 and fired == []
    QTest.keyClick(host, Qt.Key.Key_K)
    assert api.get_scene_data("hits", scene=g) == 4
    keys = scripting.key_actions()
    assert any(k == "Ctrl+Alt+K" for k, _f, _l in keys)
    for w in (m1, m2, host):
        w.close()
        w.deleteLater()
    APP.processEvents()
    ScriptLibrary().set_shortcut("Hit", None)


def test_script_time_limit_stops_runaway_code():
    import time
    from quartz_studio.scripting.runner import Watchdog
    home = _fresh_home()
    sc = _scene()
    ns = make_namespace(sc)
    start = time.perf_counter()
    r = execute("n = 0\nwhile True:\n    n += 1\n", ns, "loop.py", scene=sc, timeout=0.3)
    assert not r.ok and "ScriptTimeout" in r.error and "loop.py" in r.error and "0.3 s" in r.error
    assert time.perf_counter() - start < 10 and ns["n"] > 0
    r = execute("while True:\n    try:\n        pass\n    except Exception:\n        pass\n", ns, scene=sc, timeout=0.3)
    assert not r.ok and "ScriptTimeout" in r.error
    r = execute("total = sum(range(1000))", ns, scene=sc, timeout=5.0)
    assert r.ok and ns["total"] == 499500
    with Watchdog(5.0) as dog:
        pass
    assert not dog.fired
    lib = ScriptLibrary()
    assert lib.timeout() == 120.0
    lib.set_timeout(0.3)
    lib.save("Spin", "while True:\n    pass\n")
    r = lib.run("Spin", sc)
    assert not r.ok and "ScriptTimeout" in r.error
    lib.set_timeout(0)
    assert lib.timeout() is None
    lib.set_timeout(120)
    pytags.set_tag_timeout(0.3)
    try:
        api.add_python_tag(sc.objects[0], "while True:\n    pass\n", scene=sc)
        api.add_python_tag(sc.objects[0], "op.position = np.array([1.0, 1.0, 1.0])", scene=sc)
        res = scripting.run_python_tags(sc, 1)
        assert not res[0].ok and "ScriptTimeout" in res[0].error and res[1].ok
        assert _close(sc.objects[0].position, [1, 1, 1])
    finally:
        pytags.set_tag_timeout(None)
    assert pytags.tag_timeout() is None
    pytags.set_tag_timeout(10)


def test_code_editor_gutter_find_replace_complete():
    from quartz_studio.scripting.editor import GUTTER_WIDTHS, CodeEditor, completion_words
    _fresh_home()
    sc = _scene()
    man = ScriptManager(sc)
    man.resize(1024, 512)
    man.show()
    APP.processEvents()
    man.new_script("Edit", "value = 1\nvalue = value + 1\nprint(value)\n")
    ed = man.editor
    assert ed.gutter_width() in GUTTER_WIDTHS and ed.gutter.width() == ed.gutter_width()
    assert ed.viewportMargins().left() == ed.gutter_width()
    small = ed.gutter_width()
    ed.setPlainText("\n".join(f"x{i} = {i}" for i in range(1200)))
    assert ed.gutter_width() > small and ed.gutter_width() in GUTTER_WIDTHS
    assert ed.line_numbers_visible() > 0
    img = ed.gutter.grab()
    assert img.width() == ed.gutter_width()
    ed.setPlainText("alpha = 1\nbeta = alpha\nAlpha = 3\n")
    ed.setFocus()
    QTest.keyClick(ed, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert man.find_bar.isVisible()
    man.find_bar.find_edit.setText("alpha")
    QTest.mouseClick(man.find_bar.next_button, Qt.MouseButton.LeftButton)
    assert ed.textCursor().selectedText() == "alpha" and ed.textCursor().blockNumber() == 0
    QTest.mouseClick(man.find_bar.next_button, Qt.MouseButton.LeftButton)
    assert ed.textCursor().blockNumber() == 1
    QTest.mouseClick(man.find_bar.next_button, Qt.MouseButton.LeftButton)
    assert ed.textCursor().blockNumber() == 2
    man.find_bar.case_box.setChecked(True)
    QTest.mouseClick(man.find_bar.next_button, Qt.MouseButton.LeftButton)
    assert ed.textCursor().blockNumber() == 0
    QTest.mouseClick(man.find_bar.prev_button, Qt.MouseButton.LeftButton)
    assert ed.textCursor().blockNumber() == 1
    man.find_bar.replace_edit.setText("gamma")
    QTest.mouseClick(man.find_bar.replace_button, Qt.MouseButton.LeftButton)
    assert ed.toPlainText() == "alpha = 1\nbeta = gamma\nAlpha = 3\n"
    man.find_bar.case_box.setChecked(False)
    QTest.mouseClick(man.find_bar.replace_all_button, Qt.MouseButton.LeftButton)
    assert man.find_bar.last_count == 2 and ed.toPlainText() == "gamma = 1\nbeta = gamma\ngamma = 3\n"
    ed.undo()
    assert ed.toPlainText() == "alpha = 1\nbeta = gamma\nAlpha = 3\n"
    man.find_bar.find_edit.setText("missing")
    assert not man.find_bar.find_next()
    QTest.keyClick(man.find_bar.find_edit, Qt.Key.Key_Escape)
    assert not man.find_bar.isVisible()
    assert "create" in completion_words("", "quartz") and "zeros" in completion_words("", "np")
    assert "while" in completion_words("") and "my_var" in completion_words("my_var = 1")
    ed.setPlainText("")
    ed.setFocus()
    QTest.keyClicks(ed, "quartz.cre")
    assert ed.complete() >= 1
    assert ed.completer.popup().isVisible()
    assert ed.completer.currentCompletion().startswith("create")
    ed.insert_completion("create_polygon_object")
    assert ed.toPlainText() == "quartz.create_polygon_object"
    ed.setPlainText("")
    QTest.keyClicks(ed, "np.")
    assert ed.completer.popup().isVisible()
    ed.completer.popup().hide()
    ed.setPlainText("speed = 3\nsp")
    ed.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(ed, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert ed.completer.popup().isVisible()
    QTest.keyClick(ed.completer.popup(), Qt.Key.Key_Return)
    assert ed.toPlainText() == "speed = 3\nspeed"
    man.timeout_spin.setValue(7)
    assert ScriptLibrary().timeout() == 7.0 and "7 s" in man.status.text()
    man.timeout_spin.setValue(0)
    assert ScriptLibrary().timeout() is None and man.timeout_spin.text() == "None"
    man.set_time_limit(120)
    assert man.timeout_spin.value() == 120
    man.close()


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
