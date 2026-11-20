from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np

from ..scene import EDITABLE_KIND, SceneObject
from . import data
from . import joints as jt
from . import mathutil as mu

__all__ = [
    "SKIN_METHODS",
    "PAINT_MODES",
    "FALLOFFS",
    "skin_of",
    "is_skinned",
    "skinned_objects",
    "skin_joints",
    "bind_skin",
    "unbind_skin",
    "rebind_skin",
    "auto_weights",
    "compute_auto_weights",
    "bone_segments",
    "segment_distances",
    "adjacency",
    "smooth_weights",
    "normalize_weights",
    "limit_influences",
    "prune_weights",
    "linear_blend",
    "dual_quaternion_blend",
    "deform_points",
    "deform_skin",
    "skin_matrices",
    "reset_bind_pose",
    "brush_falloff",
    "sphere_distances",
    "cylinder_distances",
    "paint_weights",
    "apply_weights",
    "set_skin_method",
    "mirror_weights",
    "mirror_weight_matrix",
    "mirror_plane",
    "nearest_within",
    "skin_joint_names",
    "weight_totals",
    "influence_counts",
]

SKIN_METHODS = ("Linear", "Dual Quaternion")
PAINT_MODES = ("Add", "Subtract", "Replace", "Smooth", "Normalize")
FALLOFFS = ("Smooth", "Linear", "Constant")


def skin_of(obj) -> dict | None:
    value = data.read(obj, data.SKIN_KEY)
    return value if isinstance(value, dict) else None


def is_skinned(obj) -> bool:
    return isinstance(getattr(obj, "extras", None), dict) and isinstance(obj.extras.get(data.SKIN_KEY), dict)


def skin_joint_names(obj) -> list[str]:
    raw = obj.extras.get(data.SKIN_KEY) if isinstance(getattr(obj, "extras", None), dict) else None
    if not isinstance(raw, dict):
        return []
    names = raw.get("joints", [])
    return [str(n) for n in names] if isinstance(names, list) else []


def skinned_objects(scene) -> list[SceneObject]:
    return [o for o in scene.objects if is_skinned(o)]


def skin_joints(scene, skin: dict) -> list[SceneObject | None]:
    return [jt.find_joint(scene, name) for name in skin.get("joints", [])]


def segment_distances(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    p = np.asarray(points, float).reshape(-1, 3)
    a = np.asarray(a, float).reshape(-1, 3)
    b = np.asarray(b, float).reshape(-1, 3)
    ab = b - a
    denom = np.einsum("ij,ij->i", ab, ab)
    safe = np.where(denom > 1e-18, denom, 1.0)
    rel = p[:, None, :] - a[None, :, :]
    t = np.einsum("nsk,sk->ns", rel, ab) / safe[None, :]
    t = np.where(denom[None, :] > 1e-18, np.clip(t, 0.0, 1.0), 0.0)
    closest = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    return np.linalg.norm(p[:, None, :] - closest, axis=2)


def bone_segments(scene, joint_objs: Sequence[SceneObject | None],
                  matrices: np.ndarray) -> list[list[tuple[np.ndarray, np.ndarray]]]:
    index = {id(j): k for k, j in enumerate(joint_objs) if j is not None}
    out: list[list[tuple[np.ndarray, np.ndarray]]] = []
    for k, j in enumerate(joint_objs):
        m = np.asarray(matrices[k], float)
        head = m[:3, 3].copy()
        segs: list[tuple[np.ndarray, np.ndarray]] = []
        if j is not None:
            for c in jt.joint_children(scene, j):
                if id(c) in index:
                    segs.append((head, np.asarray(matrices[index[id(c)]], float)[:3, 3].copy()))
            if not segs:
                tip = np.asarray(j.params.get("tip", (0.0, 0.0, 0.0)), float)
                if float(np.linalg.norm(tip)) > mu.EPS:
                    segs.append((head, mu.transform_points(m, tip)[0]))
        if not segs:
            segs.append((head, head.copy()))
        out.append(segs)
    return out


def adjacency(mesh) -> tuple[np.ndarray, np.ndarray]:
    edges = np.asarray(list(mesh.edges), int).reshape(-1, 2)
    return edges, np.bincount(edges.reshape(-1), minlength=len(mesh.points)).astype(float)


def _neighbour_mean(w: np.ndarray, adj: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    edges, counts = adj
    if not len(edges):
        return w.copy()
    sums = np.zeros_like(w)
    np.add.at(sums, edges[:, 0], w[edges[:, 1]])
    np.add.at(sums, edges[:, 1], w[edges[:, 0]])
    has = counts > 0
    out = w.copy()
    out[has] = sums[has] / counts[has][:, None]
    return out


def normalize_weights(w: np.ndarray, rows: np.ndarray | None = None) -> np.ndarray:
    out = np.clip(np.asarray(w, float), 0.0, None)
    total = out.sum(axis=1)
    ok = total > 1e-12
    if rows is not None:
        mask = np.zeros(len(out), bool)
        mask[np.asarray(rows)] = True
        ok &= mask
    out[ok] = out[ok] / total[ok][:, None]
    return out


def limit_influences(w: np.ndarray, count: int) -> np.ndarray:
    out = np.asarray(w, float).copy()
    k = int(count)
    if k <= 0 or k >= out.shape[1]:
        return out
    order = np.argsort(-out, axis=1, kind="stable")
    drop = order[:, k:]
    np.put_along_axis(out, drop, 0.0, axis=1)
    return out


def prune_weights(w: np.ndarray, threshold: float) -> np.ndarray:
    out = np.asarray(w, float).copy()
    before = out.sum(axis=1)
    keep = out.max(axis=1, keepdims=True)
    small = (out < float(threshold)) & (out < keep)
    out[small] = 0.0
    changed = np.any(small, axis=1) & (before > 1e-12)
    return normalize_weights(out, np.nonzero(changed)[0]) if np.any(changed) else out


def smooth_weights(w: np.ndarray, adj: tuple[np.ndarray, np.ndarray], iterations: int = 1,
                   strength: float = 0.5, rows: np.ndarray | None = None) -> np.ndarray:
    out = np.asarray(w, float).copy()
    s = float(np.clip(strength, 0.0, 1.0))
    for _ in range(max(0, int(iterations))):
        avg = _neighbour_mean(out, adj)
        if rows is None:
            out = out + (avg - out) * s
        else:
            out[rows] = out[rows] + (avg[rows] - out[rows]) * s
    return out


def compute_auto_weights(points_world: np.ndarray, segments: Sequence[Sequence[tuple]],
                         falloff: float = 4.0, max_influences: int = 4,
                         adj: tuple[np.ndarray, np.ndarray] | None = None,
                         smooth: int = 0, smooth_strength: float = 0.5) -> np.ndarray:
    pts = np.asarray(points_world, float).reshape(-1, 3)
    count = len(segments)
    if count == 0:
        return np.zeros((len(pts), 0))
    if not len(pts):
        return np.zeros((0, count))
    dist = np.empty((len(pts), count))
    for k, segs in enumerate(segments):
        a = np.array([s[0] for s in segs], float)
        b = np.array([s[1] for s in segs], float)
        dist[:, k] = segment_distances(pts, a, b).min(axis=1)
    heads = np.array([segs[0][0] for segs in segments], float)
    span = np.vstack([pts, heads])
    diag = float(np.linalg.norm(span.max(axis=0) - span.min(axis=0)))
    eps = max(diag * 1e-4, 1e-9)
    nearest = dist.min(axis=1, keepdims=True)
    w = ((nearest + eps) / (dist + eps)) ** max(0.1, float(falloff))
    w = normalize_weights(limit_influences(w, max_influences))
    if smooth > 0 and adj is not None:
        w = smooth_weights(w, adj, smooth, smooth_strength)
        w = normalize_weights(limit_influences(w, max_influences))
    return w


def skin_matrices(scene, skin: dict) -> np.ndarray:
    bind = np.asarray(skin["bind_matrices"], float).reshape(-1, 4, 4)
    out = np.empty_like(bind)
    for k, j in enumerate(skin_joints(scene, skin)):
        if j is None:
            out[k] = np.eye(4)
        else:
            out[k] = j.world_matrix() @ np.linalg.inv(bind[k])
    return out


def linear_blend(points_world: np.ndarray, mats: np.ndarray, weights: np.ndarray) -> np.ndarray:
    p = np.asarray(points_world, float).reshape(-1, 3)
    w = np.asarray(weights, float)
    out = p * np.clip(1.0 - w.sum(axis=1), 0.0, None)[:, None]
    for k in range(w.shape[1] if w.ndim == 2 else 0):
        col = w[:, k]
        nz = col != 0.0
        if not np.any(nz):
            continue
        m = mats[k]
        out[nz] += col[nz, None] * (p[nz] @ m[:3, :3].T + m[:3, 3])
    return out


def _qmul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bw, bx, by, bz = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ], axis=-1)


def _qconj(q: np.ndarray) -> np.ndarray:
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def dual_quaternion_blend(points_world: np.ndarray, mats: np.ndarray, weights: np.ndarray) -> np.ndarray:
    p = np.asarray(points_world, float).reshape(-1, 3)
    w = np.asarray(weights, float)
    n, count = w.shape if w.ndim == 2 else (len(p), 0)
    if count == 0 or n == 0:
        return p.copy()
    real = np.empty((count + 1, 4))
    dual = np.empty((count + 1, 4))
    scales = np.empty((count + 1, 3, 3))
    for k in range(count):
        lin = mats[k][:3, :3]
        rot = mu.orthonormalize(lin)
        scales[k] = rot.T @ lin
        r = mu.quat_from_matrix(rot)
        t = np.array([0.0, *mats[k][:3, 3]])
        real[k] = r
        dual[k] = 0.5 * _qmul(t, r)
    real[count] = (1.0, 0.0, 0.0, 0.0)
    dual[count] = 0.0
    scales[count] = np.eye(3)
    rest = np.clip(1.0 - w.sum(axis=1), 0.0, None)
    ww = np.column_stack([w, rest])
    pivot = np.argmax(ww, axis=1)
    sign = np.sign(real @ real.T)[pivot]
    sign[sign == 0.0] = 1.0
    sw = ww * sign
    br = sw @ real
    bd = sw @ dual
    norm = np.linalg.norm(br, axis=1)
    norm = np.where(norm > 1e-12, norm, 1.0)
    br = br / norm[:, None]
    bd = bd / norm[:, None]
    stretch = np.einsum("nk,kij->nij", ww, scales)
    local = np.einsum("nij,nj->ni", stretch, p)
    w0, v = br[:, 0], br[:, 1:]
    t = 2.0 * _qmul(bd, _qconj(br))[:, 1:]
    cross1 = np.cross(v, local) + w0[:, None] * local
    rotated = local + 2.0 * np.cross(v, cross1)
    return rotated + t


def deform_points(skin: dict, mats: np.ndarray, object_world: np.ndarray) -> np.ndarray:
    bind_pts = np.asarray(skin["bind_points"], float).reshape(-1, 3)
    obj_bind = np.asarray(skin["object_bind_matrix"], float).reshape(4, 4)
    weights = np.asarray(skin["weights"], float).reshape(len(bind_pts), -1)
    world = mu.transform_points(obj_bind, bind_pts) if len(bind_pts) else bind_pts.copy()
    if skin.get("method", "Linear") == "Dual Quaternion":
        moved = dual_quaternion_blend(world, mats, weights)
    else:
        moved = linear_blend(world, mats, weights)
    inv = np.linalg.inv(np.asarray(object_world, float))
    return mu.transform_points(inv, moved) if len(moved) else moved


def _validate(obj: SceneObject, skin: dict) -> str:
    bind_pts = np.asarray(skin.get("bind_points", np.zeros((0, 3))), float).reshape(-1, 3)
    if len(bind_pts) != len(obj.mesh.points):
        return f"{obj.name}: mesh has {len(obj.mesh.points)} points but the skin was bound with {len(bind_pts)}"
    w = np.asarray(skin.get("weights", np.zeros((0, 0))), float)
    if w.ndim != 2 or w.shape != (len(bind_pts), len(skin.get("joints", []))):
        return f"{obj.name}: weight matrix has the wrong shape"
    return ""


def deform_skin(scene, obj: SceneObject) -> bool:
    skin = skin_of(obj)
    if skin is None or not skin.get("enabled", True):
        return False
    if _validate(obj, skin):
        return False
    mats = skin_matrices(scene, skin)
    pts = deform_points(skin, mats, obj.world_matrix())
    if pts.shape == obj.mesh.points.shape and np.allclose(pts, obj.mesh.points, atol=1e-9, rtol=0.0):
        return False
    obj.mesh.points = pts
    return True


def bind_skin(scene, obj: SceneObject, joint_objs: Iterable[SceneObject] | None = None,
              auto: bool = True, method: str = "Linear", falloff: float = 4.0,
              max_influences: int = 4, smooth: int = 1) -> SceneObject:
    if obj is None or obj not in scene.objects:
        raise ValueError("no object to bind")
    if jt.is_joint(obj):
        raise ValueError("a joint cannot be skinned")
    chosen = [j for j in (jt.joints(scene) if joint_objs is None else joint_objs) if jt.is_joint(j)]
    if not chosen:
        raise ValueError("the scene has no joints to bind to")
    scene.begin_group()
    try:
        if obj.kind != EDITABLE_KIND:
            obj = scene.make_editable(obj)
            if obj.kind != EDITABLE_KIND:
                raise ValueError(f"{obj.name} has no points to skin")
        if not len(obj.mesh.points):
            raise ValueError(f"{obj.name} has no points to skin")
        old = skin_of(obj)
        if old is not None and len(np.asarray(old["bind_points"]).reshape(-1, 3)) == len(obj.mesh.points):
            obj.mesh.points = np.asarray(old["bind_points"], float).reshape(-1, 3).copy()
        order = sorted(chosen, key=scene.objects.index)
        mats = np.array([j.world_matrix() for j in order])
        skin = {
            "joints": [j.name for j in order],
            "bind_matrices": mats,
            "object_bind_matrix": obj.world_matrix(),
            "bind_points": obj.mesh.points.copy(),
            "weights": np.zeros((len(obj.mesh.points), len(order))),
            "method": method if method in SKIN_METHODS else "Linear",
            "enabled": True,
        }
        if auto:
            skin["weights"] = _auto(scene, obj, skin, falloff, max_influences, smooth)
        data.write(scene, obj, data.SKIN_KEY, skin)
    finally:
        scene.end_group()
    return obj


def _auto(scene, obj: SceneObject, skin: dict, falloff: float, max_influences: int,
          smooth: int) -> np.ndarray:
    mats = np.asarray(skin["bind_matrices"], float).reshape(-1, 4, 4)
    segs = bone_segments(scene, skin_joints(scene, skin), mats)
    world = mu.transform_points(np.asarray(skin["object_bind_matrix"], float),
                                np.asarray(skin["bind_points"], float))
    return compute_auto_weights(world, segs, falloff, max_influences, adjacency(obj.mesh), smooth)


def auto_weights(scene, obj: SceneObject, falloff: float = 4.0, max_influences: int = 4,
                 smooth: int = 1) -> np.ndarray:
    skin = skin_of(obj)
    if skin is None:
        raise ValueError(f"{obj.name} is not bound")
    new = dict(skin)
    new["weights"] = _auto(scene, obj, skin, falloff, max_influences, smooth)
    data.write(scene, obj, data.SKIN_KEY, new)
    return new["weights"]


def apply_weights(scene, obj: SceneObject, weights: np.ndarray) -> None:
    skin = skin_of(obj)
    if skin is None:
        raise ValueError(f"{obj.name} is not bound")
    w = np.asarray(weights, float)
    if w.shape != np.asarray(skin["weights"]).shape:
        raise ValueError("weight matrix shape does not match the skin")
    new = dict(skin)
    new["weights"] = w.copy()
    data.write(scene, obj, data.SKIN_KEY, new)


def set_skin_method(scene, obj: SceneObject, method: str) -> None:
    skin = skin_of(obj)
    if skin is None or method not in SKIN_METHODS:
        return
    new = dict(skin)
    new["method"] = method
    data.write(scene, obj, data.SKIN_KEY, new)


def unbind_skin(scene, obj: SceneObject) -> bool:
    skin = skin_of(obj)
    if skin is None:
        return False
    scene.begin_group()
    try:
        bind_pts = np.asarray(skin["bind_points"], float).reshape(-1, 3)
        jt.checkpoint(scene, "unbind")
        if len(bind_pts) == len(obj.mesh.points):
            obj.mesh.points = bind_pts.copy()
        data.write(scene, obj, data.SKIN_KEY, None)
    finally:
        scene.end_group()
    scene.changed.emit()
    return True


def rebind_skin(scene, obj: SceneObject) -> bool:
    skin = skin_of(obj)
    if skin is None:
        return False
    if _validate(obj, skin):
        raise ValueError(_validate(obj, skin))
    new = dict(skin)
    new["bind_matrices"] = np.array([np.eye(4) if j is None else j.world_matrix()
                                     for j in skin_joints(scene, skin)]).reshape(-1, 4, 4)
    new["object_bind_matrix"] = obj.world_matrix()
    new["bind_points"] = obj.mesh.points.copy()
    data.write(scene, obj, data.SKIN_KEY, new)
    return True


def reset_bind_pose(scene, obj: SceneObject | None = None) -> int:
    targets = [obj] if obj is not None else skinned_objects(scene)
    wanted: dict[int, np.ndarray] = {}
    for o in targets:
        skin = skin_of(o)
        if skin is None:
            continue
        mats = np.asarray(skin["bind_matrices"], float).reshape(-1, 4, 4)
        for j, m in zip(skin_joints(scene, skin), mats):
            if j is not None:
                wanted[id(j)] = m
    if not wanted:
        return 0
    scene.begin_group()
    try:
        jt.checkpoint(scene, "bind_pose")
        count = 0
        for j in scene.objects:
            if id(j) in wanted:
                jt.set_world_matrix(j, wanted[id(j)])
                count += 1
        from . import ik
        for start, tag in ik.ik_tags(scene):
            chain = ik.chain_of(scene, start, tag)
            if chain and any(id(j) in wanted for j in chain):
                ik.sync_to_pose(scene, start)
        for o in targets:
            deform_skin(scene, o)
    finally:
        scene.end_group()
    scene.changed.emit()
    return count


def brush_falloff(distances: np.ndarray, radius: float, kind: str = "Smooth") -> np.ndarray:
    d = np.asarray(distances, float)
    r = float(radius)
    if r <= 0.0:
        return np.zeros_like(d)
    x = np.clip(d / r, 0.0, 1.0)
    inside = d <= r
    if kind == "Constant":
        f = np.ones_like(d)
    elif kind == "Linear":
        f = 1.0 - x
    else:
        f = (1.0 - x * x) ** 2
    return np.where(inside, f, 0.0)


def sphere_distances(points: np.ndarray, center: Iterable[float]) -> np.ndarray:
    return np.linalg.norm(np.asarray(points, float).reshape(-1, 3) - np.asarray(tuple(center), float), axis=1)


def cylinder_distances(points: np.ndarray, origin: Iterable[float], direction: Iterable[float]) -> np.ndarray:
    p = np.asarray(points, float).reshape(-1, 3) - np.asarray(tuple(origin), float)
    d = mu.normalize(direction)
    if not np.any(d):
        return np.linalg.norm(p, axis=1)
    return np.linalg.norm(p - np.outer(p @ d, d), axis=1)


def _rebalance(w: np.ndarray, joint: int, rows: np.ndarray, before: np.ndarray) -> None:
    others = np.ones(w.shape[1], bool)
    others[joint] = False
    if not np.any(others):
        w[rows, joint] = 1.0
        return
    sub = before[rows][:, others]
    osum = sub.sum(axis=1)
    rest = 1.0 - w[rows, joint]
    has = osum > 1e-12
    scaled = sub.copy()
    scaled[has] = sub[has] * (rest[has] / osum[has])[:, None]
    block = w[rows]
    block[:, others] = scaled
    lone = ~has
    block[lone, joint] = 1.0
    w[rows] = block


def paint_weights(weights: np.ndarray, joint: int, falloff: np.ndarray, mode: str = "Add",
                  strength: float = 0.5, normalize: bool = True,
                  adj: tuple[np.ndarray, np.ndarray] | None = None) -> np.ndarray:
    w = np.asarray(weights, float).copy()
    f = np.clip(np.asarray(falloff, float).reshape(-1), 0.0, 1.0)
    if w.ndim != 2 or len(f) != len(w):
        raise ValueError("falloff must have one value per point")
    rows = np.nonzero(f > 0.0)[0]
    if not len(rows):
        return w
    s = float(np.clip(strength, 0.0, 1.0))
    before = w.copy()
    if mode == "Smooth":
        avg = _neighbour_mean(w, adj) if adj is not None else w
        amount = (f[rows] * s)[:, None]
        w[rows] = w[rows] + (avg[rows] - w[rows]) * amount
        return normalize_weights(w, rows) if normalize else w
    if mode == "Normalize":
        return normalize_weights(w, rows)
    if not 0 <= int(joint) < w.shape[1]:
        raise ValueError(f"joint index {joint} out of range")
    j = int(joint)
    if mode == "Add":
        w[rows, j] = np.minimum(1.0, w[rows, j] + f[rows] * s)
    elif mode == "Subtract":
        w[rows, j] = np.maximum(0.0, w[rows, j] - f[rows] * s)
    elif mode == "Replace":
        w[rows, j] = w[rows, j] + (s - w[rows, j]) * f[rows]
    else:
        raise ValueError(f"unknown paint mode {mode!r}")
    if normalize:
        _rebalance(w, j, rows, before)
    return w


def nearest_within(queries: np.ndarray, sources: np.ndarray, radius: float) -> tuple[np.ndarray, np.ndarray]:
    q = np.asarray(queries, float).reshape(-1, 3)
    src = np.asarray(sources, float).reshape(-1, 3)
    best = np.full(len(q), -1, dtype=np.int64)
    best_d = np.full(len(q), np.inf)
    r = float(radius)
    if not len(q) or not len(src) or not r > 0.0:
        return best, best_d
    lo = np.minimum(q.min(axis=0), src.min(axis=0))
    cell = r
    span = np.maximum(q.max(axis=0), src.max(axis=0)) - lo
    dims = np.floor(span / cell).astype(np.int64) + 3
    while float(np.prod(dims.astype(float))) > 4.0e18:
        cell *= 2.0
        dims = np.floor(span / cell).astype(np.int64) + 3
    def keys(cells: np.ndarray) -> np.ndarray:
        return (cells[:, 0] * dims[1] + cells[:, 1]) * dims[2] + cells[:, 2]
    src_cells = np.floor((src - lo) / cell).astype(np.int64) + 1
    src_keys = keys(src_cells)
    order = np.argsort(src_keys, kind="stable")
    sorted_keys = src_keys[order]
    q_cells = np.floor((q - lo) / cell).astype(np.int64) + 1
    reach = int(math.ceil(r / cell))
    rng = range(-reach, reach + 1)
    for dx in rng:
        for dy in rng:
            for dz in rng:
                k = keys(q_cells + np.array([dx, dy, dz], np.int64))
                start = np.searchsorted(sorted_keys, k, side="left")
                stop = np.searchsorted(sorted_keys, k, side="right")
                length = stop - start
                if not np.any(length):
                    continue
                for step in range(int(length.max())):
                    rows = np.nonzero(length > step)[0]
                    cand = order[start[rows] + step]
                    d = np.linalg.norm(q[rows] - src[cand], axis=1)
                    better = d < best_d[rows]
                    if np.any(better):
                        hit = rows[better]
                        best_d[hit] = d[better]
                        best[hit] = cand[better]
    far = best_d > r
    best[far] = -1
    best_d[far] = np.inf
    return best, best_d


def mirror_weight_matrix(points: np.ndarray, weights: np.ndarray, names: Sequence[str], axis: int = 0,
                         positive_to_negative: bool = False, tolerance: float | None = None,
                         center: float = 0.0) -> np.ndarray:
    pts = np.asarray(points, float).reshape(-1, 3)
    w = np.asarray(weights, float).copy()
    if not len(pts):
        return w
    ax = int(axis)
    span = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    tol = span * 1e-3 if tolerance is None else float(tolerance)
    lookup = {n: k for k, n in enumerate(names)}
    perm = np.array([lookup.get(jt.mirror_name(n), k) for k, n in enumerate(names)], int)
    c = float(center)
    coord = pts[:, ax] - c
    src = np.nonzero(coord > tol if positive_to_negative else coord < -tol)[0]
    dst = np.nonzero(coord < -tol if positive_to_negative else coord > tol)[0]
    if not len(src) or not len(dst):
        return w
    reflected = pts[src].copy()
    reflected[:, ax] = 2.0 * c - reflected[:, ax]
    limit = max(tol * 10.0, span * 0.02)
    best, _dist = nearest_within(pts[dst], reflected, limit)
    ok = best >= 0
    if not np.any(ok):
        return w
    rows = dst[ok]
    source_rows = w[src[best[ok]]]
    mirrored = np.zeros_like(source_rows)
    mirrored[:, perm] = source_rows
    w[rows] = mirrored
    return w


def mirror_plane(skin: dict, axis: int = 0) -> float:
    names = list(skin.get("joints", []))
    mats = np.asarray(skin.get("bind_matrices", np.zeros((0, 4, 4))), float).reshape(-1, 4, 4)
    ax = int(axis)
    lookup = {n: k for k, n in enumerate(names)}
    mids = []
    for k, n in enumerate(names):
        other = lookup.get(jt.mirror_name(n))
        if other is not None and other != k:
            mids.append(0.5 * (mats[k][ax, 3] + mats[other][ax, 3]))
    if mids:
        return float(np.mean(mids))
    centre = [mats[k][ax, 3] for k, n in enumerate(names) if jt.mirror_name(n) == n]
    return float(np.mean(centre)) if centre else 0.0


def mirror_weights(scene, obj: SceneObject, axis: int = 0, positive_to_negative: bool = False) -> np.ndarray:
    skin = skin_of(obj)
    if skin is None:
        raise ValueError(f"{obj.name} is not bound")
    bind_pts = np.asarray(skin["bind_points"], float).reshape(-1, 3)
    obj_bind = np.asarray(skin["object_bind_matrix"], float).reshape(4, 4)
    world = mu.transform_points(obj_bind, bind_pts) if len(bind_pts) else bind_pts
    w = mirror_weight_matrix(world, np.asarray(skin["weights"], float), list(skin["joints"]), axis,
                             positive_to_negative, center=mirror_plane(skin, axis))
    apply_weights(scene, obj, w)
    return w


def weight_totals(skin: dict) -> np.ndarray:
    return np.asarray(skin["weights"], float).sum(axis=0)


def influence_counts(skin: dict, threshold: float = 1e-6) -> np.ndarray:
    return (np.asarray(skin["weights"], float) > threshold).sum(axis=1)
