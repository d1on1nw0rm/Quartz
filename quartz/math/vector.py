import math as _math
import numpy as np
from quartz.math._base import _MathBase


_AXIS = {"x": 0, "y": 1, "z": 2, "w": 3}


class Vector(_MathBase):
    def __init__(self, seq=(0.0, 0.0, 0.0)):
        super().__init__()
        if not isinstance(seq, (np.ndarray, list, tuple, _MathBase)):
            try:
                seq = list(seq)
            except TypeError:
                pass
        arr = np.asarray(seq, dtype=np.float64).ravel()
        if arr.size < 2:
            raise ValueError("Vector(): invalid size")
        self._data = arr.astype(np.float32)

    @classmethod
    def Fill(cls, size, fill=0.0):
        if size < 2:
            raise ValueError("Vector(): invalid size")
        return cls([fill] * size)

    @classmethod
    def Range(cls, start, stop=None, step=1):
        if stop is None:
            r = range(start)
        else:
            r = range(start, stop, step)
        return cls([float(v) for v in r])

    @classmethod
    def Linspace(cls, start, stop, size):
        return cls(np.linspace(start, stop, size).tolist())

    @classmethod
    def Repeat(cls, vector, size):
        v = np.asarray(vector, dtype=np.float64).ravel()
        if v.size == 0:
            raise ValueError("Vector(): invalid size")
        out = np.resize(v, size).astype(np.float64)
        if out.size < 2:
            raise ValueError("Vector(): invalid size")
        return cls(out.tolist())

    @classmethod
    def _q_wrap(cls, view, *, owner=None, on_write=None, **extra):
        obj = super()._q_wrap(view, owner=owner, on_write=on_write, **extra)
        obj._data = np.asarray(view, dtype=np.float32)
        return obj

    @property
    def size(self):
        return int(self._data.shape[0])

    def _idx(self, name):
        return _AXIS[name]

    @property
    def x(self):
        if self._data.shape[0] < 1:
            raise AttributeError
        return float(self._data[0])

    @x.setter
    def x(self, v):
        self._set_comp(0, v)

    @property
    def y(self):
        if self._data.shape[0] < 2:
            raise AttributeError
        return float(self._data[1])

    @y.setter
    def y(self, v):
        self._set_comp(1, v)

    @property
    def z(self):
        if self._data.shape[0] < 3:
            raise AttributeError
        return float(self._data[2])

    @z.setter
    def z(self, v):
        self._set_comp(2, v)

    @property
    def w(self):
        if self._data.shape[0] < 4:
            raise AttributeError
        return float(self._data[3])

    @w.setter
    def w(self, v):
        self._set_comp(3, v)

    def _set_comp(self, i, v):
        if i >= self._data.shape[0]:
            raise AttributeError
        self._check_frozen()
        self._data[i] = float(v)
        self._write()

    @property
    def length(self):
        return float(np.linalg.norm(self._data.astype(np.float64)))

    @length.setter
    def length(self, value):
        self._check_frozen()
        cur = self.length
        if cur == 0.0:
            return
        factor = float(value) / cur
        self._data[:] = (self._data.astype(np.float64) * factor).astype(np.float32)
        self._write()

    magnitude = property(lambda self: self.length, lambda self, v: setattr(self, "length", v))

    @property
    def length_squared(self):
        return float(np.dot(self._data.astype(np.float64), self._data.astype(np.float64)))

    def copy(self):
        v = Vector(self._data.tolist())
        v.is_frozen = False
        v.is_wrapped = False
        v.owner = None
        v._on_write = None
        return v

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if 2 <= len(name) <= 4 and all(c in _AXIS for c in name):
            idxs = [_AXIS[c] for c in name]
            if all(i < self._data.shape[0] for i in idxs):
                vals = [float(self._data[i]) for i in idxs]
                return Vector(vals)
        raise AttributeError(f"Vector has no attribute {name}")

    def __setattr__(self, name, value):
        if name.startswith("_") or name in ("is_wrapped", "is_frozen", "owner", "_on_write", "_data"):
            super().__setattr__(name, value)
            return
        if name in _AXIS:
            i = _AXIS[name]
            if i < self._data.shape[0]:
                self._set_comp(i, value)
                return
            raise AttributeError(f"Vector has no attribute {name}")
        if 2 <= len(name) <= 4 and all(c in _AXIS for c in name):
            idxs = [_AXIS[c] for c in name]
            if len(set(name)) != len(name):
                raise AttributeError(f"Vector swizzle '{name}' has repeated components and is read-only")
            if not all(i < self._data.shape[0] for i in idxs):
                raise AttributeError(f"Vector swizzle '{name}' exceeds the vector size")
            self._check_frozen()
            seq = [float(v) for v in value]
            if len(seq) != len(name):
                raise ValueError("swizzle length mismatch")
            for i, val in zip(idxs, seq):
                self._data[i] = val
            self._write()
            return
        super().__setattr__(name, value)

    def to_tuple(self, precision=-1):
        if precision is not None and precision >= 0:
            return tuple(round(float(v), precision) for v in self._data)
        return tuple(float(v) for v in self._data)

    def to_2d(self):
        if self._data.shape[0] >= 2:
            return Vector([float(self._data[0]), float(self._data[1])])
        return Vector([float(self._data[0]), 0.0])

    def to_3d(self):
        vals = [float(self._data[0])]
        if self._data.shape[0] >= 2:
            vals.append(float(self._data[1]))
        else:
            vals.append(0.0)
        if self._data.shape[0] >= 3:
            vals.append(float(self._data[2]))
        else:
            vals.append(0.0)
        return Vector(vals)

    def to_4d(self):
        vals = [float(self._data[0])]
        for i in range(1, 3):
            vals.append(float(self._data[i]) if i < self._data.shape[0] else 0.0)
        if self._data.shape[0] >= 4:
            vals.append(float(self._data[3]))
        else:
            vals.append(1.0)
        return Vector(vals)

    def resize(self, size):
        self._check_frozen()
        self._check_wrapped_resize()
        if size < 2:
            raise ValueError("Vector(): invalid size")
        old = self._data.copy()
        new = np.zeros(size, dtype=np.float32)
        n = min(size, old.shape[0])
        new[:n] = old[:n]
        self._data = new
        self._write()

    def resized(self, size):
        c = self.copy()
        c.resize(size)
        return c

    def resize_2d(self):
        self.resize(2)

    def resize_3d(self):
        self.resize(3)

    def resize_4d(self):
        grow = self._data.shape[0] < 4
        self.resize(4)
        if grow:
            self._data[3] = 1.0

    def normalize(self):
        self._check_frozen()
        n = self.length
        if n == 0.0:
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

    def zero(self):
        self._check_frozen()
        self._data[:] = 0.0
        self._write()

    def dot(self, other):
        o = np.asarray(other, dtype=np.float64).ravel()
        return float(np.dot(self._data.astype(np.float64), o))

    def cross(self, other):
        o = np.asarray(other, dtype=np.float64).ravel()
        if self._data.shape[0] == 3 and o.shape[0] == 3:
            r = np.cross(self._data.astype(np.float64), o)
            return Vector(r.tolist())
        if self._data.shape[0] == 2 and o.shape[0] == 2:
            return float(self._data[0] * o[1] - self._data[1] * o[0])
        raise ValueError("cross requires 2D or 3D vectors")

    def angle(self, other, fallback=None):
        o = np.asarray(other, dtype=np.float64).ravel()
        a = self._data.astype(np.float64)
        na = np.linalg.norm(a)
        no = np.linalg.norm(o)
        if na == 0.0 or no == 0.0:
            if fallback is not None:
                return fallback
            raise ValueError("zero vector")
        cos = float(np.dot(a, o) / (na * no))
        cos = max(-1.0, min(1.0, cos))
        return float(_math.acos(cos))

    def angle_signed(self, other, fallback=None):
        if self._data.shape[0] != 2:
            raise ValueError("angle_signed requires 2D")
        o = np.asarray(other, dtype=np.float64).ravel()
        a = self._data.astype(np.float64)
        na = np.linalg.norm(a)
        no = np.linalg.norm(o)
        if na == 0.0 or no == 0.0:
            if fallback is not None:
                return fallback
            raise ValueError("zero vector")
        cross = float(a[0] * o[1] - a[1] * o[0])
        dot = float(np.dot(a, o))
        return float(_math.atan2(cross, dot))

    def lerp(self, other, factor):
        o = np.asarray(other, dtype=np.float64).ravel()
        a = self._data.astype(np.float64)
        r = (1.0 - factor) * a + factor * o
        return Vector(r.astype(np.float32).tolist())

    def slerp(self, other, factor, fallback=None):
        o = np.asarray(other, dtype=np.float64).ravel()
        a = self._data.astype(np.float64)
        na = np.linalg.norm(a)
        no = np.linalg.norm(o)
        if na == 0.0 or no == 0.0:
            if fallback is not None:
                return fallback
            return self.copy()
        a_n = a / na
        o_n = o / no
        dot = float(np.dot(a_n, o_n))
        if dot < 0.0:
            o_n = -o_n
            dot = -dot
        if dot > 0.9995:
            r = a_n + factor * (o_n - a_n)
            r = r / np.linalg.norm(r) * ((1 - factor) * na + factor * no)
            return Vector(r.astype(np.float32).tolist())
        theta = _math.acos(max(-1.0, min(1.0, dot)))
        sin_theta = _math.sin(theta)
        w1 = _math.sin((1.0 - factor) * theta) / sin_theta
        w2 = _math.sin(factor * theta) / sin_theta
        r = (w1 * a_n + w2 * o_n) * ((1 - factor) * na + factor * no)
        return Vector(r.astype(np.float32).tolist())

    def project(self, other):
        o = np.asarray(other, dtype=np.float64).ravel()
        denom = float(np.dot(o, o))
        if denom == 0.0:
            return Vector([0.0] * self._data.shape[0])
        factor = float(np.dot(self._data.astype(np.float64), o)) / denom
        r = o * factor
        out = np.zeros(self._data.shape[0], dtype=np.float64)
        n = min(out.shape[0], r.shape[0])
        out[:n] = r[:n]
        return Vector(out.astype(np.float32).tolist())

    def reflect(self, mirror):
        m = np.asarray(mirror, dtype=np.float64).ravel()
        mn = np.linalg.norm(m)
        if mn == 0.0:
            return self.copy()
        n = m / mn
        a = self._data.astype(np.float64)
        r = a - 2.0 * float(np.dot(a, n)) * n
        return Vector(r.astype(np.float32).tolist())

    def orthogonal(self):
        if self._data.shape[0] != 3:
            raise ValueError("orthogonal requires 3D")
        a = self._data.astype(np.float64)
        up = np.array([0.0, 0.0, 1.0])
        if abs(np.dot(a, up)) > 0.999:
            up = np.array([0.0, 1.0, 0.0])
        r = np.cross(a, up)
        rn = np.linalg.norm(r)
        if rn == 0.0:
            r = np.array([1.0, 0.0, 0.0])
        else:
            r = r / rn
        return Vector(r.astype(np.float32).tolist())

    def rotate(self, other):
        from quartz.math.euler import Euler
        from quartz.math.matrix import Matrix
        from quartz.math.quaternion import Quaternion
        self._check_frozen()
        a = self._data.astype(np.float64)
        if isinstance(other, Matrix):
            m = other._data.astype(np.float64)
            if a.shape[0] == 2 and m.shape == (2, 2):
                r = m @ a
            elif a.shape[0] == 3 and m.shape[0] >= 3 and m.shape[1] >= 3:
                r = m[:3, :3] @ a
            else:
                raise ValueError("Vector.rotate(): matrix size does not match the vector")
        elif isinstance(other, (Quaternion, Euler)):
            if a.shape[0] != 3:
                raise ValueError("Vector.rotate(): only 3D vectors can be rotated by Euler/Quaternion")
            q = other if isinstance(other, Quaternion) else other.to_quaternion()
            r = q.normalized().to_matrix()._data.astype(np.float64) @ a
        else:
            raise TypeError("Vector.rotate(): expected Euler, Quaternion or Matrix")
        self._data[:] = r.astype(np.float32)
        self._write()

    def rotation_difference(self, other):
        from quartz.math.quaternion import Quaternion
        o = np.asarray(other, dtype=np.float64).ravel()
        a = self._data.astype(np.float64)
        na = np.linalg.norm(a)
        no = np.linalg.norm(o)
        if na == 0 or no == 0:
            return Quaternion()
        a_n = a / na
        o_n = o / no
        cross = np.cross(a_n, o_n)
        dot = float(np.dot(a_n, o_n))
        w = 1.0 + dot
        if w < 1e-12:
            perp = np.array([1.0, 0.0, 0.0])
            if abs(a_n[0]) > 0.9:
                perp = np.array([0.0, 1.0, 0.0])
            cross = np.cross(a_n, perp)
            cn = np.linalg.norm(cross)
            if cn > 0:
                cross = cross / cn
            return Quaternion((0.0, cross[0], cross[1], cross[2]))
        q = Quaternion((w, cross[0], cross[1], cross[2]))
        q.normalize()
        return q

    def to_track_quat(self, track="Z", up="Y"):
        from quartz.math.quaternion import Quaternion
        if track not in ("X", "Y", "Z", "-X", "-Y", "-Z"):
            raise ValueError("Vector.to_track_quat(): invalid track axis, expected X, Y, Z, -X, -Y or -Z")
        if up not in ("X", "Y", "Z"):
            raise ValueError("Vector.to_track_quat(): invalid up axis, expected X, Y or Z")
        if track.lstrip("-") == up:
            raise ValueError("Vector.to_track_quat(): can't have the same axis for track and up")
        a = self._data.astype(np.float64)
        nrm = np.linalg.norm(a)
        if nrm == 0.0:
            return Quaternion()
        f = a / nrm
        if abs(f[2]) > 0.9999:
            g = np.array([0.0, 1.0, 0.0])
        else:
            g = np.array([0.0, 0.0, 1.0])
        right = np.cross(g, f)
        rn = np.linalg.norm(right)
        if rn < 1e-12:
            right = np.array([1.0, 0.0, 0.0])
        else:
            right = right / rn
        up_g = np.cross(f, right)
        un = np.linalg.norm(up_g)
        if un > 0:
            up_g = up_g / un

        def axis_sign(s):
            s = s.upper()
            sign = -1 if s.startswith("-") else 1
            letter = s.lstrip("-")
            idx = {"X": 0, "Y": 1, "Z": 2}[letter]
            return idx, sign

        ti, tsign = axis_sign(track)
        ui, usign = axis_sign(up)
        remaining = [i for i in range(3) if i not in (ti, ui)][0]

        def cross_sign(a, b):
            if (a + 1) % 3 == b:
                return 1
            return -1

        cs = cross_sign(ui, ti)
        third_sign = usign * tsign * cs

        M = np.zeros((3, 3), dtype=np.float64)
        M[:, ti] = f * tsign
        M[:, ui] = up_g * usign
        M[:, remaining] = right * third_sign

        tr = M[0, 0] + M[1, 1] + M[2, 2]
        if tr > 0:
            s = _math.sqrt(tr + 1.0) * 2.0
            w = 0.25 * s
            x = (M[2, 1] - M[1, 2]) / s
            y = (M[0, 2] - M[2, 0]) / s
            z = (M[1, 0] - M[0, 1]) / s
        elif M[0, 0] > M[1, 1] and M[0, 0] > M[2, 2]:
            s = _math.sqrt(1.0 + M[0, 0] - M[1, 1] - M[2, 2]) * 2.0
            w = (M[2, 1] - M[1, 2]) / s
            x = 0.25 * s
            y = (M[0, 1] + M[1, 0]) / s
            z = (M[0, 2] + M[2, 0]) / s
        elif M[1, 1] > M[2, 2]:
            s = _math.sqrt(1.0 + M[1, 1] - M[0, 0] - M[2, 2]) * 2.0
            w = (M[0, 2] - M[2, 0]) / s
            x = (M[0, 1] + M[1, 0]) / s
            y = 0.25 * s
            z = (M[1, 2] + M[2, 1]) / s
        else:
            s = _math.sqrt(1.0 + M[2, 2] - M[0, 0] - M[1, 1]) * 2.0
            w = (M[1, 0] - M[0, 1]) / s
            x = (M[0, 2] + M[2, 0]) / s
            y = (M[1, 2] + M[2, 1]) / s
            z = 0.25 * s
        return Quaternion((w, x, y, z))

    def __len__(self):
        return int(self._data.shape[0])

    def __iter__(self):
        for v in self._data:
            yield float(v)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return tuple(float(v) for v in self._data[key])
        i = key
        if i < 0:
            i += self._data.shape[0]
        if i < 0 or i >= self._data.shape[0]:
            raise IndexError("index out of range")
        return float(self._data[i])

    def __setitem__(self, key, value):
        self._check_frozen()
        if isinstance(key, slice):
            vals = np.asarray(value, dtype=np.float64).ravel()
            self._data[key] = vals.astype(np.float32)
        else:
            i = key
            if i < 0:
                i += self._data.shape[0]
            if i < 0 or i >= self._data.shape[0]:
                raise IndexError("index out of range")
            self._data[i] = float(value)
        self._write()

    def __add__(self, other):
        o = np.asarray(other, dtype=np.float64).ravel()
        if o.shape[0] != self._data.shape[0]:
            raise ValueError("size mismatch")
        r = self._data.astype(np.float64) + o
        return Vector(r.astype(np.float32).tolist())

    def __sub__(self, other):
        o = np.asarray(other, dtype=np.float64).ravel()
        if o.shape[0] != self._data.shape[0]:
            raise ValueError("size mismatch")
        r = self._data.astype(np.float64) - o
        return Vector(r.astype(np.float32).tolist())

    def __mul__(self, other):
        if isinstance(other, (int, float, np.integer, np.floating)):
            r = self._data.astype(np.float64) * float(other)
            return Vector(r.astype(np.float32).tolist())
        o = np.asarray(other, dtype=np.float64).ravel()
        if o.shape[0] != self._data.shape[0]:
            raise ValueError("size mismatch")
        r = self._data.astype(np.float64) * o
        return Vector(r.astype(np.float32).tolist())

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, (int, float, np.integer, np.floating)):
            if float(other) == 0.0:
                raise ZeroDivisionError("division by zero")
            r = self._data.astype(np.float64) / float(other)
            return Vector(r.astype(np.float32).tolist())
        raise TypeError("unsupported operand")

    def __matmul__(self, other):
        from quartz.math.matrix import Matrix
        if isinstance(other, Matrix):
            m = other._data.astype(np.float64)
            a = self._data.astype(np.float64)
            if m.shape[0] == 4 and a.shape[0] == 3:
                a4 = np.append(a, 1.0)
                r = a4 @ m
                return Vector(r[:3].astype(np.float32).tolist())
            if m.shape[0] != a.shape[0]:
                raise ValueError("dimension mismatch")
            r = a @ m
            if r.shape[0] == 4 and self._data.shape[0] == 3:
                r = r[:3]
            return Vector(r.astype(np.float32).tolist())
        o = np.asarray(other, dtype=np.float64).ravel()
        if o.shape[0] != self._data.shape[0]:
            raise ValueError("size mismatch")
        return float(np.dot(self._data.astype(np.float64), o))

    def __neg__(self):
        r = -self._data.astype(np.float64)
        return Vector(r.astype(np.float32).tolist())

    def __pos__(self):
        return self.copy()

    def __iadd__(self, other):
        o = np.asarray(other, dtype=np.float64).ravel()
        if o.shape[0] != self._data.shape[0]:
            raise ValueError("size mismatch")
        self._check_frozen()
        self._data[:] = (self._data.astype(np.float64) + o).astype(np.float32)
        self._write()
        return self

    def __isub__(self, other):
        o = np.asarray(other, dtype=np.float64).ravel()
        if o.shape[0] != self._data.shape[0]:
            raise ValueError("size mismatch")
        self._check_frozen()
        self._data[:] = (self._data.astype(np.float64) - o).astype(np.float32)
        self._write()
        return self

    def __imul__(self, other):
        self._check_frozen()
        if isinstance(other, (int, float, np.integer, np.floating)):
            self._data[:] = (self._data.astype(np.float64) * float(other)).astype(np.float32)
        else:
            o = np.asarray(other, dtype=np.float64).ravel()
            if o.shape[0] != self._data.shape[0]:
                raise ValueError("size mismatch")
            self._data[:] = (self._data.astype(np.float64) * o).astype(np.float32)
        self._write()
        return self

    def __itruediv__(self, other):
        self._check_frozen()
        if isinstance(other, (int, float, np.integer, np.floating)):
            if float(other) == 0.0:
                raise ZeroDivisionError("division by zero")
            self._data[:] = (self._data.astype(np.float64) / float(other)).astype(np.float32)
        else:
            raise TypeError("unsupported operand")
        self._write()
        return self

    @staticmethod
    def _other_length(other):
        if isinstance(other, Vector):
            return other.length
        return float(np.linalg.norm(np.asarray(other, dtype=np.float64).ravel()))

    def __lt__(self, other):
        try:
            return self.length < self._other_length(other)
        except (TypeError, ValueError):
            return NotImplemented

    def __le__(self, other):
        try:
            return self.length <= self._other_length(other)
        except (TypeError, ValueError):
            return NotImplemented

    def __gt__(self, other):
        try:
            return self.length > self._other_length(other)
        except (TypeError, ValueError):
            return NotImplemented

    def __ge__(self, other):
        try:
            return self.length >= self._other_length(other)
        except (TypeError, ValueError):
            return NotImplemented

    def __repr__(self):
        vals = ", ".join(repr(float(v)) for v in self._data)
        return f"Vector(({vals}))"

    def __str__(self):
        vals = ", ".join(f"{float(v):.4f}" for v in self._data)
        return f"<Vector ({vals})>"
