from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import json
import math
import time

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from quartz_studio import objects as _objects
from quartz_studio.ext import store
from quartz_studio.scene import Mesh, Scene
from quartz_studio import anim
from quartz_studio.anim import core
from quartz_studio.anim.player import AnimContext, get_context

APP = QApplication.instance() or QApplication([sys.argv[0]])
LEFT = Qt.MouseButton.LeftButton
NO_MOD = Qt.KeyboardModifier.NoModifier


def _close(a, b, tol=1e-6) -> bool:
    return abs(float(a) - float(b)) <= tol


def _scene() -> Scene:
    s = Scene()
    return s


def _two_keys(s: Scene, ch: str = "position.x", v0: float = 0.0, v1: float = 100.0, f0=0, f1=10, interp=None):
    o = s.objects[0]
    core.insert_key(o, ch, f0, v0, interp=interp, scene=s)
    core.insert_key(o, ch, f1, v1, interp=interp, scene=s)
    return o


def _press(w, x, y, button=LEFT, mods=NO_MOD):
    p = QPointF(x, y)
    w.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, p, w.mapToGlobal(p), button, button, mods))


def _move(w, x, y, button=LEFT, mods=NO_MOD):
    p = QPointF(x, y)
    w.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, p, w.mapToGlobal(p), Qt.MouseButton.NoButton, button, mods))


def _release(w, x, y, button=LEFT, mods=NO_MOD):
    p = QPointF(x, y)
    w.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, p, w.mapToGlobal(p), button,
                                    Qt.MouseButton.NoButton, mods))


def _dbl(w, x, y):
    p = QPointF(x, y)
    w.mouseDoubleClickEvent(QMouseEvent(QEvent.Type.MouseButtonDblClick, p, w.mapToGlobal(p), LEFT, LEFT, NO_MOD))


def _key(w, key, mods=NO_MOD):
    w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods))


def _wheel(w, x, y, dy, mods=NO_MOD):
    p = QPointF(x, y)
    ev = QWheelEvent(p, w.mapToGlobal(p), QPoint(0, 0), QPoint(0, dy), Qt.MouseButton.NoButton, mods,
                     Qt.ScrollPhase.NoScrollPhase, False)
    w.wheelEvent(ev)


def _show(w, width=1200, height=320):
    w.resize(width, height)
    w.show()
    for _ in range(3):
        APP.processEvents()
    return w


def test_time_settings_defaults_and_sanitizing():
    s = _scene()
    t = core.time_settings(s)
    assert t["fps"] == 30 and t["min"] == 0 and t["max"] == 90 and t["frame"] == 0
    t = core.set_time_settings(s, min=10, max=5)
    assert t["min"] == 10 and t["max"] >= t["min"]
    t = core.set_time_settings(s, min=0, max=100)
    t = core.set_time_settings(s, preview_min=-50, preview_max=500)
    assert t["preview_min"] == 0 and t["preview_max"] == 100
    t = core.set_time_settings(s, preview_min=60, preview_max=20)
    assert t["preview_min"] <= t["preview_max"]
    t = core.set_time_settings(s, frame=1000)
    assert t["frame"] == 100
    t = core.set_time_settings(s, fps=0)
    assert t["fps"] == 1
    t = core.set_time_settings(s, fps=10000)
    assert t["fps"] == 240
    try:
        core.set_time_settings(s, bogus=1)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown setting accepted")
    stored = store.get_scene_data(s, core.ANIM_KEY)
    assert isinstance(stored, dict) and stored["max"] == 100


def test_max_follows_preview_when_full_range():
    s = _scene()
    t = core.set_time_settings(s, max=200)
    assert t["preview_max"] == 200
    core.set_time_settings(s, preview_max=150)
    t = core.set_time_settings(s, max=300)
    assert t["preview_max"] == 150


def test_format_time():
    s = _scene()
    core.set_time_settings(s, fps=25)
    assert core.format_time(s, 12, "frames") == "12 F"
    assert core.format_time(s, 50, "seconds") == "2.00 s"
    assert core.format_time(s, 25 * 61 + 3, "smpte") == "01:01:03"
    assert _close(core.frame_to_seconds(s, 50), 2.0)
    assert _close(core.seconds_to_frame(s, 2.0), 50)


def test_linear_interpolation_exact():
    s = _scene()
    o = _two_keys(s, interp="linear")
    keys = core.get_track(o, "position.x")
    for f, v in ((0, 0), (2.5, 25), (5, 50), (10, 100), (-3, 0), (14, 100)):
        assert _close(core.evaluate_track(keys, f), v)


def test_step_interpolation_holds():
    s = _scene()
    o = _two_keys(s, interp="step")
    keys = core.get_track(o, "position.x")
    assert _close(core.evaluate_track(keys, 9.999), 0)
    assert _close(core.evaluate_track(keys, 10), 100)


def test_spline_two_keys_is_smoothstep():
    s = _scene()
    o = _two_keys(s, interp="spline")
    keys = core.get_track(o, "position.x")
    for u in (0.1, 0.25, 0.5, 0.75, 0.9):
        expect = 100 * (3 * u * u - 2 * u * u * u)
        assert _close(core.evaluate_track(keys, 10 * u), expect, 1e-6), (u, core.evaluate_track(keys, 10 * u))


def test_auto_slopes_catmull_and_clamp():
    slopes = core.auto_slopes([0, 10, 20], [0.0, 50.0, 100.0])
    assert _close(slopes[0], 0) and _close(slopes[2], 0)
    assert _close(slopes[1], 5.0)
    peak = core.auto_slopes([0, 10, 20], [0.0, 50.0, 0.0])
    assert _close(peak[1], 0.0)
    lopsided = core.auto_slopes([0, 10, 11], [0.0, 1.0, 100.0])
    assert lopsided[1] <= 3 * 0.1 + 1e-9
    vec = core.auto_slopes([0, 10, 20], [np.zeros(2), np.array([10.0, -10.0]), np.array([20.0, 0.0])])
    assert np.allclose(vec[1], [1.0, 0.0])


def test_spline_no_overshoot_monotone_data():
    s = _scene()
    o = s.objects[0]
    for f, v in ((0, 0), (10, 10), (12, 100), (30, 110)):
        core.insert_key(o, "position.y", f, v, scene=s)
    keys = core.get_track(o, "position.y")
    vals = [core.evaluate_track(keys, f / 4) for f in range(0, 121)]
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))
    assert min(vals) >= -1e-9 and max(vals) <= 110 + 1e-9


def test_spline_extremum_flat():
    s = _scene()
    o = s.objects[0]
    for f, v in ((0, 0), (10, 50), (20, 0)):
        core.insert_key(o, "position.y", f, v, scene=s)
    keys = core.get_track(o, "position.y")
    assert core.evaluate_track(keys, 9) < 50 and core.evaluate_track(keys, 11) < 50
    assert _close(core.evaluate_track(keys, 9), core.evaluate_track(keys, 11), 1e-9)


def test_ease_flattens_tangents():
    s = _scene()
    o = s.objects[0]
    for f, v in ((0, 0), (10, 50), (20, 100)):
        core.insert_key(o, "position.x", f, v, scene=s)
    keys = core.get_track(o, "position.x")
    before = core.evaluate_track(keys, 10.01) - core.evaluate_track(keys, 9.99)
    assert before > 0.05
    core.set_key_attrs([(o, "position.x", 10)], ease="both")
    keys = core.get_track(o, "position.x")
    right = (core.evaluate_track(keys, 10.0001) - core.evaluate_track(keys, 10)) / 0.0001
    left = (core.evaluate_track(keys, 10) - core.evaluate_track(keys, 9.9999)) / 0.0001
    assert abs(right) < 1e-2 and abs(left) < 1e-2
    core.set_key_attrs([(o, "position.x", 10)], ease="out")
    keys = core.get_track(o, "position.x")
    tin, tout = core.key_tangents(keys, 1)
    assert _close(tout[1], 0) and tin[1] < 0


def test_explicit_tangents_linear_equivalence_and_overshoot():
    s = _scene()
    o = _two_keys(s, f0=0, f1=30, v0=0, v1=90)
    assert core.set_tangents(o, "position.x", 0, out_tan=[10, 30])
    assert core.set_tangents(o, "position.x", 30, in_tan=[-10, -30])
    keys = core.get_track(o, "position.x")
    for f in (3, 7.5, 15, 22, 29):
        assert _close(core.evaluate_track(keys, f), 3 * f, 1e-6)
    core.set_tangents(o, "position.x", 0, out_tan=[10, 300])
    keys = core.get_track(o, "position.x")
    peak = max(core.evaluate_track(keys, f) for f in range(31))
    assert peak > 90
    assert core.set_tangents(o, "position.x", 99, out_tan=[1, 1]) is False


def test_set_tangents_clamps_direction():
    s = _scene()
    o = _two_keys(s)
    core.set_tangents(o, "position.x", 10, in_tan=[5, 3])
    k = core.get_track(o, "position.x")[1]
    assert k["in_tan"][0] < 0 and k["out_tan"] is not None


def test_loop_modes():
    s = _scene()
    o = _two_keys(s, interp="linear")
    ch = "position.x"
    assert _close(core.evaluate_channel(o, ch, 25), 100)
    core.set_loop(o, ch, after="repeat")
    assert _close(core.evaluate_channel(o, ch, 15), 50)
    assert _close(core.evaluate_channel(o, ch, 22), 20)
    core.set_loop(o, ch, after="offset")
    assert _close(core.evaluate_channel(o, ch, 15), 150)
    assert _close(core.evaluate_channel(o, ch, 25), 250)
    core.set_loop(o, ch, after="oscillate")
    assert _close(core.evaluate_channel(o, ch, 12), 80)
    assert _close(core.evaluate_channel(o, ch, 22), 20)
    core.set_loop(o, ch, before="repeat")
    assert _close(core.evaluate_channel(o, ch, -3), 70)
    core.set_loop(o, ch, before="oscillate")
    assert _close(core.evaluate_channel(o, ch, -3), 30)
    core.set_loop(o, ch, before="offset")
    assert _close(core.evaluate_channel(o, ch, -3), -30)
    assert core.loop_mode(o, ch) == ("offset", "oscillate")
    core.set_loop(o, ch, "constant", "constant")
    assert core.track_modes(o) == {}
    try:
        core.set_loop(o, ch, after="wobble")
    except ValueError:
        pass
    else:
        raise AssertionError


def test_evaluate_applies_transform_visibility_and_param():
    s = _scene()
    o = s.objects[0]
    core.insert_key(o, "rotation.y", 0, 0, interp="linear", scene=s)
    core.insert_key(o, "rotation.y", 10, 90, interp="linear", scene=s)
    core.insert_key(o, "scale.z", 0, 1, interp="linear", scene=s)
    core.insert_key(o, "scale.z", 10, 3, interp="linear", scene=s)
    core.insert_key(o, core.VISIBILITY, 0, 1.0, scene=s)
    core.insert_key(o, core.VISIBILITY, 6, 0.0, scene=s)
    assert core.get_track(o, core.VISIBILITY)[0]["interp"] == "step"
    count = {"n": 0}
    s.changed.connect(lambda: count.__setitem__("n", count["n"] + 1))
    touched = core.evaluate(s, 5)
    assert touched == [o] and count["n"] == 1
    assert _close(o.rotation[1], 45) and _close(o.scale[2], 2) and o.enabled
    core.evaluate(s, 7)
    assert not o.enabled
    assert core.evaluate(s, 7) == []
    cube = s.add_parametric("cube")
    core.insert_key(cube, "param.size_x", 0, 100, interp="linear", scene=s)
    core.insert_key(cube, "param.size_x", 10, 300, interp="linear", scene=s)
    core.insert_key(cube, "param.segments_x", 0, 1, interp="linear", scene=s)
    core.insert_key(cube, "param.segments_x", 10, 4, interp="linear", scene=s)
    core.insert_key(cube, "param.fillet", 0, False, scene=s)
    core.insert_key(cube, "param.fillet", 5, True, scene=s)
    assert core.get_track(cube, "param.fillet")[0]["interp"] == "step"
    core.evaluate(s, 5)
    assert _close(cube.params["size_x"], 200)
    assert cube.params["segments_x"] == 2 and isinstance(cube.params["segments_x"], int)
    assert cube.params["fillet"] is True
    xs = cube.mesh.points[:, 0]
    assert _close(xs.max() - xs.min(), 200, 1e-6)


def test_pla_linear_blend():
    s = _scene()
    o = s.objects[0]
    base = o.mesh.points.copy()
    core.set_key(o, [core.POINTS], 0, s)
    o.mesh.points = base * 2.0
    core.set_key(o, [core.POINTS], 10, s)
    assert core.get_track(o, core.POINTS)[0]["interp"] == "linear"
    core.evaluate(s, 5)
    assert np.allclose(o.mesh.points, base * 1.5)
    core.evaluate(s, 0)
    assert np.allclose(o.mesh.points, base)
    o.mesh = Mesh.cube(50.0)
    o.mesh.points = np.vstack([o.mesh.points, [[0, 0, 0]]])
    assert core.apply_channel(o, core.POINTS, base) == ""


def test_set_key_records_and_replaces():
    s = _scene()
    o = s.objects[0]
    o.position = np.array([1.0, 2.0, 3.0])
    assert core.set_key(o, None, 5, s) == 9
    assert sorted(core.channels_of(o)) == sorted(core.TRANSFORM_CHANNELS)
    o.position = np.array([7.0, 2.0, 3.0])
    core.set_key(o, ["position.x"], 5, s)
    assert len(core.get_track(o, "position.x")) == 1
    assert _close(core.get_track(o, "position.x")[0]["value"], 7)
    core.set_time_settings(s, default_interp="linear")
    core.set_key(o, ["position.y"], 9, s)
    assert core.get_track(o, "position.y")[1]["interp"] == "linear"
    assert core.set_key(o, ["param.nope"], 5, s) == 0
    try:
        core.insert_key(o, "param.nope", 0)
    except KeyError:
        pass
    else:
        raise AssertionError


def test_record_active_and_points_use_selection():
    s = _scene()
    a = s.objects[0]
    b = s.add_object("Other", Mesh.cube(10.0))
    s.set_active(b)
    assert core.record_active(s, None, 3) == 9
    assert core.has_animation(b) and not core.has_animation(a)
    assert core.record_points(s, 4) == 1
    assert core.channels_of(b)[-1] == core.POINTS
    s.set_active(None)
    assert core.record_active(s) == 0


def test_delete_and_clear():
    s = _scene()
    o = s.objects[0]
    core.set_key(o, None, 0, s)
    core.set_key(o, None, 10, s)
    core.set_key(o, None, 20, s)
    assert core.delete_key(o, "position.x", 10)
    assert not core.delete_key(o, "position.x", 10)
    assert core.delete_keys_at(o, 20) == 9
    assert core.key_frames(o) == [0, 10]
    assert core.delete_keys([(o, "scale.x", 0), (o, "scale.y", 0)]) == 2
    assert core.clear_tracks(o, ["scale.x"]) == 1
    assert "scale.x" not in core.tracks(o)
    core.set_loop(o, "position.y", after="repeat")
    total = sum(len(k) for k in core.tracks(o).values())
    assert core.clear_tracks(o) == total
    assert not core.has_animation(o) and core.track_modes(o) == {}


def test_move_keys_collision_and_snap():
    s = _scene()
    o = s.objects[0]
    for f, v in ((0, 0), (10, 10), (20, 20)):
        core.insert_key(o, "position.x", f, v, scene=s)
    refs = core.move_keys([(o, "position.x", 0)], 10)
    assert refs == [(o, "position.x", 10)]
    keys = core.get_track(o, "position.x")
    assert [k["frame"] for k in keys] == [10, 20]
    assert _close(keys[0]["value"], 0)
    refs = core.move_keys([(o, "position.x", 10), (o, "position.x", 20)], 2.4)
    assert [k["frame"] for k in core.get_track(o, "position.x")] == [12, 22]
    refs = core.move_keys(refs, 0.25, snap=False)
    assert _close(core.get_track(o, "position.x")[0]["frame"], 12.25)


def test_scale_keys_pivot():
    s = _scene()
    o = s.objects[0]
    for f in (10, 20, 30):
        core.insert_key(o, "position.z", f, f, scene=s)
    refs = core.all_refs(o)
    out = core.scale_keys(refs, 2.0)
    assert [k["frame"] for k in core.get_track(o, "position.z")] == [10, 30, 50]
    assert len(out) == 3
    core.scale_keys(core.all_refs(o), 0.5, pivot=0)
    assert [k["frame"] for k in core.get_track(o, "position.z")] == [5, 15, 25]
    for bad in (0.0, -1.0, float("nan")):
        try:
            core.scale_keys(core.all_refs(o), bad, pivot=15)
        except ValueError:
            pass
        else:
            raise AssertionError(f"factor {bad} accepted")
    assert [k["frame"] for k in core.get_track(o, "position.z")] == [5, 15, 25]
    core.scale_keys(core.all_refs(o), 0.01, pivot=5)
    assert [k["frame"] for k in core.get_track(o, "position.z")] == [5, 6, 7]
    assert core.scale_keys([], 2) == []


def test_value_edits_and_attrs():
    s = _scene()
    o = _two_keys(s)
    assert core.offset_key_values([(o, "position.x", 0), (o, "position.x", 10)], 5) == 2
    keys = core.get_track(o, "position.x")
    assert _close(keys[0]["value"], 5) and _close(keys[1]["value"], 105)
    assert core.set_key_value(o, "position.x", 10, 42)
    assert not core.set_key_value(o, "position.x", 11, 42)
    assert core.set_key_attrs(core.all_refs(o), interp="step") == 2
    assert all(k["interp"] == "step" for k in core.get_track(o, "position.x"))
    try:
        core.set_key_attrs([], interp="cubic")
    except ValueError:
        pass
    else:
        raise AssertionError
    core.set_key_attrs(core.all_refs(o), interp="spline")
    core.set_tangents(o, "position.x", 0, out_tan=[3, 9])
    assert core.flatten_tangents([(o, "position.x", 0)]) == 1
    k = core.get_track(o, "position.x")[0]
    assert _close(k["out_tan"][1], 0) and _close(k["in_tan"][1], 0)
    assert core.reset_tangents([(o, "position.x", 0)]) == 1
    assert core.get_track(o, "position.x")[0]["out_tan"] is None


def test_copy_paste_single_and_multi():
    s = _scene()
    a = s.objects[0]
    b = s.add_object("B", Mesh.cube(10.0))
    core.insert_key(a, "position.x", 10, 1.0, scene=s)
    core.insert_key(a, "position.x", 14, 2.0, scene=s)
    clip = core.copy_keys(core.all_refs(a))
    assert clip["base"] == 10 and len(clip["items"]) == 2
    json.dumps(store.to_json(clip["items"][0]["key"]))
    refs = core.paste_keys(s, clip, 30, [b])
    assert sorted(r[2] for r in refs) == [30, 34]
    assert _close(core.evaluate_channel(b, "position.x", 34), 2.0)
    core.insert_key(b, "position.y", 0, 9.0, scene=s)
    clip2 = core.copy_keys(core.all_refs(a) + core.all_refs(b, ["position.y"]))
    core.clear_tracks(a)
    core.clear_tracks(b)
    out = core.paste_keys(s, clip2, 100, [])
    names = sorted({r[0].name for r in out})
    assert names == ["B", "Cube"]
    assert core.key_frames(a) == [110, 114] and core.key_frames(b) == [100]
    assert core.paste_keys(s, {}, 0) == []


def test_paste_points_shape_guard():
    s = _scene()
    a = s.objects[0]
    b = s.add_object("Line", Mesh.empty())
    core.set_key(a, [core.POINTS], 0, s)
    clip = core.copy_keys(core.all_refs(a))
    assert core.paste_keys(s, clip, 0, [b]) == []


def test_key_frames_and_navigation():
    s = _scene()
    a = s.objects[0]
    b = s.add_object("B", Mesh.cube(10.0))
    core.insert_key(a, "position.x", 5, 0, scene=s)
    core.insert_key(b, "position.y", 12, 0, scene=s)
    core.insert_key(b, "position.y", 2.5, 0, scene=s)
    assert core.key_frames([a, b]) == [2.5, 5, 12]
    assert core.next_key_frame([a, b], 5) == 12
    assert core.prev_key_frame([a, b], 5) == 2.5
    assert core.next_key_frame([a, b], 12) is None
    assert core.key_range([a, b]) == (2.5, 12.0)
    assert core.refs_at_frame([a, b], 12) == [(b, "position.y", 12)]
    assert core.animated_objects(s) == [a, b]


def test_json_roundtrip_keeps_evaluation():
    s = _scene()
    o = s.objects[0]
    core.set_key(o, ["position.x", core.POINTS], 0, s)
    o.position[0] = 50
    o.mesh.points = o.mesh.points + 10
    core.set_key(o, ["position.x", core.POINTS], 10, s)
    core.set_loop(o, "position.x", after="oscillate")
    data = json.loads(json.dumps(store.to_json(dict(store.object_extras(o)))))
    restored = store.from_json(data)
    s2 = _scene()
    o2 = s2.objects[0]
    for key, value in restored.items():
        store.set_object(o2, key, value)
    core.evaluate(s2, 15)
    assert _close(o2.position[0], 25)
    core.evaluate(s2, 5)
    assert np.allclose(o2.mesh.points, Mesh.cube(200.0).points + 5)


def test_bake_object():
    s = _scene()
    o = _two_keys(s)
    core.set_time_settings(s, min=0, max=10)
    n = core.bake_object(s, o)
    keys = core.get_track(o, "position.x")
    assert n == 11 and len(keys) == 11
    assert all(k["interp"] == "linear" for k in keys)
    assert _close(keys[5]["value"], 50)


def test_value_range_and_labels():
    s = _scene()
    o = _two_keys(s)
    lo, hi = core.value_range(o, "position.x", 0, 10)
    assert lo <= 0 and hi >= 100
    assert core.channel_label("rotation.z") == "Rotation Z"
    cube = s.add_parametric("cube")
    assert core.channel_label("param.size_x", cube) == "Size X"
    assert "param.size_x" in core.param_channels(cube, numeric_only=True)
    assert "param.fillet" not in core.param_channels(cube, numeric_only=True)
    assert core.is_scalar_channel(o, "position.x") and not core.is_scalar_channel(o, core.POINTS)


def test_snapshot_restore():
    s = _scene()
    o = _two_keys(s)
    snap = core.snapshot_tracks([o])
    core.move_keys(core.all_refs(o), 5)
    assert core.key_frames(o) == [5, 15]
    core.restore_tracks(snap)
    assert core.key_frames(o) == [0, 10]


def test_player_navigation_and_loop():
    s = _scene()
    ctx = AnimContext(s)
    pl = ctx.player
    core.set_time_settings(s, min=0, max=20, preview_min=5, preview_max=15)
    assert pl.go_start() == 5 and pl.go_end() == 15
    assert pl.go_doc_start() == 0 and pl.go_doc_end() == 20
    pl.set_frame(15)
    assert pl.advance(1) == 5
    pl.set_frame(5)
    assert pl.advance(-1) == 15
    core.set_time_settings(s, loop=False)
    pl.play(1)
    assert pl.is_playing()
    pl.set_frame(14)
    pl.advance(3)
    assert core.current_frame(s) == 15 and not pl.is_playing()
    pl.set_frame(20)
    assert pl.step(5) == 20 and pl.step(-25) == 0
    assert pl.next_frame() == 1 and pl.prev_frame() == 0
    o = s.objects[0]
    for f in (3, 9, 12):
        core.insert_key(o, "position.x", f, f, scene=s)
    assert pl.next_key() == 3 and pl.next_key() == 9 and pl.next_key() == 12 and pl.next_key() is None
    assert pl.prev_key() == 9
    ctx.close()


def test_player_ticks_and_states():
    s = _scene()
    ctx = AnimContext(s)
    pl = ctx.player
    states = []
    pl.stateChanged.connect(states.append)
    core.set_time_settings(s, min=0, max=10, play_mode="all_frames", loop=True)
    o = _two_keys(s, interp="linear")
    pl.play(1)
    for _ in range(4):
        pl._tick()
    assert core.current_frame(s) == 4
    assert _close(o.position[0], 40)
    pl.stop()
    pl._tick()
    assert core.current_frame(s) == 4
    pl.toggle(-1)
    pl._tick()
    assert core.current_frame(s) == 3
    pl.toggle(-1)
    assert states == [1, 0, -1, 0]
    core.set_time_settings(s, play_mode="realtime", fps=1000 // 8)
    pl.set_frame(0)
    pl.play(1)
    pl._clock.restart()
    pl._start_frame = 0.0
    pl._last = 0.0
    import time
    time.sleep(0.05)
    pl._tick()
    assert core.current_frame(s) >= 3
    pl.stop()
    pl.set_frame(10)
    pl.play(1)
    assert core.current_frame(s) == 0
    pl.stop()
    ctx.close()


def test_autokey_records_changed_channels_only():
    s = _scene()
    ctx = AnimContext(s)
    ak = ctx.autokey
    ak.set_enabled(True)
    core.set_frame(s, 0)
    s.set_object_position(0, 25.0)
    assert core.channels_of(s.objects[0]) == ["position.x"]
    ctx.set_frame(10)
    s.set_object_rotation(1, 45.0)
    o = s.objects[0]
    assert core.channels_of(o) == ["position.x", "rotation.y"]
    assert core.key_frames(o, ["rotation.y"]) == [10]
    core.evaluate(s, 0)
    assert core.key_frames(o) == [0, 10]
    ctx.set_frame(5)
    assert core.key_frames(o) == [0, 10]
    ak.set_enabled(False)
    s.set_object_position(2, 9.0)
    assert "position.z" not in core.channels_of(o)
    assert ak.toggle() is True
    ctx.close()


def test_autokey_ignores_evaluated_values():
    s = _scene()
    ctx = AnimContext(s)
    o = _two_keys(s, interp="linear")
    ctx.autokey.set_enabled(True)
    core.set_frame(s, 5)
    assert _close(o.position[0], 50)
    s.set_object_rotation(2, 30.0)
    assert core.key_frames(o, ["position.x"]) == [0, 10]
    assert core.key_frames(o, ["rotation.z"]) == [5]
    ctx.close()


def test_tracks_survive_scene_undo():
    s = _scene()
    ctx = AnimContext(s)
    o = _two_keys(s)
    core.set_loop(o, "position.x", after="repeat")
    s.set_object_position(1, 5.0)
    assert s.undo()
    restored = s.objects[0]
    assert restored is not o
    assert core.key_frames(restored) == [0, 10]
    assert core.loop_mode(restored, "position.x") == ("constant", "repeat")
    assert s.redo()
    assert core.key_frames(s.objects[0]) == [0, 10]
    ctx.close()


def test_context_selection_clipboard_and_signals():
    s = _scene()
    ctx = AnimContext(s)
    frames = []
    keys_changed = []
    ctx.frameChanged.connect(frames.append)
    ctx.keysChanged.connect(lambda: keys_changed.append(1))
    o = s.objects[0]
    core.insert_key(o, "position.x", 0, 0, scene=s)
    core.insert_key(o, "position.x", 10, 10, scene=s)
    assert keys_changed
    ctx.set_frame(7)
    assert frames and frames[-1] == 7.0
    ctx.select([(o, "position.x", 0)])
    ctx.select([(o, "position.x", 10)], "add")
    assert len(ctx.selection) == 2
    ctx.select([(o, "position.x", 10)], "toggle")
    assert ctx.selection == [(o, "position.x", 0)]
    ctx.select([(o, "position.x", 0)], "remove")
    assert ctx.selection == []
    ctx.select(core.all_refs(o))
    assert ctx.copy_selected() == 2
    refs = ctx.paste(40)
    assert sorted(r[2] for r in refs) == [40, 50] and ctx.selection == refs
    assert ctx.delete_selected() == 2
    assert core.key_frames(o) == [0, 10]
    ctx.select([(o, "position.x", 0)])
    core.delete_key(o, "position.x", 0)
    assert ctx.selection == []
    ctx.select(core.all_refs(o))
    ctx.set_loop(after="repeat")
    assert core.loop_mode(o, "position.x") == ("constant", "repeat")
    ctx.set_frame(10)
    assert ctx.delete_at_frame() == 1
    ctx.record()
    assert core.key_frames(o) == [10]
    assert ctx.delete_tracks() == 9 and not core.has_animation(o)
    ctx.close()


def test_get_context_is_cached_per_scene():
    s = _scene()
    a = get_context(s)
    assert get_context(s) is a
    s2 = _scene()
    assert get_context(s2) is not a


def test_registry_functions():
    names = [a[0] for a in anim.key_actions()]
    for n in ("Record Active Objects", "Play Forwards", "Go to Start", "Go to Previous Frame", "Go to Next Frame",
              "Add Parameter Keys", "Record Visibility", "Record Points", "Clear Points"):
        assert n in names
    assert len(set(names)) == len(names)
    shortcuts = {a[0]: a[1] for a in anim.key_actions()}
    assert shortcuts["Record Active Objects"] == "F9" and shortcuts["Play Forwards"] == "F8"
    assert shortcuts["Go to Start"] == "Shift+G" and shortcuts["Go to Previous Frame"] == ","
    assert shortcuts["Go to Next Frame"] == "." and shortcuts["Go to End"] == "Shift+F"
    used = [sc for sc in shortcuts.values() if sc]
    assert len(set(used)) == len(used)
    assert all(callable(a[2]) for a in anim.key_actions())
    cmds = anim.commands()
    assert all(isinstance(p, tuple) and p[0] == "Animate" and callable(fn) for p, fn in cmds)
    assert anim.pages() == [("Animate", ["Timeline", "Dope Sheet", "F-Curves"])]
    titles = [d[0] for d in anim.docks()]
    assert titles == ["Timeline", "Dope Sheet", "F-Curves"]
    assert all(d[2] in ("left", "right", "bottom") for d in anim.docks())


def test_actions_run_on_global_scene():
    from quartz_studio.scene import get_scene
    s = get_scene()
    ctx = get_context(s)
    acts = {a[0]: a[2] for a in anim.key_actions()}
    acts["Go to Start"]()
    start = core.current_frame(s)
    acts["Go to Next Frame"]()
    assert core.current_frame(s) == start + 1
    acts["Go to Previous Frame"]()
    acts["Record Active Objects"]()
    assert core.has_animation(s.active)
    acts["Play Forwards"]()
    assert ctx.player.is_playing()
    acts["Stop"]()
    assert not ctx.player.is_playing()
    loop = core.time_settings(s)["loop"]
    acts["Loop Playback"]()
    assert core.time_settings(s)["loop"] != loop
    acts["Loop Playback"]()
    acts["Autokeying"]()
    assert ctx.autokey.enabled
    acts["Autokeying"]()
    cmds = {p: fn for p, fn in anim.commands()}
    ctx.select(core.all_refs(s.active))
    cmds[("Animate", "Interpolation", "Linear")]()
    assert all(k["interp"] == "linear" for k in core.get_track(s.active, "position.x"))
    cmds[("Animate", "Ease", "Ease In Out")]()
    assert all(k["ease"] == "both" for k in core.get_track(s.active, "position.x"))
    core.set_key(s.active, ["position.x"], 40, s)
    assert acts["Preview Range to Keys"]() == (0, 40)
    assert acts["Bake Objects"]() > 0
    acts["Delete Tracks of Active Objects"]()
    assert not core.has_animation(s.active)


def test_timeline_bar_controls():
    from quartz_studio.anim.timeline import TimelineBar
    s = _scene()
    o = s.objects[0]
    bar = _show(TimelineBar(s))
    ctx = bar.ctx
    bar.max_spin.setValue(120)
    assert core.time_settings(s)["max"] == 120
    bar.min_spin.setValue(-10)
    assert core.time_settings(s)["min"] == -10
    bar.pmin_spin.setValue(0)
    bar.pmax_spin.setValue(60)
    t = core.time_settings(s)
    assert t["preview_min"] == 0 and t["preview_max"] == 60
    bar.frame_spin.setValue(20)
    assert core.current_frame(s) == 20
    bar.fps_spin.setValue(24)
    assert core.fps(s) == 24
    bar.btn_start.click()
    assert core.current_frame(s) == 0
    bar.btn_end.click()
    assert core.current_frame(s) == 60
    bar.btn_prev.click()
    assert core.current_frame(s) == 59 and bar.frame_spin.value() == 59
    bar.btn_next.click()
    assert core.current_frame(s) == 60
    bar.btn_record.click()
    assert core.key_frames(o) == [60]
    bar.frame_spin.setValue(30)
    o.position[0] = 5
    bar.btn_record.click()
    bar.btn_prev_key.click()
    assert core.current_frame(s) == 30 or core.current_frame(s) < 60
    bar.btn_next_key.click()
    assert core.current_frame(s) == 60
    bar.btn_play.click()
    assert ctx.player.direction == 1 and bar.btn_play.isChecked()
    bar.btn_play.click()
    assert not ctx.player.is_playing() and not bar.btn_play.isChecked()
    bar.btn_back.click()
    assert ctx.player.direction == -1 and bar.btn_back.isChecked()
    ctx.player.stop()
    assert not bar.btn_back.isChecked()
    bar.btn_autokey.click()
    assert ctx.autokey.enabled
    bar.btn_autokey.click()
    assert not ctx.autokey.enabled
    bar.btn_loop.click()
    assert core.time_settings(s)["loop"] is False
    bar.interp_combo.setCurrentIndex(bar.interp_combo.findData("step"))
    assert core.time_settings(s)["default_interp"] == "step"
    bar.play_combo.setCurrentIndex(bar.play_combo.findData("all_frames"))
    assert core.time_settings(s)["play_mode"] == "all_frames"
    bar.mode_combo.setCurrentIndex(bar.mode_combo.findData("seconds"))
    assert bar.ruler.time_mode == "seconds" and bar.readout.text().endswith("s")
    bar.btn_pla.click()
    assert core.POINTS in core.channels_of(o)
    core.set_time_settings(s, preview_min=10)
    assert bar.pmin_spin.value() == 10
    bar.grab()


def test_timeline_ruler_mouse():
    from quartz_studio.anim.timeline import TimelineBar
    s = _scene()
    o = s.objects[0]
    core.set_time_settings(s, min=0, max=100)
    core.set_key(o, ["position.x"], 20, s)
    core.set_key(o, ["position.x"], 50, s)
    bar = _show(TimelineBar(s))
    r = bar.ruler
    y = 32
    _press(r, r.frame_to_x(70), y)
    _move(r, r.frame_to_x(72), y)
    _release(r, r.frame_to_x(72), y)
    assert core.current_frame(s) == 72
    _press(r, r.frame_to_x(20), y)
    assert bar.ctx.selection == [(o, "position.x", 20)]
    _move(r, r.frame_to_x(30), y)
    r.grab()
    _release(r, r.frame_to_x(30), y)
    assert core.key_frames(o) == [30, 50]
    assert bar.ctx.selection == [(o, "position.x", 30)]
    _press(r, r.frame_to_x(50), y, mods=Qt.KeyboardModifier.ShiftModifier)
    _release(r, r.frame_to_x(50), y)
    assert len(bar.ctx.selection) == 2
    _key(r, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    _key(r, Qt.Key.Key_Delete)
    assert not core.has_animation(o)
    core.set_frame(s, 80)
    _key(r, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert core.key_frames(o) == [80, 100]
    _wheel(r, 10, 10, -120)
    assert core.current_frame(s) == 81
    _key(r, Qt.Key.Key_Left)
    assert core.current_frame(s) == 80
    _dbl(r, r.frame_to_x(10), y)
    assert 10 in core.key_frames(o) and core.current_frame(s) == 10
    st = bar.strip
    x0 = r.frame_to_x(0)
    _press(st, x0, 6)
    _move(st, r.frame_to_x(25), 6)
    _release(st, r.frame_to_x(25), 6)
    assert core.time_settings(s)["preview_min"] == 25
    xm = r.frame_to_x(60)
    _press(st, xm, 6)
    _move(st, r.frame_to_x(50), 6)
    _release(st, r.frame_to_x(50), 6)
    t = core.time_settings(s)
    assert t["preview_min"] == 15 and t["preview_max"] == 90
    _dbl(st, xm, 6)
    t = core.time_settings(s)
    assert t["preview_min"] == 0 and t["preview_max"] == 100


def test_dope_sheet_interactions():
    from quartz_studio.anim.dopesheet import HEADER_H, NAME_W, ROW_H, DopeSheet
    s = _scene()
    o = s.objects[0]
    b = s.add_object("B", Mesh.cube(10.0))
    s.set_active(o)
    core.insert_key(o, "position.x", 0, 0, scene=s)
    core.insert_key(o, "position.x", 10, 10, scene=s)
    core.insert_key(o, "position.y", 10, 5, scene=s)
    core.insert_key(b, "scale.x", 5, 2, scene=s)
    ds = _show(DopeSheet(s), 1000, 400)
    cv = ds.canvas
    rows = cv.rows()
    assert [r[0] for r in rows] == ["object", "channel", "channel", "object", "channel"]
    cv.frame_all()
    ry = lambda i: HEADER_H + i * ROW_H + ROW_H / 2
    _press(cv, cv.frame_to_x(10), ry(1))
    _release(cv, cv.frame_to_x(10), ry(1))
    assert ds.ctx.selection == [(o, "position.x", 10)]
    assert ds.btn_delete.isEnabled()
    _press(cv, cv.frame_to_x(10), ry(0))
    _release(cv, cv.frame_to_x(10), ry(0))
    assert sorted(r[1] for r in ds.ctx.selection) == ["position.x", "position.y"]
    _press(cv, cv.frame_to_x(10), ry(0))
    _move(cv, cv.frame_to_x(13), ry(0))
    cv.grab()
    _release(cv, cv.frame_to_x(13), ry(0))
    assert core.key_frames(o) == [0, 13]
    _press(cv, cv.frame_to_x(-0.3), ry(1) - 4)
    _move(cv, cv.frame_to_x(6), ry(4) + 4)
    cv.grab()
    _release(cv, cv.frame_to_x(6), ry(4) + 4)
    assert sorted((r[0].name, r[2]) for r in ds.ctx.selection) == [("B", 5), ("Cube", 0)]
    ds.btn_linear.click()
    assert core.get_track(o, "position.x")[0]["interp"] == "linear"
    ds.btn_right.click()
    assert core.key_frames(b) == [6]
    ds.scale_spin.setValue(3.0)
    ds.btn_scale.click()
    assert core.key_frames(b) == [16] and core.key_frames(o, ["position.x"]) == [1, 13]
    ds.btn_copy.click()
    ds.btn_delete.click()
    assert not core.has_animation(b)
    core.set_frame(s, 40)
    ds.btn_paste.click()
    assert core.key_frames(b) == [55]
    _dbl(cv, cv.frame_to_x(5), ry(2))
    assert 5 in core.key_frames(o, ["position.y"])
    _press(cv, NAME_W / 2, ry(1))
    assert all(r[1] == "position.x" for r in ds.ctx.selection) and len(ds.ctx.selection) == 2
    _press(cv, 8, ry(0))
    assert cv.rows()[1][0] == "object"
    _press(cv, 8, ry(0))
    assert cv.rows()[1][0] == "channel"
    ds.btn_collapse.click()
    assert len(cv.rows()) == 2
    ds.btn_expand.click()
    ds.btn_active.click()
    assert [r[1] for r in cv.rows() if r[0] == "object"] == [o]
    ds.btn_active.click()
    _press(cv, cv.frame_to_x(30), HEADER_H / 2)
    _move(cv, cv.frame_to_x(33), HEADER_H / 2)
    _release(cv, cv.frame_to_x(33), HEADER_H / 2)
    assert core.current_frame(s) == 33
    cv.ppf = 8.0
    ppf = cv.ppf
    _wheel(cv, 500, 100, 120, Qt.KeyboardModifier.ControlModifier)
    assert cv.ppf > ppf
    f0 = cv.f0
    _press(cv, 500, 100, Qt.MouseButton.MiddleButton)
    _move(cv, 540, 100, Qt.MouseButton.MiddleButton)
    _release(cv, 540, 100, Qt.MouseButton.MiddleButton)
    assert cv.f0 < f0
    _key(cv, Qt.Key.Key_H)
    _key(cv, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    n = len(ds.ctx.selection)
    assert n == len(core.all_refs(o)) + len(core.all_refs(b))
    _key(cv, Qt.Key.Key_Delete)
    assert not core.has_animation(o) and not core.has_animation(b)
    ds.btn_record.click()
    assert core.has_animation(s.active)
    ds.grab()


def test_curve_editor_interactions():
    from quartz_studio.anim.curves import CurveEditor
    s = _scene()
    o = s.objects[0]
    core.insert_key(o, "position.x", 0, 0, scene=s)
    core.insert_key(o, "position.x", 20, 100, scene=s)
    core.insert_key(o, "position.y", 0, 50, scene=s)
    core.insert_key(o, "position.y", 20, 50, scene=s)
    core.set_key(o, [core.POINTS], 0, s)
    ce = _show(CurveEditor(s), 1200, 480)
    cv = ce.canvas
    assert ce.list.count() == 2
    ce.list.item(0).setSelected(True)
    assert [ch for _o, ch in cv.channels] == ["position.x"]
    cv.frame_all()
    p = QPointF(cv.fx(20), cv.vy(100))
    _press(cv, p.x(), p.y())
    _release(cv, p.x(), p.y())
    assert ce.ctx.selection == [(o, "position.x", 20)]
    assert ce.key_value.isEnabled() and _close(ce.key_value.value(), 100)
    _press(cv, p.x(), p.y())
    _move(cv, p.x(), p.y() - 10 * cv.ppv)
    _release(cv, p.x(), p.y() - 10 * cv.ppv)
    assert _close(core.get_track(o, "position.x")[1]["value"], 110, 1e-6)
    cv.frame_all()
    p = QPointF(cv.fx(20), cv.vy(110))
    _press(cv, p.x(), p.y())
    _move(cv, p.x() + 5 * cv.ppf, p.y())
    _release(cv, p.x() + 5 * cv.ppf, p.y())
    assert core.key_frames(o, ["position.x"]) == [0, 25]
    ce.ctx.select([(o, "position.x", 0)])
    handles = list(cv._handles())
    assert handles and handles[0][3] == "out"
    hp = handles[0][5]
    _press(cv, hp.x(), hp.y())
    assert cv._mode == "tangent"
    _move(cv, hp.x(), hp.y() - 20 * cv.ppv)
    _release(cv, hp.x(), hp.y() - 20 * cv.ppv)
    k = core.get_track(o, "position.x")[0]
    assert k["out_tan"] is not None and k["out_tan"][1] > 10
    ce.btn_auto.click()
    assert core.get_track(o, "position.x")[0]["out_tan"] is None
    ce.btn_flat.click()
    assert _close(core.get_track(o, "position.x")[0]["out_tan"][1], 0)
    ce.btn_ease_out.click()
    assert core.get_track(o, "position.x")[0]["ease"] == "out"
    ce.btn_step.click()
    assert core.get_track(o, "position.x")[0]["interp"] == "step"
    ce.btn_spline.click()
    ce.key_value.setValue(7.5)
    assert _close(core.get_track(o, "position.x")[0]["value"], 7.5)
    ce.key_frame.setValue(3)
    assert core.key_frames(o, ["position.x"]) == [3, 25]
    ce.after_combo.setCurrentIndex(ce.after_combo.findData("oscillate"))
    ce.after_combo.activated.emit(ce.after_combo.currentIndex())
    assert core.loop_mode(o, "position.x")[1] == "oscillate"
    ce.list.clearSelection()
    assert len(cv.channels) == 2
    _press(cv, cv.fx(-5), 30)
    _move(cv, cv.fx(30), cv.height() - 2)
    cv.grab()
    _release(cv, cv.fx(30), cv.height() - 2)
    assert len(ce.ctx.selection) >= 3
    ppf, ppv = cv.ppf, cv.ppv
    _wheel(cv, 400, 200, 120)
    assert cv.ppf > ppf and cv.ppv > ppv
    _wheel(cv, 400, 200, -120, Qt.KeyboardModifier.ControlModifier)
    assert _close(cv.ppv, ppv * 1.25, 1e-9)
    _press(cv, cv.fx(10), 8)
    _release(cv, cv.fx(10), 8)
    assert core.current_frame(s) == 10
    before = len(core.get_track(o, "position.y"))
    _dbl(cv, cv.fx(10), cv.vy(50))
    assert len(core.get_track(o, "position.y")) == before + 1
    _key(cv, Qt.Key.Key_S)
    _key(cv, Qt.Key.Key_H)
    _key(cv, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    ce.btn_delete.click()
    assert core.channels_of(o) == [core.POINTS]
    assert ce.list.count() == 0
    ce.btn_active.click()
    assert ce.active_only is False
    ce.grab()


def test_widgets_from_dock_factories_default_scene():
    for title, factory, area in anim.docks():
        w = factory()
        _show(w, 900, 240)
        assert w.scene is not None and area == "bottom"
        w.grab()
        w.close()


def test_glyphs_render():
    from quartz_studio.anim.ui_common import glyph
    for name in ("start", "end", "prev_key", "next_key", "prev_frame", "next_frame", "play", "play_back",
                 "pause", "stop", "record", "autokey", "pla", "key", "loop", "frame_all", "frame_sel",
                 "spline", "linear", "step", "ease_in", "ease_out", "ease_both", "auto_tan", "flat_tan",
                 "delete", "copy", "paste", "scale", "expand", "collapse", "active"):
        icon = glyph(name)
        assert not icon.isNull()
        img = icon.pixmap(16, 16).toImage()
        assert any(img.pixelColor(x, y).alpha() > 0 for x in range(16) for y in range(16)), name


def _global():
    from quartz_studio.anim.player import drop_context
    from quartz_studio.scene import get_scene, reset_scene
    drop_context(get_scene())
    s = reset_scene()
    return s, get_context(s)


def _undo_len(s) -> int:
    return len(s._undo)


def _menu_actions(menu) -> dict:
    out = {}
    for a in menu.actions():
        if a.menu() is not None:
            out[a.text()] = a.menu()
        elif a.text():
            out[a.text()] = a
    return out


def test_global_undo_removes_keys_and_keeps_redo():
    s, ctx = _global()
    o = s.objects[0]
    n0 = _undo_len(s)
    core.insert_key(o, "position.x", 0, 0.0, scene=s)
    core.insert_key(o, "position.x", 10, 10.0, scene=s)
    assert _undo_len(s) == n0 + 2
    assert s.undo()
    assert core.key_frames(s.objects[0]) == [0]
    assert s.undo()
    assert not core.has_animation(s.objects[0]) and s.can_redo()
    assert s.redo() and s.redo()
    assert core.key_frames(s.objects[0]) == [0, 10] and not s.can_redo()
    core.set_loop(s.objects[0], "position.x", after="repeat")
    assert s.undo() and core.loop_mode(s.objects[0], "position.x") == ("constant", "constant")
    assert s.redo() and core.loop_mode(s.objects[0], "position.x") == ("constant", "repeat")
    ctx.close()


def test_global_autokey_move_undo_is_not_stuck():
    s, ctx = _global()
    ctx.autokey.set_enabled(True)
    ctx.set_frame(5)
    n0 = _undo_len(s)
    s.set_object_position(0, 50.0)
    assert core.key_frames(s.objects[0]) == [5]
    assert _undo_len(s) == n0 + 2
    assert s.undo()
    assert not core.has_animation(s.objects[0]) and _close(s.objects[0].position[0], 50)
    assert s.undo()
    assert _close(s.objects[0].position[0], 0) and not core.has_animation(s.objects[0])
    assert s.can_redo() and core.current_frame(s) == 5
    assert s.redo() and s.redo()
    assert core.key_frames(s.objects[0]) == [5] and _close(s.objects[0].position[0], 50)
    assert not s.can_redo()
    ctx.autokey.set_enabled(False)
    ctx.close()


def test_global_delete_tracks_undo_redo():
    s, ctx = _global()
    o = s.objects[0]
    core.set_key(o, None, 0, s)
    core.set_key(o, ["position.x"], 10, s)
    core.set_loop(o, "position.x", after="oscillate")
    n0 = _undo_len(s)
    assert ctx.delete_tracks() == 10
    assert _undo_len(s) == n0 + 1
    assert s.undo()
    restored = s.objects[0]
    assert core.key_frames(restored) == [0, 10] and core.loop_mode(restored, "position.x")[1] == "oscillate"
    assert s.redo()
    assert not core.has_animation(s.objects[0]) and not core.track_modes(s.objects[0])
    assert not s.can_redo()
    ctx.close()


def test_new_project_and_open_reset_animation_state():
    from quartz_studio import fileio, project
    from quartz_studio.anim.timeline import TimelineBar
    from quartz_studio.fileio import bridge
    s, ctx = _global()
    bar = _show(TimelineBar(s))
    o = s.objects[0]
    core.insert_key(o, "position.x", 0, 0.0, scene=s)
    core.insert_key(o, "position.x", 30, 30.0, scene=s)
    core.set_time_settings(s, max=200, preview_max=200, fps=24)
    ctx.set_frame(120)
    assert bar.max_spin.value() == 200 and bar.frame_spin.value() == 120
    saved = bridge.full_document_from_scene(s)
    fileio.replace_scene(s, project._default_document())
    APP.processEvents()
    assert not core.has_animation(s.objects[0])
    t = core.time_settings(s)
    assert t["max"] == 90 and t["frame"] == 0 and t["fps"] == 30
    assert bar.max_spin.value() == 90 and bar.frame_spin.value() == 0 and bar.fps_spin.value() == 30
    assert ctx.settings()["max"] == 90 and not s.can_undo()
    fileio.replace_scene(s, saved)
    APP.processEvents()
    t = core.time_settings(s)
    assert t["max"] == 200 and t["fps"] == 24 and t["frame"] == 120
    assert bar.max_spin.value() == 200 and bar.frame_spin.value() == 120
    assert core.key_frames(s.objects[0]) == [0, 30] and _close(s.objects[0].position[0], 30)
    bar.close()
    ctx.close()


def test_frame_changes_and_playback_are_not_undo_steps():
    s, ctx = _global()
    o = s.objects[0]
    core.insert_key(o, "position.x", 0, 0.0, scene=s)
    core.insert_key(o, "position.x", 30, 30.0, scene=s)
    s.set_object_position(1, 7.0)
    n = _undo_len(s)
    for f in range(20):
        ctx.set_frame(f)
    for _ in range(40):
        ctx.player.advance(1)
    ctx.player.next_frame()
    ctx.player.prev_frame()
    ctx.player.go_start()
    ctx.player.go_end()
    ctx.player.next_key()
    ctx.player.prev_key()
    ctx.player.play(1)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 0.3:
        APP.processEvents()
    ctx.player.stop()
    assert _undo_len(s) == n and not s.can_redo()
    ctx.set_frame(15)
    assert s.undo()
    assert core.current_frame(s) == 15
    assert _close(s.objects[0].position[0], 15, 1e-6) and _close(s.objects[0].position[1], 0)
    assert s.redo() and _close(s.objects[0].position[1], 7) and core.current_frame(s) == 15
    ctx.close()


def test_drags_record_single_undo_step():
    from quartz_studio.anim.curves import CurveEditor
    from quartz_studio.anim.dopesheet import HEADER_H, ROW_H, DopeSheet
    from quartz_studio.anim.timeline import TimelineBar
    s, ctx = _global()
    o = s.objects[0]
    core.insert_key(o, "position.x", 0, 0.0, scene=s)
    core.insert_key(o, "position.x", 20, 100.0, scene=s)
    ce = _show(CurveEditor(s), 1200, 480)
    cv = ce.canvas
    cv.frame_all()
    p = QPointF(cv.fx(20), cv.vy(100))
    n = _undo_len(s)
    _press(cv, p.x(), p.y())
    for i in range(1, 31):
        _move(cv, p.x() + i, p.y() - i)
    _release(cv, p.x() + 30, p.y() - 30)
    assert _undo_len(s) == n + 1 and not cv.group.active
    moved = core.get_track(s.objects[0], "position.x")[1]
    assert moved["frame"] != 20 or not _close(moved["value"], 100)
    assert s.undo()
    k = core.get_track(s.objects[0], "position.x")[1]
    assert k["frame"] == 20 and _close(k["value"], 100)
    o = s.objects[0]
    ctx.select([(o, "position.x", 0)])
    handles = [h for h in cv._handles() if h[3] == "out"]
    assert handles
    hp = handles[0][5]
    n = _undo_len(s)
    _press(cv, hp.x(), hp.y())
    for i in range(1, 21):
        _move(cv, hp.x() + i, hp.y() - 2 * i)
    _release(cv, hp.x() + 20, hp.y() - 40)
    assert _undo_len(s) == n + 1
    assert core.get_track(s.objects[0], "position.x")[0]["out_tan"] is not None
    ce.close()
    ds = _show(DopeSheet(s), 1000, 400)
    dv = ds.canvas
    dv.frame_all()
    o = s.objects[0]
    y = HEADER_H + ROW_H / 2
    n = _undo_len(s)
    _press(dv, dv.frame_to_x(20), y)
    for i in range(1, 11):
        _move(dv, dv.frame_to_x(20 + i), y)
    _release(dv, dv.frame_to_x(30), y)
    assert core.key_frames(o) == [0, 30] and _undo_len(s) == n + 1
    ds.close()
    bar = _show(TimelineBar(s))
    r = bar.ruler
    n = _undo_len(s)
    _press(r, r.frame_to_x(30), 32)
    for i in range(1, 11):
        _move(r, r.frame_to_x(30 + i), 32)
    _release(r, r.frame_to_x(40), 32)
    assert core.key_frames(o) == [0, 40] and _undo_len(s) == n + 1
    st = bar.strip
    n = _undo_len(s)
    _press(st, r.frame_to_x(0), 6)
    for i in range(1, 21):
        _move(st, r.frame_to_x(i), 6)
    _release(st, r.frame_to_x(20), 6)
    assert core.time_settings(s)["preview_min"] == 20 and _undo_len(s) == n + 1 and not st.group.active
    assert s.undo() and core.time_settings(s)["preview_min"] == 0
    bar.close()
    ctx.close()


def test_edit_group_closes_when_mouse_is_up():
    from quartz_studio.anim.ui_common import EditGroup
    s, ctx = _global()
    g = EditGroup(s)
    g.begin()
    assert g.active and s._group_depth == 1
    t0 = time.perf_counter()
    while g.active and time.perf_counter() - t0 < 1.0:
        APP.processEvents()
    assert not g.active and s._group_depth == 0
    g.end()
    assert s._group_depth == 0
    ctx.close()


def _grid(n: int) -> Mesh:
    xs, zs = np.meshgrid(np.linspace(-100, 100, n), np.linspace(-100, 100, n))
    pts = np.stack([xs.ravel(), np.zeros(n * n), zs.ravel()], 1)
    polys = [(i * n + j, i * n + j + 1, (i + 1) * n + j + 1, (i + 1) * n + j)
             for i in range(n - 1) for j in range(n - 1)]
    return Mesh(pts, polys)


def test_pla_playback_is_realtime_on_dense_mesh():
    s, ctx = _global()
    o = s.add_object("Grid", _grid(100))
    base = o.mesh.points.copy()
    t = time.perf_counter()
    for k, f in enumerate((0, 10, 20, 30, 40, 50)):
        core.insert_key(o, core.POINTS, f, base + np.array([0.0, 5.0 * k, 0.0]), scene=s)
    insert = time.perf_counter() - t
    assert insert < 1.5, insert
    raw = store.object_extras(o)[core.TRACKS_KEY][core.POINTS][0]["value"]
    assert isinstance(raw, dict) and isinstance(raw[core.PACK_KEY], str)
    assert core.tracks(o) is core.tracks(o)
    t = time.perf_counter()
    for f in range(60):
        ctx.set_frame(f)
    per_frame = (time.perf_counter() - t) / 60
    assert per_frame < 1.0 / 30, per_frame
    ctx.set_frame(5)
    assert np.allclose(o.mesh.points[:, 1], 2.5)
    ctx.set_frame(59)
    assert np.allclose(o.mesh.points[:, 1], 25.0)
    t = time.perf_counter()
    s.set_object_position(0, 1.0)
    assert time.perf_counter() - t < 0.5
    assert s.undo()
    restored = [x for x in s.objects if x.name == "Grid"][0]
    assert len(core.get_track(restored, core.POINTS)) == 6
    blob = json.dumps(store.to_json(dict(store.object_extras(restored))))
    back = store.from_json(json.loads(blob))
    s2 = _scene()
    g2 = s2.add_object("Grid", _grid(100))
    for key, value in back.items():
        store.set_object(g2, key, value)
    core.evaluate(s2, 25)
    assert np.allclose(g2.mesh.points[:, 1], 12.5)
    ctx.close()


def test_long_spline_track_editor_is_fast():
    from quartz_studio.anim.curves import CurveEditor
    s, ctx = _global()
    o = s.objects[0]
    keys = [core.make_key(f, 50.0 * math.sin(f / 7.0)) for f in range(300)]
    core.set_track(o, "position.x", keys)
    track = core.get_track(o, "position.x")
    full = core.auto_slopes([float(k["frame"]) for k in track], [k["value"] for k in track])
    for i in (0, 1, 150, 298, 299):
        assert _close(core._slope_at(track, i), full[i], 1e-12)
        assert core.key_tangents(track, i) == core.key_tangents(track, i, full)
    t = time.perf_counter()
    lo, hi = core.value_range(o, "position.x", 0, 299)
    assert time.perf_counter() - t < 0.25 and lo < -45 and hi > 45
    t = time.perf_counter()
    vals = [core.evaluate_track(track, i * 299 / 511) for i in range(512)]
    assert time.perf_counter() - t < 0.25
    assert all(abs(v) <= 50.0 + 1e-6 for v in vals)
    assert _close(core.evaluate_track(track, 77), 50.0 * math.sin(11.0))
    ce = _show(CurveEditor(s), 1200, 480)
    assert [ch for _o, ch in ce.canvas.channels] == ["position.x"]
    t = time.perf_counter()
    ce.canvas.frame_all()
    ce.canvas.grab()
    assert time.perf_counter() - t < 1.5
    ce.close()
    ctx.close()


def test_time_settings_follow_undo_and_clamp_reevaluates():
    from quartz_studio.anim.timeline import TimelineBar
    s, ctx = _global()
    o = s.objects[0]
    core.insert_key(o, "position.x", 0, 0.0, "linear", scene=s)
    core.insert_key(o, "position.x", 100, 100.0, "linear", scene=s)
    core.set_time_settings(s, max=100)
    bar = _show(TimelineBar(s))
    ctx.set_frame(80)
    assert _close(o.position[0], 80)
    bar.max_spin.setValue(50)
    assert core.current_frame(s) == 50 and _close(o.position[0], 50) and bar.frame_spin.value() == 50
    assert s.undo()
    APP.processEvents()
    assert core.time_settings(s)["max"] == 100 and bar.max_spin.value() == 100
    assert core.current_frame(s) == 50 and bar.frame_spin.value() == 50
    assert _close(s.objects[0].position[0], 50)
    assert s.redo()
    assert bar.max_spin.value() == 50 and ctx.settings()["max"] == 50
    bar.close()
    ctx.close()


def test_param_and_visibility_keys_from_ui():
    from PySide6.QtWidgets import QMenu
    from quartz_studio.anim.timeline import TimelineBar, key_menu
    from quartz_studio.anim.ui_common import fill_record_menu
    s = _scene()
    cyl = s.add_parametric("cylinder")
    s.set_active(cyl)
    chans = core.keyable_params(cyl)
    num = [ch for ch in chans if isinstance(cyl.params[ch[len(core.PARAM_PREFIX):]], float)]
    assert num
    ch = num[0]
    key = ch[len(core.PARAM_PREFIX):]
    bar = _show(TimelineBar(s))
    ctx = bar.ctx
    assert bar.btn_key.menu() is not None
    rec = QMenu(bar)
    acts = _menu_actions(fill_record_menu(ctx, rec))
    for name in ("Position, Rotation and Scale", "Visibility", "Add Parameter Keys", "Parameter", "Record Points"):
        assert name in acts, name
    ctx.set_frame(0)
    acts["Visibility"].trigger()
    assert core.key_frames(cyl, [core.VISIBILITY]) == [0]
    acts["Add Parameter Keys"].trigger()
    assert set(chans) <= set(core.channels_of(cyl))
    v0 = cyl.params[key]
    ctx.set_frame(10)
    s.set_param(cyl, key, v0 * 2 + 1)
    s.set_enabled(cyl, False)
    sub = _menu_actions(acts["Parameter"])
    sub[core.channel_label(ch, cyl)].trigger()
    acts["Visibility"].trigger()
    assert core.key_frames(cyl, [ch]) == [0, 10] and core.key_frames(cyl, [core.VISIBILITY]) == [0, 10]
    ctx.set_frame(0)
    assert _close(cyl.params[key], v0) and cyl.enabled
    ctx.set_frame(10)
    assert _close(cyl.params[key], v0 * 2 + 1) and not cyl.enabled
    km = key_menu(ctx, bar)
    menu = _menu_actions(km)
    assert "Record Channel" in menu and "Reverse Keys" in menu
    bar.close()
    ctx.close()


def test_add_parameter_keys_command_global():
    s, ctx = _global()
    cyl = s.add_parametric("cylinder")
    s.set_active(cyl)
    cmds = {p: fn for p, fn in anim.commands()}
    assert ("Animate", "Add Parameter Keys") in cmds and ("Animate", "Record Visibility") in cmds
    assert ("Animate", "Point Level Animation", "Record Points") in cmds
    assert ("Animate", "Playback Mode", "Ping-Pong") in cmds
    n = _undo_len(s)
    cmds[("Animate", "Add Parameter Keys")]()
    assert _undo_len(s) == n + 1
    assert all(c in core.channels_of(cyl) for c in core.keyable_params(cyl))
    cmds[("Animate", "Record Visibility")]()
    assert core.VISIBILITY in core.channels_of(cyl)
    cmds[("Animate", "Playback Mode", "Ping-Pong")]()
    assert core.playback_mode(s) == "pingpong"
    cmds[("Animate", "Playback Mode", "Simple")]()
    assert core.playback_mode(s) == "simple"
    ctx.close()


def test_keyable_params_on_every_object_kind():
    from quartz_studio.objects import registry
    s = _scene()
    kinds = list(registry.SPECS)
    assert kinds
    for kind in kinds:
        o = s.add_parametric(kind)
        chans = core.keyable_params(o)
        assert all(c.startswith(core.PARAM_PREFIX) for c in chans)
        core.set_key(o, chans + [core.VISIBILITY], 0, s)
        core.set_key(o, chans, 10, s)
    core.evaluate(s, 5)
    core.evaluate(s, 0)


def _menu_items(entries, out):
    for e in entries:
        if not isinstance(e, tuple) or not e:
            continue
        if e[0] == "item":
            out.append((e[1], e[2]))
        elif e[0] == "submenu":
            _menu_items(e[2], out)
    return out


def test_shortcuts_agree_with_app_menus():
    from quartz_studio.widgets import menus_data as md
    ours = {name: sc for name, sc, _fn in anim.key_actions()}
    animate = _menu_items(md.ANIMATE_MENU, [])
    for name, sc in animate:
        if sc:
            assert name in ours, name
            assert ours[name] == sc, (name, ours[name], sc)
    assert "Add Parameter Keys" in ours
    others = set()
    for _title, entries, _s in md.MENU_BAR:
        for name, sc in _menu_items(entries, []):
            if sc and name not in ours:
                others.add(sc)
    clash = [(n, sc) for n, sc in ours.items() if sc and sc in others]
    assert not clash, clash


def test_dope_sheet_scale_never_deletes_keys():
    from quartz_studio.anim.dopesheet import DopeSheet
    s = _scene()
    o = s.objects[0]
    for f in (0, 10, 20):
        core.insert_key(o, "position.x", f, float(f), scene=s)
    ds = _show(DopeSheet(s), 1000, 300)
    ds.ctx.select(core.all_refs(o))
    ds.scale_spin.setValue(0)
    assert ds.scale_spin.value() > 0
    ds._scale()
    assert core.key_frames(o) == [0, 1, 2]
    ds.ctx.select(core.all_refs(o))
    ds.scale_spin.setValue(-1)
    assert ds.scale_spin.value() > 0
    assert ds.ctx.scale_selected(0) == [] and ds.ctx.scale_selected(-1) == []
    assert core.key_frames(o) == [0, 1, 2]
    ds.ctx.select(core.all_refs(o))
    ds.scale_spin.setValue(10)
    ds._scale()
    assert core.key_frames(o) == [0, 10, 20]
    ds.close()


def test_reverse_keys_mirrors_tangents_and_ease():
    s = _scene()
    o = s.objects[0]
    core.set_track(o, "position.x", [
        core.make_key(0, 0.0, "linear", "out", out_tan=[3.0, 6.0]),
        core.make_key(10, 10.0, "spline"),
        core.make_key(20, 5.0, "step"),
    ])
    before = [core.evaluate_channel(o, "position.x", f) for f in range(0, 11)]
    ctx = AnimContext(s)
    ctx.select(core.all_refs(o))
    refs = ctx.reverse_selected()
    keys = core.get_track(o, "position.x")
    assert [k["frame"] for k in keys] == [0, 10, 20] and len(refs) == 3
    assert [k["value"] for k in keys] == [5.0, 10.0, 0.0]
    assert keys[2]["in_tan"] == [-3.0, 6.0] and keys[2]["out_tan"] is None and keys[2]["ease"] == "in"
    assert [k["interp"] for k in keys] == ["spline", "linear", "linear"]
    after = [core.evaluate_channel(o, "position.x", 20 - f) for f in range(0, 11)]
    assert all(_close(a, b, 1e-9) for a, b in zip(before, after))
    assert core.reverse_keys([]) == []
    ctx.close()


def test_record_point_selection_and_clear_points():
    s = _scene()
    o = s.objects[0]
    ctx = AnimContext(s)
    base = o.mesh.points.copy()
    core.set_key(o, [core.POINTS], 0, s)
    o.mesh.points = base + 10.0
    core.set_key(o, [core.POINTS], 20, s)
    ctx.set_frame(10)
    assert np.allclose(o.mesh.points, base + 5.0)
    pts = o.mesh.points.copy()
    pts[0] += np.array([0.0, 100.0, 0.0])
    o.mesh.points = pts
    s.selected_points = {0}
    assert ctx.record_point_selection() == 1
    key = core.get_track(o, core.POINTS)[1]
    assert key["frame"] == 10
    assert np.allclose(key["value"][0], base[0] + np.array([5.0, 105.0, 5.0]))
    assert np.allclose(key["value"][1:], base[1:] + 5.0)
    s.selected_points = set()
    assert ctx.record_point_selection() == 0
    assert ctx.clear_points() == 3 and core.POINTS not in core.channels_of(o)
    ctx.close()


def test_non_finite_frames_and_smpte():
    keys = [core.make_key(0, 0.0, "linear"), core.make_key(10, 10.0, "linear")]
    for mode in core.LOOPS:
        assert _close(core.evaluate_track(keys, float("inf"), mode, mode), 10)
        assert _close(core.evaluate_track(keys, float("-inf"), mode, mode), 0)
        assert _close(core.evaluate_track(keys, float("nan"), mode, mode), 0)
    s = _scene()
    core.insert_key(s.objects[0], "position.x", 0, 0.0, scene=s)
    core.evaluate(s, float("nan"))
    core.evaluate(s, float("inf"))
    assert core.format_time(s, -1, "smpte") == "-00:00:01"
    assert core.format_time(s, 29.6, "smpte") == "00:01:00"
    assert core.format_time(s, 29.4, "smpte") == "00:00:29"
    assert core.format_time(s, -61, "smpte") == "-00:02:01"
    assert core.format_time(s, 30 * 125 + 7, "smpte") == "02:05:07"
    assert core.format_time(s, 0, "smpte") == "00:00:00"
    assert core.format_time(s, float("inf"), "frames") == "0 F"


def test_pingpong_playback():
    from quartz_studio.anim.timeline import TimelineBar
    s = _scene()
    core.set_time_settings(s, min=0, max=10)
    bar = _show(TimelineBar(s))
    ctx = bar.ctx
    pl = ctx.player
    bar.loop_combo.setCurrentIndex(bar.loop_combo.findData("pingpong"))
    assert core.playback_mode(s) == "pingpong" and not bar.btn_loop.isChecked()
    pl.play(1)
    pl.set_frame(9)
    assert pl.advance(3) == 8 and pl.direction == -1 and bar.btn_back.isChecked()
    pl.set_frame(1)
    assert pl.advance(-3) == 2 and pl.direction == 1
    pl.set_frame(10)
    assert pl.advance(25) == 5 and pl.direction == -1
    pl.stop()
    bar.btn_loop.click()
    assert core.playback_mode(s) == "loop" and bar.loop_combo.currentData() == "loop"
    pl.set_frame(10)
    assert pl.advance(1) == 0
    bar.btn_loop.click()
    assert core.playback_mode(s) == "simple"
    pl.play(1)
    pl.set_frame(10)
    pl.advance(1)
    assert not pl.is_playing()
    bar.close()


def test_selection_index_and_find_key():
    s = _scene()
    o = s.objects[0]
    for f in range(0, 50, 5):
        core.insert_key(o, "position.x", f, float(f), scene=s)
    assert core.find_key(o, "position.x", 25) == 5 and core.find_key(o, "position.x", 26) == -1
    assert core.find_key(o, "position.x", 45.0000001) == 9 and core.find_key(o, "position.y", 0) == -1
    ctx = AnimContext(s)
    ctx.select(core.all_refs(o))
    assert ctx.is_selected(o, "position.x", 30) and ctx.is_frame_selected(o, 30)
    ctx.select([(o, "position.x", 30)], "toggle")
    assert not ctx.is_selected(o, "position.x", 30) and len(ctx.selection) == 9
    ctx.select([(o, "position.x", 30), (o, "position.x", 30)], "add")
    assert len(ctx.selection) == 10
    ctx.close()


def test_retime_document_keeps_timing():
    s, ctx = _global()
    o = s.objects[0]
    core.insert_key(o, "position.x", 0, 0.0, scene=s)
    core.insert_key(o, "position.x", 30, 30.0, scene=s)
    core.set_tangents(o, "position.x", 30, in_tan=[-6.0, -3.0])
    ctx.set_frame(15)
    before = [core.evaluate_channel(o, "position.x", f / 2) for f in range(0, 61)]
    n = _undo_len(s)
    cmds = {p: fn for p, fn in anim.commands()}
    cmds[("Animate", "Change Frame Rate Keeping Timing", "60 fps")]()
    assert _undo_len(s) == n + 1
    t = core.time_settings(s)
    assert t["fps"] == 60 and t["max"] == 180 and t["preview_max"] == 180 and t["frame"] == 30
    assert core.key_frames(o) == [0, 60]
    assert core.get_track(o, "position.x")[1]["in_tan"] == [-12.0, -3.0]
    after = [core.evaluate_channel(o, "position.x", f) for f in range(0, 61)]
    assert all(_close(a, b, 1e-9) for a, b in zip(before, after))
    assert ctx.retime(60) == 0
    assert s.undo()
    assert core.fps(s) == 30 and core.key_frames(s.objects[0]) == [0, 30]
    ctx.close()


def test_record_buttons_on_every_editor():
    from quartz_studio.anim.curves import CurveEditor
    from quartz_studio.anim.dopesheet import DopeSheet
    s = _scene()
    for cls in (DopeSheet, CurveEditor):
        w = _show(cls(s), 900, 300)
        menu = w.btn_key.menu()
        menu.aboutToShow.emit()
        acts = _menu_actions(menu)
        acts["Position"].trigger()
        assert core.channels_of(s.objects[0])[:3] == list(core.POSITION_CHANNELS)
        acts["Visibility"].trigger()
        assert core.VISIBILITY in core.channels_of(s.objects[0])
        core.clear_tracks(s.objects[0])
        w.close()


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
