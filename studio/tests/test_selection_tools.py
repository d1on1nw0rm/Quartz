from __future__ import annotations

import math
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

PREFS_DIR = tempfile.mkdtemp(prefix="quartz-prefs-selection-")
os.environ["QUARTZ_PREFS_DIR"] = PREFS_DIR

import quartz_studio
import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio import icons
from quartz_studio.app import create_app

VIEW_SIZE = (1000, 640)
LEFT = Qt.MouseButton.LeftButton
MIDDLE = Qt.MouseButton.MiddleButton
RIGHT = Qt.MouseButton.RightButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier

_LIVE: list[QWidget] = []
_STATE: dict = {}


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(app: QApplication | None = None, passes: int = 4) -> None:
    app = app or QApplication.instance()
    for _ in range(passes):
        app.processEvents()


def _isolate() -> None:
    from quartz_studio import prefs

    os.environ["QUARTZ_PREFS_DIR"] = PREFS_DIR
    for name in ("prefs.json", "prefs.json.tmp", "prefs.corrupt.json"):
        try:
            os.remove(os.path.join(PREFS_DIR, name))
        except OSError:
            pass
    prefs.reload()
    try:
        from quartz_studio import controls
    except ImportError:
        return
    controls.STORE_PATH = os.path.join(PREFS_DIR, "controls.json")


def _close_popups() -> None:
    for _ in range(4):
        popup = QApplication.activePopupWidget()
        if popup is None:
            break
        popup.close()
        _settle()


def _make(mode: str = "model", mesh=None, tool: str | None = None):
    app = _app()
    _isolate()
    from quartz_studio.modeling import select_interaction
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.viewport import Viewport

    _close_popups()
    while _LIVE:
        old = _LIVE.pop()
        old.close()
        old.deleteLater()
    _settle(app)
    scene = reset_scene()
    if mesh is not None:
        scene.active.mesh = mesh
    view = Viewport()
    view.resize(*VIEW_SIZE)
    view.show()
    _settle(app)
    _LIVE.append(view)
    canvas = view.canvas
    filt = select_interaction.SelectionToolFilter(canvas)
    if mode != "model":
        scene.set_mode(mode)
    if tool is not None:
        scene.set_tool(tool)
    scene._undo.clear()
    scene._redo.clear()
    _settle(app)
    return canvas, scene, filt


def _mouse(widget: QWidget, kind: QEvent.Type, pos, button=NO_BUTTON, buttons=NO_BUTTON, mods=NO_MOD) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    glob = QPointF(widget.mapToGlobal(local))
    QApplication.sendEvent(widget, QMouseEvent(kind, local, glob, button, buttons, mods))


def _click(widget: QWidget, pos, mods=NO_MOD, button=LEFT) -> None:
    _mouse(widget, QEvent.Type.MouseButtonPress, pos, button, button, mods)
    _mouse(widget, QEvent.Type.MouseButtonRelease, pos, button, NO_BUTTON, mods)


def _drag(widget: QWidget, start, end, mods=NO_MOD, button=LEFT, steps: int = 10) -> None:
    start, end = np.asarray(start, float), np.asarray(end, float)
    _mouse(widget, QEvent.Type.MouseButtonPress, start, button, button, mods)
    for k in range(1, steps + 1):
        _mouse(widget, QEvent.Type.MouseMove, start + (end - start) * k / steps, NO_BUTTON, button, mods)
    _mouse(widget, QEvent.Type.MouseButtonRelease, end, button, NO_BUTTON, mods)


def _hover(widget: QWidget, pos, mods=NO_MOD) -> None:
    _mouse(widget, QEvent.Type.MouseMove, pos, NO_BUTTON, NO_BUTTON, mods)


def _wheel(widget: QWidget, pos, notches: float, mods=NO_MOD) -> None:
    local = QPointF(float(pos[0]), float(pos[1]))
    ev = QWheelEvent(local, QPointF(widget.mapToGlobal(local)), QPoint(0, 0), QPoint(0, int(120 * notches)),
                     NO_BUTTON, mods, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def _cube(segments: int = 4):
    from quartz_studio.modeling import primitives

    return primitives.cube((200.0, 200.0, 200.0), (segments, segments, segments))


def _view(canvas):
    return canvas._object_view(canvas.scene.active)


def _inside(canvas, xy) -> bool:
    return 4 <= xy[0] <= canvas.width() - 4 and 4 <= xy[1] <= canvas.height() - 4


def _visible_points(canvas, view) -> np.ndarray:
    idx = np.nonzero(view.in_front & view.visible_points)[0]
    clear = canvas._sight_clear(view.world[idx])
    return idx[np.asarray(clear, bool)]


def _seg_dist(p, a, b) -> float:
    p, a, b = (np.asarray(v, float) for v in (p, a, b))
    d = b - a
    t = 0.0 if float(d @ d) <= 1e-12 else float(np.clip((p - a) @ d / (d @ d), 0.0, 1.0))
    return float(np.linalg.norm(p - a - t * d))


def _front_faces(canvas, view) -> list[int]:
    out = []
    for k in np.nonzero(view.front)[0]:
        poly, _depth = canvas._poly_screen(view, int(k))
        if poly is None:
            continue
        pts = np.array([(p.x(), p.y()) for p in poly])
        if all(_inside(canvas, q) for q in pts):
            out.append(int(k))
    return out


def _face_centre(canvas, view, k: int) -> np.ndarray:
    poly, _depth = canvas._poly_screen(view, k)
    return np.array([(p.x(), p.y()) for p in poly]).mean(axis=0)


def _edge_mid(canvas, view, e) -> np.ndarray:
    line = canvas._edge_screen(view, e)
    return np.array([(line.x1() + line.x2()) / 2.0, (line.y1() + line.y2()) / 2.0])


def _pickable_edges(canvas, view, wanted=None) -> list:
    out = []
    for e in view.visible_edges:
        if wanted is not None and not wanted(e):
            continue
        line = canvas._edge_screen(view, e)
        if line is None or line.length() < 16:
            continue
        mid = _edge_mid(canvas, view, e)
        if not _inside(canvas, mid):
            continue
        got = canvas._pick_edge(view, float(mid[0]), float(mid[1]))
        if got is not None and tuple(sorted(got)) == tuple(sorted(e)):
            out.append(tuple(sorted(e)))
    return out


def _pixels(name: str, size: int = 48) -> np.ndarray:
    img = icons.pixmap(name, size, None).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    arr = np.frombuffer(bytes(img.constBits()), dtype=np.uint8).reshape(img.height(), img.width(), 4)
    return arr.astype(np.int16)


def test_tools_and_icons_are_registered() -> None:
    _app()
    from quartz_studio import scene as scene_module
    from quartz_studio.modeling import select_tools

    for tool_id in ("select_loop", "select_ring", "select_pattern", "select_fill", "select_phong"):
        assert tool_id in scene_module.TOOLS, tool_id
    for tool in select_tools.TOOLS:
        assert icons.has(tool.icon), tool.icon
        arr = _pixels(tool.icon, 48)
        blue, green, red, alpha = (arr[:, :, k] for k in range(4))
        solid = alpha > 200
        assert int(solid.sum()) >= 40, tool.icon
        citrine = (abs(red - 255) < 30) & (abs(green - 181) < 30) & (abs(blue - 61) < 40) & solid
        neutral = (abs(red - 207) < 25) & (abs(green - 213) < 25) & (abs(blue - 225) < 25) & solid
        assert int(citrine.sum()) >= 8, f"{tool.icon}: no tool tint"
        assert int(neutral.sum()) >= 20, f"{tool.icon}: no neutral stroke"
        other = solid & ~citrine & ~neutral
        assert int(other.sum()) < int(solid.sum()) * 0.5, f"{tool.icon}: stray colours"


def test_brush_points_click_drag_ctrl_and_shift() -> None:
    canvas, scene, filt = _make("points", _cube(4), "select")
    view = _view(canvas)
    vis = [int(i) for i in _visible_points(canvas, view) if _inside(canvas, view.screen[i])]
    assert len(vis) >= 8
    target = vis[0]
    c = view.screen[target]
    _click(canvas, c)
    expected = {i for i in vis if math.hypot(*(view.screen[i] - c)) <= 10}
    assert scene.selected_points == expected == {target}, (scene.selected_points, expected)

    other = max(vis, key=lambda i: math.hypot(*(view.screen[i] - c)))
    _click(canvas, view.screen[other], SHIFT)
    assert scene.selected_points == {target, other}

    a = view.screen[vis[0]]
    b = min((view.screen[i] for i in vis if math.hypot(*(view.screen[i] - a)) > 60),
            key=lambda q: math.hypot(*(q - a)))
    end = b + (b - a) / max(1e-9, math.hypot(*(b - a))) * 20
    _drag(canvas, a, end, steps=24)
    sel = set(scene.selected_points)
    near = {i for i in vis if _seg_dist(view.screen[i], a, b) <= 8}
    assert near <= sel, (near - sel)
    for i in sel:
        assert _seg_dist(view.screen[i], a, end) <= 10.5, i
    assert len(sel) >= 2

    scene.select_components(vis)
    _drag(canvas, a, end, CTRL, steps=24)
    assert not (near & scene.selected_points)
    assert set(vis) - scene.selected_points <= {i for i in vis if _seg_dist(view.screen[i], a, end) <= 10.5}
    assert set(vis) - sel <= scene.selected_points


def test_brush_visible_only_never_selects_back_points() -> None:
    from quartz_studio.modeling import select_tools

    canvas, scene, filt = _make("points", None, "select")
    view = _view(canvas)
    hidden = {i for i in range(len(view.world)) if view.in_front[i]} - set(int(i) for i in _visible_points(canvas, view))
    assert hidden, "the default view should hide a cube corner"
    centre = view.screen[view.in_front].mean(axis=0)
    select_tools.set_option("select", "radius", 512)
    _click(canvas, centre)
    assert scene.selected_points and not (scene.selected_points & hidden)
    select_tools.set_option("select", "visible_only", False)
    _click(canvas, centre)
    assert hidden <= scene.selected_points
    select_tools.reset_options("select")


def test_brush_polygons_centroid_and_tolerant() -> None:
    from quartz_studio.modeling import select_tools

    canvas, scene, filt = _make("polygons", _cube(4), "select")
    view = _view(canvas)
    mesh = scene.active.mesh
    faces = _front_faces(canvas, view)
    assert faces
    k = faces[0]
    c = _face_centre(canvas, view, k)
    _click(canvas, c)
    expected = {f for f in faces if math.hypot(*(_face_centre(canvas, view, f) - c)) <= 10}
    assert scene.selected_polygons == expected == {k}

    counts: dict[int, list[int]] = {}
    for f in faces:
        for v in mesh.polygons[f]:
            counts.setdefault(int(v), []).append(f)
    corner = next(v for v, fs in counts.items() if len(fs) == 4 and _inside(canvas, view.screen[v]))
    touching = set(counts[corner])
    _click(canvas, view.screen[corner])
    assert scene.selected_polygons == set(), scene.selected_polygons
    select_tools.set_option("select", "tolerant", True)
    _click(canvas, view.screen[corner])
    assert scene.selected_polygons == touching, (scene.selected_polygons, touching)
    select_tools.reset_options("select")


def test_brush_model_mode_selects_parametric_objects() -> None:
    from quartz_studio.widgets import menu_bar

    canvas, scene, filt = _make("model", None, "select")
    scene.remove_object(scene.objects[0])
    sphere = menu_bar.create_object("sphere", NO_MOD)
    scene.set_tool("select")
    scene.select_object(False)
    scene.set_active(None)
    _settle()
    assert not scene.is_editable(sphere)
    view = canvas._object_view(sphere)
    centre = view.screen[view.in_front].mean(axis=0)
    _drag(canvas, centre + (-30, 0), centre + (30, 0), steps=6)
    assert scene.active is sphere and scene.object_selected
    _click(canvas, (12, 12))
    assert not scene.object_selected


def test_one_stroke_is_one_undo_step() -> None:
    canvas, scene, filt = _make("points", _cube(4), "select")
    view = _view(canvas)
    vis = [int(i) for i in _visible_points(canvas, view) if _inside(canvas, view.screen[i])]
    scene.select_components([vis[-1]])
    before = set(scene.selected_points)
    steps = len(scene._undo)
    a = view.screen[vis[0]]
    b = view.screen[vis[len(vis) // 2]]
    _drag(canvas, a, b, steps=20)
    assert scene.selected_points != before
    assert len(scene._undo) == steps + 1
    assert scene.undo()
    assert scene.selected_points == before
    steps = len(scene._undo)
    _click(canvas, view.screen[vis[-1]], SHIFT)
    assert len(scene._undo) == steps
    scene.select_components([])
    steps = len(scene._undo)
    _click(canvas, (12, 12))
    assert len(scene._undo) == steps
    assert scene._group_depth == 0


def test_shift_wheel_sizes_the_brush() -> None:
    from quartz_studio import prefs

    canvas, scene, filt = _make("points", None, "select")
    pos = (canvas.width() / 2, canvas.height() / 2)
    distance = canvas.camera.distance
    _wheel(canvas, pos, 1, SHIFT)
    assert prefs.get("selection.options")["select"]["radius"] == 12
    assert canvas.camera.distance == distance
    assert filt.overlay.circle is not None and filt.overlay.circle[1] == 12
    for _ in range(12):
        _wheel(canvas, pos, -1, SHIFT)
    assert prefs.get("selection.options")["select"]["radius"] == 2
    assert canvas.camera.distance == distance
    _wheel(canvas, pos, 1)
    assert canvas.camera.distance != distance
    canvas.setFocus()
    _settle()
    assert canvas.hasFocus()
    from PySide6.QtGui import QKeyEvent

    QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketRight, NO_MOD, "]"))
    QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketRight, NO_MOD, "]"))
    assert prefs.get("selection.options")["select"]["radius"] == 6
    QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketLeft, NO_MOD, "["))
    assert prefs.get("selection.options")["select"]["radius"] == 4
    assert filt.overlay.circle is not None and filt.overlay.circle[1] == 4


def test_loop_hover_preview_and_click() -> None:
    from quartz_studio.modeling import meshkit, select_tools

    canvas, scene, filt = _make("edges", _cube(4), "select_loop")
    mesh = scene.active.mesh
    view = _view(canvas)
    edges = _pickable_edges(canvas, view)
    assert edges
    e = edges[len(edges) // 2]
    mid = _edge_mid(canvas, view, e)
    _hover(canvas, mid)
    loop = set(meshkit.edge_loop(mesh, e))
    assert filt.overlay.preview_items == loop and filt.overlay.preview_kind == "edges"
    _click(canvas, mid)
    assert scene.selected_edges == loop

    scene.set_mode("polygons")
    view = _view(canvas)
    k = _front_faces(canvas, view)[0]
    poly = list(mesh.polygons[k])
    side = meshkit.edge_key(poly[0], poly[1])
    pos = 0.8 * _edge_mid(canvas, view, side) + 0.2 * _face_centre(canvas, view, k)
    _hover(canvas, pos)
    strip = select_tools.loop_elements(mesh, "polygons", side)
    assert strip and k in strip
    assert filt.overlay.preview_items == strip
    _click(canvas, pos)
    assert scene.selected_polygons == strip

    scene.set_mode("points")
    view = _view(canvas)
    _hover(canvas, mid)
    _click(canvas, mid)
    assert scene.selected_points == {i for edge in loop for i in edge}


def test_ring_edges_and_polygons() -> None:
    from quartz_studio.modeling import meshkit, select_tools

    canvas, scene, filt = _make("edges", _cube(4), "select_ring")
    mesh = scene.active.mesh
    view = _view(canvas)
    e = _pickable_edges(canvas, view)[0]
    mid = _edge_mid(canvas, view, e)
    _click(canvas, mid)
    assert scene.selected_edges == set(meshkit.edge_ring(mesh, e))

    scene.set_mode("polygons")
    view = _view(canvas)
    k = _front_faces(canvas, view)[0]
    poly = list(mesh.polygons[k])
    side = meshkit.edge_key(poly[0], poly[1])
    pos = 0.8 * _edge_mid(canvas, view, side) + 0.2 * _face_centre(canvas, view, k)
    _click(canvas, pos)
    ring = select_tools.ring_elements(mesh, "polygons", side, k)
    assert ring and k in ring
    assert ring != select_tools.loop_elements(mesh, "polygons", side)
    assert scene.selected_polygons == ring


def test_pattern_every_second_edge_on_a_cylinder() -> None:
    from quartz_studio.modeling import meshkit, primitives, select_tools

    mesh = primitives.cylinder(50.0, 200.0, 4, 8)
    canvas, scene, filt = _make("edges", mesh, "select_pattern")
    mesh = scene.active.mesh
    view = _view(canvas)
    pts = mesh.points

    def middle_ring(e) -> bool:
        return abs(pts[e[0], 1]) < 1e-6 and abs(pts[e[1], 1]) < 1e-6

    edges = _pickable_edges(canvas, view, middle_ring)
    assert edges
    e = edges[0]
    select_tools.set_option("select_pattern", "count", 1)
    select_tools.set_option("select_pattern", "skip", 1)
    mid = _edge_mid(canvas, view, e)
    _hover(canvas, mid)
    _click(canvas, mid)
    seq = meshkit.edge_loop(mesh, e)
    assert len(seq) == 8
    i0 = seq.index(e)
    expected = {seq[i] for i in range(len(seq)) if (i - i0) % 2 == 0}
    assert scene.selected_edges == expected and len(expected) == 4 and e in expected
    assert seq[(i0 + 1) % 8] not in expected and seq[(i0 - 1) % 8] not in expected
    assert seq[(i0 + 2) % 8] in expected and seq[(i0 - 2) % 8] in expected
    select_tools.reset_options("select_pattern")


def test_fill_inside_contour_island_and_ctrl() -> None:
    from quartz_studio.modeling import meshkit

    canvas, scene, filt = _make("polygons", _cube(4), "select_fill")
    mesh = scene.active.mesh
    view = _view(canvas)
    k = _front_faces(canvas, view)[0]
    normals = meshkit.face_normals(mesh)
    side = {f for f in range(len(mesh.polygons)) if float(normals[f] @ normals[k]) > 0.999}
    assert len(side) == 16
    contour = {meshkit.edge_key(*e) for e in meshkit.region_boundary(mesh, side)}
    scene.set_mode("edges")
    scene.select_components(contour)
    scene.set_mode("polygons")
    assert scene.selected_edges == contour
    c = _face_centre(canvas, view, k)
    _hover(canvas, c)
    assert filt.overlay.preview_items == side
    _click(canvas, c)
    assert scene.selected_polygons == side
    _click(canvas, c, CTRL)
    assert scene.selected_polygons == set()

    scene.selected_edges = set()
    _click(canvas, c)
    assert scene.selected_polygons == set(range(len(mesh.polygons)))


def test_phong_angle_on_a_cube() -> None:
    from quartz_studio.modeling import select_tools

    canvas, scene, filt = _make("polygons", None, "select_phong")
    view = _view(canvas)
    k = _front_faces(canvas, view)[0]
    c = _face_centre(canvas, view, k)
    select_tools.set_option("select_phong", "angle", 40.0)
    _click(canvas, c)
    assert scene.selected_polygons == {k}
    select_tools.set_option("select_phong", "angle", 90.0)
    _click(canvas, c)
    assert scene.selected_polygons == set(range(6))
    select_tools.reset_options("select_phong")


def test_tools_switch_to_their_mode() -> None:
    from quartz_studio.modeling import select_tools

    canvas, scene, filt = _make("model")
    select_tools.activate("select_loop")
    assert scene.tool == "select_loop" and scene.mode == "edges"
    scene.set_mode("model")
    select_tools.activate("select_fill")
    assert scene.tool == "select_fill" and scene.mode == "polygons"
    scene.set_tool("move")
    scene.set_mode("model")
    scene.set_tool("select_ring")
    assert scene.mode == "edges"
    scene.set_tool("move")
    scene.set_mode("model")
    scene.set_tool("select")
    assert scene.mode == "model"


def test_non_editable_object_shows_the_message() -> None:
    from quartz_studio.modeling.install import controller
    from quartz_studio.widgets import menu_bar

    canvas, scene, filt = _make("model")
    scene.remove_object(scene.objects[0])
    cube = menu_bar.create_object("cube", NO_MOD)
    scene.set_mode("points")
    scene.set_tool("select")
    scene._undo.clear()
    _settle()
    messages: list[str] = []
    ctl = controller()
    ctl.message.connect(messages.append)
    try:
        view = canvas._object_view(cube)
        centre = view.screen[view.in_front].mean(axis=0)
        _click(canvas, centre)
        _drag(canvas, centre, centre + (30, 10))
    finally:
        ctl.message.disconnect(messages.append)
    assert messages and messages[0] == "Brush Selection: Make Editable first", messages
    assert not scene.selected_points and not scene._undo
    assert scene.active is cube and cube.kind == "cube"


def _window():
    win = _STATE.get("window")
    if win is not None:
        return win
    app = _app()
    _isolate()
    from quartz_studio.main_window import MainWindow
    from quartz_studio.modeling import install as mi
    from quartz_studio.modeling import select_interaction

    mi.prepare()
    win = MainWindow()
    mi.install(win)
    select_interaction.install(win)
    win.setMinimumSize(1, 1)
    win.resize(1920, 1010)
    win.show()
    _settle(app, 6)
    _STATE["window"] = win
    return win


def test_options_panel_visibility_edits_and_reset() -> None:
    from quartz_studio import prefs
    from quartz_studio.modeling import select_interaction, select_tools
    from quartz_studio.scene import get_scene

    win = _window()
    _isolate()
    filt = select_interaction.install(win)
    assert filt is win.selection_filter
    panel = win.selection_options
    splitter = win.manager_splitter
    options = getattr(win, "tool_options", None)
    expected = splitter.indexOf(options) + 1 if options is not None and splitter.indexOf(options) >= 0 else 1
    assert splitter.indexOf(panel) == expected
    scene = get_scene()
    scene.set_mode("model")
    for tool, shown in (("select", True), ("select_loop", True), ("select_pattern", True),
                        ("select_phong", True), ("select_ring", False), ("select_fill", False),
                        ("move", False)):
        scene.set_tool(tool)
        _settle()
        assert panel.isVisibleTo(win) == shown, tool
        if shown:
            assert panel.header.tab_texts() == [select_tools.get(tool).name.upper()]
    scene.set_tool("select")
    _settle()
    spin = panel.editors["radius"]
    assert spin.value() == 10 and spin.suffix() == " px"
    spin.setValue(20)
    assert select_tools.options("select")["radius"] == 20
    assert prefs.get("selection.options")["select"]["radius"] == 20
    canvas = win.viewport.canvas
    _wheel(canvas, (canvas.width() / 2, canvas.height() / 2), 1, SHIFT)
    assert spin.value() == select_tools.options("select")["radius"] == 24
    panel.reset_button.click()
    assert select_tools.options("select")["radius"] == 10 and spin.value() == 10
    rows = list(panel.rows.values())
    assert all(r.height() == 24 for r in rows if r.isVisibleTo(win))
    assert panel.reset_button.height() == 24
    scene.set_tool("move")
    _settle()


def test_navigation_and_context_menu_still_work() -> None:
    for tool, mode in (("select", "points"), ("select_loop", "edges")):
        canvas, scene, filt = _make(mode, _cube(2), tool)
        view = _view(canvas)
        vis = [int(i) for i in _visible_points(canvas, view) if _inside(canvas, view.screen[i])]
        scene.select_components([vis[0]] if mode == "points" else [])
        before = (set(scene.selected_points), set(scene.selected_edges))
        centre = view.screen[view.in_front].mean(axis=0)
        cam0 = (canvas.camera.heading, canvas.camera.pitch)
        _drag(canvas, centre, centre + (60, 30), button=MIDDLE)
        assert (canvas.camera.heading, canvas.camera.pitch) != cam0, tool
        assert canvas._nav is None
        cam1 = (canvas.camera.heading, canvas.camera.pitch)
        _drag(canvas, centre, centre + (-50, 20), ALT)
        assert (canvas.camera.heading, canvas.camera.pitch) != cam1, tool
        assert (set(scene.selected_points), set(scene.selected_edges)) == before, tool
        assert scene._group_depth == 0
        canvas.context_menu = None
        _click(canvas, (12, 12), button=RIGHT)
        _settle()
        assert canvas.context_menu is not None, tool
        assert (set(scene.selected_points), set(scene.selected_edges)) == before, tool
        _close_popups()
        canvas.context_menu = None


def _cleanup() -> None:
    _close_popups()
    win = _STATE.pop("window", None)
    if win is not None:
        win.close()
    while _LIVE:
        _LIVE.pop().close()
    shutil.rmtree(PREFS_DIR, ignore_errors=True)


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
    _cleanup()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
