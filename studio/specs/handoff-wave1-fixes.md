# Handoff: wave 1 fix pass audit

Audit by reading only, 20/11/2026 about 10:40. The fix pass was cut off by the usage limit at about 07:08,
before it reported. Sources: the two reviews (function and regression) in the wave 1 scratchpad
`reviews.txt`, and the current files. Last write times of the touched files: `controls/__init__.py` 06:57:45,
`app.py` and `widgets/menu_bar.py` 06:57:56, `widgets/tool_palette.py` 06:59:31,
`tests/test_controls_widgets.py` 06:59:53, `controls/editor.py` and `modeling/select_interaction.py` 07:02:50,
`tests/test_controls_editor.py` and `tests/test_smoke.py` 07:03:14, `controls/dispatch.py` 07:04:49,
`tests/test_controls_dispatch.py` 07:05:20, `SPEC.md` 07:07:59.

No test suite was run for this audit (the final run and the build were running). One probe of a few seconds
called `dispatch._plain_text` on keypad Enter, Plus and 1 with Shift: it returned `Shift+Enter`, `Shift++`,
`Shift+1` and raised nothing. Whether the new tests pass is left to the final run's log.

## Defects

| # | Sev | Defect (review) | Verdict | Evidence in the current code | Test now covering it | Left to do |
|---|---|---|---|---|---|---|
| 1 | high | Numpad TypeError in `dispatch._plain_text` (function) | FIXED | `controls/dispatch.py` 91-93: `QKeyCombination(mods, Qt.Key(_int(ev.key())))`, mods built as `Qt.KeyboardModifier(... & ~KeypadModifier)`. Only use of `QKeyCombination` in the file. Called from `lookup` 192-194 only when the exact text misses. Probe above confirms no exception. | `test_controls_dispatch.py::test_keypad_keys_fall_back_to_the_plain_key` (637: Enter, Plus, Minus, 1, 2, 3, Delete, Asterisk, both profiles, three scopes, plus Shift+keypad Enter); `test_modal_and_modifier_lookups` (keypad Enter confirms) | No end-to-end test of the reviewer's two scenarios: Polygon Pen stroke ended by numpad Enter in Classic, and numpad 1 held plus left drag panning. Both go through `lookup`, so they should work; confirm in the final run or with the reviewer's `kpr.py`. |
| 2 | medium | Start-up 41% slower: `register_action` calls `refresh` 231 times (regression) | FIXED (timing not re-measured) | `controls/__init__.py` 45 `_DEFER`, 102-107 `refresh` only marks pending while deferred, 110-123 `deferred_refresh()` context manager (nestable, rebuilds once on exit). `register_action` 130-139 still calls `refresh()`, which is now a no-op inside the block. `app.py` 130 wraps `ext_install.install(window)` in `controls.deferred_refresh()`; `widgets/menu_bar.py` 1208 (`add_menu`) and 1221 (`add_entries`) wrap their entry loops. | `test_controls_dispatch.py::test_extension_menus_rebuild_shortcuts_once_per_install` (518: 41 entries, nested submenu, counts `dispatch.refresh` calls == 1 per `add_menu`, 0 inside an outer block and 1 on exit; the keyed item still fires) | Start-up time with the extension was not re-measured; the "within 30% of before" criterion is unverified. `app.main` still rebuilds twice (once on leaving the block in `install_extensions`, again at `app.py` 153 `controls.refresh()`); harmless but one rebuild is redundant. |
| 3 | low | Rail tooltips of Move, Rotate, Scale, Pen show no binding (function) | FIXED | `widgets/tool_palette.py` 299-307 `RAIL_ACTIONS` (tool.move, tool.rotate, tool.scale) and `PEN_ACTIONS` (tool.pen, tool.line_pen); `_tooltip` 310-315 via `controls.tooltip`; `refresh_tooltips` 434-442 sets them, connected to `hub.profileChanged` at 432. | `test_controls_widgets.py::test_rail_transform_and_pen_tooltips_follow_the_profile` (507) | None found. |
| 4 | low | Editor category list shows a horizontal scrollbar (function) | FIXED | `controls/editor.py` 580 `setFixedWidth(CATEGORY_W)`, 583 `ScrollBarAlwaysOff`; `_fill_categories` 640-643 now sizes items `QSize(0, ROW_H)` instead of `CATEGORY_W`. | `test_controls_editor.py::test_dialog_fits_and_every_size_is_in_the_norm` (assert at 188 on the policy) | Visual check of the Keyboard page not repeated. |
| 5 | low | Selection options card `LABEL_WIDTH` 160 vs contract 120 (function) | NOT FIXED (by choice) | `modeling/select_interaction.py` 30 `LABEL_WIDTH = 160`, used at 810. Documented as a deviation in `SPEC.md` 1492-1493. | none | Needs the owner's decision: confirm 160, or go back to 120 with a shorter label. |
| 6 | low | `test_every_visible_control_is_wired` leaves the Controls dialog open (regression) | FIXED | `tests/test_smoke.py` 478-491: collects every `ControlsDialog`, `close()` and `deleteLater()`, then asserts none is visible. | the same test | The smoke timing gain (42 s back to about 27 s) is not re-measured. |
| 7 | low | Editor opens in 2.0 s and keeps about 2,900 widgets after closing (regression) | PARTLY | Widget lifetime fixed: `controls/editor.py` 1611-1619 `hideEvent` schedules `_release`, which `deleteLater()`s the dialog when not visible; `dialog_for` 1635-1640 drops invalid wrappers and `open_editor` 1643-1661 builds a new one. `SPEC.md` 1456-1458 describes it. Opening speed not addressed: no lazy building of rows per category (no such code in `editor.py`). | `test_controls_editor.py::test_closed_dialog_is_freed_and_reopens_fresh` (123) | Opening still costs about 2 s with the extension (not re-measured). Optional: build rows only for the visible category. |
| 8 | low | `dispatch._WINDOWS` holds strong references (regression) | FIXED | `controls/dispatch.py` 41 `_WINDOWS`, 484-493 `_windows()` keeps only live `weakref.ref` entries checked with `_valid`, 511-512 appends `weakref.ref(window)`. `SPEC.md` 1462 says so. | `test_controls_dispatch.py::test_dropped_window_is_freed_with_its_key_filter` (558) | None found. |
| 9 | low | Broad `except Exception` in `editor.py` 1607 and `select_interaction.py` 258 (regression) | FIXED | `editor.py` 1604-1609 now catches only `ImportError` around the import and calls `apply_native_titlebar` outside the try. `select_interaction.py` 256-259 catches `(AttributeError, ValueError, TypeError, np.linalg.LinAlgError)`; `numpy as np` is imported at line 6. | none (no test needed) | None. Note: `apply_native_titlebar` errors now propagate out of `showEvent`; acceptable but not logged. |

## Loose ends, most serious first

1. The fix pass never reached its test run or its report. Every new test above (`test_keypad_keys_fall_back_to_the_plain_key`,
   `test_extension_menus_rebuild_shortcuts_once_per_install`, `test_dropped_window_is_freed_with_its_key_filter`,
   `test_closed_dialog_is_freed_and_reopens_fresh`, `test_rail_transform_and_pen_tooltips_follow_the_profile`, the
   smoke close-out) is unverified until the final run's log is read. All four touched test files register tests by
   `globals()` discovery in `_run_as_script` (dispatch 716-719, editor 594, widgets 624, smoke 766), so no test is
   left unregistered.
2. Start-up time with the extension (medium defect 2) and Controls editor open time (defect 7) were not
   re-measured after the fix. The regression reviewer's probes (`perf.py`, `profext.py`, `editor_open.py` in
   `%TEMP%\qz\wave1\reviewer\`) can be rerun once the machine is idle.
3. No end-to-end test of numpad Enter ending a Polygon Pen stroke or numpad 1 held plus left drag panning in
   Classic; the fix is proven at `lookup` level only.
4. `app.main` rebuilds shortcuts twice at start (exit of `deferred_refresh` in `install_extensions`, then
   `controls.refresh()` at `app.py` 153). Remove one; low cost either way.
5. `LABEL_WIDTH = 160` in the selection options card remains an owner decision (SPEC.md 1492).
6. Controls editor opening speed: no lazy row building. Only the lifetime half of defect 7 is done.
7. `editor.py` `hideEvent` deletes the dialog on any non-spontaneous hide. Code that hides and reshows it across
   an event-loop turn (instead of in the same turn, as the test does) gets a deleted dialog; callers must go
   through `open_editor`. Nothing in the package was found doing that, but it is a new constraint.
8. SPEC.md 1452-1464 matches the code read here (dialog deleted on close, keypad fallback, `deferred_refresh`,
   weak window references, rail tooltips). No SPEC text was found describing something absent from the code.
   README.md was not checked against these changes.
9. Checked and not a defect: `menu_bar.py` 1246-1251 still creates a fallback `QShortcut` for extension items
   when `controls_filter` is not yet installed, but `dispatch._build_shortcuts` 471-473 disables any foreign
   shortcut whose key it now serves and 477-481 replaces `bar.extension_shortcuts`, so the key is not served twice.
