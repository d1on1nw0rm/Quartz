import numpy as np

from quartz.geometry import (
    MeshGeometry,
    face_areas,
    face_centers,
    face_normals,
    vertex_normals,
    corner_normals,
)

QUAD_VERTS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]


def _quad():
    return MeshGeometry.from_pydata(QUAD_VERTS, faces=[[0, 1, 2, 3]])


def test_face_normals_plane_direction():
    geo = _quad()
    normals = face_normals(geo)
    assert normals.dtype == np.float32
    np.testing.assert_allclose(normals[0], np.array([0, 0, 1], np.float32), atol=1e-6)
    flipped = MeshGeometry.from_pydata(QUAD_VERTS, faces=[[3, 2, 1, 0]])
    np.testing.assert_allclose(face_normals(flipped)[0], np.array([0, 0, -1]), atol=1e-6)


def test_face_normals_degenerate_is_zero():
    geo = MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0)], faces=[[0, 1, 2]])
    np.testing.assert_array_equal(face_normals(geo)[0], np.zeros(3, np.float32))


def test_face_centers_and_areas():
    geo = _quad()
    np.testing.assert_allclose(face_centers(geo)[0], np.array([0.5, 0.5, 0.0]), atol=1e-6)
    np.testing.assert_allclose(face_areas(geo), np.array([1.0], np.float32), atol=1e-6)
    assert face_centers(MeshGeometry()).shape == (0, 3)
    assert face_areas(MeshGeometry()).shape == (0,)


def test_vertex_normals_are_normalized():
    geo = _quad()
    normals = vertex_normals(geo)
    assert normals.shape == (4, 3)
    assert normals.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-5)
    np.testing.assert_allclose(normals, np.array([[0, 0, 1]] * 4), atol=1e-6)


def test_vertex_normals_loose_vertex_uses_position():
    geo = MeshGeometry.from_pydata([(0, 0, 3)], faces=[])
    np.testing.assert_allclose(vertex_normals(geo)[0], np.array([0, 0, 1]), atol=1e-6)


def test_corner_normals_flat_and_smooth():
    geo = _quad()
    flat = corner_normals(geo)
    np.testing.assert_allclose(flat, np.array([[0, 0, 1]] * 4), atol=1e-6)
    smooth = corner_normals(geo, sharp_face=np.array([False]))
    np.testing.assert_allclose(smooth, np.array([[0, 0, 1]] * 4), atol=1e-6)

    geo.attributes["sharp_face"].data[:] = False
    np.testing.assert_allclose(corner_normals(geo), smooth, atol=1e-6)


def test_corner_normals_two_faces_flat_keeps_hard_edge():
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1)]
    geo = MeshGeometry.from_pydata(verts, faces=[[0, 1, 2, 3], [0, 1, 4]])
    geo.attributes["sharp_face"].data[:] = True
    normals = corner_normals(geo)
    assert normals.shape == (7, 3)
    np.testing.assert_allclose(normals[:4], np.array([[0, 0, 1]] * 4), atol=1e-6)
