# Extension: tags

Package `quartz_studio/tags` (about 4.2k lines). Loaded by `ext/install.py` as `quartz_studio.tags`.

## Purpose

Per-object tag stacks (Cinema 4D style): a registry of tag types with typed parameters and actions, tag editing with undo, runtime evaluation of transform tags per frame, and shading helpers (phong normals, UVW projections, material assignment, display and compositing flags).

## Data in extras

Object extras:

| Key | Shape |
|-----|-------|
| `tags` (`core.TAGS_KEY`) | list of tag dicts `{"type": id, "name": str, "enabled": bool, ...params}` |
| `tags_base` (`runtime.BASE_KEY`) | stored base transform used to restore after runtime evaluation |
| `selections` | named point, edge and polygon selections written by selection tags |
| `ik` (`builtin.IK_KEY`) | IK record mirrored from IK tags for the rig package |

Scene extras: `tags_current` (`core.CURRENT_KEY`, current object and tag index), `active_camera` and `camera_position` (read by runtime tags).

Writes are coalesced per 1.0 s (`COALESCE_SECONDS`).

## Tag types (`builtin.SPEC_IDS`)

| Category | Ids |
|----------|-----|
| Rendering Tags | material, compositing, display, look_at_camera |
| Modeling Tags | phong, point_selection, edge_selection, polygon_selection, uvw |
| Animation Tags | vibrate, target, protection |
| Programming Tags | python |
| Simulation Tags | rigid_body, collider_body, soft_body |
| Character Tags | constraint, ik, weight, skin |

Runtime (evaluated each frame): look_at_camera, vibrate, target, protection, constraint. Actions exist on material (fit, generate_uvw, reset_projection), phong (break edges), selection tags (set, restore, select, deselect, clear), uvw (clear), protection (freeze), constraint (set_offset, clear_offset), weight (assign, select, remove_joint, normalize).

## Public functions

- `registry`: `TagParam`, `TagAction`, `TagSpec`, `register_tag`, `get_tag_spec`, `tag_specs`, `tag_ids`, `specs_by_category`, `make_tag`, `clamp_tag`, `CATEGORIES`.
- `core`: `tags_of`, `get_tags`, `set_tags`, `tag_at`, `add_tag`, `remove_tag`, `move_tag`, `duplicate_tag`, `update_tag`, `set_tag_enabled`, `rename_tag`, `find_tags`, `find_tag_by_name`, `first_tag`, `copy_tags`, `clear_tags`, `find_object`, `set_current_tag`, `current_tag`, `run_action`, `tag_summary`, `selection_items`, `store_selection`, `restore_selection`, `new_selection_tag`, `serialize_tags`, `deserialize_tags`, `rename_references`.
- `runtime`: `evaluate_tags(scene, frame, camera_position, fps)`, `reset_runtime`, `base_transform`, `find_camera_position`, `vibrate_offsets`, `dependency_order`.
- `shading`: `phong_normals`, `flat_normals`, `object_normals`, `display_state`, `compositing_flags`, `projection_uvs`, `uvw_coordinates`, `material_polygons`, `material_assignments`, `fit_projection`, `generate_uvw`. `PROJECTIONS`: uvw, spherical, cylindrical, flat, cubic, frontal, shrinkwrap.
- Package level: `add_tag_to_active(tag_id, scene)`, `evaluate_scene(scene, frame, camera_position)`.

## Widgets

`TagsPanel` (rows with `TagChip`, `EnableToggle`, rename, drag reorder, context menu), `TagAttributes` with `ParamEditor` (typed fields, pending-edit flush, action buttons), `build_add_menu`.

## Menus, docks, pages, shortcuts

- Menu `Tags` (installed under `Materials > Tags`): one submenu per category with an Add entry per tag type, plus Set Selection, Copy Tags to Children, Remove All Tags, Evaluate Runtime Tags, Reset Runtime Transforms.
- Docks: Tags (right), Tag Attributes (right).
- Page: `Tagging` (not in `PAGE_LAYOUTS` or `DOCK_LAYOUTS`, so it gets no Layout menu entry).
- No `key_actions`.

## Known gaps

- Simulation tags (rigid_body, collider_body, soft_body) store parameters only; nothing simulates them.
- `Tagging` page is declared but never shown by the installer.
- Projection list differs from `materials.tags.PROJECTIONS` (see ext-materials.md).
