# Handoff: review of the Standard controls profile

Review of `STANDARD` in `quartz_studio/controls/profiles.py` against `specs/controls.md` sections 2.4, 2.5, 3.3 and 7.
Read-only review written on 2026-11-20 during the closing step of the night run. No code was changed.

Sources: the profile source, the contract, a short probe (`profiles.conflicts(profiles.resolve(STANDARD))`, run
with the core action registry) and `widgets/menus_data.py`. The bindings of the other programs come from their
shipped defaults as known to the reviewer (Blender 4.x default keymap and its Industry Compatible keymap, Maya
2024+, 3ds Max 2024+, Houdini 20, Modo 17, Unity 6 editor, Unreal Engine 5 editor). No web search was run in the
time available for most cells; two targeted searches confirmed the Houdini component keys (1 objects, 2 points,
3 edges, 4 primitives; Ctrl adds, Ctrl+Shift removes, Shift toggles) and the 3ds Max hide keys (Alt+H hide
selection, Alt+U unhide all) from SideFX and Autodesk documentation. Entries the reviewer is less sure of are
marked "(check)".

## 1. Verdict in short

- Standard is a sound default: Maya/Unity/Unreal navigation plus Blender middle-button navigation, Q W E R, F/A
  framing and Blender's modeling keys is the mix most newcomers will recognise. No conflict inside any scope (the
  probe returns an empty list) and no chords.
- Three real gaps for a newcomer: there is no way to pan (and no keypad views) without a three-button mouse and a
  numeric keypad; Duplicate, Hide and command search have no key although every compared program has one; the
  rationale in 3.3 is wrong about Houdini (Houdini does not use Q W E R).
- Three surprises worth fixing or documenting: `Home` resets the camera where Blender users expect "frame all";
  `Num+5` is not a toggle; plain middle drag orbits where 3ds Max and Unity users expect it to pan (accepted cost
  of the Blender scheme, keep it).

## 2. Comparison table

Legend: LMB, MMB, RMB = left, middle, right mouse button; Num = numeric keypad; "none" = no default key (menu or
marking menu only). A mark in the last column: S = surprises a newcomer from at least one program, C = collides
with a strong convention, ok = matches the majority or a strong convention.

| Operation | Blender (default) | Blender Industry Compatible | Maya | 3ds Max | Houdini | Modo | Unity | Unreal | Quartz Standard | Mark |
|---|---|---|---|---|---|---|---|---|---|---|
| Orbit | MMB | Alt+LMB | Alt+LMB | Alt+MMB | Alt+LMB or Space+LMB | Alt+LMB (also MMB with the default mouse input preset) (check) | Alt+LMB | Alt+LMB | MMB, Alt+LMB | ok |
| Pan | Shift+MMB | Alt+MMB | Alt+MMB | MMB | Alt+MMB or Space+MMB | Alt+Shift+LMB | MMB, or Q hand tool + LMB | Alt+MMB, MMB | Shift+MMB, Alt+MMB | S (Max, Unity users pan with plain MMB); no LMB-only pan |
| Dolly | Ctrl+MMB, wheel | Alt+RMB, wheel | Alt+RMB, wheel | Ctrl+Alt+MMB, wheel | Alt+RMB, wheel | Alt+Ctrl+LMB, wheel | Alt+RMB, wheel | Alt+RMB, wheel | Ctrl+MMB, Alt+RMB, wheel | ok |
| Frame selected | Num+. | F | F | Z | Space+G (check; reported unreliable) | Shift+A | F | F | F | ok |
| Frame all | Home | A | A | Z with nothing selected, Ctrl+Shift+Z all views | Space+H, H | A | none (double-click root) | none (Home in some modes) (check) | A | S for Blender users (A = select all in Blender) |
| Reset / home view | none (Home frames all) | none | none | none | Space+H | Home (check) | none | none | Home | C with Blender (Home = frame all) |
| Select | LMB | LMB | LMB | LMB | LMB (S tool) | LMB | LMB | LMB | LMB | ok |
| Add to selection | Shift+LMB (toggle) | Shift+LMB | Shift+LMB (toggle), Ctrl+Shift+LMB (add) | Ctrl+LMB | Ctrl+LMB (Shift toggles) | Shift+LMB | Shift or Ctrl+LMB (toggle) | Ctrl+LMB, Shift+LMB | Shift+LMB | ok |
| Remove from selection | Shift+LMB on selected, Ctrl+box | Ctrl+LMB | Ctrl+LMB | Alt+LMB | Ctrl+Shift+LMB | Ctrl+LMB | toggle only | Ctrl+LMB toggle | Ctrl+LMB | ok (Max users expect Alt) |
| Select all / none / invert | A / Alt+A / Ctrl+I | Ctrl+A / Ctrl+Shift+A (check) / Ctrl+I | none | Ctrl+A / Ctrl+D / Ctrl+I | N / Shift+N (check) | none (check) | Ctrl+A / Shift+D? (check) / none | Ctrl+A / Esc / Ctrl+I (check) | Ctrl+A / Ctrl+Shift+A / Ctrl+I | ok |
| Selection tool | W cycles box/lasso | Q | Q | Q | S | none | Q is the hand tool | Q | Q | S for Unity users only |
| Move | G (gizmo: W toolbar) | W | W | W | T | W | W | W | W | ok |
| Rotate | R | E | E | E | R | E | E | E | E | ok |
| Scale | S | R | R | R | E | R | R | R | R | ok (Houdini differs) |
| Points mode | 1 (edit mode) | 1 | F9 | 1 | 2 | 1 | none (ProBuilder: G cycles) | none (Modeling mode) | 1 | ok |
| Edges mode | 2 | 2 | F10 | 2 | 3 | 2 | none | none | 2 | ok |
| Polygons mode | 3 | 3 | F11 | 4 (3 = border) | 4 (primitives) | 3 | none | none | 3 | ok (Max users press 4) |
| Objects mode | Tab (toggle edit) | 4 (check) | F8 (object/component toggle) | 6 or 1 again (exit sub-object) (check) | 1 | 5 (items) | n/a | n/a | 4 | S for Max (4 = polygon) and Modo (5), acceptable |
| Extrude | E | Ctrl+E | Ctrl+E | Shift+E (check), Shift+drag | none (Tab menu) | none (check) | ProBuilder Shift+E (check) | none | Ctrl+E | ok |
| Bevel | Ctrl+B | Ctrl+B | Ctrl+B | none | none | B (check) | none | none | Ctrl+B | ok |
| Inset | I | I | none | none | none | none | none | none | I | ok |
| Loop cut | Ctrl+R | Ctrl+R (check) | none (marking menu) | none | none | Alt+C (check) | none | none | Ctrl+R | ok |
| Knife | K | K | none | none | none | none | none | none | K | ok |
| Merge / weld | M | M (check) | none | none | none | none | none | none | M | ok |
| Delete | X, Delete | Delete, Backspace | Delete, Backspace | Delete | Delete | Delete, Backspace | Delete | Delete | Delete, Backspace | ok |
| Duplicate | Shift+D | Ctrl+D | Ctrl+D | Shift+drag, Ctrl+V | Ctrl+C / Ctrl+V | Ctrl+D (check) | Ctrl+D | Ctrl+D, Alt+drag | none | C (every program has one; Ctrl+D is the majority) |
| Copy / paste | Ctrl+C / Ctrl+V | Ctrl+C / Ctrl+V | Ctrl+C / Ctrl+V | none | Ctrl+C / Ctrl+V | Ctrl+C / Ctrl+V | Ctrl+C / Ctrl+V | Ctrl+C / Ctrl+V | none (menu shows Ctrl+C / Ctrl+V as text only) | C |
| Undo | Ctrl+Z | Ctrl+Z | Ctrl+Z, Z | Ctrl+Z | Ctrl+Z | Ctrl+Z | Ctrl+Z | Ctrl+Z | Ctrl+Z | ok |
| Redo | Ctrl+Shift+Z | Ctrl+Shift+Z | Shift+Z, Ctrl+Y (check) | Ctrl+Y | Ctrl+Y, Ctrl+Shift+Z | Ctrl+Shift+Z | Ctrl+Y, Ctrl+Shift+Z | Ctrl+Y | Ctrl+Shift+Z, Ctrl+Y | ok |
| Save | Ctrl+S | Ctrl+S | Ctrl+S | Ctrl+S | Ctrl+S | Ctrl+S | Ctrl+S | Ctrl+S | Ctrl+S | ok |
| Hide selected | H | Ctrl+H | Ctrl+H | Alt+H | none | H | H (toggle scene visibility) | H | none | C |
| Unhide all | Alt+H | Ctrl+Shift+H (check) | Ctrl+Shift+H, Shift+H | Alt+U | none | Shift+H (check) | H | Ctrl+H | none | C |
| Isolate selected | Num+/ | Num+/ (check) | Shift+I (check) | Alt+Q | none | none | Shift+H | G toggles game view; isolate none | none | S |
| Front / right / top view | Num+1 / Num+3 / Num+7 | F1 / F2 / F3 | Space marking menu | F / R (check) / T | Space+1..5 (check) | Num keys (check) | gizmo click | Alt+H / Alt+K / Alt+J | Num+1 / Num+3 / Num+7 | S for laptop users (no keypad, no alternative) |
| Opposite views | Ctrl+Num+1/3/7 | Ctrl+F1..F3 (check) | Space menu | B (bottom), L (left) | Space menu | Num | gizmo | Alt+Shift+H/K/J | Ctrl+Num+1/3/7 | ok |
| Perspective / parallel | Num+5 toggles | F4 (check) | Space menu | P / U | Space menu | Num+5 (check) | gizmo center click | Alt+G | Num+5 persp, Ctrl+Num+5 parallel | S (Blender users expect Num+5 to toggle) |
| Context menu | RMB (W in left-select) | RMB | RMB marking menu | RMB quad menu | RMB | RMB | RMB | RMB | RMB | ok |
| Pie / quick menus | Z shading, Tab mode, ` view, Q quick favourites | Alt+Q? (check) | Space hotbox, Shift/Ctrl+RMB marking menus | RMB quad, Ctrl/Alt/Shift+RMB quads | Tab node menu | ` pie, Q (check) | none (Shift+Space maximise) | none | none | S (no quick menu at all) |
| Search a command | F3 | Tab (check) | none built in (check) | X (Search Actions) | Tab | none (check) | Ctrl+K | Ctrl+P assets (check) | none bound (menu shows Shift+C as text only) | C |
| Settings / preferences | Ctrl+, (4.2+) | Ctrl+, | none | none | none | none | Ctrl+, (check) | none | Ctrl+, | ok |
| Fly / walk navigation | Shift+` | Shift+` (check) | none | none | none | none | RMB + WASD | RMB + WASD | none | S (Unity and Unreal users hold RMB to look) |

## 3. Internal consistency of the Standard document

Checked against the source of `profiles.py` and the core action registry.

1. One primary key per action. Holds. Only `edit.redo` (`Ctrl+Shift+Z`, `Ctrl+Y`), `edit.delete` and
   `object.delete` (`Delete`, `Backspace`) have two keys, and both are deliberate secondaries.
2. No conflict within a scope. Holds: `conflicts(resolve(STANDARD))` returns `[]`. `Delete` and `Backspace` are
   bound twice but in disjoint scopes (`edit.delete` viewport, `object.delete` objects).
3. Chords. Standard has none, so no chord shadows a single key. Note that Classic tool shortcuts from the
   modeling registry are only added for Classic (`_builtin_resolved`), so they cannot leak into Standard.
   Registry actions with `default_keys` are added to every profile by `resolve`; none exist today, but a future
   `default_keys` could collide with Standard's plain keys (`I`, `K`, `M`, `P`, `1` to `4`). A test that runs
   `conflicts` on both built-ins with the full registry installed (modeling included) should stay in the suite.
4. Scopes of plain keys. `1` to `4`, `I`, `K`, `M`, `P` and `Shift+P` are global, while `Q W E R`, `F`, `A` are
   viewport. A plain letter bound globally fires while the Object Manager or the Attributes panel has focus
   (type-ahead in the object tree is lost, and a user typing a name start presses `M` and welds). Recommend
   viewport scope for every unmodified key in Standard, as Classic already does for its tool shortcuts
   (`_classic_tool_pair`).
5. Unbound core actions. `view.undo` and `view.redo` have no key in Standard (Classic uses `Ctrl+Shift+Z` and
   `Ctrl+Shift+Y`; the first collides with Standard's redo, which is why they were dropped). Acceptable, but say it
   in 3.3. `camera.pivot.*`, `camera.isometric`, `camera.dimetric`, `file.export_selection` are unbound too; fine.
6. Menu texts that are not bindings. `menus_data.py` shows `Ctrl+C`, `Ctrl+V` (Copy, Paste) and `Shift+C`
   (Commander / Search Commands) as shortcut texts, but Standard binds none of them. A newcomer reads the menu,
   presses the key, and nothing happens. Either bind them (proposals below) or make the menu show the active
   profile's binding only (2.6 already asks for that; check it covers these items).
7. Mouse gestures and the matcher. `match_press` picks the gesture with the most modifiers that are a subset of
   the held ones, ties going to the first in the list. Consequences:
   - `Alt+Shift+LMB` matches both `Alt+LMB` orbit and `Shift+LMB` add with score 1; the first in the list wins,
     so it orbits. Harmless, but an explicit gesture is clearer (see proposal P1).
   - `Ctrl+Shift+LMB` resolves to `remove` (listed before `add`). Maya users use it to add; document or bind it.
   - `Alt+LMB` click without a drag starts an orbit; Blender users expect `Alt+click` to select a loop. The double
     click covers loops, so this is only a note.
8. Three-button mouse. Orbit works with `Alt+LMB`, dolly with `Alt+RMB` or the wheel, but pan needs the middle
   button in every Standard gesture (`Alt+MMB`, `Shift+MMB`). A laptop touchpad user cannot pan at all. This is
   the most important gap (P1).
9. Numeric keypad. All eight camera views need the keypad; there is no alternative key. Laptops without a keypad
   reach them only through the Cameras menu (P5).
10. Cursor settings.
    - `orbit_pivot` "Center": matches Maya (centre of interest) and Blender (view centre, "Orbit Around Selection"
      off). Sensible for a default; keep.
    - `orbit_style` "turntable": Blender and Maya default. Keep.
    - `zoom_to_cursor` true: Blender ships it off, 3ds Max ships it on, Maya off. True is friendlier for modeling
      and Classic already uses it; keep, but it is a small surprise for Blender users. Keep.
    - `wheel_step` 0.88 and `wheel_invert` false: forward zooms in, as in every compared program. Keep.
    - `drag_threshold` 4 px: Blender uses 3 px for the mouse and 10 for a tablet; 4 is fine. A pen tablet user
      will want more; the Cursor page allows up to 16. Keep.
    - `click_tolerance` 4 px for the right-click context menu: fine.
    - `orbit_speed` 0.3 degrees per pixel: about 108 degrees across a 360 px drag; close to Blender. Keep.
11. Rationale text in 3.3. "Q W E R ... Houdini" is wrong: Houdini uses `S` select, `T` move, `R` rotate, `E`
    scale. Modo uses `W E R`. Replace Houdini by Modo in the sentence. "Modo and 3ds Max number the component
    levels" is right, but Max's 3 is Border and 4 is Polygon, so a Max user pressing 4 lands in Model mode.

## 4. Proposed changes to Standard

| Id | Action or gesture | Old binding | New binding | Reason |
|---|---|---|---|---|
| P1 | mouse: pan | `Alt+MMB`, `Shift+MMB` | add `{"button": "left", "mods": ["alt", "shift"], "op": "pan"}` before the `Alt+LMB` orbit | Laptop pan without a middle button; same as Modo (`Alt+Shift+LMB` pan). Score 2 beats the two score-1 gestures. |
| P2 | mouse: dolly | `Ctrl+MMB`, `Alt+RMB`, wheel | add `{"button": "left", "mods": ["alt", "ctrl"], "op": "dolly"}` | Modo convention; completes the one-button set (orbit, pan, dolly with LMB only). |
| P3 | `object.duplicate` (new action over the Duplicate menu item `m_duplicate`) | none | `Ctrl+D` | Maya, Unity, Unreal, Blender Industry Compatible and Modo all use `Ctrl+D`. Needs a core action first. |
| P4 | `edit.copy`, `edit.paste` (new actions, the menu items exist) | none, menu shows `Ctrl+C` / `Ctrl+V` | `Ctrl+C`, `Ctrl+V` | Universal desktop convention; the menu already promises it. |
| P5 | camera views without a keypad | keypad only | secondary keys in viewport scope: `camera.front` `Alt+1`, `camera.right` `Alt+3`, `camera.top` `Alt+7`, `camera.perspective` `Alt+5` (no `&` mnemonic exists in the menus, so Alt+digit is free) | Laptop users; digits mirror the keypad, so nothing new to learn. Alternative: a view quick menu on the backtick key, as Blender's view pie. |
| P6 | `view.frame_all` | `A` | `A`, secondary `Home` | Blender users press `Home` to frame all; the fallback costs nothing. |
| P7 | `view.frame_default` | `Home` | `Shift+Home` | Frees `Home` for P6; reset is a rarer action. |
| P8 | `view.hide_selected`, `view.unhide_all` (new actions over Hide Selected / Unhide) | none | `H`, `Alt+H` (viewport) | Blender default and Modo; `Ctrl+H` (Maya) is the second choice. One of them is needed: every program has a hide key. `Alt+H` is free (no menu mnemonics). `H` in viewport scope does not clash with anything in Standard. |
| P9 | `app.commander` (Search Commands) | none, menu shows `Shift+C` | `F3`, secondary `Ctrl+K` (check `Ctrl+K` is free) | `F3` is Blender's search, `Ctrl+K` Unity's and many desktop apps'. `Shift+C` is the reference program's key and fits Classic, not Standard. |
| P10 | `mode.points` ... `mode.model`, `tool.inset`, `tool.line_cut`, `tool.weld`, `tool.pen`, `tool.line_pen` | scope global | scope viewport | Plain keys must not fire while a panel has focus (3.4 above); Classic already does this. |
| P11 | `camera.perspective` | `Num+5` | `Num+5` toggles perspective / parallel; `Ctrl+Num+5` removed or kept as parallel | Blender's `Num+5` is a toggle; a second press doing nothing reads as a bug. Needs a toggle action (`camera.toggle_parallel`). |
| P12 | mouse: `Ctrl+Shift+LMB` | resolves to remove | add `{"button": "left", "mods": ["ctrl", "shift"], "op": "add"}` | Maya adds with `Ctrl+Shift`; removing is never expected on that combination. |
| P13 | `object.make_editable` | `Alt+C` | keep `Alt+C` | Checked: no menu title in `quartz_studio` uses an `&` mnemonic today, so Alt+letter and Alt+digit keys are free. Blender uses `Alt+C` (Convert). If menu mnemonics are ever added, `&C` must be avoided. No change. |

Not proposed, on purpose: plain MMB pan (3ds Max, Unity) instead of MMB orbit, and RMB fly navigation (Unity,
Unreal). Both would break the Blender half of the scheme or the right-click context menu; a "Game engine" profile
(5.3) carries them instead.

## 5. Additional built-in profiles worth shipping later

Each lists only what differs from Standard (after the P changes above). Everything not listed is the same.

### 5.1 Blender-like

Keys:
- `tool.move` `G`, `tool.rotate` `R`, `tool.scale` `S` (modal transform where possible; otherwise the tools).
- `tool.select` `W` (cycles box and lasso in Blender); drop `Q`.
- `tool.select_all` `A`, `tool.deselect_all` `Alt+A`, `tool.invert_selection` `Ctrl+I`.
- `view.frame_selection` `Num+.`, `view.frame_all` `Home`, `view.frame_default` none.
- `camera.perspective` `Num+5` toggle; `camera.*` as Standard (already Blender).
- `tool.extrude` `E`, `tool.bevel` `Ctrl+B`, `tool.inset` `I`, `tool.loop_path_cut` `Ctrl+R`, `tool.line_cut` `K`, `tool.weld` `M`.
- `edit.delete` `X`, `Delete`. `object.duplicate` `Shift+D`.
- `view.hide_selected` `H`, `view.unhide_all` `Alt+H`, `view.isolate` `Num+/`.
- `mode.model` `Tab` (toggle with the last component mode) in addition to `4`.
- `app.commander` `F3`. `object.make_editable` `Alt+C`.
Mouse: remove the `Alt` gestures (orbit `MMB`, pan `Shift+MMB`, dolly `Ctrl+MMB` only); `Shift+LMB` toggles
instead of adding (needs a `toggle` op). Cursor: `zoom_to_cursor` false, `drag_threshold` 3.

### 5.2 Maya-like

Keys:
- `mode.points` `F9`, `mode.edges` `F10`, `mode.polygons` `F11`, `mode.model` `F8`.
- `edit.redo` `Shift+Z`, `Ctrl+Y` (Maya users also press `Z` for undo: optional `edit.undo` secondary `Z`).
- `tool.extrude` `Ctrl+E`, `tool.bevel` `Ctrl+B` (same as Standard); `tool.inset`, `tool.line_cut`, `tool.weld`,
  `tool.loop_path_cut` unbound (Maya reaches them through marking menus).
- `object.duplicate` `Ctrl+D`, `view.hide_selected` `Ctrl+H`, `view.unhide_all` `Ctrl+Shift+H`, `view.isolate` `Shift+I` (check).
- Camera keypad views unbound; a quick menu on `Space` (hotbox equivalent) if one is built.
- `1`, `2`, `3` are smoothness display levels in Maya; leave them unbound rather than mode keys.
Mouse: Alt scheme only (drop `MMB` orbit, `Shift+MMB`, `Ctrl+MMB`); `Shift+LMB` toggles, `Ctrl+Shift+LMB` adds,
`Ctrl+LMB` removes. Cursor: `zoom_to_cursor` false.

### 5.3 Game engine (Unity and Unreal)

Keys:
- `tool.select` unbound (`Q` is Unity's hand tool and Unreal's select; keep `Q` select as Unreal does).
- `object.duplicate` `Ctrl+D`, `view.hide_selected` `H`, `view.unhide_all` `Ctrl+H` (Unreal) (check).
- `camera.perspective` `Alt+G`, `camera.front` `Alt+H`, `camera.top` `Alt+J`, `camera.right` `Alt+K` (Unreal) (check);
  these replace the P5 `Alt+digit` view keys in this profile. No menu mnemonic blocks them today.
- `app.commander` `Ctrl+K`.
Mouse: plain `MMB` pans (drop `MMB` orbit, `Shift+MMB`, `Ctrl+MMB`); `RMB` drag looks around with `W A S D Q E`
flying (needs a fly op), a right click without drag still opens the context menu (the `click_tolerance` test already
separates them). Cursor: `orbit_pivot` "Center", `zoom_to_cursor` false.

3ds Max-like is lower priority: its `Alt`-free scheme (`MMB` pan, `Alt+MMB` orbit, `Ctrl+Alt+MMB` zoom), `Alt+LMB`
remove and `Ctrl+LMB` add, and `F`, `T`, `L`, `P` view keys differ enough that a Max user is better served by it than
by Standard; ship it after the three above if users ask.

## 6. Recommendations on the open points (controls.md section 7)

1. Name of Classic. Keep "Classic" in the interface and show the reference program only in the profile's tooltip or
   description if rule 0.3 allows a description; otherwise keep "Classic". The id stays `classic` either way, so
   the owner can flip `CLASSIC_NAME` later at no cost. Recommendation: do not change it now.
2. Selection keys in Classic. Do not change Classic (it must equal today, and tests pin it). The owner adds `9`, `0`,
   `8` in his own user profile based on Classic; a one-click "Add the reference program's selection keys" is not
   worth building.
3. Orbit pivot of Standard. Keep "Center" as the default: it matches Maya and Blender, and the Cursor page and the
   Cameras > Navigation menu change it. Add "Object" (orbit around the selection) as the first suggestion in the
   Cursor page's help text, since many newcomers look for "orbit around selection".

## 7. Open items left by this review

- Several cells of section 2 are marked "(check)"; verify them against the programs' current documentation before
  quoting the table in user-facing help.
- P3, P4, P8, P9, P11 need new core actions before a binding can exist; P1, P2, P5 to P7, P10, P12, P13 are data
  changes in `STANDARD` plus the matching rows of controls.md 3.3 and the tests that pin Standard.
- After any change, rerun the conflict test with the full registry installed (modeling tools included).
