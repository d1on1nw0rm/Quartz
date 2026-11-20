from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QVBoxLayout, QWidget

from . import engine
from .camera import from_canvas
from .objects import CAMERA_KIND, LIGHT_KIND
from .settings import get_settings
from .worker import get_manager

__all__ = ["KeyAction", "commands", "docks", "pages", "key_actions", "render_view", "render_to_picture_viewer",
           "render_animation", "cancel_render", "edit_render_settings", "show_picture_viewer",
           "show_render_view", "add_light", "add_camera_from_view", "euler_from_axes", "find_dock",
           "DOCK_SETTINGS", "DOCK_VIEWER", "DOCK_VIEW", "PAGE_NAME"]

DOCK_SETTINGS = "Render Settings"
DOCK_VIEWER = "Picture Viewer"
DOCK_VIEW = "Render View"
PAGE_NAME = "Render"
MAX_VIEW_W = 1920

_WINDOWS: dict = {}


class KeyAction(tuple):

    def __new__(cls, name: str, shortcut: str, callback=None):
        obj = super().__new__(cls, (name, shortcut))
        obj.callback = callback
        return obj

    @property
    def name(self) -> str:
        return self[0]

    @property
    def shortcut(self) -> str:
        return self[1]


def _scene(scene=None):
    if scene is not None:
        return scene
    from ..scene import get_scene
    return get_scene()


def find_dock(title: str) -> QDockWidget | None:
    app = QApplication.instance()
    if app is None:
        return None
    for w in app.allWidgets():
        if isinstance(w, QDockWidget) and (w.windowTitle() == title or w.objectName() == title):
            return w
    return None


def _factory_for(title: str):
    from .widgets import PictureViewer, RenderSettingsPanel, RenderView
    return {DOCK_SETTINGS: RenderSettingsPanel, DOCK_VIEWER: PictureViewer, DOCK_VIEW: RenderView}[title]


def _show(title: str, scene=None) -> QWidget | None:
    dock = find_dock(title)
    if dock is not None:
        dock.show()
        dock.raise_()
        return dock.widget()
    app = QApplication.instance()
    if app is None:
        return None
    win = _WINDOWS.get(title)
    if win is None:
        win = QWidget(None, Qt.WindowType.Window)
        win.setWindowTitle(title)
        lay = QVBoxLayout(win)
        lay.setContentsMargins(0, 0, 0, 0)
        content = _factory_for(title)(_scene(scene), win)
        lay.addWidget(content)
        win.content = content
        sizes = {DOCK_SETTINGS: (384, 640), DOCK_VIEWER: (896, 576), DOCK_VIEW: (640, 448)}
        win.resize(*sizes[title])
        _WINDOWS[title] = win
    win.show()
    win.raise_()
    return win.content


def show_picture_viewer(scene=None) -> QWidget | None:
    return _show(DOCK_VIEWER, scene)


def show_render_view(scene=None) -> QWidget | None:
    return _show(DOCK_VIEW, scene)


def edit_render_settings(scene=None) -> QWidget | None:
    return _show(DOCK_SETTINGS, scene)


def render_view(scene=None) -> bool:
    scene = _scene(scene)
    canvas = engine.active_canvas()
    width = height = None
    if canvas is not None:
        rect = canvas.film_rect()
        w, h = int(rect.width()), int(rect.height())
        if w > MAX_VIEW_W:
            h = int(h * MAX_VIEW_W / w)
            w = MAX_VIEW_W
        width, height = max(16, w), max(16, h)
    view = None
    if QApplication.instance() is not None:
        from .widgets import RenderView, visible_render_view
        if find_dock(DOCK_VIEW) is not None:
            shown = show_render_view(scene)
            view = shown if isinstance(shown, RenderView) else None
        if view is None:
            view = visible_render_view()
        if view is not None and view.scene is scene:
            view.render()
            return True
        show_picture_viewer(scene)
    return get_manager().render(scene, camera=canvas, width=width, height=height, target="view",
                                animation=False, label="View")


def render_to_picture_viewer(scene=None) -> bool:
    scene = _scene(scene)
    if QApplication.instance() is not None:
        show_picture_viewer(scene)
    return get_manager().render(scene, target="viewer", label="Picture")


def render_animation(scene=None) -> bool:
    scene = _scene(scene)
    if QApplication.instance() is not None:
        show_picture_viewer(scene)
    return get_manager().render(scene, target="viewer", animation=True, label="Frame")


def cancel_render(scene=None) -> bool:
    return get_manager().cancel()


def euler_from_axes(right, up, forward) -> np.ndarray:
    m = np.stack([np.asarray(right, float), np.asarray(up, float), np.asarray(forward, float)], axis=1)
    xy = math.hypot(m[0, 0], m[1, 0])
    b = math.atan2(-m[2, 0], xy)
    if xy > 1e-9:
        a = math.atan2(m[2, 1], m[2, 2])
        c = math.atan2(m[1, 0], m[0, 0])
    else:
        a = 0.0
        c = math.atan2(-m[0, 1], m[1, 1])
    return np.degrees(np.array([a, b, c], float))


def _aim(obj, target) -> None:
    pos = np.asarray(obj.position, float)
    fwd = np.asarray(target, float) - pos
    n = float(np.linalg.norm(fwd))
    if n < 1e-9:
        return
    fwd = fwd / n
    up = np.array([0.0, 1.0, 0.0]) if abs(fwd[1]) < 0.95 else np.array([0.0, 0.0, 1.0])
    right = np.cross(up, fwd)
    right = right / np.linalg.norm(right)
    up = np.cross(fwd, right)
    obj.rotation = euler_from_axes(right, up, fwd)


LIGHT_PLACES = {
    "Point": (np.array([250.0, 400.0, -250.0]), None),
    "Spot": (np.array([300.0, 600.0, -400.0]), np.zeros(3)),
    "Infinite": (np.array([0.0, 500.0, 0.0]), np.array([-200.0, 0.0, 300.0])),
    "Area": (np.array([0.0, 450.0, -350.0]), np.zeros(3)),
}


def add_light(light_type: str = "Point", scene=None):
    scene = _scene(scene)
    scene.begin_group()
    try:
        obj = scene.add_parametric(LIGHT_KIND, name=f"{light_type} Light")
        obj.params["light_type"] = light_type
        if light_type == "Infinite":
            obj.params["falloff"] = "None"
        pos, target = LIGHT_PLACES.get(light_type, LIGHT_PLACES["Point"])
        obj.position = pos.copy()
        if target is not None:
            _aim(obj, target)
        obj._dirty = True
        scene.evaluate()
    finally:
        scene.end_group()
    scene.changed.emit()
    return obj


def add_camera_from_view(scene=None):
    scene = _scene(scene)
    canvas = engine.active_canvas()
    cam = from_canvas(canvas) if canvas is not None else engine.resolve_camera(scene, None, get_settings(scene))
    scene.begin_group()
    try:
        obj = scene.add_parametric(CAMERA_KIND, name="Camera")
        obj.position = np.asarray(cam.eye, float).copy()
        obj.rotation = euler_from_axes(cam.right, cam.up, cam.forward)
        obj.params["focal_length"] = float(cam.focal) * 36.0
        obj.params["sensor_width"] = 36.0
        if cam.ortho:
            obj.params["projection"] = "Parallel"
            obj.params["ortho_width"] = float(cam.ortho_width)
        obj._dirty = True
        scene.evaluate()
    finally:
        scene.end_group()
    scene.changed.emit()
    return obj


def commands() -> list:
    return [
        (("Render", "Render View"), lambda: render_view()),
        (("Render", "Render to Picture Viewer"), lambda: render_to_picture_viewer()),
        (("Render", "Render Animation"), lambda: render_animation()),
        (("Render", "Cancel Render"), lambda: cancel_render()),
        (("Render", "Edit Render Settings"), lambda: edit_render_settings()),
        (("Render", "Picture Viewer"), lambda: show_picture_viewer()),
        (("Render", "Interactive Render View"), lambda: show_render_view()),
        (("Render", "Add Light", "Point Light"), lambda: add_light("Point")),
        (("Render", "Add Light", "Spot Light"), lambda: add_light("Spot")),
        (("Render", "Add Light", "Infinite Light"), lambda: add_light("Infinite")),
        (("Render", "Add Light", "Area Light"), lambda: add_light("Area")),
        (("Render", "Add Camera from View"), lambda: add_camera_from_view()),
    ]


def _make(title: str):
    def factory(scene=None, parent: QWidget | None = None) -> QWidget:
        return _factory_for(title)(scene, parent)
    factory.__name__ = "make_" + title.lower().replace(" ", "_")
    return factory


def docks() -> list:
    return [
        (DOCK_SETTINGS, _make(DOCK_SETTINGS), "right"),
        (DOCK_VIEWER, _make(DOCK_VIEWER), "bottom"),
        (DOCK_VIEW, _make(DOCK_VIEW), "right"),
    ]


def pages() -> list:
    return [(PAGE_NAME, [DOCK_VIEWER, DOCK_SETTINGS, DOCK_VIEW])]


def key_actions() -> list:
    return [
        KeyAction("Render View", "Ctrl+R", lambda: render_view()),
        KeyAction("Render to Picture Viewer", "Shift+R", lambda: render_to_picture_viewer()),
        KeyAction("Edit Render Settings", "Ctrl+B", lambda: edit_render_settings()),
    ]
