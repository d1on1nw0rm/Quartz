from __future__ import annotations

import os
from pathlib import Path

from ..scene import Scene, SceneObject
from . import registry
from .bridge import (add_document_to_scene, document_from_scene, full_document_from_scene,
                     replace_scene)
from .model import Document
from .registry import FileFormat, FileFormatError

__all__ = ["import_file", "export_file", "open_scene", "save_scene"]


def _format_for(path: Path, direction: str) -> FileFormat:
    fmt = registry.by_path(path)
    if fmt is None:
        ext = path.suffix or "(none)"
        raise FileFormatError(f"{path.name}: unknown file type {ext}")
    if direction == "load" and fmt.load is None:
        raise FileFormatError(f"{path.name}: {fmt.label} files cannot be imported")
    if direction == "save" and fmt.save is None:
        raise FileFormatError(f"{path.name}: {fmt.label} files cannot be exported")
    return fmt


def _wrap(path: Path, fn, *args):
    try:
        return fn(*args)
    except FileFormatError as exc:
        named = registry.name_error(path.name, exc)
        if named is exc:
            raise
        raise named from None
    except Exception as exc:
        raise FileFormatError(f"{path.name}: {type(exc).__name__}: {exc}") from exc


def _read(path) -> tuple[Path, Document]:
    p = Path(os.fspath(path))
    fmt = _format_for(p, "load")
    if not p.is_file():
        raise FileFormatError(f"{p.name}: file not found")
    doc = _wrap(p, fmt.load, str(p))
    if not isinstance(doc, Document):
        raise FileFormatError(f"{p.name}: {fmt.label} reader returned no document")
    return p, doc


def _write(path, document: Document, options: dict | None) -> None:
    p = Path(os.fspath(path))
    fmt = _format_for(p, "save")
    _wrap(p, fmt.save, str(p), document, dict(options or {}))


def import_file(scene: Scene, path, meta: dict | None = None) -> list[SceneObject]:
    p, doc = _read(path)
    if meta is not None:
        meta.update(doc.meta)
    return _wrap(p, add_document_to_scene, scene, doc)


def export_file(scene: Scene, path, selected_only: bool = False, options: dict | None = None) -> None:
    p = Path(os.fspath(path))
    _format_for(p, "save")
    doc = _wrap(p, document_from_scene, scene, selected_only)
    if not doc.nodes:
        raise FileFormatError(f"{p.name}: nothing to export")
    _write(p, doc, options)


def open_scene(scene: Scene, path, meta: dict | None = None) -> None:
    p, doc = _read(path)
    _wrap(p, replace_scene, scene, doc)
    if meta is not None:
        meta.update(doc.meta)


def save_scene(scene: Scene, path, view: dict | None = None) -> None:
    p = Path(os.fspath(path))
    _format_for(p, "save")
    doc = _wrap(p, full_document_from_scene, scene, view)
    _write(p, doc, {})
