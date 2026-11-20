from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from quartz_studio import prefs, project


class _LogCapture(logging.Handler):

    def __init__(self, name: str = "quartz_studio.prefs") -> None:
        super().__init__(logging.DEBUG)
        self._logger = logging.getLogger(name)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(f"{record.levelname}: {record.getMessage()}")

    def __enter__(self) -> list[str]:
        self._old_level = self._logger.level
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self)
        return self.records

    def __exit__(self, *exc) -> None:
        self._logger.removeHandler(self)
        self._logger.setLevel(self._old_level)


@contextmanager
def _profile():
    folder = tempfile.mkdtemp(prefix="quartz-prefs-test-")
    old = os.environ.get("QUARTZ_PREFS_DIR")
    os.environ["QUARTZ_PREFS_DIR"] = folder
    prefs.reload()
    try:
        yield folder
    finally:
        if old is None:
            os.environ.pop("QUARTZ_PREFS_DIR", None)
        else:
            os.environ["QUARTZ_PREFS_DIR"] = old
        prefs.reload()
        shutil.rmtree(folder, ignore_errors=True)


class _Spy:

    def __init__(self) -> None:
        self.keys: list[str] = []

    def __enter__(self) -> list[str]:
        prefs.changed.connect(self.keys.append)
        return self.keys

    def __exit__(self, *exc) -> None:
        prefs.changed.disconnect(self.keys.append)


def _read_file() -> dict:
    with open(prefs.path(), "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_path_is_inside_the_prefs_dir() -> None:
    with _profile() as folder:
        assert os.path.dirname(prefs.path()) == os.path.abspath(folder)
        assert prefs.path().endswith("prefs.json")
        assert prefs.VERSION == 1


def test_get_on_an_empty_profile_returns_defaults_and_creates_nothing() -> None:
    with _profile() as folder:
        assert prefs.get("x") is None
        assert prefs.get("x", 3) == 3
        assert os.listdir(folder) == []
        assert not os.path.exists(prefs.path())


def test_set_writes_and_get_returns_a_copy() -> None:
    with _profile():
        prefs.set("a.b", {"k": [1, 2]})
        assert os.path.exists(prefs.path())
        data = _read_file()
        assert data == {"version": 1, "values": {"a.b": {"k": [1, 2]}}}
        prefs.reload()
        value = prefs.get("a.b")
        assert value == {"k": [1, 2]}
        value["k"].append(3)
        assert prefs.get("a.b") == {"k": [1, 2]}


def test_set_emits_once_and_equal_values_are_not_rewritten() -> None:
    with _profile():
        with _Spy() as keys:
            prefs.set("viewport.display", {"shading": "lines"})
            assert keys == ["viewport.display"]
            stamp = os.stat(prefs.path()).st_mtime_ns
            prefs.set("viewport.display", {"shading": "lines"})
            assert keys == ["viewport.display"]
            assert os.stat(prefs.path()).st_mtime_ns == stamp


def test_set_none_removes_the_key_and_emits() -> None:
    with _profile():
        prefs.set("k", 5)
        with _Spy() as keys:
            prefs.set("k", None)
            assert keys == ["k"]
            assert prefs.get("k") is None
            assert "k" not in _read_file()["values"]
            prefs.set("k", None)
            assert keys == ["k"]


def test_unserialisable_value_raises_and_keeps_the_old_value() -> None:
    with _profile():
        prefs.set("k", 1)
        with _Spy() as keys:
            try:
                prefs.set("k", object())
            except TypeError:
                pass
            else:
                raise AssertionError("TypeError expected")
            assert keys == []
        assert prefs.get("k") == 1
        assert _read_file()["values"]["k"] == 1


def test_corrupt_file_is_kept_aside_and_replaced() -> None:
    with _profile() as folder:
        with open(prefs.path(), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        with _LogCapture() as records:
            assert prefs.get("x", 9) == 9
        assert any(r.startswith("WARNING") for r in records), records
        corrupt = os.path.join(folder, "prefs.corrupt.json")
        with open(corrupt, "r", encoding="utf-8") as fh:
            assert fh.read() == "{not json"
        prefs.set("y", 2)
        assert _read_file() == {"version": 1, "values": {"y": 2}}
        for bad in ("[1, 2]", '{"version": 1, "values": [1]}'):
            with open(prefs.path(), "w", encoding="utf-8") as fh:
                fh.write(bad)
            prefs.reload()
            with _LogCapture():
                assert prefs.get("y") is None


def test_newer_version_and_unknown_keys_are_kept() -> None:
    with _profile():
        with open(prefs.path(), "w", encoding="utf-8") as fh:
            json.dump({"version": 7, "values": {"future.key": [1, "a"]}}, fh)
        prefs.reload()
        prefs.set("selection.options", {"select": {"radius": 12}})
        data = _read_file()
        assert data["version"] == 7
        assert data["values"]["future.key"] == [1, "a"]
        assert data["values"]["selection.options"] == {"select": {"radius": 12}}


def test_write_error_keeps_memory_logs_and_emits() -> None:
    with _profile():
        original = os.replace

        def refuse(*_args, **_kwargs):
            raise OSError("read-only")

        os.replace = refuse
        try:
            with _LogCapture() as records, _Spy() as keys:
                prefs.set("k", "v")
                assert keys == ["k"]
            assert any(r.startswith("WARNING") for r in records), records
            assert prefs.get("k") == "v"
            assert not os.path.exists(prefs.path())
        finally:
            os.replace = original


def test_without_a_folder_variable_the_path_is_temporary_never_appdata() -> None:
    old_env = os.environ.pop("QUARTZ_PREFS_DIR", None)
    old_settings = project.SETTINGS_FILE
    old_user = prefs._state["user"]
    project.SETTINGS_FILE = None
    prefs._state["user"] = False
    try:
        prefs.reload()
        where = prefs.path()
        temp = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
        assert os.path.normcase(where).startswith(temp + os.sep), where
        appdata = os.environ.get("APPDATA")
        if appdata:
            assert not os.path.normcase(where).startswith(
                os.path.normcase(os.path.join(os.path.abspath(appdata), "Quartz"))), where
        assert os.path.basename(os.path.dirname(where)).startswith("quartz-prefs-")
        assert prefs.path() == where
        settings = os.path.join(tempfile.mkdtemp(prefix="quartz-settings-"), "settings.ini")
        project.SETTINGS_FILE = settings
        assert prefs.path() == os.path.join(os.path.dirname(settings), "prefs.json")
        project.SETTINGS_FILE = None
        prefs.use_user_profile()
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        assert prefs.path() == os.path.abspath(os.path.join(base, "Quartz", "prefs.json"))
        os.environ["QUARTZ_PREFS_DIR"] = ""
        assert prefs.path() == os.path.abspath(os.path.join(base, "Quartz", "prefs.json"))
        os.environ.pop("QUARTZ_PREFS_DIR")
    finally:
        prefs._state["user"] = old_user
        project.SETTINGS_FILE = old_settings
        if old_env is not None:
            os.environ["QUARTZ_PREFS_DIR"] = old_env
        prefs.reload()


def _run_as_script() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    tests.sort(key=lambda item: item[1].__code__.co_firstlineno)
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}".encode("ascii", "replace").decode())
        else:
            print(f"ok   {name}")
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
