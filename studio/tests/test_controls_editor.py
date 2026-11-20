from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLayout, QWidget

from quartz_studio.app import create_app

APP = create_app([])

from quartz_studio import controls
from quartz_studio.controls import editor

WIDGET_MAX = 16777215
BELOW_128 = {2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 88, 96, 112, 120}
MAIN = (2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 72, 96, 128, 256, 512, 1024)


def allowed_px(v: float) -> bool:
    if v != int(v):
        return False
    v = abs(int(v))
    if v in (0, 1):
        return True
    if v < 128:
        return v in BELOW_128
    if v % 16 == 0:
        return True
    return any(a + b == v or a - b == v for a in MAIN for b in MAIN)


class _Env:

    def __init__(self) -> None:
        self.folder = tempfile.mkdtemp(prefix="quartz-ctl-editor-")
        self.saved = {name: getattr(editor, name) for name in
                      ("choose_import_file", "choose_export_file", "ask_profile_name", "confirm", "show_error")}
        controls.reset()
        controls.STORE_PATH = os.path.join(self.folder, "controls.json")
        self.host = QWidget()
        self.host.resize(1280, 720)
        self.host.show()
        self.dlg = editor.open_editor(self.host)
        APP.processEvents()

    def close(self) -> None:
        if editor._valid(self.dlg):
            self.dlg.recorder.cancel()
            self.dlg.close()
            self.dlg.deleteLater()
        self.host.close()
        self.host.deleteLater()
        for name, fn in self.saved.items():
            setattr(editor, name, fn)
        APP.processEvents()
        controls.reset()
        controls.STORE_PATH = None
        shutil.rmtree(self.folder, ignore_errors=True)

    def __enter__(self) -> "_Env":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _flush() -> None:
    QCoreApplication.sendPostedEvents(None, int(QEvent.Type.DeferredDelete.value))
    APP.processEvents()


def _store() -> dict:
    with open(controls.STORE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _user_doc(pid: str) -> dict:
    for doc in _store()["profiles"]:
        if doc["id"] == pid:
            return doc
    raise AssertionError(f"profile {pid} not in the store")


def _record_add(dlg, action_id: str) -> None:
    dlg.keyboard.add_button(action_id).click()
    assert dlg.recorder.active()
    assert QWidget.keyboardGrabber() is dlg


def test_open_editor_keeps_one_dialog_per_window():
    with _Env() as env:
        dlg = env.dlg
        assert dlg.objectName() == "qsControlsDialog"
        assert dlg.windowTitle() == "Controls"
        assert not dlg.isModal()
        assert dlg.isVisible()
        again = editor.open_editor(env.host)
        assert again is dlg
        dlg.close()
        assert not dlg.isVisible()
        third = editor.open_editor(env.host)
        assert third is dlg and dlg.isVisible()
        found = [w for w in QApplication.topLevelWidgets()
                 if isinstance(w, editor.ControlsDialog) and w.parentWidget() is env.host]
        assert found == [dlg]
        assert dlg.page_names() == ["Keyboard", "Mouse", "Cursor"]


def test_closed_dialog_is_freed_and_reopens_fresh():
    with _Env() as env:
        dlg = env.dlg
        count = len(dlg.findChildren(QWidget))
        assert count > 100, count
        dlg.close()
        _flush()
        _flush()
        assert not editor._valid(dlg)
        assert editor.dialog_for(env.host) is None
        alive = [w for w in QApplication.topLevelWidgets() if isinstance(w, editor.ControlsDialog)]
        assert alive == [], alive
        fresh = editor.open_editor(env.host)
        env.dlg = fresh
        assert fresh is not dlg and fresh.isVisible()
        assert editor.dialog_for(env.host) is fresh
        fresh.hide()
        fresh.show()
        _flush()
        assert editor._valid(fresh) and fresh.isVisible()


def test_dialog_fits_and_every_size_is_in_the_norm():
    with _Env() as env:
        dlg = env.dlg
        controls.duplicate("classic")
        _flush()
        assert dlg.width() == 960 and dlg.height() == 640
        assert dlg.minimumSize() == dlg.maximumSize()
        assert dlg.width() <= env.host.width() and dlg.height() <= env.host.height()
        bad = []
        for page in range(3):
            dlg.set_page(page)
            _flush()
            for w in dlg.findChildren(QWidget):
                if w.window() is not dlg:
                    continue
                if w.minimumWidth() == w.maximumWidth() and w.maximumWidth() < WIDGET_MAX:
                    if not allowed_px(w.maximumWidth()):
                        bad.append((type(w).__name__, w.objectName(), "w", w.maximumWidth()))
                if w.minimumHeight() == w.maximumHeight() and w.maximumHeight() < WIDGET_MAX:
                    if not allowed_px(w.maximumHeight()):
                        bad.append((type(w).__name__, w.objectName(), "h", w.maximumHeight()))
            for lay in dlg.findChildren(QLayout):
                m = lay.contentsMargins()
                values = [m.left(), m.top(), m.right(), m.bottom()]
                if lay.spacing() >= 0:
                    values.append(lay.spacing())
                for v in values:
                    if not allowed_px(v):
                        bad.append((type(lay).__name__, lay.parentWidget().objectName()
                                    if lay.parentWidget() else "", "layout", v))
        for v in re.findall(r"(-?\d+(?:\.\d+)?)px", dlg.styleSheet()):
            if not allowed_px(float(v)):
                bad.append(("qss", "", "px", v))
        assert not bad, bad
        kb = dlg.keyboard
        assert dlg.profile_combo.width() == 256 and dlg.profile_combo.height() == 28
        for b in (dlg.duplicate_button, dlg.rename_button, dlg.delete_button, dlg.import_button,
                  dlg.export_button, dlg.reset_profile_button, dlg.close_button):
            assert b.height() == 28, (b.text(), b.height())
        assert dlg.tabs.height() == 28
        assert kb.search.width() == 320 and kb.search.height() == 28
        assert kb.categories.width() == 192
        assert kb.categories.visualItemRect(kb.categories.item(0)).height() == 28
        assert kb.categories.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert not kb.categories.horizontalScrollBar().isVisible()
        assert kb.categories.horizontalScrollBar().maximum() == 0
        assert kb.categories.visualItemRect(kb.categories.item(0)).width() == kb.categories.viewport().width()
        assert kb.table.rowHeight(0) == 28
        assert kb.table.columnWidth(1) == 320 and kb.table.columnWidth(2) == 96
        assert kb.table.columnWidth(3) == 32
        chip = kb.chips("file.new")[0]
        assert chip.height() == 24 and chip.close_button.width() == 12
        assert kb.add_button("file.new").size().width() == 24
        assert kb.banner.height() == 40
        dlg.set_page(1)
        _flush()
        assert dlg.mouse.pad.width() == 256 and dlg.mouse.pad.height() == 96
        assert all(row.height() == 32 for row in dlg.mouse.rows)
        assert all(row.combo.width() == 192 and row.combo.height() == 28 for row in dlg.mouse.rows)
        assert dlg.mouse.reset_button.height() == 28
        dlg.set_page(2)
        _flush()
        page = dlg.cursor_page
        assert all(row.height() == 28 for row in page.rows.values())
        assert all(row.label.width() == 192 for row in page.rows.values())
        assert all(g.header.height() == 24 for g in page.groups)
        assert page.controls["orbit_speed"].width() == 128


def test_builtin_disables_editing_and_duplicate_enables_it():
    with _Env() as env:
        dlg = env.dlg
        assert controls.active_id() == "classic"
        editing = dlg.editing_controls()
        assert len(editing) > 20
        assert not any(w.isEnabled() for w in editing), [w for w in editing if w.isEnabled()][:5]
        assert dlg.note.isVisibleTo(dlg)
        assert dlg.note.text() == editor.NOTE_TEXT
        assert dlg.duplicate_button.isEnabled() and dlg.import_button.isEnabled()
        assert dlg.export_button.isEnabled()
        assert not os.path.exists(controls.STORE_PATH)
        QTest.mouseClick(dlg.duplicate_button, Qt.MouseButton.LeftButton)
        _flush()
        res = controls.active()
        assert res.name == "Classic Copy" and not res.builtin
        assert dlg.profile_combo.currentText() == "Classic Copy"
        assert [dlg.profile_combo.itemText(i) for i in range(dlg.profile_combo.count())] == [
            "Standard", "Classic", "Classic Copy"]
        store = _store()
        assert store["selected"] == res.id
        assert _user_doc(res.id)["base"] == "classic"
        editing = dlg.editing_controls()
        assert all(w.isEnabled() for w in editing), [w for w in editing if not w.isEnabled()][:5]
        assert not dlg.note.isVisibleTo(dlg)
        dlg.choose_profile("standard")
        _flush()
        assert controls.active_id() == "standard"
        assert _store()["selected"] == "standard"
        assert not any(w.isEnabled() for w in dlg.editing_controls())


def test_rename_delete_and_reset_profile():
    with _Env() as env:
        dlg = env.dlg
        pid = dlg.duplicate_profile()
        editor.ask_profile_name = lambda parent, current: "Mine"
        dlg.rename_button.click()
        assert _user_doc(pid)["name"] == "Mine"
        assert dlg.profile_combo.currentText() == "Mine"
        errors = []
        editor.show_error = errors.append
        editor.ask_profile_name = lambda parent, current: "Classic"
        dlg.rename_button.click()
        assert errors and _user_doc(pid)["name"] == "Mine"
        controls.set_keys(pid, "file.import", ["Ctrl+Shift+I"])
        asked = []
        editor.confirm = lambda parent, text: asked.append(text) or False
        dlg.reset_profile_button.click()
        assert _user_doc(pid)["keys"] == {"file.import": ["Ctrl+Shift+I"]}
        editor.confirm = lambda parent, text: True
        dlg.reset_profile_button.click()
        assert _user_doc(pid)["keys"] == {}
        dlg.delete_button.click()
        assert all(doc["id"] != pid for doc in _store()["profiles"])
        assert controls.active_id() == "classic"
        assert dlg.profile_combo.currentText() == "Classic"


def test_recording_a_combination_commits_at_once():
    with _Env() as env:
        dlg = env.dlg
        pid = dlg.duplicate_profile()
        _record_add(dlg, "file.import")
        chip = dlg.keyboard.chips("file.import")[-1]
        assert chip.state == "recording" and chip.text() == "Press keys..."
        QTest.keyClick(dlg, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
        assert not dlg.recorder.active()
        assert QWidget.keyboardGrabber() is None
        assert _user_doc(pid)["keys"]["file.import"] == ["Ctrl+E"]
        assert [c.text() for c in dlg.keyboard.chips("file.import")] == ["Ctrl+E"]
        assert dlg.keyboard.action_label("file.import").property("qsOverridden") == "true"
        assert dlg.keyboard.reset_button("file.import").isVisibleTo(dlg)
        dlg.keyboard.chips("file.import")[0].clicked.emit()
        QTest.keyClick(dlg, Qt.Key.Key_F5)
        assert _user_doc(pid)["keys"]["file.import"] == ["F5"]
        dlg.keyboard.chips("file.import")[0].removed.emit()
        assert _user_doc(pid)["keys"]["file.import"] == []
        dlg.keyboard.reset_button("file.import").click()
        assert "file.import" not in _user_doc(pid)["keys"]


def test_recording_a_chord_and_a_single_key():
    with _Env() as env:
        dlg = env.dlg
        pid = dlg.duplicate_profile()
        _record_add(dlg, "file.clear_recent")
        QTest.keyClick(dlg, Qt.Key.Key_M)
        assert dlg.recorder.active()
        assert dlg.recorder.chip.text() == "M then..."
        QTest.keyClick(dlg, Qt.Key.Key_E)
        assert not dlg.recorder.active()
        assert _user_doc(pid)["keys"]["file.clear_recent"] == ["M~E"]
        assert dlg.keyboard.pending is not None
        assert dlg.keyboard.banner.text() == "M~E is already used by Polygon Pen."
        dlg.keyboard.banner.keep_button.click()
        controls.set_cursor(pid, "chord_ms", 500)
        _record_add(dlg, "file.export_selection")
        _flush()
        started = time.monotonic()
        QTest.keyClick(dlg, Qt.Key.Key_J)
        assert dlg.recorder.active()
        assert dlg.recorder.timer.interval() == 500
        assert "file.export_selection" not in _user_doc(pid)["keys"]
        while dlg.recorder.active() and time.monotonic() - started < 5.0:
            QTest.qWait(20)
        assert not dlg.recorder.active()
        assert time.monotonic() - started >= 0.45
        assert _user_doc(pid)["keys"]["file.export_selection"] == ["J"]


def test_escape_and_a_click_elsewhere_cancel_recording():
    with _Env() as env:
        dlg = env.dlg
        pid = dlg.duplicate_profile()
        _record_add(dlg, "file.import")
        QTest.keyClick(dlg, Qt.Key.Key_Escape)
        assert not dlg.recorder.active()
        assert QWidget.keyboardGrabber() is None
        assert "file.import" not in _user_doc(pid)["keys"]
        assert dlg.keyboard.chips("file.import") == []
        assert dlg.isVisible()
        _record_add(dlg, "file.import")
        QTest.keyClick(dlg, Qt.Key.Key_Shift)
        assert dlg.recorder.active()
        QTest.mouseClick(dlg.keyboard.search, Qt.MouseButton.LeftButton)
        assert not dlg.recorder.active()
        assert "file.import" not in _user_doc(pid)["keys"]


def _standard_copy_with_conflict(dlg) -> str:
    dlg.choose_profile("standard")
    pid = dlg.duplicate_profile()
    _record_add(dlg, "file.clear_recent")
    QTest.keyClick(dlg, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
    assert dlg.keyboard.top.currentWidget() is dlg.keyboard.banner
    assert dlg.keyboard.banner.text() == "Ctrl+E is already used by Extrude."
    return pid


def test_conflict_banner_replace():
    with _Env() as env:
        dlg = env.dlg
        pid = _standard_copy_with_conflict(dlg)
        dlg.keyboard.banner.replace_button.click()
        keys = _user_doc(pid)["keys"]
        assert keys["file.clear_recent"] == ["Ctrl+E"]
        assert keys["tool.extrude"] == []
        assert controls.conflicts(pid) == []
        assert dlg.keyboard.top.currentIndex() == 0


def test_conflict_banner_keep_both():
    with _Env() as env:
        dlg = env.dlg
        pid = _standard_copy_with_conflict(dlg)
        dlg.keyboard.banner.keep_button.click()
        keys = _user_doc(pid)["keys"]
        assert keys["file.clear_recent"] == ["Ctrl+E"]
        assert "tool.extrude" not in keys
        assert any({c[1], c[2]} == {"file.clear_recent", "tool.extrude"} for c in controls.conflicts(pid))
        mine = dlg.keyboard.chips("file.clear_recent")[0]
        theirs = dlg.keyboard.chips("tool.extrude")[0]
        assert mine.state == "conflict" and mine.toolTip() == "Also used by Extrude"
        assert theirs.state == "conflict" and theirs.toolTip() == "Also used by Clear Recent File List"
        assert dlg.keyboard.top.currentIndex() == 0


def test_conflict_banner_cancel():
    with _Env() as env:
        dlg = env.dlg
        pid = _standard_copy_with_conflict(dlg)
        dlg.keyboard.banner.cancel_button.click()
        keys = _user_doc(pid)["keys"]
        assert "file.clear_recent" not in keys and "tool.extrude" not in keys
        assert controls.conflicts(pid) == []
        assert dlg.keyboard.chips("file.clear_recent") == []
        assert [c.text() for c in dlg.keyboard.chips("tool.extrude")] == ["Ctrl+E"]


def test_search_and_categories_filter():
    with _Env() as env:
        kb = env.dlg.keyboard
        everything = kb.visible_ids()
        assert "file.new" in everything and "view.frame_all" in everything
        kb.search.setText("save")
        shown = kb.visible_ids()
        assert "file.save" in shown and "file.save_as" in shown and "file.new" not in shown
        kb.search.setText("ctrl+shift+o")
        assert kb.visible_ids() == ["file.merge"]
        kb.search.setText("")
        names = [kb.categories.item(i).text() for i in range(kb.categories.count())]
        assert names[:11] == ["All", "File", "Edit", "Modes", "Tools", "Mesh", "Select", "Create", "View",
                              "Cameras", "Objects"]
        kb.categories.setCurrentRow(names.index("Cameras"))
        shown = kb.visible_ids()
        assert shown and all(controls.actions()[aid].category == "Cameras" for aid in shown)
        assert "camera.top" in shown
        kb.search.setText("top")
        assert kb.visible_ids() == ["camera.top"]
        kb.categories.setCurrentRow(0)
        kb.search.setText("")
        assert kb.visible_ids() == everything


def test_mouse_page_record_pad_and_rows():
    with _Env() as env:
        dlg = env.dlg
        pid = dlg.duplicate_profile()
        dlg.set_page(1)
        _flush()
        page = dlg.mouse
        base = len(controls.active().mouse)
        assert len(page.rows) == base
        assert page.rows[0].label.text() == "Alt + Left drag"
        assert page.rows[3].label.text() == "3 held + Left drag"
        assert page.rows[0].combo.currentText() == "Orbit"
        QTest.mousePress(page.pad, Qt.MouseButton.RightButton,
                         Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier, QPoint(20, 20))
        mouse = _user_doc(pid)["mouse"]
        assert len(mouse) == base + 1
        assert mouse[-1] == {"button": "right", "mods": ["shift", "ctrl"], "key": None, "double": False,
                             "op": "orbit"}
        assert not page.banner.isVisibleTo(dlg)
        QTest.mousePress(page.pad, Qt.MouseButton.RightButton,
                         Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier, QPoint(30, 30))
        assert len(_user_doc(pid)["mouse"]) == base + 1
        assert page.banner.isVisibleTo(dlg) and page.banner.text() == "This gesture is already used."
        QTest.mousePress(page.pad, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.AltModifier, QPoint(20, 20))
        assert len(_user_doc(pid)["mouse"]) == base + 1
        QTest.keyPress(page.pad, Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier)
        QTest.mousePress(page.pad, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 20))
        QTest.keyRelease(page.pad, Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier)
        mouse = _user_doc(pid)["mouse"]
        assert mouse[-1]["key"] == "Z" and mouse[-1]["button"] == "left" and mouse[-1]["mods"] == []
        last = page.rows[-1]
        last.combo.setCurrentIndex(last.combo.findText("Pan"))
        assert _user_doc(pid)["mouse"][-1]["op"] == "pan"
        page.rows[-1].up_button.click()
        mouse = _user_doc(pid)["mouse"]
        assert mouse[-2]["key"] == "Z" and mouse[-1]["button"] == "right"
        page.rows[-2].remove_button.click()
        mouse = _user_doc(pid)["mouse"]
        assert len(mouse) == base + 1 and all(g.get("key") != "Z" for g in mouse)
        page.reset_button.click()
        assert _user_doc(pid)["mouse"] is None
        assert len(page.rows) == base


def test_mouse_page_double_click_gesture():
    with _Env() as env:
        dlg = env.dlg
        pid = dlg.duplicate_profile()
        dlg.set_page(1)
        page = dlg.mouse
        base = len(controls.active().mouse)
        QTest.mousePress(page.pad, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, QPoint(20, 20))
        assert _user_doc(pid)["mouse"] is None
        assert page.banner.isVisibleTo(dlg)
        QTest.mouseDClick(page.pad, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 20))
        mouse = _user_doc(pid)["mouse"]
        assert mouse[-1]["double"] is True and mouse[-1]["button"] == "right"
        assert sum(1 for g in mouse if g["button"] == "right" and not g["mods"] and not g["key"]
                   and not g["double"]) == 1
        row = page.rows[-1]
        assert row.label.text() == "Right double-click"
        row.combo.setCurrentIndex(row.combo.findData("action:view.frame_all"))
        g = _user_doc(pid)["mouse"][-1]
        assert g["action"] == "view.frame_all" and "op" not in g


def test_cursor_page_writes_and_resets_overrides():
    with _Env() as env:
        dlg = env.dlg
        pid = dlg.duplicate_profile()
        dlg.set_page(2)
        page = dlg.cursor_page
        changes = {
            "orbit_pivot": ("combo", "Object"),
            "orbit_style": ("combo", "free"),
            "orbit_speed": ("spin", 0.5),
            "invert_orbit_x": ("toggle", True),
            "invert_orbit_y": ("toggle", True),
            "invert_pan": ("toggle", True),
            "dolly_speed": ("spin", 0.01),
            "zoom_to_cursor": ("toggle", False),
            "wheel_step": ("spin", 0.8),
            "wheel_invert": ("toggle", True),
            "drag_threshold": ("spin", 8),
            "click_tolerance": ("spin", 6),
            "hold_ms": ("spin", 200),
            "chord_ms": ("spin", 900),
        }
        assert set(changes) == set(page.controls)
        for key, (kind, value) in changes.items():
            widget = page.controls[key]
            if kind == "combo":
                widget.setCurrentIndex(widget.findData(value))
            elif kind == "toggle":
                widget.setChecked(value)
            else:
                widget.setValue(value)
            stored = _user_doc(pid)["cursor"][key]
            assert stored == value, (key, stored, value)
            assert controls.cursor(key) == value
            row = page.rows[key]
            assert row.property("qsOverridden") == "true"
            assert row.reset_button.isVisibleTo(dlg)
        for key in changes:
            page.rows[key].reset_button.click()
            assert key not in _user_doc(pid)["cursor"]
            assert page.rows[key].property("qsOverridden") == "false"
            assert not page.rows[key].reset_button.isVisibleTo(dlg)
        assert controls.cursor("drag_threshold") == 3
        combo = page.modifier_combos["snap"]
        combo.setCurrentIndex(combo.findData("ctrl"))
        assert _user_doc(pid)["modifiers"] == {"snap": "ctrl"}
        page.rows["modifiers.snap"].reset_button.click()
        assert _user_doc(pid)["modifiers"] == {}
        page.modal_cells["cancel"].add_button.click()
        assert dlg.recorder.active() and dlg.recorder.single
        QTest.keyClick(dlg, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier)
        assert dlg.recorder.active()
        QTest.keyClick(dlg, Qt.Key.Key_Q)
        assert not dlg.recorder.active()
        assert _user_doc(pid)["modal"] == {"cancel": ["Escape", "Q"]}
        assert [c.text() for c in page.modal_cells["cancel"].chips] == ["Escape", "Q"]
        page.rows["modal.cancel"].reset_button.click()
        assert _user_doc(pid)["modal"] == {}


def test_import_and_export_through_replaced_file_dialogs():
    with _Env() as env:
        dlg = env.dlg
        pid = dlg.duplicate_profile()
        controls.set_keys(pid, "file.import", ["Ctrl+Shift+I"])
        target = os.path.join(env.folder, "mine.json")
        asked = []
        editor.choose_export_file = lambda name: asked.append(name) or target
        dlg.export_button.click()
        assert asked == ["Classic Copy"]
        with open(target, encoding="utf-8") as fh:
            doc = json.load(fh)
        assert doc["format"] == "quartz-controls" and doc["keys"]["file.import"] == ["Ctrl+Shift+I"]
        editor.choose_import_file = lambda: target
        dlg.import_button.click()
        new = controls.active_id()
        assert new != pid and new.startswith("u-")
        assert controls.active().keys["file.import"][0][0] == "Ctrl+Shift+I"
        names = [dlg.profile_combo.itemText(i) for i in range(dlg.profile_combo.count())]
        assert len(names) == 4 and len(set(n.casefold() for n in names)) == 4
        assert dlg.profile_combo.currentData() == new
        bad = os.path.join(env.folder, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump({"format": "other"}, fh)
        errors = []
        editor.show_error = errors.append
        editor.choose_import_file = lambda: bad
        dlg.import_button.click()
        assert errors and controls.active_id() == new
        assert len(_store()["profiles"]) == 2
        editor.choose_import_file = lambda: None
        dlg.import_button.click()
        assert len(_store()["profiles"]) == 2


def test_profile_change_from_outside_reloads_the_dialog():
    with _Env() as env:
        dlg = env.dlg
        pid = controls.duplicate("standard")
        assert dlg.profile_combo.currentData() == pid
        assert not dlg.note.isVisibleTo(dlg)
        controls.set_keys(pid, "file.import", ["F7"])
        assert [c.text() for c in dlg.keyboard.chips("file.import")] == ["F7"]
        controls.select("classic")
        assert dlg.profile_combo.currentData() == "classic"
        assert dlg.note.isVisibleTo(dlg)


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
