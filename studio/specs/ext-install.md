# Extension: install and store

Package `quartz_studio/ext`: `install.py` (343 lines) and `store.py` (143 lines).

## Purpose

`install.py` wires the eight extension packages into the main window: menus, docks, pages, a Layout menu, shortcuts and runtime hooks. `store.py` is the shared JSON-safe extras layer every package uses.

## store.py

Data: `obj.extras` and `scene.extras` dicts. Values are converted with `to_json`: ndarray to `{"__ndarray__": list, "dtype": str}`, set to `{"__set__": [...]}`, non-finite floats to 0.0, numpy scalars to Python types. `from_json` reverses this.

Functions: `object_extras`, `scene_extras`, `get_object(obj, key, default)`, `set_object(obj, key, value)` (uses `scene.set_object_extra` for undo when the object is in the scene, `None` removes the key), `get_scene_data`, `set_scene_data` (uses `scene.set_extra`), `notify(owner, key)` (calls listeners in `_LISTENERS`, errors swallowed), `to_json`, `from_json`, `deep_copy`.

## install.py

Entry: `install(window) -> report`. Runs once per window (`window._ext_installed`).

`PACKAGES` order: materials (`materials.menus`), tags, uv, sculpt, rig, anim, scripting, render. Each module may expose `commands()`, `docks()`, `pages()`, `key_actions()`.

- `commands()`: list of `(path tuple, fn)`. Top menus are regrouped by `TOP_MENUS`: Materials (with Tags and Texture submenus), UV, Sculpt, Animate (with Character submenu), Render, Extensions.
- `docks()`: `(title, factory, area)`. Factories are called with the scene, or without arguments on `TypeError`. Dock id is `ext_<slug(title)>`; docks start hidden. `DOCK_AREAS` overrides areas.
- `pages()`: `(layout, [dock titles])`. Only layouts in `PAGE_LAYOUTS` (Materials, UV Edit, Script, Render) become pages (`ext_<slug>`); `DOCK_LAYOUTS` (Sculpt, Animate, Rigging) toggle dock visibility on the model page.
- `key_actions()`: tuples in any order; `_normalise_key_action` finds the callable, the shortcut by regex and the label. A shortcut is kept only if it contains Ctrl or Alt, is not in `RESERVED_SHORTCUTS` and is not already used by the window. Actions whose label is not a menu item are added under the package menu (`PACKAGE_MENU`).
- `Extensions > Layout` menu: Model, each available layout, and `Panels` with one toggle per dock. `window.show_ext_layout(name)` is set.
- `_attach_runtime`: `materials.hub.install_listener()`, `scripting.install_frame_driver(scene)`, and `sculpt.viewport.attach_viewport(canvas, scene)` when the viewport canvas exists.

`report` dict: `installed`, `failed` (name to traceback), `menus`, `docks`, `pages`, `shortcuts`, `skipped_shortcuts`. Every step is wrapped so one failing package does not stop the others; menu callbacks are wrapped by `_safe` and print tracebacks to stderr.

Window API used: `menu_bar.titles`, `menu_bar.add_menu`, `menu_bar.add_entries`, `add_dock`, `set_dock_visible`, `is_dock_visible`, `add_page`, `show_page`, `viewport.canvas`.

## Known gaps

- The Ctrl or Alt rule drops F-keys, single keys and Shift-only shortcuts declared by anim, sculpt and render (see those specs); `skipped_shortcuts` lists them.
- `Tagging` (tags) has no layout entry because it is in neither `PAGE_LAYOUTS` nor `DOCK_LAYOUTS`.
- `report` is module-global and is not reset between windows.
- `store.notify` swallows listener errors silently.
