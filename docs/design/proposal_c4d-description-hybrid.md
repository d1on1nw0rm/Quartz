# Architecture proposal — "c4d-description-hybrid"

> Quartz — author: **D1on1n**. Design document for the initial milestone (Path C = native `quartz` API,
> Path A = `bpy-lite` layer). Date: 2026-10-22.
> Angle of this proposal: **description-driven core** (the central idea of Cinema 4D) with
> **Blender's data and API shape** (data-blocks, collections, `bpy`-shaped).
> Inputs read: `docs/research/bpy_usage.md`, `docs/research/bpy_contract.md`,
> `docs/research/c4d_model.md`, `data/bpy_usage.json`, `data/blender_api_dump.json` and the
> earlier map in `D:/Claude/fusion` (RESUMO.txt, a summary file).
>
> Clean-room hygiene: this document cites Blender and Cinema 4D names only as identifiers.
> All code here is original sketch code in the intended Quartz syntax. Blender error messages
> are paraphrased, not copied.

Confidence legend inherited from the research: **[O]** observed by running Blender 5.2.2;
**[L]** read in the Python that ships with Blender; **[I]** inference to be verified with a differential test;
**[M]** measured by me in this proposal (see §0.2).

---

## 0. Summary

### 0.1 The thesis

Every Quartz type — data-block (`Object`, `Mesh`, `Scene`…), nested struct (`RenderSettings`,
`MeshVertex`), component (`Tag`, `Modifier`), parametric data-block (`Generator`) and registrable
add-on class (`Operator`, `Panel`, `PropertyGroup`…) — declares its parameters **exactly once**,
with annotations in the `bpy.props` style. The core compiles these annotations into an immutable,
inheritable, introspectable **`Description`** (type, limits, unit, default, enum, group, parent, conditional
enabling, widget hint, dirty channel, storage binding, schema version). This description is the **single source** of:
attribute access and validation, the `bl_rna` of the `bpy` shim, automatic UI (layout recorder), `.qz`
serialization, undo journal paths, API dump for parity tests with Blender, and add-on *sweep*
reports. On top of that, the **data model is Blender's** (Object + data, collections, view layers, unique names, user count) and
the C4D ideas come in as **extensions**: ordered children, behavior `Object.tags`,
`Generator` as a data-block, per-channel dirty counters and evaluation in named stages.

### 0.2 What I verified by running (and what I did not)

Run with `D:/Claude/reverseEngineering/Quartz/.venv/Scripts/python.exe` (Python 3.14.7,
numpy 2.5.4), inline commands only, nothing written other than this document:

| Measurement [M] | Result | Consequence in the design |
|---|---|---|
| `Vector` of 3 floats as Python list vs `np.ndarray` (sum) | 0.49 µs vs 0.57 µs | List-based Vector (§5.9) |
| dot product list vs numpy | 0.20 µs vs 1.43 µs | same |
| 4×4 matrix @ 4×4: list vs numpy | 7.5 µs vs 1.7 µs | numpy-based Matrix |
| 4×4 matrix @ vector: list vs numpy | 0.88 µs vs 1.44 µs | acceptable in both; Matrix stays on numpy |
| descriptor with coercion (get / set) vs plain attribute | 0.19 / 0.32 µs vs 0.03 / 0.04 µs | acceptable cost for `ParamDescriptor` (§4.6) |
| Python 3.14: class annotations | **lazily evaluated** (PEP 649): `IntProperty(...)` in an annotation is only called when the annotation is first read; after that it is cached | the registry reads annotations with `annotationlib.get_annotations` for each class in the MRO (§4.10) |
| swapping `obj.__class__` between subclasses without divergent `__slots__` | works | `light.type = 'SUN'` swaps the class (§5.5) |
| `tomllib` available | yes | reading `blender_manifest.toml` with the stdlib only (§8) |

**Not verified**: nothing in this architecture has been implemented. All APIs below are proposals.
Facts about Blender come from the research ([O]/[L] marks); the [I] marks need a differential test.

---

## 1. Principles and constraints

1. **The description is the single source.** Nothing (UI, IO, undo, RNA, docs) declares parameters on its
   own; all of them read the `Description`.
2. **bpy shape, C4D soul.** Names, `new()/remove()` collections, `bl_idname`, `register()` are Blender's.
   From C4D come description metadata, ordered hierarchy, tags, generators, per-channel dirtiness and evaluation stages.
   No integer IDs, `GetX/SetX` or numeric constants.
3. **Three layers with dependencies only downward** (§12). Layer 1 (math, props, geometry) has no
   cross dependency whatsoever; this is verified by an AST test.
4. **Thin shims.** `compat/*` only re-exports, filters signatures, projects names and adds stubs. Logic
   lives in `quartz`. Verified by a test (§7.8).
5. **Headless and deterministic.** No event loop, no threads; timers and msgbus only with a manual *pump*.
   Third-party add-ons run in a subprocess in the sweep.
6. **Fidelity with declared divergences.** Where Blender has accidental behavior (a half-registered
   class), Quartz MAY diverge, but the divergence is listed in `docs/COMPAT.md` and
   in a marked test.
7. **Clean-room.** Not a single line of Blender (GPL) or C4D (proprietary). Factual data (type names,
   numeric defaults, observed counts) MAY become tool-generated tables.
8. **Python files**: one-line docstring + `# Quartz - author: D1on1n`; identifiers and
   comments in English; human documentation in pt-BR.

---

## 2. Overview

```
                         Layer 3  ─────────────────────────────────────────────────────────
  compat/bpy  compat/mathutils  compat/bmesh  compat/bpy_extras  compat/addon_utils  gpu/blf stubs
        │  (re-export / signature filter / name view / stub — no logic)
  quartz.compat (activate)   quartz.addons (loader, sweep)   quartz.cli (python -m quartz)
                         Layer 2  ─────────────────────────────────────────────────────────
  quartz.core: Session · Struct/RNA · ID/Main · registry/kinds · context · undo · dirty · depsgraph
  quartz.types: Object Mesh Material Camera Light World Collection Scene ViewLayer Image Text
                Generator Tag Modifier Operator Panel Menu UIList PropertyGroup WindowManager…
  quartz.ops (runner + built-ins) · quartz.ui (recorder) · quartz.io (.qz) · quartz.app · quartz.utils
                         Layer 1  ─────────────────────────────────────────────────────────
  quartz.math (Vector/Matrix/…)   quartz.props (ParamSpec/Description/ParamStore)   quartz.geometry
                                                                                  (MeshData SoA numpy,
                                                                                   EditMesh, primitives)
```

Description pipeline (the heart of this proposal):

```
bpy.props annotations (PropDeferred) ──┐
q_groups / q_hide / q_show / q_override ├─► compile_description(cls) ─► Description (immutable, revision N)
descriptions of the bases (MRO)        ┘                                    │
Type.x = Prop(...) / del Type.x ─────► Description.derive(...) ───────────┤
instance.describe(builder) ──────────► effective description of the instance ┤
                                                                           ├─► ParamDescriptor (attributes)
                                                                           ├─► coercion/validation (ParamStore)
                                                                           ├─► bl_rna (RNAStruct) of the shim
                                                                           ├─► UILayout: auto_layout + layout.prop validation
                                                                           ├─► .qz: serialization by identifier + upgrade()
                                                                           ├─► undo: ParamChange(path, old, new)
                                                                           ├─► dirty: channel per parameter
                                                                           ├─► vectorized foreach_get/set (COLUMN)
                                                                           └─► dump-api (same schema as blender_api_dump.json)
```

---

## 3. Package and file layout

```
D:/Claude/reverseEngineering/Quartz/
├─ quartz/                          # native API (Path C)
│  ├─ __init__.py                   # version + lazy access: data, context, ops, types, props, utils, app, path
│  ├─ __main__.py                   # python -m quartz -> quartz.cli.main()
│  ├─ _version.py
│  ├─ math/                         # LAYER 1 — stdlib + numpy
│  │  ├─ __init__.py  _owner.py  _swizzle.py
│  │  ├─ vector.py  matrix.py  quaternion.py  euler.py  color.py
│  │  ├─ geometry.py  kdtree.py  bvhtree.py  interpolate.py  noise.py
│  │  └─ batch.py                   # vectorized operations (N,3)/(N,4,4) — Quartz only
│  ├─ props/                        # LAYER 1 — stdlib (+ numpy for arrays)
│  │  ├─ __init__.py  deferred.py  spec.py  description.py  store.py  coerce.py
│  │  ├─ collection.py  paths.py  adapters.py  errors.py
│  ├─ geometry/                     # LAYER 1 — stdlib + numpy
│  │  ├─ __init__.py  attributes.py  mesh_data.py  topology.py  normals.py  triangulate.py
│  │  ├─ primitives.py  transform.py  validate.py  editmesh.py  edit_ops.py
│  │  ├─ curve_data.py  instances.py  geometry_set.py
│  ├─ core/                         # LAYER 2
│  │  ├─ __init__.py  errors.py  session.py  struct.py  rna.py  id.py  names.py  users.py
│  │  ├─ main.py  dirty.py  paths.py  custom_props.py  registry.py  kinds.py  context.py
│  │  ├─ undo.py  journal.py  handlers.py  timers.py  msgbus.py  reports.py
│  │  ├─ depsgraph.py  evaluation.py
│  ├─ types/                        # LAYER 2 — namespace shaped like bpy.types
│  │  ├─ __init__.py                # re-export + __getattr__ for registered types (RNA name)
│  │  ├─ object.py  mesh.py  mesh_views.py  material.py  camera.py  light.py  world.py
│  │  ├─ collection.py  scene.py  view_layer.py  image.py  text.py
│  │  ├─ generator.py  tag.py  modifier.py
│  │  ├─ operator.py  ui.py  prefs.py  wm.py  event.py  file_handler.py  misc_kinds.py
│  ├─ ops/                          # LAYER 2
│  │  ├─ __init__.py  namespace.py  runner.py
│  │  └─ builtin/  __init__.py  object.py  mesh.py  transform.py  ed.py  wm.py
│  ├─ ui/        __init__.py  layout.py  auto_layout.py  draw.py          # LAYER 2
│  ├─ io/        __init__.py  qzfile.py  codec.py  upgrade.py             # LAYER 2
│  ├─ app/       __init__.py  handlers.py  translations.py  timers.py  settings.py   # LAYER 2
│  ├─ utils/     __init__.py  registration.py  resources.py  units.py  previews.py  time.py  # LAYER 2
│  ├─ path.py                       # LAYER 2 — equivalent of bpy.path
│  ├─ extras/    __init__.py  io_utils.py  object_utils.py  anim_utils.py  view3d_utils.py  # LAYER 2
│  ├─ factory.py                    # LAYER 2 — factory scene
│  ├─ compat/                       # LAYER 3 — activation and tables (these are NOT the shims)
│  │  ├─ __init__.py  mapping.py  messages.py  restrict.py
│  │  ├─ ui_names.json              # *_MT_/*_PT_/*_HT_/*_UL_ names (generated from data/blender_api_dump.json)
│  │  └─ coverage.json              # bpy symbol -> IMPLEMENTED | STUB | MISSING (generated)
│  ├─ addons/                       # LAYER 3
│  │  ├─ __init__.py  discovery.py  blinfo.py  manifest.py  manager.py  restrict.py
│  │  ├─ report.py  scan.py  sweep.py
│  ├─ cli/                          # LAYER 3
│  │  ├─ __init__.py  main.py  output.py
│  │  ├─ cmd_info.py  cmd_scan.py  cmd_enable.py  cmd_run.py  cmd_sweep.py  cmd_describe.py  cmd_dump.py
│  └─ testing/   __init__.py  fixtures.py  golden.py   # test support (importable by pytest)
├─ compat/                          # Path A shims (enter sys.path via quartz.compat.activate())
│  ├─ bpy/  __init__.py  types.py  props.py  ops.py  path.py  msgbus.py
│  │  ├─ utils/  __init__.py  previews.py  units.py
│  │  └─ app/    __init__.py  handlers.py  translations.py  timers.py  icons.py
│  ├─ mathutils/  __init__.py  geometry.py  kdtree.py  bvhtree.py  noise.py  interpolate.py
│  ├─ bmesh/      __init__.py  types.py  ops.py  utils.py  geometry.py
│  ├─ bpy_extras/ __init__.py  io_utils.py  object_utils.py  anim_utils.py  view3d_utils.py
│  │              node_utils.py  image_utils.py  asset_utils.py
│  ├─ addon_utils.py  rna_prop_ui.py  bl_math.py
│  ├─ idprop/     __init__.py  types.py
│  ├─ bl_ui/      __init__.py  utils.py        # minimal original helpers (PresetPanel)
│  ├─ bl_operators/ __init__.py  presets.py    # minimal original AddPresetBase
│  └─ gpu/ __init__.py …   gpu_extras/ …   blf.py   # GPU-less stubs
├─ tools/
│  ├─ scan_bpy_usage.py   dump_bpy_api.py   run_dump_bpy_api.ps1      # existing
│  ├─ gen_compat_tables.py    # dump -> quartz/compat/ui_names.json, translations.contexts names
│  ├─ run_golden.py           # runs scenarios in headless Blender -> data/golden/*.json
│  ├─ compat_coverage.py      # Quartz dump-api vs blender_api_dump.json -> docs/research/compat_coverage.md
│  └─ dev_setup.py            # creates .venv/Lib/site-packages/quartz_dev.pth pointing to the root (optional)
├─ tests/   (see §11)
├─ data/    bpy_usage.json  blender_api_dump.json  golden/*.json
└─ docs/    README.md  ARCHITECTURE.md  COMPAT.md  ROADMAP.md  design/  research/
```

Two packages called "compat" coexist without conflict: `quartz/compat/` is Quartz code
(activation, tables); `compat/` is a **search directory** whose contents are the top-level modules
`bpy`, `mathutils`… — the name `compat` is never imported as a package.

---

## 4. The description system (core of Path C)

### 4.1 From `PropDeferred` to `Description`

- `quartz.props.IntProperty(...)` (and the other 10 functions of `bpy.props`) **does not create anything**:
  it returns a `PropDeferred(function, keywords)`, exactly the contract observed in Blender
  [O, contract §4.1]. The `bpy.props` shim re-exports functions that return the same object, and
  `deferred.function` is the public function of the namespace that created it.
- `compile_description(cls)` walks the MRO (from the bases to the class) and collects, **per class**, the
  annotations whose value is a `PropDeferred` (mixins such as `ImportHelper` and `AddObjectHelper` work
  because they enter the MRO [O]), applies `q_hide`/`q_show`/`q_override` and groups (`q_groups`), resolves
  `type=` of pointers and collections and produces an immutable `Description`.
- The old-style assignment `x = IntProperty()` in the class body is ignored, as in Blender [O], but the
  compiler **records a warning** (`Description.ignored_assignments`) that the sweep reports.

### 4.2 `ParamSpec`: fields

The bpy fields reproduce the 5.2.2 `bpy.props` signature [O, contract §4.1]; the Quartz fields
are the C4D description ideas [c4d_model §3, §4, §7] translated into strings.

| Field | Origin | Meaning |
|---|---|---|
| `identifier` | bpy | attribute name; key for everything (data path) |
| `kind` | bpy | `BOOL INT FLOAT STRING ENUM POINTER COLLECTION` |
| `size` | bpy | `0` scalar, `n` vector, `(4, 4)` matrix |
| `name`, `description`, `translation_context` | bpy | labels (default in English) |
| `default`, `min`, `max`, `soft_min`, `soft_max`, `step`, `precision` | bpy | hard range (clamps) and "soft" range (UI) |
| `subtype`, `unit` | bpy | `XYZ TRANSLATION EULER MATRIX COLOR FILE_PATH…`, `LENGTH ROTATION TIME…` |
| `maxlen` | bpy | string truncation [O] |
| `items` | bpy | tuple of `EnumItem` or function `(self, context)` |
| `fixed_type` | bpy | class accepted by `POINTER`/`COLLECTION` |
| `options`, `override`, `tags` | bpy | `ANIMATABLE HIDDEN SKIP_SAVE ENUM_FLAG LIBRARY_EDITABLE OUTPUT_PATH…` |
| `update`, `get`, `set`, `get_transform`, `set_transform`, `search`, `search_options`, `poll` | bpy | callbacks |
| `group` | C4D | id of the `GroupSpec` (tab/section) |
| `parent` | C4D (`PARENTID`) | parameter this one visually depends on; if the parent is `BOOL`, the default `enabled_if` = the parent's value |
| `enabled_if`, `visible_if` | C4D (`GetDEnabling`) | `callable(owner) -> bool` |
| `widget`, `ui` | C4D (`CUSTOMGUI`) | widget hint (`SLIDER`, `COLOR`, `FILE`, …) and free-form dictionary (order, columns, short name) |
| `dirty` | C4D (`DIRTYFLAGS`) | channel bumped on write: `DATA MATRIX GEOMETRY SELECT CHILDREN DESCRIPTION SHADING VISIBILITY` |
| `storage` | Quartz | `STORE` (ParamStore), `VIRTUAL` (get/set only), `COLUMN` (numpy attribute column) |
| `column` | Quartz | `ColumnBinding(domain, attribute, component=None, invert=False)` for `COLUMN` |
| `on_remove` | Quartz | ID pointer: `CLEAR` (becomes `None`) or `DELETE_OWNER` (deletes the owner) |
| `refcount` | Quartz | ID pointer counts as a user (default `True`) |
| `uid` | C4D (numeric ID) | optional stable integer, never the primary key |
| `since` | C4D (`disklevel`) | schema version that introduced the parameter |
| `origin` | Quartz | `"bpy"` (exists in Blender) or `"quartz"` (extension) — used in the dump and in collisions (§7.6) |

### 4.3 Groups, parent and enabling

```python
class Cube(quartz.types.Generator):                 # original sketch
    bl_idname = "QZ_GEN_CUBE"
    bl_label = "Cube"
    q_groups = (GroupSpec("object", "Object"), GroupSpec("fillet", "Fillet", parent="object"))
    size: FloatVectorProperty(size=3, default=(2.0, 2.0, 2.0), min=0.0, subtype="XYZ_LENGTH",
                              unit="LENGTH", group="object", dirty="GEOMETRY")
    segments: IntVectorProperty(size=3, default=(1, 1, 1), min=1, soft_max=100, group="object",
                                dirty="GEOMETRY")
    fillet: BoolProperty(default=False, group="fillet", dirty="GEOMETRY")
    fillet_radius: FloatProperty(default=0.1, min=0.0, unit="LENGTH", group="fillet",
                                 parent="fillet", dirty="GEOMETRY")   # enabled only if fillet
```

`Description.tree()` returns groups and parameters nested by `parent`; `is_enabled(owner, id)` and
`is_visible(owner, id)` evaluate the conditions. The automatic UI (§6.6) and the dump use this.

### 4.4 Inheritance and declarative override

- Description inheritance = Python class inheritance (C4D's `INCLUDE`).
- `q_hide = {"segments"}` hides an inherited parameter (it keeps existing and serializing);
  `q_show` re-shows one that the base hid (the "deformer base declares everything hidden" pattern).
- `q_override = {"size": {"default": (1, 1, 1), "soft_max": 10}}` changes the metadata of an
  inherited parameter **without redeclaring it** (redeclaring the annotation also works and replaces it entirely).

### 4.5 Per-instance dynamic description

The equivalent of `GetDDescription`: an optional method

```python
def describe(self, builder: DescriptionBuilder) -> None:
    for i in range(self.layer_count):
        builder.add(f"layer_{i}_weight", FloatProperty(default=1.0, min=0, max=1), group="layers")
```

The instance's effective description (`struct.q_description()`) is computed on demand and cached by the
`DESCRIPTION` channel; the author calls `self.q_redescribe()` when the shape changes. Dynamic parameters
live in the same `ParamStore` and are accessed via `Struct.__getattr__/__setattr__` (which only fire when
the attribute is not a class descriptor). Values of parameters that no longer exist go to an
**orphan bucket** (`ParamStore.orphans()`), preserved in a file round trip.

### 4.6 Storage: three bindings

| `storage` | Where the value lives | Examples |
|---|---|---|
| `STORE` | the struct's `ParamStore` (typed dict; vectors as `float64` arrays) | `Object.location`, `Camera.lens`, add-on props |
| `VIRTUAL` | computed by `get`/`set` (C4D's `GetDParameter`) | `Object.matrix_world`, `Object.dimensions`, `Camera.angle`, `Object.type` |
| `COLUMN` | row `index` of a numpy geometry attribute column | `MeshVertex.co` → `("POINT","position")`, `MeshPolygon.material_index` → `("FACE","material_index")`, `MeshPolygon.use_smooth` → `("FACE","sharp_face", invert=True)` |

`ParamDescriptor` is a data descriptor installed on the class at registration (≈0.2–0.3 µs per access
[M]). `COLUMN` is what makes `foreach_get/foreach_set` **description-driven and vectorized**:
`mesh.vertices.foreach_get("co", buf)` looks up `co` in the `MeshVertex` description, finds the
`position` column and performs a single `np.copyto` (accepts a list or numpy buffer, like Blender [O]). For
non-`COLUMN` parameters, it falls back to a per-element loop.

### 4.7 Order of coercion on write (bpy contract)

`ParamStore.write(spec, owner, value)` applies, in this order:

1. if there is only a `get` (no `set`) → read-only `AttributeError` [O];
2. type check → `TypeError` (`int` accepted in `FLOAT`; `bool` not accepted in `INT` [I]);
3. vector: exact size (sequence, `Vector` or array) → `TypeError`/`ValueError`;
4. enum: value ∈ items (resolved with `context`) → `TypeError` listing the valid ones; `ENUM_FLAG` requires `set` [O];
5. clamp to `min/max` (silent) [O]; `maxlen` truncates [O];
6. `set_transform` (if any), then custom `set` **or** write to the store;
7. mark `is_set`, bump the owner's `dirty` channel, record `ParamChange` in the undo journal;
8. call `update(self, context)` **always**, even without a value change and after clamping [O].

Read: `get_transform`/`get` or the stored value or the default; vectors come back as `Vector`/`Matrix`
**bound to the owner** (writing `ob.location.x = 1` writes to the store) via an injected adapter (§4.11).

### 4.8 Runtime type extension

`StructMeta.__setattr__` intercepts `quartz.types.Scene.my_tool = PointerProperty(type=MyGroup)`:
it compiles the `ParamSpec`, generates a new `Description` (`revision + 1`), installs the descriptor, bumps
the type's global `DESCRIPTION` and fires `handlers.description_changed`. `del Scene.my_tool` does the
inverse (`hasattr` becomes false again [O]). Existing instances read the default until the first write [O].
This is add-on pattern no. 1 (`WindowManager` in 6 groups, `Scene` in 5, `Object` in 3 —
bpy_usage §6).

### 4.9 Who consumes the description

| Consumer | Use |
|---|---|
| `ParamDescriptor` / `ParamStore` | access and coercion |
| `quartz.core.rna` | `bl_rna`, `rna_type`, `bl_rna.properties[...]` (RNA form for the shim) |
| `quartz.ui.auto_layout` | draws any struct by groups, with `enabled_if` |
| `quartz.ui.layout.UILayout` | validates `layout.prop(data, "name")` against the description of `data` → problem recorded if it does not exist |
| `quartz.io` | writes by identifier; `SKIP_SAVE`, `VIRTUAL` and `COLUMN` do not enter the params (geometry goes in arrays); `q_upgrade()` migrates versions |
| `quartz.core.journal` | `ParamChange(owner_uuid, identifier, old, new)` |
| `quartz.core.dirty` | per-parameter channel |
| `python -m quartz describe/dump-api` | generated docs and dump with **the same schema** as `data/blender_api_dump.json` (`type, subtype, unit, array_length, default, min, max, soft_min, soft_max, step, precision, items, fixed_type, flags`) |
| add-on sweep | props missing from built-in types (via `layout.prop` validation), old assignments ignored, warnings |

### 4.10 Python 3.14 and lazy annotations

[M] In the project's Python 3.14, class annotations are evaluated on demand (PEP 649). Decisions:

- the compiler uses `annotationlib.get_annotations(c, format=VALUE)` **for each class in the MRO
  separately** (never `cls.__annotations__`, which in 3.14 neither inherits nor is in the `__dict__` before
  the first access);
- add-ons with `from __future__ import annotations` (annotations become strings) are accepted with
  `eval_str=True` in the module namespace — lenient mode, marked as a divergence [I] because I did not
  verify what Blender 5.2.2 does in this case;
- forward references (class defined later in the module) work in Quartz and would fail
  in Blender (3.13, eager evaluation) — benign divergence, documented.

### 4.11 Injection between layers (keeps Layer 1 free of cross dependencies)

`quartz.props.adapters` exposes injection points filled by Layer 2 on import of
`quartz.core`:

- `set_value_wrapper(family, fn)` — `VECTOR/EULER/QUATERNION/COLOR/MATRIX` → `quartz.math` with an owner;
- `set_id_resolver(fn)` — resolves pointer references (`session_uid` → live ID);
- `set_context_provider(fn)` — `context` passed to `update`/`items`/`poll`;
- `set_type_resolver(fn)` — `type="Object"` (string, internal use only) → registered class.

Without injection (pure Layer 1 tests), vectors come back as `tuple`, and `context` is `None`.

---

## 5. Data model

### 5.1 `Struct`, `ID`, `Main`

- `Struct` (≈ `bpy_struct`): base of everything that has a description. Holds `_q_store`, owner (`id_data`),
  path from the ID (`path_from_id`), liveness flag and custom properties.
- `ID(Struct)`: `name`, `name_full`, `id_type`, `session_uid` (monotonic int per process),
  **`uuid`** (stable, persisted text — the *BaseLink* idea from C4D), `users`, `use_fake_user`,
  `is_evaluated`, `original`, `library` (`None` in this milestone), `is_embedded_data`, `is_runtime_data`.
- `Main` (exposed in the shim as `bpy.types.BlendData`): one `IDCollection` per type. The identity of the
  `Main` object of a session is stable; loading a file **replaces the contents**
  (`_replace_contents`), just as `bpy.data` remains the same object in Blender [I].
- Two value spaces, as in Blender 5.x [O]: (a) described params (`ParamStore`, invisible
  in `id.keys()`, accessible through `bl_system_properties_get()`); (b) dict-style custom properties
  (`id["x"]`, `IDPropertyGroup`/`IDPropertyArray` numpy, metadata via
  `id_properties_ui`). On a `PropertyGroup` instance, `keys()` lists the written values [O].

ID semantics (all [O], contract §7.3):

| Rule | Implementation |
|---|---|
| unique names per type with `.001` | `NameRegistry.unique(base)` per collection; the one being renamed receives the suffix |
| 255 bytes UTF-8, cut at a character boundary; empty → default name | `clamp_name(name, 255)`; `q_default_name` per type |
| `users`: new mesh 0; object using it +1; linked in collection +1; fake user +1 | `UserGraph` fed by pointers with `refcount=True` and by collection links |
| double `link` in the same collection → `RuntimeError` | `CollectionObjects.link` |
| `remove()` deletes even with users; access afterwards → `ReferenceError` | sets `_q_alive=False`; every descriptor checks |
| removing the mesh **deletes the objects that use it**; `objects.remove` leaves the mesh orphaned | `Object.data` declared with `on_remove="DELETE_OWNER"`; other pointers `CLEAR` |
| `orphans_purge(do_recursive)` returns a count; `user_map(subset)` | over `UserGraph` |

This use of `on_remove` in the `ParamSpec` is an example of the angle: **the removal policy is description
data**, not scattered code.

### 5.2 `Object`: type, transforms, mode, selection

- `Object.data` (pointer to `ID`, `on_remove=DELETE_OWNER`); `Object.type` is a read-only `VIRTUAL`
  derived from the class of `data`: `MESH, CURVE, EMPTY, LIGHT, CAMERA, GENERATOR`
  (other Blender enum values are reserved). **Generator objects report `'GENERATOR'`
  in the shim as well** — add-ons filter by `type == 'MESH'` and simply skip them; lying with `'MESH'`
  would break `ob.data.vertices`.
- Transform (group `transform`, `dirty="MATRIX"`): `location`, `rotation_mode`
  (`QUATERNION, XYZ, XZY, YXZ, YZX, ZXY, ZYX, AXIS_ANGLE`, default `XYZ` [O]), `rotation_euler`,
  `rotation_quaternion`, `rotation_axis_angle`, `scale`, `delta_*`, `lock_*`,
  `matrix_parent_inverse` (STORE), and `matrix_basis`, `matrix_local`, `matrix_world`, `dimensions`
  (VIRTUAL, cached by the `MATRIX` counter of the object and its ancestors).
  Formulas to be confirmed by golden tests [I]: `basis = T(loc+dloc) · R(rot∘drot) · S(scale·dscale)`;
  `local = parent_inverse · basis`; `world = parent.world · local`; Euler `XYZ` = `Rz·Ry·Rx`.
  Writing `matrix_world` decomposes into `basis` respecting `rotation_mode`.
- **Ordered hierarchy (C4D)**: `parent` is a pointer (bpy), but the parent keeps an ordered list
  of children. `children` returns the tuple in sibling order; native: `parent_set(parent, *,
  keep_transform=False, index=None)` and `reorder(index)`. Order matters for generators that
  consume children and for the future "deformer as child".
- **Mode**: `Object.mode` (`OBJECT, EDIT, POSE, SCULPT, …`); `context.mode` derived
  (`EDIT_MESH`…). `object.mode_set` is Tier 1 (184 calls, 7 groups — bpy_usage §2), so it enters
  Layer 2: entering `EDIT` on a mesh creates an `EditMesh` (§5.3) bound to the mesh; leaving writes
  back. Multi-editing of selected objects of the same type [I].
- **Selection per view layer** (Blender model): `ViewLayer` holds a `Base(select, hide)` per
  object; `select_get/select_set(state, view_layer=None)`, `hide_get/hide_set`, `visible_get`.
- Component collections: `modifiers` (`ObjectModifiers.new(name, type)`), `tags`
  (`ObjectTags.new(type, name="")`), `constraints` (empty in this milestone), `vertex_groups` (each group
  = named point `FLOAT` attribute), `material_slots` (VIRTUAL over `data.materials` + per-object
  overrides [I]).

### 5.3 `Mesh`: numpy SoA, attributes, RNA views, edit mode

`Mesh(ID)` wraps a `quartz.geometry.MeshData` (Layer 1, composition). Topology in CSR:

| Array | Domain | dtype/shape | Observed equivalent in Blender [O] |
|---|---|---|---|
| `position` | POINT | `float32 (V,3)` | `position` FLOAT_VECTOR |
| `.edge_verts` | EDGE | `int32 (E,2)` | `.edge_verts` INT32_2D |
| `face_offsets` (not an attribute) | — | `int32 (F+1,)` | `loop_start` / `loop_total` |
| `.corner_vert`, `.corner_edge` | CORNER | `int32 (C,)` | same |
| `sharp_face`, `material_index` | FACE | `bool`, `int32` | same |
| `.select_vert/.select_edge/.select_poly`, `.hide_*` | various | `bool` | same |
| UV (`UVMap`…) | CORNER | `float32 (C,2)` (FLOAT2) | `uv_layers` |

Attribute types → dtype: `FLOAT f4`, `INT i4`, `FLOAT_VECTOR f4×3`, `FLOAT_COLOR f4×4`,
`BYTE_COLOR u1×4`, `BOOLEAN ?`, `FLOAT2 f4×2`, `INT8 i1`, `INT16_2D i2×2`, `INT32_2D i4×2`,
`QUATERNION f4×4`, `FLOAT4X4 f4×4×4`, `STRING` (Python list). Geometry stays in `float32` as in
Blender; math and transforms in `float64` (§5.9).

Rules:

- **Arrays immutable by convention, copy-on-write**: `attr.data` returns a read-only view;
  writing via `attr.set(values)`, `attr.writable()` or `foreach_set` — this allows cheap undo
  (the journal keeps the old array, not a copy) and mesh copies sharing arrays.
- RNA views (`mesh_views.py`): `MeshVertices/MeshEdges/MeshLoops/MeshPolygons/MeshLoopTriangles`
  with `add(n)`, `foreach_get/foreach_set`, indexing; elements `MeshVertex/MeshEdge/MeshLoop/
  MeshPolygon` are **row structs** whose params are `COLUMN`/`VIRTUAL`.
  `MeshPolygon.loop_start ↔ face_offsets[:-1]`; `loop_total` derived.
- `from_pydata(vertices, edges, faces, shade_flat=True)` with the same observed result
  (quad → 4 v / 4 e / 4 loops / 1 face, edges recalculated) [O]; `update(calc_edges=False,
  calc_edges_loose=False)`, `validate(verbose=False, clean_customdata=True) -> bool`,
  `transform(matrix)`, `clear_geometry()`, `calc_loop_triangles()`, lazy normals
  (`vertex_normals`, `polygon_normals`, `corner_normals`) cached by the `GEOMETRY` counter.
- **Edit mode = `EditMesh`** (Layer 1, `quartz.geometry.editmesh`): object topology
  (`EVert/EEdge/EFace/ELoop`) with the shape of `bmesh`; the shim's `bmesh` is a re-export of it (§7.5).
  Conversions `EditMesh.from_mesh_data()` / `to_mesh_data()`. A mesh in edit mode is marked
  `is_editmode`; `update_from_editmode()` synchronizes.

### 5.4 Other data-blocks

| Type | Main params (defaults come from the dump and are checked by a parity test) | Notes |
|---|---|---|
| `Material` | `diffuse_color`, `metallic`, `roughness`, `specular_intensity`, `blend_method`, `use_backface_culling`, `pass_index`, `use_nodes`, `node_tree` (`None`) | slots + `material_index` are canonical (c4d_model §14) |
| `Camera` | `type`, `lens`, `lens_unit`, `sensor_width/height/fit`, `clip_start/end`, `ortho_scale`, `shift_x/y`, `angle*` (VIRTUAL), `dof` (struct) | |
| `Light` + `PointLight/SunLight/SpotLight/AreaLight` | `type`, `color`, `energy`, `use_shadow`, factors; per subtype `shadow_soft_size`, `angle`, `spot_size/blend`, `shape/size/size_y` | `lights.new(name, type)` instantiates the subclass; `light.type = 'SUN'` swaps `__class__` [M] and the missing params go to orphans |
| `World` | `color`, `use_nodes`, `node_tree` | |
| `Collection` | `objects` (`link/unlink`), `children` (`link/unlink`), `all_objects` (VIRTUAL), `hide_viewport/render/select`, `color_tag`, `instance_offset` | C4D layers ≈ `color_tag` + flags |
| `Scene` | `camera`, `world`, `frame_start/end/current/step`, `render` (`RenderSettings`), `unit_settings`, `tool_settings`, `cursor`, `collection` (master, embedded), `view_layers`, `objects` (VIRTUAL), `frame_set(frame, subframe=0.0)` | `frame_set` fires `frame_change_pre/post (scene, depsgraph)` [O] |
| `ViewLayer` | `objects` (`LayerObjects` with `.active`, `.selected`), `layer_collection`, `active_layer_collection`, `update()`, `depsgraph` | |
| `Image` | `size`, `pixels` (numpy `float32`), `filepath`, `colorspace_settings` (stub), `generated_*` | no file decoding in this milestone |
| `Text` | `as_string()`, `from_string()`, `lines` | used by `ui_translate` and templates |
| `Generator` | see §5.5 | Quartz extension |
| `WindowManager`, `Screen`, `WorkSpace` | see §6.3 | IDs as in Blender |

### 5.5 Generator, Tag and Modifier: "fixed host + registered class"

C4D couples plugin data classes to a host node (c4d_model §2). In Python this becomes the
`register_class` model of bpy: **the core knows only the base; each concrete type is a subclass
registered by `bl_idname`** and the core instantiates it by name (just as `lights.new(name, type)` returns
`PointLight`). `isinstance` and the RNA name work naturally.

```python
class Generator(ID):                         # parametric data-block in quartz.data.generators
    q_output: ClassVar[str] = "MESH"         # MESH | CURVE | INSTANCES
    q_consumes_children: ClassVar[bool] = False   # OBJECT_INPUT from C4D
    q_stage: ClassVar[str] = "GENERATOR"
    def evaluate(self, ctx: EvalContext) -> GeometrySet: ...

class Tag(Struct):                           # behavior component, in Object.tags
    q_flags: ClassVar[frozenset[str]] = frozenset()   # MULTIPLE, HIERARCHICAL, EXPRESSION
    q_stage: ClassVar[str] = "EXPRESSION"
    q_priority: ClassVar[int] = 0
    @classmethod
    def poll(cls, obj: Object) -> bool: ...
    def execute(self, ctx: EvalContext, obj: Object) -> None: ...

class Modifier(Struct):                      # canonical stack Object.modifiers (bpy form)
    show_viewport: BoolProperty(default=True)
    show_render: BoolProperty(default=True)
    def evaluate(self, ctx: EvalContext, geometry: GeometrySet) -> GeometrySet: ...
```

- Usage: `gen = quartz.data.generators.new("Cube", kind="QZ_GEN_CUBE")`;
  `ob = quartz.data.objects.new("Cube", gen)`; `gen.size = (1, 1, 1)`;
  `ob.evaluated_get(dg).data` is a runtime `Mesh` (`is_runtime_data=True`, read-only);
  `ob.to_mesh()` works for any evaluable type. `object.convert(target='MESH')` collapses.
- Tags are **behavior only** (expressions, protection, display, script in the future); geometry never
  lives in tags — UVs, selections and weight maps are attributes (c4d_model §5, §15.4).
- Deformer-as-child (C4D) is deferred; when it arrives, it is sugar translated into an implicit modifier
  on the parent, in the order of the children.
- Built-ins of this milestone (small, to prove the pipeline): generators `QZ_GEN_CUBE`,
  `QZ_GEN_UV_SPHERE`, `QZ_GEN_ARRAY` (consumes children); tag `QZ_TAG_PROTECTION` (locks transform)
  and `QZ_TAG_LOOKAT` (points at a target, EXPRESSION stage); modifiers `ARRAY` and `TRIANGULATE`.

### 5.6 Per-channel dirtiness, depsgraph and staged evaluation

- Each ID has `DirtyCounters` (one integer per channel). The values come from a monotonic global
  clock, so "stamps" (`stamp()` → tuple) are comparable across IDs. `ParamSpec.dirty`
  says which channel to bump; `MeshData.revision` feeds `GEOMETRY`; links/parenting bump `CHILDREN`.
- `Depsgraph(scene, view_layer)`: `update()` compares stored stamps with the current ones and builds
  `updates` (`DepsgraphUpdate(id, is_updated_geometry, is_updated_transform, is_updated_shading)`),
  fires `depsgraph_update_pre/post (scene, depsgraph)` [O]. `objects`, `object_instances`,
  `ids`, `id_eval_get`, `scene_eval`, `view_layer_eval`; `ID.evaluated_get(dg)`.
- Evaluation in **named stages** (replaces C4D's numeric priorities):
  `INITIAL → ANIMATION → DRIVERS → EXPRESSION → DYNAMICS → GENERATOR → DEFORM → FINAL`; within a
  stage, `q_priority` and then hierarchy order. In this milestone only `EXPRESSION` (tags),
  `GENERATOR` (generators + modifiers) and `FINAL` do anything.
- Per-object cache: generator cache + deformation cache (c4d_model §7), keyed by the tuple of
  dependency stamps. Objects without a generator/modifier evaluate to their own mesh
  (shared, read-only).

### 5.7 Factory scene

`quartz.factory.build_factory_scene(main)` reproduces the observed **facts** [O, contract §7.2]:
Scene "Scene"; collection "Collection"; Camera (loc ≈ 7.3589, −6.9258, 4.9583), Cube (8 v / 12 e /
6 f / 24 loops, UV "UVMap"), Light (loc ≈ 4.0762, 1.0055, 5.9039); materials "Material" and
"Dots Stroke"; World "World"; frames 1–250, frame 1; engine `BLENDER_EEVEE`; units `METRIC`; Cube
active and selected. Rotations and camera/light data come from the dump. `build_empty(main)` gives an
empty scene (equivalent to `use_empty=True`).

### 5.8 Session and global registry

- **One `TypeRegistry` per process** (Python classes are global; registering installs descriptors on the
  class). **`Main`, context, undo, handlers and timers per `Session`**. Tests isolate with
  `registry.snapshot()/restore()` + a new session.
- `quartz.session()` returns the current session; `quartz.data` and `quartz.context` are resolved by
  module `__getattr__` (PEP 562), which also allows swapping them for restricted versions during
  add-on registration (§8).

### 5.9 Math (`quartz.math`)

- `Vector`, `Quaternion`, `Euler`, `Color`: list of `float64` floats with `__slots__` (faster
  than numpy for size ≤ 4 [M]); `Matrix`: `np.ndarray (r,c) float64` (4× faster in
  matmul [M]; `decompose`/`inverted` use `numpy.linalg`).
- **"Wrapped" values** (`is_wrapped`, `owner`): `ob.location` returns a `Vector` bound to the
  owner through a minimal `ArrayOwner` protocol (`_q_read/_q_write/_q_valid`) defined in
  `quartz.math._owner` — Layer 1 does not know `ParamStore`; Layer 2 implements the protocol.
  `Matrix.row/col/translation` also wrap. `copy()` and `freeze()` as in mathutils.
- Declared divergence: Blender's mathutils works in single precision [I]; Quartz in
  double. Golden tests use a relative tolerance of `1e-5`.
- `quartz.math.batch` (Quartz only): `transform_points`, `compose_trs`, `normalize_rows`,
  `euler_to_matrices` over `(N,…)` arrays — for generators, exporters and future effectors.

---

## 6. Registry, operators, context, undo, handlers, UI

### 6.1 `TypeRegistry` and `KindSpec` (data table)

The registry is driven by a `KIND_SPECS` table; each `KindSpec` has a **class description**
(the `bl_*` are params of a class `Description`, validated by the same coercion: enums of
`bl_options`, `bl_space_type`, `bl_region_type`, `maxlen` of the idname…).

| Kind | Required [O] | idname / RNA name rule | Extra |
|---|---|---|---|
| `OPERATOR` | `bl_idname`, `bl_label` | `mod.name`, 1 dot, `[a-z0-9_]`, ≤ 60 → RNA `MOD_OT_name` [O] | `bl_options` ⊂ {REGISTER, UNDO, UNDO_GROUPED, BLOCKING, MACRO, GRAB_CURSOR*, DEPENDS_ON_CURSOR, PRESET, INTERNAL, MODAL_PRIORITY} |
| `PANEL` | `bl_label`, `bl_space_type`, `bl_region_type`, `draw` | `bl_idname` or class name; without `_PT_` only a warning [O] | nonexistent `bl_parent_id` → `RuntimeError` [O] |
| `MENU` | `bl_label`, `draw` | same `_MT_` | |
| `HEADER` | `bl_space_type`, `draw` | same `_HT_` | `bl_region_type` default `HEADER` |
| `UILIST` | — | same `_UL_` | |
| `PROPERTY_GROUP`, `ADDON_PREFERENCES` | — | class name; prefs: `bl_idname` = module | |
| `FILE_HANDLER` | `bl_idname`, `bl_label` [I] | | `bl_import_operator`, `bl_file_extensions`, `poll_drop` |
| `GENERATOR`, `TAG`, `MODIFIER` | `bl_idname`, `bl_label` | `bl_idname` free-form in uppercase (`QZ_GEN_CUBE`) | `q_*` |
| `GIZMO_GROUP`, `GIZMO`, `WORKSPACE_TOOL`, `ASSET_SHELF`, `RENDER_ENGINE`, `KEYING_SET_INFO`, `NODE*` | as in Blender [I] | | **stubs**: they register, never execute (no viewport/render) |

Registration rules (contract §2.1 [O]) and decisions:

- same class twice → `ValueError`; unregistering an unregistered one → `RuntimeError`; another class
  with the same `bl_idname` replaces the previous one (with an Info message);
- `PointerProperty/CollectionProperty(type=X)` requires `X` to be already registered (or an ID type) → `ValueError`;
- **atomic registration**: if any step fails, nothing stays installed (Blender may leave things half
  registered [O]); declared divergence, because no add-on depends on the broken state;
- **owner scope** (`registry.owner_scope(module_name)`): every class registered during an
  add-on's `register()` is attributed to it; after `unregister()`, whatever remains is a **leak**
  that gets reported (Blender does not detect it);
- the RNA name appears in `quartz.types.<RNA>` (and in the shim's `bpy.types`) via module `__getattr__`.

### 6.2 Operators

`quartz.types.Operator(Struct)`: class attributes `bl_*`; instance with `properties`
(`OperatorProperties`, same description), `report(type, message)`, `poll_message_set(msg)`,
`as_keywords(ignore=())`, `layout`, `options`, `has_reports`. `self.<prop>` is redirected to
`self.properties` by the descriptors [O].

`quartz.ops` (and the shim's `bpy.ops`, with a different message prefix) is a synthesized namespace:
`quartz.ops.<sub>.<op>` → `OperatorCallable` with `__call__`, `poll()`, `idname()`
(`MESH_OT_primitive_cube_add`), `idname_py()`, `get_rna_type()`, `bl_options` [O].

Sequence of `call_operator(op_cls, exec_context, undo, properties, event=None)`:

1. positional args: ≤ 2 (`str` for execution context, `bool` for undo); `dict` → `ValueError` [O];
2. instantiates; applies kwargs through coercion (§4.7) — unknown/wrong type → `TypeError`, out
   of range clamps [O]; values **do not persist** between calls [O];
3. `poll` false → `OperatorPollError(RuntimeError)` with the text from `poll_message_set` [O];
4. `INVOKE_*` without an event (headless) → goes straight to `execute` [O]; native accepts a synthetic
   `event=` to test `invoke`/`modal` (`quartz.types.Event`);
5. `execute` returns a set ⊂ {RUNNING_MODAL, CANCELLED, FINISHED, PASS_THROUGH, INTERFACE};
   any other value, `None` or an exception → `OperatorError(RuntimeError)` with `__cause__` = original exception [O];
6. `report({'ERROR'})` + `CANCELLED` → `OperatorError("Error: …")`; INFO/WARNING go to
   `ReportList` and stdout [O];
7. `FINISHED` + `UNDO` in `bl_options` → `undo.push(bl_label)`; `REGISTER` → stores in
   `window_manager.operators` (last operator);
8. `RUNNING_MODAL` → `window_manager.modal_handler_add` stores; `quartz.app.events.feed(events)`
   (Quartz only) delivers synthetic events to `modal`.

Layer 2 built-ins (real effect on the model; selection guided by bpy_usage §2/§9 and contract §13.2):

- `object.mode_set(mode, toggle=False)`, `object.select_all(action)`, `object.delete(use_global,
  confirm)`, `object.duplicate(linked, mode)`, `object.transform_apply(location, rotation, scale,
  properties, isolate_users)`, `object.shade_smooth/shade_flat`, `object.parent_set/parent_clear`,
  `object.add/empty_add/camera_add/light_add`, `object.convert(target)`;
- `mesh.primitive_{cube,plane,grid,circle,uv_sphere,ico_sphere,cylinder,cone,torus}_add` with the
  kwargs/defaults from the dump (`size`, `location`, `rotation`, `align`, `enter_editmode`, …);
  `primitive_monkey_add` is **not** included — the mesh is Blender data; it stays `QuartzNotImplementedError`;
- `mesh.select_all`; `transform.translate/rotate/resize` with `value=` (object and edit mode);
- `ed.undo`, `ed.redo`, `ed.undo_push(message)`; `wm.read_factory_settings(use_empty)`,
  `wm.read_homefile`, `wm.open_mainfile(filepath)`, `wm.save_as_mainfile(filepath, copy)`,
  `wm.save_mainfile`, `wm.call_menu(name)` (headless: records and returns FINISHED [I]);
- Quartz natives: `object.generator_add(kind)`, `object.tag_add(type)`, `object.make_editable()`.

### 6.3 Context

- `Context(Struct)` with **table-driven** members: `CONTEXT_MEMBERS: dict[str,
  Resolver]`; the list of 75 observed names [O] becomes data. Non-null in headless: `window,
  screen, workspace, window_manager, preferences, blend_data, scene, view_layer, collection,
  layer_collection, active_object/object, selected_objects, selected_editable_objects,
  selectable_objects, visible_objects, editable_objects, objects_in_mode*, tool_settings, engine,
  mode, asset_library_reference`; null: `area, region, region_data, space_data, edit_object` (outside
  edit mode), `active_bone`, … [O].
- Read-only members (`AttributeError`) [O]; `temp_override(**members)` pushes a frame and
  restores on exit, accepting unknown keys without exposing them [O]; `copy()`, `path_resolve()`,
  `evaluated_depsgraph_get()`.
- `WindowManager` (ID): `windows`, `keyconfigs` (`addon/user/default/active`, keymaps are data only [O]),
  `operators`, `modal_handler_add`, `fileselect_add` (records the request), `invoke_props_dialog`/
  `invoke_confirm` (headless: executes directly [I]), `progress_begin/update/end` (no-op),
  `popup_menu` (records), `clipboard`.
- **Synthetic context for drawing** (Quartz only, used by the sweep): `quartz.ui.draw.synthetic_area(
  space_type)` provides fake `area/region/space_data` so that panels with
  `bl_space_type='VIEW_3D'` can be drawn in the recorder.

### 6.4 Undo: transaction journal

- Single mutation points record `Change`s: `ParamStore.write` (`ParamChange`), replacement of a
  COW array (`ArrayChange` with the old array), ID creation/removal (`IDCreate`/`IDRemove` with a
  "graveyard" for revival), collection links, parenting, mode switching.
- `UndoStack`: starts **disabled in background**, as in Blender; `ed.undo_push` (or
  `undo.enable()`) enables it [O]. `push(message)` closes the current transaction into an `UndoStep`; `undo()`/
  `redo()` apply the `Change`s in reverse/forward order and fire `undo_pre/post`, `redo_pre/post`.
  Default `step_limit` is 32 [I].
- `with quartz.undo.transaction("Move"):` groups changes (the C4D graph "transaction", c4d_model §12);
  `Transaction.rollback()` exists in the native API; in operators, automatic rollback on error is an **option**
  (`quartz.app.settings.rollback_on_operator_error`, disabled in compat mode for fidelity).
- Edit mode: entering/leaving is one step; inside edit mode, a snapshot of the `EditMesh` per step (simple
  and correct; optimize later).

### 6.5 Handlers, timers, msgbus

- `HandlerLists`: Blender's 39 lists [O] + Quartz's own (`startup_post`, `shutdown_pre`,
  `shutdown_post`, `addon_enable_post`, `addon_disable_post`, `description_changed`) — phased
  shutdown from C4D (c4d_model §8). `persistent(fn)` marks `fn._bpy_persistent = True` [L]; loading a
  file removes the non-persistent ones. `dispatch(name, *args)` isolates exceptions per callback
  (prints and continues [I]). Signatures `(scene, depsgraph)` where observed [O]; `load_pre/post` and
  `save_pre/post` to be confirmed by golden [I].
- `TimerQueue.register(fn, first_interval=0.0, persistent=False)`, `unregister`, `is_registered`,
  manual `pump(now=None)` — headless does not fire on its own, as observed [O].
- `MsgBus.subscribe_rna/publish_rna/clear_by_owner` record; `flush()` (Quartz only) delivers — faithful to the
  observed "zero synchronous notifications" [O].

### 6.6 GUI-less UI: recorder and auto-layout

- `quartz.ui.layout.UILayout` is a **recorder**: the 41 members seen in the corpus (bpy_usage §6:
  `prop` 890 refs, `label`, `operator`, `column`, `row`, `separator`, `split`, `panel`, `box`,
  `menu`, `template_list`, `prop_search`, `use_property_split`, `active`, `enabled`, …) have an
  explicit signature; any other name is accepted via `__getattr__`, recorded as `unknown` and
  returns a sub-layout (tolerance needed for the long tail).
- `layout.prop(data, "x")` **validates against the description** of `data`: if `x` does not exist, it records a
  `LayoutIssue('PROPERTY_NOT_FOUND', 'Scene.x')` (Blender only prints and continues [I]). This is the automatic
  detector for "a property the add-on expects on a built-in type that Quartz does not
  have yet".
- `layout.operator("mod.op")` returns an `OperatorProperties` of the operator (if registered), which
  validates assignments against the description; otherwise, a recorder.
- `Menu/Panel/Header/UIList` inherit `DrawExtensionMixin` with real `append/prepend/remove/is_extended`
  (wrapped draw, per-function isolated exceptions, silent `remove`) [O, contract §11].
- `quartz.ui.auto_layout(layout, struct, groups=None)` draws any struct from its description
  (groups, `parent` as indentation, `enabled_if`) — the "automatic UI" that C4D derives from
  descriptions; applies to native generators/tags/modifiers without `draw()`.
- `quartz.ui.draw.draw_class(cls, context) -> UILayout` runs `poll` + `draw` with the recorder and
  returns the tree (`to_dict()`), used by snapshot tests and by the sweep.

### 6.7 Error hierarchy

Every native exception **inherits from the built-in exception that Blender raises** — compatibility for free
in the shim, rich types in the native API:

```
QuartzError(Exception)
AlreadyRegisteredError(QuartzError, ValueError)     PropertyDefinitionError(QuartzError, ValueError)
NotRegisteredError(QuartzError, RuntimeError)       OperatorPollError(QuartzError, RuntimeError)
OperatorError(QuartzError, RuntimeError)            ContextReadOnlyError(QuartzError, AttributeError)
ReadOnlyPropertyError(QuartzError, AttributeError)  StructRemovedError(QuartzError, ReferenceError)
LinkError(QuartzError, RuntimeError)                QuartzNotImplementedError(QuartzError, NotImplementedError)
```

Messages are Quartz's own (paraphrased); differential tests compare **type**, never text.
`QuartzNotImplementedError` always cites the symbol (`"bpy.types.Object.shape_key_add"`), so that the
sweep can count it.

---

## 7. Compat layer (Path A): how `bpy` relies on `quartz`

### 7.1 Activation

```python
state = quartz.compat.activate(target=(5, 2, 2), strict=True, restrict_register=True)
import bpy, mathutils, bmesh                     # resolved in <root>/compat
quartz.compat.deactivate(purge_modules=True)     # removes from sys.path and purges bpy*, mathutils*, …
```

`activate` inserts `<root>/compat` at the start of `sys.path` (idempotent), creates the `CompatState` in the
session and prepares `sys.modules` for `bpy.types`, `bpy.app`, `bpy.app.handlers`,
`bpy.app.translations` [L]. Importing `bpy` with the directory on the path calls `ensure_active()` (the
manual path also works).

### 7.2 Four forms of adaptation (and no other)

| Form | What it is | Examples |
|---|---|---|
| **IDENTITY** | the same object from `quartz` | `bpy.types.Operator is quartz.types.Operator`; `mathutils.Vector is quartz.math.Vector`; `bpy.data`/`bpy.context` are the session's; lists in `bpy.app.handlers`; `bpy.utils.register_class` |
| **FILTER** | a wrapper that restricts signature/values to the Blender contract and delegates | `bpy.props.*` (rejects Quartz kwargs such as `group=`; `type=` must be a class), `bpy.ops` (message prefix `bpy.ops`), `addon_utils.enable(...)` |
| **VIEW** | projection of names over the registry/tables | module `bpy.types` (registered by RNA name + built-ins + UI placeholders), `bpy.app` (struct with `version=(5,2,2)`), namespace `bpy.ops` |
| **STUB** | accepts and records, or fails explicitly | `gpu`, `gpu_extras`, `blf`, `bpy.utils.previews`, `bpy.msgbus`, `bpy.app.timers` (pump), keymaps, `register_tool`, `RenderEngine` |

### 7.3 Mapping table (core of the milestone)

| bpy symbol (tier) | Maps to | Form |
|---|---|---|
| `bpy.props.*` (T1) | `quartz.props.*` | FILTER |
| `bpy.types.Operator/Panel/Menu/Header/UIList/PropertyGroup/AddonPreferences` (T1/T2) | `quartz.types.*` | IDENTITY |
| `bpy.types.ID/Object/Mesh/Material/Camera/Light/Collection/Scene/World/Image/Text/ViewLayer/WindowManager/Context/Event` | `quartz.types.*` | IDENTITY |
| `bpy.types.BlendData`, `bpy_struct`, `bpy_prop_collection` | `quartz.core.main.Main`, `quartz.core.struct.Struct`, `quartz.props.collection.PropCollection` | VIEW (aliases) |
| `bpy.types.<REGISTERED_RNA_NAME>` (`QUARTZ_PROBE_OT_hello`) | `REGISTRY.get(name).cls` | VIEW |
| `bpy.types.VIEW3D_MT_mesh_add`, `TOPBAR_MT_file_import`, … (≈1977 UI names [O]) | empty subclasses of Menu/Panel/Header/UIList generated on demand from `quartz/compat/ui_names.json` | VIEW |
| `bpy.utils.register_class/unregister_class/register_classes_factory/register_submodule_factory` (T1) | `quartz.utils.*` | IDENTITY |
| `bpy.utils.escape_identifier/user_resource/extension_path_user/execfile/units/previews` | `quartz.utils.*` | IDENTITY / STUB (`previews`) |
| `bpy.path.*` | `quartz.path.*` | IDENTITY |
| `bpy.ops.<sub>.<op>` | `quartz.ops.namespace.OpsNamespace(prefix="bpy.ops")` | VIEW |
| `bpy.data.*` | `session.main` (or `RestrictedData` during registration) | IDENTITY |
| `bpy.context.*` | `session.context` (or `RestrictedContext`) | IDENTITY |
| `bpy.app.version/version_string/version_file/background/binary_path/tempdir/debug*` | `CompatState.target` + `quartz.app` | VIEW |
| `bpy.app.handlers.*` + `persistent` | lists in `session.handlers` (only the 39 Blender names) | IDENTITY |
| `bpy.app.translations.pgettext*`, `contexts`, `register/unregister` (T1) | `quartz.app.translations` (text identity) | IDENTITY |
| `bpy.app.timers` | `session.timers` | STUB (manual pump) |
| `bpy.msgbus` | `session.msgbus` | STUB (manual flush) |
| `mathutils.Vector/Matrix/Quaternion/Euler/Color` (T1/T2) | `quartz.math.*` | IDENTITY |
| `mathutils.geometry/kdtree/bvhtree/interpolate` (T3) | `quartz.math.*` | IDENTITY (subset) |
| `mathutils.noise` | `quartz.math.noise` | STUB (same API, values **not** the same) |
| `bmesh.new/from_edit_mesh/update_edit_mesh/types/ops` (T2/T3) | `quartz.geometry.editmesh` / `edit_ops` + `Mesh` adapter | IDENTITY + thin FILTER |
| `bpy_extras.io_utils.*`, `object_utils.*` (T2/T3) | `quartz.extras.*` | IDENTITY |
| `bpy_extras.anim_utils/view3d_utils/node_utils/image_utils/asset_utils` | `quartz.extras.*` | STUB / subset |
| `addon_utils.*` | `session.addons` (`quartz.addons.manager.AddonManager`) | FILTER |
| `rna_prop_ui.rna_idprop_ui_create` etc. | `quartz.core.custom_props` | IDENTITY |
| `idprop.types.IDPropertyGroup/IDPropertyArray` | `quartz.core.custom_props` | IDENTITY |
| `bl_ui.utils.PresetPanel`, `bl_operators.presets.AddPresetBase` | minimal original mixins in `quartz.compat.helpers` | IDENTITY (functional stub) |
| `gpu.*`, `gpu_extras.*`, `blf.*` | — | STUB: state functions are no-ops; creating a shader/batch raises `QuartzNotImplementedError("no GPU")` |

### 7.4 `bpy.types` as a view

`compat/bpy/types.py` defines `__getattr__(name)`: (1) registry (RNA name), (2) built-ins of
`quartz.types` and aliases from `mapping.BPY_TYPE_ALIASES`, (3) UI placeholder if `name ∈
ui_names.json` (created once, registered as a built-in and not unregisterable), (4) otherwise
`AttributeError`. `dir()` lists everything. Extension `bpy.types.Scene.x = …` works because
`bpy.types.Scene is quartz.types.Scene` (metaclass, §4.8).

### 7.5 `mathutils`, `bmesh`, `bpy_extras`

- `mathutils`: pure re-export; the `BVHTree.FromObject(object, depsgraph, …)` adapter is injected
  by Layer 2 into `quartz.math.bvhtree` (same technique as §4.11).
- `bmesh`: `bmesh.types.BMesh is quartz.geometry.editmesh.EditMesh`, `BMVert is EVert`, …; method
  names are already those of bmesh (`verts.new`, `ensure_lookup_table`, `from_mesh`, `to_mesh`,
  `free`); `from_mesh(me)` accepts any object with `q_meshdata` (protocol, no import of Layer
  2). `bmesh.ops`: `triangulate`, `remove_doubles`, `recalc_face_normals`, `delete`,
  `create_cube/uvsphere/icosphere/circle/cone/grid`, `translate/rotate/scale/transform`,
  `reverse_faces` (the rest → `QuartzNotImplementedError`).
- `bpy_extras.io_utils.ImportHelper/ExportHelper`: original mixins with `filepath`,
  `filter_glob`, `check_existing` annotated; `invoke` calls `fileselect_add` (which in headless never
  runs, because `INVOKE_DEFAULT` falls back to `execute` [O]); `orientation_helper`, `axis_conversion`.
  `object_utils.AddObjectHelper` (`align/location/rotation` + `poll`) and `object_data_add` [L].

### 7.6 Name collisions between Quartz extensions and add-ons

Built-in types gain members that Blender does not have (`Object.tags`, `Object.reorder`,
`Main.generators`…). Rule: every member with `origin="quartz"` has **two names** — the short one
(`tags`) and a permanent prefixed alias (`q_tags`). If an add-on defines
`bpy.types.Object.tags = CollectionProperty(...)`, **the add-on wins** (the short name becomes
the add-on's, with a warning) and Quartz remains accessible via `q_tags`. Quartz class attributes on
registrable classes always use the `q_` prefix (`q_groups`, `q_schema_version`, `q_stage`).

### 7.7 Deliberate divergences (go into `docs/COMPAT.md`)

1. Atomic registration (no half-registered class).
2. Registration leaks detected and reported.
3. Double precision in `mathutils` (tolerance in the goldens).
4. `Object.type == 'GENERATOR'` exists.
5. String annotations and forward references accepted (Python 3.14).
6. `.blend` is neither read nor written: `wm.save_as_mainfile` writes Quartz `.qz` format (warns if the
   extension is `.blend`); `wm.open_mainfile` of a `.blend` → clear error.
7. `mathutils.noise` with its own values; `primitive_monkey_add` absent.
8. Paraphrased error messages.
9. `layout.prop` validation records structured issues instead of only printing.

### 7.8 Thinness rule, verified

`tests/compat/test_thin_shims.py` checks by AST that the modules in `compat/` (except declared stubs):
do not import `numpy`, do not define classes with more than N own methods, and only
import `quartz`, stdlib and other shims. If a shim needs logic, it moves up into `quartz`.

---

## 8. Add-on and extension loader (`quartz.addons`)

Three package formats:

| Format | Detected by | Module name | Requires compat |
|---|---|---|---|
| legacy add-on (`.py` file or package) | `bl_info` | file/folder name | yes |
| Blender extension | `blender_manifest.toml` | `bl_ext.<repo>.<id>` [O] | yes |
| Quartz extension | `quartz_manifest.toml` (same schema; `quartz_version_min` in place of `blender_version_min`) | `qz_ext.<repo>.<id>` | no |

Components:

- `blinfo.read_bl_info(path, fast=True)`: reads UTF-8 without importing; from the first line that **starts with**
  `bl_info` to the first blank line; `ast.parse` + `ast.literal_eval` [L, contract §5.1].
  `normalize_bl_info(info, module_name)`: defaults (`name, author, version, blender, location,
  description, doc_url, support='COMMUNITY', category, warning, show_expanded=False`), removes
  emails from `author` [O].
- `manifest.read_manifest(path)` with `tomllib`; `validate_manifest(data, strict=True)`: required
  `schema_version, id, name, tagline, version, type, maintainer, license(list),
  blender_version_min`; `type ∈ {add-on, theme}`; `id` is an identifier with no `__` and no `_` at the ends;
  `[build]` with `paths` **or** `paths_exclude_pattern` [L]; `wheels` and `permissions` → warning
  "not supported in this milestone". `synthesize_bl_info(m)` reproduces Blender's mapping
  (`name←name`, `version←version`, `blender←blender_version_min`, `description←tagline`,
  `author←maintainer`, `category='Development'`) [L]; the extension's own `bl_info` is deleted after
  import [L].
- `discovery.scan_paths(paths)`: `module_names` semantics (`*.py` except `__init__`, non-hidden folders
  with `__init__.py`, ignores `modules`) [L]; extension repositories generate synthetic `bl_ext`
  packages (`types.ModuleType` with `__path__ = [repo_dir]`).
- `manager.AddonManager.enable(name, *, default_set=False, persistent=False, refresh_handled=False,
  handle_error=None, lenient=False)`, in the order of the contract [L/O]: (1) if already enabled,
  `unregister()`; reload if the mtime changed; (2) `default_set` creates the entry in
  `preferences.addons` **before** the import; (3) **import + `register()` inside
  `restricted(session)`**: `bpy.context` with only `window_manager` and `preferences`, empty `bpy.data`
  that raises `AttributeError` (`lenient=True` turns this off, for diagnostics); (4) everything
  inside `registry.owner_scope(name)`; (5) failure → `handle_error(ex)`, removes from `sys.modules`,
  undoes `default_set`, returns `None`; missing module → `ModuleNotFoundError` [O]; (6) success →
  `__addon_enabled__ = True`, `__addon_persistent__ = persistent`, creates the instance of
  `AddonPreferences` whose `bl_idname` == name [O], fires `addon_enable_post`, returns the module.
- `disable(...)`: clears flags, `unregister()` (error reported, not propagated), optionally removes from
  `preferences.addons`, **keeps it in `sys.modules`** [O]; computes leaks.
  `check(name) -> (loaded_default, loaded_state)` [O]; `modules(refresh)`, `module_bl_info`,
  `disable_all`, `reset_all`, `check_extension`.
- `AddonReport`: status (`ENABLED, NOT_FOUND, INVALID_METADATA, IMPORT_FAILED, REGISTER_FAILED,
  DRAW_FAILED, UNREGISTER_FAILED`), error + traceback, **missing symbols** (extracted from
  `AttributeError`/`QuartzNotImplementedError`), registered classes, leaks, ignored prop
  assignments, layout issues, warnings, time.
- Security: add-ons execute arbitrary code. The loader runs only what the user points to; the sweep
  runs each add-on in a **subprocess** with a timeout (clean global state and `sys.modules`, a failure does not
  bring down the parent process).

---

## 9. CLI (`python -m quartz`)

```
python -m quartz info [--json]
python -m quartz scan-addon PATH [--json] [--coverage]
python -m quartz enable-addon NAME_OR_PATH [--path DIR]... [--repo NAME=DIR]... [--lenient]
                                              [--draw] [--synthetic-areas] [--keep] [--json]
python -m quartz run-script FILE.py [--no-compat] [--empty] [--open X.qz] [--save Y.qz] [-- ARGS...]
python -m quartz addon-sweep [--root DIR]... [--templates DIR] [--timeout 60] [--no-draw]
                             [--filter GLOB] [--json OUT] [--md OUT]
python -m quartz describe TYPE [--json] [--flavor quartz|bpy]
python -m quartz dump-api [--flavor quartz|bpy] [--out FILE.json]
```

| Command | Does | Output |
|---|---|---|
| `info` | versions (Quartz, Python, numpy, compat target), counts of registered types/operators, paths | text or JSON |
| `scan-addon` | static: `bl_info`/manifest + AST scan of symbols (the core of `tools/scan_bpy_usage.py` becomes `quartz.addons.scan`) cross-referenced with `quartz/compat/coverage.json` → **predicted compatibility** | list of IMPLEMENTED/STUB/MISSING symbols |
| `enable-addon` | enables, lists classes, optionally draws panels/menus in the recorder, disables, reports | `AddonReport` |
| `run-script` | runs as `__main__` with compat active (like `blender --background --python`); `sys.argv` after `--` | script stdout; exit code |
| `addon-sweep` | for each candidate: subprocess `enable-addon --draw --json` with timeout; templates via `run-script` | aggregated MD table + JSON |
| `describe` | prints the description of a type (groups, params, metadata) | text/JSON |
| `dump-api` | dump of the descriptions in the **`blender_api_dump.json` schema** | JSON for parity |

Exit codes: `0` success, `1` operation failure, `2` usage error, `3` timeout (sweep).
Plain `argparse`; human output in pt-BR, JSON with English keys.

To make `python -m quartz` usable outside the root: `tools/dev_setup.py` writes
`.venv/Lib/site-packages/quartz_dev.pth` with the root path (writes only inside the project);
alternative that does not touch the venv: run from the root.

---

## 10. `.qz` persistence (description-driven)

- Zip file (stdlib `zipfile`): `manifest.json` (`format="quartz"`, `format_version`,
  `quartz_version`, date), `main.json` (IDs by type: `uuid`, `rna_type`, `name`, `schema`,
  `params`, `custom`, `orphans`, `refs`), `arrays/<uuid>/<domain>/<attribute>.npy` (`numpy.save`).
- Params are written by identifier via `codec.encode_value(spec, value)`; pointers as `uuid`;
  `SKIP_SAVE`/`VIRTUAL`/`COLUMN` are left out. On read, `q_upgrade(params, from_version)` chained up to
  `q_schema_version` (C4D's `disklevel`); unknown params go to orphans (lossless
  round trip).
- Script-objects (generator/tag with code) are left for later, conditioned on
  `quartz.app.trusted()` (Blender's "auto-run" model).

---

## 11. Testing strategy

```
tests/
  conftest.py                  # fixtures: session (factory), empty_session, registry_guard, bpy (enables/disables compat), golden
  test_headers.py              # docstring 1st line + "# Quartz - author: D1on1n" in every .py
  test_layering.py             # AST: Layer 1 only stdlib/numpy and no cross imports; L2 does not import L3; shims only quartz/stdlib
  test_cleanroom.py            # no third-party license/copyright marker in quartz/ and compat/
  unit/math/  unit/props/  unit/geometry/          # pure Layer 1 (no session)
  core/  types/  ops/  ui/  io/                   # Layer 2
  compat/  addons/  cli/                          # Layer 3
  contract/                    # one test per [O] fact of bpy_contract.md (ids "C2_1_…", "C4_4_…")
  differential/
    harness.py                 # canonical emit(key, value): Vector→rounded list, set→sorted list, exception→{"raises": type}
    blender_entry.py           # runs a scenario inside Blender and writes JSON
    scenarios/sc_*.py          # scenarios written with the bpy API only (math, ids, props, registration, ops, context, mesh, handlers)
    test_differential.py       # runs each scenario in Quartz and compares with data/golden/<scenario>.json
  sweep/test_templates_smoke.py  test_easy_addons.py      # marker "corpus" (reads the Blender directory)
  fixtures/addons/             # original mini add-ons: legacy file, legacy package, extension with manifest, prefs, menus, nested PropertyGroup, ImportHelper
```

1. **Unit tests** per module; Layer 1 without session or registry. Random properties with a fixed
   `numpy.random.default_rng(seed)` (no extra dependencies): matrix inverse,
   Euler↔Quaternion↔Matrix round trip per order, topology invariants (`face_offsets`
   monotonic, every face edge exists), `foreach_get/set` round trip.
2. **Contract**: each [O] fact in `bpy_contract.md` becomes a test named after its section (registration,
   required members, idname, props, clamp, `update` always, enum flag, pointers, ID `keys()`,
   operators, `.NNN` names, users, `ReferenceError`, read-only context,
   `temp_override`, undo disabled, handlers, extensible menus, add-on lifecycle).
3. **Differential vs Blender** (goldens):
   - `tools/run_golden.py` runs `"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
     --background --factory-startup --python tests/differential/blender_entry.py -- <scenario>`
     (timeout per scenario) and writes `data/golden/<scenario>.json` with a version stamp; the goldens
     are versioned — normal pytest **does not need Blender**; the `blender` marker regenerates them.
   - comparison with `rtol=1e-5`, `atol=1e-6`; primitives compared by counts, bounding box and
     set of sorted positions (vertex order may legitimately differ);
   - **`tools/dump_bpy_api.py` itself (our code) is scenario zero**: run it in Quartz via
     `run-script` and compare the `probes` section with the one in `data/blender_api_dump.json`;
   - **description parity**: `dump-api --flavor bpy` vs `blender_api_dump.json` →
     `tools/compat_coverage.py` generates `docs/research/compat_coverage.md` (per type: props present,
     type/subtype/unit/default/limits/items equal); expected divergences listed in
     `tests/compat/expected_divergences.json`.
4. **Add-on sweep**: corpus = 13 `addons_core` + 38 `templates_py` (read-only, run
   in a subprocess) + `tests/fixtures/addons`. For each one: enable → draw all
   registered panels/menus/UILists and all built-in menus it extended (recorder, with and
   without synthetic areas) → disable → leaks. Metrics recorded per run: status, most frequent
   missing symbols (implementation order driven by data), `PROPERTY_NOT_FOUND` per type.
   Milestone goals (not verified, they are goals): `io_curve_svg`, `io_anim_bvh`, `ui_translate` and
   `hydra_storm` with clean enable/disable; ≥ 30 of the 38 templates running without exception (excluding those
   that draw with `gpu`).
5. **Performance (smoke, record only)**: `from_pydata` 1 M vertices, `foreach_get` 1 M, 100 k
   accesses to `ob.location.x`, 10 k `Matrix @ Vector` — numbers saved to JSON to detect
   regressions.

Pytest markers: `slow`, `blender` (skips if the exe does not exist), `corpus` (skips if the Blender
scripts folder does not exist). Default command:
`D:/Claude/reverseEngineering/Quartz/.venv/Scripts/python.exe -m pytest -q -m "not slow and not blender"`.

---

## 12. Implementation order in 3 layers, with public APIs

Convention: signatures in stub style; `...` = body; types `ArrayLike = np.ndarray | Sequence`.
Every class/function listed is public (exported by the package `__init__`).

### 12.1 Layer 1 — foundations with no cross dependencies (parallelizable)

Exit criterion for Layer 1: `test_layering.py` green; unit test coverage of the three packages;
`sc_math_*` goldens matching.

#### `quartz.math`

```python
# _owner.py
class ArrayOwner(Protocol):
    def _q_read(self, key: object) -> Sequence[float]: ...
    def _q_write(self, key: object, values: Sequence[float]) -> None: ...
    def _q_valid(self) -> bool: ...

# vector.py
class Vector:
    __slots__ = ("_v", "_owner", "_key", "_frozen")
    def __init__(self, seq: Iterable[float] = (0.0, 0.0, 0.0)) -> None: ...
    @classmethod
    def Fill(cls, size: int, fill: float = 0.0) -> "Vector": ...
    @classmethod
    def Range(cls, start: int, stop: int | None = None, step: int = 1) -> "Vector": ...
    @classmethod
    def Linspace(cls, start: float, stop: float, size: int) -> "Vector": ...
    @classmethod
    def Repeat(cls, vector: Sequence[float], size: int) -> "Vector": ...
    @classmethod
    def _q_wrap(cls, owner: ArrayOwner, key: object, size: int) -> "Vector": ...
    x: float; y: float; z: float; w: float           # + generated swizzles (xy, xyz, zyx, …)
    length: float; length_squared: float; magnitude: float
    is_wrapped: bool; is_frozen: bool; is_valid: bool; owner: object | None
    def copy(self) -> "Vector": ...
    def freeze(self) -> "Vector": ...
    def to_2d(self) -> "Vector": ...; def to_3d(self) -> "Vector": ...; def to_4d(self) -> "Vector": ...
    def to_tuple(self, precision: int = -1) -> tuple[float, ...]: ...
    def resize(self, size: int) -> None: ...; def resized(self, size: int) -> "Vector": ...
    def resize_2d(self) -> None: ...; def resize_3d(self) -> None: ...; def resize_4d(self) -> None: ...
    def normalize(self) -> None: ...; def normalized(self) -> "Vector": ...; def negate(self) -> None: ...
    def zero(self) -> None: ...
    def dot(self, other: Sequence[float]) -> float: ...
    def cross(self, other: Sequence[float]) -> "Vector | float": ...
    def angle(self, other: Sequence[float], fallback: object = ...) -> float: ...
    def angle_signed(self, other: Sequence[float], fallback: object = ...) -> float: ...
    def lerp(self, other: Sequence[float], factor: float) -> "Vector": ...
    def slerp(self, other: Sequence[float], factor: float, fallback: object = ...) -> "Vector": ...
    def project(self, other: Sequence[float]) -> "Vector": ...
    def reflect(self, mirror: Sequence[float]) -> "Vector": ...
    def orthogonal(self) -> "Vector": ...
    def rotate(self, other: "Euler | Quaternion | Matrix") -> None: ...
    def rotation_difference(self, other: Sequence[float]) -> "Quaternion": ...
    def to_track_quat(self, track: str = "Z", up: str = "Y") -> "Quaternion": ...
    def __array__(self, dtype: object = None, copy: bool | None = None) -> np.ndarray: ...
    # sequence protocol, + - * / @ unary, ==, slices, __len__, __iter__; __hash__ only if frozen

# matrix.py
class Matrix:
    __slots__ = ("_m", "_owner", "_key", "_frozen")       # _m: np.ndarray float64 (r, c)
    def __init__(self, rows: Iterable[Iterable[float]] = ...) -> None: ...   # default 4x4 identity
    @classmethod
    def Identity(cls, size: int) -> "Matrix": ...
    @classmethod
    def Rotation(cls, angle: float, size: int, axis: "str | Sequence[float]") -> "Matrix": ...
    @classmethod
    def Scale(cls, factor: float, size: int, axis: Sequence[float] | None = None) -> "Matrix": ...
    @classmethod
    def Translation(cls, vector: Sequence[float]) -> "Matrix": ...
    @classmethod
    def Shear(cls, plane: str, size: int, factor: "float | Sequence[float]") -> "Matrix": ...
    @classmethod
    def OrthoProjection(cls, axis: "str | Sequence[float]", size: int) -> "Matrix": ...
    @classmethod
    def Diagonal(cls, vector: Sequence[float]) -> "Matrix": ...
    @classmethod
    def LocRotScale(cls, location: Sequence[float] | None, rotation: "Quaternion | Euler | Matrix | None",
                    scale: Sequence[float] | None) -> "Matrix": ...
    row: "MatrixAccess"; col: "MatrixAccess"; translation: Vector; median_scale: float
    is_identity: bool; is_negative: bool; is_orthogonal: bool; is_orthogonal_axis_vectors: bool
    is_wrapped: bool; is_frozen: bool; is_valid: bool; owner: object | None
    def copy(self) -> "Matrix": ...; def freeze(self) -> "Matrix": ...
    def determinant(self) -> float: ...
    def invert(self, fallback: "Matrix | None" = None) -> None: ...
    def inverted(self, fallback: object = ...) -> "Matrix": ...
    def invert_safe(self) -> None: ...; def inverted_safe(self) -> "Matrix": ...
    def transpose(self) -> None: ...; def transposed(self) -> "Matrix": ...
    def normalize(self) -> None: ...; def normalized(self) -> "Matrix": ...
    def adjugate(self) -> None: ...; def adjugated(self) -> "Matrix": ...
    def zero(self) -> "Matrix": ...; def identity(self) -> None: ...
    def decompose(self) -> tuple[Vector, "Quaternion", Vector]: ...
    def to_euler(self, order: str = "XYZ", euler_compat: "Euler | None" = None) -> "Euler": ...
    def to_quaternion(self) -> "Quaternion": ...
    def to_scale(self) -> Vector: ...; def to_translation(self) -> Vector: ...
    def to_2x2(self) -> "Matrix": ...; def to_3x3(self) -> "Matrix": ...; def to_4x4(self) -> "Matrix": ...
    def resize_4x4(self) -> None: ...
    def lerp(self, other: "Matrix", factor: float) -> "Matrix": ...
    def rotate(self, other: "Euler | Quaternion | Matrix") -> None: ...
    def __matmul__(self, other: "Matrix | Vector") -> "Matrix | Vector": ...
    def __getitem__(self, i: int) -> Vector: ...    # wrapped row
    def __array__(self, dtype: object = None, copy: bool | None = None) -> np.ndarray: ...

# quaternion.py
class Quaternion:
    def __init__(self, seq: Sequence[float] = (1.0, 0.0, 0.0, 0.0), angle: float | None = None) -> None: ...
    w: float; x: float; y: float; z: float; axis: Vector; angle: float; magnitude: float
    def copy(self) -> "Quaternion": ...; def freeze(self) -> "Quaternion": ...
    def normalize(self) -> None: ...; def normalized(self) -> "Quaternion": ...
    def conjugate(self) -> None: ...; def conjugated(self) -> "Quaternion": ...
    def invert(self) -> None: ...; def inverted(self) -> "Quaternion": ...; def identity(self) -> "Quaternion": ...
    def negate(self) -> "Quaternion": ...
    def dot(self, other: "Quaternion") -> float: ...; def cross(self, other: "Quaternion") -> "Quaternion": ...
    def rotation_difference(self, other: "Quaternion") -> "Quaternion": ...
    def slerp(self, other: "Quaternion", factor: float) -> "Quaternion": ...
    def rotate(self, other: "Euler | Quaternion | Matrix") -> None: ...
    def make_compatible(self, other: "Quaternion") -> None: ...
    def to_euler(self, order: str = "XYZ", euler_compat: "Euler | None" = None) -> "Euler": ...
    def to_matrix(self) -> Matrix: ...
    def to_axis_angle(self) -> tuple[Vector, float]: ...
    def to_exponential_map(self) -> Vector: ...; def to_swing_twist(self, axis: str) -> tuple["Quaternion", float]: ...
    def __matmul__(self, other: "Quaternion | Vector") -> "Quaternion | Vector": ...

# euler.py
class Euler:
    def __init__(self, angles: Sequence[float] = (0.0, 0.0, 0.0), order: str = "XYZ") -> None: ...
    x: float; y: float; z: float; order: str
    def copy(self) -> "Euler": ...; def freeze(self) -> "Euler": ...; def zero(self) -> None: ...
    def to_matrix(self) -> Matrix: ...; def to_quaternion(self) -> Quaternion: ...
    def rotate(self, other: "Euler | Quaternion | Matrix") -> None: ...
    def rotate_axis(self, axis: str, angle: float) -> None: ...
    def make_compatible(self, other: "Euler") -> None: ...

# color.py
class Color:
    def __init__(self, rgb: Sequence[float] = (0.0, 0.0, 0.0)) -> None: ...
    r: float; g: float; b: float; h: float; s: float; v: float; hsv: tuple[float, float, float]
    def copy(self) -> "Color": ...; def freeze(self) -> "Color": ...
    def from_scene_linear_to_srgb(self) -> "Color": ...; def from_srgb_to_scene_linear(self) -> "Color": ...
    # remaining color space conversions: documented stubs (no OCIO)

# geometry.py (subset, driven by the sweep)
def intersect_line_line(v1, v2, v3, v4) -> tuple[Vector, Vector] | None: ...
def intersect_line_plane(line_a, line_b, plane_co, plane_no, no_flip: bool = False) -> Vector | None: ...
def intersect_ray_tri(v1, v2, v3, ray, orig, clip: bool = True) -> Vector | None: ...
def intersect_point_line(pt, line_p1, line_p2) -> tuple[Vector, float]: ...
def intersect_point_tri(pt, tri_p1, tri_p2, tri_p3) -> Vector | None: ...
def distance_point_to_plane(pt, plane_co, plane_no) -> float: ...
def normal(*vectors: Sequence[float]) -> Vector: ...
def area_tri(v1, v2, v3) -> float: ...
def barycentric_transform(point, tri_a1, tri_a2, tri_a3, tri_b1, tri_b2, tri_b3) -> Vector: ...
def tessellate_polygon(veclist_list: Sequence[Sequence[Sequence[float]]]) -> list[tuple[int, int, int]]: ...
def convex_hull_2d(points: Sequence[Sequence[float]]) -> list[int]: ...
def box_pack_2d(boxes: list[list[float]]) -> tuple[float, float]: ...

# kdtree.py
class KDTree:
    def __init__(self, size: int) -> None: ...
    def insert(self, co: Sequence[float], index: int) -> None: ...
    def balance(self) -> None: ...
    def find(self, co: Sequence[float], filter: Callable[[int], bool] | None = None) -> tuple[Vector | None, int | None, float | None]: ...
    def find_n(self, co: Sequence[float], n: int) -> list[tuple[Vector, int, float]]: ...
    def find_range(self, co: Sequence[float], radius: float) -> list[tuple[Vector, int, float]]: ...

# bvhtree.py
class BVHTree:
    @classmethod
    def FromPolygons(cls, vertices: ArrayLike, polygons: Sequence[Sequence[int]], all_triangles: bool = False,
                     epsilon: float = 0.0) -> "BVHTree": ...
    @classmethod
    def FromObject(cls, object: object, depsgraph: object, deform: bool = True, render: bool = False,
                   cage: bool = False, epsilon: float = 0.0) -> "BVHTree": ...   # adapter injected by Layer 2
    def ray_cast(self, origin, direction, distance: float = ...) -> tuple[Vector | None, Vector | None, int | None, float | None]: ...
    def find_nearest(self, origin, distance: float = ...) -> tuple[Vector | None, Vector | None, int | None, float | None]: ...
    def find_nearest_range(self, origin, distance: float = ...) -> list[tuple[Vector, Vector, int, float]]: ...
    def overlap(self, other_tree: "BVHTree") -> list[tuple[int, int]]: ...
def set_object_adapter(fn: Callable[..., "BVHTree"]) -> None: ...

# interpolate.py / noise.py
def poly_3d_calc(veclist: Sequence[Sequence[float]], pt: Sequence[float]) -> list[float]: ...
def noise(position, noise_basis: str = "PERLIN_ORIGINAL") -> float: ...   # own values (divergence)
def random() -> float: ...; def seed_set(seed: int) -> None: ...; def random_unit_vector(size: int = 3) -> Vector: ...

# batch.py (Quartz only)
def transform_points(matrix: ArrayLike, points: np.ndarray) -> np.ndarray: ...
def transform_directions(matrix: ArrayLike, dirs: np.ndarray, *, normalize: bool = False) -> np.ndarray: ...
def normalize_rows(a: np.ndarray, *, eps: float = 1e-12) -> np.ndarray: ...
def compose_trs(loc: np.ndarray, quat: np.ndarray, scale: np.ndarray) -> np.ndarray: ...   # (N,4,4)
def euler_to_matrices(eulers: np.ndarray, order: str = "XYZ") -> np.ndarray: ...           # (N,3,3)
```

#### `quartz.props`

```python
# deferred.py
class PropDeferred:
    __slots__ = ("function", "keywords")
    def __init__(self, function: Callable[..., "PropDeferred"], keywords: dict[str, Any]) -> None: ...
QUARTZ_EXTENSION_KWARGS: frozenset[str]   # group parent enabled_if visible_if widget ui dirty storage column on_remove refcount uid since
BPY_KWARGS: Mapping[str, frozenset[str]]  # kwargs accepted per function in Blender 5.2.2 (for the shim FILTER)
def BoolProperty(*, name: str = "", description: str = "", translation_context: str = "*", default: bool = False,
                 options: set[str] = ..., override: set[str] = ..., tags: set[str] = ..., subtype: str = "NONE",
                 update=None, get=None, set=None, get_transform=None, set_transform=None, **quartz_ext) -> PropDeferred: ...
def BoolVectorProperty(*, ..., default: Sequence[bool] = (False, False, False), size: int | tuple[int, ...] = 3, **quartz_ext) -> PropDeferred: ...
def IntProperty(*, ..., default: int = 0, min: int = ..., max: int = ..., soft_min: int = ..., soft_max: int = ...,
                step: int = 1, **quartz_ext) -> PropDeferred: ...
def IntVectorProperty(*, ..., size=3, **quartz_ext) -> PropDeferred: ...
def FloatProperty(*, ..., default: float = 0.0, min=..., max=..., soft_min=..., soft_max=..., step: int = 3,
                  precision: int = 2, unit: str = "NONE", **quartz_ext) -> PropDeferred: ...
def FloatVectorProperty(*, ..., size=3, **quartz_ext) -> PropDeferred: ...
def StringProperty(*, ..., default: str = "", maxlen: int = 0, search=None, search_options: set[str] = ..., **quartz_ext) -> PropDeferred: ...
def EnumProperty(items, *, ..., default: str | int | set[str] | None = None, **quartz_ext) -> PropDeferred: ...
def PointerProperty(*, type: type | str, ..., poll=None, update=None, **quartz_ext) -> PropDeferred: ...
def CollectionProperty(*, type: type | str, ..., **quartz_ext) -> PropDeferred: ...
def RemoveProperty(cls: type, *, attr: str) -> None: ...

# spec.py
class Kind(StrEnum): BOOL, INT, FLOAT, STRING, ENUM, POINTER, COLLECTION
class Storage(StrEnum): STORE, VIRTUAL, COLUMN
class EnumItem(NamedTuple): identifier: str; name: str; description: str; icon: str | int = "NONE"; value: int = -1
@dataclass(frozen=True, slots=True)
class ColumnBinding: domain: str; attribute: str; component: int | None = None; invert: bool = False
@dataclass(frozen=True, slots=True)
class GroupSpec: identifier: str; label: str; parent: str | None = None; order: int = 0; default_open: bool = True
@dataclass(frozen=True, slots=True)
class ParamSpec: ...   # fields from §4.2
    def to_rna_dict(self) -> dict[str, Any]: ...      # schema of data/blender_api_dump.json
    def to_json(self) -> dict[str, Any]: ...
def spec_from_deferred(identifier: str, deferred: PropDeferred, *, resolve_type: Callable[[object], type] | None = None) -> ParamSpec: ...

# description.py
class Description:
    owner: str; revision: int; schema_version: int; bases: tuple["Description", ...]
    ignored_assignments: tuple[str, ...]
    def __iter__(self) -> Iterator[ParamSpec]: ...; def __len__(self) -> int: ...
    def __contains__(self, identifier: str) -> bool: ...; def __getitem__(self, identifier: str) -> ParamSpec: ...
    def get(self, identifier: str, default: ParamSpec | None = None) -> ParamSpec | None: ...
    def groups(self) -> tuple[GroupSpec, ...]: ...
    def params_in_group(self, group: str | None) -> tuple[ParamSpec, ...]: ...
    def tree(self) -> "DescriptionNode": ...
    def is_enabled(self, owner: object, identifier: str) -> bool: ...
    def is_visible(self, owner: object, identifier: str) -> bool: ...
    def derive(self, *, owner: str | None = None, add: Iterable[ParamSpec] = (), remove: Iterable[str] = (),
               override: Mapping[str, Mapping[str, Any]] | None = None, hide: Iterable[str] = (),
               show: Iterable[str] = (), groups: Iterable[GroupSpec] = ()) -> "Description": ...
    def to_rna_dict(self) -> dict[str, Any]: ...; def to_json(self) -> dict[str, Any]: ...
class DescriptionBuilder:
    def __init__(self, base: Description) -> None: ...
    def add(self, identifier: str, prop: PropDeferred, *, group: str | None = None, after: str | None = None) -> None: ...
    def remove(self, identifier: str) -> None: ...
    def hide(self, *identifiers: str) -> None: ...; def show(self, *identifiers: str) -> None: ...
    def override(self, identifier: str, **changes: Any) -> None: ...
    def group(self, identifier: str, label: str, *, parent: str | None = None) -> None: ...
    def build(self) -> Description: ...
def collect_annotations(cls: type, *, eval_str: bool = True) -> dict[str, PropDeferred]: ...   # per class in the MRO (annotationlib)
def compile_description(cls: type, *, owner: str, resolve_type: Callable[[object], type] | None = None,
                        schema_version: int = 1) -> Description: ...

# store.py / coerce.py
class ParamStore:
    __slots__ = ("_values", "_set", "_orphans", "_listener")
    def __init__(self, listener: Callable[[ParamSpec, object, object], None] | None = None) -> None: ...  # (spec, old, new)
    def read(self, spec: ParamSpec, owner: object) -> Any: ...
    def write(self, spec: ParamSpec, owner: object, value: Any, *, notify: bool = True) -> None: ...
    def is_set(self, identifier: str) -> bool: ...
    def unset(self, identifier: str) -> None: ...
    def raw_get(self, identifier: str, default: Any = None) -> Any: ...
    def raw_items(self) -> Iterator[tuple[str, Any]]: ...
    def orphans(self) -> dict[str, Any]: ...
    def adopt_orphans(self, description: Description) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...; def restore(self, snap: dict[str, Any]) -> None: ...
def coerce(spec: ParamSpec, value: Any, *, owner: object = None, context: object = None) -> Any: ...
def default_for(spec: ParamSpec, owner: object = None) -> Any: ...
def resolve_enum_items(spec: ParamSpec, owner: object, context: object) -> tuple[EnumItem, ...]: ...

# collection.py
class PropCollection(Generic[T]):
    def __init__(self, element_factory: Callable[[], T], *, owner: object = None, path: str = "") -> None: ...
    def add(self) -> T: ...; def remove(self, index: int) -> None: ...; def clear(self) -> None: ...
    def move(self, from_index: int, to_index: int) -> None: ...
    def find(self, key: str) -> int: ...; def get(self, key: str, default: Any = None) -> T | Any: ...
    def keys(self) -> list[str]: ...; def values(self) -> list[T]: ...; def items(self) -> list[tuple[str, T]]: ...
    def foreach_get(self, attr: str, seq: ArrayLike) -> None: ...; def foreach_set(self, attr: str, seq: ArrayLike) -> None: ...
    def __getitem__(self, key: int | str | slice) -> T | list[T]: ...; def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[T]: ...; def __contains__(self, key: str) -> bool: ...

# paths.py
@dataclass(frozen=True, slots=True)
class PathToken: kind: Literal["attr", "index", "key"]; value: str | int
def parse_path(path: str) -> tuple[PathToken, ...]: ...      # 'modifiers["Bend"].angle', 'location[0]'
def format_path(tokens: Sequence[PathToken]) -> str: ...
def escape_identifier(string: str) -> str: ...; def unescape_identifier(string: str) -> str: ...

# adapters.py
def set_value_wrapper(family: str, fn: Callable[[object, ParamSpec, Any], Any]) -> None: ...
def set_id_resolver(fn: Callable[[object], object | None]) -> None: ...
def set_context_provider(fn: Callable[[], object | None]) -> None: ...
def set_type_resolver(fn: Callable[[object], type]) -> None: ...

# errors.py
class PropertyDefinitionError(ValueError): ...
class PropertyTypeError(TypeError): ...
class PropertyReadOnlyError(AttributeError): ...
```

#### `quartz.geometry`

```python
# attributes.py
class Domain(StrEnum): POINT, EDGE, FACE, CORNER, CURVE, INSTANCE
class DataType(StrEnum): FLOAT, INT, FLOAT_VECTOR, FLOAT_COLOR, BYTE_COLOR, STRING, BOOLEAN, FLOAT2, INT8, INT16_2D, INT32_2D, QUATERNION, FLOAT4X4
DTYPES: Mapping[DataType, tuple[np.dtype, tuple[int, ...]]]
class AttributeArray:
    name: str; domain: Domain; data_type: DataType; is_internal: bool; is_required: bool
    @property
    def data(self) -> np.ndarray: ...               # read-only view
    def writable(self) -> np.ndarray: ...           # copy-on-write + notification
    def set(self, values: ArrayLike) -> None: ...
class AttributeStore:
    def __init__(self, sizes: Callable[[Domain], int],
                 observer: Callable[[str, AttributeArray, np.ndarray | None], None] | None = None) -> None: ...
    def new(self, name: str, data_type: DataType | str, domain: Domain | str, *, fill: Any = None) -> AttributeArray: ...
    def get(self, name: str) -> AttributeArray | None: ...; def remove(self, name: str) -> None: ...
    def rename(self, old: str, new: str) -> None: ...; def by_domain(self, domain: Domain | str) -> list[AttributeArray]: ...
    def resize_domain(self, domain: Domain | str, new_size: int, *, keep: np.ndarray | None = None) -> None: ...
    def __getitem__(self, name: str) -> AttributeArray: ...; def __contains__(self, name: str) -> bool: ...
    def __iter__(self) -> Iterator[AttributeArray]: ...; def __len__(self) -> int: ...
    active_name: str | None; active_color_name: str | None; default_color_name: str | None

# mesh_data.py
class MeshData:
    attributes: AttributeStore; revision: int
    num_points: int; num_edges: int; num_faces: int; num_corners: int
    positions: np.ndarray; edge_verts: np.ndarray; face_offsets: np.ndarray; corner_verts: np.ndarray; corner_edges: np.ndarray
    def __init__(self) -> None: ...
    @classmethod
    def from_pydata(cls, vertices: ArrayLike, edges: ArrayLike = (), faces: Sequence[Sequence[int]] = (),
                    *, calc_edges: bool = True) -> "MeshData": ...
    def add_points(self, count: int) -> slice: ...; def add_edges(self, count: int) -> slice: ...
    def add_corners(self, count: int) -> slice: ...; def add_faces(self, count: int) -> slice: ...
    def set_face_offsets(self, loop_start: ArrayLike) -> None: ...
    def set_topology(self, face_offsets: ArrayLike, corner_verts: ArrayLike, *, edge_verts: ArrayLike | None = None) -> None: ...
    def calc_edges(self, *, keep_loose: bool = True) -> None: ...
    def face_sizes(self) -> np.ndarray: ...
    def face_normals(self) -> np.ndarray: ...; def point_normals(self) -> np.ndarray: ...; def corner_normals(self) -> np.ndarray: ...
    def face_centers(self) -> np.ndarray: ...; def face_areas(self) -> np.ndarray: ...
    def corner_triangles(self) -> np.ndarray: ...; def triangle_faces(self) -> np.ndarray: ...
    def transform(self, matrix: ArrayLike) -> None: ...
    def bounds(self) -> tuple[np.ndarray, np.ndarray]: ...
    def copy(self, *, share: bool = True) -> "MeshData": ...
    def clear(self) -> None: ...
    def validate(self, *, fix: bool = True) -> list[str]: ...

# topology.py / normals.py / triangulate.py / transform.py / validate.py
def faces_to_offsets(faces: Sequence[Sequence[int]]) -> tuple[np.ndarray, np.ndarray]: ...
def build_edges(face_offsets: np.ndarray, corner_verts: np.ndarray, existing: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]: ...
def edge_keys(edge_verts: np.ndarray) -> np.ndarray: ...
def loose_edges(num_edges: int, corner_edges: np.ndarray) -> np.ndarray: ...
def merge_by_distance(positions: np.ndarray, distance: float) -> np.ndarray: ...   # index map
def face_normals(positions: np.ndarray, face_offsets: np.ndarray, corner_verts: np.ndarray) -> np.ndarray: ...
def point_normals(...) -> np.ndarray: ...; def corner_normals(..., sharp_face: np.ndarray | None = None) -> np.ndarray: ...
def triangulate(mesh: MeshData, *, face_mask: np.ndarray | None = None, quad_method: str = "BEAUTY",
                ngon_method: str = "BEAUTY", min_vertices: int = 4) -> MeshData: ...
def apply_matrix(positions: np.ndarray, matrix: ArrayLike) -> np.ndarray: ...
def validate_mesh(mesh: MeshData, *, fix: bool = True) -> list[str]: ...

# primitives.py (defaults = defaults of the mesh.primitive_* operators in the dump)
def cube(size: float = 2.0, *, calc_uvs: bool = True) -> MeshData: ...
def plane(size: float = 2.0, *, calc_uvs: bool = True) -> MeshData: ...
def grid(x_subdivisions: int = 10, y_subdivisions: int = 10, size: float = 2.0, *, calc_uvs: bool = True) -> MeshData: ...
def circle(vertices: int = 32, radius: float = 1.0, fill_type: str = "NOTHING", *, calc_uvs: bool = True) -> MeshData: ...
def uv_sphere(segments: int = 32, ring_count: int = 16, radius: float = 1.0, *, calc_uvs: bool = True) -> MeshData: ...
def ico_sphere(subdivisions: int = 2, radius: float = 1.0, *, calc_uvs: bool = True) -> MeshData: ...
def cylinder(vertices: int = 32, radius: float = 1.0, depth: float = 2.0, end_fill_type: str = "NGON", *, calc_uvs: bool = True) -> MeshData: ...
def cone(vertices: int = 32, radius1: float = 1.0, radius2: float = 0.0, depth: float = 2.0, end_fill_type: str = "NGON", *, calc_uvs: bool = True) -> MeshData: ...
def torus(major_segments: int = 48, minor_segments: int = 12, major_radius: float = 1.0, minor_radius: float = 0.25, *, calc_uvs: bool = True) -> MeshData: ...

# editmesh.py (bmesh form)
class HasMeshData(Protocol):
    q_meshdata: MeshData
class EditMesh:
    verts: "EVertSeq"; edges: "EEdgeSeq"; faces: "EFaceSeq"; loops: "ELoopSeq"
    select_mode: set[str]; select_history: list; is_valid: bool; is_wrapped: bool
    def __init__(self) -> None: ...
    @classmethod
    def from_mesh_data(cls, md: MeshData) -> "EditMesh": ...
    def to_mesh_data(self) -> MeshData: ...
    def from_mesh(self, mesh: HasMeshData, *, face_normals: bool = True, vertex_normals: bool = True,
                  use_shape_key: bool = False, shape_key_index: int = 0) -> None: ...
    def to_mesh(self, mesh: HasMeshData) -> None: ...
    def free(self) -> None: ...; def clear(self) -> None: ...; def copy(self) -> "EditMesh": ...
    def normal_update(self) -> None: ...
    def select_flush(self, select: bool) -> None: ...; def select_flush_mode(self) -> None: ...
    def calc_volume(self, signed: bool = False) -> float: ...
    def calc_loop_triangles(self) -> list[tuple["ELoop", "ELoop", "ELoop"]]: ...
    def transform(self, matrix: ArrayLike, filter: set[str] | None = None) -> None: ...
class EVert: co; normal; index; select; hide; tag; link_edges; link_faces; link_loops; is_manifold; is_boundary; is_wire
    def select_set(self, select: bool) -> None: ...; def hide_set(self, hide: bool) -> None: ...
    def copy_from(self, other: "EVert") -> None: ...; def calc_edge_angle(self, fallback: float | None = None) -> float: ...
class EEdge: verts; link_faces; link_loops; index; select; hide; seam; smooth; is_manifold; is_boundary; is_wire
    def other_vert(self, vert: EVert) -> EVert | None: ...; def calc_length(self) -> float: ...
class EFace: verts; edges; loops; normal; material_index; smooth; select; hide; index
    def calc_area(self) -> float: ...; def calc_center_median(self) -> "Vector": ...; def calc_center_bounds(self) -> "Vector": ...
    def normal_update(self) -> None: ...; def normal_flip(self) -> None: ...; def copy(self, verts: bool = True, edges: bool = True) -> "EFace": ...
class ELoop: vert; edge; face; index; link_loop_next; link_loop_prev; link_loop_radial_next; link_loop_radial_prev
    def calc_angle(self) -> float: ...
class EVertSeq:  # EEdgeSeq / EFaceSeq analogous
    layers: "ELayerAccess"
    def new(self, co: Sequence[float] = (0.0, 0.0, 0.0), example: EVert | None = None) -> EVert: ...
    def remove(self, vert: EVert) -> None: ...; def ensure_lookup_table(self) -> None: ...
    def index_update(self) -> None: ...; def sort(self, key=None, reverse: bool = False) -> None: ...
    def __getitem__(self, i: int) -> EVert: ...; def __len__(self) -> int: ...; def __iter__(self) -> Iterator[EVert]: ...
# EEdgeSeq.new(verts, example=None) / get(verts, fallback=None); EFaceSeq.new(verts, example=None) / get(verts) / active

# edit_ops.py (= bmesh.ops subset; keyword-only kwargs and dict return as in bmesh)
def triangulate(em: EditMesh, *, faces, quad_method: int = 0, ngon_method: int = 0) -> dict: ...
def remove_doubles(em: EditMesh, *, verts, dist: float = 0.0001) -> dict: ...
def recalc_face_normals(em: EditMesh, *, faces) -> None: ...
def reverse_faces(em: EditMesh, *, faces, flip_multires: bool = False) -> None: ...
def delete(em: EditMesh, *, geom, context: str = "VERTS") -> None: ...
def create_cube(em: EditMesh, *, size: float = 1.0, matrix=None, calc_uvs: bool = False) -> dict: ...
def create_grid / create_circle / create_cone / create_uvsphere / create_icosphere (same pattern)
def translate(em, *, verts, vec, space=None) -> None: ...; def rotate(em, *, verts, cent, matrix, space=None) -> None: ...
def scale(em, *, verts, vec, space=None) -> None: ...; def transform(em, *, verts, matrix, space=None) -> None: ...

# curve_data.py / instances.py / geometry_set.py
class CurveData: positions: np.ndarray; handle_left: np.ndarray | None; handle_right: np.ndarray | None
    curve_offsets: np.ndarray; curve_types: np.ndarray; cyclic: np.ndarray; attributes: AttributeStore
class InstanceCloud:
    def __init__(self, matrices: np.ndarray, references: Sequence[object] = (), reference_index: np.ndarray | None = None) -> None: ...
    matrices: np.ndarray; reference_index: np.ndarray; references: list[object]; attributes: AttributeStore
    def __len__(self) -> int: ...
@dataclass
class GeometrySet:
    mesh: MeshData | None = None; curve: CurveData | None = None; instances: InstanceCloud | None = None
    def transformed(self, matrix: ArrayLike) -> "GeometrySet": ...
    @staticmethod
    def merge(sets: Sequence["GeometrySet"]) -> "GeometrySet": ...
```

### 12.2 Layer 2 — data model, registry, operators

Internal order: `core.errors/dirty/names/users` → `core.struct/rna/custom_props` → `core.id/main` →
`types.*` (object, mesh, others) → `core.registry/kinds` → `core.session/context` + `factory` →
`ops` (runner, built-ins) → `core.undo/journal` → `core.depsgraph/evaluation` + `types.generator/
tag/modifier` → `ui` → `io` → `app/utils/path/extras`.
Exit criterion: `contract/` tests (except loader) green; goldens `sc_ids`, `sc_props`,
`sc_registration`, `sc_operators`, `sc_context`, `sc_mesh`, `sc_handlers` matching; `.qz` round trip.

#### `quartz.core`

```python
# errors.py — hierarchy of §6.7

# dirty.py
class Channel(IntEnum): DATA = 0; MATRIX = 1; GEOMETRY = 2; SELECT = 3; CHILDREN = 4; DESCRIPTION = 5; SHADING = 6; VISIBILITY = 7
class DirtyCounters:
    __slots__ = ("_c",)
    def bump(self, channel: Channel | str) -> int: ...
    def get(self, channel: Channel | str) -> int: ...
    def stamp(self) -> tuple[int, ...]: ...
def clock() -> int: ...

# names.py / users.py
def clamp_name(name: str, max_bytes: int = 255) -> str: ...
def split_suffix(name: str) -> tuple[str, int | None]: ...
class NameRegistry:
    def unique(self, base: str, *, exclude: object = None) -> str: ...
    def add(self, name: str, owner: object) -> None: ...; def remove(self, name: str) -> None: ...
    def rename(self, old: str, new: str, owner: object) -> str: ...
class UserGraph:
    def add_user(self, target: "ID", source: object, kind: str) -> None: ...
    def remove_user(self, target: "ID", source: object, kind: str) -> None: ...
    def users_of(self, target: "ID") -> set[object]: ...; def refs_from(self, source: object) -> set["ID"]: ...
    def remap(self, old: "ID", new: "ID | None") -> int: ...

# struct.py
class StructMeta(type):
    def __setattr__(cls, name: str, value: object) -> None: ...   # PropDeferred on registered type → extends
    def __delattr__(cls, name: str) -> None: ...
    @property
    def is_registered(cls) -> bool: ...
class Struct(metaclass=StructMeta):
    bl_rna: ClassVar["RNAStruct"]
    q_schema_version: ClassVar[int] = 1
    q_groups: ClassVar[tuple[GroupSpec, ...]] = ()
    q_hide: ClassVar[frozenset[str]] = frozenset(); q_show: ClassVar[frozenset[str]] = frozenset()
    q_override: ClassVar[Mapping[str, Mapping[str, Any]]] = {}
    rna_type: "RNAStruct"; id_data: "ID | None"
    def describe(self, builder: DescriptionBuilder) -> None: ...
    @classmethod
    def q_upgrade(cls, params: dict[str, Any], from_version: int) -> dict[str, Any]: ...
    def q_description(self) -> Description: ...
    def q_redescribe(self) -> None: ...
    def path_from_id(self, property: str = "") -> str: ...
    def path_resolve(self, path: str, coerce: bool = True) -> Any: ...
    def is_property_set(self, property: str, ghost: bool = True) -> bool: ...
    def property_unset(self, property: str) -> None: ...
    def is_property_readonly(self, property: str) -> bool: ...
    def is_property_hidden(self, property: str) -> bool: ...
    def is_property_overridable_library(self, property: str) -> bool: ...
    def keys(self) -> list[str]: ...; def values(self) -> list[Any]: ...; def items(self) -> list[tuple[str, Any]]: ...
    def get(self, key: str, default: Any = None) -> Any: ...; def pop(self, key: str, default: Any = ...) -> Any: ...
    def __getitem__(self, key: str) -> Any: ...; def __setitem__(self, key: str, value: Any) -> None: ...
    def __delitem__(self, key: str) -> None: ...; def __contains__(self, key: str) -> bool: ...
    def id_properties_ensure(self) -> "IDPropertyGroup": ...
    def id_properties_ui(self, key: str) -> "IDPropertyUIManager": ...
    def id_properties_clear(self) -> None: ...
    def bl_system_properties_get(self, do_create: bool = False) -> "SystemPropertiesView | None": ...
    def as_pointer(self) -> int: ...
    def type_recast(self) -> "Struct": ...; def rna_ancestors(self) -> tuple["Struct", ...]: ...
    @classmethod
    def bl_rna_get_subclass(cls, id: str, default: object = None) -> "RNAStruct | object": ...
    @classmethod
    def bl_rna_get_subclass_py(cls, id: str, default: object = None) -> type | object: ...
    def driver_add(self, path: str, index: int = -1) -> NoReturn: ...         # QuartzNotImplementedError
    def driver_remove(self, path: str, index: int = -1) -> bool: ...
    def keyframe_insert(self, data_path: str, index: int = -1, frame: float = ..., group: str = "",
                        options: set[str] = ..., keytype: str = "KEYFRAME") -> bool: ...   # deferred: QuartzNotImplementedError
    def keyframe_delete(self, data_path: str, index: int = -1, frame: float = ..., group: str = "") -> bool: ...
class ParamDescriptor:
    def __init__(self, spec: ParamSpec) -> None: ...
    def __get__(self, instance: Struct | None, owner: type) -> Any: ...
    def __set__(self, instance: Struct, value: Any) -> None: ...
    def __delete__(self, instance: Struct) -> None: ...

# rna.py
class RNAProperty:
    identifier: str; name: str; description: str; type: str; subtype: str; unit: str
    is_readonly: bool; is_animatable: bool; is_hidden: bool; is_skip_save: bool; is_required: bool
    is_enum_flag: bool; translation_context: str; tags: set[str]
class BoolRNAProperty(RNAProperty): default: bool; default_array: tuple[bool, ...]; array_length: int; array_dimensions: tuple[int, ...]
class IntRNAProperty(RNAProperty): default: int; hard_min: int; hard_max: int; soft_min: int; soft_max: int; step: int; array_length: int
class FloatRNAProperty(RNAProperty): default: float; hard_min: float; hard_max: float; soft_min: float; soft_max: float; step: float; precision: int; array_length: int
class StringRNAProperty(RNAProperty): default: str; length_max: int
class EnumRNAProperty(RNAProperty): default: str | set[str]; enum_items: tuple["RNAEnumItem", ...]; enum_items_static: tuple["RNAEnumItem", ...]
class PointerRNAProperty(RNAProperty): fixed_type: "RNAStruct"
class CollectionRNAProperty(RNAProperty): fixed_type: "RNAStruct"
class RNAStruct:
    identifier: str; name: str; description: str; base: "RNAStruct | None"
    properties: PropCollection[RNAProperty]; functions: PropCollection["RNAFunction"]
def rna_view(cls: type[Struct]) -> RNAStruct: ...

# custom_props.py
class IDPropertyGroup:   # dict-like
    def to_dict(self) -> dict[str, Any]: ...; def update(self, other: Mapping[str, Any]) -> None: ...
    def keys(self) -> list[str]: ...; def values(self) -> list[Any]: ...; def items(self) -> list[tuple[str, Any]]: ...
    def get(self, key: str, default: Any = None) -> Any: ...; def pop(self, key: str, default: Any = ...) -> Any: ...; def clear(self) -> None: ...
class IDPropertyArray:
    typecode: str
    def to_list(self) -> list[Any]: ...; def __array__(self, dtype: object = None, copy: bool | None = None) -> np.ndarray: ...
class IDPropertyUIManager:
    def update(self, *, subtype: str | None = None, min=None, max=None, soft_min=None, soft_max=None, precision=None,
               step=None, default=None, description: str | None = None, items=None) -> None: ...
    def as_dict(self) -> dict[str, Any]: ...; def clear(self) -> None: ...; def update_from(self, other: "IDPropertyUIManager") -> None: ...
def rna_idprop_ui_create(item: Struct, prop: str, *, default: Any, min=None, max=None, soft_min=None, soft_max=None,
                         description: str | None = None, overridable: bool = False, subtype: str | None = None) -> IDPropertyUIManager: ...

# id.py
class ID(Struct):
    q_id_type: ClassVar[str]; q_collection: ClassVar[str]; q_default_name: ClassVar[str]
    name: str; name_full: str; id_type: str; session_uid: int; uuid: str
    users: int; use_fake_user: bool; use_extra_user: bool; is_evaluated: bool; original: "ID"
    library: None; is_embedded_data: bool; is_runtime_data: bool; is_editable: bool; is_missing: bool; tag: bool
    def copy(self) -> "ID": ...
    def rename(self, name: str, *, mode: str = "NEVER") -> str: ...
    def user_clear(self) -> None: ...; def user_remap(self, new_id: "ID") -> None: ...
    def user_of_id(self, id: "ID") -> int: ...
    def evaluated_get(self, depsgraph: "Depsgraph") -> "ID": ...
    def update_tag(self, *, refresh: set[str] = frozenset()) -> None: ...
    def animation_data_create(self) -> NoReturn: ...; def animation_data_clear(self) -> None: ...   # deferred

# main.py
class IDCollection(Generic[T]):
    rna_type: RNAStruct
    def new(self, name: str, *args: Any, **kwargs: Any) -> T: ...      # signature per type (below)
    def remove(self, id: T, *, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None: ...
    def get(self, key: str, default: Any = None) -> T | Any: ...; def find(self, key: str) -> int: ...
    def keys(self) -> list[str]: ...; def values(self) -> list[T]: ...; def items(self) -> list[tuple[str, T]]: ...
    def foreach_get(self, attr: str, seq: ArrayLike) -> None: ...; def foreach_set(self, attr: str, seq: ArrayLike) -> None: ...
    def tag(self, value: bool) -> None: ...
    def __getitem__(self, key: int | str) -> T: ...; def __contains__(self, key: str) -> bool: ...
    def __len__(self) -> int: ...; def __iter__(self) -> Iterator[T]: ...
# signatures of new: objects.new(name, object_data: ID | None); meshes.new(name); materials.new(name);
# cameras.new(name); lights.new(name, type: str); collections.new(name); scenes.new(name); worlds.new(name);
# images.new(name, width, height, alpha=False, float_buffer=False, stereo3d=False, is_data=False, tiled=False);
# texts.new(name); generators.new(name, kind: str); window_managers/screens/workspaces: no new.
# meshes.new_from_object(object, *, preserve_all_data_layers=False, depsgraph=None)
class Main(Struct):
    objects: IDCollection["Object"]; meshes: IDCollection["Mesh"]; materials: IDCollection["Material"]
    cameras: IDCollection["Camera"]; lights: IDCollection["Light"]; collections: IDCollection["Collection"]
    scenes: IDCollection["Scene"]; worlds: IDCollection["World"]; images: IDCollection["Image"]
    texts: IDCollection["Text"]; generators: IDCollection["Generator"]
    window_managers: IDCollection; screens: IDCollection; workspaces: IDCollection; libraries: IDCollection
    actions: IDCollection; armatures: IDCollection; curves: IDCollection; node_groups: IDCollection   # empty; new → QuartzNotImplementedError
    filepath: str; is_dirty: bool; is_saved: bool; version: tuple[int, int, int]; use_autopack: bool
    def __init__(self) -> None: ...
    def iter_ids(self) -> Iterator[ID]: ...
    def id_from_uuid(self, uuid: str) -> ID | None: ...; def id_from_session_uid(self, uid: int) -> ID | None: ...
    def user_map(self, *, subset: Iterable[ID] | None = None, key_types: set[str] | None = None,
                 value_types: set[str] | None = None) -> dict[ID, set[ID]]: ...
    def orphans_purge(self, *, do_local_ids: bool = True, do_linked_ids: bool = True, do_recursive: bool = False) -> int: ...
    def batch_remove(self, ids: Iterable[ID]) -> None: ...
    def temp_data(self, *, filepath: str | None = None) -> ContextManager["Main"]: ...
    def _replace_contents(self, other: "Main") -> None: ...

# paths.py
def resolve(root: Struct, path: str, *, coerce: bool = True) -> Any: ...
def resolve_spec(root: Struct, path: str) -> tuple[Struct, ParamSpec, int | None]: ...
def path_of(struct: Struct, identifier: str = "", index: int | None = None) -> str: ...

# registry.py / kinds.py
@dataclass
class TypeInfo: rna_name: str; cls: type; kind: str; description: Description; idname: str | None; owner: str | None; builtin: bool
@dataclass(frozen=True)
class KindSpec:
    kind: str; base_name: str; required: tuple[str, ...]; class_description: Description
    idname_rule: Callable[[type], str]; rna_name_rule: Callable[[type, str], str]
    name_convention: str | None = None
    on_register: Callable[[TypeInfo], None] | None = None; on_unregister: Callable[[TypeInfo], None] | None = None
KIND_SPECS: Mapping[str, KindSpec]
class TypeRegistry:
    def register_class(self, cls: type) -> None: ...
    def unregister_class(self, cls: type) -> None: ...
    def is_registered(self, cls: type) -> bool: ...
    def get(self, rna_name: str) -> TypeInfo | None: ...
    def by_idname(self, kind: str, idname: str) -> TypeInfo | None: ...
    def iter(self, kind: str | None = None) -> Iterator[TypeInfo]: ...
    def owner_scope(self, owner: str) -> ContextManager[None]: ...
    def owned_by(self, owner: str) -> list[TypeInfo]: ...
    def extend_type(self, cls: type, name: str, deferred: PropDeferred) -> None: ...
    def retract_type(self, cls: type, name: str) -> None: ...
    def resolve_type(self, ref: type | str) -> type: ...
    def snapshot(self) -> "RegistrySnapshot": ...; def restore(self, snap: "RegistrySnapshot") -> None: ...
REGISTRY: TypeRegistry
def register_builtin(cls: type) -> type: ...    # decorator for core types (not unregisterable)
def kind_of(cls: type) -> str | None: ...

# session.py
class Session:
    main: Main; context: "Context"; window_manager: "WindowManager"; preferences: "Preferences"
    undo: "UndoStack"; handlers: "HandlerLists"; timers: "TimerQueue"; msgbus: "MsgBus"
    reports: "ReportList"; background: bool; addons: object | None; compat: object | None
    def __init__(self, *, factory: bool = True) -> None: ...
    def activate(self) -> None: ...
    def close(self) -> None: ...                     # shutdown_pre → shutdown_post
    def restrict_blend(self) -> ContextManager[None]: ...
    def load(self, filepath: str) -> None: ...; def save(self, filepath: str, *, copy: bool = False) -> None: ...
    def reset(self, *, factory: bool = True) -> None: ...
def current() -> Session: ...
def new_session(*, factory: bool = True, activate: bool = True) -> Session: ...
def use_session(session: Session) -> ContextManager[Session]: ...

# context.py
Resolver = Callable[[Session, Mapping[str, Any]], Any]
CONTEXT_MEMBERS: dict[str, Resolver]
def register_member(name: str, resolver: Resolver) -> None: ...
class Context(Struct):
    def __getattr__(self, name: str) -> Any: ...
    def __setattr__(self, name: str, value: Any) -> NoReturn: ...      # ContextReadOnlyError
    def temp_override(self, **members: Any) -> ContextManager["Context"]: ...
    def copy(self) -> dict[str, Any]: ...
    def path_resolve(self, path: str, coerce: bool = True) -> Any: ...
    def evaluated_depsgraph_get(self) -> "Depsgraph": ...
    def q_members(self) -> tuple[str, ...]: ...
class RestrictedContext: window_manager: "WindowManager"; preferences: "Preferences"
class RestrictedData: ...   # any attribute → AttributeError

# journal.py / undo.py
class Change(Protocol):
    def undo(self, main: Main) -> None: ...; def redo(self, main: Main) -> None: ...; nbytes: int
class ParamChange: owner_uuid: str; path: str; old: Any; new: Any
class ArrayChange: owner_uuid: str; attribute: str; old: np.ndarray | None; new: np.ndarray | None
class IDCreate: ...; class IDRemove: ...; class LinkChange: ...; class ParentChange: ...; class ModeChange: ...
class Transaction:
    message: str
    def record(self, change: Change) -> None: ...; def commit(self) -> "UndoStep": ...; def rollback(self) -> None: ...
class UndoStep: message: str; changes: tuple[Change, ...]; nbytes: int
class UndoStack:
    enabled: bool; step_limit: int; steps: tuple[UndoStep, ...]; active_index: int
    def enable(self) -> None: ...
    def push(self, message: str) -> None: ...
    def undo(self) -> bool: ...; def redo(self) -> bool: ...
    def can_undo(self) -> bool: ...; def can_redo(self) -> bool: ...
    def transaction(self, message: str) -> ContextManager[Transaction]: ...
    def clear(self) -> None: ...

# handlers.py / timers.py / msgbus.py / reports.py
BLENDER_HANDLER_NAMES: tuple[str, ...]   # the 39 observed lists
QUARTZ_HANDLER_NAMES: tuple[str, ...]    # startup_post, shutdown_pre, shutdown_post, addon_enable_post, addon_disable_post, description_changed
class HandlerLists:
    def __getattr__(self, name: str) -> list[Callable[..., Any]]: ...
    def dispatch(self, name: str, *args: Any) -> list[BaseException]: ...
    def clear_non_persistent(self) -> None: ...
def persistent(function: Callable) -> Callable: ...
class TimerQueue:
    def register(self, function: Callable[[], float | None], *, first_interval: float = 0.0, persistent: bool = False) -> None: ...
    def unregister(self, function: Callable) -> None: ...
    def is_registered(self, function: Callable) -> bool: ...
    def pump(self, *, now: float | None = None, max_calls: int = 1000) -> int: ...
class MsgBus:
    def subscribe_rna(self, *, key: object, owner: object, args: tuple, notify: Callable, options: set[str] = frozenset()) -> None: ...
    def publish_rna(self, *, key: object) -> None: ...
    def clear_by_owner(self, owner: object) -> None: ...
    def flush(self) -> int: ...
@dataclass
class Report: type: str; message: str; source: str
class ReportList(list[Report]):
    def add(self, type: str, message: str, source: str = "") -> None: ...

# depsgraph.py / evaluation.py
STAGES: tuple[str, ...] = ("INITIAL", "ANIMATION", "DRIVERS", "EXPRESSION", "DYNAMICS", "GENERATOR", "DEFORM", "FINAL")
@dataclass
class EvalContext: depsgraph: "Depsgraph"; scene: "Scene"; view_layer: "ViewLayer"; frame: float
    object: "Object | None" = None; inputs: tuple[GeometrySet, ...] = ()
class DepsgraphUpdate(Struct): id: ID; is_updated_geometry: bool; is_updated_transform: bool; is_updated_shading: bool
class DepsgraphObjectInstance(Struct): object: "Object"; instance_object: "Object | None"; parent: "Object | None"
    is_instance: bool; matrix_world: Matrix; persistent_id: tuple[int, ...]; random_id: int
class Depsgraph(Struct):
    scene: "Scene"; view_layer: "ViewLayer"; mode: str; scene_eval: "Scene"; view_layer_eval: "ViewLayer"
    updates: tuple[DepsgraphUpdate, ...]; objects: Iterator["Object"]; object_instances: Iterator[DepsgraphObjectInstance]; ids: Iterator[ID]
    def __init__(self, scene: "Scene", view_layer: "ViewLayer", mode: str = "VIEWPORT") -> None: ...
    def update(self) -> None: ...
    def id_eval_get(self, id: ID) -> ID: ...
    def id_type_updated(self, id_type: str) -> bool: ...
class Evaluator:
    def __init__(self, depsgraph: Depsgraph) -> None: ...
    def evaluate(self) -> None: ...
    def geometry_of(self, obj: "Object") -> GeometrySet: ...
```

#### `quartz.types`

```python
# object.py
class Object(ID):            # params: §5.2 (groups relations/transform/visibility/instancing)
    data: ID | None; type: str; mode: str; parent: "Object | None"; parent_type: str
    children: tuple["Object", ...]; children_recursive: list["Object"]; users_collection: tuple["Collection", ...]
    location: Vector; rotation_mode: str; rotation_euler: Euler; rotation_quaternion: Quaternion
    rotation_axis_angle: tuple[float, float, float, float]; scale: Vector
    delta_location: Vector; delta_rotation_euler: Euler; delta_rotation_quaternion: Quaternion; delta_scale: Vector
    lock_location: tuple[bool, bool, bool]; lock_rotation: tuple[bool, bool, bool]; lock_scale: tuple[bool, bool, bool]
    matrix_basis: Matrix; matrix_local: Matrix; matrix_world: Matrix; matrix_parent_inverse: Matrix; dimensions: Vector
    hide_viewport: bool; hide_render: bool; hide_select: bool; display_type: str; show_name: bool; show_axis: bool
    show_wire: bool; show_in_front: bool; color: tuple[float, float, float, float]; pass_index: int
    empty_display_type: str; empty_display_size: float; instance_type: str; instance_collection: "Collection | None"
    modifiers: "ObjectModifiers"; tags: "ObjectTags"; constraints: "ObjectConstraints"; vertex_groups: "VertexGroups"
    material_slots: PropCollection["MaterialSlot"]; active_material: "Material | None"; active_material_index: int
    def select_get(self, view_layer: "ViewLayer | None" = None) -> bool: ...
    def select_set(self, state: bool, view_layer: "ViewLayer | None" = None) -> None: ...
    def hide_get(self, view_layer: "ViewLayer | None" = None) -> bool: ...
    def hide_set(self, state: bool, view_layer: "ViewLayer | None" = None) -> None: ...
    def visible_get(self, view_layer: "ViewLayer | None" = None, viewport: object = None) -> bool: ...
    def parent_set(self, parent: "Object | None", *, keep_transform: bool = False, index: int | None = None) -> None: ...  # Quartz
    def reorder(self, index: int) -> None: ...                                                                          # Quartz
    def to_mesh(self, *, preserve_all_data_layers: bool = False, depsgraph: "Depsgraph | None" = None) -> "Mesh": ...
    def to_mesh_clear(self) -> None: ...
    def ray_cast(self, origin, direction, distance: float = ..., depsgraph: "Depsgraph | None" = None) -> tuple[bool, Vector, Vector, int]: ...
    def closest_point_on_mesh(self, origin, distance: float = ..., depsgraph: "Depsgraph | None" = None) -> tuple[bool, Vector, Vector, int]: ...
    def convert_space(self, *, pose_bone=None, matrix: Matrix | None = None, from_space: str = "WORLD", to_space: str = "WORLD") -> Matrix: ...
    def is_modified(self, scene: "Scene", settings: str) -> bool: ...
    def update_from_editmode(self) -> bool: ...
class ObjectModifiers(PropCollection["Modifier"]):
    def new(self, name: str, type: str) -> "Modifier": ...; def remove(self, modifier: "Modifier") -> None: ...
    def clear(self) -> None: ...; def move(self, from_index: int, to_index: int) -> None: ...; active: "Modifier | None"
class ObjectTags(PropCollection["Tag"]):
    def new(self, type: str, name: str = "") -> "Tag": ...; def remove(self, tag: "Tag") -> None: ...
    def move(self, from_index: int, to_index: int) -> None: ...
class VertexGroups(PropCollection["VertexGroup"]):
    def new(self, *, name: str = "Group") -> "VertexGroup": ...; def remove(self, group: "VertexGroup") -> None: ...; active: "VertexGroup | None"
class VertexGroup(Struct):
    name: str; index: int
    def add(self, index: Sequence[int], weight: float, type: str) -> None: ...
    def remove(self, index: Sequence[int]) -> None: ...; def weight(self, index: int) -> float: ...
class MaterialSlot(Struct): material: "Material | None"; link: str; name: str; slot_index: int

# mesh.py / mesh_views.py
class Mesh(ID):
    vertices: "MeshVertices"; edges: "MeshEdges"; loops: "MeshLoops"; polygons: "MeshPolygons"
    loop_triangles: "MeshLoopTriangles"; loop_triangle_polygons: np.ndarray
    attributes: "AttributeGroupMesh"; uv_layers: "UVLoopLayers"; color_attributes: "AttributeGroupMesh"
    vertex_normals: PropCollection; polygon_normals: PropCollection; corner_normals: PropCollection
    materials: "IDMaterials"; is_editmode: bool; shape_keys: None; auto_texspace: bool
    q_meshdata: MeshData; q_edit: EditMesh | None
    def from_pydata(self, vertices: ArrayLike, edges: ArrayLike, faces: Sequence[Sequence[int]], shade_flat: bool = True) -> None: ...
    def update(self, calc_edges: bool = False, calc_edges_loose: bool = False) -> None: ...
    def validate(self, verbose: bool = False, clean_customdata: bool = True) -> bool: ...
    def validate_material_indices(self) -> bool: ...
    def transform(self, matrix: Matrix | ArrayLike, shape_keys: bool = False) -> None: ...
    def flip_normals(self) -> None: ...; def clear_geometry(self) -> None: ...; def calc_loop_triangles(self) -> None: ...
    def set_sharp_from_angle(self, *, angle: float = ...) -> None: ...
    def shade_smooth(self) -> None: ...; def shade_flat(self) -> None: ...     # [I] confirm existence in 5.2
    def count_selected_items(self) -> tuple[int, int, int]: ...
class MeshVertex(Struct): co: Vector; normal: Vector; select: bool; hide: bool; index: int          # COLUMN/VIRTUAL
class MeshEdge(Struct): vertices: tuple[int, int]; select: bool; hide: bool; use_seam: bool; is_loose: bool; key: tuple[int, int]; index: int
class MeshLoop(Struct): vertex_index: int; edge_index: int; normal: Vector; index: int
class MeshPolygon(Struct): vertices: tuple[int, ...]; loop_start: int; loop_total: int; material_index: int
    use_smooth: bool; select: bool; hide: bool; normal: Vector; center: Vector; area: float; index: int; edge_keys: list[tuple[int, int]]
class MeshLoopTriangle(Struct): vertices: tuple[int, int, int]; loops: tuple[int, int, int]; polygon_index: int; normal: Vector; area: float
class MeshVertices(PropCollection[MeshVertex]): def add(self, count: int) -> None: ...   # MeshEdges/MeshLoops/MeshPolygons same
class Attribute(Struct):
    name: str; domain: str; data_type: str; is_internal: bool; is_required: bool; data: PropCollection
class AttributeGroupMesh(PropCollection[Attribute]):
    def new(self, name: str, type: str, domain: str) -> Attribute: ...; def remove(self, attribute: Attribute) -> None: ...
    active: Attribute | None; active_index: int; active_color: Attribute | None; default_color_name: str; render_color_index: int
class UVLoopLayers(PropCollection["MeshUVLoopLayer"]):
    def new(self, *, name: str = "UVMap", do_init: bool = True) -> "MeshUVLoopLayer": ...; def remove(self, layer) -> None: ...; active: "MeshUVLoopLayer | None"
class IDMaterials(PropCollection["Material | None"]):
    def append(self, material: "Material | None") -> None: ...; def pop(self, *, index: int = -1) -> "Material | None": ...; def clear(self) -> None: ...

# material.py / camera.py / light.py / world.py / image.py / text.py
class Material(ID): diffuse_color: tuple[float, float, float, float]; metallic: float; roughness: float
    specular_intensity: float; blend_method: str; use_backface_culling: bool; pass_index: int; use_nodes: bool; node_tree: None
class Camera(ID): type: str; lens: float; lens_unit: str; sensor_width: float; sensor_height: float; sensor_fit: str
    clip_start: float; clip_end: float; ortho_scale: float; shift_x: float; shift_y: float
    angle: float; angle_x: float; angle_y: float; display_size: float; dof: "CameraDOFSettings"
class CameraDOFSettings(Struct): use_dof: bool; focus_object: "Object | None"; focus_distance: float; aperture_fstop: float
class Light(ID): type: str; color: tuple[float, float, float]; energy: float; use_shadow: bool
    specular_factor: float; diffuse_factor: float; volume_factor: float; use_nodes: bool
class PointLight(Light): shadow_soft_size: float
class SunLight(Light): angle: float
class SpotLight(Light): spot_size: float; spot_blend: float; show_cone: bool; shadow_soft_size: float
class AreaLight(Light): shape: str; size: float; size_y: float
class World(ID): color: tuple[float, float, float]; use_nodes: bool; node_tree: None
class Image(ID): size: tuple[int, int]; pixels: PropCollection; filepath: str; source: str; is_float: bool; channels: int
    def scale(self, width: int, height: int) -> None: ...; def update(self) -> None: ...; def pack(self) -> None: ...  # pack: stub
class Text(ID): lines: PropCollection; filepath: str; is_modified: bool
    def as_string(self) -> str: ...; def from_string(self, string: str) -> None: ...; def clear(self) -> None: ...; def write(self, text: str) -> None: ...

# collection.py / scene.py / view_layer.py
class Collection(ID): objects: "CollectionObjects"; children: "CollectionChildren"; all_objects: tuple[Object, ...]
    hide_viewport: bool; hide_render: bool; hide_select: bool; color_tag: str; instance_offset: Vector
class CollectionObjects(PropCollection[Object]): def link(self, object: Object) -> None: ...; def unlink(self, object: Object) -> None: ...
class CollectionChildren(PropCollection[Collection]): def link(self, child: Collection) -> None: ...; def unlink(self, child: Collection) -> None: ...
class Scene(ID): camera: Object | None; world: World | None; frame_start: int; frame_end: int; frame_current: int; frame_step: int
    frame_float: float; render: "RenderSettings"; unit_settings: "UnitSettings"; tool_settings: "ToolSettings"; cursor: "View3DCursor"
    collection: Collection; view_layers: "ViewLayers"; objects: tuple[Object, ...]; gravity: Vector; use_gravity: bool
    def frame_set(self, frame: int, subframe: float = 0.0) -> None: ...
class RenderSettings(Struct): engine: str; resolution_x: int; resolution_y: int; resolution_percentage: int; fps: int; fps_base: float; filepath: str
class UnitSettings(Struct): system: str; scale_length: float; length_unit: str; system_rotation: str; mass_unit: str; time_unit: str; temperature_unit: str
class ToolSettings(Struct): mesh_select_mode: tuple[bool, bool, bool]; use_snap: bool; transform_pivot_point: str
class View3DCursor(Struct): location: Vector; rotation_mode: str; rotation_euler: Euler; rotation_quaternion: Quaternion; matrix: Matrix
class ViewLayer(Struct): name: str; use: bool; objects: "LayerObjects"; layer_collection: "LayerCollection"
    active_layer_collection: "LayerCollection"; depsgraph: Depsgraph
    def update(self) -> None: ...
class LayerObjects(PropCollection[Object]): active: Object | None; selected: tuple[Object, ...]
class LayerCollection(Struct): name: str; collection: Collection; children: PropCollection["LayerCollection"]
    exclude: bool; hide_viewport: bool; is_visible: bool
class ViewLayers(PropCollection[ViewLayer]): def new(self, name: str) -> ViewLayer: ...; def remove(self, layer: ViewLayer) -> None: ...

# generator.py / tag.py / modifier.py — §5.5 (+ built-ins QZ_GEN_CUBE, QZ_GEN_UV_SPHERE, QZ_GEN_ARRAY, QZ_TAG_PROTECTION, QZ_TAG_LOOKAT, ARRAY, TRIANGULATE)

# operator.py / event.py
class Operator(Struct):
    bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_description: ClassVar[str]; bl_options: ClassVar[set[str]]
    bl_undo_group: ClassVar[str]; bl_property: ClassVar[str]; bl_translation_context: ClassVar[str]
    properties: "OperatorProperties"; layout: "UILayout"; options: "OperatorOptions"; has_reports: bool
    @classmethod
    def poll(cls, context: "Context") -> bool: ...
    def invoke(self, context: "Context", event: "Event") -> set[str]: ...
    def execute(self, context: "Context") -> set[str]: ...
    def modal(self, context: "Context", event: "Event") -> set[str]: ...
    def cancel(self, context: "Context") -> None: ...; def check(self, context: "Context") -> bool: ...
    def draw(self, context: "Context") -> None: ...
    @classmethod
    def description(cls, context: "Context", properties: "OperatorProperties") -> str: ...
    def report(self, type: set[str], message: str) -> None: ...
    @classmethod
    def poll_message_set(cls, message: str, *args: Any) -> None: ...
    def as_keywords(self, *, ignore: Iterable[str] = ()) -> dict[str, Any]: ...
class OperatorProperties(Struct): ...
class OperatorFileListElement(Struct): name: str     # PropertyGroup-like
class OperatorOptions(Struct): is_invoke: bool; is_repeat: bool; is_repeat_last: bool; use_cursor_region: bool
class Event(Struct): type: str; value: str; mouse_x: int; mouse_y: int; mouse_region_x: int; mouse_region_y: int
    shift: bool; ctrl: bool; alt: bool; oskey: bool; is_repeat: bool; unicode: str; ascii: str

# ui.py
class DrawExtensionMixin:
    @classmethod
    def append(cls, draw_func: Callable) -> None: ...
    @classmethod
    def prepend(cls, draw_func: Callable) -> None: ...
    @classmethod
    def remove(cls, draw_func: Callable) -> None: ...
    @classmethod
    def is_extended(cls) -> bool: ...
class Panel(DrawExtensionMixin, Struct):
    bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_space_type: ClassVar[str]; bl_region_type: ClassVar[str]
    bl_category: ClassVar[str]; bl_context: ClassVar[str]; bl_options: ClassVar[set[str]]; bl_parent_id: ClassVar[str]; bl_order: ClassVar[int]
    layout: "UILayout"; is_popover: bool; text: str
    @classmethod
    def poll(cls, context: "Context") -> bool: ...
    def draw(self, context: "Context") -> None: ...; def draw_header(self, context: "Context") -> None: ...
    def draw_header_preset(self, context: "Context") -> None: ...
class Menu(DrawExtensionMixin, Struct):
    bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_options: ClassVar[set[str]]; layout: "UILayout"
    @classmethod
    def poll(cls, context: "Context") -> bool: ...
    def draw(self, context: "Context") -> None: ...
    def draw_preset(self, context: "Context") -> None: ...
    def path_menu(self, searchpaths: Sequence[str], operator: str, *, props_default=None, prop_filepath: str = "filepath",
                  filter_ext=None, filter_path=None, display_name=None, add_operator=None, add_operator_props=None) -> None: ...
class Header(DrawExtensionMixin, Struct): bl_idname: ClassVar[str]; bl_space_type: ClassVar[str]; bl_region_type: ClassVar[str]; layout: "UILayout"
    def draw(self, context: "Context") -> None: ...
class UIList(DrawExtensionMixin, Struct): bl_idname: ClassVar[str]; layout_type: str; list_id: str
    filter_name: str; use_filter_invert: bool; use_filter_sort_alpha: bool; use_filter_sort_reverse: bool; bitflag_filter_item: int
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index: int = 0, flt_flag: int = 0) -> None: ...
    def draw_filter(self, context, layout) -> None: ...
    def filter_items(self, context, data, property: str) -> tuple[list[int], list[int]]: ...
class UI_UL_list(UIList):
    @staticmethod
    def filter_items_by_name(pattern: str, bitflag: int, items, propname: str = "name", flags=None, reverse: bool = False) -> list[int]: ...
    @staticmethod
    def sort_items_by_name(items, propname: str = "name") -> list[int]: ...

# prefs.py / wm.py / file_handler.py / misc_kinds.py
class Preferences(Struct): addons: "Addons"; filepaths: "PreferencesFilePaths"; edit: "PreferencesEdit"; view: Struct; system: Struct; inputs: Struct; experimental: Struct
class Addons(PropCollection["Addon"]): def new(self) -> "Addon": ...; def remove(self, addon: "Addon") -> None: ...
class Addon(Struct): module: str; preferences: "AddonPreferences | None"
class AddonPreferences(Struct): bl_idname: ClassVar[str]; layout: "UILayout"
    def draw(self, context: "Context") -> None: ...
class PreferencesFilePaths(Struct): temporary_directory: str; script_directories: PropCollection; asset_libraries: PropCollection
class PreferencesEdit(Struct): use_global_undo: bool; undo_steps: int
class WindowManager(ID): windows: PropCollection["Window"]; keyconfigs: "KeyConfigurations"; operators: PropCollection[Operator]; clipboard: str
    def modal_handler_add(self, operator: Operator) -> bool: ...
    def fileselect_add(self, operator: Operator) -> None: ...
    def invoke_props_dialog(self, operator: Operator, *, width: int = 300, title: str = "", confirm_text: str = "", cancel_default: bool = False, text_ctxt: str = "", translate: bool = True) -> set[str]: ...
    def invoke_props_popup(self, operator: Operator, event: Event) -> set[str]: ...
    def invoke_confirm(self, operator: Operator, event: Event, *, title: str = "", message: str = "", confirm_text: str = "", icon: str = "NONE", text_ctxt: str = "", translate: bool = True) -> set[str]: ...
    def invoke_search_popup(self, operator: Operator) -> None: ...
    def popup_menu(self, draw_func: Callable, *, title: str = "", icon: str = "NONE") -> None: ...
    def progress_begin(self, min: float, max: float) -> None: ...; def progress_update(self, value: float) -> None: ...; def progress_end(self) -> None: ...
    def event_timer_add(self, time_step: float, *, window: "Window | None" = None) -> "Timer": ...
    def event_timer_remove(self, timer: "Timer") -> None: ...
class Window(Struct): screen: "Screen"; scene: "Scene"; view_layer: "ViewLayer"; workspace: "WorkSpace"; width: int; height: int
class Screen(ID): areas: PropCollection; is_animation_playing: bool
class WorkSpace(ID): object_mode: str; tools: PropCollection
class KeyConfigurations(PropCollection["KeyConfig"]): addon: "KeyConfig"; user: "KeyConfig"; default: "KeyConfig"; active: "KeyConfig"
class KeyConfig(Struct): name: str; keymaps: "KeyMaps"
class KeyMaps(PropCollection["KeyMap"]):
    def new(self, name: str, *, space_type: str = "EMPTY", region_type: str = "WINDOW", modal: bool = False, tool: bool = False) -> "KeyMap": ...
    def find(self, name: str, *, space_type: str = "EMPTY", region_type: str = "WINDOW") -> "KeyMap | None": ...
class KeyMap(Struct): name: str; space_type: str; region_type: str; keymap_items: "KeyMapItems"
class KeyMapItems(PropCollection["KeyMapItem"]):
    def new(self, idname: str, type: str, value: str, *, any: bool = False, shift: int = 0, ctrl: int = 0, alt: int = 0, oskey: int = 0, key_modifier: str = "NONE", direction: str = "ANY", repeat: bool = False, head: bool = False) -> "KeyMapItem": ...
    def remove(self, item: "KeyMapItem") -> None: ...
class KeyMapItem(Struct): idname: str; type: str; value: str; active: bool; properties: OperatorProperties; shift: int; ctrl: int; alt: int; oskey: int
class FileHandler(Struct): bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_import_operator: ClassVar[str]
    bl_export_operator: ClassVar[str]; bl_file_extensions: ClassVar[str]
    @classmethod
    def poll_drop(cls, context: "Context") -> bool: ...
class GizmoGroup(Struct): ...; class Gizmo(Struct): ...; class WorkSpaceTool(Struct): ...; class AssetShelf(Struct): ...
class RenderEngine(Struct): ...; class KeyingSetInfo(Struct): ...   # registerable stubs (misc_kinds.py)
```

#### `quartz.ops`, `quartz.ui`, `quartz.io`, `quartz.app`, `quartz.utils`, `quartz.path`, `quartz.extras`, `quartz.factory`

```python
# ops/namespace.py / runner.py
class OpsNamespace:
    def __init__(self, *, prefix: str = "quartz.ops", registry: TypeRegistry = REGISTRY) -> None: ...
    def __getattr__(self, submodule: str) -> "OpsSubmodule": ...; def __dir__(self) -> list[str]: ...
class OpsSubmodule:
    def __getattr__(self, name: str) -> "OperatorCallable": ...; def __dir__(self) -> list[str]: ...
class OperatorCallable:
    bl_options: set[str]
    def __call__(self, *args: str | bool, **kwargs: Any) -> set[str]: ...
    def poll(self, *args: str) -> bool: ...
    def idname(self) -> str: ...; def idname_py(self) -> str: ...; def get_rna_type(self) -> RNAStruct: ...
EXEC_CONTEXTS: frozenset[str]; RETURN_STATUSES: frozenset[str]
def call_operator(op_cls: type[Operator], exec_context: str = "EXEC_DEFAULT", undo: bool | None = None, *,
                  properties: Mapping[str, Any] | None = None, event: Event | None = None,
                  context: Context | None = None, prefix: str = "quartz.ops") -> set[str]: ...
def op_idname_to_rna(idname: str) -> str: ...; def op_rna_to_idname(rna_name: str) -> str: ...
def validate_op_idname(idname: str) -> None: ...

# ui/layout.py / auto_layout.py / draw.py
@dataclass
class LayoutIssue: code: str; detail: str; call: str
class UILayout:      # signatures of §6.6 (prop, operator, label, row, column, split, box, panel, menu, separator, template_list, …)
    issues: list[LayoutIssue]
    def __init__(self, *, kind: str = "root", context: Context | None = None, strict: bool = False) -> None: ...
    def to_dict(self) -> dict[str, Any]: ...
def auto_layout(layout: UILayout, struct: Struct, *, groups: Iterable[str] | None = None) -> None: ...
def draw_class(cls: type, context: Context | None = None, *, synthetic_area: str | None = None) -> UILayout: ...
def synthetic_area(space_type: str) -> ContextManager[Context]: ...

# io/qzfile.py / codec.py / upgrade.py
FORMAT_VERSION: int
class FileFormatError(ValueError): ...
def save(filepath: str | os.PathLike, main: Main | None = None, *, compress: bool = True) -> None: ...
def load(filepath: str | os.PathLike, *, into: Main | None = None) -> Main: ...
def struct_to_json(struct: Struct) -> dict[str, Any]: ...; def struct_from_json(cls: type[Struct], data: Mapping[str, Any]) -> Struct: ...
def encode_value(spec: ParamSpec, value: Any) -> Any: ...; def decode_value(spec: ParamSpec, raw: Any) -> Any: ...
def upgrade_params(cls: type[Struct], params: dict[str, Any], from_version: int) -> dict[str, Any]: ...

# app/__init__.py (+ handlers.py, translations.py, timers.py, settings.py)
version: tuple[int, int, int]; version_string: str; background: bool; binary_path: str; tempdir: str
handlers: HandlerLists; timers: TimerQueue; translations: ModuleType; settings: "Settings"
def trusted() -> bool: ...
@dataclass
class Settings: rollback_on_operator_error: bool = True; strict_layout: bool = False; undo_steps: int = 32
# translations
def pgettext(msgid: str, msgctxt: str | None = None) -> str: ...      # identity
def pgettext_iface(msgid: str, msgctxt: str | None = None) -> str: ...; def pgettext_tip(...) -> str: ...
def pgettext_rpt(...) -> str: ...; def pgettext_data(...) -> str: ...; def pgettext_n(msgid: str, msgctxt: str | None = None) -> str: ...
def register(module_name: str, translations_dict: Mapping[str, Mapping[tuple[str, str], str]]) -> None: ...
def unregister(module_name: str) -> None: ...
contexts: NamedTuple; contexts_C_to_py: Mapping[str, str]; locale: str; locales: tuple[str, ...]
def locale_explode(locale: str) -> tuple[str | None, str | None, str | None, str | None, str | None]: ...

# utils/
def register_class(cls: type) -> None: ...; def unregister_class(cls: type) -> None: ...
def register_classes_factory(classes: Sequence[type]) -> tuple[Callable[[], None], Callable[[], None]]: ...
def register_submodule_factory(module_name: str, submodule_names: Sequence[str]) -> tuple[Callable[[], None], Callable[[], None]]: ...
def escape_identifier(string: str) -> str: ...; def unescape_identifier(string: str) -> str: ...
def flip_name(name: str, strip_digits: bool = False) -> str: ...
def user_resource(resource_type: str, *, path: str = "", create: bool = False) -> str: ...
def resource_path(type: str, *, major: int | None = None, minor: int | None = None) -> str: ...
def script_path_user() -> str: ...
def script_paths(*, subdir: str | None = None, user_pref: bool = True, check_all: bool = False, use_user: bool = True) -> list[str]: ...
def extension_path_user(package: str, *, path: str = "", create: bool = False) -> str: ...
def execfile(filepath: str, *, mod: ModuleType | None = None) -> ModuleType: ...
def modules_from_path(path: str, loaded_modules: set[str]) -> list[ModuleType]: ...
def register_cli_command(id: str, execute: Callable[[list[str]], int]) -> object: ...; def unregister_cli_command(handle: object) -> None: ...
def register_manual_map(manual_hook: Callable) -> None: ...; def unregister_manual_map(manual_hook: Callable) -> None: ...
def register_preset_path(path: str) -> bool: ...; def unregister_preset_path(path: str) -> bool: ...
def preset_paths(subdir: str) -> list[str]: ...; def preset_find(name: str, preset_path: str, *, display_name: bool = False, ext: str = ".py") -> str | None: ...
def register_tool(tool_cls: type, *, after: object = None, separator: bool = False, group: bool = False) -> None: ...   # only records
def unregister_tool(tool_cls: type) -> None: ...
def time_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> "timedelta": ...
def time_to_frame(time: "timedelta | float", *, fps: float | None = None, fps_base: float | None = None) -> float: ...
def smpte_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> str: ...
def smpte_from_seconds(time: float, *, fps: float | None = None, fps_base: float | None = None) -> str: ...
# utils/units.py
def to_value(unit_system: str, unit_category: str, str_input: str, *, str_ref_unit: str | None = None) -> float: ...
def to_string(unit_system: str, unit_category: str, value: float, *, precision: int = 3, split_unit: bool = False, compatible_unit: bool = False) -> str: ...
# utils/previews.py
class ImagePreview(Struct): icon_id: int; image_size: tuple[int, int]; icon_size: tuple[int, int]; is_icon_custom: bool
class ImagePreviewCollection(dict[str, ImagePreview]):
    def new(self, name: str) -> ImagePreview: ...; def load(self, name: str, filepath: str, filetype: str, force_reload: bool = False) -> ImagePreview: ...
    def clear(self) -> None: ...; def close(self) -> None: ...
def new() -> ImagePreviewCollection: ...; def remove(pcoll: ImagePreviewCollection) -> None: ...

# path.py
def abspath(path: str, *, start: str | None = None, library: object = None) -> str: ...
def relpath(path: str, *, start: str | None = None) -> str: ...
def basename(path: str) -> str: ...; def clean_name(name: str, *, replace: str = "_") -> str: ...
def display_name(name: str, *, has_ext: bool = True, title_case: bool = True) -> str: ...
def display_name_from_filepath(name: str) -> str: ...; def display_name_to_filepath(name: str) -> str: ...
def ensure_ext(filepath: str, ext: str, *, case_sensitive: bool = False) -> str: ...
def is_subdir(path: str, directory: str) -> bool: ...
def module_names(path: str, *, recursive: bool = False, package: str = "") -> list[tuple[str, str]]: ...
def native_pathsep(path: str) -> str: ...; def reduce_dirs(dirs: Sequence[str]) -> list[str]: ...; def resolve_ncase(path: str) -> str: ...
extensions_image: frozenset[str]; extensions_movie: frozenset[str]; extensions_audio: frozenset[str]

# extras/
class ImportHelper:        # filepath, filter_glob, check_existing annotated
    filename_ext: ClassVar[str]
    def invoke(self, context: Context, _event: Event) -> set[str]: ...
    def check(self, _context: Context) -> bool: ...
class ExportHelper(ImportHelper): ...
def orientation_helper(axis_forward: str = "Y", axis_up: str = "Z") -> Callable[[type], type]: ...
def axis_conversion(from_forward: str = "Y", from_up: str = "Z", to_forward: str = "Y", to_up: str = "Z") -> Matrix: ...
def axis_conversion_ensure(operator: Operator, forward_attr: str, up_attr: str) -> bool: ...
def unpack_list(list_of_tuples: Iterable[Sequence[Any]]) -> list[Any]: ...; def unpack_face_list(list_of_tuples) -> list[Any]: ...
def path_reference(filepath: str, base_src: str, base_dst: str, mode: str = "AUTO", copy_subdir: str = "", copy_set: set | None = None, library=None) -> str: ...
def poll_file_object_drop(context: Context) -> bool: ...
class AddObjectHelper:     # align, location, rotation annotated + poll
    @classmethod
    def poll(cls, context: Context) -> bool: ...
def object_data_add(context: Context, obdata: ID | None, operator: Operator | None = None, name: str | None = None) -> Object: ...
def object_add_grid_scale(context: Context) -> float: ...
def object_add_grid_scale_apply_operator(operator: Operator, context: Context) -> None: ...
def world_to_camera_view(scene: Scene, obj: Object, coord: Sequence[float]) -> Vector: ...
# anim_utils / view3d_utils: bpy_extras signatures; body → QuartzNotImplementedError (deferred)

# factory.py
def build_factory_scene(main: Main) -> Scene: ...
def build_empty(main: Main) -> Scene: ...
```

### 12.3 Layer 3 — shims, loader and CLI

Internal order: `quartz.compat` (+ `tools/gen_compat_tables.py`) → `compat/bpy` (types, props,
utils, ops, app, path, msgbus) → `compat/mathutils` → `compat/bpy_extras`, `addon_utils`,
`rna_prop_ui`, `idprop`, `bl_math` → `compat/bmesh` → stubs `gpu/gpu_extras/blf/bl_ui/bl_operators`
→ `quartz.addons` → `quartz.cli` → sweep and goldens.
Exit criterion: the 4 easy wins enable/disable cleanly; ≥ 30/38 templates run; `addon-
sweep` generates a report; `compat_coverage.md` is generated; thinness and layer tests are green.

```python
# quartz/compat/__init__.py
COMPAT_DIR: Path
SHIM_MODULE_PREFIXES: tuple[str, ...]   # bpy, mathutils, bmesh, bpy_extras, addon_utils, bl_math, rna_prop_ui, idprop, gpu, gpu_extras, blf, bl_ui, bl_operators, bl_ext
@dataclass
class CompatState: target: tuple[int, int, int]; strict: bool; restrict_register: bool; active: bool
def activate(*, target: tuple[int, int, int] = (5, 2, 2), strict: bool = True, restrict_register: bool = True,
             session: Session | None = None) -> CompatState: ...
def ensure_active() -> CompatState: ...
def deactivate(*, purge_modules: bool = True) -> None: ...
def is_active() -> bool: ...; def state() -> CompatState | None: ...
def current_data() -> Main | RestrictedData: ...; def current_context() -> Context | RestrictedContext: ...
# quartz/compat/mapping.py
BPY_TYPE_ALIASES: Mapping[str, str]
def ui_placeholder_names() -> frozenset[str]: ...
def placeholder_class(name: str) -> type: ...
def coverage() -> Mapping[str, str]: ...
# quartz/compat/messages.py
def format_message(kind: str, **fields: Any) -> str: ...      # paraphrased texts, bpy prefix

# compat/bpy/__init__.py  — submodules types, props, utils, ops, app, path, msgbus; __getattr__ for data/context
# compat/bpy/props.py     — same 11 functions as Blender; FILTER: kwargs ∉ BPY_KWARGS → TypeError; type= must be a class
# compat/bpy/types.py     — __getattr__/__dir__ of §7.4
# compat/bpy/ops.py       — ops = OpsNamespace(prefix="bpy.ops") exposed as a module (__getattr__)
# compat/bpy/app/__init__.py — version, version_file, version_string, version_cycle, background, factory_startup,
#                              binary_path, tempdir, debug*, driver_namespace, online_access, handlers, timers, translations, icons
# compat/bpy/utils/__init__.py — re-export of quartz.utils (+ previews, units)
# compat/mathutils/__init__.py — Vector, Matrix, Quaternion, Euler, Color + submodules
# compat/bmesh/__init__.py — new(use_operators: bool = True) -> BMesh; from_edit_mesh(mesh) -> BMesh;
#                            update_edit_mesh(mesh, *, loop_triangles: bool = True, destructive: bool = True) -> None; types, ops, utils, geometry
# compat/addon_utils.py   — paths(), modules(*, module_cache=..., refresh=True), check(name), check_extension(name),
#                           enable(name, *, default_set=False, persistent=False, refresh_handled=False, handle_error=None),
#                           disable(name, *, default_set=False, refresh_handled=False, handle_error=None),
#                           disable_all(), reset_all(*, reload_scripts=False), module_bl_info(mod, *, info_basis=None), modules_refresh()

# quartz/addons/
@dataclass
class AddonCandidate: module_name: str; path: Path; kind: str; repo: str | None; bl_info: dict | None; manifest: "Manifest | None"; problems: list[str]
def read_bl_info(path: Path, *, fast: bool = True) -> dict | None: ...
def normalize_bl_info(info: Mapping[str, Any], module_name: str) -> dict[str, Any]: ...
@dataclass
class Manifest: schema_version: str; id: str; name: str; tagline: str; version: str; type: str; maintainer: str
    license: tuple[str, ...]; blender_version_min: str; blender_version_max: str | None = None; website: str | None = None
    copyright: tuple[str, ...] = (); permissions: Mapping[str, str] = ...; tags: tuple[str, ...] = (); platforms: tuple[str, ...] = ()
    wheels: tuple[str, ...] = (); build: Mapping[str, Any] | None = None; raw: Mapping[str, Any] = ...
def read_manifest(path: Path) -> Manifest: ...
def validate_manifest(data: Mapping[str, Any], *, strict: bool = True) -> list[str]: ...
def synthesize_bl_info(manifest: Manifest) -> dict[str, Any]: ...
def scan_paths(paths: Iterable[Path], *, include_extensions: bool = True) -> list[AddonCandidate]: ...
def default_paths(session: Session) -> list[Path]: ...
def restricted(session: Session) -> ContextManager[None]: ...
@dataclass
class AddonReport: module_name: str; kind: str; status: str; error: str | None; traceback: str | None
    missing_symbols: list[str]; registered: list[str]; leaked: list[str]; ignored_props: list[str]
    layout_issues: list[dict]; warnings: list[str]; seconds: float
    def to_json(self) -> dict[str, Any]: ...
class AddonManager:
    paths: list[Path]; repos: dict[str, Path]
    def __init__(self, session: Session) -> None: ...
    def add_path(self, path: Path, *, kind: str = "addons", repo: str = "user_default") -> None: ...
    def modules(self, *, refresh: bool = False) -> list[ModuleType]: ...
    def enable(self, module_name: str, *, default_set: bool = False, persistent: bool = False, refresh_handled: bool = False,
               handle_error: Callable[[BaseException], None] | None = None, lenient: bool = False) -> ModuleType | None: ...
    def disable(self, module_name: str, *, default_set: bool = False, refresh_handled: bool = False,
                handle_error: Callable[[BaseException], None] | None = None) -> None: ...
    def check(self, module_name: str) -> tuple[bool, bool]: ...
    def check_extension(self, module_name: str) -> bool: ...
    def disable_all(self) -> None: ...; def reset_all(self, *, reload_scripts: bool = False) -> None: ...
    def module_bl_info(self, mod: ModuleType, *, info_basis: Mapping | None = None) -> dict[str, Any]: ...
    def draw_all(self, module_name: str, *, synthetic_areas: bool = True) -> list[dict]: ...
    def last_report(self, module_name: str) -> AddonReport | None: ...
@dataclass
class ScanResult: path: Path; bl_info: dict | None; manifest: Manifest | None; symbols: dict[str, int]; predicted: dict[str, str]
def static_scan(path: Path) -> ScanResult: ...
@dataclass
class SweepResult: reports: list[AddonReport]; started: str; seconds: float
    def to_json(self) -> dict[str, Any]: ...; def to_markdown(self) -> str: ...
def sweep(roots: Sequence[Path], *, templates: Path | None = None, timeout: float = 60.0, draw: bool = True,
          python: str = sys.executable, filter: str | None = None) -> SweepResult: ...

# quartz/cli/
def main(argv: Sequence[str] | None = None) -> int: ...
def build_parser() -> argparse.ArgumentParser: ...
# cmd_*.py: def run(args: argparse.Namespace) -> int
```

---

## 13. Risks

| # | Risk | Prob./impact | Mitigation |
|---|---|---|---|
| 1 | **Cost of the descriptor + coercion** in heavy add-ons (FBX/glTF make millions of accesses) | medium/high | `__slots__`, fast path for `STORE` without callbacks, `foreach_*` vectorized per `COLUMN`, recorded benchmarks (§11.5) |
| 2 | **Description that is too rich** becomes bureaucracy (every param with 20 fields) | medium/medium | sensible defaults; optional C4D fields; free extras in `ui`; lint only for built-in types |
| 3 | **Wrapped vectors** (`v = ob.location` stays bound; `ob.location = ...` changes `v`) have subtle semantics | high/medium | specific goldens (`sc_wrapped_math`); documented `copy()`; validity checked (`is_valid` after removing the owner) |
| 4 | **float32 vs float64 differences** with add-ons that compare exact values | low/low | tolerance in the goldens; future option to quantize writes in `ParamStore` to float32 for props with a geometry subtype |
| 5 | **Python 3.14 vs 3.13** (lazy annotations, removed modules) | medium/medium | `annotationlib` per class; tests with `from __future__ import annotations`; sweep records stdlib `ImportError` separately |
| 6 | **Global state pollution** between add-ons/tests (`sys.modules`, registry, type extension) | high/high | one subprocess per add-on in the sweep; `registry.snapshot/restore`; `bpy` fixture that purges modules |
| 7 | **Long tail** of 304 single-group symbols (bpy_usage §0) | certain/medium | `QuartzNotImplementedError` with the symbol name; priority driven by the sweep ranking; no silent "ghost" objects outside `UILayout` |
| 8 | **Clean-room**: temptation to port Blender algorithms or data (primitives, Suzanne, messages, `bl_ui`) | medium/high | only facts and names; `test_cleanroom.py`; primitives compared by invariants, not by order; PR review with checklist |
| 9 | **Journal-based undo** with arrays written in place outside the API | medium/medium | read-only arrays by default; writes only via `writable()/set()/foreach_set`; edit mode with snapshot |
| 10 | **Two representations in edit mode** (EditMesh vs MeshData) out of sync | medium/medium | same rule as Blender (`update_from_editmode`, `bmesh.update_edit_mesh`); round-trip tests |
| 11 | **Name collision** of Quartz extensions with add-on props | low/medium | rule of §7.6 (add-on wins, permanent `q_` alias) |
| 12 | **Global registry vs several sessions** | medium/low | documented: classes are global; sessions isolate only data; tests use snapshot |
| 13 | **Scope** (generators, tags, depsgraph) delaying Path A | medium/high | generators/tags/modifiers with only 2–3 built-ins; everything that does not serve the sweep is deferred; Layer 3 starts as soon as §12.2 has ID/props/registry/ops |
| 14 | **`[I]` signatures** (load_post, handlers, matrix_world, Euler) wrong | medium/medium | each has a golden scenario before becoming a contract |

---

## 14. What to defer (outside this milestone)

- GUI, viewport, renderer, real GPU (`gpu/blf` only stubs); `RenderEngine`/`HydraRenderEngine`
  register but do not render.
- **Animation**: `Action`, `FCurve`, `Keyframe`, slots/channelbags, `keyframe_insert`, drivers, NLA
  (Tier 2 — next milestone; the data path is already ready for it).
- Armatures, bones, pose, constraints (rigify and part of FBX/glTF).
- `Curve`/`TextCurve`/`SurfaceCurve` as data-blocks (the Layer 1 `CurveData` is ready; the
  `io_curve_svg` only **enables** in this milestone, importing SVG comes in the next).
- Node system (`NodeTree`, sockets, Geometry Nodes, shader nodes), capsules and derivation.
- Full Fields/MoGraph (effectors, `FieldList`); the `InstanceCloud` exists only as a container.
- Deformer-as-child, hierarchical tags, script-objects (`ScriptGenerator/ScriptTag`) with trust.
- Assets (marking, catalogs, version/update policy), linked libraries, overrides,
  takes.
- Modal with real events, automatic timers and msgbus (manual pump/flush only).
- Wheels, permissions and remote extension repositories; package installation.
- Reading/writing `.blend`; own importers/exporters (native OBJ/glTF).
- Real `bpy.utils.previews`, `mathutils.noise` with Blender's values, `primitive_monkey_add`.
- Optimizations: per-scene vectorized transforms, real BVH (starts as numpy brute force),
  differential undo for edit mode.

---

## 15. The 10 most important decisions

1. **Description as the single source**: `bpy.props` annotations compile into an immutable,
   inheritable `Description` (bpy fields + C4D metadata: `group`, `parent`, `enabled_if/visible_if`, `widget`,
   `dirty`, `storage`, `uid`, `since`) that feeds access, validation, `bl_rna`, UI, `.qz`, undo,
   the parity dump and the sweep.
2. **Three storage bindings** (`STORE`, `VIRTUAL`, `COLUMN`): element structs
   (`MeshVertex.co`) and `foreach_get/set` are driven by the description and vectorized in numpy.
3. **Blender data model + C4D extensions**: Object + data, collections, view layers, `Main` with
   `.NNN`/255 bytes/users/`ReferenceError`; removal policy in `ParamSpec`
   (`on_remove=DELETE_OWNER`); ordered children, `Object.tags` for behavior only, `Generator`
   as a data-block (honest `type='GENERATOR'` in the shim too), canonical `modifiers` stack,
   geometry always in attributes.
4. **Isolated Layer 1** (math/props/geometry only stdlib+numpy, no cross imports, verified by
   AST) with **adapter injection** by Layer 2 (owned vectors, ID resolver, context).
5. **Measured math**: Vector/Quaternion/Euler/Color in a `float64` list with "wrapped" instances
   that write to the owner; Matrix in numpy; `quartz.math.batch` for arrays; float64 is a
   declared divergence.
6. **Global registry, per-session data; atomic registration driven by `KindSpec`** (the `bl_*`
   are also validated by a class description); owner scope detects leaks;
   annotations read with `annotationlib` per MRO class (Python 3.14).
7. **Exceptions inherit from the built-in that Blender raises** (ValueError/RuntimeError/TypeError/
   AttributeError/ReferenceError): compatibility for free; paraphrased messages; tests
   compare types.
8. **Thin shims with only four forms** (IDENTITY, FILTER, VIEW, STUB), rule verified by
   test; `bpy.types` is a view of the registry + ≈1977 UI placeholders generated from names in the dump;
   collisions with Quartz extensions resolved in favor of the add-on with a `q_` alias.
9. **Undo via transaction journal** at the single mutation points (off in background, as in
   Blender) + **per-channel dirty counters** that feed the `Depsgraph` facade and evaluation
   in named stages (EXPRESSION/GENERATOR/FINAL active in this milestone).
10. **Loader, CLI and tests as a measurement system**: `bl_info` via AST without import, manifest with
    `tomllib`, emulated `RestrictBlend`, synthetic `bl_ext` packages; `python -m quartz`
    (`info/scan-addon/enable-addon/run-script/addon-sweep/describe/dump-api`); sweep in a subprocess
    that draws all panels/menus into a recording `UILayout` validating `layout.prop` against
    descriptions; headless Blender goldens versioned in `data/golden`, `dump_bpy_api.py`
    itself rerun in Quartz and description parity vs `blender_api_dump.json`.

---

## Appendix A — Usage sketches (original)

Simple Blender add-on running on Quartz:

```python
import quartz, quartz.compat
quartz.compat.activate()
import bpy

class QZDEMO_PG_settings(bpy.types.PropertyGroup):
    count: bpy.props.IntProperty(name="Count", default=3, min=1, max=10)

class QZDEMO_OT_spawn(bpy.types.Operator):
    bl_idname = "qzdemo.spawn"
    bl_label = "Spawn Cubes"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        for i in range(context.scene.qzdemo.count):
            bpy.ops.mesh.primitive_cube_add(size=0.5, location=(i, 0, 0))
        return {"FINISHED"}

bpy.utils.register_class(QZDEMO_PG_settings)
bpy.utils.register_class(QZDEMO_OT_spawn)
bpy.types.Scene.qzdemo = bpy.props.PointerProperty(type=QZDEMO_PG_settings)
bpy.context.scene.qzdemo.count = 50          # clamped to 10, update called
assert bpy.ops.qzdemo.spawn() == {"FINISHED"}
```

Native generator with automatic UI:

```python
import quartz
from quartz.props import FloatProperty, IntProperty
from quartz.types import Generator
from quartz.geometry import GeometrySet, primitives

class Stairs(Generator):
    bl_idname = "QZ_GEN_STAIRS"
    bl_label = "Stairs"
    steps: IntProperty(default=8, min=1, soft_max=64, group="shape", dirty="GEOMETRY")
    rise: FloatProperty(default=0.18, min=0.0, unit="LENGTH", group="shape", dirty="GEOMETRY")
    def evaluate(self, ctx):
        parts = [primitives.cube(size=1.0).copy() for _ in range(self.steps)]
        ...   # positions each step with quartz.math.batch.transform_points
        return GeometrySet(mesh=merged)

quartz.utils.register_class(Stairs)
gen = quartz.data.generators.new("Stairs", kind="QZ_GEN_STAIRS")
ob = quartz.data.objects.new("Stairs", gen)
quartz.context.scene.collection.objects.link(ob)
layout = quartz.ui.UILayout()
quartz.ui.auto_layout(layout, gen)           # draws the "shape" group from the description
```
