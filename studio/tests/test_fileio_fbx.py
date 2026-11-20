from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio import fileio, objects
from quartz_studio.fileio import (Document, FileFormatError, Node, baked_mesh, compose, export_file,
                                  fmt_fbx, import_file, registry)
from quartz_studio.objects import registry as object_registry
from quartz_studio.scene import Mesh, rotation_matrix

TMP = tempfile.mkdtemp(prefix="qz_fileio_fbx_")
NL = chr(10)
BLENDER = os.path.join("C:" + os.sep, "Program Files", "Blender Foundation", "Blender 5.2", "blender.exe")
MAGIC = b"Kaydara FBX Binary  " + bytes((0, 26, 0))
FOOT_ID = bytes.fromhex("fabcab09d0c8d466b176fb831cf7267e")
FOOT_MAGIC = bytes.fromhex("f85a8c6adef5d97eece90ce3758f290b")
FILE_ID = bytes.fromhex("28b32aebb624ccc2bfc8b02aa92bfcf1")


class Skip(Exception):
    pass


def _tmp(name: str) -> str:
    return os.path.join(TMP, name)


def _write_text(name: str, text: str) -> str:
    path = _tmp(name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _write_bytes(name: str, data: bytes) -> str:
    path = _tmp(name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def _read(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def _round(doc: Document, name: str, options: dict | None = None) -> tuple[Document, str]:
    path = _tmp(name)
    fmt_fbx.save(path, doc, options or {})
    return fmt_fbx.load(path), path


def _signed_volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        r = mesh.points[list(poly)]
        for k in range(1, len(r) - 1):
            total += float(np.dot(r[0], np.cross(r[k], r[k + 1])))
    return total / 6.0


def _l_prism() -> Mesh:
    outline = [(0, 0), (200, 0), (200, 60), (70, 60), (70, 160), (0, 160)]
    pts = [(x, 0.0, z) for x, z in outline] + [(x, 80.0, z) for x, z in outline]
    n = len(outline)
    polys = [tuple(range(n)), tuple(range(n, 2 * n))]
    polys += [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    mesh = Mesh(np.asarray(pts, float), polys)
    fixed = []
    for poly, normal in zip(polys, mesh.polygon_normals()):
        if len(poly) == n:
            want = -1.0 if poly[0] == 0 else 1.0
            ok = normal[1] * want > 0
        else:
            a, b = mesh.points[poly[0]], mesh.points[poly[1]]
            edge = b - a
            out = np.array([edge[2], 0.0, -edge[0]])
            ok = np.dot(out, normal) > 0
            mid = (a + b) / 2.0
            inside = _inside_l(mid[0] + out[0] * 0.01, mid[2] + out[2] * 0.01)
            if inside:
                ok = not ok
        fixed.append(tuple(poly) if ok else tuple(reversed(poly)))
    result = Mesh(np.asarray(pts, float), fixed)
    if _signed_volume(result) < 0:
        result = Mesh(np.asarray(pts, float), [tuple(reversed(p)) for p in fixed])
    return result


def _inside_l(x: float, z: float) -> bool:
    return (0 < x < 200 and 0 < z < 60) or (0 < x < 70 and 0 < z < 160)


def _sphere() -> Mesh:
    return object_registry.get("sphere").build(object_registry.defaults("sphere"), [])


def _tree(path: str):
    return fmt_fbx.read_tree(_read(path))


def _find(elems, name):
    return [e for e in elems if e.name == name]


def _walk(data: bytes, wide: bool = False):
    meta = struct.Struct("<3Q" if wide else "<3I")
    sentinel = bytes(meta.size + 1)
    records = []

    def node(pos: int, depth: int):
        end, count, plen = meta.unpack_from(data, pos)
        namelen = data[pos + meta.size]
        if end == 0:
            assert data[pos:pos + meta.size + 1] == sentinel
            return None, pos + meta.size + 1
        name = data[pos + meta.size + 1:pos + meta.size + 1 + namelen].decode("ascii")
        props_at = pos + meta.size + 1 + namelen
        p = props_at + plen
        kids = 0
        closed = False
        while p < end:
            child, p = node(p, depth + 1)
            if child is None:
                closed = True
                break
            kids += 1
        assert p == end, (name, p, end)
        if kids:
            assert closed and data[end - len(sentinel):end] == sentinel, name
        records.append({"name": name, "depth": depth, "start": pos, "end": end, "count": count,
                        "props_at": props_at, "kids": kids})
        return name, end

    pos = len(MAGIC) + 4
    while True:
        name, pos = node(pos, 0)
        if name is None:
            break
    return records, pos


def _assert_points_match(a, b, tol: float) -> None:
    a = np.asarray(a, float).reshape(-1, 3)
    b = np.asarray(b, float).reshape(-1, 3)
    assert len(a) == len(b), (len(a), len(b))
    d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    worst = max(float(d.min(axis=1).max()), float(d.min(axis=0).max()))
    assert worst < tol, worst


def test_registered():
    fmt = registry.get("fbx")
    assert fmt.label == "FBX" and fmt.extensions == (".fbx",)
    assert fmt.load is not None and fmt.save is not None
    assert registry.by_path("C:/models/Thing.FBX") is fmt
    assert fmt in fileio.importers() and fmt in fileio.exporters()


def test_cube_round_trip():
    cube = Mesh.cube(200.0)
    doc, _ = _round(Document([Node("Cube", cube)]), "cube.fbx")
    assert len(doc.nodes) == 1
    node = doc.nodes[0]
    assert node.name == "Cube" and node.parent is None
    assert np.allclose(node.mesh.points, cube.points, atol=1e-12)
    assert node.mesh.polygons == cube.polygons
    assert np.allclose(node.matrix, np.eye(4), atol=1e-12)
    assert _signed_volume(baked_mesh(node)) > 0
    assert doc.meta["unit"] == "cm" and doc.meta["up"] == "y"


def test_sphere_round_trip():
    sphere = _sphere()
    assert len(sphere.polygons) > 50
    doc, _ = _round(Document([Node("Sphere", sphere)]), "sphere.fbx")
    mesh = doc.nodes[0].mesh
    assert np.allclose(mesh.points, sphere.points, atol=1e-12)
    assert mesh.polygons == sphere.polygons
    assert np.isclose(_signed_volume(mesh), _signed_volume(sphere), rtol=1e-12)


def test_ngon_round_trip_keeps_concave_ngons():
    prism = _l_prism()
    assert _signed_volume(prism) > 0
    plate = Mesh([(np.cos(a) * 50, 0.0, -np.sin(a) * 50) for a in np.linspace(0, 2 * np.pi, 8)[:-1]],
                 [tuple(range(7))])
    doc, path = _round(Document([Node("Prism", prism), Node("Plate", plate)]), "ngon.fbx")
    assert doc.nodes[0].mesh.polygons == prism.polygons
    assert sorted(len(p) for p in doc.nodes[0].mesh.polygons) == [4] * 6 + [6, 6]
    assert doc.nodes[1].mesh.polygons == [tuple(range(7))]
    _, top = _tree(path)
    geoms = _find(_find(top, "Objects")[0].children, "Geometry")
    pvi = geoms[0].child("PolygonVertexIndex").props[0]
    ends = np.flatnonzero(pvi < 0)
    assert len(ends) == 8 and ends[-1] == len(pvi) - 1
    assert int(~pvi[ends[0]]) == prism.polygons[0][-1]


def test_two_objects():
    m2 = compose((300.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    doc, _ = _round(Document([Node("First", Mesh.cube(100.0)), Node("Second", _sphere(), m2)]), "two.fbx")
    assert [n.name for n in doc.nodes] == ["First", "Second"]
    assert all(n.parent is None for n in doc.nodes)
    assert np.allclose(doc.nodes[1].matrix, m2)
    assert len(doc.nodes[0].mesh.points) == 8


def test_transform_rotation_and_nonuniform_scale():
    m = compose((150.0, 50.0, -80.0), (30.0, 45.0, 60.0), (1.0, 2.0, 0.5))
    cube = Mesh.cube(100.0)
    doc, path = _round(Document([Node("Moved", cube, m)]), "transform.fbx")
    node = doc.nodes[0]
    assert np.allclose(node.matrix, m, atol=1e-9)
    assert np.allclose(baked_mesh(node).points, baked_mesh(Node("x", cube, m)).points, atol=1e-9)
    _, top = _tree(path)
    model = _find(_find(top, "Objects")[0].children, "Model")[0]
    props = fmt_fbx._props(model)
    assert np.allclose(props["Lcl Rotation"], (30.0, 45.0, 60.0), atol=1e-9)
    assert np.allclose(props["Lcl Scaling"], (1.0, 2.0, 0.5), atol=1e-9)
    assert np.allclose(props["Lcl Translation"], (150.0, 50.0, -80.0), atol=1e-9)
    assert "RotationOrder" not in props


def test_mirrored_object():
    m = compose((-200.0, 10.0, 0.0), (0.0, 30.0, 0.0), (-1.0, 1.0, 1.0))
    prism = _l_prism()
    doc, _ = _round(Document([Node("Mirror", prism, m)]), "mirror.fbx")
    node = doc.nodes[0]
    assert np.allclose(node.matrix, m, atol=1e-9)
    assert np.linalg.det(node.matrix[:3, :3]) < 0
    assert _signed_volume(baked_mesh(node)) > 0
    assert node.mesh.polygons == prism.polygons


def test_hierarchy_round_trip():
    parent = compose((100.0, 0.0, 0.0), (0.0, 0.0, 30.0), (2.0, 2.0, 2.0))
    child = parent @ compose((0.0, 50.0, 0.0), (10.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    nodes = [Node("Parent", None, parent), Node("Child", Mesh.cube(50.0), child, 0),
             Node("Free", Mesh.cube(10.0), np.eye(4), 7)]
    doc, path = _round(Document(nodes), "hier.fbx")
    assert [n.name for n in doc.nodes] == ["Parent", "Child", "Free"]
    assert doc.nodes[0].mesh is None and doc.nodes[1].parent == 0 and doc.nodes[2].parent is None
    assert np.allclose(doc.nodes[0].matrix, parent, atol=1e-9)
    assert np.allclose(doc.nodes[1].matrix, child, atol=1e-9)
    _, top = _tree(path)
    models = _find(_find(top, "Objects")[0].children, "Model")
    assert [m.props[2] for m in models] == ["Null", "Mesh", "Mesh"]
    local = fmt_fbx._props(models[1])
    assert np.allclose(local["Lcl Translation"], (0.0, 50.0, 0.0), atol=1e-9)


def test_given_local_transform_is_written():
    nodes = [Node("P", None, compose((0, 10, 0), (0, 0, 0), (1, 1, 1)), None, position=(0, 10, 0),
                  rotation=(0, 0, 0), scale=(1, 1, 1)),
             Node("C", Mesh.cube(10.0), compose((5, 10, 0), (0, 20, 0), (1, 1, 1)), 0, position=(5, 0, 0),
                  rotation=(0, 20, 0), scale=(1, 1, 1))]
    doc, _ = _round(Document(nodes), "given.fbx")
    assert np.allclose(doc.nodes[1].matrix, nodes[1].matrix, atol=1e-9)


def test_binary_structure():
    m = compose((10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    nodes = [Node("Cube", Mesh.cube(200.0)), Node("Ball", _sphere(), m), Node("Group", None)]
    path = _tmp("structure.fbx")
    fmt_fbx.save(path, Document(nodes), {})
    data = _read(path)
    assert data[:23] == MAGIC and len(MAGIC) == 23
    assert struct.unpack_from("<I", data, 23)[0] == 7400
    records, q = _walk(data)
    assert data[q - 13:q] == bytes(13)
    assert data[q:q + 16] == FOOT_ID and data[q + 16:q + 20] == bytes(4)
    r = q + 20
    pad = 0
    while data[r + pad] == 0 and (r + pad) % 16 != 0:
        pad += 1
    if pad == 0:
        pad = 16
    assert (r + pad) % 16 == 0 and 1 <= pad <= 16 and data[r:r + pad] == bytes(pad)
    v = r + pad
    assert struct.unpack_from("<I", data, v)[0] == 7400
    assert data[v + 4:v + 124] == bytes(120)
    assert data[v + 124:] == FOOT_MAGIC
    top_names = [rec["name"] for rec in sorted(records, key=lambda x: x["start"]) if rec["depth"] == 0]
    assert top_names == ["FBXHeaderExtension", "FileId", "CreationTime", "Creator", "GlobalSettings",
                         "Documents", "References", "Definitions", "Objects", "Connections", "Takes"]
    for rec in records:
        if rec["name"] in ("Model", "Geometry") and rec["depth"] == 1:
            assert data[rec["props_at"]] == ord("L")
    _, top = _tree(path)
    first = {e.name: e for e in top}
    assert first["FileId"].props[0] == FILE_ID
    assert first["CreationTime"].props[0] == "1970-01-01 10:00:00:000"
    gs = fmt_fbx._props(first["GlobalSettings"])
    assert gs["UpAxis"] == [1] and gs["FrontAxis"] == [2] and gs["CoordAxis"] == [0]
    assert gs["UpAxisSign"] == [1] and gs["FrontAxisSign"] == [1] and gs["CoordAxisSign"] == [1]
    assert gs["UnitScaleFactor"] == [1.0]
    defs = first["Definitions"]
    assert defs.child("Count").props[0] == 1 + 3 + 2
    types = {o.props[0]: o for o in defs.all("ObjectType")}
    assert types["GlobalSettings"].child("Count").props[0] == 1
    assert types["Model"].child("Count").props[0] == 3
    assert types["Geometry"].child("Count").props[0] == 2
    model_tmpl = fmt_fbx._props(types["Model"].child("PropertyTemplate"))
    assert types["Model"].child("PropertyTemplate").props[0] == "FbxNode"
    assert types["Geometry"].child("PropertyTemplate").props[0] == "FbxMesh"
    for key in ("Lcl Translation", "Lcl Rotation", "Lcl Scaling", "RotationOrder", "InheritType",
                "GeometricTranslation", "PreRotation"):
        assert key in model_tmpl, key
    objs = first["Objects"]
    models = objs.all("Model")
    geoms = objs.all("Geometry")
    assert [m.props[1] for m in models] == ["Cube\x00\x01Model", "Ball\x00\x01Model", "Group\x00\x01Model"]
    assert [g.props[1] for g in geoms] == ["Cube\x00\x01Geometry", "Ball\x00\x01Geometry"]
    ids = [m.props[0] for m in models] + [g.props[0] for g in geoms]
    assert len(set(ids)) == len(ids) and all(isinstance(i, int) and 0 < i < 2 ** 63 for i in ids)
    for g in geoms:
        pvi = g.child("PolygonVertexIndex").props[0]
        assert pvi.dtype == np.int32 and pvi[-1] < 0
        layer = g.child("LayerElementNormal")
        assert layer.child("MappingInformationType").props[0] == "ByPolygonVertex"
        assert layer.child("ReferenceInformationType").props[0] == "Direct"
        normals = layer.child("Normals").props[0]
        assert normals.size == pvi.size * 3
        assert np.allclose(np.linalg.norm(normals.reshape(-1, 3), axis=1), 1.0)
        assert g.child("Layer").child("LayerElement").child("Type").props[0] == "LayerElementNormal"
    links = [(c.props[0], c.props[1], c.props[2]) for c in first["Connections"].all("C")]
    assert ("OO", geoms[0].props[0], models[0].props[0]) in links
    assert ("OO", geoms[1].props[0], models[1].props[0]) in links
    assert all(("OO", m.props[0], 0) in links for m in models)
    vertex_record = next(rec for rec in records if rec["name"] == "Vertices"
                         and data[rec["props_at"]] == ord("d"))
    count, encoding, size = struct.unpack_from("<3I", data, vertex_record["props_at"] + 1)
    assert count == 24 and encoding == 1
    raw = zlib.decompress(data[vertex_record["props_at"] + 13:vertex_record["props_at"] + 13 + size])
    assert np.allclose(np.frombuffer(raw, "<f8").reshape(-1, 3), Mesh.cube(200.0).points)


def test_uncompressed_option():
    doc = Document([Node("Ball", _sphere())])
    small_path = _tmp("packed.fbx")
    fmt_fbx.save(small_path, doc, {})
    back, path = _round(doc, "plain.fbx", {"compress": False})
    assert os.path.getsize(path) > os.path.getsize(small_path)
    records, _ = _walk(_read(path))
    data = _read(path)
    for rec in records:
        code = chr(data[rec["props_at"]]) if rec["count"] else ""
        if code in "dfil" and code:
            assert struct.unpack_from("<3I", data, rec["props_at"] + 1)[1] == 0
    assert back.nodes[0].mesh.polygons == doc.nodes[0].mesh.polygons


ASCII_7400 = NL.join([
    "; FBX 7.4.0 project file",
    "; sample written by the Quartz test",
    "FBXHeaderExtension:  {",
    "\tFBXHeaderVersion: 1003",
    "\tFBXVersion: 7400",
    "\tCreator: \"test\"",
    "}",
    "GlobalSettings:  {",
    "\tVersion: 1000",
    "\tProperties70:  {",
    "\t\tP: \"UpAxis\", \"int\", \"Integer\", \"\",2",
    "\t\tP: \"UpAxisSign\", \"int\", \"Integer\", \"\",1",
    "\t\tP: \"FrontAxis\", \"int\", \"Integer\", \"\",1",
    "\t\tP: \"FrontAxisSign\", \"int\", \"Integer\", \"\",-1",
    "\t\tP: \"CoordAxis\", \"int\", \"Integer\", \"\",0",
    "\t\tP: \"CoordAxisSign\", \"int\", \"Integer\", \"\",1",
    "\t\tP: \"UnitScaleFactor\", \"double\", \"Number\", \"\",100",
    "\t}",
    "}",
    "Definitions:  {",
    "\tVersion: 100",
    "\tCount: 5",
    "\tObjectType: \"Model\" {",
    "\t\tCount: 4",
    "\t\tPropertyTemplate: \"FbxNode\" {",
    "\t\t\tProperties70:  {",
    "\t\t\t\tP: \"Lcl Scaling\", \"Lcl Scaling\", \"\", \"A\",1,1,1",
    "\t\t\t}",
    "\t\t}",
    "\t}",
    "}",
    "Objects:  {",
    "\tGeometry: 100, \"Geometry::Box\", \"Mesh\" {",
    "\t\tVertices: *15 {",
    "\t\t\ta: 0,0,0,1,0,0,1,1,0,0.5,1.5,0,0,1,0",
    "\t\t} ",
    "\t\tPolygonVertexIndex: *5 {",
    "\t\t\ta: 0,1,2,3,-5",
    "\t\t} ",
    "\t\tGeometryVersion: 124",
    "\t\tLayerElementNormal: 0 {",
    "\t\t\tMappingInformationType: \"ByPolygonVertex\"",
    "\t\t\tNormals: *15 {",
    "\t\t\t\ta: 0,0,1,0,0,1,0,0,1,0,0,1,0,0,1",
    "\t\t\t} ",
    "\t\t}",
    "\t}",
    "\tGeometry: 101, \"Geometry::Tri\", \"Mesh\" {",
    "\t\tVertices: *9 {",
    "\t\t\ta: 0,0,0,1,0,0,0,1,0",
    "\t\t} ",
    "\t\tPolygonVertexIndex: *3 {",
    "\t\t\ta: 0,1,-3",
    "\t\t} ",
    "\t}",
    "\tModel: 200, \"Model::Box\", \"Mesh\" {",
    "\t\tVersion: 232",
    "\t\tProperties70:  {",
    "\t\t\tP: \"Lcl Translation\", \"Lcl Translation\", \"\", \"A\",1,2,3",
    "\t\t\tP: \"Lcl Rotation\", \"Lcl Rotation\", \"\", \"A\",0,0,90",
    "\t\t}",
    "\t\tShading: T",
    "\t\tCulling: \"CullingOff\"",
    "\t}",
    "\tModel: 201, \"Model::Group\", \"Null\" {",
    "\t\tProperties70:  {",
    "\t\t\tP: \"Lcl Translation\", \"Lcl Translation\", \"\", \"A\",0,0,1",
    "\t\t}",
    "\t}",
    "\tModel: 202, \"Model::Inner\", \"Mesh\" {",
    "\t\tProperties70:  {",
    "\t\t\tP: \"Lcl Scaling\", \"Lcl Scaling\", \"\", \"A\",2,2,2",
    "\t\t}",
    "\t}",
    "\tModel: 203, \"Model::Cam\", \"Camera\" {",
    "\t\tProperties70:  {",
    "\t\t\tP: \"Lcl Translation\", \"Lcl Translation\", \"\", \"A\",5,0,0",
    "\t\t}",
    "\t}",
    "\tNodeAttribute: 300, \"NodeAttribute::Cam\", \"Camera\" {",
    "\t\tTypeFlags: \"Camera\"",
    "\t}",
    "\tMaterial: 400, \"Material::Red\", \"\" {",
    "\t\tShadingModel: \"phong\"",
    "\t}",
    "\tModel: 204, \"Model::UnderCamera\", \"Mesh\" {",
    "\t}",
    "\tDeformer: 500, \"Deformer::Skin\", \"Skin\" {",
    "\t}",
    "\tAnimationStack: 600, \"AnimStack::Take 001\", \"\" {",
    "\t}",
    "}",
    "Connections:  {",
    "\t;Model::Box, Model::RootNode",
    "\tC: \"OO\",200,0",
    "\tC: \"OO\",100,200",
    "\tC: \"OO\",400,200",
    "\tC: \"OO\",201,0",
    "\tC: \"OO\",202,201",
    "\tC: \"OO\",101,202",
    "\tC: \"OO\",203,0",
    "\tC: \"OO\",300,203",
    "\tC: \"OO\",204,203",
    "\tC: \"OO\",101,204",
    "\tC: \"OP\",600,200, \"Lcl Translation\"",
    "}",
    "Takes:  {",
    "\tCurrent: \"\"",
    "}",
    ""])


def _zup_to_quartz(points) -> np.ndarray:
    p = np.asarray(points, float).reshape(-1, 3)
    return 100.0 * np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1)


def test_ascii_7400_zup_meters_hierarchy_and_ignored_objects():
    doc = fmt_fbx.load(_write_text("ascii7400.fbx", ASCII_7400))
    assert [n.name for n in doc.nodes] == ["Box", "Group", "Inner", "UnderCamera"]
    assert [n.parent for n in doc.nodes] == [None, None, 1, None]
    box = doc.nodes[0]
    assert len(box.mesh.polygons) == 1 and len(box.mesh.polygons[0]) == 5
    local = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0.5, 1.5, 0], [0, 1, 0]], float)
    world = local @ rotation_matrix((0, 0, 90)).T + np.array([1.0, 2.0, 3.0])
    assert np.allclose(baked_mesh(box).points, _zup_to_quartz(world), atol=1e-9)
    assert np.allclose(box.matrix[:3, 3], [100.0, 300.0, -200.0])
    normal = box.mesh.polygon_normals()[0] @ box.matrix[:3, :3].T
    assert np.allclose(normal / np.linalg.norm(normal), [0.0, 1.0, 0.0], atol=1e-9)
    tri = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float)
    inner = doc.nodes[2]
    assert np.allclose(baked_mesh(inner).points, _zup_to_quartz(tri * 2.0 + np.array([0, 0, 1.0])), atol=1e-9)
    under = doc.nodes[3]
    assert np.allclose(baked_mesh(under).points, _zup_to_quartz(tri + np.array([5.0, 0, 0])), atol=1e-9)
    assert np.linalg.det(box.matrix[:3, :3]) > 0
    assert doc.meta["source"] == "FBX 7400"


def _rx(a):
    return rotation_matrix((a, 0, 0))


def _ry(a):
    return rotation_matrix((0, a, 0))


def _rz(a):
    return rotation_matrix((0, 0, a))


def _h(lin=None, t=None) -> np.ndarray:
    m = np.eye(4)
    if lin is not None:
        m[:3, :3] = lin
    if t is not None:
        m[:3, 3] = t
    return m


def test_ascii_pivots_prerotation_order_and_geometric():
    props = [
        ("Lcl Translation", "5,0,0"), ("Lcl Rotation", "10,20,30"), ("Lcl Scaling", "2,1,0.5"),
        ("PreRotation", "0,0,90"), ("PostRotation", "15,0,0"), ("RotationPivot", "1,2,0"),
        ("ScalingPivot", "0,1,0"), ("GeometricTranslation", "0,0,3"), ("GeometricRotation", "0,45,0"),
        ("GeometricScaling", "1,2,1")]
    lines = ["FBXHeaderExtension: {", "FBXVersion: 7300", "}", "Objects: {",
             "Geometry: 7, \"Geometry::G\", \"Mesh\" {",
             "Vertices: *12 { a: 0,0,0,1,0,0,1,1,0,0,1,1 }",
             "PolygonVertexIndex: *4 { a: 0,1,2,-4 }", "}",
             "Model: 8, \"Model::Pivoted\", \"Mesh\" {", "Properties70: {"]
    lines += [f"P: \"{k}\", \"Vector3D\", \"Vector\", \"\",{v}" for k, v in props]
    lines += ["P: \"RotationOrder\", \"enum\", \"\", \"\",5", "}", "}", "}",
              "Connections: {", "C: \"OO\",8,0", "C: \"OO\",7,8", "}"]
    doc = fmt_fbx.load(_write_text("pivots.fbx", NL.join(lines)))
    node = doc.nodes[0]
    rp = np.array([1.0, 2.0, 0.0])
    sp = np.array([0.0, 1.0, 0.0])
    r = _rx(10) @ _ry(20) @ _rz(30)
    expected = (_h(None, (5, 0, 0)) @ _h(None, rp) @ _h(_rz(90)) @ _h(r) @ _h(_rx(15).T) @ _h(None, -rp)
                @ _h(None, sp) @ _h(np.diag([2.0, 1.0, 0.5])) @ _h(None, -sp))
    geo = _h(None, (0, 0, 3)) @ _h(_ry(45)) @ _h(np.diag([1.0, 2.0, 1.0]))
    local = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 1]], float)
    full = expected @ geo
    want = local @ full[:3, :3].T + full[:3, 3]
    assert np.allclose(baked_mesh(node).points, want, atol=1e-9)
    assert np.allclose(node.matrix, expected, atol=1e-9)
    assert doc.meta["source"] == "FBX 7300"


ASCII_6100 = NL.join([
    "; FBX 6.1.0 project file",
    "; ----------------------------------------------------",
    "",
    "FBXHeaderExtension:  {",
    "\tFBXHeaderVersion: 1003",
    "\tFBXVersion: 6100",
    "\tCreator: \"FBX SDK/FBX Plugins build 20070228\"",
    "}",
    "CreationTime: \"2008-01-01 10:00:00:000\"",
    "Definitions:  {",
    "\tVersion: 100",
    "\tCount: 3",
    "\tObjectType: \"Model\" {",
    "\t\tCount: 3",
    "\t}",
    "}",
    "Objects:  {",
    "\tModel: \"Model::Base\", \"Mesh\" {",
    "\t\tVersion: 232",
    "\t\tProperties60:  {",
    "\t\t\tProperty: \"QuaternionInterpolate\", \"bool\", \"\",0",
    "\t\t\tProperty: \"Lcl Translation\", \"Lcl Translation\", \"A+\",10.000000,0.000000,0.000000",
    "\t\t\tProperty: \"Lcl Rotation\", \"Lcl Rotation\", \"A+\",0.000000,90.000000,0.000000",
    "\t\t\tProperty: \"Lcl Scaling\", \"Lcl Scaling\", \"A+\",1.000000,1.000000,1.000000",
    "\t\t}",
    "\t\tMultiLayer: 0",
    "\t\tShading: Y",
    "\t\tCulling: \"CullingOff\"",
    "\t\tVertices: 0.000000,0.000000,0.000000,4.000000,0.000000,0.000000,",
    "4.000000,4.000000,0.000000,2.000000,6.000000,0.000000,0.000000,4.000000,0.000000",
    "\t\tPolygonVertexIndex: 0,1,2,3,-5",
    "\t\tGeometryVersion: 124",
    "\t\tLayerElementNormal: 0 {",
    "\t\t\tVersion: 101",
    "\t\t\tName: \"\"",
    "\t\t\tMappingInformationType: \"ByPolygonVertex\"",
    "\t\t\tReferenceInformationType: \"Direct\"",
    "\t\t\tNormals: 0,0,1,0,0,1,0,0,1,0,0,1,0,0,1",
    "\t\t}",
    "\t}",
    "\tModel: \"Model::Child\", \"Null\" {",
    "\t\tProperties60:  {",
    "\t\t\tProperty: \"Lcl Translation\", \"Lcl Translation\", \"A+\",0,5,0",
    "\t\t}",
    "\t}",
    "\tModel: \"Model::Producer Perspective\", \"Camera\" {",
    "\t\tProperties60:  {",
    "\t\t\tProperty: \"Lcl Translation\", \"Lcl Translation\", \"A+\",0,71.3,287.5",
    "\t\t}",
    "\t}",
    "\tGlobalSettings:  {",
    "\t\tVersion: 1000",
    "\t\tProperties60:  {",
    "\t\t\tProperty: \"UpAxis\", \"int\", \"\",1",
    "\t\t\tProperty: \"UpAxisSign\", \"int\", \"\",1",
    "\t\t\tProperty: \"FrontAxis\", \"int\", \"\",2",
    "\t\t\tProperty: \"FrontAxisSign\", \"int\", \"\",1",
    "\t\t\tProperty: \"CoordAxis\", \"int\", \"\",0",
    "\t\t\tProperty: \"CoordAxisSign\", \"int\", \"\",1",
    "\t\t\tProperty: \"UnitScaleFactor\", \"double\", \"\",1",
    "\t\t}",
    "\t}",
    "}",
    "Connections:  {",
    "\tConnect: \"OO\", \"Model::Base\", \"Model::Scene\"",
    "\tConnect: \"OO\", \"Model::Child\", \"Model::Base\"",
    "\tConnect: \"OO\", \"Model::Producer Perspective\", \"Model::Scene\"",
    "}",
    ""])


def test_ascii_6100():
    doc = fmt_fbx.load(_write_text("ascii6100.fbx", ASCII_6100))
    assert [n.name for n in doc.nodes] == ["Base", "Child"]
    assert doc.nodes[1].parent == 0 and doc.nodes[1].mesh is None
    base = doc.nodes[0]
    expected = _h(_ry(90), (10, 0, 0))
    assert np.allclose(base.matrix, expected, atol=1e-9)
    assert base.mesh.polygons == [(0, 1, 2, 3, 4)]
    assert np.allclose(doc.nodes[1].matrix, expected @ _h(None, (0, 5, 0)), atol=1e-9)
    assert doc.meta["source"] == "FBX 6100"


def _p_str(text: str, code: str = "S") -> bytes:
    raw = text.encode("utf-8")
    return code.encode() + struct.pack("<I", len(raw)) + raw


def _p_num(code: str, value) -> bytes:
    fmt = {"I": "<i", "L": "<q", "D": "<d", "F": "<f", "Y": "<h"}[code]
    return code.encode() + struct.pack(fmt, value)


def _p_array(code: str, values, compress: bool) -> bytes:
    dtype = {"d": "<f8", "i": "<i4", "l": "<i8", "f": "<f4"}[code]
    raw = np.asarray(values, dtype=dtype).tobytes()
    count = len(values)
    if compress:
        packed = zlib.compress(raw)
        return code.encode() + struct.pack("<3I", count, 1, len(packed)) + packed
    return code.encode() + struct.pack("<3I", count, 0, len(raw)) + raw


def _binary_64(records, version: int = 7500) -> bytes:
    out = bytearray(MAGIC + struct.pack("<I", version))

    def write(rec) -> None:
        name, props, children = rec
        start = len(out)
        out.extend(bytes(24))
        out.append(len(name))
        out.extend(name.encode("ascii"))
        before = len(out)
        for p in props:
            out.extend(p)
        plen = len(out) - before
        for child in children:
            write(child)
        if children or not props:
            out.extend(bytes(25))
        struct.pack_into("<3Q", out, start, len(out), len(props), plen)

    for rec in records:
        write(rec)
    out.extend(bytes(25))
    out.extend(FOOT_ID + bytes(4))
    pad = (16 - len(out) % 16) or 16
    out.extend(bytes(pad))
    out.extend(struct.pack("<I", version) + bytes(120) + FOOT_MAGIC)
    return bytes(out)


def _prop70(name: str, kind: str, *values) -> tuple:
    return ("P", [_p_str(name), _p_str(kind), _p_str(""), _p_str("")] + list(values), [])


def test_binary_7500_with_64bit_records():
    pentagon = [0, 0, 0, 2, 0, 0, 2, 2, 0, 1, 3, 0, 0, 2, 0]
    records = [
        ("FBXHeaderExtension", [], [("FBXVersion", [_p_num("I", 7500)], [])]),
        ("GlobalSettings", [], [("Properties70", [], [
            _prop70("UpAxis", "int", _p_num("I", 1)),
            _prop70("UnitScaleFactor", "double", _p_num("D", 2.54))])]),
        ("Objects", [], [
            ("Geometry", [_p_num("L", 11), _p_str("Five\x00\x01Geometry"), _p_str("Mesh")], [
                ("Vertices", [_p_array("d", pentagon, False)], []),
                ("PolygonVertexIndex", [_p_array("i", [0, 1, 2, 3, ~4], True)], [])]),
            ("Model", [_p_num("L", 12), _p_str("Five\x00\x01Model"), _p_str("Mesh")], [
                ("Version", [_p_num("I", 232)], []),
                ("Properties70", [], [
                    _prop70("Lcl Translation", "Lcl Translation", _p_num("D", 1.0), _p_num("D", 0.0),
                            _p_num("D", 0.0)),
                    _prop70("Lcl Scaling", "Lcl Scaling", _p_num("D", 1.0), _p_num("D", 1.0), _p_num("D", 1.0))]),
                ("Shading", [b"C" + bytes((1,))], []),
                ("Flags", [_p_num("Y", 3), _p_num("F", 0.5)], [])])]),
        ("Connections", [], [
            ("C", [_p_str("OO"), _p_num("L", 11), _p_num("L", 12)], []),
            ("C", [_p_str("OO"), _p_num("L", 12), _p_num("L", 0)], [])]),
    ]
    data = _binary_64(records)
    _walk(data, wide=True)
    doc = fmt_fbx.load(_write_bytes("b7500.fbx", data))
    assert doc.meta["source"] == "FBX 7500"
    assert len(doc.nodes) == 1 and doc.nodes[0].name == "Five"
    node = doc.nodes[0]
    assert node.mesh.polygons == [(0, 1, 2, 3, 4)]
    assert np.allclose(node.mesh.points, np.array(pentagon, float).reshape(-1, 3) * 2.54)
    assert np.allclose(node.matrix[:3, 3], [2.54, 0, 0])
    _, top = fmt_fbx.read_tree(data)
    flags = _find(_find(top, "Objects")[0].children, "Model")[0].child("Flags").props
    assert flags[0] == 3 and abs(flags[1] - 0.5) < 1e-9


def test_writer_supports_64bit_records():
    tree = fmt_fbx.build_tree(Document([Node("Cube", Mesh.cube(20.0))]))
    data = fmt_fbx.encode_binary(tree, 7500)
    _walk(data, wide=True)
    doc = fmt_fbx.load(_write_bytes("w7500.fbx", data))
    assert len(doc.nodes[0].mesh.points) == 8


def _expect_error(path: str) -> str:
    try:
        fmt_fbx.load(path)
    except FileFormatError as exc:
        assert os.path.basename(path) in str(exc), str(exc)
        return str(exc)
    raise AssertionError(f"{os.path.basename(path)} loaded without error")


def test_truncated_files():
    path = _tmp("full.fbx")
    fmt_fbx.save(path, Document([Node("Ball", _sphere()), Node("Cube", Mesh.cube(100.0))]), {})
    data = _read(path)
    records, q = _walk(data)
    connections = next(r for r in records if r["name"] == "Connections")
    vertices = next(r for r in records if r["name"] == "Vertices")
    cuts = [0, 10, 23, 27, 30, len(data) // 4, len(data) // 2, vertices["props_at"] + 20,
            connections["start"] + 5, q - 13, q - 1]
    for k, cut in enumerate(cuts):
        _expect_error(_write_bytes(f"cut{k}.fbx", data[:cut]))
    for k, cut in enumerate((len(ASCII_7400) // 2, len(ASCII_7400) - 40)):
        _expect_error(_write_text(f"cut_ascii{k}.fbx", ASCII_7400[:cut]))


def test_corrupt_files():
    rng = np.random.default_rng(5)
    _expect_error(_write_bytes("random.fbx", rng.integers(0, 256, 4000, dtype=np.uint8).tobytes()))
    _expect_error(_write_bytes("empty.fbx", b""))
    _expect_error(_write_text("words.fbx", "hello world, this is not a scene"))
    path = _tmp("good.fbx")
    fmt_fbx.save(path, Document([Node("Cube", Mesh.cube(200.0))]), {})
    data = bytearray(_read(path))
    bad = bytearray(data)
    bad[23:27] = struct.pack("<I", 123)
    _expect_error(_write_bytes("version.fbx", bytes(bad)))
    bad = bytearray(data)
    bad[27:31] = struct.pack("<I", 0xFFFFFFF0)
    _expect_error(_write_bytes("offset.fbx", bytes(bad)))
    bad = bytearray(data)
    bad[27:31] = struct.pack("<I", 40)
    _expect_error(_write_bytes("offset_small.fbx", bytes(bad)))
    records, _ = _walk(bytes(data))
    vertices = next(r for r in records if r["name"] == "Vertices")
    at = vertices["props_at"]
    bad = bytearray(data)
    bad[at + 13:at + 15] = b"\x00\x00"
    message = _expect_error(_write_bytes("zlib.fbx", bytes(bad)))
    assert "compressed" in message
    bad = bytearray(data)
    bad[at + 5:at + 9] = struct.pack("<I", 7)
    _expect_error(_write_bytes("encoding.fbx", bytes(bad)))
    bad = bytearray(data)
    bad[at] = ord("Q")
    _expect_error(_write_bytes("typecode.fbx", bytes(bad)))
    text = ASCII_7400.replace("a: 0,1,2,3,-5", "a: 0,1,2,30,-5")
    assert "out of range" in _expect_error(_write_text("index.fbx", text))
    text = ASCII_7400.replace("a: 0,0,0,1,0,0,1,1,0,0.5,1.5,0,0,1,0", "a: 0,0,0,1,0,0,1,1,0,0.5,1.5,0,0,1")
    _expect_error(_write_text("vertices.fbx", text))
    _expect_error(_write_text("brace.fbx", ASCII_7400 + "}" + NL))
    cyclic = ASCII_7400.replace("C: \"OO\",201,0", "C: \"OO\",201,202")
    assert "cycle" in _expect_error(_write_text("cycle.fbx", cyclic))


def test_large_mesh_timing():
    nx, nz = 317, 316
    xs, zs = np.meshgrid(np.arange(nx + 1, dtype=float), np.arange(nz + 1, dtype=float))
    pts = np.stack([xs.ravel(), np.zeros(xs.size), zs.ravel()], axis=1) * 2.0
    row = nx + 1
    polys = [(j * row + i, (j + 1) * row + i, (j + 1) * row + i + 1, j * row + i + 1)
             for j in range(nz) for i in range(nx)]
    assert len(polys) >= 100000
    mesh = Mesh(pts, polys)
    path = _tmp("large.fbx")
    start = time.perf_counter()
    fmt_fbx.save(path, Document([Node("Grid", mesh)]), {})
    saved = time.perf_counter() - start
    start = time.perf_counter()
    doc = fmt_fbx.load(path)
    loaded = time.perf_counter() - start
    assert len(doc.nodes[0].mesh.polygons) == len(polys)
    assert doc.nodes[0].mesh.polygons[-1] == polys[-1]
    assert np.allclose(doc.nodes[0].mesh.points, pts)
    assert saved < 10.0 and loaded < 10.0, (saved, loaded)


def test_api_scene_round_trip():
    QApplication.instance() or QApplication([sys.argv[0]])
    scene = scene_mod.reset_scene()
    cube = scene.objects[0]
    cube.position = np.array([10.0, 20.0, 30.0])
    cube.rotation = np.array([0.0, 30.0, 0.0])
    path = _tmp("scene.fbx")
    export_file(scene, path)
    before = cube.world_points().copy()
    created = import_file(scene, path)
    assert len(created) == 1 and len(scene.objects) == 2
    _assert_points_match(created[0].world_points(), before, 1e-6)


BL_IMPORT = NL.join([
    "import json",
    "import sys",
    "import bpy",
    "args = sys.argv[sys.argv.index('--') + 1:]",
    "for ob in list(bpy.data.objects):",
    "    bpy.data.objects.remove(ob, do_unlink=True)",
    "bpy.ops.import_scene.fbx(filepath=args[0])",
    "out = []",
    "for ob in bpy.context.scene.objects:",
    "    item = {'name': ob.name, 'type': ob.type, 'parent': ob.parent.name if ob.parent else None,",
    "            'matrix': [list(r) for r in ob.matrix_world]}",
    "    if ob.type == 'MESH':",
    "        mw = ob.matrix_world",
    "        pts = [list(mw @ v.co) for v in ob.data.vertices]",
    "        item['verts'] = len(pts)",
    "        item['polys'] = len(ob.data.polygons)",
    "        item['sizes'] = sorted(len(p.vertices) for p in ob.data.polygons)",
    "        item['points'] = pts",
    "        vol = 0.0",
    "        for p in ob.data.polygons:",
    "            vs = [pts[i] for i in p.vertices]",
    "            for k in range(1, len(vs) - 1):",
    "                a, b, c = vs[0], vs[k], vs[k + 1]",
    "                vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])",
    "                        + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0",
    "        item['volume'] = vol",
    "        item['det'] = mw.determinant()",
    "    out.append(item)",
    "with open(args[1], 'w') as handle:",
    "    json.dump(out, handle)",
    ""])

BL_EXPORT = NL.join([
    "import json",
    "import sys",
    "import bpy",
    "args = sys.argv[sys.argv.index('--') + 1:]",
    "for ob in list(bpy.data.objects):",
    "    bpy.data.objects.remove(ob, do_unlink=True)",
    "bpy.ops.mesh.primitive_cube_add(size=2.0, location=(3.0, 0.0, 0.0))",
    "bpy.context.active_object.name = 'BlCube'",
    "bpy.ops.mesh.primitive_monkey_add(size=2.0, location=(0.0, 4.0, 1.0))",
    "bpy.context.active_object.name = 'BlMonkey'",
    "bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-2.0, 1.0, 0.5))",
    "parent = bpy.context.active_object",
    "parent.name = 'BlParent'",
    "parent.rotation_euler = (0.3, 0.2, 0.9)",
    "parent.scale = (1.5, 0.5, 2.0)",
    "bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0.0, 0.0, 0.0))",
    "child = bpy.context.active_object",
    "child.name = 'BlChild'",
    "child.parent = parent",
    "child.location = (1.0, 0.5, -0.5)",
    "child.rotation_euler = (0.5, -0.4, 0.2)",
    "child.scale = (0.8, 1.2, 1.0)",
    "bpy.context.view_layer.update()",
    "bpy.ops.export_scene.fbx(filepath=args[0])",
    "out = []",
    "for ob in bpy.context.scene.objects:",
    "    mw = ob.matrix_world",
    "    pts = [list(mw @ v.co) for v in ob.data.vertices]",
    "    out.append({'name': ob.name, 'verts': len(pts), 'polys': len(ob.data.polygons), 'points': pts,",
    "                'parent': ob.parent.name if ob.parent else None})",
    "with open(args[1], 'w') as handle:",
    "    json.dump(out, handle)",
    ""])


def _run_blender(script_text: str, script_name: str, *args: str) -> None:
    if not os.path.isfile(BLENDER):
        raise Skip("Blender 5.2 not installed")
    script = _write_text(script_name, script_text)
    result = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                             "--python", script, "--", *args],
                            cwd=TMP, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        tail = (result.stdout + result.stderr)[-1500:]
        raise AssertionError(f"Blender failed ({result.returncode}): {tail}")


def _quartz_to_blender(points) -> np.ndarray:
    p = np.asarray(points, float).reshape(-1, 3) / 100.0
    return np.stack([p[:, 0], -p[:, 2], p[:, 1]], axis=1)


def test_blender_imports_quartz_export():
    if not os.path.isfile(BLENDER):
        raise Skip("Blender 5.2 not installed")
    moved = compose((150.0, 50.0, -80.0), (30.0, 45.0, 60.0), (1.0, 2.0, 0.5))
    nodes = [Node("Cube", Mesh.cube(200.0)),
             Node("Sphere", _sphere(), compose((0.0, 0.0, 300.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))),
             Node("Moved", Mesh.cube(100.0), moved),
             Node("Mirrored", _l_prism(), compose((-200.0, 10.0, 0.0), (0.0, 30.0, 0.0), (-1.0, 1.0, 1.0))),
             Node("Child", Mesh.cube(40.0), moved @ compose((100.0, 0.0, 0.0), (0.0, 0.0, 20.0), (1, 1, 1)), 2)]
    path = _tmp("to_blender.fbx")
    fmt_fbx.save(path, Document(nodes), {})
    out = _tmp("to_blender.json")
    _run_blender(BL_IMPORT, "bl_import.py", path, out)
    with open(out, "r", encoding="utf-8") as handle:
        result = {item["name"]: item for item in json.load(handle)}
    assert set(result) == {n.name for n in nodes}, sorted(result)
    for node in nodes:
        item = result[node.name]
        baked = baked_mesh(node)
        assert item["type"] == "MESH"
        assert item["verts"] == len(baked.points) and item["polys"] == len(baked.polygons), node.name
        assert item["sizes"] == sorted(len(p) for p in baked.polygons), node.name
        _assert_points_match(item["points"], _quartz_to_blender(baked.points), 1e-4)
        assert item["volume"] * (1.0 if item["det"] > 0 else -1.0) > 0, node.name
    assert result["Child"]["parent"] == "Moved"
    assert result["Mirrored"]["det"] < 0 and result["Moved"]["det"] > 0
    assert 6 in result["Mirrored"]["sizes"]


def test_quartz_imports_blender_export():
    if not os.path.isfile(BLENDER):
        raise Skip("Blender 5.2 not installed")
    path = _tmp("from_blender.fbx")
    out = _tmp("from_blender.json")
    _run_blender(BL_EXPORT, "bl_export.py", path, out)
    with open(out, "r", encoding="utf-8") as handle:
        ref = {item["name"]: item for item in json.load(handle)}
    doc = fmt_fbx.load(path)
    names = [n.name for n in doc.nodes]
    assert set(names) == {"BlCube", "BlMonkey", "BlParent", "BlChild"}, names
    for node in doc.nodes:
        item = ref[node.name]
        baked = baked_mesh(node)
        assert len(baked.points) == item["verts"] and len(baked.polygons) == item["polys"], node.name
        pts = np.asarray(item["points"], float) * 100.0
        expected = np.stack([pts[:, 0], pts[:, 2], -pts[:, 1]], axis=1)
        _assert_points_match(baked.points, expected, 1e-3)
        lo, hi = baked.points.min(axis=0), baked.points.max(axis=0)
        assert np.allclose(lo, expected.min(axis=0), atol=1e-3) and np.allclose(hi, expected.max(axis=0), atol=1e-3)
    by_name = {n.name: n for n in doc.nodes}
    assert doc.nodes[by_name["BlChild"].parent].name == "BlParent"
    assert len(by_name["BlMonkey"].mesh.points) == 507 and len(by_name["BlMonkey"].mesh.polygons) == 500
    for name in ("BlCube", "BlParent", "BlChild"):
        assert _signed_volume(baked_mesh(by_name[name])) > 0, name
    cube = baked_mesh(by_name["BlCube"]).points
    assert np.allclose(cube.max(axis=0) - cube.min(axis=0), [200.0, 200.0, 200.0], atol=1e-3)


def _run_as_script() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    tests.sort(key=lambda item: item[1].__code__.co_firstlineno)
    failures = 0
    skipped = 0
    for name, fn in tests:
        try:
            fn()
        except Skip as exc:
            skipped += 1
            print(f"skip {name}: {exc}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}".encode("ascii", "replace").decode())
        else:
            print(f"ok   {name}")
    print(f"{len(tests) - failures - skipped} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
