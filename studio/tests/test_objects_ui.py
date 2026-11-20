from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from quartz_studio.app import create_app

ALT = Qt.KeyboardModifier.AltModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
NO_MOD = Qt.KeyboardModifier.NoModifier

_STATE: dict = {}

PALETTE_BUTTONS = ["Line", "Null", "Rectangle", "Circle", "Cube", "Sphere", "Text",
                   "Subdivision Surface", "Extrude", "Voronoi Fracture"]
EDITABLE_ENTRIES = {"Line": "Line", "Empty Polygon": "Polygon"}


def _window():
    if "window" in _STATE:
        return _STATE["window"]
    app = create_app([sys.argv[0]])
    from quartz_studio.main_window import MainWindow
    from quartz_studio.modeling import install as mi

    mi.prepare()
    win = MainWindow()
    mi.install(win)
    win.resize(1500, 900)
    win.show()
    for _ in range(6):
        app.processEvents()
    _STATE["window"] = win
    _STATE["app"] = app
    return win


def _settle(passes: int = 3) -> None:
    for _ in range(passes):
        _STATE["app"].processEvents()


def _clear():
    from quartz_studio.scene import get_scene

    win = _window()
    scene = get_scene()
    scene.set_tool("move")
    scene.set_mode("model")
    for obj in list(scene.objects):
        if obj in scene.objects:
            scene.remove_object(obj)
    scene._undo.clear()
    scene._redo.clear()
    _settle(1)
    return win, scene


def _spec_by_label() -> dict:
    from quartz_studio import objects

    return {spec.label: spec for spec in objects.all_specs()}


def _check_created(label: str, scene, before: int) -> None:
    specs = _spec_by_label()
    assert len(scene.objects) == before + 1, label
    obj = scene.active
    assert obj is scene.objects[-1], label
    assert scene.object_selected, label
    assert obj.name == EDITABLE_ENTRIES.get(label, label), (label, obj.name)
    assert float(np.abs(obj.position).max()) == 0.0, label
    mesh = obj.mesh
    if label in EDITABLE_ENTRIES:
        assert obj.kind == "polygon" and not len(mesh.points), label
        return
    spec = specs[label]
    assert obj.kind == spec.id, (label, obj.kind)
    assert not obj.error, (label, obj.error)
    if spec.category in ("null", "generator"):
        assert not len(mesh.points) and not mesh.polygons and not mesh.loose_edges, label
        return
    pts = np.asarray(mesh.points, float)
    assert len(pts) > 0 and np.isfinite(pts).all(), label
    assert len({tuple(np.round(p, 6)) for p in pts}) == len(pts), f"{label}: duplicate points"
    used = {i for poly in mesh.polygons for i in poly} | {i for e in mesh.loose_edges for i in e}
    assert used == set(range(len(pts))), f"{label}: unused points"
    if spec.category == "spline":
        assert not mesh.polygons and mesh.loose_edges, label
    else:
        assert mesh.polygons, label
        for poly in mesh.polygons:
            assert len(set(poly)) == len(poly) >= 3 and max(poly) < len(pts), label


def _palette_entries(win) -> list[tuple[object, str, object]]:
    out = []
    for key, button in win.regions["object_palette"].buttons.items():
        names = [c.name for c in button.foldout()] or [button.command_text()]
        for name in names:
            out.append((button, name, key))
    return out


def test_palette_has_the_planned_buttons_and_only_registered_entries() -> None:
    from quartz_studio import objects
    from quartz_studio.widgets.object_palette import PALETTE_GROUPS

    win = _window()
    palette = win.regions["object_palette"]
    assert list(palette.buttons) == PALETTE_BUTTONS
    shown = {name for _b, name, _k in _palette_entries(win)}
    registered = {spec.label for spec in objects.all_specs()}
    assert shown - registered <= set(EDITABLE_ENTRIES) | {"Line"}, shown - registered
    planned = {i for _key, ids in PALETTE_GROUPS for i in ids} | {"null", "polygon_object"}
    missing = [spec.id for spec in objects.all_specs() if spec.id not in planned]
    assert not missing, f"registered objects without a palette slot: {missing}"
    for key, ids in PALETTE_GROUPS:
        wanted = [objects.SPECS[i].label if i in objects.SPECS else "Empty Polygon"
                  for i in ids if i in objects.SPECS or i == "empty_polygon"]
        assert [c.name for c in palette.buttons[key].foldout()] == wanted, key
    assert "Spline Mask" not in shown and "Polygon" not in shown


def test_trunk_is_in_the_extrude_foldout_and_the_generator_menu() -> None:
    win = _window()
    palette = win.regions["object_palette"]
    assert [c.name for c in palette.buttons["Extrude"].foldout()] == ["Extrude", "Sweep", "Lathe", "Loft", "Trunk"]
    bar = win.regions["menu_bar"]
    entries = bar.menu_at(("Create", "Generator", "x")).entries_text()
    assert entries[entries.index("Loft"):entries.index("Loft") + 3] == ["Loft", "Trunk", "---"], entries
    assert bar.action_at(("Create", "Generator", "Trunk")) is not None


def test_every_palette_entry_creates_the_right_object() -> None:
    win, scene = _clear()
    count = 0
    for key, button in win.regions["object_palette"].buttons.items():
        menu = button.build_menu()
        names = [a.text() for a in menu.actions()] or [button.command_text()]
        for name in names:
            win, scene = _clear()
            if menu.actions():
                next(a for a in menu.actions() if a.text() == name).trigger()
            else:
                button.click()
            _settle(1)
            assert button.command_text() == name, (key, name)
            _check_created(name, scene, 0)
            count += 1
        win, scene = _clear()
        button.click()
        _settle(1)
        _check_created(names[-1], scene, 0)
        menu.deleteLater()
    assert count >= 45, count


def test_every_create_menu_item_creates_the_right_object() -> None:
    from quartz_studio import objects
    from quartz_studio.widgets.menu_bar import object_menu_path

    win, scene = _clear()
    bar = win.regions["menu_bar"]
    paths = [(object_menu_path(spec), spec.label) for spec in objects.all_specs()]
    paths += [(("Create", "Spline", "Line"), "Line"), (("Create", "Mesh", "Empty Polygon"), "Empty Polygon")]
    for path, label in paths:
        win, scene = _clear()
        act = bar.action_at(path)
        assert act is not None, path
        assert act.isEnabled(), path
        act.trigger()
        _settle(1)
        _check_created(label, scene, 0)
    shown = {t for t in bar.menu_at(("Create", "Mesh", "x")).entries_text() if t != "---"}
    assert shown == {spec.label for spec in objects.by_category("mesh")} | {"Empty Polygon"}
    assert "Spline Mask" not in bar.menu_at(("Create", "Generator", "x")).entries_text()


def test_creation_without_modifiers_makes_a_root() -> None:
    from quartz_studio.widgets.menu_bar import create_object

    _win, scene = _clear()
    first = create_object("cube", NO_MOD)
    second = create_object("extrude", NO_MOD)
    assert first.parent is None and second.parent is None
    assert scene.active is second and first.parent is None


def test_alt_makes_the_active_object_a_child_of_a_new_generator() -> None:
    from quartz_studio.widgets.menu_bar import create_object

    _win, scene = _clear()
    rect = create_object("rectangle", NO_MOD)
    scene.set_object_position(0, 50.0)
    before = rect.world_position().copy()
    gen = create_object("extrude", ALT)
    assert gen.parent is None
    assert rect.parent is gen
    assert scene.active is gen and scene.object_selected
    assert np.allclose(rect.world_position(), before)
    assert len(gen.mesh.points) > 0
    plain = create_object("cube", ALT)
    assert plain.parent is None and gen.parent is None and rect.parent is gen
    assert scene.active is plain


def test_alt_keeps_the_hierarchy_position_of_the_adopted_object() -> None:
    from quartz_studio.widgets.menu_bar import create_object

    _win, scene = _clear()
    null = create_object("null", NO_MOD)
    child = create_object("rectangle", SHIFT)
    assert child.parent is null
    gen = create_object("extrude", ALT)
    assert gen.parent is null and child.parent is gen
    assert scene.children(null) == [gen]


def test_shift_makes_the_new_object_a_child_of_the_active_one() -> None:
    from quartz_studio.widgets.menu_bar import create_object

    _win, scene = _clear()
    null = create_object("null", NO_MOD)
    cube = create_object("cube", SHIFT)
    assert cube.parent is null and scene.active is cube
    assert np.allclose(cube.world_position(), null.world_position())
    gen = create_object("boole", SHIFT)
    assert gen.parent is cube and scene.active is gen
    assert scene.children(cube) == [gen]
    lonely = create_object("sphere", SHIFT)
    assert lonely.parent is gen


def test_modifiers_work_on_real_palette_clicks() -> None:
    win, scene = _clear()
    palette = win.regions["object_palette"]
    for key in ("Rectangle", "Extrude", "Cube"):
        assert palette.button(key).show_command(key)
    QTest.mouseClick(palette.button("Rectangle"), Qt.MouseButton.LeftButton, NO_MOD,
                     palette.button("Rectangle").rect().center())
    _settle(1)
    rect = scene.active
    assert rect.kind == "rectangle" and rect.parent is None
    extrude = palette.button("Extrude")
    QTest.mouseClick(extrude, Qt.MouseButton.LeftButton, ALT, extrude.rect().center())
    _settle(1)
    gen = scene.active
    assert gen.kind == "extrude" and rect.parent is gen and gen.parent is None
    cube = palette.button("Cube")
    QTest.mouseClick(cube, Qt.MouseButton.LeftButton, SHIFT, cube.rect().center())
    _settle(1)
    assert scene.active.kind == "cube" and scene.active.parent is gen
    assert scene.undo()
    assert not [o for o in scene.objects if o.kind == "cube"]


def test_make_editable_command_button_menu_and_key() -> None:
    from quartz_studio.modeling import install as mi
    from quartz_studio.widgets.menu_bar import can_make_editable, create_object

    win, scene = _clear()
    button = win.regions["command_bar"].button("Make Editable")
    menu_bar = win.regions["menu_bar"]
    assert button.is_wired() and not button.isEnabled()
    assert not can_make_editable()
    cube = create_object("cube", NO_MOD)
    _settle(1)
    assert button.isEnabled() and can_make_editable()
    act = menu_bar.action_at(("Mesh", "Make Editable"))
    assert act is not None and act.property("qs_shortcut") == "C"
    menu_bar.menus["Mesh"].aboutToShow.emit()
    assert act.isEnabled()
    polygons = len(cube.mesh.polygons)
    scene.set_mode("polygons")
    mi.activate_tool("triangulate")
    _settle(1)
    assert len(scene.active.mesh.polygons) == polygons
    scene.set_tool("move")
    button.click()
    _settle(1)
    editable = scene.active
    assert editable is not cube and editable.kind == "polygon" and scene.is_editable(editable)
    assert editable.name == cube.name and len(editable.mesh.polygons) == polygons
    assert not button.isEnabled() and not can_make_editable()
    scene.set_mode("polygons")
    mi.activate_tool("triangulate")
    _settle(1)
    assert len(scene.active.mesh.polygons) == polygons * 2
    scene.set_tool("move")
    scene.set_mode("model")
    sphere = create_object("sphere", NO_MOD)
    _settle(1)
    menu_bar.menus["Mesh"].aboutToShow.emit()
    act.trigger()
    _settle(1)
    assert scene.active.kind == "polygon" and scene.active.name == sphere.name
    sphere = create_object("capsule", NO_MOD)
    win.activateWindow()
    QTest.keyClick(win, Qt.Key.Key_C)
    _settle(1)
    assert scene.active.kind == "polygon" and scene.active.name == sphere.name
    null = create_object("null", NO_MOD)
    assert not can_make_editable() and not button.isEnabled()
    button.setEnabled(True)
    button.click()
    assert scene.active is null and null.kind == "null"
    assert scene.undo()


def test_make_editable_lets_the_mesh_tools_work() -> None:
    from quartz_studio.modeling import install as mi
    from quartz_studio.widgets.menu_bar import create_object, make_editable

    _win, scene = _clear()
    create_object("cube", NO_MOD)
    scene.set_mode("polygons")
    scene.select_components([0])
    mi.activate_tool("extrude")
    _settle(1)
    assert mi.controller().begin() is None
    scene.set_tool("move")
    scene.set_mode("model")
    make_editable()
    scene.set_mode("polygons")
    scene.select_components([0])
    mi.activate_tool("extrude")
    _settle(1)
    session = mi.controller().begin()
    assert session is not None
    mi.controller().cancel()
    scene.set_tool("move")
    scene.set_mode("model")


def test_attribute_manager_shows_the_object_tab_of_the_created_object() -> None:
    from quartz_studio import objects
    from quartz_studio.widgets.menu_bar import create_object

    win, scene = _clear()
    attrs = win.attribute_manager
    assert not attrs.object_editors
    for spec_id in ("sphere", "cloner", "rectangle", "null", "boole"):
        spec = objects.get(spec_id)
        create_object(spec_id, NO_MOD)
        _settle(1)
        assert attrs.header.type_text() == spec.label
        assert attrs.header.name() == scene.active.name
        assert set(attrs.object_editors) == {p.key for p in spec.params}, spec_id
        assert attrs.object_host.isVisibleTo(attrs)
    sphere = create_object("sphere", NO_MOD)
    _settle(1)
    scene.set_param(sphere, "radius", 123.0)
    _settle(1)
    assert abs(float(attrs.object_editors["radius"].value()) - 123.0) < 1e-6
    attrs.object_editors["radius"].set_value(77.0, force=True)
    scene.set_param(sphere, "radius", 55.0)
    _settle(1)
    assert abs(float(attrs.object_editors["radius"].value()) - 55.0) < 1e-6
    assert float(sphere.mesh.bounds()[1][0]) > 0


def test_generator_with_children_hides_them_in_the_render_list() -> None:
    from quartz_studio.widgets.menu_bar import create_object

    win, scene = _clear()
    rect = create_object("rectangle", NO_MOD)
    gen = create_object("extrude", ALT)
    _settle(1)
    assert rect.parent is gen
    rendered = scene.render_objects()
    assert gen in rendered and rect not in rendered
    assert len(gen.mesh.polygons) > 0
    assert all(o.kind != "rectangle" for o in rendered)
    canvas = win.viewport.canvas
    canvas.update()
    _settle(2)
    null = create_object("null", NO_MOD)
    cube = create_object("cube", SHIFT)
    assert null in scene.render_objects() and cube in scene.render_objects()
    gen2 = create_object("symmetry", ALT)
    assert cube.parent is gen2 and cube not in scene.render_objects()
    assert gen2 in scene.render_objects()
    scene.set_enabled(gen2, False)
    assert gen2 not in scene.render_objects() and cube not in scene.render_objects()
    scene.set_enabled(gen2, True)
    assert scene.undo()
    assert scene.undo()


def test_empty_generator_builds_an_empty_mesh() -> None:
    from quartz_studio import objects
    from quartz_studio.widgets.menu_bar import create_object

    _win, scene = _clear()
    for spec in objects.by_category("generator"):
        obj = create_object(spec.id, NO_MOD)
        assert not len(obj.mesh.points) and not obj.error, spec.id
        scene.remove_object(obj)


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
