import math as _math
import numpy as np
from quartz.math._base import _MathBase


def _rgb_to_hsv(r, g, b):
    mx = max(r, g, b)
    mn = min(r, g, b)
    df = mx - mn
    if mx == mn:
        h = 0.0
    elif mx == r:
        h = (60 * ((g - b) / df) + 360) % 360
    elif mx == g:
        h = (60 * ((b - r) / df) + 120) % 360
    else:
        h = (60 * ((r - g) / df) + 240) % 360
    if mx == 0:
        s = 0.0
    else:
        s = df / mx
    v = mx
    return (h / 360.0, s, v)


def _hsv_to_rgb(h, s, v):
    if s == 0:
        return (v, v, v)
    h = h * 6.0
    i = int(h)
    f = h - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    i = i % 6
    if i == 0:
        return (v, t, p)
    if i == 1:
        return (q, v, p)
    if i == 2:
        return (p, v, t)
    if i == 3:
        return (p, q, v)
    if i == 4:
        return (t, p, v)
    return (v, p, q)


class Color(_MathBase):
    def __init__(self, rgb=(0.0, 0.0, 0.0)):
        super().__init__()
        arr = np.asarray(rgb, dtype=np.float64).ravel()
        if arr.size != 3:
            raise ValueError("Color requires 3 components")
        self._data = arr.astype(np.float32)

    @property
    def r(self):
        return float(self._data[0])

    @r.setter
    def r(self, v):
        self._check_frozen()
        self._data[0] = float(v)
        self._write()

    @property
    def g(self):
        return float(self._data[1])

    @g.setter
    def g(self, v):
        self._check_frozen()
        self._data[1] = float(v)
        self._write()

    @property
    def b(self):
        return float(self._data[2])

    @b.setter
    def b(self, v):
        self._check_frozen()
        self._data[2] = float(v)
        self._write()

    @property
    def h(self):
        h, s, v = _rgb_to_hsv(self.r, self.g, self.b)
        return h

    @h.setter
    def h(self, value):
        self._check_frozen()
        hh, s, v = _rgb_to_hsv(self.r, self.g, self.b)
        r, g, b = _hsv_to_rgb(value, s, v)
        self._data[:] = np.array([r, g, b], dtype=np.float32)
        self._write()

    @property
    def s(self):
        h, s, v = _rgb_to_hsv(self.r, self.g, self.b)
        return s

    @s.setter
    def s(self, value):
        self._check_frozen()
        h, ss, v = _rgb_to_hsv(self.r, self.g, self.b)
        r, g, b = _hsv_to_rgb(h, value, v)
        self._data[:] = np.array([r, g, b], dtype=np.float32)
        self._write()

    @property
    def v(self):
        h, s, v = _rgb_to_hsv(self.r, self.g, self.b)
        return v

    @v.setter
    def v(self, value):
        self._check_frozen()
        h, s, vv = _rgb_to_hsv(self.r, self.g, self.b)
        r, g, b = _hsv_to_rgb(h, s, value)
        self._data[:] = np.array([r, g, b], dtype=np.float32)
        self._write()

    @property
    def hsv(self):
        return _rgb_to_hsv(self.r, self.g, self.b)

    @hsv.setter
    def hsv(self, value):
        self._check_frozen()
        h, s, v = value
        r, g, b = _hsv_to_rgb(h, s, v)
        self._data[:] = np.array([r, g, b], dtype=np.float32)
        self._write()

    def copy(self):
        c = Color(self._data.tolist())
        c.is_frozen = False
        c.is_wrapped = False
        c.owner = None
        c._on_write = None
        return c

    def from_scene_linear_to_srgb(self):
        def f(x):
            if x <= 0.0031308:
                return 12.92 * x
            return 1.055 * (x ** (1.0 / 2.4)) - 0.055
        return Color([f(float(c)) for c in self._data])

    def from_srgb_to_scene_linear(self):
        def f(x):
            if x <= 0.04045:
                return x / 12.92
            return ((x + 0.055) / 1.055) ** 2.4
        return Color([f(float(c)) for c in self._data])

    def __getattr__(self, name):
        if name.startswith("from_") and name not in ("from_scene_linear_to_srgb", "from_srgb_to_scene_linear"):
            def _raise(*a, **k):
                raise NotImplementedError(f"Color.{name} is not implemented in Quartz")
            return _raise
        raise AttributeError(name)

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

    def __add__(self, other):
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64).ravel()
        r = self._data.astype(np.float64) + o
        return Color(r.astype(np.float32).tolist())

    def __sub__(self, other):
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64).ravel()
        r = self._data.astype(np.float64) - o
        return Color(r.astype(np.float32).tolist())

    def __mul__(self, other):
        if isinstance(other, (int, float, np.integer, np.floating)):
            r = self._data.astype(np.float64) * float(other)
            return Color(r.astype(np.float32).tolist())
        o = np.asarray(other._data if hasattr(other, "_data") else other, dtype=np.float64).ravel()
        if o.size == 3:
            r = self._data.astype(np.float64) * o
            return Color(r.astype(np.float32).tolist())
        raise TypeError("unsupported operand")

    def __rmul__(self, other):
        return self.__mul__(other)

    __eq__ = _MathBase.__eq__
    __ne__ = _MathBase.__ne__
    __hash__ = _MathBase.__hash__

    def __repr__(self):
        vals = ", ".join(repr(float(v)) for v in self._data)
        return f"Color(({vals}))"
