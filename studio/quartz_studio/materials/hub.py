from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..ext import store

__all__ = ["MaterialsHub", "hub", "install_listener", "emit", "watch_scene", "WATCHED_KEYS"]

WATCHED_KEYS = ("materials", "active_material", "tags")


class MaterialsHub(QObject):

    changed = Signal(object, str)


_HUB: MaterialsHub | None = None
_HOOKED = False


def hub() -> MaterialsHub:
    global _HUB
    if _HUB is None:
        _HUB = MaterialsHub()
    return _HUB


def _listener(owner, key: str) -> None:
    if key in WATCHED_KEYS and _HUB is not None:
        _HUB.changed.emit(owner, key)


def install_listener() -> bool:
    global _HOOKED
    listeners = getattr(store, "_LISTENERS", None)
    if isinstance(listeners, list):
        if _listener not in listeners:
            listeners.append(_listener)
        _HOOKED = True
    return _HOOKED


def emit(owner, key: str) -> None:
    if not _HOOKED and _HUB is not None:
        _HUB.changed.emit(owner, key)


install_listener()


def watch_scene(owner, scene, callback, interval: int = 0):
    from PySide6.QtCore import QTimer
    signal = getattr(scene, "changed", None)
    if signal is None:
        return None
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.setInterval(interval)
    timer.timeout.connect(callback)
    signal.connect(timer.start)
    return timer
