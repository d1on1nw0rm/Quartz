from __future__ import annotations

import logging
import math
import os
import re
import weakref

import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from quartz_studio import APP_NAME, DOCUMENT_NAME, TITLE_SUFFIX, fileio
from quartz_studio.fileio import Document, FileFormatError, Node
from quartz_studio.scene import Mesh, get_scene

log = logging.getLogger("quartz_studio.project")

EXTENSION = ".quartz"
RECENT_LIMIT = 10
RECENT_KEY = "recent/files"
SETTINGS_FILE: str | None = None

ANSWER_SAVE = "save"
ANSWER_DISCARD = "discard"
ANSWER_CANCEL = "cancel"

_state: dict = {"path": None, "modified": False}
_windows: list = []
_bound = [None]
_busy = [0]
_quitting = [0]
_last_dir = [""]


def settings() -> QSettings:
    if SETTINGS_FILE:
        return QSettings(SETTINGS_FILE, QSettings.Format.IniFormat)
    return QSettings("Quartz", APP_NAME)


def _bind_scene():
    scene = get_scene()
    if _bound[0] is scene:
        return scene
    old = _bound[0]
    if old is not None:
        for signal in (old.changed, old.objectsChanged):
            try:
                signal.disconnect(_on_scene_changed)
            except (RuntimeError, TypeError):
                pass
    scene.changed.connect(_on_scene_changed)
    scene.objectsChanged.connect(_on_scene_changed)
    _bound[0] = scene
    return scene


def _on_scene_changed(*_args) -> None:
    if _busy[0] or _state["modified"]:
        return
    _state["modified"] = True
    refresh_title()


def is_modified() -> bool:
    _bind_scene()
    return bool(_state["modified"])


def current_path() -> str | None:
    return _state["path"]


def project_name() -> str:
    path = _state["path"]
    return os.path.basename(path) if path else DOCUMENT_NAME


def window_title() -> str:
    star = "*" if _state["modified"] else ""
    return f"{project_name()}{star} - {TITLE_SUFFIX}"


def _alive_windows() -> list:
    alive = []
    for ref in list(_windows):
        window = ref()
        if window is None:
            _windows.remove(ref)
        else:
            alive.append(window)
    return alive


def refresh_title() -> None:
    title = window_title()
    for window in _alive_windows():
        try:
            window.setWindowTitle(title)
        except RuntimeError:
            pass


def attach(window) -> None:
    _bind_scene()
    _windows.append(weakref.ref(window))
    _state["path"] = None
    _state["modified"] = False
    refresh_title()


def _set_clean(path: str | None) -> None:
    _state["path"] = os.path.abspath(path) if path else None
    _state["modified"] = False
    refresh_title()


def _canvas():
    for window in reversed(_alive_windows()):
        try:
            return window.viewport.canvas
        except (AttributeError, RuntimeError):
            continue
    return None


def _number(value, default: float, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number) or (positive and number <= 0.0):
        return default
    return number


def capture_view() -> dict | None:
    canvas = _canvas()
    if canvas is None:
        return None
    cam = canvas.camera
    return {
        "name": str(canvas.view_name),
        "position": [float(v) for v in cam.position()],
        "target": [float(v) for v in cam.target],
        "heading": float(cam.heading),
        "pitch": float(cam.pitch),
        "distance": float(cam.distance),
        "ortho": bool(cam.ortho),
        "focal": float(cam.focal),
    }


def apply_view(view) -> bool:
    canvas = _canvas()
    if canvas is None:
        return False
    from quartz_studio.widgets.viewport import VIEW_PRESETS, OrbitCamera

    cam = OrbitCamera()
    name = "Perspective"
    stored = isinstance(view, dict) and bool(view)
    if stored:
        cam.heading = _number(view.get("heading"), cam.heading)
        cam.pitch = _number(view.get("pitch"), cam.pitch)
        cam.distance = _number(view.get("distance"), cam.distance, True)
        cam.focal = _number(view.get("focal"), cam.focal, True)
        cam.ortho = bool(view.get("ortho", False))
        target = view.get("target")
        if isinstance(target, (list, tuple)) and len(target) == 3:
            cam.target = np.array([_number(v, 0.0) for v in target], float)
        if view.get("name") in VIEW_PRESETS:
            name = view["name"]
    canvas._view_states.clear()
    canvas._view_undo.clear()
    canvas._view_redo.clear()
    canvas._nav = None
    canvas.camera = cam
    canvas._set_view_name(name)
    canvas.update()
    return stored


def _frame(objs) -> None:
    canvas = _canvas()
    if canvas is None:
        return
    pts = [o.world_points() for o in objs if len(o.mesh.points)]
    if pts:
        canvas.frame_points(np.vstack(pts))


def _interactive() -> bool:
    return QGuiApplication.platformName() not in ("offscreen", "minimal")


def _parent():
    app = QApplication.instance()
    active = app.activeWindow() if app is not None else None
    if active is not None:
        return active
    windows = _alive_windows()
    return windows[-1] if windows else None


def _start_dir() -> str:
    path = _state["path"]
    if path:
        return os.path.dirname(path)
    return _last_dir[0] or os.path.expanduser("~")


def _remember_dir(path: str) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        _last_dir[0] = folder


def choose_open_files(title: str, directory: str, filters: list[str], multiple: bool = False) -> list[str]:
    if not _interactive():
        return []
    joined = ";;".join(filters)
    if multiple:
        paths, _chosen = QFileDialog.getOpenFileNames(_parent(), title, directory, joined)
        return [str(p) for p in paths]
    path, _chosen = QFileDialog.getOpenFileName(_parent(), title, directory, joined)
    return [str(path)] if path else []


def choose_save_file(title: str, path: str, filters: list[str]) -> str | None:
    if not _interactive():
        return None
    chosen_path, chosen = QFileDialog.getSaveFileName(_parent(), title, path, ";;".join(filters))
    if not chosen_path:
        return None
    if not os.path.splitext(chosen_path)[1]:
        pattern = r"\*(\.[A-Za-z0-9_]+)"
        found = re.search(pattern, chosen or "") or re.search(pattern, filters[0] if filters else "")
        if found:
            chosen_path += found.group(1)
    return str(chosen_path)


def ask_save_changes(name: str) -> str:
    if not _interactive():
        return ANSWER_DISCARD
    from quartz_studio.app import apply_native_titlebar

    box = QMessageBox(_parent())
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(APP_NAME)
    apply_native_titlebar(box)
    box.setText(f"Save changes to {name}?")
    box.setInformativeText("Your changes will be lost if you do not save them.")
    save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
    discard = box.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(save)
    box.setEscapeButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is save:
        return ANSWER_SAVE
    if clicked is discard:
        return ANSWER_DISCARD
    return ANSWER_CANCEL


def show_message(kind: str, text: str) -> None:
    (log.error if kind == "error" else log.warning)("%s", text)
    if not _interactive():
        return
    if kind == "error":
        QMessageBox.critical(_parent(), APP_NAME, text)
    else:
        QMessageBox.warning(_parent(), APP_NAME, text)


def quit_application() -> None:
    app = QApplication.instance()
    if app is not None:
        app.quit()


def _quartz_filter() -> str:
    return fileio.file_filter(fileio.get("quartz"))


def _with_extension(path: str, extensions: tuple[str, ...]) -> str:
    if os.path.splitext(path)[1].lower() in extensions:
        return path
    return path + extensions[0]


def recent_files() -> list[str]:
    value = settings().value(RECENT_KEY, [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(v) for v in value if v][:RECENT_LIMIT]


def _store_recent(paths: list[str]) -> None:
    store = settings()
    if paths:
        store.setValue(RECENT_KEY, paths[:RECENT_LIMIT])
    else:
        store.remove(RECENT_KEY)
    store.sync()


def _same(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def add_recent(path: str) -> None:
    path = os.path.abspath(path)
    paths = [p for p in recent_files() if not _same(p, path)]
    _store_recent([path] + paths)


def remove_recent(path: str) -> None:
    _store_recent([p for p in recent_files() if not _same(p, path)])


def clear_recent() -> None:
    _store_recent([])


def confirm_discard() -> bool:
    if _quitting[0] or not is_modified():
        return True
    answer = ask_save_changes(project_name())
    if answer == ANSWER_SAVE:
        return save_project()
    return answer == ANSWER_DISCARD


def _default_document() -> Document:
    meta = {"unit": "cm", "up": "y", "handedness": "right", "source": "Quartz Studio",
            "active": 0, "selected": True, "mode": "model"}
    return Document([Node("Cube", Mesh.cube(200.0))], meta)


def new_project() -> bool:
    if not confirm_discard():
        return False
    scene = _bind_scene()
    _busy[0] += 1
    try:
        fileio.replace_scene(scene, _default_document())
        apply_view(None)
    finally:
        _busy[0] -= 1
    _set_clean(None)
    return True


def _open_path(path: str) -> bool:
    scene = _bind_scene()
    name = os.path.basename(path)
    if os.path.splitext(path)[1].lower() != EXTENSION:
        show_message("error", f"{name}: not a Quartz project (use File > Import for other formats)")
        return False
    meta: dict = {}
    _busy[0] += 1
    try:
        fileio.open_scene(scene, path, meta)
    except (FileFormatError, OSError) as exc:
        show_message("error", _error_text(path, exc))
        return False
    else:
        if not apply_view(meta.get("view")):
            canvas = _canvas()
            if canvas is not None:
                canvas.frame_all()
    finally:
        _busy[0] -= 1
    _set_clean(path)
    add_recent(path)
    _remember_dir(path)
    _show_warnings(meta)
    return True


def _error_text(path, exc: Exception) -> str:
    name = os.path.basename(os.fspath(path))
    text = str(exc)
    return text if name in text else f"{name}: {text}"


def _show_warnings(meta: dict) -> None:
    unique: list[str] = []
    for text in meta.get("warnings") or []:
        if text not in unique:
            unique.append(text)
    if unique:
        show_message("warning", "\n".join(unique))


def open_project() -> bool:
    paths = choose_open_files("Open Project", _start_dir(), [_quartz_filter()])
    if not paths:
        return False
    if not confirm_discard():
        return False
    return _open_path(paths[0])


def open_recent(path: str) -> bool:
    if not os.path.isfile(path):
        remove_recent(path)
        show_message("error", f"{os.path.basename(path)}: file not found")
        return False
    if not confirm_discard():
        return False
    return _open_path(path)


def _write_project(path: str) -> bool:
    scene = _bind_scene()
    try:
        fileio.save_scene(scene, path, capture_view())
    except (FileFormatError, OSError) as exc:
        show_message("error", str(exc))
        return False
    _set_clean(path)
    add_recent(path)
    _remember_dir(path)
    return True


def save_project() -> bool:
    _bind_scene()
    if _state["path"] is None:
        return save_project_as()
    return _write_project(_state["path"])


def save_project_as() -> bool:
    _bind_scene()
    suggested = _state["path"] or os.path.join(_start_dir(), DOCUMENT_NAME + EXTENSION)
    path = choose_save_file("Save Project As", suggested, [_quartz_filter()])
    if not path:
        return False
    return _write_project(_with_extension(path, (EXTENSION,)))


def next_incremental(path: str) -> str:
    base, ext = os.path.splitext(path)
    found = re.fullmatch(r"(.*?)_(\d+)", base)
    stem, number, width = (found.group(1), int(found.group(2)), max(4, len(found.group(2)))) \
        if found else (base, 0, 4)
    while True:
        number += 1
        candidate = f"{stem}_{number:0{width}d}{ext}"
        if not os.path.exists(candidate):
            return candidate


def save_incremental() -> bool:
    _bind_scene()
    if _state["path"] is None:
        return save_project_as()
    return _write_project(next_incremental(_state["path"]))


def import_paths(paths) -> list:
    scene = _bind_scene()
    added: list = []
    errors: list[str] = []
    warnings: list[str] = []
    scene.begin_group()
    try:
        for path in paths:
            meta: dict = {}
            try:
                added.extend(fileio.import_file(scene, path, meta))
            except (FileFormatError, OSError) as exc:
                errors.append(_error_text(path, exc))
                continue
            _remember_dir(str(path))
            for text in meta.get("warnings") or []:
                if text not in warnings:
                    warnings.append(text)
    finally:
        scene.end_group()
    if added:
        _frame(added)
    if errors:
        show_message("error", "\n".join(errors))
    if warnings:
        show_message("warning", "\n".join(warnings))
    return added


def merge_project() -> list:
    paths = choose_open_files("Merge Project", _start_dir(), [_quartz_filter()])
    return import_paths(paths) if paths else []


def import_files() -> list:
    paths = choose_open_files("Import", _start_dir(), fileio.import_filters(), True)
    return import_paths(paths) if paths else []


def _export_name(extension: str) -> str:
    stem = os.path.splitext(project_name())[0]
    return os.path.join(_start_dir(), stem + extension)


def _export(title: str, filters: list[str], extension: str, selected_only: bool, fmt) -> bool:
    scene = _bind_scene()
    path = choose_save_file(title, _export_name(extension), filters)
    if not path:
        return False
    if fmt is not None:
        path = _with_extension(path, fmt.extensions)
    try:
        fileio.export_file(scene, path, selected_only=selected_only)
    except (FileFormatError, OSError) as exc:
        show_message("error", str(exc))
        return False
    _remember_dir(path)
    return True


def export_as(format_id: str) -> bool:
    fmt = fileio.get(format_id)
    return _export(f"Export {fmt.label}", [fileio.file_filter(fmt)], fmt.extensions[0], False, fmt)


def export_selection() -> bool:
    scene = _bind_scene()
    if scene.active is None or not scene.object_selected:
        show_message("error", "Select an object to export.")
        return False
    filters = fileio.export_filters()
    first = fileio.exporters()[0].extensions[0] if fileio.exporters() else ""
    return _export("Export Selection", filters, first, True, None)


def exit_app() -> bool:
    if not confirm_discard():
        return False
    _quitting[0] += 1
    try:
        quit_application()
    finally:
        _quitting[0] -= 1
    return True


def paths_from_argv(argv) -> list[str]:
    return [a for a in list(argv)[1:] if not a.startswith("-") and fileio.by_path(a) is not None]


def open_paths(paths) -> None:
    paths = [os.fspath(p) for p in paths]
    quartz = [p for p in paths if os.path.splitext(p)[1].lower() == EXTENSION]
    others = [p for p in paths if p not in quartz]
    if quartz:
        if confirm_discard():
            _open_path(quartz[0])
        others = quartz[1:] + others
    if others:
        import_paths(others)
