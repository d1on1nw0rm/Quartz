# Extension: sculpt

Package `quartz_studio/sculpt` (about 4.8k lines). Loaded by `ext/install.py` as `quartz_studio.sculpt`.

## Purpose

Multiresolution sculpting on polygon objects: Catmull-Clark subdivision levels, sculpt layers with strength and visibility, masks, 17 brushes with falloff curves and stamps, symmetry, a viewport controller with brush overlay, and baking back to the mesh.

## Data in extras

Object extras `sculpt` (`data.KEY`, `VERSION` 2). Arrays are packed with tag `__qsarr__`. State dict:

`version`, `base_sizes`, `base_flat`, `base_sig`, `raw_sizes`, `raw_flat`, `raw_sig`, `base_loose`, `base_scales`, `origin` (base points), `levels` (list of point arrays per level), `level` (int), `layers` (list of `{"name", "strength", "visible", "locked", "deltas": [array or None per level]}`), `active_layer` (int, -1 for none), `mask` (per-point float array or None), `mask_levels`, `mask_enabled`, `frozen`.

Scene extras `sculpt_brushes` (`session.SCENE_KEY`): saved brush settings per brush id, active brush and symmetry.

Limit: `MAX_POINTS` 2,000,000.

## Public functions

- `data`: `ensure_state`, `get_state`, `has_sculpt`, `can_sculpt`, `subdivide`, `set_level`, `level_up`, `level_down`, `delete_higher_levels`, `add_layer`, `remove_layer`, `rename_layer`, `move_layer`, `clear_layer`, `set_active_layer`, `set_layer_strength`, `set_layer_visible`, `set_layer_locked`, `merge_layer_down`, `bake_layers`, `bake_to_mesh`, `remove_sculpt`, `mask_fill`, `mask_clear`, `mask_invert`, `mask_grow`, `mask_shrink`, `mask_smooth`, `summary`.
- `brushes`: `BRUSHES`, `BRUSH_ORDER`, `BrushDef`, `BrushSettings`, `brush`, `brush_ids`, `default_settings`.
- `stroke`: `SculptStroke`, `stroke_begin`, `stroke_dab`, `stroke_end`, `stroke_cancel`, `current_stroke`, `apply_dab`, `symmetry_frames`.
- `subdivision`: `catmull_clark`, `subdivide_mesh`. `topology`: `Topology`, `get_topology` (neighbours, normals, raycast).
- `falloff`: `evaluate`, `sample`, curve point editing. `stamps`: `generate`, `load_stamp`, `image_to_stamp`.
- `session`: `get_session(scene)`, `SculptSession` (active brush, target, symmetry, radius scaling).
- Package level: `toggle_sculpt_mode`, `attach_viewport(canvas, scene)`, `panel_factory`.

## Widgets

`SculptBrushPanel` (brush grid with drawn icons, sliders, `FalloffCurveEditor`, stamp preview), `SculptLayersPanel`, `ViewportSculptController` (mouse and tablet strokes, interactive radius and strength adjust), `BrushOverlay` (ring and mask dots).

## Menus, docks, pages, shortcuts

- Menu `Sculpt`: Sculpt Mode, Subdivide, Level Up, Level Down, Delete Higher Levels, Layers (Add Layer, Bake Layers), Mask (Invert, Clear, Fill, Grow, Shrink, Smooth), Symmetry (Local X, Y, Z), Bake to Mesh, Drop Sculpt Data, Brushes (Pull, Grab, Smooth, Inflate, Flatten, Fill, Scrape, Pinch, Knife, Polish, Clay, Wax, Amplify, Erase, Mask, Stamp).
- Docks: Sculpt Brushes, Sculpt Layers (declared right, placed left by `DOCK_AREAS`).
- Layout: `Sculpt` (dock layout).
- Key actions: Sculpt Mode `Ctrl+Shift+S`, Subdivide `Ctrl+Shift+D`, Level Up `Ctrl+Shift+Up`, Level Down `Ctrl+Shift+Down`, Invert Mask `Ctrl+Shift+I`, Smaller Brush `[`, Larger Brush `]`.

## Known gaps

- The installer drops shortcuts without Ctrl or Alt, so `[` and `]` are skipped; `Ctrl+Shift+S` and `Ctrl+Shift+I` are in `RESERVED_SHORTCUTS` and are also skipped. Only Subdivide and Level Up/Down get keys.
- The `key_actions` tuples are ordered (shortcut, label, fn), unlike other packages; the installer normalises them by pattern.
- Sculpting is CPU numpy; high levels near `MAX_POINTS` are slow.
