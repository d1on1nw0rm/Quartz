# Cinema 4D data and plugin model — distillation for Quartz

Project author: **D1on1n** · Research document (path C, native `quartz` API)
Reference: Cinema 4D 2026.3.1 (local installation, read-only)

> **Clean-room hygiene.** This document describes *concepts* and cites *names* of classes,
> constants and files for reference only. No resource excerpt (`.res`, `.str`,
> `.h`) or SDK code was copied. The code examples here are **original**, written
> in the intended Quartz syntax. Cinema 4D is proprietary; nothing from this material enters the
> Quartz code other than ideas.

---

## 0. Method and what was verified

**Sources read** (by listing entries and reading short excerpts via `zipfile`, without extracting):

| Source | What was looked at |
|---|---|
| `sdk.zip` → `frameworks/cinema.framework/source` | `c4d_baselist.h`, `c4d_baseobject.h`, `c4d_basetag.h`, `c4d_objectdata.h`, `c4d_objectplugin.h`, `c4d_tagdata.h`, `c4d_tagplugin.h`, `c4d_fielddata.h`, `c4d_baseeffectordata.h`, `c4d_plugin.h`, `ge_prepass.h` (dirty enums, types, priorities), `DESC_*` attributes |
| `sdk.zip` → `core.framework` | `datadescription*.h`, `datadictionary.h`, `registrybase.h`, `observable.h`, `idandversion.h` |
| `sdk.zip` → `graph/nodes/corenodes/nodespace/neutron.framework` | `graph.h` (graph model, wires, transactions), `nodesystem.h`, `nodetemplate.h`, `node_spaces.h`, `nimbusbase.h`, `corenodes.h`, `neutron_ids.h` |
| `sdk.zip` → `asset.framework` | `assets.h` (URL schemes, metadata, search modes), `idandversion.h` (update policy) |
| `sdk.zip` → `plugins/example.main/source/object` | cache/dirty and registration patterns in generator/deformer examples |
| `resource.zip` → `modules/*/description` | `obaselist`, `obase`, `tbase`, `mbase`, `ocube`, `obasedeform`, `obend`, `obaseeffector`, `obasemogen`, `omograph_cloner`, `ofield`, `flnoise`, `tphong`, `ttexture`, selections/vertex map, `gvbase`, `gvmath`, `opython`; string tables `strings_*/description/*.str` |
| `resource/modules/python/libs/python311/c4d` | typed stubs of the `c4d` and `c4d.plugins` modules (signatures of `Register*Plugin`, `*Data` classes) |

**Verified by running:** only the reading of the zips/stubs with the Python from Quartz's `.venv`
(counts, listings, grep). **Not verified:** no Cinema 4D runtime behavior
was observed (I ran neither `c4dpy` nor the app). Claims about axis conventions
(Y-up, left-handed) and about the UI flow come from general knowledge and are marked as such.

Observed numbers: `resource.zip` has **1067** `.res` description files; `c4d_objects/description`
alone has 458 entries (`.res` + `.h`). The SDK has 2944 entries.

---

## 1. Executive summary

Cinema 4D is built on **a single strong idea**: every scene element is a node in a
generic tree, whose parameters live in a **typed container indexed by ID**, and whose
**shape** (which parameters exist, types, limits, units, groups, UI) is declared
separately in an inheritable **description**. Behavior comes from **plugin
data classes** (`ObjectData`, `TagData`...) attached to the host node, registered with a
**global numeric ID** and **capability flags** (generator, modifier, consumes input...).
Evaluation is **non-destructive**: generators produce virtual *caches*, invalidated by
**dirty counters** per category. On top of that, modern layers (MoGraph with
SoA arrays, fields with batch sampling, a node system with a transactional graph, versioned assets)
reuse the same skeleton.

bpy, for its part, has **RNA** (properties declared per class, addressed by name),
**ID datablocks** in `bpy.data`, an **Object × data** separation (Mesh, Camera...), a **modifier
stack** and the **depsgraph**. The two views are 80% compatible: the C4D "description"
is, essentially, what RNA already is — only richer in UI metadata, inheritance and
dynamic descriptions.

---

## 2. Class tree and host × plugin data separation

**How it is in C4D.** A short, generic hierarchy:
`C4DAtom` (type, classification, `IsInstanceOf`, copy) → `GeListNode` (links
`GetUp/GetDown/GetNext/GetPred`, insertions `InsertUnder/InsertAfter`...) → `BaseList2D`
(name, data container, parameters, bits, markers/UUID, animation tracks, child shaders,
layer) → specializations `BaseObject`, `BaseTag`, `BaseMaterial`, `BaseShader`,
`BaseDocument`, etc. `PointObject` → `PolygonObject` / `SplineObject` carry geometry.

Plugins **do not inherit** from `BaseObject`. They implement a *data* class
(`NodeData` → `ObjectData`, `TagData`, `MaterialData`, `ShaderData`, `FieldData`,
`EffectorData`, `SceneHookData`...) that is allocated and attached to the host node; the host
calls the virtual methods (`Init`, `Message`, `GetDDescription`, `GetVirtualObjects`,
`ModifyObject`, `Execute`, `Read/Write/CopyTo`...). In Python, `BaseList2D.GetNodeData()`
returns this instance.

**Worth taking to Quartz? adapt** — the "generic node + behavior component" separation
keeps the core stable and leaves plugins without access to internals.
*Coexistence with bpy:* bpy already does this with `bpy.types.Operator`/`Panel`/`PropertyGroup`
registered and instantiated by the core. In Quartz, the host type (`quartz.types.Object`,
`Mesh`...) is fixed; custom behavior enters as a registered class
(`quartz.types.Generator`, `quartz.types.Tag`...) that the core instantiates and calls. For the `bpy`
shim, this is invisible.

---

## 3. Descriptions — how object/tag/material/generator declare parameters

**How it is in C4D.** Each type has a **trio of files**:

1. `.h` — enum with the **numeric IDs** of the parameters (and of the enumeration values);
2. `.res` — the **description tree**: a container named by the type's symbol (e.g.: the cube
   type), which **includes** base descriptions (`INCLUDE` of `Obase`, which in turn includes
   `Obaselist`), and organizes parameters into **groups** (tabs/sections) with a **type**
   (`REAL`, `LONG`, `BOOL`, `VECTOR`, `COLOR`, `LINK`, `STRING`, `BUTTON`, `SPLINE`,
   `GRADIENT`, `FIELDLIST`, `IN_EXCLUDE`, ...) and **attributes**;
3. `strings_<language>/description/*.str` — labels translated by ID (12 languages in the installation).

Observed attributes (they are themselves `DESC_*` entries of a per-parameter container):
name/short name, `MIN`/`MAX` (with exclusivity), `MINSLIDER`/`MAXSLIDER` (the "soft" range),
`STEP`, `UNIT` (meter, degree, percentage...), `DEFAULT`, `CYCLE` (enum), `CUSTOMGUI`
(widget), `ANIM` (on/off/mix — animatable or not), `HIDDEN`, `PARENTID` (indentation/
visual dependency: the bevel radius "belongs" to the "bevel" boolean), `ACCEPT`/`REFUSE`
(types accepted in a link), `PARENTGROUP`, layout flags (columns, scale, newline) and
semantic flags (e.g. "not important for defaults", "forbid automatic scaling").

Important mechanisms:

- **Declarative inheritance and override**: a concrete deformer includes the deformer base,
  which declares common **hidden** parameters; the concrete one only **shows** (`SHOW`) those it uses
  and adds its own. The tag base, the material base and the Xpresso node base follow
  the same pattern (`Tbase`, `Mbase`, `GVbase`).
- **Dynamic description**: `GetDDescription` lets the plugin load the static description and
  **add/remove/change** parameters at runtime (e.g. lists that grow).
- **Conditional enabling**: `GetDEnabling` decides whether a parameter is grayed out given the state.
- **Virtual parameters**: `GetDParameter`/`SetDParameter` intercept read/write
  (a computed value or one stored outside the container).
- **Defaults in two places**: `DEFAULT` in the description and/or `Init()` filling the container
  (the SDK examples do the latter).
- **Modern generation**: `core.framework` has `DataDescription` (copy-on-write,
  `DataDictionary` entries with **string** IDs in the `net.maxon...` style), used by the node
  system and assets — the evolution of the same concept, now with textual IDs.

**Worth taking to Quartz? yes (core of the native API)** — a declarative,
inheritable, introspectable description is what enables automatic UI, validation, serialization,
animation and documentation generated from a single source.
*Coexistence with bpy:* instead of `.res` files, the Quartz description is born from
**property annotations** in the bpy style (`FloatProperty(...)`), plus C4D-like
metadata (`group=`, `unit=`, `soft_min/soft_max`, `animatable=`, `parent=`, `enabled_if=`).
bpy exposes the same thing as `bl_rna.properties`; the shim only translates.

Sketch (original, Quartz):

```python
class Cube(quartz.types.Generator):
    bl_idname = "QZ_GEN_CUBE"
    size: quartz.props.FloatVectorProperty(default=(2, 2, 2), min=0.0, unit="LENGTH", group="object")
    segments: quartz.props.IntVectorProperty(default=(1, 1, 1), min=1, soft_max=20, group="object")
    fillet: quartz.props.BoolProperty(default=False, group="object")
    fillet_radius: quartz.props.FloatProperty(default=0.1, min=0.0, unit="LENGTH",
                                              parent="fillet", enabled_if=lambda s: s.fillet)

    @classmethod
    def describe(cls, desc, owner):   # optional: dynamic description
        ...
```

Description inheritance = Python class inheritance (or mixins). Translatable labels come from
translation tables by `bl_idname.prop` (the equivalent of `.str`), without embedding text in the
declaration other than the default English label.

---

## 4. Container / parameter ID model

**How it is in C4D.** `BaseContainer` is a dictionary **integer ID → typed `GeData`**
(types `DA_LONG`, `DA_REAL`, `DA_VECTOR`, `DA_MATRIX`, `DA_STRING`, nested `DA_CONTAINER`,
`DA_ALIASLINK`, custom types above 1,000,000...). Each `BaseList2D` has
an instance container (`GetDataInstance`). The "official" access goes through
`GetParameter/SetParameter(DescID, ...)`, where a **`DescID` is a path of levels**
(`DescLevel(id, dtype, creator)`): `[position, x]` addresses the X subchannel of a vector; levels
also address sub-descriptions and data from other "creators". In Python there is sugar:
`op[c4d.PRIM_CUBE_LEN]` and `op[c4d.ID_BASEOBJECT_REL_POSITION, c4d.VECTOR_X]`, with
**type protection** (overwriting with another type requires deleting the key first).

IDs are **stable forever**: written to files, animation tracks, takes.
Plugin IDs are globally unique integers (obtained from Maxon).

**Worth taking to Quartz? adapt** — the *typed hierarchical address* (DescID) is great
for animation, drivers, overrides and undo; integer IDs are not.
*Coexistence with bpy:* use **string identifiers** (like RNA) and bpy's **data path**
(`'location'`, `'location[0]'`, `'modifiers["Bend"].angle'`) as the equivalent of DescID.
Internally, each datablock keeps a typed `ParamStore` (numpy for vectors/matrices,
Python scalars), with type protection coming from the description. Optional: a stable numeric `uid`
per property for binary formats and for a future "c4d-like" shim — but never
exposed as the primary key.

---

## 5. Hierarchy and tags

**Hierarchy.** The document (`BaseDocument`) has several **list heads** (`GeListHead`):
objects, materials, layers, takes, render data, *scene hooks*. Each `BaseList2D` also
has **branches** (`GetBranchInfo`) — its own sublists: tags, animation tracks,
child shaders, node graphs. In other words: **everything is a tree of trees**, traversable
uniformly. An object is in **a single place** in the tree; grouping is by parent (Null) or by
**layers** (link `ID_LAYER_LINK` on every `BaseList2D`).

**Tags.** Components attached to objects, registered with flags (`TAG_VISIBLE`,
`TAG_MULTIPLE`, `TAG_HIERARCHICAL` — inherited by children, like the material —,
`TAG_EXPRESSION` — runs in the pipeline —, `TAG_MODIFYMATRIX`...). They cover roles that in
Blender are scattered:

| Role | C4D tag (name) | Blender equivalent |
|---|---|---|
| Material + projection + restriction by selection | Texture tag (`Ttexture`, link to `Mbase`, restriction by polygon selection name) | material slots + `material_index` |
| UV | `Tuvw` | `mesh.uv_layers` / corner attribute |
| Named selections (points/edges/polygons) | `Tpointselection`, `Tedgeselection`, `Tpolygonselection` | vertex groups / boolean attributes / face maps |
| Per-vertex weight | `Tvertexmap` (can be driven by **fields**) | vertex group |
| Vertex color, normals | `Tvertexcolor`, `Tnormal`, `Tphong` (angle-based smoothing) | color attributes, custom normals, auto smooth |
| Behavior/expression | Target, Protection, Display, Python tag, Xpresso tag... | constraints, drivers, handlers |

**Worth taking to Quartz? adapt** — tags as **behavior components** are
elegant and extensible; tags as **geometry storage** clash with a numpy
attribute model.
*Coexistence with bpy:* `Object.tags` (ordered collection, bpy-shaped:
`obj.tags.new(type="QZ_TAG_LOOKAT")`) for behavior (expressions, script tags, display,
protection, user components); the `bpy` shim's constraints can be tags internally.
Geometry data **always** stays in `mesh.attributes` (UV = corner `FLOAT2` attribute,
selections = named `BOOLEAN` attributes, vertex map = point `FLOAT`). A "tag view"
over attributes can exist for those coming from C4D, but it is presentation only.

---

## 6. Generators × deformers × effectors (parametric, non-destructive)

**How it is in C4D.** The role of a plugin object is declared by flags at registration:

- `OBJECT_GENERATOR` — `GetVirtualObjects()` builds a virtual hierarchy (the **cache**)
  from the parameters. Primitives (cube, sphere) are generators.
- `OBJECT_GENERATOR | OBJECT_INPUT` — the generator **consumes its children** as input (Extrude,
  Subdivision Surface, Boole, Symmetry, Cloner, the SDK's Atom); the children are "hidden" in the
  result. `GetAndCheckHierarchyClone` is used to obtain clones (converted to polygons)
  of the children and to know whether they changed.
- `OBJECT_ISSPLINE` — spline generator (`GetContour`).
- `OBJECT_MODIFIER` — **deformer**: an object placed as a **child** (or sibling, depending on the
  case) of the target; `ModifyObject()` alters the points of the target's *deform cache*. Deformers have a
  common base (size, limited/box/unlimited mode, strength) and can be restricted.
- `OBJECT_HIERARCHYMODIFIER`, `OBJECT_PARTICLEMODIFIER`, `OBJECT_FIELDOBJECT` — variations.
- **Effectors** (MoGraph) do not touch the mesh: they receive the **MoData arrays** from a MoGraph
  generator (Cloner, Matrix, Fracture, Text...) and modify them (`ModifyPoints`,
  `CalcPointValue`...), with **strength**, min/max, relative/absolute/remap mode, space and
  **fields** as a mask. The generator references the effectors in an **inclusion list**
  (`IN_EXCLUDE` accepting the effector base), in order.

Everything is non-destructive: the original object stays parametric; "make editable" / "current
state to object" is what collapses the cache into real geometry.

**Worth taking to Quartz? yes (generator and effector) / adapt (deformer)**
— parametric generators as first-class objects are the clearest differentiator of C4D
over Blender; effectors over arrays are a perfect fit with numpy.
*Coexistence with bpy:* bpy separates Object and data. In Quartz, a generator is a **data
datablock** (`quartz.data.generators`, type `Generator`) pointed to by `Object.data`, with
`object.type == 'GENERATOR'`; the `bpy` shim shows the object as an evaluable `'MESH'` (
`evaluated_get()` returns a mesh). Deformers enter the **`object.modifiers` stack**
(bpy-shaped); the C4D "child deformer" form becomes **sugar**: a child deformer object is
interpreted, at evaluation, as an implicit modifier on the parent (order = order of the children).
`OBJECT_INPUT` becomes a class flag (`consumes_children = True`).

---

## 7. Cache and dirty flags

**How it is in C4D.**

- Each node has **dirty counters per category** (`DIRTYFLAGS`: `MATRIX`, `DATA`,
  `SELECT`, `CACHE`, `CHILDREN`, `DESCRIPTION`, `VISIBILITY`; and in the document, selection of
  objects/tags/materials). `GetDirty(flags)` returns a **counter** — the consumer stores the
  last value seen and compares; `SetDirty` increments. There are also hierarchical counters
  in the document (`HDIRTY`: animation, object, matrix, hierarchy, tag, material, shader...).
- **Two caches** per object: the generator cache (`GetCache`) and the deformation cache
  (`GetDeformCache`). `GetCacheParent` goes up from a virtual object to the generator that created it.
- Idiomatic generator pattern: "if `CheckCache(hh)` and `IsDirty(DATA)` are false, return the
  old cache; otherwise rebuild". Generators that read **other** objects use **dependency
  lists** (`NewDependenceList` / `CompareDependenceList`) or
  override `CheckDirty`.
- Level of detail (`LOD`) reaches the generator through `HierarchyHelp`.
- The document runs **passes** in an order given by **priority** (`EXECUTIONPRIORITY_INITIAL`
  1000, `ANIMATION` 2000, `EXPRESSION` 3000, `DYNAMICS` 4000, `GENERATOR` 5000, scene nodes
  10000). Tags/objects with `Execute` enter via `AddToExecution` in a `PriorityList`.

**Worth taking to Quartz? yes** — monotonic counters per channel are cheap, allocation-free,
easy to test and explain exactly *what* changed.
*Coexistence with bpy:* the facade remains `context.evaluated_depsgraph_get()`,
`obj.evaluated_get(depsgraph)`, `depsgraph.updates` with `is_updated_geometry` /
`is_updated_transform` — which Quartz **derives** from the counters (`DATA`/`GEOMETRY` →
geometry; `MATRIX` → transform). Execution priorities become named stages of the
evaluator (`INITIAL`, `ANIMATION`, `DRIVERS/EXPRESSIONS`, `DYNAMICS`, `GENERATORS`); dependency
lists become explicit edges of the evaluation graph.

---

## 8. Plugin registration lifecycle

**How it is in C4D (C++).** Each module exports three entry points: `PluginStart` (registers
everything), `PluginMessage` (receives global messages) and `PluginEnd`. Observed lifecycle
messages: system initialization (`C4DPL_INIT_SYS`), version query
(`C4DPL_INIT_VERSION`), "all have started" (`C4DPL_STARTACTIVITY`), menu construction
(`C4DPL_BUILDMENU`), command-line arguments (`C4DPL_COMMANDLINEARGS`), and a
**phased shutdown** (`C4DPL_ENDACTIVITY` — close dialogs, threads, buffers — before
any `PluginEnd`, and then additional phases before/after releasing documents and
registries). There are **initialization priorities** per category (modules, objects, shaders,
modeling, extensions, plugins).

Each `Register*Plugin` receives: a **unique integer ID**, name, **info flags** (the `OBJECT_*`,
`TAG_*`), the data class allocator, the **description name**, icon and **`disklevel`**
(on-disk format version, passed to `Read()` for migration).

**In Python:** `.pyp` files in a plugins folder (with a `res` subfolder containing
descriptions/strings); the module registers on import by calling
`c4d.plugins.RegisterObjectPlugin(id, str, g=Class, description="Oname", info=flags, ...)`
and can define a module-level `PluginMessage(id, data)` function.

**Worth taking to Quartz? adapt** — the phased shutdown and `disklevel` are valuable;
integer IDs and allocators are not.
*Coexistence with bpy:* the add-on contract remains `register()`/`unregister()` +
`bpy.utils.register_class` with a string `bl_idname`. Quartz adds:
(1) **capability flags as class attributes** (`bl_options = {'GENERATOR', 'INPUT'}`);
(2) **schema version per type** (`q_schema_version = 2` + `def upgrade(data, from_version)`)
— C4D's `disklevel`, for file migration;
(3) lifecycle events in `quartz.app.handlers` (`startup_post`, `shutdown_pre`,
`shutdown_post`, in addition to bpy ones such as `load_post`) — the `bpy.app.handlers` shim exposes only
Blender's names. Deterministic registration order (by dependencies declared in the manifest),
in place of numeric priorities.

---

## 9. Shape of the Python API (`c4d`)

**How it is.** A **flat and huge** namespace (the `c4d.__init__` stub is ~2.2 MB): type
constants (`c4d.Ocube`), parameter constants (`c4d.PRIM_CUBE_LEN`), message constants; classes that mirror
C++ 1:1 (`c4d.BaseObject(c4d.Ocube)`), `GetX/SetX` methods in CamelCase, `op[ID]` for
parameters, `doc.InsertObject(op)` + `c4d.EventAdd()` to notify the UI; submodules
`documents`, `plugins` (`*Data` classes to subclass and `Register*`), `gui`, `utils`,
`modules.mograph` etc.; the **`maxon`** package exposes the new API (string IDs, `DataDictionary`,
interfaces), and `mxutils` brings high-level utilities. In addition, C4D allows **user
code as scene data**: Python Generator (`Opython`, code in a multiline `STRING`
parameter), Python Tag, Python Effector, Python Field, Python node in Xpresso.

**Worth taking to Quartz? no (API shape) / adapt (script objects)** — the bpy shape
(properties, snake_case, collections with `new()/remove()`) is more Pythonic and is required by
path A; generators/tags/fields with embedded script, however, are extremely powerful for prototyping.
*Coexistence with bpy:* Quartz will have neither numeric constants nor `GetX/SetX`. Script objects
enter as native types (`ScriptGenerator`, `ScriptTag`, `ScriptField`) whose code only
runs if the file is **trusted** (same model as Blender's "auto-run scripts":
`quartz.app.trusted`), with isolated execution in a controlled namespace.

---

## 10. Fields and MoGraph

**MoData.** The MoGraph generator keeps **parallel arrays (SoA)** per clone: matrix
(`MODATA_MATRIX`), color, size, UVW, flags (visible, etc.), weight, clone index (which child
/ blend), time, alternate index, falloff weight. Cloner distributions: linear,
radial, grid, honeycomb, on object/spline/surface/volume; clone selection modes
(iterate, random, blend, sort). Effectors read/write these arrays in order.

**Fields.** A field is either an object (`FieldObject`, placeable in the scene, with common
remapping) or a **layer** (`FieldLayer`, an operation inside a list). The `FieldList` is a
custom data type: a **stack of layers with blend modes and opacity**,
present as a `FIELDLIST` parameter in effectors, deformers, forces, and in the vertex
map, selection, vertex color and normal tags. The sampling interface is **batched**:
`InitSampling` → `Sample(input, output)` → `FreeSampling`, where the input carries blocks of
**positions**, optional directions and UVW, and the output carries blocks of **value**, **alpha**,
**color**, **direction**, **rotation**, **pivot** and a "disabled" boolean. There is a per-thread
context and a caller stack to avoid cycles.

**Worth bringing to Quartz? yes** — it is probably the most "numpy-native" design in C4D:
SoA + vectorized sampling map directly to `ndarray`.
*Coexistence with bpy:* `quartz.types.Field.sample(positions: (N,3)) -> FieldOutput` with
arrays `value (N,)`, `color (N,3)`, `direction (N,3)`...; `FieldList` as a property
(collection of layers with `blend_mode`, `opacity`). Quartz's MoData is an
`InstanceCloud` (matrices `(N,4,4)` + named attributes), which the `bpy` shim can expose as the
**instances** domain of Geometry Nodes. Geometry Nodes "fields" (lazy
functions evaluated on a domain) and C4D fields (sampled spatial volumes) are
different concepts with the same name — Quartz MUST name the C4D one a
**spatial `Field`** and the GN one a **node field function**, without merging them.

---

## 11. Asset system

**How it works.** An asset is identified by **Id + version** (`IdAndVersion`), has an **asset
type** (file, preset of a data type, category, node template, database...), and is
described by a **lightweight descriptor** with **metadata** (creation, timestamp, size, version
tag, preview URL/preview animation, category, keywords, dependencies). Assets
live in **layered repositories** (a repository has base repositories; a search can
ignore the bases), with search modes (latest version, all, by prefix, including deleted).
References use their own URL scheme (`asset:///...`) and a UI-only readable scheme
(`assetdb:///category/...`). **Asset links** carry an **update policy**
(`NEVER` — pins the version; `EXPLICIT` — asks; `IMPLICIT` — follows the newest). Parameter presets
of any description are assets (`DataDescription` preset storage).
There are also license flags, irrelevant to Quartz.

**Worth bringing to Quartz? adapt** — Id+version, update policy on links, and
layered repositories solve real problems (shared libraries that evolve).
*Coexistence with bpy:* the public face follows Blender: `id.asset_mark()`, `id.asset_data`
(`description`, `tags`, `catalog_id`, `author`), libraries in
`preferences.filepaths.asset_libraries` and catalogs. Quartz adds
`asset_data.version` and `asset_data.update_policy` and allows libraries with a base
(`library.bases`). Blender operator/property presets (`presets/`) and C4D description
presets converge into a single mechanism: "a preset is an asset of type PRESET for a
`bl_idname`".

---

## 12. Node system architecture

Layers observed (from bottom to top):

1. **`graph.framework`** — an **abstract graph model** (`GraphModelInterface`, observable):
   nodes, nestable input/output ports, **connections made up of several "wires"**
   (value, dependency, context, hidden, inhibition and two node-specific markers), each
   wire with a **priority** (`WIRE_MODE` NONE < MIN < NORMAL < MAX) to resolve ambiguities
   in inheritance. Every edit happens in a **transaction** (`BeginTransaction` → `Commit` /
   `Rollback`), with notifications to observers.
2. **`nodes.framework`** — the `NodeSystem`: a **copy-on-write** hierarchy of nodes/ports
   (cheap copies through sharing; writes via `BeginModification`/`EndModification`).
   A node can be an **instance of another node** (inherits ports and children and can override) —
   *derivation*. **`NodeTemplate`** is an asset that **instantiates** a node system given a
   context/arguments (ports can depend on the context). Node/port attributes described
   by `DataDescription`.
3. **`corenodes.framework`** — the **evaluation** level: compilable, groupable core nodes / micro-nodes,
   separate from the editing graph.
4. **`nodespace.framework`** — a **NodeSpace** defines a domain (e.g., the materials of a
   renderer) with its nodes and conversions; **Nimbus** links a classic object
   (`BaseList2D`, e.g., a material) to **one graph per node space** that it owns.
5. **`neutron.framework`** — **Scene Nodes**: procedural geometry/distribution; **capsules**
   expose a node asset as a **classic object** in the object manager (generator,
   deformer, field), integrated by a scene hook.

And the legacy **Xpresso**: `GV*` nodes described by the same `.res` system, with port group and
`DYNAMIC` ports (`INPORT`/`OUTPORT`, multiple, created by default), hosted by an
expression tag.

**Worth bringing to Quartz? adapt** — transactions, the editing × evaluation separation,
node groups as versioned assets and the **capsule** idea are excellent; multiple wires
with priority and full derivation are too much complexity for the current milestone.
*Coexistence with bpy:* the face is `bpy.types.NodeTree` (`nodes`, `links`, `interface`,
the tree type's `bl_idname` = the "node space"). Internally: edits grouped into a
transaction (basis of Quartz's undo), a copy-on-write snapshot so the evaluator can run without
blocking, node groups publishable as versioned assets, and "capsule" = a node group exposed
as `Generator`/modifier/`Field` (Blender already goes halfway with the
Geometry Nodes modifier). Derivation (group instance with overrides) stays in the ROADMAP.

---

## 13. Other notable concepts (short)

| Concept | Worth bringing? | Reason / coexistence |
|---|---|---|
| **Takes** (per-"take" overrides over any parameter) | adapt (future) | Overrides addressed by data path; similar to Blender's library overrides + view layers. |
| **Layers** (layer link on every node; per-layer visibility/lock/render) | adapt | Blender collections cover almost everything; a "layer color/flag" can be a `Collection` property. |
| **BaseLink** (weak reference resolved by marker/UUID, remapped in copies by `AliasTrans`) | yes | Quartz's `PointerProperty` stores the datablock UUID; scene copies remap it. |
| **Messages** (`Message` with types such as description button command, post-set of a parameter) | adapt | `update=` callbacks of bpy props + `on_button(name)` in the description; no message IDs. |
| **Explicit undo** (`AddUndo` before changing) | no | Transaction/snapshot undo is safer in a Python core. |
| **Commands by ID** (`CallCommand(id)`) and `SendModelingCommand` | no | `bpy.ops` with context is the model of path A; modeling commands become pure functions in `quartz.geometry` + thin operators. |

---

## 14. Conflicts between the C4D model and the bpy model

| Topic | Cinema 4D | bpy / Blender | Quartz decision |
|---|---|---|---|
| Parameter identity | integer ID + multilevel `DescID` | string identifier + data path | **String + data path**; optional internal numeric `uid` |
| Parameter declaration | external `.res`/`.h`/`.str`, inheritance via `INCLUDE` | class annotations (`bpy.props`) | **Annotations**, enriched with description metadata; class inheritance |
| Object × data | the object **is** the geometry (`PolygonObject`) or the generator | `Object` + shareable datablock (`Mesh`, `Camera`...) | **Object + data** (required for the shim); generator is a kind of *data* |
| Non-destructive | generators and deformers **are objects** in the hierarchy | modifier stack on the object | Canonical **`modifiers` stack** + generator as data + child deformer as sugar |
| Hierarchy/grouping | single tree + layers | parenting + collections (object in several collections) | **Blender model** (collections), with optional layer flags |
| Components | tags (behavior **and** geometry data) | constraints, vertex groups, attributes, drivers | **Tags for behavior only**; geometry in `attributes` |
| Material | texture tag + selection restriction + per-tag projection | slots + `material_index` + UV | Canonical **slots**; projection as a modifier/node |
| Invalidation | dirty counters per category + per-object caches | depsgraph with update tags | **Internal counters**, bpy depsgraph facade |
| Plugin registration | global integer ID, info flags, `PluginStart/End` | string `bl_idname`, `register()/unregister()` | **bpy**, with flags as attributes and schema version per type |
| Operations | `CallCommand`, `SendModelingCommand`, `GetX/SetX` methods | `bpy.ops` (context, poll, report), properties | **bpy.ops** for UI/scripts; pure numpy functions underneath |
| Cloning/instances | MoData SoA + effectors | Geometry Nodes (instances domain) | **SoA `InstanceCloud`** shared by both worlds |
| "Field" | sampled spatial volume (layer stack) | lazy function in the node graph | **Two concepts with distinct names** |
| Spatial conventions *(general knowledge, not verified in the files)* | Y-up, left-handed, cm, HPB rotation (there is an HPB order in `obase.h`) | Z-up, right-handed, meters, Euler XYZ | **Blender** as native; C4D importers convert |

---

## 15. Recommended hybrid

1. **bpy face, "description" soul.** Every Quartz type (datablock, struct, generator, tag,
   modifier, node) declares properties in the bpy style; the core compiles this into an
   introspectable **`Description`** (groups, units, soft/hard limits, animatable, parent,
   conditional enabling, suggested widget, translation), inheritable by class and **extensible at
   runtime** (`describe()`). The `bpy` shim's RNA is a view of this description.
2. **Parameters in a typed `ParamStore`**, addressed by **data path** (Quartz's
   DescID) — the same key serves animation (fcurves), drivers, overrides, undo and diff.
3. **Object + data as in Blender**, with a new data type **`Generator`** (parametric,
   `evaluate(ctx) -> Mesh | Curve | InstanceCloud`, `consumes_children` flag). Deformers
   are **modifiers**; a child deformer object is translated into an implicit modifier.
4. **Tags = behavior components** (`Object.tags`), executed in named evaluator
   stages; geometry never lives in tags.
5. **Evaluation with per-channel dirty counters** (`DATA`, `MATRIX`, `CHILDREN`, `GEOMETRY`,
   `SELECT`, `DESCRIPTION`) in each datablock, generator cache + per-object deformation
   cache, explicit dependency edges; `Depsgraph`/`evaluated_get` facade identical to bpy's.
6. **Vectorized spatial fields** (batched `Field.sample` over numpy, `FieldList` with
   layers and blending) used by modifiers, effectors, generated attributes and selections.
7. **MoGraph on SoA `InstanceCloud`** (matrices `(N,4,4)` + attributes), effectors in
   order with strength and per-field mask; the same container serves the shim's instances.
8. **bpy-shaped plugins** (`register()/unregister()`, `bl_idname`) with capability flags
   as attributes, **schema version per type** with `upgrade()` for migration, and
   lifecycle handlers in phases (`startup_post`, `shutdown_pre`, `shutdown_post`).
9. **Blender-like assets + Id/version/update policy** and layered libraries;
   presets unified as assets.
10. **Nodes with a `NodeTree` face and a transactional core** (commit/rollback, copy-on-write
    snapshot for evaluation), node groups as versioned assets, and **capsules**
    (group exposed as generator/modifier/field). Derivation and multiple wires are left for
    later.
11. **Script objects** (generator/tag/field with code) only with a trusted file.
12. **Blender spatial conventions** (Z-up, right-handed, meters) as native.

None of this requires path A (the `bpy` shim) to know the C4D concepts: they appear as
*extensions* (`quartz.types.Generator`, `Object.tags`, `Field`, `InstanceCloud`) that a
Blender add-on simply does not use.
