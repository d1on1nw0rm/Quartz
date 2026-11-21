from __future__ import annotations

import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QPointF

from tests.test_camera import ALT, FRONT_SPOT, RIGHT, _drag, _empty_spot, _far_cube, _image, _make, _px, _wheel

STEPS = 500


def _finite_state(canvas) -> bool:
    cam = canvas.camera
    state = cam.state()
    flat = [state[0], state[1], state[2], *state[3]]
    return bool(all(math.isfinite(v) for v in flat) and math.isfinite(cam.near) and cam.near > 0.0)


def _reach(canvas, point) -> float:
    return float(np.linalg.norm(canvas.camera.position() - np.asarray(point, float)))


def _near_colour(rgb, other, tolerance: int = 6) -> bool:
    return all(abs(int(a) - int(b)) <= tolerance for a, b in zip(rgb, other))


def _pixel(img, pos) -> tuple[int, int, int]:
    c = img.pixelColor(int(round(float(pos[0]))), int(round(float(pos[1]))))
    return c.red(), c.green(), c.blue()


def _face_colour(canvas, hit) -> tuple[int, int, int]:
    obj, k = hit[0], hit[1]
    view = canvas._object_view(obj)
    light = canvas._light_dir()
    dots = view.normals @ light
    lam = float(dots[k]) if view.front[k] else float(-dots[k] * 0.55)
    c = canvas._shade(lam)
    return c.red(), c.green(), c.blue()


def test_five_hundred_wheel_steps_in_never_stall_and_never_raise() -> None:
    from quartz_studio.widgets.viewport import reach_floor

    canvas, _scene = _make()
    spot = _px(canvas, FRONT_SPOT)
    point = np.array(FRONT_SPOT)
    floor = reach_floor(point)
    reach = _reach(canvas, point)
    start = reach
    stalled_above_floor = 0
    for _ in range(STEPS):
        _wheel(canvas, spot, 1)
        now = _reach(canvas, point)
        if now > floor * (1.0 + 1e-6) and now >= reach * (1.0 - 1e-9):
            stalled_above_floor += 1
        reach = now
        assert _finite_state(canvas)
    assert stalled_above_floor == 0, stalled_above_floor
    assert reach < 1e-4 < start, (start, reach)
    assert reach >= floor * (1.0 - 1e-6), (reach, floor)
    assert float(canvas.camera.depth(point)[0]) > 0.0
    assert np.allclose(_px(canvas, point), spot, atol=1e-3)
    hit = canvas.hit_at(spot)
    img = _image(canvas)
    assert hit is not None and _near_colour(_pixel(img, spot), _face_colour(canvas, hit), 8)


def test_five_hundred_wheel_steps_out_stay_finite_and_bounded() -> None:
    from quartz_studio.widgets.viewport import REACH_CEIL

    canvas, _scene = _make()
    spot = _px(canvas, FRONT_SPOT)
    for _ in range(STEPS):
        _wheel(canvas, spot, 1)
    for _ in range(STEPS):
        _wheel(canvas, spot, -1)
        assert _finite_state(canvas)
    cam = canvas.camera
    assert 1e12 < cam.distance <= REACH_CEIL * (1.0 + 1e-9), cam.distance
    assert abs(cam.near - 1.0) < 1e-12, cam.near
    img = _image(canvas)
    assert img.width() > 0 and np.all(np.isfinite(canvas.project_world([FRONT_SPOT])))
    assert _pixel(img, (canvas.width() // 2, canvas.height() // 2)) is not None


def test_zoom_out_then_in_over_the_same_spot_returns_the_distance() -> None:
    canvas, _scene = _make()
    spot = _px(canvas, FRONT_SPOT)
    d0 = canvas.camera.distance
    for _ in range(200):
        _wheel(canvas, spot, -1)
    far = canvas.camera.distance
    assert 1e12 < far < 1e15, far
    for _ in range(200):
        _wheel(canvas, spot, 1)
    assert abs(canvas.camera.distance / d0 - 1.0) < 1e-6, (canvas.camera.distance, d0)


def test_framing_still_works_after_extreme_zoom() -> None:
    canvas, scene = _make()
    spot = _px(canvas, FRONT_SPOT)
    for _ in range(STEPS):
        _wheel(canvas, spot, 1)
    for _ in range(STEPS):
        _wheel(canvas, spot, -1)
    assert canvas.frame_all()
    assert _finite_state(canvas) and 100.0 < canvas.camera.distance < 5000.0, canvas.camera.distance
    obj = scene.active
    xy = canvas.project_world(obj.world_points())
    film = canvas.film_rect()
    assert np.all(np.isfinite(xy))
    assert xy[:, 0].min() >= film.left() - 1 and xy[:, 0].max() <= film.right() + 1
    canvas.reset_camera()
    assert abs(canvas.camera.near - 1.0) < 1e-12 and abs(canvas.camera.distance - 1618.5) < 1e-9


def test_empty_space_wheel_keeps_moving_through_the_scene() -> None:
    canvas, scene = _make()
    _far_cube(scene, canvas)
    empty = _empty_spot(canvas)
    assert canvas.hit_at(empty) is None
    for _ in range(40):
        eye = canvas.camera.position()
        _wheel(canvas, empty, 1)
        assert float(np.linalg.norm(canvas.camera.position() - eye)) > 0.5
        assert canvas.camera.distance >= canvas.carry_depth() - 1e-9
        assert _finite_state(canvas)


def test_alt_right_drag_dolly_has_no_floor_but_never_passes_the_point() -> None:
    from quartz_studio.widgets.viewport import reach_floor

    canvas, _scene = _make()
    spot = _px(canvas, FRONT_SPOT)
    point = np.array(FRONT_SPOT)
    for _ in range(3):
        _drag(canvas, spot, spot + (2000.0, 0.0), ALT, RIGHT, steps=20)
    reach = _reach(canvas, point)
    assert reach_floor(point) * (1.0 - 1e-6) <= reach < 1e-3, reach
    assert _finite_state(canvas)
    assert float(canvas.camera.depth(point)[0]) > 0.0
    _image(canvas)


def test_orthographic_zoom_is_unlimited_in_and_out() -> None:
    canvas, _scene = _make()
    canvas.set_view("Front")
    assert canvas.camera.ortho
    centre = np.array([canvas.width() / 2.0, canvas.height() / 2.0])
    for _ in range(150):
        _wheel(canvas, centre, 1)
        assert _finite_state(canvas)
    assert canvas.camera.distance < 1e-4, canvas.camera.distance
    _image(canvas)
    for _ in range(300):
        _wheel(canvas, centre, -1)
        assert _finite_state(canvas)
    assert canvas.camera.distance > 1e9, canvas.camera.distance
    _image(canvas)


def test_dolly_helper_is_unbounded_within_the_numeric_guards() -> None:
    from quartz_studio.widgets.viewport import REACH_CEIL, REACH_FLOOR, OrbitCamera

    cam = OrbitCamera()
    for _ in range(100):
        cam.dolly(0.5)
    assert cam.distance == REACH_FLOOR
    for _ in range(200):
        cam.dolly(4.0)
    assert cam.distance == REACH_CEIL


def test_near_plane_follows_the_distance() -> None:
    canvas, _scene = _make()
    spot = _px(canvas, FRONT_SPOT)
    point = np.array(FRONT_SPOT)
    assert canvas.camera.near == 1.0
    while _reach(canvas, point) > 1e-3:
        _wheel(canvas, spot, 1)
    assert canvas.camera.near <= 1e-6 * 1.0001, canvas.camera.near
    for _ in range(STEPS):
        _wheel(canvas, spot, 1)
    assert 0.0 < canvas.camera.near <= 1e-8
    canvas.reset_camera()
    assert canvas.camera.near == 1.0


def test_frame_points_fits_a_one_millimetre_cube() -> None:
    canvas, _scene = _make()
    h = 0.05
    pts = np.array([[x, y, z] for x in (-h, h) for y in (-h, h) for z in (-h, h)])
    assert canvas.frame_points(pts)
    assert canvas.camera.distance < 1.0, canvas.camera.distance
    assert canvas.camera.near <= 1e-3
    xy = canvas.project_world(pts)
    assert np.all(np.isfinite(xy))
    width = float(xy[:, 0].max() - xy[:, 0].min())
    assert width > canvas.film_rect().height() / 2.0, width


def test_polygon_far_off_screen_is_clipped_and_its_visible_part_painted() -> None:
    from quartz_studio.scene import Mesh
    from quartz_studio.widgets.viewport import SCREEN_GUARD

    canvas, scene = _make()
    scene.remove_object(scene.objects[0])
    obj = scene.add_object("Spike", Mesh([(-50.0, -50.0, 0.0), (50.0, -50.0, 0.0), (0.0, 6.0e8, 0.0)],
                                         [(0, 1, 2)]))
    scene.set_active(obj)
    cam = canvas.camera
    cam.heading, cam.pitch, cam.distance, cam.ortho, cam.near = 0.0, 0.0, 600.0, False, 1.0
    canvas.update()
    view = canvas._object_view(obj)
    assert float(np.abs(view.screen).max()) > 1.0e8
    poly, _depth = canvas._poly_draw(view, 0)
    assert poly is not None
    for q in poly:
        assert -SCREEN_GUARD - 1e-6 <= q.x() <= canvas.width() + SCREEN_GUARD + 1e-6
        assert -SCREEN_GUARD - 1e-6 <= q.y() <= canvas.height() + SCREEN_GUARD + 1e-6
    img = _image(canvas)
    inside = _px(canvas, (0.0, 0.0, 0.0))
    probe = _pixel(img, (inside[0], inside[1]))
    corner = _pixel(img, (inside[0] + 400, inside[1] + 250))
    assert not _near_colour(probe, corner, 12), (probe, corner)


def test_segments_far_off_screen_are_clipped_to_the_guard() -> None:
    from quartz_studio.widgets.viewport import SCREEN_GUARD

    canvas, _scene = _make()
    p0 = np.array([[-1.0e9, 100.0], [10.0, 10.0], [5.0e9, 5.0e9], [-9.0e9, 50.0]])
    p1 = np.array([[1.0e9, 100.0], [20.0, 20.0], [6.0e9, 6.0e9], [-8.0e9, 60.0]])
    q0, q1, ok = canvas._guard_segments(p0, p1)
    assert ok.tolist() == [True, True, False, False]
    assert abs(q0[0, 0] + SCREEN_GUARD) < 1e-6 and abs(q1[0, 0] - (canvas.width() + SCREEN_GUARD)) < 1e-6
    assert np.allclose(q0[1], p0[1]) and np.allclose(q1[1], p1[1])


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
