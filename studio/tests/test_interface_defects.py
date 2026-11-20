from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from quartz_studio.scene import Mesh
from tests.test_objects_ui import _clear, _settle, _window

ALT = Qt.KeyboardModifier.AltModifier
NO_MOD = Qt.KeyboardModifier.NoModifier


def _canvas():
    return _window().regions["viewport"].canvas


def _grab_bytes(canvas) -> bytes:
    image = canvas.grab().toImage()
    return bytes(image.constBits())


def _reference_sight(canvas, pts: np.ndarray) -> np.ndarray:
    pos, fwd, _right, _up = canvas.camera.basis()
    clear = np.ones(len(pts), bool)
    for i, point in enumerate(pts):
        if canvas.camera.ortho:
            depth = float((point - pos) @ fwd)
            origin, direction = point - fwd * depth, fwd
        else:
            vec = point - pos
            depth = float(np.linalg.norm(vec))
            origin, direction = pos, vec
        hit = canvas.raycast(origin, direction)
        clear[i] = hit is None or not (depth > 1e-9 and hit[3] < depth - (1e-6 * depth + 1e-9))
    return clear


def test_dense_default_primitive_paints_in_every_mode_without_per_sample_raycasts() -> None:
    win, scene = _clear()
    canvas = _canvas()
    calls = {"n": 0}
    original = canvas.raycast

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    canvas.raycast = counting
    try:
        obj = scene.add_parametric("landscape")
        assert len(obj.mesh.polygons) >= 10000
        for mode in ("model", "edges", "points"):
            scene.set_mode(mode)
            calls["n"] = 0
            start = time.perf_counter()
            canvas.grab()
            elapsed = time.perf_counter() - start
            assert elapsed < 12.0, f"{mode} paint took {elapsed:.1f}s"
            assert calls["n"] < 50, f"{mode} paint made {calls['n']} raycasts"
    finally:
        del canvas.raycast
        scene.set_mode("model")


def test_sight_trace_matches_per_ray_reference_in_perspective_and_ortho() -> None:
    win, scene = _clear()
    canvas = _canvas()
    torus = scene.add_parametric("torus")
    ball = scene.add_parametric("sphere")
    ball.position[:] = [30.0, 10.0, 0.0]
    scene.changed.emit()
    rng = np.random.default_rng(3)
    pts = np.vstack([torus.world_points(), ball.world_points(),
                     rng.uniform(-300.0, 300.0, (200, 3))])
    saved = canvas.camera.ortho
    try:
        for ortho in (False, True):
            canvas.camera.ortho = ortho
            fast = canvas._trace_sight(pts)
            slow = _reference_sight(canvas, pts)
            assert fast.shape == slow.shape
            assert int((fast != slow).sum()) == 0, f"ortho={ortho}"
            assert 0 < int((~slow).sum()) < len(pts)
    finally:
        canvas.camera.ortho = saved


def test_mesh_triangulation_is_cached_per_mesh() -> None:
    win, scene = _clear()
    canvas = _canvas()
    obj = scene.add_parametric("sphere")
    first = canvas._mesh_triangles(obj.mesh)
    assert canvas._mesh_triangles(obj.mesh) is first
    obj.mesh.points[0] += 1.0
    assert canvas._mesh_triangles(obj.mesh) is not first


class _Buttons:

    def __init__(self) -> None:
        self.state = Qt.MouseButton.NoButton
        self.saved = QGuiApplication.mouseButtons

    def __enter__(self):
        QGuiApplication.mouseButtons = staticmethod(lambda: self.state)
        return self

    def __exit__(self, *_exc) -> None:
        QGuiApplication.mouseButtons = self.saved

    def press(self) -> None:
        self.state = Qt.MouseButton.LeftButton

    def release(self) -> None:
        self.state = Qt.MouseButton.NoButton
        QTest.qWait(120)


def test_each_mouse_drag_of_the_same_param_is_its_own_undo_step() -> None:
    win, scene = _clear()
    cube = scene.add_parametric("cube")
    scene._undo.clear()
    with _Buttons() as mouse:
        mouse.press()
        for v in (210.0, 220.0, 230.0):
            scene.set_param(cube, "size_x", v)
        mouse.release()
        mouse.press()
        for v in (240.0, 250.0, 260.0):
            scene.set_param(cube, "size_x", v)
        mouse.release()
    assert len(scene._undo) == 2
    assert scene.undo()
    assert scene.active.params["size_x"] == 230.0
    assert scene.undo()
    assert scene.active.params["size_x"] == 200.0


def test_each_mouse_drag_of_a_move_is_its_own_undo_step() -> None:
    win, scene = _clear()
    obj = scene.add_object("Box", Mesh.cube(50.0))
    scene.select_object(True)
    scene._undo.clear()
    with _Buttons() as mouse:
        mouse.press()
        for _ in range(3):
            scene.move_selection((10.0, 0.0, 0.0))
        mouse.release()
        mouse.press()
        for _ in range(3):
            scene.move_selection((0.0, 10.0, 0.0))
        mouse.release()
    assert len(scene._undo) == 2
    assert scene.undo()
    assert np.allclose(scene.active.position, [30.0, 0.0, 0.0])
    assert scene.undo()
    assert np.allclose(scene.active.position, [0.0, 0.0, 0.0])


def test_a_single_drag_is_still_one_undo_step() -> None:
    win, scene = _clear()
    cube = scene.add_parametric("cube")
    scene._undo.clear()
    with _Buttons() as mouse:
        mouse.press()
        for v in (210.0, 220.0, 230.0, 240.0):
            scene.set_param(cube, "size_x", v)
        QTest.qWait(100)
        scene.set_param(cube, "size_x", 250.0)
        mouse.release()
    assert len(scene._undo) == 1
    assert scene.undo()
    assert scene.active.params["size_x"] == 200.0


def test_null_symbol_segments_follow_display_radius_and_aspect() -> None:
    from quartz_studio.objects.builtin import NULL_DISPLAYS, null_segments

    for display in NULL_DISPLAYS:
        segs = null_segments(display, 10.0, 1.0)
        if display in ("None", "Dot", "Point"):
            assert segs.shape == (0, 2, 3), display
        else:
            assert segs.ndim == 3 and segs.shape[1:] == (2, 3) and len(segs) >= 4, display
    assert len(null_segments("Rectangle", 10.0, 1.0)) == 4
    assert len(null_segments("Cube", 10.0, 1.0)) == 12
    assert len(null_segments("Pyramid", 10.0, 1.0)) == 8
    assert len(null_segments("Hexagon", 10.0, 1.0)) == 6
    wide = null_segments("Rectangle", 10.0, 0.5)
    assert np.isclose(np.abs(wide[:, :, 0]).max(), 10.0)
    assert np.isclose(np.abs(wide[:, :, 1]).max(), 5.0)
    assert len(null_segments("Circle", 0.0, 1.0)) == 0


def test_null_display_radius_aspect_and_orientation_change_the_viewport() -> None:
    win, scene = _clear()
    canvas = _canvas()
    null = scene.add_parametric("null")
    scene.select_object(False)
    _settle(2)
    scene.set_param(null, "display", "None")
    _settle(2)
    nothing = _grab_bytes(canvas)
    seen = {}
    for display in ("Dot", "Point", "Circle", "Rectangle", "Diamond", "Hexagon", "Pyramid", "Cube"):
        scene.set_param(null, "display", display)
        _settle(2)
        seen[display] = _grab_bytes(canvas)
        assert seen[display] != nothing, f"{display} draws nothing"
    assert len(set(seen.values())) == len(seen)
    scene.set_param(null, "display", "Rectangle")
    base = _grab_bytes(canvas)
    scene.set_param(null, "radius", 40.0)
    assert _grab_bytes(canvas) != base
    scene.set_param(null, "radius", 10.0)
    scene.set_param(null, "aspect_ratio", 0.4)
    assert _grab_bytes(canvas) != base
    scene.set_param(null, "aspect_ratio", 1.0)
    scene.set_param(null, "orientation", "XZ")
    flat = _grab_bytes(canvas)
    scene.set_param(null, "orientation", "XY")
    assert _grab_bytes(canvas) != flat
    scene.set_param(null, "display", "None")
    assert _grab_bytes(canvas) == nothing


def _object_tab(win, kinds):
    from quartz_studio.widgets.menu_bar import create_object

    obj = None
    for kind in kinds:
        obj = create_object(kind, ALT if obj is not None else NO_MOD)
    _settle(3)
    am = win.regions["attribute_manager"]
    _settle(4)
    return am, obj


def test_every_object_tab_fits_at_the_minimum_window_size() -> None:
    from quartz_studio import objects, theme

    win, scene = _clear()
    win.resize(theme.WINDOW_MIN_W, theme.WINDOW_MIN_H)
    _settle(6)
    cases = [("star", "extrude"), ("cloner",)] + [(s.id,) for s in objects.all_specs()
                                                   if s.id not in ("star", "extrude", "cloner")]
    for kinds in cases:
        _clear()
        am, obj = _object_tab(win, kinds)
        bar = am.scroll.horizontalScrollBar()
        assert bar.maximum() == 0, f"{kinds}: {bar.maximum()} px overflow"
        for key, editor in am.object_editors.items():
            if editor.param.kind == "vector" and am.object_rows[key].isVisibleTo(am):
                for spin in editor.spins():
                    assert spin.lineEdit().width() >= 28, f"{kinds}/{key}"
                    assert spin.isVisibleTo(am)
                    right = spin.mapTo(am.scroll.viewport(), spin.rect().bottomRight()).x()
                    assert right <= am.scroll.viewport().width(), f"{kinds}/{key} cut off"
    win.resize(1500, 900)
    _settle(4)


def test_extrude_movement_z_is_visible_and_editable() -> None:
    from quartz_studio import theme

    win, scene = _clear()
    win.resize(theme.WINDOW_MIN_W, theme.WINDOW_MIN_H)
    _settle(6)
    am, obj = _object_tab(win, ("star", "extrude"))
    movement = am.object_editors["movement"]
    zspin = movement.spins()[2]
    assert zspin.value() == 20.0
    right = zspin.mapTo(am.scroll.viewport(), zspin.rect().bottomRight()).x()
    assert right <= am.scroll.viewport().width()
    zspin.setValue(35.0)
    _settle(2)
    assert tuple(obj.params["movement"]) == (0.0, 0.0, 35.0)
    win.resize(1500, 900)
    _settle(4)


def _visible(am, key: str) -> bool:
    return am.object_rows[key].isVisibleTo(am) and am.object_groups[
        am.object_editors[key].param.group].isVisibleTo(am)


def test_cloner_shows_only_the_rows_of_its_mode() -> None:
    win, scene = _clear()
    am, cloner = _object_tab(win, ("cloner",))
    linear = ("linear_count", "linear_position", "linear_scale", "linear_rotation")
    radial = ("radial_count", "radial_radius", "radial_plane", "radial_start", "radial_end",
              "radial_align")
    grid = ("grid_count", "grid_size")
    assert _visible(am, "mode")
    assert all(_visible(am, k) for k in linear)
    assert not any(_visible(am, k) for k in radial + grid)
    scene.set_param(cloner, "mode", "Radial")
    _settle(3)
    assert all(_visible(am, k) for k in radial)
    assert not any(_visible(am, k) for k in linear + grid)
    scene.set_param(cloner, "mode", "Grid Array")
    _settle(3)
    assert all(_visible(am, k) for k in grid)
    assert not any(_visible(am, k) for k in linear + radial)
    assert scene.undo()
    _settle(3)
    assert all(_visible(am, k) for k in radial)
    assert not any(_visible(am, k) for k in grid)


def test_fillet_rows_follow_the_fillet_switch() -> None:
    win, scene = _clear()
    am, cube = _object_tab(win, ("cube",))
    assert _visible(am, "fillet")
    assert not _visible(am, "fillet_radius") and not _visible(am, "fillet_subdivision")
    scene.set_param(cube, "fillet", True)
    _settle(3)
    assert _visible(am, "fillet_radius") and _visible(am, "fillet_subdivision")
    scene.set_param(cube, "fillet", False)
    _settle(3)
    assert not _visible(am, "fillet_radius")


def test_single_option_combos_are_not_offered() -> None:
    win, scene = _clear()
    from quartz_studio.objects import registry
    from quartz_studio.scene import Mesh

    if "ifd_single_choice" not in registry.SPECS:
        registry.register(registry.ObjectSpec(
            id="ifd_single_choice", label="Single Choice", category="mesh",
            build=lambda p, inputs: Mesh.cube(10.0),
            params=(registry.Param("only", "Only", "choice", "A", choices=("A",), group="Object"),
                    registry.Param("many", "Many", "choice", "A", choices=("A", "B"), group="Object"),
                    registry.Param("size", "Size", "distance", 10.0, group="Object"))))
    am, _obj = _object_tab(win, ("ifd_single_choice",))
    assert not _visible(am, "only")
    assert _visible(am, "many") and _visible(am, "size")
    am, cloner = _object_tab(win, ("cloner",))
    clones = am.object_editors["clones"].param
    assert _visible(am, "clones") == (len(clones.choices) > 1)
    am, surface = _object_tab(win, ("subdivision_surface",))
    types = am.object_editors["type"].param
    assert _visible(am, "type") == (len(types.choices) > 1)
    assert _visible(am, "subdivision_editor")


def test_every_visible_choice_combo_has_several_options() -> None:
    from quartz_studio import objects

    win, scene = _clear()
    for spec in objects.all_specs():
        _clear()
        am, _obj = _object_tab(win, (spec.id,))
        for key, editor in am.object_editors.items():
            if editor.param.kind == "choice" and _visible(am, key):
                assert len(editor.param.choices) >= 2, f"{spec.id}/{key}"


def test_object_manager_lists_siblings_in_child_order() -> None:
    from quartz_studio.widgets.menu_bar import create_object

    win, scene = _clear()
    tree = win.regions["object_manager"].tree
    for kind in ("cube", "sphere", "cone"):
        create_object(kind, NO_MOD)
    _settle(3)
    roots = [o.name for o in scene.roots()]
    assert tree.row_names() == roots
    names = tree.row_names()
    assert names.index("Cube") < names.index("Sphere") < names.index("Cone")
    sphere = next(o for o in scene.objects if o.kind == "sphere")
    scene.set_active(sphere)
    boole = create_object("boole", ALT)
    _settle(3)
    assert sphere.parent is boole
    cube = next(o for o in scene.objects if o.kind == "cube")
    scene.set_parent(cube, boole)
    _settle(3)
    kids = [o.name for o in scene.children(boole)]
    rows = [(item.text(0), depth) for item, depth in tree._walk()]
    boole_row = rows.index((boole.name, 0))
    assert [name for name, depth in rows[boole_row + 1:boole_row + 3] if depth == 1] == kids
    assert kids[0] == sphere.name


def test_dropping_between_children_keeps_child_order() -> None:
    from PySide6.QtCore import QPoint
    from quartz_studio.widgets.menu_bar import create_object

    win, scene = _clear()
    tree = win.regions["object_manager"].tree
    for kind in ("cube", "sphere", "cone"):
        create_object(kind, NO_MOD)
    _settle(3)
    cube, sphere, cone = (next(o for o in scene.objects if o.kind == k)
                          for k in ("cube", "sphere", "cone"))
    rect = tree.visualItemRect(tree.item_of(sphere))
    assert tree.drop_object(cone, QPoint(40, rect.top() + 2))
    assert [o.kind for o in scene.roots()] == ["cube", "cone", "sphere"]
    assert [item.text(0) for item, _d in tree._walk()] == [o.name for o in scene.roots()]
    rect = tree.visualItemRect(tree.item_of(cube))
    assert not tree.drop_object(cone, QPoint(40, rect.bottom() - 2))
    assert [o.kind for o in scene.roots()] == ["cube", "cone", "sphere"]
    rect = tree.visualItemRect(tree.item_of(sphere))
    assert tree.drop_object(cube, QPoint(40, rect.bottom() - 2))
    assert [o.kind for o in scene.roots()] == ["cone", "sphere", "cube"]


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
