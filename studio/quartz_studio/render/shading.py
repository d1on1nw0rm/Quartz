from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .camera import RenderCamera, look_at
from .raster import prepare, rasterize

__all__ = [
    "Light",
    "ShadowMap",
    "build_shadow_map",
    "ggx_terms",
    "shade_light",
    "ambient_light",
    "screen_ao",
    "tonemap",
    "apply_gamma",
    "background",
    "dot",
    "normalize",
]

PI = math.pi


def dot(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.einsum("...i,...i->...", a, b)


def normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n > 1e-12, n, 1.0)


@dataclass
class Light:
    kind: str = "infinite"
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    direction: np.ndarray = field(default_factory=lambda: np.array([0.0, -1.0, 0.0]))
    right: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    up: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0]))
    color: np.ndarray = field(default_factory=lambda: np.ones(3))
    intensity: float = 1.0
    falloff: str = "None"
    radius: float = 500.0
    cone_angle: float = 30.0
    penumbra: float = 8.0
    area_width: float = 100.0
    area_height: float = 100.0
    area_samples: int = 9
    shadow: bool = True
    softness: float = 1.0
    bias: float = 1.0
    name: str = "Light"

    def radiance(self) -> np.ndarray:
        return np.asarray(self.color, float) * float(self.intensity) * PI

    def size(self) -> float:
        if self.kind == "area":
            return float(max(self.area_width, self.area_height))
        return 0.0

    def sample_points(self) -> np.ndarray:
        if self.kind != "area":
            return np.asarray(self.position, float)[None, :]
        n = max(1, int(self.area_samples))
        cols = int(math.ceil(math.sqrt(n)))
        rows = int(math.ceil(n / cols))
        pts = []
        k = 0
        for r in range(rows):
            for c in range(cols):
                if k >= n:
                    break
                u = ((c + 0.5) / cols - 0.5) * self.area_width
                v = ((r + 0.5) / rows - 0.5) * self.area_height
                pts.append(np.asarray(self.position, float) + u * np.asarray(self.right, float)
                           + v * np.asarray(self.up, float))
                k += 1
        return np.asarray(pts, float)


def _attenuation(light: Light, dist: np.ndarray) -> np.ndarray:
    if light.falloff == "Inverse Square":
        r = max(float(light.radius), 1e-6)
        return (r * r) / np.maximum(dist * dist, 1e-6)
    if light.falloff == "Linear":
        r = max(float(light.radius), 1e-6)
        return np.clip(1.0 - dist / r, 0.0, 1.0)
    return np.ones_like(dist)


def _spot_factor(light: Light, to_light: np.ndarray) -> np.ndarray:
    outer = math.radians(max(0.5, min(89.5, float(light.cone_angle))))
    inner = math.radians(max(0.0, float(light.cone_angle) - float(light.penumbra)))
    co, ci = math.cos(outer), math.cos(min(inner, outer - 1e-4))
    c = dot(-to_light, np.asarray(light.direction, float))
    t = np.clip((c - co) / max(ci - co, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ggx_terms(n: np.ndarray, v: np.ndarray, l: np.ndarray, base: np.ndarray, metallic: np.ndarray,
              roughness: np.ndarray, specular: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h = normalize(l + v)
    ndl = np.clip(dot(n, l), 0.0, 1.0)
    ndv = np.clip(dot(n, v), 1e-4, 1.0)
    ndh = np.clip(dot(n, h), 0.0, 1.0)
    vdh = np.clip(dot(v, h), 0.0, 1.0)
    a = roughness * roughness
    a2 = a * a
    d = a2 / (PI * np.square(ndh * ndh * (a2 - 1.0) + 1.0) + 1e-12)
    k = np.square(roughness + 1.0) / 8.0
    g = (ndv / (ndv * (1.0 - k) + k)) * (ndl / (ndl * (1.0 - k) + k + 1e-12))
    f0 = (0.08 * specular)[:, None] * (1.0 - metallic[:, None]) + base * metallic[:, None]
    q = 1.0 - vdh
    q2 = q * q
    fw = (q2 * q2 * q)[:, None]
    f = f0 + (1.0 - f0) * fw
    spec = (d * g / (4.0 * ndv * np.maximum(ndl, 1e-4)))[:, None] * f
    kd = (1.0 - f) * (1.0 - metallic[:, None])
    diffuse = kd * base / PI
    return diffuse, spec, ndl


def shade_light(light: Light, p: np.ndarray, n: np.ndarray, v: np.ndarray, mat: dict,
                shadow: "ShadowMap | None", ng: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    total = np.zeros((len(p), 3))
    diffuse_only = np.zeros((len(p), 3))
    if not len(p):
        return total, diffuse_only
    vis = np.ones(len(p))
    if shadow is not None:
        vis = shadow.visibility(p, n if ng is None else ng)
    rad = light.radiance()
    if light.kind == "infinite":
        l = np.broadcast_to(-normalize(np.asarray(light.direction, float)), p.shape)
        dif, spec, ndl = ggx_terms(n, v, l, mat["base_color"], mat["metallic"], mat["roughness"],
                                   mat["specular"])
        k = (ndl * vis)[:, None] * rad
        return (dif + spec) * k, dif * k
    points = light.sample_points()
    weight = 1.0 / len(points)
    for q in points:
        d = q - p
        dist = np.linalg.norm(d, axis=1)
        l = d / np.maximum(dist, 1e-9)[:, None]
        att = _attenuation(light, dist)
        if light.kind == "spot":
            att = att * _spot_factor(light, l)
        elif light.kind == "area":
            att = att * np.clip(dot(-l, np.asarray(light.direction, float)), 0.0, 1.0)
        dif, spec, ndl = ggx_terms(n, v, l, mat["base_color"], mat["metallic"], mat["roughness"],
                                   mat["specular"])
        k = (ndl * att * vis * weight)[:, None] * rad
        total += (dif + spec) * k
        diffuse_only += dif * k
    return total, diffuse_only


def ambient_light(n: np.ndarray, v: np.ndarray, mat: dict, settings: dict, ao: np.ndarray) -> np.ndarray:
    amb = float(settings.get("ambient", 0.25))
    if amb <= 0.0 or not len(n):
        return np.zeros((len(n), 3))
    sky = np.asarray(settings.get("sky_color", [0.6, 0.65, 0.75]), float)
    ground = np.asarray(settings.get("ground_color", [0.2, 0.2, 0.2]), float)
    t = (0.5 + 0.5 * n[:, 1])[:, None]
    irr = (ground * (1.0 - t) + sky * t) * amb
    r = 2.0 * dot(n, v)[:, None] * n - v
    tr = (0.5 + 0.5 * r[:, 1])[:, None]
    env = (ground * (1.0 - tr) + sky * tr) * amb
    base = mat["base_color"]
    metal = mat["metallic"][:, None]
    rough = mat["roughness"][:, None]
    f0 = (0.08 * mat["specular"])[:, None] * (1.0 - metal) + base * metal
    ndv = np.clip(dot(n, v), 0.0, 1.0)[:, None]
    fr = f0 + (np.maximum(1.0 - rough, f0) - f0) * np.power(1.0 - ndv, 5.0)
    diff = irr * base * (1.0 - metal) * (1.0 - fr)
    spec = env * fr * (1.0 - 0.6 * rough)
    return (diff + spec) * ao[:, None]


@dataclass
class _Face:
    camera: RenderCamera
    depth: np.ndarray
    res: int


@dataclass
class ShadowMap:
    light: Light
    faces: list
    softness: float = 1.0
    bias: float = 1.0
    kind: str = "single"

    def _texel(self, face: _Face, z: np.ndarray) -> np.ndarray:
        cam = face.camera
        if cam.ortho:
            return np.full_like(z, cam.ortho_width / face.res)
        return np.maximum(z, 1e-6) / (cam.focal * face.res)

    def _lookup(self, face: _Face, p: np.ndarray, ng: np.ndarray, to_light: np.ndarray) -> np.ndarray:
        cam = face.camera
        z0 = cam.to_camera(p)[:, 2]
        texel = self._texel(face, z0)
        side = np.sign(dot(ng, to_light))
        side = np.where(side == 0, 1.0, side)
        offset = p + ng * (side * texel * (1.0 + 1.5 * self.bias))[:, None]
        c = cam.to_camera(offset)
        z = c[:, 2]
        scr = cam.cam_to_screen(c, face.res, face.res)
        bias = texel * (0.5 + self.bias)
        res = face.res
        soft = float(self.softness)
        radius = np.full(len(p), soft)
        if self.light.kind == "area" and self.light.size() > 0.0:
            radius = self._penumbra(face, scr, z, texel, soft)
        k = 0 if float(radius.max(initial=0.0)) <= 1e-6 else 2
        offs = [(0.0, 0.0)] if k == 0 else [(dx / k, dy / k) for dy in range(-k, k + 1) for dx in range(-k, k + 1)]
        lit = np.zeros(len(p))
        for dx, dy in offs:
            ix = np.floor(scr[:, 0] + dx * radius).astype(np.int64)
            iy = np.floor(scr[:, 1] + dy * radius).astype(np.int64)
            inside = (ix >= 0) & (ix < res) & (iy >= 0) & (iy < res) & (z > cam.near)
            d = np.full(len(p), np.inf)
            d[inside] = face.depth[iy[inside], ix[inside]]
            lit += (z - bias <= d)
        return lit / len(offs)

    def _penumbra(self, face: _Face, scr: np.ndarray, z: np.ndarray, texel: np.ndarray, soft: float) -> np.ndarray:
        res = face.res
        search = 6.0
        acc = np.zeros(len(z))
        cnt = np.zeros(len(z))
        for dy in (-1.0, 0.0, 1.0):
            for dx in (-1.0, 0.0, 1.0):
                ix = np.floor(scr[:, 0] + dx * search).astype(np.int64)
                iy = np.floor(scr[:, 1] + dy * search).astype(np.int64)
                inside = (ix >= 0) & (ix < res) & (iy >= 0) & (iy < res)
                d = np.full(len(z), np.inf)
                d[inside] = face.depth[iy[inside], ix[inside]]
                blk = d < z - texel
                acc += np.where(blk, d, 0.0)
                cnt += blk
        avg = np.where(cnt > 0, acc / np.maximum(cnt, 1), z)
        width = self.light.size() * np.maximum(z - avg, 0.0) / np.maximum(avg, 1e-3)
        return np.clip(width / np.maximum(texel, 1e-9) * 0.5, soft, 12.0)

    def visibility(self, p: np.ndarray, ng: np.ndarray) -> np.ndarray:
        if not len(p):
            return np.zeros(0)
        lp = np.asarray(self.light.position, float)
        if self.light.kind == "infinite":
            to_light = np.broadcast_to(-normalize(np.asarray(self.light.direction, float)), p.shape)
        else:
            to_light = normalize(lp - p)
        if self.kind == "single":
            return self._lookup(self.faces[0], p, ng, to_light)
        d = p - lp
        ax = np.argmax(np.abs(d), axis=1)
        sign = np.take_along_axis(d, ax[:, None], axis=1)[:, 0] >= 0
        face_id = ax * 2 + np.where(sign, 0, 1)
        out = np.ones(len(p))
        for f in range(6):
            m = face_id == f
            if m.any():
                out[m] = self._lookup(self.faces[f], p[m], ng[m], to_light[m])
        return out


CUBE_DIRS = (
    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
)


def _depth_map(camera: RenderCamera, tris: np.ndarray, res: int, cancel=None) -> np.ndarray:
    cam_tris = camera.to_camera(tris.reshape(-1, 3)).reshape(-1, 3, 3) if len(tris) else np.zeros((0, 3, 3))
    proj = prepare(cam_tris, camera, res, res)
    buf = rasterize(proj, with_bary=False, cancel=cancel)
    return buf.depth


def build_shadow_map(light: Light, tris: np.ndarray, bounds: tuple[np.ndarray, np.ndarray] | None,
                     res: int, softness: float = 1.0, cancel=None) -> ShadowMap | None:
    if not light.shadow or not len(tris):
        return None
    res = int(max(16, res))
    soft = float(softness) * float(light.softness)
    if light.kind == "infinite":
        lo, hi = bounds if bounds is not None else (tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0))
        center = (lo + hi) / 2.0
        radius = max(float(np.linalg.norm(hi - lo)) / 2.0, 1.0)
        d = normalize(np.asarray(light.direction, float))
        up = (0.0, 1.0, 0.0) if abs(d[1]) < 0.95 else (0.0, 0.0, 1.0)
        eye = center - d * (radius * 2.0 + 10.0)
        cam = look_at(eye, center, up, ortho=True, ortho_width=radius * 2.04, near=0.01)
        return ShadowMap(light, [_Face(cam, _depth_map(cam, tris, res, cancel), res)], soft, light.bias)
    pos = np.asarray(light.position, float)
    if light.kind == "spot":
        d = normalize(np.asarray(light.direction, float))
        up = (0.0, 1.0, 0.0) if abs(d[1]) < 0.95 else (0.0, 0.0, 1.0)
        fov = min(170.0, 2.0 * float(light.cone_angle) + 4.0)
        cam = look_at(pos, pos + d, up, fov=fov, near=0.5)
        return ShadowMap(light, [_Face(cam, _depth_map(cam, tris, res, cancel), res)], soft, light.bias)
    face_res = max(16, res // 2)
    faces = []
    for fwd, up in CUBE_DIRS:
        cam = look_at(pos, pos + np.asarray(fwd), up, fov=92.0, near=0.5)
        faces.append(_Face(cam, _depth_map(cam, tris, face_res, cancel), face_res))
    return ShadowMap(light, faces, soft, light.bias, kind="cube")


FAR_DEPTH = 1.0e30


def _sample_depth(field: np.ndarray, scr: np.ndarray, width: int, height: int, ortho: bool) -> np.ndarray:
    fx = np.clip(scr[:, 0] - 0.5, 0.0, width - 1.0)
    fy = np.clip(scr[:, 1] - 0.5, 0.0, height - 1.0)
    x0 = np.floor(fx).astype(np.int64)
    y0 = np.floor(fy).astype(np.int64)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    tx = fx - x0
    ty = fy - y0
    top = field[y0, x0] * (1.0 - tx) + field[y0, x1] * tx
    bottom = field[y1, x0] * (1.0 - tx) + field[y1, x1] * tx
    value = top * (1.0 - ty) + bottom * ty
    if ortho:
        return np.where(value >= FAR_DEPTH * 1e-3, np.inf, value)
    return np.where(value > 1e-300, 1.0 / np.maximum(value, 1e-300), np.inf)


def screen_ao(p: np.ndarray, n: np.ndarray, depth: np.ndarray, camera: RenderCamera, width: int, height: int,
              radius: float, samples: int, strength: float, rng: np.random.Generator) -> np.ndarray:
    count = len(p)
    if not count:
        return np.ones(0)
    a = np.where((np.abs(n[:, 0]) > 0.9)[:, None], np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    t = normalize(np.cross(n, a))
    b = np.cross(n, t)
    phi0 = rng.random(count) * 2.0 * PI
    jitter = rng.random((samples, count))
    occ = np.zeros(count)
    golden = 0.618033988749895
    base = p + n * (radius * 0.02)
    z_center = camera.to_camera(p)[:, 2]
    finite = np.isfinite(depth)
    if camera.ortho:
        field = np.where(finite, depth, FAR_DEPTH)
    else:
        field = np.where(finite & (depth > 0.0), 1.0 / np.where(finite & (depth > 0.0), depth, 1.0), 0.0)
    for k in range(samples):
        u1 = (k + jitter[k]) / samples
        u2 = (k * golden) % 1.0
        r = np.sqrt(u1)
        th = phi0 + 2.0 * PI * u2
        d = t * (r * np.cos(th))[:, None] + b * (r * np.sin(th))[:, None] + n * np.sqrt(1.0 - u1)[:, None]
        scale = radius * (0.1 + 0.9 * ((k + 1.0) / samples) ** 2)
        s = base + d * scale
        cs = camera.to_camera(s)
        scr = camera.cam_to_screen(cs, width, height)
        ix = np.floor(scr[:, 0]).astype(np.int64)
        iy = np.floor(scr[:, 1]).astype(np.int64)
        inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height) & (cs[:, 2] > camera.near)
        dz = np.full(count, np.inf)
        dz[inside] = depth[iy[inside], ix[inside]]
        if inside.any():
            smooth = _sample_depth(field, scr[inside], width, height, camera.ortho)
            dz[inside] = np.maximum(dz[inside], smooth)
        sz = cs[:, 2]
        bias = 0.002 * np.abs(z_center) + radius * 0.02
        gap = sz - dz
        rng_check = np.clip(radius / np.maximum(np.abs(z_center - dz), 1e-6), 0.0, 1.0)
        occ += np.where(gap > bias, rng_check, 0.0)
    return np.clip(1.0 - strength * occ / samples, 0.0, 1.0)


def _hable(x: np.ndarray) -> np.ndarray:
    a, b, c, d, e, f = 0.15, 0.50, 0.10, 0.20, 0.02, 0.30
    return ((x * (a * x + c * b) + d * e) / (x * (a * x + b) + d * f)) - e / f


def tonemap(rgb: np.ndarray, mode: str = "filmic", exposure: float = 0.0) -> np.ndarray:
    x = np.maximum(np.asarray(rgb, float), 0.0) * (2.0 ** float(exposure))
    if mode == "aces":
        y = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    elif mode == "filmic":
        y = _hable(x * 2.0) / _hable(np.array(11.2))
    else:
        y = x
    return np.clip(y, 0.0, 1.0)


def apply_gamma(rgb: np.ndarray, gamma: float = 2.2) -> np.ndarray:
    g = max(float(gamma), 1e-3)
    return np.power(np.clip(rgb, 0.0, 1.0), 1.0 / g)


def background(ys: np.ndarray, height: int, settings: dict) -> tuple[np.ndarray, np.ndarray]:
    mode = settings.get("background", "gradient")
    count = len(ys)
    if mode == "transparent":
        return np.zeros((count, 3)), np.zeros(count)
    if mode == "gradient":
        top = np.asarray(settings.get("bg_top", [0.1, 0.12, 0.15]), float)
        bottom = np.asarray(settings.get("bg_bottom", [0.06, 0.07, 0.09]), float)
        t = np.clip((ys + 0.5) / max(height, 1), 0.0, 1.0)[:, None]
        return top * (1.0 - t) + bottom * t, np.ones(count)
    color = np.asarray(settings.get("bg_color", [0.06, 0.07, 0.09]), float)
    return np.tile(color, (count, 1)), np.ones(count)
