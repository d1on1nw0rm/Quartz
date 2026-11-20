from __future__ import annotations

import numpy as np

__all__ = ["INTERPOLATIONS", "DEFAULT_RAMP", "normalize_ramp", "evaluate_ramp", "add_stop", "remove_stop"]

INTERPOLATIONS = ("linear", "constant", "ease")

DEFAULT_RAMP = [[0.0, [0.0, 0.0, 0.0, 1.0]], [1.0, [1.0, 1.0, 1.0, 1.0]]]


def normalize_ramp(stops) -> list:
    out = []
    for stop in stops or DEFAULT_RAMP:
        pos = float(np.clip(float(stop[0]), 0.0, 1.0))
        col = [float(x) for x in stop[1]]
        if len(col) == 3:
            col.append(1.0)
        out.append([pos, col[:4]])
    out.sort(key=lambda s: s[0])
    return out


def evaluate_ramp(stops, t, interpolation: str = "linear") -> np.ndarray:
    stops = normalize_ramp(stops)
    t = np.atleast_1d(np.asarray(t, float))
    pos = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops])
    if len(stops) == 1:
        return np.broadcast_to(cols[0], (len(t), 4)).copy()
    tc = np.clip(t, pos[0], pos[-1])
    if interpolation == "constant":
        idx = np.searchsorted(pos, t, side="right") - 1
        idx = np.clip(idx, 0, len(pos) - 1)
        return cols[idx]
    hi = np.clip(np.searchsorted(pos, tc, side="right"), 1, len(pos) - 1)
    lo = hi - 1
    span = pos[hi] - pos[lo]
    f = np.where(span > 1e-12, (tc - pos[lo]) / np.where(span > 1e-12, span, 1.0), 0.0)
    f = np.where(tc >= pos[-1], 1.0, f)
    if interpolation == "ease":
        f = f * f * (3.0 - 2.0 * f)
    return cols[lo] * (1.0 - f)[:, None] + cols[hi] * f[:, None]


def add_stop(stops, position: float, color=None) -> list:
    stops = normalize_ramp(stops)
    if color is None:
        color = evaluate_ramp(stops, [position])[0].tolist()
    stops.append([float(position), list(color)])
    return normalize_ramp(stops)


def remove_stop(stops, index: int) -> list:
    stops = normalize_ramp(stops)
    if len(stops) <= 1:
        return stops
    stops.pop(int(index))
    return stops
