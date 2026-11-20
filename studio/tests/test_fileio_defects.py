from __future__ import annotations

import base64
import json
import os
import struct
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio import fileio
from quartz_studio.fileio import (Document, FileFormatError, Node, export_file, import_file, open_scene,
                                  registry, replace_scene, triangulate)
from quartz_studio.scene import Mesh

TMP = tempfile.mkdtemp(prefix="qz_fileio_defects_")
SEQ = [0]
NL = chr(10)
BS = chr(92)
INTERCHANGE = ("obj", "stl", "ply", "gltf", "glb", "fbx")


def _scene():
    QApplication.instance() or QApplication([sys.argv[0]])
    scene = scene_mod.reset_scene()
    replace_scene(scene, Document([], {}))
    return scene


def _path(name: str) -> str:
    SEQ[0] += 1
    folder = os.path.join(TMP, f"c{SEQ[0]}")
    os.makedirs(folder)
    return os.path.join(folder, name)


def _write(name: str, content) -> str:
    path = _path(name)
    if isinstance(content, bytes):
        with open(path, "wb") as handle:
            handle.write(content)
    else:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return path


def _bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def _prism() -> Mesh:
    sides, radius, height = 5, 50.0, 150.0
    ring = [(radius * np.cos(2 * np.pi * j / sides), radius * np.sin(2 * np.pi * j / sides))
            for j in range(sides)]
    points = [(x, 0.0, z) for x, z in ring] + [(x, height, z) for x, z in ring]
    polygons = [tuple(reversed(range(sides))), tuple(range(sides, 2 * sides))]
    for j in range(sides):
        k = (j + 1) % sides
        polygons.append((j, k, sides + k, sides + j))
    return Mesh(points, polygons)


def _raises(fn, *needles: str) -> None:
    try:
        fn()
    except FileFormatError as exc:
        for needle in needles:
            assert needle in str(exc), f"{needle!r} not in {str(exc)!r}"
        return
    raise AssertionError("expected FileFormatError")


def _stl_points(path: str) -> np.ndarray:
    data = _bytes(path)
    count = struct.unpack_from("<I", data, 80)[0]
    rec = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return np.frombuffer(data, dtype=rec, count=count, offset=84)["v"].reshape(-1, 3).astype(float)


def _ply_points(path: str) -> np.ndarray:
    lines = _bytes(path).decode().splitlines()
    start = lines.index("end_header") + 1
    count = int(next(l for l in lines if l.startswith("element vertex")).split()[2])
    return np.array([[float(v) for v in l.split()] for l in lines[start:start + count]])


def _volume(mesh: Mesh) -> float:
    pts, tris = triangulate(mesh)
    return sum(float(np.dot(pts[a], np.cross(pts[b], pts[c]))) for a, b, c in tris) / 6.0


def test_stl_and_ply_export_are_z_up():
    doc = Document([Node("Prism", _prism())], {"unit": "cm"})
    for fmt_id, reader in (("stl", _stl_points), ("ply", _ply_points)):
        path = _path(f"p.{fmt_id}")
        registry.get(fmt_id).save(path, doc, {})
        pts = reader(path)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        assert abs((hi[2] - lo[2]) - 150.0) < 1e-3, (fmt_id, lo, hi)
        depth = float(_prism().points[:, 2].max() - _prism().points[:, 2].min())
        assert abs((hi[1] - lo[1]) - depth) < 1e-3, (fmt_id, lo, hi)
        back = registry.get(fmt_id).load(path).nodes[0].mesh
        blo, bhi = back.points.min(axis=0), back.points.max(axis=0)
        assert abs((bhi[1] - blo[1]) - 150.0) < 1e-3, (fmt_id, blo, bhi)


def test_stl_and_ply_import_treat_z_as_height():
    tri = np.array([[[0, 0, 0], [10, 0, 0], [0, 0, 30]]], dtype="<f4")
    rec = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    records = np.zeros(1, dtype=rec)
    records["v"] = tri
    data = b"x".ljust(80, b" ") + struct.pack("<I", 1) + records.tobytes()
    mesh = registry.get("stl").load(_write("z.stl", data)).nodes[0].mesh
    assert abs(mesh.points[:, 1].max() - 30.0) < 1e-4
    assert abs(mesh.points[:, 2].max()) < 1e-4 and abs(mesh.points[:, 2].min()) < 1e-4
    text = ("ply" + NL + "format ascii 1.0" + NL + "element vertex 3" + NL + "property float x" + NL
            + "property float y" + NL + "property float z" + NL + "element face 1" + NL
            + "property list uchar int vertex_indices" + NL + "end_header" + NL
            + "0 0 0" + NL + "10 0 0" + NL + "0 0 30" + NL + "3 0 1 2" + NL)
    mesh = registry.get("ply").load(_write("z.ply", text)).nodes[0].mesh
    assert abs(mesh.points[:, 1].max() - 30.0) < 1e-4


def test_stl_ply_round_trip_keeps_pose_and_winding():
    mesh = _prism()
    for fmt_id in ("stl", "ply"):
        path = _path(f"r.{fmt_id}")
        registry.get(fmt_id).save(path, Document([Node("P", mesh)], {}), {})
        back = registry.get(fmt_id).load(path).nodes[0].mesh
        assert np.allclose(np.sort(back.points, axis=0), np.sort(mesh.points, axis=0), atol=1e-3), fmt_id
        assert _volume(back) * _volume(mesh) > 0.0, (fmt_id, _volume(back), _volume(mesh))
        assert abs(_volume(back) - _volume(mesh)) < 1e-3 * abs(_volume(mesh)), fmt_id


def test_obj_name_with_hash_round_trips():
    scene = _scene()
    scene.add_object("Part #7", Mesh.cube(10.0))
    path = _path("a.obj")
    export_file(scene, path)
    other = _scene()
    objs = import_file(other, path)
    assert objs[0].name == "Part #7", objs[0].name


def test_obj_comments_still_stripped():
    text = ("# header" + NL + "o Box # trailing" + NL + "v 0 0 0 # c" + NL + "v 1 0 0" + NL
            + "v 0 1 0#c" + NL + "f 1 2 3 # face" + NL)
    doc = registry.get("obj").load(_write("c.obj", text))
    assert len(doc.nodes[0].mesh.polygons) == 1


def test_obj_backslash_continuation():
    text = ("v 0 0 0" + NL + "v 1 0 0" + NL + "v 1 1 0" + NL + "v 0 1 0" + NL
            + "f 1 2 " + BS + NL + " 3 4" + NL)
    mesh = registry.get("obj").load(_write("k.obj", text)).nodes[0].mesh
    assert mesh.polygons == [(0, 1, 2, 3)], mesh.polygons
    crlf = text.replace(NL, chr(13) + NL)
    mesh = registry.get("obj").load(_write("k2.obj", crlf)).nodes[0].mesh
    assert mesh.polygons == [(0, 1, 2, 3)], mesh.polygons


def test_stl_without_triangles_is_refused():
    wire = Mesh([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1), (1, 2)])
    path = _path("w.stl")
    _raises(lambda: registry.get("stl").save(path, Document([Node("W", wire)], {}), {}),
            "nothing to export")
    assert not os.path.exists(path)
    scene = _scene()
    scene.add_object("Line", wire)
    _raises(lambda: export_file(scene, _path("w2.stl")), "nothing to export")


def test_ply_and_fbx_keep_loose_edges():
    wire = Mesh([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 5)], [], [(0, 1), (1, 2), (2, 3)])
    for fmt_id in ("ply", "fbx"):
        scene = _scene()
        scene.add_object("Wire", wire)
        path = _path(f"w.{fmt_id}")
        export_file(scene, path)
        other = _scene()
        mesh = import_file(other, path)[0].mesh
        assert len(mesh.points) == 4, (fmt_id, len(mesh.points))
        assert sorted(tuple(sorted(e)) for e in mesh.loose_edges) == [(0, 1), (1, 2), (2, 3)], fmt_id
        assert not mesh.polygons, fmt_id


def test_ply_mixed_faces_and_edges_round_trip():
    mesh = Mesh([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0), (20, 0, 0)],
                [(0, 1, 2, 3)], [(1, 4)])
    path = _path("m.ply")
    registry.get("ply").save(path, Document([Node("M", mesh)], {}), {})
    back = registry.get("ply").load(path).nodes[0].mesh
    assert len(back.polygons) == 1 and len(back.loose_edges) == 1 and len(back.points) == 5


def test_ply_welds_duplicate_positions():
    text = ("ply" + NL + "format ascii 1.0" + NL + "element vertex 6" + NL + "property float x" + NL
            + "property float y" + NL + "property float z" + NL + "property float s" + NL
            + "element face 2" + NL + "property list uchar int vertex_indices" + NL + "end_header" + NL
            + "0 0 0 0" + NL + "1 0 0 0" + NL + "1 1 0 0" + NL + "0 0 0 1" + NL + "1 1 0 1" + NL
            + "0 1 0 0" + NL + "3 0 1 2" + NL + "3 3 4 5" + NL)
    mesh = registry.get("ply").load(_write("weld.ply", text)).nodes[0].mesh
    assert len(mesh.points) == 4, len(mesh.points)
    assert len(mesh.polygons) == 2
    edges = {}
    for poly in mesh.polygons:
        for k in range(len(poly)):
            key = tuple(sorted((poly[k], poly[(k + 1) % len(poly)])))
            edges[key] = edges.get(key, 0) + 1
    assert max(edges.values()) == 2


def _existing_file(fmt_id: str) -> tuple[str, bytes]:
    path = _path(f"keep.{fmt_id}")
    original = b"ORIGINAL"
    with open(path, "wb") as handle:
        handle.write(original)
    return path, original


def test_failed_export_keeps_existing_file():
    doc = Document([Node("Prism", _prism())], {"unit": "cm"})
    for fmt_id in INTERCHANGE:
        path, original = _existing_file(fmt_id)
        real = os.replace

        def broken(*args, **kwargs):
            raise OSError("disk full")

        os.replace = broken
        try:
            try:
                registry.get(fmt_id).save(path, doc, {})
            except OSError:
                pass
            else:
                raise AssertionError(f"{fmt_id}: expected the write to fail")
        finally:
            os.replace = real
        assert _bytes(path) == original, fmt_id
        assert os.listdir(os.path.dirname(path)) == [os.path.basename(path)], (fmt_id, os.listdir(os.path.dirname(path)))
        registry.get(fmt_id).save(path, doc, {})
        assert _bytes(path) != original, fmt_id


def test_failed_fsync_keeps_existing_file():
    doc = Document([Node("Prism", _prism())], {"unit": "cm"})
    for fmt_id in INTERCHANGE:
        path, original = _existing_file(fmt_id)
        real = os.fsync

        def broken(*args, **kwargs):
            raise OSError("io error")

        os.fsync = broken
        try:
            try:
                registry.get(fmt_id).save(path, doc, {})
            except OSError:
                pass
        finally:
            os.fsync = real
        assert _bytes(path) == original, fmt_id
        assert os.listdir(os.path.dirname(path)) == [os.path.basename(path)], fmt_id


def test_large_ngon_triangulates_fast():
    for n in (2000, 6000):
        angle = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
        points = np.column_stack([100.0 * np.cos(angle), np.zeros(n), -100.0 * np.sin(angle)])
        mesh = Mesh(points, [tuple(range(n))])
        started = time.perf_counter()
        pts, tris = triangulate(mesh)
        elapsed = time.perf_counter() - started
        assert elapsed < 2.0, (n, elapsed)
        assert len(tris) == n - 2
        area = 0.0
        for a, b, c in tris:
            area += np.linalg.norm(np.cross(pts[b] - pts[a], pts[c] - pts[a])) / 2.0
        assert abs(area - 0.5 * n * 100.0 ** 2 * np.sin(2 * np.pi / n)) < 1.0
        normals = np.cross(pts[tris[:, 1]] - pts[tris[:, 0]], pts[tris[:, 2]] - pts[tris[:, 0]])
        assert (normals[:, 1] > 0).all()
    scene = _scene()
    scene.add_object("Big", mesh)
    for fmt_id in ("stl", "glb"):
        started = time.perf_counter()
        export_file(scene, _path(f"big.{fmt_id}"))
        assert time.perf_counter() - started < 5.0, fmt_id


def test_large_concave_ngon_triangulates_fast_and_keeps_area():
    n = 3000
    angle = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    radius = np.where(np.arange(n) % 2 == 0, 100.0, 70.0)
    points = np.column_stack([radius * np.cos(angle), np.zeros(n), -radius * np.sin(angle)])
    mesh = Mesh(points, [tuple(range(n))])
    started = time.perf_counter()
    pts, tris = triangulate(mesh)
    assert time.perf_counter() - started < 10.0
    assert len(tris) == n - 2
    area = sum(np.linalg.norm(np.cross(pts[b] - pts[a], pts[c] - pts[a])) / 2.0 for a, b, c in tris)
    expected = 0.5 * np.sum(radius * np.roll(radius, -1)) * np.sin(2 * np.pi / n)
    assert abs(area - expected) < 1e-3 * expected, (area, expected)


def _quartz_text(objects: list) -> str:
    return json.dumps({"format": "quartz", "version": 1, "scene": {"objects": objects}, "view": {}},
                     separators=(",", ":"))


def _quartz_object(**extra) -> dict:
    entry = {"name": "A", "kind": "polygon", "parent": None, "enabled": True,
             "position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]}
    entry.update(extra)
    return entry


def test_quartz_rejects_non_finite_and_degenerate_polygons():
    scene = _scene()
    bad_position = _quartz_text([_quartz_object(position=[0, 0, 0])]).replace("[0,0,0],\"rotation", "[NaN,0,0],\"rotation", 1)
    assert "NaN" in bad_position
    _raises(lambda: open_scene(scene, _write("nan.quartz", bad_position)), "nan.quartz", "position")
    inf_scale = _quartz_text([_quartz_object()]).replace('"scale":[1,1,1]', '"scale":[Infinity,1,1]')
    _raises(lambda: open_scene(scene, _write("inf.quartz", inf_scale)), "scale")
    huge = _quartz_text([_quartz_object(scale=[1e308, 1, 1])])
    _raises(lambda: open_scene(scene, _write("huge.quartz", huge)), "scale")
    mesh = {"points": [0, 0, 0, 1, 0, 0, 0, 1, 0], "polygon_sizes": [0, 1, 2],
            "polygon_indices": [0, 1], "loose_edges": []}
    _raises(lambda: open_scene(scene, _write("tiny.quartz", _quartz_text([_quartz_object(mesh=mesh)]))),
            "tiny.quartz", "polygon")
    nan_points = {"points": [0, 0, 0, 1, 0, 0, 0, "x", 0], "polygon_sizes": [], "polygon_indices": [],
                  "loose_edges": []}
    _raises(lambda: open_scene(scene, _write("pt.quartz", _quartz_text([_quartz_object(mesh=nan_points)]))),
            "pt.quartz")
    nan_mesh = _quartz_text([_quartz_object(mesh={"points": [0, 0, 0, 1, 0, 0, 0, 1, 0],
                                                  "polygon_sizes": [3], "polygon_indices": [0, 1, 2],
                                                  "loose_edges": []})]).replace("[0,0,0,1,0,0,0,1,0]",
                                                                                "[0,0,0,1,0,0,0,NaN,0]")
    _raises(lambda: open_scene(scene, _write("pt2.quartz", nan_mesh)), "pt2.quartz")


def test_exporters_refuse_non_finite_coordinates():
    bad = Mesh([(0, 0, 0), (1, 0, 0), (float("nan"), 1, 0)], [(0, 1, 2)])
    doc = Document([Node("Bad", bad)], {"unit": "cm"})
    for fmt_id in ("obj", "stl", "ply", "fbx", "gltf", "glb"):
        path = _path(f"nan.{fmt_id}")
        _raises(lambda: registry.get(fmt_id).save(path, doc, {}), "finite")
        assert not os.path.exists(path), fmt_id
    moved = np.eye(4)
    moved[0, 3] = float("inf")
    doc = Document([Node("Far", Mesh.cube(1.0), moved)], {"unit": "cm"})
    for fmt_id in ("obj", "stl", "ply", "fbx"):
        _raises(lambda: registry.get(fmt_id).save(_path(f"inf.{fmt_id}"), doc, {}), "finite")


def test_obj_and_stl_errors_name_the_file():
    scene = _scene()
    obj = _write("bad.obj", "v 0 0 0" + NL + "v 1 0 0" + NL + "v 0 1 0" + NL + "f 1 2 99999999999999999999" + NL)
    _raises(lambda: import_file(scene, obj), "bad.obj", "out of range")
    _raises(lambda: registry.get("obj").load(obj), "bad.obj", "out of range")
    stl = _write("bad.stl", "solid x" + NL + "facet normal 0 0 1" + NL + "outer loop" + NL
                 + "vertex nan 0 0" + NL + "vertex 1 0 0" + NL + "vertex 0 1 0" + NL + "endloop" + NL
                 + "endfacet" + NL + "endsolid x" + NL)
    _raises(lambda: import_file(scene, stl), "bad.stl", "finite")
    _raises(lambda: registry.get("stl").load(stl), "bad.stl", "finite")


def _gltf_with_points() -> str:
    blob = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0) + struct.pack("<3f", 5, 5, 5)
    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "Mixed"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 4},
                                   {"attributes": {"POSITION": 1}, "mode": 0}]}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                       "min": [0, 0, 0], "max": [1, 1, 0]},
                      {"bufferView": 1, "componentType": 5126, "count": 1, "type": "VEC3",
                       "min": [5, 5, 5], "max": [5, 5, 5]}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
                        {"buffer": 0, "byteOffset": 36, "byteLength": 12}],
        "buffers": [{"byteLength": 48,
                     "uri": "data:application/octet-stream;base64," + base64.b64encode(blob).decode()}],
    }
    return json.dumps(gltf)


def test_gltf_points_primitive_is_ignored():
    mesh = registry.get("gltf").load(_write("mixed.gltf", _gltf_with_points())).nodes[0].mesh
    assert len(mesh.polygons) == 1
    assert len(mesh.points) == 3


def test_gltf_only_points_is_still_refused_clearly():
    text = json.loads(_gltf_with_points())
    text["meshes"][0]["primitives"] = text["meshes"][0]["primitives"][1:]
    path = _write("only.gltf", json.dumps(text))
    try:
        doc = registry.get("gltf").load(path)
    except FileFormatError as exc:
        assert "only.gltf" in str(exc)
    else:
        assert all(n.mesh is None or not n.mesh.polygons for n in doc.nodes)


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
