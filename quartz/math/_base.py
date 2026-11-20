import copy as _copy
import numpy as np


class _MathBase:

    def __init__(self):
        self._data = None
        self.is_wrapped = False
        self.is_frozen = False
        self.owner = None
        self._on_write = None

    @property
    def is_valid(self):
        if not self.is_wrapped:
            return True
        owner = self.owner
        if owner is None:
            return True
        return not getattr(type(owner), "_q_removed", False)

    def _write(self):
        if self._on_write is not None:
            self._on_write()

    def _check_frozen(self):
        if self.is_frozen:
            raise TypeError(f"{type(self).__name__} is frozen")
        if self.is_wrapped and self.owner is not None and getattr(self.owner, "is_frozen", False) is True:
            raise TypeError(f"{type(self).__name__} is frozen (owner is frozen)")

    def _assign(self, arr):
        arr = np.asarray(arr, dtype=np.float64)
        if arr.shape == self._data.shape:
            self._data[...] = arr.astype(np.float32)
        else:
            self._check_wrapped_resize()
            self._data = arr.astype(np.float32)

    def _check_wrapped_resize(self):
        if self.is_wrapped:
            raise TypeError(f"Cannot resize wrapped {type(self).__name__}")

    def copy(self):
        raise NotImplementedError

    def freeze(self):
        if self.is_wrapped:
            raise TypeError("Cannot freeze wrapped data")
        self.is_frozen = True
        return self

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo):
        return self.copy()

    def __array__(self, dtype=None, copy=None):
        if dtype is None:
            dtype = self._data.dtype
        return np.array(self._data, dtype=dtype, copy=True)

    @classmethod
    def _q_wrap(cls, view, *, owner=None, on_write=None, **extra):
        obj = cls.__new__(cls)
        obj._data = np.asarray(view)
        obj.is_wrapped = True
        obj.is_frozen = False
        obj.owner = owner
        obj._on_write = on_write
        for k, v in extra.items():
            setattr(obj, k, v)
        return obj

    def __hash__(self):
        if not self.is_frozen:
            raise TypeError(f"{type(self).__name__} is not frozen (mutable), call freeze first")
        return hash(tuple(float(x) for x in np.ravel(self._data)))

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        if self._data.shape != other._data.shape:
            return False
        return bool(np.all(self._data == other._data))

    def __ne__(self, other):
        return not self.__eq__(other)
