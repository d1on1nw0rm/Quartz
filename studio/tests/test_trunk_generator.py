from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.path.isdir("C:/Windows/Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

import quartz_studio.scene as scene_mod
from quartz_studio import fileio
from quartz_studio.objects import registry
from quartz_studio.scene import Mesh
from quartz_studio.widgets import menus_data, object_palette
from quartz_studio.widgets.attribute_manager import AttributeManager

_APP = QApplication.instance() or QApplication([sys.argv[0]])

KEYS = ("sides", "base_radius", "tip_radius", "taper", "caps", "root", "use_point_scales")


def _scene():
    return scene_mod.reset_scene()


def _line(points, edges=None) -> Mesh:
    pts = [tuple(p) for p in points]
    if edges is None:
        edges = [(i, i + 1) for i in range(len(pts) - 1)]
    return Mesh(pts, [], list(edges))


def _straight() -> Mesh:
    return _line([(0.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 200.0, 0.0)])


def _branched() -> Mesh:
    return _line([(0.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 200.0, 0.0), (60.0, 280.0, 0.0),
                  (-60.0, 280.0, 0.0), (0.0, 300.0, 40.0)],
                 [(0, 1), (1, 2), (2, 3), (2, 4), (3, 5)])


def _make(line: Mesh, **params):
    scene = _scene()
    child = scene.add_object("Line", line)
    gen = scene.add_parametric("trunk", adopt=child)
    for key, value in params.items():
        scene.set_param(gen, key, value)
    return scene, gen, child


def _generator(scene):
    return next(o for o in scene.objects if o.kind == "trunk")


def _edge_counts(mesh: Mesh) -> dict:
    count: dict[tuple[int, int], int] = {}
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            key = (a, b) if a < b else (b, a)
            count[key] = count.get(key, 0) + 1
    return count


def _closed(mesh: Mesh) -> bool:
    directed: set[tuple[int, int]] = set()
    for poly in mesh.polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a, b) in directed:
                return False
            directed.add((a, b))
    return bool(directed) and all((b, a) in directed for a, b in directed)


def _open_edges(mesh: Mesh) -> int:
    return sum(1 for v in _edge_counts(mesh).values() if v == 1)


def _volume(mesh: Mesh) -> float:
    total = 0.0
    for poly in mesh.polygons:
        p0 = mesh.points[poly[0]]
        for k in range(1, len(poly) - 1):
            total += float(p0 @ np.cross(mesh.points[poly[k]], mesh.points[poly[k + 1]]))
    return total / 6.0


def _euler(mesh: Mesh) -> int:
    return len(mesh.points) - len(_edge_counts(mesh)) + len(mesh.polygons)


def _solid(mesh: Mesh) -> bool:
    if not _closed(mesh) or _volume(mesh) <= 0:
        return False
    if any(v != 2 for v in _edge_counts(mesh).values()):
        return False
    keys = {tuple(round(float(v), 6) for v in p) for p in mesh.points}
    if len(keys) != len(mesh.points):
        return False
    return all(float(np.linalg.norm(n)) > 0.5 for n in mesh.polygon_normals())


def _ring_radius(mesh: Mesh, y: float, tol: float = 1e-6) -> float:
    pts = mesh.points[np.abs(mesh.points[:, 1] - y) < tol]
    assert len(pts), f"no points at y={y}"
    return float(np.max(np.hypot(pts[:, 0], pts[:, 2])))


def _ring_size(mesh: Mesh, y: float, tol: float = 1e-6) -> int:
    return int(np.sum(np.abs(mesh.points[:, 1] - y) < tol))


def _bounds(mesh: Mesh):
    return mesh.points.min(axis=0), mesh.points.max(axis=0)


def _snapshot(mesh: Mesh) -> tuple:
    return (len(mesh.points), len(mesh.polygons), tuple(np.round(mesh.points, 5).ravel().tolist()))


def test_registry_entry_and_params():
    spec = registry.get("trunk")
    assert spec.category == "generator" and spec.inputs == "children" and spec.icon == "trunk"
    assert spec.label == "Trunk"
    assert spec.description == "Gives every Line child the thickness of a trunk or twig."
    assert tuple(p.key for p in spec.params) == KEYS
    assert spec.defaults() == {"sides": 8, "base_radius": 10.0, "tip_radius": 2.0, "taper": 1.0,
                               "caps": True, "root": "First Point", "use_point_scales": True}
    kinds = {p.key: (p.kind, p.minimum, p.maximum, p.step, p.unit, p.group) for p in spec.params}
    assert kinds["sides"] == ("int", 3, 64, 1, "", "Object")
    assert kinds["base_radius"] == ("distance", 0.0, 1e6, 0.5, "cm", "Object")
    assert kinds["tip_radius"] == ("distance", 0.0, 1e6, 0.5, "cm", "Object")
    assert kinds["taper"] == ("float", 0.1, 10.0, 0.1, "", "Object")
    assert kinds["caps"][0] == "bool" and kinds["use_point_scales"][0] == "bool"
    assert spec.param("root").kind == "choice"
    assert spec.param("root").choices == ("First Point", "Lowest Point")
    assert spec.clamp({"sides": 1, "taper": 50.0, "root": "Nope"}) == dict(
        spec.defaults(), sides=3, taper=10.0)


def test_interface_placement():
    group = dict(object_palette.PALETTE_GROUPS)["Extrude"]
    assert group[-2:] == ("spline_mask", "trunk")
    texts = [e[1] if len(e) > 1 else None for e in menus_data._GENERATORS]
    assert "Trunk" in texts and texts.index("Trunk") == texts.index("Spline Mask") + 1
    assert menus_data._GENERATORS[texts.index("Trunk")][3] == "trunk"
    mesh_texts = [e[1] if len(e) > 1 else None for e in menus_data.MESH_MENU]
    assert mesh_texts.index("Trunk") == mesh_texts.index("Thicken") + 1
    from quartz_studio.widgets.menu_bar import object_menu_path
    assert object_menu_path(registry.get("trunk")) == ("Create", "Generator", "Trunk")


def test_line_child_gives_closed_manifold_with_ring_size():
    scene, gen, child = _make(_straight())
    m = gen.mesh
    assert not gen.error
    assert len(m.points) == 24 and len(m.polygons) == 18
    assert len(m.loose_edges) == 0
    assert _solid(m) and _euler(m) == 2
    for y in (0.0, 100.0, 200.0):
        assert _ring_size(m, y) == 8
    assert sorted(len(p) for p in m.polygons) == [4] * 16 + [8, 8]
    assert abs(_ring_radius(m, 0.0) - 10.0) < 1e-6
    assert abs(_ring_radius(m, 100.0) - 6.0) < 1e-6
    assert abs(_ring_radius(m, 200.0) - 2.0) < 1e-6
    assert child.parent is gen and len(child.mesh.loose_edges) == 2


def test_sides_changes_ring():
    scene, gen, _ = _make(_straight(), sides=12)
    m = gen.mesh
    assert len(m.points) == 36 and len(m.polygons) == 26 and _solid(m)
    assert _ring_size(m, 100.0) == 12
    scene.set_param(gen, "sides", 3)
    assert len(gen.mesh.points) == 9 and _solid(gen.mesh) and _ring_size(gen.mesh, 0.0) == 3
    scene.set_param(gen, "sides", 64)
    assert len(gen.mesh.points) == 192 and _solid(gen.mesh)
    scene.set_param(gen, "sides", 1000)
    assert gen.params["sides"] == 64


def test_base_radius_changes_base_ring():
    scene, gen, _ = _make(_straight(), base_radius=30.0)
    assert abs(_ring_radius(gen.mesh, 0.0) - 30.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 100.0) - 16.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 200.0) - 2.0) < 1e-6
    scene.set_param(gen, "base_radius", 5.0)
    assert abs(_ring_radius(gen.mesh, 0.0) - 5.0) < 1e-6
    assert _solid(gen.mesh)


def test_tip_radius_changes_tip_and_zero_is_apex():
    scene, gen, _ = _make(_straight(), tip_radius=6.0)
    assert abs(_ring_radius(gen.mesh, 200.0) - 6.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 100.0) - 8.0) < 1e-6
    scene.set_param(gen, "tip_radius", 0.0)
    m = gen.mesh
    assert len(m.points) == 17 and len(m.polygons) == 17 and _solid(m) and _euler(m) == 2
    assert _ring_size(m, 200.0) == 1
    assert sum(1 for p in m.polygons if len(p) == 3) == 8
    scene.set_param(gen, "base_radius", 0.0)
    assert len(gen.mesh.points) == 0 and not gen.error


def test_taper_changes_middle_ring():
    scene, gen, _ = _make(_straight())
    linear = _ring_radius(gen.mesh, 100.0)
    scene.set_param(gen, "taper", 2.0)
    thin = _ring_radius(gen.mesh, 100.0)
    scene.set_param(gen, "taper", 0.5)
    thick = _ring_radius(gen.mesh, 100.0)
    assert abs(linear - 6.0) < 1e-6
    assert abs(thin - (2.0 + 8.0 * 0.25)) < 1e-6
    assert abs(thick - (2.0 + 8.0 * 0.5 ** 0.5)) < 1e-6
    assert thin < linear < thick
    assert abs(_ring_radius(gen.mesh, 0.0) - 10.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 200.0) - 2.0) < 1e-6
    assert _solid(gen.mesh)


def test_caps_off_leaves_only_end_rings_open():
    scene, gen, _ = _make(_straight(), caps=False)
    m = gen.mesh
    assert len(m.points) == 24 and len(m.polygons) == 16
    assert _open_edges(m) == 16 and not _closed(m)
    assert all(len(p) == 4 for p in m.polygons)
    scene.set_param(gen, "caps", True)
    assert len(gen.mesh.polygons) == 18 and _open_edges(gen.mesh) == 0


def test_root_first_versus_lowest():
    top_down = _line([(0.0, 200.0, 0.0), (0.0, 100.0, 0.0), (0.0, 0.0, 0.0)])
    scene, gen, _ = _make(top_down)
    assert abs(_ring_radius(gen.mesh, 200.0) - 10.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 0.0) - 2.0) < 1e-6
    scene.set_param(gen, "root", "Lowest Point")
    assert abs(_ring_radius(gen.mesh, 0.0) - 10.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 200.0) - 2.0) < 1e-6
    assert _solid(gen.mesh)
    scene.set_param(gen, "root", "First Point")
    assert abs(_ring_radius(gen.mesh, 200.0) - 10.0) < 1e-6


def test_branched_line_is_one_closed_manifold():
    scene, gen, _ = _make(_branched())
    m = gen.mesh
    assert not gen.error and len(m.polygons) > 40
    assert _solid(m) and _euler(m) == 2
    lo, hi = _bounds(m)
    assert hi[1] > 280.0 and lo[0] < -50.0 and hi[0] > 50.0 and hi[2] > 30.0
    scene.set_param(gen, "caps", False)
    assert _open_edges(gen.mesh) == 3 * 8 and not _closed(gen.mesh)
    scene.set_param(gen, "caps", True)
    scene.set_param(gen, "tip_radius", 0.0)
    assert _solid(gen.mesh) and _euler(gen.mesh) == 2


def test_spline_child_circle_gives_torus_like_skin():
    scene = _scene()
    circle = scene.add_parametric("circle")
    gen = scene.add_parametric("trunk", adopt=circle)
    scene.set_param(gen, "base_radius", 8.0)
    scene.set_param(gen, "tip_radius", 8.0)
    m = gen.mesh
    assert not gen.error and len(circle.mesh.loose_edges) == 32
    assert len(m.points) == 32 * 8 and len(m.polygons) == 32 * 8
    assert all(len(p) == 4 for p in m.polygons)
    assert _closed(m) and _euler(m) == 0 and _volume(m) > 0
    assert _open_edges(m) == 0
    lo, hi = _bounds(m)
    assert abs(hi[0] - 208.0) < 1.0 and abs(lo[0] + 208.0) < 1.0 and abs(hi[2] - 8.0) < 1e-6


def test_spline_child_arc_gives_capped_tube():
    scene = _scene()
    arc = scene.add_parametric("arc")
    gen = scene.add_parametric("trunk", adopt=arc)
    m = gen.mesh
    assert not gen.error and len(arc.mesh.loose_edges) == 8
    assert len(m.points) == 9 * 8 and len(m.polygons) == 8 * 8 + 2
    assert _solid(m) and _euler(m) == 2
    assert sum(1 for p in m.polygons if len(p) == 8) == 2
    scene.set_param(gen, "caps", False)
    assert _open_edges(gen.mesh) == 16


def test_two_children_are_skinned_independently():
    scene = _scene()
    a = scene.add_object("A", _straight())
    b = scene.add_object("B", _line([(300.0, 0.0, 0.0), (300.0, 150.0, 0.0)]))
    gen = scene.add_parametric("trunk", adopt=a)
    scene.set_parent(b, gen)
    m = gen.mesh
    assert not gen.error
    assert len(m.points) == 24 + 16 and len(m.polygons) == 18 + 10
    assert _solid(m) and _euler(m) == 4
    lo, hi = _bounds(m)
    assert hi[0] > 305.0 and lo[0] < -5.0
    scene.set_param(gen, "caps", False)
    assert _open_edges(gen.mesh) == 32


def test_child_with_polygons_only_is_ignored():
    scene = _scene()
    plane = scene.add_object("Plane", Mesh([(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100)],
                                           [(0, 1, 2, 3)]))
    gen = scene.add_parametric("trunk", adopt=plane)
    assert not gen.error and len(gen.mesh.points) == 0 and len(gen.mesh.polygons) == 0
    line = scene.add_object("Line", _straight())
    scene.set_parent(line, gen)
    assert len(gen.mesh.points) == 24 and _solid(gen.mesh)


def test_child_with_polygons_and_loose_edges_skins_only_the_edges():
    mixed = Mesh([(0, 0, 0), (0, 100, 0), (0, 200, 0), (500, 0, 0), (600, 0, 0), (600, 0, 100)],
                 [(3, 4, 5)], [(0, 1), (1, 2)])
    scene, gen, _ = _make(mixed)
    assert len(gen.mesh.points) == 24 and _solid(gen.mesh)
    assert gen.mesh.points[:, 0].max() < 20.0


def test_no_child_gives_empty_convention():
    scene = _scene()
    gen = scene.add_parametric("trunk")
    assert gen.error == "" and len(gen.mesh.points) == 0 and len(gen.mesh.polygons) == 0
    assert len(gen.mesh.loose_edges) == 0
    scene2, gen2, child = _make(_straight())
    assert len(gen2.mesh.points) == 24
    scene2.set_parent(child, None)
    assert gen2.error == "" and len(gen2.mesh.points) == 0


def test_child_with_single_isolated_point_and_degenerate_edges():
    line = _line([(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 100.0, 0.0), (5.0, 5.0, 5.0)],
                 [(0, 1), (1, 2), (2, 1), (0, 0)])
    scene, gen, _ = _make(line)
    assert not gen.error and len(gen.mesh.points) == 16 and _solid(gen.mesh)
    only_zero = _line([(1.0, 1.0, 1.0), (1.0, 1.0, 1.0)])
    scene2, gen2, _ = _make(only_zero)
    assert not gen2.error and len(gen2.mesh.points) == 0


def test_child_under_transformed_parent():
    scene, gen, child = _make(_straight())
    gen.position = np.array([500.0, 0.0, 0.0])
    scene.changed.emit()
    base = _snapshot(gen.mesh)
    child.position = np.array([30.0, 50.0, 0.0])
    scene.changed.emit()
    lo, hi = _bounds(gen.mesh)
    assert abs(lo[1] - 50.0) < 1e-6 and abs(hi[1] - 250.0) < 1e-6
    assert abs(hi[0] - 40.0) < 1e-6 and abs(lo[0] - 20.0) < 1e-6
    assert _solid(gen.mesh)
    child.position = np.array([0.0, 0.0, 0.0])
    child.scale = np.array([1.0, 2.0, 1.0])
    scene.changed.emit()
    lo, hi = _bounds(gen.mesh)
    assert abs(hi[1] - 400.0) < 1e-6 and abs(hi[0] - 10.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 200.0) - 6.0) < 1e-6
    child.scale = np.array([1.0, 1.0, 1.0])
    scene.changed.emit()
    assert _snapshot(gen.mesh) == base


def test_child_rotation_keeps_radius():
    scene, gen, child = _make(_straight())
    child.rotation = np.array([0.0, 0.0, 90.0])
    scene.changed.emit()
    lo, hi = _bounds(gen.mesh)
    assert abs(abs(lo[0]) - 200.0) < 1.0 or abs(hi[0] - 200.0) < 1.0
    assert abs(lo[1] + 10.0) < 1e-6 and abs(hi[1] - 10.0) < 1e-6
    assert _solid(gen.mesh)


def test_point_scales_used_and_can_be_switched_off():
    scene, gen, child = _make(_straight())
    plain = _snapshot(gen.mesh)
    scene.set_point_scales([1], 2.0, child)
    assert abs(_ring_radius(gen.mesh, 100.0) - 12.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 0.0) - 10.0) < 1e-6
    assert _solid(gen.mesh)
    scene.set_param(gen, "use_point_scales", False)
    assert _snapshot(gen.mesh) == plain
    scene.set_param(gen, "use_point_scales", True)
    assert abs(_ring_radius(gen.mesh, 100.0) - 12.0) < 1e-6
    scene.set_point_scales([0, 2], [0.5, 3.0], child)
    assert abs(_ring_radius(gen.mesh, 0.0) - 5.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 200.0) - 6.0) < 1e-6


def test_zero_point_scale_on_inner_point_stays_valid():
    scene, gen, child = _make(_straight())
    scene.set_point_scales([1], 0.0, child)
    assert _solid(gen.mesh) and _ring_radius(gen.mesh, 100.0) < 0.05


def test_make_editable_on_generator_gives_polygon_mesh():
    scene, gen, child = _make(_branched())
    expected = (len(gen.mesh.points), len(gen.mesh.polygons))
    new = scene.make_editable(gen)
    assert new.kind == "polygon" and scene.is_editable(new)
    assert (len(new.mesh.points), len(new.mesh.polygons)) == expected
    assert _solid(new.mesh) and not new.mesh.loose_edges
    assert child not in scene.objects


def test_save_and_reopen_keeps_generator_and_parameters():
    scene, gen, child = _make(_branched(), sides=10, base_radius=14.0, tip_radius=1.5, taper=2.5,
                              caps=False, root="Lowest Point")
    scene.set_point_scales([2], 1.5, child)
    expected = _snapshot(gen.mesh)
    path = os.path.join(tempfile.mkdtemp(prefix="qz_trunk_gen_"), "trunk.quartz")
    fileio.save_scene(scene, path)
    other = scene_mod.reset_scene()
    fileio.open_scene(other, path)
    loaded = [o for o in other.objects if o.kind == "trunk"]
    assert len(loaded) == 1
    g = loaded[0]
    values = registry.get("trunk").clamp(g.params)
    assert values == {"sides": 10, "base_radius": 14.0, "tip_radius": 1.5, "taper": 2.5,
                      "caps": False, "root": "Lowest Point", "use_point_scales": True}
    assert not g.error and _snapshot(g.mesh) == expected
    kids = other.children(g)
    assert len(kids) == 1 and kids[0].kind == "polygon"
    assert abs(kids[0].mesh.point_scales[2] - 1.5) < 1e-9


def test_rebuilds_when_child_points_move():
    scene, gen, child = _make(_straight())
    before = _snapshot(gen.mesh)
    scene.set_active(child)
    scene.set_mode("points")
    scene.select_components([2])
    scene.move_selection((0.0, 50.0, 0.0))
    assert _snapshot(gen.mesh) != before
    assert abs(_bounds(gen.mesh)[1][1] - 250.0) < 1e-6
    assert _solid(gen.mesh)
    assert scene.undo()
    assert _snapshot(_generator(scene).mesh) == before


def test_rebuilds_when_child_gets_points_from_line_pen():
    scene, gen, child = _make(_straight())
    assert len(gen.mesh.points) == 24
    scene.set_active(child)
    scene.set_mode("points")
    scene.set_tool("line_pen")
    scene.pen_link_point(2)
    scene.pen_add_point((0.0, 300.0, 0.0))
    scene.pen_finish()
    assert len(child.mesh.points) == 4
    assert len(gen.mesh.points) == 32 and _solid(gen.mesh)
    assert abs(_bounds(gen.mesh)[1][1] - 300.0) < 1e-6
    assert abs(_ring_radius(gen.mesh, 300.0) - 2.0) < 1e-6


def test_rebuilds_when_child_scales_change_through_scene():
    scene, gen, child = _make(_straight())
    count = gen._version
    scene.multiply_point_scales([1], 3.0, child)
    assert gen._version > count
    assert abs(_ring_radius(gen.mesh, 100.0) - 18.0) < 1e-6
    assert scene.undo()
    assert abs(_ring_radius(_generator(scene).mesh, 100.0) - 6.0) < 1e-6


def test_deterministic_rebuild():
    scene, gen, _ = _make(_branched())
    first = _snapshot(gen.mesh)
    scene.set_param(gen, "sides", 9)
    scene.set_param(gen, "sides", 8)
    assert _snapshot(gen.mesh) == first


def test_large_tree_builds_fast():
    import time
    rng = np.random.default_rng(5)
    pts = [np.zeros(3)]
    edges = []
    for i in range(1, 400):
        parent = int(rng.integers(max(0, i - 6), i))
        pts.append(pts[parent] + rng.normal(size=3) * 40.0 + np.array([0.0, 30.0, 0.0]))
        edges.append((parent, i))
    scene = _scene()
    child = scene.add_object("Tree", Mesh(np.array(pts), [], edges))
    start = time.perf_counter()
    gen = scene.add_parametric("trunk", adopt=child)
    elapsed = time.perf_counter() - start
    assert not gen.error and len(gen.mesh.polygons) > 400
    assert elapsed < 3.0


def test_attribute_manager_builds_rows_from_spec():
    scene = _scene()
    child = scene.add_object("Line", _branched())
    gen = scene.add_parametric("trunk", adopt=child)
    am = AttributeManager()
    am.resize(480, 600)
    am.show()
    for _ in range(3):
        _APP.processEvents()
    assert scene.active is gen
    assert set(KEYS) <= set(am.object_editors)
    am.close()
    am.deleteLater()
    _APP.processEvents()


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
