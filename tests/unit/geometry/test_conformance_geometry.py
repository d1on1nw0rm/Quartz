from __future__ import annotations

import ast
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pytest

import quartz.geometry as G
from quartz.geometry import attributes as A
from quartz.geometry import mesh as M
from quartz.geometry import normals as N
from quartz.geometry import primitives as P
from quartz.geometry import topology as T
from quartz.geometry import transform as X
import importlib
TR = importlib.import_module("quartz.geometry.triangulate")

ROOT = Path(__file__).resolve().parents[3]
FACTS = json.loads((ROOT / "data" / "blender_facts_judge.json").read_text(encoding="utf-8"))
MeshGeometry = G.MeshGeometry

EMPTY = inspect.Parameter.empty
KW = inspect.Parameter.KEYWORD_ONLY


def quad_geo(shade_flat=True):
    return MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (), [(0, 1, 2, 3)], shade_flat=shade_flat
    )


def two_quads():
    verts = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)]
    return MeshGeometry.from_pydata(verts, (), [(0, 1, 4, 3), (1, 2, 5, 4)])


def signed_volume(geo):
    tris, _ = G.triangulate(geo)
    p = geo.positions.astype(np.float64)[geo.corner_verts[tris]]
    return float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6.0)


def params(fn):
    return inspect.signature(fn).parameters



OWNED = sorted((ROOT / "quartz" / "geometry").glob("*.py")) + sorted(
    (ROOT / "tests" / "unit" / "geometry").glob("*.py")
)


@pytest.mark.parametrize("path", OWNED, ids=lambda p: p.name)
def test_no_comments_or_docstrings(path):
    import io
    import tokenize
    src = path.read_text(encoding="utf-8")
    assert not [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT]
    assert not [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]


LIB = sorted((ROOT / "quartz" / "geometry").glob("*.py"))


@pytest.mark.parametrize("path", LIB, ids=lambda p: p.name)
def test_import_group_isolated(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    import sys

    allowed_std = set(sys.stdlib_module_names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in allowed_std or top == "numpy", alias.name
                assert not alias.name.startswith("quartz") or alias.name.startswith("quartz.geometry")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            mod = node.module or ""
            top = mod.split(".")[0]
            if top == "quartz":
                assert mod.startswith("quartz.geometry"), mod
            else:
                assert top in allowed_std or top == "numpy", mod


@pytest.mark.parametrize("path", LIB, ids=lambda p: p.name)
def test_no_print_in_library(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "print"


def test_files_listed_exist():
    for name in ["__init__", "attributes", "mesh", "topology", "normals", "triangulate", "primitives", "transform"]:
        assert (ROOT / "quartz" / "geometry" / f"{name}.py").is_file()



PUBLIC = {
    A: ["DOMAINS", "DATA_TYPES", "REQUIRED_ATTRIBUTES", "default_fill", "AttributeArray", "AttributeStore"],
    M: ["MeshGeometry"],
    T: ["calc_edges", "edge_keys", "face_edge_keys", "loose_edges", "loose_verts", "faces_to_offsets",
        "flip_faces", "join", "merge_by_distance"],
    N: ["face_normals", "vertex_normals", "corner_normals", "face_centers", "face_areas"],
    TR: ["triangulate", "triangulated"],
    P: ["plane", "cube", "circle", "uv_sphere", "ico_sphere", "cylinder", "cone", "grid", "torus"],
    X: ["euler_to_matrix3", "quat_to_matrix3", "matrix3_to_quat", "compose_trs", "decompose_trs",
        "transform_points", "transform_directions", "transform_normals", "bounds", "bound_box"],
}
ALL_PUBLIC = [(mod, name) for mod, names in PUBLIC.items() for name in names]


@pytest.mark.parametrize("mod,name", ALL_PUBLIC, ids=lambda x: x if isinstance(x, str) else x.__name__)
def test_reexported_from_package(mod, name):
    assert hasattr(mod, name)
    assert getattr(G, name) is getattr(mod, name)



def test_domains_exact():
    assert G.DOMAINS == ("POINT", "EDGE", "FACE", "CORNER")
    assert isinstance(G.DOMAINS, tuple)


EXPECTED_TYPES = {
    "FLOAT": (np.float32, ()), "INT": (np.int32, ()), "INT8": (np.int8, ()), "BOOLEAN": (np.bool_, ()),
    "FLOAT_VECTOR": (np.float32, (3,)), "FLOAT2": (np.float32, (2,)), "INT16_2D": (np.int16, (2,)),
    "INT32_2D": (np.int32, (2,)), "FLOAT_COLOR": (np.float32, (4,)), "BYTE_COLOR": (np.uint8, (4,)),
    "QUATERNION": (np.float32, (4,)), "FLOAT4X4": (np.float32, (4, 4)),
}


def test_data_types_keys_exact():
    assert set(G.DATA_TYPES) == set(EXPECTED_TYPES)


@pytest.mark.parametrize("key", sorted(EXPECTED_TYPES))
def test_data_types_entry(key):
    dtype, shape = G.DATA_TYPES[key]
    assert np.dtype(dtype) == np.dtype(EXPECTED_TYPES[key][0])
    assert tuple(shape) == EXPECTED_TYPES[key][1]


def test_required_attributes():
    assert G.REQUIRED_ATTRIBUTES == frozenset({"position", ".edge_verts", ".corner_vert", ".corner_edge"})
    assert isinstance(G.REQUIRED_ATTRIBUTES, frozenset)


@pytest.mark.parametrize("key", sorted(set(EXPECTED_TYPES) - {"QUATERNION", "FLOAT4X4"}))
def test_default_fill_zeros(key):
    value = np.asarray(G.default_fill(key))
    assert np.all(value == 0)
    shape = EXPECTED_TYPES[key][1]
    if shape:
        assert value.shape == shape


def test_default_fill_quaternion():
    assert np.allclose(np.asarray(G.default_fill("QUATERNION"), dtype=float), [1, 0, 0, 0])


def test_default_fill_matrix_identity():
    assert np.allclose(np.asarray(G.default_fill("FLOAT4X4"), dtype=float), np.eye(4))


def test_attribute_array_fields_and_flags():
    arr = G.AttributeArray(".hidden", "POINT", "FLOAT", np.zeros(3, np.float32))
    assert arr.name == ".hidden" and arr.domain == "POINT" and arr.data_type == "FLOAT"
    assert arr.is_internal is True
    assert arr.is_required is False
    pub = G.AttributeArray("position", "POINT", "FLOAT_VECTOR", np.zeros((0, 3), np.float32))
    assert pub.is_internal is False
    assert pub.is_required is True
    for name in [".edge_verts", ".corner_vert", ".corner_edge"]:
        a = G.AttributeArray(name, "EDGE", "INT", np.zeros(0, np.int32))
        assert a.is_required and a.is_internal


def test_attribute_array_is_dataclass():
    import dataclasses

    assert dataclasses.is_dataclass(G.AttributeArray)
    names = [f.name for f in dataclasses.fields(G.AttributeArray)]
    assert names[:4] == ["name", "domain", "data_type", "data"]


def test_attribute_array_copy_deep():
    arr = G.AttributeArray("a", "POINT", "FLOAT", np.arange(3, dtype=np.float32))
    c = arr.copy()
    assert isinstance(c, G.AttributeArray)
    assert c is not arr and c.data is not arr.data
    c.data[0] = 99
    assert arr.data[0] == 0
    assert (c.name, c.domain, c.data_type) == ("a", "POINT", "FLOAT")


def sizes_fn(table=None):
    t = {"POINT": 4, "EDGE": 3, "FACE": 2, "CORNER": 5} if table is None else table
    return lambda d: t[d]


def test_store_signature():
    p = params(G.AttributeStore.__init__)
    assert list(p)[1:] == ["sizes"]
    p = params(G.AttributeStore.new)
    assert list(p)[1:4] == ["name", "data_type", "domain"]
    assert p["fill"].kind == KW and p["fill"].default is None
    p = params(G.AttributeStore.names)
    assert p["domain"].default is None
    assert p["include_internal"].kind == KW and p["include_internal"].default is True


@pytest.mark.parametrize("key", sorted(EXPECTED_TYPES))
@pytest.mark.parametrize("domain", ["POINT", "EDGE", "FACE", "CORNER"])
def test_store_new_shape_dtype(key, domain):
    st = G.AttributeStore(sizes_fn())
    arr = st.new("x", key, domain)
    assert isinstance(arr, G.AttributeArray)
    n = {"POINT": 4, "EDGE": 3, "FACE": 2, "CORNER": 5}[domain]
    assert arr.data.shape == (n, *EXPECTED_TYPES[key][1])
    assert arr.data.dtype == np.dtype(EXPECTED_TYPES[key][0])
    assert arr.domain == domain and arr.data_type == key


def test_store_new_default_fill_values():
    st = G.AttributeStore(sizes_fn())
    q = st.new("q", "QUATERNION", "POINT")
    assert np.allclose(q.data, np.tile([1, 0, 0, 0], (4, 1)))
    m = st.new("m", "FLOAT4X4", "FACE")
    assert np.allclose(m.data, np.broadcast_to(np.eye(4), (2, 4, 4)))
    f = st.new("f", "FLOAT", "EDGE")
    assert np.all(f.data == 0)


def test_store_new_with_fill():
    st = G.AttributeStore(sizes_fn())
    a = st.new("a", "INT", "POINT", fill=7)
    assert np.all(a.data == 7)
    b = st.new("b", "FLOAT_COLOR", "CORNER", fill=(1, 0.5, 0.25, 1))
    assert np.allclose(b.data, np.tile([1, 0.5, 0.25, 1], (5, 1)))


def test_store_float32_at_rest():
    st = G.AttributeStore(sizes_fn())
    a = st.new("a", "FLOAT", "POINT", fill=0.1)
    assert float(a.data[0]) == FACTS["math.float32"] == 0.10000000149011612


def test_store_new_duplicate_name_valueerror():
    st = G.AttributeStore(sizes_fn())
    st.new("a", "FLOAT", "POINT")
    with pytest.raises(ValueError):
        st.new("a", "INT", "EDGE")


def test_store_new_bad_type_valueerror():
    st = G.AttributeStore(sizes_fn())
    with pytest.raises(ValueError):
        st.new("a", "NOPE", "POINT")


def test_store_new_bad_domain_valueerror():
    st = G.AttributeStore(sizes_fn())
    with pytest.raises(ValueError):
        st.new("a", "FLOAT", "VOLUME")


def test_store_get_getitem_contains():
    st = G.AttributeStore(sizes_fn())
    a = st.new("a", "FLOAT", "POINT")
    assert st.get("a") is a
    assert st.get("zz") is None
    assert st["a"] is a
    with pytest.raises(KeyError):
        st["zz"]
    assert "a" in st and "zz" not in st


def test_store_iter_len_insertion_order():
    st = G.AttributeStore(sizes_fn())
    for name in ["c", "a", "b", ".x"]:
        st.new(name, "FLOAT", "POINT")
    assert len(st) == 4
    items = list(st)
    assert all(isinstance(i, G.AttributeArray) for i in items)
    assert [i.name for i in items] == ["c", "a", "b", ".x"]


def test_store_remove():
    st = G.AttributeStore(sizes_fn())
    st.new("a", "FLOAT", "POINT")
    st.remove("a")
    assert "a" not in st and len(st) == 0
    with pytest.raises(KeyError):
        st.remove("a")


@pytest.mark.parametrize("name", sorted({"position", ".edge_verts", ".corner_vert", ".corner_edge"}))
def test_store_remove_required_valueerror(name):
    geo = MeshGeometry()
    with pytest.raises(ValueError):
        geo.attributes.remove(name)
    assert name in geo.attributes


def test_store_rename():
    st = G.AttributeStore(sizes_fn())
    a = st.new("a", "FLOAT", "POINT")
    st.new("b", "FLOAT", "POINT")
    st.rename("a", "z")
    assert "a" not in st and "z" in st
    assert st["z"].name == "z"
    assert st["z"].data is a.data
    with pytest.raises(ValueError):
        st.rename("z", "b")


def test_store_names_filters():
    st = G.AttributeStore(sizes_fn())
    st.new("p", "FLOAT", "POINT")
    st.new(".h", "FLOAT", "POINT")
    st.new("e", "INT", "EDGE")
    assert st.names() == ["p", ".h", "e"]
    assert st.names("POINT") == ["p", ".h"]
    assert st.names("POINT", include_internal=False) == ["p"]
    assert st.names(include_internal=False) == ["p", "e"]
    assert st.names("FACE") == []


def test_store_by_domain():
    st = G.AttributeStore(sizes_fn())
    p = st.new("p", "FLOAT", "POINT")
    e = st.new("e", "INT", "EDGE")
    p2 = st.new("p2", "INT", "POINT")
    assert st.by_domain("POINT") == [p, p2]
    assert st.by_domain("EDGE") == [e]
    assert st.by_domain("CORNER") == []


def test_store_resize_extend_with_default_fill():
    st = G.AttributeStore(sizes_fn())
    q = st.new("q", "QUATERNION", "POINT", fill=(0, 1, 0, 0))
    f = st.new("f", "FLOAT", "POINT", fill=3.0)
    e = st.new("e", "FLOAT", "EDGE", fill=2.0)
    st.resize("POINT", 6)
    assert st["q"].data.shape == (6, 4)
    assert np.allclose(st["q"].data[:4], [0, 1, 0, 0])
    assert np.allclose(st["q"].data[4:], [1, 0, 0, 0])
    assert np.allclose(st["f"].data, [3, 3, 3, 3, 0, 0])
    assert st["f"].data.dtype == np.float32
    assert st["e"].data.shape == (3,)


def test_store_resize_truncate():
    st = G.AttributeStore(sizes_fn())
    st.new("f", "INT", "CORNER", fill=1)
    st.new("g", "FLOAT2", "CORNER")
    st.resize("CORNER", 2)
    assert st["f"].data.shape == (2,)
    assert st["g"].data.shape == (2, 2)
    st.resize("CORNER", 0)
    assert st["f"].data.shape == (0,)


def test_store_unique_name():
    st = G.AttributeStore(sizes_fn())
    assert st.unique_name("Col") == "Col"
    st.new("Col", "FLOAT", "POINT")
    assert st.unique_name("Col") == "Col.001"
    st.new("Col.001", "FLOAT", "POINT")
    assert st.unique_name("Col") == "Col.002"


def test_store_copy_deep_and_new_sizes():
    st = G.AttributeStore(sizes_fn())
    st.new("a", "FLOAT", "POINT", fill=1.0)
    st.new("b", "INT", "EDGE")
    c = st.copy(sizes_fn({"POINT": 10, "EDGE": 10, "FACE": 10, "CORNER": 10}))
    assert isinstance(c, G.AttributeStore)
    assert [x.name for x in c] == ["a", "b"]
    assert c["a"].data is not st["a"].data
    c["a"].data[0] = 5
    assert st["a"].data[0] == 1
    c.new("z", "FLOAT", "POINT")
    assert c["z"].data.shape == (10,)
    assert "z" not in st



def test_mesh_init_empty():
    g = MeshGeometry()
    assert isinstance(g.attributes, G.AttributeStore)
    for name in G.REQUIRED_ATTRIBUTES:
        assert name in g.attributes
        assert g.attributes[name].data.shape[0] == 0
    assert g.face_offsets.tolist() == [0]
    assert g.face_offsets.dtype == np.int32
    assert (g.num_verts, g.num_edges, g.num_faces, g.num_corners) == (0, 0, 0, 0)


def test_mesh_required_attribute_domains_types():
    g = MeshGeometry()
    assert g.attributes["position"].domain == "POINT"
    assert g.attributes["position"].data_type == "FLOAT_VECTOR"
    assert g.attributes[".edge_verts"].domain == "EDGE"
    assert g.attributes[".corner_vert"].domain == "CORNER"
    assert g.attributes[".corner_edge"].domain == "CORNER"


def test_mesh_empty_classmethod():
    g = MeshGeometry.empty()
    assert isinstance(g, MeshGeometry)
    assert g.num_verts == 0 and g.face_offsets.tolist() == [0]


def test_from_pydata_signature():
    p = params(MeshGeometry.from_pydata)
    assert list(p)[:3] == ["vertices", "edges", "faces"]
    assert p["edges"].default == () and p["faces"].default == ()
    assert p["shade_flat"].kind == KW and p["shade_flat"].default is True


def test_from_pydata_quad_counts():
    g = quad_geo()
    assert (g.num_verts, g.num_edges, g.num_corners, g.num_faces) == (4, 4, 4, 1)


def test_from_pydata_positions_float32():
    g = MeshGeometry.from_pydata([(0.1, 0.2, 0.3)])
    assert g.positions.dtype == np.float32
    assert g.positions.shape == (1, 3)
    assert float(g.positions[0, 0]) == 0.10000000149011612


def test_from_pydata_live_views():
    g = quad_geo()
    assert g.positions is g.attributes["position"].data or np.shares_memory(
        g.positions, g.attributes["position"].data)
    g.positions[0, 0] = 5.0
    assert g.attributes["position"].data[0, 0] == 5.0
    g.edges[0, 0] = 3
    assert g.attributes[".edge_verts"].data[0, 0] == 3
    g.corner_verts[0] = 2
    assert g.attributes[".corner_vert"].data[0] == 2
    g.corner_edges[0] = 1
    assert g.attributes[".corner_edge"].data[0] == 1


def test_view_dtypes_shapes():
    g = quad_geo()
    assert g.edges.shape == (4, 2) and g.edges.dtype == np.int32
    assert g.corner_verts.shape == (4,) and g.corner_verts.dtype == np.int32
    assert g.corner_edges.shape == (4,) and g.corner_edges.dtype == np.int32
    assert g.face_offsets.dtype == np.int32


def test_from_pydata_face_offsets_invariants():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0)], (), [(0, 1, 2), (1, 4, 2, 3)])
    assert g.face_offsets.tolist() == [0, 3, 7]
    assert g.face_offsets.shape == (g.num_faces + 1,)
    assert g.face_offsets[-1] == g.num_corners


def test_from_pydata_edge_order_explicit_first():
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (5, 5, 5), (6, 6, 6)]
    g = MeshGeometry.from_pydata(verts, [(4, 5), (2, 1)], [(0, 1, 2, 3)])
    keys = [tuple(sorted(e)) for e in g.edges.tolist()]
    assert keys[0] == (4, 5)
    assert keys[1] == (1, 2)
    assert keys[2:] == [(0, 1), (2, 3), (0, 3)]
    assert g.num_edges == 5


def test_from_pydata_explicit_edges_no_duplicates():
    verts = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    g = MeshGeometry.from_pydata(verts, [(0, 1), (1, 0), (1, 2), (0, 1)])
    assert g.num_edges == 2


def test_from_pydata_face_edges_unoriented_shared():
    g = two_quads()
    assert g.num_edges == 7
    keys = [tuple(sorted(e)) for e in g.edges.tolist()]
    assert keys == [(0, 1), (1, 4), (3, 4), (0, 3), (1, 2), (2, 5), (4, 5)]


def test_from_pydata_corner_edge_computed():
    g = two_quads()
    keys = [tuple(sorted(e)) for e in g.edges.tolist()]
    cv = g.corner_verts.tolist()
    off = g.face_offsets.tolist()
    for f in range(g.num_faces):
        s, e = off[f], off[f + 1]
        for i in range(s, e):
            a, b = cv[i], cv[s + (i - s + 1) % (e - s)]
            assert keys[g.corner_edges[i]] == tuple(sorted((a, b)))


def test_from_pydata_select_and_sharp_attributes():
    g = quad_geo()
    for name, domain in [(".select_vert", "POINT"), (".select_edge", "EDGE"), (".select_poly", "FACE")]:
        a = g.attributes[name]
        assert a.domain == domain and a.data_type == "BOOLEAN"
        assert not a.data.any()
    s = g.attributes["sharp_face"]
    assert s.domain == "FACE" and s.data_type == "BOOLEAN"
    assert s.data.tolist() == [True]


def test_from_pydata_shade_smooth():
    g = quad_geo(shade_flat=False)
    assert g.attributes["sharp_face"].data.tolist() == [False]


def test_from_pydata_face_too_small_valueerror():
    with pytest.raises(ValueError):
        MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], (), [(0, 1)])


def test_from_pydata_face_bad_index_valueerror():
    with pytest.raises(ValueError):
        MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], (), [(0, 1, 7)])


def test_from_pydata_face_negative_index_valueerror():
    with pytest.raises(ValueError):
        MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], (), [(0, 1, -1)])


def test_from_pydata_numpy_input():
    g = MeshGeometry.from_pydata(np.zeros((3, 3)), (), np.array([[0, 1, 2]]))
    assert g.num_faces == 1 and g.num_edges == 3


def test_from_pydata_verts_only():
    g = MeshGeometry.from_pydata([(0, 0, 0), (1, 1, 1)])
    assert (g.num_verts, g.num_edges, g.num_faces, g.num_corners) == (2, 0, 0, 0)
    assert g.face_offsets.tolist() == [0]


def test_from_pydata_validate_clean():
    assert quad_geo().validate() == (False, [])
    assert two_quads().validate() == (False, [])


def test_num_properties_are_int():
    g = two_quads()
    for v in (g.num_verts, g.num_edges, g.num_faces, g.num_corners):
        assert type(v) is int


def test_domain_size():
    g = two_quads()
    assert g.domain_size("POINT") == 6
    assert g.domain_size("EDGE") == 7
    assert g.domain_size("FACE") == 2
    assert g.domain_size("CORNER") == 8


def test_face_sizes_and_corner_to_face():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0)], (), [(0, 1, 2), (1, 4, 2, 3)])
    fs = g.face_sizes()
    assert fs.tolist() == [3, 4] and fs.dtype == np.int32
    cf = g.corner_to_face()
    assert cf.tolist() == [0, 0, 0, 1, 1, 1, 1] and cf.dtype == np.int32


def test_resize_domain_points():
    g = quad_geo()
    g.resize_domain("POINT", 6)
    assert g.num_verts == 6
    assert g.attributes[".select_vert"].data.shape == (6,)
    g.resize_domain("POINT", 2)
    assert g.positions.shape == (2, 3)


def test_add_verts_returns_slice():
    g = quad_geo()
    s = g.add_verts(3)
    assert s == slice(4, 7)
    assert g.num_verts == 7
    assert np.all(g.positions[s] == 0)


def test_add_edges_returns_slice():
    g = quad_geo()
    s = g.add_edges(2)
    assert s == slice(4, 6) and g.num_edges == 6


def test_add_corners_returns_slice():
    g = MeshGeometry()
    s = g.add_corners(5)
    assert s == slice(0, 5) and g.num_corners == 5


def test_add_faces_int_empty_faces():
    g = quad_geo()
    s = g.add_faces(2)
    assert s == slice(1, 3)
    assert g.num_faces == 3
    assert g.face_offsets.tolist() == [0, 4, 4, 4]
    assert g.num_corners == 4
    assert g.attributes["sharp_face"].data.shape == (3,)


def test_add_faces_sequence_adds_corners():
    g = quad_geo()
    s = g.add_faces([3, 4])
    assert s == slice(1, 3)
    assert g.num_faces == 3
    assert g.num_corners == 11
    assert g.face_offsets.tolist() == [0, 4, 7, 11]
    assert g.face_offsets.dtype == np.int32


def test_add_faces_sequence_on_empty():
    g = MeshGeometry()
    g.add_verts(3)
    s = g.add_faces([3])
    assert s == slice(0, 1)
    assert g.face_offsets.tolist() == [0, 3]
    assert g.num_corners == 3


def test_set_face_offsets():
    g = MeshGeometry()
    g.add_corners(7)
    g.set_face_offsets([0, 3])
    assert g.face_offsets.tolist() == [0, 3, 7]
    assert g.num_faces == 2
    assert g.face_offsets.dtype == np.int32


def test_set_face_offsets_numpy():
    g = MeshGeometry()
    g.add_corners(8)
    g.set_face_offsets(np.array([0, 4]))
    assert g.face_offsets.tolist() == [0, 4, 8]


def test_set_face_offsets_decreasing_valueerror():
    g = MeshGeometry()
    g.add_corners(8)
    with pytest.raises(ValueError):
        g.set_face_offsets([0, 5, 3])


def test_copy_deep():
    g = two_quads()
    c = g.copy()
    assert isinstance(c, MeshGeometry)
    assert c.positions is not g.positions
    c.positions[0, 0] = 9
    c.face_offsets[1] = 1
    assert g.positions[0, 0] == 0
    assert g.face_offsets[1] == 4
    assert [a.name for a in c.attributes] == [a.name for a in g.attributes]
    c.add_verts(1)
    assert c.num_verts == 7 and g.num_verts == 6
    assert c.attributes[".select_vert"].data.shape == (7,)


def test_clear():
    g = two_quads()
    g.clear()
    assert (g.num_verts, g.num_edges, g.num_faces, g.num_corners) == (0, 0, 0, 0)
    assert g.face_offsets.tolist() == [0]
    assert "sharp_face" in g.attributes
    assert g.attributes["sharp_face"].data.shape == (0,)


def test_validate_signature():
    p = params(MeshGeometry.validate)
    assert p["fix"].kind == KW and p["fix"].default is False


def test_validate_empty_ok():
    assert MeshGeometry().validate() == (False, [])


def test_validate_returns_tuple_types():
    r = quad_geo().validate()
    assert isinstance(r, tuple) and isinstance(r[0], bool) and isinstance(r[1], list)


def test_validate_detects_corner_index_out_of_range():
    g = quad_geo()
    g.corner_verts[0] = 99
    changed, problems = g.validate()
    assert changed is False and problems


def test_validate_detects_edge_index_out_of_range():
    g = quad_geo()
    g.add_edges(1)
    g.edges[-1] = (0, 99)
    assert g.validate()[1]


def test_validate_detects_degenerate_edge():
    g = quad_geo()
    g.add_edges(1)
    g.edges[-1] = (2, 2)
    assert g.validate()[1]


def test_validate_detects_duplicate_edge():
    g = quad_geo()
    g.add_edges(1)
    g.edges[-1] = (1, 0)
    assert g.validate()[1]


def test_validate_detects_small_face():
    g = quad_geo()
    g.add_faces(1)
    assert g.validate()[1]


def test_validate_detects_inconsistent_corner_edge():
    g = quad_geo()
    g.corner_edges[0] = g.corner_edges[1]
    assert g.validate()[1]


def test_validate_detects_bad_offsets():
    g = quad_geo()
    g.face_offsets = np.array([0, 3], dtype=np.int32)
    assert g.validate()[1]


def test_validate_detects_nonfinite_positions():
    g = quad_geo()
    g.positions[1, 2] = np.nan
    assert g.validate()[1]
    g2 = quad_geo()
    g2.positions[0, 0] = np.inf
    assert g2.validate()[1]


def test_validate_fix_degenerate_and_duplicate_edges():
    g = quad_geo()
    g.add_edges(2)
    g.edges[-2] = (2, 2)
    g.edges[-1] = (1, 0)
    changed, problems = g.validate(fix=True)
    assert changed is True and problems
    assert g.num_edges == 4
    assert g.validate() == (False, [])


def test_validate_fix_corner_edge_recalculated():
    g = quad_geo()
    g.corner_edges[:] = 0
    changed, problems = g.validate(fix=True)
    assert changed and problems
    assert g.validate() == (False, [])


def test_validate_fix_removes_bad_face():
    g = two_quads()
    g.corner_verts[4] = 99
    changed, problems = g.validate(fix=True)
    assert changed and problems
    assert g.num_faces == 1
    assert g.validate() == (False, [])


def test_validate_fix_small_face_removed():
    g = quad_geo()
    g.add_faces(1)
    changed, _ = g.validate(fix=True)
    assert changed
    assert g.num_faces == 1
    assert g.validate() == (False, [])


def test_validate_fix_nonfinite():
    g = quad_geo()
    g.positions[1, 2] = np.nan
    changed, _ = g.validate(fix=True)
    assert changed
    assert np.isfinite(g.positions).all()
    assert g.validate() == (False, [])


def test_validate_no_fix_does_not_modify():
    g = quad_geo()
    g.add_edges(1)
    g.edges[-1] = (2, 2)
    before = g.edges.copy()
    g.validate()
    assert np.array_equal(g.edges, before)



def test_calc_edges_signature():
    p = params(G.calc_edges)
    assert p["keep_existing"].kind == KW and p["keep_existing"].default is True


def test_calc_edges_rebuilds_from_faces():
    g = MeshGeometry()
    g.add_verts(4)
    g.add_faces([4])
    g.corner_verts[:] = [0, 1, 2, 3]
    assert g.num_edges == 0
    G.calc_edges(g)
    assert g.num_edges == 4
    assert g.validate() == (False, [])


def test_calc_edges_keep_existing_true_keeps_loose():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (5, 5, 5)], [(3, 4)], [(0, 1, 2, 3)])
    G.calc_edges(g, keep_existing=True)
    keys = {tuple(sorted(e)) for e in g.edges.tolist()}
    assert (3, 4) in keys and g.num_edges == 5
    assert g.validate() == (False, [])


def test_calc_edges_keep_existing_false_drops_loose():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (5, 5, 5)], [(3, 4)], [(0, 1, 2, 3)])
    G.calc_edges(g, keep_existing=False)
    keys = {tuple(sorted(e)) for e in g.edges.tolist()}
    assert (3, 4) not in keys and g.num_edges == 4
    assert g.validate() == (False, [])


def test_edge_keys():
    k = G.edge_keys(np.array([[3, 1], [0, 2], [5, 5]], dtype=np.int32))
    assert k.shape == (3, 2)
    assert k.tolist() == [[1, 3], [0, 2], [5, 5]]


def test_face_edge_keys_quad_observed():
    g = quad_geo()
    assert G.face_edge_keys(g, 0) == [(0, 1), (1, 2), (2, 3), (0, 3)]


def test_face_edge_keys_factory_cube():
    cube = FACTS["factory"]
    g = MeshGeometry.from_pydata(cube["cube_verts"], (), cube["cube_faces"])
    assert g.num_edges == 12
    assert G.face_edge_keys(g, 0) == [(0, 4), (4, 6), (2, 6), (0, 2)]
    assert {tuple(sorted(e)) for e in g.edges.tolist()} == {tuple(sorted(e)) for e in cube["cube_edges"]}


def test_face_edge_keys_returns_python_tuples():
    out = G.face_edge_keys(quad_geo(), 0)
    assert all(type(t) is tuple and all(type(v) is int for v in t) for t in out)


def test_loose_edges():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (5, 5, 5)], [(3, 4)], [(0, 1, 2, 3)])
    le = G.loose_edges(g)
    assert le.dtype == np.bool_ and le.shape == (5,)
    assert le.tolist() == [True, False, False, False, False]


def test_loose_verts():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (5, 5, 5), (6, 6, 6)], [(3, 4)], [(0, 1, 2, 3)])
    lv = G.loose_verts(g)
    assert lv.dtype == np.bool_ and lv.shape == (6,)
    assert lv.tolist() == [False, False, False, False, False, True]


def test_faces_to_offsets():
    off, cv = G.faces_to_offsets([(0, 1, 2), (2, 3, 4, 5)])
    assert off.tolist() == [0, 3, 7]
    assert cv.tolist() == [0, 1, 2, 2, 3, 4, 5]


def test_faces_to_offsets_empty():
    off, cv = G.faces_to_offsets([])
    assert off.tolist() == [0]
    assert cv.shape == (0,)


def test_flip_faces_keeps_first_corner():
    g = quad_geo()
    G.flip_faces(g)
    assert g.corner_verts.tolist() == [0, 3, 2, 1]
    assert g.validate() == (False, [])


def test_flip_faces_flips_normal():
    g = quad_geo()
    G.flip_faces(g)
    assert np.allclose(G.face_normals(g)[0], [0, 0, -1])


def test_flip_faces_mask():
    g = two_quads()
    G.flip_faces(g, np.array([False, True]))
    assert g.corner_verts[:4].tolist() == [0, 1, 4, 3]
    assert g.corner_verts[4:].tolist() == [1, 4, 5, 2]
    assert g.validate() == (False, [])


def test_flip_faces_signature():
    assert params(G.flip_faces)["mask"].default is None


def test_join_counts_and_offsets():
    a = quad_geo()
    b = two_quads()
    j = G.join([a, b])
    assert isinstance(j, MeshGeometry)
    assert (j.num_verts, j.num_edges, j.num_faces, j.num_corners) == (10, 11, 3, 12)
    assert j.face_offsets.tolist() == [0, 4, 8, 12]
    assert j.corner_verts[4:8].tolist() == [4, 5, 8, 7]
    assert j.validate() == (False, [])


def test_join_matrices():
    a = quad_geo()
    m = np.eye(4)
    m[:3, 3] = (10, 0, 0)
    j = G.join([a, a], [np.eye(4), m])
    assert np.allclose(j.positions[4:], a.positions + [10, 0, 0])
    assert j.positions.dtype == np.float32


def test_join_does_not_modify_inputs():
    a = quad_geo()
    before = a.positions.copy()
    G.join([a, a], [np.eye(4), np.eye(4) * 2])
    assert np.array_equal(a.positions, before)


def test_join_signature():
    assert params(G.join)["matrices"].default is None


def test_merge_by_distance_map():
    g = MeshGeometry.from_pydata([(0, 0, 0), (0.0001, 0, 0), (1, 0, 0), (1, 0.00001, 0)])
    before = g.positions.copy()
    mp = G.merge_by_distance(g, 0.001)
    assert mp.shape == (4,)
    assert mp[0] == mp[1] and mp[2] == mp[3] and mp[0] != mp[2]
    assert sorted(set(mp.tolist())) == [0, 1]
    assert g.num_verts == 4 and np.array_equal(g.positions, before)


def test_merge_by_distance_none_merged():
    g = MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    assert G.merge_by_distance(g, 0.1).tolist() == [0, 1, 2]



def test_face_normals_quad():
    n = G.face_normals(quad_geo())
    assert n.shape == (1, 3) and n.dtype == np.float32
    assert np.allclose(n[0], [0, 0, 1])


def test_face_normals_newell_nonplanar_normalized():
    g = MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0.1), (1, 1, 0), (0, 1, 0.1)], (), [(0, 1, 2, 3)])
    n = G.face_normals(g)[0]
    assert math.isclose(float(np.linalg.norm(n)), 1.0, rel_tol=1e-5)
    assert n[2] > 0.9


def test_face_normals_degenerate_zero():
    g = MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0)], (), [(0, 1, 2)])
    assert np.array_equal(G.face_normals(g)[0], [0, 0, 0])


def test_face_normals_cube_outward():
    g = G.cube()
    n = G.face_normals(g)
    c = G.face_centers(g)
    assert np.all(np.einsum("ij,ij->i", n, c) > 0)


def test_vertex_normals_shape_dtype_normalized():
    g = G.cube()
    vn = G.vertex_normals(g)
    assert vn.shape == (8, 3) and vn.dtype == np.float32
    assert np.allclose(np.linalg.norm(vn, axis=1), 1, atol=1e-5)
    p = g.positions / np.linalg.norm(g.positions, axis=1)[:, None]
    assert np.allclose(vn, p, atol=1e-5)


def test_vertex_normals_angle_weighted():
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (1, 0, 1), (1, 1, 1)]
    g = MeshGeometry.from_pydata(verts, (), [(0, 1, 2, 3), (1, 2, 5)])
    vn = G.vertex_normals(g)[1].astype(np.float64)
    fn = G.face_normals(g).astype(np.float64)
    w = fn[0] * (math.pi / 2) + fn[1] * (math.pi / 2)
    w = fn[0] * (math.pi / 2) + fn[1] * (math.pi / 4)
    w /= np.linalg.norm(w)
    assert np.allclose(vn, w, atol=1e-5)


def test_vertex_normals_loose_vertex_normalized_position():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 3, 4)], (), [(0, 1, 2)])
    vn = G.vertex_normals(g)
    assert np.allclose(vn[3], [0, 0.6, 0.8], atol=1e-6)


def test_corner_normals_flat_uses_face_normal():
    g = G.cube()
    cn = G.corner_normals(g)
    assert cn.shape == (24, 3)
    fn = G.face_normals(g)
    assert np.allclose(cn, fn[g.corner_to_face()], atol=1e-6)


def test_corner_normals_smooth_uses_vertex_normal():
    g = G.cube()
    cn = G.corner_normals(g, sharp_face=np.zeros(6, dtype=bool))
    vn = G.vertex_normals(g)
    assert np.allclose(cn, vn[g.corner_verts], atol=1e-6)


def test_corner_normals_from_attribute():
    g = G.cube()
    g.attributes["sharp_face"].data[:] = False
    cn = G.corner_normals(g)
    assert np.allclose(cn, G.vertex_normals(g)[g.corner_verts], atol=1e-6)


def test_corner_normals_signature():
    p = params(G.corner_normals)
    assert p["sharp_face"].kind == KW and p["sharp_face"].default is None


def test_face_centers():
    g = two_quads()
    c = G.face_centers(g)
    assert c.shape == (2, 3)
    assert np.allclose(c, [[0.5, 0.5, 0], [1.5, 0.5, 0]])


def test_face_areas():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (2, 0, 0), (2, 3, 0), (0, 3, 0), (0, 0, 1)], (), [(0, 1, 2, 3), (0, 1, 4)])
    a = G.face_areas(g)
    assert a.shape == (2,)
    assert np.allclose(a, [6.0, 1.0])



def test_triangulate_triangle():
    g = MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], (), [(0, 1, 2)])
    tris, tf = G.triangulate(g)
    assert tris.shape == (1, 3) and tf.shape == (1,)
    assert sorted(tris[0].tolist()) == [0, 1, 2]


def test_triangulate_quad_shortest_diagonal_02():
    g = MeshGeometry.from_pydata([(0, 0, 0), (2, -1, 0), (1, 0, 0), (-1, 2, 0)], (), [(0, 1, 2, 3)])
    tris, tf = G.triangulate(g)
    assert tris.shape == (2, 3) and tf.tolist() == [0, 0]
    for t in tris.tolist():
        assert 0 in t and 2 in t


def test_triangulate_quad_shortest_diagonal_13():
    g = MeshGeometry.from_pydata([(-1, 0, 0), (0, -0.2, 0), (1, 0, 0), (0, 0.2, 0)], (), [(0, 1, 2, 3)])
    tris, _ = G.triangulate(g)
    for t in tris.tolist():
        assert 1 in t and 3 in t


def test_triangulate_returns_corner_indices():
    g = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0)], (), [(1, 4, 2), (3, 0, 1, 2)])
    tris, tf = G.triangulate(g)
    assert tris.max() < g.num_corners
    for t, f in zip(tris.tolist(), tf.tolist()):
        s, e = int(g.face_offsets[f]), int(g.face_offsets[f + 1])
        assert all(s <= c < e for c in t)
    assert sorted(tf.tolist()) == [0, 1, 1]


def test_triangulate_ngon_convex_count_and_area():
    n = 7
    verts = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0) for i in range(n)]
    g = MeshGeometry.from_pydata(verts, (), [list(range(n))])
    tris, tf = G.triangulate(g)
    assert tris.shape == (n - 2, 3)
    p = g.positions.astype(float)[g.corner_verts[tris]]
    area = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum()
    assert math.isclose(area, float(G.face_areas(g)[0]), rel_tol=1e-5)


def test_triangulate_concave_ngon_ear_clipping():
    pts2 = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
    verts = [(0, x, y) for x, y in pts2]
    g = MeshGeometry.from_pydata(verts, (), [list(range(6))])
    tris, _ = G.triangulate(g)
    assert tris.shape == (4, 3)
    p = g.positions.astype(float)[g.corner_verts[tris]]
    cr = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    area = 0.5 * np.linalg.norm(cr, axis=1).sum()
    assert math.isclose(area, 3.0, rel_tol=1e-6)
    fn = G.face_normals(g)[0]
    assert np.all(cr @ fn > 0)


def test_triangulate_preserves_winding():
    g = G.cube()
    tris, tf = G.triangulate(g)
    p = g.positions.astype(float)[g.corner_verts[tris]]
    cr = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    fn = G.face_normals(g).astype(float)[tf]
    assert np.all(np.einsum("ij,ij->i", cr, fn) > 0)


def test_triangulated_geometry():
    g = two_quads()
    g.attributes.new("w", "FLOAT", "POINT", fill=2.0)
    uv = g.attributes.new("uv", "FLOAT2", "CORNER")
    uv.data[:] = np.arange(16, dtype=np.float32).reshape(8, 2)
    g.attributes.new("fid", "INT", "FACE").data[:] = [10, 20]
    t = G.triangulated(g)
    assert isinstance(t, MeshGeometry)
    assert t.num_faces == 4 and t.num_corners == 12
    assert np.all(t.face_sizes() == 3)
    assert t.num_verts == 6
    assert t.validate() == (False, [])
    assert np.all(t.attributes["w"].data == 2.0)
    assert t.attributes["uv"].domain == "CORNER"
    assert t.attributes["uv"].data.shape == (12, 2)
    assert sorted(t.attributes["fid"].data.tolist()) == [10, 10, 20, 20]
    tris, tf = G.triangulate(g)
    assert np.array_equal(t.attributes["uv"].data, uv.data[tris.reshape(-1)])
    assert np.array_equal(t.attributes["fid"].data, np.array([10, 20])[tf])


def test_triangulated_does_not_modify_source():
    g = two_quads()
    G.triangulated(g)
    assert g.num_faces == 2



PRIM_SIGS = {
    "plane": [("size", 2.0)],
    "cube": [("size", 2.0)],
    "circle": [("vertices", 32), ("radius", 1.0), ("fill_type", "NOTHING")],
    "uv_sphere": [("segments", 32), ("ring_count", 16), ("radius", 1.0)],
    "ico_sphere": [("subdivisions", 2), ("radius", 1.0)],
    "cylinder": [("vertices", 32), ("radius", 1.0), ("depth", 2.0), ("end_fill_type", "NGON")],
    "cone": [("vertices", 32), ("radius1", 1.0), ("radius2", 0.0), ("depth", 2.0), ("end_fill_type", "NGON")],
    "grid": [("x_subdivisions", 10), ("y_subdivisions", 10), ("size", 2.0)],
    "torus": [("major_segments", 48), ("minor_segments", 12), ("major_radius", 1.0), ("minor_radius", 0.25)],
}


@pytest.mark.parametrize("name", sorted(PRIM_SIGS))
def test_primitive_signature(name):
    p = params(getattr(G, name))
    positional = [(k, v.default) for k, v in p.items() if v.kind != KW]
    assert positional == PRIM_SIGS[name]
    for k, v in positional:
        assert type(dict(positional)[k]) is type(v)
    assert p["calc_uvs"].kind == KW and p["calc_uvs"].default is True


COUNTS = {
    "plane": (4, 4, 1, 4), "cube": (8, 12, 6, 24), "circle": (32, 32, 0, 0),
    "uv_sphere": (482, 992, 512, 1984), "ico_sphere": (42, 120, 80, 240),
    "cylinder": (64, 96, 34, 192), "cone": (33, 64, 33, 128), "grid": (121, 220, 100, 400),
    "torus": (576, 1152, 576, 2304),
}


def counts(g):
    return (g.num_verts, g.num_edges, g.num_faces, g.num_corners)


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_default_counts(name):
    assert counts(getattr(G, name)()) == COUNTS[name]


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_counts_match_judge_facts(name):
    f = FACTS["primitives"][name]
    assert counts(getattr(G, name)()) == (f["v"], f["e"], f["f"], f["l"])


BOXES = {
    "plane": ((-1, -1, 0), (1, 1, 0)), "cube": ((-1, -1, -1), (1, 1, 1)),
    "circle": ((-1, -1, 0), (1, 1, 0)), "uv_sphere": ((-1, -1, -1), (1, 1, 1)),
    "cylinder": ((-1, -1, -1), (1, 1, 1)), "cone": ((-1, -1, -1), (1, 1, 1)),
    "grid": ((-1, -1, 0), (1, 1, 0)), "torus": ((-1.25, -1.25, -0.25), (1.25, 1.25, 0.25)),
}


@pytest.mark.parametrize("name", sorted(BOXES))
def test_primitive_bbox(name):
    g = getattr(G, name)()
    lo, hi = G.bounds(g.positions)
    assert np.allclose(lo, BOXES[name][0], atol=1e-5)
    assert np.allclose(hi, BOXES[name][1], atol=1e-5)


@pytest.mark.parametrize("name", sorted(BOXES))
def test_primitive_bbox_judge(name):
    g = getattr(G, name)()
    lo, hi = G.bounds(g.positions)
    box = FACTS["primitives"][name]["bbox"]
    assert np.allclose(lo, box[0], atol=2e-5)
    assert np.allclose(hi, box[1], atol=2e-5)


def test_ico_sphere_inside_unit_sphere():
    for sub in (1, 2, 3):
        g = G.ico_sphere(sub)
        r = np.linalg.norm(g.positions.astype(float), axis=1)
        assert np.all(r <= 1 + 1e-5)


def test_uv_sphere_poles_on_z():
    g = G.uv_sphere()
    p = g.positions.astype(float)
    assert np.any(np.all(np.isclose(p, [0, 0, 1], atol=1e-6), axis=1))
    assert np.any(np.all(np.isclose(p, [0, 0, -1], atol=1e-6), axis=1))


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_returns_meshgeometry_valid(name):
    g = getattr(G, name)()
    assert isinstance(g, MeshGeometry)
    assert g.validate() == (False, [])


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_positions_float32(name):
    assert getattr(G, name)().positions.dtype == np.float32


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_sharp_face_true(name):
    g = getattr(G, name)()
    s = g.attributes["sharp_face"]
    assert s.domain == "FACE" and s.data_type == "BOOLEAN"
    assert s.data.shape == (g.num_faces,)
    assert bool(np.all(s.data))


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_uvmap(name):
    g = getattr(G, name)()
    uv = g.attributes["UVMap"]
    assert uv.domain == "CORNER" and uv.data_type == "FLOAT2"
    assert uv.data.shape == (g.num_corners, 2)
    assert uv.data.dtype == np.float32
    if uv.data.size:
        assert uv.data.min() >= -1e-6 and uv.data.max() <= 1 + 1e-6


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_no_uvs(name):
    g = getattr(G, name)(calc_uvs=False)
    assert "UVMap" not in g.attributes
    assert counts(g) == COUNTS[name]


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_centered(name):
    g = getattr(G, name)()
    lo, hi = G.bounds(g.positions)
    assert np.allclose((lo + hi) / 2, 0, atol=1e-5)


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_primitive_deterministic(name):
    a, b = getattr(G, name)(), getattr(G, name)()
    assert np.array_equal(a.positions, b.positions)
    assert np.array_equal(a.corner_verts, b.corner_verts)


@pytest.mark.parametrize("name", ["cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "torus"])
def test_closed_primitive_faces_outward(name):
    g = getattr(G, name)()
    assert signed_volume(g) > 0


@pytest.mark.parametrize("name", ["cube", "uv_sphere", "ico_sphere", "cylinder", "cone"])
def test_convex_primitive_normals_outward(name):
    g = getattr(G, name)()
    n = G.face_normals(g).astype(float)
    c = G.face_centers(g).astype(float)
    assert np.all(np.einsum("ij,ij->i", n, c) > 0)


@pytest.mark.parametrize("name,kw", [("plane", {}), ("grid", {}), ("circle", {"fill_type": "NGON"}),
                                     ("circle", {"fill_type": "TRIFAN"})])
def test_flat_primitive_z_up(name, kw):
    g = getattr(G, name)(**kw)
    n = G.face_normals(g)
    assert np.allclose(n, [0, 0, 1], atol=1e-6)


@pytest.mark.parametrize("name", ["cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "torus"])
def test_closed_primitive_manifold(name):
    g = getattr(G, name)()
    use = np.bincount(g.corner_edges, minlength=g.num_edges)
    assert np.all(use == 2)


def test_circle_ngon_counts():
    assert counts(G.circle(fill_type="NGON")) == (32, 32, 1, 32)


def test_circle_trifan_counts():
    assert counts(G.circle(fill_type="TRIFAN")) == (33, 64, 32, 96)


def test_circle_nothing_edges_loop():
    g = G.circle()
    assert np.all(np.bincount(g.edges.reshape(-1), minlength=32) == 2)
    assert np.allclose(np.linalg.norm(g.positions[:, :2], axis=1), 1, atol=1e-6)


def test_ico_sphere_subdivisions_1():
    assert counts(G.ico_sphere(subdivisions=1)) == (12, 30, 20, 60)


def test_cylinder_nothing_counts():
    g = G.cylinder(end_fill_type="NOTHING")
    assert (g.num_faces, g.num_corners) == (32, 128)
    assert g.num_verts == 64


def test_cylinder_trifan_counts():
    assert counts(G.cylinder(end_fill_type="TRIFAN")) == (66, 160, 96, 320)


def test_cone_radius2_positive_like_cylinder():
    g = G.cone(radius2=0.5)
    assert g.num_verts == 64
    c = G.cylinder()
    assert counts(g) == counts(c)


def test_grid_formula():
    g = G.grid(x_subdivisions=3, y_subdivisions=5)
    assert g.num_verts == 4 * 6
    assert g.num_faces == 15


def test_primitive_sizes_scale():
    g = G.cube(size=4.0)
    lo, hi = G.bounds(g.positions)
    assert np.allclose(lo, -2) and np.allclose(hi, 2)
    p = G.plane(size=1.0)
    lo, hi = G.bounds(p.positions)
    assert np.allclose(hi, [0.5, 0.5, 0])
    s = G.uv_sphere(radius=3.0)
    assert np.allclose(np.linalg.norm(s.positions, axis=1), 3, atol=1e-5)


@pytest.mark.parametrize("call", [
    lambda: G.circle(vertices=2),
    lambda: G.cylinder(vertices=2),
    lambda: G.cone(vertices=2),
    lambda: G.circle(fill_type="BOGUS"),
    lambda: G.cylinder(end_fill_type="BOGUS"),
    lambda: G.cone(end_fill_type="BOGUS"),
    lambda: G.uv_sphere(segments=2),
], ids=["circle_v2", "cyl_v2", "cone_v2", "circle_fill", "cyl_fill", "cone_fill", "uvs_seg2"])
def test_primitive_invalid_valueerror(call):
    with pytest.raises(ValueError):
        call()



def test_transform_signatures():
    assert list(params(G.euler_to_matrix3)) == ["angles", "order"]
    assert params(G.euler_to_matrix3)["order"].default == "XYZ"
    assert list(params(G.quat_to_matrix3)) == ["q"]
    assert list(params(G.matrix3_to_quat)) == ["m"]
    assert list(params(G.compose_trs)) == ["location", "rotation3", "scale"]
    assert list(params(G.decompose_trs)) == ["m4"]
    assert list(params(G.transform_points)) == ["points", "m4"]
    assert list(params(G.transform_normals)) == ["normals", "m4"]
    assert list(params(G.bounds)) == ["points"]
    assert list(params(G.bound_box)) == ["points"]


def test_transform_directions_signature():
    p = params(G.transform_directions)
    assert list(p) == ["dirs", "m4", "normalize"]
    assert p["normalize"].kind == KW and p["normalize"].default is False


def test_euler_xyz_observed():
    m = G.euler_to_matrix3((0.1, 0.2, 0.3), "XYZ")
    assert m.shape == (3, 3) and m.dtype == np.float64
    assert np.allclose(m, FACTS["math.euler_xyz"], atol=1e-6)


def test_euler_default_order_xyz():
    assert np.allclose(G.euler_to_matrix3((0.1, 0.2, 0.3)), FACTS["math.euler_xyz"], atol=1e-6)


def test_euler_zyx_observed():
    m = G.euler_to_matrix3((0.1, 0.2, 0.3), "ZYX")
    assert np.allclose(m, FACTS["math.euler_zyx"], atol=1e-6)


def _r(axis, a):
    c, s = math.cos(a), math.sin(a)
    return {"X": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]),
            "Y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "Z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


@pytest.mark.parametrize("order", ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"])
def test_euler_all_orders_application_order(order):
    ang = dict(zip("XYZ", (0.3, -0.7, 1.1)))
    exp = _r(order[2], ang[order[2]]) @ _r(order[1], ang[order[1]]) @ _r(order[0], ang[order[0]])
    assert np.allclose(G.euler_to_matrix3((0.3, -0.7, 1.1), order), exp)


def test_rot_z_observed():
    assert np.allclose(G.euler_to_matrix3((0, 0, math.pi / 2)), FACTS["math.rot_z"], atol=1e-12)


def test_quat_from_euler_observed():
    q = G.matrix3_to_quat(G.euler_to_matrix3((0.1, 0.2, 0.3)))
    assert q.shape == (4,)
    exp = np.array(FACTS["math.quat_from_euler"])
    assert np.allclose(q, exp, atol=1e-6) or np.allclose(q, -exp, atol=1e-6)


def test_quat_to_matrix3_wxyz():
    q = FACTS["math.quat_axis_angle"]
    m = G.quat_to_matrix3(q)
    assert m.shape == (3, 3)
    assert np.allclose(m, FACTS["math.rot_z"], atol=1e-5)


def test_quat_to_matrix3_identity():
    assert np.allclose(G.quat_to_matrix3((1, 0, 0, 0)), np.eye(3))


def test_quat_roundtrip():
    rng = np.random.default_rng(1)
    for _ in range(20):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        q2 = G.matrix3_to_quat(G.quat_to_matrix3(q))
        assert np.allclose(q2, q, atol=1e-9) or np.allclose(q2, -q, atol=1e-9)


@pytest.mark.parametrize("m", [np.diag([1, -1, -1]), np.diag([-1, 1, -1]), np.diag([-1, -1, 1])],
                         ids=["x180", "y180", "z180"])
def test_matrix3_to_quat_180(m):
    q = G.matrix3_to_quat(m)
    assert np.allclose(G.quat_to_matrix3(q), m, atol=1e-9)


def test_compose_trs():
    R = G.euler_to_matrix3((0.1, 0.2, 0.3))
    m = G.compose_trs((1, 2, 3), R, (2, 3, 4))
    assert m.shape == (4, 4) and m.dtype == np.float64
    Tm = np.eye(4); Tm[:3, 3] = (1, 2, 3)
    Rm = np.eye(4); Rm[:3, :3] = R
    Sm = np.diag([2, 3, 4, 1.0])
    assert np.allclose(m, Tm @ Rm @ Sm)


def test_decompose_trs_observed():
    R = G.euler_to_matrix3((0.1, 0.2, 0.3))
    m = G.compose_trs((1, 2, 3), R, (2, 2, 2))
    loc, q, s = G.decompose_trs(m)
    exp = FACTS["math.decompose"]
    assert loc.shape == (3,) and q.shape == (4,) and s.shape == (3,)
    assert np.allclose(loc, exp[0], atol=1e-6)
    assert np.allclose(q, exp[1], atol=1e-6) or np.allclose(q, -np.array(exp[1]), atol=1e-6)
    assert np.allclose(s, exp[2], atol=1e-6)


def test_decompose_trs_negative_det_negates_all_scales():
    m = G.compose_trs((0, 0, 0), np.eye(3), (-2, 3, 4))
    loc, q, s = G.decompose_trs(m)
    assert np.allclose(s, [-2, -3, -4])
    rebuilt = G.compose_trs(loc, G.quat_to_matrix3(q), s)
    assert np.allclose(rebuilt, m, atol=1e-9)


def test_transform_points_and_dtype():
    m = G.compose_trs((1, 0, 0), np.eye(3), (2, 2, 2))
    p32 = np.array([[1, 1, 1]], dtype=np.float32)
    out = G.transform_points(p32, m)
    assert out.dtype == np.float32 and out.shape == (1, 3)
    assert np.allclose(out, [[3, 2, 2]])
    p64 = np.array([[1, 1, 1]], dtype=np.float64)
    assert G.transform_points(p64, m).dtype == np.float64


def test_transform_points_does_not_mutate_input():
    p = np.array([[1, 2, 3]], dtype=np.float32)
    G.transform_points(p, G.compose_trs((5, 5, 5), np.eye(3), (1, 1, 1)))
    assert p.tolist() == [[1, 2, 3]]


def test_transform_directions_ignores_translation():
    m = G.compose_trs((10, 10, 10), np.eye(3), (2, 1, 1))
    d = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float64)
    assert np.allclose(G.transform_directions(d, m), [[2, 0, 0], [0, 1, 0]])
    assert np.allclose(G.transform_directions(d, m, normalize=True), [[1, 0, 0], [0, 1, 0]])


def test_transform_directions_dtype():
    m = G.compose_trs((0, 0, 0), np.eye(3), (2, 1, 1))
    d = np.array([[1, 0, 0]], dtype=np.float32)
    assert G.transform_directions(d, m).dtype == np.float32


def test_transform_normals_inverse_transpose():
    m = G.compose_trs((5, 0, 0), np.eye(3), (1, 2, 1))
    n = np.array([[1, 1, 0]], dtype=np.float64) / math.sqrt(2)
    out = G.transform_normals(n, m)
    exp = np.array([2, 1, 0]) / math.sqrt(5)
    assert np.allclose(out[0], exp)
    assert math.isclose(float(np.linalg.norm(out[0])), 1.0)


def test_bounds():
    lo, hi = G.bounds(np.array([[1, -2, 3], [-1, 5, 0]], dtype=np.float32))
    assert np.allclose(lo, [-1, -2, 0]) and np.allclose(hi, [1, 5, 3])


def test_bounds_empty_zeros():
    lo, hi = G.bounds(np.zeros((0, 3)))
    assert np.array_equal(lo, [0, 0, 0]) and np.array_equal(hi, [0, 0, 0])
    assert lo.shape == (3,) and hi.shape == (3,)


def test_bound_box_order():
    bb = G.bound_box(np.array([[0, 0, 0], [1, 2, 3]], dtype=np.float32))
    assert bb.shape == (8, 3)
    exp = [(0, 0, 0), (0, 0, 3), (0, 2, 3), (0, 2, 0), (1, 0, 0), (1, 0, 3), (1, 2, 3), (1, 2, 0)]
    assert np.allclose(bb, exp)


def test_bound_box_empty():
    bb = G.bound_box(np.zeros((0, 3)))
    assert bb.shape == (8, 3) and np.all(bb == 0)


def test_euler_invalid_order_valueerror():
    with pytest.raises(ValueError):
        G.euler_to_matrix3((0, 0, 0), "XXY")



def test_mesh_attribute_store_sized_by_geometry():
    g = two_quads()
    a = g.attributes.new("f", "FLOAT", "FACE")
    c = g.attributes.new("c", "FLOAT2", "CORNER")
    e = g.attributes.new("e", "INT", "EDGE")
    assert a.data.shape == (2,) and c.data.shape == (8, 2) and e.data.shape == (7,)


def test_mesh_resize_domain_resizes_all_domain_attributes():
    g = two_quads()
    g.attributes.new("c", "FLOAT2", "CORNER")
    g.resize_domain("EDGE", 9)
    assert g.attributes[".select_edge"].data.shape == (9,)
    g.add_faces(1)
    assert g.attributes[".select_poly"].data.shape == (3,)


def test_validate_detects_corner_edge_out_of_range():
    g = quad_geo()
    g.corner_edges[0] = 99
    assert g.validate()[1]


def test_validate_fix_removes_face_with_its_face_attribute_row():
    g = two_quads()
    g.attributes["sharp_face"].data[:] = [True, False]
    g.corner_verts[1] = 99
    g.validate(fix=True)
    assert g.num_faces == 1
    assert g.attributes["sharp_face"].data.tolist() == [False]


def test_validate_fix_removes_face_with_its_corner_attribute_rows():
    g = two_quads()
    uv = g.attributes.new("uv", "FLOAT2", "CORNER")
    uv.data[:] = np.arange(16, dtype=np.float32).reshape(8, 2)
    g.corner_verts[1] = 99
    g.validate(fix=True)
    assert g.num_corners == 4
    assert g.attributes["uv"].data.tolist() == np.arange(8, 16, dtype=np.float32).reshape(4, 2).tolist()


def test_from_pydata_int_vertices_float32():
    g = MeshGeometry.from_pydata([(0, 0, 0), (1, 2, 3)])
    assert g.positions.dtype == np.float32
    assert g.positions[1].tolist() == [1.0, 2.0, 3.0]


@pytest.mark.parametrize("call", [
    lambda: G.circle(radius=-1.0),
    lambda: G.ico_sphere(subdivisions=0),
    lambda: G.torus(major_segments=2),
    lambda: G.grid(x_subdivisions=0),
], ids=["circle_r", "ico_0", "torus_2", "grid_0"])
def test_primitive_more_invalid_valueerror(call):
    with pytest.raises(ValueError):
        call()


def test_join_empty_list():
    j = G.join([])
    assert isinstance(j, MeshGeometry) and j.num_verts == 0


def test_join_preserves_corner_edges_consistency_with_explicit_edges():
    a = MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (5, 5, 5)], [(2, 3)], [(0, 1, 2)])
    j = G.join([a, a])
    assert j.num_edges == 8
    assert j.validate() == (False, [])


def test_flip_faces_validate_after_mask_none_on_primitive():
    g = G.uv_sphere(8, 4)
    G.flip_faces(g)
    assert signed_volume(g) < 0
    assert g.validate() == (False, [])
