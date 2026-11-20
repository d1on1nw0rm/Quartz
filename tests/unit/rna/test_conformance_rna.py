import ast
import json
import re
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest

import quartz.errors as E
import quartz.props as P
import quartz.rna as R
from quartz.props import (
    BoolProperty, BoolVectorProperty, CollectionProperty, EnumProperty, FloatProperty,
    FloatVectorProperty, IntProperty, IntVectorProperty, PointerProperty, StringProperty,
)
from quartz.rna import datapath as DP
from quartz.rna import hooks as H
from quartz.rna import properties as PR
from quartz.rna import idprops as IP

ROOT = Path(__file__).resolve().parents[3]
F32_01 = 0.10000000149011612



@pytest.fixture(autouse=True)
def _hooks_isolated():
    snap = H.snapshot()
    yield
    H.restore(snap)


def register(cls):
    R.install_properties(cls)
    type.__setattr__(cls, "bl_rna", R.RNAStruct(cls))
    return cls


def make_id_class(repr_text="bpy.data.scenes['Scene']"):
    class FakeID(R.Struct):
        _q_is_id = True
        changes = None

        def __repr__(self):
            return repr_text

        def _q_on_change(self, pdef):
            if type(self).changes is not None:
                type(self).changes.append(pdef.identifier)
    return register(FakeID)


def build(deferred, identifier="x", owner=None):
    if owner is None:
        class Owner(R.Struct):
            pass
        owner = Owner
    return PR.build_property(identifier, deferred, owner)


def one(deferred, name="x"):
    ns = {"__annotations__": {name: deferred}}
    Foo = R.StructMeta("Foo", (R.Struct,), ns)
    Foo.__module__ = __name__
    return register(Foo)


def one_pg(deferred, name="x"):
    ns = {"__annotations__": {name: deferred}}
    Foo = R.StructMeta("FooPG", (R.PropertyGroup,), ns)
    Foo.__module__ = __name__
    return register(Foo)



OWNED = sorted([ROOT / "quartz" / "errors.py", ROOT / "quartz" / "props.py",
                *(ROOT / "quartz" / "rna").glob("*.py"), *(ROOT / "tests" / "unit" / "rna").glob("*.py")])


@pytest.mark.parametrize("path", OWNED, ids=lambda p: p.name)
def test_no_comments_or_docstrings(path):
    import io
    import tokenize
    src = path.read_text(encoding="utf-8")
    assert not [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT]
    assert not [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]


@pytest.mark.parametrize("path", [p for p in OWNED if "quartz" in p.parts and "tests" not in p.parts], ids=lambda p: p.name)
def test_layering_rna_group_does_not_import_math_or_app(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if a.name.startswith(("quartz.math", "quartz.app", "quartz.geometry", "quartz.types"))]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith(("quartz.math", "quartz.app", "quartz.geometry", "quartz.types")):
                bad.append(node.module)
    assert not bad



ERROR_BASES = {
    "QuartzError": (Exception,),
    "RegistrationError": (ValueError,),
    "RegistrationRuntimeError": (RuntimeError,),
    "MissingClassAttributeError": (AttributeError,),
    "ClassValidationError": (TypeError,),
    "PropertyTypeError": (TypeError,),
    "PropertyValueError": (ValueError,),
    "ReadOnlyError": (AttributeError,),
    "RemovedStructError": (ReferenceError,),
    "PollFailedError": (RuntimeError,),
    "OperatorFailedError": (RuntimeError,),
    "OperatorNotFoundError": (AttributeError,),
    "ExecContextError": (ValueError,),
    "LinkError": (RuntimeError,),
    "RestrictedAccessError": (AttributeError,),
    "NotImplementedInQuartz": (NotImplementedError,),
    "ManifestError": (ValueError,),
    "FileFormatError": (ValueError,),
    "CompatError": (RuntimeError,),
}


@pytest.mark.parametrize("name", sorted(ERROR_BASES))
def test_error_class_bases(name):
    cls = getattr(E, name)
    for b in ERROR_BASES[name]:
        assert issubclass(cls, b)
    assert issubclass(cls, E.QuartzError)


def test_not_implemented_in_quartz_message_and_symbol():
    exc = E.NotImplementedInQuartz("bpy.foo")
    assert exc.symbol == "bpy.foo"
    assert str(exc) == "bpy.foo is not implemented in Quartz"


def test_not_implemented_in_quartz_detail():
    exc = E.NotImplementedInQuartz("bpy.foo", "because")
    assert str(exc) == "bpy.foo is not implemented in Quartz: because"


def test_manifest_error_fields():
    exc = E.ManifestError(("a", "b"), path="x/manifest.toml")
    assert exc.problems == ["a", "b"] and isinstance(exc.problems, list)
    assert exc.path == "x/manifest.toml"
    assert str(exc) == "a; b"


def test_manifest_error_default_path():
    assert E.ManifestError(["only"]).path == ""
    assert str(E.ManifestError(["only"])) == "only"



REEXPORTS = ("Struct StructMeta PropertyGroup builtin_struct IDRef PropertyDef BoolDef IntDef FloatDef StringDef "
             "EnumDef PointerDef CollectionDef EnumItem PropCollection GroupCollection PropArray IDPropertyGroup "
             "IDPropertyArray IDPropertyUIManager rna_idprop_ui_create rna_idprop_value_to_python "
             "rna_idprop_quote_path RNAStruct RNAProperty RNAEnumItem Description describe collect_annotations "
             "install_properties uninstall_properties define_property remove_property get_property "
             "iter_properties PropertyRef hooks datapath").split()


@pytest.mark.parametrize("name", REEXPORTS)
def test_rna_reexports(name):
    assert hasattr(R, name)


def test_rna_reexport_modules_are_modules():
    import quartz.rna.datapath
    import quartz.rna.hooks
    assert R.hooks is quartz.rna.hooks
    assert R.datapath is quartz.rna.datapath


def test_rna_reexport_identity():
    from quartz.rna import struct, properties, collections, idprops, rnainfo, description, annotations
    assert R.Struct is struct.Struct and R.PropertyDef is properties.PropertyDef
    assert R.PropArray is collections.PropArray and R.IDPropertyGroup is idprops.IDPropertyGroup
    assert R.RNAStruct is rnainfo.RNAStruct and R.describe is description.describe
    assert R.install_properties is annotations.install_properties
    assert R.PropertyRef is DP.PropertyRef



def test_deferred_slots():
    assert P._PropertyDeferred.__slots__ == ("function", "keywords", "_kind")


def test_deferred_observed_example():
    d = IntProperty(name="x", default=3)
    assert d.function is IntProperty
    assert d.keywords == {"name": "x", "default": 3}
    assert d._kind == "INT"


def test_deferred_repr():
    d = IntProperty(default=3)
    assert repr(d) == "<_PropertyDeferred, IntProperty, {'default': 3}>"


def test_deferred_keywords_only_passed():
    assert FloatProperty().keywords == {}


FACTORIES = [
    (BoolProperty, "BOOLEAN", "BoolProperty"), (BoolVectorProperty, "BOOLEAN_VECTOR", "BoolVectorProperty"),
    (IntProperty, "INT", "IntProperty"), (IntVectorProperty, "INT_VECTOR", "IntVectorProperty"),
    (FloatProperty, "FLOAT", "FloatProperty"), (FloatVectorProperty, "FLOAT_VECTOR", "FloatVectorProperty"),
    (StringProperty, "STRING", "StringProperty"),
]


@pytest.mark.parametrize("fn,kind,name", FACTORIES, ids=[f[2] for f in FACTORIES])
def test_factory_kind_and_function(fn, kind, name):
    d = fn(name="n")
    assert d.function is fn and d._kind == kind and d.keywords == {"name": "n"}
    assert P.FACTORY_NAMES[kind] == name


def test_factory_names_full():
    assert dict(P.FACTORY_NAMES) == {
        "BOOLEAN": "BoolProperty", "BOOLEAN_VECTOR": "BoolVectorProperty", "INT": "IntProperty",
        "INT_VECTOR": "IntVectorProperty", "FLOAT": "FloatProperty", "FLOAT_VECTOR": "FloatVectorProperty",
        "STRING": "StringProperty", "ENUM": "EnumProperty", "POINTER": "PointerProperty",
        "COLLECTION": "CollectionProperty"}


def _dump_props():
    d = json.loads((ROOT / "data" / "blender_api_dump.json").read_text(encoding="utf-8"))
    return {k: v for k, v in d["props"].items() if isinstance(v, dict) and k.endswith("Property") and k != "RemoveProperty"}


@pytest.mark.parametrize("factory", sorted(_dump_props()))
def test_property_kwargs_match_dump(factory):
    assert tuple(P.PROPERTY_KWARGS[factory]) == tuple(_dump_props()[factory]["kwargs"])


def test_native_kwargs_and_positional_param():
    assert P.NATIVE_KWARGS == frozenset({"meta"})
    assert dict(P.POSITIONAL_PARAM) == {"EnumProperty": "items", "PointerProperty": "type", "CollectionProperty": "type"}


def test_unexpected_kwarg_message():
    with pytest.raises(TypeError) as ei:
        IntProperty(bogus=1)
    assert "IntProperty() got an unexpected keyword argument 'bogus'" in str(ei.value)


def test_kwarg_of_other_factory_rejected():
    with pytest.raises(TypeError):
        BoolProperty(min=0)


def test_positional_not_allowed_message():
    with pytest.raises(TypeError) as ei:
        IntProperty(3)
    assert "IntProperty() takes 0 positional arguments" in str(ei.value)


def test_enum_positional_items():
    items = [("A", "a", "")]
    d = EnumProperty(items, name="e")
    assert d.keywords == {"items": items, "name": "e"}


def test_pointer_positional_type():
    d = PointerProperty(R.PropertyGroup)
    assert d.keywords == {"type": R.PropertyGroup}


def test_collection_positional_type():
    d = CollectionProperty(R.PropertyGroup)
    assert d.keywords == {"type": R.PropertyGroup}


def test_two_positionals_rejected():
    with pytest.raises(TypeError):
        EnumProperty([("A", "a", "")], [("B", "b", "")])


def test_positional_and_named_rejected():
    with pytest.raises(TypeError):
        EnumProperty([("A", "a", "")], items=[("B", "b", "")])


@pytest.mark.parametrize("fn", [EnumProperty, PointerProperty, CollectionProperty])
def test_required_arg_missing(fn):
    with pytest.raises(TypeError):
        fn(name="x")


def test_meta_accepted_by_default():
    d = IntProperty(meta={"group": "g"})
    assert d.keywords["meta"] == {"group": "g"}


def test_meta_rejected_when_not_allowed():
    with pytest.raises(TypeError) as ei:
        P.make_deferred(IntProperty, "INT", (), {"meta": {}}, allow_meta=False)
    assert "unexpected keyword argument 'meta'" in str(ei.value)


def test_make_deferred_direct():
    d = P.make_deferred(FloatProperty, "FLOAT", (), {"default": 1.0})
    assert d.function is FloatProperty and d._kind == "FLOAT" and d.keywords == {"default": 1.0}


def test_factories_do_not_validate_values():
    d = IntProperty(default="not an int", options={"BOGUS"})
    assert d.keywords["default"] == "not an int"


def test_float_defaults():
    p = build(FloatProperty())
    assert p.default == 0.0
    assert p.hard_min == pytest.approx(-3.402823e38, rel=1e-6) and p.hard_max == pytest.approx(3.402823e38, rel=1e-6)
    assert p.soft_min == pytest.approx(-3.402823e38, rel=1e-6) and p.soft_max == pytest.approx(3.402823e38, rel=1e-6)
    assert p.step == 3 and p.precision == 2


def test_int_defaults():
    p = build(IntProperty())
    assert p.default == 0
    assert p.hard_min == -2**31 and p.soft_min == -2**31
    assert p.hard_max == 2**31 - 1 and p.soft_max == 2**31 - 1
    assert p.step == 1


@pytest.mark.parametrize("fn", [BoolVectorProperty, IntVectorProperty, FloatVectorProperty])
def test_vector_default_size_3(fn):
    p = build(fn())
    assert p.size == (3,) and p.array_length == 3 and p.is_array


@pytest.mark.parametrize("fn", [BoolProperty, IntProperty, FloatProperty, StringProperty])
def test_common_defaults(fn):
    p = build(fn())
    assert p.options == frozenset({"ANIMATABLE"})
    assert p.subtype == "NONE"
    assert p.is_animatable


def test_float_unit_default():
    assert build(FloatProperty()).unit == "NONE"


def test_string_defaults():
    p = build(StringProperty())
    assert p.default == "" and p.maxlen == 0
    assert p.search_options == frozenset({"SUGGESTION"})


def test_enum_default_none_keyword():
    d = EnumProperty(items=[("A", "a", "")])
    assert "default" not in d.keywords


def test_meta_unknown_key_registration_error():
    with pytest.raises(E.RegistrationError):
        build(IntProperty(meta={"bogus": 1}))


@pytest.mark.parametrize("key,val", [("group", "g"), ("parent", "p"), ("widget", "SLIDER"), ("dirty", "DATA"),
                                     ("uid", 7), ("since", 2), ("readonly", False), ("doc", "d")])
def test_meta_known_keys_accepted(key, val):
    p = build(IntProperty(meta={key: val}))
    assert p.meta[key] == val


def test_remove_property_factory():
    Foo = one(IntProperty())
    P.RemoveProperty(Foo, attr="x")
    assert R.get_property(Foo, "x") is None



def test_hook_names():
    assert H.HOOK_NAMES == ("wrap_array", "current_context", "on_property_changed",
                            "on_type_property_defined", "on_type_property_removed", "note_missing", "repr_root")


def test_hook_defaults():
    H.reset()
    assert H.current_context() is None
    assert H.repr_root() == "quartz"
    assert H.note_missing("x") is None
    assert H.on_property_changed(object(), None) is None
    assert H.on_type_property_defined(object, "x") is None
    assert H.on_type_property_removed(object, "x") is None


def test_hook_default_wrap_array_is_proparray():
    H.reset()
    w = H.wrap_array(np.zeros(3, dtype=np.float32), None, None, lambda: None)
    assert isinstance(w, R.PropArray)


def test_hook_install_and_restore_default():
    H.install(repr_root=lambda: "bpy")
    assert H.repr_root() == "bpy"
    H.install(repr_root=None)
    assert H.repr_root() == "quartz"


def test_hook_install_only_named():
    H.install(current_context=lambda: "ctx")
    assert H.current_context() == "ctx" and H.repr_root() == "quartz"


def test_hook_install_unknown_name():
    with pytest.raises(TypeError):
        H.install(bogus=lambda: None)


def test_hook_reset():
    H.install(repr_root=lambda: "bpy", current_context=lambda: 1)
    H.reset()
    assert H.repr_root() == "quartz" and H.current_context() is None


def test_hook_snapshot_restore():
    snap = H.snapshot()
    assert isinstance(snap, dict) and set(snap) == set(H.HOOK_NAMES)
    H.install(repr_root=lambda: "bpy")
    H.restore(snap)
    assert H.repr_root() == "quartz"


def test_hook_on_property_changed_called():
    seen = []
    H.install(on_property_changed=lambda inst, pdef: seen.append(pdef.identifier))
    Foo = one(IntProperty())
    Foo().x = 2
    assert seen == ["x"]


def test_hook_wrap_array_used_for_arrays():
    H.install(wrap_array=lambda values, pdef, inst, on_write: ("W", tuple(values.tolist())))
    Foo = one(IntVectorProperty(default=(1, 2, 3)))
    assert Foo().x == ("W", (1, 2, 3))


def test_hook_current_context_passed_to_update():
    got = []
    H.install(current_context=lambda: "CTX")
    Foo = one(IntProperty(update=lambda self, ctx: got.append(ctx)))
    Foo().x = 1
    assert got == ["CTX"]


def test_hook_type_property_defined_and_removed():
    log = []
    H.install(on_type_property_defined=lambda c, i: log.append(("def", c.__name__, i)),
              on_type_property_removed=lambda c, i: log.append(("rem", c.__name__, i)))
    Foo = one(IntProperty())
    R.define_property(Foo, "y", IntProperty())
    R.remove_property(Foo, "y")
    assert log == [("def", "Foo", "y"), ("rem", "Foo", "y")]



def T(kind, value):
    return DP.PathToken(kind, value)


def test_parse_contract_example():
    assert DP.parse('modifiers["Bend"].angle[0]') == (T("ATTR", "modifiers"), T("KEY", "Bend"), T("ATTR", "angle"), T("INDEX", 0))


def test_parse_single_quote_key():
    assert DP.parse("a['k']") == (T("ATTR", "a"), T("KEY", "k"))


def test_parse_escaped_key():
    assert DP.parse('a["x\\"y\\\\z"]') == (T("ATTR", "a"), T("KEY", 'x"y\\z'))


def test_parse_empty():
    assert DP.parse("") == ()


def test_parse_dotted():
    assert DP.parse("a.b.c") == (T("ATTR", "a"), T("ATTR", "b"), T("ATTR", "c"))


@pytest.mark.parametrize("bad", ["a..b", "a[", "a[0", "1abc", "a[x]", "a.", 'a["k"', "a b", "a]"])
def test_parse_invalid(bad):
    with pytest.raises(ValueError) as ei:
        DP.parse(bad)
    assert f'invalid data path "{bad}"' in str(ei.value)


def test_pathtoken_frozen():
    t = T("ATTR", "a")
    with pytest.raises(Exception):
        t.kind = "KEY"


def test_format_tokens():
    assert DP.format([T("ATTR", "modifiers"), T("KEY", "Bend"), T("ATTR", "angle"), T("INDEX", 0)]) == 'modifiers["Bend"].angle[0]'


def test_format_escapes_key():
    assert DP.format([T("ATTR", "a"), T("KEY", 'q"b\\')]) == 'a["q\\"b\\\\"]'


def test_format_parse_roundtrip():
    toks = (T("ATTR", "a"), T("KEY", 'k"q'), T("INDEX", 3), T("ATTR", "b"))
    assert DP.parse(DP.format(toks)) == toks


def test_escape_identifier_observed():
    assert DP.escape_identifier('a"b\\c') == 'a\\"b\\\\c'


def test_escape_identifier_judge_fact():
    facts = json.loads((ROOT / "data" / "blender_facts_judge.json").read_text(encoding="utf-8"))
    assert DP.escape_identifier('a"b\\c') == facts["utils.escape_identifier"]


def test_unescape_identifier_inverse():
    for s in ['a"b\\c', "plain", '\\\\"', ""]:
        assert DP.unescape_identifier(DP.escape_identifier(s)) == s


def _graph():
    return SimpleNamespace(a=SimpleNamespace(b=[10, 20, 30], d={"k": SimpleNamespace(v=5)}))


def test_resolve_attr_index_key():
    g = _graph()
    assert DP.resolve(g, "a.b[1]") == 20
    assert DP.resolve(g, 'a.d["k"].v') == 5


def test_resolve_empty_path_returns_root():
    g = _graph()
    assert DP.resolve(g, "") is g


@pytest.mark.parametrize("path", ["a.missing", "a.b[99]", 'a.d["nope"]'])
def test_resolve_failure_message(path):
    with pytest.raises(ValueError) as ei:
        DP.resolve(_graph(), path)
    assert f'Path "{path}" could not be resolved' in str(ei.value)


def test_resolve_coerce_false_property_ref():
    Foo = one(IntProperty())
    f = Foo()
    ref = DP.resolve(f, "x", coerce=False)
    assert isinstance(ref, DP.PropertyRef) and ref == DP.PropertyRef(f, "x", None)


def test_resolve_coerce_false_array_index():
    Foo = one(FloatVectorProperty())
    f = Foo()
    assert DP.resolve(f, "x[1]", coerce=False) == DP.PropertyRef(f, "x", 1)


def test_resolve_coerce_true_returns_value():
    Foo = one(IntProperty(default=4))
    assert DP.resolve(Foo(), "x") == 4


def test_property_ref_slots_and_readonly():
    assert DP.PropertyRef.__slots__ == ("_q_struct", "_q_identifier", "_q_index")
    o = object()
    r = DP.PropertyRef(o, "x", 2)
    assert r.struct is o and r.identifier == "x" and r.index == 2
    with pytest.raises(AttributeError):
        r.struct = None
    with pytest.raises(AttributeError):
        r.identifier = "y"


def test_property_ref_default_index():
    assert DP.PropertyRef(object(), "x").index is None


def test_property_ref_eq_hash():
    o = object()
    a, b = DP.PropertyRef(o, "x", 1), DP.PropertyRef(o, "x", 1)
    assert a == b and hash(a) == hash(b) and {a: 1}[b] == 1
    assert a != DP.PropertyRef(o, "x", 2)
    assert a != DP.PropertyRef(o, "y", 1)
    assert a != DP.PropertyRef(object(), "x", 1)


def test_property_ref_eq_uses_identity_not_equality():
    a, b = [1], [1]
    assert DP.PropertyRef(a, "x") != DP.PropertyRef(b, "x")



def test_constants():
    assert PR.FLOAT_MAX == 3.4028234663852886e38
    assert PR.INT_MIN == -2**31 and PR.INT_MAX == 2**31 - 1


def test_option_flags():
    assert PR.OPTION_FLAGS == frozenset({"HIDDEN", "SKIP_SAVE", "SKIP_PRESET", "ANIMATABLE", "LIBRARY_EDITABLE",
                                         "PROPORTIONAL", "TEXTEDIT_UPDATE", "OUTPUT_PATH",
                                         "PATH_SUPPORTS_BLEND_RELATIVE", "PATH_SUPPORTS_TEMPLATES", "ENUM_FLAG"})


def test_override_flags():
    assert PR.OVERRIDE_FLAGS == frozenset({"LIBRARY_OVERRIDABLE", "NO_PROPERTY_NAME"})


def test_meta_keys():
    assert PR.META_KEYS == frozenset({"group", "parent", "enabled_if", "visible_if", "widget", "dirty", "uid",
                                      "since", "on_remove", "counts_user", "virtual_get", "virtual_set",
                                      "euler_order", "fixed_type_name", "readonly", "doc"})


def test_to_float32():
    assert PR.to_float32(0.1) == F32_01 and type(PR.to_float32(0.1)) is float
    assert PR.to_float32(1e12) == 999999995904.0


def test_judge_float32_fact():
    facts = json.loads((ROOT / "data" / "blender_facts_judge.json").read_text(encoding="utf-8"))
    assert PR.to_float32(0.1) == facts["math.float32"]



def test_enum_item_frozen_dataclass():
    it = R.EnumItem("A", "a", "d", "NONE", 0)
    assert (it.identifier, it.name, it.description, it.icon, it.value) == ("A", "a", "d", "NONE", 0)
    with pytest.raises(Exception):
        it.value = 3


def test_normalize_three_tuple_index_values():
    items = PR.normalize_enum_items([("A", "a", ""), ("B", "b", ""), ("C", "c", "")])
    assert [i.identifier for i in items] == ["A", "B", "C"]
    assert [i.value for i in items] == [0, 1, 2]
    assert all(isinstance(i, R.EnumItem) for i in items) and isinstance(items, tuple)


def test_normalize_flag_values():
    items = PR.normalize_enum_items([("A", "a", ""), ("B", "b", ""), ("C", "c", "")], is_flag=True)
    assert [i.value for i in items] == [1, 2, 4]


def test_normalize_icon_form():
    (it,) = PR.normalize_enum_items([("A", "a", "d", "MESH_DATA")])
    assert it.icon == "MESH_DATA" and it.value == 0


def test_normalize_five_tuple():
    items = PR.normalize_enum_items([("A", "a", "", "NONE", 5), ("B", "b", "", 0, 9)])
    assert [i.value for i in items] == [5, 9]


def test_normalize_four_tuple_number():
    (it,) = PR.normalize_enum_items([("A", "a", "", 42)])
    assert it.value == 42


def test_normalize_separator_ignored():
    items = PR.normalize_enum_items([("A", "a", ""), None, ("B", "b", "")])
    assert [i.identifier for i in items] == ["A", "B"]


def test_normalize_duplicate_identifier():
    with pytest.raises(ValueError):
        PR.normalize_enum_items([("A", "a", ""), ("A", "b", "")])



KIND_OF = [(PR.BoolDef, "BOOLEAN"), (PR.IntDef, "INT"), (PR.FloatDef, "FLOAT"), (PR.StringDef, "STRING"),
           (PR.EnumDef, "ENUM"), (PR.PointerDef, "POINTER"), (PR.CollectionDef, "COLLECTION")]


@pytest.mark.parametrize("cls,kind", KIND_OF, ids=[k for _, k in KIND_OF])
def test_def_classes_kind_classvar(cls, kind):
    assert issubclass(cls, PR.PropertyDef)
    assert cls.kind == kind


@pytest.mark.parametrize("fn,cls,kind", [(BoolVectorProperty, PR.BoolDef, "BOOLEAN"),
                                         (IntVectorProperty, PR.IntDef, "INT"),
                                         (FloatVectorProperty, PR.FloatDef, "FLOAT")])
def test_vector_pdef_kind_is_scalar_kind(fn, cls, kind):
    p = build(fn())
    assert isinstance(p, cls)
    assert p.kind == kind


@pytest.mark.parametrize("fn,cls", [(BoolProperty, PR.BoolDef), (IntProperty, PR.IntDef), (FloatProperty, PR.FloatDef),
                                    (StringProperty, PR.StringDef)])
def test_build_returns_def_class(fn, cls):
    assert isinstance(build(fn()), cls)


def test_common_attributes():
    class Owner(R.Struct):
        pass
    d = IntProperty(name="N", description="D", translation_context="CTX", tags={"T"}, override={"LIBRARY_OVERRIDABLE"})
    p = PR.build_property("x", d, Owner)
    assert p.identifier == "x" and p.owner is Owner and p.deferred is d
    assert p.name == "N" and p.description == "D" and p.translation_context == "CTX"
    assert p.tags == frozenset({"T"}) and p.override == frozenset({"LIBRARY_OVERRIDABLE"})
    assert isinstance(p.options, frozenset) and isinstance(p.override, frozenset) and isinstance(p.tags, frozenset)


def test_default_translation_context_and_name():
    p = build(IntProperty())
    assert p.name == "" and p.description == ""


def test_meta_is_mappingproxy():
    p = build(IntProperty(meta={"group": "g"}))
    assert isinstance(p.meta, MappingProxyType) and p.meta["group"] == "g"


def test_meta_empty_mappingproxy_when_absent():
    p = build(IntProperty())
    assert isinstance(p.meta, MappingProxyType) and len(p.meta) == 0


def test_size_scalar_and_2d():
    assert build(IntProperty()).size == () and build(IntProperty()).array_length == 0
    assert build(IntProperty()).is_array is False
    p = build(FloatVectorProperty(size=(2, 3)))
    assert p.size == (2, 3) and p.array_length == 6 and p.is_array


def test_flag_attributes_from_options():
    p = build(IntProperty(options={"HIDDEN", "SKIP_SAVE"}))
    assert p.is_hidden and p.is_skip_save and not p.is_animatable
    e = build(EnumProperty(items=[("A", "a", "")], options={"ENUM_FLAG"}))
    assert e.is_enum_flag


@pytest.mark.parametrize("kw,expected", [
    ({}, False),
    ({"get": lambda s: 1}, True),
    ({"get": lambda s: 1, "set": lambda s, v: None}, False),
    ({"meta": {"virtual_get": lambda s: 1}}, True),
    ({"meta": {"virtual_get": lambda s: 1, "virtual_set": lambda s, v: None}}, False),
    ({"meta": {"readonly": True}}, True),
])
def test_is_readonly_rules(kw, expected):
    assert build(IntProperty(**kw)).is_readonly is expected


def test_int_float_def_attributes():
    i = build(IntProperty(min=0, max=10, soft_min=2, soft_max=8, step=2))
    assert (i.hard_min, i.hard_max, i.soft_min, i.soft_max, i.step) == (0, 10, 2, 8, 2)
    f = build(FloatProperty(min=0, max=10, step=5, precision=4))
    assert (f.hard_min, f.hard_max, f.step, f.precision) == (0, 10, 5, 4)


def test_string_def_attributes():
    s = build(StringProperty(maxlen=8, search_options={"SORT"}))
    assert s.maxlen == 8 and s.search is None and s.search_options == frozenset({"SORT"})


def test_enum_def_attributes():
    e = build(EnumProperty(items=[("A", "a", ""), ("B", "b", "")], default="B"))
    assert e.default == "B" and e.is_dynamic is False
    assert [i.identifier for i in e.items_for(None)] == ["A", "B"]


def test_enum_dynamic_items():
    e = build(EnumProperty(items=lambda self, ctx: [("X", "x", ""), ("Y", "y", "")]))
    assert e.is_dynamic is True
    items = e.items_for(None, None)
    assert [i.identifier for i in items] == ["X", "Y"] and all(isinstance(i, R.EnumItem) for i in items)


def test_pointer_def_attributes():
    PG = register(type("PtrPG", (R.PropertyGroup,), {}))
    p = build(PointerProperty(type=PG))
    assert p.fixed_type is PG and p.poll is None and p.is_id_pointer is False
    assert p.counts_user is True and p.on_remove == "CLEAR"


def test_pointer_def_id_and_meta():
    FakeID = make_id_class()
    p = build(PointerProperty(type=FakeID, meta={"counts_user": False, "on_remove": "DELETE_OWNER"}))
    assert p.is_id_pointer is True and p.counts_user is False and p.on_remove == "DELETE_OWNER"


def test_collection_def_attributes():
    PG = register(type("ColPG", (R.PropertyGroup,), {}))
    p = build(CollectionProperty(type=PG))
    assert p.fixed_type is PG



def _reg_err(deferred, identifier="x"):
    class Owner(R.Struct):
        pass
    with pytest.raises(E.RegistrationError) as ei:
        PR.build_property(identifier, deferred, Owner)
    return ei.value


def test_build_error_message_and_cause():
    exc = _reg_err(IntProperty(options={"BOGUS"}), "count")
    assert 'bpy_struct "Owner" registration error: \'count\' IntProperty could not register' in str(exc)
    assert exc.__cause__ is not None


def test_build_error_enum_flag_on_non_enum():
    _reg_err(IntProperty(options={"ENUM_FLAG"}))


@pytest.mark.parametrize("deferred", [
    IntProperty(default="a"), IntProperty(default=2.5), FloatProperty(default="a"),
    BoolProperty(default="a"), StringProperty(default=5),
], ids=["int-str", "int-float", "float-str", "bool-str", "string-int"])
def test_build_error_default_wrong_type(deferred):
    _reg_err(deferred)


@pytest.mark.parametrize("deferred", [
    IntVectorProperty(size=3, default=(1, 2)), FloatVectorProperty(size=2, default=(1.0, 2.0, 3.0)),
    BoolVectorProperty(size=3, default=(True,)),
], ids=["int-short", "float-long", "bool-short"])
def test_build_error_default_wrong_size(deferred):
    _reg_err(deferred)


def test_build_error_enum_default_not_in_items():
    exc = _reg_err(EnumProperty(items=[("A", "a", "")], default="Z"))
    assert "EnumProperty could not register" in str(exc)


def test_build_error_enum_flag_default_not_set():
    _reg_err(EnumProperty(items=[("A", "a", "")], options={"ENUM_FLAG"}, default="A"))


def test_build_ok_enum_flag_default_set():
    p = build(EnumProperty(items=[("A", "a", ""), ("B", "b", "")], options={"ENUM_FLAG"}, default={"A", "B"}))
    assert set(p.default) == {"A", "B"}


def test_build_error_pointer_plain_class():
    class Plain:
        pass
    _reg_err(PointerProperty(type=Plain))


def test_build_error_pointer_unregistered_struct():
    class Unreg(R.PropertyGroup):
        pass
    _reg_err(PointerProperty(type=Unreg))


def test_build_ok_pointer_builtin_struct():
    @R.builtin_struct
    class RenderSettingsLike(R.Struct):
        pass
    assert build(PointerProperty(type=RenderSettingsLike)).fixed_type is RenderSettingsLike


def test_build_error_collection_unregistered():
    class Unreg(R.PropertyGroup):
        pass
    _reg_err(CollectionProperty(type=Unreg))


def test_build_error_unknown_meta_message():
    exc = _reg_err(FloatProperty(meta={"nope": 1}), "y")
    assert "'y' FloatProperty could not register" in str(exc)



def test_soft_limits_clamped_into_hard():
    p = build(IntProperty(min=0, max=10, soft_min=-5, soft_max=50))
    assert p.soft_min == 0 and p.soft_max == 10


def test_soft_limits_default_to_hard():
    p = build(FloatProperty(min=-1.0, max=2.0))
    assert p.soft_min == -1.0 and p.soft_max == 2.0


def test_int_default_clamped():
    Foo = one(IntProperty(default=50, max=10))
    assert Foo().x == 10


def test_float_default_clamped():
    Foo = one(FloatProperty(default=-5.0, min=0.0))
    assert Foo().x == 0.0


def test_vector_default_clamped():
    Foo = one(FloatVectorProperty(default=(5.0, 0.5, -5.0), min=0.0, max=1.0))
    assert list(Foo().x) == [1.0, 0.5, 0.0]



def test_storage_scalar_types():
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {
        "b": BoolProperty(), "i": IntProperty(), "f": FloatProperty(), "s": StringProperty()}}))
    f = Foo()
    f.b, f.i, f.f, f.s = True, 3, 0.1, "hi"
    assert f._p["b"] is True and f._p["i"] == 3 and type(f._p["i"]) is int
    assert f._p["f"] == F32_01 and type(f._p["f"]) is float
    assert f._p["s"] == "hi"


def test_storage_enum_identifier_and_flag_frozenset():
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {
        "e": EnumProperty(items=[("A", "a", ""), ("B", "b", "")]),
        "g": EnumProperty(items=[("A", "a", ""), ("B", "b", "")], options={"ENUM_FLAG"})}}))
    f = Foo()
    f.e = "B"
    f.g = {"A"}
    assert f._p["e"] == "B"
    assert isinstance(f._p["g"], frozenset) and f._p["g"] == frozenset({"A"})


@pytest.mark.parametrize("fn,dtype", [(BoolVectorProperty, np.bool_), (IntVectorProperty, np.int32), (FloatVectorProperty, np.float32)])
def test_storage_array_dtype(fn, dtype):
    Foo = one(fn(size=4))
    f = Foo()
    f.x
    arr = f._p["x"]
    assert isinstance(arr, np.ndarray) and arr.dtype == dtype and arr.shape == (4,)


def test_storage_array_2d_shape():
    Foo = one(FloatVectorProperty(size=(2, 3)))
    f = Foo()
    f.x = [[1, 2, 3], [4, 5, 6]]
    assert f._p["x"].shape == (2, 3) and f._p["x"].dtype == np.float32


def test_storage_id_pointer_strong():
    FakeID = make_id_class()
    Foo = one(PointerProperty(type=FakeID))
    f, t = Foo(), FakeID()
    f.x = t
    assert f._p["x"] is t and f.x is t


def test_storage_pg_pointer_lazy_and_kept():
    PG = register(type("InnerPG", (R.PropertyGroup,), {"__annotations__": {"v": IntProperty()}}))
    Foo = one(PointerProperty(type=PG))
    f = Foo()
    assert "x" not in f._p
    c = f.x
    assert isinstance(c, PG) and f.x is c and f._p["x"] is c
    assert c._q_owner is f and c._q_path == "x"


def test_storage_collection_lazy_groupcollection():
    PG = register(type("ItemPG", (R.PropertyGroup,), {}))
    Foo = one(CollectionProperty(type=PG))
    f = Foo()
    c = f.x
    assert isinstance(c, R.GroupCollection) and f.x is c and c.item_type is PG



def test_class_access_returns_deferred():
    d = IntProperty(default=3)
    Foo = one(d)
    assert Foo.x is d


def test_virtual_get_scalar_float32():
    Foo = one(FloatProperty(meta={"virtual_get": lambda s: 0.1}))
    assert Foo().x == F32_01


def test_virtual_get_other_kinds_as_is():
    Foo = one(StringProperty(meta={"virtual_get": lambda s: "computed"}))
    assert Foo().x == "computed"


def test_virtual_get_array_wrapped_and_virtual_set_called():
    store = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    got = []
    Foo = one(FloatVectorProperty(meta={"virtual_get": lambda s: store,
                                        "virtual_set": lambda s, v: got.append(np.array(v).tolist())}))
    f = Foo()
    w = f.x
    assert isinstance(w, R.PropArray) and list(w) == [1.0, 2.0, 3.0]
    w[0] = 9.0
    assert got and got[-1][0] == 9.0


def test_virtual_get_array_without_set_write_component_raises():
    store = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    Foo = one(FloatVectorProperty(meta={"virtual_get": lambda s: store}))
    w = Foo().x
    with pytest.raises(E.ReadOnlyError):
        w[0] = 5.0


def test_user_get_and_get_transform():
    Foo = one(IntProperty(get=lambda s: 5, get_transform=lambda s, v, is_set: v + 1))
    assert Foo().x == 6


def test_get_transform_on_stored_value():
    calls = []
    Foo = one(IntProperty(default=2, get_transform=lambda s, v, is_set: (calls.append(is_set), v * 10)[1]))
    f = Foo()
    assert f.x == 20
    f.x = 3
    assert f.x == 30 and calls == [False, True]


def test_enum_get_set_observed():
    facts = json.loads((ROOT / "data" / "blender_facts_judge.json").read_text(encoding="utf-8"))["props.enum_get_set"]
    log, store = [], {"v": 1}

    def g(self):
        log.append(("get",))
        return store["v"]

    def s(self, value):
        log.append(("set", value))
        store["v"] = value
    Foo = one(EnumProperty(items=[("A", "a", ""), ("B", "b", ""), ("C", "c", "", 0, 7)], get=g, set=s))
    f = Foo()
    out = {"read": f.x}
    f.x = "C"
    out["after_set"] = f.x
    assert out["read"] == facts["read"] and out["after_set"] == facts["after_set"]
    assert [list(e) for e in log] == facts["log"]


def test_enum_flag_get_bitmask_to_set():
    Foo = one(EnumProperty(items=[("A", "a", ""), ("B", "b", ""), ("C", "c", "")], options={"ENUM_FLAG"},
                           get=lambda s: 5, set=lambda s, v: None))
    assert Foo().x == {"A", "C"}


def test_enum_flag_set_bitmask_to_callback():
    got = []
    Foo = one(EnumProperty(items=[("A", "a", ""), ("B", "b", ""), ("C", "c", "")], options={"ENUM_FLAG"},
                           get=lambda s: 0, set=lambda s, v: got.append(v)))
    Foo().x = {"A", "C"}
    assert got == [5]


def test_array_default_materialized_not_set():
    Foo = one(FloatVectorProperty(default=(1.0, 2.0, 3.0)))
    f = Foo()
    w = f.x
    assert "x" in f._p and isinstance(f._p["x"], np.ndarray)
    assert not f.is_property_set("x")
    w[1] = 7.0
    assert f.x[1] == 7.0


def test_array_read_returns_proparray_with_python_scalars():
    Foo = one(FloatVectorProperty(default=(0.1, 0.0, 0.0)))
    w = Foo().x
    assert isinstance(w, R.PropArray)
    assert w[0] == F32_01 and type(w[0]) is float


def test_enum_flag_read_returns_new_set():
    Foo = one(EnumProperty(items=[("A", "a", "")], options={"ENUM_FLAG"}))
    f = Foo()
    a = f.x
    assert isinstance(a, set) and a == set()
    a.add("A")
    assert f.x == set() and f.x is not f.x


def test_scalar_read_types():
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {
        "i": IntProperty(default=3), "f": FloatProperty(default=1.5), "b": BoolProperty(default=True)}}))
    f = Foo()
    assert type(f.i) is int and type(f.f) is float and f.b is True


def test_float_default_float32_at_rest():
    Foo = one(FloatProperty(default=0.1))
    assert Foo().x == F32_01



def test_readonly_write_message():
    Foo = one(IntProperty(get=lambda s: 1))
    with pytest.raises(E.ReadOnlyError) as ei:
        Foo().x = 2
    assert 'bpy_struct: attribute "x" from "Foo" is read-only' in str(ei.value)


def test_meta_readonly_write_raises():
    Foo = one(IntProperty(meta={"readonly": True}))
    with pytest.raises(E.ReadOnlyError):
        Foo().x = 2


def test_pg_pointer_write_readonly():
    PG = register(type("InnerPG", (R.PropertyGroup,), {}))
    Foo = one(PointerProperty(type=PG))
    f = Foo()
    assert R.get_property(Foo, "x").is_readonly
    with pytest.raises(E.ReadOnlyError):
        f.x = PG()


def test_collection_write_readonly():
    PG = register(type("ItemPG", (R.PropertyGroup,), {}))
    Foo = one(CollectionProperty(type=PG))
    assert R.get_property(Foo, "x").is_readonly
    with pytest.raises(E.ReadOnlyError):
        Foo().x = []


def test_set_transform_result_recoerced():
    seen = []
    Foo = one(IntProperty(max=10, set_transform=lambda s, v, cur, is_set: (seen.append((v, cur, is_set)), v * 100)[1]))
    f = Foo()
    f.x = 2
    assert f.x == 10 and seen == [(2, 0, False)]


def test_user_set_scalar_receives_coerced_value():
    got = []
    Foo = one(FloatProperty(get=lambda s: 0.0, set=lambda s, v: got.append(v)))
    Foo().x = 3
    assert got == [3.0] and type(got[0]) is float


def test_user_set_array_receives_tuple():
    got = []
    Foo = one(IntVectorProperty(get=lambda s: (0, 0, 0), set=lambda s, v: got.append(v)))
    Foo().x = [1, 2, 3]
    assert got == [(1, 2, 3)] and isinstance(got[0], tuple)


def test_user_set_2d_array_receives_tuple_of_tuples():
    got = []
    Foo = one(FloatVectorProperty(size=(2, 2), get=lambda s: ((0, 0), (0, 0)), set=lambda s, v: got.append(v)))
    Foo().x = [1, 2, 3, 4]
    assert got == [((1.0, 2.0), (3.0, 4.0))] and isinstance(got[0][0], tuple)


def test_virtual_set_receives_coerced():
    got = []
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {
        "f": FloatProperty(meta={"virtual_get": lambda s: 0.0, "virtual_set": lambda s, v: got.append(("f", v))}),
        "e": EnumProperty(items=[("A", "a", ""), ("B", "b", "")],
                          meta={"virtual_get": lambda s: "A", "virtual_set": lambda s, v: got.append(("e", v))}),
        "g": EnumProperty(items=[("A", "a", ""), ("B", "b", "")], options={"ENUM_FLAG"},
                          meta={"virtual_get": lambda s: set(), "virtual_set": lambda s, v: got.append(("g", v))}),
        "a": FloatVectorProperty(meta={"virtual_get": lambda s: np.zeros(3, np.float32),
                                       "virtual_set": lambda s, v: got.append(("a", v))}),
    }}))
    f = Foo()
    f.f = 1
    f.e = "B"
    f.g = {"A"}
    f.a = (1, 2, 3)
    d = dict(got)
    assert d["f"] == 1.0 and type(d["f"]) is float
    assert d["e"] == "B"
    assert isinstance(d["g"], (set, frozenset)) and set(d["g"]) == {"A"}
    assert isinstance(d["a"], np.ndarray) and d["a"].tolist() == [1.0, 2.0, 3.0]


def test_array_write_in_place_live_wrapper():
    Foo = one(FloatVectorProperty())
    f = Foo()
    w = f.x
    arr = f._p["x"]
    f.x = (1.0, 2.0, 3.0)
    assert f._p["x"] is arr
    assert list(w) == [1.0, 2.0, 3.0]


def test_write_marks_set():
    Foo = one(IntProperty())
    f = Foo()
    f.x = 1
    assert "x" in f._p_set and f.is_property_set("x")


def test_write_step_order():
    order = []

    class Foo(R.Struct):
        x: IntProperty(update=lambda self, ctx: order.append("update"))

        def _q_on_change(self, pdef):
            order.append(("on_change", "x" in self._p_set))
    register(Foo)
    H.install(on_property_changed=lambda inst, pdef: order.append("hook"))
    Foo().x = 1
    assert order == [("on_change", True), "hook", "update"]


def test_update_always_called_even_same_value_and_clamped():
    calls = []
    Foo = one(IntProperty(max=5, update=lambda s, c: calls.append(s.x)))
    f = Foo()
    f.x = 1
    f.x = 1
    f.x = 99
    assert calls == [1, 1, 5]


def test_update_exception_printed_not_propagated(capsys):
    def boom(self, ctx):
        raise RuntimeError("update boom")
    Foo = one(IntProperty(update=boom))
    f = Foo()
    f.x = 3
    assert f.x == 3
    assert "update boom" in capsys.readouterr().err


def test_component_write_via_wrapper_reclamps_and_updates():
    calls = []
    Foo = one(IntVectorProperty(max=10, update=lambda s, c: calls.append(1)))
    f = Foo()
    f.x[0] = 100
    assert f.x[0] == 10 and calls == [1]
    assert f.is_property_set("x")


def test_delete_raises_attribute_error():
    Foo = one(IntProperty())
    f = Foo()
    with pytest.raises(AttributeError):
        del f.x



def _foo(deferred):
    return one(deferred)()


@pytest.mark.parametrize("v,expected", [(True, True), (False, False), (np.bool_(True), True), (1, True), (0, False)])
def test_bool_accepts(v, expected):
    f = _foo(BoolProperty())
    f.x = v
    assert f.x is expected


def test_bool_rejects_other_int_message_observed():
    f = _foo(BoolProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 2
    assert "Foo.x expected True/False or 0/1, not int" in str(ei.value)


def test_bool_rejects_str():
    f = _foo(BoolProperty())
    with pytest.raises(E.PropertyTypeError):
        f.x = "yes"


def test_int_from_bool_observed():
    f = _foo(IntProperty())
    f.x = True
    assert f.x == 1 and type(f.x) is int


def test_int_numpy_integer():
    f = _foo(IntProperty())
    f.x = np.int64(7)
    assert f.x == 7 and type(f.x) is int


def test_int_clamped():
    f = _foo(IntProperty(min=-3, max=3))
    f.x = 10
    assert f.x == 3
    f.x = -10
    assert f.x == -3


def test_int_rejects_float_observed():
    f = _foo(IntProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 2.0
    assert "Foo.x expected an int type, not float" in str(ei.value)


def test_int_rejects_str():
    f = _foo(IntProperty())
    with pytest.raises(E.PropertyTypeError):
        f.x = "3"


def test_float_from_int_observed():
    f = _foo(FloatProperty())
    f.x = 3
    assert f.x == 3.0 and type(f.x) is float


def test_float_value_0_1_observed():
    f = _foo(FloatProperty())
    f.x = 0.1
    assert f.x == F32_01


def test_float_from_bool_and_numpy():
    f = _foo(FloatProperty())
    f.x = True
    assert f.x == 1.0
    f.x = np.float64(0.5)
    assert f.x == 0.5


def test_float_rejects_str_message():
    f = _foo(FloatProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = "x"
    assert "Foo.x expected a float type, not str" in str(ei.value)


def test_float_clamped_and_rounded():
    f = _foo(FloatProperty(min=0.0, max=1.0))
    f.x = 5
    assert f.x == 1.0
    f.x = 0.3
    assert f.x == float(np.float32(0.3))


def test_string_accepts_str():
    f = _foo(StringProperty())
    f.x = "abc"
    assert f.x == "abc"


def test_string_rejects_bytes_by_default_message():
    f = _foo(StringProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = b"abc"
    assert "Foo.x expected a string type, not bytes" in str(ei.value)


def test_string_rejects_int_message():
    f = _foo(StringProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 5
    assert "Foo.x expected a string type, not int" in str(ei.value)


def test_byte_string_accepts_bytes():
    f = _foo(StringProperty(subtype="BYTE_STRING"))
    f.x = b"abc"
    assert f.x in ("abc", b"abc")


def test_string_maxlen_multibyte_observed():
    f = _foo(StringProperty(maxlen=5))
    f.x = "Ã" * 6
    assert f.x == "ÃÃ"


def test_string_maxlen_ascii():
    f = _foo(StringProperty(maxlen=3))
    f.x = "abcdef"
    assert len(f.x.encode("utf-8")) <= 3 and "abcdef".startswith(f.x)


def test_enum_accepts_identifier():
    f = _foo(EnumProperty(items=[("A", "a", ""), ("B", "b", "")]))
    f.x = "B"
    assert f.x == "B"


def test_enum_default_first_item_when_none():
    f = _foo(EnumProperty(items=[("A", "a", ""), ("B", "b", "")]))
    assert f.x == "A"


def test_enum_rejects_message_observed():
    f = _foo(EnumProperty(items=[("A", "a", ""), ("B", "b", "")]))
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = "Z"
    assert "enum \"Z\" not found in ('A', 'B')" in str(ei.value)


def test_enum_dynamic_coercion_uses_items_for():
    f = _foo(EnumProperty(items=lambda self, ctx: [("P", "p", ""), ("Q", "q", "")]))
    f.x = "Q"
    assert f.x == "Q"
    with pytest.raises(E.PropertyTypeError):
        f.x = "A"


def test_enum_flag_accepts_set_frozenset():
    f = _foo(EnumProperty(items=[("A", "a", ""), ("B", "b", "")], options={"ENUM_FLAG"}))
    f.x = {"A"}
    assert f.x == {"A"}
    f.x = frozenset({"A", "B"})
    assert f.x == {"A", "B"}


def test_enum_flag_rejects_str_expected_set():
    f = _foo(EnumProperty(items=[("A", "a", "")], options={"ENUM_FLAG"}))
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = "A"
    assert "expected a set" in str(ei.value)


def test_enum_flag_rejects_list():
    f = _foo(EnumProperty(items=[("A", "a", "")], options={"ENUM_FLAG"}))
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = ["A"]
    assert "expected a set" in str(ei.value)


def test_enum_flag_invalid_member():
    f = _foo(EnumProperty(items=[("A", "a", ""), ("B", "b", "")], options={"ENUM_FLAG"}))
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = {"Z"}
    assert "enum \"Z\" not found in ('A', 'B')" in str(ei.value)


def test_pointer_none_and_instance():
    FakeID = make_id_class()
    f = _foo(PointerProperty(type=FakeID))
    t = FakeID()
    f.x = t
    assert f.x is t
    f.x = None
    assert f.x is None


def test_pointer_wrong_type_message_observed():
    FakeID = make_id_class()
    f = _foo(PointerProperty(type=FakeID))
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 5
    assert "Foo.x expected a FakeID type, not int" in str(ei.value)


def test_pointer_poll_false_value_error():
    FakeID = make_id_class()
    f = _foo(PointerProperty(type=FakeID, poll=lambda self, v: False))
    with pytest.raises(E.PropertyValueError):
        f.x = FakeID()


def test_pointer_poll_true_ok():
    FakeID = make_id_class()
    seen = []
    f = _foo(PointerProperty(type=FakeID, poll=lambda self, v: (seen.append(v), True)[1]))
    t = FakeID()
    f.x = t
    assert f.x is t and seen == [t]


def test_array_wrong_size_message_observed():
    f = _foo(FloatVectorProperty())
    with pytest.raises(E.PropertyValueError) as ei:
        f.x = (1.0, 2.0)
    assert "bpy_struct: item.attr = val: sequences of dimension 0 should contain 3 items, not 2" in str(ei.value)


def test_array_2d_nested_or_flat():
    f = _foo(FloatVectorProperty(size=(2, 2)))
    f.x = [[1, 2], [3, 4]]
    assert np.asarray(f.x).tolist() == [[1.0, 2.0], [3.0, 4.0]]
    f.x = [4, 3, 2, 1]
    assert np.asarray(f.x).tolist() == [[4.0, 3.0], [2.0, 1.0]]


def test_array_rejects_str():
    f = _foo(IntVectorProperty(size=3))
    with pytest.raises(TypeError):
        f.x = "abc"


def test_array_element_coerced_as_scalar_int_rejects_float():
    f = _foo(IntVectorProperty())
    with pytest.raises(E.PropertyTypeError):
        f.x = (1, 2.0, 3)


def test_array_element_bool_rejects_2():
    f = _foo(BoolVectorProperty())
    with pytest.raises(E.PropertyTypeError):
        f.x = (1, 2, 0)


def test_array_float_clamp_and_float32():
    f = _foo(FloatVectorProperty(min=0.0, max=1.0))
    f.x = (5, -5, 0.1)
    assert list(f.x) == [1.0, 0.0, F32_01]


def test_array_accepts_ndarray_any_dtype():
    f = _foo(IntVectorProperty())
    f.x = np.array([1, 2, 3], dtype=np.int64)
    assert list(f.x) == [1, 2, 3]



PREFIX = "bpy_struct: item.attr = val: "


def test_prefix_int_from_float_observed():
    facts = json.loads((ROOT / "data" / "blender_facts_judge.json").read_text(encoding="utf-8"))["props.pg_attrs"]
    f = _foo(IntProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 2.0
    expected = facts["int_from_float"].split("TypeError: ", 1)[1].replace("QZPROBE_PG_attr", "Foo")
    assert expected in str(ei.value)


def test_prefix_bool_observed():
    f = _foo(BoolProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 2
    assert PREFIX + "Foo.x expected True/False or 0/1, not int" in str(ei.value)


def test_prefix_float():
    f = _foo(FloatProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = "x"
    assert PREFIX in str(ei.value)


def test_prefix_string():
    f = _foo(StringProperty())
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 1
    assert PREFIX in str(ei.value)


def test_prefix_enum():
    f = _foo(EnumProperty(items=[("A", "a", "")]))
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = "Z"
    assert PREFIX in str(ei.value)


def test_prefix_pointer():
    FakeID = make_id_class()
    f = _foo(PointerProperty(type=FakeID))
    with pytest.raises(E.PropertyTypeError) as ei:
        f.x = 1
    assert PREFIX in str(ei.value)



def test_coerce_without_inst():
    p = build(IntProperty(max=5))
    assert p.coerce(10) == 5


def test_default_value_scalar():
    assert build(IntProperty(default=3)).default_value() == 3
    assert build(FloatProperty(default=0.1)).default_value() == F32_01


def test_read_raw_default_and_stored():
    Foo = one(IntProperty(default=4))
    f = Foo()
    p = R.get_property(Foo, "x")
    assert p.read_raw(f) == 4
    f.x = 6
    assert p.read_raw(f) == 6


def test_write_raw_no_callbacks():
    calls = []
    H.install(on_property_changed=lambda i, p: calls.append("hook"))
    Foo = one(IntProperty(update=lambda s, c: calls.append("upd")))
    f = Foo()
    R.get_property(Foo, "x").write_raw(f, 9)
    assert f.x == 9 and calls == []


def test_clone_for():
    class Other(R.Struct):
        pass
    Foo = one(IntProperty(default=2))
    p = R.get_property(Foo, "x")
    c = p.clone_for(Other)
    assert c is not p and c.owner is Other and p.owner is Foo
    assert c.identifier == "x" and c.default == 2 and type(c) is type(p)



def test_rna_dict_int():
    d = build(IntProperty(default=3, min=0, max=10)).to_rna_dict()
    assert d["type"] == "INT" and d["subtype"] == "NONE" and "unit" not in d
    assert d["default"] == 3 and d["min"] == 0 and d["max"] == 10
    assert d["soft_min"] == 0 and d["soft_max"] == 10 and d["step"] == 1
    assert "precision" not in d and "array_length" not in d


def test_rna_dict_flags_are_names():
    d = build(IntProperty()).to_rna_dict()
    assert all(isinstance(x, str) for x in d["flags"])
    assert "is_animatable" in d["flags"] and "is_readonly" not in d["flags"]


@pytest.mark.parametrize("kw,flag", [({"options": {"HIDDEN"}}, "is_hidden"), ({"options": {"SKIP_SAVE"}}, "is_skip_save"),
                                     ({"get": lambda s: 1}, "is_readonly")])
def test_rna_dict_flags_names_present(kw, flag):
    assert flag in build(IntProperty(**kw)).to_rna_dict()["flags"]


def test_rna_dict_flags_enum_flag():
    d = build(EnumProperty(items=[("A", "a", "")], options={"ENUM_FLAG"})).to_rna_dict()
    assert "is_enum_flag" in d["flags"]


def test_rna_dict_float_unit_and_precision():
    d = build(FloatProperty(unit="LENGTH", precision=4)).to_rna_dict()
    assert d["unit"] == "LENGTH" and d["precision"] == 4 and d["type"] == "FLOAT"
    assert "unit" not in build(FloatProperty()).to_rna_dict()


def test_rna_dict_float_limits_float32():
    d = build(FloatProperty(min=-1e12, max=1e12)).to_rna_dict()
    assert d["max"] == 999999995904.0 and d["min"] == -999999995904.0
    assert d["soft_max"] == 999999995904.0


def test_rna_dict_float_default_float32():
    assert build(FloatProperty(default=0.1)).to_rna_dict()["default"] == F32_01


def test_rna_dict_vector():
    d = build(FloatVectorProperty(default=(1.0, 2.0, 3.0))).to_rna_dict()
    assert d["type"] == "FLOAT" and d["array_length"] == 3 and "array_dimensions" not in d
    assert d["default"] == [1.0, 2.0, 3.0]


def test_rna_dict_2d():
    d = build(FloatVectorProperty(size=(2, 2))).to_rna_dict()
    assert d["array_length"] == 4 and list(d["array_dimensions"]) == [2, 2]
    assert d["default"] == [0.0] * 4


def test_rna_dict_bool_vector_type():
    assert build(BoolVectorProperty()).to_rna_dict()["type"] == "BOOLEAN"


def test_rna_dict_enum_static_and_dynamic():
    d = build(EnumProperty(items=[("A", "a", ""), ("B", "b", "")], default="B")).to_rna_dict()
    assert d["type"] == "ENUM" and d["items"] == ["A", "B"] and d["default"] == "B"
    assert "items" not in build(EnumProperty(items=lambda s, c: [])).to_rna_dict()


def test_rna_dict_string_length_max():
    assert build(StringProperty(maxlen=5)).to_rna_dict()["length_max"] == 5
    d = build(StringProperty()).to_rna_dict()
    assert "length_max" not in d and d["type"] == "STRING" and d["default"] == ""


def test_rna_dict_pointer_fixed_type():
    PG = register(type("RnaPG", (R.PropertyGroup,), {}))
    assert build(PointerProperty(type=PG)).to_rna_dict()["fixed_type"] == "RnaPG"
    assert build(PointerProperty(type=PG, meta={"fixed_type_name": "Object"})).to_rna_dict()["fixed_type"] == "Object"
    d = build(CollectionProperty(type=PG)).to_rna_dict()
    assert d["fixed_type"] == "RnaPG" and d["type"] == "COLLECTION"


def test_rna_dict_pointer_no_min_max():
    PG = register(type("RnaPG2", (R.PropertyGroup,), {}))
    d = build(PointerProperty(type=PG)).to_rna_dict()
    assert "min" not in d and d["type"] == "POINTER"



class Item:
    def __init__(self, name, v, vec=(0.0, 0.0)):
        self.name, self.v, self.vec = name, v, list(vec)


class ListColl(R.PropCollection):
    def __init__(self, items, **kw):
        super().__init__(**kw)
        self._list = items

    def _q_items(self):
        return self._list


def _coll():
    return ListColl([Item("a", 1, (1, 2)), Item("b", 2, (3, 4)), Item("c", 3, (5, 6))])


def test_collection_len_iter_bool():
    c = _coll()
    assert len(c) == 3 and [i.name for i in c] == ["a", "b", "c"] and bool(c)
    assert not bool(ListColl([]))


def test_collection_getitem_int_neg():
    c = _coll()
    assert c[0].name == "a" and c[-1].name == "c"
    with pytest.raises(IndexError):
        c[3]
    with pytest.raises(IndexError):
        c[-4]


def test_collection_getitem_str_and_message_observed():
    c = _coll()
    assert c["b"].v == 2
    with pytest.raises(KeyError) as ei:
        c["zz"]
    assert 'bpy_prop_collection[key]: key "zz" not found' in str(ei.value)


def test_collection_getitem_slice_list():
    s = _coll()[0:2]
    assert isinstance(s, list) and [i.name for i in s] == ["a", "b"]


def test_collection_contains():
    c = _coll()
    assert "a" in c and "zz" not in c
    assert c[1] in c and Item("a", 1) not in c


def test_collection_get_find():
    c = _coll()
    assert c.get("b").v == 2 and c.get("zz") is None and c.get("zz", 5) == 5
    assert c.find("c") == 2 and c.find("zz") == -1


def test_collection_keys_values_items():
    c = _coll()
    assert c.keys() == ["a", "b", "c"]
    assert [i.v for i in c.values()] == [1, 2, 3]
    assert [(k, i.v) for k, i in c.items()] == [("a", 1), ("b", 2), ("c", 3)]


def test_collection_default_q_key():
    assert R.PropCollection._q_key(R.PropCollection(), SimpleNamespace(name="n")) == "n"
    assert R.PropCollection._q_key(R.PropCollection(), object()) is None


def test_collection_foreach_get_list_and_ndarray():
    c = _coll()
    seq = [0] * 3
    c.foreach_get("v", seq)
    assert seq == [1, 2, 3]
    arr = np.zeros(6, dtype=np.float32)
    c.foreach_get("vec", arr)
    assert arr.tolist() == [1, 2, 3, 4, 5, 6]


def test_collection_foreach_set():
    c = _coll()
    c.foreach_set("v", np.array([7, 8, 9], dtype=np.int64))
    assert [i.v for i in c] == [7, 8, 9]
    c.foreach_set("vec", [0.5] * 6)
    assert c[2].vec == [0.5, 0.5]


def test_collection_foreach_size_mismatch():
    c = _coll()
    with pytest.raises(E.PropertyValueError) as ei:
        c.foreach_get("v", [0] * 2)
    assert "foreach_get/set: sequence size mismatch" in str(ei.value)
    with pytest.raises(E.PropertyValueError):
        c.foreach_set("v", [0] * 4)


def test_collection_repr_observed():
    assert repr(_coll()) == "<bpy_collection[3], ListColl>"


def test_collection_path_and_id_data_attrs():
    c = ListColl([])
    assert c.id_data is None
    assert hasattr(c, "rna_type") and hasattr(c, "path_from_id")


def _owner_with_items():
    PG = register(type("ItemPG", (R.PropertyGroup,), {"__annotations__": {"v": IntProperty()}}))
    Foo = one(CollectionProperty(type=PG), name="items")
    return Foo(), PG


def test_group_collection_add():
    f, PG = _owner_with_items()
    a = f.items.add()
    b = f.items.add()
    assert isinstance(a, PG) and a._q_owner is f and b._q_owner is f
    assert a._q_path == "items[0]" and b._q_path == "items[1]"
    assert f.is_property_set("items") and len(f.items) == 2


def test_group_collection_item_type_and_init():
    gc = R.GroupCollection(R.PropertyGroup, owner=None, path="p")
    assert gc.item_type is R.PropertyGroup and len(gc) == 0


def test_group_collection_remove_reindex():
    f, PG = _owner_with_items()
    a, b, c = f.items.add(), f.items.add(), f.items.add()
    f.items.remove(0)
    assert list(f.items) == [b, c] and b._q_path == "items[0]" and c._q_path == "items[1]"
    with pytest.raises(IndexError):
        f.items.remove(5)


def test_group_collection_clear_move():
    f, PG = _owner_with_items()
    a, b, c = f.items.add(), f.items.add(), f.items.add()
    f.items.move(0, 2)
    assert list(f.items) == [b, c, a] and a._q_path == "items[2]" and b._q_path == "items[0]"
    f.items.clear()
    assert len(f.items) == 0


def test_group_collection_name_keys():
    f, PG = _owner_with_items()
    a = f.items.add()
    a.name = "first"
    assert f.items["first"] is a and f.items.keys() == ["first"]


def _parr(values, cb=None, owner=None, pdef=None):
    return R.PropArray(np.array(values, dtype=np.float32), on_write=cb, owner=owner, pdef=pdef)


def test_proparray_len_iter_getitem():
    a = _parr([1.0, 2.0, 3.0])
    assert len(a) == 3 and list(a) == [1.0, 2.0, 3.0] and all(type(x) is float for x in a)
    assert a[1] == 2.0 and type(a[1]) is float and a[-1] == 3.0


def test_proparray_int_bool_python_scalars():
    ai = R.PropArray(np.array([1, 2], dtype=np.int32))
    ab = R.PropArray(np.array([True, False]))
    assert type(ai[0]) is int and type(list(ai)[1]) is int
    assert ab[0] is True and list(ab) == [True, False]


def test_proparray_slice_tuple():
    a = _parr([1.0, 2.0, 3.0])
    assert a[0:2] == (1.0, 2.0) and isinstance(a[0:2], tuple)


def test_proparray_setitem_calls_on_write():
    calls = []
    a = _parr([1.0, 2.0, 3.0], cb=lambda: calls.append(1))
    a[0] = 5.0
    assert a[0] == 5.0 and calls == [1]
    a[0:2] = (7.0, 8.0)
    assert list(a) == [7.0, 8.0, 3.0] and calls == [1, 1]


def test_proparray_setitem_writes_view():
    data = np.zeros(3, dtype=np.float32)
    a = R.PropArray(data)
    a[2] = 4.0
    assert data[2] == 4.0


def test_proparray_eq():
    a = _parr([1.0, 2.0, 3.0])
    assert a == [1.0, 2.0, 3.0] and a == (1, 2, 3) and not (a == [1, 2]) and not (a == [1, 2, 4])


def test_proparray_array_protocol():
    a = _parr([1.0, 2.0])
    arr = np.asarray(a)
    assert arr.dtype == np.float32 and arr.tolist() == [1.0, 2.0]
    assert np.array(a, dtype=np.float64).dtype == np.float64


def test_proparray_foreach_and_to_list():
    calls = []
    a = _parr([1.0, 2.0, 3.0], cb=lambda: calls.append(1))
    out = [0.0] * 3
    a.foreach_get(out)
    assert out == [1.0, 2.0, 3.0]
    a.foreach_set([4, 5, 6])
    assert a.q_to_list() == [4.0, 5.0, 6.0] and isinstance(a.q_to_list(), list)
    assert calls


def test_proparray_2d():
    a = R.PropArray(np.arange(6, dtype=np.float32).reshape(2, 3))
    assert len(a) == 2
    rows = list(a)
    assert all(isinstance(r, R.PropArray) for r in rows) and list(rows[1]) == [3.0, 4.0, 5.0]
    assert a.q_to_list() == [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]


def test_proparray_repr():
    Foo = one(FloatVectorProperty())
    f = Foo()
    assert repr(f.x) == "<bpy_prop_array[3], Foo.x>"



def test_own_annotations_value():
    class K:
        x: IntProperty(default=1)
        y: int
    ann = R.annotations.own_annotations(K)
    assert isinstance(ann["x"], P._PropertyDeferred) and ann["y"] is int


def test_own_annotations_string_evaluated_in_module():
    ns = {"__annotations__": {"x": "IntProperty(default=4)", "bad": "NoSuchName()"}, "__module__": __name__}
    K = type("K", (), ns)
    ann = R.annotations.own_annotations(K)
    assert isinstance(ann["x"], P._PropertyDeferred) and ann["x"].keywords == {"default": 4}
    assert "bad" not in ann


def test_own_annotations_string_uses_class_namespace():
    ns = {"__annotations__": {"x": "IntProperty(default=LOCAL)"}, "LOCAL": 11, "__module__": __name__}
    K = type("K", (), ns)
    assert R.annotations.own_annotations(K)["x"].keywords == {"default": 11}


def test_own_annotations_only_own():
    class A:
        a: IntProperty()

    class B(A):
        b: IntProperty()
    assert set(R.annotations.own_annotations(B)) == {"b"}


def test_collect_annotations_mro_override_and_mixin():
    class Mixin:
        m: IntProperty()
        plain: int

    class Base(R.Struct):
        a: IntProperty(default=1)

    class Sub(Mixin, Base):
        a: IntProperty(default=2)
        z: FloatProperty()
    col = R.collect_annotations(Sub)
    assert set(col) == {"m", "a", "z"}
    assert col["a"].keywords == {"default": 2}


def test_collect_annotations_skips_builtin_bases():
    class MyPG(R.PropertyGroup):
        v: IntProperty()
    assert set(R.collect_annotations(MyPG)) == {"v"}


def test_collect_annotations_includes_cls_even_if_builtin():
    @R.builtin_struct
    class B(R.Struct):
        q: IntProperty()
    assert set(R.collect_annotations(B)) == {"q"}


def test_install_properties_returns_defs_and_records_names():
    class K(R.Struct):
        a: IntProperty()
        b: FloatProperty()
    out = R.install_properties(K)
    assert [p.identifier for p in out] == ["a", "b"]
    assert all(isinstance(p, R.PropertyDef) for p in out)
    assert K.__dict__["_q_installed"] == ["a", "b"]
    assert isinstance(K.__dict__["a"], R.IntDef)


def test_install_properties_atomic():
    class K(R.Struct):
        a: IntProperty()
        b: IntProperty(options={"BOGUS"})
    with pytest.raises(E.RegistrationError):
        R.install_properties(K)
    assert R.get_property(K, "a") is None


def test_uninstall_properties_removes_installed_and_dynamic():
    Foo = one(IntProperty())
    Foo.dyn = IntProperty()
    assert R.get_property(Foo, "dyn") is not None
    R.uninstall_properties(Foo)
    assert R.get_property(Foo, "x") is None
    assert R.get_property(Foo, "dyn") is None


def test_define_property_dynamic():
    Foo = one(IntProperty())
    p = R.define_property(Foo, "y", FloatProperty(default=2.0))
    assert isinstance(p, R.FloatDef) and R.get_property(Foo, "y") is p
    assert "y" in Foo.__dict__["_q_dynamic"]
    assert Foo().y == 2.0


def test_remove_property_basic():
    Foo = one(IntProperty())
    R.define_property(Foo, "y", IntProperty())
    R.remove_property(Foo, "y")
    assert R.get_property(Foo, "y") is None


def test_remove_property_installed():
    Foo = one(IntProperty())
    R.remove_property(Foo, "x")
    assert R.get_property(Foo, "x") is None


def test_remove_property_missing_attribute_error():
    Foo = one(IntProperty())
    with pytest.raises(AttributeError):
        R.remove_property(Foo, "nope")


def test_remove_property_non_propertydef_attribute_error():
    Foo = one(IntProperty())
    type.__setattr__(Foo, "plain", 1)
    with pytest.raises(AttributeError):
        R.remove_property(Foo, "plain")
    assert Foo.__dict__["plain"] == 1


def test_remove_property_inherited_attribute_error():
    Base = one(IntProperty())

    class Sub(Base):
        pass
    with pytest.raises(AttributeError):
        R.remove_property(Sub, "x")


def test_get_property_class_and_instance_and_mro():
    Base = one(IntProperty())

    class Sub(Base):
        pass
    p = R.get_property(Base, "x")
    assert R.get_property(Sub, "x") is p and R.get_property(Sub(), "x") is p
    assert R.get_property(Base, "nope") is None


def test_iter_properties_order_base_first():
    class Base(R.Struct):
        a: IntProperty()
        b: IntProperty()
    register(Base)

    class Sub(Base):
        c: IntProperty()
    register(Sub)
    assert [p.identifier for p in R.iter_properties(Sub)] == ["a", "b", "c"]


def test_iter_properties_dynamic_at_end():
    class Base(R.Struct):
        a: IntProperty()
    register(Base)

    class Sub(Base):
        c: IntProperty()
    register(Sub)
    R.define_property(Base, "d", IntProperty())
    R.define_property(Sub, "e", IntProperty())
    assert [p.identifier for p in R.iter_properties(Sub)] == ["a", "c", "d", "e"]


def test_iter_properties_shadowed_once_most_derived():
    class Base(R.Struct):
        a: IntProperty(default=1)
    register(Base)

    class Sub(Base):
        a: IntProperty(default=9)
    register(Sub)
    ps = [p for p in R.iter_properties(Sub()) if p.identifier == "a"]
    assert len(ps) == 1 and ps[0].default == 9


def test_legacy_class_body_assignment_not_property():
    d = IntProperty()

    class K(R.Struct):
        x = d
    register(K)
    assert R.get_property(K, "x") is None and K.__dict__["x"] is d


def test_values_survive_remove_and_redefine():
    Foo = one(IntProperty())
    f = Foo()
    f.x = 5
    R.remove_property(Foo, "x")
    R.define_property(Foo, "x", IntProperty())
    assert f.x == 5



def test_idref_namedtuple():
    assert issubclass(R.IDRef, tuple)
    assert R.IDRef._fields == ("target", "owner", "kind", "counts_user", "on_remove", "clear", "remap")


def test_structmeta_setattr_defines_on_registered():
    Foo = one(IntProperty())
    Foo.y = IntProperty(default=3)
    assert isinstance(Foo.__dict__["y"], R.IntDef) and Foo().y == 3


def test_structmeta_setattr_plain_on_unregistered():
    class K(R.Struct):
        pass
    d = IntProperty()
    K.y = d
    assert K.__dict__["y"] is d


def test_structmeta_setattr_propagates_build_error():
    Foo = one(IntProperty())
    with pytest.raises(E.RegistrationError):
        Foo.bad = IntProperty(options={"BOGUS"})


def test_structmeta_delattr_removes_property():
    log = []
    H.install(on_type_property_removed=lambda c, i: log.append(i))
    Foo = one(IntProperty())
    del Foo.x
    assert R.get_property(Foo, "x") is None and log == ["x"]


def test_structmeta_delattr_plain():
    class K(R.Struct):
        z = 1
    del K.z
    assert "z" not in K.__dict__


def test_is_registered():
    class K(R.Struct):
        pass
    assert K.is_registered is False
    register(K)
    assert K.is_registered is True
    assert R.Struct.is_registered is True


def test_builtin_struct_plain_and_with_identifier():
    @R.builtin_struct
    class A(R.Struct):
        p: IntProperty()

    @R.builtin_struct(identifier="CustomName")
    class B(R.Struct):
        pass
    assert A.__dict__["_q_builtin"] is True and isinstance(A.__dict__["bl_rna"], R.RNAStruct)
    assert A.bl_rna.identifier == "A" and B.bl_rna.identifier == "CustomName"
    assert isinstance(A.__dict__["p"], R.IntDef)


def test_missing_sentinel():
    from quartz.rna.struct import MISSING
    assert MISSING is R.struct.MISSING and MISSING is not None


def test_struct_new_state_and_init_args():
    s = R.Struct(1, 2, a=3)
    assert s._p == {} and s._p_set == set() and s._q_idprops is None
    assert s._q_owner is None and s._q_path == "" and s._q_key_order == []


def test_struct_classvars():
    assert R.Struct._q_strict_attrs is False and R.Struct._q_is_id is False


def test_rna_type_property():
    Foo = one(IntProperty())
    assert Foo().rna_type is Foo.bl_rna


def _tree():
    FakeID = make_id_class()
    Inner = register(type("Inner", (R.PropertyGroup,), {"__annotations__": {"v": IntProperty()}}))
    Mid = register(type("Mid", (R.PropertyGroup,), {"__annotations__": {"inner": PointerProperty(type=Inner)}}))
    R.define_property(FakeID, "qz_attr_pg", PointerProperty(type=Mid))
    i = FakeID()
    return i, i.qz_attr_pg, i.qz_attr_pg.inner


def test_id_data():
    i, mid, inner = _tree()
    assert i.id_data is i and mid.id_data is i and inner.id_data is i
    assert R.PropertyGroup().id_data is None


def test_strict_attrs_message_observed():
    @R.builtin_struct
    class Strict(R.Struct):
        _q_strict_attrs = True
    s = Strict()
    with pytest.raises(AttributeError) as ei:
        s.foo = 1
    assert "'Strict' object has no attribute 'foo'" in str(ei.value)
    s._private = 1
    assert s._private == 1


def test_pg_unknown_attr_accepted_observed():
    pg = R.PropertyGroup()
    pg.not_declared = 3
    assert pg.not_declared == 3


def test_setattr_routes_to_descriptor():
    Foo = one(IntProperty())
    f = Foo()
    f.x = True
    assert f.x == 1 and "x" not in f.__dict__


def test_repr_default():
    Foo = one(IntProperty())
    f = Foo()
    assert repr(f) == f"<bpy_struct, Foo at 0x{id(f):016X}>"


def test_repr_with_id_observed():
    facts = json.loads((ROOT / "data" / "blender_facts_judge.json").read_text(encoding="utf-8"))["props.pg_attrs"]
    i, mid, inner = _tree()
    assert repr(mid) == facts["pg_repr"]
    assert repr(inner) == "bpy.data.scenes['Scene'].qz_attr_pg.inner"


def test_as_pointer():
    s = R.Struct()
    assert s.as_pointer() == id(s)


def test_path_from_id_chain():
    i, mid, inner = _tree()
    assert i.path_from_id() == "" and i.path_from_id("qz_attr_pg") == "qz_attr_pg"
    assert mid.path_from_id() == "qz_attr_pg"
    assert inner.path_from_id() == "qz_attr_pg.inner"
    assert inner.path_from_id("v") == "qz_attr_pg.inner.v"


def test_path_from_id_collection_item():
    FakeID = make_id_class()
    Item_ = register(type("CItem", (R.PropertyGroup,), {}))
    R.define_property(FakeID, "items", CollectionProperty(type=Item_))
    i = FakeID()
    a = i.items.add()
    assert a.path_from_id() == "items[0]"


def test_path_from_id_without_id_raises():
    pg = R.PropertyGroup()
    with pytest.raises(ValueError) as ei:
        pg.path_from_id()
    assert "PropertyGroup.path_from_id() does not support path creation for this type" in str(ei.value)


def test_path_from_module_uses_repr_root():
    i, mid, inner = _tree()
    p = inner.path_from_module("v")
    assert p.startswith("quartz.") and p.endswith("qz_attr_pg.inner.v")
    H.install(repr_root=lambda: "bpy")
    assert inner.path_from_module("v").startswith("bpy.")


def test_path_resolve():
    i, mid, inner = _tree()
    inner.v = 4
    assert i.path_resolve("qz_attr_pg.inner.v") == 4
    ref = i.path_resolve("qz_attr_pg.inner.v", False)
    assert ref == DP.PropertyRef(inner, "v", None)


def test_is_property_set_and_unset_observed():
    Foo = one(IntProperty(default=2))
    f = Foo()
    assert not f.is_property_set("x")
    f.x = 5
    assert f.is_property_set("x")
    f.property_unset("x")
    assert not f.is_property_set("x") and f.x == 2 and "x" not in f._p


def test_is_property_set_idprop():
    s = R.Struct()
    s["k"] = 1
    assert s.is_property_set("k")


def test_is_property_readonly_hidden():
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {
        "r": IntProperty(get=lambda s: 1), "h": IntProperty(options={"HIDDEN"}), "n": IntProperty()}}))
    f = Foo()
    assert f.is_property_readonly("r") and not f.is_property_readonly("n")
    assert f.is_property_hidden("h") and not f.is_property_hidden("n")


def test_overridable_library():
    s = R.Struct()
    assert s.is_property_overridable_library("x") is False
    assert s.property_overridable_library_set("x", True) is True


def test_keys_plain_struct_only_idprops():
    Foo = one(IntProperty())
    f = Foo()
    f.x = 3
    f["a"] = 1
    assert f.keys() == ["a"]


def test_keys_id_only_idprops_observed():
    FakeID = make_id_class()
    R.define_property(FakeID, "n", IntProperty())
    i = FakeID()
    i.n = 2
    assert i.keys() == []
    i["k"] = 1
    assert i.keys() == ["k"]


def test_keys_pg_first_write_order_observed():
    PG = one_pg(IntProperty())
    pg = PG()
    pg["foo"] = 1
    pg.x = 2
    pg["bar"] = 3
    pg.x = 4
    assert pg.keys() == ["foo", "x", "bar"]


def test_keys_pg_unwritten_rna_absent():
    PG = one_pg(IntProperty())
    assert PG().keys() == []


def test_values_items_get():
    PG = one_pg(IntProperty())
    pg = PG()
    pg.x = 2
    pg["k"] = "v"
    assert pg.values() == [2, "v"] and pg.items() == [("x", 2), ("k", "v")]
    assert pg.get("k") == "v" and pg.get("zz") is None and pg.get("zz", 1) == 1


def test_getitem_missing_message_observed():
    with pytest.raises(KeyError) as ei:
        R.Struct()["nope"]
    assert 'bpy_struct[key]: key "nope" not found' in str(ei.value)


def test_pop():
    s = R.Struct()
    s["a"] = 1
    assert s.pop("a") == 1 and "a" not in s
    assert s.pop("a", 7) == 7
    with pytest.raises(KeyError):
        s.pop("a")


def test_setitem_pg_rna_name_uses_setattr():
    PG = one_pg(IntProperty())
    pg = PG()
    pg["x"] = 5
    assert pg.x == 5 and pg._q_idprops is None or "x" not in (pg._q_idprops or {})
    with pytest.raises(E.PropertyTypeError):
        pg["x"] = 2.0


def test_setitem_converts_idprop():
    s = R.Struct()
    s["g"] = {"a": 1}
    assert isinstance(s["g"], R.IDPropertyGroup)


def test_delitem_and_contains():
    s = R.Struct()
    s["a"] = 1
    assert "a" in s
    del s["a"]
    assert "a" not in s
    with pytest.raises(KeyError):
        del s["a"]


def test_id_properties_ensure_clear_ui():
    s = R.Struct()
    g = s.id_properties_ensure()
    assert isinstance(g, R.IDPropertyGroup) and s.id_properties_ensure() is g
    with pytest.raises(KeyError):
        s.id_properties_ui("k")
    s["k"] = 1.0
    assert isinstance(s.id_properties_ui("k"), R.IDPropertyUIManager)
    s.id_properties_clear()
    assert s.keys() == []


def test_bl_system_properties_get():
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {"x": IntProperty(), "v": FloatVectorProperty()}}))
    f = Foo()
    f.v
    f.x = 3
    g = f.bl_system_properties_get()
    assert isinstance(g, R.IDPropertyGroup) and dict(g.items()) == {"x": 3}


def test_bl_system_properties_get_do_create():
    g = R.Struct().bl_system_properties_get(do_create=True)
    assert isinstance(g, R.IDPropertyGroup)


def test_type_recast():
    s = R.Struct()
    assert s.type_recast() is s


def test_rna_ancestors():
    i, mid, inner = _tree()
    assert inner.rna_ancestors() == [i, mid]
    assert mid.rna_ancestors() == [i]


def test_bl_rna_get_subclass():
    PG = register(type("UniqueSubPG_xyz", (R.PropertyGroup,), {}))
    assert R.Struct.bl_rna_get_subclass("UniqueSubPG_xyz") is PG.bl_rna
    assert R.Struct.bl_rna_get_subclass_py("UniqueSubPG_xyz") is PG
    assert R.Struct.bl_rna_get_subclass("NoSuchThing_q", 5) == 5
    assert R.Struct.bl_rna_get_subclass_py("NoSuchThing_q") is None


def test_keyframe_insert_not_implemented():
    with pytest.raises(E.NotImplementedInQuartz) as ei:
        R.Struct().keyframe_insert("x")
    assert ei.value.symbol == "bpy_struct.keyframe_insert"
    assert isinstance(ei.value, NotImplementedError)


def test_keyframe_delete_not_implemented():
    with pytest.raises(E.NotImplementedInQuartz):
        R.Struct().keyframe_delete("x")


def test_driver_add_remove():
    with pytest.raises(E.NotImplementedInQuartz) as ei:
        R.Struct().driver_add("x")
    assert ei.value.symbol == "bpy_struct.driver_add"
    assert R.Struct().driver_remove("x") is False


def test_q_on_change_propagates_to_id():
    i, mid, inner = _tree()
    type(i).changes = []
    inner.v = 3
    assert "v" in type(i).changes


def test_q_refs_id_pointer_and_recursive():
    FakeID = make_id_class()
    Inner = register(type("RefInner", (R.PropertyGroup,), {"__annotations__": {
        "t": PointerProperty(type=FakeID, meta={"counts_user": False, "on_remove": "DELETE_OWNER"})}}))
    Owner = register(type("RefOwner", (R.Struct,), {"__annotations__": {
        "direct": PointerProperty(type=FakeID), "pg": PointerProperty(type=Inner),
        "col": CollectionProperty(type=Inner), "empty": PointerProperty(type=FakeID)}}))
    o = Owner()
    t1, t2, t3 = FakeID(), FakeID(), FakeID()
    o.direct = t1
    o.pg.t = t2
    o.col.add().t = t3
    refs = list(o._q_refs())
    assert {id(r.target) for r in refs} == {id(t1), id(t2), id(t3)}
    d = [r for r in refs if r.target is t1][0]
    assert isinstance(d, R.IDRef) and d.owner is o and d.kind == "POINTER" and d.counts_user is True and d.on_remove == "CLEAR"
    n = [r for r in refs if r.target is t2][0]
    assert n.owner is o.pg and n.counts_user is False and n.on_remove == "DELETE_OWNER"
    t4 = FakeID()
    d.remap(t4)
    assert o.direct is t4
    d.clear()
    assert o.direct is None


def test_q_state_get_structure_and_array_copy():
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {"x": IntProperty(), "v": FloatVectorProperty()}}))
    f = Foo()
    f.x = 3
    f.v = (1, 2, 3)
    f["k"] = 1
    st = f._q_state_get()
    assert set(st) >= {"p", "set", "idprops", "order"}
    assert st["p"]["x"] == 3 and st["set"] == ["v", "x"] and st["idprops"] == {"k": 1}
    assert isinstance(st["p"]["v"], np.ndarray) and st["p"]["v"] is not f._p["v"]


def test_q_state_get_nested_pg_and_collection():
    Inner = register(type("StInner", (R.PropertyGroup,), {"__annotations__": {"n": IntProperty()}}))
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {
        "pg": PointerProperty(type=Inner), "col": CollectionProperty(type=Inner)}}))
    f = Foo()
    f.pg.n = 5
    f.col.add().n = 7
    st = f._q_state_get()
    assert isinstance(st["p"]["pg"], dict) and st["p"]["pg"]["p"]["n"] == 5
    assert isinstance(st["p"]["col"], list) and st["p"]["col"][0]["p"]["n"] == 7


def test_q_state_set_in_place():
    Inner = register(type("StInner2", (R.PropertyGroup,), {"__annotations__": {"n": IntProperty()}}))
    Foo = register(type("Foo", (R.Struct,), {"__annotations__": {
        "x": IntProperty(), "pg": PointerProperty(type=Inner), "col": CollectionProperty(type=Inner)}}))
    f = Foo()
    f.x = 1
    f.pg.n = 5
    f.col.add().n = 7
    st = f._q_state_get()
    pg_before = f.pg
    f.x = 9
    f.pg.n = 0
    f.col.clear()
    f._q_state_set(st)
    assert f.x == 1 and f.pg is pg_before and f.pg.n == 5
    assert len(f.col) == 1 and f.col[0].n == 7


def test_q_new_child_and_set_owner():
    PG = register(type("ChildPG", (R.PropertyGroup,), {}))
    o = R.Struct()
    c = PG._q_new_child(owner=o, path="kid")
    assert isinstance(c, PG) and c._q_owner is o and c._q_path == "kid"
    c._q_set_owner(None, "")
    assert c._q_owner is None and c._q_path == ""


def test_property_group_name_prop():
    p = R.get_property(R.PropertyGroup, "name")
    assert isinstance(p, R.StringDef) and p.name == "Name"
    assert R.PropertyGroup._q_registrable is True
    pg = R.PropertyGroup()
    assert pg.name == ""
    pg.name = "n"
    assert pg.name == "n"



def test_idgroup_basic_mapping():
    g = R.IDPropertyGroup({"a": 1, "b": 2}, name="grp")
    assert g.name == "grp" and g["a"] == 1 and len(g) == 2 and list(g) == ["a", "b"]
    g["c"] = 3
    assert g.keys() == ["a", "b", "c"] and "c" in g
    del g["a"]
    assert list(g) == ["b", "c"]
    with pytest.raises(KeyError):
        g["a"]
    with pytest.raises(KeyError):
        del g["a"]


def test_idgroup_default_name():
    assert R.IDPropertyGroup().name == ""


def test_idgroup_get_pop_clear_update():
    g = R.IDPropertyGroup()
    g.update({"a": 1})
    g.update(b=2)
    assert g.get("a") == 1 and g.get("z", 0) == 0
    assert g.pop("a") == 1 and g.pop("a", 5) == 5
    with pytest.raises(KeyError):
        g.pop("a")
    g.clear()
    assert len(g) == 0


def test_idgroup_update_from_group():
    g = R.IDPropertyGroup()
    g.update(R.IDPropertyGroup({"x": 1}))
    assert g["x"] == 1


def test_idgroup_values_items():
    g = R.IDPropertyGroup({"a": 1, "b": "s"})
    assert list(g.values()) == [1, "s"] and list(g.items()) == [("a", 1), ("b", "s")]


def test_idprop_conversion_scalars():
    g = R.IDPropertyGroup()
    g["b"], g["i"], g["f"], g["s"] = True, 3, 0.1, "x"
    assert g["b"] is True and g["i"] == 3 and type(g["i"]) is int
    assert g["f"] == 0.1 and type(g["f"]) is float
    assert g["s"] == "x"


def test_idprop_int_overflow():
    g = R.IDPropertyGroup()
    with pytest.raises(OverflowError):
        g["i"] = 2**31


@pytest.mark.parametrize("seq,code", [([1, 2, 3], "i"), ([True, False], "b"), ([1, 2.5], "d"), ((0.5, 1.5), "d")])
def test_idprop_sequence_to_array(seq, code):
    g = R.IDPropertyGroup()
    g["a"] = seq
    assert isinstance(g["a"], R.IDPropertyArray) and g["a"].typecode == code
    assert g["a"].to_list() == list(seq)


def test_idprop_dict_nested_group():
    g = R.IDPropertyGroup()
    g["d"] = {"x": {"y": 1}}
    assert isinstance(g["d"], R.IDPropertyGroup) and isinstance(g["d"]["x"], R.IDPropertyGroup)
    assert g["d"]["x"]["y"] == 1


def test_idprop_list_of_dicts():
    g = R.IDPropertyGroup()
    g["l"] = [{"a": 1}, {"b": 2}]
    assert isinstance(g["l"], list) and all(isinstance(x, R.IDPropertyGroup) for x in g["l"])


def test_idprop_id_reference():
    FakeID = make_id_class()
    t = FakeID()
    g = R.IDPropertyGroup()
    g["ref"] = t
    assert g["ref"] is t


def test_idprop_other_type_error():
    g = R.IDPropertyGroup()
    with pytest.raises(TypeError):
        g["o"] = object()


def test_idprop_set_type_error():
    g = R.IDPropertyGroup()
    with pytest.raises(TypeError):
        g["o"] = {1, 2}


def test_idgroup_to_dict():
    g = R.IDPropertyGroup({"a": [1, 2], "d": {"x": 1.5}, "l": [{"q": 1}]})
    assert g.to_dict() == {"a": [1, 2], "d": {"x": 1.5}, "l": [{"q": 1}]}
    assert type(g.to_dict()["a"]) is list


def test_idarray_behaviour():
    a = R.IDPropertyArray([1, 2, 3], "i")
    assert a.typecode == "i" and len(a) == 3 and a[1] == 2 and list(a) == [1, 2, 3]
    assert a == [1, 2, 3] and a == (1, 2, 3) and a.to_list() == [1, 2, 3]
    assert np.asarray(a).tolist() == [1, 2, 3]


def test_idarray_setitem_coerces_double():
    a = R.IDPropertyArray([1.0, 2.0], "d")
    a[0] = 3
    assert a[0] == 3.0 and type(a[0]) is float


def test_idarray_bool_typecode():
    a = R.IDPropertyArray([1, 0], "b")
    assert a.to_list() == [True, False]


def test_ui_manager_observed_float():
    g = R.IDPropertyGroup({"f": 0.0})
    m = R.IDPropertyUIManager(g, "f")
    m.update(min=0, max=10)
    assert m.as_dict() == {"subtype": "NONE", "description": "", "min": 0.0, "max": 10.0, "soft_min": 0.0,
                           "soft_max": 10.0, "step": 1.0, "precision": 3, "default": 0.0}


def test_ui_manager_float_types():
    g = R.IDPropertyGroup({"f": 0.0})
    m = R.IDPropertyUIManager(g, "f")
    m.update(min=0, max=10)
    d = m.as_dict()
    assert type(d["min"]) is float and type(d["max"]) is float


def test_ui_manager_float_defaults():
    g = R.IDPropertyGroup({"f": 1.5})
    d = R.IDPropertyUIManager(g, "f").as_dict()
    assert d["min"] == -3.4028234663852886e38 and d["soft_min"] == -3.4028234663852886e38
    assert d["max"] == 3.4028234663852886e38 and d["soft_max"] == 3.4028234663852886e38
    assert d["step"] == 1.0 and d["precision"] == 3
    assert d["default"] == 0.0


def test_ui_manager_int_defaults():
    g = R.IDPropertyGroup({"i": 5})
    d = R.IDPropertyUIManager(g, "i").as_dict()
    assert d["min"] == -2**31 and d["soft_min"] == -2**31 and d["max"] == 2**31 - 1 and d["soft_max"] == 2**31 - 1
    assert d["step"] == 1 and d["default"] == 0


def test_ui_manager_string_defaults():
    g = R.IDPropertyGroup({"s": "abc"})
    assert R.IDPropertyUIManager(g, "s").as_dict() == {"subtype": "NONE", "description": "", "default": ""}


def test_ui_manager_precision_on_int_type_error():
    g = R.IDPropertyGroup({"i": 5})
    with pytest.raises(TypeError):
        R.IDPropertyUIManager(g, "i").update(precision=2)


def test_ui_manager_clear_and_update_from():
    g = R.IDPropertyGroup({"f": 0.0, "h": 0.0})
    m, n = R.IDPropertyUIManager(g, "f"), R.IDPropertyUIManager(g, "h")
    m.update(min=1.0, description="desc")
    n.update_from(m)
    assert n.as_dict()["min"] == 1.0 and n.as_dict()["description"] == "desc"
    m.clear()
    assert m.as_dict()["min"] == -3.4028234663852886e38 and m.as_dict()["description"] == ""


def test_rna_idprop_ui_create():
    s = R.Struct()
    m = R.rna_idprop_ui_create(s, "p", default=0.5, min=0, max=2, description="D")
    assert s["p"] == 0.5 and isinstance(m, R.IDPropertyUIManager)
    d = m.as_dict()
    assert d["min"] == 0 and d["max"] == 2 and d["soft_min"] == 0 and d["soft_max"] == 2 and d["description"] == "D"
    assert s.id_properties_ui("p").as_dict()["max"] == 2


def test_rna_idprop_ui_create_signature_defaults():
    import inspect
    sig = inspect.signature(R.rna_idprop_ui_create)
    assert sig.parameters["min"].default == 0 and sig.parameters["max"].default == 1
    assert sig.parameters["default"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["overridable"].default is False


def test_rna_idprop_value_to_python():
    g = R.IDPropertyGroup({"a": {"b": [1, 2]}})
    assert R.rna_idprop_value_to_python(g) == {"a": {"b": [1, 2]}}
    assert R.rna_idprop_value_to_python(R.IDPropertyArray([1.0], "d")) == [1.0]
    assert R.rna_idprop_value_to_python(5) == 5


def test_rna_idprop_quote_path():
    assert R.rna_idprop_quote_path('a"b') == '["a\\"b"]'
    assert R.rna_idprop_quote_path("plain") == '["plain"]'


def test_idprop_double_not_float32_on_struct():
    s = R.Struct()
    s["f"] = 0.1
    assert s["f"] == 0.1



def test_rnastruct_basic_fields():
    class Doc(R.Struct):
        __doc__ = "Summary line.\n\n        Detail."
        bl_label = "Nice Label"
        a: IntProperty()
    register(Doc)
    r = Doc.bl_rna
    assert r.identifier == "Doc" and r.name == "Nice Label" and r.description == "Summary line."
    assert r.translation_context == "*" and r.nested is None and r.q_py_class is Doc


def test_rnastruct_name_defaults_identifier_and_empty_doc():
    K = register(type("NoDoc", (R.Struct,), {}))
    assert K.bl_rna.name == "NoDoc" and K.bl_rna.description == ""


def test_rnastruct_explicit_identifier():
    r = R.RNAStruct(R.Struct, "Other")
    assert r.identifier == "Other"


def test_rnastruct_base_identity():
    Base = register(type("RBase", (R.Struct,), {}))
    Sub = register(type("RSub", (Base,), {}))
    assert Sub.bl_rna.base is Base.bl_rna
    assert Base.bl_rna.base is R.Struct.bl_rna
    assert R.Struct.bl_rna.base is None


def test_rnastruct_base_skips_unregistered():
    Base = register(type("RBase2", (R.Struct,), {}))
    Mid = type("RMid", (Base,), {})
    Sub = register(type("RSub2", (Mid,), {}))
    assert Sub.bl_rna.base is Base.bl_rna


def test_rnastruct_properties_live_with_rna_type():
    Foo = one(IntProperty())
    props = Foo.bl_rna.properties
    assert isinstance(props, R.PropCollection)
    assert props.keys()[0] == "rna_type" and "x" in props.keys()
    R.define_property(Foo, "late", FloatProperty())
    assert "late" in Foo.bl_rna.properties.keys()


def test_rnastruct_functions_empty():
    Foo = one(IntProperty())
    assert isinstance(Foo.bl_rna.functions, R.PropCollection) and len(Foo.bl_rna.functions) == 0


def test_rnastruct_repr():
    Foo = one(IntProperty())
    assert re.fullmatch(r'<bpy_struct, Struct\("Foo"\) at 0x[0-9A-Fa-f]+>', repr(Foo.bl_rna))


def test_rnaproperty_fields_int():
    Foo = one(IntProperty(name="N", description="D", default=3, min=0, max=9, options={"HIDDEN"}))
    rp = Foo.bl_rna.properties["x"]
    assert isinstance(rp, R.RNAProperty)
    assert rp.identifier == "x" and rp.name == "N" and rp.description == "D" and rp.type == "INT"
    assert rp.default == 3 and rp.hard_min == 0 and rp.hard_max == 9 and rp.is_hidden
    assert rp.q_definition is R.get_property(Foo, "x") and rp.array_length == 0


def test_rnaproperty_vector_type_and_arrays():
    Foo = one(FloatVectorProperty(default=(1.0, 2.0, 3.0)))
    rp = Foo.bl_rna.properties["x"]
    assert rp.type == "FLOAT" and rp.array_length == 3 and rp.default_array == (1.0, 2.0, 3.0)
    Foo2 = one(FloatVectorProperty(size=(2, 3)))
    assert tuple(Foo2.bl_rna.properties["x"].array_dimensions)[:2] == (2, 3)


def test_rnaproperty_enum_items():
    Foo = one(EnumProperty(items=[("A", "a", "da"), ("B", "b", "db")]))
    rp = Foo.bl_rna.properties["x"]
    assert rp.type == "ENUM" and rp.enum_items.keys() == ["A", "B"]
    it = rp.enum_items["B"]
    assert isinstance(it, R.RNAEnumItem) and it.name == "b" and it.description == "db" and it.value == 1
    assert isinstance(rp.enum_items_static, R.PropCollection)


def test_rnaproperty_fixed_type():
    PG = register(type("FixPG", (R.PropertyGroup,), {}))
    Foo = one(PointerProperty(type=PG))
    assert Foo.bl_rna.properties["x"].fixed_type is PG.bl_rna
    assert one(IntProperty()).bl_rna.properties["x"].fixed_type is None


def test_rnaproperty_string_length_max():
    Foo = one(StringProperty(maxlen=7))
    assert Foo.bl_rna.properties["x"].length_max == 7


def test_rnaproperty_pseudo_rna_type_no_definition():
    Foo = one(IntProperty())
    rp = Foo.bl_rna.properties["rna_type"]
    assert rp.identifier == "rna_type" and rp.q_definition is None and rp.is_readonly


def test_rnaproperty_flags_present():
    rp = one(IntProperty()).bl_rna.properties["x"]
    for attr in ("is_readonly", "is_hidden", "is_skip_save", "is_animatable", "is_enum_flag", "is_never_none",
                 "is_library_editable", "is_overridable", "is_registered", "is_registered_optional", "is_required",
                 "is_argument_optional", "is_output", "is_runtime", "translation_context", "subtype", "unit",
                 "icon", "tags", "soft_min", "soft_max", "step", "precision"):
        assert hasattr(rp, attr), attr



def _desc_cls():
    class D(R.Struct):
        a: BoolProperty(meta={"group": "G1"})
        b: IntProperty(meta={"group": "G1", "parent": "a"})
        c: IntProperty()
        d: IntProperty(meta={"visible_if": lambda inst: inst.c > 0, "enabled_if": lambda inst: inst.c > 1})
        e: IntProperty(options={"HIDDEN"}, meta={"parent": "c"})
    return register(D)


def test_describe_class_and_instance():
    D = _desc_cls()
    assert isinstance(R.describe(D), R.Description) and R.describe(D).owner is D
    assert R.describe(D()).owner is D


def test_description_iter_len_contains_getitem():
    D = _desc_cls()
    d = R.describe(D)
    assert [p.identifier for p in d] == ["a", "b", "c", "d", "e"] and len(d) == 5
    assert "a" in d and "zz" not in d
    assert d["c"] is R.get_property(D, "c")
    with pytest.raises(KeyError):
        d["zz"]


def test_description_groups_in_group_children():
    d = R.describe(_desc_cls())
    assert d.groups() == ("G1", "")
    assert [p.identifier for p in d.in_group("G1")] == ["a", "b"]
    assert [p.identifier for p in d.in_group("")] == ["c", "d", "e"]
    assert [p.identifier for p in d.children_of("a")] == ["b"]
    assert d.children_of("zz") == ()


def test_description_is_enabled():
    D = _desc_cls()
    d, inst = R.describe(D), D()
    assert d.is_enabled(inst, "b") is False
    inst.a = True
    assert d.is_enabled(inst, "b") is True
    assert d.is_enabled(inst, "c") is True
    assert d.is_enabled(inst, "e") is True
    assert d.is_enabled(inst, "d") is False
    inst.c = 2
    assert d.is_enabled(inst, "d") is True


def test_description_is_visible():
    D = _desc_cls()
    d, inst = R.describe(D), D()
    assert d.is_visible(inst, "d") is False
    inst.c = 1
    assert d.is_visible(inst, "d") is True
    assert d.is_visible(inst, "e") is False and d.is_visible(inst, "a") is True


def test_description_to_rna_dict():
    D = _desc_cls()
    d = R.describe(D).to_rna_dict()
    assert list(d) == ["a", "b", "c", "d", "e"]
    assert d["c"] == R.get_property(D, "c").to_rna_dict()
