from __future__ import annotations

import math
import os
import sys
import time

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.modeling.trunk_skin import build_skin, profile_radii


def _directed(polys):
    seen = {}
    for p in polys:
        for a, b in zip(p, p[1:] + p[:1]):
            seen[(a, b)] = seen.get((a, b), 0) + 1
    return seen


def _boundary(polys):
    seen = _directed(polys)
    return [(a, b) for (a, b) in seen if (b, a) not in seen]


def _assert_closed_manifold(polys):
    seen = _directed(polys)
    for (a, b), k in seen.items():
        assert k == 1, f"directed edge {(a, b)} used {k} times"
        assert seen.get((b, a)) == 1, f"edge {(a, b)} has no opposite"


def _assert_open_manifold(polys):
    seen = _directed(polys)
    for (a, b), k in seen.items():
        assert k == 1, f"directed edge {(a, b)} used {k} times"
    return [(a, b) for (a, b) in seen if (b, a) not in seen]


def _poly_area(pts, p):
    v = pts[list(p)]
    return 0.5 * float(np.linalg.norm(np.cross(v, np.roll(v, -1, axis=0)).sum(axis=0)))


def _assert_no_degenerate(pts, polys):
    scale = max(float(np.ptp(pts, axis=0).max()), 1e-9)
    for p in polys:
        assert len(p) >= 3, f"polygon {p} too short"
        assert len(set(p)) == len(p), f"polygon {p} repeats an index"
        v = pts[list(p)]
        longest = float(np.linalg.norm(v - np.roll(v, -1, axis=0), axis=1).max())
        area = _poly_area(pts, p)
        assert area > 1e-20 * scale * scale and area > 1e-9 * longest * longest, f"polygon {p} has zero area"


def _assert_no_coincident(pts):
    if len(pts) < 2:
        return
    scale = max(float(np.ptp(pts, axis=0).max()), 1e-9)
    tol = 1e-9 * scale
    if len(pts) <= 2500:
        d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
        np.fill_diagonal(d, np.inf)
        assert float(d.min()) > tol, "two points coincide"
        return
    order = np.lexsort((pts[:, 2], pts[:, 1], pts[:, 0]))
    s = pts[order]
    gaps = np.linalg.norm(np.diff(s, axis=0), axis=1)
    assert float(gaps.min()) > tol, "two points coincide"


def _components(polys, count):
    parent = list(range(count))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for p in polys:
        r0 = find(p[0])
        for q in p[1:]:
            rq = find(q)
            if rq != r0:
                parent[rq] = r0
    groups = {}
    for k, p in enumerate(polys):
        groups.setdefault(find(p[0]), []).append(k)
    return list(groups.values())


def _signed_volume(pts, polys):
    vol = 0.0
    for p in polys:
        a = pts[p[0]]
        for k in range(1, len(p) - 1):
            vol += float(np.dot(a, np.cross(pts[p[k]], pts[p[k + 1]]))) / 6.0
    return vol


def _euler(polys):
    verts = {i for p in polys for i in p}
    edges = {(min(a, b), max(a, b)) for p in polys for a, b in zip(p, p[1:] + p[:1])}
    return len(verts) - len(edges) + len(polys)


def _check(pts, polys, euler=None, caps=True):
    pts = np.asarray(pts, dtype=float)
    assert len(polys) > 0, "empty skin"
    used = {i for p in polys for i in p}
    assert used == set(range(len(pts))), "unused or missing points"
    _assert_no_degenerate(pts, polys)
    _assert_no_coincident(pts)
    if caps:
        _assert_closed_manifold(polys)
    else:
        _assert_open_manifold(polys)
    comps = _components(polys, len(pts))
    out = []
    for comp in comps:
        sub = [polys[k] for k in comp]
        chi = _euler(sub)
        if caps:
            assert _signed_volume(pts, sub) > 0.0, "component is inside out"
        out.append(chi)
    if euler is not None:
        assert sorted(out) == sorted(euler), f"euler {sorted(out)} expected {sorted(euler)}"
    return out


def _skin(points, edges, radii, sides=8, caps=True):
    pts, polys = build_skin(np.asarray(points, dtype=float), edges, np.asarray(radii, dtype=float), sides, caps)
    return np.asarray(pts, dtype=float), polys


def _star(directions, length=100.0, center=(0.0, 0.0, 0.0)):
    c = np.asarray(center, dtype=float)
    pts = [c]
    edges = []
    for d in directions:
        d = np.asarray(d, dtype=float)
        pts.append(c + length * d / np.linalg.norm(d))
        edges.append((0, len(pts) - 1))
    return np.array(pts), edges


def _axis_distance(pts, a, b):
    d = (b - a) / np.linalg.norm(b - a)
    rel = pts - a
    return np.linalg.norm(rel - np.outer(rel @ d, d), axis=1), rel @ d


def _random_tree(rng, n, spread=True):
    pts = [rng.uniform(-50.0, 50.0, 3)]
    deg = [0]
    edges = []
    for i in range(1, n):
        cand = [k for k in range(i) if deg[k] < 6]
        parent = int(rng.choice(cand))
        if spread and rng.random() < 0.5:
            p = rng.uniform(-100.0, 100.0, 3)
        else:
            p = pts[parent] + rng.normal(0.0, 30.0, 3)
        pts.append(p)
        deg.append(1)
        deg[parent] += 1
        edges.append((parent, i))
    return np.array(pts), edges, deg


def _random_radii(rng, pts, edges):
    if rng.random() < 0.5:
        return rng.uniform(0.5, 15.0, len(pts))
    base = rng.uniform(1.0, 15.0)
    tip = rng.choice([0.0, rng.uniform(0.0, 5.0)])
    return profile_radii(pts, edges, base, tip, taper=rng.uniform(0.3, 3.0))


def test_profile_straight_line_linear():
    pts = np.array([[0, 0, 0], [10, 0, 0], [30, 0, 0], [40, 0, 0]], dtype=float)
    r = profile_radii(pts, [(0, 1), (1, 2), (2, 3)], 10.0, 2.0)
    expect = 2.0 + 8.0 * (1.0 - np.array([0.0, 0.25, 0.75, 1.0]))
    assert np.allclose(r, expect)


def test_profile_y_tips_get_tip_radius():
    pts = np.array([[0, 0, 0], [0, 10, 0], [10, 20, 0], [-5, 15, 0]], dtype=float)
    r = profile_radii(pts, [(0, 1), (1, 2), (1, 3)], 10.0, 1.0)
    assert math.isclose(r[0], 10.0)
    assert math.isclose(r[2], 1.0) and math.isclose(r[3], 1.0)
    d_root = 10.0
    d_down = math.hypot(10.0, 10.0)
    t = d_root / (d_root + d_down)
    assert math.isclose(r[1], 1.0 + 9.0 * (1.0 - t))


def test_profile_root_first_and_lowest():
    pts = np.array([[0, 50, 0], [0, 25, 0], [0, 0, 0]], dtype=float)
    edges = [(0, 1), (1, 2)]
    first = profile_radii(pts, edges, 10.0, 2.0, root="first")
    lowest = profile_radii(pts, edges, 10.0, 2.0, root="lowest")
    assert math.isclose(first[0], 10.0) and math.isclose(first[2], 2.0)
    assert math.isclose(lowest[2], 10.0) and math.isclose(lowest[0], 2.0)
    assert math.isclose(lowest[1], 6.0) and math.isclose(first[1], 6.0)


def test_profile_taper_shapes():
    pts = np.array([[0, 0, 0], [50, 0, 0], [100, 0, 0]], dtype=float)
    edges = [(0, 1), (1, 2)]
    lin = profile_radii(pts, edges, 10.0, 0.0, taper=1.0)
    early = profile_radii(pts, edges, 10.0, 0.0, taper=3.0)
    late = profile_radii(pts, edges, 10.0, 0.0, taper=0.3)
    assert math.isclose(lin[1], 5.0)
    assert math.isclose(early[1], 10.0 * 0.5 ** 3.0)
    assert math.isclose(late[1], 10.0 * 0.5 ** 0.3)
    assert early[1] < lin[1] < late[1]


def test_profile_scales_and_isolated_points():
    pts = np.array([[0, 0, 0], [10, 0, 0], [20, 0, 0], [99, 99, 99]], dtype=float)
    r = profile_radii(pts, [(0, 1), (1, 2)], 4.0, 4.0, scales=[1.0, 2.0, 0.5, 3.0])
    assert np.allclose(r, [4.0, 8.0, 2.0, 0.0])


def test_profile_components_and_cycle():
    pts = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0], [50, 0, 0], [60, 0, 0]], dtype=float)
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5)]
    r = profile_radii(pts, edges, 10.0, 2.0)
    assert math.isclose(r[0], 10.0)
    assert math.isclose(r[2], 2.0)
    assert math.isclose(r[1], 6.0) and math.isclose(r[3], 2.0)
    assert math.isclose(r[4], 10.0) and math.isclose(r[5], 2.0)


def test_profile_empty():
    assert len(profile_radii(np.zeros((0, 3)), [], 1.0, 1.0)) == 0
    r = profile_radii(np.zeros((3, 3)), [], 1.0, 1.0)
    assert np.allclose(r, 0.0)


def test_empty_and_isolated():
    pts, polys = build_skin(np.zeros((0, 3)), [], [])
    assert len(pts) == 0 and polys == []
    pts, polys = build_skin(np.array([[0, 0, 0], [1, 1, 1]], dtype=float), [], [1.0, 1.0])
    assert len(pts) == 0 and polys == []
    pts, polys = build_skin(np.array([[0, 0, 0], [0, 0, 0]], dtype=float), [(0, 1)], [1.0, 1.0])
    assert len(pts) == 0 and polys == []


def test_single_segment():
    p, f = _skin([[0, 0, 0], [100, 0, 0]], [(0, 1)], [5.0, 5.0])
    _check(p, f, euler=[2])
    assert len(p) == 16 and len(f) == 10
    assert sum(1 for x in f if len(x) == 4) == 8 and sum(1 for x in f if len(x) == 8) == 2


def test_straight_run_radius_and_quads():
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([3.0, 4.0, 12.0])
    nodes = np.array([a + (b - a) * k for k in (0.0, 4.0, 10.0, 15.0, 20.0)])
    radii = np.array([6.0, 5.0, 3.5, 2.5, 1.5])
    p, f = _skin(nodes, [(0, 1), (1, 2), (2, 3), (3, 4)], radii, sides=12)
    _check(p, f, euler=[2])
    dist, along = _axis_distance(p, a, b)
    stations = (nodes - a) @ ((b - a) / np.linalg.norm(b - a))
    expect = np.interp(along, stations, radii)
    assert np.allclose(dist, expect, rtol=1e-6, atol=0.0)
    assert sum(1 for x in f if len(x) == 4) == len(f) - 2


def test_gentle_bends_limb_faces_are_quads():
    t = np.linspace(0.0, 1.0, 12)
    pts = np.stack([200.0 * t, 40.0 * np.sin(3.0 * t), 30.0 * np.cos(2.0 * t)], axis=1)
    edges = [(i, i + 1) for i in range(11)]
    r = profile_radii(pts, edges, 6.0, 2.0)
    p, f = _skin(pts, edges, r, sides=8)
    _check(p, f, euler=[2])
    quads = [x for x in f if len(x) == 4]
    assert len(quads) == len(f) - 2 and len(quads) == 8 * 11


def test_ninety_degree_bend():
    pts = [[0, 0, 0], [100, 0, 0], [100, 100, 0]]
    p, f = _skin(pts, [(0, 1), (1, 2)], [5.0, 5.0, 5.0])
    _check(p, f, euler=[2])
    assert sum(1 for x in f if len(x) == 4) == 16
    n = np.array([1.0, 1.0, 0.0]) / math.sqrt(2.0)
    rel = p - np.array([100.0, 0.0, 0.0])
    bend = rel[np.abs(rel @ n) < 1e-9]
    assert len(bend) == 8
    assert math.isclose(float(np.linalg.norm(bend, axis=1).max()), 5.0 * math.sqrt(2.0), rel_tol=1e-9)
    assert np.allclose(np.abs(bend[:, 2]).max(), 5.0)


def test_mitre_ring_lies_on_bisector_plane():
    pts = np.array([[0, 0, 0], [100, 0, 0], [180, 60, 0]], dtype=float)
    p, f = _skin(pts, [(0, 1), (1, 2)], [5.0, 5.0, 5.0], sides=8)
    _check(p, f, euler=[2])
    t1 = np.array([1.0, 0.0, 0.0])
    t2 = (pts[2] - pts[1]) / np.linalg.norm(pts[2] - pts[1])
    n = (t1 + t2) / np.linalg.norm(t1 + t2)
    on_plane = np.abs((p - pts[1]) @ n) < 1e-9
    assert int(on_plane.sum()) == 8
    ring = p[on_plane] - pts[1]
    perp1 = np.linalg.norm(ring - np.outer(ring @ t1, t1), axis=1)
    perp2 = np.linalg.norm(ring - np.outer(ring @ t2, t2), axis=1)
    assert np.allclose(perp1, 5.0) and np.allclose(perp2, 5.0)


def test_bend_that_almost_reverses():
    pts = [[0, 0, 0], [100, 0, 0], [0, 4, 0]]
    p, f = _skin(pts, [(0, 1), (1, 2)], [5.0, 5.0, 5.0])
    _check(p, f, euler=[2])
    assert float(p[:, 0].max()) > 99.0
    pts = [[0, 0, 0], [100, 0, 0], [10, 30, 0]]
    p, f = _skin(pts, [(0, 1), (1, 2)], [5.0, 5.0, 5.0])
    _check(p, f, euler=[2])


def test_stretch_is_limited_on_sharp_bends():
    pts = np.array([[0, 0, 0], [100, 0, 0], [100 - 100 * math.cos(math.radians(55)), 100 * math.sin(math.radians(55)), 0]])
    p, f = _skin(pts, [(0, 1), (1, 2)], [5.0, 5.0, 5.0])
    _check(p, f, euler=[2])
    near = np.linalg.norm(p - pts[1], axis=1)
    assert float(near.min()) <= 2.0 * 5.0 + 1e-9


def test_t_junction():
    pts, edges = _star([(1, 0, 0), (-1, 0, 0), (0, 1, 0)])
    p, f = _skin(pts, edges, [5.0, 5.0, 5.0, 5.0])
    _check(p, f, euler=[2])
    assert any(len(x) == 4 for x in f)


def test_y_junction():
    pts, edges = _star([(0, -1, 0), (0.6, 1, 0), (-0.6, 1, 0.2)])
    r = profile_radii(pts, edges, 10.0, 3.0)
    p, f = _skin(pts, edges, r)
    _check(p, f, euler=[2])


def test_four_five_and_eight_way_stars():
    for dirs in (
        [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)],
        [(1, 0, 0), (0.3, 1, 0), (-0.8, 0.6, 0), (-0.8, -0.6, 0), (0.3, -1, 0.1)],
        [(1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1), (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)],
    ):
        pts, edges = _star(dirs)
        p, f = _skin(pts, edges, [6.0] + [4.0] * len(dirs))
        _check(p, f, euler=[2])


def test_limbs_leaving_in_almost_the_same_direction():
    pts, edges = _star([(0, -1, 0), (1, 0.1, 0), (1, 0.17, 0.02)], length=300.0)
    p, f = _skin(pts, edges, [4.0, 4.0, 3.0, 3.0])
    _check(p, f, euler=[2])
    pts, edges = _star([(0, -1, 0), (1, 0.01, 0), (1, 0.02, 0.0)], length=50.0)
    p, f = _skin(pts, edges, [4.0, 4.0, 3.0, 3.0])
    _check(p, f, euler=[2])


def test_straight_trunk_with_side_branches():
    pts, edges = _star([(0, -1, 0), (0, 1, 0), (1, 0, 0)])
    p, f = _skin(pts, edges, [8.0, 8.0, 8.0, 3.0])
    _check(p, f, euler=[2])
    pts, edges = _star([(0, -1, 0), (0, 1, 0), (1, 0, 0), (-1, 0.2, 0.3)])
    p, f = _skin(pts, edges, [8.0, 8.0, 8.0, 3.0, 2.0])
    _check(p, f, euler=[2])
    pts, edges = _star([(0, -1, 0), (0, 1, 0), (1, 0, 0), (1, 0, 0.3)])
    p, f = _skin(pts, edges, [8.0, 8.0, 8.0, 3.0, 2.0])
    _check(p, f, euler=[2])


def test_junctions_closer_than_the_radii():
    pts = np.array([[0, -100, 0], [0, 0, 0], [0, 2, 0], [80, -20, 0], [-80, 60, 0], [0, 100, 0]], dtype=float)
    edges = [(0, 1), (1, 2), (1, 3), (2, 4), (2, 5)]
    p, f = _skin(pts, edges, [10.0, 10.0, 10.0, 4.0, 4.0, 6.0])
    _check(p, f, euler=[2])
    pts = np.array([[0, -100, 0], [0, 0, 0], [0, 1, 0], [0, 2, 0], [50, 0, 0], [-50, 1, 0], [0, 1, 50], [0, 90, 0]], dtype=float)
    edges = [(0, 1), (1, 2), (2, 3), (1, 4), (2, 5), (3, 6), (3, 7)]
    p, f = _skin(pts, edges, [10.0] * 8)
    _check(p, f, euler=[2])


def test_end_right_after_a_junction():
    pts = np.array([[0, -100, 0], [0, 0, 0], [0, 100, 0], [3, 0, 0]], dtype=float)
    p, f = _skin(pts, [(0, 1), (1, 2), (1, 3)], [6.0, 6.0, 6.0, 2.0])
    _check(p, f, euler=[2])
    pts = np.array([[0, -100, 0], [0, 0, 0], [0, 100, 0], [12, 0, 0]], dtype=float)
    p, f = _skin(pts, [(0, 1), (1, 2), (1, 3)], [6.0, 6.0, 6.0, 4.0])
    _check(p, f, euler=[2])
    assert float(p[:, 0].max()) > 11.0


def test_coincident_points_and_zero_length_edges():
    pts = np.array([[0, 0, 0], [50, 0, 0], [50, 0, 0], [100, 10, 0], [50, 0, 0]], dtype=float)
    edges = [(0, 1), (1, 2), (2, 3), (4, 4)]
    p, f = _skin(pts, edges, [5.0] * 5)
    _check(p, f, euler=[2])
    ref_p, ref_f = _skin(pts[[0, 1, 3]], [(0, 1), (1, 2)], [5.0] * 3)
    assert len(p) == len(ref_p) and len(f) == len(ref_f)
    assert np.allclose(p, ref_p)


def test_duplicate_edges_are_ignored():
    pts = np.array([[0, 0, 0], [60, 0, 0], [100, 40, 0]], dtype=float)
    a = _skin(pts, [(0, 1), (1, 2)], [5.0] * 3)
    b = _skin(pts, [(0, 1), (1, 0), (0, 1), (1, 2), (2, 1)], [5.0] * 3)
    assert np.array_equal(a[0], b[0]) and a[1] == b[1]


def test_closed_square_loop():
    pts = [[0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0]]
    p, f = _skin(pts, [(0, 1), (1, 2), (2, 3), (3, 0)], [5.0] * 4)
    _check(p, f, euler=[0])
    assert all(len(x) == 4 for x in f) and len(f) == 32


def test_twisted_loop_closes_without_seam():
    t = np.linspace(0.0, 2.0 * math.pi, 9)[:-1]
    pts = np.stack([100 * np.cos(t), 100 * np.sin(t), 40 * np.sin(2 * t)], axis=1)
    edges = [(i, (i + 1) % 8) for i in range(8)]
    p, f = _skin(pts, edges, [6.0] * 8, sides=6)
    _check(p, f, euler=[0])
    assert all(len(x) == 4 for x in f)


def test_triangle_loop_with_tail():
    pts = [[0, 0, 0], [100, 0, 0], [50, 86, 0], [-100, -50, 0]]
    p, f = _skin(pts, [(0, 1), (1, 2), (2, 0), (0, 3)], [5.0] * 4)
    _check(p, f, euler=[0])


def test_tiny_loop_is_absorbed_into_a_blob():
    pts = [[0, 0, 0], [2, 0, 0], [1, 1.5, 0], [-100, -50, 0]]
    p, f = _skin(pts, [(0, 1), (1, 2), (2, 0), (0, 3)], [5.0] * 4)
    _check(p, f, euler=[2])


def test_two_components():
    pts = [[0, 0, 0], [100, 0, 0], [0, 50, 0], [100, 50, 0], [50, 100, 0]]
    p, f = _skin(pts, [(0, 1), (2, 3), (3, 4)], [5.0] * 5)
    chis = _check(p, f, euler=[2, 2])
    assert len(chis) == 2


def test_side_counts():
    pts, edges = _star([(0, -1, 0), (0.7, 1, 0), (-0.7, 1, 0.3), (0, 0.2, 1)])
    for sides in (3, 4, 5, 8, 16):
        p, f = _skin(pts, edges, [6.0, 6.0, 4.0, 4.0, 3.0], sides=sides)
        _check(p, f, euler=[2])
        s2, f2 = _skin([[0, 0, 0], [100, 0, 0]], [(0, 1)], [5.0, 5.0], sides=sides)
        assert len(s2) == 2 * sides and len(f2) == sides + 2


def test_cone_apex_at_tips():
    pts, edges = _star([(0, -1, 0), (0.6, 1, 0), (-0.6, 1, 0.2)])
    r = profile_radii(pts, edges, 8.0, 0.0)
    p, f = _skin(pts, edges, r, sides=8)
    _check(p, f, euler=[2])
    assert r[1] > 0.0 and r[2] == 0.0 and r[3] == 0.0
    tris = [x for x in f if len(x) == 3]
    assert len(tris) >= 2 * 8
    assert sum(1 for x in f if len(x) == 8) == 1
    for tip in pts[2:]:
        assert int(np.sum(np.linalg.norm(p - tip, axis=1) < 1e-9)) == 1
        k = int(np.argmin(np.linalg.norm(p - tip, axis=1)))
        assert sum(1 for x in f if k in x) == 8
    p, f = _skin([[0, 0, 0], [100, 0, 0]], [(0, 1)], [5.0, 0.0])
    _check(p, f, euler=[2])
    assert len(p) == 9 and len(f) == 9


def test_base_smaller_than_tip():
    pts, edges = _star([(0, -1, 0), (0.6, 1, 0), (-0.6, 1, 0.2)])
    r = profile_radii(pts, edges, 2.0, 10.0)
    assert r[1] < r[2]
    p, f = _skin(pts, edges, r)
    _check(p, f, euler=[2])


def test_very_different_radii_across_a_junction():
    pts, edges = _star([(0, -1, 0), (0, 1, 0), (1, 0, 0)])
    p, f = _skin(pts, edges, [20.0, 20.0, 20.0, 0.5])
    _check(p, f, euler=[2])
    p, f = _skin(pts, edges, [0.5, 0.5, 0.5, 30.0])
    _check(p, f, euler=[2])
    pts, edges = _star([(0, -1, 0), (0.6, 1, 0), (-0.6, 1, 0.2)], length=40.0)
    p, f = _skin(pts, edges, [1.0, 30.0, 0.5, 2.0])
    _check(p, f, euler=[2])


def test_caps_off_leaves_only_end_rings_open():
    pts, edges = _star([(0, -1, 0), (0.6, 1, 0), (-0.6, 1, 0.2), (0, 0.3, 1)])
    p, f = _skin(pts, edges, [6.0, 5.0, 3.0, 3.0, 2.0], sides=8, caps=False)
    _check(p, f, caps=False)
    open_edges = _boundary(f)
    assert len(open_edges) == 4 * 8
    ends = pts[1:]
    radii = [5.0, 3.0, 3.0, 2.0]
    for a, b in open_edges:
        k = int(np.argmin(np.linalg.norm(ends - p[a], axis=1)))
        assert math.isclose(float(np.linalg.norm(p[a] - ends[k])), radii[k], rel_tol=1e-9)
    p, f = _skin([[0, 0, 0], [100, 0, 0]], [(0, 1)], [5.0, 5.0], caps=False)
    assert len(f) == 8 and len(_boundary(f)) == 16


def test_caps_off_with_an_end_inside_a_junction():
    pts = np.array([[0, -100, 0], [0, 0, 0], [0, 100, 0], [3, 0, 0]], dtype=float)
    p, f = _skin(pts, [(0, 1), (1, 2), (1, 3)], [6.0, 6.0, 6.0, 2.0], caps=False)
    _check(p, f, caps=False)
    assert len(_boundary(f)) == 2 * 8


def test_isolated_points_are_ignored():
    pts = np.array([[0, 0, 0], [500, 500, 500], [100, 0, 0], [-7, 3, 2]], dtype=float)
    p, f = _skin(pts, [(0, 2)], [5.0, 99.0, 5.0, 99.0])
    ref_p, ref_f = _skin(pts[[0, 2]], [(0, 1)], [5.0, 5.0])
    assert np.allclose(p, ref_p) and f == ref_f


def test_zero_radius_everywhere_gives_nothing():
    pts, polys = build_skin(np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0]], dtype=float), [(0, 1), (1, 2)], [0.0, 0.0, 0.0])
    assert len(pts) == 0 and polys == []


def test_zero_radius_in_the_middle_is_clamped():
    p, f = _skin([[0, 0, 0], [50, 0, 0], [100, 0, 0]], [(0, 1), (1, 2)], [5.0, 0.0, 5.0])
    _check(p, f, euler=[2])


def test_deterministic():
    rng = np.random.default_rng(7)
    pts, edges, _ = _random_tree(rng, 40, spread=False)
    r = _random_radii(rng, pts, edges)
    a = build_skin(pts, edges, r, 7)
    b = build_skin(pts.copy(), list(edges), r.copy(), 7)
    assert np.array_equal(a[0], b[0]) and a[1] == b[1]


def test_fuzz_random_trees():
    rng = np.random.default_rng(20261119)
    for trial in range(300):
        n = int(rng.integers(2, 26))
        pts, edges, _ = _random_tree(rng, n, spread=bool(rng.random() < 0.5))
        r = _random_radii(rng, pts, edges)
        sides = int(rng.choice([3, 4, 5, 6, 8, 12, 16]))
        caps = bool(rng.random() < 0.85)
        p, f = build_skin(pts, edges, r, sides, caps)
        try:
            chis = _check(p, f, caps=caps)
            if caps:
                assert chis == [2], f"euler {chis}"
        except AssertionError as exc:
            raise AssertionError(f"trial {trial}: {exc}")


def test_fuzz_random_graphs_with_cycles():
    rng = np.random.default_rng(1119)
    for trial in range(60):
        n = int(rng.integers(3, 22))
        pts, edges, deg = _random_tree(rng, n, spread=bool(rng.random() < 0.5))
        have = {(min(a, b), max(a, b)) for a, b in edges}
        extra = 0
        for _ in range(int(rng.integers(1, 4))):
            a, b = (int(x) for x in rng.choice(n, 2, replace=False))
            key = (min(a, b), max(a, b))
            if key in have or deg[a] >= 6 or deg[b] >= 6:
                continue
            have.add(key)
            edges.append(key)
            deg[a] += 1
            deg[b] += 1
            extra += 1
        if rng.random() < 0.3:
            m = len(pts)
            ring = [m, m + 1, m + 2, m + 3]
            pts = np.vstack([pts, rng.uniform(-200.0, 200.0, (4, 3))])
            edges.extend([(ring[k], ring[(k + 1) % 4]) for k in range(4)])
        r = _random_radii(rng, pts, edges)
        sides = int(rng.choice([3, 4, 5, 6, 8, 12]))
        p, f = build_skin(pts, edges, r, sides, True)
        try:
            chis = _check(p, f)
            for chi in chis:
                assert chi <= 2 and chi % 2 == 0 and chi >= 2 - 2 * (extra + 1), f"euler {chis}"
        except AssertionError as exc:
            raise AssertionError(f"trial {trial}: {exc}")


def _growing_tree(rng, n):
    pts = [np.zeros(3)]
    heading = [np.array([0.0, 1.0, 0.0])]
    deg = [0]
    edges = []
    while len(pts) < n:
        base = int(rng.integers(0, len(pts)))
        if deg[base] >= 4:
            continue
        cur = base
        h = heading[base] + rng.normal(0.0, 0.6, 3)
        for _ in range(int(rng.integers(3, 15))):
            if len(pts) >= n:
                break
            h = h / np.linalg.norm(h)
            p = pts[cur] + h * rng.uniform(8.0, 20.0)
            pts.append(p)
            heading.append(h)
            deg.append(1)
            deg[cur] += 1
            edges.append((cur, len(pts) - 1))
            cur = len(pts) - 1
            h = h + rng.normal(0.0, 0.25, 3)
    return np.array(pts), edges


def test_timing_2000_point_tree():
    rng = np.random.default_rng(2000)
    pts, edges = _growing_tree(rng, 2000)
    r = profile_radii(pts, edges, 3.0, 0.5, taper=1.0, root="lowest")
    start = time.perf_counter()
    p, f = build_skin(pts, edges, r, 8, True)
    elapsed = time.perf_counter() - start
    _check(p, f, euler=[2])
    assert elapsed < 1.5, f"took {elapsed:.2f} s"


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
