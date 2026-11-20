import pytest

from quartz import registry
from quartz.app import settings
from quartz.errors import (
    ClassValidationError,
    MissingClassAttributeError,
    RegistrationError,
    RegistrationRuntimeError,
)
from quartz.props import IntProperty, PointerProperty
from quartz.rna import PropertyGroup, Struct, hooks
from quartz.rna.annotations import get_property
from quartz.types.operator import Event, Operator, OperatorFileListElement
from quartz.types.prefs import AddonPreferences
from quartz.types.ui import SPACE_TYPES, Header, Menu, Panel, UIList


@pytest.fixture(autouse=True)
def sandbox():
    hsnap = hooks.snapshot()
    ssnap = settings.snapshot()
    rsnap = registry.snapshot()
    registry.install_hooks()
    try:
        yield
    finally:
        registry.restore(rsnap)
        settings.restore(ssnap)
        hooks.restore(hsnap)


def _op(name="QZT_OT_x", **attrs):
    ns = {"bl_label": "X", "execute": lambda self, context: {"FINISHED"}}
    ns.update(attrs)
    return type(Operator)(name, (Operator,), ns)


def _panel(name="QZT_PT_x", **attrs):
    ns = {"bl_label": "P", "bl_space_type": "VIEW_3D", "bl_region_type": "UI", "draw": lambda self, ctx: None}
    ns.update(attrs)
    for k in [k for k, v in ns.items() if v is _DROP]:
        del ns[k]
    return type(Panel)(name, (Panel,), ns)


_DROP = object()


@pytest.mark.parametrize("idname, reason", [
    ("quartzprobe", "Must contain 1 '.' character"),
    ("Quartz.Probe", "Invalid character at position 0"),
    ("quartz.probe.x", "Must contain 1 '.' character"),
    ("QUARTZ_OT_probe", "Invalid character at position 0"),
])
def test_operator_idname_invalid(idname, reason):
    cls = _op("QUARTZPROBE_OT_v", bl_idname=idname)
    with pytest.raises(RegistrationRuntimeError) as exc:
        registry.register_class(cls)
    msg = str(exc.value)
    assert "invalid bl_idname" in msg and reason in msg
    assert f"Registering operator class 'QUARTZPROBE_OT_v', invalid bl_idname '{idname}'" in msg
    assert not registry.is_registered(cls)


def test_operator_idname_too_long_truncated_to_63():
    idname = "quartz." + "x" * 80
    cls = _op("QUARTZPROBE_OT_v_long", bl_idname=idname)
    with pytest.raises(RegistrationRuntimeError) as exc:
        registry.register_class(cls)
    msg = str(exc.value)
    assert f"invalid bl_idname '{idname[:63]}'," in msg
    assert "Identifier too long, maximum length is 60" in msg
    assert len(idname[:63]) == 63


def test_operator_idname_61_chars_too_long_and_60_ok():
    ok = _op("QZT_OT_sixty", bl_idname="qzt." + "a" * 56)
    assert len(ok.bl_idname) == 60
    registry.register_class(ok)
    bad = _op("QZT_OT_sixtyone", bl_idname="qzt." + "a" * 57)
    with pytest.raises(RegistrationRuntimeError, match="maximum length is 60"):
        registry.register_class(bad)


def test_operator_leading_digit_accepted():
    cls = _op("QZT_OT_digit", bl_idname="1quartz.probe")
    registry.register_class(cls)
    assert registry.is_registered(cls)
    assert registry.rna_name_of(cls) == "1QUARTZ_OT_probe"


def test_operator_without_bl_idname_uses_class_name():
    cls = _op("QUARTZPROBE_OT_noidname")
    with pytest.raises(RegistrationRuntimeError) as exc:
        registry.register_class(cls)
    assert "invalid bl_idname 'QUARTZPROBE_OT_noidname'" in str(exc.value)
    assert "Invalid character at position 0" in str(exc.value)


def test_operator_lowercase_class_name_as_idname():
    cls = _op("qzt.classname")
    registry.register_class(cls)
    assert registry.operator_class("qzt.classname") is cls


def test_operator_without_bl_label():
    cls = type(Operator)("QUARTZPROBE_OT_nolabel", (Operator,), {"bl_idname": "qzt.nolabel"})
    with pytest.raises(MissingClassAttributeError) as exc:
        registry.register_class(cls)
    assert 'expected Operator, QUARTZPROBE_OT_nolabel class to have an "bl_label" attribute' in str(exc.value)
    assert isinstance(exc.value, AttributeError)


def test_operator_without_execute_is_ok():
    cls = type(Operator)("QZT_OT_noexec", (Operator,), {"bl_idname": "qzt.noexec", "bl_label": "N"})
    registry.register_class(cls)
    assert registry.is_registered(cls)


def test_operator_rna_name_observed():
    cls = _op("QZT_OT_hello", bl_idname="quartz_probe.hello")
    registry.register_class(cls)
    assert registry.rna_name_of(cls) == "QUARTZ_PROBE_OT_hello"
    assert cls.bl_rna.identifier == "QUARTZ_PROBE_OT_hello"
    assert registry.lookup("QUARTZ_PROBE_OT_hello") is cls


def test_operator_bl_options_validation():
    with pytest.raises(ClassValidationError) as exc:
        registry.register_class(_op("QZT_OT_o1", bl_idname="qzt.o1", bl_options={"ZZZ", "AAA", "REGISTER"}))
    assert 'validating class: enum "AAA" not found in (' in str(exc.value)
    assert "'REGISTER', 'UNDO'" in str(exc.value)
    with pytest.raises(ClassValidationError, match="expected a set"):
        registry.register_class(_op("QZT_OT_o2", bl_idname="qzt.o2", bl_options=["REGISTER"]))
    registry.register_class(_op("QZT_OT_o3", bl_idname="qzt.o3", bl_options={"REGISTER", "UNDO"}))


def test_operator_bl_idname_none_expected_string():
    with pytest.raises(ClassValidationError, match="expected a string"):
        registry.register_class(_op("QZT_OT_none", bl_idname=None))


@pytest.mark.parametrize("missing", ["bl_label", "bl_space_type", "bl_region_type", "draw"])
def test_panel_missing_required(missing):
    cls = _panel("QUARTZPROBE_PT_req", **{missing: _DROP})
    with pytest.raises(MissingClassAttributeError) as exc:
        registry.register_class(cls)
    assert f'expected Panel, QUARTZPROBE_PT_req class to have an "{missing}" attribute' in str(exc.value)


def test_panel_several_missing_reports_first_in_table_order():
    cls = type(Panel)("QZT_PT_none", (Panel,), {})
    with pytest.raises(MissingClassAttributeError, match='"bl_label" attribute'):
        registry.register_class(cls)
    cls2 = type(Panel)("QZT_PT_none2", (Panel,), {"bl_label": "x", "draw": lambda s, c: None})
    with pytest.raises(MissingClassAttributeError, match='"bl_space_type" attribute'):
        registry.register_class(cls2)


def test_panel_bad_space_enum_lists_everything():
    cls = _panel("QUARTZPROBE_PT_bad", bl_space_type="NOPE")
    with pytest.raises(ClassValidationError) as exc:
        registry.register_class(cls)
    listing = ", ".join(repr(s) for s in SPACE_TYPES)
    assert str(exc.value) == f'validating class: enum "NOPE" not found in ({listing})'
    assert isinstance(exc.value, TypeError)


def test_panel_bad_region_and_options():
    with pytest.raises(ClassValidationError, match='enum "NOPE" not found in'):
        registry.register_class(_panel("QZT_PT_r", bl_region_type="NOPE"))
    with pytest.raises(ClassValidationError, match='enum "BAD" not found in'):
        registry.register_class(_panel("QZT_PT_o", bl_options={"BAD", "HIDE_HEADER"}))
    with pytest.raises(ClassValidationError, match="expected a set"):
        registry.register_class(_panel("QZT_PT_o2", bl_options="HIDE_HEADER"))


def test_space_type_not_string():
    with pytest.raises(ClassValidationError, match="expected a string"):
        registry.register_class(_panel("QZT_PT_int", bl_space_type=3))


def test_panel_parent_missing():
    cls = _panel("QUARTZPROBE_PT_child", bl_parent_id="QUARTZPROBE_PT_none")
    with pytest.raises(RegistrationRuntimeError) as exc:
        registry.register_class(cls)
    assert "Registering panel class: parent 'QUARTZPROBE_PT_none' for 'QUARTZPROBE_PT_child' not found" \
        in str(exc.value)
    assert "parent '" in str(exc.value) and "not found" in str(exc.value)


def test_panel_parent_name_uses_rna_name_of_child():
    cls = _panel("QZT_PT_child_cls", bl_idname="QZT_PT_child_id", bl_parent_id="QZT_PT_nothing")
    with pytest.raises(RegistrationRuntimeError, match="for 'QZT_PT_child_id' not found"):
        registry.register_class(cls)


def test_panel_parent_present():
    parent = _panel("QZT_PT_parent")
    registry.register_class(parent)
    child = _panel("QZT_PT_kid", bl_parent_id="QZT_PT_parent")
    registry.register_class(child)
    assert registry.is_registered(child)


def test_panel_parent_must_be_panel():
    menu = type(Menu)("QZT_MT_notpanel", (Menu,), {"bl_label": "M", "draw": lambda s, c: None})
    registry.register_class(menu)
    with pytest.raises(RegistrationRuntimeError, match="not found"):
        registry.register_class(_panel("QZT_PT_kid2", bl_parent_id="QZT_MT_notpanel"))


def test_panel_bad_name_only_warns(capsys):
    cls = _panel("QuartzBadPanel")
    registry.register_class(cls)
    assert registry.is_registered(cls)
    err = capsys.readouterr().err
    assert "'QuartzBadPanel' does not contain '_PT_' with prefix and suffix" in err


def test_panel_tag_needs_prefix_and_suffix(capsys):
    registry.register_class(_panel("_PT_x"))
    registry.register_class(_panel("QZT_PT_"))
    err = capsys.readouterr().err
    assert "'_PT_x'" in err and "'QZT_PT_'" in err


def test_panel_with_own_bl_idname():
    cls = _panel("BadName", bl_idname="QZT_PT_own")
    registry.register_class(cls)
    assert registry.rna_name_of(cls) == "QZT_PT_own"
    assert cls.bl_rna.identifier == "QZT_PT_own"
    assert registry.lookup("QZT_PT_own") is cls


def test_panel_without_bl_idname_uses_class_name():
    cls = _panel("QZT_PT_plain")
    registry.register_class(cls)
    assert registry.rna_name_of(cls) == "QZT_PT_plain"


def test_menu_requirements():
    no_label = type(Menu)("QUARTZPROBE_MT_req", (Menu,), {"draw": lambda s, c: None})
    with pytest.raises(MissingClassAttributeError, match='expected Menu, QUARTZPROBE_MT_req class to have an '
                                                         '"bl_label" attribute'):
        registry.register_class(no_label)
    no_draw = type(Menu)("QUARTZPROBE_MT_req", (Menu,), {"bl_label": "M"})
    with pytest.raises(MissingClassAttributeError, match='"draw" attribute'):
        registry.register_class(no_draw)
    ok = type(Menu)("QZT_MT_ok", (Menu,), {"bl_label": "M", "draw": lambda s, c: None})
    registry.register_class(ok)
    with pytest.raises(ClassValidationError, match='enum "NOPE" not found in'):
        registry.register_class(type(Menu)("QZT_MT_bad", (Menu,), {"bl_label": "M", "draw": lambda s, c: None,
                                                                   "bl_options": {"NOPE"}}))


def test_menu_bad_name_warns(capsys):
    registry.register_class(type(Menu)("QuartzMenu", (Menu,), {"bl_label": "M", "draw": lambda s, c: None}))
    assert "'_MT_'" in capsys.readouterr().err


def test_header_requirements():
    no_space = type(Header)("QUARTZPROBE_HT_req", (Header,), {"draw": lambda s, c: None})
    with pytest.raises(MissingClassAttributeError, match='expected Header, QUARTZPROBE_HT_req class to have an '
                                                         '"bl_space_type" attribute'):
        registry.register_class(no_space)
    no_draw = type(Header)("QUARTZPROBE_HT_req", (Header,), {"bl_space_type": "VIEW_3D"})
    with pytest.raises(MissingClassAttributeError, match='"draw" attribute'):
        registry.register_class(no_draw)
    ok = type(Header)("QZT_HT_ok", (Header,), {"bl_space_type": "VIEW_3D", "draw": lambda s, c: None})
    registry.register_class(ok)
    assert registry.is_registered(ok)
    bad_region = type(Header)("QZT_HT_bad", (Header,), {"bl_space_type": "VIEW_3D", "bl_region_type": "NOPE",
                                                        "draw": lambda s, c: None})
    with pytest.raises(ClassValidationError, match='enum "NOPE"'):
        registry.register_class(bad_region)


def test_uilist_and_addon_preferences_need_nothing(capsys):
    ul = type(UIList)("QZT_UL_empty", (UIList,), {})
    registry.register_class(ul)
    prefs = type(AddonPreferences)("QZTPrefs", (AddonPreferences,), {})
    registry.register_class(prefs)
    pg = type(PropertyGroup)("QZT_PG_empty", (PropertyGroup,), {})
    registry.register_class(pg)
    assert all(registry.is_registered(c) for c in (ul, prefs, pg))
    assert registry.rna_name_of(prefs) == "QZTPrefs"
    assert registry.rna_name_of(pg) == "QZT_PG_empty"
    assert capsys.readouterr().err == ""


def test_uilist_bad_name_warns(capsys):
    registry.register_class(type(UIList)("QuartzList", (UIList,), {}))
    assert "'_UL_'" in capsys.readouterr().err


def test_register_twice():
    cls = _op("QUARTZPROBE_OT_twice", bl_idname="qzt.twice")
    registry.register_class(cls)
    with pytest.raises(RegistrationError) as exc:
        registry.register_class(cls)
    assert str(exc.value) == "register_class(...): already registered as a subclass 'QUARTZPROBE_OT_twice'"
    assert isinstance(exc.value, ValueError)


def test_same_rna_name_replaces_previous():
    log = []

    def make(tag):
        ns = {"bl_idname": "qzt.same", "bl_label": tag, "execute": lambda self, c: {"FINISHED"},
              "register": classmethod(lambda cls: log.append(("register", tag))),
              "unregister": classmethod(lambda cls: log.append(("unregister", tag)))}
        return type(Operator)(f"QZT_OT_same_{tag}", (Operator,), ns)

    first, second = make("a"), make("b")
    registry.register_class(first)
    registry.register_class(second)
    assert not registry.is_registered(first)
    assert "bl_rna" not in first.__dict__
    assert registry.is_registered(second)
    assert registry.operator_class("qzt.same") is second
    assert log == [("register", "a"), ("unregister", "a"), ("register", "b")]
    with pytest.raises(RegistrationRuntimeError, match="missing bl_rna attribute"):
        registry.unregister_class(first)


def test_replaced_class_stays_unregistered_when_new_fails():
    first = _op("QZT_OT_keep_a", bl_idname="qzt.keep")

    class Unreg(PropertyGroup):
        pass

    second = type(Operator)("QZT_OT_keep_b", (Operator,), {
        "bl_idname": "qzt.keep", "bl_label": "B", "__annotations__": {"p": PointerProperty(type=Unreg)}})
    registry.register_class(first)
    with pytest.raises(RegistrationError, match="could not register"):
        registry.register_class(second)
    assert not registry.is_registered(first)
    assert not registry.is_registered(second)
    assert registry.operator_class("qzt.keep") is None


def test_unregister_not_registered_twice_and_plain():
    cls = _op("QZT_OT_un", bl_idname="qzt.un")
    with pytest.raises(RegistrationRuntimeError) as exc:
        registry.unregister_class(cls)
    assert "unregister_class(...):, missing bl_rna attribute from 'StructMeta' instance (may not be registered)" \
        in str(exc.value)
    registry.register_class(cls)
    registry.unregister_class(cls)
    with pytest.raises(RegistrationRuntimeError, match="may not be registered"):
        registry.unregister_class(cls)

    class Plain:
        pass
    with pytest.raises(RegistrationRuntimeError) as exc2:
        registry.unregister_class(Plain)
    assert "missing bl_rna attribute from 'type' instance (may not be registered)" in str(exc2.value)


def test_unregister_builtin_type():
    with pytest.raises(RegistrationRuntimeError, match="missing bl_rna attribute"):
        registry.unregister_class(Operator)
    with pytest.raises(RegistrationRuntimeError, match="missing bl_rna attribute"):
        registry.unregister_class(Event)


def test_register_plain_class():
    class Plain:
        pass
    with pytest.raises(RegistrationRuntimeError) as exc:
        registry.register_class(Plain)
    assert str(exc.value) == ("register_class(...):, missing bl_rna attribute from 'type' instance "
                              "(may not be registered)")


def test_register_non_class():
    with pytest.raises(RegistrationRuntimeError, match="from 'int' instance"):
        registry.register_class(5)


def test_register_builtin_without_registrable_base():
    with pytest.raises(RegistrationRuntimeError, match="missing bl_rna attribute"):
        registry.register_class(Event)
    with pytest.raises(RegistrationRuntimeError, match="(may not be registered)"):
        registry.register_class(type(Struct)("QZTPlainStruct", (Struct,), {}))


@pytest.mark.parametrize("cls", [Operator, OperatorFileListElement, Panel, PropertyGroup])
def test_register_base_or_builtin_with_registrable_base(cls):
    with pytest.raises(RegistrationError, match="already registered as a subclass"):
        registry.register_class(cls)


def test_registration_is_atomic():
    class Unregistered(PropertyGroup):
        pass

    cls = type(PropertyGroup)("QZT_PG_atomic", (PropertyGroup,), {
        "__annotations__": {"a": IntProperty(), "b": PointerProperty(type=Unregistered)}})
    with pytest.raises(RegistrationError) as exc:
        registry.register_class(cls)
    assert "could not register" in str(exc.value)
    assert "bl_rna" not in cls.__dict__
    assert registry.lookup("QZT_PG_atomic") is None
    assert get_property(cls, "a") is None
    assert not registry.is_registered(cls)
    assert cls not in list(registry.iter_classes())


def test_atomic_when_prepare_fails(monkeypatch):
    from quartz.types import operator as opmod

    def boom(cls, name):
        raise RuntimeError("prepare failed")

    monkeypatch.setattr(registry._BASES[Operator], "prepare", boom)
    cls = type(Operator)("QZT_OT_prep", (Operator,), {"bl_idname": "qzt.prep", "bl_label": "P",
                                                       "__annotations__": {"n": IntProperty()}})
    with pytest.raises(RuntimeError, match="prepare failed"):
        registry.register_class(cls)
    assert get_property(cls, "n") is None and "bl_rna" not in cls.__dict__
    assert registry.operator_class("qzt.prep") is None
    assert opmod


def test_classmethod_hooks_order(blender_facts):
    log = []

    class QZT_PG_hooks(PropertyGroup):
        @classmethod
        def register(cls):
            log.append("register")

        @classmethod
        def unregister(cls):
            log.append("unregister")

    registry.register_class(QZT_PG_hooks)
    registry.unregister_class(QZT_PG_hooks)
    assert log == ["register", "unregister"] == blender_facts["register.classmethod_hooks"]


def test_register_hook_exception_keeps_class_registered():
    class QZT_PG_boom(PropertyGroup):
        @classmethod
        def register(cls):
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        registry.register_class(QZT_PG_boom)
    assert registry.is_registered(QZT_PG_boom)


def test_unregister_hook_exception_after_cleanup():
    class QZT_PG_boom2(PropertyGroup):
        x: IntProperty()

        @classmethod
        def unregister(cls):
            raise ValueError("late")

    registry.register_class(QZT_PG_boom2)
    with pytest.raises(ValueError, match="late"):
        registry.unregister_class(QZT_PG_boom2)
    assert not registry.is_registered(QZT_PG_boom2)
    assert "bl_rna" not in QZT_PG_boom2.__dict__
    assert get_property(QZT_PG_boom2, "x") is None


def test_register_hook_of_mixin_below_base_is_not_called():
    log = []

    class Mixin:
        @classmethod
        def register(cls):
            log.append("mixin")

    cls = type(PropertyGroup)("QZT_PG_mixin", (PropertyGroup, Mixin), {})
    registry.register_class(cls)
    assert log == []


def test_is_registered_and_structmeta():
    cls = _op("QZT_OT_isreg", bl_idname="qzt.isreg")
    assert not registry.is_registered(cls)
    assert not cls.is_registered
    registry.register_class(cls)
    assert registry.is_registered(cls) and cls.is_registered
    registry.unregister_class(cls)
    assert not registry.is_registered(cls) and not cls.is_registered
    assert not registry.is_registered(Operator)
    assert Operator.is_registered
    assert not registry.is_registered("not a class")


def test_operator_name_round_trip():
    assert registry.operator_rna_name("mesh.primitive_cube_add") == "MESH_OT_primitive_cube_add"
    assert registry.operator_idname_py("MESH_OT_primitive_cube_add") == "mesh.primitive_cube_add"
    for idname in ("qzt.x", "object.select_all", "my_mod.do_it"):
        assert registry.operator_idname_py(registry.operator_rna_name(idname)) == idname
    assert registry.operator_rna_name("a.b.c") == "A_OT_b.c"
    with pytest.raises(ValueError):
        registry.operator_rna_name("nodot")
    with pytest.raises(ValueError):
        registry.operator_idname_py("NO_OT")
    with pytest.raises(ValueError):
        registry.operator_idname_py("plain")


def test_validate_operator_idname_direct():
    registry.validate_operator_idname("qzt.ok_1", "QZT_OT_ok")
    with pytest.raises(RegistrationRuntimeError, match="Invalid character at position 3"):
        registry.validate_operator_idname("qzt-x.y", "C")
    with pytest.raises(RegistrationRuntimeError, match="Must contain 1 '.' character"):
        registry.validate_operator_idname("", "C")
    with pytest.raises(RegistrationRuntimeError, match="Registering operator class 'C', invalid bl_idname"):
        registry.validate_operator_idname("A.b", "C")
