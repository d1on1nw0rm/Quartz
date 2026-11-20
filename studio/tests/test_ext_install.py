from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from quartz_studio.app import create_app

_STATE: dict = {}


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


def test_every_package_installs():
    _win, report = _window()
    from quartz_studio.ext.install import PACKAGES

    assert set(report["installed"]) == {name for name, _m in PACKAGES}, report["failed"]
    assert not report["failed"], {k: v.strip().splitlines()[-1] for k, v in report["failed"].items()}


def test_docks_start_hidden():
    win, report = _window()
    assert report["docks"]
    for dock_id, _title, _area in report["docks"]:
        assert not win.is_dock_visible(dock_id), dock_id


def test_pages_and_layouts_switch():
    win, report = _window()
    for page_id, title in report["pages"]:
        win.show_ext_layout(title)
        _settle()
        assert win.current_page() == page_id
    for layout in ("Sculpt", "Animate", "Rigging", "Tagging"):
        win.show_ext_layout(layout)
        _settle()
        assert win.current_page() == "model"
        assert any(win.is_dock_visible(d) for d, _t, _a in report["docks"])
    tags_docks = [d for d, t, _a in report["docks"] if t == "Tags"]
    assert tags_docks, report["docks"]
    win.show_ext_layout("Tagging")
    _settle()
    assert win.is_dock_visible(tags_docks[0])
    win.show_ext_layout("Model")
    _settle()
    assert win.current_page() == "model"
    assert not any(win.is_dock_visible(d) for d, _t, _a in report["docks"])


def test_menus_exist_and_shortcuts_are_unique():
    win, report = _window()
    titles = win.menu_bar.titles()
    for title in report["menus"]:
        assert title in titles, title
    keys = [k for _l, k in report["shortcuts"]]
    assert len(keys) == len(set(keys)), keys


def test_install_twice_is_harmless():
    win, report = _window()
    from quartz_studio.ext import install as ext_install

    before = list(win.dock_ids())
    ext_install.install(win)
    assert list(win.dock_ids()) == before


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
