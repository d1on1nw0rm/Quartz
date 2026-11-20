import numpy as np

from quartz.geometry import (
    MeshGeometry,
    face_areas,
    plane,
    triangulate,
    triangulated,
)


def _triangle_area(points):
    a, b, c = points
    return 0.5 * float(np.linalg.norm(np.cross(b - a, c - a)))


def test_triangulate_quad_uses_shorter_diagonal():
    verts = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (5, 1, 0)]
    geo = MeshGeometry.from_pydata(verts, faces=[[0, 1, 2, 3]])
    tris, owners = triangulate(geo)
    assert tris.shape == (2, 3)
    assert owners.tolist() == [0, 0]
    assert tris.tolist() == [[1, 2, 3], [1, 3, 0]]

    verts = [(0, 0, 0), (10, 0, 0), (8, 2, 0), (-2, 2, 0)]
    other = MeshGeometry.from_pydata(verts, faces=[[0, 1, 2, 3]])
    assert triangulate(other)[0].tolist() == [[0, 1, 2], [0, 2, 3]]


def test_triangulate_triangle_passthrough():
    geo = MeshGeometry.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], faces=[[0, 1, 2]])
    tris, owners = triangulate(geo)
    assert tris.tolist() == [[0, 1, 2]]
    assert owners.tolist() == [0]


def test_triangulate_concave_ngon_area_is_preserved():
    verts = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (1, 1, 0), (0, 2, 0)]
    geo = MeshGeometry.from_pydata(verts, faces=[[0, 1, 2, 3, 4]])
    tris, owners = triangulate(geo)
    assert tris.shape == (3, 3)
    assert owners.tolist() == [0, 0, 0]
    total = 0.0
    for triangle in tris:
        points = geo.positions[geo.corner_verts[triangle]].astype(np.float64)
        total += _triangle_area(points)
    np.testing.assert_allclose(total, float(face_areas(geo)[0]), atol=1e-5)
    np.testing.assert_allclose(total, 3.0, atol=1e-5)


def test_triangulate_empty_geometry():
    tris, owners = triangulate(MeshGeometry())
    assert tris.shape == (0, 3)
    assert owners.shape == (0,)


def test_triangulated_geometry_counts_and_attributes():
    geo = plane()
    result = triangulated(geo)
    assert (result.num_verts, result.num_edges, result.num_faces, result.num_corners) == (4, 5, 2, 6)
    assert result.validate() == (False, [])
    assert result.attributes["UVMap"].data.shape == (6, 2)
    tris, tri_face = triangulate(geo)
    source_uv = geo.attributes["UVMap"].data
    source_corners = tris.reshape(-1)
    np.testing.assert_allclose(result.attributes["UVMap"].data, source_uv[source_corners])
    assert result.attributes["sharp_face"].data.tolist() == [True, True]


def test_triangulated_cube_counts():
    from quartz.geometry import cube

    result = triangulated(cube())
    assert (result.num_verts, result.num_faces, result.num_corners) == (8, 12, 36)
    assert result.num_edges == 18
    assert result.validate() == (False, [])


def test_triangulated_copies_custom_point_attribute():
    from quartz.geometry import cube

    geo = cube()
    geo.attributes.new("weight", "FLOAT", "POINT", fill=3.0)
    result = triangulated(geo)
    assert result.attributes["weight"].data.tolist() == [3.0] * 8
