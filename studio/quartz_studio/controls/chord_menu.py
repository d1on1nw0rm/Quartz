from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication

from quartz_studio import icons
from quartz_studio.widgets.menu_bar import StudioMenu

__all__ = ["ChordMenu", "rows", "build", "present", "PREF_KEY", "SHOW_DELAY_MS", "CURSOR_GAP"]

PREF_KEY = "controls.chord_menu"
SHOW_DELAY_MS = 200
CURSOR_GAP = 8


def enabled_pref() -> bool:
    from quartz_studio import prefs

    return bool(prefs.get(PREF_KEY, True))


def _mode() -> str | None:
    try:
        from quartz_studio.scene import get_scene

        return get_scene().mode
    except Exception:
        return None


def _tool_spec(tool_id: str):
    try:
        from quartz_studio.modeling import registry as tool_registry

        return tool_registry.get_tool(tool_id)
    except Exception:
        pass
    try:
        from quartz_studio.modeling import select_tools

        return select_tools.get(tool_id)
    except Exception:
        return None


def applies(aid: str, action) -> bool:
    if action.available is not None:
        try:
            if not action.available():
                return False
        except Exception:
            return False
    if not aid.startswith("tool."):
        return True
    mode = _mode()
    spec = _tool_spec(aid[5:])
    modes = getattr(spec, "modes", None)
    return mode is None or modes is None or mode in modes


def icon_name(aid: str) -> str | None:
    if not aid.startswith("tool."):
        return None
    spec = _tool_spec(aid[5:])
    for name in (getattr(spec, "icon", None), aid[5:]):
        if name and icons.has(name):
            return name
    return None


def rows(index, prefix: str, scopes) -> list[tuple[str, str, str, str, bool]]:
    found: dict[str, str] = {}
    for scope in scopes:
        for chord, aid in index.chords.get(scope, {}).items():
            first, second = chord.split("~", 1)
            if first == prefix and second not in found:
                found[second] = aid
    order = {aid: i for i, aid in enumerate(index.registry)}
    out = []
    for second, aid in sorted(found.items(), key=lambda kv: order.get(kv[1], len(order))):
        action = index.registry.get(aid)
        if action is not None:
            out.append((aid, action.label, action.category, second, applies(aid, action)))
    return out


class ChordMenu(StudioMenu):

    def __init__(self, parent, prefix: str, items, pick: Callable[[str], object]) -> None:
        super().__init__("", parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prefix = prefix
        self.items = list(items)
        previous = None
        for aid, label, category, second, enabled in self.items:
            if previous is not None and category != previous:
                self.addSeparator()
            previous = category
            act = self.add_item(label, second, icon_name(aid), enabled)
            self._handlers[act] = lambda a=aid: pick(a)

    def keys(self) -> dict[str, str]:
        return {second: aid for aid, _label, _cat, second, _en in self.items}


def build(parent, index, prefix: str, scopes, pick: Callable[[str], object]) -> ChordMenu | None:
    items = rows(index, prefix, scopes)
    if not items:
        return None
    return ChordMenu(parent, prefix, items, pick)


def present(menu: ChordMenu, cursor: QPoint) -> None:
    menu.ensurePolished()
    hint = menu.sizeHint()
    screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
    area = screen.availableGeometry() if screen is not None else None
    if area is not None:
        hint = hint.boundedTo(area.size())
    menu.resize(hint)
    size = menu.size()
    x = cursor.x() + CURSOR_GAP
    y = cursor.y() + CURSOR_GAP
    if area is not None:
        if x + size.width() > area.right() + 1:
            x = cursor.x() - CURSOR_GAP - size.width()
        if y + size.height() > area.bottom() + 1:
            y = area.bottom() + 1 - size.height()
        x = max(area.left(), min(x, area.right() + 1 - size.width()))
        y = max(area.top(), y)
    menu.move(x, y)
    menu.show()
