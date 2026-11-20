from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import bridges
from .objects import is_camera, is_light, light_params
from .shading import Light, normalize

__all__ = ["Geometry", "FrozenObject", "ObjectCapture", "triangulate_object", "capture_scene",
           "geometry_from_capture", "build_geometry", "scene_lights", "default_lights", "light_from_object",
           "camera_objects", "light_objects"]

LIGHT_KIND_MAP = {"Point": "point", "Spot": "spot", "Infinite": "infinite", "Area": "area"}
FROZEN_KEYS = ("tags", "uvw")


@dataclass
class Geometry:
    tris: np.ndarray = field(default_factory=lambda: np.zeros((0, 3, 3)))
    normals: np.ndarray = field(default_factory=lambda: np.zeros((0, 3, 3)))
    face_normals: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    uvs: np.ndarray = field(default_factory=lambda: np.zeros((0, 3, 2)))
    local: np.ndarray = field(default_factory=lambda: np.zeros((0, 3, 3)))
    obj: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    mat: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    cast: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    receive: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    visible: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    samplers: list = field(default_factory=list)
    names: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.tris)

    def bounds(self) -> tuple[np.ndarray, np.ndarray] | None:
        if not len(self.tris):
            return None
        pts = self.tris.reshape(-1, 3)
        return pts.min(axis=0), pts.max(axis=0)


def _ngon_tris(ring: np.ndarray) -> list[tuple[int, int, int]]:
    try:
        from ..fileio.model import triangulate_ring
        return triangulate_ring(ring)
    except Exception:
        return [(0, k, k + 1) for k in range(1, len(ring) - 1)]


class FrozenObject:

    def __init__(self, obj, matrix: np.ndarray | None = None) -> None:
        mesh = obj.mesh
        self.name = str(getattr(obj, "name", ""))
        self.kind = str(getattr(obj, "kind", ""))
        self.params = dict(getattr(obj, "params", {}) or {})
        self.mesh = bridges.FrozenMesh(np.array(mesh.points, float), [tuple(p) for p in mesh.polygons])
        extras = getattr(obj, "extras", None)
        self.extras = {k: v for k, v in extras.items() if k in FROZEN_KEYS} if isinstance(extras, dict) else {}
        self.parent = None
        self._matrix = np.array(obj.world_matrix() if matrix is None else matrix, float)

    def world_matrix(self) -> np.ndarray:
        return self._matrix.copy()


@dataclass
class ObjectCapture:
    obj: FrozenObject
    flags: dict
    samplers: list
    per_poly: list
    uvs: list | None = None


def triangulate_object(obj, world: np.ndarray | None = None, settings: dict | None = None,
                       camera_position=None, uvs: list | None = None) -> dict:
    mesh = obj.mesh
    polys = mesh.polygons
    m = obj.world_matrix() if world is None else np.asarray(world, float)
    pts = mesh.points @ m[:3, :3].T + m[:3, 3] if len(mesh.points) else np.zeros((0, 3))
    empty = {"tris": np.zeros((0, 3, 3)), "normals": np.zeros((0, 3, 3)), "face": np.zeros((0, 3)),
             "uvs": np.zeros((0, 3, 2)), "poly": np.zeros(0, np.int64), "local": np.zeros((0, 3, 3))}
    if not polys or not len(pts):
        return empty
    det = float(np.linalg.det(m[:3, :3]))
    orient = -1.0 if det < 0.0 else 1.0
    all_n = bridges.corner_normal_array(obj, settings, matrix=m)
    if uvs is None:
        tags, assign = bridges.polygon_material_tags(obj)
        uvs = bridges.polygon_uvs(obj, tags, assign, camera_position)
    face_n = mesh.polygon_normals(pts) * orient
    lay = bridges.corner_layout(polys)
    sizes = lay["sizes"]
    offsets = np.concatenate([[0], np.cumsum(sizes)])
    flat_v = lay["verts"]
    tri_c: list = []
    tri_p: list = []
    for size in np.unique(sizes):
        size = int(size)
        if size < 3:
            continue
        ks_arr = np.flatnonzero(sizes == size)
        base = offsets[ks_arr]
        if size <= 4:
            for c in range(1, size - 1):
                tri_c.append(np.stack([base, base + c, base + c + 1], axis=1))
                tri_p.append(ks_arr)
            continue
        for k in ks_arr:
            ring = pts[list(polys[k])]
            for a, b, c in _ngon_tris(ring):
                tri_c.append(np.array([[offsets[k] + a, offsets[k] + b, offsets[k] + c]], np.int64))
                tri_p.append(np.array([k], np.int64))
    if not tri_c:
        return empty
    corners = np.concatenate(tri_c)
    poly_of = np.concatenate(tri_p)
    all_uv = np.concatenate([np.asarray(u, float).reshape(-1, 2) for u in uvs]) if uvs else np.zeros((0, 2))
    tris = pts[flat_v[corners]]
    normals = all_n[corners] if len(all_n) == len(flat_v) else np.zeros((len(corners), 3, 3))
    uv = all_uv[corners] if len(all_uv) == len(flat_v) else np.zeros((len(corners), 3, 2))
    face = face_n[poly_of]
    bad = np.linalg.norm(face, axis=1) < 1e-9
    if bad.any():
        e = np.cross(tris[bad, 1] - tris[bad, 0], tris[bad, 2] - tris[bad, 0]) * orient
        face[bad] = normalize(e)
    nl = np.linalg.norm(normals, axis=2)
    zero = ~(nl >= 1e-9)
    if zero.any():
        normals[zero] = np.repeat(face[:, None, :], 3, axis=1)[zero]
    local = mesh.points[flat_v[corners]]
    return {"tris": tris, "normals": normalize(normals), "face": face, "uvs": uv, "poly": poly_of,
            "local": local}


def light_objects(scene) -> list:
    return [o for o in scene.render_objects() if is_light(o)]


def camera_objects(scene) -> list:
    return [o for o in scene.objects if is_camera(o)]


def capture_scene(scene, settings: dict | None = None, camera_position=None) -> list[ObjectCapture]:
    out: list[ObjectCapture] = []
    for obj in scene.render_objects():
        if is_light(obj) or is_camera(obj):
            continue
        mesh = getattr(obj, "mesh", None)
        if mesh is None or not mesh.polygons:
            continue
        if bridges.visibility(scene, obj) <= 0.0:
            continue
        flags = bridges.compositing(obj)
        if not flags["seen_by_camera"] and not flags["cast_shadows"]:
            continue
        samplers, per_poly, uvs = bridges.object_layout(scene, obj, camera_position, defer_base=True)
        frozen = FrozenObject(obj)
        if per_poly and len(per_poly) != len(frozen.mesh.polygons):
            per_poly = []
        out.append(ObjectCapture(frozen, flags, samplers, list(per_poly), uvs))
    return out


def geometry_from_capture(captures: list, settings: dict | None = None, camera_position=None,
                          cancel=None) -> Geometry:
    geo = Geometry()
    tris, normals, faces, uvs, objs, mats, cast, recv, vis, local = [], [], [], [], [], [], [], [], [], []
    samplers: list = []
    names: list = []
    for cap in captures:
        if cancel is not None and cancel():
            from .raster import RenderCancelled
            raise RenderCancelled()
        obj = cap.obj
        obj_uvs = cap.uvs if cap.uvs is not None else bridges.base_uvs(obj)
        data = triangulate_object(obj, settings=settings, camera_position=camera_position, uvs=obj_uvs)
        count = len(data["tris"])
        if not count:
            continue
        offset = len(samplers)
        samplers.extend(cap.samplers)
        per_poly_arr = (np.asarray(cap.per_poly, np.int64) if cap.per_poly
                        else np.zeros(len(obj.mesh.polygons), np.int64))
        index = len(names)
        names.append(obj.name)
        tris.append(data["tris"])
        normals.append(data["normals"])
        faces.append(data["face"])
        uvs.append(data["uvs"])
        local.append(data["local"])
        objs.append(np.full(count, index, np.int64))
        mats.append(per_poly_arr[data["poly"]] + offset)
        cast.append(np.full(count, cap.flags["cast_shadows"]))
        recv.append(np.full(count, cap.flags["receive_shadows"]))
        vis.append(np.full(count, cap.flags["seen_by_camera"]))
    if tris:
        geo.tris = np.concatenate(tris)
        geo.normals = np.concatenate(normals)
        geo.face_normals = np.concatenate(faces)
        geo.uvs = np.concatenate(uvs)
        geo.local = np.concatenate(local)
        geo.obj = np.concatenate(objs)
        geo.mat = np.concatenate(mats)
        geo.cast = np.concatenate(cast).astype(bool)
        geo.receive = np.concatenate(recv).astype(bool)
        geo.visible = np.concatenate(vis).astype(bool)
    geo.samplers = samplers if samplers else [bridges.MaterialSampler(None)]
    geo.names = names
    return geo


def build_geometry(scene, settings: dict | None = None, camera_position=None) -> Geometry:
    return geometry_from_capture(capture_scene(scene, settings, camera_position), settings, camera_position)


def light_from_object(obj) -> Light:
    values = light_params(obj)
    m = obj.world_matrix()
    lin = m[:3, :3]
    kind = LIGHT_KIND_MAP.get(str(values.get("light_type", "Point")), "point")
    color = np.clip(np.asarray(values.get("color", (1.0, 1.0, 1.0)), float).reshape(-1)[:3], 0.0, None)
    return Light(
        kind=kind,
        position=m[:3, 3].astype(float).copy(),
        direction=normalize(lin[:, 2]),
        right=normalize(lin[:, 0]),
        up=normalize(lin[:, 1]),
        color=color,
        intensity=float(values.get("intensity", 1.0)),
        falloff=str(values.get("falloff", "Inverse Square")),
        radius=float(values.get("radius", 500.0)),
        cone_angle=float(values.get("cone_angle", 30.0)),
        penumbra=float(values.get("penumbra", 8.0)),
        area_width=float(values.get("area_width", 100.0)) * float(np.linalg.norm(lin[:, 0])),
        area_height=float(values.get("area_height", 100.0)) * float(np.linalg.norm(lin[:, 1])),
        area_samples=int(values.get("area_samples", 9)),
        shadow=bool(values.get("shadow", True)),
        softness=float(values.get("shadow_softness", 1.0)),
        bias=float(values.get("shadow_bias", 1.0)),
        name=str(obj.name),
    )


def default_lights(camera) -> list[Light]:
    _eye, fwd, right, up = camera.basis()
    fwd, right, up = normalize(fwd), normalize(right), normalize(up)
    key_to = normalize(-0.55 * right + 0.75 * up - 0.45 * fwd)
    fill_to = normalize(0.85 * right + 0.15 * up - 0.4 * fwd)
    rim_to = normalize(0.25 * right + 0.6 * up + 0.85 * fwd)
    return [
        Light(kind="infinite", direction=-key_to, color=np.array([1.0, 0.96, 0.9]), intensity=1.0,
              shadow=True, softness=1.0, name="Key"),
        Light(kind="infinite", direction=-fill_to, color=np.array([0.85, 0.9, 1.0]), intensity=0.35,
              shadow=False, name="Fill"),
        Light(kind="infinite", direction=-rim_to, color=np.array([1.0, 1.0, 1.0]), intensity=0.55,
              shadow=False, name="Rim"),
    ]


def scene_lights(scene, camera, settings: dict) -> list[Light]:
    lights = [light_from_object(o) for o in light_objects(scene)]
    mode = settings.get("default_lights", "auto")
    if mode == "on" or (mode == "auto" and not lights):
        lights = default_lights(camera) + lights
    if not settings.get("shadows", True):
        for light in lights:
            light.shadow = False
    return lights
