from __future__ import annotations

import logging
import os
import re
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import quartz_studio
from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtWidgets import QAbstractButton, QApplication, QCheckBox, QComboBox, QLabel, QWidget

from quartz_studio.app import create_app

CLIENT_REAL = (1920, 1007)
SMALL_CLIENT = (1280, 720)

REGION_NAMES = ["menu_bar", "command_bar", "tool_palette", "viewport", "object_palette",
                "object_manager", "attribute_manager", "coordinates", "status_bar"]

RIGHT_COLUMN = ["object_manager", "attribute_manager", "coordinates"]

REMOVED_WIDGETS = {"TitleRow", "SculptBar", "PanelMenuBar"}

TOOL_BUTTONS = ["Selection", "Move", "Rotate", "Scale", "Pen", "Extrude", "Bevel", "Cut",
                "Bridge", "Dissolve", "Slide", "Normals", "Subdivide", "Clone"]

PALETTE_BUTTONS = ["Line", "Null", "Rectangle", "Circle", "Cube", "Sphere", "Text",
                   "Subdivision Surface", "Extrude", "Voronoi Fracture"]

COMMAND_BUTTONS = ["Points", "Edges", "Polygons", "Model", "Undo", "Redo", "Make Editable"]

REQUIRED_TEXTS = (
    "Objects",
    "Attributes",
    "Undo",
    "Make Editable",
    "Cube",
    "Reset Transformation",
    "Mode: Model · Tool: Move",
    "Drag to move · Hold Ctrl to copy · Esc cancels",
    "Untitled",
)

_WINDOW = None


class _FakeDialogs:

    def __init__(self, folder: str) -> None:
        from quartz_studio import project

        self.project = project
        self.folder = folder
        self.messages: list[tuple[str, str]] = []
        self.quits = 0
        self._saved = {}
        self.counter = 0

    def choose_open_files(self, title, directory, filters, multiple=False):
        return []

    def choose_save_file(self, title, path, filters):
        self.counter += 1
        found = re.search(r"\*(\.[A-Za-z0-9_]+)", filters[0])
        return os.path.join(self.folder, f"guard{self.counter}{found.group(1)}")

    def ask_save_changes(self, name):
        return "discard"

    def show_message(self, kind, text):
        self.messages.append((kind, text))

    def quit_application(self):
        self.quits += 1

    def __enter__(self):
        names = ("choose_open_files", "choose_save_file", "ask_save_changes", "show_message",
                 "quit_application")
        for name in names:
            self._saved[name] = getattr(self.project, name)
            setattr(self.project, name, getattr(self, name))
        self._saved["SETTINGS_FILE"] = self.project.SETTINGS_FILE
        self.project.SETTINGS_FILE = os.path.join(self.folder, "settings.ini")
        return self

    def __exit__(self, *exc) -> None:
        for name, value in self._saved.items():
            setattr(self.project, name, value)


class _LogCapture(logging.Handler):

    def __init__(self, name: str) -> None:
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


def _app() -> QApplication:
    return create_app([sys.argv[0]])


def _settle(app: QApplication, passes: int = 6) -> None:
    for _ in range(passes):
        app.processEvents()


def _window():
    global _WINDOW
    if _WINDOW is None:
        app = _app()
        from quartz_studio.main_window import MainWindow

        win = MainWindow()
        win.setMinimumSize(1, 1)
        win.resize(*CLIENT_REAL)
        win.show()
        _settle(app)
        win.apply_default_sizes()
        _settle(app)
        _WINDOW = win
    return _WINDOW


def _sized_window(width: int, height: int):
    from quartz_studio.main_window import MainWindow

    app = _app()
    win = MainWindow()
    win.setMinimumSize(1, 1)
    win.resize(width, height)
    win.show()
    _settle(app)
    win.apply_default_sizes()
    _settle(app)
    return win


def _close(win) -> None:
    win.close()
    win.deleteLater()
    _settle(_app())


def _rect(win: QWidget, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(win, QPoint(0, 0)), widget.size())


def _layout_errors(win, width: int, height: int) -> list[str]:
    from quartz_studio import theme

    errors: list[str] = []
    m, gap = theme.WINDOW_MARGIN, theme.CARD_GAP
    top_h, status_h = theme.TOP_BAR_H, theme.STATUS_BAR_H
    body_top, body_bottom = top_h, height - status_h
    r = {name: _rect(win, win.regions[name]) for name in REGION_NAMES}

    def expect(label: str, got: int, wanted: int, tol: int = 1) -> None:
        if abs(got - wanted) > tol:
            errors.append(f"{label}: expected {wanted}, got {got}")

    for name in ("menu_bar", "command_bar"):
        expect(f"{name} top", r[name].top(), (top_h - r[name].height()) // 2)
        expect(f"{name} bottom", r[name].bottom() + 1, top_h - (top_h - r[name].height()) // 2)
    expect("menu_bar left", r["menu_bar"].left(), m)
    expect("command_bar right", r["command_bar"].right() + 1, width - m)
    if r["menu_bar"].right() >= r["command_bar"].left():
        errors.append("menu_bar overlaps command_bar")
    bar = win.regions["command_bar"]
    modes = _rect(win, bar.mode_switcher)
    expect("mode switcher centre", round(modes.left() + modes.width() / 2), width // 2, 2)
    right_group = [bar.buttons[n] for n in ("Undo", "Redo", "Make Editable")] + [bar.project_chip]
    for widget in right_group:
        wr = _rect(win, widget)
        if not widget.isVisibleTo(win) or wr.left() <= modes.right() or wr.right() >= width - m + 1:
            errors.append(f"top bar: {widget.objectName()} misplaced at {wr}")
    lefts = [_rect(win, w).left() for w in right_group]
    if lefts != sorted(lefts):
        errors.append(f"top bar right group out of order: {lefts}")
    expect("project chip right", _rect(win, bar.project_chip).right() + 1, width - m)

    rail, view = r["tool_palette"], r["viewport"]
    expect("rail left", rail.left(), m)
    expect("rail width", rail.width(), theme.RAIL_W, 0)
    expect("viewport left", view.left(), rail.right() + 1 + gap)
    for name in ("tool_palette", "viewport", "object_manager"):
        expect(f"{name} top", r[name].top(), body_top)
    for name in ("tool_palette", "viewport", "coordinates"):
        expect(f"{name} bottom", r[name].bottom() + 1, body_bottom)
    column = [win.manager_splitter.widget(i) for i in range(win.manager_splitter.count())]
    column = [w for w in column if not w.isHidden()]
    expect("right column left", r["object_manager"].left(), view.right() + 1 + gap)
    for upper, lower in zip(column, column[1:]):
        expect(f"gap above {lower.objectName()}", _rect(win, lower).top(), _rect(win, upper).bottom() + 1 + gap)
    for widget in column:
        expect(f"{widget.objectName()} right", _rect(win, widget).right() + 1, width - m)
        if widget.height() < 40:
            errors.append(f"{widget.objectName()} squeezed to {widget.height()} px")

    status = r["status_bar"]
    expect("status left", status.left(), 0, 0)
    expect("status right", status.right() + 1, width, 0)
    expect("status top", status.top(), body_bottom, 0)
    expect("status bottom", status.bottom() + 1, height, 0)

    dock = r["object_palette"]
    palette = win.regions["object_palette"]
    area = win.dock_area()
    area = QRect(palette.parentWidget().mapTo(win, area.topLeft()), area.size())
    expect("dock centre", dock.left() + dock.width() // 2, area.left() + area.width() // 2, 1)
    expect("dock bottom", dock.bottom() + 1, area.bottom() + 1 - theme.DOCK_BOTTOM, 0)
    expect("dock height", dock.height(), theme.DOCK_H, 0)
    if dock.width() > area.width() - 2 * theme.SPACE_3:
        errors.append(f"dock wider than the viewport: {dock.width()} > {area.width()}")
    if not view.contains(dock):
        errors.append(f"dock {dock} leaves the viewport {view}")
    header = getattr(win.regions["viewport"], "menu_bar", None)
    if header is not None and dock.intersects(_rect(win, header)):
        errors.append("dock covers the viewport header")
    if palette.parentWidget() is not win.regions["viewport"]:
        errors.append("dock is not a child of the viewport")
    for key, button in palette.buttons.items():
        if not button.isVisibleTo(win) or not dock.contains(_rect(win, button)):
            errors.append(f"dock button {key} clipped")

    solid = [n for n in REGION_NAMES if n != "object_palette"]
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if r[a].intersects(r[b]):
                errors.append(f"{a} overlaps {b}")
    for name in REGION_NAMES:
        if not win.rect().contains(r[name]):
            errors.append(f"{name} {r[name]} leaves the window")
    return errors


def _texts_of(widget: QWidget) -> set[str]:
    out: set[str] = set()
    for getter in ("text", "title", "accessibleName", "windowTitle", "toolTip"):
        fn = getattr(widget, getter, None)
        if callable(fn):
            try:
                value = fn()
            except TypeError:
                continue
            if isinstance(value, str) and value:
                out.add(value)
    for action in widget.actions():
        out.update(t for t in (action.text(), action.toolTip()) if t)
    for value in vars(widget).values():
        if isinstance(value, str) and value:
            out.add(value)
    return out


def _all_texts(win: QWidget) -> set[str]:
    texts: set[str] = set()
    for w in [win, *win.findChildren(QWidget)]:
        texts |= _texts_of(w)
    return texts



def test_window_builds_without_placeholders() -> None:
    from quartz_studio import WINDOW_TITLE
    from quartz_studio.main_window import REGIONS, Placeholder

    win = _window()
    assert win.windowTitle() == WINDOW_TITLE == "Untitled - Quartz"
    assert set(win.regions) == set(REGIONS)
    missing = [name for name, w in win.regions.items() if isinstance(w, Placeholder)]
    assert not missing, f"regions fell back to placeholders: {missing}"


def test_required_texts_present() -> None:
    texts = _all_texts(_window())
    missing = [t for t in REQUIRED_TEXTS if t not in texts]
    assert not missing, f"texts not found: {missing}"


def test_no_vendor_branding_in_ui() -> None:
    texts = " ".join(_all_texts(_window())).lower()
    for banned in ("cinema 4d", "maxon"):
        assert banned not in texts, f"branding found in the UI: {banned!r}"


def test_region_geometry_matches_spec() -> None:
    win = _window()
    errors = _layout_errors(win, win.width(), win.height())
    assert not errors, "; ".join(errors)


def test_layout_fits_at_the_minimum_window_size() -> None:
    from quartz_studio import theme

    assert (theme.WINDOW_MIN_W, theme.WINDOW_MIN_H) == SMALL_CLIENT
    win = _sized_window(*SMALL_CLIENT)
    try:
        errors = _layout_errors(win, *SMALL_CLIENT)
        assert not errors, "; ".join(errors)
        tools = win.regions["tool_palette"]
        for name, button in tools.buttons.items():
            assert button.isVisibleTo(win), name
        win.resize(*CLIENT_REAL)
        _settle(_app())
        errors = _layout_errors(win, *CLIENT_REAL)
        assert not errors, "; ".join(errors)
    finally:
        _close(win)


def test_layout_keeps_its_shape_with_the_tool_options_panel() -> None:
    from quartz_studio.modeling import install as mi
    from quartz_studio.scene import get_scene

    win = _sized_window(*SMALL_CLIENT)
    scene = get_scene()
    try:
        mi.install(win)
        mi.activate_tool("extrude")
        _settle(_app())
        win.apply_default_sizes()
        _settle(_app())
        assert win.tool_options.isVisible()
        assert win.manager_splitter.indexOf(win.tool_options) == 1
        assert win.tool_options.height() >= win.tool_options.minimumHeight()
        errors = _layout_errors(win, *SMALL_CLIENT)
        assert not errors, "; ".join(errors)
    finally:
        scene.set_tool("move")
        scene.set_mode("model")
        shortcuts = getattr(win, "modeling_shortcuts", None)
        if shortcuts is not None:
            QApplication.instance().removeEventFilter(shortcuts)
        _close(win)


def test_menu_bar_titles() -> None:
    menu_bar = _window().regions["menu_bar"]
    assert menu_bar.titles() == ["File", "Edit", "Create", "Mesh"]


def _leaf_actions(menu) -> list:
    out = []
    stack = [menu]
    while stack:
        for action in stack.pop().actions():
            if action.menu() is not None:
                stack.append(action.menu())
            elif not action.isSeparator() and action.property("qs_kind") != "section":
                out.append(action)
    return out


def test_window_shows_only_functional_regions() -> None:
    from quartz_studio.main_window import REGIONS

    win = _window()
    assert list(REGIONS) == REGION_NAMES
    assert list(win.regions) == REGION_NAMES
    assert win.statusBar() is win.regions["status_bar"]
    assert win.regions["object_palette"].parentWidget() is win.regions["viewport"]
    assert not win.regions["status_bar"].findChildren(QAbstractButton)
    names = {type(w).__name__ for w in win.findChildren(QWidget)}
    assert not names & REMOVED_WIDGETS, names & REMOVED_WIDGETS
    attributes = win.attribute_manager
    stray = [w for w in win.findChildren(QComboBox) + win.findChildren(QCheckBox)
             if not attributes.isAncestorOf(w)]
    assert not stray, stray
    viewport = win.regions["viewport"]
    assert viewport.menu_bar.menu_titles() == ["View", "Cameras"]
    assert len(viewport.menu_bar.nav_buttons) == 3
    assert list(win.regions["tool_palette"].buttons) == TOOL_BUTTONS
    assert list(win.regions["object_palette"].buttons) == PALETTE_BUTTONS
    assert list(win.regions["command_bar"].buttons) == COMMAND_BUTTONS


def test_tool_palette_fits_the_client_area() -> None:
    win = _window()
    tools = win.regions["tool_palette"]
    assert not tools.arrows_visible()
    area = tools._scroll.viewport()
    for name, button in tools.buttons.items():
        assert button.isVisibleTo(win), name
        top = button.mapTo(area, QPoint(0, 0))
        assert top.y() >= 0 and top.y() + button.height() <= area.height(), (name, top.y(), area.height())
        assert top.x() >= 0 and top.x() + button.width() <= tools.width(), name
    ys = [b.mapTo(win, QPoint(0, 0)).y() for b in tools.buttons.values()]
    assert ys == sorted(ys) and len(set(ys)) == len(ys)


def _trim(scene, keep: int = 3) -> None:
    for obj in list(scene.objects[:-keep]):
        if obj in scene.objects:
            scene.remove_object(obj)


def test_every_visible_control_is_wired() -> None:
    from quartz_studio.scene import get_scene

    win = _window()
    app = _app()
    scene = get_scene()
    viewport = win.regions["viewport"]
    buttons = [b for name in ("command_bar", "tool_palette", "object_palette")
               for b in win.regions[name].buttons.values()]
    assert buttons
    dock = win.regions["object_palette"]
    assert all(b.isVisibleTo(win) for b in dock.buttons.values())
    assert all(b.popup_side() == "above" for b in dock.buttons.values())
    folder = tempfile.mkdtemp(prefix="qz_smoke_")
    with _FakeDialogs(folder) as fake, _LogCapture("quartz_studio") as records:
        for button in buttons:
            for action in _leaf_actions(button.build_menu()):
                action.trigger()
                _trim(scene)
            if button.isEnabled():
                button.click()
            _trim(scene)
            _settle(app, 2)
        for menu in win.regions["menu_bar"].menus.values():
            menu.aboutToShow.emit()
            for action in _leaf_actions(menu):
                assert action.parent().is_wired(action.property("qs_label")), action.text()
                if action.isEnabled():
                    action.trigger()
                    _trim(scene)
        for menu in viewport.menu_bar.menus.values():
            for action in _leaf_actions(menu):
                action.trigger()
        for nav in viewport.menu_bar.nav_buttons:
            nav.click()
        win.regions["coordinates"].reset_button.click()
        _settle(app, 2)
        covered = set(buttons) | set(viewport.menu_bar.nav_buttons)
        covered.add(win.regions["coordinates"].reset_button)
        extra = []
        for name in ("menu_bar", "command_bar", "tool_palette", "object_palette", "status_bar"):
            region = win.regions[name]
            extra += [b for b in region.findChildren(QAbstractButton)
                      if b.isVisibleTo(win) and b not in covered]
        for button in extra:
            if button.isEnabled():
                button.click()
                _trim(scene)
                _settle(app, 2)
        undo, redo = win.regions["command_bar"].history_buttons()
        assert undo.isEnabled()
        undo.click()
        _settle(app, 2)
        assert redo.isEnabled()
        redo.click()
        _settle(app, 2)
    assert not [r for r in records if "not implemented" in r], records
    assert not [m for m in fake.messages if m[0] == "error"], fake.messages
    assert fake.counter > 0 and os.listdir(folder)
    assert len(scene.objects) > 1
    from quartz_studio.controls.editor import ControlsDialog

    dialogs = [w for w in QApplication.topLevelWidgets() if isinstance(w, ControlsDialog)]
    assert dialogs, "Edit > Controls... opened no dialog"
    for dlg in dialogs:
        dlg.close()
        dlg.deleteLater()
    scene.set_tool("move")
    scene.set_mode("model")
    viewport.canvas.set_view("Perspective")
    viewport.canvas.reset_camera()
    _settle(app, 2)
    assert not [w for w in QApplication.topLevelWidgets()
                if isinstance(w, ControlsDialog) and w.isVisible()]


def test_default_sizes_keep_coordinates_last_with_an_extra_panel() -> None:
    from quartz_studio import theme
    from quartz_studio.main_window import MainWindow

    app = _app()
    win = MainWindow()
    try:
        win.setMinimumSize(1, 1)
        win.resize(*CLIENT_REAL)
        win.show()
        _settle(app)
        win.apply_default_sizes()
        _settle(app)
        plain = win.coordinates.height()
        extra = QWidget()
        extra.setMinimumHeight(120)
        win.manager_splitter.insertWidget(1, extra)
        _settle(app)
        win.apply_default_sizes()
        _settle(app)
        assert win.manager_splitter.indexOf(win.coordinates) == win.manager_splitter.count() - 1
        assert win.coordinates.height() == plain == theme.COORDINATES_H, (win.coordinates.height(), plain)
        assert extra.height() >= 120
        assert win.object_manager.height() > extra.height()
        extra.hide()
        win.apply_default_sizes()
        _settle(app)
        assert win.coordinates.height() == theme.COORDINATES_H
    finally:
        win.close()
        win.deleteLater()
        _settle(app)


def test_attribute_manager_takes_the_lower_half_of_the_column() -> None:
    win = _window()
    splitter = win.manager_splitter
    order = [splitter.widget(i) for i in range(splitter.count())]
    assert order[0] is win.object_manager and order[-1] is win.coordinates
    assert order.index(win.object_manager) < order.index(win.attribute_manager) < order.index(win.coordinates)
    column = splitter.height()
    assert win.attribute_manager.height() >= 0.3 * column, (win.attribute_manager.height(), column)
    assert win.object_manager.height() >= 0.3 * column, (win.object_manager.height(), column)


def test_tool_and_mode_buttons_are_exclusive() -> None:
    win = _window()
    tools = win.regions["tool_palette"]
    assert tools.active_tool() == "Move"
    checked = [b for b in tools.findChildren(QAbstractButton) if b.isCheckable() and b.isChecked()]
    assert len(checked) == 1
    modes = win.regions["command_bar"].mode_buttons()
    assert sum(1 for b in modes if b.isChecked()) == 1


def test_status_bar_shows_real_state() -> None:
    from quartz_studio.scene import get_scene

    win = _window()
    app = _app()
    status = win.regions["status_bar"]
    scene = get_scene()
    scene.set_mode("model")
    scene.set_tool("move")
    _settle(app, 2)
    assert status.mode_text() == "Mode: Model · Tool: Move"
    assert status.hint_text() == "Drag to move · Hold Ctrl to copy · Esc cancels"
    active = scene.active
    assert active is not None
    scene.select_object(True)
    _settle(app, 1)
    assert status.selection_text().startswith("1 object · ")
    scene.select_object(False)
    _settle(app, 1)
    assert status.selection_text().startswith("0 objects · ")
    scene.set_active(active)
    scene.select_object(True)
    scene.set_tool("rotate")
    _settle(app, 1)
    assert status.mode_text() == "Mode: Model · Tool: Rotate"
    assert "Shift snaps" in status.hint_text()
    if scene.is_editable(active) and len(active.mesh.polygons):
        scene.set_mode("polygons")
        scene.select_components([0])
        _settle(app, 1)
        assert status.mode_text() == "Mode: Polygons · Tool: Rotate"
        assert "1 polygon" in status.selection_text().split(" · ")
        scene.set_tool("select")
        _settle(app, 1)
        assert status.hint_text() == "Paint to select · Shift adds · Ctrl removes · Shift+wheel sizes the brush"
        scene.select_components([])
        _settle(app, 1)
        assert "0 polygons" in status.selection_text().split(" · ")
    scene.set_mode("model")
    scene.set_tool("move")
    _settle(app, 1)
    assert status.mode_text() == "Mode: Model · Tool: Move"
    assert not [w for w in status.findChildren(QAbstractButton)]


def test_project_chip_shows_the_file_and_unsaved_changes() -> None:
    from quartz_studio import project
    from quartz_studio.scene import get_scene

    win = _window()
    app = _app()
    chip = win.regions["command_bar"].project_chip
    assert chip.text() == project.project_name()
    assert chip.shows_unsaved() == project.is_modified()
    scene = get_scene()
    scene.changed.emit()
    _settle(app, 2)
    assert project.is_modified() and chip.shows_unsaved()
    assert chip.text() in win.windowTitle()


def test_mode_switcher_is_one_pill_with_inset_segments() -> None:
    from quartz_studio import theme

    win = _window()
    bar = win.regions["command_bar"]
    switcher = bar.mode_switcher
    assert switcher.property("qsRole") == "modes"
    assert switcher.height() == theme.SEGMENT_H
    outer = _rect(win, switcher)
    for button in bar.mode_buttons():
        inner = _rect(win, button)
        assert outer.contains(inner), (button.command_text(), inner, outer)
        assert inner.top() - outer.top() == outer.bottom() - inner.bottom(), (inner, outer)
        assert inner.height() == theme.SEGMENT_H - 4
    lefts = [_rect(win, b).left() for b in bar.mode_buttons()]
    assert lefts == sorted(lefts) and len(set(lefts)) == 4


def test_every_tool_has_a_hint_from_real_behaviour() -> None:
    from quartz_studio.modeling import get_tool, tool_ids
    from quartz_studio.widgets import status_bar as sb

    _window()
    for tool in ("select", "move", "rotate", "scale", "pen", "line_pen"):
        for mode in ("model", "points", "edges", "polygons"):
            assert sb.tool_hint(tool, mode), (tool, mode)
    ids = tool_ids()
    assert ids
    for tool in ids:
        spec = get_tool(tool)
        hint = sb.tool_hint(tool, spec.modes[0])
        assert hint, tool
        assert "not implemented" not in hint.lower()
        if not spec.interactive:
            assert hint == sb.APPLIED_HINT, tool
        assert sb.tool_name(tool) == spec.name
    assert sb.tool_hint("other", "model") == ""


def test_status_bar_elides_long_text_and_keeps_the_full_one() -> None:
    win = _window()
    app = _app()
    status = win.regions["status_bar"]
    label = status.hint_label
    long_text = "Drag sideways to change a very long parameter name " * 12
    label.setText(long_text)
    _settle(app, 2)
    assert label.text() == long_text
    shown = QLabel.text(label)
    assert shown != long_text and shown.endswith("…")
    assert label.sizeHint().height() <= theme_status_height()
    status.refresh()
    label.setText("")
    status.refresh()
    assert status.hint_text() == status.hint_label.text()


def theme_status_height() -> int:
    from quartz_studio import theme

    return theme.STATUS_BAR_H


def test_project_chip_elides_a_long_name() -> None:
    from quartz_studio import project, theme

    win = _window()
    app = _app()
    chip = win.regions["command_bar"].project_chip
    original = project.project_name
    long_name = "A very long project name " * 8 + ".qz"
    project.project_name = lambda: long_name
    try:
        chip.refresh()
        _settle(app, 2)
        assert chip.text() == long_name
        assert QLabel.text(chip.name_label) != long_name and "…" in QLabel.text(chip.name_label)
        assert chip.width() <= 240 + 4 * theme.SPACE_3 + theme.SPACE_2
        assert not _layout_errors(win, win.width(), win.height()), _layout_errors(win, win.width(), win.height())
    finally:
        project.project_name = original
        chip.refresh()
        _settle(app, 2)


def test_splitters_between_cards_stay_draggable() -> None:
    from quartz_studio import theme

    win = _sized_window(*SMALL_CLIENT)
    app = _app()
    try:
        assert win.body_splitter.handleWidth() == theme.CARD_GAP
        assert win.manager_splitter.handleWidth() == theme.CARD_GAP
        before = win.body_splitter.sizes()
        win.body_splitter.moveSplitter(win.body_splitter.sizes()[0] - 40, 1)
        _settle(app, 2)
        after = win.body_splitter.sizes()
        assert after[1] > before[1] and after[0] < before[0]
        sizes = win.manager_splitter.sizes()
        win.manager_splitter.moveSplitter(sizes[0] - 30, 1)
        _settle(app, 2)
        assert win.manager_splitter.sizes()[0] < sizes[0]
        kept = win.body_splitter.sizes()
        win.resize(win.width() + 60, win.height())
        _settle(app, 3)
        assert win.body_splitter.sizes()[1] == kept[1]
    finally:
        _close(win)


def test_dock_fold_outs_open_upward() -> None:
    win = _window()
    dock = win.regions["object_palette"]
    for key in ("Cube", "Sphere"):
        button = dock.buttons[key]
        menu = button.build_menu()
        try:
            pos = button._popup_pos(menu)
            top = button.mapToGlobal(QPoint(0, 0)).y()
            assert pos.y() + menu.sizeHint().height() <= top, (key, pos.y(), top)
        finally:
            menu.deleteLater()


def _isolated_main(argv: list[str]) -> int:
    from quartz_studio import app as app_module
    from quartz_studio import controls, prefs

    folder = tempfile.mkdtemp(prefix="quartz-main-")
    saved_env = os.environ.get("QUARTZ_PREFS_DIR")
    saved_store = controls.STORE_PATH
    os.environ["QUARTZ_PREFS_DIR"] = folder
    controls.STORE_PATH = os.path.join(folder, "controls.json")
    try:
        return app_module.main(argv)
    finally:
        controls.STORE_PATH = saved_store
        if saved_env is None:
            os.environ.pop("QUARTZ_PREFS_DIR", None)
        else:
            os.environ["QUARTZ_PREFS_DIR"] = saved_env
        prefs._state["user"] = False
        prefs.reload()
        controls.reset()


def test_main_loop_runs_two_seconds() -> None:
    qapp = _app()
    QTimer.singleShot(2000, qapp.quit)
    assert _isolated_main([sys.argv[0]]) == 0
    for w in QApplication.topLevelWidgets():
        if w is not _WINDOW and w.isWindow():
            w.close()


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
