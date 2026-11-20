from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import quartz_studio
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QEnterEvent, QFocusEvent, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QWidget,
)

from quartz_studio import theme
from quartz_studio.app import create_app

FLASH_MS = 100
SETTLE_MS = 450

_WINDOW = None
_HOST = None
_STANDALONE: list[QWidget] = []


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(app: QApplication, passes: int = 6) -> None:
    for _ in range(passes):
        app.processEvents()


def _window():
    global _WINDOW
    if _WINDOW is None:
        app = _app()
        from quartz_studio.scene import reset_scene

        reset_scene()
        from quartz_studio.main_window import MainWindow

        win = MainWindow()
        win.setMinimumSize(1, 1)
        win.resize(1920, 1007)
        win.show()
        _settle(app)
        win.apply_default_sizes()
        _settle(app)
        _WINDOW = win
    return _WINDOW


def _host() -> QWidget:
    global _HOST
    if _HOST is None:
        _app()
        _HOST = QWidget()
        _HOST.setObjectName("qsFeedbackTestHost")
        QHBoxLayout(_HOST)
        _HOST.resize(320, 60)
        _HOST.show()
        _settle(QApplication.instance())
    return _HOST


def _standalone(widget: QWidget, width: int, height: int) -> QWidget:
    widget.resize(width, height)
    widget.show()
    _settle(QApplication.instance())
    _STANDALONE.append(widget)
    return widget


def _checked_mode_button():
    return next(b for b in _window().regions["command_bar"].mode_buttons() if b.isChecked())


def _add(widget: QWidget) -> QWidget:
    host = _host()
    host.layout().addWidget(widget)
    widget.show()
    _settle(QApplication.instance())
    return widget


def _pf():
    from quartz_studio.widgets import press_feedback

    return press_feedback


def _enter(w: QWidget) -> None:
    local = QPointF(2, 2)
    QApplication.sendEvent(w, QEnterEvent(local, local, QPointF(w.mapToGlobal(QPoint(2, 2)))))


def _leave(w: QWidget) -> None:
    QApplication.sendEvent(w, QEvent(QEvent.Type.Leave))


def _press(w: QWidget, pos: QPoint | None = None) -> None:
    QTest.mousePress(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     pos if pos is not None else w.rect().center())


def _release(w: QWidget, pos: QPoint | None = None) -> None:
    QTest.mouseRelease(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       pos if pos is not None else w.rect().center())


def _drag_to(w: QWidget, pos: QPoint) -> None:
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(pos), QPointF(w.mapToGlobal(pos)),
                     Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


def _close_popups() -> None:
    for _ in range(5):
        popup = QApplication.activePopupWidget()
        if popup is None:
            break
        popup.close()
        _settle(QApplication.instance(), 2)


def _peak_press(ov, ms: int = FLASH_MS) -> int:
    peak = ov.press_alpha()
    waited = 0
    while waited < ms:
        QTest.qWait(10)
        waited += 10
        peak = max(peak, ov.press_alpha())
    return peak


def _luma(pm: QPixmap) -> float:
    img = pm.toImage()
    total = 0.0
    count = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            a = c.alphaF()
            total += (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) * a
            count += 1
    return total / max(1, count)


def _region(win: QWidget, w: QWidget) -> QPixmap:
    return win.grab(QRect(w.mapTo(win, QPoint(0, 0)), w.size()))


def _check_press_cycle(button: QAbstractButton, *, menu: bool = False) -> None:
    pf = _pf()
    _enter(button)
    QTest.qWait(150)
    ov = pf.overlay_of(button)
    assert ov is not None, f"no overlay on {button!r}"
    assert ov.hover_alpha() > 0, "hover did not light the button"
    _press(button)
    peak = _peak_press(ov)
    assert peak >= 40, f"press alpha did not rise (peak {peak})"
    if menu:
        assert QApplication.activePopupWidget() is not None, "the button menu did not open"
        _close_popups()
    else:
        assert ov.press_alpha() >= 40, f"press not held while the button is down ({ov.press_alpha()})"
    _release(button)
    QTest.qWait(SETTLE_MS)
    assert ov.press_alpha() == 0, f"press alpha did not decay ({ov.press_alpha()})"
    _leave(button)
    QTest.qWait(SETTLE_MS)
    _close_popups()
    assert ov.hover_alpha() == 0 and ov.press_alpha() == 0
    assert ov.is_idle(), "animations still running after the button settled"
    assert ov.isHidden(), "idle overlay should be hidden"



def test_filter_installed_once() -> None:
    pf = _pf()
    app = _app()
    _app()
    found = [c for c in app.children() if c.objectName() == pf.FILTER_NAME]
    assert len(found) == 1, found
    assert pf.installed(app) is found[0]


def test_icon_button_overlay_cycle() -> None:
    win = _window()
    button = win.regions["viewport"].menu_bar.nav_buttons[0]
    assert button.isEnabled()
    _check_press_cycle(button)


def test_command_bar_foldout_button_cycle() -> None:
    from quartz_studio.widgets.command_bar import FoldoutButton

    button = _checked_mode_button()
    assert isinstance(button, FoldoutButton)
    _check_press_cycle(button)


def test_menu_push_buttons_cycle() -> None:
    win = _window()
    for view_menu in win.regions["viewport"].menu_bar.menu_buttons:
        assert view_menu.menu() is not None
        _check_press_cycle(view_menu, menu=True)


def test_panel_tab_cycle() -> None:
    tab = _window().regions["object_manager"].tabs._buttons[0]
    assert tab.objectName() == "qsPanelTab" and tab.isChecked()
    _check_press_cycle(tab)
    assert tab.isChecked()
    assert _pf().overlay_of(tab).look().radius == theme.CONTROL_RADIUS, "panel tabs follow the control radius"


def test_title_row_buttons_animate() -> None:
    from quartz_studio.widgets.title_row import TitleRow

    title_row = TitleRow()
    _standalone(title_row, 1400, title_row.height())
    _check_press_cycle(title_row.new_tab_button)
    tab = title_row.layout_tabs[title_row.active_layout()]
    _check_press_cycle(tab)


def test_main_menu_bar_title_flashes() -> None:
    pf = _pf()
    bar = _window().regions["menu_bar"]
    act = next(a for a in bar.actions() if a.isEnabled() and a.menu() is not None)
    pos = bar.actionGeometry(act).center()
    _press(bar, pos)
    ov = pf.overlay_of(bar)
    assert ov is not None
    assert _peak_press(ov) >= 40
    _close_popups()
    _release(bar, pos)
    QTest.qWait(SETTLE_MS)
    _close_popups()
    assert ov.press_alpha() == 0 and ov.is_idle() and ov.isHidden()


def test_group_hold_menu_releases_press() -> None:
    win = _window()
    palette = win.regions["object_palette"]
    button = next(b for b in palette.buttons.values()
                  if b.isEnabled() and b.isVisibleTo(win) and b.group())
    _hold_menu_releases_press(button)


def test_modeling_group_hold_menu_releases_press() -> None:
    win = _window()
    button = win.regions["tool_palette"].buttons["Extrude"]
    assert button.isVisibleTo(win) and button.group()
    _hold_menu_releases_press(button)
    assert not button.isChecked()
    assert win.regions["tool_palette"].buttons["Move"].isChecked()


def _hold_menu_releases_press(button) -> None:
    from PySide6.QtCore import QTimer

    from quartz_studio.widgets.common import IconButton

    pf = _pf()
    win = _window()
    shown_before = (button.icon_name(), button.command_text())
    seen: dict[str, object] = {}

    def probe() -> None:
        ov = pf.overlay_of(button)
        seen["popup"] = QApplication.activePopupWidget() is not None
        seen["alpha"] = ov.press_alpha() if ov is not None else None
        _close_popups()

    QTimer.singleShot(IconButton.HOLD_MS + 320, probe)
    _press(button)
    QTest.qWait(IconButton.HOLD_MS + 450)
    _release(button)
    QTest.qWait(SETTLE_MS)
    _close_popups()
    ov = pf.overlay_of(button)
    assert seen.get("popup"), "press-and-hold did not open the fold-out"
    assert seen.get("alpha") == 0, f"press stayed dark under the open fold-out ({seen})"
    assert ov.press_alpha() == 0 and ov.is_idle() and ov.isHidden()
    assert (button.icon_name(), button.command_text()) == shown_before


def test_checkboxes_and_radios_get_no_overlay() -> None:
    pf = _pf()
    window = _window()
    attributes = window.attribute_manager
    assert not [w for w in window.findChildren(QCheckBox) if not attributes.isAncestorOf(w)]
    for box in window.findChildren(QCheckBox):
        assert pf.overlay_of(box) is None, "a checkbox in the window got an overlay"
    extra_box = _add(QCheckBox("Check"))
    extra_radio = _add(QRadioButton("Radio"))
    for w in [extra_box, extra_radio]:
        before = w.isChecked()
        _enter(w)
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(4, w.height() // 2))
        QTest.qWait(FLASH_MS)
        _leave(w)
        assert pf.overlay_of(w) is None, f"{type(w).__name__} got an overlay"
        if not isinstance(w, QRadioButton):
            assert w.isChecked() != before, f"{type(w).__name__} stopped toggling"
            w.setChecked(before)


def test_disabled_buttons_get_no_overlay() -> None:
    pf = _pf()
    from quartz_studio.widgets.common import IconButton

    from quartz_studio.widgets.sculpt_bar import SculptBar

    sculpt = SculptBar()
    _standalone(sculpt, 1200, sculpt.height())
    disabled = [b for b in sculpt.findChildren(QAbstractButton) if not b.isEnabled()]
    assert disabled, "the sculpt bar should be disabled"
    standalone = _add(IconButton("pal_mode_points", "Disabled", enabled=False))
    for b in (disabled[0], standalone):
        _enter(b)
        _press(b)
        QTest.qWait(FLASH_MS)
        _release(b)
        _leave(b)
        assert pf.overlay_of(b) is None, f"disabled {b.toolTip()!r} got an overlay"


def test_disabling_drops_the_overlay() -> None:
    pf = _pf()
    button = _add(QPushButton("Temporary"))
    _enter(button)
    _press(button)
    QTest.qWait(FLASH_MS)
    ov = pf.overlay_of(button)
    assert ov is not None and ov.press_alpha() > 0
    button.setEnabled(False)
    _settle(QApplication.instance())
    assert ov.isHidden() and ov.press_alpha() == 0 and ov.hover_alpha() == 0
    _release(button)
    button.setEnabled(True)
    _leave(button)


def test_clicked_fires_exactly_once() -> None:
    from quartz_studio.widgets.common import IconButton

    clicks: list[bool] = []
    button = _add(IconButton("pal_commander", "Click"))
    button.clicked.connect(lambda checked=False: clicks.append(checked))
    _enter(button)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     button.rect().center())
    QTest.qWait(SETTLE_MS)
    assert len(clicks) == 1, clicks
    real = _checked_mode_button()
    real_clicks: list[bool] = []

    def count(checked: bool = False) -> None:
        real_clicks.append(checked)

    real.clicked.connect(count)
    QTest.qWait(500)
    QTest.mouseClick(real, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     real.rect().center())
    QTest.qWait(FLASH_MS)
    real.clicked.disconnect(count)
    assert len(real_clicks) == 1, real_clicks
    _leave(button)


def test_pressed_grab_is_darker() -> None:
    from quartz_studio.widgets.common import IconButton

    button = _add(IconButton("pal_render_view", "Darken"))
    idle = _luma(button.grab())
    _press(button)
    QTest.qWait(FLASH_MS)
    ov = _pf().overlay_of(button)
    pressed = _luma(button.grab())
    ov.hide()
    bare = _luma(button.grab())
    _release(button)
    QTest.qWait(SETTLE_MS)
    after = _luma(button.grab())
    assert pressed < bare - 3, f"pressed {pressed:.1f} vs the same state without the layer {bare:.1f}"
    assert abs(after - idle) < 1.0, f"did not return to idle ({after:.1f} vs {idle:.1f})"
    win = _window()
    real = _checked_mode_button()
    idle = _luma(_region(win, real))
    _press(real)
    QTest.qWait(FLASH_MS)
    ov = _pf().overlay_of(real)
    pressed = _luma(_region(win, real))
    ov.hide()
    bare = _luma(_region(win, real))
    _release(real)
    QTest.qWait(SETTLE_MS)
    assert pressed < bare - 3, f"segment button pressed {pressed:.1f} vs the same state without the layer {bare:.1f}"
    assert abs(_luma(_region(win, real)) - idle) < 1.0, "segment button did not return to idle"


def test_hover_brightens_then_fades() -> None:
    from quartz_studio.widgets.common import IconButton

    button = _add(IconButton("pal_symmetry", "Lighten"))
    idle = _luma(button.grab())
    _enter(button)
    ov = _pf().overlay_of(button)
    seen = [ov.hover_alpha()]
    for _ in range(30):
        QTest.qWait(10)
        seen.append(ov.hover_alpha())
    full = seen[-1]
    assert full >= 12, seen
    assert any(0 < a < full for a in seen), f"hover jumped instead of fading in: {seen}"
    assert seen == sorted(seen), f"hover did not rise steadily: {seen}"
    assert _luma(button.grab()) > idle + 3
    _leave(button)
    QTest.qWait(SETTLE_MS)
    assert ov.hover_alpha() == 0 and ov.isHidden() and ov.is_idle()


def test_toggle_pulses() -> None:
    from quartz_studio.widgets.common import IconButton

    button = _add(IconButton("pal_axis_x", "Toggle", checkable=True))
    _enter(button)
    QTest.qWait(150)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     button.rect().center())
    QTest.qWait(20)
    ov = _pf().overlay_of(button)
    assert button.isChecked()
    assert ov.pulse_level() > 0.3, ov.pulse_level()
    QTest.qWait(SETTLE_MS)
    assert ov.pulse_level() == 0 and ov.is_idle()
    _leave(button)


def test_drag_out_and_back() -> None:
    clicks: list[bool] = []
    button = _add(QPushButton("Drag"))
    button.clicked.connect(lambda: clicks.append(True))
    _press(button)
    QTest.qWait(FLASH_MS)
    ov = _pf().overlay_of(button)
    assert ov.press_alpha() > 40
    _drag_to(button, QPoint(-30, -30))
    QTest.qWait(SETTLE_MS)
    assert ov.press_alpha() == 0, "dragging off the button should lift the press"
    _drag_to(button, button.rect().center())
    QTest.qWait(FLASH_MS)
    assert ov.press_alpha() > 40, "dragging back should press it again"
    _drag_to(button, QPoint(-30, -30))
    _release(button, QPoint(-30, -30))
    QTest.qWait(SETTLE_MS)
    assert ov.press_alpha() == 0 and ov.is_idle()
    assert clicks == [], "releasing outside must not click"


def test_overlay_is_inert_child() -> None:
    pf = _pf()
    button = _add(QPushButton("Inert"))
    _enter(button)
    QTest.qWait(50)
    ov = pf.overlay_of(button)
    assert ov.parentWidget() is button
    assert ov.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert ov.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert button.childAt(button.rect().center()) is None
    assert ov.geometry() == button.rect()
    button.setFixedWidth(button.width() + 40)
    _settle(QApplication.instance())
    assert ov.geometry() == button.rect(), "overlay must follow the button size"
    skipped = QPushButton("No Effect")
    skipped.setProperty(pf.OPT_OUT_PROPERTY, False)
    _add(skipped)
    _enter(skipped)
    assert pf.overlay_of(skipped) is None
    _leave(button)
    _leave(skipped)


def test_every_button_kind_is_covered() -> None:
    pf = _pf()
    win = _window()
    seen: dict[str, bool] = {}
    for b in win.findChildren(QAbstractButton):
        key = f"{type(b).__name__}#{b.objectName()}"
        if key in seen or not b.isEnabled() or not b.isVisibleTo(win):
            continue
        _enter(b)
        _leave(b)
        excluded = isinstance(b, (QCheckBox, QRadioButton))
        seen[key] = (pf.overlay_of(b) is None) == excluded
    QTest.qWait(SETTLE_MS)
    wrong = [k for k, ok in seen.items() if not ok]
    assert len(seen) >= 4, seen
    assert not wrong, f"wrong feedback coverage: {wrong}"



L_BUTTON = Qt.MouseButton.LeftButton
NO_MOD = Qt.KeyboardModifier.NoModifier


def _at(win: QWidget, w: QWidget, pos: QPoint | None = None) -> QPoint:
    return w.mapTo(win, pos if pos is not None else w.rect().center())


def _neutral(win: QWidget) -> QPoint:
    return _at(win, win.regions["menu_bar"], QPoint(700, 10))


def _find_button(root: QWidget, label: str) -> QAbstractButton:
    for b in root.findChildren(QAbstractButton):
        if label in (b.toolTip(), b.toolTip().split(" (")[0], b.text()) and b.isVisibleTo(root.window()):
            return b
    raise AssertionError(f"no visible button {label!r}")


def _camera_state(canvas) -> tuple:
    cam = canvas.camera
    return (round(cam.heading, 3), round(cam.pitch, 3), round(cam.distance, 3),
            tuple(round(float(v), 3) for v in cam.target))


def test_other_buttons_do_not_lift_the_left_press() -> None:
    pf = _pf()
    win = _window()
    wh = win.windowHandle()
    button = _checked_mode_button()
    centre, away = _at(win, button), _neutral(win)
    QTest.mouseMove(wh, away)
    QTest.qWait(50)
    QTest.mouseMove(wh, centre)
    QTest.qWait(50)
    QTest.mousePress(wh, L_BUTTON, NO_MOD, centre)
    ov = pf.overlay_of(button)
    assert ov is not None and _peak_press(ov) >= 40
    for other in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
        QTest.mousePress(wh, other, NO_MOD, centre)
        QTest.mouseRelease(wh, other, NO_MOD, centre)
    QTest.qWait(SETTLE_MS)
    _close_popups()
    assert button.isDown(), "the button should still be down"
    assert ov.press_alpha() >= 40, f"flash lifted while the left button is held ({ov.press_alpha()})"
    QTest.mouseMove(wh, away)
    QTest.mouseRelease(wh, L_BUTTON, NO_MOD, away)
    QTest.qWait(SETTLE_MS)
    assert not button.isDown() and ov.press_alpha() == 0 and ov.is_idle()


class _KeepDown(QObject):

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        return ev.type() == QEvent.Type.MouseMove and bool(ev.buttons() & L_BUTTON)


def test_flash_follows_the_button_down_state() -> None:
    clicks: list[bool] = []
    button = _add(QPushButton("Fixed"))
    keeper = _KeepDown(button)
    button.installEventFilter(keeper)
    button.clicked.connect(lambda: clicks.append(True))
    _press(button)
    QTest.qWait(FLASH_MS)
    ov = _pf().overlay_of(button)
    far = QPoint(-60, -40)
    _drag_to(button, far)
    QTest.qWait(SETTLE_MS)
    assert button.isDown(), "the filter should have kept the button down"
    assert ov.press_alpha() >= 40, f"flash lifted while the button is down ({ov.press_alpha()})"
    _release(button, far)
    QTest.qWait(SETTLE_MS)
    assert not button.isDown() and ov.press_alpha() == 0 and ov.is_idle()
    assert clicks == [], "releasing outside must not click"
    button.removeEventFilter(keeper)


def test_hold_property_keeps_a_nav_icon_dark() -> None:
    pf = _pf()
    win = _window()
    wh = win.windowHandle()
    viewport = win.regions["viewport"]
    nav = viewport.menu_bar.nav_buttons[2]
    old = nav.property(pf.HOLD_PROPERTY)
    nav.setProperty(pf.HOLD_PROPERTY, True)
    clicks: list[bool] = []

    def count(checked: bool = False) -> None:
        clicks.append(checked)

    nav.clicked.connect(count)
    try:
        cam_before = _camera_state(viewport.canvas)
        centre = _at(win, nav)
        QTest.mouseMove(wh, _neutral(win))
        QTest.qWait(50)
        QTest.mouseMove(wh, centre)
        QTest.qWait(150)
        QTest.mousePress(wh, L_BUTTON, NO_MOD, centre)
        ov = pf.overlay_of(nav)
        assert ov is not None and _peak_press(ov, 80) >= 40
        for i in range(1, 6):
            QTest.mouseMove(wh, centre + QPoint(-12 * i, 6 * i))
            QTest.qWait(15)
        QTest.qWait(SETTLE_MS)
        assert _camera_state(viewport.canvas) != cam_before, "the drag did not navigate"
        assert ov.press_alpha() >= 40, f"nav icon lifted during the drag ({ov.press_alpha()})"
        assert ov.hover_alpha() == 0, "the hover tint should not show under the press"
        end = centre + QPoint(-60, 30)
        QTest.mouseRelease(wh, L_BUTTON, NO_MOD, end)
        QTest.qWait(SETTLE_MS)
        QTest.mouseMove(wh, _neutral(win))
        QTest.qWait(SETTLE_MS)
        assert ov.press_alpha() == 0 and ov.is_idle() and ov.isHidden()
        assert clicks == [], "a navigation drag must not click the icon"
    finally:
        nav.clicked.disconnect(count)
        nav.setProperty(pf.HOLD_PROPERTY, old)
        viewport.canvas.reset_camera()


def test_checked_and_tab_buttons_flash_darker() -> None:
    from quartz_studio.modeling import get_tool
    from quartz_studio.modeling.install import tool_tooltip

    win = _window()
    wh = win.windowHandle()
    targets = [
        _find_button(win.regions["command_bar"], "Model"),
        _find_button(win.regions["command_bar"], "Points"),
        _find_button(win.regions["tool_palette"], "Move"),
        _find_button(win.regions["tool_palette"], tool_tooltip(get_tool("bevel"))),
        _find_button(win.regions["object_manager"], "Hierarchy"),
    ]
    away = _neutral(win)
    for b in targets:
        checked = b.isChecked()
        QTest.mouseMove(wh, away)
        QTest.qWait(SETTLE_MS)
        idle = _luma(_region(win, b))
        QTest.mouseMove(wh, _at(win, b))
        QTest.qWait(200)
        hover = _luma(_region(win, b))
        QTest.mousePress(wh, L_BUTTON, NO_MOD, _at(win, b))
        QTest.qWait(FLASH_MS)
        pressed = _luma(_region(win, b))
        QTest.mouseMove(wh, away)
        QTest.mouseRelease(wh, L_BUTTON, NO_MOD, away)
        QTest.qWait(SETTLE_MS)
        _close_popups()
        name = (b.toolTip() or b.text()).encode("ascii", "replace").decode()
        assert hover > idle + 1, f"{name}: hover {hover:.1f} vs idle {idle:.1f}"
        assert pressed < idle - 3, f"{name}: pressed {pressed:.1f} vs idle {idle:.1f}"
        assert b.isChecked() == checked, f"{name}: state changed"
        assert abs(_luma(_region(win, b)) - idle) < 1.0, f"{name}: did not return to idle"


def test_toggle_switch_flashes() -> None:
    from quartz_studio.widgets.common import ToggleSwitch

    pf = _pf()
    switch = _add(ToggleSwitch())
    idle = _luma(switch.grab())
    _enter(switch)
    QTest.qWait(150)
    ov = pf.overlay_of(switch)
    assert ov is not None and ov.look().shape == "capsule"
    assert ov.hover_alpha() == 0, "the switch paints its own hover"
    _press(switch)
    assert _peak_press(ov) >= 40
    assert _luma(switch.grab()) < idle - 5, "a pressed switch should look darker"
    _release(switch)
    QTest.qWait(SETTLE_MS)
    assert switch.isChecked(), "the switch stopped toggling"
    assert ov.press_alpha() == 0
    _leave(switch)
    QTest.qWait(SETTLE_MS)
    assert ov.is_idle() and ov.isHidden()


def test_group_header_hover_and_press() -> None:
    from quartz_studio.widgets.common import CollapsibleGroup

    pf = _pf()
    from quartz_studio.scene import get_scene
    from quartz_studio.widgets.attribute_manager import AttributeManager

    get_scene().add_parametric("cube")
    win = _standalone(AttributeManager(), 420, 520)
    groups = [g for g in win.findChildren(CollapsibleGroup)
              if g.isVisibleTo(win) and g.header.isVisibleTo(win)]
    assert groups, "the attribute manager should show collapsible groups"
    group = groups[0]
    header = group.header
    expanded = group.is_expanded()
    idle = _luma(_region(win, header))
    _enter(header)
    QTest.qWait(150)
    ov = pf.overlay_of(header)
    assert ov is not None and ov.hover_alpha() >= 12
    assert _luma(_region(win, header)) > idle + 2, "hover should light the row"
    _press(header, QPoint(header.width() - 20, header.height() // 2))
    assert _peak_press(ov) >= 40
    assert group.is_expanded() != expanded, "the group should still collapse/expand"
    _release(header, QPoint(header.width() - 20, header.height() // 2))
    QTest.qWait(SETTLE_MS)
    assert ov.press_alpha() == 0
    _leave(header)
    QTest.qWait(SETTLE_MS)
    assert ov.is_idle() and ov.isHidden()
    group.set_expanded(expanded)
    _settle(QApplication.instance())
    assert abs(_luma(_region(win, header)) - idle) < 1.0


def test_layers_use_the_crystal_tokens() -> None:
    pf = _pf()
    assert pf.HOVER_COLOR == theme.TEXT_PRIMARY
    assert pf.PRESS_COLOR == theme.SURFACE_FIELD
    assert pf.PULSE_COLOR == theme.ACCENT and pf.PULSE_ALPHA == theme.ACCENT_ALPHA
    assert pf.FOCUS_COLOR == theme.FOCUS_RING and pf.FOCUS_WIDTH == theme.FOCUS_RING_W
    assert 10 <= pf.HOVER_ALPHA <= 18
    button = _add(QPushButton("Tokens"))
    _enter(button)
    QTest.qWait(150)
    ov = pf.overlay_of(button)
    assert ov.look().radius == theme.CONTROL_RADIUS
    _press(button)
    QTest.qWait(FLASH_MS)
    image = button.grab().toImage()
    centre = image.pixelColor(button.width() // 2, 2)
    _release(button)
    QTest.qWait(SETTLE_MS)
    _leave(button)
    assert centre.red() < 60 and centre.blue() < 70, centre.name()


def test_mode_switcher_and_chips_use_pill_looks() -> None:
    pf = _pf()
    win = _window()
    for b in win.regions["command_bar"].mode_buttons():
        _enter(b)
        look = pf.overlay_of(b).look()
        assert look.shape == "capsule", b.toolTip()
        _leave(b)
    chip = _add(_find_chip())
    _enter(chip)
    assert pf.overlay_of(chip).look().radius == theme.CHIP_H / 2
    _leave(chip)
    tool = _find_button(win.regions["tool_palette"], "Move")
    _enter(tool)
    assert pf.overlay_of(tool).look().radius == theme.CONTROL_RADIUS
    assert pf.overlay_of(tool).look().shape != "capsule"
    _leave(tool)
    QTest.qWait(SETTLE_MS)


def _find_chip():
    from quartz_studio.widgets.common import Chip

    return Chip("Basic")


def test_keyboard_focus_draws_a_ring_and_mouse_focus_does_not() -> None:
    pf = _pf()
    button = _add(QPushButton("Focus"))
    QApplication.sendEvent(button, QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.MouseFocusReason))
    assert pf.overlay_of(button) is None or not pf.overlay_of(button).has_focus_ring()
    QApplication.sendEvent(button, QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason))
    ov = pf.overlay_of(button)
    assert ov is not None and ov.has_focus_ring() and not ov.isHidden()
    image = button.grab().toImage()
    edge = image.pixelColor(button.width() // 2, 0)
    assert abs(edge.red() - 0x5E) < 40 and abs(edge.green() - 0xE6) < 40, edge.name()
    QApplication.sendEvent(button, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.TabFocusReason))
    assert not ov.has_focus_ring() and ov.isHidden()


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
