from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

import quartz_studio.scene as scene_mod
from quartz_studio import objects
from quartz_studio.objects import registry
from quartz_studio.objects.registry import BuildInput, ObjectSpec, Param, mesh_chains
from quartz_studio.scene import Mesh, Scene, rotation_matrix

BUILDS: dict[str, int] = {}


def _count(key: str) -> None:
    BUILDS[key] = BUILDS.get(key, 0) + 1


def _box(p: dict, _inputs: list) -> Mesh:
    _count("box")
    m = Mesh.cube(float(p["size"]))
    if p["offset"]:
        m.points[:, 0] += float(p["offset"])
    return m


def _merge(_p: dict, inputs: list) -> Mesh:
    _count("merge")
    pts, polys, loose = [], [], []
    off = 0
    for inp in inputs:
        m = inp.mesh
        pts.append(m.points)
        polys.extend(tuple(i + off for i in poly) for poly in m.polygons)
        loose.extend((a + off, b + off) for a, b in m.loose_edges)
        off += len(m.points)
    return Mesh(np.vstack(pts) if pts else np.zeros((0, 3)), polys, loose)


def _fail(_p: dict, _inputs: list) -> Mesh:
    raise RuntimeError("broken build")


def _polyline(p: dict, _inputs: list) -> Mesh:
    n = int(p["count"])
    pts = [(100.0 * i, 0.0, 0.0) for i in range(n)]
    edges = [(i, i + 1) for i in range(n - 1)]
    if p["close"]:
        edges.append((n - 1, 0))
    return Mesh(pts, [], edges)


SPEC_BOX = registry.register(ObjectSpec(
    "test_core_box", "Test Box", "mesh", _box,
    params=(Param("size", "Size", "distance", 100.0, minimum=0.0, maximum=1000.0),
            Param("offset", "Offset", "distance", 0.0),
            Param("segments", "Segments", "int", 1, minimum=1, maximum=100),
            Param("caption", "Caption", "text", "box"),
            Param("tint", "Tint", "vector", (1.0, 1.0, 1.0), minimum=0.0, maximum=1.0))))
SPEC_MERGE = registry.register(ObjectSpec("test_core_merge", "Test Merge", "generator", _merge,
                                          inputs="children"))
SPEC_FAIL = registry.register(ObjectSpec("test_core_fail", "Test Fail", "mesh", _fail))
SPEC_LINE = registry.register(ObjectSpec(
    "test_core_line", "Test Line", "spline", _polyline,
    params=(Param("count", "Count", "int", 3, minimum=2, maximum=50),
            Param("close", "Close", "bool", False))))


def _scene() -> Scene:
    QApplication.instance() or QApplication([sys.argv[0]])
    return scene_mod.reset_scene()


def _names(objs) -> list[str]:
    return [o.name for o in objs]


def _by_name(scene: Scene, name: str):
    return next(o for o in scene.objects if o.name == name)


def test_registry_null_and_lookup():
    null = registry.get("null")
    assert null.category == "null" and null.inputs == "none" and null.label == "Null"
    assert null in registry.by_category("null")
    assert registry.get("test_core_box") is SPEC_BOX
    assert SPEC_BOX in registry.all_specs() and SPEC_BOX in registry.by_category("mesh")
    assert registry.defaults(SPEC_BOX)["size"] == 100.0
    assert registry.defaults("test_core_box") == SPEC_BOX.defaults()
    assert objects.get is registry.get


def test_registry_duplicate_and_bad_specs():
    try:
        registry.register(ObjectSpec("test_core_box", "Again", "mesh", _box))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate id accepted")
    for kwargs in ({"category": "deformer"}, {"category": "mesh", "inputs": "all"}):
        try:
            ObjectSpec("test_core_bad", "Bad", build=_box, **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"bad spec accepted: {kwargs}")
    try:
        registry.get("test_core_missing")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown id returned a spec")


def test_param_text_and_vector_kinds():
    text = SPEC_BOX.param("caption")
    assert text.clamp(12) == "12" and text.clamp(None) == ""
    vec = SPEC_BOX.param("tint")
    assert vec.clamp([2, -1, 0.5]) == (1.0, 0.0, 0.5)
    try:
        vec.clamp((1, 2))
    except ValueError:
        pass
    else:
        raise AssertionError("2-vector accepted")
    assert SPEC_BOX.param("segments").clamp(2.6) == 3


def test_default_scene_is_one_editable_cube():
    scene = _scene()
    assert _names(scene.objects) == ["Cube"]
    cube = scene.objects[0]
    assert cube.kind == "polygon" and scene.is_editable(cube)
    assert cube.parent is None and cube.enabled and cube.error == "" and cube.params == {}
    assert scene.render_objects() == [cube] and scene.roots() == [cube]


def test_add_parametric_defaults_and_undo():
    scene = _scene()
    box = scene.add_parametric("test_core_box")
    assert box.name == "Test Box" and box.kind == "test_core_box"
    assert box.params == SPEC_BOX.defaults()
    assert scene.active is box and not scene.is_editable(box)
    assert len(box.mesh.points) == 8 and np.allclose(box.mesh.size(), 100.0)
    null = scene.add_parametric("null", name="Group")
    assert null.name == "Group" and len(null.mesh.points) == 0
    assert scene.undo() and _names(scene.objects) == ["Cube", "Test Box"]
    assert scene.undo() and _names(scene.objects) == ["Cube"]
    assert scene.redo() and scene.redo()
    assert _names(scene.objects) == ["Cube", "Test Box", "Group"]
    restored = _by_name(scene, "Test Box")
    assert np.allclose(restored.mesh.size(), 100.0) and restored.kind == "test_core_box"


def test_set_param_clamp_coerce_undo_redo():
    scene = _scene()
    box = scene.add_parametric("test_core_box")
    assert scene.set_param(box, "size", 300)
    assert box.params["size"] == 300.0 and np.allclose(box.mesh.size(), 300.0)
    scene.set_param(box, "size", -5)
    assert box.params["size"] == 0.0
    scene.set_param(box, "size", 5000)
    assert box.params["size"] == 1000.0 and np.allclose(box.mesh.size(), 1000.0)
    scene.set_param(box, "segments", "7")
    assert box.params["segments"] == 7
    assert not scene.set_param(box, "segments", 7)
    for bad in (("missing", 1), ("size", "abc")):
        try:
            scene.set_param(box, *bad)
        except (KeyError, ValueError):
            continue
        raise AssertionError(f"accepted {bad}")
    try:
        scene.set_param(scene.objects[0], "size", 1)
    except ValueError:
        pass
    else:
        raise AssertionError("polygon object accepted a parameter")
    assert scene.undo()
    box = _by_name(scene, "Test Box")
    assert box.params["segments"] == 1 and box.params["size"] == 1000.0
    assert scene.undo()
    box = _by_name(scene, "Test Box")
    assert box.params["size"] == 0.0
    assert scene.undo()
    box = _by_name(scene, "Test Box")
    assert box.params["size"] == 300.0 and np.allclose(box.mesh.size(), 300.0)
    assert scene.redo()
    box = _by_name(scene, "Test Box")
    assert box.params["size"] == 0.0 and np.allclose(box.mesh.size(), 0.0)


class _Pressed:

    @staticmethod
    def mouseButtons():
        return Qt.MouseButton.LeftButton


def test_param_drag_coalesces_into_one_step():
    scene = _scene()
    box = scene.add_parametric("test_core_box")
    before = len(scene._undo)
    real = scene_mod.QGuiApplication
    scene_mod.QGuiApplication = _Pressed
    try:
        for v in (110, 120, 130, 140):
            scene.set_param(box, "size", v)
        scene.set_param(box, "offset", 5)
    finally:
        scene_mod.QGuiApplication = real
    assert len(scene._undo) == before + 2
    scene.undo()
    box = _by_name(scene, "Test Box")
    assert box.params["size"] == 140.0 and box.params["offset"] == 0.0
    scene.undo()
    assert _by_name(scene, "Test Box").params["size"] == 100.0


def test_child_follows_parent_transform():
    scene = _scene()
    null = scene.add_parametric("null")
    box = scene.add_parametric("test_core_box", parent=null)
    assert box.parent is null and scene.children(null) == [box]
    assert scene.descendants(null) == [box] and box not in scene.roots()
    box.position = np.array([600.0, 0.0, 0.0])
    null.position = np.array([0.0, 50.0, 0.0])
    null.rotation = np.array([0.0, 90.0, 0.0])
    scene.changed.emit()
    expected = (rotation_matrix((0, 90, 0)) @ np.array([600.0, 0.0, 0.0])) + np.array([0.0, 50.0, 0.0])
    assert np.allclose(box.world_position(), expected)
    assert np.allclose(box.world_points().mean(axis=0), expected)
    assert np.allclose(box.to_local_point(expected), 0.0)
    assert np.allclose(box.to_world(np.zeros((1, 3)))[0], expected)
    lo, hi = scene.world_bounds([box])
    assert np.allclose((lo + hi) / 2, expected)
    hit = scene.raycast(expected + np.array([0.0, 1000.0, 0.0]), (0, -1, 0))
    assert hit is not None and hit[0] is box


def test_object_mode_move_of_child_uses_world_delta():
    scene = _scene()
    null = scene.add_parametric("null")
    null.rotation = np.array([0.0, 90.0, 0.0])
    null.scale = np.array([2.0, 2.0, 2.0])
    box = scene.add_parametric("test_core_box", parent=null)
    scene.set_active(box)
    start = box.world_position()
    scene.move_selection((100.0, 0.0, 0.0))
    assert np.allclose(box.world_position(), start + np.array([100.0, 0.0, 0.0]))
    assert np.allclose(scene.selection_center(), box.world_position())
    assert np.allclose(box.size(), 200.0)
    scene.set_object_size(0, 100.0)
    assert np.allclose(box.size()[0], 100.0)
    cube = _by_name(scene, "Cube")
    scene.set_parent(cube, null)
    scene.set_active(cube)
    scene.set_mode("points")
    scene.select_components([6])
    before = cube.world_points()[6]
    scene.move_selection((0.0, 0.0, 40.0))
    assert np.allclose(cube.world_points()[6], before + np.array([0.0, 0.0, 40.0]))
    assert np.allclose(scene.selection_center(), before + np.array([0.0, 0.0, 40.0]))


def test_reparent_keeps_world_transform_and_refuses_cycles():
    scene = _scene()
    parent = scene.add_parametric("null", name="P")
    parent.position = np.array([10.0, 20.0, 30.0])
    parent.rotation = np.array([15.0, 40.0, -25.0])
    parent.scale = np.array([2.0, 2.0, 2.0])
    cube = _by_name(scene, "Cube")
    cube.position = np.array([-50.0, 5.0, 70.0])
    cube.rotation = np.array([10.0, 0.0, 30.0])
    world = cube.world_matrix()
    points = cube.world_points()
    assert scene.set_parent(cube, parent)
    assert cube.parent is parent and np.allclose(cube.world_matrix(), world, atol=1e-7)
    assert np.allclose(cube.world_points(), points, atol=1e-6)
    assert _names(scene.objects) == ["P", "Cube"]
    assert not scene.set_parent(parent, cube)
    assert not scene.set_parent(cube, cube)
    assert scene.set_parent(cube, None)
    assert cube.parent is None and np.allclose(cube.world_points(), points, atol=1e-6)
    assert np.allclose(cube.position, (-50.0, 5.0, 70.0), atol=1e-6)
    assert scene.undo()
    cube = _by_name(scene, "Cube")
    assert cube.parent is _by_name(scene, "P")
    assert np.allclose(cube.world_points(), points, atol=1e-6)
    assert scene.undo()
    cube = _by_name(scene, "Cube")
    assert cube.parent is None and np.allclose(cube.position, (-50.0, 5.0, 70.0))


def test_set_parent_index_orders_children():
    scene = _scene()
    null = scene.add_parametric("null")
    a = scene.add_parametric("test_core_box", name="A", parent=null)
    b = scene.add_parametric("test_core_box", name="B", parent=null)
    cube = _by_name(scene, "Cube")
    assert scene.set_parent(cube, null, 0)
    assert _names(scene.children(null)) == ["Cube", "A", "B"]
    assert scene.set_parent(b, null, 0)
    assert _names(scene.children(null)) == ["B", "Cube", "A"]
    assert _names(scene.objects) == ["Null", "B", "Cube", "A"]
    assert not scene.set_parent(b, null, 0)
    assert a in scene.descendants(null)


def test_generator_consumes_children_and_nests():
    scene = _scene()
    outer = scene.add_parametric("test_core_merge", name="Outer")
    inner = scene.add_parametric("test_core_merge", name="Inner", parent=outer)
    box = scene.add_parametric("test_core_box", parent=inner)
    box.position = np.array([0.0, 0.0, 500.0])
    scene.changed.emit()
    assert np.allclose(inner.mesh.points.mean(axis=0), (0.0, 0.0, 500.0))
    assert np.allclose(outer.mesh.points.mean(axis=0), (0.0, 0.0, 500.0))
    rendered = scene.render_objects()
    assert outer in rendered and inner not in rendered and box not in rendered
    scene.set_param(box, "size", 50.0)
    assert np.allclose(outer.mesh.size(), 50.0)
    null = scene.add_parametric("null")
    child = scene.add_parametric("test_core_box", name="Free", parent=null)
    assert null in scene.render_objects() and child in scene.render_objects()


def test_inputs_are_in_generator_space_and_null_groups_merge():
    scene = _scene()
    gen = scene.add_parametric("test_core_merge")
    gen.position = np.array([1000.0, 0.0, 0.0])
    gen.rotation = np.array([0.0, 45.0, 0.0])
    group = scene.add_parametric("null", parent=gen)
    group.position = np.array([0.0, 100.0, 0.0])
    box = scene.add_parametric("test_core_box", parent=group)
    box.position = np.array([0.0, 0.0, 10.0])
    scene.changed.emit()
    assert len(gen.mesh.points) == 8
    assert np.allclose(gen.mesh.points.mean(axis=0), (0.0, 100.0, 10.0))
    assert np.allclose(gen.world_points().mean(axis=0), box.world_position())


def test_disabled_child_ignored_and_disabled_subtree_hidden():
    scene = _scene()
    gen = scene.add_parametric("test_core_merge")
    a = scene.add_parametric("test_core_box", name="A", parent=gen)
    b = scene.add_parametric("test_core_box", name="B", parent=gen)
    scene.set_param(b, "offset", 400.0)
    assert len(gen.mesh.points) == 16
    scene.set_enabled(b, False)
    assert len(gen.mesh.points) == 8 and not b.enabled
    scene.set_enabled(gen, False)
    rendered = scene.render_objects()
    assert gen not in rendered and a not in rendered and b not in rendered
    assert scene.undo()
    assert _by_name(scene, "Test Merge").enabled
    assert scene.undo()
    assert len(_by_name(scene, "Test Merge").mesh.points) == 16


def test_build_error_is_isolated():
    scene = _scene()
    gen = scene.add_parametric("test_core_merge")
    bad = scene.add_parametric("test_core_fail", parent=gen)
    good = scene.add_parametric("test_core_box", parent=gen)
    assert bad.error.startswith("RuntimeError") and len(bad.mesh.points) == 0
    assert gen.error == "" and len(gen.mesh.points) == 8
    assert good.error == ""
    scene.set_parent(bad, None)
    assert bad in scene.render_objects() and bad.error


def test_rebuild_only_when_inputs_change():
    scene = _scene()
    gen = scene.add_parametric("test_core_merge")
    box = scene.add_parametric("test_core_box", parent=gen)
    cube = _by_name(scene, "Cube")
    scene.set_parent(cube, gen)
    merges, boxes = BUILDS.get("merge", 0), BUILDS.get("box", 0)
    assert not scene.evaluate()
    scene.changed.emit()
    scene.rename_object(box, "Renamed")
    scene.set_active(cube)
    assert BUILDS.get("merge", 0) == merges and BUILDS.get("box", 0) == boxes
    scene.set_mode("points")
    scene.select_components([2])
    scene.move_selection((0.0, 30.0, 0.0))
    assert BUILDS.get("merge", 0) == merges + 1 and BUILDS.get("box", 0) == boxes
    assert np.isclose(gen.mesh.points[:, 1].max(), 130.0)
    cube.mesh.points[1] += (0.0, 0.0, 5.0)
    scene.changed.emit()
    assert BUILDS.get("merge", 0) == merges + 2
    scene.set_object_position(0, 25.0)
    assert BUILDS.get("merge", 0) == merges + 3 and BUILDS.get("box", 0) == boxes


def test_spline_inputs_and_chains():
    scene = _scene()
    gen = scene.add_parametric("test_core_merge")
    line = scene.add_parametric("test_core_line", parent=gen)
    captured: list = []
    spec = registry.register(ObjectSpec("test_core_probe", "Probe", "generator",
                                        lambda p, inputs: captured.extend(inputs) or Mesh.empty(),
                                        inputs="children"))
    probe = scene.add_parametric(spec.id)
    scene.set_parent(line, probe)
    inp = captured[-1]
    assert isinstance(inp, BuildInput) and inp.is_spline and inp.kind == "test_core_line"
    assert inp.name == "Test Line" and inp.obj is line
    (pts, closed), = inp.chains()
    assert not closed and np.allclose(pts[:, 0], (0.0, 100.0, 200.0))
    scene.set_param(line, "close", True)
    (pts, closed), = captured[-1].chains()
    assert closed and len(pts) == 3
    box = scene.add_parametric("test_core_box", parent=probe)
    assert not captured[-1].is_spline and isinstance(captured[-1].mesh, Mesh)
    assert box is captured[-1].obj and len(captured[-2].chains()) == 1
    branched = Mesh([(0, 0, 0), (1, 0, 0), (2, 0, 0), (1, 1, 0), (5, 5, 5), (6, 5, 5), (6, 6, 5)],
                    [], [(0, 1), (1, 2), (1, 3), (4, 5), (5, 6), (6, 4)])
    chains = mesh_chains(branched)
    assert sorted((len(c), cl) for c, cl in chains) == [(2, False), (2, False), (2, False), (3, True)]
    assert gen is not None


def test_make_editable_primitive_and_generator():
    scene = _scene()
    box = scene.add_parametric("test_core_box")
    box.position = np.array([10.0, 0.0, 0.0])
    scene.set_param(box, "size", 40.0)
    poly = scene.make_editable(box)
    assert poly.kind == "polygon" and poly.name == "Test Box" and scene.is_editable(poly)
    assert np.allclose(poly.position, (10.0, 0.0, 0.0)) and np.allclose(poly.mesh.size(), 40.0)
    assert scene.active is poly and box not in scene.objects
    gen = scene.add_parametric("test_core_merge")
    scene.set_parent(poly, gen)
    a = scene.add_parametric("test_core_box", name="A", parent=gen)
    sub = scene.add_parametric("null", name="Sub", parent=a)
    result = scene.make_editable(gen)
    assert result.kind == "polygon" and len(result.mesh.points) == 16
    assert _names(scene.objects) == ["Cube", "Test Merge"]
    assert sub not in scene.objects
    cube = _by_name(scene, "Cube")
    assert scene.make_editable(cube) is cube
    group = scene.add_parametric("null")
    assert scene.make_editable(group) is group
    assert scene.undo() and scene.undo()
    restored = _by_name(scene, "Test Merge")
    assert restored.kind == "test_core_merge"
    assert _names(scene.descendants(restored)) == ["Test Box", "A", "Sub"]
    assert len(restored.mesh.points) == 16


def test_make_editable_keeps_children_of_primitive():
    scene = _scene()
    box = scene.add_parametric("test_core_box")
    cube = _by_name(scene, "Cube")
    scene.set_parent(cube, box)
    poly = scene.make_editable(box)
    assert cube.parent is poly and scene.children(poly) == [cube]
    assert cube in scene.render_objects()


def test_remove_subtree_and_undo():
    scene = _scene()
    null = scene.add_parametric("null")
    a = scene.add_parametric("test_core_box", name="A", parent=null)
    scene.add_parametric("test_core_box", name="B", parent=a)
    scene.set_active(a)
    scene.remove_object(null)
    assert _names(scene.objects) == ["Cube"] and scene.active is scene.objects[0]
    assert scene.undo()
    assert _names(scene.objects) == ["Cube", "Null", "A", "B"]
    n, a2, b2 = (_by_name(scene, k) for k in ("Null", "A", "B"))
    assert a2.parent is n and b2.parent is a2
    assert scene.redo() and _names(scene.objects) == ["Cube"]


def test_undo_restores_caches_exactly():
    scene = _scene()
    gen = scene.add_parametric("test_core_merge")
    box = scene.add_parametric("test_core_box", parent=gen)
    scene.set_param(box, "size", 70.0)
    before = gen.mesh.points.copy()
    scene.set_param(box, "size", 20.0)
    merges = BUILDS.get("merge", 0)
    scene.undo()
    gen = _by_name(scene, "Test Merge")
    assert np.array_equal(gen.mesh.points, before)
    assert BUILDS.get("merge", 0) == merges
    assert not scene.evaluate()
    scene.redo()
    assert np.allclose(_by_name(scene, "Test Merge").mesh.size(), 20.0)


def test_adopt_creates_generator_as_parent():
    scene = _scene()
    null = scene.add_parametric("null")
    cube = _by_name(scene, "Cube")
    scene.set_parent(cube, null)
    other = scene.add_parametric("test_core_box", name="Other", parent=null)
    null.position = np.array([0.0, 300.0, 0.0])
    cube.position = np.array([50.0, 0.0, 0.0])
    world = cube.world_points()
    gen = scene.add_parametric("test_core_merge", adopt=cube)
    assert gen.parent is null and cube.parent is gen
    assert _names(scene.children(null)) == ["Test Merge", "Other"]
    assert np.allclose(cube.world_points(), world)
    assert np.allclose(gen.world_points(), world)
    assert scene.active is gen and cube not in scene.render_objects()
    assert other in scene.render_objects()
    assert scene.undo()
    assert _names(scene.objects) == ["Null", "Cube", "Other"]


def test_edit_guard_on_parametric_objects():
    scene = _scene()
    box = scene.add_parametric("test_core_box")
    points = box.mesh.points.copy()
    scene.set_mode("points")
    scene.select_components([0, 1])
    assert not scene.selected_points
    scene.selected_points = {0}
    scene.move_selection((10.0, 0.0, 0.0))
    assert np.array_equal(box.mesh.points, points)
    assert not scene.extrude_selection()
    scene.set_tool("pen")
    assert scene.pen_add_point((0.0, 0.0, 0.0)) == -1
    assert len(box.mesh.points) == 8
    scene.set_tool("move")
    scene.set_mode("model")
    scene.move_selection((10.0, 0.0, 0.0))
    assert np.allclose(box.position, (10.0, 0.0, 0.0))
    from quartz_studio.modeling.session import ModelingController
    messages: list[str] = []
    ctl = ModelingController(scene)
    ctl.message.connect(messages.append)
    ctl.activate("extrude")
    scene.set_mode("polygons")
    assert ctl.begin() is None
    assert messages and "Make Editable first" in messages[-1]
    poly = scene.make_editable(box)
    scene.select_components([0])
    assert scene.selected_polygons == {0}
    assert ctl.begin() is not None and scene.active is poly


def test_line_pen_on_parametric_starts_new_line():
    scene = _scene()
    box = scene.add_parametric("test_core_box")
    scene.set_tool("line_pen")
    idx = scene.pen_add_point((0.0, 0.0, 0.0))
    assert idx == 0 and scene.active is not box and scene.is_editable(scene.active)
    assert len(box.mesh.points) == 8


_LIVE: list[QWidget] = []


def _canvas():
    from quartz_studio.app import create_app
    from quartz_studio.widgets.viewport import Viewport
    app = create_app([sys.argv[0]])
    while _LIVE:
        old = _LIVE.pop()
        old.close()
        old.deleteLater()
    scene = scene_mod.reset_scene()
    view = Viewport()
    view.resize(1000, 640)
    view.show()
    for _ in range(4):
        app.processEvents()
    _LIVE.append(view)
    return view.canvas, scene


def test_viewport_draws_and_picks_render_objects_only():
    canvas, scene = _canvas()
    cube = _by_name(scene, "Cube")
    gen = scene.add_parametric("test_core_merge")
    scene.set_parent(cube, gen)
    centre = canvas.project_world(np.zeros((1, 3)))[0]
    assert canvas.pick_object(centre) is gen
    hit = canvas.raycast(canvas.camera.position(), -canvas.camera.position())
    assert hit is not None and hit[0] is gen
    canvas.grab()
    scene.set_enabled(gen, False)
    assert canvas.pick_object(centre) is None
    scene.set_enabled(gen, True)
    null = scene.add_parametric("null")
    null.position = np.array([400.0, 0.0, 0.0])
    box = scene.add_parametric("test_core_box", parent=null)
    scene.changed.emit()
    spot = canvas.project_world(box.world_position()[None, :])[0]
    assert canvas.pick_object(spot) is box
    canvas.grab()


def _signed_volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        r = mesh.points[list(poly)]
        for k in range(1, len(r) - 1):
            total += float(np.dot(r[0], np.cross(r[k], r[k + 1])))
    return total / 6.0


def _is_closed(mesh: Mesh) -> bool:
    d: dict = {}
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            d[(a, b)] = d.get((a, b), 0) + 1
    return bool(d) and all(c == 1 and d.get((b, a), 0) == 1 for (a, b), c in d.items())


def _generator_with_child(kind: str, scale, position=(0.0, 0.0, 0.0), size: float = 100.0):
    scene = _scene()
    gen = scene.add_parametric(kind)
    child = scene.add_object("Child", Mesh.cube(size))
    child.position = np.asarray(position, float)
    child.scale = np.asarray(scale, float)
    assert scene.set_parent(child, gen)
    scene.changed.emit()
    return scene, gen, child


def test_mirrored_child_keeps_positive_volume_in_generators():
    for kind in ("connect", "subdivision_surface"):
        _, plain, _ = _generator_with_child(kind, (1.0, 1.0, 1.0))
        _, mirrored, _ = _generator_with_child(kind, (-1.0, 1.0, 1.0))
        assert not mirrored.error, mirrored.error
        assert _is_closed(mirrored.mesh), kind
        assert _signed_volume(mirrored.mesh) > 0.0, kind
        assert np.isclose(_signed_volume(mirrored.mesh), _signed_volume(plain.mesh), rtol=1e-9), kind


def test_double_mirror_is_not_flipped_and_mirror_flips_input_only():
    _, gen, child = _generator_with_child("test_core_merge", (-1.0, -1.0, 1.0))
    assert _signed_volume(gen.mesh) > 0.0
    assert gen.mesh.polygons == child.mesh.polygons
    _, gen, child = _generator_with_child("test_core_merge", (-1.0, 1.0, 1.0))
    assert _signed_volume(gen.mesh) > 0.0
    assert gen.mesh.polygons == [tuple(reversed(p)) for p in child.mesh.polygons]
    assert gen.mesh.loose_edges == child.mesh.loose_edges


def test_mirrored_spline_child_keeps_loose_edges():
    scene = _scene()
    gen = scene.add_parametric("test_core_merge")
    line = scene.add_parametric("test_core_line", parent=gen)
    line.scale = np.array([-1.0, 1.0, 1.0])
    scene.changed.emit()
    assert gen.mesh.polygons == [] and gen.mesh.loose_edges == line.mesh.loose_edges
    assert np.allclose(gen.mesh.points[:, 0], -line.mesh.points[:, 0])


def _boole_volume(kind: str, scale) -> float:
    scene = _scene()
    boole = scene.add_parametric("boole")
    a = scene.add_object("A", Mesh.cube(200.0))
    b = scene.add_object("B", Mesh.cube(150.0))
    b.position = np.array([60.0, 40.0, 20.0])
    b.scale = np.asarray(scale, float)
    assert scene.set_parent(a, boole) and scene.set_parent(b, boole)
    scene.set_param(boole, "boolean_type", kind)
    scene.changed.emit()
    assert not boole.error, boole.error
    assert _is_closed(boole.mesh)
    return _signed_volume(boole.mesh)


def test_boole_with_mirrored_child_matches_unmirrored():
    for kind in ("A union B", "A subtract B"):
        ref = _boole_volume(kind, (1.0, 1.0, 1.0))
        assert ref > 0.0
        assert np.isclose(_boole_volume(kind, (-1.0, 1.0, 1.0)), ref, rtol=1e-9), kind
        assert np.isclose(_boole_volume(kind, (-1.0, -1.0, 1.0)), ref, rtol=1e-9), kind


def test_mirrored_child_undo_redo_preserves_result():
    scene, gen, child = _generator_with_child("subdivision_surface", (-1.0, 1.0, 1.0))
    volume = _signed_volume(gen.mesh)
    points = gen.mesh.points.copy()
    assert volume > 0.0
    assert scene.undo()
    assert len(_by_name(scene, "Subdivision Surface").mesh.points) == 0
    assert scene.redo()
    again = _by_name(scene, "Subdivision Surface")
    assert np.isclose(_signed_volume(again.mesh), volume, rtol=1e-12)
    assert np.allclose(again.mesh.points, points)
    assert _by_name(scene, "Child").scale[0] == -1.0


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
