import math as _math
import numpy as np
from quartz.math._base import _MathBase
from quartz.math.matrix import Matrix

EULER_ORDERS = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")


def _rotmat(axis, angle):
    c = _math.cos(angle)
    s = _math.sin(angle)
    if axis == "X":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)
    if axis == "Y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def _compat_angles(angles, compat):
    out = []
    for a, c in zip(angles, compat):
        k = round((a - c) / (2.0 * _math.pi))
        out.append(a - k * 2.0 * _math.pi)
    return out


def _mat3_to_euler_angles(R, order, compat=None):
    if order not in EULER_ORDERS:
        raise ValueError("invalid order")
    R = np.asarray(R, dtype=np.float64)
    i, j, k = (_AXIS_INDEX[c] for c in order)
    par = 1.0 if (j - i) % 3 == 1 else -1.0
    sb = -par * R[k, i]
    cb = _math.hypot(R[i, i], R[j, i])
    if cb > 1e-6:
        a1 = _math.atan2(par * R[k, j], R[k, k])
        b1 = _math.atan2(sb, cb)
        g1 = _math.atan2(par * R[j, i], R[i, i])
        a2 = _math.atan2(-par * R[k, j], -R[k, k])
        b2 = _math.atan2(sb, -cb)
        g2 = _math.atan2(-par * R[j, i], -R[i, i])
        cands = [(a1, b1, g1), (a2, b2, g2)]
    else:
        a1 = _math.atan2(-par * R[j, k], R[j, j])
        b1 = _math.atan2(sb, cb)
        cands = [(a1, b1, 0.0)]
    results = []
    for a, b, g in cands:
        ang = [0.0, 0.0, 0.0]
        ang[i], ang[j], ang[k] = a, b, g
        results.append(ang)
    if compat is not None:
        compat = [float(c) for c in compat]
        results = [_compat_angles(r, compat) for r in results]
        return min(results, key=lambda r: sum(abs(x - c) for x, c in zip(r, compat)))
    return min(results, key=lambda r: sum(abs(x) for x in r))


class Euler(_MathBase):
    def __init__(self, angles=(0.0, 0.0, 0.0), order="XYZ"):
        super().__init__()
        if order not in EULER_ORDERS:
            raise ValueError("invalid order")
        arr = np.asarray(angles, dtype=np.float64).ravel()
        if arr.size < 3:
            arr = np.pad(arr, (0, 3 - arr.size))
        self._order = order
        self._data = arr[:3].astype(np.float32)

    @property
    def order(self):
        return self._order

    @order.setter
    def order(self, v):
        if v not in EULER_ORDERS:
            raise ValueError("invalid order")
        self._order = v

    @property
    def x(self):
        return float(self._data[0])

    @x.setter
    def x(self, v):
        self._check_frozen()
        self._data[0] = float(v)
        self._write()

    @property
    def y(self):
        return float(self._data[1])

    @y.setter
    def y(self, v):
        self._check_frozen()
        self._data[1] = float(v)
        self._write()

    @property
    def z(self):
        return float(self._data[2])

    @z.setter
    def z(self, v):
        self._check_frozen()
        self._data[2] = float(v)
        self._write()

    def copy(self):
        e = Euler(self._data.tolist(), self._order)
        e.is_frozen = False
        e.is_wrapped = False
        e.owner = None
        e._on_write = None
        return e

    @classmethod
    def _q_wrap(cls, view, *, owner=None, on_write=None, order="XYZ", **extra):
        obj = super()._q_wrap(view, owner=owner, on_write=on_write, **extra)
        obj._data = np.asarray(view, dtype=np.float32).ravel()[:3]
        if obj._data.size < 3:
            obj._data = np.pad(obj._data, (0, 3 - obj._data.size))
        obj._order = order
        return obj

    def to_matrix(self):
        R = np.eye(3, dtype=np.float64)
        for c in self._order:
            R = _rotmat(c, float(getattr(self, c.lower()))) @ R
        return Matrix(R.tolist())

    def to_quaternion(self):
        return self.to_matrix().to_quaternion()

    def rotate(self, other):
        self._check_frozen()
        from quartz.math.quaternion import Quaternion
        from quartz.math.matrix import Matrix
        if isinstance(other, Matrix):
            R = other._data.astype(np.float64)
        elif isinstance(other, Quaternion):
            R = other.to_matrix()._data.astype(np.float64)
        elif isinstance(other, Euler):
            R = other.to_matrix()._data.astype(np.float64)
        else:
            R = np.asarray(other, dtype=np.float64)
        if R.ndim != 2 or R.shape[0] < 3 or R.shape[1] < 3:
            raise ValueError("Euler.rotate(): expected a 3x3 or 4x4 rotation")
        R = R[:3, :3]
        M = self.to_matrix()._data.astype(np.float64)
        newM = R @ M
        angles = _mat3_to_euler_angles(newM, self._order, self._data.astype(np.float64))
        self._data[:] = np.array(angles, dtype=np.float32)
        self._write()

    def rotate_axis(self, axis, angle):
        self._check_frozen()
        ax = axis.upper()
        if ax not in _AXIS_INDEX:
            raise ValueError("Euler.rotate_axis(): expected axis 'X', 'Y' or 'Z'")
        R = _rotmat(ax, angle)
        M = self.to_matrix()._data.astype(np.float64)
        newM = M @ R
        angles = _mat3_to_euler_angles(newM, self._order, self._data.astype(np.float64))
        self._data[:] = np.array(angles, dtype=np.float32)
        self._write()

    def make_compatible(self, other):
        self._check_frozen()
        o = other._data.astype(np.float64)
        for i in range(3):
            diff = self._data[i] - o[i]
            while diff > _math.pi:
                self._data[i] -= 2 * _math.pi
                diff = self._data[i] - o[i]
            while diff < -_math.pi:
                self._data[i] += 2 * _math.pi
                diff = self._data[i] - o[i]
        self._write()

    def zero(self):
        self._check_frozen()
        self._data[:] = 0.0
        self._write()

    def __len__(self):
        return 3

    def __getitem__(self, i):
        if isinstance(i, slice):
            return tuple(float(v) for v in self._data[i])
        idx = i
        if idx < 0:
            idx += 3
        if idx < 0 or idx >= 3:
            raise IndexError("index out of range")
        return float(self._data[idx])

    def __setitem__(self, i, v):
        self._check_frozen()
        idx = i
        if idx < 0:
            idx += 3
        if idx < 0 or idx >= 3:
            raise IndexError("index out of range")
        self._data[idx] = float(v)
        self._write()

    def __eq__(self, other):
        if type(other) is not type(self):
            return False
        return self._order == other._order and bool(np.all(self._data == other._data))

    __ne__ = _MathBase.__ne__
    __hash__ = _MathBase.__hash__

    def __repr__(self):
        vals = ", ".join(repr(float(v)) for v in self._data)
        return f"Euler(({vals}), '{self._order}')"
