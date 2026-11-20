from __future__ import annotations

from . import objects
from .camera import RenderCamera, from_canvas, from_object, from_orbit, look_at
from .engine import (RenderCancelled, RenderJob, RenderResult, execute_job, prepare_job, render,
                     resolve_camera, save_result)
from .settings import default_settings, get_settings, set_settings, update_settings
from .shading import Light, tonemap

__all__ = [
    "objects",
    "RenderCamera",
    "from_canvas",
    "from_object",
    "from_orbit",
    "look_at",
    "RenderCancelled",
    "RenderJob",
    "RenderResult",
    "execute_job",
    "prepare_job",
    "render",
    "resolve_camera",
    "save_result",
    "default_settings",
    "get_settings",
    "set_settings",
    "update_settings",
    "Light",
    "tonemap",
    "commands",
    "docks",
    "pages",
    "key_actions",
]


def commands() -> list:
    from .actions import commands as _commands
    return _commands()


def docks() -> list:
    from .actions import docks as _docks
    return _docks()


def pages() -> list:
    from .actions import pages as _pages
    return _pages()


def key_actions() -> list:
    from .actions import key_actions as _key_actions
    return _key_actions()
