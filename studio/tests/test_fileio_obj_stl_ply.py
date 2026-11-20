from __future__ import annotations

import os
import random
import struct
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

import quartz_studio.fileio
from quartz_studio.fileio import Document, FileFormatError, Node, baked_mesh, registry, triangulate
from quartz_studio.scene import Mesh

TMP = tempfile.mkdtemp(prefix="qz_fileio_obj_stl_ply_")
SEQ = [0]
CUBE_VOLUME = 8000.0


def _path(name: str) -> str:
    return os.path.join(TMP, name)


def _write(name: str, content) -> str:
    path = _path(name)
    if isinstance(content, bytes):
        with open(path, "wb") as handle:
            handle.write(content)
    else:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return path


def _next_path(fmt_id: str) -> str:
    SEQ[0] += 1
    return _path(f"out_{SEQ[0]}.{fmt_id}")


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def _export(fmt_id: str, document: Document, options: dict | None = None) -> str:
    path = _next_path(fmt_id)
    registry.get(fmt_id).save(path, document, dict(options or {}))
    return path


def _load(fmt_id: str, path: str) -> Document:
    return registry.get(fmt_id).load(path)


def _round(fmt_id: str, document: Document, options: dict | None = None) -> Document:
    return _load(fmt_id, _export(fmt_id, document, options))


def _volume(mesh: Mesh) -> float:
    total = 0.0
    p = mesh.points
    for poly in mesh.polygons:
        a = p[poly[0]]
        for i in range(1, len(poly) - 1):
            total += float(np.dot(a, np.cross(p[poly[i]], p[poly[i + 1]])))
    return total / 6.0


def _tri_volume(mesh: Mesh) -> float:
    points, tris = triangulate(mesh)
    return _volume(Mesh(points, tris.tolist()))


def _bounds(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    return mesh.points.min(axis=0), mesh.points.max(axis=0)


def _uv_sphere(radius: float = 10.0, segments: int = 16, rings: int = 8) -> Mesh:
    points = [(0.0, radius, 0.0)]
    for i in range(1, rings):
        phi = np.pi * i / rings
        for j in range(segments):
            theta = 2.0 * np.pi * j / segments
            points.append((radius * np.sin(phi) * np.cos(theta), radius * np.cos(phi),
                           radius * np.sin(phi) * np.sin(theta)))
    points.append((0.0, -radius, 0.0))
    bottom = len(points) - 1

    def ring(i: int, j: int) -> int:
        return 1 + (i - 1) * segments + (j % segments)

    polygons = []
    for j in range(segments):
        polygons.append((0, ring(1, j + 1), ring(1, j)))
        polygons.append((bottom, ring(rings - 1, j), ring(rings - 1, j + 1)))
    for i in range(1, rings - 1):
        for j in range(segments):
            polygons.append((ring(i, j), ring(i, j + 1), ring(i + 1, j + 1), ring(i + 1, j)))
    return Mesh(points, polygons)


def _ngon_prism(sides: int = 7, radius: float = 5.0, height: float = 4.0) -> Mesh:
    top = [(radius * np.cos(2 * np.pi * j / sides), height, radius * np.sin(2 * np.pi * j / sides))
           for j in range(sides)]
    bottom = [(x, -height, z) for x, _, z in top]
    points = top + bottom
    polygons = [tuple(sides - 1 - (j % sides) for j in range(sides))]
    polygons.append(tuple(sides + j for j in range(sides)))
    for j in range(sides):
        k = (j + 1) % sides
        polygons.append((j, k, sides + k, sides + j))
    return Mesh(points, polygons)


def _translation(x: float, y: float, z: float) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = [x, y, z]
    return m


def _grid(n: int) -> Mesh:
    xs, zs = np.meshgrid(np.arange(n + 1, dtype=float), np.arange(n + 1, dtype=float))
    points = np.column_stack([xs.ravel(), 0.5 * np.sin(xs.ravel() * 0.3), zs.ravel()])
    index = np.arange((n + 1) * (n + 1)).reshape(n + 1, n + 1)
    a = index[:-1, :-1].ravel()
    b = index[1:, :-1].ravel()
    c = index[1:, 1:].ravel()
    d = index[:-1, 1:].ravel()
    polygons = [(int(p), int(q), int(r)) for p, q, r in zip(a, b, c)]
    polygons += [(int(p), int(q), int(r)) for p, q, r in zip(a, c, d)]
    return Mesh(points, polygons)


def _raises_format(fn, *needles: str) -> None:
    try:
        fn()
    except FileFormatError as exc:
        message = str(exc)
        for needle in needles:
            assert needle in message, f"{needle!r} not in {message!r}"
        return
    raise AssertionError("expected FileFormatError")


def _cube_doc(name: str = "Cube", size: float = 20.0) -> Document:
    return Document([Node(name, Mesh.cube(size))], {"unit": "cm"})


def test_round_trip_cube_in_every_format():
    expected = {"obj": 6, "ply": 6, "stl": 12}
    for fmt_id in ("obj", "stl", "ply"):
        back = _round(fmt_id, _cube_doc())
        assert len(back.nodes) == 1, fmt_id
        mesh = back.nodes[0].mesh
        assert len(mesh.points) == 8, fmt_id
        assert len(mesh.polygons) == expected[fmt_id], fmt_id
        assert np.isclose(_volume(mesh), CUBE_VOLUME), fmt_id
        lo, hi = _bounds(mesh)
        assert np.allclose(lo, -10.0) and np.allclose(hi, 10.0), fmt_id


def test_round_trip_sphere_in_every_format():
    sphere = _uv_sphere()
    doc = Document([Node("Sphere", sphere)], {"unit": "cm"})
    for fmt_id in ("obj", "ply", "stl"):
        mesh = _round(fmt_id, doc).nodes[0].mesh
        if fmt_id == "stl":
            assert np.isclose(_volume(mesh), _tri_volume(sphere), rtol=1e-5), fmt_id
        else:
            assert np.isclose(_volume(mesh), _volume(sphere), rtol=1e-9), fmt_id
        assert np.allclose(_bounds(mesh)[0], _bounds(sphere)[0]), fmt_id
        assert np.allclose(_bounds(mesh)[1], _bounds(sphere)[1]), fmt_id
        if fmt_id == "stl":
            assert len(mesh.polygons) == 2 * 16 + 2 * 16 * 6, fmt_id
        else:
            assert len(mesh.points) == len(sphere.points), fmt_id
            assert len(mesh.polygons) == len(sphere.polygons), fmt_id


def test_round_trip_ngon_keeps_ngons_in_obj_and_ply():
    prism = _ngon_prism(7)
    doc = Document([Node("Prism", prism)], {"unit": "cm"})
    for fmt_id in ("obj", "ply"):
        mesh = _round(fmt_id, doc).nodes[0].mesh
        sizes = sorted(len(p) for p in mesh.polygons)
        assert sizes == [4] * 7 + [7, 7], (fmt_id, sizes)
        assert np.isclose(_volume(mesh), _volume(prism)), fmt_id
    stl = _round("stl", doc).nodes[0].mesh
    assert len(stl.polygons) == 2 * (7 - 2) + 2 * 7
    assert np.isclose(_volume(stl), _volume(prism))


def test_two_objects_obj_keeps_objects_ply_and_stl_merge():
    doc = Document([Node("Cube", Mesh.cube(20.0)),
                    Node("Sphere", _uv_sphere(), _translation(50.0, 0.0, 0.0))], {"unit": "cm"})
    obj_nodes = _round("obj", doc).nodes
    assert [n.name for n in obj_nodes] == ["Cube", "Sphere"]
    assert len(obj_nodes[0].mesh.points) == 8
    assert len(obj_nodes[1].mesh.points) == len(_uv_sphere().points)
    assert np.isclose(_volume(obj_nodes[1].mesh), _volume(_uv_sphere()), rtol=1e-9)
    text = _read_text(_export("obj", doc))
    assert sum(1 for line in text.splitlines() if line.startswith("o ")) == 2
    face_lines = [line for line in text.splitlines() if line.startswith("f ")]
    second = face_lines[6].split()[1:]
    assert min(int(c.split("/")[0]) for c in second) == 9
    ply_points = 8 + len(_uv_sphere().points)
    ply_mesh = _round("ply", doc).nodes[0].mesh
    assert len(ply_mesh.points) == ply_points
    assert np.isclose(_volume(ply_mesh), CUBE_VOLUME + _volume(_uv_sphere()), rtol=1e-9)
    stl_nodes = _round("stl", doc).nodes
    assert len(stl_nodes) == 1
    assert len(stl_nodes[0].mesh.polygons) == 12 + 224
    assert np.isclose(_volume(stl_nodes[0].mesh), CUBE_VOLUME + _tri_volume(_uv_sphere()), rtol=1e-5)


def test_transformed_object_is_baked_to_world_space():
    angle = np.deg2rad(30.0)
    rot = np.eye(4)
    rot[:3, :3] = [[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]]
    scl = np.diag([2.0, 1.0, 0.5, 1.0])
    matrix = _translation(5.0, -3.0, 7.0) @ rot @ scl
    node = Node("Moved", Mesh.cube(20.0), matrix)
    world = baked_mesh(node).points
    doc = Document([node], {"unit": "cm"})
    for fmt_id in ("obj", "ply"):
        back = _round(fmt_id, doc).nodes[0].mesh
        assert np.allclose(back.points, world, atol=1e-9), fmt_id
    stl = _round("stl", doc).nodes[0].mesh
    assert np.isclose(_volume(stl), abs(np.linalg.det(matrix[:3, :3])) * CUBE_VOLUME, rtol=1e-6)
    lo, hi = _bounds(stl)
    assert np.allclose(lo, world.min(axis=0), atol=1e-6) and np.allclose(hi, world.max(axis=0), atol=1e-6)


def test_mirrored_object_keeps_winding_and_positive_volume():
    matrix = _translation(30.0, 0.0, 0.0)
    matrix[0, 0] = -1.0
    node = Node("Mirror", Mesh.cube(20.0), matrix)
    doc = Document([node], {"unit": "cm"})
    for fmt_id in ("obj", "ply", "stl"):
        mesh = _round(fmt_id, doc).nodes[0].mesh
        assert _volume(mesh) > 0.0, fmt_id
        assert np.isclose(_volume(mesh), CUBE_VOLUME), fmt_id
        lo, hi = _bounds(mesh)
        assert np.isclose(lo[0], 20.0) and np.isclose(hi[0], 40.0), fmt_id


def test_scale_option_multiplies_positions():
    doc = _cube_doc()
    for fmt_id in ("obj", "stl", "ply"):
        mesh = _round(fmt_id, doc, {"scale": 2.0}).nodes[0].mesh
        assert np.isclose(_volume(mesh), CUBE_VOLUME * 8.0), fmt_id
        lo, hi = _bounds(mesh)
        assert np.allclose(hi, 20.0) and np.allclose(lo, -20.0), fmt_id
    _raises_format(lambda: _export("obj", doc, {"scale": 0.0}), "scale")


def test_obj_export_layout_and_triangulate_option():
    doc = Document([Node("Cube", Mesh.cube(20.0)), Node("Prism", _ngon_prism(5))], {"unit": "cm"})
    lines = _read_text(_export("obj", doc)).splitlines()
    assert lines[0].startswith("#") and "Quartz Studio" in lines[0]
    assert sum(1 for line in lines if line.startswith("o ")) == 2
    corners = [len(line.split()) - 1 for line in lines if line.startswith("f ")]
    assert sum(corners) == sum(1 for line in lines if line.startswith("vn "))
    for line in lines:
        if line.startswith("f "):
            assert all("//" in token for token in line.split()[1:]), line
    tri_doc = Document([Node("Prism", _ngon_prism(5))], {"unit": "cm"})
    tri_lines = _read_text(_export("obj", tri_doc, {"triangulate": True})).splitlines()
    face_sizes = [len(line.split()) - 1 for line in tri_lines if line.startswith("f ")]
    assert face_sizes and all(s == 3 for s in face_sizes)
    mesh = _load("obj", _export("obj", tri_doc, {"triangulate": True})).nodes[0].mesh
    assert np.isclose(_volume(mesh), _volume(_ngon_prism(5)))


def test_obj_loose_edges_round_trip():
    mesh = Mesh([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1), (1, 2), (2, 3)])
    back = _round("obj", Document([Node("Wire", mesh)], {"unit": "cm"})).nodes[0].mesh
    assert len(back.points) == 4
    assert len(back.loose_edges) == 3
    assert not back.polygons


OBJ_SAMPLE = (
    "# sample file\n"
    "mtllib sample.mtl\n"
    "o Quad\n"
    "v 0 0 0\n"
    "v 1 0 0\n"
    "v 1 1 0\n"
    "v 0 1 0\n"
    "vt 0 0\n"
    "vt 1 0\n"
    "vn 0 0 1\n"
    "\n"
    "usemtl red\n"
    "s 1\n"
    "f 1/1/1 2/2/1 3/1/1 4//1\n"
    "o Tri\n"
    "v 2 0 0 # inline comment\n"
    "v 2 1 0\n"
    "v 3 0 0\n"
    "f -3 -2 -1\n"
    "o Wire\n"
    "v 5 5 5\n"
    "v 6 5 5\n"
    "l 8 9\n"
    "l -2 -1\n"
)


def test_obj_sample_with_every_import_feature():
    doc = _load("obj", _write("sample.obj", OBJ_SAMPLE))
    names = [n.name for n in doc.nodes]
    assert names == ["Quad", "Tri", "Wire"], names
    quad, tri, wire = (n.mesh for n in doc.nodes)
    assert len(quad.points) == 4 and quad.polygons == [(0, 1, 2, 3)]
    assert len(tri.points) == 3 and tri.polygons == [(0, 1, 2)]
    assert np.allclose(tri.points, [[2, 0, 0], [2, 1, 0], [3, 0, 0]])
    assert len(wire.points) == 2 and not wire.polygons
    assert wire.loose_edges == [(0, 1)]


def test_obj_sample_crlf_and_groups_and_no_object():
    crlf = OBJ_SAMPLE.replace("\n", "\r\n")
    doc = _load("obj", _write("sample_crlf.obj", crlf))
    assert [n.name for n in doc.nodes] == ["Quad", "Tri", "Wire"]
    groups = (
        "o Car\r\nv 0 0 0\r\nv 1 0 0\r\nv 1 1 0\r\ng wheels\r\nf 1 2 3\r\n"
        "g body\r\nv 5 0 0\r\nv 6 0 0\r\nv 6 1 0\r\nf 4 5 6\r\n"
    )
    doc = _load("obj", _write("groups.obj", groups))
    assert [n.name for n in doc.nodes] == ["Car", "body"]
    body = doc.nodes[1].mesh
    assert len(body.points) == 3 and body.polygons == [(0, 1, 2)]
    assert np.allclose(body.points, [[5, 0, 0], [6, 0, 0], [6, 1, 0]])
    bare = _load("obj", _write("bare_name.obj", "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"))
    assert [n.name for n in bare.nodes] == ["bare_name"]
    assert bare.nodes[0].mesh.polygons == [(0, 1, 2)]


def test_obj_ngon_import_and_pentagon_kept():
    text = "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0.5 1.5 0\nv 0 1 0\nf 1 2 3 4 5\n"
    mesh = _load("obj", _write("pent.obj", text)).nodes[0].mesh
    assert mesh.polygons == [(0, 1, 2, 3, 4)]


def test_obj_malformed_files_name_the_line():
    cases = [
        ("v 1 2\n", "line 1"),
        ("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 9\n", "line 4"),
        ("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 0 2\n", "line 4"),
        ("v 0 nan 0\n", "line 1"),
        ("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 x\n", "line 4"),
        ("v 0 0 0\nv 1 0 0\nf 1 2\n", "line 3"),
        ("v 0 0 0\nv 1 0 0\nv 0 1 0\nl 1\n", "line 4"),
        ("v 0 0 0\nvt 0 0\nv 1 0 0\nv 0 1 0\nf 1/2 2/3 3\n", "line 5"),
        ("# nothing here\n", "no vertices"),
    ]
    for index, (text, needle) in enumerate(cases):
        path = _write(f"bad_{index}.obj", text)
        _raises_format(lambda p=path: _load("obj", p), needle)


def test_obj_negative_indices_across_blocks():
    text = "v 0 0 0\nv 1 0 0\nv 0 1 0\no A\nf -3 -2 -1\n"
    doc = _load("obj", _write("neg.obj", text))
    assert doc.nodes[0].mesh.polygons == [(0, 1, 2)]


def _stl_binary(coords: np.ndarray) -> bytes:
    dtype = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    records = np.zeros(len(coords), dtype=dtype)
    records["vertices"] = coords
    return b"Quartz test".ljust(80, b" ") + struct.pack("<I", len(coords)) + records.tobytes()


def test_stl_binary_export_size_and_facet_normals():
    doc = _cube_doc()
    path = _export("stl", doc)
    data = _read_bytes(path)
    count = struct.unpack_from("<I", data, 80)[0]
    assert count == 12
    assert len(data) == 84 + 50 * count
    assert not data.startswith(b"solid")
    normal = struct.unpack_from("<3f", data, 84)
    assert np.isclose(np.linalg.norm(normal), 1.0, atol=1e-6)


def test_stl_binary_starting_with_solid_word_is_binary():
    data = bytearray(_read_bytes(_export("stl", _cube_doc())))
    data[0:5] = b"solid"
    assert data.startswith(b"solid")
    mesh = _load("stl", _write("solid_binary.stl", bytes(data))).nodes[0].mesh
    assert len(mesh.polygons) == 12
    assert np.isclose(_volume(mesh), CUBE_VOLUME)


def test_stl_binary_welds_vertices_and_drops_degenerate_facets():
    good = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    flat = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    dup = [(0, 0, 0), (0, 0, 0), (0, 1, 0)]
    coords = np.array([good, flat, dup, [(0, 0, 0), (1, 0, 0), (0, 1, 0)]], dtype=np.float32)
    doc = _load("stl", _write("degenerate.stl", _stl_binary(coords)))
    mesh = doc.nodes[0].mesh
    assert len(mesh.polygons) == 2
    assert len(mesh.points) == 3
    assert len(mesh.points) == len({tuple(p) for p in mesh.points.tolist()})


def test_stl_ascii_several_solids_become_nodes():
    text = (
        "solid First\n"
        "  facet normal 0 0 1\n    outer loop\n      vertex 0 0 0\n      vertex 1 0 0\n"
        "      vertex 0 1 0\n    endloop\n  endfacet\n"
        "endsolid First\n"
        "solid Second\n"
        "  facet normal 0 0 1\r\n    outer loop\r\n      vertex 0 0 0\r\n      vertex 2 0 0\r\n"
        "      vertex 0 2 0\r\n    endloop\r\n  endfacet\r\n"
        "  facet normal 0 0 1\n    outer loop\n      vertex 0 0 0\n      vertex 2 0 0\n"
        "      vertex 0 0 2\n    endloop\n  endfacet\n"
        "endsolid Second\n"
    )
    doc = _load("stl", _write("solids.stl", text))
    assert [n.name for n in doc.nodes] == ["First", "Second"]
    assert len(doc.nodes[0].mesh.polygons) == 1
    assert len(doc.nodes[1].mesh.polygons) == 2
    assert len(doc.nodes[1].mesh.points) == 4


def test_stl_ascii_sample_is_detected_without_size_match():
    text = "solid cube\n" + "".join(
        f"facet normal 0 0 0\nouter loop\nvertex {a} 0 0\nvertex {b} 1 0\nvertex {c} 0 1\nendloop\nendfacet\n"
        for a, b, c in ((0, 1, 0), (2, 3, 2))
    ) + "endsolid cube\n"
    doc = _load("stl", _write("ascii_cube.stl", text))
    assert doc.nodes[0].name == "cube"
    assert len(doc.nodes[0].mesh.polygons) == 2


def test_stl_malformed_files_name_the_line():
    cases = [
        ("solid a\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nendloop\nendfacet\nendsolid a\n", "line 7"),
        ("solid a\nfacet normal 0 0 1\nouter loop\nvertex 0 0 x\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid a\n", "line 4"),
        ("solid a\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\n", "endsolid"),
        ("solid a\nbogus 1 2 3\nendsolid a\n", "line 2"),
        ("facet normal 0 0 1\n", "line 1"),
    ]
    for index, (text, needle) in enumerate(cases):
        path = _write(f"bad_{index}.stl", text)
        _raises_format(lambda p=path: _load("stl", p), needle)
    truncated = _stl_binary(np.zeros((3, 3, 3), dtype=np.float32))[:-20]
    _raises_format(lambda: _load("stl", _write("trunc.stl", truncated)))
    empty = _stl_binary(np.zeros((0, 3, 3), dtype=np.float32))
    _raises_format(lambda: _load("stl", _write("empty.stl", empty)), "no usable facets")


PLY_ASCII = (
    "ply\n"
    "format ascii 1.0\n"
    "comment sample with normals and colours\n"
    "element vertex 5\n"
    "property float x\n"
    "property float y\n"
    "property float z\n"
    "property float nx\n"
    "property float ny\n"
    "property float nz\n"
    "property uchar red\n"
    "property uchar green\n"
    "property uchar blue\n"
    "element face 2\n"
    "property list uchar int vertex_indices\n"
    "end_header\n"
    "0 0 0 0 0 1 255 0 0\n"
    "1 0 0 0 0 1 0 255 0\n"
    "1 1 0 0 0 1 0 0 255\n"
    "0 1 0 0 0 1 9 9 9\n"
    "0.5 0.5 1 0 0 1 1 1 1\n"
    "4 0 1 2 3\n"
    "3 0 1 4\n"
)


def test_ply_ascii_sample_skips_extra_properties_and_keeps_ngons():
    mesh = _load("ply", _write("sample.ply", PLY_ASCII)).nodes[0].mesh
    assert len(mesh.points) == 5
    assert mesh.polygons == [(0, 1, 2, 3), (0, 1, 4)]
    assert np.allclose(mesh.points[4], [0.5, 1.0, -0.5])


def _ply_binary(order: str, points, faces, double: bool, count_code: str, index_code: str) -> bytes:
    prefix = "<" if order == "little" else ">"
    coord = "d" if double else "f"
    coord_type = "double" if double else "float"
    header = (
        "ply\n"
        f"format binary_{order}_endian 1.0\n"
        f"element vertex {len(points)}\n"
        f"property {coord_type} x\n"
        f"property {coord_type} y\n"
        f"property {coord_type} z\n"
        "property uchar red\n"
        f"element face {len(faces)}\n"
        f"property list {'uchar' if count_code == 'B' else 'int'} {'int' if index_code == 'i' else 'uint'} vertex_indices\n"
        "end_header\n"
    ).encode("ascii")
    body = b"".join(struct.pack(prefix + coord * 3 + "B", x, y, z, 77) for x, y, z in points)
    for face in faces:
        body += struct.pack(prefix + count_code + str(len(face)) + index_code, len(face), *face)
    return header + body


def test_ply_binary_little_and_big_endian_with_list_types():
    points = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 3.0, 0.0), (0.0, 3.0, 0.0), (1.0, 1.0, 5.0)]
    faces = [(0, 1, 2, 3), (0, 1, 4)]
    little = _ply_binary("little", points, faces, False, "B", "i")
    y_up = [(x, z, -y) for x, y, z in points]
    mesh = _load("ply", _write("little.ply", little)).nodes[0].mesh
    assert np.allclose(mesh.points, y_up)
    assert mesh.polygons == [(0, 1, 2, 3), (0, 1, 4)]
    big = _ply_binary("big", points, faces, True, "i", "i")
    mesh = _load("ply", _write("big.ply", big)).nodes[0].mesh
    assert np.allclose(mesh.points, y_up)
    assert mesh.polygons == [(0, 1, 2, 3), (0, 1, 4)]


def test_ply_point_cloud_gives_points_only():
    text = "ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n1 2 3\n-1 0.5 2\n"
    doc = _load("ply", _write("cloud.ply", text))
    mesh = doc.nodes[0].mesh
    assert len(mesh.points) == 3 and not mesh.polygons
    assert np.allclose(mesh.points[1], [1, 3, -2])


def test_ply_malformed_files():
    cases = [
        ("not a ply file\n", "line 1"),
        ("ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n", "end_header"),
        ("ply\nformat weird 1.0\nend_header\n", "line 2"),
        ("ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0\n", "line 8"),
        ("ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n1 0 0\n0 1 0\n3 0 1 9\n", "line 13"),
        ("ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nend_header\n0\n", "no y property"),
        ("ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 zz\n", "line 8"),
        ("ply\nformat ascii 1.0\nelement vertex 0\nproperty float x\nproperty float y\nproperty float z\nend_header\n", "no vertices"),
    ]
    for index, (text, needle) in enumerate(cases):
        path = _write(f"bad_{index}.ply", text)
        _raises_format(lambda p=path: _load("ply", p), needle)
    good = _ply_binary("little", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)], False, "B", "i")
    _raises_format(lambda: _load("ply", _write("trunc.ply", good[:-3])), "end of file")
    broken = _ply_binary("little", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 7)], False, "B", "i")
    _raises_format(lambda: _load("ply", _write("range.ply", broken)), "out of range")


def test_unicode_and_spaces_in_path():
    folder = _path("Modelos com acentos ção")
    os.makedirs(folder, exist_ok=True)
    name = os.path.join(folder, "cubo teste ação.obj")
    registry.get("obj").save(name, _cube_doc(), {})
    doc = _load("obj", name)
    assert len(doc.nodes) == 1 and doc.nodes[0].name == "Cube"
    assert np.isclose(_volume(doc.nodes[0].mesh), CUBE_VOLUME)
    stl_name = os.path.join(folder, "peça de teste.stl")
    registry.get("stl").save(stl_name, _cube_doc(), {})
    assert _load("stl", stl_name).nodes[0].name == "peça de teste"


def test_random_damage_raises_only_format_errors():
    rng = random.Random(20261119)
    samples = {
        "obj": (OBJ_SAMPLE.encode("utf-8"), "obj"),
        "stl": (_read_bytes(_export("stl", _cube_doc())), "stl"),
        "ply": (_read_bytes(_export("ply", _cube_doc())), "ply"),
        "ply_binary": (_ply_binary("little", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                                     [(0, 1, 2)], False, "B", "i"), "ply"),
    }
    for label, (sample, fmt_id) in samples.items():
        for _ in range(60):
            data = bytearray(sample)
            for _ in range(rng.randint(1, 6)):
                data[rng.randrange(len(data))] = rng.randrange(256)
            if rng.random() < 0.3:
                data = data[:rng.randrange(len(data))]
            path = _write(f"fuzz_{label}.{fmt_id}", bytes(data))
            try:
                _load(fmt_id, path)
            except FileFormatError:
                pass
    for _ in range(80):
        blob = bytes(rng.randrange(256) for _ in range(rng.randint(0, 300)))
        for fmt_id in ("obj", "stl", "ply"):
            path = _write(f"noise.{fmt_id}", blob)
            try:
                _load(fmt_id, path)
            except FileFormatError:
                pass


def test_hundred_thousand_triangles_are_fast():
    grid = _grid(224)
    assert len(grid.polygons) >= 100000
    doc = Document([Node("Grid", grid)], {"unit": "cm"})
    for fmt_id in ("stl", "obj"):
        started = time.perf_counter()
        path = _export(fmt_id, doc)
        back = _load(fmt_id, path)
        elapsed = time.perf_counter() - started
        assert elapsed < 10.0, (fmt_id, elapsed)
        assert sum(len(n.mesh.polygons) for n in back.nodes) == len(grid.polygons), fmt_id
    stl_path = _export("stl", doc)
    assert os.path.getsize(stl_path) == 84 + 50 * len(grid.polygons)


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
