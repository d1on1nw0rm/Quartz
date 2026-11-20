from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field

import numpy as np

from . import camera as cammod
from .raster import Buffers, Projected, RenderCancelled, empty_buffers, prepare, rasterize, resolve_bary
from .settings import clean_settings, get_settings
from .shading import (ambient_light, apply_gamma, background, build_shadow_map, dot, normalize, screen_ao,
                      shade_light, tonemap)
from . import bridges
from .snapshot import Geometry, build_geometry, camera_objects, capture_scene, geometry_from_capture, scene_lights

__all__ = ["RenderJob", "RenderResult", "RenderCancelled", "prepare_job", "execute_job", "render",
           "resolve_camera", "active_canvas", "pass_to_rgba8", "buckets", "find_camera_object",
           "save_result", "frame_path", "format_path", "camera_uid", "resolve_camera_info", "UID_KEY",
           "PASS_DTYPE"]

UID_KEY = "render_uid"
PASS_DTYPE = np.float32
TRANSPARENT_EPS = 1e-4
FORMAT_EXTS = {"png": (".png",), "jpg": (".jpg", ".jpeg")}


def active_canvas():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return None
    app = QApplication.instance()
    if app is None:
        return None
    try:
        from ..widgets.viewport import ViewportCanvas
    except Exception:
        return None
    found = [w for w in app.allWidgets() if isinstance(w, ViewportCanvas)]
    if not found:
        return None
    focus = app.focusWidget()
    for w in found:
        if w is focus:
            return w
    visible = [w for w in found if w.isVisible()]
    return (visible or found)[0]


def _default_camera() -> cammod.RenderCamera:
    try:
        from ..widgets.viewport import OrbitCamera
        return cammod.from_orbit(OrbitCamera(), "Default")
    except Exception:
        h, e = math.radians(45.0), math.radians(19.75)
        fwd = np.array([-math.sin(h) * math.cos(e), -math.sin(e), math.cos(h) * math.cos(e)])
        return cammod.look_at(-fwd * 1618.5, np.zeros(3), fov=cammod.fov_from_focal(1.0), name="Default")


def camera_uid(obj, create: bool = False, scene=None) -> str:
    from ..ext import store
    uid = store.get_object(obj, UID_KEY)
    if isinstance(uid, str) and uid:
        return uid
    if not create:
        return ""
    import uuid
    uid = uuid.uuid4().hex
    store.set_object(obj, UID_KEY, uid)
    return uid


def find_camera_object(scene, name: str, uid: str = ""):
    cams = camera_objects(scene)
    if uid:
        hits = [o for o in cams if camera_uid(o) == uid]
        for o in hits:
            if o.name == name:
                return o
        if hits:
            return hits[0]
    for o in cams:
        if name and o.name == name:
            return o
    return None


def resolve_camera(scene, camera=None, settings: dict | None = None) -> cammod.RenderCamera:
    return resolve_camera_info(scene, camera, settings)[0]


def resolve_camera_info(scene, camera=None, settings: dict | None = None) -> tuple[cammod.RenderCamera, str]:
    cam = _resolve_explicit(camera)
    if cam is not None:
        return cam, ""
    s = settings or {}
    name = str(s.get("camera", "") or "")
    uid = str(s.get("camera_id", "") or "")
    warning = ""
    if name or uid:
        obj = find_camera_object(scene, name, uid)
        if obj is not None:
            return cammod.from_object(obj), ""
    canvas = active_canvas()
    fallback = cammod.from_canvas(canvas) if canvas is not None else _default_camera()
    if name or uid:
        warning = f"Render camera '{name}' not found, rendered {fallback.name} instead"
    return fallback, warning


def _resolve_explicit(camera) -> cammod.RenderCamera | None:
    if isinstance(camera, cammod.RenderCamera):
        return camera.copy()
    if isinstance(camera, dict):
        return cammod.look_at(camera.get("eye", (0.0, 0.0, -1000.0)), camera.get("target", (0.0, 0.0, 0.0)),
                              camera.get("up", (0.0, 1.0, 0.0)), float(camera.get("fov", 53.13)),
                              bool(camera.get("ortho", False)), camera.get("ortho_width"),
                              float(camera.get("near", cammod.DEFAULT_NEAR)), str(camera.get("name", "Camera")))
    if camera is not None:
        if hasattr(camera, "world_matrix") and hasattr(camera, "kind"):
            return cammod.from_object(camera)
        if hasattr(camera, "camera") and hasattr(camera.camera, "basis"):
            return cammod.from_canvas(camera)
        if hasattr(camera, "basis"):
            return cammod.from_orbit(camera)
    return None


@dataclass
class RenderJob:
    geometry: Geometry | None
    camera: cammod.RenderCamera
    lights: list
    settings: dict
    width: int
    height: int
    frame: int | None = None
    label: str = ""
    region: tuple | None = None
    capture: list | None = None
    warnings: list = field(default_factory=list)

    def ensure_geometry(self, cancel=None) -> Geometry:
        if self.geometry is None:
            self.geometry = geometry_from_capture(self.capture or [], self.settings, self.camera.eye, cancel)
            self.capture = None
        return self.geometry


@dataclass(eq=False)
class RenderResult:
    width: int
    height: int
    passes: dict
    seconds: float = 0.0
    camera: str = ""
    frame: int | None = None
    settings: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    label: str = ""
    created: float = field(default_factory=time.time)
    compact: bool = False

    def nbytes(self) -> int:
        return int(sum(np.asarray(v).nbytes for v in self.passes.values()))

    def make_compact(self) -> None:
        if self.compact:
            return
        self.passes = {name: pass_to_rgba8(self, name) for name in self.passes}
        self.compact = True

    def names(self) -> list[str]:
        return list(self.passes)

    def rgba8(self, name: str = "beauty") -> np.ndarray:
        return pass_to_rgba8(self, name)

    def image(self, name: str = "beauty"):
        from PySide6.QtGui import QImage
        data = np.ascontiguousarray(self.rgba8(name))
        h, w = data.shape[:2]
        img = QImage(data.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        return img.copy()

    def save(self, path: str, fmt: str | None = None, name: str = "beauty", quality: int = 92) -> bool:
        return save_result(self, path, fmt, name, quality)


def _norm_depth(depth: np.ndarray) -> np.ndarray:
    valid = np.isfinite(depth)
    out = np.zeros(depth.shape)
    if valid.any():
        lo = float(depth[valid].min())
        hi = float(depth[valid].max())
        span = hi - lo if hi - lo > 1e-9 else 1.0
        out[valid] = 1.0 - 0.9 * (depth[valid] - lo) / span
    return out


def pass_to_rgba8(result: RenderResult, name: str = "beauty") -> np.ndarray:
    data = result.passes[name]
    if result.compact:
        return np.asarray(data, np.uint8)
    gamma = float(result.settings.get("gamma", 2.2)) if result.settings else 2.2
    h, w = result.height, result.width
    alpha = np.ones((h, w))
    if name == "beauty":
        rgb = data[..., :3]
        alpha = data[..., 3]
    elif name == "depth":
        g = _norm_depth(data)
        rgb = np.repeat(g[..., None], 3, axis=2)
    elif name == "normal":
        valid = np.linalg.norm(data, axis=2) > 1e-6
        rgb = np.where(valid[..., None], data * 0.5 + 0.5, 0.0)
    elif name == "albedo":
        rgb = apply_gamma(data, gamma)
    elif name == "ao":
        rgb = np.repeat(np.clip(data, 0.0, 1.0)[..., None], 3, axis=2)
    else:
        arr = np.asarray(data, float)
        rgb = np.repeat(arr[..., None], 3, axis=2) if arr.ndim == 2 else arr[..., :3]
    out = np.empty((h, w, 4), np.uint8)
    out[..., :3] = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(np.round(alpha * 255.0), 0, 255).astype(np.uint8)
    return out


def format_path(path: str, fmt: str) -> str:
    if not path:
        return path
    fmt = "jpg" if str(fmt).lower() in ("jpg", "jpeg") else "png"
    root, ext = os.path.splitext(path)
    if ext.lower() in FORMAT_EXTS[fmt]:
        return path
    if not ext or any(ext.lower() in exts for exts in FORMAT_EXTS.values()):
        return root + "." + fmt
    return path + "." + fmt


def frame_path(path: str, frame: int | None, fmt: str, suffix: str = "") -> str:
    root, ext = os.path.splitext(format_path(path, fmt))
    if suffix:
        root = f"{root}_{suffix}"
    if frame is not None:
        root = f"{root}_{int(frame):04d}"
    return root + ext


def save_result(result: RenderResult, path: str, fmt: str | None = None, name: str = "beauty",
                quality: int = 92) -> bool:
    if not path:
        return False
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    fmt = (fmt or ext or "png").lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if not os.path.splitext(path)[1]:
        path = path + "." + fmt
    img = result.image(name)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    if fmt == "jpg":
        from PySide6.QtGui import QImage, QPainter, QColor
        flat = QImage(img.size(), QImage.Format.Format_RGB32)
        bg = result.settings.get("bg_color", [0.0, 0.0, 0.0]) if result.settings else [0.0, 0.0, 0.0]
        flat.fill(QColor.fromRgbF(float(bg[0]), float(bg[1]), float(bg[2])))
        p = QPainter(flat)
        p.drawImage(0, 0, img)
        p.end()
        return bool(flat.save(path, "JPG", int(quality)))
    return bool(img.save(path, "PNG"))


def prepare_job(scene, camera=None, settings: dict | None = None, *, width: int | None = None,
                height: int | None = None, frame: int | None = None, label: str = "", defer: bool = False,
                evaluate: bool = True) -> RenderJob:
    s = clean_settings(settings) if settings is not None else get_settings(scene)
    restore = None
    if frame is not None and evaluate:
        before = bridges.current_frame(scene)
        if before is None or before != frame:
            if bridges.evaluate_frame(scene, frame) and before is not None:
                restore = before
    try:
        cam, warning = resolve_camera_info(scene, camera, s)
        w = int(width or s["width"])
        h = int(height or s["height"])
        capture = capture_scene(scene, s, camera_position=cam.eye)
        lights = scene_lights(scene, cam, s)
    finally:
        if restore is not None:
            bridges.evaluate_frame(scene, restore)
    job = RenderJob(None, cam, lights, s, max(1, w), max(1, h), frame, label or cam.name, capture=capture,
                    warnings=[warning] if warning else [])
    if not defer:
        job.ensure_geometry()
    return job


def buckets(width: int, height: int, size: int, order: str = "spiral") -> list[tuple[int, int, int, int]]:
    size = max(4, int(size))
    out = []
    for y in range(0, height, size):
        for x in range(0, width, size):
            out.append((x, y, min(width, x + size), min(height, y + size)))
    if order == "spiral":
        cx, cy = width / 2.0, height / 2.0
        out.sort(key=lambda b: ((b[0] + b[2]) / 2.0 - cx) ** 2 + ((b[1] + b[3]) / 2.0 - cy) ** 2)
    return out


def _check(cancel) -> None:
    if cancel is not None and cancel():
        raise RenderCancelled()


def _downsample(arr: np.ndarray, s: int) -> np.ndarray:
    if s == 1:
        return arr
    h, w = arr.shape[0] // s, arr.shape[1] // s
    if arr.ndim == 2:
        return arr.reshape(h, s, w, s).mean(axis=(1, 3))
    return arr.reshape(h, s, w, s, arr.shape[2]).mean(axis=(1, 3))


class _Frame:

    def __init__(self, job: RenderJob, cancel=None, progress=None) -> None:
        self.job = job
        self.cancel = cancel
        self.progress = progress
        s = job.settings
        self.aa = int(s["aa"])
        self.w = job.width
        self.h = job.height
        self.sw = self.w * self.aa
        self.sh = self.h * self.aa
        geo = job.geometry
        cam = job.camera
        self.cam = cam
        self.view_idx = np.flatnonzero(geo.visible) if len(geo) else np.zeros(0, np.int64)
        tris = geo.tris[self.view_idx]
        cam_tris = cam.to_camera(tris.reshape(-1, 3)).reshape(-1, 3, 3) if len(tris) else np.zeros((0, 3, 3))
        front = None
        if s.get("backface_culling") and len(tris):
            centre = tris.mean(axis=1)
            v = cam.view_dirs(centre)
            front = dot(geo.face_normals[self.view_idx], v) > 0.0
        self.proj: Projected = prepare(cam_tris, cam, self.sw, self.sh, front=front, key=self.view_idx)
        self.shadows = []
        self.ao_depth = None

    def _report(self, stage: str, value: float) -> None:
        if self.progress is not None:
            self.progress(float(max(0.0, min(1.0, value))), stage)

    def build_shadows(self) -> None:
        geo = self.job.geometry
        casters = geo.tris[geo.cast] if len(geo) else np.zeros((0, 3, 3))
        res = int(self.job.settings["shadow_map"])
        soft = float(self.job.settings["shadow_softness"])
        bounds = geo.bounds()
        lights = self.job.lights
        for i, light in enumerate(lights):
            _check(self.cancel)
            self._report("Shadows", 0.1 * i / max(1, len(lights)))
            self.shadows.append(build_shadow_map(light, casters, bounds, res, soft, self.cancel)
                                if light.shadow else None)
        self._report("Shadows", 0.1)

    def build_ao_depth(self) -> None:
        if not self.job.settings["ao"] or not len(self.proj):
            return
        small = self.proj.scaled(1.0 / self.aa) if self.aa != 1 else self.proj
        buf = rasterize(small, with_bary=False, cancel=self.cancel,
                        progress=lambda f: self._report("Ambient occlusion", 0.1 + 0.1 * f))
        self.ao_depth = buf.depth

    def shade_bucket(self, rect: tuple[int, int, int, int], seed: int) -> dict:
        s = self.job.settings
        a = self.aa
        x0, y0, x1, y1 = rect
        sx0, sy0, sx1, sy1 = x0 * a, y0 * a, x1 * a, y1 * a
        bh, bw = sy1 - sy0, sx1 - sx0
        buf: Buffers = rasterize(self.proj, (sx0, sy0, sx1, sy1), cancel=self.cancel)
        covered = buf.tri >= 0
        color = np.zeros((bh, bw, 3))
        alpha = np.zeros((bh, bw))
        depth = np.full((bh, bw), np.inf)
        normal = np.zeros((bh, bw, 3))
        albedo = np.zeros((bh, bw, 3))
        aoimg = np.ones((bh, bw))
        ys_all = np.repeat(np.arange(sy0, sy1), bw).astype(float) / a
        bg_rgb, bg_a = background(ys_all, self.h, s)
        bg_rgb = bg_rgb.reshape(bh, bw, 3)
        bg_a = bg_a.reshape(bh, bw)
        if covered.any():
            self._shade_pixels(buf, covered, color, alpha, depth, normal, albedo, aoimg, sx0, sy0, seed)
        acc = np.where(covered[..., None], color * alpha[..., None], 0.0)
        trans = np.where(covered, 1.0 - alpha, 1.0)
        layers = int(s.get("transparency_depth", 0))
        open_ = covered & (trans > TRANSPARENT_EPS)
        last = buf.depth.copy()
        for k in range(layers):
            if not open_.any():
                break
            _check(self.cancel)
            peel = rasterize(self.proj, (sx0, sy0, sx1, sy1), cancel=self.cancel,
                             min_depth=np.where(open_, last, np.inf))
            hit = open_ & (peel.tri >= 0)
            if not hit.any():
                break
            c2 = np.zeros((bh, bw, 3))
            a2 = np.zeros((bh, bw))
            self._shade_pixels(peel, hit, c2, a2, np.full((bh, bw), np.inf), np.zeros((bh, bw, 3)),
                               np.zeros((bh, bw, 3)), np.ones((bh, bw)), sx0, sy0, seed + 7919 * (k + 1),
                               use_ao=False)
            acc[hit] += (trans[hit] * a2[hit])[:, None] * c2[hit]
            trans[hit] *= 1.0 - a2[hit]
            last = np.where(hit, peel.depth, last)
            open_ = hit & (trans > TRANSPARENT_EPS)
        cover_a = (1.0 - trans) + trans * bg_a
        mixed = acc + (trans * bg_a)[..., None] * bg_rgb
        mixed = np.where(cover_a[..., None] > 1e-9, mixed / np.maximum(cover_a, 1e-9)[..., None], color)
        out_color = np.where(covered[..., None], mixed, bg_rgb)
        out_alpha = np.where(covered, cover_a, bg_a)
        cov = covered.astype(float)
        if a > 1:
            pre = _downsample(out_color * out_alpha[..., None], a)
            al = _downsample(out_alpha, a)
            rgb = np.where(al[..., None] > 1e-9, pre / np.maximum(al, 1e-9)[..., None], 0.0)
            covd = _downsample(cov, a)
            finite = np.where(covered, depth, 0.0)
            dsum = _downsample(finite, a)
            dep = np.where(covd > 0, dsum / np.maximum(covd, 1e-9), np.inf)
            nrm = normalize(_downsample(normal, a))
            alb = np.where(covd[..., None] > 0, _downsample(albedo, a) / np.maximum(covd, 1e-9)[..., None], 0.0)
            aos = np.where(covd > 0, _downsample(np.where(covered, aoimg, 0.0), a) / np.maximum(covd, 1e-9), 1.0)
        else:
            rgb, al, dep, nrm, alb, aos = out_color, out_alpha, depth, normal, albedo, aoimg
        return {"beauty": np.concatenate([rgb, al[..., None]], axis=2), "depth": dep, "normal": nrm,
                "albedo": alb, "ao": aos}

    def _shade_pixels(self, buf: Buffers, covered: np.ndarray, color, alpha, depth, normal, albedo, aoimg,
                      sx0: int, sy0: int, seed: int, use_ao: bool = True) -> None:
        job = self.job
        s = job.settings
        geo = job.geometry
        cam = self.cam
        iy, ix = np.nonzero(covered)
        rtri = buf.tri[iy, ix]
        src, b = resolve_bary(self.proj, rtri, buf.bary[iy, ix])
        p = np.einsum("ni,nij->nj", b, geo.tris[src])
        ns = normalize(np.einsum("ni,nij->nj", b, geo.normals[src]))
        ng = geo.face_normals[src].copy()
        uv = np.einsum("ni,nij->nj", b, geo.uvs[src])
        lp = np.einsum("ni,nij->nj", b, geo.local[src]) if len(geo.local) == len(geo.tris) else p
        v = cam.view_dirs(p)
        flip = dot(ng, v) < 0.0
        ng[flip] = -ng[flip]
        ns[flip] = -ns[flip]
        bad = dot(ns, v) < 0.0
        if bad.any():
            ns[bad] = normalize(ns[bad] - (dot(ns[bad], v[bad]) - 1e-3)[:, None] * v[bad])
        n = len(p)
        mats = {"base_color": np.zeros((n, 3)), "metallic": np.zeros(n), "roughness": np.full(n, 0.5),
                "specular": np.full(n, 0.5), "emission": np.zeros((n, 3)), "alpha": np.ones(n)}
        mat_ids = geo.mat[src]
        for mid in np.unique(mat_ids):
            sel = np.flatnonzero(mat_ids == mid)
            sampler = geo.samplers[int(mid)] if 0 <= int(mid) < len(geo.samplers) else geo.samplers[0]
            got = sampler.sample(uv[sel, 0], uv[sel, 1], lp[sel], ns[sel])
            for key in mats:
                mats[key][sel] = got[key]
            bumped = got.get("normal")
            if bumped is not None and len(bumped) == len(sel):
                facing = dot(bumped, v[sel]) > 0.0
                ns[sel[facing]] = bumped[facing]
        ao = np.ones(n)
        if use_ao and s["ao"] and self.ao_depth is not None:
            rng = np.random.default_rng(int(s["seed"]) * 7919 + seed)
            per_pixel = max(3, int(math.ceil(int(s["ao_samples"]) / float(self.aa * self.aa))))
            ao = screen_ao(p, ns, self.ao_depth, cam, self.w, self.h, float(s["ao_radius"]),
                           per_pixel, float(s["ao_strength"]), rng)
        lit = mats["emission"].copy()
        receive = geo.receive[src]
        for light, smap in zip(job.lights, self.shadows):
            use = smap if smap is not None else None
            if use is not None and not receive.all():
                rgb_a, _d = shade_light(light, p, ns, v, mats, None, ng)
                rgb_b, _d = shade_light(light, p, ns, v, mats, use, ng)
                rgb = np.where(receive[:, None], rgb_b, rgb_a)
            else:
                rgb, _d = shade_light(light, p, ns, v, mats, use, ng)
            lit += rgb
        lit += ambient_light(ns, v, mats, s, ao)
        out = apply_gamma(tonemap(lit, s["tonemap"], s["exposure"]), s["gamma"])
        color[iy, ix] = out
        alpha[iy, ix] = mats["alpha"]
        depth[iy, ix] = cam.to_camera(p)[:, 2]
        normal[iy, ix] = ns
        albedo[iy, ix] = mats["base_color"]
        aoimg[iy, ix] = ao


def execute_job(job: RenderJob, progress=None, cancel=None, on_bucket=None) -> RenderResult:
    start = time.perf_counter()
    job.ensure_geometry(cancel)
    frame = _Frame(job, cancel, progress)
    frame.build_shadows()
    frame.build_ao_depth()
    s = job.settings
    w, h = job.width, job.height
    beauty = np.zeros((h, w, 4), PASS_DTYPE)
    depth = np.full((h, w), np.inf, PASS_DTYPE)
    normal = np.zeros((h, w, 3), PASS_DTYPE)
    albedo = np.zeros((h, w, 3), PASS_DTYPE)
    ao = np.ones((h, w), PASS_DTYPE)
    region = job.region
    tiles = buckets(w, h, int(s["bucket_size"]), s["bucket_order"])
    if region is not None:
        rx0, ry0, rx1, ry1 = region
        tiles = [(max(a, rx0), max(b, ry0), min(c, rx1), min(d, ry1)) for a, b, c, d in tiles
                 if a < rx1 and c > rx0 and b < ry1 and d > ry0]
    for i, rect in enumerate(tiles):
        _check(cancel)
        out = frame.shade_bucket(rect, i)
        x0, y0, x1, y1 = rect
        beauty[y0:y1, x0:x1] = out["beauty"]
        depth[y0:y1, x0:x1] = out["depth"]
        normal[y0:y1, x0:x1] = out["normal"]
        albedo[y0:y1, x0:x1] = out["albedo"]
        ao[y0:y1, x0:x1] = out["ao"]
        if progress is not None:
            progress(1.0 if i + 1 == len(tiles) else min(1.0, 0.2 + 0.8 * (i + 1) / len(tiles)), "Rendering")
        if on_bucket is not None:
            on_bucket(rect, out["beauty"])
    passes = {"beauty": beauty, "depth": depth, "normal": normal, "albedo": albedo, "ao": ao}
    wanted = [p for p in s["passes"] if p in passes]
    seconds = time.perf_counter() - start
    stats = {"triangles": int(len(job.geometry)), "raster_triangles": int(len(frame.proj)),
             "lights": len(job.lights), "objects": len(job.geometry.names), "buckets": len(tiles),
             "warnings": list(job.warnings)}
    return RenderResult(w, h, {k: passes[k] for k in wanted}, seconds, job.camera.name, job.frame, dict(s),
                        stats, job.label)


def render(scene=None, camera=None, settings: dict | None = None, *, width: int | None = None,
           height: int | None = None, progress=None, cancel=None, on_bucket=None,
           frame: int | None = None) -> RenderResult:
    if scene is None:
        from ..scene import get_scene
        scene = get_scene()
    job = prepare_job(scene, camera, settings, width=width, height=height, frame=frame)
    return execute_job(job, progress, cancel, on_bucket)
