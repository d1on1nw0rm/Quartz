from __future__ import annotations

import codeop
import ctypes
import threading
import contextlib
import importlib
import io
import linecache
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "ExecResult",
    "make_namespace",
    "refresh_namespace",
    "execute",
    "is_complete",
    "register_source",
    "search_path",
    "purge_modules",
    "ScriptTimeout",
    "Watchdog",
    "DEFAULT_TIMEOUT",
    "TIMEOUT_KEY",
    "default_timeout",
]

DEFAULT_TIMEOUT = 120.0
TIMEOUT_KEY = "script_timeout"


class ScriptTimeout(BaseException):
    pass


def default_timeout() -> float | None:
    from . import paths
    value = paths.read_settings().get(TIMEOUT_KEY, DEFAULT_TIMEOUT)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return value if value > 0 else None


class Watchdog:

    def __init__(self, seconds: float | None, interval: float = 0.25) -> None:
        self.seconds = None if seconds is None or seconds <= 0 else float(seconds)
        self.interval = float(interval)
        self.fired = False
        self._lock = threading.Lock()
        self._running = False
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._target = threading.get_ident()

    def _inject(self, exc) -> None:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(self._target),
                                                   ctypes.py_object(exc) if exc is not None else None)

    def _watch(self) -> None:
        if self._done.wait(self.seconds):
            return
        while True:
            with self._lock:
                if not self._running:
                    return
                self.fired = True
                self._inject(ScriptTimeout)
            if self._done.wait(self.interval):
                return

    def __enter__(self) -> "Watchdog":
        self._target = threading.get_ident()
        if self.seconds is not None:
            self._running = True
            self._thread = threading.Thread(target=self._watch, name="quartz-script-watchdog", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._done.set()
            if self.fired:
                self._inject(None)
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False


@dataclass
class ExecResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    value: Any = None
    has_value: bool = False
    elapsed: float = 0.0
    filename: str = "<script>"
    messages: list = field(default_factory=list)

    @property
    def output(self) -> str:
        parts = [self.stdout, self.stderr]
        if self.error:
            parts.append(self.error)
        return "".join(p for p in parts if p)

    def summary(self) -> str:
        if self.ok:
            return f"{self.filename}: done in {self.elapsed * 1000.0:.1f} ms"
        last = self.error.strip().splitlines()[-1] if self.error.strip() else "error"
        return f"{self.filename}: {last}"


def make_namespace(scene=None, extra: dict | None = None) -> dict:
    from . import api
    scene = api.document() if scene is None else scene
    ns = {
        "__name__": "__main__",
        "__builtins__": __builtins__,
        "quartz": api,
        "doc": scene,
        "op": getattr(scene, "active", None),
        "np": np,
    }
    if extra:
        ns.update(extra)
    return ns


def refresh_namespace(ns: dict, scene=None) -> dict:
    from . import api
    scene = ns.get("doc") if scene is None else scene
    if scene is None:
        scene = api.document()
    ns["quartz"] = api
    ns["doc"] = scene
    ns["op"] = getattr(scene, "active", None)
    ns.setdefault("np", np)
    ns.setdefault("__name__", "__main__")
    ns.setdefault("__builtins__", __builtins__)
    return ns


def register_source(filename: str, source: str) -> None:
    lines = source.splitlines(True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    linecache.cache[filename] = (len(source), None, lines, filename)


def is_complete(source: str) -> bool:
    if not source.strip():
        return True
    lines = source.split("\n")
    if len(lines) > 1 and not lines[-1].strip():
        return True
    try:
        code = codeop.compile_command(source, "<console>", "single")
    except (SyntaxError, OverflowError, ValueError):
        return True
    return code is not None


def _format_error(exc: BaseException, skip_frames: int) -> str:
    tb = exc.__traceback__
    for _ in range(skip_frames):
        if tb is not None and tb.tb_next is not None:
            tb = tb.tb_next
    if isinstance(exc, SyntaxError):
        return "".join(traceback.format_exception_only(type(exc), exc))
    return "".join(traceback.format_exception(type(exc), exc, tb))


def _compile(source: str, filename: str, interactive: bool):
    if interactive:
        try:
            return compile(source, filename, "eval"), True
        except SyntaxError:
            pass
    return compile(source, filename, "exec"), False


def _module_dir(module) -> str | None:
    path = getattr(module, "__file__", None)
    if not path:
        return None
    try:
        return os.path.normcase(os.path.dirname(os.path.abspath(path)))
    except (TypeError, ValueError):
        return None


def purge_modules(folders, keep_prefix: str = "") -> list[str]:
    targets = {os.path.normcase(os.path.abspath(str(f))) for f in folders}
    gone = []
    for name, module in list(sys.modules.items()):
        if keep_prefix and name.startswith(keep_prefix):
            continue
        if module is not None and _module_dir(module) in targets:
            sys.modules.pop(name, None)
            gone.append(name)
    return gone


@contextlib.contextmanager
def search_path(folders):
    folders = [os.path.abspath(str(f)) for f in (folders or ()) if f]
    if not folders:
        yield []
        return
    purge_modules(folders)
    added = []
    for folder in reversed(folders):
        if folder not in sys.path:
            sys.path.insert(0, folder)
            added.append(folder)
    importlib.invalidate_caches()
    no_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield folders
    finally:
        sys.dont_write_bytecode = no_bytecode
        for folder in added:
            try:
                sys.path.remove(folder)
            except ValueError:
                pass


def execute(source: str, ns: dict, filename: str = "<script>", *, interactive: bool = False,
            scene=None, undo_group: bool = False, paths=None, timeout: float | None = None) -> ExecResult:
    from . import api
    out, err = io.StringIO(), io.StringIO()
    register_source(filename, source)
    start = time.perf_counter()
    messages: list = []
    listener = messages.append
    api.add_message_listener(listener)
    group_scene = scene if scene is not None else ns.get("doc")
    began = False
    result = ExecResult(True, filename=filename)
    stack = contextlib.ExitStack()
    try:
        if group_scene is not None:
            stack.enter_context(api.bind_scene(group_scene))
        stack.enter_context(search_path(paths))
        if undo_group and group_scene is not None:
            began = api.begin_undo(group_scene)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code, is_expr = _compile(source, filename, interactive)
            except SyntaxError as exc:
                result.ok = False
                result.error = _format_error(exc, 0)
            else:
                try:
                    value = None
                    with Watchdog(timeout):
                        if is_expr:
                            value = eval(code, ns)
                        else:
                            exec(code, ns)
                    if is_expr and value is not None:
                        result.value = value
                        result.has_value = True
                        ns["_"] = value
                except ScriptTimeout as exc:
                    result.ok = False
                    result.error = (_format_error(exc, 1).rstrip("\n") + f": stopped after {timeout:g} s; "
                                    "raise the time limit in the Script Manager if this script needs longer\n")
                except SystemExit as exc:
                    if exc.code not in (None, 0):
                        result.ok = False
                        result.error = f"SystemExit: {exc.code}\n"
                except KeyboardInterrupt:
                    result.ok = False
                    result.error = "KeyboardInterrupt\n"
                except BaseException as exc:
                    result.ok = False
                    result.error = _format_error(exc, 1)
    finally:
        if began:
            api.end_undo(group_scene)
        stack.close()
        api.remove_message_listener(listener)
    result.stdout = out.getvalue()
    result.stderr = err.getvalue()
    result.elapsed = time.perf_counter() - start
    result.messages = messages
    if result.ok:
        try:
            api.refresh(group_scene, soft=True)
        except Exception:
            pass
    return result


def print_result(result: ExecResult, stream=None) -> None:
    stream = stream or sys.stdout
    stream.write(result.output)
