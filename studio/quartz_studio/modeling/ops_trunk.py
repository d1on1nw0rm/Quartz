from __future__ import annotations

import numpy as np

from ..scene import Mesh
from .meshkit import OpResult, Selection, clone, compact, edge_key
from .registry import Param, ToolSpec, register
from .trunk_skin import build_skin, profile_radii

__all__ = ["trunk", "preview_wire", "MIN_RADIUS", "NO_LOOSE_EDGES", "NO_POINTS"]

MIN_RADIUS = 1e-3
ROOTS = {"First Point": "first", "Lowest Point": "lowest"}
NO_LOOSE_EDGES = "Trunk: the object has no loose edges"
NO_LOOSE_SELECTED = "Trunk: select loose edges of a Line"
BOTH_ZERO = "Trunk: Base Radius and Tip Radius are both 0"
NO_POINTS = "Trunk: select points to scale their thickness"
EMPTY_SKIN = "Trunk: the radii leave nothing to skin"


def _radii(mesh: Mesh, edges: list, p: dict) -> np.ndarray:
    radii = profile_radii(mesh.points, edges, float(p["base_radius"]), float(p["tip_radius"]),
                          float(p["taper"]), ROOTS.get(str(p["root"]), "first"),
                          scales=mesh.point_scale_array())
    radii = radii * (float(p["thickness"]) / 100.0)
    valence = np.zeros(len(mesh.points), int)
    for a, b in edges:
        valence[a] += 1
        valence[b] += 1
    inner = valence != 1
    radii[inner] = np.maximum(radii[inner], MIN_RADIUS)
    return radii


def _skin(mesh: Mesh, edges: list, p: dict) -> tuple[np.ndarray, list]:
    radii = _radii(mesh, edges, p)
    points, polygons = build_skin(mesh.points, edges, radii, int(p["sides"]), bool(p["caps"]))
    return np.asarray(points, float).reshape(-1, 3), list(polygons)


def _both_zero(p: dict) -> bool:
    return float(p["base_radius"]) <= 0.0 and float(p["tip_radius"]) <= 0.0


def _orphans(mesh: Mesh) -> list[int]:
    used = {int(i) for poly in mesh.polygons for i in poly}
    used |= {int(i) for e in mesh.loose_edges for i in e}
    return [i for i in range(len(mesh.points)) if i not in used]


def _trunk_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    if not mesh.loose_edges:
        return OpResult(mesh, sel, False, NO_LOOSE_EDGES)
    chosen_keys = {edge_key(*e) for e in sel.edges}
    if chosen_keys:
        chosen = [e for e in mesh.loose_edges if e in chosen_keys]
        if not chosen:
            return OpResult(mesh, sel, False, NO_LOOSE_SELECTED)
    else:
        chosen = list(mesh.loose_edges)
    if _both_zero(p):
        return OpResult(mesh, sel, False, BOTH_ZERO)
    skin_points, skin_polys = _skin(mesh, chosen, p)
    if not skin_polys:
        return OpResult(mesh, sel, False, EMPTY_SKIN)
    skinned = set(chosen)
    remaining = [e for e in mesh.loose_edges if e not in skinned]
    orphans = _orphans(mesh)
    stripped = Mesh(mesh.points, mesh.polygons, remaining, point_scales=mesh.point_scales)
    kept, _remap = compact(stripped, keep=orphans)
    offset = len(kept.points)
    polygons = list(kept.polygons) + [tuple(int(i) + offset for i in poly) for poly in skin_polys]
    scales = np.concatenate([kept.point_scale_array(), np.ones(len(skin_points))])
    result = Mesh(np.vstack([kept.points, skin_points]), polygons, kept.loose_edges,
                  point_scales=scales)
    return OpResult(result, Selection("edges"))


def _trunk_points(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    if not mesh.loose_edges:
        return OpResult(mesh, sel, False, NO_LOOSE_EDGES)
    picked = sorted(i for i in sel.points if 0 <= int(i) < len(mesh.points))
    if not picked:
        return OpResult(mesh, sel, False, NO_POINTS)
    out = clone(mesh)
    scales = out.point_scale_array()
    scales[picked] = scales[picked] * (float(p["point_scale"]) / 100.0)
    out.point_scales = scales
    return OpResult(out, sel)


def trunk(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    if sel.mode == "edges":
        return _trunk_edges(mesh, sel, p)
    if sel.mode == "points":
        return _trunk_points(mesh, sel, p)
    return OpResult(mesh, sel, False, "Trunk: select edges or points first")


def preview_wire(mesh: Mesh, params: dict) -> tuple[np.ndarray, np.ndarray]:
    empty = np.zeros((0, 3)), np.zeros((0, 2), int)
    if not mesh.loose_edges or _both_zero(params):
        return empty
    points, polygons = _skin(mesh, list(mesh.loose_edges), params)
    if not polygons:
        return empty
    pairs: set[tuple[int, int]] = set()
    for poly in polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            pairs.add((a, b) if a < b else (b, a))
    edges = np.array(sorted(pairs), int).reshape(-1, 2)
    return points, edges


register(ToolSpec(
    id="trunk",
    name="Trunk",
    apply=trunk,
    modes=("edges", "points"),
    params=(
        Param("sides", "Sides", "int", 8, 3, 64, 1),
        Param("base_radius", "Base Radius", "distance", 10.0, 0.0, 1e6, 0.5, "cm"),
        Param("tip_radius", "Tip Radius", "distance", 2.0, 0.0, 1e6, 0.5, "cm"),
        Param("taper", "Taper", "float", 1.0, 0.1, 10.0, 0.1),
        Param("caps", "Caps", "bool", True),
        Param("root", "Root", "choice", "First Point", choices=("First Point", "Lowest Point")),
        Param("thickness", "Thickness", "percent", 100.0, 1.0, 10000.0, 1.0, "%"),
        Param("point_scale", "Point Scale", "percent", 100.0, 1.0, 10000.0, 1.0, "%",
              modes=("points",)),
    ),
    drag_param="thickness",
    drag_kind="percent",
    shortcut="M~R",
    description="Gives a Line the thickness of a trunk or twig, with a clean quad skin.",
    extra={"drag_params": {"edges": "thickness", "points": "point_scale"},
           "drag_from_default": ("point_scale",),
           "preview": "skin_wire"},
))
