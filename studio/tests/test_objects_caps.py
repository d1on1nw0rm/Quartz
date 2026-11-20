from __future__ import annotations

import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.objects import caps
from quartz_studio.objects.caps import BEVEL_SHAPES, bevel_profile, offset_rings, safe_distance


def _close(a, b, tol: float = 1e-12) -> bool:
    if len(a) != len(b):
        return False
    return all(abs(x[0] - y[0]) <= tol and abs(x[1] - y[1]) <= tol for x, y in zip(a, b))


def _square(size: float, cx: float = 0.0, cy: float = 0.0, ccw: bool = True) -> np.ndarray:
    h = size / 2.0
    pts = np.array([[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h]], float)
    return pts if ccw else pts[::-1].copy()


def _area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _crosses(rings) -> bool:
    segs = []
    for ri, r in enumerate(rings):
        n = len(r)
        for i in range(n):
            segs.append((ri, i, (i + 1) % n, r[i], r[(i + 1) % n]))

    def orient(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            ri, a0, a1, p, q = segs[i]
            rj, b0, b1, r, s = segs[j]
            if ri == rj and {a0, a1} & {b0, b1}:
                continue
            if orient(p, q, r) * orient(p, q, s) < 0 and orient(r, s, p) * orient(r, s, q) < 0:
                return True
    return False


def _star(points: int = 5, outer: float = 10.0, inner: float = 4.0) -> np.ndarray:
    out = []
    for k in range(points * 2):
        rad = outer if k % 2 == 0 else inner
        a = math.pi / 2.0 + k * math.pi / points
        out.append([rad * math.cos(a), rad * math.sin(a)])
    return np.array(out, float)


def test_public_api():
    assert BEVEL_SHAPES == ("Round", "Step", "Solid")
    assert set(caps.__all__) == {"BEVEL_SHAPES", "bevel_profile", "offset_rings", "safe_distance"}


def test_caps_imports_no_qt_and_no_scene():
    src = open(caps.__file__, encoding="utf-8").read()
    assert "PySide6" not in src and "scene" not in src


def test_round_profile_one_segment():
    assert _close(bevel_profile("Round", 2.0, 1, 1.0), [(0.0, 0.0), (2.0, 2.0)])
    assert _close(bevel_profile("Round", 2.0, 1, 0.0), [(0.0, 0.0), (2.0, 2.0)])


def test_round_profile_three_segments():
    out = bevel_profile("Round", 2.0, 3, 1.0)
    want = [(0.0, 0.0),
            (2.0 * (1.0 - math.cos(math.pi / 6.0)), 1.0),
            (1.0, 2.0 * math.sin(math.pi / 3.0)),
            (2.0, 2.0)]
    assert _close(out, want), out
    half = bevel_profile("Round", 4.0, 3, 0.5)
    t = 1.0 / 3.0
    a = t * math.pi / 2.0
    assert abs(half[1][0] - 4.0 * (0.5 * t + 0.5 * (1.0 - math.cos(a)))) < 1e-12
    assert abs(half[1][1] - 4.0 * (0.5 * t + 0.5 * math.sin(a))) < 1e-12
    assert out[0] == (0.0, 0.0) and out[-1] == (2.0, 2.0)


def test_round_tension_zero_is_linear():
    assert _close(bevel_profile("Round", 3.0, 3, 0.0), [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)])
    out = bevel_profile("Round", 5.0, 7, 0.0)
    assert all(abs(i - r) < 1e-12 for i, r in out)
    assert all(abs(out[j][0] - 5.0 * j / 7) < 1e-12 for j in range(8))


def test_step_profile():
    assert _close(bevel_profile("Step", 2.0, 1, 0.5), [(0.0, 0.0), (0.0, 2.0), (2.0, 2.0)])
    assert _close(bevel_profile("Step", 3.0, 3, 0.5),
                  [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 2.0), (2.0, 2.0), (2.0, 3.0), (3.0, 3.0)])


def test_solid_profile():
    assert _close(bevel_profile("Solid", 3.0, 1, 1.0), [(0.0, 0.0), (0.0, 3.0)])
    assert _close(bevel_profile("Solid", 3.0, 3, 1.0), [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0), (0.0, 3.0)])


def test_zero_size_profile():
    for shape in BEVEL_SHAPES:
        assert bevel_profile(shape, 0.0, 3, 1.0) == [(0.0, 0.0)]
        assert bevel_profile(shape, -1.0, 3, 1.0) == [(0.0, 0.0)]


def test_offset_ccw_square_shrinks():
    out = offset_rings([_square(10.0)], 1.0)
    assert len(out) == 1
    assert np.allclose(out[0], _square(8.0)), out[0]


def test_offset_negative_grows():
    out = offset_rings([_square(10.0)], -1.0)
    assert np.allclose(out[0], _square(12.0)), out[0]


def test_offset_cw_hole_grows():
    hole = _square(4.0, ccw=False)
    out = offset_rings([_square(10.0), hole], 1.0)
    assert np.allclose(out[0], _square(8.0))
    assert np.allclose(out[1], _square(6.0, ccw=False)), out[1]
    assert abs(_area(out[1])) > abs(_area(hole))


def test_offset_zero_and_lists():
    ring = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]]
    out = offset_rings([ring], 0.0)
    assert isinstance(out[0], np.ndarray) and np.allclose(out[0], ring)


def test_offset_sharp_corner_is_clipped():
    ring = np.array([[0.0, 0.0], [100.0, 0.0], [0.0, 2.0]], float)
    out = offset_rings([ring], 1.0)
    moved = np.linalg.norm(out[0] - ring, axis=1)
    assert moved.max() <= 2.0 + 1e-9, moved


def test_safe_distance_rectangle():
    rect = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 2.0], [0.0, 2.0]], float)
    v = safe_distance([rect], 5.0)
    assert 0.0 < v <= 1.0, v
    moved = offset_rings([rect], v)
    assert _area(moved[0]) > 1e-9 and not _crosses(moved)


def test_safe_distance_keeps_small_and_sign():
    sq = _square(10.0)
    assert safe_distance([sq], 1.0) == 1.0
    assert safe_distance([sq], -1.0) == -1.0
    assert safe_distance([sq], 0.0) == 0.0


def test_safe_distance_star_huge():
    star = _star()
    v = safe_distance([star], 1000.0)
    assert 0.0 < v < 1000.0, v
    moved = offset_rings([star], v)
    assert not _crosses(moved)
    assert _area(moved[0]) > 1e-9


def test_safe_distance_ring_with_hole_shared():
    rings = [_square(10.0), _square(6.0, ccw=False)]
    v = safe_distance(rings, 5.0)
    assert 0.0 < v <= 1.0, v
    moved = offset_rings(rings, v)
    assert not _crosses(moved)
    assert _area(moved[0]) > 0.0 and _area(moved[1]) < 0.0


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
