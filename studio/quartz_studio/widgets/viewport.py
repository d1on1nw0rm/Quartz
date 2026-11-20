from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

import numpy as np
from PySide6.QtCore import QEvent, QLineF, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontMetricsF,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
    QRegion,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from quartz_studio import icons, theme
from quartz_studio.objects.builtin import null_segments
from quartz_studio.scene import PEN_TOOLS, Mesh, SceneObject, get_scene, rotation_matrix
from quartz_studio.scene import _merge_into_quads, _plane_2d
from quartz_studio.widgets.common import IconButton
from quartz_studio.widgets.menu_bar import P_SHORTCUT, StudioMenu
from quartz_studio.widgets.press_feedback import HOLD_PROPERTY

__all__ = [
    "GroundCamera",
    "OrbitCamera",
    "Viewport",
    "ViewportCanvas",
    "ViewportMenuBar",
    "VIEWPORT_MENUS",
]


FILM_ASPECT = 16 / 9

OVERLAY_INSET = theme.SPACE_2
OVERLAY_TOP = OVERLAY_INSET + theme.NAV_BUTTON
TRIAD_CLEARANCE = 40.0
GIZMO_AXIS_COLORS = (theme.AXIS_X, theme.AXIS_Y, theme.AXIS_Z)
SHADE_MIN = 66
SHADE_SPAN = 124
SHADE_INK = 0.12


_CAMERA_VIEWS = [
    ("check", "Perspective", True),
    ("check", "Parallel", False),
    ("sep",),
    ("check", "Left", False),
    ("check", "Right", False),
    ("check", "Front", False),
    ("check", "Back", False),
    ("check", "Top", False),
    ("check", "Bottom", False),
    ("sep",),
    ("submenu", "Axonometric", [
        ("item", "Isometric"),
        ("item", "Dimetric"),
    ]),
]

VIEWPORT_MENUS: list[tuple[str, list]] = [
    ("View", [
        ("item", "Undo View", "Ctrl+Shift+Z"),
        ("item", "Redo View", "Ctrl+Shift+Y"),
        ("sep",),
        ("item", "Frame Default", "Shift+H"),
        ("item", "Frame Geometry", "H"),
        ("item", "Frame Selected Elements", "S"),
        ("item", "Frame Selected Objects", "O"),
    ]),
    ("Cameras", [
        ("submenu", "Navigation", [
            ("check", "Cursor", True),
            ("check", "Center", False),
            ("check", "Object", False),
            ("check", "Camera", False),
        ]),
        ("sep",),
        *_CAMERA_VIEWS,
    ]),
]

NAV_ICONS: list[tuple[str, str]] = [
    ("view_pan", "Move the View"),
    ("view_zoom", "Zoom the View"),
    ("view_orbit", "Rotate the View"),
]

NAV_ICON_MODES = ("pan", "zoom", "orbit")


VIEW_CHECK = "viewcheck"


def _view_entries(entries: Iterable) -> list:
    out: list = []
    for entry in entries:
        if isinstance(entry, tuple) and entry and entry[0] == "check":
            checked = bool(entry[2]) if len(entry) > 2 else False
            out.append(("item", entry[1], None, None, True, {"check": checked, VIEW_CHECK: True}))
        elif isinstance(entry, tuple) and entry and entry[0] == "submenu":
            out.append(("submenu", entry[1], _view_entries(entry[2])))
        else:
            out.append(entry)
    return out


def _sync_checks(menu: QMenu) -> None:
    for act in menu.actions():
        sub = act.menu()
        if sub is not None:
            _sync_checks(sub)
        elif act.property("qs_" + VIEW_CHECK):
            act.setCheckable(True)
            act.setChecked(bool(act.property("qs_check")))
            act.toggled.connect(lambda on, a=act: a.setProperty("qs_check", bool(on)))


def build_view_menu(entries: Iterable, parent: QWidget | None = None) -> StudioMenu:
    menu = StudioMenu("", parent, _view_entries(entries))
    _sync_checks(menu)
    return menu


def _paint_camera_badge(p: QPainter, r: QRectF, c: QColor) -> None:
    s = min(r.width(), r.height()) / 12.0
    p.save()
    p.translate(r.x() + (r.width() - 12 * s) / 2, r.y() + (r.height() - 12 * s) / 2)
    p.scale(s, s)
    pen = QPen(c, 0.9)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.5, 4.0, 7.5, 6.0), 0.8, 0.8)
    p.drawPolyline(QPolygonF([QPointF(8.0, 6.4), QPointF(11.2, 4.6), QPointF(11.2, 9.4),
                              QPointF(8.0, 7.6)]))
    p.restore()


icons.register("viewport_camera_badge", _paint_camera_badge, theme.TEXT_SECONDARY)


def _unit16(fn):
    def wrapped(p: QPainter, r: QRectF, c: QColor) -> None:
        side = min(r.width(), r.height())
        p.save()
        p.translate(r.x() + (r.width() - side) / 2, r.y() + (r.height() - side) / 2)
        p.scale(side / 16.0, side / 16.0)
        fn(p, c)
        p.restore()
    return wrapped


def _nav_pen(c: QColor, w: float = 1.3) -> QPen:
    pen = QPen(c, w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


@_unit16
def _paint_view_pan(p: QPainter, c: QColor) -> None:
    w = 2.4
    fingers = ((4.3, 4.2), (6.7, 2.6), (9.1, 3.0), (11.5, 4.4))
    path = QPainterPath()
    path.moveTo(4.3, 11.4)
    path.lineTo(2.0, 8.9)
    path.quadTo(2.0, 7.4, 3.4, 7.9)
    path.lineTo(4.3, 9.0)
    for i, (x, top) in enumerate(fingers):
        path.lineTo(x, top + w / 2)
        path.arcTo(QRectF(x, top, w, w), 180, -180)
        if i + 1 < len(fingers):
            path.lineTo(x + w, 8.4)
    right = fingers[-1][0] + w
    path.lineTo(right, 11.0)
    path.quadTo(right, 14.8, 10.2, 14.8)
    path.lineTo(8.0, 14.8)
    path.quadTo(5.2, 14.8, 4.3, 11.4)
    path.closeSubpath()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(_nav_pen(c, 1.1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


@_unit16
def _paint_view_zoom(p: QPainter, c: QColor) -> None:
    p.scale(16 / 24, 16 / 24)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    icons._zoom_arrow(p, QColor(c))


@_unit16
def _paint_view_orbit(p: QPainter, c: QColor) -> None:
    p.setPen(_nav_pen(c, 1.4))
    p.drawArc(QRectF(2.2, 2.2, 11.6, 11.6), 105 * 16, 290 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(9.4, 0.8), QPointF(9.6, 4.6), QPointF(6.6, 2.6)]))
    p.drawEllipse(QPointF(8.0, 8.0), 1.7, 1.7)


@_unit16
def _paint_view_panel(p: QPainter, c: QColor) -> None:
    p.setPen(_nav_pen(c, 1.3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(2.0, 2.0, 12.0, 12.0))
    p.drawLine(QPointF(6.2, 6.2), QPointF(14.0, 6.2))
    p.drawLine(QPointF(6.2, 6.2), QPointF(6.2, 14.0))


icons.register("view_pan", _paint_view_pan, theme.ICON_STROKE)
icons.register("view_zoom", _paint_view_zoom, theme.ICON_STROKE)
icons.register("view_orbit", _paint_view_orbit, theme.ICON_STROKE)
icons.register("view_panel", _paint_view_panel, theme.ICON_STROKE)



LENS_MM = 36.0
FILM_MM = 36.0
DEFAULT_FOCAL = LENS_MM / FILM_MM
DEFAULT_HEADING = 45.0
DEFAULT_PITCH = 19.75
DEFAULT_DISTANCE = 1618.5
PITCH_LIMIT = 89.0
ORBIT_SPEED = 0.3
DOLLY_SPEED = 0.005
WHEEL_STEP = 0.88
MIN_DISTANCE = 2.0
MAX_DISTANCE = 1.0e6
MIN_APPROACH = 5.0
NAV_MIN_DEPTH = 100.0
ORTHO_BACK = 1.0e5
VIEW_HISTORY = 128
FRAME_MARGIN = 1.15
MIN_FRAME_RADIUS = 25.0

VIEW_PRESETS: dict[str, tuple[float | None, float | None, bool]] = {
    "Perspective": (None, None, False),
    "Parallel": (None, None, True),
    "Left": (-90.0, 0.0, True),
    "Right": (90.0, 0.0, True),
    "Front": (0.0, 0.0, True),
    "Back": (180.0, 0.0, True),
    "Top": (0.0, 90.0, True),
    "Bottom": (0.0, -90.0, True),
    "Isometric": (45.0, 35.264, True),
    "Dimetric": (45.0, 20.705, True),
}
FIXED_VIEWS = frozenset(n for n, (h, _p, _o) in VIEW_PRESETS.items() if h is not None)

NAV_PIVOTS = {"Cursor": "cursor", "Center": "center", "Object": "object", "Camera": "camera"}


def _snap(v: np.ndarray) -> np.ndarray:
    return np.where(np.abs(v) < 1e-12, 0.0, v)


@dataclass
class OrbitCamera:

    heading: float = DEFAULT_HEADING
    pitch: float = DEFAULT_PITCH
    distance: float = DEFAULT_DISTANCE
    target: np.ndarray = field(default_factory=lambda: np.zeros(3))
    focal: float = DEFAULT_FOCAL
    near: float = 1.0
    ortho: bool = False

    def copy(self) -> "OrbitCamera":
        return replace(self, target=np.array(self.target, float))

    def state(self) -> tuple:
        return (round(self.heading, 9), round(self.pitch, 9), round(self.distance, 9),
                tuple(round(float(v), 9) for v in self.target), self.ortho)

    def eye_distance(self) -> float:
        return self.distance + (ORTHO_BACK if self.ortho else 0.0)

    def basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        h, e = math.radians(self.heading), math.radians(self.pitch)
        fwd = _snap(np.array([-math.sin(h) * math.cos(e), -math.sin(e), math.cos(h) * math.cos(e)]))
        right = _snap(np.array([math.cos(h), 0.0, math.sin(h)]))
        up = _snap(np.cross(fwd, right))
        pos = np.asarray(self.target, float) - fwd * self.eye_distance()
        return pos, fwd, right, up

    def position(self) -> np.ndarray:
        return self.basis()[0]

    def to_camera(self, pts) -> np.ndarray:
        pos, fwd, right, up = self.basis()
        v = np.atleast_2d(np.asarray(pts, float)) - pos
        return np.stack([v @ right, v @ up, v @ fwd], -1)

    def depth(self, pts) -> np.ndarray:
        return self.to_camera(pts)[:, 2]

    def px_size(self, depth: float, film_w: float) -> float:
        f = max(self.focal * film_w, 1e-9)
        return (self.distance if self.ortho else max(float(depth), 1e-9)) / f

    def cam_to_screen(self, cam: np.ndarray, cx: float, cy: float, film_w: float) -> np.ndarray:
        f = self.focal * film_w
        if self.ortho:
            z = np.full(len(cam), max(self.distance, 1e-9))
        else:
            z = np.where(np.abs(cam[:, 2]) < 1e-9, 1e-9, cam[:, 2])
        return np.stack([cx + f * cam[:, 0] / z, cy - f * cam[:, 1] / z], -1)

    def project(self, pts, cx: float, cy: float, film_w: float) -> tuple[np.ndarray, np.ndarray]:
        c = self.to_camera(pts)
        return self.cam_to_screen(c, cx, cy, film_w), c[:, 2]

    def ray(self, sx: float, sy: float, cx: float, cy: float, film_w: float) -> tuple[np.ndarray, np.ndarray]:
        pos, fwd, right, up = self.basis()
        f = self.focal * film_w
        if self.ortho:
            k = self.distance / f
            return pos + right * ((sx - cx) * k) - up * ((sy - cy) * k), fwd.copy()
        d = fwd + right * ((sx - cx) / f) - up * ((sy - cy) / f)
        return pos, d / np.linalg.norm(d)

    def direction_2d(self, vec: Sequence[float]) -> tuple[float, float]:
        _p, _f, right, up = self.basis()
        v = np.asarray(vec, float)
        return float(v @ right), float(-(v @ up))

    def orbit(self, dx: float, dy: float, clamp: bool = True) -> None:
        self.heading = (self.heading - dx * ORBIT_SPEED + 180.0) % 360.0 - 180.0
        if clamp:
            limit = max(PITCH_LIMIT, abs(self.pitch))
            self.pitch = max(-limit, min(limit, self.pitch + dy * ORBIT_SPEED))
        else:
            self.pitch = (self.pitch + dy * ORBIT_SPEED + 180.0) % 360.0 - 180.0

    def orbit_about(self, pivot, dx: float, dy: float, clamp: bool = True) -> None:
        pivot = np.asarray(pivot, float)
        _p, f0, r0, u0 = self.basis()
        rel = np.stack([r0, u0, f0]) @ (np.asarray(self.target, float) - pivot)
        self.orbit(dx, dy, clamp)
        _p, f1, r1, u1 = self.basis()
        self.target = pivot + np.stack([r1, u1, f1]).T @ rel

    def pan(self, dx: float, dy: float, film_w: float) -> None:
        _p, _f, right, up = self.basis()
        k = self.distance / max(self.focal * film_w, 1e-6)
        self.target = np.asarray(self.target, float) + (-right * dx + up * dy) * k

    def scale_about(self, point, factor: float) -> None:
        point = np.asarray(point, float)
        self.target = point + (np.asarray(self.target, float) - point) * factor
        self.distance *= factor

    def dolly(self, factor: float) -> None:
        self.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, self.distance * factor))


GroundCamera = OrbitCamera


def clip_segments(cam: OrbitCamera, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    za, zb = cam.depth(a), cam.depth(b)
    keep = (za > cam.near) | (zb > cam.near)
    a, b, za, zb = a[keep], b[keep], za[keep], zb[keep]
    dz = np.where(np.abs(zb - za) < 1e-12, 1e-12, zb - za)
    t = np.clip((cam.near - za) / dz, 0.0, 1.0)[:, None]
    cut = a + (b - a) * t
    a2 = np.where((za < cam.near)[:, None], cut, a)
    b2 = np.where((zb < cam.near)[:, None], cut, b)
    return a2, b2


def _clip_polygon_near(poly: np.ndarray, near: float) -> np.ndarray:
    inside = poly[:, 2] >= near
    if inside.all():
        return poly
    if not inside.any():
        return poly[:0]
    out = []
    k = len(poly)
    for i in range(k):
        a, b = poly[i], poly[(i + 1) % k]
        ia, ib = inside[i], inside[(i + 1) % k]
        if ia:
            out.append(a)
        if ia != ib:
            t = (near - a[2]) / (b[2] - a[2])
            out.append(a + (b - a) * t)
    return np.array(out)


def _clip_segment_near(a: np.ndarray, b: np.ndarray, near: float) -> tuple[np.ndarray, np.ndarray] | None:
    if a[2] < near and b[2] < near:
        return None
    if a[2] < near:
        a = a + (b - a) * ((near - a[2]) / (b[2] - a[2]))
    elif b[2] < near:
        b = b + (a - b) * ((near - b[2]) / (a[2] - b[2]))
    return a, b


def _clip_near_many(s0: np.ndarray, s1: np.ndarray, near: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    z0, z1 = s0[:, 2], s1[:, 2]
    keep = (z0 >= near) | (z1 >= near)
    dz = np.where(np.abs(z1 - z0) < 1e-12, 1e-12, z1 - z0)
    cut = s0 + (s1 - s0) * ((near - z0) / dz)[:, None]
    return (np.where((z0 < near)[:, None], cut, s0), np.where((z1 < near)[:, None], cut, s1), keep)


def _segment_distance(x: float, y: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
    return math.hypot(x - (ax + dx * t), y - (ay + dy * t))


def _xy(pos) -> tuple[float, float]:
    if isinstance(pos, (QPoint, QPointF)):
        return float(pos.x()), float(pos.y())
    return float(pos[0]), float(pos[1])


def _ear_clip_2d(flat: np.ndarray) -> list[tuple[int, int, int]]:
    xs, ys = np.asarray(flat[:, 0], float), np.asarray(flat[:, 1], float)
    xl, yl = xs.tolist(), ys.tolist()
    n = len(xl)
    idx = list(range(n))
    tris: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3 and guard < 10 * n:
        guard += 1
        arr = np.asarray(idx)
        px, py = xs[arr], ys[arr]
        m = len(idx)
        for k in range(m):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % m]
            ax, ay, bx, by, cx, cy = xl[i0], yl[i0], xl[i1], yl[i1], xl[i2], yl[i2]
            if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) <= 1e-12:
                continue
            inside = (((bx - ax) * (py - ay) - (by - ay) * (px - ax) >= 0)
                      & ((cx - bx) * (py - by) - (cy - by) * (px - bx) >= 0)
                      & ((ax - cx) * (py - cy) - (ay - cy) * (px - cx) >= 0)
                      & (arr != i0) & (arr != i1) & (arr != i2))
            if not inside.any():
                tris.append((i0, i1, i2))
                idx.pop(k)
                break
        else:
            tris.extend((idx[0], idx[j], idx[j + 1]) for j in range(1, len(idx) - 1))
            return tris
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def _is_text_input(w: QWidget | None) -> bool:
    if isinstance(w, (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit)):
        return True
    return isinstance(w, QComboBox) and w.isEditable()


def _controls():
    from quartz_studio import controls

    return controls


def _controls_profiles():
    from quartz_studio.controls import profiles

    return profiles


def _button_name(button: Qt.MouseButton) -> str | None:
    if button == Qt.MouseButton.LeftButton:
        return "left"
    if button == Qt.MouseButton.MiddleButton:
        return "middle"
    if button == Qt.MouseButton.RightButton:
        return "right"
    return None


def _modifier_names(mods: Qt.KeyboardModifier) -> set[str]:
    names: set[str] = set()
    if mods & Qt.KeyboardModifier.ShiftModifier:
        names.add("shift")
    if mods & Qt.KeyboardModifier.ControlModifier:
        names.add("ctrl")
    if mods & Qt.KeyboardModifier.AltModifier:
        names.add("alt")
    return names


def _modifier_of_key(key: int) -> Qt.KeyboardModifier:
    if key == int(Qt.Key.Key_Shift):
        return Qt.KeyboardModifier.ShiftModifier
    if key == int(Qt.Key.Key_Control):
        return Qt.KeyboardModifier.ControlModifier
    if key == int(Qt.Key.Key_Alt):
        return Qt.KeyboardModifier.AltModifier
    return Qt.KeyboardModifier.NoModifier


NAV_OPS = {"orbit": "orbit", "pan": "pan", "dolly": "zoom"}
SELECT_OPS = ("select", "add", "remove")
TRANSFORM_TOOLS = ("move", "rotate", "scale")
PAINT_OPS = {"context": "replace", "select": "replace", "add": "add", "remove": "remove"}


HUD_TEXTS = {"select": "Brush Selection", "move": "Move", "rotate": "Rotate", "scale": "Scale",
             "pen": "Polygon Pen", "line_pen": "Pen", "select_loop": "Loop Selection",
             "select_ring": "Ring Selection", "select_pattern": "Pattern Selection",
             "select_fill": "Fill Selection", "select_phong": "Phong Angle Selection"}
AXES = ("x", "y", "z")

MODE_NAMES = {"points": "Points", "edges": "Edges", "polygons": "Polygons", "model": "Model"}
TOOL_NAMES = {"select": "Brush Selection", "move": "Move", "rotate": "Rotate", "scale": "Scale",
              "pen": "Polygon Pen", "line_pen": "Pen", "select_loop": "Loop Selection",
              "select_ring": "Ring Selection", "select_pattern": "Pattern Selection",
              "select_fill": "Fill Selection", "select_phong": "Phong Angle Selection",
              "other": "Other"}


@dataclass
class _Nav:

    mode: str
    button: Qt.MouseButton | None
    last: QPointF
    pivot: np.ndarray
    before: tuple


@dataclass
class _ObjectView:

    obj: SceneObject
    world: np.ndarray
    cam: np.ndarray
    screen: np.ndarray
    in_front: np.ndarray
    normals: np.ndarray
    front: np.ndarray
    visible_points: np.ndarray
    edge_faces: dict
    visible_edges: list
    shown: np.ndarray | None = None
    polys: dict = field(default_factory=dict)
    topo: object = None
    poly_depth: np.ndarray | None = None
    poly_front: np.ndarray | None = None
    screen_list: list | None = None

    def __post_init__(self) -> None:
        if self.shown is None:
            self.shown = np.asarray(self.front, bool).copy()


class _Topology:

    def __init__(self, mesh: Mesh) -> None:
        polys = mesh.polygons
        count = len(polys)
        self.counts = np.fromiter((len(p) for p in polys), int, count)
        total = int(self.counts.sum())
        self.flat = np.fromiter((i for p in polys for i in p), int, total)
        self.pid = np.repeat(np.arange(count), self.counts)
        edge_faces: dict = {}
        sides: list[tuple[int, int]] = []
        for k, poly in enumerate(polys):
            for a, b in zip(poly, poly[1:] + poly[:1]):
                key = (a, b) if a < b else (b, a)
                edge_faces.setdefault(key, []).append(k)
                sides.append(key)
        self.edge_faces = edge_faces
        index = {e: i for i, e in enumerate(edge_faces)}
        self.side_edge = np.fromiter((index[e] for e in sides), int, len(sides))
        faces = np.fromiter((len(v) for v in edge_faces.values()), int, len(edge_faces))
        if len(self.side_edge):
            single = (faces[self.side_edge] == 1).astype(float)
            self.open_poly = np.bincount(self.pid, single, count) > 0
        else:
            self.open_poly = np.zeros(count, bool)
        self.closed = bool(edge_faces) and bool((faces == 2).all())
        self.on_face = np.zeros(len(mesh.points), bool)
        self.on_face[self.flat] = True
        self.mesh_edge_ids = np.fromiter((index.get(e, -1) for e in mesh.edges), int, len(mesh.edges))


@dataclass
class _Drag:

    handle: str
    press: QPointF
    center0: np.ndarray
    axis: np.ndarray | None = None
    t0: float = 0.0
    plane_hit0: np.ndarray | None = None
    screen_dir: tuple[float, float] | None = None
    cm_per_px: float = 0.0
    applied: np.ndarray = field(default_factory=lambda: np.zeros(3))
    active: bool = False
    pending: tuple = ()
    ctrl_at_press: bool = False
    ctrl_seen: bool = False
    extruded: bool = False
    grew: bool = False
    gizmo: bool = False
    obj: SceneObject | None = None
    basis: tuple | None = None
    angle0: float = 0.0
    scale_base: float = 0.0
    screen_centre: tuple[float, float] = (0.0, 0.0)
    origin_pos: np.ndarray | None = None
    origin_rot: np.ndarray | None = None
    origin_scale: np.ndarray | None = None
    origin_points: np.ndarray | None = None
    affected: list = field(default_factory=list)
    world0: np.ndarray | None = None
    free: bool = False
    clone: bool = False
    click_op: str = ""
    objs: list = field(default_factory=list)
    frame: np.ndarray | None = None


@dataclass
class _Press:

    press: QPointF
    op: str
    button: Qt.MouseButton
    paint: bool = False
    moved: bool = False
    painting: bool = False
    last: QPointF | None = None
    kind: str = "replace"


@dataclass
class _PenPress:

    press: QPointF
    kind: str | None
    item: object
    moved: bool = False


def _drop_last_undo_step(scene) -> None:
    stack = getattr(scene, "_undo", None)
    if stack:
        stack.pop()


def _wrap_angle(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _axis_rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    x, y, z = (float(v) for v in axis)
    k = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return np.eye(3) + math.sin(angle) * k + (1.0 - math.cos(angle)) * (k @ k)


def _euler_xyz(m: np.ndarray) -> np.ndarray:
    xy = math.hypot(m[0, 0], m[1, 0])
    b = math.atan2(-m[2, 0], xy)
    if xy > 1e-9:
        a = math.atan2(m[2, 1], m[2, 2])
        c = math.atan2(m[1, 0], m[0, 0])
    else:
        a = 0.0
        c = math.atan2(-m[0, 1], m[1, 1])
    first = (_wrap_angle(a), b, _wrap_angle(c))
    second = (_wrap_angle(a + math.pi), _wrap_angle(math.pi - b), _wrap_angle(c + math.pi))
    best = min((first, second), key=lambda t: sum(abs(v) for v in t))
    return np.degrees(np.array(best, float))


class ViewportCanvas(QWidget):

    WORLD_AXIS_LENGTH = 250.0
    AXIS_PIECES = 12
    GIZMO_PX = 85.0
    GIZMO_HEAD_PX = 12.0
    GIZMO_PICK_PX = 7.0
    GIZMO_AXIS_FIRST_PX = 2.5
    PLANE_CORE = 0.5
    GIZMO_CENTER_PX = 6.5
    AXIS_FALLBACK_PX = 14.0
    POINT_PICK_PX = 8.0
    EDGE_PICK_PX = 6.0
    DRAG_THRESHOLD = 3
    CONTEXT_DRAG_PX = 4.0
    MAX_DRAG_CM = 1.0e5
    GIZMO_RING_PX = 68.0
    RING_TIE_PX = 0.5
    GIZMO_VIEW_RING_SCALE = 1.2
    PLANE_NEAR = 0.22
    PLANE_FAR = 0.46
    PLANE_EDGE_ON = 0.15
    PLANE_PICK_PX = 2.0
    RING_SEGMENTS = 48
    ROTATE_STEP = 5.0
    SCALE_STEP = 0.1
    MIN_SCALE = 0.01
    FREE_ROTATE_DEG_PER_PX = 0.5
    PAINT_STEP_PX = 6.0

    viewChanged = Signal(str)
    navPivotChanged = Signal(str)
    hudChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsViewportCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.camera = OrbitCamera()
        self.scene = get_scene()
        self.view_name = "Perspective"
        self.camera_name = ""
        self.nav_pivot = self._profile_pivot()
        self._hud_tool = self.scene.tool if self.scene.tool in HUD_TEXTS else "move"
        self.hud_text = HUD_TEXTS[self._hud_tool]
        self._nav: _Nav | None = None
        self._drag: _Drag | None = None
        self._hover: str | None = None
        self._held_keys: set[int] = _controls().held_set()
        self._press_mods = Qt.KeyboardModifier.NoModifier
        self._view_states: dict[str, OrbitCamera] = {}
        self._view_undo: deque[tuple[str, OrbitCamera]] = deque(maxlen=VIEW_HISTORY)
        self._view_redo: list[tuple[str, OrbitCamera]] = []
        self._wheel_merge_until = 0.0
        self._pen_press: _PenPress | None = None
        self._press_state: _Press | None = None
        self._cloning = False
        self.context_menu = None
        self._pen_hover: tuple | None = None
        self._tri_cache: dict = {}
        self._mesh_tri_cache: dict = {}
        self._guide_cache: dict = {}
        self._sight_cache: dict = {}
        self._topo_cache: dict = {}
        self._guide_batch_cache: dict = {}
        self._shade_cache: dict = {}
        self._refine_now = False
        self._refine_timer = QTimer(self)
        self._refine_timer.setSingleShot(True)
        self._refine_timer.setInterval(self.REFINE_MS)
        self._refine_timer.timeout.connect(self._refine)
        self._focus_claimed = False
        _controls().hub().profileChanged.connect(self._on_profile_changed)
        self.setToolTip("")
        self._sync_cursor()
        self.scene.changed.connect(self._on_scene_changed)
        self.scene.selectionChanged.connect(self._on_scene_changed)
        self.scene.modeChanged.connect(self._on_mode_changed)
        self.scene.toolChanged.connect(self._on_tool_changed)
        self.scene.objectsChanged.connect(self._on_objects_changed)

    def _on_scene_changed(self) -> None:
        self.update()

    @staticmethod
    def _profile_pivot() -> str:
        name = _controls().cursor("orbit_pivot")
        return name if name in NAV_PIVOTS else "Cursor"

    def _on_profile_changed(self, _profile_id: str = "") -> None:
        self.set_nav_pivot(self._profile_pivot())

    def _on_mode_changed(self, _mode: str) -> None:
        self._end_drag()
        self._drop_press()
        self._hover = None
        self._pen_press = None
        self._pen_hover = None
        self._sync_cursor()
        self.update()

    def _on_tool_changed(self, tool: str) -> None:
        if self._drag is not None and self._drag.gizmo:
            self.cancel_drag()
        if tool != "move":
            self._end_drag()
            self._hover = None
        if self._press_state is not None and not self._press_state.paint:
            self._drop_press()
        self._pen_press = None
        self._pen_hover = None
        if tool != "other":
            self._hud_tool = tool
            self.hud_text = HUD_TEXTS.get(tool) or TOOL_NAMES.get(tool, tool)
            self.hudChanged.emit()
        self._sync_cursor()
        self.update()

    def _on_objects_changed(self) -> None:
        if self._cloning:
            self.update()
            return
        self._end_drag()
        self._drop_press()
        self._pen_press = None
        self._pen_hover = None
        self.update()

    def pen_mode(self) -> bool:
        return self.scene.tool in PEN_TOOLS and self.scene.mode != "model"

    def _sync_cursor(self) -> None:
        if self.pen_mode():
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()

    def _end_drag(self) -> _Drag | None:
        d, self._drag = self._drag, None
        if d is not None:
            self.scene.end_group()
        return d

    def _drop_press(self) -> None:
        st, self._press_state = self._press_state, None
        if st is not None and st.painting:
            self.scene.end_group()

    def inner_rect(self) -> QRectF:
        return QRectF(0, 0, self.width(), self.height())

    def film_rect(self) -> QRectF:
        r = self.inner_rect()
        if r.width() / max(r.height(), 1) > FILM_ASPECT:
            w = r.height() * FILM_ASPECT
            return QRectF(r.center().x() - w / 2, r.top(), w, r.height())
        h = r.width() / FILM_ASPECT
        return QRectF(r.left(), r.center().y() - h / 2, r.width(), h)

    def _view_params(self) -> tuple[float, float, float]:
        c = self.inner_rect().center()
        return c.x(), c.y(), self.camera.focal * self.film_rect().width()

    def project(self, pts) -> tuple[np.ndarray, np.ndarray]:
        cx, cy, _f = self._view_params()
        return self.camera.project(np.asarray(pts, float), cx, cy, self.film_rect().width())

    def project_world(self, pts) -> np.ndarray:
        xy, z = self.project(pts)
        xy = xy.copy()
        xy[z <= self.camera.near] = np.nan
        return xy

    def _cam_to_screen(self, cam: np.ndarray) -> np.ndarray:
        cx, cy, _f = self._view_params()
        if not self.camera.ortho:
            cam = np.column_stack([cam[:, :2], np.maximum(cam[:, 2], 1e-9)])
        return self.camera.cam_to_screen(cam, cx, cy, self.film_rect().width())

    def _ray(self, pos) -> tuple[np.ndarray, np.ndarray]:
        x, y = _xy(pos)
        cx, cy, _f = self._view_params()
        return self.camera.ray(x, y, cx, cy, self.film_rect().width())

    def ray_at(self, pos) -> tuple[np.ndarray, np.ndarray]:
        return self._ray(pos)

    def view_direction(self) -> np.ndarray:
        return self.camera.basis()[1].copy()

    def toward_camera(self, point) -> np.ndarray:
        pos, fwd, _r, _u = self.camera.basis()
        if self.camera.ortho:
            return -fwd
        return pos - np.asarray(point, float)

    def px_size(self, depth: float) -> float:
        return self.camera.px_size(depth, self.film_rect().width())

    def hit_at(self, pos):
        o, d = self._ray(pos)
        return self.raycast(o, d)

    _CACHE_LIMIT = 512

    def _cached(self, cache: dict, key, make, limit: int | None = None):
        value = cache.pop(key, None)
        if value is None:
            value = make()
            while len(cache) >= (self._CACHE_LIMIT if limit is None else limit):
                cache.pop(next(iter(cache)))
        cache[key] = value
        return value

    def _ngon_tris(self, mesh: Mesh, poly: tuple) -> list[tuple[int, int, int]]:
        ring = mesh.points[list(poly)]
        return self._cached(self._tri_cache, (poly, ring.tobytes()),
                            lambda: _ear_clip_2d(_plane_2d(ring)))

    def ngon_guides(self, mesh: Mesh, k: int) -> list[tuple[int, int]]:
        poly = mesh.polygons[k]
        if len(poly) <= 4:
            return []
        ring = mesh.points[list(poly)]

        def make() -> list[tuple[int, int]]:
            tris = self._ngon_tris(mesh, poly)
            return [(poly[a], poly[b]) for a, b in _merge_into_quads(ring, tris)]

        return self._cached(self._guide_cache, (poly, ring.tobytes()), make)

    _MESH_TRI_LIMIT = 8

    def _mesh_triangles(self, mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
        key = (tuple(mesh.polygons), mesh.points.tobytes())
        return self._cached(self._mesh_tri_cache, key, lambda: self._build_triangles(mesh),
                            self._MESH_TRI_LIMIT)

    def _build_triangles(self, mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
        tris: list[tuple[int, int, int]] = []
        owner: list[int] = []
        for k, poly in enumerate(mesh.polygons):
            if len(poly) < 3:
                continue
            local = ([(0, m, m + 1) for m in range(1, len(poly) - 1)] if len(poly) <= 4
                     else self._ngon_tris(mesh, poly))
            tris.extend((poly[a], poly[b], poly[c]) for a, b, c in local)
            owner.extend([k] * len(local))
        return np.asarray(tris, int).reshape(-1, 3), np.asarray(owner, int)

    def raycast(self, origin, direction, objects: Iterable[SceneObject] | None = None):
        o = np.asarray(origin, float)
        d = np.asarray(direction, float)
        length = float(np.linalg.norm(d))
        if length < 1e-12:
            return None
        d = d / length
        best = None
        for obj in (self.scene.render_objects() if objects is None else objects):
            tri, owner = self._mesh_triangles(obj.mesh)
            if not len(tri):
                continue
            world = obj.world_points()
            a, b, c = world[tri[:, 0]], world[tri[:, 1]], world[tri[:, 2]]
            e1, e2 = b - a, c - a
            p = np.cross(d, e2)
            det = np.einsum("ij,ij->i", e1, p)
            ok = np.abs(det) >= 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            s = o - a
            u = np.einsum("ij,ij->i", s, p) * inv
            q = np.cross(s, e1)
            v = (q @ d) * inv
            t = np.einsum("ij,ij->i", e2, q) * inv
            ok &= (u >= -1e-9) & (u <= 1 + 1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 1e-9)
            if not ok.any():
                continue
            j = int(np.argmin(np.where(ok, t, np.inf)))
            if best is None or t[j] < best[3]:
                best = (obj, int(owner[j]), o + d * float(t[j]), float(t[j]))
        return best

    def unproject(self, pos, depth_or_plane) -> np.ndarray | None:
        o, d = self._ray(pos)
        pos_eye, fwd, _r, _u = self.camera.basis()
        if isinstance(depth_or_plane, (int, float, np.floating)):
            along = float(d @ fwd)
            if along < 1e-9:
                return None
            start = float((o - pos_eye) @ fwd)
            return o + d * ((float(depth_or_plane) - start) / along)
        point, normal = depth_or_plane
        normal = np.asarray(normal, float)
        denom = float(d @ normal)
        if abs(denom) < 1e-12:
            return None
        t = float((np.asarray(point, float) - o) @ normal) / denom
        return o + d * t if t > 0 else None

    def cursor_point(self, pos) -> np.ndarray:
        hit = self.hit_at(pos)
        if hit is not None:
            return np.asarray(hit[2], float)
        point = self.unproject(pos, max(self.camera.eye_distance(), NAV_MIN_DEPTH))
        return point if point is not None else np.asarray(self.camera.target, float).copy()

    def label_font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(11)
        return f

    def _object_view(self, obj: SceneObject) -> _ObjectView:
        mesh = obj.mesh
        world = obj.world_points()
        cam = self.camera.to_camera(world)
        screen = self._cam_to_screen(cam)
        in_front = cam[:, 2] > self.camera.near
        normals = mesh.polygon_normals(world)
        eye, fwd, _right, _up = self.camera.basis()
        topo = self._topology(mesh)
        count = len(mesh.polygons)
        pid, flat = topo.pid, topo.flat
        sizes = np.maximum(topo.counts, 1)
        if self.camera.ortho:
            front = (normals @ -fwd) > 1e-12
        else:
            centre = np.stack([np.bincount(pid, world[flat, d], count) for d in range(3)], axis=1)
            centre = centre.astype(float).reshape(count, 3) / sizes[:, None]
            front = np.einsum("ij,ij->i", normals, eye[None, :] - centre) > 1e-12
        front = np.asarray(front, bool).reshape(count)
        shown = front | topo.open_poly
        visible_points = ~topo.on_face
        visible_points[flat[shown[pid]]] = True
        if obj is self.scene.active and self.scene.pen_chain:
            chain = [i for i in self.scene.pen_chain if 0 <= i < len(world)]
            visible_points[chain] = True
        if len(topo.side_edge):
            edge_shown = np.bincount(topo.side_edge, shown[pid].astype(float), len(topo.edge_faces)) > 0
        else:
            edge_shown = np.zeros(len(topo.edge_faces), bool)
        eids = topo.mesh_edge_ids
        keep = eids < 0
        keep[~keep] = edge_shown[eids[~keep]]
        visible_edges = [e for e, k in zip(mesh.edges, keep.tolist()) if k]
        poly_depth = np.bincount(pid, cam[flat, 2], count).astype(float) / sizes
        poly_front = np.bincount(pid, (~in_front[flat]).astype(float), count) == 0
        return _ObjectView(obj, world, cam, screen, in_front, normals, front, visible_points,
                           topo.edge_faces, visible_edges, shown, topo=topo, poly_depth=poly_depth,
                           poly_front=poly_front)

    _TOPO_LIMIT = 16

    def _topology(self, mesh: Mesh) -> "_Topology":
        key = (len(mesh.points), tuple(mesh.polygons), tuple(mesh.edges))
        cache = self._topo_cache
        return self._cached(cache, key, lambda: _Topology(mesh), self._TOPO_LIMIT)

    def _poly_screen(self, view: _ObjectView, k: int) -> tuple[QPolygonF | None, float]:
        cached = view.polys.get(k)
        if cached is not None:
            return cached
        if view.poly_front is not None and view.poly_front[k]:
            if view.screen_list is None:
                view.screen_list = view.screen.tolist()
            sl = view.screen_list
            view.polys[k] = (QPolygonF([QPointF(*sl[i]) for i in view.obj.mesh.polygons[k]]),
                             float(view.poly_depth[k]))
            return view.polys[k]
        idx = list(view.obj.mesh.polygons[k])
        if view.in_front[idx].all():
            pts, depth = view.screen[idx], float(view.cam[idx, 2].mean())
        else:
            clipped = _clip_polygon_near(view.cam[idx], self.camera.near)
            if len(clipped) < 3:
                view.polys[k] = (None, 0.0)
                return view.polys[k]
            pts, depth = self._cam_to_screen(clipped), float(clipped[:, 2].mean())
        view.polys[k] = (QPolygonF([QPointF(float(x), float(y)) for x, y in pts]), depth)
        return view.polys[k]

    def _edge_lines(self, view: _ObjectView, edges) -> list[QLineF | None]:
        e = np.asarray(list(edges), int).reshape(-1, 2)
        if not len(e):
            return []
        s0, s1, keep = _clip_near_many(view.cam[e[:, 0]], view.cam[e[:, 1]], self.camera.near)
        p0, p1 = self._cam_to_screen(s0), self._cam_to_screen(s1)
        return [QLineF(p0[i, 0], p0[i, 1], p1[i, 0], p1[i, 1]) if keep[i] else None
                for i in range(len(e))]

    def _edge_screen(self, view: _ObjectView, edge) -> QLineF | None:
        seg = _clip_segment_near(view.cam[edge[0]], view.cam[edge[1]], self.camera.near)
        if seg is None:
            return None
        s = self._cam_to_screen(np.vstack(seg))
        return QLineF(s[0, 0], s[0, 1], s[1, 0], s[1, 1])

    def pick(self, pos) -> tuple[str | None, object]:
        mode = self.scene.mode
        if mode == "model":
            hit = self.pick_object(pos)
            return ("object", hit) if hit is not None else (None, None)
        obj = self.scene.active
        if obj is None:
            return None, None
        view = self._object_view(obj)
        x, y = _xy(pos)
        if mode == "points":
            item = self._pick_point(view, x, y)
            return ("point", item) if item is not None else (None, None)
        if mode == "edges":
            item = self._pick_edge(view, x, y)
            return ("edge", item) if item is not None else (None, None)
        item = self._pick_polygon(view, x, y)
        return ("polygon", item) if item is not None else (None, None)

    def pick_object(self, pos) -> SceneObject | None:
        x, y = _xy(pos)
        best, best_depth = None, math.inf
        for obj in self.scene.render_objects():
            view = self._object_view(obj)
            k = self._pick_polygon(view, x, y)
            if k is not None:
                depth = view.polys[k][1]
                if depth < best_depth:
                    best, best_depth = obj, depth
            mesh = obj.mesh
            for edge in mesh.loose_edges:
                seg = _clip_segment_near(view.cam[edge[0]], view.cam[edge[1]], self.camera.near)
                if seg is None:
                    continue
                s = self._cam_to_screen(np.vstack(seg))
                if _segment_distance(x, y, s[0, 0], s[0, 1], s[1, 0], s[1, 1]) <= self.EDGE_PICK_PX:
                    depth = float(min(seg[0][2], seg[1][2]))
                    if depth < best_depth:
                        best, best_depth = obj, depth
            if not mesh.has_faces() and len(mesh.points):
                near = view.in_front & (np.hypot(view.screen[:, 0] - x, view.screen[:, 1] - y)
                                        <= self.POINT_PICK_PX)
                if near.any():
                    depth = float(view.cam[near, 2].min())
                    if depth < best_depth:
                        best, best_depth = obj, depth
        return best

    def _pick_point(self, view: _ObjectView, x: float, y: float) -> int | None:
        cand = np.nonzero(view.visible_points & view.in_front)[0]
        if not len(cand):
            return None
        d = np.hypot(view.screen[cand, 0] - x, view.screen[cand, 1] - y)
        j = int(np.argmin(d))
        return int(cand[j]) if d[j] <= self.POINT_PICK_PX else None

    def _pick_edge(self, view: _ObjectView, x: float, y: float):
        best, best_d = None, self.EDGE_PICK_PX
        for edge in view.visible_edges:
            line = self._edge_screen(view, edge)
            if line is None:
                continue
            d = _segment_distance(x, y, line.x1(), line.y1(), line.x2(), line.y2())
            if d <= best_d:
                best, best_d = edge, d
        return best

    def _pick_polygon(self, view: _ObjectView, x: float, y: float) -> int | None:
        best, best_depth = None, math.inf
        pt = QPointF(x, y)
        for k in np.nonzero(view.shown)[0]:
            poly, depth = self._poly_screen(view, int(k))
            if poly is not None and depth < best_depth and poly.containsPoint(pt, Qt.FillRule.OddEvenFill):
                best, best_depth = int(k), depth
        return best

    def _is_selected(self, kind: str, item) -> bool:
        scene = self.scene
        if kind == "point":
            return item in scene.selected_points
        if kind == "edge":
            return tuple(item) in scene.selected_edges
        if kind == "polygon":
            return item in scene.selected_polygons
        if kind == "object":
            return scene.is_object_selected(item)
        return scene.object_selected

    def _gizmo_axes(self) -> np.ndarray:
        scene = self.scene
        obj = scene.active
        if scene.tool == "scale" and scene.mode == "model" and obj is not None:
            lin = obj.world_linear()
            norms = np.linalg.norm(lin, axis=0)
            if np.all(norms > 1e-9):
                return (lin / norms).T
        return np.eye(3)

    def _gizmo_geometry(self) -> dict | None:
        scene = self.scene
        if scene.tool not in ("move", "scale") or not scene.has_selection():
            return None
        centre = scene.selection_center()
        if centre is None:
            return None
        depth = float(self.camera.depth(centre)[0])
        if depth <= self.camera.near * 2:
            return None
        length = self.GIZMO_PX * self.px_size(depth)
        pts = np.vstack([centre, centre + self._gizmo_axes() * length])
        cam = self.camera.to_camera(pts)
        scr = self._cam_to_screen(cam)
        geo: dict = {"center": (float(scr[0, 0]), float(scr[0, 1])), "world": centre,
                     "length": length, "depth": {}}
        for i, axis in enumerate(AXES):
            if cam[i + 1, 2] > self.camera.near:
                geo[axis] = (geo["center"], (float(scr[i + 1, 0]), float(scr[i + 1, 1])))
                geo["depth"][axis] = float(cam[i + 1, 2])
        if scene.tool == "move":
            geo["planes"], geo["plane_depth"] = self._plane_handle_screens(centre, length)
        return geo

    def _plane_handle_screens(self, centre: np.ndarray, length: float) -> tuple[dict, dict]:
        planes: dict[str, np.ndarray] = {}
        depths: dict[str, float] = {}
        pos, fwd, _right, _up = self.camera.basis()
        if self.camera.ortho:
            view = fwd
        else:
            view = np.asarray(centre, float) - pos
            norm = float(np.linalg.norm(view))
            if norm < 1e-9:
                return planes, depths
            view = view / norm
        eye = np.eye(3)
        lo, hi = self.PLANE_NEAR * length, self.PLANE_FAR * length
        for i, axis in enumerate(AXES):
            if abs(float(view @ eye[i])) < self.PLANE_EDGE_ON:
                continue
            ej, ek = eye[(i + 1) % 3], eye[(i + 2) % 3]
            quad = np.asarray(centre, float) + np.array([lo * ej + lo * ek, hi * ej + lo * ek,
                                                         hi * ej + hi * ek, lo * ej + hi * ek])
            cam = self.camera.to_camera(quad)
            if (cam[:, 2] <= self.camera.near).any():
                continue
            planes["plane_" + axis] = self._cam_to_screen(cam)
            depths["plane_" + axis] = float(cam[:, 2].mean())
        return planes, depths

    def gizmo_plane_handles(self) -> dict[str, np.ndarray]:
        geo = self._gizmo_geometry()
        return {} if geo is None else dict(geo.get("planes", {}))

    def _plane_core(self, quad: np.ndarray) -> np.ndarray:
        mid = quad.mean(axis=0)
        return mid + (quad - mid) * self.PLANE_CORE

    def _plane_inside(self, quad: np.ndarray, x: float, y: float) -> bool:
        poly = QPolygonF([QPointF(float(a), float(b)) for a, b in quad])
        return poly.containsPoint(QPointF(x, y), Qt.FillRule.OddEvenFill)

    def _plane_hit_test(self, quad: np.ndarray, x: float, y: float) -> bool:
        if self._plane_inside(quad, x, y):
            return True
        for i in range(len(quad)):
            a, b = quad[i], quad[(i + 1) % len(quad)]
            if _segment_distance(x, y, float(a[0]), float(a[1]), float(b[0]), float(b[1])) <= self.PLANE_PICK_PX:
                return True
        return False

    def gizmo_handles(self) -> dict[str, tuple[tuple[float, float], tuple[float, float]]]:
        geo = self._gizmo_geometry()
        return {a: geo[a] for a in AXES if geo is not None and a in geo}

    def gizmo_center(self) -> tuple[float, float] | None:
        geo = self._gizmo_geometry()
        return None if geo is None else geo["center"]

    def gizmo_hit(self, pos) -> str | None:
        geo = self._gizmo_geometry()
        if geo is None:
            return None
        x, y = _xy(pos)
        cx, cy = geo["center"]
        if math.hypot(x - cx, y - cy) <= self.GIZMO_CENTER_PX:
            return "center"
        best, best_d = None, self.GIZMO_PICK_PX
        for axis in AXES:
            if axis not in geo:
                continue
            (sx, sy), (ex, ey) = geo[axis]
            n = math.hypot(ex - sx, ey - sy)
            if n < 1.0:
                continue
            ux, uy = (ex - sx) / n, (ey - sy) / n
            tip = (ex + ux * self.GIZMO_HEAD_PX, ey + uy * self.GIZMO_HEAD_PX)
            d = _segment_distance(x, y, sx + ux * 4.0, sy + uy * 4.0, *tip)
            if d <= best_d:
                best, best_d = axis, d
        planes = geo.get("planes", {})
        depths = geo.get("plane_depth", {})
        core = [name for name, quad in planes.items() if self._plane_inside(self._plane_core(quad), x, y)]
        if core:
            return min(core, key=lambda name: depths.get(name, 0.0))
        if best is not None and best_d <= self.GIZMO_AXIS_FIRST_PX:
            return best
        inside = [name for name, quad in planes.items() if self._plane_inside(quad, x, y)]
        if inside:
            return min(inside, key=lambda name: depths.get(name, 0.0))
        if best is not None:
            return best
        near = [name for name, quad in planes.items() if self._plane_hit_test(quad, x, y)]
        if near:
            return min(near, key=lambda name: math.hypot(x - float(planes[name][:, 0].mean()),
                                                          y - float(planes[name][:, 1].mean())))
        return None

    def _ring_screen(self, centre: np.ndarray, u: np.ndarray, v: np.ndarray, radius: float) -> np.ndarray | None:
        ang = np.linspace(0.0, 2.0 * math.pi, self.RING_SEGMENTS + 1)
        world = centre + radius * (np.outer(np.cos(ang), u) + np.outer(np.sin(ang), v))
        cam = self.camera.to_camera(world)
        if (cam[:, 2] <= self.camera.near).any():
            return None
        return self._cam_to_screen(cam)

    def _rotate_frame(self) -> dict | None:
        scene = self.scene
        if scene.tool != "rotate" or not scene.has_selection():
            return None
        centre = scene.selection_center()
        if centre is None:
            return None
        depth = float(self.camera.depth(centre)[0])
        if depth <= self.camera.near * 2:
            return None
        size = self.GIZMO_RING_PX * self.px_size(depth)
        _pos, fwd, right, up = self.camera.basis()
        eye = np.eye(3)
        specs = [(axis, eye[i], eye[(i + 1) % 3], eye[(i + 2) % 3], size) for i, axis in enumerate(AXES)]
        specs.append(("view", fwd, right, up, size * self.GIZMO_VIEW_RING_SCALE))
        rings = {}
        for name, normal, u, v, radius in specs:
            scr = self._ring_screen(centre, u, v, radius)
            if scr is not None:
                rings[name] = (scr, normal, u, v)
        return rings

    def gizmo_rings(self) -> dict[str, np.ndarray]:
        return {name: ring[0] for name, ring in (self._rotate_frame() or {}).items()}

    def ring_hit(self, pos) -> str | None:
        rings = self._rotate_frame()
        if not rings:
            return None
        x, y = _xy(pos)
        best, best_d = None, math.inf
        for name, (scr, _normal, _u, _v) in rings.items():
            d = min(_segment_distance(x, y, scr[i, 0], scr[i, 1], scr[i + 1, 0], scr[i + 1, 1])
                    for i in range(len(scr) - 1))
            if d <= self.GIZMO_PICK_PX and d < best_d - self.RING_TIE_PX:
                best, best_d = name, d
        return best

    def gizmo_pick(self, pos) -> str | None:
        tool = self.scene.tool
        if tool == "rotate":
            return self.ring_hit(pos)
        if tool in ("move", "scale"):
            return self.gizmo_hit(pos)
        return None

    def _hot_handle(self) -> str | None:
        if self._drag is not None and self._drag.active:
            return self._drag.handle
        return self._hover

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        inner = self.inner_rect()
        clip = QPainterPath()
        radius = theme.CARD_RADIUS - 1
        clip.addRoundedRect(inner, radius, radius)
        p.setClipPath(clip)
        self._paint_background(p, inner)
        self._paint_horizon(p, inner)
        self._paint_scene(p)
        self._paint_tool_gizmo(p)
        self._paint_pen(p)
        self._paint_pivot(p)
        self._paint_texts(p, inner)
        self._paint_gizmo(p, inner)
        p.end()
        self._refine_now = False

    def _paint_background(self, p: QPainter, r: QRectF) -> None:
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0.0, QColor(theme.VIEWPORT_TOP))
        g.setColorAt(1.0, QColor(theme.VIEWPORT_BOTTOM))
        p.fillRect(r, g)

    @staticmethod
    def _shade(lam: float) -> QColor:
        grey = SHADE_MIN + SHADE_SPAN * max(0.0, min(1.0, lam))
        ink = QColor(theme.VIEWPORT_TOP)
        keep = 1.0 - SHADE_INK
        return QColor(round(grey * keep + ink.red() * SHADE_INK),
                      round(grey * keep + ink.green() * SHADE_INK),
                      round(grey * keep + ink.blue() * SHADE_INK))

    def _shade_cached(self, lam: float) -> QColor:
        grey = SHADE_MIN + SHADE_SPAN * max(0.0, min(1.0, lam))
        tag = ("ink", theme.VIEWPORT_TOP)
        ink = self._shade_cache.get(tag)
        if ink is None:
            c = QColor(theme.VIEWPORT_TOP)
            ink = self._shade_cache[tag] = (c.red(), c.green(), c.blue())
        keep = 1.0 - SHADE_INK
        rgb = (round(grey * keep + ink[0] * SHADE_INK), round(grey * keep + ink[1] * SHADE_INK),
               round(grey * keep + ink[2] * SHADE_INK))
        color = self._shade_cache.get(rgb)
        if color is None:
            if len(self._shade_cache) > 1024:
                self._shade_cache.clear()
            color = self._shade_cache[rgb] = QColor(*rgb)
        return color

    def _guide_batch(self, mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
        big = [k for k, poly in enumerate(mesh.polygons) if len(poly) > 4]
        if not big:
            return np.zeros((0, 2), int), np.zeros(0, int)
        key = (tuple(mesh.polygons), mesh.points.tobytes())

        def make() -> tuple[np.ndarray, np.ndarray]:
            edges: list = []
            owner: list[int] = []
            for k in big:
                found = self.ngon_guides(mesh, k)
                edges.extend(found)
                owner.extend([k] * len(found))
            return np.asarray(edges, int).reshape(-1, 2), np.asarray(owner, int)

        return self._cached(self._guide_batch_cache, key, make, self._MESH_TRI_LIMIT)

    REFINE_MS = 160

    def _refine(self) -> None:
        self._refine_now = True
        self.update()

    def _interactive(self) -> bool:
        if self._refine_now:
            return False
        if self._nav is not None:
            return True
        drag = self._drag
        return drag is not None and bool(getattr(drag, "active", False))

    def _guide_lines(self, view: _ObjectView) -> dict:
        mesh = view.obj.mesh
        if self._interactive() and any(len(p) > 4 for p in mesh.polygons):
            key = (tuple(mesh.polygons), mesh.points.tobytes())
            if key not in self._guide_batch_cache:
                self._refine_timer.start()
                return {}
        edges, owner = self._guide_batch(mesh)
        if not len(edges):
            return {}
        s0, s1, keep = _clip_near_many(view.cam[edges[:, 0]], view.cam[edges[:, 1]], self.camera.near)
        p0 = self._cam_to_screen(s0).tolist()
        p1 = self._cam_to_screen(s1).tolist()
        out: dict = {}
        for i, k in enumerate(owner.tolist()):
            if keep[i]:
                out.setdefault(k, []).append(QLineF(p0[i][0], p0[i][1], p1[i][0], p1[i][1]))
        return out

    def _paint_horizon(self, p: QPainter, inner: QRectF) -> None:
        _pos, fwd, _right, up = self.camera.basis()
        if self.camera.ortho or up[1] < 1e-3:
            return
        cx, cy, f = self._view_params()
        y = cy + f * fwd[1] / up[1]
        if inner.top() <= y <= inner.bottom():
            line_y = math.floor(y) + 0.5
            p.setPen(QPen(QColor(theme.HORIZON), 1.0))
            o = self._triad_origin(inner)
            if abs(line_y - o.y()) <= TRIAD_CLEARANCE:
                p.drawLine(QPointF(inner.left(), line_y), QPointF(o.x() - TRIAD_CLEARANCE, line_y))
                p.drawLine(QPointF(o.x() + TRIAD_CLEARANCE, line_y), QPointF(inner.right(), line_y))
            else:
                p.drawLine(QPointF(inner.left(), line_y), QPointF(inner.right(), line_y))

    def _triad_origin(self, inner: QRectF) -> QPointF:
        return QPointF(inner.right() - OVERLAY_INSET - 32.0, inner.top() + OVERLAY_TOP + 44.0)

    def _light_dir(self) -> np.ndarray:
        _pos, fwd, right, up = self.camera.basis()
        v = -fwd + up * 0.5 - right * 0.15
        return v / np.linalg.norm(v)

    def _is_closed(self, view: _ObjectView) -> bool:
        if isinstance(view.topo, _Topology):
            return view.topo.closed
        return bool(view.edge_faces) and all(len(faces) == 2 for faces in view.edge_faces.values())

    def _eye_inside(self, view: _ObjectView) -> bool:
        if not len(view.world):
            return False
        eye = self.camera.position()
        return bool(np.all(eye >= view.world.min(axis=0)) and np.all(eye <= view.world.max(axis=0)))

    def _scene_signature(self) -> tuple:
        objects = tuple((obj.world_points().tobytes(), tuple(obj.mesh.polygons))
                        for obj in self.scene.render_objects())
        return self.camera.state(), objects

    def _sight_clear(self, points) -> np.ndarray:
        pts = np.asarray(points, float).reshape(-1, 3)
        if not len(pts):
            return np.ones(0, bool)
        return self._cached(self._sight_cache, (self._scene_signature(), pts.tobytes()),
                            lambda: self._trace_sight(pts))

    SIGHT_BUDGET = 12_000_000
    SIGHT_CHUNK = 262_144

    def _scene_triangles(self) -> np.ndarray:
        parts = []
        for obj in self.scene.render_objects():
            tri, _owner = self._mesh_triangles(obj.mesh)
            if len(tri):
                parts.append(obj.world_points()[tri])
        if not parts:
            return np.zeros((0, 3, 3))
        return np.concatenate(parts)

    SIGHT_GRID = 64
    SIGHT_BIG_CELLS = 1024

    def _sight_pairs(self, pts: np.ndarray, tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        count, total = len(pts), len(tris)
        cam_p = self.camera.to_camera(pts)
        cam_t = self.camera.to_camera(tris.reshape(-1, 3)).reshape(total, 3, 3)
        if self.camera.ortho:
            fp = cam_p[:, :2]
            ft = cam_t[:, :, :2]
            good_p = np.isfinite(fp).all(axis=1)
            good_t = np.isfinite(ft).all(axis=(1, 2))
        else:
            zp = cam_p[:, 2]
            zt = cam_t[:, :, 2]
            good_p = zp > 1e-6
            good_t = (zt > 1e-6).all(axis=1)
            fp = cam_p[:, :2] / np.where(good_p, zp, 1.0)[:, None]
            ft = cam_t[:, :, :2] / np.where(zt > 1e-6, zt, 1.0)[:, :, None]
            good_p &= np.isfinite(fp).all(axis=1)
            good_t &= np.isfinite(ft).all(axis=(1, 2))
        all_t = np.arange(total)
        bad_p = np.flatnonzero(~good_p)
        bad_t = np.flatnonzero(~good_t)
        si = [np.repeat(bad_p, total)]
        ti = [np.tile(all_t, len(bad_p))]
        gp = np.flatnonzero(good_p)
        if len(gp):
            si.append(np.repeat(gp, len(bad_t)))
            ti.append(np.tile(bad_t, len(gp)))
        gt = np.flatnonzero(good_t)
        if len(gp) and len(gt):
            sp = fp[gp]
            lo = sp.min(axis=0)
            hi = sp.max(axis=0)
            span = float((hi - lo).max())
            margin = 1e-6 * max(1.0, span) + 1e-9
            g = self.SIGHT_GRID
            cell = max(span / g, 1e-12)
            gx = max(1, min(g, int((hi[0] - lo[0]) / cell) + 1))
            gy = max(1, min(g, int((hi[1] - lo[1]) / cell) + 1))
            tmin = ft[gt].min(axis=1) - margin
            tmax = ft[gt].max(axis=1) + margin
            hit = (tmax[:, 0] >= lo[0]) & (tmax[:, 1] >= lo[1]) & (tmin[:, 0] <= hi[0]) & (tmin[:, 1] <= hi[1])
            gt, tmin, tmax = gt[hit], tmin[hit], tmax[hit]
            x0 = np.clip(np.floor((tmin[:, 0] - lo[0]) / cell), 0, gx - 1).astype(int)
            x1 = np.clip(np.floor((tmax[:, 0] - lo[0]) / cell), 0, gx - 1).astype(int)
            y0 = np.clip(np.floor((tmin[:, 1] - lo[1]) / cell), 0, gy - 1).astype(int)
            y1 = np.clip(np.floor((tmax[:, 1] - lo[1]) / cell), 0, gy - 1).astype(int)
            nx = x1 - x0 + 1
            ncell = nx * (y1 - y0 + 1)
            big = ncell > self.SIGHT_BIG_CELLS
            if big.any():
                bt = gt[big]
                si.append(np.repeat(gp, len(bt)))
                ti.append(np.tile(bt, len(gp)))
                small = ~big
                gt, x0, y0, nx, ncell = gt[small], x0[small], y0[small], nx[small], ncell[small]
            if len(gt):
                owner = np.repeat(np.arange(len(gt)), ncell)
                local = np.arange(len(owner)) - np.repeat(np.cumsum(ncell) - ncell, ncell)
                cells = (y0[owner] + local // nx[owner]) * gx + x0[owner] + local % nx[owner]
                order = np.argsort(cells, kind="stable")
                cells = cells[order]
                tri_sorted = gt[owner[order]]
                pc = np.clip(np.floor((sp - lo) / cell), 0, [gx - 1, gy - 1]).astype(int)
                pcell = pc[:, 1] * gx + pc[:, 0]
                start = np.searchsorted(cells, pcell, "left")
                stop = np.searchsorted(cells, pcell, "right")
                lens = stop - start
                n = int(lens.sum())
                if n:
                    base = np.repeat(start - (np.cumsum(lens) - lens), lens)
                    si.append(np.repeat(gp, lens))
                    ti.append(tri_sorted[base + np.arange(n)])
        return np.concatenate(si).astype(int), np.concatenate(ti).astype(int)

    def _trace_sight(self, pts: np.ndarray) -> np.ndarray:
        count = len(pts)
        clear = np.ones(count, bool)
        tris = self._scene_triangles()
        total = len(tris)
        if not total:
            return clear
        si, ti = self._sight_pairs(pts, tris)
        if not len(si) or len(si) > self.SIGHT_BUDGET:
            return clear
        pos, fwd, _right, _up = self.camera.basis()
        a = tris[:, 0]
        e1 = tris[:, 1] - a
        e2 = tris[:, 2] - a
        ortho = bool(self.camera.ortho)
        if ortho:
            depth = (pts - pos) @ fwd
            origins = pts - fwd[None, :] * depth[:, None]
            p_vec = np.cross(fwd[None, :], e2)
            det_all = np.einsum("ij,ij->i", e1, p_vec)
            z_vec = np.cross(e1, fwd[None, :])
            n_vec = np.cross(e1, e2)
            c_u = np.einsum("ij,ij->i", a, p_vec)
            c_v = np.einsum("ij,ij->i", a, z_vec)
            c_t = np.einsum("ij,ij->i", a, n_vec)
        else:
            vec = pts - pos
            depth = np.linalg.norm(vec, axis=1)
            dirs = vec / np.where(depth > 1e-9, depth, 1.0)[:, None]
            s = pos[None, :] - a
            n_vec = np.cross(e1, e2)
            w_vec = np.cross(e2, s)
            q_vec = np.cross(s, e1)
            t_num = np.einsum("ij,ij->i", e2, q_vec)
        active = depth > 1e-9
        blocked = np.zeros(count, bool)
        step = self.SIGHT_CHUNK
        for lo in range(0, len(si), step):
            sa, ta = si[lo:lo + step], ti[lo:lo + step]
            d = depth[sa]
            if ortho:
                o = origins[sa]
                det = det_all[ta]
                un = np.einsum("ij,ij->i", o, p_vec[ta]) - c_u[ta]
                vn = np.einsum("ij,ij->i", o, z_vec[ta]) - c_v[ta]
                tn = np.einsum("ij,ij->i", o, n_vec[ta]) - c_t[ta]
            else:
                dd = dirs[sa]
                det = -np.einsum("ij,ij->i", dd, n_vec[ta])
                un = np.einsum("ij,ij->i", dd, w_vec[ta])
                vn = np.einsum("ij,ij->i", dd, q_vec[ta])
                tn = t_num[ta]
            ok = np.abs(det) >= 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            u = un * inv
            v = vn * inv
            t = tn * inv
            ok &= (u >= -1e-9) & (u <= 1 + 1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
            ok &= (t > 1e-9) & (t < d - (1e-6 * d + 1e-9))
            blocked[sa[ok]] = True
        return ~(blocked & active)

    def _contour_edges(self, view: _ObjectView) -> list:
        out = []
        for edge, faces in view.edge_faces.items():
            flags = [bool(view.front[k]) for k in faces]
            if any(flags) and not all(flags) or len(flags) == 1:
                out.append(edge)
        return out

    def _visible_edge_lines(self, view: _ObjectView, edges) -> list[tuple[tuple[int, int], QLineF]]:
        edge_list = [tuple(e) for e in edges]
        if not edge_list:
            return []
        n = self.OCCLUSION_PIECES
        if self._interactive():
            n = 1
            self._refine_timer.start()
        steps = np.linspace(0.0, 1.0, n + 1)
        mids = (steps[:-1] + steps[1:]) / 2
        e = np.asarray(edge_list, int)
        wa, wb = view.world[e[:, 0]], view.world[e[:, 1]]
        samples = wa[:, None, :] + (wb - wa)[:, None, :] * mids[None, :, None]
        clear = self._sight_clear(samples.reshape(-1, 3)).reshape(len(edge_list), n)
        ca, cb = view.cam[e[:, 0]], view.cam[e[:, 1]]
        pad = np.zeros((len(edge_list), n + 2), np.int8)
        pad[:, 1:-1] = clear
        step = np.diff(pad, axis=1)
        rows, first = np.nonzero(step == 1)
        _rows, last = np.nonzero(step == -1)
        if not len(rows):
            return []
        span = cb[rows] - ca[rows]
        s0 = ca[rows] + span * steps[first][:, None]
        s1 = ca[rows] + span * steps[last][:, None]
        near = self.camera.near
        z0, z1 = s0[:, 2], s1[:, 2]
        keep = (z0 >= near) | (z1 >= near)
        a0 = s0 + (s1 - s0) * ((near - z0) / np.where(z1 == z0, 1.0, z1 - z0))[:, None]
        b1 = s1 + (s0 - s1) * ((near - z1) / np.where(z0 == z1, 1.0, z0 - z1))[:, None]
        s0 = np.where((z0 < near)[:, None], a0, s0)
        s1 = np.where((z1 < near)[:, None], b1, s1)
        p0 = self._cam_to_screen(s0).tolist()
        p1 = self._cam_to_screen(s1).tolist()
        return [(edge_list[r], QLineF(p0[i][0], p0[i][1], p1[i][0], p1[i][1]))
                for i, r in enumerate(rows.tolist()) if keep[i]]

    def _paint_scene(self, p: QPainter) -> None:
        scene = self.scene
        light = self._light_dir()
        outline = QPen(QColor(theme.POLY_OUTLINE), 1.0)
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        items: list[tuple[float, int, tuple]] = []
        active_view: _ObjectView | None = None
        guide_pen = QPen(QColor(theme.ACCENT), 1.4)
        guide_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        select_fill = QColor(theme.SELECT_FRONT)
        select_fill.setAlpha(100)
        select_pen = QPen(QColor(theme.SELECT_FRONT), 2.0)
        select_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        back_fill = QColor(theme.SELECT_BACK)
        back_fill.setAlpha(100)
        back_pen = QPen(QColor(theme.SELECT_BACK), 2.0)
        back_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        others: list[_ObjectView] = []
        extra = {id(o) for o in scene.extra_selected} if scene.mode == "model" and scene.object_selected else ()
        for obj in scene.render_objects():
            view = self._object_view(obj)
            is_active = obj is scene.active
            if is_active:
                active_view = view
            elif extra and id(obj) in extra:
                others.append(view)
            mesh = obj.mesh
            closed = self._is_closed(view)
            hide_back = closed and not self._eye_inside(view)
            picked = scene.selected_polygons if is_active and scene.mode == "polygons" else ()
            count = len(mesh.polygons)
            dots = view.normals @ light if count else np.zeros(0)
            lams = np.where(view.front, dots, -dots * 0.55).tolist()
            fronts = np.asarray(view.front, bool).tolist()
            far = None
            if not closed and count and isinstance(view.topo, _Topology):
                far = np.full(count, -np.inf)
                np.maximum.at(far, view.topo.pid, view.cam[view.topo.flat, 2])
                far = far.tolist()
            guides = self._guide_lines(view)
            for k in range(count):
                if hide_back and not fronts[k]:
                    continue
                poly, depth = self._poly_screen(view, k)
                if poly is None:
                    continue
                if not closed:
                    depth = far[k] if far is not None else float(view.cam[list(mesh.polygons[k]), 2].max())
                items.append((depth, len(items), ("poly", poly, self._shade_cached(lams[k]))))
                if k in picked:
                    if fronts[k]:
                        items.append((depth, len(items), ("selected", poly, select_fill, select_pen)))
                    else:
                        items.append((depth, len(items), ("selected", poly, back_fill, back_pen)))
                for line in guides.get(k, ()):
                    items.append((depth, len(items), ("line", line, guide_pen)))
            items.extend(self._loose_edge_items(view, len(items)))
            if obj.kind == "null":
                items.extend(self._null_items(obj, len(items)))
        if (active_view is None and scene.mode != "model" and scene.is_editable(scene.active)
                and scene.active in scene.objects):
            active_view = self._object_view(scene.active)
        items.extend(self._world_axis_items(len(items)))
        items.sort(key=lambda it: (-it[0], it[1]))
        p.setPen(outline)
        for _depth, _seq, item in items:
            if item[0] == "poly":
                p.setPen(outline)
                p.setBrush(item[2])
                p.drawPolygon(item[1])
            elif item[0] == "selected":
                p.setPen(item[3])
                p.setBrush(item[2])
                p.drawPolygon(item[1])
            elif item[0] == "line":
                p.setPen(item[2])
                p.drawLine(item[1])
            else:
                p.setPen(item[2])
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPolyline(item[1])
        for view in others:
            self._paint_overlays(p, view)
        if active_view is not None:
            self._paint_overlays(p, active_view)

    LINE_PIECES = 6
    OCCLUSION_PIECES = 4

    def _null_axes(self, obj: SceneObject, orientation: str) -> np.ndarray:
        if orientation == "Camera":
            _pos, fwd, right, up = self.camera.basis()
            return np.array([right, up, -fwd], float)
        lin = obj.world_linear()
        x, y, z = lin[:, 0], lin[:, 1], lin[:, 2]
        if orientation == "ZY":
            return np.array([z, y, x], float)
        if orientation == "XZ":
            return np.array([x, z, y], float)
        return np.array([x, y, z], float)

    def _null_items(self, obj: SceneObject, seq0: int) -> list[tuple[float, int, tuple]]:
        params = obj.params
        display = str(params.get("display", "Dot"))
        radius = float(params.get("radius", 10.0))
        aspect = float(params.get("aspect_ratio", 1.0))
        if display == "None" or radius <= 0.0:
            return []
        scene = self.scene
        selected = scene.mode == "model" and scene.object_selected and (
            obj is scene.active or any(o is obj for o in scene.extra_selected))
        color = QColor(theme.SELECT_FRONT if selected else theme.WIRE)
        near = self.camera.near
        center = obj.world_position()
        if display in ("Dot", "Point"):
            cam = self.camera.to_camera(center[None, :])
            if cam[0, 2] <= near:
                return []
            s = self._cam_to_screen(cam)[0]
            pen = QPen(color, 7.0 if display == "Dot" else 3.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            return [(float(cam[0, 2]), seq0, ("line", QLineF(s[0], s[1], s[0], s[1] + 0.01), pen))]
        segs = null_segments(display, radius, aspect)
        if not len(segs):
            return []
        axes = self._null_axes(obj, str(params.get("orientation", "Camera")))
        world = center[None, None, :] + np.einsum("sjk,kc->sjc", segs, axes)
        cam = self.camera.to_camera(world.reshape(-1, 3)).reshape(-1, 2, 3)
        s0, s1, keep = _clip_near_many(cam[:, 0], cam[:, 1], near)
        p0, p1 = self._cam_to_screen(s0), self._cam_to_screen(s1)
        pen = QPen(color, 2.0 if selected else 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        out = []
        for i in range(len(segs)):
            if keep[i]:
                depth = float((s0[i, 2] + s1[i, 2]) / 2.0)
                out.append((depth, seq0 + len(out),
                            ("line", QLineF(p0[i, 0], p0[i, 1], p1[i, 0], p1[i, 1]), pen)))
        return out

    def _loose_edge_items(self, view: _ObjectView, seq0: int) -> list[tuple[float, int, tuple]]:
        scene = self.scene
        mesh = view.obj.mesh
        if not mesh.loose_edges:
            return []
        is_active = view.obj is scene.active
        whole = scene.mode == "model" and scene.object_selected and (
            is_active or any(o is view.obj for o in scene.extra_selected))
        light = QPen(QColor(theme.WIRE), 1.4)
        warm = QPen(QColor(theme.SELECT_FRONT), 2.0)
        for pen in (light, warm):
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        near = self.camera.near
        pieces = self.LINE_PIECES
        edges = np.asarray(mesh.loose_edges, int).reshape(-1, 2)
        ea, eb = view.cam[edges[:, 0]], view.cam[edges[:, 1]]
        ends_ok = (ea[:, 2] > near) & (eb[:, 2] > near)
        span = np.full(len(edges), np.inf)
        if ends_ok.any():
            span[ends_ok] = np.linalg.norm(self._cam_to_screen(eb[ends_ok]) - self._cam_to_screen(ea[ends_ok]),
                                           axis=1)
        whole_edge = span < self.SHORT_LINE_PX
        count = np.where(whole_edge, 1, pieces)
        owner = np.repeat(np.arange(len(edges)), count)
        local = np.arange(len(owner)) - np.repeat(np.cumsum(count) - count, count)
        t0 = local / count[owner]
        t1 = (local + 1) / count[owner]
        d = (eb - ea)[owner]
        s0, s1, keep = _clip_near_many(ea[owner] + d * t0[:, None], ea[owner] + d * t1[:, None], near)
        p0, p1 = self._cam_to_screen(s0).tolist(), self._cam_to_screen(s1).tolist()
        depth = ((s0[:, 2] + s1[:, 2]) / 2.0).tolist()
        keep = keep.tolist()
        selected = scene.selected_edges if is_active and scene.mode == "edges" else ()
        pens = [warm if whole or edge in selected else light for edge in mesh.loose_edges]
        out: list[tuple[float, int, tuple]] = []
        for i, j in enumerate(owner.tolist()):
            if keep[i]:
                out.append((depth[i], seq0 + len(out),
                            ("line", QLineF(p0[i][0], p0[i][1], p1[i][0], p1[i][1]), pens[j])))
        return out

    SHORT_LINE_PX = 24.0

    def _world_axis_items(self, seq0: int) -> list[tuple[float, int, tuple]]:
        out: list[tuple[float, int, tuple]] = []
        length = self.WORLD_AXIS_LENGTH
        width = max(1.0, self.width() / 1100.0)
        near = self.camera.near
        _pos, _fwd, right, _up = self.camera.basis()
        sides = (np.array([0.0, 0.0, 1.0]), right, np.array([1.0, 0.0, 0.0]))
        ts = np.linspace(0.0, 1.0, self.AXIS_PIECES + 1)
        for axis, color, side in zip(np.eye(3), GIZMO_AXIS_COLORS, sides):
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            cam = self.camera.to_camera(np.outer(ts * length, axis))
            a, b = cam[:-1], cam[1:]
            za, zb = a[:, 2], b[:, 2]
            keep = ((za >= near) | (zb >= near)).tolist()
            ca = a + (b - a) * ((near - za) / np.where(zb == za, 1.0, zb - za))[:, None]
            cb = b + (a - b) * ((near - zb) / np.where(za == zb, 1.0, za - zb))[:, None]
            a = np.where((za < near)[:, None], ca, a)
            b = np.where((zb < near)[:, None], cb, b)
            sa = self._cam_to_screen(a).tolist()
            sb = self._cam_to_screen(b).tolist()
            mid = ((a[:, 2] + b[:, 2]) / 2).tolist()
            for i in range(self.AXIS_PIECES):
                if keep[i]:
                    out.append((mid[i], seq0 + len(out), ("line", QLineF(*sa[i], *sb[i]), pen)))
            tip, back = axis * length, axis * (length * 0.952)
            arms = self.camera.to_camera(np.array([back + side * length * 0.032, tip,
                                                   back - side * length * 0.032]))
            ends = cam[[0, -1]]
            shaft_px = (float(np.linalg.norm(np.subtract(*self._cam_to_screen(ends))))
                        if (ends[:, 2] > near).all() else math.inf)
            if (arms[:, 2] > near).all() and shaft_px > 12.0:
                s = self._cam_to_screen(arms)
                head = QPen(QColor(color), width)
                head.setCapStyle(Qt.PenCapStyle.RoundCap)
                head.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                out.append((float(arms[1, 2]) - 0.01, seq0 + len(out),
                            ("polyline", QPolygonF([QPointF(*pt) for pt in s]), head)))
        return out

    def _paint_overlays(self, p: QPainter, view: _ObjectView) -> None:
        scene = self.scene
        mode = scene.mode
        warm = QColor(theme.SELECT_FRONT)
        if mode == "model":
            if scene.object_selected:
                pen = QPen(warm, 2.0)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                for _edge, line in self._visible_edge_lines(view, self._contour_edges(view)):
                    p.drawLine(line)
            return
        if mode == "polygons":
            return
        if mode == "edges":
            light = QColor(theme.WIRE)
            light.setAlpha(225)
            pen = QPen(light, 1.3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            selected = scene.selected_edges
            lines = self._visible_edge_lines(view, view.visible_edges)
            for edge, line in lines:
                if edge not in selected:
                    p.drawLine(line)
            pen = QPen(warm, 2.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for edge, line in lines:
                if edge in selected:
                    p.drawLine(line)
            return
        shown = np.nonzero(view.visible_points & view.in_front)[0]
        shown = shown[self._sight_clear(view.world[shown])]
        selected = scene.selected_points
        p.setPen(QPen(QColor(theme.POINT_BORDER), 1.0))
        p.setBrush(QColor(theme.POINT_FILL))
        for i in shown:
            if int(i) not in selected:
                x, y = view.screen[i]
                p.drawRect(QRectF(x - 2.5, y - 2.5, 5.0, 5.0))
        p.setPen(QPen(QColor(theme.SELECT_FRONT_DARK), 1.0))
        p.setBrush(warm)
        for i in shown:
            if int(i) in selected:
                x, y = view.screen[i]
                p.drawRect(QRectF(x - 3.5, y - 3.5, 7.0, 7.0))

    def _paint_tool_gizmo(self, p: QPainter) -> None:
        tool = self.scene.tool
        if tool == "move":
            self._paint_move_gizmo(p)
        elif tool == "scale":
            self._paint_scale_gizmo(p)
        elif tool == "rotate":
            self._paint_rotate_gizmo(p)

    def _paint_move_gizmo(self, p: QPainter) -> None:
        geo = self._gizmo_geometry()
        if geo is None:
            return
        active = self._drag.handle if self._drag is not None and self._drag.active else None
        hot = active or self._hover
        self._paint_plane_handles(p, geo, hot)
        order = sorted((a for a in AXES if a in geo), key=lambda a: -geo["depth"][a])
        for axis in order:
            (sx, sy), (ex, ey) = geo[axis]
            color = QColor(theme.GIZMO_HOVER if hot == axis else GIZMO_AXIS_COLORS[AXES.index(axis)])
            pen = QPen(color, 2.6 if hot == axis else 2.0)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            n = math.hypot(ex - sx, ey - sy)
            p.setBrush(color)
            if n < 3.0:
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(ex, ey), 3.0, 3.0)
                continue
            ux, uy = (ex - sx) / n, (ey - sy) / n
            gap = min(6.5, n)
            p.setPen(pen)
            p.drawLine(QPointF(sx + ux * gap, sy + uy * gap), QPointF(ex, ey))
            p.setPen(Qt.PenStyle.NoPen)
            head = self.GIZMO_HEAD_PX * min(1.0, 0.4 + n / self.GIZMO_PX)
            half = head * 0.38
            p.drawPolygon(QPolygonF([
                QPointF(ex + ux * head, ey + uy * head),
                QPointF(ex - uy * half, ey + ux * half),
                QPointF(ex + uy * half, ey - ux * half),
            ]))
        cx, cy = geo["center"]
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(theme.SHADOW), 3.2))
        p.drawEllipse(QPointF(cx, cy), 5.6, 5.6)
        p.setPen(QPen(QColor(theme.GIZMO_HOVER if hot in ("center", "free") else theme.ICON_STROKE), 1.6))
        p.drawEllipse(QPointF(cx, cy), 5.6, 5.6)

    def _paint_plane_handles(self, p: QPainter, geo: dict, hot: str | None) -> None:
        planes = geo.get("planes", {})
        depths = geo.get("plane_depth", {})
        for name in sorted(planes, key=lambda n: (n == hot, -depths.get(n, 0.0))):
            quad = planes[name]
            is_hot = hot == name
            base = QColor(theme.GIZMO_HOVER if is_hot else GIZMO_AXIS_COLORS[AXES.index(name[-1])])
            fill = QColor(base)
            fill.setAlpha(200 if is_hot else 120)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawPolygon(QPolygonF([QPointF(float(a), float(b)) for a, b in quad]))
            pen = QPen(base, 2.6 if is_hot else 2.0)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(QPolygonF([QPointF(float(quad[1][0]), float(quad[1][1])),
                                      QPointF(float(quad[2][0]), float(quad[2][1])),
                                      QPointF(float(quad[3][0]), float(quad[3][1]))]))

    def _paint_scale_gizmo(self, p: QPainter) -> None:
        geo = self._gizmo_geometry()
        if geo is None:
            return
        hot = self._hot_handle()
        order = sorted((a for a in AXES if a in geo), key=lambda a: -geo["depth"][a])
        for axis in order:
            (sx, sy), (ex, ey) = geo[axis]
            color = QColor(theme.GIZMO_HOVER if hot == axis else GIZMO_AXIS_COLORS[AXES.index(axis)])
            pen = QPen(color, 2.6 if hot == axis else 2.0)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRect(QRectF(ex - 3.5, ey - 3.5, 7.0, 7.0))
        cx, cy = geo["center"]
        p.setPen(QPen(QColor(theme.SHADOW), 1.6))
        p.setBrush(QColor(theme.GIZMO_HOVER if hot == "center" else theme.ICON_STROKE))
        p.drawRect(QRectF(cx - 4.0, cy - 4.0, 8.0, 8.0))

    def _paint_rotate_gizmo(self, p: QPainter) -> None:
        rings = self._rotate_frame()
        if not rings:
            return
        hot = self._hot_handle()
        for name in sorted(rings, key=lambda n: n == hot):
            scr = rings[name][0]
            if hot == name:
                color, width = QColor(theme.GIZMO_HOVER), 2.6
            else:
                base = theme.TEXT_BRIGHT if name == "view" else GIZMO_AXIS_COLORS[AXES.index(name)]
                color, width = QColor(base), 2.0
            p.setPen(QPen(color, width))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(QPolygonF([QPointF(float(x), float(y)) for x, y in scr]))

    def _screen_segment(self, a, b) -> QLineF | None:
        cam = self.camera.to_camera(np.vstack([a, b]))
        seg = _clip_segment_near(cam[0], cam[1], self.camera.near)
        if seg is None:
            return None
        s = self._cam_to_screen(np.vstack(seg))
        return QLineF(s[0, 0], s[0, 1], s[1, 0], s[1, 1])

    def pen_preview_world(self) -> np.ndarray | None:
        hover = self._pen_hover
        if hover is None or not self.pen_mode():
            return None
        kind, value = hover
        if kind == "place":
            return np.asarray(value, float)
        if kind == "start":
            other, i = value
            if other not in self.scene.objects or not 0 <= int(i) < len(other.mesh.points):
                return None
            return other.world_points()[int(i)]
        obj = self.scene.active
        if obj is None or not 0 <= int(value) < len(obj.mesh.points):
            return None
        return obj.world_points()[int(value)]

    def _paint_pen(self, p: QPainter) -> None:
        if not self.pen_mode():
            return
        scene = self.scene
        obj = scene.active
        chain = [i for i in scene.pen_chain if obj is not None and 0 <= i < len(obj.mesh.points)]
        world = obj.world_points() if chain else None
        target = self.pen_preview_world()
        hover_kind = self._pen_hover[0] if self._pen_hover is not None else None
        if chain and target is not None and hover_kind != "none":
            dash = QPen(QColor(theme.TEXT_PRIMARY), 1.3, Qt.PenStyle.DashLine)
            dash.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(dash)
            line = self._screen_segment(world[chain[-1]], target)
            if line is not None:
                p.drawLine(line)
            if scene.tool == "pen" and len(chain) >= 2 and hover_kind != "close":
                faint = QColor(theme.TEXT_PRIMARY)
                faint.setAlpha(90)
                dash.setColor(faint)
                p.setPen(dash)
                line = self._screen_segment(target, world[chain[0]])
                if line is not None:
                    p.drawLine(line)
        if chain and scene.mode != "points":
            xy = self.project_world(world[chain])
            p.setPen(QPen(QColor(theme.POINT_BORDER), 1.0))
            p.setBrush(QColor(theme.TEXT_PRIMARY))
            for x, y in xy:
                if np.isfinite(x) and np.isfinite(y):
                    p.drawRect(QRectF(x - 2.5, y - 2.5, 5.0, 5.0))
        if chain and hover_kind == "close":
            x, y = self.project_world(world[chain[:1]])[0]
            if np.isfinite(x) and np.isfinite(y):
                p.setPen(QPen(QColor(theme.SHADOW), 1.0))
                p.setBrush(QColor(theme.GIZMO_HOVER))
                p.drawRect(QRectF(x - 5.0, y - 5.0, 10.0, 10.0))
        elif not chain and target is not None and hover_kind in ("place", "start"):
            x, y = self.project_world([target])[0]
            if np.isfinite(x) and np.isfinite(y):
                p.setPen(QPen(QColor(theme.TEXT_PRIMARY), 1.0))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(x, y), 3.0, 3.0)

    def pivot_screen(self) -> tuple[float, float] | None:
        nav = self._nav
        if nav is None:
            return None
        xy = self.project_world([nav.pivot])[0]
        if not np.all(np.isfinite(xy)):
            return None
        return float(xy[0]), float(xy[1])

    def _paint_pivot(self, p: QPainter) -> None:
        at = self.pivot_screen()
        if at is None:
            return
        x, y = at
        ticks = [(QPointF(x + dx * 5.0, y + dy * 5.0), QPointF(x + dx * 10.0, y + dy * 10.0))
                 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        for pen_w, color in ((3.4, QColor(theme.SHADOW)), (1.4, QColor(theme.TEXT_BRIGHT))):
            pen = QPen(color, pen_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for a, b in ticks:
                p.drawLine(a, b)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.SHADOW))
        p.drawEllipse(QPointF(x, y), 3.6, 3.6)
        p.setBrush(QColor(theme.TEXT_BRIGHT))
        p.drawEllipse(QPointF(x, y), 2.3, 2.3)

    @staticmethod
    def _paint_pill(p: QPainter, r: QRectF) -> None:
        p.setPen(QPen(QColor(theme.HAIRLINE), 1.0))
        p.setBrush(QColor(theme.OVERLAY_BG))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), r.height() / 2, r.height() / 2)

    def hud_rect(self, inner: QRectF | None = None) -> QRectF:
        if inner is None:
            inner = self.inner_rect()
        strong = self.label_font()
        strong.setWeight(QFont.Weight.DemiBold)
        hud_w = QFontMetricsF(strong).horizontalAdvance(self.hud_text)
        icon_px = round(theme.HUD_H * 0.6)
        return QRectF(inner.left() + theme.SPACE_3, inner.bottom() - theme.SPACE_3 - theme.HUD_H,
                      theme.SPACE_3 + hud_w + 6 + icon_px + theme.SPACE_2, theme.HUD_H)

    def _paint_texts(self, p: QPainter, inner: QRectF) -> None:
        strong = self.label_font()
        strong.setWeight(QFont.Weight.DemiBold)
        sfm = QFontMetricsF(strong)
        text_h = sfm.height()
        p.setFont(strong)
        row_y = inner.top() + OVERLAY_INSET
        name_w = sfm.horizontalAdvance(self.view_name)
        cx = inner.center().x()
        p.setPen(QColor(theme.TEXT_SECONDARY))
        p.drawText(QRectF(cx - name_w / 2 - 1, row_y, name_w + 2, theme.GHOST_BUTTON_H),
                   Qt.AlignmentFlag.AlignCenter, self.view_name)
        if self.camera_name:
            badge = round(text_h * 0.78)
            tw = sfm.horizontalAdvance(self.camera_name)
            plate = QRectF(cx + name_w / 2 + theme.SPACE_2,
                           row_y + (theme.GHOST_BUTTON_H - theme.HUD_H) / 2,
                           tw + 3 + badge + 2 * theme.SPACE_2, theme.HUD_H)
            self._paint_pill(p, plate)
            p.setPen(QColor(theme.TEXT_PRIMARY))
            p.drawText(QRectF(plate.left() + theme.SPACE_2, plate.top(), tw + 1, plate.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.camera_name)
            icons.render(p, QRectF(plate.left() + theme.SPACE_2 + tw + 3,
                                   plate.top() + (plate.height() - badge) / 2, badge, badge),
                         "viewport_camera_badge")
        hud_w = sfm.horizontalAdvance(self.hud_text)
        icon_px = round(theme.HUD_H * 0.6)
        hud = self.hud_rect(inner)
        self._paint_pill(p, hud)
        p.setPen(QColor(theme.TEXT_PRIMARY))
        p.drawText(QRectF(hud.left() + theme.SPACE_3, hud.top(), hud_w + 1, hud.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.hud_text)
        self._paint_tool_glyph(p, QRectF(hud.left() + theme.SPACE_3 + hud_w + 6,
                                         hud.top() + (hud.height() - icon_px) / 2, icon_px, icon_px),
                               QColor(theme.ICON_TOOL), self._hud_tool)

    @classmethod
    def _paint_tool_glyph(cls, p: QPainter, r: QRectF, c: QColor, tool: str) -> None:
        if tool == "move":
            cls._paint_move_glyph(p, r, c)
            return
        if tool in PEN_TOOLS:
            cls._paint_pen_glyph(p, r, c, tool)
            return
        cx, cy, h = r.center().x(), r.center().y(), r.width() / 2
        pen = QPen(c, max(1.0, r.width() / 10))
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if tool == "rotate":
            p.drawArc(QRectF(cx - h * 0.8, cy - h * 0.8, h * 1.6, h * 1.6), 60 * 16, 280 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            tip = QPointF(cx + h * 0.4, cy - h * 0.69)
            p.drawPolygon(QPolygonF([QPointF(tip.x() + h * 0.5, tip.y()),
                                     QPointF(tip.x() - h * 0.1, tip.y() - h * 0.42),
                                     QPointF(tip.x() - h * 0.1, tip.y() + h * 0.42)]))
        elif tool == "scale":
            p.drawRect(QRectF(cx - h * 0.85, cy - h * 0.1, h * 0.95, h * 0.95))
            p.drawLine(QPointF(cx - h * 0.2, cy + h * 0.2), QPointF(cx + h * 0.8, cy - h * 0.8))
            p.drawLine(QPointF(cx + h * 0.8, cy - h * 0.8), QPointF(cx + h * 0.25, cy - h * 0.8))
            p.drawLine(QPointF(cx + h * 0.8, cy - h * 0.8), QPointF(cx + h * 0.8, cy - h * 0.25))
        else:
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawEllipse(QPointF(cx, cy), h * 0.8, h * 0.8)

    @staticmethod
    def _paint_pen_glyph(p: QPainter, r: QRectF, c: QColor, tool: str) -> None:
        x0, y0, w = r.left(), r.top(), r.width()

        def pt(u: float, v: float) -> QPointF:
            return QPointF(x0 + u * w, y0 + v * w)

        pen = QPen(c, max(1.0, w / 11))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if tool == "pen":
            p.drawPolygon(QPolygonF([pt(0.05, 0.95), pt(0.05, 0.55), pt(0.45, 0.95)]))
        p.setBrush(c)
        p.drawPolygon(QPolygonF([pt(0.2, 0.8), pt(0.3, 0.5), pt(0.8, 0.0), pt(1.0, 0.2), pt(0.5, 0.7)]))

    @staticmethod
    def _paint_move_glyph(p: QPainter, r: QRectF, c: QColor) -> None:
        cx, cy = r.center().x(), r.center().y()
        h = r.width() / 2
        pen = QPen(c, max(1.0, r.width() / 10))
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawLine(QPointF(cx - h * 0.7, cy), QPointF(cx + h * 0.7, cy))
        p.drawLine(QPointF(cx, cy - h * 0.7), QPointF(cx, cy + h * 0.7))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        a, b = h * 0.42, h * 0.3
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tip = QPointF(cx + dx * h, cy + dy * h)
            base = QPointF(cx + dx * (h - a), cy + dy * (h - a))
            p.drawPolygon(QPolygonF([tip, QPointF(base.x() - dy * b, base.y() - dx * b),
                                     QPointF(base.x() + dy * b, base.y() + dx * b)]))

    def _paint_gizmo(self, p: QPainter, inner: QRectF) -> None:
        size = 25.0
        o = self._triad_origin(inner)
        small = QFont(self.font())
        small.setPixelSize(11)
        small.setBold(True)
        p.setFont(small)
        lfm = QFontMetricsF(small)
        fwd = self.camera.basis()[1]
        items = [("X", (1.0, 0.0, 0.0), theme.AXIS_X), ("Y", (0.0, 1.0, 0.0), theme.AXIS_Y),
                 ("Z", (0.0, 0.0, 1.0), theme.AXIS_Z)]
        items.sort(key=lambda it: -float(np.dot(it[1], fwd)))
        for letter, vec, color in items:
            dx, dy = self.camera.direction_2d(vec)
            n = math.hypot(dx, dy)
            length = size * 0.84 * n
            ux, uy = (dx / n, dy / n) if n > 1e-6 else (0.0, 0.0)
            end = QPointF(o.x() + ux * length, o.y() + uy * length)
            if length >= 1.0:
                pen = QPen(QColor(color), 2.0)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                p.setPen(pen)
                p.drawLine(o, end)
            if length >= 4.0:
                hx, hy = -ux, -uy
                px, py = -uy, ux
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(color))
                p.drawPolygon(QPolygonF([
                    QPointF(end.x() + ux * 3.4, end.y() + uy * 3.4),
                    QPointF(end.x() + hx * 2.6 + px * 2.8, end.y() + hy * 2.6 + py * 2.8),
                    QPointF(end.x() + hx * 2.6 - px * 2.8, end.y() + hy * 2.6 - py * 2.8),
                ]))
            if n < 0.25:
                ux, uy = 0.7071, 0.7071
            lw = lfm.horizontalAdvance(letter)
            lc = QPointF(end.x() + ux * 9.5, end.y() + uy * 9.5)
            p.setPen(QColor(color))
            p.drawText(QPointF(lc.x() - lw / 2, lc.y() + lfm.capHeight() / 2), letter)

    def nav_pivot_point(self, pos=None) -> np.ndarray:
        mode = NAV_PIVOTS.get(self.nav_pivot, "cursor")
        cam = self.camera
        if mode == "cursor" and pos is not None:
            return self.cursor_point(pos)
        if mode == "object":
            centre = self.scene.selection_center()
            if centre is None and self.scene.active is not None:
                centre = self.scene.active.world_position()
            if centre is not None:
                return np.asarray(centre, float).copy()
        if mode == "camera" and not cam.ortho:
            return cam.position()
        return np.asarray(cam.target, float).copy()

    def set_nav_pivot(self, name: str) -> None:
        if name in NAV_PIVOTS and name != self.nav_pivot:
            self.nav_pivot = name
            self.navPivotChanged.emit(name)

    def begin_navigation(self, mode: str, pos=None, button: Qt.MouseButton | None = None) -> None:
        if mode == "pan":
            pivot = self.cursor_point(pos) if pos is not None else np.asarray(self.camera.target, float).copy()
        else:
            pivot = self.nav_pivot_point(pos)
        last = QPointF(*_xy(pos)) if pos is not None else QPointF()
        self._nav = _Nav(mode, button, last, pivot, self._view_snapshot())
        self.update()

    def end_navigation(self) -> None:
        nav, self._nav = self._nav, None
        if nav is not None and self._view_snapshot_state(nav.before) != self._view_snapshot_state(
                self._view_snapshot()):
            self._push_view(nav.before)
        self.update()

    def navigate(self, mode: str, dx: float, dy: float, pos=None) -> None:
        nav = self._nav
        cam = self.camera
        cursor = _controls().cursor
        pivot = nav.pivot if nav is not None else np.asarray(cam.target, float)
        if mode == "orbit":
            if self.view_name in FIXED_VIEWS:
                self._set_view_name("Parallel" if cam.ortho else "Perspective")
            k = float(cursor("orbit_speed")) / ORBIT_SPEED
            ox = -dx if cursor("invert_orbit_x") else dx
            oy = -dy if cursor("invert_orbit_y") else dy
            cam.orbit_about(pivot, ox * k, oy * k, clamp=cursor("orbit_style") == "turntable")
        elif mode == "pan":
            fwd = cam.basis()[1]
            invert = bool(cursor("invert_pan"))
            if nav is not None and pos is not None and invert:
                px, py = _xy(pos)
                before = self.unproject(QPointF(px - dx, py - dy), (pivot, fwd))
                after = self.unproject(QPointF(px, py), (pivot, fwd))
                if before is not None and after is not None:
                    cam.target = np.asarray(cam.target, float) + (after - before)
                else:
                    cam.pan(-dx, -dy, self.film_rect().width())
            else:
                under = self.unproject(pos, (pivot, fwd)) if nav is not None and pos is not None else None
                if under is not None:
                    cam.target = np.asarray(cam.target, float) + (pivot - under)
                else:
                    cam.pan(-dx if invert else dx, -dy if invert else dy, self.film_rect().width())
        elif mode == "zoom":
            factor = math.exp(-(dx - dy) * float(cursor("dolly_speed")))
            if NAV_PIVOTS.get(self.nav_pivot) == "camera" and not cam.ortho:
                fwd = cam.basis()[1]
                step = (1.0 - factor) * max(cam.distance, NAV_MIN_DEPTH)
                cam.target = np.asarray(cam.target, float) + fwd * step
            else:
                self._scale_view(pivot, factor)
        self.update()

    def _scale_view(self, point, factor: float) -> None:
        cam = self.camera
        point = np.asarray(point, float)
        if cam.ortho:
            d = max(cam.distance, 1e-9)
            factor = min(max(factor, MIN_DISTANCE / d), MAX_DISTANCE / d)
            if abs(factor - 1.0) > 1e-12:
                cam.scale_about(point, factor)
            return
        eye, fwd, _right, _up = cam.basis()
        reach = float(np.linalg.norm(eye - point))
        if reach > 1e-9:
            if factor < 1.0:
                factor = max(factor, min(1.0, MIN_APPROACH / reach))
            else:
                factor = min(factor, max(1.0, MAX_DISTANCE / reach))
        if abs(factor - 1.0) <= 1e-12:
            return
        new_eye = point + (eye - point) * factor
        distance = cam.distance * factor
        if factor < 1.0:
            distance = max(distance, min(cam.distance, NAV_MIN_DEPTH))
        cam.distance = min(max(distance, MIN_DISTANCE), MAX_DISTANCE)
        cam.target = new_eye + fwd * cam.distance

    def zoom_at(self, pos, notches: float) -> None:
        if not notches:
            return
        now = time.monotonic()
        if now > self._wheel_merge_until:
            self._push_view()
        self._wheel_merge_until = now + 0.6
        cursor = _controls().cursor
        point = self.cursor_point(pos) if cursor("zoom_to_cursor") else np.array(self.camera.target, float)
        self._scale_view(point, float(cursor("wheel_step")) ** notches)
        self.update()

    def _view_snapshot(self) -> tuple[str, OrbitCamera]:
        return self.view_name, self.camera.copy()

    @staticmethod
    def _view_snapshot_state(snap: tuple[str, OrbitCamera]) -> tuple:
        return snap[0], snap[1].state()

    def _push_view(self, snap: tuple[str, OrbitCamera] | None = None) -> None:
        self._view_undo.append(snap if snap is not None else self._view_snapshot())
        self._view_redo.clear()
        self._wheel_merge_until = 0.0

    def _apply_view_snapshot(self, snap: tuple[str, OrbitCamera]) -> None:
        name, cam = snap
        self.camera = cam.copy()
        self._set_view_name(name)
        self.update()

    def can_undo_view(self) -> bool:
        return bool(self._view_undo)

    def can_redo_view(self) -> bool:
        return bool(self._view_redo)

    def undo_view(self) -> bool:
        if not self._view_undo or self._nav is not None:
            return False
        self._view_redo.append(self._view_snapshot())
        self._apply_view_snapshot(self._view_undo.pop())
        self._wheel_merge_until = 0.0
        return True

    def redo_view(self) -> bool:
        if not self._view_redo or self._nav is not None:
            return False
        self._view_undo.append(self._view_snapshot())
        self._apply_view_snapshot(self._view_redo.pop())
        self._wheel_merge_until = 0.0
        return True

    def _set_view_name(self, name: str) -> None:
        if name != self.view_name:
            self.view_name = name
            self.viewChanged.emit(name)

    def _preset_camera(self, name: str, *, default: bool = False) -> OrbitCamera:
        heading, pitch, ortho = VIEW_PRESETS[name]
        cam = OrbitCamera() if default else self.camera.copy()
        if heading is not None:
            cam.heading, cam.pitch = heading, pitch
        cam.ortho = ortho
        return cam

    def set_view(self, name: str) -> None:
        if name not in VIEW_PRESETS or name == self.view_name:
            return
        self._push_view()
        self._view_states[self.view_name] = self.camera.copy()
        saved = self._view_states.get(name)
        self.camera = saved.copy() if saved is not None else self._preset_camera(name)
        self._set_view_name(name)
        self.update()

    def reset_camera(self) -> None:
        before = self._view_snapshot()
        self._nav = None
        self.camera = self._preset_camera(self.view_name, default=True)
        if self._view_snapshot_state(before) != self._view_snapshot_state(self._view_snapshot()):
            self._push_view(before)
        self.update()

    def frame_points(self, pts) -> bool:
        pts = np.atleast_2d(np.asarray(pts, float))
        if not len(pts):
            return False
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        centre = (lo + hi) / 2.0
        radius = max(float(np.linalg.norm(hi - lo)) / 2.0, MIN_FRAME_RADIUS) * FRAME_MARGIN
        film = self.film_rect()
        f = self.camera.focal * film.width()
        short = max(min(film.width(), film.height()), 1.0)
        if self.camera.ortho:
            distance = 2.0 * radius * f / short
        else:
            distance = radius / math.sin(math.atan(short / 2.0 / f))
        self._push_view()
        self.camera.target = centre
        self.camera.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, distance))
        self.update()
        return True

    def frame_all(self) -> bool:
        bounds = self.scene.world_bounds()
        return bounds is not None and self.frame_points(np.vstack(bounds))

    def frame_selection(self) -> bool:
        pts = self.scene.selection_world_points()
        return self.frame_points(pts) if len(pts) else self.frame_all()

    def frame_active(self) -> bool:
        obj = self.scene.active
        if obj is None or not len(obj.mesh.points):
            return self.frame_all()
        return self.frame_points(obj.world_points())

    def _axis_param(self, d: _Drag, pos) -> float | None:
        o, r = self._ray(pos)
        a = d.axis
        w0 = o - d.center0
        b = float(r @ a)
        denom = 1.0 - b * b
        if denom < 1e-6:
            return None
        t = (float(a @ w0) - b * float(r @ w0)) / denom
        s = t * b - float(r @ w0)
        return t if s > 0 else None

    def _plane_hit(self, point: np.ndarray, pos) -> np.ndarray | None:
        o, r = self._ray(pos)
        fwd = self.camera.basis()[1]
        denom = float(r @ fwd)
        if denom < 1e-6:
            return None
        return o + r * (float((point - o) @ fwd) / denom)

    def _ray_plane_hit(self, point: np.ndarray, normal: np.ndarray, pos) -> np.ndarray | None:
        o, r = self._ray(pos)
        denom = float(r @ normal)
        if abs(denom) < 1e-6:
            return None
        t = float((point - o) @ normal) / denom
        if t <= 0.0:
            return None
        return o + r * t

    def _begin_drag(self, handle: str, pos, pending: tuple = (), ctrl: bool = False) -> None:
        centre = self.scene.selection_center()
        if centre is None:
            return
        drag = _Drag(handle="free" if handle == "center" else handle, press=QPointF(*_xy(pos)),
                     center0=np.asarray(centre, float), pending=pending, ctrl_at_press=ctrl)
        if drag.handle.startswith("plane_"):
            drag.axis = np.eye(3)[AXES.index(drag.handle[-1])]
            drag.plane_hit0 = self._ray_plane_hit(drag.center0, drag.axis, pos)
            if drag.plane_hit0 is None:
                return
        elif drag.handle in AXES:
            i = AXES.index(drag.handle)
            drag.axis = np.eye(3)[i]
            geo = self._gizmo_geometry()
            (sx, sy), (ex, ey) = geo[drag.handle] if geo and drag.handle in geo else ((0, 0), (0, 0))
            n = math.hypot(ex - sx, ey - sy)
            t0 = self._axis_param(drag, pos) if n >= self.AXIS_FALLBACK_PX else None
            if t0 is None:
                drag.screen_dir = ((ex - sx) / n, (ey - sy) / n) if n > 1e-6 else (0.0, -1.0)
                drag.cm_per_px = (geo["length"] if geo else 1.0) / self.GIZMO_PX
            else:
                drag.t0 = t0
        else:
            drag.plane_hit0 = self._plane_hit(drag.center0, pos)
            if drag.plane_hit0 is None:
                return
        self.scene.begin_group()
        self._drag = drag

    def _begin_gizmo_drag(self, handle: str, pos) -> None:
        scene = self.scene
        obj = scene.active
        centre = scene.selection_center()
        if obj is None or centre is None:
            return
        press = QPointF(*_xy(pos))
        d = _Drag(handle=handle, press=press, center0=np.asarray(centre, float), gizmo=True, obj=obj,
                  origin_pos=obj.position.copy(), origin_rot=obj.rotation.copy(),
                  origin_scale=obj.scale.copy())
        self._capture(d)
        if scene.tool == "rotate":
            rings = self._rotate_frame() or {}
            if handle not in rings:
                return
            _scr, normal, u, v = rings[handle]
            d.axis, d.basis = normal, (u, v)
            angle = self._ring_angle(d, pos)
            if angle is None:
                return
            d.angle0 = angle
        else:
            geo = self._gizmo_geometry()
            if geo is None or (handle != "center" and handle not in geo):
                return
            cx, cy = geo["center"]
            d.screen_centre = (cx, cy)
            if handle == "center":
                base = math.hypot(press.x() - cx, press.y() - cy)
            else:
                (sx, sy), (ex, ey) = geo[handle]
                n = math.hypot(ex - sx, ey - sy)
                dx, dy = ((ex - sx) / n, (ey - sy) / n) if n > 1e-6 else (0.0, -1.0)
                d.axis = np.eye(3)[AXES.index(handle)]
                d.screen_dir = (dx, dy)
                base = (press.x() - cx) * dx + (press.y() - cy) * dy
            if abs(base) < 1e-6:
                return
            d.scale_base = base
        scene.begin_group()
        self._drag = d

    def _capture(self, d: _Drag) -> None:
        scene = self.scene
        obj = scene.active
        d.obj = obj
        d.origin_pos, d.origin_rot, d.origin_scale = obj.position.copy(), obj.rotation.copy(), obj.scale.copy()
        if scene.mode != "model":
            d.affected = scene.affected_points()
            d.origin_points = obj.mesh.points.copy()
            d.world0 = obj.world_points()[d.affected] if d.affected else None
            return
        d.objs = [(o, o.position.copy(), o.rotation.copy(), o.scale.copy(), o.world_position().copy())
                  for o in scene.transform_roots()]
        d.frame = self._gizmo_axes()

    def _begin_free_gizmo(self, pos) -> bool:
        scene = self.scene
        centre = scene.selection_center()
        if scene.active is None or centre is None:
            return False
        d = _Drag(handle="free", press=QPointF(*_xy(pos)), center0=np.asarray(centre, float), gizmo=True,
                  free=True, axis=self.view_direction())
        self._capture(d)
        d.frame = np.eye(3)
        scene.begin_group()
        self._drag = d
        return True

    def _clone_for_drag(self, d: _Drag) -> None:
        d.clone = False
        scene = self.scene
        if scene.mode != "model":
            return
        self._cloning = True
        try:
            made = scene.duplicate_objects()
        finally:
            self._cloning = False
        if not made:
            return
        d.grew = True
        if d.gizmo:
            frame = d.frame
            self._capture(d)
            d.frame = frame

    def _drag_target(self, d: _Drag, pos) -> np.ndarray | None:
        if d.handle == "free":
            hit = self._plane_hit(d.center0, pos)
            return None if hit is None else hit - d.plane_hit0
        if d.handle.startswith("plane_"):
            hit = self._ray_plane_hit(d.center0, d.axis, pos)
            if hit is None:
                return None
            delta = np.clip(hit - d.plane_hit0, -self.MAX_DRAG_CM, self.MAX_DRAG_CM)
            delta[int(np.argmax(d.axis))] = 0.0
            return delta
        if d.screen_dir is not None:
            x, y = _xy(pos)
            amount = ((x - d.press.x()) * d.screen_dir[0] + (y - d.press.y()) * d.screen_dir[1]) * d.cm_per_px
        else:
            t = self._axis_param(d, pos)
            if t is None:
                return None
            amount = t - d.t0
        return d.axis * max(-self.MAX_DRAG_CM, min(self.MAX_DRAG_CM, amount))

    @staticmethod
    def drag_threshold() -> float:
        return float(_controls().cursor("drag_threshold"))

    @staticmethod
    def click_tolerance() -> float:
        return float(_controls().cursor("click_tolerance"))

    def _update_drag(self, pos, snap: bool = False) -> None:
        d = self._drag
        if not d.active:
            delta = QPointF(*_xy(pos)) - d.press
            if abs(delta.x()) + abs(delta.y()) < self.drag_threshold():
                return
            d.active = True
            if d.clone:
                self._clone_for_drag(d)
        if d.gizmo:
            matrix = self._gizmo_matrix(d, pos, snap)
            if matrix is not None:
                self._apply_gizmo(d, matrix)
            self.update()
            return
        if d.ctrl_seen and not d.extruded:
            self._extrude_drag()
        target = self._drag_target(d, pos)
        if target is None:
            return
        step = target - d.applied
        if np.any(np.abs(step) > 1e-9):
            d.applied = target
            self.scene.move_selection(step)
        self.update()

    def _ring_angle(self, d: _Drag, pos) -> float | None:
        hit = self.unproject(pos, (d.center0, d.axis))
        if hit is None:
            return None
        u, v = d.basis
        w = hit - d.center0
        return math.atan2(float(w @ v), float(w @ u))

    def _scale_factor(self, ratio: float, shift: bool) -> float:
        if shift:
            ratio = max(round(ratio / self.SCALE_STEP) * self.SCALE_STEP, self.SCALE_STEP)
        return max(ratio, self.MIN_SCALE)

    def _gizmo_matrix(self, d: _Drag, pos, shift: bool) -> np.ndarray | None:
        if d.free:
            dx = _xy(pos)[0] - d.press.x()
            if self.scene.tool == "rotate":
                total = math.radians(dx * self.FREE_ROTATE_DEG_PER_PX)
                if shift:
                    step = math.radians(self.ROTATE_STEP)
                    total = round(total / step) * step
                return _axis_rotation(d.axis, total)
            return np.eye(3) * self._scale_factor((self.GIZMO_PX + dx) / self.GIZMO_PX, shift)
        if self.scene.tool == "rotate":
            angle = self._ring_angle(d, pos)
            if angle is None:
                return None
            total = _wrap_angle(angle - d.angle0)
            if shift:
                step = math.radians(self.ROTATE_STEP)
                total = round(total / step) * step
            return _axis_rotation(d.axis, total)
        x, y = _xy(pos)
        cx, cy = d.screen_centre
        if d.screen_dir is None:
            ratio = math.hypot(x - cx, y - cy) / d.scale_base
            return np.eye(3) * self._scale_factor(ratio, shift)
        ratio = ((x - cx) * d.screen_dir[0] + (y - cy) * d.screen_dir[1]) / d.scale_base
        vec = np.ones(3)
        vec[int(np.argmax(d.axis))] = self._scale_factor(ratio, shift)
        return np.diag(vec)

    def _apply_gizmo(self, d: _Drag, matrix: np.ndarray) -> None:
        scene = self.scene
        if scene.mode == "model":
            rotate = scene.tool == "rotate"
            world = matrix if rotate or d.frame is None else d.frame.T @ matrix @ d.frame
            items = []
            for obj, pos0, rot0, scale0, wpos0 in self._drag_objects(d):
                rot, scale, pos = rot0, scale0, pos0
                if rotate and not np.allclose(matrix, np.eye(3)):
                    local = matrix
                    if obj.parent is not None:
                        u, _s, vt = np.linalg.svd(obj.parent.world_linear())
                        frame = u @ vt
                        local = frame.T @ matrix @ frame
                    rot = _euler_xyz(local @ rotation_matrix(rot0))
                elif not rotate:
                    scale = scale0 * np.diag(matrix)
                offset = wpos0 - d.center0
                if np.any(np.abs(offset) > 1e-9):
                    shift = d.center0 + world @ offset - wpos0
                    if obj.parent is not None:
                        shift = np.linalg.solve(obj.parent.world_linear(), shift)
                    pos = pos0 + shift
                items.append((obj, pos, rot, scale))
            scene.set_transforms(items, scene.tool)
            return
        if not d.affected:
            return
        obj = d.obj
        moved = (d.world0 - d.center0) @ matrix.T + d.center0
        local = np.linalg.solve(obj.world_linear(), (moved - obj.world_position()).T).T
        if np.allclose(local, obj.mesh.points[d.affected], atol=1e-12):
            return
        scene._record(scene.tool)
        obj.mesh.points[d.affected] = local
        scene.changed.emit()

    def _restore_gizmo(self, d: _Drag) -> None:
        scene = self.scene
        if scene.mode == "model":
            scene.set_transforms([(o, p, r, s) for o, p, r, s, _w in self._drag_objects(d)], scene.tool)
        elif d.affected:
            d.obj.mesh.points[:] = d.origin_points

    @staticmethod
    def _drag_objects(d: _Drag) -> list:
        if d.objs:
            return d.objs
        if d.obj is None:
            return []
        return [(d.obj, d.origin_pos, d.origin_rot, d.origin_scale, d.center0)]

    def _ctrl_during_drag(self) -> None:
        d = self._drag
        if d is None or d.gizmo or d.ctrl_at_press or d.ctrl_seen:
            return
        d.ctrl_seen = True
        if d.active:
            self._extrude_drag()

    def _extrude_drag(self) -> None:
        d = self._drag
        if d is None or d.extruded:
            return
        d.extruded = True
        scene = self.scene
        if scene.mode == "model" or not scene.has_selection():
            return
        if scene.pen_active():
            scene.pen_finish()
            self._pen_hover = None
        applied = d.applied.copy()
        moved = bool(np.any(applied))
        if moved:
            scene.move_selection(-applied)
        d.grew = scene.extrude_selection()
        if moved:
            scene.move_selection(applied)
        self.update()

    def cancel_drag(self) -> None:
        d = self._drag
        self._pen_press = None
        if d is None:
            self.update()
            return
        recorded = bool(getattr(self.scene, "_group_recorded", False))
        if d.gizmo:
            self._restore_gizmo(d)
        if d.grew and recorded:
            self._end_drag()
            self.scene.undo()
            redo = getattr(self.scene, "_redo", None)
            if redo:
                redo.pop()
            self.scene.changed.emit()
            self.update()
            return
        if np.any(d.applied):
            self.scene.move_selection(-d.applied)
        self._end_drag()
        if recorded:
            _drop_last_undo_step(self.scene)
            self.scene.changed.emit()
        self.update()

    def _press_select(self, pos: QPointF, op: str = "select",
                      button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> None:
        scene = self.scene
        if scene.tool in TRANSFORM_TOOLS:
            handle = self.gizmo_pick(pos)
            if handle is not None:
                if scene.tool == "move":
                    self._begin_drag(handle, pos)
                else:
                    self._begin_gizmo_drag(handle, pos)
                d = self._drag
                if d is not None:
                    d.click_op = op
                    if _controls().modifier_held(self._press_mods, "extrude"):
                        if scene.mode == "model":
                            d.clone = True
                        elif scene.tool == "move":
                            d.ctrl_seen = True
                    self.update()
                    return
        self._press_state = _Press(QPointF(pos), op, button)

    def _activate_other(self, obj: SceneObject) -> None:
        scene = self.scene
        scene.set_active(obj)
        if scene.mode != "model" and not scene.is_editable(obj):
            scene.set_mode("model")

    def click_select(self, pos, op: str = "select", keep: bool = False) -> None:
        scene = self.scene
        plain = op in ("select", "context")
        kind, item = self.pick(pos)
        if scene.mode == "model":
            if kind is None:
                if plain and not keep:
                    scene.select_objects([], "replace")
                return
            if plain:
                if not (keep and scene.is_object_selected(item)):
                    scene.select_objects([item], "replace", active=item)
            else:
                scene.select_objects([item], "add" if op == "add" else "toggle", active=item)
            return
        if kind is None:
            other = self.pick_object(pos)
            if other is not None and other is not scene.active:
                self._activate_other(other)
            elif plain and not keep:
                scene.clear_selection()
            return
        if plain:
            if not (keep and self._is_selected(kind, item)):
                scene.select_components([item])
        elif op == "add" or not self._is_selected(kind, item):
            scene.select_components([item], add=True)
        else:
            scene.select_components([item], remove=True)

    def _start_tool_drag(self, press: QPointF, pos: QPointF, mods) -> bool:
        scene = self.scene
        if scene.tool not in TRANSFORM_TOOLS or not scene.has_selection():
            return False
        held = _controls().modifier_held
        ctrl = bool(held(mods, "extrude"))
        if scene.tool == "move":
            self._begin_drag("free", press)
        elif not self._begin_free_gizmo(press):
            return False
        d = self._drag
        if d is None:
            return False
        d.clone = ctrl and scene.mode == "model"
        if ctrl and scene.mode != "model" and scene.tool == "move":
            d.ctrl_seen = True
        self._update_drag(pos, bool(held(mods, "snap")))
        return True

    def _touched(self, pos: QPointF) -> list:
        if self.scene.mode == "model":
            obj = self.pick_object(pos)
            return [] if obj is None else [obj]
        kind, item = self.pick(pos)
        return [] if kind is None else [item]

    def _paint_apply(self, items: list, op: str) -> None:
        scene = self.scene
        if scene.mode == "model":
            held = {id(o) for o in scene.selected_objects()}
            hit = {id(o) for o in items}
            if op == "replace":
                changed = held != hit
            elif op == "add":
                changed = bool(hit - held)
            else:
                changed = bool(hit & held)
            if changed:
                scene._record("selection")
                scene.select_objects(items, op)
            return
        if not scene.is_editable(scene.active):
            return
        target = scene._component_set()
        norm = {scene._normalise(i) for i in items}
        if op == "replace":
            changed = norm != target
        elif op == "add":
            changed = bool(norm - target)
        else:
            changed = bool(norm & target)
        if changed:
            scene._record("selection")
            scene.select_components(norm, add=op == "add", remove=op == "remove")

    def _paint_begin(self, st: _Press, pos: QPointF) -> None:
        st.painting = True
        st.kind = PAINT_OPS.get(st.op, "replace")
        st.last = QPointF(st.press)
        self.scene.begin_group()
        if st.kind == "replace":
            self._paint_apply(self._touched(st.press), "replace")
            st.kind = "add"
        else:
            self._paint_apply(self._touched(st.press), st.kind)
        self._paint_to(st, pos)

    def _paint_to(self, st: _Press, pos: QPointF) -> None:
        last = st.last
        dx, dy = pos.x() - last.x(), pos.y() - last.y()
        steps = max(1, int(math.ceil(math.hypot(dx, dy) / self.PAINT_STEP_PX)))
        items: list = []
        for i in range(1, steps + 1):
            for hit in self._touched(QPointF(last.x() + dx * i / steps, last.y() + dy * i / steps)):
                if all(hit != h for h in items):
                    items.append(hit)
        st.last = QPointF(pos)
        if items:
            self._paint_apply(items, st.kind)
        self.update()

    def _move_press(self, st: _Press, pos: QPointF, mods) -> None:
        if st.painting:
            self._paint_to(st, pos)
            return
        if st.moved:
            return
        delta = pos - st.press
        if st.paint:
            if math.hypot(delta.x(), delta.y()) < self.click_tolerance():
                return
            st.moved = True
            self._paint_begin(st, pos)
            return
        if abs(delta.x()) + abs(delta.y()) < self.drag_threshold():
            return
        st.moved = True
        if self._start_tool_drag(st.press, pos, mods | self._press_mods):
            self._press_state = None

    def _release_press(self, st: _Press, e: QMouseEvent) -> None:
        self._press_state = None
        if st.painting:
            self.scene.end_group()
        elif not st.moved:
            if st.paint:
                moved = e.position() - st.press
                if math.hypot(moved.x(), moved.y()) < self.click_tolerance():
                    self.click_select(st.press, st.op, keep=True)
                    self.open_context_menu(e.position(), e.globalPosition())
            else:
                self.click_select(st.press, st.op)
        self.update()

    def _pen_anchor(self) -> np.ndarray:
        scene = self.scene
        obj = scene.active
        if obj is not None:
            chain = [i for i in scene.pen_chain if 0 <= i < len(obj.mesh.points)]
            if chain:
                return obj.world_points()[chain[-1]]
            return np.asarray(obj.world_position(), float).copy()
        return np.asarray(self.camera.target, float).copy()

    def pen_place_point(self, pos) -> np.ndarray:
        hit = self.hit_at(pos)
        if hit is not None:
            return np.asarray(hit[2], float)
        point = self.unproject(pos, (self._pen_anchor(), self.view_direction()))
        return point if point is not None else self.cursor_point(pos)

    def _pick_other_point(self, x: float, y: float) -> tuple[SceneObject, int] | None:
        best, best_key = None, (math.inf, math.inf)
        for obj in self.scene.render_objects():
            if obj is self.scene.active or not len(obj.mesh.points) or not self.scene.is_editable(obj):
                continue
            view = self._object_view(obj)
            idx = self._pick_point(view, x, y)
            if idx is None:
                continue
            key = (round(math.hypot(view.screen[idx, 0] - x, view.screen[idx, 1] - y), 6),
                   float(view.cam[idx, 2]))
            if key < best_key:
                best, best_key = (obj, idx), key
        return best

    def pen_target(self, pos) -> tuple[str, object]:
        scene = self.scene
        obj = scene.active
        x, y = _xy(pos)
        if obj is not None and len(obj.mesh.points):
            idx = self._pick_point(self._object_view(obj), x, y)
            if idx is not None:
                if scene.pen_click_closes(idx):
                    return "close", idx
                if idx not in scene.pen_chain:
                    return "link", idx
                return "none", idx
        other = self._pick_other_point(x, y)
        if other is not None:
            if scene.pen_active():
                return "place", other[0].world_points()[other[1]].copy()
            return "start", other
        return "place", self.pen_place_point(pos)

    def pen_click(self, pos) -> None:
        scene = self.scene
        kind, value = self.pen_target(pos)
        scene.begin_group()
        try:
            if kind == "close":
                scene.pen_close()
            elif kind == "link":
                world = scene.active.world_points()[int(value)]
                scene.pen_link_point(int(value), self.toward_camera(world))
            elif kind == "start":
                obj, i = value
                scene.set_active(obj)
                scene.pen_link_point(int(i), self.toward_camera(obj.world_points()[int(i)]))
            elif kind == "place":
                if scene.active is None and scene.tool == "pen":
                    scene.add_object("Polygon")
                scene.pen_add_point(value, self.toward_camera(value))
        finally:
            scene.end_group()
        self._pen_hover = self.pen_target(pos)
        self.update()

    def _press_pen(self, pos: QPointF) -> None:
        kind, item = self.pick(pos)
        self._pen_press = _PenPress(QPointF(pos), kind, item)

    def _move_pen_press(self, pos: QPointF, ctrl: bool) -> None:
        pp = self._pen_press
        if not pp.moved:
            delta = QPointF(pos) - pp.press
            if abs(delta.x()) + abs(delta.y()) < self.drag_threshold():
                return
            pp.moved = True
            if pp.kind is None:
                return
            if not self._is_selected(pp.kind, pp.item):
                self.scene.select_components([pp.item])
            self._begin_drag("free", pp.press)
            if self._drag is None:
                return
            self._drag.active = True
        if self._drag is not None:
            if ctrl:
                self._ctrl_during_drag()
            self._update_drag(pos)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        btn, mods, pos = e.button(), e.modifiers(), e.position()
        if self._drag is not None:
            if btn != Qt.MouseButton.LeftButton:
                self.cancel_drag()
                self._pen_press = None
            e.accept()
            return
        if self._nav is not None:
            e.accept()
            return
        if self._pen_press is not None:
            if btn != Qt.MouseButton.LeftButton:
                self._pen_press = None
            e.accept()
            return
        st = self._press_state
        if st is not None:
            if btn != st.button and not st.painting:
                self._press_state = None
            e.accept()
            return
        gesture = self.match_gesture(btn, mods)
        op = gesture.get("op") if gesture else None
        paint = bool(gesture) and _controls_profiles().is_paint_gesture(_controls().active(), gesture)
        if op in NAV_OPS:
            self.begin_navigation(NAV_OPS[op], QPointF(pos), btn)
        elif paint and self.pen_mode() and self.scene.pen_active():
            self.scene.pen_finish()
            self._pen_hover = self.pen_target(pos)
            self.update()
        elif paint and not self.pen_mode():
            self._press_mods = mods
            self._press_state = _Press(QPointF(pos), op, btn, paint=True)
        elif op in SELECT_OPS and not paint:
            self._press_mods = mods
            if op == "select" and self.pen_mode():
                self._press_pen(QPointF(pos))
            elif self.pen_mode():
                self.click_select(QPointF(pos), op)
                self.update()
            else:
                self._press_select(QPointF(pos), op, btn)
        else:
            super().mousePressEvent(e)
            return
        e.accept()

    def match_gesture(self, button: Qt.MouseButton, mods: Qt.KeyboardModifier,
                      double: bool = False) -> dict | None:
        name = _button_name(button)
        if name is None:
            return None
        return _controls().match_press(name, _modifier_names(mods), set(self._held_keys), double)

    def open_context_menu(self, pos, global_pos=None):
        from quartz_studio.widgets import context_menu

        scene = self.scene
        target = None
        if scene.mode == "model":
            target = self.pick_object(pos)
            if target is not None and not scene.is_object_selected(target):
                scene.select_objects([target], "replace", active=target)
        menu = context_menu.build_menu(scene, scene.mode, target, canvas=self,
                                       tree=context_menu.find_tree(self), parent=self)
        point = self.mapToGlobal(QPointF(pos).toPoint()) if global_pos is None else QPointF(global_pos).toPoint()
        self.context_menu = context_menu.show_menu(menu, point)
        return self.context_menu

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        nav = self._nav
        if nav is not None:
            if nav.button is not None:
                d = pos - nav.last
                nav.last = QPointF(pos)
                self.navigate(nav.mode, d.x(), d.y(), QPointF(pos))
            e.accept()
            return
        held = _controls().modifier_held
        extrude = bool(held(e.modifiers(), "extrude"))
        if self._pen_press is not None:
            if e.buttons() & Qt.MouseButton.LeftButton:
                self._move_pen_press(QPointF(pos), extrude)
            e.accept()
            return
        st = self._press_state
        if st is not None:
            if e.buttons() & st.button:
                self._move_press(st, QPointF(pos), e.modifiers())
                e.accept()
                return
            self._drop_press()
        if self._drag is not None:
            if e.buttons() & Qt.MouseButton.LeftButton:
                d = self._drag
                if (not d.active and extrude and self.scene.mode == "model"
                        and self.scene.tool in TRANSFORM_TOOLS):
                    d.clone = True
                if extrude:
                    self._ctrl_during_drag()
                self._update_drag(pos, bool(held(e.modifiers(), "snap")))
            e.accept()
            return
        if e.buttons() == Qt.MouseButton.NoButton:
            hover = self.gizmo_pick(pos)
            if hover != self._hover:
                self._hover = hover
                self.update()
            if self.pen_mode():
                self._pen_hover = self.pen_target(pos)
                self.update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._nav is not None and self._nav.button is not None and e.button() == self._nav.button:
            self.end_navigation()
            e.accept()
            return
        st = self._press_state
        if st is not None and e.button() == st.button:
            self._release_press(st, e)
            e.accept()
            return
        if self._drag is not None and e.button() == Qt.MouseButton.LeftButton:
            self._pen_press = None
            d = self._end_drag()
            if not d.active and d.pending:
                self.scene.select_components([d.pending[0]])
            elif not d.active and d.click_op and self.pick(d.press)[0] is not None:
                self.click_select(d.press, d.click_op)
            self.update()
            e.accept()
            return
        if self._pen_press is not None and e.button() == Qt.MouseButton.LeftButton:
            pp, self._pen_press = self._pen_press, None
            if self.pen_mode():
                self.pen_click(e.position() if pp.moved else pp.press)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        gesture = self.match_gesture(e.button(), e.modifiers(), True)
        action_id = gesture.get("action") if gesture else None
        if action_id and self._run_mouse_action(action_id):
            e.accept()
            return
        self.mousePressEvent(e)

    def _run_mouse_action(self, action_id: str) -> bool:
        if action_id.startswith("tool."):
            try:
                from quartz_studio.modeling import registry

                spec = registry.get_tool(action_id[len("tool."):])
            except (ImportError, KeyError):
                spec = None
            if spec is not None and not spec.supports(self.scene.mode):
                return False
        run = self._action_callable(action_id)
        if run is None:
            return False
        self.end_navigation()
        run()
        return True

    def wheelEvent(self, e: QWheelEvent) -> None:
        self.claim_focus()
        steps = e.angleDelta().y() / 120.0
        if _controls().cursor("wheel_invert"):
            steps = -steps
        if steps and self._nav is None:
            self.zoom_at(e.position(), steps)
        e.accept()

    def key_actions(self) -> dict:
        scene = self.scene
        out = {
            "view.undo": self.undo_view,
            "view.redo": self.redo_view,
            "view.frame_default": self.reset_camera,
            "view.frame_all": self.frame_all,
            "view.frame_selection": self.frame_selection,
            "view.frame_objects": self.frame_active,
        }
        for name in VIEW_PRESETS:
            out["camera." + name.lower()] = lambda n=name: self.set_view(n)
        for name in NAV_PIVOTS:
            out["camera.pivot." + name.lower()] = lambda n=name: self.set_nav_pivot(n)
        for tool in ("select", "move", "rotate", "scale"):
            out["tool." + tool] = lambda t=tool: scene.set_tool(t)
        return out

    def _controls_window(self):
        win = _controls().window()
        return win if win is not None and self.window() is win else None

    def _action_callable(self, action_id: str):
        controls = _controls()
        if self._controls_window() is not None:
            act = controls.actions().get(action_id)
            if act is not None:
                if act.available is not None and not act.available():
                    return None
                return lambda: controls.run(action_id)
        return self.key_actions().get(action_id)

    def _action_repeats(self, action_id: str) -> bool:
        if self._controls_window() is not None:
            act = _controls().actions().get(action_id)
            if act is not None:
                return bool(act.repeat)
        return action_id in ("view.undo", "view.redo")

    def _key_action_id(self, e: QKeyEvent) -> str | None:
        return _controls().lookup(e, "viewport")

    def _view_key_action(self, e: QKeyEvent):
        action_id = self._key_action_id(e)
        return None if action_id is None else self._action_callable(action_id)

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.ShortcutOverride and isinstance(e, QKeyEvent) and (
                self._view_key_action(e) is not None or int(e.key()) in self._nav_key_codes()):
            e.accept()
            return True
        return super().event(e)

    @staticmethod
    def _nav_key_codes() -> set[int]:
        return {int(k) for k in _controls().hold_keys()}

    def keyPressEvent(self, e: QKeyEvent) -> None:
        controls = _controls()
        key = int(e.key())
        if self._drag is not None and controls.modal_key(e, "cancel"):
            self.cancel_drag()
            self._pen_press = None
            e.accept()
            return
        if self._press_state is not None and controls.modal_key(e, "cancel"):
            self._drop_press()
            e.accept()
            return
        role_mod = _modifier_of_key(key)
        if (self._drag is not None and role_mod != Qt.KeyboardModifier.NoModifier
                and controls.modifier_held(role_mod, "extrude")):
            self._ctrl_during_drag()
            e.accept()
            return
        if self.scene.pen_active() and (controls.modal_key(e, "cancel") or controls.modal_key(e, "confirm")):
            self._pen_press = None
            self.scene.pen_finish()
            e.accept()
            return
        if key in self._nav_key_codes() and not e.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                                                 | Qt.KeyboardModifier.AltModifier):
            self._held_keys.add(key)
            e.accept()
            return
        action_id = self._key_action_id(e)
        action = None if action_id is None else self._action_callable(action_id)
        if action is not None:
            if not e.isAutoRepeat() or self._action_repeats(action_id):
                action()
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent) -> None:
        key = int(e.key())
        if key in self._held_keys and not e.isAutoRepeat():
            self._held_keys.discard(key)
            e.accept()
            return
        super().keyReleaseEvent(e)

    def claim_focus(self) -> bool:
        if self.hasFocus():
            return True
        if not self.isVisible() or QApplication.activePopupWidget() is not None:
            return False
        if _is_text_input(QApplication.focusWidget()) or _is_text_input(self.window().focusWidget()):
            return False
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        return self.hasFocus() or self.window().focusWidget() is self

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if not self._focus_claimed:
            self._focus_claimed = True
            self.claim_focus()

    def enterEvent(self, e) -> None:
        self.claim_focus()
        super().enterEvent(e)

    def leaveEvent(self, e: QEvent) -> None:
        if self._hover is not None and self._drag is None:
            self._hover = None
            self.update()
        if self._pen_hover is not None and self._pen_press is None:
            self._pen_hover = None
            self.update()
        super().leaveEvent(e)

    def sizeHint(self) -> QSize:
        return QSize(1349, 864)



class _NavIconDrag(QObject):

    def __init__(self, canvas: ViewportCanvas, mode: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._canvas = canvas
        self._mode = mode
        self._last: QPointF | None = None
        self._moved = False

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        kind = ev.type()
        canvas = self._canvas
        if kind == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
            self._last = ev.globalPosition()
            self._moved = False
        elif kind == QEvent.Type.MouseMove and self._last is not None:
            if ev.buttons() & Qt.MouseButton.LeftButton:
                g = ev.globalPosition()
                d = g - self._last
                self._last = g
                if not self._moved and (d.x() or d.y()):
                    self._moved = True
                    canvas.end_navigation()
                    canvas.begin_navigation(self._mode)
                if self._moved:
                    canvas.navigate(self._mode, d.x(), d.y())
                if isinstance(obj, QAbstractButton):
                    obj.setDown(True)
                return True
        elif kind == QEvent.Type.MouseButtonRelease and ev.button() == Qt.MouseButton.LeftButton:
            if self._moved:
                if isinstance(obj, QAbstractButton):
                    obj.setDown(False)
                canvas.end_navigation()
            self._last = None
            self._moved = False
        return False


class ViewportMenuBar(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsViewportMenuBar")
        self.setFixedHeight(OVERLAY_TOP)
        self.setStyleSheet(
            "QWidget#qsViewportMenuBar { background: transparent; }"
            f"QPushButton#qsViewMenu {{ background: transparent; border: 1px solid transparent;"
            f" border-radius: {theme.CONTROL_RADIUS}px; padding: 0px {theme.SPACE_3 - 2}px;"
            f" min-height: {theme.GHOST_BUTTON_H - 2}px; max-height: {theme.GHOST_BUTTON_H - 2}px;"
            f" color: {theme.TEXT_SECONDARY}; }}"
            f"QPushButton#qsViewMenu:hover, QPushButton#qsViewMenu:pressed {{"
            f" background: {theme.qss_rgba(theme.OVERLAY_BG)}; color: {theme.TEXT_PRIMARY}; }}"
            f"QPushButton#qsViewMenu:open {{ background: {theme.qss_rgba(theme.ACCENT_TINT_ARGB)};"
            f" color: {theme.ACCENT}; }}"
            f"QPushButton#qsViewMenu:focus {{ border: {theme.FOCUS_RING_W}px solid {theme.FOCUS_RING}; }}"
            "QPushButton#qsViewMenu::menu-indicator { image: none; width: 0px; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(OVERLAY_INSET, OVERLAY_INSET, OVERLAY_INSET, 0)
        lay.setSpacing(theme.SPACE_1)
        self.menus: dict[str, QMenu] = {}
        self.menu_buttons: list[QPushButton] = []
        for title, entries in VIEWPORT_MENUS:
            btn = QPushButton(title, self)
            btn.setObjectName("qsViewMenu")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setFixedHeight(theme.GHOST_BUTTON_H)
            menu = build_view_menu(entries, btn)
            btn.setMenu(menu)
            lay.addWidget(btn)
            self.menus[title] = menu
            self.menu_buttons.append(btn)
        lay.addStretch(1)
        self.nav_buttons: list[IconButton] = []
        for name, tip in NAV_ICONS:
            b = IconButton(name, tip, parent=self, size=theme.NAV_BUTTON, icon_size=18, flat=True,
                           color=theme.ICON_STROKE)
            b.clicked.disconnect(b._on_clicked)
            lay.addWidget(b)
            self.nav_buttons.append(b)
        self._nav_filters: list[_NavIconDrag] = []
        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(0, 0, parent.width(), OVERLAY_TOP)

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if obj is self.parentWidget() and ev.type() == QEvent.Type.Resize:
            self.setGeometry(0, 0, obj.width(), OVERLAY_TOP)
        return False

    def _update_mask(self) -> None:
        region = QRegion()
        for w in (*self.menu_buttons, *self.nav_buttons):
            region = region.united(QRegion(w.geometry()))
        self.setMask(region)

    def event(self, ev: QEvent) -> bool:
        done = super().event(ev)
        if ev.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Resize, QEvent.Type.Show):
            self._update_mask()
        return done

    def mousePressEvent(self, ev) -> None:
        ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        ev.accept()

    def mouseDoubleClickEvent(self, ev) -> None:
        ev.accept()

    def menu_titles(self) -> list[str]:
        return [b.text() for b in self.menu_buttons]

    def bind_navigation(self, canvas: ViewportCanvas) -> None:
        for button, mode in zip(self.nav_buttons, NAV_ICON_MODES):
            button.setProperty(HOLD_PROPERTY, True)
            f = _NavIconDrag(canvas, mode, button)
            button.installEventFilter(f)
            self._nav_filters.append(f)
        self._bind_menus(canvas)

    def menu_action(self, title: str, text: str) -> QAction | None:
        menu = self.menus.get(title)
        stack = [menu] if menu is not None else []
        while stack:
            for act in stack.pop().actions():
                if act.menu() is not None:
                    stack.append(act.menu())
                elif act.text().split("\t")[0] == text:
                    return act
        return None

    def _rewire(self, title: str, text: str, slot) -> QAction | None:
        act = self.menu_action(title, text)
        if act is not None:
            try:
                act.triggered.disconnect()
            except (RuntimeError, TypeError):
                pass
            act.triggered.connect(lambda _=False: slot())
        return act

    VIEW_ACTION_IDS = (("Undo View", "view.undo"), ("Redo View", "view.redo"),
                       ("Frame Default", "view.frame_default"), ("Frame Geometry", "view.frame_all"),
                       ("Frame Selected Elements", "view.frame_selection"),
                       ("Frame Selected Objects", "view.frame_objects"))

    def refresh_bindings(self, _profile_id: str = "") -> None:
        binding_text = _controls().binding_text
        for text, action_id in self.VIEW_ACTION_IDS:
            act = self.menu_action("View", text)
            if act is None:
                continue
            shortcut = binding_text(action_id) or ""
            act.setProperty(P_SHORTCUT, shortcut)
            act.setText(f"{text}\t{shortcut}" if shortcut else text)

    def _bind_menus(self, canvas: ViewportCanvas) -> None:
        for text, slot in (("Undo View", canvas.undo_view),
                           ("Redo View", canvas.redo_view),
                           ("Frame Default", canvas.reset_camera),
                           ("Frame Geometry", canvas.frame_all),
                           ("Frame Selected Elements", canvas.frame_selection),
                           ("Frame Selected Objects", canvas.frame_active)):
            self._rewire("View", text, slot)
        self.refresh_bindings()
        _controls().hub().profileChanged.connect(self.refresh_bindings)
        history = (("Undo View", canvas.can_undo_view), ("Redo View", canvas.can_redo_view))

        def sync_history() -> None:
            for text, can in history:
                act = self.menu_action("View", text)
                if act is not None:
                    act.setEnabled(bool(can()))

        self.menus["View"].aboutToShow.connect(sync_history)
        sync_history()
        self.view_actions: dict[str, QAction] = {}
        self._view_group = QActionGroup(self)
        self._view_group.setExclusive(True)
        for name in VIEW_PRESETS:
            act = self._rewire("Cameras", name, lambda n=name: canvas.set_view(n))
            if act is not None:
                act.setCheckable(True)
                self._view_group.addAction(act)
                self.view_actions[name] = act
        self.nav_pivot_actions: dict[str, QAction] = {}
        self._pivot_group = QActionGroup(self)
        self._pivot_group.setExclusive(True)
        for name in NAV_PIVOTS:
            act = self._rewire("Cameras", name, lambda n=name: canvas.set_nav_pivot(n))
            if act is not None:
                self._pivot_group.addAction(act)
                self.nav_pivot_actions[name] = act
        canvas.viewChanged.connect(self._sync_view_checks)
        canvas.navPivotChanged.connect(self._sync_pivot_checks)
        self._sync_view_checks(canvas.view_name)
        self._sync_pivot_checks(canvas.nav_pivot)

    def _sync_view_checks(self, name: str) -> None:
        act = self.view_actions.get(name)
        if act is not None:
            act.setChecked(True)
        else:
            checked = self._view_group.checkedAction()
            if checked is not None:
                self._view_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
                checked.setChecked(False)
                self._view_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.Exclusive)

    def _sync_pivot_checks(self, name: str) -> None:
        act = self.nav_pivot_actions.get(name)
        if act is not None:
            act.setChecked(True)



class Viewport(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsViewport")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)
        self.canvas = ViewportCanvas(self)
        self.menu_bar = ViewportMenuBar(self.canvas)
        self.menu_bar.bind_navigation(self.canvas)
        lay.addWidget(self.canvas, 1)

    def sizeHint(self) -> QSize:
        return QSize(1349, 890)
