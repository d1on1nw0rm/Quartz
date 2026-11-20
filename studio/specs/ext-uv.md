# Extension: uv

Package `quartz_studio/uv` (about 6k lines). Loaded by `ext/install.py` as `quartz_studio.uv`.

## Purpose

Per-corner UV storage, seams, projections, LSCM and ARAP unwrapping, relax, island packing and alignment, a 2D UV editor, and simple texture painting onto per-object canvases.

## Data in extras

Object extras:

| Key | Shape |
|-----|-------|
| `uv` (`data.UV_KEY`) | list of `[u, v]` per polygon corner, in polygon order (ndarray envelopes are accepted on read) |
| `uv_seams` (`data.SEAMS_KEY`) | list of `[a, b]` point index pairs, sorted, `a < b` |
| `uv_tag` (`data.TAG_KEY`) | projection tag record used by `project.get_tag` and `uvw_from_tag` |
| `uv_textures` (`texture.TEXTURES_KEY`) | dict channel name to canvas record (`TextureCanvas.to_record()`, PNG bytes and size) |

Writes go through `data.write_object` and `store.set_object`.

## Public functions

- `data`: `has_uv`, `get_uv`, `get_uv_array`, `set_uv_array`, `ensure_uv`, `reset_uv`, `get_seams`, `set_seams`, `add_seams`, `remove_seams`, `clear_seams`, `sync_seams`, `sync_all`, `uv_islands`, `Corners`, transform helpers (`move_uv`, `rotate_uv`, `transform_uv`, `bounds_uv`).
- `project`: `project(obj, kind, polys)` (exported as `project_uv`), `project_flat`, `project_box`, `project_spherical`, `project_cylindrical`, `project_frontal`, `get_tag`, `set_tag`, `uvw_from_tag`, `look_at`.
- `unwrap`: `unwrap(obj, polys)` (exported as `unwrap_uv`), `relax`, `lscm`, `arap`, `spring_relax`, `angle_seams`, `seam_islands`, `cut_to_disc`.
- `arrange`: `pack_islands`, `align_islands`, `rectify`, `straighten`, `flip`, `rotate90`, `fit_to_bounds`, `stitch_edges`, `polygon_stretch`, `uv_stats`, `skyline_pack`.
- `texture`: `TextureCanvas`, `Brush`, `checker_image`, `checker_pixels`, `save_canvas`, `load_canvas`, `remove_canvas`, `texture_channels`, `uv_at_hit`, `paint_hit`, `paint_ray`.
- `session`: `session_for(scene)`, `drop_session`, `UVSession` (selection mode, tool, preview and commit).

## Widgets

`UVEditorView` with `UVCanvas` (zoom 16 to 65536, checker background, stretch overlay, transform handles), `UVToolsPanel` (projection, unwrap, relax, pack, stats), `TexturePaintPanel` (colour, new, checker, clear, load, save), `ViewportPainter` (event filter painting on the 3D viewport).

## Menus, docks, pages, shortcuts

- Menu `UV`: Projection (Flat, Box, Spherical, Cylindrical, Frontal), Generate UVW from Tag, Reset UVs, Seams (From Selected Edges, Remove Selected, By Angle, From UV Islands, Clear), Unwrap (Conformal, Isometric, Sharp Edges), Relax, Pack Islands, Align Islands, Rectify Grid, Stitch, Transform (Flip U, Flip V, Rotate +90, Rotate -90, Fit to Bounds, Straighten).
- Menu `Texture` (installed under `Materials > Texture`): New Texture, New Checker Texture, Fill Canvas.
- Docks: UV Editor (right), UV Tools (left), Texture Paint (left).
- Page: `UV Edit`.
- Key actions: UV Unwrap `Ctrl+Shift+U`, UV Pack Islands `Ctrl+Shift+P`, UV Relax `Ctrl+Shift+R`.

## Known gaps

- Dense solvers switch strategy above `DENSE_LIMIT` (900); very large meshes unwrap slowly in pure numpy.
- Painted canvases live in object extras as PNG bytes, which inflates scene files; there is no external texture file workflow.
- UV projection from the tags package (`tags.shading`) and from this package are separate code paths.
