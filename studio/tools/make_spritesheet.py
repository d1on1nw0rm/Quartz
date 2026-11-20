from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import pkgutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import quartz_studio
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from quartz_studio import theme
from quartz_studio.app import create_app


def load_all_icons() -> list[str]:
    from quartz_studio import icons, widgets

    for mod in pkgutil.iter_modules(widgets.__path__):
        importlib.import_module(f"quartz_studio.widgets.{mod.name}")
    return sorted(icons.names())


def render(names: list[str], cell: int, columns: int, labels: bool, bg: str | None) -> QImage:
    from quartz_studio import icons

    label_h = 14 if labels else 0
    rows = math.ceil(len(names) / columns)
    w, h = cell * columns, (cell + label_h) * rows
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(bg) if bg else Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(9)
    p.setFont(font)
    pad = cell * 0.125
    for i, name in enumerate(names):
        x, y = (i % columns) * cell, (i // columns) * (cell + label_h)
        if bg:
            p.setPen(QPen(QColor(theme.HAIRLINE), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(x + 0.5, y + 0.5, cell - 1, cell + label_h - 1))
        icons.render(p, QRectF(x + pad, y + pad, cell - 2 * pad, cell - 2 * pad), name)
        if labels:
            p.setPen(QColor(theme.TEXT_SECONDARY))
            p.drawText(QRectF(x, y + cell, cell, label_h),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, cell - 2))
    p.end()
    return img


def contact_sheet(names: list[str], sizes: tuple[int, ...], zoom: int, columns: int) -> QImage:
    from quartz_studio import icons

    small_w = max(sizes) + 6
    cell_w = zoom + small_w + 14
    label_h = 14
    cell_h = max(zoom, len(sizes) * (max(sizes) + 4)) + label_h + 10
    rows = math.ceil(len(names) / columns)
    img = QImage(cell_w * columns, cell_h * rows, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(theme.SURFACE_CARD))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(9)
    p.setFont(font)
    for i, name in enumerate(names):
        x, y = (i % columns) * cell_w, (i // columns) * cell_h
        p.setPen(QPen(QColor(theme.HAIRLINE), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x + 0.5, y + 0.5, cell_w - 1, cell_h - 1))
        icons.render(p, QRectF(x + 5, y + 5, zoom, zoom), name)
        sy = y + 5
        for s in sizes:
            icons.render(p, QRectF(x + zoom + 12, sy, s, s), name)
            sy += s + 4
        p.setPen(QColor(theme.TEXT_SECONDARY))
        p.drawText(QRectF(x, y + cell_h - label_h - 2, cell_w, label_h),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, cell_w - 4))
    p.end()
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description="Render every registered vector icon into a spritesheet PNG, a labelled preview, a contact sheet and a JSON map.")
    ap.add_argument("--out", default=os.path.join(os.path.expanduser("~"), "Downloads"))
    ap.add_argument("--cell", type=int, default=64)
    ap.add_argument("--columns", type=int, default=16)
    ap.add_argument("--sizes", default="16,20,26")
    ap.add_argument("--zoom", type=int, default=48)
    ap.add_argument("--contact-columns", type=int, default=9)
    ap.add_argument("--only", default="")
    ap.add_argument("--contact-out", default="")
    args = ap.parse_args()
    create_app([sys.argv[0]])
    names = load_all_icons()
    if args.only:
        prefixes = tuple(args.only.split(","))
        names = [n for n in names if n.startswith(prefixes)]
    os.makedirs(args.out, exist_ok=True)
    sizes = tuple(int(s) for s in args.sizes.split(",") if s)
    sheet = os.path.join(args.out, "quartz_icons_spritesheet.png")
    preview = os.path.join(args.out, "quartz_icons_preview.png")
    mapping = os.path.join(args.out, "quartz_icons_spritesheet.json")
    contact = args.contact_out or os.path.join(args.out, "quartz_icons_contact.png")
    render(names, args.cell, args.columns, False, None).save(sheet)
    render(names, args.cell, args.columns, True, theme.SURFACE_CARD).save(preview)
    contact_sheet(names, sizes, args.zoom, args.contact_columns).save(contact)
    frames = {n: {"x": (i % args.columns) * args.cell, "y": (i // args.columns) * args.cell,
                  "w": args.cell, "h": args.cell} for i, n in enumerate(names)}
    with open(mapping, "w", encoding="utf-8") as fh:
        json.dump({"cell": args.cell, "columns": args.columns, "count": len(names),
                   "frames": frames}, fh, indent=1, ensure_ascii=False)
    print(f"{len(names)} icons -> {sheet}\n{preview}\n{contact}\n{mapping}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
