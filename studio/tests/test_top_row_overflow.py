from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_FOLDER = tempfile.mkdtemp(prefix="quartz-top-row-")
os.environ["QUARTZ_PREFS_DIR"] = _FOLDER

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from quartz_studio import controls
from quartz_studio.app import create_app

controls.STORE_PATH = os.path.join(_FOLDER, "controls.json")

STAND_IN_MENUS = ["Shading", "Unwrap", "Brushes", "Keyframes", "Output", "Plugins"]
STAND_IN_PAGES = [("p_shading", "Shading"), ("p_unwrap", "Unwrap Edit"), ("p_code", "Code"),
                  ("p_output", "Output")]
SIZES = ((1280, 720), (1920, 1010))
_STATE: dict = {}


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(n: int = 6) -> None:
    app = _app()
    for _ in range(n):
        app.processEvents()


def _rect(win, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(win, QPoint(0, 0)), widget.size())


def _window(extended: bool = True):
    key = "extended" if extended else "plain"
    win = _STATE.get(key)
    if win is not None:
        return win
    from quartz_studio.main_window import MainWindow

    _app()
    win = MainWindow()
    win.setMinimumSize(1, 1)
    if extended:
        calls = _STATE.setdefault("calls", [])
        for title in STAND_IN_MENUS:
            win.menu_bar.add_menu(title, [(f"{title} Action", lambda t=title: calls.append(t))])
        for page_id, title in STAND_IN_PAGES:
            win.add_page(page_id, title, QLabel(title))
    win.resize(*SIZES[0])
    win.show()
    _settle()
    _STATE[key] = win
    return win


def _resize(win, size) -> None:
    win.resize(*size)
    _settle()


def _shown_titles(bar) -> list[str]:
    return [a.text() for a in bar.actions() if a.isVisible() and a is not bar.overflow_action]


def _check_row(win) -> None:
    bar = win.menu_bar
    pill = _rect(win, win.command_bar.mode_switcher)
    top = win.top_bar
    assert abs(pill.center().x() + 0.5 - top.width() / 2) <= 1, (pill, top.width())
    menu = _rect(win, bar)
    assert menu.right() < pill.left(), (menu, pill)
    for act in bar.actions():
        if act.isVisible():
            r = bar.actionGeometry(act)
            assert not r.isEmpty() and r.right() < bar.width(), (act.text(), r, bar.width())
    if win.page_switcher.isVisible():
        switch = _rect(win, win.page_switcher)
        assert switch.left() > menu.right(), (switch, menu)
        assert switch.right() < pill.left(), (switch, pill)
    hidden = bar.hidden_titles()
    assert _shown_titles(bar) + hidden == bar.titles()
    assert bar.overflow_action.isVisible() == bool(hidden)
    if hidden:
        assert bar.actions()[-1] is bar.overflow_action


def test_plain_window_has_no_overflow() -> None:
    win = _window(extended=False)
    for size in SIZES:
        _resize(win, size)
        _check_row(win)
        assert win.menu_bar.hidden_titles() == []
        assert not win.menu_bar.overflow_action.isVisible()
        assert win.page_switcher.isHidden()


def test_titles_keep_every_menu_in_order() -> None:
    win = _window()
    titles = win.menu_bar.titles()
    assert titles[-len(STAND_IN_MENUS):] == STAND_IN_MENUS
    for size in SIZES:
        _resize(win, size)
        assert win.menu_bar.titles() == titles
        assert set(win.menu_bar.menus) == set(titles)


def test_row_fits_before_the_centred_pill_at_both_sizes() -> None:
    win = _window()
    for size in SIZES:
        _resize(win, size)
        _check_row(win)


def test_small_window_collapses_menus_into_the_overflow() -> None:
    win = _window()
    _resize(win, SIZES[0])
    bar = win.menu_bar
    hidden = bar.hidden_titles()
    assert hidden and hidden[-1] == STAND_IN_MENUS[-1], hidden
    assert _shown_titles(bar)[:2] == ["File", "Edit"]
    entries = bar.overflow_menu.actions()
    assert [a.text() for a in entries] == hidden
    for act in entries:
        assert act.menu() is bar.menus[act.text()]
    calls = _STATE["calls"]
    calls.clear()
    menu = bar.menus[STAND_IN_MENUS[-1]]
    menu.find_action(f"{STAND_IN_MENUS[-1]} Action").trigger()
    assert calls == [STAND_IN_MENUS[-1]]
    r = bar.actionGeometry(bar.overflow_action)
    assert r.width() > 0 and r.right() < bar.width()


def test_compact_page_switcher_lists_and_switches_pages() -> None:
    win = _window()
    _resize(win, SIZES[0])
    switcher = win.page_switcher
    assert switcher.is_compact()
    assert switcher.compact_button.isVisible()
    assert not any(b.isVisible() for b in switcher.buttons.values())
    assert switcher.compact_button.text() == "Model"
    menu = switcher.build_page_menu()
    titles = ["Model"] + [t for _p, t in STAND_IN_PAGES]
    assert menu.entries_text() == titles
    assert [bool(a.property("qs_check")) for a in menu.actions()] == [True] + [False] * len(STAND_IN_PAGES)
    menu.find_action("Code").trigger()
    _settle()
    assert win.current_page() == "p_code"
    assert switcher.compact_button.text() == "Code"
    win.show_page("model")
    _settle()
    assert switcher.compact_button.text() == "Model"
    menu.deleteLater()


def test_wide_window_restores_the_full_row() -> None:
    win = _window()
    _resize(win, (3200, 1010))
    bar = win.menu_bar
    _check_row(win)
    assert bar.hidden_titles() == []
    assert not bar.overflow_action.isVisible()
    assert not win.page_switcher.is_compact()
    assert all(b.isVisible() for b in win.page_switcher.buttons.values())
    assert _shown_titles(bar) == bar.titles()
    _resize(win, SIZES[0])
    _check_row(win)
    assert bar.hidden_titles() and win.page_switcher.is_compact()


def test_menu_added_later_is_placed_by_the_rule() -> None:
    win = _window()
    _resize(win, SIZES[0])
    bar = win.menu_bar
    win.menu_bar.add_menu("Late", [("Late Action", lambda: None)])
    _settle()
    assert bar.titles()[-1] == "Late"
    assert bar.hidden_titles()[-1] == "Late"
    _check_row(win)


def test_top_row_has_no_app_mark() -> None:
    from quartz_studio import theme

    for extended in (False, True):
        win = _window(extended=extended)
        assert not hasattr(win, "app_mark")
        assert win.top_bar.findChild(QLabel, "qsAppMark") is None
        for size in SIZES:
            _resize(win, size)
            assert _rect(win, win.menu_bar).left() == theme.WINDOW_MARGIN, _rect(win, win.menu_bar)
            _check_row(win)


def test_changing_page_keeps_the_row_fitted() -> None:
    win = _window()
    _resize(win, SIZES[0])
    switcher = win.page_switcher
    assert switcher.is_compact()
    for page_id in ("p_unwrap", "p_shading", "model"):
        win.show_page(page_id)
        _settle()
        assert switcher.compact_button.text() == win._page_titles[page_id]
        assert switcher.width() == switcher.sizeHint().width()
        _check_row(win)


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
    for win in list(_STATE.values()):
        if isinstance(win, QWidget):
            win.close()
    controls.reset()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
