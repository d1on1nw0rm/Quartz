# Viewport layers, colour providers and extension object kinds

Contract for two requests from the extension session (materials, uv, sculpt, rig, anim, render):
(A) a drawing hook in the viewport, so extensions can show material colour and texture, the sculpt
mask, skin weights and joints without child widgets or event filters; (B) the Create menu and the
object dock must take the object kinds that extensions register (`joint` from `quartz_studio/rig/joints.py`
line 87, `light` and `camera` from `quartz_studio/render/objects.py` lines 154-161, all
`category="null"`), and must ignore an unknown kind quietly.

All line numbers refer to the files as read on 2026-11-20. Code lives in `widgets/viewport.py`
(class `ViewportCanvas`), `widgets/menu_bar.py`, `widgets/object_palette.py`, `app.py`. New public
names are listed in section 9 and must also be added to `specs/hooks.md` as section 6 and 7 by the
builder.

## 1. Today

### 1.1 Paint path of `ViewportCanvas`
- `paintEvent` (1287-1304): background, horizon, `_paint_scene`, `_paint_tool_gizmo`, `_paint_pen`,
  `_paint_pivot`, `_paint_texts`, `_paint_gizmo` (navigation triad). One `QPainter`, antialiased,
  clipped to the rounded inner rect.
- `_paint_scene` (1478-1550) is a painter's algorithm, no depth buffer:
  - per rendered object `_object_view(obj)` (945-979) projects all points once
    (`view.world`, `view.cam`, `view.screen`, `view.in_front`, `view.normals`, `view.front`,
    `view.shown`, `view.edge_faces`) and memoises screen polygons per frame in `view.polys`
    via `_poly_screen(view, k)` (981-995; near-clipped, depth = mean camera z of the corners).
  - back faces of closed meshes are skipped (`hide_back`, 1502-1506); open meshes use the max corner
    depth (1510-1511).
  - fill colour: `self._shade(lam)` (1313-1319), a grey from the Lambert term of `_light_dir()`
    (1340-1343); back faces get `-(n.l) * 0.55` (1513).
  - items are tuples `(depth, seq, payload)` with payload kinds `"poly"` (1514), `"selected"`
    (1515-1519, `theme.SELECT_FRONT` / `SELECT_BACK` at alpha 100 plus a 2 px pen), `"line"`
    (N-gon guides 1520-1523), polylines from `_loose_edge_items`, `_null_items`, `_world_axis_items`.
  - one sort, back to front: `items.sort(key=lambda it: (-it[0], it[1]))` (1531); draw loop 1532-1548;
    polygon outline is `theme.POLY_OUTLINE` 1 px (1481).
  - `_paint_overlays(p, active_view)` (1669-) draws points, edges, selection outline of the active object
    on top, using `_visible_edge_lines` / `_sight_clear` for occlusion.
- Caches: `_tri_cache`, `_mesh_tri_cache`, `_guide_cache`, `_sight_cache` (710-713). The occlusion
  cache `_sight_cache` is keyed by `_scene_signature()` (1354-1357: camera state plus every rendered
  object's world points and polygon tuple) plus the query points, so it invalidates itself on any
  geometry or camera change and never depends on colours. `view.polys` lives one frame only.
- Projection helpers already public: `project(pts) -> (xy, z)` (794), `project_world(pts) -> xy` with
  NaN behind the near plane (798), `ray_at(pos)` (815), `view_direction()` (818), `px_size(depth)`
  (827), `unproject(pos, depth_or_plane)` (916), `raycast(...)` (884), `camera` (an `OrbitCamera`).
- Repaints: `scene.changed`, `selectionChanged`, `modeChanged`, `toolChanged`, `objectsChanged` all
  call `self.update()` (718-762). Changes to `obj.extras` written directly emit nothing.

### 1.2 How the extensions work around the missing hook
- `quartz_studio/sculpt/viewport.py` 43-60: `BrushOverlay`, a transparent child `QWidget` of the canvas
  (`WA_TransparentForMouseEvents`, `WA_TranslucentBackground`) that paints the brush ring and a mask
  `QImage` on top, re-projecting with `canvas.project_world`; line 238 installs an event filter on
  the canvas to follow resizes and moves.
- `quartz_studio/rig/widgets.py` 850: event filter on the canvas, same pattern for joints and weights.
- Consequences: overlays draw over everything with no occlusion, every overlay re-projects all
  points a second time, and a child widget repaints the full canvas area on each update.

### 1.3 Create menu and dock
- `menu_bar.py` 987-997: `object_menu_path(spec)` puts a `null` spec at `("Create", spec.label)`, others
  at `("Create", CREATE_SUBMENUS[category], label)`. `_object_commands()` is evaluated once, at import,
  inside `SCENE_COMMANDS` (1023-1031).
- `_wire_scene_commands` (1272-1287) calls `menu.bind(path[-1], handler)`; `StudioMenu.bind`
  (735-741) logs `menu item 'Joint' not found in 'Create'` because `menus_data.CREATE_MENU` has no
  static item for it. The kind is then not reachable from the menu.
- `object_palette.py` 190-211: `_build_palette()` runs once at import (`OBJECT_PALETTE_ENTRIES,
  CREATE_COMMANDS`, 211) and only knows the ids in `PALETTE_GROUPS` (156-166) plus `null`; extension
  kinds never appear. `_spec_entry` (180-187) already returns `None` for an unknown id (quiet).
- `controls/actions.py` 299-300 already builds one `create.<id>` action per spec from `all_specs()`;
  it must run after extensions register (see 7.4).

## 2. Layer API

### 2.1 Registration
```python
canvas.add_layer(fn, *, stage="scene", order=0, name="") -> LayerHandle
canvas.remove_layer(handle_or_fn) -> bool
canvas.layers(stage=None) -> list[LayerHandle]
```
- `fn(painter: QPainter, ctx: PaintContext) -> None`.
- `stage`:
  - `"scene"`: after `_paint_scene` (so after mesh fills, selection fills and `_paint_overlays`),
    before `_paint_tool_gizmo`. For joints, weights legends, mask dots, material swatches.
  - `"top"`: after `_paint_texts`, before `_paint_gizmo` (the triad stays on top). For brush rings and
    HUD-like hints.
  - Any other value: `ValueError`.
- `order`: integer, lower draws first; ties keep registration order.
- `name`: free text used in error messages and `LayerHandle.name`; defaults to `fn.__qualname__`.
- `LayerHandle` is a small frozen dataclass `(id: int, name: str, stage: str, order: int, fn)`;
  `id` is a counter on the canvas. `remove_layer` accepts the handle or the same `fn`; returns
  `False` when not found (no exception). Both calls end with `self.update()`.
- Adding the same `fn` twice in the same stage replaces the first registration (same id kept).
- Storage: `self._layers: list[LayerHandle]` in `__init__` next to the caches (after line 713).

### 2.2 Painter state guarantee
Before each layer: `painter.save()`; after: `painter.restore()`. The painter is antialiased, clipped
to the inner rounded rect, untransformed (device pixels of the canvas widget), pen and brush reset to
`Qt.NoPen` / `Qt.NoBrush`. A layer may change anything; the restore undoes it.

### 2.3 Errors
A layer that raises is caught in `paintEvent`; the traceback is logged once
(`log.exception("viewport layer %r failed", handle.name)`) and the layer is disabled
(`handle` stays in `layers()` with `enabled=False`; `canvas.enable_layer(handle)` re-enables it). The
paint continues with the next layer. `self.layer_errors: dict[int, str]` keeps the last message by
id for tests and the extension session.

### 2.4 `PaintContext` (new plain dataclass in `viewport.py`, filled during `_paint_scene`; layers treat it as read only)
Built once per `paintEvent` by `_paint_scene`, reused for every layer and colour provider of that
frame. Fields and methods:

| Name | Type | Meaning |
|---|---|---|
| `canvas` | `ViewportCanvas` | the widget |
| `scene` | `Scene` | `self.scene` |
| `camera` | `OrbitCamera` | `self.camera` (read only by contract) |
| `inner` | `QRectF` | `self.inner_rect()` |
| `shading` | `str` | display shading key (section 4); `"shaded_lines"` until the display filter exists |
| `light` | `np.ndarray (3,)` | `self._light_dir()` |
| `views` | `dict[int, _ObjectView]` | `id(obj) -> view` for every rendered object this frame |
| `polys` | `list[PolyItem]` | every polygon drawn this frame, in draw order (back to front) |
| `project(pts, obj=None)` | `-> (xy (N,2), depth (N,))` | world points, or object-local points when `obj` is given (multiplied by `obj` world matrix); `depth` is camera z; `xy` is NaN where `depth <= camera.near` |
| `view(obj)` | `-> _ObjectView or None` | the frame's view; `view.screen` and `view.cam` are the already projected points of `obj.world_points()`: index them by point index to avoid re-projecting |
| `visible(points)` | `-> np.ndarray[bool]` | `canvas._sight_clear(points)`: True where no rendered triangle hides the world point; uses the occlusion cache |
| `poly_item(obj, k)` | `-> PolyItem or None` | lookup by `(id(obj), k)` in a dict built with `polys` |
| `px_size(depth)` | `-> float` | world units per pixel at that depth |

`PolyItem` (frozen dataclass): `obj`, `k` (polygon index), `screen` (`QPolygonF`, near-clipped, the
same object the scene filled), `depth` (float, the sort key used), `front` (bool), `order` (int,
position in the final sorted draw list, 0 = drawn first), `color` (`QColor`, the final fill colour
drawn, after providers and shading).

Rule for tinting without re-projecting: a `"scene"` layer that wants to tint polygons iterates
`ctx.polys` in order and fills `item.screen`. Because the layer draws after the whole scene, a tint
painted on a polygon that is later covered in the sort would show through; such a layer must either
(a) use a colour provider instead (section 3, correct occlusion for free), or (b) paint only items
whose polygon is not covered: use `ctx.visible(points)` on the polygon centroid. Colour providers are
the recommended way for material, weights and mask colours; layers are for marks that sit on top
(joints, bones, brush, labels).

### 2.5 Depth-sorted items from extensions
For marks that must be hidden behind meshes but are not polygons (joints and bones drawn as lines and
discs):
```python
canvas.add_item_provider(fn, *, name="") -> LayerHandle
```
- `fn(ctx) -> Iterable[tuple[float, str, object, object, object]]`: `(depth, kind, shape, pen, brush)`
  with `kind` in `"polygon"` (`QPolygonF`), `"polyline"` (`QPolygonF`), `"line"` (`QLineF`),
  `"ellipse"` (`(QPointF centre, rx, ry)`), `"path"` (`QPainterPath`). `pen` is a `QPen` or `None`
  (no pen), `brush` a `QColor`/`QBrush` or `None`.
- Called inside `_paint_scene` after `_world_axis_items` (line 1530), before the sort; each tuple is
  appended as `(depth, len(items), ("ext", kind, shape, pen, brush))` and drawn by a new branch of
  the draw loop (1532-1548). Depth is camera z, same scale as `PolyItem.depth`.
- Removed with `remove_layer`. Errors: same rule as 2.3.
- `ctx.polys` is not yet available inside an item provider (the sort has not run); `ctx.views`,
  `ctx.project`, `ctx.view` are.

## 3. Colour providers

### 3.1 Registration
```python
canvas.add_color_provider(fn, *, priority=0, name="", per="polygon") -> LayerHandle
```
- `per="polygon"`: `fn(obj, k) -> QColor | None`.
- `per="object"` (batch, required above the budget in section 6):
  `fn(obj) -> np.ndarray | None`, shape `(len(obj.mesh.polygons), 4)`, float in 0..1, RGBA; a row
  with alpha 0 means "no colour for this polygon".
- `per="vertex"`: `fn(obj) -> np.ndarray | None`, shape `(len(obj.mesh.points), 4)`, float 0..1. The
  canvas averages the corners of each polygon (`colors[list(poly)].mean(axis=0)`), so weights and
  masks show per polygon. Smooth per-vertex gradients are out of scope (QPainter has no Gouraud fill;
  see 5.3).
- `None` from `fn` means the provider does not colour this object or polygon.
- Removed with `remove_layer`. Errors: 2.3 (a failed provider is skipped for the rest of the frame
  and disabled).

### 3.2 Combination
For each drawn polygon, in `_paint_scene` at line 1513-1514:
1. Base colour `B` = grey `(SHADE_MIN + SHADE_SPAN) / 255` (viewport.py 68-69: 190/255), alpha 1.
   With this base and no tint, step 3 reproduces `_shade(lam)` exactly.
2. Providers are applied in ascending `priority`, ties in registration order. Each non-None colour
   `C` with alpha `a` is composited over the current base: `B = C * a + B * (1 - a)`. So a material
   provider (priority 0, alpha 1) sets the base and a weights or mask provider (priority 10,
   alpha 0.4 to 0.8) tints on top.
3. Lighting: `f = clamp(lam)` mapped like `_shade`: `g = (SHADE_MIN + SHADE_SPAN * f) / (SHADE_MIN +
   SHADE_SPAN)`; `rgb = B.rgb * g`; then the same ink mix as `_shade` (`keep = 1 - SHADE_INK`, mixed
   with `theme.VIEWPORT_TOP`). Back faces keep the existing `-(n.l) * 0.55` term.
4. With no provider returning a colour for the polygon, the code path must call `_shade(lam)`
   unchanged, so the default render stays pixel-identical (test 8.1).
A provider may opt out of lighting with the flag `lit=False` on `add_color_provider` (for the sculpt
mask and weight heat maps, which read better unlit): the composite of unlit providers is applied after
step 3, over the lit colour.

### 3.3 Selection colours
Unchanged. The `"selected"` items (1515-1519, alpha 100 fills plus 2 px pens) are appended after the
`"poly"` item with the same depth and drawn over the provider colour, in every shading. Object
selection outline in `_paint_overlays` is unchanged.

### 3.4 Shading modes (`specs/interface.md` section 5.4, table at lines 708-717)
The display filter is planned, not yet built (`widgets/display_filter.py` does not exist today).
`PaintContext.shading` reads it when present, else `"shaded_lines"`.

| Shading | Providers used | Outline |
|---|---|---|
| `shaded_lines` | yes, lit (3.2) | `theme.POLY_OUTLINE` 1 px, unchanged |
| `shaded` | yes, lit | 1 px pen of the final fill colour (as interface.md says) |
| `hidden_line` | no: fill stays `theme.SURFACE_CARD` | `theme.WIRE` |
| `wireframe` | no polygons drawn; providers not called | lines |

A future `"textured"` key, if the display filter adds one, enables 5.3; until then texture follows
`shaded_lines` / `shaded`.

### 3.5 Occlusion cache
Providers change only fill colours. `_sight_cache`, `_tri_cache`, `_mesh_tri_cache`, `_guide_cache`
are not touched by colour changes and must not be cleared by `invalidate_layers`. Provider results
are not cached across frames by the canvas: each frame calls each `per="object"` / `per="vertex"`
provider once per rendered object, and each `per="polygon"` provider once per drawn polygon. A
provider that is expensive caches inside itself, keyed by its own data version.

## 4. Where the frame builds the context
`_paint_scene` (1478) gains, before the object loop: `ctx = PaintContext(...)`; inside the loop
`ctx.views[id(obj)] = view` (after 1496); colours from 3.2 replace `self._shade(lam)` at 1514 only
when a provider coloured the polygon; after the sort (1531) it builds `ctx.polys` from the `"poly"`
items in order (the item tuple at 1514 grows to `("poly", poly, color, obj, k, front)`); the draw
loop reads `item[1]` and `item[2]` exactly as today. `_paint_scene` returns `ctx`; `paintEvent` keeps
it in `self._frame_ctx` (cleared at the end of `paintEvent`) and passes it to the layers.

## 5. Texture

### 5.1 Provider
```python
canvas.add_texture_provider(fn, *, name="") -> LayerHandle
```
`fn(obj) -> TextureBinding | None`, with `TextureBinding` (frozen dataclass, defined in `viewport.py`):
`image: QImage` (any format; the canvas converts once to `Format_ARGB32_Premultiplied` and caches it
by `key`), `corner_uv: Sequence[np.ndarray]` (one `(len(poly), 2)` array per polygon, 0..1, V up),
`key: Hashable` (changes when the image or the UVs change). The uv and materials packages build the
binding from their own data; the canvas does not read `obj.extras`.

### 5.2 Honest assessment
The canvas is QPainter on the CPU, from Python, one `drawPolygon` per polygon. Plain fills already
cost on the order of 10-20 microseconds per polygon in PySide6 (Python loop plus the call). A textured
triangle needs, per triangle: a `QTransform` from the UV triangle to the screen triangle (3x3 solve),
`setTransform`, a clip path of the triangle, and `drawImage`; with smooth pixmap transform this is
roughly 10x a flat fill and grows with on-screen area (estimate, not measured on this machine: the
build and timing tests were running). Affine mapping has no perspective correction, so large polygons
close to the camera swim. Conclusion: true textured drawing is not interactive beyond a few thousand
triangles and is not the default.

### 5.3 What to build
1. Default (always on when a texture provider returns a binding): per-polygon average colour. For
   each polygon, sample the image at the UV centroid of each ear-clip triangle of its corner UVs
   (`_ear_clip_2d`, 454) from a downscaled copy of the image (longest side 64 px, `Qt.SmoothTransformation`,
   cached by `key`), average them, and feed the result into 3.2 as a priority `-10` lit colour (so
   material providers at priority 0 with alpha below 1 tint it). Cache the `(P, 4)` average array by
   `(key, id(obj), len(obj.mesh.polygons))`, at most 16 entries (clear when full, like
   `_MESH_TRI_LIMIT` 861).
2. Optional textured mode, only while `canvas.texture_detail` is `True` (default `False`; a future
   Display entry toggles it): after a polygon is filled, if the object has a binding and the frame's
   triangle count so far is under `TEXTURE_TRI_BUDGET = 3000`, draw its triangles with an affine
   `QTransform` and a triangle clip, image smooth-scaled to at most 512 px, then fill the polygon
   again with the shading colour at `alpha = 1 - g` (darkening) to keep lighting. Over the budget,
   or when the previous frame took more than `TEXTURE_FRAME_MS = 40` ms, the rest of the frame uses
   the average colour. Polygons with a near-clipped corner (`not view.in_front[idx].all()`) always
   use the average colour.

## 6. Invalidation and repaint
- `canvas.request_repaint()`: `self.update()`; for any data change of an extension (mask stroke, weight
  paint, material edit). Coalesced by Qt.
- `canvas.invalidate_layers(obj=None)`: drops texture caches (5.3) for `obj` or all, then
  `update()`. Never clears the geometry or occlusion caches.
- Edits made with `scene.set_object_extra` / `scene.set_extra` already emit `scene.changed`, which
  repaints (718). Direct writes to `obj.extras` need `request_repaint()`.
- A module helper `viewport.find_canvases() -> list[ViewportCanvas]` (all live instances, kept in a
  `weakref.WeakSet` filled in `__init__`) replaces the extension packages' own `find_canvas`
  (`rig/widgets.py` 53, `sculpt`, `render`). Extensions register on every canvas.

## 7. Create menu and object dock for extension kinds

### 7.1 Rule
Every spec in `objects.all_specs()` at wiring time is reachable from the Create menu and from the
object dock. A menu path or dock id that does not exist is never logged as a warning.

### 7.2 Menu (`widgets/menu_bar.py`)
- `_object_commands()` (996-997) is no longer captured at import: remove `+ _object_commands()` from
  `SCENE_COMMANDS` (1031) and loop over `SCENE_COMMANDS + _object_commands()` in
  `_wire_scene_commands` (1273).
- New `StudioMenu.ensure_item(label, icon_name=None) -> QAction` next to `bind` (735): returns
  `find_action(label)` if present; otherwise, the first time it is called on that menu, adds a
  separator (`self.addSeparator()`), then `add_item(label, None, icon_name)` (signature at 697:
  `text, shortcut, icon_name`; the `P_LABEL` property makes `find_action` and
  `bind` work). Extension items keep registration order.
- `_wire_scene_commands`: for an object command, call `menu.ensure_item(path[-1], icon)` before
  `menu.bind`, with `icon` from `object_palette._icon_name(spec)`. A `null` spec lands at the end of
  the top-level Create menu (after Null, under one separator): Joint, Light, Camera.
- If `object_menu_path` gets a category not in `CREATE_SUBMENUS` (impossible today: `ObjectSpec`
  validates `CATEGORIES`, registry.py 31 and 138), the spec is skipped silently.
- `StudioMenu.bind` (735-741): logging changes from `warning` to `debug`. Non-object commands keep
  their paths; a missing one is a bug in `menus_data`, caught by the existing menu tests.
- New public `menu_bar.sync_object_kinds() -> list[str]`: re-runs the object part of the wiring
  (ensure plus bind) for specs not yet bound, refreshes `controls` actions (7.4), and returns the ids
  added. Idempotent.

### 7.3 Dock (`widgets/object_palette.py`)
- `_build_palette()` (190-208) gets a pass after the groups: every spec id that is in no
  `PALETTE_GROUPS` tuple and is not `null` is placed by category: `null` kinds join the Null button,
  which becomes a foldout `Item(null_cmd, foldout=[null, joint, light, camera...], key="Null")` when
  there is at least one; `spline` kinds go at the end of the `"Rectangle"` group, `mesh` at the end
  of `"Cube"`, `generator` at the end of `"Subdivision Surface"`. Command keys follow the existing
  `(group key, label)` form, so `CREATE_COMMANDS[("Null", "Joint")]` exists.
- Because extension kinds only join existing groups or turn Null into a foldout, the number of dock
  buttons does not change, so the dock keeps its measured size.
- A new `object_palette.rebuild_palette() -> int` reassigns the module globals
  `OBJECT_PALETTE_ENTRIES, CREATE_COMMANDS = _build_palette()` (211) and replaces every live
  `ObjectPalette` (track instances in a module `weakref.WeakSet` filled in `__init__`, 275-298) with a
  new instance built with the same `orientation` and `popup_side`, at the same index of its parent
  layout (`layout.replaceWidget(old, new)`, then `old.deleteLater()`). `PaletteStrip` builds its
  buttons in its constructor (281) and `set_command_action` wiring happens there (297-298), so a new
  instance is the simplest correct refresh. Returns the number of palettes replaced. With no new
  kinds since the last build it replaces nothing and returns 0.
- `_spec_entry` (180-187) already ignores unknown ids; keep it.

### 7.4 When it runs
`app.install_extensions(window)` (hooks.md section 3) calls, after `ext_install.install(window)` returns
(success or caught failure): `window.menu_bar.sync_object_kinds()` and
`object_palette.rebuild_palette()`; `sync_object_kinds` also calls the function that
builds `create.<id>` actions in `controls/actions.py` (299-300) for the new ids only. No extension needs
to call these itself, but calling them again is harmless.

## 8. Tests: `tests/test_viewport_layers.py` (new), offscreen, small scenes
1. No layers, no providers: a cube rendered to a `QImage` is byte-identical before and after the change
   (render once with the hooks code path, compare with a stored hash computed by calling the old
   `_shade` directly per polygon).
2. `add_layer` order: three layers with orders 5, -1, 0 record call order `[-1, 0, 5]`; same `fn` twice
   keeps one entry; `remove_layer(fn)` returns True then False; unknown stage raises `ValueError`.
3. Painter state: a layer that sets a red pen and a transform does not change the next layer's
   `painter.pen()` / `painter.transform()`.
4. Layer error: a raising layer is disabled, `layer_errors` holds its message, the next layer still runs,
   the frame still shows the cube.
5. `ctx.polys`: for a cube seen from the front, `len(ctx.polys)` equals the number of drawn faces, `order`
   is 0..n-1, `screen` equals what `_poly_screen` returns, and `poly_item(obj, k)` finds each one.
6. `ctx.project(pts, obj)` equals `canvas.project(obj.world_points())` for the object's points;
   points behind the camera give NaN.
7. Colour provider: a red provider (alpha 1) makes the pixel at the centre of the front face red-dominant
   and lit (darker than pure red on a face at an angle); a second provider priority 10 with blue alpha
   0.5 gives a purple mix; `per="vertex"` with one red and three white corners on a quad gives the mean.
8. Selection over providers: in polygons mode with that face selected, the pixel mixes the provider
   colour and `theme.SELECT_FRONT` at alpha 100.
9. Occlusion cache: adding, calling and removing a colour provider leaves `_sight_cache` contents
   unchanged (same keys).
10. Item provider: a disc at the cube's centre (depth behind the front face) is not visible at the
    screen centre; moved in front of the cube, it is.
11. Texture: a 2x2 checker binding gives each polygon the average colour of its UV area;
    `texture_detail=True` with `TEXTURE_TRI_BUDGET=0` draws the same as the average path.
12. Menu: register a temporary `ObjectSpec(id="test_kind", label="Test Kind", category="null")`, build a
    `MenuBar`, call `sync_object_kinds()`: `action_at(("Create", "Test Kind"))` exists and triggers
    `create_object("test_kind")`; no warning record in `caplog`; a second call returns `[]`. Unregister
    the spec in teardown (`objects.SPECS.pop`).
13. Dock: after `rebuild_palette`, `CREATE_COMMANDS[("Null", "Test Kind")]` exists; with no extension
    kinds the entries equal today's `OBJECT_PALETTE_ENTRIES`.
14. With the real extension packages installed (`rig`, `render`): `("Create", "Joint")` and
    `("Create", "Light")` exist after `install_extensions` and no "not found" record is logged.
15. Performance (section 9 budgets) as a soft test, marked the same way as the project's existing timing
    test so the runner can exclude it on a loaded machine.

## 9. Performance budgets
Measured offscreen at 1280 x 720, release interpreter, 20-frame median:
- No hooks: frame time unchanged within 3 percent of today on the existing benchmark scene.
- Context build (`PaintContext` plus `ctx.polys`): at most 1 ms per 1,000 drawn polygons.
- Colour providers: `per="polygon"` only allowed up to 2,000 polygons per object; above that the canvas
  calls a `per="polygon"` provider anyway but logs once at debug level that a batch form is expected.
  A `per="object"` provider with a cached array must add at most 1.5 ms per 10,000 polygons.
- Each layer: target 2 ms; the canvas measures each layer with `time.perf_counter` and stores the last
  value in `handle.last_ms` (no enforcement, for the profiler and tests).
- Texture average path: first build at most 30 ms for a 1024 px image and 5,000 polygons, then cached.
- Textured mode: `TEXTURE_TRI_BUDGET = 3000` triangles, `TEXTURE_FRAME_MS = 40`.

## 10. Summary of changes by function

| File | Function (lines) | Change |
|---|---|---|
| `widgets/viewport.py` | module | `log = logging.getLogger("quartz_studio.viewport")` (viewport.py has no logger today); `PaintContext`, `PolyItem`, `LayerHandle`, `TextureBinding` dataclasses; `find_canvases()`; constants `TEXTURE_TRI_BUDGET`, `TEXTURE_FRAME_MS` |
| `widgets/viewport.py` | `__init__` (683-722) | `_layers`, `_texture_cache`, `layer_errors`, `texture_detail=False`, `_frame_ctx=None`; add self to the WeakSet |
| `widgets/viewport.py` | new methods after `label_font` (940) | `add_layer`, `remove_layer`, `enable_layer`, `layers`, `add_item_provider`, `add_color_provider`, `add_texture_provider`, `request_repaint`, `invalidate_layers`, `_run_layers(p, stage)`, `_poly_color(view, k, lam, ctx)` |
| `widgets/viewport.py` | `paintEvent` (1287-1304) | `ctx = self._paint_scene(p)`, then `_run_layers(p, "scene")` before `_paint_tool_gizmo` (1299), `_run_layers(p, "top")` before `_paint_gizmo` (1303) |
| `widgets/viewport.py` | `_paint_scene` (1478-1550) | build ctx (2.4, 4), colour at 1513-1514 via `_poly_color`, item providers after 1530, `"ext"` draw branch in 1532-1548, textured branch (5.3), return ctx |
| `widgets/viewport.py` | `_shade` (1313-1319) | unchanged; the lit formula of 3.2 reuses its constants |
| `widgets/menu_bar.py` | `StudioMenu.bind` (735-741) | warning to debug |
| `widgets/menu_bar.py` | new `StudioMenu.ensure_item` | 7.2 |
| `widgets/menu_bar.py` | `SCENE_COMMANDS` (1023-1031), `_wire_scene_commands` (1272-1287) | object commands computed at wiring time, `ensure_item` before `bind` |
| `widgets/menu_bar.py` | new `MenuBar.sync_object_kinds` | 7.2, 7.4 |
| `widgets/object_palette.py` | `_build_palette` (190-208) | extension kinds by category, Null foldout |
| `widgets/object_palette.py` | new `rebuild_palette()`, instance WeakSet in `ObjectPalette.__init__` (275-298) | 7.3 |
| `app.py` | `install_extensions` | calls 7.4 after the extension install |
| `controls/actions.py` | 299-300 | callable for a list of new spec ids |

Not changed: the occlusion code (`_sight_clear`, `_trace_sight`, 1359-1436), picking, the gizmo, the
extension packages (their owners move `BrushOverlay` and the rig event filter onto `add_layer` /
`add_item_provider` / `add_color_provider` once this lands).
