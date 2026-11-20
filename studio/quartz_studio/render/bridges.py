from __future__ import annotations

import importlib
from typing import Any

import numpy as np

from ..ext import store

__all__ = [
    "DEFAULT_MATERIAL",
    "optional_module",
    "object_tags",
    "first_tag",
    "phong_angle",
    "phong_spec",
    "corner_normals",
    "corner_normal_array",
    "corner_layout",
    "split_corners",
    "FrozenMesh",
    "base_uvs",
    "compositing",
    "visibility",
    "polygon_material_tags",
    "polygon_uvs",
    "resolve_material",
    "MaterialSampler",
    "sampler_for",
    "evaluate_frame",
    "current_frame",
    "timeline_range",
    "scene_materials",
    "object_layout",
    "normalise_channels",
]

DEFAULT_MATERIAL = {
    "base_color": [0.8, 0.8, 0.8],
    "metallic": 0.0,
    "roughness": 0.5,
    "specular": 0.5,
    "emission": [0.0, 0.0, 0.0],
    "alpha": 1.0,
}

_MISSING = object()
_CACHE: dict = {}


def optional_module(name: str):
    if name in _CACHE:
        return _CACHE[name]
    try:
        mod = importlib.import_module(f"quartz_studio.{name}")
    except Exception:
        mod = None
    _CACHE[name] = mod
    return mod


def _forget(name: str) -> None:
    _CACHE.pop(name, None)


def object_tags(obj) -> list:
    tags = store.get_object(obj, "tags")
    return [t for t in tags if isinstance(t, dict)] if isinstance(tags, list) else []


def _tag_type(tag: dict) -> str:
    for key in ("type", "kind", "id", "tag"):
        v = tag.get(key)
        if isinstance(v, str):
            return v.lower()
    return ""


def first_tag(obj, tag_type: str, enabled_only: bool = True) -> dict | None:
    for tag in object_tags(obj):
        if _tag_type(tag) == tag_type and (not enabled_only or tag.get("enabled", True)):
            return tag
    return None


def _tag_value(tag: dict, keys, default=None):
    for key in keys:
        if key in tag:
            return tag[key]
    for nest in ("params", "values", "data"):
        inner = tag.get(nest)
        if isinstance(inner, dict):
            for key in keys:
                if key in inner:
                    return inner[key]
    return default


def phong_spec(obj, settings: dict | None = None) -> tuple[bool, float, list] | None:
    tag = first_tag(obj, "phong")
    if tag is not None:
        limit = bool(_tag_value(tag, ("angle_limit", "limit", "use_angle"), True))
        angle = float(_tag_value(tag, ("angle", "phong_angle", "limit_angle"), 80.0))
        breaks = []
        if tag.get("use_edge_breaks", True):
            for e in tag.get("edge_breaks", []) or []:
                try:
                    breaks.append((int(e[0]), int(e[1])))
                except (TypeError, ValueError, IndexError):
                    continue
        return limit, angle, breaks
    s = settings or {}
    if s.get("auto_phong", False):
        return True, float(s.get("phong_angle", 80.0)), []
    return None


def phong_angle(obj, settings: dict | None = None) -> float | None:
    spec = phong_spec(obj, settings)
    if spec is None:
        return None
    return 180.0 if not spec[0] else spec[1]


class FrozenMesh:

    def __init__(self, points, polygons) -> None:
        self.points = np.array(points, float).reshape(-1, 3)
        self.polygons = list(polygons)

    def polygon_normals(self, points: np.ndarray | None = None) -> np.ndarray:
        from ..scene import Mesh
        return Mesh.polygon_normals(self, points)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if not len(self.points):
            return np.zeros(3), np.zeros(3)
        return self.points.min(axis=0), self.points.max(axis=0)


def corner_layout(polygons) -> dict:
    sizes = np.fromiter((len(p) for p in polygons), np.int64, len(polygons))
    total = int(sizes.sum()) if len(sizes) else 0
    verts = np.fromiter((v for p in polygons for v in p), np.int64, total)
    poly_of = np.repeat(np.arange(len(polygons)), sizes)
    starts = np.cumsum(sizes) - sizes
    if total:
        local = np.arange(total) - starts[poly_of]
        nxt = starts[poly_of] + (local + 1) % sizes[poly_of]
        prv = starts[poly_of] + (local - 1) % sizes[poly_of]
    else:
        nxt = prv = np.zeros(0, np.int64)
    return {"sizes": sizes, "verts": verts, "poly_of": poly_of, "starts": starts, "next": nxt, "prev": prv}


def split_corners(values: np.ndarray, sizes: np.ndarray) -> list[np.ndarray]:
    if not len(sizes):
        return []
    return [np.array(a) for a in np.split(values, np.cumsum(sizes)[:-1])]


def _labels(count: int, i: np.ndarray, j: np.ndarray) -> np.ndarray:
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


def _phong_fallback(mesh, limit: bool, angle: float, breaks) -> np.ndarray:
    lay = corner_layout(mesh.polygons)
    pts = mesh.points
    fn = mesh.polygon_normals()
    verts, poly_of, nxt, prv = lay["verts"], lay["poly_of"], lay["next"], lay["prev"]
    count = len(verts)
    if not count:
        return np.zeros((0, 3))
    n = int(max(len(pts), int(verts.max()) + 1)) + 1
    a = np.minimum(verts, verts[nxt])
    b = np.maximum(verts, verts[nxt])
    code = a * n + b
    valid = a != b
    if breaks:
        bcode = np.array([min(x, y) * n + max(x, y) for x, y in breaks], np.int64)
        valid &= ~np.isin(code, bcode)
    cand = np.flatnonzero(valid)
    order = cand[np.argsort(code[cand], kind="stable")]
    first_i: list = []
    second_i: list = []
    if len(order):
        _u, first, counts = np.unique(code[order], return_index=True, return_counts=True)
        two = first[counts == 2]
        if len(two):
            first_i.append(order[two])
            second_i.append(order[two + 1])
        for f, c in zip(first[counts > 2], counts[counts > 2]):
            run = order[f:f + c]
            ii, jj = np.triu_indices(len(run), 1)
            first_i.append(run[ii])
            second_i.append(run[jj])
    if first_i:
        c1 = np.concatenate(first_i)
        c2 = np.concatenate(second_i)
        keep = poly_of[c1] != poly_of[c2]
        if limit:
            cos_limit = np.cos(np.radians(max(0.0, min(180.0, float(angle)))))
            keep &= np.einsum("ij,ij->i", fn[poly_of[c1]], fn[poly_of[c2]]) >= cos_limit - 1e-9
        c1, c2 = c1[keep], c2[keep]
        t1, t2 = nxt[c1], nxt[c2]
        same = verts[c1] == verts[c2]
        li = np.concatenate([c1, t1])
        lj = np.concatenate([np.where(same, c2, t2), np.where(same, t2, c2)])
    else:
        li = lj = np.zeros(0, np.int64)
    lab = _labels(count, li, lj)
    u = pts[verts[prv]] - pts[verts]
    w = pts[verts[nxt]] - pts[verts]
    nu = np.linalg.norm(u, axis=1)
    nw = np.linalg.norm(w, axis=1)
    ok = (nu > 1e-12) & (nw > 1e-12)
    cosang = np.zeros(count)
    cosang[ok] = np.einsum("ij,ij->i", u[ok], w[ok]) / (nu[ok] * nw[ok])
    weight = np.maximum(np.where(ok, np.arccos(np.clip(cosang, -1.0, 1.0)), 0.0), 1e-6)
    sums = np.zeros((count, 3))
    np.add.at(sums, lab, fn[poly_of] * weight[:, None])
    out = sums[lab]
    ln = np.linalg.norm(out, axis=1)
    good = ln > 1e-12
    out[good] = out[good] / ln[good][:, None]
    out[~good] = fn[poly_of][~good]
    return out


def _local_corner_normals(mesh, spec, use_tags: bool = True) -> np.ndarray:
    polys = mesh.polygons
    if not polys:
        return np.zeros((0, 3))
    if spec is None:
        lay = corner_layout(polys)
        return mesh.polygon_normals()[lay["poly_of"]]
    limit, angle, breaks = spec
    shading = optional_module("tags.shading") if use_tags else None
    if shading is not None and hasattr(shading, "phong_normals"):
        try:
            got = shading.phong_normals(mesh, limit, angle, breaks)
            return np.concatenate(got).reshape(-1, 3) if got else np.zeros((0, 3))
        except Exception:
            pass
    return _phong_fallback(mesh, limit, angle, breaks)


def _unit_rows(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return np.where(n > 1e-12, v / np.where(n > 1e-12, n, 1.0), v)


def corner_normal_array(obj, settings: dict | None = None, points: np.ndarray | None = None,
                        matrix: np.ndarray | None = None) -> np.ndarray:
    mesh = obj.mesh
    spec = phong_spec(obj, settings)
    if matrix is not None:
        m = np.asarray(matrix, float)
        lin = m[:3, :3]
        det = float(np.linalg.det(lin))
        size = float(np.abs(lin).max()) if lin.size else 0.0
        if abs(det) > 1e-12 * max(1.0, size ** 3):
            local = _local_corner_normals(mesh, spec)
            return _unit_rows(local @ np.linalg.inv(lin))
        points = mesh.points @ lin.T + m[:3, 3] if len(mesh.points) else np.zeros((0, 3))
    if points is None:
        return _local_corner_normals(mesh, spec)
    return _local_corner_normals(FrozenMesh(points, mesh.polygons), spec)


def corner_normals(obj, settings: dict | None = None, points: np.ndarray | None = None,
                   matrix: np.ndarray | None = None) -> list[np.ndarray]:
    values = corner_normal_array(obj, settings, points, matrix)
    return split_corners(values, corner_layout(obj.mesh.polygons)["sizes"])


def compositing(obj) -> dict:
    out = {"cast_shadows": True, "receive_shadows": True, "seen_by_camera": True}
    shading = optional_module("tags.shading")
    if shading is not None and hasattr(shading, "compositing_flags"):
        try:
            flags = shading.compositing_flags(obj)
            for k in out:
                if k in flags:
                    out[k] = bool(flags[k])
            return out
        except Exception:
            pass
    o = obj
    while o is not None:
        tag = first_tag(o, "compositing")
        if tag is not None:
            for k in out:
                out[k] = bool(tag.get(k, out[k]))
            break
        o = getattr(o, "parent", None)
    return out


def visibility(scene, obj) -> float:
    shading = optional_module("tags.shading")
    if shading is not None and hasattr(shading, "display_state"):
        try:
            return float(shading.display_state(scene, obj).get("visibility", 1.0))
        except Exception:
            pass
    return 1.0


def polygon_material_tags(obj) -> tuple[list, list]:
    tags = object_tags(obj)
    count = len(obj.mesh.polygons)
    shading = optional_module("tags.shading")
    assign: list = [None] * count
    if shading is not None and hasattr(shading, "material_assignments"):
        try:
            got = list(shading.material_assignments(obj))
            if len(got) == count:
                assign = got
                return tags, assign
        except Exception:
            pass
    for i, tag in enumerate(tags):
        if _tag_type(tag) != "material" or not tag.get("enabled", True):
            continue
        for k in range(count):
            assign[k] = i
    return tags, assign


def _box_uvs(obj, points: np.ndarray) -> list[np.ndarray]:
    mesh = obj.mesh
    polys = mesh.polygons
    if not polys:
        return []
    pts = np.asarray(points, float)
    lo, hi = mesh.bounds()
    size = np.where(hi - lo > 1e-9, hi - lo, 1.0)
    q = (pts - lo) / size
    fn = mesh.polygon_normals(pts)
    lay = corner_layout(polys)
    axis = np.argmax(np.abs(fn), axis=1)
    cols = np.array([[2, 1], [0, 2], [0, 1]])[axis[lay["poly_of"]]]
    uv = q[lay["verts"][:, None], cols]
    return split_corners(uv, lay["sizes"])


def _uvw_tag_coords(obj) -> list | None:
    shading = optional_module("tags.shading")
    if shading is not None and hasattr(shading, "uvw_coordinates"):
        try:
            return shading.uvw_coordinates(obj)
        except Exception:
            return None
    tag = first_tag(obj, "uvw", enabled_only=False)
    if tag is None:
        return None
    data = tag.get("uvw") or []
    polys = obj.mesh.polygons
    if len(data) != len(polys):
        return None
    out = []
    for poly, uv in zip(polys, data):
        arr = np.asarray(uv, float).reshape(-1, 2)
        if len(arr) != len(poly):
            return None
        out.append(arr)
    return out


def polygon_uvs(obj, tags: list, assign: list, camera_position=None) -> list[np.ndarray]:
    mesh = obj.mesh
    base = _uvw_tag_coords(obj)
    if base is None:
        base = _box_uvs(obj, mesh.points)
    else:
        base = [np.asarray(a, float) for a in base]
    used = sorted({a for a in assign if a is not None})
    if not used:
        return base
    shading = optional_module("tags.shading")
    if shading is None or not hasattr(shading, "projection_uvs"):
        return base
    per_tag = {}
    for i in used:
        if not 0 <= i < len(tags):
            continue
        try:
            per_tag[i] = shading.projection_uvs(obj, tags[i], camera_position)
        except Exception:
            per_tag[i] = None
    out = []
    for k, uv in enumerate(base):
        a = assign[k] if k < len(assign) else None
        got = per_tag.get(a) if a is not None else None
        if got is not None and k < len(got) and len(got[k]) == len(uv):
            out.append(np.asarray(got[k], float))
        else:
            out.append(uv)
    return out


def scene_materials(scene) -> Any:
    return store.get_scene_data(scene, "materials")


def _lookup_in(collection, ref):
    if collection is None or ref is None:
        return None
    if isinstance(collection, dict):
        if ref in collection:
            return collection[ref]
        for key in ("items", "materials", "list"):
            inner = collection.get(key)
            if isinstance(inner, (list, dict)):
                hit = _lookup_in(inner, ref)
                if hit is not None:
                    return hit
        for v in collection.values():
            if isinstance(v, dict) and (v.get("id") == ref or v.get("name") == ref):
                return v
        return None
    if isinstance(collection, list):
        if isinstance(ref, int) and 0 <= ref < len(collection):
            return collection[ref]
        for v in collection:
            if isinstance(v, dict) and (v.get("id") == ref or v.get("name") == ref):
                return v
    return None


def resolve_material(scene, ref) -> Any:
    if ref is None:
        return None
    if isinstance(ref, dict) and not ({"id", "ref"} >= set(ref.keys())):
        return ref
    if isinstance(ref, dict):
        ref = ref.get("id", ref.get("ref"))
    mats = optional_module("materials")
    if mats is not None:
        for name in ("get_material", "find_material", "material_by_id", "lookup_material", "material"):
            fn = getattr(mats, name, None)
            if callable(fn):
                for args in ((scene, ref), (ref,)):
                    try:
                        hit = fn(*args)
                    except Exception:
                        continue
                    if hit is not None:
                        return hit
    return _lookup_in(scene_materials(scene), ref)


def _tag_material_ref(tag: dict):
    return _tag_value(tag, ("material", "material_id", "material_name", "ref"), None)


def _object_material_ref(scene, obj):
    mats = optional_module("materials")
    if mats is not None:
        for name in ("object_material", "material_for", "material_of", "assigned_material"):
            fn = getattr(mats, name, None)
            if callable(fn):
                for args in ((obj, scene), (scene, obj), (obj,)):
                    try:
                        hit = fn(*args)
                    except Exception:
                        continue
                    if hit is not None:
                        return hit
    return store.get_object(obj, "material")


def _get(source, keys, default=_MISSING):
    for key in keys:
        if isinstance(source, dict):
            if key in source:
                return source[key]
        elif hasattr(source, key):
            return getattr(source, key)
    if isinstance(source, dict):
        for nest in ("params", "values", "channels"):
            inner = source.get(nest)
            if isinstance(inner, dict):
                for key in keys:
                    if key in inner:
                        return inner[key]
    return default


def _channel(value, n: int, width: int) -> np.ndarray | None:
    if value is _MISSING or value is None:
        return None
    try:
        arr = np.asarray(value, float)
    except (TypeError, ValueError):
        return None
    if width == 1:
        if arr.ndim == 0:
            return np.full(n, float(arr))
        flat = arr.reshape(-1)
        if len(flat) == n:
            return flat.astype(float)
        if len(flat) >= 1 and arr.ndim == 1 and len(flat) in (3, 4):
            return np.full(n, float(flat[:3].mean()))
        return None
    if arr.ndim == 0:
        return np.full((n, width), float(arr))
    if arr.ndim == 1:
        if len(arr) >= width:
            return np.broadcast_to(arr[:width], (n, width)).astype(float)
        if len(arr) == n:
            return np.repeat(arr[:, None], width, axis=1)
        return None
    if arr.shape[0] == n and arr.shape[-1] >= width:
        return arr.reshape(n, -1)[:, :width].astype(float)
    return None


BASE_KEYS = ("base_color", "albedo", "color", "diffuse", "diffuse_color", "basecolor")
METAL_KEYS = ("metallic", "metalness", "metal")
ROUGH_KEYS = ("roughness", "rough")
SPEC_KEYS = ("specular", "specular_level", "reflectance")
EMIT_KEYS = ("emission", "emissive", "emission_color", "luminance")
EMIT_STRENGTH_KEYS = ("emission_strength", "emission_intensity", "emissive_strength")
ALPHA_KEYS = ("alpha", "opacity")


def normalise_channels(result, n: int) -> dict:
    out = {}
    base = _channel(_get(result, BASE_KEYS), n, 3)
    out["base_color"] = base if base is not None else np.tile(DEFAULT_MATERIAL["base_color"], (n, 1))
    metal = _channel(_get(result, METAL_KEYS), n, 1)
    out["metallic"] = np.clip(metal if metal is not None else np.zeros(n), 0.0, 1.0)
    rough = _channel(_get(result, ROUGH_KEYS), n, 1)
    if rough is None:
        gloss = _channel(_get(result, ("glossiness", "gloss")), n, 1)
        rough = 1.0 - gloss if gloss is not None else np.full(n, DEFAULT_MATERIAL["roughness"])
    out["roughness"] = np.clip(rough, 0.02, 1.0)
    spec = _channel(_get(result, SPEC_KEYS), n, 1)
    out["specular"] = np.clip(spec if spec is not None else np.full(n, 0.5), 0.0, 2.0)
    emit = _channel(_get(result, EMIT_KEYS), n, 3)
    strength = _channel(_get(result, EMIT_STRENGTH_KEYS), n, 1)
    if emit is None:
        emit = np.zeros((n, 3))
    if strength is not None:
        emit = emit * strength[:, None]
    out["emission"] = np.maximum(emit, 0.0)
    alpha = _channel(_get(result, ALPHA_KEYS), n, 1)
    out["alpha"] = np.clip(alpha if alpha is not None else np.ones(n), 0.0, 1.0)
    out["base_color"] = np.clip(out["base_color"], 0.0, 1.0)
    nrm = _channel(_get(result, ("normal", "shading_normal")), n, 3)
    if nrm is not None and n and nrm.shape == (n, 3) and np.all(np.isfinite(nrm)):
        ln = np.linalg.norm(nrm, axis=1, keepdims=True)
        if np.all(ln > 1e-9):
            out["normal"] = nrm / ln
    return out


class MaterialSampler:

    def __init__(self, material=None, evaluator=None, label: str = "") -> None:
        self.material = material
        self.evaluator = evaluator
        self.label = label
        self._constant: dict | None = None
        self._vector_ok = True

    @property
    def is_default(self) -> bool:
        return self.material is None

    def _call(self, u, v, pos, normal):
        return self.evaluator(self.material, u, v, pos, normal)

    def sample(self, u: np.ndarray, v: np.ndarray, pos: np.ndarray, normal: np.ndarray) -> dict:
        n = len(u)
        if self.material is None:
            return normalise_channels(DEFAULT_MATERIAL, n)
        if self.evaluator is None:
            return normalise_channels(self.material, n)
        if self._vector_ok:
            try:
                res = self._call(u, v, pos, normal)
                chans = normalise_channels(res, n)
                if _get(res, BASE_KEYS) is not _MISSING or n == 0:
                    return chans
            except Exception:
                self._vector_ok = False
        if self._constant is None:
            try:
                if n:
                    mu, mv = float(np.mean(u)), float(np.mean(v))
                    mp = np.mean(pos, axis=0)
                    mn = np.mean(normal, axis=0)
                else:
                    mu = mv = 0.5
                    mp = np.zeros(3)
                    mn = np.array([0.0, 1.0, 0.0])
                res = self._call(mu, mv, mp, mn)
                self._constant = {k: np.asarray(val)[0] if np.ndim(val) and len(np.asarray(val)) == 1
                                  else val for k, val in normalise_channels(res, 1).items()}
            except Exception:
                self._constant = normalise_channels(self.material if isinstance(self.material, dict)
                                                    else DEFAULT_MATERIAL, 1)
        const = self._constant
        return {
            "base_color": np.tile(np.asarray(const["base_color"]).reshape(-1)[:3], (n, 1)),
            "metallic": np.full(n, float(np.asarray(const["metallic"]).reshape(-1)[0])),
            "roughness": np.full(n, float(np.asarray(const["roughness"]).reshape(-1)[0])),
            "specular": np.full(n, float(np.asarray(const["specular"]).reshape(-1)[0])),
            "emission": np.tile(np.asarray(const["emission"]).reshape(-1)[:3], (n, 1)),
            "alpha": np.full(n, float(np.asarray(const["alpha"]).reshape(-1)[0])),
        }


def _evaluator():
    mats = optional_module("materials")
    if mats is None:
        return None
    fn = getattr(mats, "evaluate_material", None)
    if callable(fn):
        return fn
    for sub in ("evaluate", "pbr", "shading", "core"):
        try:
            mod = importlib.import_module(f"quartz_studio.materials.{sub}")
        except Exception:
            continue
        fn = getattr(mod, "evaluate_material", None)
        if callable(fn):
            return fn
    return None


def _is_flat(mat) -> bool:
    return isinstance(mat, dict) and "channels" not in mat and "graph" not in mat and         str(mat.get("type", "")) not in ("pbr", "node")


def sampler_for(scene, ref) -> MaterialSampler:
    if ref is None:
        return MaterialSampler(None)
    mat = resolve_material(scene, ref)
    if mat is None:
        return MaterialSampler(None)
    if _is_flat(mat):
        return MaterialSampler(mat, None, str(mat.get("name", "") or mat.get("id", "")))
    ev = _evaluator()
    label = ""
    if isinstance(mat, dict):
        label = str(mat.get("name", "") or mat.get("id", ""))
    if ev is None and not isinstance(mat, dict):
        return MaterialSampler(None)
    return MaterialSampler(mat, ev, label)


def _hashable(ref):
    if isinstance(ref, (str, int, float, type(None))):
        return ref
    return id(ref)


def _normal_tag(tag: dict) -> dict:
    out = dict(tag)
    proj = str(tag.get("projection", "uvw") or "uvw").lower()
    out["projection"] = {"uvw mapping": "uvw", "frontal": "flat", "shrink wrapping": "spherical"}.get(proj, proj)
    if "tiling" not in tag and ("tiles_u" in tag or "tiles_v" in tag):
        out["tiling"] = [float(tag.get("tiles_u", 1.0)), float(tag.get("tiles_v", 1.0))]
    if "offset" not in tag and ("offset_u" in tag or "offset_v" in tag):
        out["offset"] = [float(tag.get("offset_u", 0.0)) / 100.0, float(tag.get("offset_v", 0.0)) / 100.0]
    return out


def _material_tags_up(obj) -> dict:
    found: dict = {}
    node = obj
    while node is not None:
        for tag in object_tags(node):
            if _tag_type(tag) == "material" and tag.get("enabled", True):
                ref = _tag_material_ref(tag)
                found.setdefault(_hashable(ref), tag)
        node = getattr(node, "parent", None)
    return found


def object_layout(scene, obj, camera_position=None, defer_base: bool = False) -> tuple[list, list, list | None]:
    mesh = obj.mesh
    count = len(mesh.polygons)
    mats = optional_module("materials")
    refs = None
    if mats is not None and hasattr(mats, "polygon_material_ids"):
        try:
            got = list(mats.polygon_material_ids(scene, obj))
            if len(got) == count:
                refs = got
        except Exception:
            refs = None
    tags_by_ref = _material_tags_up(obj)
    if refs is None or all(r is None for r in refs):
        tags, assign = polygon_material_tags(obj)
        own = [_tag_material_ref(tags[a]) if a is not None and 0 <= a < len(tags) else None for a in assign]
        if any(r is not None for r in own):
            refs = own
            for a in set(x for x in assign if x is not None):
                if 0 <= a < len(tags):
                    tags_by_ref[_hashable(_tag_material_ref(tags[a]))] = tags[a]
    if refs is None:
        refs = [None] * count
    samplers = [sampler_for(scene, _object_material_ref(scene, obj))]
    index: dict = {None: 0}
    per_poly: list[int] = []
    for r in refs:
        key = _hashable(r)
        if key not in index:
            smp = sampler_for(scene, r)
            if smp.is_default:
                index[key] = 0
            else:
                samplers.append(smp)
                index[key] = len(samplers) - 1
        per_poly.append(index[key])
    used = {_hashable(r) for r in refs if r is not None}
    if not used and defer_base:
        return samplers, per_poly, None
    uvs = _base_uvs(obj)
    if used and mats is not None and hasattr(mats, "object_uvs"):
        cache: dict = {}
        for k, r in enumerate(refs):
            key = _hashable(r)
            if r is None or key not in tags_by_ref:
                continue
            if key not in cache:
                try:
                    u, v = mats.object_uvs(obj, _normal_tag(tags_by_ref[key]))
                    pu = np.stack([np.asarray(u, float), np.asarray(v, float)], axis=1)
                    cache[key] = pu if len(pu) == len(mesh.points) else None
                except Exception:
                    cache[key] = None
            pu = cache[key]
            if pu is not None:
                uvs[k] = pu[list(mesh.polygons[k])]
    elif used:
        tags, assign = polygon_material_tags(obj)
        uvs = polygon_uvs(obj, tags, assign, camera_position)
    return samplers, per_poly, uvs


def base_uvs(obj) -> list[np.ndarray]:
    return _base_uvs(obj)


def _base_uvs(obj) -> list[np.ndarray]:
    mesh = obj.mesh
    coords = _uvw_tag_coords(obj)
    if coords is not None:
        return [np.asarray(a, float) for a in coords]
    stored = store.get_object(obj, "uvw")
    if stored is not None:
        try:
            arr = np.asarray(stored, float).reshape(-1, 2)
        except (TypeError, ValueError):
            arr = None
        if arr is not None and len(arr) == len(mesh.points):
            return [arr[list(p)] for p in mesh.polygons]
        if arr is not None and len(arr) == sum(len(p) for p in mesh.polygons):
            out = []
            i = 0
            for p in mesh.polygons:
                out.append(arr[i:i + len(p)])
                i += len(p)
            return out
    return _box_uvs(obj, mesh.points)


def object_samplers(scene, obj) -> tuple[list[MaterialSampler], list[int]]:
    samplers, per_poly, _uvs = object_layout(scene, obj)
    return samplers, per_poly


def evaluate_frame(scene, frame) -> bool:
    anim = optional_module("anim")
    if anim is None:
        return False
    for name in ("evaluate", "evaluate_scene", "evaluate_frame", "set_frame", "goto_frame", "apply_frame"):
        fn = getattr(anim, name, None)
        if not callable(fn):
            continue
        for args in ((scene, frame), (frame, scene), (frame,)):
            try:
                fn(*args)
            except TypeError:
                continue
            except Exception:
                return False
            return True
    return False


def _time_settings(scene) -> dict | None:
    anim = optional_module("anim")
    if anim is None:
        return None
    fn = getattr(anim, "time_settings", None)
    if not callable(fn):
        core = getattr(anim, "core", None)
        fn = getattr(core, "time_settings", None) if core is not None else None
    if not callable(fn):
        return None
    try:
        out = fn(scene)
    except Exception:
        return None
    return out if isinstance(out, dict) else None


def current_frame(scene):
    ts = _time_settings(scene)
    if ts is None or "frame" not in ts:
        return None
    return ts["frame"]


def timeline_range(scene) -> tuple[int, int] | None:
    ts = _time_settings(scene)
    if ts is None:
        return None
    lo = ts.get("preview_min", ts.get("min"))
    hi = ts.get("preview_max", ts.get("max"))
    if lo is None or hi is None:
        return None
    return int(round(float(lo))), int(round(float(hi)))
