from __future__ import annotations

from .data import (SEAMS_KEY, TAG_KEY, UV_KEY, Corners, add_seams, clear_seams, ensure_uv, get_seams,
                   get_uv, get_uv_array, has_uv, reset_uv, set_seams, set_uv_array, sync_all,
                   uv_islands)
from .project import (get_tag, look_at, project_box, project_cylindrical, project_flat,
                      project_frontal, project_spherical, set_tag, uvw_from_tag)
from .texture import Brush, TextureCanvas, checker_image, checker_pixels, load_canvas, save_canvas, uv_at_hit
from .unwrap import angle_seams, lscm, relax
from .project import project as project_uv
from .unwrap import unwrap as unwrap_uv

__all__ = [
    "UV_KEY",
    "SEAMS_KEY",
    "TAG_KEY",
    "Corners",
    "Brush",
    "TextureCanvas",
    "add_seams",
    "angle_seams",
    "checker_image",
    "checker_pixels",
    "clear_seams",
    "ensure_uv",
    "get_seams",
    "get_tag",
    "get_uv",
    "get_uv_array",
    "has_uv",
    "load_canvas",
    "look_at",
    "lscm",
    "project_uv",
    "project_box",
    "project_cylindrical",
    "project_flat",
    "project_frontal",
    "project_spherical",
    "relax",
    "reset_uv",
    "save_canvas",
    "set_seams",
    "set_tag",
    "set_uv_array",
    "sync_all",
    "unwrap_uv",
    "uv_at_hit",
    "uv_islands",
    "uvw_from_tag",
    "commands",
    "docks",
    "pages",
    "key_actions",
]


def _session(scene=None):
    from ..scene import get_scene
    from .session import session_for
    return session_for(scene if scene is not None else get_scene())


def _cmd(fn):
    def run(scene=None, *_args):
        if isinstance(scene, bool):
            scene = None
        return fn(_session(scene))
    return run


def commands() -> list:
    out = []
    for kind in ("Flat", "Box", "Spherical", "Cylindrical", "Frontal"):
        out.append((("UV", "Projection", kind), _cmd(lambda s, k=kind: s.project(k))))
    out.extend([
        (("UV", "Generate UVW from Tag"), _cmd(lambda s: s.uvw_from_tag())),
        (("UV", "Reset UVs"), _cmd(lambda s: s.reset())),
        (("UV", "Seams", "From Selected Edges"), _cmd(lambda s: s.seams_from_selection(False))),
        (("UV", "Seams", "Remove Selected"), _cmd(lambda s: s.remove_selected_seams())),
        (("UV", "Seams", "By Angle"), _cmd(lambda s: s.seams_by_angle(60.0))),
        (("UV", "Seams", "From UV Islands"), _cmd(lambda s: s.seams_from_islands())),
        (("UV", "Seams", "Clear"), _cmd(lambda s: s.clear_seams())),
        (("UV", "Unwrap", "Conformal"), _cmd(lambda s: s.unwrap("Conformal"))),
        (("UV", "Unwrap", "Isometric"), _cmd(lambda s: s.unwrap("Isometric"))),
        (("UV", "Unwrap", "Sharp Edges"), _cmd(lambda s: s.unwrap("Conformal", angle=60.0))),
        (("UV", "Relax"), _cmd(lambda s: s.relax("ARAP", 10))),
        (("UV", "Pack Islands"), _cmd(lambda s: s.pack())),
        (("UV", "Align Islands"), _cmd(lambda s: s.align_islands("Auto"))),
        (("UV", "Rectify Grid"), _cmd(lambda s: s.rectify())),
        (("UV", "Stitch"), _cmd(lambda s: s.stitch())),
        (("UV", "Transform", "Flip U"), _cmd(lambda s: s.flip("U"))),
        (("UV", "Transform", "Flip V"), _cmd(lambda s: s.flip("V"))),
        (("UV", "Transform", "Rotate +90"), _cmd(lambda s: s.rotate90(False))),
        (("UV", "Transform", "Rotate -90"), _cmd(lambda s: s.rotate90(True))),
        (("UV", "Transform", "Fit to Bounds"), _cmd(lambda s: s.fit(True, 0.0))),
        (("UV", "Transform", "Straighten"), _cmd(lambda s: s.straighten())),
        (("Texture", "New Texture"), _cmd(lambda s: s.new_canvas())),
        (("Texture", "New Checker Texture"), _cmd(lambda s: s.new_canvas(checker=True))),
        (("Texture", "Fill Canvas"), _cmd(lambda s: s.fill_canvas())),
    ])
    return out


def _factory(cls_path: str):
    def make(scene=None, parent=None):
        from ..scene import Scene
        if parent is None and scene is not None and not isinstance(scene, Scene):
            parent, scene = scene, None
        module, name = cls_path.rsplit(".", 1)
        import importlib
        cls = getattr(importlib.import_module(module, __name__), name)
        return cls(scene, parent)
    return make


def docks() -> list:
    return [
        ("UV Editor", _factory(".editor.UVEditorView"), "right"),
        ("UV Tools", _factory(".panels.UVToolsPanel"), "left"),
        ("Texture Paint", _factory(".panels.TexturePaintPanel"), "left"),
    ]


def pages() -> list:
    return [("UV Edit", ["UV Editor", "UV Tools", "Texture Paint"])]


def key_actions() -> list:
    return [
        ("UV Unwrap", "Ctrl+Shift+U", _cmd(lambda s: s.unwrap("Conformal"))),
        ("UV Pack Islands", "Ctrl+Shift+P", _cmd(lambda s: s.pack())),
        ("UV Relax", "Ctrl+Shift+R", _cmd(lambda s: s.relax("ARAP", 10))),
    ]
