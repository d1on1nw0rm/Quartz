from __future__ import annotations

import importlib
import pkgutil

from .model import Document, Node, baked_mesh, compose, decompose, face_normals, triangulate, weld
from .registry import (FORMATS, FileFormat, FileFormatError, by_path, exporters, export_filters,
                       file_filter, get, import_filters, importers, register)
from .bridge import (add_document_to_scene, document_from_scene, full_document_from_scene,
                     replace_scene)
from .api import export_file, import_file, open_scene, save_scene

__all__ = [
    "Document",
    "Node",
    "baked_mesh",
    "compose",
    "decompose",
    "face_normals",
    "triangulate",
    "weld",
    "FORMATS",
    "FileFormat",
    "FileFormatError",
    "by_path",
    "exporters",
    "export_filters",
    "file_filter",
    "get",
    "import_filters",
    "importers",
    "register",
    "add_document_to_scene",
    "document_from_scene",
    "full_document_from_scene",
    "replace_scene",
    "export_file",
    "import_file",
    "open_scene",
    "save_scene",
]

for _info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
    if _info.name.startswith("fmt_"):
        importlib.import_module(f"{__name__}.{_info.name}")
