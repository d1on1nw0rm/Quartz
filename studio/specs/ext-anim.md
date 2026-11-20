# Extension: anim

Package `quartz_studio/anim` (about 4.7k lines). Loaded by `ext/install.py` as `quartz_studio.anim`.

## Purpose

Keyframe animation: per-object tracks for transform, visibility, parameters and point-level animation, interpolation and easing, loop modes, playback, autokey, timeline bar, dope sheet and F-curve editor.

## Data in extras

Scene extras `anim` (`core.ANIM_KEY`): time settings `{"fps": 30, "min": 0, "max": 90, "preview_min": 0, "preview_max": 90, "frame": 0, "loop": true, "pingpong": false, "play_mode": "realtime", "default_interp": "spline", ...}`. fps is clamped to 1..240.

Object extras:

| Key | Shape |
|-----|-------|
| `tracks` (`core.TRACKS_KEY`) | dict channel to list of keys sorted by frame |
| `track_modes` (`core.MODES_KEY`) | dict channel to loop modes before and after |

Key dict: `{"frame": number, "value": scalar, vector or packed points, "interp": "spline"/"linear"/"step", "ease": "none"/"in"/"out"/"both", "in_tan": [dx, dy] or None, "out_tan": [dx, dy] or None}`.
Channels: transform channels, `visibility`, `points` (point arrays packed with `__pla__`), and `param.<key>` for object parameters.

## Public functions

- `core`: `time_settings`, `set_time_settings`, `playback_mode`, `set_playback_mode`, `retime_document`, `current_frame`, `fps`, `set_frame`, `frame_to_seconds`, `seconds_to_frame`, `format_time`, `make_key`, `tracks`, `get_track`, `set_track`, `track_modes`, `loop_mode`, `set_loop`, `has_animation`, `animated_objects`, `channels_of`, `param_channels`, `channel_value`, `apply_channel`, `evaluate_track`, `evaluate`, `insert_key`, `set_key`, `record_active`, `record_points`, `begin_edit`, `end_edit`, `edit_group`.
- `player`: `Player` (play forward and back, stop, step, go start or end), `AutoKey`, `AnimContext`, `get_context(scene)`, `drop_context`.

## Widgets

`TimelineBar` (`FrameRuler`, `PreviewStrip`, key context menu), `DopeSheet` (`DopeCanvas`, expandable rows, key drag), `CurveEditor` (`CurveCanvas`, tangent handles, channel list). Shared helpers in `ui_common`.

## Menus, docks, pages, shortcuts

- Menu `Animate`: Record Active Objects, Autokeying, Add Parameter Keys, Record Position, Rotation, Scale, Visibility, transport entries (Go to Start, Previous Frame, Play Backwards, Play Forwards, Stop, Next Frame, Go to End, Previous Key, Next Key), Loop Playback, Point Level Animation (Record Points, Record Point Selection, Clear Points), Delete Selected Keys, Delete Keys at Current Frame, Delete Tracks of Active Objects, Copy Keys, Paste Keys, Reverse Keys, Preview Range to Keys, Bake Objects, Change Frame Rate Keeping Timing (24, 25, 30, 48, 50, 60 fps), Playback Mode (Simple, Loop, Ping-Pong), Interpolation (Spline, Linear, Step), Ease (None, Ease In, Ease Out, Ease In Out).
- Docks: Timeline, Dope Sheet, F-Curves (bottom).
- Layout: `Animate` (dock layout).
- Declared key actions: F9 Record, Ctrl+F9 Autokeying, Shift+G Start, `,` Previous Frame, F6 Play Backwards, F8 Play Forwards, F7 Stop, `.` Next Frame, Shift+F End, Ctrl+F Previous Key, Ctrl+G Next Key.

## Known gaps

- The installer only keeps shortcuts with Ctrl or Alt, so F6, F7, F8, F9, Shift+G, Shift+F, `,` and `.` are skipped; only Ctrl+F9, Ctrl+F and Ctrl+G are bound by the installer (the widgets may still handle keys locally).
- Point-level animation stores full point arrays per key; memory grows with mesh size times key count.
