import numpy as np
import pytest

from quartz.geometry import MeshGeometry


QUAD_VERTS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
QUAD_FACES = [[0, 1, 2, 3]]


def test_empty_geometry():
    geo = MeshGeometry()
    assert geo.num_verts == geo.num_edges == geo.num_faces == geo.num_corners == 0
    assert geo.face_offsets.tolist() == [0]
    assert geo.face_offsets.dtype == np.int32
    for name in ("position", ".edge_verts", ".corner_vert", ".corner_edge"):
        assert geo.attributes.get(name) is not None
        assert geo.attributes[name].data.shape[0] == 0
    assert MeshGeometry.empty().num_verts == 0


def test_from_pydata_quad():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    assert (geo.num_verts, geo.num_edges, geo.num_faces, geo.num_corners) == (4, 4, 1, 4)
    assert geo.positions.dtype == np.float32
    assert geo.positions.shape == (4, 3)
    assert geo.edges.dtype == np.int32
    assert geo.corner_verts.tolist() == [0, 1, 2, 3]
    assert geo.face_sizes().tolist() == [4]
    assert geo.corner_to_face().tolist() == [0, 0, 0, 0]
    assert geo.validate() == (False, [])
    assert geo.attributes["sharp_face"].data.tolist() == [True]
    for name in (".select_vert", ".select_edge", ".select_poly"):
        assert not geo.attributes[name].data.any()


def test_from_pydata_shade_flat_false():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES, shade_flat=False)
    assert geo.attributes["sharp_face"].data.tolist() == [False]
    empty = MeshGeometry()
    assert empty.face_sizes().shape == (0,)
    assert empty.corner_to_face().shape == (0,)


def test_from_pydata_explicit_edges_come_first():
    geo = MeshGeometry.from_pydata(
        QUAD_VERTS, edges=[(0, 2), (0, 1), (0, 1)], faces=QUAD_FACES
    )
    assert geo.edges[:2].tolist() == [[0, 2], [0, 1]]
    keys = [tuple(sorted(row)) for row in geo.edges.tolist()]
    assert len(keys) == len(set(keys))
    assert set(keys) == {(0, 1), (1, 2), (2, 3), (0, 3), (0, 2)}


def test_from_pydata_corner_edges_are_consistent():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    lookup = {tuple(sorted(row)): index for index, row in enumerate(geo.edges.tolist())}
    labels = [lookup[(0, 1)], lookup[(1, 2)], lookup[(2, 3)], lookup[(0, 3)]]
    assert geo.corner_edges.tolist() == labels


def test_from_pydata_rejects_invalid_input():
    with pytest.raises(ValueError):
        MeshGeometry.from_pydata([(0, 0)], faces=[])
    with pytest.raises(ValueError):
        MeshGeometry.from_pydata(QUAD_VERTS, faces=[[0, 1]])
    with pytest.raises(ValueError):
        MeshGeometry.from_pydata(QUAD_VERTS, faces=[[0, 1, 9]])
    with pytest.raises(ValueError):
        MeshGeometry.from_pydata(QUAD_VERTS, edges=[(0, 9)], faces=[])


def test_from_pydata_without_faces_keeps_loose_edges():
    geo = MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0)], edges=[(0, 1)])
    assert (geo.num_verts, geo.num_edges, geo.num_faces, geo.num_corners) == (2, 1, 0, 0)
    assert geo.validate() == (False, [])


def test_add_domain_helpers():
    geo = MeshGeometry()
    verts = geo.add_verts(3)
    assert verts == slice(0, 3)
    assert geo.num_verts == 3
    edges = geo.add_edges(2)
    assert edges == slice(0, 2)
    corners = geo.add_corners(4)
    assert corners == slice(0, 4)
    faces = geo.add_faces(2)
    assert faces == slice(0, 2)
    assert geo.num_faces == 2
    assert geo.face_offsets.tolist() == [0, 0, 0]


def test_add_faces_with_sizes():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    new = geo.add_faces([3, 4])
    assert new == slice(1, 3)
    assert geo.num_faces == 3
    assert geo.num_corners == 11
    assert geo.face_sizes().tolist() == [4, 3, 4]
    assert geo.face_offsets.tolist() == [0, 4, 7, 11]
    with pytest.raises(ValueError):
        geo.add_faces([0])
    with pytest.raises(ValueError):
        geo.add_verts(-1)


def test_resize_domain():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.resize_domain("POINT", 6)
    assert geo.num_verts == 6
    np.testing.assert_array_equal(geo.positions[4:], np.zeros((2, 3), np.float32))
    geo.resize_domain("POINT", 2)
    assert geo.num_verts == 2
    geo.resize_domain("FACE", 2)
    assert geo.num_faces == 2
    assert geo.face_offsets.tolist() == [0, 4, 4]
    geo.resize_domain("FACE", 0)
    assert geo.num_faces == 0
    assert geo.face_offsets.tolist() == [0]


def test_set_face_offsets():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.set_face_offsets([0])
    assert geo.face_offsets.tolist() == [0, 4]
    with pytest.raises(ValueError):
        geo.set_face_offsets([0, 2, 1])
    with pytest.raises(ValueError):
        geo.set_face_offsets([1])
    with pytest.raises(ValueError):
        geo.set_face_offsets([0, 9])


def test_copy_is_independent():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    clone = geo.copy()
    clone.positions[0] = (5, 5, 5)
    clone.add_verts(1)
    assert tuple(geo.positions[0]) == (0.0, 0.0, 0.0)
    assert geo.num_verts == 4
    assert clone.num_verts == 5
    assert clone.attributes["sharp_face"] is not geo.attributes["sharp_face"]


def test_clear():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.clear()
    for domain in ("POINT", "EDGE", "FACE", "CORNER"):
        assert geo.domain_size(domain) == 0
    assert geo.face_offsets.tolist() == [0]
    assert geo.validate() == (False, [])


def test_validate_clean_and_fix_flag():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    assert geo.validate() == (False, [])
    assert geo.validate(fix=True) == (False, [])


def test_validate_detects_problems():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.corner_verts[0] = 9
    changed, problems = geo.validate()
    assert changed is False
    assert any("corner" in problem for problem in problems)

    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.edges[0] = (1, 1)
    changed, problems = geo.validate()
    assert changed is False
    assert any("degenerate" in problem for problem in problems)

    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.edges[1] = geo.edges[0]
    changed, problems = geo.validate()
    assert changed is False
    assert any("duplicate" in problem for problem in problems)

    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.positions[0] = np.nan
    changed, problems = geo.validate()
    assert changed is False
    assert any("non-finite" in problem for problem in problems)

    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.face_offsets[0] = 1
    changed, problems = geo.validate()
    assert changed is False
    assert any("offsets" in problem for problem in problems)


def test_validate_fix_repairs_geometry():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.corner_edges[1] = 99
    geo.positions[1] = np.inf
    geo.edges[0] = (1, 1)
    changed, problems = geo.validate(fix=True)
    assert changed is True
    assert problems
    assert geo.validate() == (False, [])
    assert geo.num_faces == 1
    assert int(geo.corner_verts.max()) < geo.num_verts
    assert np.isfinite(geo.positions).all()
    assert not (geo.edges[:, 0] == geo.edges[:, 1]).any()


def test_validate_fix_drops_short_faces():
    geo = MeshGeometry.from_pydata(QUAD_VERTS, faces=QUAD_FACES)
    geo.face_offsets = np.array([0, 1, 2], dtype=np.int32)
    geo.attributes.resize("FACE", 2)
    geo.resize_domain("CORNER", 2)
    geo.corner_verts[:] = [0, 1]
    changed, problems = geo.validate(fix=True)
    assert changed is True
    assert geo.num_faces == 0
    assert geo.validate() == (False, [])



TWO_QUAD_VERTS = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)]
TWO_QUAD_FACES = [(0, 1, 4, 3), (1, 2, 5, 4)]


def test_validate_fix_drops_face_attribute_row_of_removed_face():
    geo = MeshGeometry.from_pydata(TWO_QUAD_VERTS, faces=TWO_QUAD_FACES)
    geo.attributes["sharp_face"].data[:] = [True, False]
    geo.attributes.new("face_id", "INT", "FACE").data[:] = [10, 20]
    geo.corner_verts[1] = 99
    changed, _ = geo.validate(fix=True)
    assert changed
    assert geo.num_faces == 1
    assert geo.attributes["sharp_face"].data.tolist() == [False]
    assert geo.attributes["face_id"].data.tolist() == [20]
    assert geo.corner_verts.tolist() == [1, 2, 5, 4]
    assert geo.validate() == (False, [])


def test_validate_fix_drops_corner_attribute_rows_of_removed_face():
    geo = MeshGeometry.from_pydata(TWO_QUAD_VERTS, faces=TWO_QUAD_FACES)
    uv = geo.attributes.new("uv", "FLOAT2", "CORNER")
    uv.data[:] = np.arange(16, dtype=np.float32).reshape(8, 2)
    geo.corner_verts[1] = 99
    geo.validate(fix=True)
    assert geo.num_corners == 4
    assert geo.face_offsets.tolist() == [0, 4]
    expected = np.arange(8, 16, dtype=np.float32).reshape(4, 2)
    assert np.array_equal(geo.attributes["uv"].data, expected)


def test_validate_fix_drops_edge_attribute_rows_of_removed_edges():
    geo = MeshGeometry.from_pydata(
        [(0, 0, 0), (1, 0, 0), (2, 0, 0)], edges=[(0, 1), (1, 2)]
    )
    weight = geo.attributes.new("weight", "FLOAT", "EDGE")
    weight.data[:] = [1.0, 2.0]
    geo.edges[0] = (0, 0)
    sl = geo.add_edges(1)
    geo.edges[sl] = (2, 1)
    weight.data[sl] = 3.0
    changed, problems = geo.validate(fix=True)
    assert changed and problems
    assert geo.edges.tolist() == [[1, 2]]
    assert geo.attributes["weight"].data.tolist() == [2.0]
    assert geo.validate() == (False, [])
