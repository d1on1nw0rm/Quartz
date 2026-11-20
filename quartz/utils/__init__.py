from __future__ import annotations

import datetime
import importlib
import math
import os
import re
import sys
import traceback
import types
from typing import Callable, Iterator, Sequence

import quartz.app
import quartz.path as qpath
from quartz import registry
from quartz.app import paths as app_paths
from quartz.app import translations
from quartz.errors import NotImplementedInQuartz, PropertyTypeError
from quartz.rna import hooks
from quartz.rna.datapath import escape_identifier, unescape_identifier
from quartz.utils import previews, units

__all__ = [
    "previews", "units", "register_class", "unregister_class", "register_classes_factory",
    "register_submodule_factory", "escape_identifier", "unescape_identifier", "flip_name", "user_resource",
    "resource_path", "system_resource", "script_path_user", "script_paths", "script_paths_pref",
    "script_paths_system_environment", "extension_path_user", "execfile", "time_from_frame", "time_to_frame",
    "smpte_from_frame", "smpte_from_seconds", "register_manual_map", "unregister_manual_map", "manual_map",
    "manual_language_code", "register_preset_path", "unregister_preset_path", "preset_paths", "preset_find",
    "register_cli_command", "unregister_cli_command", "register_tool", "unregister_tool", "keyconfig_init",
    "keyconfig_set", "load_scripts", "load_scripts_extensions", "refresh_script_paths", "modules_from_path",
    "blend_paths", "is_path_builtin", "is_path_extension", "app_template_paths", "make_rna_paths",
    "expose_bundled_modules",
]

register_class = registry.register_class
unregister_class = registry.unregister_class

_MANUAL_HOOKS: list[Callable] = []
_PRESET_PATHS: list[str] = []
_CLI_COMMANDS: dict[str, tuple[object, Callable]] = {}
_TOOLS: list[tuple[type, dict]] = []


class _CLICommandHandle:
    __slots__ = ("id",)

    def __init__(self, ident: str) -> None:
        self.id = ident

    def __repr__(self) -> str:
        return f"<cli command {self.id!r}>"


def _enum_error(func: str, value: object, items: Sequence[str]) -> PropertyTypeError:
    listing = ", ".join(repr(i) for i in items)
    return PropertyTypeError(f'{func}(): enum "{value}" not found in ({listing})')


def register_classes_factory(classes: Sequence[type]) -> tuple[Callable[[], None], Callable[[], None]]:
    classes = tuple(classes)

    def register() -> None:
        for cls in classes:
            register_class(cls)

    def unregister() -> None:
        for cls in reversed(classes):
            unregister_class(cls)
    return register, unregister


def register_submodule_factory(module_name: str, submodule_names: Sequence[str]
                               ) -> tuple[Callable[[], None], Callable[[], None]]:
    names = tuple(submodule_names)

    def register() -> None:
        for name in names:
            mod = importlib.import_module(f"{module_name}.{name}")
            mod.register()

    def unregister() -> None:
        for name in reversed(names):
            full = f"{module_name}.{name}"
            mod = sys.modules.get(full)
            if mod is not None:
                mod.unregister()
                del sys.modules[full]
    return register, unregister


_SIDE_SWAP = {"L": "R", "R": "L", "l": "r", "r": "l"}
_SEPARATORS = ".-_ "
_WORD_SWAP = (("left", "right"), ("Left", "Right"), ("LEFT", "RIGHT"),
              ("right", "left"), ("Right", "Left"), ("RIGHT", "LEFT"))


def flip_name(name: str, strip_digits: bool = False) -> str:
    match = re.match(r"^(.*?)(\.\d+)$", name)
    base, number = (match.group(1), match.group(2)) if match else (name, "")
    if len(base) >= 2 and base[-2] in _SEPARATORS and base[-1] in _SIDE_SWAP:
        base = base[:-1] + _SIDE_SWAP[base[-1]]
    elif len(base) >= 2 and base[0] in _SIDE_SWAP and base[1] in _SEPARATORS:
        base = _SIDE_SWAP[base[0]] + base[1:]
    else:
        done = False
        for word, repl in _WORD_SWAP:
            if base.startswith(word):
                base = repl + base[len(word):]
                done = True
                break
        if not done:
            for word, repl in _WORD_SWAP:
                if base.endswith(word):
                    base = base[:-len(word)] + repl
                    break
    return base if strip_digits else base + number


_USER_RESOURCES = {
    "DATAFILES": app_paths.datafiles_dir, "CONFIG": app_paths.config_dir,
    "SCRIPTS": app_paths.scripts_dir, "EXTENSIONS": app_paths.extensions_dir,
}
_SYSTEM_RESOURCES = ("DATAFILES", "SCRIPTS", "EXTENSIONS", "PYTHON")
_RESOURCE_TYPES = ("USER", "LOCAL", "SYSTEM")


def user_resource(resource_type: str, *, path: str = "", create: bool = False) -> str:
    func = _USER_RESOURCES.get(resource_type) if isinstance(resource_type, str) else None
    if func is None:
        raise _enum_error("user_resource", resource_type, tuple(_USER_RESOURCES))
    base = str(func())
    target = os.path.join(base, path) if path else base
    if create:
        os.makedirs(target, exist_ok=True)
    return target


def _version_part(value: object, index: int, what: str) -> int:
    if value is None:
        return int(quartz.app.version[index])
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"resource_path(): {what} expected an int, not {type(value).__name__}")
    return value


def resource_path(type: str, *, major: int | None = None, minor: int | None = None) -> str:
    _version_part(major, 0, "major")
    _version_part(minor, 1, "minor")
    if type == "USER":
        return str(app_paths.user_dir())
    if type == "LOCAL":
        return str(app_paths.PROJECT_ROOT)
    if type == "SYSTEM":
        return ""
    raise _enum_error("resource_path", type, _RESOURCE_TYPES)


def system_resource(type: str, *, path: str = "") -> str:
    if type not in _SYSTEM_RESOURCES:
        raise _enum_error("system_resource", type, _SYSTEM_RESOURCES)
    return ""


def script_path_user() -> str:
    return str(app_paths.scripts_dir())


def script_paths_pref() -> list[str]:
    return []


def script_paths_system_environment() -> list[str]:
    return []


def script_paths(*, subdir: str | None = None, user_pref: bool = True, check_all: bool = False, use_user: bool = True,
                 use_system_environment: bool = True) -> list[str]:
    bases: list[str] = []
    if use_user:
        bases.append(script_path_user())
    if user_pref:
        bases.extend(script_paths_pref())
    if use_system_environment:
        bases.extend(script_paths_system_environment())
    out: list[str] = []
    for base in bases:
        candidate = os.path.join(base, subdir) if subdir else base
        if candidate in out:
            continue
        if not check_all and not os.path.isdir(candidate):
            continue
        out.append(candidate)
    return out


def extension_path_user(package: str, *, path: str = "", create: bool = False) -> str:
    parts = package.split(".") if isinstance(package, str) else []
    if len(parts) < 3 or parts[0] not in ("bl_ext", "qz_ext") or not all(parts[:3]):
        raise ValueError(f"extension_path_user(): '{package}' is not an extension package "
                         "(expected 'bl_ext.<repo>.<package>' or 'qz_ext.<repo>.<package>')")
    target = str(app_paths.extensions_dir() / ".user" / parts[1] / parts[2])
    if path:
        target = os.path.join(target, path)
    if create:
        os.makedirs(target, exist_ok=True)
    return target


_MISSING = object()


def execfile(filepath: str, *, mod: types.ModuleType | None = None) -> types.ModuleType:
    if mod is None:
        mod = types.ModuleType("__main__")
    mod.__file__ = filepath
    previous = sys.modules.get("__main__", _MISSING)
    sys.modules["__main__"] = mod
    try:
        with open(filepath, "rb") as handle:
            source = handle.read()
        exec(compile(source, filepath, "exec"), mod.__dict__)
    finally:
        if previous is _MISSING:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = previous
    return mod


def _rate(fps: float | None, fps_base: float | None) -> float:
    if fps is None:
        try:
            render = hooks.current_context().scene.render
            fps = render.fps
            if fps_base is None:
                fps_base = render.fps_base
        except AttributeError:
            fps = 24
    if fps_base is None:
        fps_base = 1.0
    return float(fps) / float(fps_base)


def time_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> datetime.timedelta:
    return datetime.timedelta(seconds=float(frame) / _rate(fps, fps_base))


def time_to_frame(time: float | datetime.timedelta, *, fps: float | None = None,
                  fps_base: float | None = None) -> float:
    seconds = time.total_seconds() if isinstance(time, datetime.timedelta) else float(time)
    return seconds * _rate(fps, fps_base)


def _smpte(seconds: float, rate: float) -> str:
    sign = "-" if seconds < 0 else ""
    t = abs(seconds)
    hours = int(t // 3600)
    minutes = int(t // 60 % 60)
    secs = int(t % 60)
    frames = min(int(round((t - int(t)) * rate)), max(math.ceil(rate) - 1, 0))
    return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def smpte_from_seconds(time: float, *, fps: float | None = None, fps_base: float | None = None) -> str:
    seconds = time.total_seconds() if isinstance(time, datetime.timedelta) else float(time)
    return _smpte(seconds, _rate(fps, fps_base))


def smpte_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> str:
    rate = _rate(fps, fps_base)
    return _smpte(float(frame) / rate, rate)


def register_manual_map(manual_hook: Callable) -> None:
    _MANUAL_HOOKS.append(manual_hook)


def unregister_manual_map(manual_hook: Callable) -> None:
    _MANUAL_HOOKS.remove(manual_hook)


def manual_map() -> Iterator:
    for hook in list(_MANUAL_HOOKS):
        yield hook()


def manual_language_code(default: str = "en") -> str:
    lang = translations.locale_explode(translations.locale)[0]
    return lang if lang else default


def register_preset_path(path: str) -> bool:
    if path in _PRESET_PATHS:
        return False
    _PRESET_PATHS.append(path)
    return True


def unregister_preset_path(path: str) -> bool:
    if path in _PRESET_PATHS:
        _PRESET_PATHS.remove(path)
        return True
    return False


def preset_paths(subdir: str) -> list[str]:
    out: list[str] = []
    for base in script_paths(subdir="presets") + list(_PRESET_PATHS):
        candidate = os.path.join(base, subdir) if subdir else base
        if os.path.isdir(candidate) and candidate not in out:
            out.append(candidate)
    return out


def preset_find(name: str, preset_path: str, display_name: bool = False, ext: str = ".py") -> str | None:
    for directory in preset_paths(preset_path):
        try:
            entries = sorted(os.listdir(directory))
        except OSError:
            continue
        if display_name:
            for fname in entries:
                full = os.path.join(directory, fname)
                if os.path.isfile(full) and qpath.display_name(fname) == name:
                    return full
        else:
            full = os.path.join(directory, name + ext)
            if os.path.isfile(full):
                return full
    return None


def register_cli_command(id: str, execute: Callable) -> object:
    if id in _CLI_COMMANDS:
        raise ValueError(f"register_cli_command(): command '{id}' is already registered")
    handle = _CLICommandHandle(id)
    _CLI_COMMANDS[id] = (handle, execute)
    return handle


def unregister_cli_command(handle: object) -> None:
    for ident, (h, _fn) in list(_CLI_COMMANDS.items()):
        if h is handle:
            del _CLI_COMMANDS[ident]
            return
    raise ValueError(f"unregister_cli_command(): unknown handle {handle!r}")


def register_tool(tool_cls: type, *, after: object = None, separator: bool = False, group: bool = False) -> None:
    for cls, _opts in _TOOLS:
        if cls is tool_cls:
            raise ValueError(f"register_tool(): tool '{getattr(tool_cls, '__name__', tool_cls)}' already registered")
    _TOOLS.append((tool_cls, {"after": after, "separator": separator, "group": group}))


def unregister_tool(tool_cls: type) -> None:
    for i, (cls, _opts) in enumerate(_TOOLS):
        if cls is tool_cls:
            del _TOOLS[i]
            return
    raise ValueError(f"unregister_tool(): tool '{getattr(tool_cls, '__name__', tool_cls)}' is not registered")


def keyconfig_init() -> None:
    return None


def keyconfig_set(filepath: str, *, report: Callable | None = None) -> None:
    raise NotImplementedInQuartz("bpy.utils.keyconfig_set")


def load_scripts(*, reload_scripts: bool = False, refresh_scripts: bool = False, extensions: bool = True) -> None:
    return None


def load_scripts_extensions(*, reload_scripts: bool = False) -> None:
    return None


def expose_bundled_modules() -> None:
    return None


def refresh_script_paths() -> None:
    for base in script_paths():
        candidate = os.path.join(base, "modules")
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.append(candidate)


def modules_from_path(path: str, loaded_modules: set[str]) -> list[types.ModuleType]:
    result: list[types.ModuleType] = []
    for name, _filepath in qpath.module_names(path):
        if name in loaded_modules:
            continue
        try:
            mod = importlib.import_module(name)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            continue
        loaded_modules.add(name)
        result.append(mod)
    return result


def blend_paths(*, absolute: bool = False, packed: bool = False, local: bool = False) -> list[str]:
    session_mod = importlib.import_module("quartz.session")
    data = session_mod.current().data
    out: list[str] = []
    for coll_name in ("images", "texts"):
        coll = getattr(data, coll_name, None)
        if coll is None:
            continue
        for item in coll:
            filepath = getattr(item, "filepath", "")
            if not filepath:
                continue
            if absolute:
                filepath = qpath.abspath(filepath)
            if filepath not in out:
                out.append(filepath)
    return out


def is_path_builtin(path: str) -> bool:
    return qpath.is_subdir(path, str(app_paths.PROJECT_ROOT / "quartz")) or \
        qpath.is_subdir(path, str(app_paths.compat_dir()))


def is_path_extension(path: str) -> bool:
    for directory in app_paths.extension_repos().values():
        if qpath.is_subdir(path, str(directory)):
            return True
    return qpath.is_subdir(path, str(app_paths.extensions_dir() / ".user"))


def app_template_paths(*, path: str | None = None) -> Iterator[str]:
    base = app_paths.scripts_dir() / "startup" / "bl_app_templates_user"
    if path:
        base = base / path
    if base.is_dir():
        yield str(base)


def make_rna_paths(struct_name: str, prop_name: str, enum_name: str) -> tuple[str, str, str]:
    if not struct_name:
        return "", "", ""
    if not prop_name:
        return struct_name, struct_name, ""
    rna = f"{struct_name}.{prop_name}"
    if not enum_name:
        return rna, rna, ""
    enum = f"{rna}:'{enum_name}'"
    return enum, rna, enum
