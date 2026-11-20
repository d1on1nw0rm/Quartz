from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np

from ..scene import SceneObject
from . import data
from . import joints as jt
from . import mathutil as mu

__all__ = [
    "SOLVERS",
    "ik_tag",
    "ik_tags",
    "add_ik",
    "remove_ik",
    "set_ik",
    "store_fk",
    "chain_of",
    "solve_two_bone",
    "solve_ccd",
    "align_to_pole",
    "apply_positions",
    "blend_rotations",
    "solve_ik",
    "solve_all",
]

SOLVERS = ("Auto", "Two Bone", "CCD")

_SOLVER_ALIASES = {"auto": "Auto", "two_bone": "Two Bone", "twobone": "Two Bone", "two bone": "Two Bone",
                   "ccd": "CCD"}


def _solver_name(name: str) -> str:
    if name in SOLVERS:
        return name
    return _SOLVER_ALIASES.get(str(name).lower(), "Auto")


def ik_tag(joint: SceneObject) -> dict | None:
    value = data.read(joint, data.IK_KEY)
    return value if isinstance(value, dict) else None


def ik_tags(scene) -> list[tuple[SceneObject, dict]]:
    out = []
    for o in scene.objects:
        if jt.is_joint(o):
            tag = ik_tag(o)
            if tag is not None:
                out.append((o, tag))
    return out


def _find(scene, name: str | None) -> SceneObject | None:
    if not name:
        return None
    for o in scene.objects:
        if o.name == name:
            return o
    return None


def chain_of(scene, start: SceneObject, tag: dict | None = None) -> list[SceneObject] | None:
    tag = ik_tag(start) if tag is None else tag
    if tag is None:
        return None
    end = jt.find_joint(scene, tag.get("end", ""))
    if end is None:
        return None
    return jt.joint_chain(start, end)


def _fk_of(chain: Sequence[SceneObject]) -> dict:
    return {j.name: [float(v) for v in j.rotation] for j in chain}


def _bend_hint(chain: Sequence[SceneObject], side: np.ndarray | None) -> np.ndarray:
    pts = np.array([j.world_position() for j in chain])
    axis = mu.normalize(pts[-1] - pts[0])
    if side is not None:
        s = np.asarray(side, float)
        perp = s - (s @ axis) * axis
        if np.linalg.norm(perp) > mu.EPS:
            return mu.normalize(perp)
    offs = np.zeros(3)
    for p in pts[1:-1]:
        v = p - pts[0]
        offs += v - (v @ axis) * axis
    if np.linalg.norm(offs) > mu.EPS:
        return mu.normalize(offs)
    return mu.perpendicular(axis)


def _make_null(scene, name: str, world: np.ndarray, display: str, radius: float) -> SceneObject:
    obj = scene.add_parametric("null", name, activate=False)
    obj.params["display"] = display
    obj.params["radius"] = float(radius)
    obj._dirty = True
    jt.set_world_position(obj, world)
    return obj


def add_ik(scene, start: SceneObject, end: SceneObject, solver: str = "Auto",
           goal: SceneObject | None = None, pole: SceneObject | None = None,
           create_goal: bool = True, create_pole: bool = True, blend: float = 1.0,
           iterations: int = 24, tolerance: float = 0.01, pole_side: Iterable[float] | None = None,
           match_goal_rotation: bool = False, twist: float = 0.0) -> dict:
    if not (jt.is_joint(start) and jt.is_joint(end)):
        raise ValueError("IK needs a start joint and an end joint")
    chain = jt.joint_chain(start, end)
    if chain is None or len(chain) < 2:
        raise ValueError(f"{end.name} is not below {start.name}")
    pts = np.array([j.world_position() for j in chain])
    length = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
    size = max(length * 0.04, 0.5)
    scene.begin_group()
    try:
        if goal is None and create_goal:
            goal = _make_null(scene, f"{end.name} Goal", pts[-1], "Cube", size)
        if pole is None and create_pole and len(chain) >= 3:
            side = None if pole_side is None else np.asarray(tuple(pole_side), float)
            hint = _bend_hint(chain, side)
            mid = pts[len(pts) // 2]
            pole = _make_null(scene, f"{end.name} Pole", mid + hint * max(length * 0.5, 1.0),
                              "Diamond", size)
        tag = {
            "end": end.name,
            "goal": goal.name if goal is not None else "",
            "pole": pole.name if pole is not None else "",
            "solver": _solver_name(solver),
            "blend": float(np.clip(blend, 0.0, 1.0)),
            "iterations": int(max(1, iterations)),
            "tolerance": float(max(1e-6, tolerance)),
            "match_goal_rotation": bool(match_goal_rotation),
            "twist": float(twist),
            "enabled": True,
            "fk": _fk_of(chain),
        }
        data.write(scene, start, data.IK_KEY, tag)
        scene.evaluate()
    finally:
        scene.end_group()
    scene.objectsChanged.emit()
    scene.changed.emit()
    return tag


def remove_ik(scene, start: SceneObject, delete_targets: bool = False, restore_fk: bool = True) -> bool:
    tag = ik_tag(start)
    if tag is None:
        return False
    scene.begin_group()
    try:
        if restore_fk:
            chain = chain_of(scene, start, tag)
            if chain:
                jt.checkpoint(scene, "ik_fk")
                _apply_fk(chain, current_fk(tag, chain))
        data.write(scene, start, data.IK_KEY, None)
        if delete_targets:
            for key in ("goal", "pole"):
                target = _find(scene, tag.get(key))
                if target is not None:
                    scene.remove_object(target)
    finally:
        scene.end_group()
    scene.changed.emit()
    return True


def set_ik(scene, start: SceneObject, **values) -> dict:
    tag = ik_tag(start)
    if tag is None:
        raise ValueError(f"{start.name} has no IK")
    new = dict(tag)
    for k, v in values.items():
        if k == "solver":
            new[k] = _solver_name(v)
        elif k == "blend":
            new[k] = float(np.clip(v, 0.0, 1.0))
        elif k == "iterations":
            new[k] = int(max(1, v))
        elif k in ("goal", "pole", "end"):
            new[k] = v.name if isinstance(v, SceneObject) else ("" if v is None else str(v))
        else:
            new[k] = v
    data.write(scene, start, data.IK_KEY, new)
    return new


def store_fk(scene, start: SceneObject) -> dict | None:
    tag = ik_tag(start)
    chain = chain_of(scene, start, tag)
    if tag is None or not chain:
        return None
    new = dict(tag)
    new["fk"] = _fk_of(chain)
    new.pop("ik_out", None)
    data.write(scene, start, data.IK_KEY, new)
    return new


def solve_two_bone(a: np.ndarray, b: np.ndarray, c: np.ndarray, target: np.ndarray,
                   pole: np.ndarray | None = None, twist: float = 0.0) -> np.ndarray:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    c = np.asarray(c, float)
    t = np.asarray(target, float)
    l1 = float(np.linalg.norm(b - a))
    l2 = float(np.linalg.norm(c - b))
    to_t = t - a
    dist = float(np.linalg.norm(to_t))
    if dist < mu.EPS:
        direction = mu.normalize(c - a)
        if not np.any(direction):
            direction = mu.normalize(b - a) if np.any(b - a) else np.array([1.0, 0.0, 0.0])
    else:
        direction = to_t / dist
    reach = min(max(dist, abs(l1 - l2)), l1 + l2)
    hint = (np.asarray(pole, float) - a) if pole is not None else (b - a)
    bend = hint - (hint @ direction) * direction
    if np.linalg.norm(bend) < mu.EPS:
        alt = b - a
        bend = alt - (alt @ direction) * direction
    if np.linalg.norm(bend) < mu.EPS:
        bend = mu.perpendicular(direction)
    bend = mu.normalize(bend)
    if twist:
        bend = axis_rotate(bend, direction, math.radians(twist))
    if reach < mu.EPS or l1 < mu.EPS:
        cos_a = 1.0
    else:
        cos_a = float(np.clip((l1 * l1 + reach * reach - l2 * l2) / (2.0 * l1 * reach), -1.0, 1.0))
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
    nb = a + l1 * (cos_a * direction + sin_a * bend)
    nc = a + reach * direction
    return np.array([a, nb, nc])


def axis_rotate(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    return mu.axis_angle_matrix(axis, angle) @ np.asarray(v, float)


def solve_ccd(points: np.ndarray, target: np.ndarray, iterations: int = 24, tolerance: float = 0.01,
              pole: np.ndarray | None = None) -> np.ndarray:
    x = np.array(points, float).reshape(-1, 3)
    t = np.asarray(target, float)
    n = len(x)
    if n < 2:
        return x
    if n >= 3:
        axis = mu.normalize(x[-1] - x[0])
        perp = np.zeros(3)
        for p in x[1:-1]:
            v = p - x[0]
            perp += v - (v @ axis) * axis
        if np.linalg.norm(perp) < 1e-6 * max(1.0, float(np.linalg.norm(x[-1] - x[0]))):
            side = (np.asarray(pole, float) - x[0]) if pole is not None else mu.perpendicular(axis)
            side = side - (side @ axis) * axis
            side = mu.normalize(side) if np.linalg.norm(side) > mu.EPS else mu.perpendicular(axis)
            rot_axis = mu.normalize(np.cross(axis, side))
            for i in range(n - 2):
                r = mu.axis_angle_matrix(rot_axis, 0.15)
                x[i + 1:] = x[i] + (x[i + 1:] - x[i]) @ r.T
    for _ in range(max(1, int(iterations))):
        for i in range(n - 2, -1, -1):
            e = x[-1] - x[i]
            g = t - x[i]
            r = mu.arc_matrix(e, g)
            x[i + 1:] = x[i] + (x[i + 1:] - x[i]) @ r.T
        if float(np.linalg.norm(x[-1] - t)) <= tolerance:
            break
    return x


def align_to_pole(points: np.ndarray, pole: np.ndarray, twist: float = 0.0) -> np.ndarray:
    x = np.array(points, float).reshape(-1, 3)
    if len(x) < 3:
        return x
    axis = mu.normalize(x[-1] - x[0])
    if not np.any(axis):
        return x
    bend = np.zeros(3)
    for p in x[1:-1]:
        v = p - x[0]
        bend += v - (v @ axis) * axis
    want = np.asarray(pole, float) - x[0]
    want = want - (want @ axis) * axis
    if np.linalg.norm(bend) < mu.EPS or np.linalg.norm(want) < mu.EPS:
        return x
    bend = mu.normalize(bend)
    want = mu.normalize(want)
    if twist:
        want = axis_rotate(want, axis, math.radians(twist))
    angle = math.atan2(float(np.cross(bend, want) @ axis), float(np.clip(bend @ want, -1.0, 1.0)))
    r = mu.axis_angle_matrix(axis, angle)
    return x[0] + (x - x[0]) @ r.T


def apply_positions(chain: Sequence[SceneObject], targets: np.ndarray) -> None:
    for i in range(len(chain) - 1):
        j, nxt = chain[i], chain[i + 1]
        p = j.world_position()
        c = nxt.world_position()
        delta = mu.arc_matrix(c - p, np.asarray(targets[i + 1], float) - p)
        world = j.world_matrix()[:3, :3]
        new_world = delta @ world
        local = np.linalg.solve(j.parent_matrix()[:3, :3], new_world)
        j.rotation = mu.euler_from_matrix(mu.rotation_part(local, j.scale))


def blend_rotations(fk: Sequence[Iterable[float]], ik: Sequence[Iterable[float]], t: float) -> list[np.ndarray]:
    out = []
    for a, b in zip(fk, ik):
        qa = mu.quat_from_matrix(mu.matrix_from_euler(a))
        qb = mu.quat_from_matrix(mu.matrix_from_euler(b))
        out.append(mu.euler_from_matrix(mu.matrix_from_quat(mu.quat_slerp(qa, qb, float(t)))))
    return out


def _same_pose(a, b, tol: float = 1e-6) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict) or a.keys() != b.keys():
        return False
    for k in a:
        va = np.asarray(a[k], float).reshape(-1)
        vb = np.asarray(b[k], float).reshape(-1)
        if va.shape != vb.shape or not np.allclose(va, vb, atol=tol, rtol=0.0):
            return False
    return True


def current_fk(tag: dict, chain: Sequence[SceneObject]) -> dict:
    now = _fk_of(chain)
    last = tag.get("ik_out")
    stored = tag.get("fk")
    if isinstance(last, dict) and not _same_pose(now, last):
        return now
    if isinstance(stored, dict) and stored:
        merged = dict(now)
        merged.update({k: [float(x) for x in np.asarray(v, float).reshape(-1)]
                       for k, v in stored.items() if k in merged})
        return merged
    return now


def _apply_fk(chain: Sequence[SceneObject], fk: dict) -> None:
    for j in chain:
        rot = fk.get(j.name)
        if rot is not None:
            j.rotation = np.asarray(rot, float).reshape(3).copy()


def _store_state(start: SceneObject, tag: dict, fk: dict, out: dict) -> None:
    if _same_pose(tag.get("fk"), fk, 0.0) and _same_pose(tag.get("ik_out"), out, 0.0):
        return
    new = dict(tag)
    new["fk"] = fk
    new["ik_out"] = out
    data.write_quiet(start, data.IK_KEY, new)


def solve_ik(scene, start: SceneObject) -> float | None:
    tag = ik_tag(start)
    if tag is None or not tag.get("enabled", True):
        return None
    chain = chain_of(scene, start, tag)
    goal = _find(scene, tag.get("goal"))
    if not chain or len(chain) < 2:
        return None
    blend = float(np.clip(tag.get("blend", 1.0), 0.0, 1.0))
    fk = current_fk(tag, chain)
    _apply_fk(chain, fk)
    if blend <= 0.0 or goal is None:
        _store_state(start, tag, fk, _fk_of(chain))
        return None
    fk_rots = [j.rotation.copy() for j in chain]
    pts = np.array([j.world_position() for j in chain])
    target = goal.world_position()
    pole_obj = _find(scene, tag.get("pole"))
    pole = pole_obj.world_position() if pole_obj is not None else None
    solver = _solver_name(tag.get("solver", "Auto"))
    twist = float(tag.get("twist", 0.0))
    if len(chain) == 3 and solver in ("Auto", "Two Bone"):
        solved = solve_two_bone(pts[0], pts[1], pts[2], target, pole, twist)
    else:
        solved = solve_ccd(pts, target, int(tag.get("iterations", 24)), float(tag.get("tolerance", 0.01)), pole)
        if pole is not None:
            solved = align_to_pole(solved, pole, twist)
    apply_positions(chain, solved)
    if tag.get("match_goal_rotation"):
        jt.set_world_rotation(chain[-1], mu.orthonormalize(goal.world_matrix()[:3, :3]))
    if blend < 1.0:
        ik_rots = [j.rotation.copy() for j in chain]
        for j, rot in zip(chain, blend_rotations(fk_rots, ik_rots, blend)):
            j.rotation = rot
    _store_state(start, tag, fk, _fk_of(chain))
    return float(np.linalg.norm(chain[-1].world_position() - target))


def solve_all(scene) -> int:
    count = 0
    for start, _tag in ik_tags(scene):
        if solve_ik(scene, start) is not None:
            count += 1
    return count


def sync_to_pose(scene, start: SceneObject) -> bool:
    tag = ik_tag(start)
    chain = chain_of(scene, start, tag)
    if tag is None or not chain or len(chain) < 2:
        return False
    goal = _find(scene, tag.get("goal"))
    pole = _find(scene, tag.get("pole"))
    chain_ids = {id(j) for j in chain}
    if goal is not None and id(goal) not in chain_ids:
        end = chain[-1]
        jt.set_world_position(goal, end.world_position())
        if tag.get("match_goal_rotation"):
            jt.set_world_rotation(goal, mu.orthonormalize(end.world_matrix()[:3, :3]))
    if pole is not None and id(pole) not in chain_ids and len(chain) >= 3:
        pts = np.array([j.world_position() for j in chain])
        axis = mu.normalize(pts[-1] - pts[0])
        bend = np.zeros(3)
        for p in pts[1:-1]:
            v = p - pts[0]
            bend += v - (v @ axis) * axis
        if np.linalg.norm(bend) > mu.EPS * max(1.0, float(np.linalg.norm(pts[-1] - pts[0]))):
            mid = pts[len(pts) // 2]
            length = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
            dist = max(float(np.linalg.norm(pole.world_position() - mid)), length * 0.5, 1.0)
            jt.set_world_position(pole, mid + mu.normalize(bend) * dist)
    pose = _fk_of(chain)
    new = dict(tag)
    new["fk"] = pose
    new["ik_out"] = pose
    data.write(scene, start, data.IK_KEY, new)
    return True


def rename_references(scene, old: str, new: str) -> int:
    count = 0
    for start, tag in ik_tags(scene):
        changed = {k: new for k in ("end", "goal", "pole") if tag.get(k) == old}
        fk = tag.get("fk", {})
        out = tag.get("ik_out")
        hit = bool(changed) or (isinstance(fk, dict) and old in fk) or (isinstance(out, dict) and old in out)
        if not hit:
            continue
        fixed = dict(tag)
        fixed.update(changed)
        for key in ("fk", "ik_out"):
            value = fixed.get(key)
            if isinstance(value, dict) and old in value:
                fixed[key] = {(new if k == old else k): v for k, v in value.items()}
        data.write_quiet(start, data.IK_KEY, fixed)
        count += 1
    return count
