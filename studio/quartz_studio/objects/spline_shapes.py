from __future__ import annotations

import ast
import math
import operator

import numpy as np

from ..scene import Mesh
from .registry import ObjectSpec, Param, register

PLANES = ("XY", "ZY", "XZ")
ARC_TYPES = ("Arc", "Sector", "Segment", "Ring")
FOUR_SIDE_TYPES = ("Diamond", "Kite", "Parallelogram", "Trapezium")
PROFILE_TYPES = ("H Shape", "L Shape", "T Shape", "U Shape", "Z Shape")
CISSOID_TYPES = ("Cissoid", "Lemniscate", "Strophoid")
CYCLOID_TYPES = ("Cycloid", "Epicycloid", "Hypocycloid")
TOL = 1e-9
MAX_TOOTH_WIDTH = 0.99


def _tail(curved: bool) -> tuple:
    tail = [
        Param("plane", "Plane", "choice", "XY", choices=PLANES, group="Object"),
        Param("reverse", "Reverse", "bool", False, group="Object"),
    ]
    if curved:
        tail.append(Param("points_per_90", "Points per 90 degrees", "int", 8,
                          minimum=1, maximum=64, group="Object"))
    return tuple(tail)


def _pts(u, v, w=0.0) -> np.ndarray:
    u, v, w = np.broadcast_arrays(np.asarray(u, float), np.asarray(v, float), np.asarray(w, float))
    return np.column_stack([u.ravel(), v.ravel(), w.ravel()])


def _polar(r, deg) -> np.ndarray:
    t = np.radians(np.asarray(deg, float))
    r = np.asarray(r, float)
    return _pts(r * np.cos(t), r * np.sin(t))


def _at(r: float, deg: float) -> np.ndarray:
    t = math.radians(deg)
    return np.array([r * math.cos(t), r * math.sin(t), 0.0])


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def _seg(span_deg: float, samples: int) -> int:
    return max(1, int(round(abs(span_deg) / 90.0 * samples)))


def _sweep(a0: float, a1: float, samples: int) -> tuple[np.ndarray, bool]:
    span = a1 - a0
    if abs(span) >= 360.0:
        n = 4 * samples
        return a0 + 360.0 * np.arange(n) / n, True
    span %= 360.0
    return a0 + np.linspace(0.0, span, _seg(span, samples) + 1), False


def _ellipse(rx: float, ry: float, samples: int) -> np.ndarray:
    t = np.linspace(0.0, 360.0, 4 * samples, endpoint=False)
    return _pts(rx * np.cos(np.radians(t)), ry * np.sin(np.radians(t)))


def _clean(pts: np.ndarray, closed: bool) -> tuple[np.ndarray, bool]:
    out: list[np.ndarray] = []
    for p in pts:
        if not out or np.linalg.norm(p - out[-1]) > TOL:
            out.append(p)
    if len(out) > 2 and np.linalg.norm(out[-1] - out[0]) <= TOL:
        out.pop()
        closed = True
    return np.array(out, float).reshape(-1, 3), closed


def _to_space(uvw: np.ndarray, plane: str) -> np.ndarray:
    u, v, w = uvw[:, 0], uvw[:, 1], uvw[:, 2]
    if plane == "ZY":
        return np.column_stack([w, v, u])
    if plane == "XZ":
        return np.column_stack([u, w, v])
    return np.column_stack([u, v, w])


def _finish(chains: list, p: dict) -> Mesh:
    points: list[np.ndarray] = []
    edges: list[tuple[int, int]] = []
    for raw, closed in chains:
        chain, closed = _clean(np.asarray(raw, float).reshape(-1, 3), closed)
        if len(chain) < (3 if closed else 2):
            continue
        if p["reverse"]:
            chain = chain[::-1]
        mapped = _to_space(chain, p["plane"])
        offset, n = len(points), len(mapped)
        points.extend(mapped)
        edges.extend((offset + i, offset + i + 1) for i in range(n - 1))
        if closed:
            edges.append((offset + n - 1, offset))
    if not points:
        return Mesh.empty()
    return Mesh(np.array(points, float), [], edges)


def _rectangle_chains(p: dict) -> list:
    w, h = p["width"], p["height"]
    if w <= 0 or h <= 0:
        return []
    hw, hh = w / 2.0, h / 2.0
    r = min(p["radius"], hw, hh) if p["rounding"] else 0.0
    if r <= 0:
        return [(_pts([-hw, hw, hw, -hw], [-hh, -hh, hh, hh]), True)]
    corners = (
        (hw - r, -hh + r, -90.0),
        (hw - r, hh - r, 0.0),
        (-hw + r, hh - r, 90.0),
        (-hw + r, -hh + r, 180.0),
    )
    parts = []
    for cx, cy, a0 in corners:
        angles = np.linspace(a0, a0 + 90.0, _seg(90.0, p["points_per_90"]) + 1)
        parts.append(_polar(r, angles) + np.array([cx, cy, 0.0]))
    return [(np.vstack(parts), True)]


def _circle_chains(p: dict) -> list:
    rx = p["radius"]
    ry = p["radius_y"] if p["ellipse"] else rx
    if rx <= 0 or ry <= 0:
        return []
    s = p["points_per_90"]
    outer = _ellipse(rx, ry, s)
    ir = p["inner_radius"]
    if not p["ring"] or ir <= 0:
        return [(outer, True)]
    if ir >= rx:
        return []
    return [(outer, True), (_ellipse(ir, ir * ry / rx, s), True)]


def _arc_chains(p: dict) -> list:
    r = p["radius"]
    if r <= 0:
        return []
    angles, full = _sweep(p["start_angle"], p["end_angle"], p["points_per_90"])
    outer = _polar(r, angles)
    kind = p["type"]
    if kind == "Arc":
        return [(outer, full)]
    if kind == "Segment":
        return [(outer, True)]
    if kind == "Sector":
        if full:
            return [(outer, True)]
        return [(np.vstack([np.zeros((1, 3)), outer]), True)]
    ir = p["inner_radius"]
    if ir >= r:
        return []
    if full:
        if ir <= 0:
            return [(outer, True)]
        return [(outer, True), (_polar(ir, angles), True)]
    inner = _polar(max(ir, 0.0), angles[::-1])
    return [(np.vstack([outer, inner]), True)]


def _nside_chains(p: dict) -> list:
    r, n, s = p["radius"], p["sides"], p["points_per_90"]
    if r <= 0:
        return []
    ang = np.radians(90.0 + 360.0 * np.arange(n) / n)
    cur = np.column_stack([r * np.cos(ang), r * np.sin(ang)])
    rr = p["rounding_radius"]
    if not p["rounding"] or rr <= 0:
        return [(_pts(cur[:, 0], cur[:, 1]), True)]
    theta = math.pi * (n - 2) / n
    half = theta / 2.0
    edge = 2.0 * r * math.sin(math.pi / n)
    rad = min(rr, edge / 2.0 * math.tan(half))
    d = rad / math.tan(half)
    dc = rad / math.sin(half)
    parts = []
    for i in range(n):
        prev, here, nxt = cur[i - 1], cur[i], cur[(i + 1) % n]
        u_in = _unit(prev - here)
        u_out = _unit(nxt - here)
        bis = _unit(u_in + u_out)
        c = here + bis * dc
        a1 = math.atan2(*(here + u_in * d - c)[::-1])
        a2 = math.atan2(*(here + u_out * d - c)[::-1])
        delta = (a2 - a1 + math.pi) % (2.0 * math.pi) - math.pi
        steps = _seg(math.degrees(abs(delta)), s)
        t = a1 + delta * np.arange(steps + 1) / steps
        parts.append(_pts(c[0] + rad * np.cos(t), c[1] + rad * np.sin(t)))
    return [(np.vstack(parts), True)]


def _four_side_chains(p: dict) -> list:
    a, b, kind = p["a"], p["b"], p["type"]
    if a <= 0:
        return []
    if kind == "Trapezium":
        base = min(max(p["angle"], 1.0), 89.0)
        h = abs(a - b) / 2.0 * math.tan(math.radians(base))
        if h <= 0:
            return []
        return [(_pts([-a / 2.0, a / 2.0, b / 2.0, -b / 2.0], [-h / 2.0, -h / 2.0, h / 2.0, h / 2.0]), True)]
    if b <= 0:
        return []
    hb = b / 2.0
    angle = min(max(p["angle"], 1.0), 179.0)
    if kind == "Kite":
        xk = -a / 2.0 + hb / math.tan(math.radians(angle) / 2.0)
        return [(_pts([-a / 2.0, xk, a / 2.0, xk], [0.0, -hb, 0.0, hb]), True)]
    if kind == "Parallelogram":
        o = b / math.tan(math.radians(angle))
        return [(_pts([-a / 2.0, a / 2.0, a / 2.0 + o, -a / 2.0 + o], [-hb, -hb, hb, hb]), True)]
    return [(_pts([-a / 2.0, 0.0, a / 2.0, 0.0], [0.0, -hb, 0.0, hb]), True)]


def _star_chains(p: dict) -> list:
    ro, ri, n = p["outer_radius"], p["inner_radius"], p["points"]
    if ro <= 0 or ri <= 0:
        return []
    k = np.arange(2 * n)
    rad = np.where(k % 2 == 0, ro, ri)
    deg = 90.0 + 180.0 * k / n + np.where(k % 2 == 1, p["twist"], 0.0)
    return [(_polar(rad, deg), True)]


def _cogwheel_chains(p: dict) -> list:
    n, r0, r1 = p["teeth"], p["root_radius"], p["addendum_radius"]
    if n < 3 or r0 <= 0 or r1 <= r0:
        return []
    pitch = 360.0 / n
    w = pitch * min(max(p["tooth_width"] / 100.0, 0.0), MAX_TOOTH_WIDTH)
    bevel = min(max(p["bevel"] / 100.0, 0.0), 1.0)
    rows: list[np.ndarray] = []
    for k in range(n):
        c = k * pitch
        t1 = _at(r1, c - w / 2.0)
        t2 = _at(r1, c + w / 2.0)
        g_prev = _at(r0, c - pitch / 2.0)
        g_next = _at(r0, c + pitch / 2.0)
        if bevel > 0.0 and w > 0.0:
            s = bevel * 0.5 * min(np.linalg.norm(g_prev - t1), np.linalg.norm(t2 - t1))
            rows.append(t1 + _unit(g_prev - t1) * s)
            rows.append(t1 + _unit(t2 - t1) * s)
            rows.append(t2 + _unit(t1 - t2) * s)
            rows.append(t2 + _unit(g_next - t2) * s)
        else:
            rows.append(t1)
            rows.append(t2)
        rows.append(g_next)
    return [(np.array(rows), True)]


def _simplify(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    cur = [np.array(q, float) for q in pts]
    scale = max(float(np.ptp([q[0] for q in pts])), float(np.ptp([q[1] for q in pts])), 1e-12)
    eps = 1e-9 * scale
    changed = True
    while changed and len(cur) >= 3:
        changed = False
        for i in range(len(cur)):
            prev, here, nxt = cur[i - 1], cur[i], cur[(i + 1) % len(cur)]
            a, c = here - prev, nxt - here
            turn = a[0] * c[1] - a[1] * c[0]
            if np.linalg.norm(a) <= eps or abs(turn) <= eps * (np.linalg.norm(a) + np.linalg.norm(c)):
                del cur[i]
                changed = True
                break
    return [(float(q[0]), float(q[1])) for q in cur]


def _profile_chains(p: dict) -> list:
    kind, h, b, s, t = p["type"], p["height"], p["b"], p["s"], p["t"]
    if h <= 0 or b <= 0:
        return []
    hw, hh = b / 2.0, h / 2.0
    if kind == "L Shape":
        s, t = min(s, b), min(t, h)
        pts = [(-hw, -hh), (hw, -hh), (hw, -hh + t), (-hw + s, -hh + t), (-hw + s, hh), (-hw, hh)]
    elif kind == "T Shape":
        s, t = min(s, b), min(t, h)
        pts = [(-hw, hh), (hw, hh), (hw, hh - t), (s / 2.0, hh - t), (s / 2.0, -hh),
               (-s / 2.0, -hh), (-s / 2.0, hh - t), (-hw, hh - t)]
    elif kind == "U Shape":
        s, t = min(s, b / 2.0), min(t, h)
        pts = [(-hw, hh), (-hw, -hh), (hw, -hh), (hw, hh), (hw - s, hh), (hw - s, -hh + t),
               (-hw + s, -hh + t), (-hw + s, hh)]
    elif kind == "Z Shape":
        s, t = min(s, b), min(t, hh)
        pts = [(-hw, hh), (s / 2.0, hh), (s / 2.0, -hh + t), (hw, -hh + t), (hw, -hh), (-s / 2.0, -hh),
               (-s / 2.0, hh - t), (-hw, hh - t)]
    else:
        s, t = min(s, b), min(t, hh)
        pts = [(-hw, -hh), (hw, -hh), (hw, -hh + t), (s / 2.0, -hh + t), (s / 2.0, hh - t), (hw, hh - t),
               (hw, hh), (-hw, hh), (-hw, hh - t), (-s / 2.0, hh - t), (-s / 2.0, -hh + t), (-hw, -hh + t)]
    pts = _simplify(pts)
    if len(pts) < 3 or len({(round(q[0], 9), round(q[1], 9)) for q in pts}) != len(pts):
        return []
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    if abs(area) <= 1e-9 * h * b:
        return []
    return [(_pts([q[0] for q in pts], [q[1] for q in pts]), True)]


_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    name: getattr(np, name)
    for name in ("sin", "cos", "tan", "arcsin", "arccos", "arctan", "arctan2", "sinh", "cosh", "tanh",
                 "exp", "log", "log10", "sqrt", "abs", "floor", "ceil", "hypot", "power",
                 "minimum", "maximum")
}
_ARITY = {name: 2 if name in ("arctan2", "hypot", "power", "minimum", "maximum") else 1 for name in _FUNCTIONS}


def _eval_node(node: ast.AST, env: dict, expr: str):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_eval_node(node.left, env, expr), _eval_node(node.right, env, expr))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand, env, expr))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCTIONS and not node.keywords             and len(node.args) == _ARITY[node.func.id]:
        return _FUNCTIONS[node.func.id](*[_eval_node(arg, env, expr) for arg in node.args])
    raise ValueError(f"unsupported part of expression {expr!r}")


def _evaluate(expr: str, env: dict, shape: tuple) -> np.ndarray:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        raise ValueError(f"invalid expression {expr!r}") from None
    except (RecursionError, MemoryError):
        raise ValueError(f"expression {expr!r} is too complex") from None
    env = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in env.items()}
    try:
        with np.errstate(all="ignore"):
            value = _eval_node(tree.body, env, expr)
            if np.iscomplexobj(value):
                raise ValueError(f"expression {expr!r} gives complex values")
            out = np.broadcast_to(np.asarray(value, dtype=float), shape).copy()
    except RecursionError:
        raise ValueError(f"expression {expr!r} is too complex") from None
    except (ArithmeticError, TypeError) as exc:
        raise ValueError(f"expression {expr!r} cannot be evaluated: {exc}") from None
    if not np.all(np.isfinite(out)):
        raise ValueError(f"expression {expr!r} gives values that are not finite")
    return out


def _formula_chains(p: dict) -> list:
    t = np.linspace(p["tmin"], p["tmax"], p["samples"])
    env = {"t": t, "pi": math.pi, "e": math.e}
    x = _evaluate(p["x_expr"], env, t.shape)
    y = _evaluate(p["y_expr"], env, t.shape)
    z = _evaluate(p["z_expr"], env, t.shape)
    return [(_pts(x, y, z), False)]


def _helix_chains(p: dict) -> list:
    r0, r1, n = p["start_radius"], p["end_radius"], p["subdivision"]
    if max(r0, r1) <= 0:
        return []
    t = np.linspace(p["start_angle"], p["end_angle"], n + 1)
    pts = _polar(np.linspace(r0, r1, n + 1), t)
    pts[:, 2] = np.linspace(0.0, p["height"], n + 1)
    return [(pts, False)]


def _cissoid_chains(p: dict) -> list:
    w, kind, s = p["width"], p["type"], p["points_per_90"]
    if w <= 0:
        return []
    if kind == "Lemniscate":
        c = w / 2.0
        n = 4 * s + 2
        t = 2.0 * math.pi * np.arange(n) / n
        den = 1.0 + np.sin(t) ** 2
        return [(_pts(c * np.cos(t) / den, c * np.sin(t) * np.cos(t) / den), True)]
    if kind == "Strophoid":
        steps = max(4, s + s % 2)
        t = np.linspace(-math.pi / 4.0, math.pi / 4.0, steps + 1)
        return [(_pts(-w * np.cos(2.0 * t), -w * np.tan(t) * np.cos(2.0 * t)), True)]
    if p["tension"] <= 0:
        return []
    m = min(math.atan(p["tension"] / 6.0), math.radians(89.0))
    t = np.linspace(-m, m, _seg(math.degrees(2.0 * m), s) + 1)
    return [(_pts(w * np.sin(t) ** 2, w * np.sin(t) ** 3 / np.cos(t)), False)]


def _cycloid_chains(p: dict) -> list:
    big, r, d, kind = p["radius"], p["r"], p["a"], p["type"]
    if r <= 0:
        return []
    n = _seg(p["end_angle"] - p["start_angle"], p["points_per_90"])
    phi = np.radians(np.linspace(p["start_angle"], p["end_angle"], n + 1))
    if kind == "Epicycloid":
        k = (big + r) / r
        x = (big + r) * np.cos(phi) - d * np.cos(k * phi)
        y = (big + r) * np.sin(phi) - d * np.sin(k * phi)
    elif kind == "Hypocycloid":
        k = (big - r) / r
        x = (big - r) * np.cos(phi) + d * np.cos(k * phi)
        y = (big - r) * np.sin(phi) - d * np.sin(k * phi)
    else:
        x = r * phi - d * np.sin(phi)
        y = -big + r - d * np.cos(phi)
    return [(_pts(x, y), False)]


def _flower_chains(p: dict) -> list:
    ri, ro, k = p["inner_radius"], p["outer_radius"], p["petals"]
    if ri <= 0 or ro <= 0:
        return []
    n = 4 * p["points_per_90"] * k
    t = np.linspace(0.0, 360.0, n, endpoint=False)
    r = ri + (ro - ri) * (1.0 + np.cos(np.radians(k * t))) / 2.0
    return [(_polar(r, t), True)]


def _build_rectangle(p: dict, _inputs: list) -> Mesh:
    return _finish(_rectangle_chains(p), p)


def _build_circle(p: dict, _inputs: list) -> Mesh:
    return _finish(_circle_chains(p), p)


def _build_arc(p: dict, _inputs: list) -> Mesh:
    return _finish(_arc_chains(p), p)


def _build_nside(p: dict, _inputs: list) -> Mesh:
    return _finish(_nside_chains(p), p)


def _build_four_side(p: dict, _inputs: list) -> Mesh:
    return _finish(_four_side_chains(p), p)


def _build_star(p: dict, _inputs: list) -> Mesh:
    return _finish(_star_chains(p), p)


def _build_cogwheel(p: dict, _inputs: list) -> Mesh:
    return _finish(_cogwheel_chains(p), p)


def _build_profile(p: dict, _inputs: list) -> Mesh:
    return _finish(_profile_chains(p), p)


def _build_cissoid(p: dict, _inputs: list) -> Mesh:
    return _finish(_cissoid_chains(p), p)


def _build_cycloid(p: dict, _inputs: list) -> Mesh:
    return _finish(_cycloid_chains(p), p)


def _build_formula(p: dict, _inputs: list) -> Mesh:
    return _finish(_formula_chains(p), p)


def _build_helix(p: dict, _inputs: list) -> Mesh:
    return _finish(_helix_chains(p), p)


def _build_flower(p: dict, _inputs: list) -> Mesh:
    return _finish(_flower_chains(p), p)


register(ObjectSpec(
    id="rectangle", label="Rectangle", category="spline", build=_build_rectangle,
    params=(
        Param("width", "Width", "distance", 400.0, minimum=0.0, group="Object"),
        Param("height", "Height", "distance", 400.0, minimum=0.0, group="Object"),
        Param("rounding", "Rounding", "bool", False, group="Object"),
        Param("radius", "Radius", "distance", 50.0, minimum=0.0, group="Object"),
    ) + _tail(True),
    icon="rectangle", description="Rectangle spline with optional rounded corners"))

register(ObjectSpec(
    id="circle", label="Circle", category="spline", build=_build_circle,
    params=(
        Param("ellipse", "Ellipse", "bool", False, group="Object"),
        Param("ring", "Ring", "bool", False, group="Object"),
        Param("radius", "Radius", "distance", 200.0, minimum=0.0, group="Object"),
        Param("radius_y", "Radius Y", "distance", 200.0, minimum=0.0, group="Object"),
        Param("inner_radius", "Inner Radius", "distance", 100.0, minimum=0.0, group="Object"),
    ) + _tail(True),
    icon="circle", description="Circle, ellipse or ring spline"))

register(ObjectSpec(
    id="arc", label="Arc", category="spline", build=_build_arc,
    params=(
        Param("type", "Type", "choice", "Arc", choices=ARC_TYPES, group="Object"),
        Param("radius", "Radius", "distance", 200.0, minimum=0.0, group="Object"),
        Param("inner_radius", "Inner Radius", "distance", 100.0, minimum=0.0, group="Object"),
        Param("start_angle", "Start Angle", "angle", 0.0, group="Object"),
        Param("end_angle", "End Angle", "angle", 90.0, group="Object"),
    ) + _tail(True),
    icon="arc", description="Arc, sector, segment or ring spline"))

register(ObjectSpec(
    id="n_side", label="n-Side", category="spline", build=_build_nside,
    params=(
        Param("radius", "Radius", "distance", 200.0, minimum=0.0, group="Object"),
        Param("sides", "Sides", "int", 6, minimum=3, maximum=1000, group="Object"),
        Param("rounding", "Rounding", "bool", False, group="Object"),
        Param("rounding_radius", "Radius", "distance", 50.0, minimum=0.0, group="Object"),
    ) + _tail(True),
    icon="n_side", description="Regular polygon spline with optional rounded corners"))

register(ObjectSpec(
    id="four_side", label="4-Side", category="spline", build=_build_four_side,
    params=(
        Param("type", "Type", "choice", "Diamond", choices=FOUR_SIDE_TYPES, group="Object"),
        Param("a", "A", "distance", 400.0, minimum=0.0, group="Object"),
        Param("b", "B", "distance", 200.0, minimum=0.0, group="Object"),
        Param("angle", "Angle", "angle", 30.0, group="Object"),
    ) + _tail(False),
    icon="four_side", description="Diamond, kite, parallelogram or trapezium spline"))

register(ObjectSpec(
    id="star", label="Star", category="spline", build=_build_star,
    params=(
        Param("inner_radius", "Inner Radius", "distance", 100.0, minimum=0.0, group="Object"),
        Param("outer_radius", "Outer Radius", "distance", 200.0, minimum=0.0, group="Object"),
        Param("twist", "Twist", "angle", 0.0, group="Object"),
        Param("points", "Points", "int", 8, minimum=3, maximum=1000, group="Object"),
    ) + _tail(False),
    icon="star", description="Star spline with alternating outer and inner points"))

register(ObjectSpec(
    id="cogwheel", label="Cogwheel", category="spline", build=_build_cogwheel,
    params=(
        Param("teeth", "Teeth", "int", 12, minimum=3, maximum=1000, group="Object"),
        Param("root_radius", "Root Radius", "distance", 150.0, minimum=0.0, group="Object"),
        Param("addendum_radius", "Addendum Radius", "distance", 200.0, minimum=0.0, group="Object"),
        Param("tooth_width", "Tooth Width", "percent", 50.0, minimum=0.0, maximum=100.0, unit="%",
              group="Object"),
        Param("bevel", "Bevel", "percent", 0.0, minimum=0.0, maximum=100.0, unit="%", group="Object"),
    ) + _tail(False),
    icon="cogwheel", description="Simplified gear outline"))

register(ObjectSpec(
    id="profile", label="Profile", category="spline", build=_build_profile,
    params=(
        Param("type", "Type", "choice", "H Shape", choices=PROFILE_TYPES, group="Object"),
        Param("height", "Height", "distance", 200.0, minimum=0.0, group="Object"),
        Param("b", "B", "distance", 100.0, minimum=0.0, group="Object"),
        Param("s", "S", "distance", 20.0, minimum=0.0, group="Object"),
        Param("t", "T", "distance", 20.0, minimum=0.0, group="Object"),
    ) + _tail(False),
    icon="profile", description="H, L, T, U or Z section outline"))

register(ObjectSpec(
    id="cissoid", label="Cissoid", category="spline", build=_build_cissoid,
    params=(
        Param("type", "Type", "choice", "Cissoid", choices=CISSOID_TYPES, group="Object"),
        Param("width", "Width", "distance", 400.0, minimum=0.0, group="Object"),
        Param("tension", "Tension", "float", 6.0, minimum=0.0, maximum=60.0, step=0.1, group="Object"),
    ) + _tail(True),
    icon="cissoid", description="Cissoid, lemniscate or strophoid curve"))

register(ObjectSpec(
    id="cycloid", label="Cycloid", category="spline", build=_build_cycloid,
    params=(
        Param("type", "Type", "choice", "Cycloid", choices=CYCLOID_TYPES, group="Object"),
        Param("radius", "Radius", "distance", 100.0, minimum=0.0, group="Object"),
        Param("r", "r", "distance", 40.0, minimum=0.0, group="Object"),
        Param("a", "a", "distance", 40.0, minimum=0.0, group="Object"),
        Param("start_angle", "Start Angle", "angle", 0.0, group="Object"),
        Param("end_angle", "End Angle", "angle", 720.0, group="Object"),
    ) + _tail(True),
    icon="cycloid", description="Cycloid, epicycloid or hypocycloid curve"))

register(ObjectSpec(
    id="formula", label="Formula", category="spline", build=_build_formula,
    params=(
        Param("x_expr", "X(t)", "text", "100.0*t", group="Object"),
        Param("y_expr", "Y(t)", "text", "100.0*sin(t*pi)", group="Object"),
        Param("z_expr", "Z(t)", "text", "0.0", group="Object"),
        Param("tmin", "Tmin", "float", -1.0, group="Object"),
        Param("tmax", "Tmax", "float", 1.0, group="Object"),
        Param("samples", "Samples", "int", 20, minimum=2, maximum=5000, group="Object"),
    ) + _tail(False),
    icon="formula", description="Curve from X(t), Y(t) and Z(t) expressions"))

register(ObjectSpec(
    id="helix", label="Helix", category="spline", build=_build_helix,
    params=(
        Param("start_radius", "Start Radius", "distance", 200.0, minimum=0.0, group="Object"),
        Param("end_radius", "End Radius", "distance", 200.0, minimum=0.0, group="Object"),
        Param("start_angle", "Start Angle", "angle", 0.0, group="Object"),
        Param("end_angle", "End Angle", "angle", 720.0, group="Object"),
        Param("height", "Height", "distance", 200.0, group="Object"),
        Param("subdivision", "Subdivision", "int", 100, minimum=1, maximum=5000, group="Object"),
    ) + _tail(False),
    icon="helix", description="Open spiral along the plane normal"))

register(ObjectSpec(
    id="flower", label="Flower", category="spline", build=_build_flower,
    params=(
        Param("inner_radius", "Inner Radius", "distance", 100.0, minimum=0.0, group="Object"),
        Param("outer_radius", "Outer Radius", "distance", 200.0, minimum=0.0, group="Object"),
        Param("petals", "Petals", "int", 8, minimum=1, maximum=100, group="Object"),
    ) + _tail(True),
    icon="flower", description="Closed petal outline"))
