from __future__ import annotations

import os
import sys

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QApplication, QWidget

from quartz_studio import icons, theme
from quartz_studio.app import create_app

_KEEP: list[QWidget] = []


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None or not app.property("qsTestThemed"):
        app = create_app([sys.argv[0]])
        app.setProperty("qsTestThemed", True)
    return app


def _settle(passes: int = 3) -> None:
    app = _app()
    for _ in range(passes):
        app.processEvents()


def _show(widget: QWidget, w: int = 480, h: int = 400) -> QWidget:
    widget.resize(w, h)
    widget.show()
    widget.activateWindow()
    _settle(4)
    _KEEP.append(widget)
    return widget


def _apply_overrides() -> None:
    from quartz_studio.ext import icon_overrides

    icon_overrides.apply()


def _dock_commands() -> dict[str, tuple[str, str | None]]:
    from quartz_studio.widgets import object_palette as op

    out: dict[str, tuple[str, str | None]] = {}
    items = {item.key: item for item in op.OBJECT_PALETTE_ENTRIES
             if hasattr(item, "foldout") and item.key}
    for key, ids in op.PALETTE_GROUPS:
        present = [i for i in ids if op._spec_entry(i) is not None]
        item = items.get(key)
        if item is None:
            continue
        assert len(item.foldout) == len(present), key
        for spec_id, cmd in zip(present, item.foldout):
            if spec_id == "empty_polygon":
                continue
            out[spec_id] = (cmd.icon, cmd.color)
    null = op._spec_entry("null")
    if null is not None:
        out["null"] = (null[0].icon, null[0].color)
    return out


def _png(image) -> bytes:
    return bytes(image.constBits()) if image.sizeInBytes() else b""


def test_every_registered_kind_uses_the_dock_icon_everywhere() -> None:
    _app()
    from quartz_studio import objects
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets import context_menu
    from quartz_studio.widgets.attribute_manager import AttributeManager
    from quartz_studio.widgets.object_manager import object_icon, object_icon_name

    _apply_overrides()
    dock = _dock_commands()
    assert dock
    checked = 0
    scene = reset_scene()
    am = _show(AttributeManager(), 480, 500)
    for spec in objects.all_specs():
        obj = scene.add_parametric(spec.id)
        _settle(1)
        row_name, row_color = object_icon(obj)
        assert row_name == object_icon_name(obj)
        assert am.header.icon_name() == row_name, spec.id
        assert am.header._icon_color == row_color, spec.id
        assert context_menu._spec_icon(spec) == row_name, spec.id
        if spec.id in dock:
            assert dock[spec.id] == (row_name, row_color), (spec.id, dock[spec.id], row_name)
            checked += 1
        assert icons.has(row_name), spec.id
    assert checked >= 40, checked
    for spec_id in ("subdivision_surface", "trunk", "cloner", "text", "circle", "cube"):
        assert spec_id in dock, spec_id


def test_polygon_objects_lines_and_nulls_keep_fixed_icons() -> None:
    _app()
    from quartz_studio.scene import Mesh, reset_scene
    from quartz_studio.widgets.object_manager import (LINE_OBJECT_ICON, OBJECT_ICON,
                                                      object_icon)

    scene = reset_scene()
    poly = scene.add_object("Poly", Mesh.cube(100.0))
    line = scene.new_line_object()
    null = scene.add_parametric("null")
    assert object_icon(poly) == (OBJECT_ICON, theme.ICON_MESH) == ("empty_polygon", theme.ICON_MESH)
    assert object_icon(line) == (LINE_OBJECT_ICON, None) == ("m_line", None)
    assert object_icon(null)[0] == "pal_null"
    from quartz_studio.widgets import menu_bar

    menu_bar.create_empty_polygon()
    empty = scene.active
    assert object_icon(empty) == ("empty_polygon", theme.ICON_MESH)
    empty.mesh = Mesh(np.zeros((2, 3)), [])
    assert object_icon(empty) == (LINE_OBJECT_ICON, None)
    made = scene.make_editable(scene.add_parametric("cube"))
    assert made.kind == "polygon"
    assert object_icon(made) == (OBJECT_ICON, theme.ICON_MESH)


def test_subdivision_surface_row_pixmap_equals_the_dock_button_pixmap() -> None:
    _app()
    from quartz_studio.scene import reset_scene
    from quartz_studio.widgets.object_manager import ObjectManager, object_icon
    from quartz_studio.widgets.object_palette import ObjectPalette

    _apply_overrides()
    scene = reset_scene()
    om = _show(ObjectManager())
    palette = _show(ObjectPalette(), 900, 80)
    sub = scene.add_parametric("subdivision_surface")
    _settle(3)
    name, color = object_icon(sub)
    assert name == "subdivision_surface"
    button = palette.buttons["Subdivision Surface"]
    assert button.icon_name() == name
    for size in (18, 24):
        dock_px = button.icon().pixmap(QSize(size, size)).toImage()
        row_px = icons.pixmap(name, size, color).toImage()
        assert dock_px.size() == row_px.size()
        assert _png(dock_px) == _png(row_px), size
    tree = om.tree
    item = tree.item_of(sub)
    rect = tree.visualItemRect(item)
    from quartz_studio.widgets.object_manager import ICON_LEFT, ICON_SIZE

    area = QRect(rect.left() + ICON_LEFT, rect.top() + (rect.height() - ICON_SIZE) // 2, ICON_SIZE, ICON_SIZE)
    shot = tree.viewport().grab().toImage().copy(area)
    from PySide6.QtGui import QImage, QPainter

    expected = QImage(ICON_SIZE, ICON_SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    expected.fill(shot.pixelColor(0, 0))
    painter = QPainter(expected)
    painter.drawPixmap(0, 0, icons.pixmap(name, ICON_SIZE, color))
    painter.end()
    assert shot.size() == expected.size()
    diff = 0
    for y in range(ICON_SIZE):
        for x in range(ICON_SIZE):
            a, b = shot.pixelColor(x, y), expected.pixelColor(x, y)
            diff += abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
    assert diff < 60, diff


def _run_as_script() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    tests.sort(key=lambda item: item[1].__code__.co_firstlineno)
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
