from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import gc
import math
import re
import tempfile
import time
import warnings
import weakref

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio.ext import store
from quartz_studio.scene import Mesh, Scene, SceneObject, reset_scene
from quartz_studio import uv as uvpkg
from quartz_studio.uv import arrange, data, project, texture, unwrap
from quartz_studio.uv.editor import UVEditorView
from quartz_studio.uv.panels import TexturePaintPanel, UVToolsPanel, ViewportPainter
from quartz_studio.uv.session import session_for

APP = QApplication.instance() or QApplication([])


def grid_mesh(nx: int = 4, ny: int = 3, size: float = 100.0, jitter: float = 0.0, seed: int = 1) -> Mesh:
    rng = np.random.default_rng(seed)
    pts = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            pts.append((i * size / nx, j * size / ny, 0.0))
    pts = np.array(pts, float)
    if jitter:
        pts[:, :2] += rng.uniform(-jitter, jitter, size=(len(pts), 2))
    polys = []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            polys.append((a, a + 1, a + nx + 2, a + nx + 1))
    return Mesh(pts, polys)


def half_grid(nx: int = 2, ny: int = 1, size: float = 100.0) -> Mesh:
    mesh = grid_mesh(nx, ny, size)
    pts = mesh.points.copy()
    pts[:, 1] *= 0.5
    mesh.points = pts
    return mesh


def cylinder_mesh(radius: float = 50.0, height: float = 200.0, segs: int = 16, rows: int = 4,
                  caps: bool = True) -> Mesh:
    pts = []
    for r in range(rows + 1):
        y = -height / 2 + height * r / rows
        for k in range(segs):
            a = 2 * math.pi * k / segs
            pts.append((radius * math.sin(a), y, radius * math.cos(a)))
    polys = []
    for r in range(rows):
        for k in range(segs):
            a = r * segs + k
            b = r * segs + (k + 1) % segs
            polys.append((a, b, b + segs, a + segs))
    if caps:
        polys.append(tuple(reversed(range(segs))))
        polys.append(tuple(rows * segs + k for k in range(segs)))
    return Mesh(pts, polys)


def sphere_mesh(radius: float = 100.0, segs: int = 16, rings: int = 8) -> Mesh:
    pts = [(0.0, -radius, 0.0)]
    for r in range(1, rings):
        phi = -math.pi / 2 + math.pi * r / rings
        for k in range(segs):
            th = 2 * math.pi * k / segs
            pts.append((radius * math.cos(phi) * math.sin(th), radius * math.sin(phi),
                        radius * math.cos(phi) * math.cos(th)))
    pts.append((0.0, radius, 0.0))
    top = len(pts) - 1
    polys = []
    for k in range(segs):
        polys.append((0, 1 + (k + 1) % segs, 1 + k))
    for r in range(rings - 2):
        for k in range(segs):
            a = 1 + r * segs + k
            b = 1 + r * segs + (k + 1) % segs
            polys.append((a, b, b + segs, a + segs))
    base = 1 + (rings - 2) * segs
    for k in range(segs):
        polys.append((base + k, base + (k + 1) % segs, top))
    return Mesh(pts, polys)


def torus_mesh(big: float = 100.0, small: float = 30.0, nu: int = 16, nv: int = 8) -> Mesh:
    pts = []
    for i in range(nu):
        u = 2 * math.pi * i / nu
        for j in range(nv):
            v = 2 * math.pi * j / nv
            pts.append(((big + small * math.cos(v)) * math.cos(u), small * math.sin(v),
                        (big + small * math.cos(v)) * math.sin(u)))
    polys = []
    for i in range(nu):
        for j in range(nv):
            a = i * nv + j
            b = ((i + 1) % nu) * nv + j
            c = ((i + 1) % nu) * nv + (j + 1) % nv
            d = i * nv + (j + 1) % nv
            polys.append((a, d, c, b))
    return Mesh(pts, polys)


def make_obj(mesh: Mesh, name: str = "T") -> SceneObject:
    return SceneObject(name, mesh)


def island_boxes(obj, uv):
    c = data.Corners(obj.mesh)
    out = []
    for isl in data.uv_islands(obj.mesh, uv, c):
        idx = data.corners_of_polys(c, isl)
        out.append((uv[idx].min(axis=0), uv[idx].max(axis=0)))
    return out


def boxes_overlap(boxes, tol: float = 1e-9) -> bool:
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a0, a1 = boxes[i]
            b0, b1 = boxes[j]
            if (a0[0] < b1[0] - tol and b0[0] < a1[0] - tol and a0[1] < b1[1] - tol and b0[1] < a1[1] - tol):
                return True
    return False


def fresh_scene(mesh: Mesh | None = None):
    scene = reset_scene()
    if mesh is not None:
        scene.active.mesh = mesh
    sess = session_for(scene)
    return scene, sess


def test_corners_layout():
    cube = Mesh.cube(200.0)
    c = data.Corners(cube)
    assert c.count == 24 and c.poly_count == 6
    assert list(c.starts) == [0, 4, 8, 12, 16, 20, 24]
    assert c.vertex[4:8].tolist() == list(cube.polygons[1])
    assert c.next[3] == 0 and c.prev[0] == 3 and c.next[0] == 1
    edges = c.edges()
    assert len(edges) == 12
    assert all(len(v) == 2 for v in edges.values())
    assert c.corner_of(1, 6) == 6


def test_uv_roundtrip_through_store():
    obj = make_obj(grid_mesh(2, 1))
    c = data.Corners(obj.mesh)
    arr = np.arange(c.count * 2, dtype=float).reshape(-1, 2) / 10.0
    data.set_uv_array(obj, arr, c)
    raw = store.get_object(obj, data.UV_KEY)
    assert isinstance(raw, list) and len(raw) == 2 and len(raw[0]) == 4
    assert raw[1][0] == [0.8, 0.9]
    back = data.get_uv_array(obj, c)
    assert np.allclose(back, arr)
    js = store.from_json(store.to_json(raw))
    assert data.uv_is_valid(js, obj.mesh)


def test_ensure_uv_repairs_after_topology_change():
    obj = make_obj(grid_mesh(2, 1))
    data.ensure_uv(obj)
    assert data.has_uv(obj)
    c = data.Corners(obj.mesh)
    arr = data.get_uv_array(obj, c)
    arr[:4] = [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]]
    data.set_uv_array(obj, arr, c)
    obj.mesh.set_polygon(1, (1, 2, 5))
    assert not data.has_uv(obj)
    fixed = data.get_uv_array(obj)
    assert fixed.shape == (7, 2)
    assert np.allclose(fixed[:4], [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]])
    assert data.ensure_uv(obj) is True
    assert data.has_uv(obj)
    scene = reset_scene()
    scene.active.mesh = Mesh(obj.mesh.points.copy(), obj.mesh.polygons)
    data.set_uv_array(scene.active, data.get_uv_array(obj))
    scene.active.mesh.add_polygon((0, 1, 4))
    assert data.sync_all(scene) == 1 and data.has_uv(scene.active)
    obj.mesh.add_polygon((0, 1, 4))
    data.ensure_uv(obj)
    uv = data.get_uv(obj)
    assert len(uv) == 3 and all(0.0 <= v <= 1.0 for ring in uv for pt in ring for v in pt)


def test_seams_store_and_sync():
    obj = make_obj(Mesh.cube(200.0))
    assert data.add_seams(obj, [(1, 0), (0, 1), (2, 3), (0, 6)]) == 2
    assert data.get_seams(obj) == {(0, 1), (2, 3)}
    assert data.remove_seams(obj, [(3, 2)]) == 1
    data.set_seams(obj, [(0, 1), (99, 100)])
    assert data.sync_seams(obj) is True
    assert data.get_seams(obj) == {(0, 1)}
    data.clear_seams(obj)
    assert data.get_seams(obj) == set()


def test_triangulate_concave_ngon():
    ring = np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0], [1, 2, 0], [0, 2, 0]], float)
    tris = data.triangulate_polygon(ring)
    assert len(tris) == 4
    area = 0.0
    for a, b, c in tris:
        e = np.cross(ring[b] - ring[a], ring[c] - ring[a])
        assert e[2] > 0
        area += 0.5 * np.linalg.norm(e)
    assert abs(area - 3.0) < 1e-12


def test_mesh_triangles_quads_and_ngons():
    mesh = Mesh([(0, 0, 0), (4, 0, 0), (4, 1, 0), (0, 1, 0), (2, 3, 0), (-1, 2, 0)],
                [(0, 1, 2, 3), (3, 2, 4, 5)])
    tris, owner = data.mesh_triangles(mesh)
    assert len(tris) == 4
    assert sorted(owner.tolist()) == [0, 0, 1, 1]
    c = data.Corners(mesh)
    area = data.polygon_area_3d(mesh, c)
    tri_area = np.zeros(2)
    P = mesh.points[c.vertex]
    for t, o in zip(tris, owner):
        tri_area[o] += 0.5 * np.linalg.norm(np.cross(P[t[1]] - P[t[0]], P[t[2]] - P[t[0]]))
    assert np.allclose(tri_area, area)


def test_point_groups_and_islands_from_uv():
    obj = make_obj(grid_mesh(2, 1))
    c = data.Corners(obj.mesh)
    uv = data.get_uv_array(obj, c)
    groups = data.point_groups(c, uv)
    assert groups.max() + 1 == 6
    assert len(data.uv_islands(obj.mesh, uv, c)) == 1
    uv2 = uv.copy()
    uv2[4:8] += 2.0
    assert len(data.uv_islands(obj.mesh, uv2, c)) == 2
    sel = data.expand_to_points(c, uv, [1])
    assert set(sel.tolist()) == {1, 4}


def test_transform_helpers():
    uv = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    r = data.rotate_uv(uv, [0, 1, 2, 3], 90.0)
    assert np.allclose(r, [[1, 0], [1, 1], [0, 1], [0, 0]])
    s = data.scale_uv(uv, [0, 1, 2, 3], 2.0, 0.5)
    assert np.allclose(s, [[-0.5, 0.25], [1.5, 0.25], [1.5, 0.75], [-0.5, 0.75]])
    m = data.move_uv(uv, [1], (0.5, 0.25))
    assert np.allclose(m[1], [1.5, 0.25]) and np.allclose(m[0], [0, 0])


def test_flat_projection_axes_and_fit():
    obj = make_obj(half_grid(4, 2, 100.0))
    uv = project.project_flat(obj, "Z")
    c = data.Corners(obj.mesh)
    p = obj.mesh.points[c.vertex]
    assert np.allclose(uv[:, 0], p[:, 0] / 100.0)
    assert np.allclose(uv[:, 1], p[:, 1] / 100.0 + 0.25)
    assert np.allclose(p[:, 1].max(), 50.0)
    assert np.allclose(uv.min(axis=0), [0.0, 0.25]) and np.allclose(uv.max(axis=0), [1.0, 0.75])
    stretched = project.project(obj, "Flat", axis="Z", keep_aspect=False, write=False)
    assert np.allclose(stretched.min(axis=0), 0.0) and np.allclose(stretched.max(axis=0), 1.0)
    assert np.allclose(data.get_uv_array(obj), uv)
    up = project.project(obj, "Flat", axis="X", write=False)
    assert np.allclose(up[:, 0], up[0, 0])


def test_flat_projection_normal_is_isometric_on_tilted_plane():
    mesh = grid_mesh(3, 3, 90.0)
    rot = np.array([[1, 0, 0], [0, math.cos(0.7), -math.sin(0.7)], [0, math.sin(0.7), math.cos(0.7)]])
    rot = rot @ np.array([[math.cos(0.4), 0, math.sin(0.4)], [0, 1, 0], [-math.sin(0.4), 0, math.cos(0.4)]])
    mesh.points = mesh.points @ rot.T
    obj = make_obj(mesh)
    uv = project.project_flat(obj, "Normal")
    st = arrange.uv_stats(obj.mesh, uv)
    assert abs(st["mean_stretch"] - 1.0) < 1e-9 and abs(st["max_conformal"] - 1.0) < 1e-6
    assert st["flipped"] == 0
    auto = project.axis_normal("Auto", mesh)
    assert np.count_nonzero(auto) == 1


def test_box_projection_atlas_cube():
    obj = make_obj(Mesh.cube(200.0))
    uv = project.project_box(obj, atlas=True)
    c = data.Corners(obj.mesh)
    boxes = []
    for p in range(6):
        ring = uv[c.of(p)]
        lo, hi = ring.min(axis=0), ring.max(axis=0)
        assert np.allclose(hi - lo, [1 / 3, 1 / 3])
        boxes.append((lo, hi))
        assert data.polygon_area_uv(uv, c)[p] > 0
    assert not boxes_overlap(boxes)
    assert uv.min() >= -1e-12 and uv.max() <= 1 + 1e-12
    overlap = project.project(obj, "Box", atlas=False, write=False)
    for p in range(6):
        ring = overlap[c.of(p)]
        assert np.allclose(ring.min(axis=0), 0.0) and np.allclose(ring.max(axis=0), 1.0)


def test_spherical_projection_latitude_and_wrap():
    mesh = sphere_mesh(100.0, 16, 8)
    obj = make_obj(mesh)
    uv = project.project(obj, "Spherical", fit=False, write=False)
    c = data.Corners(mesh)
    p = mesh.points[c.vertex]
    lat = np.arcsin(np.clip(p[:, 1] / 100.0, -1, 1))
    assert np.allclose(uv[:, 1], 0.5 + lat / math.pi, atol=1e-9)
    for poly in range(c.poly_count):
        ring = uv[c.of(poly)]
        assert ring[:, 0].max() - ring[:, 0].min() < 0.5
    fitted = project.project_spherical(obj)
    assert fitted.min() >= -1e-9 and fitted.max() <= 1 + 1e-9


def test_cylindrical_projection_height_and_angle():
    mesh = cylinder_mesh(50.0, 200.0, 16, 4, caps=False)
    obj = make_obj(mesh)
    uv = project.project(obj, "Cylindrical", axis="Y", fit=False, write=False)
    c = data.Corners(mesh)
    p = mesh.points[c.vertex]
    assert np.allclose(uv[:, 1], (p[:, 1] + 100.0) / 200.0)
    for poly in range(c.poly_count):
        ring = uv[c.of(poly)]
        width = ring[:, 0].max() - ring[:, 0].min()
        assert abs(width - 1.0 / 16) < 1e-9
    st = arrange.uv_stats(mesh, uv)
    assert st["flipped"] == 0


def test_frontal_projection_with_camera():
    obj = make_obj(grid_mesh(2, 2, 100.0))
    obj.position = np.array([-50.0, -50.0, 0.0])
    cam = project.look_at((0.0, 0.0, -500.0), (0.0, 0.0, 0.0))
    uv = project.project_frontal(obj, cam, fit=False)
    c = data.Corners(obj.mesh)
    world = obj.to_world(obj.mesh.points[c.vertex])
    center = np.argmin(np.linalg.norm(world, axis=1))
    assert np.allclose(uv[center], [0.5, 0.5])
    camx = world @ cam[0, :3]
    assert np.allclose(uv[:, 0], 0.5 + camx / 500.0)
    assert np.allclose(uv[:, 1], 0.5 + world[:, 1] / 500.0)
    fitted = project.project(obj, "Frontal", camera=cam, fit=True, write=False)
    assert np.allclose(fitted.min(axis=0), 0.0) and np.allclose(fitted.max(axis=0), 1.0)

    class Cam:
        focal = 1.0
        ortho = True
        distance = 400.0

        def basis(self):
            return (np.array([0.0, 0.0, -400.0]), np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0]),
                    np.array([0.0, 1.0, 0.0]))

    ortho = project.project(obj, "Frontal", camera=Cam(), fit=False, write=False)
    assert np.allclose(ortho[:, 0], 0.5 + world[:, 0] / 400.0)
    assert np.allclose(ortho[:, 1], 0.5 + world[:, 1] / 400.0)


def test_material_tag_generates_uvw():
    obj = make_obj(grid_mesh(2, 2, 100.0))
    tag = project.set_tag(obj, projection="Flat", axis="Z", tiles=[2.0, 3.0], offset=[0.5, -0.25])
    assert tag["tiles"] == [2.0, 3.0]
    raw = store.get_object(obj, data.TAG_KEY)
    assert raw["projection"] == "Flat"
    base = project.project(obj, "Flat", axis="Z", write=False)
    coords = project.tag_coords(obj)
    assert np.allclose(coords, base * [2.0, 3.0] + [0.5, -0.25])
    out = project.uvw_from_tag(obj)
    assert np.allclose(out, coords)
    assert np.allclose(data.get_uv_array(obj), coords)
    after = project.get_tag(obj)
    assert after["projection"] == "UVW" and after["tiles"] == [1.0, 1.0]
    project.set_tag(obj, tiles=[0.5, 0.5])
    again = project.uvw_from_tag(obj)
    assert np.allclose(again, coords * 0.5)
    project.set_tag(obj, projection="Cubic")
    assert project.tag_coords(obj).shape == coords.shape


def test_angle_seams_and_seam_islands():
    cube = Mesh.cube(200.0)
    seams = unwrap.angle_seams(cube, 60.0)
    assert len(seams) == 12
    assert len(unwrap.seam_islands(cube, seams)) == 6
    assert len(unwrap.seam_islands(cube, set())) == 1
    flat = grid_mesh(3, 3)
    assert unwrap.angle_seams(flat, 10.0) == set()


def test_chart_topology_and_disc_cutting():
    cube = Mesh.cube(200.0)
    c = data.Corners(cube)
    chart = unwrap.build_chart(cube, c, range(6), set())
    assert unwrap.chart_topology(chart) == (2, 0)
    disc, cuts = unwrap.cut_to_disc(cube, c, list(range(6)), set())
    assert unwrap.chart_topology(disc) == (1, 1)
    assert len(cuts) >= 1
    tube = cylinder_mesh(caps=False)
    tc = data.Corners(tube)
    ch = unwrap.build_chart(tube, tc, range(len(tube.polygons)), set())
    assert unwrap.chart_topology(ch) == (0, 2)
    disc, cuts = unwrap.cut_to_disc(tube, tc, list(range(len(tube.polygons))), set())
    assert unwrap.chart_topology(disc) == (1, 1)
    assert len(cuts) == 4
    tor = torus_mesh()
    tc = data.Corners(tor)
    ch = unwrap.build_chart(tor, tc, range(len(tor.polygons)), set())
    assert unwrap.chart_topology(ch) == (0, 0)
    disc, _ = unwrap.cut_to_disc(tor, tc, list(range(len(tor.polygons))), set())
    assert unwrap.chart_topology(disc) == (1, 1)


def test_lscm_reproduces_planar_similarity():
    mesh = grid_mesh(5, 4, 100.0, jitter=4.0)
    c = data.Corners(mesh)
    chart = unwrap.build_chart(mesh, c, range(len(mesh.polygons)), set())
    uv = unwrap.lscm(chart.positions, chart.tris, boundary=chart.boundary_vertices())
    P = chart.positions[:, :2]
    A = np.hstack([P, np.ones((len(P), 1))])
    sol, *_ = np.linalg.lstsq(A, uv, rcond=None)
    assert np.abs(A @ sol - uv).max() < 1e-6
    lin = sol[:2]
    assert abs(lin[0, 0] - lin[1, 1]) < 1e-6 and abs(lin[0, 1] + lin[1, 0]) < 1e-6
    scale = math.hypot(lin[0, 0], lin[0, 1])
    assert abs(scale - 1.0) < 1e-6


def test_lscm_large_island_uses_iterative_solver():
    mesh = grid_mesh(24, 24, 100.0)
    pts = mesh.points.copy()
    pts[:, 2] = 10.0 * np.sin(pts[:, 0] / 30.0)
    mesh.points = pts
    c = data.Corners(mesh)
    chart = unwrap.build_chart(mesh, c, range(len(mesh.polygons)), set())
    assert 2 * chart.vertex_count > unwrap.DENSE_LIMIT
    uv = unwrap.lscm(chart.positions, chart.tris, boundary=chart.boundary_vertices())
    obj = make_obj(mesh)
    full = np.zeros((c.count, 2))
    full[chart.corner_index] = uv[chart.labels]
    st = arrange.uv_stats(mesh, full, c)
    assert st["flipped"] == 0
    assert st["max_conformal"] < 1.01
    assert abs(st["mean_stretch"] - 1.0) < 0.01
    del obj


def test_unwrap_cube_with_cross_seams_is_isometric():
    cube = Mesh.cube(200.0)
    obj = make_obj(cube)
    seams = [(0, 3), (1, 2), (4, 7), (5, 6), (3, 7), (2, 6), (0, 1)]
    data.set_seams(obj, seams)
    uv, info = unwrap.unwrap(obj)
    assert info["islands"] == 1 and info["non_disc"] == 0 and info["cuts"] == 0
    st = arrange.uv_stats(cube, uv)
    assert st["islands"] == 1
    assert abs(st["mean_stretch"] - 1.0) < 1e-6 and st["max_conformal"] < 1 + 1e-6
    assert st["flipped"] == 0 and st["overlap"] == 0.0
    assert uv.min() >= -1e-9 and uv.max() <= 1 + 1e-9
    assert np.allclose(data.get_uv_array(obj), uv)


def test_unwrap_cube_by_angle_gives_six_squares():
    obj = make_obj(Mesh.cube(200.0))
    uv, info = unwrap.unwrap(obj, angle=60.0, margin=0.02)
    assert info["islands"] == 6
    boxes = island_boxes(obj, uv)
    assert len(boxes) == 6
    sizes = [hi - lo for lo, hi in boxes]
    for s in sizes:
        assert abs(s[0] - s[1]) < 1e-9 and abs(s[0] - sizes[0][0]) < 1e-9
    assert not boxes_overlap(boxes)
    assert uv.min() >= 0 and uv.max() <= 1
    st = arrange.uv_stats(obj.mesh, uv)
    assert st["coverage"] > 0.55 and st["flipped"] == 0


def test_unwrap_cylinder_is_developable():
    mesh = cylinder_mesh(50.0, 200.0, 24, 4)
    obj = make_obj(mesh)
    for method in ("Conformal", "Isometric"):
        uv, info = unwrap.unwrap(obj, method=method, angle=60.0)
        assert info["islands"] == 3 and info["non_disc"] == 0 and info["cuts"] == 4
        st = arrange.uv_stats(mesh, uv)
        assert st["islands"] == 3
        assert st["flipped"] == 0 and st["overlap"] == 0.0
        assert abs(st["mean_stretch"] - 1.0) < 1e-3
        assert st["max_conformal"] < 1.02
        assert uv.min() >= -1e-9 and uv.max() <= 1 + 1e-9


def test_unwrap_sphere_and_torus_have_no_flips():
    for mesh in (sphere_mesh(100.0, 16, 8), torus_mesh()):
        obj = make_obj(mesh)
        uv, info = unwrap.unwrap(obj)
        assert info["non_disc"] == 0 and info["islands"] == 1
        st = arrange.uv_stats(mesh, uv)
        assert st["flipped"] == 0 and st["overlap"] < 0.002
        assert st["mean_stretch"] < 1.2
        assert uv.min() >= -1e-9 and uv.max() <= 1 + 1e-9


def test_unwrap_only_selected_polygons():
    obj = make_obj(Mesh.cube(200.0))
    before = data.get_uv_array(obj).copy()
    uv, info = unwrap.unwrap(obj, polys=[0, 1], angle=60.0)
    c = data.Corners(obj.mesh)
    keep = data.corners_of_polys(c, [2, 3, 4, 5])
    assert np.allclose(uv[keep], before[keep])
    assert info["islands"] == 2


def test_arap_improves_area_distortion_over_lscm():
    mesh = sphere_mesh(100.0, 16, 8)
    mesh.polygons = mesh.polygons[: len(mesh.polygons) // 2]
    mesh._rebuild_edges()
    c = data.Corners(mesh)
    chart = unwrap.build_chart(mesh, c, range(len(mesh.polygons)), set())
    base = unwrap.lscm(chart.positions, chart.tris, boundary=chart.boundary_vertices())

    def area_spread(uvc):
        full = np.zeros((c.count, 2))
        full[chart.corner_index] = uvc[chart.labels]
        s = arrange.polygon_stretch(mesh, full, c)
        return float(np.abs(s["area_log"]).mean())

    q = unwrap._local_frames(chart.positions, chart.tris)[0]
    a3 = 0.5 * (q[:, 1, 0] * q[:, 2, 1] - q[:, 2, 0] * q[:, 1, 1])
    t = chart.tris
    au = 0.5 * np.abs((base[t[:, 1], 0] - base[t[:, 0], 0]) * (base[t[:, 2], 1] - base[t[:, 0], 1])
                      - (base[t[:, 1], 1] - base[t[:, 0], 1]) * (base[t[:, 2], 0] - base[t[:, 0], 0]))
    base = base * math.sqrt(a3.sum() / au.sum())
    better = unwrap.arap(chart.positions, chart.tris, base, iterations=20)
    assert area_spread(better) < area_spread(base) * 0.8


def test_relax_springs_and_arap_reduce_stretch():
    mesh = grid_mesh(6, 6, 100.0)
    obj = make_obj(mesh)
    uv = project.project_flat(obj, "Z")
    rng = np.random.default_rng(3)
    c = data.Corners(mesh)
    groups = data.point_groups(c, uv)
    noise = rng.normal(0.0, 0.02, size=(groups.max() + 1, 2))
    border = np.isclose(uv, 0.0).any(axis=1) | np.isclose(uv, 1.0).any(axis=1)
    noisy = uv + np.where(border[:, None], 0.0, noise[groups])
    data.set_uv_array(obj, noisy, c)
    before = arrange.uv_stats(mesh, noisy)["mean_conformal"]
    out = unwrap.relax(obj, method="Springs", iterations=40, pin_boundary=True)
    after = arrange.uv_stats(mesh, out)["mean_conformal"]
    assert after < before
    assert np.allclose(out[border], noisy[border])
    data.set_uv_array(obj, noisy, c)
    out2 = unwrap.relax(obj, method="ARAP", iterations=20, pin_boundary=True)
    assert arrange.uv_stats(mesh, out2)["mean_conformal"] < 1.0 + (before - 1.0) * 0.2
    assert np.allclose(out2[border], noisy[border])
    data.set_uv_array(obj, noisy, c)
    out3 = unwrap.relax(obj, method="ARAP", iterations=20)
    assert arrange.uv_stats(mesh, out3)["mean_conformal"] < 1.001


def test_skyline_pack_no_overlap():
    rng = np.random.default_rng(5)
    sizes = [(float(w), float(h)) for w, h in rng.uniform(0.1, 1.0, size=(25, 2))]
    res = arrange.skyline_pack(sizes, 3.0, rotate=True)
    assert res is not None
    placements, height = res
    rects = []
    for (w, h), (x, y, rot) in zip(sizes, placements):
        if rot:
            w, h = h, w
        assert x >= -1e-12 and x + w <= 3.0 + 1e-9 and y >= -1e-12 and y + h <= height + 1e-9
        rects.append((np.array([x, y]), np.array([x + w, y + h])))
    assert not boxes_overlap(rects)
    assert arrange.skyline_pack([(5.0, 1.0)], 3.0, rotate=False) is None


def test_pack_islands_fits_unit_square_with_margin():
    obj = make_obj(Mesh.cube(200.0))
    uv = project.project_box(obj, atlas=False)
    c = data.Corners(obj.mesh)
    assert len(data.uv_islands(obj.mesh, uv, c)) == 6
    packed = arrange.pack_islands(obj.mesh, uv, c, margin=0.05)
    boxes = island_boxes(obj, packed)
    assert len(boxes) == 6 and not boxes_overlap(boxes)
    assert packed.min() >= 0.0 and packed.max() <= 1.0 + 1e-9
    gaps = []
    for i in range(6):
        for j in range(i + 1, 6):
            a0, a1 = boxes[i]
            b0, b1 = boxes[j]
            gx = max(b0[0] - a1[0], a0[0] - b1[0])
            gy = max(b0[1] - a1[1], a0[1] - b1[1])
            gaps.append(max(gx, gy))
    assert min(gaps) >= 0.05 * 0.9
    st = arrange.uv_stats(obj.mesh, packed)
    assert abs(st["mean_stretch"] - 1.0) < 1e-6


def test_pack_rotation_search_tightens_diagonal_square():
    obj = make_obj(Mesh([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1, 2, 3)]))
    c = data.Corners(obj.mesh)
    h = math.sqrt(0.5) * 0.5
    uv = np.array([[0.5, 0.5 - h], [0.5 + h, 0.5], [0.5, 0.5 + h], [0.5 - h, 0.5]], float)
    off = arrange.pack_islands(obj.mesh, uv, c, margin=0.0)
    on = arrange.pack_islands(obj.mesh, uv, c, margin=0.0, rotation_search=True)
    area_off = float(np.abs(data.polygon_area_uv(off, c)).sum())
    area_on = float(np.abs(data.polygon_area_uv(on, c)).sum())
    assert abs(area_off - 0.5) < 1e-6
    assert area_on > 0.99 and area_on > area_off * 1.9
    assert on.min() >= -1e-9 and on.max() <= 1.0 + 1e-9
    st_off = arrange.uv_stats(obj.mesh, off)
    st_on = arrange.uv_stats(obj.mesh, on)
    assert abs(st_on["mean_stretch"] - st_off["mean_stretch"]) < 1e-6


def test_pack_equalize_and_rotation():
    obj = make_obj(grid_mesh(2, 1, 100.0))
    c = data.Corners(obj.mesh)
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [3, 0], [3.1, 0], [3.1, 0.1], [3, 0.1]], float)
    uv = np.array([[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5], [2, 0], [2.1, 0], [2.1, 0.1], [2, 0.1]], float)
    packed = arrange.pack_islands(obj.mesh, uv, c, margin=0.0, equalize=True)
    area = np.abs(data.polygon_area_uv(packed, c))
    assert abs(area[0] - area[1]) < 1e-9
    no_eq = arrange.pack_islands(obj.mesh, uv, c, margin=0.0, equalize=False)
    area2 = np.abs(data.polygon_area_uv(no_eq, c))
    assert area2[0] > area2[1] * 10
    tall = make_obj(Mesh([(0, 0, 0), (1, 0, 0), (1, 4, 0), (0, 4, 0)], [(0, 1, 2, 3)]))
    tc = data.Corners(tall.mesh)
    t_uv = np.array([[0, 0], [0.1, 0], [0.1, 0.4], [0, 0.4]], float)
    p = arrange.pack_islands(tall.mesh, t_uv, tc, margin=0.0, rotate=True)
    span = p.max(axis=0) - p.min(axis=0)
    assert max(span) > 0.99


def test_align_islands_min_area():
    obj = make_obj(grid_mesh(1, 1, 1.0))
    c = data.Corners(obj.mesh)
    sq = np.array([[0, 0], [2, 0], [2, 1], [0, 1]], float)
    rot = data.rotate_uv(sq, [0, 1, 2, 3], 30.0)
    out = arrange.align_islands(obj.mesh, rot, c)
    span = out.max(axis=0) - out.min(axis=0)
    assert np.allclose(sorted(span), [1.0, 2.0])
    out_v = arrange.align_islands(obj.mesh, rot, c, mode="V")
    span_v = out_v.max(axis=0) - out_v.min(axis=0)
    assert np.allclose(span_v, [1.0, 2.0])
    out_u = arrange.align_islands(obj.mesh, rot, c, mode="U")
    span_u = out_u.max(axis=0) - out_u.min(axis=0)
    assert np.allclose(span_u, [2.0, 1.0])


def test_align_points_and_straighten():
    uv = np.array([[0.0, 0.0], [1.0, 0.1], [2.0, -0.1], [3.0, 0.05], [9.0, 9.0]])
    a = arrange.align_points(uv, [0, 1, 2, 3], "V")
    assert np.allclose(a[:4, 1], uv[:4, 1].mean()) and np.allclose(a[:4, 0], uv[:4, 0])
    assert np.allclose(a[4], [9, 9])
    s = arrange.straighten(uv, [0, 1, 2, 3])
    assert np.allclose(s[:4, 1], s[0, 1])
    diag = np.array([[0.0, 0.0], [1.0, 1.05], [2.0, 1.95]])
    d = arrange.straighten(diag, [0, 1, 2], snap_degrees=5.0)
    v1 = d[1] - d[0]
    v2 = d[2] - d[0]
    assert abs(v1[0] * v2[1] - v1[1] * v2[0]) < 1e-12


def test_rectify_grid_island():
    mesh = grid_mesh(4, 3, 120.0)
    obj = make_obj(mesh)
    c = data.Corners(mesh)
    uv = project.project_flat(obj, "Z")
    rng = np.random.default_rng(11)
    groups = data.point_groups(c, uv)
    noise = rng.uniform(-0.03, 0.03, size=(groups.max() + 1, 2))
    noisy = uv + noise[groups]
    out, n = arrange.rectify(mesh, noisy, c)
    assert n == 1
    xs = np.unique(np.round(out[:, 0], 9))
    ys = np.unique(np.round(out[:, 1], 9))
    assert len(xs) == 5 and len(ys) == 4
    assert np.allclose(np.diff(xs), np.diff(xs)[0]) and np.allclose(np.diff(ys), np.diff(ys)[0])
    assert abs(np.diff(xs)[0] / np.diff(ys)[0] - 0.75) < 1e-9
    assert arrange.uv_stats(mesh, out)["max_conformal"] < 1 + 1e-6
    tri = make_obj(Mesh([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)]))
    _, n2 = arrange.rectify(tri.mesh, data.get_uv_array(tri))
    assert n2 == 0


def test_flip_rotate_fit():
    uv = np.array([[0.2, 0.2], [0.6, 0.2], [0.6, 0.4], [0.2, 0.4]])
    idx = [0, 1, 2, 3]
    f = arrange.flip(uv, idx, "U")
    assert np.allclose(f[:, 0], [0.6, 0.2, 0.2, 0.6]) and np.allclose(f[:, 1], uv[:, 1])
    fv = arrange.flip(uv, idx, "V")
    assert np.allclose(fv[:, 1], [0.4, 0.4, 0.2, 0.2])
    r = arrange.rotate90(uv, idx, clockwise=False)
    span = r.max(axis=0) - r.min(axis=0)
    assert np.allclose(span, [0.2, 0.4])
    assert np.allclose(r.mean(axis=0), uv.mean(axis=0))
    cw = arrange.rotate90(uv, idx, clockwise=True)
    assert np.allclose(arrange.rotate90(cw, idx, clockwise=False), uv)
    fit = arrange.fit_to_bounds(uv, idx, keep_aspect=True)
    assert np.allclose(fit.min(axis=0), [0.0, 0.25]) and np.allclose(fit.max(axis=0), [1.0, 0.75])
    fit2 = arrange.fit_to_bounds(uv, idx, keep_aspect=False, margin=0.1)
    assert np.allclose(fit2.min(axis=0), 0.1) and np.allclose(fit2.max(axis=0), 0.9)


def test_stitch_islands_along_edge():
    obj = make_obj(Mesh.cube(200.0))
    uv, _ = unwrap.unwrap(obj, angle=60.0)
    data.set_seams(obj, unwrap.angle_seams(obj.mesh, 60.0))
    c = data.Corners(obj.mesh)
    assert len(data.uv_islands(obj.mesh, uv, c)) == 6
    edge = (0, 3)
    out, welded = arrange.stitch_edges(obj.mesh, uv, [edge], c)
    assert edge in welded
    assert len(data.uv_islands(obj.mesh, out, c)) == 5
    for v in edge:
        cs = [k for k in range(c.count) if c.vertex[k] == v]
        polys_with_edge = [k for k in cs if c.poly[k] in (0, 2)]
        pts = out[polys_with_edge]
        assert np.allclose(pts, pts[0])
    st = arrange.uv_stats(obj.mesh, out)
    assert st["flipped"] == 0 and abs(st["mean_stretch"] - 1.0) < 1e-6
    arrange.remove_welded_seams(obj, welded)
    assert edge not in data.get_seams(obj)


def test_stitch_handles_mirrored_island():
    obj = make_obj(grid_mesh(2, 1, 100.0))
    c = data.Corners(obj.mesh)
    uv = np.array([[0, 0], [0.4, 0], [0.4, 0.8], [0, 0.8], [0.9, 0.1], [0.5, 0.1], [0.5, 0.9], [0.9, 0.9]], float)
    out, welded = arrange.stitch_edges(obj.mesh, uv, [(1, 4)], c, move="second")
    assert (1, 4) in welded
    assert len(data.uv_islands(obj.mesh, out, c)) == 1
    st = arrange.uv_stats(obj.mesh, out)
    assert st["flipped"] == 0


def test_uv_stats_flags_flips_and_bounds():
    obj = make_obj(half_grid(2, 1, 100.0))
    c = data.Corners(obj.mesh)
    uv = project.project_flat(obj, "Z")
    st = arrange.uv_stats(obj.mesh, uv)
    assert st["islands"] == 1 and st["flipped"] == 0 and st["out_of_bounds"] == 0
    assert abs(st["coverage"] - 0.5) < 0.02 and st["uv_points"] == 6
    bad = uv.copy()
    bad[4:8] = arrange.flip(bad, [4, 5, 6, 7], "U")[4:8] + [0.5, 0.0]
    st2 = arrange.uv_stats(obj.mesh, bad)
    assert st2["islands"] == 2 and st2["flipped"] == 0
    weird = uv.copy()
    weird[c.of(1).start:c.of(1).stop] = weird[[c.of(1).start + k for k in (1, 0, 3, 2)]]
    st3 = arrange.uv_stats(obj.mesh, weird)
    assert st3["flipped"] >= 0
    out = uv + 0.8
    assert arrange.uv_stats(obj.mesh, out)["out_of_bounds"] == 2
    stretch = arrange.polygon_stretch(obj.mesh, uv)
    assert np.allclose(stretch["area_log"], 0.0) and np.allclose(stretch["conformal"], 1.0)
    squash = uv.copy()
    squash[:4, 0] *= 0.5
    s2 = arrange.polygon_stretch(obj.mesh, squash)
    assert s2["area_log"][0] < 0 < s2["area_log"][1]


def test_checker_and_canvas_basics():
    px = texture.checker_pixels(64, 4, (1, 0, 0, 1), (0, 0, 1, 1))
    assert px.shape == (64, 64, 4)
    assert np.allclose(px[0, 0], [1, 0, 0, 1]) and np.allclose(px[0, 16], [0, 0, 1, 1])
    assert np.allclose(px[16, 16], [1, 0, 0, 1])
    img = texture.checker_image(32, 2)
    assert img.width() == 32 and QColor(img.pixel(0, 0)) != QColor(img.pixel(16, 0))
    canvas = texture.TextureCanvas(64, 32, (0.0, 0.0, 0.0, 1.0))
    assert canvas.width == 64 and canvas.height == 32
    x, y = canvas.uv_to_px(0.5, 0.5)
    assert (x, y) == (31.5, 15.5)
    assert np.allclose(canvas.px_to_uv(x, y), (0.5, 0.5))
    canvas.fill((0.25, 0.5, 0.75, 1.0))
    assert np.allclose(canvas.sample(0.3, 0.3), (0.25, 0.5, 0.75, 1.0))
    canvas.resize(16)
    assert canvas.width == 16 and canvas.height == 16
    canvas.clear()
    assert canvas.pixels[..., 3].max() == 0.0


def test_brush_dab_falloff_and_no_buildup():
    canvas = texture.TextureCanvas(64, 64, (0.0, 0.0, 0.0, 1.0))
    brush = texture.Brush(radius=10.0, hardness=0.5, opacity=1.0, color=(1.0, 1.0, 1.0, 1.0))
    canvas.dab(0.5, 0.5, brush)
    cx, cy = 32, 32
    assert canvas.pixels[cy, cx, 0] > 0.99
    assert canvas.pixels[cy, cx + 4, 0] > 0.99
    edge = canvas.pixels[cy, cx + 8, 0]
    assert 0.0 < edge < 0.5
    assert canvas.pixels[cy, cx + 12, 0] == 0.0
    canvas2 = texture.TextureCanvas(64, 64, (0.0, 0.0, 0.0, 1.0))
    half = texture.Brush(radius=6.0, hardness=1.0, opacity=0.5, color=(1, 1, 1, 1), spacing=0.1)
    canvas2.stroke([(0.5, 0.5), (0.5, 0.5), (0.52, 0.5), (0.5, 0.5)], half)
    assert abs(float(canvas2.pixels[cy, cx, 0]) - 0.5) < 0.01
    canvas2.dab(0.5, 0.5, half)
    assert abs(float(canvas2.pixels[cy, cx, 0]) - 0.75) < 0.01
    long = texture.TextureCanvas(128, 16, (0, 0, 0, 1))
    long.stroke([(0.1, 0.5), (0.9, 0.5)], texture.Brush(radius=3.0, hardness=1.0, color=(1, 0, 0, 1)))
    row = long.pixels[8, :, 0]
    assert row[16:110].min() > 0.99


def test_eraser_and_flood_fill():
    canvas = texture.TextureCanvas(32, 32, (1.0, 1.0, 1.0, 1.0))
    canvas.dab(0.5, 0.5, texture.Brush(radius=4.0, hardness=1.0, mode="erase"))
    assert canvas.pixels[16, 16, 3] < 0.01 and canvas.pixels[0, 0, 3] == 1.0
    fill = texture.TextureCanvas(32, 32, (0.0, 0.0, 0.0, 1.0))
    fill.pixels[:, 15:17] = (1.0, 1.0, 1.0, 1.0)
    n = fill.flood_fill(0.1, 0.5, (0.0, 1.0, 0.0, 1.0), tolerance=0.05)
    assert n == 32 * 15
    assert np.allclose(fill.pixels[5, 3], (0, 1, 0, 1)) and np.allclose(fill.pixels[5, 25], (0, 0, 0, 1))
    assert fill.flood_fill(2.0, 2.0, (1, 0, 0, 1)) == 0


def test_png_and_store_roundtrip():
    canvas = texture.TextureCanvas(16, 8, (0.0, 0.0, 0.0, 1.0))
    canvas.pixels[2, 3] = (1.0, 0.5, 0.0, 1.0)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "tex.png")
        assert canvas.save_png(path)
        back = texture.TextureCanvas.from_png(path)
        assert back.width == 16 and back.height == 8
        assert np.allclose(back.pixels, np.rint(canvas.pixels * 255) / 255, atol=1e-6)
        other = texture.TextureCanvas(4, 4)
        other.load_png(path)
        assert other.width == 16 and other.path == path
    obj = make_obj(grid_mesh(1, 1))
    texture.save_canvas(obj, "Color", canvas)
    assert texture.texture_channels(obj) == ["Color"]
    loaded = texture.load_canvas(obj, "Color")
    assert np.allclose(loaded.pixels[2, 3], (1.0, 128 / 255, 0.0, 1.0), atol=1e-6)
    json_rec = store.from_json(store.to_json(store.get_object(obj, texture.TEXTURES_KEY)))
    assert texture.TextureCanvas.from_record(json_rec["Color"]).width == 16
    assert texture.remove_canvas(obj, "Color") and texture.load_canvas(obj, "Color") is None


def test_uv_at_hit_and_projection_painting():
    scene = reset_scene()
    obj = scene.active
    obj.mesh = grid_mesh(1, 1, 100.0)
    project.project_flat(obj, "Z")
    hit = texture.uv_at_hit(obj, 0, (25.0, 75.0, 0.0))
    assert np.allclose(hit, (0.25, 0.75))
    obj.position = np.array([10.0, 0.0, 0.0])
    hit2 = texture.uv_at_hit(obj, 0, (35.0, 75.0, 0.0))
    assert np.allclose(hit2, (0.25, 0.75))
    canvas = texture.TextureCanvas(64, 64, (0, 0, 0, 1))
    res = texture.paint_ray(scene, (60.0, 50.0, -100.0), (0.0, 0.0, 1.0), canvas,
                            texture.Brush(radius=3.0, hardness=1.0, color=(1, 0, 0, 1)), obj=obj)
    assert np.allclose(res, (0.5, 0.5))
    assert canvas.pixels[32, 32, 0] > 0.99 and canvas.pixels[5, 5, 0] == 0.0
    assert texture.paint_ray(scene, (500.0, 500.0, -100.0), (0, 0, 1), canvas, texture.Brush()) is None


def test_session_selection_modes():
    mesh = half_grid(2, 1, 100.0)
    scene, s = fresh_scene(mesh)
    project.project_flat(scene.active, "Z")
    s.uvChanged.emit()
    s.set_select_mode("polygons")
    assert s.select_at(0.25, 0.5, 0.01)
    assert s.selected_polys == {0}
    s.select_at(0.75, 0.5, 0.01, add=True)
    assert s.selected_polys == {0, 1}
    s.select_at(0.75, 0.5, 0.01, remove=True)
    assert s.selected_polys == {0}
    s.set_select_mode("points")
    s.select_at(0.5, 0.25, 0.02)
    assert {int(s.corners().vertex[k]) for k in s.selected_corners} == {1}
    assert len(s.selected_corners) == 2
    assert s.select_box(-0.1, -0.1, 0.6, 0.3) == 3
    s.set_select_mode("islands")
    c = s.corners()
    uv = s.uv().copy()
    uv[4:8] += [1.5, 0.0]
    s.commit(uv)
    s.select_polys([1])
    assert s.selected_polys == {1}
    uv[4:8] -= [1.5, 0.0]
    s.commit(uv)
    s.select_polys([1])
    assert s.selected_polys == {0, 1}
    s.invert_selection()
    assert s.selected_polys == set()
    s.select_all()
    assert s.selected_polys == {0, 1} and len(s.selected_corners) == c.count
    s.clear_selection()
    assert not s.selected_corners


def test_session_operations_write_store_and_undo():
    scene, s = fresh_scene()
    obj = scene.active
    s.project("Box", atlas=True)
    assert data.has_uv(obj)
    stored = data.get_uv_array(obj)
    s.set_select_mode("polygons")
    s.select_polys([0])
    idx = s.affected()
    before = s.uv().copy()
    s.move(0.1, -0.05)
    after = data.get_uv_array(obj)
    assert np.allclose(after[idx], before[idx] + [0.1, -0.05])
    untouched = np.setdiff1d(np.arange(len(after)), idx)
    assert np.allclose(after[untouched], before[untouched])
    assert scene.can_undo()
    s.undo()
    assert np.allclose(data.get_uv_array(scene.active), stored)
    s.redo()
    assert np.allclose(data.get_uv_array(scene.active), after)
    s.clear_selection()
    lo0, hi0 = s.selection_bounds()
    s.rotate(90.0)
    s.scale(0.5)
    lo, hi = s.selection_bounds()
    assert np.allclose(hi - lo, (hi0 - lo0)[::-1] * 0.5)
    info = s.unwrap("Conformal", angle=60.0)
    assert info["islands"] == 6
    stats = s.stats()
    assert stats["islands"] == 6 and stats["seams"] == 0
    assert s.seams_by_angle(60.0) == 12 and len(s.seams()) == 12
    s.clear_seams()
    assert s.seams() == set()


def test_session_seams_from_scene_edges_and_islands():
    scene, s = fresh_scene()
    obj = scene.active
    scene.set_mode("edges")
    scene.select_components([(0, 3), (1, 2)])
    assert s.seams_from_selection() == 2
    assert data.get_seams(obj) == {(0, 3), (1, 2)}
    scene.select_components([(0, 3)])
    assert s.remove_selected_seams() == 1
    scene.clear_selection()
    s.project("Box", atlas=True)
    assert s.seams_from_islands() == 12


def test_session_texture_painting():
    scene, s = fresh_scene(grid_mesh(1, 1, 100.0))
    project.project_flat(scene.active, "Z")
    s.uvChanged.emit()
    canvas = s.new_canvas(64, fill=(0, 0, 0, 1))
    assert texture.texture_channels(scene.active) == ["Color"]
    s.set_tool("paint")
    s.set_brush(radius=4.0, hardness=1.0, color=(0.0, 1.0, 0.0, 1.0))
    s.paint_begin(0.25, 0.25)
    s.paint_move(0.75, 0.25)
    s.paint_end()
    c = s.canvas(create=False)
    y = int(round((1 - 0.25) * 64 - 0.5))
    assert c.pixels[y, 16:48, 1].min() > 0.99
    stored = texture.load_canvas(scene.active, "Color")
    assert np.allclose(stored.pixels[y, 30], (0, 1, 0, 1))
    s.set_tool("fill")
    s.set_brush(color=(1.0, 0.0, 0.0, 1.0), tolerance=0.05)
    s.paint_begin(0.5, 0.9)
    assert np.allclose(s.canvas().pixels[2, 2], (1, 0, 0, 1))
    s.set_tool("erase")
    s.fill_canvas()
    assert s.canvas().pixels[..., 3].max() == 0.0
    s.set_channel("Bump")
    assert s.canvas(create=False) is None
    assert s.canvas(create=True) is not None
    s.set_channel("Color")
    assert s.canvas(create=False) is canvas or s.canvas(create=False).width == 64
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "c.png")
        assert s.save_texture(path)
        s.fill_canvas()
        assert s.load_texture(path)
        assert s.canvas().path == path
    s.set_tool("paint")
    hit = s.paint_ray((50.0, 50.0, -50.0), (0.0, 0.0, 1.0))
    s.paint_end()
    assert np.allclose(hit, (0.5, 0.5))
    assert s.paint_ray((900.0, 50.0, -50.0), (0.0, 0.0, 1.0)) is None


def _press(widget, pos, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    QTest.mousePress(widget, button, mods, QPoint(int(pos[0]), int(pos[1])))


def _move(widget, pos, mods=Qt.KeyboardModifier.NoModifier):
    QTest.mouseMove(widget, QPoint(int(pos[0]), int(pos[1])))


def _release(widget, pos, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    QTest.mouseRelease(widget, button, mods, QPoint(int(pos[0]), int(pos[1])))


def test_uv_editor_view_interaction():
    scene, s = fresh_scene(grid_mesh(2, 1, 100.0))
    project.project_flat(scene.active, "Z")
    s.uvChanged.emit()
    view = UVEditorView(scene)
    view.resize(512, 600)
    view.show()
    APP.processEvents()
    cv = view.canvas
    cv.set_view(256.0, QPointF(64.0, 384.0))
    assert cv.to_uv(*cv.to_screen(0.3, 0.7)) == (0.3, 0.7) or np.allclose(cv.to_uv(*cv.to_screen(0.3, 0.7)), (0.3, 0.7))
    view.mode_buttons["polygons"].click()
    assert s.select_mode == "polygons"
    x, y = cv.to_screen(0.25, 0.5)
    _press(cv, (x, y))
    _release(cv, (x, y))
    assert s.selected_polys == {0}
    before = s.uv().copy()
    idx = s.affected()
    _press(cv, (x, y))
    _move(cv, (x + 32, y))
    _move(cv, (x + 64, y))
    _release(cv, (x + 64, y))
    after = data.get_uv_array(scene.active)
    assert np.allclose(after[idx, 0] - before[idx, 0], 64.0 / 256.0, atol=1e-9)
    assert np.allclose(after[idx, 1], before[idx, 1])
    view.tool_buttons["rotate"].click()
    assert s.tool == "rotate"
    lo, hi = s.selection_bounds()
    center = (lo + hi) / 2.0
    cx, cy = cv.to_screen(center[0], center[1])
    start = cv.to_screen(center[0] + 0.2, center[1])
    end = cv.to_screen(center[0], center[1] + 0.2)
    base = data.get_uv_array(scene.active)
    _press(cv, start)
    _move(cv, end)
    _release(cv, end)
    rotated = data.get_uv_array(scene.active)
    span0 = base[idx].max(axis=0) - base[idx].min(axis=0)
    span1 = rotated[idx].max(axis=0) - rotated[idx].min(axis=0)
    assert np.allclose(span1, span0[::-1], atol=1e-3)
    view.tool_buttons["scale"].click()
    rects = cv._handle_rects()
    br = rects["corners"]["br"].center()
    tl = rects["corners"]["tl"].center()
    mid = ((br.x() + tl.x()) / 2.0, (br.y() + tl.y()) / 2.0)
    pre = data.get_uv_array(scene.active)
    _press(cv, (br.x(), br.y()))
    _move(cv, mid)
    _release(cv, mid)
    post = data.get_uv_array(scene.active)
    s0 = pre[idx].max(axis=0) - pre[idx].min(axis=0)
    s1 = post[idx].max(axis=0) - post[idx].min(axis=0)
    assert np.all(s1 < s0 * 0.75)
    view.tool_buttons["select"].click()
    p0 = cv.to_screen(-0.2, -0.2)
    p1 = cv.to_screen(1.2, 1.2)
    s.clear_selection()
    _press(cv, p0)
    _move(cv, p1)
    _release(cv, p1)
    assert s.selected_polys == {0, 1}
    zoom = cv.zoom
    ev = QWheelEvent(QPointF(200, 200), cv.mapToGlobal(QPointF(200, 200)), QPoint(0, 0), QPoint(0, 120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(cv, ev)
    assert cv.zoom > zoom
    u_before = cv.to_uv(200, 200)
    assert np.allclose(u_before, cv.to_uv(200, 200))
    origin = QPointF(cv.origin)
    _press(cv, (100, 100), Qt.MouseButton.MiddleButton)
    _move(cv, (140, 120))
    _release(cv, (140, 120), Qt.MouseButton.MiddleButton)
    assert abs(cv.origin.x() - origin.x() - 40) < 1e-9 and abs(cv.origin.y() - origin.y() - 20) < 1e-9
    cv.setFocus()
    QTest.keyClick(cv, Qt.Key.Key_1)
    assert s.select_mode == "points"
    QTest.keyClick(cv, Qt.Key.Key_3)
    assert s.select_mode == "islands"
    QTest.keyClick(cv, Qt.Key.Key_E)
    assert s.tool == "move"
    QTest.keyClick(cv, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert s.selected_polys == {0, 1}
    pre_key = data.get_uv_array(scene.active)
    QTest.keyClick(cv, Qt.Key.Key_Right)
    assert np.allclose(data.get_uv_array(scene.active)[:, 0] - pre_key[:, 0], 1.0 / cv.zoom)
    QTest.keyClick(cv, Qt.Key.Key_Escape)
    assert not s.selected_corners
    QTest.keyClick(cv, Qt.Key.Key_H)
    assert np.allclose(cv.unit_rect().center().x(), cv.width() / 2.0)
    view.set_background("Grid")
    assert cv.background == "Grid" and view.background_actions["Grid"].isChecked()
    view.background_actions["Texture"].trigger()
    assert cv.background == "Texture"
    view.stretch_action.setChecked(True)
    assert cv.show_stretch
    view.frame_action.trigger()
    view.unit_action.trigger()
    view.select_all_action.trigger()
    assert s.selected_polys
    view.invert_action.trigger()
    view.deselect_action.trigger()
    assert not s.selected_corners
    img = view.grab()
    assert not img.isNull()
    view.undo_action.trigger()
    view.redo_action.trigger()
    view.close()


def test_uv_editor_paint_tool():
    scene, s = fresh_scene(grid_mesh(1, 1, 100.0))
    project.project_flat(scene.active, "Z")
    s.uvChanged.emit()
    s.new_canvas(64, fill=(0, 0, 0, 1))
    view = UVEditorView(scene)
    view.resize(512, 600)
    view.show()
    APP.processEvents()
    cv = view.canvas
    cv.set_view(256.0, QPointF(64.0, 384.0))
    view.tool_buttons["paint"].click()
    s.set_brush(radius=3.0, hardness=1.0, color=(1, 1, 0, 1))
    a = cv.to_screen(0.2, 0.5)
    b = cv.to_screen(0.8, 0.5)
    _press(cv, a)
    _move(cv, b)
    _release(cv, b)
    canvas = s.canvas(create=False)
    row = int(round(0.5 * 64 - 0.5))
    assert canvas.pixels[row, 14:50, 0].min() > 0.99
    assert texture.load_canvas(scene.active, "Color").pixels[row, 32, 1] > 0.99
    view.background_actions["Texture"].trigger()
    assert cv._texture_image() is not None
    view.grab()
    view.tool_buttons["fill"].click()
    s.set_brush(color=(0, 0, 1, 1))
    corner = cv.to_screen(0.05, 0.95)
    _press(cv, corner)
    _release(cv, corner)
    assert np.allclose(s.canvas().pixels[1, 1], (0, 0, 1, 1))
    view.close()


def test_uv_tools_panel_drives_every_operation():
    scene, s = fresh_scene(cylinder_mesh(50.0, 200.0, 12, 3))
    panel = UVToolsPanel(scene)
    panel.resize(320, 900)
    panel.show()
    APP.processEvents()
    obj = scene.active
    panel.proj_kind.setCurrentText("Cylindrical")
    panel.project_button.click()
    assert data.has_uv(obj)
    panel.proj_kind.setCurrentText("Frontal")
    panel.camera_provider = lambda: project.look_at((0.0, 0.0, -800.0), (0.0, 0.0, 0.0))
    panel.project_button.click()
    uv = data.get_uv_array(obj)
    assert np.allclose(uv.min(), 0.0) and np.allclose(uv.max(), 1.0)
    panel.reset_button.click()
    panel.tag_kind.setCurrentText("Flat")
    panel.tag_axis.setCurrentText("Z")
    panel.tag_tile_u.setValue(2.0)
    assert panel.tag_pending()
    panel.flush_tag()
    tag = project.get_tag(obj)
    assert tag["tiles"][0] == 2.0 and tag["axis"] == "Z"
    panel.tag_button.click()
    assert project.get_tag(obj)["projection"] == "UVW"
    assert data.get_uv_array(obj)[:, 0].max() > 1.45
    assert panel.tag_kind.currentText() == "UVW" and panel.tag_tile_u.value() == 1.0
    panel.seam_angle.setValue(60.0)
    panel.seam_by_angle.click()
    assert len(data.get_seams(obj)) == 24
    panel.unwrap_method.setCurrentText("Isometric")
    panel.unwrap_button.click()
    st = arrange.uv_stats(obj.mesh, data.get_uv_array(obj))
    assert st["islands"] == 3 and st["flipped"] == 0
    panel.seam_clear.click()
    assert data.get_seams(obj) == set()
    panel.seam_islands.click()
    assert len(data.get_seams(obj)) >= 24
    scene.set_mode("edges")
    scene.select_components([obj.mesh.polygons[0][:2]])
    panel.seam_remove.click()
    panel.seam_add.click()
    scene.clear_selection()
    panel.relax_iter.setValue(5)
    panel.relax_method.setCurrentText("Springs")
    panel.relax_button.click()
    panel.relax_method.setCurrentText("ARAP")
    panel.relax_pin_boundary.setChecked(True)
    panel.relax_button.click()
    panel.pack_margin.setValue(0.02)
    panel.pack_align.setChecked(True)
    panel.pack_button.click()
    uv = data.get_uv_array(obj)
    assert uv.min() >= -1e-9 and uv.max() <= 1 + 1e-9
    panel.align_mode.setCurrentText("U")
    panel.align_button.click()
    panel.rectify_button.click()
    assert "Rectified" in s.last_message
    before = data.get_uv_array(obj).copy()
    panel.flip_u.click()
    panel.flip_u.click()
    assert np.allclose(data.get_uv_array(obj), before)
    panel.flip_v.click()
    panel.flip_v.click()
    panel.rot_cw.click()
    panel.rot_ccw.click()
    assert np.allclose(data.get_uv_array(obj), before, atol=1e-12)
    panel.move_u.setValue(0.1)
    panel.move_button.click()
    assert np.allclose(data.get_uv_array(obj)[:, 0], before[:, 0] + 0.1)
    panel.rot_angle.setValue(180.0)
    panel.rotate_button.click()
    panel.scale_u.setValue(0.5)
    panel.scale_v.setValue(0.5)
    panel.scale_button.click()
    panel.fit_margin.setValue(0.1)
    panel.fit_button.click()
    uv = data.get_uv_array(obj)
    assert abs(uv.min() - 0.1) < 1e-9 or abs(max(uv.max(axis=0)) - 0.9) < 1e-9
    s.set_select_mode("points")
    s.select_corners(range(4))
    panel.align_u.click()
    sel = s.affected()
    assert np.allclose(data.get_uv_array(obj)[sel, 0], data.get_uv_array(obj)[sel[0], 0])
    panel.align_v.click()
    panel.straighten_button.click()
    s.clear_selection()
    panel.seam_by_angle.click()
    panel.unwrap_button.click()
    islands_before = len(data.uv_islands(obj.mesh, data.get_uv_array(obj)))
    cap = len(obj.mesh.polygons) - 1
    side = 0
    shared = set(obj.mesh.polygons[cap]) & set(obj.mesh.polygons[[k for k in range(len(obj.mesh.polygons) - 2)
                                                                 if len(set(obj.mesh.polygons[k]) & set(obj.mesh.polygons[cap])) == 2][0]])
    scene.set_mode("edges")
    scene.select_components([tuple(sorted(shared))])
    panel.stitch_move.setCurrentText("smaller")
    panel.stitch_button.click()
    scene.clear_selection()
    assert len(data.uv_islands(obj.mesh, data.get_uv_array(obj))) == islands_before - 1
    del side
    stats = panel.refresh_stats()
    assert panel.stat_values["islands"].text() == str(stats["islands"])
    assert panel.stat_values["coverage"].text().endswith("%")
    panel.stats_button.click()
    panel.groups["Statistics"].toggle()
    panel.close()


def test_texture_paint_panel_controls():
    scene, s = fresh_scene(grid_mesh(1, 1, 100.0))
    project.project_flat(scene.active, "Z")
    panel = TexturePaintPanel(scene)
    panel.resize(320, 700)
    panel.show()
    APP.processEvents()
    panel.size_combo.setCurrentText("256")
    assert s.texture_size == 256
    panel.new_button.click()
    assert s.canvas(create=False).width == 256
    panel.cells_spin.setValue(4)
    panel.checker_button.click()
    c = s.canvas(create=False)
    assert not np.allclose(c.pixels[0, 0], c.pixels[0, 70])
    panel.size_combo.setCurrentText("512")
    assert s.canvas(create=False).width == 512
    panel.clear_button.click()
    assert s.canvas().pixels[..., 3].max() == 0.0
    panel.set_color(QColor(255, 0, 0))
    assert np.allclose(s.brush.color, (1, 0, 0, 1))
    assert panel.color_button.text() == "#FF0000"
    panel.radius_spin.setValue(20.0)
    panel.hardness_spin.setValue(80.0)
    panel.opacity_spin.setValue(50.0)
    panel.spacing_spin.setValue(10.0)
    panel.tolerance_spin.setValue(20.0)
    assert (s.brush.radius, s.brush.hardness, s.brush.opacity) == (20.0, 0.8, 0.5)
    assert abs(s.brush.spacing - 0.1) < 1e-12 and abs(s.brush.tolerance - 0.2) < 1e-12
    panel.tool_chips["erase"].click()
    assert s.tool == "erase"
    panel.tool_chips["paint"].click()
    panel.opacity_spin.setValue(100.0)
    panel.fill_button.click()
    assert np.allclose(s.canvas().pixels[10, 10], (1, 0, 0, 1))
    panel.channel_combo.setCurrentText("Roughness")
    assert s.channel == "Roughness"
    assert "No Roughness" in panel.info.text()
    panel.channel_combo.setCurrentText("Color")
    assert "512 x 512" in panel.info.text()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "paint.png")
        assert panel.save_to(path)
        panel.clear_button.click()
        assert panel.load_from(path)
        assert np.allclose(s.canvas().pixels[10, 10], (1, 0, 0, 1))
        assert path in panel.info.text()
    panel.project_check.setChecked(True)
    assert s.project_paint is True
    s.set_tool("select")
    assert not any(ch.isChecked() for ch in panel.tool_chips.values())
    panel.close()


def test_viewport_painter_event_filter():
    scene, s = fresh_scene(grid_mesh(1, 1, 100.0))
    project.project_flat(scene.active, "Z")
    s.new_canvas(64, fill=(0, 0, 0, 1))

    class FakeViewport(QWidget):
        def ray_at(self, pos):
            return (np.array([pos.x(), 100.0 - pos.y(), -100.0]), np.array([0.0, 0.0, 1.0]))

    vp = FakeViewport()
    vp.resize(100, 100)
    vp.show()
    painter = ViewportPainter(vp, scene)
    s.set_tool("paint")
    s.set_brush(radius=2.0, hardness=1.0, color=(0, 1, 1, 1))
    _press(vp, (10, 50))
    _release(vp, (10, 50))
    assert s.canvas().pixels[32, 6, 1] < 0.5
    s.project_paint = True
    _press(vp, (10, 50))
    _move(vp, (90, 50))
    _release(vp, (90, 50))
    row = s.canvas().pixels[int(round(0.5 * 64 - 0.5)), :, 1]
    assert row[8:56].min() > 0.99
    assert texture.load_canvas(scene.active, "Color").pixels[31, 32, 2] > 0.99
    del painter
    vp.close()


def test_commands_docks_pages_contract():
    cmds = uvpkg.commands()
    assert len(cmds) >= 25
    paths = [p for p, _ in cmds]
    assert len(set(paths)) == len(paths)
    assert all(isinstance(p, tuple) and p[0] in ("UV", "Texture") for p in paths)
    scene, s = fresh_scene()
    for path, fn in cmds:
        fn(scene)
    assert data.has_uv(scene.active)
    assert texture.texture_channels(scene.active) == ["Color"]
    titles = []
    for title, factory, area in uvpkg.docks():
        assert area in ("left", "right", "bottom")
        w = factory(scene)
        assert isinstance(w, QWidget)
        w2 = factory()
        assert isinstance(w2, QWidget)
        titles.append(title)
        w.close()
        w2.close()
    assert uvpkg.pages() == [("UV Edit", ["UV Editor", "UV Tools", "Texture Paint"])]
    assert set(uvpkg.pages()[0][1]) == set(titles)
    for name, shortcut, fn in uvpkg.key_actions():
        assert name and shortcut
        fn(scene)


def _moved_polys(c, before, after):
    delta = np.abs(np.asarray(after) - np.asarray(before)).max(axis=1)
    per = np.zeros(c.poly_count)
    np.maximum.at(per, c.poly, delta)
    return sorted(np.nonzero(per > 1e-9)[0].tolist())


def test_stitch_moves_the_requested_island():
    m = grid_mesh(3, 1)
    o = SceneObject("T", m)
    uv, _ = unwrap.unwrap(o, seams={(1, 5)}, write=False)
    c = data.Corners(m)
    islands = data.uv_islands(m, uv, c)
    assert sorted(len(i) for i in islands) == [1, 2]
    first_poly = int(c.poly[c.edges()[(1, 5)][0]])
    small = [i for i in islands if len(i) == 1][0]
    first = [i for i in islands if first_poly in i][0]
    second = [i for i in islands if first_poly not in i][0]
    for mode, expect in (("smaller", small), ("first", first), ("second", second)):
        out, welded = arrange.stitch_edges(m, uv, [(1, 5)], c, move=mode)
        assert (1, 5) in welded
        assert _moved_polys(c, uv, out) == sorted(expect), mode
        assert len(data.uv_islands(m, out, c)) == 1
    out, _ = arrange.stitch_edges(m, uv, [(1, 5)], c)
    assert _moved_polys(c, uv, out) == sorted(small)
    scene, s = fresh_scene(grid_mesh(3, 1))
    data.set_seams(scene.active, [(1, 5)])
    s.unwrap("Conformal")
    before = s.uv().copy()
    scene.selected_edges = {(1, 5)}
    assert s.stitch() >= 1
    assert _moved_polys(s.corners(), before, s.uv()) == sorted(small)


def _wrap_mismatch(c, uv, skip=()):
    worst = 0.0
    for v in np.unique(c.vertex).tolist():
        if v in skip:
            continue
        us = uv[c.vertex == v, 0]
        d = np.abs(us - us[0]) % 1.0
        worst = max(worst, float(np.minimum(d, 1.0 - d).max()))
    return worst


def test_wrapped_projections_fit_without_breaking_the_seam():
    m = cylinder_mesh(50.0, 200.0, 16, 4, caps=False)
    o = SceneObject("T", m)
    c = data.Corners(m)
    uv = project.project(o, "Cylindrical", write=False)
    raw = project.project(o, "Cylindrical", fit=False, write=False)
    assert abs(uv[:, 0].min()) < 1e-9 and abs(uv[:, 0].max() - 1.0) < 1e-9
    assert _wrap_mismatch(c, uv) < 1e-9 and _wrap_mismatch(c, raw) < 1e-9
    shift = uv[:, 0] - raw[:, 0]
    assert np.allclose(shift, shift[0])
    assert abs(uv[:, 1].min()) < 1e-9 and abs(uv[:, 1].max() - 1.0) < 1e-9
    half = [r * 16 + k for r in range(4) for k in range(8)]
    part = project.project(o, "Cylindrical", half, write=False)
    idx = data.corners_of_polys(c, half)
    assert abs(part[idx, 0].min()) < 1e-9 and abs(part[idx, 0].max() - 1.0) < 1e-9
    sm = sphere_mesh(100.0, 16, 8)
    so = SceneObject("S", sm)
    scs = data.Corners(sm)
    su = project.project(so, "Spherical", write=False)
    sraw = project.project(so, "Spherical", fit=False, write=False)
    poles = {0, len(sm.points) - 1}
    assert abs(su[:, 0].min()) < 1e-9
    assert _wrap_mismatch(scs, su, poles) < 1e-9
    keep = ~np.isin(scs.vertex, list(poles))
    d = su[keep, 0] - sraw[keep, 0]
    assert np.allclose(d, d[0])
    project.set_tag(o, projection="Cylindrical")
    assert _wrap_mismatch(c, project.tag_coords(o)) < 1e-9


def test_session_corners_cache_sees_in_place_polygon_edits():
    sc = reset_scene()
    s = session_for(sc)
    c1 = s.corners()
    o = sc.active
    o.mesh.polygons[0] = tuple(reversed(o.mesh.polygons[0]))
    c2 = s.corners()
    assert c2 is not c1
    assert np.array_equal(c2.vertex, data.Corners(o.mesh).vertex)
    assert s.corners() is c2
    o.mesh = Mesh(o.mesh.points.copy(), list(o.mesh.polygons))
    assert np.array_equal(s.corners().vertex, data.Corners(o.mesh).vertex)


def test_unwrap_and_pack_of_selection_avoid_other_islands():
    o = make_obj(Mesh.cube(200.0))
    unwrap.unwrap(o, angle=60.0)
    base = data.get_uv_array(o)
    assert arrange.uv_stats(o.mesh, base)["overlap"] == 0.0
    uv, _ = unwrap.unwrap(o, polys=[0, 1], angle=60.0, write=False)
    st = arrange.uv_stats(o.mesh, uv)
    assert st["overlap"] < 1e-3 and st["out_of_bounds"] == 0
    c = data.Corners(o.mesh)
    rest = data.corners_of_polys(c, range(2, 6))
    assert np.allclose(uv[rest], base[rest])
    scene, s = fresh_scene(Mesh.cube(200.0))
    s.unwrap("Conformal", angle=60.0)
    s.set_select_mode("islands")
    s.select_polys([0])
    chosen = sorted(s.selected_polys)
    before = s.uv().copy()
    s.pack()
    after = s.uv()
    st = arrange.uv_stats(scene.active.mesh, after)
    assert st["overlap"] < 1e-3 and st["out_of_bounds"] == 0
    cc = s.corners()
    others = data.corners_of_polys(cc, [p for p in range(6) if p not in chosen])
    assert np.allclose(after[others], before[others])
    mine = data.corners_of_polys(cc, chosen)
    span = after[mine].max(axis=0) - after[mine].min(axis=0)
    assert span.max() < 0.6
    a3 = data.polygon_area_3d(scene.active.mesh, cc)
    auv = np.abs(data.polygon_area_uv(after, cc))
    dens_sel = auv[chosen].sum() / a3[chosen].sum()
    rest_polys = [p for p in range(6) if p not in chosen]
    dens_rest = auv[rest_polys].sum() / a3[rest_polys].sum()
    assert dens_sel <= dens_rest * (1 + 1e-6)
    s.select_all()
    s.pack()
    assert arrange.uv_stats(scene.active.mesh, s.uv())["overlap"] == 0.0
    flat, s2 = fresh_scene(grid_mesh(2, 1))
    s2.select_polys([0])
    s2.pack()
    assert np.isfinite(s2.uv()).all()


def test_single_actions_record_single_undo_steps():
    scene, s = fresh_scene(Mesh.cube(200.0))
    data.set_seams(scene.active, unwrap.angle_seams(scene.active.mesh, 60.0))
    s.unwrap("Conformal")
    seams_before = data.get_seams(scene.active)
    uv_before = s.uv().copy()
    scene.selected_edges = {sorted(seams_before)[0]}
    n0 = len(scene._undo)
    assert s.stitch() >= 1
    assert len(scene._undo) == n0 + 1
    assert data.get_seams(scene.active) != seams_before
    assert s.undo()
    assert data.get_seams(scene.active) == seams_before
    assert np.allclose(data.get_uv_array(scene.active), uv_before)
    scene.selected_edges = set()
    project.set_tag(scene.active, projection="Flat", tiles=[2.0, 2.0])
    n1 = len(scene._undo)
    assert s.uvw_from_tag()
    assert len(scene._undo) == n1 + 1
    assert project.get_tag(scene.active)["projection"] == "UVW"
    assert s.undo()
    assert project.get_tag(scene.active)["projection"] == "Flat"
    panel = UVToolsPanel(scene)
    n2 = len(scene._undo)
    for k in range(5):
        panel.tag_tile_u.setValue(1.0 + 0.5 * (k + 1))
    assert panel.tag_pending()
    assert len(scene._undo) == n2
    panel.flush_tag()
    assert len(scene._undo) == n2 + 1
    assert project.get_tag(scene.active)["tiles"][0] == 3.5
    n3 = len(scene._undo)
    panel.tag_button.click()
    assert len(scene._undo) == n3 + 1
    panel.close()


def test_session_undo_and_external_writes_on_any_scene():
    sc = Scene()
    s = session_for(sc)
    before = s.uv().copy()
    n0 = len(sc._undo)
    s.unwrap("Conformal")
    assert len(sc._undo) == n0 + 1 and sc.can_undo()
    assert not np.allclose(s.uv(), before)
    assert s.undo()
    assert np.allclose(s.uv(), before)
    assert s.redo()
    assert not np.allclose(s.uv(), before)
    sc2 = reset_scene()
    s2 = session_for(sc2)
    s2.unwrap("Conformal")
    other = s2.uv() * 0.5 + 0.1
    sc2.set_object_extra(sc2.active, "uv", data.array_to_uv(other, s2.corners()))
    assert np.allclose(s2.uv(), other)
    s2.move(0.1, 0.0)
    assert np.allclose(data.get_uv_array(sc2.active)[:, 0], other[:, 0] + 0.1)
    sc2.set_object_extra(sc2.active, "uv_seams", [[0, 1]])
    assert s2.seams() == {(0, 1)}


def test_sessions_and_canvases_are_released():
    gc.collect()
    sc = reset_scene()
    session_for(sc)
    gc.collect()
    n0 = len(store._LISTENERS)
    refs = []
    for _ in range(3):
        refs.append(weakref.ref(sc))
        sc = reset_scene()
        session_for(sc)
    gc.collect()
    assert len(store._LISTENERS) == n0
    assert all(r() is None for r in refs)
    s = session_for(sc)
    s.new_canvas(64)
    for _ in range(3):
        s.fill_canvas()
        sc.undo()
        assert s.canvas() is not None
    gc.collect()
    assert s.cached_canvas_count() <= 1


def test_color_tuple_stroke_memory_wrap_and_chunked_fill():
    assert texture.color_tuple((2.0, 0.5, 0.5)) == (1.0, 0.5, 0.5, 1.0)
    assert np.allclose(texture.color_tuple((255, 128, 0)), (1.0, 128 / 255.0, 0.0, 1.0))
    assert texture.color_tuple((1, 1, 1)) == (1.0, 1.0, 1.0, 1.0)
    assert np.allclose(texture.color_tuple(np.array([0.2, 0.4, 0.6], np.float32)), (0.2, 0.4, 0.6, 1.0))
    assert texture.color_tuple((float("nan"), 0.5, 0.5))[0] == 0.0
    canvas = texture.TextureCanvas(1024, 1024, (0, 0, 0, 1))
    brush = texture.Brush(radius=12.0, hardness=0.5, opacity=0.6, color=(1, 0, 0, 1))
    canvas.begin_stroke(brush)
    for k in range(20):
        canvas.stroke_to(0.3 + 0.01 * k, 0.5)
    for k in range(20):
        canvas.stroke_to(0.5 - 0.01 * k, 0.5)
    assert 0 < canvas.stroke_memory() < canvas.pixels.nbytes // 16
    canvas.end_stroke()
    assert canvas.stroke_memory() == 0
    assert abs(float(canvas.pixels[..., 0].max()) - 0.6) < 1e-5
    x, y = canvas.uv_to_px(0.4, 0.5)
    assert abs(float(canvas.pixels[int(round(y)), int(round(x)), 0]) - 0.6) < 1e-5
    assert float(canvas.pixels[100, 100, 0]) == 0.0
    wrap = texture.TextureCanvas(64, 64, (0, 0, 0, 1))
    wrap.dab(0.0, 0.5, texture.Brush(radius=6.0, hardness=1.0, color=(1, 1, 1, 1), wrap=True))
    assert wrap.pixels[32, 0, 0] > 0.9 and wrap.pixels[32, 63, 0] > 0.9
    plain = texture.TextureCanvas(64, 64, (0, 0, 0, 1))
    plain.dab(0.0, 0.5, texture.Brush(radius=6.0, hardness=1.0, color=(1, 1, 1, 1)))
    assert plain.pixels[32, 0, 0] > 0.9 and plain.pixels[32, 63, 0] == 0.0
    big = texture.TextureCanvas(700, 900)
    big.fill((0, 1, 0, 1), 0.5)
    assert np.allclose(big.pixels, (0.25, 0.75, 0.25, 1.0), atol=1e-6)
    big.clear()
    n = big.flood_fill(0.5, 0.5, (1, 0, 0, 1), 0.1, 1.0)
    assert n == 700 * 900 and np.allclose(big.pixels[450, 350], (1, 0, 0, 1))


def test_texture_panel_keeps_aspect_and_follows_brush():
    scene, s = fresh_scene(grid_mesh(1, 1, 100.0))
    project.project_flat(scene.active, "Z")
    panel = TexturePaintPanel(scene)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "wide.png")
        assert texture.TextureCanvas(300, 200, (0.2, 0.4, 0.6, 1.0)).save_png(path)
        assert panel.load_from(path)
    c = s.canvas(create=False)
    assert (c.width, c.height) == (300, 200)
    panel.size_combo.setCurrentText("512")
    c = s.canvas(create=False)
    assert (c.width, c.height) == (512, 341)
    assert "512 x 341" in panel.info.text()
    s.set_brush(radius=33.0, opacity=0.25, hardness=0.1, wrap=True)
    assert panel.radius_spin.value() == 33.0 and panel.opacity_spin.value() == 25.0
    assert abs(panel.hardness_spin.value() - 10.0) < 1e-9 and panel.wrap_check.isChecked()
    s.set_brush(color=(0.0, 0.0, 1.0, 1.0))
    assert panel.color_button.text() == "#0000FF"
    panel.wrap_check.setChecked(False)
    assert s.brush.wrap is False
    panel.close()


def test_non_finite_points_do_not_poison_uvs():
    nan = float("nan")
    tri = Mesh([(0, 0, 0), (1, 0, 0), (nan, 1, 0)], [(0, 1, 2)])
    grid = grid_mesh(2, 2, 100.0)
    pts = grid.points.copy()
    pts[4] = (nan, nan, nan)
    grid.points = pts
    for m in (tri, grid):
        o = make_obj(m)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert np.isfinite(data.get_uv_array(o)).all()
            for kind in project.PROJECTIONS:
                assert np.isfinite(project.project(o, kind, write=False)).all(), kind
            uv, _ = unwrap.unwrap(o, write=False)
            assert np.isfinite(uv).all()
            data.set_uv_array(o, uv)
            for method in unwrap.RELAX_METHODS:
                assert np.isfinite(unwrap.relax(o, method=method, write=False)).all(), method
            c = data.Corners(m)
            assert np.isfinite(arrange.pack_islands(m, uv, c)).all()
            assert np.isfinite(arrange.rectify(m, uv, c)[0]).all()
            assert np.isfinite(arrange.align_islands(m, uv, c)).all()
            bad = uv.copy()
            bad[0] = nan
            data.point_groups(c, bad)
            st = arrange.uv_stats(m, bad)
            assert all(math.isfinite(float(v)) for v in st.values())
        casts = [w for w in caught if "cast" in str(w.message) or "invalid value" in str(w.message)]
        assert not casts, [str(w.message) for w in casts]


def _reference_islands(mesh, uv, eps=1e-6):
    c = data.Corners(mesh)
    uf = data.UnionFind(c.poly_count)
    for _key, cs in c.edges().items():
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                a1, b1 = cs[i], int(c.next[cs[i]])
                if c.vertex[cs[j]] == c.vertex[a1]:
                    a2, b2 = cs[j], int(c.next[cs[j]])
                else:
                    a2, b2 = int(c.next[cs[j]]), cs[j]
                if np.abs(uv[a1] - uv[a2]).max() <= eps and np.abs(uv[b1] - uv[b2]).max() <= eps:
                    uf.union(int(c.poly[cs[i]]), int(c.poly[cs[j]]))
    groups = {}
    for p in range(c.poly_count):
        groups.setdefault(uf.find(p), []).append(p)
    return sorted(groups.values(), key=lambda g: g[0])


def _reference_coverage(uv, tris, grid):
    counts = np.zeros((grid, grid), dtype=int)
    cover = np.zeros((grid, grid), dtype=bool)
    centers = (np.arange(grid) + 0.5) / grid
    X, Y = np.meshgrid(centers, centers)
    for t in tris:
        a, b, c = uv[t]
        det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(det) < 1e-300:
            continue
        w1 = ((b[0] - X) * (c[1] - Y) - (b[1] - Y) * (c[0] - X)) / det
        w2 = ((c[0] - X) * (a[1] - Y) - (c[1] - Y) * (a[0] - X)) / det
        w3 = 1 - w1 - w2
        cover |= (w1 >= -1e-12) & (w2 >= -1e-12) & (w3 >= -1e-12)
        counts += (w1 > 1e-9) & (w2 > 1e-9) & (w3 > 1e-9)
    return cover.mean(), (counts > 1).mean()


def test_vectorized_islands_and_coverage_match_reference():
    rng = np.random.default_rng(7)
    m = grid_mesh(6, 5)
    o = make_obj(m)
    c = data.Corners(m)
    uv = project.project_flat(o, "Z")
    for p in rng.choice(c.poly_count, 8, replace=False).tolist():
        uv[list(c.of(p))] += rng.uniform(-0.2, 0.2, 2)
    assert data.uv_islands(m, uv, c) == _reference_islands(m, uv)
    sub = [0, 1, 2, 7, 8, 20]
    got = data.uv_islands(m, uv, c, sub)
    assert sorted(p for g in got for p in g) == sorted(sub)
    tris, _ = data.mesh_triangles(m, c)
    scatter = rng.uniform(-0.1, 1.1, size=uv.shape)
    for arr in (uv, scatter):
        assert np.allclose(arrange._coverage(arr, tris, 32), _reference_coverage(arr, tris, 32))
    from quartz_studio.uv.editor import np_polygon
    xy = rng.uniform(-50, 50, size=(9, 2))
    poly = np_polygon(xy)
    assert poly.size() == 9 and all(abs(poly.at(k).x() - xy[k, 0]) < 1e-12 and
                                     abs(poly.at(k).y() - xy[k, 1]) < 1e-12 for k in range(9))
    assert np_polygon(np.zeros((0, 2))).size() == 0


def test_editor_drag_keeps_overlay_and_stays_fast():
    scene, s = fresh_scene(grid_mesh(40, 40))
    t = time.perf_counter()
    s.unwrap("Conformal")
    assert time.perf_counter() - t < 4.0
    view = UVEditorView(scene)
    view.resize(700, 700)
    view.show()
    APP.processEvents()
    cv = view.canvas
    s.set_tool("move")
    s.select_all()
    cv.repaint()
    key0 = cv.overlay_key()
    overlay0 = cv._overlay_data()
    center = cv.rect().center()
    _press(cv, (center.x(), center.y()))
    t = time.perf_counter()
    for k in range(5):
        _move(cv, (center.x() + 4 * k + 4, center.y()))
        cv.repaint()
    per_frame = (time.perf_counter() - t) / 5
    assert cv.overlay_key() == key0 and cv._overlay_data() is overlay0
    _release(cv, (center.x() + 24, center.y()))
    assert cv.overlay_key() != key0
    assert per_frame < 0.25, per_frame
    panel = UVToolsPanel(scene)
    t = time.perf_counter()
    first = panel.refresh_stats()
    assert time.perf_counter() - t < 1.0
    t = time.perf_counter()
    assert panel.refresh_stats() == first
    assert time.perf_counter() - t < 0.05
    s.set_select_mode("points")
    c = s.corners()
    shared = [k for k in range(c.count) if c.vertex[k] == 42]
    s.select_corners(shared)
    assert len(shared) == 4 and s.selected_point_count() == 1
    cv.repaint()
    view.close()
    panel.close()


def test_no_comments_and_pixel_norm_in_package():
    root = os.path.join(STUDIO_ROOT, "quartz_studio", "uv")
    allowed = {1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 88, 96,
               112, 120, 128, 256, 512}
    for name in os.listdir(root):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(root, name), encoding="utf-8").read()
        for line in text.splitlines():
            stripped = line.strip()
            assert not stripped.startswith("#"), (name, line)
            assert '"""' not in stripped and "'''" not in stripped, (name, line)
        for m in re.finditer(r"(\d+)px", text):
            assert int(m.group(1)) in allowed, (name, m.group(0))
        for m in re.finditer(r"setFixed(?:Height|Width)\((\d+)\)|setContentsMargins\(([\d, ]+)\)|setSpacing\((\d+)\)|setPixelSize\((\d+)\)", text):
            nums = [int(x) for g in m.groups() if g for x in re.findall(r"\d+", g)]
            for v in nums:
                assert v == 0 or v in allowed, (name, m.group(0))


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
