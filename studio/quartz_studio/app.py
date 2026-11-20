from __future__ import annotations

import logging
import os
import sys
import tempfile
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from quartz_studio import APP_NAME, __version__, icons, theme
from quartz_studio.widgets import press_feedback


def _dark_palette() -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: theme.BG_WINDOW,
        QPalette.ColorRole.WindowText: theme.TEXT,
        QPalette.ColorRole.Base: theme.BG_FIELD,
        QPalette.ColorRole.AlternateBase: theme.BG_PANEL,
        QPalette.ColorRole.ToolTipBase: theme.BG_TOOLTIP,
        QPalette.ColorRole.ToolTipText: theme.TEXT,
        QPalette.ColorRole.PlaceholderText: theme.TEXT_DISABLED,
        QPalette.ColorRole.Text: theme.TEXT,
        QPalette.ColorRole.Button: theme.BG_BUTTON,
        QPalette.ColorRole.ButtonText: theme.TEXT,
        QPalette.ColorRole.BrightText: theme.TEXT_BRIGHT,
        QPalette.ColorRole.Highlight: theme.ACCENT_TINT_HOVER,
        QPalette.ColorRole.HighlightedText: theme.TEXT_BRIGHT,
        QPalette.ColorRole.Light: theme.HAIRLINE_STRONG,
        QPalette.ColorRole.Midlight: theme.HAIRLINE,
        QPalette.ColorRole.Mid: theme.SURFACE_RAISED,
        QPalette.ColorRole.Dark: theme.SURFACE_FIELD,
        QPalette.ColorRole.Shadow: theme.SURFACE_BACKDROP,
        QPalette.ColorRole.Link: theme.ACCENT_TEXT,
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(theme.TEXT_DISABLED))
    return pal


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    font = QFont(theme.FONT_FAMILY, theme.FONT_POINT_SIZE)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    asset_dir = os.path.join(tempfile.gettempdir(), f"quartz_studio_{__version__}_qss")
    try:
        assets = icons.write_qss_assets(asset_dir)
    except OSError:
        logging.getLogger("quartz_studio").warning("could not write QSS assets to %s", asset_dir)
        assets = None
    app.setStyleSheet(theme.stylesheet(assets))
    press_feedback.install(app)


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Quartz")
    apply_theme(app)
    return app


def colorref(color: str) -> int:
    value = QColor(color)
    return (value.blue() << 16) | (value.green() << 8) | value.red()


def apply_native_titlebar(window) -> None:
    if sys.platform != "win32" or QGuiApplication.platformName() == "offscreen":
        return
    try:
        import ctypes

        handle = int(window.winId())
        attributes = (
            (20, 1),
            (35, colorref(theme.SURFACE_BACKDROP)),
            (36, colorref(theme.TEXT_PRIMARY)),
            (34, colorref(theme.HAIRLINE)),
        )
        for attribute, raw in attributes:
            value = ctypes.c_int(raw)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(handle), attribute, ctypes.byref(value), 4
            )
    except Exception:
        return


APP_USER_MODEL_ID = "Quartz.Studio"


def set_instance_identity(app: QApplication) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except (AttributeError, OSError):
            logging.getLogger("quartz_studio").warning("could not set the AppUserModelID")
    from quartz_studio.main_window import window_icon

    app.setWindowIcon(window_icon())


def install_extensions(window) -> bool:
    try:
        from quartz_studio.ext import install as ext_install
    except ImportError as exc:
        if exc.name not in ("quartz_studio.ext", "quartz_studio.ext.install"):
            traceback.print_exc(file=sys.stderr)
        return False
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return False
    from quartz_studio import controls

    try:
        with controls.deferred_refresh():
            ext_install.install(window)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return False
    return True


def apply_icon_overrides() -> bool:
    try:
        from quartz_studio.ext import icon_overrides
    except ImportError:
        return False
    try:
        icon_overrides.apply()
    except Exception:
        traceback.print_exc()
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    app = create_app(argv)
    set_instance_identity(app)
    from quartz_studio import controls, prefs
    from quartz_studio.controls import store as controls_store
    from quartz_studio.modeling import install as modeling_install
    from quartz_studio.main_window import MainWindow

    prefs.use_user_profile()
    controls_store.first_run()
    modeling_install.prepare()
    apply_icon_overrides()
    window = MainWindow()
    modeling_install.install(window)
    install_extensions(window)
    controls.refresh()
    window.showMaximized()
    apply_native_titlebar(window)
    from quartz_studio import project

    paths = project.paths_from_argv(sys.argv if argv is None else argv)
    if paths:
        QTimer.singleShot(0, lambda: project.open_paths(paths))
    return app.exec()
