from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio import render as R
from quartz_studio.ext import store
from quartz_studio.objects import registry
from quartz_studio.render import actions, bridges, engine, raster, settings as rs, shading, snapshot, worker
from quartz_studio.render.camera import RenderCamera, focal_from_fov, fov_from_focal, from_object, from_orbit, look_at
from quartz_studio.render.objects import CAMERA_KIND, LIGHT_KIND, camera_gizmo, light_gizmo
from quartz_studio.scene import Mesh, SceneObject, reset_scene

APP = QApplication.instance() or QApplication([])
TMP = tempfile.mkdtemp(prefix="qs_render_")
SMALL = {"preset": "Custom", "width": 96, "height": 54, "ao_samples": 4, "shadow_map": 256}
ALLOWED_PX = {1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 88, 96, 112,
              120, 128}


def _allowed(v: int) -> bool:
    return v in ALLOWED_PX or (v >= 128 and v % 16 == 0)


def _cam() -> RenderCamera:
    return look_at((0.0, 0.0, -1000.0), (0.0, 0.0, 0.0), fov=40.0)


def _scene_cube():
    sc = reset_scene()
    return sc, sc.objects[0]


def _quad(z: float = 0.0, size: float = 100.0) -> Mesh:
    h = size / 2.0
    return Mesh([(-h, -h, z), (h, -h, z), (h, h, z), (-h, h, z)], [(0, 1, 2, 3)])


def _settings(**kw) -> dict:
    s = dict(SMALL)
    s.update(kw)
    return s


def test_settings_defaults_are_json_and_clean():
    d = rs.default_settings()
    json.dumps(d)
    c = rs.clean_settings(None)
    assert c == rs.clean_settings(d)
    assert (c["width"], c["height"]) == (640, 360)
    assert c["passes"][0] == "beauty"


def test_settings_presets_and_custom():
    s = rs.clean_settings({"preset": "1920x1080", "width": 5})
    assert (s["width"], s["height"]) == (1920, 1080)
    s = rs.clean_settings({"preset": "Custom", "width": 5, "height": 99999})
    assert s["width"] == 16 and s["height"] == rs.MAX_SIZE
    s = rs.clean_settings({"aa": 3})
    assert s["aa"] in rs.AA_LEVELS
    s = rs.clean_settings({"passes": ["depth"], "format": "JPG", "tonemap": "bogus"})
    assert s["passes"] == ["beauty", "depth"]
    assert s["format"] == "jpg"
    assert s["tonemap"] == rs.default_settings()["tonemap"]
    s = rs.clean_settings({"frame_start": 10, "frame_end": 3, "bg_color": "#ff0000"})
    assert s["frame_end"] == 10
    assert s["bg_color"] == [1.0, 0.0, 0.0]


def test_settings_store_round_trip_and_preset_inference():
    sc = reset_scene()
    rs.update_settings(sc, width=800, height=450)
    s = rs.get_settings(sc)
    assert s["preset"] == "Custom" and s["width"] == 800
    assert isinstance(store.get_scene_data(sc, rs.SETTINGS_KEY), dict)
    rs.update_settings(sc, width=1280, height=720)
    assert rs.get_settings(sc)["preset"] == "1280x720"
    rs.update_settings(sc, preset="640x360")
    assert rs.resolution(rs.get_settings(sc)) == (640, 360)
    raw = store.to_json(store.get_scene_data(sc, rs.SETTINGS_KEY))
    assert rs.clean_settings(store.from_json(json.loads(json.dumps(raw)))) == rs.get_settings(sc)
    assert sc.can_undo()


def test_frame_list():
    assert rs.frame_list({"animation": False, "frame_start": 4}) == [4]
    assert rs.frame_list({"animation": True, "frame_start": 0, "frame_end": 6, "frame_step": 3}) == [0, 3, 6]


def test_hex_round_trip():
    for c in ([0.0, 0.5, 1.0], [0.2, 0.4, 0.6]):
        back = rs.hex_to_rgb(rs.rgb_to_hex(c))
        assert np.allclose(back, c, atol=1 / 255)


def test_fov_focal_round_trip():
    for fov in (10.0, 45.0, 90.0, 120.0):
        assert abs(fov_from_focal(focal_from_fov(fov)) - fov) < 1e-9
    assert abs(focal_from_fov(90.0) - 0.5) < 1e-12


def test_look_at_basis_is_orthonormal():
    cam = look_at((100.0, 200.0, -300.0), (5.0, -10.0, 20.0))
    m = np.stack([cam.right, cam.up, cam.forward])
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)
    assert np.allclose(np.cross(cam.forward, cam.right), cam.up, atol=1e-12)
    c = cam.to_camera(np.array([[5.0, -10.0, 20.0]]))
    assert abs(c[0, 0]) < 1e-9 and abs(c[0, 1]) < 1e-9 and c[0, 2] > 0


def test_from_orbit_matches_viewport_projection():
    from quartz_studio.widgets.viewport import OrbitCamera
    rng = np.random.default_rng(3)
    for ortho in (False, True):
        oc = OrbitCamera(heading=33.0, pitch=21.0, distance=900.0, ortho=ortho)
        rc = from_orbit(oc)
        pts = rng.uniform(-200, 200, (20, 3))
        w, h = 640, 360
        a, za = oc.project(pts, w / 2.0, h / 2.0, float(w))
        b, zb = rc.project(pts, w, h)
        assert np.allclose(a, b, atol=1e-6)
        assert np.allclose(za, zb, atol=1e-6)


def test_ray_hits_projected_point():
    cam = look_at((300.0, 400.0, -800.0), (0.0, 0.0, 0.0), fov=50.0)
    p = np.array([[30.0, -20.0, 40.0]])
    scr, z = cam.project(p, 320, 240)
    o, d = cam.ray(scr[:, 0], scr[:, 1], 320, 240)
    t = float(np.dot(p[0] - o[0], d[0]))
    assert np.allclose(o[0] + d[0] * t, p[0], atol=1e-6)


def test_ortho_projection_scale():
    cam = look_at((0.0, 0.0, -500.0), (0.0, 0.0, 0.0), ortho=True, ortho_width=200.0)
    scr, _z = cam.project(np.array([[100.0, 0.0, 0.0], [0.0, 50.0, 0.0]]), 400, 200)
    assert np.allclose(scr[0], [400.0, 100.0])
    assert np.allclose(scr[1], [200.0, 0.0])


def test_camera_object_looks_down_plus_z():
    sc = reset_scene()
    obj = sc.add_parametric(CAMERA_KIND)
    obj.position = np.array([0.0, 0.0, -400.0])
    cam = from_object(obj)
    assert np.allclose(cam.forward, [0.0, 0.0, 1.0])
    assert np.allclose(cam.up, [0.0, 1.0, 0.0])
    assert abs(cam.focal - 1.0) < 1e-12
    sc.set_param(obj, "focal_length", 72.0)
    assert abs(from_object(obj).focal - 2.0) < 1e-12
    sc.set_param(obj, "projection", "Parallel")
    assert from_object(obj).ortho


def _single_tri_buffers(tri_cam, w=64, h=64, cam=None):
    cam = cam or RenderCamera(eye=np.zeros(3), focal=1.0)
    proj = raster.prepare(np.asarray(tri_cam, float)[None], cam, w, h)
    return proj, raster.rasterize(proj)


def test_raster_coverage_matches_area():
    cam = RenderCamera(eye=np.zeros(3), ortho=True, ortho_width=64.0)
    tri = [[-20.0, -20.0, 10.0], [20.0, -20.0, 10.0], [-20.0, 20.0, 10.0]]
    proj, buf = _single_tri_buffers(tri, 64, 64, cam)
    covered = int((buf.tri >= 0).sum())
    assert abs(covered - 800) <= 41
    assert np.allclose(buf.depth[buf.tri >= 0], 10.0)


def test_raster_square_has_no_gaps_or_overlap():
    cam = RenderCamera(eye=np.zeros(3), ortho=True, ortho_width=64.0)
    a, b, c, d = [-16.0, -16.0, 5.0], [16.0, -16.0, 5.0], [16.0, 16.0, 5.0], [-16.0, 16.0, 5.0]
    tris = np.array([[a, b, c], [a, c, d]])
    proj = raster.prepare(tris, cam, 64, 64)
    buf = raster.rasterize(proj)
    assert int((buf.tri >= 0).sum()) == 32 * 32
    ys, xs = np.nonzero(buf.tri >= 0)
    assert xs.min() == 16 and xs.max() == 47 and ys.min() == 16 and ys.max() == 47


def test_raster_z_test_keeps_nearest():
    cam = RenderCamera(eye=np.zeros(3), ortho=True, ortho_width=64.0)
    far = [[-30.0, -30.0, 50.0], [30.0, -30.0, 50.0], [0.0, 30.0, 50.0]]
    near = [[-10.0, -10.0, 20.0], [10.0, -10.0, 20.0], [0.0, 10.0, 20.0]]
    for order in ([far, near], [near, far]):
        proj = raster.prepare(np.array(order), cam, 64, 64)
        buf = raster.rasterize(proj)
        nid = 1 if order[1] is near else 0
        assert buf.tri[32, 32] == nid
        assert abs(buf.depth[32, 32] - 20.0) < 1e-9
        assert abs(buf.depth[2, 32] - 50.0) < 1e-9 or buf.tri[2, 32] == -1


def test_perspective_bary_reconstructs_positions():
    cam = look_at((0.0, 150.0, -400.0), (0.0, 0.0, 0.0), fov=60.0)
    world = np.array([[-300.0, 0.0, -100.0], [300.0, 0.0, -100.0], [0.0, 0.0, 600.0]])
    w, h = 80, 60
    proj = raster.prepare(cam.to_camera(world)[None], cam, w, h)
    buf = raster.rasterize(proj)
    iy, ix = np.nonzero(buf.tri >= 0)
    assert len(iy) > 100
    src, b = raster.resolve_bary(proj, buf.tri[iy, ix], buf.bary[iy, ix])
    p = b @ world
    assert np.allclose(p[:, 1], 0.0, atol=1e-6)
    scr, z = cam.project(p, w, h)
    assert np.allclose(scr[:, 0], ix + 0.5, atol=1e-6)
    assert np.allclose(scr[:, 1], iy + 0.5, atol=1e-6)
    assert np.allclose(z, buf.depth[iy, ix], atol=1e-6)


def test_near_clipping_keeps_visible_part():
    cam = RenderCamera(eye=np.zeros(3), focal=0.5, near=1.0)
    world = np.array([[-50.0, -5.0, -20.0], [50.0, -5.0, -20.0], [0.0, -5.0, 200.0]])
    proj = raster.prepare(world[None], cam, 64, 64)
    assert len(proj) >= 1 and set(proj.src.tolist()) == {0}
    buf = raster.rasterize(proj)
    iy, ix = np.nonzero(buf.tri >= 0)
    assert len(iy) > 0
    assert buf.depth[iy, ix].min() >= 1.0 - 1e-9
    _src, b = raster.resolve_bary(proj, buf.tri[iy, ix], buf.bary[iy, ix])
    p = b @ world
    assert np.allclose(p[:, 1], -5.0, atol=1e-6)
    assert np.allclose(b.sum(axis=1), 1.0)


def test_raster_regions_match_full_frame():
    rng = np.random.default_rng(11)
    centers = rng.uniform(-60, 60, (300, 1, 3)) + np.array([0.0, 0.0, 300.0])
    tris = centers + rng.uniform(-12, 12, (300, 3, 3))
    tris[:5] = centers[:5] + rng.uniform(-90, 90, (5, 3, 3))
    cam = RenderCamera(eye=np.zeros(3), focal=1.2)
    proj = raster.prepare(tris, cam, 160, 120)
    full = raster.rasterize(proj)
    depth = np.full((120, 160), np.inf)
    for y0 in range(0, 120, 32):
        for x0 in range(0, 160, 48):
            x1, y1 = min(160, x0 + 48), min(120, y0 + 32)
            part = raster.rasterize(proj, (x0, y0, x1, y1))
            depth[y0:y1, x0:x1] = part.depth
    assert np.array_equal(np.isfinite(depth), np.isfinite(full.depth))
    ok = np.isfinite(depth)
    assert np.allclose(depth[ok], full.depth[ok])


def test_raster_cancel():
    tris = np.random.default_rng(1).uniform(-50, 50, (50, 3, 3)) + np.array([0.0, 0.0, 300.0])
    proj = raster.prepare(tris, RenderCamera(eye=np.zeros(3)), 64, 64)
    try:
        raster.rasterize(proj, cancel=lambda: True)
    except raster.RenderCancelled:
        return
    raise AssertionError("cancel ignored")


def test_ggx_lambert_limit_and_reciprocity():
    n = np.array([[0.0, 1.0, 0.0]])
    v = np.array([[0.0, 1.0, 0.0]])
    base = np.array([[0.5, 0.5, 0.5]])
    dif, spec, ndl = shading.ggx_terms(n, v, v, base, np.zeros(1), np.ones(1), np.zeros(1))
    assert np.allclose(dif, 0.5 / math.pi)
    assert ndl[0] == 1.0
    l2 = shading.normalize(np.array([[0.3, 0.8, 0.1]]))
    v2 = shading.normalize(np.array([[-0.5, 0.6, 0.2]]))
    _d1, s1, _n1 = shading.ggx_terms(n, v2, l2, base, np.ones(1), np.full(1, 0.4), np.full(1, 0.5))
    _d2, s2, _n2 = shading.ggx_terms(n, l2, v2, base, np.ones(1), np.full(1, 0.4), np.full(1, 0.5))
    assert np.allclose(s1, s2)
    _d3, metal_spec, _n3 = shading.ggx_terms(n, v, v, base, np.ones(1), np.full(1, 0.3), np.full(1, 0.5))
    _d4, rough_spec, _n4 = shading.ggx_terms(n, v, v, base, np.ones(1), np.full(1, 0.9), np.full(1, 0.5))
    assert metal_spec[0, 0] > rough_spec[0, 0]
    dm, _s, _n = shading.ggx_terms(n, v, v, base, np.ones(1), np.full(1, 0.5), np.full(1, 0.5))
    assert np.allclose(dm, 0.0)


def test_tonemap_and_gamma():
    x = np.linspace(0.0, 20.0, 50)[:, None].repeat(3, axis=1)
    for mode in rs.TONEMAPS:
        y = shading.tonemap(x, mode)
        assert y.min() >= 0.0 and y.max() <= 1.0
        assert np.all(np.diff(y[:, 0]) >= -1e-12)
        assert abs(shading.tonemap(np.zeros((1, 3)), mode)[0, 0]) < 1e-3
    assert np.allclose(shading.tonemap(np.full((1, 3), 0.5), "standard"), 0.5)
    assert np.allclose(shading.tonemap(np.full((1, 3), 0.25), "standard", exposure=1.0), 0.5)
    assert np.allclose(shading.apply_gamma(np.full((1, 3), 0.25), 2.0), 0.5)


def test_background_modes():
    s = rs.default_settings()
    s["bg_top"], s["bg_bottom"] = [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]
    rgb, a = shading.background(np.array([0.0, 99.0]), 100, s)
    assert rgb[0, 0] > 0.98 and rgb[1, 2] > 0.98 and np.all(a == 1)
    s["background"] = "transparent"
    rgb, a = shading.background(np.array([3.0]), 100, s)
    assert a[0] == 0.0
    s["background"] = "color"
    s["bg_color"] = [0.2, 0.3, 0.4]
    rgb, _a = shading.background(np.array([3.0]), 100, s)
    assert np.allclose(rgb[0], [0.2, 0.3, 0.4])


def test_light_falloff_and_spot_cone():
    light = shading.Light(kind="point", falloff="Inverse Square", radius=100.0)
    assert np.allclose(shading._attenuation(light, np.array([100.0, 200.0])), [1.0, 0.25])
    light.falloff = "Linear"
    assert np.allclose(shading._attenuation(light, np.array([0.0, 50.0, 150.0])), [1.0, 0.5, 0.0])
    spot = shading.Light(kind="spot", direction=np.array([0.0, -1.0, 0.0]), cone_angle=30.0, penumbra=10.0)
    inside = shading._spot_factor(spot, np.array([[0.0, 1.0, 0.0]]))
    outside = shading._spot_factor(spot, shading.normalize(np.array([[1.0, 1.0, 0.0]])))
    assert inside[0] == 1.0 and outside[0] == 0.0


def test_area_light_samples():
    light = shading.Light(kind="area", position=np.array([0.0, 100.0, 0.0]), area_width=200.0, area_height=100.0,
                          area_samples=9)
    pts = light.sample_points()
    assert len(pts) == 9
    assert np.allclose(pts.mean(axis=0), [0.0, 100.0, 0.0])
    assert pts[:, 0].max() <= 100.0 and pts[:, 2].max() <= 50.0


def _occluder_scene():
    floor = np.array([[[-500.0, 0.0, -500.0], [500.0, 0.0, -500.0], [500.0, 0.0, 500.0]],
                      [[-500.0, 0.0, -500.0], [500.0, 0.0, 500.0], [-500.0, 0.0, 500.0]]])
    block = np.array([[[-50.0, 100.0, -50.0], [50.0, 100.0, -50.0], [50.0, 100.0, 50.0]],
                      [[-50.0, 100.0, -50.0], [50.0, 100.0, 50.0], [-50.0, 100.0, 50.0]]])
    return np.concatenate([floor, block])


def test_shadow_maps_for_every_light_type():
    tris = _occluder_scene()
    bounds = (tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0))
    pts = np.array([[0.0, 0.0, 0.0], [300.0, 0.0, 300.0]])
    ng = np.array([[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    lights = [
        shading.Light(kind="infinite", direction=np.array([0.0, -1.0, 0.0]), softness=0.0),
        shading.Light(kind="spot", position=np.array([0.0, 400.0, 0.0]), direction=np.array([0.0, -1.0, 0.0]),
                      cone_angle=60.0, softness=0.0),
        shading.Light(kind="point", position=np.array([0.0, 400.0, 0.0]), softness=0.0),
        shading.Light(kind="area", position=np.array([0.0, 400.0, 0.0]), direction=np.array([0.0, -1.0, 0.0]),
                      area_width=20.0, area_height=20.0, softness=0.0),
    ]
    for light in lights:
        sm = shading.build_shadow_map(light, tris, bounds, 256)
        vis = sm.visibility(pts, ng)
        assert vis[0] < 0.2, (light.kind, vis)
        assert vis[1] > 0.8, (light.kind, vis)
    off = shading.Light(kind="infinite", shadow=False)
    assert shading.build_shadow_map(off, tris, bounds, 64) is None


def test_screen_ao_darkens_corner():
    cam = look_at((0.0, 300.0, -600.0), (0.0, 0.0, 0.0), fov=50.0)
    floor = np.array([[[-400.0, 0.0, -400.0], [400.0, 0.0, -400.0], [400.0, 0.0, 400.0]],
                      [[-400.0, 0.0, -400.0], [400.0, 0.0, 400.0], [-400.0, 0.0, 400.0]]])
    wall = np.array([[[-400.0, 0.0, 100.0], [400.0, 0.0, 100.0], [400.0, 300.0, 100.0]],
                     [[-400.0, 0.0, 100.0], [400.0, 300.0, 100.0], [-400.0, 300.0, 100.0]]])
    tris = np.concatenate([floor, wall])
    w, h = 160, 120
    proj = raster.prepare(cam.to_camera(tris.reshape(-1, 3)).reshape(-1, 3, 3), cam, w, h)
    depth = raster.rasterize(proj, with_bary=False).depth
    p = np.array([[0.0, 0.0, 95.0], [0.0, 0.0, -200.0]])
    n = np.array([[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    ao = shading.screen_ao(p, n, depth, cam, w, h, 60.0, 32, 1.0, np.random.default_rng(0))
    assert ao[0] < ao[1] - 0.1
    assert ao[1] > 0.9


def test_triangulate_cube_and_flat_normals():
    sc, cube = _scene_cube()
    data = snapshot.triangulate_object(cube, settings={"auto_phong": True, "phong_angle": 80.0})
    assert data["tris"].shape == (12, 3, 3)
    centre = data["tris"].mean(axis=1)
    out = np.einsum("ij,ij->i", data["face"], centre)
    assert np.all(out > 0)
    for k in range(3):
        assert np.allclose(data["normals"][:, k], data["face"])


def test_smooth_normals_follow_phong_angle():
    sc = reset_scene()
    sp = sc.add_parametric("sphere")
    sc.evaluate()
    smooth = snapshot.triangulate_object(sp, settings={"auto_phong": True, "phong_angle": 80.0})
    flat = snapshot.triangulate_object(sp, settings={"auto_phong": False})
    pos = smooth["tris"].reshape(-1, 3)
    radial = shading.normalize(pos - sp.world_position())
    err_smooth = np.abs(1.0 - np.einsum("ij,ij->i", smooth["normals"].reshape(-1, 3), radial)).mean()
    err_flat = np.abs(1.0 - np.einsum("ij,ij->i", flat["normals"].reshape(-1, 3), radial)).mean()
    assert err_smooth < err_flat * 0.5
    store.set_object(sp, "tags", [{"type": "phong", "name": "Phong", "enabled": True, "angle": 1.0,
                                   "angle_limit": True}])
    tagged = snapshot.triangulate_object(sp, settings={"auto_phong": True, "phong_angle": 80.0})
    assert np.allclose(tagged["normals"][:, 0], tagged["face"], atol=1e-9)
    assert bridges.phong_angle(sp) == 1.0
    store.set_object(sp, "tags", [{"type": "phong", "enabled": True, "angle": 10.0, "angle_limit": False}])
    assert bridges.phong_angle(sp) == 180.0


def test_ngon_and_mirrored_object():
    sc = reset_scene()
    obj = sc.objects[0]
    ring = [(math.cos(a) * 100.0, math.sin(a) * 100.0, 0.0) for a in np.linspace(0, 2 * math.pi, 7)[:-1]]
    obj.mesh = Mesh(ring, [tuple(range(6))])
    data = snapshot.triangulate_object(obj)
    assert len(data["tris"]) == 4
    area = 0.5 * np.linalg.norm(np.cross(data["tris"][:, 1] - data["tris"][:, 0],
                                         data["tris"][:, 2] - data["tris"][:, 0]), axis=1).sum()
    assert abs(area - 1.5 * math.sqrt(3) * 100.0 ** 2) < 1e-6
    obj.scale = np.array([-1.0, 1.0, 1.0])
    mirrored = snapshot.triangulate_object(obj)
    n_geo = shading.normalize(np.cross(mirrored["tris"][:, 1] - mirrored["tris"][:, 0],
                                       mirrored["tris"][:, 2] - mirrored["tris"][:, 0]))
    assert np.allclose(np.abs(np.einsum("ij,ij->i", n_geo, mirrored["face"])), 1.0)


def test_build_geometry_skips_lights_cameras_and_splines():
    sc = reset_scene()
    sc.add_parametric(LIGHT_KIND)
    sc.add_parametric(CAMERA_KIND)
    sc.add_parametric("circle")
    sc.evaluate()
    geo = snapshot.build_geometry(sc, rs.default_settings())
    assert len(geo) == 12
    assert geo.names == ["Cube"]
    assert geo.bounds() is not None


def test_light_objects_registered_and_converted():
    spec = registry.get(LIGHT_KIND)
    assert spec.category == "null"
    assert registry.get(CAMERA_KIND).category == "null"
    for t in ("Point", "Spot", "Infinite", "Area"):
        m = light_gizmo({"light_type": t, "cone_angle": 30.0, "area_width": 100.0, "area_height": 50.0})
        assert len(m.loose_edges) > 3 and not m.polygons
    assert camera_gizmo({}).loose_edges
    sc = reset_scene()
    obj = sc.add_parametric(LIGHT_KIND)
    sc.set_param(obj, "light_type", "Spot")
    sc.set_param(obj, "color", (1.0, 0.5, 0.25))
    sc.set_param(obj, "intensity", 2.0)
    obj.position = np.array([10.0, 20.0, 30.0])
    obj.rotation = np.array([90.0, 0.0, 0.0])
    light = snapshot.light_from_object(obj)
    assert light.kind == "spot"
    assert np.allclose(light.position, [10.0, 20.0, 30.0])
    assert np.allclose(light.direction, [0.0, -1.0, 0.0], atol=1e-9)
    assert np.allclose(light.radiance(), np.array([1.0, 0.5, 0.25]) * 2.0 * math.pi)


def test_default_three_point_lights():
    sc = reset_scene()
    cam = _cam()
    s = rs.default_settings()
    lights = snapshot.scene_lights(sc, cam, s)
    assert [l.name for l in lights] == ["Key", "Fill", "Rim"]
    assert lights[0].shadow and not lights[1].shadow
    assert np.dot(-lights[2].direction, cam.forward) > 0
    sc.add_parametric(LIGHT_KIND)
    assert len(snapshot.scene_lights(sc, cam, s)) == 1
    s["default_lights"] = "on"
    assert len(snapshot.scene_lights(sc, cam, s)) == 4
    s["shadows"] = False
    assert not any(l.shadow for l in snapshot.scene_lights(sc, cam, s))
    s["default_lights"] = "off"
    sc2 = reset_scene()
    assert snapshot.scene_lights(sc2, cam, s) == []


def test_render_default_cube_layout():
    sc, _cube = _scene_cube()
    res = R.render(sc, camera=_cam(), settings=_settings(passes=list(rs.PASSES)))
    assert res.width == 96 and res.height == 54
    b = res.passes["beauty"]
    assert b.shape == (54, 96, 4)
    assert b[27, 48, 3] == 1.0
    assert set(res.passes) == set(rs.PASSES)
    centre_depth = res.passes["depth"][27, 48]
    assert abs(centre_depth - 900.0) < 1.0
    assert not np.isfinite(res.passes["depth"][0, 0])
    n = res.passes["normal"][27, 48]
    assert np.allclose(n, [0.0, 0.0, -1.0], atol=1e-6)
    s = res.settings
    top = shading.apply_gamma(np.array(s["bg_top"]), 1.0)
    assert np.allclose(b[0, 0, :3], np.array(s["bg_top"]) * (1 - 0.5 / 54) + np.array(s["bg_bottom"]) * (0.5 / 54),
                       atol=1e-6)
    assert top.shape == (3,)
    assert res.stats["triangles"] == 12 and res.stats["lights"] == 3
    assert res.seconds > 0


def test_render_transparent_background_and_aa_edges():
    sc, _cube = _scene_cube()
    res = R.render(sc, camera=_cam(), settings=_settings(background="transparent", aa=2, ao=False))
    a = res.passes["beauty"][..., 3]
    assert a[0, 0] == 0.0 and a[27, 48] == 1.0
    partial = (a > 0.0) & (a < 1.0)
    assert partial.sum() > 4
    rgba = res.rgba8("beauty")
    assert rgba[0, 0, 3] == 0 and rgba[27, 48, 3] == 255


def test_render_passes_selection_and_images():
    sc, _cube = _scene_cube()
    res = R.render(sc, camera=_cam(), settings=_settings(passes=["depth"], ao=False))
    assert set(res.passes) == {"beauty", "depth"}
    for name in res.passes:
        img = res.image(name)
        assert isinstance(img, QImage) and img.width() == 96 and img.height() == 54
    d8 = res.rgba8("depth")
    assert d8[27, 48, 0] > 200 and d8[0, 0, 0] == 0


def test_render_material_from_store_and_emission():
    sc, cube = _scene_cube()
    store.set_object(cube, "material", {"base_color": [0.9, 0.05, 0.05], "roughness": 0.6})
    res = R.render(sc, camera=_cam(), settings=_settings(ao=False, passes=["albedo"]))
    c = res.passes["beauty"][27, 48, :3]
    assert c[0] > c[1] * 2 and c[0] > c[2] * 2
    assert np.allclose(res.passes["albedo"][27, 48], [0.9, 0.05, 0.05])
    store.set_object(cube, "material", {"color": [0.0, 0.0, 0.0], "emission": [1.0, 1.0, 1.0],
                                        "emission_strength": 4.0})
    res = R.render(sc, camera=_cam(), settings=_settings(ao=False, tonemap="standard"))
    assert np.all(res.passes["beauty"][27, 48, :3] > 0.99)


def test_render_material_from_scene_library_and_tag():
    sc, cube = _scene_cube()
    store.set_scene_data(sc, "materials", [{"id": "m1", "name": "Green", "base_color": [0.05, 0.8, 0.05]}])
    store.set_object(cube, "tags", [{"type": "material", "name": "Material", "enabled": True, "material": "m1"}])
    res = R.render(sc, camera=_cam(), settings=_settings(ao=False))
    c = res.passes["beauty"][27, 48, :3]
    assert c[1] > c[0] * 2 and c[1] > c[2] * 2


def _materials_pkg():
    try:
        import quartz_studio.materials as mats
    except Exception:
        return None
    needed = ("create_material", "apply_material", "update_material", "evaluate_material")
    return mats if all(hasattr(mats, n) for n in needed) else None


def test_render_with_materials_package_pbr_and_texture():
    mats = _materials_pkg()
    if mats is None:
        return
    from quartz_studio.materials import model
    sc, cube = _scene_cube()
    mat = mats.create_material(sc, "pbr", name="Blue")
    model.set_channel(mat, "base_color", "value", [0.05, 0.1, 0.9])
    mats.update_material(sc, mat)
    mats.apply_material(cube, mat["id"])
    res = R.render(sc, camera=_cam(), settings=_settings(ao=False, passes=["albedo"]))
    alb = res.passes["albedo"][27, 48]
    assert alb[2] > alb[0] * 3 and alb[2] > alb[1] * 3
    from quartz_studio.materials.textures import new_texture
    model.set_channel(mat, "base_color", "texture", new_texture("checker", color1=[1.0, 0.0, 0.0],
                                                                  color2=[0.0, 1.0, 0.0], scale=4.0))
    mats.update_material(sc, mat)
    res = R.render(sc, camera=_cam(), settings=_settings(ao=False, passes=["albedo", "depth"], width=192, height=108))
    alb = res.passes["albedo"]
    covered = np.isfinite(res.passes["depth"])
    reds = (alb[..., 0] > 0.5) & (alb[..., 1] < 0.2) & covered
    greens = (alb[..., 1] > 0.5) & (alb[..., 0] < 0.2) & covered
    assert reds.sum() > 50 and greens.sum() > 50


def test_material_sampler_with_vector_and_scalar_evaluators():
    calls = []

    def vec(material, u, v, pos, normal):
        calls.append(np.ndim(u))
        return {"base_color": np.stack([u, v, np.zeros_like(u)], -1), "roughness": 0.3, "metallic": 1.0}

    s = bridges.MaterialSampler({"x": 1}, vec)
    u = np.array([0.1, 0.9])
    out = s.sample(u, u[::-1], np.zeros((2, 3)), np.zeros((2, 3)))
    assert np.allclose(out["base_color"][:, 0], [0.1, 0.9])
    assert np.allclose(out["metallic"], 1.0) and np.allclose(out["roughness"], 0.3)

    def scalar(material, u, v, pos, normal):
        return {"albedo": (float(u), 0.5, 0.25), "metalness": 0.2}

    s2 = bridges.MaterialSampler({"x": 2}, scalar)
    out2 = s2.sample(np.array([0.2, 0.4]), np.zeros(2), np.zeros((2, 3)), np.zeros((2, 3)))
    assert out2["base_color"].shape == (2, 3)
    assert np.allclose(out2["base_color"][:, 0], 0.3)
    assert np.allclose(out2["metallic"], 0.2)
    plain = bridges.MaterialSampler(None)
    assert np.allclose(plain.sample(np.zeros(3), np.zeros(3), np.zeros((3, 3)), np.zeros((3, 3)))["base_color"], 0.8)
    ch = bridges.normalise_channels({"color": [2.0, 0.5, -1.0], "glossiness": 0.75, "opacity": 0.5}, 2)
    assert np.allclose(ch["base_color"], [[1.0, 0.5, 0.0]] * 2)
    assert np.allclose(ch["roughness"], 0.25) and np.allclose(ch["alpha"], 0.5)


def test_render_red_light_object_tints_and_black_without_light():
    sc, cube = _scene_cube()
    light = sc.add_parametric(LIGHT_KIND)
    sc.set_param(light, "light_type", "Infinite")
    sc.set_param(light, "color", (1.0, 0.0, 0.0))
    light.rotation = np.array([0.0, 0.0, 0.0])
    s = _settings(ao=False, ambient=0.0)
    res = R.render(sc, camera=_cam(), settings=s)
    c = res.passes["beauty"][27, 48, :3]
    assert c[0] > 0.3 and c[1] < 0.02 and c[2] < 0.02
    sc.set_param(light, "intensity", 0.0)
    res = R.render(sc, camera=_cam(), settings=s)
    assert np.all(res.passes["beauty"][27, 48, :3] < 1e-6)


def test_render_shadow_falls_on_floor():
    sc = reset_scene()
    cube = sc.objects[0]
    cube.position = np.array([0.0, 200.0, 0.0])
    cube.scale = np.array([1.0, 0.1, 1.0])
    floor = sc.add_parametric("plane")
    sc.set_param(floor, "width", 2000.0)
    sc.set_param(floor, "height", 2000.0)
    light = sc.add_parametric(LIGHT_KIND)
    sc.set_param(light, "light_type", "Infinite")
    light.rotation = np.array([90.0, 0.0, 0.0])
    cam = look_at((0.0, 1500.0, -10.0), (0.0, 0.0, 0.0), fov=60.0)
    s = _settings(ao=False, ambient=0.0, width=64, height=64)
    lit = R.render(sc, camera=cam, settings=s).passes["beauty"]
    sc.set_param(light, "shadow", False)
    unshadowed = R.render(sc, camera=cam, settings=s).passes["beauty"]
    corner = lit[4, 4, 0]
    assert abs(corner - unshadowed[4, 4, 0]) < 1e-6


def test_render_shadow_darkens_region_under_occluder():
    sc = reset_scene()
    cube = sc.objects[0]
    cube.position = np.array([0.0, 200.0, 0.0])
    cube.scale = np.array([1.5, 0.1, 1.5])
    floor = sc.add_parametric("plane")
    sc.set_param(floor, "width", 3000.0)
    sc.set_param(floor, "height", 3000.0)
    light = sc.add_parametric(LIGHT_KIND)
    sc.set_param(light, "light_type", "Infinite")
    light.rotation = np.array([90.0, 0.0, 0.0])
    cam = look_at((900.0, 300.0, 0.0), (0.0, 0.0, 0.0), fov=60.0)
    s = _settings(ao=False, ambient=0.0, width=64, height=64, shadow_softness=0.0)
    res = R.render(sc, camera=cam, settings=s)
    depth = res.passes["depth"]
    b = res.passes["beauty"]
    scr, z = cam.project(np.array([[0.0, 0.0, 0.0]]), 64, 64)
    px, py = int(scr[0, 0]), int(scr[0, 1])
    assert abs(depth[py, px] - z[0]) < 30.0
    sc.set_param(light, "shadow", False)
    free = R.render(sc, camera=cam, settings=s).passes["beauty"]
    assert b[py, px, 0] < free[py, px, 0] - 0.2
    scr2, _z2 = cam.project(np.array([[400.0, 0.0, 0.0]]), 64, 64)
    qx, qy = int(scr2[0, 0]), int(scr2[0, 1])
    assert abs(b[qy, qx, 0] - free[qy, qx, 0]) < 1e-6


def test_render_ortho_and_camera_setting():
    sc, _cube = _scene_cube()
    obj = sc.add_parametric(CAMERA_KIND, name="Shot")
    obj.position = np.array([0.0, 0.0, -1000.0])
    sc.set_param(obj, "projection", "Parallel")
    sc.set_param(obj, "ortho_width", 400.0)
    res = R.render(sc, settings=_settings(camera="Shot", ao=False, width=100, height=100))
    a = res.passes["beauty"][..., 3]
    cov = res.passes["depth"]
    covered = np.isfinite(cov)
    assert covered.sum() == 50 * 50
    assert np.all(a == 1.0)
    assert res.camera == "Shot"


def test_render_region_cancel_progress_and_buckets():
    sc, _cube = _scene_cube()
    seen = []
    res = R.render(sc, camera=_cam(), settings=_settings(bucket_size=16),
                   progress=lambda f, st: seen.append(f))
    assert seen[-1] == 1.0 and all(b >= a - 1e-9 for a, b in zip(seen, seen[1:]))
    try:
        R.render(sc, camera=_cam(), settings=_settings(), cancel=lambda: True)
    except R.RenderCancelled:
        pass
    else:
        raise AssertionError("cancel ignored")
    tiles = engine.buckets(100, 70, 32, "spiral")
    cover = np.zeros((70, 100), int)
    for x0, y0, x1, y1 in tiles:
        cover[y0:y1, x0:x1] += 1
    assert np.all(cover == 1)
    centre = tiles[0]
    assert centre[0] <= 50 <= centre[2] and centre[1] <= 35 <= centre[3]
    job = R.prepare_job(sc, _cam(), _settings())
    job.region = (0, 0, 48, 27)
    part = R.execute_job(job)
    assert part.passes["beauty"][40, 80, 3] == 0.0
    patches = []
    R.render(sc, camera=_cam(), settings=_settings(), on_bucket=lambda r, rgba: patches.append((r, rgba.shape)))
    assert patches and all(shape[:2] == (r[3] - r[1], r[2] - r[0]) for r, shape in patches)


def test_save_png_jpg_and_frame_path():
    sc, _cube = _scene_cube()
    res = R.render(sc, camera=_cam(), settings=_settings(ao=False))
    png = os.path.join(TMP, "a.png")
    jpg = os.path.join(TMP, "sub", "b.jpg")
    assert res.save(png)
    assert res.save(jpg, quality=80)
    for path in (png, jpg):
        img = QImage(path)
        assert img.width() == 96 and img.height() == 54
    assert res.save(os.path.join(TMP, "c"), fmt="png", name="normal")
    assert os.path.exists(os.path.join(TMP, "c.png"))
    assert engine.frame_path("x/out.png", 7, "png") == "x/out_0007.png"
    assert engine.frame_path("x/out", None, "jpg", "depth") == "x/out_depth.jpg"


def test_resolve_camera_variants():
    sc, _cube = _scene_cube()
    cam = engine.resolve_camera(sc, {"eye": (0, 0, -500), "target": (0, 0, 0), "fov": 90.0})
    assert abs(cam.focal - 0.5) < 1e-12
    from quartz_studio.widgets.viewport import OrbitCamera
    oc = engine.resolve_camera(sc, OrbitCamera())
    assert isinstance(oc, RenderCamera)
    canvas_like = types.SimpleNamespace(camera=OrbitCamera(), view_name="Top")
    assert engine.resolve_camera(sc, canvas_like).name == "Top"
    obj = sc.add_parametric(CAMERA_KIND, name="C1")
    assert engine.resolve_camera(sc, obj).name == "C1"
    assert engine.resolve_camera(sc, None, {"camera": "C1"}).name == "C1"
    assert isinstance(engine.resolve_camera(sc, None, {"camera": "missing"}), RenderCamera)


def test_evaluate_frame_uses_anim_package():
    seen = []
    old = bridges._CACHE.get("anim", "absent")
    bridges._CACHE["anim"] = types.SimpleNamespace(evaluate=lambda scene, frame: seen.append(frame))
    try:
        sc = reset_scene()
        assert bridges.evaluate_frame(sc, 5)
        assert seen == [5]
    finally:
        if old == "absent":
            bridges._CACHE.pop("anim", None)
        else:
            bridges._CACHE["anim"] = old


def test_animation_render_with_anim_package():
    try:
        from quartz_studio import anim
    except Exception:
        return
    if not hasattr(anim, "insert_key") or not hasattr(anim, "evaluate"):
        return
    sc, cube = _scene_cube()
    anim.insert_key(cube, "position.x", 0, 0.0, interp="linear", scene=sc)
    anim.insert_key(cube, "position.x", 10, 400.0, interp="linear", scene=sc)
    m = worker.RenderManager(threaded=False)
    got = []
    m.finished.connect(got.append)
    m.render(sc, camera=_cam(), settings=_settings(ao=False, animation=True, frame_start=0, frame_end=10,
                                                   frame_step=10, passes=["depth"]))
    m.wait(60)
    assert [r.result.frame for r in got] == [0, 10]
    d0 = got[0].result.passes["depth"]
    d1 = got[1].result.passes["depth"]
    assert np.isfinite(d0[27, 48]) and not np.isfinite(d1[27, 20])
    cols0 = np.flatnonzero(np.isfinite(d0).any(axis=0)).mean()
    cols1 = np.flatnonzero(np.isfinite(d1).any(axis=0)).mean()
    assert cols1 > cols0 + 10
    if bridges.current_frame(sc) is not None:
        assert abs(float(cube.position[0]) - 0.0) < 1e-6
    rng = bridges.timeline_range(sc)
    if rng is not None:
        from quartz_studio.render.widgets import RenderSettingsPanel
        panel = RenderSettingsPanel(sc)
        assert panel.timeline_button.isEnabled()
        assert panel.use_timeline_range()
        s = rs.get_settings(sc)
        assert (s["frame_start"], s["frame_end"], s["animation"]) == (rng[0], rng[1], True)
        panel.close()


def test_compositing_tag_flags():
    sc, cube = _scene_cube()
    store.set_object(cube, "tags", [{"type": "compositing", "enabled": True, "seen_by_camera": False,
                                     "cast_shadows": True, "receive_shadows": False}])
    flags = bridges.compositing(cube)
    assert flags["seen_by_camera"] is False and flags["receive_shadows"] is False
    geo = snapshot.build_geometry(sc, rs.default_settings())
    assert len(geo) == 12 and not geo.visible.any() and geo.cast.all()
    res = R.render(sc, camera=_cam(), settings=_settings(ao=False))
    assert not np.isfinite(res.passes["depth"]).any()


def test_manager_threaded_render_history_and_autosave():
    sc, _cube = _scene_cube()
    rs.set_settings(sc, _settings(auto_save=True, save_passes=True, passes=["beauty", "depth"],
                                  output_path=os.path.join(TMP, "auto", "shot.png")))
    m = worker.RenderManager()
    got = []
    buckets_seen = []
    m.finished.connect(got.append)
    m.bucketReady.connect(lambda r, img: buckets_seen.append(img.width()))
    assert m.render(sc, camera=_cam())
    assert m.is_running()
    assert m.wait(60)
    assert len(got) == 1 and len(m.history) == 1
    rec = got[0]
    assert rec.saved and all(os.path.exists(p) for p in rec.saved)
    assert any(p.endswith("shot_depth.png") for p in rec.saved)
    assert buckets_seen
    assert rec.image("depth").width() == 96
    assert rec.image("missing").width() == 96


def test_manager_animation_frames_and_cancel():
    sc, _cube = _scene_cube()
    rs.set_settings(sc, _settings(animation=True, frame_start=1, frame_end=3, auto_save=True,
                                  output_path=os.path.join(TMP, "anim", "f.png"), ao=False))
    m = worker.RenderManager(threaded=False)
    got = []
    m.finished.connect(got.append)
    m.render(sc, camera=_cam())
    m.wait(60)
    assert [r.result.frame for r in got] == [1, 2, 3]
    assert os.path.exists(os.path.join(TMP, "anim", "f_0002.png"))
    big = worker.RenderManager()
    cancelled = []
    big.cancelled.connect(lambda: cancelled.append(True))
    big.render(sc, camera=_cam(), settings=_settings(width=640, height=360, aa=4, animation=False))
    big.cancel()
    assert big.wait(60)
    assert cancelled and not big.history


def test_manager_render_while_busy_restarts():
    sc, _cube = _scene_cube()
    m = worker.RenderManager()
    got = []
    m.finished.connect(got.append)
    m.render(sc, camera=_cam(), settings=_settings(width=640, height=360, aa=4))
    m.render(sc, camera=_cam(), settings=_settings(width=64, height=32))
    assert m.wait(120)
    assert got and got[-1].result.width == 64


def _widget_sizes_ok(root) -> list:
    bad = []
    for w in [root] + root.findChildren(QWidget):
        if w.minimumHeight() == w.maximumHeight() and w.maximumHeight() < 10000:
            if not _allowed(w.maximumHeight()):
                bad.append((type(w).__name__, "h", w.maximumHeight()))
        if w.minimumWidth() == w.maximumWidth() and w.maximumWidth() < 10000:
            if not _allowed(w.maximumWidth()):
                bad.append((type(w).__name__, "w", w.maximumWidth()))
    return bad


def test_settings_panel_drives_settings():
    from quartz_studio.render.widgets import RenderSettingsPanel
    sc = reset_scene()
    panel = RenderSettingsPanel(sc)
    panel.resize(384, 640)
    panel.show()
    APP.processEvents()
    i = panel.preset_combo.findData("1280x720")
    panel.preset_combo.activated.emit(i)
    assert rs.get_settings(sc)["width"] == 1280
    assert panel.width_spin.value() == 1280
    panel.width_spin.setValue(800)
    s = rs.get_settings(sc)
    assert s["preset"] == "Custom" and s["width"] == 800
    assert panel.preset_combo.currentData() == "Custom"
    panel.aa_combo.activated.emit(panel.aa_combo.findData(4))
    assert rs.get_settings(sc)["aa"] == 4
    panel.ao_check.setChecked(False)
    assert rs.get_settings(sc)["ao"] is False
    assert not panel.ao_radius_spin.isEnabled()
    panel.pass_checks["normal"].setChecked(False)
    assert "normal" not in rs.get_settings(sc)["passes"]
    panel.bg_button.set_color([0.5, 0.25, 0.0], emit=True)
    assert rs.get_settings(sc)["bg_color"] == [0.5, 0.25, 0.0]
    panel.bg_combo.activated.emit(panel.bg_combo.findData("color"))
    assert panel.bg_button.isEnabled() and not panel.top_button.isEnabled()
    panel.format_combo.activated.emit(panel.format_combo.findData("jpg"))
    assert panel.quality_spin.isEnabled()
    panel.path_edit.setText(os.path.join(TMP, "p.png"))
    panel.path_edit.editingFinished.emit()
    assert rs.get_settings(sc)["output_path"].endswith("p.png")
    panel.exposure_spin.setValue(1.5)
    panel.gamma_spin.setValue(1.8)
    panel.tonemap_combo.activated.emit(panel.tonemap_combo.findData("aces"))
    panel.lights_combo.activated.emit(panel.lights_combo.findData("off"))
    panel.shadow_combo.activated.emit(panel.shadow_combo.findData(2048))
    panel.anim_check.setChecked(True)
    panel.end_spin.setValue(12)
    panel.bucket_combo.activated.emit(panel.bucket_combo.findData(128))
    panel.phong_spin.setValue(45.0)
    s = rs.get_settings(sc)
    assert (s["exposure"], s["gamma"], s["tonemap"], s["default_lights"], s["shadow_map"]) == (1.5, 1.8, "aces", "off", 2048)
    assert s["animation"] and s["frame_end"] == 12 and s["bucket_size"] == 128 and s["phong_angle"] == 45.0
    actions.add_camera_from_view(sc)
    APP.processEvents()
    names = [panel.camera_combo.itemText(i) for i in range(panel.camera_combo.count())]
    assert "Camera" in names
    panel.camera_combo.activated.emit(panel.camera_combo.findData("Camera"))
    assert rs.get_settings(sc)["camera"] == "Camera"
    sc.undo()
    panel.reset_defaults()
    assert rs.get_settings(sc) == rs.default_settings()
    assert _widget_sizes_ok(panel) == []
    panel.close()


def test_picture_viewer_shows_history_and_saves():
    from quartz_studio.render.widgets import PictureViewer
    sc, _cube = _scene_cube()
    rs.set_settings(sc, _settings(ao=False))
    m = worker.RenderManager()
    viewer = PictureViewer(sc, manager=m)
    viewer.resize(896, 512)
    viewer.show()
    APP.processEvents()
    assert not viewer.save_button.isEnabled()
    viewer.render_button.click()
    assert m.wait(60)
    APP.processEvents()
    assert viewer.record is not None and viewer.history_list.count() == 1
    assert viewer.pane.image is not None and viewer.pane.image.width() == 96
    beauty = viewer.pane.image
    viewer.set_pass("depth")
    assert viewer.pane.image is not beauty
    viewer.pane.set_zoom(1.0)
    viewer.zoom_in_button.click()
    assert viewer.pane.zoom == 2.0
    viewer.zoom_out_button.click()
    viewer.zoom_out_button.click()
    assert viewer.pane.zoom == 0.5
    viewer.zoom_combo.activated.emit(0)
    assert viewer.pane.fit
    path = os.path.join(TMP, "viewer.png")
    assert viewer.save_current(path)
    assert QImage(path).width() == 96
    assert viewer.save_current(os.path.join(TMP, "viewer.jpg"), "jpg")
    m.render(sc, camera=_cam())
    m.wait(60)
    APP.processEvents()
    assert viewer.history_list.count() == 2
    viewer.history_list.setCurrentRow(1)
    assert viewer.record is m.history[1]
    viewer.remove_button.click()
    assert viewer.history_list.count() == 1
    viewer.clear_button.click()
    assert viewer.history_list.count() == 0 and viewer.record is None
    assert _widget_sizes_ok(viewer) == []
    viewer.close()


def test_render_view_widget_renders_and_auto_updates():
    from quartz_studio.render.widgets import RenderView
    sc, cube = _scene_cube()
    rs.set_settings(sc, _settings(ao=False))
    view = RenderView(sc)
    view.resize(640, 448)
    view.show()
    view.scale_combo.activated.emit(view.scale_combo.findData(0.25))
    assert view.scale == 0.25
    view.render_button.click()
    assert view.manager.wait(60)
    APP.processEvents()
    assert view.record is not None
    w, h = view.view_size()
    assert view.record.result.width == w
    first = view.record
    view.auto_check.setChecked(True)
    view.manager.wait(60)
    APP.processEvents()
    second = view.record
    assert second is not first
    sc.set_object_position(0, 50.0)
    view._timer.timeout.emit()
    view.manager.wait(60)
    APP.processEvents()
    assert view.record is not second
    view.pass_combo.setCurrentIndex(view.pass_combo.findData("normal"))
    assert view.pane.image is not None
    view.auto_check.setChecked(False)
    assert _widget_sizes_ok(view) == []
    view.close()


def test_actions_contract():
    cmds = R.commands()
    assert all(isinstance(p, tuple) and p[0] == "Render" and callable(fn) for p, fn in cmds)
    leaves = {p[-1] for p, _fn in cmds}
    for ka in R.key_actions():
        name, shortcut = ka
        assert name in leaves and callable(ka.callback)
    assert dict((k[0], k[1]) for k in R.key_actions()) == {"Render View": "Ctrl+R",
                                                          "Render to Picture Viewer": "Shift+R",
                                                          "Edit Render Settings": "Ctrl+B"}
    titles = [t for t, _f, _a in R.docks()]
    assert titles == ["Render Settings", "Picture Viewer", "Render View"]
    assert all(a in ("left", "right", "bottom") for _t, _f, a in R.docks())
    sc = reset_scene()
    for title, factory, _area in R.docks():
        w1 = factory(sc)
        w2 = factory(sc, None)
        assert w1.parent() is None and w2 is not w1
        w1.deleteLater()
        w2.deleteLater()
    assert R.pages() == [("Render", ["Picture Viewer", "Render Settings", "Render View"])]


def test_actions_open_windows_and_render():
    sc, _cube = _scene_cube()
    rs.set_settings(sc, _settings(ao=False))
    panel = actions.edit_render_settings(sc)
    assert type(panel).__name__ == "RenderSettingsPanel"
    viewer = actions.show_picture_viewer(sc)
    assert type(viewer).__name__ == "PictureViewer"
    assert actions.show_picture_viewer(sc) is viewer
    m = worker.get_manager()
    before = len(m.history)
    assert actions.render_to_picture_viewer(sc)
    assert m.wait(60)
    APP.processEvents()
    assert len(m.history) == before + 1
    assert viewer.record is m.history[0]
    assert actions.render_view(sc)
    assert m.wait(60)
    assert m.history[0].target == "view"
    for kind in ("Point", "Spot", "Infinite", "Area"):
        obj = actions.add_light(kind, sc)
        assert obj.kind == LIGHT_KIND and obj.params["light_type"] == kind
        assert obj.mesh.loose_edges
    spot = [o for o in sc.objects if o.params.get("light_type") == "Spot"][0]
    light = snapshot.light_from_object(spot)
    to_origin = shading.normalize(-light.position)
    assert np.dot(light.direction, to_origin) > 0.999
    cam_obj = actions.add_camera_from_view(sc)
    assert cam_obj.kind == CAMERA_KIND
    assert not actions.cancel_render(sc)
    for title in (actions.DOCK_SETTINGS, actions.DOCK_VIEWER, actions.DOCK_VIEW):
        win = actions._WINDOWS.get(title)
        if win is not None:
            win.close()


def test_euler_from_axes_round_trip():
    from quartz_studio.scene import rotation_matrix
    rng = np.random.default_rng(5)
    for _ in range(10):
        ang = rng.uniform(-170, 170, 3)
        ang[1] = rng.uniform(-80, 80)
        m = rotation_matrix(ang)
        back = actions.euler_from_axes(m[:, 0], m[:, 1], m[:, 2])
        assert np.allclose(rotation_matrix(back), m, atol=1e-9)


def test_render_view_uses_canvas_camera():
    from quartz_studio.widgets.viewport import Viewport
    sc = reset_scene()
    vp = Viewport()
    vp.resize(656, 400)
    vp.show()
    APP.processEvents()
    canvas = vp.canvas
    canvas.setFocus()
    assert engine.active_canvas() is not None
    cam = engine.resolve_camera(sc, None, rs.default_settings())
    ref = from_orbit(engine.active_canvas().camera)
    assert np.allclose(cam.eye, ref.eye)
    vp.close()
    vp.deleteLater()
    APP.processEvents()


def test_dense_mesh_performance():
    import time
    sc = reset_scene()
    obj = sc.objects[0]
    n = 100
    u = np.linspace(0, 2 * np.pi, n + 1)[:-1]
    v = np.linspace(0.05, np.pi - 0.05, n)
    uu, vv = np.meshgrid(u, v)
    pts = np.stack([100 * np.sin(vv) * np.cos(uu), 100 * np.cos(vv), 100 * np.sin(vv) * np.sin(uu)], -1).reshape(-1, 3)
    polys = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j)
             for i in range(n - 1) for j in range(n)]
    obj.mesh = Mesh(pts, polys)
    cam = look_at((0.0, 150.0, -450.0), (0.0, 0.0, 0.0), fov=50.0)
    t = time.perf_counter()
    res = R.render(sc, camera=cam, settings={"preset": "640x360", "ao_samples": 6})
    assert res.stats["triangles"] == 2 * n * (n - 1)
    assert time.perf_counter() - t < 30.0
    assert res.passes["beauty"][180, 320, 3] == 1.0


def _roof_object(sc):
    obj = sc.objects[0]
    pts = []
    for z in (0, 1, 2):
        for x in (-1, 0, 1):
            pts.append((x * 100.0, 100.0 - abs(x) * 30.0, z * 100.0))
    obj.mesh = Mesh(pts, [(0, 3, 4, 1), (1, 4, 5, 2), (3, 6, 7, 4), (4, 7, 8, 5)])
    return obj


def test_history_keeps_bounded_memory():
    sc, _cube = _scene_cube()
    res = R.render(sc, camera=_cam(), settings=_settings(ao=False))
    assert all(np.asarray(v).dtype == np.float32 for v in res.passes.values())
    per_pixel = res.nbytes() / float(res.width * res.height)
    assert per_pixel == 48.0
    assert per_pixel * 1920 * 1080 / 2 ** 20 < 100.0
    old_full, old_total = worker.HISTORY_FULL_BYTES, worker.HISTORY_BYTES
    try:
        worker.HISTORY_FULL_BYTES = int(res.nbytes() * 1.5)
        worker.HISTORY_BYTES = int(res.nbytes() * 2.5)
        m = worker.RenderManager(threaded=False)
        reference = []
        m.finished.connect(lambda rec: reference.append(rec.result.rgba8("depth").copy()))
        for _ in range(6):
            m.render(sc, camera=_cam(), settings=_settings(ao=False))
            m.wait(60)
        assert len(reference) == 6
        assert not m.history[0].compact and m.history[0].result.passes["beauty"].dtype == np.float32
        assert all(r.compact for r in m.history[1:])
        assert len(m.history) >= 2
        assert m.history_bytes() <= worker.HISTORY_BYTES
        older = m.history[1]
        assert older.result.passes["beauty"].dtype == np.uint8
        assert np.array_equal(older.result.rgba8("depth"), reference[-2])
        img = older.image("depth")
        assert img.width() == 96 and img.height() == 54
        assert older.thumbnail().width() <= worker.THUMB_SIZE
        assert older.result.save(os.path.join(TMP, "compact.png"))
        assert QImage(os.path.join(TMP, "compact.png")).width() == 96
    finally:
        worker.HISTORY_FULL_BYTES, worker.HISTORY_BYTES = old_full, old_total


def test_image_pane_paint_cost_is_bounded_at_high_zoom():
    import time
    from quartz_studio.render.widgets import ImagePane
    pane = ImagePane()
    pane.resize(800, 600)
    pane.show()
    img = QImage(1920, 1080, QImage.Format.Format_RGBA8888)
    img.fill(0x80336699)
    pane.set_image(img)
    APP.processEvents()
    for zoom in (1.0, 8.0, 32.0):
        pane.set_zoom(zoom)
        APP.processEvents()
        t = time.perf_counter()
        pane.canvas.repaint()
        assert time.perf_counter() - t < 0.25, zoom
    from PySide6.QtGui import QColor
    small = QImage(2, 2, QImage.Format.Format_RGBA8888)
    small.fill(QColor(255, 0, 0))
    small.setPixelColor(1, 1, QColor(0, 255, 0))
    pane.set_image(small)
    pane.set_zoom(16.0)
    APP.processEvents()
    rect = pane.image_rect()
    shot = pane.canvas.grab().toImage()
    a = shot.pixelColor(int(rect.left() + 8), int(rect.top() + 8))
    b = shot.pixelColor(int(rect.left() + 24), int(rect.top() + 24))
    assert (a.red(), a.green()) == (255, 0) and (b.red(), b.green()) == (0, 255)
    pane.close()


def test_render_view_disconnects_from_shared_manager_when_deleted():
    from PySide6.QtCore import QCoreApplication, QEvent
    from quartz_studio.render.widgets import RenderView
    sc, _cube = _scene_cube()
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda *exc: errors.append(exc)
    try:
        host = QWidget()
        view = RenderView(sc, host)
        assert view.shared is worker.get_manager()
        host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        m = worker.get_manager()
        m.render(sc, camera=_cam(), settings=_settings(width=32, height=32, ao=False), target="view")
        assert m.wait(60)
        APP.processEvents()
    finally:
        sys.excepthook = old_hook
    assert errors == []


def test_phong_normals_match_tags_package_with_edge_breaks():
    from quartz_studio.tags import shading as tag_shading
    sc = reset_scene()
    obj = _roof_object(sc)
    tag = {"type": "phong", "angle": 80, "angle_limit": True, "use_edge_breaks": True,
           "edge_breaks": [[1, 4], [4, 7]]}
    store.set_object(obj, "tags", [tag])
    ours = np.concatenate(bridges.corner_normals(obj))
    ref = np.concatenate(tag_shading.object_normals(obj))
    assert np.abs(ours - ref).max() < 1e-12
    centre = ours[np.flatnonzero(np.concatenate([np.array(p) for p in obj.mesh.polygons]) == 4)]
    assert np.allclose(np.abs(centre[:, 0]), 0.287, atol=2e-3) and np.allclose(centre[:, 2], 0.0)
    fallback = bridges._phong_fallback(obj.mesh, True, 80.0, [(1, 4), (4, 7)])
    assert np.abs(fallback - ref).max() < 1e-12
    store.set_object(obj, "tags", [])
    flat = np.concatenate(bridges.corner_normals(obj))
    assert np.abs(flat - np.concatenate(tag_shading.flat_normals(obj.mesh))).max() < 1e-12
    assert bridges.phong_angle(obj, rs.default_settings()) is None
    store.set_object(obj, "tags", [tag])
    obj.rotation = np.array([20.0, 35.0, -10.0])
    obj.scale = np.array([2.0, 0.5, 1.5])
    data = snapshot.triangulate_object(obj)
    lin = obj.world_matrix()[:3, :3]
    world_ref = shading.normalize(ref @ np.linalg.inv(lin))
    starts = bridges.corner_layout(obj.mesh.polygons)["starts"]
    expect = np.stack([world_ref[[starts[k], starts[k] + c, starts[k] + c + 1]] for c in (1, 2) for k in range(4)])
    assert data["normals"].shape == expect.shape
    assert np.allclose(data["normals"], expect, atol=1e-9)
    assert np.all(np.einsum("ij,ij->i", data["normals"][:, 0], data["face"]) > 0.5)


def test_backface_culling_on_mirrored_object():
    sc, cube = _scene_cube()
    cube.scale = np.array([-1.0, 1.0, 1.0])
    data = snapshot.triangulate_object(cube)
    centre = data["tris"].mean(axis=1)
    assert np.all(np.einsum("ij,ij->i", data["face"], centre) > 0)
    assert np.all(np.einsum("ij,ij->i", data["normals"][:, 0], centre) > 0)
    s = _settings(ao=False, width=64, height=64)
    culled = R.render(sc, camera=_cam(), settings=dict(s, backface_culling=True))
    full = R.render(sc, camera=_cam(), settings=dict(s, backface_culling=False))
    assert culled.stats["raster_triangles"] == 2
    assert np.abs(culled.passes["beauty"] - full.passes["beauty"]).max() < 1e-6
    cube.scale = np.array([1.0, 1.0, 1.0])
    plain = R.render(sc, camera=_cam(), settings=dict(s, backface_culling=True))
    assert np.abs(plain.passes["beauty"] - culled.passes["beauty"]).max() < 1e-6


def test_auto_save_and_panel_keep_format_and_extension_in_sync():
    from quartz_studio.render.widgets import RenderSettingsPanel
    sc, _cube = _scene_cube()
    folder = os.path.join(TMP, "fmt")
    m = worker.RenderManager(threaded=False)
    got = []
    m.finished.connect(got.append)
    m.render(sc, camera=_cam(), settings=_settings(ao=False, auto_save=True, format="jpg",
                                                   output_path=os.path.join(folder, "out.png")))
    m.wait(60)
    assert got[0].saved == [os.path.join(folder, "out.jpg")]
    with open(got[0].saved[0], "rb") as fh:
        assert fh.read(3) == b"\xff\xd8\xff"
    assert not os.path.exists(os.path.join(folder, "out.png"))
    m.render(sc, camera=_cam(), settings=_settings(ao=False, auto_save=True, format="png",
                                                   output_path=os.path.join(folder, "back.jpeg")))
    m.wait(60)
    with open(got[1].saved[0], "rb") as fh:
        assert got[1].saved[0].endswith("back.png") and fh.read(4) == b"\x89PNG"
    assert engine.format_path("a/b.jpeg", "jpg") == "a/b.jpeg"
    assert engine.format_path("a/b", "png") == "a/b.png"
    panel = RenderSettingsPanel(sc)
    panel.path_edit.setText(os.path.join(folder, "p.png"))
    panel.path_edit.editingFinished.emit()
    assert rs.get_settings(sc)["format"] == "png"
    panel.format_combo.activated.emit(panel.format_combo.findData("jpg"))
    s = rs.get_settings(sc)
    assert s["format"] == "jpg" and s["output_path"].endswith("p.jpg")
    assert panel.path_edit.text().endswith("p.jpg")
    panel.path_edit.setText(os.path.join(folder, "q.png"))
    panel.path_edit.editingFinished.emit()
    s = rs.get_settings(sc)
    assert s["format"] == "png" and s["output_path"].endswith("q.png")
    panel.set_output_path(os.path.join(folder, "noext"), "JPG Image (*.jpg)")
    s = rs.get_settings(sc)
    assert s["format"] == "jpg" and s["output_path"].endswith("noext.jpg")
    panel.close()


def test_render_frame_argument_evaluates_animation():
    try:
        from quartz_studio import anim
    except Exception:
        return
    if not all(hasattr(anim, n) for n in ("insert_key", "set_frame", "evaluate")):
        return
    sc, cube = _scene_cube()
    anim.insert_key(cube, "position.x", 0, 0.0, interp="linear", scene=sc)
    anim.insert_key(cube, "position.x", 4, 400.0, interp="linear", scene=sc)
    anim.set_frame(sc, 2)
    assert abs(float(cube.position[0]) - 200.0) < 1e-6
    s = _settings(ao=False, passes=["depth"])
    at2 = R.render(sc, camera=_cam(), settings=s)
    at4 = R.render(sc, camera=_cam(), settings=s, frame=4)
    assert at4.frame == 4
    cols2 = np.flatnonzero(np.isfinite(at2.passes["depth"]).any(axis=0)).mean()
    cols4 = np.flatnonzero(np.isfinite(at4.passes["depth"]).any(axis=0)).mean()
    assert cols4 > cols2 + 5
    assert abs(float(cube.position[0]) - 200.0) < 1e-6
    job = R.prepare_job(sc, _cam(), s, frame=4, defer=True)
    assert abs(float(cube.position[0]) - 200.0) < 1e-6
    again = R.execute_job(job)
    assert np.array_equal(np.isfinite(again.passes["depth"]), np.isfinite(at4.passes["depth"]))


def test_render_camera_survives_rename_and_warns_when_missing():
    from quartz_studio.render.widgets import RenderSettingsPanel
    sc, _cube = _scene_cube()
    a = sc.add_parametric(CAMERA_KIND, name="Cam A")
    a.position = np.array([0.0, 0.0, -1000.0])
    sc.add_parametric(CAMERA_KIND, name="Cam B")
    panel = RenderSettingsPanel(sc)
    panel.camera_combo.activated.emit(panel.camera_combo.findData("Cam A"))
    s = rs.get_settings(sc)
    assert s["camera"] == "Cam A" and s["camera_id"]
    assert engine.camera_uid(a) == s["camera_id"]
    sc.rename_object(a, "Cam C")
    APP.processEvents()
    assert engine.resolve_camera(sc, None, rs.get_settings(sc)).name == "Cam C"
    assert panel.camera_combo.currentText() == "Cam C"
    res = R.render(sc, settings=_settings(ao=False, camera="Cam C", camera_id=s["camera_id"]))
    assert res.camera == "Cam C" and res.stats["warnings"] == []
    rs.update_settings(sc, camera="Nobody")
    assert rs.get_settings(sc)["camera_id"] == ""
    panel.refresh()
    assert panel.camera_combo.currentText() == "Nobody (missing)"
    cam, warning = engine.resolve_camera_info(sc, None, rs.get_settings(sc))
    assert "Nobody" in warning and isinstance(cam, RenderCamera)
    res = R.render(sc, settings=rs.get_settings(sc) | SMALL | {"ao": False})
    assert res.stats["warnings"] and "Nobody" in res.stats["warnings"][0]
    panel.close()


def test_prepare_job_defers_geometry_off_the_gui_thread():
    import time
    sc = reset_scene()
    obj = sc.objects[0]
    n = 120
    u = np.linspace(0, 2 * np.pi, n + 1)[:-1]
    v = np.linspace(0.05, np.pi - 0.05, n)
    uu, vv = np.meshgrid(u, v)
    pts = np.stack([100 * np.sin(vv) * np.cos(uu), 100 * np.cos(vv), 100 * np.sin(vv) * np.sin(uu)],
                   -1).reshape(-1, 3)
    obj.mesh = Mesh(pts, [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j)
                          for i in range(n - 1) for j in range(n)])
    store.set_object(obj, "tags", [{"type": "phong", "angle": 80.0, "angle_limit": True}])
    cam = look_at((0.0, 150.0, -450.0), (0.0, 0.0, 0.0), fov=50.0)
    s = _settings(ao=False, shadows=False, width=64, height=36)
    R.prepare_job(sc, cam, s, defer=True)
    t = time.perf_counter()
    job = R.prepare_job(sc, cam, s, defer=True)
    assert time.perf_counter() - t < 0.25
    assert job.geometry is None and job.capture
    obj.position = np.array([5000.0, 0.0, 0.0])
    res = R.execute_job(job)
    assert res.stats["triangles"] == 2 * n * (n - 1)
    assert res.passes["beauty"][18, 32, 3] == 1.0
    obj.position = np.zeros(3)
    m = worker.RenderManager()
    from PySide6.QtCore import QTimer
    gaps = []
    stamp = [time.perf_counter()]

    def tick():
        now = time.perf_counter()
        gaps.append(now - stamp[0])
        stamp[0] = now

    timer = QTimer()
    timer.setInterval(16)
    timer.timeout.connect(tick)
    timer.start()
    stamp[0] = time.perf_counter()
    m.render(sc, camera=cam, settings=s)
    assert m.wait(60)
    timer.stop()
    assert gaps and max(gaps) < 0.5
    assert m.history[0].result.stats["triangles"] == 2 * n * (n - 1)


def test_material_alpha_composites_over_opaque_background():
    sc, cube = _scene_cube()
    s = _settings(ao=False, background="gradient", transparency_depth=0)
    store.set_object(cube, "material", {"base_color": [1.0, 0.0, 0.0], "alpha": 1.0})
    solid = R.render(sc, camera=_cam(), settings=s).passes["beauty"]
    store.set_object(cube, "material", {"base_color": [1.0, 0.0, 0.0], "alpha": 0.3})
    half = R.render(sc, camera=_cam(), settings=s).passes["beauty"]
    assert np.all(half[..., 3] == 1.0)
    bg = shading.background(np.array([27.0]), 54, rs.clean_settings(s))[0][0]
    assert np.allclose(half[27, 48, :3], 0.3 * solid[27, 48, :3] + 0.7 * bg, atol=1e-5)
    clear = R.render(sc, camera=_cam(), settings=dict(s, background="transparent")).passes["beauty"]
    assert abs(float(clear[27, 48, 3]) - 0.3) < 1e-6
    assert np.allclose(clear[27, 48, :3], solid[27, 48, :3], atol=1e-5)


def test_transparent_surface_blends_with_geometry_behind():
    from quartz_studio.render.widgets import RenderSettingsPanel
    sc, cube = _scene_cube()
    store.set_object(cube, "material", {"base_color": [0.9, 0.05, 0.05]})
    glass = sc.add_object("Glass", _quad(-300.0, 400.0))
    s = _settings(ao=False, shadows=False, transparency_depth=4)
    store.set_object(glass, "material", {"base_color": [0.05, 0.8, 0.05], "alpha": 1.0})
    green = R.render(sc, camera=_cam(), settings=s).passes["beauty"]
    store.set_object(glass, "material", {"base_color": [0.05, 0.8, 0.05], "alpha": 0.0})
    red = R.render(sc, camera=_cam(), settings=s).passes["beauty"]
    store.set_object(glass, "material", {"base_color": [0.05, 0.8, 0.05], "alpha": 0.5})
    res = R.render(sc, camera=_cam(), settings=s)
    mix = res.passes["beauty"]
    assert np.allclose(mix[27, 48, :3], 0.5 * green[27, 48, :3] + 0.5 * red[27, 48, :3], atol=1e-5)
    assert mix[27, 48, 3] == 1.0
    assert abs(float(res.passes["depth"][27, 48]) - 1000.0 + 300.0) < 1.0
    bg = shading.background(np.array([27.0]), 54, rs.clean_settings(s))[0][0]
    flat = R.render(sc, camera=_cam(), settings=dict(s, transparency_depth=0)).passes["beauty"]
    assert np.allclose(flat[27, 48, :3], 0.5 * green[27, 48, :3] + 0.5 * bg, atol=1e-5)
    store.set_object(cube, "material", {"base_color": [0.9, 0.05, 0.05], "alpha": 0.5})
    clear = R.render(sc, camera=_cam(), settings=dict(s, background="transparent")).passes["beauty"]
    assert abs(float(clear[27, 48, 3]) - (1.0 - 0.5 * 0.5 * 0.5)) < 1e-5
    one = R.render(sc, camera=_cam(), settings=dict(s, background="transparent", transparency_depth=1))
    assert abs(float(one.passes["beauty"][27, 48, 3]) - 0.75) < 1e-5
    panel = RenderSettingsPanel(sc)
    panel.transparency_spin.setValue(2)
    assert rs.get_settings(sc)["transparency_depth"] == 2
    panel.close()


def test_viewer_zoom_label_and_pass_fallback():
    from quartz_studio.render.widgets import PictureViewer, RenderView, ZOOM_LEVELS
    sc, _cube = _scene_cube()
    rs.set_settings(sc, _settings(ao=False, width=64, height=48, passes=["beauty"]))
    m = worker.RenderManager()
    viewer = PictureViewer(sc, manager=m)
    viewer.resize(896, 512)
    viewer.show()
    viewer.render_button.click()
    assert m.wait(60)
    APP.processEvents()
    viewer.pane.set_zoom(1.0)
    for _ in range(6):
        viewer.zoom_in_button.click()
    assert viewer.pane.zoom == 32.0
    assert viewer.zoom_combo.currentText() == "3200%"
    viewer.pane.set_zoom(16.0)
    assert viewer.zoom_combo.currentText() == "1600%"
    assert viewer.zoom_combo.count() == len(ZOOM_LEVELS) + 2
    viewer.zoom_out_button.click()
    assert viewer.pane.zoom == 8.0 and viewer.zoom_combo.currentText() == "800%"
    assert viewer.zoom_combo.count() == len(ZOOM_LEVELS) + 1
    viewer.zoom_combo.activated.emit(0)
    assert viewer.pane.fit and viewer.zoom_combo.currentText() == "Fit"
    assert viewer.set_pass("depth") is False
    assert viewer.current_pass() == "beauty"
    depth_index = viewer.pass_combo.findData("depth")
    assert not viewer.pass_combo.model().item(depth_index).isEnabled()
    viewer.pass_combo.setCurrentIndex(depth_index)
    APP.processEvents()
    assert viewer.current_pass() == "beauty"
    viewer.close()
    view = RenderView(sc)
    view.scale_combo.activated.emit(view.scale_combo.findData(0.25))
    view.render()
    assert view.manager.wait(60)
    APP.processEvents()
    assert view.set_pass("depth") is False and view.current_pass() == "beauty"
    view.pass_combo.setCurrentIndex(view.pass_combo.findData("normal"))
    assert view.current_pass() == "beauty"
    view.close()


def test_frame_start_spin_only_enabled_with_frame_range():
    from quartz_studio.render.widgets import RenderSettingsPanel
    sc = reset_scene()
    panel = RenderSettingsPanel(sc)
    assert not rs.get_settings(sc)["animation"]
    assert not panel.start_spin.isEnabled() and not panel.end_spin.isEnabled()
    panel.anim_check.setChecked(True)
    assert panel.start_spin.isEnabled() and panel.end_spin.isEnabled() and panel.step_spin.isEnabled()
    panel.start_spin.setValue(3)
    panel.end_spin.setValue(5)
    assert rs.frame_list(rs.get_settings(sc)) == [3, 4, 5]
    panel.close()


def test_camera_object_with_negative_scale_keeps_upright_basis():
    sc = reset_scene()
    obj = sc.add_parametric(CAMERA_KIND)
    obj.scale = np.array([2.0, 1.0, -1.0])
    cam = from_object(obj)
    assert np.allclose(cam.forward, [0.0, 0.0, -1.0]) and np.allclose(cam.up, [0.0, 1.0, 0.0])
    assert np.allclose(np.cross(cam.up, cam.forward), cam.right)
    obj.scale = np.array([-1.0, 1.0, 1.0])
    cam = from_object(obj)
    assert np.allclose(cam.forward, [0.0, 0.0, 1.0]) and np.allclose(cam.up, [0.0, 1.0, 0.0])
    assert np.allclose(cam.right, [1.0, 0.0, 0.0])
    obj.scale = np.array([1.0, -3.0, 1.0])
    obj.rotation = np.array([0.0, 30.0, 0.0])
    cam = from_object(obj)
    m = np.stack([cam.right, cam.up, cam.forward])
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)
    assert np.allclose(cam.up, [0.0, -1.0, 0.0], atol=1e-12)


def test_screen_ao_has_no_false_occlusion_on_grazing_plane():
    sc = reset_scene()
    floor = sc.objects[0]
    h = 3000.0
    floor.mesh = Mesh([(-h, 0.0, -h), (h, 0.0, -h), (h, 0.0, h), (-h, 0.0, h)], [(0, 3, 2, 1)])
    for eye, ortho in (((0.0, 100.0, -1500.0), False), ((0.0, 60.0, -2500.0), False), ((0.0, 100.0, -1500.0), True)):
        cam = look_at(eye, (0.0, 0.0, 0.0), ortho=ortho, ortho_width=2000.0 if ortho else None)
        res = R.render(sc, camera=cam, settings=_settings(width=160, height=90, ao=True, ao_samples=16,
                                                           passes=["ao", "depth"]))
        covered = np.isfinite(res.passes["depth"])
        assert covered.sum() > 1000
        assert res.passes["ao"][covered].min() > 0.99, (eye, ortho, res.passes["ao"][covered].min())
    test_screen_ao_darkens_corner()


def test_picture_viewer_ignores_view_renders_when_render_view_is_open():
    from quartz_studio.render.widgets import PictureViewer, RenderView, visible_render_view
    sc, _cube = _scene_cube()
    rs.set_settings(sc, _settings(ao=False))
    shared = worker.get_manager()
    viewer = PictureViewer(sc)
    viewer.show()
    shared.render(sc, camera=_cam(), target="viewer")
    assert shared.wait(60)
    APP.processEvents()
    shown = viewer.record
    assert shown is not None and shown.target == "viewer"
    view = RenderView(sc)
    view.show()
    APP.processEvents()
    assert visible_render_view() is view
    before = len(shared.history)
    assert actions.render_view(sc)
    assert view.manager.wait(60) and shared.wait(60)
    APP.processEvents()
    assert len(shared.history) == before
    assert view.record is not None and view.record.target == "view"
    assert viewer.record is shown
    shared.render(sc, camera=_cam(), target="view")
    assert shared.wait(60)
    APP.processEvents()
    assert viewer.record is shown
    assert view.record.target == "view" and view.record is shared.history[0]
    view.close()
    APP.processEvents()
    assert visible_render_view() is None
    shared.render(sc, camera=_cam(), target="view")
    assert shared.wait(60)
    APP.processEvents()
    assert viewer.record is shared.history[0] and viewer.record.target == "view"
    viewer.close()


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
