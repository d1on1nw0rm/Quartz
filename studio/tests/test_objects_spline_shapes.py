from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np

from quartz_studio.objects import registry
from quartz_studio.objects.registry import BuildInput, mesh_chains
from quartz_studio.scene import Mesh, Scene

SPLINES = ("rectangle", "circle", "arc", "n_side", "four_side", "star", "cogwheel", "profile",
           "cissoid", "cycloid", "formula", "helix", "flower")
PLANAR = ("rectangle", "circle", "arc", "n_side", "four_side", "star", "cogwheel", "profile",
          "cissoid", "cycloid", "formula", "flower")
PLANE_AXIS = {"XY": 2, "ZY": 0, "XZ": 1}
TOL = 1e-6


def build(kind: str, **values) -> Mesh:
    spec = registry.get(kind)
    return spec.build(spec.clamp(values), [])


def check(mesh: Mesh, closed=None, count=None, chains: int = 1, lo=None, hi=None) -> None:
    n = len(mesh.points)
    assert n >= 2, f"too few points: {n}"
    assert not mesh.polygons, "a spline must have no polygons"
    keys = {tuple(np.round(p, 6)) for p in mesh.points}
    assert len(keys) == n, "duplicate points"
    for a, b in mesh.loose_edges:
        assert np.linalg.norm(mesh.points[a] - mesh.points[b]) > 1e-9, "zero-length edge"
    used = {i for e in mesh.loose_edges for i in e}
    assert used == set(range(n)), "unused points"
    found = mesh_chains(mesh)
    assert len(found) == chains, f"{len(found)} chains, expected {chains}"
    if closed is not None:
        assert all(c == closed for _, c in found), f"closed flags {[c for _, c in found]}, expected {closed}"
    if count is not None:
        assert n == count, f"{n} points, expected {count}"
    if lo is not None:
        assert np.all(mesh.points.min(axis=0) >= np.asarray(lo, float) - TOL), \
            f"below bounds: {mesh.points.min(axis=0)} < {lo}"
    if hi is not None:
        assert np.all(mesh.points.max(axis=0) <= np.asarray(hi, float) + TOL), \
            f"above bounds: {mesh.points.max(axis=0)} > {hi}"


def check_order(mesh: Mesh) -> None:
    inputs = BuildInput(mesh, "probe", "spline").chains()
    if len(inputs) == 1:
        assert np.allclose(inputs[0][0], mesh.points), "chain does not follow the drawing order"
        return
    start = 0
    for pts, _ in inputs:
        assert np.allclose(pts, mesh.points[start:start + len(pts)]), "ring chain order differs"
        start += len(pts)


def test_registry_lists_every_spline():
    for kind in SPLINES:
        spec = registry.get(kind)
        assert spec.category == "spline", kind
        assert spec.inputs == "none", kind
        assert spec.param("plane").default == "XY", kind
        assert spec.param("plane").choices == ("XY", "ZY", "XZ"), kind
        assert spec.param("reverse").default is False, kind
        assert spec.param("reverse").kind == "bool", kind
    assert len(registry.by_category("spline")) >= len(SPLINES)


def test_sampling_parameter_is_clamped():
    for kind in ("rectangle", "circle", "arc", "n_side", "cissoid", "cycloid", "flower"):
        spec = registry.get(kind)
        assert spec.param("points_per_90").default == 8, kind
        assert spec.clamp({"points_per_90": 500})["points_per_90"] == 64, kind
        assert spec.clamp({"points_per_90": 0})["points_per_90"] == 1, kind


def test_rectangle_defaults():
    m = build("rectangle")
    check(m, closed=True, count=4, lo=(-200, -200, 0), hi=(200, 200, 0))


def test_rectangle_rounded_corners():
    m = build("rectangle", width=300, height=200, rounding=True, radius=50, points_per_90=4)
    check(m, closed=True, count=20, lo=(-150, -100, 0), hi=(150, 100, 0))
    check_order(m)


def test_rectangle_radius_larger_than_half_side_is_clamped():
    m = build("rectangle", width=300, height=200, rounding=True, radius=500, points_per_90=2)
    check(m, closed=True, lo=(-150, -100, 0), hi=(150, 100, 0))


def test_rectangle_zero_size_is_empty():
    assert len(build("rectangle", width=0.0).points) == 0


def test_circle_defaults():
    m = build("circle")
    check(m, closed=True, count=32, lo=(-200, -200, 0), hi=(200, 200, 0))
    check_order(m)


def test_circle_ellipse():
    m = build("circle", ellipse=True, radius=300, radius_y=150, points_per_90=4)
    check(m, closed=True, count=16, lo=(-300, -150, 0), hi=(300, 150, 0))


def test_circle_ring_has_two_closed_chains():
    m = build("circle", ring=True, inner_radius=100)
    check(m, closed=True, count=64, chains=2, lo=(-200, -200, 0), hi=(200, 200, 0))
    check_order(m)
    inner = m.points[32:]
    assert np.allclose(np.linalg.norm(inner, axis=1), 100.0), "inner ring radius"


def test_circle_ring_ellipse_scales_inner_ring():
    m = build("circle", ring=True, ellipse=True, radius=200, radius_y=100, inner_radius=50, points_per_90=2)
    check(m, closed=True, chains=2, lo=(-200, -100, 0), hi=(200, 100, 0))
    check_order(m)


def test_circle_ring_without_width_is_single_chain():
    m = build("circle", ring=True, inner_radius=0.0)
    check(m, closed=True, count=32, chains=1)


def test_circle_ring_inner_not_smaller_than_outer_is_empty():
    assert len(build("circle", ring=True, inner_radius=200.0).points) == 0


def test_arc_defaults_open_quarter():
    m = build("arc")
    check(m, closed=False, count=9, lo=(0, 0, 0), hi=(200, 200, 0))
    assert np.allclose(m.points[0], (200, 0, 0)) and np.allclose(m.points[-1], (0, 200, 0))
    check_order(m)


def test_arc_sector_closes_through_centre():
    m = build("arc", type="Sector")
    check(m, closed=True, count=10, lo=(0, 0, 0), hi=(200, 200, 0))
    assert np.allclose(m.points[0], (0, 0, 0))


def test_arc_segment_closes_by_chord():
    m = build("arc", type="Segment")
    check(m, closed=True, count=9, lo=(0, 0, 0), hi=(200, 200, 0))


def test_arc_ring_is_closed_band():
    m = build("arc", type="Ring", start_angle=0, end_angle=180)
    check(m, closed=True, count=34, lo=(-200, 0, 0), hi=(200, 200, 0))


def test_arc_full_sweep_is_closed():
    m = build("arc", type="Arc", start_angle=0, end_angle=360, points_per_90=4)
    check(m, closed=True, count=16, lo=(-200, -200, 0), hi=(200, 200, 0))


def _ring_edges(m: Mesh) -> list[float]:
    return sorted(round(float(np.linalg.norm(m.points[a] - m.points[b])), 3) for a, b in m.loose_edges)


def test_arc_full_ring_is_two_closed_circles():
    for end in (360, 720):
        m = build("arc", type="Ring", start_angle=0, end_angle=end)
        check(m, closed=True, chains=2, count=64, lo=(-200, -200, 0), hi=(200, 200, 0))
        assert len(m.loose_edges) == 64
        radii = np.round(np.linalg.norm(m.points, axis=1), 6)
        assert set(radii) == {100.0, 200.0}
        for a, b in m.loose_edges:
            assert abs(radii[a] - radii[b]) < 1e-9
        assert max(_ring_edges(m)) < 40.0
    flat = build("arc", type="Ring", start_angle=0, end_angle=360, inner_radius=0.0)
    check(flat, closed=True, count=32)


def test_arc_full_sector_closes_back_to_first_outer_point():
    for end in (360, 720):
        m = build("arc", type="Sector", start_angle=0, end_angle=end)
        check(m, closed=True, count=32, lo=(-200, -200, 0), hi=(200, 200, 0))
        assert np.allclose(np.linalg.norm(m.points, axis=1), 200.0)
        assert max(_ring_edges(m)) < 40.0
        assert (0, len(m.points) - 1) in {tuple(sorted(e)) for e in m.loose_edges}


def test_arc_runs_counter_clockwise_from_start_to_end():
    for start, end, span in ((300, 90, 150), (90, 0, 270), (0, 90, 90), (0, -90, 270), (350, 10, 20)):
        m = build("arc", start_angle=start, end_angle=end, points_per_90=16)
        ang = (np.degrees(np.arctan2(m.points[:, 1], m.points[:, 0])) - start) % 360.0
        assert abs(ang[0]) < 1e-6 or abs(ang[0] - 360.0) < 1e-6, (start, end)
        assert np.all(np.diff(ang) > 0.0), (start, end)
        assert abs(ang[-1] - span) < 1e-6, (start, end, ang[-1])
        check(m, closed=False)


def test_arc_zero_sweep_is_empty():
    assert len(build("arc", start_angle=45, end_angle=45).points) == 0


def test_arc_every_type_is_valid():
    for kind in ("Arc", "Sector", "Segment", "Ring"):
        m = build("arc", type=kind, start_angle=30, end_angle=300, inner_radius=60, points_per_90=3)
        check(m, closed=kind != "Arc", lo=(-200, -200, 0), hi=(200, 200, 0))
        check_order(m)


def test_arc_ring_inner_not_smaller_than_outer_is_empty():
    assert len(build("arc", type="Ring", inner_radius=250.0).points) == 0


def test_nside_defaults_hexagon():
    m = build("n_side")
    check(m, closed=True, count=6, lo=(-173.2051, -200, 0), hi=(173.2051, 200, 0))
    check_order(m)


def test_nside_rounded_corners():
    m = build("n_side", rounding=True, rounding_radius=30, sides=6, points_per_90=8)
    check(m, closed=True, count=36, lo=(-173.3, -200, 0), hi=(173.3, 200, 0))
    check_order(m)


def test_nside_every_side_count_is_valid():
    for n in (3, 4, 5, 8, 12, 36):
        m = build("n_side", sides=n)
        check(m, closed=True, count=n)
        mr = build("n_side", sides=n, rounding=True, rounding_radius=500.0, points_per_90=4)
        check(mr, closed=True)


def test_four_side_diamond_defaults():
    m = build("four_side")
    check(m, closed=True, count=4, lo=(-200, -100, 0), hi=(200, 100, 0))


def test_four_side_kite():
    m = build("four_side", type="Kite", a=400, b=200, angle=30)
    check(m, closed=True, count=4, lo=(-200, -100, 0), hi=(200, 100, 0))
    assert np.allclose(m.points[0], (-200, 0, 0))


def test_four_side_parallelogram():
    m = build("four_side", type="Parallelogram", a=400, b=200, angle=30)
    check(m, closed=True, count=4, lo=(-200, -100, 0), hi=(546.4102, 100, 0))


def test_four_side_trapezium_and_triangle():
    m = build("four_side", type="Trapezium", a=400, b=200, angle=30)
    check(m, closed=True, count=4, lo=(-200, -28.87, 0), hi=(200, 28.87, 0))
    tri = build("four_side", type="Trapezium", a=400, b=0.0, angle=30)
    check(tri, closed=True, count=3)


def test_four_side_every_type_is_valid():
    for kind in ("Diamond", "Kite", "Parallelogram", "Trapezium"):
        for angle in (5.0, 60.0, 120.0):
            check(build("four_side", type=kind, angle=angle), closed=True)


def test_star_defaults():
    m = build("star")
    check(m, closed=True, count=16, lo=(-200, -200, 0), hi=(200, 200, 0))
    check_order(m)


def test_star_twist_moves_inner_points():
    base = build("star")
    twisted = build("star", twist=22.5, points=5, inner_radius=80, outer_radius=160)
    check(twisted, closed=True, count=10, lo=(-160, -160, 0), hi=(160, 160, 0))
    untwisted = build("star", twist=0.0, points=5, inner_radius=80, outer_radius=160)
    assert not np.allclose(untwisted.points, twisted.points)
    assert len(base.points) == 16


def test_star_points_range():
    for n in (3, 5, 12, 100):
        check(build("star", points=n), closed=True, count=2 * n)


def test_cogwheel_defaults():
    m = build("cogwheel")
    check(m, closed=True, count=36, lo=(-200, -200, 0), hi=(200, 200, 0))
    check_order(m)


def test_cogwheel_bevel_adds_corner_points():
    m = build("cogwheel", bevel=50.0)
    check(m, closed=True, count=60, lo=(-200, -200, 0), hi=(200, 200, 0))


def test_cogwheel_zero_tooth_width_is_spikes():
    m = build("cogwheel", tooth_width=0.0)
    check(m, closed=True, count=24)


def test_cogwheel_full_tooth_width_keeps_gaps():
    m = build("cogwheel", tooth_width=100.0, teeth=6)
    check(m, closed=True)


def test_profile_every_type():
    counts = {"H Shape": 12, "L Shape": 6, "T Shape": 8, "U Shape": 8, "Z Shape": 8}
    for kind, count in counts.items():
        m = build("profile", type=kind)
        check(m, closed=True, count=count)
        check_order(m)


def test_profile_h_bounds():
    check(build("profile"), closed=True, lo=(-50, -100, 0), hi=(50, 100, 0))


def _simple(m: Mesh) -> bool:
    pts = m.points
    edges = m.loose_edges

    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    for i, (a, b) in enumerate(edges):
        for c, d in edges[i + 2:]:
            if len({a, b, c, d}) < 4:
                continue
            d1, d2 = orient(pts[c], pts[d], pts[a]), orient(pts[c], pts[d], pts[b])
            d3, d4 = orient(pts[a], pts[b], pts[c]), orient(pts[a], pts[b], pts[d])
            if d1 * d2 < -1e-9 and d3 * d4 < -1e-9:
                return False
    return True


def test_profile_collapsed_sections_have_no_duplicate_points():
    import itertools
    for kind in ("H Shape", "L Shape", "T Shape", "U Shape", "Z Shape"):
        for h, b, s, t in itertools.product((30, 200), (60, 100), (0, 20, 50, 60, 100, 150),
                                            (0, 20, 40, 100, 150, 250)):
            m = build("profile", type=kind, height=h, b=b, s=s, t=t)
            if not len(m.points):
                continue
            check(m, closed=True)
            assert _simple(m), (kind, h, b, s, t)
            lo, hi = m.points.min(axis=0), m.points.max(axis=0)
            assert np.all(lo >= (-b / 2 - TOL, -h / 2 - TOL, -TOL)) and np.all(hi <= (b / 2 + TOL, h / 2 + TOL, TOL))


def test_profile_h_with_thick_flanges_collapses_to_a_rectangle():
    m = build("profile", type="H Shape", height=200, b=100, s=60, t=150)
    check(m, closed=True, count=4, lo=(-50, -100, 0), hi=(50, 100, 0))
    u = build("profile", type="U Shape", b=100, s=100)
    check(u, closed=True, count=4, lo=(-50, -100, 0), hi=(50, 100, 0))
    h = build("profile", type="H Shape", height=30)
    check(h, closed=True)


def test_profile_thickness_is_clamped():
    m = build("profile", type="H Shape", s=500.0, t=500.0)
    check(m, closed=True, lo=(-50, -100, 0), hi=(50, 100, 0))


def test_cissoid_default_is_open_cusp_curve():
    m = build("cissoid")
    check(m, closed=False, count=9, lo=(0, -200, 0), hi=(200, 200, 0))
    check_order(m)


def test_cissoid_tension_widens_curve():
    small = build("cissoid", tension=2.0)
    large = build("cissoid", tension=20.0)
    assert np.abs(large.points[:, 1]).max() > np.abs(small.points[:, 1]).max()
    check(small, closed=False)
    check(large, closed=False)


def test_cissoid_zero_tension_is_empty():
    assert len(build("cissoid", tension=0.0).points) == 0


def test_lemniscate_is_closed_figure_eight():
    m = build("cissoid", type="Lemniscate")
    check(m, closed=True, count=34, lo=(-200, -100, 0), hi=(200, 100, 0))
    check_order(m)


def test_strophoid_is_closed_loop_left_of_origin():
    m = build("cissoid", type="Strophoid")
    check(m, closed=True, lo=(-400, -1e9, 0), hi=(0, 1e9, 0))
    check_order(m)


def test_strophoid_and_lemniscate_are_valid_at_every_sampling():
    for s in (1, 2, 3, 4, 8, 64):
        stro = build("cissoid", type="Strophoid", points_per_90=s)
        check(stro, closed=True, lo=(-400, -1e9, 0), hi=(0, 1e9, 0))
        lem = build("cissoid", type="Lemniscate", points_per_90=s)
        check(lem, closed=True)
        assert np.allclose(lem.points[:, 0].max(), 200.0) and np.allclose(lem.points[:, 0].min(), -200.0)
        assert abs(lem.points[:, 1].max() + lem.points[:, 1].min()) < 1e-9


def test_lemniscate_extent_matches_width():
    m = build("cissoid", type="Lemniscate", width=400.0, points_per_90=8)
    lo, hi = m.bounds()
    assert abs(hi[0] - 200.0) < 1e-9 and abs(lo[0] + 200.0) < 1e-9
    assert abs(hi[1] + lo[1]) < 1e-9


def test_cycloid_default_is_open():
    m = build("cycloid")
    check(m, closed=False, count=65, lo=(0, -100, 0), hi=(502.7, -20, 0))
    check_order(m)


def test_epicycloid_bounds():
    m = build("cycloid", type="Epicycloid", points_per_90=4)
    check(m, lo=(-180, -180, 0), hi=(180, 180, 0), chains=1)
    check_order(m)


def test_hypocycloid_open_arc_bounds():
    m = build("cycloid", type="Hypocycloid", radius=100.0, r=25.0, a=25.0, end_angle=270.0)
    check(m, closed=False, count=25, lo=(-100, -100, 0), hi=(100, 100, 0))


def test_every_cycloid_type_is_valid():
    for kind in ("Cycloid", "Epicycloid", "Hypocycloid"):
        check(build("cycloid", type=kind, start_angle=0, end_angle=180), chains=1)


def test_formula_defaults_are_open_sine():
    m = build("formula")
    check(m, closed=False, count=20, lo=(-100, -100, 0), hi=(100, 100, 0))
    check_order(m)


def test_formula_custom_expressions_and_samples():
    m = build("formula", x_expr="10*cos(t*pi)", y_expr="10*sin(t*pi)", z_expr="t*5",
              tmin=0.0, tmax=2.0, samples=9)
    check(m, closed=False, count=9, lo=(-10, -10, 0), hi=(10, 10, 10))


def test_formula_rejects_unsafe_expressions():
    for expr in ("__import__('os').getcwd()", "t.__class__", "open('x')", "1/0", "9**9**9",
                 "t[0]", "unknown_name*t", "log(t)*0+(-1)**0.5"):
        spec = registry.get("formula")
        try:
            spec.build(spec.clamp({"x_expr": expr}), [])
        except ValueError:
            continue
        raise AssertionError(f"no ValueError for {expr!r}")


def test_formula_ufunc_output_argument_is_rejected():
    spec = registry.get("formula")
    for expr in ("floor(t, t)", "sin(t, t)", "abs(t, t, t)", "sqrt(t, 1.0)", "arctan2(t)",
                 "minimum(t, t, t)", "hypot(t, t, t)"):
        try:
            spec.build(spec.clamp({"x_expr": expr}), [])
        except ValueError:
            continue
        raise AssertionError(f"no ValueError for {expr!r}")


def test_formula_expressions_do_not_share_the_parameter_array():
    m = build("formula", x_expr="floor(t*3)", y_expr="t", z_expr="t", samples=9)
    assert np.allclose(m.points[:, 1], np.linspace(-1.0, 1.0, 9))
    assert np.allclose(m.points[:, 2], np.linspace(-1.0, 1.0, 9))
    env = {"t": np.linspace(0.0, 1.0, 5)}
    from quartz_studio.objects import spline_shapes
    spline_shapes._evaluate("t", env, (5,))
    spline_shapes._evaluate("t+1", env, (5,))
    assert np.allclose(env["t"], np.linspace(0.0, 1.0, 5))


def test_formula_deep_expression_is_a_value_error():
    spec = registry.get("formula")
    try:
        spec.build(spec.clamp({"x_expr": "(" * 400 + "t" + ")" * 400}), [])
    except ValueError:
        return
    raise AssertionError("no ValueError for a deeply nested expression")


def test_formula_rejects_syntax_error():
    spec = registry.get("formula")
    try:
        spec.build(spec.clamp({"y_expr": "100.0*sin(t*"}), [])
    except ValueError:
        return
    raise AssertionError("no ValueError for a syntax error")


def test_helix_defaults_along_normal():
    m = build("helix")
    check(m, closed=False, count=101, lo=(-200, -200, 0), hi=(200, 200, 200))
    assert abs(m.points[:, 2].max() - 200.0) < TOL
    check_order(m)


def test_helix_plane_puts_height_on_normal():
    m = build("helix", plane="ZY", subdivision=10)
    check(m, closed=False, count=11)
    assert abs(np.ptp(m.points[:, 0]) - 200.0) < TOL
    assert np.ptp(m.points[:, 1]) <= 400.0 + TOL


def test_helix_radius_and_angle_options():
    m = build("helix", start_radius=50.0, end_radius=100.0, start_angle=0.0, end_angle=360.0,
              height=0.0, subdivision=40)
    check(m, closed=False, count=41, lo=(-100, -100, 0), hi=(100, 100, 0))


def test_helix_zero_radius_is_empty():
    assert len(build("helix", start_radius=0.0, end_radius=0.0).points) == 0


def test_flower_defaults():
    m = build("flower")
    check(m, closed=True, count=256, lo=(-200, -200, 0), hi=(200, 200, 0))
    check_order(m)


def test_flower_petal_count():
    m = build("flower", petals=3, points_per_90=4)
    check(m, closed=True, count=48, lo=(-200, -200, 0), hi=(200, 200, 0))


def test_flower_zero_inner_radius_is_empty():
    assert len(build("flower", inner_radius=0.0).points) == 0


def test_every_planar_spline_maps_planes_and_reverses():
    for kind in PLANAR:
        base = build(kind)
        for plane, axis in PLANE_AXIS.items():
            m = build(kind, plane=plane)
            assert np.ptp(m.points[:, axis]) < TOL, f"{kind} {plane} is not flat on its normal"
            assert len(m.points) == len(base.points), kind
        zy = build(kind, plane="ZY")
        assert np.allclose(zy.points[:, 2], base.points[:, 0]), f"{kind} ZY"
        assert np.allclose(zy.points[:, 1], base.points[:, 1]), f"{kind} ZY"
        xz = build(kind, plane="XZ")
        assert np.allclose(xz.points[:, 0], base.points[:, 0]), f"{kind} XZ"
        assert np.allclose(xz.points[:, 2], base.points[:, 1]), f"{kind} XZ"
        rev = build(kind, reverse=True)
        assert np.allclose(rev.points, base.points[::-1]), f"{kind} reverse"
        assert len(mesh_chains(rev)) == len(mesh_chains(base)), kind


def test_helix_reverse_and_plane():
    base = build("helix")
    rev = build("helix", reverse=True)
    assert np.allclose(rev.points, base.points[::-1])
    zy = build("helix", plane="ZY")
    assert np.allclose(zy.points[:, 1], base.points[:, 1])
    assert np.allclose(zy.points[:, 2], base.points[:, 0])


def test_every_choice_option_builds():
    for kind in SPLINES:
        spec = registry.get(kind)
        for param in spec.params:
            if param.kind != "choice":
                continue
            for option in param.choices:
                m = build(kind, **{param.key: option})
                assert spec.clamp({param.key: option})[param.key] == option, (kind, option)
                assert len(m.points) >= 2, (kind, param.key, option)
                check(m)
            bad = spec.clamp({param.key: "not an option"})
            assert bad[param.key] == param.default, (kind, param.key)


def test_every_spline_chains_back_to_one_ordered_chain():
    for kind in SPLINES:
        m = build(kind)
        chains = BuildInput(m, kind, "spline").chains()
        if kind == "circle":
            build_ring = build("circle", ring=True)
            ring_chains = BuildInput(build_ring, kind, "spline").chains()
            assert len(ring_chains) == 2
            assert all(closed for _, closed in ring_chains)
        assert len(chains) == 1, kind
        assert chains[0][1] == mesh_chains(m)[0][1], kind
        check_order(m)


def test_scene_add_parametric_and_set_param():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([sys.argv[0]])
    scene = Scene()
    for kind in SPLINES:
        obj = scene.add_parametric(kind)
        assert obj.kind == kind, kind
        assert obj.error == "", (kind, obj.error)
        assert len(obj.mesh.points) >= 2, kind
        for param in registry.get(kind).params:
            if param.kind == "choice":
                for option in param.choices:
                    scene.set_param(obj, param.key, option)
                    assert obj.error == "", (kind, param.key, option, obj.error)
                    assert len(obj.mesh.points) >= 2, (kind, param.key, option)
                    assert obj.params[param.key] == option
            elif param.kind == "bool":
                scene.set_param(obj, param.key, True)
                assert obj.error == "", (kind, param.key)
                assert obj.params[param.key] is True
        scene.set_param(obj, "plane", "ZY")
        assert obj.error == "", (kind, obj.error)
        assert obj.params["plane"] == "ZY"


def test_scene_formula_error_is_reported_not_run():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([sys.argv[0]])
    scene = Scene()
    obj = scene.add_parametric("formula")
    scene.set_param(obj, "x_expr", "__import__('os').getcwd()")
    assert obj.error != "", "unsafe expression must set obj.error"
    assert len(obj.mesh.points) == 0


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
