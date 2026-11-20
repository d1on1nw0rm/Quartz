# Extension: materials

Package `quartz_studio/materials` (about 6.4k lines). Loaded by `ext/install.py` through `quartz_studio.materials.menus`.

## Purpose

Scene material library with PBR channel materials and node-graph materials, procedural and image textures, a CPU evaluator, preview renders and thumbnails, assignment through material tags, and JSON library import and export.

## Data in extras

Scene extras:

| Key | Shape |
|-----|-------|
| `materials` (`model.LIBRARY_KEY`) | list of material dicts |
| `active_material` (`model.ACTIVE_KEY`) | material id string |

Material dict: `{"id": str, "name": str, "type": "pbr" or "node", "channels": {key: channel}, "preview": "sphere" | other shape, "graph": {...} (node only)}`.
Channels (`model.CHANNELS`): `base_color`, `metallic`, `roughness`, `specular`, `ior`, `normal`, `bump`, `emission`, `alpha`, `transmission`, `clearcoat`, `sheen`, `displacement`. Optional channels start disabled. A channel can hold a texture dict made by `textures.new_texture(kind, ...)`.

Object extras:

| Key | Shape |
|-----|-------|
| `tags` | list of tag dicts; material tags are `{"type": "material", "material": id, "projection": "uvw"/"spherical"/"cylindrical"/"cubic"/"flat", "offset": [u, v], "tiling": [u, v], "selection": name}` |
| `uvw` | read only, per-object UV data used by `object_uvs` |
| `selections` | read only, named polygon selections used by `polygon_selection` |

Writes are coalesced into one undo step per 1.5 s (`COALESCE_SECONDS`).

## Public functions

- `model`: `materials`, `find_material`, `new_material`, `preset_material`, `create_material`, `add_material`, `update_material`, `delete_material`, `duplicate_material`, `rename_material`, `active_material`, `active_material_id`, `set_active_material`, `set_channel`, `set_channel_texture`, `set_texture_value`, `save_library`, `load_library`, `sanitize_material`, `unused_materials`, `delete_unused`, `undo_group`, `end_coalescing`. `PRESETS`: Plastic, Metal, Gold, Glass, Rubber, Emissive, Car Paint, Velvet, Checker, Marble, Bricks.
- `nodes`: graph API `new_graph`, `add_node`, `remove_node`, `duplicate_node`, `move_node`, `connect`, `disconnect`, `can_connect`, `set_node_input`, `set_node_prop`, `sanitize_graph`, `prune_graph`, `evaluate_graph`, `node_type`, `node_types_by_category`.
- `evaluate`: `make_context`, `evaluate_material`, `evaluate_pbr`, `display_color`.
- `convert`: `pbr_to_graph`, `convert_to_nodes`.
- `textures`: `new_texture`, `texture_params`, `sample_texture`, `load_image`, `resolve_image_path`, `add_image_search_path`, `clear_image_cache`.
- `noise`, `ramp`, `colorutil`: procedural helpers (value, perlin, fractal, voronoi; colour ramps; sRGB and HSV).
- `preview`: `render_preview`, `render_preview_array`, `thumbnail`, `clear_thumbnail_cache`.
- `tags`: `new_material_tag`, `apply_material`, `assign_to_selected`, `remove_from_selected`, `remove_material_tags`, `objects_using`, `effective_material_id`, `polygon_material_ids`, `project_uv`, `object_uvs`, `tag_uv`.
- `hub`: `MaterialsHub` signal object, `install_listener`, `emit`, `watch_scene`.
- `manager.material_from_image(scene, path)`.

## Widgets

`MaterialManager` (grid list, drag with mime `application/x-quartz-material`, Ctrl+D duplicate), `MaterialEditor` (channel pages, preview shape), `NodeEditor` (graphics view, zoom 0.25 to 4, add menu), `ui_common` fields (`ColorButton`, `FloatField`, `VecField`, `PathField`, `RampEditor`, `ParamForm`).

## Menus, docks, pages, shortcuts

- Menu `Materials`: New PBR Material, New Node Material, Presets (11), Apply to Selected, Remove from Selected, Duplicate Active, Delete Active, Convert Active to Nodes, Delete Unused, Load Library..., Save Library...
- Docks: Material Manager (bottom), Material Editor (right), Node Editor (bottom).
- Page: `Materials` with the three docks.
- Key action: Apply Material to Selected, `Ctrl+Shift+M`.

## Known gaps

- Two projection lists exist: `materials.tags.PROJECTIONS` has 5 entries, `tags.shading.PROJECTIONS` has 7 (adds `frontal`, `shrinkwrap`); a tag created by the tags package with those values is rejected by `new_material_tag`.
- Evaluation and previews are CPU numpy only; there is no GPU viewport shading of node graphs.
- Library format is JSON only; unknown formats raise `ValueError`.
