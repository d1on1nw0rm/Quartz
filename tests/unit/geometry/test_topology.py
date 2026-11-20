import numpy as np
import pytest

from quartz.geometry import (
    MeshGeometry,
    calc_edges,
    edge_keys,
    face_edge_keys,
    faces_to_offsets,
    flip_faces,
    join,
    loose_edges,
    loose_verts,
    merge_by_distance,
)

QUAD_VERTS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]


def _quad():
    return MeshGeometry.from_pydata(QUAD_VERTS, faces=[[0, 1, 2, 3]])


def test_edge_keys_sorts_rows():
    edges = np.array([[3, 1], [0, 2], [5, 4]], dtype=np.int32)
    np.testing.assert_array_equal(edge_keys(edges), np.array([[1, 3], [0, 2], [4, 5]], np.int32))
    assert edge_keys(np.zeros((0, 2), np.int32)).shape == (0, 2)


def test_face_edge_keys_corner_order():
    geo = _quad()
    assert face_edge_keys(geo, 0) == [(0, 1), (1, 2), (2, 3), (0, 3)]
    with pytest.raises(IndexError):
        face_edge_keys(geo, 1)


def test_calc_edges_rebuilds_and_keeps_existing():
    geo = _quad()
    geo.resize_domain("EDGE", 0)
    calc_edges(geo, keep_existing=False)
    assert geo.num_edges == 4
    assert sorted(tuple(sorted(row)) for row in geo.edges.tolist()) == [
        (0, 1), (0, 3), (1, 2), (2, 3),
    ]
    assert geo.validate() == (False, [])

    geo.edges[0] = (0, 1)
    calc_edges(geo, keep_existing=True)
    assert geo.num_edges == 4
    geo.resize_domain("EDGE", 5)
    geo.edges[4] = (7, 8)
    calc_edges(geo, keep_existing=True)
    assert [7, 8] in geo.edges.tolist()


def test_loose_masks():
    geo = _quad()
    geo.add_edges(1)
    geo.edges[4] = (1, 3)
    assert loose_edges(geo).tolist() == [False, False, False, False, True]
    assert not loose_verts(geo).any()
    geo.resize_domain("POINT", 5)
    assert loose_verts(geo).tolist() == [False, False, False, False, True]
    assert loose_edges(geo).tolist() == [False, False, False, False, True]


def test_faces_to_offsets():
    offsets, corners = faces_to_offsets([[0, 1, 2], [2, 3, 4, 5]])
    np.testing.assert_array_equal(offsets, np.array([0, 3, 7], np.int32))
    np.testing.assert_array_equal(corners, np.array([0, 1, 2, 2, 3, 4, 5], np.int32))
    offsets, corners = faces_to_offsets([])
    assert offsets.tolist() == [0]
    assert corners.shape == (0,)


def test_flip_faces():
    geo = _quad()
    before = geo.corner_verts.tolist()
    flip_faces(geo)
    assert geo.corner_verts[0] == before[0]
    assert geo.corner_verts.tolist() == [0, 3, 2, 1]
    assert geo.validate() == (False, [])

    geo = _quad()
    flip_faces(geo, np.array([False]))
    assert geo.corner_verts.tolist() == [0, 1, 2, 3]
    with pytest.raises(ValueError):
        flip_faces(geo, np.array([True, False]))


def test_join_counts_and_offsets():
    left = _quad()
    right = _quad()
    merged = join([left, right], [np.eye(4), np.diag([1.0, 1.0, 1.0, 1.0])])
    assert (merged.num_verts, merged.num_edges, merged.num_faces, merged.num_corners) == (8, 8, 2, 8)
    assert merged.face_offsets.tolist() == [0, 4, 8]
    assert merged.corner_verts.tolist() == [0, 1, 2, 3, 4, 5, 6, 7]
    assert merged.validate() == (False, [])


def test_join_applies_matrices_and_copies_attributes():
    left = _quad()
    left.attributes.new("weight", "FLOAT", "POINT", fill=2.0)
    move = np.eye(4)
    move[:3, 3] = (10.0, 0.0, 0.0)
    merged = join([left], [move])
    np.testing.assert_allclose(merged.positions[0], np.array([10, 0, 0], np.float32))
    assert merged.attributes["weight"].data.tolist() == [2.0, 2.0, 2.0, 2.0]
    assert merged.attributes["sharp_face"].data.tolist() == [True]


def test_join_empty_and_bad_matrices():
    assert join([]).num_verts == 0
    with pytest.raises(ValueError):
        join([_quad()], [np.eye(4), np.eye(4)])


def test_join_fills_missing_attributes_with_defaults():
    left = _quad()
    left.attributes.new("weight", "FLOAT", "POINT", fill=1.0)
    left.attributes.new("color", "FLOAT_COLOR", "CORNER", fill=(1.0, 0.0, 0.0, 1.0))
    right = _quad()
    merged = join([left, right])
    weights = merged.attributes["weight"].data
    assert weights[:4].tolist() == [1.0] * 4
    assert weights[4:].tolist() == [0.0] * 4
    colors = merged.attributes["color"].data
    assert colors.shape == (8, 4)
    assert colors[:4, 0].tolist() == [1.0] * 4
    assert colors[4:, 0].tolist() == [0.0] * 4


def test_join_rejects_conflicting_attribute_definitions():
    left = _quad()
    left.attributes.new("extra", "FLOAT", "POINT")
    right = _quad()
    right.attributes.new("extra", "INT", "POINT")
    with pytest.raises(ValueError):
        join([left, right])


def test_merge_by_distance():
    verts = [(0, 0, 0), (0.0001, 0, 0), (1, 0, 0), (1, 0, 0), (5, 5, 5)]
    geo = MeshGeometry.from_pydata(verts, faces=[])
    mapping = merge_by_distance(geo, 0.001)
    assert mapping.tolist() == [0, 0, 1, 1, 2]
    assert geo.num_verts == 5
    assert merge_by_distance(geo, 0.0).tolist() == [0, 1, 2, 3, 4]
    with pytest.raises(ValueError):
        merge_by_distance(geo, -1.0)
