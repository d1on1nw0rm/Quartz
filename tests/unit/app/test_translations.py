import types

import quartz.app.translations as tr


def test_contexts_count():
    assert len(list(tr.contexts)) == 60


def test_contexts_attr():
    assert tr.contexts.default == "*"
    try:
        tr.contexts.nope
    except AttributeError:
        pass
    else:
        raise AssertionError("expected AttributeError")


def test_pgettext_identity():
    assert tr.pgettext("Hello") == "Hello"


def test_pgettext_registered():
    tr.register("m", {"pt_BR": {("*", "Hello"): "Ola"}, "en_US": {("*", "Hello"): "Hola"}})
    try:
        assert tr.pgettext("Hello") == "Hello"
        tr.set_locale("pt_BR")
        assert tr.pgettext("Hello") == "Ola"
        assert tr.pgettext("Hello", "ctx") == "Ola"
    finally:
        tr.set_locale("en_US")
        tr.unregister("m")


def test_locale_explode():
    assert tr.locale_explode("pt_BR@euro") == ("pt", "BR", "euro", "pt_BR", "pt@euro")
    assert tr.locale_explode("pt_BR") == ("pt", "BR", None, "pt_BR", None)
    assert tr.locale_explode("") == (None, None, None, None, None)


def test_contexts_c_to_py():
    assert tr.contexts_C_to_py["BLT_I18NCONTEXT_DEFAULT"] == "default"


def test_register_accepts_non_dict_mapping():
    inner = types.MappingProxyType({("*", "Add"): "Adicionar", ("Operator", "Move"): "Mover"})
    tr.register("mapping_mod", types.MappingProxyType({"pt_BR": inner}))
    old = tr.locale
    try:
        tr.set_locale("pt_BR")
        assert tr.pgettext("Add") == "Adicionar"
        assert tr.pgettext("Add", "Operator") == "Adicionar"
        assert tr.pgettext("Move", "Operator") == "Mover"
        assert tr.pgettext("Move") == "Move"
        tr.set_locale("en_US")
        assert tr.pgettext("Add") == "Add"
    finally:
        tr.set_locale(old)
        tr.unregister("mapping_mod")
