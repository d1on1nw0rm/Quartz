# Quartz architecture proposal — "minimal-incremental" angle

> Quartz — author: **D1on1n**. Design document for the initial milestone (Path C = native `quartz` API;
> Path A = `bpy-lite` layer in `compat/`). Date: 2026-10-22.
>
> Bases: `docs/research/bpy_usage.md`, `docs/research/bpy_contract.md`, `docs/research/c4d_model.md`,
> `data/bpy_usage.json`, `data/blender_api_dump.json`. Clean-room hygiene: no Blender code and no
> Cinema 4D resource was copied; names appear only as identifiers, and all the code below is
> an original Quartz sketch.
>
> Legend used in the text: **[O]** observed (Blender or `.venv` Python, executed); **[L]** deduced from
> reading; **[I]** inference to be confirmed by differential testing.

---

## 0. Thesis on one page

The shortest path to "real add-ons loading in Quartz" is **a single bpy-shaped core**,
written in pure Python + numpy, in which the `compat/` folder is almost only a **re-export of the same objects**.
There are no two data models, two property systems, or two registries: `bpy.types.Object`
**is** `quartz.types.Object`; `bpy.props.IntProperty` **is** `quartz.props.IntProperty`. `compat/` holds
only what is exclusive to Blender's peculiarities (fake version number, `RestrictBlend`, "ghost"
`*_MT_*` menus, synthetic `bl_ext` package, `addon_utils`, `gpu`/`blf` stubs).

What is optimized: **time to the first green sweep** and **ease of refactoring**. What is accepted
as a cost: performance on large scenes (many things are *derived on demand*, O(N)), and an
explicit, tested list of small divergences. Cinema 4D concepts (descriptions, per-channel dirty,
generators) enter now only as **named seams**, not as functionality.

The 10 main decisions (detailed in the following sections):

| # | Decision | Section |
|---|---|---|
| D1 | Identity, not wrapping: `compat/bpy` re-exports the `quartz` objects; "thinness" rules verified by test | 2, 6 |
| D2 | One property engine for everything (native types and add-ons): `_PropertyDeferred` → descriptors; `describe()` is the seam for the C4D *description* | 4 |
| D3 | Layer 1 with no cross dependencies thanks to a dependency-inversion hooks module (`quartz/_hooks.py`) | 2, 10.1 |
| D4 | Flat registry: one `Registry` (RNA name → class, idname → operator, owner → classes) with validation by base class | 5.1 |
| D5 | SoA mesh in numpy with attributes as the single source of truth, in a pure `quartz.geometry` (no ID) | 3.6 |
| D6 | "Derive instead of maintain": `users`, `children`, `matrix_world` computed on demand; removal by swapping `__class__` | 3.3 |
| D7 | Context = table of *providers* + stack of overrides; `RestrictedContext`/`RestrictedData` in the registry; session with in-place `reset()` | 5.5 |
| D8 | Built-in operators are classes registered through the public API (dogfooding); `ops.call()` implements the observed contract; snapshot undo with preserved identity | 5.3–5.6 |
| D9 | Sweep first: subprocess-isolated harness, STATIC→UNREGISTER_CLEAN levels, missing-symbols log, Blender's own baseline and ratchet | 7.4, 9.5 |
| D10 | Differential test triad: *golden* scripts running in Blender and Quartz through the same runner, conformance with the dump, contract tests | 9 |

---

## 1. What this angle optimizes — and the golden rules

### 1.1 Goals (in order)

1. **Early green sweep**: the largest possible number of `addons_core` add-ons and `templates_py`
   templates reaching, in Quartz, the same result they reach in headless Blender
   (import → register → clean unregister).
2. **Cheap refactoring**: few concepts, simple Python classes, a single metaclass, no
   code generator. Every structure that will change later (user counting, evaluation, undo,
   descriptions) stays behind a stable API.
3. **Measurable fidelity**: each contract behavior becomes a test; each divergence becomes a line
   in a `COMPAT.md` table + a test that pins it down (so nobody "fixes" it by accident).

### 1.2 What is knowingly sacrificed

- Performance on large scenes (thousands of objects): `users`, `children`, `scene.objects`,
  `matrix_world` are computed on every read. Replacing them with incremental caches is a future
  internal refactoring, guided by benchmark, without changing the API.
- C4D features (tags, generators, fields, MoGraph, versioned assets): **postponed**, with seams only.
- Modal/event loop, rendering, GPU, reading/writing `.blend`: out of the milestone.

### 1.3 Golden rules

1. **One implementation, two facades.** If something exists in `bpy` and makes sense in Quartz, it lives in
   `quartz` with the same name; `compat` only re-exports. If it only makes sense in Blender, it lives in `compat`.
2. **Derive before maintaining.** Incremental state is only kept when a benchmark proves the
   need.
3. **The observed contract rules.** Same exception type as Blender; paraphrased message, but
   containing the same key identifiers (tests check fragments, never the exact text).
4. **The sweep drives the backlog.** Priority = (targets unblocked) ÷ (cost); the ranking comes from the
   missing-symbols log.
5. **Layers verified by test.** An AST test (`tests/test_layering.py`) fails if a module
   imports a layer above its own.
6. **Little magic.** One metaclass (`StructMeta`), data descriptors, dictionaries. No
   `__slots__` (swapping `__class__` and flexibility depend on `__dict__`).
7. **Named seams for C4D**, never speculative implementations: `PropertyDef.meta`,
   `props.describe()`, `ID._q_dirty`, `Object.data` open to new types, `q_schema_version` reserved.
8. **Clean-room.** Implement from the research documents (paraphrased contract), never with
   the Blender source code open alongside. A test looks for Blender license headers and Blender asset
   data (e.g. Suzanne coordinates) inside `quartz/` and `compat/`.

---

## 2. Package and file layout

```
D:/Claude/reverseEngineering/Quartz/
├─ quartz/                      # native API (Path C) — all the real implementation
│  ├─ __init__.py               # facade: types, props, data, context, ops, utils, app, math, geometry, path
│  ├─ __main__.py               # `python -m quartz` → quartz.cli.main()
│  ├─ _hooks.py                 # C1 — dependency inversion hooks (array wrap, current context, file path)
│  ├─ util/                     # C1 — leaf utilities (stdlib only)
│  │  ├─ naming.py              #   unique names ".001", UTF-8 truncation to 255 bytes
│  │  ├─ paths.py               #   bpy.path functions (pure)
│  │  └─ idpath.py              #   parse/resolve of data paths ('modifiers["Bend"].angle[0]') + escape_identifier
│  ├─ math/                     # C1 — mathutils core (numpy)
│  │  ├─ __init__.py            #   Vector, Matrix, Quaternion, Euler, Color, axis_conversion
│  │  ├─ _base.py               #   float32 storage, wrap/owner, freeze
│  │  ├─ vector.py  matrix.py  quaternion.py  euler.py  color.py
│  │  ├─ scalar.py              #   clamp/lerp/smoothstep (base of bl_math)
│  │  ├─ geometry.py            #   subset of mathutils.geometry
│  │  ├─ kdtree.py              #   KDTree
│  │  └─ bvhtree.py             #   BVHTree (numpy brute force; later)
│  ├─ props.py                  # C1 — property engine (bpy.props + descriptors + describe)
│  ├─ geometry/                 # C1 — pure geometry in numpy (does not know ID)
│  │  ├─ attributes.py          #   AttributeStore/AttributeArray, domains, types
│  │  ├─ mesh.py                #   MeshGeometry (SoA), topology, from_pydata, validate
│  │  ├─ normals.py  triangulate.py  primitives.py
│  │  ├─ editmesh.py            #   bmesh core (scheduled for later)
│  │  └─ editmesh_ops.py        #   triangulate/remove_doubles/... (scheduled for later)
│  ├─ types/                    # C2 — types (Struct, ID and data-blocks, Operator, UI, WM, prefs)
│  │  ├─ __init__.py
│  │  ├─ struct.py              #   StructMeta, Struct, PropertyGroup, RNAStruct/RNAProperty, IDRef, IDProperty*
│  │  ├─ id.py                  #   ID, classes "Removed*"
│  │  ├─ object.py              #   Object, ObjectModifiers/Constraints (stubs), VertexGroups
│  │  ├─ mesh.py                #   Mesh + proxies (MeshVertex...), AttributeGroup, UV layers
│  │  ├─ material.py  camera.py  light.py  world.py  image.py  text.py
│  │  ├─ collection.py          #   Collection, CollectionObjects, CollectionChildren
│  │  ├─ scene.py               #   Scene, ViewLayer, LayerObjects, LayerCollection, RenderSettings, UnitSettings, ToolSettings, View3DCursor
│  │  ├─ operator.py            #   Operator, OperatorProperties, OperatorOptions, Event
│  │  ├─ ui.py                  #   Panel, Menu, Header, UIList + extension mixin (append/prepend/remove)
│  │  ├─ wm.py                  #   WindowManager, Window, Screen, WorkSpace, KeyConfigs/KeyMap/KeyMapItem
│  │  ├─ prefs.py               #   Preferences, Addon(s), AddonPreferences, minimal sub-structs
│  │  └─ stubs.py               #   RenderEngine, HydraRenderEngine, FileHandler, GizmoGroup, Gizmo, KeyingSetInfo,
│  │                            #   AssetShelf, WorkSpaceTool, Node/NodeTree/NodeSocket, OperatorFileListElement
│  ├─ database.py               # C2 — BlendData, IDCollection (+ subclasses per type), RestrictedData
│  ├─ registry.py               # C2 — flat Registry, register_class/unregister_class, owner_scope
│  ├─ contexts.py               # C2 — Context, RestrictedContext, provider table
│  ├─ ops.py                    # C2 — call() + namespace `quartz.ops.<mod>.<op>`
│  ├─ operators/                # C2 — built-in operators (registered like any add-on)
│  │  ├─ __init__.py  object.py  mesh.py  transform.py  ed.py  wm.py
│  ├─ ui.py                     # C2 — recording UILayout, draw_ui()
│  ├─ undo.py                   # C2 — snapshot-based UndoStack
│  ├─ depsgraph.py              # C2 — Depsgraph/DepsgraphUpdate facade (no evaluation yet)
│  ├─ app/                      # C2 — version, settings, paths, handlers, timers, msgbus, translations
│  ├─ session.py                # C2 — Session, reset(), factory scene
│  ├─ utils.py                  # C2 — register_*_factory, add_object, user_resource, previews, units...
│  ├─ compat.py                 # C3 — activate()/deactivate(), log of missing symbols
│  ├─ addons.py                 # C3 — discovery, bl_info, manifest, enable/disable/check, bl_ext
│  ├─ sweep.py                  # C3 — sweep harness, reports, ratchet
│  ├─ cli.py                    # C3 — subcommands info/scan-addon/enable-addon/run-script/addon-sweep
│  └─ devtools/bpyscan.py       # C3 — static scanner (core extracted from tools/scan_bpy_usage.py)
├─ compat/                      # Path A — thin shims, only activated by quartz.compat.activate()
│  ├─ bpy/  __init__.py types.py props.py ops.py path.py msgbus.py _ui_names.py
│  │        utils/{__init__,previews,units}.py  app/{__init__,handlers,timers,translations,icons}.py
│  ├─ mathutils/  __init__.py geometry.py kdtree.py bvhtree.py noise.py interpolate.py
│  ├─ bmesh/  __init__.py types.py ops.py utils.py geometry.py
│  ├─ bpy_extras/  __init__.py io_utils.py object_utils.py anim_utils.py node_utils.py
│  │               view3d_utils.py image_utils.py mesh_utils.py asset_utils.py
│  ├─ gpu/ (stubs: state, shader, matrix, types, texture, platform)   gpu_extras/{batch,presets}.py   blf.py
│  ├─ addon_utils.py  bl_math.py  rna_prop_ui.py  idprop/{__init__,types}.py
│  └─ bl_ui/{__init__,utils}.py     # only PresetPanel and the like, on demand
├─ tests/
│  ├─ conftest.py               # fixtures: clean session, compat activated, user dir in tmp/
│  ├─ unit/        test_math_*.py test_props_*.py test_geometry_*.py test_naming.py test_paths.py test_idpath.py
│  ├─ model/       test_id_semantics.py test_users_remove.py test_object_transforms.py test_mesh_api.py
│  │               test_scene_collections.py test_registry.py test_ops_call.py test_context.py
│  │               test_undo.py test_handlers.py test_ui_layout.py test_depsgraph.py
│  ├─ compat/      test_contract_registration.py test_contract_props.py test_contract_ops.py
│  │               test_contract_context.py test_contract_data.py test_mathutils_api.py
│  │               test_bpy_extras.py test_bmesh_subset.py test_addon_utils.py
│  ├─ golden/      harness.py  scripts/g01_factory_scene.py ... g14_addon_lifecycle.py  test_golden.py
│  ├─ conformance/ test_dump_props.py test_dump_ops.py test_dump_signatures.py
│  ├─ sweep/       fixtures/{addons,extensions,scripts}/...  test_sweep_fixtures.py  test_sweep_ratchet.py
│  ├─ test_headers.py  test_layering.py  test_cleanroom.py  test_compat_thinness.py
│  └─ test_scan_bpy_usage.py    # already exists
├─ tools/                       # already exist: scan_bpy_usage.py, dump_bpy_api.py, run_dump_bpy_api.ps1
│  ├─ golden_runner.py          # runs a golden script INSIDE the host (Blender or Quartz) and writes JSON
│  ├─ run_golden.py             # orchestrates: headless Blender and/or Quartz, with timeout, writes data/golden/
│  ├─ blender_sweep_baseline.py # runs INSIDE Blender: enable/disable of each add-on, counts classes
│  ├─ run_blender_baseline.ps1  # user resources env redirected to tmp/ (like run_dump_bpy_api.ps1)
│  └─ gen_ui_names.py           # generates compat/bpy/_ui_names.py (curated list) from the dump + usage
├─ data/  golden/*.blender.json   sweep/{blender_baseline,quartz_latest,ratchet}.json
└─ docs/  design/  research/      (later: README.md, ARCHITECTURE.md, COMPAT.md, ROADMAP.md in pt-BR)
```

### 2.1 Allowed import graph (verified by `tests/test_layering.py`)

| Module | Layer | May import |
|---|---|---|
| `quartz._hooks`, `quartz.util.*` | C1 (leaf) | stdlib, numpy |
| `quartz.math.*` | C1 | stdlib, numpy, `_hooks`, `util` |
| `quartz.props` | C1 | stdlib, numpy, `_hooks`, `util` |
| `quartz.geometry.*` | C1 | stdlib, numpy, `_hooks`, `util` |
| `quartz.types.*`, `database`, `registry`, `contexts`, `ops`, `operators.*`, `ui`, `undo`, `depsgraph`, `app.*`, `session`, `utils` | C2 | C1 + C2 |
| `quartz.compat`, `addons`, `sweep`, `cli`, `devtools.*` | C3 | C1 + C2 + C3 |
| `compat/**` | C3 | stdlib, numpy, `quartz.*` and other `compat/` modules — **never** its own data state |

`math`, `props` and `geometry` do not import each other. Where they would need to (e.g. `props` returning a
`Vector`, or an `update(self, context)` callback needing the context), they use `quartz._hooks`, which
Layer 2 fills in at `quartz/__init__.py`. This way each Layer 1 track can be written and tested in
parallel, with fake hooks in the tests.

Note on names: `quartz/math/` and `quartz/types/` do not shadow the stdlib `math`/`types` because
Python 3 only does absolute imports. The modules that hold global instances have names distinct from the
instances: `quartz/database.py` defines `BlendData`, and `quartz.data` is **the instance**;
`quartz/contexts.py` defines `Context`, and `quartz.context` is **the instance** (as in `bpy`).

---

## 3. Core data model

### 3.1 `Struct` — the base of everything (equivalent to `bpy_struct`)

- Plain Python class with the `StructMeta` metaclass, which does only three things:
  1. `Cls.attr = <_PropertyDeferred>` creates the property on the spot (`props.define_property`), and
     `del Cls.attr` removes it — this is how `bpy.types.Scene.my_tool = PointerProperty(...)` works;
  2. `Cls.is_registered` = `"bl_rna" in Cls.__dict__` (observed rule **[L][O]**);
  3. nothing else.
- Per-instance state: `_p` (values of the declared properties), `_p_set` (names explicitly
  assigned → `is_property_set`), `_idprops` ("dictionary" properties, `ob["x"]`, created
  on demand), `_owner` + `_path` (for `id_data` and `path_from_id()` of nested structs).
- This reproduces the Blender 5.x *split* **[O]**: `bpy.props` values on IDs do **not** appear in
  `id.keys()`/`id["k"]`; `ob["x"] = 3.5` does not become `ob.x`. Observed exception: on
  `PropertyGroup` instances (non-ID), `keys()` also lists the values already written — `Struct.keys()` applies this
  rule according to `isinstance(self, ID)`.
- `bl_rna` (class) is a **view** (`RNAStruct`) built from `props.describe(cls)`;
  `rna_type` (instance) returns the same view. Implicit `rna_type` property included in the list,
  as in Blender (add-ons skip it by identifier).

### 3.2 `ID` and `BlendData`

- `ID(Struct)` adds: `name` (setter goes through the collection), `name_full`, `id_type`, `session_uid`
  (global counter), `users` (derived), `use_fake_user`, `use_extra_user`, `is_evaluated=False`,
  `original` (itself), `library=None`, `is_embedded_data`, `tag`, `asset_data=None`,
  `animation_data=None`; methods `copy()`, `rename(name, mode='NEVER')` (5.2 signature in the dump:
  returns a result enum), `evaluated_get(depsgraph)`, `user_clear()`, `user_remap(new_id)`,
  `user_of_id(id)`, `make_local()`, `animation_data_create/clear()`, `update_tag(refresh=set())`,
  `asset_mark/asset_clear()`, `bl_system_properties_get()`.
- `BlendData` has one `IDCollection` per type: `objects, meshes, materials, cameras, lights,
  collections, scenes, worlds, images, texts` (core) and, as simple containers without evaluation,
  `actions, armatures, curves, node_groups, libraries, window_managers, screens, workspaces`
  (scheduled as the sweep demands). Plus `filepath=''`, `is_dirty`, `is_saved=False`, `version`,
  `user_map()`, `orphans_purge()`, `batch_remove()`.
- `IDCollection`: `new(...)` with the signature of each type (read from the dump: `objects.new(name,
  object_data)`, `lights.new(name, type)`, `images.new(name, width, height, alpha, float_buffer, ...)`),
  `remove(id, do_unlink=True, do_id_user=True, do_ui_user=True)`, `get`, `[name|index]`, `in`,
  `keys/values/items`, `find`, `tag`, `foreach_get/foreach_set`, `len`, `iter`.
- **Names [O]**: unique per type with a `.NNN` suffix; an ID renamed to an existing name gets the
  suffix; 255 UTF-8 bytes, truncating at a character boundary; empty name → the type's default name.
  Pure implementation in `quartz.util.naming.unique_name()`, tested against the dump values.
- **Iteration order [I]**: Blender keeps the ID lists sorted by name (the factory scene
  lists `["Dots Stroke", "Material"]`). The `IDCollection` iterates over a cached sorted index,
  invalidated on `new/rename/remove`. The exact rule (uppercase, numbers) is pinned down by golden `g02`.

### 3.3 "Derive instead of maintain" — `users`, children, removal

- Each `Struct` knows how to list the ID references it holds: `Struct._q_refs() -> Iterator[IDRef]`,
  where `IDRef = (target, counts_user, clear, remap)`. The generic implementation walks the class's
  `PointerDef`/`CollectionDef` (including nested `PropertyGroup`s); native types
  add what is structural (objects of a `Collection`, `Mesh.materials`, the `Scene`'s master
  collection).
- `ID.users` = sum of `counts_user` over all IDs in the database + `use_fake_user`. Initial rules
  (to be confirmed in golden `g03` **[I]** except where marked): `Object.data` +1 **[O]**; object link
  in a collection +1 **[O]**; fake user +1 **[O]**; collection child +1; material in `Mesh.materials`
  +1; `Scene.world` +1; `Scene.camera` and `Object.parent` do not count; add-on `PointerProperty` to
  an ID counts.
- `Object.children`, `children_recursive`, `users_collection`, `users_scene`, `Scene.objects`,
  `ViewLayer.objects` are also on-demand scans (Blender itself computes `children` by
  scanning).
- **Removal** (`IDCollection.remove`): undoes all references (via `IDRef.clear`), removes from the
  name index and **swaps `obj.__class__` for `Removed<Type>`**, whose `__getattribute__` raises
  `ReferenceError("StructRNA of type Mesh has been removed")` for any attribute — zero cost on the
  hot path, observed behavior **[O]** (including on a second `remove`). Removing a
  `Mesh` also removes the objects that use it **[O]**; `objects.remove(ob)` leaves the mesh orphaned **[O]**.
- When a benchmark calls for it, `users` becomes an incremental counter behind the same property; the
  differential tests guarantee the same semantics.

### 3.4 `Object`: transforms and hierarchy

Properties declared with the props engine (same names, defaults and limits as the dump):
`location`, `rotation_mode` (`QUATERNION, XYZ, XZY, YXZ, YZX, ZXY, ZYX, AXIS_ANGLE`, default `XYZ`),
`rotation_euler` (returns `Euler` with `order` = current mode if it is Euler), `rotation_quaternion`
(default `(1,0,0,0)`), `rotation_axis_angle` (default `(0,0,1,0)`), `scale` (default `(1,1,1)`),
`delta_location/delta_rotation_euler/delta_rotation_quaternion/delta_scale`, `parent`,
`parent_type='OBJECT'`, `matrix_parent_inverse` (4×4, identity), `matrix_basis`, `matrix_local`,
`matrix_world`, `dimensions`, `bound_box`, `type` (read-only, derived from `data`), `mode`,
`hide_viewport/hide_render/hide_select`, `color`, `pass_index`, `display_type`, `show_name`,
`show_in_front`, `empty_display_type/size`, `instance_type`, `instance_collection`.

Formulas (written from mathematical memory; confirmed by golden `g06`):

- `R` comes from the mode: Euler in the given order (order `'XYZ'` = apply X, then Y, then Z, that is,
  `R = Rz·Ry·Rx` **[I]**), normalized quaternion, or axis-angle.
- Deltas: Euler `R_tot = R(delta)·R(rot)`, quaternion `q_tot = q_delta ⊗ q`; `s_tot = scale ⊙
  delta_scale`; `t = location + delta_location` **[I]**.
- `matrix_basis = T(t) · [R_tot · diag(s_tot)]`.
- `matrix_local = matrix_parent_inverse · matrix_basis`;
  `matrix_world = parent.matrix_world · matrix_parent_inverse · matrix_basis`.
- Writing to `matrix_world`/`matrix_local`/`matrix_basis`: isolates the basis relative to the parent and decomposes
  (translation = column 3; scale = norm of the columns, **all three negated if the determinant is
  negative [I]**; rotation = normalized columns → current mode), discounting the deltas.
- **Documented divergence**: Quartz computes `matrix_world` on read (always current); Blender
  only updates it on depsgraph evaluation. Add-ons that call `view_layer.update()` keep
  working; those that depend on the stale value diverge (rare).
- `Object.data` accepts any ID registered as "object data" (`quartz.types.OBJECT_DATA_TYPES`:
  `Mesh→MESH`, `Camera→CAMERA`, `Light→LIGHT`, `Curve→CURVE`, `Armature→ARMATURE`, `None→EMPTY`) —
  **seam** for the future C4D `Generator`.

### 3.5 Selection, visibility, and modes

- Selection and "hidden in the view layer" live in the `ViewLayer` (like Blender's *bases*), in a dict
  `session_uid → Base(select, hide)`. `ob.select_get(view_layer=None)`, `select_set(state,
  view_layer=None)`, `hide_get/hide_set`, `visible_get()` use `context.view_layer` when omitted.
  `view_layer.objects.active` validates membership (`ValueError` if the object is not in the view layer).
- Modes: `Object.mode` (`OBJECT, EDIT, POSE, SCULPT, ...`) and derived `context.mode`
  (`EDIT_MESH`, `EDIT_CURVE`, `EDIT_ARMATURE`, `POSE`...). `object.mode_set` takes all selected
  objects of the same type as the active one into the mode, and fills in `context.edit_object` and
  `objects_in_mode`. The items of the `mode` enum depend on the type of the active object (dynamic enum — the props
  engine needs to support this anyway).
- Mesh edit mode (once `editmesh` exists): on entering, `Mesh._q_edit: EditMesh` is created; the
  `Mesh` data stays **frozen** until the mode is exited or `update_from_editmode()` is called — same as Blender.
  `bmesh.from_edit_mesh()` returns that `EditMesh`. Before that, `mode_set('EDIT')` only switches the mode.

### 3.6 `Mesh` in numpy (SoA)

`quartz.geometry.MeshGeometry` (Layer 1, no ID) is the source of truth; `quartz.types.Mesh` (Layer 2) composes it.

- Attributes as the **single source**, with the same internal names observed in Blender **[O]**:
  `position` (POINT, FLOAT_VECTOR, `(V,3) float32`), `.edge_verts` (EDGE, INT32_2D, `(E,2) int32`),
  `.corner_vert` and `.corner_edge` (CORNER, INT, `(L,) int32`), `sharp_face` (FACE, BOOLEAN),
  `.select_vert/.select_edge/.select_poly`, UVs as CORNER FLOAT2 (`UVMap`), colors as
  FLOAT_COLOR/BYTE_COLOR, `material_index` as FACE INT. Prefix `.` = internal.
- Faces by **offsets**: `face_offsets (F+1,) int32` — `loop_start = offsets[i]`,
  `loop_total = offsets[i+1] - offsets[i]`. It is not an attribute (as in Blender).
- `AttributeStore` knows the size of each domain and resizes all attributes of the domain
  together (`resize(domain, n)`), with default fill per type.
- Cheap proxies for the per-element API: `mesh.vertices[i]` → `MeshVertex(mesh, i)` with `co`
  (Vector wrapping the *view* of the row), `normal`, `select`, `hide`, `index`; likewise `MeshEdge`,
  `MeshLoop`, `MeshPolygon` (`vertices`, `loop_start`, `loop_total`, `material_index`, `use_smooth`,
  `normal`, `center`, `area`, `edge_keys`), `MeshLoopTriangle`.
- `foreach_get/foreach_set` via a **mapping table** (`("vertices","co") → position`,
  `("edges","vertices") → .edge_verts`, `("loops","vertex_index") → .corner_vert`,
  `("polygons","loop_start") → offsets[:-1]`, `("polygons","use_smooth") → ~sharp_face`, ...),
  accepting a list or numpy buffer of any dtype with the correct flat size (copy with
  `np.copyto(..., casting="unsafe")`) **[O]**.
- `from_pydata(vertices, edges, faces, shade_flat=True)`: a quad yields 4/4/4/1 **[O]**; edges
  derived from the faces by deduplicating unoriented pairs, in order of first occurrence. If the
  golden shows a different order in Blender, the algorithm is adjusted (the default comparison is by set of
  `edge_keys`; exact order only for cube and plane).
- Normals (Newell per face; per vertex angle-weighted **[I]**), triangulation (fan for
  convex, *ear clipping* for non-convex), `transform(matrix)`, `flip_normals`, `validate()`,
  `clear_geometry()`, `shade_flat/shade_smooth`, `set_sharp_from_angle`, `calc_loop_triangles`,
  `update(calc_edges=False, calc_edges_loose=False)`.

### 3.7 Material, Camera, Light, World, Image, Text

- **Material**: `diffuse_color (4)`, `metallic`, `roughness`, `specular_intensity`, `blend_method`,
  `use_backface_culling`, `pass_index`, `use_nodes`, `node_tree=None` (nodes deferred),
  `is_grease_pencil`. Slots: only `DATA` *link* in this milestone — `Mesh.materials` (`append/pop/clear`),
  `Object.material_slots` (derived), `active_material`, `active_material_index`.
- **Camera**: `type (PERSP/ORTHO/PANO)`, `lens` (50, min 1, soft_max 5000 — from the dump), `sensor_width`,
  `sensor_height`, `sensor_fit`, `clip_start`, `clip_end`, `ortho_scale`, `shift_x/y`, `angle*`
  (derived from `lens`/sensor), `dof` (simple struct), `view_frame()`.
- **Light**: a base class `Light` + `PointLight/SunLight/SpotLight/AreaLight`; the `type` setter
  performs the same `__class__` swap (Blender's *type recast*), keeping the values in `_p`.
  Per-subtype properties (`energy`, `shadow_soft_size`, `spot_size`, `spot_blend`, `size`, `angle`)
  live in the subclasses, as in the dump.
- **World**: `color`, `use_nodes`, `node_tree=None`.
- **Image**: metadata (`size`, `filepath`, `source`, `generated_color`, `alpha_mode`) and `pixels`
  as a flat float32 RGBA array created on demand; `images.load()` only records the path (without
  decoding); `save()` deferred.
- **Text**: `lines`, `as_string()`, `from_string()`, `write()`, `clear()`, `filepath`,
  `texts.load(filepath, internal=False)`.

### 3.8 Collection, Scene, ViewLayer

- `Collection`: `objects` (`link` — `RuntimeError` if already linked **[O]**; `unlink`), `children`
  (`link` with cycle check), `all_objects`, `hide_*`, `color_tag`, `instance_offset`.
- `Scene`: `collection` (built-in master collection "Scene Collection", outside `bpy.data.collections`),
  `view_layers` (a default "ViewLayer"), `world`, `camera`, `frame_start/end/current/step`,
  `frame_set(frame, subframe=0.0)` (fires `frame_change_pre/post` with `(scene, depsgraph)` **[O]**),
  `render` (resolution, fps, engine, filepath), `unit_settings`, `tool_settings` (stub), `cursor`,
  `objects` (derived).
- `ViewLayer`: `name`, `objects` (`LayerObjects` with `active`, `selected`), `layer_collection` /
  `active_layer_collection` (`LayerCollection` tree derived from the hierarchy, with `exclude`,
  `hide_viewport`), `depsgraph`, `update()` (dispatches `depsgraph_update_pre/post` if there was dirtiness).

### 3.9 Numeric policy: "float32 at rest, float64 in transit"

- Blender stores RNA and `mathutils` floats in 32 bits: reading back `0.1` gives
  `0.10000000149011612` **[L/I]** (confirm in `g07`/`g13`). So that printed outputs and simple
  comparisons match Blender, Quartz **rounds to float32 when storing** (`Float*` props,
  components of `Vector/Matrix/Quaternion/Euler/Color`, geometry arrays) and **computes in float64**
  (numpy), rounding the result when storing it.
- Integer props: 32-bit range (default `min=-2**31`, `max=2**31-1`), with *clamp*.
- Default tolerance of the differential tests: `abs=1e-5, rel=1e-5` (configurable per key).

### 3.10 Factory scene

`quartz.session.build_factory_scene()` reproduces the **facts** of the dump **[O]**: Scene "Scene"; collection
"Collection" under the "Scene Collection"; objects Camera (location ≈ 7.3589, −6.9258, 4.9583), Cube
(origin; mesh "Cube" 8 v / 12 e / 6 f / 24 loops with UV "UVMap") and Light (≈ 4.0762, 1.0055,
5.9039); materials "Material" and "Dots Stroke"; World "World"; frames 1–250; engine `BLENDER_EEVEE`;
units `METRIC`; Cube active and selected. Camera and light rotations are not in the dump — they will be
measured by golden `g01` and recorded as constants (an API fact, not code).

### 3.11 Seams for Cinema 4D (nothing implemented beyond this)

| C4D idea (see `c4d_model.md`) | Seam in this milestone | When it becomes a feature |
|---|---|---|
| Inheritable/dynamic *Description* (§3) | `PropertyDef.meta` (free dict: `group`, `unit`, `parent`, `enabled_if`, `ui`, `channel`) + `props.describe(cls)` + optional hook `@classmethod q_describe(cls, desc)` | UI milestone: `Description` replaces `describe()` without changing callers |
| Typed hierarchical address (DescID) (§4) | `quartz.util.idpath` (bpy data paths) as the single key | Animation/drivers/overrides/differential undo |
| Per-channel dirty (§7) | `ID._q_dirty = {"DATA","MATRIX","GEOMETRY","SELECT"} → int`, incremented by the descriptor (channel comes from `meta["channel"]`) | Real depsgraph, evaluation cache, incremental undo |
| Generator as data (§6) | Open `Object.data` (`OBJECT_DATA_TYPES`) and `evaluated_get()` as the swap point | Generators/modifiers milestone |
| Schema version/`disklevel` (§8) | reserved class attribute `q_schema_version` (unused) | Quartz file format |
| Phased handlers (§8) | lists `startup_post`, `shutdown_pre`, `shutdown_post` in `quartz.app.handlers` (Quartz only) | Already usable; fired by the CLI |
| Behavior tags (§5) | reserved name `Object.tags` (not created) | C4D milestone |

---

## 4. Property system (`quartz.props`, Layer 1)

### 4.1 Lifecycle

1. `IntProperty(name="x", default=3)` **creates nothing**: it returns `_PropertyDeferred(function,
   keywords)` with `.function is IntProperty` and `.keywords == {"name": "x", "default": 3}` **[O]**.
   The accepted kwargs are exactly those of 5.2.2 (table of contract §4.1) **plus just one** from Quartz:
   `meta: dict | None` — the *description* seam. Unknown kwarg → `TypeError`.
2. `install_properties(cls)` (called by `register_class` for add-on classes and by the decorator
   `@native_type` for built-in types — **the same code**) collects the annotations of the entire MRO,
   in base → derived order, and creates one **data descriptor** (`PropertyDef`) per name. Mixins without
   `bpy_struct` (ImportHelper, AddObjectHelper) work because the collection walks the entire MRO **[O]**.
3. Old-style assignment `x = IntProperty()` in the class body is **silently ignored** **[O]** (it stays
   as a plain attribute; the sweep logs a "legacy property assignment" warning).
4. `Cls.attr = Prop(...)` on an existing type → `define_property`; `del Cls.attr` →
   `remove_property` **[O]**.

### 4.2 Descriptors and storage

- `PropertyDef.__get__(inst)`: if the user supplied `get=`, call it and convert; otherwise read `inst._p` (or the
  default); wrap arrays via hook (§4.4).
- `PropertyDef.__set__(inst, value)`: read-only (`get` without `set`) → `AttributeError`
  "... is read-only" **[O]**; converts/validates (`coerce`), applies *clamp*/truncation, writes to `_p` (or
  calls `set=`), marks `_p_set`, increments `inst._q_dirty[channel]` if present, and **calls `update(self,
  context)` on every Python assignment, even without a change and even after clamp** **[O]**.
- Minimal owner protocol (duck typing): `_p: dict`, `_p_set: set`, optional `_q_on_change(pdef)`.
  `quartz.props` does not know `Struct` — it is tested with a 5-line class.

### 4.3 Semantics by type (everything observed in contract §4.4, except [I])

| Type | Stored as | Rules |
|---|---|---|
| Bool / BoolVector | `bool` / `np.ndarray(bool)` | wrong type → `TypeError` |
| Int / IntVector | `int` / `np.ndarray(int32)` | clamp to `min/max`; float → `TypeError` |
| Float / FloatVector | `float` rounded to float32 / `np.ndarray(float32)` | clamp; `int` accepted |
| String | `str` | `maxlen` truncates (`maxlen=8` → 8 characters) **[O]**; multibyte rule **[I]** |
| Enum | `str` identifier; `frozenset` with `ENUM_FLAG` | `items` list of tuples `(id, name, desc[, icon[, number]])` or function `(self, context)`; default outside the items → `ValueError` at registration; invalid value → `TypeError` listing the valid ones; **enum `get/set` callbacks work with the item's integer [I]** |
| Pointer | ID (reference) or `PropertyGroup` instance (created on demand, persistent) | `type=` must be a registered `PropertyGroup` or an ID type, otherwise `ValueError` "... could not register" **[O]**; wrong type on assignment → `TypeError` **[O]**; pointer to PG is not assignable; `poll` respected |
| Collection | `PropCollection` of `PropertyGroup` instances | `add()` returns the item, `remove(i)`, `clear()`, `move(a,b)`, `find(name)`, `keys()` by `name`, `coll["name"]` **[O]**; every PG has an implicit `name` |

### 4.4 Arrays and the wrapping hook

- The array descriptor calls `_hooks.wrap_array(view, subtype, on_write, owner)`. Layer 2 installs
  the factory: subtypes `TRANSLATION, DIRECTION, VELOCITY, ACCELERATION, XYZ, XYZ_LENGTH, COORDINATES`
  → `Vector`; `EULER` → `Euler`; `QUATERNION` (4) → `Quaternion`; `COLOR`/`COLOR_GAMMA` (3) →
  `Color`; `MATRIX` → `Matrix`; the rest → `PropArray` (the `bpy_prop_array`) **[I for the exact list]**.
- Stored values are an `np.ndarray` kept **in the same object** (`np.copyto` on assignment);
  the wrapper receives a *view*, so `v = ob.location; ob.location.x = 5; v.x == 5` (live read,
  like Blender's wrapper). Per-component writes call `on_write`, which reapplies clamp, `update`
  and dirty.
- Properties with `get/set` (including native ones, such as `matrix_world`) return a wrapper over a
  copy; a per-component write calls `set` with the whole array.

### 4.5 Annotations in Python 3.14 — verified risks

Verified by running in the `.venv` (Python 3.14.7) **[O]**:

1. Annotations are **lazily evaluated** (PEP 649): `IntProperty(...)` inside `x: ...` is only
   called on the first access to `__annotations__` — in Quartz, in `register_class`, seeing the
   module globals *at that moment* (in Blender, with Python 3.13, evaluation happens at class creation).
   Test: with `DEFAULT = 1` at definition and `DEFAULT = 2` before the access, the default read was 2.
2. The trick used by Blender helpers (`if "__annotations__" not in cls.__dict__: setattr(cls,
   "__annotations__", {})`) **wipes out** existing annotations in 3.14 (the class lost `y`, and
   `__annotate_func__` disappears from `__dict__`, so there is no way to recover them).
3. Modules with `from __future__ import annotations` (there are several in `bl_operators` and in `cycles`, e.g.
   `bl_operators/add_mesh_torus.py`) deliver **strings**, which must be evaluated with the module
   globals and the class namespace.

Design consequences:

- `props.collect_annotations(cls)` uses `annotationlib.get_annotations(c, format=VALUE)` per class in the
  MRO and, for strings, `eval(text, vars(sys.modules[c.__module__]), dict(vars(c)))`.
- The `orientation_helper` in our `compat/bpy_extras` is written with `annotationlib` (reads, merges,
  rewrites the full dictionary) — never with the trick above.
- **Annotation pinning** in the loader: after importing each add-on module (and submodules), 
  `quartz.addons` walks the module-level classes and forces evaluation of the annotations. This
  approximates the 3.13 "at class creation" semantics for the common case. Add-ons that use trick (2)
  on their own keep breaking; the sweep flags them.

### 4.6 `describe()` and `bl_rna`

`props.describe(cls) -> tuple[PropertyDef, ...]` is the **only** source of metadata: `RNAStruct`
(`bl_rna`), the future attribute editor, generated documentation, and the conformance tests against the dump
all read from it. `PropertyDef.describe()` returns a dict in the same format as `data/blender_api_dump.json`
(`type, subtype, unit, flags, array_length, default, min, max, soft_min, soft_max, step, precision,
items`) — which makes comparison with the dump trivial.

---

## 5. Registration, operators, context, undo, and app

### 5.1 Flat registry (`quartz.registry`)

- A process-global `Registry` (as in Blender, it survives `session.reset()`):
  `classes: dict[str, type]` (RNA name → class, for **all** bases), `operators: dict[str, type]`
  (`"mesh.primitive_cube_add"` → class), `owners: dict[type, str | None]`, `current_owner`.
- `register_class(cls)`:
  1. `cls` must inherit from a registrable base (`_q_registrable = True`), otherwise `RuntimeError`
     **[O]**; already registered (`"bl_rna" in cls.__dict__`) → `ValueError` "already registered" **[O]**.
  2. `base._q_validate(cls) -> rna_name` applies the base's rules (table 5.2).
  3. Same `bl_idname` already registered → silently unregisters the old one **[O]**.
  4. `props.install_properties(cls)`; on failure, **rolls everything back** (Blender may leave the class half
     registered — documented, deliberate divergence).
  5. Sets `cls.bl_rna`, indexes it, records the owner (`current_owner`, which the loader sets during the
     add-on's `register()`), and calls the class's `register()` classmethod if it exists **[L/I]**
     (used by 11 `PropertyGroup`s in the corpus).
- `unregister_class(cls)`: not registered → `RuntimeError` "missing bl_rna ... (may not be
  registered)" **[O]**; calls `cls.unregister()` if it exists, removes descriptors and indexes.
- `bpy.types` is a *view* of the registry: `compat/bpy/types.py` has a module-level `__getattr__(name)` that
  queries `REGISTRY.classes` (and records the missing name in the sweep log before the `AttributeError`).

### 5.2 Validation by base class (facts from contract §2)

| Base | Required | Name in `bpy.types` | Other rules |
|---|---|---|---|
| `Operator` | `bl_idname` (`mod.name`, 1 dot, `[a-z0-9_]`, identifier ≤ 60), `bl_label` | `MOD_OT_name` | without `bl_idname` it uses the class name and fails the rule; `bl_options` validated against the enum |
| `Panel` | `bl_label`, `bl_space_type`, `bl_region_type`, `draw` | `bl_idname` or class name | invalid space/region → `TypeError`; nonexistent `bl_parent_id` → `RuntimeError`; name without `_PT_` → warning only |
| `Menu` | `bl_label`, `draw` | same | name without `_MT_` → warning |
| `Header` | `bl_space_type`, `draw` | same | `bl_region_type` default `HEADER` |
| `UIList`, `AddonPreferences`, `PropertyGroup` | — | `bl_idname` or name | `AddonPreferences.bl_idname` must match the module to be useful |
| Stubs (`RenderEngine`, `HydraRenderEngine`, `FileHandler`, `GizmoGroup`, `Gizmo`, `KeyingSetInfo`, `AssetShelf`, `Node*`) | `bl_idname` when Blender requires it **[I]** | `bl_idname` | accept registration and store the class; nothing is executed |

### 5.3 Operator call (`quartz.ops.call`)

```
call(idname, *args, **kwargs) -> set[str]
  args: up to 2 positional — exec_context ('EXEC_DEFAULT', 'INVOKE_DEFAULT', ...) and undo (bool);
        positional dict → ValueError                                      [O]
  cls = REGISTRY.operators[idname]          → otherwise AttributeError "could not be found"   [O]
  op  = cls(); op._q_assign(kwargs)         → unknown kwarg/wrong type/invalid enum: TypeError;
                                               out of range: silent clamp                 [O]
  if not cls.poll(context): RuntimeError("Operator bpy.ops.<id>.poll() <message from poll_message_set
                                          or 'failed, context is incorrect'>")        [O]
  INVOKE_* without event (headless) → goes straight to execute (settings.invoke_in_background=False) [O]
  ret = op.execute(context)  → exception inside: RuntimeError with the traceback in the text      [O]
  validates ret ⊆ {RUNNING_MODAL, CANCELLED, FINISHED, PASS_THROUGH, INTERFACE}, otherwise RuntimeError [O]
  report ERROR + CANCELLED → RuntimeError("Error: <msg>"); INFO/WARNING only print     [O]
  FINISHED and 'UNDO' in bl_options and undo enabled and undo != False → undo.push(bl_label)
  return ret
```

The same callable serves both facades: `quartz.ops.mesh.primitive_cube_add(size=1)` and
`bpy.ops.mesh.primitive_cube_add(size=1)`, with `poll()`, `idname()` → `"MESH_OT_primitive_cube_add"`,
`get_rna_type()` and `bl_options` **[O]**. Values do not persist between calls **[O]**. Inside the
operator, `self.x` reads/writes the property and `self.properties` is a view (`OperatorProperties`) that
shares the same `_p`; `as_keywords(ignore=...)` and `properties.is_property_set(...)` work **[O]**.

### 5.4 Built-in operators (dogfooding)

Written in `quartz/operators/*.py` as ordinary `Operator` classes, registered by
`quartz.operators.register_builtin()` with owner `"quartz.builtin"`. Order, driven by real usage:

1. `object.mode_set(mode, toggle=False)` (Tier 1, 184 calls), `object.select_all(action)`,
   `object.delete(use_global=False, confirm=True)`, `object.transform_apply(location, rotation,
   scale, properties)`, `object.duplicate(linked=False)`, `object.shade_smooth/shade_flat`,
   `object.add/empty_add/camera_add/light_add`.
2. `mesh.primitive_{plane,cube,circle,uv_sphere,ico_sphere,cylinder,cone,grid,torus}_add` with the
   properties and defaults from the dump (`size=2.0`, `calc_uvs=True`, `align`, `location`, `rotation`,
   `scale`). `mesh.primitive_monkey_add` is registered with a false `poll` and the message "Suzanne data not
   included (clean-room)" — the Suzanne data is a Blender asset and will not be copied.
3. `transform.translate/rotate/resize` (subset of properties), `ed.undo`, `ed.redo`,
   `ed.undo_push(message)`, `wm.read_factory_settings`, `wm.read_homefile` (= reset),
   `wm.call_menu/call_menu_pie` (headless result pinned by the Blender baseline).

The geometric logic lives in pure functions (`quartz.geometry.primitives`, `quartz.utils.add_object`);
the operators only translate properties → calls. To compare with Blender, we test counts,
bounding boxes and topological invariants; exact index order only for `cube` and `plane`.

### 5.5 Context (`quartz.contexts`)

- `Context` resolves `ctx.member` in two steps: top of the override stack → table
  `PROVIDERS: dict[str, Callable[[Session], Any]]`. Providers cover the 75 members of 5.2 **[O]**:
  non-null in headless — `scene, view_layer, collection, layer_collection, active_object, object,
  selected_objects, selected_editable_objects, selectable_objects, visible_objects, editable_objects,
  objects_in_mode, objects_in_mode_unique_data, window_manager, window, screen, workspace,
  preferences, blend_data, tool_settings, engine, mode`; null — `area, region, region_data,
  space_data, edit_object` (outside edit mode), `active_bone, active_pose_bone, active_operator`, ...
- Members are read-only (`AttributeError` "... is read-only") **[O]**. `temp_override(**members)`
  pushes and restores on exit; unknown keys are accepted and do not become attributes **[O]**.
  `copy()`, `path_resolve(path, coerce=True)`, `evaluated_depsgraph_get()`.
- `RestrictedContext` (only `window_manager` and `preferences`) and `RestrictedData` (empty, attributes →
  `AttributeError`) — used by the loader during import + `register()` **[O]**, swapping
  `bpy.context`/`bpy.data` **and** `quartz.context`/`quartz.data` (module attributes).
- Session: `quartz.session.SESSION` holds `data`, `window_manager`, `preferences`, `context`, `undo`.
  The identities are **stable**: `reset(factory=True)` clears and rebuilds *in place*, so
  `from bpy import data` captured in a module remains valid. Tests use a fixture that calls
  `reset()`.

### 5.6 Undo (`quartz.undo`)

- `UndoStack` starts **off** in background, like Blender: `ed.undo.poll()` is false with a message
  asking for `ed.undo_push()` **[O]**; the first `push` turns it on. Useful consequence: scripts and sweep pay
  no snapshot cost by default.
- `push(message)`: snapshot of the entire state, by ID, `(class, copy of _p with ndarrays copied,
  nested structs, MeshGeometry.copy())`, name index, view layer bases, current frame.
  `undo()/redo()` restore **into the same Python object** (identity preserved; IDs removed after the
  snapshot are "resurrected" by switching `__class__` back). Benign divergence: in Blender,
  Python references may become invalid after undo **[I]**.
- Future optimization without changing the API: snapshot only the IDs whose `_q_dirty` changed since the last step.
- `undo_pre/undo_post/redo_pre/redo_post` handlers are dispatched.

### 5.7 `quartz.app`: handlers, timers, msgbus, translations

- `handlers`: Blender's 39 lists **[O]** (plain `list` objects) + `startup_post`,
  `shutdown_pre`, `shutdown_post` (Quartz only); `persistent(fn)` marks `fn._bpy_persistent = True`
  **[O]**; `dispatch(name, *args)` isolates exceptions from each callback (prints traceback and continues);
  `reset()` removes non-persistent handlers. Firing points in this milestone: `frame_set`
  (`frame_change_pre/post`), `ViewLayer.update` / `evaluated_depsgraph_get` (`depsgraph_update_*`),
  `session.reset` (`load_pre/load_post`, `load_factory_startup_post` **[I]**), undo/redo.
- `timers`: `register/unregister/is_registered` + manual `pump(now=None)` (they never fire on their own,
  as in headless **[O]**).
- `msgbus`: `subscribe_rna/publish_rna/clear_by_owner` + manual `flush()` (0 synchronous notifications,
  as observed **[O]**).
- `translations`: real and cheap implementation — `register(module, dictionary)`, lookup by
  `(context, msgid)` in the current `locale`; in `en_US` (default) it is the identity. `pgettext_n` returns the
  msgid. `contexts` with the fields listed in the dump. Ready for the future UI's pt-BR.
- `version = (0, 1, 0)` is the **Quartz** version; the "Blender" version (`(5, 2, 2)`, `"5.2.2 LTS"`,
  `version_file (5, 2, 45)`) exists only in `compat/bpy/app`.

### 5.8 Headless UI (`quartz.ui` + `quartz.types.ui`)

- `UILayout` **recorder**: `row, column, box, split, grid_flow, column_flow, panel` (returns
  `(header, body)`), `prop, prop_search, prop_enum, prop_menu_enum, props_enum, operator`
  (returns the operator's `OperatorProperties` for `op.x = 1`), `operator_menu_enum, menu, label,
  separator, separator_spacer, template_list, template_ID, context_pointer_set, popover` and attributes
  (`active, enabled, alert, alignment, scale_x/y, use_property_split, use_property_decorate,
  operator_context, emboss`). Any other `template_*` is accepted and recorded (lenient mode) or becomes a
  warning (strict mode). `prop()` with a nonexistent property records a warning (Blender only prints
  **[I]**). `to_tree()` serializes for tests.
- Extension mixin on `Panel/Menu/Header/UIList`: `append/prepend/remove/is_extended` **[O]**;
  `remove` of an absent function is silent **[O]**. `draw_ui(cls, context=None) -> UILayout` instantiates,
  calls `draw` and each attached function with exception isolation — this is what the sweep's UI_SMOKE level uses.
- Blender "ghost" menus/panels (`TOPBAR_MT_file_import`, `VIEW3D_MT_mesh_add`, ...) live in
  `compat/bpy/_ui_names.py` (**curated** list of ~60 names, generated by `tools/gen_ui_names.py` from
  the 32 UI symbols in use + the common ones from contract §11). In lenient mode (sweep default),
  an unknown `bpy.types.X_MT_y` is synthesized on demand **and noted in the report**; in strict
  mode (contract tests), `AttributeError` as in Blender.

### 5.9 Depsgraph (facade without evaluation)

`Depsgraph(scene, view_layer)`: `update()`, `updates` (list of `DepsgraphUpdate(id,
is_updated_geometry, is_updated_transform, is_updated_shading)` derived from the `_q_dirty` counters
since the last read), `objects`, `object_instances` (no real instances: one item per object),
`ids`, `id_eval_get(id)`, `id_type_updated(type)`, `scene_eval`, `view_layer_eval`.
`evaluated_get()` returns the original itself (no modifiers) — the point where the future evaluator
(modifiers, generators) plugs in.

---

## 6. How `compat/bpy` maps onto `quartz`

### 6.1 Mapping table

| Blender name | Implementation | Nature |
|---|---|---|
| `bpy.types.Object`, `Mesh`, `Scene`, ..., `Operator`, `Panel`, `PropertyGroup`, `bpy_struct`, `bpy_prop_collection` | `quartz.types.*` | **identity** |
| `bpy.types.<RegisteredName>` (`QUARTZ_OT_x`, add-on panels) | `REGISTRY.classes` via module `__getattr__` | view |
| `bpy.types.TOPBAR_MT_file_import` and similar | `compat/bpy/_ui_names.py` (subclasses of `quartz.types.Menu/Panel/Header`) | Blender only |
| `bpy.props.*` | `quartz.props.*` | identity (same function objects) |
| `bpy.data` / `bpy.context` | `quartz.data` / `quartz.context`; swapped for `RestrictedData/RestrictedContext` at registration | identity + swap |
| `bpy.ops` | `quartz.ops` namespace | identity |
| `bpy.utils.*` | `quartz.utils.*` (including `user_resource`, `extension_path_user` on top of `quartz.app.paths`) | identity |
| `bpy.path` | `quartz.util.paths` | identity |
| `bpy.app.version`, `version_string`, `version_file`, `build_*`, `alembic/usd/...` | constants in `compat/bpy/app/__init__.py` (configurable in `activate()`) | Blender only |
| `bpy.app.handlers/timers/translations`, `bpy.msgbus` | `quartz.app.*` (same lists/functions) | identity |
| `mathutils.*`, `mathutils.geometry/kdtree/bvhtree` | `quartz.math.*` | identity |
| `bmesh` | `quartz.geometry.editmesh(_ops)` with names `BMesh/BMVert/...` | name adapter |
| `bpy_extras.io_utils` | `ImportHelper/ExportHelper` mixins (annotations only + `invoke/check`), `orientation_helper` (annotationlib), `axis_conversion` = `quartz.math.axis_conversion` | glue |
| `bpy_extras.object_utils` | `AddObjectHelper` (annotations) + `object_data_add` = `quartz.utils.add_object` | glue |
| `addon_utils` | facade over `quartz.addons.MANAGER` | facade |
| `gpu`, `gpu_extras`, `blf` | stubs: state change = no-op; producing pixels → `SystemError` "no GPU in background" **[I]** | Blender only |
| `idprop.types` | `quartz.types.IDPropertyGroup/IDPropertyArray` | identity |
| `bl_math` | `quartz.math.scalar` | identity |
| `rna_prop_ui` | `rna_idprop_ui_create` etc. over `Struct.id_properties_ui` | glue |
| `bl_ui.utils.PresetPanel`, `bl_operators.presets.AddPresetBase` | minimal stubs, on demand from the sweep | Blender only |
| `_bpy`, `_cycles`, `_bl_i18n_utils`, `OpenImageIO` | **not provided** (`ImportError`) | out of scope |

### 6.2 `quartz.compat.activate()`

```python
def activate(*, blender_version=(5, 2, 2), lenient_ui=True, record_missing=True,
             restrict_register=True) -> None
```

1. Refuses if a real `bpy` is already in `sys.modules` (`RuntimeError`).
2. Inserts `compat/` (or `$QUARTZ_COMPAT_DIR`) into `sys.path[0]`, idempotent.
3. Imports `bpy` (the shim), which registers the names that Blender exposes as synthetic submodules
   (`bpy.types`, `bpy.app`, `bpy.app.handlers`, `bpy.app.translations` **[L]** — here they are real
   files, so `from bpy.app.handlers import persistent` works).
4. Adjusts `quartz.app.settings` (lenient/strict, recording of missing symbols) and
   `quartz.types.REPR_ROOT = "bpy"` (so that `repr(ob) == "bpy.data.objects['Cube']"`).

`deactivate()` removes the path and the `compat` modules from `sys.modules` (for use in tests);
`missing_symbols() -> collections.Counter[str]`; `activated(**kw)` is the context manager.

### 6.3 Thinness rules (verified)

- `tests/test_compat_thinness.py`: (a) `compat/` modules only import stdlib, numpy, `quartz.*` and
  other `compat/` modules; (b) no class in `compat/` holds an `np.ndarray` or a scene-data dictionary
  as an instance attribute (simple AST check for `self.<x> = np.`); (c) budget: `compat/` lines ≤ 30% of
  `quartz/` lines (an alarm, not dogma).
- Anything a `compat` test needs that is not a Blender peculiarity becomes a task in `quartz`.

---

## 7. Add-on and extension loader (`quartz.addons`)

### 7.1 Discovery and metadata

- Sources: `quartz.app.paths.addon_dirs` (legacy add-ons; they go into `sys.path`, as in Blender) and
  `quartz.app.paths.extension_repos` (`{"user_default": dir, "system": dir, ...}`), both configurable
  via CLI (`--path`, `--repo NAME=DIR`). Scan like `bpy.path.module_names`: `*.py` (except
  `__init__.py`) and non-hidden folders with `__init__.py`; `modules/` ignored **[L]**.
- `read_bl_info(path)`: reads UTF-8; fast mode = from the first line that **starts with** `bl_info` to the
  first blank line, `ast.parse` + `ast.literal_eval` **[L]**; without `bl_info` → `None` + warning.
  `normalize_bl_info()` fills in the base fields (`name, author, version, blender, location,
  description, doc_url, support='COMMUNITY', category, warning, show_expanded=False`), strips e-mails
  `<...>` from `author` **[O]** and expands `{BLENDER_MANUAL_URL}`.
- `Manifest.load(path)` with `tomllib` (stdlib, verified available): required `schema_version,
  id, name, tagline, version, type, maintainer, license (list), blender_version_min`; optional
  `blender_version_max, website, copyright, permissions, tags, platforms, wheels, [build]`; validation
  (`type ∈ {add-on, theme}`, `id` an identifier without `__` and without `_` at the ends, `paths` xor
  `paths_exclude_pattern`) **[L]**. `to_bl_info()` synthesizes the `bl_info` (`description←tagline`,
  `author←maintainer`, `blender←blender_version_min`, `category='Development'`) **[L]**.

### 7.2 `enable` / `disable` / `check` (contract §5.1)

```python
class AddonManager:
    def enable(self, module_name: str, *, default_set: bool = False, persistent: bool = False,
               refresh_handled: bool = False, handle_error=None, restrict: bool = True) -> ModuleType | None
```

1. Already enabled in `sys.modules` → `unregister()` first; mtime changed → `importlib.reload`.
2. `default_set` → entry in `preferences.addons` **before** the import.
3. Inside `restrict_blend()` + `registry.owner_scope(module_name)`: `importlib.import_module`,
   annotation pinning (§4.5), `mod.register()`.
4. Failure → `handle_error(ex)` (default: prints traceback), removes the module **and submodules** from
   `sys.modules`, undoes `default_set`, returns `None`. As in Blender, classes registered before the
   exception stay registered; `leaks(module_name)` lists them for the report.
5. Success → `__addon_enabled__ = True`, `__addon_persistent__ = persistent`, returns the module **[O]**.

`disable()` clears the flags, calls `unregister()` (error reported, not propagated) and **keeps** the module
in `sys.modules` **[O]**. `check(name) -> (loaded_default, loaded_state)` **[O]**. Preferences:
`context.preferences.addons[name].preferences` creates, on demand, the instance of the `AddonPreferences`
registered with `bl_idname == name` **[O]**.

### 7.3 Extensions

- Synthetic `bl_ext` package (`ModuleType` with `__path__ = []`) and one subpackage per repository
  (`bl_ext.user_default.__path__ = [dir]`), inserted into `sys.modules`; the normal import resolves
  `bl_ext.<repo>.<id>` **[O for the name]**. `check_extension(name)` = `bl_ext.` prefix.
- After the import: deletes the module's `bl_info` and writes the synthetic one **[L]**.
- `extension_path_user(__package__, path="", create=False)` →
  `<user_dir>/extensions/.user/<repo>/<id>/<path>`, with `user_dir` inside the project under
  development (§7.4).
- `wheels` and remote repositories: read, validated, **not installed** (warning in the report); the
  import may then fail and this shows up in the sweep.

### 7.4 Execution sandbox (compliance with Rule 1)

Running add-on code is the purpose of Path A, but it must not write outside the project:

- The sweep and `enable-addon` run in a **subprocess** `python -B -X utf8 -m quartz ...` (`-B` = no
  `__pycache__` — importing from `C:/Program Files/...` could try to write bytecode into the Blender
  installation), `cwd = <project>/tmp/sweep_cwd`, `QUARTZ_USER_DIR = <project>/tmp/sweep_user`
  (`user_resource`, `extension_path_user`, `tempdir` point there), `PYTHONIOENCODING=utf-8`.
- In `--sweep-mode`, `socket.socket.connect`/`create_connection` raise `PermissionError`
  (`bpy.app.online_access = False`), and `subprocess.Popen` is recorded in the report.
- Timeout per target (default 60 s) and total under 3 minutes per command (`--jobs N` parallelizes).

---

## 8. CLI (`python -m quartz`)

| Command | What it does | Output |
|---|---|---|
| `info [--json]` | versions (Quartz, Python, numpy), directories (`compat`, user dir, repositories), registry counts (by base), built-in operators, session summary | text or JSON |
| `scan-addon TARGET [--json]` | static, without importing: `bl_info`/manifest, imports, `bpy.*` symbols used (core of the existing scanner) and **prediction** of missing ones (each symbol is resolved against the activated `compat`) | report + `missing_predicted` |
| `enable-addon MOD\|PATH [--path DIR]... [--repo N=DIR]... [--no-restrict] [--smoke-ui] [--keep-enabled] [--json] [--sweep-mode]` | one full cycle: metadata → import → register → (UI_SMOKE) → unregister → leaks | `SweepResult` in JSON |
| `run-script FILE.py [--empty] [--no-compat] [--addon MOD]... [-- args]` | like `blender --python`: `__name__ == "__main__"`, `sys.argv` after `--`, factory scene (or empty) | exit code 1 on exception |
| `addon-sweep [--blender-scripts DIR] [--only N]... [--no-templates] [--fixtures] [--jobs N] [--timeout S] [--json OUT] [--md OUT] [--baseline F] [--update-ratchet]` | discovers targets, runs each in isolation, compares with the Blender baseline and with the ratchet | `data/sweep/quartz_latest.json` + `.md` in pt-BR |

Exit codes: `0` ok; `1` failure (or ratchet regression, in the sweep); `2` usage error.
`SweepResult` example (JSON):

```json
{"target": "io_anim_bvh", "kind": "LEGACY_PACKAGE", "level": "UNREGISTER_CLEAN", "ok": true,
 "registered": {"Operator": 2}, "menus_extended": ["TOPBAR_MT_file_import", "TOPBAR_MT_file_export"],
 "ui_smoke": {"drawn": 2, "failed": 0, "skipped_poll": 0}, "missing_symbols": {},
 "warnings": [], "leaks": [], "error": null, "seconds": 0.41}
```

---

## 9. Testing strategy

### 9.1 Pyramid

1. **Unit** (Layer 1, fast, no session): math, props with a fake owner, geometry,
   naming/paths/idpath.
2. **Model** (Layer 2): ID semantics, users/removal, transforms, mesh, registry, ops,
   context, undo, handlers, UI.
3. **Contract** (via `compat`, strict mode): one file per section of `bpy_contract.md`, each test
   citing the section; same exception types, messages by fragment.
4. **Differential** (golden 9.2, dump conformance 9.3), **probe contract** (9.4) and
   **sweep** (9.5).
5. **Architecture lints**: `test_headers.py` (every `.py` in the project starts with a one-line docstring
   and `# Quartz - author: D1on1n`), `test_layering.py`, `test_compat_thinness.py`, `test_cleanroom.py`
   (no `SPDX-License-Identifier: GPL` nor Blender copyright header in `quartz/`/`compat/`).

Default `pytest -q` runs 1–5 without Blender (the goldens are already-recorded JSONs). Marker `-m sweep` runs the
real sweep; `-m blender` re-records goldens (requires Blender, with timeouts).

### 9.2 Symmetric golden runner

- `tests/golden/harness.py` (pure Python, runs on both hosts): `emit(key, value, tol=None)`,
  `capture(key, fn)` (exception → `{"exc": type, "msg": text}`), normalization (Vector/Matrix →
  lists via `to_tuple`/iteration, `set` → sorted list, raw floats).
- `tools/golden_runner.py SCRIPT OUT.json` runs **inside the host**: in Blender via
  `blender --background --factory-startup --python-exit-code 1 --python tools/golden_runner.py -- ...`
  (with user resources redirected, as in `run_dump_bpy_api.ps1`), in Quartz via
  `python -m quartz run-script tools/golden_runner.py -- ...`. Same runner, same script.
- `tests/golden/test_golden.py` runs the Quartz side and compares with `data/golden/<script>.blender.json`:
  floats with tolerance, exceptions by type + declared fragments, lists marked as an unordered
  set.
- Initial scripts (original): `g01_factory_scene`, `g02_id_naming` (suffixes, 255 bytes, iteration
  order), `g03_users_and_remove`, `g04_mesh_from_pydata`, `g05_primitives`, `g06_object_transforms`
  (all rotation modes, deltas, parents, `matrix_world` set, negative scale),
  `g07_props_semantics` (clamp, `update` count, ENUM_FLAG, `maxlen`, returned types, float32),
  `g08_registration_errors`, `g09_operator_contract`, `g10_context_override`,
  `g11_collections_linking`, `g12_handlers_frame_set`, `g13_mathutils_numeric` (random vectors with a
  seed: inverse, decompose, Euler↔Quaternion in all 6 orders, slerp, `to_track_quat`, `repr`),
  `g14_addon_lifecycle` (fixture add-on).

### 9.3 Dump conformance (without running Blender)

- `test_dump_props.py`: for each (type, property) that Quartz declares natively,
  `PropertyDef.describe()` must match `data/blender_api_dump.json` in `type, subtype, unit,
  array_length, default, min, max, soft_min, soft_max, items` (allowlist of documented divergences).
- `test_dump_ops.py`: built-in operators with the same property names and defaults as
  `ops.submodules` in the dump (e.g. `mesh.primitive_cube_add.size` = 2.0, min 0).
- `test_dump_signatures.py`: parameter names of `IDCollection.new/remove`, `ID.rename`,
  `Mesh.update` etc. equal to the dump's `functions`.
- This turns hundreds of already-collected facts into free tests and prevents silent drift.

### 9.4 Contract tests

They reuse the script of the probes in `tools/dump_bpy_api.py` (`operator_basic`,
`registration_errors`, `required_bl_attrs`, `idprop_storage`, `property_semantics`, `id_semantics`,
`context_semantics`, `undo_and_handlers`, `ui_extension_points`, `addon_lifecycle`): the result
observed in Blender is in the dump's `probes`, and the test runs the same probe in Quartz and compares.

### 9.5 Sweep (levels, baseline, ratchet)

Levels per target:

| Level | Criterion |
|---|---|
| `STATIC` | all files parse; predicted missing symbols listed |
| `METADATA` | `bl_info`/manifest read and valid |
| `IMPORT` | import inside `RestrictBlend` without exception |
| `REGISTER` | `register()` without exception; class count by base |
| `UI_SMOKE` | `draw_ui` of each Panel (if `poll` passes), Menu and ghost menu extended by the owner |
| `UNREGISTER_CLEAN` | `unregister()` without exception, no leaked class, menus restored |

- **Blender baseline**: `tools/blender_sweep_baseline.py` runs inside headless Blender (one session
  for the 13 add-ons — sequential enable/disable; one process per template, 20 s timeout) and writes
  `data/sweep/blender_baseline.json` with the level reached and the **count of classes registered by base**.
  "Green" for a target = Quartz reaches the same level as Blender **and** registers the same counts
  by base. This also separates "Quartz failure" from "natural failure in headless" (modal templates,
  operators that require a VIEW_3D area).
- **Missing log**: every module `__getattr__` in `compat` (`bpy.types`, `bpy.ops.<mod>`,
  `bpy.data`, `bpy.context`, `mathutils`, `bpy_extras.*`) notes the name before the `AttributeError`, even
  when the add-on catches it with `hasattr`. The report ranks symbols by number of blocked
  targets — this ranking **is** the backlog.
- **Ratchet**: `data/sweep/ratchet.json` stores the best level of each target; `test_sweep_ratchet.py`
  (marker `sweep`) fails if any target regresses; `--update-ratchet` only goes up.
- **Own fixtures** (`tests/sweep/fixtures/`, original code): single-file add-on, package add-on
  with submodules and `AddonPreferences`, extension with `blender_manifest.toml`, add-on that fails
  in `register` (checks `sys.modules` cleanup), add-on that uses `from __future__ import
  annotations`, add-on that extends `TOPBAR_MT_file_import`. They always run in `pytest -q`.
- Initial result hypotheses **[I]**, to be measured: `cycles` fails in `register` (imports the native
  module `_cycles`) and `bl_pkg` uses private `addon_utils` API and network — both out of scope;
  `hydra_storm`, `io_curve_svg`, `io_anim_bvh`, `io_mesh_uv_layout` (with `gpu` stub), `ui_translate`,
  `io_scene_fbx`, `node_wrangler`, `pose_library`, `viewport_vr_preview`, `rigify` and `io_scene_gltf2`
  are candidates for `UNREGISTER_CLEAN` by the end of Layer 3; templates with ≤ 3 symbols outside the core
  (34 of 38) should match the baseline.
- After the milestone: `SCENARIO` level with curated scripts per add-on (`tests/sweep/scenarios/
  io_anim_bvh.py`: import a fixture BVH, export to `tmp/`, compare with Blender's output).

---

## 10. Implementation order in 3 layers — public APIs

Conventions: every file starts with a one-line docstring + `# Quartz - author: D1on1n`; signatures
below are the public contract (they may gain optional parameters, not lose any). Names with `_q_` are
internal to Quartz and are not part of the Blender API.

### 10.1 Layer 1 — foundations without cross dependencies

Parallel tracks: **U** (`_hooks` + `util`, small, first), **M** (`math`), **P** (`props`),
**G** (`geometry`). None imports the others (except U).

#### `quartz/_hooks.py`

```python
WrapArray = Callable[[np.ndarray, str, Callable[[np.ndarray], None] | None, Any], Any]
def wrap_array(values: np.ndarray, subtype: str, on_write: Callable[[np.ndarray], None] | None,
               owner: Any) -> Any            # default: None → props uses PropArray
def current_context() -> Any                 # default: None
def blend_filepath() -> str                  # default: ""
def install(*, wrap_array: WrapArray | None = None, current_context: Callable[[], Any] | None = None,
            blend_filepath: Callable[[], str] | None = None) -> None
def reset() -> None
```

#### `quartz/util/naming.py`

```python
MAX_NAME_BYTES: int = 255
def truncate_utf8(name: str, max_bytes: int = MAX_NAME_BYTES) -> str
def split_suffix(name: str) -> tuple[str, int | None]          # "Cube.001" -> ("Cube", 1)
def unique_name(name: str, is_taken: Callable[[str], bool], *, default: str,
                max_bytes: int = MAX_NAME_BYTES) -> str
```

#### `quartz/util/paths.py` (body of `bpy.path`)

```python
def abspath(path: str, *, start: str | None = None, library: Any = None) -> str   # prefix "//"
def relpath(path: str, *, start: str | None = None) -> str
def basename(path: str) -> str
def clean_name(name: str, *, replace: str = "_") -> str
def display_name(name: str, *, has_ext: bool = True, title_case: bool = True) -> str
def display_name_from_filepath(name: str) -> str
def display_name_to_filepath(name: str) -> str
def ensure_ext(filepath: str, ext: str, *, case_sensitive: bool = False) -> str
def is_subdir(path: str, directory: str) -> bool
def module_names(path: str, *, recursive: bool = False, package: str = "") -> list[tuple[str, str]]
def native_pathsep(path: str) -> str
def reduce_dirs(dirs: Iterable[str]) -> list[str]
def resolve_ncase(path: str) -> str
extensions_image: frozenset[str]; extensions_movie: frozenset[str]; extensions_audio: frozenset[str]
```

#### `quartz/util/idpath.py`

```python
@dataclass(frozen=True)
class PathToken: kind: Literal["ATTR", "INDEX", "KEY"]; value: str | int
def parse(path: str) -> tuple[PathToken, ...]       # 'modifiers["Bend"].angle[0]'
def format(tokens: Iterable[PathToken]) -> str
def resolve(root: Any, path: str, *, coerce: bool = True) -> Any
def escape_identifier(string: str) -> str
def unescape_identifier(string: str) -> str
```

#### `quartz/math/` (core of mathutils)

```python
class Vector:
    def __init__(self, seq: Iterable[float] = (0.0, 0.0, 0.0)) -> None
    @classmethod
    def Fill(cls, size: int, fill: float = 0.0) -> "Vector": ...
    @classmethod
    def Range(cls, start: int, stop: int | None = None, step: int = 1) -> "Vector": ...
    @classmethod
    def Linspace(cls, start: float, stop: float, size: int) -> "Vector": ...
    @classmethod
    def Repeat(cls, vector: Iterable[float], size: int) -> "Vector": ...
    x: float; y: float; z: float; w: float           # + xyzw swizzles of 2–4 letters via __getattr__/__setattr__
    length: float; length_squared: float; magnitude: float
    is_frozen: bool; is_wrapped: bool; is_valid: bool; owner: Any
    def copy(self) -> "Vector"; def freeze(self) -> "Vector"
    def to_tuple(self, precision: int = -1) -> tuple[float, ...]
    def to_2d(self) -> "Vector"; def to_3d(self) -> "Vector"; def to_4d(self) -> "Vector"
    def resize(self, size: int) -> None; def resized(self, size: int) -> "Vector"
    def resize_2d(self) -> None; def resize_3d(self) -> None; def resize_4d(self) -> None
    def normalize(self) -> None; def normalized(self) -> "Vector"; def negate(self) -> None
    def dot(self, other) -> float; def cross(self, other) -> "Vector | float"
    def angle(self, other, fallback: Any = None) -> float
    def angle_signed(self, other, fallback: Any = None) -> float
    def lerp(self, other, factor: float) -> "Vector"
    def slerp(self, other, factor: float, fallback: Any = None) -> "Vector"
    def project(self, other) -> "Vector"; def reflect(self, mirror) -> "Vector"
    def orthogonal(self) -> "Vector"; def rotate(self, other: "Euler | Quaternion | Matrix") -> None
    def rotation_difference(self, other) -> "Quaternion"
    def to_track_quat(self, track: str = "Z", up: str = "Y") -> "Quaternion"
    # operators: + - (vector), * (scalar or element-wise), / scalar, @ (dot; Vector @ Matrix),
    # unary -, ==, !=, < <= > >= (by length), len, [int|slice], iter, __array__, hash (frozen only),
    # repr "Vector((1.0, 2.0, 3.0))"
    @classmethod
    def _q_wrap(cls, view: np.ndarray, on_write: Callable[[np.ndarray], None] | None, owner: Any) -> "Vector": ...

class Matrix:
    def __init__(self, rows: Iterable[Iterable[float]] | None = None) -> None   # None → 4×4 identity
    @classmethod
    def Identity(cls, size: int) -> "Matrix": ...
    @classmethod
    def Rotation(cls, angle: float, size: int, axis: "str | Vector") -> "Matrix": ...
    @classmethod
    def Translation(cls, vector) -> "Matrix": ...
    @classmethod
    def Scale(cls, factor: float, size: int, axis=None) -> "Matrix": ...
    @classmethod
    def Shear(cls, plane: str, size: int, factor) -> "Matrix": ...
    @classmethod
    def OrthoProjection(cls, axis: "str | Vector", size: int) -> "Matrix": ...
    @classmethod
    def Diagonal(cls, vector) -> "Matrix": ...
    @classmethod
    def LocRotScale(cls, location, rotation, scale) -> "Matrix": ...
    row: "MatrixAccess"; col: "MatrixAccess"; translation: Vector; median_scale: float
    is_identity: bool; is_negative: bool; is_orthogonal: bool; is_orthogonal_axis_vectors: bool
    is_frozen: bool; is_wrapped: bool; owner: Any
    def copy(self) -> "Matrix"; def freeze(self) -> "Matrix"; def determinant(self) -> float
    def invert(self, fallback=None) -> None; def inverted(self, fallback=None) -> "Matrix"
    def invert_safe(self) -> None; def inverted_safe(self) -> "Matrix"
    def transpose(self) -> None; def transposed(self) -> "Matrix"
    def normalize(self) -> None; def normalized(self) -> "Matrix"
    def adjugate(self) -> None; def adjugated(self) -> "Matrix"; def zero(self) -> None; def identity(self) -> None
    def to_2x2(self) -> "Matrix"; def to_3x3(self) -> "Matrix"; def to_4x4(self) -> "Matrix"; def resize_4x4(self) -> None
    def to_euler(self, order: str = "XYZ", euler_compat: "Euler | None" = None) -> "Euler"
    def to_quaternion(self) -> "Quaternion"; def to_scale(self) -> Vector; def to_translation(self) -> Vector
    def decompose(self) -> tuple[Vector, "Quaternion", Vector]
    def lerp(self, other: "Matrix", factor: float) -> "Matrix"; def rotate(self, other) -> None
    # operators: @ (Matrix@Matrix, Matrix@Vector with implicit w=1 for 3D×4×4), * scalar, + -, ==,
    # [i] → wrapped row (Vector view), len, __array__, multi-line repr

class Quaternion:
    def __init__(self, seq: Iterable[float] = (1.0, 0.0, 0.0, 0.0), angle: float | None = None) -> None
    w: float; x: float; y: float; z: float; angle: float; axis: Vector; magnitude: float
    is_frozen: bool; is_wrapped: bool; owner: Any
    def copy(self) -> "Quaternion"; def freeze(self) -> "Quaternion"
    def conjugate(self) -> None; def conjugated(self) -> "Quaternion"
    def invert(self) -> None; def inverted(self) -> "Quaternion"; def negate(self) -> None
    def normalize(self) -> None; def normalized(self) -> "Quaternion"; def identity(self) -> None
    def cross(self, other) -> "Quaternion"; def dot(self, other) -> float
    def rotate(self, other) -> None; def rotation_difference(self, other) -> "Quaternion"
    def slerp(self, other, factor: float) -> "Quaternion"
    def to_axis_angle(self) -> tuple[Vector, float]
    def to_euler(self, order: str = "XYZ", euler_compat: "Euler | None" = None) -> "Euler"
    def to_matrix(self) -> Matrix; def to_exponential_map(self) -> Vector
    def to_swing_twist(self, axis: str) -> tuple["Quaternion", float]
    def make_compatible(self, other) -> None

class Euler:
    def __init__(self, angles: Iterable[float] = (0.0, 0.0, 0.0), order: str = "XYZ") -> None
    x: float; y: float; z: float; order: str; is_frozen: bool; is_wrapped: bool; owner: Any
    def copy(self) -> "Euler"; def freeze(self) -> "Euler"; def zero(self) -> None
    def make_compatible(self, other) -> None; def rotate(self, other) -> None
    def rotate_axis(self, axis: str, angle: float) -> None
    def to_matrix(self) -> Matrix; def to_quaternion(self) -> Quaternion

class Color:
    def __init__(self, rgb: Iterable[float] = (0.0, 0.0, 0.0)) -> None
    r: float; g: float; b: float; h: float; s: float; v: float; hsv: tuple[float, float, float]
    is_frozen: bool; is_wrapped: bool; owner: Any
    def copy(self) -> "Color"; def freeze(self) -> "Color"
    def from_scene_linear_to_srgb(self) -> "Color"; def from_srgb_to_scene_linear(self) -> "Color"
    # (other color space conversions: same signature, implemented on demand)

def axis_conversion(from_forward: str = "Y", from_up: str = "Z",
                    to_forward: str = "Y", to_up: str = "Z") -> Matrix      # 3×3

# quartz/math/scalar.py (base of bl_math)
def clamp(value: float, min: float = 0.0, max: float = 1.0) -> float
def lerp(from_value: float, to_value: float, factor: float) -> float
def smoothstep(from_value: float, to_value: float, value: float) -> float

# quartz/math/geometry.py (subset)
def intersect_line_line(v1, v2, v3, v4) -> tuple[Vector, Vector] | None
def intersect_ray_tri(v1, v2, v3, ray, orig, clip: bool = True) -> Vector | None
def intersect_line_plane(line_a, line_b, plane_co, plane_no, no_flip: bool = False) -> Vector | None
def intersect_point_line(pt, line_p1, line_p2) -> tuple[Vector, float]
def intersect_point_tri(pt, tri_p1, tri_p2, tri_p3) -> Vector | None
def intersect_line_sphere(line_a, line_b, sphere_co, sphere_radius, clip: bool = True) -> tuple[Vector | None, Vector | None]
def normal(*vectors) -> Vector
def area_tri(v1, v2, v3) -> float
def volume_tetrahedron(v1, v2, v3, v4) -> float
def barycentric_transform(point, tri_a1, tri_a2, tri_a3, tri_b1, tri_b2, tri_b3) -> Vector
def distance_point_to_plane(pt, plane_co, plane_no) -> float
def tessellate_polygon(veclist_list) -> list[tuple[int, int, int]]
def convex_hull_2d(points) -> list[int]
def box_fit_2d(points) -> float

# quartz/math/kdtree.py
class KDTree:
    def __init__(self, size: int) -> None
    def insert(self, co, index: int) -> None
    def balance(self) -> None
    def find(self, co, filter: Callable[[int], bool] | None = None) -> tuple[Vector | None, int | None, float | None]
    def find_n(self, co, n: int) -> list[tuple[Vector, int, float]]
    def find_range(self, co, radius: float) -> list[tuple[Vector, int, float]]

# quartz/math/bvhtree.py (scheduled after the sweep requests it)
class BVHTree:
    @classmethod
    def FromPolygons(cls, vertices, polygons, all_triangles: bool = False, epsilon: float = 0.0) -> "BVHTree": ...
    def ray_cast(self, origin, direction, distance: float = sys.float_info.max) -> tuple[Vector | None, Vector | None, int | None, float | None]
    def find_nearest(self, origin, distance: float = sys.float_info.max) -> tuple[Vector | None, Vector | None, int | None, float | None]
    def find_nearest_range(self, origin, distance: float) -> list[tuple]
    def overlap(self, other: "BVHTree") -> list[tuple[int, int]]
```

#### `quartz/props.py`

```python
class _PropertyDeferred:
    __slots__ = ("function", "keywords")
    def __init__(self, function: Callable[..., "_PropertyDeferred"], keywords: dict[str, Any]) -> None
    def __repr__(self) -> str

# Factories — kwargs identical to 5.2.2 (contract §4.1) + `meta`.
# In the lines below, "..." = the common BoolProperty kwargs (name, description, translation_context,
# options, override, tags, subtype, update, get, set, get_transform, set_transform, meta).
def BoolProperty(*, name: str = "", description: str = "", translation_context: str = "*",
                 default: bool = False, options: set[str] = {"ANIMATABLE"}, override: set[str] = set(),
                 tags: set[str] = set(), subtype: str = "NONE", update=None, get=None, set=None,
                 get_transform=None, set_transform=None, meta: dict | None = None) -> _PropertyDeferred
def BoolVectorProperty(*, ..., default=(False, False, False), size: int | tuple[int, ...] = 3, ...) -> _PropertyDeferred
def IntProperty(*, ..., default: int = 0, min: int = -2**31, max: int = 2**31 - 1,
                soft_min: int = -2**31, soft_max: int = 2**31 - 1, step: int = 1, ...) -> _PropertyDeferred
def IntVectorProperty(*, ..., default=(0, 0, 0), size=3, ...) -> _PropertyDeferred
def FloatProperty(*, ..., default: float = 0.0, min: float = -3.402823e38, max: float = 3.402823e38,
                  soft_min: float = -3.402823e38, soft_max: float = 3.402823e38, step: int = 3,
                  precision: int = 2, subtype: str = "NONE", unit: str = "NONE", ...) -> _PropertyDeferred
def FloatVectorProperty(*, ..., default=(0.0, 0.0, 0.0), size=3, ...) -> _PropertyDeferred
def StringProperty(*, ..., default: str = "", maxlen: int = 0, subtype: str = "NONE",
                   search=None, search_options: set[str] = {"SUGGESTION"}, ...) -> _PropertyDeferred
def EnumProperty(items, *, name: str = "", description: str = "", translation_context: str = "*",
                 default=None, options: set[str] = {"ANIMATABLE"}, override: set[str] = set(),
                 tags: set[str] = set(), update=None, get=None, set=None, get_transform=None,
                 set_transform=None, meta: dict | None = None) -> _PropertyDeferred
def PointerProperty(type=None, *, name: str = "", description: str = "", translation_context: str = "*",
                    options: set[str] = {"ANIMATABLE"}, override: set[str] = set(), tags: set[str] = set(),
                    poll=None, update=None, meta: dict | None = None) -> _PropertyDeferred
def CollectionProperty(type=None, *, name: str = "", description: str = "", translation_context: str = "*",
                       options: set[str] = set(), override: set[str] = set(), tags: set[str] = set(),
                       meta: dict | None = None) -> _PropertyDeferred
def RemoveProperty(cls: type, *, attr: str) -> None

class EnumItem(NamedTuple):
    identifier: str; name: str; description: str; icon: str | int; value: int

class PropertyDef:                       # data descriptor
    kind: ClassVar[str]                  # BOOLEAN | INT | FLOAT | STRING | ENUM | POINTER | COLLECTION
    identifier: str; name: str; description: str; translation_context: str
    options: frozenset[str]; override: frozenset[str]; tags: frozenset[str]; subtype: str
    update: Callable | None; get: Callable | None; set: Callable | None
    meta: Mapping[str, Any]; owner: type | None; deferred: _PropertyDeferred; is_readonly: bool
    def __get__(self, inst: Any, owner_cls: type | None = None) -> Any
    def __set__(self, inst: Any, value: Any) -> None
    def default_value(self) -> Any
    def coerce(self, value: Any, inst: Any = None) -> Any      # TypeError/ValueError/clamp/truncation
    def describe(self) -> dict[str, Any]                       # format of blender_api_dump.json
class BoolDef(PropertyDef); class IntDef(PropertyDef); class FloatDef(PropertyDef)
class StringDef(PropertyDef); class EnumDef(PropertyDef); class PointerDef(PropertyDef); class CollectionDef(PropertyDef)
    # Bool/Int/FloatDef have `size: tuple[int, ...]` (empty = scalar) and `array_length: int`
    # EnumDef: def items_for(self, inst, context) -> list[EnumItem]; is_flag: bool
    # PointerDef/CollectionDef: fixed_type: type; counts_user: bool (meta)

class PropArray:                          # bpy_prop_array for arrays without a math type
    def __len__(self) -> int; def __getitem__(self, i): ...; def __setitem__(self, i, v) -> None
    def __iter__(self): ...; def __eq__(self, other) -> bool; def __array__(self, dtype=None): ...
    def foreach_get(self, seq) -> None; def foreach_set(self, seq) -> None

class PropCollection:                     # value of CollectionProperty (bpy_prop_collection)
    def add(self) -> Any; def remove(self, index: int) -> None; def clear(self) -> None
    def move(self, from_index: int, to_index: int) -> None; def find(self, key: str) -> int
    def get(self, key: str, default=None) -> Any
    def keys(self) -> list[str]; def values(self) -> list[Any]; def items(self) -> list[tuple[str, Any]]
    def __len__(self) -> int; def __iter__(self): ...; def __getitem__(self, key: int | str | slice): ...
    def __contains__(self, key: str) -> bool
    def foreach_get(self, attr: str, seq) -> None; def foreach_set(self, attr: str, seq) -> None

def collect_annotations(cls: type) -> dict[str, _PropertyDeferred]   # MRO, 3.14 lazy, strings via eval
def install_properties(cls: type, *, is_valid_type: Callable[[type], bool] | None = None) -> list[PropertyDef]
def uninstall_properties(cls: type) -> None
def define_property(cls: type, attr: str, deferred: _PropertyDeferred) -> PropertyDef
def remove_property(cls: type, attr: str) -> None
def describe(cls: type) -> tuple[PropertyDef, ...]                   # seam of the C4D description
def is_property_set(inst: Any, attr: str) -> bool
def property_unset(inst: Any, attr: str) -> None
def normalize_enum_items(items, inst: Any = None, context: Any = None) -> list[EnumItem]
```

#### `quartz/geometry/`

```python
# attributes.py
Domain = Literal["POINT", "EDGE", "FACE", "CORNER"]
DataType = Literal["FLOAT", "INT", "INT8", "BOOLEAN", "FLOAT_VECTOR", "FLOAT2", "INT32_2D",
                   "FLOAT_COLOR", "BYTE_COLOR", "QUATERNION", "FLOAT4X4", "STRING"]
DTYPES: Mapping[DataType, tuple[np.dtype, tuple[int, ...]]]
@dataclass
class AttributeArray:
    name: str; domain: Domain; data_type: DataType; data: np.ndarray
    @property
    def is_internal(self) -> bool: ...                   # name starts with "."
class AttributeStore:
    def __init__(self, domain_size: Callable[[Domain], int]) -> None
    def new(self, name: str, data_type: DataType, domain: Domain, *, fill: Any = None) -> AttributeArray
    def get(self, name: str) -> AttributeArray | None
    def remove(self, name: str) -> None
    def names(self, domain: Domain | None = None, *, include_internal: bool = True) -> list[str]
    def resize(self, domain: Domain, size: int) -> None
    def copy(self) -> "AttributeStore"
    def __contains__(self, name: str) -> bool; def __iter__(self): ...; def __len__(self) -> int

# mesh.py
class MeshGeometry:
    attributes: AttributeStore
    face_offsets: np.ndarray                              # (F+1,) int32
    @classmethod
    def empty(cls) -> "MeshGeometry": ...
    @classmethod
    def from_pydata(cls, vertices, edges, faces) -> "MeshGeometry": ...
    positions: np.ndarray; edges: np.ndarray; corner_verts: np.ndarray; corner_edges: np.ndarray  # views
    num_verts: int; num_edges: int; num_faces: int; num_corners: int
    def domain_size(self, domain: Domain) -> int
    def face_sizes(self) -> np.ndarray
    def corner_to_face(self) -> np.ndarray
    def add_verts(self, count: int) -> None; def add_edges(self, count: int) -> None
    def add_faces(self, sizes: Sequence[int]) -> None
    def copy(self) -> "MeshGeometry"
    def clear(self) -> None
    def validate(self) -> list[str]                       # problems found (empty = ok)
def calc_edges(geo: MeshGeometry, *, keep_existing: bool = True) -> None
def edge_keys(geo: MeshGeometry) -> np.ndarray            # (E,2) sorted per row
def transform(geo: MeshGeometry, matrix: np.ndarray) -> None
def flip_faces(geo: MeshGeometry, mask: np.ndarray | None = None) -> None
def bounds(geo: MeshGeometry) -> tuple[np.ndarray, np.ndarray]
def join(geos: Sequence[MeshGeometry], matrices: Sequence[np.ndarray] | None = None) -> MeshGeometry

# normals.py
def face_normals(geo: MeshGeometry) -> np.ndarray         # (F,3) float32
def vertex_normals(geo: MeshGeometry) -> np.ndarray       # (V,3)
def corner_normals(geo: MeshGeometry) -> np.ndarray       # (L,3), respects sharp_face/sharp_edge
def face_centers(geo: MeshGeometry) -> np.ndarray; def face_areas(geo: MeshGeometry) -> np.ndarray

# triangulate.py
def triangulate(geo: MeshGeometry) -> tuple[np.ndarray, np.ndarray]   # (T,3) corners, (T,) source face

# primitives.py — same properties/defaults as the mesh.primitive_*_add operators (dump)
def plane(size: float = 2.0, *, calc_uvs: bool = True) -> MeshGeometry
def grid(x_subdivisions: int = 10, y_subdivisions: int = 10, size: float = 2.0, *, calc_uvs: bool = True) -> MeshGeometry
def cube(size: float = 2.0, *, calc_uvs: bool = True) -> MeshGeometry
def circle(vertices: int = 32, radius: float = 1.0, fill_type: str = "NOTHING", *, calc_uvs: bool = True) -> MeshGeometry
def uv_sphere(segments: int = 32, ring_count: int = 16, radius: float = 1.0, *, calc_uvs: bool = True) -> MeshGeometry
def ico_sphere(subdivisions: int = 2, radius: float = 1.0, *, calc_uvs: bool = True) -> MeshGeometry
def cylinder(vertices: int = 32, radius: float = 1.0, depth: float = 2.0, end_fill_type: str = "NGON", *, calc_uvs: bool = True) -> MeshGeometry
def cone(vertices: int = 32, radius1: float = 1.0, radius2: float = 0.0, depth: float = 2.0, end_fill_type: str = "NGON", *, calc_uvs: bool = True) -> MeshGeometry
def torus(major_segments: int = 48, minor_segments: int = 12, major_radius: float = 1.0, minor_radius: float = 0.25, *, calc_uvs: bool = True) -> MeshGeometry

# editmesh.py (core of bmesh; scheduled after the first sweep)
class EditMesh:
    verts: "EMSeq[EMVert]"; edges: "EMSeq[EMEdge]"; faces: "EMSeq[EMFace]"; select_mode: set[str]; is_valid: bool
    @classmethod
    def from_geometry(cls, geo: MeshGeometry) -> "EditMesh": ...
    def to_geometry(self) -> MeshGeometry
    def copy(self) -> "EditMesh"; def clear(self) -> None; def free(self) -> None
    def normal_update(self) -> None
    def calc_loop_triangles(self) -> list[tuple["EMLoop", "EMLoop", "EMLoop"]]
    def select_flush(self, select: bool) -> None; def select_flush_mode(self) -> None
    def transform(self, matrix, *, filter: set[str] | None = None) -> None
class EMVert:  co; normal; index: int; select: bool; hide: bool; tag: bool; link_edges; link_faces; link_loops; is_valid: bool  # + select_set(), is_manifold, is_boundary, is_wire
class EMEdge:  verts; link_faces; link_loops; index: int; select: bool; hide: bool; seam: bool; smooth: bool  # + other_vert(v), calc_length()
class EMFace:  verts; edges; loops; normal; material_index: int; smooth: bool; index: int; select: bool; hide: bool  # + calc_area(), calc_center_median(), normal_update(), normal_flip()
class EMLoop:  vert; edge; face; link_loop_next; link_loop_prev; link_loop_radial_next; index: int  # + calc_angle()
class EMSeq(Generic[T]):
    layers: "EMLayerAccess"
    def new(self, *args) -> T; def remove(self, elem: T) -> None; def ensure_lookup_table(self) -> None
    def index_update(self) -> None; def sort(self, key=None, reverse: bool = False) -> None
    def get(self, verts) -> T | None; def __len__(self) -> int; def __iter__(self): ...; def __getitem__(self, i: int) -> T
# editmesh_ops.py
def triangulate(em: EditMesh, *, faces, quad_method: str = "BEAUTY", ngon_method: str = "BEAUTY") -> dict
def remove_doubles(em: EditMesh, *, verts, dist: float = 0.0001) -> None
def recalc_face_normals(em: EditMesh, *, faces) -> None
def create_cube(em: EditMesh, *, size: float = 1.0, matrix=None, calc_uvs: bool = False) -> dict
def delete(em: EditMesh, *, geom, context: str = "VERTS") -> None
def transform(em: EditMesh, *, matrix, verts, space=None) -> None
def translate(em: EditMesh, *, vec, verts, space=None) -> None
```

**Layer 1 exit criterion**: unit tests green (including the math `g13` compared with the
Blender golden), `test_layering` green, quad 4/4/4/1 and cube 8/12/6/24 reproduced, props
reproducing the `property_semantics` probes with a fake owner.

### 10.2 Layer 2 — data model, registry and operators

Internal order: (a) `types/struct.py` + `types/id.py` + `database.py` (owner of the interface, first);
then in parallel (b) `object/scene/collection`, (c) `types/mesh.py` on top of `geometry`, (d)
`registry` + `types/operator.py` + `ops` + `operators/*`, (e) `contexts` + `session` + `app` + `undo` +
`depsgraph` + `ui`.

#### `quartz/types/struct.py`

```python
REPR_ROOT: str = "quartz"                     # compat switches to "bpy"
class StructMeta(type):
    def __setattr__(cls, name: str, value: Any) -> None       # _PropertyDeferred → props.define_property
    def __delattr__(cls, name: str) -> None                    # PropertyDef → props.remove_property
    @property
    def is_registered(cls) -> bool: ...                        # "bl_rna" in cls.__dict__
def native_type(cls: type) -> type                             # decorator: install_properties + native bl_rna

class Struct(metaclass=StructMeta):                            # bpy_struct
    _q_registrable: ClassVar[bool] = False
    bl_rna: ClassVar["RNAStruct"]
    def __init__(self, *args, **kwargs) -> None
    rna_type: "RNAStruct"; id_data: "ID | None"
    def path_from_id(self, property: str = "") -> str
    def path_resolve(self, path: str, coerce: bool = True) -> Any
    def is_property_set(self, property: str, ghost: bool = True) -> bool
    def property_unset(self, property: str) -> None
    def is_property_readonly(self, property: str) -> bool
    def is_property_hidden(self, property: str) -> bool
    def get(self, key: str, default: Any = None) -> Any
    def keys(self) -> list[str]; def values(self) -> list[Any]; def items(self) -> list[tuple[str, Any]]
    def pop(self, key: str, default: Any = ...) -> Any
    def __getitem__(self, key: str) -> Any; def __setitem__(self, key: str, value: Any) -> None
    def __delitem__(self, key: str) -> None; def __contains__(self, key: str) -> bool
    def id_properties_ensure(self) -> "IDPropertyGroup"; def id_properties_clear(self) -> None
    def id_properties_ui(self, key: str) -> "IDPropertyUIManager"
    def as_pointer(self) -> int
    def keyframe_insert(self, data_path: str, index: int = -1, frame: float | None = None, group: str = "",
                        options: set[str] = set(), keytype: str = "KEYFRAME") -> bool   # NotImplementedError in this milestone
    def keyframe_delete(self, data_path: str, index: int = -1, frame: float | None = None, group: str = "") -> bool
    def driver_add(self, path: str, index: int = -1) -> Any                             # NotImplementedError in this milestone
    def driver_remove(self, path: str, index: int = -1) -> bool
    @classmethod
    def bl_rna_get_subclass(cls, id: str, default: Any = None) -> "RNAStruct | Any": ...
    @classmethod
    def bl_rna_get_subclass_py(cls, id: str, default: Any = None) -> type | Any: ...
    def type_recast(self) -> "Struct"
    def rna_ancestors(self) -> list["Struct"]
    # internal
    def _q_refs(self) -> Iterator["IDRef"]
    def _q_snapshot(self) -> dict; def _q_restore(self, state: dict) -> None
    def _q_on_change(self, pdef: "PropertyDef") -> None

class PropertyGroup(Struct):                                   # registrable; implicit `name`
    _q_registrable = True
class IDRef(NamedTuple):
    target: "ID"; counts_user: bool; clear: Callable[[], None]; remap: Callable[["ID"], None]
class RNAStruct:
    identifier: str; name: str; description: str; base: "RNAStruct | None"; translation_context: str
    properties: "RNAPropertyCollection"; functions: "RNAFunctionCollection"
class RNAProperty:
    identifier: str; name: str; description: str; type: str; subtype: str; unit: str
    default: Any; default_array: tuple; array_length: int; array_dimensions: tuple[int, ...]
    hard_min: float; hard_max: float; soft_min: float; soft_max: float; step: float; precision: int
    is_readonly: bool; is_animatable: bool; is_hidden: bool; is_skip_save: bool; is_enum_flag: bool
    is_never_none: bool; length_max: int; enum_items: "RNAEnumItems"; fixed_type: RNAStruct | None
class IDPropertyGroup:   # dict-like: keys/values/items/get/pop/update/to_dict/clear
class IDPropertyArray:   # typed sequence: to_list(), typecode
class IDPropertyUIManager:  def update(self, **kw) -> None; def as_dict(self) -> dict; def clear(self) -> None; def update_from(self, other) -> None
```

#### `quartz/types/id.py`

```python
class ID(Struct):
    q_id_type: ClassVar[str]; q_default_name: ClassVar[str]; q_schema_version: ClassVar[int] = 0
    name: str; name_full: str; id_type: str; session_uid: int; users: int
    use_fake_user: bool; use_extra_user: bool; is_evaluated: bool; original: "ID"
    library: Any; is_embedded_data: bool; is_editable: bool; is_missing: bool; is_runtime_data: bool
    tag: bool; asset_data: Any; preview: Any; animation_data: Any
    def copy(self) -> "ID"
    def rename(self, name: str, *, mode: str = "NEVER") -> str   # returns UNCHANGED|RENAMED_NO_COLLISION|...
    def evaluated_get(self, depsgraph: "Depsgraph") -> "ID"
    def user_clear(self) -> None; def user_remap(self, new_id: "ID") -> None; def user_of_id(self, id: "ID") -> int
    def make_local(self, clear_proxy: bool = True) -> "ID"
    def animation_data_create(self) -> Any; def animation_data_clear(self) -> None
    def update_tag(self, *, refresh: set[str] = set()) -> None
    def asset_mark(self) -> None; def asset_clear(self) -> None; def asset_generate_preview(self) -> None
    def preview_ensure(self) -> Any
    def bl_system_properties_get(self, *, do_create: bool = False) -> IDPropertyGroup | None
    def tag_dirty(self, channel: str = "DATA") -> None          # Quartz (C4D seam)
def removed_class_for(cls: type[ID]) -> type                  # generates/gets Removed<Type>
```

#### `quartz/database.py`

```python
class IDCollection(Generic[T]):
    id_type: type[T]
    def new(self, name: str) -> T                              # subclasses override with the type's signature
    def remove(self, id: T, *, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
    def get(self, key: str, default: Any = None) -> T | Any
    def find(self, key: str) -> int
    def keys(self) -> list[str]; def values(self) -> list[T]; def items(self) -> list[tuple[str, T]]
    def tag(self, value: bool) -> None
    def foreach_get(self, attr: str, seq) -> None; def foreach_set(self, attr: str, seq) -> None
    def __getitem__(self, key: int | str | slice) -> T; def __contains__(self, key: str | T) -> bool
    def __iter__(self) -> Iterator[T]; def __len__(self) -> int
class BlendDataObjects(IDCollection[Object]):    def new(self, name: str, object_data: "ID | None") -> Object
class BlendDataLights(IDCollection[Light]):      def new(self, name: str, type: str) -> Light
class BlendDataCurves(IDCollection[Curve]):      def new(self, name: str, type: str) -> Curve
class BlendDataImages(IDCollection[Image]):
    def new(self, name: str, width: int, height: int, alpha: bool = False, float_buffer: bool = False,
            stereo3d: bool = False, is_data: bool = False, tiled: bool = False) -> Image
    def load(self, filepath: str, check_existing: bool = False) -> Image
class BlendDataTexts(IDCollection[Text]):        def load(self, filepath: str, internal: bool = False) -> Text
class BlendDataScenes(IDCollection[Scene]):      def remove(self, scene: Scene, *, do_unlink: bool = True) -> None
class BlendData:
    objects: BlendDataObjects; meshes: IDCollection[Mesh]; materials: IDCollection[Material]
    cameras: IDCollection[Camera]; lights: BlendDataLights; collections: IDCollection[Collection]
    scenes: BlendDataScenes; worlds: IDCollection[World]; images: BlendDataImages; texts: BlendDataTexts
    actions: IDCollection; armatures: IDCollection; curves: BlendDataCurves; node_groups: IDCollection
    libraries: IDCollection; window_managers: IDCollection; screens: IDCollection; workspaces: IDCollection
    filepath: str; is_dirty: bool; is_saved: bool; version: tuple[int, int, int]
    def all_ids(self) -> Iterator[ID]
    def users_of(self, id: ID) -> int                          # base of ID.users
    def user_map(self, subset: Iterable[ID] | None = None, key_types: set[str] | None = None,
                 value_types: set[str] | None = None) -> dict[ID, set[ID]]
    def orphans_purge(self, do_local_ids: bool = True, do_linked_ids: bool = True, do_recursive: bool = False) -> int
    def batch_remove(self, ids: Iterable[ID]) -> None
    def clear(self) -> None                                    # used by session.reset
class RestrictedData:                                          # bpy.data during import/register
    def __getattr__(self, name: str) -> NoReturn
```

#### `quartz/types/object.py`, `scene.py`, `collection.py`

```python
OBJECT_DATA_TYPES: dict[type, str]                             # seam: Mesh→"MESH", Camera→"CAMERA", ...
def register_object_data_type(cls: type, object_type: str) -> None

class Object(ID):
    data: "ID | None"; type: str; mode: str
    location: Vector; rotation_mode: str; rotation_euler: Euler; rotation_quaternion: Quaternion
    rotation_axis_angle: PropArray; scale: Vector
    delta_location: Vector; delta_rotation_euler: Euler; delta_rotation_quaternion: Quaternion; delta_scale: Vector
    parent: "Object | None"; parent_type: str; matrix_parent_inverse: Matrix
    matrix_basis: Matrix; matrix_local: Matrix; matrix_world: Matrix
    dimensions: Vector; bound_box: PropArray
    children: tuple["Object", ...]; children_recursive: list["Object"]
    users_collection: tuple["Collection", ...]; users_scene: tuple["Scene", ...]
    hide_viewport: bool; hide_render: bool; hide_select: bool
    material_slots: PropCollection; active_material: "Material | None"; active_material_index: int
    modifiers: "ObjectModifiers"; constraints: "ObjectConstraints"; vertex_groups: "VertexGroups"
    color: PropArray; pass_index: int; display_type: str; show_name: bool; show_in_front: bool
    empty_display_type: str; empty_display_size: float; instance_type: str; instance_collection: "Collection | None"
    def select_get(self, view_layer: "ViewLayer | None" = None) -> bool
    def select_set(self, state: bool, view_layer: "ViewLayer | None" = None) -> None
    def hide_get(self, view_layer: "ViewLayer | None" = None) -> bool
    def hide_set(self, state: bool, view_layer: "ViewLayer | None" = None) -> None
    def visible_get(self, view_layer: "ViewLayer | None" = None, viewport: Any = None) -> bool
    def to_mesh(self, preserve_all_data_layers: bool = False, depsgraph: Any = None) -> "Mesh"
    def to_mesh_clear(self) -> None
    def convert_space(self, pose_bone: Any = None, matrix: Matrix | None = None,
                      from_space: str = "WORLD", to_space: str = "WORLD") -> Matrix
    def update_from_editmode(self) -> bool
    def ray_cast(self, origin, direction, distance: float = 1.70141e38, depsgraph: Any = None) -> tuple   # later (BVH)
class ObjectModifiers(PropCollection):   def new(self, name: str, type: str) -> "Modifier"; def remove(self, modifier) -> None; def clear(self) -> None
class Modifier(Struct):                  name: str; type: str; show_viewport: bool; show_render: bool   # no evaluation
class VertexGroups(PropCollection):      def new(self, name: str = "Group") -> "VertexGroup"; def remove(self, group) -> None; active_index: int
class VertexGroup(Struct):               name: str; index: int; def add(self, index: Sequence[int], weight: float, type: str) -> None; def remove(self, index: Sequence[int]) -> None; def weight(self, index: int) -> float

class Collection(ID):
    objects: "CollectionObjects"; children: "CollectionChildren"; all_objects: tuple[Object, ...]
    hide_viewport: bool; hide_render: bool; hide_select: bool; color_tag: str; instance_offset: Vector
    children_recursive: list["Collection"]
class CollectionObjects(PropCollection):  def link(self, object: Object) -> None; def unlink(self, object: Object) -> None
class CollectionChildren(PropCollection): def link(self, child: Collection) -> None; def unlink(self, child: Collection) -> None

class Scene(ID):
    collection: Collection; view_layers: "ViewLayers"; world: "World | None"; camera: Object | None
    frame_start: int; frame_end: int; frame_current: int; frame_step: int; frame_float: float
    render: "RenderSettings"; unit_settings: "UnitSettings"; tool_settings: "ToolSettings"; cursor: "View3DCursor"
    objects: tuple[Object, ...]
    def frame_set(self, frame: int, subframe: float = 0.0) -> None
class ViewLayers(PropCollection):  def new(self, name: str) -> "ViewLayer"; def remove(self, layer: "ViewLayer") -> None
class ViewLayer(Struct):
    name: str; objects: "LayerObjects"; layer_collection: "LayerCollection"
    active_layer_collection: "LayerCollection"; depsgraph: "Depsgraph"; use: bool
    def update(self) -> None
class LayerObjects(PropCollection):  active: Object | None; selected: tuple[Object, ...]
class LayerCollection(Struct):       name: str; collection: Collection; children: PropCollection; exclude: bool; hide_viewport: bool; is_visible: bool
class RenderSettings(Struct):        engine: str; resolution_x: int; resolution_y: int; resolution_percentage: int; fps: int; fps_base: float; filepath: str
class UnitSettings(Struct):          system: str; scale_length: float; length_unit: str; mass_unit: str; time_unit: str; system_rotation: str
class View3DCursor(Struct):          location: Vector; rotation_mode: str; rotation_euler: Euler; rotation_quaternion: Quaternion; matrix: Matrix
class ToolSettings(Struct):          mesh_select_mode: PropArray   # the rest on demand
```

#### `quartz/types/mesh.py`, `material.py`, `camera.py`, `light.py`, `world.py`, `image.py`, `text.py`

```python
class Mesh(ID):
    vertices: "MeshVertices"; edges: "MeshEdges"; loops: "MeshLoops"; polygons: "MeshPolygons"
    loop_triangles: PropCollection; loop_triangle_polygons: PropArray
    attributes: "AttributeGroup"; color_attributes: "AttributeGroup"; uv_layers: "UVLoopLayers"
    materials: "IDMaterials"; vertex_normals: PropCollection; polygon_normals: PropCollection
    corner_normals: PropCollection; normals_domain: str; edge_keys: list[tuple[int, int]]
    is_editmode: bool; shape_keys: Any; total_vert_sel: int; total_edge_sel: int; total_face_sel: int
    def from_pydata(self, vertices, edges, faces, shade_flat: bool = True) -> None
    def update(self, calc_edges: bool = False, calc_edges_loose: bool = False) -> None
    def validate(self, verbose: bool = False, clean_customdata: bool = True) -> bool
    def clear_geometry(self) -> None
    def transform(self, matrix, shape_keys: bool = False) -> None
    def flip_normals(self) -> None; def shade_flat(self) -> None; def shade_smooth(self) -> None
    def set_sharp_from_angle(self, angle: float = 0.523599) -> None
    def calc_loop_triangles(self) -> None; def split_faces(self) -> None; def count_selected_items(self) -> tuple[int, int, int]
    _q_geo: MeshGeometry; _q_edit: "EditMesh | None"
class MeshVertices(PropCollection):  def add(self, count: int) -> None     # elements: MeshVertex(co, normal, select, hide, index, groups)
class MeshEdges(PropCollection):     def add(self, count: int) -> None     # MeshEdge(vertices, key, select, hide, use_seam, index)
class MeshLoops(PropCollection):     def add(self, count: int) -> None     # MeshLoop(vertex_index, edge_index, normal, index)
class MeshPolygons(PropCollection):  def add(self, count: int) -> None     # MeshPolygon(vertices, loop_start, loop_total, material_index, use_smooth, normal, center, area, edge_keys, select, hide, index)
class AttributeGroup(PropCollection):
    active: "Attribute | None"; active_color: "Attribute | None"; default_color_name: str
    def new(self, name: str, type: str, domain: str) -> "Attribute"; def remove(self, attribute: "Attribute") -> None
class Attribute(Struct):  name: str; data_type: str; domain: str; is_internal: bool; is_required: bool; data: PropCollection
class UVLoopLayers(PropCollection):  active: "MeshUVLoopLayer | None"; def new(self, name: str = "UVMap", do_init: bool = True) -> "MeshUVLoopLayer"; def remove(self, layer) -> None
class MeshUVLoopLayer(Struct):  name: str; active: bool; active_render: bool; data: PropCollection; uv: PropCollection
class IDMaterials(PropCollection):  def append(self, material: "Material | None") -> None; def pop(self, index: int = -1) -> "Material | None"; def clear(self) -> None

class Material(ID):   diffuse_color: PropArray; metallic: float; roughness: float; specular_intensity: float; blend_method: str; use_backface_culling: bool; pass_index: int; use_nodes: bool; node_tree: Any; is_grease_pencil: bool
class MaterialSlot(Struct):  material: Material | None; link: str; slot_index: int; name: str
class Camera(ID):     type: str; lens: float; lens_unit: str; sensor_width: float; sensor_height: float; sensor_fit: str; clip_start: float; clip_end: float; ortho_scale: float; shift_x: float; shift_y: float; angle: float; angle_x: float; angle_y: float; dof: "CameraDOFSettings"
                      def view_frame(self, scene: "Scene | None" = None) -> tuple[Vector, Vector, Vector, Vector]
class Light(ID):      type: str; color: Color; use_shadow: bool; specular_factor: float; diffuse_factor: float; use_nodes: bool; node_tree: Any
class PointLight(Light): energy: float; shadow_soft_size: float
class SpotLight(Light):  energy: float; shadow_soft_size: float; spot_size: float; spot_blend: float; show_cone: bool
class SunLight(Light):   energy: float; angle: float
class AreaLight(Light):  energy: float; shape: str; size: float; size_y: float
class World(ID):      color: Color; use_nodes: bool; node_tree: Any
class Image(ID):      size: tuple[int, int]; filepath: str; filepath_raw: str; source: str; generated_color: PropArray; alpha_mode: str; pixels: PropArray; is_float: bool; channels: int
                      def scale(self, width: int, height: int) -> None; def reload(self) -> None
class Text(ID):       lines: PropCollection; filepath: str; is_in_memory: bool; is_dirty: bool
                      def as_string(self) -> str; def from_string(self, string: str) -> None; def write(self, text: str) -> None; def clear(self) -> None
```

#### `quartz/types/operator.py`, `types/ui.py`, `ui.py`

```python
class Operator(Struct):
    _q_registrable = True
    bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_description: ClassVar[str] = ""
    bl_options: ClassVar[set[str]] = set(); bl_translation_context: ClassVar[str] = "Operator"
    bl_undo_group: ClassVar[str] = ""; bl_property: ClassVar[str] = ""; bl_cursor_pending: ClassVar[str] = "DEFAULT"
    layout: "UILayout | None"; properties: "OperatorProperties"; options: "OperatorOptions"
    name: str; has_reports: bool; macros: PropCollection
    def __init__(self, *args, **kwargs) -> None
    @classmethod
    def poll_message_set(cls, message: str, *args) -> None: ...
    def report(self, type: set[str], message: str) -> None
    def as_keywords(self, *, ignore: Iterable[str] = ()) -> dict[str, Any]
    # user-defined (optional): poll(cls, context), execute, invoke(context, event), modal, cancel, check, draw, description(cls, context, properties)
    _q_reports: list[tuple[set[str], str]]
class OperatorProperties(Struct):  pass        # one subclass per operator, created at registration, shares _p
class OperatorOptions(Struct):     is_invoke: bool; is_repeat: bool; is_repeat_last: bool; use_cancel_on_exit: bool
class Event(Struct):               type: str; value: str; mouse_x: int; mouse_y: int; mouse_region_x: int; mouse_region_y: int; mouse_prev_x: int; mouse_prev_y: int; shift: bool; ctrl: bool; alt: bool; oskey: bool; hyper: bool; is_repeat: bool; unicode: str; ascii: str; pressure: float; tilt: tuple[float, float]; xr: Any

class _ExtensibleUI:               # mixin of Panel/Menu/Header/UIList
    @classmethod
    def append(cls, draw_func: Callable) -> None: ...
    @classmethod
    def prepend(cls, draw_func: Callable) -> None: ...
    @classmethod
    def remove(cls, draw_func: Callable) -> None: ...
    @classmethod
    def is_extended(cls) -> bool: ...
class Panel(Struct, _ExtensibleUI):   _q_registrable = True; bl_label: ClassVar[str]; bl_space_type: ClassVar[str]; bl_region_type: ClassVar[str]; bl_category: ClassVar[str] = ""; bl_context: ClassVar[str] = ""; bl_parent_id: ClassVar[str] = ""; bl_options: ClassVar[set[str]] = set(); bl_order: ClassVar[int] = 0; layout: "UILayout"; is_popover: bool
class Menu(Struct, _ExtensibleUI):    _q_registrable = True; bl_label: ClassVar[str]; bl_idname: ClassVar[str]; bl_options: ClassVar[set[str]] = set(); layout: "UILayout"
                                      @classmethod
                                      def draw_preset(cls, context) -> None: ...   # stub
class Header(Struct, _ExtensibleUI):  _q_registrable = True; bl_space_type: ClassVar[str]; bl_region_type: ClassVar[str] = "HEADER"; layout: "UILayout"
class UIList(Struct, _ExtensibleUI):  _q_registrable = True; layout_type: str; filter_name: str; use_filter_invert: bool; use_filter_sort_alpha: bool
                                      bitflag_filter_item: ClassVar[int] = 1 << 30

# quartz/ui.py
class UILayout:
    active: bool; enabled: bool; alert: bool; alignment: str; scale_x: float; scale_y: float
    use_property_split: bool; use_property_decorate: bool; operator_context: str; emboss: str; ui_units_x: float; ui_units_y: float
    calls: list["LayoutCall"]; warnings: list[str]
    def row(self, *, align: bool = False, heading: str = "", heading_ctxt: str = "", translate: bool = True) -> "UILayout"
    def column(self, *, align: bool = False, heading: str = "", heading_ctxt: str = "", translate: bool = True) -> "UILayout"
    def box(self) -> "UILayout"; def split(self, *, factor: float = 0.0, align: bool = False) -> "UILayout"
    def grid_flow(self, *, row_major: bool = False, columns: int = 0, even_columns: bool = False, even_rows: bool = False, align: bool = False) -> "UILayout"
    def column_flow(self, *, columns: int = 0, align: bool = False) -> "UILayout"
    def panel(self, idname: str, *, default_closed: bool = False) -> tuple["UILayout", "UILayout | None"]
    def prop(self, data: Any, property: str, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
             placeholder: str = "", expand: bool = False, slider: bool = False, toggle: int = -1, icon_only: bool = False,
             event: bool = False, full_event: bool = False, emboss: bool = True, index: int = -1, icon_value: int = 0,
             invert_checkbox: bool = False) -> None
    def operator(self, operator: str, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
                 emboss: bool = True, depress: bool = False, icon_value: int = 0, search_weight: float = 0.0) -> "OperatorProperties"
    def label(self, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE", icon_value: int = 0) -> None
    def separator(self, *, factor: float = 1.0, type: str = "AUTO") -> None; def separator_spacer(self) -> None
    def menu(self, menu: str, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE", icon_value: int = 0) -> None
    def template_list(self, listtype_name: str, list_id: str, dataptr: Any, propname: str, active_dataptr: Any, active_propname: str, **kw) -> None
    def prop_search(self, data: Any, property: str, search_data: Any, search_property: str, **kw) -> None
    def context_pointer_set(self, name: str, data: Any) -> None
    def __getattr__(self, name: str) -> Callable[..., Any]       # template_* and similar: recorded (lenient)
    def to_tree(self) -> dict
def draw_ui(cls: type, context: Any = None) -> UILayout
```

#### `quartz/types/wm.py`, `types/prefs.py`, `types/stubs.py`

```python
class WindowManager(ID):
    windows: PropCollection; keyconfigs: "KeyConfigurations"; clipboard: str; operators: PropCollection
    def modal_handler_add(self, operator: Operator) -> bool
    def fileselect_add(self, operator: Operator) -> None
    def invoke_props_dialog(self, operator: Operator, *, width: int = 300, title: str = "", confirm_text: str = "", cancel_default: bool = False, text_ctxt: str = "", translate: bool = True) -> set[str]
    def invoke_props_popup(self, operator: Operator, event: Event) -> set[str]
    def invoke_confirm(self, operator: Operator, event: Event, *, title: str = "", message: str = "", confirm_text: str = "", icon: str = "NONE", text_ctxt: str = "", translate: bool = True) -> set[str]
    def invoke_popup(self, operator: Operator, *, width: int = 300) -> set[str]
    def popup_menu(self, draw_func: Callable, *, title: str = "", icon: str = "NONE") -> None
    def progress_begin(self, min: float, max: float) -> None; def progress_update(self, value: float) -> None; def progress_end(self) -> None
    def event_timer_add(self, time_step: float, *, window: Any = None) -> Any; def event_timer_remove(self, timer: Any) -> None
class Window(Struct):  scene: Scene; view_layer: ViewLayer; screen: "Screen"; workspace: "WorkSpace"
class Screen(ID):      areas: PropCollection          # empty in headless (area/space_data = None)
class WorkSpace(ID):   object_mode: str
class KeyConfigurations(PropCollection):  addon: "KeyConfig"; user: "KeyConfig"; default: "KeyConfig"; active: "KeyConfig"
class KeyConfig(Struct):  name: str; keymaps: "KeyMaps"
class KeyMaps(PropCollection):  def new(self, name: str, *, space_type: str = "EMPTY", region_type: str = "WINDOW", modal: bool = False, tool: bool = False) -> "KeyMap"; def find(self, name: str, *, space_type: str = "EMPTY", region_type: str = "WINDOW") -> "KeyMap | None"
class KeyMap(Struct):  name: str; space_type: str; region_type: str; keymap_items: "KeyMapItems"
class KeyMapItems(PropCollection):  def new(self, idname: str, type: str, value: str, *, any: bool = False, shift: int = 0, ctrl: int = 0, alt: int = 0, oskey: int = 0, hyper: int = 0, key_modifier: str = "NONE", direction: str = "ANY", repeat: bool = False, head: bool = False) -> "KeyMapItem"; def remove(self, item: "KeyMapItem") -> None
class KeyMapItem(Struct):  idname: str; type: str; value: str; active: bool; properties: OperatorProperties | None

class Preferences(Struct):  addons: "Addons"; view: Struct; edit: Struct; system: Struct; inputs: Struct; filepaths: Struct; experimental: Struct; is_dirty: bool
class Addons(PropCollection):  def new(self) -> "Addon"; def remove(self, addon: "Addon") -> None
class Addon(Struct):  module: str; preferences: "AddonPreferences | None"
class AddonPreferences(Struct):  _q_registrable = True; bl_idname: ClassVar[str]; layout: UILayout

# stubs.py — registrable, nothing runs
class RenderEngine(Struct); class HydraRenderEngine(RenderEngine); class FileHandler(Struct)
class GizmoGroup(Struct); class Gizmo(Struct); class KeyingSetInfo(Struct); class AssetShelf(Struct)
class WorkSpaceTool(Struct); class NodeTree(ID); class Node(Struct); class NodeSocket(Struct)
class NodeTreeInterfaceSocket(Struct); class OperatorFileListElement(PropertyGroup)
```

#### `quartz/registry.py`, `contexts.py`, `ops.py`, `operators/`

```python
class Registry:
    classes: dict[str, type]; operators: dict[str, type]; owners: dict[type, str | None]; current_owner: str | None
    def register_class(self, cls: type) -> None
    def unregister_class(self, cls: type) -> None
    def is_registered(self, cls: type) -> bool
    def lookup(self, rna_name: str) -> type | None
    def operator(self, idname: str) -> type | None             # "mesh.primitive_cube_add"
    def iter_classes(self, base: type | None = None) -> Iterator[type]
    def classes_owned_by(self, owner: str) -> list[type]
    @contextmanager
    def owner_scope(self, owner: str | None) -> Iterator[None]: ...
    def subscribe(self, callback: Callable[[str, type], None]) -> None   # "register"/"unregister" events
REGISTRY: Registry
def register_class(cls: type) -> None
def unregister_class(cls: type) -> None
def operator_rna_name(idname: str) -> str                      # "mesh.x" -> "MESH_OT_x"
def validate_operator_idname(idname: str) -> None              # contract rules §2.2

PROVIDERS: dict[str, Callable[["Session"], Any]]
class Context(Struct):
    def __getattr__(self, name: str) -> Any
    def __setattr__(self, name: str, value: Any) -> NoReturn
    @contextmanager
    def temp_override(self, **members) -> Iterator[None]: ...
    def copy(self) -> dict[str, Any]
    def path_resolve(self, path: str, coerce: bool = True) -> Any
    def evaluated_depsgraph_get(self) -> "Depsgraph"
class RestrictedContext(Struct):   window_manager: WindowManager; preferences: Preferences
def register_provider(name: str, fn: Callable[["Session"], Any]) -> None

def call(idname: str, *args, **kwargs) -> set[str]
class OpCallable:
    def __call__(self, *args, **kwargs) -> set[str]
    def poll(self, *args) -> bool
    def idname(self) -> str; def idname_py(self) -> str
    def get_rna_type(self) -> RNAStruct
    bl_options: set[str]
class OpsSubmodule:
    def __getattr__(self, name: str) -> OpCallable
    def __dir__(self) -> list[str]
def __getattr__(name: str) -> OpsSubmodule                     # quartz.ops.<mod>
def __dir__() -> list[str]

# quartz/operators/__init__.py
def register_builtin() -> None; def unregister_builtin() -> None
BUILTIN_OPERATORS: tuple[type[Operator], ...]
```

#### `quartz/undo.py`, `depsgraph.py`, `app/`, `session.py`, `utils.py`, `__init__.py`

```python
class UndoStack:
    def __init__(self, session: "Session", *, limit: int = 32) -> None
    enabled: bool
    def push(self, message: str = "") -> None
    def undo(self) -> bool; def redo(self) -> bool
    def can_undo(self) -> bool; def can_redo(self) -> bool
    def history(self) -> list[str]; def clear(self) -> None

class Depsgraph(Struct):
    scene: Scene; view_layer: ViewLayer; mode: str; scene_eval: Scene; view_layer_eval: ViewLayer
    updates: tuple["DepsgraphUpdate", ...]; objects: tuple[Object, ...]; ids: tuple[ID, ...]
    object_instances: tuple["DepsgraphObjectInstance", ...]
    def update(self) -> None; def id_eval_get(self, id: ID) -> ID; def id_type_updated(self, id_type: str) -> bool
class DepsgraphUpdate(Struct):          id: ID; is_updated_geometry: bool; is_updated_transform: bool; is_updated_shading: bool
class DepsgraphObjectInstance(Struct):  object: Object; instance_object: Object | None; is_instance: bool; matrix_world: Matrix; parent: Object | None; persistent_id: tuple[int, ...]; random_id: int

# quartz/app/__init__.py
version: tuple[int, int, int] = (0, 1, 0); version_string: str = "0.1.0"
background: bool = True; factory_startup: bool = True; debug: bool = False; debug_value: int = 0
binary_path: str; tempdir: str; online_access: bool = False; driver_namespace: dict[str, Any]
@dataclass
class Settings:
    invoke_in_background: bool = False; restrict_register: bool = True; lenient_ui: bool = True
    strict_layout: bool = False; record_missing: bool = False; sweep_mode: bool = False
settings: Settings
@dataclass
class Paths:
    project_root: Path; user_dir: Path; temp_dir: Path; addon_dirs: list[Path]; extension_repos: dict[str, Path]
paths: Paths
# quartz/app/handlers.py
<39 Blender lists>; startup_post; shutdown_pre; shutdown_post
def persistent(func: Callable) -> Callable
def dispatch(name: str, *args) -> None
def reset(*, keep_persistent: bool = True) -> None
def all_lists() -> dict[str, list]
# quartz/app/timers.py
def register(function: Callable[[], float | None], *, first_interval: float = 0.0, persistent: bool = False) -> None
def unregister(function: Callable) -> None
def is_registered(function: Callable) -> bool
def pump(*, now: float | None = None, max_calls: int = 1000) -> int
# quartz/app/msgbus.py
def subscribe_rna(*, key: Any, owner: Any, args: tuple, notify: Callable, options: set[str] = set()) -> None
def publish_rna(*, key: Any) -> None
def clear_by_owner(owner: Any) -> None
def flush() -> int
# quartz/app/translations.py
locale: str = "en_US"; locales: tuple[str, ...]; contexts: Any; contexts_C_to_py: dict[str, str]
def pgettext(msgid: str, msgctxt: str | None = None) -> str
def pgettext_iface(msgid: str, msgctxt: str | None = None) -> str
def pgettext_tip(msgid: str, msgctxt: str | None = None) -> str
def pgettext_rpt(msgid: str, msgctxt: str | None = None) -> str
def pgettext_data(msgid: str, msgctxt: str | None = None) -> str
def pgettext_n(msgid: str, msgctxt: str | None = None) -> str
def register(module_name: str, translations_dict: dict[str, dict[tuple[str | None, str], str]]) -> None
def unregister(module_name: str) -> None
def locale_explode(locale: str) -> tuple[str | None, str | None, str | None, str | None, str | None]

# quartz/session.py
class Session:
    data: BlendData; window_manager: WindowManager; preferences: Preferences
    context: Context; undo: UndoStack
SESSION: Session
def current() -> Session
def reset(*, factory: bool = True) -> None                     # in-place, stable identities
def build_factory_scene(data: BlendData) -> None
def build_empty_scene(data: BlendData) -> None
@contextmanager
def restrict_blend() -> Iterator[None]: ...                    # swaps data/context of quartz (and of bpy, if active)

# quartz/utils.py (body of bpy.utils)
def register_class(cls: type) -> None; def unregister_class(cls: type) -> None
def register_classes_factory(classes: Sequence[type]) -> tuple[Callable[[], None], Callable[[], None]]
def register_submodule_factory(module_name: str, submodule_names: Sequence[str]) -> tuple[Callable[[], None], Callable[[], None]]
def escape_identifier(string: str) -> str; def unescape_identifier(string: str) -> str
def flip_name(name: str, *, strip_digits: bool = False) -> str
def add_object(context: Any, data: "ID | None", *, name: str | None = None, location=None, rotation=None,
               scale=None, align: str = "WORLD", link: bool = True, select: bool = True) -> Object
def user_resource(resource_type: str, *, path: str = "", create: bool = False) -> str
def resource_path(type: str, *, major: int = 0, minor: int = 1) -> str
def script_path_user() -> str
def script_paths(*, subdir: str | None = None, user_pref: bool = True, check_all: bool = False, use_user: bool = True) -> list[str]
def extension_path_user(package: str, *, path: str = "", create: bool = False) -> str
def execfile(filepath: str, *, mod: ModuleType | None = None) -> ModuleType
def time_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> "datetime.timedelta"
def time_to_frame(time: "datetime.timedelta | float", *, fps: float | None = None, fps_base: float | None = None) -> float
def smpte_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> str
def smpte_from_seconds(time: float, *, fps: float | None = None, fps_base: float | None = None) -> str
def register_manual_map(manual_hook: Callable) -> None; def unregister_manual_map(manual_hook: Callable) -> None
def register_preset_path(path: str) -> bool; def unregister_preset_path(path: str) -> bool
def register_cli_command(id: str, execute: Callable) -> Any; def unregister_cli_command(handle: Any) -> None
def register_tool(tool_cls: type, *, after: Any = None, separator: bool = False, group: bool = False) -> None
def unregister_tool(tool_cls: type) -> None
# quartz/utils.py — submodules
class previews:  # namespace
    def new() -> "ImagePreviewCollection"; def remove(pcoll: "ImagePreviewCollection") -> None
class ImagePreviewCollection(dict):  def load(self, name: str, filepath: str, filetype: str, force_reload: bool = False) -> Any; def new(self, name: str) -> Any; def clear(self) -> None; def close(self) -> None
class units:  # namespace
    def to_string(unit_system: str, unit_category: str, value: float, *, precision: int = 3, split_unit: bool = False, compatible_unit: bool = False) -> str
    def to_value(unit_system: str, unit_category: str, str_input: str, *, str_ref_unit: str | None = None) -> float

# quartz/__init__.py — native facade (Path C)
from . import types, props, ops, utils, app, math, geometry
from .util import paths as path
data: BlendData          # = session.SESSION.data
context: Context         # = session.SESSION.context
__version__: str = "0.1.0"
# import effect: _hooks.install(...), operators.register_builtin(), session.reset(factory=True)
```

**Exit criterion for Layer 2**: factory scene equal to the dump's `factory_scene`; model and
contract tests green (without `compat`, using `quartz.*`); `test_dump_props/ops/signatures` green for what
was implemented; goldens `g01–g12` green.

### 10.3 Layer 3 — shims, loader, CLI and sweep

Order: `quartz/compat.py` + minimal `compat/bpy` → `compat/mathutils` → `quartz/addons.py` +
`compat/addon_utils.py` → `quartz/cli.py` (`info`, `run-script`, `enable-addon`) → `quartz/sweep.py` +
`addon-sweep` + Blender baseline → `compat/bpy_extras` → `compat/gpu|blf|gpu_extras` →
`quartz/devtools/bpyscan.py` + `scan-addon` → `compat/bmesh` (after `editmesh`).

#### `quartz/compat.py`

```python
COMPAT_DIR: Path                                   # <project>/compat or $QUARTZ_COMPAT_DIR
def activate(*, blender_version: tuple[int, int, int] = (5, 2, 2), lenient_ui: bool = True,
             record_missing: bool = True, restrict_register: bool = True) -> None
def deactivate() -> None
def is_active() -> bool
@contextmanager
def activated(**kwargs) -> Iterator[None]: ...
def note_missing(symbol: str) -> None              # called by the compat __getattr__ functions
def missing_symbols() -> "collections.Counter[str]"
def clear_missing() -> None
def resolve_symbol(path: str) -> bool              # does "bpy.types.FileHandler" exist in compat?
```

#### `quartz/addons.py`

```python
@dataclass
class Manifest:
    schema_version: str; id: str; name: str; tagline: str; version: str; type: str; maintainer: str
    license: list[str]; blender_version_min: str; blender_version_max: str | None = None
    website: str | None = None; copyright: list[str] | None = None; permissions: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list); platforms: list[str] = field(default_factory=list)
    wheels: list[str] = field(default_factory=list); build: dict[str, Any] = field(default_factory=dict); raw: dict[str, Any] = field(default_factory=dict)
    @classmethod
    def load(cls, path: str | Path) -> "Manifest": ...
    def validate(self, *, strict: bool = False) -> list[str]
    def to_bl_info(self) -> dict[str, Any]
@dataclass
class AddonInfo:
    module_name: str; path: Path; kind: Literal["LEGACY_FILE", "LEGACY_PACKAGE", "EXTENSION"]
    bl_info: dict[str, Any]; manifest: Manifest | None; repo: str | None; mtime: float
def read_bl_info(path: str | Path, *, fast: bool = True) -> dict[str, Any] | None
def normalize_bl_info(info: dict[str, Any], module_name: str) -> dict[str, Any]
class AddonManager:
    def __init__(self, registry: Registry, session: Session) -> None
    def add_path(self, path: str | Path) -> None
    def add_repo(self, repo_module: str, path: str | Path) -> None
    def refresh(self) -> None
    def discover(self) -> list[AddonInfo]
    def modules(self, *, refresh: bool = True) -> list[ModuleType]          # "fake modules" with bl_info/__file__/__time__
    def module_bl_info(self, mod: ModuleType, *, info_basis: dict | None = None) -> dict[str, Any]
    def enable(self, module_name: str, *, default_set: bool = False, persistent: bool = False,
               refresh_handled: bool = False, handle_error: Callable[[BaseException], None] | None = None,
               restrict: bool = True) -> ModuleType | None
    def disable(self, module_name: str, *, default_set: bool = False, refresh_handled: bool = False,
                handle_error: Callable[[BaseException], None] | None = None) -> None
    def check(self, module_name: str) -> tuple[bool, bool]
    def check_extension(self, module_name: str) -> bool
    def disable_all(self) -> None
    def reset_all(self, *, reload_scripts: bool = False) -> None
    def leaks(self, module_name: str) -> list[type]
    def extension_path_user(self, package: str, *, path: str = "", create: bool = False) -> str
    def pin_annotations(self, module: ModuleType) -> int                    # §4.5
MANAGER: AddonManager
```

#### `quartz/sweep.py`, `quartz/cli.py`, `quartz/__main__.py`, `quartz/devtools/bpyscan.py`

```python
LEVELS: tuple[str, ...] = ("NONE", "STATIC", "METADATA", "IMPORT", "REGISTER", "UI_SMOKE", "UNREGISTER_CLEAN")
@dataclass
class Target:  name: str; kind: Literal["addon", "extension", "script"]; path: Path; search_path: Path | None; repo: str | None
@dataclass
class SweepResult:
    target: str; kind: str; level: str; ok: bool; registered: dict[str, int]; menus_extended: list[str]
    ui_smoke: dict[str, int]; missing_symbols: dict[str, int]; warnings: list[str]; leaks: list[str]
    error_type: str | None; error: str | None; traceback_tail: str | None; seconds: float
    def to_dict(self) -> dict[str, Any]
@dataclass
class SweepReport:
    results: list[SweepResult]; started: str; seconds: float
    def missing_symbol_ranking(self) -> list[tuple[str, int, list[str]]]
    def compare_baseline(self, baseline: dict[str, Any]) -> dict[str, Any]    # vs data/sweep/blender_baseline.json
    def check_ratchet(self, ratchet: dict[str, Any]) -> list[str]           # regressions
    def to_json(self) -> dict[str, Any]; def to_markdown(self) -> str         # report in pt-BR
def discover_blender_targets(scripts_root: str | Path, *, addons: bool = True, templates: bool = True) -> list[Target]
def discover_fixture_targets(root: str | Path) -> list[Target]
def run_target_inprocess(target: Target, *, smoke_ui: bool = True) -> SweepResult      # used by enable-addon
def run_target(target: Target, *, timeout: float = 60.0, sweep_mode: bool = True) -> SweepResult  # subprocess
def sweep(targets: Sequence[Target], *, jobs: int = 1, timeout: float = 60.0) -> SweepReport

# quartz/cli.py
def main(argv: Sequence[str] | None = None) -> int
def build_parser() -> argparse.ArgumentParser
def cmd_info(args: argparse.Namespace) -> int
def cmd_scan_addon(args: argparse.Namespace) -> int
def cmd_enable_addon(args: argparse.Namespace) -> int
def cmd_run_script(args: argparse.Namespace) -> int
def cmd_addon_sweep(args: argparse.Namespace) -> int

# quartz/devtools/bpyscan.py — core extracted from tools/scan_bpy_usage.py (ModuleScanner, GroupStats,
# cut_depth, resolve_class_bases); tools/scan_bpy_usage.py becomes a wrapper and the 4 existing tests stay green
def scan_source(source: str, *, group: str = "target") -> "GroupStats"
def scan_path(path: str | Path) -> "GroupStats"
```

#### `compat/` — contents of each package

| File | Contents (everything is a re-export or a Blender quirk) |
|---|---|
| `bpy/__init__.py` | `from . import types, props, ops, utils, path, app, msgbus`; `data`, `context` (instances from `quartz`) |
| `bpy/types.py` | static names = `quartz.types.*` (includes `bpy_struct = Struct`, `bpy_prop_collection = PropCollection`, `ID`, `Object`...); module-level `__getattr__` over the registry + phantom menus + log of missing names; `__dir__` |
| `bpy/_ui_names.py` | curated tuple of `*_MT_*`/`*_PT_*`/`*_HT_*` names and function `make_phantom(name)` |
| `bpy/props.py` | `from quartz.props import BoolProperty, ..., RemoveProperty, _PropertyDeferred` |
| `bpy/ops.py` | `__getattr__`/`__dir__` delegating to the `quartz.ops` namespace |
| `bpy/utils/__init__.py`, `previews.py`, `units.py` | re-export of `quartz.utils` + `keyconfig_init/set`, `load_scripts`, `refresh_script_paths`, `modules_from_path`, `blend_paths`, `is_path_builtin/extension`, `manual_language_code`, `app_template_paths` (honest no-ops) |
| `bpy/path.py` | `from quartz.util.paths import *` |
| `bpy/app/__init__.py` | `version=(5,2,2)`, `version_string="5.2.2 LTS"`, `version_file=(5,2,45)`, `version_cycle`, `build_*`, `alembic/usd/ffmpeg/ocio/oiio/opensubdiv/openvdb/sdl` (`supported=False` namespaces), remaining attributes read from `quartz.app` |
| `bpy/app/handlers.py`, `timers.py`, `translations.py`, `icons.py` | re-export of `quartz.app.*` (Blender names only) |
| `bpy/msgbus.py` | re-export of `quartz.app.msgbus` (without `flush`) |
| `mathutils/*` | re-export of `quartz.math.*`; `noise`/`interpolate` with functions that raise an explicit `NotImplementedError` until the sweep asks for them |
| `bmesh/*` | `new(use_operators=True)`, `from_edit_mesh`, `update_edit_mesh`, `types.BM* = quartz.geometry.editmesh.EM*`, `ops.*` = `editmesh_ops.*` |
| `bpy_extras/*` | `ImportHelper`, `ExportHelper`, `orientation_helper`, `axis_conversion`, `unpack_list`, `unpack_face_list`, `path_reference`, `path_reference_mode`, `poll_file_object_drop`, `AddObjectHelper`, `object_data_add`, `object_add_grid_scale`; `anim_utils`/`node_utils`/`view3d_utils` with the minimum requested by the sweep |
| `gpu/*`, `gpu_extras/*`, `blf.py` | stubs (§6.1) |
| `addon_utils.py` | `paths, modules, modules_refresh, check, check_extension, enable, disable, disable_all, reset_all, module_bl_info, extensions_refresh, addons_fake_modules` → `quartz.addons.MANAGER` |
| `idprop/types.py`, `bl_math.py`, `rna_prop_ui.py`, `bl_ui/utils.py` | re-export/minimal glue |

**Exit criterion for Layer 3** (= "green sweep" for this milestone): fixtures 100% at
`UNREGISTER_CLEAN`; templates matching the Blender baseline in at least 30 of 38; out-of-scope add-ons
declared (`cycles`, `bl_pkg`); remaining add-ons in `addons_core` at the same level as Blender
at `REGISTER` and with the same class counts per base; the 5 CLI subcommands with tests; the
ratchet recorded.

### 10.4 Estimated sizes (estimate, not measurement)

| Block | Lines (order of magnitude) |
|---|---|
| `util` + `_hooks` | 400 |
| `math` (without BVH) | 1,600 |
| `props` | 1,000 |
| `geometry` (without editmesh) | 900; `editmesh` +900 |
| `types` + `database` + `registry` + `contexts` + `ops` | 3,200 |
| `operators` + `ui` + `undo` + `depsgraph` + `app` + `session` + `utils` | 1,800 |
| `addons` + `sweep` + `cli` + `compat.py` | 1,300 |
| entire `compat/` | 1,200 (≤ 30% of `quartz/`) |
| tests | 4,000+ |

---

## 11. Risks and mitigation

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Python 3.14 vs 3.13**: lazy annotations and the `__annotations__` trick that erases annotations (verified) | `collect_annotations` with `annotationlib` + string eval; pinning annotations in the loader; own `orientation_helper`; sweep flags add-ons that use the trick |
| R2 | Erosion of thinness: logic leaking into `compat/` | `test_compat_thinness` (imports, no data state, line budget); review: "is this a Blender quirk?" |
| R3 | Leniency masking errors (phantom on-demand menus, `UILayout` accepting everything) | strict mode in contract tests; everything that is synthesized goes into the report's `warnings` |
| R4 | Performance: `users`/`children`/`matrix_world` O(N) and `mathutils` on numpy with per-object overhead for small ones | `foreach_get/set` paths and direct numpy; benchmark in `tests/perf/` (own marker) before optimizing; incremental caches behind the same API |
| R5 | Blender [I] behaviors (iteration order, naming rule, scene/camera `users`, `abspath` with unsaved file, `cls.register()` call, subtype list → mathutils, `INVOKE` without `execute`) | goldens `g01–g14` before implementing each one; divergences in the `COMPAT.md` table |
| R6 | Execution of third-party code writing outside the project (bytecode in `Program Files`, user configs, network) | subprocess with `-B`, `cwd` and `QUARTZ_USER_DIR` inside `tmp/`, network denied in `--sweep-mode`, timeouts (§7.4) |
| R7 | GPL contamination (copying `bpy_extras`, `addon_utils`, `_bpy_types`, which are Python and tempting) or assets (Suzanne) | golden rule 8; implement from the paraphrased contract; `test_cleanroom`; `primitive_monkey_add` with a false `poll` |
| R8 | Semantic divergences from "eager" evaluation (`matrix_world` always current) | documented and pinned by test; becomes optional once there is a real depsgraph |
| R9 | Long tail (304 symbols used by a single group) consuming the milestone | backlog ranked by the sweep; only implement what unblocks targets |
| R10 | Global singletons making tests order-dependent | in-place `session.reset()` in an autouse fixture; sweep always in a subprocess; registry cleaned per `owner` |
| R11 | float32 vs float64 precision producing false negatives in the differentials | "float32 at rest" policy + default tolerance `1e-5`, adjustable per key |
| R12 | Costly refactoring when the C4D *description* arrives | all metadata readers go through `props.describe()`; `meta` already exists; `bl_rna` is a view |
| R13 | Encoding on Windows (add-on prints with Unicode on the cp1252 console) | `-X utf8` + `PYTHONIOENCODING=utf-8` in subprocesses; source reading always in UTF-8 |

---

## 12. What to defer (and why)

| Deferred | Reason / trigger to include |
|---|---|
| GUI, viewport, renderer, real GPU | out of the milestone by definition |
| `.blend` (read/write) and own `.qz` format | only the seam (`_q_snapshot` already serializes state); comes in with the files milestone |
| Modifier evaluation, generators, real depsgraph, Geometry Nodes, functional `NodeTree` | `evaluated_get()` returns the original; registrable stubs are enough for the sweep |
| Animation (Action/slots/channelbags/FCurve/keyframes), drivers | Tier 2 of usage; comes in when the sweep asks for execution of `io_anim_bvh`/`io_scene_fbx` |
| Armature/bones/pose, Curve with splines | data containers when an add-on scenario requires them |
| Full `bmesh` | only the Tier 3 subset (`new`, `from_mesh/to_mesh`, `ops.triangulate`, `from_edit_mesh`) after the first sweep |
| `BVHTree`, `mathutils.noise/interpolate` | on demand from the ranking |
| Event loop, modal operators, `invoke_props_*` dialogs | headless has no events; `INVOKE` goes to `execute` as in Blender |
| Incremental undo, incremental `users`, `matrix_world` caches | only with a benchmark |
| C4D concepts: full `Description`, tags, `Generator`, `Field`, `InstanceCloud`, versioned assets, takes | C4D milestone; seams already reserved (§3.11) |
| Extension wheels, remote repositories, `bl_pkg` | require network/installation; outside the milestone rules |
| `RenderEngine`/`HydraRenderEngine` executing | no renderer |
| Real pt-BR UI translations | the mechanism already exists; content comes with the UI |
| Library linking/overrides | without `.blend` there are no libraries |

---

## 13. What was verified by running and what was not

Verified by running (Python from `.venv`, 3.14.7, numpy 2.5.4):

- Lazy evaluation of annotations in 3.14 (the annotation expression only runs on first access, with the
  globals of that moment).
- The `setattr(cls, "__annotations__", {})` trick erases existing annotations in 3.14 and
  `__annotate_func__` ceases to exist (unrecoverable).
- `tomllib` and `annotationlib` available.
- Reading the research data: structure and cited contents of `data/blender_api_dump.json`
  (factory scene, properties of `Object/Camera/Light`, signatures of `ID.rename`, `objects.new`,
  `lights.new`, `Mesh.update`, `id_semantics` probes) and of `data/bpy_usage.json`.
- Reading (listing/grep only, without copying) the module-level imports of some `addons_core` add-ons
  (e.g. `cycles` imports `_cycles` inside functions called in `register`;
  `io_mesh_uv_layout` imports `gpu` only in the PNG exporter) and the use of `from __future__ import
  annotations` in `bl_operators` and `cycles`.

Not verified (none of this was executed):

- Blender was **not** run in this stage; all **[I]** items depend on the proposed goldens.
- No Quartz code was written; signatures and size estimates are design-level.
- The sweep result hypotheses (§9.5) are predictions from static analysis, not measurements.
