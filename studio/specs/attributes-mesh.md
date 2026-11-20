# Attributes: mesh objects and the Attribute Manager

Contract for the night run, key `attributes-mesh`. It covers two things:

- the audit of every parametric mesh object in `quartz_studio/objects/prim_mesh.py` and `quartz_studio/objects/builtin.py` against the Object tab of Cinema 4D;
- the simplification of the Attribute Manager (`quartz_studio/widgets/attribute_manager.py`).

Builders implement from this file alone, in parallel. Line numbers refer to the files as they were read on 20/11/2026.

Every rule of `SPEC.md` still holds: no comments or docstrings in code, the window shows only controls that do something, px sizes follow `D:\Markdown\DesignPx.md`, and the simplest implementation that works.

## 0. Ground rules for every builder

1. **Keys are permanent.** No existing parameter key is renamed or removed, and no existing choice string is renamed. `fileio/fmt_quartz.py` line 237 loads with `spec.clamp(raw)`, which fills missing keys with the default and turns an unknown choice back into the default. So:
   - every key added here must have a default that reproduces today's mesh exactly;
   - renaming a key or a choice would silently reset saved files.
2. **Defaults of existing keys stay as they are.** The defaults that differ from Cinema 4D are listed under each object as "differs, keep". Changing them would change every new object and break tests owned by other fleets tonight. The owner decides later.
3. **Old code path at defaults.** Each build keeps its current code path verbatim and uses it whenever every key added here is at its default (or inactive, see each object). The new code path runs only otherwise. The golden test (section 2.1) enforces this.
4. **Visibility rules live on the spec.** Rows are hidden by predicates attached to the spec as a plain attribute, after registration:

   ```
   spec = _register(...)
   spec.applies = {"key": predicate, ...}
   ```

   `ObjectSpec` is a non-frozen dataclass, so this works before the Attribute Manager builder adds the formal field. Each predicate takes the merged values dict `{**spec.defaults(), **obj.params}` and returns a bool. The Attribute Manager reads `getattr(spec, "applies", None) or {}` first and falls back to its own `PARAM_APPLIES` (section 3.5).
5. **Units.** Distances are in cm and angles in degrees. Mesh rules follow `SPEC.md` 7.2: counter-clockwise outward winding, no duplicate or unused points, no zero-area polygons, and a degenerate parameter set returns `Mesh.empty()`.

## 1. Audit against Cinema 4D

### Sources and how to read the tables

- **Sources.** The parameter lists, ranges and IDs come from Maxon's online help (help.maxon.net, the current "en-us" Object Properties, Caps and Slice pages, read on 20/11/2026; links in section 6).
- **Defaults.** The help pages give no default values. Every C4D default below comes from memory and is marked "(mem)".
- **"Quartz today"** gives the key and label in `prim_mesh.py`, or "no".
- **Decisions:**
  - **keep**: present and acceptable;
  - **fix**: present, something changes;
  - **add**: new Param;
  - **skip**: not built, with the reason.
- **Groups.** The `group` of each Param decides the section in the Attribute Manager (section 3.3). Mesh objects use these group names, in this order: `Object`, `Caps`, `Fillet`, `Slice`.
- **Systems Quartz does not have, so their attributes are skipped everywhere:**
  - a renderer (Render Perfect);
  - "Switch to Updated ..." buttons (legacy scene conversion);
  - Phong tags;
  - per-object Make Editable variants (Separate Surfaces).

### 1.1 Shared helpers to add in `prim_mesh.py` (builder B2)

```
SLICE_MIN = -360.0
SLICE_MAX = 360.0
FILLET_SEGMENTS_MAX = 32

def _slice_params() -> tuple:
    return (
        Param("slice", "Slice", "bool", False, group="Slice"),
        Param("slice_from", "From", "angle", 0.0, minimum=SLICE_MIN, maximum=SLICE_MAX, group="Slice"),
        Param("slice_to", "To", "angle", 180.0, minimum=SLICE_MIN, maximum=SLICE_MAX, group="Slice"),
    )

def _slice_args(p: dict) -> tuple[float | None, float | None]:
    return (float(p["slice_from"]), float(p["slice_to"])) if p["slice"] else (None, None)
```

- Applies rule for every object with a slice: `slice_from` and `slice_to` are shown only when `slice` is on.
- `_param_count(..., group=...)` already accepts a group, and `_param_distance` does too. Use them.

### 1.2 Null (`builtin.py`, id `null`)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Shape (Display) | choice | Dot (mem) | None, Dot, Point, Circle, Rectangle, Diamond, Hexagon, Pyramid, Cube (mem) | `display` "Display", same 9 choices | yes | keep |
| Radius | distance | 10 (mem) | 0..inf | `radius` "Radius" 10, min 0 | yes | keep |
| Aspect Ratio | float | 1 (mem) | 0..inf | `aspect_ratio` "Aspect Ratio" 1, min 0, step 0.1 | yes | keep |
| Orientation | choice | Camera (mem) | Camera, XY, ZY, XZ (mem) | `orientation` "Orientation", same | yes | keep |

No change. `builtin.py` gets no owner tonight.

### 1.3 Cube (`cube`, `prim_mesh.py` lines 576-586)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Size . X / Y / Z | distance | 200 each (mem) | 0..inf | `size_x/y/z` "Size X/Y/Z" 200, min 0, max 1e6 | yes | keep |
| Segments X / Y / Z | int | 1 (mem) | 1..1000 | `segments_x/y/z` 1, 1..50 | max differs | fix: maximum 50 -> `SEGMENTS_MAX` (100) |
| Separate Surfaces | bool | off | needs Fillet off | no | - | skip: it only changes Make Editable (one object per side), which needs a multi-object Make Editable in `scene.py` |
| Fillet | bool | off (mem) | - | `fillet` "Fillet", group Fillet | yes | keep |
| Fillet Radius | distance | 40 (mem) | 0..inf, at most half the smallest side | `fillet_radius` 40, clamped in build by `_rounded_cube` | yes | keep |
| Fillet Subdivision | int | 5 (mem) | 1..1000 | `fillet_subdivision` 5, 1..32 | max differs | keep 32 (performance) |

Applies, moved from `PARAM_APPLIES["cube"]`:

```
{"fillet_radius": on("fillet"), "fillet_subdivision": on("fillet")}
```

`on(k)` here means `lambda v: bool(v[k])`. B2 writes the lambdas inline in `prim_mesh.py`; it does not import from the widget.

### 1.4 Plane (`plane`, lines 588-594)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Width, Height | distance | 400 (mem) | 0..inf | `width`, `height` 400 | yes | keep |
| Width Segments, Height Segments | int | 20 (mem) | 1..1000 | 10, 1..100 | default differs | keep (rule 0.2) |
| Orientation | choice | +Y | +X..-Z | `orientation` +Y | yes | keep |

No change.

### 1.5 Polygon (`polygon_object`, lines 596-603; C4D "Polygon", `OSINGLEPOLY`)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Width, Height | distance | 400 (mem) | 0..inf | `width`, `height` 400 | yes | keep |
| Segments | int | 1 (mem) | 1..1000 | no | - | add |
| Triangle | bool | off | - | `triangle` "Triangle" | yes | keep |
| Orientation | choice | not confirmed | +X..-Z | no | - | add |
| (Quartz only) Reverse | bool | - | - | `reverse` "Reverse" | - | keep: it flips the normal, so it does something, and removing it would drop saved values |

New parameter order (`test_polygon_object_does_not_collide_with_editable_kind` changes to this list): `width, height, segments, triangle, orientation, reverse`.

- `_param_count("segments", "Segments", 1)` (group Object, 1..100).
- `Param("orientation", "Orientation", "choice", "+Z", choices=ORIENTATIONS, group="Object")`. The default `+Z` reproduces today's polygon, whose normal is +Z.

Construction, when `segments > 1` or `orientation != "+Z"` (otherwise today's code at lines 174-186 runs):

- Build in the XZ plane facing +Y, then `_orient(mesh, orientation)`. The `+Z` map turns (x, 0, z) into (x, -z, 0), so the corners below land exactly on today's corners.
- Quad: grid points (-hw + w*i/s, 0, -hh + h*j/s) for i, j = 0..s. Faces are s*s quads with hint (0, 1, 0), built like `prim.plane(w, h, s, s)`. Calling `prim.plane(w, h, s, s)` is allowed.
- Triangle: corners p0 = (-hw, 0, hh), p1 = (hw, 0, hh), p2 = (0, 0, -hh). The faces are `_triangle_grid(p0, p1, p2, s)` (s*s triangles) through `_Builder` with hint (0, 1, 0).
- Reverse: reverse every polygon tuple after building and before `_orient`. `_orient` is a proper rotation, so winding survives it.
- Width or height <= 0 returns `Mesh.empty()`, as today.

Tests (B2):

- `segments=3` gives 16 points and 9 quads; `segments=3, triangle=True` gives 10 points and 9 triangles.
- Both are `_valid`, and every polygon normal equals `_axis(o)` for each of the 6 orientations. With `reverse=True` the normal is `-_axis(o)`.
- The total area is w*h for the quad and w*h/2 for the triangle.

### 1.6 Disc (`disc`, lines 605-611)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Inner Radius | distance | 0 (mem) | 0..Outer | `inner_radius` 0 | yes | keep |
| Outer Radius | distance | 100 (mem) | 0..inf | `outer_radius` 100 | yes | keep |
| Disc Segments | int | 2 (mem, unsure) | 1..1000 | `disc_segments` 1 | unsure | keep |
| Rotation Segments | int | 32 (mem) | 3..1000 | `rotation_segments` 32, 3..128 | yes | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Slice, From, To (Slice tab) | bool, angle, angle | off, 0, 180 (mem) | -inf..inf | no | - | add `_slice_params()` |

- The disc has no Regular Grid row in C4D, because there is no cut face.
- Applies: the slice rule only.

Construction, when `slice` is on (otherwise today's code):

- `profile = [(inner + (outer - inner) * k / ds, 0.0) for k = ds down to 0]`. This is ordered outer to inner, so that `revolve` computes +Y normals.
- `revolve(profile, False, rotation_segments, a, b)`, then `_orient`.
- `outer <= inner` returns empty.

Tests:

- The default disc with `slice=True` has 34 points and 1 polygon, a 34-gon pie whose normal is +Y.
- `inner_radius=50, disc_segments=2, rotation_segments=8, slice=True, slice_from=0, slice_to=90` has 27 points and 16 quads, all with normal +Y.

### 1.7 Pyramid (`pyramid`, lines 613-619)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Size X/Y/Z | distance | 200 (mem) | 0..inf | `size_x/y/z` 200 | yes | keep |
| Segments | int | 1 (mem) | 1..1000 | `segments` 1, 1..100 | yes | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Switch to Updated Pyramid | button | - | - | no | - | skip: legacy conversion |

No change.

### 1.8 Sphere (`sphere`, lines 621-625)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Radius | distance | 100 (mem) | 0..inf | `radius` 100 | yes | keep |
| Segments | int | 24 (mem) | 3..1000 | `segments` 16, 3..64 | default and max differ | fix: maximum 64 -> `ROTATION_MAX` (128); the default stays 16 (rule 0.2) |
| Type | choice | Standard | Standard, Tetrahedron, Hexahedron, Octahedron, Icosahedron, Hemisphere | `type`, same 6 | yes | keep |
| Render Perfect | bool | on | - | no | - | skip: no renderer |

C4D has no Slice tab and no Orientation for the sphere.

### 1.9 Torus (`torus`, lines 627-633)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Ring Radius | distance | 100 (mem) | 0..inf | `ring_radius` 100 | yes | keep |
| Ring Segments | int | 24 (mem) | 3..1000 | `ring_segments` 32 | default differs | keep |
| Pipe Radius | distance | 50 (mem) | 0..Ring Radius | `pipe_radius` 50, no upper link | range differs | keep: `test_torus_winding_is_consistent_for_every_radius_pair` deliberately supports pipe >= ring |
| Pipe Segments | int | 12 (mem) | 3..1000 | `pipe_segments` 16 | default differs | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Slice, From, To | | off, 0, 180 | | no | - | add `_slice_params()` |
| Regular Grid, Width | bool, distance | off, 10 (mem) | | no | - | skip: it needs a planar grid fill of an arbitrary outline, which Quartz does not have; cut faces are single n-gons (section 2.2) |

Construction, when `slice` is on:

```
profile, closed = torus_profile(ring_radius, pipe_radius, pipe_segments)
m = revolve(profile, closed, ring_segments, a, b)
m = _orient(m, orientation)
```

Either radius <= 0 returns empty.

Tests: the default torus with `slice=True` has 528 points and 514 polygons, is `_solid(m, 2)`, and its bounds are x -150..150, y -50..50, z 0..150.

### 1.10 Cone (`cone`, lines 635-644)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Top Radius | distance | 0 | 0..inf | `top_radius` 0 | yes | keep |
| Bottom Radius | distance | 100 (mem) | 0..inf | `bottom_radius` 100 | yes | keep |
| Height | distance | 200 (mem) | 0..inf | `height` 200 | yes | keep |
| Height Segments | int | 8 (mem, unsure) | 1..1000 | `height_segments` 4 | unsure | keep |
| Rotation Segments | int | 8 (mem, unsure) | 3..1000 | `rotation_segments` 16 | unsure | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Caps (Caps tab) | bool | on | | `caps` "Caps" | yes | fix: group Object -> Caps |
| Cap Segments | int | 1 | 1..1000 | `cap_segments` 1 | yes | fix: group -> Caps; shown only when `caps` |
| Fillet Segments | int | 5 (mem) | 1..1000 | no | - | add |
| Top (fillet) | bool | off | | no | - | add |
| Top Radius / Height (fillet) | distance | 10 / 10 (mem) | 0..inf | no | - | add |
| Bottom (fillet) | bool | off | | no | - | add |
| Bottom Radius / Height (fillet) | distance | 10 / 10 (mem) | 0..inf | no | - | add |
| Slice, From, To | | off, 0, 180 | | no | - | add `_slice_params()` |
| Regular Grid, Width | | | | no | - | skip (as Torus) |

New params, appended in this order after `cap_segments` (group `Caps`):

| key | label | kind | default | min | max | shown when |
|-|-|-|-|-|-|-|
| `fillet_segments` | Fillet Segments | int | 5 | 1 | 32 | `caps and ((top_radius > 0 and top_fillet) or (bottom_radius > 0 and bottom_fillet))` |
| `top_fillet` | Top Fillet | bool | False | | | `caps and top_radius > 0` |
| `top_fillet_radius` | Top Fillet Radius | distance | 10.0 | 0 | 1e6 | `caps and top_radius > 0 and top_fillet` |
| `top_fillet_height` | Top Fillet Height | distance | 10.0 | 0 | 1e6 | same as above |
| `bottom_fillet` | Bottom Fillet | bool | False | | | `caps and bottom_radius > 0` |
| `bottom_fillet_radius` | Bottom Fillet Radius | distance | 10.0 | 0 | 1e6 | `caps and bottom_radius > 0 and bottom_fillet` |
| `bottom_fillet_height` | Bottom Fillet Height | distance | 10.0 | 0 | 1e6 | same as above |

Then `_slice_params()`. Also `cap_segments` is shown only when `caps`.

- A top fillet is **active** when `caps and top_fillet and top_radius > 0 and top_fillet_radius > 0 and top_fillet_height > 0`. The bottom fillet is active by the same rule with the bottom keys.
- The old path at lines 230-247 runs when no fillet is active and `slice` is off.
- Otherwise: `cone_profile(...)`, then `revolve(profile, False, rotation_segments, a, b)`, then `_orient`.

Tests:

- The default cone with `slice=True` has 70 points and 67 polygons and is `_solid(m, 2)`.
- The default cone with `bottom_fillet=True` (radius 10, height 10, fillet segments 5) has 145 points and 145 polygons. It is `_solid(m, 2)` with bounds (200, 200, 200), and its volume is below the volume with the fillet off.
- `top_radius=40, top_fillet=True, bottom_fillet=True, fillet_segments=1` (chamfers) is a closed solid, bounds (200, 200, 200).
- `caps=False` with fillets on gives the same mesh as `caps=False` with fillets off.

### 1.11 Tube (`tube`, lines 646-654)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Inner Radius | distance | 50 (mem) | 0..inf | `inner_radius` 50 | yes | keep |
| Outer Radius | distance | 100 (mem) | 0..inf | `outer_radius` 100 | yes | keep |
| Rotation Segments | int | 16 (mem) | 3..1000 | `rotation_segments` 16 | yes | keep |
| Cap Segments | int | 1 | 1..1000 | `cap_segments` 1 | yes | keep |
| Height | distance | 100 (mem) | 0..inf | `height` 100 | yes | keep |
| Height Segments | int | 1 | 1..1000 | `height_segments` 1 | yes | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Fillet | bool | off | | no | - | add |
| Segments (fillet) | int | 5 (mem) | 1..1000 | no | - | add |
| Radius (fillet) | distance | 10 (mem) | 0..inf | no | - | add |
| Slice, From, To | | off, 0, 180 | | no | - | add |
| Regular Grid, Width | | | | no | - | skip (as Torus) |

New params, appended after `orientation`:

```
Param("fillet", "Fillet", "bool", False, group="Fillet")
_param_count("fillet_segments", "Fillet Segments", 5, group="Fillet", maximum=FILLET_SEGMENTS_MAX)
_param_distance("fillet_radius", "Fillet Radius", 10.0, group="Fillet")
```

Then `_slice_params()`.

- Applies: `fillet_segments` and `fillet_radius` are shown when `fillet`, plus the slice rule.
- The fillet is active when `fillet and fillet_radius > 0`. The old path runs when the fillet is inactive and `slice` is off.
- Otherwise: `tube_profile(...)`, `revolve(profile, closed, rotation_segments, a, b)`, `_orient`.
- `outer <= inner` or `height <= 0` returns empty, as today.

Tests:

- The default tube with `fillet=True` has 384 points and 384 polygons and is `_solid(m, 0)`, bounds (200, 100, 200).
- The default tube with `slice=True` has 68 points and 66 polygons and is `_solid(m, 2)`.
- `inner_radius=0, fillet=True` is `_solid(m, 2)`.

### 1.12 Cylinder (`cylinder`, lines 656-664)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Radius | distance | 50 (mem) | 0..inf | `radius` 50 | yes | keep |
| Height | distance | 200 (mem) | 0..inf | `height` 200 | yes | keep |
| Height Segments | int | 4 (mem) | 1..1000 | `height_segments` 4 | yes | keep |
| Rotation Segments | int | 16 (mem) | 3..1000 | `rotation_segments` 16 | yes | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Caps (Caps tab) | bool | on | | `caps` | yes | fix: group -> Caps |
| Segments (caps) | int | 1 | 1..1000 | `cap_segments` "Cap Segments" | yes | fix: group -> Caps; shown when `caps` |
| Fillet | bool | off | needs Caps | no | - | add |
| Segments (fillet) | int | 5 (mem) | 1..1000 | no | - | add |
| Radius (fillet) | distance | 10 (mem) | 0..inf, up to Radius | no | - | add |
| Slice, From, To | | off, 0, 180 | | no | - | add |
| Regular Grid, Width | | | | no | - | skip (as Torus) |

New params, appended after `cap_segments` (group `Caps`):

```
Param("fillet", "Fillet", "bool", False, group="Caps")
_param_count("fillet_segments", "Fillet Segments", 5, group="Caps", maximum=FILLET_SEGMENTS_MAX)
_param_distance("fillet_radius", "Fillet Radius", 10.0, group="Caps")
```

Then `_slice_params()`.

- Applies: `cap_segments` and `fillet` are shown when `caps`; `fillet_segments` and `fillet_radius` are shown when `caps and fillet`; plus the slice rule.
- The fillet is active when `caps and fillet and fillet_radius > 0`. The old path runs when the fillet is inactive and `slice` is off.
- Otherwise: `cylinder_profile(...)`, `revolve(profile, False, rotation_segments, a, b)`, `_orient`.

Tests:

- The default cylinder with `fillet=True` has 240 points and 226 polygons. It is `_solid(m, 2)`, bounds (100, 200, 100), with a volume below `pi * 50**2 * 200`.
- The default cylinder with `slice=True` has 87 points and 68 polygons and is `_solid(m, 2)`. Its bounds are x -50..50, y -100..100, z 0..50.
- `fillet_radius=1000` clamps to the radius 50 (hemispherical caps) and stays `_solid(m, 2)`, bounds (100, 200, 100).
- `caps=False, slice=True` is `_valid` and not closed.

### 1.13 Oil Tank (`oil_tank`, lines 666-674)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Radius | distance | 100 (mem, unsure) | 0..inf | `radius` 50 | unsure | keep |
| Height | distance | 200 (mem) | 0..inf | `height` 200 | yes | keep |
| Height Segments | int | 4 (mem) | 1..1000 | `height_segments` 4 | yes | keep |
| Cap Height | distance | unsure | 0..Radius | `cap_height` 25, clamped to height/2 in `prim.oil_tank` | max differs | keep (the clamp is safe) |
| Cap Segments | int | 8 (mem) | 1..1000 | `cap_segments` 8 | yes | keep |
| Rotation Segments | int | 16 (mem) | 3..1000 | `rotation_segments` 16 | yes | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Slice, From, To | | off, 0, 180 | | no | - | add |
| Regular Grid, Width | | | | no | - | skip |

Construction, when `slice` is on: `capped_profile` with exactly the numbers of `prim.oil_tank`:

```
cap = min(max(0, cap_height), h / 2)
capped_profile(r, -h/2 + cap, h/2 - cap, cap, cap, height_segments, cap_segments)
```

Then `revolve(profile, False, rotation_segments, a, b)` and `_orient`.

Test: the default oil tank with `slice=True` has 325 points and 322 polygons and is `_solid(m, 2)`.

### 1.14 Capsule (`capsule`, lines 676-683)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Radius | distance | 50 (mem) | 0..inf | `radius` 50 | yes | keep |
| Height (overall) | distance | 200 (mem) | 0..inf | `height` 200, overall height | yes | keep |
| Height Segments | int | 4 (mem) | 1..1000 | `height_segments` 4 | yes | keep |
| Cap Segments | int | 8 (mem) | 1..1000 | `cap_segments` 8 | yes | keep |
| Rotation Segments | int | 16 (mem) | 3..1000 | `rotation_segments` 16 | yes | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Slice, From, To | | off, 0, 180 | | no | - | add |
| Regular Grid, Width | | | | no | - | skip |

Construction, when `slice` is on: `capped_profile` with the numbers of `_build_capsule` (line 274) and `prim.capsule`:

```
body = max(0, height - 2 * r)
capped_profile(r, -body/2, body/2, r, r, height_segments, cap_segments)
```

Then `revolve` and `_orient`.

Test: the default capsule with `slice=True` has 325 points and 322 polygons and is `_solid(m, 2)`.

### 1.15 Platonic (`platonic`, lines 685-689)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Radius | distance | 100 (mem) | 0..inf | `radius` 100 | yes | keep |
| Segments | int | 1 (mem) | 1..1000 | `segments` 1, 1..16 | max differs | keep (geodesic cost) |
| Type | choice | Tetrahedron | Tetrahedron, Hexahedron, Octahedron, Dodecahedron, Icosahedron, C60-Buckyball | `type` Tetra, Hexa, Octa, Dodeca, Icosa, Soccer | same set, short names | keep: the strings are stored in files (rule 0.1) |
| Switch to Updated Platonic | button | | | no | - | skip |

### 1.16 Landscape (`landscape`, lines 691-704; C4D "Landscape", `OFRACTAL`)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Size X/Y/Z | distance | 600, 100, 600 (mem) | 0..inf | `size_x/y/z` same | yes | keep |
| Width Segments, Depth Segments | int | 100 (mem) | 4..1000 | 100, 1..200 | min differs | keep |
| Rough Furrows, Fine Furrows | percent | 50 (mem) | 0..100 | same | yes | keep |
| Scale | float | 1 (mem) | 0..10 | `scale` 1, 0.1..10 | min differs | keep |
| Sea Level | percent | 0 | 0..100 | `sea_level` 0 | yes | keep |
| Plateau Level | percent | 100 | 0..100 | `plateau_level` 100 | yes | keep |
| Orientation | choice | +Y | | `orientation` | yes | keep |
| Multifractal | bool | on (mem) | | no | - | add |
| Seed | int | 0 | -2147483648..2147483647 | `seed` 0, unbounded | range differs | fix: minimum -2147483648, maximum 2147483647 |
| Borders At Sea Level | bool | off (mem) | unavailable with Spherical | no | - | add |
| Spherical | bool | off | | no | - | add |
| Switch to Updated Landscape | button | | | no | - | skip |

New parameter order: `..., orientation, multifractal, seed, borders_at_sea_level, spherical`.

- `Param("multifractal", "Multifractal", "bool", True, group="Object")`
- `Param("borders_at_sea_level", "Borders At Sea Level", "bool", False, group="Object")`
- `Param("spherical", "Spherical", "bool", False, group="Object")`
- Applies: `size_z` and `borders_at_sea_level` are shown when `not spherical`.

Construction (in `_height_field`, line 443, and `_build_landscape`, line 470):

- **Multifractal off.** Each layer adds `amp * weight * (1.0 - abs(noise))` instead of `amp * weight * noise`, which gives a ridged field. The rest of `_height_field` is unchanged: normalisation to 0..1, then sea and plateau. When `multifractal` is on, the code is exactly today's.
- **Borders At Sea Level** (ignored when spherical).
  - After the 0..1 normalisation and before the sea and plateau clip, multiply by `smooth(min(1, d / 0.25))`.
  - Here `d = min(u, 1 - u, v, 1 - v)` and `smooth(t) = t * t * (3 - 2 * t)`.
  - The outer border then sits at height 0.
- **Spherical.**
  - Compute `hn` on the same `(ws + 1) x (ds + 1)` grid as today. Use the columns `i = 0..ws-1` (column `ws` is dropped so that the seam closes) and the rows `j = 1..ds-1`.
  - Effective counts are `ws = max(3, ws)` and `ds = max(2, ds)`.
  - With `R = size_x / 2`, `lon = 2*pi*i/ws` and `lat = pi*j/ds - pi/2`, each point is `(R + size_y*h) * (cos(lat)*cos(lon), sin(lat), cos(lat)*sin(lon))`.
  - Pole points are `(0, -(R + size_y*mean(row 0)), 0)` and `(0, R + size_y*mean(row ds), 0)`.
  - Faces are quads between consecutive rows (wrapping in i) and triangle fans to the poles. All go through `_Builder.face` with the centroid as hint.
  - `R <= 0` returns empty, and `_orient` applies.

Tests:

- Defaults are unchanged (golden).
- `multifractal=False` differs from the default, is `_valid`, and its y range is 0..100.
- `borders_at_sea_level=True`: every border point has y == 0, and the interior max is > 0.
- `spherical=True` has 9902 points and 10000 polygons. It is `_valid` and closed with `_euler == 2`, and every point's distance from the origin is in `[300, 400]`.
- `spherical=True, width_segments=1, depth_segments=1` is a closed solid (it uses 3 x 2).

### 1.17 Bezier (`bezier`, lines 706-712)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Subdivision X / Y | int | 24 (mem, unsure) | 3..1000 | `subdivision_x/y` 24, 1..100 | min differs | keep |
| Grid Points X / Y | int | 3 (mem) | 3..100 | `grid_x/y` 3, 2..16 | range differs | keep |
| Closed X / Y | bool | off | | no | - | skip: the patch's control points cannot be edited in Quartz, so closing a flat grid gives a degenerate seam; it needs point editing of parametric control grids |
| (Quartz only) Grid Spacing | distance | - | | `spacing` 200 | - | keep |

### 1.18 Figure (`figure`, lines 714-717)

| C4D attribute | Type | C4D default | C4D range | Quartz today | Agrees | Decision |
|-|-|-|-|-|-|-|
| Height | distance | 200 (mem) | 0..inf | `height` 200 | yes | keep |
| Segments | int | 4 (mem) | 4..1000 | `segments` 2, 1..20 | default and min differ | keep (rule 0.2) |
| Legacy Axis Mode | bool | | pre-R18 scenes only | no | - | skip |

### 1.19 Out of scope here: Text

The owner's example is Text: font, caps, "well modifiable". The mesh Text object (id `text`, category `mesh`) is registered in `objects/gen_spline.py` lines 884-887, together with Text Spline, and it is not in the two files this audit covers. The splines and generators audit owns it and owns any `font` row kind.

This file asks nothing about Text from any builder.

## 2. New geometry code

### 2.1 Golden test: defaults reproduce today's meshes (B2, `tests/test_objects_mesh_golden.py`)

The signature function, exactly as it was used to compute the values below on 20/11/2026:

```
def _sig(m):
    pts = np.round(np.asarray(m.points, float), 6) + 0.0
    h = hashlib.sha1()
    h.update(pts.astype("<f8").tobytes())
    h.update(repr([tuple(int(i) for i in p) for p in m.polygons]).encode())
    h.update(repr(sorted(tuple(sorted((int(a), int(b)))) for a, b in m.loose_edges)).encode())
    return len(m.points), len(m.polygons), h.hexdigest()[:16]
```

Build with `spec.build(spec.clamp(kw), [])`. Expected values:

| id | params | points | polygons | sha1[:16] |
|-|-|-|-|-|
| cube | {} | 8 | 6 | aa63ba5a847dc202 |
| plane | {} | 121 | 100 | 6eb2a1780b32ffe4 |
| polygon_object | {} | 4 | 1 | c1ff9df6517cbf1a |
| disc | {} | 32 | 1 | fc7dbaffcef1cd5f |
| pyramid | {} | 5 | 5 | 78730499c6f9500d |
| sphere | {} | 114 | 128 | 9179d5458a8a16a7 |
| torus | {} | 512 | 512 | 0d79acff58e16dd3 |
| cone | {} | 65 | 65 | 3874cde8be363aa6 |
| tube | {} | 64 | 64 | 1b315cc386eb4e2b |
| cylinder | {} | 80 | 66 | 79dc1b9b79808a5b |
| oil_tank | {} | 306 | 320 | be7f40e03f60776b |
| capsule | {} | 306 | 320 | 825ec3325177cf2e |
| platonic | {} | 4 | 4 | b4fa6d8eb1eb51c2 |
| landscape | {} | 10201 | 10000 | cfe18fda8e29a905 |
| bezier | {} | 625 | 576 | 255fe974af4e4301 |
| figure | {} | 156 | 144 | 295ffbc7c795ada5 |
| null | {} | 0 | 0 | 871d01b18b7460ae |
| cube | {"fillet": True} | 728 | 726 | 392c29514e272e65 |
| cone | {"top_radius": 30.0, "cap_segments": 3} | 144 | 130 | e5b2e11e4a2a76ce |
| cylinder | {"caps": False} | 80 | 64 | e8e4b0c2a2e8a2f5 |
| tube | {"inner_radius": 0.0} | 32 | 18 | b40f724626a6c51b |
| polygon_object | {"triangle": True} | 3 | 1 | 94623e4ab52adb48 |
| sphere | {"type": "Hemisphere"} | 65 | 65 | 52c21fa7de9c762e |
| cylinder | {"orientation": "+X"} | 80 | 66 | e86c78513f2311e0 |

A second test loads a `.quartz` written with only today's keys and checks that the rebuilt mesh signatures are unchanged. It writes a minimal Document through `fileio` with `params` holding today's keys only, then reads it back.

### 2.2 `quartz_studio/objects/revolve.py` (new, builder B1)

The module is pure functions with no Qt. Its name has no `prim_` prefix, so `objects/__init__.py` does not import it on its own; `prim_mesh.py` imports it.

It uses `quartz_studio.modeling.primitives._Builder` (methods `vertex(x, y, z)`, `face(corners, hint)` and `mesh()`, lines 33-64). Do not import from `prim_mesh` (that would be a circular import).

```
AXIS_EPS = 1e-9
Profile = list[tuple[float, float]]

def revolve(profile: Profile, closed: bool, segments: int,
            slice_from: float | None = None, slice_to: float | None = None) -> Mesh
def cylinder_profile(radius, height, height_segments, caps, cap_segments,
                     fillet, fillet_radius, fillet_segments) -> tuple[Profile, bool]
def cone_profile(top, bottom, height, height_segments, caps, cap_segments,
                 top_fillet, top_radius, top_height, bottom_fillet, bottom_radius, bottom_height,
                 fillet_segments) -> tuple[Profile, bool]
def tube_profile(inner, outer, height, height_segments, cap_segments,
                 fillet, fillet_radius, fillet_segments) -> tuple[Profile, bool]
def torus_profile(ring_radius, pipe_radius, pipe_segments) -> tuple[Profile, bool]
def capped_profile(radius, bottom_eq, top_eq, dome_bottom, dome_top,
                   body_segments, cap_segments) -> tuple[Profile, bool]
```

#### Profile convention

- A profile is a list of `(rho, y)`, where rho is the distance from the Y axis.
- It is ordered counter-clockwise in the half-plane with rho to the right and y up:
  - axis solids go from the bottom axis point, out along the bottom, up the side, and in across the top to the top axis point;
  - loops (tube, torus) go round counter-clockwise.
- `closed=True` means that the last point connects to the first.
- A point with `rho <= AXIS_EPS` is an axis point.

#### `revolve`

1. **Clean the profile.** Drop any point closer than `AXIS_EPS` to the previous one. For `closed`, also drop a last point equal to the first. Fewer than 2 points returns `Mesh.empty()`. `segments = max(3, int(segments))`.
2. **Angles** (in degrees; points are `(rho*cos t, y, rho*sin t)`, the same convention as `_ring` in `prim_mesh.py` line 81).
   - Full revolution: `t_j = 360*j/n` for `j = 0..n-1`, wrapping.
   - Sliced: `a, b = sorted((slice_from, slice_to))`, `span = b - a`.
     - If `span >= 360 - 1e-9`, treat it as a full revolution.
     - If `span <= 1e-9`, return `Mesh.empty()`.
     - Otherwise `t_j = a + span*j/n` for `j = 0..n`, with no wrap.
   - `n` is `segments` over the remaining arc. Whether C4D keeps the full-circle density instead is not confirmed; this choice is final for Quartz.
3. **Vertices.** An off-axis profile point gives one vertex per angle. An axis point gives one vertex `(0, y, 0)`, which is created only when a face uses it, so that no point goes unused.
4. **Faces** for each profile segment `(p, q)` (including last-to-first when `closed`):
   - Both points on the axis: no face.
   - One on the axis and `abs(dy) <= AXIS_EPS` (a flat cap):
     - full revolution: one polygon made of the rim ring (n points); the axis vertex is not created;
     - sliced: one pie polygon, `[axis, rim_0 .. rim_n]`.
     - The hint is `(0, sign(n_y), 0)`.
   - One on the axis, not flat: one triangle per step, `[axis, rim_j, rim_j+1]`.
   - Neither on the axis: quads `[p_j, p_j+1, q_j+1, q_j]`.
   - The hint for triangles and quads is the outward profile normal rotated to the mid angle `tm`: with `(n_rho, n_y) = (dy, -drho)`, where `dy = q.y - p.y` and `drho = q.rho - p.rho`, the hint is `(n_rho*cos tm, n_y, n_rho*sin tm)`.
5. **Cut faces**, only when sliced and the profile encloses area (`closed`, or both of its ends on the axis):
   - At angle a: one polygon of every profile vertex at that angle, in profile order (each axis point once), with hint `-T(a)`.
   - At angle b: the same, with hint `+T(b)`.
   - Here `T(t) = (-sin t, 0, cos t)`.
   - Open profiles get no cut faces: a cylinder without caps, a disc.
6. Return `b.mesh()`.

#### Profiles

The arc helper is `arc(cx, cy, rx, ry, t0, t1, k)`. It returns the points `(cx + rx*cos t, cy + ry*sin t)` for `t = t0 + (t1 - t0)*i/k`, `i = 1..k`, so the start point is excluded.

**`cylinder_profile`**

- With `caps` off, the profile is open and has the side only: `(r, -h/2 + h*k/hs)` for `k = 0..hs`.
- With caps on:
  - `f = min(fillet_radius, r, h/2)` when `fillet`, else 0.
  - Start at `(0, -h/2)`.
  - Bottom cap: `((r - f)*k/cs, -h/2)` for `k = 1..cs`, only when `r - f > AXIS_EPS`.
  - When `f > 0`: `arc(r - f, -h/2 + f, f, f, -90, 0, fs)`.
  - Side: `(r, y0 + (y1 - y0)*k/hs)` for `k = 1..hs`, where `y0 = -h/2 + f` and `y1 = h/2 - f`, only when `y1 - y0 > AXIS_EPS`.
  - When `f > 0`: `arc(r - f, h/2 - f, f, f, 0, 90, fs)`.
  - Top cap inward: `((r - f)*k/cs, h/2)` for `k = cs-1 .. 1`, then `(0, h/2)`.
  - `closed=False`.
  - `fillet_segments = 1` gives a chamfer.

**`cone_profile`**

- Bottom fillet active: `bottom > 0` and both values > 0. Then `br = min(bottom_radius, bottom)` and `bh = bottom_height`; otherwise both are 0.
- Top fillet active: the same rule with `top`.
- If `bh + th > h`, scale both by `h / (bh + th)`.
- With `caps` off, all fillets are 0 and the profile is the side only: `(bottom + (top - bottom)*k/hs, -h/2 + h*k/hs)` for `k = 0..hs`.
- With caps on:
  - When `bottom > 0`, start at `(0, -h/2)` and add the cap points `((bottom - br)*k/cs, -h/2)` for `k = 1..cs` (only while `bottom - br > AXIS_EPS`).
  - When `br > 0`: `arc(bottom - br, -h/2 + bh, br, bh, -90, 0, fs)`.
  - Side from `(bottom, -h/2 + bh)` to `(top, h/2 - th)` in `hs` steps (`k = 1..hs`). When `top == 0`, the last point is the apex `(0, h/2)`.
  - When `th > 0`: `arc(top - tr, h/2 - th, tr, th, 0, 90, fs)`.
  - When `top > 0`: the top cap inward, `((top - tr)*k/cs, h/2)` for `k = cs-1 .. 1`, then `(0, h/2)`.
  - When `bottom == 0`, the profile starts at the axis `(0, -h/2)` and the side runs from there.
  - `closed=False`.

**`tube_profile`**

- When `inner <= AXIS_EPS`, return `cylinder_profile(outer, height, height_segments, True, cap_segments, fillet, fillet_radius, fillet_segments)`.
- Otherwise `f = min(fillet_radius, (outer - inner)/2, h/2)` when `fillet`, else 0. The loop:
  - start at `(inner + f, -h/2)`;
  - bottom edge to `(outer - f, -h/2)` in `cs` steps;
  - when `f > 0`, `arc(outer - f, -h/2 + f, f, f, -90, 0, fs)`;
  - outer wall to `(outer, h/2 - f)` in `hs` steps;
  - arc `(outer - f, h/2 - f)`, from 0 to 90;
  - top edge to `(inner + f, h/2)` in `cs` steps;
  - arc `(inner + f, h/2 - f)`, from 90 to 180;
  - inner wall down to `(inner, -h/2 + f)` in `hs` steps;
  - arc `(inner + f, -h/2 + f)`, from 180 to 270, without its last point (it equals the start).
- Zero-length walls or edges are skipped by the cleaning step. `closed=True`.

**`torus_profile`**

- `[(R + p*cos(360*j/ps), p*sin(360*j/ps)) for j in range(ps)]`, with `ps = max(3, ps)`.
- `closed=True`.

**`capped_profile`**

- The same levels as `modeling/primitives.py` `_capped_body` (lines 98-114), returned as `(rho, y)` from the bottom pole to the top pole.
- `closed=False`.

#### Edge cases

| Case | Expected result |
|-|-|
| `fillet_radius` larger than allowed | clamped as described above, no exception |
| `f == r` (cylinder) | the caps are domes, with no flat cap points |
| `f == h/2` | no straight side |
| pipe >= ring (torus, sliced) | a valid but self-intersecting result, not tested for volume |
| span of exactly 0 | empty mesh |
| span >= 360 | the full mesh, identical to the full-revolution path of `revolve` |

#### Tests (B1, `tests/test_objects_revolve.py`)

Every count is computed through the profile function plus `revolve` with today's defaults:

| Case | Points | Polygons | Check |
|-|-|-|-|
| cylinder fillet (r50 h200 hs4 cs1 fs5 f10, rot16) | 240 | 226 | `_solid(m, 2)` |
| cylinder sliced 0..180 (caps on, no fillet) | 87 | 68 | `_solid(m, 2)` |
| cone sliced 0..180 (top 0, bottom 100, h200, hs4, cs1) | 70 | 67 | `_solid(m, 2)` |
| cone bottom fillet (r10 h10 fs5) | 145 | 145 | `_solid(m, 2)` |
| tube fillet (50/100, h100, cs1, hs1, f10, fs5) | 384 | 384 | `_solid(m, 0)` |
| tube sliced 0..180 | 68 | 66 | `_solid(m, 2)` |
| torus sliced 0..180 (R100 ps16, segments 32) | 528 | 514 | `_solid(m, 2)` |
| capsule levels sliced 0..180 | 325 | 322 | `_solid(m, 2)` |
| disc profile [(100,0),(0,0)] sliced 0..180 | 34 | 1 | +Y normal |

Also:

- Slices -90..90, 0..270, 45..46 and 180..0 (equal to 0..180) are all closed solids.
- A slice of 0..360 equals the full revolution in points and polygons.
- `fillet_segments=1` on the cylinder: the arc contributes 1 point per corner.

Copy the helpers `_closed`, `_euler`, `_volume`, `_valid` and `_solid` from `tests/test_objects_prim_mesh.py` (lines 30-77) into the new test file; do not import across test files.

### 2.3 Other tests B2 updates in `tests/test_objects_prim_mesh.py`

- Line 444: the polygon key list becomes `["width", "height", "segments", "triangle", "orientation", "reverse"]`.
- Add the per-object tests of section 1 (polygon, disc, torus, cone, tube, cylinder, oil tank, capsule, landscape).
- Add `test_applies_rules_on_specs`. For each spec listed in section 1 with rules:
  - `getattr(spec, "applies")` holds exactly the keys named there;
  - each predicate gives the documented result for the defaults and for the toggled value. For example, cylinder `fillet_radius` is False at the defaults and True with `{"fillet": True}`.
- `test_distances_reject_non_finite_and_counts_have_maximums` keeps passing: every new int key ending in `segments` has a maximum.

## 3. Attribute Manager simplification (builder B3)

The owner's words: the Basic and Coord. parts are removed altogether. With only Object left, the chips disappear: just the Attributes header, then the object's line, then its attributes.

### 3.1 Removed from `widgets/attribute_manager.py`

- Constants (lines 70-72, 98-102): `TAB_NAMES`, `TAB_TITLES`, `TAB_BASIC`, `TAB_COORD`, `TAB_OBJECT`, `COORD_ROWS`, `CHIP_BAR_H` (line 43) and `SECTION_H` (line 44). Remove `"TAB_NAMES"` and `"COORD_ROWS"` from `__all__`.
- Widgets: `chip_bar`, `chip_group`, `chips` (lines 444-460); `section_title` (lines 470-477); `page_basic` with `name_edit` and `enabled_box` (lines 479-481, 518-530); `page_coord` with `coord_fields` (lines 482-484, 532-540).
- Methods: `_group_page`, `_build_basic`, `_build_coords`, `current_tab`, `tab_available`, `set_tab_index`, `_apply_tab`, `_load_basic`, `_load_coords`, `_on_name`, `_on_enabled`, `_on_coord`.
- Imports that become unused: `QButtonGroup`, `Chip`, `CoordField` (keep `format_number`), and `_rule` if it is unused.
- `self._tab`.
- **Compatibility until integration.** Keep `def set_tab(self, _name: str = "Object") -> None: return None`, because `test_interface_defects.py`, `test_objects_ui.py`, `test_context_menu.py`, `test_trunk_generator.py` and `test_coordinates.py` call `set_tab`. The integration step deletes those calls and then the method.

Where the removed controls live now:

- **Name:** the Object Manager (F2 or double click, `object_manager.py` line 456 `rename`) and the header line, which shows it.
- **Enabled:** the Object Manager toggle (`object_manager.py` line 463 `toggle_enabled`).
- **Position, rotation and size:** the Coordinates card (`widgets/coordinates.py`).

### 3.2 Card layout, top to bottom

1. `self.tabs = PanelTabBar(("Attributes",), self)` and `HeaderRule`, unchanged.
2. `self.header` (`ObjectHeader`: icon and `"Type [Name]"`), unchanged except the height (section 3.6).
3. `self.error_label`, unchanged.
4. `self.summary_label` (new). Only for editable objects (`obj.kind == "polygon"`):
   - a `QLabel` with object name `qsDimLabel`, fixed height `theme.ROW_H` (24) and contents margins `(theme.SPACE_2, 0, theme.SPACE_2, 0)`;
   - its text is `mesh_summary(obj.mesh)`;
   - hidden for parametric objects and in the empty state.
5. `self.scroll` holding `object_host` with the rows. It is visible only when the spec has params. An editable object or a spec without params shows no scroll area: the header (and the summary) are the whole card.
6. `self.empty_label` "No object selected", unchanged.

Decision for editable objects: they show a summary line, not the empty state, because the card still names the object and its size.

`mesh_summary(mesh) -> str` is a new module-level function, added to `__all__`:

| Mesh contents | Text |
|-|-|
| has polygons | `f"{P} points · {F} polygons"` |
| only loose edges | `f"{P} points · {E} edges"` |
| no polygons and no edges | `f"{P} points"` |

- `·` is U+00B7 with one space on each side, as in the status bar text.
- Singular forms: "1 point", "1 polygon", "1 edge".
- E is `len(mesh.loose_edges)`.

It refreshes on every `scene.changed`, through `_load`.

### 3.3 Sections

- Rows are grouped by `param.group`, in the order of each group's first appearance in `spec.params` (as `_rebuild_object_page` does today, lines 641-648). Every group is a `CollapsibleGroup`, and `self.object_groups` keeps all of them.
- **The first group has no header.** Call `group.header.setVisible(False)`; the group is always expanded and cannot be collapsed. Its rows follow the object line directly, which is the owner's "without saying anything".
- Every later group shows the existing `CollapsibleGroup` header: `theme.ROW_H` high, a chevron, the uppercase title in `header_font`. Examples: CAPS, FILLET, SLICE.
- Separator line: the first group passes `separator=True` only when the spec has more than one group. The other groups keep the default separator.
- **Remembered state.** `self._expanded: dict[tuple[str, str], bool]`, keyed by `(spec.id, group title)`, for the session only (no QSettings). When a page is built, apply the stored state (default True) to every group except the first. Connect `group.toggled` to store it.
- A group is hidden when none of its rows applies. This exists already in `_apply_applicable`, lines 723-731, and stays.
- Body spacing: `group.content_layout().setSpacing(2)` instead of 1, because 1 px is reserved for divider lines.

### 3.4 Row kinds

The mesh attributes of section 1 use only the existing kinds: `distance`, `int`, `bool`, `choice`, `angle`, `percent`, `float`. `angle` already shows the suffix " °" (line 108).

This audit needs **no new row kind** from the attribute manager builder. Font, colour, file path and curve rows are defined by the splines and generators audits, if they need them.

### 3.5 `param_applies` (lines 708-721)

```
rules = getattr(spec, "applies", None) or {}
rule = rules.get(key) or PARAM_APPLIES.get(spec.id, {}).get(key)
```

- The rest is unchanged: choices with fewer than 2 options are hidden; with no rule, the row is shown.
- B3 adds the formal field to `objects/registry.py` `ObjectSpec`: `applies: dict = field(default_factory=dict)`, which needs `from dataclasses import field`. It goes after `description`, so positional construction is unaffected.
- `PARAM_APPLIES` keeps its current entries. The integration step deletes the `cube` entry once `prim_mesh.py` carries it.

### 3.6 Pixel norm in this file (`DesignPx.md`)

| Constant or call | Now | New |
|-|-|-|
| `LABEL_WIDTH` | 118 | 120 |
| `HEADER_H` | 26 | 28 |
| `VECTOR_SPIN_MIN` | 30 | 32 |
| `SPIN_TEXT_MARGIN` | 5 | 6 |
| `VECTOR_TEXT_MARGIN` | 3 | 4 |
| `ParamEditor` layout `setSpacing(3)` | 3 | 4 |
| `setMinimumSize(260, 160)` | 260 x 160 | 256 x 160 |
| `VECTOR_SPIN_STYLE` padding `1px 2px` | 1px 2px | 2px 2px |

- `LABEL_INDENT` 10, `HEADER_ICON` 18, `ARROW_W` 16 and the empty-label margin 24 already comply.
- The longest mesh label, "Borders At Sea Level", measured 106 px in the default font, so it fits 120.
- Shared constants in `theme.py` and `common.py` (`CHIP_H` 26, `CollapsibleGroup` margins) belong to whichever fleet owns the pixel-norm pass, not to B3.

### 3.7 Tests (B3, `tests/test_attribute_manager.py`)

Remove:

- `test_tabs_basic_coord_object`
- `test_rename_through_the_name_field`
- `test_enabled_checkbox`
- `test_coordinates_bound_to_local_transform`
- `test_coordinates_of_a_child_are_local`
- `test_coordinates_work_for_editable_meshes`
- `test_typed_name_is_not_overwritten_by_scene_changes`
- `test_typed_coordinate_is_not_overwritten_by_scene_changes`
- `test_chip_group_is_exclusive`

Change:

- `_make`: drop the `tab` argument and the `set_tab` call. Every caller drops `tab=...`.
- `test_rows_built_per_kind`: the visible group headers are `[g.title_label.text() for g in groups if g.header.isVisibleTo(am)] == ["LOOK"]`. The SHAPE group exists, but its header is hidden.
- `test_switching_objects_rebuilds_object_tab`: replace `not am.chips[2].isVisibleTo(am)` with `not am.scroll.isVisibleTo(am)`.
- `test_object_without_params_has_no_object_tab`: no editors, the scroll area is hidden, the header is visible, and the summary is hidden.
- `test_empty_state_has_no_controls`: drop the `chip_bar` assertion and add `not am.summary_label.isVisibleTo(am)`.
- `test_error_message_is_visible`, `test_no_row_rebuild_during_edits`, `test_refresh_alone_makes_no_edits`: drop the `set_tab` lines.

Add:

- `test_no_chips_basic_or_coordinates`:
  - no `Chip`, no `CoordField` and no `QLineEdit` other than text-kind editors among the children;
  - `not hasattr(am, "chips")`, `not hasattr(am, "name_edit")`, `not hasattr(am, "coord_fields")`.
- `test_first_group_has_no_header_and_later_groups_collapse`:
  - with `ALL_ID`, the Shape header is hidden and the Look header is visible;
  - clicking the Look header hides its body;
  - switching to `BOX_ID` and back restores it collapsed.
- `test_editable_mesh_shows_summary`:
  - the default scene Cube is editable; the summary is visible with text `"8 points · 6 polygons"`, and there are no editors;
  - a mesh with 1 point and no polygons gives `"1 point"`;
  - `mesh_summary` of a 3-point, 2-edge spline mesh is `"3 points · 2 edges"`.
- `test_spec_applies_attribute_hides_rows`:
  - register a test spec, set `spec.applies = {"b": lambda v: v["a"]}`;
  - row b is hidden until `a` is set True, then shown.
- `test_pixel_constants`:
  - `LABEL_WIDTH == 120`, `HEADER_H == 28`, `am.minimumWidth() == 256`;
  - every int constant of the module that is a size is in the allowed set of `DesignPx.md`.

## 4. File ownership

Three parallel builders and one final integration step. No file has two owners.

| Builder | Owns (edits or creates) | Reads only |
|-|-|-|
| B1 Revolve | `quartz_studio/objects/revolve.py` (new), `tests/test_objects_revolve.py` (new) | `modeling/primitives.py`, `scene.py` |
| B2 Mesh params | `quartz_studio/objects/prim_mesh.py`, `tests/test_objects_prim_mesh.py`, `tests/test_objects_mesh_golden.py` (new) | `objects/revolve.py` (calls the signatures of 2.2; until B1 lands, slice and fillet tests fail by import, everything else passes), `objects/registry.py`, `fileio/` |
| B3 Attribute manager (the single owner of this file across the mesh, splines and generators audits) | `quartz_studio/widgets/attribute_manager.py`, `quartz_studio/objects/registry.py` (only the `applies` field), `tests/test_attribute_manager.py` | `widgets/common.py`, `widgets/object_manager.py`, `theme.py` |
| Integration (last, after B1-B3 and the other audits) | `tests/test_objects_ui.py` (lines 353-365: drop `tab_available`, `set_tab` and `page_basic`; assert `attrs.object_host.isVisibleTo(attrs)`), `tests/test_coordinates.py` (lines 352-357: drop the tab calls), `tests/test_interface_defects.py` (line 248), `tests/test_context_menu.py` (line 730), `tests/test_trunk_generator.py` (line 508); then remove `set_tab` from `attribute_manager.py`, delete `PARAM_APPLIES["cube"]`, update `SPEC.md` 3.8 and line 59 (no chips) and 7.1 (`ObjectSpec.applies`), `README.md` if it mentions the chips, and `D:\Markdown\Quartz.md` | - |

- **Shared files nobody here touches:** `theme.py`, `icons.py`, `main_window.py`, `widgets/viewport.py`, `widgets/menus_data.py`, `widgets/menu_bar.py`, `widgets/object_palette.py`, `widgets/common.py`, `scene.py`, `builtin.py`.
  - No new icons are needed.
  - No menu or palette entry changes.
- **Tests that fail between B3 landing and integration** (expected; do not fix them inside B3):
  - `test_objects_ui.py::test_attribute_manager_shows_the_object_tab_of_the_created_object` (it uses `page_basic` and `tab_available`);
  - `test_coordinates.py::test_object_rename_and_attribute_header` (it uses `current_tab`).
- **Run command:** `.\.venv\Scripts\python.exe tests\test_<name>.py` from `D:\Apps\Quartz\studio`, offscreen.

## 5. Not determined

- **C4D defaults.** None are on the help pages; every "(mem)" value comes from memory. Unsure: Disc Segments (2?), Cone segments (8/8?), Oil Tank radius and cap height, Bezier subdivision, the Polygon default orientation.
- **Slice segment distribution.** Whether C4D spreads Rotation Segments over the remaining arc or keeps the full-circle density is not confirmed. This contract chooses the remaining arc.
- **C4D cone fillet shape.** It is approximated by quarter-ellipses with vertical tangents at the side. Where the cone side is slanted, the seam is not tangent.
- **The exact C4D Multifractal-off algorithm** is not documented. Quartz uses a ridged variant.
- **Regular Grid** (the cut-face grid) is skipped everywhere.

## 6. Sources

- Cube: https://help.maxon.net/c4d/en-us/Content/html/OCUBE-ID_OBJECTPROPERTIES.html
- Sphere: https://help.maxon.net/c4d/en-us/Content/html/OSPHERE-ID_OBJECTPROPERTIES.html and https://help.maxon.net/c4d/r21/us/html/OSPHERE-ID_OBJECTPROPERTIES.html
- Cylinder: https://help.maxon.net/c4d/en-us/Content/html/OCYLINDER-ID_OBJECTPROPERTIES.html, https://help.maxon.net/c4d/en-us/Content/html/OCYLINDER-ID_CYLINDERCAPS.html and https://help.maxon.net/c4d/en-us/Content/html/OCYLINDER-ID_SLICE.html
- Cone: https://help.maxon.net/c4d/en-us/Content/html/OCONE-ID_OBJECTPROPERTIES.html and https://help.maxon.net/c4d/en-us/Content/html/OCONE-ID_CONECAPS.html
- Tube: https://help.maxon.net/c4d/en-us/Content/html/OTUBE-ID_OBJECTPROPERTIES.html and https://help.maxon.net/c4d/en-us/Content/html/OTUBE-ID_SLICE.html
- Torus: https://help.maxon.net/c4d/en-us/Content/html/OTORUS-ID_OBJECTPROPERTIES.html and https://help.maxon.net/c4d/en-us/Content/html/OTORUS-ID_SLICE.html
- Plane, Disc, Pyramid: https://help.maxon.net/c4d/en-us/Content/html/OPLANE-ID_OBJECTPROPERTIES.html, https://help.maxon.net/c4d/en-us/Content/html/ODISC-ID_OBJECTPROPERTIES.html and https://help.maxon.net/c4d/en-us/Content/html/OPYRAMID-ID_OBJECTPROPERTIES.html
- Capsule and Oil Tank: https://help.maxon.net/c4d/en-us/Content/html/OCAPSULE-ID_OBJECTPROPERTIES.html, https://help.maxon.net/c4d/en-us/Content/html/OOILTANK-ID_OBJECTPROPERTIES.html, https://help.maxon.net/c4d/en-us/Content/html/OCAPSULE-ID_SLICE.html and https://help.maxon.net/c4d/en-us/Content/html/OOILTANK-ID_SLICE.html
- Platonic, Landscape, Bezier, Figure: https://help.maxon.net/c4d/en-us/Content/html/OPLATONIC-ID_OBJECTPROPERTIES.html, https://help.maxon.net/c4d/en-us/Content/html/OFRACTAL-ID_OBJECTPROPERTIES.html, https://help.maxon.net/c4d/en-us/Content/html/OBEZIER-ID_OBJECTPROPERTIES.html and https://help.maxon.net/c4d/en-us/Content/html/OFIGURE-ID_OBJECTPROPERTIES.html
- Polygon and Null: https://help.maxon.net/c4d/en-us/Content/html/OSINGLEPOLY-ID_OBJECTPROPERTIES.html and https://help.maxon.net/c4d/en-us/Content/html/ONULL-ID_OBJECTPROPERTIES.html
