from __future__ import annotations

import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

APP = QApplication.instance() or QApplication([sys.argv[0]])

from quartz_studio import rig
from quartz_studio.ext import store
from quartz_studio.modeling import primitives as prim
from quartz_studio.objects import registry as objreg
from quartz_studio.rig import ik, joints as jt, mathutil as mu, runtime, skin as sk
from quartz_studio.rig.paint import WeightBrush, WeightPainter
from quartz_studio.scene import Mesh, reset_scene, rotation_matrix


def _scene():
    s = reset_scene()
    return s


def _limb(scene, segments: int = 12, height: float = 200.0, radius: float = 20.0):
    chain = jt.create_chain(scene, [(0, 0, 0), (0, height / 2, 0), (0, height, 0)])
    mesh = prim.cylinder(radius, height, segments, 12)
    obj = scene.add_object("Limb", mesh)
    obj.position = np.array([0.0, height / 2, 0.0])
    obj = sk.bind_skin(scene, obj, chain)
    return chain, obj


def _close(a, b, tol=1e-6) -> bool:
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol, rtol=0.0))


def test_euler_round_trip_matches_scene_convention():
    rng = np.random.default_rng(3)
    for _ in range(50):
        ang = rng.uniform(-170, 170, 3)
        ang[1] = rng.uniform(-80, 80)
        m = rotation_matrix(ang)
        back = mu.euler_from_matrix(m)
        assert _close(rotation_matrix(back), m, 1e-9)
    gimbal = rotation_matrix((10.0, 90.0, 0.0))
    assert _close(rotation_matrix(mu.euler_from_matrix(gimbal)), gimbal, 1e-9)


def test_quaternion_round_trip_and_slerp():
    rng = np.random.default_rng(5)
    for _ in range(30):
        m = rotation_matrix(rng.uniform(-180, 180, 3))
        assert _close(mu.matrix_from_quat(mu.quat_from_matrix(m)), m, 1e-9)
    a = mu.quat_from_matrix(np.eye(3))
    b = mu.quat_from_matrix(mu.axis_angle_matrix((0, 0, 1), math.pi / 2))
    mid = mu.matrix_from_quat(mu.quat_slerp(a, b, 0.5))
    assert _close(mid, mu.axis_angle_matrix((0, 0, 1), math.pi / 4), 1e-9)
    assert _close(mu.matrix_from_quat(mu.quat_slerp(a, b, 0.0)), np.eye(3), 1e-9)
    assert _close(mu.matrix_from_quat(mu.quat_slerp(a, b, 1.0)), mu.matrix_from_quat(b), 1e-9)


def test_arc_and_aim_matrices():
    u = np.array([1.0, 2.0, -0.5])
    v = np.array([-3.0, 0.2, 1.0])
    r = mu.arc_matrix(u, v)
    assert _close(r @ mu.normalize(u), mu.normalize(v), 1e-9)
    assert abs(np.linalg.det(r) - 1.0) < 1e-9
    flip = mu.arc_matrix((1, 0, 0), (-1, 0, 0))
    assert _close(flip @ np.array([1.0, 0, 0]), (-1, 0, 0), 1e-9)
    aim = mu.aim_matrix((0, 0, 5))
    assert _close(aim[:, 0], (0, 0, 1)) and _close(aim.T @ aim, np.eye(3), 1e-12)
    vertical = mu.aim_matrix((0, 3, 0))
    assert _close(vertical[:, 0], (0, 1, 0)) and abs(np.linalg.det(vertical) - 1) < 1e-12


def test_joint_kind_registered_with_glyph():
    spec = objreg.get("joint")
    assert spec.category == "null" and spec.inputs == "none"
    bone = jt.joint_glyph((0, 50, 0), 4.0)
    assert len(bone.points) == 6 and len(bone.loose_edges) == 12 and not bone.polygons
    assert _close(bone.points[5], (0, 50, 0))
    assert _close(bone.points[0], (0, 0, 0))
    ring = bone.points[1:5]
    assert _close(ring[:, 1], [9.0] * 4)
    assert _close(np.linalg.norm(ring - (0, 9, 0), axis=1), [4.0] * 4)
    diamond = jt.joint_glyph((0, 0, 0), 3.0)
    assert len(diamond.points) == 6 and len(diamond.loose_edges) == 12
    assert _close(np.abs(diamond.points).max(), 3.0)
    axis = jt.joint_glyph((10, 0, 0), 2.0, "Axis")
    assert len(axis.loose_edges) == 4
    assert len(jt.joint_glyph((1, 0, 0), 2.0, "None").points) == 0


def test_create_joint_world_position_and_parent():
    s = _scene()
    root = jt.create_joint(s, "Root", world_position=(10, 20, 30))
    assert root.kind == "joint" and _close(root.world_position(), (10, 20, 30))
    root.rotation = np.array([0.0, 0.0, 90.0])
    child = jt.create_joint(s, "Child", parent=root, world_position=(10, 70, 30))
    assert child.parent is root
    assert _close(child.world_position(), (10, 70, 30))
    assert _close(child.position, (50, 0, 0), 1e-9)
    assert len(root.mesh.points) == 6


def test_create_chain_orient_and_tips():
    s = _scene()
    pts = [(0, 0, 0), (0, 100, 0), (50, 150, 0), (50, 150, 80)]
    chain = jt.create_chain(s, pts, name="Arm")
    assert [j.name for j in chain] == ["Arm1", "Arm2", "Arm3", "Arm4"]
    for j, p in zip(chain, pts):
        assert _close(j.world_position(), p, 1e-9)
    assert chain[0].parent is None and all(chain[i].parent is chain[i - 1] for i in range(1, 4))
    for i in range(3):
        x_axis = chain[i].world_matrix()[:3, 0]
        assert _close(x_axis, mu.normalize(np.subtract(pts[i + 1], pts[i])), 1e-9)
        assert _close(chain[i].params["tip"], chain[i + 1].position, 1e-9)
        assert abs(chain[i].params["tip"][1]) < 1e-12 and abs(chain[i].params["tip"][2]) < 1e-12
    assert _close(chain[3].world_matrix()[:3, :3], chain[2].world_matrix()[:3, :3], 1e-9)
    flat = jt.create_chain(s, pts, name="Flat", orient=False)
    assert all(_close(j.rotation, (0, 0, 0)) for j in flat)
    assert _close(flat[1].params["tip"], np.subtract(pts[2], pts[1]))
    assert jt.joint_chain(chain[0], chain[3]) == chain
    assert jt.joint_chain(chain[2], chain[0]) is None
    assert jt.joint_hierarchy(s, chain[1]) == chain[1:]
    assert {r.name for r in jt.root_joints(s)} == {"Arm1", "Flat1"}


def test_build_joints_rejects_bad_parent_order():
    s = _scene()
    try:
        jt.build_joints(s, [{"name": "A", "position": (0, 0, 0), "parent": 1},
                            {"name": "B", "position": (0, 1, 0), "parent": None}])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_create_chain_is_one_undo_step():
    s = _scene()
    count = len(s.objects)
    jt.create_chain(s, [(0, 0, 0), (0, 10, 0), (0, 20, 0)])
    assert len(s.objects) == count + 3
    s.undo()
    assert len(s.objects) == count


def test_order_points_nearest_walk():
    pts = np.array([[0, 0, 0], [30, 0, 0], [10, 0, 0], [20, 0, 0], [99, 99, 99]], float)
    assert jt.order_points(pts, [0, 1, 2, 3], "Index") == [0, 1, 2, 3]
    walk = jt.order_points(pts, [0, 1, 2, 3], "Nearest")
    assert walk in ([0, 2, 3, 1], [1, 3, 2, 0])


def test_chain_from_selected_points():
    s = _scene()
    line = s.add_object("Path", Mesh([(0, 0, 0), (0, 40, 0), (0, 80, 10)], [], [(0, 1), (1, 2)]))
    line.position = np.array([5.0, 0.0, 0.0])
    s.set_mode("points")
    s.select_components([0, 1, 2])
    made = jt.chain_from_selection(s, "Index")
    assert len(made) == 3
    assert _close(made[2].world_position(), (5, 80, 10))
    s.set_active(line)
    s.clear_selection()
    try:
        jt.chain_from_selection(s)
    except ValueError:
        pass
    else:
        raise AssertionError("empty selection must fail")


def test_update_bone_display_and_orient_joints():
    s = _scene()
    chain = jt.create_chain(s, [(0, 0, 0), (0, 50, 0), (0, 100, 0)], orient=False)
    chain[1].position = np.array([30.0, 50.0, 0.0])
    assert jt.update_bone_display(s) >= 1
    assert _close(chain[0].params["tip"], (30, 50, 0))
    before = [j.world_position() for j in chain]
    jt.orient_joints(s)
    after = [j.world_position() for j in chain]
    assert all(_close(a, b, 1e-9) for a, b in zip(before, after))
    assert _close(chain[0].world_matrix()[:3, 0], mu.normalize(before[1] - before[0]), 1e-9)
    assert _close(chain[1].world_matrix()[:3, 0], mu.normalize(before[2] - before[1]), 1e-9)


def test_mirror_names():
    assert jt.mirror_name("L_Hand") == "R_Hand"
    assert jt.mirror_name("R_Foot") == "L_Foot"
    assert jt.mirror_name("arm_L") == "arm_R"
    assert jt.mirror_name("hand.R") == "hand.L"
    assert jt.mirror_name("LeftArm") == "RightArm"
    assert jt.mirror_name("Spine") == "Spine"


def test_biped_preset_structure():
    s = _scene()
    b = jt.build_biped(s, height=200.0)
    assert len(b) == len(jt.BIPED_LAYOUT) == 22
    for name in ("Hips", "Spine1", "Spine2", "Spine3", "Neck", "Head", "L_UpperArm", "R_ForeArm",
                 "L_Hand", "R_Hand", "L_Thigh", "R_Shin", "L_Foot", "R_Foot"):
        assert name in b, name
    assert jt.joint_chain(b["Hips"], b["L_Hand"]) is not None
    assert jt.joint_chain(b["Hips"], b["R_Toe"]) is not None
    assert _close(b["Hips"].world_position(), (0, 106, 0), 1e-9)
    assert abs(b["Head"].world_position()[1] - 174.0) < 1e-9
    for name in ("Hand", "Foot", "ForeArm", "Shin", "Clavicle"):
        l, r = b["L_" + name].world_position(), b["R_" + name].world_position()
        assert _close(l * (-1, 1, 1), r, 1e-9)
    assert b["L_Hand"].world_position()[0] < 0 < b["R_Hand"].world_position()[0]
    tip = np.asarray(b["Head"].params["tip"])
    assert abs(np.linalg.norm(tip) - 26.0) < 1e-6
    head_tip_world = mu.transform_points(b["Head"].world_matrix(), tip)[0]
    assert head_tip_world[1] > b["Head"].world_position()[1] + 20


def test_biped_with_ik_creates_goals():
    s = _scene()
    b = jt.build_biped(s, with_ik=True)
    tags = ik.ik_tags(s)
    assert {start.name for start, _t in tags} == {"L_Thigh", "R_Thigh", "L_UpperArm", "R_UpperArm"}
    goal = next(o for o in s.objects if o.name == "L_Foot Goal")
    pole = next(o for o in s.objects if o.name == "L_Foot Pole")
    assert pole.world_position()[2] < b["L_Shin"].world_position()[2]
    runtime.evaluate_rig(s)
    assert _close(b["L_Foot"].world_position(), goal.world_position(), 1e-6)
    jt.set_world_position(goal, goal.world_position() + np.array([0.0, 30.0, -20.0]))
    runtime.evaluate_rig(s)
    assert _close(b["L_Foot"].world_position(), goal.world_position(), 1e-6)
    assert b["L_Shin"].world_position()[2] < goal.world_position()[2] + 1e-6


def test_segment_distances_numeric():
    pts = np.array([[0, 5, 0], [3, 0, 4], [0, -2, 0], [0, 12, 0]], float)
    d = sk.segment_distances(pts, [(0, 0, 0)], [(0, 10, 0)])
    assert _close(d[:, 0], [0, 5, 2, 2])
    point_seg = sk.segment_distances(pts, [(0, 0, 0)], [(0, 0, 0)])
    assert _close(point_seg[:, 0], np.linalg.norm(pts, axis=1))


def test_auto_weights_normalised_and_limited():
    pts = np.array([[1, y, 0] for y in np.linspace(0, 200, 21)], float)
    segs = [[(np.array([0, 0, 0.]), np.array([0, 100, 0.]))],
            [(np.array([0, 100, 0.]), np.array([0, 200, 0.]))],
            [(np.array([0, 200, 0.]), np.array([0, 200, 0.]))]]
    w = sk.compute_auto_weights(pts, segs, falloff=4.0, max_influences=2)
    assert w.shape == (21, 3)
    assert _close(w.sum(axis=1), np.ones(21), 1e-12)
    assert ((w > 0).sum(axis=1) <= 2).all()
    assert w[2, 0] > 0.95 and w[17, 1] > 0.6
    assert abs(w[10, 0] - w[10, 1]) < 0.2
    sharp = sk.compute_auto_weights(pts, segs, falloff=12.0, max_influences=3)
    soft = sk.compute_auto_weights(pts, segs, falloff=1.0, max_influences=3)
    assert sharp[5, 0] > soft[5, 0]


def test_bind_skin_stores_contract():
    s = _scene()
    chain, obj = _limb(s)
    skin = store.get_object(obj, "skin")
    assert skin["joints"] == [j.name for j in chain]
    assert skin["bind_matrices"].shape == (3, 4, 4)
    assert skin["weights"].shape == (len(obj.mesh.points), 3)
    assert _close(skin["weights"].sum(axis=1), np.ones(len(obj.mesh.points)), 1e-9)
    assert _close(skin["bind_points"], obj.mesh.points)
    assert _close(skin["object_bind_matrix"], obj.world_matrix())
    js = store.from_json(store.to_json(skin))
    assert _close(js["weights"], skin["weights"]) and js["joints"] == skin["joints"]
    low = obj.mesh.points[:, 1] < -60
    high = obj.mesh.points[:, 1] > 60
    assert (skin["weights"][low, 0] > 0.6).all()
    assert (skin["weights"][high, 1] + skin["weights"][high, 2] > 0.6).all()


def test_bind_requires_joints_and_points():
    s = _scene()
    cube = s.objects[0]
    try:
        sk.bind_skin(s, cube)
    except ValueError:
        pass
    else:
        raise AssertionError("bind without joints must fail")
    j = jt.create_joint(s, "J")
    try:
        sk.bind_skin(s, j, [j])
    except ValueError:
        pass
    else:
        raise AssertionError("joint cannot be skinned")


def test_bind_parametric_object_makes_it_editable():
    s = _scene()
    j = jt.create_chain(s, [(0, -100, 0), (0, 100, 0)])
    sphere = s.add_parametric("sphere")
    bound = sk.bind_skin(s, sphere, j)
    assert bound.kind == "polygon" and sk.is_skinned(bound)
    assert bound in s.objects and sphere not in s.objects


def test_deform_identity_at_bind_pose():
    s = _scene()
    _chain, obj = _limb(s)
    before = obj.mesh.points.copy()
    assert not sk.deform_skin(s, obj)
    runtime.evaluate_rig(s)
    assert _close(obj.mesh.points, before, 1e-9)


def test_rigid_weight_follows_joint_exactly():
    s = _scene()
    chain, obj = _limb(s)
    n = len(obj.mesh.points)
    w = np.zeros((n, 3))
    w[:, 1] = 1.0
    sk.apply_weights(s, obj, w)
    bind_world = obj.world_points().copy()
    b1 = chain[1].world_matrix()
    chain[1].rotation = chain[1].rotation + np.array([0.0, 0.0, 40.0])
    assert sk.deform_skin(s, obj)
    m = chain[1].world_matrix() @ np.linalg.inv(b1)
    assert _close(obj.world_points(), mu.transform_points(m, bind_world), 1e-6)


def test_linear_blend_mixes_two_joints():
    p = np.array([[1.0, 2.0, 3.0]])
    a = np.eye(4)
    a[:3, 3] = (10, 0, 0)
    b = np.eye(4)
    b[:3, 3] = (0, 20, 0)
    out = sk.linear_blend(p, np.array([a, b]), np.array([[0.25, 0.75]]))
    assert _close(out[0], (1 + 2.5, 2 + 15, 3))
    rest = sk.linear_blend(p, np.array([a, b]), np.array([[0.5, 0.0]]))
    assert _close(rest[0], (6, 2, 3))


def test_dual_quaternion_preserves_volume_against_linear():
    p = np.array([[0.0, 10.0, 0.0]])
    rot = np.eye(4)
    rot[:3, :3] = mu.axis_angle_matrix((1, 0, 0), math.radians(170))
    mats = np.array([np.eye(4), rot])
    w = np.array([[0.5, 0.5]])
    lin = sk.linear_blend(p, mats, w)
    dq = sk.dual_quaternion_blend(p, mats, w)
    assert np.linalg.norm(lin[0]) < 2.0
    assert abs(np.linalg.norm(dq[0]) - 10.0) < 1e-9
    single = sk.dual_quaternion_blend(p, mats, np.array([[0.0, 1.0]]))
    assert _close(single[0], mu.transform_points(rot, p)[0], 1e-9)
    moved = np.eye(4)
    moved[:3, :3] = mu.axis_angle_matrix((0, 1, 0), 0.7)
    moved[:3, 3] = (3, -4, 5)
    pts = np.random.default_rng(1).normal(size=(10, 3))
    assert _close(sk.dual_quaternion_blend(pts, np.array([moved]), np.ones((10, 1))),
                  mu.transform_points(moved, pts), 1e-9)


def test_dual_quaternion_skin_method_in_scene():
    s = _scene()
    chain, obj = _limb(s)
    sk.set_skin_method(s, obj, "Dual Quaternion")
    assert sk.skin_of(obj)["method"] == "Dual Quaternion"
    chain[1].rotation = chain[1].rotation + np.array([0.0, 0.0, 90.0])
    assert sk.deform_skin(s, obj)
    assert np.isfinite(obj.mesh.points).all()


def test_root_motion_moves_mesh_once_even_when_parented():
    s = _scene()
    chain, obj = _limb(s)
    s.set_parent(obj, chain[0])
    bind_world = obj.world_points().copy()
    chain[0].position = chain[0].position + np.array([50.0, 0.0, 0.0])
    sk.deform_skin(s, obj)
    assert _close(obj.world_points(), bind_world + (50, 0, 0), 1e-6)


def test_zero_weight_points_stay_in_bind_pose():
    s = _scene()
    chain, obj = _limb(s)
    sk.apply_weights(s, obj, np.zeros_like(sk.skin_of(obj)["weights"]))
    before = obj.world_points().copy()
    chain[0].rotation = np.array([0.0, 30.0, 0.0])
    sk.deform_skin(s, obj)
    assert _close(obj.world_points(), before, 1e-9)


def test_bent_limb_keeps_upper_part_and_moves_tip():
    s = _scene()
    chain, obj = _limb(s)
    pts = sk.skin_of(obj)["bind_points"]
    chain[1].rotation = chain[1].rotation + np.array([0.0, 0.0, 90.0])
    runtime.evaluate_rig(s)
    world = obj.world_points()
    bottom = pts[:, 1] < -80
    top = pts[:, 1] > 90
    assert _close(world[bottom], mu.transform_points(obj.world_matrix(), pts[bottom]), 1.0)
    tip = chain[2].world_position()
    assert np.linalg.norm(world[top].mean(axis=0) - tip) < 25.0
    assert np.linalg.norm(world[top].mean(axis=0) - (0, 200, 0)) > 60.0


def test_unbind_restores_and_rebind_updates():
    s = _scene()
    chain, obj = _limb(s)
    original = obj.mesh.points.copy()
    chain[1].rotation = chain[1].rotation + np.array([0.0, 0.0, 45.0])
    sk.deform_skin(s, obj)
    assert not _close(obj.mesh.points, original, 1e-3)
    assert sk.rebind_skin(s, obj)
    posed = obj.mesh.points.copy()
    assert _close(sk.skin_of(obj)["bind_points"], posed)
    assert not sk.deform_skin(s, obj)
    assert sk.unbind_skin(s, obj)
    assert store.get_object(obj, "skin") is None
    assert _close(obj.mesh.points, posed)
    assert not sk.unbind_skin(s, obj)


def test_unbind_restores_original_points():
    s = _scene()
    chain, obj = _limb(s)
    original = obj.mesh.points.copy()
    chain[0].rotation = chain[0].rotation + np.array([20.0, 0.0, 0.0])
    sk.deform_skin(s, obj)
    sk.unbind_skin(s, obj)
    assert _close(obj.mesh.points, original)


def test_reset_bind_pose_restores_joint_matrices():
    s = _scene()
    chain, obj = _limb(s)
    mats = [j.world_matrix() for j in chain]
    chain[0].rotation = chain[0].rotation + np.array([10.0, 20.0, 30.0])
    chain[2].position = chain[2].position * 1.5
    assert sk.reset_bind_pose(s) == 3
    assert all(_close(j.world_matrix(), m, 1e-9) for j, m in zip(chain, mats))
    assert _close(obj.mesh.points, sk.skin_of(obj)["bind_points"], 1e-9)


def test_topology_change_disables_deform():
    s = _scene()
    chain, obj = _limb(s)
    obj.mesh.add_point((0, 0, 0))
    chain[1].rotation = chain[1].rotation + np.array([0.0, 0.0, 30.0])
    assert not sk.deform_skin(s, obj)


def test_skin_survives_undo_snapshot():
    s = _scene()
    _chain, obj = _limb(s)
    jt.create_joint(s, "Extra")
    s.undo()
    restored = next(o for o in s.objects if o.name == "Limb")
    assert sk.is_skinned(restored)


def test_brush_falloff_shapes():
    d = np.array([0.0, 5.0, 10.0, 12.0])
    assert _close(sk.brush_falloff(d, 10.0, "Smooth"), [1.0, 0.5625, 0.0, 0.0])
    assert _close(sk.brush_falloff(d, 10.0, "Linear"), [1.0, 0.5, 0.0, 0.0])
    assert _close(sk.brush_falloff(d, 10.0, "Constant"), [1.0, 1.0, 1.0, 0.0])
    assert _close(sk.brush_falloff(d, 0.0), [0, 0, 0, 0])
    assert _close(sk.cylinder_distances([(3, 4, 7)], (0, 0, 0), (0, 0, 1)), [5.0])


def test_paint_add_subtract_replace_normalise():
    w = np.array([[0.5, 0.5, 0.0], [0.2, 0.3, 0.5], [1.0, 0.0, 0.0]])
    f = np.array([1.0, 1.0, 0.0])
    add = sk.paint_weights(w, 2, f, "Add", 0.5)
    assert _close(add.sum(axis=1), [1, 1, 1])
    assert _close(add[0], [0.25, 0.25, 0.5]) and _close(add[1], [0.0, 0.0, 1.0])
    assert _close(add[2], w[2])
    sub = sk.paint_weights(w, 0, f, "Subtract", 0.4)
    assert _close(sub[0], [0.1, 0.9, 0.0]) and abs(sub[1, 0]) < 1e-12
    assert _close(sub[1, 1:] / sub[1, 1:].sum(), [0.375, 0.625]) and _close(sub[1].sum(), 1)
    lone = sk.paint_weights(np.array([[1.0, 0.0]]), 0, np.array([1.0]), "Subtract", 1.0)
    assert _close(lone, [[1.0, 0.0]])
    rep = sk.paint_weights(w, 1, f, "Replace", 0.3)
    assert _close(rep[:2, 1], [0.3, 0.3]) and _close(rep.sum(axis=1), [1, 1, 1])
    raw = sk.paint_weights(w, 2, f, "Add", 0.5, normalize=False)
    assert _close(raw[0], [0.5, 0.5, 0.5])
    norm = sk.paint_weights(raw, 0, f, "Normalize")
    assert _close(norm[0], [1 / 3, 1 / 3, 1 / 3])
    half = sk.paint_weights(w, 2, np.array([0.5, 0.0, 0.0]), "Add", 1.0)
    assert _close(half[0], [0.25, 0.25, 0.5])
    try:
        sk.paint_weights(w, 0, f, "Bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown mode must fail")


def test_paint_smooth_reduces_contrast():
    mesh = Mesh([(i, 0, 0) for i in range(5)], [], [(i, i + 1) for i in range(4)])
    w = np.array([[1, 0], [1, 0], [0, 1], [0, 1], [0, 1]], float)
    adj = sk.adjacency(mesh)
    out = sk.paint_weights(w, 0, np.ones(5), "Smooth", 1.0, True, adj)
    assert _close(out.sum(axis=1), np.ones(5))
    assert 0.0 < out[1, 0] < 1.0 and 0.0 < out[2, 0] < 1.0
    assert np.abs(np.diff(out[:, 0])).max() < 1.0
    sm = sk.smooth_weights(w, adj, 3, 0.5)
    assert np.abs(np.diff(sm[:, 0])).max() < np.abs(np.diff(w[:, 0])).max()


def test_prune_and_limit():
    w = np.array([[0.7, 0.2, 0.06, 0.04], [0.02, 0.98, 0.0, 0.0]])
    p = sk.prune_weights(w, 0.05)
    assert p[0, 3] == 0.0 and p[1, 0] == 0.0
    assert _close(p.sum(axis=1), [1, 1])
    lim = sk.normalize_weights(sk.limit_influences(w, 2))
    assert ((lim > 0).sum(axis=1) <= 2).all()
    assert _close(lim[0], [0.7 / 0.9, 0.2 / 0.9, 0, 0])


def test_mirror_weights_matrix():
    pts = np.array([[-10, 0, 0], [10, 0, 0], [-10, 5, 0], [10, 5, 0], [0, 9, 0]], float)
    names = ["L_Arm", "R_Arm", "Spine"]
    w = np.array([[0.9, 0.0, 0.1], [0.0, 0.0, 1.0], [0.6, 0.4, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])
    m = sk.mirror_weight_matrix(pts, w, names, axis=0)
    assert _close(m[1], [0.0, 0.9, 0.1]) and _close(m[3], [0.4, 0.6, 0.0])
    assert _close(m[0], w[0]) and _close(m[4], w[4])
    back = sk.mirror_weight_matrix(pts, m, names, axis=0, positive_to_negative=True)
    assert _close(back[0], w[0]) and _close(back[2], w[2])


def test_mirror_weights_on_biped_mesh():
    s = _scene()
    b = jt.build_biped(s, height=180.0)
    body = s.add_object("Body", prim.cube((120.0, 180.0, 30.0), (6, 8, 2)))
    body.position = np.array([0.0, 90.0, 0.0])
    body = sk.bind_skin(s, body, list(b.values()))
    w = sk.mirror_weights(s, body)
    skin = sk.skin_of(body)
    names = skin["joints"]
    pts = skin["bind_points"]
    li = names.index("L_Hand")
    ri = names.index("R_Hand")
    for i, p in enumerate(pts):
        if p[0] > 1.0:
            j = int(np.argmin(np.linalg.norm(pts - p * (-1, 1, 1), axis=1)))
            assert abs(w[i, ri] - w[j, li]) < 1e-9


def test_weight_painter_strokes_and_undo():
    s = _scene()
    chain, obj = _limb(s)
    painter = WeightPainter(s, WeightBrush(joint=2, mode="Add", radius=40.0, strength=1.0))
    assert painter.set_target(obj)
    before = painter.weights().copy()
    center = obj.world_points()[0]
    assert painter.begin_stroke()
    assert painter.dab_sphere(center)
    assert painter.dab_sphere(center + (0, 5, 0))
    assert painter.end_stroke()
    after = painter.weights()
    near = np.linalg.norm(obj.world_points() - center, axis=1) < 10.0
    assert (after[near, 2] > before[near, 2]).all()
    assert _close(after.sum(axis=1), np.ones(len(after)), 1e-9)
    assert painter.can_undo() and painter.undo()
    assert _close(painter.weights(), before)
    assert not painter.undo()
    painter.brush.mode = "Replace"
    painter.brush.strength = 0.0
    assert painter.flood()
    assert _close(painter.weights()[:, 2], 0.0)
    assert painter.limit(1)
    assert ((painter.weights() > 0).sum(axis=1) == 1).all()
    assert painter.smooth_all(2, 0.5)
    assert painter.prune(0.2)
    assert not painter.set_target(chain[0])


def test_weight_painting_redeforms_posed_mesh():
    s = _scene()
    chain, obj = _limb(s)
    chain[1].rotation = chain[1].rotation + np.array([0.0, 0.0, 60.0])
    runtime.evaluate_rig(s)
    posed = obj.mesh.points.copy()
    painter = WeightPainter(s, WeightBrush(joint=0, mode="Replace", radius=1000.0, strength=1.0,
                                           falloff="Constant"))
    painter.set_target(obj)
    painter.flood()
    assert not _close(obj.mesh.points, posed, 1e-3)
    assert _close(obj.mesh.points, sk.skin_of(obj)["bind_points"], 1e-6)


def test_two_bone_solver_reaches_with_pole():
    a, b, c = np.zeros(3), np.array([0, 50.0, 0]), np.array([0, 100.0, 0])
    target = np.array([30.0, 60.0, 0.0])
    out = solve = ik.solve_two_bone(a, b, c, target, pole=np.array([0, 50.0, 100.0]))
    assert _close(out[2], target, 1e-9)
    assert abs(np.linalg.norm(out[1] - out[0]) - 50) < 1e-9
    assert abs(np.linalg.norm(out[2] - out[1]) - 50) < 1e-9
    assert out[1][2] > 1.0
    other = ik.solve_two_bone(a, b, c, target, pole=np.array([0, 50.0, -100.0]))
    assert other[1][2] < -1.0
    far = ik.solve_two_bone(a, b, c, np.array([300.0, 0, 0]))
    assert _close(far[2], (100, 0, 0), 1e-9) and _close(far[1], (50, 0, 0), 1e-9)
    twisted = ik.solve_two_bone(a, b, c, target, pole=np.array([0, 50.0, 100.0]), twist=180.0)
    assert twisted[1][2] < -1.0 and _close(twisted[2], target, 1e-9)
    assert solve is out


def test_ccd_reaches_target_and_keeps_lengths():
    pts = np.array([[0, 0, 0], [0, 40, 0], [0, 80, 0], [0, 120, 0], [0, 160, 0]], float)
    target = np.array([60.0, 90.0, 30.0])
    out = ik.solve_ccd(pts, target, iterations=200, tolerance=1e-4, pole=np.array([0, 80.0, 100.0]))
    assert np.linalg.norm(out[-1] - target) < 1e-3
    assert _close(np.linalg.norm(np.diff(out, axis=0), axis=1), [40] * 4, 1e-9)
    assert _close(out[0], pts[0])
    aligned = ik.align_to_pole(out, np.array([0.0, 50.0, 200.0]))
    assert _close(aligned[-1], out[-1], 1e-9)
    axis = mu.normalize(aligned[-1] - aligned[0])
    perp = np.zeros(3)
    for p in aligned[1:-1]:
        v = p - aligned[0]
        perp += v - (v @ axis) * axis
    want = np.array([0.0, 50.0, 200.0]) - aligned[0]
    want = want - (want @ axis) * axis
    assert float(mu.normalize(perp) @ mu.normalize(want)) > 0.999


def test_solve_ik_on_scene_chain():
    s = _scene()
    chain = jt.create_chain(s, [(0, 0, 0), (0, 50, 0.5), (0, 100, 0)])
    tag = ik.add_ik(s, chain[0], chain[2], solver="Two Bone")
    goal = next(o for o in s.objects if o.name == tag["goal"])
    pole = next(o for o in s.objects if o.name == tag["pole"])
    assert _close(goal.world_position(), chain[2].world_position(), 1e-9)
    jt.set_world_position(goal, (40, 60, 0))
    jt.set_world_position(pole, (0, 50, 80))
    err = ik.solve_ik(s, chain[0])
    assert err is not None and err < 1e-6
    assert _close(chain[2].world_position(), (40, 60, 0), 1e-6)
    assert abs(np.linalg.norm(chain[1].world_position() - chain[0].world_position()) - math.hypot(50, 0.5)) < 1e-6
    assert chain[1].world_position()[2] > 1.0
    ccd = ik.set_ik(s, chain[0], solver="CCD", iterations=100, tolerance=1e-5)
    assert ccd["solver"] == "CCD"
    err = ik.solve_ik(s, chain[0])
    assert err < 1e-3


def test_long_chain_ik_with_goal():
    s = _scene()
    chain = jt.create_chain(s, [(0, 30.0 * i, 0) for i in range(6)])
    tag = ik.add_ik(s, chain[0], chain[-1], iterations=200, tolerance=1e-4)
    goal = next(o for o in s.objects if o.name == tag["goal"])
    jt.set_world_position(goal, (50, 80, 40))
    err = ik.solve_ik(s, chain[0])
    assert err < 1e-2
    lengths = [np.linalg.norm(chain[i + 1].world_position() - chain[i].world_position()) for i in range(5)]
    assert _close(lengths, [30] * 5, 1e-6)


def test_fk_ik_blend():
    s = _scene()
    chain = jt.create_chain(s, [(0, 0, 0), (0, 50, 1), (0, 100, 0)])
    tag = ik.add_ik(s, chain[0], chain[2], create_pole=False)
    goal = next(o for o in s.objects if o.name == tag["goal"])
    fk_end = chain[2].world_position().copy()
    jt.set_world_position(goal, (60, 40, 0))
    ik.solve_ik(s, chain[0])
    ik_end = chain[2].world_position().copy()
    assert _close(ik_end, (60, 40, 0), 1e-6)
    ik.set_ik(s, chain[0], blend=0.5)
    ik.solve_ik(s, chain[0])
    half = chain[2].world_position()
    assert np.linalg.norm(half - fk_end) > 1.0 and np.linalg.norm(half - ik_end) > 1.0
    ik.set_ik(s, chain[0], blend=0.0)
    assert ik.solve_ik(s, chain[0]) is None
    chain[1].rotation = chain[1].rotation + np.array([0.0, 0.0, 15.0])
    ik.solve_ik(s, chain[0])
    fk = ik.ik_tag(chain[0])["fk"]
    assert _close(fk[chain[1].name], chain[1].rotation)
    out = ik.blend_rotations([(0, 0, 0)], [(0, 0, 90)], 0.5)
    assert _close(out[0], (0, 0, 45), 1e-9)


def test_match_goal_rotation_and_remove_ik():
    s = _scene()
    chain = jt.create_chain(s, [(0, 0, 0), (0, 50, 1), (0, 100, 0)])
    fk = [j.rotation.copy() for j in chain]
    tag = ik.add_ik(s, chain[0], chain[2], match_goal_rotation=True)
    goal = next(o for o in s.objects if o.name == tag["goal"])
    goal.rotation = np.array([10.0, 20.0, 30.0])
    jt.set_world_position(goal, (30, 70, 10))
    ik.solve_ik(s, chain[0])
    assert _close(chain[2].world_matrix()[:3, :3], rotation_matrix((10, 20, 30)), 1e-9)
    count = len(s.objects)
    assert ik.remove_ik(s, chain[0], delete_targets=True)
    assert ik.ik_tag(chain[0]) is None
    assert len(s.objects) == count - 2
    assert all(_close(j.rotation, r) for j, r in zip(chain, fk))
    assert not ik.remove_ik(s, chain[0])


def test_add_ik_validates_chain():
    s = _scene()
    a = jt.create_chain(s, [(0, 0, 0), (0, 10, 0)])
    b = jt.create_chain(s, [(5, 0, 0), (5, 10, 0)], name="Other")
    try:
        ik.add_ik(s, a[0], b[1])
    except ValueError:
        pass
    else:
        raise AssertionError("unrelated joints must fail")


def test_evaluate_rig_drives_skin_through_ik():
    s = _scene()
    chain, obj = _limb(s)
    tag = ik.add_ik(s, chain[0], chain[2])
    goal = next(o for o in s.objects if o.name == tag["goal"])
    jt.set_world_position(goal, (80, 120, 0))
    result = runtime.evaluate_rig(s)
    assert result["ik"] == 1 and result["deformed"] == 1 and result["moved"]
    top = sk.skin_of(obj)["bind_points"][:, 1] > 95
    assert np.linalg.norm(obj.world_points()[top].mean(axis=0) - (80, 120, 0)) < 30.0
    again = runtime.evaluate_rig(s)
    assert again["deformed"] == 0 and not again["moved"]


def test_rig_updater_live_and_terminates():
    s = _scene()
    chain, obj = _limb(s)
    tag = ik.add_ik(s, chain[0], chain[2])
    goal = next(o for o in s.objects if o.name == tag["goal"])
    u = runtime.updater_for(s)
    assert u is runtime.updater_for(s)
    u.set_enabled(True)
    runs = u.runs
    jt.set_world_position(goal, (60, 100, 20))
    s.changed.emit()
    assert u.runs > runs and u.runs - runs < 10
    assert _close(chain[2].world_position(), (60, 100, 20), 1e-6)
    u.set_enabled(False)
    runs = u.runs
    s.changed.emit()
    assert u.runs == runs


def test_commands_docks_pages_contract():
    cmds = rig.commands()
    assert cmds and all(isinstance(p, tuple) and p[0] == "Character" and callable(fn) for p, fn in cmds)
    paths = [p for p, _fn in cmds]
    assert len(set(paths)) == len(paths)
    assert ("Character", "Skin", "Bind Skin") in paths
    assert ("Character", "Presets", "Biped Skeleton") in paths
    titles = [t for t, _f, _a in rig.docks()]
    assert titles == ["Rig", "Weight Paint", "Joints"]
    assert all(area in ("left", "right", "bottom") for _t, _f, area in rig.docks())
    layouts = rig.pages()
    assert layouts[0][0] == "Rigging" and set(layouts[0][1]) == set(titles)
    assert all(callable(fn) for _id, _label, fn in rig.key_actions())


def test_commands_run_end_to_end():
    s = _scene()
    run = dict(rig.commands())
    made = run[("Character", "Presets", "Biped Skeleton with IK")]()
    assert made and len(ik.ik_tags(s)) == 4
    body = s.add_object("Body", Mesh.cube(100))
    body.position = np.array([0.0, 100.0, 0.0])
    s.set_active(body)
    bound = run[("Character", "Skin", "Bind Skin")]()
    assert bound is not None and sk.is_skinned(bound)
    assert run[("Character", "Skin", "Auto Weights")]() is not None
    assert run[("Character", "Skin", "Mirror Weights")]() is not None
    assert run[("Character", "Skin", "Set Bind Pose")]()
    assert run[("Character", "Update Rig")]()["ik"] == 4
    assert run[("Character", "Skin", "Go to Bind Pose")]() > 0
    assert run[("Character", "Skin", "Unbind Skin")]()
    s.set_active(made["L_Hand"])
    joint = run[("Character", "Joint",)]()
    assert joint.parent is made["L_Hand"]
    assert run[("Character", "Align Bone Display",)]() >= 0
    assert run[("Character", "Orient Joints",)]() > 0
    s.set_active(made["Head"])
    assert run[("Character", "IK", "Add IK")]() is not None
    assert run[("Character", "IK", "Remove IK")]()
    s.set_active(s.objects[0])
    assert run[("Character", "Skin", "Unbind Skin")]() is None and rig.last_error()
    assert run[("Character", "Live Rig Update",)]() is True
    assert run[("Character", "Live Rig Update",)]() is False


def test_rig_panel_drives_everything():
    from quartz_studio.rig.widgets import RigPanel
    s = _scene()
    panel = RigPanel(s)
    panel.resize(320, 900)
    assert panel.build_biped()
    assert panel.ik_start.count() == 22
    assert len(ik.ik_tags(s)) == 4
    panel.ik_start.setCurrentText("L_Thigh")
    assert panel.ik_end.currentText() == "L_Foot"
    panel.ik_blend.setValue(50.0)
    assert abs(ik.ik_tag(jt.find_joint(s, "L_Thigh"))["blend"] - 0.5) < 1e-9
    panel.ik_solver.setCurrentText("CCD")
    assert ik.ik_tag(jt.find_joint(s, "L_Thigh"))["solver"] == "CCD"
    panel.ik_twist.setValue(10.0)
    panel.ik_iterations.setValue(40)
    panel.ik_match.setChecked(True)
    tag = ik.ik_tag(jt.find_joint(s, "L_Thigh"))
    assert tag["twist"] == 10.0 and tag["iterations"] == 40 and tag["match_goal_rotation"]
    assert panel.remove_ik()
    panel.ik_start.setCurrentText("L_Thigh")
    panel.ik_end.setCurrentText("L_Foot")
    assert panel.add_ik() is not None
    assert panel.store_fk() is not None
    assert panel.solve()["ik"] == 4
    body = s.add_object("Body", Mesh.cube(100))
    body.position = np.array([0.0, 100.0, 0.0])
    s.set_active(body)
    panel.skeleton.setCurrentText("Hips")
    panel.influences.setValue(3)
    assert panel.bind() is not None
    w = sk.skin_of(body)["weights"]
    assert ((w > 0).sum(axis=1) <= 3).all() and w.shape[1] == 22
    panel.method.setCurrentText("Dual Quaternion")
    assert sk.skin_of(body)["method"] == "Dual Quaternion"
    assert panel.auto_weights() is not None
    assert panel.mirror() is not None
    assert panel.set_bind_pose()
    assert panel.reset_pose() is not None
    assert panel.unbind()
    s.set_active(jt.find_joint(s, "Head"))
    j = panel.create_joint()
    assert j.parent is jt.find_joint(s, "Head")
    assert panel.align_bones() is not None
    assert panel.orient_joints() is not None
    line = s.add_object("Path", Mesh([(0, 0, 0), (10, 0, 0), (20, 5, 0)], [], [(0, 1), (1, 2)]))
    s.set_mode("points")
    s.select_components([0, 1, 2])
    panel.joint_radius.setValue(2.0)
    made = panel.chain_from_points()
    assert len(made) == 3 and made[0].params["radius"] == 2.0
    s.set_mode("model")
    panel.live.setChecked(True)
    assert panel.updater.is_enabled()
    panel.live.setChecked(False)
    assert not panel.updater.is_enabled()
    s.set_active(line)
    assert panel.unbind() is False and panel.status.text()
    assert not panel.grab().isNull()


def test_joint_list_widget():
    from quartz_studio.rig.widgets import JointList
    s = _scene()
    b = jt.build_biped(s, with_ik=True)
    lst = JointList(s)
    lst.resize(256, 512)
    assert lst.tree.topLevelItemCount() == 1
    assert len(lst._items) == 22
    item = lst.item_for(b["L_Thigh"])
    assert "IK" in item.text(1)
    lst.tree.setCurrentItem(lst.item_for(b["L_Hand"]))
    assert s.active is b["L_Hand"]
    s.set_active(b["Neck"])
    assert lst.selected_joint() is b["Neck"]
    lst.filter.setText("hand")
    assert not lst.item_for(b["L_Hand"]).isHidden() and lst.item_for(b["Neck"]).isHidden()
    assert not lst.item_for(b["Hips"]).isHidden()
    lst.filter.setText("")
    body = s.add_object("Body", Mesh.cube(100))
    body = sk.bind_skin(s, body, list(b.values()))
    lst.refresh()
    s.set_active(b["L_Foot"])
    lst.item_for(b["L_Foot"]).setText(0, "LeftFoot")
    assert b["L_Foot"].name == "LeftFoot"
    assert "LeftFoot" in sk.skin_of(body)["joints"]
    assert ik.ik_tag(b["L_Thigh"])["end"] == "LeftFoot"
    assert "LeftFoot" in ik.ik_tag(b["L_Thigh"])["fk"]
    runtime.evaluate_rig(s)
    assert ik.chain_of(s, b["L_Thigh"]) is not None
    lst.tree.setCurrentItem(lst.item_for(b["Head"]))
    child = lst.add_child()
    assert child.parent is b["Head"]
    assert len(lst._items) == 23
    lst.tree.setCurrentItem(lst.item_for(child))
    assert lst.delete_joint()
    assert len(lst._items) == 22
    assert not lst.grab().isNull()


def test_weight_paint_panel_and_preview():
    from quartz_studio.rig.widgets import WeightPaintPanel, weight_color
    s = _scene()
    chain, obj = _limb(s)
    s.set_active(obj)
    panel = WeightPaintPanel(s)
    panel.resize(320, 900)
    panel.show()
    APP.processEvents()
    assert panel.painter.target is obj
    assert panel.joint_combo.count() == 3
    s.set_active(chain[2])
    assert panel.joint_combo.currentIndex() == 2 and panel.brush.joint == 2
    panel.mode.setCurrentText("Replace")
    panel.strength.setValue(100.0)
    panel.radius.setValue(15.0)
    panel.falloff.setCurrentText("Constant")
    assert panel.brush.mode == "Replace" and panel.brush.strength == 1.0 and panel.brush.radius == 15.0
    before = panel.painter.weights().copy()
    prev = panel.preview
    prev.resize(256, 256)
    center = QPoint(prev.width() // 2, prev.height() // 2)
    QTest.mousePress(prev, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
    QTest.mouseMove(prev, center + QPoint(4, 8))
    QTest.mouseRelease(prev, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center + QPoint(4, 8))
    after = panel.painter.weights()
    assert not np.array_equal(before, after)
    assert (after[:, 2] >= before[:, 2] - 1e-12).all() and after[:, 2].max() == 1.0
    assert panel.undo() and _close(panel.painter.weights(), before)
    QTest.mousePress(prev, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, center)
    QTest.mouseMove(prev, center + QPoint(32, 16))
    QTest.mouseRelease(prev, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, center + QPoint(32, 16))
    assert prev.yaw != 0.0 or prev.pitch != 0.0
    img = prev.grab().toImage()
    assert not img.isNull() and img.width() == 256
    colors = {img.pixel(x, y) for x in range(0, 256, 4) for y in range(0, 256, 4)}
    assert len(colors) > 3
    assert panel.flood()
    assert _close(panel.painter.weights()[:, 2], 1.0)
    assert panel.undo()
    assert panel.smooth_all()
    panel.threshold.setValue(30.0)
    assert panel.prune() in (True, False)
    panel.limit_count.setValue(1)
    assert panel.limit()
    assert panel.normalize_all() in (True, False)
    assert "points" in panel.info.text()
    assert weight_color(0.0) != weight_color(1.0)
    panel.viewport_toggle.setChecked(True)
    assert not panel.viewport_toggle.isChecked()
    s.set_active(s.objects[0])
    assert not panel.pick_active()
    panel.close()


class _FakeCanvas:
    pass


def test_weight_paint_controller_with_canvas():
    from PySide6.QtWidgets import QWidget
    from quartz_studio.rig.widgets import WeightPaintController, WeightPaintPanel
    s = _scene()
    chain, obj = _limb(s)
    s.set_active(obj)
    panel = WeightPaintPanel(s)

    class Canvas(QWidget):
        def ray_at(self, pos):
            return np.array([200.0, 100.0, 0.0]), np.array([-1.0, 0.0, 0.0])

        def raycast(self, origin, direction, objects=None):
            return s.raycast(origin, direction, objects)

    canvas = Canvas()
    ctl = panel.attach_canvas(canvas)
    assert isinstance(ctl, WeightPaintController)
    panel.joint_combo.setCurrentIndex(0)
    panel.mode.setCurrentText("Replace")
    panel.strength.setValue(100.0)
    panel.radius.setValue(10.0)
    assert panel.set_viewport_paint(True) and ctl.enabled
    before = panel.painter.weights().copy()
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    move = QMouseEvent(QEvent.Type.MouseMove, QPointF(6, 6), QPointF(6, 6), Qt.MouseButton.NoButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(6, 6), QPointF(6, 6), Qt.MouseButton.LeftButton,
                          Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    assert ctl.eventFilter(canvas, press)
    assert ctl.eventFilter(canvas, move)
    assert ctl.eventFilter(canvas, release)
    after = panel.painter.weights()
    hit_zone = np.linalg.norm(obj.world_points() - (20.0, 100.0, 0.0), axis=1) <= 10.0
    assert hit_zone.any() and _close(after[hit_zone, 0], 1.0)
    assert _close(after[~hit_zone], before[~hit_zone])
    assert panel.painter.can_undo()
    alt = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier)
    assert not ctl.eventFilter(canvas, alt)
    panel.set_viewport_paint(False)
    assert not ctl.eventFilter(canvas, press)
    ctl.detach()
    assert ctl.canvas is None


def test_dock_factories_build_widgets():
    s = _scene()
    for title, factory, _area in rig.docks():
        w = factory(s)
        w.resize(320, 640)
        assert not w.grab().isNull(), title
        w.deleteLater()
    APP.processEvents()


def _strip(scene, nx: int = 8, ny: int = 3):
    mesh = prim.plane(100.0, 20.0, nx, ny)
    obj = scene.add_object("Strip", mesh)
    obj.rotation = np.array([90.0, 0.0, 0.0])
    obj.position = np.array([50.0, 0.0, 0.0])
    js = jt.create_chain(scene, [(0, 0, 0), (50, 0, 0), (100, 0, 0)])
    obj = sk.bind_skin(scene, obj, js)
    return js, obj


def test_regression_skinned_project_saves_to_native_format():
    import tempfile
    from quartz_studio.fileio import bridge, fmt_quartz
    s = _scene()
    js, obj = _strip(s)
    ik.add_ik(s, js[0], js[-1])
    raw = obj.extras[data_key()]
    assert isinstance(raw["weights"], dict) and "__ndarray__" in raw["weights"]
    assert not any(isinstance(v, np.ndarray) for v in raw.values())
    js[1].rotation = np.array([0.0, 0.0, 30.0])
    runtime.evaluate_rig(s)
    weights = sk.skin_of(obj)["weights"].copy()
    bind_pts = sk.skin_of(obj)["bind_points"].copy()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "rig.qz")
        fmt_quartz.save(path, bridge.full_document_from_scene(s), {})
        doc = fmt_quartz.load(path)
    s2 = _scene()
    bridge.replace_scene(s2, doc)
    loaded = next(o for o in s2.objects if o.name == "Strip")
    skin = sk.skin_of(loaded)
    assert skin is not None and skin["joints"] == [j.name for j in js]
    assert _close(skin["weights"], weights, 1e-12) and _close(skin["bind_points"], bind_pts, 1e-12)
    assert skin["bind_matrices"].shape == (3, 4, 4)
    start = jt.find_joint(s2, js[0].name)
    assert ik.ik_tag(start) is not None and ik.chain_of(s2, start) is not None
    s.clear_history()
    sk.apply_weights(s, obj, weights)
    assert len(s._undo) == 0
    sk.apply_weights(s, obj, np.roll(weights, 1, axis=1))
    assert len(s._undo) == 1


def data_key() -> str:
    from quartz_studio.rig import data
    return data.SKIN_KEY


def _blend_chain(s):
    js = jt.create_chain(s, [(0, 0, 0), (30, 0, 0), (60, 0, 0), (90, 0, 0)])
    js[1].rotation = np.array([0.0, 0.0, 20.0])
    fk = [j.rotation.copy() for j in js]
    tag = ik.add_ik(s, js[0], js[-1])
    goal = next(o for o in s.objects if o.name == tag["goal"])
    return js, fk, tag, goal


def test_regression_blend_zero_restores_fk_pose():
    s = _scene()
    js, fk, tag, goal = _blend_chain(s)
    goal.position = np.array([20.0, 50.0, 0.0])
    ik.solve_ik(s, js[0])
    solved = [j.rotation.copy() for j in js]
    assert not all(_close(a, b, 1e-3) for a, b in zip(solved, fk))
    ik.set_ik(s, js[0], blend=0.0)
    ik.solve_ik(s, js[0])
    assert all(_close(j.rotation, r, 1e-9) for j, r in zip(js, fk))
    ik.solve_ik(s, js[0])
    assert all(_close(j.rotation, r, 1e-9) for j, r in zip(js, fk))
    ik.set_ik(s, js[0], blend=1.0)
    ik.solve_ik(s, js[0])
    assert all(_close(j.rotation, r, 1e-6) for j, r in zip(js, solved))
    assert ik.remove_ik(s, js[0])
    assert all(_close(j.rotation, r, 1e-9) for j, r in zip(js, fk))


def test_regression_missing_goal_restores_fk_pose():
    s = _scene()
    js, fk, tag, goal = _blend_chain(s)
    goal.position = np.array([20.0, 50.0, 0.0])
    ik.solve_ik(s, js[0])
    s.remove_object(goal)
    assert ik.solve_ik(s, js[0]) is None
    assert all(_close(j.rotation, r, 1e-9) for j, r in zip(js, fk))
    js[2].rotation = np.array([0.0, 0.0, -10.0])
    ik.solve_ik(s, js[0])
    assert _close(js[2].rotation, (0, 0, -10), 1e-9)
    assert _close(ik.ik_tag(js[0])["fk"][js[2].name], (0, 0, -10), 1e-9)
    assert ik.remove_ik(s, js[0])
    assert _close(js[2].rotation, (0, 0, -10), 1e-9) and _close(js[1].rotation, fk[1], 1e-9)


def test_regression_remove_ik_after_solve_restores_fk():
    s = _scene()
    js, fk, tag, goal = _blend_chain(s)
    goal.position = np.array([10.0, 60.0, 0.0])
    for _ in range(3):
        ik.solve_ik(s, js[0])
    assert ik.remove_ik(s, js[0])
    assert all(_close(j.rotation, r, 1e-9) for j, r in zip(js, fk))


def test_regression_rename_joint_is_one_undo_step():
    from quartz_studio.rig.widgets import rename_joint
    s = _scene()
    js, obj = _strip(s)
    names = [j.name for j in js]
    s.clear_history()
    assert rename_joint(s, js[0], "Root") == "Root"
    assert len(s._undo) == 1
    assert sk.skin_of(obj)["joints"] == ["Root"] + names[1:]
    assert s.undo()
    joint_names = [o.name for o in s.objects if jt.is_joint(o)]
    obj2 = next(o for o in s.objects if o.name == "Strip")
    assert joint_names == names
    assert sk.skin_of(obj2)["joints"] == names
    assert all(j is not None for j in sk.skin_joints(s, sk.skin_of(obj2)))
    assert s.redo()
    obj3 = next(o for o in s.objects if o.name == "Strip")
    assert sk.skin_of(obj3)["joints"] == ["Root"] + names[1:]
    assert s._group_depth == 0


def test_regression_rename_joint_keeps_names_unique():
    from quartz_studio.rig.widgets import rename_joint
    s = _scene()
    js, obj = _strip(s)
    got = rename_joint(s, js[2], js[0].name)
    assert got != js[0].name and js[2].name == got
    names = [o.name for o in s.objects]
    assert len(names) == len(set(names))
    joints = sk.skin_of(obj)["joints"]
    assert len(set(joints)) == 3 and joints[2] == got
    assert sk.skin_joints(s, sk.skin_of(obj)) == js
    assert rename_joint(s, js[1], "   ") == js[1].name


def test_regression_external_rename_keeps_references():
    s = _scene()
    guard = runtime.guard_for(s)
    js, obj = _strip(s)
    tag = ik.add_ik(s, js[0], js[-1])
    goal = next(o for o in s.objects if o.name == tag["goal"])
    s.rename_object(goal, "Hand Target")
    s.rename_object(js[1], "Elbow")
    assert ik.ik_tag(js[0])["goal"] == "Hand Target"
    assert sk.skin_of(obj)["joints"][1] == "Elbow"
    assert "Elbow" in ik.ik_tag(js[0])["fk"]
    goal.position = np.array([40.0, 60.0, 0.0])
    err = ik.solve_ik(s, js[0])
    assert err is not None and err < 1e-2
    assert guard.fixed >= 2


def test_regression_mirror_weights_memory_and_time():
    import time
    import tracemalloc
    s = _scene()
    b = jt.build_biped(s, height=180.0)
    sheet = s.add_object("Sheet", prim.plane(120.0, 180.0, 139, 139))
    sheet.rotation = np.array([90.0, 0.0, 0.0])
    sheet.position = np.array([0.0, 90.0, 0.0])
    sheet = sk.bind_skin(s, sheet, list(b.values()), smooth=0)
    assert len(sheet.mesh.points) == 19600
    tracemalloc.start()
    t0 = time.perf_counter()
    w = sk.mirror_weights(s, sheet)
    took = time.perf_counter() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 200 * 1024 * 1024, peak
    assert took < 3.0, took
    assert _close(w.sum(axis=1), np.ones(len(w)), 1e-9)


def test_regression_mirror_uses_skeleton_plane_in_world_space():
    s = _scene()
    off = 40.0
    b = jt.build_biped(s, height=180.0, origin=(off, 0.0, 0.0))
    body = s.add_object("Body", prim.cube((120.0, 180.0, 30.0), (6, 8, 2)))
    body.position = np.array([off + 20.0, 90.0, 0.0])
    body.rotation = np.array([0.0, 180.0, 0.0])
    body = sk.bind_skin(s, body, list(b.values()))
    skin0 = sk.skin_of(body)
    assert abs(sk.mirror_plane(skin0) - off) < 1e-9
    w = sk.mirror_weights(s, body)
    skin = sk.skin_of(body)
    names = skin["joints"]
    world = mu.transform_points(skin["object_bind_matrix"], skin["bind_points"])
    li, ri = names.index("L_Hand"), names.index("R_Hand")
    checked = 0
    for i, p in enumerate(world):
        if p[0] - off > 1.0:
            q = p.copy()
            q[0] = 2 * off - q[0]
            d = np.linalg.norm(world - q, axis=1)
            j = int(np.argmin(d))
            if d[j] < 1e-6:
                assert abs(w[i, ri] - w[j, li]) < 1e-9
                assert abs(w[i, li] - w[j, ri]) < 1e-9
                checked += 1
    assert checked > 10


def test_regression_nearest_within_matches_brute_force():
    rng = np.random.default_rng(11)
    src = rng.uniform(-50, 50, (400, 3))
    q = rng.uniform(-50, 50, (300, 3))
    best, dist = sk.nearest_within(q, src, 12.0)
    full = np.linalg.norm(q[:, None, :] - src[None, :, :], axis=2)
    for i in range(len(q)):
        k = int(np.argmin(full[i]))
        if full[i, k] <= 12.0:
            assert best[i] == k and abs(dist[i] - full[i, k]) < 1e-12
        else:
            assert best[i] == -1 and np.isinf(dist[i])


def test_regression_painter_undo_survives_scene_undo():
    s = _scene()
    chain, obj = _limb(s)
    painter = WeightPainter(s, WeightBrush(joint=2, mode="Replace", radius=1000.0, strength=1.0,
                                           falloff="Constant"))
    painter.set_target(obj)
    before = painter.weights().copy()
    assert painter.flood()
    other = s.add_object("Other", Mesh.cube(10))
    other_name = other.name
    assert s.undo()
    assert all(o.name != other_name for o in s.objects)
    assert painter.valid() and painter.target in s.objects
    assert painter.undo()
    assert _close(painter.weights(), before)
    assert _close(sk.skin_of(next(o for o in s.objects if o.name == "Limb"))["weights"], before)


def test_regression_open_stroke_does_not_swallow_other_edits():
    s = _scene()
    chain, obj = _limb(s)
    painter = WeightPainter(s, WeightBrush(joint=2, mode="Add", radius=40.0, strength=1.0))
    painter.set_target(obj)
    s.clear_history()
    before = painter.weights().copy()
    assert painter.begin_stroke()
    assert s._group_depth == 0
    painter.dab_sphere(obj.world_points()[0])
    s.add_object("A", Mesh.cube(5))
    s.add_object("B", Mesh.cube(5))
    assert painter.end_stroke()
    assert len(s._undo) == 3
    assert s.undo()
    limb = next(o for o in s.objects if o.name == "Limb")
    assert _close(sk.skin_of(limb)["weights"], before)
    assert {"A", "B"} <= {o.name for o in s.objects}


def test_regression_joint_list_info_follows_scene_changed():
    from quartz_studio.rig.widgets import JointList
    s = _scene()
    js = jt.create_chain(s, [(0, 0, 0), (50, 0, 0), (100, 0, 0)])
    lst = JointList(s)
    APP.processEvents()
    assert lst.item_for(js[0]).text(1) == ""
    body = s.add_object("Body", Mesh.cube(50))
    body = s.make_editable(body) if body.kind != "polygon" else body
    APP.processEvents()
    sk.bind_skin(s, body, js)
    APP.processEvents()
    assert "skins 1" in lst.item_for(js[0]).text(1)
    ik.add_ik(s, js[0], js[2], create_goal=False, create_pole=False)
    ik.set_ik(s, js[0], blend=0.5)
    APP.processEvents()
    assert "IK to" in lst.item_for(js[0]).text(1)
    sk.unbind_skin(s, body)
    APP.processEvents()
    assert "skins" not in lst.item_for(js[0]).text(1)


def test_regression_weight_paint_tools_report_status():
    from quartz_studio.rig.widgets import WeightPaintPanel
    s = _scene()
    chain, obj = _limb(s)
    s.set_active(obj)
    panel = WeightPaintPanel(s)
    APP.processEvents()
    panel.say("No viewport found")
    assert panel.flood()
    assert panel.status.text().startswith("Flood")
    panel.say("No viewport found")
    panel.normalize_all()
    assert panel.status.text().startswith("Normalize All")
    for fn, label in ((panel.smooth_all, "Smooth All"), (panel.prune, "Prune"),
                      (panel.limit, "Limit Influences")):
        panel.say("stale")
        fn()
        assert panel.status.text().startswith(label), panel.status.text()


def test_regression_bind_pose_survives_ik_evaluation():
    s = _scene()
    b = jt.build_biped(s, height=180.0, with_ik=True)
    body = s.add_object("Body", prim.cube((120.0, 180.0, 30.0), (4, 6, 2)))
    body.position = np.array([0.0, 90.0, 0.0])
    body = sk.bind_skin(s, body, list(b.values()))
    skin = sk.skin_of(body)
    bind = {n: m for n, m in zip(skin["joints"], skin["bind_matrices"])}
    b["L_UpperArm"].rotation = b["L_UpperArm"].rotation + np.array([0.0, 0.0, -40.0])
    b["L_Thigh"].rotation = b["L_Thigh"].rotation + np.array([25.0, 0.0, 0.0])
    for start, _tag in ik.ik_tags(s):
        ik.store_fk(s, start)
    runtime.evaluate_rig(s)
    assert not _close(b["L_Thigh"].world_matrix(), bind["L_Thigh"], 1e-3)
    assert sk.reset_bind_pose(s) == len(b)
    runtime.evaluate_rig(s)
    runtime.evaluate_rig(s)
    for name, m in bind.items():
        assert _close(jt.find_joint(s, name).world_matrix(), m, 1e-6), name
    assert _close(body.mesh.points, sk.skin_of(body)["bind_points"], 1e-6)


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
