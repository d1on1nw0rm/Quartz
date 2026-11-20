# Quartz Studio: plan for the next session (waves 2, 3 and the pixel sweep, re-checked)

Written 20/11/2026 at the end of the night run, read-only, against the code as it was after the wave-1
integration (`TOTAL 2242 passed, 0 failed`). It replaces sections 4, 5 and 7 of `specs/plan.md` for the next
session. Sections 0 (common rules), 1 (decisions D1 to D20), 2 (hot files) and 6 (overrun rules) of `plan.md`
still hold unless a brief below says otherwise. Every brief here is complete: a builder reads its brief here,
not the old one.

## 0. What is true in the code now (checked, not assumed)

Files that do not exist yet (every wave-2 and wave-3 new module is still to write):
`quartz_studio/widgets/display_filter.py`, `quartz_studio/palettes.py`, `quartz_studio/widgets/palette_edit.py`,
`quartz_studio/objects/revolve.py`, `quartz_studio/objects/line_attrs.py`.

Landed in wave 1 and usable as the old briefs assumed:

- `objects/registry.py`: `Param` has `show: tuple = ()`, `axes: tuple = ("X", "Y", "Z")`, `ref: str = ""`,
  `visible(values)`; `Param.clamp` already handles the kinds `text`, `font` (empty falls back to the default),
  `font_style` and `link` (strings), `curve` (`_clamp_curve`, at most `CURVE_MAX_POINTS = 32`), `color`
  (3 units) and `vector` (3 bounded floats). `ObjectSpec` has `applies: dict` and
  `migrate: Callable[[dict], dict] | None` (run first in `ObjectSpec.clamp`). `link_keys(spec)`,
  `curve_value(curve, x)`, `mesh_is_spline`, `mesh_chains`, `BuildInput` exist.
- `objects/caps.py`: `bevel_profile(shape, size, segments, tension)`, `offset_rings(rings, distance)`,
  `safe_distance(rings, distance)`.
- `prefs.py`: `get(key, default)`, `set(key, value)`, `changed` (signal of a module hub), `path()`,
  `reload()`, `use_user_profile()`; tests isolate it with `QUARTZ_PREFS_DIR`.
- `controls`: `controls.register_action(id, label, category, run, keys=(), scope="global", available=None,
  path=None)`, `controls.run(id)`, `controls.binding_text(id)`, `controls.tooltip(label, id)`,
  `controls.modal_key(event, key)`, `controls.deferred_refresh()` (context manager), `controls.hub()
  .profileChanged`, `controls.reset()`.
- How a main-menu item becomes a controls action: `controls/actions.collect()` walks
  `menu_bar.SCENE_COMMANDS` (list of `(path, handler)`) and makes one action per path with id
  `menu_action_id(path, handler)` (form `menu.<slug>`), label `menu_label(path[-1])`, category `path[0]`
  and `available=SCENE_ENABLED.get(path)`. So a new main-menu item is registered by appending
  `(path, handler)` to `SCENE_COMMANDS` before `collect()` runs; nothing else is needed. Category "Window"
  (or any category not in `controls/editor.CATEGORIES`) is appended to the editor's category list
  automatically (`editor._fill_categories`), so no change in `controls/` is needed.
- `menu_bar.py`: overflow chevron (`overflow_menu`, `overflow_action`, `set_width_limit`, `natural_width`,
  `hidden_titles`, `menusChanged`), `_wire_scene_commands` (binds `SCENE_COMMANDS`, connects `aboutToShow`
  of every menu in `SCENE_ENABLED` to `refresh_enabled`, then `refresh_bindings`), `refresh_enabled` (only
  `setEnabled`), `refresh_bindings` (shortcut text from the active profile), `add_menu` and `add_entries`
  call `controls.register_action` for extension items inside `controls.deferred_refresh()`. The menu painter
  draws a check mark when the action has the property `qs_check` true (`_flag(act, "check")`, line ~854).
  `SCENE_CHECKED` does not exist yet.
- `widgets/attribute_manager.py`: no tabs (the `set_tab` stub is removed). `ParamEditor(param)` builds rows
  for `bool`, `choice`, `int`, `vector` (labels hard-coded "XYZ", not `param.axes`), `text` (`QLineEdit`,
  emits on `editingFinished`) and float with unit suffix (`distance`, `angle`, `percent`). No `font`,
  `font_style`, `link`, `curve` or `color` row, no `ParamEditor.set_context`. `AttributeManager` has
  `_rebuild_object_page`, `_make_group(spec_id, title, page, first, ...)` (collapsible groups, expanded
  state stored), `_hook_row_menu`, `_load`, `_load_params(obj, force, force_key)`, `param_applies(key, obj)`
  (D15 order), `_apply_applicable`, `_on_param`, `PARAM_APPLIES` with the `cube` and `cloner` entries and the
  helpers `_on`, `_is`. `LABEL_WIDTH = 120` here (the 160 of the integration report is the selection options
  card in `modeling/select_interaction.py`, not this file).
- `widgets/viewport.py` (133 kB): `MIN_DISTANCE = 2.0`, `MAX_DISTANCE = 1.0e6`, `MIN_APPROACH = 5.0`,
  `NAV_MIN_DEPTH = 100.0` (lines 259 to 262), `VIEWPORT_MENUS` (line 90), `OrbitCamera` (290) with `dolly`
  (385), `ngon_guides` (849), `cursor_point` (933), `_poly_screen` (981), `_paint_scene` (1478, the n-gon
  guide block now at ~1521, not ~1495 as interface.md 5.4 says), `navigate` (2112), `_scale_view` (2151,
  already exists), `zoom_at` (2176), `reset_camera` (2251), `frame_points` (2259), `ViewportMenuBar` (3050),
  `menu_titles` (3123), `_bind_menus` (3170). `reach_floor`, `carry_depth`, `NEAR_DEFAULT` do not exist.
  Every line number in interface.md 5.4 and 6 has drifted by about +25 to +30: locate by name.
- `widgets/menus_data.py`: `EDIT_MENU` is Undo, Redo, Undo History..., separator, Cut, Copy, Paste, Delete,
  separator, Select All, Deselect All, Select Children, separator, Project Settings..., Project Scale...,
  separator, Controls... (Shift+F12), Preferences... (Ctrl+E). `WINDOW_MENU` starts with
  `sub("Customization", [item("Customize Commands...", "Shift+F12"), ...])`.
- `modeling/install.py`: `PALETTE_MENU = "Mesh"`, `palette_groups(menu)`, `tool_tooltip(spec)`,
  `activate_tool(tool_id)`; the selection tools fold-out (D11) is on the rail.
- `scene.py`: `_flatten(root, kids)`, `_signature(flats)` (tuple of `(id, kind, matrix bytes, _mesh_sig)`
  per input), `_make_input(flat)` (static), `_build(obj, spec, inputs)`, `evaluate()`, `rename_object(obj,
  name)`. No link handling.
- `objects/gen_spline.py`: `_cap(points, outer, holes, ...)` (line 247, no `cap_type`), `_extrude_set`
  (378), `build_extrude`, `build_lathe`, `build_sweep`, `build_loft`, `text_chains` (763),
  `build_text_spline`, `build_text`, `_text_params` (820). No `_cap_params` or `_end_bevel_params`.
- Tests: 70 `tests/test_*.py` files; the wave-1 additions `test_top_row_overflow.py`,
  `test_objects_registry_kinds.py`, `test_objects_caps.py`, `test_prefs.py`, `test_selection_tools.py`,
  `test_select_sets.py`, `test_controls_*.py` are in the runner.

Consequences for the old briefs, in one list (details in each brief):

1. display-menus: `SCENE_CHECKED` is new work, and `refresh_enabled` must also apply checks; the
   `aboutToShow` connection must cover menus that have only checks (the Window menu has no
   `SCENE_ENABLED` entry today).
2. display-menus: the Window menu can sit in the overflow chevron at 1280 x 720 when extension pages are
   present; the items must work from there too (they do, `menu_at` walks `self.menus`, but the test must
   cover it).
3. vp-display-zoom: `_scale_view` already exists (wave 1, used by `zoom_at`); the brief now says "rewrite"
   not "add". Line numbers in interface.md are stale.
4. am-kinds: `vector` rows exist but ignore `param.axes`; the brief changes "add vector" to "make the
   vector tags read `param.axes`".
5. palettes-model: the Edit menu is longer than the old brief said; "Customize Palettes" and "Reset
   Palettes" go after "Controls..." and before "Preferences...". The acceptance list of the Edit menu is
   corrected below.
6. palettes-model and display-menus both edit `menus_data.py` and `menu_bar.py`: in the next wave they
   run together, so one builder (menus) owns both files and adds the palette items too.
7. Pixel sweep: `metrics.md` section 7 line numbers predate wave 1 and wave 2; the new files of the next
   wave (palette_edit.py, display_filter.py has no widgets) need owners in the sweep.

## 1. Owner's priority and how it maps to builders

| Priority | Owner's words | Builders |
|---|---|---|
| 1 | Scene Filter: n-gon lines on or off, shading with or without lines, wireframe | menus (display_filter, Window > Display and Filter), vp-display-zoom (canvas gates and shadings, viewport header menus) |
| 2 | Unlimited zoom | vp-display-zoom |
| 3 | Text with font and caps options | gen-text, am-kinds (font and style rows, multi-line text) |
| 4 | Attributes of objects and generators well modifiable | am-kinds, line-attrs, gen-surface (next wave); mesh-prims with revolve, spline-shapes, gen-sweep, gen-clone with scene-links, gen-boole (wave after) |
| 5 | Customisable palettes | palettes-model, palettes-edit, palettes-strips, palette-positions (next wave; the Edit menu items through menus) |
| 6 | Pixel norm | metrics M1 to M5 (wave after, after every UI file of the next wave has landed) |

## 2. Next wave (10 builders): Scene Filter, zoom, Text, attribute rows, palettes

### 2.1 File ownership

| Builder | Model | Files it owns (nobody else edits them in this wave) |
|---|---|---|
| N1 menus | opus | `quartz_studio/widgets/display_filter.py` (new), `quartz_studio/widgets/menus_data.py`, `quartz_studio/widgets/menu_bar.py`, `tests/test_display_state.py` (new) |
| N2 vp-display-zoom | opus | `quartz_studio/widgets/viewport.py`, `tests/test_display_filter.py` (new), `tests/test_zoom_unlimited.py` (new), `tests/test_camera.py`, `tests/test_viewport_draw.py`, `tests/test_viewport3d.py`, `tests/test_gizmo_transform.py` |
| N3 gen-text | opus | `quartz_studio/objects/gen_spline.py`, `tests/test_objects_gen_spline.py`, `tests/test_text_spline_attrs.py` (new) |
| N4 am-kinds | opus | `quartz_studio/widgets/attribute_manager.py`, `tests/test_attribute_manager.py` |
| N5 line-attrs | sonnet | `quartz_studio/objects/line_attrs.py` (new), `tests/test_line_attrs.py` (new) |
| N6 gen-surface | opus | `quartz_studio/objects/gen_surface.py`, `tests/test_objects_gen_surface.py` |
| N7 palettes-model | opus | `quartz_studio/palettes.py` (new), `tests/test_palettes_model.py` (new) |
| N8 palettes-edit | opus | `quartz_studio/widgets/palette_edit.py` (new), `quartz_studio/widgets/command_bar.py`, `tests/test_palette_edit.py` (new) |
| N9 palettes-strips | opus | `quartz_studio/widgets/tool_palette.py`, `quartz_studio/widgets/object_palette.py`, `tests/test_palettes.py` (new) |
| N10 palette-positions | opus | `quartz_studio/main_window.py`, `tests/test_palette_positions.py` (new) |

Shared tests (`test_smoke.py`, `test_wiring.py`, `test_hooks.py`, `test_objects_ui.py`,
`test_interface_defects.py`, `test_fileio_quartz.py`, `test_context_menu.py`, `test_tool_palette.py`,
`test_press_feedback.py`) belong to the integration step; builders run them and report what needs a change.
Nobody touches `theme.py`, `icons.py`, `scene.py`, `controls/` or the other session's packages in this wave.

Frozen names inside this wave (callers code against them from minute 0; the owner lands stubs in its first
15 minutes):
- `display_filter.py` (N1): `SHADINGS`, `TOGGLES`, `PREF_KEY = "viewport.display"`, `DisplayFilter`,
  `load()`, `save(df)`, `set_shading(name)`, `toggle(key)`, `reset()`, `menu_entries()`,
  `menu_commands()`, `menu_checks()` exactly as interface.md 5.2.
- `palettes.py` (N7): every public name of interface.md 7.2, plus `editing()`, `set_editing(on)`,
  `editingChanged`, `menu_commands()`, `menu_checks()`.
- `palette_edit.py` (N8): `attach(palette, palette_id, strip) -> PaletteEditor`, `PaletteEditor.refresh()`,
  `PaletteEditor.drop_target(pos) -> tuple[str, int]`, `PaletteEditor.context_menu(button) -> QMenu`,
  `GroupEditPopup`, `PaletteCatalog`. `command_bar.PaletteStrip.set_entries(entries)` (N8).
- `tool_palette.ToolPalette.rebuild()`, `ToolPalette.set_side(side)`, `object_palette.ObjectPalette.rebuild()`
  and its constructor keywords `orientation` and `popup_side` (N9).
- `line_attrs.py` (N5): the API of attributes-spline.md 5.2.

Drop order if the session runs short (last to go first): N6 gen-surface, then N10 palette-positions dock rail
modes (the tool rail left or right stays), then N8 drag and drop (context menu, popup and catalog stay).
Never drop N1, N2, N3, N4.

### 2.2 N1 menus: Display state module, Window > Display and Filter, Edit palette items (opus)

Files: `quartz_studio/widgets/display_filter.py` (new), `quartz_studio/widgets/menus_data.py`,
`quartz_studio/widgets/menu_bar.py`, `tests/test_display_state.py` (new).

Specs: plan.md sections 0 and 1 (D7, D16, D19, D20); interface.md 1.3 (`prefs`), 5.1, 5.2, 7.6 (only the
Edit menu items), 9.2 steps 1 (third bullet) and 2; this file section 0.

Task:
1. Within 15 minutes create `display_filter.py` with exactly the names of interface.md 5.2 on the prefs key
   `viewport.display`. It imports only `prefs` (and the standard library), so `menu_bar.py` and
   `viewport.py` may import it at module level. N2 uses these names from the start.
2. `menus_data.WINDOW_MENU`: insert as the first two entries `sub("Display", [...])` and
   `sub("Filter", [...])` built from `SHADINGS` and `TOGGLES` (check items, the separators of 5.2,
   "Reset Display"), then `SEP`, then the existing entries unchanged (the "Customization" submenu stays
   third).
3. `menus_data.EDIT_MENU`: insert `item("Customize Palettes")` and `item("Reset Palettes")` directly after
   `item("Controls...", "Shift+F12")` and before `item("Preferences...", "Ctrl+E", "gear")`. Nothing else in
   the Edit menu moves.
4. `menu_bar.py`:
   - Append `display_filter.menu_commands()` to `SCENE_COMMANDS` at module level, so
     `controls.actions.collect()` registers them as `menu.window.display.*` and `menu.window.filter.*`
     actions with category "Window" (the Controls editor lists the category by itself; do not edit
     `controls/`).
   - Add `SCENE_CHECKED: dict[tuple[str, ...], Callable[[], bool]]`, exported in `__all__` if the module has
     one, filled from `display_filter.menu_checks()`.
   - Palettes (D20, no module-level import of `palettes`): add a function `_palette_commands()` that imports
     `quartz_studio.palettes` inside a `try` and returns its `menu_commands()` (empty list on
     `ImportError`), and `_palette_checks()` the same for `menu_checks()`. Append the commands to
     `SCENE_COMMANDS` and the checks to `SCENE_CHECKED` lazily, the first time `_wire_scene_commands` runs
     (guard with a module flag so they are added once), and before `controls.refresh()` is called by
     `controls.install`. If `palettes.py` is still a stub, the items exist and do nothing harmful.
   - `refresh_enabled`: after the `setEnabled` loop, for each `(path, check)` of `SCENE_CHECKED`, find the
     action with `action_at(path)` and set `act.setProperty("qs_check", bool(check()))`, then `update()` the
     owning menu. Wrap each `check()` in `try` so a failing check leaves the mark off.
   - `_wire_scene_commands`: connect `aboutToShow` to `refresh_enabled` for every menu that holds a path of
     `SCENE_ENABLED` or `SCENE_CHECKED` (the Window menu and its Display and Filter submenus, the Edit menu).
   - Keep every wave-1 change intact: overflow chevron, `set_width_limit`, `hidden_titles`,
     `menusChanged`, `refresh_bindings`, `register_action` in `add_menu` and `add_entries`, `open_controls`.
5. Do not touch `viewport.py`.
6. `tests/test_display_state.py`: defaults; malformed and unknown prefs values fall back per field;
   `set_shading` and `toggle` persist through `prefs` (temporary `QUARTZ_PREFS_DIR`); `reset`;
   `menu_entries` structure and separators; in an offscreen `MainWindow` (use the `_isolated_main` pattern
   of `tests/test_smoke.py`, which sets `STORE_PATH`, `QUARTZ_PREFS_DIR` and calls `controls.reset()`):
   Window > Display > Wireframe sets the shading; the check marks follow on `aboutToShow`;
   Window > Filter > N-gon Lines flips `prefs.get("viewport.display")["ngon_lines"]`; Horizon likewise;
   `controls.actions()` (or `controls.actions.registry()`) has ids starting with `menu.window.display`;
   with `set_width_limit` small enough that Window goes into the overflow chevron, triggering
   Window > Display > Wireframe from `overflow_menu` still works; Edit shows Customize Palettes and Reset
   Palettes between Controls... and Preferences....

Run: `tests/test_display_state.py`, `tests/test_wiring.py`, `tests/test_smoke.py`, `tests/test_hooks.py`,
`tests/test_controls_widgets.py`, `tests/test_controls_dispatch.py`, `tests/test_controls_editor.py`,
`tests/test_top_row_overflow.py`. Report the pinned menu lists in shared tests that need the integration.

Accept: `tests/test_display_state.py` ends with 0 failed; the Window menu starts with Display and Filter whose
items work and draw their check marks, also from the overflow chevron; `display_filter.py` has every name of
interface.md 5.2; the controls and overflow suites end with 0 failed.

### 2.3 N2 vp-display-zoom: Display filter in the canvas and unlimited zoom (opus)

Files: `quartz_studio/widgets/viewport.py`, `tests/test_display_filter.py` (new),
`tests/test_zoom_unlimited.py` (new), `tests/test_camera.py`, `tests/test_viewport_draw.py`,
`tests/test_viewport3d.py`, `tests/test_gizmo_transform.py`.

Specs: plan.md sections 0 and 1 (D19); interface.md 5.1, 5.2 (names you call), 5.3, 5.4, 5.5, 6;
controls.md 2.5 (`zoom_to_cursor`, `wheel_step`, already wired); this file section 0 (current line numbers).

Task: You are the only owner of `viewport.py`. Locate every place by name: the line numbers in interface.md
5.4 and 6 are about 25 to 30 lines early since wave 1.
1. Display: `ViewportCanvas.display` loaded in `__init__` from `display_filter.load()` and reloaded on
   `prefs.changed` when the key is `display_filter.PREF_KEY` (then `update()`). Every gate of 5.4: the
   `ngon_lines` gate is the block in `_paint_scene` that calls `self.ngon_guides(mesh, k)` (now ~line 1521);
   the four shadings (Shaded with Lines, Shaded, Wireframe, Hidden Line) as 5.3; the other toggles of 5.2.
2. `VIEWPORT_MENUS` gets the two menus "Display" and "Filter" after "Cameras" from
   `display_filter.menu_entries()` (`ViewportMenuBar.menu_titles()` returns
   `["View", "Cameras", "Display", "Filter"]`). Rewire them in `ViewportMenuBar._bind_menus`: exclusive
   shading group, checks synced from `canvas.display` on every change (both from this header and from the
   main Window menu, because both write prefs). Keep the wave-1 binding texts of the View items (they come
   from `controls.binding_text`).
3. Unlimited zoom exactly as interface.md 6: the constants of 6.2 replace `MIN_DISTANCE`, `MAX_DISTANCE`,
   `MIN_APPROACH`, `NAV_MIN_DEPTH` (keep the four names importable as aliases if any test or module still
   imports them; checked on 20/11 at 10:42: outside `viewport.py` only `tests/test_camera.py`, which you own,
   imports them); add `NEAR_DEFAULT`, `reach_floor`,
   `carry_depth()`. Rewrite the existing `_scale_view` (it already exists and `zoom_at` already calls it),
   `OrbitCamera.dolly`, `cursor_point`, the camera-pivot step in `navigate` (only that line), ortho zoom,
   `frame_points`, the near plane following the reach, `reset_camera` and the camera presets back to
   `NEAR_DEFAULT`.
4. Screen guard last: Sutherland-Hodgman in `_poly_screen`, Liang-Barsky in the segment helpers, fast path
   untouched.
5. Keep wave-1 input code (`navigate`, `zoom_at` with its cursor-setting reads, `mousePressEvent`, the key
   handling through `controls`) working as it is.
6. Tests: write `tests/test_display_filter.py` (interface.md 5.5) and `tests/test_zoom_unlimited.py` (6.4);
   update `tests/test_camera.py` as 6.4 says and
   `tests/test_viewport_draw.py::test_header_is_overlaid_inside_the_canvas` for the four titles; touch
   `test_viewport3d.py` and `test_gizmo_transform.py` only if they break. If `display_filter.py` is not there
   yet when you start, code against the names of 5.2 and run your tests once it lands.

Run: those six files and `tests/test_controls_viewport.py`, `tests/test_selection_tools.py`,
`tests/test_pen.py`, `tests/test_context_menu.py`, `tests/test_modeling_interaction.py`.

Accept: both new test files end with 0 failed; with the default display the cube renders exactly as before
(`test_viewport_draw.test_default_cube_matches_shading_formula` passes); N-gon Lines off removes the guide
lines and nothing else; Wireframe and Hidden Line draw as 5.3; 200 wheel notches toward a face reach
`reach_floor` with the point under the cursor; the listed suites end with 0 failed. Timing: one paint of the
default scene must not get slower than today by more than 10 percent (measure with the probe used in
`tests/test_viewport_draw.py`, not with the full runner).

### 2.4 N3 gen-text: Text, Text Spline and Extrude attributes with caps and bevels (opus)

Files: `quartz_studio/objects/gen_spline.py`, `tests/test_objects_gen_spline.py`,
`tests/test_text_spline_attrs.py` (new).

Specs: plan.md sections 0 and 1 (D1, D17); attributes-gen.md 0, 3.6, 3.7, 3.11; attributes-spline.md 1,
3.14 (only `plane` and `reverse` of `text_spline`) and 6.2 (read with D1); this file section 0.

Task: unchanged from plan.md 4 in substance; the facts it relies on hold (`caps.py` has `bevel_profile`,
`offset_rings`, `safe_distance`; `Param` has `show` and `ref`; `Param.clamp` handles `font` and `font_style`).
1. Before editing, record the goldens of every default build of `gen_spline.py` (attributes-gen.md 0) in your
   scratch folder and paste them into `tests/test_objects_gen_spline.py`.
2. Text first: `_text_params()` (exists, line ~820) in the order of 3.11 (`font` kind `font`, `font_style`
   kind `font_style` with `ref="font"`, `interpolation`, `curve_points` with `show`); `text_chains` (exists,
   ~763) with the family and style rule and the Uniform walk; Text with `subdivision` and the full Caps group
   of Extrude through two new helpers `_cap_params()` and `_end_bevel_params()`; `text_spline` with `plane`
   and `reverse` (D1).
3. Extrude: params of 3.6 in order, Direction (Auto, X, Y, Z, Custom) with `offset`, Reverse Normals on walls
   only, caps and bevels through `objects/caps.py` exactly as 3.7 steps 1 to 5 inside `_extrude_set`
   (~378); change `_cap(points, outer, holes, ...)` (~247) to accept a trailing keyword
   `cap_type="Polygons"` with "Triangles" and "N-Gons". Defaults reproduce today's arithmetic bit for bit.
4. Do not change Lathe, Sweep or Loft. Keep the uses of `spline_shapes.PLANES` and `_to_space`.
5. Tests: the Text and Extrude tests of 3.7 and 3.11 in `tests/test_objects_gen_spline.py` (re-locate the
   old pins by content; the line numbers near 139 to 141 may have moved), and `tests/test_text_spline_attrs.py`
   (D1: `font_style="Bold"` of Arial gives a wider outline; a style the family lacks equals `""`).

Run: both files and `tests/test_objects_ui.py`, `tests/test_fileio_quartz.py`, `tests/test_trunk_generator.py`,
`tests/test_objects_registry_kinds.py`, `tests/test_objects_caps.py`.

Accept: both test files end with 0 failed; every GOLDEN triple of the default builds is unchanged; Text with
a Round bevel of 2 cm and 2 segments is a closed manifold whose counters stay open; Bold of Arial changes the
outline; start cap off leaves the front open; a `.quartz` saved before tonight opens with the same meshes.

### 2.5 N4 am-kinds: Attribute Manager row kinds (opus)

Files: `quartz_studio/widgets/attribute_manager.py`, `tests/test_attribute_manager.py`.

Specs: plan.md sections 0 and 1 (D1, D15); attributes-gen.md 4; attributes-spline.md 4 (4.1 items 3 to 5,
4.2) and 6.4; attributes-mesh.md 3.4; this file section 0.

Task (the tabs are gone; build on `_rebuild_object_page`, `_make_group`, `_load_params`, `param_applies`):
1. Font rows first. In `ParamEditor.__init__` add branches for `font` (combo of installed families from
   `QFontDatabase.families()`, cached once at module level, with a "(missing)" entry when the stored family
   is not installed), `font_style` (styles of the family named by the sibling key `param.ref`, refilled in
   `set_context`, no emission while the value is `""` and the list is being refilled), `link` (scene objects
   except self, ancestors and descendants, plus "(none)" and a "(missing)" entry), `curve` (`CurveEditor`
   64 px high: insert, drag, delete; one merged undo step per drag through `Scene._record("param:...")`),
   `color` (48 x 20 swatch opening `QColorDialog`). Mirror each in `set_value`, `value` and `is_busy`
   (`is_busy` counts open popups and curve drags).
2. `vector` rows exist: change the tags loop from the literal `"XYZ"` to `param.axes` (so Cloner rotations can
   show H, P, B).
3. `ParamEditor.set_context(scene, obj)`: new; `_load_params` calls it before `set_value` on every editor.
4. Multi-line text row (attributes-spline.md 4.1 item 3): for key `text` on specs `text_spline` and `text`, a
   `QPlainTextEdit` 72 px high instead of the `QLineEdit`, emitting on focus out and Ctrl+Enter.
5. Line rows (4.1 item 4) from `quartz_studio.objects.line_attrs` (N5 writes it now; import it inside
   functions so no Line rows show while it is missing), refreshed on the scene's `changed`,
   `selectionChanged` and `modeChanged`; shown in the same rows-only page, in their own collapsible group made
   with `_make_group`.
6. Add the helpers `_not`, `_all`, `_any` next to `_on` and `_is`, and the spline rules of 4.2 to
   `PARAM_APPLIES`; keep the `cube` and `cloner` entries (the integration of the wave after deletes `cube`
   once `prim_mesh.py` carries `spec.applies`); keep the D15 order in `param_applies`.
7. Keep every wave-1 change: no tabs, summary line for editable objects, collapsible groups with stored
   expanded state, row menus, `LABEL_WIDTH`, the D5 constants.
8. Tests: the cases of attributes-gen.md 4 and attributes-spline.md 6.4 with specs registered by the test
   (font, style following the family, link refusing self and family, curve insert, drag and undo, vector H P
   B, show conditions, empty sections hidden, Line rows), plus the 4.2 table.

Run: `tests/test_attribute_manager.py`, `tests/test_objects_ui.py`, `tests/test_interface_defects.py`,
`tests/test_modeling_ui.py`, `tests/test_coordinates.py`, `tests/test_press_feedback.py`.

Accept: `tests/test_attribute_manager.py` ends with 0 failed including every new kind; a `text` object shows
a font combo, a style combo that follows the family and a multi-line text row; a pen Line shows Close Spline;
the other suites end with 0 failed.

### 2.6 N5 line-attrs: Line attributes (sonnet)

Files: `quartz_studio/objects/line_attrs.py` (new), `tests/test_line_attrs.py` (new).

Specs: plan.md section 0; attributes-spline.md 5 (5.1, 5.2) and 6.3.

Task: unchanged. Create `line_attrs.py` with exactly the API of 5.2: `LINE_PARAMS` (Close Spline, Point
Thickness), `is_line`, `line_is_simple`, `line_values`, `line_applies`, `set_line_closed` (closing adds the
end edge, opening removes the closing edge by the largest index difference, one undo step with
`scene._record(f"line:{id(obj)}")`, `point_scales` kept), `set_line_value` (Point Thickness through
`scene.set_point_scales`). Import `mesh_chains`, `mesh_is_spline` and `Param` from `objects/registry.py`. Edit
no other file. Write `tests/test_line_attrs.py` with the five cases of 6.3.

Run: it and `tests/test_trunk_foundation.py`, `tests/test_pen.py`.

Accept: 0 failed; closing then opening a pen Line gives back the same edge set; undo after closing restores
the open Line; Point Thickness under a Trunk rebuilds it.

### 2.7 N6 gen-surface: Surface generator attributes (opus)

Files: `quartz_studio/objects/gen_surface.py`, `tests/test_objects_gen_surface.py`.

Specs: plan.md section 0; attributes-gen.md 0, 2 (registry names), 3.1 to 3.5.

Task: unchanged; the registry fields it needs (`show`, `migrate`) landed. Record the goldens first. Then
Subdivision Surface (`type` with Bilinear, label "Subdivision Viewport", `pre_subdivision`, `boundary` with
`show`, `_bilinear`, `_catmull_clark(corners=...)`), Symmetry (Planar and Radial with `show`, radial
construction and welding), Connect (no change), Remesh (target mode, polygon count, smoothing), Thicken
(`position` with `ObjectSpec.migrate` from `both_sides`, `shell`, `start_cap`, `end_cap`). Defaults reproduce
today. Update the tests with 3.1 to 3.5 (re-locate old pins by content).

Run: it and `tests/test_objects_ui.py`, `tests/test_fileio_quartz.py`.

Accept: 0 failed; GOLDEN holds at defaults; `spec.clamp({"both_sides": True})["position"] == 0.0`; Radial
Symmetry with 4 slices on a wedge gives a closed manifold symmetric in X and Z.

### 2.8 N7 palettes-model: Palette layouts, actions, edit state (opus)

Files: `quartz_studio/palettes.py` (new), `tests/test_palettes_model.py` (new). Changed from plan.md: the Edit
menu items and their wiring are written by N1, not by this builder; this builder owns no menu file.

Specs: plan.md sections 0, 1 (D7, D11, D16, D20) and 5 (frozen names); interface.md 7.2, 7.3, 7.5, 7.6
(`editing`, `set_editing`, `editingChanged`, `menu_commands`, `menu_checks`), 7.8 (cases 2 and 3);
controls.md 2.1.2.

Task:
1. Within 15 minutes create `palettes.py` with every public name of 7.2 as stubs that already return the
   default layouts (N8, N9, N10 and N1 call them).
2. Fill them in: `actions(palette_id)` (scene tools from `modeling.select_tools.TOOLS` and the transform and
   pen tools, mesh tools of `modeling.install.palette_groups(install.PALETTE_MENU)` including Trunk, create
   actions with icons and colours exactly as `object_palette._spec_entry` computes them, unique labels);
   `default_layout` equal to today's rail (the Selection fold-out of D11 included) and dock; `load` with every
   sanitising rule and the "More" group for new actions; `save`, `reset`, `reset_all`, `position`,
   `set_position`; `strip_entries(palette_id, layout, orientation)` returning `PaletteStrip` entries (`Item`,
   `Cmd`, `GAP`, `FLEX` and `DIVIDER` markers); the pure edit functions (never mutating input); `editing`,
   `set_editing`, `editingChanged` (module-level `QObject`).
3. `menu_commands()` returns `[(("Edit", "Customize Palettes"), toggle_editing), (("Edit", "Reset
   Palettes"), reset_all)]` and `menu_checks()` returns `{("Edit", "Customize Palettes"): editing}`; N1
   wires them (paths exactly these, so the action ids are `menu.edit.customize_palettes` and
   `menu.edit.reset_palettes`).
4. Storage on prefs keys `palette.tools` and `palette.objects`. Import widget modules only inside functions.
5. `tests/test_palettes_model.py`: cases 2 and 3 of 7.8, default layouts equal to today's palettes, round trip
   through `prefs` with a temporary `QUARTZ_PREFS_DIR`, edit functions never mutate input, `menu_commands`
   toggles `editing()` and resets both layouts (call the handlers directly; the menu test is N1's).

Run: it and `tests/test_tool_palette.py`, `tests/test_prefs.py`.

Accept: 0 failed; `default_layout("tools")` and `("objects")` describe today's palettes exactly; inputs of the
edit functions are never mutated.

### 2.9 N8 palettes-edit: Palette edit mode, drag and drop, group popup, catalog (opus)

Files: `quartz_studio/widgets/palette_edit.py` (new), `quartz_studio/widgets/command_bar.py`,
`tests/test_palette_edit.py` (new).

Specs: plan.md sections 0 and 5 (frozen names); interface.md 7.1, 7.4 (`PaletteStrip.set_entries`), 7.6,
7.8 (cases 6, 9, 10); metrics.md section 1 (the pixel norm: new sizes must already be allowed values).

Task: unchanged from plan.md 5 except the norm note.
1. In `command_bar.py` first, within 15 minutes: `PaletteStrip.set_entries(entries)` (removes and deletes
   every child widget, spacer, segment and button group, clears `buttons`, `gears`, `segments`,
   `button_groups`, adds the entries with `_add` and `_sync_segments`; the constructor calls it). Keep
   `SceneBinding` and the top bar unchanged.
2. `palette_edit.py` with the frozen names: while `palettes.editing()` an event filter on every palette
   button consumes press, move, release and double click; dashed accent border through the property
   `qsEditing`; drag start after `QApplication.startDragDistance()` with a 36 x 36 pixmap and the MIME payload
   of 7.6; drops on the same palette only; `drop_target` with the central 18 x 18 zone; insertion bar 2 x 28
   and the condense outline; a drop outside removes; a click on a group opens `GroupEditPopup` (reorder, Make
   Default, Move Out of Group, Remove); the right-click menus of 7.6 (Remove, Ungroup, Insert Divider Before,
   Remove Divider, then Customize Palette, Add Command... in edit mode, the Position submenu calling
   `palettes.set_position`, Reset Palette); `PaletteCatalog` 320 x 448 with search and double-click append;
   Escape anywhere leaves edit mode (an application filter installed only while editing, using
   `controls.modal_key(ev, "cancel")`). Every operation goes through the pure functions and `palettes.save`.
   Check each size above against metrics.md 1.1; where one is not allowed, use the nearest allowed value and
   report it.
3. Order: set_entries, edit state and click blocking, context menus, catalog, group popup, drag and drop. If
   drag and drop cannot be finished, the other operations must work and the drag code must be unreachable.
4. `tests/test_palette_edit.py`: cases 6, 9, 10 of 7.8 and each menu operation on a small strip.

Run: it and `tests/test_tool_palette.py`, `tests/test_smoke.py`, `tests/test_press_feedback.py`.

Accept: 0 failed; in edit mode a click never runs a command and Escape leaves edit mode; `drop_target` gives
insert and condense answers at centres, gaps and edges; the top bar and `test_press_feedback.py` unchanged.

### 2.10 N9 palettes-strips: Rebuildable tool rail and object dock (opus)

Files: `quartz_studio/widgets/tool_palette.py`, `quartz_studio/widgets/object_palette.py`,
`tests/test_palettes.py` (new).

Specs: plan.md sections 0, 1 (D11) and 5; interface.md 7.1, 7.3, 7.4, 7.5, 7.8 (cases 1, 4, 5, 7).

Task: unchanged from plan.md 5, with the wave-1 facts: the rail already has the Selection fold-out
(`select_tools`) and modeling groups with Trunk; mesh-tool tooltips come from `install.tool_tooltip` and are
refreshed on `controls.hub().profileChanged`; selection-tool tooltips show the binding through
`controls.tooltip`; Move, Rotate, Scale and Pen tooltips show only the name (integration deviation; keep it).
`ToolPalette.rebuild()` and `ObjectPalette.rebuild()` load `palettes.load(id)`, call
`palettes.strip_entries`, then `set_entries`, and rewire: create actions through
`set_command_action(label, run)`; mesh tools as today (`_modeling[id] = (button, label, spec.interactive)`);
scene tools through a new `SceneBinding` whose values are `{button: scene tool of its default, or
OTHER_TOOL}` and whose command map is `{button: {label: scene tool or OTHER_TOOL}}` with
`inert=(OTHER_TOOL,)`; refresh `buttons`, `button_groups`, `segments`, `gears`, `_gap_items`; run `_fit()`;
call `palette_edit.attach(...)` once (import inside the function; skip if the module is missing) and
`refresh()` after each rebuild. Both rebuild on `prefs.changed` for their key and on
`palettes.editingChanged`. The default layout gives exactly today's palettes. Keep every module constant
importable with today's values (`TOOL_PALETTE_ENTRIES`, `SCENE_TOOLS`, `OTHER_TOOL`, `PEN_KEY`,
`PEN_COMMANDS`, `SELECT_COMMANDS`, `modeling_entries`, `OBJECT_PALETTE_ENTRIES`, `CREATE_COMMANDS`,
`PALETTE_GROUPS`, `SHAPE_GROUP_COUNT`). Add `ToolPalette.set_side(side)` and make `ObjectPalette` work
vertical (`popup_side` "left", "right") and horizontal ("above", "below"). Do not touch `main_window.py`.
`tests/test_palettes.py`: cases 1, 4, 5, 7 of 7.8.

Run: it and `tests/test_tool_palette.py`, `tests/test_wiring.py`, `tests/test_objects_ui.py`,
`tests/test_trunk_tool.py`, `tests/test_trunk_generator.py`, `tests/test_smoke.py`,
`tests/test_press_feedback.py`, `tests/test_select_sets.py`, `tests/test_selection_tools.py`,
`tests/test_controls_widgets.py`.

Accept: `tests/test_palettes.py` 0 failed; the listed suites 0 failed unchanged; condensing Move onto Rotate
through `palettes.condense` and `save` rebuilds the rail with one fold-out that survives a new window; the
rail tooltips still follow the profile.

### 2.11 N10 palette-positions: Palette positions in the window (opus)

Files: `quartz_studio/main_window.py`, `tests/test_palette_positions.py` (new).

Specs: plan.md sections 0 and 5; interface.md 7.2 (`position`, `set_position`), 7.7, 7.8 (case 8); hooks.md 4.

Task: as plan.md 5, plus the wave-1 state of `main_window.py`: `MainWindow.fit_top_row()` (runs on top-bar
resize, `menusChanged`, `add_page`), `PageSwitcher` compact mode (`CompactPageButton`), the
`StudioSplitter`s, Coordinates fixed at 120 px, `controls.install(self)` at the end of `__init__`, and no
`_install_undo_shortcuts` or `_install_file_shortcuts`. Add `MainWindow.apply_palette_positions()` exactly as
interface.md 7.7, run at the end of `_build` and on `prefs.changed` for `palette.tools` and `palette.objects`:
tool rail first or last in `qsLeftBlock` with `tool_palette.set_side(position)`; object dock floating bottom
(today), floating top (40 px under the canvas top, `popup_side="below"`, no HUD dodge), or a vertical 48 px
card rail left or right; switching between floating and rail replaces the `ObjectPalette` instance
(`deleteLater` on the old one) and updates `self.object_palette` and `self.regions["object_palette"]`;
`place_object_dock()` does nothing for a rail; `dock_area()` stays the canvas rectangle. Keep every hook of
hooks.md 4. A rail position must not change the top row: after each move call `fit_top_row()` once.
`tests/test_palette_positions.py`: case 8 of 7.8 (rail right, dock top, dock rail_left, back to bottom gives
no error from `test_smoke._layout_errors`).

Run: it and `tests/test_smoke.py`, `tests/test_hooks.py`, `tests/test_layout_chrome.py`,
`tests/test_coordinates.py`, `tests/test_viewport_draw.py`, `tests/test_top_row_overflow.py`.

Accept: 0 failed; the default layout is pixel-identical to today (the listed suites 0 failed unchanged); each
position works at 1920 x 1010 and 1280 x 720.

### 2.12 Next-wave integration

1. Seams: N1's Edit items toggle the same `palettes.editing()` that N8's context menu and Escape use;
   `palette_edit.attach` is called by both palettes after every rebuild; the Position submenu moves the
   palettes through `apply_palette_positions`; the viewport header Display menu and Window > Display share
   one state through prefs; the font and style rows drive Text.
2. Shared tests: `test_smoke.py` and `test_wiring.py` (Window menu starts with Display and Filter; Edit menu
   list with the two palette items between Controls... and Preferences...; every visible control wired),
   `test_hooks.py` and `test_context_menu.py` if a menu count moved, `test_objects_ui.py`,
   `test_interface_defects.py`, `test_fileio_quartz.py` (Thicken saved with `both_sides`, Text with `font` and
   `font_style`), `test_tool_palette.py`.
3. Full run with the loop of plan.md section 0 until every file ends with 0 failed; the generator golden
   comparison (attributes-gen.md 0) confirmed from N3 and N6 reports plus one probe rerun.
4. End to end in the real window, Classic and Standard: Display > Wireframe, Hidden Line, Shaded, Shaded with
   Lines from the viewport header and from Window > Display; Filter > N-gon Lines off and on on an n-gon;
   Reset Display; state survives a new window; 200 wheel notches into the cube face and back, Frame Default; a
   Text set to Times New Roman Bold, Round bevel 2 cm, start cap off, two lines of text; an Extrude with
   Direction Auto; a Subdivision Surface Bilinear; a Line with Close Spline and Point Thickness; Edit >
   Customize Palettes, condense Move onto Rotate, insert a divider, add a command from the catalog, Escape;
   rail right, dock top, dock rail left, Edit > Reset Palettes; save and reopen.
5. Screenshots at 1920 x 1010 and 1280 x 720, each shading, the menus open, the Attribute Manager of Text and
   of a Line, edit mode, the group popup, the catalog, rail right and dock rail left.
6. `SPEC.md` 7.1 (new kinds in the Attribute Manager), 9.x (Display and Filter, unlimited zoom), 12 (palettes);
   `README.md`.
7. Rebuild `Quartz.exe` with `build.ps1` at the end (wave 1 was not in the exe before tonight's final build).

## 3. Wave after (10 builders): remaining attributes, scene links and the pixel sweep

The features left are pure object modules plus `scene.py`; the pixel sweep owns only UI files. The two sets
of files are disjoint, so they can run in the same wave. The sweep must still land after the next wave has
landed (it needs the final UI files) and its integration runs last.

### 3.1 File ownership

| Builder | Model | Files it owns |
|---|---|---|
| A1 mesh-prims | opus | `quartz_studio/objects/revolve.py` (new), `quartz_studio/objects/prim_mesh.py`, `tests/test_objects_revolve.py` (new), `tests/test_objects_prim_mesh.py`, `tests/test_objects_mesh_golden.py` (new) |
| A2 spline-shapes | opus | `quartz_studio/objects/spline_shapes.py`, `tests/test_spline_intermediate.py` (new), `tests/test_objects_spline_shapes.py` |
| A3 gen-sweep | opus | `quartz_studio/objects/gen_spline.py`, `tests/test_objects_gen_spline.py` |
| A4 gen-clone-boole | opus | `quartz_studio/objects/gen_clone.py`, `quartz_studio/objects/gen_boole.py`, `tests/test_objects_gen_clone.py`, `tests/test_objects_gen_boole.py` |
| A5 scene-links | opus | `quartz_studio/scene.py`, `tests/test_scene_links.py` (new) |
| M1 theme and shared | opus | `quartz_studio/theme.py`, `quartz_studio/widgets/common.py`, `quartz_studio/widgets/press_feedback.py`, `quartz_studio/icons.py`, `quartz_studio/app.py`, `tests/test_metrics.py` (new), `tests/test_press_feedback.py` |
| M2 window and top row | opus | `quartz_studio/main_window.py`, `quartz_studio/widgets/command_bar.py`, `quartz_studio/widgets/menu_bar.py`, `quartz_studio/widgets/status_bar.py`, `quartz_studio/widgets/context_menu.py`, `quartz_studio/widgets/menus_data.py`, `quartz_studio/widgets/title_row.py`, `quartz_studio/widgets/splitter.py`, `tests/test_smoke.py`, `tests/test_wiring.py`, `tests/test_context_menu.py`, `tests/test_top_row_overflow.py` |
| M3 viewport | opus | `quartz_studio/widgets/viewport.py`, `quartz_studio/modeling/interaction.py`, `quartz_studio/modeling/select_interaction.py`, `tests/test_viewport_draw.py`, `tests/test_viewport3d.py`, `tests/test_camera.py`, `tests/test_gizmo_transform.py`, `tests/test_modeling_interaction.py`, `tests/test_pen.py` |
| M4 palettes | opus | `quartz_studio/widgets/tool_palette.py`, `quartz_studio/widgets/object_palette.py`, `quartz_studio/widgets/palette_edit.py`, `tests/test_tool_palette.py`, `tests/test_palettes.py`, `tests/test_palette_edit.py` |
| M5 managers and controls editor | opus | `quartz_studio/widgets/object_manager.py`, `quartz_studio/widgets/attribute_manager.py`, `quartz_studio/widgets/coordinates.py`, `quartz_studio/modeling/panel.py`, `quartz_studio/controls/editor.py`, `tests/test_attribute_manager.py`, `tests/test_coordinates.py`, `tests/test_object_manager.py`, `tests/test_interface_defects.py`, `tests/test_modeling_ui.py`, `tests/test_controls_editor.py` |

Changes against metrics.md 12.2: `palette_edit.py` (new in the next wave) goes to M4;
`modeling/select_interaction.py` (the selection options card of wave 1, with its 160 px label column) goes to
M3; `controls/editor.py` (wave 1, `ROW_H`, `CATEGORY_W` and other local sizes) goes to M5; `title_row.py` and
`splitter.py` go to M2. Gen-boole is folded into gen-clone (A4) so the wave stays at 10.

Drop order (last first): A4 Boole and Voronoi part, then A3, then A2. A4 Cloner Object mode and A5 go
together or not at all.

### 3.2 A1 mesh-prims (with the revolve engine) (opus)

Files: see table. Specs: plan.md sections 0 and 1 (D15); attributes-mesh.md 0, 1 (1.1 to 1.18), 2.1, 2.2, 2.3.

Task: one builder now does both old briefs, in this order.
1. Write `tests/test_objects_mesh_golden.py` first (2.1, exact signature function and table) and check it
   passes on today's code.
2. Create `objects/revolve.py`: pure functions, no Qt, using `quartz_studio.modeling.primitives._Builder`
   (never import `prim_mesh`): `AXIS_EPS`, `revolve` (profile cleaning, full and sliced angles, axis vertices
   on use, flat caps and pies, triangle fans, quads, hints, cut faces only for enclosing profiles),
   `cylinder_profile`, `cone_profile`, `tube_profile`, `torus_profile`, `capped_profile` as 2.2.
   `tests/test_objects_revolve.py` with the table of 2.2 (copy `_closed`, `_euler`, `_volume`, `_valid`,
   `_solid` from `tests/test_objects_prim_mesh.py`).
3. `prim_mesh.py` section 1: range fixes and `spec.applies` rules first (inline lambdas; the field exists),
   then Cylinder and Cone (slice, fillets, caps), Tube, Disc, Torus, Oil Tank, Capsule, Polygon, Landscape
   (multifractal, borders, spherical, seed range). Every new path runs only when a new key leaves its
   default; the old code path stays verbatim. Update `tests/test_objects_prim_mesh.py` as 2.3.
4. Do not edit `attribute_manager.py`; report that `PARAM_APPLIES["cube"]` can be deleted (integration).

Run: the three test files, `tests/test_objects_ui.py`, `tests/test_fileio_quartz.py`,
`tests/test_modeling_primitives.py`.

Accept: all 0 failed with every count of 1 and 2.2; slices -90..90, 0..270, 45..46 and 180..0 are closed
solids; 0..360 equals the full revolution; every new int key ending in `segments` has a maximum.

### 3.3 A2 spline-shapes (opus)

Unchanged from plan.md 4 "spline-shapes" (files `objects/spline_shapes.py`, `tests/test_spline_intermediate.py`;
also owns `tests/test_objects_spline_shapes.py` now, but must leave it passing unchanged). Capture the golden of
attributes-spline.md rule 1.2 first; implement the tails, `intermediate`, `points_per_90` relabelled
"Number", `adaptive_angle`, `max_length`, knots, the None, Natural, Uniform, Adaptive and Subdivided wrapper,
`_clean` with knots, label and range fixes (Cissoid tension maximum 100), Helix biases (3.12, keep
`np.linspace` at 50). Keep `PLANES` and `_to_space(uvw, plane)` exactly (gen_spline imports them). Run the
golden comparison again at the end (no difference). Run also `tests/test_objects_gen_spline.py`,
`tests/test_trunk_generator.py`, `tests/test_fileio_quartz.py`. Accept: new file 0 failed, golden unchanged,
`test_objects_spline_shapes.py` 0 failed unchanged.

### 3.4 A3 gen-sweep: Lathe, Sweep and Loft attributes (opus)

As plan.md 5 "gen-sweep", with: the `_cap(..., cap_type="Polygons")` keyword and the Text and Extrude goldens
were added by N3 in the next wave and must keep passing; `registry.curve_value` and `ObjectSpec.migrate`
exist. Record Lathe, Sweep and Loft goldens (defaults, `caps` True and False) first. Lathe 3.8, Sweep 3.9
(`caps` removed through `migrate`, rail options, `scale_curve` through `curve_value`, `cap_type`), Loft 3.10.
Do not change Text, Text Spline or Extrude. Re-locate the old `caps` pins by content. Run also
`tests/test_text_spline_attrs.py`, `tests/test_objects_ui.py`, `tests/test_fileio_quartz.py`,
`tests/test_attribute_manager.py`. Accept: 0 failed, every GOLDEN holds, `spec.clamp({"caps": False})` gives
both caps False for Sweep and Loft, the scale curve case halves the middle ring.

### 3.5 A4 gen-clone-boole: Cloner, Array, Metaball, Voronoi Fracture (opus)

As plan.md 5 "gen-clone" then "gen-boole", one builder, Cloner first. Cloner 3.12 (Object and Honeycomb Array
appended to the mode choices, `reset_coordinates`, Object mode reading `p["object_link"]` as a `BuildInput`
or None, the Transform group with `axes=("H", "P", "B")` on rotations, which the Attribute Manager shows since
N4); Array label fix; Metaball `exponential_falloff`. Keep the old Cloner keys and the `PARAM_APPLIES["cloner"]`
rules valid (3.12.1). Then Voronoi 3.17 (`distribution`, `std_deviation` with `show`, `inside_only`,
`hull_only`, `scale_cells`, keyword-only arguments of `fracture_mesh`). Goldens first for each file. Run also
`tests/test_objects_ui.py`, `tests/test_fileio_quartz.py`, `tests/test_interface_defects.py`. Accept: both test
files 0 failed; GOLDEN holds for every old mode; Object mode with a cube target gives 8, 12, 6 and 20 clones
for Vertex, Edge, Polygon Center and Surface; no link gives an empty mesh; Inside on a torus never seeds the
hole; Hull Only keeps the input area within 1e-6 relative.

### 3.6 A5 scene-links (opus)

As plan.md 5 "scene-links", with the current names: in `Scene._build(obj, spec, inputs)` (or in `evaluate`
before it, which builds `inputs`), for each key of `registry.link_keys(spec)` resolve the stored name to the
first object of `self.objects` with that name, skipping the generator, its ancestors and its descendants, and
put `self._make_input(self._flatten(target, kids))` transformed into the generator's local space into the
values under that key, else `None`; extend `_signature(flats)` (today a tuple per input of `(id, kind, matrix
bytes, _mesh_sig)`) with the same tuple for each linked object; build generators with links in a second loop
of the same pass; `rename_object(obj, name)` renames every `link` param holding the old name in the same undo
step. Keep `extras`, `set_object_extra`, the Trunk thickness channel and every other API. Write
`tests/test_scene_links.py` with a spec registered by the test. Run also `tests/test_objects_core.py`,
`tests/test_fileio_quartz.py`, `tests/test_trunk_foundation.py`, `tests/test_trunk_generator.py`,
`tests/test_hooks.py`, `tests/test_objects_ui.py`. Accept: 0 failed; a scene without link params evaluates
exactly as before.

### 3.7 M1 to M5: pixel sweep

As `metrics.md` sections 1 to 12 with the ownership of table 3.1 above. Corrections:
- Every line number of metrics.md 3.5 and section 7 predates wave 1 and the next wave: find each literal by
  its value and context, not by line.
- New literals to sweep that metrics.md does not list: `palette_edit.py` (36 x 36 drag pixmap, 18 x 18 drop
  zone, 2 x 28 insertion bar, catalog 320 x 448), the dock rail 48 px of `main_window.apply_palette_positions`
  and the 40 px top offset, the `CurveEditor` 64 px and the 72 px text row and 48 x 20 swatch of
  `attribute_manager.py`, the selection options card in `select_interaction.py` (160 px label column),
  `controls/editor.py` (`ROW_H`, `ROW_PAD`, `CATEGORY_W`, the dialog size), the compact page button and the
  overflow chevron (`OVERFLOW_ICON`) of the top row.
- M1 lands the theme changes first, keeping `LEGACY_TOKENS`; the other four start at once against the names of
  metrics.md 3.3.
- Integration (metrics.md 12.4) runs after the feature integration of A1 to A5, last in the session.

### 3.8 Wave-after integration

1. Delete `PARAM_APPLIES["cube"]` from `attribute_manager.py` once `prim_mesh.py` carries the rules (check the
   Cube's fillet rows still hide and show).
2. Seams: the Cloner's Object row (link row of N4) offers the scene objects and the scene resolves it; moving
   and renaming the target rebuilds and follows.
3. Shared tests: `test_fileio_quartz.py` (Cylinder with slice and fillet, old rectangle and helix, Sweep with
   a scale curve, Sweep saved with `caps`, Cloner in Object mode with a link, Voronoi Hull Only),
   `test_objects_ui.py`, `test_interface_defects.py` (Cloner visibility), `test_objects_core.py` if needed.
4. Golden comparisons confirmed (spline 1.2, generator 0, mesh 2.1).
5. Metrics integration (12.4), `tests/test_metrics.py` green, full run 0 failed, screenshots at both sizes.
6. `SPEC.md` 7 ("As built" for generators, revolve, links), 9.3 and 9.5 for the norm; `README.md`; rebuild
   `Quartz.exe`.

## 4. Open points to confirm with the owner

- The selection options card label column is 160 px (contract 120); a shorter label would allow 120.
- The compact page switcher is used at 1920 x 1010 whenever the extension pages are installed.
- Whether "Customize Palettes" should also be reachable from the palettes' own right-click menu outside edit
  mode (interface.md 7.6 says yes; kept).
- Whether unlimited zoom should keep the old `MIN_DISTANCE` behaviour as an option in the Controls editor
  Cursor page (not planned).
