from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import theme
from ..scene import get_scene
from . import api, paths
from .highlight import PythonHighlighter, mono_font
from .runner import ExecResult, default_timeout, execute, is_complete, make_namespace, refresh_namespace

__all__ = ["ConsoleInput", "ScriptConsole", "HISTORY_KEY", "HISTORY_LIMIT", "panel_qss"]

HISTORY_KEY = "console_history"
HISTORY_LIMIT = 200
INDENT = "    "
BUTTON_H = 24
MAX_INPUT_LINES = 8


def panel_qss() -> str:
    return f"""
QPlainTextEdit, QListWidget, QLineEdit, QKeySequenceEdit {{
    background: {theme.SURFACE_FIELD};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {theme.HAIRLINE};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {theme.ACCENT_TINT};
    selection-color: {theme.TEXT_BRIGHT};
}}
QPlainTextEdit:focus, QListWidget:focus, QLineEdit:focus {{
    border: 1px solid {theme.HAIRLINE_STRONG};
}}
QListWidget::item {{
    padding: 4px 8px;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background: {theme.ACCENT_TINT};
    color: {theme.TEXT_BRIGHT};
}}
QListWidget::item:hover {{
    background: {theme.SURFACE_HOVER};
}}
QLabel#qsScriptPrompt {{
    color: {theme.ACCENT};
}}
QLabel#qsScriptStatus {{
    color: {theme.TEXT_MUTED};
}}
"""


def _char(color: str) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    return f


class ConsoleInput(QPlainTextEdit):

    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.history: list[str] = []
        self._index = 0
        self._draft = ""
        self.setFont(mono_font())
        self.setTabChangesFocus(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setPlaceholderText("Python: Enter runs, Shift+Enter adds a line, Up and Down browse history")
        self.highlighter = PythonHighlighter(self.document())
        self.document().contentsChanged.connect(self._fit)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fit()

    def _fit(self) -> None:
        lines = max(1, min(MAX_INPUT_LINES, self.document().blockCount()))
        fm = self.fontMetrics()
        margins = self.contentsMargins()
        doc_margin = int(self.document().documentMargin()) * 2
        self.setFixedHeight(fm.lineSpacing() * lines + margins.top() + margins.bottom() + doc_margin + 4)

    def set_history(self, items: list[str]) -> None:
        self.history = [str(i) for i in items][-HISTORY_LIMIT:]
        self._index = len(self.history)

    def push_history(self, text: str) -> None:
        if text.strip() and (not self.history or self.history[-1] != text):
            self.history.append(text)
            del self.history[:-HISTORY_LIMIT]
        self._index = len(self.history)
        self._draft = ""

    def history_prev(self) -> bool:
        if not self.history or self._index == 0:
            return False
        if self._index == len(self.history):
            self._draft = self.toPlainText()
        self._index -= 1
        self._set_text(self.history[self._index])
        return True

    def history_next(self) -> bool:
        if self._index >= len(self.history):
            return False
        self._index += 1
        self._set_text(self._draft if self._index == len(self.history) else self.history[self._index])
        return True

    def _set_text(self, text: str) -> None:
        self.setPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.End)

    def _newline(self) -> None:
        cursor = self.textCursor()
        line = cursor.block().text()[:cursor.positionInBlock()]
        indent = line[:len(line) - len(line.lstrip(" "))]
        if line.rstrip().endswith(":"):
            indent += INDENT
        cursor.insertText("\n" + indent)
        self.setTextCursor(cursor)

    def ready_to_run(self) -> bool:
        text = self.toPlainText()
        lines = text.split("\n")
        if len(lines) == 1:
            return is_complete(text)
        last = lines[-1]
        if not last.strip():
            return True
        if last[:1] in (" ", "\t"):
            return False
        try:
            compile(text, "<console>", "exec")
        except SyntaxError:
            return is_complete(text)
        return True

    def submit(self) -> str:
        text = self.toPlainText()
        self.push_history(text)
        self.clear()
        self.submitted.emit(text)
        return text

    def keyPressEvent(self, e: QKeyEvent) -> None:
        key = e.key()
        mods = e.modifiers()
        cursor = self.textCursor()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self._newline()
                return
            if mods & Qt.KeyboardModifier.ControlModifier:
                self.submit()
                return
            if cursor.atEnd() and self.ready_to_run():
                self.submit()
                return
            self._newline()
            return
        if key == Qt.Key.Key_Up and not mods and cursor.blockNumber() == 0:
            if self.history_prev():
                return
        if key == Qt.Key.Key_Down and not mods and cursor.blockNumber() == self.document().blockCount() - 1:
            if self.history_next():
                return
        if key == Qt.Key.Key_Tab and not mods:
            cursor.insertText(INDENT)
            return
        if key == Qt.Key.Key_Escape:
            self.clear()
            return
        super().keyPressEvent(e)


class ScriptConsole(QWidget):

    executed = Signal(object)

    def __init__(self, scene=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene if scene is not None else get_scene()
        self.setObjectName("qsScriptConsole")
        self.setStyleSheet(panel_qss())
        self.namespace = make_namespace(self.scene)
        self.last_result: ExecResult | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.status = QLabel("Ready", self)
        self.status.setObjectName("qsScriptStatus")
        bar.addWidget(self.status, 1)
        self.clear_button = QPushButton("Clear", self)
        self.reset_button = QPushButton("Reset Namespace", self)
        for b in (self.clear_button, self.reset_button):
            b.setFixedHeight(BUTTON_H)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            bar.addWidget(b)
        lay.addLayout(bar)

        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setFont(mono_font())
        self.output.setMaximumBlockCount(5000)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        lay.addWidget(self.output, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.prompt = QLabel(">>>", self)
        self.prompt.setObjectName("qsScriptPrompt")
        self.prompt.setFont(mono_font())
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        row.addWidget(self.prompt)
        self.input = ConsoleInput(self)
        row.addWidget(self.input, 1)
        self.run_button = QPushButton("Run", self)
        self.run_button.setFixedHeight(BUTTON_H)
        self.run_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(row)

        self.input.set_history(self._load_history())
        self.input.submitted.connect(self.execute)
        self.run_button.clicked.connect(self.input.submit)
        self.clear_button.clicked.connect(self.clear)
        self.reset_button.clicked.connect(self.reset_namespace)
        api.add_message_listener(self._on_message)
        self.destroyed.connect(lambda *_a, fn=self._on_message: api.remove_message_listener(fn))
        self.write("Quartz Python console. Names: quartz, doc, op, np\n", theme.TEXT_MUTED)

    def _load_history(self) -> list[str]:
        items = paths.read_settings().get(HISTORY_KEY, [])
        return [str(i) for i in items] if isinstance(items, list) else []

    def _save_history(self) -> None:
        try:
            paths.update_settings(HISTORY_KEY, self.input.history[-HISTORY_LIMIT:])
        except OSError:
            pass

    def write(self, text: str, color: str | None = None) -> None:
        if not text:
            return
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, _char(color or theme.TEXT_PRIMARY))
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _on_message(self, text: str) -> None:
        self.write(text.rstrip("\n") + "\n", theme.ACCENT)

    def text(self) -> str:
        return self.output.toPlainText()

    def clear(self) -> None:
        self.output.clear()
        self.status.setText("Cleared")

    def reset_namespace(self) -> None:
        self.namespace = make_namespace(self.scene)
        self.write("Namespace reset\n", theme.TEXT_MUTED)
        self.status.setText("Namespace reset")

    def execute(self, code: str) -> ExecResult:
        lines = code.split("\n") if code else [""]
        echo = "\n".join((">>> " if i == 0 else "... ") + line for i, line in enumerate(lines))
        self.write(echo + "\n", theme.TEXT_MUTED)
        refresh_namespace(self.namespace, self.scene)
        with api.bind_scene(self.scene):
            result = execute(code, self.namespace, filename="<console>", interactive=True,
                             scene=self.scene, undo_group=True, timeout=default_timeout())
        self.write(result.stdout, theme.TEXT_PRIMARY)
        self.write(result.stderr, theme.TINT_CITRINE)
        if result.has_value:
            try:
                text = repr(result.value)
            except Exception as exc:
                text = f"<repr failed: {exc}>"
            self.write(text + "\n", theme.TEXT_PRIMARY)
        if result.error:
            self.write(result.error, theme.STATUS_ERROR)
        self.status.setText("Error" if not result.ok else f"Done in {result.elapsed * 1000.0:.1f} ms")
        self.last_result = result
        self._save_history()
        self.executed.emit(result)
        return result
