import ast
import dataclasses
import importlib
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import time
import tomllib
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PY = sys.executable
FACTS = json.loads((ROOT / "data" / "blender_facts_judge.json").read_text(encoding="utf-8"))

BLENDER_39 = {
    "animation_playback_pre", "animation_playback_post", "annotation_pre", "annotation_post",
    "blend_import_pre", "blend_import_post", "composite_pre", "composite_post", "composite_cancel",
    "depsgraph_update_pre", "depsgraph_update_post", "exit_pre", "frame_change_pre",
    "frame_change_post", "load_factory_preferences_post", "load_factory_startup_post", "load_pre",
    "load_post", "load_post_fail", "object_bake_pre", "object_bake_complete", "object_bake_cancel",
    "redo_pre", "redo_post", "render_init", "render_pre", "render_post", "render_stats",
    "render_write", "render_complete", "render_cancel", "save_pre", "save_post", "save_post_fail",
    "translation_update_post", "undo_pre", "undo_post", "version_update", "xr_session_start_pre",
}
QUARTZ_5 = ("startup_post", "shutdown_pre", "shutdown_post", "addon_enable_post", "addon_disable_post")


def _load_file(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(code, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    r = subprocess.run([PY, "-c", code], cwd=str(ROOT), capture_output=True, text=True, env=e, timeout=60)
    return r


def _module_level_imports(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.append(("." * node.level) + (node.module or ""))
    return out



@pytest.fixture
def handlers():
    from quartz.app import handlers as h
    snap = h.snapshot()
    for lst in h.all_lists().values():
        lst[:] = []
    yield h
    h.restore(snap)


@pytest.fixture
def timers():
    from quartz.app import timers as t
    snap = t.snapshot()
    t.clear()
    yield t
    t.restore(snap)


@pytest.fixture
def msgbus():
    from quartz.app import msgbus as m
    snap = m.snapshot()
    m.clear()
    yield m
    m.restore(snap)


@pytest.fixture
def translations():
    from quartz.app import translations as tr
    old_locale = tr.locale
    yield tr
    tr.set_locale(old_locale)
    tr.locale = old_locale


@pytest.fixture
def settings_mod():
    from quartz.app import settings as s
    snap = s.snapshot()
    yield s
    s.restore(snap)


@pytest.fixture
def paths(monkeypatch, tmp_path):
    from quartz.app import paths as p
    monkeypatch.setenv("QUARTZ_USER_DIR", str(tmp_path / "qu"))
    monkeypatch.delenv("QUARTZ_COMPAT_DIR", raising=False)
    p.reset()
    yield p
    p.reset()


@pytest.fixture
def qpath():
    from quartz import path as qp
    yield qp
    qp.set_blend_filepath_provider(None)



EXPECTED_PYPROJECT = {
    "project": {
        "name": "quartz",
        "version": "1.0.0",
        "description": "Quartz - headless 3D application core (Cinema 4D x Blender fusion), milestone 1",
        "authors": [{"name": "D1on1n"}],
        "requires-python": ">=3.13",
        "dependencies": ["numpy"],
    },
    "tool": {"pytest": {"ini_options": {
        "testpaths": ["tests"],
        "pythonpath": ["."],
        "addopts": "--import-mode=importlib",
        "markers": [
            "slow: slow test (still runs by default)",
            "blender: needs the Blender executable; runs only with QUARTZ_RUN_BLENDER=1",
            "sweep: add-on sweep over the Blender scripts corpus; runs only with QUARTZ_RUN_SWEEP=1",
            "corpus: reads the Blender scripts directory (read-only); skipped when missing",
        ],
    }}},
}


def _pyproject():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_pyproject_exact_content():
    assert _pyproject() == EXPECTED_PYPROJECT


def test_pyproject_no_build_system():
    assert "build-system" not in _pyproject()


@pytest.mark.parametrize("key", ["name", "version", "description", "authors", "requires-python", "dependencies"])
def test_pyproject_project_keys(key):
    assert _pyproject()["project"][key] == EXPECTED_PYPROJECT["project"][key]


@pytest.mark.parametrize("key", ["testpaths", "pythonpath", "addopts", "markers"])
def test_pyproject_pytest_keys(key):
    assert _pyproject()["tool"]["pytest"]["ini_options"][key] == EXPECTED_PYPROJECT["tool"]["pytest"]["ini_options"][key]



@pytest.fixture(scope="module")
def conftest_mod():
    return _load_file("_audit_conftest", "tests/conftest.py")


def _comment_and_docstring_lines(src):
    import io
    import tokenize
    found = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT and not (tok.start[0] == 1 and tok.string.startswith("#!")):
            found.append(tok.start[0])
    for node in ast.walk(ast.parse(src)):
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field, None)
            if not isinstance(stmts, list):
                continue
            for stmt in stmts:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    found.append(stmt.lineno)
    return found


def test_conftest_has_no_comments_or_docstrings():
    src = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert _comment_and_docstring_lines(src) == []


def test_conftest_project_root(conftest_mod):
    assert conftest_mod.PROJECT_ROOT == ROOT
    assert isinstance(conftest_mod.PROJECT_ROOT, Path)


@pytest.mark.parametrize("name,rel", [
    ("DUMP_PATH", "data/blender_api_dump.json"),
    ("USAGE_PATH", "data/bpy_usage.json"),
    ("FACTS_PATH", "data/blender_facts_judge.json"),
    ("FIXTURES_DIR", "tests/fixtures"),
])
def test_conftest_data_paths(conftest_mod, name, rel):
    v = getattr(conftest_mod, name)
    assert isinstance(v, Path)
    assert v == ROOT / rel


def test_conftest_blender_defaults(monkeypatch):
    monkeypatch.delenv("QUARTZ_BLENDER_EXE", raising=False)
    monkeypatch.delenv("QUARTZ_BLENDER_SCRIPTS", raising=False)
    m = _load_file("_audit_conftest_d", "tests/conftest.py")
    assert m.BLENDER_EXE == Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
    assert m.BLENDER_SCRIPTS == Path("C:/Program Files/Blender Foundation/Blender 5.2/5.2/scripts")


def test_conftest_blender_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("QUARTZ_BLENDER_EXE", str(tmp_path / "b.exe"))
    monkeypatch.setenv("QUARTZ_BLENDER_SCRIPTS", str(tmp_path / "scr"))
    m = _load_file("_audit_conftest_e", "tests/conftest.py")
    assert m.BLENDER_EXE == tmp_path / "b.exe"
    assert m.BLENDER_SCRIPTS == tmp_path / "scr"


def test_conftest_no_module_level_quartz_import():
    imps = _module_level_imports(ROOT / "tests" / "conftest.py")
    assert not [i for i in imps if i == "quartz" or i.startswith("quartz.")]


class _FakeOption:
    def __init__(self, basetemp):
        self.basetemp = basetemp


class _FakeConfig:
    def __init__(self, basetemp):
        self.option = _FakeOption(basetemp)


def test_conftest_configure_sets_basetemp(conftest_mod):
    cfg = _FakeConfig(None)
    conftest_mod.pytest_configure(cfg)
    assert cfg.option.basetemp == str(ROOT / "tmp" / "pytest" / f"run-{os.getpid()}")


def test_conftest_configure_keeps_basetemp(conftest_mod):
    cfg = _FakeConfig("X:/given")
    conftest_mod.pytest_configure(cfg)
    assert cfg.option.basetemp == "X:/given"


class _FakeItem:
    def __init__(self, *marks):
        self._marks = set(marks)
        self.added = []

    def get_closest_marker(self, name):
        return object() if name in self._marks else None

    def iter_markers(self, name=None):
        return [types.SimpleNamespace(name=m) for m in self._marks if name in (None, m)]

    def add_marker(self, m):
        self.added.append(m)


def _skipped(item):
    for m in item.added:
        mark = getattr(m, "mark", m)
        if getattr(mark, "name", None) == "skip":
            return True
    return False


def _modify(conftest_mod, monkeypatch, tmp_path, *, exe_exists, scripts_exists, run_blender, run_sweep, marks):
    exe = tmp_path / "blender.exe"
    scr = tmp_path / "scripts"
    if exe_exists:
        exe.write_text("x")
    if scripts_exists:
        scr.mkdir()
    monkeypatch.setattr(conftest_mod, "BLENDER_EXE", exe)
    monkeypatch.setattr(conftest_mod, "BLENDER_SCRIPTS", scr)
    if run_blender:
        monkeypatch.setenv("QUARTZ_RUN_BLENDER", "1")
    else:
        monkeypatch.delenv("QUARTZ_RUN_BLENDER", raising=False)
    if run_sweep:
        monkeypatch.setenv("QUARTZ_RUN_SWEEP", "1")
    else:
        monkeypatch.delenv("QUARTZ_RUN_SWEEP", raising=False)
    item = _FakeItem(*marks)
    conftest_mod.pytest_collection_modifyitems(None, [item])
    return _skipped(item)


@pytest.mark.parametrize("exe_exists,run,expect_skip", [
    (True, True, False), (True, False, True), (False, True, True), (False, False, True)])
def test_conftest_blender_marker(conftest_mod, monkeypatch, tmp_path, exe_exists, run, expect_skip):
    assert _modify(conftest_mod, monkeypatch, tmp_path, exe_exists=exe_exists, scripts_exists=True,
                   run_blender=run, run_sweep=False, marks=["blender"]) is expect_skip


@pytest.mark.parametrize("scr_exists,run,expect_skip", [
    (True, True, False), (True, False, True), (False, True, True), (False, False, True)])
def test_conftest_sweep_marker(conftest_mod, monkeypatch, tmp_path, scr_exists, run, expect_skip):
    assert _modify(conftest_mod, monkeypatch, tmp_path, exe_exists=True, scripts_exists=scr_exists,
                   run_blender=False, run_sweep=run, marks=["sweep"]) is expect_skip


@pytest.mark.parametrize("scr_exists,expect_skip", [(True, False), (False, True)])
def test_conftest_corpus_marker(conftest_mod, monkeypatch, tmp_path, scr_exists, expect_skip):
    assert _modify(conftest_mod, monkeypatch, tmp_path, exe_exists=False, scripts_exists=scr_exists,
                   run_blender=False, run_sweep=False, marks=["corpus"]) is expect_skip


def test_conftest_unmarked_not_skipped(conftest_mod, monkeypatch, tmp_path):
    assert _modify(conftest_mod, monkeypatch, tmp_path, exe_exists=False, scripts_exists=False,
                   run_blender=False, run_sweep=False, marks=["slow"]) is False


@pytest.mark.parametrize("name,scope", [
    ("project_root", "session"), ("fixtures_dir", "session"), ("blender_dump", "session"),
    ("blender_usage", "session"), ("blender_facts", "session"), ("blender_exe", "function"),
    ("blender_scripts", "function"), ("qz_user_dir", "function"), ("qz", "function"),
    ("qz_empty", "function"), ("bpy", "function"), ("bpy_lenient", "function"),
])
def test_conftest_fixture_scopes(conftest_mod, name, scope):
    fx = getattr(conftest_mod, name)
    marker = getattr(fx, "_fixture_function_marker", None) or getattr(fx, "_pytestfixturefunction", None)
    assert marker is not None, f"{name} is not a fixture"
    assert marker.scope == scope


def _fixture_fn(conftest_mod, name):
    fx = getattr(conftest_mod, name)
    return fx._get_wrapped_function() if hasattr(fx, "_get_wrapped_function") else fx.__wrapped__


def test_conftest_simple_fixture_values(conftest_mod):
    assert _fixture_fn(conftest_mod, "project_root")() == ROOT
    assert _fixture_fn(conftest_mod, "fixtures_dir")() == ROOT / "tests" / "fixtures"
    facts = _fixture_fn(conftest_mod, "blender_facts")()
    assert isinstance(facts, dict) and facts == FACTS


def test_conftest_blender_exe_skips_when_missing(conftest_mod, monkeypatch, tmp_path):
    monkeypatch.setattr(conftest_mod, "BLENDER_EXE", tmp_path / "nope.exe")
    with pytest.raises(pytest.skip.Exception):
        _fixture_fn(conftest_mod, "blender_exe")()


def test_conftest_blender_scripts_skips_when_missing(conftest_mod, monkeypatch, tmp_path):
    monkeypatch.setattr(conftest_mod, "BLENDER_SCRIPTS", tmp_path / "nope")
    with pytest.raises(pytest.skip.Exception):
        _fixture_fn(conftest_mod, "blender_scripts")()


def test_conftest_blender_exe_returns_path(conftest_mod, monkeypatch, tmp_path):
    exe = tmp_path / "b.exe"
    exe.write_text("x")
    monkeypatch.setattr(conftest_mod, "BLENDER_EXE", exe)
    assert _fixture_fn(conftest_mod, "blender_exe")() == exe


def test_conftest_qz_user_dir_behavior(conftest_mod, tmp_path):
    from quartz.app import paths as p
    calls = []
    orig = p.reset

    def spy():
        calls.append("reset")
        orig()

    mp = pytest.MonkeyPatch()
    mp2 = pytest.MonkeyPatch()
    mp2.setattr(p, "reset", spy)
    try:
        gen = _fixture_fn(conftest_mod, "qz_user_dir")(mp, tmp_path)
        val = next(gen)
        assert val == tmp_path / "quartz_user"
        assert os.environ["QUARTZ_USER_DIR"] == str(tmp_path / "quartz_user")
        assert calls == ["reset"]
        with pytest.raises(StopIteration):
            next(gen)
        assert calls == ["reset", "reset"]
    finally:
        mp.undo()
        mp2.undo()
        p.reset()


def test_conftest_qz_fixtures_use_testing_isolated():
    src = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'template="default"' in src and 'template="empty"' in src
    assert "isolated(" in src
    assert "activate(strict=True)" in src and "activate(strict=False)" in src
    assert "deactivate()" in src



def test_version_constants():
    from quartz import _version as v
    assert v.VERSION == (1, 0, 0) and isinstance(v.VERSION, tuple)
    assert v.__version__ == "1.0.0"
    assert v.APP_NAME == "Quartz"
    assert v.AUTHOR == "D1on1n"


def test_version_no_imports():
    assert _module_level_imports(ROOT / "quartz" / "_version.py") == []



EXPECTED_LAZY = frozenset({
    "addons", "app", "bmesh", "cli", "compat", "contexts", "depsgraph", "errors", "extras",
    "geometry", "io", "math", "operators", "ops", "path", "props", "registry", "rna", "scan",
    "session", "sweep", "testing", "types", "ui", "undo", "utils",
})


def test_facade_reexports_version():
    import quartz
    assert quartz.VERSION == (1, 0, 0)
    assert quartz.__version__ == "1.0.0"
    assert quartz.APP_NAME == "Quartz"
    assert quartz.AUTHOR == "D1on1n"


def test_facade_lazy_submodules_exact():
    import quartz
    assert isinstance(quartz.LAZY_SUBMODULES, frozenset)
    assert quartz.LAZY_SUBMODULES == EXPECTED_LAZY


def test_facade_dir():
    import quartz
    assert quartz.__dir__() == sorted(EXPECTED_LAZY | {"data", "context", "msgbus", "VERSION", "__version__", "APP_NAME", "AUTHOR"})
    assert dir(quartz) == sorted(EXPECTED_LAZY | {"data", "context", "msgbus", "VERSION", "__version__", "APP_NAME", "AUTHOR"})


def test_facade_unknown_attribute_error():
    import quartz
    with pytest.raises(AttributeError) as ei:
        quartz.definitely_not_there
    assert "module 'quartz' has no attribute 'definitely_not_there'" in str(ei.value)


def test_facade_getattr_function_message():
    import quartz
    with pytest.raises(AttributeError, match="module 'quartz' has no attribute 'zzz'"):
        quartz.__getattr__("zzz")


def test_facade_msgbus_is_app_msgbus():
    import quartz
    import quartz.app.msgbus as mb
    assert quartz.msgbus is mb


@pytest.mark.parametrize("name", ["app", "path", "math", "geometry", "errors", "props", "rna"])
def test_facade_lazy_submodule_import(name):
    import quartz
    mod = getattr(quartz, name)
    assert mod is importlib.import_module(f"quartz.{name}")


def test_facade_import_is_lazy_subprocess():
    r = _run("import sys, quartz; print(sorted(m for m in sys.modules if m.startswith('quartz')))")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "['quartz', 'quartz._version']"


def test_facade_lazy_load_on_access_subprocess():
    r = _run("import sys, quartz; quartz.path; print('quartz.path' in sys.modules, 'quartz.app' in sys.modules)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "True False"


def test_facade_data_context_dynamic(monkeypatch):
    import quartz
    counter = {"data": 0, "context": 0}

    def api_data():
        counter["data"] += 1
        return ("data", counter["data"])

    def api_context():
        counter["context"] += 1
        return ("context", counter["context"])

    fake = types.ModuleType("quartz.session")
    fake.api_data = api_data
    fake.api_context = api_context
    monkeypatch.setitem(sys.modules, "quartz.session", fake)
    assert quartz.data == ("data", 1)
    assert quartz.data == ("data", 2)
    assert quartz.context == ("context", 1)
    assert quartz.context == ("context", 2)
    assert "data" not in vars(quartz)
    assert "context" not in vars(quartz)


def test_facade_no_data_context_assignment_in_source():
    tree = ast.parse((ROOT / "quartz" / "__init__.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                assert not (isinstance(t, ast.Name) and t.id in ("data", "context"))
        if isinstance(node, ast.Global):
            assert "data" not in node.names and "context" not in node.names


def test_facade_only_module_level_import_is_version():
    imps = _module_level_imports(ROOT / "quartz" / "__init__.py")
    assert imps == ["quartz._version"], imps


def test_facade_no_module_level_quartz_import_other_than_version():
    imps = _module_level_imports(ROOT / "quartz" / "__init__.py")
    assert [i for i in imps if i.startswith("quartz") or i.startswith(".")] == ["quartz._version"]



def test_main_structure():
    tree = ast.parse((ROOT / "quartz" / "__main__.py").read_text(encoding="utf-8"))
    body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant))]
    assert len(body) == 1 and isinstance(body[0], ast.If)
    test = body[0].test
    assert isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__"
    assert isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == "__main__"
    inner = body[0].body
    assert isinstance(inner[0], ast.ImportFrom) and inner[0].module == "quartz.cli"
    assert [a.name for a in inner[0].names] == ["main"]
    assert isinstance(inner[1], ast.Raise)
    exc = inner[1].exc
    assert isinstance(exc, ast.Call) and exc.func.id == "SystemExit"
    assert isinstance(exc.args[0], ast.Call) and exc.args[0].func.id == "main"


def test_main_import_does_not_import_cli():
    r = _run("import sys, importlib; importlib.import_module('quartz.__main__'); print('quartz.cli' in sys.modules)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"



PATH_FUNCS = {
    "set_blend_filepath_provider": ["fn"],
    "blend_filepath": [],
    "abspath": ["path", "start", "library"],
    "relpath": ["path", "start"],
    "basename": ["path"],
    "clean_name": ["name", "replace"],
    "display_name": ["name", "has_ext", "title_case"],
    "display_name_from_filepath": ["name"],
    "display_name_to_filepath": ["name"],
    "ensure_ext": ["filepath", "ext", "case_sensitive"],
    "is_subdir": ["path", "directory"],
    "module_names": ["path", "recursive", "package"],
    "native_pathsep": ["path"],
    "reduce_dirs": ["dirs"],
    "resolve_ncase": ["path"],
    "is_autoexec": ["filepath"],
}


@pytest.mark.parametrize("fname", sorted(PATH_FUNCS))
def test_path_signature_names(qpath, fname):
    sig = inspect.signature(getattr(qpath, fname))
    assert list(sig.parameters) == PATH_FUNCS[fname]


@pytest.mark.parametrize("fname,kwonly", [
    ("abspath", {"start": None, "library": None}),
    ("relpath", {"start": None}),
    ("clean_name", {"replace": "_"}),
    ("display_name", {"has_ext": True, "title_case": True}),
    ("ensure_ext", {"case_sensitive": False}),
    ("module_names", {"recursive": False, "package": ""}),
])
def test_path_keyword_only_defaults(qpath, fname, kwonly):
    sig = inspect.signature(getattr(qpath, fname))
    for k, d in kwonly.items():
        p = sig.parameters[k]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
        assert p.default == d


def test_path_blend_filepath_default(qpath):
    qpath.set_blend_filepath_provider(None)
    assert qpath.blend_filepath() == ""
    assert qpath.blend_filepath() == FACTS["data.filepath_unsaved"]


def test_path_provider_install_and_reset(qpath):
    qpath.set_blend_filepath_provider(lambda: "C:/proj/scene.blend")
    assert qpath.blend_filepath() == "C:/proj/scene.blend"
    qpath.set_blend_filepath_provider(None)
    assert qpath.blend_filepath() == ""


def test_path_abspath_unsaved_fact(qpath):
    assert qpath.abspath("//x/y.png") == FACTS["path.abspath_unsaved"] == "x/y.png"


def test_path_abspath_plain_fact(qpath):
    assert qpath.abspath("C:/q/x.png") == FACTS["path.abspath_plain"]


def test_path_abspath_plain_unchanged_even_with_file(qpath):
    qpath.set_blend_filepath_provider(lambda: "C:/proj/scene.blend")
    assert qpath.abspath("rel/x.png") == "rel/x.png"


def test_path_abspath_saved(qpath):
    qpath.set_blend_filepath_provider(lambda: "C:/proj/scene.blend")
    assert qpath.abspath("//x/y.png") == os.path.join("C:/proj", "x/y.png")


def test_path_abspath_start(qpath):
    assert qpath.abspath("//x/y.png", start="D:/base") == os.path.join("D:/base", "x/y.png")


def test_path_abspath_start_overrides_file(qpath):
    qpath.set_blend_filepath_provider(lambda: "C:/proj/scene.blend")
    assert qpath.abspath("//y.png", start="D:/other") == os.path.join("D:/other", "y.png")


def test_path_abspath_library_accepted(qpath):
    assert qpath.abspath("//a.png", library=None) == "a.png"


def test_path_relpath_already_relative(qpath):
    qpath.set_blend_filepath_provider(lambda: "C:/proj/scene.blend")
    assert qpath.relpath("//already/x.png") == "//already/x.png"


def test_path_relpath_empty_base_unchanged(qpath):
    qpath.set_blend_filepath_provider(None)
    assert qpath.relpath("C:/proj/tex/a.png") == "C:/proj/tex/a.png"


def test_path_relpath_saved(qpath):
    qpath.set_blend_filepath_provider(lambda: "C:/proj/scene.blend")
    assert qpath.relpath("C:/proj/tex/a.png") == "//tex/a.png"


def test_path_relpath_start_and_slash_sep(qpath):
    r = qpath.relpath("C:/base/sub/deep/a.png", start="C:/base")
    assert r == "//sub/deep/a.png"
    assert "\\" not in r


def test_path_relpath_parent(qpath):
    assert qpath.relpath("C:/a/x.png", start="C:/a/b") == "//../x.png"


def test_path_basename_fact(qpath):
    assert qpath.basename("//foo/bar.png") == FACTS["path.basename"] == "bar.png"


def test_path_basename_plain(qpath):
    assert qpath.basename("C:/a/b/c.txt") == "c.txt"


def test_path_clean_name_fact(qpath):
    assert qpath.clean_name("my file-1.2 ç!") == FACTS["path.clean_name"] == "my_file-1_2___"


def test_path_clean_name_replace(qpath):
    assert qpath.clean_name("a b.c", replace="X") == "aXbXc"


def test_path_clean_name_non_ascii_letters(qpath):
    assert qpath.clean_name("éÄ1") == "__1"


def test_path_clean_name_keeps_allowed(qpath):
    s = "AZaz09_-"
    assert qpath.clean_name(s) == s


def test_path_display_name_fact(qpath):
    assert qpath.display_name("my_file-name.blend") == FACTS["path.display_name"] == "My File-Name"


def test_path_display_name_nolower_fact(qpath):
    assert qpath.display_name("my_File-NAME") == FACTS["path.display_name_nolower"] == "my File-NAME"


def test_path_display_name_no_title(qpath):
    assert qpath.display_name("my_file.blend", title_case=False) == "my file"


def test_path_display_name_no_ext(qpath):
    assert qpath.display_name("a_b.c", has_ext=False) == "A B.C"


def test_path_display_name_from_filepath_fact(qpath):
    assert qpath.display_name_from_filepath("/a/b/my_file.blend") == FACTS["path.display_name_from_filepath"]


def test_path_display_name_from_filepath_no_title(qpath):
    assert qpath.display_name_from_filepath("/x/lower_case.txt") == "lower_case"


def test_path_display_name_to_filepath(qpath):
    assert qpath.display_name_to_filepath('a\\b/c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_path_display_name_to_filepath_keeps_others(qpath):
    assert qpath.display_name_to_filepath("Hello World.1") == "Hello World.1"


def test_path_ensure_ext_upper_fact(qpath):
    assert qpath.ensure_ext("a.TXT", ".txt") == FACTS["path.ensure_ext_upper"]


def test_path_ensure_ext_none_fact(qpath):
    assert qpath.ensure_ext("a", ".txt") == FACTS["path.ensure_ext_none"]


def test_path_ensure_ext_other_fact(qpath):
    assert qpath.ensure_ext("a.png", ".txt") == FACTS["path.ensure_ext_other"]


def test_path_ensure_ext_case_sensitive(qpath):
    assert qpath.ensure_ext("a.TXT", ".txt", case_sensitive=True) == "a.TXT.txt"
    assert qpath.ensure_ext("a.txt", ".txt", case_sensitive=True) == "a.txt"


def test_path_is_subdir_fact(qpath):
    assert [qpath.is_subdir("C:/a/b/c", "C:/a"), qpath.is_subdir("C:/ab", "C:/a")] == FACTS["path.is_subdir"]


def test_path_is_subdir_normalizes(qpath):
    assert qpath.is_subdir("C:/a/./b/../b/c", "C:/a/") is True
    assert qpath.is_subdir("C:\\a\\b", "C:/a") is True


def test_path_is_subdir_returns_bool(qpath):
    assert type(qpath.is_subdir("C:/a/b", "C:/a")) is bool


def test_path_is_subdir_parent_false(qpath):
    assert qpath.is_subdir("C:/a", "C:/a/b") is False


def _mk_tree(base):
    (base / "b_mod.py").write_text("")
    (base / "a_mod.py").write_text("")
    (base / "__init__.py").write_text("")
    (base / "notes.txt").write_text("")
    pkg = base / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "inner.py").write_text("")
    sub = pkg / "sub"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (base / "nopkg").mkdir()
    (base / "nopkg" / "x.py").write_text("")
    hid = base / ".hidden"
    hid.mkdir()
    (hid / "__init__.py").write_text("")
    pc = base / "__pycache__"
    pc.mkdir()
    (pc / "__init__.py").write_text("")
    (base / ".hid.py").write_text("")


def _norm(pairs):
    return [(n, os.path.normpath(p)) for n, p in pairs]


def test_path_module_names_basic(qpath, tmp_path):
    _mk_tree(tmp_path)
    got = _norm(qpath.module_names(str(tmp_path)))
    names = [n for n, _ in got]
    assert names == ["a_mod", "b_mod", "pkg"]
    d = dict(got)
    assert d["a_mod"] == os.path.normpath(str(tmp_path / "a_mod.py"))
    assert d["pkg"] == os.path.normpath(str(tmp_path / "pkg" / "__init__.py"))


def test_path_module_names_recursive(qpath, tmp_path):
    _mk_tree(tmp_path)
    names = [n for n, _ in qpath.module_names(str(tmp_path), recursive=True)]
    assert "pkg.inner" in names and "pkg.sub" in names
    assert names == sorted(names)


def test_path_module_names_package_prefix(qpath, tmp_path):
    _mk_tree(tmp_path)
    names = [n for n, _ in qpath.module_names(str(tmp_path), package="top")]
    assert names == ["top.a_mod", "top.b_mod", "top.pkg"]


def test_path_module_names_returns_list_of_tuples(qpath, tmp_path):
    _mk_tree(tmp_path)
    r = qpath.module_names(str(tmp_path))
    assert isinstance(r, list) and all(isinstance(t, tuple) and len(t) == 2 for t in r)


def test_path_native_pathsep(qpath):
    assert qpath.native_pathsep("a/b/c") == os.path.join("a", "b", "c")


def test_path_reduce_dirs(qpath):
    assert qpath.reduce_dirs(["C:/a", "C:/b", "C:/a/x", "C:/b", "C:/c"]) == ["C:/a", "C:/b", "C:/c"]


def test_path_reduce_dirs_order_child_first(qpath):
    assert qpath.reduce_dirs(["C:/a/x", "C:/z", "C:/a"]) == ["C:/z", "C:/a"]


def test_path_reduce_dirs_returns_list(qpath):
    assert isinstance(qpath.reduce_dirs(iter(["C:/q"])), list)


def test_path_resolve_ncase_existing(qpath, tmp_path):
    d = tmp_path / "MixedCase"
    d.mkdir()
    (d / "File.TXT").write_text("x")
    got = qpath.resolve_ncase(str(tmp_path / "mixedcase" / "file.txt"))
    assert os.path.normcase(got) == os.path.normcase(str(d / "File.TXT"))
    assert got.endswith("MixedCase" + os.sep + "File.TXT") or got.replace("/", os.sep).endswith("MixedCase" + os.sep + "File.TXT")


def test_path_resolve_ncase_missing_unchanged(qpath, tmp_path):
    p = str(tmp_path / "Does" / "Not" / "Exist.x")
    assert qpath.resolve_ncase(p) == p


@pytest.mark.parametrize("fp", ["", "a.blend", "C:/x/y.blend"])
def test_path_is_autoexec_false(qpath, fp):
    assert qpath.is_autoexec(fp) is False


@pytest.mark.parametrize("attr,required", [
    ("extensions_image", {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".exr", ".hdr", ".webp", ".dds", ".psd"}),
    ("extensions_movie", {".mp4", ".mov", ".avi", ".mkv", ".webm", ".ogv", ".mpg", ".mpeg"}),
    ("extensions_audio", {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}),
])
def test_path_extension_sets(qpath, attr, required):
    v = getattr(qpath, attr)
    assert isinstance(v, frozenset)
    assert required <= v
    assert all(e == e.lower() and e.startswith(".") for e in v)


def test_path_only_stdlib_imports():
    for i in _module_level_imports(ROOT / "quartz" / "path.py"):
        assert i.split(".")[0] in sys.stdlib_module_names, i



@pytest.mark.parametrize("name,value", [
    ("version", (1, 0, 0)), ("version_string", "1.0.0"), ("version_cycle", "alpha"),
    ("background", True), ("factory_startup", True), ("debug", False), ("debug_value", 0),
    ("online_access", False), ("online_access_override", False), ("portable", True),
    ("python_args", ()),
])
def test_app_constants(name, value):
    import quartz.app as app
    v = getattr(app, name)
    assert v == value and type(v) is type(value)


def test_app_binary_path():
    import quartz.app as app
    assert app.binary_path == sys.executable


def test_app_driver_namespace():
    import quartz.app as app
    assert isinstance(app.driver_namespace, dict)


@pytest.mark.parametrize("sub", ["handlers", "timers", "msgbus", "translations", "settings", "paths"])
def test_app_submodules(sub):
    import quartz.app as app
    assert getattr(app, sub) is importlib.import_module(f"quartz.app.{sub}")


def test_app_trusted(settings_mod):
    import quartz.app as app
    settings_mod.settings.trust_scripts = False
    assert app.trusted() is False
    settings_mod.settings.trust_scripts = True
    assert app.trusted() is True


def test_app_tempdir(paths, tmp_path):
    import quartz.app as app
    assert app.tempdir == str(tmp_path / "qu" / "temp") + os.sep
    assert (tmp_path / "qu" / "temp").is_dir()


def test_app_cachedir(paths, tmp_path):
    import quartz.app as app
    assert app.cachedir == str(tmp_path / "qu" / "cache") + os.sep


def test_app_unknown_attr():
    import quartz.app as app
    with pytest.raises(AttributeError):
        app.no_such_thing_xyz


def test_app_tempdir_not_cached_attribute(paths):
    import quartz.app as app
    _ = app.tempdir
    assert "tempdir" not in vars(app)


def test_app_group_imports_only_stdlib_and_app():
    for f in sorted((ROOT / "quartz" / "app").glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                names = [node.module]
            else:
                continue
            for n in names:
                top = n.split(".")[0]
                assert top in sys.stdlib_module_names or n == "quartz.app" or n.startswith("quartz.app."), f"{f.name}: {n}"


def test_app_import_loads_no_other_quartz_subprocess():
    r = _run("import sys, quartz.app; print(sorted(m for m in sys.modules if m.startswith('quartz') and not m.startswith('quartz.app')))")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "['quartz', 'quartz._version']"


def test_app_import_no_numpy_subprocess():
    r = _run("import sys, quartz.app, quartz.path; print('numpy' in sys.modules)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"



def test_handlers_blender_names_set(handlers):
    assert isinstance(handlers.BLENDER_HANDLER_NAMES, tuple)
    assert len(handlers.BLENDER_HANDLER_NAMES) == 39
    assert set(handlers.BLENDER_HANDLER_NAMES) == BLENDER_39


def test_handlers_blender_names_match_dump():
    dump = json.loads((ROOT / "data" / "blender_api_dump.json").read_text(encoding="utf-8"))

    def find(o):
        if isinstance(o, dict):
            if "handler_lists" in o:
                return o["handler_lists"]
            for v in o.values():
                r = find(v)
                if r is not None:
                    return r
        return None

    names = find(dump)
    assert names is not None
    assert set(names) == BLENDER_39


def test_handlers_quartz_names(handlers):
    assert handlers.QUARTZ_HANDLER_NAMES == QUARTZ_5


def test_handlers_44_lists(handlers):
    for n in list(BLENDER_39) + list(QUARTZ_5):
        assert isinstance(getattr(handlers, n), list), n


def test_handlers_persistent_marks_and_returns_same(handlers):
    def f(*a):
        pass
    r = handlers.persistent(f)
    assert r is f
    assert f._bpy_persistent is True


def test_handlers_is_persistent(handlers):
    def f():
        pass

    def g():
        pass
    g._bpy_persistent = 1
    assert handlers.is_persistent(f) is False
    assert handlers.is_persistent(handlers.persistent(f)) is True
    assert handlers.is_persistent(g) is False
    assert handlers.is_persistent(object()) is False


def test_handlers_all_lists_identity_and_order(handlers):
    al = handlers.all_lists()
    assert list(al) == list(handlers.BLENDER_HANDLER_NAMES) + list(QUARTZ_5)
    for n, lst in al.items():
        assert lst is getattr(handlers, n)


def test_handlers_all_lists_count(handlers):
    assert len(handlers.all_lists()) == 44


def test_handlers_dispatch_unknown_keyerror(handlers):
    with pytest.raises(KeyError):
        handlers.dispatch("not_a_handler")


def test_handlers_dispatch_args(handlers):
    got = []
    handlers.frame_change_pre.append(lambda *a: got.append(a))
    res = handlers.dispatch("frame_change_pre", "scene", "dg")
    assert got == [("scene", "dg")]
    assert res == []


def test_handlers_dispatch_quartz_name(handlers):
    got = []
    handlers.startup_post.append(lambda *a: got.append(a))
    handlers.dispatch("startup_post")
    assert got == [()]


def test_handlers_dispatch_iterates_copy(handlers):
    order = []

    def a(*args):
        order.append("a")
        handlers.load_post.append(b)

    def b(*args):
        order.append("b")
    handlers.load_post.append(a)
    handlers.dispatch("load_post", "f")
    assert order == ["a"]


def test_handlers_dispatch_removal_during_iteration(handlers):
    order = []

    def a(*args):
        order.append("a")
        handlers.load_pre.remove(b)

    def b(*args):
        order.append("b")
    handlers.load_pre.extend([a, b])
    handlers.dispatch("load_pre", "f")
    assert order == ["a", "b"]


def test_handlers_dispatch_captures_exceptions(handlers, capsys):
    called = []

    def bad(*a):
        raise RuntimeError("boom-handler")

    def good(*a):
        called.append(1)
    handlers.save_pre.extend([bad, good])
    res = handlers.dispatch("save_pre", "x")
    assert called == [1]
    assert len(res) == 1 and isinstance(res[0], RuntimeError)
    err = capsys.readouterr().err
    assert "boom-handler" in err and "Traceback" in err


def test_handlers_dispatch_returns_list(handlers):
    assert isinstance(handlers.dispatch("undo_pre", None), list)


def test_handlers_clear_non_persistent(handlers):
    @handlers.persistent
    def keep(*a):
        pass

    def drop(*a):
        pass
    fc = handlers.frame_change_post
    handlers.frame_change_post.extend([keep, drop])
    handlers.addon_enable_post.append(drop)
    n = handlers.clear_non_persistent()
    assert n == 2
    assert handlers.frame_change_post is fc
    assert fc == [keep]
    assert handlers.addon_enable_post == []


def test_handlers_snapshot_shallow_copies(handlers):
    def f(*a):
        pass
    handlers.render_pre.append(f)
    snap = handlers.snapshot()
    assert isinstance(snap, dict)
    assert snap["render_pre"] == [f]
    assert snap["render_pre"] is not handlers.render_pre
    handlers.render_pre.clear()
    assert snap["render_pre"] == [f]


def test_handlers_restore_in_place(handlers):
    def f(*a):
        pass
    handlers.undo_post.append(f)
    snap = handlers.snapshot()
    lst = handlers.undo_post
    lst.clear()
    handlers.redo_pre.append(f)
    handlers.restore(snap)
    assert handlers.undo_post is lst
    assert lst == [f]
    assert handlers.redo_pre == []
    assert handlers.all_lists()["undo_post"] is lst


def test_handlers_dispatch_signature(handlers):
    sig = inspect.signature(handlers.dispatch)
    assert list(sig.parameters) == ["name", "args"]



def test_timers_signatures(timers):
    sig = inspect.signature(timers.register)
    assert sig.parameters["first_interval"].default == 0.0
    assert sig.parameters["first_interval"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["persistent"].default is False
    sig = inspect.signature(timers.pump)
    assert sig.parameters["now"].default is None
    assert sig.parameters["max_calls"].default == 1000
    assert inspect.signature(timers.clear).parameters["keep_persistent"].default is False


def test_timers_register_and_is_registered(timers):
    def f():
        return None
    assert timers.is_registered(f) is False
    timers.register(f)
    assert timers.is_registered(f) is True


def test_timers_unregister(timers):
    def f():
        return None
    timers.register(f)
    timers.unregister(f)
    assert timers.is_registered(f) is False


def test_timers_unregister_missing_valueerror(timers):
    with pytest.raises(ValueError, match="function is not registered"):
        timers.unregister(lambda: None)


def test_timers_unregister_message_fragment(timers):
    with pytest.raises(ValueError) as ei:
        timers.unregister(lambda: None)
    assert "Error: function is not registered" in str(ei.value)


def test_timers_never_fire_alone(timers):
    calls = []
    timers.register(lambda: calls.append(1))
    time.sleep(0.02)
    assert calls == []


def test_timers_pump_returns_count(timers):
    calls = []
    timers.register(lambda: calls.append(1))
    n = timers.pump(now=time.monotonic() + 1.0)
    assert n == 1 and calls == [1]


def test_timers_none_unregisters(timers):
    def f():
        return None
    timers.register(f)
    timers.pump(now=time.monotonic() + 1)
    assert not timers.is_registered(f)


def test_timers_float_reschedules(timers):
    calls = []

    def f():
        calls.append(1)
        return 5.0
    timers.register(f)
    base = time.monotonic() + 1
    assert timers.pump(now=base) == 1
    assert timers.is_registered(f)
    assert timers.pump(now=base + 4.9) == 0
    assert timers.pump(now=base + 5.0) == 1
    assert len(calls) == 2


def test_timers_first_interval(timers):
    calls = []
    t0 = time.monotonic()
    timers.register(lambda: calls.append(1), first_interval=10.0)
    assert timers.pump(now=t0 + 5.0) == 0
    assert timers.pump(now=time.monotonic() + 10.5) == 1


def test_timers_pump_default_now(timers):
    calls = []
    timers.register(lambda: calls.append(1), first_interval=0.0)
    assert timers.pump() == 1


def test_timers_pump_default_now_not_due(timers):
    calls = []
    timers.register(lambda: calls.append(1), first_interval=100.0)
    assert timers.pump() == 0


def test_timers_order_by_due(timers):
    order = []
    t0 = time.monotonic()
    timers.register(lambda: order.append("late"), first_interval=2.0)
    timers.register(lambda: order.append("early"), first_interval=1.0)
    timers.pump(now=t0 + 100)
    assert order == ["early", "late"]


def test_timers_tie_registration_order(timers, monkeypatch):
    order = []
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    timers.register(lambda: order.append("a"))
    timers.register(lambda: order.append("b"))
    timers.register(lambda: order.append("c"))
    monkeypatch.undo()
    timers.pump(now=2000.0)
    assert order == ["a", "b", "c"]


def test_timers_at_most_once_per_pump(timers):
    calls = []

    def f():
        calls.append(1)
        return 0.0
    timers.register(f)
    n = timers.pump(now=time.monotonic() + 10)
    assert n == 1 and calls == [1]
    assert timers.is_registered(f)


def test_timers_max_calls(timers):
    calls = []
    for i in range(5):
        timers.register((lambda i=i: calls.append(i)))
    n = timers.pump(now=time.monotonic() + 1, max_calls=3)
    assert n == 3 and len(calls) == 3


def test_timers_exception_unregisters_and_prints(timers, capsys):
    def bad():
        raise RuntimeError("timer-boom")
    timers.register(bad)
    n = timers.pump(now=time.monotonic() + 1)
    assert not timers.is_registered(bad)
    assert n == 1
    err = capsys.readouterr().err
    assert "timer-boom" in err and "Traceback" in err


def test_timers_exception_does_not_stop_others(timers, capsys):
    calls = []

    def bad():
        raise RuntimeError("x")
    t0 = time.monotonic()
    timers.register(bad)
    timers.register(lambda: calls.append(1))
    timers.pump(now=t0 + 1)
    assert calls == [1]


def test_timers_reregister_only_reschedules(timers):
    calls = []

    def f():
        calls.append(1)
    timers.register(f, first_interval=100.0)
    timers.register(f, first_interval=0.0)
    n = timers.pump(now=time.monotonic() + 1)
    assert n == 1 and calls == [1]
    assert len(timers.snapshot()) == 0


def test_timers_reregister_single_entry(timers):
    def f():
        return None
    timers.register(f)
    timers.register(f)
    assert len(timers.snapshot()) == 1


def test_timers_clear(timers):
    def a():
        pass

    def b():
        pass
    timers.register(a, persistent=True)
    timers.register(b)
    timers.clear(keep_persistent=True)
    assert timers.is_registered(a) and not timers.is_registered(b)
    timers.clear()
    assert not timers.is_registered(a)


def test_timers_snapshot_restore(timers):
    def a():
        pass
    timers.register(a)
    snap = timers.snapshot()
    assert isinstance(snap, list)
    timers.clear()
    timers.restore(snap)
    assert timers.is_registered(a)


def test_timers_unregister_during_pump_then_return_float(timers):
    def f():
        timers.unregister(f)
        return 1.0
    timers.register(f)
    timers.pump(now=time.monotonic() + 1)
    assert not timers.is_registered(f)


def test_timers_uses_monotonic_source():
    src = (ROOT / "quartz" / "app" / "timers.py").read_text(encoding="utf-8")
    assert "time.monotonic" in src



class _S:
    pass


class _T(_S):
    pass


class _Ref:
    def __init__(self, struct, ident):
        self._q_struct = struct
        self._q_identifier = ident


def _sub(m, key, owner="o", tag=None, out=None):
    out = out if out is not None else []
    m.subscribe_rna(key=key, owner=owner, args=(tag,), notify=lambda t: out.append(t))
    return out


def test_msgbus_subscribe_signature(msgbus):
    sig = inspect.signature(msgbus.subscribe_rna)
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in sig.parameters.values())
    assert list(sig.parameters) == ["key", "owner", "args", "notify", "options"]
    assert sig.parameters["options"].default == frozenset()


def test_msgbus_subscribe_without_options(msgbus):
    out = _sub(msgbus, _S, tag=1)
    msgbus.notify_changed(_S(), "x")
    assert msgbus.flush() == 1 and out == [1]


def test_msgbus_tuple_key_match(msgbus):
    out = _sub(msgbus, (_S, "location"), tag="t")
    s = _T()
    msgbus.notify_changed(s, "location")
    assert msgbus.flush() == 1 and out == ["t"]


def test_msgbus_tuple_key_wrong_ident(msgbus):
    out = _sub(msgbus, (_S, "location"), tag="t")
    msgbus.notify_changed(_S(), "rotation")
    assert msgbus.flush() == 0 and out == []


def test_msgbus_tuple_key_wrong_class(msgbus):
    out = _sub(msgbus, (_T, "location"), tag="t")
    msgbus.notify_changed(_S(), "location")
    assert msgbus.flush() == 0 and out == []


def test_msgbus_class_key(msgbus):
    out = _sub(msgbus, _S, tag="c")
    msgbus.notify_changed(_T(), "anything")
    assert msgbus.flush() == 1 and out == ["c"]


def test_msgbus_class_key_no_match(msgbus):
    out = _sub(msgbus, _T, tag="c")
    msgbus.notify_changed(_S(), "anything")
    assert msgbus.flush() == 0


def test_msgbus_propertyref_key(msgbus):
    s = _S()
    out = _sub(msgbus, _Ref(s, "name"), tag="r")
    msgbus.notify_changed(s, "name")
    assert msgbus.flush() == 1 and out == ["r"]


def test_msgbus_propertyref_other_struct(msgbus):
    s = _S()
    out = _sub(msgbus, _Ref(s, "name"), tag="r")
    msgbus.notify_changed(_S(), "name")
    msgbus.notify_changed(s, "other")
    assert msgbus.flush() == 0 and out == []


def test_msgbus_struct_key(msgbus):
    s = _S()
    out = _sub(msgbus, s, tag="s")
    msgbus.notify_changed(s, "whatever")
    assert msgbus.flush() == 1 and out == ["s"]


def test_msgbus_struct_key_identity(msgbus):
    s = _S()
    out = _sub(msgbus, s, tag="s")
    msgbus.notify_changed(_S(), "whatever")
    assert msgbus.flush() == 0


def test_msgbus_deferred(msgbus):
    out = _sub(msgbus, _S, tag=1)
    msgbus.notify_changed(_S(), "x")
    assert out == []
    assert msgbus.pending() == 1
    msgbus.flush()
    assert out == [1]
    assert msgbus.pending() == 0


def test_msgbus_once_per_flush(msgbus):
    out = _sub(msgbus, _S, tag=1)
    s = _S()
    msgbus.notify_changed(s, "a")
    msgbus.notify_changed(s, "b")
    msgbus.publish_rna(key=_S)
    assert msgbus.flush() == 1 and out == [1]


def test_msgbus_flush_empty(msgbus):
    assert msgbus.flush() == 0


def test_msgbus_notify_args(msgbus):
    got = []
    msgbus.subscribe_rna(key=_S, owner=1, args=(1, "two", None), notify=lambda *a: got.append(a))
    msgbus.notify_changed(_S(), "x")
    msgbus.flush()
    assert got == [(1, "two", None)]


def test_msgbus_publish_rna_equal_key(msgbus):
    out = _sub(msgbus, ("Obj", "loc"), tag="p")
    msgbus.publish_rna(key=("Obj", "loc"))
    assert out == []
    assert msgbus.flush() == 1 and out == ["p"]


def test_msgbus_publish_rna_identity_key(msgbus):
    s = _S()
    out = _sub(msgbus, s, tag="p")
    msgbus.publish_rna(key=s)
    assert msgbus.flush() == 1


def test_msgbus_publish_rna_no_match(msgbus):
    _sub(msgbus, ("A", "b"))
    msgbus.publish_rna(key=("A", "c"))
    assert msgbus.pending() == 0


def test_msgbus_exception_continues(msgbus, capsys):
    out = []

    def bad(*a):
        raise RuntimeError("bus-boom")
    msgbus.subscribe_rna(key=_S, owner=1, args=(), notify=bad)
    _sub(msgbus, _S, tag="ok", out=out)
    msgbus.notify_changed(_S(), "x")
    msgbus.flush()
    assert out == ["ok"]
    err = capsys.readouterr().err
    assert "bus-boom" in err and "Traceback" in err


def test_msgbus_flush_counts_calls_including_failures(msgbus, capsys):
    def bad(*a):
        raise RuntimeError("x")
    msgbus.subscribe_rna(key=_S, owner=1, args=(), notify=bad)
    _sub(msgbus, _S, tag="ok")
    msgbus.notify_changed(_S(), "x")
    assert msgbus.flush() == 2


def test_msgbus_clear_by_owner(msgbus):
    a = _sub(msgbus, _S, owner="A", tag="a")
    b = _sub(msgbus, _S, owner="B", tag="b")
    msgbus.clear_by_owner("A")
    msgbus.notify_changed(_S(), "x")
    msgbus.flush()
    assert a == [] and b == ["b"]


def test_msgbus_clear_by_owner_drops_queued(msgbus):
    a = _sub(msgbus, _S, owner="A", tag="a")
    msgbus.notify_changed(_S(), "x")
    msgbus.clear_by_owner("A")
    msgbus.flush()
    assert a == []


def test_msgbus_clear(msgbus):
    a = _sub(msgbus, _S, tag="a")
    msgbus.notify_changed(_S(), "x")
    msgbus.clear()
    assert msgbus.pending() == 0
    msgbus.notify_changed(_S(), "x")
    assert msgbus.flush() == 0 and a == []


def test_msgbus_snapshot_restore(msgbus):
    a = _sub(msgbus, _S, tag="a")
    snap = msgbus.snapshot()
    assert isinstance(snap, tuple)
    msgbus.clear()
    msgbus.restore(snap)
    msgbus.notify_changed(_S(), "x")
    assert msgbus.flush() == 1 and a == ["a"]


def test_msgbus_notify_during_flush_deferred_to_next(msgbus):
    out = []

    def cb(*a):
        out.append(1)
        msgbus.notify_changed(_S(), "y")
    msgbus.subscribe_rna(key=_S, owner=1, args=(), notify=cb)
    msgbus.notify_changed(_S(), "x")
    assert msgbus.flush() == 1
    assert out == [1]


def test_msgbus_returns_types(msgbus):
    assert msgbus.subscribe_rna(key=_S, owner=1, args=(), notify=lambda: None) is None
    assert msgbus.publish_rna(key=_S) is None
    assert isinstance(msgbus.pending(), int)
    assert isinstance(msgbus.flush(), int)



def test_translations_locale_fact(translations):
    assert translations.locale == FACTS["translations.locale"] == "en_US"


def test_translations_locales(translations):
    assert translations.locales == ("en_US",)


def test_translations_contexts_60_fact(translations):
    facts = FACTS["translations.contexts"]
    assert len(facts) == 60
    for k, v in facts.items():
        assert getattr(translations.contexts, k) == v, k


def test_translations_contexts_type(translations):
    assert isinstance(translations.contexts, translations.TranslationContexts)


def test_translations_contexts_iter_values(translations):
    vals = list(translations.contexts)
    assert len(vals) == 60
    assert sorted(map(repr, vals)) == sorted(map(repr, FACTS["translations.contexts"].values()))


def test_translations_contexts_readonly(translations):
    with pytest.raises((AttributeError, TypeError)):
        translations.contexts.amount = "X"
    assert translations.contexts.amount == "Amount"


def test_translations_contexts_readonly_new_attr(translations):
    with pytest.raises((AttributeError, TypeError)):
        translations.contexts.brand_new = "X"


def test_translations_contexts_unknown(translations):
    with pytest.raises(AttributeError):
        translations.contexts.nope_nope


def test_translations_contexts_default_real_none(translations):
    assert translations.contexts.default_real is None
    assert translations.contexts.default == "*"


def test_translations_contexts_C_to_py(translations):
    m = translations.contexts_C_to_py
    assert isinstance(m, dict)
    assert len(m) == 60
    for field in FACTS["translations.contexts"]:
        assert m[f"BLT_I18NCONTEXT_{field.upper()}"] == field


@pytest.mark.parametrize("fn", ["pgettext", "pgettext_iface", "pgettext_tip", "pgettext_rpt", "pgettext_data", "pgettext_n"])
def test_translations_identity_en_us(translations, fn):
    f = getattr(translations, fn)
    assert f("Add") == "Add"
    assert f("Add", None) == FACTS["translations.pgettext_none_ctx"]
    assert f("Add", "Operator") == "Add"


@pytest.mark.parametrize("fn", ["pgettext", "pgettext_iface", "pgettext_tip", "pgettext_rpt", "pgettext_data", "pgettext_n"])
def test_translations_signatures(translations, fn):
    sig = inspect.signature(getattr(translations, fn))
    assert list(sig.parameters) == ["msgid", "msgctxt"]
    assert sig.parameters["msgctxt"].default is None


@pytest.mark.parametrize("fn", ["pgettext", "pgettext_iface", "pgettext_tip", "pgettext_rpt", "pgettext_data"])
def test_translations_registered_lookup(translations, fn):
    translations.register("audit_mod", {"pt_BR": {("*", "Add"): "Adicionar", ("Operator", "Open"): "Abrir"}})
    try:
        translations.set_locale("pt_BR")
        f = getattr(translations, fn)
        assert f("Add") == "Adicionar"
        assert f("Open", "Operator") == "Abrir"
        assert f("Open") == "Open"
        assert f("Add", "UnknownCtx") == "Adicionar"
        assert f("Missing") == "Missing"
    finally:
        translations.unregister("audit_mod")
        translations.set_locale("en_US")


def test_translations_pgettext_n_always_msgid(translations):
    translations.register("audit_mod_n", {"pt_BR": {("*", "Add"): "Adicionar"}})
    try:
        translations.set_locale("pt_BR")
        assert translations.pgettext_n("Add") == "Add"
    finally:
        translations.unregister("audit_mod_n")
        translations.set_locale("en_US")


def test_translations_other_locale_not_used(translations):
    translations.register("audit_mod2", {"pt_BR": {("*", "Add"): "Adicionar"}})
    try:
        translations.set_locale("en_US")
        assert translations.pgettext("Add") == "Add"
    finally:
        translations.unregister("audit_mod2")


def test_translations_unregister_removes(translations):
    translations.register("audit_mod3", {"pt_BR": {("*", "Add"): "Adicionar"}})
    translations.unregister("audit_mod3")
    translations.set_locale("pt_BR")
    try:
        assert translations.pgettext("Add") == "Add"
    finally:
        translations.set_locale("en_US")


def test_translations_unregister_silent(translations):
    assert translations.unregister("never_registered_xyz") is None


def test_translations_register_accepts_mapping(translations):
    inner = types.MappingProxyType({("*", "Add"): "Adicionar"})
    outer = types.MappingProxyType({"pt_BR": inner})
    translations.register("audit_mod4", outer)
    try:
        translations.set_locale("pt_BR")
        assert translations.pgettext("Add") == "Adicionar"
    finally:
        translations.unregister("audit_mod4")
        translations.set_locale("en_US")


def test_translations_set_locale(translations):
    translations.set_locale("pt_BR")
    assert translations.locale == "pt_BR"
    translations.set_locale("en_US")
    assert translations.locale == "en_US"


@pytest.mark.parametrize("inp,out", [
    ("pt_BR@euro", ("pt", "BR", "euro", "pt_BR", "pt@euro")),
    ("pt_BR", ("pt", "BR", None, "pt_BR", None)),
    ("", (None, None, None, None, None)),
])
def test_translations_locale_explode(translations, inp, out):
    assert translations.locale_explode(inp) == out


def test_translations_locale_explode_returns_tuple(translations):
    r = translations.locale_explode("en_US")
    assert isinstance(r, tuple) and len(r) == 5



EXPECTED_SETTINGS = {
    "api_prefix": "quartz", "restrict_register": True, "lenient_ui": True, "record_missing": True,
    "strict_layout": False, "invoke_in_background": False, "sweep_mode": False,
    "trust_scripts": False, "undo_steps": 32,
}


def test_settings_is_dataclass(settings_mod):
    assert dataclasses.is_dataclass(settings_mod.Settings)


def test_settings_fields_order_and_defaults(settings_mod):
    fields = dataclasses.fields(settings_mod.Settings)
    assert [f.name for f in fields] == list(EXPECTED_SETTINGS)
    for f in fields:
        assert f.default == EXPECTED_SETTINGS[f.name]


@pytest.mark.parametrize("name,value", list(EXPECTED_SETTINGS.items()))
def test_settings_instance_defaults(settings_mod, name, value):
    s = settings_mod.Settings()
    assert getattr(s, name) == value and type(getattr(s, name)) is type(value)


def test_settings_global_instance(settings_mod):
    assert isinstance(settings_mod.settings, settings_mod.Settings)


def test_settings_reset_same_object(settings_mod):
    obj = settings_mod.settings
    obj.api_prefix = "bpy"
    obj.undo_steps = 3
    obj.trust_scripts = True
    settings_mod.reset()
    assert settings_mod.settings is obj
    assert dataclasses.asdict(obj) == EXPECTED_SETTINGS


def test_settings_snapshot_restore(settings_mod):
    settings_mod.reset()
    settings_mod.settings.api_prefix = "bpy"
    snap = settings_mod.snapshot()
    assert isinstance(snap, dict)
    assert snap["api_prefix"] == "bpy"
    obj = settings_mod.settings
    settings_mod.reset()
    settings_mod.restore(snap)
    assert settings_mod.settings is obj
    assert obj.api_prefix == "bpy"
    settings_mod.reset()


def test_settings_snapshot_independent(settings_mod):
    settings_mod.reset()
    snap = settings_mod.snapshot()
    settings_mod.settings.undo_steps = 99
    assert snap["undo_steps"] == 32
    settings_mod.reset()



def test_paths_project_root(paths):
    assert paths.PROJECT_ROOT == ROOT
    assert paths.PROJECT_ROOT == Path(paths.__file__).resolve().parents[2]


def test_paths_user_dir_env(paths, tmp_path):
    p = paths.user_dir()
    assert p == tmp_path / "qu"
    assert p.is_dir()
    assert isinstance(p, Path)


def test_paths_user_dir_default(paths, monkeypatch, tmp_path):
    monkeypatch.delenv("QUARTZ_USER_DIR", raising=False)
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path / "fake_root")
    p = paths.user_dir()
    assert p == tmp_path / "fake_root" / "tmp" / "quartz_user"
    assert p.is_dir()


@pytest.mark.parametrize("fn,sub", [("temp_dir", "temp"), ("config_dir", "config"), ("scripts_dir", "scripts"),
                                    ("datafiles_dir", "datafiles"), ("extensions_dir", "extensions")])
def test_paths_subdirs(paths, tmp_path, fn, sub):
    p = getattr(paths, fn)()
    assert p == tmp_path / "qu" / sub
    assert p.is_dir()


def test_paths_addon_dirs_default(paths, tmp_path):
    assert paths.addon_dirs() == [tmp_path / "qu" / "scripts" / "addons"]


def test_paths_addon_dirs_mutable_same_object(paths, tmp_path):
    a = paths.addon_dirs()
    a.append(tmp_path / "extra")
    assert paths.addon_dirs() is a
    assert tmp_path / "extra" in paths.addon_dirs()


def test_paths_extension_repos_default(paths, tmp_path):
    assert paths.extension_repos() == {
        "user_default": tmp_path / "qu" / "extensions" / "user_default",
        "system": tmp_path / "qu" / "extensions" / "system",
    }


def test_paths_add_addon_dir_no_duplicates(paths, tmp_path):
    paths.add_addon_dir(tmp_path / "x")
    paths.add_addon_dir(str(tmp_path / "x"))
    assert paths.addon_dirs().count(tmp_path / "x") == 1
    assert len(paths.addon_dirs()) == 2


def test_paths_add_addon_dir_default_not_duplicated(paths, tmp_path):
    paths.add_addon_dir(tmp_path / "qu" / "scripts" / "addons")
    assert len(paths.addon_dirs()) == 1


def test_paths_add_extension_repo(paths, tmp_path):
    paths.add_extension_repo("my_repo", str(tmp_path / "r"))
    assert paths.extension_repos()["my_repo"] == tmp_path / "r"
    assert "user_default" in paths.extension_repos()


@pytest.mark.parametrize("bad", ["1abc", "has-dash", "a.b", "", "with space"])
def test_paths_add_extension_repo_invalid(paths, tmp_path, bad):
    with pytest.raises(ValueError):
        paths.add_extension_repo(bad, tmp_path)


def test_paths_compat_dir_default(paths):
    assert paths.compat_dir() == ROOT / "compat"


def test_paths_compat_dir_env(paths, monkeypatch, tmp_path):
    monkeypatch.setenv("QUARTZ_COMPAT_DIR", str(tmp_path / "cc"))
    assert paths.compat_dir() == tmp_path / "cc"


def test_paths_reset_forgets_lists(paths, tmp_path):
    paths.add_addon_dir(tmp_path / "x")
    paths.add_extension_repo("r1", tmp_path / "r")
    paths.reset()
    assert paths.addon_dirs() == [tmp_path / "qu" / "scripts" / "addons"]
    assert "r1" not in paths.extension_repos()


def test_paths_reset_rereads_env(paths, monkeypatch, tmp_path):
    paths.addon_dirs()
    monkeypatch.setenv("QUARTZ_USER_DIR", str(tmp_path / "other"))
    paths.reset()
    assert paths.user_dir() == tmp_path / "other"
    assert paths.addon_dirs() == [tmp_path / "other" / "scripts" / "addons"]


def test_paths_user_dir_env_read_each_call(paths, monkeypatch, tmp_path):
    monkeypatch.setenv("QUARTZ_USER_DIR", str(tmp_path / "u2"))
    assert paths.user_dir() == tmp_path / "u2"


def test_paths_import_has_no_side_effect_subprocess(tmp_path):
    target = tmp_path / "never_created"
    r = _run("import quartz.app, quartz.app.paths", env={"QUARTZ_USER_DIR": str(target)})
    assert r.returncode == 0, r.stderr
    assert not target.exists()



def test_arch_files_exist():
    for n in ("test_headers.py", "test_layering.py", "test_cleanroom.py"):
        assert (ROOT / "tests" / "arch" / n).is_file()


def test_arch_headers_passes_on_repo():
    m = _load_file("_audit_headers", "tests/arch/test_headers.py")
    m.test_no_comments_or_docstrings()


def test_arch_layering_passes_on_repo():
    m = _load_file("_audit_layering", "tests/arch/test_layering.py")
    m.test_layering()


def test_arch_cleanroom_passes_on_repo():
    m = _load_file("_audit_cleanroom", "tests/arch/test_cleanroom.py")
    m.test_cleanroom()


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


HDR = "x = 1\nx = 2\n"


def _headers_on(tmp_path, monkeypatch, files):
    m = _load_file("_audit_headers_t", "tests/arch/test_headers.py")
    for rel, text in files.items():
        _write(tmp_path, rel, text)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    return m


def test_arch_headers_accepts_good(tmp_path, monkeypatch):
    m = _headers_on(tmp_path, monkeypatch, {
        "quartz/a.py": HDR, "compat/b.py": 's = "# not a comment"\n',
        "tools/c.py": "#!/usr/bin/env python\nx = 1\n", "tests/d.py": "",
        "quartz/__pycache__/bad.py": "# garbage\n"})
    m.test_no_comments_or_docstrings()


@pytest.mark.parametrize("rel,text", [
    ("quartz/a.py", "# Quartz - author: someone\n"),
    ("compat/a.py", '"""\nMulti line.\n"""\n'),
    ("tools/a.py", "x = 1  # trailing\n"),
    ("tests/a.py", 'def f():\n    """Doc."""\n    return 1\n'),
    ("quartz/sub/a.py", "class A:\n    \'\'\'Doc.\'\'\'\n"),
    ("quartz/b.py", "x = 1\n#Quartz\n"),
    ("quartz/c.py", '"""Doc."""\n'),
])
def test_arch_headers_rejects_bad(tmp_path, monkeypatch, rel, text):
    m = _headers_on(tmp_path, monkeypatch, {rel: text})
    with pytest.raises(AssertionError):
        m.test_no_comments_or_docstrings()


def _cleanroom_on(tmp_path, monkeypatch, files):
    m = _load_file("_audit_cleanroom_t", "tests/arch/test_cleanroom.py")
    for rel, text in files.items():
        _write(tmp_path, rel, text)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    return m


@pytest.mark.parametrize("marker", ["SPDX-License-Identifier", "GNU General Public License",
                                    "Copyright (C) Blender", "Copyright Blender", "Maxon Computer",
                                    "All rights reserved"])
@pytest.mark.parametrize("folder", ["quartz", "compat", "tools"])
def test_arch_cleanroom_rejects_case_insensitive(tmp_path, monkeypatch, marker, folder):
    m = _cleanroom_on(tmp_path, monkeypatch, {f"{folder}/x.py": HDR + "# " + marker.upper() + "\n"})
    with pytest.raises(AssertionError):
        m.test_cleanroom()


def test_arch_cleanroom_ignores_tests_dir(tmp_path, monkeypatch):
    m = _cleanroom_on(tmp_path, monkeypatch, {"tests/x.py": HDR + "# All rights reserved\n", "quartz/ok.py": HDR})
    m.test_cleanroom()


def _layering_on(tmp_path, monkeypatch, files):
    m = _load_file("_audit_layering_t", "tests/arch/test_layering.py")
    for rel, text in files.items():
        _write(tmp_path, rel, HDR + text)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    return m


def _layer_violations(tmp_path, monkeypatch, files):
    m = _layering_on(tmp_path, monkeypatch, files)
    try:
        m.test_layering()
    except AssertionError as exc:
        return str(exc)
    return ""


@pytest.mark.parametrize("rel,text", [
    ("quartz/app/x.py", "import numpy\n"),
    ("quartz/path.py", "import quartz.math\n"),
    ("quartz/app/x.py", "from quartz.errors import QuartzError\n"),
    ("quartz/math/x.py", "import quartz.rna.struct\n"),
    ("quartz/math/x.py", "from quartz.geometry import mesh\n"),
    ("quartz/rna/x.py", "import quartz.math\n"),
    ("quartz/props.py", "import quartz.app.settings\n"),
    ("quartz/geometry/x.py", "from quartz.math import Vector\n"),
    ("quartz/types/x.py", "import quartz.cli\n"),
    ("quartz/session.py", "from quartz.compat import activate\n"),
    ("compat/bpy/__init__.py", "import numpy\n"),
    ("compat/x.py", "import numpy as np\n"),
    ("quartz/__init__.py", "import quartz.app\n"),
    ("quartz/__init__.py", "from quartz import session\n"),
    ("quartz/math/x.py", "def f():\n    import quartz.rna\n"),
    ("quartz/app/x.py", "def f():\n    from quartz.math import Vector\n"),
    ("quartz/math/x.py", "from ..rna import struct\n"),
])
def test_arch_layering_detects_violation(tmp_path, monkeypatch, rel, text):
    v = _layer_violations(tmp_path, monkeypatch, {rel: text})
    assert v, f"{rel}: {text!r} not flagged"
    assert rel in v


def test_arch_layering_violation_format(tmp_path, monkeypatch):
    v = _layer_violations(tmp_path, monkeypatch, {"quartz/app/x.py": "import os\nimport numpy\n"})
    assert "quartz/app/x.py:4 numpy" in v.replace("\\", "/")


@pytest.mark.parametrize("files", [
    {"quartz/app/x.py": "import os, sys\nfrom quartz.app import settings\nfrom . import paths\n"},
    {"quartz/math/x.py": "import numpy as np\nfrom quartz.math.vector import Vector\nfrom .scalar import clamp\n"},
    {"quartz/rna/x.py": "from quartz.errors import QuartzError\nfrom quartz import props\n" if False else "from quartz.errors import QuartzError\nimport quartz.props\n"},
    {"quartz/geometry/x.py": "import numpy\nfrom quartz.geometry.attributes import X\n"},
    {"quartz/types/object.py": "import numpy\nimport quartz.math\nimport quartz.rna.struct\nimport quartz.app.handlers\nimport quartz.geometry.mesh\nimport quartz.errors\n"},
    {"quartz/ops.py": "import quartz.session\nimport quartz.contexts\nfrom quartz.types.id import ID\n"},
    {"quartz/cli.py": "import quartz.compat\nimport quartz.session\nimport quartz.math\nimport numpy\n"},
    {"compat/bpy/__init__.py": "import sys\nimport quartz.session\nimport mathutils\nfrom bpy import types\n"},
    {"quartz/__init__.py": "from quartz._version import VERSION\n"},
    {"quartz/compat/profile.py": "import json\nimport quartz.types.mesh\nimport quartz.bmesh.core\n"},
])
def test_arch_layering_allows_legal(tmp_path, monkeypatch, files):
    v = _layer_violations(tmp_path, monkeypatch, files)
    assert v == "", v


def test_arch_layering_l2_may_import_types_package(tmp_path, monkeypatch):
    v = _layer_violations(tmp_path, monkeypatch, {
        "quartz/types/__init__.py": "from quartz.types.id import ID\n",
        "quartz/session.py": "from quartz.types import id\nimport quartz.types\n",
    })
    assert v == "", v


@pytest.mark.parametrize("pkg", ["quartz.types", "quartz.utils", "quartz.io", "quartz.operators"])
def test_arch_layering_l2_packages_classified(pkg):
    m = _load_file("_audit_layering_g", "tests/arch/test_layering.py")
    assert m._quartz_group(pkg) == "L2"


@pytest.mark.parametrize("pkg", ["quartz.compat", "quartz.extras", "quartz.bmesh", "quartz.addons"])
def test_arch_layering_l3_packages_classified(pkg):
    m = _load_file("_audit_layering_g3", "tests/arch/test_layering.py")
    assert m._quartz_group(pkg) == "L3"


def test_arch_layering_l2_package_init_cannot_import_l3(tmp_path, monkeypatch):
    v = _layer_violations(tmp_path, monkeypatch, {"quartz/types/__init__.py": "import quartz.cli\n"})
    assert "quartz/types/__init__.py" in v


def test_arch_layering_facade_function_level_import_allowed(tmp_path, monkeypatch):
    v = _layer_violations(tmp_path, monkeypatch, {
        "quartz/__init__.py": "from quartz._version import VERSION\ndef __getattr__(n):\n    import quartz.session\n    return quartz.session\n"})
    assert v == "", v


def test_arch_layering_ignores_missing_dirs(tmp_path, monkeypatch):
    m = _load_file("_audit_layering_e", "tests/arch/test_layering.py")
    monkeypatch.setattr(m, "ROOT", tmp_path)
    m.test_layering()


def test_arch_layering_shim_set():
    m = _load_file("_audit_layering_s", "tests/arch/test_layering.py")
    assert set(m.SHIM_SET) == {"bpy", "mathutils", "bmesh", "bpy_extras", "addon_utils", "idprop",
                               "rna_prop_ui", "bl_math", "bl_ui", "bl_operators", "gpu", "gpu_extras",
                               "blf", "aud", "bl_ext"}


def test_arch_layering_uses_stdlib_module_names():
    src = (ROOT / "tests" / "arch" / "test_layering.py").read_text(encoding="utf-8")
    assert "sys.stdlib_module_names" in src



OWNED = [
    "tests/conftest.py", "quartz/__init__.py", "quartz/_version.py", "quartz/__main__.py", "quartz/path.py",
    "quartz/app/__init__.py", "quartz/app/handlers.py", "quartz/app/timers.py", "quartz/app/msgbus.py",
    "quartz/app/translations.py", "quartz/app/settings.py", "quartz/app/paths.py",
    "tests/arch/test_headers.py", "tests/arch/test_layering.py", "tests/arch/test_cleanroom.py",
    "tests/unit/test_path.py",
]


@pytest.mark.parametrize("rel", OWNED + sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests" / "unit" / "app").glob("*.py")))
def test_owned_file_has_no_comments_or_docstrings(rel):
    assert _comment_and_docstring_lines((ROOT / rel).read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("rel", [r for r in OWNED if r.startswith("quartz/")])
def test_owned_library_no_print(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            pytest.fail(f"print in {rel}:{node.lineno}")


@pytest.mark.parametrize("rel", [r for r in OWNED if r.startswith("quartz/")])
def test_owned_library_no_notimplemented_stub(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            e = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            assert not (isinstance(e, ast.Name) and e.id == "NotImplementedError"), f"{rel}:{node.lineno}"
