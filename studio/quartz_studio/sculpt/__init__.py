from __future__ import annotations

from . import data, falloff, stamps, subdivision, topology
from .brushes import BRUSH_ORDER, BRUSHES, BrushDef, BrushSettings, brush, default_settings
from .data import (add_layer, bake_layers, bake_to_mesh, clear_layer, delete_higher_levels,
                   ensure_state, level_down, level_up, mask_clear, mask_fill, mask_grow, mask_invert,
                   mask_shrink, mask_smooth, merge_layer_down, remove_layer, remove_sculpt,
                   set_active_layer, set_layer_strength, set_layer_visible, set_level, subdivide,
                   summary)
from .session import SculptSession, get_session
from .stroke import SculptStroke, apply_dab, current_stroke, stroke_begin, stroke_cancel, stroke_dab, stroke_end
from .subdivision import catmull_clark, subdivide_mesh

__all__ = [
    "BRUSH_ORDER", "BRUSHES", "BrushDef", "BrushSettings", "brush", "default_settings",
    "SculptSession", "get_session", "SculptStroke", "apply_dab", "current_stroke", "stroke_begin",
    "stroke_cancel", "stroke_dab", "stroke_end", "catmull_clark", "subdivide_mesh",
    "add_layer", "bake_layers", "bake_to_mesh", "clear_layer", "delete_higher_levels", "ensure_state",
    "level_down", "level_up", "mask_clear", "mask_fill", "mask_grow", "mask_invert", "mask_shrink",
    "mask_smooth", "merge_layer_down", "remove_layer", "remove_sculpt", "set_active_layer",
    "set_layer_strength", "set_layer_visible", "set_level", "subdivide", "summary",
    "data", "falloff", "stamps", "subdivision", "topology",
    "commands", "docks", "pages", "key_actions", "attach_viewport", "panel_factory",
    "SculptBrushPanel", "SculptLayersPanel", "FalloffCurveEditor", "ViewportSculptController",
    "BrushOverlay",
]

BRUSHES_DOCK = "Sculpt Brushes"
LAYERS_DOCK = "Sculpt Layers"


def __getattr__(name: str):
    if name in ("SculptBrushPanel", "SculptLayersPanel", "FalloffCurveEditor"):
        from . import panels
        return getattr(panels, name)
    if name in ("ViewportSculptController", "BrushOverlay", "attach_viewport"):
        from . import viewport
        return getattr(viewport, name)
    raise AttributeError(name)


def _scene():
    from ..scene import get_scene
    return get_scene()


def _on_active(fn):
    def run():
        scene = _scene()
        obj = getattr(scene, "active", None)
        if not data.can_sculpt(obj):
            return False
        result = fn(obj, scene)
        get_session(scene).notify_data()
        return result
    return run


def toggle_sculpt_mode() -> bool:
    session = get_session(_scene())
    session.toggle()
    return session.active


def _select_brush(brush_id: str):
    def run():
        session = get_session(_scene())
        session.set_brush(brush_id)
        if not session.active:
            session.set_active(True)
        return session.brush
    return run


def _add_layer(obj, scene):
    return data.add_layer(obj, None, scene)


def _scale_radius(factor: float):
    def run():
        get_session(_scene()).scale_radius(factor)
    return run


def _toggle_symmetry(axis: int):
    def run():
        session = get_session(_scene())
        session.set_symmetry(axis, not session.settings().symmetry[axis])
        return session.settings().symmetry[axis]
    return run


def commands() -> list:
    out = [
        (("Sculpt", "Sculpt Mode"), toggle_sculpt_mode),
        (("Sculpt", "Subdivide"), _on_active(data.subdivide)),
        (("Sculpt", "Level Up"), _on_active(data.level_up)),
        (("Sculpt", "Level Down"), _on_active(data.level_down)),
        (("Sculpt", "Delete Higher Levels"), _on_active(data.delete_higher_levels)),
        (("Sculpt", "Layers", "Add Layer"), _on_active(_add_layer)),
        (("Sculpt", "Layers", "Bake Layers"), _on_active(data.bake_layers)),
        (("Sculpt", "Mask", "Invert Mask"), _on_active(data.mask_invert)),
        (("Sculpt", "Mask", "Clear Mask"), _on_active(data.mask_clear)),
        (("Sculpt", "Mask", "Fill Mask"), _on_active(data.mask_fill)),
        (("Sculpt", "Mask", "Grow Mask"), _on_active(data.mask_grow)),
        (("Sculpt", "Mask", "Shrink Mask"), _on_active(data.mask_shrink)),
        (("Sculpt", "Mask", "Smooth Mask"), _on_active(data.mask_smooth)),
        (("Sculpt", "Symmetry", "Local X"), _toggle_symmetry(0)),
        (("Sculpt", "Symmetry", "Local Y"), _toggle_symmetry(1)),
        (("Sculpt", "Symmetry", "Local Z"), _toggle_symmetry(2)),
        (("Sculpt", "Bake to Mesh"), _on_active(data.bake_to_mesh)),
        (("Sculpt", "Drop Sculpt Data"), _on_active(data.remove_sculpt)),
    ]
    for bid in BRUSH_ORDER:
        out.append((("Sculpt", "Brushes", BRUSHES[bid].label), _select_brush(bid)))
    return out


def panel_factory(cls_name: str):
    def make(*args, **kwargs):
        from PySide6.QtWidgets import QWidget

        from . import panels
        scene = kwargs.pop("scene", None)
        parent = kwargs.pop("parent", None)
        for a in args:
            if isinstance(a, QWidget) and parent is None:
                parent = a
            elif hasattr(a, "objects") and hasattr(a, "changed") and scene is None:
                scene = a
        return getattr(panels, cls_name)(scene, parent)
    return make


def docks() -> list:
    return [
        (BRUSHES_DOCK, panel_factory("SculptBrushPanel"), "right"),
        (LAYERS_DOCK, panel_factory("SculptLayersPanel"), "right"),
    ]


def pages() -> list:
    return [("Sculpt", [BRUSHES_DOCK, LAYERS_DOCK])]


def key_actions() -> list:
    return [
        ("[", "Sculpt: Smaller Brush", _scale_radius(1.0 / 1.2)),
        ("]", "Sculpt: Larger Brush", _scale_radius(1.2)),
        ("Ctrl+Shift+S", "Sculpt Mode", toggle_sculpt_mode),
        ("Ctrl+Shift+D", "Sculpt: Subdivide", _on_active(data.subdivide)),
        ("Ctrl+Shift+Up", "Sculpt: Level Up", _on_active(data.level_up)),
        ("Ctrl+Shift+Down", "Sculpt: Level Down", _on_active(data.level_down)),
        ("Ctrl+Shift+I", "Sculpt: Invert Mask", _on_active(data.mask_invert)),
    ]
