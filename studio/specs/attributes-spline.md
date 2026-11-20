# Spline attributes: audit against Cinema 4D and build contract

Written on 20/11/2026 (night run, contract "attributes-spline"). Scope: every spline object registered by
`quartz_studio/objects/spline_shapes.py`, the Text Spline of `quartz_studio/objects/gen_spline.py` (spline
attributes only), and the editable Line that the Line pen creates. Sister contract: `specs/attributes-mesh.md`
(Attribute Manager simplification: tabs removed, rows only, collapsible sections). Where the two touch, this file
says so in section 7.

Code, interface text and docs stay in English. Code files carry no comments or docstrings. Every size in px
follows `D:\Markdown\DesignPx.md`. The window shows only controls that do something.

## 0. Sources and how much to trust them

- Maxon online help, Cinema 4D 2027 (help.maxon.net), pages `OSPLINE-ID_OBJECTPROPERTIES` (editable spline),
  `OSPLINERECTANGLE`, `OSPLINECIRCLE`, `OSPLINEARC`, `OSPLINENSIDE`, `OSPLINE4SIDE`, `OSPLINESTAR`,
  `OSPLINECOGWHEEL`, `OSPLINEPROFILE`, `OSPLINECISSOID`, `OSPLINECYCLOID`, `OSPLINEFORMULA`, `OSPLINEHELIX`,
  `OSPLINEFLOWER`, `OSPLINETEXT` (all `-ID_OBJECTPROPERTIES.html`). They give names, ranges and choices. They do
  not state defaults (except Interpolation = Adaptive).
- Defaults marked "(memory)" come from memory of the program, not from a page. They are never used to change a
  Quartz default tonight (see rule 1.1).
- Naming: the 2027 help renames "Intermediate Points" to "Interpolation", "None" to "Off", "Number" to "Points"
  and "Maximum Length" to "Max Length". Quartz uses the classic names, the ones the owner wrote.

## 1. Rules for every change in this file

1. Defaults reproduce today's result bit for bit. Every new key has a default that makes the build return exactly
   the mesh it returns today (same points in the same order, same edges). `fileio/fmt_quartz.py` lines 267 to 275
   load parametric objects with `specs[kind].clamp(raw)`, so a saved file without the new keys gets the defaults
   and opens the same. No existing default, key or choice spelling changes.
2. Before editing a build, the builder captures a golden: a script in
   `C:\Users\User\AppData\Local\Temp\qz\night\<builder key>\` writes `points` and `loose_edges` of every
   spline with defaults and with the variants listed in 5.1 to an `.npz` there. After the edit the same script
   compares with `np.array_equal` and must report no difference. The golden is not committed.
3. All existing tests keep passing unchanged (`tests/test_objects_spline_shapes.py`,
   `tests/test_objects_gen_spline.py`, the rest). New tests go in new files (section 6).
4. A degenerate parameter set returns `Mesh.empty()` (SPEC.md 7.2), never raises, except the Formula, which keeps
   raising `ValueError` for bad expressions.

## 2. How a spline is represented in Quartz, and what the common attributes map to

- A spline object is a parametric `SceneObject` whose build returns a `Mesh` with points and loose edges only
  (SPEC.md 7.2). `spline_shapes._finish` (lines 91 to 108) turns a list of `(points, closed)` chains into that
  mesh: `_clean` (lines 71 to 79) drops consecutive duplicates and turns a chain whose last point equals the first
  into a closed one, `reverse` flips each chain, `_to_space` (lines 82 to 88) maps the shape's `(u, v, w)` onto the
  plane, and a closed chain gets an edge from its last point to its first.
- A generator reads its spline children through `BuildInput.chains()` (`objects/registry.py` lines 179 to 180),
  which calls `mesh_chains` (lines 122 to 162): polylines rebuilt from the loose edges, split at branch points.
  Nothing samples the curve again: Extrude (`gen_spline.build_extrude`), Lathe (`build_lathe`), Sweep
  (`build_sweep`) and Trunk (`gen_trunk.build_trunk`) use the chain points as they are, one ring or one row per
  point. Loft (`build_loft`) resamples each section to `subdivision_u` points with `_resample`, keeping the
  original points when there are fewer than that.
- Consequence: the curve is already a polyline when it leaves the spline. Cinema 4D keeps a curve with control
  points and samples it when a generator asks; Quartz samples inside the build. So the Cinema 4D "Intermediate
  Points" family becomes a choice of how the build samples, and its result is what every generator sees. That
  is why it is worth adding: it sets the density of Extrude, Lathe, Sweep and Trunk results.
- Plane (`plane`, choices `PLANES = ("XY", "ZY", "XZ")`, default `"XY"`) and Reverse (`reverse`, bool, `False`)
  exist on every shape today (`_tail`, lines 22 to 30) and match Cinema 4D. Keep them.
- Today the curved shapes have one sampling key, `points_per_90` ("Points per 90 degrees", int, default 8,
  1 to 64): the number of edges per 90 degrees of the shape's own parameter (`_seg`, line 53). It is pinned by
  `test_sampling_parameter_is_clamped`. It stays, with the same key, default, range and meaning in Natural mode,
  and is relabelled "Number".

### 2.1 The new common attributes

| Cinema 4D | Type | C4D default | C4D range | Quartz today | Decision |
|---|---|---|---|---|---|
| Plane | choice XY, ZY, XZ | XY (memory) | | `plane`, "Plane", same | keep |
| Reverse | bool | off (memory) | | `reverse`, "Reverse", same | keep |
| Intermediate Points | choice None, Natural, Uniform, Adaptive, Subdivided | Adaptive | | missing | add `intermediate` (2.2) |
| Number | int | 8 (memory) | 0 to 5000 | `points_per_90` on 7 curved shapes, 1 to 64 | keep key, relabel "Number", add to the linear shapes; range stays 1 to 64 (pinned by a test) |
| Angle | angle | 5 degrees (memory) | 0 to 90 | missing | add `adaptive_angle` |
| Maximum Length | distance | 5 cm (memory, unsure) | 0 to infinity | missing | add `max_length` |

Cinema 4D's default is Adaptive. Quartz keeps Natural (curved shapes) and None (linear shapes) as defaults,
because they are today's result (rule 1.1). Switching the default to Adaptive is a later decision for the owner;
it would change every point count and several pinned tests.

### 2.2 Exact parameters

Three tails replace `_tail(curved)`. `_tail` keeps its name and takes a string `kind`:

- `_tail("curved")`: shapes that have curves at their defaults or after a toggle: Rectangle, Circle, Arc, n-Side,
  Cissoid, Cycloid, Flower.
- `_tail("linear")`: shapes made of straight segments only: 4-Side, Star, Cogwheel, Profile.
- `_tail("none")`: Formula and Helix (their own Samples and Subdivision are the sampling; see 3.11 and 3.12).

Rows, in this order, all `group="Object"`:

| key | label | kind | default | min | max | step | unit | choices | tails |
|---|---|---|---|---|---|---|---|---|---|
| `plane` | Plane | choice | `"XY"` | | | | | `PLANES` | all |
| `reverse` | Reverse | bool | `False` | | | | | | all |
| `intermediate` | Intermediate Points | choice | `"Natural"` (curved), `"None"` (linear) | | | | | `CURVED_SAMPLING = ("None", "Natural", "Uniform", "Adaptive", "Subdivided")`; `LINEAR_SAMPLING = ("None", "Uniform", "Subdivided")` | curved, linear |
| `points_per_90` | Number | int | 8 | 1 | 64 | 1 | | | curved, linear |
| `adaptive_angle` | Angle | angle | 5.0 | 0.1 | 90.0 | 1.0 | degrees | | curved |
| `max_length` | Maximum Length | distance | 20.0 | 0.1 | none | 1.0 | cm | | curved, linear |

- The linear shapes get only three choices: on straight segments None, Natural and Adaptive all give the corners
  only, so offering them would show options that do nothing.
- `max_length` default 20 cm and not Cinema 4D's 5 cm: the Quartz default shapes are 400 cm across, so 5 cm would
  give 320 points on a default Rectangle. Range minimum 0.1 cm.
- `adaptive_angle` minimum 0.1 (Cinema 4D allows 0, which would keep every dense sample).
- Key names avoid `angle`, which the 4-Side already uses for its shape angle. The 4-Side therefore has no
  `adaptive_angle` (it is linear) and no label clash.
- New module constants in `spline_shapes.py`: `CURVED_SAMPLING`, `LINEAR_SAMPLING`, `DENSE_SAMPLES = 256`,
  `CORNER_TURN = 45.0` (degrees), `MAX_SUBDIVIDED_POINTS = 20000`.

### 2.3 What each mode does (construction)

Every chain function changes from `_x_chains(p)` to `_x_chains(p, s)` where `s` is the sampling (edges per 90
degrees of the shape's parameter; it replaces every read of `p["points_per_90"]` inside the function), and returns
`(points, closed, knots)` where `knots` is a bool array, one per point, marking control points (table 2.4). One
wrapper does the rest:

```
mode = p.get("intermediate", default of the tail)
None        -> chains = fn(p, 1)
Natural     -> chains = fn(p, p["points_per_90"])
Uniform, Adaptive, Subdivided -> chains = [resample(c) for c in fn(p, DENSE_SAMPLES)]
then _finish(chains, p)
```

Shapes of `_tail("none")` and linear shapes ignore `s`. With `mode` Natural (curved) or None (linear) the call is
exactly today's, so rule 1.1 holds by construction.

`_clean(pts, closed, knots)` keeps its job and also carries the knots: when a point is dropped as a duplicate of
the previous one, the previous one becomes a knot if either was; when the last point equals the first and is
popped, the first becomes a knot if either was. After cleaning, on the dense chain, every vertex whose turn angle
(angle between the incoming and outgoing segment) exceeds `CORNER_TURN` is also a knot, and the two ends of an
open chain are knots.

Pieces: a chain is cut at its knots into pieces (runs from one knot to the next). A closed chain with no knot is
one piece that starts and ends at index 0. A closed chain with knots is rotated to start at its first knot. For a
piece, `L` is its length along the dense polyline and `T` the sum, in degrees, of the turn angles at its interior
vertices (for a closed chain without knots, the turn at index 0 counts too, so a circle has `T = 360`).

- None: the shape is sampled with `s = 1`: one edge per 90 degrees of curve. Circle 4 points (a diamond, as
  Cinema 4D draws a circle with no intermediate points), rounded Rectangle 8, default Arc 2.
- Natural: today's result. `points_per_90` edges per 90 degrees of the shape's parameter (angle for circles, arcs
  and corners, phi for the Cycloid, t for the Flower and Cissoid family). Straight segments get no extra points.
- Uniform: every piece is divided into `m` edges of equal length along the dense polyline (positions by
  `np.interp` on the cumulative length), where `m = points_per_90` for a straight piece (`T < 1e-6`) and
  `m = max(1, round(points_per_90 * T / 90))` for a curved one. Knots are kept. A circle gives the same 32 points
  as Natural; an ellipse gives 32 points spaced by equal arc length; a Rectangle without rounding gives 8 edges per
  side.
- Adaptive: from the dense chain, per piece, keep the first knot, then every interior vertex `i` where
  `floor((cum_i + 1e-9) / adaptive_angle)` is larger than at the previous vertex (`cum_i` is the running sum of turn
  angles since the piece's first knot), then the closing knot. Vectorised with `np.cumsum`. Circle at 5 degrees:
  72 points (Cinema 4D gives 72 too); rounded Rectangle (default size, radius 50) at 5 degrees: 76 points.
- Subdivided: the Adaptive selection, then between every two consecutive kept points (cyclic for a closed chain)
  whose length along the dense polyline `D` exceeds `ml = max(max_length, total_chain_length /
  MAX_SUBDIVIDED_POINTS)`, insert `ceil(D / ml) - 1` points at equal lengths along the dense polyline. Straight
  sides are split on the line, curved stretches on the dense curve.

After the mode, `_clean` runs once more (defensive: very short pieces can produce coincident points), then
`reverse`, `_to_space` and the edges, exactly as `_finish` does today. A chain with fewer than 3 points (closed)
or 2 (open) is dropped as today.

Edge cases: `adaptive_angle >= 90` keeps only knots and 90 degree steps (circle: 4 points). `max_length` larger
than every gap gives the Adaptive result. A piece of zero length cannot exist after `_clean`. Reverse runs after
sampling, so Reverse plus Adaptive gives the reversed Adaptive chain (start point of a closed chain may differ from
Cinema 4D; not tested against it).

### 2.4 Knots per shape (dense build)

| Shape | Knots |
|---|---|
| Rectangle | no rounding: the 4 corners; rounding: the first and last point of each corner arc (`j * (seg + 1)` and `j * (seg + 1) + seg`) |
| Circle (and Ring) | none (each ring is one closed smooth piece) |
| Arc, type Arc | the two ends; a full sweep (`_sweep` returns `full`): none |
| Arc, Segment | the two ends of the chord |
| Arc, Sector | the centre and the two arc ends; full sweep: none |
| Arc, Ring | the outer ends and the inner ends (4 points); full sweep: none |
| n-Side | no rounding: every vertex; rounding: first and last point of each corner arc |
| 4-Side, Star, Cogwheel, Profile | every vertex |
| Cissoid, type Cissoid | the two ends (the cusp is caught by `CORNER_TURN`) |
| Cissoid, Lemniscate | none |
| Cissoid, Strophoid | index 0 (the node at the origin) |
| Cycloid | the two ends (cusps are caught by `CORNER_TURN`) |
| Flower | none |

## 3. Audit per object

Columns: Cinema 4D attribute, type, C4D default, C4D range; Quartz today (key, label; whether default and range
agree); decision. Rows of 2.2 are not repeated; each table says which tail the shape takes.

### 3.1 Rectangle (`id="rectangle"`, tail curved)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Width | distance | 400 cm (memory) | 0 to inf | `width`, "Width", 400, min 0 | keep |
| Height | distance | 400 cm (memory) | 0 to inf | `height`, "Height", 400, min 0 | keep |
| Rounding | bool | off | | `rounding`, "Rounding", False | keep |
| Radius | distance | 50 cm (memory) | 0 to inf | `radius`, "Radius", 50, min 0; clamped to half the shorter side in the build | keep |

Shown only when (rules for the Attribute Manager, section 4.2): `radius` when `rounding`.

### 3.2 Circle (`id="circle"`, tail curved)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Ellipse | bool | off | | `ellipse`, "Ellipse" | keep |
| Ring | bool | off | | `ring`, "Ring" | keep |
| Radius | distance | 200 cm (memory) | 0 to inf | `radius`, 200 | keep |
| Radius Y | distance | 200 cm (memory) | 0 to inf | `radius_y`, "Radius Y", 200 | keep |
| Inner Radius | distance | 100 cm (memory) | 0 to inf | `inner_radius`, 100 | keep |

Shown only when: `radius_y` when `ellipse`; `inner_radius` when `ring` (both exist today in `PARAM_APPLIES`).

### 3.3 Arc (`id="arc"`, tail curved)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Type | choice Arc, Sector, Segment, Ring | Arc | | `type`, `ARC_TYPES`, "Arc" | keep |
| Radius | distance | 200 cm (memory) | 0 to inf | `radius`, 200 | keep |
| Inner Radius | distance | 100 cm (memory) | 0 to inf | `inner_radius`, 100 | fix visibility: shown only when `type == "Ring"` (today it is always shown and does nothing for the other types) |
| Start Angle | angle | 0 | -360 to 360 | `start_angle`, 0, no bounds | skip the range: Quartz accepts any angle and `test_arc_full_ring_is_two_closed_circles` builds 720 degrees |
| End Angle | angle | 90 | -360 to 360 | `end_angle`, 90, no bounds | skip the range (same reason) |

### 3.4 n-Side (`id="n_side"`, tail curved)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Radius | distance | 200 cm (memory) | 0 to inf | `radius`, 200 | keep |
| Sides | int | 6 (memory) | 2 to 2147483647 | `sides`, 3 to 1000 | skip minimum 2: a 2-point closed chain is dropped by `_finish` (fewer than 3 points), so 2 would give an empty object |
| Rounding | bool | off | | `rounding` | keep |
| Radius (rounding) | distance | 50 cm (memory) | 0 to inf | `rounding_radius`, "Radius", 50 | keep; shown only when `rounding` (exists) |

### 3.5 4-Side (`id="four_side"`, tail linear)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Type | choice Diamond, Kite, Parallelogram, Trapezium | Diamond (memory) | | `type`, `FOUR_SIDE_TYPES` | keep |
| a | distance | not certain | 0 to inf | `a`, label "A", 400 | fix label to "a" |
| b | distance | not certain | 0 to inf | `b`, label "B", 200 | fix label to "b" |
| Angle | angle | 30 (memory) | -90 to 90 | `angle`, 30, no bounds; clamped inside the build (Kite 1 to 179, Parallelogram via `tan`, Trapezium 1 to 89) | fix visibility: shown only when `type != "Diamond"` (the Diamond ignores it, line 224); skip the range (the Kite uses up to 179 today) |

### 3.6 Star (`id="star"`, tail linear)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Inner Radius | distance | 100 cm (memory) | 0 to inf | `inner_radius`, 100 | keep |
| Outer Radius | distance | 200 cm (memory) | 0 to inf | `outer_radius`, 200 | keep |
| Twist | percent | 0 % | -100 to 100 % | `twist`, angle, 0 | skip: Quartz turns the inner points by an angle in degrees; the help does not define what 100 % means, and converting would change saved files with a non-zero twist |
| Points | int | 8 (memory) | 3 to 1000000 | `points`, 3 to 1000 | keep |

### 3.7 Cogwheel (`id="cogwheel"`, tail linear)

Cinema 4D's Cogwheel since R16 is an involute gear with many parameters (tooth types, regions, hub, holes); the
fetched page lists the Legacy Mode set only: Legacy Mode, Show Guides, Guide Color, Teeth (5 to 2147483647),
Inner Radius, Middle Radius, Outer Radius, Bevel (0 to 100 %).

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Teeth | int | not certain | 5 to inf | `teeth`, 12, 3 to 1000 | keep |
| Inner Radius | distance | not certain | 0 to inf | `root_radius`, "Root Radius", 150 | keep (the help calls it the Root Radius too) |
| Middle Radius | distance | not certain | 0 to inf | missing | skip tonight: it changes the tooth profile; with the involute gear, later |
| Outer Radius | distance | not certain | 0 to inf | `addendum_radius`, "Addendum Radius", 200 | keep |
| Bevel | percent | not certain | 0 to 100 | `bevel`, 0 | keep |
| (none) | | | | `tooth_width`, "Tooth Width", 50 % | keep (Quartz only) |
| Legacy Mode, Show Guides, Guide Color | bool, bool, colour | | | missing | skip: Quartz has only one model, and guides are viewport drawing |
| Involute gear set, Regions, Hub, Holes | | | | missing | later, one task of its own |

### 3.8 Profile (`id="profile"`, tail linear)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Type | choice H, L, T, U, Z Shape | H-Shape (memory) | | `type`, `PROFILE_TYPES` | keep |
| Height | distance | 200 cm (memory) | 0 to inf | `height`, 200 | keep |
| b | distance | 100 cm (memory) | 0 to inf | `b`, "B", 100 | fix label to "b" |
| s | distance | 20 cm (memory) | 0 to inf | `s`, "S", 20 | fix label to "s" |
| t | distance | 20 cm (memory) | 0 to inf | `t`, "T", 20 | fix label to "t" |

### 3.9 Cissoid (`id="cissoid"`, tail curved)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Type | choice Cissoid, Lemniscate, Strophoid | Cissoid | | `type`, `CISSOID_TYPES` | keep |
| Width | distance | not certain | 0 to inf | `width`, 400 | keep |
| Tension | float | not certain | 1.5 to 100 | `tension`, 6.0, 0 to 60 | fix maximum to 100.0; keep minimum 0 (`test_cissoid_zero_tension_is_empty` pins 0 as empty); fix visibility: shown only when `type == "Cissoid"` (Quartz's Strophoid and Lemniscate ignore it; Cinema 4D's Strophoid uses it: later) |

### 3.10 Cycloid (`id="cycloid"`, tail curved)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Type | choice Cycloid, Epicycloid, Hypocycloid | Cycloid | | `type` | keep |
| Radius | distance | not certain | 0 to inf | `radius`, 100 | keep |
| r | distance | not certain | 0 to inf | `r`, 40 | keep |
| a | distance | not certain | 0 to inf | `a`, 40 | keep |
| Start Angle | angle | 0 (memory) | any | `start_angle`, 0 | keep |
| End Angle | angle | not certain | any | `end_angle`, 720 | keep |

### 3.11 Formula (`id="formula"`, tail none)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| X(t) | text | `100.0*t` (memory) | | `x_expr`, same | keep |
| Y(t) | text | `100.0*Sin(t*PI)` (memory) | | `y_expr`, `100.0*sin(t*pi)` | keep (Quartz names are lower case, `_FUNCTIONS`) |
| Z(t) | text | `0.0` | | `z_expr` | keep |
| Tmin | float | -1 | any | `tmin`, -1 | keep |
| Tmax | float | 1 | any | `tmax`, 1 | keep |
| Samples | int | 20 (memory) | 2 to inf | `samples`, 20, 2 to 5000; Quartz makes `samples` points, C4D makes `samples + 1` | skip the off-by-one: changing it would change every saved Formula and `test_formula_defaults_are_open_sine` |
| Cubic Interpolation | bool | not certain | | missing | skip: Quartz evaluates the expression exactly at every sample; raise Samples instead |
| Intermediate Points family | | | | missing | skip: the Samples are the sampling; interpolating between exact samples adds nothing |

### 3.12 Helix (`id="helix"`, tail none)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Start Radius | distance | 200 cm (memory) | 0 to inf | `start_radius`, 200 | keep |
| End Radius | distance | 200 cm (memory) | 0 to inf | `end_radius`, 200 | keep |
| Start Angle | angle | 0 | any | `start_angle`, 0 | keep |
| End Angle | angle | 720 (memory) | any | `end_angle`, 720 | keep |
| Radial Bias | percent | 50 % (memory) | 0 to 100 | missing | add (below) |
| Height | distance | 200 cm (memory) | 0 to inf | `height`, 200, no bounds | keep (negative heights are harmless) |
| Height Bias | percent | 50 % (memory) | 0 to 100 | missing | add (below) |
| Subdivision | int | 100 (memory) | 3 to inf | `subdivision`, 100, 1 to 5000 | keep |
| Intermediate Points family | | | | missing | skip: Subdivision is the sampling |

Add, between `height` and `subdivision`, in this order:

| key | label | kind | default | min | max | step | unit |
|---|---|---|---|---|---|---|---|
| `radial_bias` | Radial Bias | percent | 50.0 | 0.0 | 100.0 | 1.0 | % |
| `height_bias` | Height Bias | percent | 50.0 | 0.0 | 100.0 | 1.0 | % |

Construction in `_helix_chains`: `u = np.linspace(0.0, 1.0, n + 1)`; `bias(u, b) = u ** (log(c) / log(0.5))` with
`c = min(max(b / 100.0, 0.001), 0.999)`, so the progression has reached `c` of the way at the middle of the helix
(above 50 % it reaches the final value faster). Radius: when `radial_bias == 50.0` keep today's
`np.linspace(r0, r1, n + 1)` exactly; otherwise `r0 + (r1 - r0) * bias(u, radial_bias)`. Height: when
`height_bias == 50.0` keep today's `np.linspace(0.0, height, n + 1)`; otherwise `height * bias(u, height_bias)`.
The special case matters: a probe on 20/11/2026 showed `0.0 + 200.0 * u` is not bit-equal to
`np.linspace(0.0, 200.0, 101)`. Ends: the first and last point keep today's values for every bias (bias(0) = 0,
bias(1) = 1).

### 3.13 Flower (`id="flower"`, tail curved)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Inner Radius | distance | 100 cm (memory) | 0 to inf | `inner_radius`, 100 | keep |
| Outer Radius | distance | 200 cm (memory) | 0 to inf | `outer_radius`, 200 | keep |
| Petals | int | 8 (memory) | 3 to inf | `petals`, 8, 1 to 100 | skip: 1 and 2 petals build valid shapes, narrowing would reopen saved files differently; maximum stays 100 (the dense build is `4 * 256 * petals` points) |

### 3.14 Text Spline (`id="text_spline"`, `gen_spline.py`)

| C4D | Type | Default | Range | Quartz today | Decision |
|---|---|---|---|---|---|
| Text | multi-line text | `Text` (memory) | | `text`, "Text", kind text; edited in a one-line `QLineEdit`, so a second line cannot be typed although `text_chains` supports `\n` | keep the key; the Attribute Manager shows a multi-line editor for it (row kind 4.1, item 3) |
| Font | font chooser | system font | installed fonts | `font`, "Font", text, `"Arial"` | keep the key and kind `text`; the Attribute Manager shows a font chooser for it (4.1, item 2) |
| (font style, part of C4D's font chooser) | choice | Regular | family's styles | missing | add `font_style` (below) |
| Align | choice | Left | Left, Centered, Right | `align`, `ALIGNS = ("Left", "Middle", "Right")` | keep "Middle" (pinned by `test_objects_gen_spline.py` line 141, and saved files) |
| Height | distance | 200 cm (memory) | any | `height`, 200, min 0 | keep |
| Horizontal Spacing | distance | 0 | any | `horizontal_spacing`, 0 | keep |
| Vertical Spacing | distance | 0 | any | `vertical_spacing`, 0 | keep |
| Separate Letters | bool | off | | missing | later: needs Make Editable to create one child Line per letter |
| Kerning | per letter | | | missing | skip: needs interactive per-letter handles |
| Plane | choice | XY | | missing | add `plane` (text_spline only) |
| Reverse | bool | off | | missing | add `reverse` (text_spline only) |
| Intermediate Points family | | Adaptive | | missing | skip: Qt flattens the glyph curves (`QPainterPath.toSubpathPolygons`, line 787) with its own tolerance; sampling them ourselves from the path elements is later |

`_text_params()` gains `Param("font_style", "Font Style", "choice", "Regular", choices=FONT_STYLES,
group="Object")` right after `font`, with `FONT_STYLES = ("Regular", "Bold", "Italic", "Bold Italic")`. In
`text_chains`, after `font = QFont(...)`: Bold and Bold Italic call `font.setBold(True)`; Italic and Bold Italic
call `font.setItalic(True)`; Regular calls neither (so the default is today's font object). Both Text Spline and
the extruded Text get it, since they share `_text_params()`.

`text_spline` params become `_text_params() + (plane, reverse)` with the same `Param` definitions as the shapes
(`plane` choice `PLANES`, default `"XY"`; `reverse` bool `False`). `build_text_spline` reverses each ring
(`ring[::-1]`) when `reverse` is on, maps the stacked points with `spline_shapes._to_space(points, plane)`, then
builds the edges exactly as today. With XY and no reverse the result is today's. The extruded `text` object does
not get `plane` or `reverse`.

The owner asked for "options to change the Caps" of Text. On the extruded Text (and Extrude) that is the Caps
group: Start Cap and End Cap (exist in `build_extrude` as `start_cap` and `end_cap`; the `text` object always caps
both ends today). That belongs to the mesh objects and is left to `specs/attributes-mesh.md`. If the owner meant
letter case, there is no Cinema 4D attribute for it; not added (see section 8).

## 4. Requests to the Attribute Manager builder

### 4.1 Row kinds

1. Existing kinds cover every spline row: bool, choice, int, distance, angle, percent, float, text
   (`ParamEditor`, `widgets/attribute_manager.py` lines 206 to 284). Nothing new is needed for the shapes.
2. Font chooser: for a param with `kind == "text"` and `key == "font"`, a `QFontComboBox` (editable, so a family
   that is not installed still shows as text). Choosing a family emits `edited(key, family_name)`. Same row height
   as the other rows (`theme.ROW_H`).
3. Multi-line text: for a param with `kind == "text"` and `key == "text"` on the specs `text_spline` and `text`, a
   `QPlainTextEdit` of height 72 px (3 x `theme.ROW_H`, 72 is in the owner's px list) that emits `edited(key,
   text)` on focus out and on Ctrl+Enter, not on every key press (each emission rebuilds the object).
4. Line rows: when the target is an editable object with `registry.mesh_is_spline(obj.mesh)`, the manager shows
   the rows of `quartz_studio.objects.line_attrs.LINE_PARAMS` (section 5) with the normal `ParamEditor`s, values
   from `line_attrs.line_values(scene, obj)`, visibility from `line_attrs.line_applies(scene, obj, key)` and edits
   sent to `line_attrs.set_line_value(scene, obj, key, value)`. Refresh them on `Scene.changed`,
   `selectionChanged` and `modeChanged`. A Line with no applicable row shows no rows at all.
5. Optional, nice to have: a mixed-value state on a percent row (for Point Thickness when the selected points
   differ). Without it, the row shows the value of the lowest selected index (5.2).

### 4.2 Visibility rules (`PARAM_APPLIES`)

Add these helpers next to `_on` and `_is` (lines 75 to 80): `_not(key, *values)` (value not in values),
`_all(*rules)`, `_any(*rules)`. Then the entries below replace or join the existing spline entries of
`PARAM_APPLIES` (lines 83 to 96). `S = "intermediate"`.

| spec | key | shown when |
|---|---|---|
| rectangle | `radius` | `_on("rounding")` |
| rectangle, n_side | `points_per_90` | `_any(_is(S, "Uniform"), _all(_on("rounding"), _is(S, "Natural")))` |
| rectangle, n_side | `adaptive_angle` | `_all(_on("rounding"), _is(S, "Adaptive", "Subdivided"))` |
| rectangle, n_side, circle, arc, cissoid, cycloid, flower, four_side, star, cogwheel, profile | `max_length` | `_is(S, "Subdivided")` |
| n_side | `rounding_radius` | `_on("rounding")` |
| circle | `radius_y` | `_on("ellipse")` |
| circle | `inner_radius` | `_on("ring")` |
| circle, arc, cissoid, cycloid, flower | `points_per_90` | `_is(S, "Natural", "Uniform")` |
| circle, arc, cissoid, cycloid, flower | `adaptive_angle` | `_is(S, "Adaptive", "Subdivided")` |
| arc | `inner_radius` | `_is("type", "Ring")` |
| cissoid | `tension` | `_is("type", "Cissoid")` |
| four_side | `angle` | `_not("type", "Diamond")` |
| four_side, star, cogwheel, profile | `points_per_90` | `_is(S, "Uniform")` |

`param_applies` merges `spec.defaults()` with `obj.params` before calling a rule (line 721), so an object saved
before tonight gets the default `intermediate` and the rules work. While the shapes builder has not landed, the
key is missing from the defaults and the Number row of Rectangle and n-Side is hidden; that is acceptable during
the parallel build and correct after integration.

## 5. The Line object

### 5.1 What it is today

The Line pen (`scene.tool == "line_pen"`) creates an editable object named "Line" (`Scene.new_line_object`,
`scene.py` line 631) whose mesh has points and loose edges only: `pen_add_point` and `_pen_extend` (lines 1343 to
1397) add a point and an edge to the previous one; `pen_close` (line 1371) adds the edge from the last point to the
first. The kind is `"polygon"`, so it has no spec and no params; `Scene.set_param` refuses it. It can branch (the pen
can link to an existing point) and it carries the Trunk thickness channel `Mesh.point_scales` (SPEC.md 10.2).
Generators read it through `mesh_chains` like any spline.

### 5.2 Attributes tonight (smallest step that makes a Line well modifiable)

New module `quartz_studio/objects/line_attrs.py` (not auto-imported: its name does not start with `prim_`,
`spline_` or `gen_`). Public API, exactly:

- `LINE_PARAMS` (tuple of `objects.registry.Param`, `group="Object"`):

| key | label | kind | default | min | max | step | unit |
|---|---|---|---|---|---|---|---|
| `closed` | Close Spline | bool | False | | | | |
| `point_thickness` | Point Thickness | percent | 100.0 | 0.0 | 10000.0 | 1.0 | % |

- `is_line(obj) -> bool`: `obj.kind == "polygon"` and `mesh_is_spline(obj.mesh)`.
- `line_is_simple(mesh) -> bool`: `mesh_chains(mesh)` returns exactly one chain, every point used by a loose edge
  has valence 1 or 2 among the loose edges, and the chain has at least 3 points.
- `line_values(scene, obj) -> dict`: `{"closed": <the single chain is closed, False when not simple>,
  "point_thickness": 100 * scale of the lowest selected point index, 100.0 when nothing is selected}`.
- `line_applies(scene, obj, key) -> bool`: `closed` when `is_line(obj)` and `line_is_simple(obj.mesh)`;
  `point_thickness` when `is_line(obj)`, `scene.active is obj`, `scene.mode == "points"` and
  `scene.selected_points` is not empty. Unknown key: `False`.
- `set_line_closed(scene, obj, flag) -> bool`: only for a simple Line of the scene, else `False`; `False` when the
  state already matches. Closing adds the loose edge between the two ends (the two points of valence 1). Opening
  removes the edge of the cycle with the largest index difference `abs(a - b)` (the pen's closing edge from the last
  point to the first), ties broken by the lowest `(min, max)` pair. Records one undo step with
  `scene._record(f"line:{id(obj)}")` (the same private call `modeling/session.py` line 69 uses), replaces
  `obj.mesh` with `Mesh(points, polygons, new_loose_edges, point_scales=old.point_scales)` (the point count does not
  change, so the channel survives), then emits `scene.changed`.
- `set_line_value(scene, obj, key, value) -> bool`: `closed` calls `set_line_closed(scene, obj, bool(value))`;
  `point_thickness` calls `scene.set_point_scales(sorted(scene.selected_points), clamp(value) / 100.0, obj)`
  (existing API, SPEC.md 10.2: undo kind `"scales:<id>"`, drags coalesce). Unknown key: `KeyError`.

Edge cases: a Line with fewer than 3 points, a branching Line or several pieces shows no Close Spline row. An open
Line closed then opened again is the original mesh (same edge list content). Undo after closing restores the open
Line. Point Thickness on a Line under a Trunk generator rebuilds the generator (SPEC.md 10.4); on a Line without
one it changes only the saved channel, which the Trunk tool and generator read later.

### 5.3 What needs a real spline type (later)

- Type (Linear, Cubic, Akima, B-Spline, Bezier) with tangents, and Intermediate Points on a Line: the Line would
  have to keep control points (and two tangents per point for Bezier) separate from the polyline that is drawn and
  fed to generators. That needs a new editable kind (for example `"spline"`) that `Scene.is_editable` accepts,
  component editing on the control points while the evaluated polyline is drawn, tangent handles in the viewport
  and a tangent drag in the pen, storage in `fmt_quartz`, Make Editable of a spline primitive into that kind instead
  of a point Line, and generators reading the evaluated mesh. Several files of other owners (`scene.py`,
  `widgets/viewport.py`, `fileio/fmt_quartz.py`). Not tonight.
- Point count as a row: information, not a control; left out.

## 6. Tests that must exist

All new files, offscreen, runnable as scripts like the existing ones (`_run_as_script`).

### 6.1 `tests/test_spline_intermediate.py` (shapes builder)

1. Every curved shape has `intermediate` with `CURVED_SAMPLING`, default `"Natural"`, and `adaptive_angle` (5.0,
   0.1 to 90) and `max_length` (20.0, min 0.1); every linear shape has `LINEAR_SAMPLING`, default `"None"`,
   `points_per_90` and `max_length`, no `adaptive_angle`; Formula and Helix have none of the three.
2. Defaults unchanged: for every spline, `build(defaults)` equals `build(clamp(old))` where `old` is the defaults
   without the new keys (`np.array_equal` on points, equal loose edges), and the point counts are those of today:
   rectangle 4, circle 32, arc 9, n_side 6, four_side 4, star 16, cogwheel 36, profile 12, cissoid 9, cycloid 65,
   formula 20, helix 101, flower 256 (measured on 20/11/2026).
3. Natural with explicit `intermediate="Natural"` equals the default build for every curved shape and for these
   variants: rectangle rounding, circle ellipse and ring, arc of every type at 30 to 300 degrees, n_side rounding,
   cissoid of every type, cycloid of every type, flower 3 petals (the golden variants of rule 1.2).
4. None: circle 4 points, rounded rectangle 8, default arc 2, flower 32 (4 x 8 petals).
5. Uniform: circle 32 points equal to the Natural circle (`np.allclose`, atol 1e-6); rectangle without rounding 32
   points with 8 equal edges per side; rounded rectangle 64 points; ellipse (300 x 150, Number 4) 16 points whose
   edge lengths have max/min below 1.05; star 128 points.
6. Adaptive: circle at 5 degrees 72 points, at 90 degrees 4; rounded rectangle (default size, radius 50) at 5
   degrees 76 points; every knot of the Natural build is a point of the Adaptive build (corners of the 4-Side,
   arc ends); at every output point that is not a knot, the turn angle between its two edges is at most
   `adaptive_angle + 0.5` degrees.
7. Subdivided: rectangle 400 x 400 with `max_length` 20 gives 80 points and every edge at most 20 + 1e-9; circle
   with `max_length` 20 gives 72 points, with 10 gives 144; a star with `max_length` 5 has every edge at most 5 +
   1e-9 and keeps all 16 corners; `max_length` 0.1 on a rectangle of 10000 x 10000 stays at most
   `MAX_SUBDIVIDED_POINTS` points per chain.
8. Every mode of every shape passes the `check` of `test_objects_spline_shapes.py` (no duplicate points, no
   zero-length edge, every point used, one chain except the circle ring and the full arc ring) for every plane and
   with reverse on.
9. Generators see the density: an Extrude over a circle with Adaptive 5 degrees has 72 x 2 points.
10. Speed: flower with 100 petals in Adaptive builds in under 1.0 s.
11. Helix bias: defaults equal today (`np.array_equal`); radial bias 75 puts the middle point's radius past the
    midpoint between start and end radius (with start 50, end 200); height bias 25 puts the middle point below half
    the height; first and last points unchanged for bias 0, 25, 75 and 100.
12. Cissoid tension clamps at 100; 4-Side labels "a" and "b"; Profile labels "b", "s", "t".
13. A `.quartz` document written with a rectangle and a helix whose params lack the new keys (write the JSON by
    hand in a temp folder) opens with the same meshes as the in-memory defaults.

### 6.2 `tests/test_text_spline_attrs.py` (text builder)

1. `font_style` default "Regular" on `text_spline` and `text`; Regular equals today (build with and without the
   key, `np.array_equal`).
2. Bold changes the outline (point arrays differ) and makes the bounding box of "Text" wider; Italic changes it
   too.
3. `text_spline` has `plane` and `reverse`; XY and no reverse equal today; ZY puts every point at x = 0 within 1e-9;
   XZ at y = 0; reverse keeps the ring count and reverses each ring's order.
4. `text` (mesh) has no `plane` and no `reverse`.

### 6.3 `tests/test_line_attrs.py` (line builder)

1. `is_line` true for a pen Line, false for the Cube and for a parametric Circle.
2. Close Spline: an open 4-point Line closes (one closed chain), undo reopens it, opening a closed pen Line removes
   the edge between the first and the last point and the result equals the open Line; a branching Line and a
   2-point Line report `line_applies(..., "closed") == False` and `set_line_closed` returns False.
3. Closing keeps `point_scales`.
4. Point Thickness: shown only in Points mode with a selection; setting 50 on two selected points stores 0.5 on
   both and leaves the others at 1.0; one undo step; a Trunk generator above the Line rebuilds (its mesh changes).
5. Line with the pen through the scene API (`scene.set_tool("line_pen")`, `pen_add_point` x 3, `pen_close`) then
   `line_values` gives `closed` True.

### 6.4 Attribute Manager tests (owned by the Attribute Manager builder)

1. The visibility table of 4.2, one assertion per row, on a live `AttributeManager` (switch the controlling value
   and check `param_applies`).
2. The font row is a `QFontComboBox` for `text_spline` and `text`; choosing a family sets `params["font"]`.
3. The text row is multi-line; a two-line text builds two rows of glyphs.
4. A pen Line shows Close Spline; toggling it closes the Line; Point Thickness appears after selecting points in
   Points mode.

## 7. File ownership

| Owner | Files |
|---|---|
| builder "shapes" | `quartz_studio/objects/spline_shapes.py`, `tests/test_spline_intermediate.py` (new) |
| builder "text" | `quartz_studio/objects/gen_spline.py` (only `_text_params`, `text_chains`, `build_text_spline`, the two text registrations and the new `FONT_STYLES`), `tests/test_text_spline_attrs.py` (new) |
| builder "line" | `quartz_studio/objects/line_attrs.py` (new), `tests/test_line_attrs.py` (new) |
| the Attribute Manager builder of `specs/attributes-mesh.md` | `quartz_studio/widgets/attribute_manager.py` (section 4: row kinds 4.1, rules 4.2), its tests (6.4) |
| integration (after the builders) | the full test run; `tests/test_objects_ui.py` and other shared tests if a pinned list changes; `README.md`; SPEC.md section 7 (one paragraph: the sampling tails and `line_attrs`); a check that the golden comparison of rule 1.2 was run |

Notes:

- No file has two owners. `objects/registry.py`, `scene.py`, `theme.py`, `icons.py`, `main_window.py`,
  `widgets/viewport.py`, `widgets/menus_data.py`, `widgets/menu_bar.py` and `fileio/*` are not touched by this
  contract.
- Dependencies between builders, all on names that exist today: "text" imports `PLANES` and `_to_space` from
  `spline_shapes.py`, so "shapes" keeps both names and the signature `_to_space(uvw, plane)`. "line" imports
  `mesh_chains`, `mesh_is_spline` and `Param` from `objects/registry.py` and calls `Scene.set_point_scales` and
  `Scene._record`. The Attribute Manager imports `line_attrs`; until "line" lands, it guards the import
  (`ImportError` gives no Line rows) or waits for integration.
- `gen_spline.py` also holds the extruded `text` object and Extrude. If `specs/attributes-mesh.md` gives that file
  to another builder (for example for the Caps of Text), the orchestrator must give `gen_spline.py` to one builder
  only, who then implements both specs' rows for it.
- "shapes" is the largest job (every chain function gets `s` and knots, the wrapper, three tails, helix bias). If
  the orchestrator wants four builders, split nothing out of `spline_shapes.py`; give "text" and "line" to one
  builder instead.

## 8. Not determined

- Cinema 4D defaults are not stated by the help; those marked "(memory)" or "not certain" were not verified,
  notably Maximum Length (5 cm?), the 4-Side a and b, the Cogwheel, Cissoid and Cycloid values, and whether Natural
  adds points on straight segments in Cinema 4D (Quartz: it does not).
- The exact meaning of Cinema 4D's Star Twist percent and of its Strophoid Tension: not documented, so not copied.
- The owner's "Caps" for Text: read as the Caps group of the extruded Text (attributes-mesh); if it meant letter
  case, nothing was planned.
- The modern involute Cogwheel parameter list (the fetched page showed only the legacy set).
- Whether `specs/attributes-mesh.md` keeps the group header "Object" visible once tabs are removed; every row
  here stays in group "Object", so either choice works.
