from __future__ import annotations

from typing import Any, Callable, Iterator, MutableSequence

import numpy as np

from ..errors import PropertyValueError, ReadOnlyError


class PropCollection:
    def __init__(self, *, owner: object = None, path: str = "") -> None:
        self._owner = owner
        self._path = path

    def _q_items(self) -> Any:
        raise NotImplementedError

    def _q_key(self, item: object) -> str | None:
        return getattr(item, "name", None)

    def __len__(self) -> int:
        return len(self._q_items())

    def __iter__(self) -> Iterator[object]:
        return iter(self._q_items())

    def __getitem__(self, key):
        items = self._q_items()
        if isinstance(key, slice):
            return list(items[key])
        if isinstance(key, str):
            for item in items:
                if self._q_key(item) == key:
                    return item
            raise KeyError(f'bpy_prop_collection[key]: key "{key}" not found')
        idx = key
        if idx < 0:
            idx += len(items)
        if idx < 0 or idx >= len(items):
            raise IndexError("index out of range")
        return items[idx]

    def __contains__(self, key) -> bool:
        if isinstance(key, str):
            try:
                self[key]
                return True
            except KeyError:
                return False
        for item in self._q_items():
            if item is key:
                return True
        return False

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def find(self, key: str) -> int:
        items = self._q_items()
        for i, item in enumerate(items):
            if self._q_key(item) == key:
                return i
        return -1

    def keys(self) -> list[str]:
        return [self._q_key(item) for item in self._q_items() if self._q_key(item) is not None]

    def values(self) -> list[object]:
        return list(self._q_items())

    def items(self) -> list[tuple[str, object]]:
        return [(self._q_key(item), item) for item in self._q_items()]

    def foreach_get(self, attr, seq):
        items = self._q_items()
        flat = []
        for item in items:
            val = getattr(item, attr)
            if isinstance(val, (list, tuple, np.ndarray)):
                flat.extend(list(val))
            else:
                flat.append(val)
        if len(seq) != len(flat):
            raise PropertyValueError("foreach_get/set: sequence size mismatch")
        for i, v in enumerate(flat):
            seq[i] = v

    def foreach_set(self, attr, seq):
        items = self._q_items()
        if not items:
            return
        first_val = getattr(items[0], attr)
        if isinstance(first_val, (list, tuple, np.ndarray)):
            chunk = len(first_val)
        else:
            chunk = 1
        if len(seq) != len(items) * chunk:
            raise PropertyValueError("foreach_get/set: sequence size mismatch")
        for i, item in enumerate(items):
            if chunk == 1:
                setattr(item, attr, seq[i])
            else:
                setattr(item, attr, list(seq[i * chunk:(i + 1) * chunk]))

    @property
    def rna_type(self):
        owner = self._owner
        if owner is not None and hasattr(owner, "rna_type"):
            return owner.rna_type
        return None

    @property
    def id_data(self):
        owner = self._owner
        if owner is not None and hasattr(owner, "id_data"):
            return owner.id_data
        return None

    def path_from_id(self) -> str:
        owner = self._owner
        if owner is not None and hasattr(owner, "path_from_id"):
            p = owner.path_from_id(self._path) if self._path else owner.path_from_id()
            return p
        return self._path

    def __repr__(self) -> str:
        return f"<bpy_collection[{len(self)}], {type(self).__name__}>"

    def __bool__(self) -> bool:
        return len(self) > 0


class GroupCollection(PropCollection):
    def __init__(self, item_type, *, owner, path):
        super().__init__(owner=owner, path=path)
        self.item_type = item_type
        self._items = []

    def _q_items(self):
        return self._items

    def add(self):
        from .struct import PropertyGroup
        inst = self.item_type.__new__(self.item_type)
        if not hasattr(inst, "_p"):
            pass
        inst._q_set_owner(self._owner, f"{self._path}[{len(self._items)}]")
        self._items.append(inst)
        for i, it in enumerate(self._items):
            it._q_set_owner(self._owner, f"{self._path}[{i}]")
        if self._owner is not None:
            try:
                self._owner._p_set.add(self._path.split("[")[0].split(".")[-1])
            except Exception:
                pass
        return inst

    def remove(self, index):
        items = self._items
        if index < 0 or index >= len(items):
            raise IndexError("index out of range")
        del items[index]
        for i, it in enumerate(items):
            it._q_set_owner(self._owner, f"{self._path}[{i}]")

    def clear(self):
        self._items.clear()

    def move(self, from_index, to_index):
        items = self._items
        if from_index < 0 or from_index >= len(items):
            raise IndexError("index out of range")
        if to_index < 0 or to_index >= len(items):
            raise IndexError("index out of range")
        item = items.pop(from_index)
        items.insert(to_index, item)
        for i, it in enumerate(items):
            it._q_set_owner(self._owner, f"{self._path}[{i}]")


class PropArray:
    def __init__(self, values, *, on_write=None, owner=None, pdef=None):
        self._owner = owner
        self._pdef = pdef
        self._on_write = on_write
        if isinstance(values, np.ndarray):
            self._data = values
        else:
            self._data = np.asarray(values)
        if self._data is None:
            self._data = np.asarray([])

    def __len__(self):
        return int(self._data.shape[0]) if self._data.ndim >= 1 else 0

    def __iter__(self):
        if self._data.ndim == 1:
            for v in self._data:
                if isinstance(v, (np.floating,)):
                    yield float(v)
                elif isinstance(v, (np.integer,)):
                    yield int(v)
                elif isinstance(v, (np.bool_,)):
                    yield bool(v)
                else:
                    yield v
        else:
            for row in self._data:
                yield PropArray(row, on_write=self._on_write, owner=self._owner, pdef=self._pdef)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if self._data.ndim == 1:
            v = self._data[index]
            if isinstance(v, (np.floating,)):
                return float(v)
            if isinstance(v, (np.integer,)):
                return int(v)
            if isinstance(v, (np.bool_,)):
                return bool(v)
            return v
        if isinstance(index, int):
            row = self._data[index]
            return PropArray(row, on_write=self._on_write, owner=self._owner, pdef=self._pdef)
        return tuple(self._data[index])

    def _q_check_writable(self):
        pdef = self._pdef
        if pdef is not None and getattr(pdef, "is_readonly", False):
            owner = type(self._owner).__name__ if self._owner is not None else "bpy_struct"
            raise ReadOnlyError(f'bpy_struct: attribute "{pdef.identifier}" from "{owner}" is read-only')

    def __setitem__(self, index, value):
        self._q_check_writable()
        if isinstance(index, slice):
            self._data[index] = np.asarray(value)
        else:
            self._data[index] = value
        if self._on_write is not None:
            self._on_write()

    def __eq__(self, other):
        try:
            o = np.asarray(other)
        except Exception:
            return False
        if o.shape != self._data.shape:
            if o.reshape(-1).shape != self._data.reshape(-1).shape:
                return False
        return bool(np.array_equal(self._data, o))

    def __array__(self, dtype=None, copy=None):
        if copy:
            return np.array(self._data, dtype=dtype, copy=True)
        if dtype is None:
            return np.asarray(self._data)
        return np.asarray(self._data, dtype=dtype)

    def foreach_get(self, seq):
        flat = list(self._data.reshape(-1))
        if len(seq) != len(flat):
            raise PropertyValueError("foreach_get/set: sequence size mismatch")
        for i, v in enumerate(flat):
            seq[i] = v

    def foreach_set(self, seq):
        flat = np.asarray(seq).reshape(-1)
        if flat.size != self._data.size:
            raise PropertyValueError("foreach_get/set: sequence size mismatch")
        self._q_check_writable()
        self._data[:] = flat.reshape(self._data.shape)
        if self._on_write is not None:
            self._on_write()

    def q_to_list(self):
        return self._data.tolist()

    def __repr__(self):
        T = "float"
        owner = self._owner
        ident = ""
        if self._pdef is not None:
            ident = self._pdef.identifier
        return f"<bpy_prop_array[{len(self)}], {type(owner).__name__}.{ident}>"
