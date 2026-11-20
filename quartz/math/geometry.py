import math as _math
import numpy as np
from quartz.math.vector import Vector


def _to_arr(v):
    if hasattr(v, "_data"):
        return np.asarray(v._data, dtype=np.float64).ravel().copy()
    return np.asarray(v, dtype=np.float64).ravel().copy()


def _to_vec(arr):
    return Vector(arr.astype(np.float32).tolist())


def intersect_ray_tri(v1, v2, v3, ray, orig, clip=True):
    V1, V2, V3 = _to_arr(v1), _to_arr(v2), _to_arr(v3)
    ray = _to_arr(ray)
    orig = _to_arr(orig)
    e1 = V2 - V1
    e2 = V3 - V1
    h = np.cross(ray, e2)
    a = float(np.dot(e1, h))
    if abs(a) < 1e-12:
        return None
    f = 1.0 / a
    s = orig - V1
    u = f * float(np.dot(s, h))
    if clip and (u < 0.0 or u > 1.0):
        return None
    q = np.cross(s, e1)
    vv = f * float(np.dot(ray, q))
    if clip and (vv < 0.0 or u + vv > 1.0):
        return None
    t = f * float(np.dot(e2, q))
    if clip and t < 0.0:
        return None
    pt = orig + t * ray
    return _to_vec(pt)


def intersect_line_line(v1, v2, v3, v4):
    a = _to_arr(v1); b = _to_arr(v2); c = _to_arr(v3); d = _to_arr(v4)
    d1 = b - a
    d2 = d - c
    r = a - c
    denom = np.dot(d1, d1)*np.dot(d2, d2) - np.dot(d1, d2)**2
    if abs(denom) < 1e-12:
        return None
    t = (np.dot(d1, d2)*np.dot(r, d2) - np.dot(d2, d2)*np.dot(r, d1)) / denom
    u = (np.dot(d1, d1)*np.dot(r, d2) - np.dot(d1, d2)*np.dot(r, d1)) / denom
    p = a + t*d1
    q = c + u*d2
    return (_to_vec(p), _to_vec(q))


def intersect_line_plane(line_a, line_b, plane_co, plane_no, no_flip=False):
    a = _to_arr(line_a); b = _to_arr(line_b)
    co = _to_arr(plane_co); no = _to_arr(plane_no)
    d = b - a
    denom = float(np.dot(no, d))
    if abs(denom) < 1e-12:
        return None
    if no_flip and denom < 0:
        no = -no
        denom = -denom
    t = float(np.dot(no, co - a)) / denom
    return _to_vec(a + t*d)


def intersect_line_sphere(line_a, line_b, sphere_co, sphere_radius, clip=True):
    a = _to_arr(line_a); b = _to_arr(line_b)
    c = _to_arr(sphere_co)
    d = b - a
    m = a - c
    bb = float(np.dot(d, m))
    cc = float(np.dot(m, m) - sphere_radius*sphere_radius)
    disc = bb*bb - np.dot(d, d)*cc
    if disc < 0:
        return (None, None)
    sq = _math.sqrt(disc)
    denom = float(np.dot(d, d))
    if denom == 0:
        return (None, None)
    t1 = (-bb - sq) / denom
    t2 = (-bb + sq) / denom
    p1 = a + t1*d
    p2 = a + t2*d
    if clip:
        if t1 < 0 or t1 > 1:
            p1 = None
        if t2 < 0 or t2 > 1:
            p2 = None
    r1 = _to_vec(p1) if p1 is not None else None
    r2 = _to_vec(p2) if p2 is not None else None
    return (r1, r2)


def intersect_point_line(pt, line_p1, line_p2):
    p = _to_arr(pt); a = _to_arr(line_p1); b = _to_arr(line_p2)
    d = b - a
    denom = float(np.dot(d, d))
    if denom == 0:
        return (_to_vec(a), 0.0)
    t = float(np.dot(p - a, d)) / denom
    closest = a + t*d
    return (_to_vec(closest), float(t))


def intersect_point_tri(pt, tri_p1, tri_p2, tri_p3):
    p = _to_arr(pt)
    a = _to_arr(tri_p1); b = _to_arr(tri_p2); c = _to_arr(tri_p3)
    v0 = c - a
    v1 = b - a
    v2 = p - a
    d00 = float(np.dot(v0, v0))
    d01 = float(np.dot(v0, v1))
    d11 = float(np.dot(v1, v1))
    d20 = float(np.dot(v2, v0))
    d21 = float(np.dot(v2, v1))
    denom = d00*d11 - d01*d01
    if abs(denom) < 1e-12:
        return None
    v = (d11*d20 - d01*d21) / denom
    w = (d00*d21 - d01*d20) / denom
    u = 1.0 - v - w
    if u < -1e-9 or v < -1e-9 or w < -1e-9:
        return None
    n = np.cross(b - a, c - a)
    nn = float(np.dot(n, n))
    if nn > 0.0 and p.shape == n.shape:
        p = p - n * (float(np.dot(p - a, n)) / nn)
    return _to_vec(p)


def intersect_point_tri_2d(pt, tri_p1, tri_p2, tri_p3):
    p = _to_arr(pt)[:2]
    a = _to_arr(tri_p1)[:2]
    b = _to_arr(tri_p2)[:2]
    c = _to_arr(tri_p3)[:2]
    def sign(p1, p2, p3):
        return (p1[0]-p3[0])*(p2[1]-p3[1]) - (p2[0]-p3[0])*(p1[1]-p3[1])
    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    if not (has_neg and has_pos):
        return 1
    return 0


def closest_point_on_tri(pt, tri_p1, tri_p2, tri_p3):
    p = _to_arr(pt)
    a = _to_arr(tri_p1); b = _to_arr(tri_p2); c = _to_arr(tri_p3)
    return _to_vec(_closest_point_on_tri_arr(p, a, b, c))


def _closest_point_on_tri_arr(p, a, b, c):
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = float(np.dot(ab, ap))
    d2 = float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        return a.copy()
    bp = p - b
    d3 = float(np.dot(ab, bp))
    d4 = float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        return b.copy()
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        return a + (d1 / (d1 - d3)) * ab
    cp = p - c
    d5 = float(np.dot(ab, cp))
    d6 = float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        return c.copy()
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        return a + (d2 / (d2 - d6)) * ac
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        return b + ((d4 - d3) / ((d4 - d3) + (d5 - d6))) * (c - b)
    total = va + vb + vc
    if total == 0.0:
        cands = []
        for s0, s1 in ((a, b), (b, c), (c, a)):
            d = s1 - s0
            dd = float(np.dot(d, d))
            t = 0.0 if dd == 0.0 else min(1.0, max(0.0, float(np.dot(p - s0, d)) / dd))
            cands.append(s0 + t * d)
        return min(cands, key=lambda q: float(np.dot(q - p, q - p)))
    v = vb / total
    w = vc / total
    return a + ab * v + ac * w


def distance_point_to_plane(pt, plane_co, plane_no):
    p = _to_arr(pt); co = _to_arr(plane_co); no = _to_arr(plane_no)
    n = no / (np.linalg.norm(no) + 1e-12)
    return float(np.dot(p - co, n))


def normal(*vectors):
    if len(vectors) == 1 and not hasattr(vectors[0], "_data"):
        seq = vectors[0]
        try:
            pts = [np.asarray(v, dtype=np.float64) if not hasattr(v, "_data") else np.asarray(v._data, dtype=np.float64) for v in seq]
        except Exception:
            pts = [_to_arr(vectors[0])]
    else:
        pts = [_to_arr(v) for v in vectors]
    if len(pts) < 3:
        return Vector([0.0, 0.0, 1.0])
    n = np.zeros(3, dtype=np.float64)
    for i in range(len(pts)):
        cur = pts[i]
        nxt = pts[(i+1) % len(pts)]
        n[0] += (cur[1] - nxt[1]) * (cur[2] + nxt[2])
        n[1] += (cur[2] - nxt[2]) * (cur[0] + nxt[0])
        n[2] += (cur[0] - nxt[0]) * (cur[1] + nxt[1])
    nn = np.linalg.norm(n)
    if nn > 0:
        n = n / nn
    return _to_vec(n)


def area_tri(v1, v2, v3):
    a = _to_arr(v1); b = _to_arr(v2); c = _to_arr(v3)
    if a.size == 2:
        a3 = np.array([a[0], a[1], 0.0]); b3 = np.array([b[0], b[1], 0.0]); c3 = np.array([c[0], c[1], 0.0])
    else:
        a3, b3, c3 = a, b, c
    return float(np.linalg.norm(np.cross(b3 - a3, c3 - a3)) / 2.0)


def volume_tetrahedron(v1, v2, v3, v4):
    a = _to_arr(v1); b = _to_arr(v2); c = _to_arr(v3); d = _to_arr(v4)
    return float(np.dot(b - a, np.cross(c - a, d - a)) / 6.0)


def barycentric_transform(point, tri_a1, tri_a2, tri_a3, tri_b1, tri_b2, tri_b3):
    p = _to_arr(point)
    A = [_to_arr(tri_a1), _to_arr(tri_a2), _to_arr(tri_a3)]
    B = [_to_arr(tri_b1), _to_arr(tri_b2), _to_arr(tri_b3)]
    def bary(p, a, b, c):
        v0 = c - a; v1 = b - a; v2 = p - a
        d00 = float(np.dot(v0, v0)); d01 = float(np.dot(v0, v1)); d11 = float(np.dot(v1, v1))
        d20 = float(np.dot(v2, v0)); d21 = float(np.dot(v2, v1))
        denom = d00*d11 - d01*d01
        if abs(denom) < 1e-12:
            return (1.0, 0.0, 0.0)
        v = (d11*d20 - d01*d21) / denom
        w = (d00*d21 - d01*d20) / denom
        u = 1.0 - v - w
        return (u, v, w)
    u, v, w = bary(p, A[0], A[1], A[2])
    r = A[0]*0
    res = u*_to_arr(tri_b1) + v*_to_arr(tri_b2) + w*_to_arr(tri_b3)
    return _to_vec(res)


def _is_point_like(v):
    if hasattr(v, "_data"):
        return True
    try:
        arr = np.asarray(v, dtype=np.float64)
    except (TypeError, ValueError):
        return False
    return arr.ndim == 1 and arr.size in (2, 3, 4)


def _signed_area_2d(pts2, loop):
    s = 0.0
    n = len(loop)
    for k in range(n):
        x0, y0 = pts2[loop[k]]
        x1, y1 = pts2[loop[(k + 1) % n]]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def _point_in_loop_2d(pt, pts2, loop):
    x, y = pt
    inside = False
    n = len(loop)
    for k in range(n):
        x0, y0 = pts2[loop[k]]
        x1, y1 = pts2[loop[(k + 1) % n]]
        if (y0 > y) != (y1 > y):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xi > x:
                inside = not inside
    return inside


def _cross2(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _seg_cross_2d(p1, p2, q1, q2):
    d1 = _cross2(p1, p2, q1)
    d2 = _cross2(p1, p2, q2)
    d3 = _cross2(q1, q2, p1)
    d4 = _cross2(q1, q2, p2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0


def _bridge_hole(outer, hole, pts2, others=()):
    hi = max(range(len(hole)), key=lambda k: (pts2[hole[k]][0], -pts2[hole[k]][1]))
    hp = pts2[hole[hi]]
    n = len(outer)
    best = None
    for k in range(n):
        cand = pts2[outer[k]]
        d = (cand[0] - hp[0]) ** 2 + (cand[1] - hp[1]) ** 2
        visible = True
        for m in range(n):
            e0 = pts2[outer[m]]
            e1 = pts2[outer[(m + 1) % n]]
            if _seg_cross_2d(hp, cand, e0, e1):
                visible = False
                break
        if visible:
            for loop in (hole, *others):
                hn = len(loop)
                for m in range(hn):
                    e0 = pts2[loop[m]]
                    e1 = pts2[loop[(m + 1) % hn]]
                    if _seg_cross_2d(hp, cand, e0, e1):
                        visible = False
                        break
                if not visible:
                    break
        if visible:
            key = (0 if cand[0] >= hp[0] else 1, d)
            if best is None or key < best[0]:
                best = (key, k)
    k = best[1] if best is not None else 0
    rotated_hole = hole[hi:] + hole[:hi]
    return outer[:k + 1] + rotated_hole + [rotated_hole[0], outer[k]] + outer[k + 1:]


def _ear_clip(ring, pts2):
    idx = list(ring)
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10 * len(ring) + 10:
        guard += 1
        n = len(idx)
        found = False
        for k in range(n):
            i0, i1, i2 = idx[(k - 1) % n], idx[k], idx[(k + 1) % n]
            a, b, c = pts2[i0], pts2[i1], pts2[i2]
            if _cross2(a, b, c) <= 1e-12:
                continue
            ok = True
            for m in range(n):
                j = idx[m]
                if j in (i0, i1, i2):
                    continue
                p = pts2[j]
                if (p[0] == a[0] and p[1] == a[1]) or (p[0] == b[0] and p[1] == b[1]) or \
                        (p[0] == c[0] and p[1] == c[1]):
                    continue
                if _cross2(a, b, p) >= 0 and _cross2(b, c, p) >= 0 and _cross2(c, a, p) >= 0:
                    ok = False
                    break
            if ok:
                tris.append((i0, i1, i2))
                del idx[k]
                found = True
                break
        if not found:
            k = min(range(n), key=lambda q: abs(_cross2(pts2[idx[(q - 1) % n]], pts2[idx[q]], pts2[idx[(q + 1) % n]])))
            i0, i1, i2 = idx[(k - 1) % n], idx[k], idx[(k + 1) % n]
            if _cross2(pts2[i0], pts2[i1], pts2[i2]) > 0:
                tris.append((i0, i1, i2))
            del idx[k]
    if len(idx) == 3 and _cross2(pts2[idx[0]], pts2[idx[1]], pts2[idx[2]]) > 1e-12:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def tessellate_polygon(veclist_list):
    if len(veclist_list) and _is_point_like(veclist_list[0]):
        loops_in = [veclist_list]
    else:
        loops_in = [loop for loop in veclist_list]
    pts3 = []
    loops = []
    for loop in loops_in:
        idxs = []
        for p in loop:
            a = _to_arr(p)
            v = np.zeros(3, dtype=np.float64)
            v[:min(3, a.size)] = a[:3]
            idxs.append(len(pts3))
            pts3.append(v)
        if len(idxs) > 1 and np.array_equal(pts3[idxs[0]], pts3[idxs[-1]]):
            idxs.pop()
        if len(idxs) >= 3:
            loops.append(idxs)
    if not loops:
        return []
    P = np.array(pts3)
    nrm = np.zeros(3)
    for loop in loops:
        for k in range(len(loop)):
            c = P[loop[k]]
            d = P[loop[(k + 1) % len(loop)]]
            nrm += np.array([(c[1] - d[1]) * (c[2] + d[2]),
                             (c[2] - d[2]) * (c[0] + d[0]),
                             (c[0] - d[0]) * (c[1] + d[1])])
    nn = float(np.linalg.norm(nrm))
    if nn < 1e-30:
        nrm = np.array([0.0, 0.0, 1.0])
    else:
        nrm = nrm / nn
    ref = np.array([1.0, 0.0, 0.0]) if abs(nrm[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(ref, nrm)
    u /= np.linalg.norm(u)
    v = np.cross(nrm, u)
    pts2 = [(float(np.dot(p, u)), float(np.dot(p, v))) for p in P]
    areas = [abs(_signed_area_2d(pts2, lp)) for lp in loops]
    containers = []
    for a_i, lp in enumerate(loops):
        probe = pts2[lp[0]]
        cont = [b_i for b_i, other in enumerate(loops)
                if b_i != a_i and areas[b_i] > areas[a_i] and _point_in_loop_2d(probe, pts2, other)]
        containers.append(cont)
    depth = [len(c) for c in containers]
    outers = [i for i in range(len(loops)) if depth[i] % 2 == 0]
    holes = {i: [] for i in outers}
    for i in range(len(loops)):
        if depth[i] % 2 == 1:
            parents = [c for c in containers[i] if depth[c] == depth[i] - 1]
            if parents:
                holes[min(parents, key=lambda c: areas[c])].append(i)
    tris = []
    for oi in outers:
        ring = list(loops[oi])
        flipped = _signed_area_2d(pts2, ring) < 0
        if flipped:
            ring.reverse()
        hl = sorted(holes[oi], key=lambda h: -max(pts2[k][0] for k in loops[h]))
        for n_h, h in enumerate(hl):
            hole = list(loops[h])
            if _signed_area_2d(pts2, hole) > 0:
                hole.reverse()
            ring = _bridge_hole(ring, hole, pts2, [loops[r] for r in hl[n_h + 1:]])
        for t in _ear_clip(ring, pts2):
            tris.append((t[0], t[2], t[1]) if flipped else t)
    return tris


def interpolate_bezier(knot1, handle1, handle2, knot2, resolution):
    k1 = _to_arr(knot1); h1 = _to_arr(handle1); h2 = _to_arr(handle2); k2 = _to_arr(knot2)
    pts = []
    for i in range(resolution):
        t = i / (resolution - 1) if resolution > 1 else 0.0
        omt = 1 - t
        p = (omt**3)*k1 + 3*(omt**2)*t*h1 + 3*omt*(t**2)*h2 + (t**3)*k2
        pts.append(_to_vec(p))
    if resolution == 1:
        pts = [_to_vec(k1)]
    return pts


def convex_hull_2d(points):
    pts = [(_to_arr(p)[0], _to_arr(p)[1]) for p in points]
    pts_sorted = sorted(set(pts))
    if len(pts_sorted) <= 1:
        return list(range(len(pts_sorted)))
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lower = []
    for p in pts_sorted:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts_sorted):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    idxs = []
    for hp in hull:
        for i, p in enumerate(pts):
            if (p[0] == hp[0] and p[1] == hp[1]) and i not in idxs:
                idxs.append(i)
                break
    return idxs


def box_fit_2d(points):
    pts = [(_to_arr(p)[0], _to_arr(p)[1]) for p in points]
    if len(pts) < 2:
        return 0.0
    best_area = float("inf")
    best_angle = 0.0
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        dx = pts[j][0] - pts[i][0]
        dy = pts[j][1] - pts[i][1]
        ang = _math.atan2(dy, dx)
        cos = _math.cos(-ang); sin = _math.sin(-ang)
        xs = [p[0]*cos - p[1]*sin for p in pts]
        ys = [p[0]*sin + p[1]*cos for p in pts]
        area = (max(xs)-min(xs))*(max(ys)-min(ys))
        if area < best_area:
            best_area = area
            best_angle = ang
    return float(best_angle)


def box_pack_2d(boxes):
    order = sorted(range(len(boxes)), key=lambda i: -boxes[i][3])
    x = 0.0; y = 0.0; row_h = 0.0; max_w = 0.0
    for i in order:
        b = boxes[i]
        if x + b[2] > max_w and max_w > 0:
            y += row_h
            x = 0.0
            row_h = 0.0
        b[0] = x
        b[1] = y
        x += b[2]
        row_h = max(row_h, b[3])
        max_w = max(max_w, x)
    total_h = y + row_h
    return (float(max_w), float(total_h))


def delaunay_2d_cdt(*args, **kwargs):
    raise NotImplementedError("mathutils.geometry.delaunay_2d_cdt is not implemented in Quartz")
