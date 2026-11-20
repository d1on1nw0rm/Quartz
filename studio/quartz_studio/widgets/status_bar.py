from __future__ import annotations

import re

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QStatusBar, QWidget

from quartz_studio import theme
from quartz_studio.scene import get_scene

__all__ = ["StatusBar", "MODE_NAMES", "TOOL_NAMES", "TOOL_HINTS", "MODELING_HINT", "MODE_HINTS", "status_texts",
           "modeling_hint", "tool_hint", "tool_name", "selection_text"]

MODE_NAMES = {"points": "Points", "edges": "Edges", "polygons": "Polygons", "model": "Model"}
TOOL_NAMES = {"select": "Brush Selection", "select_loop": "Loop Selection",
              "select_ring": "Ring Selection", "select_pattern": "Pattern Selection",
              "select_fill": "Fill Selection", "select_phong": "Phong Angle Selection",
              "move": "Move", "rotate": "Rotate", "scale": "Scale",
              "pen": "Polygon Pen", "line_pen": "Pen", "other": "Other"}

SEP = " · "

TOOL_HINTS: dict[tuple[str, str], str] = {
    ("select", "model"): "Paint over an object to select it" + SEP + "Ctrl deselects" + SEP
                         + "Shift+wheel sizes the brush",
    ("select", "components"): "Paint to select" + SEP + "Shift adds" + SEP + "Ctrl removes" + SEP
                              + "Shift+wheel sizes the brush",
    ("select_loop", "any"): "Click an edge to select its loop" + SEP + "Shift adds" + SEP
                            + "Ctrl removes",
    ("select_ring", "any"): "Click an edge to select its ring" + SEP + "Shift adds" + SEP
                            + "Ctrl removes",
    ("select_pattern", "any"): "Click an edge to select a pattern along its loop" + SEP + "Shift adds"
                               + SEP + "Ctrl removes",
    ("select_fill", "any"): "Click a polygon to fill up to the selected edges" + SEP + "Ctrl removes",
    ("select_phong", "any"): "Click a polygon to select its smooth area" + SEP + "Shift adds" + SEP
                             + "Ctrl removes",
    ("move", "model"): "Drag to move" + SEP + "Hold Ctrl to copy" + SEP + "Esc cancels",
    ("move", "components"): "Drag to move" + SEP + "Hold Ctrl to extrude" + SEP + "Esc cancels",
    ("rotate", "any"): "Drag to rotate" + SEP + "Shift snaps to 5°" + SEP + "Esc cancels",
    ("scale", "any"): "Drag to scale" + SEP + "Shift snaps to 0.1" + SEP + "Esc cancels",
    ("pen", "any"): "Click to add points" + SEP + "Click the first point to close" + SEP
                    + "Enter finishes",
    ("line_pen", "any"): "Click to add points" + SEP + "Right click or Enter ends the line",
}
MODELING_HINT = "Drag in the viewport" + SEP + "Esc or right click cancels"

MODE_HINTS: dict[tuple[str, str], str] = {
    ("trunk", "edges"): "Drag sideways to change Thickness" + SEP + "Apply skins the Line" + SEP
                        + "Esc cancels",
    ("trunk", "points"): "Click to select points" + SEP + "Drag sideways to scale their thickness"
                         + SEP + "Esc cancels",
}


APPLIED_HINT = "Applied when chosen" + SEP + "Apply Again in the tool panel repeats it"
PANEL_HINT = "Set the options in the tool panel" + SEP + "Apply runs the tool"


def modeling_hint(spec) -> str:
    if not spec.interactive:
        return APPLIED_HINT
    extra = spec.extra or {}
    pick = str(extra.get("pick", ""))
    label = None
    if spec.drag_param:
        param = spec.param(spec.drag_param)
        label = param.label if param is not None else spec.drag_param
    if pick == "line":
        return "Drag a line across the model" + SEP + "Esc cancels"
    if spec.param("edge_a") is not None and spec.param("edge_b") is not None:
        return "Click two edges, or drag from one to the other" + SEP + "Esc cancels"
    if pick == "edge":
        if extra.get("edge_offset_param"):
            return "Click or drag on an edge" + SEP + "Esc cancels"
        if label:
            return "Click an edge to apply" + SEP + f"Drag to change {label}" + SEP + "Esc cancels"
        return "Click an edge to apply"
    if pick == "point":
        if spec.param("target") is not None:
            return "Click a point to apply"
        return "Click to set the plane origin"
    if pick == "plane":
        return "Click to place the plane"
    if label:
        return f"Drag sideways to change {label}" + SEP + "Esc cancels"
    return PANEL_HINT


def _modeling_spec(tool: str):
    if tool in TOOL_NAMES:
        return None
    try:
        from quartz_studio.modeling import get_tool
        return get_tool(tool)
    except (ImportError, KeyError):
        return None


def tool_name(tool: str) -> str:
    if tool in TOOL_NAMES:
        return TOOL_NAMES[tool]
    spec = _modeling_spec(tool)
    return spec.name if spec is not None else tool


_CLASSIC_NAMES = {"snap": "Shift", "extrude": "Ctrl", "add": "Shift", "remove": "Ctrl",
                  "cancel": "Esc", "confirm": "Enter"}
_KEY_NAMES = {"Escape": "Esc", "Return": "Enter"}
_MOD_NAMES = {"shift": "Shift", "ctrl": "Ctrl", "alt": "Alt"}
_PHRASES = (
    ("Ctrl+click deselects", "remove", "{}+click deselects"),
    ("Ctrl deselects", "remove", "{} deselects"),
    ("Ctrl removes", "remove", "{} removes"),
    ("Shift adds", "add", "{} adds"),
    ("Shift snaps", "snap", "{} snaps"),
    ("Hold Ctrl to extrude", "extrude", "Hold {} to extrude"),
    ("Hold Ctrl to copy", "extrude", "Hold {} to copy"),
    ("Esc or right click cancels", "cancel", "{} or right click cancels"),
    ("Esc cancels", "cancel", "{} cancels"),
    ("Enter finishes", "confirm", "{} finishes"),
    ("or Enter ends the line", "confirm", "or {} ends the line"),
)
_PHRASE_RE = re.compile("|".join(re.escape(old) for old, _role, _new in _PHRASES))
_PHRASE_MAP = {old: (role, new) for old, role, new in _PHRASES}


def _gesture_mods(controls, op: str) -> str | None:
    for gesture in controls.active().mouse:
        if (gesture.get("button") == "left" and gesture.get("op") == op
                and not gesture.get("double") and not gesture.get("key")):
            mods = [_MOD_NAMES.get(m, str(m).title()) for m in gesture.get("mods") or ()]
            return "+".join(mods) if mods else None
    return None


def _modal_name(controls, key: str) -> str | None:
    keys = controls.active().modal.get(key) or ()
    if not keys:
        return None
    first = str(keys[0])
    return _KEY_NAMES.get(first, first)


def _control_names() -> dict[str, str]:
    from quartz_studio import controls

    names = dict(_CLASSIC_NAMES)
    for role in ("snap", "extrude"):
        names[role] = controls.modifier_name(role) or names[role]
    for op in ("add", "remove"):
        names[op] = _gesture_mods(controls, op) or names[op]
    for key in ("cancel", "confirm"):
        names[key] = _modal_name(controls, key) or names[key]
    return names


def _localise(text: str) -> str:
    if not text or not _PHRASE_RE.search(text):
        return text
    names = _control_names()
    if names == _CLASSIC_NAMES:
        return text

    def swap(match: re.Match) -> str:
        role, new = _PHRASE_MAP[match.group(0)]
        return new.format(names[role])

    return _PHRASE_RE.sub(swap, text)


def _raw_hint(tool: str, mode: str) -> str:
    if (tool, mode) in MODE_HINTS:
        return MODE_HINTS[(tool, mode)]
    kind = "model" if mode == "model" else "components"
    for key in ((tool, kind), (tool, "any")):
        if key in TOOL_HINTS:
            return TOOL_HINTS[key]
    spec = _modeling_spec(tool)
    if spec is not None:
        return modeling_hint(spec)
    return ""


def tool_hint(tool: str, mode: str) -> str:
    return _localise(_raw_hint(tool, mode))


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def selection_text(scene) -> str:
    obj = scene.active
    objects = len(scene.selected_objects()) if hasattr(scene, "selected_objects") else int(
        obj is not None and scene.object_selected)
    if obj is None:
        points = edges = polygons = 0
    else:
        points = len(scene.selected_points)
        edges = len(scene.selected_edges)
        polygons = len(scene.selected_polygons)
    return SEP.join((_count(objects, "object"), _count(points, "point"), _count(edges, "edge"),
                     _count(polygons, "polygon")))


def status_texts(scene) -> tuple[str, str, str]:
    mode = MODE_NAMES.get(scene.mode, scene.mode)
    left = f"Mode: {mode}{SEP}Tool: {tool_name(scene.tool)}"
    return left, tool_hint(scene.tool, scene.mode), selection_text(scene)


class ElidedLabel(QLabel):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""

    def setText(self, text: str) -> None:
        self._full = text
        self._fit()

    def text(self) -> str:
        return self._full

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def _fit(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(0, self.width()))
        if shown != super().text():
            super().setText(shown)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()


class StatusBar(QStatusBar):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qsStatusBar")
        self.setSizeGripEnabled(False)
        self.setFixedHeight(theme.STATUS_BAR_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body = QWidget(self)
        self.body.setObjectName("qsStatusBody")
        lay = QHBoxLayout(self.body)
        lay.setContentsMargins(theme.SPACE_3, 0, theme.SPACE_3, 0)
        lay.setSpacing(theme.SPACE_3)
        self.mode_label = self._label("qsStatusMode", Qt.AlignmentFlag.AlignLeft)
        self.hint_label = self._label("qsStatusHint", Qt.AlignmentFlag.AlignHCenter)
        self.selection_label = self._label("qsStatusSelection", Qt.AlignmentFlag.AlignRight)
        for label in (self.mode_label, self.hint_label, self.selection_label):
            lay.addWidget(label, 1)
        self.addWidget(self.body, 1)
        self.scene = get_scene()
        for signal in (self.scene.changed, self.scene.selectionChanged, self.scene.objectsChanged):
            signal.connect(self.refresh)
        self.scene.modeChanged.connect(self.refresh)
        self.scene.toolChanged.connect(self.refresh)
        from quartz_studio import controls

        controls.hub().profileChanged.connect(self.refresh)
        self.refresh()

    def _label(self, name: str, align: Qt.AlignmentFlag) -> QLabel:
        label = ElidedLabel(self.body)
        label.setObjectName(name)
        label.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

    def refresh(self, *_args) -> None:
        left, hint, selection = status_texts(self.scene)
        for label, text in ((self.mode_label, left), (self.hint_label, hint),
                            (self.selection_label, selection)):
            if label.text() != text:
                label.setText(text)
                label.setToolTip(text)

    def mode_text(self) -> str:
        return self.mode_label.text()

    def hint_text(self) -> str:
        return self.hint_label.text()

    def selection_text(self) -> str:
        return self.selection_label.text()
