from __future__ import annotations

import builtins
import keyword
import re

from PySide6.QtGui import QColor, QFont, QFontDatabase, QSyntaxHighlighter, QTextCharFormat

from .. import theme

__all__ = ["PythonHighlighter", "mono_font", "COLORS"]

COLORS = {
    "keyword": theme.TINT_AMETHYST,
    "builtin": theme.AXIS_Z,
    "string": theme.TINT_CITRINE,
    "comment": theme.TEXT_MUTED,
    "number": theme.TINT_ROSE,
    "definition": theme.ACCENT,
    "decorator": theme.ACCENT_PRESSED,
    "self": theme.TEXT_SECONDARY,
    "api": theme.ACCENT,
}

MONO_FAMILIES = ("Cascadia Mono", "Consolas", "Courier New")
MONO_PX = 12


def mono_font(pixel_size: int = MONO_PX) -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    families = set(QFontDatabase.families())
    for family in MONO_FAMILIES:
        if family in families:
            font = QFont(family)
            break
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    font.setPixelSize(pixel_size)
    return font


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.DemiBold)
    if italic:
        f.setFontItalic(True)
    return f


class PythonHighlighter(QSyntaxHighlighter):

    STATE_NONE = 0
    STATE_TRIPLE_SINGLE = 1
    STATE_TRIPLE_DOUBLE = 2

    def __init__(self, document) -> None:
        super().__init__(document)
        self.formats = {
            "keyword": _fmt(COLORS["keyword"], bold=True),
            "builtin": _fmt(COLORS["builtin"]),
            "string": _fmt(COLORS["string"]),
            "comment": _fmt(COLORS["comment"], italic=True),
            "number": _fmt(COLORS["number"]),
            "definition": _fmt(COLORS["definition"], bold=True),
            "decorator": _fmt(COLORS["decorator"]),
            "self": _fmt(COLORS["self"], italic=True),
            "api": _fmt(COLORS["api"]),
        }
        kw = "|".join(sorted(keyword.kwlist + list(getattr(keyword, "softkwlist", [])), key=len,
                             reverse=True))
        names = [n for n in dir(builtins) if not n.startswith("_")]
        bi = "|".join(sorted(names, key=len, reverse=True))
        self.rules = [
            (re.compile(r"\b(?:" + kw + r")\b"), "keyword", 0),
            (re.compile(r"\b(?:" + bi + r")\b"), "builtin", 0),
            (re.compile(r"\b(?:self|cls)\b"), "self", 0),
            (re.compile(r"\b(?:quartz|doc|op|np|frame)\b"), "api", 0),
            (re.compile(r"\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|"
                        r"(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?j?)\b"), "number", 0),
            (re.compile(r"^\s*@[\w\.]+"), "decorator", 0),
            (re.compile(r"\b(?:def|class)\s+(\w+)"), "definition", 1),
        ]
        self.string_re = re.compile(
            r"[rRbBuUfF]{0,2}(\"\"\"|'''|\"(?:[^\"\\\n]|\\.)*\"?|'(?:[^'\\\n]|\\.)*'?)")
        self.comment_re = re.compile(r"#[^\n]*")

    def _apply_rules(self, text: str, spans: list[tuple[int, int]]) -> None:
        def free(a: int, b: int) -> bool:
            return all(b <= s or a >= e for s, e in spans)

        for regex, name, group in self.rules:
            for m in regex.finditer(text):
                a, b = m.span(group)
                if a < b and free(a, b):
                    self.setFormat(a, b - a, self.formats[name])

    def highlightBlock(self, text: str) -> None:
        self.setCurrentBlockState(self.STATE_NONE)
        spans: list[tuple[int, int]] = []
        pos = 0
        prev = self.previousBlockState()
        if prev in (self.STATE_TRIPLE_SINGLE, self.STATE_TRIPLE_DOUBLE):
            delim = "'''" if prev == self.STATE_TRIPLE_SINGLE else '"""'
            end = text.find(delim)
            if end < 0:
                self.setFormat(0, len(text), self.formats["string"])
                self.setCurrentBlockState(prev)
                return
            pos = end + 3
            self.setFormat(0, pos, self.formats["string"])
            spans.append((0, pos))
        n = len(text)
        while pos < n:
            ch = text[pos]
            if ch == "#":
                self.setFormat(pos, n - pos, self.formats["comment"])
                spans.append((pos, n))
                break
            m = self.string_re.match(text, pos)
            if m and (pos == 0 or not (text[pos - 1].isalnum() or text[pos - 1] == "_")
                      or ch in "\"'"):
                token = m.group(1)
                start = pos
                if token in ("'''", '"""'):
                    end = text.find(token, m.end())
                    if end < 0:
                        self.setFormat(start, n - start, self.formats["string"])
                        spans.append((start, n))
                        self.setCurrentBlockState(self.STATE_TRIPLE_SINGLE if token == "'''"
                                                  else self.STATE_TRIPLE_DOUBLE)
                        break
                    stop = end + 3
                else:
                    stop = m.end()
                if stop > start and (ch in "\"'" or token[:1] in "\"'"):
                    self.setFormat(start, stop - start, self.formats["string"])
                    spans.append((start, stop))
                    pos = stop
                    continue
            pos += 1
        self._apply_rules(text, spans)
