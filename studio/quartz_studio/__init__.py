import os as _os
import sys as _sys

if _sys.platform == "win32" and "QT_QPA_FONTDIR" not in _os.environ:
    _fonts = _os.path.join(_os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    if _os.path.isdir(_fonts):
        _os.environ["QT_QPA_FONTDIR"] = _fonts

__version__ = "1.0.0"
APP_NAME = "Quartz Studio"
APP_VERSION_SHORT = "1.0"
DOCUMENT_NAME = "Untitled"
LAYOUT_NAME = "Main"
TITLE_SUFFIX = "Quartz"
WINDOW_TITLE = f"{DOCUMENT_NAME} - {TITLE_SUFFIX}"
