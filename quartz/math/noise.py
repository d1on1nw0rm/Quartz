import random as _random
import numpy as np
from quartz.math.vector import Vector

_DEFAULT_SEED = 0
_seed = _DEFAULT_SEED
_rng = _random.Random(_DEFAULT_SEED)
_F32_BELOW_ONE = float(np.nextafter(np.float32(1.0), np.float32(0.0)))


def random():
    return _rng.random()


def seed_set(seed):
    global _seed
    _seed = int(seed)
    _rng.seed(_seed)


def random_unit_vector(size=3):
    while True:
        v = np.array([_rng.gauss(0.0, 1.0) for _ in range(size)], dtype=np.float64)
        n = float(np.linalg.norm(v))
        if n > 1e-12:
            return Vector((v / n).astype(np.float32).tolist())


def random_vector(size=3):
    vals = []
    for _ in range(size):
        c = float(np.float32(2.0 * _rng.random() - 1.0))
        vals.append(min(c, _F32_BELOW_ONE))
    return Vector(vals)


def _not_implemented(name):
    def _fn(*a, **k):
        raise NotImplementedError(f"mathutils.noise.{name} is not implemented in Quartz")
    return _fn


for _name in ["noise", "noise_vector", "turbulence", "turbulence_vector",
              "fractal", "multi_fractal", "hetero_terrain", "hybrid_multi_fractal",
              "ridged_multi_fractal", "variable_lacunarity", "voronoi", "cell",
              "cell_vector"]:
    globals()[_name] = _not_implemented(_name)
