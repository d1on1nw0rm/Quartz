from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

_PREFS_DIR = tempfile.mkdtemp(prefix="quartz-prefs-select-")
_OLD_PREFS_DIR = os.environ.get("QUARTZ_PREFS_DIR")
os.environ["QUARTZ_PREFS_DIR"] = _PREFS_DIR

import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from quartz_studio import icons, prefs
from quartz_studio import scene as scene_module
from quartz_studio.app import create_app
from quartz_studio.modeling import Selection, run_tool
from quartz_studio.modeling import select_tools as st
from quartz_studio.modeling.meshkit import edge_faces, edge_key, edge_loop, edge_ring, region_boundary
from quartz_studio.modeling.primitives import cylinder, plane
from quartz_studio.scene import Mesh, get_scene

NEW_IDS = ("select_loop", "select_ring", "select_pattern", "select_fill", "select_phong")
NAMES = ["Brush Selection", "Loop Selection", "Ring Selection", "Pattern Selection",
         "Fill Selection", "Phong Angle Selection"]
ICONS = ["pal_live_selection", "pal_select_loop", "pal_select_ring", "pal_select_pattern",
         "pal_select_fill", "pal_select_phong"]
HINTS = {
    "select": ("Paint to select · Shift adds · Ctrl removes · Shift+wheel sizes the brush",
               "Paint over an object to select it · Ctrl deselects · Shift+wheel sizes the brush"),
    "select_loop": ("Click an edge to select its loop · Shift adds · Ctrl removes", ""),
    "select_ring": ("Click an edge to select its ring · Shift adds · Ctrl removes", ""),
    "select_pattern": ("Click an edge to select a pattern along its loop · Shift adds · Ctrl removes", ""),
    "select_fill": ("Click a polygon to fill up to the selected edges · Ctrl removes", ""),
    "select_phong": ("Click a polygon to select its smooth area · Shift adds · Ctrl removes", ""),
}

_STATE: dict = {}


def _app() -> QApplication:
    if "app" not in _STATE:
        _STATE["app"] = create_app([sys.argv[0]])
        try:
            from quartz_studio import controls
        except ImportError:
            controls = None
        if controls is not None:
            folder = tempfile.mkdtemp(prefix="quartz-controls-select-")
            _STATE["controls"] = (controls, controls.STORE_PATH, folder)
            controls.STORE_PATH = os.path.join(folder, "controls.json")
    return _STATE["app"]


def _settle(passes: int = 4) -> None:
    for _ in range(passes):
        _app().processEvents()


def _fresh_prefs() -> None:
    for name in ("prefs.json", "prefs.json.tmp", "prefs.corrupt.json"):
        try:
            os.remove(os.path.join(_PREFS_DIR, name))
        except OSError:
            pass
    prefs.reload()


def _editable_cube(mesh: Mesh | None = None):
    scene = get_scene()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_object("Cube", mesh if mesh is not None else Mesh.cube(200.0))
    scene.set_tool("move")
    scene.set_mode("model")
    scene._undo.clear()
    scene._redo.clear()
    return scene


def _subdivided_cube() -> Mesh:
    cube = Mesh.cube(200.0)
    return run_tool("subdivide", cube, Selection("polygons", polygons=set(range(6))), {}).mesh


def _edge_with_loop(mesh: Mesh, length: int):
    for e in sorted(mesh.edges):
        if len(edge_loop(mesh, e)) == length:
            return edge_key(*e)
    raise AssertionError(f"no edge with a loop of {length}")


def _pixels(name: str, size: int = 48) -> np.ndarray:
    img = icons.pixmap(name, size, None).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    arr = np.frombuffer(bytes(img.constBits()), dtype=np.uint8).reshape(img.height(), img.width(), 4)
    return arr.astype(np.int16)


def test_tool_table_is_exact() -> None:
    assert st.TOOL_IDS == ("select",) + NEW_IDS
    assert [t.name for t in st.TOOLS] == NAMES
    assert [t.icon for t in st.TOOLS] == ICONS
    assert st.get("select").modes == ("points", "edges", "polygons", "model")
    for tool_id in ("select_loop", "select_ring", "select_pattern"):
        assert st.get(tool_id).modes == ("points", "edges", "polygons")
        assert st.get(tool_id).entry_mode == "edges"
    for tool_id in ("select_fill", "select_phong"):
        assert st.get(tool_id).modes == ("polygons",)
        assert st.get(tool_id).entry_mode == "polygons"
    rows = {t.id: [(p.key, p.label, p.kind, p.default, p.minimum, p.maximum, p.step, p.unit, p.choices)
                   for p in t.params] for t in st.TOOLS}
    assert rows["select"] == [
        ("radius", "Radius", "int", 10, 2, 512, 2, "px", ()),
        ("visible_only", "Only Select Visible Elements", "bool", True, None, None, 1.0, "", ()),
        ("tolerant", "Tolerant Selection", "bool", False, None, None, 1.0, "", ()),
    ]
    assert rows["select_loop"] == [("boundary", "Select Boundary Loop", "bool", False, None, None, 1.0, "", ())]
    assert rows["select_ring"] == [] and rows["select_fill"] == []
    assert rows["select_pattern"] == [
        ("count", "Select", "int", 1, 1, 64, 1, "", ()),
        ("skip", "Skip", "int", 1, 0, 64, 1, "", ()),
        ("direction", "Direction", "choice", "Loop", None, None, 1.0, "", ("Loop", "Ring")),
    ]
    assert rows["select_phong"] == [("angle", "Angle", "angle", 40.0, 0.0, 180.0, 1.0, "", ())]
    for tool in st.TOOLS:
        assert (tool.hint, tool.hint_model) == HINTS[tool.id], tool.id
    assert all(st.is_select_tool(i) for i in st.TOOL_IDS)
    assert not st.is_select_tool("move") and not st.is_select_tool("extrude")


def test_scene_tools_hold_the_new_ids() -> None:
    _app()
    for tool_id in NEW_IDS:
        assert tool_id in scene_module.TOOLS, tool_id
    assert scene_module.TOOLS.count("select_loop") == 1
    scene = get_scene()
    scene.set_tool("select_phong")
    assert scene.tool == "select_phong"
    scene.set_tool("move")


def test_menu_commands_list_the_six_tools() -> None:
    commands = st.menu_commands()
    assert [path for path, _run in commands] == [("Select", n) for n in NAMES]
    assert all(callable(run) for _path, run in commands)


def test_icons_are_registered_with_one_citrine_part() -> None:
    _app()
    for name in ICONS:
        assert icons.has(name), name
        arr = _pixels(name)
        blue, green, red, alpha = (arr[:, :, k] for k in range(4))
        solid = alpha > 200
        assert int(solid.sum()) >= 40, name
        citrine = (abs(red - 255) < 30) & (abs(green - 181) < 30) & (abs(blue - 61) < 40) & solid
        neutral = (abs(red - 207) < 25) & (abs(green - 213) < 25) & (abs(blue - 225) < 25) & solid
        assert int(citrine.sum()) >= 8, f"{name}: no tool tint"
        assert int(neutral.sum()) >= 20, f"{name}: no neutral stroke"
        other = solid & ~citrine & ~neutral
        assert int(other.sum()) < int(solid.sum()) * 0.5, f"{name}: stray colours"
    digests = {name: _pixels(name).tobytes() for name in ICONS}
    assert len(set(digests.values())) == len(ICONS)


def test_options_clamp_persist_and_reset() -> None:
    _fresh_prefs()
    assert st.options("select") == {"radius": 10, "visible_only": True, "tolerant": False}
    assert st.options("select_ring") == {}
    assert st.options("select_pattern") == {"count": 1, "skip": 1, "direction": "Loop"}
    st.set_option("select", "radius", 1000)
    assert st.options("select")["radius"] == 512
    st.set_option("select", "radius", 0)
    assert st.options("select")["radius"] == 2
    st.set_option("select", "radius", 12)
    st.set_option("select_phong", "angle", 400)
    st.set_option("select_pattern", "direction", "Sideways")
    assert st.options("select_phong")["angle"] == 180.0
    assert st.options("select_pattern")["direction"] == "Loop"
    with open(prefs.path(), "r", encoding="utf-8") as fh:
        stored = json.load(fh)["values"]["selection.options"]
    assert stored["select"]["radius"] == 12
    prefs.reload()
    assert prefs.get("selection.options")["select"]["radius"] == 12
    assert st.options("select")["radius"] == 12
    try:
        st.set_option("select", "nope", 1)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown option accepted")
    prefs.set("selection.options", {"select": {"radius": "big", "extra": 5, "tolerant": 1},
                                    "select_loop": "broken"})
    assert st.options("select") == {"radius": 10, "visible_only": True, "tolerant": True}
    assert st.options("select_loop") == {"boundary": False}
    st.reset_options("select")
    assert st.options("select") == {"radius": 10, "visible_only": True, "tolerant": False}
    assert "select" not in prefs.get("selection.options", {})
    _fresh_prefs()


def test_apply_selection_records_one_step_per_change() -> None:
    _app()
    scene = _editable_cube()
    scene.set_mode("points")
    assert st.apply_selection(scene, "points", {0, 1}, "replace")
    assert scene.selected_points == {0, 1} and len(scene._undo) == 1
    assert not st.apply_selection(scene, "points", {0, 1}, "replace")
    assert not st.apply_selection(scene, "points", {1}, "add")
    assert len(scene._undo) == 1
    assert st.apply_selection(scene, "points", {2}, "add")
    assert scene.selected_points == {0, 1, 2}
    assert st.apply_selection(scene, "points", {0}, "remove")
    assert scene.selected_points == {1, 2} and len(scene._undo) == 3
    assert scene.undo() and scene.selected_points == {0, 1, 2}
    assert scene.undo() and scene.selected_points == {0, 1}
    assert scene.undo() and scene.selected_points == set()
    scene.set_mode("edges")
    scene.begin_group()
    st.apply_selection(scene, "edges", {(1, 0)}, "replace")
    st.apply_selection(scene, "edges", {(2, 1)}, "add")
    scene.end_group()
    assert scene.selected_edges == {edge_key(0, 1), edge_key(1, 2)}
    assert len(scene._undo) == 1
    assert scene.undo() and scene.selected_edges == set()
    obj = scene.active
    obj.kind = "cube"
    try:
        scene.set_mode("points")
        assert not st.apply_selection(scene, "points", {0}, "replace")
        assert scene.selected_points == set()
    finally:
        obj.kind = scene_module.EDITABLE_KIND


def test_apply_selection_in_model_mode() -> None:
    _app()
    scene = _editable_cube()
    first = scene.active
    second = scene.add_object("Second", Mesh.cube(50.0), activate=False)
    scene._undo.clear()
    scene.set_mode("model")
    scene.select_object(False)
    assert st.apply_selection(scene, "model", {second}, "replace")
    assert scene.active is second and scene.object_selected
    assert not st.apply_selection(scene, "model", {second}, "add")
    assert st.apply_selection(scene, "model", set(), "replace")
    assert not scene.object_selected
    assert not st.apply_selection(scene, "model", set(), "replace")
    assert st.apply_selection(scene, "model", {first}, "add")
    assert scene.active is first and scene.object_selected
    assert not st.apply_selection(scene, "model", {second}, "remove")
    assert st.apply_selection(scene, "model", {first}, "remove")
    assert not scene.object_selected
    assert len(scene._undo) == 4
    assert scene.undo() and scene.object_selected


def test_loop_sets_on_a_subdivided_cube() -> None:
    mesh = _subdivided_cube()
    e = _edge_with_loop(mesh, 8)
    edges = st.loop_elements(mesh, "edges", e)
    assert edges == set(edge_loop(mesh, e)) and len(edges) == 8
    assert st.loop_elements(mesh, "edges", (e[1], e[0])) == edges
    points = st.loop_elements(mesh, "points", e)
    assert points == {i for x in edges for i in x} and len(points) == 8
    strip = st.loop_elements(mesh, "polygons", e)
    assert len(strip) == 8
    ef = edge_faces(mesh)
    ring = edge_ring(mesh, e)
    assert strip == {f for x in ring for f in ef[x]}
    corner = next(edge_key(*x) for x in sorted(mesh.edges) if len(edge_loop(mesh, x)) < 8)
    assert st.loop_elements(mesh, "edges", corner) == set(edge_loop(mesh, corner))


def test_boundary_loop_on_an_open_grid() -> None:
    mesh = plane(400.0, 400.0, 4, 4)
    ef = edge_faces(mesh)
    border = next(x for x, faces in sorted(ef.items()) if len(faces) == 1)
    assert st.loop_elements(mesh, "edges", border, boundary=True) == {x for x, f in ef.items() if len(f) == 1}
    assert len(st.loop_elements(mesh, "edges", border, boundary=True)) == 16
    assert st.loop_elements(mesh, "edges", border, boundary=False) == set(edge_loop(mesh, border))
    inner = next(x for x, faces in sorted(ef.items()) if len(faces) == 2)
    assert st.loop_elements(mesh, "edges", inner, boundary=True) == set(edge_loop(mesh, inner))


def test_ring_sets() -> None:
    mesh = _subdivided_cube()
    e = _edge_with_loop(mesh, 8)
    ring = st.ring_elements(mesh, "edges", e)
    assert ring == set(edge_ring(mesh, e))
    assert st.ring_elements(mesh, "points", e) == {i for x in edge_ring(mesh, e) for i in x}
    k = edge_faces(mesh)[e][0]
    poly = list(mesh.polygons[k])
    j = next(j for j in range(4) if edge_key(poly[j], poly[(j + 1) % 4]) == e)
    side = edge_key(poly[(j + 1) % 4], poly[(j + 2) % 4])
    strip = st.ring_elements(mesh, "polygons", e, k)
    assert k in strip and len(strip) == 8
    ef = edge_faces(mesh)
    assert strip == {f for x in edge_ring(mesh, side) for f in ef[x]}
    assert strip != st.loop_elements(mesh, "polygons", e)
    assert st.ring_elements(mesh, "polygons", e, None) == set()
    tri = Mesh(np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]), [(0, 1, 2)])
    assert st.ring_elements(tri, "polygons", (0, 1), 0) == set()


def test_pattern_every_second_edge_both_ways() -> None:
    mesh = cylinder(50.0, 200.0, 4, 8, caps=False)
    e = _edge_with_loop(mesh, 8)
    seq = edge_loop(mesh, e)
    i0 = seq.index(e)
    got = st.pattern_elements(mesh, "edges", e, None, None, 1, 1, "Loop")
    assert len(got) == 4 and e in got
    assert got == {seq[i] for i in range(8) if (i - i0) % 2 == 0}
    assert seq[(i0 - 2) % 8] in got and seq[(i0 + 2) % 8] in got
    assert seq[(i0 - 1) % 8] not in got and seq[(i0 + 1) % 8] not in got
    two = st.pattern_elements(mesh, "edges", e, None, None, 2, 2, "Loop")
    assert two == {seq[i] for i in range(8) if (i - i0) % 4 < 2}
    ring = edge_ring(mesh, e)
    r0 = ring.index(e)
    assert st.pattern_elements(mesh, "edges", e, None, None, 1, 1, "Ring") == {
        ring[i] for i in range(len(ring)) if (i - r0) % 2 == 0}
    p = e[0]
    pts = st.pattern_elements(mesh, "points", e, None, p, 1, 1, "Loop")
    assert len(pts) == 4 and p in pts and e[1] not in pts
    k = edge_faces(mesh)[e][0]
    faces = st.pattern_elements(mesh, "polygons", e, k, None, 1, 1, "Ring")
    assert len(faces) == 4 and k in faces
    assert st.pattern_elements(mesh, "edges", e, None, None, 1, 0, "Loop") == set(seq)


def test_fill_region_inside_a_contour_whole_island_and_remove() -> None:
    mesh = plane(400.0, 400.0, 4, 4)
    inner = {5, 6, 9, 10}
    contour = {edge_key(*x) for x in region_boundary(mesh, inner)}
    assert len(contour) == 8
    assert st.fill_region(mesh, 5, contour, set()) == inner
    assert st.fill_region(mesh, 0, contour, set()) == set(range(16)) - inner
    assert st.fill_region(mesh, 5, set(), set()) == set(range(16))
    assert st.fill_region(mesh, 5, set(), {5}) == set()
    assert st.fill_region(mesh, 0, set(), inner) == set(range(16)) - inner
    everything = set(range(16))
    assert st.fill_region(mesh, 6, contour, set(range(16)) - everything) == inner
    assert st.fill_region(mesh, 6, set(), {0, 1, 2, 3}) == everything - {0, 1, 2, 3}
    scene = _editable_cube(plane(400.0, 400.0, 4, 4))
    scene.set_mode("edges")
    scene.select_components(contour)
    st.activate("select_fill")
    assert scene.mode == "polygons"
    borders = set(scene.selected_edges) | {edge_key(*x) for x in region_boundary(mesh, scene.selected_polygons)}
    region = st.fill_region(scene.active.mesh, 9, borders, set(scene.selected_polygons))
    assert st.apply_selection(scene, "polygons", region, "add")
    assert scene.selected_polygons == inner
    borders = set(scene.selected_edges)
    gone = st.fill_region(scene.active.mesh, 9, borders, set(range(16)) - scene.selected_polygons)
    assert gone == inner
    assert st.apply_selection(scene, "polygons", gone, "remove")
    assert scene.selected_polygons == set()
    scene.set_tool("move")


def test_phong_region_on_a_cube() -> None:
    cube = Mesh.cube(200.0)
    for k in range(6):
        assert st.phong_region(cube, k, 40.0) == {k}
        assert st.phong_region(cube, k, 90.0) == set(range(6))
    assert st.phong_region(cube, 0, 89.0) == {0}
    smooth = cylinder(50.0, 200.0, 1, 8, caps=False)
    assert st.phong_region(smooth, 0, 46.0) == set(range(len(smooth.polygons)))
    assert st.phong_region(smooth, 0, 44.0) == {0}


def test_activate_switches_to_the_entry_mode() -> None:
    _app()
    scene = _editable_cube()
    scene.set_mode("model")
    st.activate("select_loop")
    assert scene.tool == "select_loop" and scene.mode == "edges"
    scene.set_mode("model")
    st.activate("select_fill")
    assert scene.tool == "select_fill" and scene.mode == "polygons"
    scene.set_mode("model")
    st.activate("select")
    assert scene.tool == "select" and scene.mode == "model"
    scene.set_mode("points")
    st.activate("select_ring")
    assert scene.mode == "points"
    scene.set_mode("edges")
    st.activate("select_phong")
    assert scene.mode == "polygons"
    st.activate("select_pattern")
    assert scene.mode == "polygons" and scene.tool == "select_pattern"
    scene.set_mode("model")
    for (path, run), tool_id in zip(st.menu_commands(), st.TOOL_IDS):
        run()
        assert scene.tool == tool_id, path
    scene.set_tool("move")
    scene.set_mode("model")


def _palette():
    if "palette" in _STATE:
        return _STATE["palette"]
    _app()
    from quartz_studio.modeling import install as mi
    from quartz_studio.widgets.tool_palette import ToolPalette

    mi.prepare()
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    palette = ToolPalette(host)
    lay.addWidget(palette)
    host.resize(120, 1000)
    host.show()
    _settle(6)
    _STATE["host"] = host
    _STATE["palette"] = palette
    return palette


def test_rail_selection_group_has_the_six_tools() -> None:
    from quartz_studio.widgets import tool_palette as tp

    palette = _palette()
    assert tp.SCENE_TOOLS["Selection"] == "select"
    assert tp.SELECT_COMMANDS == dict(zip(NAMES, st.TOOL_IDS))
    first = tp.TOOL_PALETTE_ENTRIES[0]
    assert first.key == "Selection" and first.cmd.name == "Brush Selection"
    assert tp._LIVE_SELECTION.name == "Brush Selection" and tp._LIVE_SELECTION.icon == "pal_live_selection"
    assert list(palette.buttons)[0] == "Selection"
    button = palette.buttons["Selection"]
    assert button.group() == list(zip(ICONS, NAMES))
    menu = button.build_menu()
    actions = menu.actions()
    assert [a.text() for a in actions] == NAMES
    assert all(not a.icon().isNull() for a in actions)
    menu.deleteLater()
    scene = _editable_cube()
    scene.set_tool("move")
    _settle(2)
    assert button.command_text() == "Brush Selection" and not button.isChecked()


def test_choosing_each_entry_sets_its_scene_tool() -> None:
    palette = _palette()
    button = palette.buttons["Selection"]
    scene = _editable_cube()
    for name, tool_id, icon in zip(NAMES, st.TOOL_IDS, ICONS):
        scene.set_mode("model")
        scene.set_tool("move")
        _settle(2)
        menu = button.build_menu()
        action = next(a for a in menu.actions() if a.text() == name)
        action.trigger()
        menu.deleteLater()
        _settle(2)
        assert scene.tool == tool_id, (name, scene.tool)
        assert button.isChecked() and button.command_text() == name and button.icon_name() == icon
        assert scene.mode in st.get(tool_id).modes, (name, scene.mode)
        assert palette.scene_tool() == tool_id
    scene.set_mode("model")
    scene.set_tool("move")
    _settle(2)
    menu = button.build_menu()
    next(a for a in menu.actions() if a.text() == "Loop Selection").trigger()
    menu.deleteLater()
    _settle(2)
    assert scene.tool == "select_loop" and scene.mode == "edges"
    palette.buttons["Move"].click()
    _settle(2)
    assert scene.tool == "move" and not button.isChecked()
    button.click()
    _settle(2)
    assert scene.tool == "select_loop" and button.isChecked()
    scene.set_tool("select_ring")
    _settle(2)
    assert button.command_text() == "Ring Selection" and button.isChecked()
    scene.set_tool("select")
    _settle(2)
    assert button.command_text() == "Brush Selection" and button.isChecked()
    scene.set_tool("move")
    scene.set_mode("model")
    _settle(2)


def test_selection_entries_have_tooltips() -> None:
    palette = _palette()
    button = palette.buttons["Selection"]
    assert set(button.tooltips) == set(NAMES)
    for name in NAMES:
        assert button.tooltips[name].startswith(name)
    palette.refresh_tooltips()
    assert set(button.tooltips) == set(NAMES)


def _cleanup() -> None:
    host = _STATE.pop("host", None)
    if host is not None:
        host.close()
        host.deleteLater()
    saved = _STATE.pop("controls", None)
    if saved is not None:
        controls, old_path, folder = saved
        controls.STORE_PATH = old_path
        reset = getattr(controls, "reset", None)
        if reset is not None:
            reset()
        shutil.rmtree(folder, ignore_errors=True)
    if _OLD_PREFS_DIR is None:
        os.environ.pop("QUARTZ_PREFS_DIR", None)
    else:
        os.environ["QUARTZ_PREFS_DIR"] = _OLD_PREFS_DIR
    prefs.reload()
    shutil.rmtree(_PREFS_DIR, ignore_errors=True)


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
    _cleanup()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
