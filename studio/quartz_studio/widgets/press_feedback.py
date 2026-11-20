from __future__ import annotations

from typing import NamedTuple

import shiboken6
from PySide6.QtCore import QEasingCurve, QEvent, QObject, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QMenuBar,
    QPushButton,
    QRadioButton,
    QToolButton,
    QWidget,
)

from quartz_studio import theme

__all__ = [
    "HOLD_PROPERTY",
    "LOOK_ATTR",
    "OPT_OUT_PROPERTY",
    "FeedbackOverlay",
    "PressFeedback",
    "install",
    "installed",
    "overlay_of",
]

HOVER_ALPHA = 14
PRESS_ALPHA = 96
PULSE_ALPHA = theme.ACCENT_ALPHA

HOVER_COLOR = theme.TEXT_PRIMARY
PRESS_COLOR = theme.SURFACE_FIELD
PULSE_COLOR = theme.ACCENT
FOCUS_COLOR = theme.FOCUS_RING
FOCUS_WIDTH = theme.FOCUS_RING_W

HOVER_IN_MS = 120
HOVER_OUT_MS = 200
PRESS_MS = 60
RELEASE_MS = 200
PULSE_MS = 300

SOFT_HOVER = 0.5

OVERLAY_NAME = "qsPressOverlay"
FILTER_NAME = "qsPressFeedback"
OPT_OUT_PROPERTY = "qsPressFeedback"
HOLD_PROPERTY = "qsPressHold"
LOOK_ATTR = "qs_feedback_look"

_RADIUS_BY_NAME = {
    "qsPanelTab": float(theme.CONTROL_RADIUS),
    "qsPanelMenu": float(theme.CONTROL_RADIUS),
    "qsViewMenu": float(theme.CONTROL_RADIUS),
    "qsResetTransform": float(theme.CONTROL_RADIUS),
    "qsIconButton": float(theme.CONTROL_RADIUS),
    "qsChip": theme.CHIP_H / 2,
}
ROLE_PROPERTY = "qsRole"
PILL_ROLES = frozenset({"modes"})
FOCUS_REASONS = frozenset({
    Qt.FocusReason.TabFocusReason,
    Qt.FocusReason.BacktabFocusReason,
    Qt.FocusReason.ShortcutFocusReason,
})

_ATTR = "_qs_press_overlay"
_LEFT = Qt.MouseButton.LeftButton
_T = QEvent.Type
_WATCHED = frozenset({
    _T.Enter, _T.Leave, _T.MouseButtonPress, _T.MouseButtonDblClick, _T.MouseButtonRelease,
    _T.MouseMove, _T.EnabledChange, _T.Resize, _T.Show, _T.Hide, _T.FocusIn, _T.FocusOut,
})
_PRESSES = frozenset({_T.MouseButtonPress, _T.MouseButtonDblClick})


class _Look(NamedTuple):

    shape: str
    radius: float
    hover: float
    press: float



class _Level(QVariantAnimation):

    def __init__(self, overlay: FeedbackOverlay) -> None:
        super().__init__(overlay)
        self.value = 0.0
        self.valueChanged.connect(self._on_value)
        self.finished.connect(overlay._settle)

    def _on_value(self, value) -> None:
        self.value = float(value)
        overlay = self.parent()
        if overlay is not None:
            overlay._changed()

    def running(self) -> bool:
        return self.state() == QVariantAnimation.State.Running

    def go(self, target: float, full_ms: int, curve: QEasingCurve.Type) -> None:
        self.stop()
        distance = abs(target - self.value)
        if distance < 1e-3:
            self.value = target
            overlay = self.parent()
            if overlay is not None:
                overlay._changed()
                overlay._settle()
            return
        self.setStartValue(self.value)
        self.setEndValue(float(target))
        self.setDuration(max(1, round(full_ms * distance)))
        self.setEasingCurve(curve)
        self.start()

    def jump(self, value: float) -> None:
        self.stop()
        self.value = value


class FeedbackOverlay(QWidget):

    def __init__(self, host: QWidget, look: _Look) -> None:
        super().__init__(host)
        self.setObjectName(OVERLAY_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._look = look
        self._hover = _Level(self)
        self._press = _Level(self)
        self._pulse = _Level(self)
        self._hovered = False
        self._down = False
        self._release_pending = False
        self._focused = False
        self.setGeometry(host.rect())
        self.hide()
        if isinstance(host, QAbstractButton):
            host.toggled.connect(self._on_toggled)

    def host(self) -> QWidget:
        return self.parentWidget()

    def look(self) -> _Look:
        return self._look

    def hover_level(self) -> float:
        return self._hover.value

    def press_level(self) -> float:
        return self._press.value

    def pulse_level(self) -> float:
        return self._pulse.value

    def hover_alpha(self) -> int:
        return round(self._white())

    def press_alpha(self) -> int:
        return round(self._black())

    def has_focus_ring(self) -> bool:
        return self._focused

    def set_focus_ring(self, on: bool) -> None:
        if on == self._focused:
            return
        self._focused = on
        if on:
            host = self.parentWidget()
            if host is not None:
                self.setGeometry(self._geometry_for(host))
            self.show()
            self.raise_()
            self.update()
        elif self.is_idle() and self._white() < 0.5 and self._black() < 0.5:
            self.hide()
        else:
            self.update()

    def is_idle(self) -> bool:
        return not (self._hover.running() or self._press.running() or self._pulse.running())

    def hover_in(self) -> None:
        self._hovered = True
        self._hover.go(1.0, HOVER_IN_MS, QEasingCurve.Type.OutCubic)

    def hover_out(self) -> None:
        self._hovered = False
        self._hover.go(0.0, HOVER_OUT_MS, QEasingCurve.Type.OutQuad)

    def press(self) -> None:
        self._down = True
        self._release_pending = False
        self._press.go(1.0, PRESS_MS, QEasingCurve.Type.OutCubic)

    def release(self) -> None:
        self._down = False
        if self._press.running() and self._press.endValue() == 1.0:
            self._release_pending = True
            return
        self._release_pending = False
        self._press.go(0.0, RELEASE_MS, QEasingCurve.Type.OutCubic)

    def pulse(self) -> None:
        self._pulse.jump(1.0)
        self._changed()
        self._pulse.go(0.0, PULSE_MS, QEasingCurve.Type.OutCubic)

    def reset(self) -> None:
        self._hovered = self._down = self._release_pending = self._focused = False
        for level in (self._hover, self._press, self._pulse):
            level.jump(0.0)
        self.hide()

    def is_down(self) -> bool:
        return self._down

    def _on_toggled(self, checked: bool) -> None:
        if checked or self._down or self._hovered or self._press.value > 0.0:
            self.pulse()

    def _changed(self) -> None:
        if self._white() >= 0.5 or self._black() >= 0.5 or self._focused:
            if self.isHidden():
                host = self.parentWidget()
                if host is not None:
                    self.setGeometry(self._geometry_for(host))
                self.show()
                self.raise_()
            self.update()
        elif not self.isHidden():
            self.update()

    def _settle(self) -> None:
        if self._release_pending and not self._press.running():
            self._release_pending = False
            self._press.go(0.0, RELEASE_MS, QEasingCurve.Type.OutCubic)
            return
        if self.is_idle() and self._white() < 0.5 and self._black() < 0.5 and not self._focused:
            self.hide()

    def _geometry_for(self, host: QWidget):
        return self.geometry() if isinstance(host, QMenuBar) else host.rect()

    def _hover_part(self) -> float:
        return self._look.hover * HOVER_ALPHA * self._hover.value * (1.0 - self._press.value)

    def _pulse_part(self) -> float:
        return PULSE_ALPHA * self._pulse.value

    def _white(self) -> float:
        return min(255.0, self._hover_part() + self._pulse_part())

    def _black(self) -> float:
        return self._look.press * PRESS_ALPHA * self._press.value

    def _shape(self) -> QRectF:
        r = QRectF(self.rect())
        shape = self._look.shape
        if shape == "square":
            side = min(r.width(), r.height())
            return QRectF(r.center().x() - side / 2, r.center().y() - side / 2, side, side)
        if shape == "pill":
            dx = min(12.0, r.width() / 4)
            dy = max(3.0, (r.height() - 20.0) / 2)
            return r.adjusted(dx, dy, -dx, -dy)
        return r

    def paintEvent(self, e: QPaintEvent) -> None:
        white, black = self._white(), self._black()
        if white < 0.5 and black < 0.5 and not self._focused:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        rect = self._shape()
        radius = rect.height() / 2 if self._look.shape == "capsule" else self._look.radius
        layers = ((self._hover_part(), HOVER_COLOR), (self._pulse_part(), PULSE_COLOR),
                  (black, PRESS_COLOR))
        for alpha, color in layers:
            if alpha < 0.5:
                continue
            fill = QColor(color)
            fill.setAlpha(min(255, round(alpha)))
            p.setBrush(fill)
            if radius > 0:
                p.drawRoundedRect(rect, radius, radius)
            else:
                p.drawRect(rect)
        if self._focused:
            half = FOCUS_WIDTH / 2
            ring = rect.adjusted(half, half, -half, -half)
            p.setPen(QPen(QColor(FOCUS_COLOR), FOCUS_WIDTH))
            p.setBrush(Qt.BrushStyle.NoBrush)
            inner = max(0.0, radius - half)
            if inner > 0:
                p.drawRoundedRect(ring, inner, inner)
            else:
                p.drawRect(ring)
        p.end()



def _excluded_types() -> tuple[type, ...]:
    return (QCheckBox, QRadioButton)


def _class_look(cls: type) -> _Look | None:
    spec = getattr(cls, LOOK_ATTR, None)
    if isinstance(spec, tuple) and len(spec) == 4:
        return _Look(str(spec[0]), float(spec[1]), float(spec[2]), float(spec[3]))
    return None


def _local_hover_rule(button: QWidget) -> bool:
    name = button.objectName()
    if not name:
        return False
    needle = f"#{name}:hover"
    w: QWidget | None = button
    while w is not None:
        sheet = w.styleSheet()
        if sheet and needle in sheet:
            return True
        w = w.parentWidget()
    return False


def _look_for(button: QWidget) -> _Look:
    custom = _class_look(type(button))
    if custom is not None:
        return custom
    name = button.objectName()
    radius = _RADIUS_BY_NAME.get(name, float(theme.CONTROL_RADIUS))
    parent = button.parentWidget()
    if parent is not None and parent.property(ROLE_PROPERTY) in PILL_ROLES:
        return _Look("capsule", radius, 1.0, 1.0)
    if isinstance(button, (QToolButton, QPushButton)):
        hover = SOFT_HOVER if name == "qsPanelTab" or _local_hover_rule(button) else 1.0
        press = 0.75 if name == "qsPanelTab" else 1.0
        return _Look("rect", radius, hover, press)
    if button.text():
        return _Look("pill", radius, SOFT_HOVER, 0.75)
    return _Look("square", radius, SOFT_HOVER, 1.0)


def overlay_of(widget: QWidget) -> FeedbackOverlay | None:
    ov = getattr(widget, _ATTR, None)
    if isinstance(ov, FeedbackOverlay):
        return ov if shiboken6.isValid(ov) else None
    if ov is False:
        return None
    child = widget.findChild(QWidget, OVERLAY_NAME, Qt.FindChildOption.FindDirectChildrenOnly)
    return child if isinstance(child, FeedbackOverlay) else None


def _holds(widget: QWidget) -> bool:
    flag = widget.property(HOLD_PROPERTY)
    return flag is not None and bool(flag) and flag != "false"



class PressFeedback(QObject):

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(FILTER_NAME)
        self._eligible: dict[type, bool] = {}
        self._hosts: dict[type, bool] = {}
        self._excluded: tuple[type, ...] | None = None
        self._pressed: FeedbackOverlay | None = None
        self._sync_queued = False

    def pressed_overlay(self) -> FeedbackOverlay | None:
        ov = self._pressed
        return ov if ov is not None and shiboken6.isValid(ov) else None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        t = event.type()
        if t not in _WATCHED:
            return False
        if isinstance(obj, QAbstractButton) or self._is_host(obj):
            self._button_event(obj, t, event)
        elif t == _T.Show:
            if self._pressed is not None and obj.isWidgetType() \
                    and obj.windowType() == Qt.WindowType.Popup:
                self._release_pressed()
        elif t in _PRESSES and isinstance(obj, QMenuBar):
            self._menu_bar_press(obj, event)
        elif t == _T.MouseButtonRelease and self._pressed is not None \
                and event.button() == _LEFT:
            self._release_pressed()
        return False

    def _is_host(self, obj: QObject) -> bool:
        cls = type(obj)
        ok = self._hosts.get(cls)
        if ok is None:
            ok = issubclass(cls, QWidget) and _class_look(cls) is not None
            self._hosts[cls] = ok
        return ok

    def _button_event(self, button: QWidget, t: QEvent.Type, event: QEvent) -> None:
        if t == _T.MouseMove:
            ov = self.pressed_overlay()
            if ov is not None and ov.parentWidget() is button and not _holds(button):
                if isinstance(button, QAbstractButton):
                    self._queue_sync()
                else:
                    self._follow(ov, button.rect().contains(event.position().toPoint()))
            return
        ov = overlay_of(button)
        if t == _T.Enter:
            if button.isEnabled():
                ov = ov or self._create(button)
                if ov is not None:
                    ov.hover_in()
        elif t == _T.Leave:
            if ov is not None:
                ov.hover_out()
        elif t in _PRESSES:
            if event.button() != _LEFT or not button.isEnabled() \
                    or not button.rect().contains(event.position().toPoint()):
                return
            ov = ov or self._create(button)
            if ov is not None:
                self._release_pressed()
                ov.press()
                self._pressed = ov
        elif t == _T.MouseButtonRelease:
            if event.button() != _LEFT:
                return
            if self._pressed is not None:
                self._release_pressed()
            elif ov is not None and ov.is_down():
                ov.release()
        elif t == _T.FocusIn:
            if event.reason() in FOCUS_REASONS and button.isEnabled():
                ov = ov or self._create(button)
                if ov is not None:
                    ov.set_focus_ring(True)
        elif t == _T.FocusOut:
            if ov is not None:
                ov.set_focus_ring(False)
        elif t == _T.EnabledChange:
            if ov is not None and not button.isEnabled():
                self._drop(ov)
        elif t == _T.Hide:
            if ov is not None:
                self._drop(ov)
        elif t == _T.Resize or t == _T.Show:
            if ov is not None:
                ov.setGeometry(button.rect())

    def _queue_sync(self) -> None:
        if not self._sync_queued:
            self._sync_queued = True
            QTimer.singleShot(0, self, self._sync_down)

    def _sync_down(self) -> None:
        self._sync_queued = False
        ov = self.pressed_overlay()
        if ov is None:
            return
        host = ov.parentWidget()
        if isinstance(host, QAbstractButton) and not _holds(host):
            self._follow(ov, host.isDown())

    @staticmethod
    def _follow(ov: FeedbackOverlay, down: bool) -> None:
        if down != ov.is_down():
            ov.press() if down else ov.release()

    def _drop(self, ov: FeedbackOverlay) -> None:
        if self._pressed is ov:
            self._pressed = None
        ov.reset()

    def _release_pressed(self) -> None:
        ov, self._pressed = self._pressed, None
        if ov is not None and shiboken6.isValid(ov):
            ov.release()

    def _wants(self, button: QWidget) -> bool:
        cls = type(button)
        ok = self._eligible.get(cls)
        if ok is None:
            if self._excluded is None:
                self._excluded = _excluded_types()
            ok = not issubclass(cls, self._excluded)
            self._eligible[cls] = ok
        if not ok:
            return False
        flag = button.property(OPT_OUT_PROPERTY)
        return flag is None or bool(flag) and flag != "false"

    def _create(self, button: QWidget) -> FeedbackOverlay | None:
        if not self._wants(button):
            try:
                setattr(button, _ATTR, False)
            except AttributeError:
                pass
            return None
        ov = FeedbackOverlay(button, _look_for(button))
        try:
            setattr(button, _ATTR, ov)
        except AttributeError:
            pass
        return ov

    def _menu_bar_press(self, bar: QMenuBar, event: QEvent) -> None:
        if event.button() != _LEFT:
            return
        act = bar.actionAt(event.position().toPoint())
        if act is None or not act.isEnabled():
            return
        ov = overlay_of(bar)
        if ov is None:
            ov = FeedbackOverlay(bar, _Look("rect", float(theme.CONTROL_RADIUS), 0.0, 0.85))
            setattr(bar, _ATTR, ov)
        r = bar.actionGeometry(act)
        ov.setGeometry(r.x(), 0, r.width(), bar.height())
        self._release_pressed()
        ov.press()
        self._pressed = ov



def installed(app: QApplication | None = None) -> PressFeedback | None:
    app = app or QApplication.instance()
    if app is None:
        return None
    found = app.findChild(QObject, FILTER_NAME, Qt.FindChildOption.FindDirectChildrenOnly)
    return found if isinstance(found, PressFeedback) else None


def install(app: QApplication) -> PressFeedback:
    feedback = installed(app)
    if feedback is None:
        feedback = PressFeedback(app)
        app.installEventFilter(feedback)
    return feedback
