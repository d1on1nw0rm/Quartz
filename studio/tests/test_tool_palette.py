from __future__ import annotations

import hashlib
import logging
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from quartz_studio import icons, theme
from quartz_studio.app import create_app

NOT_IMPLEMENTED = "not implemented"
EXPECTED_GROUPS = ["Extrude", "Bevel", "Cut", "Bridge", "Dissolve", "Slide", "Normals", "Subdivide", "Clone"]
TRANSFORM_BUTTONS = ["Selection", "Move", "Rotate", "Scale", "Pen"]

_STATE: dict = {}


class _LogCapture(logging.Handler):

    def __init__(self, name: str = "quartz_studio") -> None:
        super().__init__(logging.DEBUG)
        self._logger = logging.getLogger(name)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())

    def __enter__(self) -> list[str]:
        self._old_level = self._logger.level
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self)
        return self.records

    def __exit__(self, *exc) -> None:
        self._logger.removeHandler(self)
        self._logger.setLevel(self._old_level)


class _Errors:

    def __enter__(self) -> list[str]:
        self.errors: list[str] = []
        self._old = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append(f"{kind.__name__}: {value}")
        return self.errors

    def __exit__(self, *exc) -> None:
        sys.excepthook = self._old


def _app() -> QApplication:
    if "app" not in _STATE:
        _STATE["app"] = create_app([sys.argv[0]])
    return _STATE["app"]


def _settle(passes: int = 4) -> None:
    for _ in range(passes):
        _app().processEvents()


def _window():
    if "window" in _STATE:
        return _STATE["window"]
    app = _app()
    from quartz_studio.main_window import MainWindow
    from quartz_studio.modeling import install as mi

    mi.prepare()
    win = MainWindow()
    mi.install(win)
    win.setMinimumSize(1, 1)
    win.resize(1920, 1010)
    win.show()
    _settle(6)
    win.apply_default_sizes()
    _settle(6)
    _STATE["window"] = win
    return win


def _fresh_cube():
    from quartz_studio.scene import Mesh, get_scene

    scene = get_scene()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_object("Cube", Mesh.cube(200.0))
    scene._undo.clear()
    scene._redo.clear()
    return scene


def _select_for(scene, spec) -> None:
    mode = next((m for m in ("polygons", "edges", "points") if m in spec.modes), spec.modes[0])
    scene.set_mode(mode)
    mesh = scene.active.mesh
    if mode == "polygons":
        scene.select_components([0])
    elif mode == "edges":
        scene.select_components(sorted(tuple(e) for e in mesh.edges)[:3])
    elif mode == "points":
        scene.select_components([0, 1])


def _tool_buttons(palette) -> list:
    from quartz_studio.widgets.tool_palette import TOOLS

    return list(palette.button_groups[TOOLS].buttons())


def _checked(palette) -> list:
    return [b for b in _tool_buttons(palette) if b.isChecked()]


def _mesh_ids() -> list[str]:
    from quartz_studio.modeling import get_tool, tool_ids

    return [i for i in tool_ids() if get_tool(i).menu == "Mesh"]


def _entry_action(button, name: str):
    menu = button.build_menu()
    for action in menu.actions():
        if action.text() == name:
            return menu, action
    raise AssertionError(f"{name!r} not in the fold-out of {button.command_text()!r}")


def test_palette_lists_transform_tools_then_the_groups() -> None:
    palette = _window().tool_palette
    assert list(palette.buttons) == TRANSFORM_BUTTONS + EXPECTED_GROUPS
    assert palette.width() == theme.RAIL_W == theme.PALETTE_BUTTON + 2 * theme.RAIL_PAD


def test_every_mesh_tool_is_in_exactly_one_group() -> None:
    from quartz_studio.modeling import get_tool
    from quartz_studio.modeling.install import MORE_GROUP, PALETTE_GROUPS, palette_groups

    groups = palette_groups()
    seen: list[str] = []
    for group in groups:
        seen.extend(spec.id for spec in group.specs)
    assert sorted(seen) == sorted(_mesh_ids())
    assert len(seen) == len(set(seen))
    assert [g.name for g in groups] == EXPECTED_GROUPS
    assert MORE_GROUP not in [g.name for g in groups]
    table = [i for _name, ids in PALETTE_GROUPS for i in ids]
    assert len(table) == len(set(table))
    assert all(get_tool(i).menu == "Mesh" for i in table)
    palette = _window().tool_palette
    names: list[str] = []
    for group in groups:
        button = palette.buttons[group.name]
        if len(group.specs) > 1:
            menu = button.build_menu()
            names.extend(a.text() for a in menu.actions())
            menu.deleteLater()
        else:
            names.append(button.command_text())
    assert sorted(names) == sorted(get_tool(i).name for i in _mesh_ids())


def test_unlisted_tool_goes_to_the_last_group() -> None:
    from quartz_studio.modeling.meshkit import OpResult
    from quartz_studio.modeling.install import MORE_GROUP, palette_groups
    from quartz_studio.modeling.registry import TOOLS, ToolSpec, register
    from quartz_studio.widgets.tool_palette import modeling_entries

    spec = register(ToolSpec("zz_palette_probe", "Probe", lambda m, s, v: OpResult(m, s, True, "")))
    try:
        groups = palette_groups()
        assert groups[-1].name == MORE_GROUP
        assert [s.id for s in groups[-1].specs] == ["zz_palette_probe"]
        flat = [s.id for g in groups for s in g.specs]
        assert len(flat) == len(set(flat))
        entries = modeling_entries(groups)
        assert entries[-1].key == MORE_GROUP and spec.name == entries[-1].cmd.name
    finally:
        del TOOLS["zz_palette_probe"]
    assert [g.name for g in palette_groups()] == EXPECTED_GROUPS


def test_foldout_entries_show_icon_and_name() -> None:
    from quartz_studio.modeling import get_tool
    from quartz_studio.modeling.install import palette_groups

    palette = _window().tool_palette
    for group in palette_groups():
        button = palette.buttons[group.name]
        assert button.group() or len(group.specs) == 1
        if len(group.specs) == 1:
            assert not button.group()
            continue
        menu = button.build_menu()
        actions = menu.actions()
        assert [a.text() for a in actions] == [s.name for s in group.specs]
        assert all(not a.icon().isNull() for a in actions)
        menu.deleteLater()
    assert get_tool("extrude").name == "Extrude"


def test_tooltips_carry_name_and_shortcut() -> None:
    from quartz_studio.modeling.install import palette_groups, tool_tooltip

    palette = _window().tool_palette
    for group in palette_groups():
        button = palette.buttons[group.name]
        for spec in group.specs:
            button.show_command(spec.name)
            tip = button.toolTip()
            assert tip == tool_tooltip(spec), (tip, spec.name)
            assert tip.startswith(spec.name)
            if spec.shortcut:
                assert tip.endswith(f"({spec.shortcut})"), tip
        button.show_command(group.specs[0].name)
    assert palette.buttons["Extrude"].toolTip() == "Extrude (M~T)"
    assert palette.buttons["Bevel"].toolTip() == "Bevel (M~S)"


def test_clicking_each_entry_activates_or_runs_the_tool() -> None:
    from quartz_studio.modeling import install as mi
    from quartz_studio.modeling.install import palette_groups
    from quartz_studio.scene import get_scene

    win = _window()
    palette = win.tool_palette
    scene = get_scene()
    ran = 0
    with _LogCapture() as records, _Errors() as errors:
        for group in palette_groups():
            button = palette.buttons[group.name]
            for spec in group.specs:
                _fresh_cube()
                _select_for(scene, spec)
                scene.set_tool("move")
                _settle(2)
                if len(group.specs) > 1:
                    menu, action = _entry_action(button, spec.name)
                    action.trigger()
                    menu.deleteLater()
                else:
                    button.click()
                _settle(2)
                ran += 1
                assert button.command_text() == spec.name, spec.id
                assert button.icon_name() == icons.modeling_icon_name(spec.id), spec.id
                assert mi.controller().tool_id == spec.id, (spec.id, mi.controller().tool_id)
                assert scene.tool == spec.id, (spec.id, scene.tool)
                if spec.interactive:
                    assert _checked(palette) == [button], spec.id
                    assert win.tool_options.isVisible(), spec.id
                else:
                    assert _checked(palette) == [], spec.id
                scene.set_tool("move")
                _settle(1)
    assert ran == len(_mesh_ids())
    assert not [r for r in records if NOT_IMPLEMENTED in r], records
    assert not errors, errors


def test_command_tools_change_the_mesh_and_do_not_stay_checked() -> None:
    from quartz_studio.scene import get_scene

    win = _window()
    palette = win.tool_palette
    scene = get_scene()
    _fresh_cube()
    scene.set_mode("polygons")
    scene.select_components([0])
    scene.set_tool("move")
    before = len(scene.active.mesh.polygons)
    menu, action = _entry_action(palette.buttons["Subdivide"], "Triangulate")
    action.trigger()
    menu.deleteLater()
    _settle()
    assert len(scene.active.mesh.polygons) > before
    assert _checked(palette) == []
    button = palette.buttons["Subdivide"]
    assert button.command_text() == "Triangulate"
    button.click()
    _settle()
    assert _checked(palette) == []
    scene.set_tool("move")
    _settle()


def test_group_button_remembers_the_last_tool() -> None:
    from quartz_studio.scene import get_scene

    win = _window()
    palette = win.tool_palette
    scene = get_scene()
    _fresh_cube()
    scene.set_mode("polygons")
    scene.select_components([0])
    button = palette.buttons["Extrude"]
    scene.set_tool("move")
    _settle()
    menu, action = _entry_action(button, "Inset")
    action.trigger()
    menu.deleteLater()
    _settle()
    assert button.command_text() == "Inset" and button.icon_name() == "mt_inset"
    assert scene.tool == "inset" and button.isChecked()
    palette.buttons["Move"].click()
    _settle()
    assert scene.tool == "move" and not button.isChecked()
    assert button.command_text() == "Inset" and button.icon_name() == "mt_inset"
    button.click()
    _settle()
    assert scene.tool == "inset" and button.isChecked()
    menu, action = _entry_action(button, "Thicken")
    action.trigger()
    menu.deleteLater()
    _settle()
    assert button.command_text() == "Thicken" and scene.tool == "thicken"
    scene.set_tool("inset")
    _settle()
    assert button.command_text() == "Inset" and button.isChecked()
    scene.set_tool("move")
    _settle()


def test_extrude_foldout_ends_with_trunk() -> None:
    from quartz_studio import icons
    from quartz_studio.modeling import get_tool

    palette = _window().tool_palette
    button = palette.buttons["Extrude"]
    menu, action = _entry_action(button, "Trunk")
    names = [a.text() for a in menu.actions()]
    assert names == ["Extrude", "Inset", "Matrix Extrude", "Smooth Shift", "Thicken", "Trunk"], names
    assert not action.icon().isNull() and icons.has("mt_trunk")
    assert get_tool("trunk").menu == "Mesh" and get_tool("trunk").modes == ("edges", "points")
    menu.deleteLater()


def test_exclusive_with_the_transform_tools() -> None:
    from quartz_studio.scene import get_scene

    win = _window()
    palette = win.tool_palette
    scene = get_scene()
    _fresh_cube()
    scene.set_mode("polygons")
    scene.select_components([0])
    for name in ("Selection", "Move", "Rotate", "Scale"):
        palette.buttons["Bevel"].click()
        _settle()
        assert _checked(palette) == [palette.buttons["Bevel"]]
        palette.buttons[name].click()
        _settle()
        assert _checked(palette) == [palette.buttons[name]], name
        assert not palette.buttons["Bevel"].isChecked()
    palette.buttons["Extrude"].click()
    _settle()
    assert _checked(palette) == [palette.buttons["Extrude"]]
    palette.buttons["Pen"].click()
    _settle()
    assert _checked(palette) == [palette.buttons["Pen"]]
    assert scene.tool in ("line_pen", "pen")
    palette.buttons["Cut"].click()
    _settle()
    assert _checked(palette) == [palette.buttons["Cut"]]
    palette.buttons["Bevel"].click()
    _settle()
    assert _checked(palette) == [palette.buttons["Bevel"]]
    assert not palette.buttons["Cut"].isChecked()
    palette.buttons["Move"].click()
    _settle()
    assert scene.tool == "move" and _checked(palette) == [palette.buttons["Move"]]


def test_scene_tool_changes_check_the_group_button() -> None:
    from quartz_studio.scene import get_scene

    win = _window()
    palette = win.tool_palette
    scene = get_scene()
    _fresh_cube()
    scene.set_tool("bevel")
    _settle()
    assert _checked(palette) == [palette.buttons["Bevel"]]
    scene.set_tool("slide")
    _settle()
    assert _checked(palette) == [palette.buttons["Slide"]]
    assert palette.buttons["Slide"].command_text() == "Slide"
    scene.set_tool("select")
    _settle()
    assert _checked(palette) == [palette.buttons["Selection"]]
    scene.set_tool("move")
    _settle()


def _fully_visible(palette, button) -> bool:
    area = palette._scroll.viewport()
    top = button.mapTo(area, QPoint(0, 0))
    return top.y() >= 0 and top.y() + button.height() <= area.height()


def _reachable(palette) -> set[str]:
    bar = palette.scroll_bar()
    seen: set[str] = set()
    for value in range(bar.minimum(), bar.maximum() + 1, 6):
        bar.setValue(value)
        _settle(1)
        seen.update(k for k, b in palette.buttons.items() if _fully_visible(palette, b))
    bar.setValue(bar.maximum())
    _settle(1)
    seen.update(k for k, b in palette.buttons.items() if _fully_visible(palette, b))
    bar.setValue(bar.minimum())
    _settle(1)
    return seen


def _sized_window(width: int, height: int):
    from quartz_studio.main_window import MainWindow

    win = MainWindow()
    win.setMinimumSize(1, 1)
    win.resize(width, height)
    win.show()
    _settle(6)
    win.apply_default_sizes()
    _settle(6)
    return win


def _gaps(palette) -> list[int]:
    buttons = list(palette.buttons.values())
    ys = [b.mapTo(palette.strip, QPoint(0, 0)).y() for b in buttons]
    return [ys[i + 1] - ys[i] - buttons[i].height() for i in range(len(ys) - 1)]


def test_palette_is_fully_visible_at_1080_pixels() -> None:
    from quartz_studio.widgets.tool_palette import DIVIDER_HEIGHT, TOOL_GAP

    win = _sized_window(1920, 1080)
    try:
        palette = win.tool_palette
        assert not palette.arrows_visible()
        assert palette.scroll_bar().maximum() == 0
        assert all(_fully_visible(palette, b) for b in palette.buttons.values())
        gaps = _gaps(palette)
        assert min(gaps) >= TOOL_GAP
        assert gaps[4] == DIVIDER_HEIGHT and DIVIDER_HEIGHT > TOOL_GAP
        assert all(g == TOOL_GAP for k, g in enumerate(gaps) if k != 4), gaps
    finally:
        win.close()
        win.deleteLater()
        _settle()


def test_palette_is_usable_at_720_pixels() -> None:
    from quartz_studio.widgets.tool_palette import TOOL_MIN_GAP

    win = _sized_window(1280, 720)
    try:
        palette = win.tool_palette
        assert _reachable(palette) == set(palette.buttons)
        assert min(_gaps(palette)) >= TOOL_MIN_GAP
        if not palette.arrows_visible():
            assert all(_fully_visible(palette, b) for b in palette.buttons.values())
        for name in ("Bevel", "Clone"):
            assert palette.buttons[name].isVisibleTo(win)
    finally:
        win.close()
        win.deleteLater()
        _settle()


def _standalone(height: int):
    from quartz_studio.widgets.tool_palette import ToolPalette

    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    palette = ToolPalette(host)
    lay.addWidget(palette)
    host.setMinimumSize(1, 1)
    host.resize(120, height)
    host.show()
    _settle(6)
    _STATE.setdefault("hosts", []).append(host)
    return host, palette


def test_short_palette_scrolls_with_arrows_and_wheel() -> None:
    from quartz_studio.widgets.tool_palette import SCROLL_STEP, TOOL_MIN_GAP

    host, palette = _standalone(320)
    assert palette.height() <= 320
    assert palette.arrows_visible()
    assert min(_gaps(palette)) == TOOL_MIN_GAP
    bar = palette.scroll_bar()
    assert bar.maximum() > 0 and bar.value() == 0
    assert not palette._up.isEnabled() and palette._down.isEnabled()
    assert _reachable(palette) == set(palette.buttons)
    palette._down.click()
    _settle(1)
    assert bar.value() == min(SCROLL_STEP, bar.maximum())
    palette._up.click()
    _settle(1)
    assert bar.value() == 0
    target = palette._scroll.viewport()
    before = bar.value()
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(target, event)
    _settle(1)
    assert bar.value() > before
    bar.setValue(bar.maximum())
    _settle(1)
    assert palette._down.isEnabled() is False and palette._up.isEnabled()
    assert _fully_visible(palette, palette.buttons["Clone"])
    host.resize(120, 900)
    _settle(6)
    assert not palette.arrows_visible() and bar.maximum() == 0
    assert all(_fully_visible(palette, b) for b in palette.buttons.values())
    assert min(_gaps(palette)) >= 10


def test_scrolled_button_still_runs_its_tool() -> None:
    from quartz_studio.scene import get_scene

    _window()
    host, palette = _standalone(320)
    bar = palette.scroll_bar()
    bar.setValue(bar.maximum())
    _settle(2)
    scene = get_scene()
    _fresh_cube()
    scene.set_mode("polygons")
    scene.select_components([0])
    button = palette.buttons["Clone"]
    assert _fully_visible(palette, button)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     button.rect().center())
    _settle(2)
    assert button.command_text() == "Array" and scene.tool == "array"
    scene.set_tool("move")
    _settle(2)


def _pixels(name: str, size: int = 31) -> np.ndarray:
    img = icons.pixmap(name, size, None).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    arr = np.frombuffer(bytes(img.constBits()), dtype=np.uint8).reshape(img.height(), img.width(), 4)
    return arr.astype(np.int16)


def test_every_mesh_tool_has_its_own_registered_icon() -> None:
    _app()
    ids = _mesh_ids()
    painted = set(icons.modeling_icon_ids())
    assert set(ids) <= painted, sorted(set(ids) - painted)
    for tool_id in ids:
        assert icons.has(icons.modeling_icon_name(tool_id)), tool_id


def test_icons_are_not_empty_and_use_the_accent() -> None:
    _app()
    for tool_id in _mesh_ids():
        arr = _pixels(icons.modeling_icon_name(tool_id))
        blue, green, red, alpha = (arr[:, :, k] for k in range(4))
        assert int((alpha > 40).sum()) >= 60, f"{tool_id}: nearly empty"
        assert int((alpha > 40).sum()) <= 31 * 31 * 0.8, f"{tool_id}: fills the cell"
        orange = (red > 190) & (green > 110) & (green < 190) & (blue < 110) & (alpha > 200)
        assert int(orange.sum()) >= 8, f"{tool_id}: no accent colour"
        grey = (abs(red - green) < 20) & (abs(green - blue) < 20) & (alpha > 120)
        assert int(grey.sum()) >= 8, f"{tool_id}: no grey shape"


def test_no_two_tools_share_an_icon() -> None:
    _app()
    ids = _mesh_ids()
    names = [icons.modeling_icon_name(i) for i in ids]
    digests = {}
    for tool_id, name in zip(ids, names):
        digest = hashlib.sha1(_pixels(name).tobytes()).hexdigest()
        assert digest not in digests, f"{tool_id} duplicates {digests[digest]}"
        digests[digest] = tool_id
    stack = {i: _pixels(n).astype(np.int32) for i, n in zip(ids, names)}
    stack["move"] = _pixels("pal_move").astype(np.int32)
    stack["rotate"] = _pixels("pal_rotate").astype(np.int32)
    stack["scale"] = _pixels("pal_scale").astype(np.int32)
    stack["pen"] = _pixels("pal_pen").astype(np.int32)
    stack["select"] = _pixels("pal_live_selection").astype(np.int32)
    keys = list(stack)
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            diff = np.abs(stack[keys[a]] - stack[keys[b]]).sum(axis=2)
            assert int((diff > 90).sum()) >= 25, f"{keys[a]} and {keys[b]} look the same"


def test_palette_buttons_use_the_tool_icons() -> None:
    from quartz_studio.modeling.install import palette_groups

    palette = _window().tool_palette
    for group in palette_groups():
        button = palette.buttons[group.name]
        current = next(s for s in group.specs if s.name == button.command_text())
        assert button.icon_name() == icons.modeling_icon_name(current.id)
        for name, text in button.group():
            assert name.startswith(icons.MODELING_ICON_PREFIX) and text


def test_command_tool_leaves_no_tool_and_selecting_an_object_brings_move_back() -> None:
    from quartz_studio.scene import get_scene

    win = _window()
    palette = win.tool_palette
    scene = get_scene()
    _fresh_cube()
    scene.set_mode("polygons")
    scene.select_components([0])
    scene.set_tool("move")
    for group, name in (("Subdivide", "Triangulate"), ("Subdivide", "Subdivide"),
                        ("Normals", "Reverse Normals"), ("Dissolve", "Dissolve")):
        _fresh_cube()
        scene.set_mode("polygons")
        scene.select_components([0])
        scene.set_tool("move")
        menu, action = _entry_action(palette.buttons[group], name)
        action.trigger()
        menu.deleteLater()
        _settle(2)
        assert _checked(palette) == [], name
        other = scene.add_object("Second", activate=False)
        scene.set_active(other)
        _settle(2)
        assert scene.tool == "move" and _checked(palette) == [palette.buttons["Move"]], (name, scene.tool)
    scene.set_tool("move")


def test_tool_is_refused_at_the_click_on_a_parametric_object_without_changing_the_mode() -> None:
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import get_scene

    win = _window()
    palette = win.tool_palette
    scene = get_scene()
    _fresh_cube()
    for obj in list(scene.objects):
        scene.remove_object(obj)
    scene.add_parametric("cube")
    messages: list[str] = []
    mi.controller().message.connect(messages.append)
    try:
        for group, name in (("Extrude", "Extrude"), ("Bevel", "Bevel"), ("Dissolve", "Dissolve"),
                            ("Dissolve", "Collapse"), ("Clone", "Mirror")):
            scene.set_mode("model")
            scene.set_tool("move")
            _settle(1)
            del messages[:]
            if group == "Bevel":
                palette.buttons[group].click()
            else:
                menu, action = _entry_action(palette.buttons[group], name)
                action.trigger()
                menu.deleteLater()
            _settle(2)
            assert messages == [f"{name}: Make Editable first"], (name, messages)
            assert scene.mode == "model" and scene.tool == "move", (name, scene.mode, scene.tool)
            assert mi.controller().tool_id is None, name
            assert _checked(palette) == [palette.buttons["Move"]], name
    finally:
        mi.controller().message.disconnect(messages.append)
        scene.set_tool("move")


def _close_enough(color, hex_value: str, tol: int = 6) -> bool:
    from PySide6.QtGui import QColor

    want = QColor(hex_value)
    return (abs(color.red() - want.red()) <= tol and abs(color.green() - want.green()) <= tol
            and abs(color.blue() - want.blue()) <= tol)


def _dividers(widget, cls_name: str) -> list:
    return [w for w in widget.findChildren(QWidget) if type(w).__name__ == cls_name]


def test_rail_buttons_use_the_crystal_look() -> None:
    win = _window()
    palette = win.tool_palette
    assert palette.property("qsCard")
    move = palette.buttons["Move"]
    assert move.isChecked()
    assert move.iconSize().width() == theme.PALETTE_ICON
    assert move.width() == move.height() == theme.PALETTE_BUTTON
    for button in palette.buttons.values():
        assert button.group_mark_color == theme.TEXT_SECONDARY
        assert button.iconSize().width() == theme.PALETTE_ICON
    image = win.grab().toImage()
    top_left = move.mapTo(win, QPoint(3, move.height() // 2))
    assert _close_enough(image.pixelColor(top_left), theme.ACCENT_TINT), image.pixelColor(top_left).name()
    rest = palette.buttons["Rotate"]
    spot = rest.mapTo(win, QPoint(3, rest.height() // 2))
    assert _close_enough(image.pixelColor(spot), theme.SURFACE_CARD), image.pixelColor(spot).name()


def test_rail_divider_is_a_hairline() -> None:
    from quartz_studio.widgets.tool_palette import DIVIDER_INSET

    win = _window()
    palette = win.tool_palette
    found = _dividers(palette, "_Divider")
    assert len(found) == 1
    divider = found[0]
    image = win.grab().toImage()
    y = divider.height() // 2
    centre = image.pixelColor(divider.mapTo(win, QPoint(divider.width() // 2, y)))
    assert _close_enough(centre, theme.HAIRLINE, 3), centre.name()
    outside = image.pixelColor(divider.mapTo(win, QPoint(DIVIDER_INSET - 1, y)))
    assert _close_enough(outside, theme.SURFACE_CARD), outside.name()
    above = image.pixelColor(divider.mapTo(win, QPoint(divider.width() // 2, y - 2)))
    assert _close_enough(above, theme.SURFACE_CARD), above.name()


def _popup_rect(button) -> tuple:
    from PySide6.QtCore import QRect

    menu = button.build_menu()
    pos = button._popup_pos(menu)
    rect = QRect(pos, menu.sizeHint())
    win = button.window()
    area = QRect(win.mapToGlobal(QPoint(0, 0)), win.size())
    menu.deleteLater()
    return rect, area


def test_dock_is_a_floating_row_with_hairline_dividers_and_upward_foldouts() -> None:
    from PySide6.QtCore import QRect

    from quartz_studio.widgets.object_palette import OBJECT_PALETTE_ENTRIES

    win = _window()
    dock = win.object_palette
    assert dock.floating and dock.popup_side == "above"
    assert dock.height() == theme.DOCK_H
    assert len(_dividers(dock, "_DockDivider")) == OBJECT_PALETTE_ENTRIES.count("gap") == 2
    image = win.grab().toImage()
    for divider in _dividers(dock, "_DockDivider"):
        assert divider.width() == theme.DOCK_GAP and divider.height() == 24
        pixel = image.pixelColor(divider.mapTo(win, QPoint(divider.width() // 2, divider.height() // 2)))
        assert _close_enough(pixel, theme.HAIRLINE, 40), pixel.name()
    folding = [b for b in dock.buttons.values() if b.group()]
    assert len(folding) == 8
    for button in folding:
        rect, area = _popup_rect(button)
        assert area.contains(rect), (button.command_text(), rect, area)
        top = button.mapToGlobal(QPoint(0, 0)).y()
        assert rect.bottom() < top, (button.command_text(), rect, top)
        assert button.popup_side() == "above"
    assert QRect(0, 0, win.width(), win.height()).contains(dock.geometry().translated(
        dock.parentWidget().mapTo(win, QPoint(0, 0))))


def test_rail_foldouts_stay_inside_the_window_at_720_pixels() -> None:
    win = _sized_window(1280, 720)
    try:
        palette = win.tool_palette
        for button in palette.buttons.values():
            if not button.group() or not button.isVisibleTo(win):
                continue
            rect, area = _popup_rect(button)
            assert area.contains(rect), (button.command_text(), rect, area)
            assert rect.left() > button.mapToGlobal(QPoint(0, 0)).x()
    finally:
        win.close()
        win.deleteLater()
        _settle()


def test_tool_icons_are_flat_strokes_with_one_citrine_part() -> None:
    _app()
    for name in ("pal_live_selection", "pal_move", "pal_rotate", "pal_scale", "pal_pen"):
        arr = _pixels(name, 48)
        blue, green, red, alpha = (arr[:, :, k] for k in range(4))
        solid = alpha > 200
        assert int(solid.sum()) >= 40, name
        citrine = (abs(red - 255) < 30) & (abs(green - 181) < 30) & (abs(blue - 61) < 40) & solid
        neutral = (abs(red - 207) < 25) & (abs(green - 213) < 25) & (abs(blue - 225) < 25) & solid
        assert int(citrine.sum()) >= 8, f"{name}: no tool tint"
        assert int(neutral.sum()) >= 20, f"{name}: no neutral stroke"
        other = solid & ~citrine & ~neutral
        assert int(other.sum()) < int(solid.sum()) * 0.5, f"{name}: stray colours"


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
