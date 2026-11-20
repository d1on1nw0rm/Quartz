from __future__ import annotations

import math

from PySide6.QtGui import QColor, QFont


def mix(fg: str, bg: str, amount: float) -> str:
    a, b = QColor(fg), QColor(bg)
    channels = (round(b.red() + (a.red() - b.red()) * amount),
                round(b.green() + (a.green() - b.green()) * amount),
                round(b.blue() + (a.blue() - b.blue()) * amount))
    return "#" + "".join(f"{c:02x}" for c in channels)


def argb(color: str, alpha: int) -> str:
    c = QColor(color)
    return f"#{alpha:02x}{c.red():02x}{c.green():02x}{c.blue():02x}"


def qss_rgba(color: str) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"


THEME_NAME = "Crystal"

SURFACE_BACKDROP = "#0f1115"
SURFACE_CARD = "#171a21"
SURFACE_RAISED = "#1f2430"
SURFACE_HOVER = "#262c3a"
SURFACE_PRESSED = "#0a0c10"
SURFACE_FIELD = "#0c0e12"
SURFACE_FIELD_HOVER = "#11141a"
SURFACE_MENU = "#12151b"
HAIRLINE = "#2a3040"
HAIRLINE_STRONG = "#3a4358"

TEXT_PRIMARY = "#e7eaf0"
TEXT_SECONDARY = "#a3abbb"
TEXT_MUTED = "#6b7385"

ACCENT = "#5ee6c8"
ACCENT_HOVER = "#7cf0d6"
ACCENT_PRESSED = "#3fc7aa"
ACCENT_ON = "#06231d"
ACCENT_TINT_AMOUNT = 0.18
ACCENT_TINT_HOVER_AMOUNT = 0.26
ACCENT_ALPHA = round(255 * ACCENT_TINT_AMOUNT)
ACCENT_TINT = mix(ACCENT, SURFACE_CARD, ACCENT_TINT_AMOUNT)
ACCENT_TINT_HOVER = mix(ACCENT, SURFACE_CARD, ACCENT_TINT_HOVER_AMOUNT)
ACCENT_TINT_MENU = mix(ACCENT, SURFACE_MENU, ACCENT_TINT_AMOUNT)
ACCENT_TINT_BACKDROP = mix(ACCENT, SURFACE_BACKDROP, ACCENT_TINT_AMOUNT)
ACCENT_TINT_ARGB = argb(ACCENT, ACCENT_ALPHA)
FOCUS_RING = ACCENT

TINT_MINT = "#5ee6c8"
TINT_CITRINE = "#ffb53d"
TINT_AMETHYST = "#9d8cff"
TINT_ROSE = "#ff7aa8"

ICON_STROKE = "#cfd5e1"
ICON_SPLINE = TINT_ROSE
ICON_MESH = TINT_MINT
ICON_TOOL = TINT_CITRINE
ICON_COMMAND = TINT_MINT
FAMILY_TINTS = {
    "splines": ICON_SPLINE,
    "meshes": ICON_MESH,
    "generators": TINT_AMETHYST,
    "tools": ICON_TOOL,
    "commands": ICON_COMMAND,
}

SELECT_FRONT = "#ffb53d"
SELECT_FRONT_DARK = "#8a5a12"
SELECT_FRONT_SOFT = "#ffd98a"
SELECT_BACK = "#9d8cff"
VIEWPORT_TOP = "#1a1e27"
VIEWPORT_BOTTOM = "#101318"
HORIZON = "#343c50"
WIRE = "#cfd5e1"
POINT_FILL = "#cfd5e1"
POINT_BORDER = "#0c0e12"
GIZMO_HOVER = "#ffd98a"
SHADOW = argb("#0c0e12", 170)
POLY_OUTLINE = argb("#0c0e12", 150)
OVERLAY_BG = argb(SURFACE_MENU, 217)
DOCK_ALPHA = 235
DOCK_BG = argb(SURFACE_CARD, DOCK_ALPHA)
STATUS_OK = "#5fd97a"
STATUS_ERROR = "#ff5d6c"

BG_TITLE = SURFACE_MENU
BG_WINDOW = SURFACE_BACKDROP
BG_BAR = SURFACE_BACKDROP
BG_PANEL = SURFACE_CARD
BG_PANEL_HEADER = SURFACE_CARD
BG_TAB_ACTIVE = SURFACE_RAISED
BG_FIELD = SURFACE_FIELD
BG_FIELD_DARK = SURFACE_FIELD
BG_FIELD_HOVER = SURFACE_FIELD_HOVER
BG_BUTTON = SURFACE_RAISED
BG_BUTTON_HOVER = SURFACE_HOVER
BG_BUTTON_PRESSED = SURFACE_PRESSED
BG_BUTTON_DISABLED = SURFACE_CARD
BG_MENU = SURFACE_MENU
BG_MENU_HOVER = ACCENT_TINT_MENU
BG_TOOLTIP = SURFACE_MENU
BG_VIEWPORT_TOP = VIEWPORT_TOP
BG_VIEWPORT_BOTTOM = VIEWPORT_BOTTOM
VIEWPORT_LETTERBOX = SURFACE_FIELD
VIEWPORT_BORDER = HAIRLINE
GRID_MINOR = "#1d2230"
GRID_MAJOR = HAIRLINE
BORDER = HAIRLINE
SPLITTER = SURFACE_BACKDROP
SEPARATOR_LINE = HAIRLINE
GROUP_LINE = HAIRLINE

AXIS_X = "#ff5d6c"
AXIS_Y = "#5fd97a"
AXIS_Z = "#5c9dff"

TEXT = TEXT_PRIMARY
TEXT_BRIGHT = "#f5f7fa"
TEXT_DIM = TEXT_SECONDARY
TEXT_DISABLED = TEXT_MUTED
TEXT_MENU_NEW = TEXT_PRIMARY
TEXT_SECTION = TEXT_SECONDARY

ACCENT_BUTTON = ACCENT_TINT
ACCENT_TEXT = ACCENT
ACCENT_UNDERLINE = ACCENT
SLIDER_TRACK = HAIRLINE
SLIDER_FILL = ACCENT_PRESSED
SLIDER_HANDLE = ACCENT

ICON_FG = ICON_STROKE
ICON_DIM = TEXT_MUTED
ICON_PRIMITIVE = ICON_MESH
ICON_GENERATOR = TINT_AMETHYST
ICON_DEFORMER = TINT_AMETHYST
ICON_FIELD = TINT_ROSE
ICON_SPLINE_PEN = TINT_CITRINE
ICON_ACCENT_ORANGE = TINT_CITRINE
ICON_ACCENT_YELLOW = TINT_CITRINE
ICON_CAMERA = ICON_STROKE
ICON_LIGHT = TINT_CITRINE
ICON_SCULPT = TEXT_SECONDARY
ICON_STROKE_W = 1.6


FRAME_SCALE = 1920 / 1456

FONT_FAMILY = "Segoe UI Variable Text"
FONT_FALLBACKS = ("Segoe UI Variable", "Segoe UI")
FONT_POINT_SIZE = 9
FONT_GROUP_POINT_SIZE = 8
FONT_SMALL_POINT_SIZE = 8
HEADER_LETTER_SPACING = 1.0

SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
WINDOW_MARGIN = SPACE_2
CARD_GAP = SPACE_2
CARD_PADDING = SPACE_2
CARD_RADIUS = 10
CONTROL_RADIUS = 6
DOCK_RADIUS = 12
MENU_RADIUS = 8
ACCENT_BAR_W = 2
FOCUS_RING_W = 1

TOP_BAR_H = 40
APP_MARK = 20
SEGMENT_H = 30
SEGMENT_PAD = 2
SEGMENT_BORDER = 1
CHIP_H = 26
STATUS_BAR_H = 24
CARD_HEADER_H = 28
MENU_ROW_H = 28
MENU_ICON = 16
ROW_H = 24
RAIL_PAD = 6
DOCK_BUTTON = 36
DOCK_ICON = 24
DOCK_PAD = 6
DOCK_H = DOCK_BUTTON + 2 * DOCK_PAD
DOCK_BOTTOM = SPACE_3
DOCK_GAP = SPACE_3
GHOST_BUTTON_H = 24
NAV_BUTTON = 24
HUD_H = 22

TITLE_ROW_H = 28
MENU_BAR_H = 32
COMMAND_BAR_H = TOP_BAR_H
COMMAND_BUTTON = 30
COMMAND_ICON = 18
PALETTE_BUTTON = 36
PALETTE_W = PALETTE_BUTTON + 2 * RAIL_PAD
RAIL_W = PALETTE_W
PALETTE_ICON = 24
SCULPT_BAR_H = 37
SCULPT_BUTTON = 30
SCULPT_ICON = 22
VIEWPORT_MENU_H = 28
PANEL_TAB_H = 24
PANEL_MENU_H = 24
PANEL_ICON = 16
FIELD_H = 22
SPLITTER_W = CARD_GAP
RIGHT_COLUMN_W = 488
OBJECT_MANAGER_H = 385
ATTRIBUTE_MANAGER_H = 475
COORDINATES_H = 120
SPLITTER_BAR = 4
SPLITTER_BAR_INSET = 24
SPLITTER_HOVER = mix(ACCENT, SURFACE_BACKDROP, 0.5)
SPLITTER_DRAG = ACCENT
SEPARATOR_GAP = SPACE_2
BUTTON_RADIUS = CONTROL_RADIUS

WINDOW_MIN_W = 1280
WINDOW_MIN_H = 720

PX_MAIN = (1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 72, 96, 128, 256, 512, 1024)
PX_BELOW_128 = (2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 88, 96, 112, 120)
_PX_TERMS = tuple(v for v in PX_MAIN if v != 1)
_PX_PAIRS = frozenset(s for a in _PX_TERMS for b in _PX_TERMS for s in (a + b, a - b) if s >= 128)


def allowed_px(v: float) -> bool:
    a = abs(v)
    if a != int(a):
        return False
    a = int(a)
    if a in (0, 1):
        return True
    if a < 128:
        return a in PX_BELOW_128
    return a % 16 == 0 or a in _PX_PAIRS


def _nearest_allowed(a: float) -> int:
    base = int(a)
    candidates = [n for n in range(max(2, base - 32), base + 34) if allowed_px(n)]
    return min(candidates, key=lambda n: (abs(n - a), n))


def snap_px(v: float) -> int:
    if allowed_px(v):
        return int(v)
    sign = -1 if v < 0 else 1
    a = abs(v)
    if a < 2:
        return sign * (1 if a <= 1.5 else 2)
    main = min(_PX_TERMS, key=lambda n: (abs(n - a), n))
    if abs(main - a) <= 0.12 * a:
        return sign * main
    return sign * _nearest_allowed(a)


def snap_px_up(v: float) -> int:
    if v <= 0:
        return 0
    n = max(2, math.ceil(v))
    if n % 2:
        n += 1
    while not allowed_px(n):
        n += 2
    return n


def install_font_substitutions() -> None:
    QFont.insertSubstitutions(FONT_FAMILY, list(FONT_FALLBACKS))


install_font_substitutions()


def ref(v: float) -> int:
    return round(v * FRAME_SCALE)


def stylesheet(assets: dict[str, str] | None = None) -> str:
    return _base_qss() + (_asset_qss(assets) if assets else "")


def _asset_qss(a: dict[str, str]) -> str:
    rules = []
    if "chevron_down" in a:
        rules.append(f"QComboBox::down-arrow {{ image: url({a['chevron_down']}); }}")
    if "chevron_down_disabled" in a:
        rules.append(f"QComboBox::down-arrow:disabled {{ image: url({a['chevron_down_disabled']}); }}")
    if "chevron_right" in a:
        rules.append(f"QMenu::right-arrow {{ image: url({a['chevron_right']}); }}")
    if "check" in a:
        rules.append(f"QCheckBox::indicator:checked {{ image: url({a['check']}); }}")
        rules.append(f"QMenu::indicator:checked {{ image: url({a['check']}); }}")
    return "\n".join(rules) + "\n"


def _base_qss() -> str:
    checked_disabled = mix(ACCENT, SURFACE_CARD, 0.4)
    view_hover = qss_rgba(OVERLAY_BG)
    view_open = qss_rgba(ACCENT_TINT_ARGB)
    tab_h = CARD_HEADER_H - 2
    chip_h = CHIP_H - 4
    field_h = FIELD_H - 4
    button_h = FIELD_H - 6
    pill = SEGMENT_H // 2 - 2
    return f"""
* {{
    font-family: "{FONT_FAMILY}";
    font-size: {FONT_POINT_SIZE}pt;
    color: {TEXT_PRIMARY};
    outline: 0;
}}
QMainWindow, QWidget#qsCentral {{
    background: {SURFACE_BACKDROP};
}}
QDialog, QMessageBox {{
    background: {SURFACE_CARD};
}}
QToolTip {{
    background: {SURFACE_MENU};
    color: {TEXT_PRIMARY};
    border: 1px solid {HAIRLINE};
    padding: {SPACE_1}px {SPACE_2}px;
}}

QMenuBar {{
    background: {SURFACE_BACKDROP};
    border: none;
    spacing: 0px;
    padding: 0px 2px;
}}
QMenuBar::item {{
    background: transparent;
    color: {TEXT_SECONDARY};
    padding: 4px 10px;
    margin: 0px;
    border-radius: {CONTROL_RADIUS}px;
}}
QMenuBar::item:selected, QMenuBar::item:pressed {{
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
}}
QMenuBar::item:disabled {{
    color: {TEXT_MUTED};
}}

QMenu {{
    background: {SURFACE_MENU};
    border: 1px solid {HAIRLINE};
    border-radius: {MENU_RADIUS}px;
    padding: {SPACE_1}px {SPACE_1}px;
}}
QMenu::item {{
    background: transparent;
    color: {TEXT_PRIMARY};
    min-height: {MENU_ROW_H}px;
    padding: 0px {SPACE_3 * 2}px 0px {MENU_ROW_H + SPACE_1}px;
    margin: 0px;
    border-radius: {CONTROL_RADIUS}px;
}}
QMenu::item:selected {{
    background: {ACCENT_TINT_MENU};
    color: {TEXT_BRIGHT};
}}
QMenu::item:disabled {{
    color: {TEXT_MUTED};
    background: transparent;
}}
QMenu::separator {{
    height: 1px;
    background: {HAIRLINE};
    margin: {SPACE_1}px {SPACE_2}px;
}}
QMenu::icon {{
    padding-left: {SPACE_2}px;
}}
QMenu::right-arrow {{
    width: 10px;
    height: 10px;
    padding-right: {SPACE_2}px;
}}
QMenu::indicator {{
    width: 14px;
    height: 14px;
    margin-left: {SPACE_2 - 1}px;
    border-radius: 4px;
}}
QMenu::indicator:checked {{
    background: {ACCENT};
}}
QLabel#qsMenuSection {{
    color: {TEXT_SECONDARY};
    font-weight: 600;
    font-size: {FONT_GROUP_POINT_SIZE}pt;
    padding: {SPACE_2}px {SPACE_3}px {SPACE_1 - 2}px {SPACE_3}px;
    background: transparent;
}}

QToolButton {{
    background: transparent;
    border: none;
    border-radius: {CONTROL_RADIUS}px;
    padding: 0px;
    color: {TEXT_PRIMARY};
}}
QToolButton:hover {{
    background: {SURFACE_RAISED};
}}
QToolButton:pressed {{
    background: {SURFACE_PRESSED};
}}
QToolButton:checked {{
    background: {ACCENT_TINT};
    color: {ACCENT};
}}
QToolButton:checked:hover {{
    background: {ACCENT_TINT_HOVER};
}}
QToolButton:disabled {{
    background: transparent;
    color: {TEXT_MUTED};
}}
QToolButton:focus {{
    border: {FOCUS_RING_W}px solid {FOCUS_RING};
}}
QToolButton::menu-indicator {{
    image: none;
    width: 0px;
}}
QFrame#qsSegment {{
    background: transparent;
    border: none;
}}
QFrame#qsSegment QToolButton#qsIconButton {{
    background: transparent;
}}
QFrame#qsSegment QToolButton#qsIconButton:hover {{
    background: {SURFACE_RAISED};
}}
QFrame#qsSegment QToolButton#qsIconButton:pressed {{
    background: {SURFACE_PRESSED};
}}
QFrame#qsSegment QToolButton#qsIconButton:checked {{
    background: {ACCENT_TINT};
}}
QFrame#qsSegment QToolButton#qsIconButton:checked:hover {{
    background: {ACCENT_TINT_HOVER};
}}
QFrame#qsSegment QToolButton#qsIconButton:disabled {{
    background: transparent;
}}
QFrame#qsSegment[qsRole="modes"] {{
    background: {SURFACE_CARD};
    border: 1px solid {HAIRLINE};
    border-radius: {SEGMENT_H // 2}px;
}}
QFrame#qsSegment[qsRole="modes"] QToolButton#qsIconButton {{
    border-radius: {pill}px;
}}

QPushButton {{
    background: {SURFACE_RAISED};
    border: 1px solid {HAIRLINE};
    border-radius: {CONTROL_RADIUS}px;
    padding: 2px {SPACE_3}px;
    color: {TEXT_PRIMARY};
    min-height: {button_h}px;
}}
QPushButton:hover {{
    background: {SURFACE_HOVER};
    border-color: {HAIRLINE_STRONG};
}}
QPushButton:pressed {{
    background: {SURFACE_PRESSED};
}}
QPushButton:checked {{
    background: {ACCENT_TINT};
    color: {ACCENT};
}}
QPushButton:checked:hover {{
    background: {ACCENT_TINT_HOVER};
}}
QPushButton:focus {{
    border-color: {FOCUS_RING};
}}
QPushButton:disabled {{
    background: {SURFACE_CARD};
    border-color: {HAIRLINE};
    color: {TEXT_MUTED};
}}
QPushButton::menu-indicator {{
    image: none;
    width: 0px;
}}

QPushButton#qsChip {{
    background: transparent;
    border: none;
    border-radius: {chip_h // 2}px;
    padding: 0px {SPACE_3}px;
    min-height: {chip_h}px;
    color: {TEXT_SECONDARY};
}}
QPushButton#qsChip:hover {{
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
}}
QPushButton#qsChip:pressed {{
    background: {SURFACE_PRESSED};
}}
QPushButton#qsChip:checked {{
    background: {ACCENT_TINT};
    color: {ACCENT};
}}
QPushButton#qsChip:checked:hover {{
    background: {ACCENT_TINT_HOVER};
}}
QPushButton#qsChip:disabled {{
    background: transparent;
    color: {TEXT_MUTED};
}}

QPushButton#qsViewMenu {{
    background: transparent;
    border: none;
    border-radius: {CONTROL_RADIUS}px;
    padding: 0px {SPACE_2}px;
    min-height: {GHOST_BUTTON_H}px;
    color: {TEXT_SECONDARY};
}}
QPushButton#qsViewMenu:hover {{
    background: {view_hover};
    color: {TEXT_PRIMARY};
}}
QPushButton#qsViewMenu:pressed, QPushButton#qsViewMenu:open {{
    background: {view_open};
    color: {ACCENT};
}}
QPushButton#qsViewMenu:disabled {{
    background: transparent;
    color: {TEXT_MUTED};
}}
QPushButton#qsViewMenu::menu-indicator {{
    image: none;
    width: 0px;
}}

QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-radius: {CHIP_H // 2}px;
    padding: 3px {SPACE_3}px;
    margin-right: {SPACE_1}px;
    min-height: {chip_h - 6}px;
}}
QTabBar::tab:selected {{
    background: {ACCENT_TINT};
    color: {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
}}
QTabWidget::pane {{
    border: none;
    background: transparent;
}}

QWidget#qsPanelTabBar {{
    background: transparent;
}}
QPushButton#qsPanelTab {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: {ACCENT_BAR_W}px solid transparent;
    border-radius: 0px;
    padding: 0px {SPACE_2}px;
    min-height: {tab_h}px;
    max-height: {tab_h}px;
    font-size: {FONT_GROUP_POINT_SIZE}pt;
    font-weight: 600;
}}
QPushButton#qsPanelTab:hover {{
    background: transparent;
    color: {TEXT_PRIMARY};
}}
QPushButton#qsPanelTab:pressed {{
    background: transparent;
}}
QPushButton#qsPanelTab:checked {{
    background: transparent;
    color: {TEXT_SECONDARY};
}}
QPushButton#qsPanelTab[multi="true"]:checked {{
    color: {TEXT_PRIMARY};
    border-bottom: {ACCENT_BAR_W}px solid {ACCENT};
}}
QPushButton#qsPanelTab:disabled {{
    background: transparent;
    color: {TEXT_MUTED};
}}
QWidget#qsPanelMenuBar {{
    background: transparent;
}}
QPushButton#qsPanelMenu {{
    background: transparent;
    border: none;
    border-radius: {CONTROL_RADIUS}px;
    padding: 1px {SPACE_2}px;
    min-height: {button_h}px;
    color: {TEXT_SECONDARY};
}}
QPushButton#qsPanelMenu:hover {{
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
}}
QPushButton#qsPanelMenu:pressed, QPushButton#qsPanelMenu:open {{
    background: {SURFACE_PRESSED};
    color: {TEXT_PRIMARY};
}}
QPushButton#qsPanelMenu:disabled {{
    background: transparent;
    color: {TEXT_MUTED};
}}
QPushButton#qsPanelMenu::menu-indicator {{
    image: none;
    width: 0px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {HAIRLINE_STRONG};
    min-height: 24px;
    border-radius: 4px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {HAIRLINE_STRONG};
    min-width: 24px;
    border-radius: 4px;
    margin: 0px;
}}
QScrollBar::handle:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::handle:pressed {{ background: {TEXT_SECONDARY}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit {{
    background: {SURFACE_FIELD};
    border: 1px solid {HAIRLINE};
    border-radius: {CONTROL_RADIUS}px;
    padding: 1px {SPACE_2 - 2}px;
    min-height: {field_h}px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_TINT_HOVER};
    selection-color: {TEXT_PRIMARY};
}}
QLineEdit:hover, QAbstractSpinBox:hover, QTextEdit:hover, QPlainTextEdit:hover {{
    background: {SURFACE_FIELD_HOVER};
    border-color: {HAIRLINE_STRONG};
}}
QLineEdit:focus, QAbstractSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    background: {SURFACE_FIELD};
    border-color: {FOCUS_RING};
}}
QLineEdit:disabled, QAbstractSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    color: {TEXT_MUTED};
    background: {SURFACE_CARD};
    border-color: {HAIRLINE};
}}
QLineEdit#qsCoordField {{
    qproperty-alignment: AlignCenter;
}}
QAbstractSpinBox QLineEdit, QComboBox QLineEdit {{
    background: transparent;
    border: none;
    border-radius: 0px;
    padding: 0px;
    min-height: 0px;
    selection-background-color: {ACCENT_TINT_HOVER};
}}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 14px;
}}

QComboBox {{
    background: {SURFACE_FIELD};
    border: 1px solid {HAIRLINE};
    border-radius: {CONTROL_RADIUS}px;
    padding: 1px 20px 1px {SPACE_2 - 2}px;
    min-height: {field_h}px;
    color: {TEXT_PRIMARY};
    combobox-popup: 0;
}}
QComboBox:hover {{
    background: {SURFACE_FIELD_HOVER};
    border-color: {HAIRLINE_STRONG};
}}
QComboBox:focus, QComboBox:on {{
    border-color: {FOCUS_RING};
}}
QComboBox:disabled {{
    color: {TEXT_MUTED};
    background: {SURFACE_CARD};
    border-color: {HAIRLINE};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}}
QComboBox::down-arrow {{
    width: 8px;
    height: 8px;
}}
QComboBoxPrivateContainer {{
    background: {SURFACE_MENU};
    border: 1px solid {HAIRLINE};
    border-radius: {MENU_RADIUS}px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_MENU};
    border: none;
    border-radius: {MENU_RADIUS}px;
    padding: {SPACE_1}px;
    selection-background-color: {ACCENT_TINT_MENU};
    selection-color: {TEXT_BRIGHT};
    color: {TEXT_PRIMARY};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    min-height: {MENU_ROW_H}px;
    padding: 0px {SPACE_2}px;
    border: none;
    border-radius: {CONTROL_RADIUS}px;
    background: transparent;
}}
QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {{
    background: {ACCENT_TINT_MENU};
    color: {TEXT_BRIGHT};
    border: none;
}}

QCheckBox {{
    spacing: {SPACE_2 - 2}px;
    color: {TEXT_PRIMARY};
    background: transparent;
}}
QCheckBox:disabled {{ color: {TEXT_MUTED}; }}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    background: {SURFACE_FIELD};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 4px;
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT_HOVER}; }}
QCheckBox::indicator:pressed {{ border-color: {ACCENT_PRESSED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:checked:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QCheckBox::indicator:checked:pressed {{ background: {ACCENT_PRESSED}; border-color: {ACCENT_PRESSED}; }}
QCheckBox::indicator:disabled {{ background: {SURFACE_CARD}; border-color: {HAIRLINE}; }}
QCheckBox::indicator:checked:disabled {{
    background: {checked_disabled};
    border-color: {checked_disabled};
}}

QSlider {{ background: transparent; min-height: 16px; }}
QSlider::groove:horizontal {{
    height: 3px;
    background: {HAIRLINE};
    border-radius: 1px;
}}
QSlider::sub-page:horizontal {{
    height: 3px;
    background: {ACCENT_PRESSED};
    border-radius: 1px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 10px;
    height: 10px;
    margin: -4px 0px;
    border-radius: 5px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT_HOVER}; }}
QSlider::handle:horizontal:pressed {{ background: {ACCENT_PRESSED}; }}
QSlider::handle:horizontal:disabled {{ background: {HAIRLINE_STRONG}; }}

QLabel {{ background: transparent; }}
QLabel#qsDimLabel {{ color: {TEXT_SECONDARY}; }}
QLabel#qsDimLabel:disabled {{ color: {TEXT_MUTED}; }}
QLabel#qsGroupTitle {{
    color: {TEXT_SECONDARY};
    font-weight: 600;
    font-size: {FONT_GROUP_POINT_SIZE}pt;
}}
QLabel#qsGroupTitle[qsHover="true"] {{ color: {TEXT_PRIMARY}; }}
QLabel#qsGroupTitle:disabled {{ color: {TEXT_MUTED}; }}

QTreeView, QListView, QTableView, QTreeWidget {{
    background: transparent;
    alternate-background-color: transparent;
    border: none;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_TINT};
    selection-color: {TEXT_PRIMARY};
}}
QTreeView::item, QListView::item {{
    min-height: {ROW_H}px;
    border: none;
    border-left: {ACCENT_BAR_W}px solid transparent;
    background: transparent;
}}
QTreeView::item:hover, QListView::item:hover {{
    background: {SURFACE_RAISED};
}}
QTreeView::item:selected, QListView::item:selected {{
    background: {ACCENT_TINT};
    border-left: {ACCENT_BAR_W}px solid {ACCENT};
    color: {TEXT_PRIMARY};
}}
QTreeView::item:selected:hover, QListView::item:selected:hover {{
    background: {ACCENT_TINT_HOVER};
}}
QTreeView::item:disabled, QListView::item:disabled {{
    color: {TEXT_MUTED};
}}
QHeaderView::section {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    padding: 2px {SPACE_2 - 2}px;
}}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: {CARD_GAP}px; }}
QSplitter::handle:vertical {{ height: {CARD_GAP}px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QFrame#qsPlaceholder {{
    background: {SURFACE_CARD};
    border: 1px dashed {HAIRLINE_STRONG};
    border-radius: {CARD_RADIUS}px;
}}
QFrame#qsPlaceholder QLabel {{ color: {TEXT_MUTED}; }}

QWidget[qsCard="true"] {{
    background: {SURFACE_CARD};
    border: 1px solid {HAIRLINE};
    border-radius: {CARD_RADIUS}px;
}}
QWidget#qsTopBar {{ background: {SURFACE_BACKDROP}; }}
QStatusBar#qsStatusBar {{ background: {SURFACE_BACKDROP}; border: none; }}
QStatusBar#qsStatusBar::item {{ border: none; }}
QStatusBar#qsStatusBar QLabel {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SMALL_POINT_SIZE}pt;
}}
QStatusBar#qsStatusBar QLabel#qsStatusMode {{ color: {TEXT_PRIMARY}; }}
QFrame#qsProjectChip {{
    background: {SURFACE_RAISED};
    border: 1px solid {HAIRLINE};
    border-radius: {CHIP_H // 2}px;
}}
QFrame#qsProjectChip QLabel {{ color: {TEXT_PRIMARY}; }}
"""
