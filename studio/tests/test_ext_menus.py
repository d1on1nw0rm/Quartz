from __future__ import annotations

import io
import logging
import os
import sys
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isdir(os.path.join(STUDIO_ROOT, "quartz_studio")):
    STUDIO_ROOT = os.environ.get("QUARTZ_STUDIO_ROOT", STUDIO_ROOT)
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from quartz_studio.app import create_app

WATCHDOG_SECONDS = 120

KNOWN_FAILURES: dict[tuple[str, ...], str] = {}

_STATE: dict = {}


_PATCHED = (
    ("QDialog", ("exec", "exec_")),
    ("QMessageBox", ("exec", "information", "warning", "critical", "question")),
    ("QFileDialog", ("exec", "getOpenFileName", "getOpenFileNames", "getSaveFileName",
                     "getExistingDirectory")),
    ("QInputDialog", ("getText", "getInt", "getDouble", "getItem")),
    ("QColorDialog", ("getColor",)),
)


def _patch_dialogs():
    from PySide6 import QtWidgets
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (QColorDialog, QDialog, QFileDialog, QInputDialog,
                                   QMessageBox)

    saved = []
    for cls_name, attrs in _PATCHED:
        cls = getattr(QtWidgets, cls_name)
        for attr in attrs:
            if attr in cls.__dict__:
                saved.append((cls, attr, cls.__dict__[attr]))
            else:
                saved.append((cls, attr, None))
    QDialog.exec = lambda self, *a, **k: 0
    QDialog.exec_ = lambda self, *a, **k: 0
    QMessageBox.exec = lambda self, *a, **k: int(QMessageBox.StandardButton.Cancel.value)
    for name in ("information", "warning", "critical"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    QFileDialog.exec = lambda self, *a, **k: 0
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
    QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
    QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
    QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
    QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
    QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
    QColorDialog.getColor = staticmethod(lambda *a, **k: QColor())

    def restore() -> None:
        for cls, attr, value in saved:
            if value is None:
                try:
                    delattr(cls, attr)
                except AttributeError:
                    pass
            else:
                setattr(cls, attr, value)

    return restore


def _start_watchdog(app):
    from PySide6.QtCore import QTimer

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: app.exit(1))
    timer.start(WATCHDOG_SECONDS * 1000)
    hard = threading.Timer(WATCHDOG_SECONDS + 15, lambda: os._exit(3))
    hard.daemon = True
    hard.start()

    def stop() -> None:
        timer.stop()
        hard.cancel()

    return stop


def _window():
    if "window" in _STATE:
        return _STATE["window"], _STATE["report"]
    app = create_app([sys.argv[0]])
    from quartz_studio.ext import install as ext_install
    from quartz_studio.main_window import MainWindow
    from quartz_studio.modeling import install as mi

    mi.prepare()
    win = MainWindow()
    mi.install(win)
    report = ext_install.install(win)
    win.resize(1536, 896)
    win.show()
    for _ in range(6):
        app.processEvents()
    _STATE.update(window=win, report=report, app=app)
    return win, report


def _settle():
    for _ in range(4):
        _STATE["app"].processEvents()


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[str] = []

    def emit(self, record) -> None:
        msg = record.getMessage()
        if "not implemented" in msg.lower():
            self.records.append(msg)


def _fresh_cube(polygons: bool) -> None:
    from quartz_studio.scene import Mesh, get_scene

    scene = get_scene()
    if scene.mode != "model":
        scene.set_mode("model")
    for obj in list(scene.objects):
        scene.remove_object(obj)
    cube = scene.add_object("Cube", Mesh.cube())
    scene.set_active(cube)
    scene.select_object(True)
    if polygons:
        scene.set_mode("polygons")
        scene.select_components([0])


def _close_new_windows(before: set[int], win) -> None:
    from PySide6.QtWidgets import QApplication

    for widget in QApplication.topLevelWidgets():
        if id(widget) in before or widget is win:
            continue
        if widget.isVisible():
            try:
                widget.close()
            except Exception:
                pass
    _settle()


def _run_action(win, path: tuple[str, ...], polygons: bool) -> list[str]:
    from PySide6.QtWidgets import QApplication

    _fresh_cube(polygons)
    _settle()
    problems: list[str] = []
    collector = _Collector()
    logger = logging.getLogger("quartz_studio")
    logger.addHandler(collector)
    old_level = logger.level
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)
    buf = io.StringIO()
    old_out, old_err, old_hook = sys.stdout, sys.stderr, sys.excepthook
    sys.stdout = io.StringIO()
    sys.stderr = buf
    sys.excepthook = lambda t, v, tb: problems.append(f"{t.__name__}: {v}")
    before = {id(w) for w in QApplication.topLevelWidgets()}
    try:
        act = win.menu_bar.action_at(path)
        if act is None:
            problems.append("action not found")
        else:
            act.trigger()
            _settle()
    except Exception as exc:
        problems.append(f"{type(exc).__name__}: {exc}")
    finally:
        sys.stdout, sys.stderr, sys.excepthook = old_out, old_err, old_hook
        logger.removeHandler(collector)
        logger.setLevel(old_level)
        _close_new_windows(before, win)
    text = buf.getvalue()
    if "Traceback" in text or "Error" in text:
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        problems.append(lines[-1] if lines else "stderr output")
    problems.extend(f"log: {m}" for m in collector.records)
    return problems


def _leaf_paths(win, report) -> list[tuple[str, ...]]:
    menus = set(report["menus"])
    return sorted(p for p in win.menu_bar._extension_ids if p and p[0] in menus)


def test_menus_listed():
    win, report = _window()
    assert report["menus"]
    assert _leaf_paths(win, report)


def test_every_menu_action_runs():
    win, report = _window()
    restore = _patch_dialogs()
    stop = _start_watchdog(_STATE["app"])
    failures: dict[tuple[str, ...], list[str]] = {}
    try:
        for path in _leaf_paths(win, report):
            problems = _run_action(win, path, polygons=True)
            if problems:
                retry = _run_action(win, path, polygons=False)
                if retry:
                    failures[path] = problems + retry
        _fresh_cube(False)
        _settle()
    finally:
        stop()
        restore()
    _STATE["failures"] = failures
    unexpected = {" > ".join(p): v for p, v in failures.items() if p not in KNOWN_FAILURES}
    assert not unexpected, unexpected
    fixed = [" > ".join(p) for p in KNOWN_FAILURES if p not in failures]
    assert not fixed, f"known failures now pass, remove them: {fixed}"


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
