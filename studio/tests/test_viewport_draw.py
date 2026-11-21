from __future__ import annotations

import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio import theme
from quartz_studio.app import create_app
from quartz_studio.widgets.viewport import ViewportCanvas

VIEW_SIZE = (1000, 640)
LEFT = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier

_LIVE: list[QWidget] = []

CUBE_VIEWS = [
    (45.0, 19.75, 420.0, False), (0.0, 0.0, 420.0, False), (90.0, -60.0, 420.0, False),
    (135.0, 60.0, 420.0, False), (225.0, -30.0, 420.0, False), (315.0, 80.0, 420.0, False),
    (30.0, -89.0, 420.0, False), (200.0, 89.0, 420.0, False), (45.0, 19.75, 150.0, False),
    (120.0, -10.0, 110.0, False), (60.0, 35.0, 420.0, True), (250.0, -45.0, 60.0, False),
]
POCKET_VIEWS = [
    (45.0, 19.75, 420.0, False), (90.0, -60.0, 420.0, False), (315.0, 80.0, 420.0, False),
    (30.0, -89.0, 420.0, False), (60.0, 35.0, 420.0, True),
]


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(app: QApplication, passes: int = 4) -> None:
    for _ in range(passes):
        app.processEvents()


def _make(mode: str = "model"):
    app = _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.viewport import Viewport

    while _LIVE:
        old = _LIVE.pop()
        old.close()
        old.deleteLater()
    scene = reset_scene()
    view = Viewport()
    view.resize(*VIEW_SIZE)
    view.show()
    _settle(app)
    _LIVE.append(view)
    if mode != "model":
        scene.set_mode(mode)
    return view.canvas, scene


def _pocket(scene) -> None:
    scene.set_mode("polygons")
    scene.select_components({1})
    scene.extrude_selection()
    scene.move_selection([0.0, 0.0, -60.0])


def _mouse(widget: QWidget, kind: QEvent.Type, pos, button=NO_BUTTON, buttons=NO_BUTTON, mods=NO_MOD) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    glob = QPointF(widget.mapToGlobal(local))
    QApplication.sendEvent(widget, QMouseEvent(kind, local, glob, button, buttons, mods))


def _click(widget: QWidget, pos, mods=NO_MOD, button=LEFT) -> None:
    _mouse(widget, QEvent.Type.MouseButtonPress, pos, button, button, mods)
    _mouse(widget, QEvent.Type.MouseButtonRelease, pos, button, NO_BUTTON, mods)


def _key(widget: QWidget, key: Qt.Key, text: str = "") -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, NO_MOD, text))


def _image(canvas) -> QImage:
    return canvas.grab().toImage()


def _rgb(img: QImage, pos) -> tuple[int, int, int]:
    c = img.pixelColor(int(round(float(pos[0]))), int(round(float(pos[1]))))
    return c.red(), c.green(), c.blue()


def _near(rgb: tuple[int, int, int], token: str, tolerance: int = 40) -> bool:
    c = QColor(token)
    return all(abs(a - b) <= tolerance for a, b in zip(rgb, (c.red(), c.green(), c.blue())))


def _is_citrine(rgb: tuple[int, int, int]) -> bool:
    return _near(rgb, theme.SELECT_FRONT)


def _closer_to(rgb: tuple[int, int, int], token: str, other: str) -> bool:
    def gap(t: str) -> int:
        c = QColor(t)
        return sum((a - b) ** 2 for a, b in zip(rgb, (c.red(), c.green(), c.blue())))

    return gap(token) < gap(other)


def _on_screen(canvas, xy) -> bool:
    return bool(np.all(np.isfinite(xy))) and canvas.inner_rect().contains(QPointF(float(xy[0]), float(xy[1])))


def _warm(rgb: tuple[int, int, int]) -> bool:
    r, _g, b = rgb
    return r > 100 and r - b > 60


def _citrine_near(img: QImage, pos) -> bool:
    x, y = float(pos[0]), float(pos[1])
    return any(_warm(_rgb(img, (x + dx, y + dy))) for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def _grey(img: QImage, pos) -> int | None:
    c = img.pixelColor(int(pos[0]), int(pos[1]))
    if max(abs(c.red() - c.green()), abs(c.green() - c.blue())) > 6:
        return None
    return c.red()


def _grid(canvas, count: int) -> list[tuple[float, float]]:
    film = canvas.film_rect()
    rows = max(1, int(round(count * film.height() / film.width())))
    return [(film.left() + (gx + 0.5) * film.width() / count, film.top() + (gy + 0.5) * film.height() / rows)
            for gx in range(count) for gy in range(rows)]


def _tris(obj) -> tuple[np.ndarray, np.ndarray]:
    tri, owner = [], []
    world = obj.world_points()
    for k, poly in enumerate(obj.mesh.polygons):
        q = world[list(poly)]
        for i in range(1, len(q) - 1):
            tri.append((q[0], q[i], q[i + 1]))
            owner.append(k)
    return np.array(tri), np.array(owner)


def _hits(o: np.ndarray, d: np.ndarray, T: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    A, B, C = T[:, 0], T[:, 1], T[:, 2]
    e1, e2 = B - A, C - A
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - A
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    good = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)
    return np.nonzero(good)[0], t


def _eye_ray(canvas, point: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    pos, fwd, _right, _up = canvas.camera.basis()
    if canvas.camera.ortho:
        depth = float((point - pos) @ fwd)
        return point - fwd * depth, fwd, depth
    vec = point - pos
    length = float(np.linalg.norm(vec))
    return pos, vec / length, length


def _hidden(canvas, point: np.ndarray, T: np.ndarray) -> bool:
    o, d, length = _eye_ray(canvas, point)
    idx, t = _hits(o, d, T)
    return bool(len(idx)) and float(np.min(t[idx])) < length - (1e-6 * length + 1e-9)


def _expected_grey(view, light: np.ndarray) -> list[int]:
    out = []
    for k in range(len(view.normals)):
        n = view.normals[k]
        lam = float(n @ light) if view.front[k] else float(-(n @ light)) * 0.55
        out.append(ViewportCanvas._shade(lam).red())
    return out


def _back_over_front(canvas, obj, img: QImage, count: int = 60) -> int:
    view = canvas._object_view(obj)
    exp = _expected_grey(view, canvas._light_dir())
    T, owner = _tris(obj)
    bad = 0
    for x, y in _grid(canvas, count):
        g = _grey(img, (x, y))
        if g is None:
            continue
        o, d = canvas._ray(QPointF(x, y))
        idx, t = _hits(o, d, T)
        if not len(idx):
            continue
        order = idx[np.argsort(t[idx])]
        near = int(owner[order[0]])
        if abs(g - exp[near]) <= 3:
            continue
        t0 = float(t[order[0]])
        behind = [int(owner[j]) for j in order if float(t[j]) > t0 + 1.0]
        if view.front[near] and any(abs(g - exp[k]) <= 3 and not view.front[k] for k in behind):
            bad += 1
    return bad


def _contour_samples(canvas, obj, img: QImage, samples: int = 12) -> tuple[int, int, int, int]:
    view = canvas._object_view(obj)
    world = obj.world_points()
    T, _owner = _tris(obj)
    hidden = hidden_citrine = visible = visible_citrine = 0
    for edge in canvas._contour_edges(view):
        a, b = world[edge[0]], world[edge[1]]
        for s in np.linspace(0.05, 0.95, samples):
            p3 = a + (b - a) * s
            xy = canvas.project_world([p3])[0]
            if not _on_screen(canvas, xy):
                continue
            citrine = _citrine_near(img, xy)
            if _hidden(canvas, p3, T):
                hidden += 1
                hidden_citrine += int(citrine)
            else:
                visible += 1
                visible_citrine += int(citrine)
    return hidden, hidden_citrine, visible, visible_citrine


def test_pocket_contour_hidden_samples_are_not_drawn() -> None:
    canvas, scene = _make()
    _pocket(scene)
    scene.set_mode("model")
    obj = scene.active
    assert obj is not None
    scene.select_object(True)
    zero_views = 0
    for h, pit, dist, ortho in POCKET_VIEWS:
        cam = canvas.camera
        cam.heading, cam.pitch, cam.distance, cam.ortho = h, pit, dist, ortho
        canvas.update()
        img = _image(canvas)
        hidden, hidden_citrine, visible, visible_citrine = _contour_samples(canvas, obj, img)
        assert hidden > 0, (h, pit, dist, ortho)
        assert visible_citrine >= 0.8 * visible, (visible_citrine, visible)
        assert hidden_citrine == 0, (h, pit, dist, ortho, hidden_citrine, hidden)
        zero_views += 1
    assert zero_views >= 4


def test_pocket_has_no_back_face_over_front() -> None:
    canvas, scene = _make()
    _pocket(scene)
    scene.set_mode("model")
    obj = scene.active
    bad_views = []
    for h, pit, dist, ortho in POCKET_VIEWS[:4]:
        cam = canvas.camera
        cam.heading, cam.pitch, cam.distance, cam.ortho = h, pit, dist, ortho
        canvas.update()
        bad = _back_over_front(canvas, obj, _image(canvas))
        if bad:
            bad_views.append(((h, pit, dist, ortho), bad))
    assert not bad_views, bad_views


def test_default_cube_matches_shading_formula() -> None:
    canvas, scene = _make()
    scene.set_tool("select")
    obj = scene.active
    T, owner = _tris(obj)
    bad = total = 0
    for h, pit, dist, ortho in CUBE_VIEWS:
        cam = canvas.camera
        cam.heading, cam.pitch, cam.distance, cam.ortho = h, pit, dist, ortho
        canvas.update()
        img = _image(canvas)
        exp = _expected_grey(canvas._object_view(obj), canvas._light_dir())
        for x, y in _grid(canvas, 40):
            g = _grey(img, (x, y))
            if g is None:
                continue
            o, d = canvas._ray(QPointF(x, y))
            idx, t = _hits(o, d, T)
            if not len(idx):
                continue
            near = int(owner[idx[int(np.argmin(t[idx]))]])
            total += 1
            if abs(g - exp[near]) > 3:
                bad += 1
    assert total > 0 and bad <= 0.03 * total, (bad, total)


def test_camera_inside_cube_shows_walls() -> None:
    canvas, scene = _make()
    cam = canvas.camera
    cam.heading, cam.pitch, cam.distance = 250.0, -10.0, 60.0
    canvas.update()
    img = _image(canvas)
    walls = total = 0
    for x, y in _grid(canvas, 16):
        g = _grey(img, (x, y))
        if g is None:
            continue
        total += 1
        walls += int(g >= 60)
    assert total > 0 and walls >= 0.9 * total, (walls, total)


def test_open_cube_shows_interior() -> None:
    from quartz_studio.scene import Mesh

    canvas, scene = _make()
    obj = scene.active
    obj.mesh = Mesh(obj.mesh.points.copy(), obj.mesh.polygons[1:])
    cam = canvas.camera
    cam.heading, cam.pitch, cam.distance = 0.0, 0.0, 420.0
    canvas.update()
    img = _image(canvas)
    view = canvas._object_view(obj)
    exp = _expected_grey(view, canvas._light_dir())
    far = [k for k in range(len(view.normals)) if view.normals[k] @ np.array([0.0, 0.0, 1.0]) > 0.99]
    assert far, view.normals
    centre = canvas.project_world([[0.0, 0.0, 0.0]])[0]
    g = _grey(img, (centre[0] + 15.0, centre[1] + 15.0))
    assert g is not None and abs(g - exp[far[0]]) <= 3, (g, exp[far[0]])


def test_hud_follows_modelling_tool() -> None:
    from quartz_studio import scene as scene_module
    from quartz_studio.modeling import install as modeling_install
    from quartz_studio.widgets.viewport import HUD_TEXTS, TOOL_NAMES

    modeling_install.prepare()
    canvas, scene = _make()
    scene.set_tool("select")
    assert canvas.hud_text == "Brush Selection"
    tool = "extrude"
    assert tool in scene_module.TOOLS, scene_module.TOOLS
    scene.set_tool(tool)
    assert canvas.hud_text == (HUD_TEXTS.get(tool) or TOOL_NAMES.get(tool, tool)), canvas.hud_text
    assert canvas.hud_text != "Move" and canvas._hud_tool == tool
    scene.set_tool("other")
    assert canvas.hud_text == (HUD_TEXTS.get(tool) or TOOL_NAMES.get(tool, tool)), canvas.hud_text
    scene.set_tool("move")
    assert canvas.hud_text == "Move"


def test_cancelled_drag_emits_changed_after_history_update() -> None:
    from PySide6.QtTest import QTest

    canvas, scene = _make()
    start = _arrow_start(canvas, "x")
    _real_drag(canvas, start, start + (40.0, 0.0), release=False)
    seen: list[tuple[bool, bool]] = []
    scene.changed.connect(lambda: seen.append((scene.can_undo(), scene.can_redo())))
    _key(canvas, Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas, LEFT, NO_MOD, QPoint(int(start[0] + 40), int(start[1])))
    assert canvas._drag is None
    assert seen, "no changed signal after cancelled drag"
    assert seen[-1] == (scene.can_undo(), scene.can_redo()), (seen[-1], scene.can_undo(), scene.can_redo())


def test_hidden_selected_points_are_not_drawn_on_top() -> None:
    canvas, scene = _make("points")
    _pocket(scene)
    scene.set_mode("points")
    obj = scene.active
    T, _owner = _tris(obj)
    cam = canvas.camera
    cam.heading, cam.pitch, cam.distance, cam.ortho = 90.0, -60.0, 420.0, False
    canvas.update()
    world = obj.world_points()
    hidden = visible = None
    for i in range(len(world)):
        xy = canvas.project_world([world[i]])[0]
        if not _on_screen(canvas, xy):
            continue
        if _hidden(canvas, world[i], T):
            hidden = (i, xy) if hidden is None else hidden
        elif visible is None:
            visible = (i, xy)
    assert hidden is not None and visible is not None
    scene.select_components({hidden[0]})
    assert not _is_citrine(_rgb(_image(canvas), hidden[1]))
    _click(canvas, visible[1])
    assert scene.selected_points == {visible[0]}, scene.selected_points
    assert _is_citrine(_rgb(_image(canvas), visible[1]))


def test_selected_polygon_fill_is_not_drawn_over_front_faces() -> None:
    canvas, scene = _make()
    _pocket(scene)
    scene.set_mode("polygons")
    scene.set_tool("select")
    obj = scene.active
    sel = set(scene.selected_polygons)
    assert sel, "no selected polygon"
    T, owner = _tris(obj)
    bad_views = []
    for h, pit in ((180.0, 60.0), (90.0, -60.0)):
        cam = canvas.camera
        cam.heading, cam.pitch, cam.distance, cam.ortho = h, pit, 420.0, False
        canvas.update()
        img = _image(canvas)
        wrong = 0
        for x, y in _grid(canvas, 80):
            if not _warm(_rgb(img, (x, y))):
                continue
            o, d = canvas._ray(QPointF(x, y))
            idx, t = _hits(o, d, T)
            if not len(idx):
                continue
            sel_hits = [j for j in idx if int(owner[j]) in sel]
            if not sel_hits:
                continue
            t_sel = float(min(t[j] for j in sel_hits))
            near = idx[int(np.argmin(t[idx]))]
            if int(owner[near]) not in sel and float(t[near]) < t_sel - 1.0:
                wrong += 1
        if wrong:
            bad_views.append(((h, pit), wrong))
    assert not bad_views, bad_views


def test_selected_polygon_seen_from_behind_is_amethyst() -> None:
    from quartz_studio.scene import Mesh

    canvas, scene = _make("polygons")
    obj = scene.active
    obj.mesh = Mesh(obj.mesh.points.copy(), obj.mesh.polygons[1:])
    cam = canvas.camera
    cam.heading, cam.pitch, cam.distance = 0.0, 0.0, 420.0
    view = canvas._object_view(obj)
    far = [k for k in range(len(view.normals)) if view.normals[k] @ np.array([0.0, 0.0, 1.0]) > 0.99]
    assert far and not view.front[far[0]], (far, view.front)
    scene.select_components({far[0]})
    canvas.update()
    img = _image(canvas)
    centre = canvas.project_world([[0.0, 0.0, 0.0]])[0]
    rgb = _rgb(img, (centre[0] + 15.0, centre[1] + 15.0))
    r, _g, b = rgb
    assert b - r > 30, rgb
    assert _closer_to(rgb, theme.SELECT_BACK, theme.SELECT_FRONT), rgb


def test_selected_polygon_seen_from_the_front_stays_citrine() -> None:
    canvas, scene = _make("polygons")
    obj = scene.active
    view = canvas._object_view(obj)
    front = [k for k in range(len(view.front)) if view.front[k]]
    assert front
    scene.select_components({front[0]})
    canvas.update()
    img = _image(canvas)
    centre = canvas.project_world([obj.to_world(obj.mesh.points[list(obj.mesh.polygons[front[0]])]).mean(axis=0)])[0]
    rgb = _rgb(img, centre)
    r, _g, b = rgb
    assert r - b > 30, rgb
    assert _closer_to(rgb, theme.SELECT_FRONT, theme.SELECT_BACK), rgb


def test_canvas_is_a_rounded_card_without_a_bright_border() -> None:
    canvas, _scene = _make()
    img = _image(canvas)
    w, h = canvas.width(), canvas.height()
    assert _rgb(img, (0, 0)) != _rgb(img, (w // 2, 0)), "the corner is cut by the card radius"
    assert not _near(_rgb(img, (0, 0)), theme.VIEWPORT_TOP, 3)
    ceiling = max(QColor(theme.VIEWPORT_TOP).value(), QColor(theme.VIEWPORT_BOTTOM).value())
    for pos in ((w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)):
        c = img.pixelColor(*pos)
        assert c.alpha() == 255 and c.value() <= ceiling + 4, (pos, c.getRgb())


def test_background_is_the_vertical_ink_gradient_without_bands() -> None:
    canvas, _scene = _make()
    img = _image(canvas)
    w, h = canvas.width(), canvas.height()
    top, bottom = QColor(theme.VIEWPORT_TOP), QColor(theme.VIEWPORT_BOTTOM)
    assert _near(_rgb(img, (w // 2, 2)), theme.VIEWPORT_TOP, 3)
    assert _near(_rgb(img, (w // 2, h - 3)), theme.VIEWPORT_BOTTOM, 3)
    assert top.value() > bottom.value()
    column = [_rgb(img, (w // 2 + 200, y))[0] for y in range(4, h - 4)]
    assert all(a >= b for a, b in zip(column, column[1:])), "background must fade monotonically"
    assert max(abs(a - b) for a, b in zip(column, column[1:])) <= 1, "no letterbox steps"


def test_horizon_is_a_one_pixel_hairline() -> None:
    canvas, _scene = _make()
    canvas.camera.pitch = 6.0
    canvas.update()
    _pos, fwd, _right, up = canvas.camera.basis()
    cx, cy, f = canvas._view_params()
    row = int(math.floor(cy + f * fwd[1] / up[1]))
    img = _image(canvas)
    x = int(canvas.width() * 0.2)
    assert _near(_rgb(img, (x, row)), theme.HORIZON, 2), _rgb(img, (x, row))
    for off in (-2, 2):
        assert not _near(_rgb(img, (x, row + off)), theme.HORIZON, 8), (off, _rgb(img, (x, row + off)))


def test_header_is_overlaid_inside_the_canvas() -> None:
    canvas, _scene = _make()
    bar = canvas.parentWidget().menu_bar
    assert bar.parentWidget() is canvas
    assert bar.geometry().top() == 0 and bar.width() == canvas.width()
    free = theme.DOCK_BOTTOM + theme.DOCK_H + theme.SPACE_3
    assert bar.geometry().bottom() < canvas.height() - free
    assert bar.menu_titles() == ["View", "Cameras", "Display", "Filter"]
    for button in bar.menu_buttons:
        assert button.height() == theme.GHOST_BUTTON_H and button.x() >= theme.SPACE_2
        assert canvas.childAt(button.geometry().center()) is button
    assert len(bar.nav_buttons) == 3
    for button in bar.nav_buttons:
        assert button.width() == button.height() == theme.NAV_BUTTON
        assert canvas.childAt(button.geometry().center()) is button
    assert bar.nav_buttons[-1].geometry().right() + 1 == canvas.width() - theme.SPACE_2
    assert canvas.childAt(QPoint(canvas.width() // 2, theme.SPACE_2 + 4)) is None


def test_viewport_menus_are_studio_menus_with_synced_checks() -> None:
    from quartz_studio.widgets.menu_bar import StudioMenu

    canvas, _scene = _make()
    bar = canvas.parentWidget().menu_bar
    for menu in bar.menus.values():
        assert isinstance(menu, StudioMenu)
    assert bar.view_actions["Perspective"].property("qs_check") is True
    bar.view_actions["Left"].trigger()
    assert bar.view_actions["Left"].property("qs_check") is True
    assert bar.view_actions["Perspective"].property("qs_check") is False
    bar.nav_pivot_actions["Center"].trigger()
    assert bar.nav_pivot_actions["Center"].property("qs_check") is True
    assert bar.nav_pivot_actions["Cursor"].property("qs_check") is False


def test_hud_is_a_pill_and_the_bottom_centre_is_free() -> None:
    canvas, scene = _make()
    scene.set_tool("move")
    img = _image(canvas)
    w, h = canvas.width(), canvas.height()
    mid = h - theme.SPACE_3 - theme.HUD_H // 2
    edge = [_rgb(img, (theme.SPACE_3 + dx, mid + dy)) for dx in (0, 1) for dy in (-1, 0, 1)]
    assert any(_near(c, theme.HAIRLINE, 14) for c in edge), edge
    assert not any(_near(c, theme.HAIRLINE, 14) for c in
                   [_rgb(img, (theme.SPACE_3 + 1, mid + theme.HUD_H // 2 - 1))]), "corners are rounded"
    top = h - (theme.DOCK_BOTTOM + theme.DOCK_H + theme.SPACE_3)
    for y in range(top, h - 2):
        row = {_rgb(img, (x, y)) for x in range(w // 2 - 200, w // 2 + 200)}
        assert len(row) == 1, (y, sorted(row)[:3])


def _real_drag(widget: QWidget, start, end, steps: int = 10, release: bool = True) -> None:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    start, end = np.asarray(start, float), np.asarray(end, float)
    p0 = QPoint(int(round(start[0])), int(round(start[1])))
    QTest.mousePress(widget, LEFT, NO_MOD, p0)
    for k in range(1, steps + 1):
        q = start + (end - start) * k / steps
        QTest.mouseMove(widget, QPoint(int(round(q[0])), int(round(q[1]))))
    assert QGuiApplication.mouseButtons() == LEFT
    if release:
        QTest.mouseRelease(widget, LEFT, NO_MOD, QPoint(int(round(end[0])), int(round(end[1]))))


def _arrow_start(canvas, axis: str) -> np.ndarray:
    (sx, sy), (ex, ey) = canvas.gizmo_handles()[axis]
    return np.array([sx, sy]) + (np.array([ex, ey]) - np.array([sx, sy])) * 0.6


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
