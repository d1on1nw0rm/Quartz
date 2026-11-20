from __future__ import annotations

from ..scene import get_scene
from . import ik, joints, mathutil, paint, runtime, skin
from .ik import add_ik, remove_ik, solve_all, solve_ccd, solve_ik, solve_two_bone
from .joints import (BIPED_LAYOUT, JOINT_KIND, build_biped, chain_from_selection, create_chain,
                     create_joint, find_joint, is_joint, joint_chain, joint_hierarchy, root_joints)
from .paint import WeightBrush, WeightPainter
from .runtime import RigUpdater, evaluate_rig, updater_for
from .skin import (auto_weights, bind_skin, deform_skin, mirror_weights, paint_weights,
                   rebind_skin, reset_bind_pose, unbind_skin)

__all__ = [
    "JOINT_KIND", "BIPED_LAYOUT",
    "create_joint", "create_chain", "chain_from_selection", "build_biped", "find_joint", "is_joint",
    "joint_chain", "joint_hierarchy", "root_joints",
    "bind_skin", "unbind_skin", "rebind_skin", "auto_weights", "deform_skin", "mirror_weights",
    "paint_weights", "reset_bind_pose",
    "add_ik", "remove_ik", "solve_ik", "solve_all", "solve_two_bone", "solve_ccd",
    "evaluate_rig", "RigUpdater", "updater_for", "WeightBrush", "WeightPainter",
    "commands", "docks", "pages", "key_actions", "last_error",
    "ik", "joints", "mathutil", "paint", "runtime", "skin",
]

MENU = "Character"
DOCK_RIG = "Rig"
DOCK_WEIGHTS = "Weight Paint"
DOCK_JOINTS = "Joints"

_STATE = {"error": ""}


def last_error() -> str:
    return _STATE["error"]


def _scene_arg(args, kwargs):
    scene = kwargs.get("scene")
    if scene is None:
        for a in args:
            if hasattr(a, "objects") and hasattr(a, "changed"):
                scene = a
                break
    return scene if scene is not None else get_scene()


def _command(fn):
    def run(*args, **kwargs):
        scene = _scene_arg(args, kwargs)
        _STATE["error"] = ""
        try:
            return fn(scene)
        except (ValueError, KeyError) as exc:
            _STATE["error"] = str(exc)
            return None

    run.__name__ = fn.__name__
    return run


def _active(scene):
    a = scene.active
    return a if a is not None and a in scene.objects else None


def _cmd_joint(scene):
    a = _active(scene)
    parent = a if joints.is_joint(a) else None
    where = None
    if parent is not None:
        where = mathutil.transform_points(parent.world_matrix(), parent.params.get("tip", (0.0, 0.0, 0.0)))[0]
    return joints.create_joint(scene, "Joint", parent=parent, world_position=where)


def _cmd_chain(scene):
    return joints.chain_from_selection(scene, "Index", True)


def _cmd_chain_nearest(scene):
    return joints.chain_from_selection(scene, "Nearest", True)


def _cmd_bind(scene):
    a = _active(scene)
    if a is None:
        raise ValueError("select the object to bind")
    obj = skin.bind_skin(scene, a)
    runtime.evaluate_rig(scene)
    return obj


def _skinned(scene):
    a = _active(scene)
    if a is None or not skin.is_skinned(a):
        raise ValueError("select a skinned object")
    return a


def _cmd_auto(scene):
    w = skin.auto_weights(scene, _skinned(scene))
    runtime.evaluate_rig(scene)
    return w


def _cmd_unbind(scene):
    return skin.unbind_skin(scene, _skinned(scene))


def _cmd_mirror(scene):
    w = skin.mirror_weights(scene, _skinned(scene))
    runtime.evaluate_rig(scene)
    return w


def _cmd_set_bind(scene):
    return skin.rebind_skin(scene, _skinned(scene))


def _cmd_bind_pose(scene):
    return skin.reset_bind_pose(scene)


def _cmd_add_ik(scene):
    end = _active(scene)
    if not joints.is_joint(end):
        raise ValueError("select the end joint of the IK chain")
    parent = joints.joint_parent(end)
    if parent is None:
        raise ValueError(f"{end.name} has no parent joint")
    start = joints.joint_parent(parent) or parent
    tag = ik.add_ik(scene, start, end)
    runtime.evaluate_rig(scene)
    return tag


def _cmd_remove_ik(scene):
    a = _active(scene)
    for start, tag in ik.ik_tags(scene):
        if start is a or tag.get("end") == getattr(a, "name", None):
            return ik.remove_ik(scene, start, True)
    raise ValueError("the selected joint has no IK")


def _cmd_biped(scene):
    made = joints.build_biped(scene)
    runtime.evaluate_rig(scene)
    return made


def _cmd_biped_ik(scene):
    made = joints.build_biped(scene, with_ik=True)
    runtime.evaluate_rig(scene)
    return made


def _cmd_update(scene):
    return runtime.evaluate_rig(scene)


def _cmd_live(scene):
    u = runtime.updater_for(scene)
    u.set_enabled(not u.is_enabled())
    return u.is_enabled()


def _cmd_orient(scene):
    a = _active(scene)
    targets = joints.joint_hierarchy(scene, a) if joints.is_joint(a) else None
    return joints.orient_joints(scene, targets)


def _cmd_align(scene):
    return joints.update_bone_display(scene)


_COMMANDS = (
    (("Joint",), _cmd_joint),
    (("Joint Chain from Points",), _cmd_chain),
    (("Joint Chain from Points (Nearest Order)",), _cmd_chain_nearest),
    (("Orient Joints",), _cmd_orient),
    (("Align Bone Display",), _cmd_align),
    (("Skin", "Bind Skin"), _cmd_bind),
    (("Skin", "Auto Weights"), _cmd_auto),
    (("Skin", "Mirror Weights"), _cmd_mirror),
    (("Skin", "Set Bind Pose"), _cmd_set_bind),
    (("Skin", "Go to Bind Pose"), _cmd_bind_pose),
    (("Skin", "Unbind Skin"), _cmd_unbind),
    (("IK", "Add IK"), _cmd_add_ik),
    (("IK", "Remove IK"), _cmd_remove_ik),
    (("Presets", "Biped Skeleton"), _cmd_biped),
    (("Presets", "Biped Skeleton with IK"), _cmd_biped_ik),
    (("Update Rig",), _cmd_update),
    (("Live Rig Update",), _cmd_live),
)


def commands() -> list:
    return [((MENU,) + path, _command(fn)) for path, fn in _COMMANDS]


def _factory(cls_name: str):
    def make(scene=None, parent=None):
        from . import widgets
        cls = getattr(widgets, cls_name)
        return cls(scene, parent)

    make.__name__ = f"make_{cls_name}"
    return make


def docks() -> list:
    return [
        (DOCK_RIG, _factory("RigPanel"), "right"),
        (DOCK_WEIGHTS, _factory("WeightPaintPanel"), "right"),
        (DOCK_JOINTS, _factory("JointList"), "left"),
    ]


def pages() -> list:
    return [("Rigging", [DOCK_JOINTS, DOCK_RIG, DOCK_WEIGHTS])]


def key_actions() -> list:
    return [
        ("rig.update", "Update Rig", _command(_cmd_update)),
        ("rig.live", "Live Rig Update", _command(_cmd_live)),
        ("rig.joint", "Create Joint", _command(_cmd_joint)),
    ]
