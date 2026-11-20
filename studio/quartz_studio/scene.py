from __future__ import annotations

import copy
import math
from collections import deque
from typing import Iterable

import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication

__all__ = [
    "MODES",
    "EDITABLE_KIND",
    "PEN_TOOLS",
    "TOOLS",
    "Mesh",
    "SceneObject",
    "Scene",
    "get_scene",
    "reset_scene",
    "rotation_matrix",
]


MODES = ("points", "edges", "polygons", "model")

TOOLS = ("select", "move", "rotate", "scale", "pen", "line_pen", "other")
PEN_TOOLS = ("pen", "line_pen")
COMMAND_TOOLS: frozenset = frozenset()

UNDO_LIMIT = 128

EDITABLE_KIND = "polygon"

Edge = tuple[int, int]


def rotation_matrix(rotation_deg: Iterable[float]) -> np.ndarray:
    rx, ry, rz = (math.radians(float(a)) for a in rotation_deg)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], float)
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], float)
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], float)
    return mz @ my @ mx


def _edge_key(a: int, b: int) -> Edge:
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


def _plane_2d(ring: np.ndarray) -> np.ndarray:
    nxt = np.roll(ring, -1, axis=0)
    normal = np.array([
        np.sum((ring[:, 1] - nxt[:, 1]) * (ring[:, 2] + nxt[:, 2])),
        np.sum((ring[:, 2] - nxt[:, 2]) * (ring[:, 0] + nxt[:, 0])),
        np.sum((ring[:, 0] - nxt[:, 0]) * (ring[:, 1] + nxt[:, 1])),
    ])
    drop = int(np.argmax(np.abs(normal)))
    keep = [i for i in range(3) if i != drop]
    flat = ring[:, keep]
    if (drop == 1) != (normal[drop] < 0):
        flat = flat[:, ::-1]
    return flat


def _cross2(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _ear_clip(ring: np.ndarray) -> list[tuple[int, int, int]]:
    flat = _plane_2d(ring)
    idx = list(range(len(flat)))
    tris: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3 and guard < 10 * len(flat):
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = flat[i0], flat[i1], flat[i2]
            if _cross2(a, b, c) <= 1e-12:
                continue
            inside = False
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = flat[j]
                if (_cross2(a, b, p) >= 0 and _cross2(b, c, p) >= 0 and _cross2(c, a, p) >= 0):
                    inside = True
                    break
            if not inside:
                tris.append((i0, i1, i2))
                idx.pop(k)
                break
        else:
            tris.extend((idx[0], idx[m], idx[m + 1]) for m in range(1, len(idx) - 1))
            idx = idx[:3] if len(idx) >= 3 else idx
            return tris
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def _ray_triangle(o: np.ndarray, d: np.ndarray, a: np.ndarray, b: np.ndarray,
                  c: np.ndarray) -> float | None:
    e1, e2 = b - a, c - a
    p = np.cross(d, e2)
    det = float(e1 @ p)
    if abs(det) < 1e-12:
        return None
    inv = 1.0 / det
    s = o - a
    u = float(s @ p) * inv
    if u < -1e-9 or u > 1 + 1e-9:
        return None
    q = np.cross(s, e1)
    v = float(d @ q) * inv
    if v < -1e-9 or u + v > 1 + 1e-9:
        return None
    t = float(e2 @ q) * inv
    return t if t > 1e-9 else None


def _merge_into_quads(ring: np.ndarray, tris: list[tuple[int, int, int]]) -> list[tuple[int, int]]:
    n = len(ring)
    flat = _plane_2d(ring)

    def is_boundary(a: int, b: int) -> bool:
        return (a - b) % n in (1, n - 1)

    diag_tris: dict[tuple[int, int], list[int]] = {}
    for t, tri in enumerate(tris):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            if not is_boundary(a, b):
                diag_tris.setdefault((min(a, b), max(a, b)), []).append(t)
    used: set[int] = set()
    remaining: list[tuple[int, int]] = []
    for diag, owners in diag_tris.items():
        if len(owners) != 2 or owners[0] in used or owners[1] in used:
            remaining.append(diag)
            continue
        quad_pts = set(tris[owners[0]]) | set(tris[owners[1]])
        a, b = diag
        others = [p for p in quad_pts if p not in diag]
        if len(others) != 2:
            remaining.append(diag)
            continue
        ring4 = [a, others[0], b, others[1]]
        signs = [_cross2(flat[ring4[i - 1]], flat[ring4[i]], flat[ring4[(i + 1) % 4]]) for i in range(4)]
        if all(s > 1e-9 for s in signs) or all(s < -1e-9 for s in signs):
            used.update(owners)
        else:
            remaining.append(diag)
    return remaining


def _clean_scales(values: Iterable | None, count: int) -> np.ndarray | None:
    if values is None:
        return None
    arr = np.array(values, dtype=float).reshape(-1)
    if len(arr) != count:
        raise ValueError(f"point_scales has {len(arr)} values for {count} points")
    arr[~np.isfinite(arr)] = 1.0
    np.maximum(arr, 0.0, out=arr)
    return None if bool(np.all(arr == 1.0)) else arr


class Mesh:

    def __init__(self, points: Iterable, polygons: Iterable[Iterable[int]],
                 loose_edges: Iterable[Iterable[int]] = (), *, point_scales: Iterable | None = None) -> None:
        self.points = np.array(points, dtype=float).reshape(-1, 3)
        self.polygons: list[tuple[int, ...]] = [tuple(int(i) for i in poly) for poly in polygons]
        self.loose_edges: list[Edge] = [_edge_key(e[0], e[1]) for e in loose_edges]
        self.edges: list[Edge] = []
        self._point_scales: np.ndarray | None = None
        self._scales_count = -1
        self._rebuild_edges()
        if point_scales is not None:
            values = np.asarray(point_scales, float).reshape(-1)
            if len(values) == len(self.points):
                self.point_scales = values

    @property
    def point_scales(self) -> np.ndarray | None:
        if self._scales_count != len(self.points):
            self._point_scales = None
            self._scales_count = -1
        return self._point_scales

    @point_scales.setter
    def point_scales(self, values: Iterable | None) -> None:
        self._point_scales = _clean_scales(values, len(self.points))
        self._scales_count = len(self.points)

    @property
    def point_scales_explicit(self) -> bool:
        return self.point_scales is not None or self._scales_count == len(self.points)

    def point_scale_array(self) -> np.ndarray:
        values = self.point_scales
        return np.ones(len(self.points)) if values is None else values.copy()

    @classmethod
    def cube(cls, size: float = 200.0) -> "Mesh":
        h = size / 2.0
        points = [
            (-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h),
            (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h),
        ]
        polygons = [
            (0, 3, 2, 1),
            (4, 5, 6, 7),
            (0, 4, 7, 3),
            (1, 2, 6, 5),
            (3, 7, 6, 2),
            (0, 1, 5, 4),
        ]
        return cls(points, polygons)

    def polygon_edges(self) -> list[Edge]:
        seen: set[Edge] = set()
        out: list[Edge] = []
        for poly in self.polygons:
            for a, b in zip(poly, poly[1:] + poly[:1]):
                key = _edge_key(a, b)
                if key not in seen:
                    seen.add(key)
                    out.append(key)
        return out

    def _rebuild_edges(self) -> None:
        poly_edges = self.polygon_edges()
        covered = set(poly_edges)
        loose: list[Edge] = []
        for e in self.loose_edges:
            if e not in covered and e not in loose and e[0] != e[1]:
                loose.append(e)
        self.loose_edges = loose
        self.edges = poly_edges + loose

    def add_point(self, local: Iterable[float]) -> int:
        scales = self.point_scales
        explicit = self._scales_count == len(self.points)
        self.points = np.vstack([self.points, np.asarray(local, float).reshape(1, 3)])
        if explicit:
            self._point_scales = None if scales is None else np.append(scales, 1.0)
            self._scales_count = len(self.points)
        return len(self.points) - 1

    def add_loose_edge(self, a: int, b: int) -> Edge:
        key = _edge_key(a, b)
        if key not in self.edges:
            self.loose_edges.append(key)
            self._rebuild_edges()
        return key

    def add_polygon(self, indices: Iterable[int]) -> int:
        self.polygons.append(tuple(int(i) for i in indices))
        self._rebuild_edges()
        return len(self.polygons) - 1

    def set_polygon(self, index: int, indices: Iterable[int]) -> None:
        self.polygons[index] = tuple(int(i) for i in indices)
        self._rebuild_edges()

    def directed_edge_owner(self, a: int, b: int) -> int | None:
        for k, poly in enumerate(self.polygons):
            for u, v in zip(poly, poly[1:] + poly[:1]):
                if u == a and v == b:
                    return k
        return None

    def ngon_guides(self, index: int, points: np.ndarray | None = None) -> list[Edge]:
        poly = self.polygons[index]
        if len(poly) <= 4:
            return []
        pts = self.points if points is None else np.asarray(points, float)
        tris = _ear_clip(pts[list(poly)])
        return [(poly[a], poly[b]) for a, b in _merge_into_quads(pts[list(poly)], tris)]

    def polygon_normals(self, points: np.ndarray | None = None) -> np.ndarray:
        pts = self.points if points is None else np.asarray(points, float)
        out = np.zeros((len(self.polygons), 3))
        groups: dict[int, list[int]] = {}
        for k, poly in enumerate(self.polygons):
            groups.setdefault(len(poly), []).append(k)
        for size, ks in groups.items():
            if size == 0:
                continue
            idx = np.array([self.polygons[k] for k in ks], int).reshape(len(ks), size)
            ring = pts[idx]
            nxt = np.roll(ring, -1, axis=1)
            n = np.stack([
                np.sum((ring[:, :, 1] - nxt[:, :, 1]) * (ring[:, :, 2] + nxt[:, :, 2]), axis=1),
                np.sum((ring[:, :, 2] - nxt[:, :, 2]) * (ring[:, :, 0] + nxt[:, :, 0]), axis=1),
                np.sum((ring[:, :, 0] - nxt[:, :, 0]) * (ring[:, :, 1] + nxt[:, :, 1]), axis=1),
            ], axis=1)
            length = np.linalg.norm(n, axis=1)
            ok = length > 1e-12
            n[ok] = n[ok] / length[ok][:, None]
            out[ks] = n
        return out

    @classmethod
    def empty(cls) -> "Mesh":
        return cls(np.zeros((0, 3)), [])

    def has_faces(self) -> bool:
        return bool(self.polygons)

    def point_valence(self, index: int) -> int:
        return sum(1 for a, b in self.edges if index in (a, b))

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if not len(self.points):
            return np.zeros(3), np.zeros(3)
        return self.points.min(axis=0), self.points.max(axis=0)

    def size(self) -> np.ndarray:
        lo, hi = self.bounds()
        return hi - lo


def _euler_xyz(m: np.ndarray) -> np.ndarray:
    def wrap(a: float) -> float:
        return (a + math.pi) % (2.0 * math.pi) - math.pi

    xy = math.hypot(m[0, 0], m[1, 0])
    b = math.atan2(-m[2, 0], xy)
    if xy > 1e-9:
        a = math.atan2(m[2, 1], m[2, 2])
        c = math.atan2(m[1, 0], m[0, 0])
    else:
        a = 0.0
        c = math.atan2(-m[0, 1], m[1, 1])
    first = (wrap(a), b, wrap(c))
    second = (wrap(a + math.pi), wrap(math.pi - b), wrap(c + math.pi))
    best = min((first, second), key=lambda t: sum(abs(v) for v in t))
    return np.degrees(np.array(best, float))


def _snap(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, float).copy()
    v[np.abs(v) < 1e-9] = 0.0
    return v


def _same_json(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same_json(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_same_json(x, y) for x, y in zip(a, b))
    try:
        return bool(a == b)
    except Exception:
        return False


def _copy_mesh(mesh: Mesh) -> Mesh:
    return Mesh(mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges),
                point_scales=mesh.point_scales)


class SceneObject:

    def __init__(self, name: str, mesh: Mesh, kind: str = "polygon", params: dict | None = None) -> None:
        self.name = name
        self.mesh = mesh
        self.kind = kind
        self.params: dict = dict(params or {})
        self.parent: SceneObject | None = None
        self.enabled = True
        self.error = ""
        self.position = np.zeros(3)
        self.rotation = np.zeros(3)
        self.scale = np.ones(3)
        self.extras: dict = {}
        self._dirty = kind != "polygon"
        self._sig = None
        self._version = 0

    def linear(self) -> np.ndarray:
        return rotation_matrix(self.rotation) @ np.diag(self.scale)

    def local_matrix(self) -> np.ndarray:
        m = np.eye(4)
        m[:3, :3] = self.linear()
        m[:3, 3] = self.position
        return m

    def parent_matrix(self) -> np.ndarray:
        return self.parent.world_matrix() if self.parent is not None else np.eye(4)

    def world_matrix(self) -> np.ndarray:
        m = self.local_matrix()
        p = self.parent
        while p is not None:
            m = p.local_matrix() @ m
            p = p.parent
        return m

    def world_linear(self) -> np.ndarray:
        if self.parent is None:
            return self.linear()
        return self.world_matrix()[:3, :3]

    def world_position(self) -> np.ndarray:
        if self.parent is None:
            return self.position.copy()
        return self.world_matrix()[:3, 3].copy()

    def to_world(self, local_points: np.ndarray) -> np.ndarray:
        pts = np.atleast_2d(np.asarray(local_points, float))
        if self.parent is None:
            return pts @ self.linear().T + self.position
        m = self.world_matrix()
        return pts @ m[:3, :3].T + m[:3, 3]

    def world_points(self) -> np.ndarray:
        return self.to_world(self.mesh.points)

    def to_local_vector(self, world_vector: Iterable[float]) -> np.ndarray:
        return np.linalg.solve(self.world_linear(), np.asarray(world_vector, float))

    def to_local_point(self, world_point: Iterable[float]) -> np.ndarray:
        return self.to_local_vector(np.asarray(world_point, float) - self.world_position())

    def size(self) -> np.ndarray:
        if self.parent is None:
            return self.mesh.size() * np.abs(self.scale)
        return self.mesh.size() * np.linalg.norm(self.world_linear(), axis=0)


class Scene(QObject):

    changed = Signal()
    selectionChanged = Signal()
    modeChanged = Signal(str)
    toolChanged = Signal(str)
    objectsChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.objects: list[SceneObject] = [SceneObject("Cube", Mesh.cube(200.0))]
        self.active: SceneObject | None = self.objects[0]
        self.object_selected = True
        self.extra_selected: list[SceneObject] = []
        self.mode = "model"
        self.tool = "move"
        self.selected_points: set[int] = set()
        self.selected_edges: set[Edge] = set()
        self.selected_polygons: set[int] = set()
        self.pen_chain: list[int] = []
        self.pen_polygon: int | None = None
        self.extras: dict = {}
        self._undo: deque[dict] = deque(maxlen=UNDO_LIMIT)
        self._redo: list[dict] = []
        self._group_depth = 0
        self._group_recorded = False
        self._last_kind = ""
        self._release_watch = False
        self._release_timer = QTimer(self)
        self._release_timer.setInterval(30)
        self._release_timer.timeout.connect(self._poll_release)
        self.changed.connect(self._on_changed)

    def _on_changed(self) -> None:
        self.evaluate()

    def begin_group(self) -> None:
        if self._group_depth == 0:
            self._group_recorded = False
        self._group_depth += 1

    def end_group(self) -> None:
        self._group_depth = max(0, self._group_depth - 1)

    def _record(self, kind: str) -> None:
        if self._group_depth and self._group_recorded:
            return
        dragging = QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton
        coalesce = kind == "move" or kind.startswith(("param:", "scales:"))
        if coalesce and kind == self._last_kind and dragging and not self._group_depth:
            return
        self._undo.append(self._snapshot())
        self._redo.clear()
        self._last_kind = kind if dragging and coalesce else ""
        if self._last_kind:
            self._watch_release(True)
        else:
            self._watch_release(False)
        if self._group_depth:
            self._group_recorded = True

    def _watch_release(self, on: bool) -> None:
        if on == self._release_watch:
            return
        self._release_watch = on
        app = QCoreApplication.instance()
        if on:
            if app is not None:
                app.installEventFilter(self)
            self._release_timer.start()
        else:
            if app is not None:
                app.removeEventFilter(self)
            self._release_timer.stop()

    def _end_drag(self) -> None:
        self._last_kind = ""
        self._watch_release(False)

    def _poll_release(self) -> None:
        if QGuiApplication.mouseButtons() == Qt.MouseButton.NoButton:
            self._end_drag()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease and self._release_watch:
            QTimer.singleShot(0, self._end_drag)
        return False

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        return True

    def _snapshot(self) -> dict:
        objs = []
        index = {id(o): i for i, o in enumerate(self.objects)}
        for o in self.objects:
            m = o.mesh
            objs.append({
                "name": o.name, "kind": o.kind, "params": dict(o.params),
                "parent": index.get(id(o.parent), -1) if o.parent is not None else -1,
                "enabled": o.enabled, "error": o.error,
                "points": m.points.copy(), "polygons": list(m.polygons),
                "loose": list(m.loose_edges),
                "scales": None if m.point_scales is None else m.point_scales.copy(),
                "position": o.position.copy(), "rotation": o.rotation.copy(),
                "scale": o.scale.copy(), "extras": copy.deepcopy(o.extras),
            })
        active = self.objects.index(self.active) if self.active in self.objects else -1
        return {
            "objects": objs, "active": active, "object_selected": self.object_selected,
            "extra": [index[id(o)] for o in self.extra_selected if id(o) in index],
            "points": set(self.selected_points), "edges": set(self.selected_edges),
            "polygons": set(self.selected_polygons),
            "pen_chain": list(self.pen_chain), "pen_polygon": self.pen_polygon,
            "extras": copy.deepcopy(self.extras),
        }

    def _restore(self, snap: dict) -> None:
        self.objects = []
        for rec in snap["objects"]:
            obj = SceneObject(rec["name"], Mesh(rec["points"].copy(), rec["polygons"], rec["loose"],
                                                point_scales=rec.get("scales")),
                              rec["kind"], rec["params"])
            obj.position = rec["position"].copy()
            obj.rotation = rec["rotation"].copy()
            obj.scale = rec["scale"].copy()
            p = rec["parent"]
            obj.parent = self.objects[p] if 0 <= p < len(self.objects) else None
            obj.enabled = rec["enabled"]
            obj.error = rec["error"]
            obj.extras = copy.deepcopy(rec.get("extras", {}))
            obj._dirty = False
            self.objects.append(obj)
        self._mark_clean()
        i = snap["active"]
        self.active = self.objects[i] if 0 <= i < len(self.objects) else None
        self.object_selected = snap["object_selected"]
        self.extra_selected = [self.objects[k] for k in snap.get("extra", ())
                               if 0 <= k < len(self.objects) and k != i]
        self.selected_points = set(snap["points"])
        self.selected_edges = set(snap["edges"])
        self.selected_polygons = set(snap["polygons"])
        self.pen_chain = list(snap["pen_chain"])
        self.pen_polygon = snap["pen_polygon"]
        self.extras = copy.deepcopy(snap.get("extras", {}))
        self._end_drag()
        self.objectsChanged.emit()
        self.changed.emit()
        self.selectionChanged.emit()

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        if mode != self.mode:
            self.mode = mode
            self.modeChanged.emit(mode)
            self.selectionChanged.emit()

    def set_tool(self, tool: str) -> None:
        if tool not in TOOLS:
            tool = "other"
        if tool != self.tool:
            if self.tool in PEN_TOOLS:
                self.pen_finish()
            self.tool = tool
            self.toolChanged.emit(tool)
        if tool in PEN_TOOLS and self.mode == "model":
            self.set_mode("points")

    def add_object(self, name: str, mesh: Mesh | None = None, *, activate: bool = True) -> SceneObject:
        self._record("objects")
        obj = SceneObject(self._unique_name(name), mesh if mesh is not None else Mesh.empty())
        self.objects.append(obj)
        self.objectsChanged.emit()
        if activate:
            self.set_active(obj)
        self.changed.emit()
        return obj

    def new_line_object(self) -> SceneObject:
        return self.add_object("Line")

    def set_active(self, obj: SceneObject | None, *, select: bool = True) -> None:
        if obj is not None and obj not in self.objects:
            raise ValueError("object is not in the scene")
        if obj is self.active:
            flag = select and obj is not None
            if self.extra_selected:
                self.extra_selected = []
                if flag == self.object_selected:
                    self.selectionChanged.emit()
            self.select_object(flag)
            return
        self.pen_finish()
        self.active = obj
        self.extra_selected = []
        self.selected_points.clear()
        self.selected_edges.clear()
        self.selected_polygons.clear()
        self.object_selected = select and obj is not None
        self.selectionChanged.emit()
        if self.object_selected:
            self._default_tool()

    def _default_tool(self) -> None:
        if self.tool == "other" or self.tool in COMMAND_TOOLS:
            self.set_tool("move")

    def remove_object(self, obj: SceneObject) -> None:
        if obj not in self.objects:
            return
        self._record("objects")
        index = self.objects.index(obj)
        gone = {id(obj)} | {id(o) for o in self.descendants(obj)}
        self.objects = [o for o in self.objects if id(o) not in gone]
        self.extra_selected = [o for o in self.extra_selected if id(o) not in gone]
        self.objectsChanged.emit()
        if self.active is not None and id(self.active) in gone:
            nxt = self.objects[min(index, len(self.objects) - 1)] if self.objects else None
            self.set_active(nxt, select=False)
        self.evaluate()
        self.changed.emit()

    def set_object_extra(self, obj: SceneObject, key: str, value) -> bool:
        if obj not in self.objects:
            raise ValueError("object is not in the scene")
        return self._set_extra_in(obj.extras, key, value, "extras:object")

    def set_extra(self, key: str, value) -> bool:
        return self._set_extra_in(self.extras, key, value, "extras:scene")

    def _set_extra_in(self, target: dict, key: str, value, kind: str) -> bool:
        if not isinstance(key, str):
            raise TypeError("extra keys must be text")
        if value is None:
            if key not in target:
                return False
        elif key in target and _same_json(target[key], value):
            return False
        self._record(kind)
        if value is None:
            del target[key]
        else:
            target[key] = copy.deepcopy(value)
        self.changed.emit()
        return True

    def clear_history(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._end_drag()

    def insert_objects(self, objs: Iterable[SceneObject], parents: Iterable[int | None],
                       activate: bool = True, replace: bool = False) -> list[SceneObject]:
        objs = list(objs)
        parents = list(parents)
        if len(parents) != len(objs):
            raise ValueError("parents and objects differ in length")
        for i, p in enumerate(parents):
            if p is None:
                continue
            if not 0 <= p < len(objs) or p == i:
                raise ValueError(f"invalid parent index {p!r}")
            seen = {i}
            j: int | None = p
            while j is not None:
                if j in seen:
                    raise ValueError("hierarchy has a cycle")
                seen.add(j)
                j = parents[j]
        if replace:
            self.objects = []
            self.active = None
            self.object_selected = False
            self.extra_selected = []
            self.selected_points.clear()
            self.selected_edges.clear()
            self.selected_polygons.clear()
            self.pen_chain = []
            self.pen_polygon = None
            self.extras = {}
        elif objs:
            self._record("objects")
        for o in objs:
            o.parent = None
            o.name = self._unique_name(o.name.strip() or "Object")
            self.objects.append(o)
        for o, p in zip(objs, parents):
            o.parent = objs[p] if p is not None else None
        self.objects = self._order(self._children_map())
        self.evaluate()
        self.objectsChanged.emit()
        if activate:
            self.set_active(objs[0] if objs else None)
        self.changed.emit()
        if replace:
            self.clear_history()
            self.selectionChanged.emit()
        return objs

    def _children_map(self) -> dict:
        kids: dict = {None: []}
        for o in self.objects:
            kids.setdefault(o, [])
            kids.setdefault(o.parent, []).append(o)
        return kids

    @staticmethod
    def _order(kids: dict) -> list[SceneObject]:
        out: list[SceneObject] = []

        def visit(o: SceneObject) -> None:
            out.append(o)
            for c in kids.get(o, ()):
                visit(c)

        for r in kids.get(None, ()):
            visit(r)
        return out

    def children(self, obj: SceneObject | None) -> list[SceneObject]:
        return [o for o in self.objects if o.parent is obj]

    def roots(self) -> list[SceneObject]:
        return self.children(None)

    def descendants(self, obj: SceneObject) -> list[SceneObject]:
        kids = self._children_map()
        out: list[SceneObject] = []

        def visit(o: SceneObject) -> None:
            for c in kids.get(o, ()):
                out.append(c)
                visit(c)

        visit(obj)
        return out

    @staticmethod
    def _spec(kind: str):
        if kind == EDITABLE_KIND:
            return None
        from .objects import registry
        return registry.SPECS.get(kind)

    def _consumes(self, obj: SceneObject) -> bool:
        if obj.kind == EDITABLE_KIND:
            return False
        spec = self._spec(obj.kind)
        return spec is not None and spec.inputs == "children"

    def is_editable(self, obj: SceneObject | None) -> bool:
        return obj is not None and obj.kind == EDITABLE_KIND

    def render_objects(self) -> list[SceneObject]:
        if all(o.parent is None and o.enabled and o.kind == EDITABLE_KIND for o in self.objects):
            return list(self.objects)
        kids = self._children_map()
        out: list[SceneObject] = []

        def visit(o: SceneObject) -> None:
            if not o.enabled:
                return
            out.append(o)
            if self._consumes(o):
                return
            for c in kids.get(o, ()):
                visit(c)

        for r in kids.get(None, ()):
            visit(r)
        return out

    def _flatten(self, root: SceneObject, kids: dict) -> list[tuple[SceneObject, np.ndarray]]:
        out: list[tuple[SceneObject, np.ndarray]] = []

        def visit(o: SceneObject, parent_m: np.ndarray) -> None:
            if not o.enabled:
                return
            m = parent_m @ o.local_matrix()
            out.append((o, m))
            if self._consumes(o):
                return
            for c in kids.get(o, ()):
                visit(c, m)

        visit(root, np.eye(4))
        return out

    @staticmethod
    def _mesh_sig(o: SceneObject):
        if o.kind != EDITABLE_KIND:
            return ("v", o._version)
        m = o.mesh
        scales = m.point_scales
        return hash((m.points.tobytes(), tuple(m.polygons), tuple(m.loose_edges),
                     None if scales is None else scales.tobytes()))

    def _input_flats(self, obj: SceneObject, kids: dict) -> list:
        return [self._flatten(c, kids) for c in kids.get(obj, ()) if c.enabled]

    def _signature(self, flats: list) -> tuple:
        return tuple(tuple((id(o), o.kind, m.tobytes(), self._mesh_sig(o)) for o, m in flat)
                     for flat in flats)

    @staticmethod
    def _make_input(flat: list):
        from .objects.registry import BuildInput
        pts: list[np.ndarray] = []
        polys: list[tuple[int, ...]] = []
        loose: list[Edge] = []
        scales: list[np.ndarray] = []
        scaled = False
        offset = 0
        for o, m in flat:
            mp = o.mesh.points
            own = o.mesh.point_scales
            scaled = scaled or own is not None
            scales.append(np.ones(len(mp)) if own is None else own)
            if len(mp):
                pts.append(mp @ m[:3, :3].T + m[:3, 3])
            flip = float(np.linalg.det(m[:3, :3])) < 0.0
            if flip:
                polys.extend(tuple(i + offset for i in reversed(p)) for p in o.mesh.polygons)
            else:
                polys.extend(tuple(i + offset for i in p) for p in o.mesh.polygons)
            loose.extend((a + offset, b + offset) for a, b in o.mesh.loose_edges)
            offset += len(mp)
        mesh = Mesh(np.vstack(pts) if pts else np.zeros((0, 3)), polys, loose,
                    point_scales=np.concatenate(scales) if scaled else None)
        root, matrix = flat[0]
        return BuildInput(mesh, root.name, root.kind, obj=root, matrix=matrix.copy())

    def _build(self, obj: SceneObject, spec, inputs: list) -> None:
        try:
            values = spec.defaults()
            values.update(obj.params)
            mesh = spec.build(values, inputs)
            if not isinstance(mesh, Mesh):
                raise TypeError(f"build returned {type(mesh).__name__}, not a Mesh")
            obj.mesh = mesh
            obj.error = ""
        except Exception as exc:
            obj.mesh = Mesh.empty()
            obj.error = f"{type(exc).__name__}: {exc}"
        obj._version += 1

    def evaluate(self) -> bool:
        if all(o.kind == EDITABLE_KIND for o in self.objects):
            return False
        kids = self._children_map()
        rebuilt = False
        for obj in reversed(self.objects):
            if obj.kind == EDITABLE_KIND:
                continue
            spec = self._spec(obj.kind)
            if spec is None:
                message = f"unknown object type {obj.kind!r}"
                if obj.error != message:
                    obj.mesh = Mesh.empty()
                    obj.error = message
                    obj._version += 1
                    rebuilt = True
                obj._dirty = False
                continue
            flats = self._input_flats(obj, kids) if spec.inputs == "children" else []
            sig = self._signature(flats)
            if not obj._dirty and sig == obj._sig:
                continue
            self._build(obj, spec, [self._make_input(f) for f in flats])
            obj._sig = sig
            obj._dirty = False
            rebuilt = True
        return rebuilt

    def _mark_clean(self) -> None:
        if all(o.kind == EDITABLE_KIND for o in self.objects):
            return
        kids = self._children_map()
        for obj in reversed(self.objects):
            if obj.kind == EDITABLE_KIND:
                continue
            spec = self._spec(obj.kind)
            flats = self._input_flats(obj, kids) if spec is not None and spec.inputs == "children" else []
            obj._sig = self._signature(flats)
            obj._dirty = False

    def _place(self, obj: SceneObject, parent: SceneObject | None, index: int | None = None) -> None:
        kids = self._children_map()
        if obj in kids.get(obj.parent, []):
            kids[obj.parent].remove(obj)
        kids.setdefault(obj, [])
        siblings = kids.setdefault(parent, [])
        if index is None or index >= len(siblings):
            siblings.append(obj)
        else:
            siblings.insert(max(0, int(index)), obj)
        obj.parent = parent
        self.objects = self._order(kids)

    @staticmethod
    def _set_world(obj: SceneObject, world: np.ndarray, old_parent_world: np.ndarray) -> None:
        parent_world = obj.parent_matrix()
        if np.array_equal(parent_world, old_parent_world):
            return
        local = np.linalg.solve(parent_world, world)
        lin = local[:3, :3]
        scale = np.linalg.norm(lin, axis=0)
        if np.linalg.det(lin) < 0:
            scale[0] = -scale[0]
        safe = np.where(np.abs(scale) > 1e-12, scale, 1.0)
        obj.position = _snap(local[:3, 3])
        obj.rotation = _snap(_euler_xyz(lin / safe))
        obj.scale = scale.astype(float)

    def add_parametric(self, kind: str, name: str | None = None, parent: SceneObject | None = None,
                       adopt: SceneObject | None = None, activate: bool = True) -> SceneObject:
        from .objects import registry
        spec = registry.get(kind)
        if parent is not None and parent not in self.objects:
            raise ValueError("parent is not in the scene")
        if adopt is not None and adopt not in self.objects:
            raise ValueError("adopted object is not in the scene")
        self._record("objects")
        obj = SceneObject(self._unique_name(name or spec.label), Mesh.empty(), spec.id, spec.defaults())
        if adopt is not None and parent is None:
            siblings = self.children(adopt.parent)
            self._place(obj, adopt.parent, siblings.index(adopt))
        else:
            self._place(obj, parent)
        if adopt is not None:
            world, old = adopt.world_matrix(), adopt.parent_matrix()
            self._place(adopt, obj, 0)
            self._set_world(adopt, world, old)
        self.evaluate()
        self.objectsChanged.emit()
        if activate:
            self.set_active(obj)
        self.changed.emit()
        return obj

    def set_param(self, obj: SceneObject, key: str, value) -> bool:
        spec = self._spec(obj.kind)
        if spec is None:
            raise ValueError(f"{obj.name!r} has no parameters")
        param = spec.param(key)
        if param is None:
            raise KeyError(f"{obj.kind!r} has no parameter {key!r}")
        v = param.clamp(value)
        if key in obj.params and obj.params[key] == v and type(obj.params[key]) is type(v):
            return False
        self._record(f"param:{id(obj)}:{key}")
        obj.params[key] = v
        obj._dirty = True
        self.evaluate()
        self.changed.emit()
        return True

    def set_parent(self, obj: SceneObject, parent: SceneObject | None, index: int | None = None) -> bool:
        if obj not in self.objects:
            return False
        if parent is not None and (parent not in self.objects or parent is obj
                                   or any(d is parent for d in self.descendants(obj))):
            return False
        siblings = [o for o in self.children(parent) if o is not obj]
        pos = len(siblings) if index is None or index >= len(siblings) else max(0, int(index))
        if parent is obj.parent and self.children(parent).index(obj) == pos:
            return False
        world, old = obj.world_matrix(), obj.parent_matrix()
        self._record("hierarchy")
        self._place(obj, parent, pos)
        self._set_world(obj, world, old)
        self.evaluate()
        self.objectsChanged.emit()
        self.changed.emit()
        return True

    def set_enabled(self, obj: SceneObject, flag: bool) -> None:
        flag = bool(flag)
        if obj not in self.objects or obj.enabled == flag:
            return
        self._record("enabled")
        obj.enabled = flag
        self.evaluate()
        self.objectsChanged.emit()
        self.changed.emit()

    def selected_objects(self) -> list[SceneObject]:
        active = self.active
        if active is None or not self.object_selected or active not in self.objects:
            return []
        if not self.extra_selected:
            return [active]
        ids = {id(active)} | {id(o) for o in self.extra_selected}
        return [o for o in self.objects if id(o) in ids]

    def is_object_selected(self, obj: SceneObject | None) -> bool:
        return obj is not None and any(o is obj for o in self.selected_objects())

    def select_objects(self, objs: Iterable[SceneObject], op: str = "replace",
                       active: SceneObject | None = None) -> bool:
        if op not in ("replace", "add", "remove", "toggle"):
            raise ValueError(f"unknown selection operation {op!r}")
        live = {id(o) for o in self.objects}
        given: list[SceneObject] = []
        for o in objs:
            if o is not None and id(o) in live and all(o is not g for g in given):
                given.append(o)
        current = self.selected_objects()
        held = {id(o) for o in current}
        hit = {id(o) for o in given}
        if op == "replace":
            new = given
        elif op == "add":
            new = current + [o for o in given if id(o) not in held]
        elif op == "remove":
            new = [o for o in current if id(o) not in hit]
        else:
            new = [o for o in current if id(o) not in hit] + [o for o in given if id(o) not in held]
        keep = {id(o) for o in new}
        if active is not None and id(active) in keep:
            head = active
        elif self.active is not None and id(self.active) in keep:
            head = self.active
        else:
            head = new[-1] if new else None
        return self._set_object_selection(head, new)

    def _set_object_selection(self, head: SceneObject | None, objs: list[SceneObject]) -> bool:
        if head is None:
            if not self.object_selected and not self.extra_selected:
                return False
            self.object_selected = False
            self.extra_selected = []
            self.selectionChanged.emit()
            return True
        extra = [o for o in objs if o is not head]
        if (head is self.active and self.object_selected
                and {id(o) for o in extra} == {id(o) for o in self.extra_selected}):
            self._default_tool()
            return False
        if head is not self.active:
            self.pen_finish()
            self.active = head
            self.selected_points.clear()
            self.selected_edges.clear()
            self.selected_polygons.clear()
        self.object_selected = True
        self.extra_selected = extra
        self.selectionChanged.emit()
        self._default_tool()
        return True

    def select_all_objects(self) -> bool:
        if not self.objects or len(self.selected_objects()) == len(self.objects):
            return False
        self._record("selection")
        return self.select_objects(self.objects, "replace", active=self.active)

    def transform_roots(self, objs: Iterable[SceneObject] | None = None) -> list[SceneObject]:
        chosen = self.selected_objects() if objs is None else [o for o in objs if o in self.objects]
        ids = {id(o) for o in chosen}

        def nested(o: SceneObject) -> bool:
            p = o.parent
            while p is not None:
                if id(p) in ids:
                    return True
                p = p.parent
            return False

        return [o for o in chosen if not nested(o)]

    def duplicate_objects(self, objs: Iterable[SceneObject] | None = None) -> list[SceneObject]:
        roots = self.transform_roots(objs)
        if not roots:
            return []
        self._record("duplicate")
        made: dict[int, SceneObject] = {}
        for root in roots:
            for o in [root] + self.descendants(root):
                c = SceneObject(self._unique_name(o.name), _copy_mesh(o.mesh), o.kind, copy.deepcopy(o.params))
                c.position, c.rotation, c.scale = o.position.copy(), o.rotation.copy(), o.scale.copy()
                c.enabled = o.enabled
                c.error = o.error
                c.extras = copy.deepcopy(o.extras)
                c.parent = root.parent if o is root else made[id(o.parent)]
                made[id(o)] = c
                self.objects.append(c)
        self.objects = self._order(self._children_map())
        self.evaluate()
        self.objectsChanged.emit()
        self.changed.emit()
        tops = [made[id(r)] for r in roots]
        head = made.get(id(self.active)) if self.active is not None else None
        self.select_objects(tops, "replace", active=head if any(head is t for t in tops) else tops[0])
        return list(made.values())

    def set_transforms(self, items: Iterable, kind: str = "transform") -> bool:
        todo = []
        for obj, pos, rot, scale in items:
            if obj not in self.objects:
                continue
            vals = [None if v is None else np.asarray(v, float).copy() for v in (pos, rot, scale)]
            olds = (obj.position, obj.rotation, obj.scale)
            if any(v is not None and not np.allclose(v, old, rtol=0.0, atol=1e-9) for v, old in zip(vals, olds)):
                todo.append((obj, vals))
        if not todo:
            return False
        self._record(kind)
        for obj, (pos, rot, scale) in todo:
            if pos is not None:
                obj.position = pos
            if rot is not None:
                obj.rotation = rot
            if scale is not None:
                obj.scale = scale
        self.changed.emit()
        return True

    def group_objects(self, objs: Iterable[SceneObject] | None = None) -> SceneObject | None:
        chosen = [o for o in (self.selected_objects() if objs is None else objs) if o in self.objects]
        ids = {id(o) for o in chosen}

        def nested(o: SceneObject) -> bool:
            p = o.parent
            while p is not None:
                if id(p) in ids:
                    return True
                p = p.parent
            return False

        chosen = sorted((o for o in chosen if not nested(o)), key=self.objects.index)
        if not chosen:
            return None
        self.begin_group()
        try:
            null = self.add_parametric("null", adopt=chosen[0])
            for o in chosen[1:]:
                self.set_parent(o, null)
        finally:
            self.end_group()
        return null

    def make_editable(self, obj: SceneObject) -> SceneObject:
        if obj not in self.objects or obj.kind == EDITABLE_KIND:
            return obj
        spec = self._spec(obj.kind)
        if spec is not None and spec.category == "null":
            return obj
        self._record("make_editable")
        new = SceneObject(obj.name, _copy_mesh(obj.mesh))
        new.position, new.rotation, new.scale = obj.position.copy(), obj.rotation.copy(), obj.scale.copy()
        new.parent = obj.parent
        new.enabled = obj.enabled
        new.extras = copy.deepcopy(obj.extras)
        consumed = self._consumes(obj)
        gone = {id(d) for d in self.descendants(obj)} if consumed else set()
        kids = self._children_map()
        siblings = kids[obj.parent]
        siblings[siblings.index(obj)] = new
        kids[new] = [] if consumed else kids.pop(obj, [])
        for c in kids[new]:
            c.parent = new
        self.objects = self._order(kids)
        self.extra_selected = [new if o is obj else o for o in self.extra_selected if id(o) not in gone]
        hit = self.active is obj or (self.active is not None and id(self.active) in gone)
        if hit:
            self.pen_finish()
            self.active = new
            self.selected_points.clear()
            self.selected_edges.clear()
            self.selected_polygons.clear()
        self.evaluate()
        self.objectsChanged.emit()
        self.changed.emit()
        self.selectionChanged.emit()
        return new

    def raycast(self, origin: Iterable[float], direction: Iterable[float],
                objects: Iterable[SceneObject] | None = None) -> tuple[SceneObject, int, np.ndarray, float] | None:
        o = np.asarray(origin, float)
        d = np.asarray(direction, float)
        length = np.linalg.norm(d)
        if length < 1e-12:
            return None
        d = d / length
        best: tuple[SceneObject, int, np.ndarray, float] | None = None
        for obj in (self.render_objects() if objects is None else objects):
            world = obj.world_points()
            for k, poly in enumerate(obj.mesh.polygons):
                ring = world[list(poly)]
                tris = [(0, m, m + 1) for m in range(1, len(poly) - 1)] if len(poly) <= 4 else _ear_clip(ring)
                for a, b, c in tris:
                    t = _ray_triangle(o, d, ring[a], ring[b], ring[c])
                    if t is not None and (best is None or t < best[3]):
                        best = (obj, k, o + d * t, t)
        return best

    def world_bounds(self, objects: Iterable[SceneObject] | None = None) -> tuple[np.ndarray, np.ndarray] | None:
        pts = [obj.world_points() for obj in (self.render_objects() if objects is None else objects)
               if len(obj.mesh.points)]
        if not pts:
            return None
        allp = np.vstack(pts)
        return allp.min(axis=0), allp.max(axis=0)

    def selection_world_points(self) -> np.ndarray:
        obj = self.active
        if obj is None or not len(obj.mesh.points):
            return np.zeros((0, 3))
        world = obj.world_points()
        if self.mode != "model" and self.has_selection():
            return world[self.affected_points()]
        return world

    def rename_object(self, obj: SceneObject, name: str) -> None:
        name = name.strip()
        if name and name != obj.name:
            self._record("rename")
            obj.name = name
            self.objectsChanged.emit()

    def _unique_name(self, name: str) -> str:
        taken = {o.name for o in self.objects}
        if name not in taken:
            return name
        n = 1
        while f"{name}.{n}" in taken:
            n += 1
        return f"{name}.{n}"

    def _component_set(self, mode: str | None = None) -> set:
        mode = mode or self.mode
        return {"points": self.selected_points, "edges": self.selected_edges,
                "polygons": self.selected_polygons}[mode]

    def select_object(self, selected: bool = True) -> None:
        dropped = not selected and bool(self.extra_selected)
        if dropped:
            self.extra_selected = []
        if selected != self.object_selected or dropped:
            self.object_selected = selected
            self.selectionChanged.emit()
        if selected and self.active is not None:
            self._default_tool()

    def select_components(self, items: Iterable, *, add: bool = False, remove: bool = False) -> None:
        if self.mode == "model" or not self.is_editable(self.active):
            return
        target = self._component_set()
        norm = [self._normalise(i) for i in items]
        before = set(target)
        if remove:
            target.difference_update(norm)
        elif add:
            target.update(norm)
        else:
            target.clear()
            target.update(norm)
        if target != before:
            self.selectionChanged.emit()

    def clear_selection(self) -> None:
        if self.mode == "model":
            self.select_object(False)
            return
        target = self._component_set()
        if target:
            target.clear()
            self.selectionChanged.emit()

    def _normalise(self, item):
        if self.mode == "edges":
            a, b = int(item[0]), int(item[1])
            return (a, b) if a < b else (b, a)
        return int(item)

    def has_selection(self) -> bool:
        if self.active is None:
            return False
        if self.mode == "model":
            return self.object_selected
        return bool(self._component_set())

    def affected_points(self) -> list[int]:
        if self.mode == "points":
            pts = set(self.selected_points)
        elif self.mode == "edges":
            pts = {i for e in self.selected_edges for i in e}
        elif self.mode == "polygons":
            pts = {i for p in self.selected_polygons for i in self.active.mesh.polygons[p]}
        else:
            pts = set()
        return sorted(pts)

    def selection_center(self) -> np.ndarray | None:
        obj = self.active
        if obj is None or not self.has_selection():
            return None
        if self.mode == "model":
            return obj.world_position()
        idx = self.affected_points()
        return obj.world_points()[idx].mean(axis=0)

    def selection_size(self) -> np.ndarray | None:
        obj = self.active
        if obj is None or self.mode == "model" or not self.has_selection():
            return None
        pts = obj.world_points()[self.affected_points()]
        return pts.max(axis=0) - pts.min(axis=0)

    def move_selection(self, delta_world: Iterable[float]) -> None:
        obj = self.active
        delta = np.asarray(delta_world, float)
        if obj is None or not self.has_selection() or not np.any(delta):
            return
        if self.mode != "model" and not self.is_editable(obj):
            return
        self._record("move")
        if self.mode == "model":
            for o in self.transform_roots():
                step = delta
                if o.parent is not None:
                    step = np.linalg.solve(o.parent.world_linear(), delta)
                o.position = o.position + step
        else:
            local = obj.to_local_vector(delta)
            idx = self.affected_points()
            obj.mesh.points[idx] += local
        self.changed.emit()

    def set_selection_center(self, axis: int, value: float) -> None:
        center = self.selection_center()
        if center is None:
            return
        delta = np.zeros(3)
        delta[axis] = float(value) - center[axis]
        self.move_selection(delta)

    def set_object_position(self, axis: int, value: float) -> None:
        self._set_vector("position", axis, float(value))

    def set_object_rotation(self, axis: int, degrees: float) -> None:
        self._set_vector("rotation", axis, float(degrees))

    def set_object_scale(self, axis: int, factor: float) -> None:
        self._set_vector("scale", axis, float(factor))

    def set_object_size(self, axis: int, cm: float) -> None:
        obj = self.active
        if obj is None:
            return
        base = obj.mesh.size()[axis]
        if obj.parent is not None:
            axis_dir = rotation_matrix(obj.rotation)[:, axis]
            base *= float(np.linalg.norm(obj.parent.world_linear() @ axis_dir))
        if base <= 1e-9 or cm <= 0:
            return
        self.set_object_scale(axis, float(cm) / base)

    def _set_vector(self, attr: str, axis: int, value: float) -> None:
        obj = self.active
        if obj is None:
            return
        vec = getattr(obj, attr).copy()
        if math.isclose(vec[axis], value, abs_tol=1e-9):
            return
        self._record(attr)
        vec[axis] = value
        setattr(obj, attr, vec)
        self.changed.emit()

    def reset_transform(self) -> None:
        obj = self.active
        if obj is None:
            return
        self._record("reset")
        obj.position = np.zeros(3)
        obj.rotation = np.zeros(3)
        obj.scale = np.ones(3)
        self.changed.emit()

    def point_scales(self, obj: SceneObject | None = None) -> np.ndarray:
        obj = self.active if obj is None else obj
        if obj is None:
            return np.zeros(0)
        return obj.mesh.point_scale_array()

    def _scale_indices(self, obj: SceneObject | None, indices: Iterable[int],
                       values) -> tuple[SceneObject | None, np.ndarray, np.ndarray]:
        obj = self.active if obj is None else obj
        empty = np.zeros(0, int), np.zeros(0)
        if obj is None or obj not in self.objects or not self.is_editable(obj):
            return None, *empty
        idx = np.array([int(i) for i in indices], int).reshape(-1)
        vals = np.asarray(values, float)
        vals = np.full(len(idx), float(vals)) if vals.ndim == 0 else vals.reshape(-1)
        if len(vals) != len(idx):
            raise ValueError(f"{len(vals)} values for {len(idx)} points")
        keep = (idx >= 0) & (idx < len(obj.mesh.points))
        return obj, idx[keep], vals[keep]

    def _commit_scales(self, obj: SceneObject, values: np.ndarray) -> bool:
        new = _clean_scales(values, len(obj.mesh.points))
        old = obj.mesh.point_scales
        if (new is None and old is None) or (new is not None and old is not None
                                             and np.array_equal(new, old)):
            return False
        self._record(f"scales:{id(obj)}")
        obj.mesh.point_scales = new
        self.changed.emit()
        return True

    def set_point_scales(self, indices: Iterable[int], values, obj: SceneObject | None = None) -> bool:
        obj, idx, vals = self._scale_indices(obj, indices, values)
        if obj is None or not len(idx):
            return False
        scales = obj.mesh.point_scale_array()
        scales[idx] = vals
        return self._commit_scales(obj, scales)

    def multiply_point_scales(self, indices: Iterable[int], factor, obj: SceneObject | None = None) -> bool:
        obj, idx, vals = self._scale_indices(obj, indices, factor)
        if obj is None or not len(idx):
            return False
        scales = obj.mesh.point_scale_array()
        scales[idx] = scales[idx] * vals
        return self._commit_scales(obj, scales)

    def pen_active(self) -> bool:
        return bool(self.pen_chain)

    def pen_add_point(self, world: Iterable[float], toward_camera: Iterable[float] | None = None) -> int:
        if self.tool != "line_pen" and self.active is not None and not self.is_editable(self.active):
            return -1
        self._record("pen")
        self.begin_group()
        try:
            if self.tool == "line_pen" and not self.pen_chain and (
                    self.active is None or self.active.mesh.has_faces()
                    or not self.is_editable(self.active)):
                self.new_line_object()
        finally:
            self.end_group()
        obj = self.active
        if obj is None or not self.is_editable(obj):
            return -1
        idx = obj.mesh.add_point(obj.to_local_point(world))
        self._pen_extend(idx, toward_camera)
        return idx

    def pen_link_point(self, index: int, toward_camera: Iterable[float] | None = None) -> None:
        if self.active is None or not self.is_editable(self.active) or index in self.pen_chain:
            return
        self._record("pen")
        self._pen_extend(int(index), toward_camera)

    def pen_click_closes(self, index: int) -> bool:
        return len(self.pen_chain) >= 2 and index == self.pen_chain[0]

    def pen_close(self) -> None:
        chain = self.pen_chain
        if self.tool == "line_pen" and len(chain) >= 3 and self.is_editable(self.active):
            self._record("pen")
            self.active.mesh.add_loose_edge(chain[-1], chain[0])
        self.pen_finish()

    def pen_finish(self) -> None:
        if self.pen_chain:
            self.pen_chain = []
            self.pen_polygon = None
            self.changed.emit()

    def _pen_extend(self, idx: int, toward_camera) -> None:
        mesh = self.active.mesh
        self.pen_chain.append(idx)
        chain = self.pen_chain
        if len(chain) == 2 or (len(chain) > 2 and self.tool == "line_pen"):
            mesh.add_loose_edge(chain[-2], chain[-1])
        elif len(chain) >= 3:
            ring = self._facing(chain, toward_camera)
            if self.pen_polygon is None:
                self.pen_polygon = mesh.add_polygon(ring)
            else:
                mesh.set_polygon(self.pen_polygon, ring)
        self._select_pen_result()
        self.changed.emit()

    def _facing(self, chain: list[int], toward_camera) -> list[int]:
        ring = list(chain)
        if toward_camera is None:
            return ring
        obj = self.active
        pts = obj.world_points()[ring]
        nxt = np.roll(pts, -1, axis=0)
        normal = np.array([
            np.sum((pts[:, 1] - nxt[:, 1]) * (pts[:, 2] + nxt[:, 2])),
            np.sum((pts[:, 2] - nxt[:, 2]) * (pts[:, 0] + nxt[:, 0])),
            np.sum((pts[:, 0] - nxt[:, 0]) * (pts[:, 1] + nxt[:, 1])),
        ])
        if float(normal @ np.asarray(toward_camera, float)) < 0:
            ring.reverse()
        return ring

    def _select_pen_result(self) -> None:
        chain = self.pen_chain
        if self.mode == "points":
            new = {chain[-1]}
            target = self.selected_points
        elif self.mode == "edges":
            new = {_edge_key(chain[-2], chain[-1])} if len(chain) >= 2 else set()
            target = self.selected_edges
        elif self.mode == "polygons":
            new = {self.pen_polygon} if self.pen_polygon is not None else set()
            target = self.selected_polygons
        else:
            return
        if target != new:
            target.clear()
            target.update(new)
            self.selectionChanged.emit()

    def extrude_selection(self) -> bool:
        obj = self.active
        if obj is None or self.mode == "model" or not self.is_editable(obj) or not self.has_selection():
            return False
        self._record("extrude")
        mesh = obj.mesh
        if self.mode == "points":
            new_sel: set = set()
            for p in sorted(self.selected_points):
                q = mesh.add_point(mesh.points[p])
                mesh.loose_edges.append(_edge_key(p, q))
                new_sel.add(q)
            mesh._rebuild_edges()
            self.selected_points = new_sel
        elif self.mode == "edges":
            copies: dict[int, int] = {}

            def copy(i: int) -> int:
                if i not in copies:
                    copies[i] = mesh.add_point(mesh.points[i])
                return copies[i]

            new_edges: set[Edge] = set()
            for a, b in sorted(self.selected_edges):
                a2, b2 = copy(a), copy(b)
                if mesh.directed_edge_owner(a, b) is not None:
                    quad = (b, a, a2, b2)
                else:
                    quad = (a, b, b2, a2)
                mesh.polygons.append(quad)
                new_edges.add(_edge_key(a2, b2))
            mesh._rebuild_edges()
            self.selected_edges = new_edges
        else:
            faces = sorted(self.selected_polygons)
            directed = {(u, v) for f in faces
                        for u, v in zip(mesh.polygons[f], mesh.polygons[f][1:] + mesh.polygons[f][:1])}
            copies = {i: mesh.add_point(mesh.points[i])
                      for i in sorted({i for f in faces for i in mesh.polygons[f]})}
            sides = [(u, v, copies[v], copies[u]) for u, v in sorted(directed) if (v, u) not in directed]
            for f in faces:
                mesh.polygons[f] = tuple(copies[i] for i in mesh.polygons[f])
            mesh.polygons.extend(sides)
            mesh._rebuild_edges()
        self.changed.emit()
        self.selectionChanged.emit()
        return True


_SCENE: Scene | None = None


def get_scene() -> Scene:
    global _SCENE
    if _SCENE is None:
        _SCENE = Scene()
    return _SCENE


def reset_scene() -> Scene:
    global _SCENE
    _SCENE = Scene()
    return _SCENE
