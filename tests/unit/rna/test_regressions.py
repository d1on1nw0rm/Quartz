import numpy as np
import pytest

import quartz.errors as E
import quartz.props as P
import quartz.rna as R
from quartz.props import (
    BoolVectorProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty,
    IntVectorProperty, PointerProperty, StringProperty,
)
from quartz.rna import datapath as DP
from quartz.rna import hooks as H
from quartz.rna import properties as PR

PREFIX = "bpy_struct: item.attr = val: "


@pytest.fixture(autouse=True)
def _hooks_isolated():
    snap = H.snapshot()
    yield
    H.restore(snap)


def register(cls):
    R.install_properties(cls)
    type.__setattr__(cls, "bl_rna", R.RNAStruct(cls))
    return cls


def one(deferred, name="x", base=R.Struct, cls_name="Foo"):
    return register(R.StructMeta(cls_name, (base,), {"__annotations__": {name: deferred}}))


def build(deferred):
    class Owner(R.Struct):
        pass
    return PR.build_property("x", deferred, Owner)


def make_id():
    class FakeID(R.Struct):
        _q_is_id = True
    return register(FakeID)



def test_d01_remove_property_fires_hook_and_updates_dynamic():
    log = []
    H.install(on_type_property_removed=lambda c, i: log.append(i))
    Foo = one(IntProperty())
    R.define_property(Foo, "y", IntProperty())
    R.remove_property(Foo, "y")
    P.RemoveProperty(Foo, attr="x")
    assert R.get_property(Foo, "y") is None and R.get_property(Foo, "x") is None
    assert log == ["y", "x"] and "y" not in Foo.__dict__["_q_dynamic"]


def test_d01_delattr_goes_through_remove_property():
    log = []
    H.install(on_type_property_removed=lambda c, i: log.append(i))
    Foo = one(IntProperty())
    del Foo.x
    assert log == ["x"] and "x" not in Foo.__dict__


def test_d02_remove_non_property_attribute_error():
    Foo = one(IntProperty())
    type.__setattr__(Foo, "plain", 1)
    with pytest.raises(AttributeError):
        R.remove_property(Foo, "plain")
    with pytest.raises(AttributeError):
        R.remove_property(Foo, "missing")
    assert Foo.__dict__["plain"] == 1



def test_d03_state_roundtrip_in_place():
    Inner = register(type("RgInner", (R.PropertyGroup,), {"__annotations__": {"n": IntProperty()}}))
    Foo = register(type("RgFoo", (R.Struct,), {"__annotations__": {
        "v": FloatVectorProperty(), "pg": PointerProperty(type=Inner), "col": CollectionProperty(type=Inner)}}))
    f = Foo()
    f.v = (1, 2, 3)
    f.pg.n = 4
    f.col.add().n = 6
    st = f._q_state_get()
    assert st["p"]["v"] is not f._p["v"] and st["p"]["pg"]["p"]["n"] == 4 and st["p"]["col"][0]["p"]["n"] == 6
    live, pg = f.v, f.pg
    f.v = (0, 0, 0)
    f.pg.n = 0
    f.col.clear()
    f._q_state_set(st)
    assert list(live) == [1.0, 2.0, 3.0] and f.pg is pg and f.pg.n == 4 and f.col[0].n == 6



def test_d04_pointer_wrong_type_rejected():
    FakeID = make_id()
    f = one(PointerProperty(type=FakeID))()
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 5
    assert PREFIX + "Foo.x expected a FakeID type, not int" in str(ei.value)
    assert "x" not in f._p


@pytest.mark.parametrize("deferred,value", [
    (IntProperty(), 2.0), (FloatProperty(), "a"), (StringProperty(), 3), (EnumProperty(items=[("A", "a", "")]), "Z"),
])
def test_d11_prefix_on_every_coercion_error(deferred, value):
    f = one(deferred)()
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = value
    assert str(ei.value).startswith(PREFIX)



def test_d05_idref_closures_bound_to_their_property():
    FakeID = make_id()
    Foo = register(type("RgRefs", (R.Struct,), {"__annotations__": {
        "a": PointerProperty(type=FakeID), "b": PointerProperty(type=FakeID)}}))
    f, ta, tb, tn = Foo(), FakeID(), FakeID(), FakeID()
    f.a, f.b = ta, tb
    ref_a = [r for r in f._q_refs() if r.target is ta][0]
    ref_a.remap(tn)
    assert f.a is tn and f.b is tb
    ref_a.clear()
    assert f.a is None and f.b is tb



@pytest.mark.parametrize("deferred", [
    IntProperty(default=1.5), StringProperty(default=1), IntVectorProperty(size=2, default=(1, 2, 3)),
    BoolVectorProperty(size=2, default=(True,)),
    EnumProperty(items=[("A", "a", "")], options={"ENUM_FLAG"}, default=["A"]),
])
def test_d06_d07_bad_defaults_rejected(deferred):
    with pytest.raises(E.RegistrationError) as ei:
        build(deferred)
    assert "could not register" in str(ei.value) and ei.value.__cause__ is not None


def test_d24_vector_default_clamped():
    p = build(IntVectorProperty(default=(-5, 5, 50), min=0, max=10))
    assert p.default == (0, 5, 10)



def test_d08_kind_classvar_and_vector_kind():
    assert PR.IntDef.kind == "INT" and PR.CollectionDef.kind == "COLLECTION"
    p = build(FloatVectorProperty())
    assert isinstance(p, PR.FloatDef) and p.kind == "FLOAT" and "kind" not in vars(p)
    assert p.to_rna_dict()["type"] == "FLOAT"


def test_d09_d10_rna_dict_flags_and_float32_limits():
    d = build(FloatProperty(max=1e12, options={"HIDDEN", "ANIMATABLE"})).to_rna_dict()
    assert d["flags"] == ["is_animatable", "is_hidden"]
    assert d["max"] == 999999995904.0



def test_d12_coerce_without_inst():
    assert build(IntProperty(min=0)).coerce(-4) == 0



def test_d13_readonly_virtual_array_component_write():
    store = np.zeros(3, dtype=np.float32)
    f = one(FloatVectorProperty(meta={"virtual_get": lambda s: store}))()
    with pytest.raises(E.ReadOnlyError):
        f.x[1] = 2.0
    assert store.tolist() == [0.0, 0.0, 0.0]



def test_d14_resolve_failure_is_value_error():
    s = R.Struct()
    with pytest.raises(ValueError) as ei:
        DP.resolve(s, "nope.deeper")
    assert 'Path "nope.deeper" could not be resolved' in str(ei.value)



def test_d15_d16_install_returns_defs_and_uninstall_removes_dynamic():
    class K(R.Struct):
        a: IntProperty()
    out = R.install_properties(K)
    type.__setattr__(K, "bl_rna", R.RNAStruct(K))
    assert out == [K.__dict__["a"]] and K.__dict__["_q_installed"] == ["a"]
    K.d = IntProperty()
    R.uninstall_properties(K)
    assert R.get_property(K, "a") is None and R.get_property(K, "d") is None


def test_d17_dynamic_properties_last_in_definition_order():
    Base = one(IntProperty(), "a", cls_name="RgBase")
    Sub = one(IntProperty(), "c", base=Base, cls_name="RgSub")
    R.define_property(Sub, "e", IntProperty())
    R.define_property(Base, "d", IntProperty())
    assert [p.identifier for p in R.iter_properties(Sub)] == ["a", "c", "e", "d"]



def test_d18_structmeta_setattr_propagates():
    Foo = one(IntProperty())
    with pytest.raises(E.RegistrationError):
        Foo.bad = IntProperty(default="no")
    assert "bad" not in Foo.__dict__


def test_d19_path_from_id_without_owner():
    with pytest.raises(ValueError) as ei:
        R.PropertyGroup().path_from_id("name")
    assert "PropertyGroup.path_from_id() does not support path creation for this type" in str(ei.value)


def test_d20_pg_keys_first_write_order():
    PG = one(IntProperty(), base=R.PropertyGroup, cls_name="RgPG")
    pg = PG()
    pg["a"] = 1
    pg.x = 1
    pg["b"] = 2
    pg["a"] = 3
    assert pg.keys() == ["a", "x", "b"]


def test_d26_system_properties_only_written_values():
    Foo = register(type("RgSys", (R.Struct,), {"__annotations__": {"x": IntProperty(), "v": IntVectorProperty()}}))
    f = Foo()
    f.v
    assert f.bl_system_properties_get() is None
    f.v = (1, 2, 3)
    assert f.bl_system_properties_get().to_dict() == {"v": [1, 2, 3]}



def test_d21_unsupported_idprop_values():
    g = R.IDPropertyGroup()
    for bad in (object(), {1, 2}, ["a", "b"], None):
        with pytest.raises(TypeError):
            g["k"] = bad
    assert "k" not in g


def test_d22_ui_manager_defaults_and_soft_range():
    g = R.IDPropertyGroup({"f": 2.5, "i": 3})
    m = R.IDPropertyUIManager(g, "f")
    assert m.as_dict()["default"] == 0.0
    m.update(min=1, max=2)
    d = m.as_dict()
    assert (d["min"], d["max"], d["soft_min"], d["soft_max"]) == (1.0, 2.0, 1.0, 2.0) and type(d["min"]) is float
    assert R.IDPropertyUIManager(g, "i").as_dict()["default"] == 0


def test_d27_mutable_mapping_semantics():
    g = R.IDPropertyGroup()
    with pytest.raises(KeyError):
        g.pop("missing")
    g.update(R.IDPropertyGroup({"a": 1}), b=2)
    g.update([("c", 3)])
    assert g.to_dict() == {"a": 1, "b": 2, "c": 3}



def test_d23_base_is_base_bl_rna():
    Base = one(IntProperty(), cls_name="RgRB")
    Sub = register(type("RgRS", (Base,), {}))
    assert Sub.bl_rna.base is Base.bl_rna and R.PropertyGroup.bl_rna.base is R.Struct.bl_rna


def test_d28_rna_type_pseudo_property():
    rp = one(IntProperty()).bl_rna.properties["rna_type"]
    assert rp.q_definition is None and rp.type == "POINTER" and rp.is_readonly



def test_d25_enum_flag_rejects_tuple():
    f = one(EnumProperty(items=[("A", "a", "")], options={"ENUM_FLAG"}))()
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = ("A",)
    assert "expected a set" in str(ei.value)
