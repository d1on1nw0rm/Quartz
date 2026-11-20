import os
from types import ModuleType
from typing import ClassVar

import numpy as np

from quartz.errors import PropertyTypeError
from quartz.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from quartz.rna import PropCollection, Struct, builtin_struct, get_property
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type

__all__ = ["Text", "TextLine", "BlendDataTexts"]

_HIGHLIGHT_EXTENSIONS = frozenset({".py", ".osl", ".glsl", ".toml"})
_MISSING = object()


def _items(*identifiers):
    return [(i, i, "") for i in identifiers]


def _never_none(cls, *names) -> None:
    for name in names:
        cls.__dict__[name].is_never_none = True


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _check_str(value, where: str) -> str:
    if not isinstance(value, str):
        raise PropertyTypeError(f"{where} expected a string type, not {type(value).__name__}")
    return value


def _check_int(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise PropertyTypeError(f"{where} expected an int type, not {type(value).__name__}")
    return int(value)


@builtin_struct
class TextLine(Struct):

    _q_strict_attrs = True

    body: StringProperty(options=set(), meta={"virtual_get": lambda s: s._q_get_body(), "virtual_set": lambda s, v: s._q_set_body(v)})

    def _q_check(self) -> int:
        text = self._q_owner
        if self._q_index >= len(text._q_lines):
            raise IndexError(f"TextLine index {self._q_index} out of range")
        return self._q_index

    def _q_get_body(self) -> str:
        return self._q_owner._q_lines[self._q_check()]

    def _q_set_body(self, value: str) -> None:
        i = self._q_check()
        text = self._q_owner
        text._q_lines[i:i + 1] = _normalize(value).split("\n")
        text._q_clamp_cursor()
        text._q_is_dirty = True

    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented
        return self._q_owner is other._q_owner and self._q_index == other._q_index

    def __hash__(self):
        return hash((type(self), id(self._q_owner), self._q_index))


def _make_line(text, index: int) -> TextLine:
    line = TextLine._q_new_child(text, f"lines[{index}]")
    line._q_index = index
    return line


class _TextLines(PropCollection):
    def __init__(self, text):
        PropCollection.__init__(self, owner=text, path="lines")
        self._q_text = text

    def __len__(self) -> int:
        return len(self._q_text._q_lines)

    def _q_items(self):
        return [_make_line(self._q_text, i) for i in range(len(self))]

    def __getitem__(self, key):
        n = len(self)
        if isinstance(key, slice):
            return [_make_line(self._q_text, i) for i in range(*key.indices(n))]
        if isinstance(key, str):
            raise KeyError(f'bpy_prop_collection[key]: key "{key}" not found')
        if isinstance(key, bool) or not isinstance(key, (int, np.integer)):
            raise TypeError(f"bpy_prop_collection[key]: invalid key, must be an int, not {type(key).__name__}")
        i = int(key)
        if i < 0:
            i += n
        if i < 0 or i >= n:
            raise IndexError(f"bpy_prop_collection[index]: index {int(key)} out of range, size {n}")
        return _make_line(self._q_text, i)

    def __iter__(self):
        for i in range(len(self)):
            yield _make_line(self._q_text, i)

    def __contains__(self, key) -> bool:
        if isinstance(key, str):
            return False
        return any(item == key for item in self)

    def keys(self) -> list:
        return []

    def __repr__(self) -> str:
        return f"{repr(self._q_text)}.lines"


@builtin_struct
class Text(ID):

    filepath: StringProperty(options=set())
    is_dirty: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_dirty()})
    is_modified: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_modified()})
    is_in_memory: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_in_memory()})
    use_module: BoolProperty()
    indentation: EnumProperty(items=_items('TABS', 'SPACES'), default='TABS')
    current_character: IntProperty(subtype='UNSIGNED', min=0, meta={"virtual_get": lambda s: s._q_get_current_character(), "virtual_set": lambda s, v: s._q_set_current_character(v)})
    current_line_index: IntProperty(soft_min=-10000, soft_max=10000, meta={"virtual_get": lambda s: s._q_get_current_line_index(), "virtual_set": lambda s, v: s._q_set_current_line_index(v)})
    select_end_line_index: IntProperty(soft_min=-10000, soft_max=10000, meta={"virtual_get": lambda s: s._q_get_select_end_line_index(), "virtual_set": lambda s, v: s._q_set_select_end_line_index(v)})
    select_end_character: IntProperty(subtype='UNSIGNED', min=0, meta={"virtual_get": lambda s: s._q_get_select_end_character(), "virtual_set": lambda s, v: s._q_set_select_end_character(v)})

    q_schema_version: ClassVar[int] = 1

    @classmethod
    def _q_construct(cls, name):
        self = super()._q_construct(name)
        self._q_lines = [""]
        self._q_cursor = [0, 0, 0, 0]
        self._q_in_memory = False
        self._q_is_dirty = False
        self._q_lines_coll = None
        return self

    def _q_clamp(self, line, char) -> tuple[int, int]:
        lines = self._q_lines
        line = max(0, min(int(line), len(lines) - 1))
        char = max(0, min(int(char), len(lines[line])))
        return line, char

    def _q_clamp_cursor(self) -> None:
        c = self._q_cursor
        c[0], c[1] = self._q_clamp(c[0], c[1])
        c[2], c[3] = self._q_clamp(c[2], c[3])

    def _q_offset(self, line: int, char: int) -> int:
        return sum(len(self._q_lines[i]) + 1 for i in range(line)) + char

    def _q_position(self, offset: int) -> tuple[int, int]:
        for i, body in enumerate(self._q_lines):
            if offset <= len(body):
                return i, offset
            offset -= len(body) + 1
        last = len(self._q_lines) - 1
        return last, len(self._q_lines[last])

    def _q_selection_offsets(self) -> tuple[int, int]:
        c = self._q_cursor
        a = self._q_offset(*self._q_clamp(c[0], c[1]))
        b = self._q_offset(*self._q_clamp(c[2], c[3]))
        return (a, b) if a <= b else (b, a)

    def _q_range_offsets(self, rng) -> tuple[int, int]:
        if rng is None:
            return self._q_selection_offsets()
        try:
            (l0, c0), (l1, c1) = rng
        except (TypeError, ValueError) as exc:
            raise PropertyTypeError("Text: range expected ((line, char), (line, char))") from exc
        a = self._q_offset(*self._q_clamp(_check_int(l0, "Text range"), _check_int(c0, "Text range")))
        b = self._q_offset(*self._q_clamp(_check_int(l1, "Text range"), _check_int(c1, "Text range")))
        return (a, b) if a <= b else (b, a)

    def _q_replace(self, start: int, end: int, body: str) -> None:
        full = self.as_string()
        body = _normalize(body)
        new = full[:start] + body + full[end:]
        self._q_lines = new.split("\n")
        line, char = self._q_position(start + len(body))
        self._q_cursor[:] = [line, char, line, char]
        self._q_edited()

    def _q_edited(self) -> None:
        self._q_is_dirty = True
        self.q_tag("DATA")

    def _q_get_is_dirty(self) -> bool:
        return bool(self._q_is_dirty)

    def _q_get_is_modified(self) -> bool:
        return False

    def _q_get_is_in_memory(self) -> bool:
        return bool(self._q_in_memory)

    def _q_get_current_line_index(self) -> int:
        return self._q_cursor[0]

    def _q_set_current_line_index(self, value) -> None:
        self._q_cursor[0], self._q_cursor[1] = self._q_clamp(value, self._q_cursor[1])

    def _q_get_current_character(self) -> int:
        return self._q_cursor[1]

    def _q_set_current_character(self, value) -> None:
        self._q_cursor[0], self._q_cursor[1] = self._q_clamp(self._q_cursor[0], value)

    def _q_get_select_end_line_index(self) -> int:
        return self._q_cursor[2]

    def _q_set_select_end_line_index(self, value) -> None:
        self._q_cursor[2], self._q_cursor[3] = self._q_clamp(value, self._q_cursor[3])

    def _q_get_select_end_character(self) -> int:
        return self._q_cursor[3]

    def _q_set_select_end_character(self, value) -> None:
        self._q_cursor[2], self._q_cursor[3] = self._q_clamp(self._q_cursor[2], value)

    @property
    def lines(self):
        if self._q_lines_coll is None:
            self._q_lines_coll = _TextLines(self)
        return self._q_lines_coll

    @property
    def current_line(self) -> TextLine:
        return _make_line(self, self._q_clamp(self._q_cursor[0], 0)[0])

    @property
    def select_end_line(self) -> TextLine:
        return _make_line(self, self._q_clamp(self._q_cursor[2], 0)[0])

    def clear(self) -> None:
        self._q_lines = [""]
        self._q_cursor[:] = [0, 0, 0, 0]
        self._q_edited()

    def write(self, text: str) -> None:
        _check_str(text, "Text.write(): text")
        start, end = self._q_selection_offsets()
        self._q_replace(start, end, text)

    def from_string(self, text: str) -> None:
        _check_str(text, "Text.from_string(): text")
        self._q_lines = _normalize(text).split("\n")
        last = len(self._q_lines) - 1
        end = len(self._q_lines[last])
        self._q_cursor[:] = [last, end, last, end]
        self._q_edited()

    def as_string(self) -> str:
        return "\n".join(self._q_lines)

    def is_syntax_highlight_supported(self) -> bool:
        return os.path.splitext(self._q_name)[1].lower() in _HIGHLIGHT_EXTENSIONS

    def select_set(self, line_start: int, char_start: int, line_end: int, char_end: int) -> None:
        l0, c0 = self._q_clamp(_check_int(line_start, "Text.select_set(): line_start"),
                               _check_int(char_start, "Text.select_set(): char_start"))
        l1, c1 = self._q_clamp(_check_int(line_end, "Text.select_set(): line_end"),
                               _check_int(char_end, "Text.select_set(): char_end"))
        self._q_cursor[:] = [l0, c0, l1, c1]

    def cursor_set(self, line: int, character: int = 0, select: bool = False) -> None:
        l0, c0 = self._q_clamp(_check_int(line, "Text.cursor_set(): line"),
                               _check_int(character, "Text.cursor_set(): character"))
        self._q_cursor[0], self._q_cursor[1] = l0, c0
        if not select:
            self._q_cursor[2], self._q_cursor[3] = l0, c0

    def as_module(self) -> ModuleType:
        name = self._q_name
        mod_name = name[:-3] if name.endswith(".py") else name
        module = ModuleType(mod_name)
        module.__file__ = name
        code = compile(self.as_string(), name, "exec")
        exec(code, module.__dict__)
        return module

    def region_as_string(self, *a, **k) -> str:
        rng = _parse_args("Text.region_as_string", a, k, ("range",), required=0)[0]
        start, end = self._q_range_offsets(rng)
        return self.as_string()[start:end]

    def region_from_string(self, *a, **k) -> None:
        body, rng = _parse_args("Text.region_from_string", a, k, ("body", "range"), required=1)
        _check_str(body, "Text.region_from_string(): body")
        start, end = self._q_range_offsets(rng)
        self._q_replace(start, end, body)

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        state["text_body"] = {
            "lines": list(self._q_lines),
            "cursor": [int(v) for v in self._q_cursor],
            "in_memory": bool(self._q_in_memory),
            "dirty": bool(self._q_is_dirty),
        }
        return state

    def _q_state_set(self, state: dict) -> None:
        super()._q_state_set(state)
        body = state.get("text_body")
        if body is not None:
            self._q_lines = list(body.get("lines", [""])) or [""]
            self._q_cursor = [int(v) for v in body.get("cursor", (0, 0, 0, 0))]
            self._q_in_memory = bool(body.get("in_memory", False))
            self._q_is_dirty = bool(body.get("dirty", False))


_never_none(Text, "filepath")


def _parse_args(where: str, args: tuple, kwargs: dict, names: tuple, *, required: int) -> list:
    if len(args) > len(names):
        raise TypeError(f"{where}() takes at most {len(names)} positional arguments ({len(args)} given)")
    values = list(args) + [_MISSING] * (len(names) - len(args))
    for key, value in kwargs.items():
        if key not in names:
            raise TypeError(f"{where}() got an unexpected keyword argument '{key}'")
        index = names.index(key)
        if values[index] is not _MISSING:
            raise TypeError(f"{where}() got multiple values for argument '{key}'")
        values[index] = value
    for index in range(required):
        if values[index] is _MISSING:
            raise TypeError(f"{where}() missing required argument '{names[index]}'")
    return [None if v is _MISSING else v for v in values]


class BlendDataTexts(IDCollection):
    def new(self, name: str) -> Text:
        text = IDCollection.new(self, name)
        text._q_in_memory = True
        text._q_is_dirty = False
        return text

    def load(self, filepath: str, internal: bool = False) -> Text:
        if not isinstance(filepath, str):
            raise PropertyTypeError(f"BlendDataTexts.load(): filepath expected a string type, not {type(filepath).__name__}")
        with open(filepath, encoding="utf-8", errors="replace", newline="") as handle:
            content = handle.read()
        text = IDCollection.new(self, os.path.basename(filepath))
        text._q_lines = _normalize(content).split("\n")
        text._q_cursor = [0, 0, 0, 0]
        get_property(Text, "filepath").write_raw(text, "" if internal else filepath)
        text._q_in_memory = bool(internal)
        text._q_is_dirty = False
        return text

    def remove(self, text: Text, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None:
        IDCollection.remove(self, text, do_unlink, do_id_user, do_ui_user)


register_id_type(Text, id_type="TEXT", collection="texts", default_name="Text", collection_cls=BlendDataTexts)
