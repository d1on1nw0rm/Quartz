from quartz._version import VERSION, __version__, APP_NAME, AUTHOR

LAZY_SUBMODULES: frozenset[str] = frozenset({
    "addons", "app", "bmesh", "cli", "compat", "contexts", "depsgraph", "errors", "extras",
    "geometry", "io", "math", "operators", "ops", "path", "props", "registry", "rna", "scan",
    "session", "sweep", "testing", "types", "ui", "undo", "utils",
})


def __getattr__(name: str) -> object:
    import importlib

    if name == "data":
        session = importlib.import_module("quartz.session")
        return session.api_data()
    if name == "context":
        session = importlib.import_module("quartz.session")
        return session.api_context()
    if name == "msgbus":
        return importlib.import_module("quartz.app.msgbus")
    if name in LAZY_SUBMODULES:
        return importlib.import_module(f"quartz.{name}")
    raise AttributeError(f"module 'quartz' has no attribute '{name}'")


def __dir__() -> list[str]:
    return sorted(LAZY_SUBMODULES | {"data", "context", "msgbus", "VERSION", "__version__", "APP_NAME", "AUTHOR"})
