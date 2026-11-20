from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["Projected", "Buffers", "prepare", "rasterize", "empty_buffers", "resolve_bary",
           "RenderCancelled", "SMALL_LEVELS"]

SMALL_LEVELS = (1, 2, 4, 8, 16, 32)
BATCH_ELEMENTS = 1 << 20
PEEL_EPS = 1e-6


class RenderCancelled(Exception):
    pass


@dataclass
class Projected:
    sx: np.ndarray
    sy: np.ndarray
    z: np.ndarray
    src: np.ndarray
    bmat: np.ndarray
    ortho: bool
    width: int
    height: int
    coef: np.ndarray
    key: np.ndarray
    x0: np.ndarray
    x1: np.ndarray
    y0: np.ndarray
    y1: np.ndarray

    def __len__(self) -> int:
        return len(self.src)

    def scaled(self, factor: float) -> "Projected":
        f = float(factor)
        sx = (self.sx * f)
        sy = (self.sy * f)
        width = max(1, int(round(self.width * f)))
        height = max(1, int(round(self.height * f)))
        coef, x0, x1, y0, y1, ok = _setup(sx, sy, width, height)
        return Projected(sx[ok], sy[ok], self.z[ok], self.src[ok], self.bmat[ok], self.ortho, width, height,
                         coef[ok], self.key[ok], x0[ok], x1[ok], y0[ok], y1[ok])


@dataclass
class Buffers:
    depth: np.ndarray
    tri: np.ndarray
    bary: np.ndarray | None


def empty_buffers(h: int, w: int, with_bary: bool = True) -> Buffers:
    return Buffers(np.full((h, w), np.inf), np.full((h, w), -1, np.int64),
                   np.zeros((h, w, 3)) if with_bary else None)


def _clip_near(cam: np.ndarray, near: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t_count = len(cam)
    eye = np.eye(3)
    if not t_count:
        return np.zeros((0, 3, 3)), np.zeros(0, np.int64), np.zeros((0, 3, 3))
    behind = cam[:, :, 2] < near
    count = behind.sum(axis=1)
    out_p = []
    out_b = []
    out_s = []
    keep = np.flatnonzero(count == 0)
    if len(keep):
        out_p.append(cam[keep])
        out_b.append(np.broadcast_to(eye, (len(keep), 3, 3)))
        out_s.append(keep)
    one = np.flatnonzero(count == 1)
    if len(one):
        i = np.argmax(behind[one], axis=1)
        perm = (i[:, None] + np.arange(3)[None, :]) % 3
        p = np.take_along_axis(cam[one], perm[:, :, None], axis=1)
        e = eye[perm]
        pi, pj, pk = p[:, 0], p[:, 1], p[:, 2]
        ei, ej, ek = e[:, 0], e[:, 1], e[:, 2]
        tj = ((near - pi[:, 2]) / np.where(np.abs(pj[:, 2] - pi[:, 2]) < 1e-12, 1e-12, pj[:, 2] - pi[:, 2]))
        tk = ((near - pi[:, 2]) / np.where(np.abs(pk[:, 2] - pi[:, 2]) < 1e-12, 1e-12, pk[:, 2] - pi[:, 2]))
        a = pi + (pj - pi) * tj[:, None]
        b = pi + (pk - pi) * tk[:, None]
        ea = ei + (ej - ei) * tj[:, None]
        eb = ei + (ek - ei) * tk[:, None]
        out_p.append(np.stack([a, pj, pk], axis=1))
        out_b.append(np.stack([ea, ej, ek], axis=1))
        out_s.append(one)
        out_p.append(np.stack([a, pk, b], axis=1))
        out_b.append(np.stack([ea, ek, eb], axis=1))
        out_s.append(one)
    two = np.flatnonzero(count == 2)
    if len(two):
        i = np.argmin(behind[two], axis=1)
        perm = (i[:, None] + np.arange(3)[None, :]) % 3
        p = np.take_along_axis(cam[two], perm[:, :, None], axis=1)
        e = eye[perm]
        pi, pj, pk = p[:, 0], p[:, 1], p[:, 2]
        ei, ej, ek = e[:, 0], e[:, 1], e[:, 2]
        tj = ((near - pi[:, 2]) / np.where(np.abs(pj[:, 2] - pi[:, 2]) < 1e-12, 1e-12, pj[:, 2] - pi[:, 2]))
        tk = ((near - pi[:, 2]) / np.where(np.abs(pk[:, 2] - pi[:, 2]) < 1e-12, 1e-12, pk[:, 2] - pi[:, 2]))
        a = pi + (pj - pi) * tj[:, None]
        b = pi + (pk - pi) * tk[:, None]
        ea = ei + (ej - ei) * tj[:, None]
        eb = ei + (ek - ei) * tk[:, None]
        out_p.append(np.stack([pi, a, b], axis=1))
        out_b.append(np.stack([ei, ea, eb], axis=1))
        out_s.append(two)
    if not out_p:
        return np.zeros((0, 3, 3)), np.zeros(0, np.int64), np.zeros((0, 3, 3))
    return (np.concatenate(out_p), np.concatenate(out_s).astype(np.int64),
            np.concatenate([np.asarray(b, float) for b in out_b]))


def _setup(sx: np.ndarray, sy: np.ndarray, width: int, height: int):
    x0, x1, x2 = sx[:, 0], sx[:, 1], sx[:, 2]
    y0, y1, y2 = sy[:, 0], sy[:, 1], sy[:, 2]
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    ok = np.abs(area) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, area, 1.0), 0.0)
    a = np.stack([(y1 - y2), (y2 - y0), (y0 - y1)], axis=1) * inv[:, None]
    b = np.stack([(x2 - x1), (x0 - x2), (x1 - x0)], axis=1) * inv[:, None]
    c = np.stack([(x1 * y2 - x2 * y1), (x2 * y0 - x0 * y2), (x0 * y1 - x1 * y0)], axis=1) * inv[:, None]
    coef = np.stack([a, b, c], axis=1)
    minx = np.min(sx, axis=1)
    maxx = np.max(sx, axis=1)
    miny = np.min(sy, axis=1)
    maxy = np.max(sy, axis=1)
    with np.errstate(invalid="ignore"):
        bx0 = np.ceil(minx - 0.5)
        bx1 = np.floor(maxx - 0.5)
        by0 = np.ceil(miny - 0.5)
        by1 = np.floor(maxy - 0.5)
    finite = np.isfinite(bx0) & np.isfinite(bx1) & np.isfinite(by0) & np.isfinite(by1)
    bx0 = np.where(finite, np.clip(bx0, -1, width), 0).astype(np.int64)
    bx1 = np.where(finite, np.clip(bx1, -1, width), -1).astype(np.int64)
    by0 = np.where(finite, np.clip(by0, -1, height), 0).astype(np.int64)
    by1 = np.where(finite, np.clip(by1, -1, height), -1).astype(np.int64)
    bx0 = np.maximum(bx0, 0)
    by0 = np.maximum(by0, 0)
    bx1 = np.minimum(bx1, width - 1)
    by1 = np.minimum(by1, height - 1)
    ok = ok & finite & (bx1 >= bx0) & (by1 >= by0)
    return coef, bx0, bx1, by0, by1, ok


def prepare(cam_tris: np.ndarray, camera, width: int, height: int, near: float | None = None,
            front: np.ndarray | None = None, key: np.ndarray | None = None) -> Projected:
    cam_tris = np.asarray(cam_tris, float).reshape(-1, 3, 3)
    if key is None:
        key = np.arange(len(cam_tris), dtype=np.int64)
    if front is not None:
        sel = np.flatnonzero(front)
        cam_tris = cam_tris[sel]
        key = np.asarray(key)[sel]
    near_v = float(camera.near if near is None else near)
    clipped, src, bmat = _clip_near(cam_tris, near_v)
    src_key = np.asarray(key, np.int64)[src] if len(src) else np.zeros(0, np.int64)
    screen = camera.cam_to_screen(clipped, width, height) if len(clipped) else np.zeros((0, 3, 2))
    sx = screen[..., 0]
    sy = screen[..., 1]
    z = clipped[..., 2] if len(clipped) else np.zeros((0, 3))
    coef, x0, x1, y0, y1, ok = _setup(sx, sy, width, height)
    return Projected(sx[ok], sy[ok], z[ok], src_key[ok], bmat[ok], bool(camera.ortho), width, height,
                     coef[ok], np.flatnonzero(ok).astype(np.int64), x0[ok], x1[ok], y0[ok], y1[ok])


def _depth_terms(proj: Projected, idx: np.ndarray) -> np.ndarray:
    z = proj.z[idx]
    if proj.ortho:
        return z
    return 1.0 / np.where(np.abs(z) < 1e-12, 1e-12, z)


def _eval(coef: np.ndarray, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    a = coef[:, 0, :]
    b = coef[:, 1, :]
    c = coef[:, 2, :]
    return a[:, None, :] * px[..., None] + b[:, None, :] * py[..., None] + c[:, None, :]


def _depth_from(w: np.ndarray, terms: np.ndarray, ortho: bool) -> np.ndarray:
    s = np.einsum("...k,...k->...", w, terms)
    if ortho:
        return s
    return 1.0 / np.where(s > 1e-300, s, 1e-300)


def _persp_bary(w: np.ndarray, terms: np.ndarray, ortho: bool) -> np.ndarray:
    if ortho:
        return w
    q = w * terms
    s = q.sum(axis=-1, keepdims=True)
    return q / np.where(np.abs(s) > 1e-300, s, 1e-300)


def _merge(buf: Buffers, rx0: int, ry0: int, rw: int, pix: np.ndarray, z: np.ndarray, tri: np.ndarray,
           w: np.ndarray | None, terms: np.ndarray | None, ortho: bool) -> None:
    if not len(pix):
        return
    order = np.lexsort((z, pix))
    ps = pix[order]
    first = np.ones(len(ps), bool)
    first[1:] = ps[1:] != ps[:-1]
    sel = order[first]
    p = pix[sel]
    zf = buf.depth.reshape(-1)
    better = z[sel] < zf[p]
    sel = sel[better]
    p = p[better]
    if not len(p):
        return
    zf[p] = z[sel]
    buf.tri.reshape(-1)[p] = tri[sel]
    if buf.bary is not None and w is not None:
        buf.bary.reshape(-1, 3)[p] = _persp_bary(w[sel], terms[sel], ortho)


def rasterize(proj: Projected, region: tuple[int, int, int, int] | None = None,
              buffers: Buffers | None = None, with_bary: bool = True, subset: np.ndarray | None = None,
              cancel=None, progress=None, min_depth: np.ndarray | None = None) -> Buffers:
    if region is None:
        region = (0, 0, proj.width, proj.height)
    rx0, ry0, rx1, ry1 = (int(v) for v in region)
    rw, rh = rx1 - rx0, ry1 - ry0
    buf = buffers if buffers is not None else empty_buffers(rh, rw, with_bary)
    if rw <= 0 or rh <= 0 or not len(proj):
        return buf
    floor = None
    if min_depth is not None:
        floor = np.asarray(min_depth, float).reshape(rh, rw)
        floor = np.where(np.isfinite(floor), floor + np.abs(floor) * PEEL_EPS + PEEL_EPS, np.inf)
    if subset is None:
        idx = np.flatnonzero((proj.x1 >= rx0) & (proj.x0 < rx1) & (proj.y1 >= ry0) & (proj.y0 < ry1))
    else:
        idx = np.asarray(subset, np.int64)
    if not len(idx):
        return buf
    bx0 = np.maximum(proj.x0[idx], rx0)
    bx1 = np.minimum(proj.x1[idx], rx1 - 1)
    by0 = np.maximum(proj.y0[idx], ry0)
    by1 = np.minimum(proj.y1[idx], ry1 - 1)
    span = np.maximum(bx1 - bx0 + 1, by1 - by0 + 1)
    live = (bx1 >= bx0) & (by1 >= by0)
    want_bary = with_bary and buf.bary is not None
    level_of = np.full(len(idx), -1)
    for li, s in enumerate(SMALL_LEVELS):
        lo = SMALL_LEVELS[li - 1] if li else 0
        level_of[live & (span > lo) & (span <= s)] = li
    total = len(idx)
    done = 0
    for li, s in enumerate(SMALL_LEVELS):
        group = np.flatnonzero(level_of == li)
        if not len(group):
            continue
        chunk = max(1, BATCH_ELEMENTS // (s * s))
        oy, ox = np.divmod(np.arange(s * s), s)
        for start in range(0, len(group), chunk):
            if cancel is not None and cancel():
                raise RenderCancelled()
            g = group[start:start + chunk]
            tri = idx[g]
            px = bx0[g][:, None] + ox[None, :]
            py = by0[g][:, None] + oy[None, :]
            valid = (px <= bx1[g][:, None]) & (py <= by1[g][:, None])
            w = _eval(proj.coef[tri], px + 0.5, py + 0.5)
            inside = valid & (w >= -1e-9).all(axis=-1)
            ti, si = np.nonzero(inside)
            if not len(ti):
                continue
            ww = w[ti, si]
            terms = _depth_terms(proj, tri)[ti]
            z = _depth_from(ww, terms, proj.ortho)
            pix = (py[ti, si] - ry0) * rw + (px[ti, si] - rx0)
            if floor is not None:
                deeper = z > floor.reshape(-1)[pix]
                if not deeper.all():
                    pix, z, ti, ww, terms = pix[deeper], z[deeper], ti[deeper], ww[deeper], terms[deeper]
            _merge(buf, rx0, ry0, rw, pix, z, tri[ti], ww if want_bary else None,
                   terms if want_bary else None, proj.ortho)
            done += len(g)
            if progress is not None:
                progress(done / total)
    big = np.flatnonzero(live & (level_of < 0))
    zbuf = buf.depth
    for n, g in enumerate(big):
        if cancel is not None and n % 16 == 0 and cancel():
            raise RenderCancelled()
        t = idx[g]
        xs = np.arange(bx0[g], bx1[g] + 1)
        ys = np.arange(by0[g], by1[g] + 1)
        coef = proj.coef[t]
        pxc = xs[None, :] + 0.5
        pyc = ys[:, None] + 0.5
        w = (coef[0][None, None, :] * pxc[..., None] + coef[1][None, None, :] * pyc[..., None]
             + coef[2][None, None, :])
        inside = (w >= -1e-9).all(axis=-1)
        if not inside.any():
            continue
        terms = _depth_terms(proj, np.array([t]))[0]
        z = _depth_from(w, terms, proj.ortho)
        sub_y = slice(by0[g] - ry0, by1[g] - ry0 + 1)
        sub_x = slice(bx0[g] - rx0, bx1[g] - rx0 + 1)
        current = zbuf[sub_y, sub_x]
        win = inside & (z < current)
        if floor is not None:
            win &= z > floor[sub_y, sub_x]
        if not win.any():
            continue
        current[win] = z[win]
        buf.tri[sub_y, sub_x][win] = t
        if want_bary:
            buf.bary[sub_y, sub_x][win] = _persp_bary(w[win], terms[None, :], proj.ortho)
        done += 1
        if progress is not None and n % 16 == 0:
            progress(min(1.0, done / total))
    if progress is not None:
        progress(1.0)
    return buf


def resolve_bary(proj: Projected, tri: np.ndarray, bary: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    src = proj.src[tri]
    b = np.einsum("ni,nij->nj", bary, proj.bmat[tri])
    return src, b
