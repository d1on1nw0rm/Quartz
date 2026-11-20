import os
from pathlib import Path
import sys

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return None
    return v


_ADDON_DIRS: list[Path] = []
_EXTENSION_REPOS: dict[str, Path] = {}
_CONFIGURED: bool = False


def _ensure_configured() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    _ADDON_DIRS.clear()
    _ADDON_DIRS.append(scripts_dir() / "addons")
    _EXTENSION_REPOS.clear()
    _EXTENSION_REPOS["user_default"] = extensions_dir() / "user_default"
    _EXTENSION_REPOS["system"] = extensions_dir() / "system"


def reset() -> None:
    global _CONFIGURED
    _ADDON_DIRS.clear()
    _EXTENSION_REPOS.clear()
    _CONFIGURED = False


def user_dir() -> Path:
    v = _env("QUARTZ_USER_DIR")
    if v is not None:
        p = Path(v)
    else:
        p = PROJECT_ROOT / "tmp" / "quartz_user"
    p.mkdir(parents=True, exist_ok=True)
    return p


def temp_dir() -> Path:
    p = user_dir() / "temp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    p = user_dir() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p


def scripts_dir() -> Path:
    p = user_dir() / "scripts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def datafiles_dir() -> Path:
    p = user_dir() / "datafiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def extensions_dir() -> Path:
    p = user_dir() / "extensions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def addon_dirs() -> list[Path]:
    _ensure_configured()
    return _ADDON_DIRS


def extension_repos() -> dict[str, Path]:
    _ensure_configured()
    return _EXTENSION_REPOS


def add_addon_dir(path: str | Path) -> None:
    _ensure_configured()
    p = Path(path)
    if p not in _ADDON_DIRS:
        _ADDON_DIRS.append(p)


def add_extension_repo(module: str, path: str | Path) -> None:
    if not isinstance(module, str) or not module.isidentifier():
        raise ValueError(f"invalid module name: {module!r}")
    _ensure_configured()
    _EXTENSION_REPOS[module] = Path(path)


def compat_dir() -> Path:
    v = _env("QUARTZ_COMPAT_DIR")
    if v is not None:
        return Path(v)
    return PROJECT_ROOT / "compat"
