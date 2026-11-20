import math as _math
import numpy as np
from quartz.math._base import _MathBase
from quartz.math.vector import Vector


class MatrixAccess:
    def __init__(self, matrix, col=False):
        self._m = matrix
        self._col = col

    def __getitem__(self, i):
        m = self._m
        if self._col:
            view = m._data[:, i]
        else:
            view = m._data[i, :]
        return Vector._q_wrap(view, owner=m, on_write=m._write)

    def __setitem__(self, i, value):
        m = self._m
        m._check_frozen()
        arr = np.asarray(value, dtype=np.float64).ravel()
        if self._col:
            m._data[:, i] = arr.astype(np.float32)
        else:
            m._data[i, :] = arr.astype(np.float32)
        m._write()


class Matrix(_MathBase):
    def __init__(self, rows=None):
        super().__init__()
        if rows is None:
            self._data = np.eye(4, dtype=np.float32)
            return
        arr = np.asarray(rows, dtype=np.float64)
        if arr.ndim == 1:
            pass
        if arr.ndim != 2:
            raise ValueError("invalid matrix")
        r, c = arr.shape
        if r < 2 or r > 4 or c < 2 or c > 4:
            raise ValueError("invalid matrix size")
        self._data = arr.astype(np.float32)

    @classmethod
    def Identity(cls, size):
        return cls(np.eye(size, dtype=np.float64))

    @classmethod
    def Rotation(cls, angle, size, axis=None):
        if size == 2:
            c = _math.cos(angle)
            s = _math.sin(angle)
            return cls([[c, -s], [s, c]])
        if isinstance(axis, str):
            ax = axis.upper()
            if ax == "X":
                v = np.array([1.0, 0.0, 0.0])
            elif ax == "Y":
                v = np.array([0.0, 1.0, 0.0])
            elif ax == "Z":
                v = np.array([0.0, 0.0, 1.0])
            else:
                raise ValueError("invalid axis")
        elif axis is None:
            v = np.array([0.0, 0.0, 1.0])
        else:
            v = np.asarray(axis, dtype=np.float64).ravel()
            n = np.linalg.norm(v)
            if n > 0:
                v = v / n
        c = _math.cos(angle)
        s = _math.sin(angle)
        K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + s * K + (1 - c) * (K @ K)
        if size == 3:
            return cls(R)
        M = np.eye(4)
        M[:3, :3] = R
        return cls(M)

    @classmethod
    def Translation(cls, vector):
        v = np.asarray(vector, dtype=np.float64).ravel()
        M = np.eye(4, dtype=np.float64)
        M[0, 3] = v[0] if v.size > 0 else 0.0
        M[1, 3] = v[1] if v.size > 1 else 0.0
        M[2, 3] = v[2] if v.size > 2 else 0.0
        return cls(M)

    @classmethod
    def Scale(cls, factor, size, axis=None):
        if size == 2:
            M = np.eye(2, dtype=np.float64) * 1.0
            if axis is None:
                M = np.eye(2, dtype=np.float64) * factor
            else:
                ax = np.asarray(axis, dtype=np.float64).ravel()
                n = np.linalg.norm(ax)
                if n > 0:
                    ax = ax / n
                M = np.eye(2) + (factor - 1.0) * np.outer(ax, ax)
            return cls(M)
        if size == 3:
            if axis is None:
                return cls(np.eye(3, dtype=np.float64) * factor)
            ax = np.asarray(axis, dtype=np.float64).ravel()
            n = np.linalg.norm(ax)
            if n > 0:
                ax = ax / n
            M = np.eye(3) + (factor - 1.0) * np.outer(ax, ax)
            return cls(M)
        if axis is None:
            M = np.eye(4, dtype=np.float64)
            M[0, 0] = factor
            M[1, 1] = factor
            M[2, 2] = factor
            return cls(M)
        ax = np.asarray(axis, dtype=np.float64).ravel()
        n = np.linalg.norm(ax)
        if n > 0:
            ax = ax / n
        M = np.eye(4, dtype=np.float64)
        M[:3, :3] = np.eye(3) + (factor - 1.0) * np.outer(ax, ax)
        return cls(M)

    @classmethod
    def Diagonal(cls, vector):
        v = np.asarray(vector, dtype=np.float64).ravel()
        n = v.shape[0]
        M = np.zeros((n, n), dtype=np.float64)
        np.fill_diagonal(M, v)
        return cls(M)

    @classmethod
    def OrthoProjection(cls, axis, size):
        if isinstance(axis, str):
            ax = axis.upper()
            if size == 2:
                if ax == "X":
                    M = np.array([[1.0, 0.0], [0.0, 0.0]])
                elif ax == "Y":
                    M = np.array([[0.0, 0.0], [0.0, 1.0]])
                else:
                    raise ValueError("invalid axis")
                return cls(M)
            if ax in ("XY", "XZ", "YZ"):
                if size not in (3, 4):
                    raise ValueError("Matrix.OrthoProjection(): plane projection requires size 3 or 4")
                M = np.eye(size, dtype=np.float64)
                if ax == "XY":
                    M[2, 2] = 0.0
                elif ax == "XZ":
                    M[1, 1] = 0.0
                else:
                    M[0, 0] = 0.0
                return cls(M)
            v = {"X": np.array([1., 0, 0]), "Y": np.array([0., 1, 0]), "Z": np.array([0., 0, 1])}[ax]
        else:
            v = np.asarray(axis, dtype=np.float64).ravel()
        n = np.linalg.norm(v)
        if n > 0:
            v = v / n
        M = np.eye(3, dtype=np.float64) - np.outer(v, v)
        if size == 4:
            M4 = np.eye(4, dtype=np.float64)
            M4[:3, :3] = M
            return cls(M4)
        return cls(M)

    @classmethod
    def Shear(cls, plane, size, factor):
        pl = plane.upper()
        if size == 2:
            M = np.eye(2, dtype=np.float64)
            if isinstance(factor, (list, tuple, np.ndarray)):
                f = float(factor[0])
            else:
                f = float(factor)
            if pl == "X":
                M[0, 1] = f
            elif pl == "Y":
                M[1, 0] = f
            return cls(M)
        M = np.eye(3, dtype=np.float64)
        if isinstance(factor, (list, tuple, np.ndarray)):
            f0 = float(factor[0])
            f1 = float(factor[1]) if len(factor) > 1 else f0
        else:
            f0 = float(factor)
            f1 = f0
        if pl == "XY":
            M[0, 2] = f0
            M[1, 2] = f1
        elif pl == "XZ":
            M[0, 1] = f0
            M[2, 1] = f1
        elif pl == "YZ":
            M[1, 0] = f0
            M[2, 0] = f1
        return cls(M)

    @classmethod
    def LocRotScale(cls, location, rotation, scale):
        M = np.eye(4, dtype=np.float64)
        if rotation is not None:
            from quartz.math.quaternion import Quaternion
            from quartz.math.euler import Euler
            if isinstance(rotation, Matrix):
                R = rotation._data.astype(np.float64)
                if R.shape == (3, 3):
                    M[:3, :3] = R
                elif R.shape == (4, 4):
                    M[:3, :3] = R[:3, :3]
            elif isinstance(rotation, Quaternion):
                M[:3, :3] = rotation.to_matrix()._data.astype(np.float64)
            elif isinstance(rotation, Euler):
                M[:3, :3] = rotation.to_matrix()._data.astype(np.float64) if hasattr(rotation, "to_matrix") else np.eye(3)
                if not hasattr(rotation, "to_matrix"):
                    pass
            else:
                try:
                    e = Euler(rotation)
                    M[:3, :3] = e.to_matrix()._data.astype(np.float64)
                except Exception:
                    pass
        if scale is not None:
            s = np.asarray(scale, dtype=np.float64).ravel()
            sx = s[0] if s.size > 0 else 1.0
            sy = s[1] if s.size > 1 else sx
            sz = s[2] if s.size > 2 else sx
            M[:3, :3] = M[:3, :3] * np.array([sx, sy, sz])[None, :]
        if location is not None:
            loc = np.asarray(location, dtype=np.float64).ravel()
            M[0, 3] = loc[0] if loc.size > 0 else 0.0
            M[1, 3] = loc[1] if loc.size > 1 else 0.0
            M[2, 3] = loc[2] if loc.size > 2 else 0.0
        return cls(M)

    @classmethod
    def _q_wrap(cls, view, *, owner=None, on_write=None, **extra):
        obj = super()._q_wrap(view, owner=owner, on_write=on_write, **extra)
        obj._data = np.asarray(view, dtype=np.float32)
        if obj._data.ndim != 2:
            obj._data = obj._data.reshape(-1, 1) if obj._data.ndim == 1 else obj._data
        return obj

    @property
    def row(self):
        return MatrixAccess(self, col=False)

    @property
    def col(self):
        return MatrixAccess(self, col=True)

    @property
    def translation(self):
        r, c = self._data.shape
        if r >= 3 and c >= 4:
            view = self._data[:3, 3]
        elif r >= 2 and c >= 3:
            view = self._data[:2, 2]
        else:
            view = self._data[:, -1]
        return Vector._q_wrap(view, owner=self, on_write=self._write)

    @translation.setter
    def translation(self, value):
        self._check_frozen()
        arr = np.asarray(value, dtype=np.float64).ravel()
        r, c = self._data.shape
        if r >= 3 and c >= 4:
            self._data[0, 3] = arr[0] if arr.size > 0 else 0.0
            self._data[1, 3] = arr[1] if arr.size > 1 else 0.0
            self._data[2, 3] = arr[2] if arr.size > 2 else 0.0
        elif r >= 2 and c >= 3:
            self._data[0, 2] = arr[0] if arr.size > 0 else 0.0
            self._data[1, 2] = arr[1] if arr.size > 1 else 0.0
        self._write()

    @property
    def median_scale(self):
        d = self._data.astype(np.float64)
        n = min(d.shape[0], d.shape[1], 3)
        block = d[:n, :n]
        return float(np.mean(np.linalg.norm(block, axis=0)))

    @property
    def is_identity(self):
        r, c = self._data.shape
        if r != c:
            return False
        return bool(np.allclose(self._data.astype(np.float64), np.eye(r)))

    @property
    def is_negative(self):
        try:
            return float(np.linalg.det(self._data.astype(np.float64))) < 0
        except Exception:
            return False

    @property
    def is_orthogonal(self):
        d = self._data.astype(np.float64)
        if d.shape[0] != d.shape[1]:
            return False
        prod = d @ d.T
        return bool(np.allclose(prod, np.eye(d.shape[0])))

    @property
    def is_orthogonal_axis_vectors(self):
        return self.is_orthogonal

    def copy(self):
        m = Matrix(self._data.copy().tolist())
        m.is_frozen = False
        m.is_wrapped = False
        m.owner = None
        m._on_write = None
        return m

    def freeze(self):
        if self.is_wrapped:
            raise TypeError("Cannot freeze wrapped data")
        self.is_frozen = True
        return self

    def determinant(self):
        d = self._data.astype(np.float64)
        if d.shape[0] != d.shape[1]:
            raise ValueError("non-square matrix")
        return float(np.linalg.det(d))

    def transpose(self):
        self._check_frozen()
        self._assign(self._data.astype(np.float64).T.copy())
        self._write()

    def transposed(self):
        c = self.copy()
        c.transpose()
        return c

    def _is_singular(self):
        d = self._data.astype(np.float64)
        if d.shape[0] != d.shape[1]:
            return True
        try:
            det = np.linalg.det(d)
        except Exception:
            return True
        return abs(det) < 1e-12

    def invert(self, fallback=None):
        self._check_frozen()
        if self._is_singular():
            if fallback is None:
                raise ValueError("Matrix.invert(ed): matrix does not have an inverse")
            src = fallback._data if isinstance(fallback, Matrix) else fallback
            self._assign(np.asarray(src, dtype=np.float64))
            self._write()
            return
        self._assign(np.linalg.inv(self._data.astype(np.float64)))
        self._write()

    def invert_safe(self):
        self._check_frozen()
        d = self._data.astype(np.float64)
        try:
            inv = np.linalg.pinv(d)
        except np.linalg.LinAlgError:
            inv = d
        self._assign(inv)
        self._write()

    def inverted_safe(self):
        c = self.copy()
        c.invert_safe()
        return c

    def adjugate(self):
        self._check_frozen()
        d = self._data.astype(np.float64)
        n = d.shape[0]
        if n != d.shape[1]:
            raise ValueError("non-square matrix")
        cof = np.zeros_like(d)
        for i in range(n):
            for j in range(n):
                minor = np.delete(np.delete(d, i, axis=0), j, axis=1)
                cof[i, j] = ((-1) ** (i + j)) * np.linalg.det(minor)
        self._assign(cof.T)
        self._write()

    def adjugated(self):
        c = self.copy()
        c.adjugate()
        return c

    def normalize(self):
        self._check_frozen()
        d = self._data.astype(np.float64)
        r, c = d.shape
        size = min(r, c, 3)
        for j in range(size):
            col = d[:size, j]
            n = np.linalg.norm(col)
            if n > 0:
                d[:size, j] = col / n
        self._assign(d)
        self._write()

    def normalized(self):
        c = self.copy()
        c.normalize()
        return c

    def zero(self):
        self._check_frozen()
        self._data[:] = 0.0
        self._write()

    def identity(self):
        self._check_frozen()
        r, c = self._data.shape
        self._data[:] = 0.0
        n = min(r, c)
        for i in range(n):
            self._data[i, i] = 1.0
        self._write()

    def to_2x2(self):
        return Matrix(self._data[:2, :2].copy().tolist())

    def to_3x3(self):
        r, c = self._data.shape
        out = np.eye(3, dtype=np.float64)
        rr = min(r, 3)
        cc = min(c, 3)
        out[:rr, :cc] = self._data[:rr, :cc].astype(np.float64)
        return Matrix(out.tolist())

    def to_4x4(self):
        r, c = self._data.shape
        out = np.eye(4, dtype=np.float64)
        rr = min(r, 4)
        cc = min(c, 4)
        out[:rr, :cc] = self._data[:rr, :cc].astype(np.float64)
        return Matrix(out.tolist())

    def resize_4x4(self):
        self._check_frozen()
        self._check_wrapped_resize()
        self._data = self.to_4x4()._data.copy()
        self._write()

    def to_euler(self, order="XYZ", euler_compat=None):
        from quartz.math.euler import Euler, _mat3_to_euler_angles
        d = self._data.astype(np.float64)
        if d.shape[0] < 3 or d.shape[1] < 3:
            raise ValueError("Matrix.to_euler(): inappropriate matrix size, expected 3x3 or 4x4")
        R = d[:3, :3].copy()
        norms = np.linalg.norm(R, axis=0)
        norms[norms == 0.0] = 1.0
        R = R / norms
        compat = None if euler_compat is None else euler_compat._data.astype(np.float64)
        return Euler(_mat3_to_euler_angles(R, order, compat), order)

    def to_quaternion(self):
        from quartz.math.quaternion import Quaternion
        d = self._data.astype(np.float64)
        if d.shape[0] >= 3 and d.shape[1] >= 3:
            R = d[:3, :3]
        else:
            R = np.eye(3)
        tr = R[0, 0] + R[1, 1] + R[2, 2]
        if tr > 0:
            s = _math.sqrt(tr + 1.0) * 2.0
            w = 0.25 * s
            x = (R[2, 1] - R[1, 2]) / s
            y = (R[0, 2] - R[2, 0]) / s
            z = (R[1, 0] - R[0, 1]) / s
        elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
            s = _math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
            w = (R[2, 1] - R[1, 2]) / s
            x = 0.25 * s
            y = (R[0, 1] + R[1, 0]) / s
            z = (R[0, 2] + R[2, 0]) / s
        elif R[1, 1] > R[2, 2]:
            s = _math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
            w = (R[0, 2] - R[2, 0]) / s
            x = (R[0, 1] + R[1, 0]) / s
            y = 0.25 * s
            z = (R[1, 2] + R[2, 1]) / s
        else:
            s = _math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
            w = (R[1, 0] - R[0, 1]) / s
            x = (R[0, 2] + R[2, 0]) / s
            y = (R[1, 2] + R[2, 1]) / s
            z = 0.25 * s
        return Quaternion((w, x, y, z))

    def to_scale(self):
        d = self._data.astype(np.float64)
        if d.shape[0] >= 3 and d.shape[1] >= 3:
            c0 = np.linalg.norm(d[:3, 0])
            c1 = np.linalg.norm(d[:3, 1])
            c2 = np.linalg.norm(d[:3, 2])
            return Vector([c0, c1, c2])
        return Vector([1.0, 1.0, 1.0])

    def to_translation(self):
        return self.translation.copy() if hasattr(self, "translation") else Vector([0.0, 0.0, 0.0])
        return self.translation.copy()

    def decompose(self):
        loc = self.to_translation()
        d = self._data.astype(np.float64)
        M = d[:3, :3].copy()
        sx = float(np.linalg.norm(M[:, 0]))
        sy = float(np.linalg.norm(M[:, 1]))
        sz = float(np.linalg.norm(M[:, 2]))
        sc = Vector([sx, sy, sz])
        R = M.copy()
        if sx > 0:
            R[:, 0] /= sx
        if sy > 0:
            R[:, 1] /= sy
        if sz > 0:
            R[:, 2] /= sz
        rot = Matrix(R.tolist()).to_quaternion()
        return (loc, rot, sc)

    def lerp(self, other, factor):
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64)
        d = self._data.astype(np.float64)
        r = (1.0 - factor) * d + factor * o
        return Matrix(r.astype(np.float32).tolist())

    def rotate(self, other):
        self._check_frozen()
        from quartz.math.quaternion import Quaternion
        from quartz.math.euler import Euler
        if isinstance(other, Matrix):
            R = other._data.astype(np.float64)
        elif isinstance(other, Quaternion):
            R = other.to_matrix()._data.astype(np.float64)
        elif isinstance(other, Euler):
            R = other.to_matrix()._data.astype(np.float64)
        else:
            R = np.asarray(other, dtype=np.float64)
        d = self._data.astype(np.float64)
        if R.shape[0] < 3 or R.shape[1] < 3 or d.shape[0] < 3 or d.shape[1] < 3:
            if R.shape == (2, 2) and d.shape == (2, 2):
                self._assign(R @ d)
                self._write()
                return
            raise ValueError("Matrix.rotate(): matrix sizes do not match")
        out = d.copy()
        out[:3, :3] = R[:3, :3] @ d[:3, :3]
        self._assign(out)
        self._write()

    def __len__(self):
        return int(self._data.shape[0])

    def __iter__(self):
        for row in self._data:
            yield Vector(row.tolist())

    def __getitem__(self, key):
        if isinstance(key, tuple):
            i, j = key
            if i < 0:
                i += self._data.shape[0]
            if j < 0:
                j += self._data.shape[1]
            return float(self._data[i, j])
        if isinstance(key, slice):
            rows = self._data[key]
            return [Vector(r.tolist()) for r in rows]
        i = key
        if i < 0:
            i += self._data.shape[0]
        if i < 0 or i >= self._data.shape[0]:
            raise IndexError("index out of range")
        return Vector._q_wrap(self._data[i, :], owner=self, on_write=self._write)

    def __setitem__(self, key, value):
        self._check_frozen()
        if isinstance(key, tuple):
            i, j = key
            if i < 0:
                i += self._data.shape[0]
            if j < 0:
                j += self._data.shape[1]
            self._data[i, j] = float(value)
            self._write()
            return
        if isinstance(key, slice):
            arr = np.asarray(value, dtype=np.float64)
            self._data[key] = arr.astype(np.float32)
        else:
            i = key
            if i < 0:
                i += self._data.shape[0]
            if i < 0 or i >= self._data.shape[0]:
                raise IndexError("index out of range")
            arr = np.asarray(value, dtype=np.float64).ravel()
            self._data[i, :] = arr.astype(np.float32)
        self._write()

    def __matmul__(self, other):
        from quartz.math.vector import Vector
        if isinstance(other, Matrix):
            a = self._data.astype(np.float64)
            b = other._data.astype(np.float64)
            if a.shape[1] != b.shape[0]:
                raise ValueError("dimension mismatch")
            r = a @ b
            return Matrix(r.tolist())
        if isinstance(other, Vector):
            a = self._data.astype(np.float64)
            v = other._data.astype(np.float64)
            if a.shape[1] != v.shape[0] and not (a.shape[1] == 4 and v.shape[0] == 3):
                raise ValueError("dimension mismatch")
            if a.shape[1] == 4 and v.shape[0] == 3:
                vv = np.append(v, 1.0)
                r = a @ vv
                return Vector(r[:3].astype(np.float32).tolist())
            r = a @ v
            if r.shape[0] == 4 and self._data.shape[0] == 4:
                pass
            return Vector(r.astype(np.float32).tolist())
        v = np.asarray(other, dtype=np.float64).ravel()
        a = self._data.astype(np.float64)
        if a.shape[1] == 4 and v.shape[0] == 3:
            vv = np.append(v, 1.0)
            r = a @ vv
            return Vector(r[:3].astype(np.float32).tolist())
        if a.shape[1] != v.shape[0]:
            raise ValueError("dimension mismatch")
        r = a @ v
        return Vector(r.astype(np.float32).tolist())

    def __mul__(self, other):
        if isinstance(other, (int, float, np.integer, np.floating)):
            r = self._data.astype(np.float64) * float(other)
            return Matrix(r.astype(np.float32).tolist())
        if isinstance(other, Matrix):
            a = self._data.astype(np.float64)
            b = other._data.astype(np.float64)
            if a.shape != b.shape:
                raise ValueError("shape mismatch")
            return Matrix((a * b).astype(np.float32).tolist())
        o = np.asarray(other, dtype=np.float64)
        r = self._data.astype(np.float64) * o
        return Matrix(r.astype(np.float32).tolist())

    def __rmul__(self, other):
        return self.__mul__(other)

    def __add__(self, other):
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64)
        r = self._data.astype(np.float64) + o
        return Matrix(r.astype(np.float32).tolist())

    def __sub__(self, other):
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64)
        r = self._data.astype(np.float64) - o
        return Matrix(r.astype(np.float32).tolist())

    def __neg__(self):
        r = -self._data.astype(np.float64)
        return Matrix(r.astype(np.float32).tolist())

    __eq__ = _MathBase.__eq__
    __ne__ = _MathBase.__ne__
    __hash__ = _MathBase.__hash__

    def __repr__(self):
        rows = []
        for row in self._data:
            rows.append("(" + ", ".join(repr(float(v)) for v in row) + ")")
        return "Matrix((" + ",\n        ".join(rows) + "))" if len(rows) > 1 else "Matrix((" + rows[0] + "))"


_UNSET = object()


def _matrix_inverted(self, fallback=_UNSET):
    c = self.copy()
    if self._is_singular():
        if fallback is _UNSET:
            raise ValueError("Matrix.invert(ed): matrix does not have an inverse")
        if isinstance(fallback, Matrix):
            return fallback.copy()
        return fallback
    inv = np.linalg.inv(self._data.astype(np.float64))
    return Matrix(inv.astype(np.float32).tolist())


Matrix.inverted = _matrix_inverted

def _to_translation(self):
    return self.translation.copy()

Matrix.to_translation = _to_translation

def _repr(self):
    rows = []
    for row in self._data:
        rows.append("(" + ", ".join(repr(float(v)) for v in row) + ")")
    if len(rows) == 1:
        return "Matrix((" + rows[0] + "))"
    return "Matrix((" + rows[0] + ",\n        " + ",\n        ".join(rows[1:]) + "))"

Matrix.__repr__ = _repr
