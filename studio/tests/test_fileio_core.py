from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio import fileio, objects
from quartz_studio.fileio import (Document, FileFormat, FileFormatError, Node, add_document_to_scene,
                                  baked_mesh, compose, decompose, document_from_scene, export_file,
                                  full_document_from_scene, import_file, open_scene, registry,
                                  replace_scene, save_scene, triangulate, weld)
from quartz_studio.objects.registry import ObjectSpec, register as register_object
from quartz_studio.scene import Mesh, Scene, rotation_matrix

TMP = tempfile.mkdtemp(prefix="qz_fileio_core_")
NL = chr(10)


def _merge(_p: dict, inputs: list) -> Mesh:
    pts, polys, off = [], [], 0
    for inp in inputs:
        m = inp.mesh
        pts.append(m.points)
        polys.extend(tuple(i + off for i in poly) for poly in m.polygons)
        off += len(m.points)
    return Mesh(np.vstack(pts) if pts else np.zeros((0, 3)), polys)


register_object(ObjectSpec("test_fileio_core_merge", "Test FileIO Merge", "generator", _merge,
                           inputs="children"))


def _load_text(path: str) -> Document:
    nodes = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if not parts:
                continue
            m = np.eye(4)
            m[:3, 3] = [float(v) for v in parts[1:4]]
            nodes.append(Node(parts[0], Mesh.cube(100.0), m))
    return Document(nodes, {"unit": "cm"})


def _save_text(path: str, document: Document, options: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for node in document.nodes:
            pts = baked_mesh(node).points
            c = pts.mean(axis=0) if len(pts) else np.zeros(3)
            handle.write(f"{node.name} {c[0]:.3f} {c[1]:.3f} {c[2]:.3f}" + NL)


def _load_boom(path: str) -> Document:
    raise KeyError("broken")


def _load_garbage(path: str):
    return None


FMT_TEXT = fileio.register(FileFormat("test_fileio_core_text", "Test Text", (".tfcore",), _load_text,
                                      _save_text, "test"))
FMT_SAVE_ONLY = fileio.register(FileFormat("test_fileio_core_out", "Test Out", (".tfout",), None, _save_text))
FMT_LOAD_ONLY = fileio.register(FileFormat("test_fileio_core_in", "Test In", (".tfin",), _load_text, None))
FMT_BOOM = fileio.register(FileFormat("test_fileio_core_boom", "Test Boom", (".tfboom",), _load_boom, None))
FMT_GARBAGE = fileio.register(FileFormat("test_fileio_core_garbage", "Test Garbage", (".tfgarb",),
                                         _load_garbage, None))


def _scene() -> Scene:
    QApplication.instance() or QApplication([sys.argv[0]])
    return scene_mod.reset_scene()


def _by_name(scene: Scene, name: str):
    return next(o for o in scene.objects if o.name == name)


def _signed_volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        r = mesh.points[list(poly)]
        for k in range(1, len(r) - 1):
            total += float(np.dot(r[0], np.cross(r[k], r[k + 1])))
    return total / 6.0


def _tmp(name: str) -> str:
    return os.path.join(TMP, name)


def _write(name: str, text: str) -> str:
    path = _tmp(name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _lines(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().splitlines()


def test_registry_duplicates_refused():
    for bad in (FileFormat("test_fileio_core_text", "Again", (".tfother",)),
                FileFormat("test_fileio_core_other", "Again", (".TFCORE",))):
        try:
            fileio.register(bad)
        except ValueError:
            continue
        raise AssertionError("duplicate accepted")
    assert "test_fileio_core_other" not in registry.FORMATS
    try:
        fileio.register(FileFormat("test_fileio_core_noext", "None", ()))
    except ValueError:
        pass
    else:
        raise AssertionError("format without extension accepted")


def test_registry_lookup_and_filters():
    assert fileio.get("test_fileio_core_text") is FMT_TEXT
    assert fileio.by_path("C:/models/House.TFCORE") is FMT_TEXT
    assert fileio.by_path("a.tfcore") is FMT_TEXT
    assert fileio.by_path("a.unknownext") is None
    assert fileio.by_path("noextension") is None
    assert FMT_TEXT in fileio.importers() and FMT_TEXT in fileio.exporters()
    assert FMT_SAVE_ONLY not in fileio.importers() and FMT_SAVE_ONLY in fileio.exporters()
    assert FMT_LOAD_ONLY in fileio.importers() and FMT_LOAD_ONLY not in fileio.exporters()
    assert fileio.file_filter(FMT_TEXT) == "Test Text (*.tfcore)"
    filters = fileio.import_filters()
    assert filters[0].startswith("All supported (") and "*.tfcore" in filters[0] and "*.tfin" in filters[0]
    assert "Test Text (*.tfcore)" in filters and "Test Out (*.tfout)" not in filters
    assert "Test Out (*.tfout)" in fileio.export_filters()
    assert fileio.export_filters()[0].startswith("All supported (")


def test_fmt_modules_register_themselves():
    import pkgutil
    names = sorted(i.name for i in pkgutil.iter_modules(fileio.__path__) if i.name.startswith("fmt_"))
    for name in names:
        assert f"quartz_studio.fileio.{name}" in sys.modules


def test_triangulate_concave_ngon_keeps_area():
    pts = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (1, 1, 0), (1, 2, 0), (0, 2, 0)]
    mesh = Mesh(pts, [(0, 1, 2, 3, 4, 5)])
    points, tris = triangulate(mesh)
    assert tris.shape == (4, 3) and tris.dtype.kind == "i"
    area = 0.0
    for a, b, c in tris:
        n = np.cross(points[b] - points[a], points[c] - points[a])
        assert n[2] > 0
        area += 0.5 * n[2]
    assert abs(area - 3.0) < 1e-9
    assert np.allclose(points, mesh.points)


def test_triangulate_mixed_polygons():
    mesh = Mesh.cube(100.0)
    points, tris = triangulate(mesh)
    assert len(tris) == 12 and tris.max() < len(points)
    tri = Mesh(points, [tuple(t) for t in tris])
    assert abs(_signed_volume(tri) - 100.0 ** 3) < 1e-3
    assert triangulate(Mesh.empty())[1].shape == (0, 3)


def test_face_normals_match_winding():
    n = fileio.face_normals(Mesh.cube(100.0))
    assert n.shape == (6, 3) and np.allclose(np.linalg.norm(n, axis=1), 1.0)
    mesh = Mesh.cube(100.0)
    centers = np.array([mesh.points[list(p)].mean(axis=0) for p in mesh.polygons])
    assert np.all(np.sum(n * centers, axis=1) > 0)


def test_weld():
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 0.0000005], [1, 0, 0], [5, 5, 5],
                    [0.9999996, 0, 0]], float)
    unique, index = weld(pts, 1e-3)
    assert len(unique) == 3 and list(index) == [0, 1, 0, 1, 2, 1]
    assert np.allclose(unique[index], pts, atol=1e-3)
    unique, index = weld(pts, 0.0)
    assert len(unique) == 5 and np.array_equal(unique[index], pts)
    edge = np.array([[0.00099999, 0, 0], [0.0010001, 0, 0]], float)
    unique, index = weld(edge, 1e-3)
    assert len(unique) == 1 and list(index) == [0, 0]
    empty, none = weld(np.zeros((0, 3)), 1e-3)
    assert len(empty) == 0 and len(none) == 0


def test_decompose_compose_round_trip():
    cases = [((10, -20, 30), (25, -40, 70), (2, 3, 0.5)),
             ((0, 0, 0), (0, 0, 0), (1, 1, 1)),
             ((-5, 6, 7), (-80, 15, -120), (100, 1, 0.01)),
             ((1, 2, 3), (0, 0, 90), (1, 1, 1))]
    for pos, rot, scale in cases:
        m = compose(pos, rot, scale)
        assert m.shape == (4, 4) and np.allclose(m[3], [0, 0, 0, 1])
        assert np.allclose(m[:3, :3], rotation_matrix(rot) @ np.diag(scale))
        p, r, s = decompose(m)
        assert np.allclose(p, pos) and np.allclose(s, scale)
        assert np.allclose(compose(p, r, s), m, atol=1e-9)
        assert np.allclose(r, rot, atol=1e-6), (r, rot)
    p, r, s = decompose(compose((0, 0, 0), (10, 20, 30), (-1, 2, 3)))
    assert s[0] < 0 and np.allclose(compose(p, r, s)[:3, :3],
                                    rotation_matrix((10, 20, 30)) @ np.diag((-1, 2, 3)), atol=1e-9)
    obj = scene_mod.SceneObject("x", Mesh.cube(10.0))
    obj.position, obj.rotation, obj.scale = np.array([1.0, 2, 3]), np.array([15.0, 35, -50]), np.array([1.0, 2, 3])
    p, r, s = decompose(obj.local_matrix())
    assert np.allclose(r, obj.rotation, atol=1e-6) and np.allclose(p, obj.position)


def test_baked_mesh_world_space_and_mirror():
    m = compose((100, 0, 0), (0, 0, 0), (1, 1, 1))
    node = Node("a", Mesh.cube(100.0), m)
    baked = baked_mesh(node)
    assert np.allclose(baked.points.mean(axis=0), [100, 0, 0])
    assert _signed_volume(baked) > 0
    assert node.mesh.points.mean(axis=0).tolist() == [0.0, 0.0, 0.0]
    mirror = Node("m", Mesh.cube(100.0), compose((0, 0, 0), (0, 0, 0), (-1, 1, 2)))
    flipped = baked_mesh(mirror)
    assert _signed_volume(flipped) > 0 and abs(_signed_volume(flipped) - 2 * 100.0 ** 3) < 1e-3
    firsts = flipped.points[[p[0] for p in flipped.polygons]]
    assert np.all(np.sum(fileio.face_normals(flipped) * firsts, axis=1) > 0)
    assert len(baked_mesh(Node("n")).points) == 0


def _rich_scene() -> Scene:
    scene = _scene()
    sphere = scene.add_parametric("sphere", name="Ball")
    scene.set_param(sphere, "radius", 40.0)
    sphere.position = np.array([300.0, 0.0, 0.0])
    scene.changed.emit()
    gen = scene.add_parametric("test_fileio_core_merge", name="Gen")
    inner = scene.add_object("Consumed", Mesh.cube(50.0), activate=False)
    scene.set_parent(inner, gen)
    null = scene.add_parametric("null", name="Group")
    null.position = np.array([1000.0, 0.0, 0.0])
    null.rotation = np.array([0.0, 30.0, 0.0])
    child = scene.add_object("Child", Mesh.cube(100.0), activate=False)
    scene.set_parent(child, null)
    child.position = np.array([0.0, 100.0, 0.0])
    child.scale = np.array([1.0, 2.0, 1.0])
    scene.changed.emit()
    return scene


def test_document_from_scene_flat_interchange():
    scene = _rich_scene()
    assert len(_by_name(scene, "Gen").mesh.points) == 8
    doc = document_from_scene(scene)
    names = [n.name for n in doc.nodes]
    assert names == ["Cube", "Ball", "Gen", "Child"], names
    assert all(n.parent is None and n.kind == "polygon" and n.params is None for n in doc.nodes)
    assert doc.meta["unit"] == "cm"
    child = doc.nodes[3]
    assert np.allclose(baked_mesh(child).points, _by_name(scene, "Child").world_points())
    assert np.allclose(child.matrix, _by_name(scene, "Child").world_matrix())
    assert np.allclose(baked_mesh(child).points.mean(axis=0),
                       _by_name(scene, "Child").world_points().mean(axis=0))
    ball = baked_mesh(doc.nodes[1])
    assert np.allclose(ball.points.mean(axis=0), [300, 0, 0], atol=1e-6)
    assert len(doc.nodes[2].mesh.points) == 8
    assert doc.nodes[2].mesh is not _by_name(scene, "Gen").mesh


def test_flat_export_child_world_position_under_transformed_parent():
    scene = _scene()
    null = scene.add_parametric("null", name="Group")
    null.position = np.array([1000.0, 0.0, 0.0])
    child = scene.add_object("Child", Mesh.cube(100.0), activate=False)
    scene.set_parent(child, null)
    child.position = np.array([0.0, 100.0, 0.0])
    scene.changed.emit()
    doc = document_from_scene(scene)
    node = next(n for n in doc.nodes if n.name == "Child")
    assert np.allclose(baked_mesh(node).points.mean(axis=0), [1000.0, 100.0, 0.0])


def test_document_from_scene_selected_only():
    scene = _rich_scene()
    scene.set_active(_by_name(scene, "Ball"))
    assert [n.name for n in document_from_scene(scene, selected_only=True).nodes] == ["Ball"]
    scene.set_active(_by_name(scene, "Group"))
    assert [n.name for n in document_from_scene(scene, selected_only=True).nodes] == ["Child"]
    scene.set_active(None)
    assert document_from_scene(scene, selected_only=True).nodes == []
    scene.set_active(_by_name(scene, "Cube"), select=False)
    assert document_from_scene(scene, selected_only=True).nodes == []


def test_document_from_scene_skips_disabled_and_empty():
    scene = _scene()
    box = scene.add_object("Hidden", Mesh.cube(10.0))
    scene.add_object("Nothing", Mesh.empty())
    scene.set_enabled(box, False)
    assert [n.name for n in document_from_scene(scene).nodes] == ["Cube"]


def test_full_document_from_scene():
    scene = _rich_scene()
    doc = full_document_from_scene(scene)
    names = [n.name for n in doc.nodes]
    assert names == [o.name for o in scene.objects]
    by = {n.name: n for n in doc.nodes}
    assert by["Cube"].kind == "polygon" and by["Cube"].mesh is not None and by["Cube"].params is None
    assert by["Ball"].kind == "sphere" and by["Ball"].mesh is None and by["Ball"].params["radius"] == 40.0
    assert by["Gen"].kind == "test_fileio_core_merge" and by["Gen"].mesh is None
    assert names[by["Consumed"].parent] == "Gen" and names[by["Child"].parent] == "Group"
    assert by["Group"].parent is None and by["Group"].kind == "null"
    assert by["Child"].position == (0.0, 100.0, 0.0) and by["Child"].scale == (1.0, 2.0, 1.0)
    assert by["Group"].rotation == (0.0, 30.0, 0.0)
    assert np.allclose(by["Child"].matrix, _by_name(scene, "Child").world_matrix())
    assert names[doc.meta["active"]] == scene.active.name
    assert by["Ball"].params is not _by_name(scene, "Ball").params


def test_full_document_round_trip_through_replace_scene():
    source = _rich_scene()
    source.set_active(_by_name(source, "Child"))
    doc = full_document_from_scene(source)
    target = _scene()
    target.add_object("Junk")
    replace_scene(target, doc)
    assert [o.name for o in target.objects] == [o.name for o in source.objects]
    assert [o.kind for o in target.objects] == [o.kind for o in source.objects]
    for a, b in zip(source.objects, target.objects):
        assert np.allclose(a.world_matrix(), b.world_matrix()), a.name
        assert np.allclose(a.position, b.position) and np.allclose(a.rotation, b.rotation)
        assert np.allclose(a.scale, b.scale)
        assert (a.parent.name if a.parent else None) == (b.parent.name if b.parent else None)
        assert a.params == b.params
        assert a.mesh.points.shape == b.mesh.points.shape
        assert np.allclose(a.mesh.points, b.mesh.points, atol=1e-9) and a.mesh.polygons == b.mesh.polygons
    assert target.active.name == "Child"
    assert not target.can_undo() and not target.can_redo()
    assert not any(o.error for o in target.objects)


def test_add_document_to_scene_is_one_undo_step():
    scene = _scene()
    before = [o.name for o in scene.objects]
    m = np.eye(4)
    m[:3, 3] = [500.0, 0.0, 0.0]
    inner = np.eye(4)
    inner[:3, 3] = [500.0, 100.0, 0.0]
    doc = Document([
        Node("Cube", Mesh.cube(80.0), m),
        Node("Group", None, m.copy()),
        Node("Cube", Mesh.cube(20.0), inner, parent=1),
        Node("Sphere", None, np.eye(4), kind="sphere", params={"radius": 55.0}),
        Node("Ghost", None, np.eye(4), kind="no_such_kind", params={"a": 1}),
    ])
    created = add_document_to_scene(scene, doc)
    assert [o.name for o in created] == ["Cube.1", "Group", "Cube.2", "Sphere", "Ghost"]
    assert scene.active is created[0]
    assert len(scene.objects) == len(before) + 5
    assert created[1].kind == "null" and created[2].parent is created[1]
    assert created[3].kind == "sphere" and created[3].params["radius"] == 55.0
    assert len(created[3].mesh.points) > 0 and not created[3].error
    assert created[4].kind == "null"
    assert np.allclose(created[2].world_matrix(), inner)
    assert np.allclose(created[2].position, [0.0, 100.0, 0.0])
    assert np.allclose(created[0].mesh.size(), [80, 80, 80])
    assert scene.undo()
    assert [o.name for o in scene.objects] == before
    assert not scene.can_undo()
    assert scene.redo()
    assert len(scene.objects) == len(before) + 5
    assert _by_name(scene, "Sphere").params["radius"] == 55.0


def test_add_document_uses_given_local_transform_and_mirror():
    scene = _scene()
    parent = np.eye(4)
    parent[:3, 3] = [100.0, 0.0, 0.0]
    doc = Document([
        Node("P", None, parent, position=(100.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)),
        Node("M", Mesh.cube(10.0), compose((100, 0, 0), (0, 0, 0), (-1, 1, 1)), parent=0),
        Node("Late", Mesh.cube(10.0), compose((0, 5, 0), (0, 0, 0), (1, 1, 1)), parent=3),
        Node("Mid", None, np.eye(4)),
    ])
    p, m, late, mid = add_document_to_scene(scene, doc)
    assert np.allclose(m.position, [0, 0, 0]) and m.scale[0] == -1.0
    assert np.allclose(m.world_matrix(), doc.nodes[1].matrix)
    assert late.parent is mid
    names = [o.name for o in scene.objects]
    assert names.index("Mid") < names.index("Late")


def test_add_document_rejects_bad_hierarchy():
    scene = _scene()
    count = len(scene.objects)
    for parents in ((5,), (0,), (1, 0)):
        nodes = [Node(f"n{i}", Mesh.cube(1.0), parent=p) for i, p in enumerate(parents)]
        try:
            add_document_to_scene(scene, Document(nodes))
        except FileFormatError:
            pass
        else:
            raise AssertionError(f"parents {parents} accepted")
    assert len(scene.objects) == count and not scene.can_undo()


def test_add_empty_document_changes_nothing():
    scene = _scene()
    assert add_document_to_scene(scene, Document()) == []
    assert not scene.can_undo() and len(scene.objects) == 1


def test_replace_scene_clears_history():
    scene = _scene()
    scene.add_object("A")
    scene.add_object("B")
    scene.undo()
    assert scene.can_undo() and scene.can_redo()
    doc = Document([Node("Only", Mesh.cube(10.0)), Node("Second", Mesh.cube(10.0))])
    replace_scene(scene, doc)
    assert [o.name for o in scene.objects] == ["Only", "Second"]
    assert not scene.can_undo() and not scene.can_redo()
    assert scene.active is scene.objects[0] and scene.object_selected
    replace_scene(scene, Document())
    assert scene.objects == [] and scene.active is None and not scene.can_undo()
    scene.add_object("After")
    assert scene.can_undo()


def test_scene_insert_objects_and_clear_history():
    scene = _scene()
    scene.add_object("A")
    assert scene.can_undo()
    scene.clear_history()
    assert not scene.can_undo() and not scene.can_redo()
    a = scene_mod.SceneObject("A", Mesh.cube(1.0))
    b = scene_mod.SceneObject("B", Mesh.cube(1.0))
    out = scene.insert_objects([a, b], [None, 0])
    assert out == [a, b] and b.parent is a and a.name == "A.1"
    try:
        scene.insert_objects([scene_mod.SceneObject("C", Mesh.cube(1.0))], [0])
    except ValueError:
        pass
    else:
        raise AssertionError("self parent accepted")


def test_api_import_export_round_trip():
    scene = _scene()
    path = _write("in.tfcore", "Alpha 100 0 0" + NL + "Beta 0 200 0" + NL)
    created = import_file(scene, path)
    assert [o.name for o in created] == ["Alpha", "Beta"] and scene.active is created[0]
    assert np.allclose(created[1].world_matrix()[:3, 3], [0, 200, 0])
    assert scene.undo() and [o.name for o in scene.objects] == ["Cube"]
    scene.redo()
    out = _tmp("out.TFCORE")
    export_file(scene, out)
    lines = _lines(out)
    assert [ln.split()[0] for ln in lines] == ["Cube", "Alpha", "Beta"]
    assert lines[1].split()[1:] == ["100.000", "0.000", "0.000"]
    export_file(scene, _tmp("sel.tfout"), selected_only=True, options={"x": 1})
    assert [ln.split()[0] for ln in _lines(_tmp("sel.tfout"))] == ["Alpha"]


def test_api_open_and_save_scene():
    scene = _rich_scene()
    path = _tmp("scene.tfout")
    save_scene(scene, path)
    assert len(_lines(path)) == len(scene.objects)
    other = _scene()
    other.add_object("Extra")
    src = _write("open.tfcore", "One 1 2 3" + NL)
    open_scene(other, src)
    assert [o.name for o in other.objects] == ["One"] and not other.can_undo()


def _raises(fn, *needles):
    try:
        fn()
    except FileFormatError as exc:
        text = str(exc)
        for needle in needles:
            assert needle in text, (needle, text)
        return
    raise AssertionError("FileFormatError not raised")


def test_api_errors():
    scene = _scene()
    count = len(scene.objects)
    _raises(lambda: import_file(scene, _tmp("a.nosuchext")), "a.nosuchext")
    _raises(lambda: import_file(scene, _tmp("noextension")), "noextension")
    _raises(lambda: import_file(scene, _tmp("missing.tfcore")), "missing.tfcore", "not found")
    _raises(lambda: import_file(scene, _tmp("x.tfout")), "x.tfout")
    _raises(lambda: open_scene(scene, _tmp("x.tfout")), "x.tfout")
    _raises(lambda: export_file(scene, _tmp("x.tfin")), "x.tfin")
    _raises(lambda: save_scene(scene, _tmp("x.tfin")), "x.tfin")
    _raises(lambda: export_file(scene, _tmp("x.nosuchext")), "x.nosuchext")
    boom = _write("boom.tfboom", "x")
    _raises(lambda: import_file(scene, boom), "boom.tfboom", "KeyError")
    _raises(lambda: open_scene(scene, boom), "boom.tfboom")
    garb = _write("g.tfgarb", "x")
    _raises(lambda: import_file(scene, garb), "g.tfgarb")
    bad = _write("bad.tfcore", "Name notanumber 1 2" + NL)
    _raises(lambda: import_file(scene, bad), "bad.tfcore", "ValueError")
    scene.set_active(None)
    _raises(lambda: export_file(scene, _tmp("e.tfout"), selected_only=True), "e.tfout", "nothing")
    assert not os.path.exists(_tmp("e.tfout"))
    assert len(scene.objects) == count and not scene.can_undo()
    unwritable = os.path.join(TMP, "no", "such", "dir", "z.tfcore")
    _raises(lambda: export_file(scene, unwritable), "z.tfcore")


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
