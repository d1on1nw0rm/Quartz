# Quartz Studio: pixel metrics contract

Scope: every size in px that the interface of Quartz Studio draws or lays out, audited against the owner's
pixel norm (`D:\Markdown\DesignPx.md`, 16/11/2026, restated by the owner on 20/11/2026). This file is the
contract for the metrics sweep. It changes sizes only: no behaviour, no colours, no texts, no new controls.

Ground truth used: the source as it was on 20/11/2026 at about 02:20, a regex scan of the UI files, the
generated stylesheet text of `theme.stylesheet()` and an offscreen run of `MainWindow` at 1920 x 1010 and
1280 x 720. Line numbers are those of that moment; other fleets are editing tonight, so a builder finds every
item by its name first and uses the line only as a hint.

Rules that hold for every builder: no comments and no docstrings in code; the simplest change that works;
the window shows only controls that do something; Python only as `.\.venv\Scripts\python.exe` from
`D:\Apps\Quartz\studio`; never kill a process by name; do not run `build.ps1`; offscreen probes with
`$env:QT_QPA_PLATFORM='offscreen'` and `$env:QT_QPA_FONTDIR='C:/Windows/Fonts'`.

---

## 1. The norm

### 1.1 Allowed values

- `0` is always allowed (no size).
- `1` is allowed only for lines: borders, separators, hairline rules, focus rings, pen widths of lines, a
  1 px inset that equals a 1 px border, and half-pixel offsets (0.5) that put a 1 px pen on the pixel grid.
  Never as padding, margin, spacing, gap, font size, letter spacing or element size.
- Main range (used without arithmetic): 1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 72, 96, 128, 256, 512, 1024.
- Below 128 the complete list is closed (DesignPx line 13: "Abaixo de 128 vale so a lista acima"):

  `2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 88, 96, 112, 120`

  This list already contains the six family the owner named tonight (6, 12, 18, 24, 36, 48, 72, 96) and the
  sums and differences DesignPx lists (10 = 8+2, 14 = 16-2, 18 = 16+2, 20 = 16+4, 28 = 32-4, 36 = 32+4,
  40 = 32+8, 44 = 48-4, 56 = 64-8, 80 = 64+16, 88 = 96-8, 112 = 128-16, 120 = 128-8).
- From 128 up: any multiple of 16, or any value `a + b` or `a - b` with `a` and `b` taken from the main range
  without 1 (DesignPx lines 12 and 13: 136 = 128+8, 488 = 512-24 and so on).
- Forbidden: odd values other than 1, decimals in px (9.5, 14.5, 0.45), and every value outside the rules
  above (DesignPx names 30, 34, 42, 54, 60, 62, 84, 85, 126, 170, 340, 875).
- Negative values (negative margins, offsets) follow the same rules by absolute value.
- Units that are not px stay as they are: percent, ratios, opacity and alpha, angles, counts, durations in
  ms, world units (cm), unitless line heights, Qt stretch factors, `QFont.PercentageSpacing`.

### 1.2 Reading of tonight's words

The owner said: "2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, then multiples of 6, and the additions between
multiples of 2 and of 6". Read literally, "multiples of 6" would admit 30, 42, 54, 60 and 84, which DesignPx
line 15 forbids by name, and "a power of two plus a six-family value" would admit 22 (16+6), 26 (2+24),
34 (16+18, forbidden by name), 38, 50, 52. This contract adopts the closed list of 1.1. Every replacement value
below is in the closed list, so it also satisfies the wider reading; if the owner later confirms the wider
reading, only `theme.PX_BELOW_128` changes and nothing in this sweep needs to be undone.

### 1.3 Choosing a replacement

`theme.snap_px(v)`, used for every replacement in this file unless the row gives a reason for another value:

1. `v` already allowed: keep it. The 12 percent preference does not move values that are already allowed.
2. `abs(v) < 2` (pen widths and lines): 1 when `abs(v) <= 1.5`, else 2.
3. Take the nearest main-range value (1 excluded; tie: the smaller). If it differs from `v` by at most
   12 percent of `v`, use it.
4. Otherwise take the nearest allowed value (tie: the smaller).

`theme.snap_px_up(v)` returns the smallest allowed value that is at least `v` (used for widths that must fit
their content).

Examples the guard pins (section 11.2): 22 -> 24, 26 -> 24, 30 -> 32, 34 -> 32, 37 -> 36, 19 -> 18, 3 -> 2,
5 -> 4, 7 -> 6, 85 -> 88, 68 -> 64, 125 -> 128, 118 -> 128, 300 -> 304, 385 -> 384, 1349 -> 1344,
890 -> 896, 200 -> 200 (128+72), 260 -> 260 (256+4), 1.4 -> 1, 1.5 -> 1, 1.6 -> 2, 2.6 -> 2, 3.2 -> 4,
10.67 -> 10, 13.33 -> 12, 6.5 -> 6, 2.5 -> 2; `snap_px_up(138)` = 140, `snap_px_up(408)` = 416,
`snap_px_up(325)` = 328. These values were checked with a script implementing 1.1 and 1.3.

### 1.4 What is in scope and what is exempt

In scope (must be allowed):

- every size constant in `quartz_studio/theme.py`;
- every px number in every stylesheet string (theme and widget-local);
- every literal or constant-derived size passed to `setFixedSize`, `setFixedWidth`, `setFixedHeight`,
  `setMinimum*`, `setMaximum*`, `setContentsMargins`, `setSpacing`, `setHorizontalSpacing`,
  `setVerticalSpacing`, `addSpacing`, `insertSpacing`, `setTextMargins`, `setIndentation`, `setIconSize`,
  `setMinimumSectionSize`, `QSize`, `QSizeF`, `setPixelSize`, and the width of every `QPen`;
- module and class constants that name a size in px (suffixes in 11.4);
- sizes of overlay elements painted in widgets (handles, markers, pills, badges, glyph boxes), hit
  tolerances in px and drag thresholds in px;
- icon canvas sizes and icon stroke widths (strokes in grid units, see 7.15).

Exempt (not checked, not changed by this sweep):

- sizes that follow the window: the width and height of the viewport, the heights the splitters give to
  the Object Manager and the Attribute Manager, any remainder after fixed parts;
- totals that are sums of allowed parts whose count varies (the dock width 396 = 10 buttons of 36 + 2 gaps
  of 12 + 2 pads of 6; the HUD width, which contains text; a chip width, which contains text);
- text metrics (text widths, the 1 or 2 px slack added to a text rectangle so glyphs are not clipped);
- glyph geometry inside an icon or an overlay glyph (path coordinates, arrow head shapes, pivot ticks):
  only the glyph box and the stroke width are in scope;
- world-space values (cm), ratios, alphas, angles, counts, durations;
- `widgets/title_row.py` and `widgets/sculpt_bar.py` (not in the window; SPEC 9.9.7), the older fallback
  painters that `icons.py` shadows (SPEC 9.11) except their `QPen` widths, and `build/` backups.

Qt measures QSS px and `setPixelSize` in device-independent pixels; the norm applies to those logical px.
High-DPI scaling multiplies them and is not part of the norm.

---

## 2. Fonts

Qt font sizes in pt are converted at 96 dpi (px = pt x 4 / 3). Rule: every font size is set in px
(`QFont.setPixelSize`, QSS `font-size: Npx`) and N is in the allowed set and at least 10. `setPointSize`,
`setPointSizeF` and `pt` in QSS are not used anywhere in the UI after the sweep.

| Where | Now | px at 96 dpi | Verdict | New |
|---|---|---|---|---|
| `theme.FONT_POINT_SIZE` (theme.py:156), QSS `*` (theme.py:264), `app.py:50`, `menu_bar.UI_POINT_SIZE` (menu_bar.py:35, 60, 73, 1018) | 9 pt | 12 | allowed, but in pt | `theme.FONT_PX = 12`, set as px |
| `theme.FONT_GROUP_POINT_SIZE` (theme.py:157; QSS 349, 541, 769; `common.header_font` common.py:121; coordinates.py:303) | 8 pt | 10.67 | violation | `theme.FONT_SMALL_PX = 10` |
| `theme.FONT_SMALL_POINT_SIZE` (theme.py:158; QSS 832; coordinates.py:305) | 8 pt | 10.67 | violation | `theme.FONT_SMALL_PX = 10` |
| Attribute section title `font-size: 10pt` (attribute_manager.py:476) | 10 pt | 13.33 | violation | `theme.FONT_TITLE_PX = 14` (override of snap 12: the title must stay above the 12 px body text) |
| Viewport label font `setPixelSize(11)` (viewport.py:914) and triad letters (viewport.py:2012) | 11 px | 11 | violation | `theme.FONT_PX` (12) |
| Modeling HUD `setPixelSize(12)` (interaction.py:144) | 12 px | 12 | allowed | `theme.FONT_PX` |
| `theme.HEADER_LETTER_SPACING` 1.0 px absolute (theme.py:159; common.py:124; coordinates.py:61; tags/widgets.py) | 1 px | 1 | violation (1 px used as a gap) | `theme.HEADER_TRACKING = 110`, applied as `font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, theme.HEADER_TRACKING)` |
| `title_row.py:143` `setPointSizeF(9)` | 9 pt | 12 | exempt file | unchanged |
| `command_bar.py:104` `setPixelSize(64)`, `icons.py:410` | glyph text | n/a | glyph geometry | unchanged |

The app scale is therefore 10 (uppercase card and section headers, status bar, column titles), 12 (all body
text, menus, fields, viewport labels), 14 (the Attribute Manager section title). 9 pt and 12 px render the
same; headers become 10 px instead of 10.67 px (6 percent smaller).

---

## 3. Theme tokens (`quartz_studio/theme.py`, owner M1)

### 3.1 Changed tokens

| Line | Token | Now | Verdict | New | Notes |
|---|---|---|---|---|---|
| 149 | `ICON_STROKE_W` | 1.6 | violation (grid stroke) | 2.0 | grid units of the 24-unit icon grid; also the px pen of the Object Manager check and cross glyphs |
| 176 | `SEGMENT_H` | 30 | violation | 32 | mode pill; 4 px above and below in the 40 px top row; `main_window.PAGE_BUTTON_H` follows (28) |
| 177 | `CHIP_H` | 26 | violation | 24 | project chip, attribute chips, pill radius 12 |
| 192 | `HUD_H` | 22 | violation | 24 | viewport HUD pill and camera plate |
| 197 | `COMMAND_BUTTON` | 30 | violation | 32 | Undo, Redo, Make Editable and every `IconButton` default |
| 210 | `FIELD_H` | 22 | violation | 24 | fields, combos, push buttons, field rows, coordinate fields |
| 215 | `COORDINATES_H` | 104 | allowed, but not the real height (127 today) | 128 | fixed height of the Coordinates card, section 7.11 |

### 3.2 Tokens that stay (allowed)

`SPACE_1` 4, `SPACE_2` 8, `SPACE_3` 12, `WINDOW_MARGIN` 8, `CARD_GAP` 8, `CARD_PADDING` 8, `CARD_RADIUS` 10,
`CONTROL_RADIUS` 6, `DOCK_RADIUS` 12, `MENU_RADIUS` 8, `ACCENT_BAR_W` 2, `FOCUS_RING_W` 1 (line), `TOP_BAR_H`
40, `APP_MARK` 20, `STATUS_BAR_H` 24, `CARD_HEADER_H` 28, `MENU_ROW_H` 28, `MENU_ICON` 16, `ROW_H` 24,
`RAIL_PAD` 6, `DOCK_BUTTON` 36, `DOCK_ICON` 24, `DOCK_PAD` 6, `DOCK_H` 48, `DOCK_BOTTOM` 12, `DOCK_GAP` 12,
`GHOST_BUTTON_H` 24, `NAV_BUTTON` 24, `TITLE_ROW_H` 28, `MENU_BAR_H` 32, `COMMAND_BAR_H` 40, `COMMAND_ICON`
18, `PALETTE_BUTTON` 36, `PALETTE_W` 48, `RAIL_W` 48, `PALETTE_ICON` 24, `PANEL_MENU_H` 24, `SPLITTER_W` 8,
`SEPARATOR_GAP` 8, `BUTTON_RADIUS` 6, `WINDOW_MIN_W` 1280 (1024+256), `WINDOW_MIN_H` 720 (multiple of 16).

### 3.3 New tokens and helpers

| Name | Value | Use |
|---|---|---|
| `PX_MAIN` | `(1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 72, 96, 128, 256, 512, 1024)` | main range |
| `PX_BELOW_128` | `(2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 88, 96, 112, 120)` | closed list below 128 |
| `allowed_px(v) -> bool` | 1.1 | `0` and `1` return True (the caller decides whether 1 is a line); non-integral values return False |
| `snap_px(v) -> int` | 1.3 | replacement value |
| `snap_px_up(v) -> int` | 1.3 | smallest allowed value at least `v` (searches even values upward) |
| `FONT_PX` | 12 | body text |
| `FONT_SMALL_PX` | 10 | uppercase headers, status bar, column titles |
| `FONT_TITLE_PX` | 14 | Attribute Manager section title |
| `HEADER_TRACKING` | 110 | percent letter spacing of uppercase headers |
| `HUD_ICON` | 16 | glyph box in the viewport HUD pill |
| `POPUP_GAP` | `SPACE_1` (4) | gap between a button and its fold-out, section 8.3 |
| `PX_TOKENS` | tuple of names | every px token above plus 3.2 (the guard reads it) |
| `NON_PX_TOKENS` | tuple of names | `ACCENT_TINT_AMOUNT`, `ACCENT_TINT_HOVER_AMOUNT`, `ACCENT_ALPHA`, `DOCK_ALPHA`, `ICON_STROKE_W`, `HEADER_TRACKING` |
| `LEGACY_TOKENS` | tuple of names | `FONT_POINT_SIZE`, `FONT_GROUP_POINT_SIZE`, `FONT_SMALL_POINT_SIZE`, `HEADER_LETTER_SPACING`; kept during the sweep so files of other builders keep importing; deleted by the integration step (section 12.4), which then empties this tuple |

### 3.4 Dead tokens to delete (no users in the package, tests or tools on 20/11 02:20)

`FRAME_SCALE` and `ref()` (theme.py:152, 230), `SCULPT_BAR_H` 37, `SCULPT_BUTTON` 30, `SCULPT_ICON` 22,
`VIEWPORT_MENU_H` 28, `PANEL_TAB_H` 24, `PANEL_ICON` 16, `RIGHT_COLUMN_W` 488, `OBJECT_MANAGER_H` 385,
`ATTRIBUTE_MANAGER_H` 475. M1 greps `theme\.<NAME>\b` over `quartz_studio`, `tests` and `tools` right before
deleting each one; a name that gained a user tonight stays and gets its snapped value instead.

### 3.5 Derived values inside `_base_qss()` (theme.py:253 to 260)

| Name | Now | New formula | New value |
|---|---|---|---|
| `tab_h` | `CARD_HEADER_H - 2` = 26 (violation) | `CARD_HEADER_H - 2 * ACCENT_BAR_W` | 24 (content) + 2 padding top + 2 border bottom = 28 |
| `chip_h` | `CHIP_H - 4` = 22 (violation) | `CHIP_H - SPACE_1` | 20 |
| `field_h` | `FIELD_H - 4` = 18 | `FIELD_H - 6` | 18 (18 + 2 x 2 padding + 2 x 1 border = 24) |
| `button_h` | `FIELD_H - 6` = 16 | `FIELD_H - 6` | 18 (push button total 24) |
| `pill` | `SEGMENT_H // 2 - 2` = 13 (violation) | `SEGMENT_H // 2 - 2` | 14 |

---

## 4. Stylesheet inventory (`theme._base_qss()`, owner M1)

Every px number in the generated text, by source line. Rows not listed are allowed and stay.

| Line | Selector | Property | Now | Verdict | New |
|---|---|---|---|---|---|
| 264 | `*` | font-size | 9pt | pt | `{FONT_PX}px` (12px) |
| 340 | `QMenu::indicator` | margin-left | 7px | violation | 6px |
| 349 | `QLabel#qsMenuSection` | font-size | 8pt | violation | `{FONT_SMALL_PX}px` |
| 410 | `QFrame#qsSegment[qsRole="modes"]` | border-radius | 15px | violation | 16px (`SEGMENT_H // 2`) |
| 413 | modes `QToolButton#qsIconButton` | border-radius | 13px | violation | 14px (`pill`) |
| 422 | `QPushButton` | min-height | 16px | allowed | 18px (`button_h`, total 24 with FIELD_H) |
| 454 | `QPushButton#qsChip` | border-radius | 11px | violation | 10px (`chip_h // 2`) |
| 456 | `QPushButton#qsChip` | min-height | 22px | violation | 20px (`chip_h`) |
| 511 | `QTabBar::tab` | border-radius | 13px | violation | 12px (`CHIP_H // 2`) |
| 512 | `QTabBar::tab` | padding | 3px 12px | violation | 2px 12px |
| 514 | `QTabBar::tab` | min-height | 16px | allowed | 20px (`CHIP_H - SPACE_1`, total 24) |
| 538 | `QPushButton#qsPanelTab` | padding | 0px 8px | allowed | 2px 8px 0px 8px |
| 539, 540 | `QPushButton#qsPanelTab` | min-height, max-height | 26px | violation | 24px (`tab_h`; 2 + 24 + 2 border = `CARD_HEADER_H` 28) |
| 541 | `QPushButton#qsPanelTab` | font-size | 8pt | violation | `{FONT_SMALL_PX}px` |
| 570 | `QPushButton#qsPanelMenu` | padding | 1px 8px | violation (1 as padding) | 2px 8px |
| 571 | `QPushButton#qsPanelMenu` | min-height | 16px | allowed | 20px (`PANEL_MENU_H - SPACE_1`, total 24) |
| 622 | `QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit` | padding | 1px 6px | violation | 2px 6px |
| 623 | same | min-height | 18px | allowed | 18px (`field_h`, total 24) |
| 662 | `QComboBox` | padding | 1px 20px 1px 6px | violation | 2px 20px 2px 6px |
| 663 | `QComboBox` | min-height | 18px | allowed | 18px |
| 743, 748 | `QSlider::groove`, `::sub-page` | height | 3px | violation | 4px (override of snap 2: a 4 px groove centres the 12 px handle on whole pixels) |
| 745, 750 | groove, sub-page | border-radius | 1px | violation (1 as a size) | 2px |
| 754, 755 | `QSlider::handle:horizontal` | width, height | 10px | allowed | 12px (keeps margin -4 with the 4 px groove) |
| 756 | handle | margin | -4px 0px | allowed | -4px 0px |
| 757 | handle | border-radius | 5px | violation | 6px |
| 769 | `QLabel#qsGroupTitle` | font-size | 8pt | violation | `{FONT_SMALL_PX}px` |
| 832 | `QStatusBar#qsStatusBar QLabel` | font-size | 8pt | violation | `{FONT_SMALL_PX}px` |
| 838 | `QFrame#qsProjectChip` | border-radius | 13px | violation | 12px (`CHIP_H // 2`) |

Allowed and unchanged (for the record): tooltip border 1, padding 4 8; menu bar spacing 0, padding 0 2, item
padding 4 10, radius 6; `QMenu` border 1, radius 8, padding 4; menu item min-height 28, padding 0 24 0 32,
radius 6; separator height 1, margin 4 8; menu icon padding-left 8; right arrow 10 x 10, padding-right 8;
indicator 14 x 14, radius 4; section padding 8 12 2 12; tool button radius 6, focus border 1; push button
border 1, radius 6, padding 2 12; chip padding 0 12; view menu radius 6, padding 0 8, min-height 24; tab
margin-right 4; panel tab border-bottom 2; scrollbars 8, handle min 24, radius 4; field border 1, radius 6;
inner line edit padding 0, min-height 0; spin buttons width 14; combo border 1, radius 6; drop-down 18;
down-arrow 8; popup border 1, radius 8, padding 4; popup item min-height 28, padding 0 8, radius 6; checkbox
spacing 6, indicator 14, border 1, radius 4; slider min-height 16; tree item min-height 24, accent bar 2;
header section padding 2 6; splitter handle 8; placeholder border 1, radius 10; card border 1, radius 10;
project chip border 1.

---

## 5. Widget-local stylesheets

| File:line | Rule | Now | Verdict | New | Owner |
|---|---|---|---|---|---|
| main_window.py:64 | `qsPlaceholder` border | 1px dashed | allowed | unchanged | M2 |
| main_window.py:117, 122 | page switcher pill | `SEGMENT_H // 2 - 2`, `SEGMENT_H // 2` | follows tokens (14, 16) | unchanged code | M2 |
| menu_bar.py:71 to 83 (`_menu_qss`) | border 1, paddings from tokens, separator 1, margin 4 | allowed | unchanged | M2 |
| menu_bar.py:73, 1018 | font-size | `{UI_POINT_SIZE}pt` | pt | `{theme.FONT_PX}px` | M2 |
| coordinates.py:291, 292, 299 | Reset button border 1, radius 6, padding 0 12; disabled field border 1 | allowed | unchanged | M5 |
| coordinates.py:303 | `qsCoordHeader` font-size, padding-left | 8pt, 10px | pt | `{theme.FONT_SMALL_PX}px`, 10px | M5 |
| coordinates.py:305 | `qsCoordTitle` font-size | 8pt | pt | `{theme.FONT_SMALL_PX}px` | M5 |
| attribute_manager.py:56 | spin buttons width 0 | allowed | unchanged | M5 |
| attribute_manager.py:61, 65 | `SPIN_STYLE` arrow width `ARROW_W` 16 | allowed | unchanged | M5 |
| attribute_manager.py:68 | `VECTOR_SPIN_STYLE` padding | 1px 2px | violation | 2px 2px | M5 |
| attribute_manager.py:476 | section title font-size | 10pt | violation | `{theme.FONT_TITLE_PX}px` | M5 |
| object_manager.py:271 | rename editor radius, padding | `CONTROL_RADIUS - 2` (4), 0 6 | allowed | unchanged | M5 |
| tool_palette.py:221, 226, 246 | rail radius 0, 6 | allowed | unchanged | M4 |
| object_palette.py:227, 232 | dock radius 0, 6 | allowed | unchanged | M4 |
| viewport.py:2955 | `qsViewMenu` border | 1px solid transparent | the 1 px border forces 22 px content | remove the border from this rule and the `:focus` rule (the buttons are `NoFocus`) | M3 |
| viewport.py:2957 | `qsViewMenu` min-height, max-height | `GHOST_BUTTON_H - 2` = 22px | violation | `{theme.GHOST_BUTTON_H}px` (24) | M3 |
| viewport.py:2956 | `qsViewMenu` padding | 0px 10px | allowed | unchanged | M3 |
| modeling/panel.py:261 | `qsToolButton` padding | 2px 10px | allowed | unchanged | M5 |

---

## 6. Live widget sizes found offscreen (1920 x 1010) that break the norm

From a walk over every widget of the built window (fixed sizes, layout margins and spacing). Each one is
fixed by the rows of section 7; the list is the acceptance check for the runtime layer of the guard.

| Widget | Size now | Cause | After the sweep |
|---|---|---|---|
| mode buttons (`FoldoutButton`, 4) | 34 x 26 | `MODE_BUTTON_W` 34, `SEGMENT_H` 30 | 32 x 28 |
| Undo, Redo, Make Editable | 30 x 30 | `COMMAND_BUTTON` 30 | 32 x 32 |
| `Segment` mode switcher | height 30, width 140 | `SEGMENT_H` | height 32, width 132 |
| `ProjectChip` | height 26 | `CHIP_H` | 24 |
| `ObjectHeader` | height 26 | attribute_manager `HEADER_H` | 24 |
| `qsAttributeSection` | height 26 | attribute_manager `SECTION_H` | 24 |
| `qsDimLabel` in field rows (11) | width 118 | attribute_manager `LABEL_WIDTH` | 120 |
| `qsResetTransform` | 138 x 22 | `RESET_W` 125 and text, `FIELD_H` | 140 x 24 |
| `qsCoordField` (9) | height 22 (QSS wins over `setFixedHeight(20)`) | `FIELD_H` | 24 |
| two layouts in the Attribute Manager | spacing 1 | `content_layout().setSpacing(1)` | 2 |
| `qsViewport` layout | margins 1, 1, 1, 1 | card border inset | allowed (border inset), unchanged |
| rail `_Divider` | height 19 | `DIVIDER_HEIGHT` | 18 |
| `CoordinatesManager` | height 127 | sum of its parts | fixed 128 |

---

## 7. Literal sizes by file

Columns: line, what the number measures, value now, verdict, new value. Rows not listed in a file are allowed
and stay.

### 7.1 `quartz_studio/main_window.py` (M2)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 31 to 36 | `RIGHT_COLUMN_RATIO`, `COORD_RATIO`, `ATTRIBUTE_SHARE`, `ATTRIBUTE_FRACTION` | ratios | exempt | `COORD_RATIO` deleted (Coordinates is fixed, 7.11) |
| 33 | `RIGHT_COLUMN_MIN` minimum right column width | 300 | violation | 304 |
| 36 | `ATTRIBUTE_FIRST_ROW` | 44 | allowed | unchanged |
| 42 | viewport placeholder minimum | 400, 300 | 300 violation | 400, 304 |
| 44, 45, 46 | manager placeholder minimum width 260 (256+4), height 120 | allowed | unchanged |
| 69 | placeholder margins | 2, 0, 2, 0 | allowed | unchanged |
| 111 | `LEFT_DOCK_W` | 256 | allowed | unchanged |
| 112 | `PAGE_BUTTON_H` | `SEGMENT_H - 4` = 26 | violation through the token | 28 (follows `SEGMENT_H` 32) |
| 159, 160 | page switcher margins 2, spacing 2 | allowed | unchanged |
| 524 | dock width cap `area.width() - 2 * SPACE_3` | window-derived | exempt | unchanged |
| 549 | bottom panels `total // 3` | window-derived | exempt | unchanged |
| 567 to 572 | default right column width | 488 at 1920, `max(325, 408)` at 1280 | 488 allowed; 408 and 325 violations | `right_w = snap_px_up(max(ratio_w, min(wanted, room), right_min))`, then `min(right_w, room)`; gives 488 at 1920 and 416 at 1280 |
| 580 | Coordinates height `max(round(total_h * COORD_RATIO), coord_min, 60)` | 127 | 60 violation, result odd | `coord_h = theme.COORDINATES_H` (128); the Coordinates card is not resizable by the splitter |

### 7.2 `quartz_studio/widgets/common.py` (M1)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 120 to 124 | `header_font` size and tracking | `setPointSizeF(8)`, absolute 1.0 | violation | `font.setPixelSize(theme.FONT_SMALL_PX)`; `PercentageSpacing`, `theme.HEADER_TRACKING` |
| 235, 236 | `IconButton` default size and icon | `COMMAND_BUTTON`, `COMMAND_ICON` | follows tokens (32, 18) | unchanged code |
| 336 | fold-out triangle hit zone `max(7, w // 3)` | 7 floor | violation | `max(8, self.width() // 3)` (8, 10, 12 for 24, 32, 36) |
| 345 to 350 | popup offset from the button (`_popup_pos`) | 1 px | violation (1 as a gap) | `theme.POPUP_GAP` (4) on every side |
| 378 | group mark inset `m` | 1.5 | violation | 2 |
| 478, 515 | `ToggleSwitch` size | 30 x 16 | 30 violation | 32 x 16 (`setFixedSize` and `sizeHint`) |
| 507 to 511 | toggle knob | `d = r.height() - 6` = 9, inset 3 | violation | knob 12 x 12 at inset 2: `QRectF(self.width() - 14 if on else 2, 2, 12, 12)`; track radius 8 |
| 494 | track rect 0.5 inset | line alignment | exempt | unchanged |
| 581 | `PANEL_RIGHT_ICON` | 18 | allowed | unchanged |
| 594 | panel menu spacing `SPACE_1 // 2` | 2 | allowed | unchanged |
| 598 | hamburger icon | 14 | allowed | unchanged |
| 682, 683 | group header margins 12, 0, 6, 0, spacing 6 | allowed | unchanged |
| 685 | chevron box | 10 x 10 | allowed | unchanged |
| 695 | group body margins 0, 2, 0, 8 | allowed | unchanged |
| 696 | group body spacing | 3 | violation | 2 |
| 745 | `FieldRow.INDENT` | 34 | violation | 32 |
| 744 | `FieldRow.LABEL_WIDTH` | 112 | allowed | unchanged |
| 752, 753 | field row right margin 8, spacing 6 | allowed | unchanged |
| 760 | `FieldRow` height `FIELD_H + 2` | 24 today, 26 with the new `FIELD_H` | would break | `theme.FIELD_H` (24); rows are separated by the group spacing 2 (rhythm 26) |

### 7.3 `quartz_studio/widgets/press_feedback.py` (M1)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 62 | chip overlay radius `CHIP_H / 2` | 13.0 | follows token | 12.0 |
| 274 | pill overlay horizontal inset `min(12, w / 4)` | text-derived | exempt | unchanged |
| 275 | pill overlay vertical inset `max(3.0, (h - 20) / 2)` | 3 floor | violation | `max(2.0, (h - 20) / 2)` (a 20 px pill in 24 and 28 px rows) |
| 301 | focus ring half width | 0.5 | line alignment | unchanged |
| 32, 33, 42 to 48 | alphas and durations | not px | exempt | unchanged |

### 7.4 `quartz_studio/widgets/command_bar.py` (M2)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 519 | gear icon `max(10, min(length, round(thickness * 0.62)))` | 10 to 22, can be odd | violation risk | `theme.snap_px(...)` of the same expression |
| 554 | default gear length `max(12, round(button * 0.58))` | can be odd | violation risk | `theme.snap_px(...)` of the same expression |
| 735 | `COMMAND_GEAR` | 17 | violation | 16 |
| 739 | `CHIP_NAME_MAX` elide width | 240 | allowed | unchanged |
| 740 | `MODE_SEGMENT_PAD` | 2 | allowed | unchanged |
| 741 | `MODE_BUTTON_W` | 34 | violation | 32 |
| 742 | `MODE_BUTTON_H` | `SEGMENT_H - 4` = 26 | violation through the token | 28 |
| 757, 764 | unsaved dot: widget 8 x 8, ellipse inset 1 | 1 as padding | violation | widget 6 x 6 (`setFixedSize(6, 6)`), ellipse fills `QRectF(self.rect())`; SPEC 9.6 already says 6 px |
| 776, 777 | project chip margins 12, spacing 8 | allowed | unchanged |
| 826 | gap before the chip | 8 | allowed | unchanged |
| 249, 256 | fallback painter pens | 1.0, 1.1 | 1.1 violation | 1.0 and 1.0 |

### 7.5 `quartz_studio/widgets/menu_bar.py` (M2, sizes only; menus, wiring and pruning are not touched)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 35, 58 to 60 | `UI_POINT_SIZE`, `menu_font(point_size)` | 9 pt | pt | `UI_PX = theme.FONT_PX`; `menu_font(bold=False, px=UI_PX)` calls `setPixelSize(px)` |
| 36 | `BAR_ITEM_PAD` | 10 | allowed | unchanged |
| 38 | `BAR_ITEM_INSET` (menu bar pill inset top and bottom) | 3 | violation | 2 (pill 28 = `MENU_ROW_H`) |
| 41 to 49 | menu paddings, insets, icon column, text x 36, icon x 10, section x 12, section height 24 | allowed | unchanged |
| 50 to 54 | right pad 32, right column 18, shortcut 32, popout column 28 | allowed | unchanged |
| 54 | `MENU_POPOUT_CX` | 22 | violation | 24 |
| 55 | `MENU_BADGE_PAD` | 3 | violation | 2 (badge 20 around the 16 px icon) |
| 637 | section text rect top 4 | allowed | unchanged |
| 815, 816, 824, 825 | `r.x() - 1`, `r.width() + 2` | compensation of the 1 px menu border | exempt (border inset) | unchanged |
| 845 | badge radius `CONTROL_RADIUS - 1` | 5 | violation | 4 (`CONTROL_RADIUS - 2`) |
| 852 | check icon inset 2 | allowed | unchanged |
| 874 | submenu chevron box | `cx - 5.5`, 11 x 11 | violation | `QRectF(cx - 6, cy - 6, 12, 12)` |
| 877 | gear box 16 x 16 | allowed | unchanged |
| 881 | popout box | `px - 8.5`, 17 x 17 | violation | `QRectF(px - 8, cy - 8, 16, 16)` |
| 1155 | pill rect 0.5 inset | line alignment | unchanged |
| 97 to 530 | fallback menu icon painters | glyph geometry | exempt | unchanged |

### 7.6 `quartz_studio/widgets/status_bar.py`, `context_menu.py`, `menus_data.py` (M2)

No violations. Status body margins 12 and spacing 12 stay; the font comes from the QSS (10 px after the
sweep). `context_menu.py` and `menus_data.py` hold no px sizes today; M2 only rechecks them with the guard.

### 7.7 `quartz_studio/widgets/tool_palette.py` (M4)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 188 | `TOOL_GAP` | 10 | allowed | unchanged |
| 189 | `TOOL_MIN_GAP` | 3 | violation | 2 |
| 192 | `DIVIDER_HEIGHT` | 19 | violation | 18 |
| 193 | `DIVIDER_INSET` | 2 | allowed | unchanged |
| 195, 196, 197 | `ARROW_HEIGHT` 14, `ARROW_ICON` 10, `SCROLL_STEP` 36 | allowed | unchanged |
| 365 | fold-out shift `(RAIL_PAD + SPACE_1 - 1, 0)` | 9 | violation | `(theme.RAIL_PAD, 0)`; with `POPUP_GAP` 4 the fold-out still opens 10 px right of the button, 4 px outside the card (SPEC 9.11) |
| 464 | compressed gap `max(TOOL_MIN_GAP, min(TOOL_GAP, (avail - fixed) // count))` | can be odd | violation risk | same expression rounded down to even: `(avail - fixed) // count // 2 * 2` inside the `min` |
| 64 and the other fallback painters | pen 1.0 | allowed | unchanged |

### 7.8 `quartz_studio/widgets/object_palette.py` (M4)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 213 to 217 | button 36, icon 24, gap 12, pad 6, divider length 24 | allowed | unchanged |
| 296 | fold-out shift `(0, -(DOCK_PAD + SPACE_1 - 1))` | -9 | violation | `(0, -theme.DOCK_PAD)`; with `POPUP_GAP` 4 the fold-out still opens 10 px above the button, 4 px above the dock |
| 308, 310 | dock outline pen 1, rect 0.5 inset | allowed | unchanged |
| 27 to 120 | fallback painters | glyph geometry | exempt | unchanged |

### 7.9 `quartz_studio/widgets/object_manager.py` (M5)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 38 | `EMPTY_TOP` | 24 | allowed | unchanged |
| 43 | `ROW_H` (delegate row height) | 26 | violation | delete the local constant; use `theme.ROW_H` (24) |
| 44 | `ROW_INSET` (selection band inset) | 1 | violation (1 as padding) | 0; the band fills the row, the accent bar is `band.height() - 8` = 16 tall |
| 45 to 50 | icon left 6, icon 18, name left 32, status column 32, indent 16, chevron 10 | allowed | unchanged |
| 58 | `DROP_LINE_H` | 2 | allowed | unchanged |
| 210, 215 | check and cross pens `ICON_STROKE_W` | 1.6 | violation through the token | 2 (token) |
| 278 | rename editor left `NAME_LEFT - 7` | 25 | violation | `NAME_LEFT - theme.SPACE_2` (24); the editor text sits 1 px left of the row text |
| 280 | editor top 2, height minus 4, minimum width 48 | allowed | unchanged |
| 304 | header minimum section | 20 | allowed | unchanged |
| 728 | drop target outline pen | 1.5 | violation | 2 |
| 731 | drop target rect `QRectF(1, top + ROW_INSET + 0.5, width - 2, h - 2 * ROW_INSET - 1)` | half pixels for a 1.5 pen | follows | `QRectF(1, cell.top() + 1, width - 2, cell.height() - 2)` |
| 742 | `setMinimumSize(260, 120)` | 260 = 256+4 | allowed | unchanged |

### 7.10 `quartz_studio/widgets/attribute_manager.py` (M5)

Tonight another contract may remove the Basic and Coord. chips, the section title and tabs. Rows for widgets
that no longer exist are dropped; the values hold for whatever remains.

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 39 | `LABEL_WIDTH` | 118 | violation | 120 (override of snap 128: width budget at 1280 x 720, `test_interface_defects`) |
| 40 | `LABEL_INDENT` | 10 | allowed | unchanged |
| 41 | `HEADER_H` | 26 | violation | 24 |
| 42 | `HEADER_ICON` | 18 | allowed | unchanged |
| 43 | `CHIP_BAR_H` `CHIP_H + 2` | 28 today, 26 with the new `CHIP_H` | would break | `theme.CHIP_H + theme.SPACE_1` (28) |
| 44 | `SECTION_H` | 26 | violation | 24 |
| 51 | `VECTOR_SPIN_MIN` | 30 | violation | 32 |
| 52 | `ARROW_W` | 16 | allowed | unchanged |
| 53 | `ARROW_HALF` (step arrow glyph) | 3.0 | glyph geometry | unchanged |
| 58 | `SPIN_TEXT_MARGIN` | 5 | violation | 4 |
| 67 | `VECTOR_TEXT_MARGIN` | 3 | violation | 2 |
| 138 | step arrow pen | 1.3 | violation | 1 |
| 217 | `ParamEditor` spacing | 3 | violation | 2 |
| 231 | `setMinimumContentsLength(8)` | characters | exempt | unchanged |
| 252 | vector tag width | 10 | allowed | unchanged |
| 360, 361 | object header margins 8, spacing 8 | allowed | unchanged |
| 404 | `setMinimumSize(260, 160)` | 260 = 256+4 | allowed | unchanged |
| 447 | chip bar margins 0, 0, 0, 2 | allowed | 0, 0, 0, `SPACE_1` (4), to fill `CHIP_BAR_H` 28 |
| 473 | section title margins 8, 4, 0, 0 | allowed | unchanged |
| 497 | empty label top margin 24 | allowed | unchanged |
| 510, 646 | `group.content_layout().setSpacing(1)` | 1 | violation | 2 |

### 7.11 `quartz_studio/widgets/coordinates.py` (M5)

The owner asked tonight that the Coordinates card keep one fixed height on screen (the width follows the
column). Metric contract for that card:

| Part | Size |
|---|---|
| card height | `theme.COORDINATES_H` = 128, fixed (minimum = maximum) |
| layout margins | left 8 (`CARD_PADDING`), top 4 (`SPACE_1`), right 8, bottom 4 (`SPACE_1`) |
| layout spacing | 4 (`SPACE_1`), one gap between the header and the grid |
| header | `HEADER_H` 24, with the hairline drawn as its own 1 px bottom border inside the 24 px (the `HeaderRule` widget leaves the layout) |
| grid | column titles `TITLE_H` 14, vertical spacing `GRID_GAP` 2, three field rows of `FIELD_H` 24, horizontal spacing 6, axis column `AXIS_W` 14 |
| sum | 4 + 24 + 4 + 14 + 2 + 24 + 2 + 24 + 2 + 24 + 4 = 128 |

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 42 | `RESET_W` | 125 | violation | 128; the button width is `theme.snap_px_up(max(RESET_W, sizeHint().width()))` (140 today) |
| 43 to 48 | header 24, header pad 10, title 14, axis 14, gap 2 | allowed | unchanged |
| 46, 224 | `ROW_H` 20 and `setFixedHeight(ROW_H)` (the QSS makes it 22 anyway) | misleading | delete `ROW_H`; `CoordField.setFixedHeight(theme.FIELD_H)` |
| 50 | `MIN_H` formula | 121 | odd | `MIN_H = theme.COORDINATES_H` |
| 225 | field minimum width 40 | allowed | unchanged |
| 308 | `setMinimumSize(260, MIN_H)` | 260 allowed, height odd | change | `setMinimumWidth(260)` and `setFixedHeight(theme.COORDINATES_H)` |
| 316, 318 | layout margins and spacing | 8, 4, 8, 8 and 2 | change | the table above |
| 345 | grid horizontal spacing `SPACE_2 - 2` | 6 | allowed | unchanged |

If the Coordinates feature contract tonight already made the card fixed, M5 only checks that the numbers
match this table.

### 7.12 `quartz_studio/modeling/panel.py` (M5)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 16 | `LABEL_WIDTH` | 118 | violation | 120 (same as the Attribute Manager) |
| 17, 18 | `ROW_INDENT` 14, `SCRUB_PX` 4 | allowed | unchanged |
| 97, 126 | fixed height `FIELD_H` | 22 | through the token | 24 |
| 162 | spacing | 3 | violation | 2 |
| 262 | minimum height 160 | allowed | unchanged |
| 270 | header margins 20, 0, 12, 0 | allowed | unchanged |
| 280 | rule height 1 | line | unchanged |
| 292, 293 | margins 8, 4, 8, 6, spacing 6 | allowed | unchanged |
| 321 | `sizeHint` `QSize(300, 300)` | violation | `QSize(304, 304)` |
| 336 | margins 0, 2, 0, 6 | allowed | unchanged |
| 337 | spacing | 1 | violation | 2 |
| 352 | group spacing 2 | allowed | unchanged |

### 7.13 `quartz_studio/modeling/interaction.py` (M3)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 17 | `DRAG_THRESHOLD` | 3.0 | violation | 4.0 (override of snap 2: a smaller threshold turns clicks into drags) |
| 18, 19 | `PERCENT_PER_PX`, `ANGLE_PER_PX` | ratios | exempt | unchanged |
| 20, 21, 22 | `COUNT_PX` 18, `EDGE_PICK_PX` 10, `POINT_PICK_PX` 10 | allowed | unchanged |
| 25 | `PREVIEW_WIRE_WIDTH` | 1.0 | line | unchanged |
| 136 | hover edge pen | 3.0 | violation | 4.0 (override of snap 2: the hovered edge must read wider than the 2 px selected edges in the same colour) |
| 139 | preview dash pen | 1.5 | violation | 1.0 |
| 144 | HUD font `setPixelSize(12)` | allowed | `theme.FONT_PX` |
| 146 | HUD rect offsets 14, 10, size 240 x 20 | allowed | unchanged |
| 148 | text shadow offset 1, 1 | 1 px shadow line | exempt | unchanged |

### 7.14 `quartz_studio/widgets/viewport.py` (M3)

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 64, 65 | `OVERLAY_INSET` 8, `OVERLAY_TOP` 32 | allowed | unchanged |
| 66 | `TRIAD_CLEARANCE` | 40 | allowed | unchanged |
| 159 | camera badge pen (12-unit grid) | 0.9 | violation | 1.0 (= 2 at 24 units scaled to the 12-unit grid) |
| 183, 211, 225, 235 | nav icon pens (16-unit grid) | 1.1 to 1.4 | violation | module constant `NAV_STROKE = theme.ICON_STROKE_W * 16 / 24` (the 24-unit stroke 2 scaled to the 16-unit grid), used as the default of `_nav_pen` and by every nav painter without a width argument; the guard does not evaluate it (grid units, see 11.4 rule 3) |
| 632, 633, 249 to 266 | world axis length, pieces, lens, distances | world units, counts | exempt | unchanged |
| 634 | `GIZMO_PX` arrow length | 85.0 | violation | 88.0 |
| 635 | `GIZMO_HEAD_PX` | 12.0 | allowed | unchanged |
| 636 | `GIZMO_PICK_PX` | 7.0 | violation | 8.0 |
| 637 | `GIZMO_AXIS_FIRST_PX` | 2.5 | violation | 2.0 |
| 638, 647, 648 to 651 | `PLANE_CORE`, `RING_TIE_PX` (tie epsilon), plane fractions, ring scale | ratios, epsilon | exempt | unchanged |
| 639 | `GIZMO_CENTER_PX` | 6.5 | violation | 6.0 |
| 640 to 644 | fallback 14, point pick 8, edge pick 6, context drag 4 | allowed | unchanged |
| 643 | `DRAG_THRESHOLD` | 3 | violation | 4 (same reason as 7.13) |
| 646 | `GIZMO_RING_PX` | 68.0 | violation | 64.0 |
| 652 | `PLANE_PICK_PX` | 2.0 | allowed | unchanged |
| 666 | `setMinimumSize(320, 200)` | 320 = 256+64, 200 = 128+72 | allowed | unchanged |
| 914, 2012 | label and triad font 11 px | violation | `theme.FONT_PX` |
| 1301, 1453 | horizon pen 1, polygon outline pen 1 | lines | unchanged |
| 1457 | n-gon guide pen | 1.4 | violation | 1.0 |
| 1461, 1465 | selection pens front and back | 2.0 | allowed | unchanged |
| 1556 | null object display Dot / Point pen | 7.0 / 3.0 | violation | 6.0 / 2.0 |
| 1567 | null lines pen (not selected) | 1.4 | violation | 1.0 (selected stays 2.0) |
| 1584 | loose edges pen | 1.4 | violation | 1.0 |
| 1610 | world axis width `max(1.0, self.width() / 1100.0)` | fractional | violation | 1.0 |
| 1632 | arrowhead threshold 12 | allowed | unchanged |
| 1658 | edge-mode wire pen | 1.3 | violation | 1.0 |
| 1666 | selected edges pen | 2.6 | violation | 2.0 |
| 1676, 1682 | point border pens 1 | lines | unchanged |
| 1681 | point handle | 5 x 5 at `x - 2.5` | violation | 4 x 4 at `x - 2` |
| 1687 | selected point handle | 7 x 7 at `x - 3.5` | violation | 6 x 6 at `x - 3` |
| 1709, 1766 | move and scale axis pen, hot / normal | 2.6 / 2.0 | 2.6 violation | 2.0 / 2.0 (the hot axis keeps `GIZMO_HOVER`, which marks it) |
| 1713, 1715 | tiny gizmo threshold 3, dot radius 3 | 3 threshold violation | threshold 4, dot radius 3 (diameter 6) |
| 1718 | shaft gap `min(6.5, n)` | violation | `min(self.GIZMO_CENTER_PX, n)` (6) |
| 1731 to 1734 | centre ring: shadow pen 3.2, ring pen 1.6, radius 5.6 | violation | shadow pen 4.0, ring pen 2.0, radius 6.0 |
| 1748 | plane handle outline pen hot / normal | 2.6 / 2.0 | violation | 2.0 / 2.0 (the fill alpha 200 against 120 marks it) |
| 1772 | scale handle | 7 x 7 at `ex - 3.5` | violation | 8 x 8 at `ex - 4` |
| 1774 | scale centre pen | 1.6 | violation | 2.0 |
| 1776 | scale centre 8 x 8 | allowed | unchanged |
| 1829 | dashed pen | 1.3 | violation | 1.0 |
| 1849 | pen chain point | 5 x 5 at `x - 2.5` | violation | 4 x 4 at `x - 2` |
| 1855, 1861 | first-point ring 10 x 10, dot radius 3 | allowed | unchanged |
| 1877 | pivot ticks from 5 to 10 | glyph geometry | exempt | unchanged |
| 1879 | pivot pens shadow / bright | 3.4 / 1.4 | violation | 4.0 / 1.0 |
| 1887, 1889 | pivot dots radius | 3.6 / 2.3 | violation | 4.0 / 2.0 |
| 1893, 1895 | pill outline pen 1, 0.5 inset | lines | unchanged |
| 1903, 1933 | HUD icon `round(HUD_H * 0.6)` | 13 | violation | `theme.HUD_ICON` (16) |
| 1905, 1939 | gap between HUD text and icon | 6 | allowed | unchanged |
| 1917, 1927 | text rect slack 1 and 2 | text metrics | exempt | unchanged |
| 1920 | camera badge `round(text_h * 0.78)` | text-derived, often odd | violation | 12 |
| 1924, 1929 | gap between camera name and badge | 3 | violation | 4 (`SPACE_1`) |
| 1952, 1994 | HUD glyph pen `max(1.0, r.width() / 10)` | 1.6 at 16 | violation | 2.0 |
| 1981 | pen glyph `max(1.0, w / 11)` | 1.45 at 16 | violation | 2.0 |
| 2009 | triad size | 25.0 | violation | 24.0 |
| 2027 | triad axis pen 2 | allowed | unchanged |
| 2037 to 2039 | triad arrowheads | glyph geometry | exempt | unchanged |
| 2044 | triad letter offset | 9.5 | violation | 10.0 |
| 2904 | canvas `sizeHint` | 1349 x 864 | 1349 violation | 1344 x 864 |
| 2967, 2968 | view menu margins 8, spacing 4 | allowed | unchanged |
| 2984 | nav icon size 18 | allowed | unchanged |
| 3116 | `Viewport.setMinimumSize(400, 300)` | 300 violation | 400, 304 |
| 3118 | canvas margins 1, 1, 1, 1 | card border inset | exempt | unchanged |
| 3126 | `Viewport.sizeHint` | 1349 x 890 | violation | 1344 x 896 |

### 7.15 `quartz_studio/icons.py` (M1)

Icon canvas: icons are drawn on a 24-unit grid (`_unit`, icons.py:216 to 224) and rendered at the size the
caller asks: 10 (QSS assets, chevrons), 12 (camera badge), 14 (hamburger), 16 (menus, panel icons), 18 (top
bar, nav icons, object icons), 24 (rail, dock), 32 (fallback app icon). All allowed. Strokes are specified in
grid units: 2 for every outline (`ICON_STROKE_W`), 1 for secondary detail lines. A painter on another grid
scales the stroke by grid / 24.

| Line | Measures | Now | Verdict | New |
|---|---|---|---|---|
| 38 | `_W = theme.ICON_STROKE_W` | 1.6 | violation | 2.0 (token) |
| 147 | group mark side `max(3.0, round(min(w, h) * 0.17))` | 5 at 32 px, 3 at 16 | violation | `6.0 if min(r.width(), r.height()) >= 32 else 4.0` |
| 158 to 161 | QSS asset pixmaps 10 px | allowed | unchanged |
| 279 | `_dot` default radius 1.8 | glyph geometry | exempt | unchanged |
| 295 | `_dashed` default pattern | dash ratios | exempt | unchanged |
| 576, 582 | chevron pens | 2.2 | violation | 2.0 |
| 588 | check pen | 2.6 | violation | 2.0 |
| 711 | axis letter pen | 1.8 | violation | 2.0 |
| 752, 955, 1014, 1126, 1374 | detail pens | 1.4 | violation | 1.0 |
| 1003, 1082, 1093 | pens 2.0 | allowed | unchanged |
| 1066 | pen | 2.2 | violation | 2.0 |
| 1499, 1507, 1787 | detail pens | 1.2 | violation | 1.0 |
| 1676, 2352 | pens | 1.6 | violation | 2.0 |
| 2410 | pen | 1.5 | violation | 1.0 |

Icons will look slightly bolder (main stroke 2 instead of 1.6). M1 checks the rail, the dock, the menus and
the top bar in a snapshot (`tools/snapshot.py`) and `tests/test_tool_palette.py` (fill and tint checks).

### 7.16 `quartz_studio/app.py` (M1)

| Line | Measures | Now | New |
|---|---|---|---|
| 50 | application font `QFont(theme.FONT_FAMILY, theme.FONT_POINT_SIZE)` | 9 pt | `QFont(theme.FONT_FAMILY)` then `font.setPixelSize(theme.FONT_PX)` |

### 7.17 Files outside the window and the new packages

- `widgets/title_row.py` and `widgets/sculpt_bar.py` are not in the window: exempt, unchanged. Known
  violations if they ever return: `SCULPT_BAR_HEIGHT` 37, `SCULPT_ICON` 31, `setPointSizeF(9)`.
- New packages written tonight (`anim`, `tags`, `scripting`, `materials`, `render`, `rig`, `sculpt`, `uv`,
  `ext`): spot checks of `anim/ui_common.py` (button 24, icon 16, field 64, combo 96, row 24, gap 4,
  margin 8), `anim/timeline.py` (ruler 48, strip 12, side 16, key radius 6, chip 32 x 16, pens 1 and 2,
  minimum widths 256 and 96), `scripting/console.py` (border 1, radius 6 and 4, padding 4 and 4 8, margins 8,
  spacing 8) and `tags/widgets.py` (heights `CARD_HEADER_H`, `CARD_HEADER_H + SPACE_2`) show no violation.
  `tags/widgets.py` uses `theme.HEADER_LETTER_SPACING` (absolute): the integration step moves it to
  `HEADER_TRACKING` (section 12.4). `scripting/console.py:86` computes a height from line spacing: text
  metrics, exempt. Any other hit in these packages that `tests/test_metrics.py` reports is fixed by the
  integration step, not by M1 to M5.

---

## 8. Derived sizes

### 8.1 Layout of SPEC 9.5 (expected after the sweep)

Window client area, x and y of the top left corner, then width x height. "Same" means unchanged.

| Region | 1920 x 1010 now | 1920 x 1010 after | 1280 x 720 now | 1280 x 720 after |
|---|---|---|---|---|
| `menu_bar` | 36, 4, 183 x 32 | same | 36, 4, 183 x 32 | same |
| `command_bar` | 227, 0, 1685 x 40 | same | 227, 0, 1045 x 40 | same |
| mode switcher | 890, 5, 140 x 30 | 894, 4, 132 x 32 | 570, 5, 140 x 30 | 574, 4, 132 x 32 |
| Undo, Redo, Make Editable | 30 x 30 | 32 x 32, y 4 | 30 x 30 | 32 x 32, y 4 |
| project chip | y 7, height 26 | y 8, height 24 | y 7, height 26 | y 8, height 24 |
| `tool_palette` | 8, 40, 48 x 946 | same | 8, 40, 48 x 656 | same |
| `viewport` | 64, 40, 1352 x 946 | same | 64, 40, 792 x 656 | 64, 40, 784 x 656 |
| `object_palette` (dock) | 542, 925, 396 x 48 | same | 262, 635, 396 x 48 | 258, 635, 396 x 48 |
| `object_manager` | 1424, 40, 488 x 337 | 1424, 40, 488 x h1 | 864, 40, 408 x 215 | 856, 40, 416 x h2 |
| `attribute_manager` | 1424, 385, 488 x 466 | window-derived | 864, 263, 408 x 298 | window-derived |
| `coordinates` | 1424, 859, 488 x 127 | 1424, 858, 488 x 128 | 864, 569, 408 x 127 | 856, 568, 416 x 128 |
| `status_bar` | 0, 986, 1920 x 24 | same | 0, 696, 1280 x 24 | same |

`h1` and `h2` (Object Manager and Attribute Manager heights) are window-derived and exempt; they keep the
rules `ATTRIBUTE_FRACTION`, `ATTRIBUTE_SHARE`, `ATTRIBUTE_FIRST_ROW`. The 1280 numbers assume the managers'
size hint stays 408 (snapped up to 416); the integration step measures the finished window with the probe of
section 11.6 and writes the real numbers into SPEC 9.5. The page switcher that another fleet is adding to the
top row tonight may shift `command_bar`; that is measured, not specified here.

### 8.2 Dock

Width: natural (sum of allowed parts, exempt), capped at the canvas width minus 24. Height `DOCK_H` 48.
Bottom `DOCK_BOTTOM` 12 above the canvas bottom; when the HUD would overlap it rises to 8 (`SPACE_2`) above
the HUD. All constants allowed; unchanged.

### 8.3 Fold-out offsets

| Popup | Now | After |
|---|---|---|
| top bar fold-outs (`popup_side="below"`) | 1 px below the button | `POPUP_GAP` 4 below |
| rail fold-outs | 1 + 9 = 10 px right of the button (4 outside the card) | `POPUP_GAP` 4 + `RAIL_PAD` 6 = 10 (same place) |
| dock fold-outs | 1 + 9 = 10 px above the button (4 above the dock) | `POPUP_GAP` 4 + `DOCK_PAD` 6 = 10 (same place) |
| `left` side | 1 px | 4 px |

### 8.4 Viewport gizmo and overlay sizes in px

Move arrows 88 (was 85), heads 12, rotate ring radius 64 (was 68), view ring 64 x 1.2 (ratio), centre ring
radius 6 (was 5.6), scale handles 8 (was 7), scale centre 8, axis triad 24 (was 25) with letters 10 out (was
9.5), point handles 4 and 6 (were 5 and 7), HUD 24 tall (was 22) with a 16 px glyph, view name and camera
plate 24 tall, nav buttons 24 with 18 px icons, ghost buttons 24.

### 8.5 Hit tolerances and thresholds in px

| Constant | Where | Now | After |
|---|---|---|---|
| `GIZMO_PICK_PX` | viewport.py:636 | 7 | 8 |
| `GIZMO_AXIS_FIRST_PX` | viewport.py:637 | 2.5 | 2 |
| `GIZMO_CENTER_PX` | viewport.py:639 | 6.5 | 6 |
| `AXIS_FALLBACK_PX` | viewport.py:640 | 14 | 14 |
| `POINT_PICK_PX` | viewport.py:641 | 8 | 8 |
| `EDGE_PICK_PX` | viewport.py:642 | 6 | 6 |
| `DRAG_THRESHOLD` | viewport.py:643 | 3 | 4 |
| `CONTEXT_DRAG_PX` | viewport.py:644 | 4 | 4 |
| `PLANE_PICK_PX` | viewport.py:652 | 2 | 2 |
| `RING_TIE_PX` | viewport.py:647 | 0.5 | exempt (tie epsilon) |
| `DRAG_THRESHOLD` | interaction.py:17 | 3.0 | 4.0 |
| `EDGE_PICK_PX`, `POINT_PICK_PX` | interaction.py:21, 22 | 10 | 10 |
| `COUNT_PX` | interaction.py:20 | 18 | 18 |
| `SCRUB_PX` | panel.py:18 | 4 | 4 |
| fold-out triangle zone | common.py:336 | `max(7, w // 3)` | `max(8, w // 3)` |
| `HOLD_MS` | common.py:222 | 380 ms | exempt (time) |

---

## 9. Values for the other contracts of tonight

These are the metric values for owner requests that other contracts implement. If such a contract names a
value differently, its names win, but the values must be in the set and the guard must pass.

| Request | Values |
|---|---|
| Splitter highlight ("reduce the thickness and round the corners of that green rectangle") | the handle stays `CARD_GAP` 8 wide (the drag area); the visible bar is 4 px thick (`SPACE_1`), radius 2, centred in the handle, its ends inset 12 px (`SPACE_3`) from the ends of the handle; colour unchanged (`ACCENT_TINT_BACKDROP`) |
| Coordinates fixed height | section 7.11 (128) |
| Attribute Manager without Basic and Coord. | rows of section 7.10 that survive; field rows `FIELD_H` 24 with spacing 2; section title, if any, `FONT_TITLE_PX` 14 |
| Viewport filter for n-gon lines and polygon outlines | n-gon guide pen 1, polygon outline pen 1 (7.14) |
| Palette customisation and condensed groups | fold-out mark 6 px on 32 px and larger buttons, 4 px below; hold-to-open zone `max(8, w // 3)`; new buttons use `DOCK_BUTTON` / `PALETTE_BUTTON` 36 and icons 24 |
| Keybinding and cursor profiles dialog | rows `ROW_H` 24 or `MENU_ROW_H` 28, fields `FIELD_H` 24, paddings from `SPACE_1` to `SPACE_3`, fonts `FONT_PX` / `FONT_SMALL_PX` |

Rule for every feature builder working tonight before the sweep: any size added or touched is taken from a
theme token or is a value allowed by section 1.1; fonts in px only; no new `pt`.

---

## 10. Tests that pin sizes today

| Test | What it pins | Change |
|---|---|---|
| `tests/test_smoke.py::_layout_errors` (169 to 254) | tokens only (`WINDOW_MARGIN`, `CARD_GAP`, `TOP_BAR_H`, `STATUS_BAR_H`, `APP_MARK`, `SPACE_2`, `RAIL_W`, `DOCK_BOTTOM`, `DOCK_H`, `SPACE_3`) and `height() < 40` | no literal changes; it must pass with the new tokens (M2) |
| `tests/test_smoke.py:600 to 615` | mode switcher height `SEGMENT_H`, segments `SEGMENT_H - 4` | passes with 32 and 28 |
| `tests/test_smoke.py:488 to 511` | Coordinates keeps its height when a panel is inserted; extra panel at least 120 | passes (fixed 128) |
| `tests/test_smoke.py:663 to 678` | chip width at most 240 + 4 x 12 + 8 | unchanged |
| `tests/test_tool_palette.py:449 to 465` | gaps equal `TOOL_GAP` 10, gap 4 equals `DIVIDER_HEIGHT` and exceeds `TOOL_GAP` | passes with 18 > 10 |
| `tests/test_tool_palette.py:502 to 535` | standalone rail at 320 px: minimum gap equals `TOOL_MIN_GAP`, `SCROLL_STEP`; `min(gaps) >= 10` at 900 | `TOOL_MIN_GAP` becomes 2; replace the literal 10 at line 535 with `TOOL_GAP` |
| `tests/test_tool_palette.py:560, 581` | icon test cell 31 px (old `TOOL_ICON` 31) and `31 * 31 * 0.8` | `_pixels(name, size=32)` and `size * size * 0.8` with `size = 32` (M4) |
| `tests/test_tool_palette.py:755 to 759` | dock height `DOCK_H`, divider `DOCK_GAP` x 24 | replace 24 with `object_palette.DIVIDER_LENGTH` (M4) |
| `tests/test_press_feedback.py:767` | chip overlay radius `CHIP_H / 2` | passes with 12 |
| `tests/test_press_feedback.py` `_neutral()` | empty top bar point `menu_bar` plus (700, 10) | M1 checks it still lands on empty space with the 132 px mode pill and the page switcher; moves it if not |
| `tests/test_viewport_draw.py:521, 556 to 561` | free band `DOCK_BOTTOM + DOCK_H + SPACE_3`, HUD corners from `HUD_H` | tokens; passes with `HUD_H` 24 (M3) |
| `tests/test_gizmo_transform.py:762` | `GIZMO_AXIS_FIRST_PX` | symbolic; M3 runs the suite with 2.0 |
| `tests/test_camera.py:246 to 253, 611 to 633` | `MIN_APPROACH`, `NAV_MIN_DEPTH` | world units, unchanged |
| `tests/test_interface_defects.py:265, 269` | no horizontal overflow; spin line edits at least 28 wide | watch: labels 120, indent 32, spacing 2 (net +2 px per row); M5 runs it at 1280 x 720 |
| `tests/test_modeling_ui.py:122` | Attribute Manager at least 25 percent of the column | ratio, unchanged |
| drag tests in `test_gizmo_transform.py`, `test_modeling_interaction.py`, `test_context_menu.py`, `test_pen.py` | drags assume a threshold of 3 | M3 runs them; a test that drags by 4 px or less moves its target farther, the threshold stays 4 |

---

## 11. Guard: `tests/test_metrics.py` (new, owner M1)

Purpose: fail when a size outside the norm enters the interface. It runs offscreen like the other suites and
uses only the standard library, PySide6 and the package.

### 11.1 Files it scans

Every `.py` file under `quartz_studio` whose text contains `PySide6.QtWidgets`, plus `quartz_studio/icons.py`,
minus `quartz_studio/theme.py` (checked by 11.2 and 11.3), `widgets/title_row.py`, `widgets/sculpt_bar.py`,
everything under `fileio/` and `objects/`, and `modeling/` files other than `panel.py` and `interaction.py`.
The list is computed at collection time, so new packages are covered without editing the test. Each file is
one parametrized case (id = path relative to `quartz_studio`, for example `widgets/viewport.py`), so a builder
runs `.\.venv\Scripts\python.exe -m pytest tests/test_metrics.py -k viewport`.

### 11.2 `test_norm_table`

Pins `theme.allowed_px`, `theme.snap_px` and `theme.snap_px_up`:

- allowed: 0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 88, 96, 112,
  120, 128, 136, 140, 144, 160, 192, 200, 240, 256, 260, 304, 320, 328, 384, 416, 488, 512, 720, 896,
  1024, 1280, 1344, -4;
- not allowed: 3, 5, 7, 9, 22, 26, 30, 34, 42, 54, 60, 62, 84, 85, 126, 170, 300, 325, 340, 385, 396, 408,
  875, 890, 1349, 9.5, 1.6, 0.45;
- every example of section 1.3, both functions.

### 11.3 `test_theme_tokens`

- every name in `theme.PX_TOKENS` exists, is an `int`, and `allowed_px` holds; 1 only for `FOCUS_RING_W`;
- `theme.ICON_STROKE_W` in `{1.0, 2.0}`; `theme.HEADER_TRACKING` between 100 and 130;
- every module-level `int` or `float` of `theme` (found with `vars(theme)`, booleans excluded) is in
  `PX_TOKENS`, `NON_PX_TOKENS`, `LEGACY_TOKENS` or `PX_MAIN` / `PX_BELOW_128` themselves, so a new number
  added to the theme must be classified.

### 11.4 `test_source_sizes[file]` (AST)

Parse the file with `ast`. Resolve names with a small evaluator: `ast.Constant` numbers, unary minus, binary
`+ - * / //`, `ast.IfExp` (both branches are checked), `theme.NAME` (read from the imported `theme`), bare
names bound at module or class level in the same file to such expressions. Anything else (calls, attributes
of `self`, runtime values) is skipped, never guessed.

Checks:

1. Calls whose function name is one of `setFixedSize`, `setFixedWidth`, `setFixedHeight`, `setMinimumSize`,
   `setMinimumWidth`, `setMinimumHeight`, `setMaximumSize`, `setMaximumWidth`, `setMaximumHeight`,
   `setContentsMargins`, `setSpacing`, `setHorizontalSpacing`, `setVerticalSpacing`, `addSpacing`,
   `insertSpacing` (second argument), `setTextMargins`, `setIndentation`, `setIconSize`,
   `setMinimumSectionSize`, `QSize`, `QSizeF`: every evaluated argument is `allowed_px` and integral.
   1 is accepted only in `setFixedHeight` and `setFixedWidth` (1 px rules) and in `setContentsMargins` when
   all four values are 1 (a border inset). `setMaximum*` with 16777215 (`QWIDGETSIZE_MAX`) is accepted.
2. `setPixelSize`: evaluated value allowed and at least 10. `setPointSize` and `setPointSizeF`: always fail.
3. `QPen(color, width, ...)` and `QPen(color, width=...)`: width allowed (1 accepted). In `icons.py` also the
   width argument of `_pen`, `_both` and `_dashed` (grid units): in `{1, 2, 4}`. A width held in a variable
   or a parameter is not evaluated; strokes of icon painters on other grids (`NAV_STROKE` in viewport.py)
   are kept that way on purpose.
4. Module and class constants (`NAME = expression` at module level or directly in a class body) whose name
   ends with `_H`, `_W`, `_PX`, `_SIZE`, `_ICON`, `_BUTTON`, `_GAP`, `_PAD`, `_PADDING`, `_INSET`, `_MARGIN`,
   `_INDENT`, `_LEFT`, `_TOP`, `_WIDTH`, `_HEIGHT`, `_LENGTH`, `_RADIUS`, `_ROW`, `_CLEARANCE`, `_THRESHOLD`,
   `_STEP`, `_X`, `_CX`, `_R`, `_COL`, or is exactly `BUTTON`, `ICON`, `ROW`, `GAP`, `MARGIN`, `SIDE`, `HIT`:
   evaluated value allowed and integral-valued (5.0 fails, 4.0 passes). 1 is accepted only when the name
   contains `WIDTH`, `LINE`, `RULE` or `BORDER` or ends with `_W` (pen and line widths such as
   `PREVIEW_WIRE_WIDTH`, `FOCUS_WIDTH`). Non-numeric values (colours, strings) are skipped.
5. Allow-list of constants that match 4 but are not px (key = file id, constant name):
   `widgets/viewport.py`: `WORLD_AXIS_LENGTH` (cm), `MIN_FRAME_RADIUS` (cm), `FRAME_MARGIN` (factor),
   `RING_TIE_PX` (epsilon), `ROTATE_STEP` (degrees), `SCALE_STEP` (factor); `modeling/interaction.py`:
   `PERCENT_PER_PX` (ratio), `ANGLE_PER_PX` (ratio). Each entry carries its one-word reason in the test
   data; a new entry needs one too.
6. Every px number inside a string literal of the file that looks like QSS (contains `{` or `px;`) is checked
   by the rules of 11.5 after the f-string pieces are evaluated where possible; pieces that cannot be
   evaluated are skipped.

### 11.5 `test_stylesheets`

Collect QSS text from `theme.stylesheet()`, `menu_bar._menu_qss()`, `tool_palette.rail_stylesheet()`,
`object_palette.dock_stylesheet()`, `attribute_manager.SPIN_STYLE`, `attribute_manager.VECTOR_SPIN_STYLE`,
`attribute_manager.SPIN_BUTTONS_STYLE`, and `styleSheet()` of every widget of a `MainWindow` built offscreen
at 1920 x 1010 (shown, settled with `processEvents`, default sizes applied). For each declaration
`property: value;` (regex `([a-z-]+)\s*:\s*([^;{}]*)`), every number with the unit `px` must be allowed by
absolute value and integral; `1px` only when the property starts with `border` or when the property is
`height` in a selector containing `separator`; any number with the unit `pt` fails. The failure message names
the selector, the property and the value.

### 11.6 `test_live_widgets`

Build the window as in 11.5 at 1920 x 1010 and again at 1280 x 720. For every widget that is visible to the
window: when `minimumWidth() == maximumWidth()` and the value is between 1 and 16777214, it is allowed (1 only
for widgets 1 px thick, that is rules); the same for heights; for every `layout()`: the four contents margins
are allowed (all four 1 accepted), and `spacing()` is allowed or -1 (style default). Splitter handles, scroll
bar internals and `QMenu` popups not shown are not walked. Failures list class name, object name and the
value. This layer catches computed sizes such as `FIELD_H + 2`.

### 11.7 What the guard does not check

Window-derived sizes, text metrics, glyph geometry, the dock width and other sums of allowed parts, sizes
drawn by Qt's style (default frame widths, native title bar), and the exempt files of 11.1.

---

## 12. File ownership and order

### 12.1 When this pass runs

Recommendation: the norm is a rule for every feature builder from now on (section 9, last paragraph), and
the sweep of this file runs last, after every feature fleet of tonight has finished, followed by one
integration step.

Reasons: the sweep touches almost every widget file (theme, common, command bar, menu bar, main window,
viewport, palettes, managers, panel, icons). Running it first would make every feature builder start from
files that change under them and would put a second owner on files the feature contracts own
(`main_window.py`, `widgets/menu_bar.py`, `app.py`, `widgets/viewport.py`); running it in parallel is
impossible with one owner per file. Running it last means each file has exactly one owner at a time, the
guard sees the finished feature code, and the tests of the feature builders are not broken mid-run by token
changes. `tests/test_metrics.py` is written in the sweep, not earlier, so it cannot fail other fleets' runs.

### 12.2 Builders of the sweep (5, in parallel)

| Builder | Files it owns (nobody else edits them in the sweep) |
|---|---|
| M1 theme and shared | `quartz_studio/theme.py` (the only owner of theme.py), `quartz_studio/widgets/common.py`, `quartz_studio/widgets/press_feedback.py`, `quartz_studio/icons.py`, `quartz_studio/app.py`, `tests/test_metrics.py` (new), `tests/test_press_feedback.py` |
| M2 window and top row | `quartz_studio/main_window.py`, `quartz_studio/widgets/command_bar.py`, `quartz_studio/widgets/menu_bar.py`, `quartz_studio/widgets/status_bar.py`, `quartz_studio/widgets/context_menu.py`, `quartz_studio/widgets/menus_data.py`, `tests/test_smoke.py`, `tests/test_wiring.py`, `tests/test_context_menu.py` |
| M3 viewport | `quartz_studio/widgets/viewport.py`, `quartz_studio/modeling/interaction.py`, `tests/test_viewport_draw.py`, `tests/test_viewport3d.py`, `tests/test_camera.py`, `tests/test_gizmo_transform.py`, `tests/test_modeling_interaction.py`, `tests/test_pen.py` |
| M4 palettes | `quartz_studio/widgets/tool_palette.py`, `quartz_studio/widgets/object_palette.py`, `tests/test_tool_palette.py` |
| M5 managers | `quartz_studio/widgets/object_manager.py`, `quartz_studio/widgets/attribute_manager.py`, `quartz_studio/widgets/coordinates.py`, `quartz_studio/modeling/panel.py`, `tests/test_attribute_manager.py`, `tests/test_coordinates.py`, `tests/test_object_manager.py`, `tests/test_interface_defects.py`, `tests/test_modeling_ui.py` |

Shared files and where they went: `theme.py` and `icons.py` to M1; `main_window.py` and `menus_data.py` to
M2; `widgets/viewport.py` to M3; shared tests `test_smoke.py` to M2, `test_press_feedback.py` to M1,
`test_tool_palette.py` to M4, `test_metrics.py` to M1. Nobody in the sweep edits `SPEC.md`, `README.md`,
`scene.py`, the new packages, `widgets/title_row.py`, `widgets/sculpt_bar.py` or anything in `D:\Markdown`.

### 12.3 Order inside the sweep

1. M1 lands the theme changes first (sections 3.1, 3.3, 3.4 and the QSS of section 4), keeping
   `LEGACY_TOKENS`. M2 to M5 start editing at once against the names of section 3.3 and run their suites
   after `.\.venv\Scripts\python.exe -c "from quartz_studio import theme; theme.FONT_PX, theme.snap_px_up"`
   succeeds. No builder other than M1 adds a theme token; a missing one is reported, not added.
2. Each builder fixes its rows of sections 5 and 7, runs its own suites and
   `tests/test_metrics.py -k <its files>` once M1 has written it, and reports the result.
3. M1 writes `tests/test_metrics.py`; until M2 to M5 finish, failures in their files are expected and are
   not M1's to fix.

### 12.4 Integration step (one agent, after M1 to M5)

- Replace the remaining users of `LEGACY_TOKENS` (at least `tags/widgets.py` for `HEADER_LETTER_SPACING`,
  plus any file of the new packages), delete the four legacy names from `theme.py`, empty `LEGACY_TOKENS`.
- Fix any guard failure left in files no sweep builder owns (new packages).
- Update `SPEC.md`: 9.3 token table (`SEGMENT_H` 32, `CHIP_H` 24, `HUD_H` 24, `COMMAND_BUTTON` 32,
  `FIELD_H` 24, `COORDINATES_H` 128, fonts in px, `HEADER_TRACKING`, removed tokens), 9.5 measured table
  (measure with the probe of 11.6), 9.6 (toggle 32 x 16, slider 4 / 12, scrollbar unchanged), 9.7 (menu
  pill 28, badge 20), 9.9.6 and 9.11 (mode pill 32 with 32 x 28 segments), and a short section that points
  to this file as the pixel norm.
- Run every suite (`runall`) and `tests/test_metrics.py`; take snapshots at 1920 x 1010 and 1280 x 720 with
  `tools/snapshot.py` and check rail, dock, menus, top row, Attribute Manager and Coordinates by eye.
- The orchestrator, not the builders, records the change in the project's Markdown files.

---

## 13. Acceptance

- `tests/test_metrics.py` passes, all of its cases, and no allow-list entry lacks a reason.
- All existing suites pass, including `tests/test_smoke.py` at 1920 x 1007 and 1280 x 720,
  `tests/test_tool_palette.py`, `tests/test_press_feedback.py`, `tests/test_interface_defects.py`.
- No `pt` font size and no `setPointSize` in the scanned files; `grep -n "pt;" quartz_studio` finds nothing in
  stylesheets.
- The offscreen walk of section 6 reports no widget, margin or spacing outside the norm.
- The Coordinates card is 128 px tall at both window sizes and does not change when the window or the
  splitter changes.
- Snapshots show the same layout with the new sizes and no clipped text in the top row, menus, the
  Attribute Manager or Coordinates.

---

## 14. Open points

- Reading of "multiples of 6" and "additions between multiples of 2 and of 6" (section 1.2): the closed list
  is used; the wider reading would also allow 22, 26, 38, 50 and so on. Nothing here depends on it.
- Small font size: 10 px for uppercase headers follows the conversion rule (10.67 -> 10); DesignPx's site
  scale starts at 12. If the owner prefers 12, only `FONT_SMALL_PX` changes.
- Overrides of `snap_px` chosen for balance, each stated in its row: attribute and tool option label width
  120 (not 128), section title 14 (not 12), slider groove 4 (not 2), drag thresholds 4 (not 2), modeling hover
  edge 4 (not 2).
- The right column at 1280 x 720 depends on the managers' size hint after tonight's Attribute Manager
  changes; 416 is the expected value, the integration step measures it.
