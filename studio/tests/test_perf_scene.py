from __future__ import annotations

import os
import random
import statistics
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

PREFS_DIR = tempfile.mkdtemp(prefix="quartz-prefs-perf-scene-")
os.environ["QUARTZ_PREFS_DIR"] = PREFS_DIR

import numpy as np
from PySide6.QtWidgets import QApplication

from quartz_studio.app import create_app

SELECT_GUARD_MS = 10.0
SPIN_GUARD_MS = 10.0
MOVE_GUARD_MS = 10.0
BOOLE_MOVE_GUARD_MS = 36.0
HISTORY_GUARD_MS = 10.0
TYPE_GUARD_MS = 150.0

_LIVE: list = []


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(passes: int = 4) -> None:
    app = QApplication.instance()
    for _ in range(passes):
        app.processEvents()


def _isolate() -> None:
    from quartz_studio import prefs

    os.environ["QUARTZ_PREFS_DIR"] = PREFS_DIR
    prefs.reload()
    try:
        from quartz_studio import controls
    except ImportError:
        return
    controls.STORE_PATH = os.path.join(PREFS_DIR, "controls.json")


def _fresh_scene():
    from quartz_studio.scene import reset_scene

    _app()
    _isolate()
    return reset_scene()


def _text_scene():
    scene = _fresh_scene()
    cube = scene.objects[0]
    spline = scene.add_parametric("text_spline")
    text = scene.add_parametric("text")
    scene.set_param(text, "text", "TESTE")
    other = scene.add_parametric("text")
    scene.set_param(other, "text", "Quartz")
    boole = scene.add_parametric("boole")
    scene.set_parent(cube, boole)
    inner = scene.add_parametric("text", parent=boole)
    return scene, {"cube": cube, "spline": spline, "text": text, "other": other, "boole": boole,
                   "inner": inner}


def _by_name(scene, name):
    return next(o for o in scene.objects if o.name == name)


class _Count:

    def __init__(self, owner, attr: str) -> None:
        self.owner = owner
        self.attr = attr
        self.raw = vars(owner)[attr] if isinstance(owner, type) else getattr(owner, attr)
        self.calls = 0

    def __enter__(self) -> "_Count":
        counter = self
        inner = self.raw.__func__ if isinstance(self.raw, staticmethod) else self.raw

        def counting(*args, **kwargs):
            counter.calls += 1
            return inner(*args, **kwargs)

        wrapped = staticmethod(counting) if isinstance(self.raw, staticmethod) else counting
        setattr(self.owner, self.attr, wrapped)
        return self

    def __exit__(self, *exc) -> None:
        setattr(self.owner, self.attr, self.raw)


def test_attribute_manager_keeps_rows_between_objects_of_the_same_kind() -> None:
    from quartz_studio.widgets.attribute_manager import AttributeManager

    scene, objs = _text_scene()
    am = AttributeManager()
    _LIVE.append(am)
    scene.set_active(objs["text"])
    _settle()
    page = am.object_page
    editors = dict(am.object_editors)
    count = am.rebuild_count
    for name in ("other", "inner", "text", "other", "inner"):
        scene.set_active(objs[name])
        _settle()
        assert am.object_page is page
        assert all(am.object_editors[k] is v for k, v in editors.items())
        assert am.object_editors["text"].widgets[0].text() == objs[name].params["text"]
    assert am.rebuild_count == count
    scene.set_active(objs["cube"])
    _settle()
    scene.set_active(objs["boole"])
    _settle()
    scene.set_active(objs["text"])
    _settle()
    assert am.object_page is page
    assert am.rebuild_count == count + 1
    for name in ("boole", "text", "boole", "other", "boole"):
        scene.set_active(objs[name])
    assert am.rebuild_count == count + 1


def test_attribute_manager_builds_pages_lazily() -> None:
    from quartz_studio.widgets.attribute_manager import AttributeManager

    scene, objs = _text_scene()
    scene.set_active(objs["cube"])
    am = AttributeManager()
    _LIVE.append(am)
    assert am.rebuild_count == 0 and am.object_page is None
    scene.set_active(objs["text"])
    assert am.rebuild_count == 1
    scene.set_active(objs["other"])
    assert am.rebuild_count == 1


def test_selection_changes_do_not_rebuild_generators() -> None:
    from quartz_studio.scene import Scene

    scene, objs = _text_scene()
    with _Count(Scene, "_build") as builds, _Count(Scene, "_make_input") as inputs:
        for name in ("spline", "text", "other", "boole", "cube", "inner", "text"):
            scene.set_active(objs[name])
        scene.set_mode("points")
        scene.set_mode("model")
        scene.select_objects([objs["text"], objs["other"]])
    assert builds.calls == 0 and inputs.calls == 0


def test_identical_params_are_built_once() -> None:
    from quartz_studio.objects import registry

    scene, objs = _text_scene()
    spec = registry.SPECS["text"]
    text = objs["text"]
    with _Count(spec, "build") as builds:
        scene.set_param(text, "text", "TESTEX")
        scene.set_param(text, "text", "TESTE")
        scene.set_param(text, "text", "TESTEX")
        scene.set_param(text, "depth", 35.0)
        scene.set_param(text, "depth", 20.0)
        scene.set_param(text, "depth", 35.0)
    assert builds.calls <= 3, builds.calls
    assert text.mesh.points[:, 2].max() == 35.0


def test_depth_change_reuses_text_topology() -> None:
    scene, objs = _text_scene()
    text = objs["text"]
    before = text.mesh
    scene.set_param(text, "depth", 55.0)
    after = text.mesh
    assert after is not before
    assert after.polygons is before.polygons and after.edges is before.edges
    assert np.isclose(after.points[:, 2].max(), 55.0) and np.isclose(after.points[:, 2].min(), 0.0)
    assert np.allclose(after.points[:, :2], before.points[:, :2])


def test_undo_and_redo_share_generator_meshes_and_rebuild_nothing() -> None:
    from quartz_studio.scene import Scene

    scene, objs = _text_scene()
    text = objs["text"]
    scene.set_param(text, "text", "TESTEX")
    snapshot = scene._undo[-1]
    assert any(rec.get("mesh") is not None for rec in snapshot["objects"])
    mesh_before = _by_name(scene, text.name).mesh
    with _Count(Scene, "_build") as builds:
        assert scene.undo()
        assert scene.redo()
    assert builds.calls == 0
    assert _by_name(scene, text.name).mesh is mesh_before
    assert len(_by_name(scene, objs["boole"].name).mesh.polygons) > 0


def test_boole_child_move_rebuilds_only_the_boole_and_one_input() -> None:
    from quartz_studio.scene import Scene

    scene, objs = _text_scene()
    scene.set_active(objs["cube"])
    scene.begin_group()
    with _Count(Scene, "_build") as builds, _Count(Scene, "_make_input") as inputs:
        for _ in range(5):
            scene.move_selection((3.0, 0.0, 0.0))
    scene.end_group()
    assert builds.calls == 5 and inputs.calls == 5, (builds.calls, inputs.calls)


def test_listeners_ignore_changes_that_do_not_concern_them() -> None:
    from quartz_studio.widgets import status_bar as status_mod
    from quartz_studio.widgets.attribute_manager import AttributeManager
    from quartz_studio.widgets.coordinates import CoordField, CoordinatesManager
    from quartz_studio.widgets.object_manager import ObjectTree
    from quartz_studio.widgets.status_bar import StatusBar

    scene, objs = _text_scene()
    scene.set_active(objs["text"])
    am = AttributeManager()
    coords = CoordinatesManager()
    status = StatusBar()
    tree = ObjectTree()
    _LIVE.extend([am, coords, status, tree])
    _settle()
    with _Count(AttributeManager, "_load") as loads, _Count(CoordField, "set_value") as sets, \
            _Count(ObjectTree, "_rows") as rows, _Count(status_mod, "status_texts") as texts:
        scene.changed.emit()
        scene.selectionChanged.emit()
        scene.objectsChanged.emit()
        scene.changed.emit()
        assert (loads.calls, sets.calls, rows.calls, texts.calls) == (0, 0, 0, 0), (
            loads.calls, sets.calls, rows.calls, texts.calls)
        scene.set_param(objs["text"], "depth", 41.0)
        assert loads.calls >= 1 and sets.calls >= 1
        assert rows.calls == 0
        before = sets.calls
        scene.set_object_position(0, 12.0)
        assert sets.calls == before + 9
        assert coords.field(0, 0).value() == 12.0
        scene.rename_object(objs["text"], "Renamed")
        assert rows.calls >= 1
        scene.set_mode("points")
        assert texts.calls >= 1


def _inside(point, ring) -> bool:
    x, y = float(point[0]), float(point[1])
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i - 1]
        x2, y2 = ring[i]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _concave_polygons() -> list[np.ndarray]:
    angles = np.linspace(0.0, 2.0 * np.pi, 41)[:-1]
    radius = np.where(np.arange(40) % 2 == 0, 100.0, 35.0)
    star = np.column_stack([np.cos(angles) * radius, np.sin(angles) * radius])
    comb = [(0, 0), (100, 0), (100, 60)]
    for k in range(5):
        x = 100 - k * 20
        comb += [(x - 5, 60), (x - 5, 10), (x - 10, 10), (x - 10, 60)]
    comb += [(0, 60)]
    rng = random.Random(5)
    blob = []
    for k in range(30):
        a = 2.0 * np.pi * k / 30
        r = 100.0 * (0.45 + 0.55 * rng.random())
        blob.append((np.cos(a) * r, np.sin(a) * r))
    return [(star, 4), (np.array(comb, float), None), (np.array(blob, float), 6)]


def test_concave_ngon_guides_stay_inside_and_do_not_fan() -> None:
    from quartz_studio.scene import Mesh

    _app()
    for flat, fan_limit in _concave_polygons():
        n = len(flat)
        pts = np.column_stack([flat, np.zeros(n)])
        area = 0.5 * float(np.sum(flat[:, 0] * np.roll(flat[:, 1], -1) - np.roll(flat[:, 0], -1) * flat[:, 1]))
        if area < 0:
            pts = pts[::-1].copy()
            flat = flat[::-1].copy()
        mesh = Mesh(pts, [tuple(range(n))])
        guides = mesh.ngon_guides(0)
        assert guides, n
        valence: dict[int, int] = {}
        for a, b in guides:
            assert a != b
            mid = (flat[a] + flat[b]) / 2.0
            assert _inside(mid, flat), (n, a, b)
            valence[a] = valence.get(a, 0) + 1
            valence[b] = valence.get(b, 0) + 1
        if fan_limit is not None:
            assert max(valence.values()) <= fan_limit, (n, valence)


def test_polygon_edges_match_the_reference_walk() -> None:
    from quartz_studio.scene import Mesh

    rng = random.Random(11)
    for _ in range(100):
        polys = [tuple(rng.randrange(0, 12) for _ in range(rng.randint(3, 8)))
                 for _ in range(rng.randint(1, 10))]
        mesh = Mesh(np.zeros((12, 3)), polys)
        assert mesh.polygon_edges() == mesh._polygon_edges_slow()
    cube = Mesh.cube()
    assert cube.polygon_edges() == cube._polygon_edges_slow() and len(cube.edges) == 12


def _median_ms(steps) -> float:
    values = []
    for step in steps:
        t = time.perf_counter()
        step()
        values.append((time.perf_counter() - t) * 1000.0)
    return statistics.median(values)


def test_interactive_events_timing_guard() -> None:
    from quartz_studio.main_window import MainWindow

    scene, objs = _text_scene()
    win = MainWindow()
    win.resize(1920, 1010)
    win.show()
    _LIVE.append(win)
    _settle(6)
    am = win.regions["attribute_manager"]
    names = [objs[k].name for k in ("spline", "text", "other", "boole", "cube", "inner")]
    scene.set_active(_by_name(scene, names[1]))
    _settle()
    select = _median_ms([lambda n=n: scene.set_active(_by_name(scene, n)) for n in names * 2])
    text_name = objs["text"].name
    scene.set_active(_by_name(scene, text_name))
    _settle()
    spin = _median_ms([lambda v=v: am.object_editors["depth"].widgets[0].setValue(v)
                       for v in (30.0 + 4.0 * i for i in range(10))])
    scene.begin_group()
    move = _median_ms([lambda: scene.move_selection((1.0, 0.0, 0.0)) for _ in range(20)])
    scene.end_group()
    cube_name = objs["cube"].name
    scene.set_active(_by_name(scene, cube_name))
    scene.begin_group()
    boole_move = _median_ms([lambda: scene.move_selection((1.0, 0.0, 0.0)) for _ in range(20)])
    scene.end_group()
    history = _median_ms([scene.undo, scene.redo, scene.undo, scene.redo])
    scene.set_active(_by_name(scene, text_name))
    word = [scene.active.params["text"]]

    def typed(ch):
        def run():
            word[0] += ch
            scene.set_param(_by_name(scene, text_name), "text", word[0])
        return run

    typing = _median_ms([typed(c) for c in "abcde"])
    print("     select %.1f, spin %.1f, move %.1f, boole move %.1f, history %.1f, type %.1f ms"
          % (select, spin, move, boole_move, history, typing))
    assert select < SELECT_GUARD_MS, select
    assert spin < SPIN_GUARD_MS, spin
    assert move < MOVE_GUARD_MS, move
    assert boole_move < BOOLE_MOVE_GUARD_MS, boole_move
    assert history < HISTORY_GUARD_MS, history
    assert typing < TYPE_GUARD_MS, typing


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
    while _LIVE:
        w = _LIVE.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
