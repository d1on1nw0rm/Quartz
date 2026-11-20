from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import quartz_studio
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from quartz_studio import theme
from quartz_studio.app import create_app

_KEEP: list[QWidget] = []


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None or not app.property("qsTestThemed"):
        app = create_app([sys.argv[0]])
        app.setProperty("qsTestThemed", True)
    return app


def _settle(passes: int = 6) -> None:
    app = _app()
    for _ in range(passes):
        app.processEvents()


def _window(w: int = 1920, h: int = 1007):
    _app()
    from quartz_studio.main_window import MainWindow
    from quartz_studio.scene import reset_scene

    reset_scene()
    win = MainWindow()
    win.setMinimumSize(1, 1)
    win.resize(w, h)
    win.show()
    _settle()
    win.apply_default_sizes()
    _settle()
    _KEEP.append(win)
    return win


def _rgb(color) -> tuple[int, int, int]:
    c = QColor(color)
    return c.red(), c.green(), c.blue()


def _grab_handle(win, handle):
    _settle(2)
    top_left = handle.mapTo(win, QPoint(0, 0))
    return win.grab(QRect(top_left, handle.size())).toImage()


def _pixels(image) -> dict[tuple[int, int], tuple[int, int, int]]:
    return {(x, y): _rgb(image.pixelColor(x, y))
            for y in range(image.height()) for x in range(image.width())}


def _enter(handle) -> None:
    centre = QPointF(handle.rect().center())
    QApplication.sendEvent(handle, QEnterEvent(centre, centre, QPointF(handle.mapToGlobal(centre))))


def _leave(handle) -> None:
    QApplication.sendEvent(handle, QEvent(QEvent.Type.Leave))


def _mouse(handle, kind: QEvent.Type, local: QPoint, buttons: Qt.MouseButton) -> None:
    button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    pos = QPointF(local)
    glob = QPointF(handle.mapToGlobal(local))
    QApplication.sendEvent(handle, QMouseEvent(kind, pos, glob, button, buttons,
                                               Qt.KeyboardModifier.NoModifier))


def _press(handle) -> None:
    _mouse(handle, QEvent.Type.MouseButtonPress, handle.rect().center(), Qt.MouseButton.LeftButton)


def _release(handle, local: QPoint | None = None) -> None:
    _mouse(handle, QEvent.Type.MouseButtonRelease, local or handle.rect().center(),
           Qt.MouseButton.NoButton)


def test_snap_helpers_follow_the_norm() -> None:
    examples = {22: 24, 26: 24, 30: 32, 34: 32, 37: 36, 19: 18, 3: 2, 5: 4, 7: 6, 85: 88, 68: 64,
                125: 128, 118: 128, 300: 304, 385: 384, 1349: 1344, 890: 896, 200: 200, 260: 260,
                1.4: 1, 1.5: 1, 1.6: 2, 2.6: 2, 3.2: 4, 10.67: 10, 13.33: 12, 6.5: 6, 2.5: 2}
    for value, expected in examples.items():
        assert theme.snap_px(value) == expected, (value, theme.snap_px(value), expected)
    assert theme.snap_px(-22) == -24
    assert theme.snap_px_up(138) == 140
    assert theme.snap_px_up(408) == 416
    assert theme.snap_px_up(325) == 328
    for value in theme.PX_BELOW_128 + theme.PX_MAIN + (0, 136, 488, 260, 200):
        assert theme.allowed_px(value), value
    for value in (30, 34, 42, 54, 60, 62, 84, 85, 126, 170, 340, 875, 9.5, 0.45, 3, 22):
        assert not theme.allowed_px(value), value
    assert theme.SPLITTER_BAR == 4 and theme.SPLITTER_BAR_INSET == 24
    assert theme.SPLITTER_HOVER == theme.mix(theme.ACCENT, theme.SURFACE_BACKDROP, 0.5)
    assert theme.SPLITTER_DRAG == theme.ACCENT
    assert theme.COORDINATES_H == 120


def test_splitters_are_studio_splitters() -> None:
    from quartz_studio.widgets.splitter import StudioSplitter, StudioSplitterHandle

    win = _window()
    for splitter in (win.body_splitter, win.manager_splitter):
        assert isinstance(splitter, StudioSplitter), type(splitter)
        assert splitter.handleWidth() == theme.CARD_GAP == 8
        assert not splitter.childrenCollapsible()
        for i in range(splitter.count()):
            assert isinstance(splitter.handle(i), StudioSplitterHandle)
    win.add_dock("chrome_bottom", "Bottom", QLabel("bottom"), "bottom")
    win.add_dock("chrome_left", "Left", QLabel("left"), "left")
    for splitter in (win.bottom_splitter, win.left_dock_column):
        assert isinstance(splitter, StudioSplitter), type(splitter)
        assert splitter.handleWidth() == 8 and not splitter.childrenCollapsible()


def test_handle_states_paint_the_rounded_bar() -> None:
    win = _window()
    splitter = win.manager_splitter
    handle = splitter.handle(splitter.indexOf(win.attribute_manager))
    assert handle.isEnabled() and handle.state() == "idle"
    backdrop = _rgb(theme.SURFACE_BACKDROP)
    hover = _rgb(theme.SPLITTER_HOVER)
    drag = _rgb(theme.SPLITTER_DRAG)
    assert handle.height() == 8 and handle.width() > 80

    idle = _pixels(_grab_handle(win, handle))
    assert set(idle.values()) == {backdrop}, set(idle.values())

    _enter(handle)
    assert handle.state() == "hover"
    image = _grab_handle(win, handle)
    pixels = _pixels(image)
    length = image.width()
    inset = theme.SPLITTER_BAR_INSET
    painted = {pos for pos, rgb in pixels.items() if rgb != backdrop}
    assert painted, "hover paints nothing"
    for x, y in painted:
        assert 2 <= y <= 5, (x, y)
        assert inset <= x < length - inset, (x, y)
    full = {pos for pos, rgb in pixels.items() if rgb == hover}
    assert {(length // 2, y) for y in range(2, 6)} <= full
    assert (inset + 4, 2) in full and (length - inset - 5, 5) in full
    for corner in ((inset, 2), (inset, 5), (length - inset - 1, 2), (length - inset - 1, 5)):
        assert pixels[corner] != hover, (corner, pixels[corner])
    assert pixels[(length // 2, 1)] == backdrop and pixels[(length // 2, 6)] == backdrop

    _press(handle)
    assert handle.state() == "drag"
    pixels = _pixels(_grab_handle(win, handle))
    assert pixels[(length // 2, 3)] == drag
    assert hover not in set(pixels.values())

    _release(handle)
    assert handle.state() == "hover"
    _leave(handle)
    assert handle.state() == "idle"
    assert set(_pixels(_grab_handle(win, handle)).values()) == {backdrop}


def test_short_handle_uses_small_inset() -> None:
    from quartz_studio.widgets.splitter import StudioSplitter

    _app()
    splitter = StudioSplitter(Qt.Orientation.Horizontal)
    splitter.addWidget(QLabel("a"))
    splitter.addWidget(QLabel("b"))
    splitter.resize(200, 60)
    splitter.show()
    _settle()
    _KEEP.append(splitter)
    handle = splitter.handle(1)
    assert handle.width() == 8 and handle.height() == 60
    rect = handle.bar_rect()
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (2, 8, 4, 44), rect


def test_dragging_a_handle_resizes_the_cards() -> None:
    win = _window()
    splitter = win.manager_splitter
    index = splitter.indexOf(win.attribute_manager)
    handle = splitter.handle(index)
    before = splitter.sizes()
    centre = handle.rect().center()
    _press(handle)
    target = centre + QPoint(0, 40)
    _mouse(handle, QEvent.Type.MouseMove, target, Qt.MouseButton.LeftButton)
    _release(handle, target)
    _settle()
    after = splitter.sizes()
    assert after[index - 1] == before[index - 1] + 40, (before, after)
    assert after[index] == before[index] - 40, (before, after)
    assert win.coordinates.height() == 120

    body = win.body_splitter
    handle = body.handle(1)
    before = body.sizes()
    centre = handle.rect().center()
    _press(handle)
    target = centre - QPoint(40, 0)
    _mouse(handle, QEvent.Type.MouseMove, target, Qt.MouseButton.LeftButton)
    _release(handle, target)
    _settle()
    after = body.sizes()
    assert after[0] == before[0] - 40 and after[1] == before[1] + 40, (before, after)


def _check_coordinates(win) -> None:
    cm = win.coordinates
    assert cm.height() == 120, cm.height()
    assert cm.width() == win.manager_splitter.width(), (cm.width(), win.manager_splitter.width())
    for axis, y in enumerate((48, 70, 92)):
        for column in range(3):
            field = cm.field(column, axis)
            assert field.mapTo(cm, QPoint(0, 0)).y() == y, (axis, column, field.mapTo(cm, QPoint(0, 0)))
            assert field.height() == 20, field.height()
    last = cm.field(2, 2)
    assert last.mapTo(cm, QPoint(0, last.height())).y() == 112


def test_coordinates_fixed_height() -> None:
    from quartz_studio.widgets.coordinates import MIN_H

    assert MIN_H == theme.COORDINATES_H == 120
    win = _window(1920, 1007)
    _check_coordinates(win)
    win.resize(1280, 720)
    _settle()
    win.apply_default_sizes()
    _settle()
    _check_coordinates(win)
    win.resize(1920, 1007)
    _settle()
    splitter = win.manager_splitter
    index = splitter.indexOf(win.attribute_manager)
    y = splitter.handle(index + 1).y()
    splitter.moveSplitter(y - 80, index + 1)
    _settle()
    _check_coordinates(win)
    win.resize(1920, 1300)
    _settle()
    _check_coordinates(win)
    cm = win.coordinates
    assert cm.minimumSizeHint().height() == 120 and cm.sizeHint().height() == 120
    assert cm.minimumWidth() == 256


def test_handle_above_coordinates_is_disabled() -> None:
    win = _window()
    splitter = win.manager_splitter
    above = splitter.handle(splitter.indexOf(win.coordinates))
    assert not above.isEnabled()
    assert above.cursor().shape() == Qt.CursorShape.ArrowCursor
    _enter(above)
    assert above.state() == "idle"
    backdrop = _rgb(theme.SURFACE_BACKDROP)
    assert set(_pixels(_grab_handle(win, above)).values()) == {backdrop}
    _leave(above)
    for i in range(1, splitter.count()):
        if i != splitter.indexOf(win.coordinates):
            assert splitter.handle(i).isEnabled(), i
            assert splitter.handle(i).cursor().shape() == Qt.CursorShape.SplitVCursor

    extra = QLabel("extra")
    splitter.insertWidget(1, extra)
    _settle()
    index = splitter.indexOf(win.coordinates)
    assert not splitter.handle(index).isEnabled()
    assert all(splitter.handle(i).isEnabled() for i in range(splitter.count()) if i != index)
    dock = QLabel("right dock")
    win.add_dock("chrome_right", "Right", dock, "right")
    _settle()
    index = splitter.indexOf(win.coordinates)
    assert splitter.indexOf(dock) == splitter.count() - 1
    assert not splitter.handle(index).isEnabled()
    assert splitter.handle(splitter.indexOf(dock)).isEnabled()
    win.apply_default_sizes()
    _settle()
    assert win.coordinates.height() == 120


def _near(color, tint, tol: int = 6) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(_rgb(color), _rgb(tint)))


def _switcher_window(w: int, h: int):
    win = _window(w, h)
    for page_id, title in (("chrome_mat", "Materials"), ("chrome_uv", "UV Edit"),
                           ("chrome_script", "Script"), ("chrome_render", "Render")):
        win.add_page(page_id, title, QLabel(title))
    win.resize(w, h)
    _settle()
    return win


def _pill_gaps(image, box: QRect, probe_x: int) -> tuple[int, int, int, int]:
    tint = QColor(theme.ACCENT_TINT)
    column = [image.pixelColor(probe_x, y) for y in range(box.top(), box.bottom() + 1)]
    row_y = box.top() + box.height() // 2
    row = [image.pixelColor(x, row_y) for x in range(box.left(), box.right() + 1)]
    top = next(i for i, c in enumerate(column) if _near(c, tint))
    bottom = next(i for i, c in enumerate(reversed(column)) if _near(c, tint))
    left = next(i for i, c in enumerate(row) if _near(c, tint))
    right = next(i for i, c in enumerate(reversed(row)) if _near(c, tint))
    return top, left, bottom, right


def _ink_clusters(image, pill: QRect) -> list[tuple[int, int, int, int]]:
    tint = QColor(theme.ACCENT_TINT)
    columns = {}
    for x in range(pill.left() + 5, pill.right() - 4):
        ys = [y for y in range(pill.top() + 3, pill.bottom() - 2)
              if not _near(image.pixelColor(x, y), tint, 10)]
        if ys:
            columns[x] = (min(ys), max(ys))
    clusters: list[list[int]] = []
    for x in sorted(columns):
        top, bottom = columns[x]
        if clusters and x - clusters[-1][1] <= 2:
            c = clusters[-1]
            c[1], c[2], c[3] = x, min(c[2], top), max(c[3], bottom)
        else:
            clusters.append([x, x, top, bottom])
    return [tuple(c) for c in clusters]


def test_page_switcher_pill_is_concentric_with_its_border() -> None:
    from quartz_studio.main_window import PAGE_BUTTON_H

    assert PAGE_BUTTON_H == theme.SEGMENT_H - 2 * theme.SEGMENT_PAD == 26
    for size in ((1920, 1010), (1280, 720)):
        win = _switcher_window(*size)
        switcher = win.page_switcher
        assert switcher.isVisible() and switcher.height() == theme.SEGMENT_H
        assert switcher.is_compact() == (size[0] == 1280)
        mode = win.command_bar.mode_switcher
        sw_rect = QRect(switcher.mapTo(win, QPoint(0, 0)), switcher.size())
        mode_rect = QRect(mode.mapTo(win, QPoint(0, 0)), mode.size())
        assert sw_rect.height() == mode_rect.height() == theme.SEGMENT_H
        assert sw_rect.center().y() == mode_rect.center().y(), (sw_rect, mode_rect)
        assert abs(mode_rect.center().x() + 0.5 - win.top_bar.width() / 2) <= 1
        current = switcher.compact_button if switcher.is_compact() else switcher.buttons["model"]
        geom = current.geometry()
        assert geom.top() == geom.left() == theme.SEGMENT_PAD, geom
        assert switcher.height() - geom.bottom() - 1 == theme.SEGMENT_PAD, geom
        if switcher.is_compact():
            assert switcher.width() - geom.right() - 1 == theme.SEGMENT_PAD, geom
        image = win.grab().toImage()
        probe_x = sw_rect.x() + geom.x() + geom.width() // 2
        top, left, bottom, right = _pill_gaps(image, sw_rect, probe_x)
        assert (top, left, bottom) == (theme.SEGMENT_PAD,) * 3, (top, left, bottom, right)
        if switcher.is_compact():
            assert right == theme.SEGMENT_PAD, right
            pill = QRect(sw_rect.x() + left, sw_rect.y() + top,
                         sw_rect.width() - left - right, sw_rect.height() - top - bottom)
            clusters = _ink_clusters(image, pill)
            assert len(clusters) == 2, clusters
            text, chevron = clusters
            lift = (text[2] - pill.top()) - (pill.bottom() - text[3])
            assert abs(lift) <= 1, (text, pill)
            assert abs((chevron[2] - pill.top()) - (pill.bottom() - chevron[3])) <= 1, (chevron, pill)
            pad_left = text[0] - pill.left()
            pad_right = pill.right() - chevron[1]
            assert abs(pad_left - pad_right) <= 1, (pad_left, pad_right)
            assert chevron[0] - text[1] - 1 in (4, 5, 6), (text, chevron)
        else:
            pill = QRect(sw_rect.x() + geom.x(), sw_rect.y() + top, geom.width(),
                         sw_rect.height() - top - bottom)
            ink = _ink_clusters(image, pill)
            assert len(ink) == 1, ink
            lift = (ink[0][2] - pill.top()) - (pill.bottom() - ink[0][3])
            assert abs(lift) <= 1, (ink, pill)
            assert abs((ink[0][0] - pill.left()) - (pill.right() - ink[0][1])) <= 1, (ink, pill)


def test_page_switcher_menu_matches_the_other_menus() -> None:
    from quartz_studio.widgets import menu_bar

    win = _switcher_window(1280, 720)
    switcher = win.page_switcher
    menu = switcher.build_page_menu()
    assert isinstance(menu, menu_bar.StudioMenu)
    assert menu.entries_text() == ["Model", "Materials", "UV Edit", "Script", "Render"]
    assert [bool(a.property("qs_check")) for a in menu.actions()] == [True, False, False, False, False]
    assert all(menu.actionGeometry(a).height() == theme.MENU_ROW_H for a in menu.actions())
    switcher.open_page_menu()
    _settle()
    popup = switcher.page_menu
    anchor = switcher.mapToGlobal(QPoint(0, switcher.height() + theme.SPACE_1))
    assert popup.x() == anchor.x() and popup.y() == anchor.y(), (popup.pos(), anchor)
    popup.hide()
    menu.deleteLater()


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
    for w in _KEEP:
        w.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
