# Quartz Studio

The desktop interface of Quartz, a 3D modeling program. Author: **D1on1n**.

Quartz Studio has its own look, called Crystal: a precision instrument cut from dark glass. Cool blue-black
surfaces, rounded cards separated by 8 px gaps and 1 px hairlines, one mint accent used sparingly, and flat
icons with one neutral stroke plus one family tint. It has a working 3D viewport and a shared scene model.
The window shows only controls that do something: a button, menu item or panel appears when its function
exists and stays out until then. The look and the layout are specified in `SPEC.md`, section 9; every colour,
size, radius and font lives in `quartz_studio/theme.py`.

Layout of the window:

- Top bar (40 px): the menus on the left, the Points, Edges, Polygons and Model switcher as
  one pill in the centre, Undo, Redo, Make Editable and the project chip (file name, with a dot while there
  are unsaved changes) on the right. The pill always stays centred: when an extension adds pages and menus
  that do not fit before it, the page switcher becomes one compact button with a menu of the pages, and the
  menus that do not fit move into a chevron item at the end of the menu bar.
- Left: the tool rail, a rounded card.
- Centre: the viewport, a rounded card. View and Cameras are ghost buttons inside it at the top left, the
  pan, zoom and orbit icons at the top right, the tool HUD is a pill at the bottom left. The object
  creation palette is a floating dock at the bottom centre of the viewport; its fold-outs open upward.
- Right: three stacked cards (Objects, Attributes, Coordinates), plus the tool options card while a
  modeling tool is active and the selection options card while a selection tool with options is active. The
  gaps between cards are splitters: invisible at rest, a thin rounded bar on hover and while dragging.
  Coordinates keeps a fixed height of 120 px.
- Bottom: a 24 px status bar with the mode and tool on the left, a hint for the active tool in the centre
  and the number of selected objects, points, edges and polygons on the right.
- Right click opens a context menu in the viewport (object, component or empty space) and in the Objects panel;
  right click on an attribute row offers Reset to Default.

What is in the window:

- Main menu: File (New Project, Open Project, Open Recent, Merge Project, Save Project, Save Project As, Save Incremental, Import, Export, Exit), Edit (Undo, Redo, Controls...), Create (Null, Spline, Mesh and Generator, with every registered
  parametric object), Select (the selection tools and commands), Mesh (Make Editable, Polygon Pen and the
  modeling tools).
- Command bar: Undo, Redo, Make Editable, and the Points, Edges, Polygons and Model modes.
- Tool rail: the Selection fold-out (Brush, Loop, Ring, Pattern, Fill and Phong Angle Selection), Move,
  Rotate, Scale, the Pen fold-out (Polygon Pen, Pen), a divider and the mesh tool groups.
- Viewport: View and Cameras menus, the pan, zoom and orbit icons.
- Object dock, left to right: Line, Null, then the Rectangle, Circle, Cube, Sphere and Text buttons
  (splines and meshes), then the Subdivision Surface, Extrude and Voronoi Fracture buttons (generators).
  Each button has a fold-out with the other objects of its group. An object that is not registered has
  no entry: Polygon and Spline Mask are missing for now.
- Objects (tree with parents and children, several rows can be selected), Attribute Manager (the object header, a points and
  polygons summary for editable meshes, and one row per parameter for parametric objects; no tabs) and
  Coordinate Manager.

Creating objects: clicking an entry creates the object at the world origin, active and selected, named after
its label. Holding Alt while clicking a generator makes the active object its child. Holding Shift makes
the new object a child of the active object. Make Editable (button, Mesh menu or the `C` key) converts the
active parametric object into a polygon object so the mesh tools can edit it. Parametric objects live in
`quartz_studio/objects/` (see `SPEC.md`, section 7).

Trunk gives a Line the thickness of a trunk or twig, with a clean quad skin (closed, no interior faces). It
exists twice. The Trunk tool (Extrude fold-out of the tool rail, Mesh menu, and the Points and Edges context
menus) works on the active Line: in Edges mode it skins the selected loose edges, or all of them, with Sides,
Base Radius, Tip Radius, Taper, Caps and Root, and a drag in the viewport changes an overall Thickness; in
Points mode a drag scales the thickness of the selected points, like the Scale tool, and the viewport shows a
wire preview of the skin. The Trunk generator (Extrude fold-out of the object dock, Create > Generator) skins
every Line or spline child without changing it, follows edits of the child, and can use the per-point
thickness scales. The shared algorithm is `quartz_studio/modeling/trunk_skin.py` and the details are in
`SPEC.md`, section 10.

Selection tools (rail fold-out and Select menu, `quartz_studio/modeling/select_tools.py` and
`select_interaction.py`):

- Brush Selection paints a selection with a circle in Points, Edges and Polygons mode and picks objects in
  Model mode. Shift adds, Ctrl removes, `[` and `]` or Shift+wheel change the radius. One stroke is one undo
  step. Options: Radius, Only Select Visible Elements, Tolerant Selection.
- Loop, Ring and Pattern Selection select an edge loop, an edge ring or a pattern along a loop from one click;
  Fill Selection fills the polygons up to the selected edges; Phong Angle Selection selects the smooth area
  around a polygon (Angle option). The options are kept in the preferences file (`prefs.json`).

Controls (`quartz_studio/controls/`, details in `SPEC.md` section 11 and `specs/controls.md`):

- Every key and mouse gesture comes from a controls profile. Two built-in profiles: Classic (the keys the
  app always had: `E`, `R`, `T`, the `M~`, `K~` and `U~` chords, `H`, `S`, `O`, `F1` to `F4`, Alt with the mouse
  buttons) and Standard (Q, W, E, R for Selection, Move, Rotate, Scale; F and A to frame; 1 to 4 for the
  modes; Ctrl+E Extrude and the other common keys; Shift and Ctrl with the middle button to pan and dolly).
- Edit > Controls... opens the editor (`Shift+F12` in Classic, `Ctrl+,` in Standard). Built-in profiles are
  read-only: Duplicate one, then record keys, change mouse gestures and cursor settings; conflicts are shown
  with Replace, Keep Both and Cancel. Profiles can be exported and imported.
- The selection and the user profiles are stored in `%APPDATA%\Quartz\controls.json`. On first start the app
  selects Classic on a machine that had Quartz before and Standard otherwise; this machine uses Classic.

File commands (`quartz_studio/project.py`, the formats in `quartz_studio/fileio/`):

- Project: `.quartz` (JSON). The keys below are the Classic and Standard bindings. New Project `Ctrl+N`, Open `Ctrl+O`, Open Recent (last 10 files, kept with
  QSettings, with Clear Recent File List), Merge Project `Ctrl+Shift+O` (adds the file's objects as one undo
  step), Save `Ctrl+S`, Save As `Ctrl+Shift+S`, Save Incremental `Ctrl+Alt+S` (`name_0001.quartz`, then
  `_0002`), Exit `Alt+F4`. The file also stores the viewport camera and view name.
- The window title is `name.quartz - Quartz`, `Untitled - Quartz` for a new project, with
  an asterisk after the name while there are unsaved changes (`name.quartz* - Quartz`). New, Open, Open Recent,
  Exit and closing the window ask Save, Don't Save or Cancel when the project is modified.
- Import (File > Import, drag and drop, or a path on the command line) and Export (one item per format in
  File > Export, plus Export Selection). Directions: FBX, glTF (`.gltf`), glTF Binary (`.glb`), Wavefront
  OBJ, Stanford PLY, STL and Quartz Project are read and written. Imported objects are added as one undo
  step and framed in the viewport; a file the importer rejects is reported in a message and the scene is
  left as it was; warnings from the file are shown once.
- Opening from outside: `launcher.py file.quartz` opens the project, any other supported extension is
  imported; dropping files on the window does the same.
- Every dialog (file pickers, the save question, messages, quit) is a function in `project.py`
  (`choose_open_files`, `choose_save_file`, `ask_save_changes`, `show_message`, `quit_application`), so
  tests replace them. Under the offscreen platform they do nothing and the save question answers Don't Save.
  `tests/test_fileio_ui.py` covers every command.

How a new function gets its control:

- Main menu: add the path and the handler to `SCENE_COMMANDS` in `widgets/menu_bar.py`. The whole menu tree
  stays in `widgets/menus_data.py`; `MenuBar` hides every item that has no handler. Every wired item becomes
  a controls action (`menu.<slug>`) that a profile can bind.
- Tools: add an `Item` to `TOOL_PALETTE_ENTRIES` and the tool name to `SCENE_TOOLS` in
  `widgets/tool_palette.py`.
- Object creation: register an `ObjectSpec` in `quartz_studio/objects/`, add its id to the matching group of
  `PALETTE_GROUPS` in `widgets/object_palette.py` and its label to the Create menu in
  `widgets/menus_data.py`. The palette and `SCENE_COMMANDS` are built from the registry, so only registered
  objects get a button and a menu item.
- Viewport menus: add the entry to `VIEWPORT_MENUS` and bind it in `ViewportMenuBar._bind_menus`.

`widgets/title_row.py` and `widgets/sculpt_bar.py` are not in the window.
They stay in the package for when their functions exist. `tests/test_smoke.py` fails if a control in the
window writes "not implemented" to the log.

What works:

- Scene model in `quartz_studio/scene.py`. Every object is a mesh: the cube, pen faces and Lines.
- Selection, move, point, edge and face extrusion, several objects, mesh picking, framing. Rotation and size
  are edited in the Coordinate Manager.
- Undo and Redo (`Ctrl+Z`, `Ctrl+Y`, and `Ctrl+Shift+Z` in Standard), up to 128 steps. One drag is one step.
- Points, Edges, Polygons and Model modes. Selected elements seen from the front are citrine, selected
  polygons seen from behind are amethyst.
- Orbit camera: pivot on the clicked point (Classic) or the view centre (Standard), the wheel zooms toward
  the mouse, Alt plus mouse buttons, the middle button, keys 1/2/3, H/S/O and F1 to F4 in Classic, the Cameras
  menu, and view undo (`Ctrl+Shift+Z`, `Ctrl+Shift+Y` in Classic).
- Polygon Pen and Line Pen. Holding Ctrl after a drag starts turns it into an extrusion.
- Coordinate Manager in cm and degrees. Objects panel with several objects, rename and Delete.

Selection and tools (Classic and Standard):

- A click selects one thing, in any mode, with Move, Rotate, Scale or a selection tool; a click on nothing
  clears the selection. Shift adds, Ctrl removes (with a transform tool Ctrl inverts the click). Right click
  selects the same way and opens the context menu; right drag selects what the pointer touches.
- With something selected, a left drag applies Move, Rotate or Scale from anywhere: Move in the plane facing the
  camera, Scale on all three axes (right is bigger, left is smaller). Ctrl and drag copies the selected objects
  in Model mode (and extrudes in the component modes).
- `Ctrl+A` selects every object in Model mode, and every point, edge or polygon of the active object in the
  component modes.
- In Classic, press `U`, `M` or `K` and wait a moment: a popup lists the keys that can follow (for example
  `U` then `Y` grows the selection and `U` then `K` shrinks it). The popup can be turned off in the
  preferences (`controls.chord_menu`).

No icon, logo or file of the original program is used. Every icon is drawn in code.

## Requirements

- Windows.
- Python 3.14.
- PySide6 6.12.0 and numpy. PyInstaller only to build the executable.

## How to run

From this folder (`studio`), in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install numpy PySide6==6.12.0 pyinstaller
.venv\Scripts\python.exe -m quartz_studio
```

The first two commands are needed only once.

## How to build

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

- The script writes `Quartz.exe` to the parent folder (`D:\Apps\Quartz\Quartz.exe`). It creates `.venv` first
  if it is missing.
- The file icon of the executable is `..\quartz.ico`. The window icon, the instance icon (the taskbar button, set
  in `app.set_instance_identity` together with the AppUserModelID `Quartz.Studio`) and the desktop shortcut
  icon are `assets\quartzInstance.ico`, a copy of `D:\Icons\quartzInstance.ico` that is never redrawn. Quartz
  has no web page, so there is no favicon.
- The window regions are imported at run time, so the build needs `--collect-submodules quartz_studio`.
  Without it the executable opens with empty panels.
- Run the tests before building. After building, open the executable and check the viewport.

## How to test

The tests use offscreen Qt and run as scripts. Run them from this folder:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.venv\Scripts\python.exe -m tests.test_smoke
.venv\Scripts\python.exe -m tests.test_wiring
.venv\Scripts\python.exe -m tests.test_coordinates
.venv\Scripts\python.exe -m tests.test_press_feedback
.venv\Scripts\python.exe -m tests.test_camera
.venv\Scripts\python.exe -m tests.test_pen
.venv\Scripts\python.exe -m tests.test_viewport3d
.venv\Scripts\python.exe -m tests.test_objects_ui
.venv\Scripts\python.exe -m tests.test_fileio_ui
.venv\Scripts\python.exe -m tests.test_trunk_skin
.venv\Scripts\python.exe -m tests.test_trunk_tool
.venv\Scripts\python.exe -m tests.test_trunk_generator
```

Each script prints one line per test and a final count. The modeling tests are in `tests/test_modeling_*.py`,
the object tests in `tests/test_objects_*.py` and the managers in `tests/test_object_manager.py` and
`tests/test_attribute_manager.py`. `test_viewport3d` takes several minutes.

## Layout

- `quartz_studio/`: `app.py`, `main_window.py`, `project.py` (project state, title, dialogs, file commands), `scene.py`, `theme.py` (the Crystal tokens and the QSS), `icons.py`
  (vector icons drawn in code), `prefs.py` (preferences file), `controls/` (profiles, dispatch and the Controls
  editor) and `widgets/` (one screen region per file).
- `reference/`: historical screenshots of the arrangement study, and `layout_palettes.json` with the palette
  contents read from the user's layout file. The names in that file are kept in the original program's language.
- `tools/snapshot.py --out <png> --size 1920x1010`: renders the window offscreen to a PNG (also `--size 1280x720`).
- `tools/make_spritesheet.py`: renders every icon into a spritesheet and a contact sheet (`--sizes`, `--zoom`,
  `--only`, `--contact-out`).
- `SPEC.md`: the specification the interface was built from.
