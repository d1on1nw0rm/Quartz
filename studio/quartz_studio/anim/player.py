from __future__ import annotations

import copy
import math
import weakref

from PySide6.QtCore import QElapsedTimer, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from ..ext import store
from . import core

__all__ = ["Player", "AutoKey", "AnimContext", "get_context", "drop_context"]


def _mouse_down() -> bool:
    try:
        return QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton
    except RuntimeError:
        return False


def _fkey(f) -> float:
    return round(float(f), 4)


class Player(QObject):

    frameChanged = Signal(float)
    stateChanged = Signal(int)

    def __init__(self, scene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self._direction = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()
        self._start_frame = 0.0
        self._last = 0.0

    @property
    def direction(self) -> int:
        return self._direction

    def is_playing(self) -> bool:
        return self._direction != 0

    def _range(self) -> tuple[int, int]:
        s = core.time_settings(self.scene)
        return s["preview_min"], s["preview_max"]

    def play(self, direction: int = 1) -> None:
        direction = 1 if direction >= 0 else -1
        lo, hi = self._range()
        f = core.current_frame(self.scene)
        if direction > 0 and f >= hi and hi > lo:
            self.set_frame(lo)
        elif direction < 0 and f <= lo and hi > lo:
            self.set_frame(hi)
        elif not lo <= f <= hi:
            self.set_frame(lo if direction > 0 else hi)
        self._direction = direction
        self._restart_clock()
        rate = core.fps(self.scene)
        self._timer.setInterval(max(1, int(round(1000.0 / rate))))
        self._timer.start()
        self.stateChanged.emit(direction)

    def _restart_clock(self) -> None:
        self._start_frame = float(core.current_frame(self.scene))
        self._last = self._start_frame
        self._clock.start()

    def play_forward(self) -> None:
        self.play(1)

    def play_backward(self) -> None:
        self.play(-1)

    def toggle(self, direction: int = 1) -> None:
        if self.is_playing():
            self.stop()
        else:
            self.play(direction)

    def stop(self) -> None:
        was = self._direction
        self._direction = 0
        self._timer.stop()
        if was:
            self.stateChanged.emit(0)

    def set_frame(self, frame: float) -> float:
        f = core.set_frame(self.scene, frame)
        self.frameChanged.emit(float(f))
        return f

    def advance(self, steps: float) -> float:
        lo, hi = self._range()
        s = core.time_settings(self.scene)
        f = float(core.current_frame(self.scene)) + steps
        if f > hi or f < lo:
            if s["pingpong"] and hi > lo and self.is_playing():
                span = hi - lo
                over = (f - hi) if f > hi else (lo - f)
                over = math.fmod(over, 2 * span)
                if over > span:
                    f = lo + (over - span) if f > hi else hi - (over - span)
                else:
                    self._direction = -self._direction
                    f = hi - over if f > hi else lo + over
                    out = self.set_frame(float(min(max(f, lo), hi)))
                    self._restart_clock()
                    self.stateChanged.emit(self._direction)
                    return out
                return self.set_frame(float(min(max(f, lo), hi)))
            if s["loop"] and hi > lo and not s["pingpong"]:
                span = hi - lo + 1
                f = lo + math.fmod(f - lo, span)
                if f < lo:
                    f += span
                f = float(math.floor(f + 1e-9))
            else:
                f = float(min(max(f, lo), hi))
                self.set_frame(f)
                self.stop()
                return f
        return self.set_frame(f)

    def _tick(self) -> None:
        if not self._direction:
            return
        s = core.time_settings(self.scene)
        if s["play_mode"] == "all_frames":
            self.advance(self._direction)
            return
        elapsed = self._clock.elapsed() / 1000.0
        target = self._start_frame + self._direction * math.floor(elapsed * s["fps"] + 1e-9)
        steps = target - self._last
        if steps:
            self._last = target
            self.advance(steps)

    def go_start(self) -> float:
        return self.set_frame(core.time_settings(self.scene)["preview_min"])

    def go_end(self) -> float:
        return self.set_frame(core.time_settings(self.scene)["preview_max"])

    def go_doc_start(self) -> float:
        return self.set_frame(core.time_settings(self.scene)["min"])

    def go_doc_end(self) -> float:
        return self.set_frame(core.time_settings(self.scene)["max"])

    def step(self, n: int = 1) -> float:
        s = core.time_settings(self.scene)
        f = float(core.current_frame(self.scene)) + n
        return self.set_frame(min(max(f, s["min"]), s["max"]))

    def next_frame(self) -> float:
        return self.step(1)

    def prev_frame(self) -> float:
        return self.step(-1)

    def _key_objects(self) -> list:
        objs = list(self.scene.selected_objects()) if hasattr(self.scene, "selected_objects") else []
        if not objs and getattr(self.scene, "active", None) is not None:
            objs = [self.scene.active]
        objs = [o for o in objs if core.has_animation(o)]
        return objs or core.animated_objects(self.scene)

    def next_key(self) -> float | None:
        f = core.next_key_frame(self._key_objects(), core.current_frame(self.scene))
        return None if f is None else self.set_frame(f)

    def prev_key(self) -> float | None:
        f = core.prev_key_frame(self._key_objects(), core.current_frame(self.scene))
        return None if f is None else self.set_frame(f)


class AutoKey(QObject):

    toggled = Signal(bool)

    def __init__(self, scene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self._enabled = False
        self._busy = False
        self._pending = False
        self._snap: dict = {}
        self.recorded = 0
        self._poll = QTimer(self)
        self._poll.setInterval(30)
        self._poll.timeout.connect(self._poll_release)
        scene.changed.connect(self._on_changed)
        sel = getattr(scene, "selectionChanged", None)
        if sel is not None:
            sel.connect(self.refresh)

    def close(self) -> None:
        self._poll.stop()
        for sig, fn in ((getattr(self.scene, "changed", None), self._on_changed),
                        (getattr(self.scene, "selectionChanged", None), self.refresh)):
            if sig is None:
                continue
            try:
                sig.disconnect(fn)
            except (RuntimeError, TypeError):
                pass

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def pending(self) -> bool:
        return self._pending

    def set_enabled(self, flag: bool) -> None:
        flag = bool(flag)
        if flag == self._enabled:
            return
        self._enabled = flag
        self._pending = False
        self._poll.stop()
        self.refresh()
        self.toggled.emit(flag)

    def toggle(self) -> bool:
        self.set_enabled(not self._enabled)
        return self._enabled

    def _channels(self, obj) -> list[str]:
        chans = list(core.TRANSFORM_CHANNELS)
        for ch in core.channels_of(obj):
            if ch not in chans and ch != core.POINTS:
                chans.append(ch)
        return chans

    def _targets(self) -> list:
        objs = list(self.scene.selected_objects()) if hasattr(self.scene, "selected_objects") else []
        if not objs and getattr(self.scene, "active", None) is not None:
            objs = [self.scene.active]
        return [o for o in objs if o in self.scene.objects]

    def _values(self, obj) -> dict:
        return {ch: core.channel_value(obj, ch) for ch in self._channels(obj)}

    def refresh(self, *_a) -> None:
        if self._pending and self._enabled and not core.is_evaluating(self.scene):
            self.flush()
        self._pending = False
        self._snap = {id(o): (o, self._values(o)) for o in self._targets()}

    def _on_changed(self) -> None:
        if self._busy or not self._enabled:
            return
        if core.is_evaluating(self.scene):
            self._pending = False
            self.refresh()
            return
        if _mouse_down():
            self._pending = True
            if not self._poll.isActive():
                self._poll.start()
            return
        self.flush()

    def _poll_release(self) -> None:
        if _mouse_down():
            return
        self._poll.stop()
        if self._pending:
            self.flush()

    def flush(self) -> int:
        self._pending = False
        self._poll.stop()
        if not self._enabled or self._busy:
            return 0
        self._busy = True
        n = 0
        try:
            with core.edit_group(self.scene):
                for obj in self._targets():
                    old = self._snap.get(id(obj))
                    now = self._values(obj)
                    if old is None or old[0] is not obj:
                        self._snap[id(obj)] = (obj, now)
                        continue
                    prev = old[1]
                    changed = [ch for ch, v in now.items() if _differs(prev.get(ch), v)]
                    if changed:
                        n += core.set_key(obj, changed, None, self.scene)
                    self._snap[id(obj)] = (obj, now)
        finally:
            self._busy = False
        self.recorded += n
        return n


def _differs(a, b) -> bool:
    if a is None or b is None:
        return a is not b
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) > 1e-9
    if isinstance(a, list) and isinstance(b, list):
        return len(a) != len(b) or any(_differs(x, y) for x, y in zip(a, b))
    try:
        return bool(a != b)
    except Exception:
        return True


class AnimContext(QObject):

    frameChanged = Signal(float)
    timeChanged = Signal()
    keysChanged = Signal()
    keySelectionChanged = Signal()

    def __init__(self, scene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self.player = Player(scene, self)
        self.autokey = AutoKey(scene, self)
        self._selection: list = []
        self._sel_index: set = set()
        self._sel_frames: set = set()
        self.clipboard: dict = {}
        self._extras_ref = getattr(scene, "extras", None)
        self._settings = core.time_settings(scene)
        self._swap_pending = False
        self._swap_original = None
        self._closed = False
        self._swap_timer = QTimer(self)
        self._swap_timer.setSingleShot(True)
        self._swap_timer.setInterval(0)
        self._swap_timer.timeout.connect(self._finish_swap)
        ref = weakref.ref(self)

        def listener(owner, key, _ref=ref):
            ctx = _ref()
            if ctx is not None:
                ctx._on_store(owner, key)

        self._listener = listener
        _listeners().append(listener)
        self.player.frameChanged.connect(self._on_player_frame)
        if hasattr(scene, "objectsChanged"):
            scene.objectsChanged.connect(self._on_objects)
        if hasattr(scene, "changed"):
            scene.changed.connect(self._on_scene_changed)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.player.stop()
        self.autokey.close()
        self._swap_timer.stop()
        lst = _listeners()
        if self._listener in lst:
            lst.remove(self._listener)
        for sig, fn in ((getattr(self.scene, "objectsChanged", None), self._on_objects),
                        (getattr(self.scene, "changed", None), self._on_scene_changed)):
            if sig is None:
                continue
            try:
                sig.disconnect(fn)
            except (RuntimeError, TypeError):
                pass

    @property
    def selection(self) -> list:
        return self._selection

    @selection.setter
    def selection(self, refs) -> None:
        self._set_selection(list(refs))

    def _set_selection(self, refs: list) -> None:
        self._selection = [(r[0], r[1], r[2]) for r in refs]
        self._sel_index = {(id(o), ch, _fkey(f)) for o, ch, f in self._selection}
        self._sel_frames = {(id(o), _fkey(f)) for o, _ch, f in self._selection}

    def _on_player_frame(self, _f: float) -> None:
        self.autokey.refresh()

    def _on_store(self, owner, key) -> None:
        if self._closed:
            return
        if owner is self.scene and key == core.ANIM_KEY:
            self._check_settings()
            return
        if key in (core.TRACKS_KEY, core.MODES_KEY) and owner in getattr(self.scene, "objects", ()):
            self._prune()
            self.keysChanged.emit()

    def _check_settings(self) -> None:
        s = core.time_settings(self.scene)
        if s == self._settings:
            return
        old = self._settings
        self._settings = s
        self.timeChanged.emit()
        if not core._same(s["frame"], old["frame"]):
            self.frameChanged.emit(float(s["frame"]))

    def _on_objects(self) -> None:
        if self._closed:
            return
        ex = getattr(self.scene, "extras", None)
        if ex is not self._extras_ref:
            raw = ex.get(core.ANIM_KEY) if isinstance(ex, dict) else None
            self._swap_original = copy.deepcopy(raw)
            self._extras_ref = ex
            self._swap_pending = True
            core.set_frame(self.scene, self._settings["frame"], evaluate_scene=True)
            self._swap_timer.start()
        self._prune()
        self.autokey.refresh()
        self._check_settings()
        self.keysChanged.emit()

    def _on_scene_changed(self) -> None:
        if not self._closed and not core.is_evaluating(self.scene):
            self.sync()

    def _finish_swap(self) -> None:
        if not self._closed:
            self.sync()
            self._swap_pending = False

    def _history(self) -> bool:
        sc = self.scene
        undo = getattr(sc, "can_undo", None)
        redo = getattr(sc, "can_redo", None)
        return bool((callable(undo) and undo()) or (callable(redo) and redo()))

    def sync(self) -> None:
        if self._closed:
            return
        ex = getattr(self.scene, "extras", None)
        if ex is not self._extras_ref:
            self._extras_ref = ex
            self._swap_pending = False
            self._load_document()
        elif self._swap_pending and not self._history():
            self._swap_pending = False
            if self._swap_original is None and isinstance(ex, dict):
                ex.pop(core.ANIM_KEY, None)
            self._load_document()

    def _load_document(self) -> None:
        s = core.time_settings(self.scene)
        core.evaluate(self.scene, s["frame"])
        self._prune()
        self.autokey.refresh()
        self._check_settings()
        self.keysChanged.emit()

    def _prune(self) -> None:
        objs = getattr(self.scene, "objects", ())
        kept = [r for r in self._selection if r[0] in objs]
        kept = core.refs_exist(kept)
        if len(kept) != len(self._selection):
            self._set_selection(kept)
            self.keySelectionChanged.emit()

    @property
    def frame(self) -> float:
        self.sync()
        return core.current_frame(self.scene)

    def settings(self) -> dict:
        self.sync()
        return core.time_settings(self.scene)

    def set_settings(self, **kw) -> dict:
        self.sync()
        return core.set_time_settings(self.scene, **kw)

    def playback_mode(self) -> str:
        return core.playback_mode(self.scene)

    def set_playback_mode(self, mode: str) -> str:
        return core.set_playback_mode(self.scene, mode)

    def set_frame(self, frame: float) -> float:
        self.sync()
        return self.player.set_frame(frame)

    def retime(self, fps: float) -> int:
        self.sync()
        n = core.retime_document(self.scene, fps)
        self.autokey.refresh()
        self._check_settings()
        self.keysChanged.emit()
        return n

    def targets(self) -> list:
        return self.autokey._targets()

    def record(self, channels=None) -> int:
        n = core.record_objects(self.scene, self.targets(), channels)
        self.autokey.refresh()
        return n

    def record_params(self, keys=None) -> int:
        n = core.record_params(self.scene, keys, objects=self.targets())
        self.autokey.refresh()
        return n

    def record_visibility(self) -> int:
        n = core.record_visibility(self.scene, objects=self.targets())
        self.autokey.refresh()
        return n

    def record_points(self) -> int:
        n = core.record_points(self.scene)
        self.autokey.refresh()
        return n

    def record_point_selection(self) -> int:
        n = core.record_point_selection(self.scene)
        self.autokey.refresh()
        return n

    def clear_points(self) -> int:
        n = core.clear_points(self.scene, self.targets())
        self.autokey.refresh()
        return n

    def evaluate(self) -> list:
        out = core.evaluate(self.scene)
        self.autokey.refresh()
        return out

    def is_selected(self, obj, channel: str, frame: float) -> bool:
        return (id(obj), channel, _fkey(frame)) in self._sel_index

    def is_frame_selected(self, obj, frame: float) -> bool:
        return (id(obj), _fkey(frame)) in self._sel_frames

    def select(self, refs, mode: str = "replace") -> None:
        refs = list(refs)
        cur = [] if mode == "replace" else list(self._selection)
        index = {(id(c[0]), c[1], _fkey(c[2])): i for i, c in enumerate(cur)}
        drop: set = set()
        for r in refs:
            key = (id(r[0]), r[1], _fkey(r[2]))
            hit = key in index and index[key] not in drop
            if mode == "remove" or (mode == "toggle" and hit):
                if hit:
                    drop.add(index[key])
            elif not hit:
                index[key] = len(cur)
                cur.append((r[0], r[1], r[2]))
        cur = [c for i, c in enumerate(cur) if i not in drop]
        if cur != self._selection:
            self._set_selection(cur)
            self.keySelectionChanged.emit()

    def clear_selection(self) -> None:
        self.select([], "replace")

    def _after_edit(self) -> None:
        self.evaluate()

    def delete_selected(self) -> int:
        with core.edit_group(self.scene):
            n = core.delete_keys(self._selection)
        self._set_selection([])
        self.keySelectionChanged.emit()
        self._after_edit()
        return n

    def delete_at_frame(self) -> int:
        n = 0
        f = self.frame
        with core.edit_group(self.scene):
            for obj in self.targets():
                n += core.delete_keys_at(obj, f)
        self._after_edit()
        return n

    def delete_tracks(self) -> int:
        n = 0
        with core.edit_group(self.scene):
            for obj in self.targets():
                n += core.clear_tracks(obj)
        return n

    def copy_selected(self) -> int:
        self.clipboard = core.copy_keys(self._selection)
        return len(self.clipboard.get("items", []))

    def cut_selected(self) -> int:
        n = self.copy_selected()
        self.delete_selected()
        return n

    def paste(self, frame: float | None = None, targets=None) -> list:
        refs = core.paste_keys(self.scene, self.clipboard, frame, targets)
        if refs:
            self.select(refs)
            self._after_edit()
        return refs

    def move_selected(self, delta: float) -> list:
        refs = core.move_keys(self._selection, delta)
        self.select(refs)
        self._after_edit()
        return refs

    def scale_selected(self, factor: float, pivot: float | None = None) -> list:
        try:
            refs = core.scale_keys(self._selection, factor, pivot)
        except ValueError:
            return []
        self.select(refs)
        self._after_edit()
        return refs

    def reverse_selected(self) -> list:
        refs = core.reverse_keys(self._selection)
        self.select(refs)
        self._after_edit()
        return refs

    def set_interp(self, interp: str) -> int:
        n = core.set_key_attrs(self._selection, interp=interp)
        self._after_edit()
        return n

    def set_ease(self, ease: str) -> int:
        n = core.set_key_attrs(self._selection, ease=ease)
        self._after_edit()
        return n

    def reset_tangents(self) -> int:
        n = core.reset_tangents(self._selection)
        self._after_edit()
        return n

    def flatten_tangents(self) -> int:
        n = core.flatten_tangents(self._selection)
        self._after_edit()
        return n

    def selected_channels(self) -> list:
        out = []
        seen: set = set()
        for o, ch, _f in self._selection:
            if (id(o), ch) not in seen:
                seen.add((id(o), ch))
                out.append((o, ch))
        return out

    def set_loop(self, before: str | None = None, after: str | None = None, channels=None) -> int:
        pairs = list(channels) if channels is not None else self.selected_channels()
        with core.edit_group(self.scene):
            for obj, ch in pairs:
                core.set_loop(obj, ch, before, after)
        self._after_edit()
        return len(pairs)

    def bake(self) -> int:
        n = 0
        with core.edit_group(self.scene):
            for obj in self.targets():
                if core.has_animation(obj):
                    n += core.bake_object(self.scene, obj)
        return n


def _listeners() -> list:
    lst = getattr(store, "_LISTENERS", None)
    if lst is None:
        lst = []
        store._LISTENERS = lst
    return lst


_CONTEXTS: dict = {}


def get_context(scene=None) -> AnimContext:
    if scene is None:
        from ..scene import get_scene
        scene = get_scene()
    entry = _CONTEXTS.get(id(scene))
    if entry is not None and entry[0]() is scene:
        return entry[1]
    if entry is not None:
        try:
            entry[1].close()
        except RuntimeError:
            pass
    ctx = AnimContext(scene)
    _CONTEXTS[id(scene)] = (weakref.ref(scene), ctx)
    try:
        scene.destroyed.connect(lambda *_a, k=id(scene): drop_context(k))
    except (AttributeError, RuntimeError, TypeError):
        pass
    return ctx


def drop_context(key) -> None:
    if not isinstance(key, int):
        key = id(key)
    entry = _CONTEXTS.pop(key, None)
    if entry is not None:
        try:
            entry[1].close()
        except RuntimeError:
            pass
