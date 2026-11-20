import numpy as np

from quartz.errors import PropertyTypeError, ReadOnlyError
from quartz.props import IntProperty, FloatProperty, StringProperty, EnumProperty, PointerProperty, CollectionProperty, FloatVectorProperty
from quartz.rna import Struct, PropertyGroup, builtin_struct, describe, hooks


def test_errors_subclass():
    from quartz.errors import QuartzError
    import builtins
    assert issubclass(QuartzError, Exception)


def test_int_coercion():
    @builtin_struct
    class Foo(Struct):
        x: IntProperty(default=0)
    f = Foo()
    f.x = 5
    assert f.x == 5
    try:
        f.x = 2.0
    except PropertyTypeError:
        pass
    else:
        raise AssertionError("expected PropertyTypeError")


def test_float32():
    @builtin_struct
    class Foo(Struct):
        x: FloatProperty(default=0.1)
    f = Foo()
    assert f.x == float(np.float32(0.1))


def test_string_maxlen():
    @builtin_struct
    class Foo(Struct):
        s: StringProperty(maxlen=5)
    f = Foo()
    f.s = "ÃÃÃ…"
    assert f.s.encode("utf-8") == "ÃÃ".encode("utf-8")


def test_enum():
    @builtin_struct
    class Foo(Struct):
        m: EnumProperty(items=[("A", "A", "a"), ("B", "B", "b")], default="A")
    f = Foo()
    assert f.m == "A"
    f.m = "B"
    assert f.m == "B"
    try:
        f.m = "Z"
    except PropertyTypeError:
        pass
    else:
        raise AssertionError("expected")


def test_vector_wrap():
    @builtin_struct
    class Foo(Struct):
        loc: FloatVectorProperty(default=(1, 2, 3))
    f = Foo()
    f.loc[0] = 10
    assert list(f.loc) == [10.0, 2.0, 3.0]


def test_pointer_collection():
    @builtin_struct
    class Item(PropertyGroup):
        pass

    @builtin_struct
    class Foo(Struct):
        item: PointerProperty(type=Item)
        items: CollectionProperty(type=Item)

    f = Foo()
    f.item.name = "abc"
    assert f.item.name == "abc"
    col = f.items
    new = col.add()
    new.name = "xyz"
    assert len(col) == 1
    assert col[0].name == "xyz"


def test_hooks():
    hooks.reset()
    assert hooks.repr_root() == "quartz"
    hooks.install(repr_root=lambda: "bpy")
    assert hooks.repr_root() == "bpy"
    hooks.reset()


def test_describe():
    @builtin_struct
    class Foo(PropertyGroup):
        x: IntProperty(default=3, meta={"group": "g"})
    d = describe(Foo)
    assert "x" in d
    assert "g" in d.groups()
    assert d.children_of("x") == ()
    assert d.is_enabled(Foo(), "x") is True


def test_datapath():
    from quartz.rna.datapath import parse, format
    toks = parse('a.b[0]["c"].d')
    assert format(toks) == 'a.b[0]["c"].d'


def test_readonly():
    @builtin_struct
    class Foo(Struct):
        x: IntProperty(get=lambda self: 1)
    f = Foo()
    try:
        f.x = 2
    except ReadOnlyError:
        pass
    else:
        raise AssertionError("expected readonly")
