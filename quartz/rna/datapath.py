from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PathToken:
    kind: str
    value: object


def escape_identifier(string: str) -> str:
    return string.replace("\\", "\\\\").replace('"', '\\"')


def unescape_identifier(string: str) -> str:
    out = []
    i = 0
    n = len(string)
    while i < n:
        c = string[i]
        if c == "\\" and i + 1 < n:
            nxt = string[i + 1]
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
            if nxt == '"':
                out.append('"')
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out)


def parse(path: str) -> tuple[PathToken, ...]:
    if path == "":
        return ()
    tokens: list[PathToken] = []
    i = 0
    n = len(path)

    def read_ident(s, pos):
        start = pos
        if pos >= len(s) or not (s[pos].isalpha() or s[pos] == "_"):
            return None, pos
        pos += 1
        while pos < len(s) and (s[pos].isalnum() or s[pos] == "_"):
            pos += 1
        return s[start:pos], pos

    ident, i = read_ident(path, i)
    if ident is None:
        raise ValueError(f'invalid data path "{path}"')
    tokens.append(PathToken("ATTR", ident))
    while i < n:
        c = path[i]
        if c == ".":
            i += 1
            ident, i = read_ident(path, i)
            if ident is None:
                raise ValueError(f'invalid data path "{path}"')
            tokens.append(PathToken("ATTR", ident))
        elif c == "[":
            i += 1
            if i >= n:
                raise ValueError(f'invalid data path "{path}"')
            if path[i] == '"' or path[i] == "'":
                quote = path[i]
                i += 1
                buf = []
                while i < n and path[i] != quote:
                    if path[i] == "\\" and i + 1 < n:
                        buf.append(path[i])
                        buf.append(path[i + 1])
                        i += 2
                        continue
                    buf.append(path[i])
                    i += 1
                if i >= n:
                    raise ValueError(f'invalid data path "{path}"')
                i += 1
                key = unescape_identifier("".join(buf))
                if i >= n or path[i] != "]":
                    raise ValueError(f'invalid data path "{path}"')
                i += 1
                tokens.append(PathToken("KEY", key))
                if i < n and path[i] != "." and path[i] != "[":
                    raise ValueError(f'invalid data path "{path}"')
            else:
                start = i
                while i < n and (path[i].isdigit() or path[i] == "-" or path[i] == "+"):
                    i += 1
                if start == i:
                    raise ValueError(f'invalid data path "{path}"')
                try:
                    idx = int(path[start:i])
                except ValueError:
                    raise ValueError(f'invalid data path "{path}"')
                if i >= n or path[i] != "]":
                    raise ValueError(f'invalid data path "{path}"')
                i += 1
                tokens.append(PathToken("INDEX", idx))
                if i < n and path[i] != "." and path[i] != "[":
                    raise ValueError(f'invalid data path "{path}"')
        else:
            raise ValueError(f'invalid data path "{path}"')
    return tuple(tokens)


def format(tokens) -> str:
    out = ""
    for t in tokens:
        if t.kind == "ATTR":
            if out == "":
                out += str(t.value)
            elif out.endswith("]"):
                out += "." + str(t.value)
            elif out.endswith("."):
                out += str(t.value)
            else:
                out += "." + str(t.value)
        elif t.kind == "INDEX":
            out += f"[{t.value}]"
        elif t.kind == "KEY":
            out += f'["{escape_identifier(str(t.value))}"]'
    return out


class PropertyRef:
    __slots__ = ("_q_struct", "_q_identifier", "_q_index")

    def __init__(self, struct, identifier, index=None):
        self._q_struct = struct
        self._q_identifier = identifier
        self._q_index = index

    @property
    def struct(self):
        return self._q_struct

    @property
    def identifier(self):
        return self._q_identifier

    @property
    def index(self):
        return self._q_index

    def __eq__(self, other):
        if not isinstance(other, PropertyRef):
            return False
        return (self._q_struct is other._q_struct and
                self._q_identifier == other._q_identifier and
                self._q_index == other._q_index)

    def __hash__(self):
        return hash((id(self._q_struct), self._q_identifier, self._q_index))


def resolve(root, path, *, coerce=True):
    tokens = parse(path) if isinstance(path, str) else tuple(path)
    text = path if isinstance(path, str) else format(tokens)
    try:
        return _resolve_tokens(root, tokens, coerce)
    except (AttributeError, IndexError, KeyError, TypeError) as e:
        raise ValueError(f'Path "{text}" could not be resolved') from e


def _resolve_tokens(root, tokens, coerce):
    from .annotations import get_property
    cur = root
    last_attr = None
    last_struct = root
    n = len(tokens)
    for idx, t in enumerate(tokens):
        is_last = idx == n - 1
        if t.kind == "ATTR":
            if is_last and not coerce and get_property(cur, t.value) is not None:
                return PropertyRef(cur, t.value, None)
            last_struct = cur
            cur = getattr(cur, t.value)
            last_attr = t.value
        elif t.kind == "INDEX":
            if is_last and not coerce and last_attr is not None and get_property(last_struct, last_attr) is not None:
                return PropertyRef(last_struct, last_attr, t.value)
            cur = cur[t.value]
        else:
            cur = cur[t.value]
    return cur
