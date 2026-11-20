from __future__ import annotations

import importlib.util
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import api, paths
from .runner import purge_modules

__all__ = [
    "PLUGIN_TYPES",
    "PluginRecord",
    "PluginAPI",
    "PluginLoader",
    "get_loader",
    "reset_loader",
]

PLUGIN_TYPES = ("command", "object", "tag", "tool")
STATE_FILE = "plugins.json"


@dataclass
class PluginRecord:
    stem: str
    path: Path
    name: str = ""
    type: str = ""
    version: str = ""
    author: str = ""
    description: str = ""
    enabled: bool = True
    loaded: bool = False
    error: str = ""
    module: Any = None
    commands: list = field(default_factory=list)
    objects: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    tags: list = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.name or self.stem

    def contributions(self) -> int:
        return len(self.commands) + len(self.objects) + len(self.tools) + len(self.tags)


class PluginAPI:

    def __init__(self, loader: "PluginLoader", record: PluginRecord) -> None:
        self._loader = loader
        self._record = record

    def __getattr__(self, name: str):
        return getattr(api, name)

    @property
    def plugin(self) -> PluginRecord:
        return self._record

    def register_command(self, label: str, fn: Callable, shortcut: str | None = None,
                         menu: tuple | list | None = None) -> tuple:
        if not callable(fn):
            raise TypeError("command needs a callable")
        label = str(label).strip()
        if not label:
            raise ValueError("command label is empty")
        path = ("Extensions",) + tuple(str(m) for m in (menu or ())) + (label,)
        self._record.commands.append((path, fn, shortcut or ""))
        return path

    def register_object(self, spec=None, **kw):
        from ..objects import registry as reg
        if spec is None:
            category = kw.pop("category", "mesh")
            spec = reg.ObjectSpec(kw.pop("id"), kw.pop("label"), category, kw.pop("build"), **kw)
        reg.register(spec)
        self._record.objects.append(spec.id)
        return spec

    def register_tool(self, spec=None, **kw):
        from ..modeling import registry as mreg
        mreg.tool_ids()
        if spec is None:
            spec = mreg.ToolSpec(kw.pop("id"), kw.pop("name"), kw.pop("apply"), **kw)
        mreg.register(spec)
        self._record.tools.append(spec.id)
        return spec

    def register_tag(self, tag_id: str, label: str, defaults: dict | None = None,
                     run: Callable | None = None, description: str = ""):
        from . import pytags
        spec = pytags.register_tag_type(tag_id, label, defaults, run, owner=self._record.stem,
                                        description=description)
        self._record.tags.append(spec.id)
        return spec


_SAFE = re.compile(r"[^A-Za-z0-9_]")
MODULE_PREFIX = "quartz_plugin_"


class PluginLoader:

    def __init__(self, folder: str | Path | None = None) -> None:
        self._folder = Path(folder) if folder is not None else None
        self.records: dict[str, PluginRecord] = {}
        self._listeners: list[Callable[[], None]] = []
        self.loaded_once = False

    @property
    def folder(self) -> Path:
        if self._folder is not None:
            self._folder.mkdir(parents=True, exist_ok=True)
            return self._folder
        return paths.plugins_dir()

    @property
    def state_path(self) -> Path:
        return self.folder.parent / STATE_FILE

    def add_listener(self, fn: Callable[[], None]) -> None:
        if fn not in self._listeners:
            self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[], None]) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    def _emit(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                pass

    def disabled(self) -> set[str]:
        data = paths.read_json(self.state_path, {})
        items = data.get("disabled", []) if isinstance(data, dict) else []
        return {str(s) for s in items}

    def _save_state(self) -> None:
        disabled = sorted(s for s, r in self.records.items() if not r.enabled)
        known = self.disabled() - set(self.records)
        paths.write_json(self.state_path, {"disabled": sorted(set(disabled) | known)})

    def discover(self) -> list[Path]:
        return sorted((p for p in self.folder.glob("*.py")
                       if p.is_file() and not p.name.startswith("_")), key=lambda p: p.name.lower())

    def _unregister(self, record: PluginRecord) -> None:
        mod = record.module
        if mod is not None and record.loaded:
            fn = getattr(mod, "unregister", None)
            if callable(fn):
                try:
                    fn(PluginAPI(self, record))
                except Exception:
                    record.error = "unregister failed:\n" + traceback.format_exc()
        from ..objects import registry as reg
        for sid in record.objects:
            reg.SPECS.pop(sid, None)
        if record.tools:
            from ..modeling import registry as mreg
            for tid in record.tools:
                mreg.TOOLS.pop(tid, None)
        if record.tags:
            from . import pytags
            for tag_id in record.tags:
                pytags.unregister_tag_type(tag_id)
        record.commands.clear()
        record.objects.clear()
        record.tools.clear()
        record.tags.clear()
        record.loaded = False
        record.module = None
        sys.modules.pop(self._module_name(record.stem), None)

    @staticmethod
    def _module_name(stem: str) -> str:
        return MODULE_PREFIX + _SAFE.sub("_", stem)

    def _ensure_search_path(self) -> str:
        folder = str(self.folder.resolve())
        if folder not in sys.path:
            sys.path.append(folder)
            importlib.invalidate_caches()
        return folder

    def _purge_helpers(self) -> list[str]:
        return purge_modules([self.folder.resolve()], keep_prefix=MODULE_PREFIX)

    def _import(self, record: PluginRecord):
        self._ensure_search_path()
        name = self._module_name(record.stem)
        spec = importlib.util.spec_from_file_location(name, record.path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {record.path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        no_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        finally:
            sys.dont_write_bytecode = no_bytecode
        return module

    def _read_meta(self, record: PluginRecord, module) -> None:
        meta = getattr(module, "PLUGIN", None)
        if not isinstance(meta, dict):
            raise ValueError("the plugin has no PLUGIN dictionary")
        name = str(meta.get("name", "")).strip()
        kind = str(meta.get("type", "")).strip()
        if not name:
            raise ValueError("PLUGIN['name'] is missing")
        if kind not in PLUGIN_TYPES:
            raise ValueError(f"PLUGIN['type'] must be one of {', '.join(PLUGIN_TYPES)}")
        record.name = name
        record.type = kind
        record.version = str(meta.get("version", ""))
        record.author = str(meta.get("author", ""))
        record.description = str(meta.get("description", ""))

    def _activate(self, record: PluginRecord) -> bool:
        record.error = ""
        try:
            module = self._import(record)
            self._read_meta(record, module)
            record.module = module
            register = getattr(module, "register", None)
            if not callable(register):
                raise ValueError("the plugin has no register(api) function")
            register(PluginAPI(self, record))
            if record.type == "command" and not record.commands:
                run = getattr(module, "run", None)
                if callable(run):
                    proxy = PluginAPI(self, record)
                    record.commands.append((("Extensions", record.name), lambda r=run, p=proxy: r(p), ""))
            record.loaded = True
            return True
        except BaseException as exc:
            record.module = None
            record.loaded = True
            self._unregister(record)
            record.error = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            return False

    def _peek_meta(self, record: PluginRecord) -> None:
        try:
            text = record.path.read_text(encoding="utf-8")
        except OSError:
            return
        m = re.search(r"['\"]name['\"]\s*:\s*['\"]([^'\"]+)['\"]", text)
        if m and not record.name:
            record.name = m.group(1)
        m = re.search(r"['\"]type['\"]\s*:\s*['\"]([^'\"]+)['\"]", text)
        if m and not record.type:
            record.type = m.group(1)

    def load_all(self) -> list[PluginRecord]:
        for record in list(self.records.values()):
            if record.loaded:
                self._unregister(record)
        self.records = {}
        self._purge_helpers()
        disabled = self.disabled()
        for path in self.discover():
            record = PluginRecord(path.stem, path, enabled=path.stem not in disabled)
            self.records[record.stem] = record
            if record.enabled:
                self._activate(record)
            else:
                self._peek_meta(record)
        self.loaded_once = True
        self._emit()
        return list(self.records.values())

    reload = load_all

    def ensure_loaded(self) -> None:
        if not self.loaded_once:
            self.load_all()

    def get(self, stem: str) -> PluginRecord | None:
        return self.records.get(stem)

    def set_enabled(self, stem: str, enabled: bool) -> bool:
        record = self.records.get(stem)
        if record is None:
            raise KeyError(stem)
        enabled = bool(enabled)
        if record.enabled == enabled and record.loaded == enabled:
            return record.loaded or not enabled
        record.enabled = enabled
        if enabled:
            ok = self._activate(record)
        else:
            self._unregister(record)
            ok = True
        self._save_state()
        self._emit()
        return ok

    def reload_one(self, stem: str) -> bool:
        record = self.records.get(stem)
        if record is None:
            raise KeyError(stem)
        self._unregister(record)
        self._purge_helpers()
        ok = self._activate(record) if record.enabled else True
        self._emit()
        return ok

    @staticmethod
    def _safe(record: PluginRecord, fn: Callable) -> Callable:
        def call(*args, **kw):
            try:
                with api.undo_group(api.document()):
                    return fn(*args, **kw)
            except Exception as exc:
                text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                record.error = text
                api.message(f"{record.title}: {type(exc).__name__}: {exc}")
                return None
        call.__name__ = getattr(fn, "__name__", "command")
        call.__wrapped__ = fn
        return call

    def commands(self) -> list[tuple[tuple, Callable]]:
        out = []
        for record in self.records.values():
            if record.loaded and record.enabled:
                for path, fn, _keys in record.commands:
                    out.append((path, self._safe(record, fn)))
        return out

    def shortcuts(self) -> list[tuple[str, Callable, str]]:
        out = []
        for record in self.records.values():
            if record.loaded and record.enabled:
                for path, fn, keys in record.commands:
                    if keys:
                        out.append((keys, self._safe(record, fn), path[-1]))
        return out

    def run_command(self, label: str) -> Any:
        for path, fn in self.commands():
            if path[-1] == label or "/".join(path) == label:
                return fn()
        raise KeyError(label)

    def errors(self) -> dict[str, str]:
        return {s: r.error for s, r in self.records.items() if r.error}


_LOADERS: dict[str, PluginLoader] = {}


def get_loader() -> PluginLoader:
    key = str(paths.plugins_dir().resolve())
    loader = _LOADERS.get(key)
    if loader is None:
        loader = PluginLoader()
        _LOADERS[key] = loader
    return loader


def reset_loader() -> None:
    for loader in _LOADERS.values():
        for record in list(loader.records.values()):
            if record.loaded:
                loader._unregister(record)
    _LOADERS.clear()
