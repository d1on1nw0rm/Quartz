from __future__ import annotations

import sys

from . import api, paths
from .examples import EXAMPLE_PLUGINS, EXAMPLE_SCRIPTS, install_examples
from .library import ScriptLibrary, get_library, sanitize_name
from .plugins import PLUGIN_TYPES, PluginAPI, PluginLoader, PluginRecord, get_loader, reset_loader
from .pytags import (FrameDriver, TagRunResult, TagType, register_tag_type, run_python_tags,
                     run_tags, tag_types, unregister_tag_type)
from .runner import ExecResult, execute, make_namespace

__all__ = [
    "api",
    "paths",
    "ExecResult",
    "execute",
    "make_namespace",
    "ScriptLibrary",
    "get_library",
    "sanitize_name",
    "PLUGIN_TYPES",
    "PluginAPI",
    "PluginLoader",
    "PluginRecord",
    "get_loader",
    "reset_loader",
    "FrameDriver",
    "TagRunResult",
    "TagType",
    "register_tag_type",
    "unregister_tag_type",
    "tag_types",
    "run_python_tags",
    "run_tags",
    "EXAMPLE_SCRIPTS",
    "EXAMPLE_PLUGINS",
    "install_examples",
    "PANEL_TITLES",
    "commands",
    "docks",
    "pages",
    "key_actions",
    "show_panel",
    "run_user_script",
    "reload_plugins",
    "open_scripts_folder",
    "install_frame_driver",
    "frame_driver",
    "set_tags_on_frame_change",
    "get_binder",
]

sys.modules.setdefault("quartz", api)

SCRIPT_MANAGER = "Script Manager"
CONSOLE = "Console"
PLUGIN_MANAGER = "Plugin Manager"
PANEL_TITLES = (SCRIPT_MANAGER, CONSOLE, PLUGIN_MANAGER)

_WINDOWS: dict = {}
_DRIVERS: dict = {}


def _factory(title: str):
    def make(scene=None, parent=None):
        install_frame_driver()
        if title == SCRIPT_MANAGER:
            from .manager import ScriptManager
            return ScriptManager(scene, parent)
        if title == CONSOLE:
            from .console import ScriptConsole
            return ScriptConsole(scene, parent)
        from .plugin_panel import PluginManager
        return PluginManager(scene, parent)
    make.__name__ = "make_" + title.lower().replace(" ", "_")
    return make


def _main_windows() -> list:
    from PySide6.QtWidgets import QApplication, QMainWindow
    app = QApplication.instance()
    if app is None:
        return []
    return [w for w in app.topLevelWidgets() if isinstance(w, QMainWindow)]


def show_panel(title: str, scene=None):
    from PySide6.QtWidgets import QDockWidget
    if title not in PANEL_TITLES:
        raise KeyError(title)
    for win in _main_windows():
        for dock in win.findChildren(QDockWidget):
            if dock.windowTitle() == title:
                dock.show()
                dock.raise_()
                inner = dock.widget()
                if inner is not None:
                    inner.setFocus()
                return dock
    window = _WINDOWS.get(title)
    alive = window is not None
    if alive:
        try:
            window.isVisible()
        except RuntimeError:
            alive = False
    if not alive:
        from PySide6.QtCore import Qt
        window = _factory(title)(scene)
        window.setWindowTitle(title)
        window.setWindowFlag(Qt.WindowType.Window, True)
        window.resize(768, 512)
        _WINDOWS[title] = window
    window.show()
    window.raise_()
    window.activateWindow()
    return window


def run_user_script(name: str, scene=None) -> ExecResult:
    result = get_library().run(name, scene)
    api.message(result.summary())
    if not result.ok:
        print(result.error, file=sys.stderr)
    elif result.stdout:
        print(result.stdout, end="")
    return result


def reload_plugins() -> list:
    loader = get_loader()
    records = loader.reload()
    errors = loader.errors()
    api.message(f"Loaded {len(records)} plugins" + (f", {len(errors)} with errors" if errors else ""))
    return records


def open_scripts_folder(launch: bool = True) -> str:
    folder = str(paths.scripts_dir())
    if launch:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
    return folder


def install_frame_driver(scene=None) -> FrameDriver:
    key = "global" if scene is None else id(scene)
    driver = _DRIVERS.get(key)
    if driver is None or (scene is not None and driver.scene is not scene):
        driver = FrameDriver(scene, follow_global=scene is None)
        _DRIVERS[key] = driver
    elif not driver.installed:
        driver.install()
    return driver


def frame_driver(scene=None) -> FrameDriver | None:
    return _DRIVERS.get("global" if scene is None else id(scene))


def set_tags_on_frame_change(flag: bool | None = None) -> bool:
    driver = install_frame_driver()
    driver.enabled = (not driver.enabled) if flag is None else bool(flag)
    api.message("Python tags run on frame change" if driver.enabled else "Python tags paused")
    return driver.enabled


def get_binder(install: bool = True):
    from .shortcuts import get_binder as _get
    return _get(install)


def _run_tags_now() -> list:
    results = run_tags()
    failed = [r for r in results if not r.ok]
    api.message(f"Ran {len(results)} tags" + (f", {len(failed)} failed" if failed else ""))
    for r in failed:
        print(f"{r.object_name} / {r.tag_name}:\n{r.error}", file=sys.stderr)
    return results


def commands() -> list:
    out = [
        (("Extensions", SCRIPT_MANAGER), lambda: show_panel(SCRIPT_MANAGER)),
        (("Extensions", CONSOLE), lambda: show_panel(CONSOLE)),
        (("Extensions", PLUGIN_MANAGER), lambda: show_panel(PLUGIN_MANAGER)),
        (("Extensions", "Reload Plugins"), reload_plugins),
        (("Extensions", "Run Python Tags"), _run_tags_now),
        (("Extensions", "Python Tags On Frame Change"), lambda: set_tags_on_frame_change()),
        (("Extensions", "Install Examples"), lambda: install_examples()),
        (("Extensions", "Open Scripts Folder"), lambda: open_scripts_folder()),
    ]
    for name in get_library().list():
        out.append((("Extensions", "Scripts", name[:-3]), lambda n=name: run_user_script(n)))
    loader = get_loader()
    loader.ensure_loaded()
    taken = {p for p, _f in out}
    for path, fn in loader.commands():
        if path not in taken:
            out.append((path, fn))
            taken.add(path)
    return out


def key_actions() -> list:
    install_frame_driver()
    try:
        from PySide6.QtCore import QCoreApplication
        if QCoreApplication.instance() is not None:
            get_binder()
    except ImportError:
        pass
    out = []
    lib = get_library()
    for name, keys in sorted(lib.shortcuts().items()):
        out.append((keys, lambda n=name: run_user_script(n), f"Run script {name[:-3]}"))
    loader = get_loader()
    loader.ensure_loaded()
    out += loader.shortcuts()
    return out


def docks() -> list:
    return [
        (SCRIPT_MANAGER, _factory(SCRIPT_MANAGER), "bottom"),
        (CONSOLE, _factory(CONSOLE), "bottom"),
        (PLUGIN_MANAGER, _factory(PLUGIN_MANAGER), "right"),
    ]


def pages() -> list:
    return [("Script", [SCRIPT_MANAGER, CONSOLE])]
