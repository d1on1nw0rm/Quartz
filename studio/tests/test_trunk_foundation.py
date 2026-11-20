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
from PySide6.QtWidgets import QApplication

from quartz_studio import fileio
from quartz_studio.fileio import bridge
from quartz_studio.modeling import meshkit
from quartz_studio.modeling.meshkit import OpResult, Selection
from quartz_studio.modeling.registry import Param, ToolSpec, register as register_tool
from quartz_studio.modeling.session import ModelingController, ToolSession
from quartz_studio.objects import registry as objects_registry
from quartz_studio.scene import Mesh, SceneObject, _copy_mesh, reset_scene

_APP = QApplication.instance() or QApplication([sys.argv[0]])

SCALE_TOOL = "test_trunk_foundation_scale"
RESET_TOOL = "test_trunk_foundation_reset"
PROBE_GEN = "test_trunk_foundation_probe"
SEEN: list = []


def _scale_apply(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    if not sel.points:
        return OpResult(mesh, sel, False, "Scale: select points first")
    scales = mesh.point_scale_array()
    scales[sorted(sel.points)] *= p["point_scale"] / 100.0
    mesh.point_scales = scales
    return OpResult(mesh, sel.copy())


def _reset_apply(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh.point_scales = None
    return OpResult(mesh, sel.copy())


register_tool(ToolSpec(SCALE_TOOL, "Scale Probe", _scale_apply, modes=("points",),
                       params=(Param("point_scale", "Point Scale", "percent", 100.0, 0.0, 10000.0),),
                       menu="Test"))
register_tool(ToolSpec(RESET_TOOL, "Reset Probe", _reset_apply, modes=("points",), menu="Test"))


def _probe_build(p: dict, inputs: list) -> Mesh:
    SEEN.append([None if i.mesh.point_scales is None else i.mesh.point_scales.copy() for i in inputs])
    return Mesh.empty()


objects_registry.register(objects_registry.ObjectSpec(PROBE_GEN, "Probe", "generator", _probe_build,
                                                      inputs="children"))


def _line(n: int = 4) -> Mesh:
    pts = [(10.0 * i, 0.0, 0.0) for i in range(n)]
    return Mesh(pts, [], [(i, i + 1) for i in range(n - 1)])


def _scene_with_line(n: int = 4):
    scene = reset_scene()
    line = scene.add_object("Line", _line(n))
    scene.clear_history()
    return scene, line


def test_absent_by_default_and_ones_array():
    m = _line()
    assert m.point_scales is None
    assert np.array_equal(m.point_scale_array(), np.ones(4))
    assert not m.point_scales_explicit


def test_setter_normalises_and_validates():
    m = _line()
    m.point_scales = [1.0, 2.0, -3.0, float("nan")]
    assert np.allclose(m.point_scales, [1.0, 2.0, 0.0, 1.0])
    m.point_scales = [1.0, 1.0, 1.0, 1.0]
    assert m.point_scales is None and m.point_scales_explicit
    try:
        m.point_scales = [1.0, 2.0]
    except ValueError:
        pass
    else:
        raise AssertionError("wrong length accepted")


def test_constructor_ignores_misaligned_scales():
    m = Mesh(np.zeros((3, 3)), [], [], point_scales=[2.0, 2.0])
    assert m.point_scales is None
    m = Mesh(np.zeros((2, 3)), [], [(0, 1)], point_scales=[2.0, 3.0])
    assert np.allclose(m.point_scales, [2.0, 3.0])


def test_misaligned_after_raw_point_change_reads_absent():
    m = _line()
    m.point_scales = [2.0, 1.0, 1.0, 1.0]
    m.points = np.vstack([m.points, np.zeros((2, 3))])
    assert m.point_scales is None
    assert np.array_equal(m.point_scale_array(), np.ones(6))
    assert not m.point_scales_explicit
    m.add_point((1.0, 1.0, 1.0))
    assert m.point_scales is None


def test_add_point_appends_one():
    m = _line()
    m.point_scales = [2.0, 1.0, 1.0, 3.0]
    i = m.add_point((5.0, 5.0, 5.0))
    assert i == 4 and np.allclose(m.point_scales, [2.0, 1.0, 1.0, 3.0, 1.0])


def test_in_place_point_move_keeps_scales():
    m = _line()
    m.point_scales = [2.0, 1.0, 1.0, 3.0]
    m.points[1] += 5.0
    assert np.allclose(m.point_scales, [2.0, 1.0, 1.0, 3.0])


def test_copies_keep_scales():
    m = _line()
    m.point_scales = [2.0, 1.0, 1.0, 3.0]
    for c in (meshkit.clone(m), _copy_mesh(m)):
        assert np.allclose(c.point_scales, m.point_scales)
        assert c.point_scales is not m.point_scales


def test_compact_remaps_scales():
    m = Mesh([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)], [], [(0, 1), (2, 3)])
    m.point_scales = [2.0, 3.0, 4.0, 5.0]
    m.loose_edges = [(2, 3)]
    m._rebuild_edges()
    out, remap = meshkit.compact(m)
    assert remap == {2: 0, 3: 1}
    assert np.allclose(out.point_scales, [4.0, 5.0])


def test_weld_remaps_to_root():
    m = Mesh([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)], [], [(0, 1), (1, 2), (2, 3)])
    m.point_scales = [2.0, 3.0, 4.0, 5.0]
    out, full = meshkit.weld(m, {2: 1})
    assert len(out.points) == 3
    assert np.allclose(out.point_scales, [2.0, 3.0, 5.0])
    assert full[2] == full[1]


def test_compact_without_channel_stays_absent():
    out, _ = meshkit.compact(_line())
    assert out.point_scales is None and not out.point_scales_explicit


def test_carry_point_scales_by_position():
    src = _line()
    src.point_scales = [2.0, 3.0, 4.0, 5.0]
    lost = Mesh(src.points[[0, 2, 3]], [], [(0, 1), (1, 2)])
    meshkit.carry_point_scales(src, lost)
    assert np.allclose(lost.point_scales, [2.0, 4.0, 5.0])
    moved = Mesh(src.points[[0, 1]] + 0.5, [], [(0, 1)])
    meshkit.carry_point_scales(src, moved)
    assert moved.point_scales is None
    explicit = Mesh(src.points[[0, 1]], [], [(0, 1)])
    explicit.point_scales = None
    meshkit.carry_point_scales(src, explicit)
    assert explicit.point_scales is None


def test_carry_point_scales_same_topology():
    src = _line()
    src.point_scales = [2.0, 3.0, 4.0, 5.0]
    moved = Mesh(src.points + 1.5, [], list(src.loose_edges))
    meshkit.carry_point_scales(src, moved)
    assert np.allclose(moved.point_scales, [2.0, 3.0, 4.0, 5.0])
    other = Mesh(src.points + 1.5, [], [(0, 1), (1, 2)])
    meshkit.carry_point_scales(src, other)
    assert other.point_scales is None


def test_scene_point_scales_accessors():
    scene, line = _scene_with_line()
    assert np.array_equal(scene.point_scales(), np.ones(4))
    assert scene.point_scales(line) is not line.mesh.point_scales
    hits = []
    scene.changed.connect(lambda: hits.append(1))
    assert scene.set_point_scales([1, 2], 2.0)
    assert np.allclose(scene.point_scales(), [1.0, 2.0, 2.0, 1.0])
    assert scene.multiply_point_scales([2, 3, 3], 0.5)
    assert np.allclose(scene.point_scales(), [1.0, 2.0, 1.0, 0.5])
    assert scene.set_point_scales([0, 3], [4.0, 1.0], line)
    assert np.allclose(scene.point_scales(line), [4.0, 2.0, 1.0, 1.0])
    assert not scene.set_point_scales([0], 4.0)
    assert not scene.set_point_scales([99, -1], 3.0)
    assert not scene.multiply_point_scales([], 2.0)
    assert len(hits) == 3


def test_scene_scales_reset_to_absent():
    scene, line = _scene_with_line()
    scene.set_point_scales([1], 2.0)
    scene.set_point_scales([1], 1.0)
    assert line.mesh.point_scales is None


def test_scene_scales_undo_redo():
    scene, line = _scene_with_line()
    scene.set_point_scales([1], 2.0)
    scene.multiply_point_scales([1, 2], 3.0)
    assert np.allclose(scene.point_scales(), [1.0, 6.0, 3.0, 1.0])
    assert scene.undo()
    assert np.allclose(scene.point_scales(), [1.0, 2.0, 1.0, 1.0])
    assert scene.undo()
    assert scene.active.mesh.point_scales is None
    assert scene.redo() and scene.redo()
    assert np.allclose(scene.point_scales(), [1.0, 6.0, 3.0, 1.0])


def test_snapshot_is_not_shared():
    scene, line = _scene_with_line()
    scene.set_point_scales([1], 2.0)
    scene.set_point_scales([1], 5.0)
    scene.active.mesh.point_scales[1] = 9.0
    scene.undo()
    assert np.allclose(scene.point_scales(), [1.0, 2.0, 1.0, 1.0])


def test_scene_scales_refuse_parametric():
    scene = reset_scene()
    gen = scene.add_parametric(PROBE_GEN)
    assert not scene.set_point_scales([0], 2.0, gen)
    assert len(scene.point_scales(gen)) == len(gen.mesh.points)


def test_move_selection_keeps_scales():
    scene, line = _scene_with_line()
    scene.set_point_scales([0, 3], [2.0, 3.0])
    scene.set_mode("points")
    scene.select_components([1])
    scene.move_selection((0.0, 5.0, 0.0))
    assert np.allclose(scene.point_scales(), [2.0, 1.0, 1.0, 3.0])
    assert scene.active.mesh.points[1][1] == 5.0


def test_line_pen_new_points_get_one():
    scene, line = _scene_with_line()
    scene.set_point_scales([3], 2.5)
    scene.set_mode("points")
    scene.set_tool("line_pen")
    scene.pen_link_point(3)
    scene.pen_add_point((50.0, 0.0, 0.0))
    scene.pen_add_point((60.0, 0.0, 0.0))
    scene.pen_finish()
    assert len(line.mesh.points) == 6
    assert np.allclose(scene.point_scales(), [1.0, 1.0, 1.0, 2.5, 1.0, 1.0])
    assert (3, 4) in line.mesh.loose_edges


def test_extrude_points_keeps_alignment():
    scene, line = _scene_with_line()
    scene.set_point_scales([0], 2.0)
    scene.set_mode("points")
    scene.select_components([3])
    assert scene.extrude_selection()
    assert np.allclose(scene.point_scales(), [2.0, 1.0, 1.0, 1.0, 1.0])


def test_make_editable_keeps_channel_of_copy():
    scene = reset_scene()
    gen = scene.add_parametric(PROBE_GEN)
    gen.mesh = _line()
    gen.mesh.point_scales = [1.0, 2.0, 1.0, 1.0]
    new = scene.make_editable(gen)
    assert new.kind == "polygon"
    assert np.allclose(new.mesh.point_scales, [1.0, 2.0, 1.0, 1.0])


def test_session_points_apply_is_one_undo_step():
    scene, line = _scene_with_line()
    scene.set_mode("points")
    scene.select_components([1, 2])
    before = len(scene._undo)
    session = ToolSession(scene, SCALE_TOOL, {"point_scale": 200.0})
    assert session.apply().ok
    assert session.apply({"point_scale": 300.0}).ok
    session.commit()
    assert len(scene._undo) == before + 1
    assert np.allclose(scene.point_scales(), [1.0, 3.0, 3.0, 1.0])
    assert len(line.mesh.points) == 4 and line.mesh.loose_edges == [(0, 1), (1, 2), (2, 3)]
    assert scene.selected_points == {1, 2}
    scene.undo()
    assert scene.active.mesh.point_scales is None


def test_session_cancel_restores_scales():
    scene, line = _scene_with_line()
    scene.set_point_scales([1], 2.0)
    scene.set_mode("points")
    scene.select_components([1])
    session = ToolSession(scene, SCALE_TOOL, {"point_scale": 50.0})
    session.apply()
    assert np.allclose(scene.point_scales(), [1.0, 1.0, 1.0, 1.0])
    session.cancel()
    assert np.allclose(scene.point_scales(), [1.0, 2.0, 1.0, 1.0])


def test_session_explicit_reset_is_not_carried():
    scene, line = _scene_with_line()
    scene.set_point_scales([1], 2.0)
    scene.set_mode("points")
    scene.select_components([1])
    session = ToolSession(scene, RESET_TOOL)
    assert session.apply().ok
    assert scene.active.mesh.point_scales is None


def test_delete_points_through_controller_remaps():
    scene, line = _scene_with_line(5)
    scene.set_point_scales([0, 1, 2, 3, 4], [2.0, 3.0, 4.0, 5.0, 6.0])
    scene.set_mode("points")
    scene.select_components([2])
    ctl = ModelingController(scene)
    ctl.activate("delete")
    assert ctl.apply_once()
    assert len(scene.active.mesh.points) == 4
    assert np.allclose(scene.point_scales(), [2.0, 3.0, 5.0, 6.0])


def test_subdivide_line_keeps_old_points():
    scene, line = _scene_with_line()
    scene.set_point_scales([1, 3], [2.0, 3.0])
    scene.set_mode("edges")
    scene.select_components([(0, 1), (2, 3)])
    ctl = ModelingController(scene)
    ctl.activate("subdivide")
    ctl.apply_once()
    mesh = scene.active.mesh
    scales = scene.point_scales()
    assert len(scales) == len(mesh.points)
    for k, x in ((1, 10.0), (3, 30.0)):
        hits = np.where(np.all(np.isclose(mesh.points, (x, 0.0, 0.0)), axis=1))[0]
        assert len(hits) == 1 and np.isclose(scales[hits[0]], {1: 2.0, 3: 3.0}[k])


def test_generator_reads_child_scales_and_rebuilds():
    scene, line = _scene_with_line()
    gen = scene.add_parametric(PROBE_GEN, adopt=line)
    assert SEEN and SEEN[-1] == [None]
    count = len(SEEN)
    scene.set_point_scales([2], 3.0, line)
    assert len(SEEN) == count + 1
    assert np.allclose(SEEN[-1][0], [1.0, 1.0, 3.0, 1.0])
    scene.set_active(line)
    scene.set_mode("points")
    scene.select_components([0])
    session = ToolSession(scene, SCALE_TOOL, {"point_scale": 50.0})
    session.apply()
    session.commit()
    assert np.allclose(SEEN[-1][0], [0.5, 1.0, 3.0, 1.0])
    scene.undo()
    child = scene.active
    assert child.name == "Line" and child.parent is not None and child.parent.kind == PROBE_GEN
    assert np.allclose(scene.point_scales(), [1.0, 1.0, 3.0, 1.0])
    scene.multiply_point_scales([1], 2.0)
    assert np.allclose(SEEN[-1][0], [1.0, 2.0, 3.0, 1.0])
    assert gen.kind == PROBE_GEN


def test_build_input_concatenates_scales():
    scene = reset_scene()
    a = scene.add_object("A", _line(3))
    b = scene.add_object("B", _line(2))
    gen = scene.add_parametric(PROBE_GEN, adopt=a)
    scene.set_parent(b, a)
    scene.set_point_scales([1], 2.0, b)
    assert np.allclose(SEEN[-1][0], [1.0, 1.0, 1.0, 1.0, 2.0])
    assert gen in scene.objects


def _save(scene, path):
    fileio.save_scene(scene, path)
    with open(path, "rb") as handle:
        return handle.read()


def test_quartz_round_trip_and_optional_key():
    folder = tempfile.mkdtemp(prefix="qz_trunk_")
    scene, line = _scene_with_line()
    plain = _save(scene, os.path.join(folder, "plain.quartz"))
    assert b"point_scales" not in plain
    scene.set_point_scales([1], 2.0)
    scene.set_point_scales([1], 1.0)
    reset = _save(scene, os.path.join(folder, "reset.quartz"))
    assert reset == plain
    scene.set_point_scales([1, 3], [2.5, 0.25])
    path = os.path.join(folder, "scaled.quartz")
    data = json.loads(_save(scene, path))
    mesh = [o for o in data["scene"]["objects"] if o["name"] == "Line"][0]["mesh"]
    assert mesh["point_scales"] == [1.0, 2.5, 1.0, 0.25]
    other = reset_scene()
    fileio.open_scene(other, path)
    loaded = [o for o in other.objects if o.name == "Line"][0]
    assert np.allclose(loaded.mesh.point_scales, [1.0, 2.5, 1.0, 0.25])
    fileio.open_scene(other, os.path.join(folder, "plain.quartz"))
    assert all(o.mesh.point_scales is None for o in other.objects)


def test_quartz_rejects_bad_scales():
    folder = tempfile.mkdtemp(prefix="qz_trunk_")
    scene, line = _scene_with_line()
    scene.set_point_scales([1], 2.0)
    path = os.path.join(folder, "bad.quartz")
    data = json.loads(_save(scene, path))
    for bad in ([1.0, 2.0], "x", [1.0, 2.0, "a", 1.0]):
        for o in data["scene"]["objects"]:
            if o["name"] == "Line":
                o["mesh"]["point_scales"] = bad
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        try:
            fileio.open_scene(reset_scene(), path)
        except fileio.FileFormatError as exc:
            assert "point_scales" in str(exc)
        else:
            raise AssertionError(f"accepted {bad!r}")


def test_interchange_export_drops_scales():
    scene, line = _scene_with_line()
    scene.set_point_scales([1], 2.0)
    doc = bridge.document_from_scene(scene)
    assert all(n.mesh.point_scales is None for n in doc.nodes)
    full = bridge.full_document_from_scene(scene)
    node = [n for n in full.nodes if n.name == "Line"][0]
    assert np.allclose(node.mesh.point_scales, [1.0, 2.0, 1.0, 1.0])
    folder = tempfile.mkdtemp(prefix="qz_trunk_")
    fileio.export_file(scene, os.path.join(folder, "line.ply"))
    fileio.export_file(scene, os.path.join(folder, "line.obj"))


def test_import_document_keeps_scales():
    scene, line = _scene_with_line()
    scene.set_point_scales([2], 4.0)
    doc = bridge.full_document_from_scene(scene)
    other = reset_scene()
    made = bridge.add_document_to_scene(other, doc)
    lines = [o for o in made if o.name.startswith("Line")]
    assert np.allclose(lines[0].mesh.point_scales, [1.0, 1.0, 4.0, 1.0])


def test_tools_unaware_of_channel_do_not_crash():
    scene, line = _scene_with_line()
    scene.set_point_scales([0, 1, 2, 3], [2.0, 3.0, 4.0, 5.0])
    scene.set_mode("points")
    for tool in ("select_all", "optimize", "subdivide", "delete"):
        scene.select_components([0, 1, 2, 3])
        ctl = ModelingController(scene)
        ctl.activate(tool)
        ctl.apply_once()
        assert len(scene.point_scales()) == len(scene.active.mesh.points)


def test_scene_object_default_mesh_channel():
    obj = SceneObject("X", Mesh.cube(10.0))
    assert obj.mesh.point_scales is None


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
