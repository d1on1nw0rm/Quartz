from quartz.errors import NotImplementedInQuartz, PropertyTypeError, PropertyValueError
from quartz.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from quartz.rna import IDRef, PropCollection, Struct, builtin_struct
from quartz.rna.datapath import escape_identifier
import quartz.types as _types
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type
from quartz.types.object import OBJECT_MODES
from quartz.types.scene import Scene

__all__ = [
    "EVENT_TYPES", "Screen", "WorkSpace", "Timer", "Window", "Windows", "KeyMapItem", "KeyMap", "KeyMapItems",
    "KeyMaps", "KeyConfig", "KeyConfigurations", "WindowManager", "BlendDataWindowManagers", "BlendDataScreens",
    "BlendDataWorkSpaces",
]

EVENT_TYPES: tuple[str, ...] = (
    "NONE", "LEFTMOUSE", "MIDDLEMOUSE", "RIGHTMOUSE", "BUTTON4MOUSE", "BUTTON5MOUSE", "BUTTON6MOUSE",
    "BUTTON7MOUSE", "PEN", "ERASER", "MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "TRACKPADPAN", "TRACKPADZOOM",
    "MOUSEROTATE", "MOUSESMARTZOOM", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
    "WHEELLEFTMOUSE", "WHEELRIGHTMOUSE", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O",
    "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX",
    "SEVEN", "EIGHT", "NINE", "LEFT_CTRL", "LEFT_ALT", "LEFT_SHIFT", "RIGHT_ALT", "RIGHT_CTRL", "RIGHT_SHIFT",
    "OSKEY", "HYPER", "APP", "GRLESS", "ESC", "TAB", "RET", "SPACE", "LINE_FEED", "BACK_SPACE", "DEL", "SEMI_COLON",
    "PERIOD", "COMMA", "QUOTE", "ACCENT_GRAVE", "MINUS", "PLUS", "SLASH", "BACK_SLASH", "EQUAL", "LEFT_BRACKET",
    "RIGHT_BRACKET", "LEFT_ARROW", "DOWN_ARROW", "RIGHT_ARROW", "UP_ARROW", "NUMPAD_2", "NUMPAD_4", "NUMPAD_6",
    "NUMPAD_8", "NUMPAD_1", "NUMPAD_3", "NUMPAD_5", "NUMPAD_7", "NUMPAD_9", "NUMPAD_PERIOD", "NUMPAD_SLASH",
    "NUMPAD_ASTERIX", "NUMPAD_0", "NUMPAD_MINUS", "NUMPAD_ENTER", "NUMPAD_PLUS", "F1", "F2", "F3", "F4", "F5", "F6",
    "F7", "F8", "F9", "F10", "F11", "F12", "F13", "F14", "F15", "F16", "F17", "F18", "F19", "F20", "F21", "F22",
    "F23", "F24", "PAUSE", "INSERT", "HOME", "PAGE_UP", "PAGE_DOWN", "END", "MEDIA_PLAY", "MEDIA_STOP",
    "MEDIA_FIRST", "MEDIA_LAST", "TEXTINPUT", "WINDOW_DEACTIVATE", "TIMER", "TIMER0", "TIMER1", "TIMER2",
    "TIMER_JOBS", "TIMER_AUTOSAVE", "TIMER_REPORT", "TIMERREGION", "NDOF_MOTION", "NDOF_BUTTON_MENU",
    "NDOF_BUTTON_FIT", "NDOF_BUTTON_TOP", "NDOF_BUTTON_BOTTOM", "NDOF_BUTTON_LEFT", "NDOF_BUTTON_RIGHT",
    "NDOF_BUTTON_FRONT", "NDOF_BUTTON_BACK", "NDOF_BUTTON_ISO1", "NDOF_BUTTON_ISO2", "NDOF_BUTTON_ROLL_CW",
    "NDOF_BUTTON_ROLL_CCW", "NDOF_BUTTON_SPIN_CW", "NDOF_BUTTON_SPIN_CCW", "NDOF_BUTTON_TILT_CW",
    "NDOF_BUTTON_TILT_CCW", "NDOF_BUTTON_ROTATE", "NDOF_BUTTON_PANZOOM", "NDOF_BUTTON_DOMINANT", "NDOF_BUTTON_PLUS",
    "NDOF_BUTTON_MINUS", "NDOF_BUTTON_V1", "NDOF_BUTTON_V2", "NDOF_BUTTON_V3", "NDOF_BUTTON_SAVE_V1",
    "NDOF_BUTTON_SAVE_V2", "NDOF_BUTTON_SAVE_V3", "NDOF_BUTTON_1", "NDOF_BUTTON_2", "NDOF_BUTTON_3",
    "NDOF_BUTTON_4", "NDOF_BUTTON_5", "NDOF_BUTTON_6", "NDOF_BUTTON_7", "NDOF_BUTTON_8", "NDOF_BUTTON_9",
    "NDOF_BUTTON_10", "NDOF_BUTTON_11", "NDOF_BUTTON_12", "ACTIONZONE_AREA", "ACTIONZONE_REGION",
    "ACTIONZONE_REGION_QUAD", "ACTIONZONE_FULLSCREEN", "XR_ACTION"
)

_SPACE_TYPES = ("EMPTY", "VIEW_3D", "IMAGE_EDITOR", "NODE_EDITOR", "SEQUENCE_EDITOR", "CLIP_EDITOR",
                "DOPESHEET_EDITOR", "GRAPH_EDITOR", "NLA_EDITOR", "TEXT_EDITOR", "CONSOLE", "INFO", "TOPBAR",
                "STATUSBAR", "OUTLINER", "PROPERTIES", "FILE_BROWSER", "SPREADSHEET", "PREFERENCES")
_REGION_TYPES = ("WINDOW", "HEADER", "CHANNELS", "TEMPORARY", "UI", "TOOLS", "TOOL_PROPS", "ASSET_SHELF",
                 "ASSET_SHELF_HEADER", "PREVIEW", "HUD", "NAVIGATION_BAR", "EXECUTE", "FOOTER", "TOOL_HEADER", "XR",
                 "SCRUBBING")
_VALUES = ("ANY", "PRESS", "RELEASE", "CLICK", "DOUBLE_CLICK", "CLICK_DRAG", "NOTHING")
_DIRECTIONS = ("ANY", "NORTH", "NORTH_EAST", "EAST", "SOUTH_EAST", "SOUTH", "SOUTH_WEST", "WEST", "NORTH_WEST")
_MAP_TYPES = ("KEYBOARD", "MOUSE", "NDOF", "TEXTINPUT", "TIMER")
_MAX_OPERATORS = 32
_RO = {"readonly": True}

_NOT_IMPLEMENTED_WM = (
    "gizmo_group_type_ensure", "gizmo_group_type_unlink_delayed", "popmenu_begin__internal", "popmenu_end__internal",
    "popover_begin__internal", "popover_end__internal", "piemenu_begin__internal", "piemenu_end__internal",
    "print_undo_steps", "tag_script_reload", "asset_library_status_begin_loading",
    "asset_library_status_ping_still_loading", "asset_library_status_ping_metafiles_in_place",
    "asset_library_status_ping_loaded_new_pages", "asset_library_status_ping_loaded_new_preview",
    "asset_library_status_ping_asset_file_progress", "asset_library_status_ping_asset_file_succeeded",
    "asset_library_status_ping_asset_file_failed", "asset_library_status_ping_finished_download_queue",
    "asset_library_status_finished_loading", "asset_library_status_failed_loading", "register_node_group_operators",
    "draw_cursor_add", "draw_cursor_remove",
)


def _items(seq):
    return [(t, t, "") for t in seq]


def _enum_error(where: str, value, items) -> PropertyTypeError:
    listing = ", ".join(repr(i) for i in items)
    return PropertyTypeError(f'{where}: enum "{value}" not found in ({listing})')


class _NoAttribute:

    def __set_name__(self, owner, name):
        self._q_name = name

    def __get__(self, inst, owner=None):
        who = type(inst).__name__ if inst is not None else owner.__name__
        raise AttributeError(f"'{who}' object has no attribute '{self._q_name}'")


def _false(self):
    return False


@builtin_struct
class Screen(ID):

    _q_strict_attrs = True

    is_temporary: BoolProperty(options=set(), meta={"virtual_get": _false})

    @property
    def areas(self) -> tuple:
        return ()


@builtin_struct
class WorkSpace(ID):

    _q_strict_attrs = True

    object_mode: EnumProperty(items=_items(OBJECT_MODES), default="OBJECT")

    @property
    def tools(self) -> tuple:
        return ()


@builtin_struct
class Timer(Struct):

    _q_strict_attrs = True

    time_step: FloatProperty(options=set(), meta=_RO)
    time_delta: FloatProperty(options=set(), meta=_RO)
    time_duration: FloatProperty(options=set(), meta=_RO)


@builtin_struct
class Window(Struct):

    _q_strict_attrs = True

    scene: PointerProperty(type=Scene, options=set(), meta={"counts_user": False})
    screen: PointerProperty(type=Screen, options=set(), meta={"counts_user": False, "readonly": True})
    workspace: PointerProperty(type=WorkSpace, options=set(), meta={"counts_user": False})
    x: IntProperty(options=set(), meta=_RO)
    y: IntProperty(options=set(), meta=_RO)
    width: IntProperty(options=set(), meta=_RO)
    height: IntProperty(options=set(), meta=_RO)

    @classmethod
    def _q_create(cls, wm, index: int, scene=None) -> "Window":
        win = cls._q_new_child(owner=wm, path=f"windows[{index}]")
        object.__setattr__(win, "_q_view_layer", None)
        pdefs = Window.__dict__
        pdefs["x"].write_raw(win, 0)
        pdefs["y"].write_raw(win, 0)
        pdefs["width"].write_raw(win, 1920)
        pdefs["height"].write_raw(win, 1080)
        if scene is not None:
            pdefs["scene"].write_raw(win, scene)
            layers = list(scene.view_layers)
            win._q_view_layer = layers[0] if layers else None
        return win

    def _q_sync_view_layer(self) -> None:
        scene = self._p.get("scene")
        vl = self._q_view_layer
        if scene is None:
            self._q_view_layer = None
        elif vl is None or not any(v is vl for v in scene.view_layers):
            layers = list(scene.view_layers)
            self._q_view_layer = layers[0] if layers else None

    def _q_on_change(self, pdef) -> None:
        if pdef.identifier == "scene":
            self._q_sync_view_layer()
        super()._q_on_change(pdef)

    @property
    def view_layer(self):
        return self._q_view_layer

    @view_layer.setter
    def view_layer(self, value) -> None:
        if value is not None:
            scene = self._p.get("scene")
            if scene is None or not any(v is value for v in scene.view_layers):
                raise PropertyValueError(f"Window.view_layer: view layer '{getattr(value, 'name', value)}' "
                                         f"not in scene '{getattr(scene, 'name', None)}'")
        self._q_view_layer = value


class Windows(PropCollection):

    def __init__(self, wm: "WindowManager") -> None:
        super().__init__(owner=wm, path="windows")
        self._q_wm = wm

    def _q_items(self):
        return self._q_wm._q_windows

    def _q_key(self, item):
        return None

    def find_playing(self, scrub: bool = False):
        return None


def _kmi_shift_ui_getter(field: str):
    def getter(self):
        return _raw_int(self, field) == 1
    return getter


def _kmi_shift_ui_setter(field: str):
    def setter(self, value):
        KeyMapItem.__dict__[field].write_raw(self, 1 if value else 0)
    return setter


def _raw_int(st, field: str) -> int:
    return int(type(st).__dict__[field].read_raw(st))


def _kmi_name(self):
    return self._p.get("idname", "")


def _modifier_int(value, field: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, int):
        raise PropertyTypeError(f'KeyMapItems.new(): error with keyword argument "{field}" - expected an int type, '
                                f'not {type(value).__name__}')
    return max(-1, min(1, value))


@builtin_struct
class KeyMapItem(Struct):

    _q_strict_attrs = True

    idname: StringProperty(maxlen=64, options=set())
    name: StringProperty(options=set(), meta={"virtual_get": _kmi_name})
    map_type: EnumProperty(items=_items(_MAP_TYPES), default="KEYBOARD")
    type: EnumProperty(items=_items(EVENT_TYPES), default="NONE")
    value: EnumProperty(items=_items(_VALUES), default="NOTHING")
    direction: EnumProperty(items=_items(_DIRECTIONS), default="ANY")
    id: IntProperty(min=-32768, max=32767, meta=_RO)
    any: BoolProperty()
    shift: IntProperty(min=-1, max=1)
    ctrl: IntProperty(min=-1, max=1)
    alt: IntProperty(min=-1, max=1)
    oskey: IntProperty(min=-1, max=1)
    hyper: IntProperty(min=-1, max=1)
    shift_ui: BoolProperty(meta={"virtual_get": _kmi_shift_ui_getter("shift"),
                                 "virtual_set": _kmi_shift_ui_setter("shift")})
    ctrl_ui: BoolProperty(meta={"virtual_get": _kmi_shift_ui_getter("ctrl"),
                                "virtual_set": _kmi_shift_ui_setter("ctrl")})
    alt_ui: BoolProperty(meta={"virtual_get": _kmi_shift_ui_getter("alt"),
                               "virtual_set": _kmi_shift_ui_setter("alt")})
    oskey_ui: BoolProperty(meta={"virtual_get": _kmi_shift_ui_getter("oskey"),
                                 "virtual_set": _kmi_shift_ui_setter("oskey")})
    hyper_ui: BoolProperty(meta={"virtual_get": _kmi_shift_ui_getter("hyper"),
                                 "virtual_set": _kmi_shift_ui_setter("hyper")})
    key_modifier: EnumProperty(items=_items(EVENT_TYPES), default="NONE")
    repeat: BoolProperty()
    show_expanded: BoolProperty()
    active: BoolProperty()
    is_user_modified: BoolProperty(meta=_RO)
    is_user_defined: BoolProperty(meta=_RO)

    @classmethod
    def _q_create(cls, owner, path: str) -> "KeyMapItem":
        item = cls._q_new_child(owner=owner, path=path)
        object.__setattr__(item, "_q_propvalue", "NONE")
        object.__setattr__(item, "_q_props_cache", None)
        return item

    @property
    def properties(self):
        idname = self._p.get("idname", "")
        cache = self._q_props_cache
        if cache is not None and cache[0] == idname:
            return cache[1]
        if "." not in idname:
            self._q_props_cache = None
            return None
        mod, op = idname.split(".", 1)
        cls = _types.resolve_name(f"{mod.upper()}_OT_{op}")
        if cls is None or not hasattr(cls, "q_new_properties"):
            self._q_props_cache = None
            return None
        props = cls.q_new_properties()
        self._q_props_cache = (idname, props)
        return props

    @property
    def propvalue(self) -> str:
        return self._q_propvalue

    @propvalue.setter
    def propvalue(self, value: str) -> None:
        if not isinstance(value, str):
            raise PropertyTypeError(f"KeyMapItem.propvalue expected a string type, not {type(value).__name__}")
        self._q_propvalue = value

    def compare(self, item) -> bool:
        fields = ("idname", "type", "value", "any", "shift", "ctrl", "alt", "oskey", "hyper", "key_modifier",
                  "direction", "repeat")
        pdefs = KeyMapItem.__dict__
        same = all(pdefs[f].read_raw(self) == pdefs[f].read_raw(item) for f in fields)
        return bool(same and self._q_propvalue == item._q_propvalue)

    def to_string(self, compact: bool = False):
        raise NotImplementedInQuartz("KeyMapItem.to_string")


class KeyMapItems(PropCollection):

    def __init__(self, km: "KeyMap") -> None:
        super().__init__(owner=km, path="keymap_items")
        self._q_km = km

    def _q_items(self):
        return self._q_km._q_items_list

    def _q_key(self, item):
        return item._p.get("idname", "")

    def _q_reindex(self) -> None:
        for i, item in enumerate(self._q_km._q_items_list):
            item._q_set_owner(self._q_km, f"keymap_items[{i}]")

    def _q_add(self, *, idname: str, type: str, value: str, any: bool, shift, ctrl, alt, oskey, hyper,
               key_modifier: str, direction: str, repeat: bool, head: bool, propvalue: str | None = None):
        if type not in EVENT_TYPES:
            raise _enum_error('KeyMapItems.new(): error with argument "type"', type, EVENT_TYPES)
        if value not in _VALUES:
            raise _enum_error('KeyMapItems.new(): error with argument "value"', value, _VALUES)
        if key_modifier not in EVENT_TYPES:
            raise _enum_error('KeyMapItems.new(): error with keyword argument "key_modifier"', key_modifier,
                              EVENT_TYPES)
        if direction not in _DIRECTIONS:
            raise _enum_error('KeyMapItems.new(): error with keyword argument "direction"', direction, _DIRECTIONS)
        if not isinstance(idname, str):
            raise PropertyTypeError(f"KeyMapItems.new(): error with argument 1 - expected a string type, "
                                    f"not {idname.__class__.__name__}")
        km = self._q_km
        item = KeyMapItem._q_create(km, "")
        pdefs = KeyMapItem.__dict__
        km._q_next_id += 1
        values = {"idname": idname, "type": type, "value": value, "any": bool(any),
                  "shift": _modifier_int(shift, "shift"), "ctrl": _modifier_int(ctrl, "ctrl"),
                  "alt": _modifier_int(alt, "alt"), "oskey": _modifier_int(oskey, "oskey"),
                  "hyper": _modifier_int(hyper, "hyper"), "key_modifier": key_modifier, "direction": direction,
                  "repeat": bool(repeat), "id": km._q_next_id}
        for field, v in values.items():
            pdefs[field].write_raw(item, v)
        if propvalue is not None:
            item._q_propvalue = propvalue
        if head:
            km._q_items_list.insert(0, item)
        else:
            km._q_items_list.append(item)
        self._q_reindex()
        return item

    def new(self, idname: str, type: str, value: str, any: bool = False, shift: int = 0, ctrl: int = 0, alt: int = 0,
            oskey: int = 0, hyper: int = 0, key_modifier: str = "NONE", direction: str = "ANY", repeat: bool = False,
            head: bool = False):
        return self._q_add(idname=idname, type=type, value=value, any=any, shift=shift, ctrl=ctrl, alt=alt,
                           oskey=oskey, hyper=hyper, key_modifier=key_modifier, direction=direction, repeat=repeat,
                           head=head)

    def new_modal(self, propvalue: str, type: str, value: str, any: bool = False, shift: int = 0, ctrl: int = 0,
                  alt: int = 0, oskey: int = 0, hyper: int = 0, key_modifier: str = "NONE", direction: str = "ANY",
                  repeat: bool = False):
        km = self._q_km
        if not km._p.get("is_modal", False):
            raise PropertyValueError(f"KeyMapItems.new_modal(): keymap '{km._p.get('name', '')}' is not modal")
        return self._q_add(idname="", type=type, value=value, any=any, shift=shift, ctrl=ctrl, alt=alt,
                           oskey=oskey, hyper=hyper, key_modifier=key_modifier, direction=direction, repeat=repeat,
                           head=False, propvalue=propvalue)

    def new_from_item(self, item, head: bool = False):
        pdefs = KeyMapItem.__dict__

        def raw(f):
            return pdefs[f].read_raw(item)
        new = self._q_add(idname=raw("idname"), type=raw("type"), value=raw("value"), any=raw("any"),
                          shift=raw("shift"), ctrl=raw("ctrl"), alt=raw("alt"), oskey=raw("oskey"),
                          hyper=raw("hyper"), key_modifier=raw("key_modifier"), direction=raw("direction"),
                          repeat=raw("repeat"), head=head, propvalue=item._q_propvalue)
        for f in ("map_type", "active", "show_expanded"):
            pdefs[f].write_raw(new, raw(f))
        return new

    def remove(self, item) -> None:
        km = self._q_km
        for i, cur in enumerate(km._q_items_list):
            if cur is item:
                del km._q_items_list[i]
                self._q_reindex()
                return
        raise PropertyValueError("KeyMapItems.remove(): item not in keymap")

    def from_id(self, id: int):
        for item in self._q_km._q_items_list:
            if item._p.get("id") == id:
                return item
        return None

    def find_from_operator(self, idname: str, properties=None, include: set = frozenset(),
                           exclude: set = frozenset()):
        for item in self._q_km._q_items_list:
            if item._p.get("idname", "") == idname:
                return item
        return None

    def find_match(self, *a, **k):
        raise NotImplementedInQuartz("KeyMapItems.find_match")

    def match_event(self, *a, **k):
        raise NotImplementedInQuartz("KeyMapItems.match_event")


@builtin_struct
class KeyMap(Struct):

    _q_strict_attrs = True

    name: StringProperty(maxlen=64, options=set(), meta=_RO)
    bl_owner_id: StringProperty(maxlen=128, options=set())
    space_type: EnumProperty(items=_items(_SPACE_TYPES), default="EMPTY", meta=_RO)
    region_type: EnumProperty(items=_items(_REGION_TYPES), default="WINDOW", meta=_RO)
    is_user_modified: BoolProperty()
    is_modal: BoolProperty(meta=_RO)
    show_expanded_items: BoolProperty()
    show_expanded_children: BoolProperty()

    @classmethod
    def _q_create(cls, owner, name: str, space_type: str, region_type: str, modal: bool) -> "KeyMap":
        km = cls._q_new_child(owner=owner, path=f'keymaps["{escape_identifier(name)}"]')
        pdefs = KeyMap.__dict__
        pdefs["name"].write_raw(km, name)
        pdefs["space_type"].write_raw(km, space_type)
        pdefs["region_type"].write_raw(km, region_type)
        pdefs["is_modal"].write_raw(km, bool(modal))
        object.__setattr__(km, "_q_items_list", [])
        object.__setattr__(km, "_q_next_id", 0)
        object.__setattr__(km, "_q_items_coll", KeyMapItems(km))
        return km

    @property
    def keymap_items(self) -> KeyMapItems:
        return self._q_items_coll

    def active(self):
        return self

    def restore_to_default(self) -> None:
        return None

    def restore_item_to_default(self, item) -> None:
        return None


class KeyMaps(PropCollection):

    def __init__(self, kc: "KeyConfig") -> None:
        super().__init__(owner=kc, path="keymaps")
        self._q_kc = kc

    def _q_items(self):
        return self._q_kc._q_keymaps

    def _q_key(self, item):
        return item._p.get("name", "")

    def new(self, name: str, space_type: str = "EMPTY", region_type: str = "WINDOW", modal: bool = False,
            tool: bool = False):
        if space_type not in _SPACE_TYPES:
            raise _enum_error('KeyMaps.new(): error with keyword argument "space_type"', space_type, _SPACE_TYPES)
        if region_type not in _REGION_TYPES:
            raise _enum_error('KeyMaps.new(): error with keyword argument "region_type"', region_type,
                              _REGION_TYPES)
        if not isinstance(name, str):
            raise PropertyTypeError(f"KeyMaps.new(): error with argument 1, \"name\" - expected a string type, "
                                    f"not {type(name).__name__}")
        found = self.find(name, space_type, region_type)
        if found is not None:
            return found
        km = KeyMap._q_create(self._q_kc, name, space_type, region_type, modal)
        self._q_kc._q_keymaps.append(km)
        return km

    def find(self, name: str, space_type: str = "EMPTY", region_type: str = "WINDOW"):
        for km in self._q_kc._q_keymaps:
            p = km._p
            if p.get("name") == name and p.get("space_type") == space_type and p.get("region_type") == region_type:
                return km
        return None

    def remove(self, keymap) -> None:
        maps = self._q_kc._q_keymaps
        for i, cur in enumerate(maps):
            if cur is keymap:
                del maps[i]
                return
        raise PropertyValueError("KeyMaps.remove(): keymap not in key configuration")


@builtin_struct
class KeyConfig(Struct):

    _q_strict_attrs = True

    name: StringProperty(maxlen=64, options=set())

    @classmethod
    def _q_create(cls, owner, name: str) -> "KeyConfig":
        kc = cls._q_new_child(owner=owner, path=f'keyconfigs["{escape_identifier(name)}"]')
        KeyConfig.__dict__["name"].write_raw(kc, name)
        object.__setattr__(kc, "_q_keymaps", [])
        object.__setattr__(kc, "_q_keymaps_coll", KeyMaps(kc))
        return kc

    @property
    def keymaps(self) -> KeyMaps:
        return self._q_keymaps_coll


class KeyConfigurations(PropCollection):

    def __init__(self, wm: "WindowManager") -> None:
        super().__init__(owner=wm, path="keyconfigs")
        self._q_wm = wm
        self._q_configs: list = []
        self._q_default = KeyConfig._q_create(wm, "Blender")
        self._q_addon = KeyConfig._q_create(wm, "Blender addon")
        self._q_user = KeyConfig._q_create(wm, "Blender user")
        self._q_active = self._q_default
        self._q_configs.extend([self._q_default, self._q_addon, self._q_user])

    def _q_items(self):
        return self._q_configs

    def _q_key(self, item):
        return item._p.get("name", "")

    @property
    def addon(self):
        return self._q_addon

    @property
    def user(self):
        return self._q_user

    @property
    def default(self):
        return self._q_default

    @property
    def active(self):
        return self._q_active

    def new(self, name: str):
        if not isinstance(name, str):
            raise PropertyTypeError(f"KeyConfigurations.new(): error with argument 1, \"name\" - expected a string "
                                    f"type, not {type(name).__name__}")
        kc = KeyConfig._q_create(self._q_wm, name)
        self._q_configs.append(kc)
        return kc

    def remove(self, keyconfig) -> None:
        if any(keyconfig is k for k in (self._q_default, self._q_addon, self._q_user)):
            raise PropertyValueError("KeyConfigurations.remove(): built-in key configurations can not be removed")
        for i, cur in enumerate(self._q_configs):
            if cur is keyconfig:
                del self._q_configs[i]
                if self._q_active is keyconfig:
                    self._q_active = self._q_default
                return
        raise PropertyValueError("KeyConfigurations.remove(): key configuration not found")

    def update(self, keep_properties: bool = False) -> None:
        return None

    def find_item_from_operator(self, idname: str, context: str = "INVOKE_DEFAULT", properties=None,
                                include: set = frozenset(), exclude: set = frozenset()):
        for km in self._q_active._q_keymaps:
            item = km.keymap_items.find_from_operator(idname)
            if item is not None:
                return km, item
        return None, None


class _OperatorHistory(PropCollection):

    def __init__(self, wm: "WindowManager") -> None:
        super().__init__(owner=wm, path="operators")
        self._q_wm = wm

    def _q_items(self):
        return self._q_wm._q_operators

    def _q_key(self, item):
        return getattr(item, "bl_idname", None)


@builtin_struct
class WindowManager(ID):

    _q_strict_attrs = True

    @classmethod
    def _q_construct(cls, name: str):
        inst = super()._q_construct(name)
        object.__setattr__(inst, "_q_windows", [Window._q_create(inst, 0)])
        object.__setattr__(inst, "_q_windows_coll", Windows(inst))
        object.__setattr__(inst, "_q_keyconfigs", KeyConfigurations(inst))
        object.__setattr__(inst, "_q_operators", [])
        object.__setattr__(inst, "_q_operators_coll", _OperatorHistory(inst))
        object.__setattr__(inst, "_q_clipboard", "")
        object.__setattr__(inst, "_q_timers", [])
        object.__setattr__(inst, "q_modal_handlers", [])
        object.__setattr__(inst, "q_fileselect_requests", [])
        object.__setattr__(inst, "q_ui_requests", [])
        object.__setattr__(inst, "q_progress", None)
        return inst

    @property
    def windows(self) -> Windows:
        return self._q_windows_coll

    @property
    def keyconfigs(self) -> KeyConfigurations:
        return self._q_keyconfigs

    @property
    def operators(self):
        return self._q_operators_coll

    @property
    def clipboard(self) -> str:
        return self._q_clipboard

    @clipboard.setter
    def clipboard(self, value: str) -> None:
        if not isinstance(value, str):
            raise PropertyTypeError(f"WindowManager.clipboard expected a string type, not {type(value).__name__}")
        self._q_clipboard = value

    def modal_handler_add(self, operator) -> bool:
        self.q_modal_handlers.append(operator)
        return True

    def fileselect_add(self, operator) -> None:
        self.q_fileselect_requests.append(operator)

    def event_timer_add(self, time_step: float, window=None):
        timer = Timer._q_new_child(owner=self, path="")
        Timer.__dict__["time_step"].write_raw(timer, float(time_step))
        self._q_timers.append(timer)
        return timer

    def event_timer_remove(self, timer) -> None:
        self._q_timers[:] = [t for t in self._q_timers if t is not timer]

    def progress_begin(self, min: float, max: float) -> None:
        self.q_progress = (float(min), float(max), float(min))

    def progress_update(self, value: float) -> None:
        cur = self.q_progress
        if cur is None:
            self.q_progress = (0.0, 0.0, float(value))
        else:
            self.q_progress = (cur[0], cur[1], float(value))

    def progress_end(self) -> None:
        self.q_progress = None

    def invoke_props_dialog(self, operator, width: int = 300, title: str = "", confirm_text: str = "",
                            cancel_default: bool = False, text_ctxt: str = "", translate: bool = True) -> set:
        self.q_ui_requests.append(("invoke_props_dialog", operator, {
            "width": width, "title": title, "confirm_text": confirm_text, "cancel_default": cancel_default,
            "text_ctxt": text_ctxt, "translate": translate}))
        return {"RUNNING_MODAL"}

    def invoke_props_popup(self, operator, event) -> set:
        self.q_ui_requests.append(("invoke_props_popup", operator, {"event": event}))
        return {"RUNNING_MODAL"}

    def invoke_popup(self, operator, width: int = 300, *, auto_keymap: bool = True) -> set:
        self.q_ui_requests.append(("invoke_popup", operator, {"width": width, "auto_keymap": auto_keymap}))
        return {"RUNNING_MODAL"}

    def invoke_confirm(self, operator, event, title: str = "", message: str = "", confirm_text: str = "",
                       icon: str = "NONE", text_ctxt: str = "", translate: bool = True) -> set:
        self.q_ui_requests.append(("invoke_confirm", operator, {
            "event": event, "title": title, "message": message, "confirm_text": confirm_text, "icon": icon,
            "text_ctxt": text_ctxt, "translate": translate}))
        return {"RUNNING_MODAL"}

    def invoke_search_popup(self, operator) -> None:
        self.q_ui_requests.append(("invoke_search_popup", operator, {}))

    def popup_menu(self, draw_func, title: str = "", icon: str = "NONE") -> None:
        self.q_ui_requests.append(("popup_menu", draw_func, {"title": title, "icon": icon}))

    def popover(self, draw_func, *a, **k) -> None:
        self.q_ui_requests.append(("popover", draw_func, {"args": a, **k}))

    def popup_menu_pie(self, event, draw_func, title: str = "", icon: str = "NONE") -> None:
        self.q_ui_requests.append(("popup_menu_pie", draw_func, {"event": event, "title": title, "icon": icon}))

    def operator_properties_last(self, operator: str):
        return None

    def q_push_operator(self, op) -> None:
        ops = self._q_operators
        ops.append(op)
        if len(ops) > _MAX_OPERATORS:
            del ops[:len(ops) - _MAX_OPERATORS]

    def q_new_window(self, scene=None) -> Window:
        win = Window._q_create(self, len(self._q_windows), scene)
        self._q_windows.append(win)
        return win

    def _q_trim_windows(self, keep: int = 1) -> None:
        if keep < 1:
            raise ValueError("WindowManager._q_trim_windows(): keep must be >= 1")
        del self._q_windows[keep:]

    def _q_refs(self):
        yield from super()._q_refs()
        for win in list(self._q_windows):
            scene = win._p.get("scene")
            if scene is not None:
                yield IDRef(scene, win, "WINDOW_SCENE", True, "CLEAR", *_window_closures(self, win, scene))

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        windows = []
        for win in self._q_windows:
            vl = win._q_view_layer
            windows.append({"scene": win._p.get("scene"), "view_layer": vl._q_name if vl is not None else None,
                            "screen": win._p.get("screen"), "workspace": win._p.get("workspace"),
                            "p": Struct._q_state_get(win)})
        state["windows"] = windows
        state["clipboard"] = self._q_clipboard
        return state

    def _q_state_set(self, state: dict) -> None:
        super()._q_state_set(state)
        if "windows" in state:
            old = list(self._q_windows)
            wins = []
            for i, ws in enumerate(state["windows"]):
                win = old[i] if i < len(old) else Window._q_create(self, i)
                Struct._q_state_set(win, ws.get("p", {}))
                pdefs = Window.__dict__
                pdefs["scene"].write_raw(win, ws.get("scene"))
                pdefs["screen"].write_raw(win, ws.get("screen"))
                pdefs["workspace"].write_raw(win, ws.get("workspace"))
                scene = ws.get("scene")
                vl_name = ws.get("view_layer")
                win._q_view_layer = None
                if scene is not None and vl_name is not None:
                    win._q_view_layer = scene.view_layers.get(vl_name)
                win._q_set_owner(self, f"windows[{i}]")
                wins.append(win)
            self._q_windows[:] = wins
        if "clipboard" in state:
            self._q_clipboard = str(state["clipboard"])


def _window_closures(wm: WindowManager, win: Window, scene):
    def clear():
        other = None
        main = wm._q_main
        if main is not None:
            for s in main.scenes:
                if s is not scene:
                    other = s
                    break
        win.scene = other

    def remap(new):
        win.scene = new
    return clear, remap


def _not_implemented_wm(name: str):
    def method(self, *a, **k):
        raise NotImplementedInQuartz(f"WindowManager.{name}")
    method.__name__ = name
    return method


for _name in _NOT_IMPLEMENTED_WM:
    type.__setattr__(WindowManager, _name, _not_implemented_wm(_name))
del _name


class BlendDataWindowManagers(IDCollection):

    new = _NoAttribute()
    remove = _NoAttribute()


class BlendDataScreens(IDCollection):

    new = _NoAttribute()
    remove = _NoAttribute()


class BlendDataWorkSpaces(IDCollection):

    new = _NoAttribute()
    remove = _NoAttribute()


register_id_type(WindowManager, id_type="WINDOWMANAGER", collection="window_managers", default_name="WinMan",
                 collection_cls=BlendDataWindowManagers)
register_id_type(Screen, id_type="SCREEN", collection="screens", default_name="Screen",
                 collection_cls=BlendDataScreens)
register_id_type(WorkSpace, id_type="WORKSPACE", collection="workspaces", default_name="WorkSpace",
                 collection_cls=BlendDataWorkSpaces)
