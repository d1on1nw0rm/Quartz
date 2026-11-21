from __future__ import annotations

import math
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_PREFS_DIR = tempfile.mkdtemp(prefix="quartz-display-")
os.environ["QUARTZ_PREFS_DIR"] = _PREFS_DIR

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtGui import QColor, QImage

from quartz_studio import prefs, theme
from quartz_studio.widgets import display_filter
from tests import test_viewport_draw as draw

HEADINGS = (35.0, 25.0, 600.0)


def _fresh(mode: str = "model"):
    prefs.reload()
    display_filter.reset()
    canvas, scene = draw._make(mode)
    scene.set_tool("select")
    cam = canvas.camera
    cam.heading, cam.pitch, cam.distance, cam.ortho = HEADINGS[0], HEADINGS[1], HEADINGS[2], False
    return canvas, scene


def _sub():
    canvas, scene = _fresh()
    cube = scene.active
    sub = scene.add_parametric("subdivision_surface", adopt=cube)
    scene.set_active(sub)
    draw._settle(draw._app())
    return canvas, scene, sub


def _shot(canvas) -> QImage:
    draw._settle(draw._app())
    return canvas.grab().toImage()


def _grey(img: QImage, pos) -> float:
    x, y = int(round(float(pos[0]))), int(round(float(pos[1])))
    if not (0 <= x < img.width() and 0 <= y < img.height()):
        return 0.0
    c = img.pixelColor(x, y)
    return (c.red() + c.green() + c.blue()) / 3.0


def _rgb(img: QImage, pos) -> tuple[int, int, int]:
    c = img.pixelColor(int(round(float(pos[0]))), int(round(float(pos[1]))))
    return c.red(), c.green(), c.blue()


def _close(a, b, tolerance: int) -> bool:
    return all(abs(int(p) - int(q)) <= tolerance for p, q in zip(a, b))


def _token(token: str) -> tuple[int, int, int]:
    c = QColor(token)
    return c.red(), c.green(), c.blue()


def _background(canvas, y: float) -> tuple[int, int, int]:
    top, bottom = _token(theme.VIEWPORT_TOP), _token(theme.VIEWPORT_BOTTOM)
    t = min(max((y + 0.5) / canvas.inner_rect().height(), 0.0), 1.0)
    return tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))


def _face_colour(canvas, view, k: int) -> tuple[int, int, int]:
    dots = view.normals @ canvas._light_dir()
    lam = float(dots[k]) if view.front[k] else float(-dots[k] * 0.55)
    c = canvas._shade(lam)
    return c.red(), c.green(), c.blue()


def _centroid(canvas, view, k: int):
    poly, _depth = canvas._poly_screen(view, k)
    if poly is None:
        return None
    pts = np.array([(q.x(), q.y()) for q in poly])
    return pts.mean(axis=0)


def _face_stats(canvas, obj, img: QImage, tolerance: int = 5) -> tuple[int, int, int, int]:
    view = canvas._object_view(obj)
    shaded = background = total = 0
    for k in range(len(obj.mesh.polygons)):
        if not view.front[k]:
            continue
        at = _centroid(canvas, view, k)
        if at is None:
            continue
        total += 1
        pixel = _rgb(img, at)
        if _close(pixel, _face_colour(canvas, view, k), tolerance):
            shaded += 1
        elif _close(pixel, _background(canvas, at[1]), 3):
            background += 1
    return shaded, background, total, len(obj.mesh.polygons)


def _edge_samples(canvas, obj, front: bool | None):
    view = canvas._object_view(obj)
    out = []
    for edge, faces in view.edge_faces.items():
        flags = [bool(view.front[k]) for k in faces]
        if len(flags) != 2:
            continue
        if front is True and not all(flags):
            continue
        if front is False and any(flags):
            continue
        a, b = view.screen[edge[0]], view.screen[edge[1]]
        length = float(np.hypot(*(b - a)))
        if length < 14.0:
            continue
        n = np.array([-(b - a)[1], (b - a)[0]]) / length
        for t in (0.35, 0.5, 0.65):
            out.append((edge, a + (b - a) * t, n))
    return out


def _hidden_samples(canvas, obj):
    from quartz_studio.widgets.viewport import _segment_distance

    view = canvas._object_view(obj)
    lines = []
    for edge, faces in view.edge_faces.items():
        if any(bool(view.front[k]) for k in faces):
            a, b = view.screen[edge[0]], view.screen[edge[1]]
            lines.append((a[0], a[1], b[0], b[1]))
    out = []
    for edge, at, n in _edge_samples(canvas, obj, False):
        if all(_segment_distance(at[0], at[1], *line) > 3.0 for line in lines):
            out.append((edge, at, n))
    return out


def _dark(img: QImage, at, n) -> bool:
    line = min(_grey(img, at + n * d) for d in (-1.0, 0.0, 1.0))
    side = min(_grey(img, at + n * 4.0), _grey(img, at - n * 4.0))
    return line <= side - 18.0


def _light(canvas, img: QImage, at, n) -> bool:
    line = max(_grey(img, at + n * d) for d in (-1.0, 0.0, 1.0))
    bg = sum(_background(canvas, at[1])) / 3.0
    return line >= bg + 40.0


def _share(flags: list[bool]) -> float:
    return sum(flags) / max(len(flags), 1)


def _isolate(canvas) -> None:
    display_filter.toggle("world_axis")
    display_filter.toggle("horizon")
    draw._settle(draw._app())


def _count(img: QImage, rect, token: str, tolerance: int = 30) -> int:
    want = _token(token)
    x0, y0, x1, y1 = (int(v) for v in rect)
    total = 0
    for y in range(max(y0, 0), min(y1, img.height())):
        for x in range(max(x0, 0), min(x1, img.width())):
            if _close(_rgb(img, (x, y)), want, tolerance):
                total += 1
    return total


def test_defaults_are_todays_picture() -> None:
    canvas, _scene = _fresh()
    state = display_filter.load()
    assert state == display_filter.DisplayFilter() and state.shading == "shaded_lines"
    assert canvas.display == state
    assert all(getattr(state, key) for key, _label in display_filter.TOGGLES)
    base = _shot(canvas)
    display_filter.set_shading("shaded")
    assert _shot(canvas) != base
    display_filter.set_shading("shaded_lines")
    assert _shot(canvas) == base
    display_filter.set_shading("isoparms")
    assert _shot(canvas) == base
    display_filter.reset()
    assert _shot(canvas) == base
    obj = canvas.scene.active
    img = base
    samples = _edge_samples(canvas, obj, True)
    assert samples and _share([_dark(img, at, n) for _e, at, n in samples]) >= 0.8


def test_cube_in_every_display_mode() -> None:
    canvas, _scene = _fresh()
    obj = canvas.scene.active
    _isolate(canvas)
    results = {}
    for key, _label in display_filter.SHADINGS:
        display_filter.set_shading(key)
        img = _shot(canvas)
        front = _edge_samples(canvas, obj, True)
        back = _hidden_samples(canvas, obj)
        results[key] = (
            _face_stats(canvas, obj, img),
            _share([_dark(img, at, n) for _e, at, n in front]),
            _share([_light(canvas, img, at, n) for _e, at, n in front]),
            _share([_light(canvas, img, at, n) for _e, at, n in back]),
        )
    assert len(_edge_samples(canvas, obj, True)) > 0 and len(_hidden_samples(canvas, obj)) > 0
    for key in ("shaded_lines", "isoparms"):
        faces, dark, _light_front, _light_back = results[key]
        assert faces[0] == faces[2] and dark >= 0.8, (key, results[key])
    faces, dark, _light_front, _light_back = results["shaded"]
    assert faces[0] == faces[2] and dark <= 0.1, results["shaded"]
    faces, _dark_share, light_front, light_back = results["wireframe"]
    assert faces[0] == 0 and faces[1] == faces[2] and light_front >= 0.8 and light_back >= 0.8, results["wireframe"]
    faces, _dark_share, light_front, light_back = results["hidden_line"]
    assert faces[0] == 0 and faces[1] == faces[2], results["hidden_line"]
    assert light_front >= 0.8 and light_back <= 0.1, results["hidden_line"]


def test_subdivision_surface_in_every_display_mode() -> None:
    canvas, _scene, sub = _sub()
    mesh = sub.mesh
    iso = set(mesh.isoparms)
    assert 0 < len(iso) < len(mesh.edges) and iso <= set(mesh.edges)
    _isolate(canvas)
    front = [s for s in _edge_samples(canvas, sub, True)]
    on_iso = [s for s in front if s[0] in iso]
    off_iso = [s for s in front if s[0] not in iso]
    assert on_iso and off_iso
    display_filter.set_shading("shaded_lines")
    img = _shot(canvas)
    faces = _face_stats(canvas, sub, img)
    assert faces[0] >= 0.9 * faces[2]
    assert _share([_dark(img, at, n) for _e, at, n in front]) >= 0.8
    display_filter.set_shading("shaded")
    img = _shot(canvas)
    faces = _face_stats(canvas, sub, img)
    assert faces[0] >= 0.9 * faces[2]
    assert _share([_dark(img, at, n) for _e, at, n in front]) <= 0.1
    display_filter.set_shading("isoparms")
    img = _shot(canvas)
    faces = _face_stats(canvas, sub, img)
    assert faces[0] >= 0.9 * faces[2]
    assert _share([_dark(img, at, n) for _e, at, n in on_iso]) >= 0.8
    assert _share([_dark(img, at, n) for _e, at, n in off_iso]) <= 0.1
    display_filter.set_shading("wireframe")
    img = _shot(canvas)
    faces = _face_stats(canvas, sub, img)
    assert faces[0] == 0
    every = _edge_samples(canvas, sub, None)
    assert _share([_light(canvas, img, at, n) for _e, at, n in every]) >= 0.7
    display_filter.set_shading("hidden_line")
    img = _shot(canvas)
    faces = _face_stats(canvas, sub, img)
    assert faces[0] == 0 and faces[1] >= 0.9 * faces[2]
    assert _share([_light(canvas, img, at, n) for _e, at, n in front]) >= 0.7
    back = _hidden_samples(canvas, sub)
    assert len(back) >= 6 and _share([_light(canvas, img, at, n) for _e, at, n in back]) <= 0.1


def test_isoparms_on_an_editable_polygon_object_draws_every_edge() -> None:
    canvas, _scene = _fresh()
    display_filter.set_shading("shaded_lines")
    lines = _shot(canvas)
    display_filter.set_shading("isoparms")
    assert getattr(canvas.scene.active.mesh, "isoparms", None) is None
    assert _shot(canvas) == lines


def test_generators_name_their_isoparms() -> None:
    from quartz_studio.scene import Mesh

    assert getattr(Mesh.cube(), "isoparms", None) is None
    canvas, scene = _fresh()
    for kind in ("sphere", "cylinder", "cone", "torus", "tube", "capsule"):
        obj = scene.add_parametric(kind)
        mesh = obj.mesh
        iso = getattr(mesh, "isoparms", None)
        assert iso, kind
        assert 0 < len(iso) < len(mesh.edges), (kind, len(iso), len(mesh.edges))
        assert set(iso) <= set(mesh.edges), kind
        assert all(a < b for a, b in iso), kind
        scene.remove_object(obj)
    cube = scene.active
    sub = scene.add_parametric("subdivision_surface", adopt=cube)
    assert len(sub.mesh.isoparms) == 12 * 2 ** 2
    scene.set_param(sub, "subdivision_editor", 1)
    assert len(sub.mesh.isoparms) == 12 * 2


def test_ngon_lines_toggle_removes_the_accent_guides() -> None:
    from quartz_studio.scene import Mesh

    canvas, scene = _fresh()
    scene.remove_object(scene.objects[0])
    ring = [(100.0 * math.cos(2 * math.pi * i / 5), 100.0 * math.sin(2 * math.pi * i / 5), 0.0)
            for i in range(5)]
    obj = scene.add_object("Pentagon", Mesh(ring, [tuple(range(5))]))
    scene.set_active(obj)
    cam = canvas.camera
    cam.heading, cam.pitch, cam.distance = 0.0, 0.0, 500.0
    canvas.update()
    view = canvas._object_view(obj)
    pts = view.screen
    rect = (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())
    assert canvas.ngon_guides(obj.mesh, 0)
    on = _count(_shot(canvas), rect, theme.ACCENT)
    assert on > 0
    display_filter.toggle("ngon_lines")
    assert canvas.display.ngon_lines is False
    assert _count(_shot(canvas), rect, theme.ACCENT) == 0
    display_filter.toggle("ngon_lines")
    assert _count(_shot(canvas), rect, theme.ACCENT) == on


def test_horizon_toggle() -> None:
    canvas, _scene = _fresh()
    canvas.camera.pitch = 6.0
    canvas.update()
    cx, cy, f = canvas._view_params()
    _pos, fwd, _right, up = canvas.camera.basis()
    row = math.floor(cy + f * fwd[1] / up[1])
    assert canvas.inner_rect().top() + 60 < row < canvas.inner_rect().bottom()
    at = (30, row)
    img = _shot(canvas)
    assert _close(_rgb(img, at), _token(theme.HORIZON), 14)
    display_filter.toggle("horizon")
    img = _shot(canvas)
    assert _close(_rgb(img, at), _background(canvas, row), 3)
    assert _close(_rgb(img, (30, row - 3)), _background(canvas, row - 3), 3)


def test_world_axis_toggle() -> None:
    canvas, _scene = _fresh()
    img = _shot(canvas)
    area = (0, 90, canvas.width() - 140, canvas.height() - 50)
    colours = (theme.AXIS_X, theme.AXIS_Y, theme.AXIS_Z)
    assert sum(_count(img, area, c, 24) for c in colours) > 40
    display_filter.toggle("world_axis")
    img = _shot(canvas)
    assert sum(_count(img, area, c, 24) for c in colours) == 0


def test_axis_triad_toggle() -> None:
    canvas, _scene = _fresh()
    corner = (canvas.width() - 130, 0, canvas.width(), 130)
    colours = (theme.AXIS_X, theme.AXIS_Y, theme.AXIS_Z)
    img = _shot(canvas)
    assert sum(_count(img, corner, c, 24) for c in colours) > 20
    display_filter.toggle("axis_triad")
    img = _shot(canvas)
    assert sum(_count(img, corner, c, 24) for c in colours) == 0


def test_gizmo_toggle_hides_and_unpicks_the_gizmo() -> None:
    canvas, scene = _fresh()
    scene.set_tool("move")
    display_filter.toggle("world_axis")
    handles = canvas.gizmo_handles()
    (sx, sy), (ex, ey) = handles["x"]
    spot = np.array([sx, sy]) + (np.array([ex, ey]) - np.array([sx, sy])) * 0.6
    area = (spot[0] - 30, spot[1] - 30, spot[0] + 30, spot[1] + 30)
    assert canvas.gizmo_pick(spot) == "x"
    img = _shot(canvas)
    assert _count(img, area, theme.AXIS_X, 24) > 0
    display_filter.toggle("gizmo")
    assert canvas.display.gizmo is False
    assert canvas.gizmo_pick(spot) is None
    img = _shot(canvas)
    assert _count(img, area, theme.AXIS_X, 24) == 0
    scene.set_tool("rotate")
    assert canvas.gizmo_pick(spot) is None
    scene.set_tool("move")
    display_filter.toggle("gizmo")
    assert canvas.display.gizmo is True and canvas.gizmo_pick(spot) == "x"


def test_tool_hud_toggle() -> None:
    canvas, _scene = _fresh()
    hud = canvas.hud_rect(canvas.inner_rect())
    box = (hud.left() + 2, hud.top() + 2, hud.right() - 2, hud.bottom() - 2)

    def stray(img: QImage) -> int:
        total = 0
        for y in range(int(box[1]), int(box[3])):
            for x in range(int(box[0]), int(box[2])):
                if not _close(_rgb(img, (x, y)), _background(canvas, y), 3):
                    total += 1
        return total

    assert stray(_shot(canvas)) > 40
    display_filter.toggle("hud")
    assert canvas.display.hud is False
    assert stray(_shot(canvas)) == 0
    assert canvas.hud_rect(canvas.inner_rect()) == hud


def test_selection_outline_toggle() -> None:
    canvas, scene = _fresh()
    obj = scene.active
    xy = canvas.project_world(obj.world_points())
    rect = (xy[:, 0].min() - 8, xy[:, 1].min() - 8, xy[:, 0].max() + 8, xy[:, 1].max() + 8)
    assert scene.mode == "model" and scene.object_selected
    assert _count(_shot(canvas), rect, theme.SELECT_FRONT, 40) > 40
    display_filter.toggle("selection_outline")
    assert _count(_shot(canvas), rect, theme.SELECT_FRONT, 40) == 0
    display_filter.toggle("selection_outline")
    assert _count(_shot(canvas), rect, theme.SELECT_FRONT, 40) > 40


def test_points_toggle_keeps_picking() -> None:
    canvas, scene = _fresh("points")
    obj = scene.active
    view = canvas._object_view(obj)
    shown = [i for i in range(len(view.screen)) if view.visible_points[i] and view.in_front[i]
             and view.screen[i][0] > 0]
    assert shown
    img = _shot(canvas)
    fill = _token(theme.POINT_FILL)

    def squares(image: QImage) -> int:
        return sum(1 for i in shown if _close(_rgb(image, view.screen[i]), fill, 12))

    assert squares(img) >= 2
    display_filter.toggle("points")
    assert canvas.display.points is False
    assert squares(_shot(canvas)) == 0
    target = max(shown, key=lambda i: view.screen[i][0])
    kind, item = canvas.pick(view.screen[target])
    assert kind == "point" and item is not None


def test_prefs_state_menus_and_second_window() -> None:
    from quartz_studio.widgets.viewport import Viewport

    canvas, scene = _fresh()
    bar = canvas.parentWidget().menu_bar
    assert bar.menu_titles() == ["View", "Cameras", "Display", "Filter"]
    for key, label in display_filter.SHADINGS:
        assert bar.menu_action("Display", label) is bar.shading_actions[key]
    for key, label in display_filter.TOGGLES:
        assert bar.menu_action("Filter", label) is bar.filter_actions[key]
    assert bar.shading_actions["shaded_lines"].isChecked()
    assert all(a.isChecked() for a in bar.filter_actions.values())

    bar.filter_actions["horizon"].trigger()
    assert canvas.display.horizon is False
    assert prefs.get("display.horizon") is False
    assert bar.filter_actions["horizon"].isChecked() is False
    assert bar.filter_actions["horizon"].property("qs_check") is False

    bar.shading_actions["wireframe"].trigger()
    assert canvas.display.shading == "wireframe" and prefs.get("display.shading") == "wireframe"
    assert [k for k, a in bar.shading_actions.items() if a.isChecked()] == ["wireframe"]
    bar.shading_actions["isoparms"].trigger()
    assert [k for k, a in bar.shading_actions.items() if a.isChecked()] == ["isoparms"]
    assert bar.shading_actions["isoparms"].property("qs_check") is True
    assert bar.shading_actions["wireframe"].property("qs_check") is False

    display_filter.toggle("points")
    assert bar.filter_actions["points"].isChecked() is False
    assert canvas.display.points is False

    prefs.reload()
    again = display_filter.load()
    assert again.shading == "isoparms" and again.horizon is False and again.points is False
    assert os.path.exists(prefs.path())

    app = draw._app()
    second = Viewport()
    second.resize(*draw.VIEW_SIZE)
    second.show()
    draw._LIVE.append(second)
    draw._settle(app)
    assert second.canvas.display == again
    assert second.menu_bar.shading_actions["isoparms"].isChecked()
    assert second.menu_bar.filter_actions["horizon"].isChecked() is False
    display_filter.set_shading("hidden_line")
    draw._settle(app)
    assert second.canvas.display.shading == "hidden_line" and canvas.display.shading == "hidden_line"
    assert second.menu_bar.shading_actions["hidden_line"].isChecked()

    bar.menu_action("Filter", display_filter.RESET_LABEL).trigger()
    assert canvas.display == display_filter.DisplayFilter() == second.canvas.display
    assert all(a.isChecked() for a in bar.filter_actions.values())
    assert bar.shading_actions["shaded_lines"].isChecked()


def test_malformed_prefs_fall_back_per_field() -> None:
    prefs.reload()
    display_filter.reset()
    prefs.set("display.shading", "mystery")
    prefs.set("display.horizon", "yes")
    prefs.set("display.hud", False)
    state = display_filter.load()
    assert state.shading == "shaded_lines" and state.horizon is True and state.hud is False
    display_filter.reset()
    assert display_filter.load() == display_filter.DisplayFilter()
    display_filter.toggle("nothing")
    display_filter.set_shading("nothing")
    assert display_filter.load() == display_filter.DisplayFilter()


def test_every_item_is_a_controls_action_and_classic_binds_the_display_keys() -> None:
    from quartz_studio import controls
    from quartz_studio.controls import profiles

    actions = controls.actions()
    for key, label in display_filter.SHADINGS:
        assert actions["display." + key].label == label
    for key, label in display_filter.TOGGLES:
        assert actions["filter." + key].label == label
    prefs.reload()
    display_filter.reset()
    actions["display.wireframe"].run()
    assert display_filter.load().shading == "wireframe"
    actions["filter.gizmo"].run()
    assert display_filter.load().gizmo is False
    display_filter.reset()
    keys = profiles.CLASSIC["keys"]
    assert keys["display.shaded"] == ["N~A"] and keys["display.shaded_lines"] == ["N~B"]
    assert keys["display.wireframe"] == ["N~H"] and keys["display.isoparms"] == ["N~I"]
    assert keys["display.hidden_line"] == ["N~F"]
    assert all(not k.startswith("N") for aid, ks in keys.items() for k in ks if "~" not in k)
    standard = profiles.STANDARD["keys"]
    assert not any(a.startswith("display.") for a in standard)


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
    display_filter.reset()
    shutil.rmtree(_PREFS_DIR, ignore_errors=True)
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
