import math as _math
import numpy as np


def _as_point(v):
    arr = np.asarray(v._data if hasattr(v, "_data") else v, dtype=np.float64).ravel()
    out = np.zeros(3, dtype=np.float64)
    out[:min(3, arr.size)] = arr[:3]
    return out


def _triangle_weights(a, b, c, p):
    v0 = b - a
    v1 = c - a
    v2 = p - a
    d00 = float(np.dot(v0, v0))
    d01 = float(np.dot(v0, v1))
    d11 = float(np.dot(v1, v1))
    d20 = float(np.dot(v2, v0))
    d21 = float(np.dot(v2, v1))
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-30:
        return None
    wb = (d11 * d20 - d01 * d21) / denom
    wc = (d00 * d21 - d01 * d20) / denom
    return [1.0 - wb - wc, wb, wc]


def _mean_value_weights(pts, p):
    n = len(pts)
    nrm = np.zeros(3)
    for i in range(n):
        c = pts[i]
        d = pts[(i + 1) % n]
        nrm += np.array([(c[1] - d[1]) * (c[2] + d[2]),
                         (c[2] - d[2]) * (c[0] + d[0]),
                         (c[0] - d[0]) * (c[1] + d[1])])
    nn = float(np.linalg.norm(nrm))
    if nn < 1e-30:
        return [1.0 / n] * n
    nrm /= nn
    ref = np.array([1.0, 0.0, 0.0]) if abs(nrm[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(ref, nrm)
    u /= np.linalg.norm(u)
    v = np.cross(nrm, u)
    q = np.array([[np.dot(x - p, u), np.dot(x - p, v)] for x in pts])
    r = np.linalg.norm(q, axis=1)
    eps = 1e-12 * max(1.0, float(r.max()))
    for i in range(n):
        if r[i] <= eps:
            w = [0.0] * n
            w[i] = 1.0
            return w
    for i in range(n):
        j = (i + 1) % n
        cross = q[i][0] * q[j][1] - q[i][1] * q[j][0]
        dot = float(np.dot(q[i], q[j]))
        if abs(cross) <= eps * (r[i] + r[j]) and dot < 0.0:
            w = [0.0] * n
            w[i] = float(r[j] / (r[i] + r[j]))
            w[j] = float(r[i] / (r[i] + r[j]))
            return w
    tans = []
    for i in range(n):
        j = (i + 1) % n
        cross = q[i][0] * q[j][1] - q[i][1] * q[j][0]
        dot = float(np.dot(q[i], q[j]))
        alpha = _math.atan2(cross, dot)
        tans.append(_math.tan(alpha / 2.0))
    w = [(tans[i - 1] + tans[i]) / r[i] for i in range(n)]
    s = sum(w)
    if s == 0.0 or not _math.isfinite(s):
        return [1.0 / n] * n
    return [float(x / s) for x in w]


def poly_3d_calc(veclist, pt):
    pts = [_as_point(v) for v in veclist]
    p = _as_point(pt)
    n = len(pts)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    if n == 2:
        d = pts[1] - pts[0]
        dd = float(np.dot(d, d))
        t = 0.0 if dd == 0.0 else min(1.0, max(0.0, float(np.dot(p - pts[0], d)) / dd))
        return [1.0 - t, t]
    if n == 3:
        w = _triangle_weights(pts[0], pts[1], pts[2], p)
        if w is not None:
            return [float(x) for x in w]
        return [1.0 / 3.0] * 3
    return _mean_value_weights(pts, p)
