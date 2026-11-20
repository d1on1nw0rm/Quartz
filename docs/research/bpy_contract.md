# Blender 5.2.2 Python API contract that the `bpy-lite` layer must honor

> Quartz — author: D1on1n. Research note (Path A + input for Path C).
> Date: 2026-10-22. Reference: Blender 5.2.2 LTS (hash d13f752e3b9c, embedded Python 3.13.13).

## 0. Scope, method and confidence level

This document defines the **observable contract** (names, call forms, life cycles, return values,
error messages and side effects) that simple add-ons expect from `bpy` and its neighbors. It does not
describe Blender's internal implementation and does not contain Blender code: everything here is a
paraphrase of behavior, with names cited only as identifiers.

Sources, in order of weight:

1. **Live introspection** — `tools/dump_bpy_api.py`, run by me inside Blender 5.2.2 in
   `--background --factory-startup` mode (via `tools/run_dump_bpy_api.ps1`, which redirects
   Blender's user resources to `tmp/blender_user`). Output: `data/blender_api_dump.json`
   (~1.9 MB). Besides the inventory (types, properties, operators…), the script runs **behavior
   probes** (the `probes` section) that register test classes, call operators, create/delete
   data-blocks, etc., and record the result or the exception text. Everything marked as "observed" below
   came from these probes.
2. **Reading (without copying)** the Python modules that ship with Blender: `modules/bpy/` (`__init__`,
   `ops`, `utils`, `path`), `_bpy_types.py`, `_bpy_restrict_state.py`, `addon_utils.py`,
   `bpy_extras/` (`object_utils`, `io_utils`, …), `rna_prop_ui.py`, `nodeitems_utils.py`,
   `addons_core/bl_pkg/cli/blender_ext.py` (manifest validation) and `templates_py/`.

Confidence legend: **[O]** = observed by running in Blender 5.2.2; **[L]** = deduced from reading
the Python code that ships with Blender; **[I]** = inference/convention, not verified.

To reproduce:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:/Claude/reverseEngineering/Quartz/tools/run_dump_bpy_api.ps1
```

Honest notes about the environment: even with user resources redirected, Blender itself
creates (and removes on exit) a temporary directory in `%TEMP%\blender_*`, and on the first attempt
(which hung, see §14) it wrote `%TEMP%\blender.crash.txt`. This is behavior of the executable, not of the
script.

---

## 1. Shape of the `bpy` package

- `bpy` exposes: `app`, `context`, `data`, `msgbus`, `ops`, `path`, `props`, `types`, `utils`.
  `app/context/data/msgbus/props/types` are objects of the C module `_bpy`; `ops`, `path` and `utils` are
  Python. **[L]**
- At startup, `sys.modules` receives synthetic entries for `bpy.app`, `bpy.app.handlers`,
  `bpy.app.translations` and `bpy.types`, so that `from bpy.types import Panel` works. **[L]**
  → The shim must register these names in `sys.modules` as well.
- `bpy.types` has **4023** names in the factory startup (including ~685 `*_MT_*`, ~1233 `*_PT_*`, 26 `*_HT_*`,
  33 `*_UL_*` from the built-in UI). **[O]** Add-ons do `bpy.types.VIEW3D_MT_mesh_add.append(fn)`, so the
  most commonly cited menus/panels need to exist as empty classes (list in §11).
- `bpy.types.bpy_struct` (base of everything) offers: `as_pointer, bl_rna_get_subclass,
  bl_rna_get_subclass_py, driver_add, driver_remove, get, id_data, id_properties_clear,
  id_properties_ensure, id_properties_ui, is_property_hidden, is_property_overridable_library,
  is_property_readonly, is_property_set, items, keyframe_delete, keyframe_insert, keys,
  path_from_id, path_from_module, path_resolve, pop, property_overridable_library_set,
  property_unset, rna_ancestors, type_recast, values`. **[O]**
- All "registerable" classes use a metaclass whose `is_registered` property is simply
  "the class has `bl_rna` in its own `__dict__`". **[L][O]**

### 1.1 `bpy.ops`

- `bpy.ops.<sub>` is a module synthesized on demand by `__getattr__`; `dir(bpy.ops)` derives the
  submodules from the registered idnames (`MESH_OT_primitive_cube_add` → `mesh`). `bpy.ops.<sub>.<op>`
  returns a callable object (in 5.2 it is a C type, `BPyOpsCallable`). **[L]**
- The factory startup has **2499 operators in 77 submodules** (largest: `object` 250, `node` 182,
  `mesh` 167, `grease_pencil` 123, `wm` 118). **[O]** Requested groups: `mesh.primitive_*_add` =
  circle, cone, cube, cylinder, grid, ico_sphere, monkey, plane, torus, uv_sphere; `object.*` = 250;
  `transform.*` = 27. Full names and properties of each operator are in the dump
  (`ops.submodules`; full type/default/limit details only for `mesh.primitive_*`,
  `object.*` and `transform.*`).
- Call form **[O]**: `bpy.ops.mod.op([execution_context: str], [undo: bool], **props)`.
  - Up to 2 positional arguments: execution context (`'EXEC_DEFAULT'`, `'INVOKE_DEFAULT'`, …) and
    `undo`. Passing a positional `dict` (the old override) gives `ValueError` ("1-2 args execution
    context is supported"). The dictionary override **was removed**; use `temp_override` (§6).
  - Return: a `set` of strings, e.g. `{'FINISHED'}` or `{'CANCELLED'}`.
  - Methods of the callable: `poll()` → bool, `idname()` → `"MESH_OT_primitive_cube_add"`,
    `get_rna_type()` → struct with `.properties`, and `bl_options` (set). **[O]**
  - Kwarg conversion errors are `TypeError` ("keyword … unrecognized", "enum … not found in
    (…)", "expected an int type, not str"). **Out-of-range values are silently clamped**
    (`count=99` with `max=10` became 10). **[O]**
  - A false `poll()` → `RuntimeError` whose text includes the `poll_message_set` message if there is one
    ("Operator bpy.ops.x.y.poll() <message>"). **[O]**
  - A nonexistent/unregistered operator → `AttributeError` ("could not be found"). **[O]**
- In background mode, `poll()` was true for all `mesh.primitive_*_add` and for the main
  `transform.*` (translate, rotate, resize, transform, mirror, …), and for many `object.*`. The full
  map is in `ops.poll_in_background`. **[O]** `mesh.primitive_cube_add(size=1,
  location=(3,0,0))` created `Cube.001` (8 vertices, active, selected), `transform.translate` moved it,
  `object.delete` deleted the object **leaving the mesh orphaned** (0 users). **[O]**

---

## 2. Class registration (`bpy.utils.register_class` / `unregister_class`)

### 2.1 General rules **[O]**

| Situation | Result in Blender 5.2.2 |
|---|---|
| Registering an already registered class | `ValueError` "already registered as a subclass …" |
| Registering a **different** class with the same `bl_idname` | OK; the previous one is unregistered (Info message) |
| Unregistering a class that is not registered (or twice) | `RuntimeError` "missing bl_rna attribute … (may not be registered)" |
| Registering a plain Python class (not `bpy_struct`) | `RuntimeError` (same message family) |
| Failure to register a property of the class | `ValueError` "… registration error: '<prop>' … could not register"; **the class may be left half registered** (a new `register_class` on it said "already registered") |

After registering, `cls.is_registered` is `True`, `cls.bl_rna` exists, and the class appears in
`bpy.types` **under the RNA name**, not under the Python name. For operators this name comes from `bl_idname`:
`quartz_probe.hello` → `bpy.types.QUARTZ_PROBE_OT_hello`. For Panel/Menu/Header/UIList the name is the
`bl_idname` (or the class name if `bl_idname` is missing). **[O]**

### 2.2 Required attributes by type **[O]** (probe `required_bl_attrs`)

Starting from a minimal valid class and removing one attribute at a time:

| Base | Required | Optional (registration accepted without them) |
|---|---|---|
| `Operator` | `bl_idname` (form `module.name`), `bl_label` | `execute`, `invoke`, `modal`, `poll`, `draw`, `cancel`, `check`, `description`; all remaining `bl_*` |
| `Panel` | `bl_label`, `bl_space_type`, `bl_region_type`, `draw` | `bl_idname` (uses the class name), `bl_category`, `bl_context`, `bl_options`, `bl_parent_id`, `bl_order`, … |
| `Menu` | `bl_label`, `draw` | `bl_idname` |
| `Header` | `bl_space_type`, `draw` | `bl_idname`, `bl_region_type` (default `'HEADER'`) |
| `UIList` | — | `bl_idname`, `draw_item` |
| `AddonPreferences` | — (but `bl_idname` must match the module to be useful, §5) | |
| `PropertyGroup` | — | |

Validation of the operator `bl_idname` **[O]**:
- exactly **one** dot (`quartzprobe` and `a.b.c` are rejected);
- only lowercase letters/digits/`_` ("Invalid character at position 0" for `Quartz.Probe` and for the form
  `QUARTZ_OT_probe` — the `XXX_OT_yyy` format is **not** accepted as a `bl_idname` coming from Python);
- maximum identifier length: **60** ("Identifier too long, maximum length is 60"); the field
  `bl_idname` has `length_max` 64;
- a leading digit was accepted (`1quartz.probe`).
- Without `bl_idname`, the class name is used as the idname and fails under the rule above.

Class name convention **[O]**: `CATEGORY_PT_name`, `_MT_`, `_HT_`, `_UL_`, `_OT_`. For
Panel/Menu, violating the convention generates **only a warning** ("does not contain '_PT_' with prefix and
suffix") — registration goes through. For operators the class name is irrelevant (the `bl_idname` is what counts).

Other rules **[O]**: invalid `bl_space_type` → `TypeError` listing the valid values;
`bl_parent_id` pointing to a nonexistent panel → `RuntimeError` "parent … not found".

### 2.3 Enum values used in classes **[O]**

- `Operator.bl_options`: `REGISTER, UNDO, UNDO_GROUPED, BLOCKING, MACRO, GRAB_CURSOR,
  GRAB_CURSOR_X, GRAB_CURSOR_Y, DEPENDS_ON_CURSOR, PRESET, INTERNAL, MODAL_PRIORITY` (default empty).
- `Panel.bl_options`: `DEFAULT_CLOSED, HIDE_HEADER, INSTANCED, HEADER_LAYOUT_EXPAND`.
- `Menu.bl_options`: `SEARCH_ON_KEY_PRESS`.
- `bl_space_type`: `EMPTY, VIEW_3D, IMAGE_EDITOR, NODE_EDITOR, SEQUENCE_EDITOR, CLIP_EDITOR,
  DOPESHEET_EDITOR, GRAPH_EDITOR, NLA_EDITOR, TEXT_EDITOR, CONSOLE, INFO, TOPBAR, STATUSBAR,
  OUTLINER, PROPERTIES, FILE_BROWSER, SPREADSHEET, PREFERENCES`.
- `bl_region_type`: `WINDOW, HEADER, CHANNELS, TEMPORARY, UI, TOOLS, TOOL_PROPS, ASSET_SHELF,
  ASSET_SHELF_HEADER, PREVIEW, HUD, NAVIGATION_BAR, EXECUTE, FOOTER, TOOL_HEADER, XR, SCRUBBING`.
- `bl_icon` accepts ~1000 icon identifiers (full list in the dump, `base_classes.Panel`).
  For the shim it is enough to accept any string in `icon=`/`bl_icon` [I].

### 2.4 Registration utilities **[L]**

- `register_classes_factory(classes)` → `(register, unregister)`; registers in order and unregisters
  in **reverse** order.
- `register_submodule_factory(module_name, submodule_names)` → imports the submodules, calls
  `register()` of each one in order; on `unregister` it calls them in reverse order and **removes** the
  submodules from `sys.modules`.
- `startup` scripts without `register()` generate a warning ("now a requirement for registerable scripts").

---

## 3. Operator life cycle

Callbacks (all optional for registration, see §2.2) **[O]**, with signatures observed in RNA:

| Callback | Type | Parameters | Return |
|---|---|---|---|
| `poll` | classmethod | `(cls, context)` | bool |
| `invoke` | method | `(self, context, event)` | status set |
| `execute` | method | `(self, context)` | status set |
| `modal` | method | `(self, context, event)` | status set |
| `cancel` | method | `(self, context)` | — |
| `check` | method | `(self, context)` | bool (redraw?) |
| `draw` | method | `(self, context)` | — |
| `description` | classmethod | `(cls, context, properties)` | str |

- Valid statuses (observed error message): `RUNNING_MODAL, CANCELLED, FINISHED, PASS_THROUGH,
  INTERFACE`. Returning any other value (`{'DONE'}`) or `None` makes the **call via `bpy.ops` raise
  `RuntimeError`** with the validation error embedded in the text; an exception inside `execute` also
  becomes a `RuntimeError` containing the traceback. **[O]**
- `self.report({'ERROR'}, msg)` + `{'CANCELLED'}` → the call raises `RuntimeError("Error: msg")`;
  `report({'INFO'|'WARNING'}, …)` only prints. **[O]**
- `poll` was called **2 times per call** of `bpy.ops` (once by the wrapper's check, once by the
  window manager). This is not part of the contract, but add-ons must not depend on the count. **[O]**
- **`'INVOKE_DEFAULT'` in background mode did not call `invoke`**: the operator went straight to `execute`
  (there is no event). **[O]** `'EXEC_DEFAULT'` and the call with no arguments run `execute`.
- Property attributes: inside the operator, `self.<prop>` reads/writes `self.properties.<prop>`
  (the base class's `__getattribute__/__setattr__` diverts names that are RNA properties). **[L][O]**
  `self.as_keywords(ignore=(...))` returns a dict of only the declared properties. **[O]**
  `self.properties.is_property_set("x")` is true only if the caller passed `x`. **[O]**
- Property values **do not persist between Python calls**: after `op(count=5)`, the next
  `op()` saw the default again. **[O]** (The memory of "last used values" is a UI thing [I].)
- Modal: `invoke` calls `context.window_manager.modal_handler_add(self)` and returns
  `{'RUNNING_MODAL'}`; the event loop calls `modal` until `FINISHED/CANCELLED`. **[L]** (template
  `Operator/modal.py`). Without an event loop (headless) this never progresses.
- Mixin helpers (`bpy_extras`): `ImportHelper`/`ExportHelper` declare `filepath` (and
  `check_existing`), implement `invoke` by opening the file selector
  (`window_manager.fileselect_add`) and `check`; `orientation_helper` is a class decorator that
  injects `axis_forward/axis_up`; `AddObjectHelper` injects `align/location/rotation` and a `poll`;
  `object_data_add(context, obdata, operator=None, name=None)` creates the object, links it to the active collection,
  selects it, makes it active and applies the matrix derived from `location/rotation/align`. **[L]**
  Note: mixins do **not** inherit from `bpy_struct`; registration collects `__annotations__` from the whole MRO.

---

## 4. Properties (`bpy.props`)

### 4.1 Functions and kwargs **[O]** (extracted from the signature documented in 5.2.2)

| Function | kwargs (all keyword-only) |
|---|---|
| `BoolProperty` | name, description, translation_context, default, options, override, tags, subtype, update, get, set, get_transform, set_transform |
| `BoolVectorProperty` | … + size |
| `IntProperty` | name, description, translation_context, default, min, max, soft_min, soft_max, step, options, override, tags, subtype, update, get, set, get_transform, set_transform |
| `IntVectorProperty` | … + size |
| `FloatProperty` | … from Int + precision, unit |
| `FloatVectorProperty` | … + size |
| `StringProperty` | name, description, translation_context, default, maxlen, options, override, tags, subtype, update, get, set, get_transform, set_transform, search, search_options |
| `EnumProperty` | items, name, description, translation_context, default, options, override, tags, update, get, set, get_transform, set_transform |
| `PointerProperty` | type, name, description, translation_context, options, override, tags, poll, update |
| `CollectionProperty` | type, name, description, translation_context, options, override, tags |
| `RemoveProperty` | cls, attr |

Relevant defaults (Float): `default=0.0`, `min/max/soft_min/soft_max=±3.402823e+38`, `step=3`,
`precision=2`, `options={'ANIMATABLE'}`, `subtype='NONE'`, `unit='NONE'`. `get_transform` /
`set_transform` are new (4.x/5.x) and almost no simple add-on uses them.

- Each function **creates nothing**: it returns a `_PropertyDeferred` object with `.function` and
  `.keywords` (e.g. `IntProperty(name="x", default=3)` → `function=IntProperty`,
  `keywords={'name': 'x', 'default': 3}`). The actual creation happens at class registration or at
  assignment to a type. **[O]** → The shim must reproduce exactly this deferred object.

### 4.2 Annotation vs assignment **[O]**

- The correct form is **class annotation**: `count: IntProperty(...)`.
- The old form `count = IntProperty(...)` inside the class **registers without error, but the property
  is not created** (it does not appear in `bl_rna.properties`). Silent. 2.7x add-ons break this way.
- Assignment **on an existing type** is the way to extend Blender types:
  `bpy.types.Scene.my_prop = IntProperty(...)` creates it immediately; `del bpy.types.Scene.my_prop` removes it
  (`hasattr` becomes false). Reading before any write returns the default.
- RNA property names **shadow** `bpy_struct` methods on the instance: a
  `CollectionProperty` named `items` made `pg.items` the collection, not the method. **[O]**

### 4.3 Registration order (PointerProperty / CollectionProperty / PropertyGroup) **[O]**

- `type=` must be a `PropertyGroup` that is **already registered** (or an ID type for `PointerProperty`).
  Otherwise: `TypeError` printed ("expected an RNA type … may not be registered") and
  `ValueError` "… '<prop>' PointerProperty/CollectionProperty could not register".
- Correct order: (1) register the leaf `PropertyGroup`s; (2) the groups that contain them; (3) the remaining
  classes; (4) attach `bpy.types.X.prop = PointerProperty(type=Group)`. Undo in reverse order
  (first `del bpy.types.X.prop`).
- Unregistering a group still referenced by a pointer **was accepted** without error (there is no dependency
  check).
- `PointerProperty(type=bpy.types.Object)` accepts only that type: assigning a `Mesh` → `TypeError`
  "expected a Object type, not Mesh". Default `None`.

### 4.4 Value semantics **[O]**

- `update(self, context)`: called **on every Python assignment**, including when the value does not change and
  when the value was clamped (`level=50` with `max=10` became 10 and fired `update`). `context`
  is not `None`.
- `get(self)` / `set(self, value)`: with `get`+`set`, the value is not stored automatically (the
  example stored it in `self["_shadow"]`). `get` only → **read-only** property
  (`AttributeError` "… is read-only").
- Int/Float outside `min/max` are clamped on assignment (no error). Wrong type → `TypeError`.
- `StringProperty(maxlen=8)` truncated `"0123456789abc"` to `"01234567"`.
- `EnumProperty`: `items` can be a list of tuples `(id, name, description[, icon[, number]])` or
  a function `(self, context) -> list`. `default` outside the items → `ValueError` at registration. Invalid
  value on assignment → `TypeError` listing the valid ones. With `options={'ENUM_FLAG'}` the value is
  a `set`.
- `FloatVectorProperty(size=3, subtype='XYZ')` returns `mathutils.Vector`; `size=(4, 4),
  subtype='MATRIX'` returns `mathutils.Matrix`.
- `CollectionProperty`: `add()` returns the new item; `remove(i)`, `clear()`, `move(a, b)`,
  `find(name)` → index (or -1), `keys()` via the `name` property, `coll["name"]`. Every
  `PropertyGroup` has an implicit `StringProperty` `name`.
- `pg.path_from_id()` → `"quartz_probe"`; `pg.id_data` → the owning ID (the Scene).

### 4.5 Where values live (important change in 5.x) **[O]**

- Values of properties defined by `bpy.props` **do not appear** in the ID's custom properties
  dictionary: after `ob.quartz_probe_val = 5`, `ob.keys()` was `[]`,
  `"quartz_probe_val" in ob` was false and `ob["quartz_probe_val"]` raised `KeyError`. There is
  `bl_system_properties_get()` for the separate storage.
- Custom "dictionary" properties (`ob["x"] = 3.5`, lists → `IDPropertyArray`, dicts →
  `IDPropertyGroup` with `.to_dict()`) are a different namespace and do **not** become attributes
  (`ob.x` does not exist). `id_properties_ui("x").update(min=…, max=…)` / `.as_dict()` control UI
  metadata (`rna_prop_ui.rna_idprop_ui_create` is the helper that add-ons use).
- Inside a `PropertyGroup` instance, however, `pg.keys()` listed the values already written
  (`level`, `entries`, `target`, …). The shim may use a single dictionary per instance, as long as it
  hides the `bpy.props` values from `keys()` **of IDs**.
- `is_property_set("x")` / `property_unset("x")` work (after `unset`, the default returns).

---

## 5. Add-ons and extensions

### 5.1 Legacy add-on (`bl_info`) **[L][O]**

- Discovery: `addon_utils.paths()` = `addons_core` in the first scripts directory and `addons` in the
  others. Each directory is scanned by `bpy.path.module_names`: `*.py` files (except
  `__init__.py`) and non-hidden folders with `__init__.py`; the `modules` folder is ignored.
- Metadata reading **without importing**: the file is read as UTF-8; in fast mode, it reads from the
  first line that **starts with `bl_info`** up to the first **blank line**; the snippet is
  parsed with `ast` and `ast.literal_eval` (so `bl_info` must be a pure literal, with no blank line
  inside). Without `bl_info` → warning and the module is ignored in the listing. `modules()` sorts by
  `bl_info["name"]` (casefold) and then by module name; it stores `__file__` and `__time__` (mtime).
- Base fields (filled in by `module_bl_info`): `name, author, version, blender, location,
  description, doc_url, support='COMMUNITY', category, warning, show_expanded=False`. Empty `name` →
  module name; emails `<...>` are removed from `author` (observed: `"D1on1n <x@y.z>"` →
  `"D1on1n"`); `{BLENDER_MANUAL_URL}` in `doc_url` is expanded; it sets a `"_init"` mark so as not to redo it.
- `addon_utils.enable(module_name, *, default_set=False, persistent=False, refresh_handled=False,
  handle_error=None)`:
  1. if the module is already in `sys.modules` and enabled, it calls `unregister()` first; if the mtime changed,
     `importlib.reload`;
  2. `default_set=True` adds the entry to `preferences.addons` **before** importing (so the
     add-on can read its own preferences);
  3. **it imports and registers inside `RestrictBlend`**: during import + `register()`, `bpy.context`
     is replaced by an object that only has `window_manager` and `preferences`, and `bpy.data` by an empty
     object. Add-ons that touch `bpy.context.scene`/`bpy.data.*` during registration fail in real Blender;
  4. it sets the "owner id" (used to filter menus by owner) and calls `mod.register()`;
  5. failure at any step → `handle_error(ex)`, removes from `sys.modules`, undoes `default_set`,
     returns `None`. Missing module: `ModuleNotFoundError` with the short message "Add-on not loaded:
     "<name>", cause: …" **[O]**;
  6. success → `mod.__addon_enabled__ = True`, `mod.__addon_persistent__ = persistent`, returns the
     module. **[O]**
- `disable(module_name, *, default_set=False, refresh_handled=False, handle_error=None)`: clears the
  flags, calls `unregister()` (an error is reported, not propagated), optionally removes from
  `preferences.addons`. The module **remains in `sys.modules`**. **[O]**
- `check(module_name)` → `(loaded_default, loaded_state)`: `(False, False)` before,
  `(True, True)` enabled with `default_set`, `(False, False)` after disabling. **[O]**
- Other public functions: `paths, modules, modules_refresh, check, check_extension, enable,
  disable, disable_all, reset_all, module_bl_info, extensions_refresh, stale_pending_*`. **[O]**
- Preferences: `AddonPreferences` class with `bl_idname` **equal to the module name** (`__name__`
  in a single file; `__package__` in a package/extension). After enabling,
  `context.preferences.addons[name].preferences` is the instance (observed: type `QuartzProbePrefs`,
  `flag=True`). **[O]**

### 5.2 Extension (`blender_manifest.toml`) **[L][O]**

- The module name of an extension is `bl_ext.<repo_module>.<pkg_id>`; `bl_ext` is a synthetic package
  whose submodules have `__path__ = [repository directory]`. Repositories in the factory setup:
  `blender_org` (remote), `user_default`, `system`. **[O]** `check_extension(name)` = prefix
  `bl_ext.`.
- `__package__` must have exactly 3 identifier components for
  `bpy.utils.extension_path_user(__package__, path="", create=False)`, which points to
  `<user EXTENSIONS>/.user/<repo>/<pkg>/<path>` (the extension's writable location).
- If the extension module defines `bl_info`, it is **deleted** after the import; the synthetic `bl_info` is
  generated from the manifest: `name←name`, `version←version` ("X.Y.Z", the 3rd component reads only the leading
  digits), `blender←blender_version_min`, `description←tagline`, `author←maintainer`,
  `category='Development'` (fictitious).
- Manifest fields (`bl_pkg` validation):
  - required: `schema_version`, `id`, `name`, `tagline`, `version`, `type`, `maintainer`,
    `license` (list), `blender_version_min`;
  - optional: `blender_version_max`, `website`, `copyright` (list "YEAR Name" or "A-B Name"),
    `permissions` (table with keys `files, network, clipboard, camera, microphone` → reason
    text; old lists accepted in non-strict mode), `tags`, `platforms`, `wheels`;
  - `[build]`: `paths` **or** `paths_exclude_pattern` (both together is an error);
  - `type` ∈ {`add-on`, `theme`}; `id` must be a Python identifier, without `__`, without `_` at the
    start or end;
  - in strict mode, Blender versions must have 3 numbers; an empty `blender_version_max` is
    allowed.
- Declared wheels are installed into a local `site-packages` and that path goes into `sys.path`
  (out of scope for Quartz for now; treat as "not supported" with a warning [I]).

---

## 6. Context (`bpy.context`)

- In `--background --factory-startup`, 75 members/methods. **Not null [O]**: `active_object`
  (Cube), `object`, `scene` (Scene), `view_layer`, `collection` (Collection), `layer_collection`,
  `window_manager` (WinMan), `window`, `screen` (Layout), `workspace` (Layout), `preferences`,
  `blend_data`, `tool_settings`, `engine` = `"BLENDER_EEVEE"`, `mode` = `"OBJECT"`,
  `selected_objects` (1), `selected_editable_objects` (1), `selectable_objects` (3),
  `visible_objects` (3), `editable_objects` (3), `objects_in_mode` (0),
  `objects_in_mode_unique_data` (0), `asset_library_reference`.
  **Null**: `area`, `region`, `region_data`, `space_data`, `edit_object`, `active_bone`,
  `active_pose_bone`, `active_operator`, `pose_object`, `sculpt_object`, `ui_list`, `property`, …
  (full list in `context`). Methods: `copy`, `evaluated_depsgraph_get`, `path_resolve`,
  `temp_override`.
- Curiosity 5.2 **[O]**: `context.window` is **not `None`** in background, but `area`/`space_data`
  are. Operators that require a `VIEW_3D` area fail in `poll`.
- Members are **read-only**: `context.scene = …` → `AttributeError` "… is read-only". **[O]**
- `with context.temp_override(**members):` replaces members inside the block and restores them on exit
  (observed with `active_object/object/selected_objects`). Unknown keys are accepted without
  error, but do not become attributes. **[O]**
- `context.copy()` → dict of the members (without methods). `context.path_resolve("scene.frame_current")`
  resolves the first segment as a member and delegates the rest to the value's `path_resolve`. **[O][L]**
- `object.mode_set(mode='EDIT')` works in background (`edit_object` becomes the Cube). **[O]**

---

## 7. Data-blocks (ID) and `bpy.data`

### 7.1 `bpy.data` collections **[O]**

40 collections; all have `tag(value)` and the generic collection methods (`get, keys, values, items,
find, foreach_get, foreach_set`, indexing by name/index, `in`). Signatures of `new`/`remove`
for the most used:

| Collection | `new(...)` | `remove(...)` | extra |
|---|---|---|---|
| `objects` | `name, object_data` (`None` → Empty) | `object, do_unlink, do_id_user, do_ui_user` | |
| `meshes` | `name` | `mesh, do_unlink, do_id_user, do_ui_user` | `new_from_object(object, preserve_all_data_layers, depsgraph)` |
| `materials` | `name` | same | `create_gpencil_data`, `remove_gpencil_data` |
| `cameras`, `worlds`, `collections`, `armatures`, `actions`, `texts`, `lattices`, `metaballs`, `speakers`, `palettes`, `masks`, `pointclouds`, `volumes`, `hair_curves`, `grease_pencils`, `annotations`, `particles`, `linestyles` | `name` | same | `texts.load(filepath, internal)` |
| `lights`, `curves`, `textures`, `lightprobes`, `node_groups` | `name, type` | same | |
| `images` | `name, width, height, alpha, float_buffer, stereo3d, is_data, tiled` | same | `load(filepath, check_existing)` |
| `scenes` | `name` | `scene, do_unlink` | |
| `libraries` | — | same | `load(...)`/`write(...)` (Python) |
| `fonts`, `sounds`, `movieclips` | — | same | `load(filepath, check_existing)` |
| `screens`, `window_managers`, `workspaces`, `cache_files`, `paint_curves`, `shape_keys`, `all_ids` | — | — | |

Also: properties `filepath, is_dirty, is_saved, use_autopack, version, colorspace`; function
`pack_linked_ids_hierarchy`; Python members `batch_remove`, `orphans_purge`, `user_map`,
`temp_data`, `file_path_map`, `file_path_foreach`. **[O]**

### 7.2 Factory scene (golden) **[O]**

Scene "Scene"; collection "Collection" under the Scene Collection; objects Camera (CAMERA, loc ≈ 7.359,
-6.926, 4.958), Cube (MESH, origin), Light (LIGHT, loc ≈ 4.076, 1.005, 5.904); materials "Material"
and "Dots Stroke"; World "World"; mesh "Cube" 8 v / 12 e / 6 f / 24 loops with UV "UVMap"; frames
1–250, current frame 1; engine `BLENDER_EEVEE`; unit system `METRIC`. Cube active and
selected.

### 7.3 ID semantics **[O]**

- **Unique names per type**: `new("QProbe")` three times → `QProbe`, `QProbe.001`, `QProbe.002`.
- Renaming to an existing name: **the one being renamed gets the suffix** (`m2.name = "QProbe"` became
  `QProbe.001`; the original owner keeps the name).
- Maximum name length: **255 UTF-8 bytes**, truncating at a character boundary (300 "N" → 255;
  200 "Ã" → 127 characters = 254 bytes). Empty name → the type's default name ("Mesh").
- User count: new mesh 0; object using the mesh → mesh 1; new object 0, linked to a
  collection → 1; `use_fake_user=True` adds 1. `copy()` produces `Name.NNN` with 0 users.
- Double `link` in the same collection → `RuntimeError` "Object '…' already in collection '…'".
- `remove(id)` (default `do_unlink=True`) **deletes even with users**, unlinking them; any
  later access to the Python object raises `ReferenceError` "StructRNA of type Mesh has been
  removed" (including a second `remove`). **Removing the mesh also deletes the objects that use it**
  as `data`: confirmed in an isolated probe (`tmp/probe_scripts/remove_mesh_probe.py`) — the object
  vanished from `bpy.data.objects` and its Python reference started raising `ReferenceError`. In contrast,
  `objects.remove(ob)` only decrements the mesh's users (it becomes an orphan, 0 users).
- `coll["nonexistent"]` → `KeyError`; `get` → `None`; `"name" in coll` works.
- `orphans_purge(do_recursive=True)` returns the removed count (5 in the probe); `user_map(subset=…)`
  returns `{id: set(ids that use it)}`.
- Other ID attributes: `id_type` ("OBJECT"), `session_uid` (int), `is_evaluated` (False on the
  original), `original` (itself), `name_full`, `library`, `users`, `use_fake_user`.

### 7.4 Mesh contract **[O][L]**

- `Mesh.from_pydata(vertices, edges, faces, shade_flat=True)` (Python): adds vertices, edges,
  loops and polygons; fills `co`, `vertices` of the edges, `loop_start` and `vertices` of the
  polygons; with faces, recomputes edges (`update(calc_edges=True)`). A quad produced 4 v / 4 e /
  4 loops / 1 face; `validate()` → `False` (nothing to fix).
- Internal attributes after that: `position` (POINT, FLOAT_VECTOR), `.edge_verts` (EDGE,
  INT32_2D), `.corner_vert`/`.corner_edge` (CORNER, INT), `sharp_face` (FACE, BOOLEAN) and selection
  layers `.select_vert/.select_edge/.select_poly`. Prefix `.` = internal/hidden.
- `edge_keys`, `polygon.edge_keys`, `polygon.loop_start/loop_total/vertices`;
  `vertices.foreach_get("co", buf)` accepts a list **and** a numpy buffer (`float32`).
- This confirms Blender's SoA model: Quartz's numpy model (`verts/edges/loops/faces` +
  per-domain attributes) fits directly and `foreach_get/foreach_set` must copy from/to arrays.

---

## 8. Undo **[O]**

- In background the undo system **starts disabled**: `ed.undo.poll()` is false, calling it gives
  `RuntimeError` "Undo disabled at startup in background-mode (call `ed.undo_push()` …)".
  `ed.undo_push(message=…)` has a true `poll` and initializes it. `preferences.edit.use_global_undo`
  is `True`.
- `bl_options={'UNDO'}` requests an undo step after `FINISHED` [L]; `UNDO_GROUPED` + `bl_undo_group`
  groups repetitions [I].
- Handlers `undo_pre/undo_post/redo_pre/redo_post` exist (§9).

## 9. Handlers and timers **[O]**

- `bpy.app.handlers` has 39 plain Python lists: `animation_playback_pre/post, annotation_pre/post,
  blend_import_pre/post, composite_pre/post/cancel, depsgraph_update_pre/post, exit_pre,
  frame_change_pre/post, load_factory_preferences_post, load_factory_startup_post, load_pre,
  load_post, load_post_fail, object_bake_pre/complete/cancel, redo_pre/post, render_init,
  render_pre/post/stats/write/complete/cancel, save_pre/post, save_post_fail,
  translation_update_post, undo_pre/post, version_update, xr_session_start_pre`, plus the decorator
  `persistent`.
- Callbacks receive **2 positional arguments** `(scene, depsgraph)` in `frame_change_pre/post` and
  `depsgraph_update_post` (observed: `Scene, Depsgraph`). In `frame_change_pre` the depsgraph came
  filled in as the second argument, but the function with a default accepted it; write callbacks as
  `def h(scene, depsgraph=None)` or `*args`.
- `scene.frame_set(n)` triggers `frame_change_pre` (already with `frame_current == n`) and then
  `frame_change_post`. `view_layer.update()` after changes triggered `depsgraph_update_post` once.
- `@bpy.app.handlers.persistent` only marks the function with the attribute `_bpy_persistent`; handlers without
  the mark are removed when another .blend is loaded [L/I].
- `bpy.app.timers.register(fn, first_interval=…, persistent=…)`, `unregister`, `is_registered`.
  In background without an event loop the timer **did not fire** immediately. The shim can store it and
  offer a manual "pump".

## 10. msgbus **[O]**

- `bpy.msgbus` = `subscribe_rna(key, owner, args, notify, options=…)`, `publish_rna(key)`,
  `clear_by_owner(owner)`. `key` can be `(bpy.types.Object, "location")` or a path/object.
- Notifications are **deferred** to the event loop: 0 synchronous notifications after changing the value and
  calling `publish_rna`. A stub that accepts subscriptions and (optionally) delivers on an
  explicit "flush" is faithful to the headless behavior.

## 11. UI extension points **[O][L]**

- `Menu/Panel/Header/UIList` inherit from a mixin with `append(fn)`, `prepend(fn)`, `remove(fn)`,
  `is_extended()`. On the first extension the original `draw` is wrapped by a function that calls the
  list of functions in order, catches exceptions from each (prints the traceback and continues), restores the
  `operator_context` between them and filters by owner when the workspace asks. `remove` of a function that was not
  added is silent. `is_extended()` went from `False` to `True` (2 functions in the list).
- Menus/panels that add-ons reference and that exist in the factory setup: `VIEW3D_MT_mesh_add`, `VIEW3D_MT_object`,
  `VIEW3D_MT_add`, `TOPBAR_MT_file_import`, `TOPBAR_MT_file_export`, `VIEW3D_MT_editor_menus`,
  `VIEW3D_MT_edit_mesh`, `NODE_MT_add`, `VIEW3D_PT_tools_active`, `OBJECT_PT_context_object`.
- Keymaps work in background: `window_manager.keyconfigs.addon` is not `None`;
  `keymaps.new(name="3D View", space_type="VIEW_3D")` and
  `keymap_items.new("object.select_all", "A", "PRESS", ctrl=True)` worked.
- `UILayout` has dozens of functions (`row, column, box, split, prop, operator, label, menu,
  template_list, …`); the list with parameter names is in `extras.UILayout_functions`. In
  headless, `draw()` is never called by Blender; the shim can provide a `UILayout` that only records
  the call tree (useful for tests).
- `bpy.utils.register_tool/unregister_tool`, `register_manual_map`, `register_preset_path` exist;
  `register_tool` depends on the tools UI (out of scope for now).

## 12. `bpy.app`, `bpy.utils`, `bpy.path` (surface) **[O]**

- `bpy.app`: `version=(5, 2, 2)`, `version_file=(5, 2, 45)`, `version_string="5.2.2 LTS"`,
  `version_cycle`, `binary_path`, `background`, `factory_startup`, `debug*`, `tempdir`, `cachedir`,
  `driver_namespace` (dict), `handlers`, `timers`, `translations`, `icons`, `build_*`, `online_access`,
  `portable`, `module`, `python_args`, `autoexec_fail*`, `render_icon_size`, `render_preview_size`,
  and library sub-structs (`alembic, ffmpeg, ocio, oiio, opensubdiv, openvdb, sdl, usd`).
  `bpy.app` is a *struct sequence* (it has `n_fields`, `count`, `index`).
- `bpy.utils` (public): `app_template_paths, blend_paths, escape_identifier, execfile,
  expose_bundled_modules, extension_path_user, flip_name, is_path_builtin, is_path_extension,
  keyconfig_init, keyconfig_set, load_scripts, load_scripts_extensions, make_rna_paths,
  manual_language_code, manual_map, modules_from_path, preset_find, preset_paths,
  refresh_script_paths, register_class, register_classes_factory, register_cli_command,
  register_manual_map, register_preset_path, register_submodule_factory, register_tool,
  resource_path, script_path_user, script_paths, script_paths_pref,
  script_paths_system_environment, smpte_from_frame, smpte_from_seconds, system_resource,
  time_from_frame, time_to_frame, unescape_identifier, units, unregister_class,
  unregister_cli_command, unregister_manual_map, unregister_preset_path, unregister_tool,
  user_resource`, and the submodule `previews`. `execfile(path, *, mod=None)` runs as a temporary
  `__main__` and returns the module.
- `bpy.path`: `abspath, basename, clean_name, display_name, display_name_from_filepath,
  display_name_to_filepath, ensure_ext, extensions_audio, extensions_image, extensions_movie,
  is_autoexec, is_subdir, module_names, native_pathsep, reduce_dirs, relpath, resolve_ncase`.
  Paths relative to the .blend use the prefix `//`.
- Name-only inventories for `mathutils` (Vector/Matrix/Quaternion/Euler/Color, `geometry`,
  `kdtree`, `bvhtree`, `noise`, `interpolate`), `bmesh` (`types.BM*`, `ops`, `utils`, `geometry`),
  `gpu`, `blf`, `bpy_extras`, `idprop`, `bl_math` are in `extras`.

---

## 13. What can be faked cheaply vs what needs real behavior

### 13.1 Cheap (a simple stub/registry is enough)

| Area | How to fake it |
|---|---|
| Built-in Menus/Panels/Headers (`VIEW3D_MT_*`, `TOPBAR_MT_*`…) | Empty classes with real `append/prepend/remove/is_extended`; never draw |
| `Panel.draw`, `Menu.draw`, `UIList.draw_item`, `Operator.draw` | Recording `UILayout` (accepts any call, returns sub-layouts) |
| `bl_icon`, `icon=`, `translation_context`, `bl_description` | Accept and store |
| `bpy.app.translations` (`pgettext*`, `register/unregister`) | Identity |
| `bpy.app` build/debug/libs | Plausible constants; configurable `version` (default (5,2,2)) |
| `bpy.msgbus` | Store subscriptions; optional manual `flush()` |
| `bpy.app.timers` | Queue + manual `pump()`; never fires on its own |
| Keymaps (`keyconfigs.addon.keymaps.new`, `keymap_items.new/remove`) | Data objects with no effect |
| `register_manual_map`, `register_preset_path`, `register_cli_command` | In-memory lists |
| `gpu`, `blf`, `gpu_extras` | Modules with no-op functions/explicit "no GPU" error |
| `context.window/screen/area/region/space_data` | `window`/`screen`/`workspace` simple objects; `area`/`space_data` = `None` (same as headless Blender) |
| `bl_options` (`REGISTER`, `UNDO`, `PRESET`, …) | Validate against the enum and store |
| `poll_message_set`, `report` | Store; `report({'ERROR'})` + `CANCELLED` must become `RuntimeError` on the call |
| `invoke` in headless mode | Like Blender: `INVOKE_DEFAULT` without an event falls back to `execute` |
| Extension wheels, permissions, remote repositories | Read/validate the manifest, warn "not supported" |
| Undo | Stack that starts disabled; `ed.undo_push` enables it; optional snapshot later |

### 13.2 Needs real behavior (add-ons break or give wrong results without it)

| Area | Why |
|---|---|
| `register_class/unregister_class` with validation | Errors for `bl_idname`, required attributes, duplicates and the RNA name `MOD_OT_name` in `bpy.types` are a visible contract |
| Collecting `__annotations__` across the MRO + `_PropertyDeferred` | This is how every property is born; mixins (`ImportHelper`, `AddObjectHelper`) depend on it |
| Dynamic assignment `bpy.types.X.p = Prop(...)` / `del` | Add-ons' number 1 pattern for keeping state on the Scene/Object |
| Property semantics: defaults, clamp, `update`, `get/set`, enums (including dynamic and `ENUM_FLAG`), `maxlen`, Vector/Matrix | Add-on logic reads these values |
| `PointerProperty`/`CollectionProperty`/`PropertyGroup` (add/remove/move/find/clear, `name`, `path_from_id`, `id_data`) | Structured state of add-ons |
| Operator call (`bpy.ops.x.y(...)`): kwargs conversion/validation, `poll`, return as a set, exceptions → `RuntimeError` | Add-ons call their own and built-in operators |
| Most-used built-in operators: `mesh.primitive_*_add`, `object.select_all`, `object.delete`, `object.mode_set`, `object.duplicate`, `transform.translate/rotate/resize`, `object.shade_smooth/flat`, `object.transform_apply` [I] | Must have a real effect on Quartz's model |
| Data-blocks: unique `.NNN` names, 255-byte limit, rename, `users`, fake user, `remove` with `ReferenceError` afterwards, `link/unlink` in collections, `get/[]/in` | Add-ons' naming and cleanup logic |
| `Mesh` (from_pydata, vertices/edges/polygons/loops, `foreach_get/set` with numpy, attributes, `update`, `validate`) | Geometry is the core |
| `Object` (location/rotation_euler/scale/matrix_world, parent, data, type, select_set/get, hide_*) | Used by almost everything |
| `context` with `temp_override`, read-only members, `selected_objects`, `active_object`, `view_layer.objects.active` | Operator scope |
| `addon_utils.enable/disable/check/modules/module_bl_info` + AST reading of `bl_info` + extension manifest | It is Path A's own loader |
| `RestrictBlend` during import/register | Fidelity: add-ons that only work by accident must fail the same way (a "lenient" mode may exist) |
| Handlers `frame_change_*`, `depsgraph_update_post`, `load_post`, `save_pre/post` with `(scene, depsgraph)` | Many add-ons react to changes |
| `mathutils` (Vector/Matrix/Quaternion/Euler/Color) numerically correct | Real math; errors show up as wrong geometry |

---

## 14. Pitfalls found

1. **Blender 5.2.2 crash**: reading the `is_overridable` flag of a "type-level" RNA property (no
   instance), e.g. in `bpy.types.Image.bl_rna.properties`, brought Blender down with
   `EXCEPTION_ACCESS_VIOLATION` (stack in `rna_Image_pixels_get_length`). The script avoids this flag.
2. The `is_registered`/`is_registered_optional` flags of the `bl_*` **properties** do not distinguish
   required from optional via Python (all appear as optional); the table in §2.2 comes from
   probes, not from these flags. For **functions** the flag works (`Panel.draw` appears as
   required).
3. Registering a class whose property fails can leave the class half-registered.
4. Old-style assignment (`x = IntProperty()`) is ignored without error.
5. `bpy.props` values on IDs are not in `id.keys()` (5.x).
6. `object.delete` leaves the mesh orphaned; `bpy.data.meshes.remove` also deletes the objects that use
   the mesh and invalidates the Python references of both.
7. Many RNA enums generate "current value '0' matches no enum" warnings when read without an instance —
   noise, not an error.

## 15. Suggested next steps for Quartz

- Generate from the dump a "minimal surface" table (types/properties used by the sampled
  add-ons — cross with `data/bpy_usage.json` produced by another step, if it exists).
- Turn the probes into shim **conformance tests**: the same script running in Blender
  (golden) and in Quartz, comparing the JSON output.
- Not yet verified by execution: `modal` behavior with real events, `invoke` with a real
  window/area, undo with effective steps, `load_post`/`save_*` (require opening/saving a .blend),
  real installation of an extension into a repository.
