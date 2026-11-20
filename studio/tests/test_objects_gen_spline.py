from __future__ import annotations

import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.path.isdir("C:/Windows/Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio.objects import registry
from quartz_studio.scene import Mesh


def _scene():
    QApplication.instance() or QApplication([sys.argv[0]])
    return scene_mod.reset_scene()


def _poly(points, closed=True, z=0.0) -> Mesh:
    pts = [(p[0], p[1], z) if len(p) == 2 else tuple(p) for p in points]
    n = len(pts)
    edges = [(i, i + 1) for i in range(n - 1)]
    if closed:
        edges.append((n - 1, 0))
    return Mesh(pts, [], edges)


def _square(side: float, cx=0.0, cy=0.0, ccw=True) -> Mesh:
    h = side / 2.0
    pts = [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
    return _poly(pts if ccw else pts[::-1])


def _circle(r: float, n: int, plane: str = "xy", center=(0.0, 0.0, 0.0)) -> Mesh:
    pts = []
    for k in range(n):
        a = 2.0 * math.pi * k / n
        c, s = r * math.cos(a), r * math.sin(a)
        if plane == "xy":
            q = (c, s, 0.0)
        elif plane == "xz":
            q = (c, 0.0, s)
        else:
            q = (0.0, c, s)
        pts.append((q[0] + center[0], q[1] + center[1], q[2] + center[2]))
    return _poly(pts)


def _make(kind: str, *splines: Mesh, **params):
    scene = _scene()
    objs = [scene.add_object(f"S{i}", m) for i, m in enumerate(splines)]
    gen = scene.add_parametric(kind, adopt=objs[0])
    for o in objs[1:]:
        scene.set_parent(o, gen)
    for key, value in params.items():
        scene.set_param(gen, key, value)
    return scene, gen


def _find(scene, kind: str):
    return next(o for o in scene.objects if o.kind == kind)


def _volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        p0 = mesh.points[poly[0]]
        for k in range(1, len(poly) - 1):
            total += float(p0 @ np.cross(mesh.points[poly[k]], mesh.points[poly[k + 1]]))
    return total / 6.0


def _closed(mesh: Mesh) -> bool:
    directed: set[tuple[int, int]] = set()
    count: dict[tuple[int, int], int] = {}
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a, b) in directed:
                return False
            directed.add((a, b))
            key = (a, b) if a < b else (b, a)
            count[key] = count.get(key, 0) + 1
    return bool(directed) and all(v == 2 for v in count.values()) and all((b, a) in directed for a, b in directed)


def _euler(mesh: Mesh) -> int:
    return len(mesh.points) - len(mesh.edges) + len(mesh.polygons)


def _clean(mesh: Mesh) -> bool:
    keys = {tuple(round(float(v), 6) for v in p) for p in mesh.points}
    if len(keys) != len(mesh.points):
        return False
    used = {i for poly in mesh.polygons for i in poly}
    if len(used) != len(mesh.points):
        return False
    return all(float(np.linalg.norm(n)) > 0.5 for n in mesh.polygon_normals())


def _solid(mesh: Mesh) -> bool:
    return _clean(mesh) and _closed(mesh) and _volume(mesh) > 0


def _shoelace(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(b))


def test_specs_registered():
    for key, cat, inputs in (("extrude", "generator", "children"), ("lathe", "generator", "children"),
                             ("sweep", "generator", "children"), ("loft", "generator", "children"),
                             ("text_spline", "spline", "none"), ("text", "mesh", "none")):
        spec = registry.get(key)
        assert spec.category == cat and spec.inputs == inputs, key
    d = registry.defaults("extrude")
    assert d["movement"] == (0.0, 0.0, 20.0) and d["subdivision"] == 1
    assert d["start_cap"] and d["end_cap"] and not d["hierarchical"]
    d = registry.defaults("lathe")
    assert d["angle"] == 360.0 and d["subdivision"] == 32 and d["movement"] == 0.0 and d["scale"] == 100.0
    d = registry.defaults("sweep")
    assert (d["end_scale"], d["end_rotation"], d["start_growth"], d["end_growth"], d["caps"]) == (
        100.0, 0.0, 0.0, 100.0, True)
    d = registry.defaults("loft")
    assert (d["subdivision_u"], d["subdivision_v"], d["loop"], d["caps"]) == (30, 10, False, True)
    d = registry.defaults("text")
    assert d["text"] == "Text" and d["height"] == 200.0 and d["font"] == "Arial"
    assert d["horizontal_spacing"] == 0.0 and d["align"] == "Left" and d["depth"] == 20.0
    assert registry.get("text_spline").param("align").choices == ("Left", "Middle", "Right")


def test_extrude_square_counts_and_volume():
    scene, gen = _make("extrude", _square(100.0))
    m = gen.mesh
    assert not gen.error
    assert len(m.points) == 8 and len(m.polygons) == 6
    assert _solid(m) and _close(_volume(m), 100.0 * 100.0 * 20.0)
    assert _euler(m) == 2


def test_extrude_winding_does_not_matter():
    _, a = _make("extrude", _square(100.0, ccw=True))
    _, b = _make("extrude", _square(100.0, ccw=False))
    assert _solid(a.mesh) and _solid(b.mesh)
    assert _close(_volume(a.mesh), _volume(b.mesh))
    assert len(a.mesh.polygons) == len(b.mesh.polygons) == 6


def test_extrude_cap_normals_point_out():
    _, gen = _make("extrude", _square(100.0))
    m = gen.mesh
    normals = m.polygon_normals()
    for k, poly in enumerate(m.polygons):
        c = m.points[list(poly)].mean(axis=0)
        if len(poly) == 4 and abs(normals[k][2]) > 0.99:
            assert (normals[k][2] > 0) == (c[2] > 10.0)


def test_extrude_concave_outline():
    pts = [(0, 0), (200, 0), (200, 100), (100, 100), (100, 200), (0, 200)]
    _, gen = _make("extrude", _poly(pts))
    m = gen.mesh
    assert _solid(m) and _close(_volume(m), 30000.0 * 20.0)
    assert len(m.points) == 12 and len(m.polygons) == 6 + 2 * 2
    normals = m.polygon_normals()
    for k, poly in enumerate(m.polygons):
        c = m.points[list(poly)].mean(axis=0)
        if abs(normals[k][2]) > 0.99:
            assert (normals[k][2] > 0) == (c[2] > 10.0)


def test_extrude_star_outline_all_cap_faces_valid():
    pts = []
    for k in range(10):
        r = 100.0 if k % 2 == 0 else 40.0
        a = math.pi * k / 5.0
        pts.append((r * math.cos(a), r * math.sin(a)))
    _, gen = _make("extrude", _poly(pts))
    m = gen.mesh
    area = abs(_shoelace(np.array([(p[0], p[1]) for p in pts])))
    assert _solid(m) and _close(_volume(m), area * 20.0)
    normals = m.polygon_normals()
    for k, poly in enumerate(m.polygons):
        if abs(normals[k][2]) > 0.5:
            assert len(poly) >= 3


def test_extrude_hole_from_nested_outline():
    outer = _square(200.0)
    inner = _square(100.0, ccw=False)
    _, gen = _make("extrude", outer, inner)
    m = gen.mesh
    assert _solid(m)
    assert _close(_volume(m), (40000.0 - 10000.0) * 20.0)
    assert _euler(m) == 0


def test_extrude_hole_orientation_independent():
    _, a = _make("extrude", _square(200.0), _square(100.0, ccw=True))
    _, b = _make("extrude", _square(200.0, ccw=False), _square(100.0, ccw=True))
    assert _solid(a.mesh) and _solid(b.mesh)
    assert _close(_volume(a.mesh), 30000.0 * 20.0) and _close(_volume(b.mesh), 30000.0 * 20.0)


def test_extrude_island_inside_hole():
    _, gen = _make("extrude", _square(300.0), _square(200.0), _square(100.0))
    m = gen.mesh
    assert _solid(m)
    assert _close(_volume(m), (90000.0 - 40000.0 + 10000.0) * 20.0)


def test_extrude_hierarchical_keeps_children_apart():
    scene, gen = _make("extrude", _square(200.0), _square(100.0))
    assert _close(_volume(gen.mesh), 30000.0 * 20.0)
    scene.set_param(gen, "hierarchical", True)
    assert _solid(gen.mesh)
    assert _close(_volume(gen.mesh), (40000.0 + 10000.0) * 20.0)
    assert scene.undo()
    assert _close(_volume(_find(scene, "extrude").mesh), 30000.0 * 20.0)


def test_extrude_movement_subdivision_and_caps():
    scene, gen = _make("extrude", _square(100.0))
    scene.set_param(gen, "movement", (0, 0, 50))
    assert _close(_volume(gen.mesh), 10000.0 * 50.0)
    scene.set_param(gen, "subdivision", 4)
    m = gen.mesh
    assert len(m.points) == 20 and len(m.polygons) == 16 + 2 and _solid(m)
    scene.set_param(gen, "start_cap", False)
    assert len(gen.mesh.polygons) == 17 and not _closed(gen.mesh)
    scene.set_param(gen, "end_cap", False)
    assert len(gen.mesh.polygons) == 16
    assert scene.undo() and len(_find(scene, "extrude").mesh.polygons) == 17
    assert scene.undo() and len(_find(scene, "extrude").mesh.polygons) == 18


def test_extrude_movement_along_other_axis():
    _, gen = _make("extrude", _square(100.0))
    scene = scene_mod.get_scene()
    scene.set_param(gen, "movement", (0, 0, -30))
    assert _solid(gen.mesh) and _close(_volume(gen.mesh), 10000.0 * 30.0)
    scene.set_param(gen, "movement", (40, 0, 20))
    assert _solid(gen.mesh) and _close(_volume(gen.mesh), 10000.0 * 20.0)


def test_extrude_open_chain_is_uncapped_ribbon():
    _, gen = _make("extrude", _poly([(0, 0), (100, 0), (100, 100)], closed=False))
    m = gen.mesh
    assert len(m.points) == 6 and len(m.polygons) == 2 and not _closed(m)
    assert _clean(m)
    normals = m.polygon_normals()
    assert np.allclose(normals[0], [0, -1, 0]) and np.allclose(normals[1], [1, 0, 0])


def test_extrude_empty_and_unusable_inputs():
    scene = _scene()
    cube = scene.objects[0]
    gen = scene.add_parametric("extrude", adopt=cube)
    assert len(gen.mesh.points) == 0 and not gen.error
    _, gen = _make("extrude", _square(100.0), movement=(0, 0, 0))
    assert len(gen.mesh.points) == 0
    scene = _scene()
    gen = scene.add_parametric("extrude")
    assert len(gen.mesh.points) == 0 and not gen.error


def test_extrude_tiny_duplicate_points_are_cleaned():
    pts = [(0, 0), (0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]
    _, gen = _make("extrude", _poly(pts))
    assert _solid(gen.mesh) and len(gen.mesh.points) == 8


def test_extrude_undo_and_redo_through_scene():
    scene, gen = _make("extrude", _square(100.0))
    scene.set_param(gen, "movement", (0, 0, 80))
    assert _close(_volume(gen.mesh), 10000.0 * 80.0)
    assert scene.undo()
    assert _close(_volume(_find(scene, "extrude").mesh), 10000.0 * 20.0)
    assert scene.redo()
    assert _close(_volume(_find(scene, "extrude").mesh), 10000.0 * 80.0)


def _lathe_volume(segs: int, angle: float, r_out: float, r_in: float, h: float) -> float:
    return segs * 0.5 * math.sin(math.radians(angle) / segs) * (r_out ** 2 - r_in ** 2) * h


def test_lathe_rectangle_profile_makes_tube():
    prof = _poly([(50, 0), (100, 0), (100, 100), (50, 100)])
    _, gen = _make("lathe", prof)
    m = gen.mesh
    assert len(m.points) == 128 and len(m.polygons) == 128
    assert _solid(m) and _euler(m) == 0
    assert _close(_volume(m), _lathe_volume(32, 360.0, 100.0, 50.0, 100.0))


def test_lathe_profile_direction_does_not_matter():
    prof = _poly([(50, 0), (100, 0), (100, 100), (50, 100)][::-1])
    _, gen = _make("lathe", prof)
    assert _solid(gen.mesh)
    assert _close(_volume(gen.mesh), _lathe_volume(32, 360.0, 100.0, 50.0, 100.0))


def test_lathe_axis_points_become_poles():
    prof = _poly([(0, 0), (100, 0), (0, 100)])
    _, gen = _make("lathe", prof)
    m = gen.mesh
    assert len(m.points) == 34 and len(m.polygons) == 64
    assert _solid(m) and _euler(m) == 2
    assert _close(_volume(m), 32 * 0.5 * math.sin(2 * math.pi / 32) * 100.0 ** 3 / 3.0)


def test_lathe_partial_angle_gets_caps_for_closed_profile():
    prof = _poly([(50, 0), (100, 0), (100, 100), (50, 100)])
    scene, gen = _make("lathe", prof, angle=180.0, subdivision=16)
    m = gen.mesh
    assert len(m.polygons) == 4 * 16 + 2 and len(m.points) == 4 * 17
    assert _solid(m)
    assert _close(_volume(m), _lathe_volume(16, 180.0, 100.0, 50.0, 100.0))
    scene.set_param(gen, "angle", 90.0)
    assert _solid(gen.mesh)
    assert _close(_volume(gen.mesh), _lathe_volume(16, 90.0, 100.0, 50.0, 100.0))
    assert scene.undo()
    assert _close(_volume(_find(scene, "lathe").mesh), _lathe_volume(16, 180.0, 100.0, 50.0, 100.0))


def test_lathe_open_profile_normals_face_away_from_axis():
    for pts in ([(100, 0), (100, 100)], [(100, 100), (100, 0)]):
        _, gen = _make("lathe", _poly(pts, closed=False), subdivision=8)
        m = gen.mesh
        assert len(m.polygons) == 8 and len(m.points) == 16 and not _closed(m)
        normals = m.polygon_normals()
        for k, poly in enumerate(m.polygons):
            c = m.points[list(poly)].mean(axis=0)
            assert normals[k][0] * c[0] + normals[k][2] * c[2] > 0


def test_lathe_movement_and_scale():
    prof = _poly([(50, 0), (100, 0), (100, 100), (50, 100)])
    scene, gen = _make("lathe", prof, movement=200.0, subdivision=16)
    lo, hi = gen.mesh.bounds()
    assert abs(lo[1]) < 1e-6 and abs(hi[1] - 300.0) < 1e-6
    assert _closed(gen.mesh) and _volume(gen.mesh) > 0
    scene.set_param(gen, "movement", 0.0)
    scene.set_param(gen, "angle", 270.0)
    scene.set_param(gen, "scale", 50.0)
    m = gen.mesh
    assert len(m.points) == 4 * 17 and _closed(m) and _volume(m) > 0
    ring = m.points[-4:]
    radii = np.sort(np.hypot(ring[:, 0], ring[:, 2]))
    assert abs(radii[0] - 25.0) < 1e-6 and abs(radii[-1] - 50.0) < 1e-6


def test_lathe_invalid_inputs():
    scene = _scene()
    gen = scene.add_parametric("lathe", adopt=scene.objects[0])
    assert len(gen.mesh.points) == 0 and not gen.error
    _, gen = _make("lathe", _poly([(50, 0), (100, 0), (100, 100)]), angle=0.0)
    assert len(gen.mesh.points) == 0


def _sweep_prism_path() -> Mesh:
    return _poly([(0, 0, 0), (0, 100, 0), (0, 200, 0)], closed=False)


def test_sweep_straight_path_prism():
    _, gen = _make("sweep", _circle(20.0, 12), _sweep_prism_path())
    m = gen.mesh
    assert not gen.error
    assert len(m.points) == 36 and len(m.polygons) == 24 + 2
    assert _solid(m) and _close(_volume(m), 1200.0 * 200.0)


def test_sweep_caps_off_leaves_open_tube():
    scene, gen = _make("sweep", _circle(20.0, 12), _sweep_prism_path())
    scene.set_param(gen, "caps", False)
    assert len(gen.mesh.polygons) == 24 and not _closed(gen.mesh)
    assert scene.undo() and len(_find(scene, "sweep").mesh.polygons) == 26


def test_sweep_end_scale_tapers():
    path = _poly([(0, 0, 0), (0, 200, 0)], closed=False)
    scene, gen = _make("sweep", _circle(20.0, 12), path, end_scale=50.0)
    assert _solid(gen.mesh)
    assert _close(_volume(gen.mesh), 200.0 / 3.0 * 1200.0 * 1.75)
    scene.set_param(gen, "end_scale", 0.0)
    m = gen.mesh
    assert _solid(m) and _close(_volume(m), 200.0 / 3.0 * 1200.0)
    assert len(m.points) == 13


def test_sweep_end_rotation_keeps_solid():
    path = _poly([(0, 0, 0), (0, 100, 0), (0, 200, 0)], closed=False)
    scene, gen = _make("sweep", _square(40.0), path, end_rotation=90.0)
    assert _solid(gen.mesh) and len(gen.mesh.points) == 12
    first = gen.mesh.points[:4]
    last = gen.mesh.points[-4:]
    assert abs(np.hypot(first[:, 0], first[:, 2]).max() - np.hypot(last[:, 0], last[:, 2]).max()) < 1e-6
    assert abs(first[0, 0] - last[0, 0]) > 1.0 or abs(first[0, 2] - last[0, 2]) > 1.0


def test_sweep_growth_window():
    path = _poly([(0, 0, 0), (0, 100, 0), (0, 200, 0), (0, 300, 0), (0, 400, 0)], closed=False)
    scene, gen = _make("sweep", _circle(20.0, 12), path, start_growth=25.0, end_growth=75.0)
    m = gen.mesh
    assert len(m.points) == 36 and _solid(m)
    lo, hi = m.bounds()
    assert abs(lo[1] - 100.0) < 1e-6 and abs(hi[1] - 300.0) < 1e-6
    assert _close(_volume(m), 1200.0 * 200.0)
    scene.set_param(gen, "end_growth", 20.0)
    assert len(gen.mesh.points) == 0
    assert scene.undo() and len(_find(scene, "sweep").mesh.points) == 36


def test_sweep_closed_path_makes_closed_tube_without_caps():
    path = _circle(100.0, 24)
    _, gen = _make("sweep", _square(20.0), path)
    m = gen.mesh
    assert len(m.points) == 96 and len(m.polygons) == 96
    assert _clean(m) and _closed(m) and _euler(m) == 0
    assert 230000.0 < _volume(m) < 252000.0


def test_sweep_helix_frames_do_not_flip():
    n = 60
    pts = [(100.0 * math.cos(6.0 * math.pi * k / n), 100.0 * math.sin(6.0 * math.pi * k / n),
            4.0 * k) for k in range(n + 1)]
    contour = _poly([(30.0 * math.cos(2 * math.pi * k / 8), 30.0 * math.sin(2 * math.pi * k / 8))
                     for k in range(8)])
    _, gen = _make("sweep", contour, _poly(pts, closed=False))
    m = gen.mesh
    assert len(m.points) == 8 * (n + 1) and _solid(m)
    prev = None
    for k in range(n + 1):
        w = m.points[k * 8] - np.array(pts[k])
        w = w / np.linalg.norm(w)
        if prev is not None:
            assert float(w @ prev) > math.cos(math.radians(30.0)), k
        prev = w


def test_sweep_circle_path_frames_do_not_flip():
    n = 36
    path = _circle(100.0, n)
    contour = _poly([(10.0 * math.cos(2 * math.pi * k / 6), 25.0 * math.sin(2 * math.pi * k / 6))
                     for k in range(6)])
    _, gen = _make("sweep", contour, path)
    m = gen.mesh
    assert _closed(m) and _volume(m) > 0 and len(m.points) == 6 * n
    ref = m.points[0] - np.array(path.points[0])
    for k in range(n):
        w = m.points[k * 6] - np.array(path.points[k])
        assert abs(float(np.linalg.norm(w)) - float(np.linalg.norm(ref))) < 1e-6


def test_sweep_needs_two_splines():
    scene, gen = _make("sweep", _circle(20.0, 12))
    assert len(gen.mesh.points) == 0 and not gen.error
    scene = _scene()
    cube = scene.objects[0]
    gen = scene.add_parametric("sweep", adopt=cube)
    assert len(gen.mesh.points) == 0


def _frustum(h: float, a: float, b: float) -> float:
    return h / 3.0 * (a * a + a * b + b * b)


def _square_xz(side: float, y: float) -> Mesh:
    h = side / 2.0
    return _poly([(-h, y, -h), (h, y, -h), (h, y, h), (-h, y, h)])


def test_loft_two_squares_is_frustum():
    _, gen = _make("loft", _square_xz(100.0, 0.0), _square_xz(50.0, 200.0))
    m = gen.mesh
    assert not gen.error
    assert len(m.points) == 11 * 30 and len(m.polygons) == 10 * 30 + 2
    assert _solid(m) and _close(_volume(m), _frustum(200.0, 100.0, 50.0))


def test_loft_parameters_and_undo():
    scene, gen = _make("loft", _square_xz(100.0, 0.0), _square_xz(50.0, 200.0))
    scene.set_param(gen, "subdivision_u", 8)
    scene.set_param(gen, "subdivision_v", 2)
    m = gen.mesh
    assert len(m.points) == 3 * 8 and len(m.polygons) == 2 * 8 + 2 and _solid(m)
    assert _close(_volume(m), _frustum(200.0, 100.0, 50.0))
    scene.set_param(gen, "caps", False)
    assert len(gen.mesh.polygons) == 16 and not _closed(gen.mesh)
    assert scene.undo() and len(_find(scene, "loft").mesh.polygons) == 18
    assert scene.undo() and len(_find(scene, "loft").mesh.points) == 11 * 8
    assert scene.undo() and len(_find(scene, "loft").mesh.points) == 11 * 30


def test_loft_three_sections_smooth():
    _, gen = _make("loft", _square_xz(100.0, 0.0), _square_xz(60.0, 100.0), _square_xz(100.0, 200.0))
    m = gen.mesh
    assert len(m.points) == 21 * 30 and _solid(m)
    mid = m.points[10 * 30:11 * 30]
    assert abs(np.abs(mid[:, 0]).max() - 30.0) < 1e-6 and abs(mid[:, 1].mean() - 100.0) < 1e-6


def test_loft_mixed_point_counts_and_reversed_section():
    sq = _square_xz(100.0, 0.0)
    circle = _circle(40.0, 16, plane="xz", center=(0.0, 150.0, 0.0))
    circle.polygons.clear()
    rev = Mesh(circle.points[::-1], [], [(i, (i + 1) % 16) for i in range(16)])
    _, gen = _make("loft", sq, rev)
    assert _solid(gen.mesh) and len(gen.mesh.points) == 11 * 30


def test_loft_loop_closes_ring_of_sections():
    sections = []
    for k in range(4):
        a = math.pi / 2.0 * k
        c = (100.0 * math.cos(a), 100.0 * math.sin(a), 0.0)
        radial = np.array([math.cos(a), math.sin(a), 0.0])
        pts = []
        for j in range(12):
            t = 2.0 * math.pi * j / 12
            q = np.array(c) + 20.0 * math.cos(t) * radial + 20.0 * math.sin(t) * np.array([0, 0, 1.0])
            pts.append(tuple(q))
        sections.append(_poly(pts))
    scene, gen = _make("loft", *sections, subdivision_u=12, subdivision_v=4, loop=True)
    m = gen.mesh
    assert len(m.points) == 16 * 12 and len(m.polygons) == 16 * 12
    assert _clean(m) and _closed(m) and _euler(m) == 0 and _volume(m) > 0
    scene.set_param(gen, "loop", False)
    assert len(gen.mesh.points) == 13 * 12 and _solid(gen.mesh)


def test_loft_open_sections_make_ribbon():
    a = _poly([(0, 0, 0), (100, 0, 0)], closed=False)
    b = _poly([(0, 100, 50), (100, 100, 50)], closed=False)
    _, gen = _make("loft", a, b, subdivision_u=5, subdivision_v=3)
    m = gen.mesh
    assert len(m.points) == 6 * 4 and len(m.polygons) == 5 * 3 and not _closed(m) and _clean(m)


def test_loft_open_section_direction_is_aligned():
    a = _poly([(0, 0, 0), (100, 0, 0)], closed=False)
    b = _poly([(100, 100, 0), (0, 100, 0)], closed=False)
    _, gen = _make("loft", a, b, subdivision_u=4, subdivision_v=1)
    m = gen.mesh
    assert len(m.polygons) == 4 and _clean(m)
    assert np.allclose(m.polygon_normals()[:, 2], m.polygon_normals()[0, 2])
    assert abs(m.polygon_normals()[0, 2]) > 0.99


def test_loft_single_child_is_empty():
    _, gen = _make("loft", _square_xz(100.0, 0.0))
    assert len(gen.mesh.points) == 0 and not gen.error


def _ring_areas(mesh: Mesh):
    chains = [c for c in registry.BuildInput(mesh, "t", "text_spline").chains()]
    return [(abs(_shoelace(pts[:, :2])), closed) for pts, closed in chains]


def test_text_spline_outlines():
    scene = _scene()
    obj = scene.add_parametric("text_spline")
    m = obj.mesh
    assert not obj.error and not m.polygons and m.loose_edges
    chains = registry.BuildInput(m, "t", "text_spline").chains()
    assert len(chains) == 5 and all(closed for _, closed in chains)
    assert np.allclose(m.points[:, 2], 0.0)
    lo, hi = m.bounds()
    assert 120.0 < hi[1] - lo[1] < 170.0
    assert abs(lo[1]) < 6.0
    assert lo[0] > -1.0 and lo[0] < 20.0 and hi[0] > 200.0


def test_text_spline_align_and_spacing():
    scene = _scene()
    obj = scene.add_parametric("text_spline")
    lo0, hi0 = obj.mesh.bounds()
    scene.set_param(obj, "align", "Middle")
    lo1, hi1 = obj.mesh.bounds()
    width = hi0[0] - lo0[0]
    assert abs((lo1[0] + hi1[0]) / 2.0) < 0.1 * width
    scene.set_param(obj, "align", "Right")
    lo2, hi2 = obj.mesh.bounds()
    assert hi2[0] < 0.0 and hi2[0] > -0.1 * width
    scene.set_param(obj, "align", "Left")
    scene.set_param(obj, "horizontal_spacing", 20.0)
    lo3, hi3 = obj.mesh.bounds()
    assert abs((hi3[0] - lo3[0]) - width - 60.0) < 2.0
    assert scene.undo() and abs(_find(scene, "text_spline").mesh.bounds()[1][0] - hi0[0]) < 1e-6


def test_text_spline_height_scales_and_empty_text():
    scene = _scene()
    obj = scene.add_parametric("text_spline")
    h0 = obj.mesh.size()[1]
    scene.set_param(obj, "height", 400.0)
    assert abs(obj.mesh.size()[1] / h0 - 2.0) < 0.02
    scene.set_param(obj, "text", "")
    assert len(obj.mesh.points) == 0 and not obj.error
    scene.set_param(obj, "text", "o")
    chains = registry.BuildInput(obj.mesh, "t", "text_spline").chains()
    assert len(chains) == 2
    scene.set_param(obj, "text", "A\nB")
    lo, hi = obj.mesh.bounds()
    assert hi[1] - lo[1] > 300.0


def test_text_object_is_closed_solid_with_real_hole():
    scene = _scene()
    spl = scene.add_parametric("text_spline", name="Outline")
    scene.set_param(spl, "text", "o")
    areas = sorted(a for a, _ in _ring_areas(spl.mesh))
    assert len(areas) == 2
    txt = scene.add_parametric("text")
    scene.set_param(txt, "text", "o")
    m = txt.mesh
    assert not txt.error
    assert _solid(m) and _euler(m) == 0
    assert _close(_volume(m), (areas[1] - areas[0]) * 20.0, 1e-4)


def test_text_object_default_and_parameters():
    scene = _scene()
    txt = scene.add_parametric("text")
    m = txt.mesh
    assert _solid(m)
    v = _volume(m)
    size = m.size()
    assert abs(size[2] - 20.0) < 1e-6 and 120.0 < size[1] < 170.0
    scene.set_param(txt, "depth", 40.0)
    assert _solid(txt.mesh) and abs(_volume(txt.mesh) / v - 2.0) < 1e-6
    scene.set_param(txt, "depth", 0.0)
    assert len(txt.mesh.points) == 0
    assert scene.undo() and abs(_volume(_find(scene, "text").mesh) / v - 2.0) < 1e-6
    assert scene.undo() and abs(_volume(_find(scene, "text").mesh) / v - 1.0) < 1e-6
    txt = _find(scene, "text")
    scene.set_param(txt, "text", "")
    assert len(txt.mesh.points) == 0 and not txt.error


def test_text_spline_feeds_extrude_generator():
    scene = _scene()
    spl = scene.add_parametric("text_spline")
    scene.set_param(spl, "text", "oi")
    gen = scene.add_parametric("extrude", adopt=spl)
    scene.set_param(gen, "movement", (0, 0, 30))
    m = gen.mesh
    assert not gen.error and _solid(m)
    areas = sorted(a for a, _ in _ring_areas(spl.mesh))
    assert len(areas) == 4
    assert _close(_volume(m), (areas[3] - areas[2] + areas[1] + areas[0]) * 30.0, 1e-6)
    assert _euler(m) == 4


def _ringed_profile(outer: float, inner: float, hole_ccw: bool = True) -> Mesh:
    a, b = outer / 2.0, inner / 2.0
    sq = [(-a, -a, 0.0), (a, -a, 0.0), (a, a, 0.0), (-a, a, 0.0)]
    hole = [(-b, -b, 0.0), (b, -b, 0.0), (b, b, 0.0), (-b, b, 0.0)]
    if not hole_ccw:
        hole = hole[::-1]
    pts = sq + hole
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4)]
    return Mesh(pts, [], edges)


def test_sweep_profile_with_hole_sweeps_every_chain():
    for ccw in (True, False):
        _, gen = _make("sweep", _ringed_profile(40.0, 20.0, ccw), _sweep_prism_path())
        m = gen.mesh
        assert not gen.error and _solid(m), ccw
        assert _close(_volume(m), (1600.0 - 400.0) * 200.0), ccw
        assert len(m.points) == 8 * 3


def test_sweep_text_ring_keeps_its_hole():
    text = registry.get("text_spline")
    mesh = text.build({**text.defaults(), "text": "o", "height": 40.0}, [])
    _, gen = _make("sweep", mesh, _sweep_prism_path())
    assert not gen.error and _solid(gen.mesh)
    solid = _volume(gen.mesh) / 200.0
    _, flat = _make("extrude", mesh, movement=(0.0, 0.0, 1.0))
    assert abs(solid - _volume(flat.mesh)) <= 0.02 * solid


def test_lathe_scale_zero_closes_the_spiral():
    rect = _poly([(150, -100), (250, -100), (250, 100), (150, 100)])
    _, gen = _make("lathe", rect, scale=0.0)
    m = gen.mesh
    assert not gen.error and len(m.polygons) > 0
    assert _closed(m) and _clean(m) and _volume(m) > 0.0
    _, tip = _make("lathe", rect, scale=0.0, angle=90.0)
    assert _closed(tip.mesh) and _volume(tip.mesh) > 0.0


def test_loft_identical_sections_are_degenerate():
    _, gen = _make("loft", _circle(50.0, 12), _circle(50.0, 12))
    assert not gen.error and len(gen.mesh.points) == 0 and not gen.mesh.polygons
    _, ok = _make("loft", _circle(50.0, 12), _circle(50.0, 12, center=(0.0, 0.0, 100.0)))
    assert _solid(ok.mesh)


def test_text_vertical_spacing_moves_second_line():
    for key in ("text_spline", "text"):
        spec = registry.get(key)
        assert spec.param("vertical_spacing").default == 0.0
        base = {**spec.defaults(), "text": "a" + chr(10) + "b", "height": 40.0}
        a = spec.build(base, [])
        b = spec.build({**base, "vertical_spacing": 60.0}, [])
        assert len(a.points) == len(b.points)
        assert abs(float(a.points[:, 1].min()) - 60.0 - float(b.points[:, 1].min())) < 1e-6
        assert abs(float(a.points[:, 1].max()) - float(b.points[:, 1].max())) < 1e-6


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
