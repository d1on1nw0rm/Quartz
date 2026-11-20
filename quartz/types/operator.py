from __future__ import annotations

import weakref
from typing import Callable, Iterable, Mapping

from quartz import registry
from quartz.errors import PropertyTypeError, PropertyValueError, ReadOnlyError, RegistrationRuntimeError
from quartz.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from quartz.rna.annotations import get_property
from quartz.rna.collections import PropCollection
from quartz.rna.properties import COERCE_PREFIX, PropertyDef
from quartz.rna.struct import PropertyGroup, Struct, builtin_struct

__all__ = [
    "OPERATOR_RETURN_FLAGS", "OPERATOR_OPTIONS", "REPORT_TYPES", "EVENT_TYPES", "EVENT_VALUES",
    "Operator", "OperatorProperties", "OperatorOptions", "OperatorFileListElement", "Event",
]

OPERATOR_RETURN_FLAGS: tuple[str, ...] = ("RUNNING_MODAL", "CANCELLED", "FINISHED", "PASS_THROUGH", "INTERFACE")
OPERATOR_OPTIONS: tuple[str, ...] = (
    "REGISTER", "UNDO", "UNDO_GROUPED", "BLOCKING", "MACRO", "GRAB_CURSOR", "GRAB_CURSOR_X", "GRAB_CURSOR_Y",
    "DEPENDS_ON_CURSOR", "PRESET", "INTERNAL", "MODAL_PRIORITY"
)
REPORT_TYPES: tuple[str, ...] = (
    "DEBUG", "INFO", "OPERATOR", "PROPERTY", "WARNING", "ERROR", "ERROR_INVALID_INPUT", "ERROR_INVALID_CONTEXT",
    "ERROR_OUT_OF_MEMORY"
)
EVENT_TYPES: tuple[str, ...] = (
    "NONE", "LEFTMOUSE", "MIDDLEMOUSE", "RIGHTMOUSE", "BUTTON4MOUSE", "BUTTON5MOUSE", "BUTTON6MOUSE",
    "BUTTON7MOUSE", "PEN", "ERASER", "MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "TRACKPADPAN", "TRACKPADZOOM",
    "MOUSEROTATE", "MOUSESMARTZOOM", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
    "WHEELLEFTMOUSE", "WHEELRIGHTMOUSE", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N",
    "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE",
    "SIX", "SEVEN", "EIGHT", "NINE", "LEFT_CTRL", "LEFT_ALT", "LEFT_SHIFT", "RIGHT_ALT", "RIGHT_CTRL",
    "RIGHT_SHIFT", "OSKEY", "HYPER", "APP", "GRLESS", "ESC", "TAB", "RET", "SPACE", "LINE_FEED", "BACK_SPACE",
    "DEL", "SEMI_COLON", "PERIOD", "COMMA", "QUOTE", "ACCENT_GRAVE", "MINUS", "PLUS", "SLASH", "BACK_SLASH",
    "EQUAL", "LEFT_BRACKET", "RIGHT_BRACKET", "LEFT_ARROW", "DOWN_ARROW", "RIGHT_ARROW", "UP_ARROW", "NUMPAD_2",
    "NUMPAD_4", "NUMPAD_6", "NUMPAD_8", "NUMPAD_1", "NUMPAD_3", "NUMPAD_5", "NUMPAD_7", "NUMPAD_9",
    "NUMPAD_PERIOD", "NUMPAD_SLASH", "NUMPAD_ASTERIX", "NUMPAD_0", "NUMPAD_MINUS", "NUMPAD_ENTER",
    "NUMPAD_PLUS", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F13", "F14",
    "F15", "F16", "F17", "F18", "F19", "F20", "F21", "F22", "F23", "F24", "PAUSE", "INSERT", "HOME", "PAGE_UP",
    "PAGE_DOWN", "END", "MEDIA_PLAY", "MEDIA_STOP", "MEDIA_FIRST", "MEDIA_LAST", "TEXTINPUT",
    "WINDOW_DEACTIVATE", "TIMER", "TIMER0", "TIMER1", "TIMER2", "TIMER_JOBS", "TIMER_AUTOSAVE", "TIMER_REPORT",
    "TIMERREGION", "NDOF_MOTION", "NDOF_BUTTON_MENU", "NDOF_BUTTON_FIT", "NDOF_BUTTON_TOP",
    "NDOF_BUTTON_BOTTOM", "NDOF_BUTTON_LEFT", "NDOF_BUTTON_RIGHT", "NDOF_BUTTON_FRONT", "NDOF_BUTTON_BACK",
    "NDOF_BUTTON_ISO1", "NDOF_BUTTON_ISO2", "NDOF_BUTTON_ROLL_CW", "NDOF_BUTTON_ROLL_CCW",
    "NDOF_BUTTON_SPIN_CW", "NDOF_BUTTON_SPIN_CCW", "NDOF_BUTTON_TILT_CW", "NDOF_BUTTON_TILT_CCW",
    "NDOF_BUTTON_ROTATE", "NDOF_BUTTON_PANZOOM", "NDOF_BUTTON_DOMINANT", "NDOF_BUTTON_PLUS",
    "NDOF_BUTTON_MINUS", "NDOF_BUTTON_V1", "NDOF_BUTTON_V2", "NDOF_BUTTON_V3", "NDOF_BUTTON_SAVE_V1",
    "NDOF_BUTTON_SAVE_V2", "NDOF_BUTTON_SAVE_V3", "NDOF_BUTTON_1", "NDOF_BUTTON_2", "NDOF_BUTTON_3",
    "NDOF_BUTTON_4", "NDOF_BUTTON_5", "NDOF_BUTTON_6", "NDOF_BUTTON_7", "NDOF_BUTTON_8", "NDOF_BUTTON_9",
    "NDOF_BUTTON_10", "NDOF_BUTTON_11", "NDOF_BUTTON_12", "ACTIONZONE_AREA", "ACTIONZONE_REGION",
    "ACTIONZONE_REGION_QUAD", "ACTIONZONE_FULLSCREEN", "XR_ACTION"
)
EVENT_VALUES: tuple[str, ...] = ("ANY", "PRESS", "RELEASE", "CLICK", "DOUBLE_CLICK", "CLICK_DRAG", "NOTHING")
_EVENT_DIRECTIONS: tuple[str, ...] = (
    "ANY", "NORTH", "NORTH_EAST", "EAST", "SOUTH_EAST", "SOUTH", "SOUTH_WEST", "WEST", "NORTH_WEST"
)

_ASSIGN_PREFIX = "Converting py args to operator properties: "
_POLL_MESSAGES: "weakref.WeakKeyDictionary[type, tuple[object, tuple]]" = weakref.WeakKeyDictionary()


def _enum_items(ids: Iterable[str]) -> list[tuple[str, str, str]]:
    return [(i, i.replace("_", " ").title(), "") for i in ids]


class _EmptyCollection(PropCollection):

    def _q_items(self):
        return ()


@builtin_struct
class OperatorProperties(Struct):
    pass


@builtin_struct
class OperatorOptions(Struct):
    _q_strict_attrs = True
    is_invoke: BoolProperty(name="Invoke", meta={"readonly": True})
    is_repeat: BoolProperty(name="Repeat", meta={"readonly": True})
    is_repeat_last: BoolProperty(name="Repeat Call", meta={"readonly": True})
    use_cursor_region: BoolProperty(name="Focus Region", meta={"readonly": True})
    is_grab_cursor: BoolProperty(name="Grab Cursor", meta={"readonly": True})


@builtin_struct
class OperatorFileListElement(PropertyGroup):
    _q_strict_attrs = True


def _type_name(value: object) -> str:
    return type(value).__name__


def _op_label(self) -> str:
    label = getattr(type(self), "bl_label", "")
    return label if isinstance(label, str) else str(label)


def _props_class(cls: type) -> type:
    pcls = cls.__dict__.get("_q_props_class")
    if pcls is None:
        raise RegistrationRuntimeError(f"{cls.__name__} is not registered")
    return pcls


def _shared_properties(op: Struct) -> Struct:
    inst = op.__dict__.get("_q_props_inst")
    if inst is None:
        pcls = _props_class(type(op))
        inst = pcls.__new__(pcls)
        object.__setattr__(inst, "_p", op._p)
        object.__setattr__(inst, "_p_set", op._p_set)
        object.__setattr__(op, "_q_props_inst", inst)
    return inst


def _operator_prepare(cls: type, rna_name: str) -> None:
    ids = list(cls.__dict__.get("_q_installed", ()))
    annotations = {i: get_property(cls, i).deferred for i in ids}
    pcls = type(OperatorProperties)(rna_name, (OperatorProperties,), {
        "__module__": cls.__module__,
        "__qualname__": rna_name,
        "_q_strict_attrs": True,
        "__annotations__": annotations,
    })
    builtin_struct(pcls, identifier=rna_name)
    type.__setattr__(cls, "_q_props_class", pcls)


def _operator_cleanup(cls: type) -> None:
    pcls = cls.__dict__.get("_q_props_class")
    if pcls is not None:
        type.__delattr__(cls, "_q_props_class")
        if "bl_rna" in pcls.__dict__:
            type.__delattr__(pcls, "bl_rna")
    _POLL_MESSAGES.pop(cls, None)


def _assign(op: Struct, kwargs: Mapping[str, object]) -> None:
    pcls = _props_class(type(op))
    props = _shared_properties(op)
    for key, value in kwargs.items():
        if not isinstance(get_property(pcls, key), PropertyDef):
            raise PropertyTypeError(f'Converting py args to operator properties:: keyword "{key}" unrecognized')
        try:
            setattr(props, key, value)
        except (PropertyTypeError, PropertyValueError, ReadOnlyError) as exc:
            msg = str(exc)
            if msg.startswith(COERCE_PREFIX):
                msg = msg[len(COERCE_PREFIX):]
            raise type(exc)(_ASSIGN_PREFIX + msg) from exc


@builtin_struct
class Operator(Struct):
    _q_registrable = True
    _q_class_enums = {"bl_options": ("SET", OPERATOR_OPTIONS)}

    name: StringProperty(name="Name", options=set(), meta={"virtual_get": _op_label})
    has_reports: BoolProperty(name="Has Reports", meta={"virtual_get": lambda self: bool(self._q_reports)})

    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls)
        object.__setattr__(inst, "_q_reports", [])
        object.__setattr__(inst, "_q_layout", None)
        object.__setattr__(inst, "_q_props_inst", None)
        return inst

    @property
    def properties(self) -> OperatorProperties:
        return _shared_properties(self)

    @property
    def layout(self):
        return getattr(self, "_q_layout", None)

    @property
    def options(self) -> OperatorOptions:
        opts = self.__dict__.get("_q_options")
        if opts is None:
            opts = OperatorOptions._q_new_child(owner=self, path="options")
            object.__setattr__(self, "_q_options", opts)
        return opts

    @property
    def macros(self) -> PropCollection:
        coll = self.__dict__.get("_q_macros")
        if coll is None:
            coll = _EmptyCollection(owner=self, path="macros")
            object.__setattr__(self, "_q_macros", coll)
        return coll

    @classmethod
    def poll_message_set(cls, message: str | Callable[..., str], *args: object) -> None:
        _POLL_MESSAGES[cls] = (message, tuple(args))

    def report(self, type: set[str], message: str) -> None:
        if not isinstance(type, (set, frozenset)):
            raise PropertyTypeError(
                f'Operator.report(): error with keyword argument "type" - expected a set, not {_type_name(type)}')
        if not type:
            raise PropertyTypeError('Operator.report(): error with keyword argument "type" - '
                                    "expected a set with at least one item")
        listing = ", ".join(repr(i) for i in REPORT_TYPES)
        for item in sorted(type, key=str):
            if item not in REPORT_TYPES:
                raise PropertyTypeError(f'Operator.report(): enum "{item}" not found in ({listing})')
        if not isinstance(message, str):
            raise PropertyTypeError(
                f"Operator.report(): message expected a string type, not {_type_name(message)}")
        self._q_reports.append((frozenset(type), message))

    def is_repeat(self) -> bool:
        return False

    def as_keywords(self, *, ignore: Iterable[str] = ()) -> dict[str, object]:
        skip = set(ignore)
        pcls = _props_class(type(self))
        return {k: getattr(self, k) for k in pcls.__dict__.get("_q_installed", ()) if k not in skip}

    @classmethod
    def q_properties_class(cls) -> type:
        return _props_class(cls)

    @classmethod
    def q_new_properties(cls) -> OperatorProperties:
        return _props_class(cls)()

    def _q_assign(self, kwargs: Mapping[str, object]) -> None:
        _assign(self, kwargs)

    @classmethod
    def _q_take_poll_message(cls) -> str | None:
        record = _POLL_MESSAGES.pop(cls, None)
        if record is None:
            return None
        message, args = record
        if callable(message):
            return str(message(*args))
        return message


def _ro(**kw) -> dict:
    return {"meta": {"readonly": True}, **kw}


@builtin_struct
class Event(Struct):
    _q_strict_attrs = True

    ascii: StringProperty(name="ASCII", options=set(), **_ro())
    unicode: StringProperty(name="Unicode", options=set(), **_ro())
    value: EnumProperty(items=_enum_items(EVENT_VALUES), name="Value", default="NOTHING", **_ro())
    value_prev: EnumProperty(items=_enum_items(EVENT_VALUES), name="Previous Value", default="NOTHING", **_ro())
    type: EnumProperty(items=_enum_items(EVENT_TYPES), name="Type", default="NONE", **_ro())
    type_prev: EnumProperty(items=_enum_items(EVENT_TYPES), name="Previous Type", default="NONE", **_ro())
    direction: EnumProperty(items=_enum_items(_EVENT_DIRECTIONS), name="Direction", default="ANY", **_ro())
    is_repeat: BoolProperty(name="Is Repeat", **_ro())
    is_consecutive: BoolProperty(name="Is Consecutive", **_ro())
    mouse_x: IntProperty(name="Mouse X Position", soft_min=-10000, soft_max=10000, **_ro())
    mouse_y: IntProperty(name="Mouse Y Position", soft_min=-10000, soft_max=10000, **_ro())
    mouse_region_x: IntProperty(name="Mouse X Position", soft_min=-10000, soft_max=10000, **_ro())
    mouse_region_y: IntProperty(name="Mouse Y Position", soft_min=-10000, soft_max=10000, **_ro())
    mouse_prev_x: IntProperty(name="Mouse Previous X Position", soft_min=-10000, soft_max=10000, **_ro())
    mouse_prev_y: IntProperty(name="Mouse Previous Y Position", soft_min=-10000, soft_max=10000, **_ro())
    mouse_prev_press_x: IntProperty(name="Mouse Previous X Press Position", soft_min=-10000, soft_max=10000, **_ro())
    mouse_prev_press_y: IntProperty(name="Mouse Previous Y Press Position", soft_min=-10000, soft_max=10000, **_ro())
    pressure: FloatProperty(name="Tablet Pressure", subtype="FACTOR", default=1.0, min=0.0, max=1.0, step=10,
                            precision=3, **_ro())
    tilt: FloatVectorProperty(name="Tablet Tilt", subtype="XYZ_LENGTH", unit="LENGTH", size=2, soft_min=-10000.0,
                              soft_max=10000.0, step=10, precision=3, **_ro())
    is_tablet: BoolProperty(name="Is Tablet", **_ro())
    is_mouse_absolute: BoolProperty(name="Absolute Motion", **_ro())
    shift: BoolProperty(name="Shift", **_ro())
    ctrl: BoolProperty(name="Ctrl", **_ro())
    alt: BoolProperty(name="Alt", **_ro())
    oskey: BoolProperty(name="OS Key", **_ro())
    hyper: BoolProperty(name="Hyper", **_ro())

    @property
    def ndof_motion(self) -> None:
        return None

    @property
    def xr(self) -> None:
        return None

    @classmethod
    def q_synthetic(cls, type: str = "NONE", value: str = "NOTHING", **fields: object) -> "Event":
        ev = cls()
        items = [("type", type), ("value", value)] + list(fields.items())
        for key, val in items:
            pdef = get_property(cls, key)
            if not isinstance(pdef, PropertyDef):
                raise PropertyTypeError(f"Event has no field '{key}'")
            pdef.write_raw(ev, pdef.coerce(val, ev))
            ev._p_set.discard(key)
        return ev


registry.register_base(
    Operator, kind="OPERATOR", required=("bl_label",),
    callbacks={
        "poll": (True, True),
        "execute": (True, False),
        "check": (True, False),
        "invoke": (True, False),
        "modal": (True, False),
        "draw": (True, False),
        "cancel": (True, False),
        "description": (True, True),
    },
    prepare=_operator_prepare, cleanup=_operator_cleanup,
)
