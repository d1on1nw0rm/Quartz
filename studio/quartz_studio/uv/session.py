from __future__ import annotations

import weakref
from contextlib import contextmanager
from typing import Callable, Iterable

import numpy as np
from PySide6.QtCore import QObject, Signal

from ..ext import store
from . import arrange, project, unwrap
from .data import (SEAMS_KEY, TAG_KEY, UV_KEY, Corners, add_seams, bounds_uv, clear_seams, edge_key,
                   get_seams, get_uv_array, point_groups, remove_seams, reset_uv, set_seams, set_uv_array,
                   transform_uv, uv_islands, write_scene)
from .texture import CHANNELS, TEXTURES_KEY, Brush, TextureCanvas, checker_pixels, load_canvas, save_canvas

__all__ = ["SELECT_MODES", "TOOLS", "UVSession", "session_for", "drop_session"]

SELECT_MODES = ("points", "polygons", "islands")
TOOLS = ("select", "move", "rotate", "scale", "paint", "erase", "fill")
_SESSIONS: dict[int, tuple] = {}


def _forget(key: int, ref) -> None:
    entry = _SESSIONS.get(key)
    if entry is not None and entry[0] is ref:
        _SESSIONS.pop(key, None)


def session_for(scene) -> "UVSession":
    key = id(scene)
    entry = _SESSIONS.get(key)
    if entry is not None:
        ref, sess = entry
        if ref() is scene:
            return sess
    sess = UVSession(scene)
    ref = weakref.ref(scene, lambda r, k=key: _forget(k, r))
    _SESSIONS[key] = (ref, sess)
    return sess


def drop_session(scene) -> None:
    entry = _SESSIONS.pop(id(scene), None)
    if entry is not None:
        entry[1].detach()


def _remove_listener(fn) -> None:
    listeners = getattr(store, "_LISTENERS", None)
    if isinstance(listeners, list):
        try:
            listeners.remove(fn)
        except ValueError:
            pass


def _raw(obj, key: str):
    extras = getattr(obj, "extras", None)
    return extras.get(key) if isinstance(extras, dict) else None


class UVSession(QObject):

    uvChanged = Signal()
    selectionChanged = Signal()
    textureChanged = Signal()
    toolChanged = Signal(str)
    modeChanged = Signal(str)
    brushChanged = Signal()
    channelChanged = Signal(str)
    objectChanged = Signal()
    message = Signal(str)

    def __init__(self, scene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._scene_ref = weakref.ref(scene)
        self.select_mode = "polygons"
        self.tool = "select"
        self.brush = Brush()
        self.channel = CHANNELS[0]
        self.texture_size = 1024
        self.selected_corners: set[int] = set()
        self.selected_polys: set[int] = set()
        self.uv_revision = 0
        self.topo_revision = 0
        self._working: np.ndarray | None = None
        self._working_ref = None
        self._corners: Corners | None = None
        self._corners_polys: list | None = None
        self._groups: tuple | None = None
        self._islands: tuple | None = None
        self._stats: tuple | None = None
        self._seen: tuple = (None, None, None)
        self._canvases: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self._last_ref = None
        self.last_message = ""
        self._suspend = 0
        self.project_paint = False
        self._connections = []
        for name in ("changed", "selectionChanged", "objectsChanged"):
            sig = getattr(scene, name, None)
            if sig is not None:
                try:
                    sig.connect(self._on_scene)
                    self._connections.append(sig)
                except (RuntimeError, TypeError):
                    pass
        self._listener = None
        listeners = getattr(store, "_LISTENERS", None)
        if isinstance(listeners, list):
            ref = weakref.ref(self)

            def listen(owner, key, ref=ref):
                me = ref()
                if me is not None:
                    me._on_store(owner, key)

            self._listener = listen
            listeners.append(listen)
            weakref.finalize(self, _remove_listener, listen)

    @property
    def scene(self):
        return self._scene_ref()

    def detach(self) -> None:
        for sig in self._connections:
            try:
                sig.disconnect(self._on_scene)
            except (RuntimeError, TypeError):
                pass
        self._connections = []
        if self._listener is not None:
            _remove_listener(self._listener)
            self._listener = None

    def _bump(self, topology: bool = True) -> None:
        self.uv_revision += 1
        if topology:
            self.topo_revision += 1

    def _working_obj(self):
        return self._working_ref() if self._working_ref is not None else None

    def _drop_working(self) -> None:
        self._working = None
        self._working_ref = None
        self._bump()

    def _set_working(self, arr: np.ndarray, obj, topology: bool = True) -> None:
        self._working = arr
        self._working_ref = weakref.ref(obj)
        self._bump(topology)

    def _remember(self, obj) -> None:
        if obj is None:
            self._seen = (None, None, None)
        else:
            self._seen = (_raw(obj, UV_KEY), _raw(obj, SEAMS_KEY), _raw(obj, TEXTURES_KEY))

    @contextmanager
    def _edit(self):
        scene = self.scene
        begin = getattr(scene, "begin_group", None)
        end = getattr(scene, "end_group", None)
        if begin is not None:
            begin()
        self._suspend += 1
        try:
            with write_scene(scene):
                yield
        finally:
            self._suspend -= 1
            if end is not None:
                end()
            self._remember(self.obj)

    def _on_store(self, owner, key: str) -> None:
        if self._suspend:
            return
        if owner is self.obj and key in (UV_KEY, SEAMS_KEY, TAG_KEY):
            self._drop_working()
            self._remember(owner)
            self.uvChanged.emit()
        elif owner is self.obj and key == TEXTURES_KEY:
            self._remember(owner)
            self.textureChanged.emit()

    def _on_scene(self, *args) -> None:
        if self._suspend:
            return
        obj = self.obj
        last = self._last_ref() if self._last_ref is not None else None
        if obj is not last:
            self._last_ref = weakref.ref(obj) if obj is not None else None
            self.selected_corners.clear()
            self.selected_polys.clear()
            self._drop_working()
            self._remember(obj)
            self.objectChanged.emit()
            self.selectionChanged.emit()
            self.uvChanged.emit()
            self.textureChanged.emit()
            return
        if obj is None:
            return
        uv_raw, seam_raw, tex_raw = _raw(obj, UV_KEY), _raw(obj, SEAMS_KEY), _raw(obj, TEXTURES_KEY)
        external = uv_raw is not self._seen[0] or seam_raw is not self._seen[1]
        textures = tex_raw is not self._seen[2]
        self._seen = (uv_raw, seam_raw, tex_raw)
        if external:
            self._drop_working()
            self._prune_selection()
            self.uvChanged.emit()
        elif self._working is not None and self._working_obj() is obj and not self._valid_working():
            self._drop_working()
            self._prune_selection()
            self.uvChanged.emit()
        elif self._working is None:
            self.uvChanged.emit()
        if textures:
            self.textureChanged.emit()

    @property
    def obj(self):
        obj = getattr(self.scene, "active", None)
        if obj is None or getattr(obj, "mesh", None) is None or not obj.mesh.polygons:
            return None
        return obj

    def corners(self) -> Corners | None:
        obj = self.obj
        if obj is None:
            return None
        polys = obj.mesh.polygons
        if self._corners is None or self._corners_polys != polys:
            self._corners = Corners(obj.mesh)
            self._corners_polys = list(polys)
            self._bump()
        return self._corners

    def _valid_working(self) -> bool:
        c = self.corners()
        return c is not None and self._working is not None and len(self._working) == c.count

    def uv(self) -> np.ndarray:
        obj = self.obj
        if obj is None:
            return np.zeros((0, 2))
        c = self.corners()
        if self._working is not None and self._working_obj() is obj and self._valid_working():
            return self._working
        arr = get_uv_array(obj, c)
        self._set_working(arr, obj)
        self._remember(obj)
        return arr

    def point_groups(self) -> np.ndarray:
        c = self.corners()
        if c is None:
            return np.zeros(0, dtype=np.int64)
        uv = self.uv()
        key = (self.topo_revision, id(c))
        if self._groups is None or self._groups[0] != key:
            self._groups = (key, point_groups(c, uv))
        return self._groups[1]

    def islands(self) -> list[list[int]]:
        c = self.corners()
        if c is None:
            return []
        uv = self.uv()
        key = (self.topo_revision, id(c))
        if self._islands is None or self._islands[0] != key:
            self._islands = (key, uv_islands(self.obj.mesh, uv, c))
        return self._islands[1]

    def preview(self, arr: np.ndarray, keep_topology: bool = False) -> None:
        obj = self.obj
        if obj is None:
            return
        self._set_working(np.asarray(arr, float), obj, topology=not keep_topology)
        self.uvChanged.emit()

    def commit(self, arr: np.ndarray | None = None, message: str = "") -> None:
        obj = self.obj
        if obj is None:
            return
        arr = self._working if arr is None else np.asarray(arr, float)
        if arr is None:
            return
        with self._edit():
            set_uv_array(obj, arr, self.corners())
        self._set_working(np.array(arr, float), obj)
        self.uvChanged.emit()
        if message:
            self.say(message)

    def say(self, text: str) -> None:
        self.last_message = text
        self.message.emit(text)

    def set_select_mode(self, mode: str) -> None:
        if mode not in SELECT_MODES:
            raise ValueError(f"unknown selection mode {mode!r}")
        if mode != self.select_mode:
            self.select_mode = mode
            if mode == "islands" and self.selected_polys:
                self.select_polys(self.selected_polys)
            self.modeChanged.emit(mode)

    def set_tool(self, tool: str) -> None:
        if tool not in TOOLS:
            raise ValueError(f"unknown tool {tool!r}")
        if tool != self.tool:
            self.tool = tool
            self.toolChanged.emit(tool)

    def _prune_selection(self) -> None:
        c = self.corners()
        if c is None:
            self.selected_corners.clear()
            self.selected_polys.clear()
            return
        self.selected_corners = {i for i in self.selected_corners if 0 <= i < c.count}
        self.selected_polys = {p for p in self.selected_polys if 0 <= p < c.poly_count}

    def clear_selection(self) -> None:
        if self.selected_corners or self.selected_polys:
            self.selected_corners.clear()
            self.selected_polys.clear()
            self.selectionChanged.emit()

    def _combine(self, current: set, items: set, add: bool, remove: bool) -> set:
        if remove:
            return current - items
        if add:
            return current | items
        return set(items)

    def select_corners(self, corners_idx: Iterable[int], add: bool = False, remove: bool = False) -> None:
        c = self.corners()
        if c is None:
            return
        items = {int(i) for i in corners_idx if 0 <= int(i) < c.count}
        self.selected_corners = self._combine(self.selected_corners, items, add, remove)
        if self.selected_corners:
            flags = np.zeros(c.count, dtype=bool)
            flags[np.fromiter(self.selected_corners, dtype=np.int64, count=len(self.selected_corners))] = True
            full = np.bincount(c.poly, weights=flags.astype(float), minlength=c.poly_count) >= c.sizes - 0.5
            full &= c.sizes > 0
            self.selected_polys = set(np.nonzero(full)[0].tolist())
        else:
            self.selected_polys = set()
        self.selectionChanged.emit()

    def select_polys(self, polys: Iterable[int], add: bool = False, remove: bool = False) -> None:
        c = self.corners()
        if c is None:
            return
        items = {int(p) for p in polys if 0 <= int(p) < c.poly_count}
        if self.select_mode == "islands" and items:
            grown = set()
            for group in self.islands():
                if items.intersection(group):
                    grown.update(group)
            items = grown
        self.selected_polys = self._combine(self.selected_polys, items, add, remove)
        if self.selected_polys:
            sel = np.zeros(c.poly_count, dtype=bool)
            sel[np.fromiter(self.selected_polys, dtype=np.int64, count=len(self.selected_polys))] = True
            self.selected_corners = set(np.nonzero(sel[c.poly])[0].tolist())
        else:
            self.selected_corners = set()
        self.selectionChanged.emit()

    def select_all(self) -> None:
        c = self.corners()
        if c is None:
            return
        if self.select_mode == "points":
            self.select_corners(range(c.count))
        else:
            self.select_polys(range(c.poly_count))

    def invert_selection(self) -> None:
        c = self.corners()
        if c is None:
            return
        if self.select_mode == "points":
            self.select_corners(set(range(c.count)) - self.selected_corners)
        else:
            self.select_polys(set(range(c.poly_count)) - self.selected_polys)

    def selected_poly_list(self) -> list[int] | None:
        if self.selected_polys:
            return sorted(self.selected_polys)
        if self.selected_corners and self.corners() is not None:
            c = self.corners()
            return sorted({int(c.poly[k]) for k in self.selected_corners})
        return None

    def selected_point_count(self) -> int:
        if not self.selected_corners or self.corners() is None:
            return 0
        groups = self.point_groups()
        idx = np.fromiter(self.selected_corners, dtype=np.int64, count=len(self.selected_corners))
        return int(len(np.unique(groups[idx])))

    def affected(self) -> np.ndarray:
        c = self.corners()
        if c is None:
            return np.zeros(0, dtype=np.int64)
        if not self.selected_corners:
            return np.arange(c.count, dtype=np.int64)
        groups = self.point_groups()
        wanted = np.zeros(int(groups.max()) + 1, dtype=bool)
        wanted[groups[np.fromiter(self.selected_corners, dtype=np.int64, count=len(self.selected_corners))]] = True
        return np.nonzero(wanted[groups])[0]

    def selection_bounds(self) -> tuple[np.ndarray, np.ndarray] | None:
        idx = self.affected()
        if not len(idx):
            return None
        return bounds_uv(self.uv(), idx)

    def run(self, fn: Callable[[np.ndarray, np.ndarray], np.ndarray], message: str = "") -> bool:
        if self.obj is None:
            self.say("No polygon object is active")
            return False
        uv = self.uv()
        idx = self.affected()
        out = fn(uv, idx)
        self.commit(out, message)
        return True

    def move(self, du: float, dv: float, commit: bool = True) -> None:
        self._xf(lambda uv, idx: transform_uv(uv, idx, np.eye(2), offset=(du, dv)), commit)

    def rotate(self, degrees: float, pivot=None, commit: bool = True) -> None:
        from .data import rotate_uv
        self._xf(lambda uv, idx: rotate_uv(uv, idx, degrees, pivot), commit)

    def scale(self, sx: float, sy: float | None = None, pivot=None, commit: bool = True) -> None:
        from .data import scale_uv
        self._xf(lambda uv, idx: scale_uv(uv, idx, sx, sy, pivot), commit)

    def _xf(self, fn, commit: bool) -> None:
        if self.obj is None:
            return
        out = fn(self.uv(), self.affected())
        if commit:
            self.commit(out)
        else:
            self.preview(out, keep_topology=True)

    def flip(self, axis: str) -> bool:
        return self.run(lambda uv, idx: arrange.flip(uv, idx, axis), f"Flipped {axis.upper()}")

    def rotate90(self, clockwise: bool) -> bool:
        return self.run(lambda uv, idx: arrange.rotate90(uv, idx, clockwise),
                        "Rotated 90 degrees " + ("clockwise" if clockwise else "counter-clockwise"))

    def fit(self, keep_aspect: bool = True, margin: float = 0.0) -> bool:
        return self.run(lambda uv, idx: arrange.fit_to_bounds(uv, idx, keep_aspect, margin), "Fitted to 0..1")

    def align_points(self, axis: str) -> bool:
        if not self.selected_corners:
            self.say("Select UV points to align")
            return False
        return self.run(lambda uv, idx: arrange.align_points(uv, idx, axis), f"Aligned {axis.upper()}")

    def straighten(self) -> bool:
        if not self.selected_corners:
            self.say("Select UV points to straighten")
            return False
        return self.run(lambda uv, idx: arrange.straighten(uv, idx), "Straightened")

    def project(self, kind: str, **options) -> bool:
        obj = self.obj
        if obj is None:
            self.say("No polygon object is active")
            return False
        uv = project.project(obj, kind, self.selected_poly_list(), write=False, **options)
        self.commit(uv, f"{kind} projection applied")
        return True

    def uvw_from_tag(self) -> bool:
        obj = self.obj
        if obj is None:
            self.say("No polygon object is active")
            return False
        with self._edit():
            project.uvw_from_tag(obj)
        self._drop_working()
        self.uvChanged.emit()
        self.say("UVW coordinates generated from the tag")
        return True

    def reset(self) -> bool:
        obj = self.obj
        if obj is None:
            return False
        with self._edit():
            reset_uv(obj)
        self._drop_working()
        self.uvChanged.emit()
        self.say("UVs reset to planar")
        return True

    def _seams_changed(self) -> None:
        self._bump()
        self.uvChanged.emit()

    def seams(self) -> set[tuple[int, int]]:
        obj = self.obj
        return get_seams(obj) if obj is not None else set()

    def scene_edges(self) -> list[tuple[int, int]]:
        edges = getattr(self.scene, "selected_edges", set()) or set()
        return [edge_key(a, b) for a, b in edges]

    def uv_selection_edges(self) -> list[tuple[int, int]]:
        c = self.corners()
        if c is None or not self.selected_corners:
            return []
        groups = self.point_groups()
        chosen = np.zeros(int(groups.max()) + 1, dtype=bool)
        chosen[groups[np.fromiter(self.selected_corners, dtype=np.int64, count=len(self.selected_corners))]] = True
        hit = chosen[groups] & chosen[groups[c.next]]
        va, vb = c.vertex, c.vertex[c.next]
        keep = hit & (va != vb)
        lo = np.minimum(va[keep], vb[keep])
        hi = np.maximum(va[keep], vb[keep])
        return sorted({(int(a), int(b)) for a, b in zip(lo.tolist(), hi.tolist())})

    def candidate_edges(self) -> list[tuple[int, int]]:
        edges = self.scene_edges()
        return edges if edges else self.uv_selection_edges()

    def seams_from_selection(self, replace: bool = False) -> int:
        obj = self.obj
        if obj is None:
            self.say("No polygon object is active")
            return 0
        edges = self.candidate_edges()
        with self._edit():
            if replace:
                valid = set(obj.mesh.polygon_edges())
                set_seams(obj, [e for e in edges if e in valid])
                count = len(get_seams(obj))
            else:
                count = add_seams(obj, edges)
        self._seams_changed()
        self.say(f"{len(get_seams(obj))} seam edges")
        return count

    def remove_selected_seams(self) -> int:
        obj = self.obj
        if obj is None:
            return 0
        with self._edit():
            n = remove_seams(obj, self.candidate_edges())
        self._seams_changed()
        self.say(f"Removed {n} seam edges")
        return n

    def clear_seams(self) -> None:
        obj = self.obj
        if obj is None:
            return
        with self._edit():
            clear_seams(obj)
        self._seams_changed()
        self.say("Seams cleared")

    def seams_by_angle(self, angle: float) -> int:
        obj = self.obj
        if obj is None:
            return 0
        found = unwrap.angle_seams(obj.mesh, angle, self.corners())
        with self._edit():
            add_seams(obj, found)
        self._seams_changed()
        self.say(f"{len(get_seams(obj))} seam edges")
        return len(found)

    def seams_from_islands(self) -> int:
        obj = self.obj
        c = self.corners()
        if obj is None or c is None:
            return 0
        islands = self.islands()
        owner = np.zeros(c.poly_count, dtype=np.int64)
        for i, isl in enumerate(islands):
            owner[isl] = i
        a, b = c.edge_pairs()
        cut = owner[c.poly[a]] != owner[c.poly[b]]
        va, vb = c.vertex[a[cut]], c.vertex[c.next[a[cut]]]
        edges = sorted({(int(min(x, y)), int(max(x, y))) for x, y in zip(va.tolist(), vb.tolist())})
        with self._edit():
            set_seams(obj, edges)
        self._seams_changed()
        self.say(f"{len(edges)} seam edges from UV islands")
        return len(edges)

    def unwrap(self, method: str = "Conformal", angle: float | None = None, pack: bool = True,
               margin: float = 0.01, rotate: bool = True) -> dict:
        obj = self.obj
        if obj is None:
            self.say("No polygon object is active")
            return {}
        uv, info = unwrap.unwrap(obj, self.selected_poly_list(), method=method, angle=angle, pack=pack,
                                 margin=margin, rotate=rotate, write=False)
        self.commit(uv, f"Unwrapped {info.get('islands', 0)} islands")
        return info

    def relax(self, method: str = "ARAP", iterations: int = 10, pin_boundary: bool = False,
              pin_selected: bool = False) -> bool:
        obj = self.obj
        if obj is None:
            self.say("No polygon object is active")
            return False
        pins = self.selected_corners if pin_selected else None
        polys = None if pin_selected else self.selected_poly_list()
        self._suspend += 1
        try:
            uv = unwrap.relax(obj, polys, method=method, iterations=iterations, pin_boundary=pin_boundary,
                              pinned_corners=pins, write=False)
        finally:
            self._suspend -= 1
        self.commit(uv, f"Relaxed ({method}, {iterations} iterations)")
        return True

    def pack(self, margin: float = 0.01, rotate: bool = True, equalize: bool = True,
             align: bool = False) -> bool:
        obj = self.obj
        if obj is None:
            self.say("No polygon object is active")
            return False
        uv = arrange.pack_islands(obj.mesh, self.uv(), self.corners(), self.selected_poly_list(),
                                  margin=margin, rotate=rotate, equalize=equalize, align=align)
        self.commit(uv, "Islands packed")
        return True

    def align_islands(self, mode: str = "Auto") -> bool:
        obj = self.obj
        if obj is None:
            return False
        uv = arrange.align_islands(obj.mesh, self.uv(), self.corners(), self.selected_poly_list(), mode)
        self.commit(uv, "Islands aligned")
        return True

    def rectify(self) -> int:
        obj = self.obj
        if obj is None:
            return 0
        uv, n = arrange.rectify(obj.mesh, self.uv(), self.corners(), self.selected_poly_list())
        self.commit(uv, f"Rectified {n} quad islands" if n else "No quad grid island to rectify")
        return n

    def stitch(self, move: str = "smaller") -> int:
        obj = self.obj
        if obj is None:
            return 0
        edges = self.scene_edges()
        if not edges:
            edges = arrange.boundary_edges_of_selection(obj.mesh, self.uv(), self.corners(),
                                                        self.selected_corners)
        if not edges:
            self.say("Select a seam edge to stitch")
            return 0
        uv, welded = arrange.stitch_edges(obj.mesh, self.uv(), edges, self.corners(), move)
        with self._edit():
            self.commit(uv)
            if welded:
                arrange.remove_welded_seams(obj, welded)
        self._seams_changed()
        self.say(f"Stitched {len(welded)} edges")
        return len(welded)

    def stats(self) -> dict:
        obj = self.obj
        if obj is None:
            return {}
        c = self.corners()
        key = (self.uv_revision, id(c), id(obj))
        if self._stats is not None and self._stats[0] == key:
            return dict(self._stats[1])
        out = arrange.uv_stats(obj.mesh, self.uv(), c)
        out["seams"] = len(get_seams(obj))
        self._stats = ((self.uv_revision, id(c), id(obj)), out)
        return dict(out)

    def stretch(self) -> dict:
        obj = self.obj
        if obj is None:
            return {}
        return arrange.polygon_stretch(obj.mesh, self.uv(), self.corners())

    def _channels(self, obj) -> dict:
        found = self._canvases.get(obj)
        if found is None:
            found = {}
            self._canvases[obj] = found
        return found

    def canvas(self, create: bool = True, channel: str | None = None) -> TextureCanvas | None:
        obj = self.obj
        if obj is None:
            return None
        channel = channel or self.channel
        rec = store.get_object(obj, TEXTURES_KEY)
        entry = rec.get(channel) if isinstance(rec, dict) else None
        slots = self._channels(obj)
        cached = slots.get(channel)
        if cached is not None:
            if entry is None and not cached.dirty and not create:
                slots.pop(channel, None)
                return None
            if entry is None or int(entry.get("rev", -1)) == cached.revision or cached.dirty:
                return cached
        loaded = load_canvas(obj, channel)
        if loaded is not None:
            slots[channel] = loaded
            return loaded
        if not create:
            return None
        canvas = TextureCanvas(self.texture_size, self.texture_size, (0.5, 0.5, 0.5, 1.0))
        slots[channel] = canvas
        return canvas

    def cached_canvas_count(self) -> int:
        return sum(len(v) for v in self._canvases.values())

    def has_canvas(self) -> bool:
        return self.canvas(create=False) is not None

    def new_canvas(self, size: int | None = None, fill=(0.5, 0.5, 0.5, 1.0), checker: bool = False,
                   cells: int = 8) -> TextureCanvas | None:
        obj = self.obj
        if obj is None:
            self.say("No polygon object is active")
            return None
        size = int(size or self.texture_size)
        self.texture_size = size
        if checker:
            canvas = TextureCanvas.from_pixels(checker_pixels(size, cells))
        else:
            canvas = TextureCanvas(size, size, fill)
        self._channels(obj)[self.channel] = canvas
        self.commit_texture(canvas)
        self.say(f"New {size} x {size} {self.channel} texture")
        return canvas

    def commit_texture(self, canvas: TextureCanvas | None = None) -> None:
        obj = self.obj
        canvas = canvas or self.canvas(create=False)
        if obj is None or canvas is None:
            return
        with self._edit():
            save_canvas(obj, self.channel, canvas)
        self.textureChanged.emit()

    def set_channel(self, channel: str) -> None:
        if channel != self.channel:
            self.channel = channel
            self.channelChanged.emit(channel)
            self.textureChanged.emit()

    def set_brush(self, **values) -> None:
        changed = False
        for key, value in values.items():
            if not hasattr(self.brush, key):
                raise AttributeError(key)
            if getattr(self.brush, key) != value:
                setattr(self.brush, key, value)
                changed = True
        if changed:
            self.brushChanged.emit()

    def brush_for_tool(self) -> Brush:
        b = self.brush.copy()
        b.mode = "erase" if self.tool == "erase" else "paint"
        return b

    def paint_begin(self, u: float, v: float) -> bool:
        canvas = self.canvas(create=True)
        if canvas is None:
            return False
        if self.tool == "fill":
            canvas.flood_fill(u, v, self.brush.color, self.brush.tolerance, self.brush.opacity)
            self.commit_texture(canvas)
            return True
        canvas.begin_stroke(self.brush_for_tool())
        canvas.stroke_to(u, v)
        self.textureChanged.emit()
        return True

    def paint_move(self, u: float, v: float) -> None:
        canvas = self.canvas(create=False)
        if canvas is not None and canvas.in_stroke():
            canvas.stroke_to(u, v)
            self.textureChanged.emit()

    def paint_end(self) -> None:
        canvas = self.canvas(create=False)
        if canvas is not None and canvas.in_stroke():
            canvas.end_stroke()
            self.commit_texture(canvas)

    def paint_world(self, poly: int, point, continue_stroke: bool = False) -> tuple[float, float] | None:
        from .texture import uv_at_hit
        obj = self.obj
        if obj is None:
            return None
        hit = uv_at_hit(obj, poly, point, uv=self.uv())
        if hit is None:
            return None
        if continue_stroke:
            self.paint_move(*hit)
        else:
            self.paint_begin(*hit)
        return hit

    def paint_ray(self, origin, direction, continue_stroke: bool = False) -> tuple[float, float] | None:
        obj = self.obj
        scene = self.scene
        if obj is None or scene is None or not hasattr(scene, "raycast"):
            return None
        hit = scene.raycast(origin, direction, [obj])
        if hit is None:
            return None
        return self.paint_world(hit[1], hit[2], continue_stroke)

    def fill_canvas(self) -> bool:
        canvas = self.canvas(create=True)
        if canvas is None:
            return False
        if self.tool == "erase":
            canvas.clear()
        else:
            canvas.fill(self.brush.color, self.brush.opacity)
        self.commit_texture(canvas)
        return True

    def save_texture(self, path: str) -> bool:
        canvas = self.canvas(create=False)
        if canvas is None:
            self.say("No texture to save")
            return False
        ok = canvas.save_png(path)
        if ok:
            self.commit_texture(canvas)
            self.say(f"Saved {path}")
        return ok

    def load_texture(self, path: str) -> bool:
        obj = self.obj
        if obj is None:
            return False
        try:
            canvas = TextureCanvas.from_png(path)
        except OSError as exc:
            self.say(str(exc))
            return False
        self._channels(obj)[self.channel] = canvas
        self.commit_texture(canvas)
        self.say(f"Loaded {path}")
        return True

    def tag(self) -> dict:
        obj = self.obj
        return project.get_tag(obj) if obj is not None else dict(project.DEFAULT_TAG)

    def set_tag(self, target=None, **values) -> dict:
        obj = target if target is not None else self.obj
        if obj is None:
            return dict(project.DEFAULT_TAG)
        with self._edit():
            return project.set_tag(obj, **values)

    def grouped(self):
        return self._edit()

    def pick(self, u: float, v: float, radius: float) -> tuple[str, int] | None:
        c = self.corners()
        if c is None:
            return None
        uv = self.uv()
        if self.select_mode == "points":
            d = np.hypot(uv[:, 0] - u, uv[:, 1] - v)
            k = int(np.argmin(d)) if len(d) else -1
            if k >= 0 and d[k] <= radius:
                return ("corner", k)
            return None
        poly = self.poly_at(u, v)
        return ("poly", poly) if poly is not None else None

    def poly_at(self, u: float, v: float) -> int | None:
        c = self.corners()
        if c is None:
            return None
        uv = self.uv()
        from .data import mesh_triangles
        tris, owner = mesh_triangles(self.obj.mesh, c)
        if not len(tris):
            return None
        a, b, d = uv[tris[:, 0]], uv[tris[:, 1]], uv[tris[:, 2]]
        p = np.array([u, v])

        def cross(o, x, q):
            return (x[:, 0] - o[:, 0]) * (q[1] - o[:, 1]) - (x[:, 1] - o[:, 1]) * (q[0] - o[:, 0])

        s1, s2, s3 = cross(a, b, p), cross(b, d, p), cross(d, a, p)
        inside = ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))
        area = np.abs((b[:, 0] - a[:, 0]) * (d[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (d[:, 0] - a[:, 0]))
        inside &= area > 1e-14
        hits = np.nonzero(inside)[0]
        if not len(hits):
            return None
        best = hits[np.argmin(area[hits])]
        return int(owner[best])

    def select_at(self, u: float, v: float, radius: float, add: bool = False, remove: bool = False) -> bool:
        hit = self.pick(u, v, radius)
        if hit is None:
            if not add and not remove:
                self.clear_selection()
            return False
        kind, index = hit
        if kind == "corner":
            groups = self.point_groups()
            members = np.nonzero(groups == groups[index])[0]
            self.select_corners(members.tolist(), add=add, remove=remove)
        else:
            self.select_polys([index], add=add, remove=remove)
        return True

    def select_box(self, u0: float, v0: float, u1: float, v1: float, add: bool = False,
                   remove: bool = False) -> int:
        c = self.corners()
        if c is None:
            return 0
        lo = np.minimum([u0, v0], [u1, v1])
        hi = np.maximum([u0, v0], [u1, v1])
        uv = self.uv()
        inside = np.all((uv >= lo) & (uv <= hi), axis=1)
        if self.select_mode == "points":
            idx = np.nonzero(inside)[0]
            self.select_corners(idx.tolist(), add=add, remove=remove)
            return len(idx)
        per_poly = np.bincount(c.poly, weights=inside.astype(float), minlength=c.poly_count)
        polys = np.nonzero(per_poly >= c.sizes - 0.5)[0]
        self.select_polys(polys.tolist(), add=add, remove=remove)
        return len(polys)

    def frame_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        uv = self.uv()
        if not len(uv):
            return np.zeros(2), np.ones(2)
        idx = self.affected() if self.selected_corners else np.arange(len(uv))
        lo, hi = bounds_uv(uv, idx)
        lo = np.minimum(lo, 0.0) if not self.selected_corners else lo
        hi = np.maximum(hi, 1.0) if not self.selected_corners else hi
        return lo, hi

    def _after_history(self) -> None:
        self._drop_working()
        self._canvases.clear()
        self._remember(self.obj)
        self._prune_selection()
        self.uvChanged.emit()
        self.textureChanged.emit()

    def undo(self) -> bool:
        fn = getattr(self.scene, "undo", None)
        if fn is None:
            return False
        ok = bool(fn())
        self._after_history()
        return ok

    def redo(self) -> bool:
        fn = getattr(self.scene, "redo", None)
        if fn is None:
            return False
        ok = bool(fn())
        self._after_history()
        return ok
