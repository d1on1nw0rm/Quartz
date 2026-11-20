from __future__ import annotations

import argparse
import os
import sys

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse_size(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid size {text!r}, expected WxH") from exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render the Quartz Studio main window offscreen and save it as a PNG.")
    ap.add_argument("--out", required=True, help="output PNG path")
    ap.add_argument("--size", type=_parse_size, default=(1920, 1010),
                    help="window size WxH in pixels (default 1920x1010)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="render at size*scale real pixels, then downscale to size (default 1.0)")
    ap.add_argument("--settle", type=int, default=6, help="event-loop passes before grabbing")
    args = ap.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if STUDIO_ROOT not in sys.path:
        sys.path.insert(0, STUDIO_ROOT)

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap

    from quartz_studio.app import create_app
    from quartz_studio.main_window import MainWindow

    app = create_app([sys.argv[0]])
    out_w, out_h = args.size
    real_w, real_h = round(out_w * args.scale), round(out_h * args.scale)

    win = MainWindow()
    win.setMinimumSize(1, 1)
    win.resize(real_w, real_h)
    win.show()
    for _ in range(max(1, args.settle)):
        app.processEvents()
    win.apply_default_sizes()
    for _ in range(max(1, args.settle)):
        app.processEvents()

    pm: QPixmap = win.grab()
    if pm.width() != out_w or pm.height() != out_h:
        pm = pm.scaled(out_w, out_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    if not pm.save(args.out, "PNG"):
        print(f"error: could not save {args.out}", file=sys.stderr)
        return 1
    print(f"snapshot: {args.out} ({pm.width()}x{pm.height()}, window rendered at {real_w}x{real_h})")
    win.close()
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
