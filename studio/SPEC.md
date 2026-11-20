# Quartz Studio: interface shell specification

Quartz, author: **D1on1n**. This is the reference document for whoever builds the shell.

Goal: a desktop app (Python 3.14 + PySide6 6.12) for 3D modeling with an identity of its own. The first
versions (31/10 to 19/11/2026) arranged the window after the user's "Startup" layout of another 3D program;
that arrangement study is over. Since 19/11/2026 the look and the layout follow the **Crystal** identity in
section 9, which overrides anything older in this document. The 3D viewport and scene model are described
in `README.md` and sections 7 and 8.

**Status (19/11/2026):** the window shows only the controls that have a function (see `README.md`). Regions:
`menu_bar` and `command_bar` (one top row), `tool_palette` (left rail card), `viewport` (card) with the
`object_palette` floating as a dock inside it, `object_manager`, `attribute_manager` and `coordinates`
(three cards in the right column, the modeling tool options panel between the first two when a tool is
active) and `status_bar`. The title row and the sculpt bar stay on disk out of the window. The right
palette and the Create menu are built from the object registry (section 7), and Make Editable is wired
(top bar button, Mesh menu, key `C`).

## 0. Rules

1. Folder: `studio/`. Environment: `studio/.venv` (PySide6 6.12.0, numpy). Run with
   `studio/.venv/Scripts/python.exe -m quartz_studio` from `studio/`.
2. Code files have no comments and no docstrings. Code, identifiers and visible interface text are in
   English, using the English names of the reference program.
3. **Clean room and branding**: do NOT use icons, logos, fonts or files from Maxon or Cinema 4D, and do not
   extract them from the installed program. Every icon is drawn in code (`QPainter`, vector) in the Crystal
   icon style (section 9.4). The app is called **Quartz Studio** (window title:
   `Untitled - Quartz`). No mention of "Cinema 4D" or "Maxon" in the interface. The
   window icon is the user's file `assets/quartzInstance.ico`; it is never redrawn or replaced.
4. Only PySide6 + the standard library (+ numpy if needed). No network. No dependency on the `quartz` package
   (the shell is independent and will be wired to the core later).
5. The captures in `studio/reference/` are historical: they were the arrangement study and are now used only
   for menu content and command names (sections 5 and 5b). The look and the layout come from section 9. The
   window opens maximized, minimum size 1280x720, and the layout scales (splitters and stretch), not absolute
   positions.

## 1. File layout

```
studio/
  quartz_studio/
    __init__.py            version
    __main__.py            python -m quartz_studio -> app.main()
    app.py                 QApplication, font, theme, MainWindow, show maximized
    theme.py               Crystal tokens (colours, metrics, fonts) and the global QSS
    icons.py               vector icon factory: icon(name, size=24, state=...) -> QIcon
    main_window.py         builds everything (QMainWindow without a native menu bar)
    scene.py               shared scene model
    prefs.py               small JSON preferences store (section 12)
    controls/              actions, profiles, store, dispatch and the Controls editor (section 11)
    widgets/
      __init__.py
      title_row.py         old title row (not in the window)
      menu_bar.py          menus of the top row (data in menus_data.py); StudioMenu
      menus_data.py        menu contents
      command_bar.py       top row: mode switcher, Undo, Redo, Make Editable, project chip
      tool_palette.py      left tool rail (card)
      object_palette.py    object creation dock floating at the bottom centre of the viewport
      viewport.py          viewport card (overlaid View and Cameras menus + drawn area)
      object_manager.py    Hierarchy card (the object tree)
      attribute_manager.py Attribute Manager card (header, summary and parameter rows)
      splitter.py          StudioSplitter and its handle (thin rounded bar on hover and drag)
      coordinates.py       Coordinates card
      status_bar.py        status bar: mode and tool, tool hint, selection counts
      context_menu.py      right-click menus of the viewport and the managers
      sculpt_bar.py        old sculpt bar (not in the window)
      common.py            shared base widgets (IconButton, Segment, PanelTabBar, make_card, ...)
  tools/
    snapshot.py            renders the window offscreen (QT_QPA_PLATFORM=offscreen) to PNG
  tests/
    test_smoke.py          builds the window offscreen, checks regions, layout, texts and wiring
```

## 2. Theme (theme.py)

`theme.py` holds every colour, size, radius, spacing and font token of the Crystal identity, plus the global
QSS. The full token list, with values and uses, is section 9.2 and 9.3. The older names (`BG_WINDOW`,
`BG_PANEL`, `ACCENT_BUTTON`, `ICON_PRIMITIVE` and so on) stay valid and now carry Crystal values (table in
section 9.2.6). No other file defines a colour literal; a file that needs a colour imports the token.

## 3. Arrangement

The arrangement is section 9.5 (one top row, a left tool rail card, the viewport card with the object dock
floating inside it, three cards in the right column, the status bar). The contents of each region:

### 3.1 Title row
Not in the window (`title_row.py` stays on disk). The window title carries the project name.

### 3.2 `menu_bar`
In the left part of the top row, after the app mark. Shows only the menus with wired items (today File,
Edit, Create, Select, Mesh, plus the menus added by extensions); the full tree stays in `menus_data.py`
(section 5). When the menus do not fit before the centred mode switcher, the bar keeps as many as fit and
shows one overflow item (a chevron) whose menu lists the hidden menus as submenus (section 12).

### 3.3 `command_bar`
Shares the top row with `menu_bar`. Centre: the mode switcher (Points, Edges, Polygons, Model), one
segmented pill, exclusive, bound to `Scene.mode`. Right: Undo, Redo (enabled from `Scene.can_undo` and
`can_redo`), Make Editable (enabled when the active object is parametric) and the project chip (file name,
plus a dot while there are unsaved changes; tooltip with the full path).

### 3.4 `tool_palette`
The left rail card. Top to bottom: Selection (fold-out: Brush Selection, Loop Selection, Ring Selection,
Pattern Selection, Fill Selection, Phong Angle Selection; the button shows Brush Selection by default), Move
(checked by default), Rotate, Scale, Pen (fold-out:
Polygon Pen, Pen), a divider, then the mesh tool groups (Extrude, Bevel, Cut, Bridge, Dissolve, Slide,
Normals, Subdivide, Clone), each a fold-out with its tools (the Extrude fold-out ends with Trunk). Exclusive, bound to `Scene.tool`. When the rail is
too short the gaps shrink to 3 px and then up and down arrows scroll it. Tooltips of every rail entry (Move,
Rotate, Scale, both pens, the selection tools and the modeling tools) carry the active profile's binding and
follow a profile change.

### 3.5 `viewport`
The viewport card: View and Cameras menus and the pan, zoom and orbit icons overlaid at the top of the drawn
area; the drawn area (own `paintEvent`, no OpenGL): gradient background, horizon hairline, world axis,
objects, components, gizmos, the axis triad at the top right, the view name, and the tool HUD pill. The mode
and tool text is shown by the status bar, not in the viewport.

### 3.6 `object_palette`
A horizontal dock floating at the bottom centre of the viewport, fold-outs opening upward. Contents (built
from the registry, `widgets/object_palette.py`): Line and Null; then Rectangle (Rectangle, Text Spline,
Profile, 4-Side, n-Side, Star, Cogwheel), Circle (Circle, Arc, Cissoid, Cycloid, Formula, Helix, Flower), Cube
(Cube, Empty Polygon, Plane, Bezier, Landscape, Pyramid), Sphere (Sphere, Disc, Torus, Cone, Tube, Cylinder,
Oil Tank, Capsule), Text (Text, Figure, Platonic); then the generators: Subdivision Surface (Subdivision
Surface, Boole, Symmetry, Remesh, Connect, Cloner, Thicken), Extrude (Extrude, Sweep, Lathe, Loft, Spline
Mask, Trunk), Voronoi Fracture (Voronoi Fracture, Fracture, Metaball, Array). Unregistered objects have no entry. A
click creates the object at the origin, active and selected; Alt on a generator adopts the active object as
its child; Shift makes the new object a child of the active one. `ObjectPalette(parent, orientation=...,
popup_side=...)` also builds a vertical strip (fold-outs to the left) for other hosts.

### 3.7 `object_manager`
First card of the right column: header label "Hierarchy" (it was "Objects"), the object tree (select, Shift and
Ctrl click for several rows, rename with F2 or double click, Delete, drag to reparent, enable check), context
menu. The Python names (`object_manager`, `ObjectManager`) keep their name.

### 3.8 `attribute_manager`
Third card when the tool options panel is shown, second otherwise: header label "Attributes", the object
header (icon, type and name), a summary line for editable meshes (for example "8 points · 6 polygons"), and
one row per parameter of the active object. There are no chips and no Basic or Coord. pages: rows only. The
first group has no header; later groups are collapsible and remember their state per object type.

### 3.9 `coordinates`
Last card, fixed at `COORDINATES_H` 120 px whatever the column size (the handle above it is disabled): Reset
Transformation and the nine fields (Position, Rotation and Size for X, Y and Z, in cm and degrees).

### 3.10 `status_bar`
Bottom of the window: mode and active tool at the left, a hint for the active tool in the centre, the
selection counts at the right (section 9.8).

### 3.11 Sculpt bar
Not in the window (`sculpt_bar.py` stays on disk).

## 4. Behavior
- Every visible control does something; nothing in the window writes "not implemented" (guard:
  `tests/test_smoke.py`, `test_every_visible_control_is_wired`).
- Tool rail buttons and the mode switcher are exclusive (QButtonGroup) and follow the scene both ways.
- Hover, press, checked, disabled and focus states follow section 9.6; press feedback is animated by
  `widgets/press_feedback.py`.
- Menus open with the content from section 5, pruned to wired items. A menu item shows the active profile's
  binding for its action (section 11), and nothing when the profile binds none.
- Tooltips with the name (and the active profile's binding, when there is one) of each button.

## 5. Menu contents (menus_data.py)
Structure: a list of entries `("item", text, shortcut|None, icon|None, enabled)`, `("section", TITLE)`,
`("sep",)`, `("submenu", text, [ ... ])`. Use the captures (`standard/11_menu_modes.jpg`,
`12_menu_create.jpg`, `13_menu_tools.jpg`, `01_window_menu_open.jpg` = Window menu) literally for those four
(capitalized sections as non-clickable headers, disabled items in grey). Fill the other menus with plausible
items of the reference program (File: New Project, Open Project..., Merge Project..., Save Project, Save
Project As..., Export, Close Project, Exit; Edit: Undo, Redo, Cut, Copy, Paste, Delete, Select All, Project
Settings..., Preferences...; and so on). Submenus can have 3 to 8 items.

## 5b. Real palette contents (from the user's layout file)
`studio/reference/layout_palettes.json` was extracted from the user's startup layout file (`template.l4d`),
with the names read from the program itself, in its interface language at the time. Each palette has
`items`: `button` (one command), `group` (a button with a group triangle; it shows `shown`, and clicking or
holding opens a vertical or horizontal popup with all `commands`, as in the program) and `separator`.
Roles: palette 1 = `command_bar`; palette 4 = `tool_palette`; palette 18 = `sculpt_bar`; palette 19 =
`object_palette`; the others are saved palettes that are not visible in this layout.
- Historical note: this file was the source of command names and group contents during the arrangement
  study. Positions, order on screen and look now come from section 9; only the names and group contents
  below are still used.
- The JSON decides **the content of the groups** (popups) and the exact names and tooltips. For example, the
  sculpt bar has Subdivide, Decrease,
  Increase, Unsubdivide | Draw, Wax, Inflate, Amplify, Knife, Repeat | Grab, Smooth, Flatten, Pinch,
  Scrape, Fill | Erase, Mask (group: Invert, Clear, Hide, Show Masked) | Add Layer, Add Folder | Project
  Mesh, Bake Sculpt Objects, Sculpt to Pose Morph.
- The object palette (19) lists Null; Rectangle, Circle, Cube, Sphere, Text/Figure (primitives); 4
  generators; Bend (deformers) and Linear Field (fields); Camera, Light and Sky groups. Only entries whose
  objects exist are shown (section 3.6); new groups join the dock in that order.
- `layout_palettes_named.txt` holds the same information as readable text.

## 5c. File commands

Implemented in `quartz_studio/project.py`; the File menu is the first menu of the bar and shows only wired
items (the other items of the tree in `menus_data.py` stay hidden).
- Items: New Project `Ctrl+N`, Open Project... `Ctrl+O`, Open Recent (up to 10 paths in QSettings, then
  Clear Recent File List), Merge Project... `Ctrl+Shift+O`, Save Project `Ctrl+S`, Save Project As...
  `Ctrl+Shift+S`, Save Incremental `Ctrl+Alt+S`, Import..., Export (one item per registered exporter, then
  Export Selection...), Exit `Alt+F4` (the Classic bindings; section 11). The file shortcuts are created by
  `controls.install(window)` from the active profile (`window.file_shortcuts`).
- Title: `name.quartz - Quartz`; `Untitled - Quartz` for a new project; `*` after the name
  when modified (any `Scene.changed` or `objectsChanged`; cleared by save, open and new).
- A modified project asks Save / Don't Save / Cancel before New, Open, Open Recent, Exit and window close.
- The `.quartz` file stores the camera in `Document.meta["view"]`: `name`, `position`, `target`, `heading`,
  `pitch`, `distance`, `ortho`, `focal`. A file without it is framed with Frame All.
- Dialogs go through `project.choose_open_files`, `choose_save_file`, `ask_save_changes`, `show_message`
  and `quit_application`; tests replace them and set `project.SETTINGS_FILE` to a temporary `.ini`.
- Import adds the objects as one undo step and frames them; `FileFormatError` and `OSError` become one
  message; `Document.meta["warnings"]` become one message. The command line (`launcher.py path...`) and
  dropping files on the window open a `.quartz` as the project and import any other supported file.
- Formats and directions: FBX, glTF, glTF Binary, Wavefront OBJ, Stanford PLY, STL and Quartz Project, each
  read and written. STL drops loose edges on export; PLY writes them as `element edge` and FBX as edges of
  the geometry. STL and PLY are written Z-up and read as Z-up; OBJ, glTF and FBX keep Y-up, with FBX and
  glTF in the units their headers declare. Every exporter writes through a temporary file and `os.replace`.

## 6. Verification
- `tools/snapshot.py --out <png> --size 1920x1010` (and `--size 1280x720`) saves the window rendered
  offscreen. Look at both sizes after any layout or style change.
- `tests/test_smoke.py` (offscreen): the window builds with the nine regions of `main_window.REGIONS`; the
  texts "Hierarchy", "Attributes", "Undo", "Make Editable", "Cube", "Reset Transformation", "Untitled",
  "Mode: Model · Tool: Move" and "Drag to move · Hold Ctrl to copy · Esc cancels" exist; `_layout_errors` checks the geometry of
  section 9.5 (margins, gaps, top row, centred mode switcher, rail, viewport, right column, status bar, dock
  inside the viewport and not wider than it, no overlaps) at 1920x1007 and 1280x720, also with the tool
  options panel shown; `test_every_visible_control_is_wired` clicks every button, fold-out entry and menu
  item of the top row, the rail, the dock and the status bar and fails on "not implemented"; the status bar
  and the project chip show real state; dock fold-outs open upward.

## 7. Parametric objects

Contract for every agent that adds objects (primitives, splines, generators). Source of truth for names and
signatures: `quartz_studio/objects/registry.py` and this section. Code files carry no comments or
docstrings; parameter names, defaults and option lists follow the Object tab of the reference program.

### 7.1 Package `quartz_studio.objects`

- `registry.py` defines everything below; `__init__.py` re-exports it. Importing `quartz_studio.objects`
  imports `builtin.py` and then every module of the package whose name starts with `prim_`, `spline_` or
  `gen_`, sorted by name. A new file registers itself at import; nothing else has to be edited.
- `builtin.py` registers only `"null"` (category `null`, inputs `none`, empty mesh; params `display`,
  `radius`, `aspect_ratio`, `orientation`). Every other id belongs to the agent that owns it.
- `CATEGORIES = ("null", "spline", "mesh", "generator")`, `INPUTS = ("none", "children")`.
- `Param(key, label, kind, default, minimum=None, maximum=None, step=1.0, unit="", choices=(),
  group="Options", modes=())`: subclass of `quartz_studio.modeling.registry.Param` (same fields, same
  panel). Kinds: `distance` (cm), `angle` (degrees), `percent`, `float`, `int`, `bool`, `choice` (a value
  outside `choices` falls back to the default), `vector` (exactly 3 floats, each clamped to
  minimum/maximum, stored as a tuple) and `text` (stored as `str`), plus `font`, `font_style`, `link`,
  `curve` and `color` (their rows come in wave 2). `Param.clamp(value)` clamps and coerces; a value that
  cannot be converted raises `ValueError` or `TypeError`. Extra fields `show` (a rule that hides the row;
  `Param.visible(values)`), `axes` and `ref`; `link_keys(spec)` lists the link parameters.
- `ObjectSpec(id, label, category, build, params=(), inputs="none", icon="", description="", applies=None,
  migrate=None)`: `applies(values)` hides rows for the current values (the Attribute Manager also applies
  `Param.show`), `migrate(values)` upgrades stored values and runs first in `ObjectSpec.clamp`.
  `objects/caps.py` holds the bevel engine (`BEVEL_SHAPES`, `bevel_profile`, `offset_rings`, `safe_distance`)
  for the caps of wave 2.
  - `build(p: dict, inputs: list[BuildInput]) -> Mesh`. `p` holds every parameter key (defaults merged with
    the object's values, already clamped). The build must not mutate the inputs and must return a new
    `Mesh` in the object's local space.
  - `inputs="none"`: `inputs` is always `[]`; children of the object are drawn normally (a Null, a primitive).
  - `inputs="children"`: the object is a generator; `inputs` holds one `BuildInput` per enabled child, in
    child order. Those children (and their subtrees) are consumed: not drawn, not pickable in Model mode.
  - `spec.param(key)`, `spec.defaults()`, `spec.clamp(values)`. An unknown category or inputs value, or a
    repeated parameter key, raises `ValueError`.
- `register(spec) -> spec` (a duplicate id raises `ValueError`), `get(id)` (unknown id raises `KeyError`),
  `all_specs()` (registration order), `by_category(cat)`, `defaults(spec_or_id) -> dict`, `SPECS` (the dict).
- `BuildInput` attributes:
  - `mesh`: a new `Mesh` already transformed into the generator's local space. It is the child's evaluated
    mesh merged with its drawn descendants (so a Null child acts as a group; a generator child gives its
    output only, never its consumed children).
  - `name`, `kind` (the child's kind, `"polygon"` for editable meshes), `obj` (the child `SceneObject`, read
    only), `matrix` (4x4, child space to generator space).
  - `is_spline`: no polygons and at least one loose edge.
  - `chains() -> list[(points N x 3 float array, closed bool)]`: polylines rebuilt from the loose edges.
    Open chains start at their lower-numbered end; a closed chain starts at its lowest point index and goes
    toward its lower-numbered neighbour, and does not repeat the first point. Branch points split chains.
  - Helpers usable on any mesh: `mesh_chains(mesh)`, `mesh_is_spline(mesh)`.

### 7.2 Mesh rules for builds

`Mesh(points, polygons, loose_edges)`, cm, Y up. Polygons are counter-clockwise seen from outside (Newell
normal outward). No duplicate points, no zero-area polygons, no unused points. A closed solid has every edge
shared by exactly 2 faces and positive signed volume. A spline is a `Mesh` with points and loose edges only,
in drawing order; a closed spline has a last edge from the last point to the first. A degenerate parameter set
(for example radius 0) returns `Mesh.empty()` rather than raising.

### 7.3 Scene model (`quartz_studio.scene`)

- `SceneObject(name, mesh, kind="polygon", params=None)` with `kind` (`"polygon"` for editable meshes,
  otherwise the spec id), `params` (dict), `parent` (`SceneObject` or `None`), `enabled` (bool), `error`
  (str, empty when the last build succeeded), `position`, `rotation` (degrees), `scale`, all local to the
  parent. Matrices: `linear()` and `local_matrix()` (local), `parent_matrix()`, `world_matrix()` (4x4),
  `world_linear()`, `world_position()`. `to_world`, `world_points`, `to_local_vector`, `to_local_point` and
  `size` use the parent chain; an object without a parent behaves exactly as before.
- `Scene.objects` is a flat list in depth-first hierarchy order. `Scene.children(obj)` (`None` gives the
  roots), `Scene.roots()`, `Scene.descendants(obj)` (depth-first, without `obj`).
- `Scene.add_parametric(kind, name=None, parent=None, adopt=None, activate=True) -> SceneObject`: default
  params, evaluated at once, appended as the last child of `parent` (or the last root). With `adopt` (and no
  `parent`) the new object takes the place of `adopt` among its siblings and `adopt` becomes its first child
  with an unchanged world transform (create a generator as parent of the selection). One undo step.
- `Scene.set_param(obj, key, value) -> bool`: clamps and coerces through the spec, re-evaluates, one undo
  step, emits `changed`; returns `False` when the value does not change. A continuous mouse drag of the same
  key on the same object is one undo step. An unknown key raises `KeyError`; an editable object raises
  `ValueError`.
- `Scene.set_parent(obj, parent, index=None) -> bool`: `parent=None` makes a root; `index` is the position
  among the new siblings (`None` appends). Refuses cycles (returns `False`), keeps the world transform of
  `obj`, one undo step, emits `objectsChanged` and `changed`.
- `Scene.set_enabled(obj, flag)`: one undo step. A disabled object and its whole subtree are not drawn and
  are not generator inputs.
- `Scene.render_objects()`: what the viewport draws and picks, in depth-first order: enabled objects whose
  ancestors are all enabled and not generators. `Scene.raycast` and `Scene.world_bounds` default to it.
- `Scene.evaluate() -> bool`: rebuilds, bottom-up, every parametric object whose params changed or whose
  inputs changed (child mesh, transform, params, enabled state, hierarchy; renames do not count). It runs
  inside every scene method above and on every `changed` emission, so a tool that edits a child mesh and
  emits `changed` updates the generators above it. Nothing is rebuilt when nothing changed. A build that
  raises (or returns something that is not a `Mesh`) leaves an empty mesh and the message in `obj.error`.
- `Scene.make_editable(obj) -> SceneObject`: replaces a parametric object by a `"polygon"` object holding
  its evaluated mesh, with the same name, transform, parent and place. A generator's children are removed;
  the children of a primitive stay under the new object. A Null or an editable object is returned unchanged.
  One undo step.
- `Scene.is_editable(obj)`: `True` only for kind `"polygon"`. On any other active object the component
  selection and edit methods (`select_components`, `move_selection` in Points, Edges and Polygons mode,
  `extrude_selection`, the polygon pen) do nothing, the line pen starts a new Line object, and the modeling
  tools refuse with "<Tool>: Make Editable first". Model mode move, rotate and scale work on every object.
- `remove_object(obj)` removes its whole subtree. Undo and redo snapshots keep kind, params, parent,
  enabled, error and the cached meshes, so undo restores hierarchy and caches without rebuilding.
- The default scene is one editable `"Cube"`.
- Component editing of the active object stays possible in Points, Edges and Polygons mode even when a
  generator consumes it (cage editing); the viewport then draws only its component overlay.

### 7.4 Examples

A mesh object, in `quartz_studio/objects/prim_example.py`:

```python
from __future__ import annotations

from ..scene import Mesh
from .registry import ObjectSpec, Param, register


def build_box(p: dict, _inputs: list) -> Mesh:
    if p["size"] <= 0:
        return Mesh.empty()
    return Mesh.cube(p["size"])


register(ObjectSpec(
    id="example_box", label="Example Box", category="mesh", build=build_box,
    params=(Param("size", "Size", "distance", 200.0, minimum=0.0, group="Object"),),
    icon="cube"))
```

A spline object, in `spline_example.py`:

```python
import math

from ..scene import Mesh
from .registry import ObjectSpec, Param, register


def build_ngon(p: dict, _inputs: list) -> Mesh:
    n, r = p["sides"], p["radius"]
    pts = [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n), 0.0) for k in range(n)]
    return Mesh(pts, [], [(k, (k + 1) % n) for k in range(n)])


register(ObjectSpec(
    id="example_ngon", label="Example N-Side", category="spline", build=build_ngon,
    params=(Param("radius", "Radius", "distance", 200.0, minimum=0.0),
            Param("sides", "Sides", "int", 6, minimum=3, maximum=1000))))
```

A generator, in `gen_example.py` (moves a copy of every input up by `offset`):

```python
import numpy as np

from ..scene import Mesh
from .registry import ObjectSpec, Param, register


def build_lift(p: dict, inputs: list) -> Mesh:
    pts, polys, loose, off = [], [], [], 0
    for inp in inputs:
        m = inp.mesh
        pts.append(m.points + np.array([0.0, p["offset"], 0.0]))
        polys += [tuple(i + off for i in poly) for poly in m.polygons]
        loose += [(a + off, b + off) for a, b in m.loose_edges]
        off += len(m.points)
    return Mesh(np.vstack(pts) if pts else np.zeros((0, 3)), polys, loose)


register(ObjectSpec(
    id="example_lift", label="Example Lift", category="generator", build=build_lift,
    params=(Param("offset", "Offset", "distance", 100.0),), inputs="children"))
```

A spline generator reads `inp.chains()` of each input with `inp.is_spline` and ignores the others.

### 7.5 Using objects from a test

```python
from quartz_studio.scene import reset_scene

scene = reset_scene()
box = scene.add_parametric("example_box")
scene.set_param(box, "size", 50)
lift = scene.add_parametric("example_lift", adopt=box)
assert box.parent is lift and box not in scene.render_objects()
assert len(lift.mesh.points) == 8 and not lift.error
poly = scene.make_editable(lift)
scene.undo()
```

A test may register its own specs under unique ids (for example prefixed with the test module name); see
`tests/test_objects_core.py`. A spec can also be built directly without a scene:
`registry.get("example_box").build(registry.defaults("example_box"), [])`.

## 8. Files

Contract for file import and export. Source of truth for names and signatures: the package
`quartz_studio/fileio` and this section. Code files carry no comments or docstrings.

### 8.1 Package `quartz_studio.fileio`

- `model.py`, `registry.py`, `bridge.py` and `api.py` define everything below; `__init__.py` re-exports it.
  Importing `quartz_studio.fileio` imports `model`, `registry`, `bridge`, `api` and then every module of the
  package whose name starts with `fmt_`, sorted by name. A new format is one new file `fmt_<name>.py` that
  calls `register` at import; nothing else has to be edited. A duplicate id or extension raises `ValueError`.
- `Node(name, mesh=None, matrix=eye(4), parent=None, kind="polygon", params=None, enabled=True,
  position=None, rotation=None, scale=None)`: dataclass. `mesh` is a `Mesh` in the node's own (local) space or
  `None` (an empty group, or a parametric object stored without geometry). `matrix` is the 4x4 WORLD transform
  (column vectors, same as `SceneObject.world_matrix()`). `parent` is an index into `Document.nodes` or `None`.
  `kind` is `"polygon"` for editable meshes, otherwise an object spec id (section 7). `params` is the spec
  parameter dict (vectors as tuples) or `None`. `position`, `rotation` (degrees) and `scale` are the LOCAL
  transform relative to the parent, or `None` when the source does not know them (they are then derived from
  `matrix` and the parent's matrix).
- `Document(nodes=[], meta={})`: dataclass. `meta` is free-form; the bridge writes `unit` ("cm"), `up` ("y"),
  `handedness` ("right"), `source`, and for the full document `active` (node index or `None`).
- `baked_mesh(node) -> Mesh`: the node's mesh in world space, polygon winding reversed when the determinant of
  `matrix[:3, :3]` is negative (so a mirrored object keeps outward normals). A `None` mesh gives `Mesh.empty()`.
- `triangulate(mesh) -> (points (N, 3) float, triangles (M, 3) int)`: a triangle is kept as is; every polygon
  with more than 3 corners goes through `scene._ear_clip`, the routine the scene uses for n-gons, so concave
  n-gons keep their area. Winding is preserved.
- `face_normals(mesh, points=None) -> (P, 3)`: unit normals, same as `Mesh.polygon_normals`.
- `weld(points, tolerance=1e-6) -> (unique points, index map)`: `unique[index[i]]` is within `tolerance` of
  `points[i]`; unique points keep the order of first appearance; `tolerance=0` merges exact duplicates only.
- `decompose(matrix) -> (position, rotation_deg, scale)` and `compose(position, rotation_deg, scale) -> 4x4`:
  the exact convention of `scene.rotation_matrix`: `R = Rz @ Ry @ Rx`, linear part `R @ diag(scale)`. A
  negative determinant is carried by a negative `scale[0]`. `decompose(compose(p, r, s))` returns `r` for
  `|pitch| < 90` degrees and non-negative scale.
- `registry.FileFormat(id, label, extensions, load=None, save=None, description="")`: frozen dataclass.
  `extensions` is a tuple such as `(".obj",)` (stored lowercase with the dot). `load(path: str) -> Document`.
  `save(path: str, document: Document, options: dict) -> None`. `None` means the direction is not supported.
- `registry.register(fmt) -> fmt`, `get(id)` (unknown id raises `KeyError`), `by_path(path) -> FileFormat | None`
  (case-insensitive on the extension), `importers()`, `exporters()` (lists, registration order),
  `file_filter(fmt) -> "Label (*.ext *.ext2)"`, `import_filters()` and `export_filters()` (lists of Qt filter
  strings: `"All supported (*.a *.b)"` first, then one per format; join with `";;"` for a dialog), `FORMATS`.
- `registry.FileFormatError(Exception)`: its message is shown to the user as is, so it names the file and the
  reason. A format module raises it for bad content; any other exception is wrapped by `api`.
- `bridge.document_from_scene(scene, selected_only=False) -> Document`: interchange export. One flat node
  (`parent=None`, `kind="polygon"`, `params=None`) per object of `Scene.render_objects()` that has points and
  at least one polygon or loose edge: evaluated mesh (a copy), `matrix = world_matrix()`, name. A generator
  contributes its result, never its consumed children; disabled subtrees are skipped. With `selected_only`
  only the active object (when `scene.object_selected`) and its drawn descendants are exported.
- `bridge.full_document_from_scene(scene) -> Document`: native format. Every object in `Scene.objects` order
  with `kind`, `params` (copy, `None` for editable), `parent` index, `enabled`, local `position`, `rotation`,
  `scale`, `matrix`, and `mesh` only for editable (`"polygon"`) objects; `meta["active"]`.
- `bridge.add_document_to_scene(scene, document) -> list[SceneObject]`: creates one object per node, in node
  order. A node becomes a parametric object when `kind` is a registered spec and `params` is not `None`
  (params are clamped by the spec); otherwise an editable polygon object with a copy of `mesh`; a node with
  no mesh and no usable spec becomes a Null. Hierarchy comes from `parent`, the local transform from the
  node's `position`/`rotation`/`scale` or else from `inverse(parent.matrix) @ matrix`; `enabled` is kept;
  names are made unique (`Cube` becomes `Cube.1`). It is ONE undo step (`Scene.insert_objects`) and the first
  created object becomes active. A bad parent index or a cycle raises `FileFormatError` and changes nothing.
  An empty document changes nothing.
- `bridge.replace_scene(scene, document)`: same creation, but the whole scene content is replaced and the
  undo and redo history is cleared (`Scene.clear_history`). Active object: `meta["active"]` or the first.
- `api.import_file(scene, path) -> list[SceneObject]`, `api.export_file(scene, path, selected_only=False,
  options=None)`, `api.open_scene(scene, path)`, `api.save_scene(scene, path)`: choose the format by
  extension. `FileFormatError` for an unknown extension, a missing file, a format that cannot do that
  direction, an export with nothing to write, and any other exception from a format (wrapped as
  `"<file name>: <ExceptionType>: <message>"`). `open_scene` and `save_scene` use the full document
  (`replace_scene`, `full_document_from_scene`); `import_file` and `export_file` use the interchange one.
  `options` is passed to the format as a dict (never `None`). Formats receive `path` as `str`.
- Scene additions for this contract: `Scene.insert_objects(objs, parents, activate=True, replace=False)`
  (`parents[i]` is the index in `objs` of the parent of `objs[i]` or `None`; raises `ValueError` on a bad
  index or a cycle) and `Scene.clear_history()`.

### 8.2 Units and axes

Quartz is centimetres, Y up, right-handed, counter-clockwise polygons seen from outside. A `Document` is
always in those units. Each format converts at its own border: on load multiply by the file's unit to get
cm and rotate or mirror axes into Y-up right-handed (a Z-up file maps `(x, y, z)` to `(x, z, -y)`); on save
do the inverse and write the unit and axes in the file when the format has a place for them. A converted
left-handed source must flip polygon winding. Rotation is stored in degrees in the scene's `Rz @ Ry @ Rx`
convention; a format with another convention converts through `compose` and `decompose`.

### 8.3 Example format module

`quartz_studio/fileio/fmt_example.py`, a text format with one `name x y z` line per cube-shaped node:

```python
from __future__ import annotations

import numpy as np

from ..scene import Mesh
from .model import Document, Node, baked_mesh
from .registry import FileFormat, FileFormatError, register


def load(path: str) -> Document:
    nodes = []
    with open(path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) != 4:
                raise FileFormatError(f"line {number}: expected name x y z")
            matrix = np.eye(4)
            matrix[:3, 3] = [float(v) for v in parts[1:]]
            nodes.append(Node(parts[0], Mesh.cube(100.0), matrix))
    return Document(nodes, {"unit": "cm"})


def save(path: str, document: Document, options: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for node in document.nodes:
            points = baked_mesh(node).points
            x, y, z = points.mean(axis=0) if len(points) else (0.0, 0.0, 0.0)
            handle.write(f"{node.name} {x:.3f} {y:.3f} {z:.3f}" + chr(10))


register(FileFormat("example", "Example Text", (".exa",), load, save, "One cube per line"))
```

A format that only imports passes `save=None`; one that only exports passes `load=None`. Use `baked_mesh`
when the format has no transforms, `triangulate` when it needs triangles, `weld` to merge duplicated
points. Test a format by registering it under a unique id and calling `import_file` and `export_file`.

### 8.4 What the native format must store

The native format (`save_scene` and `open_scene`) stores the full document so that a round trip is lossless:
for every object in order its `name`, `kind`, `params` (vector params as 3 numbers, restored as tuples),
`parent` index, `enabled`, local `position`, `rotation` and `scale` (full float precision), and for editable
objects the mesh (`points`, `polygons`, `loose_edges`); parametric objects store no mesh, they are rebuilt
from `kind` and `params`. It also stores `meta["active"]`, a format version number, and the unit (`cm`). It
may additionally store the camera and view state. Unknown `kind` values must load as Null objects without
failing, so a file written with more object types still opens.

## 9. Identity (Crystal)

Decided on 19/11/2026: Quartz Studio stops looking like a copy of another 3D program and gets its own
identity, **Crystal**: a precision instrument cut from dark glass. This section is the single source for the
look and the layout. Where an older section disagrees, this section wins. A builder needs nothing else than
this section, `quartz_studio/theme.py` and the files it owns.

### 9.1 Principles

1. Surfaces are cool blue-black ink, never neutral grey. Separation comes from 8 px gaps and 1 px light
   hairlines (`HAIRLINE`), never from black lines.
2. The accent (mint ice) is used sparingly. A checked or active control is an **accent tint** (the accent at
   18 percent over the surface) with its icon or text in the accent colour, never a solid coloured slab.
   Solid accent appears only in small marks: focus ring, selected row bar, unsaved dot, checkbox fill,
   toggle track, slider handle.
3. Cards are rounded (10 px), controls are rounded (6 px), pills are fully rounded.
4. Every colour, size, radius, spacing and font comes from `theme.py`. No other file contains a colour
   literal (`"#rrggbb"`, `QColor(r, g, b)`, colour names) after the build; section 9.9 says which token
   replaces each literal that exists today.
5. The functional-only rule stays: the window shows only controls that do something.
6. The window icon (`assets/quartzInstance.ico`) belongs to the user and is not changed; the app mark in
   the top bar shows that same icon.

### 9.2 Colour tokens

All names live in `quartz_studio.theme`. Helpers: `mix(fg, bg, amount) -> "#rrggbb"` (blend, used for the
tints), `argb(color, alpha) -> "#aarrggbb"` (QColor reads it directly), `qss_rgba(color) -> "rgba(r, g, b,
a)"` (use it to put an ARGB token in a stylesheet).

#### 9.2.1 Surfaces and lines

| Token | Value | Use |
|---|---|---|
| `SURFACE_BACKDROP` | `#0f1115` | window background, top bar, status bar, splitter gaps, menu bar background |
| `SURFACE_CARD` | `#171a21` | cards (rail, viewport frame, right column cards, tool options), dock (at `DOCK_ALPHA`), segmented pill container |
| `SURFACE_RAISED` | `#1f2430` | resting push buttons and project chip; hover of ghost buttons, rail and dock buttons, tree rows, menu bar items |
| `SURFACE_HOVER` | `#262c3a` | hover of raised controls (push buttons) |
| `SURFACE_PRESSED` | `#0a0c10` | pressed controls |
| `SURFACE_FIELD` | `#0c0e12` | text fields, spin boxes, coordinate fields, combo boxes, checkbox box |
| `SURFACE_FIELD_HOVER` | `#11141a` | hover of fields |
| `SURFACE_MENU` | `#12151b` | menus, fold-outs, context menus, combo popups, tooltips |
| `HAIRLINE` | `#2a3040` | card border, separators, dividers, field and button borders, menu border, horizon-like rules |
| `HAIRLINE_STRONG` | `#3a4358` | hover border of fields and buttons, scrollbar handle, checkbox border |

#### 9.2.2 Text

| Token | Value | Use |
|---|---|---|
| `TEXT_PRIMARY` (= `TEXT`) | `#e7eaf0` | labels, values, menu items, tree rows, status bar mode text |
| `TEXT_SECONDARY` (= `TEXT_DIM`) | `#a3abbb` | card header labels, field labels, shortcuts, menu bar items at rest, status hint and counts, section headers |
| `TEXT_MUTED` (= `TEXT_DISABLED`) | `#6b7385` | disabled text only (it is under 4.5:1 on purpose) |
| `TEXT_BRIGHT` | `#f5f7fa` | hovered menu row text, gizmo view ring, pivot mark |

#### 9.2.3 Accent

| Token | Value | Use |
|---|---|---|
| `ACCENT` | `#5ee6c8` | icon or text of a checked control, focus ring, selected row bar, unsaved dot, checkbox fill, toggle track on, slider handle, drop indicator, n-gon guide |
| `ACCENT_HOVER` | `#7cf0d6` | accent marks under the mouse (slider handle, checkbox border) |
| `ACCENT_PRESSED` | `#3fc7aa` | accent marks pressed; slider fill |
| `ACCENT_ON` | `#06231d` | text or glyph on solid accent (check mark, toggle knob) |
| `ACCENT_TINT` (= `ACCENT_BUTTON`) | `#243f3f` | background of checked controls and selected rows on a card (accent 18 percent over `SURFACE_CARD`) |
| `ACCENT_TINT_HOVER` | `#294f4c` | checked or selected and hovered (26 percent); text selection in fields |
| `ACCENT_TINT_MENU` (= `BG_MENU_HOVER`) | `#203b3a` | hovered menu row (18 percent over `SURFACE_MENU`) |
| `ACCENT_TINT_BACKDROP` | `#1d3735` | open menu bar item, hovered splitter gap (18 percent over `SURFACE_BACKDROP`) |
| `ACCENT_TINT_ARGB` | `#2e5ee6c8` | accent tint painted over an unknown surface (viewport overlays) |
| `ACCENT_ALPHA` | `46` | alpha of the tint (18 percent of 255) for painters |
| `FOCUS_RING` | `= ACCENT` | 1 px ring (`FOCUS_RING_W`) |

#### 9.2.4 Icon stroke and family tints

| Token | Value | Use |
|---|---|---|
| `ICON_STROKE` (= `ICON_FG`) | `#cfd5e1` | the one neutral stroke colour of every icon |
| `TINT_MINT` | `#5ee6c8` | family tint: meshes and commands |
| `TINT_CITRINE` | `#ffb53d` | family tint: tools |
| `TINT_AMETHYST` | `#9d8cff` | family tint: generators (and future deformers) |
| `TINT_ROSE` | `#ff7aa8` | family tint: splines (and future fields) |
| `ICON_MESH` (= `ICON_PRIMITIVE`) | `#5ee6c8` | mesh objects and primitives |
| `ICON_SPLINE` | `#ff7aa8` | spline objects and the Line entry |
| `ICON_GENERATOR` | `#9d8cff` | generators |
| `ICON_TOOL` | `#ffb53d` | tools of the rail and modeling tool icons |
| `ICON_COMMAND` | `#5ee6c8` | top bar, menu and viewport command icons |
| `FAMILY_TINTS` | dict | `{"splines", "meshes", "generators", "tools", "commands"}` to the tints above |
| `ICON_STROKE_W` | `1.6` | stroke width on the 24-unit icon grid |

#### 9.2.5 Viewport

| Token | Value | Use |
|---|---|---|
| `VIEWPORT_TOP` / `VIEWPORT_BOTTOM` | `#1a1e27` / `#101318` | the quiet vertical background gradient (no letterbox bands) |
| `HORIZON` | `#343c50` | the horizon, drawn as a 1 px hairline |
| `GRID_MINOR` / `GRID_MAJOR` | `#1d2230` / `#2a3040` | floor grid, if one is drawn |
| `AXIS_X` / `AXIS_Y` / `AXIS_Z` | `#ff5d6c` / `#5fd97a` / `#5c9dff` | world axis, gizmo arrows, rings and planes, axis triad, axis letters |
| `SELECT_FRONT` | `#ffb53d` | selected points, edges, polygons and object outline seen from the front (citrine) |
| `SELECT_FRONT_DARK` | `#8a5a12` | outline under a selected element |
| `SELECT_FRONT_SOFT` | `#ffd98a` | hover and preview of a pick |
| `SELECT_BACK` | `#9d8cff` | selected polygons seen from behind (amethyst) |
| `WIRE` | `#cfd5e1` | edges, lines and loose edges at rest |
| `POINT_FILL` / `POINT_BORDER` | `#cfd5e1` / `#0c0e12` | unselected points |
| `GIZMO_HOVER` | `#ffd98a` | hovered gizmo handle |
| `SHADOW` | `#aa0c0e12` | dark halo under lines and points |
| `POLY_OUTLINE` | `#960c0e12` | polygon outlines in Model mode |
| `OVERLAY_BG` | `#d912151b` | viewport overlays: HUD pill, labels, hovered ghost buttons |
| `DOCK_BG` / `DOCK_ALPHA` | `#eb171a21` / `235` | object dock fill (card colour at 92 percent) |
| `STATUS_OK` / `STATUS_ERROR` | `#5fd97a` / `#ff5d6c` | enabled check and disabled cross in the Hierarchy, error text, invalid drop |

#### 9.2.6 Older names

These names stay so nothing breaks; use the Crystal names in new code.

| Old name | Now |
|---|---|
| `BG_WINDOW`, `BG_BAR`, `SPLITTER` | `SURFACE_BACKDROP` |
| `BG_PANEL`, `BG_PANEL_HEADER`, `BG_BUTTON_DISABLED` | `SURFACE_CARD` |
| `BG_TAB_ACTIVE`, `BG_BUTTON` | `SURFACE_RAISED` |
| `BG_BUTTON_HOVER` / `BG_BUTTON_PRESSED` | `SURFACE_HOVER` / `SURFACE_PRESSED` |
| `BG_FIELD`, `BG_FIELD_DARK`, `VIEWPORT_LETTERBOX` | `SURFACE_FIELD` |
| `BG_FIELD_HOVER` | `SURFACE_FIELD_HOVER` |
| `BG_MENU`, `BG_TOOLTIP`, `BG_TITLE` | `SURFACE_MENU` |
| `BG_MENU_HOVER` | `ACCENT_TINT_MENU` |
| `BG_VIEWPORT_TOP` / `BG_VIEWPORT_BOTTOM` | `VIEWPORT_TOP` / `VIEWPORT_BOTTOM` |
| `BORDER`, `SEPARATOR_LINE`, `GROUP_LINE`, `VIEWPORT_BORDER`, `SLIDER_TRACK` | `HAIRLINE` |
| `TEXT`, `TEXT_MENU_NEW` | `TEXT_PRIMARY` (menus are no longer highlighted in yellow) |
| `TEXT_DIM`, `TEXT_SECTION`, `ICON_SCULPT` | `TEXT_SECONDARY` |
| `TEXT_DISABLED`, `ICON_DIM` | `TEXT_MUTED` |
| `ACCENT_BUTTON` | `ACCENT_TINT` |
| `ACCENT_TEXT`, `ACCENT_UNDERLINE`, `SLIDER_HANDLE` | `ACCENT` |
| `SLIDER_FILL` | `ACCENT_PRESSED` |
| `ICON_FG`, `ICON_CAMERA` | `ICON_STROKE` |
| `ICON_PRIMITIVE` | `ICON_MESH` |
| `ICON_DEFORMER` | `TINT_AMETHYST` |
| `ICON_FIELD` | `TINT_ROSE` |
| `ICON_SPLINE_PEN`, `ICON_ACCENT_ORANGE`, `ICON_ACCENT_YELLOW`, `ICON_LIGHT` | `TINT_CITRINE` |

#### 9.2.7 Measured contrast

WCAG 2 contrast ratios (relative luminance), computed from the token values:

| Text on | BACKDROP | CARD | RAISED | HOVER | FIELD | MENU | TINT | TINT_HOVER | TINT_MENU |
|---|---|---|---|---|---|---|---|---|---|
| `TEXT_PRIMARY` | 15.68 | 14.45 | 12.88 | 11.59 | 16.03 | 15.17 | 9.38 | 7.52 | 9.97 |
| `TEXT_SECONDARY` | 8.19 | 7.54 | 6.72 | 6.05 | 8.37 | 7.92 | 4.90 | 3.93 | 5.21 |
| `TEXT_MUTED` | 3.97 | 3.66 | 3.26 | 2.94 | 4.06 | 3.84 | 2.38 | 1.91 | 2.53 |
| `ACCENT` | 12.26 | 11.30 | 10.07 | 9.06 | 12.54 | 11.86 | 7.34 | 5.88 | 7.80 |
| `TEXT_BRIGHT` | 17.61 | 16.22 | 14.46 | 13.01 | 18.00 | 17.03 | 10.53 | 8.44 | 11.19 |
| `ICON_STROKE` | 12.83 | 11.82 | 10.54 | 9.48 | 13.11 | 12.41 | 7.67 | 6.15 | 8.16 |

`ACCENT_ON` on `ACCENT` 10.77, on `ACCENT_HOVER` 12.08, on `ACCENT_PRESSED` 7.87. Primary and secondary text
pass 4.5:1 on every surface a card can show except `TEXT_SECONDARY` on `ACCENT_TINT_HOVER` (3.93): a checked
or selected and hovered control therefore shows its text in `TEXT_PRIMARY` or `ACCENT`, never in
`TEXT_SECONDARY`. Tints and axis colours against the viewport (`VIEWPORT_TOP` / `VIEWPORT_BOTTOM`): mint
10.83 / 12.08, citrine 9.48 / 10.57, amethyst 6.06 / 6.76, rose 6.83 / 7.62, X 5.59 / 6.23, Y 9.29 / 10.36,
Z 6.13 / 6.84. `HAIRLINE` is 1.32 on a card: it separates, it does not shout.

### 9.3 Shape, spacing, size and font tokens

| Token | Value | Use |
|---|---|---|
| `SPACE_1` / `SPACE_2` / `SPACE_3` | 4 / 8 / 12 | the only spacing steps |
| `WINDOW_MARGIN` | 8 | body and top bar margin to the window edge |
| `CARD_GAP` (= `SPLITTER_W`) | 8 | gap between cards, splitter handle width |
| `CARD_PADDING` | 8 | inner padding of card content |
| `CARD_RADIUS` | 10 | cards |
| `CONTROL_RADIUS` (= `BUTTON_RADIUS`) | 6 | buttons, fields, combos, menu rows, tooltips |
| `DOCK_RADIUS` | 12 | object dock |
| `MENU_RADIUS` | 8 | menus, fold-outs, context menus, combo popups |
| pills | height / 2 | mode switcher (`SEGMENT_H / 2`), chips (`CHIP_H / 2`), HUD (`HUD_H / 2`) |
| `ACCENT_BAR_W` | 2 | accent bar at the left of a selected row |
| `FOCUS_RING_W` | 1 | focus ring |
| `TOP_BAR_H` (= `COMMAND_BAR_H`) | 40 | top row |
| `MENU_BAR_H` | 32 | menu bar inside the top row (vertically centred) |
| `APP_MARK` | 20 | size the app mark had; the mark is no longer in the top row, the token stays for tests that import it |
| `SEGMENT_PAD` / `SEGMENT_BORDER` | 2 / 1 | space between the border of a segmented pill (mode switcher, page switcher) and its buttons, and the border width |
| `COMMAND_BUTTON` / `COMMAND_ICON` | 30 / 18 | top bar buttons and their icons |
| `SEGMENT_H` | 30 | mode switcher height |
| `CHIP_H` | 26 | project chip and chips |
| `RAIL_PAD` | 6 | rail padding |
| `PALETTE_BUTTON` / `PALETTE_ICON` | 36 / 24 | rail buttons and icons |
| `PALETTE_W` (= `RAIL_W`) | 48 | rail card width |
| `DOCK_BUTTON` / `DOCK_ICON` / `DOCK_PAD` / `DOCK_GAP` | 36 / 24 / 6 / 12 | dock buttons, icons, padding, gap between groups |
| `DOCK_H` | 48 | dock height |
| `DOCK_BOTTOM` | 12 | dock distance to the viewport bottom |
| `GHOST_BUTTON_H` / `NAV_BUTTON` / `HUD_H` | 24 / 24 / 22 | viewport overlays |
| `VIEWPORT_MENU_H` | 28 | height of the overlaid viewport menu row |
| `CARD_HEADER_H` | 28 | card header label row |
| `PANEL_TAB_H` / `PANEL_MENU_H` | 24 / 24 | panel tab and menu rows inside cards |
| `ROW_H` | 24 | tree rows |
| `FIELD_H` | 22 | fields and field rows |
| `MENU_ROW_H` / `MENU_ICON` | 28 / 16 | menu rows and their icons |
| `STATUS_BAR_H` | 24 | status bar |
| `COORDINATES_H` | 120 | Coordinates card height (fixed) |
| `SPLITTER_BAR` / `SPLITTER_BAR_INSET` | 4 / 24 | splitter bar thickness and its inset from each end (8 on a handle shorter than 80) |
| `FONT_FAMILY` | `"Segoe UI Variable Text"` | every text; `theme.install_font_substitutions()` (run at import) maps it to `FONT_FALLBACKS` = `("Segoe UI Variable", "Segoe UI")` when Qt does not know the name, so `QFont(theme.FONT_FAMILY)` and the QSS `font-family` both resolve |
| `FONT_POINT_SIZE` | 9 | default text |
| `FONT_GROUP_POINT_SIZE` / `FONT_SMALL_POINT_SIZE` | 8 / 8 | card headers, section headers, status bar |
| `HEADER_LETTER_SPACING` | 1.0 | absolute letter spacing (px) of uppercase headers |
| `WINDOW_MIN_W` / `WINDOW_MIN_H` | 1280 / 720 | minimum window size |

Card headers and section headers are uppercase through `QFont.Capitalization.AllUppercase` and
`QFont.SpacingType.AbsoluteSpacing` = `HEADER_LETTER_SPACING`, DemiBold, `FONT_GROUP_POINT_SIZE`,
`TEXT_SECONDARY`. Their text stays title case in code ("Hierarchy", "Attributes"), so tests, tooltips and
accessibility read the real words.

### 9.4 Icons

- Drawn in code on a 24-unit grid, flat: one stroke colour (`ICON_STROKE`, or the colour passed to
  `icons.icon(name, size, color)`), `ICON_STROKE_W` 1.6 at 24 units, round caps and round joins. At most one
  family tint per icon, used for one accent part (a face, a dot, a stroke). Fills are flat, in the stroke
  colour or the tint, at full or 25 percent opacity. No gradients, no `lighter()` / `darker()` shading, no
  glossy highlights, no white (`#ffffff`) and no black parts.
- Families and tints:

| Family | Tint | Icons |
|---|---|---|
| splines | `TINT_ROSE` | Line, Rectangle, Circle and every object of category `spline` (Text Spline, Profile, Arc, Helix, ...) |
| meshes | `TINT_MINT` | Cube, Sphere, Text, Empty Polygon, every object of category `mesh`, editable polygon objects |
| generators | `TINT_AMETHYST` | Subdivision Surface, Extrude, Voronoi Fracture and every object of category `generator` |
| tools | `TINT_CITRINE` | Selection, Move, Rotate, Scale, Pen, Polygon Pen, every modeling tool (`mt_*`), the viewport HUD glyph |
| commands | `TINT_MINT` | mode icons (Points, Edges, Polygons, Model), Undo, Redo, Make Editable, menu command icons (`m_*`), viewport pan, zoom and orbit icons |
| neutral | none | Null, chevrons, check, arrows, hamburger, gear, close, the group mark |

- States: checked or active icons are drawn with the stroke in `ACCENT` (the tint stays); disabled icons at
  `icons.DISABLED_OPACITY`; the fold-out mark (`icons.draw_group_mark`, `GROUP_MARK_COLOR`) is a small
  triangle in `TEXT_SECONDARY` at the bottom right.
- The icon API stays: `register`, `has`, `icon`, `pixmap`, `render`, `draw_group_mark`, `write_qss_assets`,
  `modeling_icon_name`, `modeling_icon_ids`, `DISABLED_OPACITY`, `GROUP_MARK_COLOR`. Icons registered by
  other modules (`command_bar.py`, `tool_palette.py`, `object_palette.py`, `menu_bar.py`) follow the same
  rules; their owners restyle them.
- Tests that hold: every mesh tool icon has its own name, is not empty, fills at most 80 percent of its cell
  and shows the tool tint (`tests/test_tool_palette.py` looks for pixels with red > 190, 110 < green < 190,
  blue < 110: `TINT_CITRINE` qualifies); no two tools share an icon.

### 9.5 Layout

```
+--------------------------------------------------------------------------------------------+
| [mark] File Edit Create Mesh        ( Points | Edges | Polygons | Model )   < > [E] (o Untitled) |  top row 40
+--------------------------------------------------------------------------------------------+
| +----+ +---------------------------------------------------------+ +----------------------+ |
| |rail| | View  Cameras            Perspective          pan zoom orb| | OBJECTS              | |
| |    | |                                                         | |                      | |
| |Sel | |                                                         | +----------------------+ |
| |Move| |                       drawn area                        | | (tool options)       | |
| |Rot | |                                                         | +----------------------+ |
| |Scl | | HUD pill                                                | | ATTRIBUTES           | |
| |Pen | |                                                         | |                      | |
| |----| |              +------ object dock ------+                | +----------------------+ |
| |mesh| |              | Line Null | shapes | gens |               | | Coordinates          | |
| +----+ +---------------------------------------------------------+ +----------------------+ |
| Mode: Model · Tool: Move        Drag to move · Esc cancels      1 object · 0 points · ...  |  status 24
+--------------------------------------------------------------------------------------------+
```

- **Top row** (`QWidget#qsTopBar`, `TOP_BAR_H` 40, `SURFACE_BACKDROP`, margins 8, spacing 8): `menu_bar` (starts at the left
  margin, height 32, centred, size policy Maximum so it takes the width of its items; the app mark is gone), the page switcher when there is more than one page (height `SEGMENT_H`, 2 px of `SEGMENT_PAD` on every side of
  the current button, the same as the mode switcher, so both pills share one vertical centre), `command_bar` (stretch,
  height 40). `MainWindow.fit_top_row()` keeps the menus and the switcher left of the mode switcher with a gap
  of at least 16 (section 12). The mode switcher is centred on the
  window (`CommandBar.center_modes()` recomputes a leading spacer on resize, move and show). Right group, in
  order: Undo, Redo (one segment, `qsRole="history"`), gap 8, Make Editable, gap 8, project chip; it ends 8 px
  from the window edge. `menu_bar` and `command_bar` stay separate regions.
- **Body** (`QWidget#qsBody`, margins 8 left and right, 0 top and bottom): `body_splitter` (horizontal
  `StudioSplitter`, handle `CARD_GAP` 8, invisible at rest, a 4 px rounded bar on hover and drag). Left block (`qsLeftBlock`): the rail (`RAIL_W` 48, fixed),
  gap 8, the viewport (stretch). Right column: `manager_splitter` (vertical, handle 8) with
  `object_manager`, the modeling `ToolOptionsPanel` at index 1 when installed, `attribute_manager`,
  `coordinates` (always last). Default right column width `round(window width * 370 / 1456)` (488 at
  1920, 325 at 1280), or the managers' size hint when wider and there is room, minimum 300. Coordinates
  height fixed at `COORDINATES_H` 120 (the handle above it is disabled); the Hierarchy and the
  Attribute Manager share the rest (the Attribute Manager at least its minimum). The selection options card
  sits after the tool options card while a selection tool with options is active.
- **Cards**: `tool_palette`, `viewport`, `object_manager`, `attribute_manager`, `coordinates` and every
  other widget in `manager_splitter` are marked with `common.make_card(widget)` (dynamic property
  `qsCard=true` plus `WA_StyledBackground`); the QSS rule `QWidget[qsCard="true"]` paints `SURFACE_CARD`,
  1 px `HAIRLINE` and radius `CARD_RADIUS`. Card content keeps its own backgrounds transparent (or inset by
  at least 1 px) so the rounded corners and the border stay visible.
- **Dock** (`object_palette`): a child of the `Viewport` widget, never in a layout. `MainWindow.
  place_object_dock()` (called from an event filter on the viewport and on `viewport.canvas` for resize,
  show and move, and from `apply_default_sizes`) sizes it to its natural width (`sizeHint`, 396 px today)
  but never wider than the canvas minus 24, height `DOCK_H` 48, centred on `viewport.canvas.geometry()`,
  bottom edge `DOCK_BOTTOM` 12 px above the canvas bottom, and raises it. `MainWindow.dock_area()` returns
  that canvas rectangle (in viewport coordinates).
- **Status bar** (`status_bar`, `StatusBar(QStatusBar)` installed with `QMainWindow.setStatusBar`, height
  `STATUS_BAR_H` 24, full width, `SURFACE_BACKDROP`).

Measured on the finished window with the modeling tools installed and no extension, 20/11/2026 (window client area, x and y of the top left corner, then width x height):

| Region | 1920 x 1010 | 1280 x 720 |
|---|---|---|
| `menu_bar` | 36, 4, 235 x 32 | 36, 4, 235 x 32 |
| `command_bar` | 279, 0, 1633 x 40 | 279, 0, 993 x 40 |
| mode switcher (140 x 30) | x 890 to 1030 | x 570 to 710 |
| project chip | x 1843 to 1912 | x 1203 to 1272 |
| `tool_palette` | 8, 40, 48 x 946 | 8, 40, 48 x 656 |
| `viewport` | 64, 40, 1352 x 946 | 64, 40, 792 x 656 |
| `object_palette` (dock) | 542, 925, 396 x 48 | 262, 635, 396 x 48 |
| `object_manager` | 1424, 40, 488 x 340 | 864, 40, 408 x 218 |
| `attribute_manager` | 1424, 388, 488 x 470 | 864, 266, 408 x 302 |
| `coordinates` | 1424, 862, 488 x 124 | 864, 572, 408 x 124 |
| `status_bar` | 0, 986, 1920 x 24 | 0, 696, 1280 x 24 |

The Attribute Manager takes `ATTRIBUTE_FRACTION` (58 percent) of the height left for the Hierarchy and
the Attribute Manager together, and never less than `ATTRIBUTE_SHARE` (26 percent) of the column when the tool
options panel is shown. Builders may change content sizes; they must keep every rule above
(`tests/test_smoke.py::_layout_errors` checks them at 1920 x 1007 and 1280 x 720). The tool rail is aligned to
the top of its card.

### 9.6 Control states

| Control | Rest | Hover | Pressed | Checked | Disabled | Focus |
|---|---|---|---|---|---|---|
| Ghost icon button (Undo, Redo, Make Editable, viewport nav icons, rail scroll arrows) | transparent, icon `ICON_STROKE` | `SURFACE_RAISED`, radius 6 | `SURFACE_PRESSED` | not checkable | icon at `DISABLED_OPACITY`, no fill | 1 px `FOCUS_RING`, radius 6 |
| Rail button and dock button (36 x 36, radius 6) | transparent | `SURFACE_RAISED` | `SURFACE_PRESSED` | `ACCENT_TINT`, icon stroke `ACCENT` (rail only); checked and hovered `ACCENT_TINT_HOVER` | icon at `DISABLED_OPACITY` | ring |
| Mode switcher (`QFrame#qsSegment[qsRole="modes"]`) | container `SURFACE_CARD`, 1 px `HAIRLINE`, radius `SEGMENT_H / 2`; segments transparent | segment `SURFACE_RAISED` pill | `SURFACE_PRESSED` | segment `ACCENT_TINT` pill, icon `ACCENT` | icon at `DISABLED_OPACITY` | ring |
| Push button (`QPushButton`, `qsResetTransform`, tool options buttons) | `SURFACE_RAISED`, 1 px `HAIRLINE`, radius 6, text `TEXT_PRIMARY` | `SURFACE_HOVER`, border `HAIRLINE_STRONG` | `SURFACE_PRESSED` | `ACCENT_TINT`, text `ACCENT` | `SURFACE_CARD`, border `HAIRLINE`, text `TEXT_MUTED` | border `ACCENT` |
| Chip (`QPushButton#qsChip`; no longer used by the Attribute Manager) | transparent, pill, text `TEXT_SECONDARY` | `SURFACE_RAISED`, text `TEXT_PRIMARY` | `SURFACE_PRESSED` | `ACCENT_TINT`, text `ACCENT` | text `TEXT_MUTED` | ring |
| Project chip (`QFrame#qsProjectChip`, not a control) | `SURFACE_RAISED`, 1 px `HAIRLINE`, radius `CHIP_H / 2`, name `TEXT_PRIMARY`, unsaved dot `ACCENT` 6 px | none | none | none | none | none |
| Field (`QLineEdit`, spin boxes, `QLineEdit#qsCoordField`) | `SURFACE_FIELD`, 1 px `HAIRLINE`, radius 6, text `TEXT_PRIMARY` | `SURFACE_FIELD_HOVER`, border `HAIRLINE_STRONG` | as focus | n/a | `SURFACE_CARD`, text `TEXT_MUTED` | border `ACCENT`; text selection `ACCENT_TINT_HOVER` |
| Combo box | as field, chevron `ICON_STROKE` | as field | popup opens (9.7) | n/a | as field | as field |
| Checkbox (14 x 14, radius 4) | `SURFACE_FIELD`, border `HAIRLINE_STRONG` | border `ACCENT_HOVER` | border `ACCENT_PRESSED` | fill `ACCENT`, check `ACCENT_ON` | 40 percent opacity | ring |
| Toggle switch (`common.ToggleSwitch`) | track `SURFACE_RAISED`, knob `TEXT_SECONDARY` | track lighter by one step (`SURFACE_HOVER` / `ACCENT_HOVER`) | `ACCENT_PRESSED` when on | track `ACCENT`, knob `ACCENT_ON` | 50 percent opacity | ring |
| Slider | track `HAIRLINE` 3 px, fill `ACCENT_PRESSED`, round handle `ACCENT` 10 px | handle `ACCENT_HOVER` | handle `ACCENT_PRESSED` | n/a | 40 percent opacity | ring |
| Tree row (Hierarchy, `ROW_H` 24) | transparent, text `TEXT_PRIMARY` | `SURFACE_RAISED` | `SURFACE_PRESSED` | selected: `ACCENT_TINT` with a 2 px `ACCENT` bar at its left edge, text `TEXT_PRIMARY`; selected and hovered `ACCENT_TINT_HOVER` | disabled object: text `TEXT_MUTED` | rename editor: field with focus ring |
| Card header (`PanelTabBar`: `QWidget#qsPanelTabBar`, `QPushButton#qsPanelTab`) | transparent, uppercase letterspaced `TEXT_SECONDARY`, `CARD_HEADER_H` 28, left padding 12 | (several tabs) `TEXT_PRIMARY` | none | the current header stays `TEXT_SECONDARY`; with several tabs the current one is `TEXT_PRIMARY` with a 2 px `ACCENT` underline | `TEXT_MUTED` | ring |
| Collapsible group header | uppercase `TEXT_SECONDARY`, chevron `TEXT_SECONDARY` | `TEXT_PRIMARY` | `SURFACE_PRESSED` | n/a | `TEXT_MUTED` | n/a |
| Menu bar item (`QMenuBar#qsMenuBar`) | transparent, `TEXT_SECONDARY` | `SURFACE_RAISED`, radius 6, `TEXT_PRIMARY` | as open | open: `ACCENT_TINT_BACKDROP`, `ACCENT` | `TEXT_MUTED` | ring |
| Viewport ghost text button (View, Cameras: `QPushButton#qsViewMenu`) | transparent over the canvas, `TEXT_SECONDARY`, height 24, radius 6 | `OVERLAY_BG`, `TEXT_PRIMARY` | as open | open: `ACCENT_TINT_ARGB`, `ACCENT` | `TEXT_MUTED` | ring |
| Scrollbar | 8 px, transparent track, handle `HAIRLINE_STRONG`, radius 4 | handle `TEXT_MUTED` | handle `TEXT_SECONDARY` | n/a | hidden | n/a |
| Splitter gap (`StudioSplitterHandle`, 8 px) | nothing painted (invisible) | 4 px bar, radius 2, inset 24 from each end, `SPLITTER_HOVER` | 4 px bar, `SPLITTER_DRAG` | n/a | the handle above Coordinates: never paints, arrow cursor | n/a |
| Tooltip | `SURFACE_MENU`, 1 px `HAIRLINE`, radius 6, `TEXT_PRIMARY`, padding 4 8 | n/a | n/a | n/a | n/a | n/a |

Press feedback (`widgets/press_feedback.py`) draws the hover and press layers of every button: hover is a
light layer (`TEXT_PRIMARY` colour at about 6 percent, `HOVER_ALPHA` about 14), press is an ink layer
(`SURFACE_FIELD` colour at `PRESS_ALPHA`), the toggle pulse is `ACCENT_TINT_ARGB`. The overlay radius equals
the control radius: `CONTROL_RADIUS` for icon buttons, push buttons, view menus and panel tabs, the pill
radius for segments and chips. Keyboard focus is a 1 px `FOCUS_RING` drawn inside the control's radius;
controls that are `NoFocus` today stay `NoFocus`.

### 9.7 Menus, fold-outs and popups

- Kinds: main menus and context menus are `menu_bar.StudioMenu` (custom painted); fold-outs are `QMenu`
  with object name `qsFoldout` (`FoldoutButton.build_menu`, `IconButton.open_group_menu`); combo popups
  are `QComboBox QAbstractItemView`.
- Every popup goes through `common.prepare_popup(menu)` (frameless, no native shadow, translucent
  background, property `qsPopup=true`) and then paints a rounded rectangle: `SURFACE_MENU`, 1 px `HAIRLINE`,
  radius `MENU_RADIUS` 8, 4 px vertical padding.
- Rows: `MENU_ROW_H` 28, inset 4 px left and right, row radius 6; icon column 28 px wide with
  `MENU_ICON` 16 icons centred; text `TEXT_PRIMARY` at `FONT_POINT_SIZE`; shortcut right-aligned in
  `TEXT_SECONDARY`; submenu arrow `ICON_STROKE`; check marks `ACCENT`.
- Hover: `ACCENT_TINT_MENU` row, text `TEXT_BRIGHT` (the shortcut stays `TEXT_SECONDARY`). Disabled:
  `TEXT_MUTED`, no hover. Separators: 1 px `HAIRLINE`, inset 8, 4 px above and below. Section headers:
  uppercase letterspaced `TEXT_SECONDARY`, `FONT_GROUP_POINT_SIZE`, DemiBold, 24 px tall, not clickable.
- Fold-outs open toward free space: rail to the right, dock above (`popup_side="above"`), top bar below.

### 9.8 Status bar

- `widgets/status_bar.py`: `StatusBar(QStatusBar)` with three labels in `qsStatusBody` (margins 12,
  spacing 12): `mode_label` (`QLabel#qsStatusMode`, left), `hint_label` (`qsStatusHint`, centre),
  `selection_label` (`qsStatusSelection`, right); methods `refresh()`, `mode_text()`, `hint_text()`,
  `selection_text()`. Module functions: `status_texts(scene) -> (left, hint, counts)`, `tool_name(tool)`,
  `tool_hint(tool, mode)`, `selection_text(scene)`; tables `MODE_NAMES`, `TOOL_NAMES`, `TOOL_HINTS`,
  `MODELING_HINT`.
- Left: `Mode: <Points|Edges|Polygons|Model> · Tool: <name>` (tool names as in the HUD: Brush Selection,
  Loop Selection, Ring Selection, Pattern Selection, Fill Selection, Phong Angle Selection, Move, Rotate,
  Scale, Polygon Pen, Pen, Other, or the modeling tool name from `quartz_studio.modeling`).
- Centre, by tool and mode: Brush Selection in Model "Paint over an object to select it · Ctrl deselects ·
  Shift+wheel sizes the brush", in a component mode "Paint to select · Shift adds · Ctrl removes ·
  Shift+wheel sizes the brush"; Loop, Ring and Pattern "Click an edge to select its loop (its ring, a pattern
  along its loop) · Shift adds · Ctrl removes"; Fill "Click a polygon to fill up to the selected edges · Ctrl
  removes"; Phong Angle "Click a polygon to select its smooth area · Shift adds · Ctrl removes"; Move in Model "Drag to move · Esc cancels",
  in a component mode "Drag to move · Hold Ctrl to extrude · Esc cancels"; Rotate "Drag a ring to rotate ·
  Shift snaps to 5° · Esc cancels"; Scale "Drag a handle to scale · Shift snaps to 0.1 · Esc cancels";
  Polygon Pen "Click to add points · Click the first point to close · Enter finishes"; Pen "Click to add
  points · Right click or Enter ends the line"; an interactive modeling tool "Drag in the viewport · Esc or
  right click cancels"; anything else empty. Each hint describes behaviour that exists in the viewport
  code; change the hint when the behaviour changes. The modifier and key names in the hints (Shift, Ctrl,
  Esc, Enter) come from the active profile; with Classic and Standard they read as above.
- Right: `N object(s) · N point(s) · N edge(s) · N polygon(s)` from `scene.active`,
  `scene.object_selected`, `selected_points`, `selected_edges`, `selected_polygons`.
- Updates on `Scene.changed`, `selectionChanged`, `objectsChanged`, `modeChanged`, `toolChanged`. A
  temporary message (`window.statusBar().showMessage`, used by the modeling controller for 4 s) replaces the
  three labels while it shows.
- Look: `SURFACE_BACKDROP`, no item borders; mode text `TEXT_PRIMARY`, hint and counts `TEXT_SECONDARY`,
  `FONT_SMALL_POINT_SIZE`; no buttons.

### 9.9 Builders

Six builders restyle in parallel. Nobody edits a file that is not listed for them; a needed change elsewhere
is reported to the orchestrator. Names marked **frozen** must keep their meaning and signature.

Frozen shared names (already in place):

| Where | Names |
|---|---|
| `main_window` | `REGIONS` (order: menu_bar, command_bar, tool_palette, viewport, object_palette, object_manager, attribute_manager, coordinates, status_bar), `CARD_REGIONS`, `MainWindow.regions` and one attribute per region, `top_bar`, `body_splitter`, `manager_splitter`, `apply_default_sizes()`, `place_object_dock()`, `dock_area()`, `window_icon()`, `file_shortcuts`, `statusBar()` is the `status_bar` region |
| `common` | `make_card(widget)`, `is_card(widget)`, `CARD_PROPERTY` (`"qsCard"`), `prepare_popup(menu)`, `POPUP_PROPERTY` (`"qsPopup"`), `IconButton.popup_side()` / `set_popup_side(side)`, every existing class |
| `command_bar` | `CommandBar.mode_switcher` (the modes `Segment`, `qsRole="modes"`), history segment `qsRole="history"`, `ROLE_PROPERTY`, `project_chip` (`ProjectChip`: `text()`, `shows_unsaved()`, `refresh()`, `dot`, `name_label`), `refresh_project()`, `center_modes()`, `mode_buttons()`, `history_buttons()`, `buttons` in the order Points, Edges, Polygons, Model, Undo, Redo, Make Editable, `MODE_BUTTONS`, `FoldoutButton`, `PaletteStrip`, `SceneBinding` |
| `object_palette` | `ObjectPalette(parent=None, *, orientation=Horizontal, popup_side=None)`, `floating`, `popup_side`, `natural_width()`, `OBJECT_PALETTE_ENTRIES`, `CREATE_COMMANDS`, `PALETTE_GROUPS`, buttons Line, Null, Rectangle, Circle, Cube, Sphere, Text, Subdivision Surface, Extrude, Voronoi Fracture |
| `tool_palette` | `ToolPalette` width `RAIL_W`, `RAIL_PAD`, `strip`, `buttons`, `scroll_bar()`, `arrows_visible()`, `active_tool()`, `scene_tool()`, `TOOL_GAP`, `TOOL_MIN_GAP`, `DIVIDER_HEIGHT`, `SCENE_TOOLS`, `PEN_KEY`, `PEN_COMMANDS` |
| `viewport` | `Viewport.canvas` (direct child of the `Viewport`), `Viewport.menu_bar` with `menus`, `menu_buttons`, `menu_titles()` (`["View", "Cameras"]`), `nav_buttons` (3), `bind_navigation()` |
| `status_bar` | section 9.8 |

Object names and selectors the stylesheet uses: `qsCentral`, `qsTopBar`, `qsMenuBar`,
`qsCommandBar`, `qsSegment` (with `qsRole`), `qsIconButton` (property `flat`), `qsProjectChip`,
`qsProjectDot`, `qsProjectName`, `qsBody`, `qsBodySplitter`, `qsLeftBlock`, `qsToolPalette`,
`qsToolStrip`, `qsToolScroll`, `qsToolScrollArrow`, `qsViewport`, `qsViewportMenuBar`, `qsViewMenu`,
`qsViewportCanvas`, `qsObjectPalette`, `qsManagerSplitter`, `qsObjectManager`, `qsObjectTree`,
`qsObjectRename`, `qsAttributeManager`, `qsObjectHeader`, `qsObjectHeaderTitle`, `qsAttributeSection`,
`qsAttributeError`, `qsCoordinatesManager`, `qsCoordField`, `qsCoordTitle`, `qsAxisLabel`,
`qsResetTransform`, `qsToolOptions`, `qsToolTitle`, `qsToolButton`, `qsPanelTabBar`, `qsPanelTab`,
`qsPanelMenuBar`, `qsPanelMenu`, `qsChip`, `qsDimLabel`, `qsGroupTitle`, `qsMenuSection`, `qsFoldout`,
`qsStatusBar`, `qsStatusBody`, `qsStatusMode`, `qsStatusHint`, `qsStatusSelection`, `qsPlaceholder`,
properties `qsCard`, `qsPopup`, `qsRole`, `flat`.

#### 9.9.1 theme: `theme.py` (stylesheet functions), `widgets/menu_bar.py` (styling only), `widgets/common.py`

- Rewrite `_base_qss()` and `_asset_qss()` with tokens only (no literal colours) for every row of 9.6 and
  for 9.7; keep the rules `QWidget[qsCard="true"]`, `QWidget#qsTopBar`, `QStatusBar#qsStatusBar` (and its
  `::item { border: none; }`) and `QFrame#qsProjectChip`. Do not rename or remove any token; add new ones
  only if this section lacks one, and report them.
- `common.py`: `IconButton` renders the checked state with the icon stroke in `ACCENT` (a second pixmap for
  `QIcon.State.On`); `PanelTabBar` buttons render as card headers (9.6, uppercase through the font, text
  unchanged); `Segment` draws its dividers in `HAIRLINE` (or none) and supports the pill look of
  `qsRole="modes"`; `IconButton.open_group_menu` calls `prepare_popup`; `ToggleSwitch`, `Chip`,
  `CollapsibleGroup`, `FieldRow`, `Separator` follow 9.6. Keep `make_card`, `prepare_popup` and the
  `popup_side` accessors.
- `menu_bar.py` (styling only, no change to menus, wiring or pruning): `StudioMenu` calls `prepare_popup`
  and paints 9.7; `MenuBar` paints 9.6. Replace: `COL_MENU_BG` -> `SURFACE_MENU`, `COL_MENU_BORDER`,
  `COL_MENU_TEAR`, `COL_MENU_SEP` -> `HAIRLINE`, `COL_MENU_HOVER` -> `ACCENT_TINT_MENU`, `COL_MENU_TEXT` ->
  `TEXT_PRIMARY`, `COL_MENU_TEXT_HOVER` -> `TEXT_BRIGHT`, `COL_MENU_SHORTCUT` and `COL_MENU_SHORTCUT_HOVER`
  -> `TEXT_SECONDARY`, `COL_MENU_SECTION` -> `TEXT_SECONDARY`, `COL_MENU_DISABLED` -> `TEXT_MUTED`,
  `COL_MENU_ARROW` -> `ICON_STROKE`, `COL_BAR_BG` -> `SURFACE_BACKDROP`, `COL_BAR_TEXT` -> `TEXT_SECONDARY`,
  `COL_BAR_HOVER` -> `SURFACE_RAISED`, `COL_BAR_OPEN` -> `ACCENT_TINT_BACKDROP` (text `ACCENT`),
  `COL_BAR_NEW` and `COL_BAR_NEW_PALE` -> `TEXT_SECONDARY` (no highlighted menus). Menu icon painters
  (`_fill(p, "#9aa4c8")` and the others near the top of the file, `m_mode_object`, `m_effector`, the gear
  and popout icons in the tear-off row) -> `ICON_STROKE` plus one family tint (9.4).
- Keep `MENU_BAR_H` 32 and the menu bar at its natural width.

#### 9.9.2 icons: `icons.py`, `tools/make_spritesheet.py`

- Redraw every built-in icon to 9.4. Replace: `GROUP_MARK_COLOR` -> `theme.TEXT_SECONDARY`, every `"#ffffff"`
  part -> the stroke colour or `TEXT_BRIGHT`, dark parts (`"#202020"`, `"#262626"`, `"#1e1e1e"`, black with
  alpha) -> `SURFACE_FIELD` or nothing, default colours of `toggle`, `mode_model`, `null`, `sky`, `floor`,
  `environment`, `material`, `python` -> `ICON_STROKE` (with a tint only where 9.4 assigns one),
  `app_logo` -> a crystal in `ICON_STROKE` with a `TINT_MINT` facet, `MODELING_ICON_GREY` -> `ICON_STROKE`
  with the tools tint, the gradient at the `environment` icon -> flat fills. Keep the API of 9.4.
- `make_spritesheet.py`: render every registered icon on `SURFACE_CARD` cells with `HAIRLINE` grid lines
  and labels in `TEXT_SECONDARY`.

#### 9.9.3 viewport: `widgets/viewport.py` and its tests

- The viewport card: keep `Viewport` and `canvas` (direct child); the card look comes from `make_card`
  (already applied by `main_window`); replace the widget's own stylesheet so it does not repaint a square
  `BG_BAR` background, and clip the canvas painting to a rounded rectangle of radius `CARD_RADIUS` (inset
  1 px for the border), or give the canvas a rounded mask.
- Header: the `ViewportMenuBar` stops being a strip above the canvas. View and Cameras become ghost text
  buttons overlaid inside the canvas at the top left (inset 8, height `GHOST_BUTTON_H`); the pan, zoom and
  orbit icons overlay the top right (`NAV_BUTTON`); the view name ("Perspective") is drawn in
  `TEXT_SECONDARY` next to the Cameras button or at the top centre; the axis triad stays at the top right
  below the nav icons. Keep `menu_bar`, `menus`, `menu_buttons`, `menu_titles()`, `nav_buttons` and the
  navigation drag behaviour.
- Background: vertical gradient `VIEWPORT_TOP` to `VIEWPORT_BOTTOM`, no letterbox bands, horizon as a 1 px
  `HORIZON` line.
- HUD: a pill (`HUD_H`, radius `HUD_H / 2`, `OVERLAY_BG`, 1 px `HAIRLINE`, text `TEXT_PRIMARY`, glyph
  `ICON_STROKE` with the tools tint).
- Footer: the "Mode: ... · Tool: ..." text is no longer drawn (the status bar shows it); `footer_left` and
  `footer_right` may stay as attributes.
- Keep the bottom `DOCK_BOTTOM + DOCK_H + 12` px of the canvas free of fixed overlays: the dock lives
  there (it is placed by `main_window`; do not reparent or move it).
- Replace: `VIEW_AXIS_X/Y/Z` and `GIZMO_COLORS` -> `AXIS_X/Y/Z`; `VIEW_TEXT` -> `TEXT_PRIMARY`;
  `VIEW_MENU_TEXT` -> `TEXT_SECONDARY`; `VIEW_NAV_ICON` -> `ICON_STROKE`; `VIEW_CAMERA_BADGE` ->
  `TEXT_SECONDARY`; `LABEL_BOX`, `HUD_BOX` -> `OVERLAY_BG`; `FOOTER_BOX` -> removed; `HORIZON_COLOR` ->
  `HORIZON`; `POLY_OUTLINE` -> `POLY_OUTLINE`; `SELECT_ORANGE` -> `SELECT_FRONT`; `SELECT_BACK_BLUE` ->
  `SELECT_BACK`; `"#8a4200"` -> `SELECT_FRONT_DARK`; `POINT_COLOR` -> `POINT_FILL`; `POINT_BORDER` ->
  `POINT_BORDER`; `EDGE_COLOR`, `LINE_COLOR` -> `WIRE`; `GIZMO_HOVER` -> `GIZMO_HOVER`; `GIZMO_CENTER` ->
  `ICON_STROKE`; `GIZMO_VIEW_RING`, `PIVOT_COLOR` -> `TEXT_BRIGHT`; `NGON_GUIDE_COLOR` -> `ACCENT`;
  `PEN_PREVIEW`, `PEN_CHAIN_POINT` -> `TEXT_PRIMARY`; `PIVOT_OUTLINE` and every `QColor(20, 20, 20, a)` ->
  `SHADOW`; `QColor(255, 255, 255, 10)` -> `HAIRLINE`; the HUD glyph `"#c4c4c4"` -> `ICON_STROKE`.
- Tests: update the viewport tests that read colours or the footer; the selection-colour semantics (front
  warm, back cool) must stay tested.

#### 9.9.4 palettes: `widgets/tool_palette.py`, `widgets/object_palette.py`, `widgets/press_feedback.py`, their tests

- Rail: already a card (`make_card(self)`, width `RAIL_W`, padding `RAIL_PAD`). Buttons `PALETTE_BUTTON`
  36 with icons `PALETTE_ICON` 24 (today `TOOL_ICON` 31: reduce); states 9.6; divider a 1 px `HAIRLINE`
  inset 8; scroll arrows are ghost buttons with `TEXT_SECONDARY` chevrons. Restyle the tool icons painted
  in this file (`pal_live_selection`, `pal_move`, `pal_rotate`, `pal_scale`, `pal_pen`, ...) to 9.4 with
  `TINT_CITRINE` (replace `theme.ICON_ACCENT_ORANGE` in the selection icon and `theme.ICON_SPLINE_PEN` in the
  pen with `ICON_TOOL`).
- Dock: keep `paintEvent` (`DOCK_BG`, 1 px `HAIRLINE`, `DOCK_RADIUS`); buttons `DOCK_BUTTON` with
  `DOCK_ICON`; between groups a `DOCK_GAP` gap with a centred 1 px `HAIRLINE` divider 24 px tall; fold-out
  mark 9.4; fold-outs above. Restyle `pal_null`, `pal_volume_builder`, `pal_voronoi`, `pal_extrude`,
  `pal_sphere` to 9.4 (no `lighter()` / `darker()`). `CATEGORY_COLORS`: null none, spline `ICON_SPLINE`,
  mesh `ICON_MESH`, generator `ICON_GENERATOR` (already set).
- `press_feedback.py`: 9.6 press feedback; `_RADIUS_BY_NAME` from tokens (`qsPanelTab`, `qsPanelMenu`,
  `qsViewMenu`, `qsResetTransform`, `qsIconButton` -> `CONTROL_RADIUS`; `qsChip` -> `CHIP_H / 2`); no colour
  literals.
- Tests: keep the 1080 and 720 rail checks and the scroll checks; `_neutral()` in
  `tests/test_press_feedback.py` points at empty top bar space (it uses `menu_bar` plus (700, 10); move it if
  the top row changes).

#### 9.9.5 managers: `widgets/object_manager.py`, `widgets/attribute_manager.py`, `widgets/coordinates.py`, their tests and `tests/test_interface_defects.py`

- Each region is already a card. Header: the `PanelTabBar` header (keep the `tabs` attribute and its
  buttons; `tests/test_press_feedback.py` uses `object_manager.tabs._buttons[0]`). Content inset
  `CARD_PADDING`, transparent backgrounds so the card's corners show; a `HAIRLINE` rule under the header
  at most.
- Hierarchy (object manager): rows `ROW_H`, states 9.6 (selected row: `ACCENT_TINT` plus the 2 px `ACCENT` bar).
  Replace: `ROW_SELECTED_BG` -> `ACCENT_TINT`, `ROW_SELECTED_HOVER_BG` -> `ACCENT_TINT_HOVER`,
  `ROW_HOVER_BG` -> `SURFACE_RAISED`, `CHECK_COLOR` -> `STATUS_OK`, `CROSS_COLOR` and `DROP_INVALID_COLOR`
  -> `STATUS_ERROR`, `DROP_COLOR` -> `ACCENT`, `DIVIDER_COLOR` and `RULE_COLOR` -> `HAIRLINE`, the rename
  editor `"#1f1f1f"` -> `SURFACE_FIELD` with the `ACCENT` focus border. Object icons: spline kinds
  (`Line` included) use `ICON_SPLINE` (update the test that pins `ICON_PRIMITIVE` for the line).
- Attribute Manager: `SECTION_LINE` -> `HAIRLINE`, `ERROR_COLOR` -> `STATUS_ERROR`, the section title
  `"#e6e6e6"` -> `TEXT_PRIMARY`; chips, fields, checkboxes, groups per 9.6.
- Coordinates: `"#363636"` (disabled Reset) -> `SURFACE_CARD` with `HAIRLINE` border, `"#8e8e8e"` and
  `"#858585"` -> `TEXT_SECONDARY`, `"#6c6c6c"` -> `TEXT_MUTED`; fields per 9.6, axis letters in
  `AXIS_X/Y/Z`.
- Everything must fit at 1280 x 720 (column 376 px wide; 270 / 269 / 101 px tall, or 153 / 218 / 160 / 101 with
  the tool options panel): no horizontal overflow in any Object tab (`test_interface_defects`).

#### 9.9.6 topbar: `main_window.py`, `widgets/command_bar.py`, `widgets/status_bar.py`, `widgets/context_menu.py` (styling hooks only), `tests/test_smoke.py`, `tests/test_wiring.py`, `tests/test_context_menu.py`

- Top row per 9.5 (built): mode switcher pill (`SEGMENT_H`, segments about 34 x 26 inside), Undo and Redo
  ghost buttons, Make Editable ghost button, project chip. `FoldoutButton.build_menu` calls
  `prepare_popup`. Restyle the icons painted in `command_bar.py` (`pal_mode_points`, `pal_mode_edges`,
  `pal_mode_polygons`, `pal_mode_model` and the unused `pal_*` bar icons) to 9.4 with `TINT_MINT`: replace
  every `"#ffffff"`, `"#f2f2f2"`, `"#d9d9d9"`, `"#bdbdbd"`, `"#8e8e8e"`, `"#ececec"`, `"#2e2e2e"` and the
  `lighter()` / `darker()` shading.
- Status bar per 9.8 (built): only styling and wording may change, and only to describe real behaviour.
- `context_menu.py`: context menus are `StudioMenu`s, so they inherit 9.7; add only styling hooks (for
  example an object name `qsContextMenu`), no behaviour.
- `main_window.py`: the `Placeholder` uses tokens already; keep the dock placement and the card marking.
- Keep `_layout_errors` and the wired-controls guard passing; extend them when a control is added.

#### 9.9.7 Files owned by nobody in this phase

Done by the integration step: `app.py` (`_dark_palette` uses `TEXT_BRIGHT`, `HAIRLINE_STRONG`, `HAIRLINE`,
`SURFACE_RAISED`, `SURFACE_FIELD`, `SURFACE_BACKDROP`; `Highlight` is `ACCENT_TINT_HOVER` and `HighlightedText`
is `TEXT_BRIGHT`, because dark text on the tint would not be readable), `modeling/interaction.py`
(`SELECT_FRONT`, `SELECT_FRONT_SOFT`, `TEXT_PRIMARY`, `SHADOW`), `modeling/panel.py` (hairline rule, uppercase
letterspaced card header, no local background), `title_row.py` and `sculpt_bar.py` (tokens only; not in the
window).

### 9.10 Acceptance for the build

- All suites pass (`runall`), including `tests/test_smoke.py` at both sizes.
- Snapshots at 1920 x 1010 and 1280 x 720 (`tools/snapshot.py`) show the Crystal look: ink surfaces, rounded
  cards with 8 px gaps, no black lines, no grey slabs, checked controls as tints.
- No colour literal in the package outside `theme.py` (search for `#` followed by six hex digits and for
  `QColor(` with numbers). Only the shading helpers of `title_row.py` and `sculpt_bar.py` (not in the window)
  still derive colours with `lighter` and `darker`.
- `assets/quartzInstance.ico` is byte for byte unchanged and identical to `D:\Icons\quartzInstance.ico`.

### 9.11 As built

Differences between the plan above and the finished window, and known limits:

- Tool rail: aligned to the top of its card; its fold-outs open 4 px outside the card edge. Dock fold-outs open
  4 px above the dock (`confine_popup(button, shift)` in `tool_palette.py`).
- Tool options card: header is the tool name in the card header style (uppercase, letterspaced,
  `TEXT_SECONDARY`), with the modes on the right.
- Icons: `icons.py` registers the Crystal versions of the `pal_*`, `pal_brush_*`, `m_line`, `tr_*` and `mt_*`
  names first, so the older painters in `command_bar.py`, `tool_palette.py`, `object_palette.py`, `menu_bar.py`,
  `sculpt_bar.py` and `title_row.py` run only as a fallback. The `view_*` names registered by `viewport.py`
  are pinned. A `color` passed to `icon()` is the stroke colour, except when it is one of the four tints,
  which then act as the tint and leave the stroke neutral.
- Spin boxes: the theme draws no arrows; the attribute manager draws its own step arrows because they are the
  scrub handle. The coordinate fields and the modeling panel spin boxes show none.
- Tooltips have square corners (Qt tooltips are not translucent). Combo popups are rounded only after
  `common.prepare_combo(combo)`, which `combo_row`, the attribute manager combos and the tool options panel combos call.
- Menus taller than the screen wrap into columns; the painting uses each row's own geometry. The Mesh menu and
  the Polygons context menu are about 780 px tall.
- The mode and history segments are real `Segment`s; the mode pill is 30 px tall with 34 x 26 segments.
- The status bar hint is built from the registry for modeling tools (`status_bar.modeling_hint`) and elides
  with an ellipsis when the window is narrow. The project chip name is elided in the middle at 240 px.
- The window title keeps the contract `<name><*> - Quartz`, `Untitled - Quartz` for a new project (section 5c). On Windows 11 the native title bar is coloured through DWM (`app.apply_native_titlebar`: dark mode, caption colour = backdrop token, text colour = primary text token, border colour = hairline token), keeping the native frame.
- Instance icon: `app.set_instance_identity` sets the AppUserModelID `Quartz.Studio` and the application window
  icon from `assets/quartzInstance.ico`; the main window uses the same file. The desktop shortcut uses it too.
- At 1280 x 720 with the tool options card and a long attribute list the Attribute Manager scrolls.
- `tools/snapshot.py` no longer composes the old reference frame: it renders the window at `--size` (default
  1920 x 1010).

## 10. Trunk

Decided on 19/11/2026. Trunk gives a Line (an editable mesh with points and loose edges, possibly branching, with
any number of ends and cycles) the thickness of a trunk or twig, with a clean quad topology. It exists twice: a
modeling tool `trunk` (destructive, works on the active Line) and a generator `trunk` (non-destructive, skins its
children). Both use one shared algorithm module (10.1) and the per-point thickness scale channel (10.2). Code,
interface text and docs are in English; code files carry no comments or docstrings; every colour comes from
`theme.py` (section 9).

### 10.1 Module `quartz_studio/modeling/trunk_skin.py`

Pure numpy, no Qt and no scene imports. Public API, exactly:

- `profile_radii(points, edges, base, tip, taper=1.0, root="first", scales=None) -> numpy array` of one radius
  per point. `points` is an `(n, 3)` float array, `edges` a sequence of `(a, b)` index pairs. For each connected
  component a root is chosen: `root="first"` takes the end point (valence 1) with the lowest index, or the
  lowest index of the component if it has no end; `root="lowest"` takes the end point with the smallest Y (ties
  by lowest index), or the point with the smallest Y if it has no end. With `d_root(p)` the path length from the
  root in the shortest-path tree and `d_down(p)` the longest path length from `p` to a leaf going away from the
  root, `t(p) = d_root / (d_root + d_down)` (0 at the root, 1 at every tip; 0 when both are 0). Radius =
  `(tip + (base - tip) * (1 - t) ** taper) * scale(p)`, where `scales` is an optional array of per-point
  multipliers (default 1.0). Points not used by any edge get radius 0.
- `build_skin(points, edges, radii, sides=8, caps=True) -> (new_points as (m, 3) float array, polygons as list
  of tuples of indices)`. It skins the graph given by the edges; points not used by any edge are ignored.

Clean topology, the contract of `build_skin`:

- Along every limb (run of points of valence 2 between ends and junctions) the skin is a tube of quads with
  `sides` quads per ring, rings placed at the points on the bisector plane of the two segments (mitred, with the
  ring stretched so the tube keeps its radius on both sides, and a limit on that stretch for very sharp bends),
  oriented by a rotation-minimising frame so the tube does not twist.
- An end (valence 1) is closed by one n-gon cap when `caps` is on and left open when off; a radius of 0 (below
  1e-6) at an end makes a cone apex (one point, a fan of triangles) with no cap.
- A junction (valence 3 or more) is one watertight patch that joins the rings of its limbs: place one ring per
  incident limb, set back from the junction point far enough for the rings not to intersect each other (clamped
  by the length of the segment), and close the gap with the convex hull of those ring points with the ring discs
  removed; pairs of hull triangles that are coplanar within a tolerance are merged into quads. No limb passes
  through another, there are no interior faces and no overlapping faces.
- The result with caps on is a closed 2-manifold per connected component: every edge is shared by exactly two
  polygons with opposite direction, normals point outward (positive signed volume), no polygon has zero area or
  repeated indices, no two points coincide, and the Euler characteristic is 2 for a tree (0 for a component with
  one cycle). With caps off the only open edges are the end rings.
- Cycles in the graph (a closed loop, or a loop with branches) are skinned too. Several components are skinned
  independently. Zero-length edges and duplicate edges are ignored. A segment shorter than the set-back it needs
  must still give a valid manifold (shrink the set-back, or merge the two neighbouring nodes), never a
  self-intersecting or open result.
- Deterministic (same input, same output) and fast: 2000 points in a random tree with `sides=8` in under 1.5 s.

Caller rule (tool and generator): radii come from `profile_radii`; then every point that is not an end
(valence other than 1 in the skinned edge set) gets `max(radius, MIN_RADIUS)` with `MIN_RADIUS = 1e-3` cm, so
only ends can reach 0 (cone apex). A caller never passes an internal zero radius to `build_skin`. `MIN_RADIUS`
is a module constant of each caller (`ops_trunk.py` and `gen_trunk.py`); `trunk_skin.py` keeps exactly the
public API above and is not edited by the builders.

### 10.2 Thickness scale channel (`Mesh.point_scales`)

One float per point, a multiplier of the profile radius at that point. It lives on the `Mesh`, so it travels
with every mesh copy, undo snapshot and tool session. It is meaningful only on editable objects and is ignored by
everything except Trunk.

API (`quartz_studio/scene.py`):

| Name | Meaning |
|---|---|
| `Mesh(points, polygons, loose_edges=(), *, point_scales=None)` | optional channel; a value whose length is not the point count is ignored (absent) |
| `Mesh.point_scales` | property: `numpy (n,) float` or `None` (absent = every point 1.0). Never edit the returned array in place; assign a new one |
| `Mesh.point_scales = values` | setter: `None` or exactly `n` numbers (else `ValueError`); non-finite values become 1.0, negative values 0.0; an all-1.0 array is stored as `None` |
| `Mesh.point_scale_array()` | a new `(n,)` array, ones when absent; the call every reader uses |
| `Mesh.point_scales_explicit` | `True` when the channel was assigned (even to `None`) and the point count has not changed since |
| `Scene.point_scales(obj=None) -> ndarray` | copy of `point_scale_array()` of `obj` (default: the active object); empty array when there is no object |
| `Scene.set_point_scales(indices, values, obj=None) -> bool` | `values` is one number or one per index (another length raises `ValueError`); out of range indices are skipped |
| `Scene.multiply_point_scales(indices, factor, obj=None) -> bool` | `factor` is one number or one per index; a repeated index is multiplied once |

`set_point_scales` and `multiply_point_scales` act only on an editable object of the scene (else `False`), return
`False` when nothing changes, record one undo step of kind `"scales:<id>"` (a continuous mouse drag on the same
object coalesces into one step, like `"move"` and `"param:"`) and emit `Scene.changed` (which re-evaluates the
generators above the object). They do not depend on the mode.

Invariants: the stored array always has the point count of its mesh, or the channel is absent; it is never
misaligned. The getter drops the channel (reads `None`) as soon as the point count differs from the count it was
set for, so a tool that knows nothing about it can never crash on it or read stale values. Values are finite and
at least 0.

What keeps it and what resets it:

| Operation | Effect |
|---|---|
| moving points in place (Move, Rotate and Scale gizmos, `move_selection`, transform tools) | kept |
| undo and redo (snapshot key `"scales"`, a copy) | kept |
| `meshkit.clone`, `scene._copy_mesh`, Make Editable (copies the mesh), the `bridge` full document | kept |
| `Mesh.add_point` (Line pen, Polygon Pen, `extrude_selection`, every tool that grows through `add_point`) | the new point gets 1.0 |
| `meshkit.compact` | remapped (`scales[used]`); an explicit `None` stays explicit |
| `meshkit.weld` | remapped; a merged point keeps the value of its root (the point it welds onto) |
| a tool run through `ToolSession` that returns a mesh without an explicit channel (Delete, Dissolve, Optimize, cuts, merges, ...) | `meshkit.carry_point_scales(base, result)`, called by `ToolSession.apply`: when the result has the base's point count, polygons and loose edges (only positions changed) the channel is copied as is; otherwise each result point that sits exactly (bit for bit, `-0.0` equal to `0.0`) at the position of a base point takes that point's value, the others 1.0. Deleting points therefore keeps the scales of the survivors |
| a mesh change of the point count by raw array assignment outside a tool session | reset to absent |
| `.quartz` save and open | kept (10.3) |
| interchange export (`bridge.document_from_scene`: FBX, glTF, OBJ, PLY, STL) | dropped; exporters never read it |
| import of other formats, parametric builds, generator outputs | absent |

### 10.3 File format

`fmt_quartz` writes the optional key `"point_scales"` (a list of one number per point) inside the `"mesh"` of an
editable object only when the channel is present; the format version stays 1. A file without the key opens with
the channel absent, and a project whose scales are all 1.0 is written byte for byte as before. On load the key
must be a list of finite numbers (magnitude at most `LIMIT`) with one entry per point, else `FileFormatError`
(`"<file>: object <i>: point_scales must hold one number per point"`). Older builds ignore the key.

### 10.4 Hooks for the builders

- Generator: `BuildInput.mesh.point_scales` and `BuildInput.mesh.point_scale_array()` are aligned with
  `BuildInput.mesh.points`. `Scene._make_input` concatenates the channels of the child and its drawn descendants
  (ones for a part without one; absent when no part has one). Parametric children (spline objects) have none.
  The generator signature includes the channel of every editable child, so any change of a child's scales (scene
  accessor, tool session, undo followed by an edit) rebuilds the generator on the next `Scene.changed`. Radii are
  in the generator's local units (the child transform moves and bends the line; it does not scale the radius).
- Tool session: `ToolSpec.apply(mesh, sel, params)` receives `clone(base_mesh)`, channel included. A points-mode
  apply returns `OpResult(mesh, sel)` with the same points and edges and a new channel assigned through the
  setter (`mesh.point_scales = new`). The session records one `"modeling"` undo step per session, as for every
  tool, and `cancel()` restores the base mesh with its channel. A tool that wants to clear the channel assigns
  `None` explicitly (`carry_point_scales` leaves an explicit channel alone).

### 10.5 Tool `trunk` (`quartz_studio/modeling/ops_trunk.py`)

`register(ToolSpec(...))`:

| Field | Value |
|---|---|
| `id` / `name` | `"trunk"` / `"Trunk"` |
| `modes` | `("edges", "points")` (`install.activate_tool` switches Model or Polygons mode to Edges) |
| `interactive` | `True` |
| `drag_param` / `drag_kind` | `"thickness"` / `"percent"` (`interaction.drag_amount`: 0.5 percent per pixel) |
| `menu` / `section` | `"Mesh"` / `"CREATION TOOLS"` |
| `shortcut` | `"M~R"` (free: no tool, no menu entry and no test uses it) |
| icon | `"mt_trunk"` (`icons.modeling_icon_name("trunk")`; `ToolSpec.icon` stays `None` like the other tools) |
| `description` | `"Gives a Line the thickness of a trunk or twig, with a clean quad skin."` |
| `extra` | `{"drag_params": {"edges": "thickness", "points": "point_scale"}, "drag_from_default": ("point_scale",), "preview": "skin_wire"}` |

Params, in this order, group `"Options"` (`modes=()` means both modes):

| key | label | kind | default | min | max | step | unit | modes |
|---|---|---|---|---|---|---|---|---|
| `sides` | Sides | int | 8 | 3 | 64 | 1 | | |
| `base_radius` | Base Radius | distance | 10.0 | 0.0 | 1e6 | 0.5 | cm | |
| `tip_radius` | Tip Radius | distance | 2.0 | 0.0 | 1e6 | 0.5 | cm | |
| `taper` | Taper | float | 1.0 | 0.1 | 10.0 | 0.1 | | |
| `caps` | Caps | bool | True | | | | | |
| `root` | Root | choice | `"First Point"` (choices `"First Point"`, `"Lowest Point"`) | | | | | |
| `thickness` | Thickness | percent | 100.0 | 1.0 | 10000.0 | 1.0 | % | |
| `point_scale` | Point Scale | percent | 100.0 | 1.0 | 10000.0 | 1.0 | % | `("points",)` |

`root` maps to `profile_radii(root="first" | "lowest")`. `taper` 1 is linear, above 1 thins early, below 1 stays
thick and thins near the tip.

Edges mode ("all at once"), `apply(mesh, sel, p)`:

1. Refusals (`OpResult(mesh, sel, False, message)`): no loose edge in the mesh: `"Trunk: the object has no
   loose edges"`; edges selected but none of them loose: `"Trunk: select loose edges of a Line"`; `base_radius`
   and `tip_radius` both 0: `"Trunk: Base Radius and Tip Radius are both 0"`.
2. Edge set: the selected edges that are loose, or every loose edge when no edge is selected.
3. Radii: `profile_radii(points, edges, base, tip, taper, root, scales=mesh.point_scale_array())` times
   `thickness / 100`, then the caller rule of 10.1; then `build_skin(points, edges, radii, sides, caps)`.
4. Result mesh: the original mesh without the skinned loose edges, compacted with `meshkit.compact(mesh,
   keep=<points used by no edge and no polygon before the apply>)`, so the points left unused by the skin are
   removed and the remaining points keep their scales; then the skin points appended. Build the result in one
   constructor call, `Mesh(np.vstack([kept.points, skin_points]), polygons, loose, point_scales=np.concatenate(
   [kept.point_scale_array(), np.ones(len(skin_points))]))` (never `kept.points = np.vstack(...)`, which drops
   the channel). Polygons: the original
   polygons plus the skin polygons (offset); loose edges: the ones that were not skinned. One undo step (the
   session). Selection after applying: `Selection("edges")` (Edges mode, nothing selected), so the mode does not
   change and the options card keeps re-applying from the original Line while the session lives.
5. Live behaviour: the usual interactive flow. A drag in the viewport starts a session and changes `thickness`
   (start value: the current value); options card edits re-apply from the session's base mesh.

Points mode ("point by point, like the Scale tool"), `apply(mesh, sel, p)`:

1. Refusals: no loose edge: `"Trunk: the object has no loose edges"`; no point selected: `"Trunk: select points
   to scale their thickness"`.
2. Result: the same mesh (points, polygons and loose edges unchanged) with the channel `scales[selected] *=
   point_scale / 100` assigned through the setter. Selection unchanged. The mesh stays a Line.
3. Drag: each drag is one session and one undo step; `point_scale` starts at its default (100) at every drag
   (`extra["drag_from_default"]`), so a drag multiplies the current scales of the selected points.

Both modes: on an object that is not editable, `"Trunk: Make Editable first"` (the existing
`EDITABLE_MESSAGE`); in a mode the tool does not support, the existing `"Trunk: select edges or points first"`.

Interaction changes (`modeling/interaction.py`, builder "tool"):

- Per-mode drag param: `spec.extra.get("drag_params", {}).get(scene.mode, spec.drag_param)` replaces
  `spec.drag_param` in `_on_move` and `_begin_drag`; a key listed in `extra["drag_from_default"]` starts the drag
  from `param.default` instead of the current value. Tools without these keys behave exactly as before.
- Points-mode preview: a new attribute `ToolOverlay.preview_wire: tuple[np.ndarray, np.ndarray] | None` (world
  points `(m, 3)` and edge index pairs `(k, 2)`), painted in `paintEvent` before `hover_edge`: the points are
  projected at paint time with `self.parentWidget().project_world(points)` (so camera moves need no recompute),
  segments with a NaN end are skipped, pen `QColor(PREVIEW_COLOR)` (`theme.SELECT_FRONT_SOFT`), width 1.0,
  solid, antialiased. `clear()` resets it and the early return of `paintEvent` takes it into account.
  `ViewportToolFilter` refreshes it, coalesced with `QTimer.singleShot(0, ...)`, on `Scene.changed`,
  `selectionChanged`, `modeChanged`, `ModelingController.paramsChanged` and `toolChanged`: when `_spec()` is the
  `trunk` spec, the scene is in Points mode and the active object is editable with loose edges, `preview_wire =
  (obj.to_world(pts), edges)` from `ops_trunk.preview_wire(mesh, params)`; otherwise `None`.
- `ops_trunk.preview_wire(mesh, params) -> (points (m, 3) float in object space, edges (k, 2) int)`: skins every
  loose edge of the mesh exactly as the edges-mode apply would with no edge selected (Thickness included) and
  returns the unique edges of the skin polygons; empty arrays where the apply would refuse.

### 10.6 Generator `trunk` (`quartz_studio/objects/gen_trunk.py`)

`register(ObjectSpec(id="trunk", label="Trunk", category="generator", build=build_trunk, inputs="children",
icon="trunk", description="Gives every Line child the thickness of a trunk or twig.", params=...))`, params in
this order, group `"Object"`:

| key | label | kind | default | min | max | step | unit |
|---|---|---|---|---|---|---|---|
| `sides` | Sides | int | 8 | 3 | 64 | 1 | |
| `base_radius` | Base Radius | distance | 10.0 | 0.0 | 1e6 | 0.5 | cm |
| `tip_radius` | Tip Radius | distance | 2.0 | 0.0 | 1e6 | 0.5 | cm |
| `taper` | Taper | float | 1.0 | 0.1 | 10.0 | 0.1 | |
| `caps` | Caps | bool | True | | | | |
| `root` | Root | choice | `"First Point"` (`"First Point"`, `"Lowest Point"`) | | | | |
| `use_point_scales` | Use Point Scales | bool | True | | | | |

`build_trunk(p, inputs)`: each input whose `mesh.loose_edges` is not empty (a Line, a spline object, or a mesh
that still has loose edges) is skinned on its own: its loose edges only (its polygons are ignored), radii from
`profile_radii` with `scales=inp.mesh.point_scale_array()` when `use_point_scales` is on (else `None`), the
caller rule of 10.1, then `build_skin`. The skins are joined into one `Mesh` (points stacked, polygon indices
offset, no loose edges, no channel). Inputs without loose edges are ignored. No usable input, or both radii 0:
`Mesh.empty()` with no error (the convention of the other generators, section 7.2). An exception from
`trunk_skin` is not caught: the scene shows `"<ExceptionType>: <message>"` in `obj.error` and an empty mesh.
Editing a consumed child as the active object (moving points, the Line pen, the Trunk tool in Points mode)
rebuilds the generator live (10.4).

### 10.7 Interface placement

- Tool rail: `modeling/install.py` `PALETTE_GROUPS`, group `"Extrude"`, after `"thicken"`:
  `("extrude", "inset", "matrix_extrude", "smooth_shift", "thicken", "trunk")`.
- Mesh menu: section CREATION TOOLS; `widgets/menus_data.py` gets `item("Trunk")` right after `item("Thicken")`
  in `MESH_MENU` (no shortcut text; `install._place_tool` fills in `M~R`). The Points and Edges context menus
  list it as its own item (`context_menu._mesh_nodes` lists every Mesh menu tool that supports the mode); the
  Polygons and Model menus do not.
- Object dock: `widgets/object_palette.py` `PALETTE_GROUPS`, fold-out `"Extrude"` (the spline-input
  generators), after `"spline_mask"`. Create > Generator: `menus_data._GENERATORS` gets `item("Trunk", None,
  "trunk")` after `item("Spline Mask", None, "generator")`; `menu_bar.object_menu_path` wires it from the spec.
- Icons (`icons.py`, section 9.4): `@_mt("trunk")` (name `mt_trunk`, tools tint `TINT_CITRINE`) and
  `@_builtin("trunk", AMETHYST)` (name `trunk`, generators tint), both original drawings of a tapering, branching
  tube, distinct from every other icon.
- Status bar (`widgets/status_bar.py`): a per-mode table checked first by `tool_hint`, `MODE_HINTS =
  {("trunk", "edges"): "Drag sideways to change Thickness · Apply skins the Line · Esc cancels", ("trunk",
  "points"): "Click to select points · Drag sideways to scale their thickness · Esc cancels"}`; other modes fall
  back to `modeling_hint`. The generator needs no hint; the Attribute Manager builds its rows from the spec.

### 10.8 File ownership

| Owner | Files |
|---|---|
| contract (done) | `scene.py`, `modeling/meshkit.py`, `modeling/session.py`, `fileio/fmt_quartz.py`, `fileio/bridge.py`, `fileio/model.py` (unchanged), `tests/test_trunk_foundation.py`, `SPEC.md` |
| skin | `modeling/trunk_skin.py` and its test |
| builder "tool" | `modeling/ops_trunk.py` (new), `modeling/interaction.py`, `modeling/panel.py`, `modeling/install.py`, `icons.py` (both icons), `widgets/status_bar.py`, `tests/test_trunk_tool.py` (new) |
| builder "generator" | `objects/gen_trunk.py` (new), `widgets/object_palette.py`, `widgets/menus_data.py` (the Mesh menu item and the Create > Generator item), `tests/test_trunk_generator.py` (new) |
| integration (after the builders) | shared tests (`test_smoke.py`, `test_wiring.py`, `test_tool_palette.py`, `test_context_menu.py`, `test_objects_ui.py` and the like), `README.md`, sections 3.4 and 3.6 of this file |

No file has two owners. `trunk_skin.py` is imported by both builders and edited by neither.

### 10.9 As built

Verified on 20/11/2026: the full test run ends with 0 failed, no code file has a comment or docstring, and the
end-to-end walk-through (Line pen, Trunk tool in Points and Edges mode, undo, generator with Alt, Attribute
Manager edits, moving a child point, context menus, save and reopen) passes offscreen at 1920 x 1010 and
1280 x 720. Where the build differs from sections 10.1 to 10.7, or has a limit:

- Skin (`trunk_skin.py`):
  - A loop smaller than its own radii is filled in as one solid blob (Euler characteristic 2, not 0).
  - Junctions, or a junction and an end, closer than the set-back they need are merged into one hull patch; an
    end inside such a patch loses its own cap, so with caps off it leaves no open ring.
  - A bend sharper than about 127 degrees (cosine below -0.6) gets a small hull patch instead of a mitred ring;
    gentler bends use the mitred ring with the stretch limited to 2x.
  - A radius of 0 at an interior point is raised to 1e-3 of the largest radius of its component; a component
    whose radii are all 0 produces nothing.
  - Not covered: limbs of different branches that cross each other in space are not checked for
    self-intersection (only the cases above are tested). Timing: 2000 points in a random tree, 0.83 s.
- Tool (`ops_trunk.py`):
  - Extra edges-mode refusal: `"Trunk: the radii leave nothing to skin"` when the radii leave nothing to skin
    (for example a 2-point Line whose scales are 0).
  - `MIN_RADIUS = 1e-3` is a constant of `ops_trunk.py` and of `gen_trunk.py`, not of `trunk_skin.py`.
  - The two drag parameters per mode live in `ToolSpec.extra["drag_params"]` and `extra["drag_from_default"]`;
    `ToolSpec` still has one `drag_param`.
  - The wire preview is skipped above `SKIN_PREVIEW_BUDGET = 600` points of the Line; the status bar then says
    `"Trunk: preview skipped, the Line has more than 600 points"`, once.
  - The preview is refreshed on `Scene.changed`, `selectionChanged`, `modeChanged`, `objectsChanged`,
    `paramsChanged` and `toolChanged`, coalesced with `QTimer.singleShot(0)`, and only when its inputs changed.
  - Dragging in Points mode changes the scale by 0.5 percent per pixel (80 px gives 140 percent).
- Generator (`gen_trunk.py`): zero-length, duplicate and looped edges of a child are dropped before valences are
  counted, so a point that only touches a zero-length edge is never taken as interior.
- Interface: Mesh menu and generator menu entries are as in 10.7. Undo of a generator creation recreates the
  objects, so tests look the generator up by `kind` again.
- Shared tests pinned for Trunk: `test_tool_palette` (Extrude fold-out lists six tools and `mt_trunk`),
  `test_objects_ui` (dock fold-out and Create > Generator order), `test_context_menu` (Trunk listed in the Points
  and Edges context menus, not in the Polygons one). The `PALETTE_GROUPS` of the dock gained `"trunk"` and the
  mesh tool count went up by one; no existing pinned list or count had to change.
- Not verified: the merging of scale changes into one undo step during a held real mouse button (tests use
  synthesised presses, moves and releases, one session per drag), and Alt on a fold-out entry through a real
  keyboard (the e2e uses `QTest.mouseClick` with the Alt modifier on the dock button after choosing Trunk).
- Not run: `build.ps1`; `Quartz.exe` was not rebuilt, so the executable does not contain Trunk yet.

## 11. Controls and profiles

The contract is `specs/controls.md`; `specs/plan.md` section 1 (D6 to D14) settles its conflicts with the
other contracts.

- Package `quartz_studio/controls/`: `actions.py` (the action registry: core actions, every modeling tool,
  every wired menu item as `menu.<slug>`, every selection tool, extension menu items), `profiles.py` (the
  built-in Classic and Standard documents, resolution, binding validation, conflicts, mouse gestures, cursor
  settings, modifier roles, modal keys), `store.py` (the store file), `dispatch.py` (`install(window)`: one
  `QShortcut` per global binding, the `KeyFilter` for chords and viewport keys, the shared held-key set) and
  `editor.py` (the Controls dialog). `__init__.py` holds the frozen API of `controls.md` 5.2;
  `controls.actions` and `controls.profiles` are the submodules made callable.
- Classic is the inventory of `controls.md` section 1 (the keys of the app before profiles, the `M~`, `K~`
  and `U~` chords included, with the three defects of 1.9 fixed); Standard is the shipped default (Q W E R
  tools, F and A framing, 1 to 4 modes, Shift and Ctrl with the middle button). Neither has a conflict.
- Store: `%APPDATA%\Quartz\controls.json` (`controls.STORE_PATH`, or the folder of `project.SETTINGS_FILE`,
  in tests). `app.main` calls `store.first_run()` before the window: with no store it selects Classic on a
  machine that had Quartz before (registry key `HKCU\Software\Quartz\Quartz Studio`), Standard otherwise.
  On this machine the store was written on 20/11/2026 with `"selected": "classic"`.
- Editor: Edit > Controls... (`Shift+F12` in Classic, `Ctrl+,` in Standard). Profile row (Duplicate, Rename,
  Delete, Import, Export), Keyboard page (search, categories, binding chips, recording, conflict banner with
  Replace, Keep Both and Cancel), Mouse page (gesture list and record pad), Cursor page (orbit, pan, wheel,
  click thresholds, modifier roles, modal keys). Built-in profiles are read-only; Duplicate makes an editable
  copy. Every change is saved at once and applied live through `controls.hub().profileChanged`. The dialog is
  deleted once it has been closed (the next Edit > Controls... builds a new one), so its widgets do not stay
  alive for the session.
- Keypad keys with no binding of their own run the binding of the plain key (numpad Enter confirms, numpad
  1 to 3 held navigate). `controls.deferred_refresh()` batches shortcut rebuilds: extension menus added by
  `MenuBar.add_menu` and `add_entries`, and the whole `app.install_extensions`, rebuild the shortcuts once.
  `dispatch` keeps weak references to the installed windows.
- Every place that shows a key (menus, context menus, rail tooltips, the View menu of the viewport, status
  bar hints) reads it from the active profile.

## 12. Wave 1 interface changes

The contract is `specs/interface.md` (sections 1 to 4) with `specs/plan.md` section 1; the attribute changes
follow `specs/attributes-mesh.md` 3 and `specs/attributes-gen.md` 2.

Built:

- `prefs.py`: JSON preferences (`get`, `set`, `changed`, `path`); `%APPDATA%\Quartz\prefs.json` only after
  `prefs.use_user_profile()` (called by `app.main`), a temporary folder otherwise (plan D7).
- Selection tools (`modeling/select_tools.py`, `modeling/select_interaction.py`): Brush Selection (paints with
  a circle; `[`, `]` or Shift+wheel size it; Shift adds, Ctrl removes; picks objects in Model mode), Loop,
  Ring, Pattern, Fill and Phong Angle Selection, the rail fold-out, and an options card in the right column.
  Select > Loop, Ring and Fill Selection in the main menu open the interactive tools (plan D10); the `U~L`,
  `U~B` and `U~F` chords still run the one-shot commands in Classic.
- `widgets/splitter.py`: `StudioSplitter` for the body, the right column, the bottom and the left dock areas.
- Coordinates fixed at 120 px; Attribute Manager rows only (section 3.8).
- Registry kinds and `objects/caps.py` (section 7.1).
- Top row overflow (`MenuBar.set_width_limit`, `MenuBar.hidden_titles`, `MainWindow.fit_top_row`): the mode
  switcher stays centred. When the menus and the page switcher do not fit before it, the page switcher becomes
  one compact button (the current page and a chevron; its menu lists the pages with a check on the current
  one), then the menu bar keeps the menus that fit and moves the rest, in order, into one chevron item at its
  end whose menu lists them as submenus. `MenuBar.titles()` and `MenuBar.menus` still list every menu.
  `tests/test_top_row_overflow.py` checks it with stand-in menus and pages.

Deviations from the contracts:

- The selection options card uses a 160 px label column (the contract says 120), so "Only Select Visible
  Elements" is not clipped.
- The compact page switcher is used whenever the full segmented switcher and every menu do not fit together:
  at 1920 x 1010 with the extension's pages it is compact and every menu is visible; at 1280 x 720 it is
  compact and Sculpt, Animate, Render and Extensions go to the overflow.
- Shift+E, Shift+R and Shift+T no longer switch tools (the binding is the plain key); with a hold key down a
  right click no longer ends an open pen stroke (`controls.md` rule 2.3.4); holding Ctrl+Z no longer repeats
  undo (only actions marked `repeat` repeat).

## 13. Interaction rules and multi-selection

Built after sections 11 and 12. Every gesture below is a row of the active profile (section 11); Classic and
Standard hold the same rows.

- Selection model. `Scene.selected_objects()` is the whole selection; `Scene.active` is the one the managers
  and the gizmo show; `Scene.extra_selected` holds the others. `select_objects(objs, op, active)` takes
  `replace`, `add`, `remove` or `toggle`; `is_object_selected`, `select_all_objects`, `transform_roots`
  (selected objects whose parent is not selected), `duplicate_objects` and `set_transforms` support it. Undo
  snapshots, removal and `set_active` keep it consistent; the file stores it as `selection`.
- Click (left). One thing per click, in every mode and with Move, Rotate, Scale or a selection tool: a click on
  an object (Model) or a point, edge or polygon (component modes) replaces the selection; a click on nothing
  clears it. Shift adds. Ctrl removes; with a transform tool a Ctrl click on something not yet selected adds it
  (it inverts the result of a plain click). The Brush Selection tool keeps Ctrl as remove only and, like the
  other selection tools, adds and removes several objects in Model mode.
- Right click selects the same way and opens the context menu. Right drag selects what the pointer touches
  (a paint stroke, one undo step, no menu); Shift adds, Ctrl removes. Rows: `right+Shift = add`,
  `right+Ctrl = remove`, `profiles.is_paint_gesture`.
- Left drag applies the tool wherever it starts when something is selected, even off the gizmo: Move in the
  plane perpendicular to the camera, Scale on three axes at once (right of the press is bigger, left smaller,
  factor `(85 + dx) / 85`), Rotate about the view axis (0.5 degree per px). Snaps are 5 degrees and 0.1. A press
  on a gizmo handle still constrains. Dragging with nothing selected does nothing. A drag under
  `drag_threshold` is a click. Escape or a right click cancels the drag.
- Ctrl and drag copies: in Model mode Ctrl held when a Move, Rotate or Scale drag starts (free or on a handle)
  duplicates the selected objects with their children and transforms the copies, one undo step, and the
  copies become the selection. In component modes Ctrl and Move extrudes. The status hints say "Hold Ctrl to
  copy" and "Hold Ctrl to extrude".
- Ctrl+A (`tool.select_all`, Classic and Standard): every object in Model mode; every point, edge or polygon
  of the active object in a component mode. It does nothing while a text field has focus.
- Chord popup. After a prefix key (`U`, `M`, `K` in Classic) the `ChordMenu` (`controls/chord_menu.py`) opens at
  the cursor 200 ms later and lists every continuation of the prefix, in registry order, with a separator per
  category, the tool icon, the label and the second key. Entries that do not apply in the current mode are
  grey. A click runs the entry; Escape, a click elsewhere or a key that does not continue the chord closes it.
  The prefix does not expire while it is open. It does not open with a text field in focus or a mouse button
  down; the preference `controls.chord_menu` (default on) turns it off. Classic binds `U~G` Grow Selection and
  `U~K` Shrink Selection (`ops_select.py` carries the same `U~G`); Standard has no prefixes and binds
  `Ctrl+Num++` and `Ctrl+Num+-`.
- Hierarchy panel: Shift and Ctrl click select several rows, selected rows are tinted and the active row has
  the accent bar, Delete removes the whole selection. The context menu commands Enabled, Group Objects,
  Unparent, Select Children and Delete act on the whole selection, one undo step each. The status bar counts
  the selection.
- Top row: the app mark is removed; the menus start at the margin. The page switcher keeps 2 px
  (`SEGMENT_PAD`) between its border and the current button on every side, text and chevron are centred, and
  its menu opens at its outer border.
- Performance and 3D Text (`widgets/viewport.py`, `objects/gen_boole.py`, `objects/gen_spline.py`): the
  viewport keeps per-mesh topology caches and skips n-gon lines and full occlusion while navigating or
  dragging (a 160 ms timer restores them); generators are not rebuilt on camera or selection changes; Boole
  caches each input and rounds its tolerance to a power of two. Concave caps are cut into quads and triangles
  by a constrained Delaunay ear clipper (no fan of one convex n-gon); convex caps stay one n-gon. Known limit:
  the n-gon guide lines of other meshes still come from `Mesh.ngon_guides`.
- Tests: `test_interaction_rules`, `test_multi_selection`, `test_controls_chords`, `test_perf_text`, plus the
  updated `test_smoke`, `test_press_feedback`, `test_modeling_integration`, `test_modeling_select`,
  `test_controls_profiles` and `test_pen`.
