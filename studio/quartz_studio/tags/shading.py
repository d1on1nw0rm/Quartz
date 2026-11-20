from __future__ import annotations

import itertools
import math
from typing import Iterable

import numpy as np

from ..ext import store
from .core import find_tag_by_name, find_tags, first_tag, selection_items, tags_of, update_tag
from .mathutil import rotation_matrix

__all__ = [
    "SHADING_MODES",
    "PROJECTIONS",
    "PROJECTION_LABELS",
    "SIDES",
    "COMPOSITING_FLAGS",
    "SELECTIONS_KEY",
    "corner_layout",
    "phong_normals",
    "flat_normals",
    "object_normals",
    "phong_break_edges",
    "display_state",
    "compositing_flags",
    "projection_frame",
    "projection_label",
    "tag_tiling",
    "tag_offset",
    "projection_uvs",
    "uvw_coordinates",
    "material_polygons",
    "material_assignments",
    "material_side_visible",
    "fit_projection",
    "generate_uvw",
]

SHADING_MODES = ("Smooth Shading", "Smooth Shading (Lines)", "Quick Shading",
                 "Quick Shading (Lines)", "Constant Shading", "Constant Shading (Lines)",
                 "Hidden Line", "Lines", "Wireframe", "Box", "Skeleton")

PROJECTIONS = ("uvw", "spherical", "cylindrical", "flat", "cubic", "frontal", "shrinkwrap")
PROJECTION_LABELS = ("UVW Mapping", "Spherical", "Cylindrical", "Flat", "Cubic", "Frontal",
                     "Shrink Wrapping")

SIDES = ("Both", "Front", "Back")

COMPOSITING_FLAGS = ("cast_shadows", "receive_shadows", "self_shadowing", "seen_by_camera",
                     "seen_by_rays", "seen_by_gi", "seen_by_transparency", "holdout")

SELECTIONS_KEY = "selections"


def _edge_key(a: int, b: int) -> tuple[int, int]:
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


def corner_layout(mesh) -> dict:
    polys = mesh.polygons
    sizes = np.fromiter((len(p) for p in polys), int, len(polys))
    total = int(sizes.sum()) if len(sizes) else 0
    verts = np.fromiter(itertools.chain.from_iterable(polys), int, total)
    poly_of = np.repeat(np.arange(len(polys)), sizes)
    starts = np.cumsum(sizes) - sizes
    if total:
        local = np.arange(total) - starts[poly_of]
        size_c = sizes[poly_of]
        nxt = starts[poly_of] + (local + 1) % size_c
        prv = starts[poly_of] + (local - 1) % size_c
    else:
        nxt = np.zeros(0, int)
        prv = np.zeros(0, int)
    return {"sizes": sizes, "verts": verts, "poly_of": poly_of, "starts": starts,
            "next": nxt, "prev": prv, "splits": np.cumsum(sizes)[:-1] if len(sizes) else sizes}


def _split(values: np.ndarray, layout: dict) -> list[np.ndarray]:
    if not len(layout["sizes"]):
        return []
    return [np.array(a) for a in np.split(values, layout["splits"])]


def flat_normals(mesh) -> list[np.ndarray]:
    lay = corner_layout(mesh)
    fn = mesh.polygon_normals()
    return _split(fn[lay["poly_of"]] if len(lay["poly_of"]) else np.zeros((0, 3)), lay)


def _corner_weights(pts: np.ndarray, lay: dict) -> np.ndarray:
    v = lay["verts"]
    if not len(v):
        return np.zeros(0)
    u = pts[v[lay["prev"]]] - pts[v]
    w = pts[v[lay["next"]]] - pts[v]
    nu = np.linalg.norm(u, axis=1)
    nw = np.linalg.norm(w, axis=1)
    ok = (nu > 1e-12) & (nw > 1e-12)
    cos = np.zeros(len(v))
    cos[ok] = np.sum(u[ok] * w[ok], axis=1) / (nu[ok] * nw[ok])
    ang = np.where(ok, np.arccos(np.clip(cos, -1.0, 1.0)), 0.0)
    return np.maximum(ang, 1e-6)


def _components(count: int, i: np.ndarray, j: np.ndarray) -> np.ndarray:
    lab = np.arange(count)
    if not len(i):
        return lab
    while True:
        m = np.minimum(lab[i], lab[j])
        new = lab.copy()
        np.minimum.at(new, i, m)
        np.minimum.at(new, j, m)
        new = new[new]
        if np.array_equal(new, lab):
            return lab
        lab = new


def phong_normals(mesh, angle_limit: bool = True, angle: float = 80.0,
                  breaks: Iterable | None = None) -> list[np.ndarray]:
    lay = corner_layout(mesh)
    pts = mesh.points
    fn = mesh.polygon_normals()
    verts, poly_of, nxt = lay["verts"], lay["poly_of"], lay["next"]
    count = len(verts)
    if not count:
        return _split(np.zeros((0, 3)), lay)
    n = max(len(pts), int(verts.max()) + 1) + 1
    a = np.minimum(verts, verts[nxt])
    b = np.maximum(verts, verts[nxt])
    code = a * n + b
    valid = a != b
    br = [_edge_key(e[0], e[1]) for e in (breaks or ())]
    if br:
        bcode = np.array([x * n + y for x, y in br], dtype=code.dtype)
        valid &= ~np.isin(code, bcode)
    cand = np.nonzero(valid)[0]
    order = cand[np.argsort(code[cand], kind="stable")]
    pi: list = []
    pj: list = []
    if len(order):
        _u, first, counts = np.unique(code[order], return_index=True, return_counts=True)
        two = first[counts == 2]
        if len(two):
            pi.append(order[two])
            pj.append(order[two + 1])
        for f, c in zip(first[counts > 2], counts[counts > 2]):
            run = order[f:f + c]
            ii, jj = np.triu_indices(len(run), 1)
            pi.append(run[ii])
            pj.append(run[jj])
    if pi:
        c1 = np.concatenate(pi)
        c2 = np.concatenate(pj)
        keep = poly_of[c1] != poly_of[c2]
        if angle_limit:
            cos_limit = math.cos(math.radians(max(0.0, min(180.0, float(angle)))))
            dots = np.sum(fn[poly_of[c1]] * fn[poly_of[c2]], axis=1)
            keep &= dots >= cos_limit - 1e-9
        c1, c2 = c1[keep], c2[keep]
        s1, t1, s2, t2 = c1, nxt[c1], c2, nxt[c2]
        same = verts[s1] == verts[s2]
        ji = np.concatenate([s1, t1])
        jj = np.concatenate([np.where(same, s2, t2), np.where(same, t2, s2)])
    else:
        ji = jj = np.zeros(0, int)
    lab = _components(count, ji, jj)
    w = _corner_weights(pts, lay)
    sums = np.zeros((count, 3))
    np.add.at(sums, lab, fn[poly_of] * w[:, None])
    out = sums[lab]
    ln = np.linalg.norm(out, axis=1)
    ok = ln > 1e-12
    out[ok] = out[ok] / ln[ok][:, None]
    out[~ok] = fn[poly_of][~ok]
    return _split(out, lay)


def phong_break_edges(tag: dict | None) -> list[tuple[int, int]]:
    if not tag or not tag.get("use_edge_breaks", True):
        return []
    return [_edge_key(e[0], e[1]) for e in tag.get("edge_breaks", [])]


def object_normals(obj) -> list[np.ndarray]:
    tag = first_tag(obj, "phong")
    if tag is None:
        return flat_normals(obj.mesh)
    return phong_normals(obj.mesh, bool(tag.get("angle_limit", True)), float(tag.get("angle", 80.0)),
                         phong_break_edges(tag))


def display_state(scene, obj) -> dict:
    state = {"visibility": 1.0, "shading": "", "backface_culling": False, "textures": True,
             "xray": False, "tag": False}
    chain = []
    o = obj
    while o is not None:
        chain.append(o)
        o = o.parent
    vis = 1.0
    for depth, o in enumerate(chain):
        tag = first_tag(o, "display")
        if tag is None:
            continue
        if tag.get("use_visibility", True):
            vis *= max(0.0, min(100.0, float(tag.get("visibility", 100.0)))) / 100.0
        if depth == 0 or tag.get("affect_children", True):
            if not state["shading"] and tag.get("use_shading", False):
                state["shading"] = str(tag.get("shading_mode", SHADING_MODES[0]))
        if depth == 0:
            state["tag"] = True
            state["backface_culling"] = bool(tag.get("backface_culling", False))
            state["textures"] = bool(tag.get("textures", True))
            state["xray"] = bool(tag.get("xray", False))
    state["visibility"] = vis
    return state


def compositing_flags(obj) -> dict:
    defaults = {k: k != "holdout" for k in COMPOSITING_FLAGS}
    tag = first_tag(obj, "compositing")
    o = obj.parent
    while tag is None and o is not None:
        tag = first_tag(o, "compositing")
        o = o.parent
    if tag is None:
        return defaults
    return {k: bool(tag.get(k, defaults[k])) for k in COMPOSITING_FLAGS}


def projection_label(value: str) -> str:
    if value in PROJECTIONS:
        return PROJECTION_LABELS[PROJECTIONS.index(value)]
    return str(value)


def _projection_id(value) -> str:
    v = str(value or "uvw").strip().lower()
    if v in PROJECTIONS:
        return v
    for pid, label in zip(PROJECTIONS, PROJECTION_LABELS):
        if v == label.lower():
            return pid
    if v in ("shrink wrapping", "shrink_wrap", "shrink"):
        return "shrinkwrap"
    return "flat"


def tag_tiling(tag: dict) -> np.ndarray:
    t = tag.get("tiling")
    if t is not None:
        try:
            arr = np.asarray(t, float).reshape(-1)
            if len(arr) >= 2:
                return arr[:2].copy()
        except (TypeError, ValueError):
            pass
    return np.array([float(tag.get("tiles_u", 1.0)), float(tag.get("tiles_v", 1.0))])


def tag_offset(tag: dict) -> np.ndarray:
    o = tag.get("offset")
    if o is not None:
        try:
            arr = np.asarray(o, float).reshape(-1)
            if len(arr) >= 2:
                return arr[:2].copy()
        except (TypeError, ValueError):
            pass
    return np.array([float(tag.get("offset_u", 0.0)), float(tag.get("offset_v", 0.0))]) / 100.0


def projection_frame(tag: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = np.asarray(tag.get("proj_offset", [0.0, 0.0, 0.0]), float)
    rot = rotation_matrix(tag.get("proj_rotation", [0.0, 0.0, 0.0]))
    size = np.asarray(tag.get("proj_size", [100.0, 100.0, 100.0]), float)
    size = np.where(np.abs(size) > 1e-9, size, 1.0)
    return center, rot, size


def _fix_seam(us: np.ndarray, poly_of: np.ndarray, count: int) -> np.ndarray:
    if not len(us):
        return us
    hi = np.full(count, -np.inf)
    lo = np.full(count, np.inf)
    np.maximum.at(hi, poly_of, us)
    np.minimum.at(lo, poly_of, us)
    wide = (hi - lo > 0.5)[poly_of]
    us = us.copy()
    us[wide & (us < 0.5)] += 1.0
    return us


def uvw_coordinates(obj) -> list[np.ndarray] | None:
    tag = first_tag(obj, "uvw", enabled_only=False)
    if tag is None:
        return None
    data = tag.get("uvw") or []
    polys = obj.mesh.polygons
    if len(data) != len(polys):
        return None
    out = []
    for poly, uv in zip(polys, data):
        arr = np.asarray(uv, float).reshape(-1, 2) if len(uv) else np.zeros((0, 2))
        if len(arr) != len(poly):
            return None
        out.append(arr)
    return out


def _frontal(obj, mesh, center, size, camera_position) -> np.ndarray | None:
    if camera_position is None:
        return None
    m = obj.world_matrix()
    world = mesh.points @ m[:3, :3].T + m[:3, 3]
    cam = np.asarray(camera_position, float)
    center_w = m[:3, :3] @ center + m[:3, 3]
    f = center_w - cam
    dist = float(np.linalg.norm(f))
    if dist < 1e-9:
        return None
    f = f / dist
    right = np.cross(f, np.array([0.0, 1.0, 0.0]))
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1.0, 0.0, 0.0])
    right = right / np.linalg.norm(right)
    upv = np.cross(right, f)
    d = world - cam
    depth = d @ f
    depth = np.where(np.abs(depth) > 1e-9, depth, 1e-9)
    sx = (d @ right) / depth * dist / size[0]
    sy = (d @ upv) / depth * dist / size[1]
    return np.column_stack([0.5 + 0.5 * sx, 0.5 + 0.5 * sy])


def _raw_uvs(obj, tag: dict, camera_position=None) -> list[np.ndarray]:
    mesh = obj.mesh
    projection = _projection_id(tag.get("projection", "uvw"))
    if projection == "uvw":
        uvw = uvw_coordinates(obj)
        if uvw is not None:
            return [a.copy() for a in uvw]
        projection = "flat"
    lay = corner_layout(mesh)
    verts, poly_of = lay["verts"], lay["poly_of"]
    if not len(verts):
        return _split(np.zeros((0, 2)), lay)
    center, rot, size = projection_frame(tag)
    q = (((mesh.points - center) @ rot) / size)[verts]
    if projection == "frontal":
        front = _frontal(obj, mesh, center, size, camera_position)
        if front is None:
            projection = "flat"
        else:
            return _split(front[verts], lay)
    if projection == "cylindrical":
        us = 0.5 + np.arctan2(q[:, 0], q[:, 2]) / (2.0 * math.pi)
        uv = np.column_stack([_fix_seam(us, poly_of, len(lay["sizes"])), 0.5 + 0.5 * q[:, 1]])
    elif projection == "spherical":
        r = np.linalg.norm(q, axis=1)
        r = np.where(r > 1e-12, r, 1.0)
        us = 0.5 + np.arctan2(q[:, 0], q[:, 2]) / (2.0 * math.pi)
        vs = 0.5 + np.arcsin(np.clip(q[:, 1] / r, -1.0, 1.0)) / math.pi
        uv = np.column_stack([_fix_seam(us, poly_of, len(lay["sizes"])), vs])
    elif projection == "shrinkwrap":
        r = np.linalg.norm(q, axis=1)
        r = np.where(r > 1e-12, r, 1.0)
        d = q / r[:, None]
        theta = np.arccos(np.clip(d[:, 1], -1.0, 1.0))
        phi = np.arctan2(d[:, 0], d[:, 2])
        rho = theta / math.pi * 0.5
        uv = np.column_stack([0.5 + rho * np.sin(phi), 0.5 + rho * np.cos(phi)])
    elif projection == "cubic":
        fn = (mesh.polygon_normals() @ rot)[poly_of]
        axis = np.argmax(np.abs(fn), axis=1)
        sign = np.where(fn[np.arange(len(fn)), axis] >= 0, 1.0, -1.0)
        a = np.where(axis == 0, -sign * q[:, 2], np.where(axis == 1, q[:, 0], sign * q[:, 0]))
        b = np.where(axis == 1, -sign * q[:, 2], q[:, 1])
        uv = np.column_stack([0.5 + 0.5 * a, 0.5 + 0.5 * b])
    else:
        uv = np.column_stack([0.5 + 0.5 * q[:, 0], 0.5 + 0.5 * q[:, 1]])
    return _split(uv, lay)


def projection_uvs(obj, tag: dict, camera_position=None, tiled: bool = True) -> list[np.ndarray]:
    raw = _raw_uvs(obj, tag, camera_position)
    if not tiled:
        return raw
    tiles = tag_tiling(tag)
    offset = tag_offset(tag)
    return [uv * tiles + offset for uv in raw]


def _store_selection(obj, name: str) -> set | None:
    sels = store.get_object(obj, SELECTIONS_KEY, None)
    if not isinstance(sels, dict) or name not in sels:
        return None
    entry = sels[name]
    if isinstance(entry, dict):
        if entry.get("type", "polygons") not in ("polygons", "polygon"):
            return None
        entry = entry.get("indices", [])
    try:
        return {int(i) for i in entry}
    except TypeError:
        return None


def material_polygons(obj, tag: dict) -> set[int]:
    allp = set(range(len(obj.mesh.polygons)))
    name = str(tag.get("selection", "") or "")
    if not name:
        return allp
    found = find_tag_by_name(obj, name, "polygon_selection")
    if found is not None:
        return allp & set(selection_items(obj, found[1]))
    return allp & (_store_selection(obj, name) or set())


def material_side_visible(tag: dict, front: bool) -> bool:
    side = tag.get("side", "Both")
    if side == "Front":
        return bool(front)
    if side == "Back":
        return not front
    return True


def material_assignments(obj, front: bool = True) -> list[int | None]:
    out: list[int | None] = [None] * len(obj.mesh.polygons)
    for i, tag in find_tags(obj, "material", enabled_only=True):
        if not material_side_visible(tag, front):
            continue
        for k in material_polygons(obj, tag):
            out[k] = i
    return out


def fit_projection(scene, obj, index: int) -> bool:
    tags = tags_of(obj)
    if not 0 <= index < len(tags) or not len(obj.mesh.points):
        return False
    lo, hi = obj.mesh.bounds()
    center = (lo + hi) / 2.0
    half = np.maximum((hi - lo) / 2.0, 1e-3)
    update_tag(obj, index, proj_offset=center.tolist(), proj_rotation=[0.0, 0.0, 0.0],
               proj_size=half.tolist())
    return True


def generate_uvw(scene, obj, index: int, camera_position=None) -> int | None:
    from .core import get_tags, owner_scene, set_tags
    from .registry import get_tag_spec, make_tag
    tags = tags_of(obj)
    if not 0 <= index < len(tags):
        return None
    uvs = projection_uvs(obj, dict(tags[index]), camera_position, tiled=False)
    data = [uv.tolist() for uv in uvs]
    new = get_tags(obj)
    found = [i for i, t in enumerate(new) if t.get("type") == "uvw"]
    if found:
        uvw_index = found[0]
        new[uvw_index] = dict(new[uvw_index], uvw=data)
    else:
        taken = {t.get("name") for t in new}
        name, n = get_tag_spec("uvw").label, 1
        base = name
        while name in taken:
            name = f"{base}.{n}"
            n += 1
        uvw_tag = make_tag("uvw", name)
        uvw_tag["uvw"] = data
        new.append(uvw_tag)
        uvw_index = len(new) - 1
    new[index] = dict(new[index], projection="uvw")
    owner = scene if scene is not None and obj in getattr(scene, "objects", ()) else owner_scene(obj)
    set_tags(obj, new, scene=owner)
    return uvw_index
