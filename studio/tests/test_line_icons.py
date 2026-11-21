from __future__ import annotations

import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from quartz_studio import icons, theme
from quartz_studio.ext.icon_svgs import ICON_SVGS

LINE_ICONS = (
    "line", "m_line", "spline", "spline_generic", "spline_arc", "spline_smooth", "rectangle", "circle",
    "arc", "n_side", "four_side", "star", "cogwheel", "profile", "cissoid", "cycloid", "formula", "helix",
    "flower", "text_spline",
)
CLOSED = ("rectangle", "circle", "n_side", "four_side", "star", "cogwheel")
NO_POINTS = ("cogwheel", "formula")
SIZES = (16, 24, 48)
MAX_COVERAGE = {16: 0.55, 24: 0.5, 48: 0.42}
ROSE = QColor(theme.TINT_ROSE)
LIGHT = QColor(theme.ICON_STROKE)

_APP: list = []


def _app() -> QApplication:
    if not _APP:
        _APP.append(QApplication.instance() or QApplication([]))
    return _APP[0]


def _blank(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    return img


def _render_py(name: str, size: int) -> QImage:
    _app()
    img = _blank(size)
    p = QPainter(img)
    icons.render(p, QRectF(0, 0, size, size), name)
    p.end()
    return img


def _render_svg(name: str, size: int) -> QImage:
    _app()
    img = _blank(size)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(QByteArray(ICON_SVGS[name].encode("utf-8"))).render(p, QRectF(0, 0, size, size))
    p.end()
    return img


def _sources(name: str):
    yield "icons", _render_py
    if name in ICON_SVGS:
        yield "svg", _render_svg


def _coverage(img: QImage) -> float:
    total = img.width() * img.height()
    hit = sum(1 for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x, y).alpha() > 32)
    return hit / total


def _near(color: QColor, ref: QColor, tol: int) -> bool:
    return (color.alpha() >= 250 and abs(color.red() - ref.red()) <= tol
            and abs(color.green() - ref.green()) <= tol and abs(color.blue() - ref.blue()) <= tol)


def _count(img: QImage, ref: QColor, tol: int = 12) -> int:
    return sum(1 for y in range(img.height()) for x in range(img.width()) if _near(img.pixelColor(x, y), ref, tol))


def test_every_icon_exists():
    for name in LINE_ICONS:
        assert icons.has(name), name


def test_svg_has_no_fill():
    allowed = {"none", theme.ICON_STROKE.lower()}
    for name in LINE_ICONS:
        if name not in ICON_SVGS:
            continue
        fills = set(re.findall(r'\bfill="([^"]*)"', ICON_SVGS[name]))
        assert {f.lower() for f in fills} <= allowed, (name, fills)
        for el in re.findall(r"<(?:polygon|rect|circle|path|ellipse|polyline) [^>]*/>", ICON_SVGS[name]):
            assert 'fill="' in el, (name, el)


def test_svg_dots_are_small_and_light():
    for name in LINE_ICONS:
        if name not in ICON_SVGS:
            continue
        for el in re.findall(r"<circle [^>]*/>", ICON_SVGS[name]):
            if 'fill="%s"' % theme.ICON_STROKE in el:
                assert float(re.search(r'\br="([\d.]+)"', el).group(1)) <= 4.5, (name, el)


def test_stroke_only_coverage():
    for name in LINE_ICONS:
        for label, render in _sources(name):
            for size in SIZES:
                cov = _coverage(render(name, size))
                assert 0.02 < cov <= MAX_COVERAGE[size], (name, label, size, round(cov, 3))


def test_closed_shapes_are_hollow():
    for name in CLOSED:
        for label, render in _sources(name):
            for size in (24, 48):
                img = render(name, size)
                c = size // 2
                for x, y in ((c, c), (c - 1, c), (c, c - 1), (c - 1, c - 1)):
                    alpha = img.pixelColor(x, y).alpha()
                    assert alpha <= 8, (name, label, size, (x, y), alpha)


def test_outline_is_rose():
    for name in LINE_ICONS:
        for label, render in _sources(name):
            img = render(name, 48)
            rose = _count(img, ROSE)
            assert rose >= 60, (name, label, rose)


def test_points_are_white():
    for name in LINE_ICONS:
        if name in NO_POINTS:
            continue
        for label, render in _sources(name):
            if label == "icons" and name == "cycloid":
                continue
            img = render(name, 48)
            assert _count(img, LIGHT, 10) >= 6, (name, label)


def test_no_translucent_rose_area():
    for name in LINE_ICONS:
        for label, render in _sources(name):
            img = render(name, 48)
            area = 0
            for y in range(img.height()):
                for x in range(img.width()):
                    c = img.pixelColor(x, y)
                    if 40 <= c.alpha() <= 200 and c.red() > 200 and c.green() < 170:
                        area += 1
            assert area < 0.12 * img.width() * img.height(), (name, label, area)


def _run_as_script() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
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
