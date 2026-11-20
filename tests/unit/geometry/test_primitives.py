import numpy as np
import pytest

from quartz.geometry import (
    circle,
    cone,
    cube,
    cylinder,
    face_centers,
    face_normals,
    grid,
    ico_sphere,
    plane,
    torus,
    uv_sphere,
)

TABLE = {
    "plane": (plane, 4, 4, 1, 4, (-1, -1, 0), (1, 1, 0)),
    "cube": (cube, 8, 12, 6, 24, (-1, -1, -1), (1, 1, 1)),
    "circle": (circle, 32, 32, 0, 0, (-1, -1, 0), (1, 1, 0)),
    "uv_sphere": (uv_sphere, 482, 992, 512, 1984, (-1, -1, -1), (1, 1, 1)),
    "ico_sphere": (ico_sphere, 42, 120, 80, 240, (-1, -1, -1), (1, 1, 1)),
    "cylinder": (cylinder, 64, 96, 34, 192, (-1, -1, -1), (1, 1, 1)),
    "cone": (cone, 33, 64, 33, 128, (-1, -1, -1), (1, 1, 1)),
    "grid": (grid, 121, 220, 100, 400, (-1, -1, 0), (1, 1, 0)),
    "torus": (torus, 576, 1152, 576, 2304, (-1.25, -1.25, -0.25), (1.25, 1.25, 0.25)),
}


@pytest.mark.parametrize("name", sorted(TABLE))
def test_counts_and_bounds(name):
    factory, verts, edges, faces, corners, low, high = TABLE[name]
    geo = factory()
    assert (geo.num_verts, geo.num_edges, geo.num_faces, geo.num_corners) == (
        verts, edges, faces, corners,
    )
    np.testing.assert_allclose(geo.positions.min(axis=0), np.array(low, np.float32), atol=1e-5)
    np.testing.assert_allclose(geo.positions.max(axis=0), np.array(high, np.float32), atol=1e-5)
    assert geo.validate() == (False, [])


@pytest.mark.parametrize("name", sorted(TABLE))
def test_uvs_and_sharp_faces(name):
    factory = TABLE[name][0]
    geo = factory()
    assert geo.attributes.get("UVMap") is not None
    uv = geo.attributes["UVMap"].data
    assert uv.dtype == np.float32
    assert uv.shape == (geo.num_corners, 2)
    if uv.size:
        assert float(uv.min()) >= 0.0
        assert float(uv.max()) <= 1.0
    if geo.num_faces:
        assert geo.attributes["sharp_face"].data.all()
        assert geo.attributes["sharp_face"].data.shape == (geo.num_faces,)
    geo = factory(calc_uvs=False)
    assert geo.attributes.get("UVMap") is None


@pytest.mark.parametrize("name", ["cube", "uv_sphere", "ico_sphere", "cylinder", "cone"])
def test_face_normals_point_outward(name):
    geo = TABLE[name][0]()
    normals = face_normals(geo).astype(np.float64)
    centers = face_centers(geo).astype(np.float64)
    lengths = np.linalg.norm(normals, axis=1)
    assert np.all(lengths > 0.99)
    assert float(np.min(np.sum(normals * centers, axis=1))) > 0.0


def test_plane_and_grid_normals_face_up():
    for geo in (plane(), grid()):
        normals = face_normals(geo)
        np.testing.assert_allclose(normals, np.tile(np.array([0, 0, 1]), (geo.num_faces, 1)), atol=1e-6)


def test_torus_normals_point_away_from_tube_axis():
    geo = torus()
    normals = face_normals(geo).astype(np.float64)
    centers = face_centers(geo).astype(np.float64)
    radial = centers.copy()
    radial[:, 2] = 0.0
    lengths = np.linalg.norm(radial, axis=1)
    lengths[lengths == 0] = 1.0
    tube_centers = radial / lengths[:, None]
    dots = np.sum(normals * (centers - tube_centers), axis=1)
    assert float(dots.min()) > 0.0


def test_circle_fill_variants():
    nothing = circle(fill_type="NOTHING")
    assert (nothing.num_verts, nothing.num_edges, nothing.num_faces, nothing.num_corners) == (32, 32, 0, 0)
    ngon = circle(fill_type="NGON")
    assert (ngon.num_verts, ngon.num_edges, ngon.num_faces, ngon.num_corners) == (32, 32, 1, 32)
    fan = circle(fill_type="TRIFAN")
    assert (fan.num_verts, fan.num_edges, fan.num_faces, fan.num_corners) == (33, 64, 32, 96)
    for geo in (ngon, fan):
        checks = face_normals(geo).astype(np.float64)
        assert float(checks[:, 2].min()) > 0.99


def test_cylinder_fill_variants():
    nothing = cylinder(end_fill_type="NOTHING")
    assert (nothing.num_verts, nothing.num_edges, nothing.num_faces, nothing.num_corners) == (64, 96, 32, 128)
    fan = cylinder(end_fill_type="TRIFAN")
    assert (fan.num_verts, fan.num_edges, fan.num_faces, fan.num_corners) == (66, 160, 96, 320)


def test_cone_frustum_matches_cylinder():
    frustum = cone(radius2=0.5)
    assert (frustum.num_verts, frustum.num_edges, frustum.num_faces, frustum.num_corners) == (64, 96, 34, 192)


def test_ico_sphere_subdivisions():
    one = ico_sphere(subdivisions=1)
    assert (one.num_verts, one.num_edges, one.num_faces, one.num_corners) == (12, 30, 20, 60)
    three = ico_sphere(subdivisions=3)
    assert (three.num_verts, three.num_edges, three.num_faces, three.num_corners) == (162, 480, 320, 960)
    assert float(np.linalg.norm(three.positions, axis=1).max()) == pytest.approx(1.0)


def test_uv_sphere_poles():
    geo = uv_sphere()
    z = geo.positions[:, 2]
    assert float(z.max()) == pytest.approx(1.0)
    assert float(z.min()) == pytest.approx(-1.0)
    assert int(np.count_nonzero(np.isclose(z, 1.0))) == 1
    assert int(np.count_nonzero(np.isclose(z, -1.0))) == 1


def test_invalid_parameters_raise():
    with pytest.raises(ValueError):
        plane(0.0)
    with pytest.raises(ValueError):
        cube(-1.0)
    with pytest.raises(ValueError):
        circle(vertices=2)
    with pytest.raises(ValueError):
        circle(fill_type="NOPE")
    with pytest.raises(ValueError):
        uv_sphere(segments=2)
    with pytest.raises(ValueError):
        uv_sphere(ring_count=1)
    with pytest.raises(ValueError):
        ico_sphere(subdivisions=0)
    with pytest.raises(ValueError):
        cylinder(vertices=2)
    with pytest.raises(ValueError):
        cylinder(depth=0.0)
    with pytest.raises(ValueError):
        cylinder(end_fill_type="NOPE")
    with pytest.raises(ValueError):
        cone(radius1=0.0, radius2=0.0)
    with pytest.raises(ValueError):
        cone(radius1=0.0, radius2=1.0)
    with pytest.raises(ValueError):
        cone(radius2=-1.0)
    with pytest.raises(ValueError):
        cylinder(radius=0.0)
    with pytest.raises(ValueError):
        grid(x_subdivisions=0)
    with pytest.raises(ValueError):
        torus(major_segments=2)
    with pytest.raises(ValueError):
        torus(minor_radius=0.0)
