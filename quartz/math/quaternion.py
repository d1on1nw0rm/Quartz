import math as _math
import numpy as np
from quartz.math._base import _MathBase
from quartz.math.vector import Vector
from quartz.math.matrix import Matrix



class Quaternion(_MathBase):
    def __init__(self, seq=(1.0, 0.0, 0.0, 0.0), angle=None):
        super().__init__()
        if angle is not None:
            axis = np.asarray(seq, dtype=np.float64).ravel()
            n = np.linalg.norm(axis)
            if n == 0:
                axis = np.array([0.0, 0.0, 1.0])
            else:
                axis = axis / n
            half = angle / 2.0
            w = _math.cos(half)
            xyz = axis * _math.sin(half)
            data = np.array([w, xyz[0], xyz[1], xyz[2]], dtype=np.float64)
        else:
            arr = np.asarray(seq, dtype=np.float64).ravel()
            if arr.size == 3:
                ang = np.linalg.norm(arr)
                if ang == 0:
                    data = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
                else:
                    half = ang / 2.0
                    s = _math.sin(half) / ang
                    data = np.array([_math.cos(half), arr[0]*s, arr[1]*s, arr[2]*s], dtype=np.float64)
            elif arr.size == 4:
                data = arr[:4].astype(np.float64)
            else:
                data = np.zeros(4, dtype=np.float64)
                data[:min(4, arr.size)] = arr[:min(4, arr.size)]
                if data[0] == 0 and np.all(data[1:] == 0):
                    data[0] = 1.0
        self._data = data.astype(np.float32)

    @classmethod
    def _q_wrap(cls, view, *, owner=None, on_write=None, **extra):
        obj = super()._q_wrap(view, owner=owner, on_write=on_write, **extra)
        obj._data = np.asarray(view, dtype=np.float32).ravel()[:4]
        if obj._data.size < 4:
            obj._data = np.pad(obj._data, (0, 4 - obj._data.size))
        return obj

    @property
    def w(self):
        return float(self._data[0])

    @w.setter
    def w(self, v):
        self._check_frozen()
        self._data[0] = float(v)
        self._write()

    @property
    def x(self):
        return float(self._data[1])

    @x.setter
    def x(self, v):
        self._check_frozen()
        self._data[1] = float(v)
        self._write()

    @property
    def y(self):
        return float(self._data[2])

    @y.setter
    def y(self, v):
        self._check_frozen()
        self._data[2] = float(v)
        self._write()

    @property
    def z(self):
        return float(self._data[3])

    @z.setter
    def z(self, v):
        self._check_frozen()
        self._data[3] = float(v)
        self._write()

    @property
    def angle(self):
        xyz = self._data[1:].astype(np.float64)
        n = np.linalg.norm(xyz)
        w = float(self._data[0])
        if n == 0:
            return 0.0
        return float(2.0 * _math.atan2(n, w))

    @angle.setter
    def angle(self, value):
        self._check_frozen()
        xyz = self._data[1:].astype(np.float64)
        n = np.linalg.norm(xyz)
        if n == 0:
            xyz = np.array([1.0, 0.0, 0.0])
            n = 1.0
        half = value / 2.0
        self._data[0] = _math.cos(half)
        s = _math.sin(half)
        self._data[1:] = (xyz / n * s).astype(np.float32)
        self._write()

    @property
    def axis(self):
        xyz = self._data[1:].astype(np.float64)
        n = np.linalg.norm(xyz)
        if n == 0:
            return Vector([1.0, 0.0, 0.0])
        return Vector((xyz / n).tolist())

    @axis.setter
    def axis(self, value):
        self._check_frozen()
        v = np.asarray(value, dtype=np.float64).ravel()
        n = np.linalg.norm(v)
        if n == 0:
            v = np.array([1.0, 0.0, 0.0])
            n = 1.0
        v = v / n
        ang = self.angle
        half = ang / 2.0
        self._data[0] = _math.cos(half)
        self._data[1:] = (v * _math.sin(half)).astype(np.float32)
        self._write()

    @property
    def magnitude(self):
        return float(np.linalg.norm(self._data.astype(np.float64)))

    def copy(self):
        q = Quaternion(self._data.tolist())
        q.is_frozen = False
        q.is_wrapped = False
        q.owner = None
        q._on_write = None
        return q

    def conjugate(self):
        self._check_frozen()
        self._data[1:] = -self._data[1:]
        self._write()

    def conjugated(self):
        c = self.copy()
        c.conjugate()
        return c

    def invert(self):
        self._check_frozen()
        n2 = float(np.dot(self._data.astype(np.float64), self._data.astype(np.float64)))
        if n2 == 0:
            return
        self._data[:] = (np.array([self._data[0], -self._data[1], -self._data[2], -self._data[3]]) / n2).astype(np.float32)
        self._write()

    def inverted(self):
        c = self.copy()
        c.invert()
        return c

    def normalize(self):
        self._check_frozen()
        n = self.magnitude
        if n == 0:
            return
        self._data[:] = (self._data.astype(np.float64) / n).astype(np.float32)
        self._write()

    def normalized(self):
        c = self.copy()
        c.normalize()
        return c

    def negate(self):
        self._check_frozen()
        self._data[:] = (-self._data.astype(np.float64)).astype(np.float32)
        self._write()

    def identity(self):
        self._check_frozen()
        self._data[:] = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        self._write()

    def dot(self, other):
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64)
        return float(np.dot(self._data.astype(np.float64), o))

    def cross(self, other):
        if not isinstance(other, Quaternion):
            other = Quaternion(np.asarray(other, dtype=np.float64).ravel().tolist())
        return self @ other

    def __matmul__(self, other):
        from quartz.math.vector import Vector
        if isinstance(other, Quaternion):
            a = self._data.astype(np.float64)
            b = other._data.astype(np.float64)
            w = a[0]*b[0] - a[1]*b[1] - a[2]*b[2] - a[3]*b[3]
            x = a[0]*b[1] + a[1]*b[0] + a[2]*b[3] - a[3]*b[2]
            y = a[0]*b[2] - a[1]*b[3] + a[2]*b[0] + a[3]*b[1]
            z = a[0]*b[3] + a[1]*b[2] - a[2]*b[1] + a[3]*b[0]
            return Quaternion((w, x, y, z))
        if isinstance(other, Vector):
            v = other._data.astype(np.float64)
            if v.shape[0] != 3:
                raise ValueError("requires 3D vector")
            qv = np.array([0.0, v[0], v[1], v[2]])
            res = self @ Quaternion(qv.tolist())
            conj = Quaternion((self._data[0], -self._data[1], -self._data[2], -self._data[3]))
            res2 = res @ conj
            return Vector([res2.x, res2.y, res2.z])
        arr = np.asarray(other, dtype=np.float64).ravel()
        if arr.size == 3:
            return self @ Vector(arr.tolist())
        raise TypeError("unsupported operand")

    def __mul__(self, other):
        if isinstance(other, (int, float, np.integer, np.floating)):
            r = self._data.astype(np.float64) * float(other)
            return Quaternion(r.tolist())
        o = np.asarray(other._data if isinstance(other, _MathBase) else other, dtype=np.float64).ravel()
        if o.shape != (4,):
            return NotImplemented
        r = self._data.astype(np.float64) * o
        return Quaternion(r.tolist())

    def __rmul__(self, other):
        return self.__mul__(other)

    def __add__(self, other):
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64)
        r = self._data.astype(np.float64) + o
        return Quaternion(r.tolist())

    def __sub__(self, other):
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64)
        r = self._data.astype(np.float64) - o
        return Quaternion(r.tolist())

    def __neg__(self):
        r = -self._data.astype(np.float64)
        return Quaternion(r.tolist())

    def rotation_difference(self, other):
        o = other if isinstance(other, Quaternion) else Quaternion(np.asarray(other, dtype=np.float64).tolist() if False else (list(other) + [0.0])[:4])
        if not isinstance(other, Quaternion):
            arr = np.asarray(other, dtype=np.float64).ravel()
            if arr.size == 3:
                other = Quaternion(arr.tolist())
            else:
                other = Quaternion(arr.tolist())
        return other @ self.inverted()

    def slerp(self, other, factor):
        if not isinstance(other, Quaternion):
            other = Quaternion(np.asarray(other, dtype=np.float64).tolist())
        a = self._data.astype(np.float64)
        b = other._data.astype(np.float64)
        dot = float(np.dot(a, b))
        if dot < 0.0:
            b = -b
            dot = -dot
        if dot > 0.9995:
            r = a + factor * (b - a)
            r = r / np.linalg.norm(r)
            return Quaternion(r.tolist())
        theta = _math.acos(max(-1.0, min(1.0, dot)))
        sin_theta = _math.sin(theta)
        w1 = _math.sin((1.0 - factor) * theta) / sin_theta
        w2 = _math.sin(factor * theta) / sin_theta
        r = w1 * a + w2 * b
        r = r / np.linalg.norm(r)
        return Quaternion(r.tolist())

    def rotate(self, other):
        self._check_frozen()
        from quartz.math.euler import Euler
        from quartz.math.matrix import Matrix
        if isinstance(other, Quaternion):
            q = other
        elif isinstance(other, Euler):
            q = other.to_quaternion()
        elif isinstance(other, Matrix):
            q = other.to_quaternion()
        else:
            q = Quaternion(np.asarray(other, dtype=np.float64).tolist())
        length = self.magnitude
        base = self.normalized() if length > 0.0 else Quaternion()
        r = (q.normalized() @ base)._data.astype(np.float64) * (length if length > 0.0 else 1.0)
        self._data[:] = r.astype(np.float32)
        self._write()

    def make_compatible(self, other):
        self._check_frozen()
        if self.dot(other) < 0:
            self._data[:] = (-self._data.astype(np.float64)).astype(np.float32)
            self._write()

    def to_matrix(self):
        q = self._data.astype(np.float64)
        w, x, y, z = q
        R = np.array([
            [1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)],
            [2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)],
            [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)],
        ], dtype=np.float64)
        return Matrix(R.tolist())

    def to_euler(self, order="XYZ", euler_compat=None):
        from quartz.math.euler import Euler, _mat3_to_euler_angles
        q = self._data.astype(np.float64)
        n = float(np.linalg.norm(q))
        q = q / n if n > 0.0 else np.array([1.0, 0.0, 0.0, 0.0])
        R = Quaternion(q.tolist()).to_matrix()._data.astype(np.float64)
        compat = None if euler_compat is None else euler_compat._data.astype(np.float64)
        return Euler(_mat3_to_euler_angles(R, order, compat), order)

    def to_axis_angle(self):
        xyz = self._data[1:].astype(np.float64)
        n = np.linalg.norm(xyz)
        w = float(self._data[0])
        if n == 0:
            return (Vector([1.0, 0.0, 0.0]), 0.0)
        ang = 2.0 * _math.atan2(n, w)
        axis = xyz / n
        return (Vector(axis.tolist()), float(ang))

    def to_exponential_map(self):
        xyz = self._data[1:].astype(np.float64)
        n = np.linalg.norm(xyz)
        w = float(self._data[0])
        if n == 0:
            return Vector([0.0, 0.0, 0.0])
        ang = 2.0 * _math.atan2(n, w)
        axis = xyz / n
        return Vector((axis * ang).tolist())

    def to_swing_twist(self, axis):
        ax = axis.upper() if isinstance(axis, str) else None
        if ax is not None:
            if ax == "X":
                a = np.array([1.0, 0.0, 0.0])
            elif ax == "Y":
                a = np.array([0.0, 1.0, 0.0])
            else:
                a = np.array([0.0, 0.0, 1.0])
        else:
            a = np.asarray(axis, dtype=np.float64).ravel()
            n = np.linalg.norm(a)
            if n > 0:
                a = a / n
        q = self._data.astype(np.float64)
        dot = float(np.dot(q[1:], a))
        twist = Quaternion((q[0], a[0]*dot, a[1]*dot, a[2]*dot))
        twist.normalize()
        swing = (Quaternion(q.tolist()) @ twist.inverted())
        swing = Quaternion(q.tolist()) @ twist.inverted()
        twist_angle = twist.angle
        return (swing, float(twist_angle))

    def __len__(self):
        return 4

    def __getitem__(self, i):
        if isinstance(i, slice):
            return tuple(float(v) for v in self._data[i])
        idx = i
        if idx < 0:
            idx += 4
        if idx < 0 or idx >= 4:
            raise IndexError("index out of range")
        return float(self._data[idx])

    def __setitem__(self, i, v):
        self._check_frozen()
        idx = i
        if idx < 0:
            idx += 4
        if idx < 0 or idx >= 4:
            raise IndexError("index out of range")
        self._data[idx] = float(v)
        self._write()

    def __repr__(self):
        vals = ", ".join(repr(float(v)) for v in self._data)
        return f"Quaternion(({vals}))"

    def __str__(self):
        return self.__repr__()
