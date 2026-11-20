import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPen, QPolygonF

SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0

    def pt(x: float, y: float) -> QPointF:
        return QPointF(x * s, y * s)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1f2130"))
    p.drawRoundedRect(int(8 * s), int(8 * s), int(240 * s), int(240 * s), 48 * s, 48 * s)

    facets = [
        ([(128, 28), (84, 92), (128, 112)], "#c9d2ff"),
        ([(128, 28), (172, 92), (128, 112)], "#8f9cf0"),
        ([(84, 92), (128, 112), (128, 228), (70, 168)], "#6f7fe6"),
        ([(172, 92), (128, 112), (128, 228), (186, 168)], "#4b58c4"),
    ]
    for poly, color in facets:
        grad = QLinearGradient(pt(70, 28), pt(186, 228))
        grad.setColorAt(0.0, QColor(color).lighter(115))
        grad.setColorAt(1.0, QColor(color))
        p.setBrush(grad)
        p.setPen(QPen(QColor("#e8ecff"), max(1.0, 3 * s)))
        p.drawPolygon(QPolygonF([pt(x, y) for x, y in poly]))
    p.end()
    return img


def main(out: str) -> None:
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    draw(256).save(out, "ICO")
    draw(256).save(str(Path(out).with_suffix(".png")), "PNG")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "assets/quartz_studio.ico")
