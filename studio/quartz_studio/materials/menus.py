from __future__ import annotations

from ..scene import get_scene
from . import model
from .convert import convert_to_nodes
from .tags import apply_material, assign_to_selected, remove_from_selected

__all__ = [
    "DOCK_MANAGER",
    "DOCK_EDITOR",
    "DOCK_NODES",
    "commands",
    "docks",
    "pages",
    "key_actions",
    "new_pbr",
    "new_node",
    "apply_active",
    "remove_active",
    "add_tag_to_selected",
]

DOCK_MANAGER = "Material Manager"
DOCK_EDITOR = "Material Editor"
DOCK_NODES = "Node Editor"


def _scene(scene=None):
    return scene if scene is not None else get_scene()


def new_pbr(scene=None) -> dict:
    return model.create_material(_scene(scene), "pbr")


def new_node(scene=None) -> dict:
    return model.create_material(_scene(scene), "node")


def new_preset(preset: str, scene=None) -> dict:
    return model.create_material(_scene(scene), preset=preset)


def apply_active(scene=None) -> int:
    return assign_to_selected(_scene(scene))


def remove_active(scene=None) -> int:
    return remove_from_selected(_scene(scene))


def duplicate_active(scene=None) -> dict | None:
    s = _scene(scene)
    mid = model.active_material_id(s)
    return model.duplicate_material(s, mid) if mid else None


def delete_active(scene=None) -> bool:
    s = _scene(scene)
    mid = model.active_material_id(s)
    return model.delete_material(s, mid) if mid else False


def convert_active(scene=None) -> dict | None:
    s = _scene(scene)
    mid = model.active_material_id(s)
    return convert_to_nodes(s, mid) if mid else None


def delete_unused(scene=None) -> int:
    return model.delete_unused(_scene(scene))


def add_tag_to_selected(scene=None) -> int:
    s = _scene(scene)
    targets = list(getattr(s, "selected_objects", lambda: [])())
    if not targets:
        return 0
    with model.undo_group(s):
        mid = model.active_material_id(s)
        if mid is None:
            mid = model.create_material(s, "pbr")["id"]
        for obj in targets:
            apply_material(obj, mid)
    return len(targets)


def load_library_dialog(scene=None) -> list:
    from PySide6.QtWidgets import QFileDialog
    from .manager import LIBRARY_FILTER
    path, _ = QFileDialog.getOpenFileName(None, "Load Material Library", "", LIBRARY_FILTER)
    return model.load_library(_scene(scene), path) if path else []


def save_library_dialog(scene=None) -> int:
    from PySide6.QtWidgets import QFileDialog
    from .manager import LIBRARY_FILTER
    path, _ = QFileDialog.getSaveFileName(None, "Save Material Library", "materials.qmat.json", LIBRARY_FILTER)
    return model.save_library(_scene(scene), path) if path else 0


def commands() -> list:
    out = [
        (("Materials", "New PBR Material"), new_pbr),
        (("Materials", "New Node Material"), new_node),
    ]
    for key, spec in model.PRESETS.items():
        out.append((("Materials", "Presets", spec["name"]), lambda k=key: new_preset(k)))
    out.extend([
        (("Materials", "Apply to Selected"), add_tag_to_selected),
        (("Materials", "Remove from Selected"), remove_active),
        (("Materials", "Duplicate Active"), duplicate_active),
        (("Materials", "Delete Active"), delete_active),
        (("Materials", "Convert Active to Nodes"), convert_active),
        (("Materials", "Delete Unused"), delete_unused),
        (("Materials", "Load Library..."), load_library_dialog),
        (("Materials", "Save Library..."), save_library_dialog),
    ])
    return out


def docks() -> list:
    from .editor import MaterialEditor
    from .manager import MaterialManager
    from .node_editor import NodeEditor
    return [
        (DOCK_MANAGER, MaterialManager, "bottom"),
        (DOCK_EDITOR, MaterialEditor, "right"),
        (DOCK_NODES, NodeEditor, "bottom"),
    ]


def pages() -> list:
    return [("Materials", [DOCK_MANAGER, DOCK_EDITOR, DOCK_NODES])]


def key_actions() -> list:
    return [("Apply Material to Selected", "Ctrl+Shift+M", apply_active)]
