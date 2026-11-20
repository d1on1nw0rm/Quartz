# Handoff: UX critique of wave 1

Read-only review, 20/11/2026, closing step of the night run. Sources: screenshots in `%TEMP%\qz\wave1\final\` (F) and `%TEMP%\qz\wave1\review\shots\` (R), SPEC.md section 9 "Crystal", `D:\Markdown\DesignPx.md`, specs\controls.md section 4, specs\interface.md sections 1 to 3, specs\attributes-mesh.md section 3. Sizes were checked against the constants in the widget code; nothing was edited and nothing was run.

Pixel norm used below: multiples of 2; main range 1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256; derived values (10, 14, 18, 20, 28, 192, 320) only when the main range would deform the layout by more than 12 percent. Card radius 10, button radius 6, card spacing 4, 8, 12.

## Findings, ordered by how much the owner would notice them

### 1. Empty Attribute Manager for an editable object looks broken, not intentional
- Screenshots: R `am_editable.png`, F `am_editable_1920.png`, F `window_standard_1280.png` (right column, middle card).
- What is seen: header "Polygon Object [Cube]" and one summary line "8 points . 6 polygons", then about 450 px (1920) or 230 px (1280) of empty card. No hint of what to do, no divider, no muted placeholder. Next to the full Text page (F `fix_am_text_crop.png`) it reads as a failed load.
- File: `quartz_studio\widgets\attribute_manager.py`, around the summary label (line 438).
- Proposal: keep the summary row at `theme.ROW_H`, then add one muted hint row below it, 12 px font, top margin `theme.SPACE_2` (8), text like "Editable mesh. Use the Mesh menu or the point, edge and polygon modes to edit it." Optionally an outline icon of 32 centered at 64 px from the header. Under the hint, a 1 px divider in the card border token so the empty area reads as the end of content.

### 2. Controls editor, Keyboard page: horizontal scrollbar and size grip in the category list
- Screenshot: F `controls_keyboard_1280.png`, left column bottom (about x 33 to 220, y 548 to 556).
- What is seen: a horizontal scrollbar under "Sculpt" and a stray corner grip at about x 218, y 553. Category names are short, so the horizontal bar is noise; the list also ends with "Sculpt" cut in half.
- File: `quartz_studio\controls\editor.py`, category list built with `CATEGORY_W = 192`.
- Proposal: `setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` on the category list and keep `CATEGORY_W = 192` (valid derived value). Row height of the list at `ROW_H = 28` is fine; make the visible height a whole number of rows (list height = 13 x 28 = 364 inside the 640 dialog) so no row is cut.

### 3. Controls editor, Keyboard page: table scrollbar overlaps the "Scope" header
- Screenshot: F `controls_keyboard_1280.png`, right edge of the table header (about x 920, y 166 to 188).
- What is seen: the vertical scrollbar starts inside the header row, so the header looks cut on the right and "Scope" sits 8 px from a bar.
- File: `quartz_studio\controls\editor.py`, table built with `KEYS_W = 320`, `SCOPE_W = 96`.
- Proposal: give the table a right viewport margin of 8 (SPACE_2) or place the scrollbar below the header; keep `SCOPE_W = 96`.

### 4. Controls editor, Mouse page: last visible row cut in half and a heavy capture pad
- Screenshot: F `controls_mouse_1280.png`, row "Right click" at y about 452, pad at bottom left.
- What is seen: the gesture list stops mid-row (no fade, no whole-row height). The capture pad (`PAD_W = 256`, `PAD_H = 96`) is a large dark box with centered text that pulls the eye more than the list, and "Reset Mouse" floats alone at the right, not aligned with the pad top or bottom.
- File: `quartz_studio\controls\editor.py`, `GESTURE_ROW_H = 32`, `PAD_W`, `PAD_H`.
- Proposal: list height a whole multiple of `GESTURE_ROW_H` (for example 10 x 32 = 320); `PAD_H = 64` (main range) with the text on one line; put "Reset Mouse" on the same baseline as the bottom of the pad (align bottom), gap 8.

### 5. Controls editor: tab bar 4 px left of the profile row
- Screenshot: F `controls_keyboard_1280.png` and `controls_mouse_1280.png`, "KEYBOARD" at x about 29 against "PROFILE" at x 33 and search field at x 33.
- File: `quartz_studio\controls\editor.py`, `INSET = 16`, tab bar margins.
- Proposal: same left inset for header, note, tab bar and pages (`INSET = 16`); the tab text left padding 0 or the underline starting at the text start.

### 6. Controls editor: task "change the key of one tool" in under five clicks
- Path seen in F `controls_keyboard_1280.png`: the active profile is "Classic", built in and read only (note line "Built-in profiles cannot be changed."). The real path is: open editor (1), Duplicate (2), confirm name (3), click "Tools" or type in search (4), click "+" on the row or the chip (5), press the key, then Close (6).
- Verdict: six clicks on the first edit, four on later edits. It misses the target only because of the duplicate step.
- Proposal (spec, not a pixel change): when the user clicks a "+" or a chip on a built-in profile, offer the duplicate inline in the banner (`BANNER_H = 40` already exists) with the button "Duplicate and edit", so the first edit is five clicks. Also: the "+" glyphs next to chips are very dim (disabled token) on a built-in profile; they look clickable but are not. Either hide them or show them at full secondary token with the duplicate banner on click.

### 7. Coordinates card: off-grid vertical rhythm, rows nearly touch
- Screenshots: R `coords_1920.png`, F `window_standard_1280.png` (bottom right).
- What is seen: field rows at a 22 px pitch with a 2 px gap, so the three rows look like one block; the "Reset Transformation" button (`RESET_H = 20`) is shorter than the neighbouring 24 to 28 buttons and touches the header right edge.
- File: `quartz_studio\widgets\coordinates.py`.
- Proposals: `GRID_GAP = 4` (was 2); `GRID_COLUMN_GAP = 8` (was 6); `HEADER_PAD = 12` (was 10); `TITLE_H = 16` (was 14); `AXIS_W = 16` (was 14); `RESET_H = 24` (was 20) with button radius 6; keep `ROW_H = 20` only if `theme.COORDINATES_H` cannot grow by 6, otherwise `ROW_H = 24`. Check that `theme.COORDINATES_H` absorbs the extra height (header 24 + titles 16 + 3 x 24 + 2 x 4 gaps + margins).

### 8. Attribute Manager page rhythm: off-grid indent and group spacing
- Screenshot: F `fix_am_text_crop.png`.
- What is seen: rows read well and fields line up, but the label column starts 2 px right of the header icon and groups are packed at 2 px.
- File: `quartz_studio\widgets\attribute_manager.py`: `LABEL_INDENT = 10`, `GROUP_SPACING = 2`, `HEADER_ICON = 18`.
- Proposals: `LABEL_INDENT = 8` (aligns with `theme.SPACE_2` used by the header margin); `GROUP_SPACING = 4`; `HEADER_ICON = 16`. `LABEL_WIDTH = 120` is a valid derived value; keep it.

### 9. Selection options card (Brush Selection): header off the card grid, wide radius field, loose bottom
- Screenshots: F `brush_points_1280.png` (right column, card between Objects and Attributes), F `selection_options_card.png`.
- Header mismatch with its neighbours (most visible item of this card): the title "BRUSH SELECTION" starts at x about 876 while "OBJECTS" and "ATTRIBUTES" start at x 884, and the card has no 1 px divider under its header, which both neighbours have. Row labels start at x 886, the Attribute Manager summary at x 880. Proposal: build the header with the same header helper the Objects and Attributes cards use (same left padding `theme.CARD_PADDING` and same divider), and indent rows by `theme.SPACE_2` (8) like the Attribute Manager.
- What is seen: the "Radius" field stretches about 280 px for a value like "10 px"; checkboxes sit at the field column, good. "Reset" is a separate row at the bottom right with more space under the last checkbox than between rows.
- File: `quartz_studio\modeling\select_interaction.py` (options card builder).
- Proposal: radius field fixed width 96 (main range); row height 28; "Reset" button height 24, radius 6, right aligned on the header row (same pattern as "Reset Transformation") or under the rows with a top gap of 8.

### 10. Top row with eleven menus, the mode pill and the overflow chevron
- Screenshots: F `top_row_1920.png`, F `top_row_1280.png`, F `overflow_menu_1280.png`, F `page_menu_1280.png`.
- 1920: all eleven menus fit, then the "Model" pill, then the four mode buttons centered. Legible. The undo, redo and render icons at the right are very dim (disabled token) and almost vanish; at 1280 in `window_standard_1280.png` they are normal. Good.
- 1280: menus stop at "UV" and the chevron opens Sculpt, Animate, Render, Extensions. Legible. The chevron sits 12 px from "UV" and 24 px from the pill; make both 12 (`theme.SPACE_3`).
- The page switcher is the "Model" pill itself (`page_menu_1280.png`: Model, Materials, UV Edit, Script, Render). There is no separate page switcher, so "Materials" and "Render" appear twice in the top row (menu and page). Proposal: no pixel change; a note in interface.md that the pill is the page switcher, and a label on hover "Page".
- File: `quartz_studio\main_window.py`, top row layout.

### 11. Angle unit shown two ways on the same screen
- Screenshot: F `am_cloner_1920.png`: Attribute Manager "Rotation (H, P, B)" shows "0 deg"; the Coordinates card right below shows "0 °".
- Files: `quartz_studio\widgets\attribute_manager.py` (vector suffix for angles) and `quartz_studio\widgets\coordinates.py` (`COLUMN_UNITS`).
- Proposal: one unit string for angles in the whole app, "°" with no space before it ("0°"), as Crystal favours compact numeric fields.

### 12. Attribute Manager for a Cloner: wide combos and a heavy empty tail
- Screenshot: F `am_cloner_1920.png`, right column.
- What is seen: "Mode" and "Clones" combos stretch about 330 px for one-word values; the vector rows (X, Y, Z fields) are well aligned and read well. Below "Rotation (H, P, B)" about 170 px of empty card, acceptable here because the page has content.
- Proposal: cap single-value combos and spin boxes at 192 (derived, already used as `CATEGORY_W`) in `attribute_manager.py`; leave vector rows full width.

### 13. Controls editor, Cursor page and conflict banner
- Screenshots: F `controls_cursor_1280.png`, F `controls_conflict_1280.png`.
- Cursor page: groups with uppercase headers and 1 px dividers are consistent with the cards. The last row ("Drag Threshold" and the field under it) is cut at the bottom edge like the Mouse page; same fix (whole-row heights, `FORM_ROW_H = 28`). On a built-in profile every field is drawn disabled, which is correct but makes the page look broken at first sight; the note line above the tabs is the only explanation and is 12 px muted text. Proposal: in read-only state use the secondary text token for values instead of the disabled token, and make the note a banner (`BANNER_H = 40`) with the "Duplicate" action.
- Conflict banner: red 1 px border, message left, three buttons right, radius consistent; reads well. The category list horizontal scrollbar (finding 2) is still present here.

### 14. Splitter bar
- Screenshots: F `splitter_hover_crop.png`, F `fix_splitter_drag_crop.png`, R `splitter_hover.png`, R `splitter_drag.png`.
- Hover shows a rounded accent line across almost the full card width between Objects and Attributes; clear and in the Crystal accent. No clipping. The R crops are 288 and 293 bytes and carry no usable content. Only check: hit area at least 8 px while the drawn line stays 2 to 4 px (`quartz_studio\widgets\splitter.py`), and the line inset 12 from the card edges to match the card padding.

## Not checked
- Splitter drag in motion, the sphere AM page (R `am_sphere.png`), brush and pattern selection shots (F `brush_points_*.png`, R `clean_*.png`).
- No widget was measured at runtime; values come from the code constants and the screenshots.
