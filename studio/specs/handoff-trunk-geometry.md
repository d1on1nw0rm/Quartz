# Handoff: Trunk skin geometry and performance review

Scope: `quartz_studio/modeling/trunk_skin.py` (read completely, 1096 lines) against SPEC.md 10.1. Review by reading,
plus tiny probes only (no test suite, no app). Written 2026-11-20 during the closing step of the night run. Nothing in
the code was changed.

## Pipeline as built

1. `build_skin`: sanitise radii (abs, non finite to 0), `_unique_edges` (drop self loops, out of range, duplicates),
   drop edges with non finite endpoints, `_weld` (spatial hash, tolerance 1e-6 of the bounding diagonal, union find),
   then `_Skin(...).run()`.
2. `_Skin.__init__`: adjacency, components, drop components whose max radius is below 1e-6, interior floor
   `rint = max(R, 1e-3 * rmax_component)`, apex flags (valence 1 and R < 1e-6), initial hubs = valence >= 3 or a
   valence 2 bend sharper than cos < -0.6 (`_sharp`).
3. `run()` loop, at most `4 n + 20` rounds:
   - `_solve_dirty`: for each dirty hub, `_solve` finds a set-back `s` per exit by growing it (x1.15 + 0.02 r per
     sweep, at most 400 sweeps) until every exit ring passes `_caps` (centre farther than 1.05 r from the hub centre,
     facing > 0.3, angular cones of the rings separated). If an exit runs past its budget the exit neighbour is merged
     into the hub (`_union`) and the neighbours are dirtied.
   - `_limbs`: walks every limb from the hub rings, the free ends and the pure cycles, building `_Station`s.
   - `_fold`: for every consecutive station pair, `_ring_max` tests whether one ring crosses the plane of the next;
     offending mitres become hubs, offending hub or end pairs are merged. Any action restarts the round.
   - `_emit`: rings per station (`_frames` = rotation minimising transport, closed loops untwisted by distributing the
     holonomy angle), quads between rings, apex fans, end caps, then one patch per hub: `_patch_star` (hull of the
     ring points radially projected onto the unit sphere around the hub centre) when the hub has exit rings, or
     `_patch_convex` (plain hull) when the whole component collapsed into one hub. `_finish` removes the ring discs
     from the hull, checks each ring loop is exactly the hull border of its disc, and pairs coplanar triangles into
     quads. A failed patch merges its exits and restarts the round.
4. If the round budget runs out, `run()` returns an empty mesh.

## Findings, ordered by severity

### F1 (high, performance): merge cascade inside `_solve_dirty`, cost grows with radius / segment length

Measured (probe below): the number of `run()` rounds stays at 1 or 2 even for fat trees, so the restart loop is not
the problem. The cost is the merge cascade inside `_solve_dirty`. When a hub cannot fit its rings, `_solve` returns
ONE failing exit; `_union` merges that single neighbour, `_touch` dirties the hub and every neighbouring hub, and the
grown hub is solved again from scratch: exits recomputed by scanning all members, `_budget` per exit in Python, the
k x k angle matrix, and the sweep loop of `_caps` from the initial set-back. A hub that absorbs m nodes one at a time
costs O(m x (m + sweeps x k^2)) plus O(m^2 log m) for the sorted concatenation in `_union`. The bigger the radius
against the segment length, the more nodes each hub must absorb before its rings fit, hence the growth with the
radii. With base 10 and segments of about 1.4, the 120 point probe tree collapses into a handful of hubs (only 3 hull
builds, 465 polygons for 120 points: essentially one convex blob), after 117 solves and 342 `_caps` calls; the 1000
point case was not run here (too heavy during the build); by the same mechanism it should absorb hubs with m in the
hundreds, which would explain the 3.8 s (inference, to confirm with a profile after the build). `_solve` own time (Python overhead per
exit) is as large as `_caps`.

Fixes: merge every exit whose `s` exceeds its budget in one step instead of one per solve; warm start (F2); keep
`members` as a set. Also a product question: with base 10 on segments of 1.4 the honest result is a blob, so the
caller could warn when `max radius > segment length` instead of spending seconds to produce one.

### F2 (medium, performance): `_solve` growth from a radius independent start, no warm start

Non core exits start at `s = 0.05 L`, independent of the radius, and grow by 15 % per sweep. The set-back that
passes `_caps` is of the order of `r / sin(half angle between limbs)`, so a solve that converges needs about
`log(r / (0.05 L)) / log(1.15)` sweeps (up to 20 to 40 for r/L of 1 to 10), each allocating a (k, 24, 3) array in
`_caps` plus a k x k arccos matrix. Core exits get the closed form estimate `est`, clamped to 0.95 budget; non core
exits never get it. Merged hubs re-solve from scratch every time they are dirtied (no warm start from the previous
`s`). In the probes the average is 1.2 to 4.5 `_caps` calls per solve, because most solves on fat trees end early
with one exit over budget (F1); once F1 is fixed, the sweeps of the remaining converging solves become the next
cost, so F2 matters after F1.

### F3 (medium, correctness): silent empty result when the round budget is exhausted

`run()` returns `(zeros((0, 3)), [])` after `4 n + 20` rounds without any signal. The contract says a short segment
must still give a valid manifold, never an open result; an empty mesh is neither and the caller cannot tell it from
"nothing to skin". The same silent loss happens for a hub put in `self.dead` (`_emit`, patch failure with no exits):
a component that collapsed into one hub with no exits simply disappears from the output. Suggested test (dense zigzag of very short segments with a huge radius, which forces
many merge rounds):

```python
pts = [(i * 0.01, (i % 2) * 0.01, 0.0) for i in range(60)]
edges = [(i, i + 1) for i in range(59)]
mesh_pts, polys = build_skin(pts, edges, [10.0] * 60)
assert len(polys) > 0
```

Expected per contract: one closed blob (Euler 2). Probe result: this input gives a valid closed blob (Euler 2, no
open or duplicated edge, 0.085 s), so the empty path was not reproduced; it stays a latent risk because the guard
exists and returns nothing silently. Recommended: return the best partial result or raise, and add the test above.

### F4 (medium, correctness): `_patch_star` maps a sphere triangulation back without checking orientation

The patch triangulation is the convex hull of the ring points projected onto the unit sphere around `O` (the mean of
the core members). `star()` rejects only the case where `O` is not strictly inside the projected hull. The faces are
then used with the original, unprojected positions `X`. If two adjacent rings sit at very different distances from
`O` (one limb set back far, its neighbour close), a hull triangle that spans both can face inwards in real space (the
tetra `O, a, b, c` has negative volume) or intersect a neighbouring ring tube, while the sphere hull is still valid.
No check for that exists (`_outside` only filters the extra cap and octa points). After a merge, `O` is the mean of
merged core nodes and can lie outside the region bounded by the rings for an L or U shaped merged cluster, which
makes this more likely. Suggested test (a T junction where one branch is much thicker and one segment is short):

```python
pts = [(0, 0, 0), (0, 1, 0), (0, 2, 0), (1, 1, 0), (1.2, 1, 0)]
edges = [(0, 1), (1, 2), (1, 3), (3, 4)]
radii = [0.6, 0.6, 0.6, 0.05, 0.05]
```

Assert: every patch polygon has positive signed volume against the hub centre, and the total signed volume is
positive with no edge used twice in the same direction.

Probe result: this input gives a closed manifold (Euler 2, no open or duplicated directed edge, positive volume), so
the flip was not reproduced with it; the global checks would not catch a local inward face whose neighbours
compensate, so the per face check is still the recommended test.

Fix: in `star()` compute `det(X[b]-O, X[c]-O, X[a]-O)` sign per face (or the dot of the real normal with `X[a]-O`)
and reject the hull if any is not positive, so the existing fallback (merge the exits) takes over.

### F5 (medium, contract): a cycle that collapses into one hub loses its hole

A small closed loop with a large radius folds every mitre into a hub, all hubs merge, the hub has no exits, and
`_patch_convex` emits one convex blob. The result is a valid closed manifold but with Euler characteristic 2, while
SPEC 10.1 says 0 for a component with one cycle. Input:

```python
pts = [(0, 0, 0), (1, 0, 0), (0.5, 0.8, 0)]
edges = [(0, 1), (1, 2), (2, 0)]
radii = [0.6, 0.6, 0.6]
```

Probe result: confirmed, Euler 2, 15 points, 22 polygons, closed, positive volume.
Either the contract should say "0 unless the hole closes" (physically the tube fills the hole, so a blob is the honest
result), or the test must accept 2 for that case. A test that only checks Euler 0 on fat small loops will fail.

### F6 (low, correctness): convex hull robustness (`_hull`)

What it does: incremental hull in input order, simplex from the lexicographic minimum, farthest point, farthest from
the line, farthest from the plane; visibility is `dist > eps`; the horizon is checked to be one simple loop and any
inconsistency returns `None`. It never returns a broken surface (good), but:

- Points within `eps` of a face plane are not visible, so a point coplanar with a face and lying outside it is either
  attached through an adjacent face (giving a sliver coplanar with the old face; `_pair_quads` may merge it) or, if no
  face sees it, dropped silently. A dropped ring point breaks the `border == loop` test in `_finish`, the patch
  fails and the hub merges its exits. This is the main order dependent path to "unexpected merges" on nearly coplanar
  input, for example a junction where all limbs lie in one plane and the rings are thin (`_patch_star` points on a
  near great circle). Input that stresses it:

  ```python
  pts = [(0, 0, 0), (1, 0, 0), (-0.5, 0.866, 0), (-0.5, -0.866, 0)]
  edges = [(0, 1), (0, 2), (0, 3)]
  radii = [0.001, 0.001, 0.001, 0.001]
  ```

  All exits coplanar, very thin: the projected ring points lie in a band about 1e-3 wide around a great circle; the
  `star()` test `off.min() <= 1e-7` and the fixed `eps = 1e-10` decide whether the anchors fallback runs. Assert a
  closed manifold with Euler 2. Probe result: passes (Euler 2, closed, 48 points, 41 polygons), so the eps choice
  holds at this scale; keep it as a regression test.
- `_patch_star` uses an absolute `eps = 1e-10` on unit vectors, fine; `_patch_convex` scales eps with the extent,
  fine. `area_eps = eps * eps` compares a cross product length (twice the area), consistent but extremely small, so
  sliver triangles pass and become very thin polygons; the contract forbids zero area, not thin, so acceptable.
- All k < 4 or fully coplanar inputs return `None` (for example a component collapsed into one hub that holds only
  two apex points): the hub then goes to `octa` or `dead`. See F3 for the silent loss.
- Cost: no conflict lists, every new point tests all faces, O(k^2) with numpy per point. Fine for k up to a few
  hundred (sides 8 x exits); a merged hub of 50 nodes with octa points reaches k of several hundred and becomes a
  visible cost.

### F7 (low, correctness): mitre and stretch limit

`_ring` projects the ring along the incoming tangent onto the bisector plane; `tn = t . n` is cos(half bend), never 0
because bends sharper than cos < -0.6 are hubs from the start, so `tn >= sqrt(0.2)`, stretch <= 2.24, and the clamp
to `_STRETCH_MAX = 2` acts only for bends between about 120 and 127 degrees. The clamp direction `bd = t2 - t1` lies
in the bisector plane, so the ring stays planar. `_budget` uses the same `min(tan(half), 2 sin(half))` extension, so
it is consistent. No defect found. One weak spot: `_fold` uses a margin of `0.02 max(rA, rB)`; two rings whose planes
cross inside the tube by less than the margin can still give self intersecting quads on a long thin bend with very
different radii. Low risk.

### F8 (low): welding and close nodes

`_weld` merges only points closer than 1e-6 of the bounding diagonal. Points that are close but not that close
(segment of 1e-4 on a radius 1 tube) are handled by folding, which is correct but slow (F1). Spatial hash per point
in Python, 27 cells, fine for 2000 points.

### Correct as read

- `profile_radii` matches SPEC (root choice, `t = d_root / (d_root + d_down)`, scales, unused points 0).
- Duplicate edges, self loops, zero length edges (welded) and non finite points are ignored as required.
- Cone apex: valence 1 and R < 1e-6, a fan without cap; an apex inside a merged hub becomes a single hull point.
- End caps oriented reversed at the start and forward at the end, so normals point outward; patch caps take the
  orientation from the hull's directed edges.
- `_pair_quads` builds the quad as `(e0, d, e1, opp)`, which keeps the orientation of both triangles.
- Closed loops: the holonomy angle is distributed linearly over the stations, so the last ring meets the first.
- Determinism: all iteration orders are sorted (`min(self.dirty)`, `sorted(self.members)`, sorted adjacency).

## Probe results (tiny runs, `.venv` Python, while the build was running, so times are indicative)

| Input | Points / polygons | Euler | Open or doubled directed edges | Volume | Time |
|---|---|---|---|---|---|
| Triangle loop, r 0.6 (F5) | 15 / 22 | 2 | 0 / 0 | 1.54 | 0.038 s |
| Thick T with thin short branch (F4) | 56 / 55 | 2 | 0 / 0 | 2.21 | 0.007 s |
| Planar three way junction, r 0.001 (F6) | 48 / 41 | 2 | 0 / 0 | about 0 | 0.005 s |
| Zigzag of 60 points 0.01 apart, r 10 (F3) | 279 / 322 | 2 | 0 / 0 | 1774 | 0.085 s |

Random 120 point tree (seed 1, segments about 1.4), counters of `_solve`, `_caps` and `run()` rounds:

| base / tip | solves | `_caps` calls | rounds | polygons | time |
|---|---|---|---|---|---|
| 0.2 / 0.04 | 32 | 39 | 1 | 2437 | 0.16 s |
| 1.0 / 0.2 | 91 | 424 | 2 | 1463 | 0.19 s |
| 3.0 / 0.6 | 133 | 600 | 2 | 509 | 0.18 s |
| 10 / 2 | 117 | 342 | 1 | 465 | 0.12 s |

Reading: solves grow 4x and `_caps` calls 15x from thin to fat while the rounds stay at 1 or 2, and the polygon count
falls because limbs are swallowed by hubs. The cost is the merge cascade (F1) and the sweeps per solve (F2), not the
outer loop. Profile of the base 10 run: `_solve` 0.037 s own time, `_caps` 0.032 s, `_hull` 3 calls.

## Optimisation plan

Ordered by gain over effort. Times refer to the measured 3.8 s (1000 points, base 10, tip 2) and 0.5 s (300 points).

1. Stop the one-node-at-a-time merge cascade (`_solve`, `_solve_dirty`, `_union`, and a pre-pass in
   `_Skin.__init__`). `_solve` returns every exit with `s > budget` (or `grow` at the last sweep), and
   `_solve_dirty` unions them all before re-solving. Pre-merge, with the spatial hash of `_weld` and a cell of the
   local radius, every pair of nodes closer than `c x max(r_a, r_b)` (c about 1) into hubs before the first solve,
   so a fat trunk starts with its final hubs. Keep `members` as a set and sort only in `_statics` and the patches.
   Expected: solves on the 1000 point base 10 case drop from O(m) per hub to a few; 3x to 8x on the 3.8 s case.
2. Closed form start and warm start in `_solve`.
   Start every exit (not only core) at `max(0.05 L, est)` with `est` the existing angular estimate, keep the last
   `s` per (root, exit) in a cache and start from it when the hub is re-solved, and replace the x1.15 walk by a
   doubling then bisection on the failing exits. Expected: converging solves from up to 20 to 40 sweeps down to 4 to
   8; 1.5x to 3x on `_solve` after step 1.
3. Analytic `_caps` (no 24 sample points).
   With `x = cos(phi - phi0)`, `W . a = dist + r rho x` and `|W|^2 = dist^2 + r^2 + 2 r dist rho x`, where `rho` is
   the length of the projection of `a` on the ring plane, so `cos beta = min over x in [-1, 1]` of a 1D function
   with a closed form minimum (check `x = -1`, `x = 1` and the stationary point). Removes the (k, 24, 3) temporaries;
   `wn.min` becomes `sqrt(dist^2 + r^2 - 2 r dist rho)`. Expected: 4x to 6x on `_caps`.
4. Cache per junction and dirty only what changed (`_touch`, `_solve_dirty`).
   A hub's solution depends only on its members, the positions and radii of the exit pairs and whether each exit
   neighbour is a hub (budget). `_touch` dirties every hub neighbour; dirty a neighbour only when its exit toward this
   hub changed (the hub flag of `v` flipped). Store `sol` with that key and skip the solve when it matches.
5. Incremental limbs and vectorised folding (`_limbs`, `_fold`, `_ring_max`).
   Keep limbs in a dict keyed by their first station; after a fold re-walk only the limbs touching dirtied hubs.
   Evaluate `_ring_max` for all consecutive station pairs as numpy arrays (c, n, t, r) in one call. Expected: small
   today (the probes show 1 or 2 rounds), worth doing together with step 8 where only one limb changes.
6. One hull per patch (`_patch_star`).
   `star(groups)` and then `star(groups + kept)` build the hull twice; build once with the kept candidates, and fall
   back to the base only on failure. Add the orientation check of F4 in the same place. Expected: about 40 % less
   hull time for hubs with caps or sharp members. Add conflict lists to `_hull` only if merged hubs above about 300
   points remain common.
7. `_union` merges sorted lists with `heapq.merge` or keeps a set and sorts at emit time. Small gain, removes an
   O(m^2) worst case on long merge chains.
8. Incremental rebuild when one point moved (new API inside the module, callers unchanged).
   Keep the `_Skin` object between calls in the tool; when only point `p` moved, dirty the hub that owns `p` or the
   two hubs at the ends of its limb, re-solve those, re-walk that limb, re-emit its rings and the two patches, and
   splice the new blocks into the cached vertex and polygon arrays (blocks are already allocated per station and per
   patch by `alloc`, so offsets can be kept per block). Expected: a drag preview of a 300 point tree from 0.5 s to
   under 50 ms. Requires a second public entry point, which SPEC 10.1 forbids today ("keeps exactly the public API"),
   so it needs a SPEC change first; alternatively cache inside the caller and only call `build_skin` on release.
9. Cheap preview (`ops_trunk.py`, owned by the tool): while dragging, draw one ring per point (oriented by the
   bisector, the same `_ring` maths, vectorised with numpy for all points at once) plus the axis lines, with no
   junction patches; run `build_skin` on mouse release or after a 150 ms idle. Rings and lines for 1000 points cost a
   few ms. Alternatively build the preview with `sides=4`, which cuts `_emit` and hull work roughly in half but not
   `_solve`.

Suggested order for the next session: 1, 2, 3 (each independently testable against `tests/test_trunk_skin.py`),
then 9 (largest felt gain, no change to the module), then 4 to 7, and 8 only after a SPEC decision.
