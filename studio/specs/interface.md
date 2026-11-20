# Quartz Studio interface contract: selection tools, splitter, coordinates, display filter, zoom, palettes

Contract for the night run of 20/11/2026. It covers the owner's interface requests except controls,
shortcuts and the Attribute Manager, which have their own contracts. Builders implement from this file
without asking anybody, so every name, key, label, default, size and behaviour below is binding. When the
code you open differs from a line number quoted here (other fleets are editing tonight), find the named
symbol and apply the rule to it; the name wins over the line number.

## 0. Ground rules for every builder

- Python only as `.\.venv\Scripts\python.exe` from `D:\Apps\Quartz\studio`. Offscreen runs:
  `$env:QT_QPA_PLATFORM='offscreen'; $env:QT_QPA_FONTDIR='C:/Windows/Fonts'`. Never kill a process by
  name, never touch the owner's running Quartz.exe, never run `build.ps1`.
- No comments and no docstrings in code. English for code, UI text and docs.
- The window shows only controls that do something. A menu item without a handler is pruned
  (`StudioMenu.prune_unwired`); a panel with no options is hidden; nothing is added "for later".
- Every colour is a token from `quartz_studio/theme.py`. New tokens are listed in this file and are
  added by the Layout builder only (section 9).
- Pixel norm (`D:\Markdown\DesignPx.md`): every px size is one of 1, 2, 4, 6, 8, 12, 16, 24, 32, 48,
  64, 72, 96, 128, 256, 512, 1024, or one of the listed sums and differences (10, 14, 18, 20, 28, 36, 40,
  44, 56, 80, 88, 112, 120, 136, 144, 160, 192, 224, 240, ...), any multiple of 16 from 128 up. 1 px only
  for hairlines and borders. No odd values except 1, no fractions. Every size in this file already follows
  it; any size a builder has to invent follows it too.
- Tests never touch the real profile: `tests/conftest.py` (section 1.6) points `QUARTZ_PREFS_DIR` at a
  temporary folder and wipes it before every test.
- Simplest implementation that works; reuse the existing functions named here instead of writing new
  geometry.

## 1. Shared preferences: `quartz_studio/prefs.py` (new)

One JSON file per user holds the display filter, the palettes, the selection tool options and whatever the
controls contract stores. The controls contract relies on exactly these names.

### 1.1 Location

- Folder: `os.environ["QUARTZ_PREFS_DIR"]` when that variable is set and not empty; otherwise
  `os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Quartz")`.
- Safety net: when the variable is not set and `"pytest"` is in `sys.modules`, the folder is
  `os.path.join(tempfile.gettempdir(), "quartz-prefs-pytest")`, so a test run can never write the real
  profile even without the conftest.
- File: `<folder>/prefs.json`. The folder is created on the first write, not on import or read.
- The folder is resolved on every `path()` call, so a test that changes the variable and calls
  `reload()` gets the new place.

### 1.2 File format

```json
{"version": 1, "values": {"viewport.display": {"shading": "shaded_lines"}, "palette.tools": {"position": "left"}}}
```

- `VERSION = 1` (module constant). Top level is an object with `version` (int) and `values` (object).
- Keys are flat strings with a dot namespace. Values are anything `json.dumps` accepts (dict, list, str,
  int, float, bool). Reserved namespaces: `viewport.`, `palette.`, `selection.` (this contract),
  `controls.` (controls contract). Nobody else writes into another builder's namespace.
- Written with `json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)`, UTF-8, to
  `prefs.json.tmp` in the same folder and then `os.replace` onto `prefs.json` (atomic).

### 1.3 API (module level; nothing else is public)

| Name | Behaviour |
|---|---|
| `get(key: str, default=None)` | Returns a deep copy of the stored value for `key`, or `default` when the key is absent. Loads the file lazily on the first call. Never raises. |
| `set(key: str, value) -> None` | `value is None` removes the key. Otherwise the value is checked with `json.dumps` (a `TypeError`/`ValueError` from it propagates to the caller and nothing changes), deep-copied and stored. If the stored value is equal (`==`) to the old one nothing is written and no signal is sent. Otherwise the file is written and `changed.emit(key)` runs after the write. A write error (`OSError`) is logged with `logging.getLogger("quartz_studio.prefs").warning` and swallowed; the in-memory value stays changed and the signal is still emitted. |
| `path() -> str` | Absolute path of `prefs.json` (section 1.1), whether or not it exists. |
| `changed` | A Qt signal carrying the key (`str`). It is the bound signal of a module-level `QObject` instance: `class _Hub(QObject): changed = Signal(str)`, `_hub = _Hub()`, `changed = _hub.changed`. Connect with `prefs.changed.connect(fn)`. |
| `reload() -> None` | Drops the in-memory copy so the next `get`/`set` reads the file again. Emits nothing. Used by tests and by the conftest. |

`get`, `set`, `path` and `changed` are the interface shared with the controls contract and must keep
exactly these names and signatures; `reload` and `VERSION` are the only additions.

### 1.4 Loading rules

- Missing file: empty values, no warning.
- File that is not valid JSON, whose top level is not an object, or whose `values` is not an object:
  the file is copied to `prefs.corrupt.json` in the same folder (overwriting an older copy), a warning is
  logged, and loading continues with empty values. The broken file is replaced on the next `set`.
- `version` missing or lower than `VERSION`: read the values as they are (there is no migration yet).
- `version` higher than `VERSION`: read the values; on the next write keep every key, including keys this
  build does not know, and write `version` back as the higher number read.
- Values are never validated by `prefs`; every feature validates its own keys when it reads them and falls
  back to its own default for anything malformed.

### 1.5 Keys used by this contract

| Key | Owner | Shape |
|---|---|---|
| `viewport.display` | Viewport builder | object, section 5.2 |
| `palette.tools` | Palettes builder | object, section 7.3 |
| `palette.objects` | Palettes builder | object, section 7.3 |
| `selection.options` | Selection builder | object `{tool_id: {param_key: value}}`, section 2.3 |

### 1.6 Test isolation: `tests/conftest.py` (new)

```python
import os
import tempfile

import pytest

os.environ["QUARTZ_PREFS_DIR"] = tempfile.mkdtemp(prefix="quartz-prefs-")


@pytest.fixture(autouse=True)
def _fresh_prefs():
    from quartz_studio import prefs

    for name in ("prefs.json", "prefs.json.tmp", "prefs.corrupt.json"):
        try:
            os.remove(os.path.join(os.environ["QUARTZ_PREFS_DIR"], name))
        except OSError:
            pass
    prefs.reload()
    yield
```

The variable is assigned (not `setdefault`) so an owner's shell variable can never leak into tests.

### 1.7 Tests: `tests/test_prefs.py` (new)

1. `path()` is inside `QUARTZ_PREFS_DIR` and ends with `prefs.json`.
2. `get("x")` is `None`, `get("x", 3)` is 3 on an empty profile; no file is created by reading.
3. `set("a.b", {"k": [1, 2]})` writes the file; a fresh `reload()` then `get` returns an equal value; the
   returned value is a copy (mutating it does not change a second `get`).
4. `set` emits `changed` once with the key; setting an equal value emits nothing and does not rewrite the
   file (compare `os.stat(path()).st_mtime_ns` before and after).
5. `set(key, None)` removes the key and emits.
6. `set("k", object())` raises `TypeError` and leaves the old value.
7. A file containing `{not json` is moved to `prefs.corrupt.json`, `get` returns defaults, the next `set`
   writes a valid file.
8. A file with `"version": 7` and an unknown key keeps both after a `set` of another key.
9. A read-only folder (patch `os.replace` to raise `OSError`) keeps the value in memory, logs a warning
   and still emits.
10. With `QUARTZ_PREFS_DIR` deleted from the environment and `pytest` imported, `path()` is in the
    temporary `quartz-prefs-pytest` folder, never under `APPDATA`.

## 2. Selection tools

### 2.1 What exists today

- Commands (non-interactive `ToolSpec`s, `menu="Select"`, run on the current selection through
  `modeling/install.activate_tool` and `ModelingController.apply_once`), all in
  `quartz_studio/modeling/ops_select.py`: `select_all`, `deselect_all`, `invert_selection` (U~I),
  `select_connected` (U~W), `grow_selection` (U~G), `shrink_selection` (U~K), `loop_selection` (U~L,
  lines 275-291), `ring_selection` (U~B, 294-310), `outline_selection` (U~Q), `fill_selection` (U~F,
  321-352, needs a closed edge contour), `path_selection` (U~M), `convert_selection` (U~X). They stay as
  they are, with their ids, names and shortcuts; the viewport context menu keeps using them
  (`widgets/context_menu.py::_fill_select`, `SELECT_ORDER`).
- Interactive selection: only the click pick in the canvas. `ViewportCanvas.mousePressEvent`
  (`widgets/viewport.py` ~2663) sends every left click that is not navigation or pen to `_press_select`
  (~2526): Shift adds, Ctrl removes, a click on nothing clears; `pick()` (~985) returns one point, edge,
  polygon or object. This works for every tool, not only for `select`. There is no rectangle, lasso or
  brush selection, and click selection is not recorded in the undo history.
- Scene tool `"select"` (`scene.TOOLS`, `scene.py` line 28) is the rail's first button
  (`widgets/tool_palette.py` lines 167-184: `Cmd("Selection", "pal_live_selection")`, a single checkable
  item in the exclusive group `TOOLS`), HUD text `"Selection"` (`viewport.HUD_TEXTS`, line 515), status
  bar name `"Selection"` (`status_bar.TOOL_NAMES`).
- Mesh helpers to reuse (`quartz_studio/modeling/meshkit.py`): `edge_loop(mesh, e) -> list[Edge]`
  (ordered), `edge_ring(mesh, e) -> list[Edge]` (ordered), `polygon_loop(mesh, e) -> list[int]` (ordered
  strip of quads crossing `e`), `boundary_loops(mesh)`, `edge_faces`, `point_faces`, `face_normals`,
  `region_boundary`, `directed_edges`, `edge_key`. Canvas helpers: `_object_view(obj)`, `_pick_point`,
  `_pick_edge`, `_pick_polygon`, `_poly_screen(view, k)`, `_edge_screen(view, edge)`,
  `_sight_clear(points)`, `pick_object(pos)`, `project_world(pts)`.

### 2.2 Decisions

- Every new selection tool is a **scene tool** (a value of `scene.tool`), not a modeling `ToolSpec`.
  Reason: selection must work in Model mode on parametric objects, and `activate_tool` refuses
  non-editable objects and opens a `ToolSession`. The modeling registry and `ViewportToolFilter` are not
  touched; when the scene tool changes to a selection tool, `modeling/install.py::install.on_tool` already
  deactivates the modeling controller.
- The scene tool `"select"` becomes **Brush Selection** (Cinema 4D's Live Selection). The id stays
  `"select"` so every existing call to `scene.set_tool("select")` keeps working; only its texts change.
- New scene tool ids, in this order: `"select_loop"`, `"select_ring"`, `"select_pattern"`,
  `"select_fill"`, `"select_phong"`.
- There is no rectangle selection in the code; none is added (the owner did not ask for one).
- Every completed stroke or click of a selection tool that changes the selection records exactly one undo
  step. Click selection with Move, Rotate and Scale stays as today (not recorded).
- All selection tools act on `scene.active` only (the scene has one active object and no multi-object
  selection).

### 2.3 Module `quartz_studio/modeling/select_tools.py` (new; not named `ops_*`, so the modeling registry
does not load it)

Public names:

```python
@dataclass(frozen=True)
class SelectTool:
    id: str
    name: str
    icon: str
    modes: tuple[str, ...]
    entry_mode: str
    params: tuple[Param, ...]
    hint: str
    hint_model: str = ""

TOOLS: tuple[SelectTool, ...]
TOOL_IDS: tuple[str, ...]
def get(tool_id: str) -> SelectTool
def is_select_tool(tool: str) -> bool
def options(tool_id: str) -> dict
def set_option(tool_id: str, key: str, value) -> None
def reset_options(tool_id: str) -> None
def activate(tool_id: str) -> None
def ensure_mode(scene, tool_id: str) -> None
def apply_selection(scene, mode: str, items, op: str) -> bool
def menu_commands() -> list[tuple[tuple[str, ...], Callable[[], None]]]
def loop_elements(mesh, mode: str, edge, boundary: bool = False) -> set
def ring_elements(mesh, mode: str, edge, polygon: int | None = None) -> set
def pattern_elements(mesh, mode: str, edge, polygon: int | None, point: int | None,
                     count: int, skip: int, direction: str) -> set
def fill_region(mesh, face: int, borders: set, blocked: set) -> set[int]
def phong_region(mesh, face: int, angle: float) -> set[int]
```

`Param` is `quartz_studio.modeling.registry.Param` (reused for kinds, ranges and clamping).

At import the module:
1. Extends `scene.TOOLS` with the five new ids when missing:
   `scene_module.TOOLS = tuple(scene_module.TOOLS) + missing` (same technique as
   `install._extend_scene_tools`).
2. Registers the five new icons (section 2.10) with `icons.register` when `not icons.has(name)`.

The tool table (exact):

| id | name | icon | modes | entry_mode | params (key, label, kind, default, min, max, step, unit/choices) |
|---|---|---|---|---|---|
| `select` | Brush Selection | `pal_live_selection` | points, edges, polygons, model | (none, any mode) | `radius`, "Radius", int, 10, 2, 512, 2, unit "px"; `visible_only`, "Only Select Visible Elements", bool, True; `tolerant`, "Tolerant Selection", bool, False |
| `select_loop` | Loop Selection | `pal_select_loop` | points, edges, polygons | edges | `boundary`, "Select Boundary Loop", bool, False |
| `select_ring` | Ring Selection | `pal_select_ring` | points, edges, polygons | edges | none |
| `select_pattern` | Pattern Selection | `pal_select_pattern` | points, edges, polygons | edges | `count`, "Select", int, 1, 1, 64, 1; `skip`, "Skip", int, 1, 0, 64, 1; `direction`, "Direction", choice, "Loop", choices ("Loop", "Ring") |
| `select_fill` | Fill Selection | `pal_select_fill` | polygons | polygons | none |
| `select_phong` | Phong Angle Selection | `pal_select_phong` | polygons | polygons | `angle`, "Angle", angle, 40.0, 0.0, 180.0, 1.0 |

Hints (`hint` for component modes, `hint_model` for Model mode; separator `" · "`):

| id | hint | hint_model |
|---|---|---|
| `select` | `Paint to select · Shift adds · Ctrl removes · Shift+wheel sizes the brush` | `Paint over an object to select it · Ctrl deselects · Shift+wheel sizes the brush` |
| `select_loop` | `Click an edge to select its loop · Shift adds · Ctrl removes` | |
| `select_ring` | `Click an edge to select its ring · Shift adds · Ctrl removes` | |
| `select_pattern` | `Click an edge to select a pattern along its loop · Shift adds · Ctrl removes` | |
| `select_fill` | `Click a polygon to fill up to the selected edges · Ctrl removes` | |
| `select_phong` | `Click a polygon to select its smooth area · Shift adds · Ctrl removes` | |

Options storage: `options(tool_id)` returns the tool's defaults updated with
`prefs.get("selection.options", {}).get(tool_id, {})`, each value clamped with its `Param.clamp`; unknown
keys are dropped. `set_option` clamps, merges and writes the whole `selection.options` object back with
`prefs.set`. `reset_options(tool_id)` removes that tool's entry. Options persist between sessions.

`activate(tool_id)`: `ensure_mode(scene, tool_id)` then `scene.set_tool(tool_id)`.
`ensure_mode(scene, tool_id)`: when `scene.mode not in tool.modes`, `scene.set_mode(tool.entry_mode)`.

`apply_selection(scene, mode, items, op)` with `op` in `"replace"`, `"add"`, `"remove"`:
- Model mode (`mode == "model"`): `items` is a set of at most one `SceneObject`. `replace`/`add` with an
  object: `scene.set_active(obj)` when it is not active, then `scene.select_object(True)`; `replace`
  with an empty set: `scene.select_object(False)`; `remove`: when the active object is in `items`,
  `scene.select_object(False)`.
- Component modes: does nothing unless `scene.is_editable(scene.active)`. Computes the new set from
  `scene.selected_points|edges|polygons` (edges normalised with `edge_key`), compares it with the old set,
  and only when it differs calls `scene._record("selection")` (inside a group, see 2.4) and then
  `scene.select_components(new, ...)` with the same `add`/`remove` flags, or a replace.
- Returns `True` when the selection changed.

`menu_commands()` returns, for the main menu (wired by the integration step):
`(("Select", "Brush Selection"), partial(activate, "select"))`, `(("Select", "Loop Selection"),
partial(activate, "select_loop"))`, `(("Select", "Ring Selection"), ...)`, `(("Select", "Pattern
Selection"), ...)`, `(("Select", "Fill Selection"), ...)`, `(("Select", "Phong Angle Selection"),
...)`. They are appended after the modeling commands, so for the labels that the commands
`loop_selection`, `ring_selection` and `fill_selection` also bind, the interactive tool wins in the main
menu (`StudioMenu.bind` keeps the last handler). The context menu keeps the commands.

### 2.4 Event handling: `quartz_studio/modeling/select_interaction.py` (new)

`class SelectionToolFilter(QObject)` installed on `ViewportCanvas` with `canvas.installEventFilter`. It
owns a `SelectionOverlay(QWidget)` child of the canvas (transparent for mouse, `WA_NoSystemBackground`,
resized with the canvas, raised above it, the same technique as `interaction.ToolOverlay`).

It acts only while `is_select_tool(scene.tool)`. It never consumes an event when:
- the event is not a mouse press, move, release, wheel, key press or leave on the canvas;
- it is a mouse press or release of a button other than the left one, or a move with a non-left button
  held (middle, right and Alt combinations stay navigation and the context menu exactly as today);
- it is a wheel event without exactly the Shift modifier, or Shift+wheel while the tool is not Brush
  Selection (plain wheel always zooms);
- Alt is held, or `canvas._held_keys` is not empty (number-key navigation);
- `canvas._nav` is not `None`.

On `scene.toolChanged` it calls `ensure_mode(scene, tool)` for selection tools and clears the overlay.
On `scene.modeChanged`, `objectsChanged`, `changed` it clears the hover cache.

Undo grouping: on left press it calls `scene.begin_group()`; `apply_selection` calls
`scene._record("selection")` before the first change of the stroke (the group makes later calls no-ops);
on release, on Escape and on focus loss it calls `scene.end_group()`. One stroke, one undo step.

A click on a non-editable active object in a component mode sends
`controller().message.emit(f"{tool.name}: {EDITABLE_MESSAGE}")` (`modeling/install.controller`,
`modeling/session.EDITABLE_MESSAGE`) and changes nothing.

Modifiers at press decide the operation for the whole stroke: none `replace`, Shift `add`, Ctrl
`remove` (Ctrl+Shift counts as Ctrl). Fill Selection uses `add` for none and Shift.

### 2.5 Brush Selection (`select`)

- Cursor: the canvas cursor stays the arrow. The overlay draws a circle of `radius` px around the cursor
  whenever the cursor is inside the canvas: pen 1 px, `theme.TEXT_SECONDARY` while hovering,
  `theme.SELECT_FRONT` while painting with `add`/`replace`, `theme.TEXT_MUTED` while painting with
  `remove`; no fill; antialiased; centre at the cursor position. It hides on leave.
- Press: for `replace`, the selection of the current mode is cleared first (through `apply_selection`
  with an empty `replace`, part of the same undo step); then the brush is applied at the press position.
- Move with the left button: the brush is applied at points spaced `max(1, radius / 2)` px along the
  segment from the last applied position to the current one (so fast strokes leave no holes).
- Release: ends the stroke. A press and release without movement is a single dab (a click).
- Hit rules at one dab of centre `c` (canvas pixels) and radius `R`, on `view = canvas._object_view(active)`
  (cache the view for the whole stroke; the camera cannot change during a stroke):
  - Points: candidates `view.in_front`; with `visible_only`, also `view.visible_points` and then
    `canvas._sight_clear(view.world[cand])`. Hit when `hypot(screen - c) <= R`.
  - Edges: candidates `view.visible_edges` with `visible_only`, else `mesh.edges`; screen segment from
    `canvas._edge_screen(view, e)` (skip `None`). Not tolerant: hit when the segment midpoint is within
    `R`. Tolerant: hit when the distance from `c` to the segment is `<= R`. With `visible_only`, the
    world midpoint must also pass `_sight_clear`.
  - Polygons: candidates `view.front` (with `visible_only`) or every polygon; screen polygon from
    `canvas._poly_screen(view, k)` (skip `None`). Not tolerant: hit when the mean of the screen polygon's
    vertices is within `R`. Tolerant: hit when the polygon contains `c` (`OddEvenFill`), or any vertex is
    within `R`, or any side is within `R` of `c`. With `visible_only`, the world centroid must also pass
    `_sight_clear`.
  - Model mode: the object is `canvas.pick_object(c)`; when that is `None`, the first non-`None` of
    `pick_object` at 16 samples: radius `R/2` then `R`, angles 0, 45, ..., 315 degrees. The object found
    (if any) is applied with the stroke's operation. A `replace` press with no object under the whole brush
    deselects (`select_object(False)`). Parametric objects work (no editable check in Model mode).
- Radius change: Shift+wheel over the canvas while Brush Selection is the tool changes `radius` by
  `round_even(radius * 1.25 ** notches)` with at least 2 px of change per notch, clamped to 2..512, saved
  with `set_option`, the circle redraws at once; the event is consumed (no zoom). `notches =
  angleDelta().y() / 120`. The keys `[` and `]` change it by -2 and +2 (key press consumed only while the
  tool is active and the canvas has focus). Their final bindings belong to the controls contract under the
  action ids `select.brush_smaller` and `select.brush_larger`; until that contract lands, these defaults
  are hard-wired in the filter.
- Hover preview: the circle only.

### 2.6 Loop, Ring and Pattern Selection

Hover (no button down): the hovered element is found on `view` of the active object:
- the hovered edge `e`: in Edges and Points mode `canvas._pick_edge(view, x, y)` (6 px, visible edges);
  in Polygons mode the polygon `k = canvas._pick_polygon(view, x, y)` and `e` = the side of `k` nearest
  to the cursor in screen space;
- in Points mode also the hovered point `p` = the endpoint of `e` nearest to the cursor.

The preview is the set the click would select, drawn by the overlay: edges as 2 px lines in
`theme.SELECT_FRONT_SOFT`; polygons filled with `SELECT_FRONT_SOFT` at alpha 64 and outlined 1 px in
`SELECT_FRONT_SOFT`; points as 6 x 6 px squares in `SELECT_FRONT_SOFT`. Only elements in front of the near
plane are drawn (`canvas.project_world`, skip NaN). The preview is recomputed only when the hovered element
changes (cache key: object id, mesh points bytes, polygons tuple, mode, element, options).

Click (press and release within `DRAG_THRESHOLD` 4 px): applies the previewed set with the press
operation. A click on nothing does nothing (no clearing).

Sets (pure functions in `select_tools.py`):
- `loop_elements(mesh, mode, e, boundary)`:
  - edges: `set(edge_loop(mesh, e))`; when `boundary` and `e` has one face (`edge_faces`), the edges of the
    boundary loop containing `e` (`boundary_loops(mesh)`, consecutive vertex pairs, closed).
  - polygons: `set(polygon_loop(mesh, e))` (the strip that crosses `e`); empty when the hovered polygon is
    not a quad.
  - points: every endpoint of the edges in the edges result.
- `ring_elements(mesh, mode, e, k)`:
  - edges: `set(edge_ring(mesh, e))`.
  - polygons: `set(polygon_loop(mesh, s))` where `s` is the side of quad `k` that follows `e` in the
    polygon's vertex order (the strip parallel to `e`); empty for a non-quad.
  - points: every endpoint of `edge_ring(mesh, e)`.
- `pattern_elements(mesh, mode, e, k, p, count, skip, direction)`: builds an ordered sequence `S` and
  keeps `S[i]` when `(i - i0) % (count + skip) < count` (Python modulo, so it runs both ways from the
  hovered element):
  - edges: `S = edge_loop(mesh, e)` for "Loop", `edge_ring(mesh, e)` for "Ring"; `i0 = S.index(e)`.
  - polygons: `S = polygon_loop(mesh, e)` for "Loop", `polygon_loop(mesh, s)` (as in ring) for "Ring";
    `i0 = S.index(k)`.
  - points: "Loop": the ordered vertex chain of `edge_loop(mesh, e)` (walk the ordered edges, sharing
    endpoints), `i0` its index of `p`; "Ring": `S = edge_ring(mesh, e)` and each kept edge contributes both
    endpoints, `i0 = S.index(e)`.
  On a closed loop whose length is not a multiple of `count + skip` the pattern meets itself unevenly at
  the far side; that is accepted.

### 2.7 Fill Selection (`select_fill`, Polygons mode)

- Borders: `scene.selected_edges` (kept from Edges mode; the scene keeps the three sets separately) plus
  the edges of `region_boundary(mesh, scene.selected_polygons)`.
- `fill_region(mesh, f0, borders, blocked)`: flood from the clicked polygon `f0` to neighbours through
  shared edges (`edge_faces`) that are not in `borders`, never entering `blocked`.
- Click without Ctrl: `blocked = selected_polygons`; the region is added. With no border at all the
  region is the whole connected island of `f0`. A click on an already selected polygon does nothing.
- Ctrl+click on a selected polygon: flood with `borders` = edges only, through selected polygons only
  (`blocked` = unselected polygons), and remove that region.
- Hover preview: the region the click would add or remove (style of 2.6).
- In Points or Edges mode the tool stays chosen, shows no preview, and a click sends
  `"Fill Selection: switch to Polygons mode"` through `controller().message`.

### 2.8 Phong Angle Selection (`select_phong`, Polygons mode)

- `phong_region(mesh, f0, angle)`: breadth-first flood from `f0` across shared edges to a neighbour `g`
  of the current polygon `f` when the angle between `face_normals(mesh)[f]` and `[g]` is
  `<= angle + 1e-9` degrees (neighbour to neighbour, not against `f0`). Normals in object space.
- Click: replace, Shift add, Ctrl remove. Hover preview: the region.
- In Points or Edges mode: as Fill, message `"Phong Angle Selection: switch to Polygons mode"`.

### 2.9 Tool options panel

`class SelectionOptionsPanel(QWidget)` in `select_interaction.py`, a card in the right column, inserted
into `window.manager_splitter` right after the modeling `ToolOptionsPanel` (index 2 when that panel is at
index 1; use `splitter.indexOf(window.tool_options) + 1` when `window.tool_options` exists, else 1),
`setStretchFactor(index, 0)`, `make_card`.
- Visible only while `scene.tool` is a selection tool **with params** (Brush, Loop, Pattern, Phong);
  hidden for Ring and Fill and for every other tool.
- Header: `PanelTabBar([tool.name.upper()])` like `ToolOptionsPanel`, height `CARD_HEADER_H` 28.
- One row per param, `FieldRow(label, editor, label_width=120, indent=14)`: int params a
  `modeling/panel.ScrubIntSpin` with suffix (`" px"` for radius), angle a `ScrubSpin` with suffix
  `" °"`, bool a `QCheckBox`, choice a `QComboBox` passed through `common.prepare_combo`. Row height 24,
  row spacing 4, content margins 8 left/right, 4 top, 8 bottom.
- Last row: a right-aligned `QPushButton("Reset")` height 24 that calls `reset_options`.
- Edits call `set_option` immediately; the panel follows `prefs.changed` for `selection.options` (so the
  Shift+wheel radius change shows in the spin box).

### 2.10 Icons (24-unit grid painters registered at import of `select_tools.py`)

Same style rules as the rail icons (`tool_palette.register_tool_icons`): strokes `theme.ICON_STROKE` at
`theme.ICON_STROKE_W`, exactly one part in `theme.ICON_TOOL` (citrine), painted with
`command_bar.unit_painter`, default colour `theme.ICON_STROKE`.
- `pal_select_loop`: a 3 x 3 grid of rounded squares (grey outlines); the middle row's three squares'
  shared horizontal line drawn as one citrine stroke across the grid.
- `pal_select_ring`: three parallel horizontal grey bars stacked; short citrine vertical ticks crossing all
  three at the centre.
- `pal_select_pattern`: a row of five small grey squares; squares 1, 3 and 5 filled citrine.
- `pal_select_fill`: a grey closed outline (rounded hexagon); its interior filled citrine at full
  opacity, inset 3 units.
- `pal_select_phong`: two grey quads meeting at a fold (a shallow "V" seen from the side); a citrine arc
  between them marking the angle.

### 2.11 Names, HUD and status bar

- `viewport.HUD_TEXTS` and `viewport.TOOL_NAMES` (Viewport builder, static edit): `"select": "Brush
  Selection"`, `"select_loop": "Loop Selection"`, `"select_ring": "Ring Selection"`,
  `"select_pattern": "Pattern Selection"`, `"select_fill": "Fill Selection"`, `"select_phong": "Phong
  Angle Selection"`. The HUD glyph stays the dashed circle (`_paint_tool_glyph` default branch).
- `status_bar.TOOL_NAMES` (Selection builder, static edit): the same six names.
- `status_bar.TOOL_HINTS` (Selection builder, static edit): `("select", "model")` = hint_model of
  `select`, `("select", "components")` = its hint; `(id, "any")` = the hint of each other tool. The
  existing `("select", ...)` entries are replaced.

### 2.12 Tool rail entry

The rail's first button becomes a fold-out group, key `"Selection"` (unchanged, `SCENE_TOOLS` keeps the key
`"Selection"` mapped to `"select"`), shown command Brush Selection, entries in the order Brush Selection,
Loop Selection, Ring Selection, Pattern Selection, Fill Selection, Phong Angle Selection, each mapped to its
scene tool through the `SceneBinding` command map (`SELECT_COMMANDS: dict[str, str]` in
`tool_palette.py`, name to tool id, the same mechanism as `PEN_COMMANDS`). Built by the Palettes builder
from section 7 defaults.

### 2.13 Shortcut suggestions (decided by the controls contract, not here)

Brush Selection `9` (as in `menus_data.SELECT_MENU`), Loop Selection `U~L`, Ring Selection `U~B`, Fill
Selection `U~F`; Pattern and Phong Angle without a default. Today those chords belong to the commands
`loop_selection`, `ring_selection`, `fill_selection`.

### 2.14 Tests: `tests/test_selection_tools.py` (new)

Build `Viewport` (or a `MainWindow`) offscreen, make the default cube editable
(`menu_bar.make_editable`), install `SelectionToolFilter(canvas)`, drive with `QTest`-style mouse events
as `tests/test_viewport3d.py` does (`_mouse`, `_click` helpers can be copied).
1. `scene.TOOLS` contains the five new ids after importing `select_tools`; every icon in the table is
   registered and passes the rail icon check (one citrine part) used by
   `test_tool_palette.test_tool_icons_are_flat_strokes_with_one_citrine_part`.
2. Brush, Points mode, radius 10: a click on a point selects exactly the points within 10 px; a drag across
   the cube adds every point within 10 px of the path; Ctrl drag removes; Shift click adds.
3. Brush `visible_only` on: a dab over the front face never selects back points; off: it does.
4. Brush Polygons mode: not tolerant selects only faces whose screen centroid is inside; tolerant with a
   dab on a face's corner selects the faces touching it.
5. Brush Model mode with a parametric object (e.g. `create_object("sphere")`): painting over it makes it
   active and selected; a `replace` press on empty space deselects.
6. One stroke is one undo step: after a stroke `scene.undo()` restores the previous selection exactly; a
   stroke that changes nothing adds no step.
7. Shift+wheel changes the radius (10 to 12 after one notch up, never below 2), saves it to
   `prefs.get("selection.options")["select"]["radius"]`, and does not change `canvas.camera.distance`.
8. Loop: hovering an edge of a subdivided cube previews the loop (overlay holds the set); the click
   selects `edge_loop`; Polygons mode selects the strip crossing the nearest side; Points mode the loop's
   points.
9. Ring: Edges and Polygons as specified.
10. Pattern: on a 4 x 8 cylinder loop with `count=1, skip=1` every second edge is selected, both
    directions from the hovered edge.
11. Fill: with a closed edge contour selected in Edges mode, a click inside the contour in Polygons mode adds
    the polygons inside; with no contour it adds the whole island; Ctrl removes.
12. Phong: on a cube with `angle=40` a click selects one face; with `angle=90` all six.
13. Choosing Loop in Model mode switches to Edges; Fill in Model mode switches to Polygons.
14. Non-editable active object in Points mode: a click shows `Make Editable first` and changes nothing.
15. The options panel shows for Brush, Loop, Pattern, Phong and hides for Ring, Fill and Move; editing the
    radius spin writes the option; Reset restores 10.
16. Middle drag, Alt+left drag and right click still navigate and open the context menu with a selection
    tool active.

## 3. Splitter handle

### 3.1 Today

`theme.py` lines 808-811:
`QSplitter::handle { background: SURFACE_BACKDROP; }`, width/height `CARD_GAP` 8, and
`QSplitter::handle:hover, QSplitter::handle:pressed { background: ACCENT_TINT_BACKDROP; }`. The "green
rectangle" is the whole 8 px gap painted `ACCENT_TINT_BACKDROP` (`mix(ACCENT, SURFACE_BACKDROP, 0.18)`)
along the full handle length with square ends, on hover and while dragging. `main_window.py` sets
`setHandleWidth(theme.CARD_GAP)` on `body_splitter` (line 230) and `manager_splitter` (line 256);
`opaqueResize()` is `True` (no rubber band). The QSS approach cannot shrink the painted bar: margins on
`::handle` enlarge the handle (measured: margins 3 x 24 grew a handle to 62 px).

### 3.2 New handle: `quartz_studio/widgets/splitter.py` (new)

```python
class StudioSplitter(QSplitter):
    def createHandle(self) -> QSplitterHandle

class StudioSplitterHandle(QSplitterHandle):
    def state(self) -> str
```

- `StudioSplitter(orientation, parent)` calls `setHandleWidth(theme.CARD_GAP)` (8) and
  `setChildrenCollapsible(False)` itself. The gap between cards stays 8 px (the smoke test's gap checks
  stay valid).
- `StudioSplitterHandle` sets `setAttribute(WA_Hover, True)` and `setMouseTracking(True)`, keeps the
  inherited resize cursors, and overrides `paintEvent` (no `super()` call, so the QSS rule is never drawn).
- States: `"idle"` (no hover, not pressed), `"hover"` (`underMouse()`), `"drag"` (left button pressed on
  it until release); `state()` returns the current one; `enterEvent`, `leaveEvent`, `mousePressEvent`,
  `mouseReleaseEvent` update it, call `super()` and `update()`.
- Painting: idle paints nothing (the backdrop shows through). Hover and drag paint one rounded bar:
  - thickness `SPLITTER_BAR` 4 px across the gap, centred (2 px clear on each side of an 8 px handle);
  - length: the handle length minus `SPLITTER_BAR_INSET` 24 px at each end; when the handle is shorter
    than 80 px, minus 8 px at each end;
  - radius 2 (fully rounded ends), antialiased, no pen;
  - colour `theme.SPLITTER_HOVER` on hover, `theme.SPLITTER_DRAG` while dragging.
- A disabled handle (`setEnabled(False)`) never paints and shows the arrow cursor.

New tokens (Layout builder, `theme.py`): `SPLITTER_BAR = 4`, `SPLITTER_BAR_INSET = 24`,
`SPLITTER_HOVER = mix(ACCENT, SURFACE_BACKDROP, 0.5)`, `SPLITTER_DRAG = ACCENT`. The QSS lines 808-811
become `QSplitter::handle { background: transparent; }` (width and height rules kept).

`main_window.py` builds `body_splitter` and `manager_splitter` (and any splitter the hooks fleet adds, such
as `bottom_splitter` and `left_dock_column`) as `StudioSplitter`. The handle above Coordinates is disabled
(section 4.3).

### 3.3 Tests (in `tests/test_layout_chrome.py`, new)

1. `body_splitter` and `manager_splitter` are `StudioSplitter`; `handleWidth()` is 8.
2. A handle grabbed in each state (force the state through the event handlers: send `QEvent.Enter`, a
   left press, a release, `QEvent.Leave`): idle has no pixel different from `SURFACE_BACKDROP`; hover has
   `SPLITTER_HOVER` pixels only in the centre 4 px band and only between 24 px from each end; drag uses
   `SPLITTER_DRAG`; the corner pixels of the bar's end are blended (rounded), not full colour.
3. Dragging a handle with the mouse still resizes the neighbouring cards.

## 4. Coordinates card: fixed minimal height

### 4.1 Today (measured offscreen at 1920 x 1040)

`CoordinatesManager` (`widgets/coordinates.py`) is 127 px tall: top margin 4, header 24, spacing 2,
`HeaderRule` 1, spacing 2, grid 86 (titles 14, then three rows of 22 px because the global QSS `min-height`
of `QLineEdit` overrides `CoordField.setFixedHeight(ROW_H=20)`, grid spacing 2), bottom margin 8. Its
size policy is vertical `Preferred` with a stretch item at the bottom, so dragging the splitter handle above
it makes it taller. `MIN_H` (line 50) computes 121, which no longer matches the real 127.

### 4.2 New layout (exact, total 120 px)

| Part | px |
|---|---|
| top content margin (includes the card's 1 px border) | 4 |
| header row (title, Reset Transformation); its bottom 1 px row is the hairline | 24 |
| layout spacing | 4 |
| column titles row (Position, Rotation, Size) | 14 |
| grid spacing | 2 |
| X row | 20 |
| grid spacing | 2 |
| Y row | 20 |
| grid spacing | 2 |
| Z row | 20 |
| bottom content margin | 8 |
| **total** | **120** |

- `theme.COORDINATES_H = 120`. `coordinates.MIN_H = theme.COORDINATES_H` (the name stays for the test).
- `CoordinatesManager.setFixedHeight(theme.COORDINATES_H)`, size policy `(Expanding, Fixed)`,
  `setMinimumWidth(256)` (was 260). `minimumSizeHint` and `sizeHint` return height 120.
- Content margins `(8, 4, 8, 8)`, layout spacing 4, no stretch item.
- Header: a small `QWidget` subclass of fixed height 24 that paints a 1 px `theme.HAIRLINE` line on its
  last row (y = 23) across its full width; the separate `HeaderRule` item is removed. Title label as today
  (`qsCoordHeader`, left padding `HEADER_PAD` 10). Reset button height 20, width
  `max(128, theme.snap_up(sizeHint().width()))` (section 8.2 helper; today's hint 138 gives 144),
  vertically at y 2.
- Grid: vertical spacing 2, horizontal spacing 6, axis column 14; titles `setFixedHeight(14)`; fields
  `setFixedHeight(20)` plus the local style rule
  `QLineEdit#qsCoordField { min-height: 16px; padding: 1px 6px; }` so the real height is 20.
- Width follows the right column (the column decides; the card never sets a maximum width).

### 4.3 Splitter and default sizes

- `MainWindow.apply_default_sizes` uses `coord_h = theme.COORDINATES_H` (drop `COORD_RATIO` and the 60
  floor).
- The handle directly above Coordinates
  (`manager_splitter.handle(manager_splitter.indexOf(self.coordinates))`) is `setEnabled(False)`:
  nothing to drag there, so it never highlights.
- Dragging any other handle or resizing the window never changes the Coordinates height.

### 4.4 Tests

- `tests/test_coordinates.py::test_main_window_coordinates_not_clipped`: change to
  `cm.height() == MIN_H == 120`.
- New in `tests/test_layout_chrome.py`: height 120 at 1920 x 1007 and at 1280 x 720; after
  `manager_splitter.moveSplitter(y - 80, index_of_attribute_manager + 1)` and after resizing the window to
  1920 x 1300 it is still 120; its width equals the column width; the grid rows are at y 48, 70, 92 with
  height 20 (relative to the card); the last field's bottom is 112; the handle above it is disabled.

## 5. Scene display filter

### 5.1 Placement

- Viewport header (`widgets/viewport.py`, `VIEWPORT_MENUS` line 90): two new ghost menus after Cameras,
  titles `"Display"` and `"Filter"` (Cinema 4D's names). `ViewportMenuBar.menu_titles()` becomes
  `["View", "Cameras", "Display", "Filter"]`.
- Main menu: `Window` gets two submenus at its top, `"Display"` and `"Filter"`, with the same entries and
  handlers, followed by a separator (integration step, `menus_data.WINDOW_MENU`).

### 5.2 State: `quartz_studio/widgets/display_filter.py` (new)

```python
SHADINGS: tuple[tuple[str, str], ...] = (
    ("shaded_lines", "Shaded (Lines)"),
    ("shaded", "Shaded"),
    ("hidden_line", "Hidden Line"),
    ("wireframe", "Wireframe"),
)
TOGGLES: tuple[tuple[str, str], ...] = (
    ("ngon_lines", "N-gon Lines"),
    ("points", "Points"),
    ("line_objects", "Line Objects"),
    ("null_objects", "Null Objects"),
    ("horizon", "Horizon"),
    ("world_axis", "World Axis"),
    ("axis_triad", "Axis Triad"),
    ("gizmo", "Gizmo"),
    ("hud", "HUD"),
    ("selection_outline", "Selection Outline"),
    ("backface_selection", "Back-face Selection Colour"),
)
PREF_KEY = "viewport.display"

@dataclass
class DisplayFilter:
    shading: str = "shaded_lines"
    ngon_lines: bool = True
    points: bool = True
    line_objects: bool = True
    null_objects: bool = True
    horizon: bool = True
    world_axis: bool = True
    axis_triad: bool = True
    gizmo: bool = True
    hud: bool = True
    selection_outline: bool = True
    backface_selection: bool = True

def load() -> DisplayFilter
def save(state: DisplayFilter) -> None
def set_shading(key: str) -> None
def toggle(key: str) -> None
def reset() -> None
def menu_entries() -> tuple[list, list]
def menu_commands() -> list[tuple[tuple[str, ...], Callable[[], None]]]
def menu_checks() -> dict[tuple[str, ...], Callable[[], bool]]
```

- `load()` reads `prefs.get(PREF_KEY, {})`; unknown fields ignored; a wrong type or unknown shading falls
  back to the default for that field.
- `save` writes all fields with `prefs.set(PREF_KEY, asdict(state))`; `reset()` is
  `prefs.set(PREF_KEY, None)`.
- `set_shading(key)` and `toggle(key)` load, change, save.
- State is a per-user preference shared by every window and canvas; it is not stored in `.quartz` files
  and not in the view history.
- `menu_entries()` returns the two entry lists for `build_view_menu`: Display: one `("check", label,
  default)` per shading. Filter: the toggles in the table order with `("sep",)` after Null Objects, after
  Axis Triad and after Back-face Selection Colour, then `("item", "Reset Display")`.
- `menu_commands()` returns the main menu paths `("Window", "Display", label)` and
  `("Window", "Filter", label)` with their handlers; `menu_checks()` returns the same paths mapped to
  functions that report the current check state (used by the integration step, section 9.3).

### 5.3 Canvas wiring (Viewport builder)

- `ViewportCanvas.display: DisplayFilter`, loaded in `__init__`; `prefs.changed` with `PREF_KEY` reloads it
  and calls `update()`; `ViewportMenuBar` re-syncs its checks.
- `ViewportMenuBar._bind_menus` rewires Display items to `set_shading`, Filter items to `toggle` and
  Reset Display to `reset`, the shading actions in an exclusive `QActionGroup` (like `_view_group`), and
  syncs `qs_check` from `canvas.display` on every change.

### 5.4 What each entry gates (all in `widgets/viewport.py`)

| Key | Off means | Code it gates |
|---|---|---|
| `ngon_lines` | no accent N-gon guide lines | `_paint_scene`, the block `if len(mesh.polygons[k]) > 4:` that appends `("line", line, guide_pen)` from `ngon_guides` (~1492-1495) |
| `points` | no point squares in Points mode (picking still works) | `_paint_overlays`, the points branch after `if mode == "edges"` (~1673-1687) |
| `line_objects` | loose edges (Line objects, splines) not drawn and not pickable | `items.extend(self._loose_edge_items(...))` (~1496) and the loose-edge loop in `pick_object` (~1015-1023) |
| `null_objects` | nulls not drawn | `items.extend(self._null_items(...))` (~1497-1498) |
| `horizon` | no horizon line | `self._paint_horizon(p, inner)` in `paintEvent` (~1269) |
| `world_axis` | no world axis arrows at the origin | `items.extend(self._world_axis_items(len(items)))` (~1502) |
| `axis_triad` | no X/Y/Z triad in the top right corner | `self._paint_gizmo(p, inner)` in `paintEvent` (~1275) |
| `gizmo` | no Move/Rotate/Scale gizmo, and the gizmo is not pickable (clicks select through it) | `self._paint_tool_gizmo(p)` (~1271); `gizmo_pick` returns `None` |
| `hud` | the tool pill at the bottom left is not drawn (the view name and the camera plate stay) | the HUD part of `_paint_texts` (~1932-1941); `hud_rect` keeps its value so the dock placement does not jump |
| `selection_outline` | no citrine contour of the selected object in Model mode | `_paint_overlays`, `if mode == "model":` block (~1645-1652) |
| `backface_selection` | selected polygons seen from behind use the front colours (citrine) instead of amethyst | `_paint_scene`, the `else:` branch that appends `("selected", poly, back_fill, back_pen)` (~1490-1491) |

Shading (in `_paint_scene`, the `"poly"` items and their drawing loop ~1476-1520):

| Key | Fill | Polygon outline |
|---|---|---|
| `shaded_lines` (default, today) | `_shade(lam)` | `outline` pen (`theme.POLY_OUTLINE`, 1 px): the "black lines" |
| `shaded` | `_shade(lam)` | a 1 px pen of the fill colour itself (hides the lines without antialiasing cracks) |
| `hidden_line` | `theme.SURFACE_CARD` | 1 px `theme.WIRE` |
| `wireframe` | none: no `"poly"` items at all | every `mesh.edge` of every rendered object as a `("line", ...)` item, 1 px `theme.WIRE` at alpha 160, near-clipped with `_edge_lines`, depth = mean depth of its two ends; back edges included |

Selected-polygon fills, N-gon lines, overlays, nulls and loose edges are drawn the same way in every shading.

### 5.5 Tests: `tests/test_display_filter.py` (new)

1. Defaults equal today's look: an image of the default cube with an empty profile equals the image
   rendered before the change (use `test_viewport_draw.test_default_cube_matches_shading_formula` as is;
   it must keep passing).
2. `toggle("ngon_lines")` on a mesh with a pentagon removes every `theme.ACCENT` pixel inside the polygon.
3. Each toggle in 5.4 removes its marks: horizon row pixels become background; triad corner has no axis
   colours; Move gizmo handles absent and `gizmo_pick` is `None`; HUD pill area equals background;
   Model-mode outline absent; back-face selected polygon is citrine.
4. `shaded` has no `POLY_OUTLINE` pixels on the cube's edges; `wireframe` shows the background colour at the
   centre of a front face and `WIRE` pixels on the back edges; `hidden_line` fills with `SURFACE_CARD`.
5. Menu: `menu_titles()` is `["View", "Cameras", "Display", "Filter"]`; triggering Filter > Horizon flips
   `canvas.display.horizon` and `prefs.get("viewport.display")["horizon"]`; Display items are exclusive;
   Reset Display restores all defaults.
6. A second `Viewport` created after a change starts with the changed state (preference persistence).

Existing test to update: `tests/test_viewport_draw.py::test_header_is_overlaid_inside_the_canvas` (line
523, the titles list).

## 6. Unlimited zoom

### 6.1 Every clamp today (`widgets/viewport.py`)

| Line (about) | Code | Effect |
|---|---|---|
| 259-260 | `MIN_DISTANCE = 2.0`, `MAX_DISTANCE = 1.0e6` | orbit distance and ortho scale bounds |
| 261 | `MIN_APPROACH = 5.0` | wheel and Alt+RMB stop 5 cm before the point under the cursor |
| 262 | `NAV_MIN_DEPTH = 100.0` | empty-space pivot depth, carry floor, camera-pivot step |
| 266 | `MIN_FRAME_RADIUS = 25.0` | Frame never gets closer than a 25 cm sphere |
| 299 | `near: float = 1.0` | fixed 1 cm near plane: anything nearer to the eye is clipped |
| 385 | `OrbitCamera.dolly`: `max(MIN_DISTANCE, min(MAX_DISTANCE, ...))` | dolly bounds |
| 909 | `cursor_point`: `max(eye_distance, NAV_MIN_DEPTH)` | empty-space point depth |
| 2103 | camera pivot zoom step `max(cam.distance, NAV_MIN_DEPTH)` | step size |
| 2113-2114 | ortho: factor clamped to `[MIN_DISTANCE/d, MAX_DISTANCE/d]` | ortho zoom bounds |
| 2120-2124 | perspective: factor clamped with `MIN_APPROACH/reach` and `MAX_DISTANCE/reach` | approach and retreat bounds |
| 2129-2131 | distance floor `min(cam.distance, NAV_MIN_DEPTH)` and `[MIN_DISTANCE, MAX_DISTANCE]` | target carry and bounds |
| 2221, 2231 | `frame_points`: `MIN_FRAME_RADIUS` and the distance clamp | Frame bounds |

There is no far plane (painter's algorithm, no depth buffer) and no field-of-view clamp (`focal` is fixed
at `LENS_MM / FILM_MM`); `ORTHO_BACK = 1e5` is an eye offset, not a limit. `PITCH_LIMIT` is orbit, not
zoom. The small guards `1e-9` and `1e-6` in `px_size`, `cam_to_screen`, `pan` and `ray` stay.

### 6.2 New constants (replace `MIN_DISTANCE`, `MAX_DISTANCE`, `MIN_APPROACH`, `NAV_MIN_DEPTH`)

```python
REACH_FLOOR = 1.0e-6
REACH_FLOOR_REL = 1.0e-12
REACH_CEIL = 1.0e15
CARRY_RATIO = 0.5
EMPTY_CARRY = 100.0
NEAR_DEFAULT = 1.0
NEAR_RATIO = 1.0e-3
NEAR_FLOOR = 1.0e-9
SCREEN_GUARD = 4096.0
```

`reach_floor(point) = max(REACH_FLOOR, REACH_FLOOR_REL * norm(point))`. These two are numeric floors and
the ceiling a numeric guard (1e-6 cm is a hundredth of a micron; 1e15 cm is ten billion km), not zoom
limits: 0.88 per notch reaches the floor after more than 160 notches from the default view.

`ViewportCanvas.carry_depth() -> float`: `CARRY_RATIO * radius` of the rendered scene's bounds
(`scene.world_bounds()`, radius `norm(hi - lo) / 2`), at least `REACH_FLOOR`; `EMPTY_CARRY` when the
scene has no points. (Default cube: 86.6; it replaces the absolute 100.)

### 6.3 Rules

- Perspective zoom about a point `P` with factor `f` (wheel: `WHEEL_STEP ** notches`, 0.88 per notch;
  Alt+RMB: `exp(-(dx - dy) * DOLLY_SPEED)`), in `_scale_view(point, factor)`:
  1. `reach = norm(eye - P)`; return when `reach <= 1e-300`.
  2. `new_reach = clamp(reach * f, reach_floor(P), REACH_CEIL)`; `f = new_reach / reach`.
  3. `new_eye = P + (eye - P) * f`.
  4. `distance = cam.distance * f`; when `f < 1`: `distance = max(distance, min(cam.distance,
     self.carry_depth()))` (the orbit target is carried forward instead of collapsing, so the camera
     passes through the old target and never stalls); then `distance = clamp(distance, REACH_FLOOR,
     REACH_CEIL)`.
  5. `cam.target = new_eye + fwd * distance`; `cam.near = clamp(NEAR_RATIO * new_reach, NEAR_FLOOR,
     NEAR_DEFAULT)`.
  The point under the cursor stays under the cursor (unchanged property). Zooming toward a surface point
  approaches it geometrically without limit and never passes through it.
- Empty space (wheel with no hit): `cursor_point` uses `max(eye_distance, carry_depth())` instead of
  `NAV_MIN_DEPTH`. Each notch then moves the eye by 12 percent of at least the carry depth, so flying
  through empty space never stalls and has no absolute step.
- Camera navigation pivot (`Cameras > Navigation > Camera`): step `(1 - f) * max(cam.distance,
  self.carry_depth())`.
- Orthographic: `cam.distance` is the zoom scale: `new = clamp(cam.distance * f, REACH_FLOOR,
  REACH_CEIL)`, then `scale_about(P, new / cam.distance)`; `near` untouched.
- `OrbitCamera.dolly(factor)`: `distance = clamp(distance * factor, REACH_FLOOR, REACH_CEIL)`.
- `frame_points`: `radius = norm(hi - lo) / 2 * FRAME_MARGIN` when the extent is above `REACH_FLOOR`,
  else `MIN_FRAME_RADIUS * FRAME_MARGIN` (a single point); distance clamped to `[REACH_FLOOR,
  REACH_CEIL]`; `near = clamp(NEAR_RATIO * distance, NEAR_FLOOR, NEAR_DEFAULT)`.
- `reset_camera` and the view presets give `near = NEAR_DEFAULT` (fresh `OrbitCamera`); `near` stays a
  dataclass field (copied by `copy()`, not part of `state()`).
- Screen guard against numeric breakdown: very close geometry projects to coordinates in the millions of
  pixels, which overflow Qt's raster fixed point. Every polygon and line handed to `QPainter` is clipped
  in screen space to the canvas rectangle grown by `SCREEN_GUARD` px on each side: polygons with
  Sutherland-Hodgman in `_poly_screen` (only when a vertex is outside the guard; picking keeps using the
  unclipped polygon), segments with Liang-Barsky in `_edge_lines`, `_edge_screen`,
  `_visible_edge_lines`, `_loose_edge_items`, `_world_axis_items` and `_null_items` (a segment fully
  outside is dropped). The fast path (all inside) adds no work.

### 6.4 Tests

New `tests/test_zoom_unlimited.py` (helpers from `tests/test_camera.py`):
1. 200 wheel notches toward the front face: reach decreases every notch until it equals
   `reach_floor(point)` and then stays there, ends below `1e-4` (old limit 5), the point stays under the
   cursor within 1e-3 px, depth stays positive, no NaN in `camera.state()`, and `canvas.grab()` renders
   the face colour at the cursor.
2. 200 notches out over the cube face: distance above `1e12` and below `REACH_CEIL`, no NaN, finite
   projections; 200 notches back in over the same spot return the distance within 1e-6 relative of the
   start.
3. Empty space: 60 notches with the far cube of `test_camera._far_cube` never move the eye less than
   0.5 cm per notch and keep `camera.distance >= canvas.carry_depth() - 1e-9`.
4. Alt+RMB drag of 2000 px toward a point: reach above `reach_floor` and below 1e-3, no exception.
5. Ortho (Front view): 150 notches in give `distance < 1e-4`, 150 out give `> 1e9`.
6. `frame_points` on a 1 mm cube gives `distance < 1` and the cube fills the view (projected width above
   half the film width).
7. Near plane follows: after zooming to reach 1e-3, `camera.near <= 1e-6`; after `reset_camera`, 1.0.
8. Screen guard: a polygon with a vertex 1e9 px off screen draws without exception and its visible part is
   painted.

Existing tests to update (`tests/test_camera.py`):
- `test_wheel_never_passes_through_the_point` (line 245): drop `MIN_APPROACH`; assert the reach after 80
  notches is below `1618 * 0.88 ** 79` and above `reach_floor`, depth positive, point under the cursor.
- `test_wheel_zoom_never_stalls_on_a_close_target` (line 610): replace `NAV_MIN_DEPTH` with
  `canvas.carry_depth()` and `MIN_APPROACH` with the geometric bound of case 1.
- `test_wheel_zoom_keeps_point_under_mouse` and `test_alt_rmb_dolly_moves_toward_the_pivot` keep
  passing unchanged (default distance 1618 is far above the carry depth).
- `tests/test_gizmo_transform.py` and `tests/test_viewport3d.py` calls to `camera.dolly(0.5)` and
  `dolly(2.0)` keep working.

## 7. Palette customisation

### 7.1 Today

- Tool rail (`widgets/tool_palette.py`): `TOOL_PALETTE_ENTRIES` (lines 170-184) = Selection, GAP, Move,
  GAP, Rotate, GAP, Scale, GAP, Pen group (`Item(_PEN, foldout=[Polygon Pen, Pen])`, shown command Pen),
  FLEX; `ToolPalette.__init__` (324-392) appends a `_Divider` and `modeling_entries(groups)` (283-291):
  one checkable fold-out `Item` per `modeling.install.palette_groups()` group (from `PALETTE_GROUPS`,
  `install.py` 26-38, plus `MORE_GROUP` "More"), GAP between groups. `SceneBinding` (`command_bar.py`
  633-711) maps the transform buttons to scene tools (`SCENE_TOOLS`, `PEN_COMMANDS`); modeling entries run
  `install.activate_tool` through `FoldoutButton.set_command_action`. The strip lives in a `QScrollArea`
  with arrows (`_fit`).
- Object dock (`widgets/object_palette.py`): `_build_palette()` (190-208) = FLEX, Line, Null, GAP, five
  shape groups, GAP, three generator groups, FLEX, from `PALETTE_GROUPS` (156-166) and
  `SHAPE_GROUP_COUNT`; GAP becomes `_DockDivider`; each entry runs `create_object(spec_id)`,
  `create_line` or `create_empty_polygon` via `CREATE_COMMANDS`. `ObjectPalette` is itself a
  `PaletteStrip`, horizontal and floating (painted pill) or vertical.
- Group buttons (`widgets/common.py` `IconButton` 219-384, `command_bar.FoldoutButton` 377-511): a
  click runs the shown entry; press and hold `IconButton.HOLD_MS` = 380 ms opens the fold-out; a press in
  the corner zone (`_in_triangle`: the bottom right `max(7, width // 3)` px square, where the group mark is
  drawn) opens it at once; choosing an entry makes it the shown entry for the session.
- `PaletteStrip` (`command_bar.py` 531-630) builds its widgets once in `__init__`; there is no way to
  rebuild.

### 7.2 Module `quartz_studio/palettes.py` (new)

```python
TOOLS = "tools"
OBJECTS = "objects"
PALETTE_IDS = (TOOLS, OBJECTS)
RAIL_POSITIONS = ("left", "right")
DOCK_POSITIONS = ("bottom", "top", "rail_left", "rail_right")
DIVIDER = "divider"
MORE = "More"

@dataclass(frozen=True)
class PaletteAction:
    id: str
    label: str
    icon: str
    color: str | None
    kind: str
    scene_tool: str | None
    run: Callable[[], None] | None
    tooltip: str

def actions(palette_id: str) -> dict[str, PaletteAction]
def default_layout(palette_id: str) -> dict
def load(palette_id: str) -> dict
def save(palette_id: str, layout: dict) -> None
def reset(palette_id: str) -> None
def reset_all() -> None
def position(palette_id: str) -> str
def set_position(palette_id: str, value: str) -> None
def strip_entries(palette_id: str, layout: dict, orientation) -> list
def editing() -> bool
def set_editing(on: bool) -> None
editingChanged: Signal(bool)
def menu_commands() -> list[tuple[tuple[str, ...], Callable[[], None]]]
def menu_checks() -> dict[tuple[str, ...], Callable[[], bool]]
def move_entry(layout, src: int, dst: int) -> dict
def condense(layout, src: int, target: int) -> dict
def take_out(layout, group: int, item: int, dst: int) -> dict
def move_in_group(layout, group: int, item: int, dst: int) -> dict
def remove_entry(layout, index: int) -> dict
def remove_from_group(layout, group: int, item: int) -> dict
def set_default(layout, group: int, item: int) -> dict
def ungroup(layout, index: int) -> dict
def insert_action(layout, action_id: str, dst: int) -> dict
def insert_divider(layout, dst: int) -> dict
```

`editingChanged` is the bound signal of a module-level `QObject` (same pattern as `prefs.changed`).

Action ids and kinds (`actions(palette_id)`, built lazily on first call, cached):
- Tool palette:
  - `kind="scene_tool"`: `tool.select` (Brush Selection, `pal_live_selection`), `tool.select_loop`,
    `tool.select_ring`, `tool.select_pattern`, `tool.select_fill`, `tool.select_phong` (names and icons
    from `select_tools.TOOLS`), `tool.move` (Move, `pal_move`), `tool.rotate` (Rotate, `pal_rotate`),
    `tool.scale` (Scale, `pal_scale`), `tool.pen` (Polygon Pen, `polygon_pen`), `tool.line_pen` (Pen,
    `pal_pen`); `scene_tool` is the part after `tool.`; `run` is `None`; tooltip the label.
  - `kind="mesh_tool"`: `mesh.<id>` for every modeling tool with `menu == install.PALETTE_MENU` ("Mesh"),
    label `spec.name`, icon `icons.modeling_icon_name(id)`, `run = partial(install.activate_tool, id)`,
    tooltip `install.tool_tooltip(spec)`.
- Object dock, `kind="create"`: `create.line` (Line, `m_line`, `menu_bar.create_line`),
  `create.empty_polygon` (Empty Polygon, `empty_polygon`, colour `theme.ICON_MESH`,
  `create_empty_polygon`), and `create.<spec_id>` for every `objects.SPECS` entry (label `spec.label`,
  icon and colour exactly as `object_palette._spec_entry` computes them, `run = partial(create_object,
  spec.id)`).
- A palette accepts only its own actions. Labels are unique within a palette (the fold-out code keys
  commands by label); if two ever collide, the later one gets the suffix `" 2"`.

### 7.3 Layout data (stored in prefs `palette.tools` and `palette.objects`)

```json
{
  "position": "left",
  "entries": [
    {"group": "Selection", "items": ["tool.select", "tool.select_loop", "tool.select_ring",
     "tool.select_pattern", "tool.select_fill", "tool.select_phong"], "default": "tool.select"},
    {"item": "tool.move"},
    {"item": "tool.rotate"},
    {"item": "tool.scale"},
    {"group": "Pen", "items": ["tool.pen", "tool.line_pen"], "default": "tool.line_pen"},
    "divider",
    {"group": "Extrude", "items": ["mesh.extrude", "mesh.inset"], "default": "mesh.extrude"}
  ],
  "known": ["tool.select", "tool.move"]
}
```

- `entries` is an ordered list of: `{"item": id}` (a single button), `{"group": name, "items": [ids],
  "default": id}` (a fold-out button), or the string `"divider"`.
- Spacing is not stored: in the tool rail a GAP (`TOOL_GAP`, the shrinking gap of `_fit`) goes between
  every two consecutive buttons and none next to a divider (exactly today's rail); `"divider"` is the rail
  `_Divider` hairline. In the dock buttons touch as today and `"divider"` is `_DockDivider`.
- Button keys (`PaletteStrip.buttons`): a group's `group` name; a single item's action label. Group names
  are unique within a palette; a new group made by condensing takes the label of the target's default
  action, suffixed `" 2"`, `" 3"` when taken.
- `default` must be one of `items`; otherwise `items[0]`.
- `known` lists every action id the palette offered when the layout was saved.
- Default layouts (`default_layout`), equal to today's palettes:
  - tools: position `left`; Selection group (section 2.12), Move, Rotate, Scale, Pen group as above, a
    divider, then one group per `install.palette_groups()` group in order (name = group name, items =
    `mesh.<spec.id>` in order, default = first; a group of one item is still a group entry, shown without
    a fold-out, like Bevel today).
  - objects: position `bottom`; `{"item": "create.line"}`, `{"item": "create.null"}`, a divider, the
    first `SHAPE_GROUP_COUNT` groups of `object_palette.PALETTE_GROUPS`, a divider, the rest (ids missing
    from `objects.SPECS` skipped, empty groups skipped, as `_build_palette` does).
- `load(palette_id)`: `prefs.get("palette." + palette_id)`; when absent or not a dict, the default.
  Otherwise sanitised: unknown action ids and ids of the other palette dropped; an id used twice keeps the
  first use; groups left empty dropped; two dividers in a row collapse to one, leading and trailing
  dividers dropped; bad `position` becomes the default position. Actions offered now but missing from
  `known` (new since the save) are appended to the group `"More"` at the end (created when missing), so
  new tools appear without wiping the owner's layout.
- `save` writes the sanitised layout with the current `known`. `reset(id)` and `reset_all()` remove the
  keys (`prefs.set(key, None)`).
- `position(id)` reads the layout's position; `set_position` saves it (other fields unchanged).
- The pure edit functions return a new sanitised layout and never mutate their input. Indexes are positions
  in `entries` (dividers count). `condense(src, target)`: the target becomes a group (if it was a single,
  its action is the default) and gets the source's action(s) appended (a group source merges all of its
  items; the target's default is kept); the source entry is removed. `take_out(group, item, dst)` removes
  the item from the group and inserts it as a single at `dst` (a group left with one item stays a group of
  one). `ungroup(index)` replaces a group by its items as singles, default first. `insert_action` refuses
  (returns the layout unchanged) an id already present.

### 7.4 Building the palettes (`tool_palette.py`, `object_palette.py`, `command_bar.py`)

- `PaletteStrip.set_entries(entries)` (new): removes and deletes every child widget, spacer, segment and
  button group, clears `buttons`, `gears`, `segments`, `button_groups`, then adds `entries` with `_add`
  and `_sync_segments`. The constructor calls it.
- `palettes.strip_entries(palette_id, layout, orientation)` turns a layout into `PaletteStrip` entries:
  groups become `Item(Cmd(default), foldout=[Cmd(each item)], key=name)`, singles
  `Item(Cmd(action), key=label)`; tool palette items are `checkable=True, exclusive=TOOLS`; `Cmd(label,
  icon, color)`; spacing and dividers per 7.3; a leading and trailing `FLEX` for the dock, a trailing
  `FLEX` for the rail.
- `ToolPalette.rebuild()` and `ObjectPalette.rebuild()` (new) load the layout, call `set_entries`, and
  rewire: create actions through `set_command_action(label, run)`; mesh tools as today (`_modeling[id] =
  (button, label, spec.interactive)`, tooltips); scene tools through a new `SceneBinding` whose values are
  `{button: scene tool of its default, or OTHER_TOOL}` and whose command map is `{button: {label: scene
  tool or OTHER_TOOL}}` for every button that holds at least one scene tool (`inert=(OTHER_TOOL,)`).
  `self.buttons`, `button_groups`, `segments`, `gears`, `_gap_items` are refreshed; `_fit()` runs. Both
  palettes rebuild on `prefs.changed` for their key and on `palettes.editingChanged`.
- Module constants stay importable with today's values for the tests: `TOOL_PALETTE_ENTRIES`,
  `SCENE_TOOLS` (`{"Selection": "select", "Move": "move", "Rotate": "rotate", "Scale": "scale", "Pen":
  "line_pen"}`), `OTHER_TOOL`, `PEN_KEY`, `PEN_COMMANDS`, `modeling_entries`, `OBJECT_PALETTE_ENTRIES`,
  `CREATE_COMMANDS`, `PALETTE_GROUPS`, `SHAPE_GROUP_COUNT`; `TOOL_PALETTE_ENTRIES[0]` becomes the Selection
  group item. New: `SELECT_COMMANDS = {"Brush Selection": "select", "Loop Selection": "select_loop",
  "Ring Selection": "select_ring", "Pattern Selection": "select_pattern", "Fill Selection":
  "select_fill", "Phong Angle Selection": "select_phong"}`.
- `ToolPalette.set_side(side)` (new, `"left"` or `"right"`): sets every button's popup side to `"right"`
  or `"left"` and re-applies `confine_popup` with the shift mirrored. `ObjectPalette` already takes
  `orientation` and `popup_side`.

### 7.5 Group buttons outside edit mode

Unchanged: click runs the shown entry; press and hold 380 ms (`IconButton.HOLD_MS`) or a press on the
corner mark opens the fold-out; the chosen entry becomes the shown one until the palette is rebuilt or the
app restarts (it is not saved; the saved `default` changes only through edit mode).

### 7.6 Edit mode

Entered and left with "Customize Palettes" (main menu Edit, a check item) or "Customize Palette" (palette
context menu, a check item); Esc anywhere in the main window leaves it (an application event filter
installed only while editing). Edit mode is one global state for both palettes (`palettes.editing()`).

While editing:
- Buttons do not run anything: an event filter on every palette button consumes mouse press, move,
  release and double-click (so the hold timer never starts).
- Look: the tool rail card border becomes 1 px dashed `theme.ACCENT` (local style rule on
  `#qsToolPalette[qsEditing="true"]`); the floating dock paints its pill border 1 px dashed `ACCENT`; a
  rail dock uses the same rule as the tool rail. The scroll arrows keep working.
- Drag: pressing a button and moving at least `QApplication.startDragDistance()` starts a `QDrag` with a
  36 x 36 pixmap of the button and MIME type `application/x-quartz-palette` holding UTF-8 JSON
  `{"palette": id, "source": "entry"|"group_item"|"catalog", "index": int, "item": int|null,
  "action": id}`. Both palettes accept drops (`setAcceptDrops`) only for their own `palette` value.
- Drop resolution on a palette, along its main axis: if the cursor is inside a button and inside its central
  zone (the button rectangle shrunk by 9 px on each side, the inner 18 x 18 of 36) and the button is not
  the source, the drop condenses into that button (`condense`, or for catalog drops: insert, then
  condense); otherwise it inserts at the index equal to the number of entries whose centre is before the
  cursor (`move_entry`, `take_out`, or `insert_action`). A drop outside every palette (`QDrag.exec`
  returning `IgnoreAction`) of an `entry` or `group_item` removes it (`remove_entry`,
  `remove_from_group`).
- Drop feedback while dragging over a palette: an insertion bar 2 px thick across the cross axis, 28 px
  long (button 36 minus 4 at each end), radius 1, `theme.ACCENT`, centred in the gap at the insertion
  index; a condense target gets a 2 px `ACCENT` rounded outline (radius `CONTROL_RADIUS` 6) instead.
- Click on a group button opens `GroupEditPopup`: a frameless popup (`Qt.Popup`, `prepare_popup` look:
  `SURFACE_MENU`, 1 px `HAIRLINE`, radius `MENU_RADIUS` 8, padding 4, gap 4) with one 36 x 36 button per
  item, in a row for a vertical palette (opening right of a left rail, left of a right rail) and in a
  column for a horizontal dock (opening above a bottom dock, below a top dock), kept inside the window
  (`confine_popup` logic). The default item shows the checked look (`ACCENT_TINT`). Its items drag like
  palette buttons (`source="group_item"`); dropping back inside the popup reorders (`move_in_group`).
  Right-click on an item: "Make Default" (`set_default`), "Move Out of Group" (`take_out` to the index
  after the group), "Remove" (`remove_from_group`).
- Right-click on a palette button: "Remove" (`remove_entry`), "Ungroup" (groups only), "Insert Divider
  Before" (`insert_divider`), then the common items below. Right-click on a divider: "Remove Divider".
- "Add Command..." (palette context menu, edit mode only) opens `PaletteCatalog(QDialog)`, non-modal,
  320 x 448, title `"Tool Palette Commands"` or `"Object Palette Commands"`: a `QLineEdit` with
  placeholder `Search` filtering by label (case-insensitive substring), and a `QListWidget` (icon 16, row
  24) of the palette's actions not present in the layout, in `actions()` order. Items drag onto the
  palette (`source="catalog"`); a double-click appends to the end. The list refreshes after every change;
  the dialog closes when edit mode ends.
- Every operation saves through `palettes.save` (which rebuilds both palettes through `prefs.changed`).

Context menu of a palette (right-click on its background or a button), in and out of edit mode:
1. "Customize Palette" (check)
2. "Add Command..." (edit mode only)
3. "Position" submenu, check items: tool rail "Left", "Right"; dock "Bottom", "Top", "Left Rail",
   "Right Rail".
4. "Reset Palette" (this palette: layout and position).

Main menu Edit (integration step): "Customize Palettes" (check) and "Reset Palettes" (both palettes),
after "Customize Commands...".

### 7.7 Palette positions (Layout builder, `main_window.py`)

`MainWindow.apply_palette_positions()` (new) runs at the end of `_build` and on `prefs.changed` for
`palette.tools` and `palette.objects`:
- Tool rail: `"left"` (default) first in `qsLeftBlock`; `"right"` last in `qsLeftBlock` (between the
  viewport and the right column). Calls `tool_palette.set_side(position)`.
- Object dock:
  - `"bottom"` (default): floating, as today (`place_object_dock`).
  - `"top"`: floating, same width and centring, top edge at `canvas.geometry().top() + OVERLAY_TOP +
    SPACE_2` (32 + 8 = 40 px from the canvas top, under the View/Cameras/Display/Filter header),
    `popup_side="below"`; no HUD dodge.
  - `"rail_left"` and `"rail_right"`: a vertical `ObjectPalette(orientation=Vertical,
    popup_side="right"/"left")`, a card (`make_card`) 48 px wide in `qsLeftBlock`, right after the tool
    rail when the rail is on the same side, otherwise next to the viewport.
  Order in `qsLeftBlock`, left to right: hooks' left dock column (if present), tool rail (left), dock rail
  (rail_left), viewport, dock rail (rail_right), tool rail (right). Spacing `CARD_GAP` 8 as today.
- Switching between floating and rail replaces the `ObjectPalette` instance (`deleteLater` on the old
  one), updates `self.object_palette` and `self.regions["object_palette"]`, and calls
  `place_object_dock()` for floating positions. `dock_area()` stays the canvas rectangle.
- `place_object_dock()` does nothing when the dock is a rail.

### 7.8 Tests

New `tests/test_palettes.py`:
1. `default_layout("tools")` builds a rail whose `buttons` keys, order, fold-outs and shown commands equal
   today's (Selection now a group); `default_layout("objects")` equals today's dock (`OBJECT_PALETTE_ENTRIES`
   count of `"gap"` is still 2).
2. Pure functions: `move_entry`, `condense` (single onto single, group onto single, single onto group),
   `take_out`, `move_in_group`, `remove_entry`, `remove_from_group`, `set_default`, `ungroup`,
   `insert_action` (refuses duplicates), `insert_divider`; inputs never mutated; results sanitised.
3. `load` sanitising: unknown ids, cross-palette ids, duplicates, empty groups, double dividers, bad
   position; a new action missing from `known` lands in "More".
4. Save, rebuild and restart: condensing Move onto Rotate in edit mode gives one button with a fold-out;
   a new `ToolPalette` (fresh window) shows the same; `reset_all()` restores today's rail and dock.
5. Outside edit mode a condensed group runs its default on click, opens the fold-out after 380 ms hold and
   at once on the corner mark (as `test_tool_palette` does for Extrude).
6. In edit mode a click on Move does not change `scene.tool`; Esc leaves edit mode.
7. Mixed group (Move with Extrude): choosing Extrude runs the Extrude tool, choosing Move sets
   `scene.tool == "move"`; check states follow `scene.toolChanged`.
8. Positions: rail right puts the rail's left edge after the viewport's right edge plus 8 and opens
   fold-outs to the left inside the window; dock top places it 40 px under the canvas top; dock
   rail_left gives a 48 px wide vertical card next to the tool rail; back to bottom restores
   `_layout_errors` with no error.
9. Catalog: lists only absent actions of that palette; search filters; double-click appends.
10. Drag and drop through `QDrag` is hard offscreen: test the drop resolution function
    (`_drop_target(pos) -> ("insert", index) | ("condense", index)`) directly at button centres, gaps and
    edges.

Existing tests to keep passing (update only if a name has to change): `tests/test_tool_palette.py`
(`TRANSFORM_BUTTONS` keys, groups, tooltips, hold and corner behaviour, dividers, 720 px scrolling),
`tests/test_wiring.py` lines 247-310 (`PEN_COMMANDS`, `SCENE_TOOLS` keys), `tests/test_objects_ui.py`
118-129 and `tests/test_trunk_generator.py` 150 (`object_palette.PALETTE_GROUPS`),
`tests/test_trunk_tool.py` 619 (`install.PALETTE_GROUPS`), `tests/test_smoke.py::_layout_errors` (defaults).

## 8. Pixel norm pass

### 8.1 Tokens in `theme.py` outside the norm today (measured by scanning the module)

| Token | Today | New | Notes |
|---|---|---|---|
| `SEGMENT_H` | 30 | 32 | mode switcher; pill radius 16, inner pill `SEGMENT_H // 2 - 2` = 14 |
| `CHIP_H` | 26 | 24 | chips, project chip, tab radius `CHIP_H // 2` = 12 |
| `HUD_H` | 22 | 24 | HUD pill and camera plate; icon `round(HUD_H * 0.6)` = 14 |
| `COMMAND_BUTTON` | 30 | 32 | top bar buttons |
| `FIELD_H` | 22 | 24 | fields; QSS `field_h` 20, `button_h` 18 |
| `SCULPT_BAR_H` | 37 | 40 | also `sculpt_bar.SCULPT_BAR_HEIGHT` 37 to 40 |
| `SCULPT_BUTTON` | 30 | 32 | |
| `SCULPT_ICON` | 22 | 24 | |
| `RIGHT_COLUMN_W` | 488 | 480 | |
| `OBJECT_MANAGER_H` | 385 | 384 | |
| `ATTRIBUTE_MANAGER_H` | 475 | 480 | |
| `COORDINATES_H` | 104 | 120 | section 4 |

QSS literals in `_base_qss()` outside the norm: `QMenu::indicator margin-left 7` (8), `QTabBar::tab
padding 3px 12px` (4px 12px), `QPushButton#qsPanelTab min/max-height 26` (`CARD_HEADER_H - 4` = 24),
`QSlider` groove and sub-page `height 3px` (4, radius 2), slider handle `10 x 10, radius 5, margin -4px`
(12 x 12, radius 6, margin -4px), and every radius derived from the old `SEGMENT_H` and `CHIP_H` (15, 13,
11), which the new token values fix.

### 8.2 Helper

`theme.snap_up(v: float) -> int`: the smallest allowed px value (DesignPx list below 128, multiples of 16
from 128) that is `>= v`. Used for sizes that come from text metrics (buttons sized by their label).

### 8.3 Local constants in files owned tonight

- `tool_palette.py` (Palettes builder): `TOOL_MIN_GAP` 3 to 2, `DIVIDER_HEIGHT` 19 to 20.
- `command_bar.py` (Palettes builder): `COMMAND_GEAR` 17 to 16; `MODE_SEGMENT_PAD` 2 to 4 and
  `MODE_BUTTON_W` 34 to 32, so the mode switcher is 4 x 32 + 2 x 4 = 136 wide and its buttons 24 tall
  (`SEGMENT_H - 2 * MODE_SEGMENT_PAD`).
- `coordinates.py` (Layout builder): section 4; `RESET_W` 125 to 128.
- `viewport.py` (Viewport builder): `label_font` pixel size 11 to 12 (also in `_paint_gizmo`); triad
  `size` 25 to 24; HUD text gaps `+ 6` stay, `+ 3` become 4; point squares 5 and 7 become 6 and 8;
  `GIZMO_PX` 85 to 80, `GIZMO_RING_PX` 68 to 64, `GIZMO_PICK_PX` 7 to 8, `GIZMO_CENTER_PX` 6.5 to 6,
  `DRAG_THRESHOLD` 3 to 4.
- `menu_bar.py` (integration step): `BAR_ITEM_PAD` stays 10; the item vertical padding
  `(MENU_BAR_H - 15) // 2` = 8 stays.

### 8.4 Test: `tests/test_px_norm.py` (new, Layout builder)

Scans the upper-case int tokens of `theme` (skipping alpha, amounts, point sizes and the stroke width) and
every `\d+px` in `theme.stylesheet()`, and asserts each value is allowed by the DesignPx rule. It lists the
offending names in the failure message. Tests that pin old geometry (`tests/test_smoke.py` measured table,
`tests/test_tool_palette.py` mode switcher width if pinned, `tests/test_gizmo_transform.py` gizmo sizes if
pinned) are updated by the builder who owns the changed value.

## 9. Builders, file ownership and integration

### 9.1 Builders (run in parallel; no file has two owners)

| Builder | Owns (edit or create) | Tests it owns |
|---|---|---|
| **E. Prefs** (smallest; finish first, the others code against section 1 meanwhile) | `quartz_studio/prefs.py` (new) | `tests/conftest.py` (new), `tests/test_prefs.py` (new) |
| **A. Selection tools** | `quartz_studio/modeling/select_tools.py` (new), `quartz_studio/modeling/select_interaction.py` (new), `quartz_studio/widgets/status_bar.py` (names and hints, 2.11) | `tests/test_selection_tools.py` (new) |
| **B. Viewport** (display filter and zoom) | `quartz_studio/widgets/viewport.py`, `quartz_studio/widgets/display_filter.py` (new) | `tests/test_display_filter.py` (new), `tests/test_zoom_unlimited.py` (new), updates to `tests/test_camera.py`, `tests/test_viewport_draw.py`, `tests/test_viewport3d.py` (HUD text "Brush Selection", lines 398 and 405), `tests/test_gizmo_transform.py` (only if 8.3 sizes break it) |
| **C. Palettes** | `quartz_studio/palettes.py` (new), `quartz_studio/widgets/tool_palette.py`, `quartz_studio/widgets/object_palette.py`, `quartz_studio/widgets/command_bar.py` | `tests/test_palettes.py` (new), updates to `tests/test_tool_palette.py`, `tests/test_wiring.py`, `tests/test_objects_ui.py` (only if needed) |
| **D. Layout** (splitter, coordinates, palette placement, pixel tokens) | `quartz_studio/widgets/splitter.py` (new), `quartz_studio/main_window.py`, `quartz_studio/widgets/coordinates.py`, `quartz_studio/theme.py`, `quartz_studio/widgets/sculpt_bar.py` (8.1 height only) | `tests/test_layout_chrome.py` (new), `tests/test_px_norm.py` (new), updates to `tests/test_coordinates.py`, `tests/test_smoke.py`, `tests/test_interface_defects.py` (only if needed) |

Cross-builder dependencies are by name only, all defined above:
- A uses `prefs` (E); B uses `prefs` (E) and writes the HUD names of A's tool ids (2.11); C imports
  `select_tools.TOOLS` (A) and `prefs` (E); D reads `palette.*` positions through `palettes.position`
  (C) and calls `ToolPalette.set_side` and `ObjectPalette(orientation=..., popup_side=...)` (C), and
  provides `theme.SPLITTER_*`, `theme.COORDINATES_H`, `theme.snap_up` (used by nobody else).
- Until a dependency lands, import it lazily inside functions so a module still imports; tests that need
  the other builder's module use `pytest.importorskip` only during development and must run without skips
  at the integration step.
- `main_window.py`, `scene.py`, `app.py` and `widgets/menu_bar.py` are also being edited tonight by the
  hooks fleet (`specs/hooks.md`): D re-reads `main_window.py` right before editing and keeps every hook
  (`add_page`, `add_dock`, `page_stack`, `model_page`, `left_dock_column`, `bottom_splitter`). Nobody in
  this contract edits `scene.py` or `app.py`.
- Nobody edits `modeling/interaction.py`, `modeling/ops_select.py`, `modeling/install.py`,
  `widgets/menus_data.py`, `widgets/menu_bar.py`, `widgets/context_menu.py`, `icons.py`, `SPEC.md`,
  `README.md` except the integration step.

### 9.2 Integration step (one agent, after A to E are done)

1. `widgets/menus_data.py`:
   - `SELECT_MENU`: under "SELECTION TOOLS" keep "Brush Selection" ("9", `live_selection`), drop nothing;
     in "TOPOLOGICAL SELECTION" add `item("Pattern Selection")` after "Ring Selection" and rename
     "Phong Break Selection" to "Phong Angle Selection". Unwired items (Rectangle, Lasso, Polygon
     Selection, Stamp, Selection Filter) stay in the data and are pruned as today.
   - `EDIT_MENU`: after "Customize Commands...", `item("Customize Palettes", None, None, check=False)` and
     `item("Reset Palettes")`.
   - `WINDOW_MENU`: first two entries `sub("Display", [...])` and `sub("Filter", [...])` built from
     `display_filter.SHADINGS` and `TOGGLES` (check items, separators as in 5.2, "Reset Display"), then
     `SEP`.
2. `widgets/menu_bar.py`: append `select_tools.menu_commands()`, `display_filter.menu_commands()` and
   `palettes.menu_commands()` to `SCENE_COMMANDS` (after the modeling commands that `install.prepare`
   adds, so the interactive selection tools win the shared labels); add `SCENE_CHECKED: dict[path,
   Callable[[], bool]]` filled from `display_filter.menu_checks()` and `palettes.menu_checks()`, applied
   in `refresh_enabled` as `act.setProperty("qs_check", bool(check()))` and connected to `aboutToShow` like
   `SCENE_ENABLED`.
3. `modeling/install.py`: in `install(window)`, after the modeling panel and filter, call
   `select_interaction.install(window)` (creates the `SelectionToolFilter` on `window.viewport.canvas`
   and the `SelectionOptionsPanel` in `window.manager_splitter`; returns the filter, stored as
   `window.selection_filter`).
4. Run the whole suite (`.\.venv\Scripts\python.exe -m pytest -q`) with no skips; fix seams.
5. `SPEC.md`: section 9.5 (Coordinates fixed at 120; the splitter bar), 9.6 (splitter row:
   idle invisible, hover `SPLITTER_HOVER` 4 px rounded bar, drag `SPLITTER_DRAG`), 9.8 (new tool names and
   hints), and a new section "11. Interface customisation" pointing to this file; `README.md` feature list.

### 9.3 Existing tests that pin what changes

| Test | Pins | Changed by |
|---|---|---|
| `tests/test_viewport3d.py::test_keyboard_tools_and_hud` (398, 405) | HUD "Selection" | B |
| `tests/test_viewport_draw.py::test_hud_follows_modelling_tool` (351) | HUD "Selection" | B |
| `tests/test_viewport_draw.py::test_header_is_overlaid_inside_the_canvas` (523) | menu titles | B |
| `tests/test_camera.py::test_wheel_never_passes_through_the_point` (245) | `MIN_APPROACH` | B |
| `tests/test_camera.py::test_wheel_zoom_never_stalls_on_a_close_target` (610) | `NAV_MIN_DEPTH`, `MIN_APPROACH` | B |
| `tests/test_coordinates.py::test_main_window_coordinates_not_clipped` (733) | `MIN_H` | D |
| `tests/test_smoke.py::test_default_sizes_keep_coordinates_last_with_an_extra_panel` (485) | Coordinates height stable | D (keeps passing) |
| `tests/test_smoke.py::_layout_errors` and the SPEC 9.5 measured table | geometry with the old tokens | D |
| `tests/test_tool_palette.py` (whole file) | rail and dock structure | C (keeps passing) |
| `tests/test_wiring.py` 247-310 | `PEN_COMMANDS`, `SCENE_TOOLS` | C (keeps passing) |
| `tests/test_context_menu.py` 350-355 | Select submenu of the context menu (commands) | nobody (must keep passing) |

## 10. Not determined here

- Whether the selection tool options should live in the Attribute Manager instead of a panel card: the
  attributes contracts may move all tool options there; until then section 2.9 holds.
- Final shortcuts for the selection tools and the brush radius keys: controls contract (2.13).
- Icon stroke width `theme.ICON_STROKE_W` 1.6 and the viewport pen widths (1.3, 1.4, 2.6 px) are outside
  the norm's stroke rule (1, 2 or 4); changing them redraws every icon and the whole viewport look, so this
  contract leaves them for a separate pass the owner approves.
- Font sizes are in points (9 pt is 12 px, inside the scale; 8 pt is 10.7 px, outside it). Moving the 8 pt
  labels to 12 px enlarges every small label; left for the owner.
- `.quartz` files do not store the display filter or the palettes (they are user preferences); if the
  owner wants per-project display settings, that is a later change to `fmt_quartz.py` `view` block.
- The hooks fleet's final `main_window.py` structure was not visible yet; section 7.7 names its expected
  attributes (`left_dock_column`, `bottom_splitter`) from `specs/hooks.md`.
