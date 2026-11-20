import math as _math
import numpy as np
from quartz.math.vector import Vector


class KDTree:
    def __init__(self, size):
        self.size = int(size)
        self._points = [None] * self.size
        self._indices = [None] * self.size
        self._count = 0
        self._balanced = False

    def insert(self, co, index):
        if self._count >= self.size:
            raise ValueError("KDTree is full")
        arr = np.asarray(co._data if hasattr(co, "_data") else co, dtype=np.float64).ravel()
        self._points[self._count] = arr.copy()
        self._indices[self._count] = int(index)
        self._count += 1
        self._balanced = False

    def balance(self):
        self._balanced = True

    def _ensure(self):
        if not self._balanced:
            raise RuntimeError("KDTree must be balanced before use")

    def find(self, co, filter=None):
        self._ensure()
        arr = np.asarray(co._data if hasattr(co, "_data") else co, dtype=np.float64).ravel()
        best = None
        bestd = None
        besti = None
        for i in range(self._count):
            if filter is not None and not filter(self._indices[i]):
                continue
            d = float(np.linalg.norm(self._points[i] - arr))
            if bestd is None or d < bestd or (d == bestd and self._indices[i] < besti):
                bestd = d
                best = self._points[i].copy()
                besti = self._indices[i]
        if best is None:
            return (None, None, None)
        return (Vector(best.astype(np.float32).tolist()), besti, bestd)

    def find_n(self, co, n):
        self._ensure()
        arr = np.asarray(co._data if hasattr(co, "_data") else co, dtype=np.float64).ravel()
        items = []
        for i in range(self._count):
            d = float(np.linalg.norm(self._points[i] - arr))
            items.append((d, self._indices[i], self._points[i].copy()))
        items.sort(key=lambda t: (t[0], t[1]))
        res = []
        for d, idx, pt in items[:n]:
            res.append((Vector(pt.astype(np.float32).tolist()), idx, d))
        return res

    def find_range(self, co, radius):
        self._ensure()
        arr = np.asarray(co._data if hasattr(co, "_data") else co, dtype=np.float64).ravel()
        items = []
        for i in range(self._count):
            d = float(np.linalg.norm(self._points[i] - arr))
            if d <= radius + 1e-12:
                items.append((d, self._indices[i], self._points[i].copy()))
        items.sort(key=lambda t: (t[0], t[1]))
        return [(Vector(pt.astype(np.float32).tolist()), idx, d) for d, idx, pt in items]
