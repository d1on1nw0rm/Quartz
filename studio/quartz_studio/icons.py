from __future__ import annotations

import logging
import math
import os
from typing import Callable

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QIconEngine,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from quartz_studio import theme

log = logging.getLogger("quartz_studio.icons")

Painter = Callable[[QPainter, QRectF, QColor], None]

_REGISTRY: dict[str, Painter] = {}
_DEFAULT_COLORS: dict[str, str] = {}
_TINTS: dict[str, str] = {}
_PINNED: set[str] = set()
_CACHE: dict[tuple, QIcon] = {}
_WARNED: set[str] = set()
_STATE: dict[str, str | None] = {"tint": None}

GROUP_MARK_COLOR = theme.TEXT_SECONDARY
DISABLED_OPACITY = 0.38

_W = theme.ICON_STROKE_W
_DOT_R = 2.1
_TINT_SET = {theme.TINT_MINT.lower(), theme.TINT_CITRINE.lower(),
             theme.TINT_AMETHYST.lower(), theme.TINT_ROSE.lower()}

MINT = theme.TINT_MINT
CITRINE = theme.TINT_CITRINE
AMETHYST = theme.TINT_AMETHYST
ROSE = theme.TINT_ROSE


def register(name: str, painter: Painter, default_color: str | None = None) -> None:
    if name in _PINNED:
        log.debug("icon %r is pinned to the Crystal set; registration ignored", name)
        return
    _REGISTRY[name] = painter
    if default_color:
        _DEFAULT_COLORS[name] = default_color
    _CACHE.clear()


def names() -> list[str]:
    return sorted(_REGISTRY)


def has(name: str) -> bool:
    return name in _REGISTRY


def default_color(name: str) -> str:
    return _DEFAULT_COLORS.get(name, theme.ICON_STROKE)


def family_tint(name: str) -> str | None:
    return _TINTS.get(name)


def icon(name: str, size: int = 24, color: str | None = None,
         group_mark: bool = False, disabled: bool = False) -> QIcon:
    key = (name, size, color, group_mark, disabled)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    if name not in _REGISTRY and name not in _WARNED:
        _WARNED.add(name)
        log.debug("icon %r not registered; using fallback", name)
    engine = _VectorIconEngine(name, size, color, group_mark, disabled)
    result = QIcon(engine)
    _CACHE[key] = result
    return result


def pixmap(name: str, size: int = 24, color: str | None = None,
           group_mark: bool = False, disabled: bool = False,
           device_pixel_ratio: float = 1.0) -> QPixmap:
    px = round(size * device_pixel_ratio)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    render(p, QRectF(0, 0, px, px), name, color, group_mark, disabled)
    p.end()
    pm.setDevicePixelRatio(device_pixel_ratio)
    return pm


def _resolve(name: str, color: str | None) -> tuple[QColor, QColor | None]:
    stroke = QColor(default_color(name))
    own = _TINTS.get(name)
    tint = QColor(own) if own else None
    if color:
        given = QColor(color)
        key = given.name().lower()
        if own and key in _TINT_SET and not (key == theme.TINT_MINT.lower() and own.lower() != key):
            tint = given
        else:
            stroke = given
    return stroke, tint


def render(p: QPainter, rect: QRectF, name: str, color: str | None = None,
           group_mark: bool = False, disabled: bool = False) -> None:
    stroke, tint = _resolve(name, color)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    if disabled:
        p.setOpacity(p.opacity() * DISABLED_OPACITY)
        stroke = _desaturate(stroke)
        tint = _desaturate(tint) if tint is not None else None
    painter = _REGISTRY.get(name, _fallback_painter(name))
    previous = _STATE["tint"]
    _STATE["tint"] = (tint or stroke).name(QColor.NameFormat.HexArgb)
    try:
        painter(p, QRectF(rect), stroke)
    except Exception:
        log.exception("icon painter %r failed", name)
    finally:
        _STATE["tint"] = previous
    p.restore()
    if group_mark:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if disabled:
            p.setOpacity(p.opacity() * DISABLED_OPACITY)
        draw_group_mark(p, rect)
        p.restore()


def draw_group_mark(p: QPainter, rect: QRectF, color: str = GROUP_MARK_COLOR) -> None:
    r = QRectF(rect)
    t = max(3.0, round(min(r.width(), r.height()) * 0.17))
    x1, y1 = r.right(), r.bottom()
    tri = QPolygonF([QPointF(x1, y1 - t), QPointF(x1, y1), QPointF(x1 - t, y1)])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon(tri)


def write_qss_assets(directory: str) -> dict[str, str]:
    os.makedirs(directory, exist_ok=True)
    wanted = {
        "chevron_down": ("chevron_down", theme.TEXT_SECONDARY, 10),
        "chevron_down_disabled": ("chevron_down", theme.TEXT_MUTED, 10),
        "chevron_right": ("chevron_right", theme.TEXT_SECONDARY, 10),
        "check": ("check", theme.ACCENT_ON, 10),
    }
    paths: dict[str, str] = {}
    for key, (name, col, sz) in wanted.items():
        pm = pixmap(name, sz, col, device_pixel_ratio=2.0)
        path = os.path.join(directory, f"{key}.png")
        pm.save(path, "PNG")
        paths[key] = path.replace("\\", "/")
    return paths


class _VectorIconEngine(QIconEngine):

    def __init__(self, name: str, size: int, color: str | None,
                 group_mark: bool, disabled: bool) -> None:
        super().__init__()
        self._name = name
        self._size = size
        self._color = color
        self._group = group_mark
        self._disabled = disabled

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        disabled = self._disabled or mode == QIcon.Mode.Disabled
        render(painter, QRectF(rect), self._name, self._color, self._group, disabled)

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pm

    def scaledPixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State, scale: float) -> QPixmap:
        real = QSize(round(size.width() * scale), round(size.height() * scale))
        pm = self.pixmap(real, mode, state)
        pm.setDevicePixelRatio(scale)
        return pm

    def actualSize(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QSize:
        return size

    def clone(self) -> QIconEngine:
        return _VectorIconEngine(self._name, self._size, self._color, self._group, self._disabled)

    def key(self) -> str:
        return "quartz_vector"


def _desaturate(c: QColor) -> QColor:
    h, s, v, a = c.getHsvF()
    return QColor.fromHsvF(max(h, 0.0), s * 0.25, v * 0.85, a)


def _unit(fn: Callable[[QPainter, QColor], None]) -> Painter:
    def wrapped(p: QPainter, r: QRectF, c: QColor) -> None:
        p.save()
        side = min(r.width(), r.height())
        p.translate(r.x() + (r.width() - side) / 2, r.y() + (r.height() - side) / 2)
        p.scale(side / 24.0, side / 24.0)
        fn(p, c)
        p.restore()
    return wrapped


def _builtin(name: str, tint: str | None = None, *aliases: str):
    def deco(fn: Callable[[QPainter, QColor], None]):
        painter = _unit(fn)
        for n in (name, *aliases):
            _REGISTRY[n] = painter
            if tint:
                _TINTS[n] = tint
            if n.startswith(("view_", "pal_")):
                _PINNED.add(n)
        return fn
    return deco


def _T() -> QColor:
    return QColor(_STATE["tint"] or theme.ICON_STROKE)


def _pen(p: QPainter, c: QColor | str, w: float = _W, style=Qt.PenStyle.SolidLine,
         cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin) -> None:
    p.setPen(QPen(QColor(c), w, style, cap, join))
    p.setBrush(Qt.BrushStyle.NoBrush)


def _fill(p: QPainter, c: QColor | str) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))


def _both(p: QPainter, line: QColor | str, fill: QColor | str, w: float = _W) -> None:
    p.setPen(QPen(QColor(line), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QColor(fill))


def _alpha(c: QColor | str, a: float) -> QColor:
    q = QColor(c)
    q.setAlphaF(a * q.alphaF())
    return q


def _poly(*pts: tuple[float, float]) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _line(p: QPainter, x0: float, y0: float, x1: float, y1: float) -> None:
    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))


def _lines(p: QPainter, pts: tuple[tuple[float, float], ...]) -> None:
    p.drawPolyline(_poly(*pts))


def _dot(p: QPainter, x: float, y: float, c: QColor | str, r: float = 1.8) -> None:
    _fill(p, c)
    p.drawEllipse(QPointF(x, y), r, r)


def _cubic(*segs: tuple[float, ...]) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(segs[0][0], segs[0][1])
    for seg in segs[1:]:
        if len(seg) == 2:
            path.lineTo(*seg)
        else:
            path.cubicTo(*seg)
    return path


def _dashed(p: QPainter, c: QColor | str, w: float = _W, pattern: tuple[float, float] = (1.6, 1.8)) -> None:
    pen = QPen(QColor(c), w, Qt.PenStyle.CustomDashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    pen.setDashPattern([pattern[0], pattern[1]])
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)


def _chevron(p: QPainter, c: QColor | str, tip: tuple[float, float], angle_deg: float,
             size: float = 3.6, w: float = _W) -> None:
    a = math.radians(angle_deg)
    tx, ty = tip
    spread = math.radians(38)
    pts = []
    for sign in (1, -1):
        b = a + math.pi + sign * spread
        pts.append((tx + size * math.cos(b), ty + size * math.sin(b)))
    _pen(p, c, w)
    p.drawPolyline(_poly(pts[0], (tx, ty), pts[1]))


def _arrow(p: QPainter, c: QColor | str, x0: float, y0: float, x1: float, y1: float,
           w: float = _W, head: float = 3.6) -> None:
    _pen(p, c, w)
    _line(p, x0, y0, x1, y1)
    _chevron(p, c, (x1, y1), math.degrees(math.atan2(y1 - y0, x1 - x0)), head, w)


def _hexagon(cx: float, cy: float, s: float) -> dict[str, QPointF]:
    k = 0.866 * s
    return {
        "T": QPointF(cx, cy - s), "UR": QPointF(cx + k, cy - s / 2), "LR": QPointF(cx + k, cy + s / 2),
        "B": QPointF(cx, cy + s), "LL": QPointF(cx - k, cy + s / 2), "UL": QPointF(cx - k, cy - s / 2),
        "C": QPointF(cx, cy),
    }


def _hex_ring(h: dict[str, QPointF]) -> QPolygonF:
    return QPolygonF([h["T"], h["UR"], h["LR"], h["B"], h["LL"], h["UL"]])


def _cube(p: QPainter, c: QColor, tint: QColor | None, cx: float = 12, cy: float = 12,
          s: float = 8.5, w: float = _W, face: str = "top") -> dict[str, QPointF]:
    h = _hexagon(cx, cy, s)
    faces = {
        "top": [h["T"], h["UR"], h["C"], h["UL"]],
        "left": [h["UL"], h["C"], h["B"], h["LL"]],
        "right": [h["C"], h["UR"], h["LR"], h["B"]],
    }
    if tint is not None and face in faces:
        _fill(p, tint)
        p.drawPolygon(QPolygonF(faces[face]))
    _pen(p, c, w)
    p.drawPolygon(_hex_ring(h))
    p.drawLine(h["C"], h["UL"])
    p.drawLine(h["C"], h["UR"])
    p.drawLine(h["C"], h["B"])
    return h


def _circle(p: QPainter, cx: float, cy: float, r: float) -> None:
    p.drawEllipse(QPointF(cx, cy), r, r)


def _ellipse_path(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    return path


def _rect_path(x: float, y: float, w: float, h: float) -> QPainterPath:
    path = QPainterPath()
    path.addRect(QRectF(x, y, w, h))
    return path


def _rrect_path(x: float, y: float, w: float, h: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


def _ngon(cx: float, cy: float, r: float, n: int, rot: float = -90.0) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(math.radians(rot + 360.0 * k / n)),
             cy + r * math.sin(math.radians(rot + 360.0 * k / n))) for k in range(n)]


def _star_pts(cx: float, cy: float, ro: float, ri: float, n: int = 5) -> list[tuple[float, float]]:
    pts = []
    for i in range(2 * n):
        r = ro if i % 2 == 0 else ri
        a = -math.pi / 2 + i * math.pi / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _gear_path(cx: float, cy: float, r_out: float, r_in: float, r_hole: float,
               teeth: int = 8) -> QPainterPath:
    path = QPainterPath()
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a0 = i * step
        for frac, rad in ((0.0, r_in), (0.14, r_out), (0.36, r_out), (0.5, r_in)):
            a = a0 + frac * step
            pts.append(QPointF(cx + rad * math.cos(a), cy + rad * math.sin(a)))
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    path.addEllipse(QPointF(cx, cy), r_hole, r_hole)
    path.setFillRule(Qt.FillRule.OddEvenFill)
    return path


def _text(p: QPainter, c: QColor, text: str, x: float, baseline: float, px: float,
          bold: bool = False) -> None:
    f = QFont(theme.FONT_FAMILY)
    f.setPixelSize(max(1, round(px)))
    f.setBold(bold)
    path = QPainterPath()
    path.addText(QPointF(0, 0), f, text)
    br = path.boundingRect()
    path.translate(x - br.center().x(), baseline)
    _fill(p, c)
    p.drawPath(path)


def _cursor_pts(x: float, y: float, s: float = 1.0) -> QPolygonF:
    pts = [(0, 0), (0, 12), (3.2, 9.0), (5.4, 13.6), (7.6, 12.6), (5.5, 8.2), (9.5, 8.2)]
    return _poly(*[(x + px * s, y + py * s) for px, py in pts])


def _cursor(p: QPainter, c: QColor, x: float, y: float, s: float = 1.0, w: float = _W) -> None:
    _pen(p, c, w)
    p.drawPolygon(_cursor_pts(x, y, s))


def _local(p: QPainter, cx: float, cy: float, angle: float, fn: Callable[[], None]) -> None:
    p.save()
    p.translate(cx, cy)
    p.rotate(angle)
    fn()
    p.restore()


def _fallback_painter(name: str) -> Painter:
    def fn(p: QPainter, c: QColor) -> None:
        _pen(p, c)
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
        letter = (name.strip("_")[:1] or "?").upper()
        _text(p, c, letter, 12, 16.5, 11, bold=True)
    return _unit(fn)


def _clip_fill(p: QPainter, shape: QPainterPath, clip: QPainterPath, c: QColor) -> None:
    _fill(p, c)
    p.drawPath(shape.intersected(clip))


def _arc_pts(cx: float, cy: float, rx: float, ry: float, a0: float, span: float,
             steps: int = 40) -> list[tuple[float, float]]:
    pts = []
    for i in range(steps + 1):
        a = math.radians(a0 + span * i / steps)
        pts.append((cx + rx * math.cos(a), cy - ry * math.sin(a)))
    return pts


def _arc_arrow(p: QPainter, c: QColor, head: QColor, cx: float, cy: float, rx: float, ry: float,
               a0: float, span: float, w: float = _W, size: float = 4.0) -> None:
    pts = _arc_pts(cx, cy, rx, ry, a0, span)
    _pen(p, c, w)
    p.drawPolyline(_poly(*pts))
    (x0, y0), (x1, y1) = pts[-3], pts[-1]
    _chevron(p, head, (x1, y1), math.degrees(math.atan2(y1 - y0, x1 - x0)), size, w)


@_builtin("undo", MINT, "tr_undo")
def _undo(p, c):
    _pen(p, c)
    p.drawPath(_cubic((4.8, 8.5), (13.0, 8.5), (17.4, 8.5, 19.5, 11.2, 19.5, 14.0),
                      (19.5, 16.9, 17.2, 19.5, 13.0, 19.5), (8.0, 19.5)))
    _chevron(p, _T(), (4.5, 8.5), 180, 4.4)


@_builtin("redo", MINT, "tr_redo")
def _redo(p, c):
    p.translate(24, 0)
    p.scale(-1, 1)
    _undo(p, c)


@_builtin("home", None, "tr_home")
def _home(p, c):
    _pen(p, c)
    p.drawPolyline(_poly((3.5, 11.5), (12, 4), (20.5, 11.5)))
    p.drawPolyline(_poly((6, 9.5), (6, 20), (18, 20), (18, 9.5)))
    p.drawPolyline(_poly((10, 20), (10, 14.5), (14, 14.5), (14, 20)))


@_builtin("home_small")
def _home_small(p, c):
    _pen(p, c)
    shell = QPainterPath()
    shell.moveTo(5.0, 19.5)
    shell.lineTo(5.0, 11.0)
    shell.arcTo(QRectF(5.0, 4.0, 14.0, 14.0), 180, -180)
    shell.lineTo(19.0, 19.5)
    shell.closeSubpath()
    p.drawPath(shell)


@_builtin("close", None, "tr_close")
def _close(p, c):
    _pen(p, c)
    _line(p, 7, 7, 17, 17)
    _line(p, 17, 7, 7, 17)


@_builtin("plus", None, "tr_plus")
def _plus(p, c):
    _pen(p, c)
    _line(p, 12, 5, 12, 19)
    _line(p, 5, 12, 19, 12)


@_builtin("kebab", None, "tr_kebab")
def _kebab(p, c):
    for y in (6, 12, 18):
        _dot(p, 12, y, c, 1.7)


@_builtin("hamburger")
def _hamburger(p, c):
    _pen(p, c)
    for y in (6.5, 12, 17.5):
        _line(p, 4.5, y, 19.5, y)


@_builtin("search")
def _search(p, c):
    _pen(p, c)
    _circle(p, 10.5, 10.5, 5.8)
    _line(p, 14.8, 14.8, 20, 20)


@_builtin("filter")
def _filter(p, c):
    _pen(p, c)
    _line(p, 4, 7, 20, 7)
    _line(p, 7.5, 12, 16.5, 12)
    _line(p, 10.5, 17, 13.5, 17)


@_builtin("popout")
def _popout(p, c):
    _pen(p, c)
    p.drawPolyline(_poly((11, 5), (5, 5), (5, 19), (19, 19), (19, 13)))
    _arrow(p, c, 10.5, 13.5, 19.5, 4.5, _W, 4.2)


@_builtin("arrow_left")
def _arrow_left(p, c):
    _arrow(p, c, 19.5, 12, 4.5, 12, _W, 5.2)


@_builtin("arrow_right")
def _arrow_right(p, c):
    _arrow(p, c, 4.5, 12, 19.5, 12, _W, 5.2)


@_builtin("arrow_up")
def _arrow_up(p, c):
    _arrow(p, c, 12, 19.5, 12, 4.5, _W, 5.2)


@_builtin("arrow_down")
def _arrow_down(p, c):
    _arrow(p, c, 12, 4.5, 12, 19.5, _W, 5.2)


@_builtin("chevron_down")
def _chevron_down(p, c):
    _pen(p, c, 2.2)
    p.drawPolyline(_poly((6, 9), (12, 15), (18, 9)))


@_builtin("chevron_right")
def _chevron_right(p, c):
    _pen(p, c, 2.2)
    p.drawPolyline(_poly((9, 6), (15, 12), (9, 18)))


@_builtin("check")
def _check(p, c):
    _pen(p, c, 2.6)
    p.drawPolyline(_poly((5, 12.5), (10, 17.5), (19, 6.5)))


@_builtin("triangle_down")
def _triangle_down(p, c):
    _fill(p, c)
    p.drawPolygon(_poly((7, 9), (17, 9), (12, 15)))


@_builtin("dot")
def _dot_icon(p, c):
    _dot(p, 12, 12, c, 3)


@_builtin("lock")
def _lock(p, c):
    _pen(p, c)
    shackle = QPainterPath()
    shackle.moveTo(7.8, 11.0)
    shackle.lineTo(7.8, 8.5)
    shackle.arcTo(QRectF(7.8, 3.5, 8.4, 9.0), 180, -180)
    shackle.lineTo(16.2, 11.0)
    p.drawPath(shackle)
    p.drawRoundedRect(QRectF(5.0, 11.0, 14.0, 9.5), 2.4, 2.4)
    _dot(p, 12, 15.8, _T(), 1.4)


@_builtin("target")
def _target(p, c):
    _pen(p, c)
    _circle(p, 12, 12, 8.4)
    _dot(p, 12, 12, _T(), 2.6)


@_builtin("toggle")
def _toggle(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(2.8, 6.8, 18.4, 10.4), 5.2, 5.2)
    _dot(p, 8, 12, c, 2.6)


@_builtin("gear")
def _gear(p, c):
    _pen(p, c)
    p.drawPath(_gear_path(12, 12, 9.0, 6.6, 3.0, 8))


@_builtin("pencil")
def _pencil(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((5, 19), (6.2, 14.6), (15.6, 5.2), (18.8, 8.4), (9.4, 17.8)))
    _line(p, 13.4, 7.4, 16.6, 10.6)


@_builtin("maximize")
def _maximize(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(4.5, 4.5, 15, 15), 2.4, 2.4)
    _line(p, 4.5, 9.5, 19.5, 9.5)


@_builtin("hand")
def _hand(p, c):
    path = QPainterPath()
    fingers = ((5.6, 8.6), (9.0, 5.0), (12.4, 4.4), (15.8, 6.6))
    w = 3.2
    path.moveTo(fingers[0][0], 14.0)
    for i, (x, top) in enumerate(fingers):
        path.lineTo(x, top + w / 2)
        path.arcTo(QRectF(x, top, w, w), 180, -180)
        if i + 1 < len(fingers):
            path.lineTo(x + w, 11.0)
    x_last = fingers[-1][0] + w
    path.lineTo(x_last, 15.0)
    path.quadTo(x_last, 21.0, 13.0, 21.0)
    path.quadTo(8.6, 21.0, 6.8, 18.0)
    path.lineTo(3.2, 12.8)
    path.quadTo(4.0, 11.4, 5.6, 12.8)
    path.closeSubpath()
    _both(p, c, _alpha(c, 0.25))
    p.drawPath(path)


def _zoom_arrow(p: QPainter, c: QColor) -> None:
    _pen(p, c)
    _circle(p, 10.5, 10.5, 6.6)
    _line(p, 15.4, 15.4, 20.5, 20.5)
    _pen(p, _T(), _W)
    _line(p, 7.8, 10.5, 13.2, 10.5)
    _line(p, 10.5, 7.8, 10.5, 13.2)


_builtin("zoom_arrow", MINT, "view_zoom", "zoom")(_zoom_arrow)


@_builtin("orbit", MINT, "view_orbit")
def _orbit(p, c):
    _arc_arrow(p, c, _T(), 12, 12, 9.6, 5.4, 200, 292, _W, 4.4)
    _dot(p, 12, 12, _T(), 2.4)


@_builtin("view_pan", MINT)
def _view_pan(p, c):
    _pen(p, c)
    for dx, dy, ang in ((0, -1, 270), (1, 0, 0), (0, 1, 90), (-1, 0, 180)):
        _chevron(p, c, (12 + dx * 9.5, 12 + dy * 9.5), ang, 3.8)
        _line(p, 12 + dx * 6.2, 12 + dy * 6.2, 12 + dx * 9.5, 12 + dy * 9.5)
    _pen(p, _T())
    _circle(p, 12, 12, 2.6)


@_builtin("view_panel", MINT)
def _view_panel(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(3.5, 3.5, 17, 17), 3, 3)
    _pen(p, _T())
    _lines(p, ((8, 20.5), (8, 8), (20.5, 8)))


def _axis_letter(letter: str, axis_color: str):
    def fn(p, c):
        _text(p, c, letter, 12, 15, 14)
        _pen(p, axis_color, 1.8)
        _line(p, 6.5, 19.8, 17.5, 19.8)
    return fn


_builtin("axis_x")(_axis_letter("X", theme.AXIS_X))
_builtin("axis_y")(_axis_letter("Y", theme.AXIS_Y))
_builtin("axis_z")(_axis_letter("Z", theme.AXIS_Z))
_builtin("pal_axis_x")(_axis_letter("X", theme.AXIS_X))
_builtin("pal_axis_y")(_axis_letter("Y", theme.AXIS_Y))
_builtin("pal_axis_z")(_axis_letter("Z", theme.AXIS_Z))


@_builtin("coord_system", MINT, "pal_coord_system")
def _coord_system(p, c):
    _arrow(p, c, 7.5, 17, 7.5, 3.8, _W, 3.8)
    _arrow(p, c, 7.5, 17, 20.5, 17, _W, 3.8)
    _line(p, 7.5, 17, 3.8, 20.6)
    _dot(p, 7.5, 17, _T(), 2.2)


@_builtin("axis_enable", MINT, "pal_axis_enable")
def _axis_enable(p, c):
    _pen(p, c)
    for ex, ey in ((12, 4), (4.5, 19.5), (19.5, 19.5)):
        _line(p, 12, 13.5, ex, ey)
        _dot(p, ex, ey, c, 1.9)
    _dot(p, 12, 13.5, _T(), 2.2)


def _gem_points() -> dict[str, tuple[float, float]]:
    return {"T": (12, 1.8), "R": (20.8, 12), "B": (12, 22.2), "L": (3.2, 12), "C": (12, 12)}


def _gem_ring(g) -> QPolygonF:
    return _poly(g["T"], g["R"], g["B"], g["L"])


@_builtin("mode_points", MINT, "pal_mode_points")
def _mode_points(p, c):
    g = _gem_points()
    _pen(p, _alpha(c, 0.6), 1.4)
    p.drawPolygon(_gem_ring(g))
    for k in ("T", "R", "B", "L"):
        _dot(p, g[k][0], g[k][1], _T(), 2.4)


@_builtin("mode_edges", MINT, "pal_mode_edges")
def _mode_edges(p, c):
    g = _gem_points()
    _pen(p, c)
    p.drawPolygon(_gem_ring(g))
    _line(p, *g["T"], *g["B"])
    _line(p, *g["L"], *g["R"])
    _pen(p, _T(), 2.6)
    _line(p, *g["T"], *g["R"])


@_builtin("mode_polygons", MINT, "pal_mode_polygons")
def _mode_polygons(p, c):
    g = _gem_points()
    _fill(p, _T())
    p.drawPolygon(_poly(g["T"], g["R"], g["C"]))
    _pen(p, c)
    p.drawPolygon(_gem_ring(g))
    _line(p, *g["T"], *g["B"])
    _line(p, *g["L"], *g["R"])


@_builtin("mode_model", MINT, "pal_mode_model")
def _mode_model(p, c):
    g = _gem_points()
    _both(p, c, _alpha(_T(), 0.3))
    p.drawPolygon(_gem_ring(g))
    _pen(p, c)
    _line(p, *g["L"], *g["R"])


@_builtin("symmetry", AMETHYST, "pal_symmetry", "symmetry_generator")
def _symmetry(p, c):
    _dashed(p, c, 1.4, (1.8, 1.6))
    _line(p, 12, 2.5, 12, 21.5)
    _pen(p, c)
    p.drawPolygon(_poly((3.5, 19.5), (9.6, 19.5), (9.6, 5.5)))
    _both(p, _T(), _alpha(_T(), 0.9))
    p.drawPolygon(_poly((20.5, 19.5), (14.4, 19.5), (14.4, 5.5)))


def _clapper(p: QPainter, c: QColor, x: float, y: float, w: float, h: float, stripes: bool = True) -> None:
    _pen(p, c)
    p.drawRoundedRect(QRectF(x, y + h * 0.36, w, h * 0.64), 1.8, 1.8)
    p.drawPolygon(_poly((x, y + h * 0.2), (x + w, y), (x + w, y + h * 0.26), (x, y + h * 0.4)))
    if stripes:
        _pen(p, _T())
        for i in (1, 2):
            fx = x + w * i / 3
            _line(p, fx - 1.2, y + h * 0.37 - (fx - x) / w * h * 0.16,
                  fx + 1.4, y + h * 0.11 - (fx - x) / w * h * 0.16 + 0.2)


@_builtin("render_view", MINT, "pal_render_view", "timeline")
def _render_view(p, c):
    _clapper(p, c, 3.5, 3.5, 17, 17)
    _fill(p, _T())
    p.drawPolygon(_poly((10.2, 12.2), (14.6, 15.0), (10.2, 17.8)))


@_builtin("render_settings", MINT, "pal_render_settings")
def _render_settings(p, c):
    _clapper(p, c, 3, 3, 14, 13, False)
    _pen(p, _T(), 1.4)
    p.drawPath(_gear_path(17, 17, 4.9, 3.5, 1.5, 7))


@_builtin("render_queue", MINT)
def _render_queue(p, c):
    _clapper(p, c, 3.5, 3, 14, 12)
    _pen(p, _T())
    _line(p, 6, 18.2, 20, 18.2)
    _line(p, 6, 21, 15, 21)


@_builtin("render_region", MINT, "pal_render_region")
def _render_region(p, c):
    _pen(p, c)
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        x = 12 - sx * 8
        y = 12 - sy * 8
        _lines(p, ((x + sx * 4.5, y), (x, y), (x, y + sy * 4.5)))
    _dot(p, 12, 12, _T(), 2.2)


@_builtin("take", MINT)
def _take(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(3.5, 7.5, 12, 12), 2.2, 2.2)
    _pen(p, _T())
    p.drawRoundedRect(QRectF(8.5, 4, 12, 12), 2.2, 2.2)


@_builtin("pal_commander", MINT, "commander")
def _commander(p, c):
    _search(p, c)


@_builtin("pal_gear", MINT)
def _gear_pal(p, c):
    _gear(p, c)


@_builtin("live_selection", CITRINE, "pal_live_selection")
def _live_selection(p, c):
    _dashed(p, _T(), 1.8, (1.5, 1.9))
    p.drawRoundedRect(QRectF(3.2, 3.2, 12.6, 11.6), 2.4, 2.4)
    _cursor(p, c, 10.4, 9.2, 0.95)


@_builtin("select_rect", CITRINE)
def _select_rect(p, c):
    _dashed(p, _T(), 1.8, (1.5, 1.9))
    p.drawRect(QRectF(3.2, 3.2, 14, 12))
    _cursor(p, c, 11.2, 10.2, 0.85)


@_builtin("select_lasso", CITRINE)
def _select_lasso(p, c):
    _dashed(p, _T(), 1.8, (1.5, 1.9))
    p.drawPath(_cubic((5, 12), (2.5, 4.5, 15, 2.2, 17.6, 7.2), (19.4, 11, 14, 14, 10, 13.4)))
    _cursor(p, c, 11.2, 10.2, 0.85)


@_builtin("select_polygon", CITRINE)
def _select_polygon(p, c):
    _dashed(p, _T(), 1.8, (1.5, 1.9))
    p.drawPolygon(_poly((3.5, 8), (10, 3.2), (17.2, 7.4), (14, 14.6), (5, 14)))
    _cursor(p, c, 11.2, 10.2, 0.85)


@_builtin("select_loop", CITRINE)
def _select_loop(p, c):
    _pen(p, c)
    p.drawEllipse(QRectF(3, 7, 18, 10))
    _pen(p, _T(), 2.4)
    p.drawArc(QRectF(3, 7, 18, 10), 200 * 16, 140 * 16)


def _cross_arrows(p: QPainter, c: QColor, cx: float, cy: float, r: float, gap: float,
                  head: float, w: float = _W) -> None:
    _pen(p, c, w)
    for dx, dy, ang in ((0, -1, 270), (1, 0, 0), (0, 1, 90), (-1, 0, 180)):
        _line(p, cx + dx * gap, cy + dy * gap, cx + dx * r, cy + dy * r)
        _chevron(p, c, (cx + dx * r, cy + dy * r), ang, head, w)


@_builtin("move", CITRINE, "pal_move")
def _move(p, c):
    _cross_arrows(p, c, 12, 12, 9.2, 3.4, 3.8)
    _dot(p, 12, 12, _T(), 2.0)


@_builtin("rotate", CITRINE, "pal_rotate")
def _rotate(p, c):
    _arc_arrow(p, c, c, 12, 12, 7.8, 7.8, 70, 285, _W, 4.2)
    _dot(p, 12, 12, _T(), 2.1)


@_builtin("scale", CITRINE, "pal_scale")
def _scale(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(3.8, 3.8, 16.4, 16.4), 2.8, 2.8)
    _fill(p, _T())
    p.drawRoundedRect(QRectF(6.8, 12.2, 5.4, 5.4), 1.2, 1.2)
    _arrow(p, c, 11.2, 12.8, 17.2, 6.8, _W, 3.6)


@_builtin("placement", CITRINE, "pal_placement")
def _placement(p, c):
    _cursor(p, c, 3.2, 3.2, 0.85)
    _cross_arrows(p, c, 15.4, 15.4, 5.6, 2.2, 2.8, 1.5)
    _dot(p, 15.4, 15.4, _T(), 1.5)


@_builtin("dynamic_place", CITRINE, "pal_dynamic_place")
def _dynamic_place(p, c):
    _cross_arrows(p, c, 14.6, 14.6, 6.0, 2.2, 2.8, 1.5)
    for x, y in ((5.2, 5.2), (10.0, 4.2), (4.4, 10.2)):
        _dot(p, x, y, _T(), 1.7)


def _nib_shape(p: QPainter, c: QColor, eye: QColor | None) -> None:
    body = QPainterPath()
    body.moveTo(0, 9.5)
    body.lineTo(-4.4, 1.4)
    body.cubicTo(-4.9, -2.4, -3.9, -4.8, -3.0, -6.4)
    body.lineTo(3.0, -6.4)
    body.cubicTo(3.9, -4.8, 4.9, -2.4, 4.4, 1.4)
    body.closeSubpath()
    _pen(p, c)
    p.drawPath(body)
    p.drawRoundedRect(QRectF(-3.0, -10.2, 6.0, 3.8), 1.2, 1.2)
    _line(p, 0, 9.5, 0, 3.0)
    if eye is not None:
        _dot(p, 0, 1.2, eye, 1.7)
    else:
        _pen(p, c, 1.4)
        _circle(p, 0, 1.2, 1.4)


def _nib(p: QPainter, c: QColor, cx: float, cy: float, scale: float, eye: QColor | None) -> None:
    p.save()
    p.translate(cx, cy)
    p.rotate(45)
    p.scale(scale, scale)
    _nib_shape(p, c, eye)
    p.restore()


@_builtin("pen", CITRINE, "pal_pen")
def _pen_icon(p, c):
    _nib(p, c, 12.6, 11.4, 1.0, _T())


@_builtin("polygon_pen", CITRINE)
def _polygon_pen(p, c):
    _nib(p, c, 14.2, 9.8, 0.8, None)
    _pen(p, _T())
    p.drawPolygon(_poly(*_ngon(6.4, 17.6, 3.4, 5)))


@_builtin("spline_pen", CITRINE)
def _spline_pen(p, c):
    _nib(p, c, 14.2, 9.8, 0.8, None)
    _pen(p, _T())
    p.drawPath(_cubic((3.2, 19.6), (4.6, 14.6, 7.8, 21.2, 10, 16.4)))


@_builtin("sketch", CITRINE)
def _sketch(p, c):
    _nib(p, c, 14.2, 9.8, 0.8, None)
    _pen(p, _T())
    p.drawPath(_cubic((2.8, 19.4), (4.2, 15.4, 5.4, 21.4, 7, 18), (8.2, 15.6, 9.6, 19.6, 11, 17.4)))


@_builtin("scatter_pen", CITRINE)
def _scatter_pen(p, c):
    _nib(p, c, 14.2, 9.8, 0.8, None)
    for x, y in ((4.2, 20), (8.6, 18.4), (5.2, 15.2)):
        _dot(p, x, y, _T(), 1.5)


@_builtin("paint_brush", CITRINE, "pal_paint")
def _paint_brush(p, c):
    _pen(p, c, 2.0)
    _line(p, 19.5, 4.5, 12.6, 11.4)
    _pen(p, c)
    p.drawPolygon(_poly((11.2, 9.8), (14.2, 12.8), (11.6, 15.4), (8.6, 12.4)))
    _fill(p, _T())
    p.drawPath(_cubic((8.2, 13.8), (10, 14.8, 10.4, 16.6, 9.2, 18.2), (7.8, 20, 5.2, 20.4, 3.6, 20),
                      (5.2, 18.4, 4.6, 15.2, 8.2, 13.8)))


@_builtin("create_point", CITRINE)
def _create_point(p, c):
    _pen(p, _alpha(c, 0.6), 1.4)
    _circle(p, 12, 12, 8.4)
    _dot(p, 12, 12, _T(), 2.8)


@_builtin("joint", CITRINE)
def _joint(p, c):
    _pen(p, c)
    _line(p, 6.5, 17.5, 17.5, 6.5)
    _dot(p, 6.5, 17.5, _T(), 2.6)
    _pen(p, c)
    _circle(p, 17.5, 6.5, 2.6)


@_builtin("weight", CITRINE)
def _weight(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((6.4, 9.4), (17.6, 9.4), (20.2, 20), (3.8, 20)))
    _pen(p, _T())
    _circle(p, 12, 5.6, 2.4)


@_builtin("measure", CITRINE)
def _measure(p, c):
    def ruler():
        _pen(p, c)
        p.drawRoundedRect(QRectF(-10, -3.4, 20, 6.8), 1.6, 1.6)
        _pen(p, _T())
        for x in (-6.4, -2.1, 2.2, 6.5):
            _line(p, x, -3.4, x, 0.2)
    _local(p, 12, 12, -45, ruler)


@_builtin("null", None, "pal_null")
def _null(p, c):
    _pen(p, c)
    _arrow(p, c, 8, 16, 8, 4.5, _W, 3.4)
    _arrow(p, c, 8, 16, 19.5, 16, _W, 3.4)
    _line(p, 8, 16, 4.2, 19.8)
    _fill(p, c)
    p.drawEllipse(QPointF(8, 16), 2.1, 2.1)


_SCULPT_RING = (12, 12, 8.4)


def _brush_painter(kind: str):
    def fn(p, c):
        t = _T()
        _pen(p, c)
        _circle(p, 12, 12, 8.4)
        if kind == "draw":
            _pen(p, t, 2.2)
            p.drawArc(QRectF(6.2, 6.2, 11.6, 11.6), 20 * 16, 140 * 16)
        elif kind == "wax":
            ring = _ellipse_path(12, 12, 8.4, 8.4)
            cut = _ellipse_path(9.2, 11, 7.4, 7.4)
            _fill(p, t)
            p.drawPath(ring.subtracted(cut))
            _pen(p, c)
            _circle(p, 12, 12, 8.4)
        elif kind == "inflate":
            _pen(p, t)
            _circle(p, 12, 12, 3.8)
        elif kind == "amplify":
            _pen(p, t)
            p.drawPolyline(_poly((5.2, 13), (8, 9.2), (11, 14), (14, 9.2), (16.8, 14), (18.8, 11)))
        elif kind == "knife":
            _pen(p, t, 2.0)
            _line(p, 6.4, 17.6, 17.6, 6.4)
        elif kind == "repeat":
            for x in (8.4, 12, 15.6):
                _dot(p, x, 12, t, 1.5)
        elif kind == "grab":
            _arrow(p, t, 8.6, 15.4, 16.4, 7.6, _W, 3.8)
        elif kind == "smooth":
            _pen(p, t)
            p.drawPath(_cubic((5.4, 13), (8.4, 9, 13.6, 17, 18.6, 12)))
        elif kind == "flatten":
            _pen(p, t, 2.0)
            _line(p, 5.6, 9.4, 18.4, 9.4)
        elif kind == "pinch":
            _pen(p, t)
            p.drawPolyline(_poly((6.2, 8), (10, 12), (6.2, 16)))
            p.drawPolyline(_poly((17.8, 8), (14, 12), (17.8, 16)))
        elif kind == "scrape":
            _pen(p, t)
            for y in (8.6, 12, 15.4):
                _line(p, 7, y, 17, y)
        elif kind == "fill":
            low = _rect_path(0, 14, 24, 10)
            _clip_fill(p, _ellipse_path(12, 12, 8.4, 8.4), low, t)
            _pen(p, c)
            _circle(p, 12, 12, 8.4)
    return fn


_BRUSHES = ["draw", "wax", "inflate", "amplify", "knife", "repeat",
            "grab", "smooth", "flatten", "pinch", "scrape", "fill"]

for _i, _kind in enumerate(_BRUSHES):
    _builtin(f"brush_{_i + 1}", CITRINE, f"brush_{_kind}", f"pal_brush_{_kind}")(_brush_painter(_kind))


@_builtin("eraser", CITRINE, "sketch_eraser")
def _eraser(p, c):
    def body():
        _pen(p, c)
        p.drawRoundedRect(QRectF(-8, -4.2, 16, 8.4), 2, 2)
        _fill(p, _T())
        p.drawRoundedRect(QRectF(-8, -4.2, 6.4, 8.4), 2, 2)
    _local(p, 12, 11, -40, body)
    _pen(p, c, 1.4)
    _line(p, 9, 20.6, 20, 20.6)


@_builtin("mask", CITRINE)
def _mask(p, c):
    _both(p, c, _alpha(_T(), 0.35))
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 3.6, 3.6)
    _fill(p, _T())
    _circle(p, 12, 12, 4.4)


@_builtin("mask_invert", CITRINE)
def _mask_invert(p, c):
    shape = _rrect_path(4, 4, 16, 16, 3.6)
    shape.addRoundedRect(QRectF(8.4, 8.4, 7.2, 7.2), 1.4, 1.4)
    shape.setFillRule(Qt.FillRule.OddEvenFill)
    _fill(p, _T())
    p.drawPath(shape)
    _pen(p, c)
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 3.6, 3.6)
    p.drawRoundedRect(QRectF(8.4, 8.4, 7.2, 7.2), 1.4, 1.4)


@_builtin("mask_clear", CITRINE)
def _mask_clear(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 3.6, 3.6)
    _pen(p, _T())
    _line(p, 8.6, 8.6, 15.4, 15.4)
    _line(p, 15.4, 8.6, 8.6, 15.4)


@_builtin("mask_hide", CITRINE)
def _mask_hide(p, c):
    _pen(p, c)
    p.drawEllipse(QRectF(3, 7.5, 18, 9))
    _pen(p, _T())
    _line(p, 4.5, 20, 19.5, 4.5)


@_builtin("mask_show", CITRINE, "eye")
def _mask_show(p, c):
    _pen(p, c)
    p.drawEllipse(QRectF(3, 7.5, 18, 9))
    _dot(p, 12, 12, _T(), 2.6)


@_builtin("add_layer", CITRINE)
def _add_layer(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
    _pen(p, _T())
    _line(p, 12, 8, 12, 16)
    _line(p, 8, 12, 16, 12)


@_builtin("add_folder", CITRINE)
def _add_folder(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((3.5, 6.5), (9, 6.5), (11, 8.5), (20.5, 8.5), (20.5, 19), (3.5, 19)))
    _pen(p, _T())
    _line(p, 12, 13.8, 18, 13.8)
    _line(p, 15, 10.8, 15, 16.8)


@_builtin("folder")
def _folder(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((3.5, 6.5), (9, 6.5), (11, 8.5), (20.5, 8.5), (20.5, 19), (3.5, 19)))


@_builtin("project_mesh", CITRINE)
def _project_mesh(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(3, 7.4, 18, 11.2), 2.4, 2.4)
    _pen(p, _T())
    _circle(p, 15, 13, 3.4)
    _pen(p, c)
    _line(p, 6, 11, 9.8, 11)
    _line(p, 8, 4.6, 14, 4.6)


@_builtin("bake", CITRINE)
def _bake(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15.5), 2.4, 2.4)
    _line(p, 3.5, 9.4, 20.5, 9.4)
    for x in (7, 10.2, 13.4):
        _dot(p, x, 7, c, 1.0)
    _pen(p, _T())
    _line(p, 7.5, 14.6, 16.5, 14.6)


@_builtin("pose_morph", CITRINE)
def _pose_morph(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(3.2, 3.2, 10.4, 10.4), 2, 2)
    _pen(p, _T())
    _circle(p, 15.2, 15.2, 5.4)


@_builtin("cube", MINT, "primitive")
def _cube_icon(p, c):
    _cube(p, c, _T(), 12, 12, 9)


@_builtin("sphere", MINT, "pal_sphere")
def _sphere_icon(p, c):
    cap = _rect_path(0, 0, 24, 9.4).united(_ellipse_path(12, 9.4, 8.6, 2.6))
    _clip_fill(p, _ellipse_path(12, 12, 8.6, 8.6), cap, _T())
    _pen(p, c)
    _circle(p, 12, 12, 8.6)
    p.drawArc(QRectF(3.4, 6.8, 17.2, 5.2), 180 * 16, 180 * 16)
    p.drawArc(QRectF(4.6, 12.6, 14.8, 4.4), 180 * 16, 180 * 16)


@_builtin("plane", MINT)
def _plane(p, c):
    _both(p, c, _T())
    p.drawPolygon(_poly((12, 5.5), (21.5, 11), (12, 16.5), (2.5, 11)))
    _line(p, 12, 16.5, 12, 19.5)


@_builtin("empty_polygon", MINT)
def _empty_polygon(p, c):
    corners = ((12, 4.5), (20.5, 12), (12, 19.5), (3.5, 12))
    _pen(p, _T(), 1.8)
    p.drawPolygon(_poly(*corners))
    for x, y in corners:
        _dot(p, x, y, c, 2.3)


@_builtin("disc", MINT)
def _disc(p, c):
    ring = _ellipse_path(12, 10.5, 9, 4)
    ring.addEllipse(QPointF(12, 10.5), 3.0, 1.3)
    ring.setFillRule(Qt.FillRule.OddEvenFill)
    _fill(p, _T())
    p.drawPath(ring)
    _pen(p, c)
    p.drawEllipse(QRectF(3, 6.5, 18, 8))
    p.drawEllipse(QRectF(9, 9.2, 6, 2.6))
    _line(p, 3, 10.5, 3, 14.5)
    _line(p, 21, 10.5, 21, 14.5)
    p.drawArc(QRectF(3, 10.5, 18, 8), 180 * 16, 180 * 16)


@_builtin("torus", MINT)
def _torus(p, c):
    ring = _ellipse_path(12, 12, 9.5, 6.4)
    ring.addEllipse(QPointF(12, 12), 3.6, 1.8)
    ring.setFillRule(Qt.FillRule.OddEvenFill)
    _fill(p, _T())
    p.drawPath(ring)
    _pen(p, c)
    p.drawEllipse(QRectF(2.5, 5.6, 19, 12.8))
    p.drawEllipse(QRectF(8.4, 10.2, 7.2, 3.6))


@_builtin("cone", MINT)
def _cone(p, c):
    _fill(p, _T())
    p.drawEllipse(QRectF(4, 14, 16, 6))
    _pen(p, c)
    p.drawEllipse(QRectF(4, 14, 16, 6))
    _lines(p, ((4, 17), (12, 3), (20, 17)))


@_builtin("cylinder", MINT)
def _cylinder(p, c):
    _fill(p, _T())
    p.drawEllipse(QRectF(5, 3.5, 14, 5))
    _pen(p, c)
    p.drawEllipse(QRectF(5, 3.5, 14, 5))
    _line(p, 5, 6, 5, 18)
    _line(p, 19, 6, 19, 18)
    p.drawArc(QRectF(5, 15.5, 14, 5), 180 * 16, 180 * 16)


@_builtin("tube", MINT)
def _tube(p, c):
    ring = _ellipse_path(12, 6, 7, 2.5)
    ring.addEllipse(QPointF(12, 6), 3.8, 1.2)
    ring.setFillRule(Qt.FillRule.OddEvenFill)
    _fill(p, _T())
    p.drawPath(ring)
    _pen(p, c)
    p.drawEllipse(QRectF(5, 3.5, 14, 5))
    p.drawEllipse(QRectF(8.2, 4.8, 7.6, 2.4))
    _line(p, 5, 6, 5, 18)
    _line(p, 19, 6, 19, 18)
    p.drawArc(QRectF(5, 15.5, 14, 5), 180 * 16, 180 * 16)


@_builtin("oil_tank", MINT)
def _oil_tank(p, c):
    cap = _rect_path(0, 0, 24, 8.4).united(_ellipse_path(12, 8.4, 7, 1.8))
    _clip_fill(p, _rrect_path(5, 3, 14, 18, 5), cap, _T())
    _pen(p, c)
    p.drawRoundedRect(QRectF(5, 3, 14, 18), 5, 5)
    p.drawArc(QRectF(5, 6.6, 14, 3.6), 180 * 16, 180 * 16)
    p.drawArc(QRectF(5, 13.6, 14, 3.6), 180 * 16, 180 * 16)


@_builtin("capsule", MINT)
def _capsule(p, c):
    def body():
        cap = _rect_path(-8, 3.2, 16, 12)
        _clip_fill(p, _rrect_path(-4.4, -9.6, 8.8, 19.2, 4.4), cap, _T())
        _pen(p, c)
        p.drawRoundedRect(QRectF(-4.4, -9.6, 8.8, 19.2), 4.4, 4.4)
        _line(p, -4.4, 3.2, 4.4, 3.2)
    _local(p, 12, 12, 40, body)


@_builtin("pyramid", MINT)
def _pyramid(p, c):
    _fill(p, _T())
    p.drawPolygon(_poly((12, 3), (3.5, 16.5), (12, 21)))
    _pen(p, c)
    p.drawPolygon(_poly((12, 3), (3.5, 16.5), (12, 21), (20.5, 16.5)))
    _line(p, 12, 3, 12, 21)


@_builtin("landscape", MINT)
def _landscape(p, c):
    ridge = QPainterPath()
    ridge.addPolygon(_poly((2.5, 19.5), (8, 9.5), (11.4, 14.6), (15.6, 6), (21.5, 19.5)))
    ridge.closeSubpath()
    _clip_fill(p, ridge, _rect_path(0, 0, 24, 10.6), _T())
    _pen(p, c)
    p.drawPolygon(_poly((2.5, 19.5), (8, 9.5), (11.4, 14.6), (15.6, 6), (21.5, 19.5)))


@_builtin("bezier", MINT)
def _bezier(p, c):
    _pen(p, c)
    p.drawPath(_cubic((3.5, 14), (8, 4, 15, 16, 20.5, 7), (20.5, 14), (15, 23, 8, 11, 3.5, 20.5), (3.5, 14)))
    for x, y in ((3.5, 14), (20.5, 7), (20.5, 14), (3.5, 20.5)):
        _dot(p, x, y, _T(), 1.9)


@_builtin("text", MINT)
def _text_icon(p, c):
    t_shape = [(3.2, 8.6), (14.4, 8.6), (14.4, 12), (10.4, 12), (10.4, 20.5), (7.2, 20.5), (7.2, 12), (3.2, 12)]
    dx, dy = 4.2, -4.4
    back = [(x + dx, y + dy) for x, y in t_shape]
    _pen(p, c, 1.4)
    p.drawPolygon(_poly(*back))
    for k in (0, 1, 4, 5):
        _line(p, *t_shape[k], *back[k])
    _both(p, c, _T())
    p.drawPolygon(_poly(*t_shape))


@_builtin("figure", MINT)
def _figure(p, c):
    _dot(p, 12, 4.6, _T(), 2.6)
    _pen(p, c)
    _line(p, 7, 9.6, 17, 9.6)
    _line(p, 12, 9.6, 12, 15.6)
    _line(p, 12, 15.6, 8.6, 21)
    _line(p, 12, 15.6, 15.4, 21)
    _line(p, 7, 9.6, 5.6, 15)
    _line(p, 17, 9.6, 18.4, 15)


@_builtin("platonic", MINT)
def _platonic(p, c):
    outer = _ngon(12, 12.4, 9.4, 5)
    inner = _ngon(12, 12.8, 4.2, 5, 90)
    _fill(p, _T())
    p.drawPolygon(_poly(*inner))
    _pen(p, c)
    p.drawPolygon(_poly(*outer))
    p.drawPolygon(_poly(*inner))
    for a, b in zip(outer, inner[3:] + inner[:3]):
        _line(p, *a, *b)


@_builtin("line", ROSE, "m_line")
def _line_icon(p, c):
    pts = ((3.8, 17.6), (9, 8.2), (15, 15.8), (20.2, 6.4))
    _pen(p, _T())
    p.drawPolyline(_poly(*pts))
    for x, y in pts:
        _dot(p, x, y, c, _DOT_R)


@_builtin("spline", ROSE, "spline_generic")
def _spline(p, c):
    _pen(p, _T())
    p.drawPath(_cubic((3.5, 17), (7, 3, 12, 22, 20.5, 6)))
    _dot(p, 3.5, 17, c, _DOT_R)
    _dot(p, 20.5, 6, c, _DOT_R)


@_builtin("rectangle", ROSE)
def _rectangle(p, c):
    _pen(p, _T())
    p.drawRect(QRectF(4, 6.5, 16, 11))
    _dot(p, 4, 6.5, c, _DOT_R)
    _dot(p, 20, 17.5, c, _DOT_R)


@_builtin("circle", ROSE)
def _circle_icon(p, c):
    _pen(p, _T())
    _circle(p, 12, 12, 8.2)
    _dot(p, 12, 3.8, c, _DOT_R)
    _dot(p, 12, 20.2, c, _DOT_R)


@_builtin("four_side", ROSE)
def _four_side(p, c):
    _pen(p, _T())
    p.drawPolygon(_poly((12, 3.2), (20.8, 12), (12, 20.8), (3.2, 12)))
    _dot(p, 12, 3.2, c, _DOT_R)
    _dot(p, 12, 20.8, c, _DOT_R)


@_builtin("n_side", ROSE)
def _n_side(p, c):
    pts = _ngon(12, 12, 8.8, 6)
    _pen(p, _T())
    p.drawPolygon(_poly(*pts))
    _dot(p, *pts[0], c, _DOT_R)
    _dot(p, *pts[3], c, _DOT_R)


@_builtin("star", ROSE)
def _star(p, c):
    pts = _star_pts(12, 12.6, 9, 4)
    _pen(p, _T())
    p.drawPolygon(_poly(*pts))
    _dot(p, *pts[0], c, _DOT_R)


@_builtin("cogwheel", ROSE)
def _cogwheel(p, c):
    _pen(p, _T())
    p.drawPath(_gear_path(12, 12, 9.4, 6.9, 3.4, 8))


@_builtin("profile", ROSE)
def _profile(p, c):
    _pen(p, _T())
    p.drawPolyline(_poly((4, 20), (4, 12.5), (10.5, 12.5), (10.5, 6), (20, 6)))
    _dot(p, 4, 20, c, _DOT_R)
    _dot(p, 20, 6, c, _DOT_R)


@_builtin("arc", ROSE)
def _arc_icon(p, c):
    pts = _arc_pts(12, 16, 8.6, 8.6, 28, 124)
    _pen(p, _T())
    p.drawPolyline(_poly(*pts))
    _dot(p, *pts[0], c, _DOT_R)
    _dot(p, *pts[-1], c, _DOT_R)


@_builtin("cissoid", ROSE)
def _cissoid(p, c):
    _pen(p, _T())
    p.drawPath(_cubic((3.5, 3.5), (10, 4.5, 12, 11, 12, 20.5)))
    p.drawPath(_cubic((20.5, 3.5), (14, 4.5, 12, 11, 12, 20.5)))
    _dot(p, 12, 20.5, c, _DOT_R)


@_builtin("cycloid", ROSE)
def _cycloid(p, c):
    _pen(p, _alpha(c, 0.6), 1.2)
    _line(p, 2.5, 19.5, 21.5, 19.5)
    _pen(p, _T())
    p.drawPath(_cubic((2.5, 19.5), (3.5, 5, 10, 5, 12, 19.5), (14, 5, 20.5, 5, 21.5, 19.5)))


@_builtin("formula", ROSE)
def _formula(p, c):
    _pen(p, _alpha(c, 0.6), 1.2)
    _line(p, 3, 12, 21, 12)
    _pen(p, _T())
    p.drawPath(_cubic((3, 12), (6, 2.5, 9, 2.5, 12, 12), (15, 21.5, 18, 21.5, 21, 12)))


@_builtin("helix", ROSE)
def _helix(p, c):
    pts = []
    steps = 72
    for i in range(steps + 1):
        t = i / steps * 3.0 * 2 * math.pi
        pts.append((12 + 7.5 * math.cos(t), 20.5 - 15.5 * i / steps + 2.3 * math.sin(t)))
    _pen(p, _T())
    p.drawPolyline(_poly(*pts))
    _dot(p, *pts[0], c, _DOT_R)
    _dot(p, *pts[-1], c, _DOT_R)


@_builtin("flower", ROSE)
def _flower(p, c):
    _pen(p, _T())
    for k in range(5):
        p.save()
        p.translate(12, 12)
        p.rotate(72 * k)
        p.drawEllipse(QPointF(0, -5.4), 2.8, 4.4)
        p.restore()
    _dot(p, 12, 12, c, 1.5)


@_builtin("text_spline", ROSE)
def _text_spline(p, c):
    pts = ((4, 4.5), (20, 4.5), (20, 9), (14.2, 9), (14.2, 20), (9.8, 20), (9.8, 9), (4, 9))
    _pen(p, _T())
    p.drawPolygon(_poly(*pts))
    _dot(p, *pts[0], c, _DOT_R)
    _dot(p, *pts[4], c, _DOT_R)


@_builtin("spline_arc", ROSE)
def _spline_arc(p, c):
    _arc_icon(p, c)


@_builtin("spline_smooth", ROSE)
def _spline_smooth(p, c):
    _spline(p, c)


@_builtin("subdivision_surface", AMETHYST, "generator")
def _subdivision_surface(p, c):
    _cube(p, c, None, 12, 12, 9.2)
    _pen(p, _T(), 1.8)
    _circle(p, 12, 12, 4.8)


@_builtin("extrude", AMETHYST, "pal_extrude")
def _extrude(p, c):
    top = _poly((12, 2.4), (18, 5.6), (12, 8.8), (6, 5.6))
    _fill(p, _T())
    p.drawPolygon(top)
    _pen(p, c)
    p.drawPolygon(top)
    _lines(p, ((6, 5.6), (6, 16.4), (12, 19.6), (18, 16.4), (18, 5.6)))
    _line(p, 12, 8.8, 12, 19.6)
    _line(p, 4, 21.6, 20, 21.6)


@_builtin("sweep", AMETHYST)
def _sweep(p, c):
    a = _cubic((4, 19), (4, 9, 16, 15, 17, 5))
    b = QPainterPath(a)
    b.translate(3.6, 1.0)
    _pen(p, c)
    p.drawPath(a)
    p.drawPath(b)
    _both(p, c, _T())
    p.drawEllipse(QPointF(5.8, 19.5), 2.2, 1.3)
    _pen(p, c)
    p.drawEllipse(QPointF(18.8, 5.5), 2.2, 1.3)


@_builtin("lathe", AMETHYST)
def _lathe(p, c):
    _dashed(p, _T(), 1.5, (1.6, 1.8))
    _line(p, 12, 2, 12, 22)
    _pen(p, c)
    left = _cubic((10, 3.8), (10.6, 8.4, 6, 10.8, 7.2, 15.6), (7.4, 17.6, 7.6, 19.4, 7.6, 20.4))
    p.drawPath(left)
    p.save()
    p.translate(24, 0)
    p.scale(-1, 1)
    p.drawPath(left)
    p.restore()
    _line(p, 10, 3.8, 14, 3.8)
    _line(p, 7.6, 20.4, 16.4, 20.4)


@_builtin("loft", AMETHYST)
def _loft(p, c):
    _pen(p, c)
    p.drawEllipse(QPointF(12, 5.2), 6.6, 2.4)
    p.drawEllipse(QPointF(12, 19), 8.2, 2.6)
    p.drawPath(_cubic((5.4, 5.2), (8, 9, 4.6, 14, 3.8, 19)))
    p.drawPath(_cubic((18.6, 5.2), (16, 9, 19.4, 14, 20.2, 19)))
    _pen(p, _T())
    p.drawEllipse(QPointF(12, 12), 4.6, 1.9)


@_builtin("boolean", AMETHYST, "boole")
def _boolean(p, c):
    a = _ellipse_path(9.2, 12, 6.4, 6.4)
    b = _ellipse_path(14.8, 12, 6.4, 6.4)
    _fill(p, _T())
    p.drawPath(a.intersected(b))
    _pen(p, c)
    _circle(p, 9.2, 12, 6.4)
    _circle(p, 14.8, 12, 6.4)


@_builtin("remesh", AMETHYST)
def _remesh(p, c):
    ring = _ngon(12, 12, 9, 6)
    inner = _ngon(12, 12, 3.8, 6)
    _fill(p, _T())
    p.drawPolygon(_poly(*inner))
    _pen(p, c)
    p.drawPolygon(_poly(*ring))
    p.drawPolygon(_poly(*inner))
    for a, b in zip(ring, inner):
        _line(p, *a, *b)


@_builtin("connect", AMETHYST)
def _connect(p, c):
    _cube(p, c, None, 7.4, 15.6, 5.2, 1.4)
    _cube(p, c, None, 16.6, 8.4, 5.2, 1.4)
    _pen(p, _T(), 2.0)
    _line(p, 11.0, 12.6, 13.0, 11.4)


@_builtin("cloner", AMETHYST)
def _cloner(p, c):
    _fill(p, _T())
    _circle(p, 12, 6.8, 3.8)
    _pen(p, c)
    _circle(p, 6.2, 17, 3.8)
    _circle(p, 17.8, 17, 3.8)


@_builtin("thicken", AMETHYST)
def _thicken(p, c):
    top = _poly((12, 4), (21, 8.6), (12, 13.2), (3, 8.6))
    _fill(p, _T())
    p.drawPolygon(top)
    _pen(p, c)
    p.drawPolygon(top)
    _lines(p, ((3, 8.6), (3, 13.6), (12, 18.2), (21, 13.6), (21, 8.6)))
    _line(p, 12, 13.2, 12, 18.2)


@_builtin("trunk", AMETHYST)
def _trunk(p, c):
    _pen(p, c)
    _lines(p, ((4.6, 21.0), (8.2, 4.4)))
    _lines(p, ((15.0, 21.0), (11.6, 4.4)))
    p.drawEllipse(QPointF(9.8, 21.0), 5.2, 1.8)
    p.drawEllipse(QPointF(9.9, 4.4), 1.7, 0.9)
    _pen(p, _T(), 1.8)
    p.drawEllipse(QPointF(8.6, 13.0), 3.7, 1.3)
    _pen(p, c, 1.6)
    _line(p, 12.4, 10.2, 18.2, 5.8)
    _line(p, 11.8, 14.2, 19.6, 8.2)
    _pen(p, _T(), 1.8)
    p.drawEllipse(QPointF(19.0, 7.0), 1.1, 1.8)


@_builtin("array", AMETHYST)
def _array(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(15.4, 3.6, 5.4, 5.4), 1.4, 1.4)
    p.drawRoundedRect(QRectF(9.3, 9.3, 5.4, 5.4), 1.4, 1.4)
    _both(p, c, _T())
    p.drawRoundedRect(QRectF(3.2, 15, 5.4, 5.4), 1.4, 1.4)


@_builtin("fracture", AMETHYST)
def _fracture(p, c):
    _pen(p, c)
    p.drawPolygon(_poly(*_ngon(12, 12, 9.2, 6)))
    _pen(p, _T(), 1.8)
    p.drawPolyline(_poly((10.8, 3.2), (13, 8.4), (9.6, 12.2), (13.6, 15.6), (11.2, 20.8)))


@_builtin("voronoi", AMETHYST, "pal_voronoi", "voronoi_fracture")
def _voronoi(p, c):
    _pen(p, c)
    _circle(p, 12, 12, 8.8)
    _pen(p, _T())
    a, b, cc, d = (9, 9.4), (15, 9), (16, 15), (9.6, 15.6)
    p.drawPolygon(_poly(a, b, cc, d))
    _line(p, *a, 5.8, 5.8)
    _line(p, *b, 17.4, 5.2)
    _line(p, *cc, 20.6, 14)
    _line(p, *d, 7.2, 19.4)


@_builtin("metaball", AMETHYST)
def _metaball(p, c):
    blob = _ellipse_path(9, 14, 6.2, 6.2).united(_ellipse_path(16, 8.8, 5, 5))
    _pen(p, c)
    p.drawPath(blob.simplified())
    _dot(p, 9, 14, _T(), 1.7)
    _dot(p, 16, 8.8, _T(), 1.5)


@_builtin("volume_builder", AMETHYST, "pal_volume_builder")
def _volume_builder(p, c):
    _cube(p, c, None, 7.2, 16, 4.6, 1.4)
    _cube(p, c, None, 16.8, 16, 4.6, 1.4)
    _cube(p, c, _T(), 12, 8.6, 4.6, 1.4)


@_builtin("volume_mesher", AMETHYST)
def _volume_mesher(p, c):
    _pen(p, c)
    _circle(p, 12, 12, 8.8)
    _pen(p, _T(), 1.4)
    p.drawEllipse(QRectF(3.2, 9, 17.6, 6))
    p.drawEllipse(QRectF(9, 3.2, 6, 17.6))


@_builtin("sdf", AMETHYST)
def _sdf(p, c):
    _pen(p, c)
    _circle(p, 12, 12, 8.8)
    _pen(p, _T())
    _circle(p, 12, 12, 5.2)
    _dot(p, 12, 12, _T(), 1.8)


@_builtin("fog", AMETHYST)
def _fog(p, c):
    cloud = _ellipse_path(7.5, 13, 4.5, 4)
    cloud = cloud.united(_ellipse_path(12, 9.4, 5, 5))
    cloud = cloud.united(_ellipse_path(16.6, 12.8, 4.6, 4.2))
    cloud = cloud.united(_rect_path(7.5, 12.5, 9.2, 4.5))
    _pen(p, c)
    p.drawPath(cloud)
    _pen(p, _T())
    _line(p, 5.5, 19.6, 18.5, 19.6)
    _line(p, 8.5, 22, 15.5, 22)


@_builtin("vector", AMETHYST)
def _vector(p, c):
    _arrow(p, c, 4, 14.4, 10, 8.4, _W, 3.4)
    _arrow(p, _T(), 8, 19.4, 18.4, 9, _W, 3.8)
    _arrow(p, c, 13.4, 20.8, 19.4, 14.8, _W, 3.4)


@_builtin("bend", AMETHYST, "deformer")
def _bend(p, c):
    _pen(p, c)
    _line(p, 4.5, 21, 4.5, 14)
    _line(p, 11.5, 5.5, 19.5, 5.5)
    _chevron(p, c, (20, 5.5), 0, 3.8)
    _pen(p, _T(), 1.8)
    p.drawArc(QRectF(4.5, 5.5, 14, 17), 90 * 16, 90 * 16)


@_builtin("twist", AMETHYST)
def _twist(p, c):
    _pen(p, c)
    p.drawPath(_cubic((6, 3), (20, 9, 4, 15, 18, 21)))
    _pen(p, _T())
    p.drawPath(_cubic((18, 3), (4, 9, 20, 15, 6, 21)))


@_builtin("ffd", AMETHYST)
def _ffd(p, c):
    _pen(p, c, 1.2)
    for i in range(3):
        v = 5 + i * 7
        _line(p, 5, v, 19, v)
        _line(p, v, 5, v, 19)
    for i in range(3):
        for j in range(3):
            _dot(p, 5 + i * 7, 5 + j * 7, _T(), 1.7)


@_builtin("linear_field", ROSE, "field")
def _linear_field(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((4, 12), (12, 9), (13, 18), (5, 21)))
    _pen(p, _T())
    p.drawPolygon(_poly((11, 6), (19, 3), (20, 12), (12, 15)))


@_builtin("radial_field", ROSE)
def _radial_field(p, c):
    _pen(p, c)
    _circle(p, 12, 12, 8.4)
    _pen(p, _T())
    _circle(p, 12, 12, 4)


@_builtin("spherical_field", ROSE)
def _spherical_field(p, c):
    _pen(p, c)
    _circle(p, 12, 12, 8.6)
    _pen(p, _T())
    p.drawEllipse(QRectF(3.4, 9, 17.2, 6))


@_builtin("box_field", ROSE)
def _box_field(p, c):
    h = _hexagon(12, 12, 8.6)
    _dashed(p, c, _W, (1.8, 1.8))
    p.drawPolygon(_hex_ring(h))
    _pen(p, _T())
    p.drawLine(h["C"], h["UL"])
    p.drawLine(h["C"], h["UR"])
    p.drawLine(h["C"], h["B"])


@_builtin("random_field", ROSE)
def _random_field(p, c):
    for k, (x, y, r) in enumerate(((6, 7, 2), (13, 5, 1.5), (18, 9, 2.2), (9, 14, 1.6), (16, 17, 1.8), (5, 18, 1.4))):
        _dot(p, x, y, _T() if k in (1, 4) else c, r)


@_builtin("camera")
def _camera(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(2.8, 8.4, 12.6, 9.6), 2.2, 2.2)
    p.drawPolygon(_poly((15.4, 11.6), (21.2, 8.6), (21.2, 17.8), (15.4, 14.8)))
    _circle(p, 6.4, 5.4, 2.4)
    _circle(p, 12, 5.4, 2.4)


@_builtin("light", CITRINE)
def _light(p, c):
    _pen(p, c)
    _circle(p, 12, 9.6, 6.2)
    _line(p, 9.4, 17.6, 14.6, 17.6)
    _line(p, 10.2, 20.4, 13.8, 20.4)
    _dot(p, 12, 9.6, _T(), 2.2)


@_builtin("sky")
def _sky(p, c):
    _pen(p, c)
    p.drawArc(QRectF(2.5, 7, 19, 19), 0, 180 * 16)
    _line(p, 2, 16.5, 22, 16.5)


@_builtin("floor")
def _floor(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((12, 5.5), (21.5, 11), (12, 16.5), (2.5, 11)))
    _line(p, 7.2, 8.2, 16.8, 13.8)
    _line(p, 16.8, 8.2, 7.2, 13.8)


@_builtin("environment", CITRINE)
def _environment(p, c):
    _pen(p, c)
    p.drawArc(QRectF(2.5, 8, 19, 19), 0, 180 * 16)
    _line(p, 2, 17.5, 22, 17.5)
    _dot(p, 15.5, 7.8, _T(), 2.5)


@_builtin("material")
def _material(p, c):
    clip = _ellipse_path(12, 12, 8.6, 8.6)
    shape = _rect_path(3.4, 3.4, 8.6, 8.6).united(_rect_path(12, 12, 8.6, 8.6))
    _clip_fill(p, shape, clip, _alpha(c, 0.3))
    _pen(p, c)
    _circle(p, 12, 12, 8.6)


@_builtin("python")
def _python(p, c):
    _text(p, c, "Py", 12, 16.5, 11, bold=True)


@_builtin("tag", MINT)
def _tag(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((4, 4), (12, 4), (20, 12), (12, 20), (4, 12)))
    _dot(p, 8, 8, _T(), 1.6)


@_builtin("star_favorite")
def _star_favorite(p, c):
    _pen(p, c)
    p.drawPolygon(_poly(*_star_pts(12, 12.6, 9, 4)))


@_builtin("layers", MINT)
def _layers(p, c):
    _pen(p, c)
    p.drawPolyline(_poly((4, 12), (12, 16), (20, 12)))
    p.drawPolyline(_poly((4, 16), (12, 20), (20, 16)))
    _pen(p, _T())
    p.drawPolygon(_poly((12, 4), (20, 8), (12, 12), (4, 8)))


@_builtin("file_new", MINT)
def _file_new(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((6, 3.5), (14, 3.5), (18.5, 8), (18.5, 20.5), (6, 20.5)))
    p.drawPolyline(_poly((14, 3.5), (14, 8), (18.5, 8)))
    _pen(p, _T())
    _line(p, 9.2, 14.6, 15.4, 14.6)
    _line(p, 12.3, 11.5, 12.3, 17.7)


@_builtin("file_open", MINT)
def _file_open(p, c):
    _pen(p, c)
    p.drawPolyline(_poly((3.5, 18.5), (3.5, 6.5), (9, 6.5), (11, 8.5), (18.5, 8.5), (18.5, 11)))
    _pen(p, _T())
    p.drawPolygon(_poly((3.5, 18.5), (6.4, 11), (21, 11), (18.1, 18.5)))


@_builtin("file_save", MINT)
def _file_save(p, c):
    _pen(p, c)
    p.drawPolygon(_poly((4, 6), (4, 18), (6, 20), (18, 20), (20, 18), (20, 6), (18, 4), (6, 4)))
    p.drawRect(QRectF(8, 4, 8, 5))
    _pen(p, _T())
    p.drawRect(QRectF(7.6, 13, 8.8, 7))


@_builtin("info")
def _info(p, c):
    _pen(p, c)
    _circle(p, 12, 12, 8.6)
    _line(p, 12, 11, 12, 16.6)
    _dot(p, 12, 7.8, _T(), 1.2)


@_builtin("window")
def _window(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2.4, 2.4)
    _line(p, 3.5, 8.6, 20.5, 8.6)
    _dot(p, 6.4, 6.6, _T(), 0.9)


@_builtin("asset_browser")
def _asset_browser(p, c):
    _pen(p, c)
    p.drawRoundedRect(QRectF(13, 4, 7, 7), 1.8, 1.8)
    p.drawRoundedRect(QRectF(4, 13, 7, 7), 1.8, 1.8)
    p.drawRoundedRect(QRectF(13, 13, 7, 7), 1.8, 1.8)
    _both(p, c, _T())
    p.drawRoundedRect(QRectF(4, 4, 7, 7), 1.8, 1.8)


@_builtin("connect_objects", MINT)
def _connect_objects(p, c):
    _cube(p, c, None, 8.4, 14.6, 5.6, 1.4)
    _cube(p, c, _T(), 15.6, 9.4, 5.6, 1.4)


@_builtin("guide", MINT)
def _guide(p, c):
    _dashed(p, c, 1.4, (1.8, 1.8))
    _line(p, 3, 12, 21, 12)
    _line(p, 12, 3, 12, 21)
    _dot(p, 12, 12, _T(), 2)


@_builtin("make_editable", MINT)
def _make_editable(p, c):
    _cube(p, c, None, 9.4, 9.6, 6.6, 1.5)
    def pencil():
        _pen(p, _T(), 1.5)
        p.drawPolygon(_poly((-6.2, -1.9), (2.6, -1.9), (6.6, 0), (2.6, 1.9), (-6.2, 1.9)))
        _line(p, -2.6, -1.9, -2.6, 1.9)
    _local(p, 16.2, 16.4, -45, pencil)


@_builtin("app_logo", MINT)
def _app_logo(p, c):
    tip = _poly((12, 2.2), (15.6, 9.6), (8.4, 9.6))
    _fill(p, _T())
    p.drawPolygon(tip)
    _pen(p, c)
    p.drawPolygon(_poly((12, 2.2), (17.6, 9.6), (17.6, 21.4), (6.4, 21.4), (6.4, 9.6)))
    _line(p, 6.4, 9.6, 17.6, 9.6)
    _line(p, 9.6, 9.6, 9.6, 21.4)
    _line(p, 14.4, 9.6, 14.4, 21.4)
    _line(p, 12, 2.2, 8.4, 9.6)
    _line(p, 12, 2.2, 15.6, 9.6)


MODELING_ICON_PREFIX = "mt_"

_MODELING_PAINTERS: dict[str, Callable[[QPainter, QColor], None]] = {}


def modeling_icon_name(tool_id: str) -> str:
    return MODELING_ICON_PREFIX + tool_id


def modeling_icon_ids() -> tuple[str, ...]:
    return tuple(_MODELING_PAINTERS)


def _mt(tool_id: str):
    def deco(fn: Callable[[QPainter, QColor], None]):
        _MODELING_PAINTERS[tool_id] = fn
        return fn
    return deco


def _is_tint(col: QColor | str) -> bool:
    return QColor(col).rgb() == _T().rgb()


def _mt_orange(alpha: float = 1.0) -> QColor:
    col = _T()
    col.setAlphaF(alpha)
    return col


def _mt_soft(c: QColor, alpha: float = 0.3) -> QColor:
    col = QColor(c)
    col.setAlphaF(alpha)
    return col


def _mt_fill_color(fill: QColor) -> QColor:
    q = QColor(fill)
    if _is_tint(q):
        q.setAlphaF(1.0 if q.alphaF() >= 0.6 else 0.3)
    else:
        q.setAlphaF(0.2)
    return q


def _mt_width(col: QColor | str, w: float) -> float:
    if _is_tint(col):
        return 2.4 if w >= 2.2 else 1.9
    return 1.5 if w >= 1.3 else 1.2


def _mt_stroke(col: QColor) -> QColor:
    q = QColor(col)
    if q.alphaF() < 0.6:
        q.setAlphaF(0.6)
    return q


def _mt_shape(p: QPainter, pts, line: QColor | None, w: float = 1.5, fill: QColor | None = None) -> None:
    if line is None:
        p.setPen(Qt.PenStyle.NoPen)
    else:
        _pen(p, _mt_stroke(line), _mt_width(line, w))
    p.setBrush(_mt_fill_color(fill) if fill is not None else Qt.BrushStyle.NoBrush)
    p.drawPolygon(_poly(*pts))


def _mt_path(p: QPainter, pts, col: QColor, w: float = 1.5) -> None:
    _pen(p, _mt_stroke(col), _mt_width(col, w))
    p.drawPolyline(_poly(*pts))


def _mt_dashed(p: QPainter, pts, col: QColor, w: float = 1.4) -> None:
    _dashed(p, _mt_stroke(col), _mt_width(col, w), (1.7, 1.6))
    p.drawPolyline(_poly(*pts))


def _mt_dot(p: QPainter, x: float, y: float, col: QColor, r: float = 1.7) -> None:
    _fill(p, col)
    p.drawEllipse(QPointF(x, y), r, r)


def _mt_shrink(pts, k: float):
    cx = sum(x for x, _y in pts) / len(pts)
    cy = sum(y for _x, y in pts) / len(pts)
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in pts]


def _mt_ngon(cx: float, cy: float, r: float, n: int, rot: float = -90.0):
    return _ngon(cx, cy, r, n, rot)


def _mt_arrow(p: QPainter, c: QColor, x0: float, y0: float, x1: float, y1: float,
              w: float = 1.5, head: float = 3.4) -> None:
    _arrow(p, _mt_stroke(c), x0, y0, x1, y1, _mt_width(c, w), max(2.6, head))


def _arrow_head(p: QPainter, c: QColor, tip: tuple[float, float], angle_deg: float,
                length: float = 4.0, width: float = 3.4) -> None:
    _chevron(p, _mt_stroke(c), tip, angle_deg, max(2.6, length), _mt_width(c, 1.5))


def _mt_arc_arrow(p: QPainter, cx: float, cy: float, rx: float, ry: float, a0: float,
                  span: float, col: QColor, w: float = 1.6, head: float = 3.6) -> None:
    pts = []
    for i in range(25):
        a = math.radians(a0 + span * i / 24.0)
        pts.append((cx + rx * math.cos(a), cy - ry * math.sin(a)))
    _mt_path(p, pts[:-1], col, w)
    (x0, y0), (x1, y1) = pts[-4], pts[-1]
    _arrow_head(p, col, (x1, y1), math.degrees(math.atan2(y1 - y0, x1 - x0)), head, head * 0.95)


def _mt_cube(p: QPainter, c: QColor, x: float, y: float, top: QColor) -> None:
    front = [(x, y + 3), (x + 6, y + 3), (x + 6, y + 9), (x, y + 9)]
    side = [(x + 6, y + 3), (x + 9, y), (x + 9, y + 6), (x + 6, y + 9)]
    cap = [(x, y + 3), (x + 6, y + 3), (x + 9, y), (x + 3, y)]
    _mt_shape(p, front, c, 1.4, _mt_soft(c, 0.3))
    _mt_shape(p, side, c, 1.4, _mt_soft(c, 0.55))
    _mt_shape(p, cap, c, 1.4, top)


@_mt("extrude")
def _mt_extrude(p, c):
    _mt_shape(p, [(3, 13), (15, 13), (15, 21), (3, 21)], c, 1.4, _mt_soft(c, 0.3))
    _mt_shape(p, [(15, 13), (21, 7), (21, 15), (15, 21)], c, 1.4, _mt_soft(c, 0.55))
    _mt_shape(p, [(3, 13), (15, 13), (21, 7), (9, 7)], _mt_orange(), 1.4, _mt_orange(0.75))
    _mt_arrow(p, c, 9.0, 6.0, 9.0, 1.6, 1.3, 3.2)


@_mt("inset")
def _mt_inset(p, c):
    outer = [(3, 20), (18, 20), (21, 4), (6, 4)]
    inner = _mt_shrink(outer, 0.5)
    _mt_shape(p, outer, c, 1.5)
    for a, b in zip(outer, inner):
        _mt_path(p, [a, b], _mt_soft(c, 0.5), 0.9)
    _mt_shape(p, inner, _mt_orange(), 1.4, _mt_orange(0.75))


@_mt("matrix_extrude")
def _mt_matrix_extrude(p, c):
    _mt_shape(p, [(2, 13), (11, 13), (11, 22), (2, 22)], c, 1.4)
    _mt_shape(p, [(8.5, 8.5), (15.5, 8.5), (15.5, 15.5), (8.5, 15.5)], c, 1.4, _mt_soft(c, 0.3))
    _mt_shape(p, [(15, 4), (20.5, 4), (20.5, 9.5), (15, 9.5)], _mt_orange(), 1.4, _mt_orange(0.8))
    _mt_path(p, [(11, 13), (15.5, 8.5)], _mt_soft(c, 0.7), 1.0)
    _mt_path(p, [(15.5, 8.5), (20.5, 4)], _mt_soft(c, 0.7), 1.0)


@_mt("smooth_shift")
def _mt_smooth_shift(p, c):
    _mt_shape(p, [(4, 21), (14, 21), (20, 16), (10, 16)], c, 1.4, _mt_soft(c, 0.3))
    _mt_shape(p, [(4, 9), (14, 9), (20, 4), (10, 4)], _mt_orange(), 1.4, _mt_orange(0.75))
    for x in (8.0, 12.0, 16.0):
        _mt_arrow(p, c, x, 18.5, x, 12.0, 1.2, 3.0)


@_mt("thicken")
def _mt_thicken(p, c):
    _mt_shape(p, [(3, 12), (16, 12), (16, 16), (3, 16)], c, 1.4, _mt_soft(c, 0.3))
    _mt_shape(p, [(16, 12), (22, 6), (22, 10), (16, 16)], c, 1.4, _mt_soft(c, 0.55))
    _mt_shape(p, [(3, 12), (16, 12), (22, 6), (9, 6)], _mt_orange(), 1.4, _mt_orange(0.75))
    _mt_arrow(p, c, 12.0, 4.6, 12.0, 1.8, 1.3, 3.0)
    _mt_arrow(p, c, 10.0, 17.8, 10.0, 21.8, 1.3, 3.0)


@_mt("trunk")
def _mt_trunk(p, c):
    body = [(4.2, 21.0), (8.0, 13.4), (3.0, 5.6), (6.6, 3.0), (11.2, 9.4), (17.4, 3.0), (20.8, 5.6),
            (13.6, 13.4), (15.6, 21.0)]
    _mt_shape(p, body, c, 1.5, _mt_soft(c, 0.45))
    _pen(p, _mt_stroke(_mt_orange()), 2.4)
    p.drawEllipse(QPointF(9.9, 21.0), 5.7, 1.8)
    _mt_path(p, [(7.0, 16.6), (12.6, 16.6)], _mt_orange(), 2.4)
    _mt_dot(p, 4.8, 4.2, _mt_orange(), 1.7)
    _mt_dot(p, 19.0, 4.2, _mt_orange(), 1.7)


@_mt("bevel")
def _mt_bevel(p, c):
    _mt_shape(p, [(3, 21), (3, 3), (14, 3), (21, 10), (21, 21)], c, 1.5, _mt_soft(c, 0.25))
    _mt_path(p, [(14, 3), (21, 10)], _mt_orange(), 2.4)
    _mt_dot(p, 14, 3, _mt_orange(), 1.8)
    _mt_dot(p, 21, 10, _mt_orange(), 1.8)


@_mt("loop_path_cut")
def _mt_loop_cut(p, c):
    _mt_shape(p, [(2, 20), (15, 20), (22, 5), (9, 5)], c, 1.5, _mt_soft(c, 0.2))
    _mt_path(p, [(5.5, 12.5), (18.5, 12.5)], _mt_orange(), 2.0)
    _mt_dot(p, 5.5, 12.5, _mt_orange(), 1.8)
    _mt_dot(p, 18.5, 12.5, _mt_orange(), 1.8)


@_mt("line_cut")
def _mt_line_cut(p, c):
    _mt_shape(p, [(2, 20), (15, 20), (22, 5), (9, 5)], c, 1.5, _mt_soft(c, 0.2))
    _mt_dashed(p, [(1.5, 8.5), (22.5, 18.0)], _mt_orange(), 1.8)
    _mt_dot(p, 4.4, 9.8, _mt_orange(), 1.8)
    _mt_dot(p, 19.6, 16.7, _mt_orange(), 1.8)


@_mt("plane_cut")
def _mt_plane_cut(p, c):
    _mt_shape(p, [(4, 10), (14, 10), (14, 20), (4, 20)], c, 1.4, _mt_soft(c, 0.25))
    _mt_shape(p, [(14, 10), (19, 6), (19, 16), (14, 20)], c, 1.4, _mt_soft(c, 0.45))
    _mt_shape(p, [(4, 10), (14, 10), (19, 6), (9, 6)], c, 1.4, _mt_soft(c, 0.35))
    _mt_shape(p, [(1, 16), (17, 16), (23, 10), (7, 10)], _mt_orange(), 1.5, _mt_orange(0.5))


@_mt("edge_cut")
def _mt_edge_cut(p, c):
    _mt_shape(p, [(4, 4), (20, 4), (20, 20), (4, 20)], c, 1.5, _mt_soft(c, 0.2))
    _mt_path(p, [(20, 4), (20, 20)], _mt_orange(), 2.4)
    _mt_path(p, [(20, 12), (9, 20)], _mt_orange(), 1.6)
    _mt_dot(p, 20, 12, _mt_orange(), 2.0)
    _mt_dot(p, 9, 20, _mt_orange(), 1.8)


@_mt("bridge")
def _mt_bridge(p, c):
    _mt_shape(p, [(2, 7), (8, 5), (8, 19), (2, 17)], c, 1.5, _mt_soft(c, 0.3))
    _mt_shape(p, [(16, 5), (22, 7), (22, 17), (16, 19)], c, 1.5, _mt_soft(c, 0.3))
    _mt_shape(p, [(8, 5), (16, 5), (16, 19), (8, 19)], _mt_orange(), 1.4, _mt_orange(0.7))
    _mt_path(p, [(8, 12), (16, 12)], _mt_orange(), 1.0)


@_mt("weld")
def _mt_weld(p, c):
    _mt_path(p, [(3, 6), (3, 18)], _mt_soft(c, 0.6), 1.4)
    _mt_path(p, [(21, 6), (21, 18)], _mt_soft(c, 0.6), 1.4)
    _mt_dot(p, 3, 12, c, 2.0)
    _mt_dot(p, 21, 12, c, 2.0)
    _mt_arrow(p, c, 6.0, 12.0, 9.2, 12.0, 1.4, 3.2)
    _mt_arrow(p, c, 18.0, 12.0, 14.8, 12.0, 1.4, 3.2)
    _mt_dot(p, 12, 12, _mt_orange(), 2.8)


@_mt("stitch_and_sew")
def _mt_stitch(p, c):
    _mt_path(p, [(5, 3), (5, 21)], c, 2.0)
    _mt_path(p, [(19, 3), (19, 21)], c, 2.0)
    _mt_path(p, [(5, 4), (19, 8), (5, 12), (19, 16), (5, 20)], _mt_orange(), 1.5)


@_mt("connect_points_edges")
def _mt_connect(p, c):
    ring = _mt_ngon(12, 12, 9.0, 6)
    _mt_shape(p, ring, c, 1.4, _mt_soft(c, 0.2))
    tri = [ring[0], ring[2], ring[4]]
    _mt_shape(p, tri, _mt_orange(), 1.6)
    for x, y in tri:
        _mt_dot(p, x, y, _mt_orange(), 1.9)


@_mt("close_polygon_hole")
def _mt_close_hole(p, c):
    ring = _mt_ngon(12, 12, 9.2, 8, -67.5)
    _mt_shape(p, ring, None, 0, _mt_orange(0.6))
    _mt_path(p, ring[1:] + [ring[0]], c, 1.6)
    _mt_dashed(p, [ring[0], ring[1]], _mt_orange(), 1.8)


@_mt("dissolve")
def _mt_dissolve(p, c):
    _mt_shape(p, [(3, 5), (21, 5), (21, 19), (3, 19)], c, 1.5, _mt_soft(c, 0.2))
    _mt_dashed(p, [(12, 5), (12, 19)], _mt_orange(), 2.0)
    _mt_dot(p, 12, 5, _mt_orange(), 1.7)
    _mt_dot(p, 12, 19, _mt_orange(), 1.7)


@_mt("melt")
def _mt_melt(p, c):
    _mt_shape(p, _mt_ngon(12, 12, 10.0, 6), c, 1.2, _mt_soft(c, 0.18))
    drop = QPainterPath()
    drop.moveTo(12, 3.5)
    drop.cubicTo(14, 8, 18, 10.5, 18, 15)
    drop.cubicTo(18, 18.8, 15.2, 21, 12, 21)
    drop.cubicTo(8.8, 21, 6, 18.8, 6, 15)
    drop.cubicTo(6, 10.5, 10, 8, 12, 3.5)
    _fill(p, _mt_orange())
    p.drawPath(drop)


@_mt("collapse")
def _mt_collapse(p, c):
    _mt_shape(p, [(3, 3), (21, 3), (21, 21), (3, 21)], c, 1.3, _mt_soft(c, 0.15))
    for pt in ((3, 3), (21, 3), (21, 21), (3, 21)):
        _mt_path(p, [pt, (12, 12)], c, 1.2)
    _mt_dot(p, 12, 12, _mt_orange(), 3.0)


@_mt("delete")
def _mt_delete(p, c):
    _mt_shape(p, [(3, 3), (15, 3), (15, 15), (3, 15)], c, 1.5, _mt_soft(c, 0.25))
    _mt_path(p, [(12, 12), (21, 21)], _mt_orange(), 2.6)
    _mt_path(p, [(21, 12), (12, 21)], _mt_orange(), 2.6)


@_mt("optimize")
def _mt_optimize(p, c):
    _mt_path(p, [(2, 6), (22, 6)], c, 1.3)
    for x in (2, 22):
        _mt_dot(p, x, 6, c, 1.9)
    for x in (7, 12, 17):
        _mt_dot(p, x, 6, _mt_orange(), 1.6)
    _mt_arrow(p, _mt_orange(), 12.0, 9.5, 12.0, 14.5, 1.6, 3.4)
    _mt_path(p, [(2, 19), (22, 19)], c, 1.3)
    for x in (2, 22):
        _mt_dot(p, x, 19, c, 1.9)


@_mt("disconnect")
def _mt_disconnect(p, c):
    _mt_shape(p, [(2, 3), (10, 3), (10, 16), (2, 16)], c, 1.5, _mt_soft(c, 0.25))
    _mt_shape(p, [(14, 8), (22, 8), (22, 21), (14, 21)], c, 1.5, _mt_soft(c, 0.25))
    _mt_dashed(p, [(10, 3), (14, 8)], _mt_orange(), 1.5)
    _mt_dashed(p, [(10, 16), (14, 21)], _mt_orange(), 1.5)
    for pt in ((10, 3), (10, 16), (14, 8), (14, 21)):
        _mt_dot(p, pt[0], pt[1], _mt_orange(), 1.7)


@_mt("split")
def _mt_split(p, c):
    _mt_shape(p, [(2, 2), (13, 2), (2, 13)], c, 1.5, _mt_soft(c, 0.3))
    _mt_shape(p, [(22, 11), (22, 22), (11, 22)], c, 1.5, _mt_soft(c, 0.3))
    _mt_dashed(p, [(13, 2), (22, 11)], _mt_orange(), 1.5)
    _mt_dashed(p, [(2, 13), (11, 22)], _mt_orange(), 1.5)
    for pt in ((13, 2), (22, 11), (2, 13), (11, 22)):
        _mt_dot(p, pt[0], pt[1], _mt_orange(), 1.7)


@_mt("slide")
def _mt_slide(p, c):
    _mt_shape(p, [(3, 20), (15, 20), (21, 4), (9, 4)], c, 1.5, _mt_soft(c, 0.2))
    _mt_path(p, [(6.0, 12.0), (18.0, 12.0)], _mt_orange(), 2.4)
    _mt_arrow(p, c, 13.0, 9.6, 14.6, 5.6, 1.3, 3.0)
    _mt_arrow(p, c, 11.0, 14.4, 9.4, 18.4, 1.3, 3.0)


@_mt("iron")
def _mt_iron(p, c):
    wave = QPainterPath()
    wave.moveTo(2, 18)
    wave.cubicTo(5, 12.5, 8.5, 12.5, 12, 18)
    wave.cubicTo(15.5, 23, 19, 23, 22, 18)
    _pen(p, c, 1.6)
    p.drawPath(wave)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_mt_orange())
    p.drawRoundedRect(QRectF(3, 3, 18, 4.4), 1.4, 1.4)
    _mt_arrow(p, c, 12.0, 9.0, 12.0, 13.4, 1.4, 3.2)


@_mt("equal_spacing")
def _mt_equal_spacing(p, c):
    _mt_path(p, [(3, 17), (21, 17)], _mt_soft(c, 0.6), 1.2)
    for k, x in enumerate((3.0, 9.0, 15.0, 21.0)):
        _mt_path(p, [(x, 4.5), (x, 11)], _mt_orange(), 1.4)
        _mt_dot(p, x, 17, c if k in (0, 3) else _mt_orange(), 2.0)
    _mt_path(p, [(3, 7.8), (21, 7.8)], _mt_orange(), 1.4)


@_mt("straighten_edges")
def _mt_straighten(p, c):
    _mt_path(p, [(2, 8), (7, 3.5), (12, 8.5), (17, 3.5), (22, 8)], _mt_soft(c, 0.8), 1.3)
    _mt_arrow(p, c, 12.0, 10.5, 12.0, 14.0, 1.2, 2.8)
    _mt_path(p, [(2, 19), (22, 19)], _mt_orange(), 2.2)
    _mt_dot(p, 2, 19, _mt_orange(), 1.9)
    _mt_dot(p, 22, 19, _mt_orange(), 1.9)


@_mt("fit_circle")
def _mt_fit_circle(p, c):
    _pen(p, _mt_orange(), 1.7)
    p.drawEllipse(QPointF(12, 12), 8.0, 8.0)
    for ang, rad in ((-80, 6.8), (-10, 9.4), (60, 7.2), (130, 9.2), (200, 6.9)):
        a = math.radians(ang)
        _mt_dot(p, 12 + rad * math.cos(a), 12 + rad * math.sin(a), c, 1.9)


@_mt("flatten")
def _mt_flatten(p, c):
    _mt_shape(p, [(2, 15), (16, 15), (22, 9), (8, 9)], _mt_orange(), 1.5, _mt_orange(0.5))
    _mt_dot(p, 11, 2.6, c, 1.7)
    _mt_arrow(p, c, 11.0, 4.6, 11.0, 8.6, 1.2, 2.8)
    _mt_dot(p, 13, 21.4, c, 1.7)
    _mt_arrow(p, c, 13.0, 19.4, 13.0, 15.4, 1.2, 2.8)
    _mt_dot(p, 4, 21.4, c, 1.7)


@_mt("smooth_edges")
def _mt_smooth_edges(p, c):
    _mt_path(p, [(2, 17), (6, 8), (10, 17), (14, 8), (18, 17), (22, 11)], _mt_soft(c, 0.8), 1.3)
    curve = QPainterPath()
    curve.moveTo(2, 14)
    curve.cubicTo(5, 6, 9, 20, 12, 12.5)
    curve.cubicTo(15, 6, 19, 17, 22, 8.5)
    _pen(p, _mt_orange(), 1.9)
    p.drawPath(curve)


@_mt("randomize")
def _mt_randomize(p, c):
    _pen(p, c, 1.5)
    p.setBrush(_mt_soft(c, 0.2))
    p.drawRoundedRect(QRectF(3, 3, 18, 18), 3.5, 3.5)
    for x, y in ((8, 8), (16, 8), (12, 12), (8, 16), (16, 16)):
        _mt_dot(p, x, y, _mt_orange(), 1.7)


@_mt("set_flow")
def _mt_set_flow(p, c):
    for dy, col, w in ((-6.0, _mt_soft(c, 0.8), 1.3), (0.0, _mt_orange(), 2.0), (6.0, _mt_soft(c, 0.8), 1.3)):
        curve = QPainterPath()
        curve.moveTo(2, 15 + dy)
        curve.cubicTo(9, 15 + dy, 9, 9 + dy, 22, 9 + dy)
        _pen(p, col, w)
        p.drawPath(curve)


@_mt("set_point_value")
def _mt_set_point_value(p, c):
    _mt_arrow(p, c, 4.0, 19.0, 22.0, 19.0, 1.3, 3.2)
    _mt_arrow(p, c, 4.0, 19.0, 4.0, 2.0, 1.3, 3.2)
    _mt_path(p, [(4, 19), (9, 14.5)], _mt_soft(c, 0.7), 1.2)
    _mt_dashed(p, [(15, 9), (15, 19)], _mt_soft(c, 0.8), 1.0)
    _mt_dashed(p, [(15, 9), (4, 9)], _mt_soft(c, 0.8), 1.0)
    _mt_dot(p, 15, 9, _mt_orange(), 2.6)


@_mt("normal_move")
def _mt_normal_move(p, c):
    _mt_shape(p, [(2, 21), (14, 21), (20, 15), (8, 15)], c, 1.5, _mt_soft(c, 0.3))
    _mt_arrow(p, _mt_orange(), 11.0, 18.0, 11.0, 2.5, 2.0, 5.0)


@_mt("normal_scale")
def _mt_normal_scale(p, c):
    _mt_shape(p, [(2, 21), (14, 21), (20, 15), (8, 15)], c, 1.5, _mt_soft(c, 0.3))
    _mt_arrow(p, _mt_orange(), 11.0, 12.5, 11.0, 2.0, 1.8, 4.4)
    _mt_path(p, [(7.5, 12.5), (14.5, 12.5)], _mt_orange(), 1.8)
    _mt_path(p, [(7.5, 8.0), (14.5, 8.0)], _mt_soft(c, 0.8), 1.2)


@_mt("normal_rotate")
def _mt_normal_rotate(p, c):
    _mt_shape(p, [(2, 22), (14, 22), (20, 17), (8, 17)], c, 1.5, _mt_soft(c, 0.3))
    _mt_dashed(p, [(11, 3), (11, 18)], _mt_soft(c, 0.8), 1.2)
    _mt_arc_arrow(p, 11.0, 10.5, 8.0, 3.6, 30.0, 290.0, _mt_orange(), 1.9, 4.0)


@_mt("reverse_normals")
def _mt_reverse_normals(p, c):
    _mt_path(p, [(2, 12), (22, 12)], _mt_soft(c, 0.7), 2.2)
    _mt_dashed(p, [(7, 9.5), (7, 4.5)], _mt_soft(c, 0.8), 1.5)
    _arrow_head(p, _mt_soft(c, 0.8), (7, 2.0), -90, 3.6, 3.4)
    _mt_arrow(p, _mt_orange(), 17.0, 14.5, 17.0, 22.0, 2.0, 4.6)


@_mt("align_normals")
def _mt_align_normals(p, c):
    for x in (4.5, 12.0, 19.5):
        _mt_path(p, [(x - 3.2, 20), (x + 3.2, 20)], c, 2.2)
        _mt_arrow(p, _mt_orange(), x, 16.5, x, 3.5, 1.7, 4.0)


@_mt("subdivide")
def _mt_subdivide(p, c):
    _mt_shape(p, [(3, 3), (21, 3), (21, 21), (3, 21)], c, 1.5, _mt_soft(c, 0.15))
    _mt_path(p, [(12, 3), (12, 21)], _mt_orange(), 1.8)
    _mt_path(p, [(3, 12), (21, 12)], _mt_orange(), 1.8)
    _mt_dot(p, 12, 12, _mt_orange(), 2.2)


@_mt("triangulate")
def _mt_triangulate(p, c):
    _mt_shape(p, [(3, 3), (21, 3), (3, 21)], None, 0, _mt_soft(c, 0.3))
    _mt_shape(p, [(3, 3), (21, 3), (21, 21), (3, 21)], c, 1.5)
    _mt_path(p, [(21, 3), (3, 21)], _mt_orange(), 2.0)


@_mt("untriangulate")
def _mt_untriangulate(p, c):
    _mt_shape(p, [(3, 3), (21, 3), (21, 21), (3, 21)], c, 1.5, _mt_orange(0.85))
    _mt_dashed(p, [(21, 3), (3, 21)], _mt_soft(c, 0.9), 1.3)


@_mt("remove_ngons")
def _mt_remove_ngons(p, c):
    ring = _mt_ngon(12, 12, 9.5, 6)
    _mt_shape(p, ring, c, 1.5, _mt_soft(c, 0.15))
    for k in (0, 2, 4):
        _mt_path(p, [(12, 12), ring[k]], _mt_orange(), 1.8)
    _mt_dot(p, 12, 12, _mt_orange(), 1.8)


@_mt("retriangulate_ngons")
def _mt_retriangulate_ngons(p, c):
    ring = _mt_ngon(12, 12.5, 9.5, 5)
    _mt_shape(p, ring, c, 1.5, _mt_soft(c, 0.15))
    _mt_path(p, [ring[0], ring[2]], _mt_orange(), 1.8)
    _mt_path(p, [ring[0], ring[3]], _mt_orange(), 1.8)
    _mt_dot(p, ring[0][0], ring[0][1], _mt_orange(), 1.8)


@_mt("spin_edge")
def _mt_spin_edge(p, c):
    _mt_shape(p, [(4, 4), (20, 20), (4, 20)], None, 0, _mt_soft(c, 0.3))
    _mt_shape(p, [(4, 4), (20, 4), (20, 20), (4, 20)], c, 1.5)
    _mt_path(p, [(4, 4), (20, 20)], _mt_orange(), 2.2)
    _mt_arc_arrow(p, 12.0, 12.0, 5.0, 5.0, 150.0, 250.0, c, 1.4, 3.2)


@_mt("array")
def _mt_array(p, c):
    _mt_shape(p, [(2, 15), (8, 15), (8, 21), (2, 21)], _mt_orange(), 1.5, _mt_orange(0.75))
    _mt_shape(p, [(9, 9), (15, 9), (15, 15), (9, 15)], c, 1.5, _mt_soft(c, 0.3))
    _mt_shape(p, [(16, 3), (22, 3), (22, 9), (16, 9)], c, 1.5, _mt_soft(c, 0.3))


@_mt("clone")
def _mt_clone(p, c):
    _mt_cube(p, c, 2.0, 5.0, _mt_soft(c, 0.45))
    _mt_cube(p, c, 12.0, 11.0, _mt_orange(0.85))


@_mt("mirror")
def _mt_mirror(p, c):
    _mt_dashed(p, [(12, 2), (12, 22)], _mt_soft(c, 0.8), 1.2)
    _mt_shape(p, [(3, 20), (10, 20), (10, 5)], c, 1.5, _mt_soft(c, 0.3))
    _mt_shape(p, [(21, 20), (14, 20), (14, 5)], _mt_orange(), 1.5, _mt_orange(0.7))


@_mt("edge_to_spline")
def _mt_edge_to_spline(p, c):
    pts = [(3, 18), (9, 7), (15, 17), (21, 6)]
    _mt_path(p, pts, _mt_soft(c, 0.8), 1.3)
    curve = QPainterPath()
    curve.moveTo(*pts[0])
    curve.cubicTo(7, 3, 13, 25, 21, 6)
    _pen(p, _mt_orange(), 1.9)
    p.drawPath(curve)
    for x, y in pts:
        _mt_dot(p, x, y, c, 1.6)


for _mt_id, _mt_fn in _MODELING_PAINTERS.items():
    _REGISTRY[modeling_icon_name(_mt_id)] = _unit(_mt_fn)
    _TINTS[modeling_icon_name(_mt_id)] = CITRINE
