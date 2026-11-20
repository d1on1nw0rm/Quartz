from __future__ import annotations

import numpy as np

from ..modeling import trunk_skin
from ..scene import Mesh
from .registry import ObjectSpec, Param, register

MIN_RADIUS = 1e-3
ROOTS = ("First Point", "Lowest Point")
ROOT_KEYS = {"First Point": "first", "Lowest Point": "lowest"}


def _edge_array(points: np.ndarray, loose) -> np.ndarray:
    e = np.asarray(list(loose), dtype=np.int64).reshape(-1, 2)
    n = len(points)
    ok = (e[:, 0] != e[:, 1]) & (e.min(axis=1) >= 0) & (e.max(axis=1) < n)
    e = e[ok]
    if len(e) == 0:
        return e
    e = np.unique(np.sort(e, axis=1), axis=0)
    lengths = np.linalg.norm(points[e[:, 1]] - points[e[:, 0]], axis=1)
    return e[lengths > 0.0]


def trunk_radii(points: np.ndarray, edges: np.ndarray, base: float, tip: float, taper: float,
                root: str, scales) -> np.ndarray:
    radii = trunk_skin.profile_radii(points, edges, base, tip, taper, root, scales)
    valence = np.bincount(edges.reshape(-1), minlength=len(points))
    inner = valence != 1
    radii[inner] = np.maximum(radii[inner], MIN_RADIUS)
    return radii


def build_trunk(p: dict, inputs: list) -> Mesh:
    base = float(p["base_radius"])
    tip = float(p["tip_radius"])
    if base <= 0.0 and tip <= 0.0:
        return Mesh.empty()
    sides = int(p["sides"])
    taper = float(p["taper"])
    caps = bool(p["caps"])
    root = ROOT_KEYS.get(str(p["root"]), "first")
    use_scales = bool(p["use_point_scales"])
    chunks: list[np.ndarray] = []
    polys: list[tuple[int, ...]] = []
    count = 0
    for inp in inputs:
        mesh = inp.mesh
        if not mesh.loose_edges:
            continue
        points = np.asarray(mesh.points, dtype=float).reshape(-1, 3)
        edges = _edge_array(points, mesh.loose_edges)
        if len(edges) == 0:
            continue
        scales = mesh.point_scale_array() if use_scales else None
        radii = trunk_radii(points, edges, base, tip, taper, root, scales)
        skin_points, skin_polys = trunk_skin.build_skin(points, edges.tolist(), radii, sides, caps)
        if len(skin_points) == 0 or not skin_polys:
            continue
        chunks.append(np.asarray(skin_points, dtype=float).reshape(-1, 3))
        polys.extend(tuple(int(i) + count for i in poly) for poly in skin_polys)
        count += len(skin_points)
    if not chunks:
        return Mesh.empty()
    return Mesh(np.vstack(chunks), polys)


register(ObjectSpec(
    id="trunk", label="Trunk", category="generator", build=build_trunk, inputs="children",
    params=(
        Param("sides", "Sides", "int", 8, minimum=3, maximum=64, step=1, group="Object"),
        Param("base_radius", "Base Radius", "distance", 10.0, minimum=0.0, maximum=1e6, step=0.5,
              unit="cm", group="Object"),
        Param("tip_radius", "Tip Radius", "distance", 2.0, minimum=0.0, maximum=1e6, step=0.5,
              unit="cm", group="Object"),
        Param("taper", "Taper", "float", 1.0, minimum=0.1, maximum=10.0, step=0.1, group="Object"),
        Param("caps", "Caps", "bool", True, group="Object"),
        Param("root", "Root", "choice", "First Point", choices=ROOTS, group="Object"),
        Param("use_point_scales", "Use Point Scales", "bool", True, group="Object"),
    ),
    icon="trunk",
    description="Gives every Line child the thickness of a trunk or twig."))
