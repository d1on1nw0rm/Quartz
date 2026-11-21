from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

PREFS_DIR = tempfile.mkdtemp(prefix="quartz-prefs-perf-text-")
os.environ["QUARTZ_PREFS_DIR"] = PREFS_DIR

import numpy as np
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio.app import create_app

BACKUP_ROOT = os.path.join(STUDIO_ROOT, "build", "backup-pre-interaction-20261120")
VIEW_SIZE = (1000, 640)
ORBIT_GUARD_MS = 76.0
PAINT_GUARD_MS = 64.0
EDIT_GUARD_MS = 100.0
LETTERS = "SextTAOB8"

_LIVE: list[QWidget] = []

RENDER_SCRIPT = """
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
os.environ["QUARTZ_PREFS_DIR"] = tempfile.mkdtemp(prefix="quartz-prefs-perf-render-")
from quartz_studio.app import create_app
from quartz_studio import prefs
prefs.reload()
try:
    from quartz_studio import controls
    controls.STORE_PATH = os.path.join(os.environ["QUARTZ_PREFS_DIR"], "controls.json")
except ImportError:
    pass
from quartz_studio.scene import reset_scene
from quartz_studio.widgets.viewport import Viewport

app = create_app([sys.argv[0]])
views = [(45.0, 19.75, 420.0, False), (135.0, 60.0, 420.0, False), (250.0, -45.0, 60.0, False),
         (60.0, 35.0, 420.0, True)]
modes = ["model", "points", "edges", "polygons"]
for m, mode in enumerate(modes):
    scene = reset_scene()
    view = Viewport()
    view.resize(1000, 640)
    view.show()
    for _ in range(4):
        app.processEvents()
    canvas = view.canvas
    if mode != "model":
        scene.set_mode(mode)
        if mode == "points":
            scene.select_components([0, 6])
        elif mode == "edges":
            scene.select_components([scene.active.mesh.edges[0]])
        else:
            scene.select_components([1])
    for k, (h, p, d, ortho) in enumerate(views):
        cam = canvas.camera
        cam.heading, cam.pitch, cam.distance, cam.ortho = h, p, d, ortho
        canvas.repaint()
        canvas.grab().toImage().save(os.path.join(out, "%s_%d.png" % (mode, k)))
    view.close()
"""


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


def _text_scene():
    from quartz_studio.scene import reset_scene

    scene = reset_scene()
    cube = scene.objects[0]
    spline = scene.add_parametric("text_spline")
    text = scene.add_parametric("text")
    scene.set_param(text, "text", "TESTE")
    boole = scene.add_parametric("boole")
    scene.set_parent(cube, boole)
    inner = scene.add_parametric("text", parent=boole)
    return scene, {"cube": cube, "spline": spline, "text": text, "boole": boole, "inner": inner}


def _viewport():
    from quartz_studio.widgets.viewport import Viewport

    _app()
    _isolate()
    while _LIVE:
        old = _LIVE.pop()
        old.close()
        old.deleteLater()
    _settle()
    view = Viewport()
    view.resize(*VIEW_SIZE)
    view.show()
    _settle()
    _LIVE.append(view)
    return view.canvas


class _Counter:

    def __init__(self) -> None:
        from quartz_studio.scene import Scene

        self.cls = Scene
        self.original = Scene._build
        self.names: list[str] = []

    def __enter__(self) -> "_Counter":
        original = self.original
        names = self.names

        def counting(scene, obj, spec, inputs):
            names.append(obj.name)
            return original(scene, obj, spec, inputs)

        self.cls._build = counting
        return self

    def __exit__(self, *exc) -> None:
        self.cls._build = self.original


def _orbit(canvas, steps: int = 30) -> None:
    canvas.begin_navigation("orbit")
    for _ in range(steps):
        canvas.navigate("orbit", 4.0, 1.0)
        canvas.repaint()
    canvas.end_navigation()
    canvas.repaint()


def test_generators_not_rebuilt_on_camera_or_selection_change() -> None:
    _app()
    scene, objs = _text_scene()
    canvas = _viewport()
    canvas.repaint()
    with _Counter() as counter:
        _orbit(canvas, 12)
        for name in ("spline", "text", "boole", "cube", "inner"):
            scene.set_active(objs[name])
            canvas.repaint()
        scene.set_active(objs["text"])
        scene.set_mode("points")
        scene.select_components([0, 1, 2])
        canvas.repaint()
        scene.set_mode("model")
        canvas.repaint()
    assert counter.names == [], counter.names
    with _Counter() as counter:
        scene.set_active(objs["spline"])
        scene.set_object_position(0, 120.0)
        canvas.repaint()
    assert counter.names == [], counter.names
    with _Counter() as counter:
        scene.set_active(objs["cube"])
        scene.set_object_position(0, 30.0)
    assert counter.names == ["Boole"], counter.names
    with _Counter() as counter:
        scene.set_param(objs["text"], "text", "TESTEX")
    assert counter.names == ["Text"], counter.names


def _ring_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _inside(point: np.ndarray, rings: list[np.ndarray]) -> bool:
    x, y = float(point[0]), float(point[1])
    inside = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i - 1]
            x2, y2 = ring[i]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def _glyph_area(rings: list[np.ndarray]) -> float:
    total = 0.0
    for i, ring in enumerate(rings):
        depth = sum(1 for j, other in enumerate(rings)
                    if j != i and _inside(ring[0], [other]))
        total += abs(_ring_area(ring)) * (1 if depth % 2 == 0 else -1)
    return total


def test_glyph_caps_cover_the_letter_exactly() -> None:
    _app()
    from quartz_studio.objects import registry
    from quartz_studio.objects.gen_spline import text_chains

    spec = registry.SPECS["text"]
    for ch in LETTERS:
        params = {**spec.defaults(), "text": ch, "depth": 20.0}
        rings = [r[:, :2] for r in text_chains(params)]
        mesh = spec.build(params, [])
        pts = mesh.points
        top = [p for p in mesh.polygons if np.allclose(pts[list(p), 2], 20.0)]
        assert top, ch
        area = 0.0
        for poly in top:
            flat = pts[list(poly), :2]
            a = _ring_area(flat)
            assert a > 0.0, (ch, poly, a)
            area += a
            if len(poly) > 3:
                e = np.roll(flat, -1, axis=0) - flat
                cross = e[:, 0] * np.roll(e, -1, axis=0)[:, 1] - e[:, 1] * np.roll(e, -1, axis=0)[:, 0]
                assert (cross > -1e-9).all(), (ch, poly)
            centre = flat.mean(axis=0)
            assert _inside(centre, rings), (ch, poly)
        expected = _glyph_area(rings)
        assert abs(area - expected) <= 1e-6 * expected, (ch, area, expected)
        assert max(len(p) for p in top) <= 4, (ch, max(len(p) for p in top))


def _tri_area_check(flat: np.ndarray, tris) -> tuple[float, int]:
    total = 0.0
    negative = 0
    for a, b, c in tris:
        v = _ring_area(flat[[a, b, c]])
        total += abs(v)
        negative += v < -1e-12
    return total, negative


def _concave_rings() -> list[np.ndarray]:
    angles = np.linspace(0.0, 2.0 * np.pi, 41)[:-1]
    radius = np.where(np.arange(40) % 2 == 0, 100.0, 35.0)
    star = np.column_stack([np.cos(angles) * radius, np.sin(angles) * radius])
    comb = [(0, 0), (100, 0), (100, 60)]
    for k in range(5):
        x = 100 - k * 20
        comb += [(x - 5, 60), (x - 5, 10), (x - 10, 10), (x - 10, 60)]
    comb += [(0, 60)]
    spiral = []
    for t in np.linspace(0.0, 3.0 * np.pi, 60):
        spiral.append((np.cos(t) * (20 + 10 * t), np.sin(t) * (20 + 10 * t)))
    for t in np.linspace(3.0 * np.pi, 0.0, 60):
        spiral.append((np.cos(t) * (10 + 10 * t), np.sin(t) * (10 + 10 * t)))
    rings = [star, np.array(comb, float), np.array(spiral, float)]
    return [r if _ring_area(r) > 0 else r[::-1].copy() for r in rings]


def test_concave_ring_triangulation_covers_exact_area() -> None:
    from quartz_studio.fileio.model import triangulate_ring
    from quartz_studio.objects.gen_spline import _ear_clip
    from quartz_studio.widgets.viewport import _ear_clip_2d

    for ring in _concave_rings():
        expected = _ring_area(ring)
        xyz = np.column_stack([ring, np.zeros(len(ring))])
        for tris in (triangulate_ring(xyz), _ear_clip_2d(ring),
                     _ear_clip(ring, list(range(len(ring))), 1e-12 * 1e4)):
            total, negative = _tri_area_check(ring, tris)
            assert negative == 0, negative
            assert abs(total - expected) <= 1e-9 * expected, (total, expected)
            for a, b, c in tris:
                assert _inside(ring[[a, b, c]].mean(axis=0), [ring])


def test_rings_with_holes_cap_exact_area() -> None:
    from quartz_studio.objects.gen_spline import _cap

    outer = np.array([(0, 0), (120, 0), (120, 40), (40, 40), (40, 120), (0, 120)], float)
    hole_a = np.array([(10, 10), (10, 30), (30, 30), (30, 10)], float)
    hole_b = np.array([(60, 10), (60, 30), (100, 30), (100, 10)], float)
    circle = np.column_stack([np.cos(np.linspace(0, 2 * np.pi, 49)[:-1]) * 100,
                              np.sin(np.linspace(0, 2 * np.pi, 49)[:-1]) * 100])
    inner = circle[::-1] * 0.6
    cases = [(outer, [hole_a, hole_b]), (circle, [inner]), (outer, [])]
    for ring, holes in cases:
        rings = [ring] + holes
        pts = np.column_stack([np.vstack(rings), np.zeros(sum(len(r) for r in rings))])
        ids = list(range(len(pts)))
        start = len(ring)
        hole_ids = []
        for h in holes:
            hole_ids.append(ids[start:start + len(h)])
            start += len(h)
        polys = _cap(pts, ids[:len(ring)], hole_ids, np.array([0.0, 0.0, 1.0]))
        expected = abs(_ring_area(ring)) - sum(abs(_ring_area(h)) for h in holes)
        total = 0.0
        for poly in polys:
            flat = pts[list(poly), :2]
            a = _ring_area(flat)
            assert a > 0.0
            total += a
            assert _inside(flat.mean(axis=0), rings)
        assert abs(total - expected) <= 1e-9 * expected, (total, expected)


def test_default_cube_picture_matches_backup_tree() -> None:
    if not os.path.isdir(os.path.join(BACKUP_ROOT, "quartz_studio")):
        print("     backup tree missing: comparison skipped")
        return
    work = tempfile.mkdtemp(prefix="quartz-perf-pixels-")
    script = os.path.join(work, "render.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(RENDER_SCRIPT)
    outs = {}
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    for tag, root in (("now", STUDIO_ROOT), ("backup", BACKUP_ROOT)):
        out = os.path.join(work, tag)
        os.makedirs(out)
        subprocess.run([sys.executable, script, root, out], check=True, env=env, cwd=root, timeout=600)
        outs[tag] = out
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QImage, QPainter

    def masked(path: str) -> QImage:
        img = QImage(path).convertToFormat(QImage.Format.Format_ARGB32)
        painter = QPainter(img)
        painter.fillRect(QRect(120, 0, 180, 40), Qt.black)
        painter.end()
        return img

    names = sorted(os.listdir(outs["backup"]))
    assert len(names) == 16, names
    for name in names:
        a = masked(os.path.join(outs["now"], name))
        b = masked(os.path.join(outs["backup"], name))
        assert a.size() == b.size() and a == b, name


def test_text_scene_timing_guard() -> None:
    _app()
    scene, objs = _text_scene()
    canvas = _viewport()
    canvas.repaint()
    scene.set_active(objs["text"])
    canvas.repaint()
    t = time.perf_counter()
    for _ in range(5):
        canvas.repaint()
    paint = (time.perf_counter() - t) * 1000.0 / 5
    t = time.perf_counter()
    _orbit(canvas, 20)
    orbit = (time.perf_counter() - t) * 1000.0 / 21
    scene.set_active(objs["cube"])
    canvas.repaint()
    t = time.perf_counter()
    scene.begin_group()
    for _ in range(10):
        scene.move_selection((2.0, 0.0, 0.0))
        canvas.repaint()
    scene.end_group()
    edit = (time.perf_counter() - t) * 1000.0 / 10
    print("     paint %.1f ms, orbit %.1f ms, edit %.1f ms" % (paint, orbit, edit))
    assert paint < PAINT_GUARD_MS, paint
    assert orbit < ORBIT_GUARD_MS, orbit
    assert edit < EDIT_GUARD_MS, edit


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
