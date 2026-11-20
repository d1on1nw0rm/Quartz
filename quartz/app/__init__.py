import os
import sys

from quartz.app import handlers, timers, msgbus, translations, settings, paths

version: tuple[int, int, int] = (0, 1, 0)
version_string: str = "0.1.0"
version_cycle: str = "alpha"
background: bool = True
factory_startup: bool = True
debug: bool = False
debug_value: int = 0
binary_path: str = sys.executable
driver_namespace: dict[str, object] = {}
online_access: bool = False
online_access_override: bool = False
portable: bool = True
python_args: tuple[str, ...] = ()


def trusted() -> bool:
    return bool(settings.settings.trust_scripts)


def __getattr__(name: str) -> object:
    if name == "tempdir":
        return str(paths.temp_dir()) + os.sep
    if name == "cachedir":
        return str(paths.user_dir() / "cache") + os.sep
    raise AttributeError(f"module 'quartz.app' has no attribute '{name}'")
