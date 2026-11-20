from __future__ import annotations

import builtins
import keyword
import re

from PySide6.QtCore import QRect, QSize, QStringListModel, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QCheckBox, QCompleter, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QPushButton, QWidget)

from .. import theme
from .console import BUTTON_H, INDENT
from .highlight import PythonHighlighter, mono_font

__all__ = ["CodeEditor", "FindBar", "LineNumberArea", "GUTTER_WIDTHS", "completion_words"]

GUTTER_WIDTHS = (24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 112, 128)
GUTTER_PAD = 8
POPUP_W = 256
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_MEMBER = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)?$")
_IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
SCOPE_NAMES = ("quartz", "doc", "op", "np", "frame", "tag")


def _api_names() -> list[str]:
    from . import api
    names = set(api.__all__)
    names.update(("Selection", "OpResult", "ToolSpec", "ToolParam", "ObjectSpec", "ObjectParam"))
    return sorted(n for n in names if not n.startswith("_"))


def completion_words(text: str = "", owner: str | None = None) -> list[str]:
    if owner == "quartz":
        return _api_names()
    if owner == "np":
        import numpy as np
        return sorted(n for n in dir(np) if not n.startswith("_"))
    if owner is not None:
        return []
    words = set(keyword.kwlist) | {n for n in dir(builtins) if not n.startswith("_")} | set(SCOPE_NAMES)
    words.update(_IDENT.findall(text))
    return sorted(words, key=str.lower)


class LineNumberArea(QWidget):

    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):

    runRequested = Signal()
    saveRequested = Signal()
    findRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(mono_font())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * len(INDENT))
        self.highlighter = PythonHighlighter(self.document())
        self.gutter = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self.gutter.update)
        self._update_gutter_width()
        self._model = QStringListModel(self)
        self.completer = QCompleter(self._model, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated[str].connect(self.insert_completion)

    def gutter_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        need = GUTTER_PAD * 2 + self.fontMetrics().horizontalAdvance("9") * digits
        for w in GUTTER_WIDTHS:
            if w >= need:
                return w
        return GUTTER_WIDTHS[-1]

    def _update_gutter_width(self, *_args) -> None:
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, event) -> None:
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor(theme.SURFACE_CARD))
        painter.setFont(self.font())
        current = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        height = self.fontMetrics().height()
        width = self.gutter.width() - GUTTER_PAD
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(theme.ACCENT if number == current else theme.TEXT_MUTED))
                painter.drawText(0, top, width, height, Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1
        painter.end()

    def line_numbers_visible(self) -> int:
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        count = 0
        while block.isValid() and top <= self.viewport().height():
            count += 1
            top += self.blockBoundingRect(block).height()
            block = block.next()
        return count

    def _prefix(self) -> tuple[str, str | None]:
        cursor = self.textCursor()
        line = cursor.block().text()[:cursor.positionInBlock()]
        m = _MEMBER.search(line)
        if m:
            return m.group(2) or "", m.group(1)
        m = _WORD.search(line)
        return (m.group(0) if m else ""), None

    def complete(self) -> int:
        prefix, owner = self._prefix()
        words = completion_words(self.toPlainText(), owner)
        if owner is None and prefix:
            words = [w for w in words if w != prefix]
        self._model.setStringList(words)
        self.completer.setCompletionPrefix(prefix)
        count = self.completer.completionCount()
        if count == 0:
            self.completer.popup().hide()
            return 0
        self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(POPUP_W)
        self.completer.complete(rect)
        return count

    def insert_completion(self, text: str) -> None:
        prefix, _owner = self._prefix()
        cursor = self.textCursor()
        if prefix:
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.completer.popup().hide()

    def _find_flags(self, backward: bool, case: bool, whole: bool = False):
        flags = QTextDocument.FindFlag(0)
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        if case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole:
            flags |= QTextDocument.FindFlag.FindWholeWords
        return flags

    def find_text(self, text: str, backward: bool = False, case: bool = False) -> bool:
        if not text:
            return False
        flags = self._find_flags(backward, case)
        if self.find(text, flags):
            return True
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        return self.find(text, flags)

    def _selection_matches(self, text: str, case: bool) -> bool:
        sel = self.textCursor().selectedText()
        return sel == text if case else sel.lower() == text.lower()

    def replace_next(self, text: str, replacement: str, case: bool = False) -> bool:
        if not text:
            return False
        if not self._selection_matches(text, case) and not self.find_text(text, case=case):
            return False
        cursor = self.textCursor()
        cursor.insertText(replacement)
        self.setTextCursor(cursor)
        self.find_text(text, case=case)
        return True

    def replace_all(self, text: str, replacement: str, case: bool = False) -> int:
        if not text:
            return 0
        doc = self.document()
        flags = self._find_flags(False, case)
        cursor = QTextCursor(doc)
        edit = QTextCursor(doc)
        edit.beginEditBlock()
        count = 0
        while True:
            cursor = doc.find(text, cursor, flags)
            if cursor.isNull():
                break
            cursor.insertText(replacement)
            count += 1
        edit.endEditBlock()
        return count

    def keyPressEvent(self, e: QKeyEvent) -> None:
        key = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        popup = self.completer.popup()
        if popup.isVisible() and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape,
                                         Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            e.ignore()
            return
        if (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and ctrl) or key == Qt.Key.Key_F5:
            self.runRequested.emit()
            return
        if key == Qt.Key.Key_S and ctrl:
            self.saveRequested.emit()
            return
        if key == Qt.Key.Key_F and ctrl:
            self.findRequested.emit()
            return
        if key == Qt.Key.Key_Space and ctrl:
            self.complete()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not mods:
            cursor = self.textCursor()
            line = cursor.block().text()[:cursor.positionInBlock()]
            indent = line[:len(line) - len(line.lstrip(" "))]
            if line.rstrip().endswith(":"):
                indent += INDENT
            cursor.insertText("\n" + indent)
            self.setTextCursor(cursor)
            return
        if key == Qt.Key.Key_Tab and not mods:
            cursor = self.textCursor()
            if cursor.hasSelection():
                self.indent_selection(1)
            else:
                cursor.insertText(INDENT)
            return
        if key == Qt.Key.Key_Backtab:
            self.indent_selection(-1)
            return
        super().keyPressEvent(e)
        if e.text() == ".":
            _prefix, owner = self._prefix()
            if owner in ("quartz", "np"):
                self.complete()
        elif popup.isVisible():
            if self._prefix()[0] or self._prefix()[1]:
                self.complete()
            else:
                popup.hide()

    def indent_selection(self, direction: int) -> None:
        cursor = self.textCursor()
        start, end = sorted((cursor.selectionStart(), cursor.selectionEnd()))
        doc = self.document()
        first = doc.findBlock(start).blockNumber()
        last = doc.findBlock(max(start, end - 1) if end > start else end).blockNumber()
        cursor.beginEditBlock()
        for n in range(first, last + 1):
            block = doc.findBlockByNumber(n)
            c = QTextCursor(block)
            if direction > 0:
                c.insertText(INDENT)
            else:
                text = block.text()
                remove = len(text) - len(text.lstrip(" "))
                remove = min(remove, len(INDENT))
                if remove:
                    c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, remove)
                    c.removeSelectedText()
        cursor.endEditBlock()


class FindBar(QWidget):

    closed = Signal()

    def __init__(self, editor: CodeEditor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = editor
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.find_edit = QLineEdit(self)
        self.find_edit.setPlaceholderText("Find")
        self.replace_edit = QLineEdit(self)
        self.replace_edit.setPlaceholderText("Replace with")
        self.case_box = QCheckBox("Match Case", self)
        self.next_button = QPushButton("Next", self)
        self.prev_button = QPushButton("Previous", self)
        self.replace_button = QPushButton("Replace", self)
        self.replace_all_button = QPushButton("Replace All", self)
        self.close_button = QPushButton("Close", self)
        for w in (self.find_edit, self.replace_edit):
            w.setFixedHeight(BUTTON_H)
            lay.addWidget(w, 1)
        lay.addWidget(self.case_box)
        for b in (self.next_button, self.prev_button, self.replace_button, self.replace_all_button,
                  self.close_button):
            b.setFixedHeight(BUTTON_H)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            lay.addWidget(b)
        self.last_count = 0
        self.last_found = False
        self.find_edit.returnPressed.connect(lambda: self.find_next())
        self.replace_edit.returnPressed.connect(lambda: self.replace())
        self.next_button.clicked.connect(lambda: self.find_next())
        self.prev_button.clicked.connect(lambda: self.find_next(backward=True))
        self.replace_button.clicked.connect(lambda: self.replace())
        self.replace_all_button.clicked.connect(lambda: self.replace_all())
        self.close_button.clicked.connect(self.close_bar)

    def open(self) -> None:
        sel = self.editor.textCursor().selectedText()
        if sel and "\u2029" not in sel:
            self.find_edit.setText(sel)
        self.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def close_bar(self) -> None:
        self.hide()
        self.editor.setFocus()
        self.closed.emit()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close_bar()
            return
        super().keyPressEvent(e)

    def find_next(self, backward: bool = False) -> bool:
        self.last_found = self.editor.find_text(self.find_edit.text(), backward, self.case_box.isChecked())
        return self.last_found

    def replace(self) -> bool:
        self.last_found = self.editor.replace_next(self.find_edit.text(), self.replace_edit.text(),
                                                   self.case_box.isChecked())
        return self.last_found

    def replace_all(self) -> int:
        self.last_count = self.editor.replace_all(self.find_edit.text(), self.replace_edit.text(),
                                                  self.case_box.isChecked())
        return self.last_count
