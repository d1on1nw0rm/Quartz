from __future__ import annotations

import importlib
import sys
import time
import weakref

from PySide6.QtCore import QCoreApplication, QEvent, QKeyCombination, QObject, Qt, QTimer
from PySide6.QtGui import QCursor, QKeyEvent, QKeySequence, QShortcut, QWindow
from PySide6.QtWidgets import QApplication, QComboBox, QWidget

__all__ = ["install", "refresh", "KeyFilter", "lookup", "hold_keys", "held_set", "is_navigation_press",
           "modifier_held", "modal_key", "binding_text", "tooltip", "bindings", "FILE_ORDER"]

PORTABLE = QKeySequence.SequenceFormat.PortableText
FILE_ORDER = ("file.new", "file.open", "file.merge", "file.save", "file.save_as", "file.save_incremental")
NAVIGATION_OPS = frozenset(("orbit", "pan", "dolly"))
MOD_FLAGS = {
    "shift": Qt.KeyboardModifier.ShiftModifier,
    "ctrl": Qt.KeyboardModifier.ControlModifier,
    "alt": Qt.KeyboardModifier.AltModifier,
    "meta": Qt.KeyboardModifier.MetaModifier,
}
BUTTON_NAMES = {
    Qt.MouseButton.LeftButton: "left",
    Qt.MouseButton.MiddleButton: "middle",
    Qt.MouseButton.RightButton: "right",
}
CHORD_BLOCKERS = (Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier,
                  Qt.KeyboardModifier.MetaModifier)
HOLD_BLOCKERS = (Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier)
MODIFIER_KEYS = frozenset(int(k.value) for k in (
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr,
    Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock, Qt.Key.Key_ScrollLock, Qt.Key.Key_Super_L,
    Qt.Key.Key_Super_R, Qt.Key.Key_Hyper_L, Qt.Key.Key_Hyper_R))

_HELD: set[int] = set()
_TRACKER: list = [None]
_INDEX: list = [None]
_HOLD: list = [None]
_WINDOWS: list = []
_CONNECTED: list = [False]


def _controls():
    from quartz_studio import controls

    return controls


def _actions_module():
    return importlib.import_module("quartz_studio.controls.actions")


def _valid(obj) -> bool:
    if obj is None:
        return False
    try:
        from shiboken6 import isValid
    except ImportError:
        return True
    return isValid(obj)


def _int(value) -> int:
    return int(getattr(value, "value", value))


def _has(mods, flag) -> bool:
    return bool(_int(mods) & _int(flag))


def _portable(text: str) -> str:
    seq = QKeySequence(text)
    if seq.count() != 1:
        return ""
    return seq.toString(PORTABLE)


def _key_code(name: str) -> int | None:
    seq = QKeySequence(name)
    if seq.count() != 1:
        return None
    return _int(seq[0].key())


def _event_text(ev: QKeyEvent) -> str:
    return QKeySequence(ev.keyCombination()).toString(PORTABLE)


def _plain_text(ev: QKeyEvent) -> str:
    mods = Qt.KeyboardModifier(_int(ev.modifiers()) & ~_int(Qt.KeyboardModifier.KeypadModifier))
    return QKeySequence(QKeyCombination(mods, Qt.Key(_int(ev.key())))).toString(PORTABLE)


def _chord_part(ev: QKeyEvent) -> str:
    text = ev.text()
    if text and text.isprintable() and not text.isspace():
        return text.upper()
    return QKeySequence(_int(ev.key())).toString(PORTABLE).upper()


def _is_chord(binding: str) -> bool:
    return "~" in binding and len(binding) > 2


def _chord_menu_delay() -> int:
    try:
        from quartz_studio.controls import chord_menu
    except ImportError:
        return 200
    return chord_menu.SHOW_DELAY_MS


def _is_text_input(w) -> bool:
    try:
        from quartz_studio.widgets.viewport import _is_text_input as check
    except ImportError:
        check = None
    if check is not None:
        return check(w)
    if w is None:
        return False
    if w.inherits("QLineEdit") or w.inherits("QAbstractSpinBox") or w.inherits("QTextEdit") \
            or w.inherits("QPlainTextEdit"):
        return True
    return isinstance(w, QComboBox) and w.isEditable()


class _Index:

    def __init__(self, resolved, registry: dict) -> None:
        self.resolved = resolved
        self.registry = registry
        self.keys: dict[str, dict[str, str]] = {}
        self.chords: dict[str, dict[str, str]] = {}
        self.prefixes: dict[str, set[str]] = {}
        self.size = len(registry)
        for aid in registry:
            for binding, scope in resolved.keys.get(aid, ()):
                if _is_chord(binding):
                    first, second = binding.split("~", 1)
                    chord = f"{first.strip().upper()}~{second.strip().upper()}"
                    self.chords.setdefault(scope, {}).setdefault(chord, aid)
                    self.prefixes.setdefault(scope, set()).add(first.strip().upper())
                    continue
                text = _portable(binding)
                if text:
                    self.keys.setdefault(scope, {}).setdefault(text, aid)


def _index() -> _Index:
    c = _controls()
    resolved = c.active()
    registry = c.actions()
    cached = _INDEX[0]
    if cached is not None and cached.resolved is resolved and cached.registry is registry \
            and len(registry) == cached.size:
        return cached
    index = _Index(resolved, registry)
    _INDEX[0] = index
    return index


def _hold_codes() -> frozenset[int]:
    resolved = _controls().active()
    cached = _HOLD[0]
    if cached is not None and cached[0] is resolved:
        return cached[1]
    codes = set()
    for gesture in resolved.mouse:
        key = gesture.get("key")
        if key:
            code = _key_code(str(key))
            if code is not None:
                codes.add(code)
    result = frozenset(codes)
    _HOLD[0] = (resolved, result)
    return result


def bindings(action_id: str) -> list[tuple[str, str]]:
    return [(str(b), str(s)) for b, s in _controls().active().keys.get(action_id, ())]


def binding_text(action_id: str) -> str:
    found = bindings(action_id)
    return found[0][0] if found else ""


def tooltip(label: str, action_id: str) -> str:
    text = binding_text(action_id)
    return f"{label} ({text})" if text else label


def lookup(event: QKeyEvent, scope: str) -> str | None:
    table = _index().keys.get(scope)
    if not table:
        return None
    hit = table.get(_event_text(event))
    if hit is None and _has(event.modifiers(), Qt.KeyboardModifier.KeypadModifier):
        hit = table.get(_plain_text(event))
    return hit


def hold_keys() -> set[int]:
    return set(_hold_codes())


class _HeldTracker(QObject):

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        kind = ev.type()
        if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) and isinstance(ev, QKeyEvent):
            if ev.isAutoRepeat():
                return False
            key = _int(ev.key())
            if key not in _HELD and key not in _hold_codes():
                return False
            if kind == QEvent.Type.KeyRelease:
                _HELD.discard(key)
            elif not any(_has(ev.modifiers(), m) for m in HOLD_BLOCKERS):
                _HELD.add(key)
        elif kind == QEvent.Type.ApplicationDeactivate:
            _HELD.clear()
        return False


def held_set() -> set[int]:
    tracker = _TRACKER[0]
    if tracker is None or not _valid(tracker):
        _TRACKER[0] = None
        app = QCoreApplication.instance()
        if app is not None:
            tracker = _HeldTracker(app)
            app.installEventFilter(tracker)
            _TRACKER[0] = tracker
    return _HELD


def _mods(mods) -> set[str]:
    return {name for name in ("shift", "ctrl", "alt") if _has(mods, MOD_FLAGS[name])}


def is_navigation_press(event, held) -> bool:
    button = BUTTON_NAMES.get(event.button())
    if button is None:
        return False
    c = _controls()
    mods = _mods(event.modifiers())
    keys = set(held or ())
    gesture = None
    if event.type() == QEvent.Type.MouseButtonDblClick:
        gesture = c.match_press(button, mods, keys, True)
    if gesture is None:
        gesture = c.match_press(button, mods, keys, False)
    return gesture is not None and gesture.get("op") in NAVIGATION_OPS


def modifier_held(mods, role: str) -> bool:
    name = _controls().active().modifiers.get(role)
    flag = MOD_FLAGS.get(str(name)) if name else None
    return flag is not None and _has(mods, flag)


def modal_key(event, key: str) -> bool:
    code = _int(event.key())
    for name in _controls().active().modal.get(key, ()):
        if _key_code(str(name)) == code:
            return True
    return False


def _pointer(ev) -> int:
    try:
        from shiboken6 import getCppPointer
    except ImportError:
        return id(ev)
    try:
        return int(getCppPointer(ev)[0])
    except Exception:
        return id(ev)


def _recording() -> bool:
    editor = sys.modules.get("quartz_studio.controls.editor")
    return editor is not None and editor.is_recording()


class KeyFilter(QObject):

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.window = window
        self.fresh = False
        self._last: tuple | None = None
        self._last_event = None
        self._prefix: tuple[str, float] | None = None
        self._menu = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_menu)

    def clear(self) -> None:
        self._drop()
        self.fresh = False

    def _menu_open(self) -> bool:
        return self._menu is not None and _valid(self._menu) and self._menu.isVisible()

    def _drop(self) -> None:
        self._prefix = None
        self._timer.stop()
        menu = self._menu
        self._menu = None
        if menu is not None and _valid(menu):
            menu.hide()
            menu.deleteLater()

    def _pick(self, aid: str) -> None:
        self._drop()
        _controls().run(aid)

    def _inside_menu(self, obj) -> bool:
        menu = self._menu
        if isinstance(obj, QWindow):
            handle = menu.windowHandle()
            return handle is not None and _pointer(obj) == _pointer(handle)
        if isinstance(obj, QWidget):
            return obj is menu or menu.isAncestorOf(obj)
        return False

    def _show_menu(self) -> None:
        part = self._pending()
        if part is None or self._menu_open():
            return
        try:
            from quartz_studio.controls import chord_menu
        except ImportError:
            return
        if not chord_menu.enabled_pref():
            return
        focus = QApplication.focusWidget()
        if not self._in_window(focus) or _is_text_input(focus):
            return
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        menu = chord_menu.build(self.window, _index(), part, self._live_scopes(focus), self._pick)
        if menu is None:
            return
        self._menu = menu
        chord_menu.present(menu, QCursor.pos())

    def _canvas(self):
        vp = getattr(self.window, "viewport", None)
        return vp, getattr(vp, "canvas", None)

    def _tree(self):
        return getattr(getattr(self.window, "object_manager", None), "tree", None)

    def _in_window(self, focus) -> bool:
        if QApplication.activePopupWidget() is not None:
            return False
        if focus is None:
            active = QApplication.activeWindow()
            return active is None or active is self.window
        return focus is self.window or self.window.isAncestorOf(focus)

    def _owns(self, obj) -> bool:
        if isinstance(obj, QWindow):
            handle = self.window.windowHandle()
            return handle is not None and _pointer(obj) == _pointer(handle)
        if isinstance(obj, QWidget):
            return obj.window() is self.window
        return False

    def _viewport_focus(self, focus) -> bool:
        if focus is None:
            return True
        vp, canvas = self._canvas()
        return focus is vp or focus is canvas

    def _live_scopes(self, focus) -> tuple[str, ...]:
        scopes = ["global"]
        if self._viewport_focus(focus):
            scopes.append("viewport")
        tree = self._tree()
        if tree is not None and focus is tree:
            scopes.append("objects")
        return tuple(scopes)

    def _pending(self) -> str | None:
        if self._prefix is None:
            return None
        part, stamp = self._prefix
        if self._menu_open():
            return part
        limit = float(_controls().cursor("chord_ms")) / 1000.0
        if time.monotonic() - stamp > limit:
            self._drop()
            return None
        return part

    def _chord(self, index: _Index, chord: str, focus) -> str | None:
        for scope in self._live_scopes(focus):
            aid = index.chords.get(scope, {}).get(chord)
            if aid is not None:
                return aid
        return None

    def _is_prefix(self, index: _Index, part: str, focus) -> bool:
        return any(part in index.prefixes.get(scope, ()) for scope in self._live_scopes(focus))

    def _chord_ready(self, ev: QKeyEvent, focus) -> bool:
        if not self._in_window(focus) or _is_text_input(focus):
            return False
        if ev.isAutoRepeat() or _int(ev.key()) in MODIFIER_KEYS:
            return False
        return not any(_has(ev.modifiers(), m) for m in CHORD_BLOCKERS)

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        kind = ev.type()
        if self._menu is not None:
            if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
                if not self._menu_open() or not self._inside_menu(obj):
                    self._drop()
                return False
            if kind == QEvent.Type.ApplicationDeactivate:
                self._drop()
                return False
        if kind in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and _recording():
            return False
        if kind == QEvent.Type.ShortcutOverride and isinstance(ev, QKeyEvent):
            return self._override(ev)
        if kind == QEvent.Type.KeyPress and isinstance(ev, QKeyEvent):
            return self._press(obj, ev)
        return False

    def _override(self, ev: QKeyEvent) -> bool:
        self.fresh = True
        focus = QApplication.focusWidget()
        if not self._chord_ready(ev, focus):
            return False
        index = _index()
        part = _chord_part(ev)
        pending = self._pending()
        if pending is not None:
            if self._chord(index, f"{pending}~{part}", focus) is None:
                return False
        elif not self._is_prefix(index, part, focus):
            return False
        ev.accept()
        return True

    def _press(self, obj: QObject, ev: QKeyEvent) -> bool:
        fresh = self.fresh
        self.fresh = False
        stamp = (_pointer(ev), _int(ev.key()), _int(ev.modifiers()))
        if not fresh and self._last == stamp:
            return False
        focus = QApplication.focusWidget()
        if focus is not None and not isinstance(obj, QWindow) and obj is not focus \
                and obj is not focus.window():
            return False
        if focus is None and not self._owns(obj):
            return False
        self._last = stamp
        self._last_event = ev
        return self._decide(ev, focus)

    def _decide(self, ev: QKeyEvent, focus) -> bool:
        if not self._in_window(focus) or _is_text_input(focus):
            return False
        key = _int(ev.key())
        if key in MODIFIER_KEYS:
            return False
        c = _controls()
        index = _index()
        if key == _int(Qt.Key.Key_Escape) and self._menu_open():
            self._drop()
            return True
        if self._chord_ready(ev, focus):
            part = _chord_part(ev)
            pending = self._pending()
            if pending is not None:
                self._drop()
                aid = self._chord(index, f"{pending}~{part}", focus)
                if aid is not None:
                    c.run(aid)
                    return True
            elif self._is_prefix(index, part, focus):
                self._prefix = (part, time.monotonic())
                self._timer.start(_chord_menu_delay())
                return True
        elif any(_has(ev.modifiers(), m) for m in CHORD_BLOCKERS):
            self._drop()
        if not self._viewport_focus(focus):
            return False
        vp, canvas = self._canvas()
        if focus is not None and focus is canvas:
            return False
        aid = lookup(ev, "viewport")
        if aid is None:
            return False
        action = index.registry.get(aid)
        if action is None or ev.isAutoRepeat() and not action.repeat:
            return False
        return bool(c.run(aid))


def _foreign_shortcuts(window: QWidget, own: list) -> list:
    mine = {id(sc) for sc in own}
    return [sc for sc in window.findChildren(QShortcut) if id(sc) not in mine and sc.parent() is window]


def _build_shortcuts(window: QWidget) -> None:
    c = _controls()
    old = getattr(window, "_controls_shortcuts", None) or []
    for sc in old:
        if _valid(sc):
            sc.setEnabled(False)
            sc.setParent(None)
            sc.deleteLater()
    own: list[QShortcut] = []
    by_action: dict[str, list[QShortcut]] = {}
    taken: set[str] = set()
    index = _index()
    resolved = index.resolved
    for aid, action in index.registry.items():
        for binding, scope in resolved.keys.get(aid, ()):
            if scope != "global" or _is_chord(binding):
                continue
            text = _portable(binding)
            if not text or text in taken:
                continue
            taken.add(text)
            sc = QShortcut(QKeySequence(text), window)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.setAutoRepeat(bool(action.repeat))
            sc.activated.connect(lambda a=aid: c.run(a))
            own.append(sc)
            by_action.setdefault(aid, []).append(sc)
    for sc in _foreign_shortcuts(window, own):
        if sc.isEnabled() and sc.key().toString(PORTABLE) in taken:
            sc.setEnabled(False)
    window._controls_shortcuts = own
    window.key_shortcuts = by_action
    window.file_shortcuts = [sc for aid in FILE_ORDER for sc in by_action.get(aid, ())]
    bar = getattr(window, "menu_bar", None)
    if bar is not None:
        extra = getattr(_actions_module(), "_EXTRA", {})
        bar.extension_shortcuts = [sc for aid in index.registry if aid in extra
                                   for sc in by_action.get(aid, ())]


def _windows() -> list:
    alive = []
    refs = []
    for ref in _WINDOWS:
        w = ref()
        if w is not None and _valid(w):
            alive.append(w)
            refs.append(ref)
    _WINDOWS[:] = refs
    return alive


def _on_profile_changed(*_args) -> None:
    _INDEX[0] = None
    _HELD.clear()
    for window in _windows():
        flt = getattr(window, "controls_filter", None)
        if flt is not None and _valid(flt):
            flt.clear()
        _build_shortcuts(window)


def install(window) -> None:
    c = _controls()
    _actions_module().collect()
    _INDEX[0] = None
    c._set_window(window)
    if window not in _windows():
        _WINDOWS.append(weakref.ref(window))
    held_set()
    _build_shortcuts(window)
    flt = getattr(window, "controls_filter", None)
    if flt is None or not _valid(flt):
        flt = KeyFilter(window)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(flt)
        window.controls_filter = flt
    window.modeling_shortcuts = flt
    if not _CONNECTED[0]:
        c.hub().profileChanged.connect(_on_profile_changed)
        _CONNECTED[0] = True


def refresh() -> None:
    windows = _windows()
    if not windows:
        _INDEX[0] = None
        return
    _actions_module().collect()
    _INDEX[0] = None
    for window in windows:
        _build_shortcuts(window)
