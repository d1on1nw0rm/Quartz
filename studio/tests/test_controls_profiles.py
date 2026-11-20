from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from PySide6.QtWidgets import QApplication

from quartz_studio import controls, project
from quartz_studio.controls import profiles, store
from quartz_studio.controls.profiles import CLASSIC, STANDARD

APP = QApplication.instance() or QApplication(sys.argv[:1])
TMP = tempfile.mkdtemp(prefix="quartz-controls-profiles-")

CLASSIC_WINDOW_KEYS = [
    ("edit.undo", "Ctrl+Z", "global"),
    ("edit.redo", "Ctrl+Y", "global"),
    ("object.make_editable", "C", "global"),
    ("file.new", "Ctrl+N", "global"),
    ("file.open", "Ctrl+O", "global"),
    ("file.merge", "Ctrl+Shift+O", "global"),
    ("file.save", "Ctrl+S", "global"),
    ("file.save_as", "Ctrl+Shift+S", "global"),
    ("file.save_incremental", "Ctrl+Alt+S", "global"),
    ("file.exit", "Alt+F4", "global"),
    ("app.controls", "Shift+F12", "global"),
    ("tool.select_all", "Ctrl+A", "global"),
]

CLASSIC_CHORDS = [
    ("pen", "M~E"), ("bevel", "M~S"), ("extrude", "M~T"), ("inset", "M~W"), ("matrix_extrude", "M~X"),
    ("smooth_shift", "M~Y"), ("trunk", "M~R"), ("bridge", "M~B"), ("stitch_and_sew", "M~P"), ("weld", "M~Q"),
    ("close_polygon_hole", "M~D"), ("edge_cut", "M~F"), ("mirror", "M~H"), ("connect_points_edges", "M~M"),
    ("dissolve", "M~N"), ("slide", "M~O"), ("iron", "M~G"), ("normal_move", "M~Z"), ("normal_scale", "M~#"),
    ("normal_rotate", "M~,"), ("line_cut", "K~K"), ("loop_path_cut", "K~L"), ("plane_cut", "K~J"),
    ("subdivide", "U~S"), ("untriangulate", "U~U"), ("reverse_normals", "U~R"), ("align_normals", "U~A"),
    ("spin_edge", "U~V"), ("collapse", "U~C"), ("melt", "U~Z"), ("optimize", "U~O"), ("disconnect", "U~D"),
    ("split", "U~P"), ("invert_selection", "U~I"), ("select_connected", "U~W"), ("grow_selection", "U~G"),
    ("shrink_selection", "U~K"), ("loop_selection", "U~L"), ("ring_selection", "U~B"),
    ("outline_selection", "U~Q"), ("fill_selection", "U~F"), ("path_selection", "U~M"),
    ("convert_selection", "U~X"),
]

CLASSIC_VIEWPORT_KEYS = [
    ("tool.move", "E"), ("tool.rotate", "R"), ("tool.scale", "T"),
    ("view.frame_all", "H"), ("view.frame_selection", "S"), ("view.frame_objects", "O"),
    ("view.frame_default", "Shift+H"), ("view.undo", "Ctrl+Shift+Z"), ("view.redo", "Ctrl+Shift+Y"),
    ("camera.perspective", "F1"), ("camera.top", "F2"), ("camera.right", "F3"), ("camera.front", "F4"),
    ("tool.delete", "Delete"),
]

CLASSIC_OBJECT_KEYS = [("object.rename", "F2"), ("object.delete", "Delete"), ("object.delete", "Backspace")]

CLASSIC_MOUSE = [
    ("left", ["alt"], None, False, "orbit", None),
    ("middle", ["alt"], None, False, "pan", None),
    ("right", ["alt"], None, False, "dolly", None),
    ("left", [], "3", False, "orbit", None),
    ("left", [], "2", False, "dolly", None),
    ("left", [], "1", False, "pan", None),
    ("middle", [], None, False, "orbit", None),
    ("left", ["ctrl"], None, False, "remove", None),
    ("left", ["shift"], None, False, "add", None),
    ("left", [], None, False, "select", None),
    ("right", [], None, False, "context", None),
    ("right", ["ctrl"], None, False, "remove", None),
    ("right", ["shift"], None, False, "add", None),
    ("middle", [], None, True, None, "view.frame_default"),
    ("middle", ["shift"], None, True, None, "view.frame_default"),
    ("middle", ["ctrl"], None, True, None, "view.frame_default"),
    ("middle", ["shift", "ctrl"], None, True, None, "view.frame_default"),
]

STANDARD_KEYS = [
    ("file.new", ["Ctrl+N"], "global"), ("file.open", ["Ctrl+O"], "global"),
    ("file.merge", ["Ctrl+Shift+O"], "global"), ("file.save", ["Ctrl+S"], "global"),
    ("file.save_as", ["Ctrl+Shift+S"], "global"), ("file.save_incremental", ["Ctrl+Alt+S"], "global"),
    ("file.import", ["Ctrl+Shift+I"], "global"), ("file.exit", ["Ctrl+Q"], "global"),
    ("edit.undo", ["Ctrl+Z"], "global"), ("edit.redo", ["Ctrl+Shift+Z", "Ctrl+Y"], "global"),
    ("app.controls", ["Ctrl+,"], "global"), ("object.make_editable", ["Alt+C"], "global"),
    ("mode.points", ["1"], "global"), ("mode.edges", ["2"], "global"), ("mode.polygons", ["3"], "global"),
    ("mode.model", ["4"], "global"), ("tool.select_all", ["Ctrl+A"], "global"),
    ("tool.deselect_all", ["Ctrl+Shift+A"], "global"), ("tool.invert_selection", ["Ctrl+I"], "global"),
    ("tool.grow_selection", ["Ctrl+Num++"], "global"), ("tool.shrink_selection", ["Ctrl+Num+-"], "global"),
    ("tool.extrude", ["Ctrl+E"], "global"), ("tool.bevel", ["Ctrl+B"], "global"),
    ("tool.inset", ["I"], "global"), ("tool.line_cut", ["K"], "global"),
    ("tool.loop_path_cut", ["Ctrl+R"], "global"), ("tool.weld", ["M"], "global"),
    ("tool.pen", ["P"], "global"), ("tool.line_pen", ["Shift+P"], "global"),
    ("tool.select", ["Q"], "viewport"), ("tool.move", ["W"], "viewport"), ("tool.rotate", ["E"], "viewport"),
    ("tool.scale", ["R"], "viewport"), ("view.frame_selection", ["F"], "viewport"),
    ("view.frame_all", ["A"], "viewport"), ("view.frame_objects", ["Shift+F"], "viewport"),
    ("view.frame_default", ["Home"], "viewport"), ("camera.front", ["Num+1"], "viewport"),
    ("camera.back", ["Ctrl+Num+1"], "viewport"), ("camera.right", ["Num+3"], "viewport"),
    ("camera.left", ["Ctrl+Num+3"], "viewport"), ("camera.top", ["Num+7"], "viewport"),
    ("camera.bottom", ["Ctrl+Num+7"], "viewport"), ("camera.perspective", ["Num+5"], "viewport"),
    ("camera.parallel", ["Ctrl+Num+5"], "viewport"), ("edit.delete", ["Delete", "Backspace"], "viewport"),
    ("object.rename", ["F2"], "objects"), ("object.delete", ["Delete", "Backspace"], "objects"),
]

STANDARD_MOUSE = [
    ("left", ["alt"], None, False, "orbit", None),
    ("middle", ["alt"], None, False, "pan", None),
    ("right", ["alt"], None, False, "dolly", None),
    ("middle", ["shift"], None, False, "pan", None),
    ("middle", ["ctrl"], None, False, "dolly", None),
    ("middle", [], None, False, "orbit", None),
    ("left", ["ctrl"], None, False, "remove", None),
    ("left", ["shift"], None, False, "add", None),
    ("left", [], None, False, "select", None),
    ("right", [], None, False, "context", None),
    ("right", ["ctrl"], None, False, "remove", None),
    ("right", ["shift"], None, False, "add", None),
    ("left", [], None, True, None, "tool.loop_selection"),
]


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _fresh(name: str) -> str:
    folder = os.path.join(TMP, name)
    shutil.rmtree(folder, ignore_errors=True)
    project.SETTINGS_FILE = None
    controls.STORE_PATH = os.path.join(folder, "controls.json")
    controls.reset()
    return controls.STORE_PATH


def _done() -> None:
    controls.reset()
    controls.STORE_PATH = None


def _gestures(res) -> list[tuple]:
    return [(g["button"], list(g["mods"]), g["key"], g["double"], g.get("op"), g.get("action"))
            for g in res.mouse]


def _expected_classic_keys() -> dict:
    expected: dict[str, list[tuple[str, str]]] = {}
    for aid, key, scope in CLASSIC_WINDOW_KEYS:
        expected.setdefault(aid, []).append((key, scope))
    for tool_id, chord in CLASSIC_CHORDS:
        expected.setdefault("tool." + tool_id, []).append((chord, "global"))
    for aid, key in CLASSIC_VIEWPORT_KEYS:
        expected.setdefault(aid, []).append((key, "viewport"))
    for aid, key in CLASSIC_OBJECT_KEYS:
        expected.setdefault(aid, []).append((key, "objects"))
    return {k: tuple(v) for k, v in expected.items()}


def _with_extra_tools(expected: dict) -> dict:
    from quartz_studio.modeling import registry as tool_registry

    out = dict(expected)
    listed = {"tool." + t for t, _c in CLASSIC_CHORDS} | {"tool.delete"}
    for tool_id in tool_registry.tool_ids():
        spec = tool_registry.get_tool(tool_id)
        aid = "tool." + tool_id
        if spec.shortcut and aid not in listed and aid not in out:
            out[aid] = ((spec.shortcut, "global" if "~" in spec.shortcut else "viewport"),)
    return out


def test_builtins_validate_and_have_no_conflict() -> None:
    _fresh("builtins")
    try:
        for doc, pid, name in ((STANDARD, "standard", "Standard"), (CLASSIC, "classic", "Classic")):
            assert doc["format"] == "quartz-controls" and doc["version"] == 1
            assert doc["id"] == pid and doc["name"] == name and doc["base"] is None
            for aid, bindings in doc["keys"].items():
                for b in bindings:
                    assert profiles.is_valid(b), (pid, aid, b)
            profiles.check_mouse(doc["mouse"])
            for key, value in doc["cursor"].items():
                assert profiles.check_cursor(key, value) == value, (pid, key)
            assert set(doc["cursor"]) == set(profiles.CURSOR_SPEC)
            assert set(doc["modifiers"]) == set(profiles.MODIFIER_ROLES)
            assert set(doc["modal"]) == set(profiles.MODAL_ROLES)
            res = profiles.resolve(doc, controls.actions())
            assert res.builtin and res.name == name and res.id == pid
            assert profiles.conflicts(res) == [], profiles.conflicts(res)
            assert controls.conflicts(pid) == []
        assert profiles.CLASSIC_NAME == "Classic" and profiles.STANDARD_NAME == "Standard"
        assert [p["id"] for p in controls.profiles()] == ["standard", "classic"]
    finally:
        _done()


def test_classic_tables_hold_literally() -> None:
    _fresh("classic")
    try:
        res = profiles.resolve(CLASSIC, controls.actions())
        expected = _with_extra_tools(_expected_classic_keys())
        got = {k: v for k, v in res.keys.items() if v}
        assert got == expected, sorted(set(got.items()) ^ set(expected.items()))
        assert _gestures(res) == CLASSIC_MOUSE
        assert res.cursor["orbit_pivot"] == "Cursor" and res.cursor["drag_threshold"] == 3
        assert res.cursor["click_tolerance"] == 4 and res.cursor["hold_ms"] == 380
        assert res.cursor["chord_ms"] == 1500 and res.cursor["wheel_step"] == 0.88
        assert res.cursor["orbit_speed"] == 0.3 and res.cursor["dolly_speed"] == 0.005
        assert res.modifiers == {"snap": "shift", "extrude": "ctrl", "create_child": "shift",
                                 "create_adopt": "alt"}
        assert res.modal == {"cancel": ("Escape",), "confirm": ("Return", "Enter")}
        from quartz_studio.modeling import registry as tool_registry

        for tool_id in tool_registry.tool_ids():
            spec = tool_registry.get_tool(tool_id)
            if spec.shortcut:
                assert res.keys["tool." + tool_id][0][0] == spec.shortcut, tool_id
        assert res.keys["tool.trunk"] == (("M~R", "global"),)
        assert res.keys["tool.delete"] == (("Delete", "viewport"),)
        for unbound in ("file.import", "file.export_selection", "file.clear_recent", "edit.delete",
                        "mode.points", "tool.select", "tool.line_pen", "camera.left", "camera.pivot.cursor"):
            assert not res.keys.get(unbound), unbound
        assert controls.active().keys == res.keys
    finally:
        _done()


def test_classic_mouse_matching_follows_today() -> None:
    _fresh("classic-mouse")
    try:
        match = controls.match_press
        key1, key2, key3 = (profiles.key_code(k) for k in ("1", "2", "3"))
        assert match("left", {"alt"}, set())["op"] == "orbit"
        assert match("left", {"alt", "shift"}, set())["op"] == "orbit"
        assert match("left", {"alt", "ctrl", "shift"}, set())["op"] == "orbit"
        assert match("middle", {"alt"}, set())["op"] == "pan"
        assert match("right", {"alt"}, set())["op"] == "dolly"
        assert match("left", set(), {key1})["op"] == "pan"
        assert match("left", set(), {key2})["op"] == "dolly"
        assert match("left", set(), {key3})["op"] == "orbit"
        assert match("left", set(), {key1, key3})["op"] == "orbit"
        assert match("left", set(), {key1, key2})["op"] == "dolly"
        assert match("left", {"alt"}, {key3})["op"] == "orbit"
        assert match("middle", set(), set())["op"] == "orbit"
        assert match("middle", {"shift", "ctrl"}, set())["op"] == "orbit"
        assert match("left", set(), set())["op"] == "select"
        assert match("left", {"shift"}, set())["op"] == "add"
        assert match("left", {"ctrl"}, set())["op"] == "remove"
        assert match("left", {"ctrl", "shift"}, set())["op"] == "remove"
        assert match("right", set(), set())["op"] == "context"
        assert match("right", set(), {key1}) is None
        assert match("right", {"shift"}, {key2}) is None
        assert match("middle", set(), set(), True)["action"] == "view.frame_default"
        assert match("middle", {"shift", "ctrl"}, set(), True)["action"] == "view.frame_default"
        assert match("middle", {"alt"}, set(), True)["op"] == "pan"
        assert match("left", set(), set(), True)["op"] == "select"
        assert controls.modifier_name("snap") == "Shift"
        assert controls.modifier_name("extrude") == "Ctrl"
        assert controls.modifier_name("create_adopt") == "Alt"
        res = controls.active()
        assert profiles.hold_key_codes(res) == {key1, key2, key3}
        assert profiles.modal_keys(res, "cancel") == ("Escape",)
        assert profiles.modal_keys(res, "confirm") == ("Return", "Enter")
    finally:
        _done()


def test_standard_table_holds_literally() -> None:
    _fresh("standard")
    try:
        res = profiles.resolve(STANDARD, controls.actions())
        expected = {aid: tuple((k, scope) for k in keys) for aid, keys, scope in STANDARD_KEYS}
        got = {k: v for k, v in res.keys.items() if v}
        assert got == expected, sorted(set(got.items()) ^ set(expected.items()))
        assert res.keys["tool.select"] == (("Q", "viewport"),)
        assert _gestures(res) == STANDARD_MOUSE
        assert res.cursor["orbit_pivot"] == "Center" and res.cursor["drag_threshold"] == 4
        assert res.cursor["orbit_style"] == "turntable" and res.cursor["click_tolerance"] == 4
        assert res.modifiers == {"snap": "shift", "extrude": "ctrl", "create_child": "shift",
                                 "create_adopt": "alt"}
        for chord in (b for keys in STANDARD["keys"].values() for b in keys):
            assert "~" not in chord
        controls.select("standard")
        match = controls.match_press
        assert match("middle", {"shift"}, set())["op"] == "pan"
        assert match("middle", {"ctrl"}, set())["op"] == "dolly"
        assert match("middle", set(), set())["op"] == "orbit"
        assert match("left", set(), set(), True)["action"] == "tool.loop_selection"
        assert match("left", {"shift"}, set(), True)["op"] == "add"
        assert controls.cursor("drag_threshold") == 4
    finally:
        _done()


def test_binding_parsing_and_conflict_rules() -> None:
    assert profiles.normalize("Delete") == profiles.normalize("Del") == "Del"
    assert profiles.normalize("ctrl+shift+z") == "Ctrl+Shift+Z"
    assert profiles.normalize("Ctrl+,") == "Ctrl+,"
    assert profiles.normalize("Num+1") != profiles.normalize("1")
    assert profiles.normalize("m~e") == "M~E"
    assert profiles.parse_chord("M~#") == ("M", "#")
    assert profiles.parse_chord("M~,") == ("M", ",")
    assert profiles.parse_chord("Ctrl+M~E") is None
    assert profiles.parse_chord("E") is None
    for bad in ("", "Foo", "Ctrl", "Ctrl+Shift+Z, A", "M~", "~E", "M~Foo", 3, None):
        assert not profiles.is_valid(bad), bad
    for good in ("E", "Delete", "F2", "Home", "Backspace", "Ctrl+Shift+Z", "Alt+C", "Ctrl+,", "Num+1",
                 "Ctrl+Num+5", "M~E", "U~L", "M~#", "Shift+F12"):
        assert profiles.is_valid(good), good
    assert profiles.check_bindings(["E", {"key": "Delete", "scope": "viewport"}]) == [
        "E", {"key": "Delete", "scope": "viewport"}]
    for bad in (["Foo"], [{"key": "E", "scope": "nowhere"}], [{"scope": "global"}], 5):
        try:
            profiles.check_bindings(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    base = profiles.resolve(CLASSIC, controls.actions())
    doc = profiles.empty_user("u-00000001", "Test", "classic")
    doc["keys"]["view.frame_all"] = ["M"]
    found = profiles.conflicts(profiles.resolve(doc, controls.actions()))
    assert any(c[1] == "view.frame_all" or c[2] == "view.frame_all" for c in found), found
    assert any(c[0].startswith("M~") for c in found), found
    doc = profiles.empty_user("u-00000002", "Test", "classic")
    doc["keys"]["file.import"] = ["Ctrl+N"]
    found = profiles.conflicts(profiles.resolve(doc, controls.actions()))
    assert ("Ctrl+N", "file.new", "file.import") in found or ("Ctrl+N", "file.import", "file.new") in found
    doc = profiles.empty_user("u-00000003", "Test", "classic")
    doc["keys"]["object.rename"] = ["F3"]
    found = profiles.conflicts(profiles.resolve(doc, controls.actions()))
    assert found == [], found
    doc = profiles.empty_user("u-00000004", "Test", "classic")
    doc["keys"]["object.rename"] = ["E"]
    doc["keys"]["mode.points"] = ["Del"]
    found = profiles.conflicts(profiles.resolve(doc, controls.actions()))
    assert any({c[1], c[2]} == {"mode.points", "object.delete"} for c in found), found
    assert any({c[1], c[2]} == {"mode.points", "tool.delete"} for c in found), found
    assert not any("object.rename" in c for c in found), found
    assert base.keys["object.delete"][0] == ("Delete", "objects")


def test_user_profile_operations() -> None:
    _fresh("user-ops")
    try:
        first = controls.duplicate("classic")
        assert controls.active_id() == first
        docs = {p["id"]: p for p in controls.profiles()}
        assert docs[first]["name"] == "Classic Copy" and docs[first]["base"] == "classic"
        second = controls.duplicate("classic")
        assert {p["id"]: p for p in controls.profiles()}[second]["name"] == "Classic Copy 2"
        third = controls.duplicate(first)
        assert {p["id"]: p for p in controls.profiles()}[third]["name"] == "Classic Copy Copy"
        assert {p["id"]: p for p in controls.profiles()}[third]["base"] == "classic"
        named = controls.duplicate("standard", "Mine")
        assert controls.active().base == "standard" and controls.active().name == "Mine"
        assert [p["id"] for p in controls.profiles()][:2] == ["standard", "classic"]
        names = [p["name"] for p in controls.profiles()][2:]
        assert names == sorted(names, key=str.casefold)
        for pid in profiles.BUILTIN_IDS:
            for call in (lambda: controls.rename(pid, "X"), lambda: controls.delete(pid),
                         lambda: controls.set_keys(pid, "tool.move", ["W"]),
                         lambda: controls.reset_action(pid, "tool.move"),
                         lambda: controls.set_mouse(pid, []), lambda: controls.reset_mouse(pid),
                         lambda: controls.set_cursor(pid, "hold_ms", 200),
                         lambda: controls.reset_cursor(pid, "hold_ms"),
                         lambda: controls.set_modifier(pid, "snap", "ctrl"),
                         lambda: controls.reset_modifier(pid, "snap"),
                         lambda: controls.set_modal(pid, "cancel", ["Q"]),
                         lambda: controls.reset_modal(pid, "cancel"), lambda: controls.reset_profile(pid)):
                try:
                    call()
                except PermissionError:
                    pass
                else:
                    raise AssertionError(pid)
        for bad in ("", "   ", "x" * 49, "classic", "STANDARD", "classic copy"):
            try:
                controls.rename(named, bad)
            except ValueError:
                pass
            else:
                raise AssertionError(bad)
        try:
            controls.duplicate("classic", "Mine")
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate name accepted")
        controls.rename(named, "x" * 48)
        controls.rename(named, "Renamed")
        assert controls.active().name == "Renamed"
        try:
            controls.select("u-ffffffff")
        except KeyError:
            pass
        else:
            raise AssertionError("unknown id selected")
        seen: list[str] = []
        controls.hub().profileChanged.connect(seen.append)
        try:
            controls.set_keys(named, "tool.extrude", ["Ctrl+E"])
            assert controls.active().keys["tool.extrude"] == (("Ctrl+E", "global"),)
            assert "tool.extrude" in controls.active().overridden
            assert seen and seen[-1] == named
            controls.set_keys(named, "tool.weld", [])
            assert controls.active().keys["tool.weld"] == ()
            controls.reset_action(named, "tool.weld")
            assert controls.active().keys["tool.weld"] == (("M", "global"),)
            controls.set_cursor(named, "hold_ms", 200)
            controls.set_modifier(named, "snap", "ctrl")
            controls.set_modal(named, "cancel", ["Q"])
            controls.set_mouse(named, [{"button": "left", "op": "select"}])
            res = controls.active()
            assert res.cursor["hold_ms"] == 200 and controls.cursor("hold_ms") == 200
            assert res.modifiers["snap"] == "ctrl" and controls.modifier_name("snap") == "Ctrl"
            assert res.modal["cancel"] == ("Q",)
            assert len(res.mouse) == 1
            assert {"cursor.hold_ms", "modifiers.snap", "modal.cancel", "mouse"} <= res.overridden
            controls.reset_cursor(named, "hold_ms")
            assert controls.cursor("hold_ms") == 380
            controls.reset_mouse(named)
            assert len(controls.active().mouse) == len(STANDARD["mouse"])
            controls.reset_profile(named)
            res = controls.active()
            assert res.overridden == frozenset()
            assert res.keys == profiles.resolve(STANDARD, controls.actions()).keys
        finally:
            controls.hub().profileChanged.disconnect(seen.append)
        controls.delete(named)
        assert controls.active_id() == "standard"
        controls.select(second)
        controls.delete(second)
        assert controls.active_id() == "classic"
        controls.delete(first)
        controls.delete(third)
        assert [p["id"] for p in controls.profiles()] == ["standard", "classic"]
    finally:
        _done()


def test_store_round_trip_unknown_ids_and_invalid_bindings() -> None:
    target = _fresh("store")
    try:
        pid = controls.duplicate("standard", "Round Trip")
        controls.set_keys(pid, "tool.extrude", ["Ctrl+E", {"key": "X", "scope": "viewport"}])
        controls.set_cursor(pid, "orbit_pivot", "Object")
        assert os.path.exists(target)
        assert not os.path.exists(target + ".tmp")
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["format"] == "quartz-controls-store" and data["version"] == 1
        assert data["selected"] == pid
        data["profiles"][0]["keys"]["ext.someone.unknown"] = ["Ctrl+K"]
        data["profiles"][0]["keys"]["tool.bevel"] = ["Ctrl+B", "NotAKey"]
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        controls.reset()
        assert controls.active_id() == "classic"
        handler = _Records()
        logger = logging.getLogger("quartz_studio.controls")
        logger.addHandler(handler)
        try:
            controls.load()
        finally:
            logger.removeHandler(handler)
        assert any("NotAKey" in r.getMessage() for r in handler.records), [r.getMessage() for r in handler.records]
        assert controls.active_id() == pid
        res = controls.active()
        assert res.name == "Round Trip" and res.base == "standard"
        assert res.keys["tool.extrude"] == (("Ctrl+E", "global"), ("X", "viewport"))
        assert res.keys["tool.bevel"] == (("Ctrl+B", "global"),)
        assert res.cursor["orbit_pivot"] == "Object"
        controls.set_cursor(pid, "hold_ms", 300)
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
        keys = data["profiles"][0]["keys"]
        assert keys["ext.someone.unknown"] == ["Ctrl+K"]
        assert keys["tool.bevel"] == ["Ctrl+B"]
        data["selected"] = "u-0badbad0"
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        controls.reset()
        controls.load()
        assert controls.active_id() == "standard"
        del data["selected"]
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        controls.reset()
        controls.load()
        assert controls.active_id() == "standard"
        assert [p["name"] for p in controls.profiles()][2:] == ["Round Trip"]
        data["profiles"].append({"format": "quartz-controls", "version": 1, "id": "bad", "name": "Broken",
                                 "base": "classic"})
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        controls.reset()
        controls.load()
        assert [p["name"] for p in controls.profiles()][2:] == ["Round Trip"]
    finally:
        _done()


def test_corrupt_store_is_renamed_and_first_run_runs() -> None:
    original = store.previous_install
    try:
        for content, wrong in (("{not json", None), (None, {"format": "other", "version": 1, "profiles": []}),
                               (None, {"format": "quartz-controls-store", "version": 2, "profiles": []}),
                               (None, {"format": "quartz-controls-store", "version": 1, "profiles": {}})):
            target = _fresh("corrupt")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target + ".bad", "w", encoding="utf-8") as fh:
                fh.write("older")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content if content is not None else json.dumps(wrong))
            store.previous_install = lambda: True
            controls.load()
            with open(target + ".bad", encoding="utf-8") as fh:
                bad = fh.read()
            assert bad == (content if content is not None else json.dumps(wrong))
            assert os.path.exists(target)
            assert store.read()["selected"] == "classic"
            assert controls.active_id() == "classic"
    finally:
        store.previous_install = original
        _done()


def test_first_run_follows_previous_install() -> None:
    original = store.previous_install
    try:
        for previous, expected in ((True, "classic"), (False, "standard")):
            target = _fresh(f"first-run-{expected}")
            store.previous_install = lambda previous=previous: previous
            store.first_run()
            assert os.path.exists(target)
            assert store.read()["selected"] == expected
            assert controls.active_id() == expected
            store.previous_install = lambda: not previous
            controls.reset()
            store.first_run()
            assert controls.active_id() == expected
        store.previous_install = original
        project.SETTINGS_FILE = os.path.join(TMP, "settings-present.ini")
        with open(project.SETTINGS_FILE, "w", encoding="utf-8") as fh:
            fh.write("[General]\n")
        assert store.previous_install() is True
        project.SETTINGS_FILE = os.path.join(TMP, "settings-missing.ini")
        assert store.previous_install() is False
        controls.STORE_PATH = None
        assert store.path() == os.path.join(TMP, "controls.json")
    finally:
        store.previous_install = original
        project.SETTINGS_FILE = None
        _done()


def test_store_path_without_overrides_is_the_user_folder() -> None:
    project.SETTINGS_FILE = None
    controls.STORE_PATH = None
    old = os.environ.get("APPDATA")
    try:
        os.environ["APPDATA"] = os.path.join(TMP, "fake-appdata")
        assert store.path() == os.path.join(TMP, "fake-appdata", "Quartz", "controls.json")
        controls.reset()
        controls.select("standard")
        assert not os.path.exists(os.path.join(TMP, "fake-appdata"))
        controls.reset()
    finally:
        if old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old


def test_export_then_import_gives_an_equal_profile() -> None:
    _fresh("export")
    try:
        pid = controls.duplicate("classic", "Exported")
        controls.set_keys(pid, "tool.extrude", ["Ctrl+E"])
        controls.set_keys(pid, "view.frame_all", [])
        controls.set_cursor(pid, "orbit_speed", 0.5)
        controls.set_modifier(pid, "create_child", "ctrl")
        controls.set_mouse(pid, CLASSIC["mouse"][:5])
        path = os.path.join(TMP, "export", "exported.json")
        controls.export_profile(pid, path)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["format"] == "quartz-controls" and data["version"] == 1 and data["base"] == "classic"
        assert set(data["cursor"]) == set(profiles.CURSOR_SPEC)
        new = controls.import_profile(path)
        assert new != pid and controls.active_id() == new
        a, b = controls.resolved(pid), controls.resolved(new)
        assert b.name == "Exported Copy"
        assert (a.keys, a.mouse, a.cursor, a.modifiers, a.modal) == (b.keys, b.mouse, b.cursor, b.modifiers,
                                                                     b.modal)
        again = controls.import_profile(path)
        assert controls.resolved(again).name == "Exported Copy 2"
        builtin_path = os.path.join(TMP, "export", "standard.json")
        controls.export_profile("standard", builtin_path)
        third = controls.import_profile(builtin_path)
        s, t = controls.resolved("standard"), controls.resolved(third)
        assert t.name == "Standard Copy" and t.base == "standard"
        assert (s.keys, s.mouse, s.cursor, s.modifiers, s.modal) == (t.keys, t.mouse, t.cursor, t.modifiers,
                                                                     t.modal)
        bad_cases = [
            {"format": "something-else", "version": 1, "name": "X"},
            {"format": "quartz-controls", "version": 2, "name": "X"},
            {"format": "quartz-controls", "version": 1, "name": "X", "keys": {"tool.bevel": ["NotAKey"]}},
            {"format": "quartz-controls", "version": 1, "name": "X", "mouse": [{"button": "top", "op": "pan"}]},
            {"format": "quartz-controls", "version": 1, "name": "X", "cursor": {"orbit_style": "spin"}},
        ]
        count = len(controls.profiles())
        for k, bad in enumerate(bad_cases):
            bad_path = os.path.join(TMP, "export", f"bad{k}.json")
            with open(bad_path, "w", encoding="utf-8") as fh:
                json.dump(bad, fh)
            try:
                controls.import_profile(bad_path)
            except ValueError:
                pass
            else:
                raise AssertionError(bad)
        not_json = os.path.join(TMP, "export", "not.json")
        with open(not_json, "w", encoding="utf-8") as fh:
            fh.write("[")
        try:
            controls.import_profile(not_json)
        except ValueError:
            pass
        else:
            raise AssertionError("broken json accepted")
        assert len(controls.profiles()) == count
        loose = os.path.join(TMP, "export", "loose.json")
        with open(loose, "w", encoding="utf-8") as fh:
            json.dump({"format": "quartz-controls", "version": 1, "name": "Loose", "base": "nothing"}, fh)
        assert controls.resolved(controls.import_profile(loose)).base == "standard"
    finally:
        _done()


def test_cursor_values_are_clamped_and_enums_fall_back() -> None:
    target = _fresh("cursor")
    try:
        pid = controls.duplicate("standard", "Cursor")
        controls.set_cursor(pid, "orbit_speed", 9.0)
        assert controls.cursor("orbit_speed") == 2.0
        controls.set_cursor(pid, "drag_threshold", 0)
        assert controls.cursor("drag_threshold") == 1
        controls.set_cursor(pid, "chord_ms", 99999)
        assert controls.cursor("chord_ms") == 3000
        controls.set_cursor(pid, "wheel_step", 0.1)
        assert controls.cursor("wheel_step") == 0.5
        for key, value in (("orbit_style", "spin"), ("orbit_pivot", "Nowhere"), ("unknown_key", 1),
                           ("invert_pan", "yes")):
            try:
                controls.set_cursor(pid, key, value)
            except ValueError:
                pass
            else:
                raise AssertionError(key)
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
        data["profiles"][0]["cursor"].update({"orbit_style": "spin", "orbit_pivot": "Nowhere",
                                              "dolly_speed": 5, "hold_ms": 10})
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        controls.reset()
        controls.load()
        assert controls.active_id() == pid
        assert controls.cursor("orbit_style") == "turntable"
        assert controls.cursor("orbit_pivot") == "Center"
        assert controls.cursor("dolly_speed") == 0.05
        assert controls.cursor("hold_ms") == 150
        assert controls.cursor("orbit_speed") == 2.0
    finally:
        _done()


def test_unloaded_state_is_classic_and_touches_no_file() -> None:
    folder = os.path.join(TMP, "unloaded", "missing")
    shutil.rmtree(os.path.join(TMP, "unloaded"), ignore_errors=True)
    project.SETTINGS_FILE = None
    controls.STORE_PATH = os.path.join(folder, "controls.json")
    try:
        controls.reset()
        assert controls.active_id() == "classic"
        res = controls.active()
        assert res.name == "Classic" and res.builtin and res.base is None
        assert controls.cursor("drag_threshold") == 3
        assert [p["id"] for p in controls.profiles()] == ["standard", "classic"]
        assert controls.conflicts() == []
        assert controls.match_press("left", set(), set())["op"] == "select"
        controls.actions()
        assert controls.window() is None
        assert not os.path.exists(folder)
        controls.select("standard")
        assert os.path.exists(controls.STORE_PATH)
        assert controls.active_id() == "standard"
        controls.reset()
        assert controls.active_id() == "classic"
        assert [p["id"] for p in controls.profiles()] == ["standard", "classic"]
    finally:
        _done()


def test_every_frozen_name_is_exported() -> None:
    names = ["STORE_PATH", "SHIPPED_DEFAULT", "hub", "load", "reset", "window", "install", "refresh", "actions",
             "register_action", "run", "active", "active_id", "profiles", "select", "duplicate", "rename",
             "delete", "set_keys", "reset_action", "set_mouse", "reset_mouse", "set_cursor", "reset_cursor",
             "set_modifier", "reset_modifier", "set_modal", "reset_modal", "reset_profile", "export_profile",
             "import_profile", "bindings", "binding_text", "tooltip", "lookup", "hold_keys", "held_set",
             "match_press", "is_navigation_press", "modifier_held", "modifier_name", "modal_key", "cursor",
             "conflicts", "_set_window"]
    for name in names:
        assert hasattr(controls, name), name
        if name not in ("STORE_PATH", "SHIPPED_DEFAULT"):
            assert callable(getattr(controls, name)), name
    assert controls.SHIPPED_DEFAULT == "standard"
    assert isinstance(controls.actions(), dict) and isinstance(controls.profiles(), list)
    assert controls.profiles.CLASSIC is CLASSIC and controls.actions.MENU_IDS[("Edit", "Controls...")] == \
        "app.controls"
    from quartz_studio.controls import Action, Resolved

    assert Resolved.__dataclass_params__.frozen
    assert {"id", "label", "category", "run", "scope", "available", "repeat", "default_keys"} <= set(
        Action.__dataclass_fields__)
    assert isinstance(controls.hub(), controls.ControlsHub) and controls.hub() is controls.hub()


def test_registry_ids_and_extension_actions() -> None:
    _fresh("registry")
    try:
        from quartz_studio.controls import actions

        reg = controls.actions()
        for aid in reg:
            assert actions.ID_RE.match(aid), aid
        for row in ("file.new", "file.export_selection", "edit.delete", "app.controls", "mode.model",
                    "tool.select", "tool.pen", "tool.line_pen", "object.make_editable", "object.rename",
                    "view.frame_objects", "camera.isometric", "camera.pivot.camera", "create.line",
                    "create.empty_polygon", "tool.extrude", "tool.trunk", "tool.delete"):
            assert row in reg, row
        assert reg["view.undo"].repeat and reg["view.undo"].scope == "viewport"
        assert reg["object.delete"].scope == "objects" and reg["edit.delete"].scope == "viewport"
        assert actions.slug(("Extensions", "Script Manager...")) == "menu.extensions.script_manager"
        assert actions.menu_action_id(("File", "Exit")) == "file.exit"
        assert actions.menu_action_id(("Edit", "Controls...")) == "app.controls"
        from quartz_studio.widgets import menu_bar

        for path, handler in menu_bar.SCENE_COMMANDS:
            aid = actions.menu_action_id(path, handler)
            assert aid in reg, (path, aid)
        ran: list[int] = []
        action = controls.register_action("menu.extensions.probe_item", "Probe Item", "Extensions",
                                          lambda: ran.append(1), keys=("Ctrl+Alt+P",))
        assert controls.actions()["menu.extensions.probe_item"] is action
        assert action.default_keys == ("Ctrl+Alt+P",)
        assert controls.active().keys["menu.extensions.probe_item"] == (("Ctrl+Alt+P", "global"),)
        assert profiles.resolve(STANDARD).keys["menu.extensions.probe_item"] == (("Ctrl+Alt+P", "global"),)
        assert controls.run("menu.extensions.probe_item") and ran == [1]
        assert not controls.run("no.such.action")
        actions.collect()
        assert "menu.extensions.probe_item" in controls.actions()
        controls.register_action("menu.extensions.blocked", "Blocked", "Extensions", lambda: ran.append(2),
                                 available=lambda: False)
        assert not controls.run("menu.extensions.blocked") and ran == [1]
        try:
            controls.register_action("Bad Id", "Bad", "Extensions", lambda: None)
        except ValueError:
            pass
        else:
            raise AssertionError("bad id accepted")
    finally:
        from quartz_studio.controls import actions

        actions._EXTRA.pop("menu.extensions.probe_item", None)
        actions._EXTRA.pop("menu.extensions.blocked", None)
        actions.collect()
        _done()


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
