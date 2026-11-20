from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from .data import (Corners, bounds_uv, corners_of_polys, edge_key, finite_mesh, get_seams, mesh_triangles,
                   point_groups, polygon_area_3d, polygon_area_uv, set_seams, transform_uv,
                   uv_islands)
from .unwrap import _local_frames, chart_from_uv

__all__ = [
    "island_corners",
    "convex_hull",
    "min_area_angle",
    "skyline_pack",
    "pack_islands",
    "align_islands",
    "align_points",
    "straighten",
    "rectify",
    "flip",
    "rotate90",
    "fit_to_bounds",
    "stitch_edges",
    "boundary_edges_of_selection",
    "uv_stats",
    "polygon_stretch",
]


def island_corners(corners: Corners, island: Iterable[int]) -> np.ndarray:
    return corners_of_polys(corners, island)


def convex_hull(pts: np.ndarray) -> np.ndarray:
    pts = np.unique(np.asarray(pts, float).reshape(-1, 2), axis=0)
    if len(pts) <= 2:
        return pts
    order = np.lexsort((pts[:, 1], pts[:, 0]))
    pts = pts[order]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 1e-15:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 1e-15:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def min_area_angle(pts: np.ndarray) -> float:
    hull = convex_hull(pts)
    if len(hull) < 3:
        if len(hull) == 2:
            d = hull[1] - hull[0]
            return math.atan2(d[1], d[0])
        return 0.0
    best_area, best_angle = math.inf, 0.0
    for i in range(len(hull)):
        d = hull[(i + 1) % len(hull)] - hull[i]
        if np.hypot(d[0], d[1]) < 1e-15:
            continue
        ang = math.atan2(d[1], d[0])
        c, s = math.cos(-ang), math.sin(-ang)
        r = hull @ np.array([[c, -s], [s, c]]).T
        span = r.max(axis=0) - r.min(axis=0)
        area = float(span[0] * span[1])
        if area < best_area - 1e-15:
            best_area, best_angle = area, ang
    return best_angle


def _rot(pts: np.ndarray, ang: float, pivot) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    piv = np.asarray(pivot, float)
    return (pts - piv) @ np.array([[c, -s], [s, c]]).T + piv


def _search_rotation(pts: np.ndarray, step_degrees: float = 15.0) -> np.ndarray:
    if len(pts) < 2:
        return pts
    pivot = pts.mean(axis=0)
    span = pts.max(axis=0) - pts.min(axis=0)
    best_area, best = float(span[0] * span[1]), pts
    steps = max(1, int(round(90.0 / float(step_degrees))))
    for k in range(1, steps):
        r = _rot(pts, math.radians(k * float(step_degrees)), pivot)
        span = r.max(axis=0) - r.min(axis=0)
        area = float(span[0] * span[1])
        if area < best_area * (1.0 - 1e-9):
            best_area, best = area, r
    return best


def skyline_pack(sizes: list[tuple[float, float]], width: float,
                 rotate: bool = True) -> tuple[list, float] | None:
    sky: list[list[float]] = [[0.0, 0.0, float(width)]]
    out: list = [None] * len(sizes)
    order = sorted(range(len(sizes)), key=lambda i: (-max(sizes[i]), -min(sizes[i]), i))
    eps = 1e-12 * max(width, 1.0)
    for i in order:
        w0, h0 = sizes[i]
        options = [(w0, h0, False)]
        if rotate and abs(w0 - h0) > eps:
            options.append((h0, w0, True))
        best = None
        for w, h, rot in options:
            if w > width + eps:
                continue
            for s in range(len(sky)):
                x = sky[s][0]
                if x + w > width + eps:
                    break
                y = 0.0
                t = s
                reach = x
                while reach < x + w - eps and t < len(sky):
                    y = max(y, sky[t][1])
                    reach = sky[t][0] + sky[t][2]
                    t += 1
                score = (y + h, x, rot)
                if best is None or score < best[0]:
                    best = (score, x, y, w, h, rot)
        if best is None:
            return None
        _, x, y, w, h, rot = best
        out[i] = (x, y, rot)
        top = y + h
        new_sky: list[list[float]] = []
        for seg in sky:
            sx, sy, sw = seg
            ex = sx + sw
            if ex <= x + eps or sx >= x + w - eps:
                new_sky.append(seg)
                continue
            if sx < x - eps:
                new_sky.append([sx, sy, x - sx])
            if ex > x + w + eps:
                new_sky.append([x + w, sy, ex - (x + w)])
        new_sky.append([x, top, w])
        new_sky.sort(key=lambda seg: seg[0])
        merged: list[list[float]] = []
        for seg in new_sky:
            if merged and abs(merged[-1][1] - seg[1]) <= eps:
                merged[-1][2] = seg[0] + seg[2] - merged[-1][0]
            else:
                merged.append(list(seg))
        sky = merged
    height = max(seg[1] for seg in sky)
    return out, height


def _best_square(sizes: list[tuple[float, float]], rotate: bool) -> tuple[list, float]:
    area = sum(w * h for w, h in sizes)
    longest = max(max(w, h) for w, h in sizes)
    shortest_need = max(min(w, h) for w, h in sizes) if rotate else max(w for w, _ in sizes)
    lo = max(math.sqrt(max(area, 1e-300)), shortest_need)
    hi = max(lo * 3.0, longest, sum(w for w, _ in sizes) if len(sizes) < 3 else lo * 3.0)
    best = None
    for k in range(40):
        width = lo * (hi / lo) ** (k / 39.0) if hi > lo else lo
        res = skyline_pack(sizes, width, rotate)
        if res is None:
            continue
        placements, height = res
        used_w = 0.0
        for (w0, h0), (x, _y, rot) in zip(sizes, placements):
            used_w = max(used_w, x + (h0 if rot else w0))
        side = max(used_w, height)
        if best is None or side < best[1] - 1e-15:
            best = (placements, side)
    if best is None:
        res = skyline_pack(sizes, hi * 4.0, rotate)
        placements, height = res
        best = (placements, max(height, hi * 4.0))
    return best


def _tri_cells(uv: np.ndarray, tris: np.ndarray, grid: int, chunk: int = 1 << 21):
    if not len(tris):
        return
    p = np.asarray(uv, float)[tris]
    finite = np.isfinite(p).all(axis=(1, 2))
    p = np.where(finite[:, None, None], p, 0.0)
    pmin = p.min(axis=1)
    pmax = p.max(axis=1)
    a, b, c = p[:, 0], p[:, 1], p[:, 2]
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    ok = finite & (pmax >= 0).all(axis=1) & (pmin <= 1).all(axis=1) & (np.abs(det) > 1e-300)
    ids = np.nonzero(ok)[0]
    if not len(ids):
        return
    lo = np.clip(np.floor(pmin[ids] * grid - 0.5), 0, grid - 1).astype(np.int64)
    hi = np.clip(np.ceil(pmax[ids] * grid - 0.5), 0, grid - 1).astype(np.int64)
    nx = hi[:, 0] - lo[:, 0] + 1
    ny = hi[:, 1] - lo[:, 1] + 1
    counts = nx * ny
    cum = np.cumsum(counts)
    start = 0
    while start < len(ids):
        base = cum[start - 1] if start else 0
        stop = int(np.searchsorted(cum, base + chunk, side="right"))
        stop = max(stop, start + 1)
        sel = np.arange(start, stop)
        cnt = counts[sel]
        total = int(cnt.sum())
        rep = np.repeat(sel, cnt)
        offs = np.repeat(np.cumsum(cnt) - cnt, cnt)
        local = np.arange(total, dtype=np.int64) - offs
        w = nx[rep]
        cx = lo[rep, 0] + local % w
        cy = lo[rep, 1] + local // w
        X = (cx + 0.5) / grid
        Y = (cy + 0.5) / grid
        t = ids[rep]
        ax, ay, bx, by, qx, qy = a[t, 0], a[t, 1], b[t, 0], b[t, 1], c[t, 0], c[t, 1]
        d = det[t]
        w1 = ((bx - X) * (qy - Y) - (by - Y) * (qx - X)) / d
        w2 = ((qx - X) * (ay - Y) - (qy - Y) * (ax - X)) / d
        w3 = 1.0 - w1 - w2
        inside = (w1 >= -1e-12) & (w2 >= -1e-12) & (w3 >= -1e-12)
        strict = (w1 > 1e-9) & (w2 > 1e-9) & (w3 > 1e-9)
        yield cy, cx, t, inside, strict
        start = stop


def _occupancy(uv: np.ndarray, tris: np.ndarray, grid: int, dilate: int = 0) -> np.ndarray:
    occ = np.zeros(grid * grid, dtype=bool)
    for cy, cx, _t, inside, _s in _tri_cells(uv, tris, grid):
        occ[(cy * grid + cx)[inside]] = True
    if len(tris):
        pts = np.asarray(uv, float)[np.unique(tris.reshape(-1))]
        pts = pts[np.isfinite(pts).all(axis=1)]
        cell = np.floor(pts * grid).astype(np.int64)
        good = ((cell >= 0) & (cell < grid)).all(axis=1)
        occ[cell[good, 1] * grid + cell[good, 0]] = True
    occ = occ.reshape(grid, grid)
    if dilate > 0 and occ.any():
        sat = np.zeros((grid + 1, grid + 1), dtype=np.int64)
        sat[1:, 1:] = occ.astype(np.int64).cumsum(axis=0).cumsum(axis=1)
        k = int(dilate)
        ys = np.arange(grid)
        y0 = np.clip(ys - k, 0, grid)
        y1 = np.clip(ys + k + 1, 0, grid)
        s = sat[y1][:, y1] - sat[y0][:, y1] - sat[y1][:, y0] + sat[y0][:, y0]
        occ = s > 0
    return occ


def _first_free(occ: np.ndarray, w: int, h: int) -> tuple[int, int] | None:
    g = occ.shape[0]
    if w > g or h > g or w < 1 or h < 1:
        return None
    sat = np.zeros((g + 1, g + 1), dtype=np.int64)
    sat[1:, 1:] = occ.astype(np.int64).cumsum(axis=0).cumsum(axis=1)
    win = sat[h:, w:] - sat[:-h, w:] - sat[h:, :-w] + sat[:-h, :-w]
    free = np.nonzero(win.reshape(-1) == 0)[0]
    if not len(free):
        return None
    k = int(free[0])
    cols = win.shape[1]
    return k % cols, k // cols


def _place_into_free(occ: np.ndarray, sizes: list[tuple[float, float]], rotate: bool):
    g = occ.shape[0]
    occ = occ.copy()
    out: list = [None] * len(sizes)
    order = sorted(range(len(sizes)), key=lambda i: (-max(sizes[i]), -min(sizes[i]), i))
    for i in order:
        w0, h0 = sizes[i]
        best = None
        options = [(w0, h0, False)]
        if rotate and abs(w0 - h0) > 1e-12:
            options.append((h0, w0, True))
        for w, h, rot in options:
            wc, hc = int(math.ceil(w * g - 1e-9)), int(math.ceil(h * g - 1e-9))
            spot = _first_free(occ, wc, hc)
            if spot is None:
                continue
            score = (spot[1] + hc, spot[0], rot)
            if best is None or score < best[0]:
                best = (score, spot, wc, hc, rot)
        if best is None:
            return None
        _score, (x, y), wc, hc, rot = best
        occ[y:y + hc, x:x + wc] = True
        out[i] = (x / g, y / g, rot)
    return out


def _pack_avoiding(mesh, out: np.ndarray, corners: Corners, islands: list[list[int]], locals_: list,
                   idxs: list, raw: list, margin: float, rotate: bool, equalize: bool,
                   grid: int = 256) -> bool:
    chosen = np.zeros(corners.poly_count, dtype=bool)
    for isl in islands:
        chosen[isl] = True
    others = np.nonzero(~chosen)[0]
    if not len(others):
        return False
    tris, owner = mesh_triangles(mesh, corners, others.tolist())
    if not len(tris):
        return False
    pad = max(float(margin), 0.0)
    occ = _occupancy(out, tris, grid, dilate=int(math.ceil(pad / 2.0 * grid)))
    free_frac = 1.0 - float(occ.mean())
    if occ.mean() <= 0.0 or free_frac < 0.05:
        return False
    total = sum(w * h for w, h in raw)
    if total <= 0:
        return False
    s_hi = math.sqrt(free_frac / total)
    s_hi = min(s_hi, min((1.0 - pad) / max(max(w, h), 1e-12) for w, h in raw))
    if equalize:
        a3 = polygon_area_3d(mesh, corners)[others]
        auv = np.abs(polygon_area_uv(out, corners))[others]
        if a3.sum() > 1e-300 and auv.sum() > 1e-300:
            s_hi = min(s_hi, math.sqrt(float(auv.sum()) / float(a3.sum())))
    if s_hi <= 0:
        return False

    def attempt(s: float):
        sizes = [(w * s + pad, h * s + pad) for w, h in raw]
        return _place_into_free(occ, sizes, rotate)

    best_s, best = s_hi, attempt(s_hi)
    if best is None:
        lo_s, hi_s = 0.0, s_hi
        for _ in range(14):
            mid = (lo_s + hi_s) / 2.0
            res = attempt(mid)
            if res is None:
                hi_s = mid
            else:
                lo_s, best_s, best = mid, mid, res
        if best is None or best_s < 0.02 * s_hi:
            return False
    for pts, idx, (w, h), (x, y, rot) in zip(locals_, idxs, raw, best):
        p = pts * best_s
        if rot:
            p = np.stack([h * best_s - p[:, 1], p[:, 0]], axis=1)
        out[idx] = p + np.array([x + pad / 2.0, y + pad / 2.0])
    return True


def pack_islands(mesh, uv: np.ndarray, corners: Corners | None = None,
                 polys: Iterable[int] | None = None, *, margin: float = 0.01, rotate: bool = True,
                 equalize: bool = True, align: bool = False, avoid: bool = True,
                 rotation_search: bool = False) -> np.ndarray:
    mesh = finite_mesh(mesh)
    corners = corners or Corners(mesh)
    out = np.array(uv, dtype=float, copy=True)
    out = np.where(np.isfinite(out), out, 0.0)
    islands = uv_islands(mesh, out, corners, polys)
    if not islands:
        return out
    a3 = polygon_area_3d(mesh, corners)
    auv = np.abs(polygon_area_uv(out, corners))
    locals_: list[np.ndarray] = []
    idxs: list[np.ndarray] = []
    for isl in islands:
        idx = island_corners(corners, isl)
        pts = out[idx].copy()
        if equalize:
            s3 = float(a3[isl].sum())
            su = float(auv[isl].sum())
            if su > 1e-300 and s3 > 0:
                center = pts.mean(axis=0)
                pts = (pts - center) * math.sqrt(s3 / su) + center
        if align and len(pts) >= 2:
            ang = min_area_angle(pts)
            pts = _rot(pts, -ang, pts.mean(axis=0))
        if rotation_search:
            pts = _search_rotation(pts)
        locals_.append(pts - pts.min(axis=0))
        idxs.append(idx)
    raw = [tuple(float(v) for v in (p.max(axis=0) if len(p) else np.zeros(2))) for p in locals_]
    raw = [(max(w, 1e-9), max(h, 1e-9)) for w, h in raw]
    if avoid and polys is not None and _pack_avoiding(mesh, out, corners, islands, locals_, idxs, raw,
                                                      margin, rotate, equalize):
        return out
    side_est = math.sqrt(sum(w * h for w, h in raw))
    pad = float(margin) * side_est
    placements, side = None, 1.0
    for _ in range(3):
        sizes = [(w + pad, h + pad) for w, h in raw]
        placements, side = _best_square(sizes, rotate)
        new_pad = float(margin) * side
        if abs(new_pad - pad) <= 1e-6 * max(side, 1e-300):
            pad = new_pad
            sizes = [(w + pad, h + pad) for w, h in raw]
            placements, side = _best_square(sizes, rotate)
            break
        pad = new_pad
    if side <= 0:
        return out
    scale = 1.0 / side
    for pts, idx, (w, h), (x, y, rot) in zip(locals_, idxs, raw, placements):
        p = pts
        if rot:
            p = np.stack([h - p[:, 1], p[:, 0]], axis=1)
        p = p + np.array([x + pad / 2.0, y + pad / 2.0])
        out[idx] = p * scale
    return out


def align_islands(mesh, uv: np.ndarray, corners: Corners | None = None,
                  polys: Iterable[int] | None = None, mode: str = "Auto") -> np.ndarray:
    corners = corners or Corners(mesh)
    out = np.array(uv, dtype=float, copy=True)
    out = np.where(np.isfinite(out), out, 0.0)
    for isl in uv_islands(mesh, out, corners, polys):
        idx = island_corners(corners, isl)
        pts = out[idx]
        if len(pts) < 2:
            continue
        center = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
        ang = min_area_angle(pts)
        p = _rot(pts, -ang, center)
        span = p.max(axis=0) - p.min(axis=0)
        key = str(mode).lower()
        if (key == "u" and span[1] > span[0]) or (key == "v" and span[0] > span[1]):
            p = _rot(p, math.pi / 2.0, center)
        out[idx] = p
    return out


def align_points(uv: np.ndarray, idx, axis: str = "U") -> np.ndarray:
    out = np.array(uv, dtype=float, copy=True)
    idx = np.asarray(idx, dtype=np.int64)
    if not len(idx):
        return out
    k = 0 if str(axis).upper() == "U" else 1
    out[idx, k] = out[idx, k].mean()
    return out


def straighten(uv: np.ndarray, idx, snap_degrees: float = 15.0) -> np.ndarray:
    out = np.array(uv, dtype=float, copy=True)
    idx = np.asarray(idx, dtype=np.int64)
    if len(idx) < 2:
        return out
    pts = out[idx]
    center = pts.mean(axis=0)
    d = pts - center
    _, _, vt = np.linalg.svd(d, full_matrices=False)
    direction = vt[0]
    ang = math.degrees(math.atan2(direction[1], direction[0])) % 180.0
    for target in (0.0, 90.0, 180.0):
        if abs(ang - target) <= snap_degrees:
            r = math.radians(target)
            direction = np.array([math.cos(r), math.sin(r)])
            break
    t = d @ direction
    out[idx] = center + t[:, None] * direction[None, :]
    return out


def _procrustes(src: np.ndarray, dst: np.ndarray, mirror: bool) -> tuple[np.ndarray, np.ndarray, float]:
    ms, md = src.mean(axis=0), dst.mean(axis=0)
    a, b = src - ms, dst - md
    if mirror:
        a = a * np.array([1.0, -1.0])
    sxx = float((a[:, 0] * b[:, 0] + a[:, 1] * b[:, 1]).sum())
    sxy = float((a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum())
    ang = math.atan2(sxy, sxx)
    ang = round(ang / (math.pi / 2.0)) * (math.pi / 2.0)
    c, s = round(math.cos(ang)), round(math.sin(ang))
    r = np.array([[c, -s], [s, c]], float)
    if mirror:
        r = r @ np.diag([1.0, -1.0])
    ra = (src - ms) @ r.T
    denom = float((ra * ra).sum())
    scale = float((ra * b).sum()) / denom if denom > 1e-300 else 1.0
    return r, md - scale * (ms @ r.T), scale


def rectify(mesh, uv: np.ndarray, corners: Corners | None = None,
            polys: Iterable[int] | None = None) -> tuple[np.ndarray, int]:
    mesh = finite_mesh(mesh)
    corners = corners or Corners(mesh)
    out = np.array(uv, dtype=float, copy=True)
    done = 0
    for isl in uv_islands(mesh, out, corners, polys):
        chart = chart_from_uv(mesh, corners, out, isl)
        if not chart.faces or any(len(f) != 4 or len(set(f)) != 4 for f in chart.faces):
            continue
        grid: dict[int, tuple[int, int]] = {}
        edge_faces: dict[tuple[int, int], list[int]] = {}
        for fi, f in enumerate(chart.faces):
            for a, b in zip(f, f[1:] + f[:1]):
                edge_faces.setdefault((min(a, b), max(a, b)), []).append(fi)
        f0 = chart.faces[0]
        for v, g in zip(f0, ((0, 0), (1, 0), (1, 1), (0, 1))):
            grid[v] = g
        seen = {0}
        queue = [0]
        ok = True
        head = 0
        while head < len(queue) and ok:
            fi = queue[head]
            head += 1
            for a, b in zip(chart.faces[fi], chart.faces[fi][1:] + chart.faces[fi][:1]):
                for g in edge_faces.get((min(a, b), max(a, b)), ()):
                    if g in seen:
                        continue
                    f = chart.faces[g]
                    start = None
                    for i in range(4):
                        if f[i] in grid and f[(i + 1) % 4] in grid:
                            start = i
                            break
                    if start is None:
                        continue
                    q0 = np.array(grid[f[start]])
                    q1 = np.array(grid[f[(start + 1) % 4]])
                    d = q1 - q0
                    perp = np.array([-d[1], d[0]])
                    want = {f[start]: tuple(q0), f[(start + 1) % 4]: tuple(q1),
                            f[(start + 2) % 4]: tuple(q1 + perp), f[(start + 3) % 4]: tuple(q0 + perp)}
                    for v, gv in want.items():
                        gv = (int(gv[0]), int(gv[1]))
                        if v in grid and grid[v] != gv:
                            ok = False
                            break
                        grid[v] = gv
                    if not ok:
                        break
                    seen.add(g)
                    queue.append(g)
                if not ok:
                    break
        if not ok or len(seen) != len(chart.faces):
            continue
        used = sorted(grid)
        gi = np.array([grid[v] for v in used])
        lo = gi.min(axis=0)
        gi = gi - lo
        nx, ny = int(gi[:, 0].max()), int(gi[:, 1].max())
        coord = {v: tuple(g) for v, g in zip(used, gi.tolist())}
        widths = np.zeros(max(nx, 1))
        wcount = np.zeros(max(nx, 1))
        heights = np.zeros(max(ny, 1))
        hcount = np.zeros(max(ny, 1))
        for f in chart.faces:
            for a, b in zip(f, f[1:] + f[:1]):
                ga, gb = coord[a], coord[b]
                length = float(np.linalg.norm(chart.positions[a] - chart.positions[b]))
                if ga[1] == gb[1] and abs(ga[0] - gb[0]) == 1:
                    i = min(ga[0], gb[0])
                    widths[i] += length
                    wcount[i] += 1
                elif ga[0] == gb[0] and abs(ga[1] - gb[1]) == 1:
                    j = min(ga[1], gb[1])
                    heights[j] += length
                    hcount[j] += 1
        widths = np.where(wcount > 0, widths / np.maximum(wcount, 1), 1.0)
        heights = np.where(hcount > 0, heights / np.maximum(hcount, 1), 1.0)
        ucol = np.concatenate([[0.0], np.cumsum(widths)])
        vrow = np.concatenate([[0.0], np.cumsum(heights)])
        layout = np.zeros((chart.vertex_count, 2))
        for v, (i, j) in coord.items():
            layout[v] = (ucol[i], vrow[j])
        current = np.zeros((chart.vertex_count, 2))
        current[chart.labels] = out[chart.corner_index]
        area_cur = float(polygon_area_uv(out, corners)[isl].sum())
        r, t, s = _procrustes(layout[used], current[used], mirror=area_cur < 0)
        fitted = layout @ r.T * s + t
        out[chart.corner_index] = fitted[chart.labels]
        done += 1
    return out, done


def _center(uv, idx):
    lo, hi = bounds_uv(uv, idx)
    return (lo + hi) / 2.0


def flip(uv: np.ndarray, idx, axis: str = "U", pivot=None) -> np.ndarray:
    idx = np.asarray(idx, dtype=np.int64)
    pivot = _center(uv, idx) if pivot is None else pivot
    m = np.diag([-1.0, 1.0]) if str(axis).upper() == "U" else np.diag([1.0, -1.0])
    return transform_uv(uv, idx, m, pivot)


def rotate90(uv: np.ndarray, idx, clockwise: bool = False, pivot=None) -> np.ndarray:
    idx = np.asarray(idx, dtype=np.int64)
    pivot = _center(uv, idx) if pivot is None else pivot
    m = np.array([[0.0, 1.0], [-1.0, 0.0]]) if clockwise else np.array([[0.0, -1.0], [1.0, 0.0]])
    return transform_uv(uv, idx, m, pivot)


def fit_to_bounds(uv: np.ndarray, idx, keep_aspect: bool = True, margin: float = 0.0,
                  lo_bound=(0.0, 0.0), hi_bound=(1.0, 1.0)) -> np.ndarray:
    out = np.array(uv, dtype=float, copy=True)
    idx = np.asarray(idx, dtype=np.int64)
    if not len(idx):
        return out
    lo, hi = bounds_uv(out, idx)
    span = hi - lo
    blo = np.asarray(lo_bound, float) + margin
    bhi = np.asarray(hi_bound, float) - margin
    room = np.maximum(bhi - blo, 1e-12)
    if keep_aspect:
        s = float(min(room[0] / max(span[0], 1e-12), room[1] / max(span[1], 1e-12)))
        if span[0] < 1e-12:
            s = room[1] / max(span[1], 1e-12)
        if span[1] < 1e-12:
            s = room[0] / max(span[0], 1e-12)
        scaled = (out[idx] - lo) * s
        extent = span * s
        out[idx] = scaled + blo + (room - extent) / 2.0
    else:
        safe = np.where(span < 1e-12, 1.0, span)
        out[idx] = (out[idx] - lo) / safe * room + blo
    return out


def _signed_area(uv: np.ndarray, corners: Corners, polys) -> float:
    return float(polygon_area_uv(uv, corners)[list(polys)].sum())


def boundary_edges_of_selection(mesh, uv: np.ndarray, corners: Corners,
                                selected_corners: Iterable[int]) -> list[tuple[int, int]]:
    sel = set(int(c) for c in selected_corners)
    groups = point_groups(corners, uv)
    sel_groups = {int(groups[c]) for c in sel}
    out = []
    for key, cs in corners.edges().items():
        if len(cs) != 2:
            continue
        c1, c2 = cs
        ends1 = (c1, int(corners.next[c1]))
        ends2 = (c2, int(corners.next[c2]))
        hit1 = all(int(groups[c]) in sel_groups for c in ends1)
        hit2 = all(int(groups[c]) in sel_groups for c in ends2)
        if not (hit1 or hit2):
            continue
        same = {int(groups[c]) for c in ends1} == {int(groups[c]) for c in ends2}
        if not same:
            out.append(key)
    return sorted(out)


def stitch_edges(mesh, uv: np.ndarray, edges: Iterable, corners: Corners | None = None,
                 move: str = "smaller") -> tuple[np.ndarray, list[tuple[int, int]]]:
    corners = corners or Corners(mesh)
    out = np.array(uv, dtype=float, copy=True)
    welded: list[tuple[int, int]] = []
    for e in edges:
        key = edge_key(e[0], e[1])
        cs = corners.edges().get(key, [])
        if len(cs) != 2:
            continue
        c1, c2 = cs
        p1, p2 = int(corners.poly[c1]), int(corners.poly[c2])
        a, b = key
        ca1, cb1 = corners.corner_of(p1, a), corners.corner_of(p1, b)
        ca2, cb2 = corners.corner_of(p2, a), corners.corner_of(p2, b)
        if None in (ca1, cb1, ca2, cb2):
            continue
        if np.abs(out[ca1] - out[ca2]).max() <= 1e-9 and np.abs(out[cb1] - out[cb2]).max() <= 1e-9:
            welded.append(key)
            continue
        islands = uv_islands(mesh, out, corners)
        owner = {}
        for i, isl in enumerate(islands):
            for p in isl:
                owner[p] = i
        i1, i2 = owner[p1], owner[p2]
        if i1 == i2:
            ga = point_groups(corners, out)
            for x, y in ((ca1, ca2), (cb1, cb2)):
                mid = (out[x] + out[y]) / 2.0
                gx, gy = ga[x], ga[y]
                out[(ga == gx) | (ga == gy)] = mid
            welded.append(key)
            continue
        size1 = len(islands[i1])
        size2 = len(islands[i2])
        key_move = str(move).lower()
        if key_move == "first":
            move_first = True
        elif key_move == "second":
            move_first = False
        else:
            move_first = size1 <= size2
        if move_first:
            fixed, moving = i2, i1
            src_a, src_b, dst_a, dst_b = out[ca1], out[cb1], out[ca2], out[cb2]
        else:
            fixed, moving = i1, i2
            src_a, src_b, dst_a, dst_b = out[ca2], out[cb2], out[ca1], out[cb1]
        midx = island_corners(corners, islands[moving])
        fixed_polys = islands[fixed]
        moving_polys = islands[moving]
        mirror = (_signed_area(out, corners, fixed_polys) < 0) != (_signed_area(out, corners, moving_polys) < 0)
        pts = out[midx].copy()
        sa, sb = src_a.copy(), src_b.copy()
        if mirror:
            pts[:, 1] = -pts[:, 1]
            sa[1], sb[1] = -sa[1], -sb[1]
        za, zb = complex(sa[0], sa[1]), complex(sb[0], sb[1])
        wa, wb = complex(dst_a[0], dst_a[1]), complex(dst_b[0], dst_b[1])
        if abs(zb - za) < 1e-15:
            alpha = 1.0 + 0j
        else:
            alpha = (wb - wa) / (zb - za)
        beta = wa - alpha * za
        z = pts[:, 0] + 1j * pts[:, 1]
        z = alpha * z + beta
        out[midx] = np.stack([z.real, z.imag], axis=1)
        fixed_set = set(fixed_polys)
        moving_set = set(moving_polys)
        for k2, cs2 in corners.edges().items():
            if len(cs2) != 2:
                continue
            q1, q2 = int(corners.poly[cs2[0]]), int(corners.poly[cs2[1]])
            if q1 in fixed_set and q2 in moving_set:
                fpoly, mpoly = q1, q2
            elif q2 in fixed_set and q1 in moving_set:
                fpoly, mpoly = q2, q1
            else:
                continue
            fa, fb = corners.corner_of(fpoly, k2[0]), corners.corner_of(fpoly, k2[1])
            ma, mb = corners.corner_of(mpoly, k2[0]), corners.corner_of(mpoly, k2[1])
            close_a = np.linalg.norm(out[fa] - out[ma])
            close_b = np.linalg.norm(out[fb] - out[mb])
            tol = 1e-6 + 1e-3 * float(np.linalg.norm(dst_b - dst_a))
            if k2 == key or (close_a <= tol and close_b <= tol):
                out[ma] = out[fa]
                out[mb] = out[fb]
                welded.append(k2)
    return out, sorted(set(welded))


def polygon_stretch(mesh, uv: np.ndarray, corners: Corners | None = None) -> dict:
    mesh = finite_mesh(mesh)
    uv = np.where(np.isfinite(np.asarray(uv, float)), np.asarray(uv, float), 0.0)
    corners = corners or Corners(mesh)
    tris, owner = mesh_triangles(mesh, corners)
    n_poly = corners.poly_count
    res = {
        "area_log": np.zeros(n_poly),
        "conformal": np.ones(n_poly),
        "l2": np.ones(n_poly),
        "tri_l2": np.zeros(0),
        "tri_area": np.zeros(0),
        "tri_owner": owner,
        "global_scale": 1.0,
    }
    if not len(tris):
        return res
    P = mesh.points[corners.vertex]
    q, ok = _local_frames(P, tris)
    uv = np.asarray(uv, float)
    a3 = 0.5 * (q[:, 1, 0] * q[:, 2, 1] - q[:, 2, 0] * q[:, 1, 1])
    u0, u1, u2 = uv[tris[:, 0]], uv[tris[:, 1]], uv[tris[:, 2]]
    auv = 0.5 * ((u1[:, 0] - u0[:, 0]) * (u2[:, 1] - u0[:, 1]) - (u1[:, 1] - u0[:, 1]) * (u2[:, 0] - u0[:, 0]))
    total3 = float(a3[ok].sum())
    totaluv = float(np.abs(auv[ok]).sum())
    g = math.sqrt(total3 / totaluv) if totaluv > 1e-300 else 1.0
    res["global_scale"] = g
    dq = np.stack([q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]], axis=2)
    du = np.stack([u1 - u0, u2 - u0], axis=2) * g
    det = dq[:, 0, 0] * dq[:, 1, 1] - dq[:, 0, 1] * dq[:, 1, 0]
    safe = np.where(np.abs(det) < 1e-300, 1.0, det)
    inv = np.stack([np.stack([dq[:, 1, 1], -dq[:, 0, 1]], axis=1),
                    np.stack([-dq[:, 1, 0], dq[:, 0, 0]], axis=1)], axis=1) / safe[:, None, None]
    J = du @ inv
    a, b, c, d = J[:, 0, 0], J[:, 0, 1], J[:, 1, 0], J[:, 1, 1]
    e2 = (a * a + b * b + c * c + d * d) / 2.0
    dj = np.abs(a * d - b * c)
    disc = np.sqrt(np.maximum(e2 * e2 - dj * dj, 0.0))
    s1 = np.sqrt(np.maximum(e2 + disc, 0.0))
    s2 = np.sqrt(np.maximum(e2 - disc, 0.0))
    l2 = np.sqrt((s1 * s1 + s2 * s2) / 2.0)
    conf = s1 / np.maximum(s2, 1e-12)
    area_ratio = np.maximum(s1 * s2, 1e-12)
    w = np.where(ok, np.abs(a3), 0.0)
    l2 = np.where(ok, l2, 1.0)
    conf = np.where(ok, np.minimum(conf, 1e6), 1.0)
    alog = np.where(ok, np.log2(area_ratio), 0.0)
    wsum = np.bincount(owner, weights=w, minlength=n_poly)
    safe_w = np.where(wsum > 0, wsum, 1.0)
    res["area_log"] = np.bincount(owner, weights=w * alog, minlength=n_poly) / safe_w
    res["conformal"] = np.where(wsum > 0, np.bincount(owner, weights=w * conf, minlength=n_poly) / safe_w, 1.0)
    res["l2"] = np.where(wsum > 0, np.sqrt(np.bincount(owner, weights=w * l2 * l2, minlength=n_poly) / safe_w), 1.0)
    res["tri_l2"] = l2
    res["tri_area"] = w
    res["tri_conformal"] = conf
    return res


def _coverage(uv: np.ndarray, tris: np.ndarray, grid: int) -> tuple[float, float]:
    total = grid * grid
    counts = np.zeros(total, dtype=np.int64)
    cover = np.zeros(total, dtype=bool)
    for cy, cx, _t, inside, strict in _tri_cells(uv, tris, grid):
        flat = cy * grid + cx
        cover[flat[inside]] = True
        counts += np.bincount(flat[strict], minlength=total)
    covered = float(cover.sum()) / total
    overlap = float((counts > 1).sum()) / total
    return covered, overlap


def uv_stats(mesh, uv: np.ndarray, corners: Corners | None = None, grid: int = 128) -> dict:
    mesh = finite_mesh(mesh)
    corners = corners or Corners(mesh)
    uv = np.asarray(uv, float)
    uv = np.where(np.isfinite(uv), uv, 0.0)
    islands = uv_islands(mesh, uv, corners)
    signed = polygon_area_uv(uv, corners)
    flipped = 0
    if islands:
        owner = np.zeros(corners.poly_count, dtype=np.int64)
        for i, isl in enumerate(islands):
            owner[isl] = i
        sums = np.bincount(owner, weights=signed, minlength=len(islands))
        sign = np.where(sums >= 0, 1.0, -1.0)[owner]
        flipped = int(np.sum(signed * sign < -1e-15))
    oob = 0
    if corners.count:
        bad = ((uv < -1e-9) | (uv > 1 + 1e-9)).any(axis=1)
        oob = int((np.bincount(corners.poly, weights=bad.astype(float), minlength=corners.poly_count) > 0).sum())
    stretch = polygon_stretch(mesh, uv, corners)
    w = stretch["tri_area"]
    wsum = float(w.sum()) if len(w) else 0.0
    if wsum > 0:
        mean_l2 = float(math.sqrt((w * stretch["tri_l2"] ** 2).sum() / wsum))
        max_l2 = float(stretch["tri_l2"][w > 0].max())
        mean_conf = float((w * stretch["tri_conformal"]).sum() / wsum)
        max_conf = float(stretch["tri_conformal"][w > 0].max())
    else:
        mean_l2 = max_l2 = mean_conf = max_conf = 1.0
    tris, _ = mesh_triangles(mesh, corners)
    covered, overlap = _coverage(uv, tris, int(grid)) if len(tris) else (0.0, 0.0)
    return {
        "polygons": corners.poly_count,
        "corners": corners.count,
        "uv_points": int(point_groups(corners, uv).max() + 1) if corners.count else 0,
        "islands": len(islands),
        "uv_area": float(np.abs(signed).sum()),
        "coverage": covered,
        "overlap": overlap,
        "out_of_bounds": oob,
        "flipped": flipped,
        "mean_stretch": mean_l2,
        "max_stretch": max_l2,
        "mean_conformal": mean_conf,
        "max_conformal": max_conf,
    }


def seams_count(obj) -> int:
    return len(get_seams(obj))


def remove_welded_seams(obj, welded: Iterable) -> None:
    seams = get_seams(obj)
    seams.difference_update(edge_key(*e) for e in welded)
    set_seams(obj, seams)
