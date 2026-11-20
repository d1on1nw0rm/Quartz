from __future__ import annotations

import fnmatch
import os
from typing import Callable, Iterable, Iterator, Mapping, Sequence

import quartz.path as qpath
from quartz import registry
from quartz.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from quartz.rna.struct import Struct, builtin_struct

__all__ = [
    "SPACE_TYPES", "REGION_TYPES", "PANEL_OPTIONS", "MENU_OPTIONS",
    "Panel", "Menu", "Header", "UIList", "UI_UL_list",
    "draw_funcs_owned_by", "iter_extended", "extensions_snapshot", "extensions_restore", "draw_sequence",
]

SPACE_TYPES: tuple[str, ...] = (
    "EMPTY", "VIEW_3D", "IMAGE_EDITOR", "NODE_EDITOR", "SEQUENCE_EDITOR", "CLIP_EDITOR", "DOPESHEET_EDITOR",
    "GRAPH_EDITOR", "NLA_EDITOR", "TEXT_EDITOR", "CONSOLE", "INFO", "TOPBAR", "STATUSBAR", "OUTLINER",
    "PROPERTIES", "FILE_BROWSER", "SPREADSHEET", "PREFERENCES"
)
REGION_TYPES: tuple[str, ...] = (
    "WINDOW", "HEADER", "CHANNELS", "TEMPORARY", "UI", "TOOLS", "TOOL_PROPS", "ASSET_SHELF",
    "ASSET_SHELF_HEADER", "PREVIEW", "HUD", "NAVIGATION_BAR", "EXECUTE", "FOOTER", "TOOL_HEADER", "XR",
    "SCRUBBING"
)
PANEL_OPTIONS: tuple[str, ...] = ("DEFAULT_CLOSED", "HIDE_HEADER", "INSTANCED", "HEADER_LAYOUT_EXPAND")
MENU_OPTIONS: tuple[str, ...] = ("SEARCH_ON_KEY_PRESS",)


class _Extensions:
    __slots__ = ("pre", "post", "extended")

    def __init__(self, pre=None, post=None, extended=False):
        self.pre: list[tuple[Callable, str | None]] = list(pre or ())
        self.post: list[tuple[Callable, str | None]] = list(post or ())
        self.extended: bool = extended

    def copy(self) -> "_Extensions":
        return _Extensions(self.pre, self.post, self.extended)


_EXTENSIONS: dict[type, _Extensions] = {}


def _ext_for(cls: type) -> _Extensions:
    ext = _EXTENSIONS.get(cls)
    if ext is None:
        ext = _Extensions()
        _EXTENSIONS[cls] = ext
    return ext


class _GenericUI:

    @classmethod
    def append(cls, draw_func: Callable[[object, object], None]) -> None:
        ext = _ext_for(cls)
        ext.post.append((draw_func, registry.current_owner()))
        ext.extended = True

    @classmethod
    def prepend(cls, draw_func: Callable[[object, object], None]) -> None:
        ext = _ext_for(cls)
        ext.pre.insert(0, (draw_func, registry.current_owner()))
        ext.extended = True

    @classmethod
    def remove(cls, draw_func: Callable) -> None:
        ext = _EXTENSIONS.get(cls)
        if ext is None:
            return
        for lst in (ext.pre, ext.post):
            for i, (fn, _owner) in enumerate(lst):
                if fn == draw_func:
                    del lst[i]
                    return

    @classmethod
    def is_extended(cls) -> bool:
        ext = _EXTENSIONS.get(cls)
        return bool(ext is not None and ext.extended)


def draw_sequence(cls: type) -> tuple[Callable, ...]:
    ext = _EXTENSIONS.get(cls)
    pre = [fn for fn, _ in ext.pre] if ext is not None else []
    post = [fn for fn, _ in ext.post] if ext is not None else []
    middle = [cls.draw] if hasattr(cls, "draw") else []
    return tuple(pre + middle + post)


def draw_funcs_owned_by(owner: str) -> list[tuple[type, Callable]]:
    out: list[tuple[type, Callable]] = []
    for cls, ext in list(_EXTENSIONS.items()):
        for fn, own in ext.pre + ext.post:
            if own == owner:
                out.append((cls, fn))
    return out


def iter_extended() -> Iterator[tuple[type, tuple[Callable, ...]]]:
    items = [(cls, tuple(fn for fn, _ in ext.pre + ext.post)) for cls, ext in _EXTENSIONS.items() if ext.extended]
    return iter(items)


def extensions_snapshot() -> object:
    return tuple((cls, ext.copy()) for cls, ext in _EXTENSIONS.items())


def extensions_restore(snap: object) -> None:
    _EXTENSIONS.clear()
    for cls, ext in snap:
        _EXTENSIONS[cls] = ext.copy()


def _ui_cleanup(cls: type) -> None:
    _EXTENSIONS.pop(cls, None)


def _ui_rna_name(cls: type) -> str:
    idname = getattr(cls, "bl_idname", "")
    if isinstance(idname, str) and idname:
        return idname
    return cls.__name__


def _layout_of(self) -> object:
    return getattr(self, "_q_layout", None)


@builtin_struct
class Panel(Struct, _GenericUI):
    _q_registrable = True
    _q_class_enums = {
        "bl_space_type": ("ENUM", SPACE_TYPES),
        "bl_region_type": ("ENUM", REGION_TYPES),
        "bl_options": ("SET", PANEL_OPTIONS),
    }
    _q_name_tag = "PT"
    _q_has_parent_id = True

    text: StringProperty(name="Text", options=set())
    use_pin: BoolProperty(name="Pin")
    is_popover: BoolProperty(name="Popover", meta={"readonly": True})

    @property
    def layout(self):
        return _layout_of(self)

    @property
    def custom_data(self) -> None:
        return None


@builtin_struct
class Menu(Struct, _GenericUI):
    _q_registrable = True
    _q_class_enums = {"bl_options": ("SET", MENU_OPTIONS)}
    _q_name_tag = "MT"

    @property
    def layout(self):
        return _layout_of(self)

    def draw_preset(self, context: object) -> None:
        if not (hasattr(self, "preset_subdir") and hasattr(self, "preset_operator")):
            return
        from quartz import utils
        self.path_menu(utils.preset_paths(self.preset_subdir), self.preset_operator,
                       props_default=getattr(self, "preset_operator_defaults", None),
                       add_operator=getattr(self, "preset_add_operator", None))

    @classmethod
    def draw_collapsible(cls, context: object, layout) -> None:
        layout.menu(registry.rna_name_of(cls))

    def path_menu(self, searchpaths: Sequence[str], operator: str, *, props_default: Mapping[str, object] | None = None,
                  prop_filepath: str = "filepath", filter_ext: Callable[[str], bool] | None = None,
                  filter_path: Callable[[str], bool] | None = None, display_name: Callable[[str], str] | None = None,
                  add_operator: str | None = None, add_operator_props: Mapping[str, object] | None = None,
                  translate: bool = True) -> None:
        layout = self.layout
        if layout is None:
            return
        for directory in searchpaths:
            if not directory or not os.path.isdir(directory):
                continue
            names = sorted((n for n in os.listdir(directory) if os.path.isfile(os.path.join(directory, n))),
                           key=str.casefold)
            for fname in names:
                ext = os.path.splitext(fname)[1]
                if filter_ext is not None and not filter_ext(ext):
                    continue
                filepath = os.path.join(directory, fname)
                if filter_path is not None and not filter_path(filepath):
                    continue
                label = display_name(filepath) if display_name is not None else qpath.display_name(fname)
                props = layout.operator(operator, text=label, translate=translate)
                for key, value in dict(props_default or {}).items():
                    _try_set(props, key, value)
                _try_set(props, prop_filepath, filepath)
        if add_operator:
            props = layout.operator(add_operator, text="", icon="ADD")
            for key, value in dict(add_operator_props or {}).items():
                _try_set(props, key, value)


def _try_set(target: object, key: str, value: object) -> None:
    if target is None:
        return
    try:
        setattr(target, key, value)
    except Exception:
        pass


@builtin_struct
class Header(Struct, _GenericUI):
    _q_registrable = True
    _q_class_enums = {
        "bl_space_type": ("ENUM", SPACE_TYPES),
        "bl_region_type": ("ENUM", REGION_TYPES),
    }
    _q_name_tag = "HT"

    @property
    def layout(self):
        return _layout_of(self)


@builtin_struct
class UIList(Struct, _GenericUI):
    _q_registrable = True
    _q_name_tag = "UL"

    list_id: StringProperty(name="List Name", maxlen=256, options=set(), meta={"readonly": True})
    layout_type: EnumProperty(items=[("DEFAULT", "Default Layout", ""), ("COMPACT", "Compact Layout", "")],
                              name="Layout Type", default="DEFAULT", meta={"readonly": True})
    use_filter_show: BoolProperty(name="Show Filter")
    filter_name: StringProperty(name="Filter by Name", maxlen=256, options=set())
    use_filter_invert: BoolProperty(name="Invert")
    use_filter_sort_alpha: BoolProperty(name="Sort by Name")
    use_filter_sort_reverse: BoolProperty(name="Reverse")
    use_filter_sort_lock: BoolProperty(name="Lock Order")
    bitflag_filter_item: IntProperty(name="FILTER_ITEM", subtype="UNSIGNED", min=0, soft_max=10000,
                                     meta={"virtual_get": lambda self: 1 << 30})
    bitflag_item_never_show: IntProperty(name="ITEM_NEVER_SHOW", subtype="UNSIGNED", min=0, soft_max=10000,
                                         meta={"virtual_get": lambda self: 1 << 29})

    @property
    def layout(self):
        return _layout_of(self)


@builtin_struct
class UI_UL_list(UIList):

    @staticmethod
    def filter_items_by_name(pattern: str, bitflag: int, items: Iterable, propname: str = "name",
                             flags: list[int] | None = None, reverse: bool = False) -> list[int]:
        items = list(items) if items is not None else []
        if not pattern or not items:
            return flags if flags is not None else []
        if flags is None:
            flags = [0] * len(items)
        glob = f"*{pattern.casefold()}*"
        for i, item in enumerate(items):
            name = getattr(item, propname, None)
            matched = isinstance(name, str) and bool(name) and fnmatch.fnmatchcase(name.casefold(), glob)
            if matched != bool(reverse):
                flags[i] |= bitflag
        return flags

    @staticmethod
    def sort_items_helper(sort_data: list[tuple], key: Callable, reverse: bool = False) -> list[int]:
        sort_data.sort(key=key, reverse=reverse)
        neworder = [0] * len(sort_data)
        for new_index, entry in enumerate(sort_data):
            neworder[entry[0]] = new_index
        return neworder

    @staticmethod
    def sort_items_by_name(items: Iterable, propname: str = "name") -> list[int]:
        sort_data = [(i, getattr(item, propname, "")) for i, item in enumerate(items)]
        return UI_UL_list.sort_items_helper(sort_data, lambda e: str(e[1]).casefold())


registry.register_base(
    Panel, kind="UI", required=("bl_label", "bl_space_type", "bl_region_type", "draw"), rna_name=_ui_rna_name,
    callbacks={
        "poll": (True, True),
        "draw": (False, False),
        "draw_header": (True, False),
        "draw_header_preset": (True, False),
    },
    cleanup=_ui_cleanup,
)
registry.register_base(
    Menu, kind="UI", required=("bl_label", "draw"), rna_name=_ui_rna_name,
    callbacks={
        "poll": (True, True),
        "draw": (False, False),
    },
    cleanup=_ui_cleanup,
)
registry.register_base(
    Header, kind="UI", required=("bl_space_type", "draw"), rna_name=_ui_rna_name,
    callbacks={
        "draw": (False, False),
    },
    cleanup=_ui_cleanup,
)
registry.register_base(
    UIList, kind="UI", required=(), rna_name=_ui_rna_name,
    callbacks={
        "draw_item": (True, False),
        "draw_filter": (True, False),
        "filter_items": (True, False),
    },
    cleanup=_ui_cleanup,
)
