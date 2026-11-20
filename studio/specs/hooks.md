# Quartz Studio extension hooks

Stable entry points for packages that plug into the app without editing existing files
(`quartz_studio.materials`, `tags`, `uv`, `sculpt`, `rig`, `anim`, `scripting`, `render`, `ext`).
Tests: `tests/test_hooks.py`.

## 1. Extras on objects and on the scene (`quartz_studio/scene.py`)

### `SceneObject.extras: dict`
Default `{}`. Holds JSON types only: `dict` (text keys), `list`, `str`, `int`, `float` (finite), `bool`, `None`.
Deep-copied into every undo snapshot and back on undo/redo. `Scene.make_editable` gives the new
object a deep copy of the source object's extras. Objects opened or merged from a `.quartz` file get
their saved extras.

### `Scene.extras: dict`
Default `{}`. Same rules. Deep-copied in undo snapshots. Cleared by every scene replace
(`Scene.insert_objects(..., replace=True)`, which New and Open use); Open then loads the
file's scene extras. `reset_scene()` builds a new `Scene`, so it starts empty too.

### `Scene.set_object_extra(obj: SceneObject, key: str, value) -> bool`
### `Scene.set_extra(key: str, value) -> bool`
- One undo step each, then emits `Scene.changed` (the signal every other edit emits).
- The value is stored as a deep copy.
- `value is None` removes the key (no step when the key is absent).
- A value equal to the current one (same JSON types and contents) does nothing: no undo step, no
  signal, returns `False`. Returns `True` when something changed.
- `key` must be `str` (`TypeError` otherwise); `obj` must be in the scene (`ValueError` otherwise).
- Writing `obj.extras[...]` directly is allowed but records no undo step and emits nothing.

```python
from quartz_studio.scene import get_scene
scene = get_scene()
scene.set_object_extra(scene.active, "material", {"name": "Red", "rgb": [1.0, 0.0, 0.0]})
scene.set_extra("timeline", {"fps": 24, "range": [0, 90]})
scene.set_extra("timeline", None)
```

## 2. `.quartz` format (`quartz_studio/fileio/fmt_quartz.py`, `fileio/bridge.py`)
- Object extras are written as `scene.objects[i].extras`; scene extras as `scene.extras`. Both keys are
  optional and written only when the dict is not empty, so a scene without extras saves
  byte-identical to the previous code, and old files open unchanged (extras stay `{}`).
- Non-JSON content (a set, bytes, numpy value, object, NaN or infinity, a non-text key) raises
  `FileFormatError` on save before anything is written, so the old file is left intact.
  Convert numpy arrays to lists first (`quartz_studio.ext.store.to_json` does this).
- An `extras` key in a file that is not an object is ignored with a load warning.
- In a `Document`, object extras travel as `node.extras` (a plain attribute, read with
  `getattr(node, "extras", None)`) and scene extras as `document.meta["extras"]`.

```python
from quartz_studio import fileio
from quartz_studio.scene import get_scene
scene = get_scene()
scene.set_extra("render", {"samples": 64})
fileio.save_scene(scene, "D:/shot.quartz")
```

## 3. Extension package (`quartz_studio/app.py`)
`main()` calls `install_extensions(window)` right after `modeling_install.install(window)` and before
the window is shown.

### `install_extensions(window) -> bool`
- Runs `from quartz_studio.ext import install as ext_install; ext_install.install(window)`.
- If `quartz_studio.ext` or `quartz_studio.ext.install` does not exist: returns `False`, prints nothing.
- Any other exception (an import error inside the module, or anything raised by `install`) is
  caught, its traceback printed to stderr, and the app continues. Returns `True` only on success.

Example `quartz_studio/ext/install.py`:

```python
def install(window) -> None:
    from quartz_studio.anim import timeline
    window.add_dock("timeline", "Timeline", timeline.TimelineWidget(), "bottom")
    window.menu_bar.add_menu("Animate", [("Play", timeline.play, "Ctrl+Alt+P")])
```

## 4. Pages and docks (`quartz_studio/main_window.py`)
The window body (rail, viewport, right column) is the page `"model"` (title `"Model"`,
`window.model_page`) inside a `QStackedWidget` (`window.page_stack`). The top row and the status bar
are shared by all pages. With no page and no dock added the window looks and measures exactly as
before.

### `window.add_page(page_id: str, title: str, widget: QWidget) -> QWidget`
Adds a full page. `ValueError` on an empty or duplicate id. Does not switch to it.
### `window.show_page(page_id: str) -> None`
Shows the page; `KeyError` for an unknown id. Emits `pageChanged(page_id)` only when the page changes.
### `window.current_page() -> str`, `window.page_ids() -> list[str]`, `window.page(page_id) -> QWidget | None`
### Signal `window.pageChanged(str)`
### `window.page_switcher` (`PageSwitcher`)
Segmented control in the top row, between the menus and the command bar; hidden while there is only
one page. The mode pill stays centred on the window (the command bar re-centres it). Buttons are in
`page_switcher.buttons[page_id]`.

```python
from PySide6.QtWidgets import QLabel
page = QLabel("Material editor")
window.add_page("materials", "Materials", page)
window.pageChanged.connect(lambda pid: print("now on", pid))
window.show_page("materials")
```

### `window.add_dock(dock_id: str, title: str, widget: QWidget, area: str = "bottom") -> QWidget`
- `area="bottom"`: a card under the viewport, in a vertical splitter with it
  (`window.bottom_splitter`, created on the first bottom dock). Default height: the widget's
  `sizeHint`/`minimumHeight`, at most a third of the column. Use `setMinimumHeight` for a timeline.
- `area="left"`: a card in a column on the left of the model page, before the tool rail
  (`window.left_dock_column`, a vertical splitter, default width 256 px).
- `area="right"`: a card appended to the right column (`window.manager_splitter`), below Coordinates.
- The widget itself becomes the card (`widgets.common.make_card`), like the existing regions; its
  `windowTitle` is set to `title`. `ValueError` on an empty or duplicate id or an unknown area.
### `window.dock(dock_id) -> QWidget | None`, `window.dock_ids() -> list[str]`
### `window.set_dock_visible(dock_id: str, visible: bool) -> None`, `window.is_dock_visible(dock_id) -> bool`
Hides or shows the card (`KeyError` for an unknown id). The left column hides itself when all of its
docks are hidden; the viewport takes the room of a hidden bottom dock.

```python
from PySide6.QtWidgets import QLabel
timeline = QLabel("Timeline")
timeline.setMinimumHeight(96)
window.add_dock("timeline", "Timeline", timeline, "bottom")
window.set_dock_visible("timeline", False)
```

## 5. Menus (`quartz_studio/widgets/menu_bar.py`, reached as `window.menu_bar`)

### `menu_bar.add_menu(title: str, entries: list) -> StudioMenu`
Appends a top-level menu at run time. `ValueError` if a menu with that title already exists
(use `add_entries`).
### `menu_bar.add_entries(menu_title: str, entries: list) -> StudioMenu`
Appends entries to an existing top-level menu (`File`, `Edit`, ...) after a separator.
`KeyError` for an unknown title. The titles present are `menu_bar.titles()`.

Entry forms:
- `(label, handler, shortcut_or_None)`: an item; `handler` is a no-argument callable.
- `None`: a separator.
- `(label, [sub entries])`: a submenu with the same entry forms.

Menus use the same `StudioMenu` look as the rest. A shortcut is shown in the item and installed as a
window-wide `QShortcut` that triggers the item (kept in `menu_bar.extension_shortcuts`). Pick keys
that the app does not use yet.

```python
bar = window.menu_bar
bar.add_menu("Render", [("Render View", render_view, "Ctrl+Alt+R"), None,
                        ("Settings", [("Quality", open_quality, None)])])
bar.add_entries("File", [("Export Animation", export_animation, None)])
```
