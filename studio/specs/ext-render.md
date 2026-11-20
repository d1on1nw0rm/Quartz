# Extension: render

Package `quartz_studio/render` (about 4.9k lines). Loaded by `ext/install.py` as `quartz_studio.render`.

## Purpose

CPU bucket renderer in numpy: scene snapshot and triangulation, rasterisation with depth peeling for transparency, GGX shading with materials from the materials package, shadow maps, screen-space AO, tone mapping, render passes, a picture viewer with history, an interactive render view, and light and camera object kinds.

## Data in extras

Scene extras `render` (`settings.SETTINGS_KEY`): `preset`, `width`, `height` (max 4096), `aa`, `output_path`, `format` (png, jpg, ...), `jpg_quality`, `auto_save`, `save_passes`, `passes` (beauty, depth, normal, albedo, ao), `camera`, `camera_id`, `animation`, `frame_start`, `frame_end`, `frame_step`, `background` and colours (`bg_color`, `bg_top`, `bg_bottom`, `sky_color`, `ground_color`), `ambient`, `default_lights`, `shadows`, `shadow_map`, `shadow_softness`, `ao`, `ao_radius`, and further tone and transparency fields (max 8 layers).

Object extras: `render_uid` (`engine.UID_KEY`) on cameras. Read only: `tags`, `material`, `materials`, `uvw` (through `bridges`).

Object kinds: `light` and `camera` (`objects.LIGHT_KIND`, `CAMERA_KIND`), registered by `objects.ensure_registered`.

## Public functions

- `engine`: `render(scene, camera, settings)`, `prepare_job`, `execute_job`, `resolve_camera`, `save_result`, `RenderJob`, `RenderResult`, `RenderCancelled`, `frame_path`, `buckets`.
- `settings`: `default_settings`, `get_settings`, `set_settings`, `update_settings`, `clean_settings`, `resolution`, `frame_list`.
- `camera`: `RenderCamera`, `look_at`, `from_orbit`, `from_canvas`, `from_object`, `focal_from_fov`, `fov_from_focal`.
- `shading`: `Light`, `tonemap`, `ggx_terms`, `shade_light`, `build_shadow_map`, `screen_ao`.
- `snapshot`: `capture_scene`, `build_geometry`, `scene_lights`, `default_lights`.
- `bridges`: optional links to tags, materials and anim (`phong_spec`, `polygon_uvs`, `sampler_for`, `evaluate_frame`, `timeline_range`).
- `worker`: `RenderManager` (threaded jobs, history limit 24), `RenderWorker`, `RenderRecord`, `get_manager`.
- `actions`: `render_view`, `render_to_picture_viewer`, `render_animation`, `cancel_render`, `edit_render_settings`, `show_picture_viewer`, `show_render_view`, `add_light`, `add_camera_from_view`.

## Widgets

`PictureViewer` (pass selector, history thumbnails, save), `RenderSettingsPanel`, `RenderView` (interactive), `ImagePane` (zoom and fit).

## Menus, docks, pages, shortcuts

- Menu `Render`: Render View, Render to Picture Viewer, Render Animation, Cancel Render, Edit Render Settings, Picture Viewer, Interactive Render View, Add Light (Point, Spot, Infinite, Area), Add Camera from View.
- Docks: Render Settings (right), Picture Viewer (bottom), Render View (right).
- Page: `Render`.
- Declared key actions: Render View `Ctrl+R`, Render to Picture Viewer `Shift+R`, Edit Render Settings `Ctrl+B`.

## Known gaps

- All three declared shortcuts are dropped by the installer: `Ctrl+R` and `Ctrl+B` are in `RESERVED_SHORTCUTS`, `Shift+R` has no Ctrl or Alt.
- Key actions are 2-tuples without callbacks; they only attach shortcuts to existing menu labels.
- No global illumination or ray tracing; reflections and refraction are approximated.
