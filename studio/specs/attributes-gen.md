# Generator attributes against Cinema 4D (contract `attributes-gen`)

Written on 20/11/2026 for the night run. It audits every generator registered in `quartz_studio/objects/`
against the Object tab (and the Caps tab where Cinema 4D has one) of the matching Cinema 4D object, and says
exactly what is added, fixed or skipped tonight. Builders implement from this file without asking anyone.

Companion contract: `specs/attributes-mesh.md` (Attribute Manager simplification: no Basic and Coordinates
tabs, rows only, collapsible sections). Where both files touch `widgets/attribute_manager.py`, that file has one
owner, the Attribute Manager builder of `attributes-mesh.md`; section 4 of this file is the list of row kinds that
builder adds on top of its own work.

## 0. Ground rules for every builder

- Code, labels and tests in English. No comments and no docstrings in any code file. The simplest code that works.
- Every px size named here follows `D:\Markdown\DesignPx.md` (1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 72, 96, 128,
  ... and sums or differences such as 10, 14, 20, 28, 40, 56, 80). Every colour is a token of `theme.py`.
- Run Python only as `.\.venv\Scripts\python.exe` from `D:\Apps\Quartz\studio`, offscreen
  (`$env:QT_QPA_PLATFORM='offscreen'; $env:QT_QPA_FONTDIR='C:/Windows/Fonts'`). Never kill a process by name.
  Do not run `build.ps1`. Leave the owner's open `Quartz.exe` alone.
- File compatibility is the first acceptance rule. A `.quartz` file saved before tonight must open and build the
  same mesh. How a file loads today: `fileio/fmt_quartz.py:272` and `fileio/bridge.py:96` call
  `spec.clamp(raw)`, which starts from `spec.defaults()` and keeps only keys the spec knows
  (`objects/registry.py:82-87`); a `choice` value outside `choices` falls back to the default
  (`modeling/registry.py:33-35`). Therefore:
  - every new key has a default that reproduces today's geometry bit for bit;
  - an existing key is never renamed or removed without a `migrate` function (2.3) that maps the old value;
  - an existing `choice` value string is never renamed (`"Grid Array"`, `"Explode Segments and Connect"`,
    `"Catmull-Clark"`, `"Triangles"`, `"Quads"`, `"Middle"` stay as they are); new values are appended or inserted.
- Golden fixtures. Before editing a `gen_*.py` file, its builder records, from the code as it is now, the output of
  the default build of every spec in that file on the probe inputs of its own test file (and on the probes named
  in section 3), as `GOLDEN = {name: (point_count, polygon_count, sha1)}` pasted into its test file, with
  `sha1 = hashlib.sha1((np.round(m.points, 6) + 0.0).tobytes() + repr(list(m.polygons)).encode()
  + repr(list(m.loose_edges)).encode()).hexdigest()`. A test asserts the same triple after the change. The `+ 0.0`
  folds `-0.0` into `0.0`.
- A degenerate parameter set returns `Mesh.empty()` without raising (SPEC.md 7.2). Closed inputs give closed
  2-manifolds where the row says so: every edge shared by exactly two polygons with opposite direction, positive
  signed volume.

## 1. Sources

Fetched tonight from Maxon's help (help.maxon.net, current and 2027 manuals) and the Maxon SDK resource pages:
Extrude, Lathe, Loft, Text (Object and Caps and Bevels tabs), Sweep (SDK `Osweep` parameter list), Cloner (all
modes), Boole, Subdivision Surface, Connect, Symmetry (new generator), Voronoi Fracture (Object and Sources tabs,
R21 page), Remesh, Thicken. The Maxon pages give names, ids and ranges but almost no defaults: every default in the
"C4D default" columns below is from memory of Cinema 4D unless the Quartz value is quoted, and is marked `(m)`.
Array, Fracture, Metaball and Text Spline lists are from memory. Trunk has no Cinema 4D counterpart.

## 2. Registry changes (`objects/registry.py`, builder R, lands first)

Builder R ships these before anything else, in one short change, so every other builder can register params with
them. Nothing else in the registry changes.

### 2.1 `Param` fields

`objects/registry.py:31` `Param(_ToolParam)` gains three fields, all with defaults, after the inherited ones
(`key, label, kind, default, minimum, maximum, step, unit, choices, group, modes`):

| field | type | default | meaning |
|---|---|---|---|
| `show` | `tuple[tuple[str, tuple], ...]` | `()` | the row is shown only when, for every `(key, allowed)` pair, `values[key] in allowed` (values = defaults merged with the object's params). Example: `show=(("direction", ("Auto", "X", "Y", "Z")),)`; a bool: `show=(("separate_bevels", (True,)),)` |
| `axes` | `tuple[str, str, str]` | `("X", "Y", "Z")` | the three tags drawn before the three fields of a `vector` row (`("H", "P", "B")` for rotations) |
| `ref` | `str` | `""` | the key another key's row depends on; used by `font_style` (its family key, `"font"`) |

New method `Param.visible(values: dict) -> bool`: `all(values.get(k) in allowed for k, allowed in self.show)`.

### 2.2 New kinds and their `clamp`

`Param.clamp` (`objects/registry.py:41`) handles these before calling `super().clamp` (the base class would turn
an unknown kind into a float):

| kind | stored value | `clamp(value)` | default used here |
|---|---|---|---|
| `font` | `str` family name | `"" if value is None else str(value)`; an empty string becomes the param default | `"Arial"` |
| `font_style` | `str` style name, `""` = the family's own default face (today's `QFont(family)`) | `"" if value is None else str(value)` | `""` |
| `link` | `str` name of a scene object, `""` = none | `"" if value is None else str(value)` | `""` |
| `curve` | `tuple[tuple[float, float], ...]`, 2 to 32 points, x strictly increasing, first x 0.0, last x 1.0, x and y in [0, 1] | each item must be a pair of finite numbers (else `ValueError`); clamp x and y to [0, 1]; sort by x (stable); drop a point whose x equals the previous x; force the first x to 0.0 and the last x to 1.0; fewer than 2 points raises `ValueError`; more than 32 keeps the first 31 and the last | `((0.0, 1.0), (1.0, 1.0))` |
| `color` | `tuple[float, float, float]` in [0, 1] | 3 finite numbers (else `ValueError`), each clamped to [0, 1] | not used by any generator tonight |

New helper `curve_value(curve, x: float) -> float`: `float(np.interp(x, xs, ys))` over the points of a clamped
curve. A flat curve at 1.0 returns exactly `1.0`.

JSON: `fmt_quartz` writes tuples as lists; `clamp` turns them back into tuples on load, so
`tests/test_fileio_quartz.py:74` (`x.params == y.params`) keeps passing for curves.

### 2.3 `ObjectSpec.migrate`

`ObjectSpec` (`objects/registry.py:52`) gains `migrate: Callable[[dict], dict] | None = None` (after
`description`). `ObjectSpec.clamp(values)` calls `values = self.migrate(dict(values))` first when it is set.
`migrate` only adds new keys derived from old ones and leaves keys it does not know; it must be idempotent. The
two migrations used tonight are in 3.5 (Thicken) and 3.8 and 3.9 (Sweep, Loft).

### 2.4 Link values at build time

The stored value of a `link` param is a name. At build time the scene replaces it (section 6) so that
`p[key]` is a `BuildInput` (the linked object's evaluated mesh, merged with its drawn descendants, in the
generator's local space, exactly like a child input) or `None`. A build function must treat any value that is not
a `BuildInput` (for example `""` when a test calls `spec.build(spec.defaults(), inputs)`) as `None`. New helper
`link_keys(spec) -> tuple[str, ...]`: keys of the spec's params of kind `link`, in order.

### 2.5 Tests (new file `tests/test_objects_registry_kinds.py`, builder R)

- `Param.visible` with no `show`, with one and with two conditions, with a bool condition.
- `axes` default and an `("H", "P", "B")` param.
- `clamp` of `font`, `font_style`, `link` (None, numbers, strings); `curve` (unsorted input sorted, x clamped,
  first and last x forced, duplicate x dropped, list of lists from JSON gives a tuple of tuples, 1 point raises,
  a non-number raises, 40 points gives 32); `color`.
- `curve_value` on a flat curve returns `1.0` exactly; on `((0, 0), (1, 1))` at 0.25 returns 0.25.
- `ObjectSpec.migrate` is applied by `clamp` and not by `defaults`; a spec without it behaves as before.
- Every spec registered today still clamps its own defaults to themselves (`spec.clamp(spec.defaults()) ==
  spec.defaults()` for every spec in `registry.all_specs()`).

## 3. Audit and decisions, generator by generator

Legend for "Quartz today": `key` and label as in the code; "ok" means default and range agree with Cinema 4D (or
Quartz deliberately keeps its own default for file compatibility, said in the row). "Decision": add (exact Param
in the table that follows), fix, or skip with the reason. All new params use `group="Object"` unless the table
says otherwise; `show` is written as `key in (values)`.

### 3.1 Subdivision Surface (`gen_surface.py:590`, `id="subdivision_surface"`, builder S)

| C4D attribute | type | C4D default | range | Quartz today | decision |
|---|---|---|---|---|---|
| Type | choice: Catmull-Clark, Catmull-Clark (N-Gons), OpenSubdiv Catmull-Clark, OpenSubdiv Loop, OpenSubdiv Bilinear | Catmull-Clark (N-Gons) (m) | | `type` "Type", one choice `"Catmull-Clark"` (hidden: a choice with one value is not shown, `attribute_manager.py:716`) | add the choice `"Bilinear"`; the row becomes visible. `"Catmull-Clark"` keeps today's meaning, which subdivides n-gons as true faces (what Cinema 4D calls Catmull-Clark (N-Gons)). Skip OpenSubdiv Loop (needs a triangle scheme, nothing else uses it) |
| Subdivision Viewport | int | 2 | 0..6 | `subdivision_editor` "Subdivision Editor", 2, 0..6 | fix the label to "Subdivision Viewport"; key unchanged |
| Subdivision Renderer | int | 3 | 0..6 | none | skip tonight: Quartz has no renderer yet, so the row would do nothing. When `quartz_studio/render` evaluates objects for a final render, add `Param("subdivision_render", "Subdivision Renderer", "int", 3, 0, 6, 1, group="Object")` and read it when the build receives `p["_quality"] == "render"` |
| Subdivide UVs | choice | Standard | | none | skip: no UVs on generator output |
| Boundary Interpolation | choice: Edge, Edge and Corner | Edge and Corner (m) | | none (today's boundary rule is "Edge": every boundary vertex is smoothed, `gen_surface.py:195-197`) | add `boundary`, default `"Edge"` (today) |
| Triangle Subdivision, Edge Crease, R12 Compatibility | | | | none | skip: no crease data on meshes |
| Linear Pre-Subdivision | int | 0 | 0..6 | none | add `pre_subdivision` |

New and changed params, in this order:

| key | label | kind | default | min | max | step | unit | choices | show |
|---|---|---|---|---|---|---|---|---|---|
| `type` | Type | choice | `"Catmull-Clark"` | | | | | `("Catmull-Clark", "Bilinear")` | |
| `subdivision_editor` | Subdivision Viewport | int | 2 | 0 | 6 | 1 | | | |
| `pre_subdivision` | Linear Pre-Subdivision | int | 0 | 0 | 6 | 1 | | | |
| `boundary` | Boundary Interpolation | choice | `"Edge"` | | | | | `("Edge", "Edge and Corner")` | `type in ("Catmull-Clark",)` |

Construction:
- `_bilinear(points, polys)`: same topology as `_catmull_clark` (one quad per polygon corner, same point order:
  vertices, then edge points, then face points), positions unchanged for vertices, edge midpoints, face centroids.
- `_catmull_clark(points, polys, corners=False)`: with `corners=True`, a boundary vertex that belongs to exactly one
  polygon keeps its position; every other rule unchanged.
- `build_subdivision`: `pre = min(pre_subdivision, 6 - subdivision_editor)` levels of `_bilinear`, then
  `subdivision_editor` levels of `_catmull_clark(..., corners=(boundary == "Edge and Corner"))` for type
  Catmull-Clark, or of `_bilinear` for type Bilinear. Defaults run exactly today's loop.

Tests (`tests/test_objects_gen_surface.py`, which pins `sub.defaults()` at line 145; update that line):
GOLDEN for levels 0 to 3 on the existing cube, prism and open grid probes; Bilinear level 1 of a cube keeps every
point on the cube's faces (bounds unchanged, 24 quads, closed manifold); pre-subdivision 1 plus level 1 on a cube
gives 96 quads and differs from level 2; the combined level is capped at 6 (pre 6 with level 6 equals level 6
alone); "Edge and Corner" on a single quad keeps its 4 corners in place, "Edge" moves them.

### 3.2 Symmetry (`gen_surface.py:596`, `id="symmetry"`, builder S)

Cinema 4D now has two Symmetry objects: the legacy one (Mirror Plane XY/ZY/XZ, Weld Points, Tolerance,
Symmetrical, Delete Polygons on Axis or Clamp Points on Axis, Automatic Flip, Flip) and the new generator (Type
Planar or Radial; per axis Off, + to -, - to +; Radial: Axis, Rotation Offset, Source Slice, Slice Count, Mirror;
Weld Off, Crosses Plane, On; Cut Along Plane; Remove Outside; Tolerance). Quartz follows the legacy one.

| C4D attribute | C4D default | Quartz today | decision |
|---|---|---|---|
| Mirror Plane (legacy) | ZY | `mirror_plane` ZY, choices ZY XY XZ | ok |
| Weld Points | on | `weld_points` True | ok |
| Tolerance | 0.01 cm (m) | `tolerance` 0.01 cm | ok |
| Flip | off | `flip` False | ok |
| Delete Polygons on Axis | on (m) | always on when welding (`gen_surface.py:254-255`) | skip as a row: turning it off would leave a polygon and its mirror on the same plane, a double face |
| Symmetrical, Automatic Flip | off | none | skip: they react to interactive point edits, not to the build |
| Type Planar / Radial (new generator) | Planar | none | add `type` and the radial rows |
| Per-axis Off / + to - / - to + (new) | | none | skip: nest two Symmetry objects for two planes |
| Cut Along Plane, Remove Outside (new) | | none | skip: needs a polygon-by-plane clip that keeps concave n-gons valid |
| Keep Parametric, Show Planes | | none | skip: display only |

New params, after `flip`:

| key | label | kind | default | min | max | step | unit | choices | show |
|---|---|---|---|---|---|---|---|---|---|
| `type` | Type | choice | `"Planar"` | | | | | `("Planar", "Radial")` | (first row: insert it before `mirror_plane`) |
| `mirror_plane` | (unchanged) | | | | | | | | `type in ("Planar",)` |
| `flip` | (unchanged) | | | | | | | | `type in ("Planar",)` |
| `radial_axis` | Axis | choice | `"Y"` | | | | | `("X", "Y", "Z")` | `type in ("Radial",)` |
| `slice_count` | Slice Count | int | 4 | 2 | 64 | 1 | | | `type in ("Radial",)` |
| `rotation_offset` | Rotation Offset | angle | 0.0 | -360.0 | 360.0 | 1.0 | | | `type in ("Radial",)` |
| `radial_mirror` | Mirror | bool | False | | | | | | `type in ("Radial",)` |

Radial construction: `n = slice_count`, step `360 / n` degrees, rotation about the chosen axis by the right-hand
rule. The base direction in the plane is +Y for axis X, +X for axis Y, +X for axis Z. Slice boundary half-planes
contain the axis at angles `rotation_offset + k * step`. Copy `k` (k = 0..n-1) is the source rotated by `k *
step`. With `radial_mirror`, an odd copy is the source reflected across the boundary plane at
`rotation_offset + step` and then rotated by `(k - 1) * step`, with its polygons reversed. The user models one
wedge between the boundaries at `rotation_offset` and `rotation_offset + step`. With `weld_points`, points within
`tolerance` of the axis or of a boundary plane are welded with `_weld_map(points, tolerance, subset)` and polygons
go through `_remap_polys` (degenerate and duplicate rings dropped). Odd `n` with `radial_mirror` is allowed (the
last seam does not match; no error).

Tests: GOLDEN for the default Planar build on the existing probes; Radial Y with 4 slices on a closed wedge
prism spanning 0 to 90 degrees gives 4 times the source polygon count before welding, and after welding a closed
manifold whose bounds are symmetric in X and Z; `radial_mirror` with 2 slices equals the Planar mirror across the
same plane (same point set after rounding); `slice_count` clamps to 2..64; rows of the other type are hidden
(through `Param.visible`).

### 3.3 Connect (`gen_surface.py:604`, `id="connect"`, builder S)

| C4D attribute | C4D default | Quartz today | decision |
|---|---|---|---|
| Objects (link) | empty | children are the inputs | skip: Quartz connects its children |
| Weld | on | `weld` True | ok |
| Tolerance | 1 cm (m) | `tolerance` 0.01 cm | ok; Quartz keeps 0.01 for compatibility |
| Phong Mode, Textures | | none | skip: no Phong angles or textures on meshes |
| Center Axis | off | none | skip: a build cannot move the object's axis |

No change. Tests: GOLDEN only.

### 3.4 Remesh (`gen_surface.py:617`, `id="remesh"`, builder S)

Cinema 4D 2023+ Remesh (ZRemesher or Instant Mesh): Algorithm, Polygon Target Mode, Mesh Density 1..10000 %,
Polygon Count 1..5000000, Keep Outline, Keep Creases, Edge Angle 0..180, Smooth Iterations 0..100, Only
Quadrangles, Density Map, Density Scale 25..400 %, Adaptive Count, Adaptiveness, Detect Hard Edges, Hard Edge
Selection, Symmetric X/Y/Z, Flow Splines, Transfer Attributes, Polygon Type (Quad Dominant, Triangles).

| C4D attribute | Quartz today | decision |
|---|---|---|
| Polygon Type | `mode` "Mode" Triangles / Quads | ok (values kept) |
| Mesh Density | `polygon_density` 100 %, 10..400 | ok (range narrower on purpose: split and collapse cost) |
| Polygon Target Mode, Polygon Count | none | add `target_mode`, `polygon_count` |
| Smooth Iterations | none | add `smooth_iterations` |
| Keep Outline | boundary points already stay (collapse only moves interior points, `gen_surface.py:438-452`) | skip as a row |
| Algorithm, Keep Creases, Edge Angle, Density Map, Adaptive, Hard Edges, Symmetric, Flow Splines, Transfer | none | skip: they belong to ZRemesher; Quartz's edge split and collapse has no field for them |

New params, after `mode`:

| key | label | kind | default | min | max | step | unit | choices | show |
|---|---|---|---|---|---|---|---|---|---|
| `target_mode` | Polygon Target Mode | choice | `"Density"` | | | | | `("Density", "Polygon Count")` | |
| `polygon_density` | (unchanged) | | | | | | | | `target_mode in ("Density",)` |
| `polygon_count` | Polygon Count | int | 1000 | 4 | 200000 | 1 | | | `target_mode in ("Polygon Count",)` |
| `smooth_iterations` | Smooth Iterations | int | 0 | 0 | 100 | 1 | | | |

Construction: with "Polygon Count" the triangle target of each input part is `polygon_count` (Triangles) or
`2 * polygon_count` (Quads), split across parts in proportion to their triangle counts (at least 4 each), instead of
`len(tris) * density`. After split or collapse and before quad pairing, `smooth_iterations` rounds of uniform
Laplacian smoothing move every interior point (all its edges shared by two triangles) by `0.5 * (mean of its
neighbours - point)`; boundary points stay. 0 rounds is today.

Tests: GOLDEN at defaults; Polygon Count 200 on a 6x6 grid cube gives a triangle count within 10 % of 200
(Triangles) and a quad-dominant result near 200 (Quads); 5 smoothing rounds keep boundary points of an open grid
bit for bit and keep a closed input closed.

### 3.5 Thicken (`gen_surface.py:610`, `id="thicken"`, builder S)

Cinema 4D 2024+ Thicken generator: Mode (Basic, Advanced), Thickness 0..inf, Clamp (Advanced), Position
-100..100 %, Subdivision 0..inf, Shell, Start Cap, End Cap, Thickness Map, Polygon Selection, Selection Handling,
Map Handling, Resolve Intersections, Optimize, Perpendicular Boundary, Preserve Corners.

| C4D attribute | Quartz today | decision |
|---|---|---|
| Thickness | `thickness` 10 cm, 0..1e6 | ok |
| Position | `both_sides` bool (False: the shell grows behind the surface; True: centred) | fix: replace by `position`, migrated |
| Subdivision | `subdivision` 1..100 | ok (Quartz counts wall rows from 1) |
| Shell, Start Cap, End Cap | none (all three always built) | add, default on |
| Mode, Clamp, Thickness Map, selections, Resolve Intersections, Optimize, Perpendicular Boundary, Preserve Corners | none | skip: no vertex maps or selection sets on generator inputs; intersections are not resolved anywhere in Quartz |

Params, in this order (`both_sides` is removed):

| key | label | kind | default | min | max | step | unit |
|---|---|---|---|---|---|---|---|
| `thickness` | Thickness | distance | 10.0 | 0.0 | 1e6 | 1.0 | cm |
| `position` | Position | percent | -100.0 | -100.0 | 100.0 | 1.0 | % |
| `subdivision` | Subdivision | int | 1 | 1 | 100 | 1 | |
| `shell` | Shell | bool | True | | | | |
| `start_cap` | Start Cap | bool | True | | | | |
| `end_cap` | End Cap | bool | True | | | | |

`migrate`: when `"both_sides" in values and "position" not in values`, set `position = 0.0 if
values["both_sides"] else -100.0`. Construction: `front = thickness * (1 + position / 100) / 2`, `back = thickness
- front` (so -100 is today's `both_sides=False`, 0 is today's `both_sides=True`); `_thicken_part` keeps the front
layer polygons only with `start_cap`, the back layer only with `end_cap`, the walls only with `shell`. All three off
gives `Mesh.empty()`.

Tests: GOLDEN for `position` -100 and 0 equal to today's `both_sides` False and True (record both before the
change); `spec.clamp({"both_sides": True})["position"] == 0.0`; a file written with `both_sides` reopens with the
same mesh (round trip through `fmt_quartz`); caps and shell toggles on an open grid remove exactly the front, back
or wall polygons; update `tests/test_objects_gen_surface.py:152`, `:312-340` and `:519`.

### 3.6 Extrude (`gen_spline.py:831`, `id="extrude"`, builder P)

| C4D attribute | type | C4D default | range | Quartz today | decision |
|---|---|---|---|---|---|
| Direction | choice: Auto, X, Y, Z, Custom, Absolute | Auto (m) | | none (always the Movement vector) | add `direction`, default `"Custom"` (today); skip Absolute (global axes; generator output is local) |
| Offset | distance | 100 cm (m) | -inf..inf | none | add `offset`, shown when Direction is not Custom |
| Movement | vector | 0, 0, 20 cm (m) | | `movement` (0, 0, 20) | ok; shown only when Direction is Custom |
| Subdivision | int | 1 | 1..4000 | `subdivision` 1..1000 | ok (cap kept) |
| Isoparm Subdivision | int | 10 | 3..4000 | none | skip: no isoparm display |
| Reverse Normals | bool | off | | none | add `flip_normals` |
| Hierarchical | bool | off | | `hierarchical` False | ok |
| Caps tab: Start, End | bool | on, on | | `start_cap`, `end_cap` (group "Caps") | ok |
| Caps tab: Separate Controls, Shape, Size, Subdivision, Tension, Bevel Outside | | off, Round, 0, 1, 100 %, off (m) | Size -inf..inf, Subdivision 1..100 | none | add, through `objects/caps.py` (3.7) |
| Caps tab: Extrusion and Offset of the cap, Spline shape and its curve, Load and Save Preset, Break Phong Rounding | | | | none | skip: extra cap extrusion and preset files are out of scope tonight; no Phong angles |
| Caps tab: Avoid Self Intersections | bool | on | | none | not a row: Quartz always limits the bevel size (3.7) |
| Caps tab: Tessellation | choice: Triangles, Quadrangles, N-Gons, Delaunay, Regular Grid | N-Gons (m) | | none (convex polygons from ear clipping and merging, `gen_spline.py:247-282`) | add `cap_type` with Polygons (today), Triangles, N-Gons |

Params of Extrude, in this order (group "Object" then group "Caps", then group "End Bevel"):

| key | label | kind | default | min | max | step | unit | choices | group | show |
|---|---|---|---|---|---|---|---|---|---|---|
| `direction` | Direction | choice | `"Custom"` | | | | | `("Auto", "X", "Y", "Z", "Custom")` | Object | |
| `offset` | Offset | distance | 100.0 | -1e6 | 1e6 | 1.0 | cm | | Object | `direction in ("Auto", "X", "Y", "Z")` |
| `movement` | Movement | vector | (0.0, 0.0, 20.0) | | | 1.0 | cm | | Object | `direction in ("Custom",)` |
| `subdivision` | Subdivision | int | 1 | 1 | 1000 | 1 | | | Object | |
| `flip_normals` | Reverse Normals | bool | False | | | | | | Object | |
| `hierarchical` | Hierarchical | bool | False | | | | | | Object | |
| `start_cap` | Start Cap | bool | True | | | | | | Caps | |
| `end_cap` | End Cap | bool | True | | | | | | Caps | |
| `separate_bevels` | Separate Controls | bool | False | | | | | | Caps | |
| `bevel_shape` | Shape | choice | `"Round"` | | | | | `("Round", "Step", "Solid")` | Caps | |
| `bevel_size` | Size | distance | 0.0 | 0.0 | 1e6 | 1.0 | cm | | Caps | |
| `bevel_segments` | Subdivision | int | 1 | 1 | 100 | 1 | | | Caps | |
| `bevel_tension` | Tension | percent | 100.0 | 0.0 | 100.0 | 1.0 | % | | Caps | `bevel_shape in ("Round",)` |
| `bevel_outside` | Bevel Outside | bool | False | | | | | | Caps | |
| `cap_type` | Tessellation | choice | `"Polygons"` | | | | | `("Polygons", "Triangles", "N-Gons")` | Caps | |
| `end_bevel_shape` | Shape | choice | `"Round"` | | | | | `("Round", "Step", "Solid")` | End Bevel | `separate_bevels in (True,)` |
| `end_bevel_size` | Size | distance | 0.0 | 0.0 | 1e6 | 1.0 | cm | | End Bevel | `separate_bevels in (True,)` |
| `end_bevel_segments` | Subdivision | int | 1 | 1 | 100 | 1 | | | End Bevel | `separate_bevels in (True,)` |
| `end_bevel_tension` | Tension | percent | 100.0 | 0.0 | 100.0 | 1.0 | % | | End Bevel | `separate_bevels in (True,)` and `end_bevel_shape in ("Round",)` |

The `bevel_*` set applies to both ends, or to the start only when `separate_bevels` is on. `bevel_outside` and
`cap_type` always apply to both ends. The Caps rows are also the caps of Text (3.10); define them once as
`_cap_params()` and `_end_bevel_params()` in `gen_spline.py`.

Construction (in `_extrude_set`, `gen_spline.py:378`, and `build_extrude`, `:449`):
- Movement: Custom uses `movement` (today). X, Y, Z use the unit axis times `offset`. Auto uses the normal of the
  largest closed ring (the `big` Newell vector the code already computes at `:397`, over all sets together),
  signed so that its largest-magnitude component is positive (ties: Z, then Y, then X), times `offset`; with no
  closed ring, +Z times `offset`. A zero-length result gives `Mesh.empty()` (today's rule at `:441`).
- Reverse Normals reverses the side wall polygons only; the caps keep their outward normals (Cinema 4D behaviour;
  a closed result is then not consistently oriented, which is what the user asked for).
- Caps and bevels: see 3.7. With both sizes 0, `cap_type` "Polygons" and Direction Custom, the code must run
  today's arithmetic (`layers = shape + move * (k / sub)`), so GOLDEN holds.
- Open chains never get caps or bevels (today).

### 3.7 Bevel engine (`objects/caps.py`, new, builder R after 2) and how Extrude and Text use it (builder P)

`objects/caps.py` is pure numpy (no Qt, no scene import), not auto-imported (its name has no `gen_` prefix),
imported by `gen_spline.py`. Public API, exactly:

- `BEVEL_SHAPES = ("Round", "Step", "Solid")`
- `bevel_profile(shape: str, size: float, segments: int, tension: float) -> list[tuple[float, float]]`: the
  `(inset, rise)` pairs from the wall end `(0.0, 0.0)` to the cap `(size, size)` (Solid: `(0.0, size)`), in cm.
  `tension` is a fraction 0..1. With `t = j / segments`, `a = t * pi / 2`, j = 0..segments:
  - Round: `inset = size * ((1 - tension) * t + tension * (1 - cos a))`, `rise = size * ((1 - tension) * t +
    tension * sin a)`. Tension 0 is a straight chamfer, 1 a quarter circle.
  - Step: `(0, 0)`, then for j = 1..segments the two pairs `(size * (j - 1) / segments, size * j / segments)` and
    `(size * j / segments, size * j / segments)`.
  - Solid: `inset = 0`, `rise = size * t`.
  - `size <= 0` returns `[(0.0, 0.0)]`.
- `offset_rings(rings: list[np.ndarray], distance: float) -> list[np.ndarray]`: each ring is an `(n, 2)` array
  already oriented so that its material lies on its left (outer rings counter-clockwise, holes clockwise; the order
  `_extrude_set` already enforces at `gen_spline.py:407-410`). Every vertex moves to its left by `distance` along the
  mitre `m = (n1 + n2) / (1 + n1 . n2)` of the left normals of its two edges; when `1 + n1 . n2 < 0.5` the mitre
  is scaled down to length 2 (the corner is clipped instead of spiking). A negative distance moves outward.
- `safe_distance(rings, distance: float) -> float`: the largest value of `d, d/2, d/4, ...` (at most 6 halvings,
  else 0.0), with `d = min(|distance|, 0.5 * w)` and `w` the smallest distance from any ring vertex to any edge
  of any ring that does not touch that vertex, such that `offset_rings(rings, sign * value)` keeps every ring's
  signed area sign and an area above `1e-9`, and has no two crossing segments (all rings together, brute-force
  numpy segment test). Returns the value with the sign of `distance`.

Use in `_extrude_set` for closed rings when `caps_ok` (builder P):
1. Effective sizes `s0` (start) and `s1` (end): the requested size if that cap is on, else 0; each passed through
   `safe_distance` on the oriented flat rings (`flat` at `gen_spline.py:405`); if `s0 + s1 > L` (L = movement
   length along the cap normal, `abs(normal . move)`), both are scaled by `L / (s0 + s1)` and the wall gets no
   layers of its own.
2. Profiles: `bevel_profile` of each end. With `bevel_outside`, every inset becomes `inset - size` (the wall is
   pushed out by `size`, the cap keeps the outline).
3. Layers per ring, from the start cap to the end cap: start profile reversed (cap first) at axial positions
   `s0 - rise`, then the wall layers from `s0` to `L - s1` in `subdivision` steps, then the end profile at `L - s1
   + rise`. Each layer is the flat ring offset by its inset (`offset_rings`), lifted back to 3D with the same `u, v`
   basis and moved along the movement vector. Duplicate neighbouring layers (same
   inset and axial) are emitted once.
   Precisely: a layer point is `shape_point + dx * u + dy * v + move * (axial / L)`, where `(dx, dy)` is the
   offset flat point minus the flat point (zero for inset 0). A layer with inset 0 at `axial = L * k / sub` is
   therefore exactly today's `shape + move * (k / sub)`, and a ring that is not quite planar keeps its shape.
4. Skin all layers with `_skin` (one quad strip per pair of layers); caps on the first and last layers with
   `_cap(..., cap_type)`. The holes use the same layers, so a letter with a counter gets a bevelled hole.
5. `cap_type`: `_cap(points, outer, holes, normal, cap_type="Polygons")` gains the argument. "Polygons" is today
   (ear clip plus `_convex_merge`); "Triangles" skips `_convex_merge`; "N-Gons" returns one polygon `tuple(outer)`
   (reversed if its Newell normal points against `normal`) when there are no holes, else falls back to "Polygons".
   Lathe, Sweep and Loft pass their own `cap_type` too (3.8 to 3.10).

Edge cases: a bevel larger than half a letter's stroke is limited by `safe_distance` (never a self-intersecting
cap); `safe_distance` runs once on all the rings of one shape set (every outer ring and its holes together) and
every ring of the set uses that one result, so an outer ring and its hole never get different bevels; Step with 1 segment is one flat ledge and one vertical riser; Solid adds wall rings and leaves the cap
size unchanged.

Tests (`tests/test_objects_caps.py`, new, builder R): profiles for each shape at 1 and 3 segments (exact values);
Round with tension 0 is linear; `offset_rings` of a CCW square by 1 gives the square shrunk by 1 on each side, of
a CW hole grows the hole's material side; `safe_distance` of a 10 x 2 rectangle asked for 5 returns at most 1; a
star asked for a huge distance returns a value whose offset has no crossing.
Tests in `tests/test_objects_gen_spline.py` (builder P): GOLDEN for every default; Extrude of a 100 cm square
with Round size 5, 3 segments, both caps: closed manifold, positive volume, bounds equal to the unbevelled
extrusion (the bevel eats into the outline and the depth, it adds nothing outside), polygon count
`4 * (1 + 2 * 3) + caps`; Bevel Outside: the cap outline equals the square and the bounds grow by 5 on each side in X and Y;
separate controls with only an end bevel leaves the start cap identical to the unbevelled one; a bevel bigger than
the shape is limited and the result stays a closed manifold; "Triangles" caps are all triangles; "N-Gons" cap of a
square without holes is one quad, of a ring with a hole falls back to Polygons; Direction X with offset 30 moves
every point by at most 30 in X only; Auto on a circle in the XY plane extrudes along +Z; Reverse Normals flips
exactly the wall polygons.

### 3.8 Lathe (`gen_spline.py:842`, `id="lathe"`, builder P)

| C4D attribute | C4D default | range | Quartz today | decision |
|---|---|---|---|---|
| Angle | 360 | -inf..inf deg | `angle` 360, -360..360 | fix the range to -36000..36000 (more than one turn with Movement makes a spiral) |
| Subdivision | 24 (m) | 3..4000 | `subdivision` 32, 3..1000 | ok (Quartz keeps 32) |
| Isoparm Subdivision | 10 | 3..4000 | none | skip: display only |
| Movement | 0 | | `movement` 0 | ok |
| Scaling | 100 % | 0..inf | `scale` "Scale" 100 %, 0..10000 | fix the label to "Scaling" |
| Reverse Normals | off | | none | add `flip_normals` (walls only) |
| Caps tab: Start, End | on | | always on for a closed profile that does not wrap (`gen_spline.py:506-508`) | add `start_cap`, `end_cap` (group "Caps") |
| Caps tab: bevels | | | none | skip: a bevel on a lathe cap needs the inset in the rotating frame; second phase reuses `caps.py` |
| Caps tab: Tessellation | | | none | add `cap_type` (group "Caps") |

New params after `scale`: `flip_normals` (Reverse Normals, bool, False, group Object), `start_cap` (Start Cap,
bool, True, group Caps), `end_cap` (End Cap, bool, True, group Caps), `cap_type` (Tessellation, choice,
`"Polygons"`, choices `("Polygons", "Triangles", "N-Gons")`, group Caps). Tests: GOLDEN; angle 720 with movement
100 gives a two-turn spiral whose Y extent is 100 plus the profile height; caps toggles remove exactly one cap each;
Reverse Normals flips the wall polygons only.

### 3.9 Sweep (`gen_spline.py:853`, `id="sweep"`, builder P)

Sweep parameters from the Maxon SDK (`Osweep`): Isoparm Subdivision, End Scale, End Rotation, Start Growth, End
Growth, Parallel Movement, Constant Cross Section, Banking, Keep Segments, Use Rail Direction, 2-Rail, Use Rail
Scale, Reverse Normals, Stick UVs, Scale (curve), Rotation (curve), Rotation from, Rotation to; plus the Caps tab.

| C4D attribute | C4D default | Quartz today | decision |
|---|---|---|---|
| End Scale | 100 % | `end_scale` 100 %, 0..10000 | ok |
| End Rotation | 0 | `end_rotation` 0, -36000..36000 | ok |
| Start Growth, End Growth | 0 %, 100 % | `start_growth`, `end_growth` | ok |
| Parallel Movement | off | none | add `parallel_movement` |
| Constant Cross Section | on | none (today the profile is not stretched at bends) | add `constant_cross_section`, default False (today) |
| Banking | on | none (rotation-minimising frames, no banking) | skip: banking from curvature flips on straight runs and needs a rule Quartz does not have; the frames stay as today |
| Keep Segments, 2-Rail, Stick UVs, Isoparm | | none | skip: no UVs or isoparms; 2-Rail needs a second rail the hierarchy has no slot for |
| Use Rail Direction, Use Rail Scale | on, on | a third spline child is ignored | add both, default True: a third spline child becomes the rail |
| Reverse Normals | off | none | add `flip_normals` (walls only) |
| Details: Scale curve | flat | none | add `scale_curve` (kind `curve`, group "Details") |
| Details: Rotation curve, Rotation from, Rotation to | | none | skip: End Rotation covers the linear case; one curve row tonight |
| Caps tab: Start, End | on | `caps` bool, one switch for both | fix: `start_cap` and `end_cap`, migrated from `caps` |
| Caps tab: bevels | | none | skip: needs the bevel along a curved frame; second phase |
| Caps tab: Tessellation | | none | add `cap_type` |

Params, in this order (`caps` is removed):

| key | label | kind | default | min | max | step | unit | choices | group |
|---|---|---|---|---|---|---|---|---|---|
| `end_scale` | End Scale | percent | 100.0 | 0.0 | 10000.0 | 1.0 | % | | Object |
| `end_rotation` | End Rotation | angle | 0.0 | -36000.0 | 36000.0 | 1.0 | | | Object |
| `start_growth` | Start Growth | percent | 0.0 | 0.0 | 100.0 | 1.0 | % | | Object |
| `end_growth` | End Growth | percent | 100.0 | 0.0 | 100.0 | 1.0 | % | | Object |
| `parallel_movement` | Parallel Movement | bool | False | | | | | | Object |
| `constant_cross_section` | Constant Cross Section | bool | False | | | | | | Object |
| `use_rail_direction` | Use Rail Direction | bool | True | | | | | | Object |
| `use_rail_scale` | Use Rail Scale | bool | True | | | | | | Object |
| `flip_normals` | Reverse Normals | bool | False | | | | | | Object |
| `scale_curve` | Scale | curve | ((0.0, 1.0), (1.0, 1.0)) | | | | | | Details |
| `start_cap` | Start Cap | bool | True | | | | | | Caps |
| `end_cap` | End Cap | bool | True | | | | | | Caps |
| `cap_type` | Tessellation | choice | `"Polygons"` | | | | | `("Polygons", "Triangles", "N-Gons")` | Caps |

`migrate`: when `"caps" in values` and neither `start_cap` nor `end_cap` is in values, both become
`bool(values["caps"])`.

Construction (in `build_sweep`, `gen_spline.py:582`):
- Scale at sample `i`: `sc = (1 + (end_scale - 1) * s) * curve_value(scale_curve, s)`, `s = S[i]` (0 at the start of
  the grown window, 1 at its end). The flat default multiplies by exactly 1.0.
- Parallel Movement: every sample uses the first frame (`T[0]`, `N[0]`, `B[0]`); the profile slides without
  turning.
- Constant Cross Section: at an interior sample (or every sample when the path wraps) with incoming and outgoing
  directions `d0`, `d1`, the profile offset `r` (the `sc * (x N + y B)` part) is stretched along `w`, the unit
  component of `d1 - d0` perpendicular to `T[i]`, by `k = 1 / sqrt((1 + d0 . d1) / 2)`, capped at 2:
  `r' = r + (k - 1) * (r . w) * w`. Ends and straight runs (`|d1 - d0| < 1e-9`) are unchanged.
- Rail: when `inputs[2]` exists and is a spline, its first chain is the rail. The rail point for sample `i` is the
  point at arc fraction `g0 + S[i] * (g1 - g0)` of the rail's own length (g0, g1 the growth window). Use Rail
  Direction: `N[i]` becomes the unit projection of `rail_i - Q[i]` perpendicular to `T[i]` (kept from the frame
  when that projection is shorter than 1e-9), `B[i] = T[i] x N[i]`. Use Rail Scale: `sc` is multiplied by
  `|rail_i - Q[i]| / |rail_0 - Q[0]|` (skipped when the first distance is below 1e-9). With fewer than three
  spline children nothing changes.
- Compatibility note: a Sweep saved with three or more spline children changes (its third child used to be
  ignored and is now the rail). Every other saved Sweep builds the same mesh.
- Reverse Normals: wall polygons reversed, caps unchanged. `orient_volume=True` then leaves the mesh as is because it
  is no longer consistently oriented.
- Caps: `start_cap` and `end_cap` replace `p["caps"]` at `:640`.

Tests: GOLDEN (with the old `caps` True and False through `migrate`); `spec.clamp({"caps": False})` gives both caps
False; a scale curve `((0, 1), (0.5, 0.5), (1, 1))` makes the middle ring half the size of the end rings; Parallel
Movement on an L-shaped path keeps every ring parallel to the first; Constant Cross Section on a 90 degree corner
makes the corner ring about 1.414 times wider along the bend; a straight rail at twice the profile distance doubles
the end scale with Use Rail Scale and turns the profile toward the rail with Use Rail Direction; existing sweep
tests at `:377-467` and `:678-697` keep passing (update the `caps` keys at `:134`, `:387`).

### 3.10 Loft (`gen_spline.py:868`, `id="loft"`, builder P)

| C4D attribute | C4D default | range | Quartz today | decision |
|---|---|---|---|---|
| Subdivision U | 30 | 2..4000 | `subdivision_u` "Mesh Subdivision U" 30, 3..1000 | fix the label to "Subdivision U" |
| Subdivision V | 10 | 2..4000 | `subdivision_v` "Mesh Subdivision V" 10, 1..500 | fix the label to "Subdivision V" |
| Isoparm Subdivision U | 10 | | none | skip: display only |
| Organic Form | off | | none | skip: needs the sections as control points of a NURBS surface |
| Per Segment | off | | none (today Subdivision V is per pair of sections, which is Per Segment on) | add `per_segment`, default True (today) |
| Loop | off | | `loop` False | ok |
| Linear Interpolation | off | | none (Catmull-Rom between sections) | add `linear_interpolation` |
| Adapt UV | on | | none | skip: no UVs |
| Reverse Normals | off | | none | add `flip_normals` (walls only) |
| Caps tab: Start, End | on | | `caps` one switch | fix: `start_cap`, `end_cap`, migrated from `caps` (same `migrate` as Sweep) |
| Caps tab: bevels | | | none | skip: sections differ, needs the bevel on a moving outline |
| Caps tab: Tessellation | | | none | add `cap_type` |

Params, in this order: `subdivision_u`, `subdivision_v`, `per_segment` (Per Segment, bool, True),
`loop`, `linear_interpolation` (Linear Interpolation, bool, False), `flip_normals` (Reverse Normals, bool, False),
then group Caps: `start_cap` (True), `end_cap` (True), `cap_type` (`"Polygons"`, choices as Extrude).

Construction: Linear Interpolation uses `(1 - t) * p1 + t * p2` instead of `_catmull`. Per Segment off: the
`subdivision_v` rows are spread over all section pairs in proportion to the mean distance between corresponding
points of each pair (at least 1 row per pair, rounding by largest remainder so the total is exactly
`max(subdivision_v, pairs)`). Tests: GOLDEN; three sections with Linear Interpolation put every middle layer
exactly on the straight line between its sections; Per Segment off with V 10 over a short and a long gap puts more
rows in the long gap and 10 rows in total; caps toggles; update `:137` and `:500`.

### 3.11 Text and Text Spline (`gen_spline.py:880-887`, `id="text"` and `"text_spline"`, builder P)

| C4D attribute | C4D default | Quartz today | decision |
|---|---|---|---|
| Depth (Text only) | 20 cm | `depth` 20 cm, min 0 | ok |
| Subdivision (Text only) | 1 | none (always 1) | add `subdivision` |
| Text | "Text" | `text` "Text" (kind `text`, one line edit; `\n` splits lines) | ok |
| Font: family and style | Arial, Regular | `font` "Font" kind `text` "Arial" | fix: `font` becomes kind `font` (same key, same stored string), add `font_style` |
| Align | Left (Left, Middle, Right) | `align` Left, Middle, Right | ok |
| Height | 200 cm | `height` 200, min 0 | ok |
| Horizontal Spacing, Vertical Spacing | 0, 0 | `horizontal_spacing`, `vertical_spacing` | ok |
| Kerning (per letter) | | none | skip: needs a per-letter editing mode in the viewport |
| Separate Letters (Text Spline) | off | none | skip: Quartz has no multi-object output from one object |
| Interpolation (spline intermediate points) | Adaptive, 5 deg (m) | none (Qt flattens the glyph curves, `gen_spline.py:777`, `fine = 4`) | add `interpolation` and `curve_points` |
| Shader Indexing | | none | skip: no shaders on generator output |
| Caps tab (Text only) | Start, End on; Round, size 0 | always both caps (`build_text` `:817`) | add the full Extrude Caps group (`_cap_params()`, `_end_bevel_params()` of 3.6), so Text has start and end caps on or off, bevel shape, size, segments, tension, Bevel Outside and Tessellation |

`_text_params()` becomes, in this order: `text`, `font` (Font, kind `font`, `"Arial"`), `font_style` (Style, kind
`font_style`, `""`, `ref="font"`), `align`, `height`, `horizontal_spacing`, `vertical_spacing`, `interpolation`
(Interpolation, choice, `"Automatic"`, choices `("Automatic", "Uniform")`), `curve_points` (Points, int, 8, 1, 64,
step 1, `show=(("interpolation", ("Uniform",)),)`). Text adds `depth`, `subdivision` (Subdivision, int, 1, 1, 1000),
then the Caps group of Extrude.

Construction of `text_chains` (`gen_spline.py:763`):
- Font: `family = str(p["font"]) or "Arial"`; `style = str(p.get("font_style", ""))`; when `style` is not empty and
  `style in QFontDatabase.styles(family)`, `font = QFontDatabase.font(family, style, 12)`, else `font =
  QFont(family)` (today's call, so the default is unchanged). Then `setPixelSize`, letter spacing as today. A family
  that is not installed is passed to Qt as is (Qt substitutes); a style that the family does not have falls back to
  the family default, so changing the family never needs to rewrite `font_style`.
- Interpolation "Automatic" is today's `toSubpathPolygons(matrix)`. "Uniform" walks the elements of
  `matrix.map(path)`: `MoveTo` starts a ring, `LineTo` adds its point, a `CurveTo` with its two `CurveToData`
  elements is a cubic Bezier from the current point, sampled at `t = k / curve_points`, k = 1..curve_points. Then
  the same division by `fine`, shift and `_clean(..., True)` as today.
- Text build: `_extrude_chains([...], (0, 0, depth), subdivision, start_cap, end_cap, bevels..., cap_type)` with the
  caps engine of 3.7 (closed letters, both caps share one `safe_distance` per letter set).

Tests: GOLDEN for Text and Text Spline defaults; `font_style` "Bold" of Arial gives a wider outline than "" (more
area); a style the family lacks builds the same mesh as ""; Uniform with 1 point has only straight chords and fewer
points than Automatic, with 16 points more; Text with a Round bevel of 2 cm, 2 segments is a closed manifold with
the letter counters still open (the hole of "o" stays a hole); start cap off leaves the front open; `subdivision` 3
adds two wall rings; update `:139-141`.

### 3.12 Cloner (`gen_clone.py:421`, `id="cloner"`, builder C)

Cinema 4D Cloner, Object tab: Mode (Object, Linear, Radial, Grid Array, Honeycomb Array), Clones (Iterate,
Random, Blend, Sort), Reset Coordinates (older name Fix Clone), Fix Texture, Instance Mode, Viewport Mode, Seed; per
mode below; and the Transform tab (Position, Scale, Rotation of every clone, Color, Weight, Time).

| C4D attribute | C4D default | Quartz today | decision |
|---|---|---|---|
| Mode | Linear | `mode` Linear, Radial, Grid Array | add `"Object"` and `"Honeycomb Array"` (values appended, see the choices row) |
| Clones | Iterate | `clones` Iterate, Random, Blend, Sort | ok |
| Seed | 1234567 | `seed` 1234567 | ok |
| Reset Coordinates | on | none (a clone keeps its child's offset from the cloner, `gen_clone.py:53-60`) | add `reset_coordinates`, default False (today) |
| Fix Texture, Instance Mode, Viewport Mode | | none | skip: no textures, instances or viewport proxies |
| Object mode: Object (link), Align Clone, Up Vector, Distribution (Vertex, Edge, Polygon Center, Surface, Volume, Axis), Count and Seed (Surface), Selection, Enable Scaling | | none | add Object, Align Clone, Distribution (Vertex, Edge, Polygon Center, Surface), Count, Seed; skip Volume and Axis (no inside test on arbitrary links tonight), Up Vector, Selection (no selection sets) and Enable Scaling (no per-point scale on arbitrary meshes); spline targets: only their points (Vertex) and edges |
| Linear: Count | 3 | `linear_count` 3 | ok |
| Linear: Offset | 0 | none | add `linear_offset` |
| Linear: Mode (Per Step, End Point) | Per Step | none (Per Step) | add `linear_mode` |
| Linear: Amount | 100 % | none | add `linear_amount` |
| Linear: Position, Scale, Rotation | 0, 50, 0; 100 %; 0 | `linear_position`, `linear_scale`, `linear_rotation` | ok; `linear_rotation` gets `axes=("H", "P", "B")` |
| Linear: Step Mode, Step Size | Single Value, 100 % | none | skip: Amount and the per-step values cover them |
| Linear: Step Rotation (H, P, B) | 0 | none | add `step_rotation` |
| Radial: Count, Radius, Plane, Align, Start Angle, End Angle | 5 (m), 50 cm (m), XY (m), on, 0, 360 | `radial_*` (plane default XZ) | ok (Quartz keeps XZ) |
| Radial: Offset | 0 | none | add `radial_offset` |
| Radial: Offset Variation, Offset Seed | 0 | none | skip: random jitter, low value tonight |
| Grid Array: Count, Size | 3, 3, 3; 200 cm | `grid_count` (3, 1, 3), `grid_size` 200 | ok (Quartz keeps 3, 1, 3) |
| Grid Array: Mode (Per Step, End Point) | End Point | none (End Point) | add `grid_mode` |
| Grid Array: Form (Cube, Sphere, Cylinder, Object), Fill | Cube, 100 % | none | add `grid_form` (Cube, Sphere, Cylinder) and `grid_fill`; skip Object form |
| Honeycomb Array: Orientation, Offset Direction, Offset, Width Count, Height Count, Mode, Width Size, Height Size, Form | Z, Height, 50 %, 5, 5, Per Step, 50 cm, 50 cm, Square (m) | none | add all except Form (Square only) and the variation rows |
| Transform tab: Position, Scale, Rotation of each clone | 0; 100 %; 0 | none | add group "Transform" |
| Transform tab: Color, Weight, Time, Effectors tab | | none | skip: no MoGraph colour, weights, animation or effectors |

Params, in this order:

| key | label | kind | default | min | max | step | unit | choices | group | axes | show |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `mode` | Mode | choice | `"Linear"` | | | | | `("Object", "Linear", "Radial", "Grid Array", "Honeycomb Array")` | Object | | |
| `clones` | Clones | choice | `"Iterate"` | | | | | (unchanged) | Object | | |
| `seed` | Seed | int | 1234567 | 0 | 2147483647 | 1 | | | Object | | `clones in ("Random",)` |
| `reset_coordinates` | Reset Coordinates | bool | False | | | | | | Object | | |
| `object_link` | Object | link | `""` | | | | | | Object | | `mode in ("Object",)` |
| `object_distribution` | Distribution | choice | `"Vertex"` | | | | | `("Vertex", "Edge", "Polygon Center", "Surface")` | Object | | `mode in ("Object",)` |
| `object_count` | Count | int | 20 | 1 | 2000 | 1 | | | Object | | `mode in ("Object",)` and `object_distribution in ("Surface",)` |
| `object_seed` | Seed | int | 1234567 | 0 | 2147483647 | 1 | | | Object | | `mode in ("Object",)` and `object_distribution in ("Surface",)` |
| `object_align` | Align Clone | bool | True | | | | | | Object | | `mode in ("Object",)` |
| `linear_count` | Count | int | 3 | 1 | 2000 | 1 | | | Linear | | (rule in `PARAM_APPLIES` today, see 3.12.1) |
| `linear_offset` | Offset | int | 0 | 0 | 2000 | 1 | | | Linear | | `mode in ("Linear",)` |
| `linear_mode` | Mode | choice | `"Per Step"` | | | | | `("Per Step", "End Point")` | Linear | | `mode in ("Linear",)` |
| `linear_amount` | Amount | percent | 100.0 | -10000.0 | 10000.0 | 1.0 | % | | Linear | | `mode in ("Linear",)` |
| `linear_position` | Position | vector | (0.0, 50.0, 0.0) | | | 1.0 | cm | | Linear | | |
| `linear_scale` | Scale | vector | (100.0, 100.0, 100.0) | 1.0 | 10000.0 | 1.0 | % | | Linear | | |
| `linear_rotation` | Rotation | vector | (0.0, 0.0, 0.0) | | | 1.0 | deg | | Linear | ("H", "P", "B") | |
| `step_rotation` | Step Rotation | vector | (0.0, 0.0, 0.0) | | | 1.0 | deg | | Linear | ("H", "P", "B") | `mode in ("Linear",)` |
| `radial_count` .. `radial_align` | (unchanged) | | | | | | | | Radial | | |
| `radial_offset` | Offset | angle | 0.0 | -36000.0 | 36000.0 | 1.0 | | | Radial | | `mode in ("Radial",)` |
| `grid_count`, `grid_size` | (unchanged) | | | | | | | | Grid Array | | |
| `grid_mode` | Mode | choice | `"End Point"` | | | | | `("End Point", "Per Step")` | Grid Array | | `mode in ("Grid Array",)` |
| `grid_form` | Form | choice | `"Cube"` | | | | | `("Cube", "Sphere", "Cylinder")` | Grid Array | | `mode in ("Grid Array",)` |
| `grid_fill` | Fill | percent | 100.0 | 0.0 | 100.0 | 1.0 | % | | Grid Array | | `mode in ("Grid Array",)` |
| `honey_orientation` | Orientation | choice | `"XY"` | | | | | `("XY", "ZY", "XZ")` | Honeycomb Array | | `mode in ("Honeycomb Array",)` |
| `honey_offset_direction` | Offset Direction | choice | `"Height"` | | | | | `("Width", "Height")` | Honeycomb Array | | same |
| `honey_offset` | Offset | percent | 50.0 | 0.0 | 100.0 | 1.0 | % | | Honeycomb Array | | same |
| `honey_width_count` | Width Count | int | 5 | 1 | 2000 | 1 | | | Honeycomb Array | | same |
| `honey_height_count` | Height Count | int | 5 | 1 | 2000 | 1 | | | Honeycomb Array | | same |
| `honey_mode` | Mode | choice | `"Per Step"` | | | | | `("Per Step", "End Point")` | Honeycomb Array | | same |
| `honey_width_size` | Width Size | distance | 50.0 | 0.0 | 1e6 | 1.0 | cm | | Honeycomb Array | | same |
| `honey_height_size` | Height Size | distance | 50.0 | 0.0 | 1e6 | 1.0 | cm | | Honeycomb Array | | same |
| `clone_position` | Position | vector | (0.0, 0.0, 0.0) | | | 1.0 | cm | | Transform | | |
| `clone_scale` | Scale | vector | (100.0, 100.0, 100.0) | 0.0 | 10000.0 | 1.0 | % | | Transform | | |
| `clone_rotation` | Rotation | vector | (0.0, 0.0, 0.0) | | | 1.0 | deg | | Transform | ("H", "P", "B") | |

The existing label "Rotation (H, P, B)" of `linear_rotation`, "Count (X, Y, Z)" and "Size (X, Y, Z)" become
"Rotation", "Count", "Size": the axis tags now say H P B or X Y Z.

#### 3.12.1 Show conditions of the Cloner

`widgets/attribute_manager.py:88-95` holds the Cloner's mode rules in `PARAM_APPLIES` today. They stay valid as
they are (the old keys still belong to the same modes). New keys use `Param.show`. The Attribute Manager applies
both (3.12 rows marked "(rule in PARAM_APPLIES today)" keep their rule; nothing is duplicated).

#### 3.12.2 Construction

All modes produce the same list of `(rot, scl, trans)` steps as `_cloner_steps` (`gen_clone.py:76`), capped at
`MAX_CLONES`, and then the same Clones assignment (Iterate, Random, Sort, Blend).

- Placement (`_placed`, `:53`): with the Transform group, a clone point is
  `q = ((p - pivot) * clone_scale / 100) @ Rc.T + clone_position`, `Rc = rotation_matrix((P, H, B))` of
  `clone_rotation` (stored H, P, B, the same mapping as `linear_rotation` at `:83-85`); then
  `result = pivot + (q * scl) @ rot.T + trans`, or without `+ pivot` when `reset_coordinates` is on (the child's own
  offset from the cloner is dropped). Defaults give today's formula exactly. Blend (`_add_blend`) uses the same
  placement.
- Linear: index `m = i + linear_offset`; `a = linear_amount / 100`. Per Step: position step `pos * a`, rotation
  step `rot * a`, scale step `scl ** a`. End Point: the values are totals reached at the last clone, so with
  `n > 1` the steps are `pos * a / (n - 1)`, `rot * a / (n - 1)`, `scl ** (a / (n - 1))`; with `n == 1` all zero.
  Position of clone m: `P(m) = sum over k = 0..m-1 of rotation_matrix(step_rotation * k mapped to (P, H, B)) @
  pos_step`; orientation `rotation_matrix(step_rotation * m) @ rotation_matrix(rot_step * m)`; scale `scl_step ** m`.
  With the defaults this is `pos * i`, `rot * i`, `scl ** i` (today).
- Radial: every angle gets `+ radial_offset` before the position and the alignment are computed.
- Grid Array: End Point is today (`linspace(-size/2, size/2, n)`); Per Step uses `(k - (n - 1) / 2) * size` on each
  axis. Form: normalised coordinates `x' = x / (half extent)` per axis (an axis with one clone or zero extent gives
  0); Cube keeps all (`r = max |x'|`), Sphere `r = sqrt(x'^2 + y'^2 + z'^2)`, Cylinder (axis Y)
  `r = sqrt(x'^2 + z'^2)`; a clone is kept when `r <= 1 + 1e-9` and `r >= 1 - grid_fill / 100 - 1e-9`. Cube at fill
  100 keeps every clone (today).
- Honeycomb Array: `w, h` counts; cell sizes `ws, hs` (End Point: `size / (count - 1)` when count > 1); for row `r`
  in 0..h-1 and column `c` in 0..w-1, `u = c * ws` plus `honey_offset / 100 * ws` when the direction is Width and
  `r` is odd, `v = r * hs` plus `honey_offset / 100 * hs` when the direction is Height and `c` is odd; centred by
  subtracting `((w - 1) * ws / 2, (h - 1) * hs / 2)`; plane XY gives `(u, v, 0)`, ZY `(0, v, u)`, XZ `(u, 0, v)`.
  Rotation identity, scale one.
- Object: `target = p["object_link"]` (a `BuildInput` or `None`, 2.4). No target, or a target without points, gives
  `Mesh.empty()` and no error. Vertex: every target point, normal = normalised sum of the Newell normals of its
  polygons (none for a point without polygons). Edge: every unique edge (polygon edges and loose edges, sorted by
  `(min, max)`), at its midpoint, normal = normalised sum of its polygons' normals. Polygon Center: every polygon's
  centroid and Newell normal. Surface: `object_count` points, uniformly by area over the triangles of the target's
  polygons (`modeling.meshkit.triangulate_polygon` per polygon), from `np.random.default_rng(object_seed)`: one
  `choice` of triangles weighted by area, then `sqrt`-corrected barycentric coordinates; normal = the triangle's.
  With `object_align` and a normal, the clone's rotation has +Z along the normal (Cinema 4D aligns the clone's Z
  axis), X = `unit(cross(+Y, n))` (or `cross(+Z, n)` when `|n . Y| > 0.99`), Y = `cross(Z, X)`; otherwise identity.
  The steps keep the target's order and are capped at `MAX_CLONES`.

Tests (`tests/test_objects_gen_clone.py`; update the choices pin at `:169`): GOLDEN for every old mode at defaults;
reset coordinates on a child placed at (100, 0, 0) puts the first clone at the cloner origin; Linear offset 2
starts at the third position; End Point with count 5 and position (0, 100, 0) puts the last clone at Y 100; amount
50 halves every step; step rotation (0, 0, 90) H turns a row of 4 into the corners of a square; radial offset 90
rotates the ring; grid Per Step with size 10 and count 3 spans 20; Sphere form on 5 x 5 x 5 drops the corners; fill
0 keeps only the shell (r = 1) on a cube grid; honeycomb 3 x 2 with Height offset 50 % shifts odd columns by half a
cell; Object mode with a cube target: Vertex gives 8 clones, Polygon Center 6 with +Z along each face normal, Edge
12, Surface 20 (seeded, repeatable, all on the cube's faces); no link gives an empty mesh without error; clone
transform position (0, 10, 0) moves every clone by 10 in its own frame.

### 3.13 Array (`gen_clone.py:446`, `id="array"`, builder C)

| C4D attribute | C4D default | Quartz today | decision |
|---|---|---|---|
| Radius | 250 cm | `radius` 250 | ok |
| Copies | 7 | `copies` 7, 1..500 | ok |
| Amplitude | 0 | `amplitude` 0 | ok |
| Frequency (wave speed over time) | 0 | none | skip: needs the animation time; Quartz has no timeline in builds |
| Array Frequency (waves around the ring) | 0 | `frequency` "Frequency" (it is the Array Frequency: `gen_clone.py:159`) | fix the label to "Array Frequency"; key unchanged |
| Render Instances | off | none | skip: no renderer |

Tests: GOLDEN only, plus the label.

### 3.14 Fracture (`gen_clone.py:455`, `id="fracture"`, builder C)

Cinema 4D (MoGraph Fracture): Mode (Straight, Explode Segments, Explode Segments and Connect), Fix Clone, Instance
Mode, Viewport Mode, Transform and Effectors tabs.

| C4D attribute | Quartz today | decision |
|---|---|---|
| Mode | `mode` with the same three values | ok |
| Fix Clone, Instance Mode, Viewport Mode, Effectors | none | skip: no instances or effectors |
| (Quartz only) Offset | `offset` 0 | keep: it stands in for an effector pushing the pieces out |

No change. Tests: GOLDEN only.

### 3.15 Metaball (`gen_clone.py:462`, `id="metaball"`, builder C)

| C4D attribute | C4D default | Quartz today | decision |
|---|---|---|---|
| Hull Value | 100 % | `hull_value` 100, 10..200 | ok |
| Editor Subdivision | 40 cm (m) | `editor_subdivision` 20, 2..1000 | ok (Quartz keeps 20) |
| Render Subdivision | 5 cm (m) | none | skip: no renderer |
| Exponential Falloff | off | none | add `exponential_falloff` |
| Accurate Normals | off | none | skip: the viewport computes normals; nothing to switch |

New param `exponential_falloff` (Exponential Falloff, bool, False). Construction: `_field` adds
`exp(-4 * d2 / reach^2)` per ball instead of `max(0, 1 - d2 / reach^2) ** 3`, and the iso base becomes `exp(-1)`
instead of `FALLOFF_AT_RADIUS`, so a lone sphere still lands on its radius. Tests: GOLDEN; a lone sphere with the
exponential falloff stays within one cell of its radius and is a closed manifold; two balls merge at a larger gap
than with the polynomial falloff.

### 3.16 Boole (`gen_boole.py:816`, `id="boole"`, builder V)

| C4D attribute | C4D default | Quartz today | decision |
|---|---|---|---|
| Boolean Type | A subtract B | `boolean_type` with the same four values | ok |
| High Quality | on | `high_quality` True | ok |
| Create Single Object | off | none | skip: Quartz always outputs one welded mesh (`_to_mesh` welds at 1e-5 of the scale), so off and on look the same |
| Hide New Edges | off | `hide_new_edges` False | ok |
| Create Phong Breaks at Intersections | off | none | skip: no Phong angles |
| Select Intersections | off | none | skip: no selection sets on generator output |
| Optimize Points | 0.01 cm (m), with Create Single Object | none | skip with Create Single Object |

No change. Tests: GOLDEN only.

### 3.17 Voronoi Fracture (`gen_boole.py:831`, `id="voronoi_fracture"`, builder V)

Cinema 4D: Object tab (MoGraph Selection, MoGraph Weightmap, Colorize Fragments, Create N-Gon Surfaces, Offset
Fragments, Invert, Hull Only, Thickness, Hollow Object, Optimize and Close Holes, Scale Cells X/Y/Z, Save Result to
File, Autoupdate); Sources tab (Show All Used Points, Viewport Amount, Sources list, Add Distribution Source, Add
Shader Source); a Distribution Source has Distribution Type (Uniform, Normal, Inverse Normal, Exponential), Point
Amount 2..200000 (20), Seed 0..2147483647 (1234567), Inside (on), Standard Deviation (Normal).

| C4D attribute | Quartz today | decision |
|---|---|---|
| Point Amount | `point_amount` 20, 1..500 | ok (cap kept: one boolean per point) |
| Seed | `seed` 12345 | ok (Quartz keeps 12345) |
| Distribution Type | uniform in the bounding box (`gen_boole.py:744`) | add `distribution` (Uniform, Normal) and `std_deviation`; skip Inverse Normal and Exponential |
| Inside | none (seeds may fall outside the object; such cells give nothing) | add `inside_only`, default False (today) |
| Offset Fragments | `offset_fragments` 0 | ok |
| Hull Only | none (inner faces always built and sealed) | add `hull_only` |
| Scale Cells X, Y, Z | none | add `scale_cells` |
| Create N-Gon Surfaces | inner faces are already merged per cell plane (`_to_mesh` mode "source") | skip as a row |
| Invert, MoGraph Selection and Weightmap, Colorize, Thickness, Hollow Object, Optimize and Close Holes, Save Result, Autoupdate, shader sources, several sources | none | skip: no MoGraph selections, colours or shell offsets of fragments tonight |
| (Quartz only) Sort Result | `sort_result` False | keep |

New params after `seed`, in this order:

| key | label | kind | default | min | max | step | unit | choices | show |
|---|---|---|---|---|---|---|---|---|---|
| `distribution` | Distribution Type | choice | `"Uniform"` | | | | | `("Uniform", "Normal")` | |
| `std_deviation` | Standard Deviation | float | 0.2 | 0.01 | 1.0 | 0.01 | | | `distribution in ("Normal",)` |
| `inside_only` | Inside | bool | False | | | | | | |
| `hull_only` | Hull Only | bool | False | | | | | | (after `offset_fragments`) |
| `scale_cells` | Scale Cells | vector | (1.0, 1.0, 1.0) | 0.01 | 100.0 | 0.1 | | | (after `hull_only`) |

Construction: `fracture_mesh(mesh, amount, seed, offset=0.0, *, distribution="Uniform", std_deviation=0.2,
inside_only=False, hull_only=False, scale=(1.0, 1.0, 1.0))`, so the existing positional calls in tests
(`test_objects_gen_boole.py:382`, `:456`, `:484`) keep working.
- Scale Cells: fracture the mesh with points divided by `scale` (seeds drawn in that space's bounding box) and
  multiply the fragments' points by `scale` afterwards. Division and multiplication by 1.0 are exact, so the
  default is today's result.
- Uniform keeps today's draw `lo + rng.random((amount, 3)) * (hi - lo)` exactly. Normal: `rng.normal(centre,
  std_deviation * (hi - lo), (amount, 3))` clipped to `[lo, hi]`.
- Inside: draw batches of `amount` with the chosen distribution from the same generator and keep the seeds inside
  the mesh (ray parity along +X against the triangles of `triangulate_polygon`, a hit exactly on an edge counts
  once by the half-open rule), until `amount` seeds or 32 batches; fewer seeds are fine.
- Hull Only: skip `_seal` and drop every fragment polygon whose centroid lies within `tol` of one of that cell's
  planes with a normal parallel within 1e-6 (the inner faces); the fragments are then open shells of the original
  surface.

Tests (`tests/test_objects_gen_boole.py`; update the defaults pin at `:192`): GOLDEN on the existing torus and
sphere probes; Normal with deviation 0.05 puts the seeds near the centre (all fragments' centroids within 0.3 of
the half extent for most cells); Inside on a torus never yields a seed in the hole; Hull Only: the union of the
fragments has the same area as the input (within 1e-6 relative) and no polygon on a cell plane; Scale Cells (4, 1,
1) makes fragments elongated in X (mean X extent over mean Y extent above 2); each non-Hull-Only fragment is still a
closed manifold.

### 3.18 Trunk (`gen_trunk.py`, `id="trunk"`, SPEC.md 10.6)

No Cinema 4D counterpart (the nearest is a Sweep with a circle along each branch, which Trunk replaces). Its
params are fixed by SPEC.md 10.6 and pinned by `tests/test_trunk_generator.py:27`, `:134-142`. No change tonight;
`gen_trunk.py` has no owner in this contract.

## 4. Row kinds for the Attribute Manager (builder AM of `attributes-mesh.md`)

`ParamEditor` (`widgets/attribute_manager.py:206`) builds one editor per `Param` by `kind`; today `bool`, `choice`,
`int`, `vector`, `text` and a float spin for the rest. Add these, using theme tokens only and the row height
`theme.ROW_H` (24 px). All combos use `_Combo` (`:165`: wheel only when focused). New method
`ParamEditor.set_context(scene, obj)` stores the scene and the object; `AttributeManager._load_params` (`:701`) calls
it before `set_value` on every editor. `param_applies` (`:708`) also returns `False` when
`not param.visible({**spec.defaults(), **obj.params})`, in addition to the `PARAM_APPLIES` rules.

| kind | editor | value shown | emits `edited(key, value)` |
|---|---|---|---|
| `font` | `_Combo`, items `QFontDatabase.families()` without private families (`QFontDatabase.isPrivateFamily`), sorted case-insensitively, loaded once per process and cached; a stored family that is not installed is inserted at the top as `"<name> (missing)"` with the name as item data | the stored family | on `currentIndexChanged`: the item data (family) |
| `font_style` | `_Combo`; items `QFontDatabase.styles(family)` where `family = obj.params.get(param.ref, default of that param)`, refilled in `set_context` when the family changed and the popup is not open; the stored `""` selects the first style without emitting; a stored style the family lacks also shows the first style | the stored style or the first one | the chosen style name |
| `link` | `_Combo`; first item `"None"` (data `""`), then every scene object in `scene.objects` order except `obj`, its ancestors and its descendants, by name, refilled in `set_context` unless the popup is open; a stored name not found is inserted after "None" as `"<name> (missing)"` | the stored name | the item data (name, or `""`) |
| `curve` | `CurveEditor(QWidget)`: height 64 px, full row width (the label column stays), background `theme.SURFACE_FIELD`, radius `theme.CONTROL_RADIUS`, 1 px border `theme.HAIRLINE`; grid lines at x 0.25, 0.5, 0.75 and y 0.5 in `theme.GRID_MINOR` 1 px; the curve as a polyline in `theme.ACCENT` 2 px, antialiased; each point a 6 px square in `theme.POINT_FILL` with a 1 px `theme.POINT_BORDER`, the dragged one in `theme.SELECT_FRONT`; 4 px inner margin. Mouse: press within 8 px of a point picks it; press elsewhere inserts a point at the cursor (up to 32); drag moves the picked point (first and last points move only in y; x stays between its neighbours); double-click on an inner point deletes it | the stored tuple | on every drag move and on insert and delete, the full clamped tuple (continuous drags merge into one undo step through `Scene._record("param:...")`) |
| `color` | not used by generators tonight; if `attributes-mesh.md` defines it, that definition wins. Otherwise a 48 x 20 px swatch button (radius `theme.CONTROL_RADIUS`, 1 px `theme.HAIRLINE`) that opens `QColorDialog.getColor` | the colour | the chosen colour as 3 floats |
| `vector` (changed) | as today, but the three tags are `param.axes` instead of `"XYZ"` (`:249`) | | as today |

`is_busy` (`:295`) counts a combo with an open popup and a curve editor during a drag. The curve editor's right
click opens the row's parameter menu like every other row (`_hook_row_menu`, `:661`).

Tests (in the AM builder's test file, with specs registered by the test like `ALL_ID` at
`tests/test_attribute_manager.py:61`): a `font` row lists Arial and emits the family; a missing family shows
"(missing)"; a `font_style` row follows the family (Arial lists Bold; switching the family to one without Bold shows
its first style and emits nothing); a `link` row lists other objects but not self, parent or child, and emits a
name; a `curve` row inserts, drags and deletes points and the stored value stays clamped; `vector` rows show H P B
tags when `axes` says so; a row with `show` hides and reappears when its condition changes; group sections with no
visible row are hidden (today's rule at `:730-731`).

## 5. What each builder must not touch

- No builder edits `scene.py`, `app.py`, `main_window.py`, `widgets/menu_bar.py`, `widgets/menus_data.py`,
  `widgets/object_palette.py`, `widgets/viewport.py`, `theme.py`, `icons.py`, `modeling/*`, `fileio/*` or the new
  packages (`materials`, `tags`, `uv`, `sculpt`, `rig`, `anim`, `scripting`, `render`, `ext`): other fleets own them
  tonight. No new icon, menu entry or object id is introduced by this contract, so `icons.py`, `menus_data.py` and
  the palettes need nothing.
- `SPEC.md` and `README.md` are updated only in the integration step.

## 6. Integration step (after all builders, one person)

1. `scene.py` link resolution (2.4): in `Scene._build` (`:877`), for each key of `registry.link_keys(spec)`, find
   the first object in `self.objects` whose name equals the stored value, skip it when it is the generator itself,
   one of its ancestors or one of its descendants, and pass `self._make_input(self._flatten(target, kids))`
   transformed into the generator's local space (multiply by `inverse(generator.world_matrix()) @
   target.parent_matrix()`), else `None`. In `evaluate` (`:891`) and `_signature` (`:845`), a generator's
   signature also holds `(id, kind, world matrix bytes, _mesh_sig)` of each linked object, so moving or editing the
   target rebuilds the cloner. Generators with links are built after the others in the same `evaluate` pass (a
   second loop), so a target that is itself a generator is fresh; a link to an object that itself has links uses
   that object's mesh from the previous evaluation.
2. `Scene.rename_object` (`:1131`): every `link` param of every object that holds the old name gets the new name in
   the same undo step.
3. `tests/test_interface_defects.py` (Cloner visibility at `:315` and `:359`), `tests/test_objects_ui.py`,
   `tests/test_fileio_quartz.py` (round trip of a Sweep with a curve, a Thicken saved with `both_sides`, a Cloner in
   Object mode with a link), `tests/test_objects_core.py` if it pins `Param` fields.
4. `SPEC.md` section 7.1 (new kinds, `show`, `axes`, `ref`, `migrate`, link values at build time) and a new "As
   built" note; `README.md` generator list.
5. Full test run; an offscreen walk through the Attribute Manager of every generator at 1920 x 1010 checking that
   every row shown changes the mesh (the owner's rule: only controls that do something).

## 7. File ownership

| builder | phase | files (sole owner) |
|---|---|---|
| R: registry and bevel engine | first `objects/registry.py` and its test, then `objects/caps.py` | `objects/registry.py`, `tests/test_objects_registry_kinds.py` (new), `objects/caps.py` (new), `tests/test_objects_caps.py` (new) |
| S: surface generators | after R's registry change (geometry work can start at once) | `objects/gen_surface.py`, `tests/test_objects_gen_surface.py` |
| P: spline generators and text | after R's registry change; uses the `caps.py` API of 3.7 (may stub it until R delivers) | `objects/gen_spline.py`, `tests/test_objects_gen_spline.py` |
| C: cloners | after R's registry change | `objects/gen_clone.py`, `tests/test_objects_gen_clone.py` |
| V: boole and Voronoi | after R's registry change | `objects/gen_boole.py`, `tests/test_objects_gen_boole.py` |
| AM: row kinds (same builder as in `attributes-mesh.md`) | after R's registry change | `widgets/attribute_manager.py` and the files `attributes-mesh.md` gives it, `tests/test_attribute_manager.py` |
| integration | last | `scene.py` (link resolution and rename only), `tests/test_interface_defects.py`, `tests/test_objects_ui.py`, `tests/test_fileio_quartz.py`, `tests/test_objects_core.py`, `SPEC.md`, `README.md` |
| nobody | | `objects/gen_trunk.py`, `objects/builtin.py`, `objects/prim_mesh.py`, `objects/spline_shapes.py`, `theme.py`, `icons.py`, `main_window.py`, `widgets/viewport.py`, `widgets/menus_data.py`, shared tests not listed above |

No file has two owners. R's registry change is small and must land before S, P, C, V and AM register params with
`show`, `axes`, `ref`, the new kinds or `migrate`; until then they work on geometry against this contract.

## 8. Not determined

- Most Cinema 4D defaults (marked `(m)`) are from memory; Maxon's pages list names and ranges but not defaults.
  Where Quartz's default already differs (Lathe subdivision 32, Metaball editor subdivision 20, Cloner radial
  plane XZ and grid count 3 x 1 x 3, Voronoi seed 12345, Connect tolerance 0.01) Quartz keeps its own value so saved
  files are unchanged.
- The owner wrote that Text should have "options to change the Caps". This contract reads it as Cinema 4D's Caps
  tab (start and end caps, bevel shape, size, segments). If he meant letter case (upper or lower case), that is a
  one-row addition to Text (`letter_case` choice `("As Typed", "Upper", "Lower")`, default "As Typed") and is not
  specified here.
- Whether Cinema 4D's Object mode aligns the clone's Z or Y axis to the normal: this contract says Z (from memory).
- `specs/attributes-mesh.md` did not exist when this file was written; if it defines `show` conditions or a colour
  row differently, the registry builder implements one mechanism and the AM builder follows that file.
