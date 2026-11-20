from __future__ import annotations

import math
import re

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quartz_studio import theme
from quartz_studio.scene import get_scene
from quartz_studio.widgets.common import IconButton, not_implemented, populate_menu

__all__ = [
    "CoordinatesManager",
    "CoordField",
    "COORDINATE_COLUMNS",
    "COLUMN_TITLES",
    "format_number",
    "format_value",
    "parse_value",
]

COORDINATE_COLUMNS = ("0 cm", "0 °", "0 cm")
COLUMN_TITLES = ("Position", "Rotation", "Size")
COLUMN_UNITS = ("cm", "°", "cm")
AXES = ("X", "Y", "Z")

RESET_W = 128
HEADER_H = 24
HEADER_PAD = 10
TITLE_H = 14
ROW_H = 20
AXIS_W = 14
GRID_GAP = 2
GRID_COLUMN_GAP = 6
LAYOUT_GAP = 4
RESET_H = 20
MIN_W = 256
AXIS_COLORS = (theme.AXIS_X, theme.AXIS_Y, theme.AXIS_Z)
MIN_H = theme.COORDINATES_H

STATE_NONE = "none"
STATE_OBJECT = "object"
STATE_COMPONENTS = "components"


def _style_header_font(label: QLabel) -> None:
    font = label.font()
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, theme.HEADER_LETTER_SPACING)
    label.setFont(font)


DECIMALS = 3

LENGTH_UNITS = {"cm": 1.0, "mm": 0.1, "m": 100.0, "km": 100000.0}
ANGLE_UNITS = {"°": 1.0, "º": 1.0, "deg": 1.0, "degree": 1.0, "degrees": 1.0}
UNITS_BY_FIELD = {"cm": LENGTH_UNITS, "°": ANGLE_UNITS}

MAX_EXPRESSION_LEN = 120
MAX_NESTING = 32

_TOKEN_RE = re.compile(
    r"(?P<space>\s+)"
    r"|(?P<number>\d+(?:[.,]\d*)?|[.,]\d+)"
    r"|(?P<unit>[^\W\d_]+|°)"
    r"|(?P<op>[-+*/()×÷−])"
)
_OPERATOR_ALIASES = {"×": "*", "÷": "/", "−": "-"}


def format_number(value: float, decimals: int = DECIMALS) -> str:
    value = float(value)
    if not math.isfinite(value):
        return "0"
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", "", "-"):
        text = "0"
    return text


def format_value(value: float, unit: str) -> str:
    number = format_number(value)
    return f"{number} {unit}" if unit else number


class _ParseError(ValueError):
    pass


def _tokenize(text: str, units: dict[str, float]) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise _ParseError(f"unexpected {text[pos]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "space":
            continue
        raw = m.group(kind)
        if kind == "number":
            tokens.append(("num", float(raw.replace(",", "."))))
        elif kind == "unit":
            factor = units.get(raw.lower())
            if factor is None:
                raise _ParseError(f"unknown unit {raw!r}")
            tokens.append(("unit", factor))
        else:
            tokens.append(("op", _OPERATOR_ALIASES.get(raw, raw)))
    return tokens


class _Parser:

    def __init__(self, tokens: list[tuple[str, object]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> tuple[str, object] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _take_op(self, *ops: str) -> str | None:
        tok = self._peek()
        if tok is not None and tok[0] == "op" and tok[1] in ops:
            self.pos += 1
            return str(tok[1])
        return None

    def parse(self) -> float:
        value = self._sum(0)
        if self.pos != len(self.tokens):
            raise _ParseError("trailing input")
        return value

    def _sum(self, depth: int) -> float:
        value = self._product(depth)
        while (op := self._take_op("+", "-")) is not None:
            rhs = self._product(depth)
            value = value + rhs if op == "+" else value - rhs
        return value

    def _product(self, depth: int) -> float:
        value = self._unary(depth)
        while (op := self._take_op("*", "/")) is not None:
            rhs = self._unary(depth)
            value = value * rhs if op == "*" else value / rhs
        return value

    def _unary(self, depth: int) -> float:
        if depth > MAX_NESTING:
            raise _ParseError("expression nested too deeply")
        op = self._take_op("+", "-")
        if op is not None:
            value = self._unary(depth + 1)
            return -value if op == "-" else value
        return self._atom(depth)

    def _atom(self, depth: int) -> float:
        tok = self._peek()
        if tok is None:
            raise _ParseError("unexpected end")
        if tok[0] == "num":
            self.pos += 1
            value = float(tok[1])
        elif self._take_op("(") is not None:
            value = self._sum(depth + 1)
            if self._take_op(")") is None:
                raise _ParseError("missing ')'")
        else:
            raise _ParseError(f"unexpected token {tok!r}")
        nxt = self._peek()
        if nxt is not None and nxt[0] == "unit":
            self.pos += 1
            value *= float(nxt[1])
        return value


def parse_value(text: str, unit: str = "cm") -> float | None:
    text = (text or "").strip()
    if not text or len(text) > MAX_EXPRESSION_LEN:
        return None
    units = UNITS_BY_FIELD.get(unit, {unit: 1.0} if unit else {})
    try:
        value = _Parser(_tokenize(text, units)).parse()
    except (_ParseError, ZeroDivisionError, OverflowError, ValueError):
        return None
    return value if math.isfinite(value) else None



_SCENE_UNDO_KEYS = (Qt.Key.Key_Z, Qt.Key.Key_Y)


def _is_scene_undo_key(e: QKeyEvent) -> bool:
    mods = e.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
    return mods == Qt.KeyboardModifier.ControlModifier and e.key() in _SCENE_UNDO_KEYS


class CoordField(QLineEdit):

    committed = Signal(float)

    def __init__(self, unit: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.unit = unit
        self._value = 0.0
        self.setObjectName("qsCoordField")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(ROW_H)
        self.setMinimumWidth(40)
        self.editingFinished.connect(self._on_editing_finished)
        self._show()

    def value(self) -> float:
        return self._value

    def is_editing(self) -> bool:
        return self.hasFocus() and self.isModified()

    def set_value(self, value: float, *, discard_edit: bool = False) -> None:
        self._value = float(value)
        if discard_edit or not self.is_editing():
            self._show()

    def revert(self) -> None:
        self._show()

    def _show(self) -> None:
        text = format_value(self._value, self.unit)
        if self.text() != text:
            self.setText(text)
        else:
            self.setModified(False)

    def _on_editing_finished(self) -> None:
        if not self.isModified():
            return
        value = parse_value(self.text(), self.unit)
        self.setModified(False)
        if value is not None and self.isEnabled() and not self.isReadOnly():
            self.committed.emit(value)
        self._show()

    def event(self, e: QEvent) -> bool:
        if (e.type() == QEvent.Type.ShortcutOverride
                and _is_scene_undo_key(e) and not self.isModified()):
            e.ignore()
            return False
        return super().event(e)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        key = e.key()
        if key == Qt.Key.Key_Escape:
            self.revert()
            self.clearFocus()
            e.accept()
            return
        super().keyPressEvent(e)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.selectAll()


class CoordHeader(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsCoordHeaderRow")
        self.setFixedHeight(HEADER_H)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(0, self.height() - 1, self.width(), 1, QColor(theme.HAIRLINE))
        p.end()


class CoordinatesManager(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsCoordinatesManager")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        axis_rules = "".join(
            f'QLabel#qsAxisLabel[axis="{a.lower()}"] {{ color: {c}; }}'
            f'QLabel#qsAxisLabel[axis="{a.lower()}"]:disabled'
            f" {{ color: {theme.mix(c, theme.SURFACE_CARD, 0.5)}; }}"
            for a, c in zip(AXES, AXIS_COLORS))
        self.setStyleSheet(
            f"QPushButton#qsResetTransform {{ background: {theme.SURFACE_RAISED};"
            f" color: {theme.TEXT_PRIMARY}; border: 1px solid {theme.HAIRLINE};"
            f" border-radius: {theme.CONTROL_RADIUS}px; padding: 0px {theme.SPACE_3}px; }}"
            f"QPushButton#qsResetTransform:hover {{ background: {theme.SURFACE_HOVER};"
            f" border-color: {theme.HAIRLINE_STRONG}; }}"
            f"QPushButton#qsResetTransform:pressed {{ background: {theme.SURFACE_PRESSED}; }}"
            f"QPushButton#qsResetTransform:disabled {{ background: {theme.SURFACE_CARD};"
            f" border-color: {theme.HAIRLINE}; color: {theme.TEXT_MUTED}; }}"
            f"QLineEdit#qsCoordField:disabled {{ color: {theme.TEXT_SECONDARY};"
            f" background: {theme.SURFACE_CARD}; border: 1px solid {theme.HAIRLINE}; }}"
            f"QLineEdit#qsCoordField {{ min-height: 14px; padding: 2px 6px; }}"
            f"QLabel#qsAxisLabel {{ font-weight: 600; }}"
            + axis_rules +
            f"QLabel#qsCoordHeader {{ color: {theme.TEXT_SECONDARY}; font-weight: 600;"
            f" font-size: {theme.FONT_GROUP_POINT_SIZE}pt; padding-left: {HEADER_PAD}px; }}"
            f"QLabel#qsCoordTitle {{ color: {theme.TEXT_SECONDARY};"
            f" font-size: {theme.FONT_SMALL_POINT_SIZE}pt; }}"
            f"QLabel#qsCoordTitle:disabled {{ color: {theme.TEXT_MUTED}; }}"
        )
        self.setFixedHeight(theme.COORDINATES_H)
        self.setMinimumWidth(MIN_W)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._scene = get_scene()
        self._state = STATE_NONE
        self._target: tuple = (STATE_NONE,)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.CARD_PADDING, theme.SPACE_1, theme.CARD_PADDING,
                               theme.CARD_PADDING)
        lay.setSpacing(LAYOUT_GAP)

        header = CoordHeader(self)
        self.header = header
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        self.header_label = QLabel("Coordinates", header)
        self.header_label.setObjectName("qsCoordHeader")
        _style_header_font(self.header_label)
        hl.addWidget(self.header_label)
        hl.addStretch(1)
        self.reset_button = QPushButton("Reset Transformation", header)
        self.reset_button.setObjectName("qsResetTransform")
        self.reset_button.setFixedSize(
            max(RESET_W, theme.snap_px_up(self.reset_button.sizeHint().width())), RESET_H)
        self.reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.reset_button.setToolTip("Reset Object Position, Rotation and Scale")
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self._reset_transform)
        hl.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(header)

        grid_host = QWidget(self)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(GRID_COLUMN_GAP)
        grid.setVerticalSpacing(GRID_GAP)
        grid.setColumnMinimumWidth(0, AXIS_W)
        self.column_titles: list[QLabel] = []
        for c, title in enumerate(COLUMN_TITLES):
            label = QLabel(title, grid_host)
            label.setObjectName("qsCoordTitle")
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            label.setFixedHeight(TITLE_H)
            _style_header_font(label)
            label.setEnabled(False)
            grid.addWidget(label, 0, c + 1)
            self.column_titles.append(label)
        self.axis_labels: list[QLabel] = []
        self.fields: list[list[CoordField]] = []
        for r, axis in enumerate(AXES):
            label = QLabel(axis, grid_host)
            label.setObjectName("qsAxisLabel")
            label.setProperty("axis", axis.lower())
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedWidth(AXIS_W)
            label.setEnabled(False)
            grid.addWidget(label, r + 1, 0)
            self.axis_labels.append(label)
            row_fields: list[CoordField] = []
            for c, unit in enumerate(COLUMN_UNITS):
                field = CoordField(unit, grid_host)
                field.setEnabled(False)
                field.setToolTip(f"{COLUMN_TITLES[c]} {axis}")
                field.committed.connect(
                    lambda value, a=r, col=c: self._commit(a, col, value))
                grid.addWidget(field, r + 1, c + 1)
                row_fields.append(field)
            self.fields.append(row_fields)
        for c in range(1, 4):
            grid.setColumnStretch(c, 1)
        lay.addWidget(grid_host)

        self._scene.changed.connect(self.refresh)
        self._scene.selectionChanged.connect(self.refresh)
        self._scene.modeChanged.connect(self.refresh)
        self._scene.objectsChanged.connect(self.refresh)
        self.refresh()

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(max(hint.width(), MIN_W), MIN_H)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(max(hint.width(), MIN_W), MIN_H)

    def state(self) -> str:
        return self._state

    def field(self, column: int, axis: int) -> CoordField:
        return self.fields[axis][column]

    def _compute_state(self) -> str:
        scene = self._scene
        if scene.active is None or not scene.has_selection():
            return STATE_NONE
        return STATE_OBJECT if scene.mode == "model" else STATE_COMPONENTS

    def _target_of(self, state: str) -> tuple:
        scene = self._scene
        if state == STATE_OBJECT:
            return (state, scene.active)
        if state == STATE_COMPONENTS:
            selected = getattr(scene, f"selected_{scene.mode}", set())
            return (state, scene.active, scene.mode, frozenset(selected))
        return (state,)

    def refresh(self, *_args) -> None:
        scene = self._scene
        state = self._compute_state()
        target = self._target_of(state)
        retarget = target != self._target
        self._state = state
        self._target = target
        obj = scene.active
        zeros = (0.0, 0.0, 0.0)
        if state == STATE_OBJECT:
            columns = (obj.position, obj.rotation, obj.size())
            editable = (True, True, True)
        elif state == STATE_COMPONENTS:
            center, size = self._component_values()
            columns = (zeros if center is None else center, zeros,
                       zeros if size is None else size)
            editable = (True, False, False)
        else:
            columns = (zeros, zeros, zeros)
            editable = (False, False, False)

        for c, values in enumerate(columns):
            for a in range(3):
                field = self.fields[a][c]
                field.set_value(float(values[a]), discard_edit=retarget)
                field.setEnabled(editable[c])

        active = state != STATE_NONE
        for label in (*self.axis_labels, *self.column_titles):
            label.setEnabled(active)
        obj = self._scene.active
        changed = state == STATE_OBJECT and obj is not None and (
            any(float(v) != 0.0 for v in obj.position)
            or any(float(v) != 0.0 for v in obj.rotation)
            or any(float(v) != 1.0 for v in obj.scale))
        self.reset_button.setEnabled(bool(changed))

    def _component_values(self) -> tuple:
        scene = self._scene
        try:
            return scene.selection_center(), scene.selection_size()
        except (IndexError, ValueError):
            return None, None

    def _commit(self, axis: int, column: int, value: float) -> None:
        scene = self._scene
        state = self._compute_state()
        if self._target_of(state) != self._target:
            state = STATE_NONE
        if state == STATE_OBJECT:
            if column == 0:
                scene.set_object_position(axis, value)
            elif column == 1:
                scene.set_object_rotation(axis, value)
            else:
                scene.set_object_size(axis, value)
        elif state == STATE_COMPONENTS and column == 0:
            scene.set_selection_center(axis, value)
        self.refresh()

    def _reset_transform(self) -> None:
        if self._compute_state() == STATE_OBJECT:
            self._scene.reset_transform()
        self.refresh()
