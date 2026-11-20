# Quartz — Initial Milestone Architecture (Path C + Path A)

> Quartz — author: **D1on1n**. Normative document for the initial milestone. Date: 2026-10-22.
> This document records **decisions and justifications**. The exact public API (names, signatures,
> return values, errors, owner of each file) is in [`docs/CONTRACTS.md`](CONTRACTS.md), which is the single
> source of truth between parallel implementers. In case of conflict, **CONTRACTS.md wins**.
>
> Judged inputs: `docs/design/proposal_bpy-faithful.md` (proposal **A**),
> `docs/design/proposal_c4d-description-hybrid.md` (proposal **B**),
> `docs/design/proposal_minimal-incremental.md` (proposal **C**), `docs/research/*.md`,
> `data/bpy_usage.json`, `data/blender_api_dump.json` and a new probe by the judge
> (`tools/probe_judge_facts.py` → `data/blender_facts_judge.json`, see §17).
>
> Clean-room hygiene: no piece of Blender code (GPL) or Cinema 4D resource
> (proprietary) was copied. API names appear only as identifiers; factual values
> (defaults, counts, enum names) come from executed introspection, never from source code.

---

## 0. Executive summary

**Decision:** the Quartz chassis is that of proposal **C (minimal-incremental)** — a single core in
pure Python + numpy, shaped like `bpy`, in which `compat/` is almost only re-exporting the *same*
objects (`bpy.types.Object is quartz.types.Object`). On top of this chassis come measured grafts:

| Graft | Origin | Why |
|---|---|---|
| Hierarchy of typed exceptions that inherit from the builtin exception Blender raises | A, B | Add-on code keeps catching `TypeError`/`RuntimeError`; the native side gets rich types |
| Compatibility profile **generated from the dump** (names, kwargs, enums, context members) + phantom surface with telemetry for missing symbols | A + C | Immediate coverage of the ~1977 UI names and the 40 `bpy.data` collections; the log of missing symbols becomes a backlog ordered by real usage |
| C4D *description* metadata as native kwarg `meta=` + `Description` view (groups, parent, `enabled_if`, dirty channel, `uid`, `since`) | B (shape), C (seam) | Single source for future automatic UI, serialization and documentation, at no cost to `bpy` |
| Removal policy as pointer data (`on_remove="DELETE_OWNER"` on `Object.data`) | B | Remove the mesh → remove the objects that use it, with no scattered code |
| Per-channel dirty counters with a monotonic clock behind the `Depsgraph` facade | B, C | Cheap, testable, and a basis for future incremental evaluation/undo |
| `.qz` scene serialization (zip + JSON + `.npy`) driven by property definitions, with `q_schema_version` + `q_upgrade()` | B (C4D's *disklevel*) | Milestone requirement ("scene serialization") with schema migration from day 1 |
| Validation of `layout.prop()` against the real properties, recording `LayoutIssue` | B | Automatic detector of "property the add-on expects and Quartz lacks" in the sweep |
| Broad owner tracking (classes, props on types, menu extensions, handlers) and leak report | A | The `UNREGISTER_CLEAN` sweep level measures real cleanliness |
| Schema tests against the dump (props of built-in types and operators) + contract tests using the dump probes as oracle | A, C | Hundreds of already-collected facts become tests without running Blender |
| `q_` prefix rule for Quartz-only members on bpy-shaped types | B | Avoids collision with properties that add-ons hang on the types |
| Lifecycle phases (`startup_post`, `shutdown_pre`, `shutdown_post`) | A, B, C (C4D) | Cheap, already useful in the CLI |

What does **not** go into this milestone (deferred with a named seam): generators, tags, Fields/MoGraph,
nodes, animation, armatures, modifier evaluation, GUI/viewport/render/GPU (§15).

---

## 1. Context, constraints and what was verified

- Project: **Quartz**, a personal 3D application by the author D1on1n that merges ideas from Cinema 4D 2026.3.1 and
  Blender 5.2.2 LTS. Single write root: `D:/Claude/reverseEngineering/Quartz`.
- Current milestone: headless core + CLI + tests. **Path C** (native `quartz` API, shaped like bpy)
  and **Path A** (`compat/` shims that let simple Blender add-ons run on top of Quartz).
- Allowed dependencies: stdlib + numpy (+ pytest). `.venv` Python: 3.14.7 (Blender uses 3.13).
- Code rules: no comments and no docstrings in any code file; identifiers in English; human documentation in English.

**Verified by running in this step (by the judge):**

1. Full reading of the three proposals, the three research notes and the structure of the two data JSONs
   (throwaway scripts in the scratchpad, nothing written to the project by them).
2. An original probe in headless Blender 5.2.2 (`--background --factory-startup`, user resources
   redirected to `tmp/blender_user`, 120 s timeout), which resolved 30+ items that the proposals marked as **[I]**
   (inference). Result versioned in
   `data/blender_facts_judge.json`; summary in §17.

**Not verified:** no Quartz code exists yet; all APIs are contracts. Sweep targets
are targets, not measurements.

---

## 2. Evaluation of the proposals

### 2.1 Criteria and weights

| Criterion | Weight | What it measures |
|---|---|---|
| Adherence to measured usage | 25 % | Prioritizes what `bpy_usage.json` shows (Tier 1/2, implicit `context`/`layout` surface, native menus, `mode_set`) |
| Fidelity to real bpy semantics | 20 % | How much of the observed contract (`bpy_contract.md` + probes) is reproduced, and how honest the divergences are |
| Long-term fit for the C4D × Blender merge | 20 % | Whether the architecture accepts descriptions, generators, tags, fields, assets without a rewrite |
| Implementation risk **in this milestone** | 20 % | Volume, new mechanisms, dependencies between parts, chance of blocking Path A (high score = low risk) |
| Testability | 15 % | Available oracles (dump, goldens, sweep), isolation, architecture tests |

### 2.2 Scores (1–5)

| Criterion | A — bpy-faithful | B — c4d-description-hybrid | C — minimal-incremental |
|---|---|---|---|
| Adherence to measured usage | 5 | 4 | 5 |
| Fidelity to bpy | 5 | 4 | 4 |
| C4D × Blender merge | 3 | 5 | 3 |
| Risk in the milestone (5 = low) | 2 | 2 | 4,5 |
| Testability | 5 | 4 | 5 |
| **Weighted total** | **4,00** | **3,80** | **4,30** |

### 2.3 Comments

**A — bpy-faithful.** The most faithful: `float32` at rest, `matrix_world` stale until evaluation,
profile generated from the dump, phantom surface with telemetry, portable Blender×Quartz probes with
`deviations.toml`. Weak points for *this* milestone: a `quartz.rna` package of 14 files, a profile generator,
a phantom factory, a depsgraph that must evaluate to keep `matrix_world` stale, full native bmesh
and 28 operators — too much machinery before the first add-on runs.
The C4D merge is limited to accepted and stored kwargs.

**B — c4d-description-hybrid.** The best long-term vision: compiled, inheritable description, three
storage bindings (`STORE/VIRTUAL/COLUMN`), `on_remove` in the specification, undo via transaction journal with
copy-on-write arrays, `.qz` driven by the description, real generators and tags. High risk: the description compiler,
the undo journal and the generators are three new systems that Path A does not need now; `float64` in `mathutils` is a
visible divergence (Blender stores `float32`: `Vector((0.1,0,0)).x == 0.10000000149011612`, verified).

**C — minimal-incremental.** Optimizes time to the first green sweep and the cost of refactoring:
one metaclass, descriptors, dictionaries; "derive instead of maintain" (`users`, `children`,
`matrix_world` computed on read); named seams for C4D; sweep with levels, Blender baseline
and ratchet; symmetric golden runner. Weak points: C4D appears only as a seam, and some
behaviors were left as [I] — the judge's probe resolved several of them (§17).

**Verdict.** C wins on risk and testability without losing adherence. A contributes the fidelity discipline
(typed exceptions, generated profile, telemetry, schema tests, leak report).
B contributes the shape of the description and the declarative policies, implemented as optional data inside C's
single engine — enough so that the merge does not require a rewrite.

---

## 3. Decisions (D1–D18)

| # | Decision | Justification |
|---|---|---|
| D1 | **One implementation, two facades.** `compat/*` re-exports objects from `quartz`; only Blender peculiarities live in `compat` (version 5.2.2, `RestrictBlend` visible as `bpy.data/bpy.context`, UI placeholders, `bl_ext`, `addon_utils`, `gpu`/`blf` stubs). A thinness test verifies this. | Mechanical port and zero divergence between the paths |
| D2 | **bpy vocabulary is the native one** (`bl_idname`, enums as strings, `register()/unregister()`). Quartz-only members on bpy-shaped types have the `q_` prefix; internals `_q_`. | A's golden rule + collision resolved by B |
| D3 | **Single property engine** (`quartz.props` + `quartz.rna`) for built-in types and add-ons: `_PropertyDeferred` → `PropertyDef` descriptors with the observed semantics; built-in types use the same factories. | A single place for clamp, `update`, `get/set`, enums, `maxlen`, vector wrap |
| D4 | **C4D description as optional data**: native kwarg `meta={...}` (`group`, `parent`, `enabled_if`, `visible_if`, `widget`, `dirty`, `uid`, `since`, `on_remove`, `counts_user`, `virtual_get/virtual_set`, `euler_order`) + `describe(cls) -> Description`. The compat `bpy.props` rejects `meta` with `TypeError`. | B's graft in C's format; basis for automatic UI and migration |
| D5 | **Float32 at rest, float64 in transit**: `FLOAT` props, components of `Vector/Matrix/Quaternion/Euler/Color` and geometry arrays store `float32`; computations in `float64`. | Observed fidelity (`0.10000000149011612`) with computation precision |
| D6 | **Layers verified by AST test** (§4); Layer 1 has four groups with no cross imports (app, rna, math, geometry); seams via `quartz.rna.hooks`. | Real parallelism in Layer 1 |
| D7 | **IDs with observed semantics**: unique `.NNN` names, 255 bytes UTF-8, the one renamed gets the suffix, **stable case-insensitive** order (verified), `rename()` with the 5 results of 5.2, **derived** `users` by reference scan, removal by **class swap to tombstone** (`ReferenceError`), `DELETE_OWNER` cascade. | [O] facts; deriving is simple and correct; tombstone has zero cost on the hot path |
| D8 | **Object + data as in Blender**, with `Object.data` open to registered types (`register_object_data_type`) — seam for the future C4D `Generator`. | Required by the shim; merge without a rewrite |
| D9 | **`matrix_world` computed on read (eager)**. Declared divergence: in Blender it only changes after `view_layer.update()` (verified). | Simple and correct for all code that already calls `update()`; code that depends on the stale value is rare |
| D10 | **SoA geometry in numpy** in the Blender 4+/5 attribute layout (`position`, `.edge_verts`, `.corner_vert`, `.corner_edge`, face offsets, `sharp_face`, `.select_*`, corner `FLOAT2` UV), pure in `quartz.geometry` (no ID). `quartz.types.Mesh` composes. | Single source, vectorized `foreach_get/set` |
| D11 | **Flat and atomic registry** with validation by base class (fact table), RNA name in `quartz.types`/`bpy.types`, `owner_scope` for leaks, call to class `register()/unregister()` (verified). | Research contract §2 + benign divergence (no "half registered") |
| D12 | **Operator engine with the observed contract** (positional arguments, `poll` before kwargs — verified by the call sequence —, conversion `TypeError`, clamp, `RuntimeError` for invalid return/exception/`report ERROR`, headless `INVOKE_*` → `execute`, values do not persist). Built-ins are classes registered through the public API. | Dogfooding and fidelity |
| D13 | **Context = provider table + override stack**; read-only members; the 71 profile members exist (unimplemented → `None`, as in headless); `RestrictBlend` swaps the **facades** (`quartz.data/context`, `bpy.data/context`) during import + `register()`. | Research contract §6 |
| D14 | **Single session with stable identity** (`reset()` in place). | `from bpy import data` captured earlier remains valid |
| D15 | **Undo by snapshot with preserved identity** (memfile style), disabled in background until `ed.undo_push()`. The state protocol `_q_state_get/_q_state_set` is the same as for `.qz`. | Simple and correct; transaction journal stays in the ROADMAP |
| D16 | **`.qz` file** (zip: `manifest.json`, `data.json`, `arrays/*.npy`) driven by property definitions, with `q_schema_version` + `q_upgrade()` per type. `.blend` is neither read nor written. | "Scene serialization" requirement; C4D *disklevel* idea |
| D17 | **Compat driven by a profile generated from the dump** (`quartz/compat/blender_5_2.json`, only names/kwargs/enums/defaults) + UI placeholders + inert phantom types + missing-symbol log; strict mode for contract tests, lenient for the sweep. | Wide surface that is cheap and honest |
| D18 | **Sweep first**: harness in an isolated subprocess, levels `STATIC → … → UNREGISTER_CLEAN`, Blender's own baseline, ratchet; Blender goldens versioned in `data/golden/`. | The backlog comes from data, not from opinion |

---

## 4. Layers, layout and import rules

### 4.1 Tree (summary; exact owners in CONTRACTS.md §0.4)

```
Quartz/
├─ pyproject.toml            # metadata + pytest (pythonpath ".", import-mode importlib, markers)
├─ quartz/
│  ├─ __init__.py  _version.py  __main__.py      # lazy facade (PEP 562)
│  ├─ path.py                 # = bpy.path                                   ┐
│  ├─ app/                    # handlers, timers, msgbus, translations,      │ Layer 1, group "app"
│  │                          # settings, paths                              ┘
│  ├─ errors.py  props.py     # typed exceptions; = bpy.props                ┐ Layer 1, group "rna"
│  ├─ rna/                    # Struct, PropertyDef, collections, idprops,   │
│  │                          # RNA views, Description, hooks, data paths    ┘
│  ├─ math/                   # = mathutils (Vector, Matrix, …)              ─ Layer 1, group "math"
│  ├─ geometry/               # SoA numpy mesh, primitives, normals         ─ Layer 1, group "geometry"
│  ├─ types/                  # data-blocks and structs (= bpy.types)          ┐
│  ├─ depsgraph.py  registry.py  ui.py  utils/                               │
│  ├─ session.py  contexts.py  ops.py  undo.py  io/  testing.py              │ Layer 2
│  └─ operators/              # built-in operators                           ┘
│  ├─ compat/                 # activate()/deactivate(), generated profile   ┐
│  ├─ extras/  bmesh/         # = bpy_extras, = bmesh (native)               │ Layer 3
│  ├─ addons/                 # loader for add-ons and extensions            │
│  └─ cli.py  sweep.py  scan.py                                              ┘
├─ compat/                    # shims; NOT a package; goes into sys.path via quartz.compat.activate()
│  ├─ bpy/  mathutils/  bmesh/  bpy_extras/  idprop/  bl_ui/  bl_operators/
│  ├─ gpu/  gpu_extras/  blf.py  aud.py  addon_utils.py  bl_math.py  rna_prop_ui.py
├─ tools/   tests/   data/   docs/   tmp/ (scratch)
```

### 4.2 Import rules (verified by `tests/arch/test_layering.py`)

| Group | Modules | May import |
|---|---|---|
| L1-app | `quartz._version`, `quartz.path`, `quartz.app.*` | stdlib |
| L1-rna | `quartz.errors`, `quartz.props`, `quartz.rna.*` | stdlib, numpy, the group itself |
| L1-math | `quartz.math.*` | stdlib, numpy, the group itself |
| L1-geometry | `quartz.geometry.*` | stdlib, numpy, the group itself |
| facade | `quartz/__init__.py` | only `quartz._version` at module level (the rest lazy) |
| L2 | `quartz.types.*`, `quartz.depsgraph`, `quartz.registry`, `quartz.ui`, `quartz.utils.*`, `quartz.session`, `quartz.contexts`, `quartz.ops`, `quartz.undo`, `quartz.io.*`, `quartz.testing`, `quartz.operators.*` | stdlib, numpy, L1, L2 |
| L3 | `quartz.compat.*`, `quartz.extras.*`, `quartz.bmesh.*`, `quartz.addons.*`, `quartz.cli`, `quartz.sweep`, `quartz.scan` | everything in `quartz` |
| shims | `compat/**` | stdlib, `quartz.*`, other top-level modules of `compat/` — **not** numpy |

Imports inside functions count. The seam between Layer 1 groups and between Layer 1 and 2 is
`quartz.rna.hooks` (installed by Layer 2/3) and `quartz.path.set_blend_filepath_provider`.

### 4.3 Why Layer 1 also has `app` and the `Struct` core

The request fixes Layer 1 as "math/props/geometry". Two inclusions are deliberate:

- `quartz.app` (handler lists, timer queue, msgbus, translations, settings, paths) is
  primitive and dependency-free; placing it in L1 takes a task off L2 and lets the operator engine
  and the scene consume something already ready.
- `quartz.rna.Struct` (the `bpy_struct`) is inseparable from the property system: the descriptors
  need an owner, and `path_from_id`, `is_property_set`, `keys()`, idprops and `bl_rna` are API of the
  property system. The **ID core** (names, users, removal) stays in L2.

---

## 5. Data model

### 5.1 `Struct` (= `bpy_struct`)

- Per-instance state (created in `__new__`, so a user's `__init__` works without `super()`):
  `_p` (values of RNA props), `_p_set` (assigned names), `_q_idprops` (dictionary
  properties), `_q_owner`/`_q_path` (owner and path for `id_data`/`path_from_id`).
- No `__slots__` (class swap for tombstone and for light subtypes).
- Two storages, as in 5.x (verified): values of `bpy.props` do **not** appear in
  `id.keys()`; `ob["x"] = 3.5` does not become `ob.x`. In `PropertyGroup` instances, `keys()` lists the
  values already written (verified).
- Built-in types reject unknown attributes (`AttributeError "'Object' object has no attribute
  'x'"`, verified); registrable user classes (Operator, Panel, PropertyGroup — verified
  for PropertyGroup) accept them.

### 5.2 IDs and `BlendData`

- `ID` with `name`, `name_full`, `id_type`, `session_uid`, `users`, `use_fake_user`, `is_evaluated`,
  `original`, `library=None`, `is_embedded_data`…; `copy()`, `rename()`, `user_remap()`,
  `evaluated_get()`.
- **Names**: unique per collection with `.001`…; cap of 255 UTF-8 bytes at a character boundary; empty
  → default name of the type; renaming to an existing name gives the suffix to the one renamed.
- **Order**: each collection iterates sorted by `name.casefold()`, stable on ties (verified:
  `_x, a, A, a10, a2, b, B, Zed`; re-sorts after renaming).
- **Users (derived)**: count `Object.data`, link in a collection (object or child collection),
  `Scene.world`, entries of `Mesh.materials`, `Window.scene`, `bpy.props` pointers to an ID and
  fake user; they do **not** count `Scene.camera` or `Object.parent` (all verified).
- **Removal**: undoes all references; pointers marked `DELETE_OWNER` remove the owner
  (removing the mesh removes the objects that use it; `objects.remove` leaves the mesh orphaned — verified);
  the instance swaps class to a tombstone whose access raises `ReferenceError "StructRNA of type
  Mesh has been removed"` (including a second `remove`).
- `BlendData` exposes the **40 collections** of 5.2; unimplemented ones are phantom collections (empty,
  `new()` → `NotImplementedInQuartz`, access noted in the missing log).

### 5.3 Object, transforms and organization

- `Object.type` derived from the class of `data` (`None` → `EMPTY`), read-only (verified).
- `matrix_basis = T(loc+Δloc) · R_total · S(scale⊙Δscale)`; `matrix_local = matrix_parent_inverse ·
  matrix_basis`; `matrix_world = parent.matrix_world · matrix_local`. Euler with order `'XYZ'` applies
  X, then Y, then Z (`R = Rz·Ry·Rx`, verified numerically). Assigning `matrix_world` decomposes
  immediately (verified). Assigning `parent` does not recompute the inverse (the child "jumps", verified).
- Blender collections (object in several collections, `Collection.objects` in **link order**:
  the factory's `scene.objects` is `Cube, Light, Camera`, verified); selection/visibility per
  `ViewLayer` (bases); unlinked object → `select_get()` false (verified).
- Modes: `object.mode_set` (Tier 1) switches the mode; enum items depend on the type of the active object (mesh:
  `OBJECT, EDIT, SCULPT, VERTEX_PAINT, WEIGHT_PAINT, TEXTURE_PAINT`; `POSE` on a mesh →
  `TypeError`, verified); `context.mode == "EDIT_MESH"` in edit mode (verified).

### 5.4 Mesh

`quartz.geometry.MeshGeometry` is the truth; `quartz.types.Mesh` composes (`Mesh.q_geometry`). Cheap
proxies (`MeshVertex(mesh, i)`), `foreach_get/set` via a mapping table (list or numpy),
`from_pydata` (quad → 4/4/4/1; edges compared as a set), `update(calc_edges=…)`,
`validate()`, normals, triangulation, `shade_flat/shade_smooth` (exist in 5.2, verified).
Counts of the default primitives (verified) are in CONTRACTS §1.5.

### 5.5 Math

`Vector`, `Matrix`, `Quaternion`, `Euler`, `Color` with data in `numpy.float32`, computations in
`float64`, *wrapped* instances that write to the owner (`ob.location.x = 1`), `freeze()`/`hash`
(mutable → `TypeError`, verified), `Vector == tuple` is **false** (verified), exact `repr` of 5.2
(verified), `Matrix(4×4) @ Vector(3)` homogeneous (verified), `Vector @ Matrix` as a row
vector (verified), `*` element-wise and `@` dot product between vectors (verified).

---

## 6. Property system

- **Factories** (`quartz.props.*Property`) do not create anything: they return `_PropertyDeferred(function,
  keywords)` with only the kwargs passed (verified). Accepted kwargs = those of 5.2.2 in 5.2.2 + `meta` (native).
- **Registration by annotation** (read with `annotationlib` for each class in the MRO, because of the lazy
  evaluation in 3.14; `from __future__ import annotations` strings are evaluated in the module). The old
  assignment `x = IntProperty()` is ignored (verified). Mixins (`ImportHelper`) work through the MRO.
- **Dynamic extension**: `Scene.x = PointerProperty(...)` defines it immediately; `del Scene.x` removes it
  (`hasattr` false, verified). Access through the class returns the `_PropertyDeferred`.
- **Value semantics** (verified): silent clamp; `update(self, context)` on **every**
  assignment (even with an equal or clamped value); only `get` → read-only; `maxlen` truncates in UTF-8 bytes
  at a character boundary (`maxlen=5` with `"ÃÃÃ…"` → `"ÃÃ"`); `IntProperty` accepts `bool`
  but not `float`; `FloatProperty` accepts `int`; `BoolProperty` accepts `0/1` and rejects `2`; invalid enum
  → `TypeError` listing the valid ones; `ENUM_FLAG` → `set`; **enum `get/set` callbacks
  work with the item's integer value** (verified); `PointerProperty(type=Object)` rejects `Mesh`
  with `TypeError`.
- **Vector wrap** by subtype (installed by Layer 2 in the `wrap_array` hook):
  `TRANSLATION/DIRECTION/VELOCITY/ACCELERATION/XYZ/XYZ_LENGTH/COORDINATES` → `Vector`,
  `EULER` → `Euler` (order = the owner's `rotation_mode` when it is Euler, verified), `QUATERNION` →
  `Quaternion`, `COLOR/COLOR_GAMMA` with 3 components → `Color`, `MATRIX` → `Matrix`; the rest → `PropArray`.
- **Computed properties of the built-in types** use `meta={"virtual_get": f, "virtual_set": g}`
  (final value, not the raw form of bpy's `get/set`).
- **Description** (`describe(cls)`): ordered view of the `PropertyDef`s with groups, children by `parent`,
  `is_enabled()`/`is_visible()` and `to_rna_dict()` in the dump's schema.

---

## 7. Registration, operators, context, undo, handlers, UI, depsgraph and file

### 7.1 Registration

Observed rules (all in CONTRACTS §2.3): class already registered → `ValueError`; another class with the
same `bl_idname` replaces it; unregistering an unregistered / plain class → `RuntimeError`;
missing `bl_label` → `AttributeError`; operator `bl_idname` with exactly 1 dot, `[a-z0-9_]`,
leading digit accepted, maximum 60; invalid `bl_space_type` enum → `TypeError`; nonexistent `bl_parent_id`
→ `RuntimeError`; name outside `_PT_/_MT_/_HT_/_UL_` → warning only; `type=` of
Pointer/Collection requires an already registered `PropertyGroup` → `ValueError`. Divergence: **atomic**
registration (Blender may leave the class half registered).

### 7.2 Operators

`quartz.ops.<mod>.<op>(*args, **kwargs)` with the same callable as `bpy.ops`. Sequence and messages
in CONTRACTS §2.5. Divergence: `poll` is called **once** per call (Blender calls it twice;
this is not a contract). The built-ins declare **all** the properties the dump lists for them
(they accept the kwargs that add-ons pass) and implement the semantics of the documented subset;
`mesh.primitive_monkey_add` exists with a false `poll` (Suzanne's data does not enter Quartz).

### 7.3 Context and RestrictBlend

Providers for `scene`, `view_layer`, `object/active_object`, `selected_objects`, `mode`,
`window_manager`, `preferences`, …; `area/region/space_data` are `None` (headless, verified);
`window` is not `None` (verified). `temp_override(**members)` pushes and restores; unknown
keys are accepted and ignored (verified). During an add-on's import + `register()`,
`quartz.data/context` and `bpy.data/context` become restricted objects (only `window_manager` and
`preferences`).

### 7.4 Undo

Stack of snapshots (identity preserved: the same Python objects return to the state; removed IDs
are "resurrected" by reverting the tombstone). Starts off in background; `ed.undo` with a false `poll`
and the observed message; `ed.undo_push()` turns it on. `bl_options={'UNDO'}` pushes after `FINISHED`.

### 7.5 Handlers, timers, msgbus, translations

The 39 Blender lists (plain Python lists, stable identity) + Quartz phases.
`persistent` sets `_bpy_persistent` (verified). Timers and msgbus never fire on their own
(verified); `pump()`/`flush()` are native extras. `pgettext_*` is identity in `en_US`; `contexts`
with the 60 observed fields.

### 7.6 Headless UI

`UILayout` **recorder** (all 116 functions of 5.2 accepted; the most used ones with an explicit
signature; `prop()` validates the property and records `LayoutIssue`). `Panel/Menu/Header/UIList` with
real `append/prepend/remove/is_extended`. `draw_ui(cls, context)` draws and never propagates an exception
from user code (records `DRAW_EXCEPTION`). Blender UI placeholders (`VIEW3D_MT_mesh_add`…)
are created by compat from the profile; the future Quartz GUI must **reuse these
identifiers**.

### 7.7 Depsgraph and dirtiness

Each ID has per-channel counters (`DATA, TRANSFORM, GEOMETRY, SHADING, SELECT, HIERARCHY,
VISIBILITY`) stamped by a global clock. `Depsgraph.update()` derives `updates`
(`is_updated_transform/geometry/shading`) from the stamps and fires `depsgraph_update_pre/post`.
`evaluated_get()` returns the original (there is no modifier evaluation in the milestone).

### 7.8 `.qz` file

Zip with `manifest.json` (format, versions), `data.json` (IDs with `type`, `name`, `schema`, `state`
with references `{"__id__": n}` and arrays `{"__array__": "arrays/k.npy"}`) and `arrays/*.npy`
(`allow_pickle=False`). Loading calls `q_upgrade()` when the saved schema is older.
`wm.save_as_mainfile`/`wm.open_mainfile` use this format (divergence: no `.blend`).

---

## 8. Mapping `compat/` → `quartz`

| Blender | Quartz | Form |
|---|---|---|
| `bpy.types.*` | `quartz.types.*` (+ `bpy_struct`, `bpy_prop_collection`, `bpy_prop_array`) | identity + view (registration by RNA name, UI placeholders, ghost types) |
| `bpy.props.*` | `quartz.props.*` | filter (rejects `meta`) |
| `bpy.data`, `bpy.context` | `quartz.session.api_data()/api_context()` | identity (swapped in RestrictBlend) |
| `bpy.ops` | `quartz.ops` | identity (messages prefixed with `bpy.ops`) |
| `bpy.utils` (+ `previews`, `units`) | `quartz.utils` | identity |
| `bpy.path` | `quartz.path` | identity |
| `bpy.app` (+ `handlers`, `timers`, `translations`, `icons`) | `quartz.app` | view (version 5.2.2, `build_*`, libs `supported=False`) |
| `bpy.msgbus` | `quartz.app.msgbus` | identity (no `flush`) |
| `mathutils` (+ `geometry`, `kdtree`, `bvhtree`, `noise`, `interpolate`) | `quartz.math` | identity |
| `bl_math` | `quartz.math.scalar` | identity |
| `bmesh` | `quartz.bmesh` | identity |
| `bpy_extras` | `quartz.extras` | identity (subset) |
| `addon_utils` | `quartz.addons.manager` | facade |
| `idprop.types`, `rna_prop_ui` | `quartz.rna.idprops` | identity / glue |
| `bl_ui.utils.PresetPanel`, `bl_operators.presets.AddPresetBase` | original minimal mixins | compat only |
| `gpu`, `gpu_extras`, `blf`, `aud` | — | stubs (no-op state; creating a resource → `NotImplementedInQuartz`) |
| `bl_ext.<repo>.<pkg>` | loader's synthetic packages | compat only |

The profile `quartz/compat/blender_5_2.json` is **generated** by `tools/gen_compat_profile.py` from
`data/blender_api_dump.json` (only names, kwargs, enums, defaults — interface facts).

---

## 9. Add-on and extension loader

- Discovery as `module_names` (`.py` files except `__init__`, folders with `__init__.py`, ignores
  hidden ones and `modules`); `bl_info` read **without importing** (from the 1st line that starts with `bl_info` to the 1st
  blank line, `ast.literal_eval`); `module_bl_info` fills in the observed base fields and removes
  author emails (verified).
- Extensions: `blender_manifest.toml` validated with `tomllib` (required fields, `type`, `id`, versions,
  `[build]`), module `bl_ext.<repo>.<id>` with synthetic packages, synthetic `bl_info` from the manifest;
  native extensions: `quartz_manifest.toml` → `qz_ext.<repo>.<id>`. Wheels/permissions: read and
  warned about, not installed.
- `enable/disable/check` in the observed order (`default_set` before the import; import + `register()`
  under RestrictBlend and `owner_scope`; failure → `handle_error`, removed from `sys.modules`; `disable`
  keeps the module in `sys.modules`; `check()` → `(loaded_default, loaded_state)`).
- Python 3.14: annotations are "pinned" right after the add-on import (evaluated and stored), to
  approximate the eager semantics of 3.13.
- Security and Rule 1: the sweep runs each target in a `-I -B -X utf8` subprocess, with `cwd` and user directory
  inside `tmp/`, timeout per target; no network, wheels or system clipboard.

---

## 10. CLI

`python -m quartz info | scan-addon | enable-addon | run-script | addon-sweep`. Codes: `0` ok,
`1` operation failure (or regression in the ratchet), `2` usage error, `3` internal error. Human-readable output in English,
JSON with keys in English. Details in CONTRACTS §3.5.

---

## 11. Testing strategy

1. **Architecture** (`tests/arch`): header of every `.py`, layers by AST, clean-room (no
   GPL/Blender/Maxon headers), leanness of `compat/`.
2. **Unit tests per layer**: L1 without a session (fake owners for props); L2 with the `qz` fixture
   (isolated session, registry restored); L3 with the `bpy` fixture (compat active).
3. **Schema against the dump** (without Blender): props of the built-in types and built-in operators
   equal to the dump (type, subtype, unit, size, default, limits, items) with an explicit list of
   divergences.
4. **Contract** (`tests/contract`): each probe of the dump (`registration_errors`, `operator_basic`,
   `property_semantics`, `id_semantics`, `context_semantics`, `undo_and_handlers`,
   `ui_extension_points`, `addon_lifecycle`, …) and the judge's facts reproduced in Quartz and
   compared (exception types and chosen fragments, never the whole text).
5. **Goldens** (`tests/golden` + `data/golden/*.blender.json`): the same script runs in Blender
   (tool with timeout, regenerates only with an explicit flag) and in Quartz; comparison with tolerance.
6. **Sweep** (`-m sweep`, opt-in via `QUARTZ_RUN_SWEEP=1`): own fixtures always; Blender's `addons_core`
   and `templates_py` when available; Blender baseline and ratchet.

Standard command: `D:/Claude/reverseEngineering/Quartz/.venv/Scripts/python.exe -m pytest -q`.
`blender` tests only run with `QUARTZ_RUN_BLENDER=1`. Temporary test files go in
`tmp/pytest/run-<pid>` (configured in `conftest.py`), never outside the project.

---

## 12. Implementation plan (summary)

Three layers; within each layer the tasks have disjoint files and can be implemented in
parallel from CONTRACTS. Each layer ends in a **gate**: the entire suite up to that point green.

- **L1 — Foundations**: `l1-scaffold-app` (pyproject, conftest, facade, `quartz.path`,
  `quartz.app`, architecture tests), `l1-math`, `l1-rna-props`, `l1-geometry`. No dependencies
  among them.
- **L2 — Model and runtime**: `l2-idmodel` (ID, BlendData, Object, Collection, Scene/ViewLayer,
  World, WM, depsgraph — key task), `l2-datablocks` (Mesh, Material, Camera, Light, Image,
  Text), `l2-registry-ui` (registration, Operator/Panel/Menu/UIList, prefs, stubs, `UILayout`, `utils`),
  `l2-runtime` (session + factory scene, context, `ops.call`, undo, snapshot, `.qz`, `testing`),
  `l2-operators` (built-ins). `l2-datablocks` depends only on the `l2-idmodel` contract;
  `l2-runtime` and `l2-operators` are integrators (their full tests pass at the gate).
- **L3 — Compat, loader, CLI**: `l3-compat-bpy`, `l3-compat-math-extras`, `l3-bmesh`,
  `l3-addons`, `l3-cli-sweep`.

Rule for dependencies within a layer: each task imports sibling modules **only** by the names
in CONTRACTS, never creates files belonging to another task, and writes tests that isolate its own code where
possible (fake owners, test data types registered locally).

---

## 13. Deliberate divergences (go into `docs/COMPAT.md`)

1. Atomic registration (no "half registered" class).
2. `poll` called once per operator call.
3. `matrix_world` always current (Blender only updates it on evaluation).
4. Stable Python references: the same ID returns the same object (`a is b`); undo preserves
   identity; changing `light.type` swaps the class of the existing instance (Blender keeps the old
   class on the live reference, verified).
5. Error messages with their own wording (tests compare type + fragments).
6. Own ordering of edges generated by `calc_edges` and of vertices in the primitives (compared as
   a set / counts / bounding box); own UVs.
7. `primitive_monkey_add` with a false `poll` (clean-room).
8. `.blend` is neither read nor written; `.qz` instead.
9. `PropertyGroup.__getitem__` of an RNA prop returns the prop's Python value (Blender returns the raw
   IDProperty form).
10. String annotations and forward references are accepted (Python 3.14).
11. `layout.prop` validation records structured problems (Blender only prints).
12. Registration leaks are detected and reported.
13. `mathutils.noise`: only `random`, `seed_set`, `random_unit_vector` (own values); the rest
    raises `NotImplementedError`.

---

## 14. Risks and mitigation

| Risk | Mitigation |
|---|---|
| Dependencies within layer L2 (key task `l2-idmodel`) | Precise contract for `ID`/`BlendData`/type registry; `quartz.types` with lazy imports and tolerance for a missing sibling; tests with local fake types; gate at the end of the layer |
| Python 3.14 × 3.13 (lazy annotations; the trick of reassigning `__annotations__` erases annotations) | `annotationlib` per class; annotation pinning in the loader; own `orientation_helper` that merges without erasing |
| Performance (descriptors, derived O(N) `users`, per-element proxies) | numpy paths (`foreach_*`, `q_geometry`, `Attribute.q_array()`); optimize only with a benchmark |
| Erosion of compat leanness | Leanness test (imports and line budget per file) |
| Leniency masking errors | Strict mode in the contract tests; everything synthesized goes into the missing/warnings log |
| Execution of third-party code writing outside the project | `-I -B` subprocess, `cwd`/user in `tmp/`, `sys.dont_write_bytecode`, timeouts |
| GPL/proprietary contamination | Implement from the paraphrased contract; `test_cleanroom`; profile with only names/defaults |
| Remaining [I] behaviors | Each has a golden or contract test; if the golden contradicts, the golden prevails |

---

## 15. Deferred (ROADMAP)

| Item | State in the milestone | How it comes in later |
|---|---|---|
| GUI, viewport, renderer, GPU | `gpu/blf` stubs; inert `RenderEngine`; `draw_handler_add` stores and does not call | GUI reuses `UILayout` and the `*_MT_*/*_PT_*` identifiers |
| Animation (Action/slots/channelbags, FCurve, keyframes, drivers) | `keyframe_insert/driver_add` → `NotImplementedInQuartz`; ghost `bpy.data.actions` | `ANIMATION` stage of the depsgraph; data paths are already the key (C4D's DescID) |
| Generators (C4D), tags, Fields, MoGraph/`InstanceCloud` | seams: open `Object.data`, `meta`, `Description`, reserved stages; name `Object.tags` reserved | additive types `quartz.types.Generator/Tag/Field` that compat does not see |
| Modifier evaluation | `Object.modifiers` stack only as data | registry of modifier types with `evaluate(geometry, ctx)` |
| Nodes (`NodeTree`/`Node`/`NodeSocket`) | inert registrable bases | transactional copy-on-write core with a `NodeTree` face |
| Armatures, curves, grease pencil, volumes | ghost collections | data containers when the sweep asks for them |
| Incremental undo / transaction journal | full snapshot | snapshot of only the dirty IDs (counters already exist) |
| Assets, libraries, overrides, takes | `NotImplementedInQuartz` | Blender-style assets + C4D's Id/version/update policy |
| Modal with event loop | `testing.drive_modal()` for tests | GUI event loop |
| Wheels, remote repositories | "not supported" warning | own extension manager |
| `.pyi` stubs, port codemod | — | generated from the introspectable RNA |

---

## 16. Open decisions for the author (D1on1n)

1. Keep `bl_` in the native API (proposed) × accept `qz_` as an alias.
2. Eager `matrix_world` (proposed) × optional "obsolete like Blender" mode for conformance.
3. Default ghost policy in `run-script`: lenient (proposed) × strict.
4. Namespace of native extensions: `qz_ext` (proposed).
5. Language of error messages: English (proposed, like `bpy`).

---

## 17. New facts verified by the judge probe (`data/blender_facts_judge.json`)

| Fact (Blender 5.2.2 headless) | Consequence |
|---|---|
| ID collections sorted case-insensitively, stable on ties, with no "natural" ordering (`a10` before `a2`) | `naming.sort_key = str.casefold` |
| `rename()` returns `RENAMED_COLLISION_ADJUSTED`, `RENAMED_NO_COLLISION`, `RENAMED_COLLISION_FORCED` (the latter gives the exact name to the renamed one and the suffix to the other) | `ID.rename` contract |
| `users`: `Scene.world` counts; `Scene.camera` and `Object.parent` do not; `Mesh.materials` counts; add-on pointer to an ID counts; linked child collection counts | `IDRef.counts_user` table |
| `register_class` calls the class's `register()` classmethod and `unregister_class` calls `unregister()` | registration |
| `matrix_world` only changes after `view_layer.update()`; assigning `matrix_world` updates `location` immediately | documented divergence D9 |
| Euler `XYZ` → `Rz·Ry·Rx`; `ZYX` → `Rx·Ry·Rz`; numeric reference values | `quartz.math` tests |
| `repr`/`str` of `Vector`, `Matrix`, `Euler`, `Quaternion`; `Vector == tuple` false; `hash` of a mutable vector → `TypeError` | `quartz.math` contract |
| Assigning an unknown attribute to `Object` → `AttributeError`; to a `PropertyGroup` → accepted | `Struct` attribute policy |
| `IntProperty` accepts `True`, rejects `2.0`; `BoolProperty` accepts `1`, rejects `2`; `maxlen` counts bytes | coercion |
| `EnumProperty` `get/set` receive/return the item's **integer value** | enums |
| Factory scene: camera rotation/lens/clip (clip_end **100**), POINT light 1000 W radius 0.1, World color, resolution 1920×1080 at 24 fps, names `ViewLayer/WinMan/Layout`, order `Cube, Light, Camera` in the collection | `session.build_factory_scene` |
| Counts of the 9 default primitives (e.g. UV sphere 482/992/512, grid 121/220/100, torus 576/1152/576) | `quartz.geometry.primitives` |
| `mode_set(mode='POSE')` on a mesh → `TypeError` (dynamic enum); `toggle=True` works | `object.mode_set` |
| `select_all(TOGGLE)` with no selection selects everything; `duplicate` creates `Cube.001` with mesh `Cube.001`, deselects the original; `linked=True` shares the mesh | operators |
| `bpy.app.translations.contexts`: 60 fields and values | `quartz.app.translations` |
| `bpy.path.clean_name`, `display_name`, `ensure_ext`, `abspath("//…")` with no saved file | `quartz.path` |
| `escape_identifier`, `flip_name`, `smpte_from_frame(100)` | `quartz.utils` |
| `repr(bpy.data.objects) == "<bpy_collection[3], BlendDataObjects>"`; `repr` of a vertex and of the master collection | `repr` |
