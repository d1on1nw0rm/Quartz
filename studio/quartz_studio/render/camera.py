from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

__all__ = ["RenderCamera", "look_at", "from_orbit", "from_canvas", "from_object", "focal_from_fov",
           "fov_from_focal", "DEFAULT_NEAR"]

DEFAULT_NEAR = 1.0


def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


def focal_from_fov(fov_deg: float) -> float:
    half = math.radians(max(1e-3, min(179.0, float(fov_deg)))) / 2.0
    return 0.5 / math.tan(half)


def fov_from_focal(focal: float) -> float:
    return math.degrees(2.0 * math.atan(0.5 / max(float(focal), 1e-9)))


@dataclass
class RenderCamera:
    eye: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, -1000.0]))
    forward: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0]))
    right: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    up: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0]))
    focal: float = 1.0
    ortho: bool = False
    ortho_width: float = 1000.0
    near: float = DEFAULT_NEAR
    name: str = "View"

    def copy(self) -> "RenderCamera":
        return replace(self, eye=np.array(self.eye, float), forward=np.array(self.forward, float),
                       right=np.array(self.right, float), up=np.array(self.up, float))

    def basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        return (np.asarray(self.eye, float), np.asarray(self.forward, float),
                np.asarray(self.right, float), np.asarray(self.up, float))

    def fov(self) -> float:
        return fov_from_focal(self.focal)

    def to_camera(self, pts) -> np.ndarray:
        p = np.asarray(pts, float)
        v = p - np.asarray(self.eye, float)
        return np.stack([v @ self.right, v @ self.up, v @ self.forward], -1)

    def scale(self, width: int) -> float:
        if self.ortho:
            return float(width) / max(float(self.ortho_width), 1e-9)
        return float(self.focal) * float(width)

    def cam_to_screen(self, cam: np.ndarray, width: int, height: int) -> np.ndarray:
        cam = np.asarray(cam, float)
        s = self.scale(width)
        cx, cy = width / 2.0, height / 2.0
        if self.ortho:
            return np.stack([cx + s * cam[..., 0], cy - s * cam[..., 1]], -1)
        z = np.where(np.abs(cam[..., 2]) < 1e-12, 1e-12, cam[..., 2])
        return np.stack([cx + s * cam[..., 0] / z, cy - s * cam[..., 1] / z], -1)

    def project(self, pts, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
        cam = self.to_camera(pts)
        return self.cam_to_screen(cam, width, height), cam[..., 2]

    def ray(self, sx, sy, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
        sx = np.asarray(sx, float)
        sy = np.asarray(sy, float)
        s = self.scale(width)
        cx, cy = width / 2.0, height / 2.0
        a = (sx - cx) / s
        b = -(sy - cy) / s
        if self.ortho:
            o = self.eye + a[..., None] * self.right + b[..., None] * self.up
            d = np.broadcast_to(self.forward, o.shape).copy()
            return o, d
        d = self.forward + a[..., None] * self.right + b[..., None] * self.up
        d = d / np.linalg.norm(d, axis=-1, keepdims=True)
        o = np.broadcast_to(np.asarray(self.eye, float), d.shape).copy()
        return o, d

    def view_dirs(self, pts) -> np.ndarray:
        p = np.asarray(pts, float)
        if self.ortho:
            return np.broadcast_to(-np.asarray(self.forward, float), p.shape).copy()
        v = np.asarray(self.eye, float) - p
        n = np.linalg.norm(v, axis=-1, keepdims=True)
        return v / np.where(n > 1e-12, n, 1.0)


def look_at(eye, target, up=(0.0, 1.0, 0.0), fov: float = 53.13, ortho: bool = False,
            ortho_width: float | None = None, near: float = DEFAULT_NEAR, name: str = "Camera") -> RenderCamera:
    eye = np.asarray(eye, float)
    target = np.asarray(target, float)
    fwd = _unit(target - eye)
    if float(np.linalg.norm(fwd)) < 1e-12:
        fwd = np.array([0.0, 0.0, 1.0])
    upv = _unit(up)
    right = np.cross(upv, fwd)
    if float(np.linalg.norm(right)) < 1e-9:
        alt = np.array([0.0, 0.0, 1.0]) if abs(fwd[1]) > 0.9 else np.array([0.0, 1.0, 0.0])
        right = np.cross(alt, fwd)
    right = _unit(right)
    true_up = _unit(np.cross(fwd, right))
    focal = focal_from_fov(fov)
    width = ortho_width
    if width is None:
        width = float(np.linalg.norm(target - eye)) / focal
    return RenderCamera(eye=eye, forward=fwd, right=right, up=true_up, focal=focal, ortho=bool(ortho),
                        ortho_width=float(width), near=float(near), name=name)


def from_orbit(cam, name: str = "View") -> RenderCamera:
    pos, fwd, right, up = cam.basis()
    focal = float(getattr(cam, "focal", 1.0))
    ortho = bool(getattr(cam, "ortho", False))
    distance = float(getattr(cam, "distance", 1000.0))
    near = float(getattr(cam, "near", DEFAULT_NEAR))
    width = distance / max(focal, 1e-9)
    return RenderCamera(eye=np.array(pos, float), forward=_unit(fwd), right=_unit(right), up=_unit(up),
                        focal=focal, ortho=ortho, ortho_width=width, near=max(near, 1e-3), name=name)


def from_canvas(canvas, name: str | None = None) -> RenderCamera:
    label = name or getattr(canvas, "view_name", "") or "View"
    return from_orbit(canvas.camera, label)


def from_object(obj) -> RenderCamera:
    m = obj.world_matrix()
    lin = m[:3, :3]
    fwd = _unit(lin[:, 2])
    if float(np.linalg.norm(fwd)) < 1e-12:
        fwd = np.array([0.0, 0.0, 1.0])
    up = np.asarray(lin[:, 1], float) - fwd * float(np.dot(lin[:, 1], fwd))
    if float(np.linalg.norm(up)) < 1e-9:
        up = np.cross(fwd, _unit(lin[:, 0]))
    if float(np.linalg.norm(up)) < 1e-9:
        up = np.array([0.0, 1.0, 0.0]) if abs(fwd[1]) < 0.95 else np.array([0.0, 0.0, 1.0])
        up = up - fwd * float(np.dot(up, fwd))
    up = _unit(up)
    right = _unit(np.cross(up, fwd))
    params = dict(getattr(obj, "params", {}) or {})
    try:
        from .objects import CAMERA_DEFAULTS
        values = dict(CAMERA_DEFAULTS)
    except ImportError:
        values = {}
    values.update(params)
    focal_mm = float(values.get("focal_length", 36.0))
    sensor = float(values.get("sensor_width", 36.0))
    focal = focal_mm / max(sensor, 1e-6)
    if "fov" in params and "focal_length" not in params:
        focal = focal_from_fov(float(params["fov"]))
    projection = str(values.get("projection", "Perspective"))
    ortho = projection.lower() in ("parallel", "orthographic", "ortho")
    width = float(values.get("ortho_width", 1000.0))
    near = float(values.get("near_clip", DEFAULT_NEAR))
    return RenderCamera(eye=m[:3, 3].astype(float).copy(), forward=fwd, right=right, up=up, focal=focal,
                        ortho=ortho, ortho_width=max(width, 1e-6), near=max(near, 1e-3),
                        name=str(getattr(obj, "name", "Camera")))
