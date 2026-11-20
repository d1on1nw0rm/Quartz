from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

__all__ = ["FALLOFFS", "DEFAULT_CURVE", "clean_curve", "evaluate", "sample", "insert_point",
           "remove_point", "move_point"]

FALLOFFS = ("smooth", "linear", "constant", "spherical", "sharp", "custom")

DEFAULT_CURVE: tuple[tuple[float, float], ...] = ((0.0, 1.0), (0.5, 0.5), (1.0, 0.0))


def clean_curve(points: Iterable[Sequence[float]] | None) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for p in points or ():
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        pts.append((min(1.0, max(0.0, x)), min(1.0, max(0.0, y))))
    pts.sort(key=lambda q: q[0])
    out: list[tuple[float, float]] = []
    for x, y in pts:
        if out and abs(out[-1][0] - x) < 1e-6:
            out[-1] = (out[-1][0], y)
        else:
            out.append((x, y))
    if not out:
        return list(DEFAULT_CURVE)
    if out[0][0] > 0.0:
        out.insert(0, (0.0, out[0][1]))
    if out[-1][0] < 1.0:
        out.append((1.0, out[-1][1]))
    return out


def _custom(t: np.ndarray, curve: Sequence[Sequence[float]]) -> np.ndarray:
    pts = clean_curve(curve)
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    if len(xs) < 3:
        return np.interp(t, xs, ys)
    h = np.diff(xs)
    h[h < 1e-9] = 1e-9
    delta = np.diff(ys) / h
    m = np.zeros(len(xs))
    m[0], m[-1] = delta[0], delta[-1]
    for i in range(1, len(xs) - 1):
        if delta[i - 1] * delta[i] <= 0:
            m[i] = 0.0
        else:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    k = np.clip(np.searchsorted(xs, t, side="right") - 1, 0, len(xs) - 2)
    s = (t - xs[k]) / h[k]
    s2, s3 = s * s, s * s * s
    h00 = 2 * s3 - 3 * s2 + 1
    h10 = s3 - 2 * s2 + s
    h01 = -2 * s3 + 3 * s2
    h11 = s3 - s2
    out = h00 * ys[k] + h10 * h[k] * m[k] + h01 * ys[k + 1] + h11 * h[k] * m[k + 1]
    return np.clip(out, 0.0, 1.0)


def evaluate(kind: str, t, curve: Sequence[Sequence[float]] | None = None) -> np.ndarray:
    x = np.clip(np.asarray(t, float), 0.0, 1.0)
    if kind == "linear":
        out = 1.0 - x
    elif kind == "constant":
        out = np.ones_like(x)
    elif kind == "spherical":
        out = np.sqrt(np.maximum(0.0, 1.0 - x * x))
    elif kind == "sharp":
        out = (1.0 - x) ** 2
    elif kind == "custom":
        out = _custom(x, curve if curve is not None else DEFAULT_CURVE)
    else:
        out = 1.0 - x * x * (3.0 - 2.0 * x)
    out = np.where(np.asarray(t, float) > 1.0, 0.0, out)
    return np.clip(out, 0.0, 1.0)


def sample(kind: str, count: int = 64, curve: Sequence[Sequence[float]] | None = None) -> np.ndarray:
    xs = np.linspace(0.0, 1.0, max(2, int(count)))
    return np.column_stack([xs, evaluate(kind, xs, curve)])


def insert_point(curve: Sequence[Sequence[float]], x: float, y: float) -> list[tuple[float, float]]:
    return clean_curve(list(curve) + [(x, y)])


def remove_point(curve: Sequence[Sequence[float]], index: int) -> list[tuple[float, float]]:
    pts = clean_curve(curve)
    if 0 < index < len(pts) - 1:
        pts.pop(index)
    return pts


def move_point(curve: Sequence[Sequence[float]], index: int, x: float, y: float) -> list[tuple[float, float]]:
    pts = clean_curve(curve)
    if not 0 <= index < len(pts):
        return pts
    y = min(1.0, max(0.0, float(y)))
    if index == 0:
        pts[0] = (0.0, y)
    elif index == len(pts) - 1:
        pts[-1] = (1.0, y)
    else:
        lo = pts[index - 1][0] + 1e-3
        hi = pts[index + 1][0] - 1e-3
        pts[index] = (min(hi, max(lo, float(x))), y)
    return pts
