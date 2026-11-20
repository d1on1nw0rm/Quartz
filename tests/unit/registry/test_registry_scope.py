import pytest

from quartz import registry
from quartz.app import settings
from quartz.errors import RegistrationRuntimeError
from quartz.props import IntProperty, StringProperty
from quartz.rna import PropertyGroup, Struct, builtin_struct, hooks
from quartz.rna.annotations import get_property
import quartz.types.ui as ui_types
from quartz.types.operator import Operator
from quartz.types.prefs import AddonPreferences
from quartz.types.stubs import HydraRenderEngine, RenderEngine
from quartz.types.ui import Menu, Panel, UIList


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


def _op(name, idname, **extra):
    ns = {"bl_idname": idname, "bl_label": name, "execute": lambda self, context: {"FINISHED"}}
    ns.update(extra)
    return type(Operator)(name, (Operator,), ns)


def _pg(name, **ann):
    return type(PropertyGroup)(name, (PropertyGroup,), {"__annotations__": dict(ann)})


def _panel(name, **extra):
    ns = {"bl_label": name, "bl_space_type": "VIEW_3D", "bl_region_type": "UI", "draw": lambda self, ctx: None}
    ns.update(extra)
    return type(Panel)(name, (Panel,), ns)


def _menu(name):
    return type(Menu)(name, (Menu,), {"bl_label": name, "draw": lambda self, ctx: None})


def test_owner_scope_nested_and_restored_after_exception():
    assert registry.current_owner() is None
    with registry.owner_scope("a"):
        assert registry.current_owner() == "a"
        with pytest.raises(ValueError):
            with registry.owner_scope("b"):
                assert registry.current_owner() == "b"
                raise ValueError
        assert registry.current_owner() == "a"
        with registry.owner_scope(None):
            assert registry.current_owner() is None
        assert registry.current_owner() == "a"
    assert registry.current_owner() is None


def test_owner_of_and_classes_owned_by():
    a, b, c = _pg("QZT_PG_a"), _pg("QZT_PG_b"), _pg("QZT_PG_c")
    with registry.owner_scope("mod_one"):
        registry.register_class(a)
        registry.register_class(b)
    registry.register_class(c)
    assert registry.owner_of(a) == "mod_one"
    assert registry.owner_of(c) is None
    assert registry.owner_of(_pg("QZT_PG_unreg")) is None
    assert registry.classes_owned_by("mod_one") == [a, b]
    registry.unregister_class(a)
    assert registry.classes_owned_by("mod_one") == [b]
    assert registry.owner_of(a) is None


def test_counts_by_base_ignores_quartz_owners():
    before = registry.counts_by_base()
    with registry.owner_scope("quartz.builtin"):
        registry.register_class(_op("QZT_OT_builtin", "qzt.builtin"))
    with registry.owner_scope("quartz.placeholder"):
        registry.register_class(_menu("QZT_MT_ph"))
    with registry.owner_scope("user_mod"):
        registry.register_class(_op("QZT_OT_user", "qzt.user"))
        registry.register_class(_panel("QZT_PT_user"))
        registry.register_class(_pg("QZT_PG_user"))
    registry.register_class(_menu("QZT_MT_free"))
    after = registry.counts_by_base()
    assert after.get("Operator", 0) - before.get("Operator", 0) == 1
    assert after.get("Panel", 0) - before.get("Panel", 0) == 1
    assert after.get("PropertyGroup", 0) - before.get("PropertyGroup", 0) == 1
    assert after.get("Menu", 0) - before.get("Menu", 0) == 1
    assert all(v > 0 for v in after.values())


def test_counts_by_base_only_positive():
    counts = registry.counts_by_base()
    assert "Header" not in counts or counts["Header"] > 0


def test_type_props_owned_by():
    target = _pg("QZT_PG_target")
    registry.register_class(target)
    with registry.owner_scope("addon_x"):
        target.qzt_dyn = IntProperty(default=4)
        target.qzt_dyn2 = StringProperty()
    target.qzt_free = IntProperty()
    assert registry.type_props_owned_by("addon_x") == [(target, "qzt_dyn"), (target, "qzt_dyn2")]
    del target.qzt_dyn
    assert registry.type_props_owned_by("addon_x") == [(target, "qzt_dyn2")]
    registry.unregister_class(target)
    assert registry.type_props_owned_by("addon_x") == []


def test_dynamic_props_without_install_hooks_not_recorded():
    hooks.install(on_type_property_defined=None, on_type_property_removed=None)
    target = _pg("QZT_PG_nohooks")
    registry.register_class(target)
    with registry.owner_scope("addon_y"):
        target.qzt_dyn = IntProperty()
    assert registry.type_props_owned_by("addon_y") == []
    snap = registry.snapshot()
    assert all(rec[0] is not target for rec in snap.props)


def test_install_hooks_twice_does_not_duplicate():
    registry.install_hooks()
    registry.install_hooks()
    target = _pg("QZT_PG_twice")
    registry.register_class(target)
    with registry.owner_scope("dup"):
        target.qzt_a = IntProperty()
        target.qzt_a = IntProperty(default=2)
    assert registry.type_props_owned_by("dup") == [(target, "qzt_a")]


def test_subscribe_and_cancel():
    events = []
    cancel = registry.subscribe(lambda ev, cls: events.append((ev, cls.__name__)))
    a = _pg("QZT_PG_sub")
    registry.register_class(a)
    registry.unregister_class(a)
    assert events == [("register", "QZT_PG_sub"), ("unregister", "QZT_PG_sub")]
    cancel()
    cancel()
    registry.register_class(a)
    assert len(events) == 2


def test_subscriber_exception_is_printed(capsys):
    def bad(ev, cls):
        raise RuntimeError("subscriber failure")

    cancel = registry.subscribe(bad)
    try:
        cls = _pg("QZT_PG_badsub")
        registry.register_class(cls)
        assert registry.is_registered(cls)
        assert "subscriber failure" in capsys.readouterr().err
    finally:
        cancel()


def test_iter_classes_order_and_filter():
    base = list(registry.iter_classes())
    a, p, o = _pg("QZT_PG_i1"), _panel("QZT_PT_i2"), _op("QZT_OT_i3", "qzt.i3")
    for c in (a, p, o):
        registry.register_class(c)
    assert list(registry.iter_classes())[len(base):] == [a, p, o]
    assert [c for c in registry.iter_classes(Panel) if c.__name__.startswith("QZT_")] == [p]
    assert o in list(registry.iter_classes(Operator))
    assert a in list(registry.iter_classes(PropertyGroup))


def test_iter_operators_submodules_and_operator_class():
    a = _op("QZT_OT_one", "qzt_b.one")
    b = _op("QZT_OT_two", "qzt_a.two")
    registry.register_class(a)
    registry.register_class(b)
    ops = [(i, c) for i, c in registry.iter_operators() if i.startswith("qzt_")]
    assert ops == [("qzt_b.one", a), ("qzt_a.two", b)]
    subs = registry.operator_submodules()
    assert subs == sorted(subs) and "qzt_a" in subs and "qzt_b" in subs
    assert registry.operator_class("qzt_b.one") is a
    assert registry.operator_class("QZT_B_OT_one") is a
    assert registry.operator_class("qzt_b.missing") is None
    assert registry.operator_class(None) is None


def test_lookup_with_and_without_resolver():
    made = []

    def resolver(name):
        made.append(name)
        return Struct if name == "Resolvable" else None

    assert registry.lookup("Resolvable") is None
    registry.set_missing_type_resolver(resolver)
    try:
        assert registry.lookup("Resolvable") is Struct
        assert registry.lookup("Resolvable", resolve=False) is None
        assert registry.lookup("Other") is None
        assert made == ["Resolvable", "Other"]
        pg = _pg("QZT_PG_look")
        registry.register_class(pg)
        assert registry.lookup("QZT_PG_look") is pg
        assert made == ["Resolvable", "Other"]
    finally:
        registry.set_missing_type_resolver(None)
    assert registry.lookup("Resolvable") is None
    assert registry.lookup("Operator") is None


def test_snapshot_restore_undoes_and_restores():
    calls = []

    def hooks_ns():
        return {"register": classmethod(lambda cls: calls.append("reg")),
                "unregister": classmethod(lambda cls: calls.append("unreg"))}

    a = type(PropertyGroup)("QZT_PG_s1", (PropertyGroup,), hooks_ns())
    b = type(PropertyGroup)("QZT_PG_s2", (PropertyGroup,), hooks_ns())
    c = type(PropertyGroup)("QZT_PG_s3", (PropertyGroup,), hooks_ns())
    with registry.owner_scope("own_a"):
        registry.register_class(a)
    with registry.owner_scope("own_b"):
        registry.register_class(b)
    registry.register_class(c)
    a.qzt_extra = IntProperty(default=1)
    with registry.owner_scope("own_props"):
        a.qzt_owned = IntProperty(default=7)
    order_before = list(registry.iter_classes())
    snap = registry.snapshot()
    calls.clear()

    registry.unregister_class(b)
    d = type(PropertyGroup)("QZT_PG_s4", (PropertyGroup,), hooks_ns())
    with registry.owner_scope("own_d"):
        registry.register_class(d)
    del a.qzt_owned
    with registry.owner_scope("someone_else"):
        a.qzt_new = IntProperty()
    calls.clear()

    registry.restore(snap)
    assert calls == []
    assert not registry.is_registered(d)
    assert registry.is_registered(b)
    assert b.bl_rna.identifier == "QZT_PG_s2"
    assert registry.owner_of(b) == "own_b"
    assert registry.owner_of(a) == "own_a"
    assert list(registry.iter_classes()) == order_before
    assert get_property(a, "qzt_new") is None
    assert get_property(a, "qzt_owned") is not None
    assert get_property(a, "qzt_extra") is not None
    assert registry.type_props_owned_by("own_props") == [(a, "qzt_owned")]
    assert registry.type_props_owned_by("someone_else") == []

    registry.restore(snap)
    assert list(registry.iter_classes()) == order_before
    assert registry.type_props_owned_by("own_props") == [(a, "qzt_owned")]


def test_restore_reregisters_with_same_identity_and_props():
    class QZT_PG_ident(PropertyGroup):
        value: IntProperty(default=5)

    registry.register_class(QZT_PG_ident)
    snap = registry.snapshot()
    registry.unregister_class(QZT_PG_ident)
    assert get_property(QZT_PG_ident, "value") is None
    registry.restore(snap)
    assert registry.lookup("QZT_PG_ident") is QZT_PG_ident
    assert get_property(QZT_PG_ident, "value") is not None
    assert QZT_PG_ident().value == 5


def test_restore_reregisters_operator_property_class():
    op = _op("QZT_OT_restore", "qzt.restore", __annotations__={"n": IntProperty(default=3)})
    registry.register_class(op)
    snap = registry.snapshot()
    registry.unregister_class(op)
    with pytest.raises(RegistrationRuntimeError):
        op.q_properties_class()
    registry.restore(snap)
    assert op.q_properties_class().bl_rna.identifier == "QZT_OT_restore"
    assert op.q_new_properties().n == 3


def test_restore_order_of_classes_registered_the_whole_time():
    a, b = _pg("QZT_PG_o1"), _pg("QZT_PG_o2")
    registry.register_class(a)
    registry.register_class(b)
    snap = registry.snapshot()
    registry.unregister_class(a)
    registry.register_class(a)
    assert list(registry.iter_classes())[-2:] == [b, a]
    registry.restore(snap)
    assert list(registry.iter_classes())[-2:] == [a, b]


def test_restore_dynamic_props_keep_snapshot_owner():
    target = _pg("QZT_PG_dynown")
    registry.register_class(target)
    with registry.owner_scope("orig"):
        target.qzt_p = IntProperty()
    snap = registry.snapshot()
    del target.qzt_p
    with registry.owner_scope("current_owner"):
        registry.restore(snap)
    assert registry.type_props_owned_by("orig") == [(target, "qzt_p")]
    assert registry.type_props_owned_by("current_owner") == []


def test_restore_ui_extensions():
    menu = _menu("QZT_MT_ext")
    registry.register_class(menu)
    snap = registry.snapshot()

    def extra(self, context):
        pass
    menu.append(extra)
    assert menu.is_extended()
    registry.restore(snap)
    assert not menu.is_extended()
    assert ui_types.draw_sequence(menu) == (menu.draw,)


def test_restore_rejects_foreign_object():
    with pytest.raises(TypeError):
        registry.restore(object())


def test_reentrant_registration_through_resolver():
    def resolver(name):
        if name == "QZT_PT_auto_parent":
            parent = _panel("QZT_PT_auto_parent")
            registry.register_class(parent)
            return parent
        return None

    registry.set_missing_type_resolver(resolver)
    try:
        child = _panel("QZT_PT_auto_child", bl_parent_id="QZT_PT_auto_parent")
        registry.register_class(child)
        assert registry.is_registered(child)
        assert registry.is_registered(registry.lookup("QZT_PT_auto_parent"))
    finally:
        registry.set_missing_type_resolver(None)


def test_registrable_base_of():
    assert registry.registrable_base_of(Operator) is Operator
    assert registry.registrable_base_of(_op("QZT_OT_rb", "qzt.rb")) is Operator
    sub = type(HydraRenderEngine)("QZTHydra", (HydraRenderEngine,), {})
    assert registry.registrable_base_of(sub) is RenderEngine
    assert registry.registrable_base_of(Struct) is None
    assert registry.registrable_base_of(int) is None
    assert registry.registrable_base_of("x") is None


def test_iter_bases_order():
    bases = list(registry.iter_bases())
    assert bases[0] is PropertyGroup
    for b in (Operator, Panel, Menu, UIList, AddonPreferences):
        assert b in bases
    assert bases.index(Panel) < bases.index(Menu) < bases.index(UIList)


def test_base_callbacks_lookup():
    assert registry.base_callbacks(PropertyGroup) == {}
    with pytest.raises(KeyError):
        registry.base_callbacks(Struct)
    view = registry.base_callbacks(Operator)
    with pytest.raises(TypeError):
        view["poll"] = (False, False)


def test_register_base_type_errors():
    with pytest.raises(TypeError):
        registry.register_base(int)

    class NotBuiltin(Struct):
        pass
    with pytest.raises(TypeError):
        registry.register_base(NotBuiltin)


def test_register_base_replaces_entry_idempotently():
    @builtin_struct
    class QZTCustomBase(Struct):
        _q_registrable = True

    try:
        registry.register_base(QZTCustomBase, required=("a",))
        registry.register_base(QZTCustomBase, required=())
        bases = list(registry.iter_bases())
        assert bases.count(QZTCustomBase) == 1
        sub = type(QZTCustomBase)("QZTCustomSub", (QZTCustomBase,), {})
        registry.register_class(sub)
        assert registry.rna_name_of(sub) == "QZTCustomSub"
    finally:
        registry._BASES.pop(QZTCustomBase, None)


def test_rna_name_of_variants():
    reg = _panel("QZT_PT_reg", bl_idname="QZT_PT_named")
    registry.register_class(reg)
    assert registry.rna_name_of(reg) == "QZT_PT_named"
    assert registry.rna_name_of(_panel("QZT_PT_unreg")) == "QZT_PT_unreg"
    assert registry.rna_name_of(_op("Whatever", "qzt.x")) == "QZT_OT_x"
    assert registry.rna_name_of(_op("NoDotOp", "nodot")) == "NoDotOp"

    class Plain:
        pass
    assert registry.rna_name_of(Plain) == "Plain"
    assert registry.rna_name_of(5) == "int"
