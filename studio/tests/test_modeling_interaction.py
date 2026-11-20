from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from quartz_studio.app import create_app
from quartz_studio.modeling import Selection, get_tool, run_tool, tool_ids
from quartz_studio.modeling.meshkit import clone, edge_key
from quartz_studio.modeling.session import selection_from_scene
from quartz_studio.scene import Mesh

LEFT = Qt.MouseButton.LeftButton
NO_MOD = Qt.KeyboardModifier.NoModifier

_STATE: dict = {}


def _window():
    if "window" in _STATE:
        return _STATE["window"]
    app = create_app([sys.argv[0]])
    from quartz_studio.modeling import install as mi
    from quartz_studio.main_window import MainWindow

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


def _settle():
    app = _STATE["app"]
    for _ in range(4):
        app.processEvents()


def _pair_mesh() -> Mesh:
    pts = np.array([[-150, -50, 0], [-50, -50, 0], [-50, 50, 0], [-150, 50, 0],
                    [50, -50, 0], [150, -50, 0], [150, 50, 0], [50, 50, 0]], float)
    return Mesh(pts, [(0, 1, 2, 3), (4, 5, 6, 7)], [])


def _setup(tool_id: str, mode: str, mesh: Mesh | None = None, select=None):
    win = _window()
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import get_scene

    scene = get_scene()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_object("Object", Mesh.cube(200.0) if mesh is None else mesh)
    scene._undo.clear()
    scene._redo.clear()
    ctl = mi.controller()
    scene.set_tool("move")
    ctl.activate(None)
    ctl.new_transform()
    scene.set_mode(mode)
    if select is not None:
        scene.select_components(list(select))
    mi.activate_tool(tool_id)
    _settle()
    return win, scene, win.viewport.canvas, ctl


def _qp(xy) -> QPoint:
    return QPoint(int(round(xy[0])), int(round(xy[1])))


def _click(canvas, xy) -> None:
    QTest.mousePress(canvas, LEFT, NO_MOD, _qp(xy))
    QTest.mouseRelease(canvas, LEFT, NO_MOD, _qp(xy))
    _settle()


def _drag(canvas, a, b, steps: int = 5) -> None:
    QTest.mousePress(canvas, LEFT, NO_MOD, _qp(a))
    for k in range(1, steps + 1):
        t = k / steps
        QTest.mouseMove(canvas, _qp((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)))
    QTest.mouseRelease(canvas, LEFT, NO_MOD, _qp(b))
    _settle()


def _screen(canvas, world) -> tuple[float, float]:
    xy = canvas.project_world(np.asarray([world], float))[0]
    return float(round(xy[0])), float(round(xy[1]))


def _vertex_xy(canvas, obj, i: int) -> tuple[float, float]:
    return _screen(canvas, obj.world_points()[i])


def _mid_xy(canvas, obj, a: int, b: int) -> tuple[float, float]:
    pa, pb = _vertex_xy(canvas, obj, a), _vertex_xy(canvas, obj, b)
    return (pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0


def _along_xy(canvas, obj, a: int, b: int, t: float) -> tuple[float, float]:
    pa, pb = _vertex_xy(canvas, obj, a), _vertex_xy(canvas, obj, b)
    return pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t


def _counts(mesh: Mesh) -> tuple[int, int]:
    return len(mesh.points), len(mesh.polygons)


class _Recorder:

    def __init__(self, spec) -> None:
        self.spec = spec
        self.calls: list[dict] = []
        self.original = spec.apply

    def __enter__(self) -> "_Recorder":
        original = self.original

        def apply(mesh, sel, p):
            self.calls.append(dict(p))
            return original(mesh, sel, p)

        self.spec.apply = apply
        return self

    def __exit__(self, *exc) -> None:
        self.spec.apply = self.original

    @property
    def last(self) -> dict:
        return self.calls[-1]


class _Messages:

    def __init__(self, ctl) -> None:
        self.ctl = ctl
        self.items: list[str] = []
        ctl.message.connect(self.items.append)


def _direct(tool_id: str, mesh: Mesh, sel: Selection, params: dict) -> tuple[int, int]:
    return _counts(run_tool(tool_id, mesh, sel, params).mesh)


def test_line_cut_drag_sends_world_values_and_cuts():
    win, scene, canvas, ctl = _setup("line_cut", "polygons")
    obj = scene.active
    ctl.set_param("visible_only", False)
    ctl.set_param("infinite_cut", True)
    with _Recorder(get_tool("line_cut")) as rec:
        _drag(canvas, _screen(canvas, (-150.0, 0.0, 0.0)), _screen(canvas, (150.0, 0.0, 0.0)))
    assert rec.calls, "line cut was never applied"
    params = rec.last
    assert params["start"] is not None and params["end"] is not None
    assert np.allclose(params["object_linear"], np.eye(3))
    assert np.allclose(params["object_position"], [0.0, 0.0, 0.0])
    view = np.asarray(params["view_dir"], float)
    assert abs(float(np.linalg.norm(view)) - 1.0) < 1e-6
    assert np.allclose(view, canvas.view_direction(), atol=1e-6)
    got = _counts(obj.mesh)
    assert got == (12, 10), got


def test_line_cut_click_without_drag_keeps_mesh():
    win, scene, canvas, ctl = _setup("line_cut", "polygons")
    obj = scene.active
    with _Recorder(get_tool("line_cut")) as rec:
        _click(canvas, _screen(canvas, (0.0, 0.0, 0.0)))
    assert not rec.calls
    assert _counts(obj.mesh) == (8, 6)


def test_line_cut_degenerate_line_reports_tool_message():
    win, scene, canvas, ctl = _setup("line_cut", "polygons")
    obj = scene.active
    msgs = _Messages(ctl)
    start = _screen(canvas, (0.0, 0.0, 0.0))
    with _Recorder(get_tool("line_cut")) as rec:
        QTest.mousePress(canvas, LEFT, NO_MOD, _qp(start))
        QTest.mouseMove(canvas, _qp((start[0] + 20, start[1])))
        QTest.mouseMove(canvas, _qp(start))
        QTest.mouseRelease(canvas, LEFT, NO_MOD, _qp(start))
        _settle()
    assert not rec.calls
    assert msgs.items == ["Line Cut: draw a cut line in the viewport first"], msgs.items
    assert _counts(obj.mesh) == (8, 6)


def test_bridge_two_clicks_send_edge_a_then_edge_b():
    win, scene, canvas, ctl = _setup("bridge", "edges", _pair_mesh())
    obj = scene.active
    msgs = _Messages(ctl)
    with _Recorder(get_tool("bridge")) as rec:
        _click(canvas, _mid_xy(canvas, obj, 1, 2))
        assert not rec.calls
        assert _counts(obj.mesh) == (8, 2)
        assert msgs.items == ["Bridge: click the second edge"], msgs.items
        _click(canvas, _mid_xy(canvas, obj, 4, 7))
    assert rec.last["edge_a"] == edge_key(1, 2)
    assert rec.last["edge_b"] == edge_key(4, 7)
    assert _counts(obj.mesh) == (8, 3)


def test_bridge_drag_sends_both_edges():
    win, scene, canvas, ctl = _setup("bridge", "edges", _pair_mesh())
    obj = scene.active
    with _Recorder(get_tool("bridge")) as rec:
        _drag(canvas, _mid_xy(canvas, obj, 1, 2), _mid_xy(canvas, obj, 4, 7))
    assert rec.last["edge_a"] == edge_key(1, 2)
    assert rec.last["edge_b"] == edge_key(4, 7)
    assert _counts(obj.mesh) == (8, 3)


def test_stitch_and_sew_two_clicks_weld_the_chains():
    win, scene, canvas, ctl = _setup("stitch_and_sew", "edges", _pair_mesh())
    obj = scene.active
    with _Recorder(get_tool("stitch_and_sew")) as rec:
        _click(canvas, _mid_xy(canvas, obj, 1, 2))
        _click(canvas, _mid_xy(canvas, obj, 4, 7))
    assert rec.last["edge_a"] == edge_key(1, 2)
    assert rec.last["edge_b"] == edge_key(4, 7)
    assert _counts(obj.mesh) == (6, 2)


def test_weld_click_sends_target_and_merges():
    win, scene, canvas, ctl = _setup("weld", "points", select=[0])
    obj = scene.active
    before, sel = clone(obj.mesh), selection_from_scene(scene)
    with _Recorder(get_tool("weld")) as rec:
        _click(canvas, _vertex_xy(canvas, obj, 1))
    assert rec.last["target"] == 1
    got = _counts(obj.mesh)
    assert got == _direct("weld", before, sel, rec.last), (got, _direct("weld", before, sel, rec.last))
    assert got[0] == 7


def test_weld_click_on_empty_space_reports_and_keeps_mesh():
    win, scene, canvas, ctl = _setup("weld", "points", select=[0])
    obj = scene.active
    msgs = _Messages(ctl)
    with _Recorder(get_tool("weld")) as rec:
        _click(canvas, (30.0, 30.0))
    assert not rec.calls
    assert msgs.items == ["Weld: no point under the cursor"], msgs.items
    assert _counts(obj.mesh) == (8, 6)


def test_mirror_click_sends_plane_origin_in_object_space():
    win, scene, canvas, ctl = _setup("mirror", "points", select=[6])
    obj = scene.active
    obj.position = np.array([30.0, 0.0, 0.0])
    center = _screen(canvas, (30.0, 0.0, 0.0))
    expected_world = canvas.cursor_point(QPointF(*center))
    with _Recorder(get_tool("mirror")) as rec:
        _click(canvas, center)
    origin = np.asarray(rec.last["plane_origin"], float)
    assert np.allclose(origin, expected_world - np.array([30.0, 0.0, 0.0]), atol=1e-3), (origin, expected_world)
    got = _counts(obj.mesh)
    assert got == (9, 6), got


def test_mirror_world_coordinates_send_world_origin_and_matrix():
    win, scene, canvas, ctl = _setup("mirror", "points", select=[0])
    obj = scene.active
    obj.position = np.array([30.0, 0.0, 0.0])
    ctl.set_param("coordinate_system", "World")
    center = _screen(canvas, (30.0, 0.0, 0.0))
    expected_world = canvas.cursor_point(QPointF(*center))
    with _Recorder(get_tool("mirror")) as rec:
        _click(canvas, center)
    assert np.allclose(np.asarray(rec.last["plane_origin"], float), expected_world, atol=1e-3)
    matrix = np.asarray(rec.last["object_matrix"], float)
    assert matrix.shape == (4, 4)
    assert np.allclose(matrix[:3, 3], [30.0, 0.0, 0.0])
    assert np.allclose(matrix[:3, :3], np.eye(3))


def test_plane_cut_local_click_sends_local_plane_position_and_cuts():
    win, scene, canvas, ctl = _setup("plane_cut", "polygons")
    obj = scene.active
    obj.position = np.array([30.0, 0.0, 0.0])
    ctl.set_param("plane", "YZ")
    center = _screen(canvas, (30.0, 0.0, 0.0))
    expected_world = canvas.cursor_point(QPointF(*center))
    with _Recorder(get_tool("plane_cut")) as rec:
        _click(canvas, center)
    assert np.allclose(np.asarray(rec.last["plane_position"], float),
                       expected_world - np.array([30.0, 0.0, 0.0]), atol=1e-3)
    got = _counts(obj.mesh)
    assert got == (12, 10), got


def test_plane_cut_world_click_sends_world_plane_position():
    win, scene, canvas, ctl = _setup("plane_cut", "polygons")
    obj = scene.active
    obj.position = np.array([30.0, 0.0, 0.0])
    ctl.set_param("plane", "YZ")
    ctl.set_param("mode", "World")
    center = _screen(canvas, (30.0, 0.0, 0.0))
    expected_world = canvas.cursor_point(QPointF(*center))
    with _Recorder(get_tool("plane_cut")) as rec:
        _click(canvas, center)
    assert np.allclose(np.asarray(rec.last["plane_position"], float), expected_world, atol=1e-3)
    assert np.allclose(np.asarray(rec.last["object_position"], float), [30.0, 0.0, 0.0])


def test_loop_path_clicks_accumulate_path_edges():
    win, scene, canvas, ctl = _setup("loop_path_cut", "edges")
    obj = scene.active
    ctl.set_param("mode", "Path")
    first, second = edge_key(0, 1), edge_key(1, 5)
    assert first in set(obj.mesh.edges) and second in set(obj.mesh.edges)
    with _Recorder(get_tool("loop_path_cut")) as rec:
        _click(canvas, _mid_xy(canvas, obj, *first))
        _click(canvas, _mid_xy(canvas, obj, *second))
    assert rec.last["edge"] == second
    assert [tuple(e) for e in rec.last["path"]] == [first, second]


def test_viewport_context_supplies_object_and_camera_values():
    win, scene, canvas, ctl = _setup("line_cut", "polygons")
    obj = scene.active
    obj.position = np.array([30.0, 0.0, 0.0])
    filt = win.modeling_filter
    ctx = filt._context(get_tool("line_cut"))
    assert np.allclose(ctx["object_position"], [30.0, 0.0, 0.0])
    assert np.allclose(ctx["object_linear"], np.eye(3))
    flat = filt._context(get_tool("flatten"))
    view = np.asarray(flat["view_direction"], float)
    assert abs(float(np.linalg.norm(view)) - 1.0) < 1e-6
    plane = filt._context(get_tool("plane_cut"))
    rot = np.asarray(plane["camera_rotation"], float)
    assert rot.shape == (3, 3)
    assert np.allclose(rot.T @ rot, np.eye(3), atol=1e-6)
    mirror = filt._context(get_tool("mirror"))
    assert np.asarray(mirror["object_matrix"], float).shape == (4, 4)


NOT_SENT = {("weld", "position"), ("flatten", "modeling_axis")}


def _capture_live(ctl) -> tuple[list, object]:
    sent: list[dict] = []
    original = ctl.apply_live

    def capture(params=None):
        sent.append(dict(params or {}))
        return original(params)

    ctl.apply_live = capture
    return sent, original


def _gesture_keys(tool_id: str) -> set:
    spec = get_tool(tool_id)
    pick = spec.extra.get("pick") if spec.extra else None
    mode = {"edge": "edges", "point": "points"}.get(pick, "polygons")
    mesh = _pair_mesh() if pick in ("edge", "point") else None
    win, scene, canvas, ctl = _setup(tool_id, mode, mesh)
    obj = scene.active
    if spec.param("mode") is not None and "Path" in spec.param("mode").choices:
        ctl.set_param("mode", "Path")
    sent, original = _capture_live(ctl)
    try:
        if pick == "edge":
            _click(canvas, _mid_xy(canvas, obj, 1, 2))
            _click(canvas, _mid_xy(canvas, obj, 4, 7))
        elif pick == "point":
            _click(canvas, _vertex_xy(canvas, obj, 1))
        elif pick == "plane":
            _click(canvas, _screen(canvas, (0.0, 0.0, 0.0)))
        elif pick == "line":
            _drag(canvas, _screen(canvas, (-150.0, 0.0, 0.0)), _screen(canvas, (150.0, 0.0, 0.0)))
        elif spec.drag_param:
            center = _screen(canvas, (0.0, 0.0, 0.0))
            _drag(canvas, center, (center[0] + 40, center[1]))
    finally:
        ctl.apply_live = original
    return set().union(*sent) if sent else set()


def test_every_tool_runtime_param_and_pick_is_handled():
    from quartz_studio.modeling import interaction

    problems = []
    for tool_id in tool_ids():
        spec = get_tool(tool_id)
        pick = spec.extra.get("pick") if spec.extra else None
        if pick is not None and pick not in interaction.PICK_KINDS:
            problems.append(f"{tool_id}: pick {pick!r}")
        for param in spec.params:
            if param.kind == "runtime" and param.key not in interaction.RUNTIME_SOURCES:
                problems.append(f"{tool_id}: runtime {param.key!r}")
    for tool_id in tool_ids():
        spec = get_tool(tool_id)
        expected = {p.key for p in spec.params if p.kind == "runtime"}
        expected -= {key for owner, key in NOT_SENT if owner == tool_id}
        if not expected:
            continue
        missing = expected - _gesture_keys(tool_id)
        if missing:
            problems.append(f"{tool_id}: never sent {sorted(missing)}")
    assert not problems, problems


def test_loop_path_offset_drag_changes_offset():
    win, scene, canvas, ctl = _setup("loop_path_cut", "edges")
    obj = scene.active
    ctl.set_param("mode", "Loop")
    ctl.set_param("offset", 50.0)
    start = _mid_xy(canvas, obj, 0, 1)
    with _Recorder(get_tool("loop_path_cut")) as rec:
        _drag(canvas, start, (start[0] + 60, start[1]))
    assert rec.calls, "offset drag never reached the tool"
    assert abs(float(rec.last["offset"]) - 80.0) < 1e-6, rec.last["offset"]
    assert tuple(rec.last["edge"]) == edge_key(0, 1), rec.last["edge"]


def test_loop_mode_clicks_do_not_accumulate_path():
    win, scene, canvas, ctl = _setup("loop_path_cut", "edges")
    obj = scene.active
    ctl.set_param("mode", "Loop")
    ctl.set_param("path", None)
    with _Recorder(get_tool("loop_path_cut")) as rec:
        _click(canvas, _mid_xy(canvas, obj, *edge_key(0, 1)))
        _click(canvas, _mid_xy(canvas, obj, *edge_key(1, 5)))
    assert rec.calls
    assert rec.last["path"] is None, rec.last["path"]


def test_loop_path_click_off_the_mesh_reports_and_keeps_mesh():
    win, scene, canvas, ctl = _setup("loop_path_cut", "edges")
    obj = scene.active
    msgs = _Messages(ctl)
    with _Recorder(get_tool("loop_path_cut")) as rec:
        _click(canvas, (30.0, 30.0))
    assert not rec.calls
    assert msgs.items == ["Loop/Path Cut: no edge under the cursor"], msgs.items
    assert _counts(obj.mesh) == (8, 6)


def test_stitch_and_sew_same_edge_twice_is_refused():
    win, scene, canvas, ctl = _setup("stitch_and_sew", "edges", _pair_mesh())
    obj = scene.active
    msgs = _Messages(ctl)
    with _Recorder(get_tool("stitch_and_sew")) as rec:
        _click(canvas, _mid_xy(canvas, obj, 1, 2))
        _click(canvas, _mid_xy(canvas, obj, 1, 2))
    assert not rec.calls
    assert msgs.items == ["Stitch and Sew: click the second edge",
                          "Stitch and Sew: pick a different second edge"], msgs.items
    assert _counts(obj.mesh) == (8, 2)


def test_bridge_drag_between_two_points_of_one_edge_is_refused():
    win, scene, canvas, ctl = _setup("bridge", "edges", _pair_mesh())
    obj = scene.active
    msgs = _Messages(ctl)
    with _Recorder(get_tool("bridge")) as rec:
        _drag(canvas, _along_xy(canvas, obj, 1, 2, 0.25), _along_xy(canvas, obj, 1, 2, 0.75))
    assert not rec.calls
    assert msgs.items == ["Bridge: pick a different second edge"], msgs.items
    assert _counts(obj.mesh) == (8, 2)


def test_stitch_and_sew_drag_sends_both_edges():
    win, scene, canvas, ctl = _setup("stitch_and_sew", "edges", _pair_mesh())
    obj = scene.active
    with _Recorder(get_tool("stitch_and_sew")) as rec:
        _drag(canvas, _mid_xy(canvas, obj, 1, 2), _mid_xy(canvas, obj, 4, 7))
    assert rec.last["edge_a"] == edge_key(1, 2)
    assert rec.last["edge_b"] == edge_key(4, 7)
    assert _counts(obj.mesh) == (6, 2)


def test_slide_click_sends_edge_and_edge_position():
    win, scene, canvas, ctl = _setup("slide", "edges", _pair_mesh())
    obj = scene.active
    with _Recorder(get_tool("slide")) as rec:
        _click(canvas, _along_xy(canvas, obj, 1, 2, 0.25))
    assert rec.last["edge"] == edge_key(1, 2), rec.last["edge"]
    assert abs(float(rec.last["edge_position"]) - 25.0) < 3.0, rec.last["edge_position"]


def test_close_polygon_hole_click_sends_border_edge():
    win, scene, canvas, ctl = _setup("close_polygon_hole", "edges", _pair_mesh())
    obj = scene.active
    with _Recorder(get_tool("close_polygon_hole")) as rec:
        _click(canvas, _mid_xy(canvas, obj, 1, 2))
    assert rec.last["edge"] == edge_key(1, 2), rec.last["edge"]


def test_flatten_drag_sends_view_direction_and_strength():
    win, scene, canvas, ctl = _setup("flatten", "polygons")
    ctl.set_param("strength", 0.0)
    center = _screen(canvas, (0.0, 0.0, 0.0))
    with _Recorder(get_tool("flatten")) as rec:
        _drag(canvas, center, (center[0] + 40, center[1]))
    view = np.asarray(rec.last["view_direction"], float)
    assert abs(float(np.linalg.norm(view)) - 1.0) < 1e-6
    assert abs(float(rec.last["strength"]) - 20.0) < 1e-6, rec.last["strength"]


def test_pick_without_active_object_reports_message():
    win, scene, canvas, ctl = _setup("weld", "points")
    for obj in list(scene.objects):
        scene.remove_object(obj)
    _settle()
    msgs = _Messages(ctl)
    _click(canvas, (517.0, 411.0))
    assert msgs.items == ["Weld: select an object first"], msgs.items
    assert ctl.session is None


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
