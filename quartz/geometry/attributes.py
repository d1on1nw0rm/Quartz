from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Mapping

import numpy as np

DOMAINS: tuple[str, ...] = ("POINT", "EDGE", "FACE", "CORNER")

DATA_TYPES: Mapping[str, tuple[np.dtype, tuple[int, ...]]] = {
    "FLOAT": (np.dtype(np.float32), ()),
    "INT": (np.dtype(np.int32), ()),
    "INT8": (np.dtype(np.int8), ()),
    "BOOLEAN": (np.dtype(np.bool_), ()),
    "FLOAT_VECTOR": (np.dtype(np.float32), (3,)),
    "FLOAT2": (np.dtype(np.float32), (2,)),
    "INT16_2D": (np.dtype(np.int16), (2,)),
    "INT32_2D": (np.dtype(np.int32), (2,)),
    "FLOAT_COLOR": (np.dtype(np.float32), (4,)),
    "BYTE_COLOR": (np.dtype(np.uint8), (4,)),
    "QUATERNION": (np.dtype(np.float32), (4,)),
    "FLOAT4X4": (np.dtype(np.float32), (4, 4)),
}

REQUIRED_ATTRIBUTES: frozenset[str] = frozenset(
    {"position", ".edge_verts", ".corner_vert", ".corner_edge"}
)

_SCALAR_PROTOTYPES: Mapping[np.dtype, type] = {
    np.dtype(np.float32): np.float32,
    np.dtype(np.int32): np.int32,
    np.dtype(np.int8): np.int8,
    np.dtype(np.bool_): np.bool_,
    np.dtype(np.int16): np.int16,
    np.dtype(np.uint8): np.uint8,
}


def default_fill(data_type: str) -> object:
    try:
        dtype, sub_shape = DATA_TYPES[data_type]
    except KeyError:
        raise ValueError(f"unknown attribute data type {data_type!r}") from None
    if data_type == "QUATERNION":
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=dtype)
    if data_type == "FLOAT4X4":
        return np.eye(4, dtype=dtype)
    if sub_shape:
        return np.zeros(sub_shape, dtype=dtype)
    return _SCALAR_PROTOTYPES[dtype](0)


@dataclass
class AttributeArray:

    name: str
    domain: str
    data_type: str
    data: np.ndarray

    @property
    def is_internal(self) -> bool:
        return self.name.startswith(".")

    @property
    def is_required(self) -> bool:
        return self.name in REQUIRED_ATTRIBUTES

    def copy(self) -> AttributeArray:
        return AttributeArray(self.name, self.domain, self.data_type, self.data.copy())


class AttributeStore:

    def __init__(self, sizes: Callable[[str], int]) -> None:
        if not callable(sizes):
            raise TypeError("AttributeStore requires a callable domain-size function")
        self._sizes = sizes
        self._attrs: dict[str, AttributeArray] = {}

    @staticmethod
    def _check_type(data_type: str, domain: str) -> None:
        if data_type not in DATA_TYPES:
            raise ValueError(f"unknown attribute data type {data_type!r}")
        if domain not in DOMAINS:
            raise ValueError(f"unknown attribute domain {domain!r}")

    def new(
        self, name: str, data_type: str, domain: str, *, fill: object = None
    ) -> AttributeArray:
        self._check_type(data_type, domain)
        if not isinstance(name, str) or not name:
            raise ValueError("attribute name must be a non-empty string")
        if name in self._attrs:
            raise ValueError(f"attribute {name!r} already exists")
        dtype, sub_shape = DATA_TYPES[data_type]
        shape = (int(self._sizes(domain)), *sub_shape)
        data = np.empty(shape, dtype=dtype)
        value = default_fill(data_type) if fill is None else fill
        try:
            data[...] = value
        except (TypeError, ValueError) as exc:
            raise ValueError(f"cannot fill attribute {name!r} with {value!r}") from exc
        attr = AttributeArray(name, domain, data_type, data)
        self._attrs[name] = attr
        return attr

    def get(self, name: str) -> AttributeArray | None:
        return self._attrs.get(name)

    def __getitem__(self, name: str) -> AttributeArray:
        try:
            return self._attrs[name]
        except KeyError:
            raise KeyError(f"attribute {name!r} not found") from None

    def __contains__(self, name: object) -> bool:
        return name in self._attrs

    def __iter__(self) -> Iterator[AttributeArray]:
        return iter(list(self._attrs.values()))

    def __len__(self) -> int:
        return len(self._attrs)

    def remove(self, name: str) -> None:
        if name not in self._attrs:
            raise KeyError(f"attribute {name!r} not found")
        if name in REQUIRED_ATTRIBUTES:
            raise ValueError(f"attribute {name!r} is required and cannot be removed")
        del self._attrs[name]

    def rename(self, old: str, new: str) -> None:
        if old not in self._attrs:
            raise KeyError(f"attribute {old!r} not found")
        if old in REQUIRED_ATTRIBUTES:
            raise ValueError(f"attribute {old!r} is required and cannot be renamed")
        if new in self._attrs:
            raise ValueError(f"attribute {new!r} already exists")
        if not isinstance(new, str) or not new:
            raise ValueError("attribute name must be a non-empty string")
        attr = self._attrs[old]
        rebuilt: dict[str, AttributeArray] = {}
        for key, value in self._attrs.items():
            if key == old:
                value.name = new
                rebuilt[new] = value
            else:
                rebuilt[key] = value
        self._attrs = rebuilt
        attr.name = new

    def names(
        self, domain: str | None = None, *, include_internal: bool = True
    ) -> list[str]:
        if domain is not None and domain not in DOMAINS:
            raise ValueError(f"unknown attribute domain {domain!r}")
        out: list[str] = []
        for attr in self._attrs.values():
            if domain is not None and attr.domain != domain:
                continue
            if not include_internal and attr.is_internal:
                continue
            out.append(attr.name)
        return out

    def by_domain(self, domain: str) -> list[AttributeArray]:
        if domain not in DOMAINS:
            raise ValueError(f"unknown attribute domain {domain!r}")
        return [attr for attr in self._attrs.values() if attr.domain == domain]

    def resize(self, domain: str, size: int) -> None:
        if domain not in DOMAINS:
            raise ValueError(f"unknown attribute domain {domain!r}")
        size = int(size)
        if size < 0:
            raise ValueError("attribute size cannot be negative")
        for attr in self._attrs.values():
            if attr.domain == domain:
                _resize_array(attr, size)

    def unique_name(self, base: str) -> str:
        if base not in self._attrs:
            return base
        index = 1
        while f"{base}.{index:03d}" in self._attrs:
            index += 1
        return f"{base}.{index:03d}"

    def copy(self, sizes: Callable[[str], int]) -> AttributeStore:
        clone = AttributeStore(sizes)
        for attr in self._attrs.values():
            clone._attrs[attr.name] = attr.copy()
        return clone


def _resize_array(attr: AttributeArray, size: int) -> None:
    current = int(attr.data.shape[0])
    if current == size:
        return
    dtype, sub_shape = DATA_TYPES[attr.data_type]
    new_shape = (size, *sub_shape)
    data = np.empty(new_shape, dtype=dtype)
    data[...] = default_fill(attr.data_type)
    keep = min(current, size)
    if keep:
        data[:keep] = attr.data[:keep]
    attr.data = data
