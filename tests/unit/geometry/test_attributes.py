import numpy as np
import pytest

from quartz.geometry import (
    DATA_TYPES,
    DOMAINS,
    REQUIRED_ATTRIBUTES,
    AttributeArray,
    AttributeStore,
    default_fill,
)


class Sizes:

    def __init__(self, **values):
        self.values = {"POINT": 0, "EDGE": 0, "FACE": 0, "CORNER": 0}
        self.values.update(values)

    def __call__(self, domain):
        return self.values[domain]


def test_domains_and_data_types():
    assert DOMAINS == ("POINT", "EDGE", "FACE", "CORNER")
    assert REQUIRED_ATTRIBUTES == frozenset(
        {"position", ".edge_verts", ".corner_vert", ".corner_edge"}
    )
    for name, (dtype, shape) in DATA_TYPES.items():
        assert isinstance(name, str)
        assert isinstance(dtype, np.dtype)
        assert isinstance(shape, tuple)
    assert DATA_TYPES["FLOAT_VECTOR"] == (np.dtype(np.float32), (3,))
    assert DATA_TYPES["BYTE_COLOR"] == (np.dtype(np.uint8), (4,))
    assert DATA_TYPES["FLOAT4X4"] == (np.dtype(np.float32), (4, 4))


def test_default_fill_values():
    assert float(default_fill("FLOAT")) == 0.0
    assert int(default_fill("INT")) == 0
    assert bool(default_fill("BOOLEAN")) is False
    np.testing.assert_array_equal(default_fill("FLOAT2"), np.zeros(2, np.float32))
    np.testing.assert_array_equal(
        default_fill("QUATERNION"), np.array([1, 0, 0, 0], np.float32)
    )
    np.testing.assert_array_equal(default_fill("FLOAT4X4"), np.eye(4, dtype=np.float32))
    with pytest.raises(ValueError):
        default_fill("NOPE")


def test_new_sizes_and_fill():
    sizes = Sizes(POINT=3, FACE=2)
    store = AttributeStore(sizes)
    attr = store.new("a", "FLOAT", "POINT")
    assert attr.data.shape == (3,)
    assert attr.data.dtype == np.float32
    vec = store.new("b", "FLOAT_VECTOR", "POINT", fill=(1.0, 2.0, 3.0))
    assert vec.data.shape == (3, 3)
    np.testing.assert_array_equal(vec.data[0], np.array([1, 2, 3], np.float32))
    flag = store.new("c", "BOOLEAN", "FACE", fill=True)
    assert flag.data.shape == (2,)
    assert flag.data.all()


def test_new_rejects_bad_arguments():
    store = AttributeStore(Sizes())
    store.new("a", "FLOAT", "POINT")
    with pytest.raises(ValueError):
        store.new("a", "FLOAT", "POINT")
    with pytest.raises(ValueError):
        store.new("b", "NOPE", "POINT")
    with pytest.raises(ValueError):
        store.new("b", "FLOAT", "NOPE")
    with pytest.raises(ValueError):
        store.new("", "FLOAT", "POINT")
    with pytest.raises(ValueError):
        store.new("b", "FLOAT2", "POINT", fill=(1.0, 2.0, 3.0))


def test_get_item_contains_iteration_order():
    store = AttributeStore(Sizes(POINT=1))
    for name in ("z", "a", "m"):
        store.new(name, "FLOAT", "POINT")
    assert "a" in store
    assert "missing" not in store
    assert [attr.name for attr in store] == ["z", "a", "m"]
    assert len(store) == 3
    assert store.get("a") is store["a"]
    assert store.get("missing") is None
    with pytest.raises(KeyError):
        store["missing"]


def test_remove_rules():
    store = AttributeStore(Sizes(POINT=1))
    store.new("position", "FLOAT_VECTOR", "POINT")
    store.new("custom", "FLOAT", "POINT")
    with pytest.raises(ValueError):
        store.remove("position")
    with pytest.raises(KeyError):
        store.remove("missing")
    store.remove("custom")
    assert "custom" not in store


def test_rename_keeps_order():
    store = AttributeStore(Sizes(POINT=1))
    store.new("a", "FLOAT", "POINT")
    store.new("b", "FLOAT", "POINT")
    store.new("c", "FLOAT", "POINT")
    store.rename("b", "bb")
    assert [attr.name for attr in store] == ["a", "bb", "c"]
    with pytest.raises(ValueError):
        store.rename("bb", "a")
    with pytest.raises(KeyError):
        store.rename("missing", "x")


def test_rename_required_attribute_is_rejected():
    store = AttributeStore(Sizes(POINT=1))
    store.new("position", "FLOAT_VECTOR", "POINT")
    with pytest.raises(ValueError):
        store.rename("position", "co")


def test_names_and_by_domain():
    store = AttributeStore(Sizes(POINT=1, FACE=1))
    store.new("position", "FLOAT_VECTOR", "POINT")
    store.new(".hidden", "FLOAT", "POINT")
    store.new("sharp_face", "BOOLEAN", "FACE")
    assert store.names() == ["position", ".hidden", "sharp_face"]
    assert store.names(include_internal=False) == ["position", "sharp_face"]
    assert store.names("FACE") == ["sharp_face"]
    assert [attr.name for attr in store.by_domain("POINT")] == ["position", ".hidden"]
    with pytest.raises(ValueError):
        store.names("NOPE")


def test_resize_truncates_and_fills_defaults():
    sizes = Sizes(POINT=2)
    store = AttributeStore(sizes)
    attr = store.new("a", "FLOAT", "POINT", fill=2.0)
    quat = store.new("q", "QUATERNION", "POINT")
    store.resize("POINT", 4)
    assert attr.data.shape == (4,)
    np.testing.assert_array_equal(attr.data, np.array([2, 2, 0, 0], np.float32))
    np.testing.assert_array_equal(quat.data[2], np.array([1, 0, 0, 0], np.float32))
    store.resize("POINT", 1)
    np.testing.assert_array_equal(attr.data, np.array([2], np.float32))
    with pytest.raises(ValueError):
        store.resize("POINT", -1)
    with pytest.raises(ValueError):
        store.resize("NOPE", 1)


def test_unique_name():
    store = AttributeStore(Sizes(POINT=1))
    assert store.unique_name("col") == "col"
    store.new("col", "FLOAT", "POINT")
    assert store.unique_name("col") == "col.001"
    store.new("col.001", "FLOAT", "POINT")
    assert store.unique_name("col") == "col.002"


def test_copy_is_deep():
    store = AttributeStore(Sizes(POINT=2))
    attr = store.new("a", "FLOAT", "POINT", fill=1.0)
    clone = store.copy(Sizes(POINT=2))
    clone["a"].data[0] = 9.0
    assert attr.data[0] == 1.0
    assert clone["a"].data[0] == 9.0
    assert clone["a"] is not attr


def test_attribute_array_flags_and_copy():
    required = AttributeArray("position", "POINT", "FLOAT_VECTOR", np.zeros((1, 3), np.float32))
    hidden = AttributeArray(".edge_verts", "EDGE", "INT32_2D", np.zeros((1, 2), np.int32))
    custom = AttributeArray("weight", "POINT", "FLOAT", np.zeros(1, np.float32))
    assert required.is_required and not required.is_internal
    assert hidden.is_required and hidden.is_internal
    assert not custom.is_required and not custom.is_internal
    clone = custom.copy()
    clone.data[0] = 5.0
    assert custom.data[0] == 0.0
