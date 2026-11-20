import math as _math
import sys
import numpy as np
from quartz.math.vector import Vector

_object_adapter = None
_bmesh_adapter = None


def set_object_adapter(fn):
    global _object_adapter
    _object_adapter = fn


def set_bmesh_adapter(fn):
    global _bmesh_adapter
    _bmesh_adapter = fn


class BVHTree:
    def __init__(self):
        self._positions = None
        self._tris = None
        self._tri_polygon = None
        self._epsilon = 0.0

    @classmethod
    def FromPolygons(cls, vertices, polygons, all_triangles=False, epsilon=0.0):
        verts = np.asarray(vertices, dtype=np.float64)
        if verts.ndim == 1:
            verts = verts.reshape(-1, 3)
        tris = []
        tri_polygon = []
        for poly_index, poly in enumerate(polygons):
            p = [int(i) for i in poly]
            for i in range(1, len(p) - 1):
                tris.append((p[0], p[i], p[i + 1]))
                tri_polygon.append(poly_index)
        obj = cls()
        obj._positions = verts
        obj._tris = np.array(tris, dtype=np.int64) if tris else np.zeros((0, 3), dtype=np.int64)
        obj._tri_polygon = np.array(tri_polygon, dtype=np.int64)
        obj._epsilon = float(epsilon)
        return obj

    @classmethod
    def FromBMesh(cls, bmesh, epsilon=0.0):
        if _bmesh_adapter is None:
            raise NotImplementedError("BVHTree.FromObject is not available (adapter not installed)")
        return _bmesh_adapter(bmesh, epsilon=epsilon)

    @classmethod
    def FromObject(cls, object, depsgraph, *, deform=True, render=False, cage=False, epsilon=0.0):
        if _object_adapter is None:
            raise NotImplementedError("BVHTree.FromObject is not available (adapter not installed)")
        return _object_adapter(object, depsgraph, deform=deform, render=render, cage=cage, epsilon=epsilon)

    @classmethod
    def _q_from_triangles(cls, positions, tris, tri_polygon, epsilon=0.0):
        obj = cls()
        obj._positions = np.asarray(positions, dtype=np.float64)
        obj._tris = np.asarray(tris, dtype=np.int64)
        obj._tri_polygon = np.asarray(tri_polygon, dtype=np.int64)
        obj._epsilon = float(epsilon)
        return obj

    def _tri_points(self, i):
        tri = self._tris[i]
        return self._positions[tri[0]], self._positions[tri[1]], self._positions[tri[2]]

    def ray_cast(self, origin, direction, distance=sys.float_info.max):
        origin = _to_arr(origin) if False else np.asarray(origin._data if hasattr(origin, "_data") else origin, dtype=np.float64).ravel()
        direction = np.asarray(direction._data if hasattr(direction, "_data") else direction, dtype=np.float64).ravel()
        dn = np.linalg.norm(direction)
        if dn > 0:
            direction = direction / dn
        best_t = distance
        best_i = None
        best_point = None
        best_normal = None
        for i in range(len(self._tris)):
            p0, p1, p2 = self._tri_points(i)
            e1 = p1 - p0
            e2 = p2 - p0
            h = np.cross(direction, e2)
            a = float(np.dot(e1, h))
            if abs(a) < 1e-12:
                continue
            f = 1.0 / a
            s = origin - p0
            u = f * float(np.dot(s, h))
            if u < 0.0 or u > 1.0:
                continue
            q = np.cross(s, e1)
            v = f * float(np.dot(direction, q))
            if v < 0.0 or u + v > 1.0:
                continue
            t = f * float(np.dot(e2, q))
            if t < 0.0 or t > best_t:
                continue
            best_t = t
            best_i = int(self._tri_polygon[i]) if self._tri_polygon is not None else i
            best_point = origin + t * direction
            best_normal = np.cross(e1, e2)
            nn = np.linalg.norm(best_normal)
            if nn > 0:
                best_normal = best_normal / nn
        if best_i is None:
            return (None, None, None, None)
        return (Vector(best_point.astype(np.float32).tolist()),
                Vector(best_normal.astype(np.float32).tolist()),
                best_i,
                float(best_t))

    def find_nearest(self, origin, distance=sys.float_info.max):
        origin = np.asarray(origin._data if hasattr(origin, "_data") else origin, dtype=np.float64).ravel()
        best_d = distance
        best_i = None
        best_point = None
        best_normal = None
        for i in range(len(self._tris)):
            p0, p1, p2 = self._tri_points(i)
            cp = _closest_point_triangle(origin, p0, p1, p2)
            d = float(np.linalg.norm(cp - origin))
            if d < best_d:
                best_d = d
                best_i = int(self._tri_polygon[i]) if self._tri_polygon is not None else i
                best_point = cp
                best_normal = np.cross(p1 - p0, p2 - p0)
                nn = np.linalg.norm(best_normal)
                if nn > 0:
                    best_normal = best_normal / nn
        if best_i is None:
            return (None, None, None, None)
        return (Vector(best_point.astype(np.float32).tolist()),
                Vector(best_normal.astype(np.float32).tolist()),
                best_i,
                float(best_d))

    def find_nearest_range(self, origin, distance=sys.float_info.max):
        origin = np.asarray(origin._data if hasattr(origin, "_data") else origin, dtype=np.float64).ravel()
        best = {}
        for i in range(len(self._tris)):
            p0, p1, p2 = self._tri_points(i)
            cp = _closest_point_triangle(origin, p0, p1, p2)
            d = float(np.linalg.norm(cp - origin))
            if d <= distance:
                idx = int(self._tri_polygon[i]) if self._tri_polygon is not None else i
                if idx not in best or d < best[idx][3]:
                    normal = np.cross(p1 - p0, p2 - p0)
                    nn = np.linalg.norm(normal)
                    if nn > 0:
                        normal = normal / nn
                    best[idx] = (Vector(cp.astype(np.float32).tolist()),
                                 Vector(normal.astype(np.float32).tolist()),
                                 idx,
                                 d)
        return sorted(best.values(), key=lambda r: (r[3], r[2]))

    def overlap(self, other_tree):
        res = []
        seen = set()
        eps = max(self._epsilon, other_tree._epsilon)
        for i in range(len(self._tris)):
            a = np.array(self._tri_points(i))
            a_min = a.min(axis=0) - eps
            a_max = a.max(axis=0) + eps
            for j in range(len(other_tree._tris)):
                b = np.array(other_tree._tri_points(j))
                if np.any(a_min > b.max(axis=0) + 1e-9) or np.any(b.min(axis=0) > a_max + 1e-9):
                    continue
                if not _tri_tri_intersect(a, b, eps):
                    continue
                ii = int(self._tri_polygon[i]) if self._tri_polygon is not None else i
                jj = int(other_tree._tri_polygon[j]) if other_tree._tri_polygon is not None else j
                if (ii, jj) not in seen:
                    seen.add((ii, jj))
                    res.append((ii, jj))
        return res


def _segment_tri_intersect(p, q, tri, eps):
    a, b, c = tri
    d = q - p
    e1 = b - a
    e2 = c - a
    h = np.cross(d, e2)
    det = float(np.dot(e1, h))
    scale = max(float(np.linalg.norm(d) * np.linalg.norm(e1) * np.linalg.norm(e2)), 1e-300)
    if abs(det) <= 1e-12 * scale:
        return False
    f = 1.0 / det
    s = p - a
    u = f * float(np.dot(s, h))
    tol = 1e-9 + eps
    if u < -tol or u > 1.0 + tol:
        return False
    qv = np.cross(s, e1)
    v = f * float(np.dot(d, qv))
    if v < -tol or u + v > 1.0 + tol:
        return False
    t = f * float(np.dot(e2, qv))
    return -tol <= t <= 1.0 + tol


def _orient2d(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect_2d(p1, p2, q1, q2, tol):
    def on_seg(a, b, c):
        return (min(a[0], b[0]) - tol <= c[0] <= max(a[0], b[0]) + tol
                and min(a[1], b[1]) - tol <= c[1] <= max(a[1], b[1]) + tol)

    o1 = _orient2d(p1, p2, q1)
    o2 = _orient2d(p1, p2, q2)
    o3 = _orient2d(q1, q2, p1)
    o4 = _orient2d(q1, q2, p2)
    proper_a = (o1 > tol and o2 < -tol) or (o1 < -tol and o2 > tol)
    proper_b = (o3 > tol and o4 < -tol) or (o3 < -tol and o4 > tol)
    if proper_a and proper_b:
        return True
    return ((abs(o1) <= tol and on_seg(p1, p2, q1)) or (abs(o2) <= tol and on_seg(p1, p2, q2))
            or (abs(o3) <= tol and on_seg(q1, q2, p1)) or (abs(o4) <= tol and on_seg(q1, q2, p2)))


def _point_in_tri_2d(p, a, b, c, tol):
    d1 = _orient2d(a, b, p)
    d2 = _orient2d(b, c, p)
    d3 = _orient2d(c, a, p)
    has_neg = d1 < -tol or d2 < -tol or d3 < -tol
    has_pos = d1 > tol or d2 > tol or d3 > tol
    return not (has_neg and has_pos)


def _tri_tri_intersect(a, b, eps=0.0):
    na = np.cross(a[1] - a[0], a[2] - a[0])
    nb = np.cross(b[1] - b[0], b[2] - b[0])
    lna = float(np.linalg.norm(na))
    lnb = float(np.linalg.norm(nb))
    if lna == 0.0 or lnb == 0.0:
        return False
    da = (b - a[0]) @ (na / lna)
    db = (a - b[0]) @ (nb / lnb)
    size = max(float(np.ptp(np.vstack([a, b]), axis=0).max()), 1e-12)
    tol = 1e-9 * size + eps
    if np.all(da > tol) or np.all(da < -tol) or np.all(db > tol) or np.all(db < -tol):
        return False
    if np.all(np.abs(da) <= tol):
        axis = int(np.argmax(np.abs(na)))
        keep = [k for k in range(3) if k != axis]
        a2 = a[:, keep]
        b2 = b[:, keep]
        tol2 = tol * size
        for m in range(3):
            for n in range(3):
                if _segments_intersect_2d(a2[m], a2[(m + 1) % 3], b2[n], b2[(n + 1) % 3], tol2):
                    return True
        return (_point_in_tri_2d(a2[0], b2[0], b2[1], b2[2], tol2)
                or _point_in_tri_2d(b2[0], a2[0], a2[1], a2[2], tol2))
    for m in range(3):
        if _segment_tri_intersect(a[m], a[(m + 1) % 3], b, eps):
            return True
        if _segment_tri_intersect(b[m], b[(m + 1) % 3], a, eps):
            return True
    return False


def _closest_point_triangle(p, a, b, c):
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = np.dot(ab, ap)
    d2 = np.dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a.copy()
    bp = p - b
    d3 = np.dot(ab, bp)
    d4 = np.dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b.copy()
    cp = p - c
    d5 = np.dot(ab, cp)
    d6 = np.dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c.copy()
    vc = d1*d4 - d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return a + v * ab
    vb = d5*d2 - d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return a + w * ac
    va = d3*d6 - d5*d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return b + w * (c - b)
    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    return a + ab * v + ac * w


def _to_arr(v):
    if hasattr(v, "_data"):
        return np.asarray(v._data, dtype=np.float64).ravel()
    return np.asarray(v, dtype=np.float64).ravel()
