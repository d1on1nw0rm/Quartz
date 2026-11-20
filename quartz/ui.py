from __future__ import annotations

import functools
import inspect
import re
import sys
import traceback
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping

from quartz import registry
from quartz.app import settings as app_settings
from quartz.props import BoolProperty, EnumProperty, FloatProperty
from quartz.rna import hooks
from quartz.rna.annotations import get_property
from quartz.rna.datapath import unescape_identifier
from quartz.rna.properties import EnumDef
from quartz.rna.struct import Struct, builtin_struct
from quartz.types.operator import OperatorProperties
from quartz.types.ui import Header, Menu, Panel, UIList, draw_sequence

__all__ = [
    "UILAYOUT_FUNCTIONS", "UILAYOUT_OUTPUTS", "OPERATOR_CONTEXTS", "LayoutIssue", "LayoutNode", "UILayout",
    "DrawResult", "draw_ui", "draw_panel", "draw_menu", "draw_ui_list", "placeholder_type",
]

UILAYOUT_FUNCTIONS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "row": ("layout", "align", "heading", "heading_ctxt", "translate"),
    "column": ("layout", "align", "heading", "heading_ctxt", "translate"),
    "panel": ("idname", "default_closed", "layout_header", "layout_body"),
    "panel_prop": ("data", "property", "layout_header", "layout_body"),
    "column_flow": ("columns", "layout", "align"),
    "grid_flow": ("row_major", "columns", "even_columns", "even_rows", "align", "layout"),
    "box": ("layout",),
    "split": ("layout", "factor", "align"),
    "menu_pie": ("layout",),
    "icon": ("icon_value", "data"),
    "enum_item_name": ("name", "data", "property", "identifier"),
    "enum_item_description": ("description", "data", "property", "identifier"),
    "enum_item_icon": ("icon_value", "data", "property", "identifier"),
    "textbox": ("data", "property", "initial_visible_lines", "placeholder", "text_ctxt", "translate"),
    "textbox_with_state": ("data", "property", "textbox_state", "placeholder", "text_ctxt", "translate"),
    "prop": ("data", "property", "text", "text_ctxt", "translate", "icon", "placeholder", "expand", "slider", "toggle", "icon_only", "event", "full_event", "emboss", "index", "icon_value", "invert_checkbox", "text_align"),
    "props_enum": ("data", "property"),
    "prop_menu_enum": ("data", "property", "text", "text_ctxt", "translate", "icon"),
    "prop_with_popover": ("data", "property", "text", "text_ctxt", "translate", "icon", "icon_only", "panel"),
    "prop_with_menu": ("data", "property", "text", "text_ctxt", "translate", "icon", "icon_only", "menu"),
    "prop_tabs_enum": ("data", "property", "data_highlight", "property_highlight", "icon_only", "expand_as"),
    "prop_enum": ("data", "property", "value", "text", "text_ctxt", "translate", "icon"),
    "prop_search": ("data", "property", "search_data", "search_property", "text", "text_ctxt", "translate", "icon", "results_are_suggestions", "item_search_property"),
    "prop_decorator": ("data", "property", "index"),
    "operator": ("operator", "text", "text_ctxt", "translate", "icon", "emboss", "depress", "icon_value", "search_weight", "properties"),
    "operator_menu_hold": ("operator", "text", "text_ctxt", "translate", "icon", "emboss", "depress", "icon_value", "menu", "properties"),
    "operator_enum": ("operator", "property", "icon_only"),
    "operator_menu_enum": ("operator", "property", "text", "text_ctxt", "translate", "icon", "properties"),
    "label": ("text", "text_ctxt", "translate", "icon", "icon_value"),
    "link": ("url", "text", "text_ctxt", "translate", "icon", "icon_value"),
    "menu": ("menu", "text", "text_ctxt", "translate", "icon", "icon_value"),
    "menu_contents": ("menu",),
    "popover": ("panel", "text", "text_ctxt", "translate", "icon", "icon_value", "direction"),
    "popover_group": ("space_type", "region_type", "context", "category"),
    "separator": ("factor", "type"),
    "separator_spacer": (),
    "progress": ("text", "text_ctxt", "translate", "factor", "type"),
    "context_pointer_set": ("name", "data"),
    "context_string_set": ("name", "value"),
    "template_header": (),
    "template_ID": ("data", "property", "new", "open", "unlink", "filter", "live_icon", "text", "text_ctxt", "translate"),
    "template_ID_session_uid": ("data", "property", "id_type"),
    "template_ID_preview": ("data", "property", "new", "open", "unlink", "rows", "cols", "filter", "hide_buttons"),
    "template_matrix": ("data", "property"),
    "template_any_ID": ("data", "property", "type_property", "text", "text_ctxt", "translate"),
    "template_ID_tabs": ("data", "property", "new", "menu", "filter"),
    "template_action": ("id", "new", "unlink", "text", "text_ctxt", "translate"),
    "template_search": ("data", "property", "search_data", "search_property", "new", "unlink", "text", "text_ctxt", "translate"),
    "template_search_preview": ("data", "property", "search_data", "search_property", "new", "unlink", "text", "text_ctxt", "translate", "rows", "cols"),
    "template_path_builder": ("data", "property", "root", "text", "text_ctxt", "translate"),
    "template_modifiers": (),
    "template_strip_modifiers": (),
    "template_collection_importer": (),
    "template_collection_exporters": (),
    "template_constraints": ("use_bone_constraints",),
    "template_shaderfx": (),
    "template_greasepencil_color": ("data", "property", "rows", "cols", "scale", "filter"),
    "template_constraint_header": ("data",),
    "template_preview": ("id", "show_buttons", "parent", "slot", "preview_id"),
    "template_curve_mapping": ("data", "property", "type", "levels", "brush", "use_negative_slope", "show_tone", "show_presets"),
    "template_curveprofile": ("data", "property"),
    "template_color_ramp": ("data", "property", "expand"),
    "template_icon": ("icon_value", "scale"),
    "template_icon_view": ("data", "property", "show_labels", "scale", "scale_popup"),
    "template_histogram": ("data", "property"),
    "template_waveform": ("data", "property"),
    "template_vectorscope": ("data", "property"),
    "template_layers": ("data", "property", "used_layers_data", "used_layers_property", "active_layer"),
    "template_color_picker": ("data", "property", "value_slider", "lock", "lock_luminosity", "cubic"),
    "template_palette": ("data", "property"),
    "template_image_layers": ("image", "image_user"),
    "template_image": ("data", "property", "image_user", "compact", "multiview"),
    "template_image_settings": ("image_settings", "color_management"),
    "template_image_stereo_3d": ("stereo_3d_format",),
    "template_image_views": ("image_settings",),
    "template_movieclip": ("data", "property", "compact"),
    "template_track": ("data", "property"),
    "template_marker": ("data", "property", "clip_user", "track", "compact"),
    "template_movieclip_information": ("data", "property", "clip_user"),
    "template_list": ("listtype_name", "list_id", "dataptr", "propname", "active_dataptr", "active_propname", "item_dyntip_propname", "rows", "maxrows", "type", "columns", "sort_reverse", "sort_lock"),
    "template_running_jobs": (),
    "template_operator_search": (),
    "template_menu_search": (),
    "template_header_3D_mode": (),
    "template_edit_mode_selection": (),
    "template_reports_banner": (),
    "template_input_status": (),
    "template_status_info": (),
    "template_node_link": ("ntree", "node", "socket"),
    "template_node_view": ("ntree", "node", "socket"),
    "template_node_operator_registration_errors": ("idname",),
    "template_node_asset_menu_items": ("catalog_path", "operator"),
    "template_modifier_asset_menu_items": ("catalog_path", "skip_essentials"),
    "template_node_operator_asset_menu_items": ("catalog_path",),
    "template_node_operator_asset_root_items": (),
    "template_texture_user": (),
    "template_keymap_item_properties": ("item",),
    "template_component_menu": ("data", "property", "name"),
    "template_colorspace_settings": ("data", "property"),
    "template_colormanaged_view_settings": ("data", "property"),
    "template_node_socket": ("color",),
    "template_cache_file": ("data", "property"),
    "template_cache_file_velocity": ("data", "property"),
    "template_cache_file_time_settings": ("data", "property"),
    "template_cache_file_layers": ("data", "property"),
    "template_recent_files": ("rows", "found"),
    "template_file_select_path": ("params",),
    "template_event_from_keymap_item": ("item", "text", "text_ctxt", "translate"),
    "template_light_linking_collection": ("context_layout", "data", "property"),
    "template_bone_collection_tree": (),
    "template_grease_pencil_layer_tree": (),
    "template_node_tree_interface": ("interface",),
    "template_node_inputs": ("node",),
    "template_asset_shelf_popover": ("asset_shelf", "name", "icon", "icon_value"),
    "template_popup_confirm": ("operator", "text", "text_ctxt", "translate", "icon", "cancel_text", "cancel_default", "properties"),
    "template_shape_key_tree": (),
})

UILAYOUT_OUTPUTS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "row": ("layout",), "column": ("layout",), "column_flow": ("layout",), "grid_flow": ("layout",),
    "box": ("layout",), "split": ("layout",), "menu_pie": ("layout",),
    "panel": ("layout_header", "layout_body"), "panel_prop": ("layout_header", "layout_body"),
    "icon": ("icon_value",), "enum_item_icon": ("icon_value",), "enum_item_name": ("name",),
    "enum_item_description": ("description",),
    "operator": ("properties",), "operator_menu_hold": ("properties",), "operator_menu_enum": ("properties",),
    "template_popup_confirm": ("properties",),
    "template_recent_files": ("found",),
})

OPERATOR_CONTEXTS: tuple[str, ...] = (
    "INVOKE_DEFAULT", "INVOKE_REGION_WIN", "INVOKE_REGION_CHANNELS", "INVOKE_REGION_PREVIEW", "INVOKE_AREA",
    "INVOKE_SCREEN", "EXEC_DEFAULT", "EXEC_REGION_WIN", "EXEC_REGION_CHANNELS", "EXEC_REGION_PREVIEW",
    "EXEC_AREA", "EXEC_SCREEN",
)

_KEY_PATH = re.compile(r'^\[\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\')\s*\]$')
_PLACEHOLDER_KINDS = {"MT": Menu, "PT": Panel, "HT": Header, "UL": UIList}
_PLACEHOLDERS: dict[str, type] = {}


@dataclass(frozen=True)
class LayoutIssue:
    kind: str
    message: str
    detail: Mapping[str, object] = field(default_factory=dict)


@dataclass
class LayoutNode:
    kind: str
    args: tuple = ()
    kwargs: dict[str, object] = field(default_factory=dict)
    children: list["LayoutNode"] = field(default_factory=list)


class _AnyProperties:

    def __init__(self, idname: str) -> None:
        object.__setattr__(self, "_q_idname", idname)
        object.__setattr__(self, "_q_values", {})

    def __setattr__(self, name: str, value: object) -> None:
        self._q_values[name] = value

    def __getattr__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._q_values[name]
        except KeyError:
            raise AttributeError(f"'{self._q_idname}' properties have no attribute '{name}'") from None

    def __repr__(self) -> str:
        return f"<unknown operator properties {self._q_idname!r} {self._q_values!r}>"


def _struct_name(data: object) -> str:
    if data is None:
        return "None"
    rna = getattr(type(data), "bl_rna", None)
    ident = getattr(rna, "identifier", None)
    return ident if isinstance(ident, str) else type(data).__name__


def _has_data_descriptor(cls: type, name: str) -> bool:
    for klass in cls.__mro__:
        if name in klass.__dict__:
            attr = klass.__dict__[name]
            return hasattr(type(attr), "__set__") or hasattr(type(attr), "__delete__")
    return False


def _property_exists(data: object, prop: object) -> bool:
    if not isinstance(data, Struct) or not isinstance(prop, str):
        return False
    if get_property(data, prop) is not None:
        return True
    if _has_data_descriptor(type(data), prop):
        return True
    m = _KEY_PATH.match(prop)
    if m is not None:
        key = unescape_identifier(m.group(1) if m.group(1) is not None else m.group(2))
        try:
            return key in data
        except Exception:
            return False
    return False


def _is_operator_props_class(cls: type) -> bool:
    return isinstance(cls, type) and issubclass(cls, OperatorProperties) and cls is not OperatorProperties


def _idname_py(operator: str) -> str:
    if isinstance(operator, str) and "_OT_" in operator:
        try:
            return registry.operator_idname_py(operator)
        except ValueError:
            return operator
    return operator


def _recorder(fn):
    sig = inspect.signature(fn)
    name = fn.__name__

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        bound = sig.bind(self, *args, **kwargs)
        passed = {k: v for k, v in bound.arguments.items() if k != "self"}
        node = LayoutNode(name, (), passed, [])
        self._q_node.children.append(node)
        object.__setattr__(self, "_q_current", node)
        return fn(self, *args, **kwargs)
    return wrapper


@builtin_struct
class UILayout(Struct):
    _q_strict_attrs = True

    active: BoolProperty(name="Active", default=True)
    enabled: BoolProperty(name="Enabled", default=True)
    alert: BoolProperty(name="Alert", default=False)
    alignment: EnumProperty(items=[("EXPAND", "Expand", ""), ("LEFT", "Left", ""), ("CENTER", "Center", ""),
                                   ("RIGHT", "Right", "")], name="Alignment", default="EXPAND")
    scale_x: FloatProperty(name="Scale X", default=1.0, min=0.0)
    scale_y: FloatProperty(name="Scale Y", default=1.0, min=0.0)
    ui_units_x: FloatProperty(name="Units X", default=0.0, min=0.0)
    ui_units_y: FloatProperty(name="Units Y", default=0.0, min=0.0)
    use_property_split: BoolProperty(name="Use Property Split", default=False)
    use_property_decorate: BoolProperty(name="Use Property Decorate", default=True)
    operator_context: EnumProperty(items=[(c, c, "") for c in OPERATOR_CONTEXTS], name="Operator Context",
                                   default="INVOKE_REGION_WIN")
    emboss: EnumProperty(items=[("NORMAL", "Regular", ""), ("NONE", "None", ""), ("PULLDOWN_MENU", "Pulldown Menu", ""),
                                ("PIE_MENU", "Pie Menu", ""), ("NONE_OR_STATUS", "None or Status", "")],
                         name="Emboss", default="NORMAL")
    activate_init: BoolProperty(name="Activate on Init", default=False)
    active_default: BoolProperty(name="Active Default", default=False)

    def __init__(self) -> None:
        object.__setattr__(self, "_q_node", LayoutNode("ROOT", (), {}, []))
        object.__setattr__(self, "_q_issue_list", [])
        object.__setattr__(self, "_q_current", None)

    def _q_child(self, node: LayoutNode) -> "UILayout":
        child = UILayout.__new__(UILayout)
        object.__setattr__(child, "_q_node", node)
        object.__setattr__(child, "_q_issue_list", self._q_issue_list)
        object.__setattr__(child, "_q_current", None)
        child._p.update(self._p)
        child._p_set.update(self._p_set)
        return child

    def _q_add_child_node(self, kind: str) -> "UILayout":
        node = LayoutNode(kind, (), {}, [])
        self._q_node.children.append(node)
        return self._q_child(node)

    def _q_issue(self, kind: str, message: str, detail: Mapping[str, object]) -> None:
        self._q_issue_list.append(LayoutIssue(kind, message, dict(detail)))

    def _q_check(self, function: str, data: object, prop: object) -> bool:
        if _property_exists(data, prop):
            return True
        tname = _struct_name(data)
        self._q_issue("UNKNOWN_PROPERTY", f"{tname}.{prop} not found",
                      {"function": function, "struct": tname, "property": prop})
        dtype = type(data)
        if data is not None and "_q_builtin" in dtype.__dict__ and not _is_operator_props_class(dtype):
            hooks.note_missing(f"bpy.types.{tname}.{prop}")
        return False

    def _q_operator(self, node: LayoutNode, operator: object, returns_props: bool = True) -> object:
        cls = registry.operator_class(operator) if isinstance(operator, str) else None
        if cls is not None:
            if not returns_props:
                return None
            props = cls.q_new_properties()
            node.kwargs["properties"] = props
            return props
        self._q_issue("UNKNOWN_OPERATOR", f"operator {operator} not found", {"operator": operator})
        hooks.note_missing(f"bpy.ops.{_idname_py(operator)}")
        if not returns_props:
            return None
        props = _AnyProperties(str(operator))
        node.kwargs["properties"] = props
        return props

    def _q_layout_result(self) -> "UILayout":
        return self._q_child(self._q_current)

    @property
    def q_issues(self) -> list[LayoutIssue]:
        return self._q_issue_list

    def q_tree(self) -> LayoutNode:
        return self._q_node

    @_recorder
    def row(self, align: bool = False, heading: str = "", heading_ctxt: str = "", translate: bool = True) -> "UILayout":
        return self._q_layout_result()

    @_recorder
    def column(self, align: bool = False, heading: str = "", heading_ctxt: str = "",
               translate: bool = True) -> "UILayout":
        return self._q_layout_result()

    @_recorder
    def column_flow(self, columns: int = 0, align: bool = False) -> "UILayout":
        return self._q_layout_result()

    @_recorder
    def grid_flow(self, row_major: bool = False, columns: int = 0, even_columns: bool = False, even_rows: bool = False,
                  align: bool = False) -> "UILayout":
        return self._q_layout_result()

    @_recorder
    def box(self) -> "UILayout":
        return self._q_layout_result()

    @_recorder
    def split(self, factor: float = 0.0, align: bool = False) -> "UILayout":
        return self._q_layout_result()

    def _q_panel_pair(self, open_body: bool) -> tuple["UILayout", "UILayout | None"]:
        node = self._q_current
        holder = self._q_child(node)
        header = holder._q_add_child_node("layout_header")
        body = holder._q_add_child_node("layout_body")
        return header, (body if open_body else None)

    @_recorder
    def panel(self, idname: str, default_closed: bool = False) -> tuple["UILayout", "UILayout | None"]:
        return self._q_panel_pair(not default_closed)

    @_recorder
    def panel_prop(self, data: object, property: str) -> tuple["UILayout", "UILayout | None"]:
        node = self._q_current
        ok = self._q_check("panel_prop", data, property)
        is_open = False
        if ok:
            try:
                is_open = bool(getattr(data, property))
            except Exception:
                is_open = False
        object.__setattr__(self, "_q_current", node)
        return self._q_panel_pair(is_open)

    @_recorder
    def menu_pie(self) -> "UILayout":
        return self._q_layout_result()

    @_recorder
    def prop(self, data: object, property: str, text: str | None = None, text_ctxt: str = "", translate: bool = True,
             icon: str = "NONE", placeholder: str = "", expand: bool = False, slider: bool = False, toggle: int = -1,
             icon_only: bool = False, event: bool = False, full_event: bool = False, emboss: bool = True,
             index: int = -1, icon_value: int = 0, invert_checkbox: bool = False, text_align: str = "") -> None:
        self._q_check("prop", data, property)

    @_recorder
    def props_enum(self, data: object, property: str) -> None:
        self._q_check("props_enum", data, property)

    @_recorder
    def prop_menu_enum(self, data: object, property: str, text: str | None = None, text_ctxt: str = "",
                       translate: bool = True, icon: str = "NONE") -> None:
        self._q_check("prop_menu_enum", data, property)

    @_recorder
    def prop_enum(self, data: object, property: str, value: str, text: str | None = None, text_ctxt: str = "",
                  translate: bool = True, icon: str = "NONE") -> None:
        self._q_check("prop_enum", data, property)

    @_recorder
    def prop_search(self, data: object, property: str, search_data: object, search_property: str,
                    text: str | None = None, text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
                    results_are_suggestions: bool = False, item_search_property: str = "") -> None:
        self._q_check("prop_search", data, property)
        self._q_check("prop_search", search_data, search_property)

    @_recorder
    def prop_tabs_enum(self, data: object, property: str, data_highlight: object = None, property_highlight: str = "",
                       icon_only: bool = False, expand_as: str = "") -> None:
        self._q_check("prop_tabs_enum", data, property)

    @_recorder
    def prop_decorator(self, data: object, property: str, index: int = -1) -> None:
        self._q_check("prop_decorator", data, property)

    @_recorder
    def operator(self, operator: str, text: str | None = None, text_ctxt: str = "", translate: bool = True,
                 icon: str = "NONE", emboss: bool = True, depress: bool = False, icon_value: int = 0,
                 search_weight: float = 0.0) -> OperatorProperties:
        return self._q_operator(self._q_current, operator)

    @_recorder
    def operator_enum(self, operator: str, property: str, icon_only: bool = False) -> None:
        return self._q_operator(self._q_current, operator, returns_props=False)

    @_recorder
    def operator_menu_enum(self, operator: str, property: str, text: str | None = None, text_ctxt: str = "",
                           translate: bool = True, icon: str = "NONE") -> OperatorProperties:
        return self._q_operator(self._q_current, operator)

    @_recorder
    def label(self, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
              icon_value: int = 0) -> None:
        return None

    def _q_check_menu(self, menu: object) -> None:
        cls = registry.lookup(menu) if isinstance(menu, str) else None
        if not (isinstance(cls, type) and issubclass(cls, Menu)):
            self._q_issue("UNKNOWN_MENU", f"menu {menu} not found", {"menu": menu})

    @_recorder
    def menu(self, menu: str, text: str | None = None, text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
             icon_value: int = 0) -> None:
        self._q_check_menu(menu)

    @_recorder
    def menu_contents(self, menu: str) -> None:
        self._q_check_menu(menu)

    @_recorder
    def popover(self, panel: str, text: str | None = None, text_ctxt: str = "", translate: bool = True,
                icon: str = "NONE", icon_value: int = 0, direction: str = "") -> None:
        cls = registry.lookup(panel) if isinstance(panel, str) else None
        if not (isinstance(cls, type) and issubclass(cls, Panel)):
            self._q_issue("UNKNOWN_PANEL", f"panel {panel} not found", {"panel": panel})

    @_recorder
    def separator(self, factor: float = 1.0, type: str = "AUTO") -> None:
        return None

    @_recorder
    def separator_spacer(self) -> None:
        return None

    @_recorder
    def progress(self, text: str = "", text_ctxt: str = "", translate: bool = True, factor: float = 0.0,
                 type: str = "BAR") -> None:
        return None

    @_recorder
    def context_pointer_set(self, name: str, data: object) -> None:
        return None

    @_recorder
    def context_string_set(self, name: str, value: str) -> None:
        return None

    @_recorder
    def template_list(self, listtype_name: str, list_id: str, dataptr: object, propname: str, active_dataptr: object,
                      active_propname: str, item_dyntip_propname: str = "", rows: int = 5, maxrows: int = 5,
                      type: str = "DEFAULT", columns: int = 9, sort_reverse: bool = False,
                      sort_lock: bool = False) -> None:
        self._q_check("template_list", dataptr, propname)
        self._q_check("template_list", active_dataptr, active_propname)

    @_recorder
    def template_ID(self, data: object, property: str, new: str = "", open: str = "", unlink: str = "",
                    filter: str = "ALL", live_icon: bool = False, text: str | None = None, text_ctxt: str = "",
                    translate: bool = True) -> None:
        self._q_check("template_ID", data, property)

    @_recorder
    def template_popup_confirm(self, operator: str, text: str | None = None, text_ctxt: str = "",
                               translate: bool = True, icon: str = "NONE", cancel_text: str = "",
                               cancel_default: bool = False) -> OperatorProperties | None:
        if operator == "":
            return None
        return self._q_operator(self._q_current, operator)

    @_recorder
    def icon(self, data: object) -> int:
        return 0

    def _q_enum_item(self, function: str, data: object, property: str, identifier: str):
        if not self._q_check(function, data, property):
            return None
        pdef = get_property(data, property)
        if not isinstance(pdef, EnumDef):
            return None
        try:
            items = pdef.items_for(data, hooks.current_context())
        except Exception:
            return None
        for item in items:
            if item.identifier == identifier:
                return item
        return None

    @_recorder
    def enum_item_name(self, data: object, property: str, identifier: str) -> str:
        item = self._q_enum_item("enum_item_name", data, property, identifier)
        return item.name if item is not None else ""

    @_recorder
    def enum_item_description(self, data: object, property: str, identifier: str) -> str:
        item = self._q_enum_item("enum_item_description", data, property, identifier)
        return item.description if item is not None else ""

    @_recorder
    def enum_item_icon(self, data: object, property: str, identifier: str) -> int:
        item = self._q_enum_item("enum_item_icon", data, property, identifier)
        if item is None:
            return 0
        icon = item.icon
        return icon if isinstance(icon, int) and not isinstance(icon, bool) else 0

    def __getattr__(self, name: str) -> Callable[..., object]:
        if name.startswith("_"):
            raise AttributeError(f"'UILayout' object has no attribute '{name}'")
        params = UILAYOUT_FUNCTIONS.get(name)
        if params is not None:
            return self._q_generic(name, params)
        if app_settings.settings.strict_layout:
            raise AttributeError(f"'UILayout' object has no attribute '{name}'")

        def unknown(*args, **kwargs):
            self._q_node.children.append(LayoutNode(name, tuple(args), dict(kwargs), []))
            self._q_issue("UNKNOWN_FUNCTION", f"UILayout.{name} is not a known layout function", {"function": name})
            hooks.note_missing(f"bpy.types.UILayout.{name}")
            return None
        unknown.__name__ = name
        return unknown

    def _q_generic(self, name: str, params: tuple[str, ...]) -> Callable[..., object]:
        outputs = UILAYOUT_OUTPUTS.get(name, ())
        inputs = [p for p in params if p not in outputs]
        checks_prop = inputs[:2] == ["data", "property"]

        def generic(*args, **kwargs):
            node = LayoutNode(name, tuple(args), dict(kwargs), [])
            self._q_node.children.append(node)
            if checks_prop:
                data = args[0] if len(args) > 0 else kwargs.get("data")
                prop = args[1] if len(args) > 1 else kwargs.get("property")
                self._q_check(name, data, prop)
            if outputs == ("layout",):
                return self._q_child(node)
            if outputs == ("properties",):
                operator = args[0] if args else kwargs.get("operator")
                return self._q_operator(node, operator)
            return None
        generic.__name__ = name
        return generic


@dataclass
class DrawResult:
    layout: UILayout | None
    poll: bool | None
    issues: list[LayoutIssue]

    @property
    def ok(self) -> bool:
        return not any(i.kind in ("DRAW_EXCEPTION", "POLL_EXCEPTION") for i in self.issues)


def _exception_issue(root: UILayout, kind: str, exc: BaseException, detail: dict) -> None:
    text = traceback.format_exc()
    sys.stderr.write(text)
    detail = dict(detail)
    detail["traceback"] = text
    root._q_issue(kind, f"{type(exc).__name__}: {exc}", detail)


def _call_draw(root: UILayout, rna_name: str, fn: Callable, *args) -> None:
    try:
        fn(*args)
    except Exception as exc:
        _exception_issue(root, "DRAW_EXCEPTION", exc,
                         {"class": rna_name, "function": getattr(fn, "__qualname__", repr(fn))})


def draw_ui(cls: type, context: object | None = None, *, check_poll: bool = True) -> DrawResult:
    if not (isinstance(cls, type) and issubclass(cls, (Panel, Menu, Header, UIList))):
        raise TypeError(f"draw_ui() expects a Panel, Menu, Header or UIList subclass, not {cls!r}")
    if context is None:
        context = hooks.current_context()
    rna_name = registry.rna_name_of(cls)
    root = UILayout()
    poll: bool | None = None
    if check_poll and hasattr(cls, "poll"):
        try:
            ok = bool(cls.poll(context))
        except Exception as exc:
            _exception_issue(root, "POLL_EXCEPTION", exc, {"class": rna_name, "function": "poll"})
            ok = False
        if not ok:
            return DrawResult(None, False, list(root.q_issues))
        poll = True
    inst = cls()
    object.__setattr__(inst, "_q_layout", root)
    if issubclass(cls, Panel):
        for attr, kind in (("draw_header", "HEADER"), ("draw_header_preset", "HEADER_PRESET")):
            if hasattr(cls, attr):
                child = root._q_add_child_node(kind)
                object.__setattr__(inst, "_q_layout", child)
                try:
                    _call_draw(root, rna_name, getattr(cls, attr), inst, context)
                finally:
                    object.__setattr__(inst, "_q_layout", root)
    elif issubclass(cls, UIList) and hasattr(cls, "draw_filter"):
        _call_draw(root, rna_name, getattr(cls, "draw_filter"), inst, context, root)
    had_ctx = "operator_context" in root._p
    saved_ctx = root._p.get("operator_context")
    saved_set = "operator_context" in root._p_set
    for fn in draw_sequence(cls):
        if had_ctx:
            root._p["operator_context"] = saved_ctx
        else:
            root._p.pop("operator_context", None)
        if saved_set:
            root._p_set.add("operator_context")
        else:
            root._p_set.discard("operator_context")
        _call_draw(root, rna_name, fn, inst, context)
    return DrawResult(root, poll, list(root.q_issues))


def draw_panel(cls: type, context: object | None = None) -> DrawResult:
    if not (isinstance(cls, type) and issubclass(cls, Panel)):
        raise TypeError(f"draw_panel() expects a Panel subclass, not {cls!r}")
    return draw_ui(cls, context)


def draw_menu(cls: type, context: object | None = None) -> DrawResult:
    if not (isinstance(cls, type) and issubclass(cls, Menu)):
        raise TypeError(f"draw_menu() expects a Menu subclass, not {cls!r}")
    return draw_ui(cls, context)


def draw_ui_list(cls: type, data: object, propname: str, context: object | None = None) -> DrawResult:
    if not (isinstance(cls, type) and issubclass(cls, UIList)):
        raise TypeError(f"draw_ui_list() expects a UIList subclass, not {cls!r}")
    if context is None:
        context = hooks.current_context()
    rna_name = registry.rna_name_of(cls)
    root = UILayout()
    inst = cls()
    get_property(UIList, "list_id").write_raw(inst, "")
    object.__setattr__(inst, "_q_layout", root)
    if not root._q_check("draw_ui_list", data, propname):
        return DrawResult(root, None, list(root.q_issues))
    items = list(getattr(data, propname))
    flags: list = []
    neworder: list = []
    if hasattr(cls, "filter_items"):
        try:
            result = inst.filter_items(context, data, propname)
            flags, neworder = list(result[0] or []), list(result[1] or [])
            if (flags and len(flags) != len(items)) or (neworder and len(neworder) != len(items)):
                raise ValueError(f"filter_items() returned {len(flags)} flags and {len(neworder)} positions "
                                 f"for {len(items)} items")
        except Exception as exc:
            _exception_issue(root, "DRAW_EXCEPTION", exc, {"class": rna_name, "function": "filter_items"})
            flags, neworder = [], []
    filter_bit = inst.bitflag_filter_item
    never_bit = inst.bitflag_item_never_show
    visible = []
    for i in range(len(items)):
        flag_i = flags[i] if flags else filter_bit
        if flag_i & filter_bit and not flag_i & never_bit:
            visible.append((i, flag_i))
    visible.sort(key=lambda e: neworder[e[0]] if neworder else e[0])
    draw_item = getattr(cls, "draw_item", None) if hasattr(cls, "draw_item") else None
    for i, flag_i in visible:
        item = items[i]
        row = root.row()
        if draw_item is not None:
            _call_draw(root, rna_name, draw_item, inst, context, row, data, item, 0, data, propname, i, flag_i)
        else:
            row.label(text=getattr(item, "name", ""))
    if hasattr(cls, "draw_filter"):
        child = root._q_add_child_node("FILTER")
        _call_draw(root, rna_name, getattr(cls, "draw_filter"), inst, context, child)
    return DrawResult(root, None, list(root.q_issues))


def _noop_draw(self, context):
    return None


def _noop_draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
    return None


def placeholder_type(name: str, kind: str, *, owner: str = "quartz.placeholder") -> type:
    if kind not in _PLACEHOLDER_KINDS or not isinstance(name, str) or \
            re.fullmatch(rf"[A-Za-z0-9_]+_{kind}_[A-Za-z0-9_]+", name) is None:
        raise ValueError(f"'{name}' does not follow the '<PREFIX>_{kind}_<suffix>' naming convention")
    cls = _PLACEHOLDERS.get(name)
    if cls is None:
        base = _PLACEHOLDER_KINDS[kind]
        namespace: dict[str, object] = {
            "__module__": "quartz.placeholder", "__qualname__": name, "bl_idname": name, "bl_label": name,
            "bl_space_type": "EMPTY", "_q_placeholder": True, "_q_placeholder_kind": kind,
        }
        if kind == "UL":
            namespace["draw_item"] = _noop_draw_item
        else:
            namespace["draw"] = _noop_draw
        if kind == "PT":
            namespace["bl_region_type"] = "WINDOW"
        elif kind == "HT":
            namespace["bl_region_type"] = "HEADER"
        cls = type(base)(name, (base,), namespace)
        _PLACEHOLDERS[name] = cls
    elif cls.__dict__.get("_q_placeholder_kind") != kind:
        raise ValueError(f"placeholder '{name}' already exists with kind {cls.__dict__.get('_q_placeholder_kind')!r}")
    if not registry.is_registered(cls) and registry.lookup(name, resolve=False) is None:
        with registry.owner_scope(owner):
            registry.register_class(cls)
    return cls
