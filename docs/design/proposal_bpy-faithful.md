# "bpy-faithful" architecture proposal for Quartz

> Quartz — author: **D1on1n**. Design document (one of the architecture proposals for the initial milestone).
> Date: 2026-10-22. Paths covered: **C** (native `quartz` API) and **A** (`bpy`-lite layer in `compat/`).
>
> **Status: PROPOSAL.** Nothing in this document has been implemented or executed. The signatures below
> are the intended contract, not existing code. Facts about Blender come from
> `docs/research/bpy_contract.md` (marked there as [O] observed / [L] read) and from `docs/research/bpy_usage.md` + `data/bpy_usage.json`; ideas from Cinema 4D come from
> `docs/research/c4d_model.md`. Where I state something about Blender that is **not** in the research,
> I mark it with **[I]** (an inference to be confirmed by a conformance probe, §11.3).
>
> Clean-room hygiene: the code snippets here are original, in the intended Quartz syntax.
> Blender names appear only as API identifiers.

---

## 0. Thesis and the 10 decisions

**Thesis of the "bpy-faithful" angle:** the Quartz core *is* an RNA. Typed data-blocks, properties
declared by annotation (`bpy.props`), class registration by `bl_idname`, operators called through
`quartz.ops.<mod>.<op>(...)` and a read-only `context` object are the **native** model, not an
emulation. The native API is a clean, typed restatement of that model; the `compat/` layer is almost
just a *rename*: `bpy.types.Object is quartz.types.Object`.

The 10 decisions that support this (detailed in the indicated sections):

1. **One class, two faces (§8).** `compat/bpy` re-exports the *same* objects from `quartz` — with no
   wrappers. What is exclusive to compat fits in a short list: Blender version profile
   (`bpy.app.version = (5, 2, 2)`), strict kwargs filter, "ghost" UI/type names, the `RestrictBlend`
   swap, and `gpu`/`blf` stubs.
2. **The bpy vocabulary is the native vocabulary (§1.3).** `bl_idname`, `bl_label`, `bl_options`,
   enums as strings, `quartz.props.IntProperty(...)` returning `_PropertyDeferred`, registration by
   annotation only. Porting an add-on is a fixed renaming table (`bpy`→`quartz`,
   `mathutils`→`quartz.math`, `bmesh`→`quartz.bmesh`, `bpy_extras`→`quartz.extras`,
   `addon_utils`→`quartz.addons`). "Typed" means type hints, `Literal`, stubs and **typed
   exceptions that inherit from the exact builtin exception that bpy raises**, plus additive numpy extras,
   never a different shape.
3. **Pure-Python RNA core (`quartz.rna`, §4).** `StructRNA`/`PropertyRNA` as descriptors,
   a metaclass with `is_registered`, collection of annotations across the MRO **at registration** (via `annotationlib`,
   since the venv is Python 3.14), dynamic extension `Type.prop = Prop()` / `del`, two separate stores
   (RNA values × dictionary IDProperties, as in 5.x) and the observed
   value semantics (silent clamp, `update` on every assignment, `get`/`set`, `maxlen`, `TypeError` on an
   invalid enum, `ENUM_FLAG` as a `set`). The "description" metadata from C4D enters as additive native kwargs
   (`group`, `ui_parent`, `enabled_if`) that compat rejects.
4. **ID semantics replicated as observed (§5.1).** Unique `.NNN` names, 255-byte
   UTF-8 cap, the renamed one gets the suffix, `users` and fake user, double `link` → `RuntimeError`,
   `remove()` deletes even with users and invalidates the Python object **by swapping its class for a
   tombstone** that raises `ReferenceError`. Removing a mesh deletes the objects that use it. `bpy.data` lists
   stay in alphabetical order [I, consistent with the dump: `Camera, Cube, Light`].
5. **Numpy SoA geometry in the Blender 4+/5 layout (§5.3).** Attributes per domain (`position`,
   `.edge_verts`, face offsets, `.corner_vert`, `.corner_edge`, `sharp_face`, `material_index`,
   `.select_*`, UV = corner `FLOAT2`). The pure functions live in `quartz.geometry` (layer 1, with no
   dependency on the data model). `MeshVertex` and the like are *flyweights* over the arrays.
   Storage in **float32** where the stored value is observable (`clip_start` reads
   `0.10000000149011612`, same as the dump).
6. **Faithful transforms, including the "evaluated" `matrix_world` (§5.4, §6).** `matrix_world` is
   stored and only recomputed by depsgraph evaluation (`view_layer.update()`, `frame_set`, end of
   operator, `evaluated_depsgraph_get()`), as in Blender [I]. Internally we use per-channel
   *dirty* counters (an idea from C4D) behind the bpy `Depsgraph` facade (`updates`,
   `evaluated_get`, `is_updated_*`). Selection and visibility are kept per `ViewLayer` (Base), and an
   object can be in several collections.
7. **Operator engine with the observed call contract (§7.2).** Up to 2 positionals
   (`exec_context`, `undo`), positional dict → `ValueError`, `TypeError` on kwarg/enum/type, clamp,
   false poll → `RuntimeError` with the `poll_message_set` message, invalid return / `None` /
   exception / `report ERROR` → `RuntimeError`, `INVOKE_*` without UI goes straight to `execute`, values
   do not persist between calls. The 28 built-in operators of the milestone are ordinary `Operator` classes in
   `quartz.operators`, with the property schema checked against `data/blender_api_dump.json`.
8. **Single read-only context with an override stack (§7.3).** `quartz.context` has the 75
   members of the 5.2 profile (unimplemented ones return `None`, as in headless Blender),
   `temp_override` on top of `contextvars`, a mode concept (`OBJECT`/`EDIT`) from the start because of
   `mode_set` (Tier 1), and `RestrictBlend` replicated during add-on import/register (strict
   by default, `--lenient` for debugging).
9. **Profile-driven compat with a ghost surface and telemetry (§8.4).** The names (and only the
   names) extracted from the dump generate *placeholder* menus/panels (`VIEW3D_MT_mesh_add`…), empty
   `bpy.data` collections and context members. Every access to an unimplemented API is logged
   (`ghosts='error'|'log'|'silent'`) and becomes a backlog prioritized by real usage. `activate()` and
   `deactivate()` are idempotent and reversible, which is essential for tests.
10. **Test triad (§11).** (a) Unit tests per layer plus architecture tests (import rules
    between layers, file headers, clean-room guard). (b) **Portable conformance probes**:
    the same script runs unchanged in Blender (versioned golden JSON, regenerated by a
    tool with a timeout) and in Quartz, compared with a tolerance and an explicit list of deviations.
    (c) **Add-on sweep** in isolated subprocesses (`-I -B`, sandboxed user directory,
    timeout) with levels L0–L4 over `addons_core`, `templates_py` and our own fixtures. Undo uses
    *in place* snapshots of `BlendData`, which is the same mechanism the `.quartz` file will use
    later.

---

## 1. Principles

### 1.1 Contract × accident

What we **replicate** is everything a simple add-on can observe and may depend on: names,
signatures, return types, exception **types**, order of side effects, defaults, clamps,
unique names, user counts, context members and the registration lifecycle. The research
(§13.2 of `bpy_contract.md`) lists this as "needs real behavior".

What we **do not** replicate is what is clearly an implementation accident:

| Blender 5.2.2 behavior | Quartz | Why |
|---|---|---|
| `poll` called 2× per `bpy.ops` call [O] | 1× | Not part of the contract. The research explicitly says add-ons must not depend on this |
| Class is left "half registered" if a property fails [O] | **Atomic** registration (rollback) and the same `ValueError` | It is a defect, not a contract. A new `register_class` works after the fix |
| Text of error messages | Our own wording, in English, always containing the idname/property in question | Clean-room. Tests compare the **type** + fragments we choose, not the text |
| Python objects recreated on every access (RNA wrappers) [I] | Objects are the storage itself: `a is b` holds for the same ID | Superset of the behavior. `==` still holds |
| Order of edges generated by `calc_edges` (the dump shows `[(0,3),(0,1),(1,2),(2,3)]` for a quad) | Our own deterministic order | Conformance compares edges as a **set** |
| Exact UVs of the primitives | Our own UV layout, same domain/type/name (`UVMap`, `FLOAT2`, `CORNER`) | Clean-room and low value |
| `primitive_monkey_add` | Not implemented (`NotImplementedInQuartz`) | The Suzanne mesh is Blender data; copying it would violate rule 3 |
| Reading `is_overridable` on a type property crashes Blender [O] | Works | Obvious |

Each deviation becomes an entry in `tests/conformance/deviations.toml`, with a reason. An unlisted
deviation is a bug.

### 1.2 Golden rule of the native API

> If a name exists in bpy and the same idea exists in Quartz, **the name, the signature and the semantics
> are bpy's**. Quartz only adds: new types (`Generator`, `Tag`, `Field`… in the future),
> new methods with non-colliding names (`as_array()`, `to_arrays()`), new native kwargs
> (filtered in compat) and more specific exceptions (subclasses of bpy's).

### 1.3 What "native, clean and typed" means here

- **Complete type hints** across the whole public API, enums as `typing.Literal[...]`
  (`quartz/typing.py` exports aliases such as `ObjectType`, `ModeName`, `AttributeDomain`) and, later,
  `.pyi` stubs generated from the RNA (`tools/gen_stubs.py`, deferred).
- **Typed exceptions** in `quartz.errors`, each inheriting from the builtin that bpy uses. Code written
  for Blender keeps catching the same type:

  ```python
  class QuartzError(Exception): ...
  class RegistrationError(QuartzError, ValueError): ...          # already registered / property fails to register
  class RegistrationRuntimeError(QuartzError, RuntimeError): ... # invalid bl_idname, nonexistent parent, unregister without registration
  class MissingClassAttributeError(QuartzError, AttributeError): ... # missing bl_label/bl_space_type/draw
  class ClassValidationError(QuartzError, TypeError): ...        # invalid bl_space_type enum
  class PollFailedError(QuartzError, RuntimeError): ...
  class OperatorFailedError(QuartzError, RuntimeError): ...      # invalid return, exception, report ERROR
  class OperatorNotFoundError(QuartzError, AttributeError): ...
  class PropertyTypeError(QuartzError, TypeError): ...           # unknown kwarg, wrong type/enum
  class ReadOnlyError(QuartzError, AttributeError): ...
  class RemovedStructError(QuartzError, ReferenceError): ...
  class RestrictedAccessError(QuartzError, AttributeError): ... # bpy.data/context during register
  class NotImplementedInQuartz(QuartzError, NotImplementedError): ...
  class ManifestError(QuartzError, ValueError): ...
  ```
- **Additive numpy extras**: `mesh.attributes["position"].as_array()` (live view),
  `Mesh.to_arrays()/from_arrays()`, `Vector.__array__`, `foreach_get/set` with a fast path for
  `ndarray`.
- **No second form**: there is no `obj.get_location()`, no Python enums, no numeric IDs.

---

## 2. Package layout

```
D:/Claude/reverseEngineering/Quartz/
├─ pyproject.toml            # metadata + [tool.pytest.ini_options] (markers, testpaths). No build/install.
├─ conftest.py               # puts the root on sys.path for `import quartz` without installing
├─ quartz/                   # Path C — native API
│  ├─ __init__.py            # exports types, props, utils, ops, app, path, msgbus, math, geometry; data/context (swappable)
│  ├─ __main__.py            # python -m quartz → quartz.cli.main()
│  ├─ _version.py            # VERSION = (0, 1, 0)
│  ├─ errors.py              # typed exceptions (§1.3)
│  ├─ typing.py              # Literal aliases (ObjectType, ModeName, AttributeDomain, AttributeType, ...)
│  ├─ _kernels/              # LAYER 0 — shared private pure functions, stateless
│  │  ├─ rotation.py         #   euler/quat/axis-angle ↔ 3x3 (numpy)
│  │  └─ naming.py           #   UTF-8 truncation at a character boundary, .NNN suffix, sorting
│  ├─ math/                  # LAYER 1 — equivalent to mathutils
│  │  ├─ __init__.py  _base.py  vector.py  matrix.py  quaternion.py  euler.py  color.py
│  │  ├─ geometry.py  kdtree.py  bvhtree.py  noise.py  interpolate.py
│  │  └─ scalar.py           #   equivalent to bl_math (clamp, lerp, smoothstep)
│  ├─ rna/                   # LAYER 1 — RNA core (no scene)
│  │  ├─ __init__.py  meta.py  struct.py  property.py  deferred.py  annotations.py
│  │  ├─ collection.py  array.py  idprops.py  datapath.py  registry.py  enums.py  storage.py  hooks.py
│  ├─ props.py               # LAYER 1 — BoolProperty … RemoveProperty (deferred factories)
│  ├─ geometry/              # LAYER 1 — numpy SoA mesh, pure functions
│  │  ├─ __init__.py  arrays.py  topology.py  normals.py  triangulate.py
│  │  ├─ primitives.py  transform.py  bounds.py  validate.py
│  ├─ types/                 # LAYER 2 — data-blocks and structs (the "bpy.types")
│  │  ├─ __init__.py         #   exports everything + __getattr__ over the TypeRegistry (registered classes)
│  │  ├─ id.py  blenddata.py  object.py  mesh.py  mesh_elements.py  attributes.py
│  │  ├─ material.py  camera.py  light.py  world.py  image.py  text.py
│  │  ├─ collection.py  scene.py  view_layer.py  wm.py  preferences.py
│  │  ├─ modifier.py  operator.py  addon_prefs.py  inert.py  ghosts.py
│  ├─ ui/                    # LAYER 2 — Panel/Menu/Header/UIList + recording UILayout
│  │  ├─ __init__.py  base.py  layout.py  lists.py  placeholders.py
│  ├─ runtime/               # LAYER 2 — global state, context, operator execution
│  │  ├─ __init__.py  state.py  context.py  factory.py  restrict.py  opexec.py  settings.py
│  ├─ app/                   # LAYER 2 — bpy.app
│  │  ├─ __init__.py  handlers.py  timers.py  translations.py  icons.py
│  ├─ utils/                 # LAYER 2 — bpy.utils
│  │  ├─ __init__.py  registration.py  resources.py  previews.py  units.py  misc.py
│  ├─ ops.py                 # LAYER 2 — quartz.ops namespace (bpy.ops)
│  ├─ operators/             # LAYER 2 — built-in operators (NOT called quartz/ops/: it would collide with quartz.ops.object)
│  │  ├─ __init__.py  object.py  mesh.py  transform.py  ed.py  wm.py
│  ├─ depsgraph.py           # LAYER 2 — dirty channels + Depsgraph
│  ├─ undo.py                # LAYER 2 — snapshot-based undo stack
│  ├─ msgbus.py  path.py     # LAYER 2
│  ├─ io/                    # LAYER 2 — snapshot (basis of undo; the .quartz file comes later)
│  │  ├─ __init__.py  snapshot.py
│  ├─ extras/                # LAYER 2 — equivalent to bpy_extras
│  │  ├─ __init__.py  io_utils.py  object_utils.py  view3d_utils.py  anim_utils.py
│  ├─ bmesh/                 # LAYER 2 (final, Tier 3) — native pure-Python BMesh
│  │  ├─ __init__.py  types.py  ops.py  utils.py  geometry.py  convert.py
│  ├─ testing/               # reusable test utilities (isolation, probes, comparison)
│  │  ├─ __init__.py  isolate.py  probes.py  compare.py
│  ├─ compat/                # LAYER 3 — activation of the bpy-lite layer
│  │  ├─ __init__.py  profile.py  ghosts.py  strict.py
│  │  └─ profiles/blender_5_2.json   # names/signatures/defaults only, generated from the dump by a tool
│  ├─ addons/                # LAYER 3 — add-on and extension loader
│  │  ├─ __init__.py  bl_info.py  manifest.py  discovery.py  lifecycle.py  extensions.py
│  │  ├─ owners.py  report.py  sweep.py  static_scan.py
│  └─ cli.py                 # LAYER 3
├─ compat/                   # LAYER 3 — shims. Directory put on sys.path. Has NO __init__.py.
│  ├─ bpy/
│  │  ├─ __init__.py         #   data, context (swappable); registers synthetic sys.modules
│  │  ├─ types.py  props.py  ops.py  path.py  msgbus.py
│  │  ├─ utils/__init__.py  utils/previews.py  utils/units.py
│  │  └─ app/__init__.py  app/handlers.py  app/translations.py  app/timers.py  app/icons.py
│  ├─ mathutils/__init__.py  geometry.py  kdtree.py  bvhtree.py  noise.py  interpolate.py
│  ├─ bmesh/__init__.py  types.py  ops.py  utils.py  geometry.py
│  ├─ bpy_extras/__init__.py  io_utils.py  object_utils.py  view3d_utils.py  anim_utils.py  node_utils.py  image_utils.py
│  ├─ addon_utils.py
│  ├─ idprop/__init__.py  types.py
│  ├─ bl_math.py  rna_prop_ui.py
│  ├─ bl_ui/__init__.py  utils.py                 # minimal PresetPanel/PresetMenu on top of quartz.ui
│  ├─ gpu/__init__.py  state.py  shader.py  matrix.py  types.py  texture.py  capabilities.py  platform.py
│  ├─ gpu_extras/__init__.py  batch.py  presets.py
│  └─ blf.py  aud.py                              # stubs
├─ tools/                    # existing + new (§11.7)
├─ tests/                    # §11
├─ data/                     # existing + compat_coverage.json + sweeps
└─ docs/  README.md  ARCHITECTURE.md  COMPAT.md  ROADMAP.md  research/  design/
```

Naming notes that avoid pitfalls:

- `quartz.ops` is **a module** (`ops.py`) with `__getattr__`: `quartz.ops.object` must be the
  operators submodule, not a file `quartz/ops/object.py`. That is why the built-in implementations
  live in `quartz/operators/`.
- `quartz.data` and `quartz.context` are **attributes** of `quartz/__init__.py`, never submodules, so that
  they can be swapped by `RestrictBlend`. Internal code never captures these attributes: it uses
  `quartz.runtime.state.current()`.
- `compat/` is not a package. Its children (`bpy`, `mathutils`, …) become top-level packages when
  `quartz.compat.activate()` puts `compat/` on `sys.path`. The name `quartz.compat` (the activator) does not
  collide with that.
- `quartz/math/` imports the stdlib `math` normally (absolute import).

---

## 3. Layers and dependencies

```
Layer 0    quartz._kernels                       (numpy + stdlib)
              ▲             ▲              ▲
Layer 1    quartz.math   quartz.rna+props   quartz.geometry      ← no dependency among them
              ▲             ▲              ▲
Layer 2    quartz.app → types(id, blenddata, mesh, object, ...) → depsgraph → ui → utils(registration)
           → runtime(state, context, opexec) → ops → operators → undo/io → msgbus/path → extras → bmesh
              ▲
Layer 3    quartz.compat  ·  quartz.addons  ·  quartz.cli   ·   compat/* (re-export only)
```

- **Layer 1 does not know about itself.** Two seams make this possible:
  - `quartz.rna.array.set_array_wrapper(subtype, factory)`: in layer 1, a `FloatVectorProperty`
    returns a generic `PropArray`. Layer 2, on initialization, registers `quartz.math.Vector` for
    the subtypes `XYZ`, `TRANSLATION`, `DIRECTION`, `VELOCITY`, `ACCELERATION`, `XYZ_LENGTH`,
    `EULER` → `Euler`, `QUATERNION` → `Quaternion`, `COLOR`/`COLOR_GAMMA` → `Color`
    (size 3 only), `MATRIX` → `Matrix`.
  - `quartz.rna.hooks`: `get_context()`, `on_property_changed(inst, prop)` (dirty channels +
    msgbus) and `on_struct_created(inst)` have null implementations in layer 1 and are filled in by
    layer 2.
- **Layer 2** has a fixed internal order (the arrow above). A module only imports the earlier ones. The permitted
  late imports (inside a function) are few and are listed in the architecture test.
- **Layer 3** depends on everything. `compat/*` may only import `quartz.*` and the profile, and each file
  has a size budget (≤ ~150 lines, except `bpy/types.py`), which enforces the "thin adapter"
  rule.
- The test `tests/arch/test_layering.py` analyzes the imports with `ast` and fails if a rule is
  broken.

---

## 4. RNA core and property system

### 4.1 Pieces

| Piece | Role | bpy equivalent |
|---|---|---|
| `RNAMeta` (metaclass) | `is_registered`; intercepts `Type.x = <_PropertyDeferred>` and `del Type.x` | `_RNAMeta` |
| `Struct` | base of everything; slots `_qz_store`, `_qz_idprops`, `_qz_owner`; `bpy_struct` methods | `bpy.types.bpy_struct` |
| `StructRNA` | description of a type (`identifier`, `base`, `properties`, `functions`) | `cls.bl_rna` |
| `PropertyRNA` (+7 subclasses) | **Python descriptor** + metadata (`bpy.types.Property`) | RNA property |
| `_PropertyDeferred` | what `IntProperty(...)` returns: `.function`, `.keywords` | same [O] |
| `PropCollection` / `GroupCollection` | RNA collections; the second has `add/remove/clear/move` | `bpy_prop_collection` |
| `PropArray` | non-math array (Bool/Int vector) | `bpy_prop_array` |
| `IDPropertyGroup` / `IDPropertyArray` / `IDPropertyUIManager` | dictionary properties (`ob["x"]`) | `idprop.types` |
| `TypeRegistry` | RNA name → class; naming rules (`MOD_OT_name`) | dynamic `bpy.types` |
| `datapath` | parse/resolve of `modifiers["Bend"].angle` | `path_resolve`, `path_from_id` |

### 4.2 Sketch (original)

```python
# quartz/rna/struct.py (sketch)
class Struct(metaclass=RNAMeta):
    __slots__ = ("_qz_store", "_qz_idprops", "_qz_owner", "__weakref__")

    def __new__(cls, *args, **kwargs):
        self = object.__new__(cls)
        object.__setattr__(self, "_qz_store", {})      # values of the RNA properties ("system properties")
        object.__setattr__(self, "_qz_idprops", None)  # IDPropertyGroup created on demand
        object.__setattr__(self, "_qz_owner", None)    # (parent struct, identifier, index|key) for path_from_id
        hooks.on_struct_created(self)
        return self
```

- State is born in `__new__`, so a user-defined `__init__` on an `Operator` works
  even without `super().__init__()`.
- Built-in types declare `__slots__ = ()`. With no `__dict__`, assigning an unknown attribute to an
  `Object` raises `AttributeError` for free [I, to be confirmed]. User-registered classes
  (Operator, Panel, PropertyGroup) do not declare slots, get a `__dict__` and accept instance
  attributes (`self._timer` in modal operators).
- All built-in types have the same slot layout. That way `obj.__class__ = OtherClass` works.
  This is used for the **tombstone** of removed IDs and for swapping `Light` ↔ `PointLight`/`SunLight`/…
  when `light.type` changes.

### 4.3 Declaration and registration

- **Built-ins** (Object, Mesh, …) declare properties with the same factories from `quartz.props`,
  plus internal native kwargs (`storage=`, `dirty=`). The `StructRNA` is built when the
  class is created, because the class attribute `_qz_builtin = True` makes the metaclass register them at import.
- **User classes** keep raw annotations until `register_class`. Then:

```python
# quartz/rna/annotations.py (sketch)
def collect_deferred(cls) -> dict[str, _PropertyDeferred]:
    found: dict[str, _PropertyDeferred] = {}
    for klass in reversed(cls.__mro__):
        if klass is object or "bl_rna" in klass.__dict__:   # built-in bases already have their own StructRNA
            continue
        for name, value in own_annotations(klass).items():  # annotationlib.get_annotations(klass, format=VALUE)
            if isinstance(value, _PropertyDeferred):
                found[name] = value                          # subclass overrides mixin/base
    return found
```

  `own_annotations` uses `annotationlib` (Python 3.14, lazy evaluation of annotations) and falls back to
  `klass.__dict__.get("__annotations__", {})` in earlier versions. This covers mixins
  (`ImportHelper`, `AddObjectHelper`) that do not inherit from `Struct` [O].
- The old-style assignment `x = IntProperty()` in the class body is **ignored** (it stays as a plain attribute),
  as in Blender [O]. In `--warn-legacy` mode, the loader emits a warning.
- `PointerProperty(type=X)` / `CollectionProperty(type=X)` require `X` to be a `PropertyGroup`
  **already registered** (or an `ID` for Pointer). Otherwise: `RegistrationError` (`ValueError`). Registration
  order is the same as in Blender [O].
- Dynamic extension: `quartz.types.Scene.mine = PointerProperty(type=G)` goes through
  `RNAMeta.__setattr__`, which creates the `PropertyRNA`, appends it to `Scene.bl_rna.properties` and installs
  the descriptor. `del` removes it [O].
- `unregister_class` removes descriptors and `bl_rna`, but **does not erase** the values in `_qz_store` of
  the instances. Registering again "recovers" the values, as with Blender's separate storage.

### 4.4 Value semantics (contract [O] from `bpy_contract.md` §4.4)

| Rule | Implementation in `PropertyRNA.__set__` |
|---|---|
| Int/Float outside `min/max` → silent clamp | `coerce()` |
| Float stored as float32 | `float(np.float32(v))`; vectors in `ndarray[float32]` |
| `StringProperty(maxlen=n)` truncates | `coerce()` |
| Wrong type → `TypeError`; invalid enum → `TypeError` listing the valid ones | `PropertyTypeError` |
| `ENUM_FLAG` → `set[str]` | `EnumPropertyRNA` |
| `update(self, context)` on **every** assignment, even with an equal or clamped value | `notify()` after writing |
| `get` + `set` → nothing is stored automatically; only `get` → read-only | `CallbackStorage`; `ReadOnlyError` |
| `get_transform`/`set_transform` (5.x) | applied around the storage |
| `FloatVectorProperty` returns *wrapped* `Vector`/`Matrix` (writes are reflected in the owner) | wrapper from §3 over numpy view + write callback |
| `is_property_set` / `property_unset` | key present in `_qz_store` / removes key |
| RNA name shadows a `bpy_struct` method (`items` as a collection) [O] | instance descriptor wins over the method |
| `PropertyGroup` has an implicit `name` | injected by the base |
| Pointer to `PropertyGroup` is never `None` and is read-only | created on demand |
| Pointer to `ID` counts a user [I] | `IDPointerStorage` does `users ±1` |

### 4.5 Two storages (Blender 5.x)

- `_qz_store`: values of RNA properties (built-in and `bpy.props`). It does not appear in `id.keys()`
  [O]. It is accessible through `bl_system_properties_get()`.
- `_qz_idprops`: `IDPropertyGroup` of the dictionary-style properties (`ob["x"] = 3.5`, lists →
  `IDPropertyArray`, dicts → nested group). It does not become an attribute [O].
- Observed exception: on a **`PropertyGroup` instance**, `keys()` lists the written values [O].
  For that reason `PropertyGroup.keys()` merges the two views, and on `ID` they stay separate.

### 4.6 Pluggable storage (`quartz/rna/storage.py`)

```python
class Storage(Protocol):
    def get(self, inst: Struct, prop: PropertyRNA) -> Any: ...
    def set(self, inst: Struct, prop: PropertyRNA, value: Any) -> None: ...
    def is_set(self, inst: Struct, prop: PropertyRNA) -> bool: ...

class StoreSlot(Storage): ...        # default: inst._qz_store[prop.identifier]
class CallbackStorage(Storage): ...  # user's get=/set=
class ComputedStorage(Storage): ...  # matrix_world, dimensions, users, type (built-in)
class ElementColumn(Storage): ...    # MeshVertex.co → mesh.attributes["position"][index]
class IDPointerStorage(Storage): ... # pointer to ID with user count
```

### 4.7 "Description" metadata (C4D idea, native only)

`quartz.props.*Property` accepts, **only on the native face**, `group: str | None`,
`ui_parent: str | None` (visual dependency, C4D's "PARENTID"), `enabled_if: Callable[[Struct],
bool] | None` (the "GetDEnabling") and `dirty: set[str]` (internal). They appear in `PropertyRNA` and
a future UI generator uses them. `compat/bpy/props.py` validates the kwargs against the list of the
5.2 profile and raises `TypeError` like Blender, so an add-on never sees these names. The
`describe(cls, desc)` hook (dynamic description) is **deferred** (§14).

---

## 5. Data model

### 5.1 ID and `BlendData`

- `ID(Struct)` with `name`, `name_full`, `id_type`, `session_uid` (monotonic session counter),
  `users`, `use_fake_user`, `use_extra_user`, `is_evaluated`, `original`, `library` (`None`), `tag`,
  `is_embedded_data`, `is_missing`, `is_runtime_data`, `is_editable`, `asset_data` (`None`, deferred).
- **Names** (`quartz/_kernels/naming.py`): unique per type, `.NNN` suffix starting at `.001`;
  255-byte UTF-8 cap, truncating at a character boundary; empty → the type's default name
  ("Mesh"); renaming to an existing name gives the suffix **to the one that was renamed** [O].
  `rename(name, *, mode='NEVER'|'ALWAYS'|'SAME_ROOT') -> str` returns the result as in 5.2
  (`UNCHANGED`, `RENAMED_NO_COLLISION`, `RENAMED_COLLISION_ADJUSTED`, …).
- **Order**: each `IDCollection` keeps the list sorted by name (insertion with `bisect`) [I].
- **Users**: explicit count. `IDPointerStorage` (Object.data, mesh materials, `bpy.props` pointers
  to ID [I]), `Collection.objects.link` and the fake user each add 1. A new object has
  0 users; linked to a collection, 1 [O].
- **Removal** (`IDCollection.remove(id, *, do_unlink=True, do_id_user=True, do_ui_user=True)`):
  unlinks all users (`user_remap(None)`). Objects whose `data` disappears **are deleted** when the
  removed ID is object data [O]. Afterwards the instance changes class to `_Removed<Type>`, whose
  `__getattribute__` raises `RemovedStructError` (`ReferenceError`), including on a second
  `remove` [O]. It has zero cost on the hot path.
- `copy()`: `.NNN` name, 0 users. `Object.copy()` shares `data` (users+1); `Mesh.copy()`
  copies the arrays.
- `BlendData`: real collections (`objects, meshes, materials, cameras, lights, collections, scenes,
  worlds, images, texts, window_managers, screens, workspaces`) and **ghost collections** for the
  other ~27 in the profile (`actions, armatures, curves, node_groups, …`): empty, iterable, and `new()`
  raises `NotImplementedInQuartz`. Plus `filepath` (`""`), `is_dirty`, `is_saved`, `version`,
  `batch_remove`, `orphans_purge`, `user_map`.

### 5.2 Hierarchy and organization (Blender model, not C4D)

- `Collection` (ID) with `objects` (`link/unlink`; double `link` → `RuntimeError` [O]), `children`
  (`link/unlink` with cycle detection → `RuntimeError`), `all_objects`, `children_recursive`,
  `hide_select/hide_viewport/hide_render`, `color_tag`, `instance_offset`.
- `Scene.collection` is the **embedded** master collection ("Scene Collection", `is_embedded_data=True`,
  outside `bpy.data.collections`) [O from the double `link` message].
- `ViewLayer` with a `LayerCollection` tree mirroring the scene's collections (`exclude`,
  `hide_viewport`, `is_visible`), `objects` (with `active`), `active_layer_collection` and an
  internal map `Object → _Base(select, hide)`. It is synchronized lazily by the scene's
  `HIERARCHY` dirty channel.
- `Object.parent` is the transform hierarchy (orthogonal to collections). `children` and
  `children_recursive` are computed.
- An object can be in several collections (`users_collection`). There are no C4D "layers".

### 5.3 Mesh: numpy SoA

Internal layout, the same as what Blender 5.2 exposes as attributes [O]:

| Attribute | Domain | Type | dtype/shape |
|---|---|---|---|
| `position` | POINT | FLOAT_VECTOR | float32 (V,3) |
| `.edge_verts` | EDGE | INT32_2D | int32 (E,2) |
| `.corner_vert` / `.corner_edge` | CORNER | INT | int32 (L,) |
| *(face offsets, not an attribute)* | — | — | int32 (F+1,) |
| `sharp_face` | FACE | BOOLEAN | bool (F,) — `use_smooth = not sharp_face` |
| `material_index` | FACE | INT | int32 (F,) — created on demand |
| `.select_vert/.select_edge/.select_poly` | P/E/F | BOOLEAN | bool |
| `UVMap` (UV) | CORNER | FLOAT2 | float32 (L,2) |
| colors | POINT/CORNER | FLOAT_COLOR / BYTE_COLOR | float32 (N,4) / uint8 (N,4) |

Also `FLOAT`, `INT`, `INT8`, `BOOLEAN`, `QUATERNION` (N,4) and `FLOAT4X4` (N,4,4). `STRING` is
deferred. Prefix `.` = internal and hidden in `attributes` (filtered as in Blender).

- `quartz.geometry.MeshArrays` is the pure package (layer 1). `quartz.types.Mesh` owns an
  `AttributeStorage` (dict name → `AttributeArray`) and the offsets. Resizing a domain
  resizes all of its arrays.
- `vertices/edges/polygons/loops` are `PropCollection`s whose items are *flyweights*
  (`MeshVertex(mesh, i)`). `foreach_get/foreach_set` copy directly between the array and the buffer
  (fast numpy, a list is also accepted [O]).
- `from_pydata(vertices, edges, faces, shade_flat=True)` uses `quartz.geometry.from_pydata` and
  recalculates edges from the faces (a quad yields 4/4/4/1 [O]). `update(calc_edges=...)`,
  `validate(verbose=False, clean_customdata=True) -> bool`.
- Edit mode: `Mesh.is_editmode` and an *edit hook* per data type (`runtime.editmode`). In the milestone,
  entering EDIT only marks the state. `quartz.bmesh.from_edit_mesh` (Tier 3) creates an edit BMesh
  that is written back when leaving the mode.

### 5.4 Object and transforms

- `Object(ID)`: `data`, `type` (derived from the type of `data`, read-only; `None` → `EMPTY` [O]),
  `mode`, `parent`, `parent_type='OBJECT'`, `location`, `rotation_euler`, `rotation_quaternion`,
  `rotation_axis_angle`, `rotation_mode` (`XYZ` default; Euler orders, `QUATERNION`, `AXIS_ANGLE`),
  `scale`, `delta_*`, `lock_*`, `matrix_basis` (computed, rw), `matrix_parent_inverse`,
  `matrix_local` (rw), `matrix_world` (rw, **stored/evaluated**), `dimensions`, `bound_box`,
  `material_slots`, `active_material(_index)`, `modifiers`, `hide_viewport/hide_render/hide_select`,
  `display_type`, `show_*`, `color`, `empty_display_type/size`, `pass_index`,
  `users_collection`, `users_scene`. `constraints` and `vertex_groups` exist as ghosts in the milestone.
- Formula: `matrix_basis = T(location + delta_location) · R(rotation according to rotation_mode, composed
  with delta) · S(scale ⊙ delta_scale)`. `matrix_local = matrix_parent_inverse · matrix_basis`.
  `matrix_world = parent.matrix_world · matrix_local`.
- Assigning `ob.parent = p` does **not** recalculate `matrix_parent_inverse` (the object "jumps"), as in
  Blender. The `object.parent_set` operator (deferred) does the compensation.
- Assigning `matrix_world` decomposes into `location/rotation/scale` taking the parent into account and stores
  the `matrix_world` itself.
- **`matrix_world` only changes on evaluation** (§6) [I]. Assigning `ob.location` and reading
  `ob.matrix_world` without `view_layer.update()` returns the old matrix, which is the classic
  Blender gotcha. It is preserved on purpose for conformance and so that code written for
  Blender behaves the same.
- Selection: `select_get(view_layer=None)`, `select_set(state, view_layer=None)`, `hide_get/set`,
  `visible_get`, stored in the view layer's `_Base`.

### 5.5 Other data-blocks of the milestone

| Type | Milestone properties (dump defaults when available) | Functions |
|---|---|---|
| `Material` | `diffuse_color`(4), `metallic`, `roughness`, `specular_intensity`, `specular_color`, `use_backface_culling`, `blend_method`, `surface_render_method`, `alpha_threshold`, `pass_index`, `is_grease_pencil`, `use_nodes`, `node_tree=None` | — |
| `Camera` | `type` (`PERSP` default; `ORTHO`, `PANO`, `CUSTOM`), `lens=50`, `lens_unit='MILLIMETERS'`, `angle/angle_x/angle_y` (derived), `sensor_width=36`, `sensor_height=24`, `sensor_fit='AUTO'`, `clip_start=0.1`(float32), `clip_end=1000`, `ortho_scale=6`, `shift_x/y`, `display_size`, `dof` (`use_dof`, `focus_object`, `focus_distance`, `aperture_fstop`), `show_*` | `view_frame(*, scene=None)` |
| `Light` → `PointLight`/`SunLight`/`SpotLight`/`AreaLight` | base: `type`, `color`, `use_shadow`, `exposure`, `normalize`, `specular_factor`, `diffuse_factor`, `use_temperature`, `temperature`; subclasses: `energy`, `shadow_soft_size`; `SunLight.angle`; `SpotLight.spot_size/spot_blend/show_cone`; `AreaLight.shape/size/size_y/spread` | `lights.new(name, type)` chooses the subclass; changing `type` swaps the class |
| `World` | `color`, `use_nodes`, `node_tree=None`, `mist_settings`/`light_settings` ghosts | — |
| `Image` | `size`, `generated_*`, `filepath`, `pixels` (float32 (H·W·4)), `is_dirty` | `images.new(...)`; `load()` deferred (no dependency-free decoder) |
| `Text` | `lines`, `current_line_index`, `filepath`, `is_dirty`, `is_in_memory` | `write`, `clear`, `as_string`, `from_string` |
| `Scene` | `collection`, `objects`, `view_layers`, `camera`, `world`, `frame_current=1`, `frame_start=1`, `frame_end=250`, `frame_step=1`, `frame_float`, `frame_subframe`, `render` (resolution, `fps`, `fps_base`, `engine='BLENDER_EEVEE'`, `filepath`), `unit_settings` (`system='METRIC'`, `scale_length`, `length_unit`), `tool_settings` (subset + ghost), `cursor` (`location`, `rotation_*`, `matrix`), `gravity`, `use_gravity` | `frame_set(frame, subframe=0.0)`, `statistics(view_layer)`, `ray_cast(depsgraph, origin, direction, distance=...)` |
| `WindowManager` | `windows`, `keyconfigs` (data only), `operators`, `clipboard` (in memory, **never** the system clipboard) | `modal_handler_add`, `fileselect_add`, `event_timer_add/remove`, `progress_begin/update/end`, `invoke_props_dialog`, `invoke_props_popup`, `invoke_popup`, `invoke_confirm`, `invoke_search_popup`, `popup_menu`, `popover` |
| `Preferences` | `addons`, `filepaths` (`temporary_directory`, `asset_libraries` empty), `view` (`ui_scale=1.0`, `show_developer_ui`, `language`), `edit` (`use_global_undo=True`, `undo_steps=32`), `system`, `inputs`, `extensions` (repos `user_default`, `system`; `blender_org` present but with network disabled), `use_preferences_save=False` | — |

Factory scene (`quartz.runtime.factory`): "Scene", collection "Collection", Camera/Cube/Light objects
at the dump positions (`factory_scene`), materials "Material" and "Dots Stroke" (the latter with
`is_grease_pencil=True`), World "World", mesh "Cube" 8/12/6/24 with `UVMap`, Cube active and
selected, frames 1–250. Camera/light rotations, lens and energy come from the probe
`p_factory_scene` (§11.3) **before** being fixed in the code, because they are observed values and not
code. `factory_reset(template='empty')` creates only Scene + view layer, for tests.

### 5.6 Modifiers (skeleton)

`Object.modifiers` (`new(name, type)`, `remove(m)`, `clear()`, `move(from, to)`, `[name]`) over
`Modifier(Struct)` (`name`, `type`, `show_viewport`, `show_render`, `show_in_editmode`,
`show_expanded`, `is_active`, `persistent_uid`). There is a type registry with
`evaluate(arrays: MeshArrays, ctx: EvalContext) -> MeshArrays`. The milestone delivers only `TRIANGULATE`
(proof of the pipeline, using `quartz.geometry.triangulate`). The other types in the profile exist
as valid names in `new()` and raise `NotImplementedInQuartz`. The C4D child deformers will come
as sugar over this stack (§14).

---

## 6. Evaluation: dirty channels + Depsgraph facade

```python
class DirtyChannel(enum.IntFlag):
    TRANSFORM = 1; GEOMETRY = 2; SHADING = 4; SELECT = 8; HIERARCHY = 16; PARAMETERS = 32; VISIBILITY = 64
```

- Each ID has monotonic counters per channel (C4D idea). `PropertyRNA(dirty={...})` says what
  a write increments (`location` → `TRANSFORM`; `position` → `GEOMETRY`; `Collection.objects.link`
  → the scene's `HIERARCHY`…). `hooks.on_property_changed` does the increment.
- `Depsgraph` (one per scene+view layer pair) stores the last counter seen for each ID. `update()`
  evaluates in named stages: `HIERARCHY` (synchronizes bases) → `TRANSFORM` (recalculates
  `matrix_world` in parent order for dirty IDs and descendants) → `GEOMETRY` (modifier stack →
  cached evaluated mesh) → `HANDLERS` (`depsgraph_update_post(scene, depsgraph)`
  if there was a change [O]). The `ANIMATION`/`DRIVERS`/`GENERATORS` stages are reserved.
- `updates` is derived from the deltas: `DepsgraphUpdate(id, is_updated_transform, is_updated_geometry,
  is_updated_shading)`.
- `ob.evaluated_get(dg)` returns a lightweight evaluated copy (`is_evaluated=True`, `original=ob`) with the
  cached mesh. Without modifiers, the evaluated mesh is the original (no copy).
  `ob.to_mesh()`/`to_mesh_clear()` create/discard a temporary mesh outside `bpy.data`.
- What triggers evaluation: end of a `FINISHED` operator, `view_layer.update()`,
  `scene.frame_set()` (`frame_change_pre` already with the new frame, then the evaluation, then
  `frame_change_post` [O]) and `context.evaluated_depsgraph_get()` [I].

---

## 7. Registration, operators, context, undo, handlers and UI

### 7.1 `register_class` / `unregister_class`

Flow of `quartz.utils.register_class(cls)` (all messages are our own, the exception types are
the observed ones [O]):

1. Not a subclass of `Struct` → `RegistrationRuntimeError`.
2. `"bl_rna" in cls.__dict__` → `RegistrationError` ("already registered").
3. Finds the registrable base in the MRO (`Operator`, `Macro`, `Panel`, `Menu`, `Header`, `UIList`,
   `PropertyGroup`, `AddonPreferences`, `FileHandler`, `KeyingSetInfo`, `RenderEngine`, `Gizmo`,
   `GizmoGroup`, `WorkSpaceTool`, `AssetShelf`, `Node`, `NodeSocket`, `NodeTree`, …). The unimplemented ones
   are **inert bases** (`quartz/types/inert.py`): they validate and register, with no
   runtime behavior.
4. Validates the required attributes per base (table in §2.2 of the research):
   `MissingClassAttributeError` (`AttributeError`). Operator: `bl_idname` with exactly 1 dot,
   only `[a-z0-9_]`, identifier ≤ 60 → `RegistrationRuntimeError`. Without `bl_idname`, it uses the class
   name and fails by the same rule [O]. `bl_space_type`/`bl_region_type` outside the enum →
   `ClassValidationError` (`TypeError`). Nonexistent `bl_parent_id` → `RegistrationRuntimeError`.
   Panel/Menu name without `_PT_`/`_MT_` → warning only [O].
5. Collects the annotations (§4.3), creates the `PropertyRNA`s, validates `type=` and the enum defaults. Any
   failure causes a **full rollback** and raises `RegistrationError`.
6. If a class with the same `bl_idname` (same base) already exists, it is silently unregistered
   (INFO log) [O].
7. Installs descriptors and `bl_rna`, publishes in the `TypeRegistry` under the **RNA name**
   (`quartz_probe.hello` → `QUARTZ_PROBE_OT_hello`; Panel/Menu/… → `bl_idname` or the class name)
   [O].
8. Records the owner (`addons.owners.current()`) and calls the classmethod `cls.register()` if it exists [I].

`unregister_class`: without its own `bl_rna` → `RegistrationRuntimeError` [O]. Calls
`cls.unregister()` if it exists, removes from the registry and removes descriptors/`bl_rna`.
`register_classes_factory` and `register_submodule_factory` follow the contract [L] (reverse order on
unregister; the second removes submodules from `sys.modules`).

### 7.2 Operator engine (`quartz/runtime/opexec.py`)

```python
def call_operator(idname_py: str, args: tuple, props: dict[str, Any]) -> set[str]:
    exec_ctx, undo = _parse_positional(args)     # 0–2 positional; dict → ValueError; unknown context → TypeError
    cls = registry.operator(idname_py)           # missing → OperatorNotFoundError (AttributeError)
    context = state.current().context
    with poll_messages() as msgs:
        if not cls.poll(context):                # 1 call (deviation §1.1)
            raise PollFailedError(f"Operator quartz.ops.{idname_py}.poll() failed: {msgs.last or 'context is incorrect'}")
    op = cls()                                   # new instance per call: values do NOT persist
    op.properties._qz_apply_kwargs(props)        # PropertyTypeError on kwarg/type/enum; silent clamp
    try:
        if exec_ctx.startswith("INVOKE") and _can_invoke(cls):   # headless: _can_invoke is False → execute [O]
            result = op.invoke(context, _synthetic_event())
        else:
            result = op.execute(context) if _has_execute(cls) else {"CANCELLED"}   # [I]
    except Exception as exc:
        raise OperatorFailedError(f"Error: Python: {format_exc(exc)}") from exc
    status = _validate_status(result)            # set ⊆ {RUNNING_MODAL, CANCELLED, FINISHED, PASS_THROUGH, INTERFACE}
    _flush_reports(op, status)                   # ERROR + CANCELLED → OperatorFailedError; INFO/WARNING → stdout + wm.reports
    if "FINISHED" in status:
        _after_finished(op, cls, undo)           # undo push if 'UNDO' ∈ bl_options; wm.operators; depsgraph evaluation
    return status
```

- Inside the operator, `self.<prop>` is the descriptor bound to `self.properties` [O]. Also available are
  `as_keywords(*, ignore=())`, `properties.is_property_set(name)` (true only if the caller
  passed it [O]), `report(type, message)`, `poll_message_set(message, *args)` and `layout` (recorder,
  when `draw` is called).
- Modal: `wm.modal_handler_add(op)` stores the instance, but nothing runs on its own. The native test
  extra is `quartz.testing.drive_modal(idname, events)`, which calls `invoke` and then `modal` with
  synthetic events (deferred until after the milestone if time is tight).
- The built-in operators of the milestone live in `quartz/operators/` and are registered at boot as ordinary
  classes (dogfooding the registration). List: `object.mode_set`, `object.select_all`, `object.delete`,
  `object.duplicate`, `object.transform_apply`, `object.shade_smooth`, `object.shade_flat`,
  `object.add`, `object.empty_add`, `object.camera_add`, `object.light_add`,
  `object.parent_clear`; `mesh.primitive_{plane,cube,grid,circle,uv_sphere,ico_sphere,cylinder,cone,torus}_add`;
  `transform.translate`, `transform.rotate`, `transform.resize` (by value, no interaction);
  `ed.undo`, `ed.redo`, `ed.undo_push`; `wm.read_factory_settings`. The properties of each one
  (names, types, defaults, limits, enums) are checked against the dump (§11.4).

### 7.3 Context (`quartz/runtime/context.py`)

- **One** `Context` instance. Members are read-only properties (`context.scene = …` →
  `ReadOnlyError` [O]). Resolution: (1) the `ContextVar` override stack, from top to bottom;
  (2) base state: `window_manager.windows[0]` → `scene`, `view_layer`, `workspace`, `screen`;
  (3) derived: `object`/`active_object` = `view_layer.objects.active`, `selected_objects` and related
  from the bases, `mode` from the active object (`OBJECT`, `EDIT_MESH`, …), `edit_object`,
  `collection` = `active_layer_collection.collection`; (4) the other members of profile 5.2 → `None`
  (`area`, `region`, `space_data`, … as in headless [O]); (5) any other name →
  `AttributeError`.
- `temp_override(*, window=None, area=None, region=None, **keywords)` pushes onto the stack and restores on exit
  [O]. Unknown keys are accepted and never become attributes [O]. `window=` replaces the base.
- `copy() -> dict`, `path_resolve(path, coerce=True)` (the first segment is a member, the rest goes to
  the value's `path_resolve` [O/L]), `evaluated_depsgraph_get()`.
- **RestrictBlend** (`quartz/runtime/restrict.py`): during add-on import + `register()`,
  `quartz.context`/`quartz.data` (and `bpy.context`/`bpy.data` if compat is active) are swapped
  for `RestrictedContext` (only `window_manager` and `preferences`) and `RestrictedData` (empty), which
  raise `RestrictedAccessError` [L]. An add-on that does `from bpy import context` at import
  captures the restricted object forever, just like Blender.

### 7.4 Undo (`quartz/undo.py`, `quartz/io/snapshot.py`)

- Stack of global snapshots ("memfile" style): `snapshot.take(blend_data)` serializes
  `_qz_store`/idprops of all IDs (numpy arrays copied; pointers as `session_uid`).
  `restore()` reapplies **in place** by `session_uid`: IDs that disappear become tombstones, those that return
  are recreated, existing ones have their state restored. This way Python references remain valid,
  a friendly deviation [I].
- In background it starts **off**: `ed.undo.poll()` is false with a message; `ed.undo_push(message)`
  turns it on and pushes [O]. `bl_options={'UNDO'}` pushes after `FINISHED`. `UNDO_GROUPED` +
  `bl_undo_group` merges consecutive steps of the same group. Limit in
  `preferences.edit.undo_steps`. Handlers `undo_pre/post`, `redo_pre/post`.
- Cost is O(scene) per step, acceptable in headless. Incremental undo by dirty channel is left for
  later.

### 7.5 Handlers, timers, msgbus, translations

- `quartz.app.handlers`: Blender's 39 lists [O] + the Quartz phases (`startup_post`,
  `shutdown_pre`, `shutdown_post`, the idea of phased shutdown from C4D). `persistent(fn)` marks
  `fn._bpy_persistent = True` (name kept for fidelity [O]). `factory_reset()` removes the
  non-persistent handlers and fires `load_pre`, `load_post` and `load_factory_startup_post` [I].
  `handlers.call(name, *args)` catches the exception of each callback, prints it and continues.
- `quartz.app.timers`: `register(fn, *, first_interval=0, persistent=False)`, `unregister`,
  `is_registered`. Never fires on its own [O]. `pump(*, now=None, max_calls=None) -> int` is the native
  extra for tests and for the CLI.
- `quartz.msgbus`: `subscribe_rna(*, key, owner, args, notify, options=set())`,
  `publish_rna(*, key)`, `clear_by_owner(owner)`. Notifications are queued, never synchronous [O].
  `flush() -> int` (native) delivers them.
- `quartz.app.translations`: `pgettext*` are identity; `contexts` comes from the profile;
  `register(module_name, translations_dict)`/`unregister` store without effect.

### 7.6 Headless UI (`quartz/ui`)

- `Panel`, `Menu`, `Header`, `UIList` with `append/prepend/remove/is_extended` (`_GenericUI` mixin).
  On the first extension, `draw` becomes a chain that calls each function, catches and prints the exception
  of each one and continues [L]. `remove` of an absent function is silent [O].
- `UILayout` **recorder**: each call (`row`, `column`, `box`, `split`, `prop`, `label`,
  `operator`, `menu`, `separator`, `template_list`, `panel`, …) becomes a `LayoutNode`. `operator()`
  returns a usable `OperatorProperties` (`op = layout.operator("x.y"); op.value = 1`).
  `prop(data, "name")` with a nonexistent property records a warning and does not raise [I]. The methods
  are generated from the profile's names (`extras.UILayout_functions` of the dump); the unmodeled ones
  accept `*args, **kwargs` and record.
- `quartz.ui.draw_panel(cls, context=None) -> LayoutNode` and `draw_menu(...)` are used by the
  tests and by level L4 of the sweep.
- `quartz.ui.placeholder_type(name, kind)` creates empty menu/panel/header/list classes. The Blender
  **names** come from the profile (§8.4). The future Quartz GUI MUST **reuse** these
  identifiers (`VIEW3D_MT_mesh_add`, `TOPBAR_MT_file_import`…), so that add-on menu extensions
  work without adaptation.
- `quartz.types.Space` (and the `SpaceView3D`… placeholders) accepts `draw_handler_add/remove` and
  stores the callbacks without ever calling them.

---

## 8. Mapping `compat/` → `quartz`

### 8.1 Activation

```python
# quartz/compat/__init__.py (signatures)
COMPAT_DIR: Path                        # <root>/compat
def activate(*, profile: str = "blender-5.2", strict_kwargs: bool = True,
             ghosts: Literal["error", "log", "silent"] = "log",
             restrict_register: bool = True) -> None
def deactivate() -> None                # removes COMPAT_DIR from sys.path and removes bpy*, mathutils*, bmesh*, bpy_extras*,
                                        # addon_utils, idprop*, gpu*, gpu_extras*, blf, aud, bl_math, bl_ui*, rna_prop_ui, bl_ext* from sys.modules
def is_active() -> bool
def current_profile() -> CompatProfile
def ghost_log() -> list[GhostAccess]    # what was touched and does not exist in Quartz
def clear_ghost_log() -> None
```

`activate()` is idempotent: it inserts `COMPAT_DIR` into `sys.path[0]`, imports `bpy` (which registers
`sys.modules["bpy.types"]`, `["bpy.app"]`, `["bpy.app.handlers"]`, `["bpy.app.translations"]`
[L]) and records the choices in `quartz.app.settings`.

### 8.2 Renaming table (the "almost a rename")

| Blender | Quartz | Difference in compat |
|---|---|---|
| `bpy.types.*` | `quartz.types.*` | + `bpy_struct`, `bpy_prop_collection`, `bpy_prop_array` (aliases of `quartz.rna.*`); + ghost names from the profile |
| `bpy.props.*` | `quartz.props.*` | kwargs filtered by the profile's list (`TypeError` as in Blender) |
| `bpy.utils.*` (+ `previews`, `units`) | `quartz.utils.*` | none |
| `bpy.ops` | `quartz.ops` | none (messages cite `bpy.ops` when compat is active) |
| `bpy.data` / `bpy.context` | `quartz.data` / `quartz.context` | same objects; swapped together by RestrictBlend |
| `bpy.app` (+ `handlers`, `timers`, `translations`, `icons`) | `quartz.app` | `version=(5,2,2)`, `version_file=(5,2,45)`, `version_string="5.2.2 LTS"`, `build_*` placeholders, lib structs with `supported=False` |
| `bpy.path` | `quartz.path` | none |
| `bpy.msgbus` | `quartz.msgbus` | none |
| `mathutils` (+ `geometry`, `kdtree`, `bvhtree`, `noise`, `interpolate`) | `quartz.math` (+ submodules) | none |
| `bl_math` | `quartz.math.scalar` | none |
| `bmesh` (+ `types`, `ops`, `utils`, `geometry`) | `quartz.bmesh` | none |
| `bpy_extras` (+ `io_utils`, `object_utils`, `view3d_utils`, `anim_utils`) | `quartz.extras` | `node_utils`, `image_utils` as typed stubs |
| `addon_utils` | `quartz.addons` | private names used by add-ons (`addons_fake_modules`) point to the equivalents |
| `idprop.types` | `quartz.rna.idprops` | none |
| `rna_prop_ui.rna_idprop_ui_create` | `quartz.rna.idprops.ui_create` | none |
| `bl_ui.utils.PresetPanel`/`PresetMenu`, `bpy.types.UI_UL_list` | `quartz.ui.PresetPanel`, `quartz.ui.UI_UL_list` | — |
| `gpu`, `gpu_extras`, `blf`, `aud` | — | **compat-only stubs**: import works; attributes return a callable that raises `NotImplementedInQuartz("no GPU in headless Quartz")`; `gpu.platform.backend_type_get()` returns `"NONE"` |
| `bl_ext.<repo>.<pkg>` | created at runtime by `quartz.addons.extensions` | — |

### 8.3 What lives only in compat (closed list)

1. The profile (`quartz/compat/profiles/blender_5_2.json`): target version, kwargs per property
   factory, handler names, the 75 context members, the 40 `bpy.data` collections, the
   ~4023 `bpy.types` names (with a mark of which are UI `_MT_/_PT_/_HT_/_UL_`), `UILayout` method
   names, class enum items (`bl_space_type`, `bl_region_type`, `bl_options`)
   and the property schema of the built-in operators that Quartz implements.
   **Only names, types and defaults** (interface facts), generated by
   `tools/build_compat_profile.py` from `data/blender_api_dump.json`.
2. The strict kwargs filter (`quartz/compat/strict.py`).
3. The ghost factory (`quartz/compat/ghosts.py`).
4. `bpy.app` with the target version.
5. The `gpu`/`gpu_extras`/`blf`/`aud` stubs.

Everything else is re-export.

### 8.4 Profile-driven ghost surface

- `bpy.types.__getattr__(name)`: (1) `TypeRegistry` (built-ins + registered); (2) if `name` is in the
  profile as UI, creates `quartz.ui.placeholder_type(name, kind)` on demand and publishes it in the
  registry (stable from then on); (3) if it is in the profile as an unimplemented struct/ID, creates an
  **inert ghost type** (subclass of `Struct`, no properties, accepts
  `Type.prop = Prop(...)`); (4) otherwise, `AttributeError`, as in Blender for a nonexistent name.
- Unimplemented `bpy.data` collections and context members follow the same idea (§5.1, §7.3).
- **Telemetry**: each ghost records `GhostAccess(symbol, first_caller_file, count)`. Policy:
  `ghosts='error'` raises `NotImplementedInQuartz` on use (not on `hasattr`), `'log'` (default)
  records and continues, `'silent'` does not record. `python -m quartz addon-sweep` aggregates this into
  `data/sweep_ghosts.json`, which becomes the backlog sorted by number of add-ons.

---

## 9. Add-on and extension loader (`quartz.addons`)

### 9.1 Discovery

- `paths()`: `settings.addon_paths` (configurable) + `<user_dir>/scripts/addons`. Blender's
  `addons_core` directory enters **only** with an explicit option (`--blender-scripts`), read-only.
- Scan by `module_names`: `*.py` (except `__init__.py`) and non-hidden folders with
  `__init__.py`; the `modules` folder is ignored [L].
- `read_bl_info(path)` reads **without importing**: from the first line that starts with `bl_info` to
  the first blank line, then `ast.parse` + `ast.literal_eval` [L]. `module_bl_info(mod,
  info_basis=None)` fills in the base fields (empty `name` → module name, removes `<email>` from
  `author`, expands `{BLENDER_MANUAL_URL}`, marks `_init`) [L/O]. `modules()` creates "fake modules"
  with `bl_info`, `__file__`, `__time__`, sorted by name (casefold) and then by module [L].

### 9.2 Extensions

- Repositories: `user_default` (`<user_dir>/extensions/user_default`), `system` and `blender_org`
  (off: `online_access=False`). More local repositories via `add_extension_repo`.
- `parse_manifest(path, *, strict=True) -> Manifest` with `tomllib` (stdlib) and the `bl_pkg` rules
  [L]: required fields; `type ∈ {add-on, theme}`; `id` a Python identifier without `__` and without `_`
  at the start/end; versions with 3 numbers in strict mode; `[build]` with `paths` **or**
  `paths_exclude_pattern`; `permissions` as a table. All problems come together in one
  `ManifestError`. `wheels` → "not supported" warning. `type = theme` → listed, not enableable.
- Module name: `bl_ext.<repo>.<pkg_id>`, with synthetic packages `bl_ext` and `bl_ext.<repo>`
  (`__path__ = [repo dir]`) [O]. A `bl_info` defined by the extension is erased and replaced by the
  synthetic one from the manifest (`name`, `version`, `blender ← blender_version_min`,
  `description ← tagline`, `author ← maintainer`, `category='Development'`) [L].
- Native Quartz extensions: same format with `quartz_manifest.toml`
  (`quartz_version_min` in place of `blender_version_min`) and namespace `qz_ext.<repo>.<pkg>`.
  `extension_path_user(package)` accepts both prefixes.

### 9.3 Lifecycle (`enable` / `disable` / `check`)

```python
def enable(module_name: str, *, default_set: bool = False, persistent: bool = False,
           refresh_handled: bool = False,
           handle_error: Callable[[BaseException], None] | None = None) -> ModuleType | None
```

1. Already enabled → `unregister()` and, if the mtime changed, `importlib.reload` [L].
2. `default_set=True` → creates the entry in `preferences.addons` **before** importing [L].
3. `with restrict_state(), owners.push(module_name), sandbox_io():` → import + `mod.register()`.
   `sandbox_io` ensures `sys.dont_write_bytecode = True` for paths outside the project root
   (no `__pycache__` in `Program Files`).
4. Failure → `handle_error(exc)` (default: prints), removes from `sys.modules`, undoes `default_set`,
   returns `None`. Missing module → short message "Add-on not loaded" [O].
5. Success → `mod.__addon_enabled__ = True`, `mod.__addon_persistent__ = persistent`, returns the
   module [O]. `AddonPreferences` with `bl_idname == module` is available at
   `context.preferences.addons[name].preferences` [O].

`disable(module_name, *, default_set=False, refresh_handled=False, handle_error=None)` clears the flags,
calls `unregister()` (the error is reported, not propagated) and leaves the module in `sys.modules` [O].
`check(name) -> (loaded_default, loaded_state)` [O]. There are also `disable_all()`,
`reset_all(*, reload_scripts=False)`, `check_extension(name)` and `extensions_refresh()`.

### 9.4 Owner tracking and leaks (`owners.py`, `report.py`)

During `enable`, `register_class`, `RNAMeta.__setattr__` (props on types), menu `append` and the
handler lists record the owner. `enable_with_report()` returns an `AddonReport` with what was
registered. After `disable`, it flags **leaks**: classes still registered, properties
still attached to `bpy.types.X`, module handlers still in the lists and menus still extended. It is a
Quartz feature, useful in the sweep and for add-on authors.

### 9.5 Sweep (`sweep.py`)

Each target runs in a **subprocess** `python -I -B -m quartz enable-addon --json ...` with timeout
(default 20 s), `QUARTZ_USER_DIR` pointing to `tmp/sweep_user/<target>` and compat active.
Levels:

| Level | Criterion |
|---|---|
| L0 | metadata read and valid (`bl_info` or manifest), without importing |
| L1 | import OK under RestrictBlend |
| L2 | `register()` OK |
| L3 | `unregister()` OK and **no leaks** |
| L4 | headless smoke: `poll` of each registered operator on the factory scene + `draw` of each registered Panel/Menu/UIList with the recorder `UILayout`, no exception |

Templates (`templates_py`) are **scripts**, not add-ons: they run with
`python -m quartz run-script <tpl>` as `__main__` (they register and often call their own
operator). Success = exit code 0.

---

## 10. CLI (`python -m quartz ...`)

```
python -m quartz info [--json]
python -m quartz scan-addon PATH [--json] [--profile blender-5.2]
python -m quartz enable-addon NAME|PATH [--addons-dir DIR]... [--blender-scripts DIR]
                              [--lenient] [--keep-enabled] [--smoke] [--json]
python -m quartz run-script FILE [--no-compat] [--empty] [--addon NAME]... [--ghosts error|log|silent] [-- ARGS...]
python -m quartz addon-sweep [--dir DIR]... [--blender-scripts DIR] [--templates] [--extensions DIR]...
                             [--timeout 20] [--json OUT] [--md OUT]
```

| Subcommand | Does | Output / code |
|---|---|---|
| `info` | Quartz version, Python, numpy, compat profile, number of types/ops/handlers, user directory, add-on paths | text or JSON; 0 |
| `scan-addon` | reads `bl_info`/manifest **without importing** and validates; runs `quartz.addons.static_scan` (the `tools/scan_bpy_usage.py` engine, migrated) and cross-checks the used symbols against the real compat surface (introspection of the shims) → "% covered, missing: …" | 0 ok; 1 invalid metadata |
| `enable-addon` | enables, prints the `AddonReport` (classes, ops, panels, extended menus, props on types), optionally runs the L4 smoke, disables and checks for leaks | 0 up to L3/L4; 1 failure; the JSON carries the level reached |
| `run-script` | emulates `blender --background --python FILE -- ARGS`: `sys.argv = [sys.executable, "--background", "--python", FILE, "--", *ARGS]` and `__name__ == "__main__"`; factory scene (or `--empty`); `timers.pump()` and `msgbus.flush()` at the end | script's code (unhandled exception → 1) |
| `addon-sweep` | §9.5; summary table + JSON/MD; aggregates ghost telemetry | 0 if it ran (even with add-on failures); 3 internal error |

Common codes: `2` usage error, `3` internal Quartz error. The default user directory is
`$QUARTZ_USER_DIR` or `<project root>/tmp/quartz_user`. Nothing is written outside it.

---

## 11. Testing strategy

### 11.1 Tree

```
tests/
├─ conftest.py                 # fixtures qz (factory_reset default), qz_empty, compat, isolated; markers: blender, sweep, slow
├─ test_scan_bpy_usage.py      # (exists; keeps passing after the engine migration)
├─ arch/   test_layering.py  test_headers.py  test_cleanroom.py  test_compat_thin.py
├─ unit/
│  ├─ math/      test_vector.py test_matrix.py test_quaternion.py test_euler.py test_color.py test_wrapping.py test_geometry.py test_kdtree.py
│  ├─ rna/       test_deferred.py test_annotations_mro.py test_value_semantics.py test_enum.py test_pointer_collection.py
│  │             test_idprops_split.py test_datapath.py test_dynamic_type_props.py test_registration_atomic.py
│  ├─ geometry/  test_from_pydata.py test_calc_edges.py test_normals.py test_triangulate.py test_primitives.py test_validate.py
│  ├─ types/     test_id_naming.py test_id_users.py test_id_remove.py test_mesh_api.py test_attributes.py test_object_transform.py
│  │             test_parenting.py test_collections.py test_view_layer.py test_light_type_swap.py test_factory_scene.py
│  ├─ runtime/   test_context.py test_temp_override.py test_restrict.py
│  ├─ ops/       test_register_rules.py test_call_contract.py test_lifecycle.py test_builtin_object.py test_builtin_mesh.py test_mode_set.py
│  ├─ test_depsgraph.py test_undo.py test_handlers.py test_timers.py test_msgbus.py test_ui_recorder.py test_path.py test_extras.py test_bmesh.py
│  ├─ compat/    test_activate_deactivate.py test_identity.py test_strict_kwargs.py test_ghosts.py test_sys_modules.py
│  ├─ addons/    test_bl_info.py test_manifest.py test_enable_disable.py test_extension_namespace.py test_owner_leaks.py
│  └─ cli/       test_info.py test_scan_addon.py test_enable_addon.py test_run_script.py test_addon_sweep.py
├─ conformance/
│  ├─ probes/    _probe_runtime.py  p_props_semantics.py p_registration.py p_operator_contract.py p_id_naming.py p_id_users_remove.py
│  │             p_mesh_from_pydata.py p_object_transforms.py p_collections_viewlayer.py p_context.py p_mode_set.py
│  │             p_primitives.py p_math.py p_handlers.py p_undo_background.py p_addon_lifecycle.py p_factory_scene.py p_rna_surface.py
│  ├─ golden/blender-5.2.2/*.json
│  ├─ deviations.toml
│  └─ test_conformance.py
├─ schema/       data/builtin_ops.json  test_builtin_ops_schema.py  test_rna_surface.py  test_usage_surface.py
├─ sweep/        test_sweep.py         # @pytest.mark.sweep (slow; needs the Blender scripts directory)
├─ perf/         test_perf_smoke.py    # @pytest.mark.slow; generous budgets
└─ fixtures/
   ├─ addons/     qz_min_addon.py  qz_pkg_addon/__init__.py  qz_bad_register.py  qz_touch_data_on_register.py  qz_leaky.py
   └─ extensions/ user_default/qz_ext_demo/{blender_manifest.toml, __init__.py}
```

### 11.2 Unit and architecture

- One test file per contract rule in `bpy_contract.md` (each [O] line becomes at least
  one assertion). Fixture `qz` = `quartz.testing.isolated()`: snapshot/restore of the registry, of
  `sys.modules` (prefixes `bpy`, `mathutils`, `bl_ext`, fixtures), of global state and of the handler
  lists.
- `arch/test_layering.py`: import rules from §3 (via `ast`). `arch/test_headers.py`: every `.py`
  starts with a one-line docstring followed by `# Quartz - author: D1on1n`.
  `arch/test_compat_thin.py`: line budget per shim and "only imports `quartz.*`".
  `arch/test_cleanroom.py` runs `tools/check_cleanroom.py` (§11.7) when the Blender scripts
  directory exists.

### 11.3 Differential conformance (Blender × Quartz)

- A **probe** is a Python script that uses only `bpy`/`mathutils` and writes a JSON via
  `_probe_runtime.Recorder`. The same file runs:
  - in Blender: `blender --background --factory-startup --python-exit-code 1 --python p_x.py -- --out <tmp>/p_x.json`
    via `tools/run_probes_blender.py` (120 s timeout per probe, user resources redirected
    to `tmp/blender_user` as `run_dump_bpy_api.ps1` already does). The golden is only updated in
    `tests/conformance/golden/blender-5.2.2/` with an explicit `--update-goldens`;
  - in Quartz: `quartz.testing.run_probe(path) -> dict` in-process, with compat active and the factory
    scene.
- Normalization (`quartz/testing/compare.py`): `mathutils` types → `{"__math__": type, "v": [...]}`;
  `set` → marked sorted list; ID → `{"__id__": type, "name": ...}`; exception →
  `{"__exc__": "RuntimeError", "has": [chosen fragments]}` (without comparing the whole text);
  geometry → canonical form (positions rounded and sorted; edges and faces as sets of
  positions). Floats: `|a-b| ≤ 1e-5 + 1e-5·|b|`.
- `deviations.toml`: `[[deviation]] probe = "...", key = "...", reason = "..."`. A diverging key
  that is not listed fails the test. A deviation that no longer diverges also fails (to keep the list
  honest).
- The versioned goldens let the tests run **without** Blender. The `blender` marker exists only
  to regenerate.

### 11.4 Schema tests (dump as a static oracle)

- `test_builtin_ops_schema.py`: for each Quartz built-in operator, names/types/defaults/limits/
  enum items/`bl_options` equal to those in the dump (`ops.submodules`), via
  `tools/build_op_schemas.py`.
- `test_rna_surface.py`: for the milestone types, the dump properties that Quartz declares
  as implemented have the same type, subtype, unit, `array_length`, default and limits.
- `test_usage_surface.py`: every Tier 1 symbol in `data/bpy_usage.json` resolves in the compat layer
  (`import` + chained `getattr`). A report (`tools/surface_report.py` →
  `data/compat_coverage.json`) measures coverage weighted by references, Tier 1+2 and Tier 1+2+3.

### 11.5 Add-on sweep (integration)

`tests/sweep/test_sweep.py` (marker `sweep`) runs `addon-sweep` over `tests/fixtures`,
`templates_py` and `addons_core` and compares against a versioned baseline
(`tests/sweep/baseline.json`: level reached per target). **Regression = any target dropping a level.**
Moving up a level updates the baseline on purpose.

### 11.6 Performance (smoke)

Generous budgets to catch gross regressions: `from_pydata` of 100k quads; `foreach_get`
of 1M floats; 10k `Vector` ops; registering 200 classes; 1000 empty operator calls.

### 11.7 New tools in `tools/`

| Tool | Does |
|---|---|
| `build_compat_profile.py` | dump → `quartz/compat/profiles/blender_5_2.json` (names, types, defaults only) |
| `build_op_schemas.py` | dump → `tests/schema/data/builtin_ops.json` |
| `run_probes_blender.py` + `.ps1` | runs the probes in Blender with a timeout; writes to `tmp/`; `--update-goldens` copies |
| `surface_report.py` | coverage of `data/bpy_usage.json` by the compat layer |
| `check_cleanroom.py` | compares windows of 6+ normalized lines (tokens) of Quartz `.py` files against the Blender scripts and flags long matches (trivial windows, such as imports and `pass`, go in an ignored list) |
| `check_headers.py` | rule 4 (docstring + author) |

---

## 12. Implementation order in 3 layers, with public API per module

The signatures below are **public and normative** for the milestone. `→` indicates the return value. Keyword-only
parameters follow bpy.

### Layer 1 — foundations (no cross dependencies)

#### 12.1 `quartz._kernels` (layer 0, private)

```python
# rotation.py (float64)
def euler_to_mat3(angles: ArrayLike, order: str = "XYZ") -> np.ndarray
def mat3_to_euler(m: ArrayLike, order: str = "XYZ", compat: ArrayLike | None = None) -> np.ndarray
def quat_to_mat3(q: ArrayLike) -> np.ndarray            # q = (w, x, y, z)
def mat3_to_quat(m: ArrayLike) -> np.ndarray
def axis_angle_to_mat3(axis: ArrayLike, angle: float) -> np.ndarray
def quat_mul(a: ArrayLike, b: ArrayLike) -> np.ndarray
def quat_slerp(a: ArrayLike, b: ArrayLike, t: float) -> np.ndarray
# naming.py
def truncate_utf8(name: str, max_bytes: int = 255) -> str
def split_suffix(name: str) -> tuple[str, int | None]   # "Cube.012" → ("Cube", 12)
def unique_name(name: str, taken: Container[str], *, default: str, max_bytes: int = 255) -> str
```

#### 12.2 `quartz.math` (= `mathutils`)

```python
class Vector:
    def __init__(self, seq: Iterable[float] = (0.0, 0.0, 0.0)) -> None
    @classmethod
    def Fill(cls, size: int, fill: float = 0.0) -> Vector
    @classmethod
    def Range(cls, start: int, stop: int | None = None, step: int = 1) -> Vector
    @classmethod
    def Linspace(cls, start: float, stop: float, size: int) -> Vector
    @classmethod
    def Repeat(cls, vector: Sequence[float], size: int) -> Vector
    x: float; y: float; z: float; w: float                     # rw depending on the size
    # generated swizzles: xy, xyz, zyx, ... (writing only without repeated components)
    length: float                                              # rw (rescales)
    length_squared: float; magnitude: float
    is_wrapped: bool; is_frozen: bool; is_valid: bool; owner: object | None
    def copy(self) -> Vector
    def freeze(self) -> Vector
    def to_tuple(self, precision: int = -1) -> tuple[float, ...]
    def to_2d(self) -> Vector; def to_3d(self) -> Vector; def to_4d(self) -> Vector
    def resize(self, size: int) -> None; def resized(self, size: int) -> Vector
    def resize_2d(self) -> None; def resize_3d(self) -> None; def resize_4d(self) -> None
    def normalize(self) -> None; def normalized(self) -> Vector
    def negate(self) -> None; def zero(self) -> None
    def dot(self, other: Sequence[float]) -> float
    def cross(self, other: Sequence[float]) -> Vector | float
    def angle(self, other: Sequence[float], fallback: Any = None) -> float
    def angle_signed(self, other: Sequence[float], fallback: Any = None) -> float
    def lerp(self, other: Sequence[float], factor: float) -> Vector
    def slerp(self, other: Sequence[float], factor: float, fallback: Any = None) -> Vector
    def project(self, other: Sequence[float]) -> Vector
    def reflect(self, mirror: Sequence[float]) -> Vector
    def orthogonal(self) -> Vector
    def rotate(self, other: Euler | Quaternion | Matrix) -> None
    def rotation_difference(self, other: Sequence[float]) -> Quaternion
    def to_track_quat(self, track: str = "Z", up: str = "Y") -> Quaternion
    # operators: + - (vector), * / (scalar and element-wise), @ (dot; Matrix), unary -, ==, !=, <, <= (by length),
    # len, [i], [a:b], iter, __array__ (extra); hash only when frozen

class Matrix:
    def __init__(self, rows: Iterable[Iterable[float]] = ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1))) -> None
    @classmethod
    def Identity(cls, size: int) -> Matrix
    @classmethod
    def Translation(cls, vector: Sequence[float]) -> Matrix
    @classmethod
    def Rotation(cls, angle: float, size: int, axis: str | Sequence[float]) -> Matrix
    @classmethod
    def Scale(cls, factor: float, size: int, axis: Sequence[float] | None = None) -> Matrix
    @classmethod
    def Diagonal(cls, vector: Sequence[float]) -> Matrix
    @classmethod
    def OrthoProjection(cls, axis: str | Sequence[float], size: int) -> Matrix
    @classmethod
    def Shear(cls, plane: str, size: int, factor: float | Sequence[float]) -> Matrix
    @classmethod
    def LocRotScale(cls, location: Sequence[float] | None, rotation: Matrix | Quaternion | Euler | None,
                    scale: Sequence[float] | None) -> Matrix
    row: MatrixAccess; col: MatrixAccess                        # wrapped views
    translation: Vector                                         # rw
    median_scale: float; is_identity: bool; is_negative: bool; is_orthogonal: bool; is_orthogonal_axis_vectors: bool
    is_wrapped: bool; is_frozen: bool; is_valid: bool; owner: object | None
    def determinant(self) -> float
    def transpose(self) -> None; def transposed(self) -> Matrix
    def invert(self, fallback: Matrix | None = None) -> None; def inverted(self, fallback: Any = None) -> Matrix
    def invert_safe(self) -> None; def inverted_safe(self) -> Matrix
    def adjugate(self) -> None; def adjugated(self) -> Matrix
    def normalize(self) -> None; def normalized(self) -> Matrix
    def zero(self) -> None; def identity(self) -> None
    def to_2x2(self) -> Matrix; def to_3x3(self) -> Matrix; def to_4x4(self) -> Matrix; def resize_4x4(self) -> None
    def to_euler(self, order: str = "XYZ", euler_compat: Euler | None = None) -> Euler
    def to_quaternion(self) -> Quaternion
    def to_scale(self) -> Vector; def to_translation(self) -> Vector
    def decompose(self) -> tuple[Vector, Quaternion, Vector]
    def lerp(self, other: Matrix, factor: float) -> Matrix
    def rotate(self, other: Euler | Quaternion | Matrix) -> None
    def copy(self) -> Matrix; def freeze(self) -> Matrix
    # m[i] → wrapped row; m @ Matrix; m @ Vector (4x4 @ vector-3 → implicit homogeneous, returns vector-3); vec @ m (row vector)

class Quaternion:
    def __init__(self, seq: Sequence[float] = (1.0, 0.0, 0.0, 0.0), angle: float | None = None) -> None
                                                                # (seq4) | (axis, angle) | (exponential map 3)
    w: float; x: float; y: float; z: float; angle: float; axis: Vector; magnitude: float
    def conjugate(self) -> None; def conjugated(self) -> Quaternion
    def invert(self) -> None; def inverted(self) -> Quaternion
    def normalize(self) -> None; def normalized(self) -> Quaternion; def negate(self) -> None; def identity(self) -> None
    def dot(self, other: Quaternion) -> float; def cross(self, other: Quaternion) -> Quaternion
    def rotation_difference(self, other: Quaternion) -> Quaternion
    def slerp(self, other: Quaternion, factor: float) -> Quaternion
    def rotate(self, other: Euler | Quaternion | Matrix) -> None
    def make_compatible(self, other: Quaternion) -> None
    def to_matrix(self) -> Matrix
    def to_euler(self, order: str = "XYZ", euler_compat: Euler | None = None) -> Euler
    def to_axis_angle(self) -> tuple[Vector, float]
    def to_exponential_map(self) -> Vector
    def to_swing_twist(self, axis: str) -> tuple[Quaternion, float]
    def copy(self) -> Quaternion; def freeze(self) -> Quaternion
    # q @ q (composition), q @ Vector (rotates), ==, [i], len

class Euler:
    def __init__(self, angles: Sequence[float] = (0.0, 0.0, 0.0), order: str = "XYZ") -> None
    x: float; y: float; z: float; order: str
    def to_matrix(self) -> Matrix; def to_quaternion(self) -> Quaternion
    def rotate(self, other: Euler | Quaternion | Matrix) -> None
    def rotate_axis(self, axis: str, angle: float) -> None
    def make_compatible(self, other: Euler) -> None
    def zero(self) -> None; def copy(self) -> Euler; def freeze(self) -> Euler

class Color:
    def __init__(self, rgb: Sequence[float] = (0.0, 0.0, 0.0)) -> None
    r: float; g: float; b: float; h: float; s: float; v: float; hsv: tuple[float, float, float]
    def copy(self) -> Color; def freeze(self) -> Color
    def from_scene_linear_to_srgb(self) -> Color; def from_srgb_to_scene_linear(self) -> Color
    # other conversions (ACES, Rec.2020, XYZ) → NotImplementedInQuartz at the milestone

# geometry.py (subset)
def intersect_ray_tri(v1, v2, v3, ray, orig, clip: bool = True) -> Vector | None
def intersect_line_plane(line_a, line_b, plane_co, plane_no, no_flip: bool = False) -> Vector | None
def intersect_line_line(v1, v2, v3, v4) -> tuple[Vector, Vector] | None
def intersect_point_line(pt, line_p1, line_p2) -> tuple[Vector, float]
def intersect_point_tri(pt, tri_p1, tri_p2, tri_p3) -> Vector | None
def closest_point_on_tri(pt, tri_p1, tri_p2, tri_p3) -> Vector
def distance_point_to_plane(pt, plane_co, plane_no) -> float
def normal(*vectors) -> Vector
def area_tri(v1, v2, v3) -> float
def volume_tetrahedron(v1, v2, v3, v4) -> float
def tessellate_polygon(veclist_list: Sequence[Sequence[Sequence[float]]]) -> list[tuple[int, int, int]]
def barycentric_transform(point, tri_a1, tri_a2, tri_a3, tri_b1, tri_b2, tri_b3) -> Vector
def interpolate_bezier(knot1, handle1, handle2, knot2, resolution: int) -> list[Vector]
def convex_hull_2d(points) -> list[int]
# kdtree.py
class KDTree:
    def __init__(self, size: int) -> None
    def insert(self, co: Sequence[float], index: int) -> None
    def balance(self) -> None
    def find(self, co: Sequence[float], filter: Callable[[int], bool] | None = None) -> tuple[Vector | None, int | None, float | None]
    def find_n(self, co: Sequence[float], n: int) -> list[tuple[Vector, int, float]]
    def find_range(self, co: Sequence[float], radius: float) -> list[tuple[Vector, int, float]]
# bvhtree.py (Tier 3; FromObject imports quartz.types lazily, exception listed in the layering test)
class BVHTree:
    @classmethod
    def FromPolygons(cls, vertices, polygons, all_triangles: bool = False, epsilon: float = 0.0) -> BVHTree
    @classmethod
    def FromObject(cls, object, depsgraph, *, deform: bool = True, render: bool = False, cage: bool = False, epsilon: float = 0.0) -> BVHTree
    def ray_cast(self, origin, direction, distance: float = sys.float_info.max) -> tuple[Vector | None, Vector | None, int | None, float | None]
    def find_nearest(self, origin, distance: float = sys.float_info.max) -> tuple[Vector | None, Vector | None, int | None, float | None]
    def find_nearest_range(self, origin, distance: float = sys.float_info.max) -> list[tuple[Vector, Vector, int, float]]
    def overlap(self, other_tree: BVHTree) -> list[tuple[int, int]]
# scalar.py (= bl_math)
def clamp(value: float, min: float = 0.0, max: float = 1.0) -> float
def lerp(from_value: float, to_value: float, factor: float) -> float
def smoothstep(from_value: float, to_value: float, value: float) -> float
# noise.py, interpolate.py → stubs NotImplementedInQuartz (deferred)
```

Storage: its own `ndarray[float32]`, or a *view* of the owner when *wrapped*, plus a write
callback. Arithmetic is done in float32 (close to the C math of mathutils).

#### 12.3 `quartz.rna`

```python
class _PropertyDeferred:
    function: Callable[..., _PropertyDeferred]; keywords: dict[str, Any]
class RNAMeta(type):
    is_registered: bool                                   # class property: "bl_rna" in cls.__dict__
    def __setattr__(cls, name: str, value: Any) -> None   # deferred on registered/built-in type → defines property
    def __delattr__(cls, name: str) -> None
class Struct(metaclass=RNAMeta):                          # = bpy_struct
    bl_rna: ClassVar[StructRNA]
    @property
    def rna_type(self) -> StructRNA
    @property
    def id_data(self) -> "ID | None"
    def as_pointer(self) -> int
    def path_from_id(self, property: str = "") -> str
    def path_from_module(self, property: str = "", index: int = -1) -> str
    def path_resolve(self, path: str, coerce: bool = True) -> Any
    def is_property_set(self, property: str, *, ghost: bool = True) -> bool
    def property_unset(self, property: str) -> None
    def is_property_readonly(self, property: str) -> bool
    def is_property_hidden(self, property: str) -> bool
    def is_property_overridable_library(self, property: str) -> bool
    def property_overridable_library_set(self, property: str, overridable: bool) -> bool
    def keys(self) -> list[str]; def values(self) -> list[Any]; def items(self) -> list[tuple[str, Any]]
    def get(self, key: str, default: Any = None) -> Any; def pop(self, key: str, default: Any = ...) -> Any
    def __getitem__(self, key: str) -> Any; def __setitem__(self, key: str, value: Any) -> None
    def __delitem__(self, key: str) -> None; def __contains__(self, key: str) -> bool
    def id_properties_ensure(self) -> IDPropertyGroup
    def id_properties_clear(self) -> None
    def id_properties_ui(self, key: str) -> IDPropertyUIManager
    def bl_system_properties_get(self, *, do_create: bool = False) -> IDPropertyGroup | None
    def type_recast(self) -> Struct
    def rna_ancestors(self) -> list[Struct]
    @classmethod
    def bl_rna_get_subclass(cls, id: str, default: Any = None) -> StructRNA | None
    @classmethod
    def bl_rna_get_subclass_py(cls, id: str, default: Any = None) -> type | None
    def keyframe_insert(self, data_path: str, *, index: int = -1, frame: float = ..., group: str = "", options: set[str] = set(), keytype: str = "KEYFRAME") -> bool   # NotImplementedInQuartz in the milestone
    def keyframe_delete(self, data_path: str, *, index: int = -1, frame: float = ..., group: str = "") -> bool                                                        # same
    def driver_add(self, path: str, index: int = -1) -> Any; def driver_remove(self, path: str, index: int = -1) -> bool                                             # same

class StructRNA:
    identifier: str; name: str; description: str; translation_context: str
    base: StructRNA | None; nested: StructRNA | None
    properties: PropCollection[PropertyRNA]; functions: PropCollection[FunctionRNA]
    py_class: type
    def property(self, identifier: str) -> PropertyRNA | None          # native extra
class PropertyRNA:                                     # descriptor; metadata with the names of bpy.types.Property
    identifier: str; name: str; description: str; translation_context: str
    type: Literal["BOOLEAN", "INT", "FLOAT", "STRING", "ENUM", "POINTER", "COLLECTION"]
    subtype: str; unit: str; icon: str
    is_readonly: bool; is_hidden: bool; is_skip_save: bool; is_animatable: bool; is_enum_flag: bool
    is_library_editable: bool; is_overridable: bool; is_required: bool; is_argument_optional: bool
    is_never_none: bool; is_output: bool; is_registered: bool; is_registered_optional: bool; is_runtime: bool
    options: frozenset[str]; tags: frozenset[str]
    group: str | None; ui_parent: str | None; enabled_if: Callable[[Struct], bool] | None; dirty: frozenset[str]   # native
    def __set_name__(self, owner: type, name: str) -> None
    def __get__(self, inst: Struct | None, owner: type) -> Any
    def __set__(self, inst: Struct, value: Any) -> None
    def coerce(self, inst: Struct, value: Any) -> Any
    def notify(self, inst: Struct) -> None
class BoolPropertyRNA(PropertyRNA): default: bool; array_length: int; array_dimensions: tuple[int, ...]; default_array: tuple[bool, ...]
class IntPropertyRNA(PropertyRNA): default: int; hard_min: int; hard_max: int; soft_min: int; soft_max: int; step: int; array_length: int; array_dimensions: tuple[int, ...]; default_array: tuple[int, ...]
class FloatPropertyRNA(PropertyRNA): default: float; hard_min: float; hard_max: float; soft_min: float; soft_max: float; step: float; precision: int; array_length: int; array_dimensions: tuple[int, ...]; default_array: tuple[float, ...]
class StringPropertyRNA(PropertyRNA): default: str; length_max: int
class EnumPropertyRNA(PropertyRNA):
    default: str | set[str]; enum_items: PropCollection[EnumPropertyItem]; enum_items_static: PropCollection[EnumPropertyItem]
    def items_for(self, inst: Struct | None, context: Any) -> list[EnumPropertyItem]
class PointerPropertyRNA(PropertyRNA): fixed_type: StructRNA; poll: Callable[[Struct, Struct], bool] | None
class CollectionPropertyRNA(PropertyRNA): fixed_type: StructRNA
class EnumPropertyItem: identifier: str; name: str; description: str; icon: str; value: int

class PropCollection(Generic[T]):                      # = bpy_prop_collection
    def __len__(self) -> int; def __iter__(self) -> Iterator[T]
    def __getitem__(self, key: int | str | slice) -> T | list[T]; def __contains__(self, key: str) -> bool
    def get(self, key: str, default: Any = None) -> T | None
    def find(self, key: str) -> int
    def keys(self) -> list[str]; def values(self) -> list[T]; def items(self) -> list[tuple[str, T]]
    def foreach_get(self, attr: str, seq: MutableSequence | np.ndarray) -> None
    def foreach_set(self, attr: str, seq: Sequence | np.ndarray) -> None
    rna_type: StructRNA; id_data: "ID | None"
class GroupCollection(PropCollection[PG]):
    def add(self) -> PG; def remove(self, index: int) -> None; def clear(self) -> None; def move(self, from_index: int, to_index: int) -> None
class PropArray(Sequence):                             # = bpy_prop_array (vector Bool/Int and Float without math subtype)
    def foreach_get(self, seq) -> None; def foreach_set(self, seq) -> None
    def to_list(self) -> list   # extra

# idprops.py
class IDPropertyGroup(MutableMapping[str, Any]):
    name: str
    def to_dict(self) -> dict[str, Any]; def update(self, other: Mapping[str, Any]) -> None
class IDPropertyArray(Sequence):
    typecode: str
    def to_list(self) -> list; def __array__(self, dtype=None) -> np.ndarray
class IDPropertyUIManager:
    def update(self, *, subtype: str | None = None, min=None, max=None, soft_min=None, soft_max=None,
               precision: int | None = None, step=None, default=None, id_type: str | None = None,
               items=None, description: str | None = None) -> None
    def as_dict(self) -> dict[str, Any]; def clear(self) -> None; def update_from(self, ui_manager: IDPropertyUIManager) -> None
def ui_create(item: Struct, prop: str, *, default: Any, min: Any = 0, max: Any = 1, soft_min: Any = None, soft_max: Any = None,
              description: str | None = None, overridable: bool = False, subtype: str | None = None, **kwargs) -> None   # = rna_idprop_ui_create

# registry.py
class TypeRegistry:
    def add(self, rna_name: str, cls: type) -> None; def remove(self, rna_name: str) -> None
    def get(self, rna_name: str) -> type | None; def names(self) -> list[str]
    def find_by_idname(self, base: type, bl_idname: str) -> type | None
    def operators(self) -> dict[str, type]           # idname_py → class
def operator_idname_to_rna(idname_py: str) -> str    # "quartz_probe.hello" → "QUARTZ_PROBE_OT_hello"
def operator_rna_to_idname(rna_name: str) -> str
def validate_operator_idname(idname_py: str) -> None # RegistrationRuntimeError

# datapath.py
@dataclass(frozen=True)
class PathToken: kind: Literal["attr", "index", "key"]; value: str | int
def parse(path: str) -> list[PathToken]
def format(tokens: Sequence[PathToken]) -> str
def resolve(root: Any, path: str, *, coerce: bool = True) -> Any

# array.py / hooks.py (seams of §3)
def set_array_wrapper(subtype: str, factory: Callable[[np.ndarray, Callable[[], None]], Any]) -> None
class hooks:
    get_context: Callable[[], Any]
    on_property_changed: Callable[[Struct, PropertyRNA], None]
    on_struct_created: Callable[[Struct], None]
```

#### 12.4 `quartz.props`

```python
def BoolProperty(*, name: str = "", description: str = "", translation_context: str = "*", default: bool = False,
                 options: set[str] = {"ANIMATABLE"}, override: set[str] = set(), tags: set[str] = set(),
                 subtype: str = "NONE", update=None, get=None, set=None, get_transform=None, set_transform=None,
                 **native) -> _PropertyDeferred
def BoolVectorProperty(*, name="", description="", translation_context="*", default=(False, False, False),
                       options={"ANIMATABLE"}, override=set(), tags=set(), subtype="NONE", size: int | tuple[int, ...] = 3,
                       update=None, get=None, set=None, get_transform=None, set_transform=None, **native) -> _PropertyDeferred
def IntProperty(*, name="", description="", translation_context="*", default: int = 0, min: int = -2**31, max: int = 2**31 - 1,
                soft_min: int = -2**31, soft_max: int = 2**31 - 1, step: int = 1, options={"ANIMATABLE"}, override=set(), tags=set(),
                subtype="NONE", update=None, get=None, set=None, get_transform=None, set_transform=None, **native) -> _PropertyDeferred
def IntVectorProperty(*, ..., default=(0, 0, 0), size: int | tuple[int, ...] = 3, ...) -> _PropertyDeferred
def FloatProperty(*, name="", description="", translation_context="*", default: float = 0.0,
                  min: float = -3.402823e38, max: float = 3.402823e38, soft_min: float = -3.402823e38, soft_max: float = 3.402823e38,
                  step: float = 3, precision: int = 2, options={"ANIMATABLE"}, override=set(), tags=set(),
                  subtype="NONE", unit="NONE", update=None, get=None, set=None, get_transform=None, set_transform=None, **native) -> _PropertyDeferred
def FloatVectorProperty(*, ..., default=(0.0, 0.0, 0.0), size: int | tuple[int, ...] = 3, ...) -> _PropertyDeferred
def StringProperty(*, name="", description="", translation_context="*", default: str = "", maxlen: int = 0,
                   options={"ANIMATABLE"}, override=set(), tags=set(), subtype="NONE", update=None, get=None, set=None,
                   get_transform=None, set_transform=None, search=None, search_options={"SUGGESTION"}, **native) -> _PropertyDeferred
def EnumProperty(items, *, name="", description="", translation_context="*", default: str | int | set[str] | None = None,
                 options={"ANIMATABLE"}, override=set(), tags=set(), update=None, get=None, set=None,
                 get_transform=None, set_transform=None, **native) -> _PropertyDeferred
def PointerProperty(*, type: type, name="", description="", translation_context="*", options={"ANIMATABLE"},
                    override=set(), tags=set(), poll=None, update=None, **native) -> _PropertyDeferred
def CollectionProperty(*, type: type, name="", description="", translation_context="*", options={"ANIMATABLE"},
                       override=set(), tags=set(), **native) -> _PropertyDeferred
def RemoveProperty(cls: type, *, attr: str) -> None
# **native: group, ui_parent, enabled_if (public); storage, dirty (internal, only for built-ins)
```

The `Float*` defaults come from the dump [O]. The `Int*` ones use the int32 range [I, to be verified in
`p_props_semantics`].

#### 12.5 `quartz.geometry`

```python
DOMAINS: tuple[str, ...] = ("POINT", "EDGE", "FACE", "CORNER")
DATA_TYPES: Mapping[str, tuple[np.dtype, tuple[int, ...]]]   # "FLOAT"→(f32,()), "FLOAT_VECTOR"→(f32,(3,)), "FLOAT2"→(f32,(2,)),
                                                             # "FLOAT_COLOR"→(f32,(4,)), "BYTE_COLOR"→(u8,(4,)), "INT"→(i32,()),
                                                             # "INT8"→(i8,()), "INT32_2D"→(i32,(2,)), "BOOLEAN"→(bool,()),
                                                             # "QUATERNION"→(f32,(4,)), "FLOAT4X4"→(f32,(4,4))
@dataclass
class AttributeArray:
    domain: str; data_type: str; data: np.ndarray
    def resized(self, n: int) -> AttributeArray
@dataclass
class MeshArrays:
    positions: np.ndarray          # (V,3) float32
    edges: np.ndarray              # (E,2) int32
    face_offsets: np.ndarray       # (F+1,) int32
    corner_verts: np.ndarray       # (L,) int32
    corner_edges: np.ndarray       # (L,) int32
    attributes: dict[str, AttributeArray]
    @property
    def num_verts(self) -> int     # same for num_edges, num_faces, num_corners
    @classmethod
    def empty(cls) -> MeshArrays
    def copy(self) -> MeshArrays
    def domain_size(self, domain: str) -> int
# topology.py
def from_pydata(vertices: ArrayLike, edges: Sequence[Sequence[int]], faces: Sequence[Sequence[int]]) -> MeshArrays
def calc_edges(face_offsets: np.ndarray, corner_verts: np.ndarray, loose_edges: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]
def edge_keys(edges: np.ndarray) -> np.ndarray                    # (E,2) sorted per row
def face_sizes(face_offsets: np.ndarray) -> np.ndarray
def loose_edges(arrays: MeshArrays) -> np.ndarray
# normals.py
def face_normals(positions, face_offsets, corner_verts) -> np.ndarray       # Newell
def vertex_normals(positions, face_offsets, corner_verts, face_normals: np.ndarray | None = None) -> np.ndarray  # angle-weighted
def face_centers(positions, face_offsets, corner_verts) -> np.ndarray
def face_areas(positions, face_offsets, corner_verts) -> np.ndarray
# triangulate.py
def triangulate(positions, face_offsets, corner_verts, *, quad_method: str = "BEAUTY", ngon_method: str = "BEAUTY") -> tuple[np.ndarray, np.ndarray]  # (tris (T,3) corner indices, face (T,))
def triangulate_arrays(arrays: MeshArrays, **kw) -> MeshArrays
# validate.py
def validate(arrays: MeshArrays, *, fix: bool = False) -> tuple[bool, list[str]]   # (changed?, problems)
# transform.py
def compose_trs(location, rotation3: np.ndarray, scale) -> np.ndarray              # (4,4) float64
def decompose_trs(m4: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]    # loc, quat(wxyz), scale
def transform_points(points: np.ndarray, m4: np.ndarray) -> np.ndarray
def transform_normals(normals: np.ndarray, m4: np.ndarray) -> np.ndarray
# bounds.py
def bounds(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]
def bound_box(points: np.ndarray) -> np.ndarray                                    # (8,3), same corner order as bpy's bound_box [I]
# primitives.py — each → MeshArrays (+ "UVMap" FLOAT2/CORNER if calc_uvs)
def plane(size: float = 2.0, *, calc_uvs: bool = True) -> MeshArrays
def cube(size: float = 2.0, *, calc_uvs: bool = True) -> MeshArrays
def grid(x_subdivisions: int = 10, y_subdivisions: int = 10, size: float = 2.0, *, calc_uvs: bool = True) -> MeshArrays
def circle(vertices: int = 32, radius: float = 1.0, *, fill_type: str = "NOTHING", calc_uvs: bool = True) -> MeshArrays
def uv_sphere(segments: int = 32, ring_count: int = 16, radius: float = 1.0, *, calc_uvs: bool = True) -> MeshArrays
def ico_sphere(subdivisions: int = 2, radius: float = 1.0, *, calc_uvs: bool = True) -> MeshArrays
def cylinder(vertices: int = 32, radius: float = 1.0, depth: float = 2.0, *, end_fill_type: str = "NGON", calc_uvs: bool = True) -> MeshArrays
def cone(vertices: int = 32, radius1: float = 1.0, radius2: float = 0.0, depth: float = 2.0, *, end_fill_type: str = "NGON", calc_uvs: bool = True) -> MeshArrays
def torus(major_segments: int = 48, minor_segments: int = 12, major_radius: float = 1.0, minor_radius: float = 0.25, *, calc_uvs: bool = True) -> MeshArrays
```

The primitives' defaults are checked against the dump (`mesh.primitive_*_add`), and the
v/e/f counts against the `p_primitives` probe.

**Layer 1 done criteria:** `tests/unit/{math,rna,geometry}` + `tests/arch` green. Each [O] rule of
`bpy_contract.md` §4 covered in a test host class (minimal Struct, no ID). Cube
8/12/6/24. No cross imports.

### Layer 2 — data model + registration/ops

#### 12.6 `quartz.app`

```python
version: tuple[int, int, int]; version_string: str; version_cycle: str
background: bool                 # always True in this milestone
factory_startup: bool; binary_path: str; tempdir: str; cachedir: str
debug: bool; debug_value: int; driver_namespace: dict[str, Any]
online_access: bool; online_access_override: bool; portable: bool; python_args: tuple[str, ...]
handlers: Handlers; timers: ModuleType; translations: ModuleType; icons: ModuleType
settings: QuartzSettings
def factory_reset(*, template: Literal["default", "empty"] = "default") -> None
# handlers.py
class Handlers:
    # 39 Blender lists: animation_playback_pre, ..., depsgraph_update_post, frame_change_pre, frame_change_post,
    # load_pre, load_post, load_post_fail, save_pre, save_post, save_post_fail, undo_pre, undo_post, redo_pre, redo_post,
    # version_update, exit_pre, ... (exact list in the profile)  +  startup_post, shutdown_pre, shutdown_post
    def call(self, name: str, *args: Any) -> None
def persistent(function: F) -> F
# timers.py
def register(function: Callable[[], float | None], *, first_interval: float = 0, persistent: bool = False) -> None
def unregister(function: Callable[[], float | None]) -> None
def is_registered(function: Callable[[], float | None]) -> bool
def pump(*, now: float | None = None, max_calls: int | None = None) -> int
# translations.py
def pgettext(msgid: str, msgctxt: str | None = None) -> str        # same for pgettext_iface, _tip, _rpt, _data, _n
def register(module_name: str, translations_dict: dict) -> None
def unregister(module_name: str) -> None
def locale_explode(locale: str) -> tuple[str | None, ...]
locale: str; locales: tuple[str, ...]; contexts: TranslationContexts; contexts_C_to_py: dict[str, str]
# settings.py
@dataclass
class QuartzSettings:
    user_dir: Path; addon_paths: list[Path]; strict_restrict: bool = True
    ghosts: Literal["error", "log", "silent"] = "log"; headless_dialogs: Literal["running_modal", "execute"] = "running_modal"
```

#### 12.7 `quartz.types` — IDs and `bpy.data` collections

```python
class ID(Struct):
    name: str; name_full: str; id_type: str; session_uid: int; users: int; use_fake_user: bool; use_extra_user: bool
    is_evaluated: bool; original: Self; library: None; tag: bool; is_embedded_data: bool; is_missing: bool
    is_runtime_data: bool; is_editable: bool; asset_data: None; preview: None
    def copy(self) -> Self
    def rename(self, name: str, *, mode: Literal["NEVER", "ALWAYS", "SAME_ROOT"] = "NEVER") -> str
    def evaluated_get(self, depsgraph: Depsgraph) -> Self
    def user_clear(self) -> None
    def user_remap(self, new_id: ID | None) -> None
    def user_of_id(self, id: ID) -> int
    def update_tag(self, *, refresh: set[str] = set()) -> None
    def make_local(self, *, clear_proxy: bool = True, clear_liboverride: bool = False) -> Self
    def animation_data_create(self) -> Any; def animation_data_clear(self) -> None      # NotImplementedInQuartz in this milestone
    def asset_mark(self) -> None; def asset_clear(self) -> None                         # same
class IDCollection(PropCollection[T]):           # base of BlendDataObjects, BlendDataMeshes, ...
    def remove(self, id: T, *, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
    def tag(self, value: bool) -> None
class BlendDataObjects(IDCollection[Object]):    def new(self, name: str, object_data: ID | None) -> Object
class BlendDataMeshes(IDCollection[Mesh]):
    def new(self, name: str) -> Mesh
    def new_from_object(self, object: Object, *, preserve_all_data_layers: bool = False, depsgraph: Depsgraph | None = None) -> Mesh
class BlendDataMaterials(IDCollection[Material]):     def new(self, name: str) -> Material
class BlendDataCameras(IDCollection[Camera]):         def new(self, name: str) -> Camera
class BlendDataLights(IDCollection[Light]):           def new(self, name: str, type: Literal["POINT", "SUN", "SPOT", "AREA"]) -> Light
class BlendDataCollections(IDCollection[Collection]): def new(self, name: str) -> Collection
class BlendDataScenes(IDCollection[Scene]):           def new(self, name: str) -> Scene   # remove(scene, *, do_unlink=True)
class BlendDataWorlds(IDCollection[World]):           def new(self, name: str) -> World
class BlendDataImages(IDCollection[Image]):
    def new(self, name: str, width: int, height: int, *, alpha: bool = False, float_buffer: bool = False,
            stereo3d: bool = False, is_data: bool = False, tiled: bool = False) -> Image
    def load(self, filepath: str, *, check_existing: bool = False) -> Image        # NotImplementedInQuartz
class BlendDataTexts(IDCollection[Text]):
    def new(self, name: str) -> Text
    def load(self, filepath: str, *, internal: bool = False) -> Text               # reads a UTF-8 text file
class GhostIDCollection(IDCollection[ID]):            def new(self, *args, **kwargs) -> NoReturn  # NotImplementedInQuartz
class BlendData(Struct):
    objects: BlendDataObjects; meshes: BlendDataMeshes; materials: BlendDataMaterials; cameras: BlendDataCameras
    lights: BlendDataLights; collections: BlendDataCollections; scenes: BlendDataScenes; worlds: BlendDataWorlds
    images: BlendDataImages; texts: BlendDataTexts; window_managers: IDCollection; screens: IDCollection; workspaces: IDCollection
    # + ghost collections from the profile: actions, armatures, curves, node_groups, libraries, fonts, ...
    filepath: str; is_dirty: bool; is_saved: bool; version: tuple[int, int, int]; use_autopack: bool
    def batch_remove(self, ids: Iterable[ID]) -> None
    def orphans_purge(self, *, do_local_ids: bool = True, do_linked_ids: bool = True, do_recursive: bool = False) -> int
    def user_map(self, *, subset: Iterable[ID] | None = None, key_types: set[str] | None = None,
                 value_types: set[str] | None = None) -> dict[ID, set[ID]]
    def all_ids(self) -> Iterator[ID]                                              # extra
```

#### 12.8 `quartz.types` — Object, Mesh and company

```python
class Object(ID):
    data: ID | None; type: ObjectType; mode: ModeName; parent: Object | None; parent_type: str
    location: Vector; rotation_euler: Euler; rotation_quaternion: Quaternion; rotation_axis_angle: PropArray
    rotation_mode: str; scale: Vector
    delta_location: Vector; delta_rotation_euler: Euler; delta_rotation_quaternion: Quaternion; delta_scale: Vector
    lock_location: PropArray; lock_rotation: PropArray; lock_rotation_w: bool; lock_rotations_4d: bool; lock_scale: PropArray
    matrix_basis: Matrix; matrix_local: Matrix; matrix_world: Matrix; matrix_parent_inverse: Matrix
    dimensions: Vector; bound_box: PropArray
    children: tuple[Object, ...]; children_recursive: list[Object]
    users_collection: tuple[Collection, ...]; users_scene: tuple[Scene, ...]
    modifiers: ObjectModifiers; material_slots: PropCollection[MaterialSlot]
    active_material: Material | None; active_material_index: int
    constraints: GhostCollection; vertex_groups: GhostCollection
    hide_viewport: bool; hide_render: bool; hide_select: bool
    display_type: str; show_name: bool; show_axis: bool; show_wire: bool; show_in_front: bool; show_bounds: bool
    color: Vector; empty_display_type: str; empty_display_size: float; pass_index: int
    instance_type: str; instance_collection: Collection | None; animation_data: None
    def select_get(self, *, view_layer: ViewLayer | None = None) -> bool
    def select_set(self, state: bool, *, view_layer: ViewLayer | None = None) -> None
    def hide_get(self, *, view_layer: ViewLayer | None = None) -> bool
    def hide_set(self, state: bool, *, view_layer: ViewLayer | None = None) -> None
    def visible_get(self, *, view_layer: ViewLayer | None = None, viewport: Any = None) -> bool
    def to_mesh(self, *, preserve_all_data_layers: bool = False, depsgraph: Depsgraph | None = None) -> Mesh
    def to_mesh_clear(self) -> None
    def is_modified(self, scene: Scene, settings: Literal["PREVIEW", "RENDER"]) -> bool
    def convert_space(self, *, pose_bone: None = None, matrix: Matrix = ..., from_space: str = "WORLD", to_space: str = "WORLD") -> Matrix
    def ray_cast(self, origin, direction, *, distance: float = 1.70141e38, depsgraph: Depsgraph | None = None) -> tuple[bool, Vector, Vector, int]
    def closest_point_on_mesh(self, origin, *, distance: float = 1.84467e19, depsgraph: Depsgraph | None = None) -> tuple[bool, Vector, Vector, int]
class MaterialSlot(Struct): link: Literal["OBJECT", "DATA"]; material: Material | None; slot_index: int; name: str
class ObjectModifiers(PropCollection[Modifier]):
    def new(self, name: str, type: str) -> Modifier; def remove(self, modifier: Modifier) -> None
    def clear(self) -> None; def move(self, from_index: int, to_index: int) -> None
    active: Modifier | None
class Modifier(Struct):
    name: str; type: str; show_viewport: bool; show_render: bool; show_in_editmode: bool; show_on_cage: bool
    show_expanded: bool; is_active: bool; use_pin_to_last: bool; persistent_uid: int
class TriangulateModifier(Modifier): quad_method: str; ngon_method: str; min_vertices: int; keep_custom_normals: bool

class Mesh(ID):
    vertices: MeshVertices; edges: MeshEdges; loops: MeshLoops; polygons: MeshPolygons
    attributes: AttributeGroupMesh; color_attributes: AttributeGroupMesh; uv_layers: UVLoopLayers
    vertex_normals: PropCollection; polygon_normals: PropCollection; corner_normals: PropCollection; normals_domain: str
    loop_triangles: MeshLoopTriangles; loop_triangle_polygons: PropCollection
    materials: IDMaterials; is_editmode: bool; total_vert_sel: int; total_edge_sel: int; total_face_sel: int
    edge_keys: list[tuple[int, int]]; shape_keys: None; has_custom_normals: bool
    texspace_location: Vector; texspace_size: Vector; use_auto_texspace: bool
    def from_pydata(self, vertices, edges, faces, *, shade_flat: bool = True) -> None
    def update(self, *, calc_edges: bool = False, calc_edges_loose: bool = False) -> None
    def validate(self, *, verbose: bool = False, clean_customdata: bool = True) -> bool
    def validate_material_indices(self) -> bool
    def transform(self, matrix: Matrix, *, shape_keys: bool = False) -> None
    def flip_normals(self) -> None
    def calc_loop_triangles(self) -> None
    def clear_geometry(self) -> None
    def set_sharp_from_angle(self, *, angle: float = 0.523599) -> None
    def shade_flat(self) -> None; def shade_smooth(self) -> None
    def count_selected_items(self) -> tuple[int, int, int]
    def to_arrays(self, *, copy: bool = True) -> MeshArrays            # extra
    def from_arrays(self, arrays: MeshArrays) -> None                   # extra
class MeshVertices(PropCollection["MeshVertex"]):  def add(self, count: int) -> None
class MeshEdges(PropCollection["MeshEdge"]):       def add(self, count: int) -> None
class MeshLoops(PropCollection["MeshLoop"]):       def add(self, count: int) -> None
class MeshPolygons(PropCollection["MeshPolygon"]): def add(self, count: int) -> None
class MeshVertex(Struct): co: Vector; normal: Vector; select: bool; hide: bool; index: int; undeformed_co: Vector; groups: GhostCollection
class MeshEdge(Struct): vertices: PropArray; key: tuple[int, int]; index: int; select: bool; hide: bool; use_seam: bool; use_edge_sharp: bool; is_loose: bool
class MeshLoop(Struct): vertex_index: int; edge_index: int; index: int; normal: Vector
class MeshPolygon(Struct):
    vertices: PropArray; loop_start: int; loop_total: int; loop_indices: range; material_index: int; use_smooth: bool
    select: bool; hide: bool; normal: Vector; center: Vector; area: float; index: int; edge_keys: list[tuple[int, int]]
    def flip(self) -> None
class MeshLoopTriangle(Struct): vertices: PropArray; loops: PropArray; polygon_index: int; normal: Vector; area: float; center: Vector; material_index: int; use_smooth: bool
class AttributeGroupMesh(PropCollection["Attribute"]):
    def new(self, name: str, type: AttributeType, domain: AttributeDomain) -> Attribute
    def remove(self, attribute: Attribute) -> None
    def domain_size(self, domain: AttributeDomain) -> int
    active: Attribute | None; active_index: int; active_color: Attribute | None; active_color_index: int
    active_color_name: str; default_color_name: str; render_color_index: int
class Attribute(Struct):
    name: str; data_type: AttributeType; domain: AttributeDomain; is_internal: bool; is_required: bool; storage_type: str
    data: PropCollection                           # items with .value / .vector / .color / .color_srgb depending on the type
    def as_array(self) -> np.ndarray               # extra: live view
class UVLoopLayers(PropCollection["MeshUVLoopLayer"]):
    def new(self, *, name: str = "UVMap", do_init: bool = True) -> MeshUVLoopLayer
    def remove(self, layer: MeshUVLoopLayer) -> None
    active: MeshUVLoopLayer | None; active_index: int
class MeshUVLoopLayer(Struct): name: str; active: bool; active_render: bool; data: PropCollection   # items with .uv (wrapped 2D Vector)
class IDMaterials(PropCollection[Material | None]):
    def append(self, material: Material | None) -> None; def pop(self, *, index: int = -1) -> Material | None; def clear(self) -> None
```

#### 12.9 `quartz.types` — scene, collections, view layers, WM, preferences

```python
class Collection(ID):
    objects: CollectionObjects; children: CollectionChildren; all_objects: PropCollection[Object]
    children_recursive: list[Collection]; hide_select: bool; hide_viewport: bool; hide_render: bool
    instance_offset: Vector; color_tag: str
class CollectionObjects(PropCollection[Object]):
    def link(self, object: Object) -> None         # duplicate → RuntimeError
    def unlink(self, object: Object) -> None
class CollectionChildren(PropCollection[Collection]):
    def link(self, child: Collection) -> None      # cycle/duplicate → RuntimeError
    def unlink(self, child: Collection) -> None
class Scene(ID):
    collection: Collection; objects: PropCollection[Object]; view_layers: ViewLayers; camera: Object | None; world: World | None
    frame_current: int; frame_start: int; frame_end: int; frame_step: int; frame_float: float; frame_subframe: float
    render: RenderSettings; unit_settings: UnitSettings; tool_settings: ToolSettings; cursor: View3DCursor
    gravity: Vector; use_gravity: bool
    def frame_set(self, frame: int, *, subframe: float = 0.0) -> None
    def statistics(self, view_layer: ViewLayer) -> str
    def ray_cast(self, depsgraph: Depsgraph, origin, direction, *, distance: float = 1.70141e38) -> tuple[bool, Vector, Vector, int, Object | None, Matrix]
class ViewLayers(PropCollection["ViewLayer"]):
    def new(self, name: str) -> ViewLayer; def remove(self, layer: ViewLayer) -> None
class ViewLayer(Struct):
    name: str; use: bool; objects: LayerObjects; layer_collection: LayerCollection; active_layer_collection: LayerCollection
    depsgraph: Depsgraph
    def update(self) -> None
class LayerObjects(PropCollection[Object]): active: Object | None; selected: PropCollection[Object]
class LayerCollection(Struct):
    collection: Collection; name: str; children: PropCollection[LayerCollection]
    exclude: bool; hide_viewport: bool; holdout: bool; indirect_only: bool; is_visible: bool
    def visible_get(self) -> bool; def has_objects(self) -> bool; def has_selected_objects(self, view_layer: ViewLayer) -> bool
class RenderSettings(Struct):
    engine: str; resolution_x: int; resolution_y: int; resolution_percentage: int; fps: int; fps_base: float; filepath: str
class UnitSettings(Struct): system: str; scale_length: float; length_unit: str; mass_unit: str; time_unit: str; temperature_unit: str; system_rotation: str
class ToolSettings(Struct): mesh_select_mode: PropArray; use_proportional_edit: bool; proportional_size: float; transform_pivot_point: str; use_snap: bool; use_keyframe_insert_auto: bool  # + ghosts
class View3DCursor(Struct): location: Vector; rotation_mode: str; rotation_euler: Euler; rotation_quaternion: Quaternion; matrix: Matrix
class WindowManager(ID):
    windows: PropCollection["Window"]; keyconfigs: KeyConfigurations; operators: PropCollection[Operator]; clipboard: str
    def modal_handler_add(self, operator: Operator) -> bool
    def fileselect_add(self, operator: Operator) -> None
    def event_timer_add(self, time_step: float, *, window: "Window | None" = None) -> "Timer"
    def event_timer_remove(self, timer: "Timer") -> None
    def progress_begin(self, min: float, max: float) -> None
    def progress_update(self, value: float) -> None
    def progress_end(self) -> None
    def invoke_props_dialog(self, operator: Operator, *, width: int = 300, title: str = "", confirm_text: str = "",
                            cancel_default: bool = False, text_ctxt: str = "", translate: bool = True) -> set[str]
    def invoke_props_popup(self, operator: Operator, event: "Event") -> set[str]
    def invoke_popup(self, operator: Operator, *, width: int = 300) -> set[str]
    def invoke_confirm(self, operator: Operator, event: "Event", *, title: str = "", message: str = "",
                       confirm_text: str = "", icon: str = "NONE", text_ctxt: str = "", translate: bool = True) -> set[str]
    def invoke_search_popup(self, operator: Operator) -> None
    def popup_menu(self, draw_func: Callable, *, title: str = "", icon: str = "NONE") -> None
    def popover(self, draw_func: Callable, *, ui_units_x: int = 0, keymap: Any = None, from_active_button: bool = False) -> None
class Window(Struct): scene: Scene; view_layer: ViewLayer; workspace: "WorkSpace"; screen: "Screen"; x: int; y: int; width: int; height: int
class KeyConfigurations(PropCollection["KeyConfig"]): addon: "KeyConfig"; user: "KeyConfig"; default: "KeyConfig"; active: "KeyConfig"
class KeyConfig(Struct): name: str; keymaps: "KeyMaps"
class KeyMaps(PropCollection["KeyMap"]):
    def new(self, name: str, *, space_type: str = "EMPTY", region_type: str = "WINDOW", modal: bool = False, tool: bool = False) -> KeyMap
    def find(self, name: str, *, space_type: str = "EMPTY", region_type: str = "WINDOW") -> KeyMap | None
    def remove(self, keymap: KeyMap) -> None
class KeyMap(Struct): name: str; space_type: str; region_type: str; is_modal: bool; keymap_items: "KeyMapItems"
class KeyMapItems(PropCollection["KeyMapItem"]):
    def new(self, idname: str, type: str, value: str, *, any: bool = False, shift: int = 0, ctrl: int = 0, alt: int = 0,
            oskey: int = 0, hyper: int = 0, key_modifier: str = "NONE", direction: str = "ANY", repeat: bool = False,
            head: bool = False) -> KeyMapItem
    def remove(self, item: KeyMapItem) -> None
class KeyMapItem(Struct): idname: str; type: str; value: str; active: bool; properties: OperatorProperties; any: bool; shift: int; ctrl: int; alt: int; oskey: int
class Preferences(Struct):
    addons: "Addons"; filepaths: "PreferencesFilePaths"; view: "PreferencesView"; edit: "PreferencesEdit"
    system: Struct; inputs: Struct; extensions: "PreferencesExtensions"; experimental: Struct
    version: tuple[int, int, int]; is_dirty: bool; use_preferences_save: bool
class Addons(PropCollection["Addon"]): ...      # entry created by the loader
class Addon(Struct): module: str; preferences: "AddonPreferences | None"
class AddonPreferences(Struct): bl_idname: ClassVar[str]; layout: "UILayout | None"
    # def draw(self, context) -> None   (optional, defined by the add-on)
```

#### 12.10 `quartz.types` — Operator, Event, inert bases

```python
class Operator(Struct):
    bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_description: ClassVar[str]; bl_translation_context: ClassVar[str]
    bl_options: ClassVar[set[str]]; bl_undo_group: ClassVar[str]; bl_property: ClassVar[str]; bl_cursor_pending: ClassVar[str]
    properties: OperatorProperties; layout: "UILayout | None"; options: "OperatorOptions"; name: str; has_reports: bool
    @classmethod
    def poll(cls, context: Context) -> bool                         # default True
    @classmethod
    def description(cls, context: Context, properties: OperatorProperties) -> str
    @classmethod
    def poll_message_set(cls, message: str, *args: Any) -> None
    def report(self, type: set[str], message: str) -> None
    def as_keywords(self, *, ignore: Iterable[str] = ()) -> dict[str, Any]
    # optional, user-defined: execute(self, context) -> set[str]; invoke(self, context, event) -> set[str];
    # modal(self, context, event) -> set[str]; cancel(self, context) -> None; check(self, context) -> bool; draw(self, context) -> None
class OperatorProperties(Struct): ...                                # same properties StructRNA as the operator
class OperatorOptions(Struct): is_invoke: bool; is_repeat: bool; is_repeat_last: bool; use_cursor_region: bool; is_grab_cursor: bool
class OperatorFileListElement(PropertyGroup): name: str
class Macro(Operator): ...                                            # inert in the milestone
class PropertyGroup(Struct): name: str
class Event(Struct):
    type: str; value: str; mouse_x: int; mouse_y: int; mouse_region_x: int; mouse_region_y: int; mouse_prev_x: int; mouse_prev_y: int
    shift: bool; ctrl: bool; alt: bool; oskey: bool; hyper: bool; is_repeat: bool; ascii: str; unicode: str; pressure: float; tilt: Vector; xr: None
    @classmethod
    def synthetic(cls, type: str, value: str = "PRESS", **fields: Any) -> Event      # extra for tests
class Space(Struct):
    @classmethod
    def draw_handler_add(cls, callback: Callable, args: tuple, region_type: str, draw_type: str) -> object
    @classmethod
    def draw_handler_remove(cls, handle: object, region_type: str) -> None
class FileHandler(Struct):
    bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_import_operator: ClassVar[str]; bl_export_operator: ClassVar[str]
    bl_file_extensions: ClassVar[str]
    @classmethod
    def poll_drop(cls, context: Context) -> bool
# inert.py: RenderEngine, HydraRenderEngine, KeyingSetInfo, Gizmo, GizmoGroup, WorkSpaceTool, AssetShelf, Node, NodeSocket,
#           NodeTree, NodeTreeInterfaceSocket — registrable, only bl_* validation; no runtime
```

#### 12.11 `quartz.ui`

```python
class _GenericUI:
    @classmethod
    def append(cls, draw_func: Callable[[Any, Context], None]) -> None
    @classmethod
    def prepend(cls, draw_func: Callable[[Any, Context], None]) -> None
    @classmethod
    def remove(cls, draw_func: Callable[[Any, Context], None]) -> None
    @classmethod
    def is_extended(cls) -> bool
class Panel(Struct, _GenericUI):
    bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_space_type: ClassVar[str]; bl_region_type: ClassVar[str]
    bl_category: ClassVar[str]; bl_context: ClassVar[str]; bl_options: ClassVar[set[str]]; bl_parent_id: ClassVar[str]
    bl_order: ClassVar[int]; bl_owner_id: ClassVar[str]; bl_translation_context: ClassVar[str]; bl_description: ClassVar[str]
    bl_ui_units_x: ClassVar[int]
    layout: UILayout; text: str; is_popover: bool; use_pin: bool
    @classmethod
    def poll(cls, context: Context) -> bool
    # draw(self, context), draw_header(self, context), draw_header_preset(self, context): user-defined
class Menu(Struct, _GenericUI):
    bl_idname: ClassVar[str]; bl_label: ClassVar[str]; bl_description: ClassVar[str]; bl_options: ClassVar[set[str]]
    bl_owner_id: ClassVar[str]; bl_translation_context: ClassVar[str]; layout: UILayout
    @classmethod
    def poll(cls, context: Context) -> bool
    @classmethod
    def draw_collapsible(cls, context: Context, layout: UILayout) -> None
    def draw_preset(self, context: Context) -> None
class Header(Struct, _GenericUI): bl_idname: ClassVar[str]; bl_space_type: ClassVar[str]; bl_region_type: ClassVar[str]; layout: UILayout
class UIList(Struct, _GenericUI):
    bl_idname: ClassVar[str]; layout_type: str; list_id: str; filter_name: str; use_filter_show: bool
    use_filter_invert: bool; use_filter_sort_alpha: bool; use_filter_sort_reverse: bool; bitflag_filter_item: int
    # draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0)
    # draw_filter(self, context, layout); filter_items(self, context, data, propname) -> tuple[list[int], list[int]]
class UI_UL_list(UIList):
    @staticmethod
    def filter_items_by_name(pattern: str, bitflag: int, items, *, propname: str = "name", flags=None, reverse: bool = False) -> list[int]
    @staticmethod
    def sort_items_helper(sort_data, key, *, reverse: bool = False) -> list[int]
    @staticmethod
    def sort_items_by_name(items, *, propname: str = "name") -> list[int]
class UILayout(Struct):
    active: bool; enabled: bool; alert: bool; alignment: str; scale_x: float; scale_y: float; ui_units_x: float; ui_units_y: float
    use_property_split: bool; use_property_decorate: bool; operator_context: str; emboss: str; activate_init: bool
    def row(self, *, align: bool = False, heading: str = "", heading_ctxt: str = "", translate: bool = True) -> UILayout
    def column(self, *, align: bool = False, heading: str = "", heading_ctxt: str = "", translate: bool = True) -> UILayout
    def column_flow(self, *, columns: int = 0, align: bool = False) -> UILayout
    def grid_flow(self, *, row_major: bool = False, columns: int = 0, even_columns: bool = False, even_rows: bool = False, align: bool = False) -> UILayout
    def box(self) -> UILayout
    def split(self, *, factor: float = 0.0, align: bool = False) -> UILayout
    def panel(self, idname: str, *, default_closed: bool = False) -> tuple[UILayout, UILayout | None]
    def panel_prop(self, data: Struct, property: str) -> tuple[UILayout, UILayout | None]
    def prop(self, data: Struct, property: str, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
             placeholder: str = "", expand: bool = False, slider: bool = False, toggle: int = -1, icon_only: bool = False,
             event: bool = False, full_event: bool = False, emboss: bool = True, index: int = -1, icon_value: int = 0,
             invert_checkbox: bool = False) -> None
    def prop_enum(self, data: Struct, property: str, value: str, *, text: str = "", icon: str = "NONE", **kw) -> None
    def prop_menu_enum(self, data: Struct, property: str, *, text: str = "", icon: str = "NONE", **kw) -> None
    def props_enum(self, data: Struct, property: str) -> None
    def prop_search(self, data: Struct, property: str, search_data: Struct, search_property: str, *, text: str = "",
                    icon: str = "NONE", results_are_suggestions: bool = False, **kw) -> None
    def operator(self, operator: str, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
                 emboss: bool = True, depress: bool = False, icon_value: int = 0, search_weight: float = 0.0) -> OperatorProperties
    def operator_enum(self, operator: str, property: str, *, icon_only: bool = False) -> None
    def operator_menu_enum(self, operator: str, property: str, *, text: str = "", icon: str = "NONE", **kw) -> OperatorProperties
    def label(self, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE", icon_value: int = 0) -> None
    def separator(self, *, factor: float = 1.0, type: str = "AUTO") -> None
    def separator_spacer(self) -> None
    def menu(self, menu: str, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE", icon_value: int = 0) -> None
    def menu_contents(self, menu: str) -> None
    def popover(self, panel: str, *, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE", icon_value: int = 0) -> None
    def context_pointer_set(self, name: str, data: Any) -> None
    def template_list(self, listtype_name: str, list_id: str, dataptr: Struct, propname: str, active_dataptr: Struct,
                      active_propname: str, *, item_dyntip_propname: str = "", rows: int = 5, maxrows: int = 5,
                      type: str = "DEFAULT", columns: int = 9, sort_reverse: bool = False, sort_lock: bool = False, **kw) -> None
    def template_ID(self, data: Struct, property: str, *, new: str = "", open: str = "", unlink: str = "", **kw) -> None
    def __getattr__(self, name: str) -> Callable[..., Any]   # remaining template_* of the profile: records generically
    def to_tree(self) -> "LayoutNode"                         # extra
@dataclass
class LayoutNode: kind: str; args: tuple; kwargs: dict[str, Any]; children: list["LayoutNode"]
def draw_panel(panel_cls: type[Panel], context: Context | None = None) -> LayoutNode
def draw_menu(menu_cls: type[Menu], context: Context | None = None) -> LayoutNode
def draw_ui_list(list_cls: type[UIList], data: Struct, propname: str, context: Context | None = None) -> LayoutNode
def placeholder_type(name: str, kind: Literal["MT", "PT", "HT", "UL"]) -> type
class PresetPanel(Panel): ...   # minimal: preset_subdir, preset_operator, preset_add_operator; draw lists nothing
class PresetMenu(Menu): ...
```

#### 12.12 `quartz.depsgraph`

```python
class DirtyChannel(enum.IntFlag): TRANSFORM; GEOMETRY; SHADING; SELECT; HIERARCHY; PARAMETERS; VISIBILITY
def tag(id: ID, channels: DirtyChannel) -> None
def counter(id: ID, channel: DirtyChannel) -> int
def get(scene: Scene, view_layer: ViewLayer) -> Depsgraph
class Depsgraph(Struct):
    mode: str; scene: Scene; view_layer: ViewLayer; scene_eval: Scene; view_layer_eval: ViewLayer
    ids: Iterable[ID]; objects: Iterable[Object]; object_instances: Iterable["DepsgraphObjectInstance"]; updates: list["DepsgraphUpdate"]
    def update(self) -> None
    def id_eval_get(self, id: ID) -> ID
    def id_type_updated(self, id_type: str) -> bool
class DepsgraphUpdate(Struct): id: ID; is_updated_transform: bool; is_updated_geometry: bool; is_updated_shading: bool
class DepsgraphObjectInstance(Struct):
    object: Object; instance_object: Object | None; is_instance: bool; matrix_world: Matrix; parent: Object | None
    persistent_id: tuple[int, ...]; random_id: int; show_self: bool; show_particles: bool; uv: Vector; orco: Vector
```

#### 12.13 `quartz.utils`, `quartz.path`, `quartz.msgbus`

```python
# utils
def register_class(cls: type) -> None
def unregister_class(cls: type) -> None
def register_classes_factory(classes: Sequence[type]) -> tuple[Callable[[], None], Callable[[], None]]
def register_submodule_factory(module_name: str, submodule_names: Sequence[str]) -> tuple[Callable[[], None], Callable[[], None]]
def escape_identifier(string: str) -> str
def unescape_identifier(string: str) -> str
def flip_name(name: str, *, strip_digits: bool = False) -> str
def execfile(filepath: str, *, mod: ModuleType | None = None) -> ModuleType
def script_paths(*, subdir: str | None = None, user_pref: bool = True, check_all: bool = False, use_user: bool = True,
                 use_system_environment: bool = True) -> list[str]
def script_path_user() -> str | None
def user_resource(resource_type: Literal["DATAFILES", "CONFIG", "SCRIPTS", "EXTENSIONS"], *, path: str = "", create: bool = False) -> str
def resource_path(type: Literal["USER", "LOCAL", "SYSTEM"], *, major: int = ..., minor: int = ...) -> str
def system_resource(type: str, *, path: str = "") -> str
def extension_path_user(package: str, *, path: str = "", create: bool = False) -> str
def preset_paths(subdir: str) -> list[str]
def preset_find(name: str, preset_path: str, *, display_name: bool = False, ext: str = ".py") -> str | None
def register_manual_map(manual_hook: Callable) -> None; def unregister_manual_map(manual_hook: Callable) -> None
def register_preset_path(path: str) -> bool; def unregister_preset_path(path: str) -> bool
def register_cli_command(id: str, execute: Callable[[list[str]], int]) -> object; def unregister_cli_command(handle: object) -> None
def register_tool(tool_cls: type, *, after: Any = None, separator: bool = False, group: bool = False) -> None   # data only
def unregister_tool(tool_cls: type) -> None
def time_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> datetime.timedelta
def time_to_frame(time: float | datetime.timedelta, *, fps: float | None = None, fps_base: float | None = None) -> float
def smpte_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> str
def smpte_from_seconds(time: float, *, fps: float | None = None, fps_base: float | None = None) -> str
def is_path_builtin(path: str) -> bool; def is_path_extension(path: str) -> bool
def modules_from_path(path: str, loaded_modules: set[str]) -> list[ModuleType]
def keyconfig_init() -> None; def keyconfig_set(filepath: str, *, report: Callable | None = None) -> None   # no-op
# utils.previews
def new() -> "ImagePreviewCollection"; def remove(pcoll: "ImagePreviewCollection") -> None
class ImagePreviewCollection(dict):
    def load(self, name: str, filepath: str, filetype: Literal["IMAGE", "MOVIE", "BLEND", "FONT"], *, force_reload: bool = False) -> "ImagePreview"
    def new(self, name: str) -> "ImagePreview"; def clear(self) -> None; def close(self) -> None
class ImagePreview(Struct): icon_id: int; image_size: tuple[int, int]; icon_size: tuple[int, int]; is_icon_custom: bool; is_image_custom: bool
# path
def abspath(path: str, *, start: str | None = None, library: Any = None) -> str      # "//" relative to quartz.data.filepath
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
def reduce_dirs(dirs: Sequence[str]) -> list[str]
def resolve_ncase(path: str) -> str
extensions_image: frozenset[str]; extensions_movie: frozenset[str]; extensions_audio: frozenset[str]
# msgbus
def subscribe_rna(*, key: Any, owner: Any, args: tuple, notify: Callable[..., None], options: set[str] = set()) -> None
def publish_rna(*, key: Any) -> None
def clear_by_owner(owner: Any) -> None
def flush() -> int                                                                   # extra
```

#### 12.14 `quartz.runtime`, `quartz.ops`, `quartz.operators`

```python
# runtime/state.py
class AppState:
    blend_data: BlendData; window_manager: WindowManager; preferences: Preferences; undo: UndoStack; context: Context
def current() -> AppState
# runtime/context.py
class Context(Struct):
    # 75 profile members, read-only; implemented: window_manager, window, workspace, screen, blend_data, scene,
    # view_layer, collection, layer_collection, tool_settings, preferences, engine, mode, object, active_object, edit_object,
    # selected_objects, selected_editable_objects, selectable_objects, visible_objects, editable_objects, objects_in_mode,
    # objects_in_mode_unique_data, active_operator; the rest → None
    def temp_override(self, *, window: Window | None = None, area: Any = None, region: Any = None, **keywords: Any) -> ContextManager[None]
    def copy(self) -> dict[str, Any]
    def path_resolve(self, path: str, coerce: bool = True) -> Any
    def evaluated_depsgraph_get(self) -> Depsgraph
# runtime/restrict.py
@contextmanager
def restrict_state(*, enabled: bool = True) -> Iterator[None]
class RestrictedContext: window_manager: WindowManager; preferences: Preferences
class RestrictedData: ...
# runtime/factory.py
def build_default_scene(state: AppState) -> None
def build_empty_scene(state: AppState) -> None
# ops.py
class OpsSubmodule:
    def __getattr__(self, name: str) -> "OpCallable"
    def __dir__(self) -> list[str]
class OpCallable:
    def __call__(self, *args: str | bool, **props: Any) -> set[str]
    def poll(self, *args: str) -> bool
    def idname(self) -> str           # "OBJECT_OT_mode_set"
    def idname_py(self) -> str        # "object.mode_set"
    def get_rna_type(self) -> StructRNA
    bl_options: set[str]
def __getattr__(name: str) -> OpsSubmodule
def __dir__() -> list[str]
def call(idname_py: str, *args: str | bool, invoke_event: Event | None = None, **props: Any) -> set[str]   # extra
def operator_class(idname_py: str) -> type[Operator] | None                                               # extra
# operators/__init__.py
def register_builtin() -> None; def unregister_builtin() -> None
```

#### 12.15 `quartz.undo`, `quartz.io`, `quartz.extras`, `quartz.bmesh`, `quartz.testing`

```python
# undo
class UndoStack:
    enabled: bool; max_steps: int
    def push(self, message: str, *, group: str | None = None) -> None
    def undo(self) -> bool; def redo(self) -> bool
    def can_undo(self) -> bool; def can_redo(self) -> bool
    def history(self) -> list[str]; def clear(self) -> None
# io/snapshot.py
@dataclass(frozen=True)
class Snapshot: label: str; payload: bytes | dict
def take(blend_data: BlendData, *, label: str = "") -> Snapshot
def restore(blend_data: BlendData, snapshot: Snapshot) -> None
# extras.io_utils
class ImportHelper:                    # mixin (does not inherit from Struct)
    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})   # annotation; remaining fields via filename_ext/filter_glob of the subclass
    def invoke(self, context: Context, _event: Event) -> set[str]          # fileselect_add + RUNNING_MODAL
    def check(self, _context: Context) -> bool
class ExportHelper:
    filepath: StringProperty(subtype="FILE_PATH"); check_existing: BoolProperty(default=True, options={"HIDDEN"})
    def invoke(self, context: Context, _event: Event) -> set[str]
    def check(self, _context: Context) -> bool                              # ensures the extension
def orientation_helper(axis_forward: str = "Y", axis_up: str = "Z") -> Callable[[type], type]
def axis_conversion(from_forward: str = "Y", from_up: str = "Z", to_forward: str = "Y", to_up: str = "Z") -> Matrix
def axis_conversion_ensure(operator: Operator, forward_attr: str, up_attr: str) -> bool
def unpack_list(list_of_tuples: Iterable[Sequence]) -> list
def unpack_face_list(list_of_tuples: Iterable[Sequence]) -> list
def path_reference(filepath: str, base_src: str, base_dst: str, mode: str = "AUTO", copy_subdir: str = "",
                   copy_set: set | None = None, library: Any = None) -> str
def path_reference_copy(copy_set: set, report: Callable[[str], None] = print) -> None
path_reference_mode: _PropertyDeferred
def unique_name(key: Any, name: str, name_dict: dict, *, name_max: int = -1, clean_func: Callable | None = None, sep: str = ".") -> str
def poll_file_object_drop(context: Context) -> bool
# extras.object_utils
class AddObjectHelper:                 # mixin: align (enum WORLD/VIEW/CURSOR), location, rotation (+ scale where the profile requires it)
    @classmethod
    def poll(cls, context: Context) -> bool
def object_data_add(context: Context, obdata: ID | None, *, operator: Operator | None = None, name: str | None = None) -> Object
def add_object_align_init(context: Context, operator: Operator | None) -> Matrix
def object_add_grid_scale(context: Context) -> float
def object_add_grid_scale_apply_operator(operator: Operator, context: Context) -> None
def world_to_camera_view(scene: Scene, obj: Object, coord: Sequence[float]) -> Vector
# extras.view3d_utils (Tier 3; math only over RegionView3D-like objects)
def region_2d_to_vector_3d(region, rv3d, coord) -> Vector
def region_2d_to_origin_3d(region, rv3d, coord, *, clamp: float | None = None) -> Vector
def location_3d_to_region_2d(region, rv3d, coord, *, default: Any = None) -> Vector | None
# extras.anim_utils → action_get_channelbag_for_slot / action_ensure_channelbag_for_slot: NotImplementedInQuartz (deferred)
# bmesh (Tier 3)
def new(*, use_operators: bool = True) -> "BMesh"
def from_edit_mesh(mesh: Mesh) -> "BMesh"
def update_edit_mesh(mesh: Mesh, *, loop_triangles: bool = True, destructive: bool = True) -> None
class BMesh:
    verts: "BMVertSeq"; edges: "BMEdgeSeq"; faces: "BMFaceSeq"; loops: "BMLoopSeq"; select_mode: set[str]; is_valid: bool; is_wrapped: bool
    def from_mesh(self, mesh: Mesh, *, face_normals: bool = True, vertex_normals: bool = True, use_shape_key: bool = False, shape_key_index: int = 0) -> None
    def to_mesh(self, mesh: Mesh) -> None
    def free(self) -> None; def clear(self) -> None; def copy(self) -> BMesh
    def normal_update(self) -> None; def calc_loop_triangles(self) -> list[tuple["BMLoop", ...]]
    def select_flush(self, select: bool) -> None; def select_flush_mode(self) -> None
    def transform(self, matrix: Matrix, *, filter: set[str] | None = None) -> None
# bmesh.ops (subset): triangulate(bm, *, faces, quad_method="BEAUTY", ngon_method="BEAUTY") -> dict;
#   create_cube(bm, *, size=1.0, matrix=Matrix.Identity(4), calc_uvs=False) -> dict; create_grid(...); create_circle(...);
#   remove_doubles(bm, *, verts, dist=0.0001) -> dict; recalc_face_normals(bm, *, faces) -> dict;
#   delete(bm, *, geom, context="VERTS") -> dict; translate(bm, *, vec, space=None, verts) -> dict; transform(bm, *, matrix, space=None, verts) -> dict
# bmesh.types: BMVert, BMEdge, BMFace, BMLoop, BMVertSeq, BMEdgeSeq, BMFaceSeq, BMLoopSeq, BMLayerAccess*, BMLayerItem (subset of the dump)
# testing
@contextmanager
def isolated(*, template: Literal["default", "empty"] = "default", compat: bool = False) -> Iterator[AppState]
def run_probe(path: str | Path, *, args: Sequence[str] = ()) -> dict
def compare(golden: dict, actual: dict, *, rel: float = 1e-5, abs_: float = 1e-5, deviations: Mapping[str, str] = {}) -> list["Mismatch"]
def drive_modal(idname_py: str, events: Sequence[Event], **props: Any) -> set[str]
```

**Layer 2 done criteria:** unit tests for `types/runtime/ops/depsgraph/undo/ui` are green; the
factory scene matches `factory_scene` in the dump (names, counts, positions, alphabetical order); the built-in operators schema test is green; the fixture add-on `qz_min_addon` (written in
native `quartz`) registers, runs the operator and unregisters **without the compat layer**.

### Layer 3 — shims, loader, CLI

Internal order: (3a) skeleton of `compat/bpy` + `quartz.compat.activate()`, which already unlocks
the conformance probes; (3b) `mathutils`, `bpy_extras`, `idprop`, `bl_math`, `rna_prop_ui`;
(3c) `quartz.addons` (bl_info, manifest, lifecycle, owner/leaks); (3d) `quartz.cli`;
(3e) sweep + baseline; (3f) `bmesh`, `gpu`/`blf` stubs, minimal `bl_ui`; (3g) docs
`README`, `ARCHITECTURE`, `COMPAT`, `ROADMAP` in Portuguese.

#### 12.16 `quartz.compat` / `compat/*`

Signatures in §8.1. Plus:

```python
@dataclass(frozen=True)
class CompatProfile:
    name: str; blender_version: tuple[int, int, int]; version_file: tuple[int, int, int]; version_string: str
    props_kwargs: Mapping[str, frozenset[str]]; handler_names: tuple[str, ...]; context_members: tuple[str, ...]
    data_collections: tuple[str, ...]; type_names: frozenset[str]; ui_type_names: Mapping[str, str]   # name → "MT"/"PT"/"HT"/"UL"
    uilayout_functions: Mapping[str, tuple[str, ...]]; class_enums: Mapping[str, tuple[str, ...]]
    @classmethod
    def load(cls, name: str) -> CompatProfile
@dataclass
class GhostAccess: symbol: str; first_caller: str; count: int
def strict_factory(native: Callable[..., _PropertyDeferred], allowed: frozenset[str]) -> Callable[..., _PropertyDeferred]
```

Each `compat/<pkg>/*.py` has the form:

```python
"""Compat shim: Blender-style module name over quartz.math."""
# Quartz - author: D1on1n
from quartz.math import Vector, Matrix, Quaternion, Euler, Color   # noqa: F401  (pure re-export)
from quartz.math import geometry, kdtree, bvhtree, noise, interpolate  # noqa: F401
```

#### 12.17 `quartz.addons`

```python
def paths() -> list[str]
def modules(*, module_cache: dict | None = None, refresh: bool = True) -> list[ModuleType]
def modules_refresh(*, module_cache: dict | None = None) -> None
def module_bl_info(mod: ModuleType, *, info_basis: dict | None = None) -> dict
def read_bl_info(path: str | Path) -> dict | None
def check(module_name: str) -> tuple[bool, bool]
def check_extension(module_name: str) -> bool
def enable(module_name: str, *, default_set: bool = False, persistent: bool = False, refresh_handled: bool = False,
           handle_error: Callable[[BaseException], None] | None = None) -> ModuleType | None
def disable(module_name: str, *, default_set: bool = False, refresh_handled: bool = False,
            handle_error: Callable[[BaseException], None] | None = None) -> None
def disable_all() -> None
def reset_all(*, reload_scripts: bool = False) -> None
def extensions_refresh(*, ensure_wheels: bool = False, addon_modules_pending: Sequence[str] | None = None, handle_error: Callable | None = None) -> None
addons_fake_modules: dict[str, ModuleType]
# native
def add_addon_path(path: str | Path) -> None
def add_extension_repo(module: str, directory: str | Path, *, source: Literal["USER", "SYSTEM"] = "USER") -> None
def enable_with_report(module_name: str, *, smoke: bool = False, **kw: Any) -> "AddonReport"
@dataclass
class Manifest:
    schema_version: str; id: str; name: str; tagline: str; version: str; type: Literal["add-on", "theme"]
    maintainer: str; license: list[str]; blender_version_min: str; blender_version_max: str | None = None
    website: str | None = None; copyright: list[str] = field(default_factory=list); permissions: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list); platforms: list[str] = field(default_factory=list)
    wheels: list[str] = field(default_factory=list); build: dict[str, Any] = field(default_factory=dict)
def parse_manifest(path: str | Path, *, strict: bool = True) -> Manifest
def manifest_to_bl_info(manifest: Manifest) -> dict
@dataclass
class RegisteredItem: kind: str; rna_name: str; bl_idname: str
@dataclass
class AddonReport:
    module: str; kind: Literal["legacy", "extension", "native"]; level: Literal["L0", "L1", "L2", "L3", "L4"]
    registered: list[RegisteredItem]; type_props_added: list[str]; handlers_added: list[str]; menus_extended: list[str]
    leaks: list[str]; ghosts: list[GhostAccess]; error: str | None; traceback: str | None; seconds: float
    def to_json(self) -> dict
@dataclass
class SweepEntry: target: str; path: str; kind: str; level: str; error: str | None; seconds: float; ghosts: list[str]
def sweep(targets: Sequence[Path], *, timeout: float = 20.0, templates: Sequence[Path] = (), python: str = sys.executable,
          user_root: Path | None = None) -> list[SweepEntry]
# static_scan (engine migrated from tools/scan_bpy_usage.py)
def scan_paths(paths: Sequence[Path]) -> "UsageReport"
def coverage(report: "UsageReport", *, profile: CompatProfile) -> "CoverageReport"
```

#### 12.18 `quartz.cli`

```python
def main(argv: Sequence[str] | None = None) -> int
def build_parser() -> argparse.ArgumentParser
def cmd_info(ns: argparse.Namespace) -> int
def cmd_scan_addon(ns: argparse.Namespace) -> int
def cmd_enable_addon(ns: argparse.Namespace) -> int
def cmd_run_script(ns: argparse.Namespace) -> int
def cmd_addon_sweep(ns: argparse.Namespace) -> int
```

**Layer 3 done criteria (goals, not promises):**

- Tier 1 of `bpy_usage.md` 100% resolvable in the compat. Coverage weighted by references in the
  real packages ≥ 80% (the easy-core alone gives 75.3%; Tier 1+2 gives 78.5%).
- Conformance probes green, with deviations listed.
- `templates_py`: ≥ 30 of 38 exiting with code 0 (7 use only the core, 34 have ≤ 3 symbols outside it).
- `addons_core`: `io_curve_svg`, `io_anim_bvh`, `ui_translate` at L3. `hydra_storm` at L3 with
  `HydraRenderEngine` as an inert base. The rest are measured and recorded as a baseline.
- The CLI covers the 5 subcommands with tests.

---

## 13. Risks and mitigation

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Inheriting bpy's warts** in the native API (`bl_*`, string enums, stale `matrix_world`, RNA names shadowing methods) | This is the conscious price of this approach. Compensation: hints/`Literal`, stubs, specific exceptions, additive extras, and documentation in `ARCHITECTURE.md` explaining each pitfall. Any eventual change of vocabulary becomes an explicit decision by the author (§15) |
| 2 | **Performance** of RNA in pure Python (descriptor per access, flyweights, per-element loops ~50–100× slower than Blender's C) | numpy paths (`foreach_get/set`, `as_array`, `to_arrays`), built-in operators without per-element loops, `perf/test_perf_smoke.py` with a budget. Optimization (descriptor cache, `__slots__` on flyweights) after measuring |
| 3 | **Precision**: float32 stored × float64 in Python; results slightly different from C mathutils | float32 arithmetic in `quartz.math` objects; tolerance in conformance; documented in `COMPAT.md` |
| 4 | **Scope drift** ("full fidelity" with 2499 operators and 4023 types) | Usage-driven backlog (tiers) + ghost telemetry; "deferred" list (§14) reviewed at each milestone; every new operator needs an add-on/template that uses it |
| 5 | **Global state** (singleton, `sys.modules`, registry) breaking test isolation | `quartz.testing.isolated()`, reversible `compat.deactivate()`, sweep in a subprocess |
| 6 | **Running third-party code** (Blender add-ons): disk writes (`__pycache__` in `Program Files`, preferences, temp), network, clipboard | `-I -B` and `sys.dont_write_bytecode`; sandboxed `user_dir` inside `tmp/`; `use_preferences_save=False`; `online_access=False`; in-memory clipboard; subprocess with timeout; never install wheels |
| 7 | **GPL / proprietary contamination**: temptation to copy logic from `bl_ui`, `bpy_extras`, `_bpy_types`, `addon_utils`, Suzanne data, or error messages | Rule 3 + `tools/check_cleanroom.py` in CI + profile with only names/defaults + tests that compare behavior and not text + `primitive_monkey_add` left out |
| 8 | **Python 3.14** (venv) × 3.13 (Blender): lazy annotations (PEP 649/749), `from __future__ import annotations` in add-ons, modules removed from the stdlib | `annotationlib.get_annotations(..., format=VALUE)` per class in the MRO; string in annotation → evaluate in the module namespace and, if that fails, a clear error identical to Blender's ("property not created"); import probe in the sweep |
| 9 | **Blender version drift** (5.3+ changes contracts) | Per-version profile (`profiles/blender_X_Y.json`), per-version goldens, regenerable dump |
| 10 | **[I] behaviors** that I inferred wrongly (alphabetical order, class `register()`, pointer counts a user, stale `matrix_world`, `evaluated_depsgraph_get` evaluating, unknown attribute → `AttributeError`) | Each one becomes a probe **before** the corresponding implementation; if the golden contradicts it, the golden wins |
| 11 | **Strict RestrictBlend** making add-ons "work less" than expected | Same behavior as Blender; `--lenient` only for diagnostics, and the report says when lenient mode was used |
| 12 | **Snapshot-based undo** O(scene) | Acceptable in headless; incremental snapshot per dirty channel in the ROADMAP |
| 13 | **Multiple-inheritance exceptions** (`QuartzError` + `AttributeError`/`ReferenceError`) | Unit test guarantees `isinstance` and that the classes can be created on 3.14 |

---

## 14. What I would defer (and how it comes in later)

| Deferred | Behavior at the milestone | How it comes in later |
|---|---|---|
| GUI, viewport, renderer, GPU | `gpu`/`blf` stubs; inert `RenderEngine`; `draw_handler_add` stores and does not call | GUI reuses the `*_MT_*`/`*_PT_*` names and the `UILayout` (the recorder becomes the model for the real UI) |
| Animation (Action/slots/channelbag, FCurve, Keyframe, drivers, NLA) | ghost `bpy.data.actions`; `keyframe_insert`/`driver_add` → `NotImplementedInQuartz` | `ANIMATION` stage of the depsgraph; RNA data paths already serve as the key (C4D DescID idea) |
| Armature/Pose/Bones, `mode_set('POSE')` | `POSE` accepted only for ARMATURE objects (none exist) | Edit hook per data type (§5.3) |
| Curves (`bpy.data.curves`), Text/Font, Grease Pencil, Volume, PointCloud | ghosts | `io_curve_svg` is the first post-milestone target (needs `curves`) |
| Nodes (`NodeTree`/`Node`/`NodeSocket`, node-based materials, Geometry Nodes) | inert bases; `node_tree = None` | Copy-on-write transactional core (c4d_model §12) with a `NodeTree` face |
| Vertex groups, shape keys, custom normals, tangents | ghosts / `NotImplementedInQuartz` | point `FLOAT` attributes and dedicated layers |
| Modifiers other than `TRIANGULATE` | names accepted, `NotImplementedInQuartz` | type registry already exists |
| `.quartz` file (save/load), `wm.save_as_mainfile`, real `load_post` | does not exist; `factory_reset` fires the load handlers | zip with JSON + `.npy` over `io.snapshot`, with `q_schema_version` + `upgrade()` per type (C4D's `disklevel`) |
| Libraries/link/overrides, assets (`asset_mark`, catalogs) | `NotImplementedInQuartz` | Blender-style assets + Id/version/update policy (c4d_model §11) |
| Modal with event loop, gizmos, tools, keymaps with effect | modal stored; `drive_modal` for tests | GUI event loop |
| Extension wheels, remote repository, zip installation | "not supported" warning | own extension manager |
| Dynamic `describe()`, `enabled_if` with effect, generators, tags, Fields, MoGraph/`InstanceCloud` (C4D) | metadata accepted and stored in `PropertyRNA`; no new types | come in as **additive types** (`quartz.types.Generator` as `Object.data`, `Object.tags`, `Field.sample`); the compat does not see them; the depsgraph already reserves the stages |
| `mathutils.noise`, `interpolate`, `delaunay_2d_cdt`, ACES color conversions | stubs | on demand |
| `bpy.utils.units`, `previews` with real images | data structures only | on demand |
| `.pyi` stub generator, port codemod (`tools/port_addon.py`) | — | right after the milestone: introspectable RNA makes both cheap |

---

## 15. Open decisions for the author (D1on1n)

1. **`bl_` prefix** in the native API. I propose keeping it (`bl_idname`, `bl_label`…), because switching to
   `qz_` duplicates the entire surface and breaks the "mechanical port". Alternative: accept `qz_*` as an
   alias in the metaclass.
2. **Stale `matrix_world` until evaluation** on the native face as well. I propose yes, for fidelity.
   Alternative: a flag `settings.eager_matrix_world` only for native scripts, at the cost of two
   behaviors.
3. **float32 storage** for everything that bpy stores as float. I propose yes.
4. **Default ghost policy**: `log` (proposed) × `error`.
5. **Error messages** in English with original wording (proposed) × in Portuguese.
6. **Name of the native extensions namespace**: `qz_ext` (proposed).

---

## Appendix A — Mechanical port (original example)

Add-on written for Blender:

```python
"""Tiny example add-on (Blender flavour)."""
# Quartz - author: D1on1n
import bpy
from mathutils import Vector

bl_info = {"name": "Nudge", "author": "D1on1n", "version": (0, 1, 0), "blender": (4, 2, 0), "category": "Object"}

class OBJECT_OT_nudge(bpy.types.Operator):
    bl_idname = "object.nudge"
    bl_label = "Nudge"
    bl_options = {'REGISTER', 'UNDO'}
    amount: bpy.props.FloatProperty(name="Amount", default=0.5, min=0.0, max=10.0)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        context.active_object.location += Vector((0.0, 0.0, self.amount))
        return {'FINISHED'}

def menu(self, context):
    self.layout.operator(OBJECT_OT_nudge.bl_idname)

def register():
    bpy.utils.register_class(OBJECT_OT_nudge)
    bpy.types.VIEW3D_MT_object.append(menu)

def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu)
    bpy.utils.unregister_class(OBJECT_OT_nudge)
```

The native version changes **only** the imports (`import quartz as bpy` is not recommended; the swap is textual):

```python
import quartz
from quartz.math import Vector
# ... bpy.types → quartz.types, bpy.props → quartz.props, bpy.utils → quartz.utils
# the menu line becomes conditional: quartz.types.VIEW3D_MT_object only exists with the compat
# or when Quartz's future GUI defines this menu (same identifier, on purpose).
```

With the compat active, the original file runs unchanged:
`python -m quartz enable-addon tests/fixtures/addons/nudge.py --smoke --json`.

## Appendix B — Format of a conformance probe (original)

```python
"""Conformance probe: ID naming and user counting."""
# Quartz - author: D1on1n
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import bpy
from _probe_runtime import Recorder

rec = Recorder("p_id_naming")
a = bpy.data.meshes.new("QProbe"); b = bpy.data.meshes.new("QProbe")
rec.add("second_name", b.name)                       # golden: "QProbe.001"
b.name = "QProbe"
rec.add("rename_collision", [a.name, b.name])        # golden: ["QProbe", "QProbe.001"]
rec.add("long_name_bytes", len(bpy.data.meshes.new("N" * 300).name.encode()))
rec.expect_exc("remove_twice", lambda: (bpy.data.meshes.remove(a), bpy.data.meshes.remove(a)))
rec.dump()                                           # --out <file> comes after "--" in sys.argv
```

## Appendix C — Traceability: research → decision

| Research finding | Decision |
|---|---|
| `bpy.props` returns `_PropertyDeferred`; annotations in the MRO; old assignment ignored [O] | §4.3 |
| `bpy.props` values outside `id.keys()` in 5.x [O] | §4.5 (two storages) |
| RNA name `MOD_OT_name` in `bpy.types`; `bl_idname` rules; exception types per error [O] | §7.1 |
| `bpy.ops` contract (positionals, `TypeError`, clamp, `RuntimeError`, headless invoke→execute) [O] | §7.2 |
| `mode_set` Tier 1 (184 calls) | §5.3 (mode/edit hook), §7.2 (built-in operator) |
| Context: 75 members, read-only, `temp_override` [O]; 78 members used, `space_data` 168 refs | §7.3 + `None` ghosts |
| Implicit `UILayout` (`prop` 890 refs) | §7.6 recorder + L4 of the sweep |
| 32 references to native menus; `TOPBAR_MT_file_import` in 4 add-ons | §8.4 placeholders per profile |
| `pgettext_*` Tier 1 | §7.5 identity since layer 2 |
| `bmesh` in 1 add-on; `gpu/blf` in 3 | `quartz.bmesh` Tier 3; stubs only in the compat |
| `RestrictBlend`, `enable/disable/check`, manifest [L/O] | §9 |
| ID semantics and SoA mesh semantics [O] | §5.1, §5.3 |
| Undo disabled in background; `(scene, depsgraph)` handlers; timers/msgbus without synchronous firing [O] | §7.4, §7.5 |
| C4D: description, dirty counters, lifecycle phases, schema version | §4.7, §6, §7.5, §14 |
