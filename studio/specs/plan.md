# Quartz Studio night run: implementation plan

Written on 20/11/2026 by the planner from the six contracts of tonight (`controls.md`, `interface.md`,
`attributes-mesh.md`, `attributes-spline.md`, `attributes-gen.md`, `metrics.md`), `hooks.md`, SPEC.md section 10
and the code as it was at about 04:30. This plan replaces the file-ownership tables at the end of the six
contracts. Where a contract and this plan disagree, this plan wins; section 1 lists every resolved conflict.

## Schedule

Three waves. Each wave: builders about 55 minutes, integration about 30, reviewers and fix pass about 25.

| Wave | Start | Builders stop | Integration | Review and fix | End | Theme |
|---|---|---|---|---|---|---|
| 1 | 04:45 | 05:40 | 05:40 to 06:10 | 06:10 to 06:35 | 06:35 | Controls and profiles with the editor; selection tools (Brush first); splitter bar; Coordinates 120 px; Attribute Manager rows only; registry kinds and bevel engine |
| 2 | 06:35 | 07:30 | 07:30 to 08:00 | 08:00 to 08:25 | 08:25 | Viewport Display and Filter menus; unlimited zoom; Text font, style and caps; Extrude; spline sampling; Line attributes; mesh primitives; surface generators; new row kinds |
| 3 | 08:25 | 09:20 | 09:20 to 09:50 | 09:50 to 10:15 | 10:15 | Customisable palettes; Lathe, Sweep, Loft; Cloner modes and links; Array, Metaball; Voronoi; scene link resolution |

Margin 10:15 to 10:20. Hard stop for wave 3: its integration starts at 09:25 at the latest, whatever the builders'
state (section 6 says what is dropped then). Every wave leaves the application working and every suite at 0 failed,
so the run can stop after any wave.

Backup before every wave: the orchestrator copies every file listed for the wave (those that exist) into
`C:\Users\User\AppData\Local\Temp\qz\night\backup\wave<n>\` with their relative paths, so the integration agent
can restore a file whose builder failed (the folder is not a git repository).

## 0. Common rules for every agent

Every builder reads this section and section 1, then exactly the spec sections named in its brief.

- Edit only the files listed for you. A new file listed for you is yours to create. Anything you need in another
  file goes in your final report under "For integration", with the exact change.
- Re-read a file right before you edit it. The Trunk work (SPEC.md 10) landed before 04:45 in
  `modeling\interaction.py`, `modeling\install.py`, `icons.py`, `widgets\status_bar.py`, `widgets\object_palette.py`,
  `widgets\menus_data.py`, `modeling\ops_trunk.py`, `objects\gen_trunk.py`, `modeling\trunk_skin.py`: keep every
  Trunk change (tool, `M~R` chord, palette group, icons, hints, generator).
- No comments and no docstrings in code. English for code, interface text and docs. No emojis anywhere.
- Pixel norm (`metrics.md` 1.1, the owner's DesignPx rule): every px size you write is 0, 1 (lines and borders
  only), or one of 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 88, 96, 112, 120;
  from 128 up a multiple of 16, or a sum or difference of two values of the main range (2, 4, 6, 8, 12, 16, 24, 32,
  48, 64, 72, 96, 128, 256, 512, 1024). No odd px other than 1, no fractional px, fonts in px only (no new `pt`, no
  `setPointSize`). Colours only from `theme` tokens. Existing sizes you do not touch stay as they are tonight (the
  sweep of `metrics.md` is deferred, section 7).
- The window shows only controls that do something; an unwired menu item is pruned, an unfinished control is not
  shown.
- Python only as `.\.venv\Scripts\python.exe` from `D:\Apps\Quartz\studio`, with
  `$env:QT_QPA_PLATFORM='offscreen'; $env:QT_QPA_FONTDIR='C:/Windows/Fonts'`.
- There is no pytest in the venv. A test file is plain `test_*` functions plus the `_run_as_script()` runner and
  the `if __name__ == "__main__": sys.exit(_run_as_script())` block copied from `tests\test_smoke.py`. Run it as
  `.\.venv\Scripts\python.exe tests\<file>.py`; it must end with `0 failed`. Wherever a contract says pytest,
  conftest, `importorskip`, `-k` or parametrize, use this style instead (a loop inside one test function).
- Never kill a process by name, never run `build.ps1`, never touch the owner's running `Quartz.exe`.
- Never edit `quartz_studio\materials`, `tags`, `uv`, `sculpt`, `rig`, `anim`, `scripting`, `render`, `ext`,
  `tests\test_ext_*.py`, `specs\ext-*.md` (another session owns them), nor `SPEC.md`, `README.md` (integration
  only), nor anything in `D:\Markdown`.
- Shared tests that pin lists and counts (`tests\test_smoke.py`, `tests\test_wiring.py`, `tests\test_tool_palette.py`,
  `tests\test_context_menu.py`, `tests\test_hooks.py`, `tests\test_objects_ui.py`, `tests\test_interface_defects.py`,
  `tests\test_fileio_quartz.py`, `tests\test_fileio_ui.py`, `tests\test_objects_core.py`,
  `tests\test_modeling_integration.py`, `tests\test_trunk_*.py`) belong to the integration agent of the wave. A
  builder runs them and reports the exact edits they need; it never edits them.
- Scratch scripts, probes and goldens go in `C:\Users\User\AppData\Local\Temp\qz\night\<your key>\`.
- Same-wave dependencies: when you call a module another builder of your wave is writing, code against the names
  frozen in the contract and in this plan, import it inside functions so your module imports without it, keep at
  most a local stub while waiting, and delete the stub before you report. Your tests must pass with the real module
  present; if it is still missing when you finish, say so in the report.
- Final report: files changed, every test run with its last line, what is left undone, "For integration" items.

Integration agents may edit any file except the forbidden ones above (other session's packages and tests,
`D:\Markdown`). They own the shared tests, `SPEC.md` and `README.md`. Full-suite command (all of `tests\`, the
`test_ext_*` files included; a failure there caused by our change is fixed on our side, never in those files):

```
$env:QT_QPA_PLATFORM='offscreen'; $env:QT_QPA_FONTDIR='C:/Windows/Fonts'
Get-ChildItem tests -Filter 'test_*.py' | ForEach-Object { $out = & .\.venv\Scripts\python.exe $_.FullName 2>&1; $last = $out | Select-String 'passed,' | Select-Object -Last 1; "{0}: {1} (exit {2})" -f $_.Name, $last, $LASTEXITCODE }
```

Screenshots: `.\.venv\Scripts\python.exe tools\snapshot.py --out <png> --size 1920x1010` and `--size 1280x720`,
saved in `C:\Users\User\AppData\Local\Temp\qz\night\shots\wave<n>\`; extra grabs (dialogs, menus, crops) with
small scripts in the same folder that build the window offscreen and call `grab()`. The integration agent looks at
every picture it takes and fixes what is wrong before the reviewers start.

## 1. Decisions that resolve conflicts between the contracts

- **D1 Text font.** `attributes-gen.md` 3.11 and 4 govern: `font` becomes kind `font` (same key, same stored
  string), `font_style` is kind `font_style`, default `""`, `ref="font"`, filled from `QFontDatabase.styles(family)`.
  The `FONT_STYLES` choice of `attributes-spline.md` 3.14 is not built. From `attributes-spline.md` 3.14 only the
  `plane` and `reverse` params of `text_spline` are built. The font row is the `font` kind row of
  `attributes-gen.md` 4 (not a `QFontComboBox`); the multi-line text row of `attributes-spline.md` 4.1 item 3 is
  built. `attributes-spline.md` 6.2 cases 1 and 2 are read with `font_style` `""` as the default and `"Bold"` as
  the bold face.
- **D2 Coordinates height.** 120 px (`interface.md` 4.2), not 128 (`metrics.md` 7.11), with field rows of a real
  20 px. The local field rule must stay in the norm (no 1 px padding): for example
  `QLineEdit#qsCoordField { min-height: 14px; padding: 2px 6px; }`; the builder measures the real height. The
  deferred sweep reconciles it with `FIELD_H`; the owner decides 120 or 128 then.
- **D3 Splitter bar.** `interface.md` 3.2 values (bar 4, inset 24, `SPLITTER_HOVER`, `SPLITTER_DRAG`), not the
  values of `metrics.md` 9 (`metrics.md` 9 says the other contract's names win).
- **D4 Theme helpers.** Named as `metrics.md` 3.3: `PX_MAIN`, `PX_BELOW_128`, `allowed_px(v)`, `snap_px(v)`,
  `snap_px_up(v)` (rules of `metrics.md` 1.1 and 1.3, its examples must hold). `interface.md`'s `snap_up` is
  `snap_px_up`. Tonight only these helpers and the tokens `SPLITTER_BAR`, `SPLITTER_BAR_INSET`, `SPLITTER_HOVER`,
  `SPLITTER_DRAG` and `COORDINATES_H = 120` are added; every other token change of `interface.md` 8 and
  `metrics.md` 3 to 7 is deferred.
- **D5 Attribute Manager constants.** `attributes-mesh.md` 3.6 values (`LABEL_WIDTH` 120, `HEADER_H` 28,
  `VECTOR_SPIN_MIN` 32, `SPIN_TEXT_MARGIN` 6, `VECTOR_TEXT_MARGIN` 4, spacing 4, minimum 256 x 160, vector padding
  `2px 2px`), not `metrics.md` 7.10.
- **D6 Controls storage.** `controls.md` 3.5 (its own `controls.json`). `prefs.py` does not hold controls; the
  `controls.` namespace of `interface.md` 1.2 stays unused.
- **D7 Preferences location without pytest.** `prefs.path()` folder, in this order: `QUARTZ_PREFS_DIR` when set and
  not empty; else the folder of `project.SETTINGS_FILE` when it is set (`tests\test_smoke.py` and
  `tests\test_fileio_ui.py` set it); else, once `prefs.use_user_profile()` has been called (only `app.main` calls it),
  `%APPDATA%\Quartz` (`os.environ.get("APPDATA") or ~`); else one per-process temporary folder
  (`tempfile.mkdtemp(prefix="quartz-prefs-")`, created on first need). So no test and no `tools\snapshot.py` run can
  write the owner's profile. `tests\conftest.py` is not created. `use_user_profile()` and `reload()` are the only
  additions to the API of `interface.md` 1.3. Case 10 of `interface.md` 1.7 becomes: with no variable, no
  `SETTINGS_FILE` and no `use_user_profile()`, `path()` is under `tempfile.gettempdir()` and never under `APPDATA`.
  Tests that call `app.main` set `QUARTZ_PREFS_DIR` and `controls.STORE_PATH` to temporary paths and call
  `controls.reset()` after.
- **D8 Drag thresholds.** Input tolerances follow `controls.md` 2.5: Classic `drag_threshold` 3 (today), Standard
  4. `ViewportCanvas.DRAG_THRESHOLD`, `CONTEXT_DRAG_PX` and `interaction.DRAG_THRESHOLD` keep the Classic values as
  attributes (tests read them). The changes to 4 in `metrics.md` 7.13, 7.14 and `interface.md` 8.3 are not made.
  The click threshold of the Loop, Ring and Pattern tools (`interface.md` 2.6) is `controls.cursor("drag_threshold")`.
- **D9 Selection shortcuts.** Classic stays equal to today: no key for the new selection tools. Standard has `Q`
  for `tool.select`, which is now Brush Selection. The brush radius keys `[` and `]` stay hard-wired in the
  selection filter (`interface.md` 2.5); registering them as controls actions is deferred.
- **D10 Main menu Loop, Ring and Fill Selection.** As `interface.md` 2.3: in the main menu these labels open the
  interactive tools. The selection commands are appended to `menu_bar.SCENE_COMMANDS` inside
  `modeling.install.prepare()`, after the loop that appends the modeling commands, so they win (`interface.md` 9.2
  step 2 would put them before the modeling commands, because `prepare()` appends later, and they would lose). The
  commands keep their chords (`U~L`, `U~B`, `U~F` run the commands in Classic, as today) and stay in the context
  menu. The three menu items therefore show the binding of the tool action (none in Classic); the wave-1
  integration makes `tests\test_modeling_integration.py::test_every_tool_menu_item_shows_registry_shortcut` skip
  tool specs whose menu label is a name of `select_tools.TOOLS`.
- **D11 Selection rail group.** The rail's first button becomes the Selection fold-out in wave 1 (`interface.md`
  2.12 with the `SELECT_COMMANDS` map of 7.4), built by builder `select-core` inside today's `ToolPalette`, key
  `"Selection"` unchanged. The customisable palettes of wave 3 keep the same default layout.
- **D12 Controls before integration.** Until the wave-1 integration rewires `main_window.py`, `MainWindow` still
  creates its own `QShortcut`s and `modeling.install.install` may still be the old one. Every controls test that
  builds a window uses one helper: when the window has no `controls_filter` attribute, disable and delete every
  `QShortcut` child of the window, then call `controls.install(win)`; when it has one, do nothing. After integration
  the helper is a no-op.
- **D13 Dispatch names in `controls\__init__.py`.** The names that `controls.md` 6 gives to builder 2 (`install`,
  `refresh`, `lookup`, `hold_keys`, `is_navigation_press`, `modifier_held`, `modal_key`, `binding_text`, `tooltip`,
  `bindings`, plus `held_set`) are thin wrappers in `__init__.py` that import `quartz_studio.controls.dispatch` at
  call time. `__init__.py` also has `_set_window(window)`, which `dispatch.install` calls so that `window()` returns
  it.
- **D14 Held keys without a window.** `dispatch.held_set()` returns the one shared set and, the first time it is
  called while a `QApplication` exists, installs a small application filter that tracks presses and releases of
  `hold_keys()` (no Ctrl or Alt, no auto-repeat) and clears on `ApplicationDeactivate`. The `KeyFilter` of
  `install` reuses the same set. Canvas-only tests (`tests\test_camera.py`, `tests\test_viewport3d.py`) keep working.
- **D15 Spec-level visibility.** Both mechanisms exist: `ObjectSpec.applies` (`attributes-mesh.md` 0.4 and 3.5) and
  `Param.show` (`attributes-gen.md` 2.1). `param_applies` hides a row when any of them says so, then applies
  today's `PARAM_APPLIES` and the one-choice rule.
- **D16 Edit menu order.** Undo, Redo, separator, "Controls..." (the renamed "Customize Commands...",
  `controls.md` 4.1), then "Customize Palettes" and "Reset Palettes" (`interface.md` 7.6, wave 3).
- **D17 `gen_spline.py` across waves.** Wave 2: Text, Text Spline, Extrude, the shared
  `_cap(..., cap_type="Polygons")` argument and `_cap_params()` / `_end_bevel_params()`. Wave 3: Lathe, Sweep, Loft.
- **D18 Pixel pass.** `interface.md` section 8 and its `tests\test_px_norm.py` are superseded by `metrics.md`. The
  whole `metrics.md` sweep (sections 2 to 8, the guard `tests\test_metrics.py`, section 12) is deferred: `metrics.md`
  12.1 says it must run after every feature fleet, with one owner per file across nearly every widget file, which
  conflicts with every wave tonight. Wave 1 lands only the helpers of D4; every builder respects the norm in what it
  writes.
- **D19 Display filter split.** In wave 2 the state module `widgets\display_filter.py` and the main menu wiring
  (`menus_data.WINDOW_MENU`, `menu_bar.SCENE_CHECKED`) go to builder `display-menus`; the canvas gates, shadings, the
  viewport header menus and the zoom go to builder `vp-display-zoom`, the single owner of `viewport.py`.
- **D20 Late menu commands.** `widgets\object_palette.py` imports `widgets\menu_bar.py`, so `menu_bar.py` must not
  import `quartz_studio.palettes` at module level. Commands of modules that import widgets are appended when
  `MenuBar._wire_scene_commands` runs (a small `_late_commands()` that imports them inside the function), or by the
  module itself at its own import, never by a module-level import in `menu_bar.py`.

## 2. Hot files: one owner per wave

| File | Wave 1 | Wave 2 | Wave 3 |
|---|---|---|---|
| `quartz_studio\widgets\viewport.py` | ctl-viewport (input functions, HUD names) | vp-display-zoom (display gates, header menus, zoom) | nobody |
| `quartz_studio\main_window.py` | chrome (splitters, Coordinates sizes); integration adds `controls.install` | nobody | palette-positions |
| `quartz_studio\theme.py` | chrome | nobody | nobody |
| `quartz_studio\icons.py` | nobody (new icons are registered at import by their modules) | nobody | nobody |
| `quartz_studio\widgets\attribute_manager.py` | am-rows | am-kinds; integration deletes `PARAM_APPLIES["cube"]` | nobody |
| `quartz_studio\widgets\menu_bar.py` | ctl-widgets | display-menus | palettes-model |
| `quartz_studio\widgets\menus_data.py` | ctl-widgets | display-menus | palettes-model |
| `quartz_studio\widgets\common.py` | ctl-widgets (only `IconButton.mousePressEvent`) | nobody | nobody |
| `quartz_studio\widgets\tool_palette.py` | select-core | nobody | palettes-strips |
| `quartz_studio\widgets\object_palette.py` | nobody | nobody | palettes-strips |
| `quartz_studio\widgets\command_bar.py` | nobody | nobody | palettes-edit |
| `quartz_studio\widgets\status_bar.py` | ctl-widgets (controls names and selection hints) | nobody | nobody |
| `quartz_studio\objects\registry.py` | obj-registry | nobody | nobody |
| `quartz_studio\modeling\install.py` | ctl-dispatch; integration adds the selection hooks | nobody | nobody |
| `quartz_studio\modeling\interaction.py` | ctl-dispatch | nobody | nobody |
| `quartz_studio\scene.py` | nobody | nobody | scene-links |
| `quartz_studio\app.py` | integration | nobody | nobody |
| `quartz_studio\objects\gen_spline.py` | nobody | gen-text | gen-sweep |

The split of `viewport.py` across waves is real (checked in the code): the controls work of wave 1 lives in
`mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent`, `mouseDoubleClickEvent`, `wheelEvent`,
`_view_key_action`, `event`, `keyPressEvent`, `keyReleaseEvent`, `_nav_key_codes`, `_press_select`, `navigate`,
`zoom_at`, `_update_drag`, `_move_pen_press`, `OrbitCamera.orbit`, `_HeldNavKeys`, the tables `VIEW_KEYS`,
`TOOL_KEYS`, `NAV_KEYS`, `HUD_TEXTS`, `TOOL_NAMES` and `ViewportMenuBar._bind_menus` (shortcut texts only). The
zoom work of wave 2 lives in `_scale_view`, `OrbitCamera.dolly`, `cursor_point`, `frame_points`, `reset_camera`,
the camera `near`, the module constants `MIN_DISTANCE` to `NAV_MIN_DEPTH` and the segment and polygon helpers;
the display gates live in `paintEvent`, `_paint_scene`, `_paint_overlays`, `_paint_texts`, `pick_object`,
`gizmo_pick`, `VIEWPORT_MENUS` and `ViewportMenuBar._bind_menus`. `navigate` and `zoom_at` both call `_scale_view`
and `_bind_menus` is touched by both features, so the two go to different waves, and the wave-2 builder keeps the
wave-1 input code as it is.

Selection tools do not touch `viewport.py` beyond the name tables: they act through an event filter installed on
the canvas (`interface.md` 2.4) and read the canvas helpers `_object_view`, `_pick_point`, `_pick_edge`,
`_pick_polygon`, `_poly_screen`, `_edge_screen`, `_sight_clear`, `pick_object`, `project_world`, `_nav`,
`_held_keys`, which keep their names and signatures in every wave.

## 3. Wave 1: controls and profiles, editor, quick chrome, selection tools (04:45 to 06:35)

Goal: the controls package with both built-in profiles, live dispatch and a working Controls editor; Brush
Selection and the five other selection tools; the thin rounded splitter bar; Coordinates fixed at 120 px; the
Attribute Manager without Basic and Coord. tabs; the registry kinds and the bevel engine that wave 2 builds on.

### ctl-core: Controls core package (opus)

Files: `quartz_studio\controls\__init__.py`, `quartz_studio\controls\actions.py`, `quartz_studio\controls\profiles.py`,
`quartz_studio\controls\store.py`, `tests\test_controls_profiles.py`.

Specs: plan.md sections 0 and 1; controls.md sections 0, 1, 2 (2.1 to 2.5), 3, 5.2, 5.6 (block
test_controls_profiles), 7.

Task: Build the core of the new package `quartz_studio\controls`. Write `controls\__init__.py` first, within your
first 15 minutes, exposing every name of controls.md 5.2 so the four other controls builders can import it at
once; the dispatch names are thin wrappers that import `quartz_studio.controls.dispatch` at call time (D13); add
`_set_window(window)` used by `dispatch.install`. Never create `dispatch.py` or `editor.py` (builders ctl-dispatch
and ctl-editor). `hub()` returns one module-level `ControlsHub(QObject)` with `profileChanged = Signal(str)`.
`actions.py`: the `Action` dataclass, the `CORE` table of 2.1.1, `MENU_IDS`, the slug rule and `collect()` with the
steps of 2.1.2 (import `quartz_studio.modeling.registry`, `quartz_studio.objects`, `quartz_studio.widgets.menu_bar`
inside `collect` to avoid import cycles; read `menu_bar.SCENE_COMMANDS` at call time; `run` callables resolve the
window through `controls.window()` when called), `register_action` (step 5; after an install it calls `refresh()`).
`profiles.py`: `CLASSIC_NAME = "Classic"`, `STANDARD_NAME = "Standard"`, the `CLASSIC` (3.2) and `STANDARD` (3.3)
documents exactly as written (Standard binds `Q` to `tool.select`, D9), the frozen `Resolved` dataclass,
`resolve()` (3.1, including the Classic rule that adds every `ToolSpec.shortcut`, the Trunk `M~R` included, and
`default_keys`), binding validation with `QKeySequence(text).toString(PortableText)` (Delete equals Del), chord
parsing (2.2), `conflicts()` (2.2: scope overlap and the chord prefix rule), cursor clamping and enum fallback
(2.5), modifier roles and modal keys (2.4), `match_press` (2.3, including rule 4 for hold keys), `modifier_name`,
`cursor`. `store.py`: `path()` (3.5), `read()`, atomic writes, a corrupt store renamed to `controls.json.bad`,
unknown action ids kept, invalid bindings dropped with a `logging` warning (logger `quartz_studio.controls`),
`first_run()` and `previous_install()` (3.6; `winreg` on Windows). The profile operations of 3.4 (duplicate,
rename, delete, set and reset of keys, mouse, cursor, modifiers, modal, whole profile, export, import) with
`PermissionError` on built-ins, `ValueError` on bad names, unique names, duplicates named "<name> Copy",
"<name> Copy 2". The unloaded state is Classic with no disk access until `load()` or `first_run()`; `reset()`
returns to it. Write `tests\test_controls_profiles.py` with every case of the first block of 5.6 (a `QApplication`
for `QKeySequence` is fine; no window; `STORE_PATH` in a temporary folder). Run it and `tests\test_modeling_merge.py`.

Accept: `tests\test_controls_profiles.py` ends with 0 failed; every name of controls.md 5.2 imports from
`quartz_studio.controls`; `.\.venv\Scripts\python.exe -c "from quartz_studio import controls; print(controls.active_id())"`
prints `classic` and creates no file; both built-ins resolve with an empty `conflicts()`; the Classic resolved keys
equal tables 1.1 to 1.4 of controls.md, Trunk chord included.

### ctl-dispatch: Controls dispatch, key filter, modeling hooks (opus)

Files: `quartz_studio\controls\dispatch.py`, `quartz_studio\modeling\install.py`, `quartz_studio\modeling\interaction.py`,
`tests\test_controls_dispatch.py`.

Specs: plan.md sections 0 and 1 (D12 to D14); controls.md sections 1.2, 1.7, 1.9, 2.2, 2.3, 2.6, 5.1, 5.3, 5.4 (rows
`modeling/install.py` and `modeling/interaction.py`), 5.5, 5.6 (block test_controls_dispatch).

Task: Write `quartz_studio\controls\dispatch.py` as controls.md 5.3: `install(window)` (registry build, one
`QShortcut` per global non-chord binding in registry order skipping taken sequences, `window.file_shortcuts` in the
order new, open, merge, save, save as, save incremental, `window.key_shortcuts`,
`window.menu_bar.extension_shortcuts`, one `KeyFilter` on the `QApplication` stored as `window.modeling_shortcuts`
and `window.controls_filter`, rebuild on `hub().profileChanged`, call `controls._set_window(window)`), `refresh()`,
`KeyFilter` (one decision per physical press through the `ShortcutOverride` freshness flag; chords whose second key
wins over window shortcuts; text inputs skipped; viewport scope when the focus is the `Viewport` or nothing), and
the lookups `lookup`, `hold_keys`, `held_set` (D14), `is_navigation_press`, `modifier_held`, `modal_key`,
`binding_text`, `tooltip`, `bindings`. Fix the three defects of 1.9. In `modeling\install.py` (re-read it: the Trunk
work changed it) remove `_ShortcutFilter`, `_select_pen`, `_key_text`, `_key_of_event`, `SHORTCUT_WINDOW`,
`PEN_CHORD`; `install()` calls `controls.install(window)` only when `window` has no `controls_filter`;
`tool_tooltip(spec)` returns `controls.tooltip(spec.name, "tool." + spec.id)`; `_clear_foreign_chords` keeps the
registry chords plus the literal `"M~E"`; keep `prepare()`, `activate_tool`, `controller`, `palette_groups`,
`PALETTE_GROUPS`, `MORE_GROUP`, `PALETTE_MENU`, `on_tool` and every Trunk addition. Do not add the selection hooks
(integration step 2). In `modeling\interaction.py`: `DRAG_THRESHOLD` stays 3.0 as an attribute (D8) and every use
reads `controls.cursor("drag_threshold")`; `ViewportToolFilter._blocked(ev)` becomes
`controls.is_navigation_press(ev, canvas._held_keys)`; the Escape check becomes `controls.modal_key(ev, "cancel")`.
Other builders of this wave rely on the exact names of controls.md 5.2 and on `held_set()`. Write
`tests\test_controls_dispatch.py` with every case of the test_controls_dispatch block of 5.6, for both built-in
profiles, using the D12 window helper. Do not touch `main_window.py` or `app.py` (integration). Run
`tests\test_controls_dispatch.py`, `tests\test_modeling_integration.py`, `tests\test_modeling_interaction.py`,
`tests\test_trunk_tool.py`, `tests\test_pen.py`, `tests\test_hooks.py`.

Accept: `tests\test_controls_dispatch.py` ends with 0 failed for Classic and Standard, including the 1.9 cases (one
`K` press runs nothing, `K~L`, `U~C`, `M~#`, `M~,`); the listed existing suites end with 0 failed; no
`_ShortcutFilter` is left in the package.

### ctl-viewport: Viewport input through profiles (opus)

Files: `quartz_studio\widgets\viewport.py`, `tests\test_controls_viewport.py`, `tests\test_viewport3d.py`,
`tests\test_viewport_draw.py`.

Specs: plan.md sections 0, 1 (D8, D14) and 2; controls.md sections 1.3, 1.6, 2.3, 2.4, 2.5, 5.4 (rows
`widgets/viewport.py`), 5.5, 5.6 (block test_controls_viewport); interface.md section 2.11 (first bullet only).

Task: Make the canvas read its keys, mouse gestures, modifier roles, modal keys and cursor settings from the active
profile, as the `viewport.py` rows of controls.md 5.4 say: remove `VIEW_KEYS`, `TOOL_KEYS`, `NAV_KEYS`,
`_HeldNavKeys` (the canvas binds `self._held_keys` to `controls.held_set()`); `OrbitCamera.orbit(..., clamp=True)`;
`navigate` with `orbit_style`, `orbit_speed`, `invert_orbit_x/y`, `invert_pan`, `dolly_speed`; `zoom_at` with
`wheel_step` and `zoom_to_cursor`; `wheelEvent` with `wheel_invert`; `mousePressEvent` dispatching on the `op` of
`controls.match_press(...)`; `mouseDoubleClickEvent` with double gestures (an action through `controls.run`, a
canvas-only fallback for `view.frame_default`, no match falls back to a press); `_press_select(pos, op)` with op
`select`, `add`, `remove`; snap and extrude from `modifier_held`; thresholds from `drag_threshold` and
`click_tolerance` while `DRAG_THRESHOLD = 3` and `CONTEXT_DRAG_PX = 4` stay as attributes (D8); `_view_key_action`,
`event` (`ShortcutOverride` for viewport-scope keys and hold keys) and `keyPressEvent` through
`controls.lookup(e, "viewport")`, running `controls.run(id)` with a window and the canvas map `key_actions()` without
one; Escape, Return and Enter through `modal_key`; `ViewportMenuBar._bind_menus` writes the shortcut text of the six
View items from `binding_text` and refreshes on `profileChanged`; `nav_pivot` from `cursor("orbit_pivot")`, updated
on `profileChanged`. Also change the static name tables: `HUD_TEXTS` and `TOOL_NAMES` get `"select": "Brush
Selection"` and the five tool names of interface.md 2.11 (`select_loop`, `select_ring`, `select_pattern`,
`select_fill`, `select_phong`); update the HUD assertions `canvas.hud_text == "Selection"` in
`tests\test_viewport3d.py` (two, near line 398) and `tests\test_viewport_draw.py` (near line 351) to "Brush Selection".
Do not touch painting, `_scale_view`, `OrbitCamera.dolly`, `cursor_point`, `frame_points`, the zoom constants,
`VIEWPORT_MENUS` or the menu titles (wave 2). Keep the canvas helpers named in plan.md section 2 with their names
and signatures (the selection builders install their own event filter on the canvas). Write
`tests\test_controls_viewport.py` with every case of the test_controls_viewport block of 5.6. Run it and
`tests\test_camera.py`, `tests\test_viewport3d.py`, `tests\test_viewport_draw.py`, `tests\test_gizmo_transform.py`,
`tests\test_pen.py`, `tests\test_context_menu.py`.

Accept: `tests\test_controls_viewport.py` ends with 0 failed; `tests\test_camera.py`, `test_viewport3d.py`,
`test_viewport_draw.py`, `test_gizmo_transform.py`, `test_pen.py`, `test_context_menu.py` end with 0 failed with no
change other than the three HUD lines; no table of keys or mouse buttons is left in `viewport.py`.

### ctl-widgets: Menus, context menus, Object Manager, status bar through profiles (opus)

Files: `quartz_studio\widgets\menu_bar.py`, `quartz_studio\widgets\menus_data.py`, `quartz_studio\widgets\context_menu.py`,
`quartz_studio\widgets\object_manager.py`, `quartz_studio\widgets\common.py`, `quartz_studio\widgets\status_bar.py`,
`tests\test_controls_widgets.py`.

Specs: plan.md sections 0 and 1 (D10, D12, D16); controls.md sections 1.4, 1.8, 2.1.2 (step 5), 2.4, 2.6, 4.1, 5.4
(rows `widgets/object_manager.py`, `widgets/common.py`, `widgets/menu_bar.py`, `widgets/menus_data.py`,
`widgets/context_menu.py`, `widgets/status_bar.py`), 5.5, 5.6 (block test_controls_widgets); interface.md sections
2.3 (hint table), 2.11 (second and third bullets), 9.2 step 1 (first bullet, SELECT_MENU only); hooks.md section 5.

Task: Implement the controls rows of 5.4 for these files (re-read `menus_data.py` and `status_bar.py`: the Trunk work
changed them; keep it). `menus_data.EDIT_MENU`: "Customize Commands..." becomes `item("Controls...", "Shift+F12")`
(leave the Window menu entry of the same name alone; it stays unwired and pruned). `menus_data.SELECT_MENU`: add
`item("Pattern Selection")` after "Ring Selection" and rename "Phong Break Selection" to "Phong Angle Selection"
(nothing else; unwired items stay and are pruned). `menu_bar.py`: `SCENE_COMMANDS` gets
`(("Edit", "Controls..."), open_controls)` where `open_controls()` runs `controls.run("app.controls")`; new
`MenuBar.refresh_bindings()` (2.6) called at the end of `_wire_scene_commands` and on
`controls.hub().profileChanged`; `create_object` reads the roles `create_child` and `create_adopt`; `add_menu` and
`add_entries` register actions with `controls.register_action` (2.1.2 step 5) instead of creating their own
`QShortcut`, and `extension_shortcuts` stays the list of those actions' shortcuts so `tests\test_hooks.py` keeps
passing (hooks.md 5). `context_menu.py`: shortcut texts from `controls.binding_text`. `object_manager.py`:
`ObjectTree.keyPressEvent` through `controls.lookup(e, "objects")`, new `event()` accepting `ShortcutOverride` for
objects-scope keys. `common.py`: only `IconButton.mousePressEvent` sets the hold timer interval from
`controls.cursor("hold_ms")`; `HOLD_MS` stays 380. `status_bar.py`: the modifier and key names in the hints come from
`controls.modifier_name` and the modal keys (Classic texts stay exactly today's); `TOOL_NAMES` gets the six names of
interface.md 2.11; `TOOL_HINTS` gets `("select", "model")` and `("select", "components")` from the `hint_model` and
`hint` of Brush Selection and `(id, "any")` (or the lookup your `tool_hint` uses) for the five other selection tools
with the texts of interface.md 2.3, replacing today's `("select", ...)` entries. Do not add the selection or Display
menu commands to `SCENE_COMMANDS` (integration and wave 2). Write `tests\test_controls_widgets.py` with every case of
the test_controls_widgets block of 5.6 plus the status bar names and hints, using the D12 window helper. Run it and
`tests\test_wiring.py`, `tests\test_hooks.py`, `tests\test_context_menu.py`, `tests\test_object_manager.py`,
`tests\test_press_feedback.py`, `tests\test_objects_ui.py`, `tests\test_modeling_integration.py`; report failures
that only the integration can fix (for example the Edit menu list at `tests\test_wiring.py` line 528).

Accept: `tests\test_controls_widgets.py` ends with 0 failed; `tests\test_hooks.py`, `test_context_menu.py`,
`test_object_manager.py`, `test_press_feedback.py`, `test_objects_ui.py` end with 0 failed; the only `test_wiring.py`
failure left is the Edit menu list, reported for integration.

### ctl-editor: Controls editor dialog (opus)

Files: `quartz_studio\controls\editor.py`, `tests\test_controls_editor.py`.

Specs: plan.md sections 0 and 1; controls.md sections 2.2, 2.3, 2.4, 2.5, 3.4, 4 (4.2 to 4.7), 5.2, 5.6 (block
test_controls_editor); metrics.md section 1.1.

Task: Build `quartz_studio\controls\editor.py`: `open_editor(window)` keeps one non-modal `ControlsDialog(QDialog)`
per window (object name `qsControlsDialog`, 960 x 640 fixed, title "Controls") and raises it when already open; the
frame of 4.2 (profile combo listing `profiles()`, Duplicate, Rename, Delete, Import..., Export..., the read-only note
for built-ins, `PanelTabBar` with Keyboard, Mouse, Cursor, footer with Reset Profile and Close); the Keyboard page
of 4.3 (search, category list, action table with binding chips, add button, overridden bar, reset button, conflict
marks) with recording (grab the keyboard; a combination or non-printable key commits at once; a plain key waits
`chord_ms` for a chord; Escape alone or a click elsewhere cancels); the conflict banner of 4.4 (Replace, Keep Both,
Cancel); the Cursor page of 4.6; the Mouse page of 4.5 (gesture list with operation combos, order buttons, record
pad, Reset Mouse); `choose_import_file()` and `choose_export_file(name)` of 4.7. Every change applies at once through
the core functions (`set_keys`, `reset_action`, `set_cursor`, `set_mouse`, ...). Build in this order and keep each
step working: frame and profile operations, Keyboard page with recording and conflicts, Cursor page, Mouse page; a
page that is not finished at 05:35 is not shown (its tab is removed) and reported. Sizes exactly as 4.2 to 4.6,
colours from `theme` tokens; use `widgets.common` helpers (`make_card`, `prepare_combo`, `PanelTabBar`) and the
existing `plus` and `close` icons (paint locally with `theme.ICON_STROKE` if missing). Code against the core API of
controls.md 5.2 (builder ctl-core writes it now). Write `tests\test_controls_editor.py` with every case of the
test_controls_editor block of 5.6, using a temporary `controls.STORE_PATH`. Run it.

Accept: `tests\test_controls_editor.py` ends with 0 failed; the dialog fits 1280 x 720 and every size it sets is in
the norm; a built-in profile disables every editing control; Duplicate, recording `Ctrl+E`, a chord `M` then `E`,
Escape cancel, the three conflict buttons, the Cursor page and the Mouse record pad all write the store as specified.

### chrome: Splitter bar, Coordinates fixed height, theme helpers (opus)

Files: `quartz_studio\widgets\splitter.py`, `quartz_studio\widgets\coordinates.py`, `quartz_studio\theme.py`,
`quartz_studio\main_window.py`, `tests\test_layout_chrome.py`, `tests\test_coordinates.py`.

Specs: plan.md sections 0 and 1 (D2, D3, D4); interface.md sections 3 and 4; metrics.md sections 1.1, 1.3 and 3.3
(only the helpers `PX_MAIN`, `PX_BELOW_128`, `allowed_px`, `snap_px`, `snap_px_up`); hooks.md section 4.

Task: Create `quartz_studio\widgets\splitter.py` with `StudioSplitter` and `StudioSplitterHandle` exactly as
interface.md 3.2 (handle width 8, children not collapsible, states idle, hover, drag, a 4 px rounded bar inset 24 px
from each end, 8 px when the handle is shorter than 80, radius 2, `SPLITTER_HOVER` and `SPLITTER_DRAG`; a disabled
handle never paints and shows the arrow cursor). In `theme.py` add `SPLITTER_BAR = 4`, `SPLITTER_BAR_INSET = 24`,
`SPLITTER_HOVER = mix(ACCENT, SURFACE_BACKDROP, 0.5)`, `SPLITTER_DRAG = ACCENT`, set `COORDINATES_H = 120`, add the
helpers of D4 implementing metrics.md 1.1 and 1.3 exactly (every example of 1.3 must hold), and change the QSS
`QSplitter::handle` background to transparent (width and height rules kept, the hover rule removed); change nothing
else in the theme. In `main_window.py` build `body_splitter`, `manager_splitter`, the bottom splitter of
`_bottom_host` and the left column of `_left_host` as `StudioSplitter`; `apply_default_sizes` uses
`coord_h = theme.COORDINATES_H` (drop `COORD_RATIO` and the 60 floor); the handle directly above Coordinates is
disabled, re-applied whenever a widget is inserted into `manager_splitter` (the modeling tool options panel at index
1, `add_dock` right docks), so it stays the handle above Coordinates; keep every hook of hooks.md 4. Do not touch the
shortcut installs in `MainWindow.__init__` (the integration replaces them). In `coordinates.py` implement interface.md
4.2 with the D2 field rule (header widget with its own bottom hairline, no `HeaderRule`, margins 8, 4, 8, 8, spacing
4, grid spacing 2 and 6, titles 14, fields a real 20, Reset button `max(128, theme.snap_px_up(hint))`,
`MIN_H = theme.COORDINATES_H`, fixed height, `(Expanding, Fixed)`, minimum width 256). Write
`tests\test_layout_chrome.py` with interface.md 3.3 and the new part of 4.4, and change
`tests\test_coordinates.py::test_main_window_coordinates_not_clipped` to `cm.height() == MIN_H == 120`. Run
`tests\test_layout_chrome.py`, `tests\test_coordinates.py`, `tests\test_smoke.py`, `tests\test_interface_defects.py`,
`tests\test_hooks.py`, `tests\test_modeling_ui.py` and report what `test_smoke.py` needs (its measured table belongs
to integration).

Accept: `tests\test_layout_chrome.py` and `tests\test_coordinates.py` end with 0 failed (except the `current_tab`
use near line 354, which the integration removes); the Coordinates card is 120 px at 1920 x 1007 and 1280 x 720 and
stays 120 after moving a splitter or resizing to 1920 x 1300; an idle handle paints nothing, hover paints the 4 px
rounded bar; `tests\test_hooks.py` ends with 0 failed.

### am-rows: Attribute Manager without tabs, rows only (opus)

Files: `quartz_studio\widgets\attribute_manager.py`, `tests\test_attribute_manager.py`.

Specs: plan.md sections 0 and 1 (D5, D15); attributes-mesh.md sections 0 and 3 (3.1 to 3.7).

Task: Simplify the Attribute Manager exactly as attributes-mesh.md 3: remove the Basic and Coord. pages, the chips,
the section title and every name listed in 3.1, keeping `def set_tab(self, _name: str = "Object") -> None: return
None` as a compatibility stub (the wave-1 integration removes it); card layout of 3.2 with the new `summary_label`
and `mesh_summary(mesh)` (added to `__all__`); sections of 3.3 (first group without header, later groups
collapsible with remembered state per `(spec.id, title)` for the session, body spacing 2); `param_applies` of 3.5
reading `getattr(spec, "applies", None) or {}` first (the formal `ObjectSpec.applies` field is added this wave by
builder obj-registry; do not edit `objects\registry.py`), and also hiding a row when the param has a `visible` method
that returns False for the merged values (D15; `Param.visible` lands this wave, so use `getattr`); the pixel
constants of 3.6 (D5). No new row kinds in this wave. Update `tests\test_attribute_manager.py` as 3.7 (remove,
change, add). Run it and `tests\test_objects_ui.py`, `tests\test_coordinates.py`, `tests\test_interface_defects.py`,
`tests\test_context_menu.py`, `tests\test_trunk_generator.py`, `tests\test_modeling_ui.py`; the failures that use
the removed tab API (`page_basic`, `tab_available`, `current_tab`) are for integration: list them with file and line.

Accept: `tests\test_attribute_manager.py` ends with 0 failed; the card shows the Attributes header, the object line
and the rows only (no `Chip`, no `CoordField`, no `name_edit`); the default Cube shows "8 points · 6 polygons"; the
only failures left in the listed suites are the tab-API uses, reported for integration.

### obj-registry: Registry kinds, show, migrate, applies and the bevel engine (opus)

Files: `quartz_studio\objects\registry.py`, `quartz_studio\objects\caps.py`, `tests\test_objects_registry_kinds.py`,
`tests\test_objects_caps.py`.

Specs: plan.md sections 0 and 1 (D15); attributes-gen.md sections 0, 2 (2.1 to 2.5) and 3.7 (the `caps.py` API, its
edge cases and its tests); attributes-mesh.md sections 0.4 and 3.5 (the `applies` field).

Task: In `objects\registry.py` add, with defaults that change nothing for today's specs (the class `Param` extends
the frozen `modeling.registry.Param`, whose fields all have defaults after `default`, so new fields with defaults
are legal): the `Param` fields `show`, `axes`, `ref` and `Param.visible(values)` (2.1); the kinds `font`,
`font_style`, `link`, `curve`, `color` in `Param.clamp`, handled before `super().clamp`, and the helper
`curve_value` (2.2); `ObjectSpec.migrate`, applied first by `ObjectSpec.clamp` and never by `defaults` (2.3);
`link_keys(spec)` (2.4); `ObjectSpec.applies: dict = field(default_factory=dict)` after `description`
(attributes-mesh.md 3.5); export the new names in `__all__`. Land this registry change first, within 20 minutes:
builders am-rows (this wave) and five builders of wave 2 register params with these names. Then create
`objects\caps.py`, pure numpy, with exactly `BEVEL_SHAPES`, `bevel_profile`, `offset_rings`, `safe_distance` of 3.7.
Write `tests\test_objects_registry_kinds.py` (2.5) and `tests\test_objects_caps.py` (the `caps.py` tests of 3.7). Run
both and `tests\test_objects_core.py`, `tests\test_fileio_quartz.py`, `tests\test_objects_ui.py`,
`tests\test_objects_prim_mesh.py`, `tests\test_objects_gen_spline.py`, `tests\test_objects_gen_clone.py`,
`tests\test_trunk_generator.py`.

Accept: both new test files end with 0 failed; every registered spec clamps its own defaults to themselves; the
listed existing suites end with 0 failed unchanged.

### select-core: Preferences, selection tool table and sets, rail Selection group (opus)

Files: `quartz_studio\prefs.py`, `tests\test_prefs.py`, `quartz_studio\modeling\select_tools.py`,
`quartz_studio\widgets\tool_palette.py`, `tests\test_select_sets.py`.

Specs: plan.md sections 0 and 1 (D7, D9, D10, D11); interface.md sections 1 (with D7), 2.1, 2.2, 2.3, 2.6 (the sets
only), 2.7 and 2.8 (`fill_region`, `phong_region` and the click rules), 2.10, 2.12, 7.4 (the `SELECT_COMMANDS` line
only); controls.md section 5.4 (row `widgets/tool_palette.py`).

Task: Write `quartz_studio\prefs.py` first, within 15 minutes (interface.md 1 with the D7 location rule,
`use_user_profile()`, `reload()`, `VERSION`, `changed` signal of a module-level `_Hub(QObject)`), and
`tests\test_prefs.py` (cases 1 to 9 of 1.7 and the D7 version of case 10; point `QUARTZ_PREFS_DIR` at a temporary
folder inside the test and restore the environment after). Then write `quartz_studio\modeling\select_tools.py` with
every public name of interface.md 2.3: the `SelectTool` table and hints exactly, scene tool registration at import
(extend `scene.TOOLS` like `install._extend_scene_tools`), the five icons of 2.10 registered at import with
`icons.register` when missing (style of `tool_palette.register_tool_icons`, one citrine part each), `options`,
`set_option`, `reset_options` on the `prefs` key `selection.options`, `activate`, `ensure_mode`, `apply_selection`
(one undo step per changed selection through `scene._record("selection")`; the caller groups strokes),
`menu_commands()` (the six main-menu paths of 2.3), and the pure functions `loop_elements`, `ring_elements`,
`pattern_elements`, `fill_region`, `phong_region` (2.6 to 2.8, using `modeling.meshkit` helpers). Builder
select-brush writes `select_interaction.py` against these names at the same time; keep them exactly. In
`widgets\tool_palette.py`: the first rail entry becomes the Selection fold-out group (key `"Selection"`, shown command
"Brush Selection", six entries in the order of 2.12 with the icons of the tool table), `SELECT_COMMANDS` as in 7.4,
the `SceneBinding` command map gets the Selection button (as `PEN_COMMANDS` does), `SCENE_TOOLS` keeps
`"Selection": "select"`, `_LIVE_SELECTION` and `TOOL_PALETTE_ENTRIES[0]` stay importable; import `select_tools` so
its icons exist before the buttons are built; set the modeling tooltips from `install.tool_tooltip` and refresh them
on `controls.hub().profileChanged` (controls.md 5.4 row; import controls lazily). Write `tests\test_select_sets.py`:
tool table, `scene.TOOLS`, icons with one citrine part, options clamp and persistence through `prefs`,
`apply_selection` undo, cases 8 to 13 of interface.md 2.14 at the level of the pure functions and `activate`, plus the
rail group (fold-out of six; choosing Loop sets `scene.tool == "select_loop"`). Run `tests\test_prefs.py`,
`tests\test_select_sets.py`, `tests\test_tool_palette.py` (report the pinned changes it needs to integration),
`tests\test_wiring.py`, `tests\test_press_feedback.py`.

Accept: `tests\test_prefs.py` and `tests\test_select_sets.py` end with 0 failed; nothing is written under `APPDATA`
by any test; the rail's first button is a fold-out of the six selection tools and each entry sets its scene tool;
`tests\test_tool_palette.py` fails at most on the pinned first-button expectations, reported for integration.

### select-brush: Selection tool filter, Brush first, overlay and options card (opus)

Files: `quartz_studio\modeling\select_interaction.py`, `tests\test_selection_tools.py`.

Specs: plan.md sections 0, 1 (D8, D9) and 2; interface.md sections 2.2, 2.3 (names it calls), 2.4, 2.5, 2.6, 2.7,
2.8, 2.9, 2.14.

Task: Write `quartz_studio\modeling\select_interaction.py`: `SelectionToolFilter(QObject)` installed on the canvas,
with its `SelectionOverlay` child, acting only while `select_tools.is_select_tool(scene.tool)` and never consuming
the events listed in 2.4 (non-left buttons, plain wheel, Alt, held keys, a running navigation); undo grouping with
`scene.begin_group()` / `end_group()` so one stroke or click is one undo step; the editable check message. Build in
this order and keep each step working: Brush Selection (2.5: circle cursor, dabs along the stroke, hit rules per
mode, Model mode sampling, Shift+wheel radius, `[` and `]`), then Loop, Ring and Pattern (2.6: hover preview with
cache, click within `controls.cursor("drag_threshold")`, D8), then Fill (2.7) and Phong Angle (2.8), then
`SelectionOptionsPanel` (2.9) following `prefs.changed`. Add `install(window) -> SelectionToolFilter`: creates the
filter on `window.viewport.canvas` and the options card in `window.manager_splitter` right after
`window.tool_options` (index 1 when there is none), stores it as `window.selection_filter` and returns it (the wave-1
integration calls it from `modeling\install.py`). Use the canvas helpers named in plan.md section 2 and the
`select_tools` API (builder select-core writes it now). Write `tests\test_selection_tools.py` with every case of 2.14
(build a `Viewport` or a `MainWindow` and call `select_interaction.install` yourself). Run it and
`tests\test_viewport3d.py`, `tests\test_context_menu.py`, `tests\test_camera.py`.

Accept: `tests\test_selection_tools.py` ends with 0 failed, all 16 cases of interface.md 2.14; middle drag, Alt+left
and right click still navigate and open the context menu with a selection tool active; one stroke is one undo step.

### Wave 1 integration

1. `main_window.py`: the controls.md 5.4 row (remove `_install_undo_shortcuts`, `_install_file_shortcuts`,
   `FILE_SHORTCUTS`; call `controls.install(self)` at the end of `__init__`; `file_shortcuts` is set by install).
   `app.py`: `prefs.use_user_profile()` and `controls.store.first_run()` before `MainWindow()`, `controls.refresh()`
   after `install_extensions(window)`.
2. `modeling\install.py`: in `prepare()`, after the loop that appends the `activate_tool` commands, append
   `select_tools.menu_commands()` to `menu_bar.SCENE_COMMANDS`, skipping paths already appended by this step (D10);
   in `install(window)`, after the modeling panel and filter, `window.selection_filter =
   select_interaction.install(window)`.
3. Remove the Attribute Manager tab API: delete the `set_tab`, `tab_available`, `page_basic`, `current_tab` uses in
   `tests\test_objects_ui.py` (near lines 353 to 367; assert `attrs.object_host.isVisibleTo(attrs)` instead),
   `tests\test_coordinates.py` (near 352 to 357), `tests\test_interface_defects.py` (near 248),
   `tests\test_context_menu.py` (near 730), `tests\test_trunk_generator.py` (near 508), then delete the `set_tab` stub.
4. Shared tests: `tests\test_wiring.py` line 528 becomes `["Undo", "Redo", "---", "Controls..."]`;
   `tests\test_hooks.py::test_main_runs_with_a_raising_extension`, the `app.main` test of `tests\test_smoke.py` and of
   `tests\test_fileio_ui.py` set `controls.STORE_PATH` and `QUARTZ_PREFS_DIR` to temporary paths and call
   `controls.reset()` after (D7); `tests\test_smoke.py` measured table and default sizes for the fixed 120 px
   Coordinates and the `StudioSplitter`s; `tests\test_tool_palette.py` and `tests\test_smoke.py` for the Selection
   fold-out (key `"Selection"` unchanged, shown command "Brush Selection", six entries);
   `tests\test_modeling_integration.py` skip of D10; any test that checks for leftover top-level windows also closes
   the non-modal Controls dialog that `test_every_visible_control_is_wired` opens.
5. Confirm the D12 helper in the four controls test files is now a no-op (the window has `controls_filter`).
6. Run every suite with the loop of section 0 until every file ends with 0 failed. Then run the first run on this
   machine (controls.md 3.6): `.\.venv\Scripts\python.exe -c "from quartz_studio.controls import store;
   store.first_run(); print(store.read()['selected'])"` must print `classic` and `%APPDATA%\Quartz\controls.json`
   must exist.
7. End to end in an offscreen `MainWindow` after `modeling.install.install(win)`, with a temporary `STORE_PATH`:
   Classic `E`, `R`, `T` switch tools, `M~E` opens the Polygon Pen, `M~R` the Trunk tool, one `K` runs nothing, `K~L`
   and `U~C` run their tools, `C` makes the cube editable; select Standard live: `W` moves, `E` rotates, `Q` is Brush
   Selection, the menus, context menu and rail tooltips show the Standard bindings, Shift+middle pans; Edit >
   Controls... opens the dialog, Duplicate gives "Classic Copy", recording `Ctrl+E` on Extrude works and `Ctrl+E` then
   runs Extrude; Brush Selection paints points in Points mode and Ctrl paints them off, one undo restores; Loop
   Selection selects an edge loop, Fill fills a region; hover on a splitter handle shows the bar; the Attribute
   Manager shows no chips and the Cube summary; Coordinates is 120 px at both sizes. Select Classic again at the end.
8. Screenshots: the window at 1920 x 1010 and 1280 x 720; the Controls dialog on each page at 1280 x 720; the rail
   with the Selection fold-out open; a splitter handle in hover state (crop); the Brush circle over the cube in
   Points mode; the Selection options card.
9. `SPEC.md`: a short section 11 "Controls" pointing to `specs/controls.md`, the "with shortcut" wording of 3.4 and 4
   replaced by "with the active profile's binding", 9.5 (Coordinates fixed at 120, the splitter bar), 9.6 (splitter
   row: idle invisible, hover `SPLITTER_HOVER` 4 px rounded bar, drag `SPLITTER_DRAG`), 9.8 (new tool names and
   hints), 3.8 (no chips; rows only), 7.1 (`ObjectSpec.applies`, the new `Param` fields and kinds); a section 12
   "Interface customisation" pointing to `specs/interface.md`. `README.md`: a "Controls" section (where the editor is,
   the two profiles, the store path) and the selection tools.

## 4. Wave 2: viewport Display and Filter, unlimited zoom, object and generator attributes (06:35 to 08:25)

Goal: the Display and Filter menus and unlimited zoom; Text with font family, style and caps (first); Extrude caps
and bevels; spline intermediate points; Line attributes; mesh primitives against Cinema 4D (slice, fillets,
landscape); surface generators; the Attribute Manager row kinds these need.

### vp-display-zoom: Display filter in the canvas and unlimited zoom (opus)

Files: `quartz_studio\widgets\viewport.py`, `tests\test_display_filter.py`, `tests\test_zoom_unlimited.py`,
`tests\test_camera.py`, `tests\test_viewport_draw.py`, `tests\test_viewport3d.py`, `tests\test_gizmo_transform.py`.

Specs: plan.md sections 0, 1 (D19) and 2; interface.md sections 5.1, 5.2 (names you call), 5.3, 5.4, 5.5, 6;
controls.md section 2.5 (rows `zoom_to_cursor` and `wheel_step`, wired in wave 1).

Task: You are the only owner of `viewport.py` in this wave. Display first: `ViewportCanvas.display` loaded in
`__init__` from `display_filter.load()` and reloaded on `prefs.changed` for `display_filter.PREF_KEY` (builder
display-menus writes `quartz_studio\widgets\display_filter.py` with the frozen names of interface.md 5.2 in its first
15 minutes); `VIEWPORT_MENUS` gets the two ghost menus "Display" and "Filter" after Cameras from
`display_filter.menu_entries()` (`menu_titles()` is `["View", "Cameras", "Display", "Filter"]`), rewired in
`ViewportMenuBar._bind_menus` (exclusive shading group, checks synced from `canvas.display` on every change) while
keeping the wave-1 binding texts of the View items; every gate of 5.4 and the four shadings. Then unlimited zoom
exactly as interface.md 6: the constants of 6.2 replacing `MIN_DISTANCE`, `MAX_DISTANCE`, `MIN_APPROACH`,
`NAV_MIN_DEPTH`; `reach_floor`; `carry_depth()`; `_scale_view`, `OrbitCamera.dolly`, `cursor_point`, the
camera-pivot step in `navigate` (only that line), ortho zoom, `frame_points`, the near plane following the reach,
`reset_camera` and presets back to `NEAR_DEFAULT`. Last, the screen guard (Sutherland-Hodgman in `_poly_screen`,
Liang-Barsky in the segment helpers, fast path untouched). Keep the wave-1 input code (`navigate`, `zoom_at`,
`mousePressEvent`, keys) working as it is; `zoom_at` keeps its cursor-setting reads and calls the new `_scale_view`.
Write `tests\test_display_filter.py` (5.5) and `tests\test_zoom_unlimited.py` (6.4); update `tests\test_camera.py` as
6.4 says and `tests\test_viewport_draw.py::test_header_is_overlaid_inside_the_canvas` for the four titles; touch
`tests\test_viewport3d.py` and `tests\test_gizmo_transform.py` only if they break. Run those six files and
`tests\test_controls_viewport.py`, `tests\test_selection_tools.py`, `tests\test_pen.py`, `tests\test_context_menu.py`.

Accept: `tests\test_display_filter.py` and `tests\test_zoom_unlimited.py` end with 0 failed; with an empty profile
the default cube renders exactly as before (`test_viewport_draw.test_default_cube_matches_shading_formula` passes);
200 wheel notches toward a face reach `reach_floor` with the point under the cursor; the listed suites end with 0
failed.

### display-menus: Display state module and the main menu Display and Filter (opus)

Files: `quartz_studio\widgets\display_filter.py`, `quartz_studio\widgets\menus_data.py`,
`quartz_studio\widgets\menu_bar.py`, `tests\test_display_state.py`.

Specs: plan.md sections 0 and 1 (D7, D19, D20); interface.md sections 1.3 (the `prefs` API), 5.1, 5.2, 9.2 steps 1
(third bullet, WINDOW_MENU) and 2 (only `display_filter.menu_commands()` and `SCENE_CHECKED`); controls.md section
2.1.2 (how menu items become actions).

Task: First, within 15 minutes, create `quartz_studio\widgets\display_filter.py` with exactly the names of
interface.md 5.2 (`SHADINGS`, `TOGGLES`, `PREF_KEY`, `DisplayFilter`, `load`, `save`, `set_shading`, `toggle`,
`reset`, `menu_entries`, `menu_commands`, `menu_checks`) on the `prefs` key `viewport.display`; it imports only
`prefs` (no widget modules, so `menu_bar.py` may import it at module level). Builder vp-display-zoom uses these names
now. Then `menus_data.WINDOW_MENU`: first two entries `sub("Display", [...])` and `sub("Filter", [...])` built from
`SHADINGS` and `TOGGLES` (check items, the separators of 5.2, "Reset Display"), then a separator; the rest of the menu
unchanged. `menu_bar.py`: append `display_filter.menu_commands()` to `SCENE_COMMANDS`; add `SCENE_CHECKED: dict[path,
Callable[[], bool]]` (exported in `__all__`) filled from `display_filter.menu_checks()`, applied in `refresh_enabled`
as `act.setProperty("qs_check", bool(check()))` and connected to `aboutToShow` the same way as `SCENE_ENABLED`; check
items must render their check mark (the `"check"` flag the menu painter reads). Keep every wave-1 controls change
(`refresh_bindings`, `register_action` in `add_menu` and `add_entries`, `open_controls`). Do not touch
`viewport.py`. Write `tests\test_display_state.py`: defaults, malformed and unknown prefs values fall back per field,
`set_shading` and `toggle` persist through `prefs` (temporary `QUARTZ_PREFS_DIR`), `reset`, `menu_entries` structure
and separators, and in an offscreen `MainWindow`: Window > Display > Wireframe sets the shading, the check states
follow on `aboutToShow`, Window > Filter > Horizon flips `prefs.get("viewport.display")["horizon"]`, and the controls
registry lists these items as actions (`controls.actions()` has ids starting with `menu.window.`). Run it and
`tests\test_wiring.py`, `tests\test_smoke.py`, `tests\test_hooks.py`, `tests\test_controls_widgets.py`,
`tests\test_controls_dispatch.py`; report the pinned menu lists that need integration.

Accept: `tests\test_display_state.py` ends with 0 failed; the Window menu starts with Display and Filter whose items
work and show their checks; `display_filter.py` has every name of interface.md 5.2; the controls suites still end
with 0 failed.

### gen-text: Text, Text Spline and Extrude attributes with caps and bevels (opus)

Files: `quartz_studio\objects\gen_spline.py`, `tests\test_objects_gen_spline.py`, `tests\test_text_spline_attrs.py`.

Specs: plan.md sections 0 and 1 (D1, D17); attributes-gen.md sections 0, 3.6, 3.7 (use of `caps.py` in `_extrude_set`
and `_cap`), 3.11; attributes-spline.md sections 1, 3.14 (only the `plane` and `reverse` params of `text_spline`) and
6.2 (read with D1).

Task: Before editing, record the goldens of every default build of `gen_spline.py` (attributes-gen.md 0) in your
scratch folder and paste them into `tests\test_objects_gen_spline.py`. Text first, it is the owner's top item of
this wave: `_text_params()` in the order of 3.11 (`font` kind `font`, `font_style` kind `font_style` with
`ref="font"`, `interpolation`, `curve_points` with `show`), `text_chains` with the family and style rule and the
Uniform walk, Text with `subdivision` and the full Caps group of Extrude (`_cap_params()`, `_end_bevel_params()`),
`text_spline` with `plane` and `reverse` (attributes-spline.md 3.14 construction, D1). Then Extrude: params of 3.6 in
order, Direction (Auto, X, Y, Z, Custom) with `offset`, Reverse Normals on walls only, caps and bevels through
`objects\caps.py` (landed in wave 1: `bevel_profile`, `offset_rings`, `safe_distance`) exactly as 3.7 steps 1 to 5,
`_cap(points, outer, holes, normal, cap_type="Polygons")` with Triangles and N-Gons. Defaults must reproduce today's
arithmetic bit for bit. Do not change Lathe, Sweep or Loft (wave 3) beyond what the new default argument of `_cap`
needs (none). Keep the uses of `spline_shapes.PLANES` and `_to_space` as they are (builder spline-shapes keeps both).
Tests: the Text and Extrude tests of 3.7 and 3.11 in `tests\test_objects_gen_spline.py` (update its pins near lines
139 to 141), and `tests\test_text_spline_attrs.py` with font style, plane and reverse cases (D1: Bold through
`font_style="Bold"` of Arial gives a wider outline; a style the family lacks equals `""`). Run both and
`tests\test_objects_ui.py`, `tests\test_fileio_quartz.py`, `tests\test_trunk_generator.py`,
`tests\test_objects_registry_kinds.py`.

Accept: both test files end with 0 failed; the GOLDEN triples of every default build are unchanged; Text with a Round
bevel of 2 cm and 2 segments is a closed manifold whose counters stay open; `font_style` "Bold" of Arial changes the
outline; start cap off leaves the front open; a `.quartz` saved before tonight opens with the same meshes.

### am-kinds: Attribute Manager row kinds for fonts, links, curves, text and Lines (opus)

Files: `quartz_studio\widgets\attribute_manager.py`, `tests\test_attribute_manager.py`.

Specs: plan.md sections 0 and 1 (D1, D15); attributes-gen.md section 4; attributes-spline.md sections 4 (4.1 items 3
to 5, 4.2) and 6.4 (read with D1); attributes-mesh.md section 3.4.

Task: Font rows first (Text is the owner's top item). Add the row kinds of attributes-gen.md 4 to `ParamEditor`:
`font` (combo of installed families cached once, "(missing)" entry), `font_style` (styles of the `ref` family,
refilled in `set_context`, no emission when `""`), `link` (scene objects except self, ancestors and descendants,
"(missing)" entry), `curve` (`CurveEditor` 64 px: insert, drag, delete, merged undo through
`Scene._record("param:...")`), `color` (48 x 20 swatch), `vector` tags from `param.axes`;
`ParamEditor.set_context(scene, obj)` called by `_load_params` before `set_value`; `is_busy` counting open popups
and curve drags. Add the multi-line text row of attributes-spline.md 4.1 item 3 (`QPlainTextEdit` 72 px for key
`text` on `text_spline` and `text`, emitting on focus out and Ctrl+Enter). Add the Line rows of 4.1 item 4 from
`quartz_studio.objects.line_attrs` (builder line-attrs writes it now; import it inside functions so no Line rows show
while it is missing) refreshed on `changed`, `selectionChanged` and `modeChanged`. Add the helpers `_not`, `_all`,
`_any` and the spline rules of 4.2 to `PARAM_APPLIES` (keep the `cube` and `cloner` entries; the integration deletes
`cube`); keep the D15 order in `param_applies`. Keep every wave-1 change (no tabs, summary line, collapsible groups,
D5 constants). Tests: the cases of attributes-gen.md 4 and attributes-spline.md 6.4 with specs registered by the test
(font, style, link, curve, vector H P B, show conditions, empty sections hidden, Line rows), plus the 4.2 table. Run
`tests\test_attribute_manager.py`, `tests\test_objects_ui.py`, `tests\test_interface_defects.py`,
`tests\test_modeling_ui.py`, `tests\test_coordinates.py`.

Accept: `tests\test_attribute_manager.py` ends with 0 failed including every new kind; a `text` object shows a font
combo, a style combo that follows the family and a multi-line text row; a pen Line shows Close Spline; the other
listed suites end with 0 failed.

### spline-shapes: Spline intermediate points and shape fixes (opus)

Files: `quartz_studio\objects\spline_shapes.py`, `tests\test_spline_intermediate.py`.

Specs: plan.md section 0; attributes-spline.md sections 1, 2 (2.1 to 2.4), 3.1 to 3.13, 6.1.

Task: Capture the golden of rule 1.2 first (every spline at defaults and the variants of 6.1 case 3, in your scratch
folder). Then implement the three tails `_tail("curved" | "linear" | "none")` with `intermediate`, `points_per_90`
(relabelled "Number"), `adaptive_angle`, `max_length` (2.2), the constants of 2.2, every chain function taking `s` and
returning knots (2.3, 2.4), the wrapper with None, Natural, Uniform, Adaptive and Subdivided, `_clean` carrying knots,
the label fixes, the range fixes (Cissoid tension maximum 100) and the Helix biases (3.12 with the special case that
keeps `np.linspace` at 50). Keep `PLANES` and `_to_space(uvw, plane)` exactly (builder gen-text uses them). Defaults
reproduce today bit for bit. Write `tests\test_spline_intermediate.py` with the 13 cases of 6.1 and re-run your golden
comparison (it must report no difference). Run it and `tests\test_objects_spline_shapes.py`,
`tests\test_objects_gen_spline.py`, `tests\test_trunk_generator.py`, `tests\test_fileio_quartz.py`.

Accept: `tests\test_spline_intermediate.py` ends with 0 failed; the golden comparison reports no difference;
`tests\test_objects_spline_shapes.py` ends with 0 failed unchanged.

### line-attrs: Line attributes (sonnet)

Files: `quartz_studio\objects\line_attrs.py`, `tests\test_line_attrs.py`.

Specs: plan.md section 0; attributes-spline.md sections 5 (5.1, 5.2) and 6.3.

Task: Create `quartz_studio\objects\line_attrs.py` with exactly the API of 5.2: `LINE_PARAMS` (Close Spline, Point
Thickness), `is_line`, `line_is_simple`, `line_values`, `line_applies`, `set_line_closed` (closing adds the end edge,
opening removes the closing edge by the largest index difference, one undo step with
`scene._record(f"line:{id(obj)}")`, `point_scales` kept), `set_line_value` (Point Thickness through
`scene.set_point_scales`). Import `mesh_chains`, `mesh_is_spline` and `Param` from `objects\registry.py`; do not edit
any other file (builder am-kinds shows the rows). Write `tests\test_line_attrs.py` with the five cases of 6.3. Run it
and `tests\test_trunk_foundation.py`, `tests\test_pen.py`.

Accept: `tests\test_line_attrs.py` ends with 0 failed; closing then opening a pen Line gives back the same edge set;
undo after closing restores the open Line; Point Thickness under a Trunk rebuilds it.

### mesh-revolve: Revolve engine (opus)

Files: `quartz_studio\objects\revolve.py`, `tests\test_objects_revolve.py`.

Specs: plan.md section 0; attributes-mesh.md section 2.2.

Task: Create `quartz_studio\objects\revolve.py`, pure functions with no Qt, using
`quartz_studio.modeling.primitives._Builder` (never import `prim_mesh`): `AXIS_EPS`, `revolve` (profile cleaning,
full and sliced angles, axis vertices created on use, flat caps and pies, triangle fans, quads, hints, cut faces only
for enclosing profiles), `cylinder_profile`, `cone_profile`, `tube_profile`, `torus_profile`, `capped_profile` exactly
as specified, and the edge cases. Builder mesh-prims calls these signatures right now; keep them exactly and land a
first working `revolve` and `cylinder_profile` within 20 minutes. Write `tests\test_objects_revolve.py` with the table
of counts and checks of 2.2 (copy the `_closed`, `_euler`, `_volume`, `_valid`, `_solid` helpers from
`tests\test_objects_prim_mesh.py`). Run it.

Accept: `tests\test_objects_revolve.py` ends with 0 failed with every point and polygon count of the table and every
solid check; slices -90..90, 0..270, 45..46 and 180..0 are closed solids; 0..360 equals the full revolution.

### mesh-prims: Mesh primitive attributes against Cinema 4D (opus)

Files: `quartz_studio\objects\prim_mesh.py`, `tests\test_objects_prim_mesh.py`, `tests\test_objects_mesh_golden.py`.

Specs: plan.md sections 0 and 1 (D15); attributes-mesh.md sections 0, 1 (1.1 to 1.18), 2.1, 2.3.

Task: Write `tests\test_objects_mesh_golden.py` first (2.1, with the exact signature function and the table) and
check it passes on today's code. Then implement section 1 in `prim_mesh.py`: the shared slice helpers (1.1), the
range fixes (cube segments, sphere segments), the Polygon segments and orientation, slices for disc, torus, cone,
tube, cylinder, oil tank and capsule, the cone fillets, the tube and cylinder fillets, the caps groups, the landscape
multifractal, borders and spherical options, the seed range, and `spec.applies` rules on every spec named
(attributes-mesh.md 0.4, inline lambdas; the `applies` field landed in wave 1). Every new path runs only when a new
key leaves its default; the old code path stays verbatim. Use `quartz_studio.objects.revolve` (builder mesh-revolve
writes it now; your slice and fillet tests fail by import until it lands, everything else must pass). Order of work:
range fixes and `applies`, Cylinder and Cone (slice, fillets, caps), Tube, Disc, Torus, Oil Tank, Capsule, Polygon,
Landscape. Update `tests\test_objects_prim_mesh.py` as 2.3. Run `tests\test_objects_mesh_golden.py`,
`tests\test_objects_prim_mesh.py`, `tests\test_objects_ui.py`, `tests\test_fileio_quartz.py`.

Accept: `tests\test_objects_mesh_golden.py` (both tests) and `tests\test_objects_prim_mesh.py` end with 0 failed with
`revolve.py` present; every count of section 1 holds; every new int key ending in `segments` has a maximum.

### gen-surface: Surface generator attributes (opus)

Files: `quartz_studio\objects\gen_surface.py`, `tests\test_objects_gen_surface.py`.

Specs: plan.md section 0; attributes-gen.md sections 0, 2 (the registry names it uses), 3.1 to 3.5.

Task: Record the goldens first (attributes-gen.md 0). Then Subdivision Surface (`type` with Bilinear, label
"Subdivision Viewport", `pre_subdivision`, `boundary` with `show`, `_bilinear`, `_catmull_clark(corners=...)`),
Symmetry (Planar and Radial with `show`, radial construction and welding), Connect (no change), Remesh (target mode,
polygon count, smoothing), Thicken (`position` with `migrate` from `both_sides`, `shell`, `start_cap`, `end_cap`), all
with the registry fields landed in wave 1 (`show`, `migrate`). Defaults reproduce today's meshes. Update
`tests\test_objects_gen_surface.py` with the tests of 3.1 to 3.5 and the pins near lines 145, 152, 312 to 340 and 519.
Run it and `tests\test_objects_ui.py`, `tests\test_fileio_quartz.py`.

Accept: `tests\test_objects_gen_surface.py` ends with 0 failed; GOLDEN holds at defaults; `spec.clamp({"both_sides":
True})["position"] == 0.0`; Radial Symmetry with 4 slices on a wedge gives a closed manifold symmetric in X and Z.

### Wave 2 integration

1. Delete `PARAM_APPLIES["cube"]` from `attribute_manager.py` once `prim_mesh.py` carries the same rules in
   `spec.applies` (check the Cube's fillet rows still hide and show).
2. Shared tests: `tests\test_objects_ui.py`, `tests\test_interface_defects.py`, `tests\test_fileio_quartz.py` (round
   trips of a Thicken saved with `both_sides`, a Text with `font` and `font_style`, a Cylinder with slice and fillet,
   a hand-written old rectangle and helix), `tests\test_objects_core.py` if it pins `Param` fields,
   `tests\test_smoke.py` and `tests\test_wiring.py` for the Window menu (Display and Filter first, every item wired),
   `tests\test_context_menu.py` and `tests\test_hooks.py` if a menu count moved.
3. Confirm that the three golden comparisons were run (spline rule 1.2, generator rule 0, mesh 2.1): read each
   builder's report and rerun one probe script yourself.
4. Run every suite with the loop of section 0 until every file ends with 0 failed.
5. End to end: Display > Wireframe, Hidden Line, Shaded, back to Shaded (Lines) from the viewport header and from
   Window > Display; Filter > Horizon, HUD, Gizmo off and on; Reset Display; the state survives a new window; 200
   wheel notches into the cube face and back out, then Frame Default; create a Text, change its font to Times New
   Roman and its style to Bold in the Attribute Manager, set a Round bevel of 2 cm, turn the start cap off, type two
   lines of text; Extrude a Circle with Adaptive 5 degrees (72 rings) and Direction Auto; a Cylinder with fillet and
   slice; a Landscape spherical; a Subdivision Surface Bilinear; a Line with Close Spline and Point Thickness; save
   and reopen a `.quartz` with these objects; the Controls editor lists the Window > Display items.
6. Screenshots: the window at 1920 x 1010 and 1280 x 720; each shading mode (crops of the viewport); the viewport
   Display and Filter menus open and Window > Display open; the Attribute Manager of Text (font and style combos),
   Extrude, Cylinder and a Line; the zoomed-in face.
7. `SPEC.md` 7.1 (new kinds, `show`, `axes`, `ref`, `migrate`, link values at build time), 7 (the sampling tails and
   `line_attrs`, the revolve engine), 9.x (Display and Filter menus, unlimited zoom), an "As built" note;
   `README.md` objects and viewport features.

## 5. Wave 3: customisable palettes, remaining generators, scene links (08:25 to 10:15)

Goal: palettes the owner can rearrange, group and place; Lathe, Sweep and Loft attributes; Cloner modes including
Object mode with links; Array and Metaball attributes; Voronoi distribution, inside, hull and scale; link
resolution in the scene.

Frozen names inside this wave, beyond `interface.md` 7.2 (all in `quartz_studio\widgets\palette_edit.py`, new):
`attach(palette: QWidget, palette_id: str, strip) -> PaletteEditor`; `PaletteEditor(QObject)`;
`PaletteEditor.refresh()` re-hooks the buttons after every rebuild; `PaletteEditor.drop_target(pos) ->
tuple[str, int]` (`("insert", i)` or `("condense", i)`); `PaletteEditor.context_menu(button) -> QMenu` (button None
for the background); `GroupEditPopup(QFrame)`; `PaletteCatalog(QDialog)`. In `command_bar.py`:
`PaletteStrip.set_entries(entries)`. In `tool_palette.py`: `ToolPalette.rebuild()`, `ToolPalette.set_side(side)`. In
`object_palette.py`: `ObjectPalette.rebuild()`, the constructor keywords `orientation` and `popup_side`.

### palettes-model: Palette layouts, actions, edit state and Edit menu (opus)

Files: `quartz_studio\palettes.py`, `quartz_studio\widgets\menus_data.py`, `quartz_studio\widgets\menu_bar.py`,
`tests\test_palettes_model.py`.

Specs: plan.md sections 0, 1 (D7, D11, D16, D20) and 5 (frozen names); interface.md sections 7.2, 7.3, 7.5, 7.6
(only `editing`, `set_editing`, `editingChanged`, `menu_commands`, `menu_checks` and the Edit menu items), 7.8 (cases
2 and 3); controls.md section 2.1.2.

Task: Create `quartz_studio\palettes.py` first with every public name of 7.2 as stubs that already return the
default layouts (within 15 minutes; three builders of this wave call them), then fill them in: `actions(palette_id)`
(scene tools from `select_tools.TOOLS` and the transform and pen tools, mesh tools of `install.PALETTE_MENU`
including Trunk, create actions with icons and colours exactly as `object_palette._spec_entry` computes them, unique
labels), `default_layout` equal to today's rail (the Selection group of D11 included) and dock, `load` with every
sanitising rule and the "More" group for new actions, `save`, `reset`, `reset_all`, `position`, `set_position`,
`strip_entries(palette_id, layout, orientation)` returning `PaletteStrip` entries (`Item`, `Cmd`, `GAP`, `FLEX`, and
`DIVIDER` markers that the strips replace with their own divider widgets), the pure edit functions (never mutating
input), `editing`, `set_editing`, `editingChanged` (module-level `QObject`), `menu_commands()` (Edit "Customize
Palettes" toggling edit mode, "Reset Palettes") and `menu_checks()`. Storage on `prefs` keys `palette.tools` and
`palette.objects`. Import widget modules only inside functions. In `menus_data.EDIT_MENU` add, after "Controls...",
`item("Customize Palettes")` (a check item) and `item("Reset Palettes")` (D16). In `menu_bar.py` wire them without a
module-level import of `palettes` (D20): `_wire_scene_commands` also wires `palettes.menu_commands()` and adds
`palettes.menu_checks()` to the checks that `refresh_enabled` applies (the `SCENE_CHECKED` mechanism of wave 2); keep
every wave-1 and wave-2 change in both files. Write `tests\test_palettes_model.py` (cases 2 and 3 of 7.8, default
layouts equal to today's palettes, round trip through `prefs` with a temporary `QUARTZ_PREFS_DIR`, the Edit menu
items toggle `editing()` and reset both layouts). Run it and `tests\test_wiring.py`, `tests\test_smoke.py`,
`tests\test_display_state.py`, `tests\test_controls_widgets.py`.

Accept: `tests\test_palettes_model.py` ends with 0 failed; `default_layout("tools")` and `("objects")` describe
today's palettes exactly; inputs of the edit functions are never mutated; Edit shows Undo, Redo, separator,
Controls..., Customize Palettes, Reset Palettes and both palette items work.

### palettes-edit: Palette edit mode, drag and drop, group popup, catalog (opus)

Files: `quartz_studio\widgets\palette_edit.py`, `quartz_studio\widgets\command_bar.py`, `tests\test_palette_edit.py`.

Specs: plan.md sections 0 and 5 (frozen names); interface.md sections 7.1, 7.4 (`PaletteStrip.set_entries`), 7.6,
7.8 (cases 6, 9 and 10).

Task: In `command_bar.py` first, within 15 minutes, add `PaletteStrip.set_entries(entries)` (removes and deletes every
child widget, spacer, segment and button group, clears `buttons`, `gears`, `segments`, `button_groups`, adds the
entries with `_add` and `_sync_segments`; the constructor calls it); keep `SceneBinding` and the top bar unchanged.
Then create `quartz_studio\widgets\palette_edit.py` with the frozen names: while `palettes.editing()` an event filter
on every palette button consumes press, move, release and double click; the dashed accent border through the
property `qsEditing`; drag start after `QApplication.startDragDistance()` with a 36 x 36 pixmap and the MIME payload
of 7.6; drops on the same palette only; `drop_target` with the central 18 x 18 zone; insertion bar 2 x 28 and the
condense outline; a drop outside removes; a click on a group opens `GroupEditPopup` (reorder, Make Default, Move Out
of Group, Remove); the right-click menus of 7.6 (Remove, Ungroup, Insert Divider Before, Remove Divider, then
Customize Palette, Add Command... in edit mode, the Position submenu calling `palettes.set_position`, Reset Palette);
`PaletteCatalog` 320 x 448 with search and double-click append; Escape anywhere in the window leaves edit mode (an
application filter installed only while editing, using `controls.modal_key(ev, "cancel")`). Every operation goes
through the pure functions and `palettes.save`. Build in this order: set_entries, edit state and click blocking,
context menus, catalog, group popup, drag and drop; if drag and drop cannot be finished, the context-menu, popup and
catalog operations must still work and the drag code must not be reachable. Write `tests\test_palette_edit.py`
(cases 6, 9, 10 of 7.8 and each menu operation on a small strip). Run it and `tests\test_tool_palette.py`,
`tests\test_smoke.py`, `tests\test_press_feedback.py`.

Accept: `tests\test_palette_edit.py` ends with 0 failed; in edit mode a click never runs a command and Escape leaves
edit mode; `drop_target` gives insert and condense answers at centres, gaps and edges; the top bar and
`tests\test_press_feedback.py` are unchanged.

### palettes-strips: Rebuildable tool rail and object dock (opus)

Files: `quartz_studio\widgets\tool_palette.py`, `quartz_studio\widgets\object_palette.py`, `tests\test_palettes.py`.

Specs: plan.md sections 0, 1 (D11) and 5 (frozen names); interface.md sections 7.1, 7.3, 7.4, 7.5, 7.8 (cases 1, 4, 5
and 7).

Task: Make both palettes rebuild from a layout, as interface.md 7.4: `ToolPalette.rebuild()` and
`ObjectPalette.rebuild()` load `palettes.load(id)`, call `palettes.strip_entries`, then `set_entries` (builder
palettes-edit adds it now), and rewire: create actions through `set_command_action(label, run)`; mesh tools as today
(`_modeling[id] = (button, label, spec.interactive)`, tooltips from `install.tool_tooltip`, refreshed on
`controls.hub().profileChanged` as in wave 1); scene tools through a new `SceneBinding` whose values are `{button:
scene tool of its default, or OTHER_TOOL}` and whose command map is `{button: {label: scene tool or OTHER_TOOL}}`
for every button that holds a scene tool (`inert=(OTHER_TOOL,)`); refresh `self.buttons`, `button_groups`,
`segments`, `gears`, `_gap_items`; run `_fit()`; call `palette_edit.attach(...)` once and `refresh()` after each
rebuild. Both rebuild on `prefs.changed` for their key and on `palettes.editingChanged`. The default layout must give
exactly today's palettes (the Selection fold-out of wave 1, Pen group, modeling groups with Trunk, the dock with Line,
Null and the groups). Keep every module constant importable with today's values (`TOOL_PALETTE_ENTRIES`,
`SCENE_TOOLS`, `OTHER_TOOL`, `PEN_KEY`, `PEN_COMMANDS`, `SELECT_COMMANDS`, `modeling_entries`,
`OBJECT_PALETTE_ENTRIES`, `CREATE_COMMANDS`, `PALETTE_GROUPS`, `SHAPE_GROUP_COUNT`). Add `ToolPalette.set_side(side)`
("left" or "right": popup side and mirrored `confine_popup` shift) and make sure `ObjectPalette` works vertical with
`popup_side` "left" and "right" and horizontal with "above" and "below". Do not touch `main_window.py` (builder
palette-positions). Write `tests\test_palettes.py` with cases 1, 4, 5 and 7 of 7.8. Run it and
`tests\test_tool_palette.py`, `tests\test_wiring.py`, `tests\test_objects_ui.py`, `tests\test_trunk_tool.py`,
`tests\test_trunk_generator.py`, `tests\test_smoke.py`, `tests\test_press_feedback.py`, `tests\test_select_sets.py`.

Accept: `tests\test_palettes.py` ends with 0 failed; `tests\test_tool_palette.py`, `test_wiring.py`, `test_objects_ui.py`,
`test_trunk_tool.py`, `test_trunk_generator.py`, `test_smoke.py` end with 0 failed unchanged; condensing Move onto
Rotate through `palettes.condense` and `save` rebuilds the rail with one fold-out button that survives a new window.

### palette-positions: Palette positions in the window (opus)

Files: `quartz_studio\main_window.py`, `tests\test_palette_positions.py`.

Specs: plan.md sections 0 and 5 (frozen names); interface.md sections 7.2 (`position`, `set_position`), 7.7, 7.8
(case 8); hooks.md section 4.

Task: Add `MainWindow.apply_palette_positions()` exactly as interface.md 7.7, run at the end of `_build` and on
`prefs.changed` for `palette.tools` and `palette.objects`: tool rail first or last in `qsLeftBlock` with
`tool_palette.set_side(position)`; object dock floating bottom (today), floating top (40 px under the canvas top,
`popup_side="below"`, no HUD dodge), or a vertical 48 px card rail left or right in the order of 7.7; switching
between floating and rail replaces the `ObjectPalette` instance (`deleteLater` on the old one) and updates
`self.object_palette` and `self.regions["object_palette"]`; `place_object_dock()` does nothing for a rail;
`dock_area()` stays the canvas rectangle. Keep every hook of hooks.md 4 (left dock column, bottom splitter, pages),
the `StudioSplitter`s, the fixed Coordinates and the `controls.install` call of wave 1. Code against
`palettes.position` and the constructor keywords of `ObjectPalette` (builders palettes-model and palettes-strips
write them now). Write `tests\test_palette_positions.py` with case 8 of 7.8 (rail right, dock top, dock rail_left,
back to bottom restores `test_smoke._layout_errors` with no error; import that helper or copy it). Run it and
`tests\test_smoke.py`, `tests\test_hooks.py`, `tests\test_layout_chrome.py`, `tests\test_coordinates.py`,
`tests\test_viewport_draw.py`.

Accept: `tests\test_palette_positions.py` ends with 0 failed; the default layout is pixel-identical to wave 2 (the
listed suites end with 0 failed unchanged); each position works at 1920 x 1010 and 1280 x 720.

### gen-sweep: Lathe, Sweep and Loft attributes (opus)

Files: `quartz_studio\objects\gen_spline.py`, `tests\test_objects_gen_spline.py`.

Specs: plan.md sections 0 and 1 (D17); attributes-gen.md sections 0, 2.2 (`curve`, `curve_value`), 2.3 (`migrate`),
3.7 (step 5, `cap_type`), 3.8, 3.9, 3.10.

Task: Record the goldens of Lathe, Sweep and Loft at defaults and with `caps` True and False first (attributes-gen.md
0); the Text and Extrude goldens of wave 2 are already in the test file and must keep passing. Lathe (3.8): angle
range, "Scaling" label, `flip_normals`, `start_cap`, `end_cap`, `cap_type`. Sweep (3.9): the params in order with
`caps` removed and the `migrate`, `parallel_movement`, `constant_cross_section`, the rail with `use_rail_direction`
and `use_rail_scale`, `flip_normals`, `scale_curve` through `registry.curve_value`, caps and `cap_type`. Loft (3.10):
labels, `per_segment`, `linear_interpolation`, `flip_normals`, caps with the same `migrate`, `cap_type`. Use the
`_cap(..., cap_type)` argument added in wave 2. Do not change Text, Text Spline or Extrude. Defaults reproduce today
bit for bit. Tests of 3.8 to 3.10 in `tests\test_objects_gen_spline.py` (update the `caps` pins near lines 134, 137,
387 and 500). Run it and `tests\test_text_spline_attrs.py`, `tests\test_objects_ui.py`, `tests\test_fileio_quartz.py`,
`tests\test_attribute_manager.py`.

Accept: `tests\test_objects_gen_spline.py` ends with 0 failed; every GOLDEN holds; `spec.clamp({"caps": False})` gives
both caps False for Sweep and Loft; the scale curve case halves the middle ring.

### gen-clone: Cloner, Array and Metaball attributes (opus)

Files: `quartz_studio\objects\gen_clone.py`, `tests\test_objects_gen_clone.py`.

Specs: plan.md sections 0 and 1 (D15); attributes-gen.md sections 0, 2.1 (`show`, `axes`), 2.4 (link values), 3.12
(3.12.1, 3.12.2), 3.13, 3.14, 3.15.

Task: Record the goldens first (attributes-gen.md 0). Cloner: the params of 3.12 in order (new modes Object and
Honeycomb Array appended to the choices, `reset_coordinates`, the Object mode link and distribution params, Linear
offset, mode, amount, step rotation, Radial offset, Grid mode, form and fill, Honeycomb params, the Transform group,
`axes=("H", "P", "B")` on rotations, the relabels), every construction rule of 3.12.2, Object mode reading
`p["object_link"]` as a `BuildInput` or anything else as None (builder scene-links resolves links in the scene now;
your tests build with a `BuildInput` made by hand). Array: the label fix. Metaball: `exponential_falloff`. Fracture:
nothing. Keep the old Cloner keys and their `PARAM_APPLIES` rules valid (3.12.1). Defaults reproduce today. Tests of
3.12 to 3.15 in `tests\test_objects_gen_clone.py` (update the choices pin near line 169). Run it and
`tests\test_objects_ui.py`, `tests\test_fileio_quartz.py`, `tests\test_interface_defects.py`.

Accept: `tests\test_objects_gen_clone.py` ends with 0 failed; GOLDEN holds for every old mode; Object mode with a cube
target gives 8, 12, 6 and 20 clones for Vertex, Edge, Polygon Center and Surface; no link gives an empty mesh without
error.

### gen-boole: Boole and Voronoi Fracture attributes (opus)

Files: `quartz_studio\objects\gen_boole.py`, `tests\test_objects_gen_boole.py`.

Specs: plan.md section 0; attributes-gen.md sections 0, 2.1 (`show`), 3.16, 3.17.

Task: Record the goldens first (attributes-gen.md 0) on the existing torus and sphere probes. Boole: no change.
Voronoi Fracture: the new params after `seed` in the order of 3.17 (`distribution`, `std_deviation` with `show`,
`inside_only`, `hull_only`, `scale_cells`), the keyword-only arguments of `fracture_mesh` so the positional calls in
the tests keep working, Scale Cells by division and multiplication, Normal distribution clipped to the bounds, Inside
by ray parity with the half-open rule and at most 32 batches, Hull Only without `_seal` and without the inner faces.
Defaults reproduce today bit for bit. Tests of 3.17 in `tests\test_objects_gen_boole.py` (update the defaults pin near
line 192). Run it and `tests\test_objects_ui.py`, `tests\test_fileio_quartz.py`.

Accept: `tests\test_objects_gen_boole.py` ends with 0 failed; GOLDEN holds; Inside on a torus never puts a seed in
the hole; Hull Only keeps the input area within 1e-6 relative; every non-Hull-Only fragment is a closed manifold.

### scene-links: Link resolution in the scene (opus)

Files: `quartz_studio\scene.py`, `tests\test_scene_links.py`.

Specs: plan.md section 0; attributes-gen.md sections 2.4 and 6 (steps 1 and 2); hooks.md section 1 (keep the extras).

Task: Implement attributes-gen.md 6 steps 1 and 2 in `scene.py`: in `Scene._build`, for each key of
`registry.link_keys(spec)`, resolve the stored name to the first object of `self.objects` with that name, skipping
the generator itself, its ancestors and its descendants, and pass `self._make_input(self._flatten(target, kids))`
transformed into the generator's local space (`inverse(generator.world_matrix()) @ target.parent_matrix()`), else
`None`; in `evaluate` and `_signature` a generator's signature also holds `(id, kind, world matrix bytes, _mesh_sig)`
of each linked object, so moving or editing the target rebuilds it; generators with links are built after the others
in the same pass (a second loop), a link to an object that itself has links uses that object's previous mesh;
`Scene.rename_object` renames every `link` param that holds the old name in the same undo step. Change nothing else
(keep `extras`, `set_object_extra`, the Trunk thickness channel and every other API). Write
`tests\test_scene_links.py` with a test spec registered by the test that has one `link` param and returns the linked
mesh (so it does not depend on builder gen-clone): resolution, self and family refused, local-space transform, moving
the target rebuilds, editing the target rebuilds, rename follows in one undo step, a missing name gives None, a
`.quartz` round trip keeps the name. Run it and `tests\test_objects_core.py`, `tests\test_fileio_quartz.py`,
`tests\test_trunk_foundation.py`, `tests\test_trunk_generator.py`, `tests\test_hooks.py`, `tests\test_objects_ui.py`.

Accept: `tests\test_scene_links.py` ends with 0 failed; the listed suites end with 0 failed unchanged; a scene without
link params evaluates exactly as before.

### Wave 3 integration

1. Check the seams the builders could not: `palette_edit.attach` is called by both palettes after every rebuild; the
   Position submenu moves the palettes through `apply_palette_positions`; the Edit menu items and the palette
   context menu share one edit state; the Cloner's Object row offers the scene objects (`link` row of wave 2) and the
   scene resolves it.
2. Shared tests: `tests\test_tool_palette.py`, `tests\test_smoke.py` and `tests\test_wiring.py` (Edit menu list of
   D16, every visible control wired, the palette context menu items), `tests\test_interface_defects.py` (Cloner
   visibility near lines 315 and 359), `tests\test_objects_ui.py`, `tests\test_fileio_quartz.py` (round trips of a
   Sweep with a scale curve, a Sweep saved with `caps`, a Cloner in Object mode with a link, a Voronoi with Hull
   Only), `tests\test_objects_core.py` if needed.
3. Run every suite with the loop of section 0 until every file ends with 0 failed.
4. End to end: Edit > Customize Palettes; condense Move onto Rotate by the drop-target logic or the context menu;
   insert a divider; add a command from the catalog; leave edit mode with Escape; open a new window and see the same
   rail; rail right, dock top, dock rail left, back to defaults with Edit > Reset Palettes; a Cloner in Object mode
   linked to a Sphere (Vertex, Polygon Center, Surface), move and rename the Sphere; a Sweep with a scale curve edited
   in the Attribute Manager; a Lathe spiral of 720 degrees; a Loft with Linear Interpolation; a Voronoi with Hull Only
   and Scale Cells; save and reopen.
5. Screenshots: the window at 1920 x 1010 and 1280 x 720 in the default layout; edit mode with the dashed border;
   the group popup; the catalog; rail right and dock rail left; the Attribute Manager of the Cloner in Object mode and
   of the Sweep with its curve row.
6. `SPEC.md`: section 12 "Interface customisation" completed (palettes, positions, edit mode), 7 (generator
   attributes and link resolution, "As built"); `README.md` palettes and generators.
7. Final full run at the end of the fix pass, before 10:15, with every file at 0 failed; report the deferred items of
   section 7 and any step that was dropped under section 6.

## 6. If a wave overruns

- A builder that has not reported when its wave's integration starts is stopped; the integration agent restores its
  files from the wave backup, unless the builder's own tests already pass on what it wrote.
- Wave 2 starts no later than 06:50 and wave 3 no later than 08:40. When a wave starts late, the builders of that
  wave drop work in this order (last item first to go): wave 2: gen-surface, then mesh-prims together with
  mesh-revolve, then spline-shapes; never vp-display-zoom, display-menus, gen-text, am-kinds or line-attrs. Wave 3:
  gen-boole, then gen-sweep, then palettes drag and drop (context menu, popup and catalog stay), then the dock rail
  positions of palette-positions; gen-clone's Object mode and scene-links go together or not at all (an Object mode
  that never receives its target would be a control that does nothing).
- The wave-3 integration starts at 09:25 at the latest; the tree must be green by 10:20 whatever is dropped.

## 7. Deferred (not built tonight)

- The whole pixel sweep of `metrics.md` (sections 2 to 8: fonts in px, the token changes `SEGMENT_H`, `CHIP_H`,
  `HUD_H`, `COMMAND_BUTTON`, `FIELD_H`, the QSS literals, the local sizes of every widget file, icons, viewport
  overlay sizes), its guard `tests\test_metrics.py` (section 11) and its integration (12.4). It must run as its own
  fleet of five builders after the feature fleets (`metrics.md` 12.1); tonight only the helpers of D4 land and every
  builder writes in the norm.
- `interface.md` section 8 and `tests\test_px_norm.py` (superseded by `metrics.md`, D18).
- Coordinates 120 or 128 and the `FIELD_H` reconciliation (D2), for the owner and the sweep.
- `tests\conftest.py` of `interface.md` 1.6 (no pytest in the venv; D7 replaces it).
- The brush radius keys `[` and `]` as controls actions, and Classic keys for the new selection tools (D9,
  `controls.md` 7.2).
- The owner's open points: `CLASSIC_NAME` "Cinema 4D" (`controls.md` 7.1), Standard's orbit pivot (7.3), Text letter
  case if "Caps" meant upper and lower case (`attributes-gen.md` 8), the wider reading of the px norm (`metrics.md`
  1.2).
- The "later" items the contracts already exclude: a real spline type with tangents and intermediate points on Lines
  (`attributes-spline.md` 5.3), Separate Letters and per-letter kerning, bevels on Lathe, Sweep and Loft caps, Cloner
  Volume and Axis distributions, rectangle and lasso selection.
