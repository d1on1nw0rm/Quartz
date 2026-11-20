from __future__ import annotations

import math

import numpy as np

from ..objects.registry import SPECS, ObjectSpec, Param, register
from ..scene import Mesh

__all__ = ["LIGHT_KIND", "CAMERA_KIND", "LIGHT_TYPES", "FALLOFFS", "PROJECTIONS", "LIGHT_DEFAULTS",
           "CAMERA_DEFAULTS", "LIGHT_SPEC", "CAMERA_SPEC", "light_gizmo", "camera_gizmo",
           "is_light", "is_camera", "light_params", "camera_params", "ensure_registered"]

LIGHT_KIND = "light"
CAMERA_KIND = "camera"
LIGHT_TYPES = ("Point", "Spot", "Infinite", "Area")
FALLOFFS = ("None", "Inverse Square", "Linear")
PROJECTIONS = ("Perspective", "Parallel")
GIZMO = 40.0


def _segments_mesh(segs) -> Mesh:
    arr = np.asarray(segs, float).reshape(-1, 2, 3)
    if not len(arr):
        return Mesh.empty()
    pts = arr.reshape(-1, 3)
    edges = [(2 * i, 2 * i + 1) for i in range(len(arr))]
    return Mesh(pts, [], edges)


def _circle(radius: float, z: float, n: int = 16) -> list:
    out = []
    for i in range(n):
        a0 = 2.0 * math.pi * i / n
        a1 = 2.0 * math.pi * (i + 1) / n
        out.append(((radius * math.cos(a0), radius * math.sin(a0), z),
                    (radius * math.cos(a1), radius * math.sin(a1), z)))
    return out


def light_gizmo(values: dict) -> Mesh:
    kind = str(values.get("light_type", "Point"))
    r = GIZMO
    segs: list = []
    if kind == "Point":
        for axis in range(3):
            a = [0.0, 0.0, 0.0]
            b = [0.0, 0.0, 0.0]
            a[axis] = -r
            b[axis] = r
            segs.append((tuple(a), tuple(b)))
        d = r * 0.6
        segs += [((-d, -d, -d), (d, d, d)), ((-d, d, -d), (d, -d, d)),
                 ((d, -d, -d), (-d, d, d)), ((d, d, -d), (-d, -d, d))]
    elif kind == "Spot":
        length = 3.0 * r
        angle = math.radians(max(1.0, min(89.0, float(values.get("cone_angle", 30.0)))))
        rad = length * math.tan(angle)
        segs += _circle(rad, length)
        for i in range(4):
            a = 2.0 * math.pi * i / 4
            segs.append(((0.0, 0.0, 0.0), (rad * math.cos(a), rad * math.sin(a), length)))
    elif kind == "Infinite":
        length = 3.0 * r
        segs.append(((0.0, 0.0, 0.0), (0.0, 0.0, length)))
        h = r * 0.35
        segs += [((0.0, 0.0, length), (h, 0.0, length - h)), ((0.0, 0.0, length), (-h, 0.0, length - h)),
                 ((0.0, 0.0, length), (0.0, h, length - h)), ((0.0, 0.0, length), (0.0, -h, length - h))]
        segs += _circle(r * 0.5, 0.0, 12)
    else:
        w = float(values.get("area_width", 100.0)) / 2.0
        h = float(values.get("area_height", 100.0)) / 2.0
        c = [(-w, -h, 0.0), (w, -h, 0.0), (w, h, 0.0), (-w, h, 0.0)]
        segs += [(c[i], c[(i + 1) % 4]) for i in range(4)]
        segs += [(c[0], c[2]), (c[1], c[3]), ((0.0, 0.0, 0.0), (0.0, 0.0, max(w, h)))]
    return _segments_mesh(segs)


def camera_gizmo(values: dict) -> Mesh:
    focal = float(values.get("focal_length", 36.0)) / max(float(values.get("sensor_width", 36.0)), 1e-6)
    depth = 2.0 * GIZMO
    hw = depth / (2.0 * max(focal, 1e-3))
    hh = hw * 9.0 / 16.0
    if str(values.get("projection", "Perspective")) == "Parallel":
        hw = float(values.get("ortho_width", 1000.0)) / 2.0
        hh = hw * 9.0 / 16.0
        far = [(-hw, -hh, depth), (hw, -hh, depth), (hw, hh, depth), (-hw, hh, depth)]
        near = [(x, y, 0.0) for x, y, _z in far]
        segs = [(far[i], far[(i + 1) % 4]) for i in range(4)]
        segs += [(near[i], near[(i + 1) % 4]) for i in range(4)]
        segs += [(near[i], far[i]) for i in range(4)]
    else:
        far = [(-hw, -hh, depth), (hw, -hh, depth), (hw, hh, depth), (-hw, hh, depth)]
        segs = [(far[i], far[(i + 1) % 4]) for i in range(4)]
        segs += [((0.0, 0.0, 0.0), f) for f in far]
    segs.append(((-hw * 0.4, hh * 1.1, depth), (0.0, hh * 1.5, depth)))
    segs.append(((0.0, hh * 1.5, depth), (hw * 0.4, hh * 1.1, depth)))
    box = GIZMO * 0.5
    cube = [(-box, -box, -2 * box), (box, -box, -2 * box), (box, box, -2 * box), (-box, box, -2 * box)]
    back = [(x, y, 0.0) for x, y, _z in cube]
    segs += [(cube[i], cube[(i + 1) % 4]) for i in range(4)]
    segs += [(back[i], back[(i + 1) % 4]) for i in range(4)]
    segs += [(cube[i], back[i]) for i in range(4)]
    return _segments_mesh(segs)


def _build_light(values: dict, _inputs: list) -> Mesh:
    return light_gizmo(values)


def _build_camera(values: dict, _inputs: list) -> Mesh:
    return camera_gizmo(values)


LIGHT_PARAMS = (
    Param("light_type", "Type", "choice", "Point", choices=LIGHT_TYPES, group="Light"),
    Param("color", "Color", "vector", (1.0, 1.0, 1.0), minimum=0.0, maximum=1.0, step=0.05, group="Light"),
    Param("intensity", "Intensity", "float", 1.0, minimum=0.0, maximum=1000.0, step=0.1, group="Light"),
    Param("falloff", "Falloff", "choice", "Inverse Square", choices=FALLOFFS, group="Light"),
    Param("radius", "Radius", "distance", 500.0, minimum=0.01, group="Light"),
    Param("cone_angle", "Cone Angle", "angle", 30.0, minimum=1.0, maximum=89.0, group="Spot"),
    Param("penumbra", "Penumbra", "angle", 8.0, minimum=0.0, maximum=89.0, group="Spot"),
    Param("area_width", "Area Width", "distance", 100.0, minimum=0.01, group="Area"),
    Param("area_height", "Area Height", "distance", 100.0, minimum=0.01, group="Area"),
    Param("area_samples", "Area Samples", "int", 9, minimum=1.0, maximum=64.0, group="Area"),
    Param("shadow", "Shadow", "bool", True, group="Shadow"),
    Param("shadow_softness", "Shadow Softness", "float", 1.0, minimum=0.0, maximum=8.0, step=0.1,
          group="Shadow"),
    Param("shadow_bias", "Shadow Bias", "float", 1.0, minimum=0.0, maximum=20.0, step=0.1, group="Shadow"),
)

CAMERA_PARAMS = (
    Param("projection", "Projection", "choice", "Perspective", choices=PROJECTIONS, group="Camera"),
    Param("focal_length", "Focal Length", "float", 36.0, minimum=1.0, maximum=2000.0, step=1.0, unit="mm",
          group="Camera"),
    Param("sensor_width", "Sensor Size", "float", 36.0, minimum=1.0, maximum=200.0, step=1.0, unit="mm",
          group="Camera"),
    Param("ortho_width", "Parallel Width", "distance", 1000.0, minimum=0.01, group="Camera"),
    Param("near_clip", "Near Clip", "distance", 1.0, minimum=0.001, group="Camera"),
)

LIGHT_DEFAULTS = {p.key: p.default for p in LIGHT_PARAMS}
CAMERA_DEFAULTS = {p.key: p.default for p in CAMERA_PARAMS}

LIGHT_SPEC: ObjectSpec | None = None
CAMERA_SPEC: ObjectSpec | None = None


def ensure_registered() -> None:
    global LIGHT_SPEC, CAMERA_SPEC
    if LIGHT_KIND in SPECS:
        LIGHT_SPEC = SPECS[LIGHT_KIND]
    else:
        LIGHT_SPEC = register(ObjectSpec(
            id=LIGHT_KIND, label="Light", category="null", build=_build_light, params=LIGHT_PARAMS,
            inputs="none", icon="light", description="Light source used by the renderer"))
    if CAMERA_KIND in SPECS:
        CAMERA_SPEC = SPECS[CAMERA_KIND]
    else:
        CAMERA_SPEC = register(ObjectSpec(
            id=CAMERA_KIND, label="Camera", category="null", build=_build_camera, params=CAMERA_PARAMS,
            inputs="none", icon="camera", description="Camera the renderer can look through"))


def is_light(obj) -> bool:
    return getattr(obj, "kind", "") == LIGHT_KIND


def is_camera(obj) -> bool:
    return getattr(obj, "kind", "") == CAMERA_KIND


def light_params(obj) -> dict:
    values = dict(LIGHT_DEFAULTS)
    values.update(getattr(obj, "params", {}) or {})
    return values


def camera_params(obj) -> dict:
    values = dict(CAMERA_DEFAULTS)
    values.update(getattr(obj, "params", {}) or {})
    return values


ensure_registered()
