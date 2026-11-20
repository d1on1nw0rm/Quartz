from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer

from .icon_svgs import ICON_SVGS

__all__ = ["apply", "applied", "ICON_SVGS"]

_RENDERERS: dict[str, QSvgRenderer] = {}
_APPLIED: list[str] = []


def _renderer(name: str) -> QSvgRenderer:
    r = _RENDERERS.get(name)
    if r is None:
        r = QSvgRenderer(QByteArray(ICON_SVGS[name].encode("utf-8")))
        _RENDERERS[name] = r
    return r


def _painter(name: str):
    def paint(p: QPainter, rect: QRectF, _color) -> None:
        _renderer(name).render(p, QRectF(rect))
    return paint


def apply() -> list[str]:
    from .. import icons

    if _APPLIED:
        return list(_APPLIED)
    registry = getattr(icons, "_REGISTRY", None)
    if registry is None:
        return []
    for name in ICON_SVGS:
        registry[name] = _painter(name)
        _APPLIED.append(name)
    cache = getattr(icons, "_CACHE", None)
    if cache is not None:
        cache.clear()
    return list(_APPLIED)


def applied() -> list[str]:
    return list(_APPLIED)
