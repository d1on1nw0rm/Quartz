from __future__ import annotations

import base64
import json
import math
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
from quartz_studio.fileio import (Document, FileFormatError, Node, baked_mesh, compose, export_file,
                                  import_file, registry, triangulate)
from quartz_studio.scene import Mesh

TMP = tempfile.mkdtemp(prefix="qz_fileio_gltf_")
COUNTER = [0]
FLOAT, UBYTE, USHORT, UINT, SHORT, BYTE = 5126, 5121, 5123, 5125, 5122, 5120


def tmp_path(name: str) -> str:
    COUNTER[0] += 1
    folder = os.path.join(TMP, f"case{COUNTER[0]}")
    os.makedirs(folder)
    return os.path.join(folder, name)


def split_glb(data: bytes):
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and version == 2, "GLB header"
    assert total == len(data), f"GLB total length {total} != file size {len(data)}"
    assert total % 4 == 0
    pos = 12
    chunks = []
    while pos < total:
        size, kind = struct.unpack_from("<II", data, pos)
        assert size % 4 == 0, "chunk length not a multiple of 4"
        assert pos + 8 + size <= total, "chunk past the end"
        chunks.append((kind, data[pos + 8:pos + 8 + size]))
        pos += 8 + size
    assert pos == total
    return chunks


def glb_bytes(gltf: dict, blob: bytes = b"") -> bytes:
    text = json.dumps(gltf).encode("utf-8")
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text
    if blob:
        padded = blob + b"\x00" * (-len(blob) % 4)
        body += struct.pack("<II", len(padded), 0x004E4942) + padded
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def _reject_constant(name):
    raise AssertionError(f"JSON contains {name}")


def decode_accessor(gltf: dict, binary: bytes, index: int) -> np.ndarray:
    a = gltf["accessors"][index]
    view = gltf["bufferViews"][a["bufferView"]]
    code = {FLOAT: "<f4", UBYTE: "u1", USHORT: "<u2", UINT: "<u4"}[a["componentType"]]
    parts = {"SCALAR": 1, "VEC3": 3}[a["type"]]
    start = view["byteOffset"] + a.get("byteOffset", 0)
    return np.frombuffer(binary, dtype=code, count=a["count"] * parts, offset=start).reshape(a["count"], parts)


def validate(path: str) -> dict:
    data = open(path, "rb").read()
    is_glb = path.lower().endswith(".glb")
    if is_glb:
        chunks = split_glb(data)
        assert 1 <= len(chunks) <= 2
        assert chunks[0][0] == 0x4E4F534A, "first chunk must be JSON"
        raw = chunks[0][1]
        stripped = raw.rstrip(b" ")
        assert len(raw) - len(stripped) < 4, "JSON chunk padded by more than 3 bytes"
        assert stripped.endswith(b"}")
        gltf = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        binary = b""
        if len(chunks) == 2:
            assert chunks[1][0] == 0x004E4942, "second chunk must be BIN"
            binary = chunks[1][1]
            declared = gltf["buffers"][0]["byteLength"]
            assert declared <= len(binary) and len(binary) - declared < 4, "BIN chunk size does not match byteLength"
            assert set(binary[declared:]) <= {0}, "BIN padding must be zeros"
            assert "uri" not in gltf["buffers"][0], "GLB buffer must not have a uri"
        else:
            assert "buffers" not in gltf
    else:
        gltf = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
        binary = b""
        if "buffers" in gltf:
            uri = gltf["buffers"][0]["uri"]
            prefix = "data:application/octet-stream;base64,"
            assert uri.startswith(prefix), "buffer must be an embedded base64 data URI"
            binary = base64.b64decode(uri[len(prefix):], validate=True)
    assert gltf["asset"]["version"] == "2.0"
    assert isinstance(gltf["asset"].get("generator"), str) and gltf["asset"]["generator"]
    assert gltf.get("scene") == 0 and len(gltf["scenes"]) == 1
    nodes = gltf.get("nodes", [])
    meshes = gltf.get("meshes", [])
    accessors = gltf.get("accessors", [])
    views = gltf.get("bufferViews", [])
    for key in ("nodes", "meshes", "accessors", "bufferViews", "buffers", "materials"):
        if key in gltf:
            assert len(gltf[key]) >= 1, f"{key} is an empty list"
    if "buffers" in gltf:
        assert len(gltf["buffers"]) == 1
        length = gltf["buffers"][0]["byteLength"]
        assert length == len(binary) or (is_glb and length <= len(binary)), "buffer byteLength"
        assert length % 4 == 0 and length >= 1
    else:
        assert not views and not accessors
    end = 0
    for v in views:
        assert v["buffer"] == 0
        assert v["byteOffset"] % 4 == 0, "bufferView offset not 4-aligned"
        assert v["byteOffset"] >= end, "bufferViews overlap or are out of order"
        assert v["byteLength"] >= 1
        assert v["target"] in (34962, 34963)
        end = v["byteOffset"] + v["byteLength"]
        assert end <= gltf["buffers"][0]["byteLength"], "bufferView past the end of the buffer"
    used_accessors = set()
    used_materials = set()
    for m in meshes:
        assert len(m["primitives"]) >= 1
        for p in m["primitives"]:
            mode = p.get("mode", 4)
            assert mode in (1, 4)
            assert "POSITION" in p["attributes"]
            pos_index = p["attributes"]["POSITION"]
            pa = accessors[pos_index]
            assert pa["componentType"] == FLOAT and pa["type"] == "VEC3"
            assert views[pa["bufferView"]]["target"] == 34962
            assert pa.get("byteOffset", 0) % 4 == 0
            assert pa["count"] * 12 <= views[pa["bufferView"]]["byteLength"]
            pos = decode_accessor(gltf, binary, pos_index)
            assert np.isfinite(pos).all()
            assert pa["min"] == [float(x) for x in pos.min(axis=0)], "POSITION min mismatch"
            assert pa["max"] == [float(x) for x in pos.max(axis=0)], "POSITION max mismatch"
            used_accessors.add(pos_index)
            ia = accessors[p["indices"]]
            assert ia["type"] == "SCALAR" and ia["componentType"] in (USHORT, UINT)
            assert views[ia["bufferView"]]["target"] == 34963
            idx = decode_accessor(gltf, binary, p["indices"]).reshape(-1)
            assert (ia["componentType"] == USHORT) == (pa["count"] <= 65535), "index type does not follow the vertex count"
            assert ia.get("byteOffset", 0) % (2 if ia["componentType"] == USHORT else 4) == 0
            assert idx.max() < pa["count"], "index out of range"
            assert ia["count"] * (2 if ia["componentType"] == USHORT else 4) == views[ia["bufferView"]]["byteLength"]
            used_accessors.add(p["indices"])
            if mode == 4:
                assert len(idx) % 3 == 0
                na = accessors[p["attributes"]["NORMAL"]]
                assert na["componentType"] == FLOAT and na["type"] == "VEC3" and na["count"] == pa["count"]
                assert views[na["bufferView"]]["target"] == 34962
                nrm = decode_accessor(gltf, binary, p["attributes"]["NORMAL"])
                assert np.isfinite(nrm).all()
                assert np.abs(np.linalg.norm(nrm, axis=1) - 1.0).max() < 1e-5, "normals are not unit length"
                used_accessors.add(p["attributes"]["NORMAL"])
                assert 0 <= p["material"] < len(gltf["materials"])
                used_materials.add(p["material"])
            else:
                assert len(idx) % 2 == 0
                assert "NORMAL" not in p["attributes"]
    assert used_accessors == set(range(len(accessors))), "an accessor is not used"
    assert len(views) == len(accessors)
    assert used_materials == set(range(len(gltf.get("materials", []))))
    seen = set()
    stack = list(gltf["scenes"][0].get("nodes", []))
    while stack:
        i = stack.pop()
        assert 0 <= i < len(nodes) and i not in seen, "node reused or out of range"
        seen.add(i)
        n = nodes[i]
        assert not ("matrix" in n and any(k in n for k in ("translation", "rotation", "scale")))
        if "rotation" in n:
            assert len(n["rotation"]) == 4 and abs(math.sqrt(sum(c * c for c in n["rotation"])) - 1.0) < 1e-9
        if "scale" in n:
            assert len(n["scale"]) == 3 and all(abs(c) > 0 for c in n["scale"])
        if "mesh" in n:
            assert 0 <= n["mesh"] < len(meshes)
        stack.extend(n.get("children", []))
    assert seen == set(range(len(nodes))), "a node is unreachable from the scene"
    assert sorted(m for n in nodes for m in ([n["mesh"]] if "mesh" in n else [])) == list(range(len(meshes)))
    return gltf


def export(doc: Document, ext: str, name: str = "model") -> str:
    path = tmp_path(name + ext)
    registry.by_path(path).save(path, doc, {})
    return path


def load(path: str) -> Document:
    return registry.by_path(path).load(path)


def roundtrip(doc: Document, ext: str):
    path = export(doc, ext)
    gltf = validate(path)
    return path, gltf, load(path)


def signed_volume(mesh: Mesh) -> float:
    pts, tris = triangulate(mesh)
    if len(tris) == 0:
        return 0.0
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def tri_normals(mesh: Mesh) -> np.ndarray:
    pts, tris = triangulate(mesh)
    n = np.cross(pts[tris[:, 1]] - pts[tris[:, 0]], pts[tris[:, 2]] - pts[tris[:, 0]])
    return n / np.linalg.norm(n, axis=1)[:, None]


def tri_area(mesh: Mesh) -> float:
    pts, tris = triangulate(mesh)
    n = np.cross(pts[tris[:, 1]] - pts[tris[:, 0]], pts[tris[:, 2]] - pts[tris[:, 0]])
    return float(np.linalg.norm(n, axis=1).sum() / 2.0)


def same_points(a: np.ndarray, b: np.ndarray, tol: float = 1e-3) -> bool:
    if len(a) != len(b):
        return False
    d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    return bool(d.min(axis=1).max() < tol and d.min(axis=0).max() < tol)


def uv_sphere(radius: float = 100.0, lat: int = 12, lon: int = 16) -> Mesh:
    pts = [(0.0, radius, 0.0), (0.0, -radius, 0.0)]
    for i in range(1, lat):
        theta = math.pi * i / lat
        for j in range(lon):
            phi = 2.0 * math.pi * j / lon
            pts.append((radius * math.sin(theta) * math.cos(phi), radius * math.cos(theta),
                        radius * math.sin(theta) * math.sin(phi)))

    def ring(i: int, j: int) -> int:
        return 2 + (i - 1) * lon + (j % lon)

    polys = []
    for j in range(lon):
        polys.append((0, ring(1, j + 1), ring(1, j)))
        polys.append((1, ring(lat - 1, j), ring(lat - 1, j + 1)))
    for i in range(1, lat - 1):
        for j in range(lon):
            polys.append((ring(i, j), ring(i, j + 1), ring(i + 1, j + 1), ring(i + 1, j)))
    mesh = Mesh(pts, polys)
    if signed_volume(mesh) < 0.0:
        mesh = Mesh(pts, [tuple(reversed(p)) for p in polys])
    return mesh


def grid_mesh(n: int) -> Mesh:
    ys, xs = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
    pts = np.stack([xs.ravel() * 1.0, np.sin(xs.ravel() * 0.3) * np.cos(ys.ravel() * 0.2) * 5.0, ys.ravel() * 1.0], axis=1)
    polys = []
    for i in range(n):
        for j in range(n):
            a = i * (n + 1) + j
            b = a + 1
            c = a + n + 1
            d = c + 1
            polys.append((a, c, b))
            polys.append((b, c, d))
    return Mesh(pts, polys)


def node_matrix(p, r, s) -> np.ndarray:
    return compose(p, r, s)


def test_registered_formats():
    gltf, glb = registry.get("gltf"), registry.get("glb")
    assert gltf.label == "glTF" and gltf.extensions == (".gltf",)
    assert glb.label == "glTF Binary" and glb.extensions == (".glb",)
    assert gltf.load is not None and gltf.save is not None and glb.load is not None and glb.save is not None
    assert registry.by_path("a/b/Thing.GLB").id == "glb"
    assert registry.by_path("x.gltf").id == "gltf"
    assert any("*.gltf" in f for f in registry.import_filters())
    assert any("*.glb" in f for f in registry.export_filters())


def test_cube_roundtrip_both_containers():
    for ext in (".gltf", ".glb"):
        doc = Document([Node("Cube", Mesh.cube(100.0))])
        path, gltf, back = roundtrip(doc, ext)
        assert len(back.nodes) == 1 and back.nodes[0].name == "Cube"
        mesh = back.nodes[0].mesh
        assert len(mesh.points) == 8, f"{ext}: welded points {len(mesh.points)}"
        assert len(mesh.polygons) == 12 and all(len(p) == 3 for p in mesh.polygons)
        assert np.isclose(signed_volume(mesh), 1e6, rtol=1e-5), signed_volume(mesh)
        assert np.allclose(mesh.points.min(axis=0), -50.0, atol=1e-4)
        assert np.allclose(mesh.points.max(axis=0), 50.0, atol=1e-4)
        assert np.allclose(back.nodes[0].matrix, np.eye(4))
        assert back.meta["unit"] == "cm"


def test_cube_is_flat_shaded_with_split_vertices():
    path = export(Document([Node("Cube", Mesh.cube(100.0))]), ".gltf")
    gltf = validate(path)
    prim = gltf["meshes"][0]["primitives"][0]
    assert gltf["accessors"][prim["attributes"]["POSITION"]]["count"] == 24
    assert gltf["accessors"][prim["indices"]]["count"] == 36
    assert gltf["accessors"][prim["indices"]]["componentType"] == USHORT
    assert gltf["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"][:3] == [0.8, 0.8, 0.8]


def test_sphere_roundtrip_both_containers():
    sphere = uv_sphere()
    quads = sum(1 for p in sphere.polygons if len(p) == 4)
    tris = sum(1 for p in sphere.polygons if len(p) == 3)
    for ext in (".gltf", ".glb"):
        _, _, back = roundtrip(Document([Node("Sphere", sphere)]), ext)
        mesh = back.nodes[0].mesh
        assert len(mesh.points) == len(sphere.points), f"{ext}: {len(mesh.points)} vs {len(sphere.points)}"
        assert len(mesh.polygons) == tris + 2 * quads
        assert np.isclose(signed_volume(mesh), signed_volume(sphere), rtol=1e-4)
        assert same_points(mesh.points, sphere.points)


def test_two_objects_with_transforms_roundtrip():
    ma = node_matrix((10, 20, 30), (20, 30, 40), (1, 2, 3))
    mb = node_matrix((-50, 0, 5), (15, -40, 70), (2, 2, 2))
    for ext in (".gltf", ".glb"):
        doc = Document([Node("A", Mesh.cube(100.0), ma), Node("B", uv_sphere(), mb)])
        path, gltf, back = roundtrip(doc, ext)
        assert [n.name for n in back.nodes] == ["A", "B"]
        assert len(gltf["nodes"]) == 2 and len(gltf["meshes"]) == 2
        assert "translation" in gltf["nodes"][0] and "rotation" in gltf["nodes"][0] and "scale" in gltf["nodes"][0]
        assert np.allclose(gltf["nodes"][0]["translation"], [0.1, 0.2, 0.3])
        assert np.allclose(back.nodes[0].matrix, ma, atol=1e-6)
        assert np.allclose(back.nodes[1].matrix, mb, atol=1e-6)
        for before, after in zip(doc.nodes, back.nodes):
            assert same_points(baked_mesh(before).points, baked_mesh(after).points, 1e-3)
            assert np.isclose(signed_volume(baked_mesh(after)), signed_volume(baked_mesh(before)), rtol=1e-4)
        assert back.nodes[0].position is not None and np.allclose(back.nodes[0].position, (10, 20, 30), atol=1e-6)
        assert np.allclose(back.nodes[0].scale, (1, 2, 3), atol=1e-9)


def test_mirrored_object_roundtrip():
    m = node_matrix((5, 6, 7), (10, 20, 30), (-1, 1, 1))
    assert np.linalg.det(m[:3, :3]) < 0
    doc = Document([Node("Mirror", uv_sphere(80.0), m)])
    for ext in (".gltf", ".glb"):
        _, gltf, back = roundtrip(doc, ext)
        node = gltf["nodes"][0]
        assert "matrix" not in node and min(node["scale"]) < 0
        assert abs(abs(np.prod(node["scale"])) - 1.0) < 1e-9
        assert np.allclose(back.nodes[0].matrix, m, atol=1e-6)
        before = baked_mesh(doc.nodes[0])
        after = baked_mesh(back.nodes[0])
        assert signed_volume(after) > 0 and np.isclose(signed_volume(after), signed_volume(before), rtol=1e-4)
        assert same_points(before.points, after.points)
    flip_y = np.diag([1.0, -1.0, 1.0, 1.0])
    _, gltf, back = roundtrip(Document([Node("FlipY", Mesh.cube(100.0), flip_y)]), ".gltf")
    assert gltf["nodes"][0]["scale"] == [1.0, -1.0, 1.0] and "rotation" not in gltf["nodes"][0]
    assert np.allclose(back.nodes[0].matrix, flip_y)
    assert signed_volume(baked_mesh(back.nodes[0])) > 0


def test_sheared_matrix_is_baked_into_vertices():
    m = np.eye(4)
    m[0, 1] = 0.5
    m[:3, 3] = (5.0, 6.0, 7.0)
    doc = Document([Node("Shear", Mesh.cube(100.0), m)])
    for ext in (".gltf", ".glb"):
        _, gltf, back = roundtrip(doc, ext)
        node = gltf["nodes"][0]
        assert "matrix" not in node and "rotation" not in node and "scale" not in node
        assert np.allclose(node["translation"], [0.05, 0.06, 0.07])
        before = baked_mesh(doc.nodes[0])
        after = baked_mesh(back.nodes[0])
        assert same_points(before.points, after.points)
        assert signed_volume(after) > 0 and np.isclose(signed_volume(after), signed_volume(before), rtol=1e-4)
    mirror_shear = m.copy()
    mirror_shear[2, 2] = -1.0
    _, _, back = roundtrip(Document([Node("ShearMirror", Mesh.cube(100.0), mirror_shear)]), ".glb")
    before = baked_mesh(Node("x", Mesh.cube(100.0), mirror_shear))
    after = baked_mesh(back.nodes[0])
    assert same_points(before.points, after.points)
    assert signed_volume(after) > 0


def test_hierarchy_roundtrip_with_children_before_parents():
    root = node_matrix((100, 0, 0), (0, 0, 30), (2, 2, 2))
    mid_local = node_matrix((0, 50, 0), (10, 20, 30), (1, 1, 1))
    mid = root @ mid_local
    leaf_local = node_matrix((20, 0, 10), (0, 0, 0), (1, 3, 1))
    leaf = mid @ leaf_local
    doc = Document([
        Node("Leaf", Mesh.cube(40.0), leaf, 2),
        Node("Mid", Mesh.cube(60.0), mid, 2),
        Node("Root", None, root, None),
    ])
    doc.nodes[1].parent = 2
    doc.nodes[0].parent = 1
    for ext in (".gltf", ".glb"):
        _, gltf, back = roundtrip(doc, ext)
        names = [n.name for n in back.nodes]
        assert sorted(names) == ["Leaf", "Mid", "Root"]
        by_name = {n.name: n for n in back.nodes}
        assert by_name["Root"].parent is None and by_name["Root"].mesh is None
        assert back.nodes[by_name["Mid"].parent].name == "Root"
        assert back.nodes[by_name["Leaf"].parent].name == "Mid"
        assert np.allclose(by_name["Root"].matrix, root, atol=1e-6)
        assert np.allclose(by_name["Mid"].matrix, mid, atol=1e-6)
        assert np.allclose(by_name["Leaf"].matrix, leaf, atol=1e-6)
        assert np.allclose(by_name["Leaf"].position, (20, 0, 10), atol=1e-6)
        assert len(gltf["scenes"][0]["nodes"]) == 1


def test_hierarchy_with_sheared_parent_keeps_world_geometry():
    root = np.eye(4)
    root[0, 1] = 0.4
    root[:3, 3] = (10.0, 0.0, 0.0)
    child = root @ node_matrix((0, 30, 0), (0, 30, 0), (1, 1, 1))
    doc = Document([Node("Root", Mesh.cube(100.0), root, None), Node("Child", Mesh.cube(50.0), child, 0)])
    _, gltf, back = roundtrip(doc, ".gltf")
    by_name = {n.name: n for n in back.nodes}
    for name, original in (("Root", doc.nodes[0]), ("Child", doc.nodes[1])):
        assert same_points(baked_mesh(original).points, baked_mesh(by_name[name]).points, 1e-3), name


def test_loose_edges_use_a_lines_primitive():
    pts = [(0, 0, 0), (100, 0, 0), (100, 100, 0), (0, 100, 50), (200, 0, 0)]
    mesh = Mesh(pts, [], [(0, 1), (1, 2), (2, 3), (1, 4)])
    for ext in (".gltf", ".glb"):
        _, gltf, back = roundtrip(Document([Node("Lines", mesh)]), ext)
        prims = gltf["meshes"][0]["primitives"]
        assert len(prims) == 1 and prims[0]["mode"] == 1
        got = back.nodes[0].mesh
        assert len(got.points) == 5 and got.polygons == [] and len(got.loose_edges) == 4
        edges = {tuple(sorted(map(tuple, np.round(got.points[list(e)], 2).tolist()))) for e in got.loose_edges}
        want = {tuple(sorted(map(tuple, np.round(np.array(pts, float)[list(e)], 2).tolist()))) for e in mesh.loose_edges}
        assert edges == want
    mixed = Mesh([(0, 0, 0), (100, 0, 0), (0, 100, 0), (300, 0, 0)], [(0, 1, 2)], [(1, 3)])
    _, gltf, back = roundtrip(Document([Node("Mixed", mixed)]), ".glb")
    assert [p.get("mode", 4) for p in gltf["meshes"][0]["primitives"]] == [4, 1]
    assert len(back.nodes[0].mesh.polygons) == 1 and len(back.nodes[0].mesh.loose_edges) == 1


def test_concave_ngon_keeps_area_and_normal():
    pts = [(0, 0, 0), (200, 0, 0), (200, 0, 100), (100, 0, 100), (100, 0, 200), (0, 0, 200)]
    mesh = Mesh(pts, [tuple(range(6))])
    ref = mesh.polygon_normals()[0]
    path, gltf, back = roundtrip(Document([Node("L", mesh)]), ".gltf")
    got = back.nodes[0].mesh
    assert np.isclose(tri_area(got), 30000.0, rtol=1e-5)
    assert (tri_normals(got) @ ref).min() > 0.99
    prim = gltf["meshes"][0]["primitives"][0]
    data = base64.b64decode(gltf["buffers"][0]["uri"].split(",", 1)[1])
    nrm = decode_accessor(gltf, data, prim["attributes"]["NORMAL"])
    assert gltf["accessors"][prim["attributes"]["POSITION"]]["count"] == 6
    assert np.allclose(nrm, ref, atol=1e-6)


def test_index_component_type_follows_vertex_count():
    small = export(Document([Node("S", grid_mesh(10))]), ".glb")
    g = validate(small)
    assert g["accessors"][g["meshes"][0]["primitives"][0]["indices"]]["componentType"] == USHORT
    big = grid_mesh(120)
    assert len(big.polygons) * 3 > 65535
    path, g, back = roundtrip(Document([Node("B", big)]), ".gltf")
    assert g["accessors"][g["meshes"][0]["primitives"][0]["indices"]]["componentType"] == UINT
    assert len(back.nodes[0].mesh.polygons) == len(big.polygons)
    assert len(back.nodes[0].mesh.points) == len(big.points)
    for tris, want in ((21845, USHORT), (21846, UINT)):
        edge = grid_mesh(120)
        edge.polygons = edge.polygons[:tris]
        g = validate(export(Document([Node("E", edge)]), ".glb"))
        got = g["accessors"][g["meshes"][0]["primitives"][0]["indices"]]["componentType"]
        assert got == want, (tris, got)


def test_groups_and_empty_documents():
    for ext in (".gltf", ".glb"):
        _, gltf, back = roundtrip(Document([Node("Group", None, node_matrix((1, 2, 3), (0, 0, 0), (1, 1, 1)))]), ext)
        assert "buffers" not in gltf and "meshes" not in gltf
        assert len(back.nodes) == 1 and back.nodes[0].mesh is None
        assert np.allclose(back.nodes[0].matrix[:3, 3], (1, 2, 3))
        _, gltf, back = roundtrip(Document([]), ext)
        assert back.nodes == []
        _, gltf, back = roundtrip(Document([Node("Empty", Mesh.empty())]), ext)
        assert len(back.nodes) == 1 and back.nodes[0].mesh is None


def test_export_rejects_bad_documents():
    path = tmp_path("bad.gltf")
    fmt = registry.get("gltf")
    bad_parent = Document([Node("A", Mesh.cube(10.0), parent=5)])
    cycle = Document([Node("A", Mesh.cube(10.0), parent=1), Node("B", Mesh.cube(10.0), parent=0)])
    nan_mesh = Mesh([(0, 0, 0), (math.nan, 0, 0), (0, 1, 0)], [(0, 1, 2)])
    nan_matrix = np.eye(4)
    nan_matrix[0, 3] = math.inf
    for label, doc in (("parent", bad_parent), ("cycle", cycle), ("nan", Document([Node("N", nan_mesh)])),
                       ("matrix", Document([Node("M", Mesh.cube(10.0), nan_matrix)]))):
        try:
            fmt.save(path, doc, {})
        except FileFormatError as exc:
            assert "bad.gltf" in str(exc), str(exc)
        else:
            raise AssertionError(f"{label}: export did not fail")


def test_exported_metres_and_unit_conversion():
    path = export(Document([Node("Cube", Mesh.cube(100.0), node_matrix((100, 0, 0), (0, 0, 0), (1, 1, 1)))]), ".gltf")
    gltf = validate(path)
    accessor = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert accessor["min"] == [-0.5, -0.5, -0.5] and accessor["max"] == [0.5, 0.5, 0.5]
    assert gltf["nodes"][0]["translation"] == [1.0, 0.0, 0.0]
    gen = Gen()
    v = gen.floats([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    i = gen.ints([0, 1, 2], USHORT)
    doc = gen.finish(build([{"attributes": {"POSITION": v}, "indices": i}], [{"mesh": 0, "translation": [1, 2, 3]}]))
    got = load(gen.write("metre", doc))
    assert np.allclose(sorted(got.nodes[0].mesh.points.tolist()), sorted([[0, 0, 0], [100, 0, 0], [0, 100, 0]]))
    assert np.allclose(got.nodes[0].matrix[:3, 3], (100, 200, 300))


class Gen:
    def __init__(self) -> None:
        self.blob = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []

    def view(self, data: bytes, stride: int | None = None) -> int:
        while len(self.blob) % 4:
            self.blob.append(0)
        entry = {"buffer": 0, "byteOffset": len(self.blob), "byteLength": len(data)}
        if stride:
            entry["byteStride"] = stride
        self.blob += data
        self.views.append(entry)
        return len(self.views) - 1

    def acc(self, view, ctype: int, count: int, kind: str, offset: int = 0, **extra) -> int:
        entry = {"componentType": ctype, "count": count, "type": kind}
        if view is not None:
            entry["bufferView"] = view
        if offset:
            entry["byteOffset"] = offset
        entry.update(extra)
        self.accessors.append(entry)
        return len(self.accessors) - 1

    def floats(self, values, **extra) -> int:
        arr = np.array(values, dtype="<f4")
        return self.acc(self.view(arr.tobytes()), FLOAT, len(arr), "VEC3", **extra)

    def ints(self, values, ctype: int) -> int:
        code = {UBYTE: "u1", USHORT: "<u2", UINT: "<u4"}[ctype]
        arr = np.array(values, dtype=code)
        return self.acc(self.view(arr.tobytes()), ctype, len(arr), "SCALAR")

    def finish(self, doc: dict) -> dict:
        doc = dict(doc)
        if self.accessors:
            doc["accessors"] = self.accessors
        if self.views:
            doc["bufferViews"] = self.views
            doc["buffers"] = [{"byteLength": len(self.blob)}]
        return doc

    def write(self, name: str, doc: dict, kind: str = "gltf") -> str:
        doc = json.loads(json.dumps(doc))
        blob = bytes(self.blob)
        if kind == "glb":
            path = tmp_path(name + ".glb")
            with open(path, "wb") as handle:
                handle.write(glb_bytes(doc, blob))
            return path
        path = tmp_path(name + ".gltf")
        if "buffers" in doc:
            if kind == "ext":
                folder = os.path.join(os.path.dirname(path), "sub dir")
                os.makedirs(folder)
                with open(os.path.join(folder, "data file.bin"), "wb") as handle:
                    handle.write(blob)
                doc["buffers"][0]["uri"] = "sub%20dir/data%20file.bin"
            else:
                doc["buffers"][0].setdefault("uri", "data:application/octet-stream;base64," + base64.b64encode(blob).decode())
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        return path


def build(primitives, nodes=None, **top) -> dict:
    doc = {"asset": {"version": "2.0"}, "meshes": [{"primitives": primitives}],
           "nodes": nodes if nodes is not None else [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    doc.update(top)
    return doc


def mesh_of(doc: Document, index: int = 0) -> Mesh:
    return doc.nodes[index].mesh


def test_import_triangle_strip():
    for kind in ("gltf", "glb", "ext"):
        g = Gen()
        v = g.floats([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 2, 0), (1, 2, 0)])
        i = g.ints([0, 1, 2, 3, 4, 5], USHORT)
        doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i, "mode": 5}]))
        mesh = mesh_of(load(g.write("strip", doc, kind)))
        assert len(mesh.polygons) == 4 and len(mesh.points) == 6
        assert np.allclose(tri_normals(mesh), [0, 0, 1]), kind
        assert np.isclose(tri_area(mesh), 20000.0)


def test_import_triangle_fan_and_welding():
    g = Gen()
    v = g.floats([(0.5, 0.5, 0), (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 0)])
    doc = g.finish(build([{"attributes": {"POSITION": v}, "mode": 6}]))
    mesh = mesh_of(load(g.write("fan", doc)))
    assert len(mesh.polygons) == 4
    assert len(mesh.points) == 5, "the repeated corner must be welded"
    assert np.allclose(tri_normals(mesh), [0, 0, 1])
    assert np.isclose(tri_area(mesh), 10000.0)


def test_import_non_indexed_triangles_are_welded():
    g = Gen()
    v = g.floats([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    doc = g.finish(build([{"attributes": {"POSITION": v}}]))
    mesh = mesh_of(load(g.write("plain", doc)))
    assert len(mesh.points) == 4 and len(mesh.polygons) == 2
    assert np.isclose(tri_area(mesh), 10000.0)
    assert np.allclose(tri_normals(mesh), [0, 0, 1])


def test_import_line_modes():
    pts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    expect = {1: 2, 2: 4, 3: 3}
    for mode, count in expect.items():
        g = Gen()
        v = g.floats(pts)
        i = g.ints([0, 1, 2, 3], UBYTE)
        doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i, "mode": mode}]))
        mesh = mesh_of(load(g.write(f"lines{mode}", doc)))
        assert mesh.polygons == [] and len(mesh.loose_edges) == count, (mode, mesh.loose_edges)
        assert len(mesh.points) == 4


def test_import_accessor_component_types_offsets_and_normalization():
    g = Gen()
    corners = [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]
    arr16 = np.array(corners, dtype="<i2") * 32767
    pad = g.view(b"\x00" * 8)
    v16 = g.acc(g.view(arr16.tobytes()), SHORT, 4, "VEC3", normalized=True)
    arr8 = np.array(corners, dtype="i1") * 127
    v8 = g.acc(g.view(arr8.tobytes()), BYTE, 4, "VEC3", normalized=True)
    raw_int = np.array([[0, 0, 0], [3, 0, 0], [3, 3, 0], [0, 3, 0]], dtype="<u2")
    vu = g.acc(g.view(raw_int.tobytes()), USHORT, 4, "VEC3")
    idx32 = g.ints([0, 1, 2, 0, 2, 3], UINT)
    for label, acc, size in (("int16 normalized", v16, 100.0), ("int8 normalized", v8, 100.0), ("uint16", vu, 300.0)):
        doc = g.finish(build([{"attributes": {"POSITION": acc}, "indices": idx32}]))
        mesh = mesh_of(load(g.write("types", doc)))
        assert len(mesh.polygons) == 2 and len(mesh.points) == 4, label
        span = mesh.points.max(axis=0) - mesh.points.min(axis=0)
        expected = size * 2 if "normalized" in label else size
        assert np.allclose(span, [expected, expected, 0.0], atol=1e-3), (label, span)
    g = Gen()
    g.view(b"\xAA" * 6)
    base = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], dtype="<f4")
    data = b"\x00" * 12 + base.tobytes()
    view = g.view(data)
    v = g.acc(view, FLOAT, 4, "VEC3", offset=12)
    ind = np.array([7, 7, 0, 1, 2, 0, 2, 3], dtype="<u2")
    iv = g.view(ind.tobytes())
    i = g.acc(iv, USHORT, 6, "SCALAR", offset=4)
    doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i}]))
    mesh = mesh_of(load(g.write("offset", doc)))
    assert len(mesh.polygons) == 2 and np.isclose(tri_area(mesh), 10000.0)
    assert np.allclose(tri_normals(mesh), [0, 0, 1])


def test_import_byte_stride_interleaved():
    g = Gen()
    rows = []
    for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]:
        rows.append(struct.pack("<3f", *p) + struct.pack("<3f", 0, 0, 1) + struct.pack("<2f", 9, 9))
    view = g.view(b"".join(rows), stride=32)
    v = g.acc(view, FLOAT, 4, "VEC3")
    n = g.acc(view, FLOAT, 4, "VEC3", offset=12)
    i = g.ints([0, 1, 2, 0, 2, 3], USHORT)
    doc = g.finish(build([{"attributes": {"POSITION": v, "NORMAL": n}, "indices": i}]))
    mesh = mesh_of(load(g.write("stride", doc)))
    assert len(mesh.points) == 4 and np.isclose(tri_area(mesh), 10000.0)
    assert np.allclose(mesh.points.max(axis=0), [100, 100, 0], atol=1e-3)
    g = Gen()
    packed = b"".join(struct.pack("<3h", *p) + b"\x00\x00" for p in [(0, 0, 0), (300, 0, 0), (300, 300, 0), (0, 300, 0)])
    view = g.view(packed, stride=8)
    v = g.acc(view, SHORT, 4, "VEC3")
    i = g.ints([0, 1, 2, 0, 2, 3], UBYTE)
    doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i}]))
    mesh = mesh_of(load(g.write("stride16", doc)))
    assert np.allclose(mesh.points.max(axis=0), [30000, 30000, 0], atol=1e-3)


def test_import_sparse_accessors():
    g = Gen()
    where = g.view(np.array([1, 2, 3], dtype="<u2").tobytes())
    vals = g.view(np.array([(1, 0, 0), (1, 1, 0), (0, 1, 0)], dtype="<f4").tobytes())
    v = g.acc(None, FLOAT, 4, "VEC3", sparse={"count": 3, "indices": {"bufferView": where, "componentType": USHORT},
                                              "values": {"bufferView": vals}})
    i = g.ints([0, 1, 2, 0, 2, 3], UBYTE)
    doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i}]))
    mesh = mesh_of(load(g.write("sparse_zero", doc)))
    assert len(mesh.points) == 4 and np.isclose(tri_area(mesh), 10000.0)
    assert np.allclose(tri_normals(mesh), [0, 0, 1])
    g = Gen()
    base = g.view(np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (5, 5, 5)], dtype="<f4").tobytes())
    where = g.view(np.array([3], dtype="u1").tobytes())
    vals = g.view(np.array([(0, 1, 0)], dtype="<f4").tobytes())
    v = g.acc(base, FLOAT, 4, "VEC3", sparse={"count": 1, "indices": {"bufferView": where, "componentType": UBYTE},
                                              "values": {"bufferView": vals}})
    i = g.ints([0, 1, 2, 0, 2, 3], UBYTE)
    doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i}]))
    mesh = mesh_of(load(g.write("sparse_base", doc, "glb")))
    assert np.isclose(tri_area(mesh), 10000.0) and np.allclose(mesh.points.max(axis=0), [100, 100, 0], atol=1e-3)


def test_import_external_bin_and_data_uri_and_glb():
    results = []
    for kind in ("ext", "gltf", "glb"):
        g = Gen()
        v = g.floats([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
        i = g.ints([0, 1, 2, 0, 2, 3], USHORT)
        doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i}]))
        path = g.write("ext_case", doc, kind)
        if kind == "ext":
            assert os.path.exists(os.path.join(os.path.dirname(path), "sub dir", "data file.bin"))
            assert "sub%20dir" in open(path, encoding="utf-8").read()
        results.append(mesh_of(load(path)))
    for m in results:
        assert len(m.polygons) == 2 and np.isclose(tri_area(m), 10000.0)
    assert np.allclose(results[0].points, results[1].points) and np.allclose(results[1].points, results[2].points)


def test_import_trs_and_matrix_hierarchy():
    s = math.sqrt(0.5)
    g = Gen()
    v = g.floats([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    i = g.ints([0, 1, 2], USHORT)
    matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1]
    nodes = [
        {"name": "Root", "translation": [1, 2, 3], "rotation": [0, 0, s, s], "scale": [2, 2, 2], "children": [1]},
        {"translation": [0.5, 0, 0], "mesh": 0, "children": [2]},
        {"matrix": matrix, "mesh": 0},
    ]
    doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i}], nodes))
    got = load(g.write("trs", doc))
    assert [n.parent for n in got.nodes] == [None, 0, 1]
    assert [n.name for n in got.nodes][0] == "Root" and got.nodes[1].name == "Node 1"
    root = np.eye(4)
    root[:3, :3] = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]]) * 2.0
    root[:3, 3] = (100, 200, 300)
    mid = root.copy()
    mid[:3, 3] += root[:3, :3] @ np.array([50.0, 0.0, 0.0])
    leaf = mid.copy()
    leaf[:3, 3] += mid[:3, :3] @ np.array([0.0, 0.0, 100.0])
    assert np.allclose(got.nodes[0].matrix, root, atol=1e-9)
    assert np.allclose(got.nodes[1].matrix, mid, atol=1e-9)
    assert np.allclose(got.nodes[2].matrix, leaf, atol=1e-9)
    assert got.nodes[0].mesh is None and got.nodes[1].mesh is not None and got.nodes[2].mesh is not None
    assert np.allclose(got.nodes[1].position, (50, 0, 0), atol=1e-9)
    assert np.allclose(got.nodes[2].position, (0, 0, 100), atol=1e-9)
    assert np.allclose(got.nodes[0].rotation, (0, 0, 90), atol=1e-6) and np.allclose(got.nodes[0].scale, (2, 2, 2))
    assert got.nodes[1].mesh is not got.nodes[2].mesh
    path = g.write("trs_scene", doc)
    scene = reset()
    objs = import_file(scene, path)
    assert len(objs) == 3
    assert objs[1].parent is objs[0] and objs[2].parent is objs[1] and objs[0].parent is None
    assert np.allclose(objs[2].world_matrix(), leaf, atol=1e-6)


def reset():
    QApplication.instance() or QApplication([sys.argv[0]])
    return scene_mod.reset_scene()


def test_import_several_primitives_are_merged_and_welded():
    g = Gen()
    quad = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    v1 = g.floats(quad)
    i1 = g.ints([0, 1, 2], USHORT)
    v2 = g.floats(quad)
    i2 = g.ints([0, 2, 3], USHORT)
    v3 = g.floats([(1, 1, 0), (2, 1, 0)])
    i3 = g.ints([0, 1], UBYTE)
    doc = g.finish(build([{"attributes": {"POSITION": v1}, "indices": i1},
                          {"attributes": {"POSITION": v2}, "indices": i2, "material": 0},
                          {"attributes": {"POSITION": v3}, "indices": i3, "mode": 1}]))
    mesh = mesh_of(load(g.write("multi", doc)))
    assert len(mesh.points) == 5 and len(mesh.polygons) == 2 and len(mesh.loose_edges) == 1
    assert np.isclose(tri_area(mesh), 10000.0)


def test_import_shared_mesh_and_unused_vertices():
    g = Gen()
    v = g.floats([(0, 0, 0), (1, 0, 0), (0, 1, 0), (9, 9, 9)])
    i = g.ints([0, 1, 2, 2, 2, 0], USHORT)
    nodes = [{"mesh": 0, "children": [1]}, {"mesh": 0, "translation": [2, 0, 0]}]
    doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i}], nodes))
    got = load(g.write("shared", doc))
    a, b = mesh_of(got, 0), mesh_of(got, 1)
    assert a is not b and a.points is not b.points
    assert len(a.points) == 3 and len(a.polygons) == 1, "unused points and degenerate triangles must be dropped"
    assert np.allclose(got.nodes[1].matrix[:3, 3], (200, 0, 0))


def test_import_tolerates_missing_optional_fields_and_ignored_content():
    g = Gen()
    v = g.floats([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    doc = g.finish({"asset": {"version": "2.0"}, "meshes": [{"primitives": [{"attributes": {"POSITION": v, "NORMAL": 99,
                    "TEXCOORD_0": 98}, "material": 7}]}], "nodes": [{"mesh": 0}, {"name": "Empty"}]})
    got = load(g.write("no_scenes", doc))
    assert len(got.nodes) == 2 and got.nodes[0].mesh is not None and got.nodes[1].mesh is None
    assert got.nodes[1].name == "Empty"
    doc2 = dict(doc)
    doc2["scenes"] = [{"name": "S"}]
    assert load(g.write("empty_scene", doc2)).nodes == []
    doc3 = dict(doc)
    doc3.update({
        "scenes": [{"nodes": [0]}, {"nodes": [1]}],
        "cameras": [{"type": "perspective", "perspective": {"yfov": 1, "znear": 0.1}}],
        "skins": [{"joints": [0]}],
        "animations": [{"channels": [], "samplers": []}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1]}}],
        "textures": [{"source": 0}], "images": [{"uri": "missing.png"}], "samplers": [{}],
        "extensionsUsed": ["KHR_materials_unlit"], "extensionsRequired": ["KHR_materials_unlit"],
        "extras": {"anything": [1, 2]}, "extensions": {"VENDOR_thing": {}},
    })
    doc3["nodes"] = [{"mesh": 0, "camera": 0, "skin": 0, "weights": [0.5], "extras": {}}, {"name": "Empty"}]
    got = load(g.write("ignored", doc3))
    assert len(got.nodes) == 1 and got.nodes[0].mesh is not None
    doc3["scene"] = 1
    got = load(g.write("scene_one", doc3))
    assert len(got.nodes) == 1 and got.nodes[0].name == "Empty"


def expect_error(label: str, path: str, contains: str | None = None) -> None:
    try:
        load(path)
    except FileFormatError as exc:
        message = str(exc)
        assert os.path.basename(path) in message, f"{label}: message lacks the file name: {message}"
        if contains is not None:
            assert contains.lower() in message.lower(), f"{label}: {message!r} lacks {contains!r}"
        return
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__} instead of FileFormatError: {exc}")
    raise AssertionError(f"{label}: no error raised")


def valid_parts():
    g = Gen()
    v = g.floats([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    i = g.ints([0, 1, 2, 0, 2, 3], USHORT)
    return g, build([{"attributes": {"POSITION": v}, "indices": i}]), v, i


def test_malformed_files_raise_file_format_error():
    def text(name: str, content: bytes) -> str:
        path = tmp_path(name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    expect_error("not json", text("a.gltf", b"hello there"), "json")
    expect_error("empty", text("b.gltf", b""), "json")
    expect_error("array", text("c.gltf", b"[1, 2]"), "object")
    expect_error("bad utf8", text("d.gltf", b"\xff\xfe\x00{"), "utf")
    expect_error("empty glb", text("e.glb", b"glTF"), "short")
    g, doc, v, i = valid_parts()
    good = glb_bytes(g.finish(doc), bytes(g.blob))
    expect_error("glb truncated", text("f.glb", good[:len(good) - 7]), "truncated")
    expect_error("glb version", text("g.glb", good[:4] + struct.pack("<I", 1) + good[8:]), "version")
    swapped = good[:16] + struct.pack("<I", 0x004E4942) + good[20:]
    expect_error("glb first chunk", text("h.glb", swapped), "JSON")
    huge = good[:12] + struct.pack("<I", 10 ** 6) + good[16:]
    expect_error("glb chunk overflow", text("i.glb", huge), "chunk")
    no_bin = glb_bytes(g.finish(doc), b"")
    expect_error("glb without BIN", text("j.glb", no_bin), "BIN")

    def mutated(label: str, edit, contains: str | None = None, kind: str = "gltf") -> None:
        gg, d, vv, ii = valid_parts()
        d = gg.finish(d)
        edit(d, gg)
        expect_error(label, gg.write("mal_" + label.replace(" ", "_"), d, kind), contains)

    def drop(key):
        return lambda d, gg: d.pop(key)

    mutated("no asset", drop("asset"), "asset")
    mutated("version 1", lambda d, gg: d["asset"].update(version="1.0"), "version")
    mutated("version 3", lambda d, gg: d["asset"].update(version="3.0"), "version")
    mutated("count too big", lambda d, gg: d["accessors"][0].update(count=1000), "past")
    mutated("index out of range", lambda d, gg: None if gg.blob.__setitem__(slice(gg.views[1]["byteOffset"], gg.views[1]["byteOffset"] + 2), struct.pack("<H", 9)) else None, "index")
    mutated("mode 9", lambda d, gg: d["meshes"][0]["primitives"][0].update(mode=9), "mode")
    mutated("no position", lambda d, gg: d["meshes"][0]["primitives"][0]["attributes"].pop("POSITION"), "POSITION")
    mutated("position scalar", lambda d, gg: d["accessors"][0].update(type="SCALAR"), "type")
    mutated("indices vec3", lambda d, gg: d["accessors"][1].update(type="VEC3"), "type")
    mutated("indices float", lambda d, gg: d["accessors"][1].update(componentType=FLOAT), "componentType")
    mutated("bad scene index", lambda d, gg: d.update(scene=3), "scene")
    mutated("child out of range", lambda d, gg: d["nodes"][0].update(children=[4]), "child")
    mutated("cycle", lambda d, gg: d["nodes"][0].update(children=[0]), "more than once")
    mutated("node twice", lambda d, gg: (d["nodes"].append({"mesh": 0}), d["nodes"][0].update(children=[1, 1])), "more than once")
    mutated("stride small", lambda d, gg: gg.views[0].update(byteStride=8) or d.update(bufferViews=gg.views), "byteStride")
    mutated("buffer too long", lambda d, gg: d["buffers"][0].update(byteLength=10 ** 6), "declares")
    mutated("bad base64", lambda d, gg: d["buffers"][0].update(uri="data:application/octet-stream;base64,@@@"), "base64")
    mutated("not base64 uri", lambda d, gg: d["buffers"][0].update(uri="data:text/plain,hello"), "data URI")
    mutated("http uri", lambda d, gg: d["buffers"][0].update(uri="http://example.com/a.bin"), "remote")
    mutated("absolute uri", lambda d, gg: d["buffers"][0].update(uri="C:/data/a.bin"), "remote")
    mutated("draco required", lambda d, gg: d.update(extensionsRequired=["KHR_draco_mesh_compression"]), "draco")
    mutated("meshopt required", lambda d, gg: d.update(extensionsRequired=["EXT_meshopt_compression"]), "meshopt")
    mutated("draco primitive", lambda d, gg: d["meshes"][0]["primitives"][0].update(extensions={"KHR_draco_mesh_compression": {}}), "draco")
    mutated("zero quaternion", lambda d, gg: d["nodes"][0].update(rotation=[0, 0, 0, 0]), "quaternion")
    mutated("short matrix", lambda d, gg: d["nodes"][0].update(matrix=[1, 2, 3]), "matrix")
    mutated("string translation", lambda d, gg: d["nodes"][0].update(translation=["a", 0, 0]), "translation")
    mutated("no primitives", lambda d, gg: d["meshes"][0].update(primitives=[]), "primitive")
    mutated("bad mesh index", lambda d, gg: d["nodes"][0].update(mesh=5), "mesh")
    mutated("bad view index", lambda d, gg: d["accessors"][0].update(bufferView=9), "bufferView")
    mutated("view past buffer", lambda d, gg: d["bufferViews"][0].update(byteOffset=10 ** 5), "past")
    mutated("not affine", lambda d, gg: d["nodes"][0].update(matrix=[1, 0, 0, 5, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]), "affine")
    mutated("nodes not list", lambda d, gg: d.update(nodes={"a": 1}), "nodes")
    mutated("glb no uri buffer in gltf", lambda d, gg: d["buffers"][0].update(uri=None), "uri")

    g, doc, v, i = valid_parts()
    doc = g.finish(doc)
    path = g.write("ext_missing", doc, "ext")
    os.remove(os.path.join(os.path.dirname(path), "sub dir", "data file.bin"))
    expect_error("missing bin file", path, "not found")
    g, doc, v, i = valid_parts()
    doc = g.finish(doc)
    path = g.write("ext_short", doc, "ext")
    with open(os.path.join(os.path.dirname(path), "sub dir", "data file.bin"), "wb") as handle:
        handle.write(b"\x00" * 4)
    expect_error("short bin file", path, "declares")

    g = Gen()
    v = g.floats([(0, 0, 0), (1, 0, 0), (math.nan, 0, 0)])
    doc = g.finish(build([{"attributes": {"POSITION": v}}]))
    expect_error("nan positions", g.write("nan", doc), "finite")
    g = Gen()
    v = g.floats([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    doc = g.finish(build([{"attributes": {"POSITION": v}}]))
    expect_error("4 non-indexed vertices", g.write("four", doc), "multiple of 3")
    g = Gen()
    where = g.view(np.array([9], dtype="<u2").tobytes())
    vals = g.view(np.array([(1, 0, 0)], dtype="<f4").tobytes())
    v = g.acc(None, FLOAT, 3, "VEC3", sparse={"count": 1, "indices": {"bufferView": where, "componentType": USHORT},
                                              "values": {"bufferView": vals}})
    doc = g.finish(build([{"attributes": {"POSITION": v}}]))
    expect_error("sparse index out of range", g.write("sparse_bad", doc), "sparse")
    g = Gen()
    v = g.floats([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    i = g.ints([0, 1], USHORT)
    doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i, "mode": 5}]))
    expect_error("strip with two indices", g.write("short_strip", doc), "at least 3")
    doc = g.finish(build([{"attributes": {"POSITION": v}, "indices": i, "mode": 1}]))
    assert len(load(g.write("one_line", doc)).nodes[0].mesh.loose_edges) == 1
    missing = tmp_path("nothing.glb")
    expect_error("missing file", missing)


def test_api_import_export_through_the_scene():
    scene = reset()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_object("Box", Mesh.cube(100.0))
    path = tmp_path("scene.glb")
    export_file(scene, path)
    gltf = validate(path)
    assert len(gltf["nodes"]) == 1
    other = reset()
    for obj in list(other.objects):
        other.remove_object(obj)
    objs = import_file(other, path)
    assert len(objs) == 1 and objs[0].name == "Box"
    assert np.isclose(signed_volume(objs[0].mesh), 1e6, rtol=1e-5)
    bad = tmp_path("broken.gltf")
    with open(bad, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    try:
        import_file(other, bad)
    except FileFormatError as exc:
        assert "broken.gltf" in str(exc)
    else:
        raise AssertionError("broken file imported")
    assert len(other.objects) == 1


def test_timing_with_100000_triangles():
    mesh = grid_mesh(224)
    count = len(mesh.polygons)
    assert 100000 <= count <= 101000, count
    doc = Document([Node("Big", mesh)])
    path = tmp_path("big.glb")
    t0 = time.perf_counter()
    registry.get("glb").save(path, doc, {})
    t_export = time.perf_counter() - t0
    validate(path)
    t0 = time.perf_counter()
    back = load(path)
    t_import = time.perf_counter() - t0
    got = back.nodes[0].mesh
    assert len(got.polygons) == count and len(got.points) == len(mesh.points)
    path2 = tmp_path("big.gltf")
    t0 = time.perf_counter()
    registry.get("gltf").save(path2, doc, {})
    t_text = time.perf_counter() - t0
    t0 = time.perf_counter()
    load(path2)
    t_text_import = time.perf_counter() - t0
    print(f"     timing 100k triangles: glb export {t_export:.2f}s import {t_import:.2f}s, "
          f"gltf export {t_text:.2f}s import {t_text_import:.2f}s")
    assert t_export < 5.0 and t_text < 5.0, (t_export, t_text)
    assert t_import < 15.0 and t_text_import < 15.0, (t_import, t_text_import)


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
