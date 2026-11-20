from __future__ import annotations

import ctypes
import math

import numpy as np
import shiboken6
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QMenu, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from .. import theme
from ..scene import get_scene
from ..widgets.common import Chip, prepare_popup
from .data import get_seams
from .session import SELECT_MODES, UVSession, session_for
from .texture import checker_image

__all__ = ["UVCanvas", "UVEditorView", "BACKGROUNDS"]

BACKGROUNDS = ("Checker", "Texture", "Grid")
HANDLE = 8
ROTATE_OFFSET = 24
PICK_PX = 8
FRAME_PAD = 24
MIN_ZOOM = 16.0
MAX_ZOOM = 65536.0


def _fill_direct(poly: QPolygonF, xy: np.ndarray) -> bool:
    try:
        address = shiboken6.getCppPointer(poly.data())[0]
    except (AttributeError, TypeError, RuntimeError):
        return False
    ctypes.memmove(int(address), xy.ctypes.data, xy.nbytes)
    return True


def _probe_direct() -> bool:
    poly = QPolygonF()
    poly.resize(2)
    probe = np.array([[1.5, -2.25], [3.0, 4.75]], dtype=np.float64)
    if not _fill_direct(poly, probe):
        return False
    a, b = poly.at(0), poly.at(1)
    return (a.x(), a.y(), b.x(), b.y()) == (1.5, -2.25, 3.0, 4.75)


_DIRECT: list = []


def np_polygon(xy) -> QPolygonF:
    xy = np.ascontiguousarray(np.asarray(xy, dtype=np.float64).reshape(-1, 2))
    if not _DIRECT:
        _DIRECT.append(_probe_direct())
    if not len(xy):
        return QPolygonF()
    if _DIRECT[0]:
        poly = QPolygonF()
        poly.resize(len(xy))
        if _fill_direct(poly, xy):
            return poly
    return QPolygonF(list(map(QPointF, xy[:, 0].tolist(), xy[:, 1].tolist())))


def _qcolor(name: str, alpha: int | None = None) -> QColor:
    c = QColor(name)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def _heat(value: float) -> QColor:
    t = max(-1.0, min(1.0, value / 2.0))
    cold = QColor(theme.AXIS_Z)
    hot = QColor(theme.STATUS_ERROR)
    mid = QColor(theme.TEXT_PRIMARY)
    a, b = (mid, hot) if t >= 0 else (mid, cold)
    k = abs(t)
    out = QColor(round(a.red() + (b.red() - a.red()) * k), round(a.green() + (b.green() - a.green()) * k),
                 round(a.blue() + (b.blue() - a.blue()) * k))
    out.setAlpha(round(48 + 128 * k))
    return out


class UVCanvas(QWidget):

    viewChanged = Signal()

    def __init__(self, session: UVSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMinimumSize(128, 128)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.zoom = 256.0
        self.origin = QPointF(64.0, 320.0)
        self.background = "Checker"
        self.show_stretch = False
        self.checker_cells = 8
        self._checker = checker_image(512, 8)
        self._tex_cache: tuple | None = None
        self._overlay: dict | None = None
        self._drag: dict | None = None
        self._hover = QPointF(-1.0, -1.0)
        self._framed = False
        session.uvChanged.connect(self._invalidate)
        session.selectionChanged.connect(self.update)
        session.textureChanged.connect(self.update)
        session.toolChanged.connect(lambda *_: self.update())
        session.modeChanged.connect(lambda *_: self.update())
        session.objectChanged.connect(self._on_object)
        session.brushChanged.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(512, 512)

    def _invalidate(self) -> None:
        self.update()

    def overlay_key(self) -> tuple:
        s = self.session
        obj = s.obj
        return (s.topo_revision, id(obj), self.show_stretch, id(s.corners()) if obj is not None else 0)

    def _on_object(self) -> None:
        self._overlay = None
        self.frame_all()

    def to_screen(self, u, v) -> tuple:
        return self.origin.x() + np.asarray(u) * self.zoom, self.origin.y() - np.asarray(v) * self.zoom

    def to_uv(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.origin.x()) / self.zoom, (self.origin.y() - y) / self.zoom

    def set_background(self, name: str) -> None:
        if name not in BACKGROUNDS:
            raise ValueError(name)
        self.background = name
        self.update()

    def set_checker_cells(self, cells: int) -> None:
        self.checker_cells = max(1, int(cells))
        self._checker = checker_image(512, self.checker_cells)
        self.update()

    def set_show_stretch(self, on: bool) -> None:
        self.show_stretch = bool(on)
        self._overlay = None
        self.update()

    def set_view(self, zoom: float, origin: QPointF) -> None:
        self.zoom = float(min(max(zoom, MIN_ZOOM), MAX_ZOOM))
        self.origin = QPointF(origin)
        self.viewChanged.emit()
        self.update()

    def frame(self, lo, hi) -> None:
        w, h = max(self.width(), 64), max(self.height(), 64)
        span = np.maximum(np.asarray(hi, float) - np.asarray(lo, float), 1e-6)
        z = min((w - 2 * FRAME_PAD) / span[0], (h - 2 * FRAME_PAD) / span[1])
        z = float(min(max(z, MIN_ZOOM), MAX_ZOOM))
        cu, cv = (float(lo[0]) + float(hi[0])) / 2.0, (float(lo[1]) + float(hi[1])) / 2.0
        self.set_view(z, QPointF(w / 2.0 - cu * z, h / 2.0 + cv * z))

    def frame_all(self) -> None:
        lo, hi = self.session.frame_bounds()
        self.frame(lo, hi)

    def frame_unit(self) -> None:
        self.frame((0.0, 0.0), (1.0, 1.0))

    def zoom_at(self, factor: float, x: float, y: float) -> None:
        u, v = self.to_uv(x, y)
        z = float(min(max(self.zoom * factor, MIN_ZOOM), MAX_ZOOM))
        self.set_view(z, QPointF(x - u * z, y + v * z))

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if not self._framed and self.width() > 64 and self.height() > 64:
            self._framed = True
            self.frame_all()

    def _overlay_data(self) -> dict:
        key = self.overlay_key()
        if self._overlay is not None and self._overlay.get("key") == key:
            return self._overlay
        s = self.session
        obj = s.obj
        c = s.corners()
        data = {"key": key, "edges": np.zeros((0, 2), dtype=np.int64), "seam": np.zeros(0, bool),
                "border": np.zeros(0, bool), "heat": None, "points": np.zeros(0, dtype=np.int64),
                "islands": 0}
        if obj is None or c is None or not c.count:
            self._overlay = data
            return data
        groups = s.point_groups()
        a = np.arange(c.count, dtype=np.int64)
        b = c.next
        ga, gb = groups[a], groups[b]
        keep = ga != gb
        a, b, ga, gb = a[keep], b[keep], ga[keep], gb[keep]
        ng = int(groups.max()) + 1
        gk = np.minimum(ga, gb) * ng + np.maximum(ga, gb)
        _, first, inv, counts = np.unique(gk, return_index=True, return_inverse=True, return_counts=True)
        edges = np.stack([a[first], b[first]], axis=1)
        border = counts == 1
        va, vb = c.vertex[edges[:, 0]], c.vertex[edges[:, 1]]
        seams = get_seams(obj)
        if seams:
            nv = int(max(int(c.vertex.max()), max(max(e) for e in seams))) + 1
            skeys = np.array([x * nv + y for x, y in seams], dtype=np.int64)
            ekeys = np.minimum(va, vb) * nv + np.maximum(va, vb)
            seam = np.isin(ekeys, skeys)
        else:
            seam = np.zeros(len(edges), dtype=bool)
        _, pts = np.unique(groups, return_index=True)
        data.update(edges=edges, seam=seam, border=border, points=pts)
        data["islands"] = len(s.islands())
        if self.show_stretch:
            data["heat"] = s.stretch().get("area_log")
        self._overlay = data
        return data

    def _texture_image(self) -> QImage | None:
        canvas = self.session.canvas(create=False)
        if canvas is None:
            return None
        key = (id(canvas), canvas.revision)
        if self._tex_cache is None or self._tex_cache[0] != key:
            self._tex_cache = (key, canvas.to_qimage())
        return self._tex_cache[1]

    def unit_rect(self) -> QRectF:
        x0, y0 = self.to_screen(0.0, 1.0)
        return QRectF(float(x0), float(y0), self.zoom, self.zoom)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), _qcolor(theme.SURFACE_FIELD))
        unit = self.unit_rect()
        if self.background == "Checker":
            p.drawImage(unit, self._checker)
            p.fillRect(unit, _qcolor(theme.SURFACE_FIELD, 96))
        elif self.background == "Texture":
            img = self._texture_image()
            if img is not None:
                p.drawImage(unit, img)
            else:
                p.fillRect(unit, _qcolor(theme.SURFACE_CARD))
        else:
            p.fillRect(unit, _qcolor(theme.SURFACE_CARD))
        self._paint_grid(p, unit)
        s = self.session
        if s.obj is not None:
            self._paint_mesh(p)
            self._paint_handles(p)
        self._paint_overlay_tools(p)
        self._paint_hud(p)
        p.end()

    def _paint_grid(self, p: QPainter, unit: QRectF) -> None:
        pen = QPen(_qcolor(theme.GRID_MINOR), 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        steps = 10
        for k in range(1, steps):
            x = unit.left() + unit.width() * k / steps
            y = unit.top() + unit.height() * k / steps
            p.drawLine(QPointF(x, unit.top()), QPointF(x, unit.bottom()))
            p.drawLine(QPointF(unit.left(), y), QPointF(unit.right(), y))
        pen = QPen(_qcolor(theme.HAIRLINE_STRONG), 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(unit)

    def _paint_mesh(self, p: QPainter) -> None:
        s = self.session
        c = s.corners()
        uv = s.uv()
        if c is None or not len(uv):
            return
        xs, ys = self.to_screen(uv[:, 0], uv[:, 1])
        xs = np.where(np.isfinite(xs), xs, 0.0)
        ys = np.where(np.isfinite(ys), ys, 0.0)
        xy = np.stack([xs, ys], axis=1)
        data = self._overlay_data()
        heat = data["heat"]
        sel = s.selected_polys
        fill_sel = _qcolor(theme.ACCENT, 72)
        p.setPen(Qt.PenStyle.NoPen)
        starts = c.starts.tolist()
        sizes = c.sizes.tolist()
        if heat is not None or sel:
            ring_all = np_polygon(xy)
            if heat is not None:
                for poly in range(c.poly_count):
                    p.setBrush(QBrush(_heat(float(heat[poly]))))
                    p.drawPolygon(ring_all.sliced(starts[poly], sizes[poly]))
            if sel:
                p.setBrush(QBrush(fill_sel))
                for poly in sel:
                    if 0 <= poly < c.poly_count:
                        p.drawPolygon(ring_all.sliced(starts[poly], sizes[poly]))
        edges = data["edges"]
        if len(edges) and int(edges.max()) < len(uv):
            wire = QPen(_qcolor(theme.WIRE, 160), 1)
            wire.setCosmetic(True)
            border = QPen(_qcolor(theme.TEXT_PRIMARY), 2)
            border.setCosmetic(True)
            seam = QPen(_qcolor(theme.TINT_ROSE), 2)
            seam.setCosmetic(True)
            kind = np.where(data["seam"], 2, np.where(data["border"], 1, 0))
            dense = len(edges) > 2048
            for k, pen in ((0, wire), (1, border), (2, seam)):
                pick = edges[kind == k]
                if not len(pick):
                    continue
                p.setRenderHint(QPainter.RenderHint.Antialiasing, not (dense and k == 0))
                p.setPen(pen)
                p.drawLines(np_polygon(xy[pick.reshape(-1)]))
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if s.select_mode == "points":
            pts = data["points"]
            dot = QPen(_qcolor(theme.POINT_FILL), 4)
            dot.setCosmetic(True)
            dot.setCapStyle(Qt.PenCapStyle.SquareCap)
            p.setPen(dot)
            p.drawPoints(np_polygon(xy[pts]))
            if s.selected_corners:
                idx = np.fromiter(s.selected_corners, dtype=np.int64, count=len(s.selected_corners))
                idx = idx[idx < len(uv)]
                big = QPen(_qcolor(theme.SELECT_FRONT), 8)
                big.setCosmetic(True)
                big.setCapStyle(Qt.PenCapStyle.SquareCap)
                p.setPen(big)
                p.drawPoints(np_polygon(xy[idx]))

    def _handle_rects(self) -> dict | None:
        s = self.session
        if not s.selected_corners or s.tool in ("paint", "erase", "fill"):
            return None
        b = s.selection_bounds()
        if b is None:
            return None
        lo, hi = b
        x0, y0 = self.to_screen(lo[0], hi[1])
        x1, y1 = self.to_screen(hi[0], lo[1])
        x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
        if x1 - x0 < 2 * HANDLE:
            m = (x0 + x1) / 2.0
            x0, x1 = m - HANDLE, m + HANDLE
        if y1 - y0 < 2 * HANDLE:
            m = (y0 + y1) / 2.0
            y0, y1 = m - HANDLE, m + HANDLE
        box = QRectF(QPointF(x0, y0), QPointF(x1, y1))
        h = HANDLE
        corners = {
            "tl": QRectF(x0 - h / 2, y0 - h / 2, h, h),
            "tr": QRectF(x1 - h / 2, y0 - h / 2, h, h),
            "bl": QRectF(x0 - h / 2, y1 - h / 2, h, h),
            "br": QRectF(x1 - h / 2, y1 - h / 2, h, h),
        }
        rot = QRectF((x0 + x1) / 2 - h / 2, y0 - ROTATE_OFFSET - h / 2, h, h)
        return {"box": box, "corners": corners, "rotate": rot}

    def _paint_handles(self, p: QPainter) -> None:
        rects = self._handle_rects()
        if rects is None:
            return
        pen = QPen(_qcolor(theme.SELECT_FRONT), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        box = rects["box"]
        p.drawRect(box)
        top = QPointF(box.center().x(), box.top())
        p.drawLine(top, rects["rotate"].center())
        solid = QPen(_qcolor(theme.SELECT_FRONT_DARK), 1)
        solid.setCosmetic(True)
        p.setPen(solid)
        p.setBrush(_qcolor(theme.SELECT_FRONT))
        for r in rects["corners"].values():
            p.drawRect(r)
        p.drawEllipse(rects["rotate"])
        cx, cy = box.center().x(), box.center().y()
        p.drawLine(QPointF(cx - HANDLE, cy), QPointF(cx + HANDLE, cy))
        p.drawLine(QPointF(cx, cy - HANDLE), QPointF(cx, cy + HANDLE))

    def _paint_overlay_tools(self, p: QPainter) -> None:
        d = self._drag
        if d is not None and d.get("kind") == "box":
            pen = QPen(_qcolor(theme.ACCENT), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(_qcolor(theme.ACCENT, 32))
            p.drawRect(QRectF(d["start"], d["now"]).normalized())
        s = self.session
        if s.tool in ("paint", "erase") and self._hover.x() >= 0:
            canvas = s.canvas(create=False)
            width = canvas.width if canvas is not None else s.texture_size
            r = float(s.brush.radius) / max(width, 1) * self.zoom
            pen = QPen(_qcolor(theme.TEXT_PRIMARY), 1)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self._hover, r, r)
            inner = r * max(min(float(s.brush.hardness), 1.0), 0.0)
            if inner > 2:
                pen.setStyle(Qt.PenStyle.DotLine)
                p.setPen(pen)
                p.drawEllipse(self._hover, inner, inner)

    def _paint_hud(self, p: QPainter) -> None:
        s = self.session
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(_qcolor(theme.TEXT_SECONDARY))
        if s.obj is None:
            text = "No polygon object"
        else:
            data = self._overlay_data()
            n_sel = len(s.selected_polys) if s.select_mode != "points" else s.selected_point_count()
            text = (f"{s.obj.name}  {data['islands']} islands  {n_sel} selected  "
                    f"{s.select_mode}  {s.tool}  {self.zoom / 256.0 * 100:.0f}%")
        p.drawText(QRectF(8, self.height() - 24, self.width() - 16, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        if self._hover.x() >= 0:
            u, v = self.to_uv(self._hover.x(), self._hover.y())
            p.drawText(QRectF(8, self.height() - 24, self.width() - 16, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"U {u:.3f}  V {v:.3f}")

    def _hit_handle(self, pos: QPointF) -> tuple[str, str] | None:
        rects = self._handle_rects()
        if rects is None:
            return None
        grow = 4
        if rects["rotate"].adjusted(-grow, -grow, grow, grow).contains(pos):
            return ("rotate", "")
        for name, r in rects["corners"].items():
            if r.adjusted(-grow, -grow, grow, grow).contains(pos):
                return ("scale", name)
        if rects["box"].contains(pos):
            return ("move", "")
        return None

    def _begin_xf(self, kind: str, pos: QPointF, corner: str = "") -> None:
        s = self.session
        base = s.uv().copy()
        idx = s.affected()
        lo, hi = s.selection_bounds() or (np.zeros(2), np.ones(2))
        center = (lo + hi) / 2.0
        anchor = center.copy()
        if corner:
            anchor = np.array([hi[0] if "l" in corner else lo[0], lo[1] if "t" in corner else hi[1]])
        self._drag = {"kind": kind, "start": QPointF(pos), "now": QPointF(pos), "base": base, "idx": idx,
                      "center": center, "anchor": anchor, "corner": corner, "moved": False}

    def _apply_xf(self, pos: QPointF, modifiers) -> None:
        d = self._drag
        s = self.session
        base, idx = d["base"], d["idx"]
        u0, v0 = self.to_uv(d["start"].x(), d["start"].y())
        u1, v1 = self.to_uv(pos.x(), pos.y())
        out = base.copy()
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        if d["kind"] == "move":
            du, dv = u1 - u0, v1 - v0
            if shift:
                if abs(du) > abs(dv):
                    dv = 0.0
                else:
                    du = 0.0
            if ctrl:
                step = 1.0 / 64.0
                du, dv = round(du / step) * step, round(dv / step) * step
            out[idx] += np.array([du, dv])
        elif d["kind"] == "rotate":
            c = d["center"]
            a0 = math.atan2(v0 - c[1], u0 - c[0])
            a1 = math.atan2(v1 - c[1], u1 - c[0])
            ang = math.degrees(a1 - a0)
            if ctrl or shift:
                ang = round(ang / 15.0) * 15.0
            r = math.radians(ang)
            m = np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]])
            out[idx] = (base[idx] - c) @ m.T + c
            d["angle"] = ang
        elif d["kind"] == "scale":
            a = d["anchor"] if d["corner"] else d["center"]
            if d["corner"]:
                ref = np.array([u0, v0]) - a
                cur = np.array([u1, v1]) - a
                sx = cur[0] / ref[0] if abs(ref[0]) > 1e-12 else 1.0
                sy = cur[1] / ref[1] if abs(ref[1]) > 1e-12 else 1.0
                if shift:
                    k = (sx + sy) / 2.0
                    sx = sy = k
            else:
                k = math.exp((pos.x() - d["start"].x()) / 128.0)
                sx = sy = k
                if shift:
                    if abs(pos.x() - d["start"].x()) >= abs(pos.y() - d["start"].y()):
                        sy = 1.0
                    else:
                        sx, sy = 1.0, math.exp(-(pos.y() - d["start"].y()) / 128.0)
            out[idx] = (base[idx] - a) * np.array([sx, sy]) + a
        d["moved"] = True
        d["result"] = out
        s.preview(out, keep_topology=True)

    def mousePressEvent(self, e) -> None:
        pos = e.position()
        s = self.session
        mods = e.modifiers()
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        if e.button() == Qt.MouseButton.MiddleButton or (e.button() == Qt.MouseButton.LeftButton and alt):
            self._drag = {"kind": "pan", "start": QPointF(pos), "origin": QPointF(self.origin)}
            return
        if e.button() == Qt.MouseButton.RightButton:
            self._drag = {"kind": "zoom", "start": QPointF(pos), "zoom": self.zoom, "anchor": QPointF(pos),
                          "origin": QPointF(self.origin)}
            return
        if e.button() != Qt.MouseButton.LeftButton or s.obj is None:
            return
        u, v = self.to_uv(pos.x(), pos.y())
        if s.tool in ("paint", "erase", "fill"):
            if s.paint_begin(u, v):
                self._drag = {"kind": "paint", "start": QPointF(pos)}
            return
        add = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        remove = bool(mods & Qt.KeyboardModifier.ControlModifier)
        handle = self._hit_handle(pos)
        if handle is not None and not add and not remove:
            kind, corner = handle
            if kind == "move" and s.tool == "select":
                hit = s.pick(u, v, PICK_PX / self.zoom)
                if hit is None:
                    self._drag = {"kind": "box", "start": QPointF(pos), "now": QPointF(pos), "add": add,
                                  "remove": remove}
                    return
            if kind == "move" and s.tool == "rotate":
                kind = "rotate"
            elif kind == "move" and s.tool == "scale":
                kind = "scale"
            self._begin_xf(kind, pos, corner)
            return
        if s.tool in ("move", "rotate", "scale") and s.selected_corners and not add and not remove:
            self._begin_xf(s.tool, pos)
            return
        hit = s.pick(u, v, PICK_PX / self.zoom)
        if hit is None:
            self._drag = {"kind": "box", "start": QPointF(pos), "now": QPointF(pos), "add": add, "remove": remove}
            return
        s.select_at(u, v, PICK_PX / self.zoom, add=add, remove=remove)
        if not add and not remove and s.selected_corners:
            self._begin_xf("move" if s.tool in ("select", "move") else s.tool, pos)

    def mouseMoveEvent(self, e) -> None:
        pos = e.position()
        self._hover = QPointF(pos)
        d = self._drag
        s = self.session
        if d is None:
            if s.tool in ("paint", "erase"):
                self.update()
            else:
                self.update()
            return
        kind = d["kind"]
        if kind == "pan":
            delta = pos - d["start"]
            self.set_view(self.zoom, d["origin"] + delta)
        elif kind == "zoom":
            factor = math.exp((pos.x() - d["start"].x()) / 128.0)
            z = float(min(max(d["zoom"] * factor, MIN_ZOOM), MAX_ZOOM))
            a = d["anchor"]
            u = (a.x() - d["origin"].x()) / d["zoom"]
            v = (d["origin"].y() - a.y()) / d["zoom"]
            self.set_view(z, QPointF(a.x() - u * z, a.y() + v * z))
        elif kind == "paint":
            u, v = self.to_uv(pos.x(), pos.y())
            s.paint_move(u, v)
        elif kind == "box":
            d["now"] = QPointF(pos)
            self.update()
        elif kind in ("move", "rotate", "scale"):
            if (pos - d["start"]).manhattanLength() >= 2 or d["moved"]:
                self._apply_xf(pos, e.modifiers())

    def mouseReleaseEvent(self, e) -> None:
        d = self._drag
        self._drag = None
        s = self.session
        if d is None:
            return
        kind = d["kind"]
        if kind == "paint":
            s.paint_end()
        elif kind == "box":
            a = self.to_uv(d["start"].x(), d["start"].y())
            b = self.to_uv(e.position().x(), e.position().y())
            if (e.position() - d["start"]).manhattanLength() < 4:
                if not d["add"] and not d["remove"]:
                    s.clear_selection()
            else:
                s.select_box(a[0], a[1], b[0], b[1], add=d["add"], remove=d["remove"])
        elif kind in ("move", "rotate", "scale"):
            if d.get("moved") and d.get("result") is not None:
                s.commit(d["result"], f"UV {kind}")
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = QPointF(-1.0, -1.0)
        self.update()
        super().leaveEvent(e)

    def wheelEvent(self, e) -> None:
        steps = e.angleDelta().y() / 120.0
        if steps:
            pos = e.position()
            self.zoom_at(1.2 ** steps, pos.x(), pos.y())
        e.accept()

    def keyPressEvent(self, e) -> None:
        s = self.session
        key = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if ctrl and key == Qt.Key.Key_Z:
            s.redo() if shift else s.undo()
        elif ctrl and key == Qt.Key.Key_Y:
            s.redo()
        elif ctrl and key == Qt.Key.Key_A:
            s.select_all()
        elif ctrl and key == Qt.Key.Key_I:
            s.invert_selection()
        elif key == Qt.Key.Key_Escape:
            s.clear_selection()
        elif key == Qt.Key.Key_F:
            self.frame_all()
        elif key == Qt.Key.Key_H:
            self.frame_unit()
        elif key in (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3):
            s.set_select_mode(SELECT_MODES[key - Qt.Key.Key_1])
        elif key == Qt.Key.Key_Q:
            s.set_tool("select")
        elif key == Qt.Key.Key_E:
            s.set_tool("move")
        elif key == Qt.Key.Key_R:
            s.set_tool("rotate")
        elif key == Qt.Key.Key_T:
            s.set_tool("scale")
        elif key == Qt.Key.Key_B:
            s.set_tool("paint")
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and s.selected_corners:
            step = (8.0 if shift else 1.0) / max(self.zoom, 1e-9)
            du = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(key, 0.0)
            dv = {Qt.Key.Key_Down: -step, Qt.Key.Key_Up: step}.get(key, 0.0)
            s.move(du, dv)
        else:
            super().keyPressEvent(e)
            return
        e.accept()


class UVEditorView(QWidget):

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self.session = session_for(self.scene)
        self.setObjectName("qsUVEditor")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#qsUVEditor {{ background: {theme.SURFACE_CARD}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget(self)
        rows = QVBoxLayout(bar)
        rows.setContentsMargins(8, 4, 8, 4)
        rows.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(4)
        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        rows.addLayout(top)
        rows.addLayout(bottom)
        self.mode_buttons: dict[str, Chip] = {}
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for mode in SELECT_MODES:
            chip = Chip(mode.capitalize(), bar, checked=mode == self.session.select_mode)
            chip.clicked.connect(lambda _c=False, m=mode: self.session.set_select_mode(m))
            self.mode_group.addButton(chip)
            self.mode_buttons[mode] = chip
            top.addWidget(chip)
        top.addStretch(1)
        self.view_button = QToolButton(bar)
        self.view_button.setText("View")
        self.view_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.view_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view_menu = prepare_popup(QMenu(self.view_button))
        self.background_actions: dict[str, QAction] = {}
        self.background_group = QActionGroup(self)
        self.background_group.setExclusive(True)
        for name in BACKGROUNDS:
            act = self.view_menu.addAction(f"{name} Background")
            act.setCheckable(True)
            act.setChecked(name == "Checker")
            act.triggered.connect(lambda _c=False, n=name: self.set_background(n))
            self.background_group.addAction(act)
            self.background_actions[name] = act
        self.view_menu.addSeparator()
        self.stretch_action = self.view_menu.addAction("Show Stretch")
        self.stretch_action.setCheckable(True)
        self.stretch_action.toggled.connect(lambda on: self.canvas.set_show_stretch(on))
        self.view_menu.addSeparator()
        self.frame_action = self.view_menu.addAction("Frame Selection")
        self.frame_action.triggered.connect(lambda _c=False: self.canvas.frame_all())
        self.unit_action = self.view_menu.addAction("Frame 0..1")
        self.unit_action.triggered.connect(lambda _c=False: self.canvas.frame_unit())
        self.view_button.setMenu(self.view_menu)
        top.addWidget(self.view_button)
        self.edit_button = QToolButton(bar)
        self.edit_button.setText("Edit")
        self.edit_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.edit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.edit_menu = prepare_popup(QMenu(self.edit_button))
        self.undo_action = self.edit_menu.addAction("Undo")
        self.undo_action.triggered.connect(lambda _c=False: self.session.undo())
        self.redo_action = self.edit_menu.addAction("Redo")
        self.redo_action.triggered.connect(lambda _c=False: self.session.redo())
        self.edit_menu.addSeparator()
        self.select_all_action = self.edit_menu.addAction("Select All")
        self.select_all_action.triggered.connect(lambda _c=False: self.session.select_all())
        self.invert_action = self.edit_menu.addAction("Invert Selection")
        self.invert_action.triggered.connect(lambda _c=False: self.session.invert_selection())
        self.deselect_action = self.edit_menu.addAction("Deselect")
        self.deselect_action.triggered.connect(lambda _c=False: self.session.clear_selection())
        self.edit_button.setMenu(self.edit_menu)
        top.addWidget(self.edit_button)
        self.tool_buttons: dict[str, Chip] = {}
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for tool in ("select", "move", "rotate", "scale", "paint", "erase", "fill"):
            chip = Chip(tool.capitalize(), bar, checked=tool == self.session.tool)
            chip.clicked.connect(lambda _c=False, t=tool: self.session.set_tool(t))
            self.tool_group.addButton(chip)
            self.tool_buttons[tool] = chip
            bottom.addWidget(chip)
        bottom.addStretch(1)
        lay.addWidget(bar)
        rule = QWidget(self)
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {theme.HAIRLINE};")
        lay.addWidget(rule)
        self.canvas = UVCanvas(self.session, self)
        lay.addWidget(self.canvas, 1)
        self.status = QLabel("", self)
        self.status.setObjectName("qsDimLabel")
        self.status.setContentsMargins(8, 0, 8, 0)
        self.status.setFixedHeight(theme.ROW_H)
        lay.addWidget(self.status)
        self.session.modeChanged.connect(self._sync_mode)
        self.session.toolChanged.connect(self._sync_tool)
        self.session.message.connect(self.status.setText)

    def set_background(self, name: str) -> None:
        self.canvas.set_background(name)
        act = self.background_actions.get(name)
        if act is not None and not act.isChecked():
            act.setChecked(True)

    def sizeHint(self) -> QSize:
        return QSize(512, 576)

    def _sync_mode(self, mode: str) -> None:
        chip = self.mode_buttons.get(mode)
        if chip is not None and not chip.isChecked():
            chip.setChecked(True)

    def _sync_tool(self, tool: str) -> None:
        chip = self.tool_buttons.get(tool)
        if chip is not None and not chip.isChecked():
            chip.setChecked(True)
