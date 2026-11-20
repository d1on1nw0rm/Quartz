from __future__ import annotations

import itertools
import math
import weakref

import numpy as np

from . import data
from . import stamps as _stamps
from .brushes import BrushSettings, DabContext, brush

__all__ = ["SculptStroke", "stroke_begin", "stroke_dab", "stroke_end", "stroke_cancel",
           "current_stroke", "apply_dab", "symmetry_frames", "has_live_stroke", "end_strokes",
           "oriented_topology"]

_CURRENT: "SculptStroke | None" = None
_LIVE: "weakref.WeakSet" = weakref.WeakSet()


def _unit(v, fallback=(0.0, 1.0, 0.0)) -> np.ndarray:
    v = np.asarray(v, float).reshape(3)
    length = float(np.linalg.norm(v))
    if length < 1e-12 or not np.isfinite(length):
        return np.asarray(fallback, float)
    return v / length


def symmetry_frames(symmetry) -> list[np.ndarray]:
    axes = [k for k in range(3) if bool(tuple(symmetry)[k])] if symmetry is not None else []
    out = []
    for flips in itertools.product((1.0, -1.0), repeat=len(axes)):
        s = np.ones(3)
        for axis, f in zip(axes, flips):
            s[axis] = f
        out.append(s)
    return out


_BOUNDS: list = []
BOUND_CACHE = 4


def _fingerprint(pts: np.ndarray) -> tuple:
    step = max(1, len(pts) // 64)
    return (len(pts), float(np.asarray(pts[::step], float).sum()))


def _cached_bound(pts, topo, lin) -> float | None:
    for ref, t, m, fp, bound in _BOUNDS:
        if ref is pts and t is topo and np.array_equal(m, lin) and fp == _fingerprint(pts):
            return bound
    return None


def _store_bound(pts, topo, lin, bound: float) -> None:
    _BOUNDS[:] = [b for b in _BOUNDS if b[0] is not pts][-(BOUND_CACHE - 1):]
    _BOUNDS.append((pts, topo, np.array(lin, float, copy=True), _fingerprint(pts), float(bound)))


class _Oriented:

    def __init__(self, topo, sign: float) -> None:
        self._topo = topo
        self.sign = float(sign)

    def __getattr__(self, name):
        return getattr(self._topo, name)

    def vertex_normals(self, pts, idx=None):
        return self._topo.vertex_normals(pts, idx) * self.sign

    def face_normals(self, pts, faces=None):
        return self._topo.face_normals(pts, faces) * self.sign

    def face_normal(self, pts, face):
        return self._topo.face_normal(pts, face) * self.sign

    def tri_normals(self, pts, tris=None):
        return self._topo.tri_normals(pts, tris) * self.sign


def oriented_topology(topo, sign: float):
    return topo if float(sign) >= 0.0 else _Oriented(topo, sign)


class SculptStroke:

    def __init__(self, obj, settings: BrushSettings, scene=None, *, smooth: bool = False,
                 invert: bool | None = None, record: bool = True) -> None:
        self.obj = obj
        self.scene = data._scene(scene)
        self.settings = (settings.copy() if isinstance(settings, BrushSettings)
                         else BrushSettings.from_dict(settings)).clamp()
        self.smooth = bool(smooth)
        if invert is not None:
            self.settings.invert = bool(invert)
        self.brush = brush("smooth") if self.smooth and self.settings.brush != "mask" else brush(self.settings.brush)
        self.state = data.ensure_state(obj)
        self.block = None
        if self.state is not None:
            if data.is_frozen(self.state):
                self.block = "frozen"
            elif self.brush.kind != "mask":
                self.block = data.edit_block(self.state)
        self.valid = self.state is not None and self.block is None
        self.dabs = 0
        self.moved = 0
        self.changed = False
        self.recorded = False
        self._want_record = bool(record)
        self._undo_entry = None
        self._redo_saved = None
        self._last: np.ndarray | None = None
        self._last_pressure = 1.0
        self._grab: list | None = None
        self._grab_origin: np.ndarray | None = None
        self.finished = False
        if not self.valid:
            return
        st = self.state
        base_topo = data.topology(st)
        self._base_topo = base_topo
        self.sign = data.orientation(obj)
        self.topo = oriented_topology(base_topo, self.sign)
        m = obj.world_matrix()
        self.lin = m[:3, :3].copy()
        self.trans = m[:3, 3].copy()
        det = float(np.linalg.det(self.lin))
        self.inv = np.linalg.inv(self.lin) if abs(det) > 1e-18 else np.eye(3)
        self.P0 = np.array(obj.mesh.points, float, copy=True)
        self.P = self.P0.copy()
        self.W = self.P @ self.lin.T + self.trans
        n = len(self.P)
        self.mask = data.get_mask(st, n)
        self.mask_dirty = False
        self.use_mask = bool(self.settings.use_mask) and data.mask_enabled(st)
        self.target = None
        if self.brush.id == "erase":
            self.target = data.erase_target(st) @ self.lin.T + self.trans
        scale = float(np.mean(np.linalg.norm(self.lin, axis=0))) if n else 1.0
        self.world_scale = scale if scale > 1e-12 else 1.0
        self.edge_bound = _cached_bound(obj.mesh.points, base_topo, self.lin)
        if self.edge_bound is None:
            self.edge_bound = base_topo.max_edge(self.W)
        _LIVE.add(self)

    def raycast(self, origin, direction):
        if not self.valid:
            return None
        return self._base_topo.raycast(self.W, origin, direction, bound=self.edge_bound)

    def surface_normal(self, face: int) -> np.ndarray:
        return self.topo.face_normal(self.W, face)

    def _strength(self, pressure: float) -> float:
        s = self.settings.smooth_strength if self.smooth else self.settings.strength
        if self.settings.pressure_strength:
            s *= min(max(float(pressure), 0.0), 1.0)
        return float(s)

    def _radius(self, radius: float | None, pressure: float) -> float:
        r = float(self.settings.radius if radius is None else radius)
        if self.settings.pressure_radius:
            r *= max(0.05, min(max(float(pressure), 0.0), 1.0))
        return max(r, 1e-9)

    def _frames(self, hit: np.ndarray, normal: np.ndarray, view: np.ndarray, r: float):
        lh = self.inv @ (hit - self.trans)
        ln = self.lin.T @ normal
        lv = self.inv @ view
        out = []
        for s in symmetry_frames(self.settings.symmetry):
            c = self.lin @ (lh * s) + self.trans
            if any(float(np.linalg.norm(c - o[0])) < 1e-6 * max(r, 1.0) for o in out):
                continue
            nn = _unit(self.inv.T @ (ln * s), normal)
            vv = _unit(self.lin @ (lv * s), view)
            out.append((c, nn, vv, s))
        return out

    def _region(self, c: np.ndarray, n: np.ndarray, v: np.ndarray, r: float, pressure: float,
                for_mask: bool = False):
        cand = np.nonzero(np.abs(self.W[:, 0] - c[0]) < r)[0]
        if not len(cand):
            return None
        diff = np.take(self.W, cand, axis=0) - c
        d2 = np.einsum("ij,ij->i", diff, diff)
        inside = d2 < r * r
        idx = cand[inside]
        if not len(idx):
            return None
        t = np.sqrt(d2[inside]) / r
        f = self.settings.weight(t)
        vn = self.topo.vertex_normals(self.W, idx)
        if self.settings.front_only:
            keep = (vn @ n) > -0.05
            idx, t, f, vn = idx[keep], t[keep], f[keep], vn[keep]
            if not len(idx):
                return None
        stamp = self.settings.stamp_array()
        if stamp is not None:
            a = np.array([0.0, 1.0, 0.0]) if abs(float(v[1])) < 0.9 else np.array([1.0, 0.0, 0.0])
            u = _unit(np.cross(v, a))
            w2 = _unit(np.cross(u, v))
            ang = math.radians(float(self.settings.stamp_rotation))
            ca, sa = math.cos(ang), math.sin(ang)
            size = r * float(self.settings.stamp_scale)
            rel = self.W[idx] if self.settings.stamp_tile else self.W[idx] - c
            x0 = (rel @ u) / size
            y0 = (rel @ w2) / size
            x = ca * x0 + sa * y0
            y = -sa * x0 + ca * y0
            if self.settings.stamp_tile:
                x = np.mod(x + 1.0, 2.0) - 1.0
                y = np.mod(y + 1.0, 2.0) - 1.0
            f = f * _stamps.sample(stamp, x, y)
        fsum = float(f.sum())
        if fsum > 1e-12:
            na = (vn * f[:, None]).sum(axis=0)
            ac = (self.W[idx] * f[:, None]).sum(axis=0) / fsum
        else:
            na = n
            ac = c
        na = _unit(na, n)
        if float(na @ n) < 0.0:
            na = -na
        w = f * self._strength(pressure)
        if self.use_mask and not for_mask:
            w = w * (1.0 - self.mask[idx])
        return idx, w, f, na, ac

    def _move(self, idx: np.ndarray, new_w: np.ndarray) -> bool:
        if not len(idx):
            return False
        if not np.any(new_w != self.W[idx]):
            return False
        self.W[idx] = new_w
        self.P[idx] = (self.W[idx] - self.trans) @ self.inv.T
        self.edge_bound = max(self.edge_bound, self._base_topo.max_edge(self.W, idx))
        return True

    def _apply_at(self, hit: np.ndarray, normal: np.ndarray, view: np.ndarray, pressure: float,
                  radius: float | None) -> tuple[int, bool]:
        r = self._radius(radius, pressure)
        total = 0
        changed = False
        sign = -1.0 if self.settings.invert else 1.0
        for c, n, v, _s in self._frames(hit, normal, view, r):
            if self.brush.kind == "mask":
                reg = self._region(c, n, v, r, pressure, for_mask=True)
                if reg is None:
                    continue
                idx, w, _f, _na, _ac = reg
                w = np.clip(w, 0.0, 1.0)
                before = self.mask[idx].copy()
                if self.smooth:
                    mean = self.topo.neighbor_mean(self.mask, idx, keep_boundary=False)
                    self.mask[idx] += (mean - self.mask[idx]) * w
                else:
                    goal = 1.0 if sign > 0 else 0.0
                    self.mask[idx] += (goal - self.mask[idx]) * w
                np.clip(self.mask, 0.0, 1.0, out=self.mask)
                if np.any(self.mask[idx] != before):
                    self.mask_dirty = True
                    changed = True
                total += len(idx)
                continue
            reg = self._region(c, n, v, r, pressure)
            if reg is None:
                continue
            idx, w, _f, na, ac = reg
            ctx = DabContext(self.W, idx, w, c, na, ac, r, v, sign, self.topo, self.target, self.mask)
            disp = self.brush.apply(ctx)
            disp[~np.isfinite(disp)] = 0.0
            if self._move(idx, self.W[idx] + disp):
                changed = True
            total += len(idx)
        return total, changed

    def _grab_dab(self, hit: np.ndarray, normal: np.ndarray, view: np.ndarray, pressure: float,
                  radius: float | None) -> tuple[int, bool]:
        if self._grab is None:
            r = self._radius(radius, pressure)
            groups = []
            for c, n, v, s in self._frames(hit, normal, view, r):
                reg = self._region(c, n, v, r, 1.0)
                if reg is None:
                    continue
                idx, w, _f, _na, _ac = reg
                groups.append((idx, np.clip(w, 0.0, 1.0), s))
            self._grab = groups
            self._grab_origin = hit.copy()
            self._grab_base = self.W.copy()
            return sum(len(g[0]) for g in groups), False
        delta = hit - self._grab_origin
        ld = self.inv @ delta
        W = self._grab_base.copy()
        touched = []
        for idx, w, s in self._grab:
            d = self.lin @ (ld * s)
            W[idx] += np.outer(w, d)
            touched.append(idx)
        if not touched:
            return 0, False
        idx = np.unique(np.concatenate(touched))
        return len(idx), self._move(idx, W[idx])

    def _publish(self) -> None:
        if not self.recorded and self._want_record:
            redo = getattr(self.scene, "_redo", None)
            self._redo_saved = list(redo) if isinstance(redo, list) else None
            data._record(self.scene)
            undo = getattr(self.scene, "_undo", None)
            self._undo_entry = undo[-1] if undo else None
        self.recorded = True
        if self.obj.mesh.points is not self.P:
            self.obj.mesh.points = self.P

    def dab(self, world_hit_point, world_normal=None, view_dir=None, pressure: float = 1.0,
            radius: float | None = None) -> int:
        if not self.valid or self.finished:
            return 0
        hit = np.asarray(world_hit_point, float).reshape(3)
        if not np.all(np.isfinite(hit)):
            return 0
        view = _unit(view_dir if view_dir is not None else (0.0, 0.0, 1.0), (0.0, 0.0, 1.0))
        normal = _unit(world_normal if world_normal is not None else -view, -view)
        pressure = float(min(max(pressure, 0.0), 1.0))
        changed = False
        if self.brush.kind == "grab":
            count, changed = self._grab_dab(hit, normal, view, pressure, radius)
        else:
            r = self._radius(radius, 1.0)
            step = float(self.settings.spacing) * r
            if self._last is None or step <= 1e-12:
                count, changed = self._apply_at(hit, normal, view, pressure, radius)
                self._last = hit.copy()
            else:
                dist = float(np.linalg.norm(hit - self._last))
                if dist < step:
                    self._last_pressure = pressure
                    return 0
                k = int(dist // step)
                count = 0
                start = self._last.copy()
                p0 = self._last_pressure
                for j in range(1, k + 1):
                    a = j * step / dist
                    c, ch = self._apply_at(start + (hit - start) * a, normal, view,
                                           p0 + (pressure - p0) * a, radius)
                    count += c
                    changed = changed or ch
                self._last = start + (hit - start) * (k * step / dist)
        self._last_pressure = pressure
        self.dabs += 1
        self.moved += count
        if changed:
            self.changed = True
            self._publish()
            data._changed(self.scene)
        return count

    def end(self) -> bool:
        if not self.valid or self.finished:
            return False
        self.finished = True
        _LIVE.discard(self)
        if not self.changed:
            return False
        data.commit_stroke(self.obj, None, self.P0, self.P,
                           self.mask if self.mask_dirty else None, self.scene)
        _store_bound(self.obj.mesh.points, self._base_topo, self.lin, self.edge_bound)
        return True

    def cancel(self) -> None:
        if not self.valid or self.finished:
            return
        self.finished = True
        _LIVE.discard(self)
        if not self.recorded:
            return
        self.obj.mesh.points = self.P0.copy()
        undo = getattr(self.scene, "_undo", None)
        if undo and self._undo_entry is not None and undo[-1] is self._undo_entry:
            undo.pop()
            redo = getattr(self.scene, "_redo", None)
            if isinstance(redo, list) and self._redo_saved is not None:
                redo[:] = self._redo_saved
        data._changed(self.scene)


def has_live_stroke(obj) -> bool:
    return any(s.obj is obj and not s.finished for s in list(_LIVE))


def end_strokes(obj=None) -> int:
    count = 0
    for s in list(_LIVE):
        if (obj is None or s.obj is obj) and not s.finished:
            s.end()
            count += 1
    return count


def stroke_begin(obj, settings, scene=None, *, smooth: bool = False, invert: bool | None = None,
                 record: bool = True) -> SculptStroke | None:
    global _CURRENT
    if _CURRENT is not None and not _CURRENT.finished:
        _CURRENT.end()
    stroke = SculptStroke(obj, settings, scene, smooth=smooth, invert=invert, record=record)
    _CURRENT = stroke if stroke.valid else None
    return _CURRENT


def stroke_dab(world_hit_point, world_normal=None, view_dir=None, pressure: float = 1.0,
               radius: float | None = None) -> int:
    if _CURRENT is None:
        return 0
    return _CURRENT.dab(world_hit_point, world_normal, view_dir, pressure, radius)


def stroke_end() -> bool:
    global _CURRENT
    stroke, _CURRENT = _CURRENT, None
    return stroke.end() if stroke is not None else False


def stroke_cancel() -> None:
    global _CURRENT
    stroke, _CURRENT = _CURRENT, None
    if stroke is not None:
        stroke.cancel()


def current_stroke() -> SculptStroke | None:
    return _CURRENT if _CURRENT is not None and not _CURRENT.finished else None


def apply_dab(obj, settings, world_hit_point, world_normal=None, view_dir=None, pressure: float = 1.0,
              radius: float | None = None, scene=None, **kw) -> int:
    stroke = SculptStroke(obj, settings, scene, **kw)
    if not stroke.valid:
        return 0
    count = stroke.dab(world_hit_point, world_normal, view_dir, pressure, radius)
    stroke.end()
    return count
