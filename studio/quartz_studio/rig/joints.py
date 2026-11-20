from __future__ import annotations

import re
from typing import Iterable, Sequence

import numpy as np

from ..objects import registry as objreg
from ..scene import Mesh, SceneObject
from . import mathutil as mu

__all__ = [
    "JOINT_KIND",
    "JOINT_DISPLAYS",
    "JOINT_SPEC",
    "joint_glyph",
    "is_joint",
    "joints",
    "find_joint",
    "joint_children",
    "joint_parent",
    "root_joints",
    "joint_hierarchy",
    "joint_chain",
    "set_world_position",
    "set_world_rotation",
    "set_world_matrix",
    "checkpoint",
    "create_joint",
    "create_chain",
    "build_joints",
    "order_points",
    "chain_from_selection",
    "update_bone_display",
    "orient_joints",
    "mirror_name",
    "BIPED_LAYOUT",
    "build_biped",
]

JOINT_KIND = "joint"
JOINT_DISPLAYS = ("Bone", "Axis", "None")


def joint_glyph(tip: Iterable[float], radius: float, display: str = "Bone") -> Mesh:
    r = max(0.0, float(radius))
    t = np.asarray(tuple(tip), float).reshape(3)
    length = float(np.linalg.norm(t))
    if display == "None" or r <= 0.0:
        return Mesh.empty()
    if display == "Axis":
        pts = [(0.0, 0.0, 0.0), (2 * r, 0.0, 0.0), (0.0, 2 * r, 0.0), (0.0, 0.0, 2 * r)]
        edges = [(0, 1), (0, 2), (0, 3)]
        if length > mu.EPS:
            pts.append(tuple(t))
            edges.append((0, 4))
        return Mesh(pts, [], edges)
    if length < mu.EPS:
        pts = [(r, 0, 0), (-r, 0, 0), (0, r, 0), (0, -r, 0), (0, 0, r), (0, 0, -r)]
        ring = [0, 4, 1, 5]
        edges = [(ring[i], ring[(i + 1) % 4]) for i in range(4)]
        edges += [(2, k) for k in ring] + [(3, k) for k in ring]
        return Mesh(pts, [], edges)
    axis = t / length
    u = mu.perpendicular(axis)
    v = np.cross(axis, u)
    w = min(r, length * 0.2)
    base = axis * (length * 0.18)
    ring = [base + w * (np.cos(a) * u + np.sin(a) * v) for a in (0.0, np.pi / 2, np.pi, 1.5 * np.pi)]
    pts = [np.zeros(3), *ring, t]
    edges = [(0, k) for k in range(1, 5)]
    edges += [(k, 1 + (k % 4)) for k in range(1, 5)]
    edges += [(k, 5) for k in range(1, 5)]
    return Mesh(np.asarray(pts, float), [], edges)


def _build_joint(params: dict, _inputs: list) -> Mesh:
    return joint_glyph(params.get("tip", (0.0, 0.0, 0.0)), float(params.get("radius", 4.0)),
                       str(params.get("display", "Bone")))


def _register() -> objreg.ObjectSpec:
    existing = objreg.SPECS.get(JOINT_KIND)
    if existing is not None:
        return existing
    return objreg.register(objreg.ObjectSpec(
        id=JOINT_KIND,
        label="Joint",
        category="null",
        build=_build_joint,
        params=(
            objreg.Param("display", "Display", "choice", "Bone", choices=JOINT_DISPLAYS, group="Joint"),
            objreg.Param("radius", "Radius", "distance", 4.0, minimum=0.0, group="Joint"),
            objreg.Param("tip", "Bone Tip", "vector", (0.0, 0.0, 0.0), group="Joint"),
        ),
        inputs="none",
        icon="null",
        description="Skeleton joint that drives skinned meshes",
    ))


JOINT_SPEC = _register()


def is_joint(obj) -> bool:
    return obj is not None and getattr(obj, "kind", None) == JOINT_KIND


def joints(scene) -> list[SceneObject]:
    return [o for o in scene.objects if is_joint(o)]


def find_joint(scene, name: str) -> SceneObject | None:
    for o in scene.objects:
        if is_joint(o) and o.name == name:
            return o
    return None


def joint_children(scene, joint: SceneObject) -> list[SceneObject]:
    return [c for c in scene.children(joint) if is_joint(c)]


def joint_parent(joint: SceneObject) -> SceneObject | None:
    p = joint.parent
    return p if is_joint(p) else None


def root_joints(scene) -> list[SceneObject]:
    return [j for j in joints(scene) if not is_joint(j.parent)]


def joint_hierarchy(scene, root: SceneObject) -> list[SceneObject]:
    out: list[SceneObject] = []

    def visit(j: SceneObject) -> None:
        out.append(j)
        for c in joint_children(scene, j):
            visit(c)

    if is_joint(root):
        visit(root)
    return out


def joint_chain(start: SceneObject, end: SceneObject) -> list[SceneObject] | None:
    path = [end]
    cur = end
    while cur is not start:
        cur = cur.parent
        if cur is None or not is_joint(cur):
            return None
        path.append(cur)
    path.reverse()
    return path


def set_world_position(obj: SceneObject, world: Iterable[float]) -> None:
    pm = obj.parent_matrix()
    w = np.append(np.asarray(tuple(world), float).reshape(3), 1.0)
    obj.position = np.linalg.solve(pm, w)[:3]


def set_world_rotation(obj: SceneObject, rot_world: np.ndarray) -> None:
    pm = obj.parent_matrix()
    local = np.linalg.solve(pm[:3, :3], np.asarray(rot_world, float)[:3, :3])
    obj.rotation = mu.euler_from_matrix(mu.orthonormalize(local))


def set_world_matrix(obj: SceneObject, world: np.ndarray) -> None:
    local = np.linalg.solve(obj.parent_matrix(), np.asarray(world, float))
    lin = local[:3, :3]
    scale = np.linalg.norm(lin, axis=0)
    if np.linalg.det(lin) < 0.0:
        scale[0] = -scale[0]
    safe = np.where(np.abs(scale) > mu.EPS, scale, 1.0)
    obj.position = local[:3, 3].copy()
    obj.rotation = mu.euler_from_matrix(mu.orthonormalize(lin / safe[None, :]))
    obj.scale = scale.astype(float)


def checkpoint(scene, kind: str) -> None:
    record = getattr(scene, "_record", None)
    if callable(record):
        record(kind)


def _set_params(obj: SceneObject, **values) -> None:
    for k, v in values.items():
        if k == "tip":
            v = tuple(0.0 if abs(float(x)) < 1e-9 else float(x) for x in v)
        obj.params[k] = JOINT_SPEC.param(k).clamp(v)
    obj._dirty = True


def create_joint(scene, name: str = "Joint", parent: SceneObject | None = None,
                 world_position: Iterable[float] | None = None, activate: bool = True,
                 radius: float | None = None) -> SceneObject:
    scene.begin_group()
    try:
        obj = scene.add_parametric(JOINT_KIND, name, parent=parent, activate=activate)
        if world_position is not None:
            set_world_position(obj, world_position)
        if radius is not None:
            _set_params(obj, radius=radius)
        scene.evaluate()
    finally:
        scene.end_group()
    scene.changed.emit()
    return obj


def build_joints(scene, entries: Sequence[dict], orient: bool = True,
                 parent: SceneObject | None = None, up: Iterable[float] = (0.0, 1.0, 0.0),
                 radius: float | None = None, activate: bool = True) -> list[SceneObject]:
    count = len(entries)
    if count == 0:
        return []
    pos = np.array([np.asarray(e["position"], float).reshape(3) for e in entries])
    parents: list[int | None] = []
    for i, e in enumerate(entries):
        p = e.get("parent")
        if p is not None and not 0 <= int(p) < i:
            raise ValueError(f"joint {i} has parent {p}, parents must come first")
        parents.append(None if p is None else int(p))
    kids: dict[int, list[int]] = {i: [] for i in range(count)}
    for i, p in enumerate(parents):
        if p is not None:
            kids[p].append(i)
    rots: list[np.ndarray] = []
    for i in range(count):
        if not orient:
            rots.append(np.eye(3))
        elif kids[i]:
            rots.append(mu.aim_matrix(pos[kids[i][0]] - pos[i], up))
        elif parents[i] is not None:
            rots.append(rots[parents[i]])
        elif parent is not None:
            rots.append(mu.orthonormalize(parent.world_matrix()[:3, :3]))
        else:
            rots.append(np.eye(3))
    made: list[SceneObject] = []
    scene.begin_group()
    try:
        for i, e in enumerate(entries):
            par = made[parents[i]] if parents[i] is not None else parent
            obj = scene.add_parametric(JOINT_KIND, e.get("name", "Joint"), parent=par, activate=False)
            if orient:
                set_world_rotation(obj, rots[i])
            set_world_position(obj, pos[i])
            if radius is not None:
                _set_params(obj, radius=radius)
            made.append(obj)
        for i, obj in enumerate(made):
            if kids[i]:
                _set_params(obj, tip=tuple(made[kids[i][0]].position))
            else:
                tip_len = float(entries[i].get("tip", 0.0))
                if tip_len > 0.0:
                    if parents[i] is not None:
                        direction = pos[i] - pos[parents[i]]
                    else:
                        direction = np.array([0.0, 1.0, 0.0])
                    direction = mu.normalize(direction) * tip_len
                    local = np.linalg.solve(obj.world_matrix()[:3, :3], direction)
                    _set_params(obj, tip=tuple(local))
        scene.evaluate()
        if activate and made:
            scene.set_active(made[0])
    finally:
        scene.end_group()
    scene.objectsChanged.emit()
    scene.changed.emit()
    return made


def create_chain(scene, points: Iterable[Iterable[float]], name: str = "Joint",
                 parent: SceneObject | None = None, orient: bool = True,
                 up: Iterable[float] = (0.0, 1.0, 0.0), radius: float | None = None,
                 activate: bool = True) -> list[SceneObject]:
    pts = np.asarray([tuple(p) for p in points], float).reshape(-1, 3)
    entries = [{"name": f"{name}{i + 1}" if len(pts) > 1 else name, "position": pts[i],
                "parent": i - 1 if i else None} for i in range(len(pts))]
    return build_joints(scene, entries, orient=orient, parent=parent, up=up, radius=radius,
                        activate=activate)


def order_points(points: np.ndarray, indices: Sequence[int], order: str = "Index") -> list[int]:
    idx = sorted(int(i) for i in indices)
    if order != "Nearest" or len(idx) < 3:
        return idx
    pts = np.asarray(points, float)
    sub = pts[idx]
    start = int(np.argmax(np.linalg.norm(sub - sub.mean(axis=0), axis=1)))
    remaining = list(range(len(idx)))
    path = [remaining.pop(start)]
    while remaining:
        last = sub[path[-1]]
        d = [float(np.linalg.norm(sub[k] - last)) for k in remaining]
        path.append(remaining.pop(int(np.argmin(d))))
    return [idx[k] for k in path]


def chain_from_selection(scene, order: str = "Index", orient: bool = True,
                         name: str = "Joint") -> list[SceneObject]:
    obj = scene.active
    if obj is None or obj not in scene.objects:
        raise ValueError("no active object")
    sel = sorted(scene.selected_points)
    if not sel:
        raise ValueError("select points on the active object first")
    ordered = order_points(obj.mesh.points, sel, order)
    world = obj.to_world(obj.mesh.points[ordered])
    return create_chain(scene, world, name=name, orient=orient)


def update_bone_display(scene, targets: Iterable[SceneObject] | None = None) -> int:
    changed = 0
    items = joints(scene) if targets is None else [j for j in targets if is_joint(j)]
    scene.begin_group()
    try:
        for j in items:
            kids = joint_children(scene, j)
            if not kids:
                continue
            tip = tuple(float(v) for v in kids[0].position)
            if scene.set_param(j, "tip", tip):
                changed += 1
    finally:
        scene.end_group()
    return changed


def orient_joints(scene, targets: Iterable[SceneObject] | None = None,
                  up: Iterable[float] = (0.0, 1.0, 0.0)) -> int:
    items = joints(scene) if targets is None else [j for j in targets if is_joint(j)]
    items = sorted(items, key=scene.objects.index)
    worlds = {id(j): j.world_matrix() for j in joints(scene)}
    count = 0
    scene.begin_group()
    try:
        checkpoint(scene, "orient")
        for j in items:
            kids = joint_children(scene, j)
            if not kids:
                parent = joint_parent(j)
                rot = mu.orthonormalize(parent.world_matrix()[:3, :3]) if parent is not None else np.eye(3)
            else:
                rot = mu.aim_matrix(worlds[id(kids[0])][:3, 3] - worlds[id(j)][:3, 3], up)
            set_world_rotation(j, rot)
            set_world_position(j, worlds[id(j)][:3, 3])
            for c in scene.descendants(j):
                if id(c) in worlds:
                    set_world_matrix(c, worlds[id(c)])
            count += 1
        for j in items:
            kids = joint_children(scene, j)
            if kids:
                _set_params(j, tip=tuple(kids[0].position))
        scene.evaluate()
    finally:
        scene.end_group()
    scene.changed.emit()
    return count


_MIRROR_RULES = (
    (re.compile(r"^L_"), "R_"), (re.compile(r"^R_"), "L_"),
    (re.compile(r"^l_"), "r_"), (re.compile(r"^r_"), "l_"),
    (re.compile(r"_L$"), "_R"), (re.compile(r"_R$"), "_L"),
    (re.compile(r"\.L$"), ".R"), (re.compile(r"\.R$"), ".L"),
    (re.compile(r"^Left"), "Right"), (re.compile(r"^Right"), "Left"),
)


def mirror_name(name: str) -> str:
    for pattern, repl in _MIRROR_RULES:
        if pattern.search(name):
            return pattern.sub(repl, name, count=1)
    return name


BIPED_LAYOUT: tuple = (
    ("Hips", None, (0.0, 0.53, 0.0), 0.0),
    ("Spine1", "Hips", (0.0, 0.59, 0.005), 0.0),
    ("Spine2", "Spine1", (0.0, 0.66, 0.008), 0.0),
    ("Spine3", "Spine2", (0.0, 0.73, 0.005), 0.0),
    ("Neck", "Spine3", (0.0, 0.82, 0.0), 0.0),
    ("Head", "Neck", (0.0, 0.87, -0.005), 0.13),
    ("L_Clavicle", "Spine3", (-0.015, 0.80, -0.01), 0.0),
    ("L_UpperArm", "L_Clavicle", (-0.10, 0.80, 0.0), 0.0),
    ("L_ForeArm", "L_UpperArm", (-0.26, 0.80, 0.012), 0.0),
    ("L_Hand", "L_ForeArm", (-0.40, 0.80, 0.0), 0.09),
    ("R_Clavicle", "Spine3", (0.015, 0.80, -0.01), 0.0),
    ("R_UpperArm", "R_Clavicle", (0.10, 0.80, 0.0), 0.0),
    ("R_ForeArm", "R_UpperArm", (0.26, 0.80, 0.012), 0.0),
    ("R_Hand", "R_ForeArm", (0.40, 0.80, 0.0), 0.09),
    ("L_Thigh", "Hips", (-0.055, 0.51, 0.0), 0.0),
    ("L_Shin", "L_Thigh", (-0.055, 0.28, -0.012), 0.0),
    ("L_Foot", "L_Shin", (-0.055, 0.045, 0.0), 0.0),
    ("L_Toe", "L_Foot", (-0.055, 0.01, -0.09), 0.04),
    ("R_Thigh", "Hips", (0.055, 0.51, 0.0), 0.0),
    ("R_Shin", "R_Thigh", (0.055, 0.28, -0.012), 0.0),
    ("R_Foot", "R_Shin", (0.055, 0.045, 0.0), 0.0),
    ("R_Toe", "R_Foot", (0.055, 0.01, -0.09), 0.04),
)


def build_biped(scene, height: float = 180.0, orient: bool = True, prefix: str = "",
                origin: Iterable[float] = (0.0, 0.0, 0.0), with_ik: bool = False,
                radius: float | None = None) -> dict[str, SceneObject]:
    h = max(1.0, float(height))
    base = np.asarray(tuple(origin), float).reshape(3)
    names = [row[0] for row in BIPED_LAYOUT]
    entries = []
    for name, parent, frac, tip in BIPED_LAYOUT:
        entries.append({
            "name": prefix + name,
            "position": base + np.asarray(frac, float) * h,
            "parent": None if parent is None else names.index(parent),
            "tip": tip * h,
        })
    made = build_joints(scene, entries, orient=orient,
                        radius=radius if radius is not None else max(0.5, h * 0.012))
    out = {name: obj for name, obj in zip(names, made)}
    if with_ik:
        from . import ik
        scene.begin_group()
        try:
            for side in ("L_", "R_"):
                ik.add_ik(scene, out[side + "Thigh"], out[side + "Foot"], solver="two_bone",
                          pole_side=np.array([0.0, 0.0, -1.0]))
                ik.add_ik(scene, out[side + "UpperArm"], out[side + "Hand"], solver="two_bone",
                          pole_side=np.array([0.0, 0.0, 1.0]))
        finally:
            scene.end_group()
    return out
