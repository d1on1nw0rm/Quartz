from __future__ import annotations

from .menus import commands, docks, key_actions, pages
from .convert import convert_to_nodes, pbr_to_graph
from .evaluate import display_color, evaluate_material, make_context
from .model import (CHANNELS, PRESETS, active_material, active_material_id, create_material, delete_material,
                    duplicate_material, find_material, load_library, materials, new_material, rename_material,
                    save_library, set_active_material, update_material)
from .preview import render_preview, render_preview_array, thumbnail
from .tags import (apply_material, assign_to_selected, effective_material_id, material_tags, new_material_tag,
                   object_uvs, polygon_material_ids, project_uv, remove_material_tags, tag_uv)

__all__ = [
    "commands",
    "docks",
    "pages",
    "key_actions",
    "CHANNELS",
    "PRESETS",
    "materials",
    "find_material",
    "new_material",
    "create_material",
    "update_material",
    "delete_material",
    "duplicate_material",
    "rename_material",
    "active_material",
    "active_material_id",
    "set_active_material",
    "save_library",
    "load_library",
    "evaluate_material",
    "make_context",
    "display_color",
    "render_preview",
    "render_preview_array",
    "thumbnail",
    "pbr_to_graph",
    "convert_to_nodes",
    "new_material_tag",
    "apply_material",
    "assign_to_selected",
    "remove_material_tags",
    "material_tags",
    "effective_material_id",
    "polygon_material_ids",
    "tag_uv",
    "project_uv",
    "object_uvs",
]
