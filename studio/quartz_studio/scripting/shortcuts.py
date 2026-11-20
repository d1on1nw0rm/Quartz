from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QKeyCombination, QObject, Qt, Signal
from PySide6.QtGui import QKeySequence

from . import api, paths
from .library import ScriptLibrary

__all__ = ["ShortcutBinder", "get_binder", "key_combination"]

MODIFIER_KEYS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr,
    Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock, Qt.Key.Key_unknown,
}
MODIFIER_MASK = (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
                 | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)


def key_combination(keys: str) -> int | None:
    seq = QKeySequence(keys)
    if seq.isEmpty() or seq.count() != 1:
        return None
    return int(seq[0].toCombined())


def _event_combination(event) -> int | None:
    key = event.key()
    try:
        key_enum = Qt.Key(key)
    except ValueError:
        return None
    if key_enum in MODIFIER_KEYS:
        return None
    mods = Qt.KeyboardModifier(event.modifiers()) & MODIFIER_MASK
    return int(QKeyCombination(mods, key_enum).toCombined())


class ShortcutBinder(QObject):

    triggered = Signal(str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._extra: dict[str, ScriptLibrary] = {}
        self.table: dict[int, tuple[ScriptLibrary, str]] = {}
        self.shortcuts: dict[str, str] = {}
        self._stamp = None
        self._installed = False
        self.runs = 0

    def install(self) -> bool:
        app = QCoreApplication.instance()
        if app is None:
            return False
        if not self._installed:
            app.installEventFilter(self)
            self._installed = True
        return True

    def uninstall(self) -> None:
        app = QCoreApplication.instance()
        if self._installed and app is not None:
            app.removeEventFilter(self)
        self._installed = False

    @property
    def installed(self) -> bool:
        return self._installed

    def attach(self, library: ScriptLibrary) -> None:
        if library is None or library._folder is None:
            return
        self._extra[str(Path(library.folder).resolve())] = library
        self.rebuild()

    def libraries(self) -> list[ScriptLibrary]:
        default = ScriptLibrary()
        out = [default]
        seen = {str(Path(default.folder).resolve())}
        for key, lib in list(self._extra.items()):
            if key not in seen:
                seen.add(key)
                out.append(lib)
        return out

    def _settings_stamp(self):
        path = paths.settings_path()
        try:
            st = os.stat(path)
        except OSError:
            return (str(path), paths.settings_version(), None)
        return (str(path), paths.settings_version(), st.st_mtime_ns, st.st_size)

    def rebuild(self) -> dict[str, str]:
        self.table = {}
        self.shortcuts = {}
        for lib in self.libraries():
            for name, keys in sorted(lib.shortcuts().items()):
                combo = key_combination(keys)
                if combo is None or combo in self.table:
                    continue
                self.table[combo] = (lib, name)
                self.shortcuts.setdefault(name, keys)
        self._stamp = self._settings_stamp()
        return dict(self.shortcuts)

    def sync(self) -> None:
        if self._stamp != self._settings_stamp():
            self.rebuild()

    def lookup(self, keys: str) -> tuple[ScriptLibrary, str] | None:
        self.sync()
        combo = key_combination(keys)
        return None if combo is None else self.table.get(combo)

    def _match(self, event) -> tuple[ScriptLibrary, str] | None:
        combo = _event_combination(event)
        if combo is None:
            return None
        self.sync()
        return self.table.get(combo)

    def trigger(self, name: str, library: ScriptLibrary | None = None):
        lib = library or ScriptLibrary()
        result = lib.run(name, api.document())
        self.runs += 1
        api.message(result.summary())
        self.triggered.emit(name, result)
        return result

    def activate(self, keys: str):
        hit = self.lookup(keys)
        if hit is None:
            return None
        lib, name = hit
        return self.trigger(name, lib)

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.ShortcutOverride:
            if self._match(event) is not None:
                event.accept()
                return True
            return False
        if kind == QEvent.Type.KeyPress:
            hit = self._match(event)
            if hit is None:
                return False
            if not event.isAutoRepeat():
                lib, name = hit
                self.trigger(name, lib)
            event.accept()
            return True
        return False


_BINDER: list[ShortcutBinder] = []


def get_binder(install: bool = True) -> ShortcutBinder:
    if not _BINDER:
        _BINDER.append(ShortcutBinder())
    binder = _BINDER[0]
    if install:
        binder.install()
    binder.sync()
    return binder
