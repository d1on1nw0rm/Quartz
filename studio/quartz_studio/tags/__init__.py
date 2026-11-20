from __future__ import annotations

from . import builtin, core
from .core import (CURRENT_KEY, SELECTION_TYPES, TAGS_KEY, add_tag, clear_tags, copy_tags,
                   current_tag, deserialize_tags, duplicate_tag, find_object, find_tag_by_name,
                   find_tags, first_tag, get_tags, move_tag, new_selection_tag, remove_tag,
                   rename_tag, restore_selection, run_action, selection_items, serialize_tags,
                   set_current_tag, set_tag_enabled, set_tags, store_selection, tag_at,
                   tag_summary, tags_of, update_tag)
from .registry import (CATEGORIES, TAG_SPECS, TagAction, TagParam, TagSpec, get_tag_spec,
                       make_tag, register_tag, specs_by_category, tag_ids, tag_specs)
from .runtime import (BASE_KEY, base_transform, evaluate_tags, find_camera_position,
                      reset_runtime, vibrate_offsets)
from .shading import (PROJECTIONS, SHADING_MODES, compositing_flags, display_state,
                      fit_projection, flat_normals, generate_uvw, material_assignments,
                      material_polygons, object_normals, phong_normals, projection_uvs,
                      uvw_coordinates)

__all__ = [
    "CATEGORIES", "TAG_SPECS", "TAGS_KEY", "CURRENT_KEY", "BASE_KEY", "SELECTION_TYPES",
    "PROJECTIONS", "SHADING_MODES",
    "TagParam", "TagAction", "TagSpec", "register_tag", "get_tag_spec", "tag_specs", "tag_ids",
    "specs_by_category", "make_tag",
    "tags_of", "get_tags", "set_tags", "tag_at", "add_tag", "remove_tag", "move_tag",
    "duplicate_tag", "update_tag", "set_tag_enabled", "rename_tag", "find_tags",
    "find_tag_by_name", "first_tag", "copy_tags", "clear_tags", "find_object",
    "set_current_tag", "current_tag", "run_action", "tag_summary", "selection_items",
    "store_selection", "restore_selection", "new_selection_tag", "serialize_tags",
    "deserialize_tags",
    "phong_normals", "flat_normals", "object_normals", "display_state", "compositing_flags",
    "projection_uvs", "uvw_coordinates", "material_polygons", "material_assignments",
    "fit_projection", "generate_uvw",
    "evaluate_tags", "reset_runtime", "base_transform", "find_camera_position", "vibrate_offsets",
    "add_tag_to_active", "evaluate_scene", "commands", "docks", "pages", "builtin", "core",
]


def _scene(scene=None):
    if scene is None:
        from ..scene import get_scene
        scene = get_scene()
    return scene


def add_tag_to_active(tag_id: str, scene=None) -> int | None:
    scene = _scene(scene)
    obj = scene.active
    if obj is None or obj not in scene.objects:
        return None
    index = add_tag(obj, tag_id, scene=scene)
    set_current_tag(scene, obj, index)
    scene.changed.emit()
    return index


def evaluate_scene(scene=None, frame: float | None = None, camera_position=None) -> list:
    scene = _scene(scene)
    if frame is None:
        from .widgets import current_frame
        frame = current_frame(scene)
    changed = evaluate_tags(scene, frame, camera_position)
    if changed:
        scene.changed.emit()
    return changed


def _reset_scene_runtime(scene=None) -> int:
    scene = _scene(scene)
    n = reset_runtime(scene)
    if n:
        scene.changed.emit()
    return n


def _set_selection(scene=None) -> int | None:
    scene = _scene(scene)
    return new_selection_tag(scene)


def _copy_to_children(scene=None) -> int:
    scene = _scene(scene)
    obj = scene.active
    if obj is None:
        return 0
    total = 0
    core.watch_scene(scene)
    with core.undo_group(scene):
        for child in scene.descendants(obj):
            total += copy_tags(obj, child, scene=scene)
    if total:
        scene.changed.emit()
    return total


def _remove_all(scene=None) -> None:
    scene = _scene(scene)
    obj = scene.active
    if obj is not None:
        core.watch_scene(scene)
        clear_tags(obj)
        set_current_tag(scene, obj, None)
        scene.changed.emit()


def _adder(tag_id: str):
    def run(*_args) -> int | None:
        return add_tag_to_active(tag_id)
    run.__name__ = f"add_{tag_id}_tag"
    return run


def commands() -> list:
    out = []
    for category, specs in specs_by_category():
        for spec in specs:
            out.append((("Tags", category, spec.label), _adder(spec.id)))
    out.append((("Tags", "Set Selection"), lambda *_a: _set_selection()))
    out.append((("Tags", "Copy Tags to Children"), lambda *_a: _copy_to_children()))
    out.append((("Tags", "Remove All Tags"), lambda *_a: _remove_all()))
    out.append((("Tags", "Evaluate Runtime Tags"), lambda *_a: evaluate_scene()))
    out.append((("Tags", "Reset Runtime Transforms"), lambda *_a: _reset_scene_runtime()))
    return out


def _tags_panel(scene=None, parent=None):
    from .widgets import TagsPanel
    return TagsPanel(scene, parent)


def _tag_attributes(scene=None, parent=None):
    from .widgets import TagAttributes
    return TagAttributes(scene, parent)


def docks() -> list:
    return [("Tags", _tags_panel, "right"), ("Tag Attributes", _tag_attributes, "right")]


def pages() -> list:
    return [("Tagging", ["Tags", "Tag Attributes"])]
