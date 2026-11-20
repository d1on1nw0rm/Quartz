import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HDR = '"""x."""\n# Quartz - author: D1on1n\n'


def _load_checker():
    spec = importlib.util.spec_from_file_location("_layering_checker", HERE / "test_layering.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _violations(tmp_path, monkeypatch, files: dict[str, str]) -> str:
    checker = _load_checker()
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(HDR + text, encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    try:
        checker.test_layering()
    except AssertionError as exc:
        return str(exc)
    return ""


@pytest.mark.parametrize("pkg", ["quartz.types", "quartz.utils", "quartz.io", "quartz.operators"])
def test_l2_package_names_are_l2(pkg):
    assert _load_checker()._quartz_group(pkg) == "L2"


@pytest.mark.parametrize("pkg", ["quartz.compat", "quartz.extras", "quartz.bmesh", "quartz.addons"])
def test_l3_package_names_are_l3(pkg):
    assert _load_checker()._quartz_group(pkg) == "L3"


def test_prefix_lookalikes_not_grouped():
    checker = _load_checker()
    assert checker._quartz_group("quartz.typesx") is None
    assert checker._quartz_group("quartz.application") is None


def test_l2_may_import_l2_package(tmp_path, monkeypatch):
    v = _violations(tmp_path, monkeypatch, {
        "quartz/types/__init__.py": "from quartz.types.id import ID\n",
        "quartz/session.py": "from quartz.types import id\nimport quartz.types\nimport quartz.utils\n",
    })
    assert v == "", v


@pytest.mark.parametrize("rel", ["quartz/types/__init__.py", "quartz/utils/__init__.py",
                                 "quartz/io/__init__.py"])
def test_l2_package_init_cannot_import_l3(tmp_path, monkeypatch, rel):
    v = _violations(tmp_path, monkeypatch, {rel: "import quartz.cli\n"})
    assert rel in v


def test_facade_function_level_import_allowed(tmp_path, monkeypatch):
    v = _violations(tmp_path, monkeypatch, {
        "quartz/__init__.py": ("from quartz._version import VERSION\n"
                               "def __getattr__(n):\n    import quartz.session\n    return quartz.session\n"),
    })
    assert v == "", v


@pytest.mark.parametrize("text", [
    "import quartz.session\n",
    "if True:\n    import quartz.session\n",
    "try:\n    import quartz.session\nexcept ImportError:\n    pass\n",
])
def test_facade_module_level_import_still_flagged(tmp_path, monkeypatch, text):
    v = _violations(tmp_path, monkeypatch, {"quartz/__init__.py": text})
    assert "quartz/__init__.py" in v


def test_non_facade_function_level_import_still_flagged(tmp_path, monkeypatch):
    v = _violations(tmp_path, monkeypatch, {"quartz/math/x.py": "def f():\n    import quartz.rna\n"})
    assert "quartz/math/x.py" in v


def test_relative_import_in_package_init_resolves(tmp_path, monkeypatch):
    v = _violations(tmp_path, monkeypatch, {"quartz/app/__init__.py": "from . import handlers\n"})
    assert v == "", v


def test_real_facade_only_module_level_import_is_version():
    import ast

    tree = ast.parse((HERE.parents[1] / "quartz" / "__init__.py").read_text(encoding="utf-8"))
    found = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
    assert found == ["quartz._version"], found


def test_facade_lazy_attributes_still_work():
    import quartz

    assert quartz.msgbus.__name__ == "quartz.app.msgbus"
    assert quartz.app.__name__ == "quartz.app"
    with pytest.raises(AttributeError):
        quartz.no_such_attribute_xyz
