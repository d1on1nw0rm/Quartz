from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from .model import Document

__all__ = [
    "FileFormat",
    "FileFormatError",
    "FORMATS",
    "register",
    "get",
    "by_path",
    "importers",
    "exporters",
    "file_filter",
    "import_filters",
    "export_filters",
    "name_error",
]


class FileFormatError(Exception):
    pass


def name_error(label: str, exc: FileFormatError) -> FileFormatError:
    text = str(exc)
    return exc if label in text else FileFormatError(f"{label}: {text}")


@dataclass(frozen=True)
class FileFormat:
    id: str
    label: str
    extensions: tuple[str, ...]
    load: Callable[[str], Document] | None = None
    save: Callable[[str, Document, dict], None] | None = None
    description: str = ""


FORMATS: dict[str, FileFormat] = {}


def _normal(ext: str) -> str:
    ext = str(ext).strip().lower()
    return ext if ext.startswith(".") else "." + ext


def register(fmt: FileFormat) -> FileFormat:
    if not fmt.id:
        raise ValueError("file format needs an id")
    if fmt.id in FORMATS:
        raise ValueError(f"file format {fmt.id!r} registered twice")
    exts = tuple(_normal(e) for e in fmt.extensions)
    if not exts or any(len(e) < 2 for e in exts):
        raise ValueError(f"file format {fmt.id!r} needs at least one extension")
    for other in FORMATS.values():
        for e in exts:
            if e in other.extensions:
                raise ValueError(f"extension {e!r} of {fmt.id!r} already belongs to {other.id!r}")
    if exts != tuple(fmt.extensions):
        fmt = FileFormat(fmt.id, fmt.label, exts, fmt.load, fmt.save, fmt.description)
    FORMATS[fmt.id] = fmt
    return fmt


def get(format_id: str) -> FileFormat:
    return FORMATS[format_id]


def by_path(path) -> FileFormat | None:
    ext = os.path.splitext(os.fspath(path))[1].lower()
    if not ext:
        return None
    for fmt in FORMATS.values():
        if ext in fmt.extensions:
            return fmt
    return None


def importers() -> list[FileFormat]:
    return [f for f in FORMATS.values() if f.load is not None]


def exporters() -> list[FileFormat]:
    return [f for f in FORMATS.values() if f.save is not None]


def _patterns(fmt: FileFormat) -> str:
    return " ".join("*" + e for e in fmt.extensions)


def file_filter(fmt: FileFormat) -> str:
    return f"{fmt.label} ({_patterns(fmt)})"


def _filters(formats: list[FileFormat]) -> list[str]:
    if not formats:
        return []
    everything = " ".join(_patterns(f) for f in formats)
    return [f"All supported ({everything})"] + [file_filter(f) for f in formats]


def import_filters() -> list[str]:
    return _filters(importers())


def export_filters() -> list[str]:
    return _filters(exporters())
