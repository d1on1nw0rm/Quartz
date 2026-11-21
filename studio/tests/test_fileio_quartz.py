from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio import fileio, objects
from quartz_studio.fileio import (Document, FileFormatError, Node, baked_mesh, export_file,
                                  full_document_from_scene, import_file, open_scene, save_scene)
from quartz_studio.fileio import fmt_quartz
from quartz_studio.objects import registry as object_registry
from quartz_studio.scene import Mesh, Scene

TMP = tempfile.mkdtemp(prefix="qz_fileio_quartz_")
FMT = fileio.get("quartz")


def _scene() -> Scene:
    QApplication.instance() or QApplication([sys.argv[0]])
    return scene_mod.reset_scene()


def _tmp(name: str) -> str:
    return os.path.join(TMP, name)


def _write(name: str, data) -> str:
    path = _tmp(name)
    if isinstance(data, (dict, list)):
        data = json.dumps(data)
    mode = "wb" if isinstance(data, bytes) else "w"
    kwargs = {} if mode == "wb" else {"encoding": "utf-8"}
    with open(path, mode, **kwargs) as handle:
        handle.write(data)
    return path


def _by_name(scene: Scene, name: str):
    return next(o for o in scene.objects if o.name == name)


def _parent_name(obj):
    return obj.parent.name if obj.parent is not None else None


def _same_mesh(a: Mesh, b: Mesh, label: str) -> None:
    assert a.points.shape == b.points.shape, (label, a.points.shape, b.points.shape)
    assert np.array_equal(a.points, b.points), label
    assert a.polygons == b.polygons, label
    assert a.loose_edges == b.loose_edges, label
    assert a.edges == b.edges, label


def _same_scene(a: Scene, b: Scene) -> None:
    assert [o.name for o in a.objects] == [o.name for o in b.objects]
    assert [o.kind for o in a.objects] == [o.kind for o in b.objects]
    for x, y in zip(a.objects, b.objects):
        assert _parent_name(x) == _parent_name(y), x.name
        assert x.enabled == y.enabled, x.name
        assert x.params == y.params, (x.name, x.params, y.params)
        assert np.array_equal(x.position, y.position), x.name
        assert np.array_equal(x.rotation, y.rotation), x.name
        assert np.array_equal(x.scale, y.scale), x.name
        assert x.error == y.error, (x.name, x.error, y.error)
        _same_mesh(x.mesh, y.mesh, x.name)
        assert np.array_equal(x.world_matrix(), y.world_matrix()), x.name
    assert (a.active.name if a.active else None) == (b.active.name if b.active else None)
    assert a.object_selected == b.object_selected
    assert a.mode == b.mode


def _round_trip(scene: Scene, name: str = "round.quartz") -> Scene:
    path = _tmp(name)
    save_scene(scene, path)
    other = _scene()
    other.add_object("Junk")
    open_scene(other, path)
    return other


def _transform(obj, position, rotation, scale) -> None:
    obj.position = np.array(position, float)
    obj.rotation = np.array(rotation, float)
    obj.scale = np.array(scale, float)


def _editable_cube_with_extras() -> Mesh:
    base = Mesh.cube(100.0)
    extra = np.array([[10.0 / 3.0, 0.1 + 0.2, 1e-9], [20.5, 30.25, -40.125], [1.0, 2.0, 3.0],
                      [4.0, 5.0, 6.0], [7.0, 8.0, 9.0], [50.0, 60.0, 70.0], [51.0, 61.0, 71.0],
                      [52.0, 62.0, 72.0]])
    pts = np.vstack([base.points, extra])
    polys = list(base.polygons) + [(8, 9, 10, 11, 12)]
    return Mesh(pts, polys, [(13, 14), (14, 15)])


def _build_rich_scene() -> Scene:
    scene = _scene()
    cube = _by_name(scene, "Cube")
    _transform(cube, (1.0 / 3.0, 0.1 + 0.2, -7.75), (12.5, -33.3, 71.0), (1.0, 2.5, 0.3))
    edit = scene.add_object("Edit Mesh", _editable_cube_with_extras())
    _transform(edit, (100.0, -50.0, 25.5), (10.0, 20.0, 30.0), (2.0, 0.5, -1.5))
    line = scene.add_object("Line", Mesh([(0, 0, 0), (10, 5, 0), (20, 0, 3.5), (30, 10, 1)], [],
                                         [(0, 1), (1, 2), (2, 3)]))
    _transform(line, (5.0, 6.0, 7.0), (0.0, 90.0, 0.0), (1.0, 1.0, 1.0))
    empty = scene.add_object("Empty Polygon Object")
    group = scene.add_parametric("null", name="Group")
    _transform(group, (500.0, 20.0, 0.0), (0.0, 45.0, 10.0), (1.5, 1.5, 0.75))
    scene.set_param(group, "display", "Cube")
    scene.set_param(group, "radius", 33.5)
    child = scene.add_object("Group Child", Mesh.cube(40.0), activate=False)
    scene.set_parent(child, group)
    child.position = np.array([0.0, 100.0, 5.0])
    child.scale = np.array([1.0, 2.0, 1.0])
    off = scene.add_object("Disabled", Mesh.cube(10.0), activate=False)
    scene.set_enabled(off, False)
    star = scene.add_parametric("star", name="Star")
    scene.set_param(star, "twist", 12.5)
    scene.set_param(star, "outer_radius", 123.456)
    extrude = scene.add_parametric("extrude", name="Extrude", adopt=star)
    scene.set_param(extrude, "movement", (1.5, 2.25, 80.0))
    sds = scene.add_parametric("subdivision_surface", name="SDS", adopt=extrude)
    scene.set_param(sds, "subdivision_editor", 1)
    _transform(sds, (-400.0, 0.0, 0.0), (0.0, 15.0, 0.0), (1.0, 1.0, 1.0))
    boole = scene.add_parametric("boole", name="Boole")
    bcube = scene.add_parametric("cube", name="Boole Cube", parent=boole)
    bsphere = scene.add_parametric("sphere", name="Boole Sphere", parent=boole)
    bsphere.position = np.array([60.0, 40.0, 20.0])
    scene.set_param(bsphere, "radius", 90.0)
    _transform(boole, (0.0, 300.0, 0.0), (0.0, 0.0, 20.0), (1.0, 1.0, 1.0))
    scene.changed.emit()
    scene.set_active(edit)
    return scene


def _alter(spec, p):
    d = p.default
    if p.kind == "bool":
        return not d
    if p.kind == "choice":
        others = [c for c in p.choices if c != d]
        return others[0] if others else d
    if p.kind == "text":
        if spec.id == "formula":
            return "40.0*t" if p.key == "x_expr" else d
        return str(d) + "\u00e9"
    if p.kind == "vector":
        return tuple(float(v) + 1.5 for v in d)
    if p.kind == "int":
        up = int(d) + 1
        return up if p.maximum is None or up <= p.maximum else int(d) - 1
    up = float(d) + 7.5
    return up if p.maximum is None or up <= p.maximum else float(d) - 7.5


def _expect_error(fn, *needles):
    try:
        fn()
    except FileFormatError as exc:
        text = str(exc)
        for needle in needles:
            assert needle in text, (needle, text)
        return text
    raise AssertionError("FileFormatError not raised")


def _good_header(**scene_extra) -> dict:
    scene = {"objects": [{"name": "A", "kind": "polygon", "parent": None,
                          "mesh": fmt_quartz._mesh_to_json(Mesh.cube(10.0))}]}
    scene.update(scene_extra)
    return {"format": "quartz", "version": 1, "app": "1.0.0", "scene": scene, "view": {}}


def _open_must_fail(name: str, data, *needles):
    scene = _scene()
    scene.add_object("Keep")
    names = [o.name for o in scene.objects]
    path = _write(name, data)
    _expect_error(lambda: open_scene(scene, path), name, *needles)
    assert [o.name for o in scene.objects] == names
    assert scene.can_undo()


def test_format_registered():
    assert FMT.id == "quartz" and FMT.label == "Quartz Project" and FMT.extensions == (".quartz",)
    assert FMT.load is not None and FMT.save is not None
    assert fileio.by_path("C:/x/Project.QUARTZ") is FMT
    assert FMT in fileio.importers() and FMT in fileio.exporters()
    assert fileio.file_filter(FMT) == "Quartz Project (*.quartz)"
    assert "quartz_studio.fileio.fmt_quartz" in sys.modules


def test_file_is_utf8_json_with_header():
    scene = _build_rich_scene()
    path = _tmp("header.quartz")
    save_scene(scene, path)
    with open(path, "rb") as handle:
        raw = handle.read()
    data = json.loads(raw.decode("utf-8"))
    assert data["format"] == "quartz" and data["version"] == 1 and isinstance(data["app"], str)
    assert isinstance(data["scene"], dict) and isinstance(data["view"], dict)
    assert data["scene"]["unit"] == "cm" and len(data["scene"]["objects"]) == len(scene.objects)
    by = {o["name"]: o for o in data["scene"]["objects"]}
    assert by["SDS"]["kind"] == "subdivision_surface" and "mesh" not in by["SDS"]
    assert "params" not in by["Edit Mesh"] and isinstance(by["Edit Mesh"]["mesh"]["points"][0], float)
    assert by["Boole Cube"]["parent"] == [o.name for o in scene.objects].index("Boole")
    assert by["Disabled"]["enabled"] is False
    assert by["Extrude"]["params"]["movement"] == [1.5, 2.25, 80.0]
    assert len(by["Edit Mesh"]["mesh"]["points"]) == 3 * len(_by_name(scene, "Edit Mesh").mesh.points)


def test_round_trip_everything():
    scene = _build_rich_scene()
    assert len(_by_name(scene, "SDS").mesh.points) > 0 and len(_by_name(scene, "Boole").mesh.points) > 0
    other = _round_trip(scene)
    _same_scene(scene, other)
    edit = _by_name(other, "Edit Mesh")
    assert (8, 9, 10, 11, 12) in edit.mesh.polygons and edit.mesh.loose_edges == [(13, 14), (14, 15)]
    line = _by_name(other, "Line")
    assert not line.mesh.polygons and line.mesh.loose_edges == [(0, 1), (1, 2), (2, 3)]
    assert len(_by_name(other, "Empty Polygon Object").mesh.points) == 0
    assert _by_name(other, "Group").params["display"] == "Cube"
    assert _by_name(other, "Group Child").parent is _by_name(other, "Group")
    assert _by_name(other, "Disabled").enabled is False
    assert _by_name(other, "Boole Sphere").parent is _by_name(other, "Boole")
    assert other.active is _by_name(other, "Edit Mesh")
    assert not any(o.error for o in other.objects)


def test_nested_generators_evaluate_the_same():
    scene = _build_rich_scene()
    other = _round_trip(scene)
    for name in ("SDS", "Extrude", "Star", "Boole"):
        a, b = _by_name(scene, name), _by_name(other, name)
        assert len(a.mesh.points) > 0
        _same_mesh(a.mesh, b.mesh, name)
    assert _by_name(other, "Extrude").parent is _by_name(other, "SDS")
    assert _by_name(other, "Star").parent is _by_name(other, "Extrude")
    assert [o.name for o in other.render_objects()] == [o.name for o in scene.render_objects()]
    other.set_param(_by_name(other, "Boole Sphere"), "radius", 20.0)
    assert len(_by_name(other, "Boole").mesh.points) != len(_by_name(scene, "Boole").mesh.points) or \
        not np.array_equal(_by_name(other, "Boole").mesh.points, _by_name(scene, "Boole").mesh.points)


def test_every_registered_object_with_non_default_params():
    scene = _scene()
    specs = object_registry.all_specs()
    assert len(specs) >= 40
    changed = 0
    for spec in specs:
        obj = scene.add_parametric(spec.id, name=f"All {spec.id}", activate=False)
        for p in spec.params:
            scene.set_param(obj, p.key, _alter(spec, p))
        if spec.params and obj.params != spec.defaults():
            changed += 1
        obj.position = np.array([float(len(scene.objects)), 0.0, 1.0 / 3.0])
        obj.rotation = np.array([0.0, 17.5, 0.0])
    assert changed >= len(specs) - 3
    scene.changed.emit()
    other = _round_trip(scene, "every.quartz")
    _same_scene(scene, other)
    assert len(other.objects) == len(specs) + 1
    for spec in specs:
        o = _by_name(other, f"All {spec.id}")
        assert o.kind == spec.id and o.params == _by_name(scene, f"All {spec.id}").params


def test_vector_and_text_params_restored_as_python_types():
    scene = _scene()
    ext = scene.add_parametric("extrude", name="E")
    scene.set_param(ext, "movement", (3.0, 4.0, 5.5))
    text = scene.add_parametric("text", name="T")
    scene.set_param(text, "text", "Caf\u00e9 \u65e5\u672c\u8a9e \u2615")
    other = _round_trip(scene)
    assert _by_name(other, "E").params["movement"] == (3.0, 4.0, 5.5)
    assert isinstance(_by_name(other, "E").params["movement"], tuple)
    assert _by_name(other, "T").params["text"] == "Caf\u00e9 \u65e5\u672c\u8a9e \u2615"


def test_float_precision_is_exact():
    scene = _scene()
    awkward = [1.0 / 3.0, 2.0 ** -40, 1e300, -1e-300, 0.1 + 0.2, 123456789.123456789, 5e-324, 1.7976931348623157e308]
    pts = np.array([[awkward[i % 8], awkward[(i + 3) % 8] * 0.5, awkward[(i + 5) % 8]] for i in range(12)])
    obj = scene.add_object("Precise", Mesh(pts, [(0, 1, 2), (3, 4, 5, 6)], [(8, 9)]))
    obj.position = np.array([1.0 / 7.0, np.pi, -np.e])
    obj.rotation = np.array([np.pi, 1.0 / 9.0, 100.0 / 3.0])
    obj.scale = np.array([np.sqrt(2.0), 1.0 / 3.0, 3.0])
    other = _round_trip(scene)
    a, b = _by_name(scene, "Precise"), _by_name(other, "Precise")
    assert np.array_equal(a.mesh.points, b.mesh.points)
    assert np.array_equal(a.position, b.position) and np.array_equal(a.rotation, b.rotation)
    assert np.array_equal(a.scale, b.scale)
    assert a.mesh.polygons == b.mesh.polygons and a.mesh.loose_edges == b.mesh.loose_edges


def test_selection_mode_and_active_state():
    scene = _build_rich_scene()
    scene.set_mode("polygons")
    scene.set_active(_by_name(scene, "Line"), select=False)
    other = _round_trip(scene, "state1.quartz")
    assert other.mode == "polygons" and other.active.name == "Line" and other.object_selected is False
    scene.set_mode("edges")
    scene.set_active(_by_name(scene, "Boole Cube"))
    other = _round_trip(scene, "state2.quartz")
    assert other.mode == "edges" and other.active.name == "Boole Cube" and other.object_selected is True
    scene.set_mode("model")
    scene.set_active(None)
    other = _round_trip(scene, "state3.quartz")
    assert other.active is None and other.object_selected is False and other.mode == "model"
    assert len(other.objects) == len(scene.objects)


def test_view_passes_through_untouched():
    scene = _build_rich_scene()
    view = {"camera": {"position": [100.5, 200.25, -300.125], "target": [0, 0, 0], "fov": 36.0,
                       "projection": "perspective", "name": "Vista \u00e1gil"}, "grid": False,
            "extra": {"nested": [1, 2, {"a": None}]}}
    doc = full_document_from_scene(scene, view=view)
    assert doc.meta["view"] is view
    path = _tmp("view.quartz")
    FMT.save(path, doc, {})
    loaded = FMT.load(path)
    assert loaded.meta["view"] == view
    assert loaded.meta["active"] == doc.meta["active"] and loaded.meta["mode"] == "model"
    assert loaded.meta["selected"] is True and loaded.meta["warnings"] == []
    assert loaded.meta["unit"] == "cm"
    doc2 = full_document_from_scene(scene)
    assert "view" not in doc2.meta
    doc2.meta["view"] = {"camera": "x"}
    FMT.save(path, doc2, {})
    assert FMT.load(path).meta["view"] == {"camera": "x"}
    doc3 = full_document_from_scene(scene)
    FMT.save(path, doc3, {})
    assert FMT.load(path).meta["view"] == {}


def test_loaded_document_has_world_matrices_and_local_transforms():
    scene = _build_rich_scene()
    path = _tmp("doc.quartz")
    save_scene(scene, path)
    doc = FMT.load(path)
    assert [n.name for n in doc.nodes] == [o.name for o in scene.objects]
    for node, obj in zip(doc.nodes, scene.objects):
        assert np.allclose(node.matrix, obj.world_matrix(), atol=1e-9), obj.name
        assert node.position == tuple(float(v) for v in obj.position)
        assert node.scale == tuple(float(v) for v in obj.scale)
        assert (node.mesh is None) == (obj.kind != "polygon")


def test_unicode_names_and_path_with_spaces_and_accents():
    scene = _scene()
    names = ["Caf\u00e9 \u2615", "\u65e5\u672c\u8a9e \u540d\u524d", "\u00dcber \u00e7a va", "emoji \U0001F600", "tab\there",
             "quote \" and \\ slash"]
    for n in names:
        scene.add_object(n, Mesh.cube(5.0))
    scene.add_parametric("null", name="Gr\u00fapo \u00e3\u00f5")
    folder = os.path.join(TMP, "Pasta com espa\u00e7os e acentua\u00e7\u00e3o")
    os.makedirs(folder)
    path = os.path.join(folder, "Projeto \u00c1gil \u2014 vers\u00e3o 1.quartz")
    save_scene(scene, path)
    assert sorted(os.listdir(folder)) == ["Projeto \u00c1gil \u2014 vers\u00e3o 1.quartz"]
    other = _scene()
    open_scene(other, path)
    _same_scene(scene, other)
    assert [o.name for o in other.objects][1:] == names + ["Gr\u00fapo \u00e3\u00f5"]


def test_header_errors():
    _open_must_fail("empty.quartz", "", "not a Quartz project")
    _open_must_fail("garbage.quartz", "this is not json {", "not a Quartz project")
    _open_must_fail("binary.quartz", bytes([0xff, 0xfe, 0x00, 0x80]), "not a Quartz project")
    _open_must_fail("array.quartz", "[1, 2, 3]", "not a Quartz project")
    _open_must_fail("other.quartz", {"format": "gltf", "version": 1, "scene": {"objects": []}}, "format")
    good = _good_header()
    for key in ("format", "version", "scene"):
        broken = dict(good)
        del broken[key]
        _open_must_fail(f"missing_{key}.quartz", broken, key)
    broken = _good_header()
    del broken["scene"]["objects"]
    _open_must_fail("missing_objects.quartz", broken, "objects")
    for bad in ("1", 1.0, 0, -3, True, None):
        broken = _good_header()
        broken["version"] = bad
        _open_must_fail("badversion.quartz", broken, "version")
    broken = _good_header()
    broken["scene"] = []
    _open_must_fail("scene_list.quartz", broken, "scene")
    broken = _good_header()
    broken["scene"]["objects"] = {}
    _open_must_fail("objects_dict.quartz", broken, "objects")


def test_newer_version_is_refused_with_clear_message():
    data = _good_header()
    data["version"] = 2
    data["future"] = {"layout": "different"}
    del data["scene"]
    text = _expect_error(lambda: FMT.load(_write("newer.quartz", data)), "newer.quartz", "newer", "2")
    assert "newer version" in text
    scene = _scene()
    before = len(scene.objects)
    _expect_error(lambda: open_scene(scene, _tmp("newer.quartz")), "newer.quartz", "newer")
    assert len(scene.objects) == before


def test_malformed_objects_are_refused_and_scene_untouched():
    def with_object(**changes):
        data = _good_header()
        entry = data["scene"]["objects"][0]
        for k, v in changes.items():
            if v is KeyError:
                entry.pop(k, None)
            else:
                entry[k] = v
        return data

    _open_must_fail("o_notdict.quartz", dict(_good_header(), scene={"objects": [5]}), "object 0")
    _open_must_fail("o_name.quartz", with_object(name=5), "name")
    _open_must_fail("o_kind.quartz", with_object(kind=7), "kind")
    _open_must_fail("o_parent_range.quartz", with_object(parent=4), "parent")
    _open_must_fail("o_parent_self.quartz", with_object(parent=0), "parent")
    _open_must_fail("o_parent_type.quartz", with_object(parent="0"), "parent")
    _open_must_fail("o_position.quartz", with_object(position=[1, 2]), "position")
    _open_must_fail("o_rotation.quartz", with_object(rotation=["a", 0, 0]), "rotation")
    _open_must_fail("o_scale.quartz", with_object(scale=5), "scale")
    mesh = fmt_quartz._mesh_to_json(Mesh.cube(10.0))
    for label, change in (("points_odd", {"points": mesh["points"][:-1]}),
                          ("points_text", {"points": ["a"] * 3}),
                          ("poly_range", {"polygon_indices": [0, 1, 99, 3] + mesh["polygon_indices"][4:]}),
                          ("poly_sizes", {"polygon_sizes": [4]}),
                          ("poly_negative", {"polygon_sizes": [-4] + mesh["polygon_sizes"][1:]}),
                          ("poly_float", {"polygon_indices": [0.5] * len(mesh["polygon_indices"])}),
                          ("loose_odd", {"loose_edges": [0, 1, 2]}),
                          ("loose_range", {"loose_edges": [0, 50]})):
        bad = dict(mesh)
        bad.update(change)
        _open_must_fail(f"m_{label}.quartz", with_object(mesh=bad), "object 0")
    _open_must_fail("m_notdict.quartz", with_object(mesh=[1, 2]), "mesh")
    cycle = {"format": "quartz", "version": 1, "scene": {"objects": [
        {"name": "a", "kind": "polygon", "parent": 1, "mesh": mesh},
        {"name": "b", "kind": "polygon", "parent": 0, "mesh": mesh}]}, "view": {}}
    _open_must_fail("cycle.quartz", cycle, "cycle")


def test_unknown_kind_becomes_named_null_placeholder():
    mesh = fmt_quartz._mesh_to_json(Mesh.cube(10.0))
    data = {"format": "quartz", "version": 1, "app": "9.9.9", "scene": {"active": 0, "objects": [
        {"name": "Holo", "kind": "hologram", "params": {"a": 1}, "parent": None, "enabled": True,
         "position": [1, 2, 3], "rotation": [0, 30, 0], "scale": [1, 2, 1]},
        {"name": "Kid", "kind": "polygon", "parent": 0, "enabled": True, "position": [0, 5, 0],
         "mesh": mesh},
        {"name": "Sub Kid", "kind": "warp_drive", "parent": 0, "enabled": False,
         "position": [9, 9, 9]},
        {"name": "Sph", "kind": "sphere", "params": {"radius": 33, "bogus": 1}, "parent": None}]},
        "view": {"camera": 1}}
    path = _write("unknown.quartz", data)
    doc = FMT.load(path)
    warnings = doc.meta["warnings"]
    assert len(warnings) == 2
    assert "Holo" in warnings[0] and "hologram" in warnings[0]
    assert "Sub Kid" in warnings[1] and "warp_drive" in warnings[1]
    assert doc.meta["view"] == {"camera": 1} and doc.meta["app"] == "9.9.9"
    scene = _scene()
    open_scene(scene, path)
    holo = _by_name(scene, "Holo")
    assert holo.kind == "null" and len(holo.mesh.points) == 0 and not holo.error
    assert np.allclose(holo.position, [1, 2, 3]) and np.allclose(holo.rotation, [0, 30, 0])
    assert np.allclose(holo.scale, [1, 2, 1])
    assert _by_name(scene, "Kid").parent is holo and len(_by_name(scene, "Kid").mesh.points) == 8
    sub = _by_name(scene, "Sub Kid")
    assert sub.kind == "null" and sub.parent is holo and sub.enabled is False
    sph = _by_name(scene, "Sph")
    assert sph.kind == "sphere" and sph.params["radius"] == 33 and "bogus" not in sph.params
    assert len(sph.mesh.points) > 0
    assert scene.active is holo


def test_invalid_params_fall_back_to_defaults_with_warning():
    data = _good_header()
    data["scene"]["objects"] = [
        {"name": "Bad", "kind": "extrude", "params": {"movement": [1, 2]}},
        {"name": "Worse", "kind": "sphere", "params": [1, 2]},
        {"name": "Fine", "kind": "sphere", "params": {"radius": "12"}}]
    path = _write("badparams.quartz", data)
    doc = FMT.load(path)
    assert len(doc.meta["warnings"]) == 2
    assert doc.nodes[0].params == object_registry.get("extrude").defaults()
    assert doc.nodes[1].params == object_registry.get("sphere").defaults()
    assert doc.nodes[2].params["radius"] == 12.0
    scene = _scene()
    open_scene(scene, path)
    assert [o.kind for o in scene.objects] == ["extrude", "sphere", "sphere"]


def test_unknown_extra_keys_are_ignored():
    scene = _build_rich_scene()
    path = _tmp("extra.quartz")
    save_scene(scene, path)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    data["thumbnail"] = "abc"
    data["future_section"] = {"x": [1, 2, 3]}
    data["scene"]["lights"] = [{"kind": "sun"}]
    data["view"]["stereo"] = True
    for obj in data["scene"]["objects"]:
        obj["material"] = {"color": [1, 0, 0]}
        obj["tags"] = ["a", "b"]
        if "mesh" in obj and obj["mesh"] is not None:
            obj["mesh"]["uv"] = [0.0, 1.0]
            obj["mesh"]["selections"] = {"a": [1]}
    _write("extra2.quartz", data)
    other = _scene()
    open_scene(other, _tmp("extra2.quartz"))
    _same_scene(scene, other)
    doc = FMT.load(_tmp("extra2.quartz"))
    assert doc.meta["warnings"] == [] and doc.meta["view"]["stereo"] is True


def test_missing_optional_object_fields_use_defaults():
    data = _good_header()
    data["scene"]["objects"] = [{"name": "Bare"}, {"kind": "null"}]
    del data["app"]
    del data["view"]
    path = _write("bare.quartz", data)
    scene = _scene()
    open_scene(scene, path)
    bare = scene.objects[0]
    assert bare.name == "Bare" and bare.kind == "null"
    assert np.array_equal(bare.position, [0, 0, 0]) and np.array_equal(bare.scale, [1, 1, 1])
    assert scene.objects[1].kind == "null" and scene.objects[1].name == "Object"
    assert "view" not in FMT.load(path).meta


def test_atomic_save_keeps_previous_file_when_replace_fails():
    scene = _build_rich_scene()
    folder = os.path.join(TMP, "atomic")
    os.makedirs(folder)
    path = os.path.join(folder, "keep.quartz")
    save_scene(scene, path)
    with open(path, "rb") as handle:
        original = handle.read()
    scene.add_object("Different")
    real = os.replace
    seen = []

    def boom(src, dst):
        seen.append((src, dst))
        raise OSError("disk full")

    os.replace = boom
    try:
        _expect_error(lambda: save_scene(scene, path), "keep.quartz", "disk full")
    finally:
        os.replace = real
    assert len(seen) == 1
    assert os.path.dirname(os.path.abspath(seen[0][0])) == os.path.dirname(os.path.abspath(seen[0][1]))
    with open(path, "rb") as handle:
        assert handle.read() == original
    assert os.listdir(folder) == ["keep.quartz"]
    save_scene(scene, path)
    with open(path, "rb") as handle:
        assert handle.read() != original
    assert os.listdir(folder) == ["keep.quartz"]


def test_atomic_save_keeps_previous_file_when_content_cannot_be_encoded():
    folder = os.path.join(TMP, "atomic2")
    os.makedirs(folder)
    path = os.path.join(folder, "keep.quartz")
    scene = _scene()
    save_scene(scene, path)
    with open(path, "rb") as handle:
        original = handle.read()
    bad = Document([Node("a", None, kind="null", params={"oops": object()})])
    _expect_error(lambda: FMT.save(path, bad, {}), "object")
    bad = Document([Node("a", Mesh.cube(1.0))], {"view": {"x": object()}})
    _expect_error(lambda: FMT.save(path, bad, {}), "object")
    with open(path, "rb") as handle:
        assert handle.read() == original
    assert os.listdir(folder) == ["keep.quartz"]
    missing = os.path.join(folder, "no", "such", "dir", "x.quartz")
    _expect_error(lambda: save_scene(scene, missing), "x.quartz")
    assert os.listdir(folder) == ["keep.quartz"]


def test_save_overwrites_existing_file():
    scene = _scene()
    path = _tmp("overwrite.quartz")
    save_scene(scene, path)
    scene.add_object("Second")
    save_scene(scene, path)
    other = _scene()
    open_scene(other, path)
    assert [o.name for o in other.objects] == ["Cube", "Second"]


def test_undo_history_is_empty_after_open():
    scene = _build_rich_scene()
    path = _tmp("history.quartz")
    save_scene(scene, path)
    other = _scene()
    other.add_object("A")
    other.add_object("B")
    other.undo()
    assert other.can_undo() and other.can_redo()
    open_scene(other, path)
    assert not other.can_undo() and not other.can_redo()
    other.add_object("After")
    assert other.can_undo()
    assert other.undo() and "After" not in [o.name for o in other.objects]
    assert not other.can_undo()


def test_empty_scene_round_trip():
    scene = _scene()
    scene.remove_object(scene.objects[0])
    assert scene.objects == [] and scene.active is None
    other = _round_trip(scene)
    assert other.objects == [] and other.active is None and not other.can_undo()


def test_interchange_export_to_quartz_imports_back():
    scene = _build_rich_scene()
    scene.remove_object(_by_name(scene, "Group"))
    path = _tmp("flat.quartz")
    export_file(scene, path)
    other = _scene()
    other.remove_object(other.objects[0])
    created = import_file(other, path)
    drawn = [o for o in scene.render_objects() if len(o.mesh.points) and (o.mesh.polygons or o.mesh.loose_edges)]
    assert [o.name for o in created] == [o.name for o in drawn]
    assert len(created) >= 5
    for src, dst in zip(drawn, created):
        assert np.allclose(src.world_points(), dst.world_points(), atol=1e-6), src.name
        assert dst.kind == "polygon" and dst.parent is None


def test_100k_polygon_mesh_speed():
    nx, ny = 250, 400
    xs, ys = np.meshgrid(np.arange(nx + 1, dtype=float), np.arange(ny + 1, dtype=float))
    pts = np.stack([xs.ravel() * 1.25, np.sin(xs.ravel() * 0.1) * np.cos(ys.ravel() * 0.07) * 10.0, ys.ravel() * 0.8],
                   axis=1)
    idx = np.arange((nx + 1) * (ny + 1)).reshape(ny + 1, nx + 1)
    quads = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], axis=1)
    polys = [tuple(q) for q in quads.tolist()]
    assert len(polys) == 100000
    scene = _scene()
    scene.add_object("Big", Mesh(pts, polys))
    path = _tmp("big.quartz")
    t0 = time.perf_counter()
    save_scene(scene, path)
    t1 = time.perf_counter()
    other = _scene()
    open_scene(other, path)
    t2 = time.perf_counter()
    size = os.path.getsize(path) / 1e6
    print(f"     100000 polygons: save {t1 - t0:.2f} s, open {t2 - t1:.2f} s, file {size:.1f} MB")
    assert t1 - t0 < 15.0 and t2 - t1 < 15.0
    _same_mesh(_by_name(scene, "Big").mesh, _by_name(other, "Big").mesh, "Big")
    assert len(_by_name(other, "Big").mesh.polygons) == 100000


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
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
