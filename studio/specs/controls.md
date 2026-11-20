# Controls and shortcuts with profiles

Contract written on 20/11/2026 for the night run. Builders implement from this file without asking. It covers:
every keyboard and mouse input the app understands today (section 1), the model that replaces the scattered
handlers (section 2), the profiles and their storage (section 3), the Controls editor (section 4), the code
changes and tests (section 5), and the split into parallel builders (section 6).

Line numbers point at the files as they were read on 20/11/2026. Other fleets are editing some of these files
tonight, so function and constant names are the reference; line numbers are only a hint.

## 0. Decisions in one place

1. A new package `quartz_studio/controls/` owns everything: action registry, profiles, storage, dispatch,
   editor. No other file keeps a table of keys or mouse buttons after this change.
2. Two built-in read-only profiles: `standard` (name "Standard", the shipped default for a new user) and
   `classic` (name "Classic"). Classic is the owner's "Cinema 4D" profile: it is today's behaviour, binding for
   binding. It is not called "Cinema 4D" in the interface because SPEC.md rule 0.3 forbids naming that program
   in the interface; if the owner wants that literal name, it is the single constant `CLASSIC_NAME` in
   `controls/profiles.py` (see 7.1).
3. This machine keeps Classic: the first run writes `selected = "classic"` when a previous Quartz Studio
   install is detected (the registry key `HKCU\Software\Quartz\Quartz Studio` exists on this machine, checked
   20/11/2026), `"standard"` otherwise. The integration step runs that first-run once on this machine and
   checks the result (3.6).
4. Code that never calls `controls.load()` (every test, `tools/snapshot.py`) runs Classic with no disk access,
   so today's suites keep pinning today's behaviour unchanged. That is the "Classic reproduces today, test by
   test" guarantee; new tests select Standard explicitly.
5. Dispatch wraps, it does not replace: Qt's shortcut machinery keeps handling window-wide keys (so the canvas
   and the coordinate fields keep winning over window shortcuts exactly as today), but the `QShortcut` objects
   are created from the active profile; one application event filter handles chords and held keys; the canvas
   and the Object Manager keep their `keyPressEvent`, which now look the key up in the profile.
6. Three key scopes: `global` (window), `viewport` (canvas or viewport focused), `objects` (Object Manager
   tree focused). Text fields never receive bindings. The narrower scope wins.
7. Mouse navigation and selection are data: a list of gestures (button, modifiers, optional held key, single
   or double click) mapped to an operation or an action. Roll is not offered (the camera has no roll).
8. One file holds the user's choices: `%APPDATA%\Quartz\controls.json` (selected profile id plus the user
   profiles). Export and import use one profile document per `.json` file.
9. Three defects of today's key filter are fixed in every profile (1.9): a single K press runs Line Cut, a
   single U press runs Untriangulate, and the chords `M~#`, `M~,` and `U~C` can never be typed.
10. Edit > Controls... opens the editor (Classic `Shift+F12`, Standard `Ctrl+,`); menus, context menus, the
    viewport View menu and the rail tooltips show the binding of the active profile and change live.

## 1. Inventory of today's inputs (this is the Classic profile)

### 1.1 Window-wide keys (`QShortcut`, context `WindowShortcut`)

| Key | Command | Installed in |
|---|---|---|
| `Ctrl+Z` | `get_scene().undo()` | `main_window.MainWindow._install_undo_shortcuts` (line 130) |
| `Ctrl+Y` | `get_scene().redo()` | same |
| `C` | `menu_bar.make_editable()` (only when `can_make_editable()`) | same |
| `Ctrl+N` | `project.new_project` | `MainWindow.FILE_SHORTCUTS` / `_install_file_shortcuts` (line 143), list `window.file_shortcuts` |
| `Ctrl+O` | `project.open_project` | same |
| `Ctrl+Shift+O` | `project.merge_project` | same |
| `Ctrl+S` | `project.save_project` | same |
| `Ctrl+Shift+S` | `project.save_project_as` | same |
| `Ctrl+Alt+S` | `project.save_incremental` | same |
| `Alt+F4` | window close (Windows itself; `closeEvent` asks to save) | not installed by the app; shown on File > Exit |
| any key given to `menu_bar.add_menu` / `add_entries` | the extension item | `menu_bar.extension_shortcuts` (specs/hooks.md section 5, being built tonight) |

Menu items carry their shortcut only as text (`StudioMenu.add_item` writes `"text\tshortcut"` and the property
`qs_shortcut`); no `QAction` has `setShortcut`. Menus are pruned to wired items (`MenuBar.prune_unwired`), so
the only shortcut texts visible today are the ones in the tables of this section.

### 1.2 Chords (application event filter `modeling.install._ShortcutFilter`, line 251)

Installed by `modeling.install.install(window)` on the `QApplication` (`window.modeling_shortcuts`). A chord is
`X~Y`: press X, then Y within `SHORTCUT_WINDOW` = 1.5 s. Ignored when Ctrl or Alt is held, on auto-repeat, when
a `QLineEdit` or `QAbstractSpinBox` has focus, and when the focus is outside the main window. Every chord calls
`modeling.install.activate_tool(id)` (which switches to Polygons mode, or the tool's first mode, when the
current mode is not supported), except `M~E`, which calls `_select_pen()` (`scene.set_tool("pen")`).

| Chord | Tool id | Name |
|---|---|---|
| `M~E` | `pen` (scene tool) | Polygon Pen (`PEN_CHORD`) |
| `M~S` | `bevel` | Bevel |
| `M~T` | `extrude` | Extrude |
| `M~W` | `inset` | Inset |
| `M~X` | `matrix_extrude` | Matrix Extrude |
| `M~Y` | `smooth_shift` | Smooth Shift |
| `M~R` | `trunk` | Trunk |
| `M~B` | `bridge` | Bridge |
| `M~P` | `stitch_and_sew` | Stitch and Sew |
| `M~Q` | `weld` | Weld |
| `M~D` | `close_polygon_hole` | Close Polygon Hole |
| `M~F` | `edge_cut` | Edge Cut |
| `M~H` | `mirror` | Mirror |
| `M~M` | `connect_points_edges` | Connect Points/Edges |
| `M~N` | `dissolve` | Dissolve |
| `M~O` | `slide` | Slide |
| `M~G` | `iron` | Iron |
| `M~Z` | `normal_move` | Normal Move |
| `M~#` | `normal_scale` | Normal Scale (unreachable today, 1.9) |
| `M~,` | `normal_rotate` | Normal Rotate (unreachable today, 1.9) |
| `K~K` | `line_cut` | Line Cut |
| `K~L` | `loop_path_cut` | Loop/Path Cut |
| `K~J` | `plane_cut` | Plane Cut |
| `U~S` | `subdivide` | Subdivide |
| `U~U` | `untriangulate` | Untriangulate |
| `U~R` | `reverse_normals` | Reverse Normals |
| `U~A` | `align_normals` | Align Normals |
| `U~V` | `spin_edge` | Spin Edge |
| `U~C` | `collapse` | Collapse (shadowed by `C` today, 1.9) |
| `U~Z` | `melt` | Melt |
| `U~O` | `optimize` | Optimize |
| `U~D` | `disconnect` | Disconnect |
| `U~P` | `split` | Split |
| `U~I` | `invert_selection` | Invert |
| `U~W` | `select_connected` | Select Connected |
| `U~G` | `grow_selection` | Grow Selection |
| `U~K` | `shrink_selection` | Shrink Selection |
| `U~L` | `loop_selection` | Loop Selection |
| `U~B` | `ring_selection` | Ring Selection |
| `U~Q` | `outline_selection` | Outline Selection |
| `U~F` | `fill_selection` | Fill Selection |
| `U~M` | `path_selection` | Path Selection |
| `U~X` | `convert_selection` | Convert Selection (menu label "Convert Selection Mode...") |

The chord strings come from `ToolSpec.shortcut` in the `modeling/ops_*.py` modules (registry
`modeling/registry.py`). The same filter also holds one single key from the registry: `Delete` -> tool
`delete`, run only when the scene mode is not `model` and the focus is the canvas, the `Viewport` widget or
nothing (`_ShortcutFilter._press_key`, line 301).

### 1.3 Viewport canvas keys (`widgets/viewport.py`, `ViewportCanvas.keyPressEvent`, line 2832)

Work only while the canvas has the focus. The canvas takes the focus on show, on mouse enter and on wheel
(`claim_focus`, line 2874) unless a text input has the focus or a popup is open. `ViewportCanvas.event`
(line 2821) accepts `ShortcutOverride` for every key below, so these keys win over window shortcuts when the
canvas has the focus.

| Key | Command | Source |
|---|---|---|
| `E` | `scene.set_tool("move")` | `TOOL_KEYS` (line 517); not with Ctrl or Alt |
| `R` | `scene.set_tool("rotate")` | same |
| `T` | `scene.set_tool("scale")` | same |
| `H` | `frame_all()` (View > Frame Geometry) | `_view_key_action` (line 2805), no modifier |
| `S` | `frame_selection()` (View > Frame Selected Elements) | same |
| `O` | `frame_active()` (View > Frame Selected Objects) | same |
| `Shift+H` | `reset_camera()` (View > Frame Default) | same |
| `Ctrl+Shift+Z` | `undo_view()` (View > Undo View), repeats while held | same |
| `Ctrl+Shift+Y` | `redo_view()` (View > Redo View), repeats while held | same |
| `F1` | `set_view("Perspective")` | `VIEW_KEYS` (line 281) |
| `F2` | `set_view("Top")` | same |
| `F3` | `set_view("Right")` | same |
| `F4` | `set_view("Front")` | same |
| `1` held | left drag pans | `NAV_KEYS` (line 524), tracked by `_HeldNavKeys` (line 492, application filter) even without focus |
| `2` held | left drag dollies (internal mode name `"zoom"`) | same |
| `3` held | left drag orbits | same; with several held, 3 beats 2 beats 1 |
| `Escape` | during a drag: `cancel_drag()` | `keyPressEvent` |
| `Control` pressed | during a Move drag in a component mode: extrude the selection, then keep moving | `_ctrl_during_drag` |
| `Escape`, `Return`, `Enter` | while a pen stroke is open: `scene.pen_finish()` | `keyPressEvent` |
| `Delete` | tool `delete` (1.2) | `_ShortcutFilter` |

Keypad keys count as the plain key (`KeypadModifier` is removed in `_view_key_action`). Auto-repeat runs only
the two view history keys.

### 1.4 Object Manager keys (`widgets/object_manager.py`, `keyPressEvent`, line 646)

| Key | Command |
|---|---|
| `F2` | rename the active object (`rename()`), when an object is selected |
| `Delete`, `Backspace` | `delete_active()`, when no name editor is open |

### 1.5 Keys inside fields (stay widget-local, not in profiles)

| Widget | Key | Behaviour |
|---|---|---|
| `coordinates.CoordField` | `Escape` | revert and drop focus |
| same | `Return`, `Enter` | commit and select all |
| same | `Ctrl+Z`, `Ctrl+Y` | when the text is not modified the field refuses the `ShortcutOverride`, so the window shortcut undoes the scene (`_is_scene_undo_key`, line 209) |
| every other `QLineEdit`, spin box, editable combo | all keys | normal Qt text editing; window shortcuts with printable keys do not fire while typing |
| `modeling.panel.ScrubSpin` / `ScrubIntSpin` (also the Attribute Manager spins) | wheel | changes the value only with focus |
| same | left drag on the arrows | one step per `SCRUB_PX` = 4 px of (dx - dy); a click without drag steps once |

### 1.6 Viewport mouse (`ViewportCanvas.mousePressEvent`, line 2663, and the move, release, double-click and wheel handlers after it)

Order of the checks in `mousePressEvent`, which is also the priority:

| Gesture | Result |
|---|---|
| any button but left while a gizmo or move drag runs | `cancel_drag()` (restores, leaves no undo step) |
| any button while a navigation runs | ignored |
| any button but left while a pen press is pending | drops the pen press |
| `Alt` + left drag (any other modifiers) | orbit |
| `Alt` + middle drag | pan |
| `Alt` + right drag | dolly (`"zoom"`) |
| left drag with `1`, `2` or `3` held | pan, dolly, orbit |
| middle drag without Alt (Shift and Ctrl ignored) | orbit |
| left, pen tool (`pen` or `line_pen`) in a component mode, no Shift or Ctrl | pen press: a click places or links a point, a drag of more than 3 px moves the picked component |
| left otherwise | selection press (`_press_select`, line 2526), below |
| right, pen mode, pen stroke open | `pen_finish()` |
| right, no held key, not pen mode | context press: release within 4 px (`CONTEXT_DRAG_PX`, Euclidean) opens the context menu (`open_context_menu`), a larger move cancels it |
| right, pen mode without an open stroke, or with a held key | nothing |
| middle double-click without Alt | `end_navigation()` then `reset_camera()` (Frame Default) |
| other double-clicks | handled as a second press |
| wheel (vertical `angleDelta / 120` notches) | `zoom_at(pos, notches)`: scales the view by `WHEEL_STEP ** notches` (0.88 per notch, forward zooms in) about the point under the cursor (`cursor_point`: mesh hit, else the point at the camera distance); consecutive notches within 0.6 s are one view-undo step; ignored during a navigation |

Selection press (`_press_select`):

| Gesture | Model mode | Component modes |
|---|---|---|
| left on a gizmo handle (tool Move, Rotate or Scale), without Ctrl | starts the gizmo drag (Move: axis or plane drag; Rotate: ring; Scale: handle) | same |
| left on nothing, no Shift or Ctrl | clears the selection | clears the selection |
| left on an object or component | object becomes active and selected | selects only it (if it was already selected: decided on release, so a drag moves the whole selection) |
| `Shift` + left | as left | adds |
| `Ctrl` + left | deselects the object if it is the active one | removes |
| `Ctrl` + `Shift` + left | as Ctrl | as Ctrl |
| left drag after a selecting press with the Move tool | moves the selection (free drag) after 3 px (`DRAG_THRESHOLD`, Manhattan) |  |

During a drag: `Shift` snaps Rotate to `ROTATE_STEP` 5 degrees and Scale to `SCALE_STEP` 0.1; `Ctrl` pressed
during a Move drag in a component mode extrudes once (`ctrl_seen`; not when Ctrl was already held at the
press); `Escape` or any other mouse button cancels.

Navigation details (`begin_navigation`, `navigate`, `_scale_view`, lines 2068 to 2132):

- Orbit pivot: `nav_pivot_point(pos)` by the Cameras > Navigation choice (`canvas.nav_pivot`, default
  `"Cursor"`): Cursor = point under the press (`cursor_point`), Center = the camera target, Object = the
  selection centre (else the active object's position, else the target), Camera = the camera position (not in
  parallel views). The pivot is marked while navigating.
- Orbit: `OrbitCamera.orbit` turns heading by `-dx * ORBIT_SPEED` and pitch by `dy * ORBIT_SPEED`
  (`ORBIT_SPEED` 0.3 degrees per px), pitch clamped to `PITCH_LIMIT` 89 degrees (turntable). Orbiting an axis
  view (Left, Top, ...) turns it into Parallel or Perspective.
- Pan: keeps the grabbed point (the point under the press) under the cursor.
- Dolly drag: factor `exp(-(dx - dy) * DOLLY_SPEED)` (`DOLLY_SPEED` 0.005), about the pivot; with the Camera
  pivot it walks along the view.
- Limits today: `MIN_DISTANCE` 2, `MAX_DISTANCE` 1e6, `MIN_APPROACH` 5, `NAV_MIN_DEPTH` 100. The owner asked
  tonight to remove the zoom limit; that belongs to the viewport contract, not to this one. Profiles hold no
  limits.
- Each finished navigation that changed the view is one view-undo step (`VIEW_HISTORY` 128).

Navigation icons (`ViewportMenuBar.bind_navigation`, `_NavIconDrag`, line 2908): left drag on the pan, zoom or
orbit icon at the top right navigates with that mode about the pivot of `nav_pivot_point(None)`; the icon
stays down while dragging; a click without move does nothing.

### 1.7 Modeling tools in the viewport (`modeling/interaction.py`, `ViewportToolFilter`, line 257)

Active while an interactive modeling tool is the scene tool. It takes only a plain left press: it yields when
Alt is held or any `1`/`2`/`3` key is held (`_blocked`), and passes Shift or Ctrl presses on to the canvas
selection. A drag starts after 3 px (`DRAG_THRESHOLD`, Manhattan) and sets the tool's drag parameter
(`drag_amount`: 0.5 percent or 0.5 degrees per px, counts per 18 px); a click without drag is replayed to the
canvas as a selection click; right press or `Escape` during the press aborts (`_abort`). On a parametric
object the left press only shows "Make it editable" in the status bar.

### 1.8 Other mouse behaviour

| Where | Gesture | Result |
|---|---|---|
| Fold-out buttons (`common.IconButton`, rail, dock, top bar) | left click | runs the shown command |
| same | left press held `HOLD_MS` = 380 ms | opens the fold-out |
| same | left press in the bottom-right third (the group triangle) | opens the fold-out at once |
| Object dock and Create menu (`menu_bar.create_object`) | `Shift` + click | the new object becomes a child of the active object |
| same, generator with children input | `Alt` + click | the new generator adopts the active object |
| Rail scroll arrows | press | scrolls 36 px, auto-repeat after 250 ms every 45 ms |
| Object Manager | left click | selects; on the status column toggles Enabled |
| same | double click on the name | rename editor |
| same | left drag past `QApplication.startDragDistance()` | drag to reparent (above, onto, below bands of a quarter row) |
| same | right click | object menu on a row, Create menu on empty space |

### 1.9 Defects of today's filter (fixed in every profile)

Probed on 20/11/2026 with the real window offscreen (script `C:\Users\User\AppData\Local\Temp\qz\night\controls\probe4.py`):

1. A key the focused widget ignores propagates to its parents, and the application filter sees every
   delivery (`QWindow`, the canvas, then the `Viewport`). `_ShortcutFilter.eventFilter` does not check the
   receiver, so the second delivery completes a chord with the first: one K press runs Line Cut (`K~K`), one
   U press runs Untriangulate (`U~U`), and `K~L`, `K~J` and every `U~` chord but `U~U` cannot be typed. `M`
   chords work only because the filter consumes the first M.
2. `M~#` and `M~,`: the second key is refused because its text is not a letter (`text.isalpha()`).
3. `U~C`: the `C` window shortcut (Make Editable) fires before the filter sees the key.

The new dispatcher handles each physical key press once (5.3) and lets a chord's second key win over window
shortcuts. Tests pin the fixes (5.6).

## 2. The model

### 2.1 Actions

An action is one thing the user can trigger. Module `quartz_studio/controls/actions.py`:

```python
@dataclass
class Action:
    id: str
    label: str
    category: str
    run: Callable[[], object]
    scope: str = "global"
    available: Callable[[], bool] | None = None
    repeat: bool = False
    default_keys: tuple[str, ...] = ()
```

- `id`: stable, lowercase, dot separated, `[a-z0-9_.]` only. Ids never change once shipped.
- `label`: the text shown in the editor (the menu label without "...", or the tool name).
- `category`: one of the editor categories (4.3).
- `scope`: `"global"`, `"viewport"` or `"objects"` (2.2).
- `available`: when it returns False the key is not consumed (it passes on, as today for Delete in Model mode).
- `repeat`: the action also runs on key auto-repeat.
- `default_keys`: keys declared by the action's source for every profile that has no entry for it (used by
  extension menu items, 2.1.3). Tool shortcuts from `ToolSpec.shortcut` are not defaults: they belong to
  Classic only (3.2).

#### 2.1.1 Core actions (static table `CORE` in `actions.py`)

`run` resolves its target at call time through `controls.window()` (the window passed to `install`), so the
table has no import cycles. `canvas` below is `window.viewport.canvas`, `tree` is `window.object_manager.tree`.

| Id | Label | Category | Scope | Runs |
|---|---|---|---|---|
| `file.new` | New Project | File | global | `project.new_project` |
| `file.open` | Open Project | File | global | `project.open_project` |
| `file.merge` | Merge Project | File | global | `project.merge_project` |
| `file.save` | Save Project | File | global | `project.save_project` |
| `file.save_as` | Save Project As | File | global | `project.save_project_as` |
| `file.save_incremental` | Save Incremental | File | global | `project.save_incremental` |
| `file.import` | Import | File | global | `project.import_files` |
| `file.export_selection` | Export Selection | File | global | `project.export_selection` |
| `file.export.<format id>` | the exporter label, for example "FBX" | File | global | `project.export_as(id)`, one per `fileio.exporters()` |
| `file.clear_recent` | Clear Recent File List | File | global | `project.clear_recent` |
| `file.exit` | Exit | File | global | `project.exit_app` |
| `edit.undo` | Undo | Edit | global | `get_scene().undo()` |
| `edit.redo` | Redo | Edit | global | `get_scene().redo()` |
| `edit.delete` | Delete | Edit | viewport | Model mode: `context_menu.delete_objects(scene, scene.selected_objects())`; component modes: `activate_tool("delete")`; available when something is selected |
| `app.controls` | Controls | Edit | global | `controls.editor.open_editor(window)` |
| `mode.points`, `mode.edges`, `mode.polygons`, `mode.model` | Points, Edges, Polygons, Model | Modes | global | `scene.set_mode(...)` |
| `tool.select` | Selection | Tools | viewport | `scene.set_tool("select")` |
| `tool.move` | Move | Tools | viewport | `scene.set_tool("move")` |
| `tool.rotate` | Rotate | Tools | viewport | `scene.set_tool("rotate")` |
| `tool.scale` | Scale | Tools | viewport | `scene.set_tool("scale")` |
| `tool.pen` | Polygon Pen | Tools | global | `scene.set_tool("pen")` (`menu_bar.polygon_pen`) |
| `tool.line_pen` | Pen | Tools | global | `scene.set_tool("line_pen")` |
| `object.make_editable` | Make Editable | Objects | global | `menu_bar.make_editable`; available when `can_make_editable()` |
| `object.rename` | Rename | Objects | objects | `tree.rename()`; available when an object is selected |
| `object.delete` | Delete Object | Objects | objects | `tree.delete_active()`; available when the tree has no open editor |
| `view.undo` | Undo View | View | viewport | `canvas.undo_view`, `repeat=True` |
| `view.redo` | Redo View | View | viewport | `canvas.redo_view`, `repeat=True` |
| `view.frame_default` | Frame Default | View | viewport | `canvas.reset_camera` |
| `view.frame_all` | Frame Geometry | View | viewport | `canvas.frame_all` |
| `view.frame_selection` | Frame Selected Elements | View | viewport | `canvas.frame_selection` |
| `view.frame_objects` | Frame Selected Objects | View | viewport | `canvas.frame_active` |
| `camera.<preset>` | the preset name | Cameras | viewport | `canvas.set_view(name)` for each key of `viewport.VIEW_PRESETS`: `perspective`, `parallel`, `left`, `right`, `front`, `back`, `top`, `bottom`, `isometric`, `dimetric` |
| `camera.pivot.<name>` | Navigation: Cursor, Center, Object, Camera | Cameras | viewport | `canvas.set_nav_pivot(name)` |

Labels keep the reference program's English names already used in the menus. Tool labels follow the HUD
names (`viewport.TOOL_NAMES`): if the palette contract renames "Selection" to "Brush Selection" tonight, the
label follows `TOOL_NAMES["select"]` and the id stays `tool.select`.

#### 2.1.2 Actions from the registries

`actions.collect()` builds the registry in this order; the first action with an id wins, later duplicates are
skipped:

1. `CORE`.
2. Every modeling tool: `tool.<spec.id>` for each `modeling.registry.tool_ids()`, label `spec.name`, category
   `spec.menu` ("Mesh" or "Select"), scope `global`, run `partial(activate_tool, spec.id)`. Available always,
   except `tool.delete`: only outside Model mode (today's rule). New tools (the Trunk fleet, the palette
   contract's Loop, Ring, Pattern, Fill Area and Phong Angle selections) get their action by registering a
   `ToolSpec`; nothing else is needed.
3. Every parametric object: `create.<spec.id>` for each `objects.all_specs()`, label `spec.label`, category
   "Create", run `partial(menu_bar.create_object, spec.id)`; plus `create.line` (`menu_bar.create_line`) and
   `create.empty_polygon` (`menu_bar.create_empty_polygon`).
4. Every wired menu item: for each `(path, handler)` in `menu_bar.SCENE_COMMANDS` the id is found by
   - `handler` is a `functools.partial` of `activate_tool` -> `tool.<args[0]>`;
   - `handler` is a `functools.partial` of `create_object` -> `create.<args[0]>`;
   - `path` is in the table `MENU_IDS` of `actions.py` (File, Edit and Mesh > Make Editable, Mesh > Polygon
     Pen, Edit > Controls..., Create > Spline > Line, Create > Mesh > Empty Polygon) -> that id;
   - otherwise `menu.` + the path slug: each part lowercased, every run of characters outside `[a-z0-9]`
     replaced by `_`, stripped of `_`, parts joined by `.` (`("Extensions", "Script Manager...")` ->
     `menu.extensions.script_manager`).
   The action records the path, so the menu can show its binding (2.6).
5. Extension items (specs/hooks.md section 5): `MenuBar.add_menu` and `add_entries` call
   `controls.register_action(id, label, category, run, keys=(shortcut,) if shortcut else ())` with the
   `menu.` slug id of the item's path and category = the top-level menu title; the shortcut becomes
   `default_keys`. They stop creating their own `QShortcut`: `controls` creates it, and
   `menu_bar.extension_shortcuts` stays as the list of the `QShortcut`s of those actions (the hooks test reads
   it). `register_action` after `install` rebuilds the shortcuts (`controls.refresh()`).

Palette entries need nothing extra: rail buttons run `tool.*` or scene tools, dock buttons run `create.*`.
The palette contract should store action ids if it saves palette layouts.

`controls.actions()` returns the registry as an ordered `dict[str, Action]`; `controls.run(id)` runs one if it
exists and is available and returns True when it ran.

### 2.2 Key bindings

A binding is a string:

| Form | Example | Meaning |
|---|---|---|
| single key | `E`, `Delete`, `F2`, `Home`, `Backspace` | no modifier |
| combination | `Ctrl+Shift+Z`, `Alt+C`, `Ctrl+,` | modifiers `Ctrl`, `Shift`, `Alt`, `Meta` before the key |
| keypad | `Num+1`, `Ctrl+Num+5` | Qt `KeypadModifier` |
| chord | `M~E`, `U~L`, `M~#` | two plain keys (no Ctrl, Alt or Meta), the second within `chord_ms` |

- Parsing and matching go through `QKeySequence(text).toString(QKeySequence.SequenceFormat.PortableText)` for
  single keys and combinations; `Delete` and `Del` are the same key. The stored text is kept as written and is
  what menus show (so Classic shows `Delete`, as today). A text that `QKeySequence` cannot parse, or a
  sequence of more than one combination, is invalid.
- Chord parts are compared upper-case. The second part is matched against the event's `text()` upper-cased,
  and when the text is empty or not printable, against the key name (`QKeySequence(key).toString()`). Shift is
  ignored for chord parts (Shift+M starts `M~` as today).
- An action can have any number of bindings. A binding may carry its own scope as an object:
  `{"key": "Delete", "scope": "viewport"}`; a plain string takes the action's scope.
- Scopes and where they are live:

| Scope | Live when | Mechanism |
|---|---|---|
| `global` | the main window is active and the focus is not a text input | one `QShortcut(QKeySequence(key), window)` with `WindowShortcut` per binding; chords through the filter (5.3) |
| `viewport` | the focus is the canvas, the `Viewport` widget, or nothing in the window | `ViewportCanvas.keyPressEvent` (canvas focused); the filter for `Viewport` or no focus |
| `objects` | the focus is the Object Manager tree | `ObjectTree.keyPressEvent` |

- Text inputs (`viewport._is_text_input`: `QLineEdit`, `QAbstractSpinBox`, `QTextEdit`, `QPlainTextEdit`,
  editable `QComboBox`) never trigger a binding of the filter; `QShortcut`s keep Qt's rule (the field accepts
  `ShortcutOverride` for the keys it edits), which keeps 1.5 unchanged.
- Precedence: `viewport` and `objects` beat `global` (the canvas and the tree accept `ShortcutOverride` for
  every key bound in their scope in the active profile). A pending chord's second key beats everything.
- Conflicts (`profiles.conflicts(profile) -> list[tuple[str, str, str]]`, binding plus two action ids): two
  actions share a binding and their scopes overlap. `global` overlaps every scope; `viewport` and `objects` do
  not overlap each other. A chord `X~Y` conflicts with a single-key binding `X` in an overlapping scope (the
  prefix would hide it). `Num+X` and `X` are different bindings (on the canvas the keypad key goes to the
  viewport binding first; elsewhere Qt falls back to `X`).
- When a profile still holds a conflict (the editor's "Keep both", 4.4), the action that comes first in the
  registry order gets the key and the other gets nothing for that binding; the editor marks both rows.

### 2.3 Mouse gestures

A gesture is an object in the profile's `mouse` list:

```json
{"button": "left", "mods": ["alt"], "key": null, "double": false, "op": "orbit"}
```

| Field | Values | Default |
|---|---|---|
| `button` | `"left"`, `"middle"`, `"right"` | required |
| `mods` | subset of `"shift"`, `"ctrl"`, `"alt"` | `[]` |
| `key` | one plain key that must be held (`"1"`, `"Space"`, `"Z"`), or null | null |
| `double` | true for a double click | false |
| `op` | `"orbit"`, `"pan"`, `"dolly"`, `"select"`, `"add"`, `"remove"`, `"context"` | one of `op` or `action` |
| `action` | an action id (double clicks only) | |

Matching (`controls.match_press(button, mods, held, double) -> dict | None`), applied to the canvas press:

1. Only gestures with the same `button` and `double` are candidates; a gesture with `key` needs that key held.
2. Single clicks: a gesture matches when its `mods` are a subset of the held modifiers. Among matches, the one
   with the most required items (`len(mods)` plus 1 when `key` is set) wins; ties go to the earlier gesture in
   the list.
3. Double clicks: `mods` must equal the held modifiers exactly. No match falls back to the single-click
   gesture (today's "handled as a second press").
4. While a key that some gesture of the profile holds (a "hold key") is down, a `context` gesture never fires.

Operations:

| Op | Canvas behaviour |
|---|---|
| `orbit`, `pan`, `dolly` | `begin_navigation` with mode `orbit`, `pan` or `zoom`; the modeling tool filter yields to every press that matches one of these (replaces `_blocked`) |
| `select` | `_press_select` replace; in pen mode it is the pen press; on a gizmo handle it starts the gizmo drag |
| `add` | `_press_select` add (Shift today); on a gizmo handle it starts the gizmo drag |
| `remove` | `_press_select` remove (Ctrl today); never takes the gizmo |
| `context` | context press (opens the menu on a release within `click_tolerance`); in pen mode it ends an open stroke |

Fixed rules, not data: any second mouse button during a drag cancels it; a right press during a modeling tool
press aborts it; the modeling tool filter takes only presses that match `select`. "Roll" is not offered: the
camera has no roll, and the window shows only controls that work.

The wheel is not a gesture: it always zooms (`zoom_at`), shaped by the cursor settings `zoom_to_cursor`,
`wheel_step` and `wheel_invert`.

### 2.4 Modifier roles and modal keys

Part of every profile:

| Key in `modifiers` | Meaning | Classic | Standard |
|---|---|---|---|
| `snap` | held during a Rotate or Scale gizmo drag: snap to 5 degrees / 0.1 | `shift` | `shift` |
| `extrude` | pressed during a Move drag in a component mode: extrude, then move | `ctrl` | `ctrl` |
| `create_child` | held when creating from the dock or the Create menu: child of the active object | `shift` | `shift` |
| `create_adopt` | held when creating a generator: it adopts the active object | `alt` | `alt` |

Values: `"shift"`, `"ctrl"`, `"alt"`. Two roles may share a modifier.

| Key in `modal` | Meaning | Classic | Standard |
|---|---|---|---|
| `cancel` | cancels a drag, a modeling tool press; ends an open pen stroke | `["Escape"]` | `["Escape"]` |
| `confirm` | ends an open pen stroke | `["Return", "Enter"]` | `["Return", "Enter"]` |

Modal keys are single keys without modifiers, handled by the canvas and the tool filter only while their mode
runs, so they never conflict with bindings.

### 2.5 Cursor settings

Part of every profile (`cursor`). Values outside the range are clamped on load; an unknown enum value takes the
base profile's value.

| Key | Type | Range or values | Classic (today) | Standard | Used by |
|---|---|---|---|---|---|
| `orbit_pivot` | enum | `"Cursor"`, `"Center"`, `"Object"`, `"Camera"` (keys of `viewport.NAV_PIVOTS`) | `"Cursor"` | `"Center"` | `canvas.nav_pivot` when the profile becomes active; Cameras > Navigation still changes it for the session |
| `orbit_style` | enum | `"turntable"` (pitch clamped to 89 degrees), `"free"` (pitch not clamped, the view can turn over) | `"turntable"` | `"turntable"` | `OrbitCamera.orbit` |
| `orbit_speed` | float, degrees per px | 0.05 to 2.0, step 0.05 | 0.3 | 0.3 | `navigate` |
| `invert_orbit_x` | bool | | false | false | `navigate` |
| `invert_orbit_y` | bool | | false | false | `navigate` |
| `invert_pan` | bool | | false | false | `navigate` (moves the view instead of the grabbed point) |
| `dolly_speed` | float per px | 0.001 to 0.05, step 0.001 | 0.005 | 0.005 | `navigate` |
| `zoom_to_cursor` | bool | | true | true | `zoom_at`: true = about the point under the cursor, false = about the camera target |
| `wheel_step` | float, scale per notch | 0.50 to 0.98, step 0.01 | 0.88 | 0.88 | `zoom_at` |
| `wheel_invert` | bool | | false | false | `wheelEvent` (forward zooms out when true) |
| `drag_threshold` | int, px (Manhattan) | 1 to 16 | 3 | 4 | `ViewportCanvas.DRAG_THRESHOLD` uses, `interaction.DRAG_THRESHOLD` |
| `click_tolerance` | int, px (Euclidean) | 1 to 16 | 4 | 4 | `CONTEXT_DRAG_PX` |
| `hold_ms` | int, ms | 150 to 1000, step 10 | 380 | 380 | `IconButton.HOLD_MS` |
| `chord_ms` | int, ms | 500 to 3000, step 100 | 1500 | 1500 | chord window |

Classic keeps 3 px for `drag_threshold` because it is today's value (an input tolerance, not a drawn size);
Standard uses 4, inside the owner's pixel norm.

### 2.6 Showing bindings

- `controls.binding_text(action_id) -> str`: the first binding of the action in the active profile, as stored,
  or `""`.
- `controls.tooltip(label, action_id) -> str`: `"label (binding)"` or `"label"`.
- Menus: after wiring, `MenuBar.refresh_bindings()` sets, for every wired item whose path maps to an action,
  `qs_shortcut` = `binding_text(id)` and the action text = `label` or `label\tbinding`. Items without an action
  keep no shortcut. `menus_data.py` shortcut strings are no longer shown.
- Context menus (`context_menu._add`, `_history`, `_frame`, `_emit_nodes`, `_fill_select`,
  `build_component_menu`) pass `binding_text` of the matching action instead of literals and
  `spec.shortcut`.
- Viewport View menu: `ViewportMenuBar` rewrites the shortcut text of Undo View, Redo View, Frame Default,
  Frame Geometry, Frame Selected Elements, Frame Selected Objects from the profile.
- Rail: `modeling.install.tool_tooltip(spec)` becomes `controls.tooltip(spec.name, "tool." + spec.id)`.
- All of these refresh on `controls.hub().profileChanged`.

## 3. Profiles

### 3.1 Document

One JSON object per profile:

```json
{
  "format": "quartz-controls",
  "version": 1,
  "id": "u-3fa91c07",
  "name": "My Controls",
  "base": "classic",
  "keys": {"tool.extrude": ["Ctrl+E"], "view.frame_all": []},
  "mouse": null,
  "cursor": {"orbit_pivot": "Object"},
  "modifiers": {},
  "modal": {}
}
```

| Field | Built-in | User profile |
|---|---|---|
| `format`, `version` | `"quartz-controls"`, 1 | same |
| `id` | `"standard"` or `"classic"` | `"u-"` plus 8 lowercase hex digits (`secrets.token_hex(4)`) |
| `name` | `"Standard"`, `"Classic"` | 1 to 48 characters, unique among all profiles (case-insensitive) |
| `base` | null | `"standard"` or `"classic"` |
| `keys` | every bound action, action id to list of bindings | overrides only; `[]` unbinds; a missing id inherits the base |
| `mouse` | the full gesture list | null inherits the base; a list replaces it whole |
| `cursor`, `modifiers`, `modal` | full | overrides only |

Resolution (`profiles.resolve(doc) -> Resolved`): start from the base built-in (resolved), apply the
overrides. For each action of the registry with no entry in the resolved `keys`, use `default_keys`. The
Classic built-in also adds, for every modeling tool with a `ToolSpec.shortcut` and no entry, that shortcut
(scope `viewport` for a single key without modifier, the action's scope otherwise), so new tools with a
shortcut keep today's rule in Classic.

### 3.2 Built-in "Classic" (today's behaviour)

Defined as a Python dict `CLASSIC` in `controls/profiles.py`, schema 3.1, `CLASSIC_NAME = "Classic"`.

`keys`:

| Action | Bindings |
|---|---|
| `file.new` | `Ctrl+N` |
| `file.open` | `Ctrl+O` |
| `file.merge` | `Ctrl+Shift+O` |
| `file.save` | `Ctrl+S` |
| `file.save_as` | `Ctrl+Shift+S` |
| `file.save_incremental` | `Ctrl+Alt+S` |
| `file.exit` | `Alt+F4` |
| `edit.undo` | `Ctrl+Z` |
| `edit.redo` | `Ctrl+Y` |
| `app.controls` | `Shift+F12` (new; the reference program's key for its command manager, already in `menus_data.EDIT_MENU`) |
| `object.make_editable` | `C` |
| `tool.pen` | `M~E` |
| `tool.move`, `tool.rotate`, `tool.scale` | `E`, `R`, `T` |
| `view.frame_all`, `view.frame_selection`, `view.frame_objects` | `H`, `S`, `O` |
| `view.frame_default` | `Shift+H` |
| `view.undo`, `view.redo` | `Ctrl+Shift+Z`, `Ctrl+Shift+Y` |
| `camera.perspective`, `camera.top`, `camera.right`, `camera.front` | `F1`, `F2`, `F3`, `F4` |
| `object.rename` | `F2` |
| `object.delete` | `Delete`, `Backspace` |
| every `tool.<id>` with a `ToolSpec.shortcut` | that shortcut (table 1.2; `tool.delete` gets `{"key": "Delete", "scope": "viewport"}`), added by resolution, not written in `CLASSIC` |

Unbound in Classic, as today: `file.import`, `file.export.*`, `file.export_selection`, `file.clear_recent`,
`edit.delete`, `mode.*`, `tool.select`, `tool.line_pen`, the other cameras, `camera.pivot.*`, `create.*` and
the registry tools without a shortcut.

`mouse` (order matters, 2.3):

```json
[
  {"button": "left",   "mods": ["alt"], "op": "orbit"},
  {"button": "middle", "mods": ["alt"], "op": "pan"},
  {"button": "right",  "mods": ["alt"], "op": "dolly"},
  {"button": "left",   "key": "3", "op": "orbit"},
  {"button": "left",   "key": "2", "op": "dolly"},
  {"button": "left",   "key": "1", "op": "pan"},
  {"button": "middle", "op": "orbit"},
  {"button": "left",   "mods": ["ctrl"], "op": "remove"},
  {"button": "left",   "mods": ["shift"], "op": "add"},
  {"button": "left",   "op": "select"},
  {"button": "right",  "op": "context"},
  {"button": "middle", "double": true, "action": "view.frame_default"},
  {"button": "middle", "double": true, "mods": ["shift"], "action": "view.frame_default"},
  {"button": "middle", "double": true, "mods": ["ctrl"], "action": "view.frame_default"},
  {"button": "middle", "double": true, "mods": ["shift", "ctrl"], "action": "view.frame_default"}
]
```

Check against 1.6: Alt+Shift+left -> `[alt]` (one item) beats `[shift]` (tie broken by order) -> orbit;
Ctrl+Shift+left -> remove; 3 held with Alt+left -> orbit by order; 3 and 1 held -> orbit (3 first); right with
a held key -> no context (rule 2.3.4); Alt+middle double -> no double match, so a second press -> pan.

`cursor`: the Classic column of 2.5. `modifiers`, `modal`: the Classic columns of 2.4.

### 3.3 Built-in "Standard" (shipped default)

`STANDARD`, `STANDARD_NAME = "Standard"`. Conventions taken, and why:

- Navigation with Alt and the three buttons (orbit, pan, dolly): the Maya scheme, shared by Houdini, Modo,
  Unreal, Substance and Classic itself, so it is the one most users already know.
- Middle drag orbits, Shift+middle pans, Ctrl+middle dollies: Blender's scheme, the most used free tool; it
  coexists with the Alt scheme without a conflict.
- Q W E R for Selection, Move, Rotate, Scale: Maya, 3ds Max, Unity, Unreal and Houdini all use it.
- F frames the selection, A frames everything, Home resets the view: Maya and Unity (F, A), Blender (Home).
- Keypad views (1 front, 3 right, 7 top, with Ctrl the opposite side, 5 perspective): Blender.
- 1, 2, 3, 4 switch Points, Edges, Polygons, Model: Modo and 3ds Max number the component levels.
- Modeling: Ctrl+E Extrude (Maya), Ctrl+B Bevel (Maya and Blender), I Inset, K Line Cut (knife), Ctrl+R
  Loop/Path Cut, M Weld (merge): Blender. P for the Polygon Pen (the pen key of 2D tools). No chords.
- Desktop conventions: Ctrl+Shift+Z and Ctrl+Y redo, Ctrl+A select all, Ctrl+Shift+A deselect, Ctrl+I invert,
  F2 rename, Delete and Backspace delete, Ctrl+Q quit, Ctrl+, settings.

`keys`:

| Action | Bindings | Scope |
|---|---|---|
| `file.new` | `Ctrl+N` | global |
| `file.open` | `Ctrl+O` | global |
| `file.merge` | `Ctrl+Shift+O` | global |
| `file.save` | `Ctrl+S` | global |
| `file.save_as` | `Ctrl+Shift+S` | global |
| `file.save_incremental` | `Ctrl+Alt+S` | global |
| `file.import` | `Ctrl+Shift+I` | global |
| `file.exit` | `Ctrl+Q` | global |
| `edit.undo` | `Ctrl+Z` | global |
| `edit.redo` | `Ctrl+Shift+Z`, `Ctrl+Y` | global |
| `app.controls` | `Ctrl+,` | global |
| `object.make_editable` | `Alt+C` | global |
| `mode.points`, `mode.edges`, `mode.polygons`, `mode.model` | `1`, `2`, `3`, `4` | global |
| `tool.select_all` | `Ctrl+A` | global |
| `tool.deselect_all` | `Ctrl+Shift+A` | global |
| `tool.invert_selection` | `Ctrl+I` | global |
| `tool.extrude` | `Ctrl+E` | global |
| `tool.bevel` | `Ctrl+B` | global |
| `tool.inset` | `I` | global |
| `tool.line_cut` | `K` | global |
| `tool.loop_path_cut` | `Ctrl+R` | global |
| `tool.weld` | `M` | global |
| `tool.pen` | `P` | global |
| `tool.line_pen` | `Shift+P` | global |
| `tool.select`, `tool.move`, `tool.rotate`, `tool.scale` | `Q`, `W`, `E`, `R` | viewport |
| `view.frame_selection` | `F` | viewport |
| `view.frame_all` | `A` | viewport |
| `view.frame_objects` | `Shift+F` | viewport |
| `view.frame_default` | `Home` | viewport |
| `camera.front`, `camera.back` | `Num+1`, `Ctrl+Num+1` | viewport |
| `camera.right`, `camera.left` | `Num+3`, `Ctrl+Num+3` | viewport |
| `camera.top`, `camera.bottom` | `Num+7`, `Ctrl+Num+7` | viewport |
| `camera.perspective`, `camera.parallel` | `Num+5`, `Ctrl+Num+5` | viewport |
| `edit.delete` | `Delete`, `Backspace` | viewport |
| `object.rename` | `F2` | objects |
| `object.delete` | `Delete`, `Backspace` | objects |

Everything else is unbound in Standard and reachable from the menus, the rail, the dock and the context menus.

`mouse`:

```json
[
  {"button": "left",   "mods": ["alt"], "op": "orbit"},
  {"button": "middle", "mods": ["alt"], "op": "pan"},
  {"button": "right",  "mods": ["alt"], "op": "dolly"},
  {"button": "middle", "mods": ["shift"], "op": "pan"},
  {"button": "middle", "mods": ["ctrl"], "op": "dolly"},
  {"button": "middle", "op": "orbit"},
  {"button": "left",   "mods": ["ctrl"], "op": "remove"},
  {"button": "left",   "mods": ["shift"], "op": "add"},
  {"button": "left",   "op": "select"},
  {"button": "right",  "op": "context"},
  {"button": "left",   "double": true, "action": "tool.loop_selection"}
]
```

The left double click runs Loop Selection only when the current mode supports it (`available` of a mouse
triggered tool action = `spec.supports(scene.mode)`); in Model mode it falls back to a second press. The first
click of the double click has already selected the component under the cursor.

`cursor`: the Standard column of 2.5. `modifiers`, `modal`: the Standard columns of 2.4.

Both built-ins must have no conflict (2.2); a test pins it.

### 3.4 User profiles

Operations in `controls/__init__.py` (each saves the store at once and emits `profileChanged` when the active
profile changed):

| Function | Behaviour |
|---|---|
| `profiles() -> list[dict]` | built-ins first (Standard, Classic), then user profiles by name |
| `active() -> Resolved`, `active_id() -> str` | the selected profile |
| `select(id)` | makes it active; unknown id raises `KeyError` |
| `duplicate(id, name=None) -> str` | new user profile with `base` = the source's built-in base (a built-in source is its own base) and the source's overrides copied; default name `"<name> Copy"`, then `"<name> Copy 2"` and so on; returns the new id and selects it |
| `rename(id, name)` | user profiles only (`PermissionError` for a built-in); `ValueError` for an empty, longer than 48, or duplicate name |
| `delete(id)` | user profiles only; when it was active, its base becomes active |
| `set_keys(id, action_id, bindings)` | user profiles only; stores the list (empty list = unbound) |
| `reset_action(id, action_id)` | removes the override, so the base applies again |
| `set_mouse(id, gestures)`, `reset_mouse(id)` | whole list, or back to null |
| `set_cursor(id, key, value)`, `set_modifier(id, role, mod)`, `set_modal(id, key, keys)` | one override each; `reset_*` variants remove it |
| `reset_profile(id)` | removes every override |
| `export_profile(id, path)` | writes the resolved document (all sections full, `base` kept) |
| `import_profile(path) -> str` | reads a document (`format` must be `"quartz-controls"`, `version` 1); new id; `base` taken from the file when it is a built-in id, else `"standard"`; every section stored as overrides; name made unique as in `duplicate`; selected; returns the id. `ValueError` with one message for anything invalid |

Built-ins can never be changed: every editing control of the editor is disabled for them and the functions
raise `PermissionError`.

### 3.5 Storage

- Path (`store.path()`): `controls.STORE_PATH` when set; else, when `project.SETTINGS_FILE` is set (tests),
  `controls.json` in the same folder; else `%APPDATA%\Quartz\controls.json` (`os.environ["APPDATA"]`, falling
  back to `~`). The folder is created on the first save.
- Content:

```json
{
  "format": "quartz-controls-store",
  "version": 1,
  "selected": "classic",
  "profiles": [ {"format": "quartz-controls", "version": 1, "id": "u-3fa91c07", "...": "..."} ]
}
```

- Writes go to `controls.json.tmp` then `os.replace` (as the file exporters do), UTF-8, `indent=2`,
  `sort_keys=False`.
- Unknown action ids in `keys` are kept in the document and written back unchanged (an extension may not be
  loaded yet); they are ignored by dispatch and not shown in the editor.
- An invalid binding text is dropped on load with a `logging` warning (logger `quartz_studio.controls`).
- A corrupt store (not JSON, wrong `format`, `version` greater than 1, `profiles` not a list) is renamed to
  `controls.json.bad` (replacing an older one), a warning is logged, and the first-run rule (3.6) runs as if
  the file did not exist. One invalid user profile inside a valid store is dropped with a warning; the others
  load.
- `selected` naming a profile that does not exist falls back to `"standard"`.

### 3.6 First run and this machine

- Shipped default: `SHIPPED_DEFAULT = "standard"`.
- `store.first_run()`, called once from `app.main()` before `MainWindow()`: if the store file exists it loads
  it; else it decides `selected` = `"classic"` when `store.previous_install()` is true, `"standard"` otherwise,
  writes the store, and loads it.
- `previous_install()`: on Windows, `winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Quartz\Quartz
  Studio")` succeeds (the `QSettings("Quartz", APP_NAME)` key of `project.settings()`); elsewhere
  `os.path.exists(project.settings().fileName())`; when `project.SETTINGS_FILE` is set,
  `os.path.exists(project.SETTINGS_FILE)`. On this machine the key exists (empty, checked 20/11/2026), so the
  first run selects Classic.
- Integration step on this machine (once, after the build of the package): from `D:\Apps\Quartz\studio` run
  `.\.venv\Scripts\python.exe -c "from quartz_studio.controls import store; store.first_run(); print(store.read()['selected'])"`
  and check that it prints `classic` and that `%APPDATA%\Quartz\controls.json` exists. The owner's open
  `Quartz.exe` is not touched; his next start reads the same file.
- Unloaded state: until `load()` or `first_run()` runs, the active profile is Classic, there are no user
  profiles and nothing is read or written. `controls.reset()` returns to that state (tests that call
  `app.main()` call it afterwards).

## 4. The interface

### 4.1 Where it opens

- `menus_data.EDIT_MENU`: the entry `item("Customize Commands...", "Shift+F12")` becomes
  `item("Controls...", "Shift+F12")`. `menu_bar.SCENE_COMMANDS` gets `(("Edit", "Controls..."),
  open_controls)`, where `open_controls()` runs action `app.controls`. The pruned Edit menu becomes Undo,
  Redo, separator, Controls...
- `editor.open_editor(window)`: one `ControlsDialog` per window, non-modal (`show()`, then `raise_()` and
  `activateWindow()` when already open), so tests that click every menu item never block.

### 4.2 Dialog frame (Crystal, fits 1280 x 720)

All sizes are px in the owner's norm (D:\Markdown\DesignPx.md); colours are `theme` tokens only.

| Part | Size and look |
|---|---|
| `ControlsDialog(QDialog)`, object name `qsControlsDialog` | 960 x 640 fixed, title "Controls", background `SURFACE_BACKDROP`; content inset 16 |
| body card | `make_card` (`SURFACE_CARD`, 1 px `HAIRLINE`, `CARD_RADIUS`) |
| header row | height 48, padding 0 16, gap 8: label "PROFILE" (card header style: uppercase through the font, `TEXT_SECONDARY`), profile combo 256 x 28 (`prepare_combo`), push buttons Duplicate, Rename, Delete, Import..., Export... each height 28, padding 0 12; Rename and Delete disabled for built-ins |
| read-only note | under the header, height 24, `TEXT_SECONDARY`: "Built-in profiles cannot be changed. Duplicate one to edit it." shown only for built-ins |
| page tabs | `PanelTabBar` with Keyboard, Mouse, Cursor; height 28 |
| footer | height 48, padding 0 16: "Reset Profile" (user profiles only, asks for confirmation) at the left, "Close" at the right; height 28 each |

Every change applies at once and is saved; there is no OK or Cancel. The combo lists `profiles()`; choosing an
entry selects that profile (it becomes the active one).

### 4.3 Keyboard page

| Part | Size and look |
|---|---|
| search field | height 28, width 320, placeholder "Search actions or keys"; filters on label, id and binding text, case-insensitive |
| category list | width 192, rows 28: All, File, Edit, Modes, Tools, Mesh, Select, Create, View, Cameras, Objects, then the top-level titles of extension menus; selected row as a tree row (`ACCENT_TINT` with the 2 px `ACCENT` bar) |
| action table | rows 28, columns Action (stretch, `TEXT_PRIMARY`), Keys (320), Scope (96, `TEXT_SECONDARY`: Window, Viewport, Objects), reset (32) |
| binding chip | height 24, pill radius 12, padding 0 8, gap 4, `SURFACE_RAISED`, 1 px `HAIRLINE`, text `TEXT_PRIMARY`; a 12 px close mark at the right removes it |
| add button | 24 x 24 ghost icon button with a plus, after the chips |
| overridden row | 2 px `ACCENT` bar at the left edge (`ACCENT_BAR_W`); the reset button (16 px icon in a 24 button) shows only then and calls `reset_action` |
| conflict mark | binding chip text in `STATUS_ERROR` and the tooltip "Also used by <label>" |

Recording (click a chip to replace it, or the add button to append):

- The chip turns into the recording state: `ACCENT_TINT`, 1 px `ACCENT` border, text "Press keys..." in
  `ACCENT`; the dialog grabs the keyboard (`grabKeyboard`) until done.
- A key press with Ctrl, Alt or Meta, or a non-printable key (F-keys, Delete, Home, keypad, arrows), commits
  that combination at once.
- A plain printable key shows "M then..." and waits `chord_ms`: a second plain key commits the chord `M~X`; the
  time running out commits the single key `M`.
- `Escape` alone cancels the recording (it cannot be recorded as a binding; it is a modal key, 2.4). A click
  anywhere else cancels too. Modifier keys alone do nothing.
- After a commit the conflict check (2.2) runs on the edited profile.

### 4.4 Conflicts

When the new binding conflicts, a banner replaces the search row: height 40, radius 8 (`MENU_RADIUS`),
`SURFACE_MENU`, 1 px `STATUS_ERROR` border, padding 0 12, text "Ctrl+E is already used by Extrude." and three
buttons of height 24:

| Button | Effect |
|---|---|
| Replace | the binding moves to the new action; the other action loses it (written as an override of that action) |
| Keep Both | both keep it; both rows show the conflict mark; dispatch follows 2.2 |
| Cancel | the recording is discarded |

### 4.5 Mouse page

| Part | Size and look |
|---|---|
| gesture list | rows 32: gesture text ("Alt + Left drag", "1 held + Left drag", "Middle double-click"), operation combo 192 x 28 (Orbit, Pan, Dolly, Select, Add to Selection, Remove from Selection, Context Menu; for double clicks: None plus every action label of the registry, searchable), remove button 24 x 24 |
| order buttons | up and down 24 x 24 per row (order decides ties, 2.3) |
| record pad | 256 x 96, `SURFACE_FIELD`, 1 px `HAIRLINE`, radius 10, text "Press a mouse button here, holding modifiers or a key" in `TEXT_SECONDARY`; a press (or double click) inside it with the modifiers and held key adds a gesture with op Orbit, which the user then changes; a gesture identical to an existing one is refused with the banner text "This gesture is already used." |
| reset | "Reset Mouse" push button (height 28), user profiles only, calls `reset_mouse` |

### 4.6 Cursor page

Form rows of height 28, label column 192 (`TEXT_SECONDARY`), groups with collapsible headers of height 24:

| Group | Rows (control) |
|---|---|
| Orbit | Pivot (combo: Cursor, Center, Object, Camera), Style (combo: Turntable, Free), Speed (spin 128 wide, 0.05 to 2.0, suffix "°/px"), Invert Horizontal (toggle), Invert Vertical (toggle) |
| Pan and Dolly | Invert Pan (toggle), Dolly Speed (spin, 0.001 to 0.05) |
| Wheel | Zoom Toward Cursor (toggle), Step (spin, 0.50 to 0.98), Invert Wheel (toggle) |
| Clicks | Drag Threshold (spin, 1 to 16, suffix " px"), Click Tolerance (spin, 1 to 16, " px"), Hold Delay (spin, 150 to 1000, " ms"), Chord Time (spin, 500 to 3000, " ms") |
| Modifiers | Snap, Extrude While Moving, Create as Child, Create and Adopt (combos Shift, Ctrl, Alt) |
| Modal Keys | Cancel, Confirm (binding chips, recorded as in 4.3, single keys only) |

Overridden rows carry the 2 px accent bar and a reset button, as on the keyboard page.

### 4.7 File dialogs

`editor.choose_import_file() -> str | None` and `editor.choose_export_file(name) -> str | None` wrap
`project.choose_open_files` and `project.choose_save_file` with the filter "Quartz Controls (*.json)"; tests
replace them. Errors from `import_profile` show through `project.show_message`.

## 5. Code changes

### 5.1 Decision: wrap

Replacing every handler with one global filter would move the canvas's key handling out of the canvas, and the
canvas-only tests (`_make()` in `test_camera.py`, `test_viewport3d.py`, `test_gizmo_transform.py`,
`test_pen.py`) send keys straight to the canvas with no window. Wrapping keeps each handler where it is and
swaps its hard-coded table for a profile lookup, keeps Qt's `ShortcutOverride` priorities (canvas keys win,
coordinate fields keep their Ctrl+Z rule, typing never fires a shortcut), and leaves one new filter for the two
things Qt cannot do (chords, held keys).

### 5.2 Package `quartz_studio/controls/` (frozen API)

`__init__.py` re-exports:

```python
STORE_PATH: str | None
SHIPPED_DEFAULT: str
def hub() -> ControlsHub                      # QObject with Signal profileChanged(str)
def load() -> None
def reset() -> None
def window()                                  # the window given to install, or None
def install(window) -> None
def refresh() -> None
def actions() -> dict[str, Action]
def register_action(id, label, category, run, keys=(), scope="global", available=None) -> Action
def run(action_id: str) -> bool
def active() -> Resolved
def active_id() -> str
def profiles() -> list[dict]
def select(profile_id: str) -> None
def duplicate(profile_id: str, name: str | None = None) -> str
def rename(profile_id: str, name: str) -> None
def delete(profile_id: str) -> None
def set_keys(profile_id, action_id, bindings) -> None
def reset_action(profile_id, action_id) -> None
def set_mouse(profile_id, gestures) -> None
def reset_mouse(profile_id) -> None
def set_cursor(profile_id, key, value) -> None
def reset_cursor(profile_id, key) -> None
def set_modifier(profile_id, role, mod) -> None
def reset_modifier(profile_id, role) -> None
def set_modal(profile_id, key, keys) -> None
def reset_modal(profile_id, key) -> None
def reset_profile(profile_id) -> None
def export_profile(profile_id, path) -> None
def import_profile(path) -> str
def bindings(action_id: str) -> list[tuple[str, str]]          # (binding text, scope)
def binding_text(action_id: str) -> str
def tooltip(label: str, action_id: str) -> str
def lookup(event: QKeyEvent, scope: str) -> str | None          # single keys and combinations only
def hold_keys() -> set[int]                                     # Qt key codes of gesture keys
def match_press(button: str, mods: set[str], held: set[int], double: bool = False) -> dict | None
def is_navigation_press(event: QMouseEvent, held: set[int]) -> bool
def modifier_held(mods: Qt.KeyboardModifier, role: str) -> bool
def modifier_name(role: str) -> str                             # "Shift", "Ctrl", "Alt"
def modal_key(event: QKeyEvent, key: str) -> bool               # "cancel" or "confirm"
def cursor(key: str)
def conflicts(profile_id: str | None = None) -> list[tuple[str, str, str]]
```

`Resolved` (in `profiles.py`) is a frozen dataclass: `id`, `name`, `builtin: bool`, `base: str | None`,
`keys: dict[str, tuple[tuple[str, str], ...]]` (action id to (binding, scope) pairs), `mouse: tuple[dict, ...]`,
`cursor: dict`, `modifiers: dict`, `modal: dict`, `overridden: frozenset[str]` (action ids and section keys
the user profile overrides).

Module split: `actions.py` (2.1), `profiles.py` (built-ins, resolve, validate, conflicts), `store.py` (3.5,
3.6), `dispatch.py` (install, shortcuts, filter, lookups, matching), `editor.py` (4).

### 5.3 Dispatch (`controls/dispatch.py`)

`install(window)`:

1. Builds the registry (`actions.collect()`), remembers `window`.
2. Deletes the `QShortcut`s it created before, then creates one `QShortcut(QKeySequence(binding), window)`
   with `WindowShortcut` per (action, binding) of scope `global` that is not a chord, in registry order,
   skipping a sequence already taken (2.2); `activated` calls `run(id)`. Sets `window.file_shortcuts` to the
   shortcuts of `file.*` actions in the order new, open, merge, save, save as, save incremental (the frozen name
   of SPEC 9.9; `test_wiring.py` and `test_fileio_ui.py` read it), `window.key_shortcuts` to a dict action id
   -> list of shortcuts, and `window.menu_bar.extension_shortcuts` to those of extension actions.
3. Installs one `KeyFilter` on the `QApplication` (once per window) and sets `window.modeling_shortcuts` and
   `window.controls_filter` to it (`test_smoke.py` removes `modeling_shortcuts` as an event filter).
4. Connects `hub().profileChanged` to rebuild steps 2 and to clear the held keys.

`KeyFilter.eventFilter(obj, ev)`:

- One physical press, one decision: on `ShortcutOverride` it sets `fresh = True`; a `KeyPress` is examined only
  when `fresh` is True (then `fresh = False`), so propagated deliveries to parents and the second `QWindow` or
  widget delivery are ignored. A `KeyPress` received while a focus widget exists and `obj` is neither a
  `QWindow`, the focus widget nor its window is ignored as well.
- Skips text inputs, auto-repeat (except `repeat` actions), events outside the main window, and presses with
  Ctrl, Alt or Meta for chords.
- Chord prefix: a plain key that starts a chord of a live scope is consumed and remembered with its time.
- With a prefix pending (younger than `chord_ms`): on `ShortcutOverride` for a key that completes a chord, it
  accepts the event and returns True (so no `QShortcut` fires); on the `KeyPress` it runs the chord's action
  and consumes it. A key that completes no chord clears the prefix and passes on untouched.
- Held keys: presses and releases of `hold_keys()` (no Ctrl or Alt) update one shared set that the canvas
  reads as `canvas._held_keys`; `ApplicationDeactivate` clears it. This replaces `viewport._HeldNavKeys`.
- Viewport scope without canvas focus: when the focus is the `Viewport` widget or nothing, a `KeyPress` that
  `lookup(ev, "viewport")` maps to an available action runs it and is consumed (covers
  `test_delete_key_with_viewport_focus_removes_face`).

### 5.4 Changes per file

| File | Function or name | Change |
|---|---|---|
| `main_window.py` | `MainWindow.__init__`, `_install_undo_shortcuts`, `FILE_SHORTCUTS`, `_install_file_shortcuts` | the two install calls become `controls.install(self)`; the two methods and `FILE_SHORTCUTS` are removed; `file_shortcuts` stays (set by `install`) |
| `app.py` | `main` | `from quartz_studio.controls import store; store.first_run()` before `MainWindow()`; `controls.refresh()` after `install_extensions(window)` |
| `modeling/install.py` | `_ShortcutFilter`, `_select_pen`, `_key_text`, `_key_of_event`, `SHORTCUT_WINDOW`, `PEN_CHORD`, `install()` | removed; `install()` no longer creates a filter (`controls.install` from `MainWindow` does; if `window.controls_filter` is missing it calls `controls.install(window)`); `prepare()` keeps writing `spec.shortcut` into `menus_data` (harmless, overwritten by `refresh_bindings`) but `_clear_foreign_chords` keeps using the set of registry chords plus `"M~E"` as a literal; `tool_tooltip(spec)` returns `controls.tooltip(spec.name, "tool." + spec.id)` |
| `modeling/interaction.py` | `DRAG_THRESHOLD`, `ViewportToolFilter._blocked`, `eventFilter` Escape | threshold read from `controls.cursor("drag_threshold")` at use; `_blocked(ev)` = `controls.is_navigation_press(ev, canvas._held_keys)`; Escape check = `controls.modal_key(ev, "cancel")` |
| `widgets/viewport.py` | `VIEW_KEYS`, `TOOL_KEYS`, `NAV_KEYS` | removed |
| same | `_HeldNavKeys` | removed (the filter fills the shared held set); the canvas keeps `self._held_keys` bound to `dispatch.held_set()` |
| same | `OrbitCamera.orbit` | new keyword `clamp: bool = True`; `navigate` passes `cursor("orbit_style") == "turntable"` |
| same | `navigate` | orbit dx and dy times `orbit_speed / ORBIT_SPEED` and signs from `invert_orbit_x/y`; pan inverted by `invert_pan`; dolly `exp(-(dx - dy) * cursor("dolly_speed"))` |
| same | `zoom_at` | step `cursor("wheel_step")`; pivot `cursor_point(pos)` when `zoom_to_cursor`, else the camera target |
| same | `wheelEvent` | sign from `wheel_invert` |
| same | `mousePressEvent` | the button and modifier chain of 1.6 becomes `controls.match_press(...)` and a dispatch on `op` (2.3); held keys from `_held_keys`; right press with a held hold key opens nothing |
| same | `mouseDoubleClickEvent` | `match_press(..., double=True)`; an `action` runs through `controls.run`, a canvas-only fallback map runs `view.frame_default` without a window; no match -> `mousePressEvent` |
| same | `_press_select(pos, mods)` | becomes `_press_select(pos, op)` with `op` in select, add, remove; same logic, Shift read as add, Ctrl as remove |
| same | `mouseMoveEvent`, `_update_drag`, `_move_pen_press`, `keyPressEvent` Control | snap from `modifier_held(mods, "snap")`; extrude from `modifier_held(mods, "extrude")` and the key of that role; thresholds from `drag_threshold` and `click_tolerance` (`DRAG_THRESHOLD` and `CONTEXT_DRAG_PX` stay as attributes holding Classic values for tests) |
| same | `_view_key_action`, `event`, `keyPressEvent` | `controls.lookup(e, "viewport")` -> action id; with a window `controls.run(id)`, without one the canvas map `key_actions()` (view.*, camera.*, tool.select/move/rotate/scale) runs it; `event` accepts `ShortcutOverride` for every key with a viewport binding and for `hold_keys()`; cancel and confirm through `modal_key` |
| same | `ViewportMenuBar._bind_menus` | after rewiring, sets the shortcut text of the six View items from `binding_text`; refreshes on `profileChanged` |
| same | `ViewportCanvas.__init__` | `nav_pivot` from `cursor("orbit_pivot")`, updated on `profileChanged` |
| `widgets/object_manager.py` | `ObjectTree.keyPressEvent` | `controls.lookup(e, "objects")`; `object.rename` -> `rename()` when an object is selected, `object.delete` -> `delete_active()` when not editing; new `event()` accepting `ShortcutOverride` for objects-scope keys |
| `widgets/common.py` | `IconButton.mousePressEvent` | sets the hold timer interval from `controls.cursor("hold_ms")` before starting it; `HOLD_MS` stays as the Classic value (380; `test_press_feedback.py` reads it) |
| `widgets/menu_bar.py` | `SCENE_COMMANDS`, `MenuBar`, `create_object`, `add_menu`, `add_entries` | adds `(("Edit", "Controls..."), open_controls)`; new `MenuBar.refresh_bindings()` called at the end of `_wire_scene_commands` and on `profileChanged`; `create_object` reads the roles `create_child` and `create_adopt`; `add_menu` and `add_entries` register actions (2.1.2 step 5) instead of creating `QShortcut`s |
| `widgets/menus_data.py` | `EDIT_MENU` | "Customize Commands..." -> "Controls..." (4.1) |
| `widgets/context_menu.py` | `_history`, `_frame`, `_emit_nodes`, `_fill_select`, `build_component_menu` | shortcut texts from `controls.binding_text` (`edit.undo`, `edit.redo`, `view.frame_selection`, `view.frame_all`, `tool.<id>`, `tool.pen`) |
| `widgets/tool_palette.py` | `ToolPalette.__init__` | `set_tooltips` from `tool_tooltip`; reconnect to `profileChanged` to refresh them |
| `widgets/status_bar.py` | `tool_hint`, `TOOL_HINTS` | the modifier and key names in the hints ("Shift adds", "Ctrl removes", "Hold Ctrl to extrude", "Shift snaps", "Esc cancels", "Enter finishes", "Right click or Enter ends the line") come from `modifier_name` and the modal keys; with Classic the texts are exactly today's |

### 5.5 Existing tests that pin inputs, and what happens to them

All of them run in the unloaded state, which is Classic, so they keep passing unchanged except where marked.

| Test | Pins | Change |
|---|---|---|
| `test_camera.py` (keys and mouse, from `test_orbit_pivot_under_clicked_point_stays_fixed` to `test_held_number_key_navigates_even_without_focus`) | 1.3, 1.6 | none |
| `test_viewport3d.py` `test_escape_cancels_drag`, `test_wheel_zoom_changes_distance`, `test_mouse_navigation`, `test_nav_icons_drag_navigates`, `test_keyboard_tools_and_hud` | 1.3, 1.6 | none |
| `test_gizmo_transform.py` `test_palette_buttons_switch_tool_and_keys_check_their_button`, `test_tool_key_during_rotate_drag_cancels_and_restores`, `test_move_key_during_rotate_drag_cancels_and_restores`, the right-click and Escape cancel tests | E, R, T, cancel | none |
| `test_context_menu.py` lines 336 to 343 and `test_alt_right_drag_zooms_and_opens_no_menu` to `test_pens_keep_their_right_click_and_open_no_menu` | context menu texts and right-button rules | none (`binding_text` returns `spec.shortcut` and `"M~E"` in Classic) |
| `test_modeling_integration.py` `test_every_tool_menu_item_shows_registry_shortcut`, `test_registry_chords_are_shown_on_menu_items`, the three Delete key tests, `test_pen_chord_m_e_activates_pen_tool` | 1.2, Delete | none |
| `test_trunk_tool.py` `test_tool_is_in_the_mesh_menu_with_its_shortcut` | `M~R` shown | none |
| `test_tool_palette.py` `test_tooltips_carry_name_and_shortcut` | rail tooltips | none |
| `test_modeling_merge.py` `test_shortcuts_are_unique_across_registry` | registry data | none |
| `test_wiring.py` `test_menu_undo_redo`, `test_file_menu_wiring_and_shortcuts` | menu texts, `win.file_shortcuts` | none |
| `test_wiring.py` line 528 | `bar.menus["Edit"].entries_text() == ["Undo", "Redo"]` | becomes `["Undo", "Redo", "---", "Controls..."]` |
| `test_fileio_ui.py` `test_keyboard_shortcuts_run_the_commands` | `win.file_shortcuts` by key | none |
| `test_objects_ui.py` `test_make_editable_command_button_menu_and_key`, the Alt adopt tests | `C`, Alt and Shift on create | none |
| `test_coordinates.py` `test_ctrl_z_y_in_focused_field_undo_scene`, `test_object_manager_delete_and_undo` | 1.5, 1.4 | none |
| `test_object_manager.py` delete and rename tests | 1.4 | none |
| `test_pen.py` `test_esc_enter_and_right_click_end_stroke`, `test_escape_cancels_extrude_drag` | modal keys | none |
| `test_press_feedback.py` lines 292 and 294 | `IconButton.HOLD_MS` | none (kept at 380) |
| `test_smoke.py` line 352 | `win.modeling_shortcuts` removed as an event filter | none (it is the `KeyFilter`) |
| `test_smoke.py` `test_every_visible_control_is_wired` and `test_wiring.py` equivalents | every menu item does something | Edit > Controls... opens the non-modal editor; the test closes top-level dialogs it opens if it checks for leftovers |
| `test_hooks.py` `test_menu_add_menu_with_handler_separator_submenu_and_shortcut` | an extension shortcut fires | none (the action's `QShortcut` fires) |
| `test_hooks.py` `test_main_runs_with_a_raising_extension` | `app.main()` | sets `controls.STORE_PATH` to a file in its `TMP` before `main()` and calls `controls.reset()` after |

### 5.6 New tests

Each file runs as a script like the others (`_run_as_script`) and offscreen.

`tests/test_controls_profiles.py` (no window):
- both built-ins validate, have `format`, `version`, names "Standard" and "Classic", and no conflict;
- the Classic tables of 3.2 hold literally (the test lists every row of 1.1 to 1.4 and 1.6 as data and compares
  them with `profiles.resolve(CLASSIC)`), including every chord of 1.2 from the registry;
- the Standard table of 3.3 holds literally;
- a user profile: duplicate, rename (empty, too long and duplicate names refused), delete (falls back to its
  base), `set_keys`, `reset_action`, `reset_profile`; built-ins raise `PermissionError`;
- store: round trip through a temporary `STORE_PATH`; unknown action ids survive a save; an invalid binding is
  dropped; a corrupt file becomes `controls.json.bad` and the first-run rule runs; a missing `selected` falls
  back to Standard;
- `first_run` with `previous_install` patched true writes Classic, false writes Standard;
- export then import gives an equal resolved profile under a new id and a unique name; a file with another
  `format` is refused with `ValueError`;
- cursor values are clamped; an unknown enum value takes the base value;
- the unloaded state is Classic and touches no file (the test points `STORE_PATH` at a missing folder and checks
  it stays missing until a write).

`tests/test_controls_dispatch.py` (real `MainWindow`, offscreen; each built-in profile in turn):
- every action with a binding in the profile runs when the binding is pressed with `QTest.keyClick` in its
  scope (focus set to the canvas, the tree or the window as the scope needs), checked by a spy that replaces
  `Action.run`; chords with two presses;
- every wired menu item, rail fold-out entry and dock entry maps to a registered action id;
- `win.file_shortcuts` has the six file shortcuts of the active profile;
- 1.9 fixed: one K press runs nothing, `K~L` runs Loop/Path Cut, `U~C` runs Collapse and not Make Editable,
  `M~#` (Shift+3 with text "#") and `M~,` run Normal Scale and Normal Rotate, one key press delivered to the
  canvas and propagated to the `Viewport` runs its action once;
- typing in a `QLineEdit` never runs a binding; `Ctrl+Z` in an unmodified coordinate field still undoes the
  scene;
- switching the profile live changes the menus' shortcut text, the rail tooltips and the `QShortcut`s (Classic
  `E` moves, Standard `W` moves and `E` rotates) without a restart;
- an extension item added with `add_menu` gets `menu.<slug>` and its shortcut fires in both profiles.

`tests/test_controls_viewport.py` (canvas and window, offscreen):
- Standard mouse: Shift+middle pans, Ctrl+middle dollies, middle orbits, Alt combinations as Classic; a left
  double-click on a polygon in Polygons mode runs Loop Selection; in Model mode it is a plain press;
- Classic mouse: every row of 1.6 through `match_press` (table-driven) and through real events on the canvas;
- cursor settings: `orbit_style` free lets the pitch pass 89 degrees; `invert_orbit_x` flips the heading
  change; `zoom_to_cursor` false keeps the target fixed under the wheel; `wheel_invert`; `wheel_step`;
  `drag_threshold` 8 ignores a 6 px drag; `orbit_pivot` sets `canvas.nav_pivot` on selection;
- modifier roles: with `snap` set to Ctrl, Ctrl snaps a rotate drag and Shift does not;
- the modeling tool filter yields to every navigation gesture of the active profile.

`tests/test_controls_widgets.py`:
- the Object Manager answers `object.rename` and `object.delete` from the profile;
- `IconButton` opens its fold-out after `hold_ms` (set to 200 in a user profile);
- the status bar hints of 9.8 are unchanged in Classic and follow a changed `snap` role;
- context menus show the active profile's bindings;
- Edit > Controls... exists in both profiles and opens one dialog.

`tests/test_controls_editor.py` (the dialog offscreen, at 1280 x 720 window size):
- fits inside 1280 x 720 and every size it sets is in the owner's norm (the test lists the allowed values of
  DesignPx.md and checks fixed sizes, row heights and paddings of the dialog's widgets);
- built-in selected: every editing control disabled, the note visible; Duplicate creates "Classic Copy" and
  enables editing;
- recording: `Ctrl+E` commits at once; `M` then `E` commits `M~E`; `M` alone commits after `chord_ms`;
  Escape cancels;
- conflict banner with Replace, Keep Both and Cancel, each with its effect on the store;
- search filters by label and by binding text; categories filter;
- mouse page: the record pad adds a gesture from a synthetic press with modifiers; a duplicate is refused;
- cursor page: each control writes its override and the reset button removes it;
- import and export through replaced `choose_import_file` and `choose_export_file`.

## 6. File ownership

Five builders work in parallel. Nobody edits a file that is not in their row. The API of 5.2 is frozen, so
builders 2 to 5 code against it before builder 1 finishes; each may keep a small local stub while waiting and
must delete it before handing over.

Other fleets edit some of these files tonight (`main_window.py`, `app.py`, `widgets/menu_bar.py` for the
extension hooks; `widgets/viewport.py` for the display filters and the zoom limit; `modeling/*` for Trunk;
the palette contract for `tool_palette.py`, `object_palette.py`, `common.py`). Each builder re-reads a shared
file just before editing it, changes only the functions named in 5.4, and reports any clash to the
orchestrator.

| Builder | Owns (writes) | Delivers |
|---|---|---|
| 1 core | `quartz_studio/controls/__init__.py`, `controls/actions.py`, `controls/profiles.py`, `controls/store.py`, `tests/test_controls_profiles.py` | 2.1, 2.2 parsing and conflicts, 2.3 data and `match_press`, 2.4, 2.5, 3 entirely, the 5.2 functions except those of builder 2 |
| 2 dispatch | `controls/dispatch.py`, `modeling/install.py`, `modeling/interaction.py`, `tests/test_controls_dispatch.py` | 5.3; `install`, `refresh`, `lookup`, `hold_keys`, `is_navigation_press`, `modifier_held`, `modal_key`, `binding_text`, `tooltip`, `bindings` (re-exported by `__init__`); the 5.4 rows for `modeling/install.py` and `modeling/interaction.py` |
| 3 viewport | `widgets/viewport.py` (only the input functions of 5.4), `tests/test_controls_viewport.py` | the 5.4 rows of `viewport.py` |
| 4 widgets | `widgets/object_manager.py`, `widgets/common.py` (only `IconButton.mousePressEvent`), `widgets/menu_bar.py`, `widgets/menus_data.py`, `widgets/context_menu.py`, `widgets/tool_palette.py` (only the tooltip lines), `widgets/status_bar.py`, `tests/test_controls_widgets.py` | the 5.4 rows of those files, `open_controls` |
| 5 editor | `controls/editor.py`, `tests/test_controls_editor.py` | section 4 (except 4.1, which is builder 4) |

Shared files nobody above owns, kept for the integration step: `main_window.py`, `app.py`, `theme.py`
(no new token is needed; if the editor needs one, builder 5 reports it), `icons.py` (the plus and close marks
use existing icons: `plus` and `close`; if missing, builder 5 paints them locally with `ICON_STROKE`),
`tests/test_wiring.py`, `tests/test_hooks.py`, `tests/test_smoke.py`, `README.md`, `SPEC.md`.

### 6.1 Integration step (one session, after the five builders)

1. `main_window.py`: the 5.4 row (remove `_install_undo_shortcuts`, `_install_file_shortcuts`,
   `FILE_SHORTCUTS`; call `controls.install(self)`).
2. `app.py`: `store.first_run()` before `MainWindow()`, `controls.refresh()` after `install_extensions`.
3. `menu_bar.add_menu` / `add_entries`: check that builder 4's change keeps `extension_shortcuts` and the hooks
   tests green.
4. `tests/test_wiring.py` line 528 and `tests/test_hooks.py` `test_main_runs_with_a_raising_extension` as in
   5.5.
5. Run every suite: from `D:\Apps\Quartz\studio`, `$env:QT_QPA_PLATFORM='offscreen'`, then
   `.\.venv\Scripts\python.exe tests\<file>.py` for each file in `tests\` (no pytest in the venv).
6. Snapshot the window at 1920 x 1010 and 1280 x 720 (`tools/snapshot.py`) and a grab of the editor on each
   page at 1280 x 720; look at them.
7. Run the first run on this machine (3.6) and confirm `classic`.
8. `README.md`: a "Controls" section (where the editor is, the two profiles, the store path); `SPEC.md`: a
   short section 11 pointing to this file, and in 3.4 and 4 replace "with shortcut" wording by "with the
   active profile's binding". The `.md` files in `D:\Markdown` are the orchestrator's job.
9. Do not run `build.ps1`; the owner rebuilds `Quartz.exe` himself.

## 7. Open points for the owner

1. Name: the profile of today's controls is shown as "Classic" because SPEC.md rule 0.3 forbids naming the
   reference program in the interface. Changing `CLASSIC_NAME` to "Cinema 4D" is one line if he accepts the
   exception (the id stays `classic`).
2. Classic has no key for the Selection tool today. The reference program uses `9` (Live Selection), `0`
   (Rectangle) and `8` (Lasso), already written in `menus_data.SELECT_MENU`; they are not added because
   Classic must equal today. The owner can add them in his own profile, or ask for them in Classic.
3. Standard orbits around the view centre (`orbit_pivot` "Center"), as Maya and Blender do by default;
   Classic keeps the point under the cursor.
