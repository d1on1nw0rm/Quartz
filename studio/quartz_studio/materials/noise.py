from __future__ import annotations

import numpy as np

__all__ = [
    "hash_u32",
    "hash_cells",
    "rand01",
    "value_noise",
    "perlin_noise",
    "fractal",
    "voronoi",
    "NOISE_TYPES",
]

NOISE_TYPES = ("value", "perlin", "fbm", "turbulence", "ridged")

_GRADS = np.array([
    (1, 1, 0), (-1, 1, 0), (1, -1, 0), (-1, -1, 0),
    (1, 0, 1), (-1, 0, 1), (1, 0, -1), (-1, 0, -1),
    (0, 1, 1), (0, -1, 1), (0, 1, -1), (0, -1, -1),
    (1, 1, 0), (-1, 1, 0), (0, -1, 1), (0, -1, -1),
], float)


def _u32(x) -> np.ndarray:
    return (np.asarray(x, np.int64) & 0xFFFFFFFF).astype(np.uint32)


def hash_u32(x) -> np.ndarray:
    with np.errstate(over="ignore"):
        h = np.array(_u32(x), np.uint32, copy=True)
        h ^= h >> np.uint32(16)
        h *= np.uint32(0x7FEB352D)
        h ^= h >> np.uint32(15)
        h *= np.uint32(0x846CA68B)
        h ^= h >> np.uint32(16)
    return h


def hash_cells(ix, iy, iz, seed: int = 0, salt: int = 0) -> np.ndarray:
    base = (int(seed) * 7919 + int(salt) * 104729 + 1) & 0xFFFFFFFF
    h = hash_u32(np.full(np.shape(ix), base, np.int64))
    h = hash_u32(h.astype(np.int64) + _u32(iz).astype(np.int64))
    h = hash_u32(h.astype(np.int64) + _u32(iy).astype(np.int64))
    h = hash_u32(h.astype(np.int64) + _u32(ix).astype(np.int64))
    return h


def rand01(ix, iy, iz, seed: int = 0, salt: int = 0) -> np.ndarray:
    return hash_cells(ix, iy, iz, seed, salt).astype(np.float64) / 4294967295.0


def _fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _split(p):
    p = np.asarray(p, float)
    cell = np.floor(p)
    return cell.astype(np.int64), p - cell


def value_noise(p, seed: int = 0) -> np.ndarray:
    p = np.atleast_2d(np.asarray(p, float))
    cell, f = _split(p)
    w = _fade(f)
    out = np.zeros(len(p))
    for dx in (0, 1):
        wx = w[:, 0] if dx else 1.0 - w[:, 0]
        for dy in (0, 1):
            wy = w[:, 1] if dy else 1.0 - w[:, 1]
            for dz in (0, 1):
                wz = w[:, 2] if dz else 1.0 - w[:, 2]
                r = rand01(cell[:, 0] + dx, cell[:, 1] + dy, cell[:, 2] + dz, seed)
                out += wx * wy * wz * r
    return out


def perlin_noise(p, seed: int = 0) -> np.ndarray:
    p = np.atleast_2d(np.asarray(p, float))
    cell, f = _split(p)
    w = _fade(f)
    out = np.zeros(len(p))
    for dx in (0, 1):
        wx = w[:, 0] if dx else 1.0 - w[:, 0]
        for dy in (0, 1):
            wy = w[:, 1] if dy else 1.0 - w[:, 1]
            for dz in (0, 1):
                wz = w[:, 2] if dz else 1.0 - w[:, 2]
                h = hash_cells(cell[:, 0] + dx, cell[:, 1] + dy, cell[:, 2] + dz, seed) & np.uint32(15)
                g = _GRADS[h.astype(np.int64)]
                d = f - np.array([dx, dy, dz], float)
                out += wx * wy * wz * np.sum(g * d, axis=1)
    return out


def fractal(p, noise_type: str = "fbm", octaves: float = 4.0, roughness: float = 0.5,
            lacunarity: float = 2.0, distortion: float = 0.0, seed: int = 0) -> np.ndarray:
    p = np.atleast_2d(np.asarray(p, float))
    seed = int(seed)
    if distortion:
        offs = np.stack([perlin_noise(p + 13.7, seed + 11), perlin_noise(p + 41.3, seed + 23),
                         perlin_noise(p + 71.9, seed + 37)], axis=1)
        p = p + offs * float(distortion)
    if noise_type == "value":
        return value_noise(p, seed)
    if noise_type == "perlin":
        return np.clip(0.5 + 0.5 * perlin_noise(p, seed), 0.0, 1.0)
    octaves = max(0.0, float(octaves))
    whole = int(np.floor(octaves))
    frac = octaves - whole
    total = np.zeros(len(p))
    norm = 0.0
    amp = 1.0
    freq = 1.0
    for k in range(whole + 1):
        weight = amp if k < whole else amp * frac
        if k == 0:
            weight = amp
        if weight <= 0.0:
            break
        n = perlin_noise(p * freq, seed + k * 101)
        if noise_type == "turbulence":
            n = np.abs(n)
        elif noise_type == "ridged":
            n = (1.0 - np.abs(n)) ** 2
        else:
            n = 0.5 + 0.5 * n
        total += weight * n
        norm += weight
        amp *= float(roughness)
        freq *= float(lacunarity)
    if norm <= 0.0:
        return np.full(len(p), 0.5)
    out = total / norm
    if noise_type == "turbulence":
        out = out * 1.6
    return np.clip(out, 0.0, 1.0)


def _metric(d: np.ndarray, metric: str) -> np.ndarray:
    if metric == "manhattan":
        return np.sum(np.abs(d), axis=-1)
    if metric == "chebyshev":
        return np.max(np.abs(d), axis=-1)
    return np.sqrt(np.sum(d * d, axis=-1))


def voronoi(p, randomness: float = 1.0, metric: str = "euclidean", seed: int = 0,
            dims: int = 3) -> dict:
    p = np.array(np.atleast_2d(np.asarray(p, float)), copy=True)
    seed = int(seed)
    if dims == 2:
        p[:, 2] = 0.0
    cell, f = _split(p)
    n = len(p)
    f1 = np.full(n, np.inf)
    f2 = np.full(n, np.inf)
    id1 = np.zeros((n, 3), np.int64)
    pos1 = np.zeros((n, 3))
    zr = (0,) if dims == 2 else (-1, 0, 1)
    jitter = float(np.clip(randomness, 0.0, 1.0))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in zr:
                c = cell + np.array([dx, dy, dz])
                j = np.stack([rand01(c[:, 0], c[:, 1], c[:, 2], seed, 1),
                              rand01(c[:, 0], c[:, 1], c[:, 2], seed, 2),
                              rand01(c[:, 0], c[:, 1], c[:, 2], seed, 3)], axis=1)
                feature = np.array([dx, dy, dz], float) + 0.5 + (j - 0.5) * jitter
                if dims == 2:
                    feature[:, 2] = 0.0
                d = _metric(feature - f, metric)
                closer = d < f1
                second = (~closer) & (d < f2)
                f2 = np.where(closer, f1, np.where(second, d, f2))
                f1 = np.where(closer, d, f1)
                id1 = np.where(closer[:, None], c, id1)
                pos1 = np.where(closer[:, None], cell + feature, pos1)
    color = np.stack([rand01(id1[:, 0], id1[:, 1], id1[:, 2], seed, 5),
                      rand01(id1[:, 0], id1[:, 1], id1[:, 2], seed, 6),
                      rand01(id1[:, 0], id1[:, 1], id1[:, 2], seed, 7)], axis=1)
    return {"f1": f1, "f2": f2, "cell": id1, "color": color, "position": pos1}
