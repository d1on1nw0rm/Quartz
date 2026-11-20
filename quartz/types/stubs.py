from __future__ import annotations

from types import SimpleNamespace
from typing import Callable, Mapping, NoReturn

from quartz import registry
from quartz.errors import NotImplementedInQuartz
from quartz.rna.struct import Struct, builtin_struct
from quartz.types.operator import OPERATOR_OPTIONS, OperatorProperties, _operator_cleanup, _operator_prepare, \
    _props_class

__all__ = [
    "Macro", "RenderEngine", "HydraRenderEngine", "KeyingSetInfo", "Gizmo", "GizmoGroup", "WorkSpaceTool",
    "AssetShelf", "FileHandler", "Node", "NodeSocket", "NodeTree", "NodeTreeInterfaceSocket", "Space",
    "SpaceView3D", "SpaceImageEditor", "SpaceNodeEditor", "SpaceTextEditor", "SpaceProperties", "SpaceOutliner",
    "SpaceFileBrowser", "SpaceSequenceEditor", "SpaceClipEditor", "SpaceGraphEditor", "SpaceDopeSheetEditor",
    "SpaceNLA", "SpaceConsole", "SpaceInfo", "SpacePreferences", "SpaceSpreadsheet", "draw_handlers",
]


class _MacroStep:

    def __init__(self, idname: str, properties: object) -> None:
        self.idname = idname
        self.properties = properties


_MACRO_STEPS: dict[type, list[_MacroStep]] = {}


@builtin_struct
class Macro(Struct):
    _q_registrable = True
    _q_class_enums = {"bl_options": ("SET", OPERATOR_OPTIONS)}

    @classmethod
    def define(cls, opname: str) -> object:
        op_cls = registry.operator_class(opname)
        if op_cls is not None and hasattr(op_cls, "q_new_properties"):
            props: object = op_cls.q_new_properties()
        else:
            props = SimpleNamespace()
        step = _MacroStep(opname, props)
        _MACRO_STEPS.setdefault(cls, []).append(step)
        return step

    @classmethod
    def q_properties_class(cls) -> type[OperatorProperties]:
        return _props_class(cls)

    @classmethod
    def q_new_properties(cls) -> OperatorProperties:
        return _props_class(cls)()

    def _q_assign(self, kwargs: Mapping[str, object]) -> NoReturn:
        raise NotImplementedInQuartz("Macro operators")


def _macro_cleanup(cls: type) -> None:
    _operator_cleanup(cls)
    _MACRO_STEPS.pop(cls, None)


@builtin_struct
class RenderEngine(Struct):
    _q_registrable = True


@builtin_struct
class HydraRenderEngine(RenderEngine):
    pass


@builtin_struct
class KeyingSetInfo(Struct):
    _q_registrable = True


@builtin_struct
class Gizmo(Struct):
    _q_registrable = True


@builtin_struct
class GizmoGroup(Struct):
    _q_registrable = True


@builtin_struct
class WorkSpaceTool(Struct):
    _q_registrable = True


@builtin_struct
class AssetShelf(Struct):
    _q_registrable = True


@builtin_struct
class FileHandler(Struct):
    _q_registrable = True


@builtin_struct
class Node(Struct):
    _q_registrable = True


@builtin_struct
class NodeSocket(Struct):
    _q_registrable = True


@builtin_struct
class NodeTree(Struct):
    _q_registrable = True


@builtin_struct
class NodeTreeInterfaceSocket(Struct):
    _q_registrable = True


class _DrawHandle:
    __slots__ = ("entry",)

    def __init__(self, entry: tuple) -> None:
        self.entry = entry

    def __repr__(self) -> str:
        return f"<draw handler {self.entry[1]!r} at 0x{id(self):X}>"


_DRAW_HANDLERS: list[tuple[_DrawHandle, tuple[type, Callable, tuple, str, str]]] = []


@builtin_struct
class Space(Struct):
    _q_strict_attrs = True

    @classmethod
    def draw_handler_add(cls, callback: Callable, args: tuple, region_type: str, draw_type: str) -> object:
        entry = (cls, callback, tuple(args) if args is not None else (), region_type, draw_type)
        handle = _DrawHandle(entry)
        _DRAW_HANDLERS.append((handle, entry))
        return handle

    @classmethod
    def draw_handler_remove(cls, handle: object, region_type: str) -> None:
        for i, (h, _entry) in enumerate(_DRAW_HANDLERS):
            if h is handle:
                del _DRAW_HANDLERS[i]
                return


def draw_handlers(space_cls: type | None = None) -> list[tuple[type, Callable, tuple, str, str]]:
    return [entry for _h, entry in _DRAW_HANDLERS if space_cls is None or entry[0] is space_cls]


@builtin_struct
class SpaceView3D(Space):
    pass


@builtin_struct
class SpaceImageEditor(Space):
    pass


@builtin_struct
class SpaceNodeEditor(Space):
    pass


@builtin_struct
class SpaceTextEditor(Space):
    pass


@builtin_struct
class SpaceProperties(Space):
    pass


@builtin_struct
class SpaceOutliner(Space):
    pass


@builtin_struct
class SpaceFileBrowser(Space):
    pass


@builtin_struct
class SpaceSequenceEditor(Space):
    pass


@builtin_struct
class SpaceClipEditor(Space):
    pass


@builtin_struct
class SpaceGraphEditor(Space):
    pass


@builtin_struct
class SpaceDopeSheetEditor(Space):
    pass


@builtin_struct
class SpaceNLA(Space):
    pass


@builtin_struct
class SpaceConsole(Space):
    pass


@builtin_struct
class SpaceInfo(Space):
    pass


@builtin_struct
class SpacePreferences(Space):
    pass


@builtin_struct
class SpaceSpreadsheet(Space):
    pass


def _generic_rna_name(cls: type) -> str:
    idname = getattr(cls, "bl_idname", "")
    if isinstance(idname, str) and idname:
        return idname
    return cls.__name__


registry.register_base(
    Macro, kind="OPERATOR", required=("bl_label",),
    callbacks={
        "poll": (True, True),
        "draw": (True, False),
    },
    prepare=_operator_prepare, cleanup=_macro_cleanup,
)
registry.register_base(
    KeyingSetInfo, kind="GENERIC", required=("poll", "iterator", "generate"), rna_name=_generic_rna_name,
    callbacks={
        "poll": (False, False),
        "iterator": (False, False),
        "generate": (False, False),
    },
)
registry.register_base(
    RenderEngine, kind="GENERIC", required=(), rna_name=_generic_rna_name,
    callbacks={
        "update": (True, False),
        "render": (True, False),
        "render_frame_finish": (True, False),
        "draw": (True, False),
        "bake": (True, False),
        "view_update": (True, False),
        "view_draw": (True, False),
        "update_script_node": (True, False),
        "update_render_passes": (True, False),
        "update_custom_camera": (True, False),
    },
)
registry.register_base(
    Gizmo, kind="GENERIC", required=("draw",), rna_name=_generic_rna_name,
    callbacks={
        "draw": (False, False),
        "draw_select": (True, False),
        "test_select": (True, False),
        "modal": (True, False),
        "setup": (True, False),
        "invoke": (True, False),
        "exit": (True, False),
        "select_refresh": (True, False),
    },
)
registry.register_base(
    GizmoGroup, kind="GENERIC", required=("setup",), rna_name=_generic_rna_name,
    callbacks={
        "poll": (True, True),
        "setup_keymap": (True, True),
        "setup": (False, False),
        "refresh": (True, False),
        "draw_prepare": (True, False),
        "invoke_prepare": (True, False),
    },
)
registry.register_base(WorkSpaceTool, kind="GENERIC", required=(), rna_name=_generic_rna_name,
                       callbacks={})
registry.register_base(
    AssetShelf, kind="GENERIC", required=(), rna_name=_generic_rna_name,
    callbacks={
        "poll": (True, True),
        "asset_poll": (True, True),
        "get_active_asset": (True, True),
        "draw_context_menu": (True, True),
    },
)
registry.register_base(
    FileHandler, kind="GENERIC", required=(), rna_name=_generic_rna_name,
    callbacks={
        "poll_drop": (True, True),
    },
)
registry.register_base(
    Node, kind="GENERIC", required=("poll",), rna_name=_generic_rna_name,
    callbacks={
        "poll": (False, True),
        "poll_instance": (True, False),
        "update": (True, False),
        "insert_link": (True, False),
        "init": (True, False),
        "copy": (True, False),
        "free": (True, False),
        "draw_buttons": (True, False),
        "draw_buttons_ext": (True, False),
        "draw_label": (True, False),
    },
)
registry.register_base(
    NodeSocket, kind="GENERIC", required=("draw",), rna_name=_generic_rna_name,
    callbacks={
        "draw": (False, False),
        "draw_color": (True, False),
        "draw_color_simple": (True, True),
    },
)
registry.register_base(
    NodeTree, kind="GENERIC", required=(), rna_name=_generic_rna_name,
    callbacks={
        "poll": (True, True),
        "update": (True, False),
        "get_from_context": (True, True),
        "valid_socket_type": (True, True),
    },
)
registry.register_base(NodeTreeInterfaceSocket, kind="GENERIC", required=(), rna_name=_generic_rna_name,
                       callbacks={})
