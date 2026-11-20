# Extension: scripting

Package `quartz_studio/scripting` (about 5.2k lines). Loaded by `ext/install.py` as `quartz_studio.scripting`.

## Purpose

Python scripting inside the app: a `quartz` API module, a script library with editor and per-script shortcuts, an interactive console, Python tags run on frame change, and a plugin loader with example scripts and plugins.

## Data

Mostly on disk, not in scene extras:

- `paths.quartz_home()`, `scripts_dir()`, `plugins_dir()`; settings in `scripting.json` (`script_timeout`, `tag_timeout`, `console_history` up to 200 entries, shortcuts).
- Plugin enable state in `plugins.json`; plugin modules imported with prefix `quartz_plugin_`.

Scene and object extras used through `api` and `pytags`: object `tags` (Python tags of type `python` with `priority` and `code`), object `tracks` and `track_modes`, scene `anim`, scene `materials`.

## Public functions

- `api` (exposed to scripts as `quartz`, `API_VERSION` 1.0): document and scene access (`document`, `bind_scene`, `objects`, `iter_objects`, `roots`, `children`, `descendants`, `parent`, `set_parent`, `find`, `find_all`, `active_object`, `set_active`), creation (`create`, `create_polygon_object`, `duplicate`, `delete`, `rename`, `make_editable`), parameters and transforms (`params`, `get_param`, `set_param`, `position`, `rotation`, `scale`, `set_transform`, ...), selection, undo groups, messages, animation and material helpers. Errors raise `ScriptError`.
- `runner`: `execute(source, ns, filename)` with a watchdog timeout (default 120 s, max 3600), `make_namespace`, `is_complete`, `ExecResult`.
- `library`: `ScriptLibrary`, `get_library`, `sanitize_name`.
- `plugins`: `PluginLoader`, `PluginAPI` (`register_command`, `register_object`, `register_tool`, `register_tag`), `PluginRecord`, `get_loader`, `reset_loader`, `PLUGIN_TYPES`.
- `pytags`: `register_tag_type`, `unregister_tag_type`, `tag_types`, `run_python_tags`, `run_tags`, `FrameDriver`, `tag_timeout`, `set_tag_timeout` (default 10 s).
- `shortcuts`: `ShortcutBinder`, `get_binder`, `key_combination`.
- `examples`: `install_examples`, `EXAMPLE_SCRIPTS`, `EXAMPLE_PLUGINS`.
- Package level: `show_panel`, `run_user_script`, `reload_plugins`, `open_scripts_folder`, `install_frame_driver`, `frame_driver`, `set_tags_on_frame_change`.

## Widgets

`ScriptManager` (list, `CodeEditor` with line numbers, completion, `FindBar`, run, rename, delete), `ScriptConsole` with `ConsoleInput` (history, multi-line), `PluginManager`, `PythonHighlighter`.

## Menus, docks, pages, shortcuts

- Menu `Extensions`: Script Manager, Console, Plugin Manager, Reload Plugins, Run Python Tags, Python Tags On Frame Change, Install Examples, Open Scripts Folder. The installer also adds `Extensions > Layout` here.
- Docks: Script Manager (bottom), Console (bottom), Plugin Manager (right).
- Page: `Script` (Script Manager and Console).
- No package `key_actions`; user scripts get shortcuts through `ShortcutBinder`.

## Known gaps

- Scripts run in-process with full Python access; the timeout watchdog is the only guard.
- Plugin Manager is not part of the `Script` page and only opens as a dock.
