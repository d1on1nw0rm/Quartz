from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from . import paths
from .runner import DEFAULT_TIMEOUT, TIMEOUT_KEY, ExecResult, default_timeout, execute, make_namespace

__all__ = ["ScriptLibrary", "sanitize_name", "get_library", "SCRIPT_TEMPLATE", "DEFAULT_TIMEOUT"]

SCRIPT_TEMPLATE = (
    "import quartz\n"
    "\n"
    "\n"
    "def main():\n"
    "    obj = quartz.active_object()\n"
    "    print(\"Active object:\", obj.name if obj else None)\n"
    "\n"
    "\n"
    "main()\n"
)

_BAD = re.compile(r"[^A-Za-z0-9 _\-\.\(\)]")


def sanitize_name(name: str) -> str:
    base = os.path.basename(str(name).replace("\\", "/")).strip()
    if base.lower().endswith(".py"):
        base = base[:-3]
    base = _BAD.sub("_", base).strip(" .")
    if not base:
        raise ValueError("script name is empty")
    return base + ".py"


class ScriptLibrary:

    SHORTCUTS_KEY = "script_shortcuts"

    def __init__(self, folder: str | Path | None = None) -> None:
        self._folder = Path(folder) if folder is not None else None

    @property
    def folder(self) -> Path:
        if self._folder is not None:
            self._folder.mkdir(parents=True, exist_ok=True)
            return self._folder
        return paths.scripts_dir()

    def path(self, name: str) -> Path:
        return self.folder / sanitize_name(name)

    def list(self) -> list[str]:
        return sorted((p.name for p in self.folder.glob("*.py") if p.is_file()), key=str.lower)

    def exists(self, name: str) -> bool:
        return self.path(name).is_file()

    def load(self, name: str) -> str:
        with open(self.path(name), "r", encoding="utf-8") as fh:
            return fh.read()

    def save(self, name: str, text: str) -> Path:
        target = self.path(name)
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return target

    def unique_name(self, base: str = "Untitled") -> str:
        name = sanitize_name(base)
        if not self.exists(name):
            return name
        stem = name[:-3]
        n = 1
        while self.exists(f"{stem} {n}.py"):
            n += 1
        return f"{stem} {n}.py"

    def create(self, base: str = "Untitled", text: str = SCRIPT_TEMPLATE) -> str:
        name = self.unique_name(base)
        self.save(name, text)
        return name

    def delete(self, name: str) -> bool:
        target = self.path(name)
        if not target.is_file():
            return False
        target.unlink()
        self.set_shortcut(name, None)
        return True

    def rename(self, old: str, new: str) -> str:
        src = self.path(old)
        if not src.is_file():
            raise FileNotFoundError(old)
        dst_name = sanitize_name(new)
        dst = self.folder / dst_name
        if dst.exists() and dst != src:
            raise FileExistsError(dst_name)
        key = self.shortcut(old)
        src.rename(dst)
        self.set_shortcut(old, None)
        if key:
            self.set_shortcut(dst_name, key)
        return dst_name

    def import_file(self, source: str | Path) -> str:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(str(source))
        if source.parent.resolve() == self.folder.resolve():
            return source.name
        name = self.unique_name(source.stem)
        shutil.copyfile(source, self.folder / name)
        return name

    def shortcuts(self) -> dict[str, str]:
        data = paths.read_settings().get(self.SHORTCUTS_KEY, {})
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(v, str) and v and self.exists(k)}

    def shortcut(self, name: str) -> str:
        return self.shortcuts().get(sanitize_name(name), "")

    def set_shortcut(self, name: str, keys: str | None) -> None:
        data = paths.read_settings()
        table = data.get(self.SHORTCUTS_KEY, {})
        if not isinstance(table, dict):
            table = {}
        name = sanitize_name(name)
        keys = (keys or "").strip()
        if keys:
            for other, value in list(table.items()):
                if value == keys and other != name:
                    table.pop(other)
            table[name] = keys
        else:
            table.pop(name, None)
        data[self.SHORTCUTS_KEY] = table
        paths.write_settings(data)

    def timeout(self) -> float | None:
        return default_timeout()

    def set_timeout(self, seconds: float | None) -> float:
        value = 0.0 if seconds is None else max(0.0, float(seconds))
        paths.update_settings(TIMEOUT_KEY, value)
        return value

    def run(self, name: str, scene=None, text: str | None = None, undo_group: bool = True,
            timeout: float | None | str = "default") -> ExecResult:
        from . import api
        source = self.load(name) if text is None else text
        scene = api.document() if scene is None else scene
        ns = make_namespace(scene, {"__file__": str(self.path(name))})
        limit = default_timeout() if timeout == "default" else timeout
        return execute(source, ns, filename=sanitize_name(name), scene=scene,
                       undo_group=undo_group, paths=[self.folder], timeout=limit)


def get_library() -> ScriptLibrary:
    return ScriptLibrary()
