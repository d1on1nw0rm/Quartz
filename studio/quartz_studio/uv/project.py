from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from ..ext import store
from .data import (TAG_KEY, Corners, _basis, corners_of_polys, finite_mesh, finite_points, get_uv_array,
                   polygon_area_3d, set_uv_array, write_object)

__all__ = [
    "PROJECTIONS",
    "AXES",
    "TAG_PROJECTIONS",
    "DEFAULT_TAG",
    "axis_normal",
    "fit_unit",
    "flat_coords",
    "box_coords",
    "spherical_coords",
    "cylindrical_coords",
    "frontal_coords",
    "look_at",
    "camera_view",
    "project",
    "project_flat",
    "project_box",
    "project_spherical",
    "project_cylindrical",
    "project_frontal",
    "get_tag",
    "set_tag",
    "tag_coords",
    "uvw_from_tag",
]

PROJECTIONS = ("Flat", "Box", "Spherical", "Cylindrical", "Frontal")
AXES = ("Auto", "X", "Y", "Z", "Normal")
TAG_PROJECTIONS = ("UVW", "Flat", "Cubic", "Spherical", "Cylindrical", "Frontal")
DEFAULT_TAG = {
    "projection": "Flat",
    "axis": "Auto",
    "tiles": [1.0, 1.0],
    "offset": [0.0, 0.0],
    "fit": True,
    "camera": None,
}


def axis_normal(axis: str, mesh=None, polys: Iterable[int] | None = None,
                corners: Corners | None = None) -> np.ndarray:
    key = str(axis).strip().lower()
    if key in ("x", "+x"):
        return np.array([1.0, 0.0, 0.0])
    if key in ("y", "+y"):
        return np.array([0.0, 1.0, 0.0])
    if key in ("z", "+z"):
        return np.array([0.0, 0.0, 1.0])
    if key == "-x":
        return np.array([-1.0, 0.0, 0.0])
    if key == "-y":
        return np.array([0.0, -1.0, 0.0])
    if key == "-z":
        return np.array([0.0, 0.0, -1.0])
    if mesh is None or not mesh.polygons:
        return np.array([0.0, 0.0, 1.0])
    normals = mesh.polygon_normals()
    areas = polygon_area_3d(mesh, corners)
    idx = list(range(len(mesh.polygons))) if polys is None else [int(p) for p in polys]
    if not idx:
        return np.array([0.0, 0.0, 1.0])
    avg = (normals[idx] * areas[idx][:, None]).sum(axis=0)
    if key == "normal":
        if np.linalg.norm(avg) < 1e-9:
            avg = np.abs(normals[idx] * areas[idx][:, None]).sum(axis=0)
        return avg / max(np.linalg.norm(avg), 1e-12)
    if np.linalg.norm(avg) < 1e-9:
        avg = np.abs(normals[idx] * areas[idx][:, None]).sum(axis=0)
    k = int(np.argmax(np.abs(avg)))
    out = np.zeros(3)
    out[k] = 1.0 if avg[k] >= 0 else -1.0
    return out


def fit_unit(uv: np.ndarray, keep_aspect: bool = True, margin: float = 0.0) -> np.ndarray:
    uv = np.asarray(uv, float)
    if not len(uv):
        return uv.copy()
    lo = uv.min(axis=0)
    span = uv.max(axis=0) - lo
    room = max(1.0 - 2.0 * margin, 1e-6)
    if keep_aspect:
        s = float(max(span.max(), 1e-12))
        out = (uv - lo) / s * room
        extent = span / s * room
        return out + (1.0 - extent) / 2.0
    span = np.where(span < 1e-12, 1.0, span)
    return (uv - lo) / span * room + margin


def _object_box(mesh) -> tuple[np.ndarray, float]:
    if not len(mesh.points):
        return np.zeros(3), 1.0
    lo, hi = mesh.points.min(axis=0), mesh.points.max(axis=0)
    return (lo + hi) / 2.0, float(max((hi - lo).max(), 1e-12))


def _targets(mesh, polys) -> list[int]:
    return list(range(len(mesh.polygons))) if polys is None else sorted({int(p) for p in polys})


def flat_coords(mesh, corners: Corners, idx: np.ndarray, normal: np.ndarray) -> np.ndarray:
    eu, ev = _basis(normal)
    p = mesh.points[corners.vertex[idx]]
    return np.stack([p @ eu, p @ ev], axis=1)


def box_coords(mesh, corners: Corners, polys: list[int], atlas: bool = True) -> tuple[np.ndarray, np.ndarray]:
    normals = mesh.polygon_normals()
    center, size = _object_box(mesh)
    dirs = [np.array(v, float) for v in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
    idx_all: list[int] = []
    uv_all: list[np.ndarray] = []
    for p in polys:
        n = normals[p]
        scores = [float(n @ d) for d in dirs]
        k = int(np.argmax(scores))
        eu, ev = _basis(dirs[k])
        cs = np.arange(corners.starts[p], corners.starts[p + 1])
        pts = mesh.points[corners.vertex[cs]] - center
        uv = np.stack([pts @ eu, pts @ ev], axis=1) / size + 0.5
        if atlas:
            col, row = k % 3, k // 3
            cell = 1.0 / 3.0
            uv = uv * cell + np.array([col * cell, (1 - row) * cell + (1.0 - 2.0 * cell) / 2.0])
        idx_all.extend(cs.tolist())
        uv_all.append(uv)
    if not idx_all:
        return np.zeros(0, dtype=np.int64), np.zeros((0, 2))
    return np.array(idx_all, dtype=np.int64), np.vstack(uv_all)


def _wrap_fix(uv: np.ndarray, corners: Corners, idx: np.ndarray, polar: np.ndarray) -> np.ndarray:
    out = uv.copy()
    pos = {int(c): i for i, c in enumerate(idx)}
    polys = np.unique(corners.poly[idx])
    for p in polys:
        rows = [pos[c] for c in corners.of(int(p)) if c in pos]
        if not rows:
            continue
        rows = np.array(rows)
        normal_rows = rows[~polar[rows]]
        us = out[normal_rows, 0] if len(normal_rows) else out[rows, 0]
        if len(us) and us.max() - us.min() > 0.5:
            low = normal_rows[out[normal_rows, 0] < 0.5]
            out[low, 0] += 1.0
        pr = rows[polar[rows]]
        if len(pr):
            others = rows[~polar[rows]]
            if len(others):
                out[pr, 0] = out[others, 0].mean()
    return out


def spherical_coords(mesh, corners: Corners, idx: np.ndarray, center=None) -> np.ndarray:
    c0, _ = _object_box(mesh)
    center = c0 if center is None else np.asarray(center, float)
    p = mesh.points[corners.vertex[idx]] - center
    r = np.linalg.norm(p, axis=1)
    rxz = np.hypot(p[:, 0], p[:, 2])
    u = 0.5 + np.arctan2(p[:, 0], p[:, 2]) / (2.0 * math.pi)
    v = 0.5 + np.arcsin(np.clip(p[:, 1] / np.maximum(r, 1e-12), -1, 1)) / math.pi
    uv = np.stack([u, v], axis=1)
    polar = rxz <= 1e-6 * np.maximum(r.max() if len(r) else 1.0, 1e-12)
    return _wrap_fix(uv, corners, idx, polar)


def cylindrical_coords(mesh, corners: Corners, idx: np.ndarray, axis: str = "Y",
                       center=None) -> np.ndarray:
    key = str(axis).upper()
    if key == "X":
        a, b, h = 1, 2, 0
    elif key == "Z":
        a, b, h = 0, 1, 2
    else:
        a, b, h = 0, 2, 1
    c0, _ = _object_box(mesh)
    center = c0 if center is None else np.asarray(center, float)
    p = mesh.points[corners.vertex[idx]] - center
    rad = np.hypot(p[:, a], p[:, b])
    u = 0.5 + np.arctan2(p[:, a], p[:, b]) / (2.0 * math.pi)
    allp = mesh.points[:, h] - center[h]
    lo, hi = float(allp.min()), float(allp.max())
    v = (p[:, h] - lo) / max(hi - lo, 1e-12)
    uv = np.stack([u, v], axis=1)
    polar = rad <= 1e-6 * max(float(rad.max()) if len(rad) else 1.0, 1e-12)
    return _wrap_fix(uv, corners, idx, polar)


def look_at(eye, target, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    eye = np.asarray(eye, float)
    fwd = np.asarray(target, float) - eye
    fwd /= max(np.linalg.norm(fwd), 1e-12)
    up = np.asarray(up, float)
    right = np.cross(up, fwd)
    if np.linalg.norm(right) < 1e-9:
        right = np.cross(np.array([0.0, 0.0, 1.0]), fwd)
    right /= max(np.linalg.norm(right), 1e-12)
    true_up = np.cross(fwd, right)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = right, true_up, fwd
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def camera_view(camera) -> tuple[np.ndarray, float | None, bool, float]:
    if isinstance(camera, dict):
        view = np.asarray(camera.get("view", np.eye(4)), float).reshape(4, 4)
        return view, camera.get("focal"), bool(camera.get("ortho", False)), float(camera.get("distance", 1.0))
    if hasattr(camera, "basis"):
        pos, fwd, right, up = camera.basis()
        m = np.eye(4)
        m[0, :3], m[1, :3], m[2, :3] = right, up, fwd
        m[:3, 3] = -m[:3, :3] @ np.asarray(pos, float)
        return m, float(getattr(camera, "focal", 1.0)), bool(getattr(camera, "ortho", False)), \
            float(getattr(camera, "distance", 1.0))
    return np.asarray(camera, float).reshape(4, 4), 1.0, False, 1.0


def frontal_coords(world: np.ndarray, view: np.ndarray, focal: float | None = None,
                   ortho: bool = False, distance: float = 1.0, aspect: float = 1.0) -> np.ndarray:
    world = np.atleast_2d(np.asarray(world, float))
    cam = world @ view[:3, :3].T + view[:3, 3]
    if ortho:
        xy = cam[:, :2] / max(distance, 1e-12)
    else:
        z = np.where(np.abs(cam[:, 2]) < 1e-9, 1e-9, cam[:, 2])
        xy = cam[:, :2] / z[:, None]
    if focal is None:
        return xy
    return np.stack([0.5 + focal * xy[:, 0], 0.5 + focal * xy[:, 1] * aspect], axis=1)


def project(obj, kind: str, polys: Iterable[int] | None = None, *, axis: str = "Auto",
            fit: bool = True, keep_aspect: bool = True, atlas: bool = True, camera=None,
            aspect: float = 1.0, write: bool = True) -> np.ndarray:
    corners = Corners(obj.mesh)
    uv = get_uv_array(obj, corners)
    mesh = finite_mesh(obj.mesh)
    targets = _targets(mesh, polys)
    idx = corners_of_polys(corners, targets)
    if not len(idx):
        return uv
    name = str(kind).strip().lower()
    if name in ("flat", "planar"):
        n = axis_normal(axis, mesh, targets, corners)
        coords = flat_coords(mesh, corners, idx, n)
        if fit:
            coords = fit_unit(coords, keep_aspect)
        else:
            center, size = _object_box(mesh)
            eu, ev = _basis(n)
            coords = (coords - np.array([center @ eu, center @ ev])) / size + 0.5
    elif name in ("box", "cubic"):
        idx, coords = box_coords(mesh, corners, targets, atlas=atlas)
    elif name == "spherical":
        coords = spherical_coords(mesh, corners, idx)
        if fit:
            coords = _fit_wrapped(coords, keep_aspect=False)
    elif name == "cylindrical":
        cyl_axis = "Y" if str(axis).lower() in ("auto", "normal") else str(axis)
        coords = cylindrical_coords(mesh, corners, idx, cyl_axis)
        if fit:
            coords = _fit_wrapped(coords, keep_aspect=False)
    elif name in ("frontal", "camera"):
        if camera is None:
            camera = look_at((0.0, 0.0, -1000.0), (0.0, 0.0, 0.0))
        view, focal, ortho, distance = camera_view(camera)
        world = obj.to_world(mesh.points[corners.vertex[idx]])
        if fit or focal is None:
            coords = frontal_coords(world, view, None, ortho, distance)
            coords = fit_unit(coords, keep_aspect)
        else:
            coords = frontal_coords(world, view, focal, ortho, distance, aspect)
    else:
        raise ValueError(f"unknown projection {kind!r}")
    uv[idx] = np.where(np.isfinite(coords), coords, 0.0)
    if write:
        set_uv_array(obj, uv, corners)
    return uv


def _fit_wrapped(coords: np.ndarray, keep_aspect: bool = False) -> np.ndarray:
    coords = np.asarray(coords, float)
    if not len(coords):
        return coords.copy()
    lo = coords.min(axis=0)
    hi = coords.max(axis=0)
    span = np.where(hi - lo < 1e-12, 1.0, hi - lo)
    out = (coords - lo) / span
    if span[0] >= 1.0 - 1e-6:
        out[:, 0] = coords[:, 0] - lo[0]
    if keep_aspect:
        s = float(span.max())
        out[:, 1] = (coords[:, 1] - lo[1]) / s
    return out


def project_flat(obj, axis: str = "Auto", polys=None, fit: bool = True, keep_aspect: bool = True):
    return project(obj, "Flat", polys, axis=axis, fit=fit, keep_aspect=keep_aspect)


def project_box(obj, polys=None, atlas: bool = True):
    return project(obj, "Box", polys, atlas=atlas)


def project_spherical(obj, polys=None, fit: bool = True):
    return project(obj, "Spherical", polys, fit=fit)


def project_cylindrical(obj, axis: str = "Y", polys=None, fit: bool = True):
    return project(obj, "Cylindrical", polys, axis=axis, fit=fit)


def project_frontal(obj, camera, polys=None, fit: bool = False, aspect: float = 1.0):
    return project(obj, "Frontal", polys, camera=camera, fit=fit, aspect=aspect)


def get_tag(obj) -> dict:
    raw = store.get_object(obj, TAG_KEY)
    tag = dict(DEFAULT_TAG)
    if isinstance(raw, dict):
        tag.update(store.from_json(raw))
    tag["tiles"] = [float(x) for x in list(tag.get("tiles") or [1.0, 1.0])[:2]]
    tag["offset"] = [float(x) for x in list(tag.get("offset") or [0.0, 0.0])[:2]]
    if tag.get("projection") not in TAG_PROJECTIONS:
        tag["projection"] = DEFAULT_TAG["projection"]
    return tag


def set_tag(obj, **values) -> dict:
    tag = get_tag(obj)
    for key, value in values.items():
        if key in ("tiles", "offset"):
            value = [float(value[0]), float(value[1])]
        elif key == "camera" and value is not None and not isinstance(value, dict):
            view, focal, ortho, distance = camera_view(value)
            value = {"view": view.tolist(), "focal": focal, "ortho": ortho, "distance": distance}
        tag[key] = value
    write_object(obj, TAG_KEY, store.to_json(tag))
    return tag


def tag_coords(obj, tag: dict | None = None) -> np.ndarray:
    tag = get_tag(obj) if tag is None else {**get_tag(obj), **tag}
    kind = tag["projection"]
    if kind == "UVW":
        uv = get_uv_array(obj)
    else:
        mapped = {"Cubic": "Box"}.get(kind, kind)
        uv = project(obj, mapped, None, axis=tag.get("axis", "Auto"), fit=bool(tag.get("fit", True)),
                     camera=tag.get("camera"), write=False)
    tiles = np.asarray(tag["tiles"], float)
    offset = np.asarray(tag["offset"], float)
    return uv * tiles + offset


def uvw_from_tag(obj, tag: dict | None = None, switch_to_uvw: bool = True) -> np.ndarray:
    uv = tag_coords(obj, tag)
    set_uv_array(obj, uv)
    if switch_to_uvw:
        set_tag(obj, projection="UVW", tiles=[1.0, 1.0], offset=[0.0, 0.0])
    return uv
