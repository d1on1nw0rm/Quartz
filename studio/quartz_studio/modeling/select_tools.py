from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from functools import partial
from typing import Callable

import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPolygonF

from .. import icons, prefs, theme
from .. import scene as scene_module
from .meshkit import (
    boundary_loops,
    directed_edges,
    edge_faces,
    edge_key,
    edge_loop,
    edge_ring,
    face_normals,
    polygon_loop,
)
from ..widgets.command_bar import solid, stroke, unit_painter
from .registry import Param

__all__ = ["SelectTool", "TOOLS", "TOOL_IDS", "OPTIONS_KEY", "get", "is_select_tool", "options",
           "set_option", "reset_options", "activate", "ensure_mode", "apply_selection",
           "menu_commands", "loop_elements", "ring_elements", "pattern_elements", "fill_region",
           "phong_region"]

OPTIONS_KEY = "selection.options"
COMPONENT_MODES = ("points", "edges", "polygons")


@dataclass(frozen=True)
class SelectTool:
    id: str
    name: str
    icon: str
    modes: tuple[str, ...]
    entry_mode: str
    params: tuple[Param, ...]
    hint: str
    hint_model: str = ""


_ALL_MODES = ("points", "edges", "polygons", "model")

TOOLS: tuple[SelectTool, ...] = (
    SelectTool(
        "select", "Brush Selection", "pal_live_selection", _ALL_MODES, "",
        (Param("radius", "Radius", "int", 10, 2, 512, 2, "px"),
         Param("visible_only", "Only Select Visible Elements", "bool", True),
         Param("tolerant", "Tolerant Selection", "bool", False)),
        "Paint to select · Shift adds · Ctrl removes · Shift+wheel sizes the brush",
        "Paint over an object to select it · Ctrl deselects · Shift+wheel sizes the brush"),
    SelectTool(
        "select_loop", "Loop Selection", "pal_select_loop", COMPONENT_MODES, "edges",
        (Param("boundary", "Select Boundary Loop", "bool", False),),
        "Click an edge to select its loop · Shift adds · Ctrl removes"),
    SelectTool(
        "select_ring", "Ring Selection", "pal_select_ring", COMPONENT_MODES, "edges", (),
        "Click an edge to select its ring · Shift adds · Ctrl removes"),
    SelectTool(
        "select_pattern", "Pattern Selection", "pal_select_pattern", COMPONENT_MODES, "edges",
        (Param("count", "Select", "int", 1, 1, 64, 1),
         Param("skip", "Skip", "int", 1, 0, 64, 1),
         Param("direction", "Direction", "choice", "Loop", choices=("Loop", "Ring"))),
        "Click an edge to select a pattern along its loop · Shift adds · Ctrl removes"),
    SelectTool(
        "select_fill", "Fill Selection", "pal_select_fill", ("polygons",), "polygons", (),
        "Click a polygon to fill up to the selected edges · Ctrl removes"),
    SelectTool(
        "select_phong", "Phong Angle Selection", "pal_select_phong", ("polygons",), "polygons",
        (Param("angle", "Angle", "angle", 40.0, 0.0, 180.0, 1.0),),
        "Click a polygon to select its smooth area · Shift adds · Ctrl removes"),
)
TOOL_IDS: tuple[str, ...] = tuple(t.id for t in TOOLS)
_BY_ID = {t.id: t for t in TOOLS}


def get(tool_id: str) -> SelectTool:
    return _BY_ID[tool_id]


def is_select_tool(tool: str) -> bool:
    return tool in _BY_ID


def _extend_scene_tools() -> None:
    missing = tuple(i for i in TOOL_IDS if i not in scene_module.TOOLS)
    if missing:
        scene_module.TOOLS = tuple(scene_module.TOOLS) + missing


def _stored() -> dict:
    data = prefs.get(OPTIONS_KEY, {})
    return data if isinstance(data, dict) else {}


def _clamped(param: Param, value):
    try:
        return param.clamp(value)
    except (TypeError, ValueError, OverflowError):
        return param.default


def options(tool_id: str) -> dict:
    tool = get(tool_id)
    saved = _stored().get(tool_id, {})
    if not isinstance(saved, dict):
        saved = {}
    out = {}
    for param in tool.params:
        out[param.key] = _clamped(param, saved.get(param.key, param.default))
    return out


def set_option(tool_id: str, key: str, value) -> None:
    tool = get(tool_id)
    param = next((p for p in tool.params if p.key == key), None)
    if param is None:
        raise KeyError(f"{tool_id} has no option {key!r}")
    data = _stored()
    entry = options(tool_id)
    entry[key] = _clamped(param, value)
    data[tool_id] = entry
    prefs.set(OPTIONS_KEY, data)


def reset_options(tool_id: str) -> None:
    get(tool_id)
    data = _stored()
    if tool_id not in data:
        return
    del data[tool_id]
    prefs.set(OPTIONS_KEY, data if data else None)


def ensure_mode(scene, tool_id: str) -> None:
    tool = get(tool_id)
    if scene.mode not in tool.modes and tool.entry_mode:
        scene.set_mode(tool.entry_mode)


def activate(tool_id: str) -> None:
    scene = scene_module.get_scene()
    ensure_mode(scene, tool_id)
    scene.set_tool(tool_id)


def _apply_model(scene, items, op: str) -> bool:
    objs = [o for o in items if o is not None]
    obj = objs[0] if objs else None
    held = {id(o) for o in scene.selected_objects()}
    if op in ("replace", "add") and obj is not None:
        if op == "replace":
            changed = held != {id(obj)} or obj is not scene.active
        else:
            changed = id(obj) not in held or obj is not scene.active
        if not changed:
            return False
        scene._record("selection")
        return scene.select_objects([obj], op, active=obj)
    if op == "replace":
        if not held:
            return False
        scene._record("selection")
        return scene.select_objects([], "replace")
    if op == "remove" and any(id(o) in held for o in objs):
        scene._record("selection")
        return scene.select_objects(objs, "remove")
    return False


def apply_selection(scene, mode: str, items, op: str) -> bool:
    if op not in ("replace", "add", "remove"):
        raise ValueError(f"unknown selection operation {op!r}")
    if mode == "model":
        return _apply_model(scene, items, op)
    if mode not in COMPONENT_MODES or mode != scene.mode or not scene.is_editable(scene.active):
        return False
    if mode == "edges":
        norm = {edge_key(int(e[0]), int(e[1])) for e in items}
    else:
        norm = {int(i) for i in items}
    old = set(scene._component_set(mode))
    if op == "add":
        new = old | norm
    elif op == "remove":
        new = old - norm
    else:
        new = norm
    if new == old:
        return False
    scene._record("selection")
    scene.select_components(norm, add=op == "add", remove=op == "remove")
    return True


def menu_commands() -> list[tuple[tuple[str, ...], Callable[[], None]]]:
    return [(("Select", tool.name), partial(activate, tool.id)) for tool in TOOLS]


def _endpoints(edges) -> set:
    return {int(i) for e in edges for i in e}


def _boundary_edges(mesh, e) -> list:
    for loop in boundary_loops(mesh):
        ring = [edge_key(loop[i], loop[(i + 1) % len(loop)]) for i in range(len(loop))]
        if e in ring:
            return ring
    return [e]


def _loop_edges(mesh, e, boundary: bool) -> list:
    if boundary and len(edge_faces(mesh).get(e, [])) == 1:
        return _boundary_edges(mesh, e)
    return edge_loop(mesh, e)


def _next_side(mesh, polygon: int | None, e) -> tuple[int, int] | None:
    if polygon is None or not 0 <= polygon < len(mesh.polygons):
        return None
    poly = list(mesh.polygons[polygon])
    if len(poly) != 4:
        return None
    for j in range(4):
        if edge_key(poly[j], poly[(j + 1) % 4]) == e:
            return edge_key(poly[(j + 1) % 4], poly[(j + 2) % 4])
    return None


def _strip(mesh, e) -> list[int]:
    faces = polygon_loop(mesh, e)
    ring = edge_ring(mesh, e)
    if len(ring) > 2:
        ef = edge_faces(mesh)
        for f in set(ef.get(ring[-1], [])) & set(ef.get(ring[0], [])):
            if f not in faces:
                faces.append(f)
    return faces


def loop_elements(mesh, mode: str, edge, boundary: bool = False) -> set:
    e = edge_key(int(edge[0]), int(edge[1]))
    if mode == "polygons":
        return set(_strip(mesh, e))
    edges = _loop_edges(mesh, e, boundary)
    if mode == "points":
        return _endpoints(edges)
    return set(edges)


def ring_elements(mesh, mode: str, edge, polygon: int | None = None) -> set:
    e = edge_key(int(edge[0]), int(edge[1]))
    if mode == "polygons":
        side = _next_side(mesh, polygon, e)
        return set(_strip(mesh, side)) if side is not None else set()
    ring = edge_ring(mesh, e)
    if mode == "points":
        return _endpoints(ring)
    return set(ring)


def _vertex_chain(edges: list) -> list[int]:
    if not edges:
        return []
    if len(edges) == 1:
        return [int(edges[0][0]), int(edges[0][1])]
    a, b = edges[0]
    second = edges[1]
    chain = [a, b] if b in second else [b, a]
    for nxt in edges[1:]:
        last = chain[-1]
        if nxt[0] == last:
            chain.append(nxt[1])
        elif nxt[1] == last:
            chain.append(nxt[0])
        else:
            break
    if len(chain) > 2 and chain[-1] == chain[0]:
        chain.pop()
    return [int(i) for i in chain]


def _pattern(seq: list, i0: int, count: int, skip: int) -> list:
    period = count + skip
    return [item for i, item in enumerate(seq) if (i - i0) % period < count]


def pattern_elements(mesh, mode: str, edge, polygon: int | None, point: int | None,
                     count: int, skip: int, direction: str) -> set:
    e = edge_key(int(edge[0]), int(edge[1]))
    count = max(1, int(count))
    skip = max(0, int(skip))
    ring = direction == "Ring"
    if mode == "polygons":
        if ring:
            side = _next_side(mesh, polygon, e)
            seq = _strip(mesh, side) if side is not None else []
        else:
            seq = _strip(mesh, e)
        if polygon not in seq:
            return set()
        return set(_pattern(seq, seq.index(polygon), count, skip))
    if mode == "points":
        if ring:
            seq = edge_ring(mesh, e)
            return _endpoints(_pattern(seq, seq.index(e), count, skip))
        chain = _vertex_chain(edge_loop(mesh, e))
        if point is None or int(point) not in chain:
            return set()
        return set(_pattern(chain, chain.index(int(point)), count, skip))
    seq = edge_ring(mesh, e) if ring else edge_loop(mesh, e)
    if e not in seq:
        return set()
    return set(_pattern(seq, seq.index(e), count, skip))


def _neighbours(mesh, ef: dict, f: int):
    for a, b in directed_edges(mesh.polygons[f]):
        key = edge_key(a, b)
        for g in ef.get(key, ()):
            if g != f:
                yield key, g


def fill_region(mesh, face: int, borders: set, blocked: set) -> set[int]:
    if not 0 <= face < len(mesh.polygons) or face in blocked:
        return set()
    walls = {edge_key(int(a), int(b)) for a, b in borders}
    ef = edge_faces(mesh)
    region = {face}
    queue = deque([face])
    while queue:
        f = queue.popleft()
        for key, g in _neighbours(mesh, ef, f):
            if key in walls or g in region or g in blocked:
                continue
            region.add(g)
            queue.append(g)
    return region


def _angle(n0: np.ndarray, n1: np.ndarray) -> float:
    l0 = float(np.linalg.norm(n0))
    l1 = float(np.linalg.norm(n1))
    if l0 <= 0.0 or l1 <= 0.0:
        return 180.0
    c = float(np.clip((n0 @ n1) / (l0 * l1), -1.0, 1.0))
    return math.degrees(math.acos(c))


def phong_region(mesh, face: int, angle: float) -> set[int]:
    if not 0 <= face < len(mesh.polygons):
        return set()
    normals = face_normals(mesh)
    ef = edge_faces(mesh)
    limit = float(angle) + 1e-9
    region = {face}
    queue = deque([face])
    while queue:
        f = queue.popleft()
        for _key, g in _neighbours(mesh, ef, f):
            if g in region:
                continue
            if _angle(normals[f], normals[g]) <= limit:
                region.add(g)
                queue.append(g)
    return region


GREY = theme.ICON_STROKE
TINT = theme.ICON_TOOL
STROKE_W = theme.ICON_STROKE_W


def _icon_loop(p: QPainter, c: QColor) -> None:
    stroke(p, c, STROKE_W)
    for row in range(3):
        for col in range(3):
            p.drawRoundedRect(QRectF(3.6 + col * 6.2, 3.6 + row * 6.2, 4.4, 4.4), 1.2, 1.2)
    stroke(p, TINT, STROKE_W + 0.4)
    p.drawLine(QPointF(2.6, 12.0), QPointF(21.4, 12.0))


def _icon_ring(p: QPainter, c: QColor) -> None:
    stroke(p, c, STROKE_W)
    for y in (6.0, 12.0, 18.0):
        p.drawLine(QPointF(4.0, y), QPointF(20.0, y))
    stroke(p, TINT, STROKE_W + 0.4)
    for y in (6.0, 12.0, 18.0):
        p.drawLine(QPointF(12.0, y - 2.4), QPointF(12.0, y + 2.4))


def _icon_pattern(p: QPainter, c: QColor) -> None:
    size = 3.8
    step = 4.6
    left = 12.0 - (4 * step + size) / 2.0
    for k in range(5):
        solid(p, TINT if k % 2 == 0 else c)
        p.drawRoundedRect(QRectF(left + k * step, 12.0 - size / 2.0, size, size), 0.8, 0.8)


def _hexagon(r: float) -> QPolygonF:
    pts = []
    for k in range(6):
        a = math.radians(-90 + 60 * k)
        pts.append(QPointF(12 + r * math.cos(a), 12 + r * math.sin(a)))
    return QPolygonF(pts)


def _icon_fill(p: QPainter, c: QColor) -> None:
    outer = 9.4
    solid(p, TINT)
    p.drawPolygon(_hexagon(outer - 3.0 / math.cos(math.radians(30))))
    stroke(p, c, STROKE_W)
    p.drawPolygon(_hexagon(outer))


def _icon_phong(p: QPainter, c: QColor) -> None:
    stroke(p, c, STROKE_W)
    p.drawPolygon(QPolygonF([QPointF(2.8, 8.0), QPointF(12.0, 15.4), QPointF(12.0, 19.6),
                             QPointF(2.8, 12.2)]))
    p.drawPolygon(QPolygonF([QPointF(12.0, 15.4), QPointF(21.2, 8.0), QPointF(21.2, 12.2),
                             QPointF(12.0, 19.6)]))
    stroke(p, TINT, STROKE_W + 0.4)
    r = 6.0
    start = math.degrees(math.atan2(7.4, 9.2))
    span = 180.0 - 2 * start
    p.drawArc(QRectF(12.0 - r, 15.4 - r, 2 * r, 2 * r), round(start * 16), round(span * 16))


_ICON_PAINTERS = {
    "pal_select_loop": _icon_loop,
    "pal_select_ring": _icon_ring,
    "pal_select_pattern": _icon_pattern,
    "pal_select_fill": _icon_fill,
    "pal_select_phong": _icon_phong,
}


def _register_icons() -> None:
    for name, fn in _ICON_PAINTERS.items():
        if not icons.has(name):
            icons.register(name, unit_painter(fn), GREY)


_extend_scene_tools()
_register_icons()
