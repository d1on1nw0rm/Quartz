from __future__ import annotations

import copy
import logging
import re
import sys
import types
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

LOG = logging.getLogger("quartz_studio.controls")

FORMAT = "quartz-controls"
VERSION = 1
CLASSIC_NAME = "Classic"
STANDARD_NAME = "Standard"
BUILTIN_IDS = ("standard", "classic")
USER_ID_RE = re.compile(r"^u-[0-9a-f]{8}$")

SCOPES = ("global", "viewport", "objects")
BUTTONS = ("left", "middle", "right")
MODS = ("shift", "ctrl", "alt")
OPS = ("orbit", "pan", "dolly", "select", "add", "remove", "context")
NAV_OPS = ("orbit", "pan", "dolly")
MODIFIER_ROLES = ("snap", "extrude", "create_child", "create_adopt")
MODAL_ROLES = ("cancel", "confirm")
MOD_NAMES = {"shift": "Shift", "ctrl": "Ctrl", "alt": "Alt"}

CURSOR_SPEC: dict[str, tuple] = {
    "orbit_pivot": ("enum", ("Cursor", "Center", "Object", "Camera")),
    "orbit_style": ("enum", ("turntable", "free")),
    "orbit_speed": ("float", 0.05, 2.0),
    "invert_orbit_x": ("bool",),
    "invert_orbit_y": ("bool",),
    "invert_pan": ("bool",),
    "dolly_speed": ("float", 0.001, 0.05),
    "zoom_to_cursor": ("bool",),
    "wheel_step": ("float", 0.5, 0.98),
    "wheel_invert": ("bool",),
    "drag_threshold": ("int", 1, 16),
    "click_tolerance": ("int", 1, 16),
    "hold_ms": ("int", 150, 1000),
    "chord_ms": ("int", 500, 3000),
}

_MODIFIER_KEYS = {Qt.Key.Key_unknown, Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                  Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock}
_PORTABLE = QKeySequence.SequenceFormat.PortableText
_MOD_MASK = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
             | Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ShiftModifier
             | Qt.KeyboardModifier.KeypadModifier)

CLASSIC: dict = {
    "format": FORMAT,
    "version": VERSION,
    "id": "classic",
    "name": CLASSIC_NAME,
    "base": None,
    "keys": {
        "file.new": ["Ctrl+N"],
        "file.open": ["Ctrl+O"],
        "file.merge": ["Ctrl+Shift+O"],
        "file.save": ["Ctrl+S"],
        "file.save_as": ["Ctrl+Shift+S"],
        "file.save_incremental": ["Ctrl+Alt+S"],
        "file.exit": ["Alt+F4"],
        "edit.undo": ["Ctrl+Z"],
        "edit.redo": ["Ctrl+Y"],
        "app.controls": ["Shift+F12"],
        "object.make_editable": ["C"],
        "tool.pen": ["M~E"],
        "tool.select_all": ["Ctrl+A"],
        "tool.grow_selection": ["U~G"],
        "tool.shrink_selection": ["U~K"],
        "tool.move": ["E"],
        "tool.rotate": ["R"],
        "tool.scale": ["T"],
        "view.frame_all": ["H"],
        "view.frame_selection": ["S"],
        "view.frame_objects": ["O"],
        "view.frame_default": ["Shift+H"],
        "view.undo": ["Ctrl+Shift+Z"],
        "view.redo": ["Ctrl+Shift+Y"],
        "camera.perspective": ["F1"],
        "camera.top": ["F2"],
        "camera.right": ["F3"],
        "camera.front": ["F4"],
        "display.shaded": ["N~A"],
        "display.shaded_lines": ["N~B"],
        "display.wireframe": ["N~H"],
        "display.isoparms": ["N~I"],
        "display.hidden_line": ["N~F"],
        "object.rename": ["F2"],
        "object.delete": ["Delete", "Backspace"],
    },
    "mouse": [
        {"button": "left", "mods": ["alt"], "op": "orbit"},
        {"button": "middle", "mods": ["alt"], "op": "pan"},
        {"button": "right", "mods": ["alt"], "op": "dolly"},
        {"button": "left", "key": "3", "op": "orbit"},
        {"button": "left", "key": "2", "op": "dolly"},
        {"button": "left", "key": "1", "op": "pan"},
        {"button": "middle", "op": "orbit"},
        {"button": "left", "mods": ["ctrl"], "op": "remove"},
        {"button": "left", "mods": ["shift"], "op": "add"},
        {"button": "left", "op": "select"},
        {"button": "right", "op": "context"},
        {"button": "right", "mods": ["ctrl"], "op": "remove"},
        {"button": "right", "mods": ["shift"], "op": "add"},
        {"button": "middle", "double": True, "action": "view.frame_default"},
        {"button": "middle", "double": True, "mods": ["shift"], "action": "view.frame_default"},
        {"button": "middle", "double": True, "mods": ["ctrl"], "action": "view.frame_default"},
        {"button": "middle", "double": True, "mods": ["shift", "ctrl"], "action": "view.frame_default"},
    ],
    "cursor": {
        "orbit_pivot": "Cursor",
        "orbit_style": "turntable",
        "orbit_speed": 0.3,
        "invert_orbit_x": False,
        "invert_orbit_y": False,
        "invert_pan": False,
        "dolly_speed": 0.005,
        "zoom_to_cursor": True,
        "wheel_step": 0.88,
        "wheel_invert": False,
        "drag_threshold": 3,
        "click_tolerance": 4,
        "hold_ms": 380,
        "chord_ms": 1500,
    },
    "modifiers": {"snap": "shift", "extrude": "ctrl", "create_child": "shift", "create_adopt": "alt"},
    "modal": {"cancel": ["Escape"], "confirm": ["Return", "Enter"]},
}

STANDARD: dict = {
    "format": FORMAT,
    "version": VERSION,
    "id": "standard",
    "name": STANDARD_NAME,
    "base": None,
    "keys": {
        "file.new": ["Ctrl+N"],
        "file.open": ["Ctrl+O"],
        "file.merge": ["Ctrl+Shift+O"],
        "file.save": ["Ctrl+S"],
        "file.save_as": ["Ctrl+Shift+S"],
        "file.save_incremental": ["Ctrl+Alt+S"],
        "file.import": ["Ctrl+Shift+I"],
        "file.exit": ["Ctrl+Q"],
        "edit.undo": ["Ctrl+Z"],
        "edit.redo": ["Ctrl+Shift+Z", "Ctrl+Y"],
        "app.controls": ["Ctrl+,"],
        "object.make_editable": ["Alt+C"],
        "mode.points": ["1"],
        "mode.edges": ["2"],
        "mode.polygons": ["3"],
        "mode.model": ["4"],
        "tool.select_all": ["Ctrl+A"],
        "tool.deselect_all": ["Ctrl+Shift+A"],
        "tool.invert_selection": ["Ctrl+I"],
        "tool.grow_selection": ["Ctrl+Num++"],
        "tool.shrink_selection": ["Ctrl+Num+-"],
        "tool.extrude": ["Ctrl+E"],
        "tool.bevel": ["Ctrl+B"],
        "tool.inset": ["I"],
        "tool.line_cut": ["K"],
        "tool.loop_path_cut": ["Ctrl+R"],
        "tool.weld": ["M"],
        "tool.pen": ["P"],
        "tool.line_pen": ["Shift+P"],
        "tool.select": ["Q"],
        "tool.move": ["W"],
        "tool.rotate": ["E"],
        "tool.scale": ["R"],
        "view.frame_selection": ["F"],
        "view.frame_all": ["A"],
        "view.frame_objects": ["Shift+F"],
        "view.frame_default": ["Home"],
        "camera.front": ["Num+1"],
        "camera.back": ["Ctrl+Num+1"],
        "camera.right": ["Num+3"],
        "camera.left": ["Ctrl+Num+3"],
        "camera.top": ["Num+7"],
        "camera.bottom": ["Ctrl+Num+7"],
        "camera.perspective": ["Num+5"],
        "camera.parallel": ["Ctrl+Num+5"],
        "edit.delete": ["Delete", "Backspace"],
        "object.rename": ["F2"],
        "object.delete": ["Delete", "Backspace"],
    },
    "mouse": [
        {"button": "left", "mods": ["alt"], "op": "orbit"},
        {"button": "middle", "mods": ["alt"], "op": "pan"},
        {"button": "right", "mods": ["alt"], "op": "dolly"},
        {"button": "middle", "mods": ["shift"], "op": "pan"},
        {"button": "middle", "mods": ["ctrl"], "op": "dolly"},
        {"button": "middle", "op": "orbit"},
        {"button": "left", "mods": ["ctrl"], "op": "remove"},
        {"button": "left", "mods": ["shift"], "op": "add"},
        {"button": "left", "op": "select"},
        {"button": "right", "op": "context"},
        {"button": "right", "mods": ["ctrl"], "op": "remove"},
        {"button": "right", "mods": ["shift"], "op": "add"},
        {"button": "left", "double": True, "action": "tool.loop_selection"},
    ],
    "cursor": {
        "orbit_pivot": "Center",
        "orbit_style": "turntable",
        "orbit_speed": 0.3,
        "invert_orbit_x": False,
        "invert_orbit_y": False,
        "invert_pan": False,
        "dolly_speed": 0.005,
        "zoom_to_cursor": True,
        "wheel_step": 0.88,
        "wheel_invert": False,
        "drag_threshold": 4,
        "click_tolerance": 4,
        "hold_ms": 380,
        "chord_ms": 1500,
    },
    "modifiers": {"snap": "shift", "extrude": "ctrl", "create_child": "shift", "create_adopt": "alt"},
    "modal": {"cancel": ["Escape"], "confirm": ["Return", "Enter"]},
}

BUILTINS: dict[str, dict] = {"standard": STANDARD, "classic": CLASSIC}

DEFAULT_SCOPES: dict[str, str] = {
    "edit.delete": "viewport",
    "tool.select": "viewport",
    "tool.move": "viewport",
    "tool.rotate": "viewport",
    "tool.scale": "viewport",
    "object.rename": "objects",
    "object.delete": "objects",
}


@dataclass(frozen=True)
class Resolved:
    id: str
    name: str
    builtin: bool
    base: str | None
    keys: dict[str, tuple[tuple[str, str], ...]]
    mouse: tuple[dict, ...]
    cursor: dict
    modifiers: dict
    modal: dict
    overridden: frozenset[str]


def _sequence(text):
    if not isinstance(text, str) or not text.strip():
        return None
    seq = QKeySequence(text.strip())
    if seq.count() != 1:
        return None
    combo = seq[0]
    if combo.key() in _MODIFIER_KEYS:
        return None
    if not seq.toString(_PORTABLE):
        return None
    return seq


def portable(text) -> str | None:
    seq = _sequence(text)
    return None if seq is None else seq.toString(_PORTABLE)


def _plain_part(text) -> str | None:
    seq = _sequence(text)
    if seq is None:
        return None
    mods = seq[0].keyboardModifiers()
    if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
               | Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ShiftModifier
               | Qt.KeyboardModifier.KeypadModifier):
        return None
    return seq.toString(_PORTABLE).upper()


def parse_chord(text) -> tuple[str, str] | None:
    if not isinstance(text, str):
        return None
    text = text.strip()
    if len(text) < 3 or "~" not in text[1:-1]:
        return None
    k = text.index("~", 1)
    first, second = text[:k].strip(), text[k + 1:].strip()
    a, b = _plain_part(first), _plain_part(second)
    if a is None or b is None:
        return None
    return a, b


def is_chord(text) -> bool:
    return parse_chord(text) is not None


def normalize(text) -> str | None:
    chord = parse_chord(text)
    if chord is not None:
        return chord[0] + "~" + chord[1]
    if isinstance(text, str) and "~" in text.strip()[1:-1]:
        return None
    return portable(text)


def is_valid(text) -> bool:
    return normalize(text) is not None


def is_plain_key(text) -> bool:
    return parse_chord(text) is None and _plain_part(text) is not None


def key_code(text) -> int | None:
    seq = _sequence(text)
    if seq is None:
        return None
    return int(seq[0].key().value)


def binding_parts(binding) -> tuple[str, str | None] | None:
    if isinstance(binding, str):
        return binding, None
    if isinstance(binding, dict) and isinstance(binding.get("key"), str):
        scope = binding.get("scope")
        if scope is not None and scope not in SCOPES:
            return None
        return binding["key"], scope
    return None


def _check_binding(binding):
    parts = binding_parts(binding)
    if parts is None or not is_valid(parts[0]):
        raise ValueError(f"Invalid key binding: {binding!r}")
    if parts[1] is None:
        return parts[0]
    return {"key": parts[0], "scope": parts[1]}


def check_bindings(bindings) -> list:
    if isinstance(bindings, (str, dict)):
        bindings = [bindings]
    if bindings is None:
        bindings = []
    if not isinstance(bindings, (list, tuple)):
        raise ValueError(f"Key bindings must be a list: {bindings!r}")
    return [_check_binding(b) for b in bindings]


def _clean_bindings(action_id: str, bindings, where: str) -> list | None:
    if isinstance(bindings, (str, dict)):
        bindings = [bindings]
    if not isinstance(bindings, (list, tuple)):
        LOG.warning("controls: %s: bindings of %s are not a list; dropped", where, action_id)
        return None
    out = []
    for b in bindings:
        try:
            out.append(_check_binding(b))
        except ValueError:
            LOG.warning("controls: %s: invalid binding %r of %s dropped", where, b, action_id)
    return out


def check_gesture(gesture) -> dict:
    if not isinstance(gesture, dict):
        raise ValueError(f"Invalid mouse gesture: {gesture!r}")
    button = gesture.get("button")
    if button not in BUTTONS:
        raise ValueError(f"Invalid mouse button: {button!r}")
    mods = gesture.get("mods") or []
    if not isinstance(mods, (list, tuple, set, frozenset)) or any(m not in MODS for m in mods):
        raise ValueError(f"Invalid gesture modifiers: {mods!r}")
    key = gesture.get("key")
    if key is not None and not is_plain_key(key):
        raise ValueError(f"Invalid held key: {key!r}")
    double = gesture.get("double", False)
    if not isinstance(double, bool):
        raise ValueError(f"Invalid double flag: {double!r}")
    op = gesture.get("op")
    action = gesture.get("action")
    if (op is None) == (action is None):
        raise ValueError("A gesture has exactly one of op and action.")
    if op is not None and op not in OPS:
        raise ValueError(f"Invalid gesture operation: {op!r}")
    if action is not None and (not isinstance(action, str) or not double):
        raise ValueError("A gesture action needs a double click and an action id.")
    out = {"button": button, "mods": [m for m in MODS if m in set(mods)], "key": key, "double": double}
    if op is not None:
        out["op"] = op
    else:
        out["action"] = action
    return out


def check_mouse(gestures) -> list[dict]:
    if not isinstance(gestures, (list, tuple)):
        raise ValueError("Mouse gestures must be a list.")
    return [check_gesture(g) for g in gestures]


def check_cursor(key, value):
    spec = CURSOR_SPEC.get(key)
    if spec is None:
        raise ValueError(f"Unknown cursor setting: {key!r}")
    kind = spec[0]
    if kind == "enum":
        if value not in spec[1]:
            raise ValueError(f"Invalid value for {key}: {value!r}")
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"Invalid value for {key}: {value!r}")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        raise ValueError(f"Invalid value for {key}: {value!r}")
    lo, hi = spec[1], spec[2]
    if kind == "int":
        return int(min(hi, max(lo, round(value))))
    return float(min(hi, max(lo, float(value))))


def check_modifier(role, mod) -> str:
    if role not in MODIFIER_ROLES:
        raise ValueError(f"Unknown modifier role: {role!r}")
    if mod not in MODS:
        raise ValueError(f"Invalid modifier: {mod!r}")
    return mod


def check_modal(key, keys) -> list[str]:
    if key not in MODAL_ROLES:
        raise ValueError(f"Unknown modal key: {key!r}")
    if isinstance(keys, str):
        keys = [keys]
    if not isinstance(keys, (list, tuple)):
        raise ValueError("Modal keys must be a list.")
    out = []
    for k in keys:
        if not is_plain_key(k):
            raise ValueError(f"Invalid modal key: {k!r}")
        out.append(k)
    return out


def empty_user(profile_id: str, name: str, base: str) -> dict:
    return {"format": FORMAT, "version": VERSION, "id": profile_id, "name": name, "base": base,
            "keys": {}, "mouse": None, "cursor": {}, "modifiers": {}, "modal": {}}


def _clean_sections(doc: dict, strict: bool, where: str) -> dict:
    out: dict = {"keys": {}, "mouse": None, "cursor": {}, "modifiers": {}, "modal": {}}
    keys = doc.get("keys") or {}
    if not isinstance(keys, dict):
        raise ValueError("The keys section must be an object.")
    for aid, bindings in keys.items():
        if not isinstance(aid, str):
            raise ValueError("Action ids must be text.")
        if strict:
            out["keys"][aid] = check_bindings(bindings)
        else:
            cleaned = _clean_bindings(aid, bindings, where)
            if cleaned is not None:
                out["keys"][aid] = cleaned
    mouse = doc.get("mouse")
    if mouse is not None:
        if strict:
            out["mouse"] = check_mouse(mouse)
        else:
            try:
                out["mouse"] = check_mouse(mouse)
            except ValueError as exc:
                LOG.warning("controls: %s: mouse section dropped: %s", where, exc)
    for section, check in (("cursor", check_cursor), ("modifiers", check_modifier), ("modal", check_modal)):
        values = doc.get(section) or {}
        if not isinstance(values, dict):
            raise ValueError(f"The {section} section must be an object.")
        for k, v in values.items():
            try:
                out[section][k] = check(k, v)
            except ValueError as exc:
                if strict:
                    raise
                LOG.warning("controls: %s: %s", where, exc)
    return out


def load_user(doc) -> dict:
    if not isinstance(doc, dict):
        raise ValueError("A profile must be an object.")
    if doc.get("format") != FORMAT or doc.get("version") != VERSION:
        raise ValueError("Not a quartz-controls version 1 profile.")
    pid = doc.get("id")
    if not isinstance(pid, str) or not USER_ID_RE.match(pid):
        raise ValueError(f"Invalid profile id: {pid!r}")
    name = doc.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 48:
        raise ValueError(f"Invalid profile name: {name!r}")
    base = doc.get("base")
    if base not in BUILTIN_IDS:
        raise ValueError(f"Invalid profile base: {base!r}")
    out = empty_user(pid, name.strip(), base)
    out.update(_clean_sections(doc, False, f"profile {name.strip()!r}"))
    return out


def import_document(data) -> dict:
    if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("version") != VERSION:
        raise ValueError("This file is not a Quartz controls profile (format quartz-controls, version 1).")
    base = data.get("base") if data.get("base") in BUILTIN_IDS else "standard"
    name = data.get("name")
    if name is None:
        name = "Imported"
    if not isinstance(name, str) or not name.strip():
        raise ValueError("This file is not a Quartz controls profile: the name is invalid.")
    out = empty_user("", name.strip()[:48], base)
    try:
        out.update(_clean_sections(data, True, "import"))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"This file is not a Quartz controls profile: {exc}") from exc
    return out


def _action_scope(action_id: str, registry) -> str:
    action = registry.get(action_id) if registry else None
    if action is not None:
        return action.scope
    return DEFAULT_SCOPES.get(action_id, "global")


def _pairs(action_id: str, bindings, registry) -> tuple[tuple[str, str], ...]:
    out = []
    for b in bindings:
        parts = binding_parts(b)
        if parts is None or not is_valid(parts[0]):
            continue
        out.append((parts[0], parts[1] or _action_scope(action_id, registry)))
    return tuple(out)


def tool_shortcuts() -> list[tuple[str, str]]:
    try:
        from quartz_studio.modeling import registry as tool_registry
    except ImportError:
        return []
    out = []
    for tool_id in tool_registry.tool_ids():
        spec = tool_registry.get_tool(tool_id)
        if spec.shortcut:
            out.append((spec.id, spec.shortcut))
    return out


def _classic_tool_pair(shortcut: str, action_id: str, registry) -> tuple[str, str]:
    if parse_chord(shortcut) is None:
        seq = _sequence(shortcut)
        if seq is not None and not (seq[0].keyboardModifiers() & _MOD_MASK):
            return shortcut, "viewport"
    return shortcut, _action_scope(action_id, registry)


def _full_mouse(gestures) -> tuple[dict, ...]:
    return tuple(check_gesture(g) for g in gestures)


def _builtin_resolved(base_id: str, registry) -> dict:
    doc = BUILTINS[base_id]
    keys = {aid: _pairs(aid, b, registry) for aid, b in doc["keys"].items()}
    if base_id == "classic":
        for tool_id, shortcut in tool_shortcuts():
            aid = "tool." + tool_id
            if aid not in keys and is_valid(shortcut):
                keys[aid] = (_classic_tool_pair(shortcut, aid, registry),)
    return {"keys": keys, "mouse": _full_mouse(doc["mouse"]), "cursor": dict(doc["cursor"]),
            "modifiers": dict(doc["modifiers"]), "modal": {k: list(v) for k, v in doc["modal"].items()}}


def resolve(doc: dict, registry=None) -> Resolved:
    if registry is None:
        from quartz_studio.controls import actions as actions_module

        registry = actions_module.known()
    builtin = doc.get("id") in BUILTIN_IDS and doc.get("base") is None
    base_id = doc["id"] if builtin else doc.get("base")
    if base_id not in BUILTIN_IDS:
        base_id = "standard"
    res = _builtin_resolved(base_id, registry)
    overridden: set[str] = set()
    if not builtin:
        for aid, bindings in (doc.get("keys") or {}).items():
            res["keys"][aid] = _pairs(aid, bindings, registry)
            overridden.add(aid)
        if doc.get("mouse") is not None:
            try:
                res["mouse"] = _full_mouse(doc["mouse"])
                overridden.add("mouse")
            except ValueError:
                pass
        for section, check in (("cursor", check_cursor), ("modifiers", check_modifier),
                               ("modal", check_modal)):
            for k, v in (doc.get(section) or {}).items():
                try:
                    res[section][k] = check(k, v)
                except ValueError:
                    continue
                overridden.add(f"{section}.{k}")
    for aid, action in (registry or {}).items():
        if aid not in res["keys"] and action.default_keys:
            pairs = _pairs(aid, action.default_keys, registry)
            if pairs:
                res["keys"][aid] = pairs
    modal = {k: tuple(v) for k, v in res["modal"].items()}
    return Resolved(id=doc["id"], name=doc["name"], builtin=builtin, base=None if builtin else base_id,
                    keys=res["keys"], mouse=res["mouse"], cursor=res["cursor"], modifiers=res["modifiers"],
                    modal=modal, overridden=frozenset(overridden))


def export_document(res: Resolved, registry=None) -> dict:
    keys = {}
    for aid, pairs in res.keys.items():
        out = []
        for text, scope in pairs:
            if scope == _action_scope(aid, registry):
                out.append(text)
            else:
                out.append({"key": text, "scope": scope})
        keys[aid] = out
    return {
        "format": FORMAT,
        "version": VERSION,
        "id": res.id,
        "name": res.name,
        "base": res.id if res.builtin else res.base,
        "keys": keys,
        "mouse": [copy.deepcopy(g) for g in res.mouse],
        "cursor": dict(res.cursor),
        "modifiers": dict(res.modifiers),
        "modal": {k: list(v) for k, v in res.modal.items()},
    }


def scopes_overlap(a: str, b: str) -> bool:
    return a == b or a == "global" or b == "global"


def _flat(res: Resolved) -> list[tuple[str, str, str, str]]:
    out = []
    for aid, pairs in res.keys.items():
        for text, scope in pairs:
            norm = normalize(text)
            if norm is not None:
                out.append((norm, text, scope, aid))
    return out


def conflicts(profile) -> list[tuple[str, str, str]]:
    res = profile if isinstance(profile, Resolved) else resolve(profile)
    flat = [(n, t, s, a, parse_chord(t)) for n, t, s, a in _flat(res)]
    plain = [_plain_part(t) if c is None else None for _n, t, _s, _a, c in flat]
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for i, (na, ta, sa, aa, ca) in enumerate(flat):
        for j in range(i + 1, len(flat)):
            nb, tb, sb, ab, cb = flat[j]
            if aa == ab or not scopes_overlap(sa, sb):
                continue
            hit = None
            if na == nb:
                hit = ta
            elif ca is not None and cb is None and plain[j] == ca[0]:
                hit = ta
            elif cb is not None and ca is None and plain[i] == cb[0]:
                hit = tb
            if hit is not None:
                item = (hit, aa, ab)
                if item not in seen:
                    seen.add(item)
                    out.append(item)
    return out


def hold_key_codes(res: Resolved) -> set[int]:
    out = set()
    for g in res.mouse:
        if g.get("key"):
            code = key_code(g["key"])
            if code is not None:
                out.add(code)
    return out


def _gesture_key_held(g: dict, held) -> bool:
    if not g.get("key"):
        return True
    code = key_code(g["key"])
    return code is not None and code in held


def paint_buttons(res: Resolved) -> set[str]:
    return {g["button"] for g in res.mouse if g.get("op") == "context" and not g["double"]}


def is_paint_gesture(res: Resolved, g: dict | None) -> bool:
    if not g:
        return False
    op = g.get("op")
    return op == "context" or (op in ("add", "remove") and g.get("button") in paint_buttons(res))


def match_press(res: Resolved, button: str, mods, held, double: bool = False) -> dict | None:
    mods = {m for m in (mods or ()) if m in MODS}
    held = {int(getattr(k, "value", k)) for k in (held or ())}
    hold_down = bool(hold_key_codes(res) & held)
    if double:
        for g in res.mouse:
            if g["button"] != button or not g["double"]:
                continue
            if set(g["mods"]) != mods or not _gesture_key_held(g, held):
                continue
            if hold_down and is_paint_gesture(res, g):
                continue
            return g
    best = None
    best_score = -1
    for g in res.mouse:
        if g["button"] != button or g["double"]:
            continue
        if not set(g["mods"]) <= mods or not _gesture_key_held(g, held):
            continue
        if hold_down and is_paint_gesture(res, g):
            continue
        score = len(g["mods"]) + (1 if g.get("key") else 0)
        if score > best_score:
            best, best_score = g, score
    return best


def modifier_name(res: Resolved, role: str) -> str:
    return MOD_NAMES[res.modifiers[role]]


def modal_keys(res: Resolved, key: str) -> tuple[str, ...]:
    return tuple(res.modal.get(key, ()))


class _ProfilesModule(types.ModuleType):
    def __call__(self) -> list[dict]:
        from quartz_studio import controls

        return controls.profile_list()


sys.modules[__name__].__class__ = _ProfilesModule
